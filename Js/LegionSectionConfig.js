/**
 * Legion → Section config panel.
 *
 * When the user connects the Legion squad to a section (toggle in Legion.html,
 * persisted to `skemi_legion_connections_v1`), THAT section's page grows a small
 * floating panel to (1) choose how many agents work here and (2) assign a
 * sub-task to each active agent. Saved to `skemi_legion_section_config_v1` and
 * read by the section's squad runner when it dispatches work.
 *
 * Self-contained: reads the shared roster from localStorage (falling back to the
 * same 8 defaults Legion ships), detects the current section from the filename,
 * and only renders when this section is connected. No other script depends on it.
 */
(function () {
  'use strict';

  var LS_CONN = 'skemi_legion_connections_v1';
  var LS_AGENTS = 'skemi_legion_agents_v1';
  var LS_SECTION = 'skemi_legion_section_config_v1';
  var TASK_MAX = 160;

  // Keep in sync with Legion.html's DEFAULTS (id/name/colour) so names + avatar
  // colours show even before the user edits the roster.
  var DEFAULTS = [
    { id: 'AG-ceo', name: 'Giám đốc', color: '#6E62FF' },
    { id: 'AG-pm', name: 'Quản lý dự án', color: '#3B82F6' },
    { id: 'AG-rsc', name: 'Nhà nghiên cứu', color: '#06B6D4' },
    { id: 'AG-ana', name: 'Phân tích viên', color: '#10B981' },
    { id: 'AG-sol', name: 'Kỹ sư giải pháp', color: '#F59E0B' },
    { id: 'AG-qa', name: 'Chuyên gia kiểm chứng', color: '#EF4444' },
    { id: 'AG-cre', name: 'Chuyên viên sáng tạo', color: '#EC4899' },
    { id: 'AG-eng', name: 'Kỹ sư kỹ thuật', color: '#8B5CF6' }
  ];

  var SECTIONS = [
    { key: 'search', label: 'Tra cứu', files: ['search.html'] },
    { key: 'studio', label: 'Studio', files: ['home.html'] },
    { key: 'chat', label: 'Chat', files: ['chat.html'] },
    { key: 'lab', label: 'Phòng Lab', files: ['lab.html'] },
    { key: 'quiz', label: 'Quiz', files: ['quiz.html'] },
    { key: 'prompt', label: 'Prompt Agent', files: ['promptagent.html'] }
  ];

  function currentSection() {
    var file = (location.pathname.split('/').pop() || '').toLowerCase();
    for (var i = 0; i < SECTIONS.length; i++) {
      if (SECTIONS[i].files.indexOf(file) >= 0) return SECTIONS[i];
    }
    return null;
  }

  function readJSON(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem(key) || 'null'); return v == null ? fallback : v; }
    catch (e) { return fallback; }
  }

  function loadAgents() {
    var cfg = readJSON(LS_AGENTS, {}) || {};
    return DEFAULTS.map(function (d) {
      var c = cfg[d.id] || {};
      return { id: d.id, name: c.name || d.name, color: c.color || d.color };
    });
  }

  function initials(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  function isConnected(key) {
    var conn = readJSON(LS_CONN, {}) || {};
    return !!conn[key];
  }

  function loadSectionCfg(key) {
    var all = readJSON(LS_SECTION, {}) || {};
    var c = all[key] || {};
    return { count: typeof c.count === 'number' ? c.count : 4, assignments: c.assignments || {} };
  }

  function saveSectionCfg(key, cfg) {
    var all = readJSON(LS_SECTION, {}) || {};
    all[key] = cfg;
    try { localStorage.setItem(LS_SECTION, JSON.stringify(all)); } catch (e) {}
    try { window.dispatchEvent(new CustomEvent('skemiLegionSectionConfigChanged', { detail: { section: key, config: cfg } })); } catch (e) {}
  }

  // Public read API for the section's squad runner.
  window.SkemiLegionSection = {
    isConnected: isConnected,
    config: function (key) { return loadSectionCfg(key || (currentSection() || {}).key); },
    activeAgents: function (key) {
      key = key || (currentSection() || {}).key;
      var cfg = loadSectionCfg(key);
      var agents = loadAgents().slice(0, Math.max(1, Math.min(8, cfg.count)));
      return agents.map(function (a) { return { id: a.id, name: a.name, color: a.color, task: cfg.assignments[a.id] || '' }; });
    }
  };

  var els = {};

  function injectStyles() {
    if (document.getElementById('lgsc-styles')) return;
    var css = ''
      + '.lgsc-fab{position:fixed;left:18px;bottom:18px;z-index:9998;display:inline-flex;align-items:center;gap:8px;'
      + 'padding:11px 16px;border:none;border-radius:999px;cursor:pointer;font-family:inherit;font-weight:700;font-size:.84rem;'
      + 'color:#fff;background:linear-gradient(90deg,#22d3ee,#8b5cf6);box-shadow:0 12px 30px -8px rgba(90,60,220,.6);transition:transform .16s ease}'
      + '.lgsc-fab:hover{transform:translateY(-2px)}'
      + '.lgsc-fab .lgsc-dot{width:8px;height:8px;border-radius:50%;background:#fff;box-shadow:0 0 8px #fff}'
      + '.lgsc-panel{position:fixed;left:18px;bottom:18px;z-index:9999;width:340px;max-width:calc(100vw - 36px);max-height:78vh;overflow-y:auto;'
      + 'background:var(--bg-primary,#12131c);border:1px solid var(--border-light,rgba(255,255,255,.12));border-radius:18px;'
      + 'box-shadow:0 24px 60px -16px rgba(0,0,0,.65);animation:lgscIn .22s cubic-bezier(.2,.9,.3,1)}'
      + '@keyframes lgscIn{from{opacity:0;transform:translateY(12px) scale(.98)}to{opacity:1;transform:none}}'
      + '.lgsc-head{display:flex;align-items:center;gap:10px;padding:15px 16px;border-bottom:1px solid var(--border-light,rgba(255,255,255,.1))}'
      + '.lgsc-head .lgsc-ic{width:30px;height:30px;flex:none;display:inline-flex;align-items:center;justify-content:center;border-radius:9px;'
      + 'background:linear-gradient(135deg,#22d3ee,#8b5cf6);font-size:.9rem}'
      + '.lgsc-head b{font-size:.92rem;color:var(--text-primary,#eef0f6)}'
      + '.lgsc-head small{display:block;font-size:.72rem;color:var(--text-secondary,#9aa0aa)}'
      + '.lgsc-x{margin-left:auto;flex:none;width:28px;height:28px;border:none;border-radius:8px;cursor:pointer;'
      + 'background:rgba(255,255,255,.06);color:var(--text-secondary,#9aa0aa);font-size:.9rem}'
      + '.lgsc-body{padding:14px 16px}'
      + '.lgsc-count-row{display:flex;align-items:center;gap:12px;margin-bottom:6px}'
      + '.lgsc-count-row label{font-size:.82rem;font-weight:600;color:var(--text-primary,#e6e8ee)}'
      + '.lgsc-count-row input[type=range]{flex:1;accent-color:#8b5cf6}'
      + '.lgsc-count-val{font-weight:800;color:#8b5cf6;font-variant-numeric:tabular-nums;min-width:2ch;text-align:right}'
      + '.lgsc-hint{font-size:.74rem;color:var(--text-secondary,#9aa0aa);margin:0 0 12px;line-height:1.45}'
      + '.lgsc-agent{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-top:1px solid var(--border-light,rgba(255,255,255,.07))}'
      + '.lgsc-av{width:32px;height:32px;flex:none;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;'
      + 'font-weight:800;font-size:.78rem;color:#fff;background:var(--av,#6E62FF)}'
      + '.lgsc-agent-main{flex:1;min-width:0}'
      + '.lgsc-agent-name{font-size:.82rem;font-weight:700;color:var(--text-primary,#eef0f6);margin-bottom:5px}'
      + '.lgsc-task{width:100%;box-sizing:border-box;padding:8px 10px;border-radius:9px;font-family:inherit;font-size:.8rem;'
      + 'border:1px solid var(--border-light,rgba(255,255,255,.14));background:var(--bg-secondary,rgba(255,255,255,.04));color:var(--text-primary,#eef0f6)}'
      + '.lgsc-task:focus{outline:none;border-color:#8b5cf6;box-shadow:0 0 0 3px rgba(139,92,246,.2)}'
      + '.lgsc-foot{padding:12px 16px;border-top:1px solid var(--border-light,rgba(255,255,255,.1));font-size:.74rem;color:var(--text-secondary,#9aa0aa);display:flex;align-items:center;gap:6px}'
      + '.lgsc-saved{color:#22c55e;font-weight:700}'
      + 'body.light-mode .lgsc-panel,html[data-skemi-bg=light] .lgsc-panel{background:#fff}'
      + 'body.light-mode .lgsc-task,html[data-skemi-bg=light] .lgsc-task{background:#f5f7fb;color:#1e293b}';
    var st = document.createElement('style');
    st.id = 'lgsc-styles';
    st.textContent = css;
    document.head.appendChild(st);
  }

  var open = false;

  function renderPanel(sec) {
    var cfg = loadSectionCfg(sec.key);
    var agents = loadAgents();
    var count = Math.max(1, Math.min(8, cfg.count));

    var wrap = document.createElement('div');
    wrap.className = 'lgsc-panel';
    wrap.id = 'lgscPanel';

    var rows = agents.slice(0, count).map(function (a) {
      var task = (cfg.assignments[a.id] || '').replace(/"/g, '&quot;');
      return '<div class="lgsc-agent">'
        + '<span class="lgsc-av" style="--av:' + a.color + '">' + initials(a.name) + '</span>'
        + '<div class="lgsc-agent-main"><div class="lgsc-agent-name">' + escapeHtml(a.name) + '</div>'
        + '<input class="lgsc-task" data-aid="' + a.id + '" maxlength="' + TASK_MAX + '" placeholder="Giao việc cho agent này..." value="' + task + '"></div>'
        + '</div>';
    }).join('');

    wrap.innerHTML = ''
      + '<div class="lgsc-head"><span class="lgsc-ic">🛡️</span>'
      + '<div><b>Đội ngũ Legion</b><small>Đang phục vụ: ' + escapeHtml(sec.label) + '</small></div>'
      + '<button class="lgsc-x" id="lgscClose" aria-label="Đóng">✕</button></div>'
      + '<div class="lgsc-body">'
      + '<div class="lgsc-count-row"><label>Số agent</label>'
      + '<input type="range" id="lgscCount" min="1" max="8" value="' + count + '">'
      + '<span class="lgsc-count-val" id="lgscCountVal">' + count + '</span></div>'
      + '<p class="lgsc-hint">Phân việc cho từng agent bên dưới. Để trống thì agent tự nhận phần việc Manager chia.</p>'
      + '<div id="lgscAgents">' + rows + '</div>'
      + '</div>'
      + '<div class="lgsc-foot"><span id="lgscStatus">Tự động lưu</span></div>';

    document.body.appendChild(wrap);
    els.panel = wrap;

    wrap.querySelector('#lgscClose').addEventListener('click', function () { open = false; refresh(); });

    var countEl = wrap.querySelector('#lgscCount');
    countEl.addEventListener('input', function () {
      var n = +countEl.value;
      wrap.querySelector('#lgscCountVal').textContent = n;
      var c = loadSectionCfg(sec.key); c.count = n; saveSectionCfg(sec.key, c);
      // re-render the agent list to match the new count
      var host = wrap.querySelector('#lgscAgents');
      var cfg2 = loadSectionCfg(sec.key);
      host.innerHTML = agents.slice(0, n).map(function (a) {
        var task = (cfg2.assignments[a.id] || '').replace(/"/g, '&quot;');
        return '<div class="lgsc-agent"><span class="lgsc-av" style="--av:' + a.color + '">' + initials(a.name) + '</span>'
          + '<div class="lgsc-agent-main"><div class="lgsc-agent-name">' + escapeHtml(a.name) + '</div>'
          + '<input class="lgsc-task" data-aid="' + a.id + '" maxlength="' + TASK_MAX + '" placeholder="Giao việc cho agent này..." value="' + task + '"></div></div>';
      }).join('');
      bindTasks(sec.key);
      flashSaved();
    });

    bindTasks(sec.key);
  }

  function bindTasks(key) {
    if (!els.panel) return;
    els.panel.querySelectorAll('.lgsc-task').forEach(function (inp) {
      inp.addEventListener('change', function () {
        var c = loadSectionCfg(key);
        c.assignments[inp.dataset.aid] = inp.value.trim();
        saveSectionCfg(key, c);
        flashSaved();
      });
    });
  }

  function flashSaved() {
    if (!els.panel) return;
    var s = els.panel.querySelector('#lgscStatus');
    if (!s) return;
    s.innerHTML = '<span class="lgsc-saved">✓ Đã lưu</span>';
    clearTimeout(flashSaved._t);
    flashSaved._t = setTimeout(function () { s.textContent = 'Tự động lưu'; }, 1600);
  }

  function renderFab(sec) {
    var fab = document.createElement('button');
    fab.className = 'lgsc-fab';
    fab.id = 'lgscFab';
    fab.innerHTML = '<span class="lgsc-dot"></span> Cấu hình Legion';
    fab.addEventListener('click', function () { open = true; refresh(); });
    document.body.appendChild(fab);
    els.fab = fab;
  }

  function clearUI() {
    ['lgscPanel', 'lgscFab'].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); });
    els = {};
  }

  function refresh() {
    var sec = currentSection();
    clearUI();
    if (!sec || !isConnected(sec.key)) return;
    injectStyles();
    if (open) renderPanel(sec); else renderFab(sec);
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // React to connect/disconnect done in Legion (other tab) or here.
  window.addEventListener('storage', function (e) { if (e.key === LS_CONN || e.key === LS_AGENTS) refresh(); });
  window.addEventListener('skemiLegionConnChanged', refresh);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refresh);
  else refresh();
})();
