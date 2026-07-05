/**
 * Global Status & Notification Hub for Skemi.
 * Tracks background work across pages, keeps sidebar activity dots in sync,
 * and shows a compact toast only when the user is away from the owning page.
 */

class GlobalStatusHub {
    constructor() {
        this.pollInterval = 15000;
        this.activeJobs = new Map();
        this.runningByType = new Map();
        this.typeToLinkId = {
            computer: 'computer-link',
            browser: 'computer-link',
            search: 'search-link',
            chat: 'chat-link',
            aichat: 'chat-link',
            studio: 'mindmap-link',
            quiz: 'quiz-link',
            prompt: 'prompt-agent-link'
        };
        try {
            this.notifiedJobs = new Set(JSON.parse(localStorage.getItem('skemi_notified_jobs') || '[]'));
        } catch (e) {
            this.notifiedJobs = new Set();
        }
        // Legion squad completions surface here too (each connected section's work
        // finishes as a /api/legion/activity run). Track which runs we've announced.
        this.notifiedRuns = new Set();
        this.seenRuns = new Map();
        this.sectionMeta = {
            'tra cứu': { label: 'Tra cứu', href: 'Search.html', icon: '🔍' },
            'search': { label: 'Tra cứu', href: 'Search.html', icon: '🔍' },
            'studio': { label: 'Studio', href: 'Home.html', icon: '📓' },
            'chat': { label: 'Chat', href: '/Chat.html', icon: '💬' },
            'lab': { label: 'Phòng Lab', href: 'Lab.html', icon: '🧪' },
            'quiz': { label: 'Quiz', href: 'Quiz.html', icon: '🎮' },
            'prompt': { label: 'Prompt Agent', href: 'PromptAgent.html', icon: '⚡' },
            'legion': { label: 'Legion', href: 'Legion.html', icon: '🛡️' }
        };
        this.init();
    }

    // User-controllable master switch (Settings → Thông báo). Default ON.
    notificationsEnabled() {
        try { return localStorage.getItem('skemi_notifications_enabled') !== '0'; } catch (e) { return true; }
    }

    init() {
        this.maybeShowEnablePrompt();
        this.startPolling();
        window.skemiGlobalHub = this;
    }

