/* ComponentLab.js — 3D exploded-component viewer for a knowledge node.
 *
 * Turns an object node into a "blueprint" you can take apart: each part is a 3D
 * primitive you can EXPLODE/ASSEMBLE ("tháo / lắp"), ROTATE (drag), ZOOM (wheel) and
 * CLICK to inspect — Iron-Man-style. Self-contained; uses the global THREE (r134)
 * already loaded on the Search page. Degrades gracefully if THREE is missing.
 *
 * Public API:
 *   const lab = new ComponentLab(canvas, { onSelect(part){...} });
 *   lab.setParts(data);   // data = { object, parts:[{name,desc,shape,color,size,pos}] }
 *   lab.explode(true|false);  lab.start();  lab.stop();  lab.dispose();
 */
(function (global) {
  'use strict';
  const THREE = global.THREE;

  function geomFor(shape, size) {
    const s = Array.isArray(size) ? size : [1, 1, 1];
    const w = Math.max(0.15, Math.abs(+s[0] || 1));
    const h = Math.max(0.15, Math.abs(+s[1] || 1));
    const d = Math.max(0.15, Math.abs(+s[2] || 1));
    switch (String(shape || 'box').toLowerCase()) {
      case 'cylinder': return new THREE.CylinderGeometry(w / 2, w / 2, h, 40);
      case 'sphere':   return new THREE.SphereGeometry(Math.max(w, h, d) / 2, 36, 28);
      case 'cone':     return new THREE.ConeGeometry(w / 2, h, 40);
      case 'torus':    { const R = Math.max(w, d) / 2; return new THREE.TorusGeometry(R, Math.max(0.08, Math.min(R * 0.5, h / 2 || R * 0.3)), 20, 44); }
      default:         return new THREE.BoxGeometry(w, h, d);
    }
  }

  class ComponentLab {
    constructor(canvas, opts = {}) {
      this.canvas = canvas;
      this.onSelect = opts.onSelect || (() => {});
      this.ok = !!THREE;
      this._raf = 0;
      this._exploded = false;
      this._t = 0;                 // explode interpolation 0..1
      this._target = 0;
      this._rotX = -0.35; this._rotY = 0.6;   // current rotation
      this._velY = 0.0035;          // gentle idle auto-spin
      this._camZ = 9;
      this._parts = [];
      this._selected = null;
      this._drag = null;
      if (!this.ok) return;
      this._init();
      this._bind();
    }

    _init() {
      const c = this.canvas;
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(45, (c.clientWidth || 800) / (c.clientHeight || 500), 0.1, 100);
      this.camera.position.set(0, 0, this._camZ);
      this.renderer = new THREE.WebGLRenderer({ canvas: c, alpha: true, antialias: true });
      this.renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
      this._resize();
      this.group = new THREE.Group();
      this.scene.add(this.group);
      this.scene.add(new THREE.AmbientLight(0xffffff, 0.65));
      const key = new THREE.DirectionalLight(0xffffff, 0.9); key.position.set(4, 6, 8); this.scene.add(key);
      const rim = new THREE.DirectionalLight(0x88aaff, 0.5); rim.position.set(-6, -2, -4); this.scene.add(rim);
      this._ray = new THREE.Raycaster();
      this._mouse = new THREE.Vector2();
    }

    setParts(data) {
      if (!this.ok) return;
      // clear old
      for (const m of this._parts) {
        this.group.remove(m.mesh);
        if (m.mesh.geometry) m.mesh.geometry.dispose();
        if (m.mesh.material) m.mesh.material.dispose();
      }
      this._parts = [];
      this._selected = null;
      const parts = (data && Array.isArray(data.parts)) ? data.parts : [];
      // center of mass for radial explode direction
      let cx = 0, cy = 0, cz = 0;
      parts.forEach((p) => { const pos = p.pos || [0, 0, 0]; cx += +pos[0] || 0; cy += +pos[1] || 0; cz += +pos[2] || 0; });
      const n = Math.max(1, parts.length); cx /= n; cy /= n; cz /= n;
      parts.forEach((p, i) => {
        let col = 0x60a5fa;
        try { col = new THREE.Color(p.color || '#60a5fa').getHex(); } catch (e) {}
        const mat = new THREE.MeshStandardMaterial({ color: col, metalness: 0.35, roughness: 0.45,
          emissive: new THREE.Color(col).multiplyScalar(0.06) });
        const mesh = new THREE.Mesh(geomFor(p.shape, p.size), mat);
        // orient the part (rot in DEGREES from the model) so cylinders/tori/etc. sit right
        const rot = Array.isArray(p.rot) ? p.rot : [0, 0, 0];
        const D2R = Math.PI / 180;
        mesh.rotation.set((+rot[0] || 0) * D2R, (+rot[1] || 0) * D2R, (+rot[2] || 0) * D2R);
        const pos = p.pos || [0, (parts.length / 2 - i) * 0.8, 0];
        const assembled = new THREE.Vector3(+pos[0] || 0, +pos[1] || 0, +pos[2] || 0);
        // exploded position = pushed out radially from the center of mass
        let dir = new THREE.Vector3(assembled.x - cx, assembled.y - cy, assembled.z - cz);
        if (dir.lengthSq() < 0.001) dir = new THREE.Vector3((i % 2 ? 1 : -1), (i - n / 2) * 0.6, ((i % 3) - 1));
        dir.normalize();
        const exploded = assembled.clone().add(dir.multiplyScalar(2.6 + (i % 3) * 0.5));
        mesh.position.copy(assembled);
        mesh.userData = { index: i, name: p.name || ('Part ' + (i + 1)), desc: p.desc || '', baseColor: col };
        this.group.add(mesh);
        this._parts.push({ mesh, assembled, exploded, mat });
      });
      // frame the group
      this._fit(parts);
      return this._parts.length;
    }

    _fit(parts) {
      let r = 1;
      this._parts.forEach((p) => { r = Math.max(r, p.exploded.length()); });
      this._camZ = Math.min(20, Math.max(6, r * 2.4));
      this.camera.position.z = this._camZ;
    }

    explode(on) { this._exploded = (on == null) ? !this._exploded : !!on; this._target = this._exploded ? 1 : 0; return this._exploded; }

    select(index) {
      this._parts.forEach((p, i) => {
        const sel = (i === index);
        p.mat.emissive.setHex(sel ? 0xffffff : p.mesh.userData.baseColor);
        p.mat.emissiveIntensity = sel ? 0.5 : 0.06;
        p.mat.opacity = (index == null || sel) ? 1 : 0.35;
        p.mat.transparent = !(index == null || sel);
      });
      this._selected = index;
      const p = (index != null) ? this._parts[index] : null;
      this.onSelect(p ? p.mesh.userData : null);
    }

    _bind() {
      const c = this.canvas;
      const down = (e) => { const t = e.touches ? e.touches[0] : e; this._drag = { x: t.clientX, y: t.clientY, moved: false }; this._velY = 0; };
      const move = (e) => {
        if (!this._drag) return;
        const t = e.touches ? e.touches[0] : e;
        const dx = t.clientX - this._drag.x, dy = t.clientY - this._drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) this._drag.moved = true;
        this._rotY += dx * 0.01; this._rotX += dy * 0.01;
        this._rotX = Math.max(-1.4, Math.min(1.4, this._rotX));
        this._drag.x = t.clientX; this._drag.y = t.clientY;
        if (e.cancelable) e.preventDefault();
      };
      const up = (e) => {
        if (this._drag && !this._drag.moved) this._pick(e.changedTouches ? e.changedTouches[0] : e);
        this._drag = null;
      };
      c.addEventListener('mousedown', down);
      global.addEventListener('mousemove', move);
      global.addEventListener('mouseup', up);
      c.addEventListener('touchstart', down, { passive: true });
      c.addEventListener('touchmove', move, { passive: false });
      c.addEventListener('touchend', up);
      c.addEventListener('wheel', (e) => { e.preventDefault(); this._camZ = Math.max(3.5, Math.min(24, this._camZ + (e.deltaY > 0 ? 0.8 : -0.8))); }, { passive: false });
      this._boundResize = () => this._resize();
      global.addEventListener('resize', this._boundResize);
    }

    _pick(t) {
      if (!t || !this._parts.length) return;
      const r = this.canvas.getBoundingClientRect();
      this._mouse.x = ((t.clientX - r.left) / r.width) * 2 - 1;
      this._mouse.y = -((t.clientY - r.top) / r.height) * 2 + 1;
      this._ray.setFromCamera(this._mouse, this.camera);
      const hits = this._ray.intersectObjects(this._parts.map((p) => p.mesh));
      if (hits.length) this.select(hits[0].object.userData.index);
      else this.select(null);
    }

    _resize() {
      const c = this.canvas;
      const w = c.clientWidth || 800, h = c.clientHeight || 500;
      this.renderer.setSize(w, h, false);
      this.camera.aspect = w / Math.max(1, h);
      this.camera.updateProjectionMatrix();
    }

    _tick() {
      this._raf = global.requestAnimationFrame(() => this._tick());
      if (!this.ok) return;
      // smooth explode interpolation
      this._t += (this._target - this._t) * 0.12;
      for (const p of this._parts) {
        p.mesh.position.lerpVectors(p.assembled, p.exploded, this._t);
      }
      // idle auto-spin when not dragging
      if (!this._drag) this._rotY += this._velY;
      this.group.rotation.x = this._rotX;
      this.group.rotation.y = this._rotY;
      this.camera.position.z += (this._camZ - this.camera.position.z) * 0.15;
      this.renderer.render(this.scene, this.camera);
    }

    start() { if (this.ok && !this._raf) this._tick(); }
    stop() { if (this._raf) { global.cancelAnimationFrame(this._raf); this._raf = 0; } }

    dispose() {
      this.stop();
      if (this._boundResize) global.removeEventListener('resize', this._boundResize);
      for (const p of this._parts) {
        if (p.mesh.geometry) p.mesh.geometry.dispose();
        if (p.mesh.material) p.mesh.material.dispose();
      }
      this._parts = [];
      if (this.renderer) { try { this.renderer.dispose(); } catch (e) {} }
    }
  }

  global.ComponentLab = ComponentLab;
})(window);
