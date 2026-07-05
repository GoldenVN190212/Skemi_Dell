/**
 * Phantom.js — DISABLED (legacy overlay deprecated).
 *
 * The standalone overlay built by this script (white-card modal with mini
 * viewport) was duplicating the polished Phantom UI baked into Computer.html
 * (`#localPhantomPreview`, `#localPhantomImage`, `#desktopPhantomHud`,
 * `#desktopViewportIdle`, `showPhantomDesktopOrVirtualChoice`,
 * `showPhantomScanOverlay`, etc.).
 *
 * The old script hijacked `#localPhantomModeBtn` in CAPTURE phase, blocking the
 * built-in flow and rendering the viewport into a tiny 720px modal — that's
 * why users saw only a thin strip of the desktop and no taskbar/icons.
 *
 * This file is intentionally a no-op so any cached `<script src="…Phantom.js">`
 * tag in older HTML keeps loading without doing anything. All Phantom logic now
 * lives inside Computer.html. To re-enable the legacy overlay set
 * `window.__SKEMI_PHANTOM_LEGACY = true` *before* this script loads.
 */
(function () {
    if (window.__SKEMI_PHANTOM_LEGACY === true) {
        // Caller explicitly opted into the legacy overlay — bail and let any
        // future rewrite live somewhere else.
        return;
    }
    // Expose a tiny shim so legacy callers don't blow up.
    if (!window.SkemiPhantom) {
        window.SkemiPhantom = {
            open() {
                const btn = document.getElementById('localPhantomModeBtn');
                if (btn) { btn.click(); return; }
                console.warn('[Phantom] Legacy overlay disabled. Use the Computer.html Phantom mode.');
            },
            close() { /* noop */ },
        };
    }
})();
