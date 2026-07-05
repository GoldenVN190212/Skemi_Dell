/* ========================================================================
   SKEMI motion.js  —  drives the Motion.css polish layer.
   ------------------------------------------------------------------------
   • Adds .js to <html> so [data-reveal] hidden states only apply when JS lives.
   • Plays a one-time page entrance (.skemi-anim-in on <body>).
   • Tags repeating content blocks for a staggered cascade (--i index).
   • Material ripple on .btn / .btn-primary / .nav-shortcut clicks.
   • IntersectionObserver scroll-reveal for [data-reveal] elements.
   • Fully respects reduced-motion (OS setting OR body.reduce-motion): in that
     case it still reveals everything instantly, just without the motion.
   Zero dependencies. Never throws — every block is guarded.
======================================================================== */
(function () {
    'use strict';

    // Mark that JS is alive (Motion.css uses .js to gate hidden reveal states).
    try { document.documentElement.classList.add('js'); } catch (_) {}

    var reduce = false;
    try {
        reduce = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) ||
                 (document.body && document.body.classList.contains('reduce-motion'));
    } catch (_) {}

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn, { once: true });
        } else { fn(); }
    }

    // ---- 1. Page entrance + stagger tagging ----
    function playEntrance() {
        try {
            // Tag repeating blocks so they cascade in via --i.
            if (!reduce) {
                var sels = [
                    '.stats-card', '.settings-card', '.plan-card', '.studio-card',
                    '.feature-card', '.result-card', '.source-card', '.quiz-card',
                    '.glass-panel'
                ];
                document.querySelectorAll(sels.join(',')).forEach(function (el, i) {
                    // cap the stagger so long lists don't wait forever
                    el.setAttribute('data-skemi-stagger', '');
                    el.style.setProperty('--i', String(Math.min(i, 12)));
                });
            }
            document.body.classList.add('skemi-anim-in');
        } catch (_) {}
    }

    // ---- 2. Material ripple ----
    function attachRipple() {
        if (reduce) return;
        document.addEventListener('click', function (e) {
            var host = e.target && e.target.closest &&
                e.target.closest('.btn, .btn-primary, .btn-secondary, .btn-outline, .nav-shortcut');
            if (!host || host.disabled) return;
            try {
                var rect = host.getBoundingClientRect();
                var size = Math.max(rect.width, rect.height);
                var span = document.createElement('span');
                span.className = 'skemi-ripple';
                span.style.width = span.style.height = size + 'px';
                span.style.left = (e.clientX - rect.left - size / 2) + 'px';
                span.style.top = (e.clientY - rect.top - size / 2) + 'px';
                host.appendChild(span);
                span.addEventListener('animationend', function () {
                    if (span.parentNode) span.parentNode.removeChild(span);
                }, { once: true });
                // hard cleanup safety
                setTimeout(function () { if (span.parentNode) span.parentNode.removeChild(span); }, 800);
            } catch (_) {}
        }, { passive: true });
    }

    // ---- 3. Scroll reveal ----
    function attachReveal() {
        var nodes = document.querySelectorAll('[data-reveal]');
        if (!nodes.length) return;
        if (reduce || !('IntersectionObserver' in window)) {
            nodes.forEach(function (n) { n.classList.add('is-in'); });
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (ent) {
                if (ent.isIntersecting) {
                    ent.target.classList.add('is-in');
                    io.unobserve(ent.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
        nodes.forEach(function (n) { io.observe(n); });

        // Safety net: if anything is still hidden after 1.8s, reveal it.
        setTimeout(function () {
            nodes.forEach(function (n) { n.classList.add('is-in'); });
        }, 1800);
    }

    onReady(function () {
        playEntrance();
        attachRipple();
        attachReveal();
    });
})();
