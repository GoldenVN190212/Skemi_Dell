/* Skemi Architect — vanilla architecture-canvas IDE.
   Service nodes carry rich metadata; connections are typed (HTTP/WS/PubSub); a
   DETERMINISTIC rule engine flags logic errors (Frontend→DB = red) and bottlenecks
   (missing cache = yellow). Build is gated on zero red. Reverse-engineers a
   package.json into a starter diagram. No LLM needed — the "AI checks" are rules. */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const svg = $('arSvg'), canvas = $('arCanvas');

    // ── Node catalogue ───────────────────────────────────────────────────────
    const TYPES = {
        frontend: { label: 'Frontend', ic: '🖥', color: '#22d3ee', tech: 'React', note: 'Client / UI' },
        gateway:  { label: 'API Gateway', ic: '🚪', color: '#22d3ee', tech: 'Nginx', note: 'Edge / routing' },
        api:      { label: 'API Service', ic: '⚙', color: '#a855f7', tech: 'Node/Express', note: 'Business logic' },
        worker:   { label: 'Worker', ic: '🛠', color: '#a855f7', tech: 'Node', note: 'Background jobs' },
        database: { label: 'Database', ic: '🗄', color: '#34d399', tech: 'PostgreSQL', note: 'Persistent store' },
        cache:    { label: 'Cache', ic: '⚡', color: '#fbbf24', tech: 'Redis', note: 'Hot data' },
        queue:    { label: 'Message Queue', ic: '📨', color: '#fbbf24', tech: 'RabbitMQ', note: 'Async events' },
        stripe:   { label: 'Stripe', ic: '💳', color: '#a855f7', tech: 'Stripe API', note: '3rd-party · payments', third: true },
        s3:       { label: 'S3 / Storage', ic: '🪣', color: '#34d399', tech: 'AWS S3', note: '3rd-party · objects', third: true }
    };
    const PROTOCOLS = ['http', 'ws', 'pubsub'];
    const PROTO_LABEL = { http: 'HTTP', ws: 'WebSocket', pubsub: 'PubSub' };

    // ── State ────────────────────────────────────────────────────────────────
    const KEY = 'skemi_architect_v1';
    let state = load() || { nodes: [], edges: [], seq: 1 };
    let selected = null, lastIssues = null;

    function load() { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }
    function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
    function uid(p) { return p + (state.seq++); }
    function nodeById(id) { return state.nodes.find(n => n.id === id); }
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

    // ── Palette ──────────────────────────────────────────────────────────────
    (function buildPalette() {
        $('arPalette').innerHTML = Object.keys(TYPES).map(t => {
            const T = TYPES[t];
            return `<button class="ar-pal-btn" data-add="${t}" title="Thêm ${T.label}"><span class="dot" style="background:${T.color}"></span>${T.ic} ${T.label}</button>`;
        }).join('');
        $('arPalette').querySelectorAll('[data-add]').forEach(b => b.addEventListener('click', () => addNode(b.dataset.add)));
    })();

    function addNode(type, x, y, extra) {
        const T = TYPES[type];
        const n = {
            id: uid('n'), type,
            name: (extra && extra.name) || T.label,
            tech: (extra && extra.tech) || T.tech,
            port: (extra && extra.port) || (type === 'frontend' ? 3000 : type === 'api' ? 8080 : type === 'database' ? 5432 : type === 'cache' ? 6379 : ''),
            endpoints: (extra && extra.endpoints) || (type === 'api' ? '/api/users\n/api/orders' : ''),
            schema: (extra && extra.schema) || (type === 'database' ? 'users(id, email)\norders(id, user_id, total)' : ''),
            env: (extra && extra.env) || (type === 'stripe' ? 'STRIPE_SECRET_KEY' : type === 'database' ? 'DATABASE_URL' : ''),
            x: x != null ? x : 60 + (state.nodes.length % 5) * 210,
            y: y != null ? y : 50 + Math.floor(state.nodes.length / 5) * 150
        };
        state.nodes.push(n); save(); render(); selectNode(n.id);
        return n;
    }

    // ── Rendering ────────────────────────────────────────────────────────────
    function render() {
        $('arEmpty').style.display = state.nodes.length ? 'none' : 'grid';
        // nodes
        canvas.querySelectorAll('.ar-node').forEach(e => e.remove());
        const flags = lastIssues ? lastIssues.byNode : {};
        state.nodes.forEach(n => {
            const T = TYPES[n.type] || TYPES.api;
            const el = document.createElement('div');
            el.className = 'ar-node' + (selected === n.id ? ' sel' : '') + (flags[n.id] === 'red' ? ' flag-red' : flags[n.id] === 'amber' ? ' flag-amber' : '');
            el.style.left = n.x + 'px'; el.style.top = n.y + 'px'; el.dataset.id = n.id;
            el.innerHTML =
                `<div class="ar-node-flag">!</div>` +
                `<div class="ar-node-bar"><span class="ar-node-ic" style="background:color-mix(in srgb, ${T.color} 22%, transparent);color:${T.color}">${T.ic}</span>` +
                `<span class="ar-node-title">${esc(n.name)}</span></div>` +
                `<div class="ar-node-body"><div class="ar-node-type">${esc(T.label)}</div>` +
                `<div class="row"><span>Tech</span><b>${esc(n.tech || '—')}</b></div>` +
                (n.port ? `<div class="row"><span>Port</span><b>${esc(n.port)}</b></div>` : '') +
                `</div><button class="ar-port" title="Kéo để nối sang node khác">+</button>`;
            canvas.appendChild(el);
            wireNode(el, n);
        });
        renderEdges();
    }

    function nodeCenter(n) { return { x: n.x + 90, y: n.y + 36 }; }
    function nodePort(n) { return { x: n.x + 180, y: n.y + 72 }; }

    function renderEdges() {
        const defs = svg.querySelector('defs');
        svg.innerHTML = ''; svg.appendChild(defs);
        const badSet = lastIssues ? lastIssues.badEdges : {};
        state.edges.forEach(e => {
            const a = nodeById(e.from), b = nodeById(e.to); if (!a || !b) return;
            const p1 = nodePort(a), p2 = nodeCenter(b);
            const mx = (p1.x + p2.x) / 2;
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', `M ${p1.x} ${p1.y} C ${mx} ${p1.y}, ${mx} ${p2.y}, ${p2.x} ${p2.y}`);
            path.setAttribute('class', 'ar-edge ' + (e.proto || 'http') + (badSet[e.id] ? ' bad' : ''));
            svg.appendChild(path);
            const lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            lbl.setAttribute('x', mx); lbl.setAttribute('y', (p1.y + p2.y) / 2 - 4);
            lbl.setAttribute('class', 'ar-edge-label'); lbl.setAttribute('text-anchor', 'middle');
            lbl.textContent = PROTO_LABEL[e.proto || 'http'];
            lbl.style.cursor = 'pointer'; lbl.style.pointerEvents = 'all';
            lbl.addEventListener('click', () => cycleProto(e));
            svg.appendChild(lbl);
        });
    }

    function cycleProto(e) { const i = PROTOCOLS.indexOf(e.proto || 'http'); e.proto = PROTOCOLS[(i + 1) % PROTOCOLS.length]; save(); renderEdges(); }

    // ── Drag nodes + connect via port ────────────────────────────────────────
    function wireNode(el, n) {
        const bar = el.querySelector('.ar-node-bar');
        bar.addEventListener('pointerdown', (ev) => {
            if (ev.button !== 0) return;
            selectNode(n.id);
            const sx = ev.clientX, sy = ev.clientY, ox = n.x, oy = n.y;
            el.style.cursor = 'grabbing';
            function mv(e) { n.x = Math.max(0, ox + (e.clientX - sx)); n.y = Math.max(0, oy + (e.clientY - sy)); el.style.left = n.x + 'px'; el.style.top = n.y + 'px'; renderEdges(); }
            function up() { el.style.cursor = 'grab'; save(); window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); }
            window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
        });
        el.addEventListener('click', (e) => { if (!e.target.closest('.ar-port')) selectNode(n.id); });
        // connect drag
        const port = el.querySelector('.ar-port');
        port.addEventListener('pointerdown', (ev) => {
            ev.stopPropagation();
            const tmp = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            tmp.setAttribute('class', 'ar-edge http'); svg.appendChild(tmp);
            const p1 = nodePort(n);
            function mv(e) { const r = canvas.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top; tmp.setAttribute('d', `M ${p1.x} ${p1.y} L ${x} ${y}`); }
            function up(e) {
                window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); tmp.remove();
                const tgt = document.elementFromPoint(e.clientX, e.clientY); const nodeEl = tgt && tgt.closest && tgt.closest('.ar-node');
                if (nodeEl && nodeEl.dataset.id !== n.id) {
                    const to = nodeEl.dataset.id;
                    if (!state.edges.some(x => x.from === n.id && x.to === to)) { state.edges.push({ id: uid('e'), from: n.id, to, proto: 'http' }); save(); render(); }
                }
            }
            window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
        });
    }

    // ── Inspector ────────────────────────────────────────────────────────────
    function selectNode(id) { selected = id; render(); renderInspector(); if (window.innerWidth <= 820) $('arSide').classList.add('open'); }

    function renderInspector() {
        const n = nodeById(selected), box = $('arInspector');
        if (!n) { box.innerHTML = `<div class="ar-side-empty">Chọn một node để xem &amp; sửa metadata chi tiết.</div>`; return; }
        const T = TYPES[n.type] || TYPES.api;
        box.innerHTML =
            field('Tên dịch vụ', 'name', n.name, 'input') +
            `<div class="ar-field"><label>Loại</label><input value="${esc(T.label)}" disabled></div>` +
            field('Công nghệ', 'tech', n.tech, 'input') +
            field('Port', 'port', n.port, 'input') +
            field('API Endpoints', 'endpoints', n.endpoints, 'textarea') +
            field('DB Schema', 'schema', n.schema, 'textarea') +
            field('Biến môi trường', 'env', n.env, 'textarea') +
            `<div class="ar-field ar-del"><button class="ar-act ar-ghost" style="width:100%;color:var(--ar-red)" id="arDelNode">🗑 Xoá node</button></div>`;
        box.querySelectorAll('[data-prop]').forEach(inp => inp.addEventListener('input', () => { n[inp.dataset.prop] = inp.value; save(); if (inp.dataset.prop === 'name' || inp.dataset.prop === 'tech' || inp.dataset.prop === 'port') render(); }));
        const del = $('arDelNode'); if (del) del.addEventListener('click', () => { state.nodes = state.nodes.filter(x => x.id !== n.id); state.edges = state.edges.filter(e => e.from !== n.id && e.to !== n.id); selected = null; save(); render(); renderInspector(); });
    }
    function field(label, prop, val, kind) {
        const v = esc(val == null ? '' : val);
        const ctrl = kind === 'textarea' ? `<textarea data-prop="${prop}" rows="2">${v}</textarea>` : `<input data-prop="${prop}" value="${v}">`;
        return `<div class="ar-field"><label>${label}</label>${ctrl}</div>`;
    }

    // ── Validation rule engine (deterministic "AI checks") ───────────────────
    function validate() {
        const issues = [], byNode = {}, badEdges = {};
        const out = (id) => state.edges.filter(e => e.from === id);
        const into = (id) => state.edges.filter(e => e.to === id);
        function flag(id, sev) { if (sev === 'red' || byNode[id] !== 'red') byNode[id] = sev; }

        state.edges.forEach(e => {
            const a = nodeById(e.from), b = nodeById(e.to); if (!a || !b) return;
            // RED: Frontend wired straight to a Database
            if (a.type === 'frontend' && b.type === 'database') {
                issues.push({ sev: 'red', node: a.id, msg: `"${a.name}" nối thẳng tới Database "${b.name}"`, hint: 'Frontend lộ thông tin & không kiểm soát truy cập. Phải đi qua một API Service.' });
                badEdges[e.id] = 1; flag(a.id, 'red'); flag(b.id, 'red');
            }
            // RED: Frontend → 3rd-party secret-bearing service (Stripe) directly
            if (a.type === 'frontend' && b.type === 'stripe') {
                issues.push({ sev: 'red', node: a.id, msg: `"${a.name}" gọi thẳng Stripe`, hint: 'Secret key sẽ lộ ở client. Thanh toán phải khởi tạo từ API Service.' });
                badEdges[e.id] = 1; flag(a.id, 'red');
            }
        });

        state.nodes.forEach(n => {
            // YELLOW: API reads a DB but has no Cache anywhere on its outgoing paths
            if (n.type === 'api') {
                const targets = out(n.id).map(e => nodeById(e.to)).filter(Boolean);
                const hitsDb = targets.some(t => t.type === 'database');
                const hasCache = targets.some(t => t.type === 'cache');
                if (hitsDb && !hasCache) {
                    issues.push({ sev: 'amber', node: n.id, msg: `"${n.name}" truy vấn DB không qua Cache`, hint: 'Điểm nghẽn khi tải cao — cân nhắc thêm một node Cache (Redis) trước Database.' });
                    flag(n.id, 'amber');
                }
                if (!n.port) { issues.push({ sev: 'amber', node: n.id, msg: `"${n.name}" chưa khai báo Port`, hint: 'Mỗi service cần một port rõ ràng để định tuyến.' }); flag(n.id, 'amber'); }
            }
            // YELLOW: isolated node (no connections at all)
            if (state.nodes.length > 1 && out(n.id).length === 0 && into(n.id).length === 0) {
                issues.push({ sev: 'amber', node: n.id, msg: `"${n.name}" chưa nối với gì`, hint: 'Node bị cô lập — nối nó vào kiến trúc hoặc xoá đi.' });
                flag(n.id, 'amber');
            }
            // YELLOW: a Database with no API in front (only frontends / nothing)
            if (n.type === 'database') {
                const callers = into(n.id).map(e => nodeById(e.from)).filter(Boolean);
                if (callers.length && callers.every(c => c.type === 'frontend')) {
                    /* already covered as red above */
                } else if (callers.length === 0) {
                    issues.push({ sev: 'amber', node: n.id, msg: `Database "${n.name}" không có service nào dùng`, hint: 'Không có API/Worker truy cập — DB thừa hoặc thiếu kết nối.' });
                    flag(n.id, 'amber');
                }
            }
        });

        if (!state.nodes.length) issues.push({ sev: 'amber', msg: 'Canvas trống', hint: 'Thêm vài node để bắt đầu thiết kế kiến trúc.' });

        lastIssues = { issues, byNode, badEdges, reds: issues.filter(i => i.sev === 'red').length, ambers: issues.filter(i => i.sev === 'amber').length };
        renderIssues(); render();
        return lastIssues;
    }

    function renderIssues() {
        const r = lastIssues; const box = $('arIssues'); const cnt = $('arIssueCount');
        if (!r) return;
        cnt.innerHTML = r.reds ? `<span style="color:var(--ar-red)">${r.reds} đỏ</span>` : '' + (r.ambers ? ` <span style="color:var(--ar-amber)">${r.ambers} vàng</span>` : '');
        cnt.innerHTML = (r.reds ? `<span style="color:var(--ar-red)">● ${r.reds}</span> ` : '') + (r.ambers ? `<span style="color:var(--ar-amber)">● ${r.ambers}</span>` : '') + (!r.reds && !r.ambers ? `<span style="color:var(--ar-green)">● Sạch</span>` : '');
        if (!r.issues.length) { box.innerHTML = `<div class="ar-issue ok"><span class="sev"></span><span class="txt">Không phát hiện vấn đề. Kiến trúc hợp lệ ✓</span></div>`; }
        else box.innerHTML = r.issues.map(i => `<div class="ar-issue ${i.sev === 'red' ? 'red' : 'amber'}" data-node="${i.node || ''}"><span class="sev"></span><span class="txt">${esc(i.msg)}<small>${esc(i.hint)}</small></span></div>`).join('');
        box.querySelectorAll('[data-node]').forEach(el => el.addEventListener('click', () => { if (el.dataset.node) selectNode(el.dataset.node); }));
        // gate Build on zero red
        $('arBuild').disabled = r.reds > 0;
    }

    // ── Reverse engineering: package.json → starter diagram ──────────────────
    function reverse() {
        const raw = prompt('Dán nội dung package.json (hoặc danh sách dependency) để AI dựng sơ đồ:');
        if (!raw) return;
        let deps = {};
        try { const pkg = JSON.parse(raw); deps = Object.assign({}, pkg.dependencies, pkg.devDependencies); }
        catch (e) { raw.split(/[\n,]/).forEach(s => { s = s.trim().replace(/["':\d.^~]/g, '').trim(); if (s) deps[s] = 1; }); }
        const names = Object.keys(deps).map(d => d.toLowerCase());
        const has = (re) => names.some(n => re.test(n));
        const created = [];
        const fe = addNode('frontend', 40, 60, { name: 'Web Client', tech: has(/react/) ? 'React' : has(/vue/) ? 'Vue' : has(/svelte/) ? 'Svelte' : 'SPA' }); created.push(fe);
        const api = addNode('api', 260, 60, { name: 'API', tech: has(/express/) ? 'Express' : has(/fastify/) ? 'Fastify' : has(/koa/) ? 'Koa' : has(/next/) ? 'Next.js' : 'Node' }); created.push(api);
        state.edges.push({ id: uid('e'), from: fe.id, to: api.id, proto: 'http' });
        if (has(/pg|postgres|mysql|sequelize|typeorm|prisma|mongoose|mongodb/)) { const db = addNode('database', 480, 30, { name: 'Database', tech: has(/mongo/) ? 'MongoDB' : has(/mysql/) ? 'MySQL' : 'PostgreSQL' }); created.push(db); state.edges.push({ id: uid('e'), from: api.id, to: db.id, proto: 'http' }); }
        if (has(/redis|ioredis/)) { const c = addNode('cache', 480, 170, { name: 'Cache', tech: 'Redis' }); created.push(c); state.edges.push({ id: uid('e'), from: api.id, to: c.id, proto: 'http' }); }
        if (has(/socket\.io|ws|websocket/)) { const w = addNode('worker', 260, 220, { name: 'Realtime', tech: 'Socket.io' }); created.push(w); state.edges.push({ id: uid('e'), from: fe.id, to: w.id, proto: 'ws' }); }
        if (has(/amqp|rabbit|kafka|bull|bullmq/)) { const q = addNode('queue', 480, 290, { name: 'Queue', tech: has(/kafka/) ? 'Kafka' : 'RabbitMQ' }); created.push(q); state.edges.push({ id: uid('e'), from: api.id, to: q.id, proto: 'pubsub' }); }
        if (has(/stripe/)) { const s = addNode('stripe', 700, 60, { name: 'Stripe' }); created.push(s); state.edges.push({ id: uid('e'), from: api.id, to: s.id, proto: 'http' }); }
        if (has(/aws-sdk|s3|@aws/)) { const s = addNode('s3', 700, 180, { name: 'S3' }); created.push(s); state.edges.push({ id: uid('e'), from: api.id, to: s.id, proto: 'http' }); }
        save(); render(); validate();
        toast(`Dựng ${created.length} node từ ${names.length} dependency · đã chạy Validate`);
    }

    function toast(msg) { const t = document.createElement('div'); t.className = 'ar-toast'; t.textContent = msg; document.body.appendChild(t); setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; }, 2400); setTimeout(() => t.remove(), 2900); }

    // ── Integrated terminal (xterm) — build logs alongside the canvas ────────
    let term = null, fit = null, deployed = false;
    function ensureTerm() {
        if (term || typeof Terminal === 'undefined') return term;
        term = new Terminal({ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", cursorBlink: true, theme: { background: '#0a0c12', foreground: '#cdd6f4', cyan: '#22d3ee', green: '#34d399', yellow: '#fbbf24', red: '#fb7185' }, convertEol: true, rows: 12 });
        try { fit = new FitAddon.FitAddon(); term.loadAddon(fit); } catch (e) {}
        term.open($('arTermHost'));
        try { fit && fit.fit(); } catch (e) {}
        term.write('\x1b[36mskemi-architect\x1b[0m · terminal sẵn sàng. Bấm \x1b[1mBuild\x1b[0m để xem log.\r\n');
        return term;
    }
    function openTerm(force) { const w = $('arTermWrap'); const on = force != null ? force : !w.classList.contains('open'); w.classList.toggle('open', on); if (on) { ensureTerm(); setTimeout(() => { try { fit && fit.fit(); } catch (e) {} }, 280); } }
    function tw(s) { ensureTerm(); if (term) term.write(s); }

    // ── Build (gated) → stream logs to terminal, then enable Deploy ──────────
    let building = false;
    async function build() {
        if (building) return;
        if (!lastIssues) validate();
        if (lastIssues.reds > 0) { openTerm(true); tw('\r\n\x1b[31m✖ Build bị chặn: còn ' + lastIssues.reds + ' lỗi đỏ. Sửa hết mới Build được.\x1b[0m\r\n'); toast('Còn lỗi đỏ — sửa hết mới Build được.'); return; }
        building = true; openTerm(true); ensureTerm();
        const wait = (ms) => new Promise(r => setTimeout(r, ms));
        tw('\r\n\x1b[1m$ skemi build --project\x1b[0m\r\n');
        await wait(250); tw('\x1b[2m›\x1b[0m phân tích sơ đồ kiến trúc… ' + state.nodes.length + ' node, ' + state.edges.length + ' kết nối\r\n');
        await wait(300); tw('\x1b[2m›\x1b[0m cài đặt phụ thuộc…\r\n');
        for (const n of state.nodes) { await wait(180); tw('  \x1b[32m✓\x1b[0m ' + n.name + ' \x1b[2m(' + (n.tech || '—') + (n.port ? ':' + n.port : '') + ')\x1b[0m\r\n'); }
        await wait(250); tw('\x1b[2m›\x1b[0m biên dịch & đóng gói…\r\n');
        if (lastIssues.ambers) { await wait(200); tw('  \x1b[33m⚠ ' + lastIssues.ambers + ' cảnh báo (vàng) — build vẫn chạy.\x1b[0m\r\n'); }
        await wait(400); tw('\x1b[32m\x1b[1m✓ Build hoàn tất\x1b[0m trong ' + (1.4 + Math.random()).toFixed(1) + 's. Sẵn sàng \x1b[1mDeploy\x1b[0m.\r\n');
        building = false; $('arDeploy').disabled = false; toast('✓ Build hợp lệ — có thể Deploy');
    }

    function deploy() {
        if ($('arDeploy').disabled) return;
        openTerm(true); tw('\r\n\x1b[1m$ skemi deploy --public\x1b[0m\r\n');
        tw('\x1b[2m›\x1b[0m đẩy lên môi trường public…\r\n');
        setTimeout(() => { tw('\x1b[32m✓ Live tại https://app.skemi.dev — APM bật.\x1b[0m\r\n'); deployed = true; $('arMonToggle').disabled = false; openMonitor(true); }, 900);
    }

    // ── APM real-time monitoring (charts derived from the diagram) ────────────
    const charts = {}; let monTimer = null, errTimer = null;
    function chartDefs() {
        const has = (t) => state.nodes.some(n => n.type === t);
        const defs = [{ id: 'rps', t: '⚡ Request / giây', unit: '', color: '#22d3ee', base: 120, kind: 'line' }];
        if (state.nodes.some(n => n.type === 'api')) defs.push({ id: 'lat', t: '⏱ Độ trễ p95 (ms)', unit: 'ms', color: '#a855f7', base: 80, kind: 'line' });
        if (has('database')) defs.push({ id: 'pool', t: '🗄 DB Connection Pool', unit: '', color: '#34d399', base: 18, max: 40, kind: 'bar' });
        if (has('cache')) defs.push({ id: 'cache', t: '⚡ Cache hit rate (%)', unit: '%', color: '#fbbf24', base: 92, max: 100, kind: 'line' });
        if (has('stripe')) defs.push({ id: 'rev', t: '💳 Doanh thu (Stripe, $)', unit: '$', color: '#a855f7', base: 0, kind: 'rev' });
        if (has('queue')) defs.push({ id: 'queue', t: '📨 Queue depth', unit: '', color: '#fbbf24', base: 6, kind: 'bar' });
        if (has('s3')) defs.push({ id: 's3', t: '🪣 S3 throughput (MB/s)', unit: 'MB/s', color: '#34d399', base: 14, kind: 'line' });
        return defs;
    }
    function openMonitor(force) {
        const on = force != null ? force : !$('arMonitor').classList.contains('open');
        $('arMonitor').classList.toggle('open', on);
        if (!on) { stopMonitor(); return; }
        if (!deployed) { return; }
        const defs = chartDefs();
        $('arMonCharts').innerHTML = defs.map(d => `<div class="ar-chart-card"><h4>${d.t}</h4><div class="kpi" id="kpi-${d.id}">—</div><canvas id="cv-${d.id}"></canvas></div>`).join('');
        Object.values(charts).forEach(c => { try { c.destroy(); } catch (e) {} });
        const labels = Array.from({ length: 24 }, (_, i) => '');
        defs.forEach(d => {
            const ctx = document.getElementById('cv-' + d.id); if (!ctx || typeof Chart === 'undefined') return;
            d.data = Array.from({ length: 24 }, () => d.id === 'rev' ? 0 : d.base * (0.85 + Math.random() * 0.3));
            charts[d.id] = new Chart(ctx, {
                type: d.kind === 'bar' ? 'bar' : 'line',
                data: { labels, datasets: [{ data: d.data.slice(), borderColor: d.color, backgroundColor: d.kind === 'bar' ? d.color : 'transparent', borderWidth: 2, tension: .35, pointRadius: 0, fill: false }] },
                options: { responsive: true, animation: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { ticks: { color: '#9aa0aa', font: { size: 9 } }, grid: { color: 'rgba(128,128,128,.12)' }, beginAtZero: d.id !== 'cache' } } }
            });
            charts[d.id]._def = d;
        });
        if (monTimer) clearInterval(monTimer);
        monTimer = setInterval(tickMonitor, 1500);
        if (errTimer) clearTimeout(errTimer);
        scheduleError();
        tickMonitor();
    }
    function stopMonitor() { if (monTimer) clearInterval(monTimer); if (errTimer) clearTimeout(errTimer); monTimer = errTimer = null; }
    function tickMonitor() {
        Object.values(charts).forEach(c => {
            const d = c._def; let v;
            if (d.id === 'rev') { v = (d.data[d.data.length - 1] || 0) + Math.random() * 40; }
            else { const prev = d.data[d.data.length - 1] || d.base; v = Math.max(0, prev + (Math.random() - 0.5) * d.base * 0.18); if (d.max) v = Math.min(d.max, v); }
            d.data.push(v); d.data.shift();
            c.data.datasets[0].data = d.data.slice(); c.update('none');
            const kpi = document.getElementById('kpi-' + d.id);
            if (kpi) kpi.textContent = (d.unit === '$' ? '$' : '') + Math.round(v).toLocaleString() + (d.unit && d.unit !== '$' ? ' ' + d.unit : '');
        });
    }
    // Map a runtime error (stack trace) onto the right node + offer AI quick-fix.
    const ERR_TEMPLATES = {
        database: { msg: 'ECONNREFUSED — pool exhausted', trace: 'Error: connect ECONNREFUSED\n  at Pool.query (db/pool.js:42)\n  at OrderService.list (api/orders.js:17)', fix: 'Tăng max pool size & thêm retry/back-off; cân nhắc Cache trước Database.' },
        api: { msg: 'Unhandled 500 — null deref', trace: 'TypeError: Cannot read properties of undefined\n  at handler (api/users.js:88)\n  at Layer.handle (express/router.js:95)', fix: 'Thêm guard kiểm tra null + validate payload đầu vào ở route.' },
        cache: { msg: 'Redis timeout', trace: 'ReplyError: timeout\n  at RedisClient.get (cache/redis.js:23)', fix: 'Đặt timeout + fallback đọc thẳng DB khi cache lỗi.' },
        stripe: { msg: 'Stripe 402 — card declined spike', trace: 'StripeCardError: Your card was declined\n  at Charge.create (stripe/charges.js:11)', fix: 'Thêm xử lý 402 thân thiện + cơ chế retry/alert doanh thu.' },
        frontend: { msg: 'Chunk load failed', trace: 'ChunkLoadError: Loading chunk 7 failed\n  at webpackJsonp (main.js:1)', fix: 'Bật cache-busting & retry tải chunk; kiểm tra CDN.' },
        queue: { msg: 'Consumer lag tăng', trace: 'Warning: queue depth > threshold\n  at Worker.poll (worker/index.js:30)', fix: 'Scale thêm worker hoặc tăng prefetch.' }
    };
    function scheduleError() { errTimer = setTimeout(injectError, 4000 + Math.random() * 5000); }
    function injectError() {
        if (!$('arMonitor').classList.contains('open')) return;
        const pool = state.nodes.filter(n => ERR_TEMPLATES[n.type]);
        if (pool.length) {
            const n = pool[Math.floor(Math.random() * pool.length)], tpl = ERR_TEMPLATES[n.type];
            const feed = $('arErrFeed'); if (feed.querySelector('.ar-mon-empty')) feed.innerHTML = '';
            const el = document.createElement('div'); el.className = 'ar-err';
            el.innerHTML = `<div class="top"><span class="node-tag">${esc(n.name)}</span><b style="color:var(--ar-red)">${esc(tpl.msg)}</b></div>` +
                `<div class="trace">${esc(tpl.trace)}</div>` +
                `<button class="fix">⚡ Sửa nhanh bằng AI</button>`;
            feed.prepend(el);
            // highlight the node on canvas
            const nodeEl = canvas.querySelector('.ar-node[data-id="' + n.id + '"]'); if (nodeEl) { nodeEl.classList.add('flag-red'); }
            el.querySelector('.fix').addEventListener('click', () => {
                el.classList.add('fixed'); el.querySelector('.fix').textContent = '✓ Đã áp dụng fix';
                const tip = document.createElement('div'); tip.className = 'trace'; tip.style.color = 'var(--ar-green)'; tip.textContent = '→ ' + tpl.fix; el.appendChild(tip);
                if (nodeEl) nodeEl.classList.remove('flag-red');
                toast('AI đã đề xuất & áp dụng fix cho "' + n.name + '"');
            });
        }
        scheduleError();
    }

    // ── Group tool (draw a labelled boundary; drag moves contained nodes) ────
    if (!state.groups) state.groups = [];
    let groupMode = false;
    function renderGroups() {
        canvas.querySelectorAll('.ar-group').forEach(e => e.remove());
        state.groups.forEach(g => {
            const el = document.createElement('div'); el.className = 'ar-group'; el.dataset.id = g.id;
            el.style.left = g.x + 'px'; el.style.top = g.y + 'px'; el.style.width = g.w + 'px'; el.style.height = g.h + 'px';
            el.innerHTML = `<div class="ar-group-label">${esc(g.name)}</div>`;
            canvas.insertBefore(el, canvas.querySelector('.ar-node') || null);
            const lbl = el.querySelector('.ar-group-label');
            lbl.style.cursor = 'grab';
            lbl.addEventListener('pointerdown', (ev) => {
                ev.stopPropagation(); const sx = ev.clientX, sy = ev.clientY, ox = g.x, oy = g.y;
                const inside = state.nodes.filter(n => n.x + 90 >= g.x && n.x + 90 <= g.x + g.w && n.y + 36 >= g.y && n.y + 36 <= g.y + g.h);
                const orig = inside.map(n => ({ n, x: n.x, y: n.y }));
                function mv(e) { const dx = e.clientX - sx, dy = e.clientY - sy; g.x = ox + dx; g.y = oy + dy; el.style.left = g.x + 'px'; el.style.top = g.y + 'px'; orig.forEach(o => { o.n.x = o.x + dx; o.n.y = o.y + dy; }); render(); renderGroups(); }
                function up() { save(); window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); }
                window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
            });
            lbl.addEventListener('dblclick', () => { if (confirm('Xoá nhóm "' + g.name + '"? (node bên trong giữ nguyên)')) { state.groups = state.groups.filter(x => x.id !== g.id); save(); renderGroups(); } });
        });
    }
    function startGroup() {
        groupMode = true; canvas.style.cursor = 'crosshair'; toast('Kéo một vùng trên canvas để tạo nhóm');
        const onDown = (ev) => {
            if (ev.target.closest('.ar-node') || ev.target.closest('.ar-monitor')) return;
            const r = canvas.getBoundingClientRect(); const sx = ev.clientX - r.left, sy = ev.clientY - r.top;
            const box = document.createElement('div'); box.className = 'ar-group'; box.style.left = sx + 'px'; box.style.top = sy + 'px'; canvas.appendChild(box);
            function mv(e) { const x = e.clientX - r.left, y = e.clientY - r.top; box.style.left = Math.min(sx, x) + 'px'; box.style.top = Math.min(sy, y) + 'px'; box.style.width = Math.abs(x - sx) + 'px'; box.style.height = Math.abs(y - sy) + 'px'; }
            function up(e) {
                window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up);
                const w = parseInt(box.style.width) || 0, h = parseInt(box.style.height) || 0; box.remove();
                if (w > 40 && h > 40) { const name = prompt('Tên nhóm (vd: Backend, Data layer):', 'Group') || 'Group'; state.groups.push({ id: uid('g'), name, x: parseInt(box.style.left) || sx, y: parseInt(box.style.top) || sy, w, h }); save(); renderGroups(); }
                groupMode = false; canvas.style.cursor = ''; canvas.removeEventListener('pointerdown', onDown);
            }
            window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
        };
        canvas.addEventListener('pointerdown', onDown, { once: true });
    }

    // ── Wire toolbar ─────────────────────────────────────────────────────────
    $('arValidate').addEventListener('click', validate);
    $('arBuild').addEventListener('click', build);
    $('arDeploy').addEventListener('click', deploy);
    $('arReverse').addEventListener('click', reverse);
    $('arGroup').addEventListener('click', startGroup);
    $('arTermToggle').addEventListener('click', () => openTerm());
    $('arMonToggle').addEventListener('click', () => openMonitor());
    $('arMonClose').addEventListener('click', () => openMonitor(false));
    $('arTermClear').addEventListener('click', () => { if (term) term.clear(); });
    $('arClear').addEventListener('click', () => { if (confirm('Xoá toàn bộ canvas?')) { state = { nodes: [], edges: [], seq: 1, groups: [] }; selected = null; lastIssues = null; deployed = false; $('arDeploy').disabled = true; $('arMonToggle').disabled = true; save(); render(); renderGroups(); renderInspector(); renderIssues(); } });

    // seed a tiny demo the first time so the canvas isn't blank
    if (!state.nodes.length && !localStorage.getItem(KEY + '_seeded')) {
        localStorage.setItem(KEY + '_seeded', '1');
        const fe = addNode('frontend', 60, 70); const api = addNode('api', 300, 70); const db = addNode('database', 540, 40);
        state.edges.push({ id: uid('e'), from: fe.id, to: api.id, proto: 'http' });
        state.edges.push({ id: uid('e'), from: api.id, to: db.id, proto: 'http' });
        selected = null; save();
    }
    render(); renderGroups(); renderInspector();
})();
