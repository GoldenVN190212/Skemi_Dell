/**
 * account-storage.js — Per-account localStorage namespace helper.
 * Ported from Skemi (2). See that file for the full design rationale.
 *
 * Every user-bound key is stored at `${baseKey}:${uid}` where uid comes from
 * Firebase auth. When the user changes (login, logout, switch account), reads
 * and writes automatically point at the right slot — no cross-contamination.
 *
 *   const projects = JSON.parse(loadUserData('skemi_studio_projects_v1') || '[]');
 *   saveUserData('skemi_studio_projects_v1', JSON.stringify(projects));
 *
 * Pair with:
 *   - guest-storage-guard.js: synchronous wipe in <head> for guest sessions
 *   - UserScopedStorage.js: auth-state listener that wipes on logout / switch
 */
(function (root) {
    'use strict';

    var GUEST = 'guest';

    function getCurrentUid() {
        try {
            if (root.auth && root.auth.currentUser && root.auth.currentUser.uid) {
                return root.auth.currentUser.uid;
            }
        } catch (e) { /* ignore */ }
        var cached = '';
        try { cached = localStorage.getItem('skemi_user_id') || ''; } catch (e) { /* ignore */ }
        return cached || GUEST;
    }

    function scopedKey(baseKey) {
        var uid = getCurrentUid();
        // Use `_` separator to match Skemi (1)'s existing StorageManager.js
        // and AIChat.js conventions (`${baseKey}_${uid}`). The colon was a
        // mistake — switching to underscore lets StorageManager.clearAllUserData
        // also see and clean these keys.
        return String(baseKey) + '_' + uid;
    }

    function loadUserData(baseKey) {
        try { return localStorage.getItem(scopedKey(baseKey)); }
        catch (e) { return null; }
    }

    function saveUserData(baseKey, value) {
        try { localStorage.setItem(scopedKey(baseKey), value); return true; }
        catch (e) { return false; }
    }

    function removeUserData(baseKey) {
        try { localStorage.removeItem(scopedKey(baseKey)); return true; }
        catch (e) { return false; }
    }

    function clearAccountData(uid) {
        var target = uid || getCurrentUid();
        var suffix = '_' + target;
        var removed = 0;
        try {
            var keys = [];
            for (var i = 0; i < localStorage.length; i++) {
                var k = localStorage.key(i);
                if (k && k.indexOf(suffix, k.length - suffix.length) !== -1) keys.push(k);
            }
            for (var j = 0; j < keys.length; j++) {
                localStorage.removeItem(keys[j]);
                removed++;
            }
        } catch (e) { /* ignore */ }
        return removed;
    }

    var SkemiAccountStorage = {
        getCurrentUid: getCurrentUid,
        scopedKey: scopedKey,
        load: loadUserData,
        save: saveUserData,
        remove: removeUserData,
        clearForUid: clearAccountData,
        GUEST_UID: GUEST
    };

    if (typeof window !== 'undefined') {
        window.SkemiAccountStorage = SkemiAccountStorage;
        window.loadUserData = loadUserData;
        window.saveUserData = saveUserData;
        window.removeUserData = removeUserData;
    }
})(typeof window !== 'undefined' ? window : globalThis);
