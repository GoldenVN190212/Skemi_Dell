(function () {
    const JOB_STORE_KEY = 'skemi_background_jobs_v3';
    const RESULT_CACHE_KEY = 'skemi_search_result_cache_v3';
    const JOB_EVENT_KEY = 'skemi_job_event_v3';
    const JOB_NOTIFY_KEY = 'skemi_job_notify_state_v1';
    const runtimeJobStorage = window.sessionStorage || window.localStorage;

    const readJson = (storage, key, fallback) => {
        try {
            const raw = storage?.getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch {
            return fallback;
        }
    };

    const writeJson = (storage, key, value) => {
        try {
            storage?.setItem(key, JSON.stringify(value));
        } catch {}
    };

    const loadJobs = () => Array.isArray(readJson(runtimeJobStorage, JOB_STORE_KEY, [])) ? readJson(runtimeJobStorage, JOB_STORE_KEY, []) : [];
    const saveJobs = (rows) => writeJson(runtimeJobStorage, JOB_STORE_KEY, rows);
    const loadNotifyState = () => readJson(window.localStorage, JOB_NOTIFY_KEY, {});
    const saveNotifyState = (state) => writeJson(window.localStorage, JOB_NOTIFY_KEY, state);
    const loadResultCache = () => readJson(window.localStorage, RESULT_CACHE_KEY, {});
    const saveResultCache = (state) => writeJson(window.localStorage, RESULT_CACHE_KEY, state);

    const notificationToken = (jobId, status) => `${String(jobId || '').trim()}::${String(status || '').trim().toLowerCase()}`;
    const wasNotified = (jobId, status) => Boolean(loadNotifyState()[notificationToken(jobId, status)]);
    const markNotified = (jobId, status) => {
        const token = notificationToken(jobId, status);
        if (!token) return;
        const state = loadNotifyState();
        state[token] = Date.now();
        saveNotifyState(state);
    };

    const showBridgeToast = (message, type = 'info', title = '') => {
        if (!message) return;
        if (typeof window.showToast === 'function') {
            window.showToast(title ? `${title}: ${message}` : message, type);
            return;
        }
        const existing = document.querySelector('.skemi-job-toast');
        if (existing) existing.remove();
        const toast = document.createElement('div');
        toast.className = 'skemi-job-toast';
        toast.textContent = title ? `${title}: ${message}` : message;
        toast.style.cssText = [
            'position:fixed',
            'right:24px',
            'bottom:24px',
            'z-index:99999',
            'max-width:360px',
            'padding:14px 16px',
            'border-radius:14px',
            'color:#fff',
            'font-size:14px',
            'line-height:1.45',
            'box-shadow:0 18px 40px rgba(0,0,0,0.28)',
            type === 'error'
                ? 'background:linear-gradient(135deg,#d84d6a,#a5334d)'
                : 'background:linear-gradient(135deg,#3b82f6,#7c3aed)'
        ].join(';');
        document.body.appendChild(toast);
        window.setTimeout(() => toast.remove(), 4200);
    };

    const emitJobEvent = (payload) => {
        const eventPayload = {
            id: payload.id || `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            timestamp: Date.now(),
            ...payload
        };
        window.dispatchEvent(new CustomEvent('skemi:job-event', { detail: eventPayload }));
        writeJson(window.localStorage, JOB_EVENT_KEY, eventPayload);
    };

    const updateJobRow = (jobId, patch) => {
        const rows = loadJobs();
        const index = rows.findIndex((item) => item.id === jobId);
        if (index < 0) return null;
        rows[index] = { ...rows[index], ...patch, updatedAt: Date.now() };
        saveJobs(rows);
        return rows[index];
    };

    const cacheResult = (requestKey, analysis) => {
        if (!requestKey || !analysis) return;
        const cache = loadResultCache();
        cache[requestKey] = {
            requestKey,
            analysis,
            savedAt: Date.now()
        };
        saveResultCache(cache);
    };

    const pollJobs = async () => {
        const runningJobs = loadJobs().filter((item) => ['queued', 'running'].includes(String(item.status || '').toLowerCase()));
        if (!runningJobs.length) return;

        for (const job of runningJobs) {
            try {
                const response = await fetch(`/search/jobs/${encodeURIComponent(job.id)}`);
                if (!response.ok) continue;
                const payload = await response.json();
                if (!payload?.success || !payload?.job) continue;
                const remoteJob = payload.job;
                const updated = updateJobRow(job.id, {
                    status: remoteJob.status || job.status,
                    analysis: remoteJob.analysis || job.analysis || null,
                    error: remoteJob.error || '',
                    requestKey: remoteJob.request_key || job.requestKey || '',
                    query: remoteJob.query || job.query || '',
                    context: remoteJob.context || job.context || 'search'
                });
                if (!updated) continue;

                if (updated.requestKey && updated.analysis) {
                    cacheResult(updated.requestKey, updated.analysis);
                }

                const status = String(updated.status || '').toLowerCase();
                if (status === 'completed' && updated.analysis && !wasNotified(updated.id, status)) {
                    emitJobEvent({
                        jobId: updated.id,
                        requestKey: updated.requestKey,
                        context: updated.context
                    });
                    showBridgeToast(
                        updated.context === 'studio-library'
                            ? `Skemi da xu ly xong nguon cho "${updated.query}".`
                            : `Skemi da hoan tat phan tich cho "${updated.query}".`,
                        'success',
                        updated.context === 'studio-library' ? 'Nguon da san sang' : 'Tra cuu da xong'
                    );
                    markNotified(updated.id, status);
                } else if (status === 'failed' && !wasNotified(updated.id, status)) {
                    emitJobEvent({
                        jobId: updated.id,
                        requestKey: updated.requestKey,
                        context: updated.context
                    });
                    showBridgeToast(
                        updated.error || `Skemi khong the hoan tat tac vu cho "${updated.query}".`,
                        'error',
                        'Tac vu bi loi'
                    );
                    markNotified(updated.id, status);
                }
            } catch (error) {
                console.warn('Background search notifier poll failed:', error);
            }
        }
    };

    window.setInterval(pollJobs, 3500);
    pollJobs().catch(() => {});
})();
