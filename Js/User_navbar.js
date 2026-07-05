// Imports for the Firebase-based Auth ported from Skemi (2). Previously this
// file relied on Auth.js leaking signOut/auth/onAuthStateChanged onto window;
// now those live on the ES module and must be imported explicitly.
import { auth, signOut, onAuthStateChanged } from './Auth.js';
import { clearUserScopedStorage } from './UserScopedStorage.js';

const getApiBase = () => {
    if (window.SKEMI_API_BASE) return window.SKEMI_API_BASE.trim().replace(/\/+$/, '');
    if (window.location.port === '8010') {
        return window.location.origin.replace(/\/+$/, '');
    }
    if (window.location.port === '8001' || window.location.port === '5500' || !window.location.port) {
        return 'http://127.0.0.1:8010';
    }
    return '';
};
const API_BASE = getApiBase();
const apiUrl = (path) => (API_BASE ? `${API_BASE}${path}` : path);

// Mark "this unload is an in-app navigation, not a real close" — every Skemi
// section is a separate .html page, so clicking a sidebar link (or any
// same-origin link) triggers the SAME pagehide event a genuine tab close
// would. Sections that cancel in-flight AI jobs on pagehide (Search, Studio)
// check this flag first so navigating within the app never interrupts a
// generation the user just wants to check on later — only an actual close
// (or leaving the site) does. Sessionstorage persists exactly long enough:
// set synchronously on click, read synchronously in the SAME page's pagehide
// handler right before it unloads.
document.addEventListener('click', (e) => {
    const a = e.target && e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || a.target === '_blank') return;
    try {
        const url = new URL(href, window.location.href);
        if (url.origin === window.location.origin) sessionStorage.setItem('skemi_in_app_nav', '1');
    } catch (e2) { /* relative/invalid href — ignore */ }
}, true);

