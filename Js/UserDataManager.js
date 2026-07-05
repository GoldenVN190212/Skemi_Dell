/**
 * UserDataManager v2.0
 * Lưu dữ liệu server-side theo user_id.
 * Fallback localStorage khi offline/chưa đăng nhập.
 */
class UserDataManager {
    constructor(namespace) {
        this.namespace = namespace;
        this.cache = {};
        this._loaded = false;
    }

    async load() {
        if (this._loaded) return this.cache;
        // Resolve token synchronously. The new Auth.js made getToken() async (returns
// a Promise) — a Promise is truthy, so calling `if (!token)` after that would
// always proceed to the API call and send "Bearer [object Promise]" → 401.
// `getTokenSync` returns the cached Firebase ID token (or null) without a round-trip.
let token = null;
if (typeof window.SkemiAuth?.getTokenSync === 'function') {
    token = window.SkemiAuth.getTokenSync();
} else {
    const maybe = window.SkemiAuth?.getToken?.();
    token = typeof maybe === 'string' ? maybe : null;
}

        if (!token) {
            const local = localStorage.getItem(`udm_${this.namespace}`);
            if (local) try { this.cache = JSON.parse(local); } catch {}
            this._loaded = true;
            return this.cache;
        }

        try {
            const res = await fetch(
                `/api/user/data?namespace=${encodeURIComponent(this.namespace)}`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            // 401 = no valid bearer token (we now use Firebase ID tokens; the
            // server's JWT-only middleware doesn't accept those yet). DON'T
            // auto-logout — that creates a redirect loop:
            //   page → UDM.load → 401 → logout → /Login.html → UDM.load → 401 → …
            // Just return whatever's cached locally and let feature code carry on.
            if (res.status === 401) {
                const local = localStorage.getItem(`udm_${this.namespace}`);
                if (local) { try { this.cache = JSON.parse(local); } catch {} }
                this._loaded = true;
                return this.cache;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            (json.data || []).forEach(item => { this.cache[item.key] = item.value; });
            localStorage.setItem(`udm_${this.namespace}`, JSON.stringify(this.cache));
        } catch (e) {
            console.error(`[UDM:${this.namespace}]`, e);
            const local = localStorage.getItem(`udm_${this.namespace}`);
            if (local) try { this.cache = JSON.parse(local); } catch {}
        }

        this._loaded = true;
        return this.cache;
    }

    async set(key, value) {
        this.cache[key] = value;
        localStorage.setItem(`udm_${this.namespace}`, JSON.stringify(this.cache));
        // Resolve token synchronously. The new Auth.js made getToken() async (returns
// a Promise) — a Promise is truthy, so calling `if (!token)` after that would
// always proceed to the API call and send "Bearer [object Promise]" → 401.
// `getTokenSync` returns the cached Firebase ID token (or null) without a round-trip.
let token = null;
if (typeof window.SkemiAuth?.getTokenSync === 'function') {
    token = window.SkemiAuth.getTokenSync();
} else {
    const maybe = window.SkemiAuth?.getToken?.();
    token = typeof maybe === 'string' ? maybe : null;
}
        if (!token) return;
        try {
            await fetch('/api/user/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json',
                           'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ namespace: this.namespace, key, value })
            });
        } catch (e) { console.error(`[UDM:${this.namespace}] set:`, e); }
    }

    get(key, def = null) { return key in this.cache ? this.cache[key] : def; }

    async delete(key) {
        delete this.cache[key];
        localStorage.setItem(`udm_${this.namespace}`, JSON.stringify(this.cache));
        // Resolve token synchronously. The new Auth.js made getToken() async (returns
// a Promise) — a Promise is truthy, so calling `if (!token)` after that would
// always proceed to the API call and send "Bearer [object Promise]" → 401.
// `getTokenSync` returns the cached Firebase ID token (or null) without a round-trip.
let token = null;
if (typeof window.SkemiAuth?.getTokenSync === 'function') {
    token = window.SkemiAuth.getTokenSync();
} else {
    const maybe = window.SkemiAuth?.getToken?.();
    token = typeof maybe === 'string' ? maybe : null;
}
        if (!token) return;
        await fetch('/api/user/data/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json',
                       'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ namespace: this.namespace, key })
        });
    }

    invalidate() { this._loaded = false; this.cache = {}; }
}
window.UserDataManager = UserDataManager;