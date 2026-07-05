/* ResearchGraph.js — Skemi deep-research knowledge map (v3 "Lab").
 *
 * A self-contained, dependency-free knowledge graph on a <canvas>. A research
 * topic becomes an interactive web of ROOT → CORE → COMPONENT → APPLICATION →
 * EXAMPLE → CAUTION nodes with NAMED, often cross-linking relationships, so the
 * topic is absorbed visually. Designed to be driven by mouse/touch AND by the
 * webcam hand-gesture controller (HandGesture.js).
 *
 * v3 changes (per user goal):
 *   • Nodes are CARDS (icon chip + label inside a rounded card), not bare circles
 *   • Collision-aware layout → children fan OUT from their parent, no overlap
 *   • Curved, named edges; cross-links styled distinctly → a real web, not a star
 *   • Single click = select (summary panel); DOUBLE click = enter node "world"
 *   • Per-node drill state persists when you switch nodes and come back
 *   • Smooth appear animation for newly drilled / created nodes
 *   • LAB MODE: drag a wire from one node to another to connect them (with a
 *     feasibility hint), double-click empty space to create a new node
 *
 * Public API (used by gestures + the Search page):
 *   setData, mergeData, panBy, zoomAt, grabAt, grabNearest, dragTo, release,
 *   spin, explode, focusNext, select, nodeAt, nearestNode, setPaused, linkNodes,
 *   addNode, setLabMode, fit
 */
