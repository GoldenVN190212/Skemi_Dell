/**
 * Preferences.js — Đồng bộ theme và language mọi trang, mọi tab
 * Include sau Auth.js và UserDataManager.js
 */

/* ───────────────────────────────────────────────────────────────────────────
   EARLY THEME / COLOR SYNC  — runs the moment this script loads in <head>,
   BEFORE first paint. Reads the user's last theme + custom colors from the
   localStorage cache and applies them to <html> (and to <body> the instant it
   exists) so every page shows the chosen look immediately, instead of flashing
   its hardcoded <body class="..."> default and only correcting after the async
   server load. SkemiPrefs.init() still runs later to reconcile with the
   authoritative server value. Never throws — guarded end to end.
─────────────────────────────────────────────────────────────────────────── */
(function () {
    'use strict';
    try {
        var VALID = { light: 1, dark: 1, galaxy: 1 };
        var root = document.documentElement;

        var theme = '';
        try { theme = String(localStorage.getItem('skemi-theme') || localStorage.getItem('chat-theme') || '').replace(/^"|"$/g, '').trim().toLowerCase(); } catch (e) {}

        function readColor(k) {
            try {
                var v = localStorage.getItem(k);
                if (v == null) return null;
                if (v.charAt(0) === '"') { try { return JSON.parse(v); } catch (e) { return v; } }
                return v;
            } catch (e) { return null; }
        }

        if (VALID[theme]) root.setAttribute('data-theme', theme);
        var bg = readColor('skemi_bg_color');
        if (bg) { root.style.setProperty('--bg', bg); root.style.setProperty('--bg-primary', bg); }
        var accent = readColor('skemi_accent_color');
        if (accent) { root.style.setProperty('--accent', accent); root.style.setProperty('--brand-primary', accent); }

        if (VALID[theme]) {
            var applyBody = function () {
                var b = document.body;
                if (!b) return false;
                b.classList.remove('light-mode', 'dark-mode', 'galaxy-mode');
                b.classList.add(theme + '-mode');
                if (theme === 'galaxy') b.classList.add('dark-mode');
                return true;
            };
            if (!applyBody()) {
                var obs = new MutationObserver(function () { if (applyBody()) { try { obs.disconnect(); } catch (e) {} } });
                try { obs.observe(root, { childList: true }); } catch (e) {}
                document.addEventListener('DOMContentLoaded', function () { applyBody(); try { obs.disconnect(); } catch (e) {} }, { once: true });
            }
        }
    } catch (e) { /* never block page load */ }
})();

