/**
 * Skills.js — cross-section "skill" registry.
 *
 * Skills are toggles configured in Settings (the "Kỹ năng & Kết nối" group) and
 * stored on the account under skemi_user_data.settings.skills. Any section reads
 * them via window.SkemiSkills to change behaviour (e.g. Legion multi-agent count,
 * shared memory between sections, Lab-everywhere). Changes broadcast live so every
 * open page reacts without a reload.
 */
(function () {
    if (window.SkemiSkills) return;

    const DEFAULTS = {
        multi_agent: false,   // let AI sections deploy a Legion of agents, not just 1
        agent_count: 4,       // default Legion size when a section parallelises
        shared_memory: true,  // pass context/results between sections
        lab_everywhere: true, // show the research-Lab launcher beyond Search
        auto_deepen: true,    // auto deep-research when confidence is low
    };

    function readProfile() {
        try { return JSON.parse(localStorage.getItem('skemi_user_data') || '{}') || {}; }
        catch { return {}; }
    }
    function readSkills() {
        const p = readProfile();
        const s = (p && p.settings && p.settings.skills) || {};
        return Object.assign({}, DEFAULTS, s);
    }

    window.SkemiSkills = {
        DEFAULTS,
        all() { return readSkills(); },
        get(key, def) {
            const s = readSkills();
            return (key in s) ? s[key] : (def !== undefined ? def : DEFAULTS[key]);
        },
        enabled(key) { return !!this.get(key); },
        agentCount() {
            if (!this.enabled('multi_agent')) return 1;
            const n = parseInt(this.get('agent_count', 4), 10);
            return Math.max(1, Math.min(16, isNaN(n) ? 4 : n));
        },
        set(key, value) {
            const p = readProfile();
            p.settings = p.settings || {};
            p.settings.skills = Object.assign({}, DEFAULTS, p.settings.skills, { [key]: value });
            try { localStorage.setItem('skemi_user_data', JSON.stringify(p)); } catch (e) {}
            // Broadcast to other tabs/pages via the shared pref-change channel.
            try { localStorage.setItem('skemi_pref_change', JSON.stringify({ key: 'skills', value: p.settings.skills, t: Date.now() })); } catch (e) {}
            window.dispatchEvent(new CustomEvent('skemiSkillsChanged', { detail: p.settings.skills }));
            // Best-effort persist to the account/back-end through the prefs layer.
            try { if (window.SkemiPrefs && window.SkemiPrefs.set) window.SkemiPrefs.set('skills', p.settings.skills); } catch (e) {}
            return p.settings.skills;
        },
    };

    // Live propagation: a skill changed in another tab → re-emit locally so any
    // section listening to skemiSkillsChanged updates immediately.
    window.addEventListener('storage', (e) => {
        if (e.key === 'skemi_user_data' || e.key === 'skemi_pref_change') {
            window.dispatchEvent(new CustomEvent('skemiSkillsChanged', { detail: readSkills() }));
        }
    });

    // ── Legion bridge ─────────────────────────────────────────────────────────
    // Any section can dispatch a task to the AI squad (the multi_agent skill). The
    // backend runs a real Manager→Workers→synthesis pipeline and returns the
    // combined result + each agent's contribution. `roster` lets the caller pass
    // the user's division of labour (who does what).
    function apiBase() {
        try {
            if (window.SKEMI_API_BASE) return String(window.SKEMI_API_BASE).replace(/\/+$/, '');
            if (location.port === '8001' || location.port === '5500' || !location.port) return 'http://127.0.0.1:8010';
        } catch (e) {}
        return '';
    }
    window.SkemiLegion = {
        // True when the user enabled the multi-agent skill.
        active() { return window.SkemiSkills && window.SkemiSkills.enabled('multi_agent'); },
        agentCount() { return window.SkemiSkills ? window.SkemiSkills.agentCount() : 1; },
        // The user's saved division of labour (Legion roster editor), used as the
        // default for every squad run so the same management style applies everywhere.
        roster() {
            const r = window.SkemiSkills ? window.SkemiSkills.get('legion_roster', []) : [];
            return Array.isArray(r) ? r.filter(Boolean) : [];
        },
        // The full named-agent org chart (name • position • system prompt • stats).
        team() {
            const a = window.SkemiSkills ? window.SkemiSkills.get('legion_agents', []) : [];
            return Array.isArray(a) ? a : [];
        },
        // Roll the tokens/tasks each agent just spent back into their saved stats so
        // Legion shows cumulative usage + efficiency per agent.
        _recordStats(result) {
            try {
                const team = this.team();
                if (!team.length) return;
                const byId = {}; team.forEach(a => { byId[a.id] = a; });
                const bump = (key, ok, toks) => {
                    const a = byId[key]; if (!a) return;
                    a.stats = a.stats || { tokens: 0, tasks: 0, ok: 0 };
                    a.stats.tokens += (toks || 0); a.stats.tasks += 1; if (ok) a.stats.ok += 1;
                };
                (result.agents || []).forEach(r => bump(r.id, r.ok, r.tokens));
                if (result.manager) bump(result.manager.id, true, result.manager.tokens);
                window.SkemiSkills && window.SkemiSkills.set('legion_agents', team);
            } catch (e) {}
        },
        async runTask(task, opts) {
            opts = opts || {};
            const agents = Math.max(2, Math.min(16, opts.agents || (window.SkemiSkills ? window.SkemiSkills.agentCount() : 4)));
            const section = opts.section || (function () { try { return (location.pathname.split('/').pop() || '').replace('.html', '').toLowerCase(); } catch (e) { return ''; } })();
            const body = { task: String(task || ''), agents, section };
            // Prefer the full named-agent team; fall back to the simple roster.
            const team = (Array.isArray(opts.team) && opts.team.length) ? opts.team : this.team();
            if (team && team.length) {
                body.agents_spec = team.map(a => ({ id: a.id, name: a.name, position: a.position, system_prompt: a.system_prompt }));
            }
            const roster = (Array.isArray(opts.roster) && opts.roster.length) ? opts.roster : this.roster();
            if (roster && roster.length) body.roster = roster;
            const res = await fetch(apiBase() + '/api/legion/run-task', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error('Legion HTTP ' + res.status);
            const data = await res.json();
            if (data && data.success) this._recordStats(data);
            return data;
        },
    };
})();