    // One-time in-app prompt: ask the user to turn on completion notifications and
    // (if they accept) request the browser Notification permission for background
    // alerts. Shown once; the choice + "asked" flag persist.
    maybeShowEnablePrompt() {
        let asked;
        try { asked = localStorage.getItem('skemi_notify_prompted'); } catch (e) { asked = '1'; }
        if (asked) return;
        const show = () => {
            if (document.getElementById('skemi-notify-ask')) return;
            const box = document.createElement('div');
            box.id = 'skemi-notify-ask';
            box.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:100000;max-width:340px;padding:16px 18px;border-radius:16px;'
                + 'color:#eef1ff;background:linear-gradient(135deg,rgba(24,26,44,.98),rgba(14,16,30,.98));border:1px solid rgba(120,140,220,.4);'
                + 'box-shadow:0 20px 50px rgba(0,0,0,.5);backdrop-filter:blur(10px);font-size:.88rem;line-height:1.5;animation:gsToastIn .3s ease both;';
            box.innerHTML = '<b style="display:block;margin-bottom:6px">🔔 Bật thông báo?</b>'
                + '<div style="color:#c3c9e6;margin-bottom:12px">Skemi sẽ báo cho bạn khi AI ở một mục hoàn tất công việc — kể cả khi bạn đang ở mục khác.</div>'
                + '<div style="display:flex;gap:8px"><button id="skNotifyYes" style="flex:1;padding:9px;border:none;border-radius:10px;font-weight:700;cursor:pointer;color:#fff;background:linear-gradient(90deg,#6E62FF,#8B5CF6)">Bật</button>'
                + '<button id="skNotifyNo" style="padding:9px 14px;border:1px solid rgba(255,255,255,.2);border-radius:10px;background:transparent;color:#c3c9e6;cursor:pointer">Để sau</button></div>';
            document.body.appendChild(box);
            const done = (enabled) => {
                try {
                    localStorage.setItem('skemi_notify_prompted', '1');
                    localStorage.setItem('skemi_notifications_enabled', enabled ? '1' : '0');
                } catch (e) {}
                box.remove();
            };
            box.querySelector('#skNotifyYes').addEventListener('click', () => {
                if ('Notification' in window && Notification.permission === 'default') {
                    try { Notification.requestPermission(); } catch (e) {}
                }
                done(true);
            });
            box.querySelector('#skNotifyNo').addEventListener('click', () => done(false));
        };
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(show, 1500));
        else setTimeout(show, 1500);
    }

    startPolling() {
        this.checkStatus();
        this.checkLabAlerts();
        this.checkLegionActivity();
        this.timer = window.setInterval(() => { this.checkStatus(); this.checkLabAlerts(); this.checkLegionActivity(); }, this.pollInterval);
    }

    // Watch every section's Legion squad: when a run flips to "done", announce it.
    async checkLegionActivity() {
        if (!this.notificationsEnabled()) return;
        try {
            const base = window.SKEMI_API_BASE || '';
            const res = await fetch(`${base}/api/legion/activity`, { cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data || !data.success || !Array.isArray(data.runs)) return;
            data.runs.forEach(run => {
                const rid = String(run.run_id || '');
                if (!rid) return;
                const prev = this.seenRuns.get(rid);
                this.seenRuns.set(rid, run.status);
                if (run.status === 'done' && prev && prev !== 'done' && !this.notifiedRuns.has(rid)) {
                    this.notifiedRuns.add(rid);
                    const key = String(run.section_label || run.section || '').toLowerCase();
                    let meta = this.sectionMeta.legion;
                    for (const k in this.sectionMeta) { if (key.indexOf(k) >= 0) { meta = this.sectionMeta[k]; break; } }
                    const n = (run.agents || []).length;
                    this.announce(meta.icon + ' ' + meta.label + ' đã hoàn tất',
                        (n ? n + ' agent · ' : '') + String(run.goal || 'Công việc hoàn tất.').slice(0, 100), meta.href);
                }
            });
        } catch (e) {}
    }

    // Cross-page "Breaking News": the Lab R&D chronicle queues breakthroughs/emergencies
    // to localStorage; surface them as a toast on ANY page (except Lab, where the
    // chronicle already shows them), then mark seen so each fires once.
    checkLabAlerts() {
        // Lab.html now writes this account-scoped via loadUserData/saveUserData
        // (was a raw un-suffixed key — fixed for privacy + CloudSync); read/write
        // the same way here so the cross-page toast keeps seeing it.
        let q;
        try { q = JSON.parse((window.loadUserData && window.loadUserData('skemi_lab_alerts')) || '[]'); } catch (e) { return; }
        if (!Array.isArray(q) || !q.length) return;
        const unseen = q.filter(a => a && !a.seen);
        if (!unseen.length) return;
        const onLab = /lab\.html/i.test(window.location.pathname);
        if (!onLab) {
            const top = unseen.find(a => a.level === 'breakthrough') || unseen[0];
            const icon = top.level === 'breakthrough' ? '💥' : '🚨';
            const extra = unseen.length > 1 ? ` (+${unseen.length - 1})` : '';
            this.showToast(`${icon} Lab R&D`, `${String(top.msg || '').slice(0, 120)}${extra} — mở Phòng thí nghiệm để xem.`);
        }
        q.forEach(a => { a.seen = true; });
        try { window.saveUserData && window.saveUserData('skemi_lab_alerts', JSON.stringify(q.slice(-20))); } catch (e) {}
    }

    async checkStatus() {
        try {
            const base = window.SKEMI_API_BASE || '';
            const response = await fetch(`${base}/api/global/status`, { cache: 'no-store' });
            if (!response.ok) return;
            const data = await response.json();
            if (data && data.success && Array.isArray(data.jobs)) {
                this.processJobs(data.jobs);
            }
        } catch (err) {}
    }

    normalizeStatus(status) {
        const value = String(status || '').toLowerCase();
        if (['running', 'queued', 'starting', 'working', 'thinking', 'preview'].includes(value)) return 'running';
        if (['completed', 'complete', 'success', 'done'].includes(value)) return 'done';
        if (['failed', 'error'].includes(value)) return 'error';
        if (['stopped', 'cancelled', 'canceled'].includes(value)) return 'stopped';
        return value || 'idle';
    }

    normalizeType(type) {
        const value = String(type || '').toLowerCase();
        if (value === 'aichat') return 'chat';
        if (value === 'browser') return 'computer';
        return value || 'computer';
    }

    processJobs(jobs) {
        const currentIds = new Set();
        const nextRunningByType = new Map();

        jobs.forEach(job => {
            const id = String(job.id || '');
            if (!id) return;
            currentIds.add(id);
            const type = this.normalizeType(job.type);
            const status = this.normalizeStatus(job.status);
            const normalizedJob = { ...job, id, type, status };
            const prev = this.activeJobs.get(id);
            const isRunning = status === 'running' || status === 'queued';
            const isFinished = ['done', 'error', 'stopped'].includes(status);

            if (isRunning) {
                nextRunningByType.set(type, true);
            }
            if (isFinished && prev && !['done', 'error', 'stopped'].includes(prev.status) && !this.notifiedJobs.has(id)) {
                this.notify(normalizedJob);
                this.notifiedJobs.add(id);
                this.saveNotified();
            }
            this.activeJobs.set(id, normalizedJob);
        });

        for (const [id, job] of Array.from(this.activeJobs.entries())) {
            if (!currentIds.has(id)) {
                if (job && !['done', 'error', 'stopped', 'idle'].includes(job.status) && !this.notifiedJobs.has(id)) {
                    this.notify({ ...job, status: 'done', message: job.message || 'Task completed.' });
                    this.notifiedJobs.add(id);
                    this.saveNotified();
                }
                this.activeJobs.delete(id);
            }
        }

        this.runningByType = nextRunningByType;
        this.syncSidebarPulses();
    }

    syncSidebarPulses() {
        Object.entries(this.typeToLinkId).forEach(([type, linkId]) => {
            const el = document.getElementById(linkId);
            if (!el) return;
            const active = !!this.runningByType.get(type);
            el.classList.toggle('status-working', active);
            el.classList.toggle('ai-activity-pulse', active);
        });
    }

    pageForType(type) {
        const normalized = this.normalizeType(type);
        if (normalized === 'computer') return 'computer.html';
        if (normalized === 'search') return 'search.html';
        if (normalized === 'chat') return 'chat.html';
        if (normalized === 'quiz') return 'quiz.html';
        if (normalized === 'studio') return 'home.html';
        if (normalized === 'prompt') return 'prompt';
        return '';
    }

    isOnOwningPage(job) {
        const target = this.pageForType(job.type);
        if (!target) return false;
        return window.location.pathname.toLowerCase().includes(target) && document.visibilityState === 'visible';
    }

    notify(job) {
        if (!this.notificationsEnabled()) return;
        const title = `Skemi ${String(job.type || 'job').toUpperCase()}`;
        const body = job.message || job.description || 'Task completed.';
        const page = this.pageForType(job.type);
        const href = page ? (page.charAt(0).toUpperCase() + page.slice(1)) : '';
        this.announce(title, body, href);
    }

    // Unified announce: always shows the in-app toast (per spec — even if the user is
    // already in that section), and additionally fires a native browser notification
    // when the tab is in the background so the user sees it outside Skemi too.
    announce(title, body, href) {
        if (!this.notificationsEnabled()) return;
        if (document.visibilityState === 'hidden' && 'Notification' in window && Notification.permission === 'granted') {
            try {
                const n = new Notification(title, { body, icon: './favicon.ico', silent: false });
                n.onclick = () => { window.focus(); if (href) window.location.href = href; };
            } catch (e) {}
        }
        this.showToast(title, body, href);
    }

    showToast(title, message, href) {
        const target = href || 'Lab.html';
        try {
            let host = document.getElementById('skemi-gs-toasts');
            if (!host) {
                host = document.createElement('div');
                host.id = 'skemi-gs-toasts';
                host.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:99999;display:flex;flex-direction:column;gap:10px;max-width:340px;';
                document.body.appendChild(host);
            }
            const t = document.createElement('div');
            const isBreak = /💥|đột phá|breakthrough/i.test(title + message);
            const isDone = /hoàn tất|✓|✅/i.test(title + message);
            const edge = isBreak ? 'rgba(52,211,153,.5)' : (isDone ? 'rgba(110,98,255,.55)' : 'rgba(120,140,200,.4)');
            const grad = isBreak ? 'rgba(16,52,40,.97),rgba(8,20,16,.97)' : 'rgba(22,24,44,.97),rgba(12,14,28,.97)';
            t.style.cssText = 'cursor:pointer;padding:13px 16px;border-radius:13px;font-size:.86rem;line-height:1.45;color:#eaf2ff;'
                + 'background:linear-gradient(135deg,' + grad + ');'
                + 'border:1px solid ' + edge + ';box-shadow:0 16px 40px rgba(0,0,0,.5);'
                + 'animation:gsToastIn .3s ease both;backdrop-filter:blur(8px);';
            t.innerHTML = `<b style="display:block;margin-bottom:3px">${String(title || '')}</b>${String(message || '')}`;
            t.addEventListener('click', () => { if (target) window.location.href = target; });
            if (!document.getElementById('gs-toast-kf')) {
                const st = document.createElement('style'); st.id = 'gs-toast-kf';
                st.textContent = '@keyframes gsToastIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}';
                document.head.appendChild(st);
            }
            host.appendChild(t);
            setTimeout(() => { t.style.transition = 'opacity .4s, transform .4s'; t.style.opacity = '0'; t.style.transform = 'translateY(10px)'; setTimeout(() => t.remove(), 450); }, 9000);
        } catch (e) {}
    }

    saveNotified() {
        const list = Array.from(this.notifiedJobs).slice(-100);
        localStorage.setItem('skemi_notified_jobs', JSON.stringify(list));
    }
}

if (typeof window !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new GlobalStatusHub());
    } else {
        new GlobalStatusHub();
    }
}
