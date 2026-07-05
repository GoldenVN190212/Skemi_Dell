/* ============================================================
 * Skemi — Client entitlements bridge
 * ------------------------------------------------------------
 * Talks to GET /api/entitlements and exposes a small, safe API
 * the rest of the UI can use to gate features and show usage:
 *
 *   await SkemiEntitlements.ready;          // resolves once loaded
 *   SkemiEntitlements.tier                  // 'free' | 'pro' | ...
 *   SkemiEntitlements.can('deep_research')  // boolean
 *   SkemiEntitlements.usage('tokens')       // { used, limit, remaining }
 *   SkemiEntitlements.guard('comic')        // false + fires upgrade nudge
 *   SkemiEntitlements.handle402(resp,json)  // shows nudge on a 402 body
 *   SkemiEntitlements.refresh()             // re-fetch from server
 *
 * It NEVER throws on the page; on any error it degrades to the
 * free tier so the UI keeps working. Pairs with upgrade-nudge.js.
 * Include AFTER User_navbar.js / upgrade-nudge.js:
 *   <script src="./Js/entitlements.js"></script>
 * ========================================================== */
(function () {
    'use strict';
    if (window.SkemiEntitlements) return;

    var LANG = (localStorage.getItem('skemi_language') || 'vi')
        .toLowerCase().indexOf('en') === 0 ? 'en' : 'vi';

    // ---- minimal free-tier fallback (mirrors entitlements.py free tier) ----
    var FREE_FALLBACK = {
        account_id: null,
        tier: 'free',
        label: 'Free',
        price_vnd: 0,
        features: {
            search_basic: true, deep_research: false, studio_basic: true,
            studio_premium: false, studio_comic_book: false,
            prompt_agent_full: false, skemi_computer: false, beta: false, api: false
        },
        quotas: {},
        usage: {},
        all_tiers: {}
    };

    var state = { data: null, loaded: false };

    function authToken() {
        try {
            if (window.SkemiAuth && typeof window.SkemiAuth.getTokenSync === 'function') {
                return window.SkemiAuth.getTokenSync() || '';
            }
        } catch (e) { }
        return '';
    }

    function apply(data) {
        state.data = data || FREE_FALLBACK;
        state.loaded = true;
        // Keep the navbar/global tier flag in sync.
        try { window.SkemiTier = state.data.tier || 'free'; } catch (e) { }
        try {
            document.dispatchEvent(new CustomEvent('skemi:entitlements', { detail: state.data }));
        } catch (e) { }
        return state.data;
    }

    function fetchEntitlements() {
        var headers = {};
        var tok = authToken();
        if (tok) headers['Authorization'] = 'Bearer ' + tok;
        return fetch('/api/entitlements', { headers: headers, credentials: 'include' })
            .then(function (r) { return r.ok ? r.json() : FREE_FALLBACK; })
            .then(function (d) { return apply(d); })
            .catch(function () { return apply(FREE_FALLBACK); });
    }

    var ready = fetchEntitlements();

    // ---- helpers ----
    function data() { return state.data || FREE_FALLBACK; }

    // BETA SWITCH — while false (default), EVERY feature is free for EVERYONE.
    // The whole paywall is built but dormant; flip to true (AND set the server
    // env SKEMI_GATING_ENABLED=1) to activate real per-tier gating after testing.
    var GATING_ENABLED = false;

    // ---- founder (CEO) bypass — full access while testing ----
    var FOUNDER_EMAILS = ['tvo24027@gmail.com'];
    function currentEmail() {
        try { var u = (typeof loadUserData === 'function') ? loadUserData() : (window.loadUserData ? window.loadUserData() : null); if (u && u.email) return String(u.email).toLowerCase(); } catch (e) {}
        try { if (window.firebase && firebase.auth && firebase.auth().currentUser) return String(firebase.auth().currentUser.email || '').toLowerCase(); } catch (e) {}
        try { return String(localStorage.getItem('skemi_email') || '').toLowerCase(); } catch (e) {}
        return '';
    }
    function isFounder() {
        if (FOUNDER_EMAILS.indexOf(currentEmail()) >= 0) return true;
        try { if (localStorage.getItem('skemi_founder') === '1') return true; } catch (e) {}
        return false;
    }
    function effTier() { if (!GATING_ENABLED) return 'skemi'; return isFounder() ? 'skemi' : (data().tier || 'free'); }

    function can(feature) {
        if (!GATING_ENABLED || isFounder()) return true;   // beta: everything free
        var f = (data().features) || {};
        return !!f[feature];
    }

    // Squad size cap by tier: free 0 · pro 3 · advanced/skemi 8.
    function agentCap() {
        if (!GATING_ENABLED) return 8;                     // beta: full squad free
        var t = effTier();
        if (t === 'skemi' || t === 'advanced') return 8;
        if (t === 'pro') return 3;
        return 0;
    }

    function usage(kind) {
        var u = (data().usage || {})[kind];
        if (!u) return { used: 0, limit: 0, remaining: 0 };
        var rem = (u.remaining != null)
            ? u.remaining
            : (u.limit === -1 ? Infinity : Math.max(0, (u.limit || 0) - (u.used || 0)));
        return { used: u.used || 0, limit: u.limit || 0, remaining: rem, bucket: u.bucket };
    }

    function tokensExhausted() {
        var t = usage('tokens');
        return t.limit !== -1 && t.remaining <= 0;
    }

    // Fire an upgrade nudge for a gated feature; returns whether it's allowed.
    function guard(feature, opts) {
        opts = opts || {};
        if (can(feature)) return true;
        try {
            if (window.SkemiUpgrade && opts.nudge !== false) {
                window.SkemiUpgrade.feature(feature);
            }
        } catch (e) { }
        return false;
    }

    // Inspect a server response; if it's a 402 token-budget block, nudge.
    function handle402(resp, json) {
        try {
            var is402 = resp && resp.status === 402;
            var ent = json && json.entitlement;
            if (!is402 && !(ent && ent.reason === 'tokens')) return false;
            var msg = (ent && ent.message && ent.message[LANG]) || '';
            var tier = (ent && ent.suggest_tier) || 'pro';
            if (window.SkemiUpgrade) {
                if (msg) window.SkemiUpgrade.nudge({ message: msg, tier: tier });
                else window.SkemiUpgrade.limit('prompts');
            }
            return true;
        } catch (e) { return false; }
    }

    // Some responses carry a soft downgrade hint (e.g. deep_research → basic).
    function handleDowngrade(json) {
        try {
            var ent = json && json.entitlement;
            if (!ent || ent.allowed) return false;
            if (ent.reason === 'feature' && window.SkemiUpgrade) {
                var msg = (ent.message && ent.message[LANG]) || '';
                window.SkemiUpgrade.nudge({ message: msg, tier: ent.suggest_tier || 'pro' });
                return true;
            }
        } catch (e) { }
        return false;
    }

    // ---- Declarative gating: lock any [data-feature] the tier can't use ----
    // Feature → minimum tier (mirrors entitlements.py) for the upgrade prompt.
    var FEATURE_MIN = {
        deep_research: 'pro', map_3d: 'pro', studio_premium: 'pro', studio_comic_book: 'pro',
        prompt_agent_full: 'pro', quiz_create: 'pro', lab_feasibility: 'pro', legion_squad: 'pro',
        skemi_computer: 'advanced', lab_sandbox: 'advanced', remote_full: 'advanced', legion_full: 'advanced', beta: 'advanced',
        api: 'skemi'
    };
    var TIER_LABEL = { free: 'Free', pro: 'Pro', advanced: 'Advanced', skemi: 'Skemi' };
    var FEATURE_NAME = {
        deep_research: { vi: 'Nghiên cứu sâu', en: 'Deep Research' },
        map_3d: { vi: 'Bản đồ tri thức 3D', en: '3D Knowledge Map' },
        studio_premium: { vi: 'Studio cao cấp', en: 'Premium Studio' },
        studio_comic_book: { vi: 'Comic & Sách AI', en: 'AI Comic & Book' },
        prompt_agent_full: { vi: 'Prompt Agent toàn lực', en: 'Full Prompt Agent' },
        quiz_create: { vi: 'Tạo Quiz bằng AI', en: 'AI Quiz creation' },
        lab_feasibility: { vi: 'Phân tích khả thi', en: 'Feasibility Lab' },
        lab_sandbox: { vi: 'Chạy code thật', en: 'Code sandbox' },
        legion_squad: { vi: 'Đội hình Legion', en: 'Legion squad' },
        legion_full: { vi: 'Legion 8 agent', en: 'Full 8-agent Legion' },
        skemi_computer: { vi: 'Skemi Control', en: 'Skemi Control' },
        remote_full: { vi: 'Điều khiển từ xa', en: 'Full Remote' },
        api: { vi: 'API Skemi', en: 'Skemi API' }
    };
    function featureName(f) { var m = FEATURE_NAME[f]; return m ? (LANG === 'en' ? m.en : m.vi) : f; }
    function minTier(f) { return FEATURE_MIN[f] || 'free'; }

    function ensureStyles() {
        if (document.getElementById('skemi-ent-style')) return;
        var s = document.createElement('style'); s.id = 'skemi-ent-style';
        s.textContent = '.skemi-locked{position:relative}.skemi-lock-badge{position:absolute;top:6px;right:6px;z-index:5;width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:11px;background:var(--brand-gradient,linear-gradient(135deg,#6366f1,#a855f7));color:#fff;box-shadow:0 2px 8px -2px rgba(0,0,0,.4);pointer-events:none}'
            + '.skemi-ent-ov{position:fixed;inset:0;z-index:16000;display:flex;align-items:center;justify-content:center;background:rgba(8,10,20,.55);backdrop-filter:blur(6px)}'
            + '.skemi-ent-card{width:min(430px,92vw);background:var(--bg-secondary,#fff);color:var(--text-primary,#0f172a);border:1px solid var(--border-light,rgba(0,0,0,.1));border-radius:var(--radius-lg,20px);padding:26px 24px;box-shadow:var(--shadow-xl,0 28px 70px rgba(0,0,0,.3));text-align:center;animation:skemiEntPop .28s cubic-bezier(.34,1.56,.64,1)}'
            + '@keyframes skemiEntPop{from{opacity:0;transform:scale(.94)}to{opacity:1;transform:none}}'
            + '.skemi-ent-tier{display:inline-block;margin:4px 0 6px;padding:4px 14px;border-radius:999px;font-weight:700;font-size:.82rem;background:var(--brand-gradient,linear-gradient(135deg,#6366f1,#a855f7));color:#fff}'
            + '.skemi-ent-card h3{font-family:var(--font-heading,inherit);margin:6px 0;font-size:1.25rem;font-weight:800}'
            + '.skemi-ent-card p{color:var(--text-secondary,#334155);font-size:.92rem;line-height:1.55;margin:0 0 18px}'
            + '.skemi-ent-act{display:flex;gap:10px;justify-content:center}'
            + '.skemi-ent-b{border:none;cursor:pointer;font-weight:700;border-radius:12px;padding:11px 20px;font-size:.9rem}'
            + '.skemi-ent-up{background:var(--brand-gradient,linear-gradient(135deg,#6366f1,#a855f7));color:#fff}'
            + '.skemi-ent-later{background:var(--bg-tertiary,#eef2ff);color:var(--text-secondary,#334155)}';
        document.head.appendChild(s);
    }
    function escv(x) { return String(x == null ? '' : x).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }

    // Show an upgrade prompt. Prefer the shared SkemiUpgrade nudge; fall back to
    // a built-in modal so gating still works on pages that don't load it.
    function showUpgrade(feature) {
        try { if (window.SkemiUpgrade && typeof window.SkemiUpgrade.feature === 'function') { window.SkemiUpgrade.feature(feature); return; } } catch (e) {}
        ensureStyles();
        var vi = LANG !== 'en'; var need = TIER_LABEL[minTier(feature)] || 'Pro';
        var old = document.querySelector('.skemi-ent-ov'); if (old) old.remove();
        var ov = document.createElement('div'); ov.className = 'skemi-ent-ov';
        ov.innerHTML = '<div class="skemi-ent-card"><div style="font-size:32px">🔒</div><div class="skemi-ent-tier">' + (vi ? 'Cần gói ' : 'Requires ') + need + '</div><h3>' + escv(featureName(feature)) + '</h3><p>' + (vi ? ('Tính năng này mở khoá từ gói <b>' + need + '</b>. Nâng cấp để dùng đầy đủ — huỷ bất cứ lúc nào.') : ('This feature unlocks from the <b>' + need + '</b> plan.')) + '</p><div class="skemi-ent-act"><button class="skemi-ent-b skemi-ent-later">' + (vi ? 'Để sau' : 'Later') + '</button><button class="skemi-ent-b skemi-ent-up">' + (vi ? 'Nâng cấp' : 'Upgrade') + '</button></div></div>';
        document.body.appendChild(ov);
        ov.addEventListener('click', function (e) { if (e.target === ov) ov.remove(); });
        ov.querySelector('.skemi-ent-later').addEventListener('click', function () { ov.remove(); });
        ov.querySelector('.skemi-ent-up').addEventListener('click', function () { window.location.href = 'Subscription.html?want=' + encodeURIComponent(minTier(feature)); });
    }
    function requireFeature(feature) { if (can(feature)) return true; showUpgrade(feature); return false; }

    // One delegated capture-phase listener on the document intercepts clicks on
    // any locked [data-feature] BEFORE the section's own handlers run (which may
    // stopPropagation on their own). More robust than per-button listeners.
    var _gateDelegateBound = false;
    function bindGateDelegate() {
        if (_gateDelegateBound) return; _gateDelegateBound = true;
        document.addEventListener('click', function (e) {
            var host = e.target && e.target.closest ? e.target.closest('[data-feature]') : null;
            if (!host) return;
            var feat = host.getAttribute('data-feature');
            if (can(feat)) return;
            e.preventDefault(); e.stopImmediatePropagation();
            showUpgrade(feat);
        }, true);
    }
    function applyGates(root) {
        root = root || document; ensureStyles(); bindGateDelegate();
        var els = root.querySelectorAll('[data-feature]');
        for (var i = 0; i < els.length; i++) {
            var el = els[i], feat = el.getAttribute('data-feature');
            if (!can(feat)) {
                if (!el.classList.contains('skemi-locked')) {
                    el.classList.add('skemi-locked');
                    if (el.getAttribute('data-feature-badge') !== 'off') {
                        var b = document.createElement('span'); b.className = 'skemi-lock-badge'; b.textContent = '🔒'; el.appendChild(b);
                    }
                }
            } else {
                el.classList.remove('skemi-locked');
                var badge = el.querySelector(':scope > .skemi-lock-badge'); if (badge) badge.remove();
            }
        }
    }
    // Re-lock whenever entitlements load/change.
    document.addEventListener('skemi:entitlements', function () { try { applyGates(); } catch (e) {} });
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', function () { ready.then(function () { applyGates(); }); }); }
    else { ready.then(function () { applyGates(); }); }

    window.SkemiEntitlements = {
        ready: ready,
        get data() { return data(); },
        get tier() { return effTier(); },
        get label() { return isFounder() ? 'Skemi (Founder)' : (data().label || 'Free'); },
        isFounder: isFounder,
        agentCap: agentCap,
        can: can,
        usage: usage,
        tokensExhausted: tokensExhausted,
        guard: guard,
        requireFeature: requireFeature,
        showUpgrade: showUpgrade,
        applyGates: applyGates,
        minTier: minTier,
        featureName: featureName,
        handle402: handle402,
        handleDowngrade: handleDowngrade,
        refresh: fetchEntitlements
    };
})();
