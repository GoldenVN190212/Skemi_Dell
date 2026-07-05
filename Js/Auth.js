/**
 * Auth.js — Skemi (1) auth integration layer (passive listener)
 *
 * Background: Skemi (1) Login.html and Register.html have their own inline
 * Firebase submit handlers (UI flow polished for this app). Auth.js used to
 * bind a competing submit listener which fired sign-in twice — the form-
 * binding logic now lives ONLY inline in those two pages.
 *
 * Auth.js's job today:
 *   1. Re-export Firebase `auth`, `signOut`, `onAuthStateChanged` so module
 *      consumers (UserScopedStorage, User_navbar, page-level scripts) can
 *      import from one place.
 *   2. Expose a `SkemiAuth` backward-compat shim on `window` for legacy code
 *      (Phantom, Computer pages, older fetch wrappers) that asks for
 *      `SkemiAuth.getToken()`. The shim now returns the Firebase ID token.
 *   3. Listen to `onAuthStateChanged` and mirror critical fields to
 *      localStorage (`skemi_token`, `skemi_user_id`, `skemi_username`). This
 *      lets non-module pages read `localStorage.getItem('skemi_user_id')`
 *      synchronously after login without re-touching Firebase.
 *
 * It does NOT bind form submit handlers — the Login/Register HTML do that.
 */
import { auth, db } from './Firebase_config.js';
import {
  signOut,
  onAuthStateChanged
} from 'https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js';

export { auth, db, signOut, onAuthStateChanged };

// ────────────────────────────────────────────────────────────────────────────
// Backward-compat SkemiAuth shim
// ────────────────────────────────────────────────────────────────────────────
const TOKEN_KEY = 'skemi_token';

const SkemiAuth = {
    TOKEN_KEY,
    async getToken() {
        try {
            const user = auth.currentUser;
            if (user) {
                const idToken = await user.getIdToken();
                if (idToken) {
                    localStorage.setItem(TOKEN_KEY, idToken);
                    return idToken;
                }
            }
        } catch (e) { /* fall through */ }
        return localStorage.getItem(TOKEN_KEY) || null;
    },
    getTokenSync() {
        return localStorage.getItem(TOKEN_KEY) || null;
    },
    isLoggedIn() {
        return !!auth.currentUser || !!localStorage.getItem(TOKEN_KEY);
    },
    async getHeaders() {
        const t = await this.getToken();
        return t ? { 'Authorization': `Bearer ${t}` } : {};
    },
    async logout() {
        try {
            if (window.SkemiUserScopedStorage?.clearUserScopedStorage) {
                window.SkemiUserScopedStorage.clearUserScopedStorage();
            }
            await signOut(auth);
        } catch (e) { /* never block redirect */ }
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem('skemi_user_id');
        localStorage.removeItem('skemi_username');
        window.location.href = '/Login.html';
    },
    async requireAuth() {
        // Wait one auth callback so we don't false-redirect on first-load
        // before Firebase has restored its persisted session.
        if (auth.currentUser) return true;
        await new Promise((resolve) => {
            const unsub = onAuthStateChanged(auth, () => { unsub(); resolve(); });
        });
        if (!auth.currentUser && !localStorage.getItem(TOKEN_KEY)) {
            window.location.href = '/Login.html';
            return false;
        }
        return true;
    }
};

window.SkemiAuth = SkemiAuth;
window.getAuthToken = () => SkemiAuth.getTokenSync() || '';
// Legacy globals — Settings.html, Search.js, Features.js, SettingsPage.js etc.
// were written when Auth.js was a classic script that put these on window.
// Now Auth.js is an ES module, so we need to expose them explicitly.
window.auth = auth;
window.signOut = signOut;
window.onAuthStateChanged = onAuthStateChanged;

// ────────────────────────────────────────────────────────────────────────────
// Passive auth state mirror
// ────────────────────────────────────────────────────────────────────────────
// Caches uid + idToken + username to localStorage so non-module pages can
// read them synchronously. Doesn't touch user data keys — that's
// UserScopedStorage's job, and it listens to the same event.
onAuthStateChanged(auth, async (user) => {
    if (user) {
        try {
            const t = await user.getIdToken();
            if (t) localStorage.setItem(TOKEN_KEY, t);
        } catch (e) { /* ignore */ }
        if (user.uid) localStorage.setItem('skemi_user_id', user.uid);
        const displayName = user.displayName || user.email || '';
        if (displayName) localStorage.setItem('skemi_username', displayName);
    } else {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem('skemi_user_id');
        localStorage.removeItem('skemi_username');
    }
});