document.addEventListener('DOMContentLoaded', () => {
    const authButtons = document.getElementById('auth-buttons');

    // ── Extra sections injector (Arena + Skemi CLI) ─────────────────────────
    // Additive & defensive: surfaces the gamification "Arena" and "Skemi CLI"
    // workspaces as first-class nav sections on EVERY page that loads this
    // module, without editing each page's inline navbar. No-ops where the
    // containers or links are already present. Never throws.
    try {
        // Arena (gamification) is merged INTO the Quiz section, so it is NOT a
        // standalone nav entry. Only Skemi CLI is its own section.
        // Phòng Lab is a TOOL inside the Search section (not a standalone nav
        // entry) — reached from the Search hero / knowledge-map node. Legion and
        // Skemi CLI ARE their own sections.
        const EXTRA_SECTIONS = [
            { href: 'Legion.html', icon: '🛡️', label: 'Legion', id: 'legion-link' },
            // Skemi CLI = the NOVA workspace (home → create project → enter and pick
            // terminals/sessions to work with AI, Claude-Code style). That's the
            // user's own build (Workspace.html → :3000), NOT the Architect canvas.
            { href: 'Workspace.html', icon: '💻', label: 'Skemi CLI', id: 'cli-link' }
        ];
        const here = (location.pathname.split('/').pop() || '').toLowerCase();
        const shortcuts = document.querySelector('.navbar-shortcuts');
        if (shortcuts) {
            EXTRA_SECTIONS.forEach((s) => {
                if (shortcuts.querySelector(`a[href$="${s.href}"]`)) return;
                const a = document.createElement('a');
                a.href = s.href;
                a.className = 'nav-shortcut' + (here === s.href.toLowerCase() ? ' active' : '');
                a.innerHTML = `<span>${s.icon}</span><span>${s.label}</span>`;
                shortcuts.appendChild(a);
            });
        }
        const sidebar = document.querySelector('.sidebar-links');
        if (sidebar) {
            const settingsAnchor = sidebar.querySelector('a[href$="Settings.html"]');
            const settingsLi = settingsAnchor ? settingsAnchor.closest('li') : null;
            EXTRA_SECTIONS.forEach((s) => {
                if (sidebar.querySelector(`a[href$="${s.href}"]`)) return;
                const li = document.createElement('li');
                const active = here === s.href.toLowerCase() ? ' class="active"' : '';
                li.innerHTML = `<a href="${s.href}" id="${s.id}"${active}><span class="icon">${s.icon}</span><span>${s.label}</span></a>`;
                if (settingsLi) sidebar.insertBefore(li, settingsLi); else sidebar.appendChild(li);
            });
        }

        // --- Top navbar = account only ------------------------------------
        // The top bar STAYS (it holds the brand + username + login/register), but
        // the section-switch shortcuts live ONLY in the left rail — hide the top
        // duplicates so the bar is a clean account strip. (Global.css also hides
        // `.navbar-shortcuts`; this removes the runtime-injected extras too.)
        try {
            const topShortcuts = document.querySelector('.navbar-shortcuts');
            if (topShortcuts) topShortcuts.style.display = 'none';
        } catch (e) { /* never break a page */ }

        // --- Mobile hamburger ---------------------------------------------
        // The off-canvas sidebar (≤768px) had no opener, so phone users couldn't
        // navigate. Inject a hamburger into the navbar + a tap-to-close backdrop,
        // wired to the existing `.app-sidebar.mobile-open` CSS.
        const navbar = document.querySelector('.navbar');
        const appSidebar = document.getElementById('appSidebar') || document.querySelector('.app-sidebar');
        if (navbar && appSidebar && !document.getElementById('navHamburger')) {
            const burger = document.createElement('button');
            burger.id = 'navHamburger';
            burger.className = 'nav-hamburger';
            burger.type = 'button';
            burger.setAttribute('aria-label', 'Menu');
            burger.setAttribute('aria-expanded', 'false');
            burger.innerHTML = '<span>☰</span>';

            const backdrop = document.createElement('div');
            backdrop.className = 'sidebar-backdrop';

            const setOpen = (open) => {
                appSidebar.classList.toggle('mobile-open', open);
                backdrop.classList.toggle('show', open);
                burger.setAttribute('aria-expanded', open ? 'true' : 'false');
                document.body.classList.toggle('sidebar-locked', open);
            };
            burger.addEventListener('click', (e) => {
                e.stopPropagation();
                setOpen(!appSidebar.classList.contains('mobile-open'));
            });
            backdrop.addEventListener('click', () => setOpen(false));
            // Tapping a destination should close the drawer so the page is visible.
            appSidebar.addEventListener('click', (e) => {
                if (e.target.closest('a')) setOpen(false);
            });
            // Keep state sane when rotating back to desktop width.
            window.addEventListener('resize', () => {
                if (window.innerWidth > 768 && appSidebar.classList.contains('mobile-open')) setOpen(false);
            });

            navbar.insertBefore(burger, navbar.firstChild);
            document.body.appendChild(backdrop);
        }
    } catch (e) { /* nav injection must never break a page */ }
    const TEMP_LOCAL_KEYS = [
        'skemi_search_history_v1',
        'skemi_search_result_cache_v3',
        'skemi_job_notify_state_v1',
        'skemi_job_event_v3',
        'skemi_ai_working_v1',
        'skemi_ai_pending_command_v1',
        'skemi_search_last_command_v3',
        'skemi_surface_session_id_v1',
        'skemi_active_computer_session_v1',
        'skemi_active_workflow_id_v1',
        'skemi_user_data',
        'skemi_computer_mode',
        'skemi_computer_phantom_index'
    ];
    const TEMP_SESSION_KEYS = [
        'skemi_search_state_v7',
        'skemi_search_analysis_v5',
        'skemi_search_active_job_v4',
        'skemi_background_jobs_v3',
        'skemi_notebook_search_job_v3',
        'skemi_search_notebook_active',
        'skemi_search_notebook_q',
        'skemi_search_notebook_deep',
        'skemi_global_pulse_notebook'
    ];

    const clearStorageKeys = (storage, keys) => {
        if (!storage) return;
        keys.forEach((key) => {
            try { storage.removeItem(key); } catch {}
        });
    };

    const cleanupTransientWebData = async ({ redirect = false, clearAiChat = false } = {}) => {
        clearStorageKeys(window.localStorage, TEMP_LOCAL_KEYS);
        clearStorageKeys(window.sessionStorage, TEMP_SESSION_KEYS);
        if (clearAiChat) {
            try {
                window.dispatchEvent(new CustomEvent('skemi:clear-ai-chat-history', {
                    detail: { notifyBackend: true }
                }));
            } catch {}
        }
        const payload = {
            user_id: currentUser?.uid || currentUser?.email || 'default_user',
            clear_runtime: true
        };
        try {
            if (navigator.sendBeacon && !redirect) {
                const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
                navigator.sendBeacon('/end_session', blob);
                return;
            }
        } catch {}
        try {
            await fetch('/end_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                keepalive: true
            });
        } catch {}
    };
    window.SkemiCleanup = { cleanupTransientWebData };
    if (authButtons) authButtons.style.visibility = 'hidden';

    let currentUser = null;
    const t = (path, fallback = path) => window.languageManager?.t?.(path) || fallback;

    const ensureToastBridge = () => {
        if (typeof window.showToast === 'function') return;
        window.showToast = (message, type = 'info', title = null) => {
            let container = document.querySelector('.toast-container');
            if (!container) {
                container = document.createElement('div');
                container.className = 'toast-container';
                document.body.appendChild(container);
            }

            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
            const resolvedTitle = title || (type === 'success'
                ? 'Success'
                : type === 'error'
                    ? 'Error'
                    : type === 'warning'
                        ? 'Warning'
                        : 'Notice');

            toast.innerHTML = `
                <div class="toast-icon">${icon}</div>
                <div class="toast-content">
                    <div class="toast-title">${resolvedTitle}</div>
                    <div class="toast-message">${message}</div>
                </div>
                <button class="toast-close">&times;</button>
            `;
            container.appendChild(toast);

            const close = () => {
                toast.style.animation = 'fadeOutRight 0.3s forwards';
                setTimeout(() => toast.remove(), 300);
            };
            setTimeout(close, 4500);
            toast.querySelector('.toast-close')?.addEventListener('click', close);
        };
    };

    const JOB_STORE_KEY = 'skemi_background_jobs_v3';
    const RESULT_CACHE_KEY = 'skemi_search_result_cache_v3';
    const JOB_EVENT_KEY = 'skemi_job_event_v3';
    const JOB_NOTIFY_KEY = 'skemi_job_notify_state_v1';
    const MAX_JOB_ROWS = 12;
    const MAX_CACHE_ROWS = 18;
    let computerPollBackoffMs = 0;
    let nextComputerPollAt = 0;
    let computerPollingDisabled = false;
    let apiHealthProbePromise = null;
    const COMPUTER_POLL_SUCCESS_INTERVAL_MS = 12000;
    const COMPUTER_POLL_SKIP_ON_COMPUTER_PAGE_MS = 30000;
    const seenEvents = new Set();
    const runtimeJobStorage = (() => {
        try {
            return window.sessionStorage;
        } catch {
            try {
                return window.localStorage;
            } catch {
                return null;
            }
        }
    })();

    const loadJobRows = () => {
        try {
            const rows = JSON.parse(runtimeJobStorage?.getItem(JOB_STORE_KEY) || '[]');
            return Array.isArray(rows) ? rows : [];
        } catch {
            return [];
        }
    };

    const saveJobRows = (rows) => {
        const trimmed = [...(Array.isArray(rows) ? rows : [])]
            .sort((a, b) => Number(b.updatedAt || b.createdAt || 0) - Number(a.updatedAt || a.createdAt || 0))
            .slice(0, MAX_JOB_ROWS);
        runtimeJobStorage?.setItem(JOB_STORE_KEY, JSON.stringify(trimmed));
    };

    const loadResultCache = () => {
        try {
            const rows = JSON.parse(localStorage.getItem(RESULT_CACHE_KEY) || '{}');
            return rows && typeof rows === 'object' ? rows : {};
        } catch {
            return {};
        }
    };

    const saveResultCache = (cache) => {
        const entries = Object.entries(cache || {})
            .sort((a, b) => Number(b[1]?.savedAt || 0) - Number(a[1]?.savedAt || 0))
            .slice(0, MAX_CACHE_ROWS);
        localStorage.setItem(RESULT_CACHE_KEY, JSON.stringify(Object.fromEntries(entries)));
    };

    const loadNotifyState = () => {
        try {
            const rows = JSON.parse(localStorage.getItem(JOB_NOTIFY_KEY) || '{}');
            return rows && typeof rows === 'object' ? rows : {};
        } catch {
            return {};
        }
    };

    const saveNotifyState = (state) => {
        const trimmed = Object.entries(state || {})
            .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
            .slice(0, 40);
        localStorage.setItem(JOB_NOTIFY_KEY, JSON.stringify(Object.fromEntries(trimmed)));
    };

    const notificationToken = (jobId, status) => `${String(jobId || '').trim()}::${String(status || '').trim().toLowerCase()}`;
    const currentPagePath = () => String(window.location.pathname || '').toLowerCase();
    const shouldSurfaceJobNotification = (job) => {
        const path = currentPagePath();
        const context = String(job?.context || '').toLowerCase();
        if (context === 'search-page' && path.endsWith('/search.html')) return false;
        if (context === 'studio-library' && (path.endsWith('/home.html') || path === '/' || path === '')) return false;
        return true;
    };

    const wasNotified = (jobId, status) => {
        const token = notificationToken(jobId, status);
        return Boolean(token && loadNotifyState()[token]);
    };

    const markNotified = (jobId, status) => {
        const token = notificationToken(jobId, status);
        if (!token) return;
        const state = loadNotifyState();
        state[token] = Date.now();
        saveNotifyState(state);
    };

    const emitJobEvent = (payload) => {
        const eventPayload = {
            id: payload.id || `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            timestamp: Date.now(),
            ...payload
        };
        window.dispatchEvent(new CustomEvent('skemi:job-event', { detail: eventPayload }));
        localStorage.setItem(JOB_EVENT_KEY, JSON.stringify(eventPayload));
    };

    const normalizeJobToastText = (value) => {
        const text = String(value || '').trim();
        if (!text) return '';
        const quoted = text.match(/"([^"]+)"/)?.[1] || '';
        if (text.includes('Nguá')) return 'Nguon da san sang';
        if (text.includes('Tra cá')) return 'Tra cuu da xong';
        if (text.includes('Tác vụ')) return 'Tac vu bi loi';
        if (text.includes('Skemi đã tìm xong nguồn')) {
            return quoted ? `Skemi da tim xong nguon cho "${quoted}".` : 'Skemi da tim xong nguon.';
        }
        if (text.includes('Skemi đã hoàn tất phân tích')) {
            return quoted ? `Skemi da hoan tat phan tich cho "${quoted}".` : 'Skemi da hoan tat phan tich.';
        }
        if (text.includes('Skemi không thể hoàn tất tác vụ')) {
            return quoted ? `Skemi khong the hoan tat tac vu cho "${quoted}".` : 'Skemi khong the hoan tat tac vu.';
        }
        return text;
    };

    const handleJobEvent = (payload) => {
        const eventId = String(payload?.id || '');
        if (!eventId || seenEvents.has(eventId)) return;
        seenEvents.add(eventId);
        if (seenEvents.size > 40) {
            const first = seenEvents.values().next().value;
            seenEvents.delete(first);
        }
        if (payload?.message) {
            window.showToast(
                normalizeJobToastText(payload.message),
                payload.type || 'info',
                normalizeJobToastText(payload.title) || null
            );
        }
    };

    window.addEventListener('storage', (event) => {
        if (event.key !== JOB_EVENT_KEY || !event.newValue) return;
        try {
            handleJobEvent(JSON.parse(event.newValue));
        } catch {}
    });
    window.addEventListener('skemi:job-event', (event) => handleJobEvent(event?.detail));

    window.SkemiJobs = {
        register(job, meta = {}) {
            if (!job?.id) return null;
            const rows = loadJobRows();
            const nextRow = {
                id: job.id,
                requestKey: job.request_key || meta.requestKey || '',
                query: job.query || meta.query || '',
                status: job.status || meta.status || 'queued',
                context: meta.context || job.context || 'search',
                page: meta.page || '',
                kind: meta.kind || 'search_analysis',
                updatedAt: Date.now(),
                createdAt: Number(job.created_at || Date.now()),
                analysis: meta.analysis || null,
                error: ''
            };
            const filtered = rows.filter((item) => item.id !== nextRow.id);
            filtered.unshift(nextRow);
            saveJobRows(filtered);
            if (nextRow.analysis && nextRow.requestKey) {
                this.cacheResult(nextRow.requestKey, nextRow.analysis);
            }
            return nextRow;
        },
        update(jobId, patch = {}) {
            if (!jobId) return null;
            const rows = loadJobRows();
            const idx = rows.findIndex((item) => item.id === jobId);
            if (idx < 0) return null;
            rows[idx] = {
                ...rows[idx],
                ...patch,
                updatedAt: Date.now()
            };
            saveJobRows(rows);
            if (rows[idx].analysis && rows[idx].requestKey) {
                this.cacheResult(rows[idx].requestKey, rows[idx].analysis);
            }
            return rows[idx];
        },
        remove(jobId) {
            saveJobRows(loadJobRows().filter((item) => item.id !== jobId));
        },
        get(jobId) {
            return loadJobRows().find((item) => item.id === jobId) || null;
        },
        getByRequestKey(requestKey) {
            return loadJobRows().find((item) => item.requestKey === requestKey) || null;
        },
        list() {
            return loadJobRows();
        },
        cacheResult(requestKey, analysis) {
            if (!requestKey || !analysis) return;
            const cache = loadResultCache();
            cache[requestKey] = {
                requestKey,
                analysis,
                savedAt: Date.now()
            };
            saveResultCache(cache);
        },
        getCachedResult(requestKey) {
            if (!requestKey) return null;
            return loadResultCache()[requestKey] || null;
        }
    };

    let pollTimer = null;
    const pollActiveSearchJobs = async () => {
        const runningJobs = window.SkemiJobs.list().filter((item) => ['queued', 'running'].includes(String(item.status || '').toLowerCase()));
        if (!runningJobs.length) return;

        for (const job of runningJobs) {
            try {
                const response = await fetch(apiUrl(`/search/jobs/${encodeURIComponent(job.id)}`));
                if (!response.ok) continue;
                const payload = await response.json();
                if (!payload?.success || !payload?.job) continue;
                const remoteJob = payload.job;
                const updated = window.SkemiJobs.update(job.id, {
                    status: remoteJob.status || job.status,
                    analysis: remoteJob.analysis || job.analysis || null,
                    error: remoteJob.error || '',
                    requestKey: remoteJob.request_key || job.requestKey || '',
                    query: remoteJob.query || job.query || '',
                    context: remoteJob.context || job.context || 'search'
                });
                if (!updated) continue;

                const status = String(updated.status || '').toLowerCase();
                const suppressVisibleToast = !shouldSurfaceJobNotification(updated);
                if (status === 'completed' && updated.analysis) {
                    if (!wasNotified(updated.id, status)) {
                        if (suppressVisibleToast) {
                            emitJobEvent({
                                jobId: updated.id,
                                requestKey: updated.requestKey,
                                context: updated.context
                            });
                            markNotified(updated.id, status);
                            continue;
                        }
                        emitJobEvent({
                            type: 'success',
                            title: updated.context === 'studio-library' ? 'Nguồn đã sẵn sàng' : 'Tra cứu đã xong',
                            message: updated.context === 'studio-library'
                                ? `Skemi đã tìm xong nguồn cho "${updated.query}".`
                                : `Skemi đã hoàn tất phân tích cho "${updated.query}".`,
                            jobId: updated.id,
                            requestKey: updated.requestKey,
                            context: updated.context
                        });
                        markNotified(updated.id, status);
                    }
                } else if (status === 'failed') {
                    if (!wasNotified(updated.id, status)) {
                        if (suppressVisibleToast) {
                            emitJobEvent({
                                jobId: updated.id,
                                requestKey: updated.requestKey,
                                context: updated.context
                            });
                            markNotified(updated.id, status);
                            continue;
                        }
                        emitJobEvent({
                            type: 'error',
                            title: 'Tác vụ bị lỗi',
                            message: updated.error || `Skemi không thể hoàn tất tác vụ cho "${updated.query}".`,
                            jobId: updated.id,
                            requestKey: updated.requestKey,
                            context: updated.context
                        });
                        markNotified(updated.id, status);
                    }
                }
            } catch (error) {
                console.warn('Job poll failed:', error);
            }
        }
    };

    const pollActiveComputerJobs = async () => {
        const now = Date.now();
        if (now < nextComputerPollAt) return;
        if (document.visibilityState === 'hidden') return;
        if (computerPollingDisabled) return;
        const path = currentPagePath();
        const inComputerPage = path.endsWith('/computer.html');
        if (inComputerPage) {
            nextComputerPollAt = Date.now() + COMPUTER_POLL_SKIP_ON_COMPUTER_PAGE_MS;
            return;
        }

        const ensureApiReachable = async () => {
            if (window.location.port === '8010') return true;
            if (apiHealthProbePromise) return apiHealthProbePromise;
            apiHealthProbePromise = (async () => {
                try {
                    const response = await fetch(apiUrl('/api/health'), {
                        cache: 'no-store',
                        headers: { 'Accept': 'application/json' }
                    });
                    return response.ok;
                } catch {
                    return false;
                } finally {
                    apiHealthProbePromise = null;
                }
            })();
            return apiHealthProbePromise;
        };

        const reachable = await ensureApiReachable();
        if (!reachable) {
            computerPollingDisabled = true;
            nextComputerPollAt = Date.now() + 60000;
            return;
        }

        try {
            const response = await fetch(apiUrl('/api/computer/status'), {
                cache: 'no-store',
                headers: { 'Accept': 'application/json' }
            });
            if (!response.ok) return;
            const payload = await response.json();
            if (!payload?.success || !Array.isArray(payload.jobs)) return;
            computerPollBackoffMs = 0;
            nextComputerPollAt = Date.now() + COMPUTER_POLL_SUCCESS_INTERVAL_MS;

            payload.jobs.forEach(job => {
                if (job.done) {
                    const status = 'completed';
                    if (!wasNotified(job.id, status)) {
                        if (inComputerPage) {
                            markNotified(job.id, status);
                            return;
                        }
                        emitJobEvent({
                            type: 'success',
                            title: 'Hoàn tất Tự động hoá',
                            message: `Mật vụ ${job.type === 'desktop' ? 'Máy tính cục bộ' : 'Trình duyệt ảo'} đã hoàn tất 100% công việc giao phó!`,
                            jobId: job.id,
                            context: 'computer'
                        });
                        markNotified(job.id, status);
                    }
                }
            });
        } catch (error) {
            computerPollBackoffMs = computerPollBackoffMs
                ? Math.min(computerPollBackoffMs * 2, 30000)
                : 4000;
            nextComputerPollAt = Date.now() + computerPollBackoffMs;
            if (computerPollBackoffMs >= 12000) {
                computerPollingDisabled = true;
                nextComputerPollAt = Date.now() + 60000;
            }
        }
    };

    ensureToastBridge();
    if (!pollTimer) {
        pollTimer = window.setInterval(() => {
            pollActiveSearchJobs().catch(() => {});
            pollActiveComputerJobs().catch(() => {});
        }, 3500);
        pollActiveSearchJobs().catch(() => {});
        pollActiveComputerJobs().catch(() => {});
    }

    const renderAuthButtons = (user) => {
        if (!authButtons) return;
        authButtons.innerHTML = '';
        authButtons.style.display = 'flex';
        authButtons.style.alignItems = 'center';
        authButtons.style.gap = '12px';

        if (!user) {
            authButtons.innerHTML = `
                <button class="btn btn-secondary" id="signupBtn">${t('auth.signup', 'Sign up')}</button>
                <button class="btn btn-primary" id="loginBtn">${t('auth.login', 'Log in')}</button>
            `;
            document.getElementById('signupBtn').onclick = () => { window.location.href = 'Register.html'; };
            document.getElementById('loginBtn').onclick = () => { window.location.href = 'Login.html'; };
            return;
        }

        const username = (user.email || 'user').split('@')[0];

        // --- Upgrade button (like ChatGPT/Gemini) -> Subscription page.
        // Hidden on the Subscription page itself and for top-tier ("skemi") users.
        let currentTier = 'free';
        try {
            const ud = (typeof window.loadUserData === 'function') ? window.loadUserData() : null;
            if (ud && ud.subscription) currentTier = String(ud.subscription).toLowerCase();
        } catch (e) { /* default free */ }
        // Expose the active tier so gating/metering code can read it app-wide.
        window.SkemiTier = currentTier;
        const onSubscriptionPage = /subscription\.html$/i.test(window.location.pathname);
        if (currentTier !== 'skemi' && !onSubscriptionPage) {
            const upgradeBtn = document.createElement('button');
            upgradeBtn.className = 'btn btn-upgrade';
            upgradeBtn.id = 'navUpgradeBtn';
            upgradeBtn.innerHTML = `<span class="upgrade-spark" aria-hidden="true">⚡</span><span>${t('nav.upgrade', 'Nâng cấp')}</span>`;
            upgradeBtn.title = t('nav.upgradeHint', 'Mở khoá toàn bộ sức mạnh của Skemi');
            upgradeBtn.onclick = () => { window.location.href = 'Subscription.html'; };
            authButtons.appendChild(upgradeBtn);
        }

        const userBtn = document.createElement('button');
        userBtn.className = 'btn btn-user-premium';
        userBtn.id = 'userProfileBtn';
        userBtn.innerHTML = `
            <span class="user-avatar-small">${username[0].toUpperCase()}</span>
            <span class="user-name-text">${username}</span>
        `;
        userBtn.title = t('auth.profileMenu', 'Right click to log out');
        authButtons.appendChild(userBtn);

        userBtn.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            document.getElementById('custom-context-menu')?.remove();

            const menu = document.createElement('div');
            menu.id = 'custom-context-menu';
            menu.className = 'custom-context-menu animate-fadeInFast';
            menu.innerHTML = `
                <div class="menu-item logout-item">
                    <span class="icon">↩</span> ${t('auth.logout', 'Log out')}
                </div>
            `;
            menu.style.position = 'fixed';
            menu.style.top = `${e.clientY}px`;
            menu.style.left = `${e.clientX}px`;
            menu.style.zIndex = '10000';
            document.body.appendChild(menu);

            let loggingOut = false;
            menu.querySelector('.logout-item').onclick = async (ev) => {
                if (loggingOut) return;            // guard repeat clicks ("nhấn liên tục")
                loggingOut = true;
                const item = ev.currentTarget;
                if (item) item.innerHTML = `<span class="icon">⏳</span> ${t('auth.loggingOut', 'Đang đăng xuất…')}`;
                // Drop THIS account's per-uid localStorage slot BEFORE signOut so the
                // next visitor on this browser can't see the previous user's data.
                try {
                    const uid = auth.currentUser?.uid;
                    if (uid) clearUserScopedStorage(uid);
                } catch (e) { /* never block logout */ }
                // Fire the transient cleanup NON-BLOCKING (sendBeacon, redirect:false) —
                // the old `await ...{redirect:true}` awaited a /end_session fetch and
                // hung logout for seconds ("siêu lâu"). Never await it now.
                try { cleanupTransientWebData({ redirect: false, clearAiChat: true }); } catch (e) {}
                // signOut is local+fast, but guard with a 1.2s race so a slow network
                // call can never hang the logout. Redirect immediately afterwards.
                try { await Promise.race([signOut(auth), new Promise((r) => setTimeout(r, 1200))]); } catch (e) {}
                window.location.replace('Login.html');
            };

            const closeMenu = () => {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            };
            setTimeout(() => document.addEventListener('click', closeMenu), 10);
        });
    };

    if (authButtons) {
        onAuthStateChanged(auth, (user) => {
            currentUser = user;
            renderAuthButtons(user);
            authButtons.style.visibility = 'visible';
        });
    }

    // Auth buttons are rendered asynchronously, so a later language switch would
    // leave them in the old language. Re-render them (translated via t()) on the
    // languageChanged event LanguageManager dispatches.
    window.addEventListener('languageChanged', () => {
        try { renderAuthButtons(currentUser); } catch (e) {}
    });

    // --- GLOBAL AI ACTIVITY MONITORING ---
    const WORKING_KEY = 'skemi_ai_working_v1';
    window.SkemiAI = {
        setWorking: (section, isActive) => {
            if (isActive) {
                localStorage.setItem(WORKING_KEY, JSON.stringify({ section, timestamp: Date.now() }));
            } else {
                const current = localStorage.getItem(WORKING_KEY);
                if (current) {
                    try {
                        const data = JSON.parse(current);
                        if (data.section === section) localStorage.removeItem(WORKING_KEY);
                    } catch { localStorage.removeItem(WORKING_KEY); }
                }
            }
            window.SkemiAI.syncSidebar();
        },
        getWorking: () => {
            const raw = localStorage.getItem(WORKING_KEY);
            if (!raw) return null;
            try { return JSON.parse(raw); } catch { return null; }
        },
        syncSidebar: () => {
            const working = window.SkemiAI.getWorking();
            const sidebarLinks = document.querySelectorAll('.sidebar-links li a, .nav-shortcut');
            const appSidebar = document.getElementById('appSidebar');

            sidebarLinks.forEach(link => {
                link.classList.remove('ai-activity-pulse');
                const href = link.getAttribute('href') || '';
                if (working) {
                    const isSectionMatch = 
                        (working.section === 'search' && href.includes('Search.html')) ||
                        (working.section === 'studio' && href.includes('Home.html')) ||
                        (working.section === 'quiz' && href.includes('Quiz.html')) ||
                        (working.section === 'chat' && href.includes('Chat.html')) ||
                        (working.section === 'studio' && link.id === 'top-studio-link') ||
                        (working.section === 'search' && link.id === 'top-search-link');

                    if (isSectionMatch) {
                        link.classList.add('ai-activity-pulse');
                        // Optional: Add a subtle indicator to the sidebar itself if collapsed
                        if (appSidebar?.classList.contains('collapsed')) {
                            appSidebar.classList.add('ai-busy');
                        }
                    }
                } else {
                    appSidebar?.classList.remove('ai-busy');
                }
            });
        }
    };

    // Auto-sync every second
    setInterval(window.SkemiAI.syncSidebar, 1000);
    window.SkemiAI.syncSidebar();
});

/* ── Global AI-squad launcher ───────────────────────────────────────────────
 * When the "multi_agent" skill is on, every section gets a floating launcher to
 * dispatch a task to a real Legion squad (manager → role workers → synthesis),
 * using the user's saved roster. Self-contained so it works on any page that
 * loads User_navbar.js — that's the cross-section "connect Legion to every
 * section" the user asked for, without editing each page.  */
(function () {
    function apiBase() {
        try {
            if (window.SKEMI_API_BASE) return String(window.SKEMI_API_BASE).replace(/\/+$/, '');
            if (location.port === '8001' || location.port === '5500' || !location.port) return 'http://127.0.0.1:8010';
        } catch (e) {}
        return '';
    }
    function skills() {
        try { return (JSON.parse(localStorage.getItem('skemi_user_data') || '{}').settings || {}).skills || {}; }
        catch (e) { return {}; }
    }
    function multiOn() { return !!skills().multi_agent; }
    function agentCount() {
        if (!multiOn()) return 1;
        const n = parseInt(skills().agent_count, 10);
        return Math.max(1, Math.min(8, isNaN(n) ? 4 : n));
    }
    function roster() {
        const r = skills().legion_roster;
        return Array.isArray(r) ? r.filter(Boolean) : [];
    }
    // The fixed 8-agent squad (mirrors Legion). Used when no saved roster exists so
    // the per-agent assignment below always has the real team.
    const DEFAULT_TEAM = [
        { id: 'AG-ceo', icon: '👑', name: 'Giám đốc', position: 'Sếp', system_prompt: 'Chỉ huy: phân rã mục tiêu và tổng hợp kết quả cả đội.' },
        { id: 'AG-pm', icon: '📋', name: 'Quản lý dự án', position: 'Quản lý', system_prompt: 'Điều phối tiến độ, phân việc, kiểm soát chất lượng.' },
        { id: 'AG-rsc', icon: '🔬', name: 'Nhà nghiên cứu', position: 'Chuyên viên', system_prompt: 'Khảo sát, thu thập và đối chiếu dữ liệu.' },
        { id: 'AG-ana', icon: '📊', name: 'Phân tích viên', position: 'Chuyên viên', system_prompt: 'Phân tích chuyên sâu, chỉ ra mấu chốt và rủi ro.' },
        { id: 'AG-sol', icon: '🛠️', name: 'Kỹ sư giải pháp', position: 'Chuyên viên', system_prompt: 'Đề xuất giải pháp khả thi, cụ thể.' },
        { id: 'AG-qa', icon: '🔍', name: 'Chuyên gia kiểm chứng', position: 'Chuyên viên', system_prompt: 'Phản biện, kiểm chứng, tìm lỗ hổng.' },
        { id: 'AG-cre', icon: '🎨', name: 'Chuyên viên sáng tạo', position: 'Chuyên viên', system_prompt: 'Góc nhìn sáng tạo, ý tưởng mới, trình bày hấp dẫn.' },
        { id: 'AG-eng', icon: '⚙️', name: 'Kỹ sư kỹ thuật', position: 'Chuyên viên', system_prompt: 'Xử lý kỹ thuật, code và tự động hoá.' }
    ];
    function team() {
        const a = skills().legion_agents;
        return (Array.isArray(a) && a.length) ? a : DEFAULT_TEAM.map(x => ({ ...x }));
    }
    // Per-section per-agent work assignments (persisted in the skill store).
    function assignments() { const s = skills(); const m = s['legion_assign_' + currentSection()]; return (m && typeof m === 'object') ? m : {}; }
    function saveAssignment(agentId, text) {
        try {
            const p = JSON.parse(localStorage.getItem('skemi_user_data') || '{}');
            p.settings = p.settings || {}; p.settings.skills = p.settings.skills || {};
            const key = 'legion_assign_' + currentSection();
            const m = (p.settings.skills[key] && typeof p.settings.skills[key] === 'object') ? p.settings.skills[key] : {};
            if (text) m[agentId] = text; else delete m[agentId];
            p.settings.skills[key] = m;
            localStorage.setItem('skemi_user_data', JSON.stringify(p));
        } catch (e) {}
    }
    // Roll spent tokens/tasks back into each named agent's saved stats.
    function recordStats(data) {
        try {
            const t = team(); if (!t.length) return;
            const by = {}; t.forEach(a => { by[a.id] = a; });
            const bump = (id, ok, tok) => { const a = by[id]; if (!a) return; a.stats = a.stats || { tokens: 0, tasks: 0, ok: 0 }; a.stats.tokens += (tok || 0); a.stats.tasks += 1; if (ok) a.stats.ok += 1; };
            (data.agents || []).forEach(r => bump(r.id, r.ok, r.tokens));
            if (data.manager) bump(data.manager.id, true, data.manager.tokens);
            const p = JSON.parse(localStorage.getItem('skemi_user_data') || '{}');
            p.settings = p.settings || {}; p.settings.skills = p.settings.skills || {}; p.settings.skills.legion_agents = t;
            localStorage.setItem('skemi_user_data', JSON.stringify(p));
            localStorage.setItem('skemi_pref_change', JSON.stringify({ key: 'skills', value: p.settings.skills, t: Date.now() }));
        } catch (e) {}
    }
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    let fab, panel;
    function ensureUI() {
        if (fab) return;
        fab = document.createElement('button');
        fab.id = 'skemiSquadFab';
        fab.title = 'Đội quân AI';
        fab.textContent = '🛡️';
        fab.style.cssText = 'position:fixed;left:18px;bottom:18px;z-index:99990;width:50px;height:50px;border-radius:50%;border:none;cursor:pointer;font-size:1.4rem;background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;box-shadow:0 10px 30px rgba(99,102,241,.45);transition:transform .15s ease;display:none;';
        fab.onmouseenter = () => fab.style.transform = 'scale(1.08)';
        fab.onmouseleave = () => fab.style.transform = 'scale(1)';
        fab.addEventListener('click', togglePanel);
        document.body.appendChild(fab);

        panel = document.createElement('div');
        panel.id = 'skemiSquadPanel';
        panel.style.cssText = 'position:fixed;left:18px;bottom:78px;z-index:99990;width:min(420px,92vw);max-height:72vh;overflow:auto;border-radius:16px;padding:16px;background:var(--bg-secondary,#11131c);border:1px solid var(--border-light,rgba(255,255,255,.14));box-shadow:0 24px 60px rgba(0,0,0,.5);color:var(--text-primary,#e8e8ea);display:none;';
        panel.innerHTML =
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><b style="font-size:.95rem">🛡️ Đội quân AI</b><button id="sqClose" style="background:none;border:none;color:inherit;cursor:pointer;font-size:1.1rem">✕</button></div>'
            + '<div style="font-size:.8rem;opacity:.7;margin-bottom:8px">Giao 1 nhiệm vụ — Chỉ huy phân rã, các tác tử (theo phân vai của bạn) chạy song song rồi tổng hợp.</div>'
            + '<textarea id="sqTask" rows="3" placeholder="Nhập nhiệm vụ cho đội quân…" style="width:100%;border-radius:10px;padding:10px;background:var(--bg-tertiary,rgba(0,0,0,.3));color:inherit;border:1px solid var(--border-light,rgba(255,255,255,.12));font-family:inherit;resize:vertical"></textarea>'
            + '<details id="sqAssignWrap" style="margin-top:10px"><summary style="cursor:pointer;font-weight:700;font-size:.85rem;color:#a5b4fc">⚙️ Phân việc cho từng agent (tuỳ chọn)</summary><div style="font-size:.74rem;opacity:.6;margin:6px 0 4px">Ghi việc riêng cho từng con — để trống thì Chỉ huy tự phân.</div><div id="sqAssign" style="display:flex;flex-direction:column;gap:7px;margin-top:6px"></div></details>'
            + '<button id="sqRun" style="margin-top:10px;width:100%;padding:11px;border:none;border-radius:10px;cursor:pointer;font-weight:700;background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff">⚡ Triển khai đội quân</button>'
            + '<div id="sqOut" style="margin-top:12px;font-size:.85rem;line-height:1.55"></div>';
        document.body.appendChild(panel);
        panel.querySelector('#sqClose').addEventListener('click', () => panel.style.display = 'none');
        panel.querySelector('#sqRun').addEventListener('click', runSquad);
    }
    // Render the per-agent assignment rows for the active (tier-capped) squad.
    function renderAssign() {
        const box = panel && panel.querySelector('#sqAssign'); if (!box) return;
        let capN = 8; try { capN = window.SkemiEntitlements ? window.SkemiEntitlements.agentCap() : 8; } catch (e) {}
        const active = team().slice(0, Math.min(agentCount(), capN || 8));
        const saved = assignments();
        box.innerHTML = active.map(a =>
            '<div style="display:flex;gap:8px;align-items:center">'
            + '<span style="width:26px;height:26px;flex:none;display:inline-flex;align-items:center;justify-content:center;border-radius:8px;background:rgba(99,102,241,.16);font-size:.9rem">' + (a.icon || '🤖') + '</span>'
            + '<div style="min-width:88px;flex:none"><div style="font-size:.76rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:96px">' + esc(a.name) + '</div><div style="font-size:.62rem;opacity:.6">' + esc(a.position) + '</div></div>'
            + '<input class="sq-assign-inp" data-aid="' + esc(a.id) + '" value="' + esc(saved[a.id] || '') + '" placeholder="Việc riêng…" style="flex:1;min-width:0;border-radius:8px;padding:6px 9px;font-size:.76rem;background:var(--bg-tertiary,rgba(0,0,0,.3));color:inherit;border:1px solid var(--border-light,rgba(255,255,255,.12));font-family:inherit">'
            + '</div>'
        ).join('');
        box.querySelectorAll('.sq-assign-inp').forEach(inp => inp.addEventListener('change', () => saveAssignment(inp.getAttribute('data-aid'), inp.value.trim())));
    }
    function togglePanel() { const show = panel.style.display === 'none'; panel.style.display = show ? 'block' : 'none'; if (show) renderAssign(); }
    async function runSquad() {
        const task = panel.querySelector('#sqTask').value.trim();
        if (!task) return;
        const out = panel.querySelector('#sqOut');
        const btn = panel.querySelector('#sqRun');
        let capN = 8; try { capN = window.SkemiEntitlements ? window.SkemiEntitlements.agentCap() : 8; } catch (e) {}
        const n = Math.max(1, Math.min(agentCount(), capN || 8));
        btn.disabled = true; btn.textContent = '⏳ Đang chạy…';
        out.innerHTML = '<span style="opacity:.6">' + n + ' tác tử đang làm việc…</span>';
        try {
            const body = { task, agents: n, section: currentSection() || 'widget' };
            const asg = assignments();
            const tm = team().slice(0, n);
            if (tm.length) body.agents_spec = tm.map(a => {
                const focus = asg[a.id];
                const sp = focus ? ((a.system_prompt || '') + '\n\nViệc cụ thể ở mục này: ' + focus) : (a.system_prompt || '');
                return { id: a.id, name: a.name, position: a.position, system_prompt: sp };
            });
            const r = roster(); if (r.length) body.roster = r;
            const res = await fetch(apiBase() + '/api/legion/run-task', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            const data = await res.json();
            if (!data || !data.success) { out.textContent = 'Đội quân chưa chạy được.'; return; }
            recordStats(data);
            const agents = (data.agents || []).map(a => '<div style="margin:6px 0;padding:8px 10px;border-radius:8px;background:var(--bg-tertiary,rgba(255,255,255,.05))"><b>🤖 ' + esc(a.name || a.id) + ' — ' + esc(a.function) + '</b><div style="opacity:.8;white-space:pre-wrap;margin-top:3px;font-size:.82rem">' + esc((a.output || '').slice(0, 500)) + '</div></div>').join('');
            out.innerHTML = '<div style="padding:10px;border-radius:10px;background:rgba(168,85,247,.12);border:1px solid rgba(168,85,247,.3)"><b>🧠 Tổng hợp</b><div style="white-space:pre-wrap;margin-top:5px">' + esc(data.result || '') + '</div></div>'
                + '<details style="margin-top:8px"><summary style="cursor:pointer;font-weight:700">Từng tác tử (' + data.workers_ok + '/' + data.worker_count + ')</summary>' + agents + '</details>';
        } catch (e) { out.textContent = 'Lỗi: ' + (e.message || e); }
        finally { btn.disabled = false; btn.textContent = '⚡ Triển khai đội quân'; }
    }
    // ── Integrated squad strip — the "other sections' UI auto-shows extra" piece.
    //    When the Đội quân AI skill is on, a connection bar is injected at the top of
    //    each section's content: team names + live "N agent đang làm ở mục này" + a
    //    button to dispatch the squad right here. This is the native-UI adaptation
    //    (beyond the floating button).
    function currentSection() {
        try { return (location.pathname.split('/').pop() || '').replace('.html', '').toLowerCase(); } catch (e) { return ''; }
    }
    function teamNames() {
        const t = team(); if (!t.length) return '';
        return t.slice(0, 4).map(a => esc(a.name)).join(' · ') + (t.length > 4 ? (' +' + (t.length - 4)) : '');
    }
    let strip, stripPoll;
    function ensureStrip() {
        if (strip) return;
        const sec = currentSection();
        if (['legion', 'login', 'register', 'settings', ''].includes(sec)) return;  // not on HQ/auth
        const host = document.querySelector('.main-content-wrapper main') || document.querySelector('.main-content-wrapper') || document.querySelector('main');
        if (!host) return;
        strip = document.createElement('div');
        strip.id = 'skemiSquadStrip';
        strip.style.cssText = 'display:none;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 14px;padding:11px 16px;border-radius:14px;background:linear-gradient(135deg,rgba(99,102,241,.15),rgba(168,85,247,.12));border:1px solid rgba(168,85,247,.32);color:var(--text-primary,#e8e8ea);font-size:.86rem;';
        const stepBtn = 'border:none;width:24px;height:24px;border-radius:7px;cursor:pointer;font-weight:800;background:rgba(255,255,255,.12);color:inherit;font-size:1rem;line-height:1';
        strip.innerHTML = '<span style="font-weight:800">🛡️ Đội quân AI</span>'
            + '<span id="sqStripTeam" style="opacity:.85"></span>'
            + '<span style="display:inline-flex;align-items:center;gap:6px;background:rgba(0,0,0,.18);padding:4px 8px;border-radius:9px" title="Số AI agent làm việc song song ở mọi mục">'
            + '<span style="font-size:.78rem;opacity:.8">Agent</span>'
            + '<button id="sqStripMinus" type="button" style="' + stepBtn + '">−</button>'
            + '<b id="sqStripN" style="min-width:18px;text-align:center;color:#22d3ee">4</b>'
            + '<button id="sqStripPlus" type="button" style="' + stepBtn + '">+</button></span>'
            + '<span id="sqStripLive" style="margin-left:auto;font-weight:700;color:#22d3ee"></span>'
            + '<button id="sqStripGo" type="button" style="border:none;border-radius:10px;padding:7px 14px;cursor:pointer;font-weight:700;background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff">⚡ Giao việc cho đội</button>'
            + '<a href="Legion.html" style="color:#22d3ee;text-decoration:none;font-weight:700">Xem chi tiết →</a>';
        host.insertBefore(strip, host.firstChild);
        // Inline agent-count stepper — adjust the squad size right here; persists to
        // the account + broadcasts so Legion + every section stay in sync.
        const writeCount = (n) => {
            n = Math.max(1, Math.min(8, n));
            try {
                const p = JSON.parse(localStorage.getItem('skemi_user_data') || '{}');
                p.settings = p.settings || {}; p.settings.skills = p.settings.skills || {};
                p.settings.skills.agent_count = n; p.settings.skills.multi_agent = true;
                localStorage.setItem('skemi_user_data', JSON.stringify(p));
                localStorage.setItem('skemi_pref_change', JSON.stringify({ key: 'skills', value: p.settings.skills, t: Date.now() }));
                window.dispatchEvent(new CustomEvent('skemiSkillsChanged', { detail: p.settings.skills }));
            } catch (e) {}
            const el = strip.querySelector('#sqStripN'); if (el) el.textContent = n;
        };
        const curCount = () => { const n = parseInt(skills().agent_count, 10); return Math.max(1, Math.min(8, isNaN(n) ? 4 : n)); };
        strip.querySelector('#sqStripMinus').addEventListener('click', () => writeCount(curCount() - 1));
        strip.querySelector('#sqStripPlus').addEventListener('click', () => writeCount(curCount() + 1));
        strip.querySelector('#sqStripGo').addEventListener('click', () => {
            ensureUI();
            // Prefill the squad task box from this section's main input if any.
            const src = document.querySelector('textarea:not(#sqTask), input[type="text"]');
            panel.style.display = 'block';
            renderAssign();
            const ti = panel.querySelector('#sqTask');
            if (ti) { if (src && src.value && !ti.value) ti.value = src.value.trim(); ti.focus(); }
        });
    }
    async function pollStrip() {
        if (!strip || strip.style.display === 'none') return;
        try {
            const r = await fetch(apiBase() + '/api/legion/activity', { cache: 'no-store' });
            const d = await r.json();
            const sec = currentSection();
            const mine = (d.runs || []).filter(x => String(x.section || '').toLowerCase() === sec && x.status === 'working');
            const n = mine.reduce((a, x) => a + (x.agents || []).filter(g => g.status === 'working').length, 0);
            const live = strip.querySelector('#sqStripLive');
            if (live) live.textContent = n ? ('🔴 ' + n + ' agent đang làm ở mục này') : '🟢 đội sẵn sàng';
        } catch (e) {}
    }
    function sync() {
        ensureUI();
        ensureStrip();
        const on = multiOn();
        fab.style.display = on ? 'inline-flex' : 'none';
        if (!on && panel) panel.style.display = 'none';
        if (strip) {
            strip.style.display = on ? 'flex' : 'none';
            const tn = strip.querySelector('#sqStripTeam');
            if (tn) tn.innerHTML = on ? ('đã kết nối mục này · ' + (teamNames() || 'đội mặc định')) : '';
            const nEl = strip.querySelector('#sqStripN');
            if (nEl) { const n = parseInt(skills().agent_count, 10); nEl.textContent = Math.max(1, Math.min(8, isNaN(n) ? 4 : n)); }
            if (on && !stripPoll) { pollStrip(); stripPoll = setInterval(pollStrip, 2500); }
            if (!on && stripPoll) { clearInterval(stripPoll); stripPoll = null; }
        }
    }
    function boot() { sync(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
    else boot();
    window.addEventListener('skemiSkillsChanged', sync);
    window.addEventListener('storage', (e) => { if (e.key === 'skemi_user_data' || e.key === 'skemi_pref_change') sync(); });
})();
