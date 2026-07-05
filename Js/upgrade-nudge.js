/* ============================================================
 * Skemi — Non-intrusive upgrade nudge
 * ------------------------------------------------------------
 * A tiny, professional, dismissible card that slides in at the
 * bottom-right when a user hits a quota or lacks a feature.
 * It NEVER blocks the UI. One call shows it:
 *
 *   SkemiUpgrade.feature('deep_research');      // catalog-driven
 *   SkemiUpgrade.limit('prompts');              // quota reached
 *   SkemiUpgrade.nudge({ title, message, tier });// custom
 *
 * No real payment is processed — the CTA simply routes the user
 * to Subscription.html where checkout will live.
 * Include on any page:  <script src="./Js/upgrade-nudge.js"></script>
 * ========================================================== */
(function () {
    'use strict';
    if (window.SkemiUpgrade) return;

    var LANG = (localStorage.getItem('skemi_language') || 'vi').toLowerCase().indexOf('en') === 0 ? 'en' : 'vi';
    var vi = LANG === 'vi';

    // ---- per-tier display meta ----
    var TIER_LABEL = {
        pro: 'Pro',
        advanced: 'Advanced',
        skemi: 'Skemi'
    };

    // ---- feature catalog: key -> { tier, vi, en } ----
    // Ordered conceptually by token cost; heavier features need higher tiers.
    var FEATURES = {
        deep_research: {
            tier: 'pro',
            vi: 'Nghiên cứu sâu trực quan có ở gói Pro.',
            en: 'Vivid Deep Research is available on Pro.'
        },
        comic: { tier: 'pro', vi: 'Tạo Comic có ở gói Pro.', en: 'Comic generation is on Pro.' },
        book: { tier: 'pro', vi: 'Tạo Sách có ở gói Pro.', en: 'Book generation is on Pro.' },
        podcast: { tier: 'pro', vi: 'Tạo Podcast có ở gói Pro.', en: 'Podcast generation is on Pro.' },
        slides: { tier: 'pro', vi: 'Xuất Slide có ở gói Pro.', en: 'Slide export is on Pro.' },
        infographic: { tier: 'pro', vi: 'Tạo Infographic có ở gói Pro.', en: 'Infographic generation is on Pro.' },
        prompt_agent: {
            tier: 'pro',
            vi: 'Prompt Agent toàn lực có ở gói Pro.',
            en: 'Full-power Prompt Agent is on Pro.'
        },
        skemi_computer: {
            tier: 'advanced',
            vi: 'Skemi Control (màn hình ảo) có ở gói Advanced.',
            en: 'Skemi Control (virtual desktop) is on Advanced.'
        },
        beta: { tier: 'advanced', vi: 'Truy cập Beta sớm có ở gói Advanced.', en: 'Early Beta access is on Advanced.' },
        api: { tier: 'skemi', vi: 'Truy cập API có ở gói Skemi.', en: 'API access is on the Skemi plan.' }
    };

    // ---- quota catalog: key -> { tier, vi, en } ----
    var LIMITS = {
        prompts: {
            tier: 'pro',
            vi: 'Bạn đã dùng hết lượt Prompt. Nâng cấp Pro để có 100 lượt mỗi 6 giờ.',
            en: 'You\'ve used all your Prompts. Upgrade to Pro for 100 every 6 hours.'
        },
        uploads: {
            tier: 'pro',
            vi: 'Bạn đã hết lượt tải tài liệu. Nâng cấp Pro để tải nhiều hơn.',
            en: 'You\'re out of uploads. Upgrade to Pro to upload more.'
        },
        quiz_rooms: {
            tier: 'pro',
            vi: 'Bạn đã đạt giới hạn phòng Quiz. Nâng cấp Pro để tạo thêm.',
            en: 'You\'ve hit the Quiz room limit. Upgrade to Pro for more.'
        },
        deep_research: {
            tier: 'advanced',
            vi: 'Bạn đã hết lượt Nghiên cứu sâu hôm nay. Nâng cấp Advanced để không giới hạn.',
            en: 'You\'re out of Deep Research runs today. Upgrade to Advanced for unlimited.'
        }
    };

    var STR = {
        title: vi ? 'Nâng cấp Skemi' : 'Upgrade Skemi',
        upgrade: vi ? 'Nâng cấp' : 'Upgrade',
        later: vi ? 'Để sau' : 'Later',
        dismiss: vi ? 'Đóng' : 'Dismiss'
    };

    // ---- inject styles once ----
    function injectStyles() {
        if (document.getElementById('skemi-upgrade-styles')) return;
        var css = '' +
            '.skemi-nudge-wrap{position:fixed;right:20px;bottom:20px;z-index:13500;display:flex;flex-direction:column;gap:10px;max-width:340px;pointer-events:none;}' +
            '.skemi-nudge{pointer-events:auto;background:var(--bg-secondary,#fff);color:var(--text-primary,#111);border:1px solid var(--border-light,#e5e7eb);border-left:4px solid var(--brand-primary,#4f46e5);border-radius:14px;padding:14px 14px 14px 16px;box-shadow:0 14px 40px rgba(0,0,0,.22);display:flex;gap:12px;align-items:flex-start;transform:translateY(14px);opacity:0;transition:transform .28s cubic-bezier(.2,.7,.3,1),opacity .28s ease;}' +
            '.skemi-nudge.in{transform:translateY(0);opacity:1;}' +
            '.skemi-nudge .sn-ico{flex:none;font-size:1.15rem;line-height:1.3;}' +
            '.skemi-nudge .sn-body{flex:1;min-width:0;}' +
            '.skemi-nudge .sn-title{font-weight:800;font-size:.84rem;letter-spacing:.01em;margin:0 0 3px;color:var(--text-primary,#111);display:flex;align-items:center;gap:6px;}' +
            '.skemi-nudge .sn-tier{font-size:.66rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:#fff;background:linear-gradient(120deg,var(--brand-primary,#4f46e5),var(--brand-secondary,#7c3aed));padding:2px 8px;border-radius:999px;}' +
            '.skemi-nudge .sn-msg{font-size:.82rem;line-height:1.45;color:var(--text-muted,#6b7280);margin:0 0 10px;}' +
            '.skemi-nudge .sn-actions{display:flex;gap:8px;align-items:center;}' +
            '.skemi-nudge .sn-up{border:none;cursor:pointer;font-weight:700;font-size:.8rem;padding:7px 14px;border-radius:999px;color:#fff;background:linear-gradient(120deg,var(--brand-primary,#4f46e5),var(--brand-secondary,#7c3aed));transition:filter .2s ease,transform .15s ease;}' +
            '.skemi-nudge .sn-up:hover{filter:brightness(1.08);transform:translateY(-1px);}' +
            '.skemi-nudge .sn-later{border:none;background:transparent;cursor:pointer;font-weight:600;font-size:.8rem;color:var(--text-muted,#6b7280);padding:7px 6px;}' +
            '.skemi-nudge .sn-later:hover{color:var(--text-primary,#111);}' +
            '.skemi-nudge .sn-x{flex:none;border:none;background:transparent;cursor:pointer;color:var(--text-muted,#9ca3af);font-size:1rem;line-height:1;padding:0 2px;margin-left:2px;}' +
            '.skemi-nudge .sn-x:hover{color:var(--text-primary,#111);}' +
            '@media (max-width:480px){.skemi-nudge-wrap{left:14px;right:14px;max-width:none;bottom:14px;}}';
        var st = document.createElement('style');
        st.id = 'skemi-upgrade-styles';
        st.textContent = css;
        document.head.appendChild(st);
    }

    function wrap() {
        var w = document.getElementById('skemi-nudge-wrap');
        if (!w) {
            w = document.createElement('div');
            w.id = 'skemi-nudge-wrap';
            w.className = 'skemi-nudge-wrap';
            (document.body || document.documentElement).appendChild(w);
        }
        return w;
    }

    // ---- de-dupe: same key won't re-fire within 45s ----
    var lastShown = {};
    function debounced(key) {
        var now = Date.now();
        if (lastShown[key] && now - lastShown[key] < 45000) return true;
        lastShown[key] = now;
        return false;
    }

    var openCount = 0; // never stack more than 2 at once

    function render(opts) {
        injectStyles();
        var tier = (opts.tier && TIER_LABEL[opts.tier]) ? opts.tier : 'pro';
        var w = wrap();
        if (openCount >= 2) { var first = w.querySelector('.skemi-nudge'); if (first) closeCard(first); }

        var card = document.createElement('div');
        card.className = 'skemi-nudge';
        card.innerHTML =
            '<div class="sn-ico">⚡</div>' +
            '<div class="sn-body">' +
            '<div class="sn-title">' + esc(opts.title || STR.title) + '<span class="sn-tier">' + esc(TIER_LABEL[tier]) + '</span></div>' +
            '<p class="sn-msg">' + esc(opts.message || '') + '</p>' +
            '<div class="sn-actions">' +
            '<button class="sn-up">' + esc(STR.upgrade) + '</button>' +
            '<button class="sn-later">' + esc(STR.later) + '</button>' +
            '</div></div>' +
            '<button class="sn-x" aria-label="' + esc(STR.dismiss) + '">&times;</button>';

        w.appendChild(card);
        openCount++;
        requestAnimationFrame(function () { card.classList.add('in'); });

        var autoTimer = setTimeout(function () { closeCard(card); }, 11000);

        function go() {
            clearTimeout(autoTimer);
            var url = 'Subscription.html' + (opts.tier ? ('#' + opts.tier) : '');
            window.location.href = url;
        }
        card.querySelector('.sn-up').onclick = go;
        card.querySelector('.sn-later').onclick = function () { clearTimeout(autoTimer); closeCard(card); };
        card.querySelector('.sn-x').onclick = function () { clearTimeout(autoTimer); closeCard(card); };
        return card;
    }

    function closeCard(card) {
        if (!card || card.__closing) return;
        card.__closing = true;
        card.classList.remove('in');
        openCount = Math.max(0, openCount - 1);
        setTimeout(function () { if (card.parentNode) card.parentNode.removeChild(card); }, 300);
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ---- public API ----
    window.SkemiUpgrade = {
        /** Show a custom nudge: { title?, message, tier? } */
        nudge: function (opts) {
            opts = opts || {};
            var key = 'custom:' + (opts.message || '');
            if (debounced(key)) return null;
            return render(opts);
        },
        /** Nudge because a gated FEATURE was attempted: SkemiUpgrade.feature('comic') */
        feature: function (featureKey, override) {
            var f = FEATURES[featureKey];
            if (!f) return this.nudge(override || { message: vi ? 'Tính năng này cần gói cao hơn.' : 'This feature needs a higher plan.' });
            if (debounced('feature:' + featureKey)) return null;
            return render(Object.assign({ message: f[LANG] || f.vi, tier: f.tier }, override || {}));
        },
        /** Nudge because a quota/LIMIT was reached: SkemiUpgrade.limit('prompts') */
        limit: function (limitKey, override) {
            var l = LIMITS[limitKey];
            if (!l) return this.nudge(override || { message: vi ? 'Bạn đã đạt giới hạn của gói hiện tại.' : 'You\'ve reached your current plan limit.' });
            if (debounced('limit:' + limitKey)) return null;
            return render(Object.assign({ message: l[LANG] || l.vi, tier: l.tier }, override || {}));
        },
        /** Programmatic close of all open nudges. */
        clear: function () {
            var w = document.getElementById('skemi-nudge-wrap');
            if (w) Array.prototype.forEach.call(w.querySelectorAll('.skemi-nudge'), closeCard);
        }
    };
})();