if (typeof SkemiPrefs === 'undefined' || window.SkemiPrefs === null) {
const SkemiPrefs = {
    _udm: null,

    async init() {
        this._udm = new UserDataManager('settings');
        await this._udm.load();
        this._apply('language', this._udm.get('language','vi'));
        // Fall back to the user's last cached theme (not a hard 'dark') so a
        // missing/empty server value never clobbers what they actually chose.
        let _cachedTheme = '';
        try { _cachedTheme = String(localStorage.getItem('skemi-theme') || '').replace(/^"|"$/g, '').trim().toLowerCase(); } catch (e) {}
        this._apply('theme',    this._udm.get('theme', _cachedTheme || 'dark'));
        const bg = this._udm.get('bg_color', null);
        if (bg) document.documentElement.style.setProperty('--bg', bg);

        window.addEventListener('storage', e => {
            if (e.key !== 'skemi_pref_change') return;
            try {
                const {key, value} = JSON.parse(e.newValue);
                this._apply(key, value);
            } catch {}
        });
    },

    async set(key, value) {
        if (!this._udm) await this.init();
        await this._udm.set(key, value);
        this._apply(key, value);
        localStorage.setItem('skemi_pref_change',
            JSON.stringify({key, value, t: Date.now()}));
    },

    get(key, def=null) {
        return this._udm?.get(key, def) ?? def;
    },

    _apply(key, value) {
        if (key === 'language') {
            window.applyLanguage?.(value);
        } else if (key === 'theme') {
            // Sync BOTH theme conventions:
            //   1. data-theme on <html> — used by Chat.css, Computer.css, design-tokens.css :root[data-theme=...]
            //   2. body.{theme}-mode class — used by Home.css, Studio2.css, Global.css body.dark-mode
            // Different page CSS files were authored at different times; some target
            // one convention, some the other. Setting both keeps every page in sync.
            document.documentElement.setAttribute('data-theme', value);
            const body = document.body;
            if (body) {
                body.classList.remove('light-mode', 'dark-mode', 'galaxy-mode');
                body.classList.add(value + '-mode');
                if (value === 'galaxy') body.classList.add('dark-mode');
            }
            // Cache user choice for early-load scripts that read it before SkemiPrefs.init().
            // `chat-theme` is consumed by the skemma_chat_assets bundle on /Chat.html
            // (SharedSettings.getCurrentTheme reads skemi-theme || chat-theme || 'light'),
            // so we mirror the value to both keys to keep Chat.html aligned with the rest.
            try {
                localStorage.setItem('skemi-theme', value);
                localStorage.setItem('chat-theme', value);
            } catch (e) { /* ignore quota */ }
            window.applyTheme?.(value);
            // After theme change, re-apply any custom bg/accent stored in prefs
            this._restoreCustomColors();
        } else if (key === 'bg_color') {
            if (value) {
                // Set BOTH --bg (legacy alias) and --bg-primary (design-tokens)
                document.documentElement.style.setProperty('--bg', value);
                document.documentElement.style.setProperty('--bg-primary', value);
                try { localStorage.setItem('skemi_bg_color', JSON.stringify(value)); } catch (e) { /* ignore */ }
                this._applyAutoContrast();
            }
        } else if (key === 'accent_color') {
            if (value) {
                document.documentElement.style.setProperty('--accent', value);
                document.documentElement.style.setProperty('--brand-primary', value);
                try { localStorage.setItem('skemi_accent_color', JSON.stringify(value)); } catch (e) { /* ignore */ }
                this._applyAutoContrast();
            }
        } else if (key === 'compact_mode') {
            // Layout density — apply live on every page that imports SkemiPrefs.
            document.body && document.body.classList.toggle('compact-mode', !!value);
        } else if (key === 'animations_enabled') {
            document.body && document.body.classList.toggle('reduce-motion', value === false);
        }
    },

    /** Re-apply custom bg/accent after a theme switch so the user's chosen
     *  color overrides the theme default. */
    _restoreCustomColors() {
        if (!this._udm) return;
        const bg = this._udm.get('bg_color', null);
        if (bg) {
            document.documentElement.style.setProperty('--bg', bg);
            document.documentElement.style.setProperty('--bg-primary', bg);
        }
        const accent = this._udm.get('accent_color', null);
        if (accent) {
            document.documentElement.style.setProperty('--accent', accent);
            document.documentElement.style.setProperty('--brand-primary', accent);
        }
        this._applyAutoContrast();
    },

    // ─────────────────────────────────────────────────────────────────────────
    //  AUTO-CONTRAST ENGINE (WCAG)
    //  When the user picks a custom --bg or --accent, the theme's hand-tuned
    //  text tokens may no longer be readable against it. We compute the WCAG
    //  relative luminance of the chosen color and flip text/button-text to the
    //  variant (near-black or near-white) that yields the higher contrast ratio.
    //  Only kicks in when a CUSTOM color exists — default themes stay untouched.
    // ─────────────────────────────────────────────────────────────────────────

    /** Parse "#rgb" | "#rrggbb" | "rgb()/rgba()" | "hsl()/hsla()" → {r,g,b} 0-255. */
    _parseColor(color) {
        if (!color) return null;
        color = String(color).trim().toLowerCase();
        let m = color.match(/^#([0-9a-f]{3})$/);
        if (m) {
            const h = m[1];
            return {
                r: parseInt(h[0] + h[0], 16),
                g: parseInt(h[1] + h[1], 16),
                b: parseInt(h[2] + h[2], 16),
            };
        }
        m = color.match(/^#([0-9a-f]{6})$/);
        if (m) {
            const h = m[1];
            return {
                r: parseInt(h.slice(0, 2), 16),
                g: parseInt(h.slice(2, 4), 16),
                b: parseInt(h.slice(4, 6), 16),
            };
        }
        m = color.match(/^rgba?\(([^)]+)\)$/);
        if (m) {
            const p = m[1].split(',').map(s => parseFloat(s));
            if (p.length >= 3) return { r: p[0], g: p[1], b: p[2] };
        }
        m = color.match(/^hsla?\(([^)]+)\)$/);
        if (m) {
            const p = m[1].split(',').map(s => s.trim());
            const h = parseFloat(p[0]);
            const s = parseFloat(p[1]) / 100;
            const l = parseFloat(p[2]) / 100;
            return this._hslToRgb(h, s, l);
        }
        return null;
    },

    _hslToRgb(h, s, l) {
        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
        const mm = l - c / 2;
        let r = 0, g = 0, b = 0;
        if (h < 60)       { r = c; g = x; b = 0; }
        else if (h < 120) { r = x; g = c; b = 0; }
        else if (h < 180) { r = 0; g = c; b = x; }
        else if (h < 240) { r = 0; g = x; b = c; }
        else if (h < 300) { r = x; g = 0; b = c; }
        else              { r = c; g = 0; b = x; }
        return {
            r: Math.round((r + mm) * 255),
            g: Math.round((g + mm) * 255),
            b: Math.round((b + mm) * 255),
        };
    },

    /** WCAG relative luminance for an {r,g,b} (0-255) color. */
    _luminance({ r, g, b }) {
        const lin = [r, g, b].map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
    },

    _contrastRatio(lumA, lumB) {
        const hi = Math.max(lumA, lumB);
        const lo = Math.min(lumA, lumB);
        return (hi + 0.05) / (lo + 0.05);
    },

    /** Blend two colors; `t` is the weight of `c2` (0..1). Returns 'rgb(r,g,b)'. */
    _mix(c1, c2, t) {
        const a = this._parseColor(c1), b = this._parseColor(c2);
        if (!a || !b) return null;
        const m = (x, y) => Math.round(x + (y - x) * t);
        return `rgb(${m(a.r, b.r)}, ${m(a.g, b.g)}, ${m(a.b, b.b)})`;
    },
    _rgba(c, alpha) {
        const x = this._parseColor(c);
        return x ? `rgba(${x.r}, ${x.g}, ${x.b}, ${alpha})` : null;
    },

    /** Pick near-black or near-white text for the best contrast on `bgColor`. */
    _bestTextColor(bgColor) {
        const rgb = this._parseColor(bgColor);
        if (!rgb) return null;
        const bgLum = this._luminance(rgb);
        const whiteLum = 1.0;   // luminance of #fff
        const blackLum = 0.0;   // luminance of #000
        const cWhite = this._contrastRatio(whiteLum, bgLum);
        const cBlack = this._contrastRatio(bgLum, blackLum);
        // Bias slightly toward white for darker bg, black for lighter bg.
        return cWhite >= cBlack ? '#f8fafc' : '#0f172a';
    },

    /** Read a custom color from UDM first, then localStorage fallback. */
    _readCustom(udmKey, lsKey) {
        let v = this._udm ? this._udm.get(udmKey, null) : null;
        if (v) return v;
        try {
            const raw = localStorage.getItem(lsKey);
            if (raw == null) return null;
            if (raw.startsWith('"')) { try { return JSON.parse(raw); } catch { return raw; } }
            return raw;
        } catch { return null; }
    },

    /** Recompute readable text/button colors against the active custom palette. */
    // Tokens we may set; cleared on both root and body when a custom bg is removed.
    _CUSTOM_BG_TOKENS: ['--bg','--bg-primary','--text-primary','--text-secondary','--text-muted','--text','--text2','--text3','--text-auto',
        '--bg2','--bg-secondary','--bg-elevated','--bg3','--bg-tertiary','--bg-glass','--glass-bg',
        '--border','--border-light','--glass-border','--border-medium'],

    _applyAutoContrast() {
        const root = document.documentElement;
        // The theme CLASS lives on <body> and redefines tokens like --bg2 there. Because
        // <body> is a closer ancestor than :root, a :root-only override is shadowed for
        // body content. So set custom tokens on BOTH root and body (inline > stylesheet).
        const targets = [root, document.body].filter(Boolean);
        const setVar = (k, v) => { if (v) targets.forEach(t => t.style.setProperty(k, v)); };

        const customBg = this._readCustom('bg_color', 'skemi_bg_color');
        if (!customBg) {
            // No custom bg → let the preset theme class govern. Clear marker + stale inline tokens.
            root.removeAttribute('data-skemi-bg');
            targets.forEach(t => this._CUSTOM_BG_TOKENS.forEach(k => t.style.removeProperty(k)));
        }
        if (customBg) {
            const txt = this._bestTextColor(customBg);
            if (txt) {
                const isLightText = txt === '#f8fafc';
                // Marker for CSS: hardcoded neon/accent TEXT (var(--lg-cyan) etc.) can't read
                // --text, so page styles also key off this to darken on a light custom bg.
                // isLightText === bg is dark → data-skemi-bg="dark"; else the bg is light.
                root.setAttribute('data-skemi-bg', isLightText ? 'dark' : 'light');
                // Page bg on body too — the theme class shadows --bg for body content
                // (e.g. Legion's .lg-command gradient reads var(--bg)).
                setVar('--bg', customBg); setVar('--bg-primary', customBg);
                const sec = isLightText ? 'rgba(248,250,252,0.78)' : 'rgba(15,23,42,0.78)';
                const muted = isLightText ? 'rgba(248,250,252,0.58)' : 'rgba(15,23,42,0.58)';
                // design-tokens text scale + legacy aliases
                setVar('--text-primary', txt); setVar('--text-secondary', sec); setVar('--text-muted', muted);
                setVar('--text', txt); setVar('--text2', muted); setVar('--text3', muted);
                setVar('--text-auto', txt);

                // Derive the whole SURFACE palette from the custom bg so cards, glass
                // panels and borders stay in the same lightness family as the page —
                // otherwise flipping only --bg/--text leaves cards (var(--bg2)) the old
                // theme shade, and darkened text lands on a mismatched surface.
                setVar('--bg2', this._mix(customBg, txt, 0.06)); setVar('--bg-secondary', this._mix(customBg, txt, 0.06)); setVar('--bg-elevated', this._mix(customBg, txt, 0.06));
                setVar('--bg3', this._mix(customBg, txt, 0.11)); setVar('--bg-tertiary', this._mix(customBg, txt, 0.11));
                setVar('--bg-glass', this._mix(customBg, txt, 0.045)); setVar('--glass-bg', this._mix(customBg, txt, 0.045));
                setVar('--border', this._rgba(txt, 0.14)); setVar('--border-light', this._rgba(txt, 0.14)); setVar('--glass-border', this._rgba(txt, 0.14));
                setVar('--border-medium', this._rgba(txt, 0.22));
            }
        }

        const customAccent = this._readCustom('accent_color', 'skemi_accent_color');
        if (customAccent) {
            const onAccent = this._bestTextColor(customAccent);
            if (onAccent) {
                // Text that sits ON TOP of accent-colored buttons/badges.
                root.style.setProperty('--text-on-brand', onAccent);
                root.style.setProperty('--on-accent', onAccent);
                root.style.setProperty('--accent-text', onAccent);
            }
        }
    }
};

window.SkemiPrefs = SkemiPrefs;

document.addEventListener('DOMContentLoaded', () => SkemiPrefs.init());
}