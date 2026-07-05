/* HandGesture.js — "Iron Man" webcam hand control for the research graph.
 *
 * MediaPipe Hands (loaded on demand from CDN) reads hand landmarks from the webcam
 * and drives a ResearchGraph like Tony Stark waving at a holographic display. The
 * vocabulary was deliberately kept SMALL and intuitive (the earlier 10-gesture
 * scheme tested as "siêu khó" — too hard to remember/aim). A clean cursor reticle
 * tracks the hand; no on-screen skeleton.
 *
 * SINGLE HAND
 *   • Move your hand                     → a glowing cursor follows your index finger
 *   • Pinch (thumb + index)              → GRAB the nearest node (generous snap radius)
 *   • Move while pinched                 → drag the grabbed node; open the pinch → drop
 * TWO HANDS
 *   • Move hands apart / together        → zoom in / out (pinch-to-zoom)
 *   • Rotate the line between hands       → gently spin the whole map
 *
 * Opt-in: asks for camera permission; degrades gracefully (mouse still works) if
 * the camera or MediaPipe is unavailable. The live HUD labels the detected gesture.
 */
(function (global) {
  'use strict';

  const HANDS_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
  const CONNECTIONS = [
    [0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
    [9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17],
  ];
  const GESTURE_VI = {
    PINCH: '🤏 Nắm / kéo', POINT: '👆 Trỏ', OPEN: '🖐 Bàn tay mở',
    FIST: '✊ Nắm đấm', PEACE: '✌️ Liên kết', THUMB: '👍 Bung toả',
    NONE: '…',
  };
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  class HandGesture {
    constructor(graph, opts = {}) {
      this.graph = graph;
      this.canvas = graph.canvas;
      this.overlay = opts.overlay || null;
      this.octx = this.overlay ? this.overlay.getContext('2d') : null;
      this.onStatus = opts.onStatus || (() => {});
      this.onGesture = opts.onGesture || (() => {});
      this.video = null;
      this.hands = null;
      this.running = false;
      this._raf = 0;
      this._dpr = Math.min(global.devicePixelRatio || 1, 2);
      // per-frame transient state
      this._prev = {};
      this._lastGesture = 'NONE';
      this._linkMode = false;
      this._linkA = null;
      this._pinchActive = false;
      this._grabbed = false;
      this._fistStillFrames = 0;
      this._boundResize = this._resizeOverlay.bind(this);
    }

    async start() {
      if (this.running) return { ok: true };
      this.onStatus('Đang xin quyền camera…');
      try {
        this.video = document.createElement('video');
        this.video.autoplay = true; this.video.playsInline = true; this.video.muted = true;
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: 'user' }, audio: false,
        });
        this.video.srcObject = stream;
        await this.video.play();
      } catch (e) {
        this.onStatus('Không mở được camera: ' + (e && e.message || e));
        return { ok: false, error: 'camera' };
      }
      try {
        await this._loadScript(HANDS_URL);
        const Hands = global.Hands;
        if (!Hands) throw new Error('MediaPipe Hands unavailable');
        this.hands = new Hands({ locateFile: (f) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}` });
        this.hands.setOptions({
          maxNumHands: 2, modelComplexity: 1,
          minDetectionConfidence: 0.6, minTrackingConfidence: 0.5,
        });
        this.hands.onResults((r) => this._onResults(r));
      } catch (e) {
        this.onStatus('Không tải được nhận diện tay: ' + (e && e.message || e));
        this._stopStream();
        return { ok: false, error: 'mediapipe' };
      }
      this.running = true;
      this._resizeOverlay();
      global.addEventListener('resize', this._boundResize);
      this.onStatus('Đưa tay vào khung hình ✋  (mở bàn tay = di chuyển)');
      this._loop();
      return { ok: true };
    }

    _loadScript(src) {
      return new Promise((res, rej) => {
        if (document.querySelector(`script[src="${src}"]`)) return res();
        const s = document.createElement('script');
        s.src = src; s.crossOrigin = 'anonymous';
        s.onload = () => res(); s.onerror = () => rej(new Error('load fail ' + src));
        document.head.appendChild(s);
      });
    }

    async _loop() {
      if (!this.running) return;
      try { if (this.video && this.video.readyState >= 2) await this.hands.send({ image: this.video }); }
      catch (e) { /* skip frame */ }
      this._raf = global.requestAnimationFrame(() => this._loop());
    }

    /* MediaPipe x is mirrored for a front camera → flip to match the user's view. */
    _toScreen(lm) {
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      return { x: (1 - lm.x) * W, y: lm.y * H };
    }

    _analyze(lm) {
      const wrist = lm[0];
      const ext = (tip, pip) => dist(lm[tip], wrist) > dist(lm[pip], wrist) * 1.04;
      const fingers = {
        thumb: dist(lm[4], lm[5]) > dist(lm[3], lm[5]) * 1.05,
        index: ext(8, 6), middle: ext(12, 10), ring: ext(16, 14), pinky: ext(20, 18),
      };
      const size = dist(lm[0], lm[9]) || 0.01;     // palm length (depth proxy)
      const pinch = dist(lm[4], lm[8]) / size;       // normalised thumb–index
      const center = {
        x: (lm[0].x + lm[5].x + lm[9].x + lm[13].x + lm[17].x) / 5,
        y: (lm[0].y + lm[5].y + lm[9].y + lm[13].y + lm[17].y) / 5,
      };
      const roll = Math.atan2(lm[17].y - lm[5].y, lm[17].x - lm[5].x);
      const cnt = [fingers.index, fingers.middle, fingers.ring, fingers.pinky].filter(Boolean).length;
      let gesture;
      if (pinch < 0.5) gesture = 'PINCH';
      else if (cnt === 0 && !fingers.thumb) gesture = 'FIST';
      else if (cnt >= 4) gesture = 'OPEN';
      else if (fingers.index && fingers.middle && !fingers.ring && !fingers.pinky) gesture = 'PEACE';
      else if (fingers.index && !fingers.middle && !fingers.ring && !fingers.pinky) gesture = 'POINT';
      else if (fingers.thumb && cnt === 0) gesture = 'THUMB';
      else gesture = 'OPEN';
      return { fingers, size, pinch, center, roll, gesture, tip: this._toScreen(lm[8]),
               centerScreen: this._toScreen({ x: center.x, y: center.y }) };
    }

    _onResults(res) {
      const handsLm = (res && res.multiHandLandmarks) || [];
      const analyses = handsLm.map((lm) => this._analyze(lm));
      this._drawHud(handsLm, analyses);

      if (!handsLm.length) {
        if (this._pinchActive) { this.graph.release(); this._pinchActive = false; this._grabbed = false; }
        this.graph.setPaused(false);
        this._prev = {};
        this._cursor = null;
        this.onGesture('NONE');
        return;
      }

      // TWO hands → pinch-to-zoom (move hands apart = zoom in, together = out) +
      // gentle spin. ONE hand → move cursor / pinch-grab a node / drag.
      if (analyses.length >= 2) { this._prev.single = false; this._twoHand(analyses); }
      else { this._prev.two = null; this._singleHand(analyses[0]); }
    }

    // DEAD-SIMPLE control (the old 10-gesture scheme was "siêu khó"):
    //   • Move your hand  → a glowing cursor follows your index finger
    //   • Pinch (thumb+index) → GRAB the nearest node (generous radius, snaps)
    //   • Move while pinched → the node follows your hand
    //   • Open the pinch → drop
    // Nothing else. No fist/peace/thumb/pan/zoom to remember.
    _singleHand(a) {
      // Heavy smoothing for a calm, easy-to-aim cursor.
      const rawTip = a.tip;
      if (!this._sTip) this._sTip = { x: rawTip.x, y: rawTip.y };
      this._sTip.x += (rawTip.x - this._sTip.x) * 0.35;
      this._sTip.y += (rawTip.y - this._sTip.y) * 0.35;
      const tip = this._sTip;
      this._cursor = tip;                       // for the HUD reticle

      const pinching = a.pinch < 0.6;           // forgiving threshold
      this.onGesture(pinching ? 'PINCH' : 'OPEN');

      if (pinching && !this._pinchActive) {
        this._pinchActive = true;
        const got = this.graph.grabNearest(tip.x, tip.y, 240);  // snap to nearest
        this._grabbed = !!got;
        this.onStatus(got ? '✊ Đang nắm: ' + (got.label || '') : 'Chụm gần một node để nắm');
      } else if (pinching && this._pinchActive) {
        if (this._grabbed) this.graph.dragTo(tip.x, tip.y);
      } else if (!pinching && this._pinchActive) {
        this.graph.release(); this._pinchActive = false; this._grabbed = false;
        this.onStatus('🖐 Di chuyển tay để ngắm · chụm ngón để nắm');
      } else {
        // hover-highlight the node you'd grab so aiming is obvious
        this.graph.hover = this.graph.nearestNode(tip.x, tip.y, 90);
      }
    }

    _twoHand(as) {
      if (this._pinchActive) { this.graph.release(); this._pinchActive = false; this._grabbed = false; }
      this.onGesture('TWO');
      const a = as[0].centerScreen, b = as[1].centerScreen;
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      const ang = Math.atan2(b.y - a.y, b.x - a.x);
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      this._twoMid = mid;                                   // for the HUD hint
      const p = this._prev.two;
      if (p) {
        const f = d / p.d;                                  // distance → zoom
        if (isFinite(f) && f > 0.5 && f < 2 && Math.abs(f - 1) > 0.006) this.graph.zoomAt(f, mid.x, mid.y);
        let da = ang - p.ang;                               // rotation → gentle spin
        if (da > Math.PI) da -= Math.PI * 2; if (da < -Math.PI) da += Math.PI * 2;
        if (Math.abs(da) > 0.012 && Math.abs(da) < 0.4) this.graph.spin(da);
      }
      this._prev.two = { d, ang };
      this.onStatus('🙌 Hai tay: kéo ra/vào để phóng to-nhỏ · xoay để quay');
    }

    // The on-screen hand skeleton was distracting ("bỏ cái tay đi") — we now draw
    // ONLY a small, clean cursor (one hand) or a zoom hint (two hands).
    _drawHud(handsLm, analyses) {
      if (!this.octx) return;
      const o = this.overlay, ctx = this.octx;
      const W = o.clientWidth, H = o.clientHeight;
      ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      if (analyses && analyses.length >= 2) {
        // two-hand zoom hint: a line + endpoints between the two palm centers
        const a = analyses[0].centerScreen, b = analyses[1].centerScreen;
        ctx.strokeStyle = 'rgba(34,211,238,0.7)'; ctx.lineWidth = 2; ctx.setLineDash([6, 6]);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.setLineDash([]);
        [a, b].forEach((c) => { ctx.fillStyle = 'rgba(34,211,238,0.9)'; ctx.beginPath(); ctx.arc(c.x, c.y, 8, 0, Math.PI * 2); ctx.fill(); });
        return;
      }

      // single-hand: a clean cursor reticle at the smoothed fingertip — green &
      // filled while grabbing, pink otherwise. No skeleton.
      const c = this._cursor;
      if (c) {
        const grab = this._pinchActive && this._grabbed;
        const col = this._pinchActive ? '#34d399' : '#f472b6';
        const r = grab ? 24 : 18;
        ctx.shadowColor = col; ctx.shadowBlur = 18;
        ctx.strokeStyle = col; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI * 2); ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.beginPath(); ctx.moveTo(c.x - 6, c.y); ctx.lineTo(c.x + 6, c.y);
        ctx.moveTo(c.x, c.y - 6); ctx.lineTo(c.x, c.y + 6); ctx.stroke();
        if (grab) { ctx.fillStyle = 'rgba(52,211,153,0.18)'; ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI * 2); ctx.fill(); }
      }
    }

    _resizeOverlay() {
      if (!this.overlay) return;
      const o = this.overlay;
      o.width = Math.round((o.clientWidth || 800) * this._dpr);
      o.height = Math.round((o.clientHeight || 600) * this._dpr);
    }

    _stopStream() {
      try {
        const s = this.video && this.video.srcObject;
        if (s) s.getTracks().forEach((t) => t.stop());
      } catch (e) {}
    }

    stop() {
      this.running = false;
      if (this._raf) global.cancelAnimationFrame(this._raf);
      this._raf = 0;
      global.removeEventListener('resize', this._boundResize);
      this._stopStream();
      this.graph.setPaused(false);
      if (this.octx) {
        this.octx.setTransform(1, 0, 0, 1, 0, 0);
        this.octx.clearRect(0, 0, this.overlay.width, this.overlay.height);
      }
      this.onStatus('Đã tắt điều khiển cử chỉ.');
    }
  }

  global.HandGesture = HandGesture;
})(window);
