/**
 * Graph3D.js — renders the research knowledge-graph as an interactive 3D
 * constellation (Iron-Man "hologram" feel). Nodes become glowing spheres
 * positioned in 3D, edges become lines, labels float as sprites.
 *
 * Controls: drag = rotate, wheel = zoom, click a sphere = select (callback).
 * Idle = gentle auto-spin. Self-contained; uses the global THREE (r134)
 * already loaded on the Search page. Degrades gracefully if THREE is missing.
 *
 * Public API:  new Graph3D(canvas, { onSelect })
 *   .setData(nodes, edges)   nodes:[{id,label,group,body,detail,url,score}], edges:[{source,target,relation}]
 *   .select(node) · .resize() · .dispose()
 */
(function (global) {
  'use strict';
  const THREE = global.THREE;

  const GROUP_COLORS = {
    root: '#f472b6', core: '#a855f7', component: '#60a5fa', application: '#34d399',
    example: '#fbbf24', caution: '#fb7185', custom: '#22d3ee', default: '#94a3b8'
  };
  const colorFor = (g) => GROUP_COLORS[g] || GROUP_COLORS.default;

  function labelSprite(text, hex) {
    const cv = document.createElement('canvas');
    cv.width = 512; cv.height = 128;
    const ctx = cv.getContext('2d');
    ctx.font = 'bold 40px Inter, "Segoe UI", Arial, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const t = String(text || '').length > 24 ? String(text).slice(0, 23) + '…' : String(text || '');
    ctx.shadowColor = hex; ctx.shadowBlur = 16;
    ctx.fillStyle = 'rgba(255,255,255,0.97)';
    ctx.fillText(t, cv.width / 2, cv.height / 2);
    const tex = new THREE.CanvasTexture(cv); tex.minFilter = THREE.LinearFilter; tex.needsUpdate = true;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
    sp.scale.set(5.0, 1.25, 1);
    return sp;
  }

  // Fibonacci-sphere seed, then a few force-relaxation steps (repulsion + edge
  // springs) so connected concepts pull together — organic but bounded.
  function layout(nodes, edges) {
    const n = nodes.length || 1;
    const R = Math.max(14, Math.sqrt(n) * 7);
    const ga = Math.PI * (3 - Math.sqrt(5));
    nodes.forEach((nd, i) => {
      if (nd.group === 'root') { nd._p = new THREE.Vector3(0, 0, 0); nd._pin = true; return; }
      const y = 1 - (i / Math.max(1, n - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const th = ga * i;
      nd._p = new THREE.Vector3(Math.cos(th) * r * R, y * R, Math.sin(th) * r * R);
    });
    const idx = new Map(nodes.map((nd) => [nd.id, nd]));
    for (let step = 0; step < 60; step++) {
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]; if (a._pin) continue;
        const f = new THREE.Vector3();
        for (let j = 0; j < nodes.length; j++) {
          if (i === j) continue;
          const d = a._p.clone().sub(nodes[j]._p);
          const dist = Math.max(2.2, d.length());
          f.add(d.normalize().multiplyScalar(140 / (dist * dist)));
        }
        a._f = f;
      }
      edges.forEach((e) => {
        const a = idx.get(e.source && e.source.id ? e.source.id : e.source);
        const b = idx.get(e.target && e.target.id ? e.target.id : e.target);
        if (!a || !b) return;
        const d = b._p.clone().sub(a._p); const dist = d.length();
        const spring = d.normalize().multiplyScalar((dist - R * 0.7) * 0.05);
        if (!a._pin && a._f) a._f.add(spring);
        if (!b._pin && b._f) b._f.sub(spring);
      });
      nodes.forEach((nd) => {
        if (nd._pin || !nd._f) return;
        nd._p.add(nd._f.clampLength(0, 3));
        nd._p.clampLength(0, R * 1.7);
      });
    }
  }

  class Graph3D {
    constructor(canvas, opts = {}) {
      this.canvas = canvas;
      this.onSelect = opts.onSelect || (() => {});
      this.ok = !!THREE && !!canvas;
      if (!this.ok) return;
      const c = canvas;
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(52, (c.clientWidth || 800) / (c.clientHeight || 520), 0.1, 4000);
      this._zoom = 90; this.camera.position.set(0, 0, this._zoom);
      this.renderer = new THREE.WebGLRenderer({ canvas: c, alpha: true, antialias: true });
      this.renderer.setPixelRatio(Math.min(2, global.devicePixelRatio || 1));
      this.group = new THREE.Group(); this.scene.add(this.group);
      this.scene.add(new THREE.AmbientLight(0xffffff, 0.75));
      const key = new THREE.DirectionalLight(0xffffff, 0.85); key.position.set(6, 9, 12); this.scene.add(key);
      const rim = new THREE.DirectionalLight(0x8ab4ff, 0.55); rim.position.set(-9, -3, -7); this.scene.add(rim);
      this._ray = new THREE.Raycaster(); this._mouse = new THREE.Vector2();
      this.nodes = []; this.meshes = []; this.lineObj = null; this.selected = null;
      this._rot = { x: -0.25, y: 0 }; this._drag = false; this._moved = false; this._last = { x: 0, y: 0 };
      this._auto = true; this._raf = null;
      this._bind();
      this._tick = this._tick.bind(this);
      this._raf = requestAnimationFrame(this._tick);
      this.resize();
    }

    setData(nodes, edges) {
      if (!this.ok) return;
      // clear previous
      this.meshes.forEach((m) => { this.group.remove(m.mesh); this.group.remove(m.label); });
      if (this.lineObj) { this.group.remove(this.lineObj); this.lineObj = null; }
      this.meshes = []; this.nodes = nodes || [];
      if (!this.nodes.length) return;
      layout(this.nodes, edges || []);

      this.nodes.forEach((nd) => {
        const hex = colorFor(nd.group);
        const r = nd.group === 'root' ? 3.4 : (nd.group === 'core' ? 2.5 : 1.8);
        const mat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(hex), metalness: 0.4, roughness: 0.32,
          emissive: new THREE.Color(hex).multiplyScalar(0.35)
        });
        const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 30, 24), mat);
        mesh.position.copy(nd._p); mesh.userData.node = nd; mesh.userData.baseEmissive = 0.35;
        // soft halo
        const halo = new THREE.Mesh(
          new THREE.SphereGeometry(r * 1.5, 20, 16),
          new THREE.MeshBasicMaterial({ color: new THREE.Color(hex), transparent: true, opacity: 0.1, depthWrite: false })
        );
        mesh.add(halo);
        const label = labelSprite(nd.label, hex);
        label.position.copy(nd._p.clone().add(new THREE.Vector3(0, r + 1.8, 0)));
        this.group.add(mesh); this.group.add(label);
        this.meshes.push({ mesh, label, node: nd, r });
      });

      const pos = [];
      (edges || []).forEach((e) => {
        const a = this.nodes.find((x) => x.id === (e.source && e.source.id ? e.source.id : e.source));
        const b = this.nodes.find((x) => x.id === (e.target && e.target.id ? e.target.id : e.target));
        if (!a || !b) return;
        pos.push(a._p.x, a._p.y, a._p.z, b._p.x, b._p.y, b._p.z);
      });
      if (pos.length) {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
        this.lineObj = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
          color: 0x8b9dff, transparent: true, opacity: 0.28
        }));
        this.group.add(this.lineObj);
      }
      // frame the camera to the cloud
      let maxR = 16; this.nodes.forEach((nd) => { maxR = Math.max(maxR, nd._p.length()); });
      this._zoom = maxR * 2.2 + 18; this.camera.position.set(0, 0, this._zoom);
    }

    select(node) {
      this.selected = node;
      this.meshes.forEach((m) => {
        const on = m.node === node;
        m.mesh.material.emissiveIntensity = on ? 1.0 : 1.0; // keep emissive map; scale instead
        m.mesh.scale.setScalar(on ? 1.45 : 1.0);
        m.mesh.material.emissive = new THREE.Color(colorFor(m.node.group)).multiplyScalar(on ? 0.85 : 0.35);
      });
      if (node) this.onSelect(node);
    }

    _bind() {
      const c = this.canvas;
      this._onDown = (ev) => { this._drag = true; this._moved = false; this._auto = false; const p = this._pt(ev); this._last = p; };
      this._onMove = (ev) => {
        const p = this._pt(ev);
        if (this._drag) {
          const dx = p.x - this._last.x, dy = p.y - this._last.y;
          if (Math.abs(dx) + Math.abs(dy) > 3) this._moved = true;
          this._rot.y += dx * 0.005; this._rot.x += dy * 0.005;
          this._rot.x = Math.max(-1.3, Math.min(1.3, this._rot.x));
          this._last = p;
        }
      };
      this._onUp = (ev) => {
        if (this._drag && !this._moved) this._pick(ev);
        this._drag = false;
        clearTimeout(this._idleT); this._idleT = setTimeout(() => { this._auto = true; }, 3500);
      };
      this._onWheel = (ev) => { ev.preventDefault(); this._zoom = Math.max(22, Math.min(420, this._zoom + (ev.deltaY > 0 ? 8 : -8))); };
      c.addEventListener('pointerdown', this._onDown);
      global.addEventListener('pointermove', this._onMove);
      global.addEventListener('pointerup', this._onUp);
      c.addEventListener('wheel', this._onWheel, { passive: false });
    }

    _pt(ev) { const r = this.canvas.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; }

    _pick(ev) {
      const r = this.canvas.getBoundingClientRect();
      this._mouse.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
      this._mouse.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
      this._ray.setFromCamera(this._mouse, this.camera);
      const hits = this._ray.intersectObjects(this.meshes.map((m) => m.mesh), false);
      if (hits.length && hits[0].object.userData.node) this.select(hits[0].object.userData.node);
    }

    resize() {
      if (!this.ok) return;
      const c = this.canvas;
      const w = c.clientWidth || c.parentElement.clientWidth || 800;
      const h = c.clientHeight || c.parentElement.clientHeight || 520;
      this.renderer.setSize(w, h, false);
      this.camera.aspect = w / Math.max(1, h); this.camera.updateProjectionMatrix();
    }

    _tick() {
      if (!this.ok) return;
      this._raf = requestAnimationFrame(this._tick);
      if (this._auto) this._rot.y += 0.0016;
      this.group.rotation.y += (this._rot.y - this.group.rotation.y) * 0.12;
      this.group.rotation.x += (this._rot.x - this.group.rotation.x) * 0.12;
      this.camera.position.z += (this._zoom - this.camera.position.z) * 0.1;
      // keep labels facing camera scale-stable
      this.renderer.render(this.scene, this.camera);
    }

    dispose() {
      if (!this.ok) return;
      cancelAnimationFrame(this._raf);
      global.removeEventListener('pointermove', this._onMove);
      global.removeEventListener('pointerup', this._onUp);
      try { this.renderer.dispose(); } catch (e) {}
    }
  }

  global.Graph3D = Graph3D;
})(window);
