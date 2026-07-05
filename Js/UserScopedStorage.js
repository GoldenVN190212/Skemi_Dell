/**
 * UserScopedStorage.js — Single source of truth for which localStorage keys
 * belong to a logged-in user. Ported from Skemi (2) where this fixed the
 * "guest sees previous user's projects" data leak.
 *
 * Other modules (Home, Search, Features, AIChat, Chatbot, Phantom) write to
 * these keys assuming they're scoped to "the current user", but the keys
 * themselves are global. Before this module, signing out left every other
 * user's projects/notebooks/quiz rooms/chat history visible to whoever opened
 * the page next.
 *
 * This module:
 *   1. Lists every key that holds user-specific data (USER_DATA_KEYS).
 *   2. Exports clearUserScopedStorage() — call from the logout handler.
 *   3. Wires onAuthStateChanged(null) → clearUserScopedStorage() so any time
 *      the page loads without an authenticated user, prior user data is
 *      flushed before render code reads it.
 *   4. Leaves device-local prefs (theme, language) UNTOUCHED — those should
 *      survive logout.
 */

import { auth, onAuthStateChanged } from './Auth.js';

// Keys whose VALUES are tied to a specific signed-in user.
// Edit this list whenever a new feature stores per-user data.
export const USER_DATA_KEYS = Object.freeze([
    // Studio / Home
    'skemi_studio_projects_v1',
    'skemi_search_notebook_active',
    'skemi_search_notebook_q',
    'skemi_search_notebook_deep',
    'skemi_global_pulse_notebook',
    'skemi_ai_pending_command_v1',
    'skemi_ai_workflow_state_v1',
    'skemi_workspace_seed_v1',

    // Search
    'skemi_search_history_v1',
    'skemi_search_result_cache_v3',

    // Quiz / Features
    'skemi_private_quiz_rooms_v1',

    // AIChat
    'ai_chat_history',

    // Chatbot session
    'chat_session_id',

    // Profile cache (Firestore mirror)
    'skemi_user_data',

    // Auth tokens issued during a session
    'skemi_token',
    'skemi_user_id',
    'skemi_username',
    'skemi_role',

    // Background AI activity flag
    'skemi_ai_working_v1',

    // Pending notification / job state
    'skemi_job_notify_state_v1',
    'skemi_job_event_v3',

    // Phantom (Skemi-specific) — locked desktop, AI command history
    'skemi_phantom_locked_desktop_v1',
    'skemi_phantom_command_history_v1',
]);

// Key prefixes — anything matching gets nuked too. Useful for dynamic keys
// like `skemi_studio_project:abc123`.
export const USER_DATA_KEY_PREFIXES = Object.freeze([
    'skemi_studio_project:',
    'skemi_notebook:',
    'skemi_quiz_room:',
    'skemi_ai_session_id_v1_',
    'skemi_surface_session_id_v1',
    'skemi_phantom_',
]);

// Keys that MUST survive logout (device-local prefs). Exported so CloudSync.js
// can exclude these from server sync too — device prefs shouldn't follow the
// account across machines, only the account-scoped data below should.
export const PRESERVE_KEYS = new Set([
    'skemi-theme',
    'chat-theme',
    'skemi_language',
    'skemi_lang_change',
    'skemi_runtime_ui_pack_cache_v1',
]);

// Wipe both legacy un-namespaced keys AND the per-uid slot for `targetUid`.
// With per-account namespacing (Js/account-storage.js) the live data lives at
// `${baseKey}:${uid}`. On logout/switch we drop the OLD user's slot so the
// next visitor starts blank — matching "đăng xuất thì xóa dữ liệu".
export function clearUserScopedStorage(targetUid = 'guest') {
    let removed = 0;
    // Match Skemi (1)'s existing `${baseKey}_${uid}` convention (see
    // StorageManager.js + AIChat.js _uidSuffix). Wiping by underscore suffix
    // hits both account-storage.js writes and AIChat's per-uid keys.
    const suffix = '_' + String(targetUid);

    // 1. Legacy un-namespaced keys (pre-account-storage.js data we don't trust).
    for (const key of Object.keys(localStorage)) {
        if (PRESERVE_KEYS.has(key)) continue;
        if (USER_DATA_KEYS.includes(key)) {
            localStorage.removeItem(key);
            removed++;
        } else if (USER_DATA_KEY_PREFIXES.some((p) => key.startsWith(p))) {
            localStorage.removeItem(key);
            removed++;
        }
    }
    // 2. Per-uid slot for the user we're clearing out.
    for (const key of Object.keys(localStorage)) {
        if (PRESERVE_KEYS.has(key)) continue;
        if (key.endsWith(suffix)) {
            localStorage.removeItem(key);
            removed++;
        }
    }

    try {
        window.dispatchEvent(new CustomEvent('skemi:user-data-cleared', { detail: { uid: targetUid } }));
    } catch { /* never let cleanup throw */ }
    if (removed) (function(){})(`[UserScopedStorage] cleared ${removed} keys for uid=${targetUid}`);
    return removed;
}

let lastKnownUid = null;

onAuthStateChanged(auth, (user) => {
    const newUid = user?.uid || null;
    if (lastKnownUid !== null && newUid !== lastKnownUid) {
        // User changed (logged out or switched account) — drop old user's slot.
        clearUserScopedStorage(lastKnownUid);
    } else if (lastKnownUid === null && newUid === null) {
        // First load with no user — clear the guest slot + leaked legacy keys.
        clearUserScopedStorage('guest');
    }
    lastKnownUid = newUid;
});

if (typeof window !== 'undefined') {
    window.SkemiUserScopedStorage = { clearUserScopedStorage, USER_DATA_KEYS };
}
