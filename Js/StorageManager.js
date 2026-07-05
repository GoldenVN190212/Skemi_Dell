/**
 * StorageManager.js
 * Utility để quản lý per-user localStorage.
 * Tất cả dữ liệu user-specific phải sử dụng StorageManager để tránh data leakage giữa các user.
 */

export function getCurrentUserUID() {
    // `skemi_user_data` (the Firestore profile mirror) never actually contains
    // a `uid`/`user_id` field — that lookup always returned null, so every
    // caller's per-user key list resolved empty. `skemi_user_id` is what
    // Auth.js actually sets from the real Firebase uid on sign-in.
    try {
        return localStorage.getItem('skemi_user_id') || null;
    } catch {
        return null;
    }
}

/**
 * Lấy tất cả storage keys đặc trưng cho user UID hiện tại
 * Dùng khi logout để clear tất cả user-specific data
 * @returns {string[]} list các keys cần xóa
 */
export function getAllUserSpecificKeys() {
    const uid = getCurrentUserUID();
    if (!uid) return [];

    const baseKeys = [
        'skemi_studio_projects_v1',
        'skemi_search_history_v1',
        'skemi_search_state_v3',
        'skemi_ai_pending_command_v1',
        'skemi_ai_chat_history_v3',
        'skemi_ai_session_id_v1',
        'skemi_ai_pending_assistant_job_v1',
        'skemi_ai_workflow_state_v1',
        'skemi_private_quiz_rooms_v1',
        'skemi_computer_mode',
        'skemi_computer_phantom_index',
        'skemi_notified_jobs',
        'chat_session_id',
        'skemi_active_computer_session_v1',
        'skemi_active_workflow_id_v1'
    ];

    return baseKeys.map(key => `${key}_${uid}`);
}

/**
 * Clear tất cả user-specific data khi logout
 * QUAN TRỌNG: Gọi này trước khi signOut từ Firebase
 */
export function clearAllUserData() {
    const keysToRemove = getAllUserSpecificKeys();
    keysToRemove.forEach(key => {
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.warn(`[StorageManager] Failed to remove key: ${key}`, e);
        }
    });
    (function(){})(`[StorageManager] Cleared ${keysToRemove.length} user-specific keys`);
}

/**
 * Migrate old global keys to per-user keys (one-time migration)
 * Gọi khi user login lần đầu tiên
 */
export function migrateGlobalKeyToUserKey(baseKey) {
    const uid = getCurrentUserUID();
    if (!uid) return;

    try {
        const globalValue = localStorage.getItem(baseKey);
        if (globalValue) {
            const perUserKey = `${baseKey}_${uid}`;
            // Nếu per-user key chưa tồn tại, copy từ global
            if (!localStorage.getItem(perUserKey)) {
                localStorage.setItem(perUserKey, globalValue);
                (function(){})(`[StorageManager] Migrated ${baseKey} to ${perUserKey}`);
            }
            // Xóa global key để tránh confusion
            localStorage.removeItem(baseKey);
        }
    } catch (e) {
        console.warn(`[StorageManager] Migration failed for ${baseKey}:`, e);
    }
}

/**
 * Migrate tất cả global keys sang per-user keys
 * Gọi trong onAuthStateChanged khi user login
 */
export function migrateAllGlobalKeys() {
    const baseKeys = [
        'skemi_studio_projects_v1',
        'skemi_search_history_v1',
        'skemi_search_state_v3',
        'skemi_notified_jobs',
        'chat_session_id',
        'skemi_ai_pending_command_v1',
        'skemi_ai_chat_history_v3',
        'skemi_ai_session_id_v1',
        'skemi_ai_pending_assistant_job_v1',
        'skemi_ai_workflow_state_v1',
        'skemi_private_quiz_rooms_v1',
        'skemi_computer_mode',
        'skemi_computer_phantom_index',
        'skemi_active_computer_session_v1',
        'skemi_active_workflow_id_v1'
    ];
    baseKeys.forEach(key => migrateGlobalKeyToUserKey(key));
}

/**
 * UserDataManager (dùng chung mọi trang)
 * Lưu dữ liệu server-side theo user_id qua API của Skemi.
 * localStorage chỉ đóng vai trò làm cache tạm.
 */
export class UserDataManager {
    constructor(namespace) {
        this.namespace = namespace;
        this.cache = {};
    }

    async load() {
        try {
            const token = typeof window !== 'undefined' && typeof window.getAuthToken === 'function' ? window.getAuthToken() : '';
            const res = await fetch(`/api/user/data?namespace=${this.namespace}`, {
                headers: { 
                    'Authorization': token ? `Bearer ${token}` : ''
                }
            });
            if (res.ok) {
                const payload = await res.json();
                const data = payload?.data || [];
                this.cache = {};
                data.forEach(item => {
                    try {
                        this.cache[item.key] = JSON.parse(item.value);
                    } catch (e) {
                        this.cache[item.key] = item.value;
                    }
                });
            }
        } catch (e) {
            console.error(`[UserDataManager] Failed to load data for namespace ${this.namespace}:`, e);
            // Fallback to cache/localStorage if offline
            try {
                const legacyKey = `skemi_${this.namespace}_cache_v1`;
                const stored = localStorage.getItem(legacyKey);
                if (stored) {
                    this.cache = JSON.parse(stored);
                }
            } catch (_) {}
        }
        return this.cache;
    }

    async set(key, value) {
        this.cache[key] = value;
        try {
            const token = typeof window !== 'undefined' && typeof window.getAuthToken === 'function' ? window.getAuthToken() : '';
            await fetch('/api/user/data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : ''
                },
                body: JSON.stringify({
                    namespace: this.namespace,
                    key,
                    value: value
                })
            });
        } catch (e) {
            console.error(`[UserDataManager] Failed to set key ${key} for namespace ${this.namespace}:`, e);
        }

        // Cache locally in localStorage
        try {
            const legacyKey = `skemi_${this.namespace}_cache_v1`;
            localStorage.setItem(legacyKey, JSON.stringify(this.cache));
        } catch (_) {}
    }

    async delete(key) {
        delete this.cache[key];
        try {
            const token = typeof window !== 'undefined' && typeof window.getAuthToken === 'function' ? window.getAuthToken() : '';
            await fetch('/api/user/data', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : ''
                },
                body: JSON.stringify({
                    namespace: this.namespace,
                    key
                })
            });
        } catch (e) {
            console.error(`[UserDataManager] Failed to delete key ${key} for namespace ${this.namespace}:`, e);
        }

        try {
            const legacyKey = `skemi_${this.namespace}_cache_v1`;
            localStorage.setItem(legacyKey, JSON.stringify(this.cache));
        } catch (_) {}
    }

    get(key, defaultVal = null) {
        return this.cache[key] ?? defaultVal;
    }
}
