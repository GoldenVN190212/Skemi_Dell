/**
 * CloudSync.js — transparent server-side backup for account-scoped localStorage.
 *
 * PROBLEM this fixes: most sections (Studio, Search, Quiz, Chat AI, Phantom,
 * Legion, Skills…) read/write account data straight to localStorage via
 * account-storage.js (`loadUserData`/`saveUserData`) or the raw keys listed in
 * UserScopedStorage.js's USER_DATA_KEYS. That data was NEVER sent to the
 * server — and UserScopedStorage.js actively DELETES it on logout/account
 * switch (to stop a shared browser leaking one user's data to the next), so
 * every logout was silently destroying real history with no way back.
 *
 * FIX: this module doesn't change any of those call sites. It watches every
 * localStorage write, and for keys that belong to the signed-in account it
 * also mirrors the value to `/api/user/data/bulk` (debounced + batched) using
 * the SAME per-user SQLite storage the account already has. On sign-in it
 * pulls that account's data back down and hydrates localStorage BEFORE the
 * rest of the page acts on it (reloading once if anything actually changed),
 * so logging back in — even in a fresh browser — restores full history.
 *
 * Load AFTER account-storage.js, Auth.js and UserScopedStorage.js.
 */
import { auth, onAuthStateChanged } from './Auth.js';
import { USER_DATA_KEYS, USER_DATA_KEY_PREFIXES, PRESERVE_KEYS as DEVICE_LOCAL_KEYS } from './UserScopedStorage.js';

(function () {
    'use strict';

    const NAMESPACE = 'cloud_sync';
    const DEBOUNCE_MS = 1800;
    const pending = new Map(); // physical localStorage key -> value
    let flushTimer = null;
    let currentUid = null;
    let hydrating = false;

    function token() {
        try { return (window.SkemiAuth && window.SkemiAuth.getTokenSync && window.SkemiAuth.getTokenSync()) || null; }
        catch (e) { return null; }
    }

    function isTrackedKey(physicalKey) {
        if (DEVICE_LOCAL_KEYS.has(physicalKey)) return false;
        if (USER_DATA_KEYS.includes(physicalKey)) return true;
        if (USER_DATA_KEY_PREFIXES.some((p) => physicalKey.startsWith(p))) return true;
        // account-storage.js convention: `${baseKey}_${uid}`.
        if (currentUid && physicalKey.endsWith('_' + currentUid)) return true;
        return false;
    }

    // Server-side key drops the uid suffix (the row is already scoped by
    // user_id server-side, so keeping the uid in the key text is redundant
    // and would break lookups if we ever need to read it without the uid).
    function toServerKey(physicalKey) {
        if (currentUid && physicalKey.endsWith('_' + currentUid)) {
            return physicalKey.slice(0, -(currentUid.length + 1));
        }
        return physicalKey;
    }
    function toLocalKey(serverKey) {
        if (USER_DATA_KEYS.includes(serverKey) || USER_DATA_KEY_PREFIXES.some((p) => serverKey.startsWith(p))) {
            return serverKey; // raw session-style key — never uid-suffixed
        }
        return currentUid ? (serverKey + '_' + currentUid) : serverKey;
    }

    function scheduleFlush() {
        if (flushTimer) return;
        flushTimer = setTimeout(flush, DEBOUNCE_MS);
    }

    async function flush(keepaliveOnUnload) {
        flushTimer = null;
        if (!pending.size || hydrating) return;
        const t = token();
        if (!t) { pending.clear(); return; }
        const items = Array.from(pending.entries()).map(([k, v]) => ({ key: toServerKey(k), value: v }));
        pending.clear();
        try {
            await fetch('/api/user/data/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${t}` },
                body: JSON.stringify({ namespace: NAMESPACE, items }),
                keepalive: !!keepaliveOnUnload, // survives page unload (best-effort, small payloads only)
            });
        } catch (e) { /* best-effort background sync — never block the UI */ }
    }

    // ---- Capture every write to an account-scoped key ------------------------
    const _setItem = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, value) {
        _setItem(key, value);
        if (!hydrating && isTrackedKey(key)) {
            pending.set(key, value);
            scheduleFlush();
        }
    };

    window.addEventListener('beforeunload', () => { if (pending.size) flush(true); });
    window.addEventListener('pagehide', () => { if (pending.size) flush(true); });

    // ---- One-time repair: AIChat.js's per-account keys used to derive the uid
    // suffix from a field (`skemi_user_data.uid`) that was never actually
    // populated, so every signed-in user's Studio projects / chat history /
    // session state silently landed under a shared `_guest` slot instead of
    // their own account. Now that the suffix source is fixed, recover
    // whatever's sitting in that old `_guest` slot into the real account's
    // slot — but only if the real slot is still empty, so we never clobber
    // data a user already has under their own uid.
    const LEGACY_GUEST_MIGRATION_KEYS = [
        'skemi_ai_chat_history_v2', 'skemi_ai_session_id_v1', 'skemi_ai_pending_command_v1',
        'skemi_ai_workflow_state_v1', 'skemi_ai_pending_assistant_job_v1',
        'skemi_studio_projects_v1', 'skemi_search_state_v3', 'skemi_private_quiz_rooms_v1',
    ];
    function migrateLegacyGuestSlot(uid) {
        const flag = 'skemi_guest_migrated_' + uid;
        if (localStorage.getItem(flag)) return false;
        let migrated = false;
        LEGACY_GUEST_MIGRATION_KEYS.forEach((base) => {
            const guestVal = localStorage.getItem(base + '_guest');
            const realKey = base + '_' + uid;
            if (guestVal != null && localStorage.getItem(realKey) == null) {
                _setItem(realKey, guestVal);
                migrated = true;
            }
        });
        _setItem(flag, '1');
        return migrated;
    }

    // ---- On sign-in, restore this account's data from the server -------------
    async function hydrate(uid) {
        const t = token();
        if (!t) return;
        hydrating = true;
        let changed = migrateLegacyGuestSlot(uid);
        try {
            const res = await fetch(`/api/user/data/bulk?namespace=${encodeURIComponent(NAMESPACE)}`, {
                headers: { 'Authorization': `Bearer ${t}` },
            });
            if (res.ok) {
                const json = await res.json();
                const items = (json && json.data) || [];
                items.forEach((item) => {
                    let incoming;
                    try { incoming = JSON.parse(item.value); } catch (e) { incoming = item.value; }
                    if (typeof incoming !== 'string') incoming = JSON.stringify(incoming);
                    const localKey = toLocalKey(item.key);
                    if (localStorage.getItem(localKey) !== incoming) {
                        _setItem(localKey, incoming);
                        changed = true;
                    }
                });
            } // else: 401 = not authenticated yet; will retry on the next auth event.
              // Still fall through below — the guest-slot migration may have
              // changed something even if the server round-trip didn't.
        } catch (e) { /* offline / server hiccup — local cache still works */ }
        finally { hydrating = false; }

        if (changed) {
            // Most section code reads localStorage synchronously at load time and
            // won't notice this out-of-band write, so do a single reload to pick
            // it up cleanly. Guarded so we never reload more than once per uid
            // per tab session (and never loop if the server has nothing new).
            const flag = 'skemi_cloud_hydrated_' + uid;
            if (!sessionStorage.getItem(flag)) {
                sessionStorage.setItem(flag, '1');
                window.location.reload();
            }
        }
    }

    onAuthStateChanged(auth, (user) => {
        const newUid = (user && user.uid) || null;
        currentUid = newUid;
        if (newUid) hydrate(newUid);
    });
})();
