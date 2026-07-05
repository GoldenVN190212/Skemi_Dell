/**
 * guest-storage-guard.js — Synchronous, ES5-only guard that runs in <head>
 * BEFORE any module script (Home.js, Search.js, …) reads localStorage.
 *
 * Why this exists:
 *   Module scripts are deferred — they execute after HTML parsing. Inline
 *   scripts in <head> execute immediately. Home.js calls loadProjects() near
 *   the bottom of its module, which reads `skemi_studio_projects_v1`. If the
 *   previous user signed out (or never signed in but the tab has stale data),
 *   that key still holds their projects and they flash on screen before the
 *   async auth-state listener can clear them.
 *
 *   This script inspects Firebase's own auth persistence — Firebase stores
 *   the active user as a localStorage key matching `firebase:authUser:…`.
 *   If no such key is present, no user is signed in; we flush every key in
 *   USER_DATA_KEYS before render code runs.
 *
 *   Theme, language, and other device-local prefs are preserved.
 *
 * Sync with UserScopedStorage.js — keep the two key lists aligned.
 */
(function () {
    try {
        var hasFirebaseUser = false;
        for (var i = 0; i < localStorage.length; i++) {
            var k = localStorage.key(i);
            if (k && k.indexOf('firebase:authUser:') === 0) {
                hasFirebaseUser = true;
                break;
            }
        }
        if (hasFirebaseUser) return;

        var USER_DATA_KEYS = [
            'skemi_studio_projects_v1',
            'skemi_search_notebook_active',
            'skemi_search_notebook_q',
            'skemi_search_notebook_deep',
            'skemi_global_pulse_notebook',
            'skemi_ai_pending_command_v1',
            'skemi_ai_workflow_state_v1',
            'skemi_workspace_seed_v1',
            'skemi_search_history_v1',
            'skemi_search_result_cache_v3',
            'skemi_private_quiz_rooms_v1',
            'ai_chat_history',
            'chat_session_id',
            'skemi_user_data',
            'skemi_token',
            'skemi_user_id',
            'skemi_username',
            'skemi_role',
            'skemi_ai_working_v1',
            'skemi_job_notify_state_v1',
            'skemi_job_event_v3',
            'skemi_phantom_locked_desktop_v1',
            'skemi_phantom_command_history_v1'
        ];
        var prefixes = [
            'skemi_studio_project:',
            'skemi_notebook:',
            'skemi_quiz_room:',
            'skemi_ai_session_id_v1_',
            'skemi_surface_session_id_v1',
            'skemi_phantom_'
        ];
        var i2, key, removed = 0;
        // 1. Drop legacy un-namespaced keys (pre-per-account data).
        for (i2 = 0; i2 < USER_DATA_KEYS.length; i2++) {
            key = USER_DATA_KEYS[i2];
            if (localStorage.getItem(key) !== null) {
                localStorage.removeItem(key);
                removed++;
            }
        }
        // 2. Drop _guest slot — leftover data from previous unauthenticated session.
        var allKeys = [];
        for (i2 = 0; i2 < localStorage.length; i2++) {
            allKeys.push(localStorage.key(i2));
        }
        var GUEST_SUFFIX = '_guest';
        for (i2 = 0; i2 < allKeys.length; i2++) {
            key = allKeys[i2];
            if (!key) continue;
            // Match either `${baseKey}_guest` (per-account namespaced) or one of
            // the dynamic prefixes (legacy multi-part keys).
            if (key.length >= GUEST_SUFFIX.length &&
                key.indexOf(GUEST_SUFFIX, key.length - GUEST_SUFFIX.length) !== -1) {
                localStorage.removeItem(key);
                removed++;
                continue;
            }
            for (var p = 0; p < prefixes.length; p++) {
                if (key.indexOf(prefixes[p]) === 0) {
                    localStorage.removeItem(key);
                    removed++;
                    break;
                }
            }
        }
        if (removed && window.console && (function(){})) {
            (function(){})('[guest-storage-guard] wiped ' + removed + ' user-scoped keys (no Firebase session)');
        }
    } catch (e) {
        if (window.console && console.warn) console.warn('[guest-storage-guard] failed', e);
    }
})();