(function (global) {
  'use strict';

  const GROUPS = {
    root:        { color: '#f472b6', glow: 'rgba(244,114,182,0.55)', icon: '◆' },
    core:        { color: '#a855f7', glow: 'rgba(168,85,247,0.50)',  icon: '✸' },
    component:   { color: '#60a5fa', glow: 'rgba(96,165,250,0.45)',  icon: '▣' },
    application: { color: '#34d399', glow: 'rgba(52,211,153,0.45)',  icon: '◈' },
    example:     { color: '#fbbf24', glow: 'rgba(251,191,36,0.45)',  icon: '✦' },
    caution:     { color: '#fb7185', glow: 'rgba(251,113,133,0.45)', icon: '⚠' },
    custom:      { color: '#22d3ee', glow: 'rgba(34,211,238,0.50)',  icon: '＋' },
    default:     { color: '#94a3b8', glow: 'rgba(148,163,184,0.4)',  icon: '•' },
  };
  const groupOf = (g) => GROUPS[g] || GROUPS.default;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);

  class ResearchGraph {
    constructor(canvas, opts = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.nodes = [];
      this.edges = [];
      this.onSelect = opts.onSelect || (() => {});
      this.onEnter = opts.onEnter || (() => {});         // double-click → node world
      this.onCreateNode = opts.onCreateNode || (() => {}); // lab: dblclick empty
      this.onLink = opts.onLink || (() => {});           // lab: a wire was connected
      this.scale = 1;
      this.offsetX = 0;
      this.offsetY = 0;
      this.dpr = Math.min(global.devicePixelRatio || 1, 2);
      this.dragNode = null;
      this.panning = false;
      this.last = { x: 0, y: 0 };
      this.hover = null;
      this.selected = null;
      this.paused = false;
      this.labMode = false;
      this.linkPulses = [];     // transient edge-creation glows
      this._wireFrom = null;    // lab: node a wire is being dragged from
      this._wirePos = null;     // lab: current cursor (screen) while wiring
      this._raf = 0;
      this._alpha = 1;          // simulation "temperature"
      this._frozen = false;     // once settled, the graph is SOLID (no springs/jiggle)
      this._fitUntil = 0;       // auto-fit window (ms epoch) while the layout settles
      this._userMoved = false;  // user pan/zoom/drag → stop auto-fitting
      this._seq = 0;
      this._resize = this._resize.bind(this);
      this._tick = this._tick.bind(this);
      this._bindEvents();
      this._resize();
      global.addEventListener('resize', this._resize);
    }

    /* ---- node geometry (cards, measured in WORLD units) ---- */
    _measure(n) {
      const ctx = this.ctx;
      const big = n.group === 'root';
      const fs = big ? 19 : 15.5;
      ctx.font = `${big ? 800 : 600} ${fs}px Inter, system-ui, sans-serif`;
      // Clean junk tails (" \ Anthropic", " | Site") so a label reads as a concept,
      // then WRAP to at most 2 lines instead of cutting mid-word with an ellipsis —
      // titles now read fully on the card (full text still lives in the detail card).
      const label = String(n.label || '').replace(/\s*[\\|]\s*\S.*$/, '').replace(/\s+/g, ' ').trim();
      const maxChars = big ? 30 : 26;
      const lines = []; let line = '';
      for (const w of label.split(' ')) {
        const tryl = line ? line + ' ' + w : w;
        if (tryl.length > maxChars && line) { lines.push(line); line = w; if (lines.length === 2) break; }
        else line = tryl;
      }
      if (lines.length < 2 && line) lines.push(line);
      if (lines.length === 2 && lines.join(' ').length < label.length) {
        lines[1] = lines[1].slice(0, maxChars - 1).replace(/\s+\S*$/, '') + '…';
      }
      n._lines = lines.length ? lines : [label || '—'];
      n._fs = fs;
      let tw = 0; n._lines.forEach((l) => { tw = Math.max(tw, ctx.measureText(l).width); });
      n.w = clamp(tw + (big ? 66 : 56), big ? 170 : 132, big ? 300 : 250);
      n.h = (big ? 58 : 46) + (n._lines.length > 1 ? (big ? 18 : 16) : 0);
    }

    setData(data) {
      const nodes = Array.isArray(data && data.nodes) ? data.nodes : [];
      const edges = Array.isArray(data && data.edges) ? data.edges : [];
      const W = this.canvas.clientWidth || 900, H = this.canvas.clientHeight || 640;
      const cx = W / 2, cy = H / 2;
      // Build node objects first (positions set after we know the branch structure).
      this.nodes = nodes.map((n, i) => {
        const isRoot = (n.group === 'root');
        const node = {
          id: String(n.id != null ? n.id : 'n' + i),
          label: String(n.label || '').slice(0, 60),
          group: n.group || 'default',
          importance: clamp(Number(n.importance) || 2, 1, 5),
          detail: String(n.detail || ''),
          body: String(n.body || n.detail || ''),
          url: String(n.url || ''),
          depth: isRoot ? 0 : 1,
          x: cx, y: cy, vx: 0, vy: 0, pinned: isRoot, appear: 1,
          expanded: false, drilling: false, drillMsg: '',
        };
        this._measure(node);
        return node;
      });
      const byId = {};
      this.nodes.forEach((n) => { byId[n.id] = n; });
      this.edges = edges
        .map((e) => ({
          source: byId[String(e.source)], target: byId[String(e.target)],
          relation: String(e.relation || ''),
        }))
        .filter((e) => e.source && e.target && e.source !== e.target)
        .map((e) => { e.cross = (e.source.group !== 'root' && e.target.group !== 'root'); return e; });
      this._layoutBranched(cx, cy);
      this.scale = 1; this.offsetX = 0; this.offsetY = 0;
      this._alpha = 1; this.selected = null; this.hover = null;
      // Keep the whole map framed while the force layout expands & settles (~2.8s),
      // so a big 20-node graph never overflows the view. Stops the moment the user
      // pans/zooms/drags so we don't fight their interaction.
      this.refit(2800);
      this.start();
    }

    /* BRANCHED initial layout (so 16-20 nodes read as clear branches, not a crammed
     * ring): root at center, "core" pillars on an inner ring, and every leaf
     * clustered around the angle of the core it links to. Falls back to an even ring
     * when the graph has no core tier (e.g. web-grounded / skeleton maps). */
    _layoutBranched(cx, cy) {
      const root = this.nodes.find((n) => n.group === 'root') || this.nodes[0];
      if (!root) return;
      root.x = cx; root.y = cy; root.depth = 0;
      const cores = this.nodes.filter((n) => n !== root && n.group === 'core');
      const leaves = this.nodes.filter((n) => n !== root && n.group !== 'core');
      const n = this.nodes.length;
      // rings scale gently with node count so a big graph has room to breathe
      const innerR = 180 + Math.max(0, n - 12) * 6;
      const outerR = innerR + 190 + Math.max(0, n - 12) * 6;
      if (!cores.length) {                       // no core tier → even spread ring
        const non = this.nodes.filter((x) => x !== root);
        non.forEach((x, k) => {
          const ang = (k / Math.max(1, non.length)) * Math.PI * 2 - Math.PI / 2;
          const rad = innerR + (k % 3) * 64;
          x.x = cx + Math.cos(ang) * rad; x.y = cy + Math.sin(ang) * rad; x.depth = 1;
        });
        return;
      }
      const coreAngle = new Map();
      cores.forEach((c, k) => {
        const ang = (k / cores.length) * Math.PI * 2 - Math.PI / 2;
        coreAngle.set(c, ang); c.depth = 1;
        c.x = cx + Math.cos(ang) * innerR; c.y = cy + Math.sin(ang) * innerR;
      });
      const parentCore = (leaf) => {
        for (const e of this.edges) {
          if (e.source === leaf && coreAngle.has(e.target)) return e.target;
          if (e.target === leaf && coreAngle.has(e.source)) return e.source;
        }
        return null;
      };
      const grouped = new Map(); const orphans = [];
      leaves.forEach((l) => { const p = parentCore(l); if (p) { (grouped.get(p) || grouped.set(p, []).get(p)).push(l); } else orphans.push(l); });
      grouped.forEach((arr, core) => {
        const base = coreAngle.get(core);
        const spread = Math.min(1.1, 0.34 + arr.length * 0.2);
        arr.forEach((l, j) => {
          const frac = arr.length > 1 ? (j / (arr.length - 1)) : 0.5;
          const ang = base - spread / 2 + spread * frac;
          const rad = outerR + (j % 2) * 54;
          l.depth = 2;
          l.x = cx + Math.cos(ang) * rad + (Math.random() - 0.5) * 16;
          l.y = cy + Math.sin(ang) * rad + (Math.random() - 0.5) * 16;
        });
      });
      orphans.forEach((l, j) => {
        const ang = (j / Math.max(1, orphans.length)) * Math.PI * 2 - Math.PI / 4;
        l.depth = 2;
        l.x = cx + Math.cos(ang) * (outerR + 34); l.y = cy + Math.sin(ang) * (outerR + 34);
      });
    }

    start() { if (!this._raf) this._raf = global.requestAnimationFrame(this._tick); }
    stop() { if (this._raf) { global.cancelAnimationFrame(this._raf); this._raf = 0; } }

    /* ---- physics: settle firmly, then FREEZE into a solid (no rubber-band) ---- */
    _simulate() {
      const nodes = this.nodes;
      if (!nodes.length) return;
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      const cx = W / 2, cy = H / 2;

      // FROZEN: the layout has settled → the map is SOLID. Nothing drifts; only the
      // node the user is actively dragging moves, and it STAYS where dropped. This
      // kills the "lỏng lẻo như cao su" feel + the slow snap-back entirely.
      if (this._frozen) {
        const drag = this.dragNode;
        for (const n of nodes) {
          if (n.appear < 1) n.appear = Math.min(1, n.appear + 0.06);
          n.vx = 0; n.vy = 0;
        }
        // While dragging, gently push any node the dragged card overlaps so they
        // never end up stacked — but only the OTHERS move, the map stays calm.
        if (drag) {
          for (const b of nodes) {
            if (b === drag || b.pinned) continue;
            const dx = b.x - drag.x, dy = b.y - drag.y;
            const d = Math.hypot(dx, dy) || 0.01;
            const minD = (Math.hypot(drag.w, drag.h) + Math.hypot(b.w, b.h)) * 0.5;
            if (d < minD) {
              const push = (minD - d);
              b.x += (dx / d) * push; b.y += (dy / d) * push;
            }
          }
        }
        return;
      }

      const k = this._alpha;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy || 0.01;
          const d = Math.sqrt(d2);
          const rep = (11500 / d2) * k;
          let fx = (dx / d) * rep, fy = (dy / d) * rep;
          // HARD collision — unscaled by alpha so the FINAL settled layout has NO
          // overlap, even with many nodes (the "chồng lên nhau" complaint).
          const minD = (Math.hypot(a.w, a.h) + Math.hypot(b.w, b.h)) * 0.52;
          if (d < minD) {
            const push = (minD - d) * 0.9;
            fx += (dx / d) * push; fy += (dy / d) * push;
          }
          a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
        }
        a.vx += (cx - a.x) * 0.0011 * k;
        a.vy += (cy - a.y) * 0.0011 * k;
      }
      this.edges.forEach((e) => {
        let dx = e.target.x - e.source.x, dy = e.target.y - e.source.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const rest = e.cross ? 240 : 200;
        const f = ((d - rest) / d) * 0.016 * k;
        const fx = dx * f, fy = dy * f;
        e.source.vx += fx; e.source.vy += fy;
        e.target.vx -= fx; e.target.vy -= fy;
      });
      nodes.forEach((n) => {
        if (n.appear < 1) n.appear = Math.min(1, n.appear + 0.06);
        if (n === this.dragNode) { n.vx = 0; n.vy = 0; return; }
        if (n.pinned) { n.x += (cx - n.x) * 0.03; n.y += (cy - n.y) * 0.03; n.vx = 0; n.vy = 0; return; }
        if (n.fixed) { n.vx = 0; n.vy = 0; return; }
        n.vx *= 0.80; n.vy *= 0.80;        // firmer damping → settles fast, less wobble
        n.x += clamp(n.vx, -16, 16);
        n.y += clamp(n.vy, -16, 16);
      });
      this._alpha *= 0.985;
      // Settled → FREEZE: lock every node in place so the graph is rock-solid.
      if (this._alpha < 0.06 && !this.dragNode) {
        this._alpha = 0;
        this._frozen = true;
        for (const n of nodes) { if (n.group !== 'root') n.fixed = true; n.vx = 0; n.vy = 0; }
      }
    }

    /* ---- transforms / hit-testing ---- */
    _toScreen(n) {
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      return { x: (n.x - W / 2) * this.scale + W / 2 + this.offsetX,
               y: (n.y - H / 2) * this.scale + H / 2 + this.offsetY };
    }
    _toWorld(sx, sy) {
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      return { x: (sx - W / 2 - this.offsetX) / this.scale + W / 2,
               y: (sy - H / 2 - this.offsetY) / this.scale + H / 2 };
    }
    _nodeAt(sx, sy) {
      for (let i = this.nodes.length - 1; i >= 0; i--) {
        const n = this.nodes[i];
        const s = this._toScreen(n);
        const hw = (n.w / 2) * this.scale + 4, hh = (n.h / 2) * this.scale + 4;
        if (Math.abs(sx - s.x) <= hw && Math.abs(sy - s.y) <= hh) return n;
      }
      return null;
    }

    /* ---- render ---- */
    _tick() {
      if (!this.paused) this._simulate();
      if (this._fitUntil) {
        const now = (global.performance ? performance.now() : Date.now());
        if (!this._userMoved && now < this._fitUntil) this.fit();
        else this._fitUntil = 0;
      }
      this._draw();
      this._raf = global.requestAnimationFrame(this._tick);
    }

    _roundRect(ctx, x, y, w, h, r) {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r);
      ctx.closePath();
    }

    _draw() {
      const ctx = this.ctx;
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      // ---- edges (curved, named) ----
      this.edges.forEach((e) => {
        const a = this._toScreen(e.source), b = this._toScreen(e.target);
        const active = this.selected && (e.source === this.selected || e.target === this.selected);
        const hov = this.hover && (e.source === this.hover || e.target === this.hover);
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        // curve control point offset perpendicular to the edge for an arc
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
        const bend = (e.cross ? 26 : 14);
        const cxp = mx + (-dy / len) * bend, cyp = my + (dx / len) * bend;
        const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
        grad.addColorStop(0, groupOf(e.source.group).color);
        grad.addColorStop(1, groupOf(e.target.group).color);
        ctx.strokeStyle = grad;
        ctx.lineWidth = (active || hov) ? 2.4 : (e.cross ? 1.1 : 1.5);
        ctx.globalAlpha = (active || hov) ? 0.98 : (e.cross ? 0.30 : 0.45);
        if (e.cross && !(active || hov)) ctx.setLineDash([5, 5]); else ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(cxp, cyp, b.x, b.y); ctx.stroke();
        ctx.setLineDash([]);
        // Flowing "current" along the wire — small bright dots travel from source →
        // target on a seamless loop (animated dash offset; GPU-cheap, every frame).
        const _flow = (global.performance ? performance.now() : Date.now()) / 1000;
        ctx.save();
        ctx.globalAlpha = (active || hov) ? 0.95 : 0.5;
        ctx.lineWidth = (active || hov) ? 2.2 : 1.4;
        ctx.lineCap = 'round';
        ctx.setLineDash([2.5, 15]);
        ctx.lineDashOffset = -((_flow * 30) % 17.5);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(cxp, cyp, b.x, b.y); ctx.stroke();
        ctx.restore();
        ctx.setLineDash([]);
        // (relation labels intentionally NOT drawn on the wires — too cluttered;
        // the named relationships live in the node "world" panel instead.)
      });
      ctx.globalAlpha = 1;

      // ---- lab wire being dragged ----
      if (this._wireFrom && this._wirePos) {
        const a = this._toScreen(this._wireFrom), b = this._wirePos;
        ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2.4; ctx.setLineDash([7, 6]);
        ctx.shadowColor = '#22d3ee'; ctx.shadowBlur = 14;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        ctx.shadowBlur = 0; ctx.setLineDash([]);
      }

      // ---- link pulses (new edge glow) ----
      if (this.linkPulses.length) {
        this.linkPulses.forEach((p) => {
          const a = this._toScreen(p.a), b = this._toScreen(p.b);
          ctx.strokeStyle = '#34d399'; ctx.lineWidth = 3; ctx.globalAlpha = p.t;
          ctx.shadowColor = '#34d399'; ctx.shadowBlur = 18;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          ctx.shadowBlur = 0; p.t -= 0.02;
        });
        this.linkPulses = this.linkPulses.filter((p) => p.t > 0);
        ctx.globalAlpha = 1;
      }

      // ---- nodes as cards ----
      this.nodes.forEach((n) => {
        const s = this._toScreen(n);
        const g = groupOf(n.group);
        const ap = easeOut(clamp(n.appear, 0, 1));
        const sc = this.scale * (0.6 + 0.4 * ap);
        const w = n.w * sc, h = n.h * sc;
        const x = s.x - w / 2, y = s.y - h / 2, r = Math.min(16, h / 2);
        const isSel = n === this.selected, isHov = n === this.hover;
        const wireTarget = this._wireFrom && isHov && n !== this._wireFrom;
        ctx.globalAlpha = ap;
        // glow
        ctx.shadowColor = g.glow; ctx.shadowBlur = (isSel || isHov) ? 30 : 16;
        // card body
        this._roundRect(ctx, x, y, w, h, r);
        const bg = ctx.createLinearGradient(x, y, x, y + h);
        bg.addColorStop(0, 'rgba(24,16,40,0.96)');
        bg.addColorStop(1, 'rgba(14,9,26,0.96)');
        ctx.fillStyle = bg; ctx.fill();
        ctx.shadowBlur = 0;
        // colored border / selection ring
        ctx.lineWidth = isSel ? 2.6 : (wireTarget ? 2.6 : 1.4);
        ctx.strokeStyle = wireTarget ? '#22d3ee' : (isSel ? '#ffffff' : g.color);
        ctx.globalAlpha = ap * (isSel || isHov || wireTarget ? 1 : 0.85);
        this._roundRect(ctx, x, y, w, h, r); ctx.stroke();
        ctx.globalAlpha = ap;
        // icon chip (left)
        const chipR = h * 0.30;
        const chipX = x + h * 0.5, chipY = y + h / 2;
        ctx.beginPath(); ctx.arc(chipX, chipY, chipR, 0, Math.PI * 2);
        const cg = ctx.createRadialGradient(chipX - chipR * 0.3, chipY - chipR * 0.3, chipR * 0.2, chipX, chipY, chipR);
        cg.addColorStop(0, '#ffffff'); cg.addColorStop(0.3, g.color); cg.addColorStop(1, g.color);
        ctx.fillStyle = cg; ctx.fill();
        ctx.fillStyle = 'rgba(8,5,16,0.92)';
        ctx.font = `${chipR * 1.25}px Inter, system-ui, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(g.icon, chipX, chipY + 0.5);
        // label (1-2 wrapped lines, vertically centered next to the chip)
        ctx.fillStyle = 'rgba(255,255,255,0.97)';
        ctx.font = `${n.group === 'root' ? 800 : 600} ${n._fs * sc}px Inter, system-ui, sans-serif`;
        ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
        const _lines = n._lines || [n._disp || ''];
        const _lx = x + h * 0.5 + chipR + 6;
        const _lh = n._fs * sc * 1.18;
        const _ly0 = chipY + 0.5 - (_lines.length - 1) * _lh / 2;
        const _maxw = w - (h * 0.5 + chipR + 14);
        _lines.forEach((ln, li) => ctx.fillText(ln, _lx, _ly0 + li * _lh, _maxw));
        // "expanded" dot indicator
        if (n.expanded) {
          ctx.fillStyle = '#34d399';
          ctx.beginPath(); ctx.arc(x + w - 9, y + 9, 3.5, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;
      });
      ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    }

    /* ---- public API ---- */
    panBy(dx, dy) { this._userMoved = true; this.offsetX += dx; this.offsetY += dy; }
    zoomAt(factor, sx, sy) {
      this._userMoved = true;
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      if (sx == null) { sx = W / 2; sy = H / 2; }
      const before = this._toWorld(sx, sy);
      this.scale = clamp(this.scale * factor, 0.25, 3.4);
      const after = this._toWorld(sx, sy);
      this.offsetX += (after.x - before.x) * this.scale;
      this.offsetY += (after.y - before.y) * this.scale;
    }
    grabAt(sx, sy) {
      this.dragNode = this._nodeAt(sx, sy);
      if (this.dragNode) {
        const w = this._toWorld(sx, sy);
        this._dragOffset = { x: this.dragNode.x - w.x, y: this.dragNode.y - w.y };
      }
      this._alpha = Math.max(this._alpha, 0.5);
      return this.dragNode;
    }
    grabNearest(sx, sy, radius) {
      const n = this.nearestNode(sx, sy, radius || 220);
      this.dragNode = n;
      if (n) {
        const w = this._toWorld(sx, sy);
        this._dragOffset = { x: n.x - w.x, y: n.y - w.y };
        this.select(n);
      }
      this._alpha = Math.max(this._alpha, 0.5);
      return n;
    }
    dragTo(sx, sy) {
      if (!this.dragNode) return;
      const w = this._toWorld(sx, sy);
      const off = this._dragOffset || { x: 0, y: 0 };
      const tx = w.x + off.x, ty = w.y + off.y;
      this.dragNode.x += (tx - this.dragNode.x) * 0.5;
      this.dragNode.y += (ty - this.dragNode.y) * 0.5;
    }
    release() {
      const d = this.dragNode;
      if (d) {
        if (d.group !== 'root') d.fixed = true;   // stays EXACTLY where dropped
        // DROP-TO-LINK ("lắp"): if dropped squarely onto another node, connect them
        // (works for mouse AND hand gesture) — easy way to wire ideas together.
        let best = null, bestD = Infinity;
        for (const n of this.nodes) {
          if (n === d) continue;
          const dist = Math.hypot(n.x - d.x, n.y - d.y);
          const near = (Math.hypot(n.w, n.h) + Math.hypot(d.w, d.h)) * 0.34;
          if (dist < near && dist < bestD) { bestD = dist; best = n; }
        }
        if (best) {
          const exists = this.edges.some((e) => (e.source === d && e.target === best) || (e.source === best && e.target === d));
          if (!exists) {
            // nudge apart so they don't stack, then wire
            const dx = (d.x - best.x) || 1, dy = (d.y - best.y) || 1, m = Math.hypot(dx, dy) || 1;
            const sep = (Math.hypot(best.w, best.h) + Math.hypot(d.w, d.h)) * 0.5;
            d.x = best.x + (dx / m) * sep; d.y = best.y + (dy / m) * sep;
            // lab mode → synthesise a new idea from the pair; otherwise just wire them.
            this.linkNodes(best, d, '', !this.labMode);
          }
        }
      }
      this.dragNode = null;
    }
    spin(rad) {
      this._userMoved = true;
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight, cx = W / 2, cy = H / 2;
      const c = Math.cos(rad), s = Math.sin(rad);
      this.nodes.forEach((n) => { const dx = n.x - cx, dy = n.y - cy; n.x = cx + dx * c - dy * s; n.y = cy + dx * s + dy * c; });
    }
    explode(factor) {
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight, cx = W / 2, cy = H / 2;
      const f = clamp(factor || 1, 0.85, 1.18);
      this.nodes.forEach((n) => { if (n.group === 'root') return; n.x = cx + (n.x - cx) * f; n.y = cy + (n.y - cy) * f; });
    }
    focusNext() {
      if (!this.nodes.length) return;
      const i = this.selected ? this.nodes.indexOf(this.selected) : -1;
      this.select(this.nodes[(i + 1) % this.nodes.length]);
    }
    select(n) { this.selected = n; if (n) this.onSelect(n); }
    nodeAt(sx, sy) { return this._nodeAt(sx, sy); }
    nearestNode(sx, sy, maxDist) {
      let best = null, bd = (maxDist || 9999) ** 2;
      this.nodes.forEach((n) => { const s = this._toScreen(n); const d = (sx - s.x) ** 2 + (sy - s.y) ** 2; if (d < bd) { bd = d; best = n; } });
      return best;
    }
    setPaused(p) { this.paused = !!p; }
    setLabMode(b) { this.labMode = !!b; if (!b) { this._wireFrom = null; this._wirePos = null; } }

    /* DEEP-RESEARCH drill: graft a sub-graph onto an anchor, fanning children
     * OUTWARD from the anchor (away from root) in a spaced arc so they don't
     * pile on top of existing nodes. */
    mergeData(subData, anchor) {
      if (!subData || !Array.isArray(subData.nodes) || !anchor) return 0;
      const prefix = 'd' + (++this._seq) + '_';
      const subRoot = subData.nodes.find((n) => n.group === 'root');
      const subRootId = subRoot ? String(subRoot.id) : null;
      const idMap = {};
      const added = [];
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight, cx = W / 2, cy = H / 2;
      // outward direction = from root/center toward the anchor
      let baseAng = Math.atan2(anchor.y - cy, anchor.x - cx);
      if (!isFinite(baseAng)) baseAng = 0;
      const children = subData.nodes.filter((n) => !(subRootId && String(n.id) === subRootId));
      const span = Math.min(Math.PI * 1.2, 0.5 + children.length * 0.32);
      let ci = 0;
      subData.nodes.forEach((n) => {
        if (subRootId && String(n.id) === subRootId) { idMap[String(n.id)] = anchor.id; return; }
        const nid = prefix + String(n.id);
        idMap[String(n.id)] = nid;
        const frac = children.length > 1 ? (ci / (children.length - 1)) : 0.5;
        const ang = baseAng - span / 2 + span * frac;
        const rad = 150 + (ci % 2) * 56;
        const node = {
          id: nid, label: String(n.label || '').slice(0, 60), group: n.group || 'component',
          importance: clamp(Number(n.importance) || 2, 1, 5),
          detail: String(n.detail || ''), body: String(n.body || n.detail || ''),
          url: String(n.url || ''),
          depth: (anchor.depth || 1) + 1,
          x: anchor.x + Math.cos(ang) * rad + (Math.random() - 0.5) * 18,
          y: anchor.y + Math.sin(ang) * rad + (Math.random() - 0.5) * 18,
          vx: 0, vy: 0, pinned: false, appear: 0,
          expanded: false, drilling: false, drillMsg: '',
        };
        this._measure(node);
        this.nodes.push(node); added.push(node); ci++;
      });
      const byId = {}; this.nodes.forEach((n) => { byId[n.id] = n; });
      (subData.edges || []).forEach((e) => {
        const s = byId[idMap[String(e.source)]], t = byId[idMap[String(e.target)]];
        if (s && t && s !== t &&
            !this.edges.some((x) => (x.source === s && x.target === t) || (x.source === t && x.target === s))) {
          this.edges.push({ source: s, target: t, relation: String(e.relation || ''),
            cross: (s.group !== 'root' && t.group !== 'root' && s !== anchor && t !== anchor) });
        }
      });
      anchor.expanded = true;
      this._alpha = 1; this._frozen = false;      // new sub-nodes must settle into place
      return added.length;
    }

    // Lab: create a fresh node near a world point (or center).
    addNode(label, group, near) {
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      const p = near || this._toWorld(W / 2, H / 2);
      const node = {
        id: 'u' + (++this._seq), label: String(label || 'Node mới').slice(0, 60),
        group: group || 'custom', importance: 3, detail: '', body: '',
        depth: 2, x: p.x, y: p.y, vx: 0, vy: 0, pinned: false, appear: 0,
        expanded: false, drilling: false, drillMsg: '', custom: true,
      };
      this._measure(node);
      this.nodes.push(node);
      this._alpha = Math.max(this._alpha, 0.6); this._frozen = false;
      this.select(node);
      return node;
    }

    // Create a link between two nodes (Stark-style "connect these"). Returns the
    // new edge (with a feasibility score) or null if it already existed.
    linkNodes(a, b, relation, silent) {
      if (!a || !b || a === b) return null;
      if (this.edges.some((e) => (e.source === a && e.target === b) || (e.source === b && e.target === a))) return null;
      const feas = this._feasibility(a, b);
      const edge = { source: a, target: b, relation: relation || feas.label,
        cross: (a.group !== 'root' && b.group !== 'root'), feasibility: feas.score, custom: true };
      this.edges.push(edge);
      this.linkPulses.push({ a, b, t: 1 });
      this._alpha = Math.max(this._alpha, 0.4);
      if (!silent) this.onLink(a, b, feas);   // silent: skip the synthesis trigger
      return edge;
    }

    // Rough feasibility heuristic for a hand-made connection: shared neighbours
    // and group affinity → "khả thi cao / vừa / thấp".
    _feasibility(a, b) {
      const na = new Set(), nb = new Set();
      this.edges.forEach((e) => {
        if (e.source === a) na.add(e.target); if (e.target === a) na.add(e.source);
        if (e.source === b) nb.add(e.target); if (e.target === b) nb.add(e.source);
      });
      let shared = 0; na.forEach((n) => { if (nb.has(n)) shared++; });
      const affinity = (a.group === b.group) ? 0.2 : 0.35;
      const score = clamp(0.25 + shared * 0.22 + affinity, 0, 1);
      const label = score > 0.66 ? 'khả thi cao' : score > 0.4 ? 'có thể' : 'thử nghiệm';
      return { score, label, shared };
    }

    // Fit/center the whole graph in view. Bounds include each card's FULL extent
    // (half width/height) so edge cards aren't clipped, with generous padding that
    // leaves room for the floating legend / overview / topbar overlays.
    fit() {
      if (!this.nodes.length) return;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      this.nodes.forEach((n) => {
        const hw = n.w / 2 + 8, hh = n.h / 2 + 8;
        minX = Math.min(minX, n.x - hw); maxX = Math.max(maxX, n.x + hw);
        minY = Math.min(minY, n.y - hh); maxY = Math.max(maxY, n.y + hh);
      });
      const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
      const padX = 110, padY = 104;            // headroom for legend / overview panels
      const gw = (maxX - minX) || 1, gh = (maxY - minY) || 1;
      // Floor raised to 0.5 so cards never shrink to an unreadable size — better to
      // let the user pan a slightly larger map than squint at a tiny one.
      this.scale = clamp(Math.min(W / (gw + padX * 2), H / (gh + padY * 2)), 0.5, 1.5);
      const gcx = (minX + maxX) / 2, gcy = (minY + maxY) / 2;
      // center the graph's midpoint on the screen center
      this.offsetX = (W / 2 - gcx) * this.scale;
      this.offsetY = (H / 2 - gcy) * this.scale;
    }

    // Re-frame: keep the map fitted while it settles for `ms`, then hand control
    // back to the user. Used on open, "Canh giữa" and "Sắp xếp".
    refit(ms) {
      this._userMoved = false;
      this._frozen = false;                       // re-heat so the layout can re-settle
      if (this._alpha < 0.3) this._alpha = 0.6;
      this._fitUntil = (global.performance ? performance.now() : Date.now()) + (ms || 2200);
      this.fit();
    }

    /* ---- mouse / touch ---- */
    _bindEvents() {
      const c = this.canvas;
      const pos = (ev) => { const r = c.getBoundingClientRect(); const t = ev.touches ? ev.touches[0] : ev; return { x: t.clientX - r.left, y: t.clientY - r.top }; };
      const down = (ev) => {
        this._userMoved = true;            // stop the settle-time auto-fit
        const p = pos(ev); this.last = p;
        const n = this._nodeAt(p.x, p.y);
        if (this.labMode && n) {           // lab: start a wire from this node
          this._wireFrom = n; this._wirePos = p; this.select(n);
          ev.preventDefault && ev.preventDefault(); return;
        }
        if (n) { this.dragNode = n; this._alpha = Math.max(this._alpha, 0.5); this.select(n); }
        else { this.panning = true; }
      };
      const move = (ev) => {
        const p = pos(ev);
        if (this._wireFrom) { this._wirePos = p; this.hover = this._nodeAt(p.x, p.y); }
        else if (this.dragNode) { const w = this._toWorld(p.x, p.y); this.dragNode.x = w.x; this.dragNode.y = w.y; this._alpha = Math.max(this._alpha, 0.3); }
        else if (this.panning) { this.offsetX += p.x - this.last.x; this.offsetY += p.y - this.last.y; }
        else { this.hover = this._nodeAt(p.x, p.y); c.style.cursor = this.hover ? (this.labMode ? 'crosshair' : 'pointer') : 'grab'; }
        this.last = p;
        if (this.dragNode || this.panning || this._wireFrom) ev.preventDefault && ev.preventDefault();
      };
      const up = (ev) => {
        if (this._wireFrom) {
          const p = this.last; const tgt = this._nodeAt(p.x, p.y);
          if (tgt && tgt !== this._wireFrom) this.linkNodes(this._wireFrom, tgt);
          this._wireFrom = null; this._wirePos = null;
        }
        this.release(); this.panning = false;
      };
      const dbl = (ev) => {
        const p = pos(ev); const n = this._nodeAt(p.x, p.y);
        if (n) { this.select(n); this.onEnter(n); }
        else if (this.labMode) { this.onCreateNode(this._toWorld(p.x, p.y)); }
      };
      c.addEventListener('mousedown', down);
      global.addEventListener('mousemove', move);
      global.addEventListener('mouseup', up);
      c.addEventListener('dblclick', dbl);
      c.addEventListener('touchstart', down, { passive: true });
      c.addEventListener('touchmove', move, { passive: false });
      c.addEventListener('touchend', up);
      c.addEventListener('wheel', (ev) => { ev.preventDefault(); this._userMoved = true; const p = pos(ev); this.zoomAt(ev.deltaY < 0 ? 1.1 : 0.9, p.x, p.y); }, { passive: false });
    }

    _resize() {
      const c = this.canvas;
      const W = c.clientWidth || 900, H = c.clientHeight || 640;
      c.width = Math.round(W * this.dpr);
      c.height = Math.round(H * this.dpr);
    }

    destroy() { this.stop(); global.removeEventListener('resize', this._resize); }
  }

  global.ResearchGraph = ResearchGraph;
})(window);
