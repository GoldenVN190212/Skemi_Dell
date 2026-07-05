
        import { db, signOut } from './Js/Firebase_config.js';

        import { doc, getDoc, setDoc } from 'https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js';



        const tabs = document.querySelectorAll('.tab-btn');
        const authGuard = document.getElementById('authGuard');
        const settingsLayout = document.querySelector('.settings-layout');
        const logoutBtn = document.getElementById('logoutBtn');

        const panels = document.querySelectorAll('.tab-panel');

        const themeCards = document.querySelectorAll('.theme-card');

        let currentAuthUser = null;

        function collectSettingsState() {
            return {
                sound_notify: document.getElementById('soundNotifyToggle')?.checked ?? true,
                email_notify: document.getElementById('emailNotifyToggle')?.checked ?? false,
                startup_tips: document.getElementById('startupTipsToggle')?.checked ?? true,
                compact_mode: document.getElementById('compactModeToggle')?.checked ?? false,
                animations_enabled: document.getElementById('animationsToggle')?.checked ?? true,
                ai_personalize: document.getElementById('aiPersonalizeToggle')?.checked ?? true,
                theme: localStorage.getItem('skemi-theme') || 'light',
                language: localStorage.getItem('skemi_language') || 'vi',
                auto_create_desktop: document.getElementById('autoCreateDesktopToggle')?.checked ?? false,
                prefer_app: document.getElementById('preferAppToggle')?.checked ?? true
            };
        }

        function announceSettingsChanged(detail = {}) {
            window.dispatchEvent(new CustomEvent('skemiSettingsChanged', { detail }));
        }

        async function syncUserProfile(patch = {}) {

            if (!currentAuthUser) return null;

            const current = loadUserData();

            const merged = { ...current, ...patch, theme: localStorage.getItem('skemi-theme') || patch.theme || 'light', language: localStorage.getItem('skemi_language') || patch.language || 'en' };

            await setDoc(doc(db, 'users', currentAuthUser.uid), {

                username: merged.username || currentAuthUser.displayName || currentAuthUser.email?.split('@')[0] || 'Skemi user',

                email: merged.email || currentAuthUser.email || '',

                age_group: merged.age_group || 'middle',

                age_range: merged.age_range || '',

                subscription: merged.subscription || 'free',

                prompts_remaining: Number.isFinite(merged.prompts_remaining) ? merged.prompts_remaining : 10,

                uploads_remaining: Number.isFinite(merged.uploads_remaining) ? merged.uploads_remaining : 3,

                quiz_rooms_remaining: Number.isFinite(merged.quiz_rooms_remaining) ? merged.quiz_rooms_remaining : 3,

                last_prompt_reset: merged.last_prompt_reset || Date.now(),

                email_verified: currentAuthUser.emailVerified,

                theme: merged.theme,

                language: merged.language,

                linked_apps: { skemi: true, skemi_chat: true },

                settings: collectSettingsState()

            }, { merge: true });

            return merged;

        }



        async function loadRemoteSettings(user) {

            if (!user) return;

            const snap = await getDoc(doc(db, 'users', user.uid));

            if (!snap.exists()) return;

            const data = snap.data();

            if (data.theme) {

                localStorage.setItem('skemi-theme', data.theme);

                localStorage.setItem('chat-theme', data.theme);

            }

            if (data.language) {

                localStorage.setItem('skemi_language', data.language);

                if (window.languageManager && window.languageManager.currentLanguage !== data.language) {
                    window.languageManager.changeLanguage(data.language);
                } else if (window.languageManager) {
                    window.languageManager.applyLanguage();
                }

            }

            saveUserData(data);

            if (data.age_group) document.getElementById('ageTag').value = data.age_group;

            if (typeof data.age_range === 'string') document.getElementById('ageRange').value = data.age_range;

            if (data.settings) {
                applyStoredSettingsToControls(data.settings);

            }

            announceSettingsChanged({ source: 'remote-load' });

        }



        function applyTheme(theme) {

            document.body.classList.remove('dark-mode', 'galaxy-mode');
            document.body.setAttribute('data-theme', theme);
            document.documentElement.setAttribute('data-theme', theme);

            if (theme === 'dark') {

                document.body.classList.add('dark-mode');

            }

            if (theme === 'galaxy') {

                document.body.classList.add('galaxy-mode', 'dark-mode');

            }



            // Update theme toggle icon if it exists

            const themeToggle = document.getElementById('themeToggle');

            if (themeToggle) {

                const themeIcon = themeToggle.querySelector('i') || themeToggle.querySelector('span') || themeToggle;

                const isLight = theme === 'light';

                const isGalaxy = theme === 'galaxy';



                // Update icon class

                if (themeIcon.tagName === 'I') {

                    themeIcon.className = isLight ? 'fas fa-sun' : (isGalaxy ? 'fas fa-star' : 'fas fa-moon');

                } else {

                    themeIcon.innerText = isLight ? '☀️' : (isGalaxy ? '🌟' : '🌙');

                }



                // Set explicit colors

                if (isLight) {

                    themeIcon.style.color = '#000';

                    themeIcon.style.textShadow = 'none';

                } else if (isGalaxy) {

                    themeIcon.style.color = '#fff';

                    themeIcon.style.textShadow = '0 0 12px rgba(255, 255, 255, 0.8)';

                } else {

                    themeIcon.style.color = '#fff';

                    themeIcon.style.textShadow = 'none';

                }

            }

        }



        function setTheme(theme) {

            localStorage.setItem('skemi-theme', theme);

            localStorage.setItem('chat-theme', theme);

            saveUserData({
                theme,
                language: localStorage.getItem('skemi_language') || 'vi',
                settings: {
                    ...(loadUserData().settings || {}),
                    ...collectSettingsState(),
                    theme
                }
            });

            applyTheme(theme);

            themeCards.forEach(card => card.classList.toggle('active', card.dataset.theme === theme));

            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));

            announceSettingsChanged({ source: 'theme', theme });

            // Persist via SkemiPrefs (UDM) so every page restores the same theme on
            // load, and emit the cross-tab signal that Preferences.js listens for so
            // OTHER open tabs re-theme live (not only on next navigation).
            try { window.SkemiPrefs?.set('theme', theme); } catch (e) {}
            try {
                localStorage.setItem('skemi_pref_change',
                    JSON.stringify({ key: 'theme', value: theme, t: Date.now() }));
            } catch (e) {}

            void syncUserProfile({ theme });

        }



        // --- Statistics Initialization ---
        let activityChart, topicChart, timeChart;

        function readJsonStorage(key, fallback) {
            try {
                const raw = localStorage.getItem(key) ?? sessionStorage.getItem(key);
                if (!raw) return fallback;
                const parsed = JSON.parse(raw);
                return parsed ?? fallback;
            } catch {
                return fallback;
            }
        }

        function toTimestamp(value) {
            if (typeof value === 'number' && Number.isFinite(value)) return value;
            if (typeof value === 'string') {
                const numeric = Number(value);
                if (Number.isFinite(numeric) && numeric > 0) return numeric;
                const parsed = Date.parse(value);
                if (!Number.isNaN(parsed)) return parsed;
            }
            return null;
        }

        function formatMetric(value) {
            const locale = (window.languageManager?.base || 'vi') === 'vi' ? 'vi-VN' : 'en-US';
            try {
                return new Intl.NumberFormat(locale).format(Number(value) || 0);
            } catch {
                return String(value ?? 0);
            }
        }

        function getChartPalette() {
            const isDark = document.body.classList.contains('dark-mode') || document.body.classList.contains('galaxy-mode');
            return isDark
                ? {
                    text: 'rgba(241, 245, 249, 0.88)',
                    grid: 'rgba(148, 163, 184, 0.16)',
                    accent: '#a855f7',
                    accentFill: 'rgba(168, 85, 247, 0.28)',
                    accentSoft: 'rgba(168, 85, 247, 0.14)',
                    secondary: '#22d3ee',
                    secondaryFill: 'rgba(34, 211, 238, 0.12)'
                }
                : {
                    text: '#1e293b',
                    grid: 'rgba(15, 23, 42, 0.12)',
                    accent: '#7c3aed',
                    accentFill: 'rgba(124, 58, 237, 0.22)',
                    accentSoft: 'rgba(124, 58, 237, 0.10)',
                    secondary: '#0891b2',
                    secondaryFill: 'rgba(8, 145, 178, 0.12)'
                };
        }

        function getLast7DayLabels() {
            const locale = (window.languageManager?.base || 'vi') === 'vi' ? 'vi-VN' : 'en-US';
            const base = new Date();
            base.setHours(0, 0, 0, 0);
            return Array.from({ length: 7 }, (_, index) => {
                const day = new Date(base);
                day.setDate(base.getDate() - 6 + index);
                return new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(day);
            });
        }

        function collectRealStats() {
            const dayMs = 24 * 60 * 60 * 1000;
            const now = Date.now();
            const today = new Date();
            today.setHours(0, 0, 0, 0);

            const projects = readJsonStorage('skemi_studio_projects_v1', []);
            const chatHistory = readJsonStorage('skemi_ai_chat_history_v2', readJsonStorage('ai_chat_history', {}));
            const searchHistory = readJsonStorage('skemi_search_history_v1', []);
            const quizRooms = readJsonStorage('skemi_private_quiz_rooms_v1', []);

            const safeProjects = Array.isArray(projects) ? projects.filter((item) => item && typeof item === 'object') : [];
            const safeChatMessages = Array.isArray(chatHistory?.messages) ? chatHistory.messages.filter((item) => item && typeof item === 'object') : [];
            const safeSearchHistory = Array.isArray(searchHistory) ? searchHistory : [];
            const safeQuizRooms = Array.isArray(quizRooms) ? quizRooms.filter((item) => item && typeof item === 'object') : [];

            const events = [];
            let savedSources = 0;
            let notebookMessages = 0;
            let generatedOutputs = 0;

            const addEvent = (value) => {
                const timestamp = toTimestamp(value);
                if (Number.isFinite(timestamp)) events.push(timestamp);
            };

            safeProjects.forEach((project) => {
                addEvent(project.createdAt);

                const sources = Array.isArray(project?.notebook?.sources) ? project.notebook.sources : [];
                const notebookLogs = Array.isArray(project?.notebook?.messages) ? project.notebook.messages : [];

                savedSources += sources.length;
                notebookMessages += notebookLogs.length;

                notebookLogs.forEach((message) => addEvent(message?.ts || message?.timestamp || message?.createdAt));

                if (project?.workspace?.lastResult) generatedOutputs += 1;
                if (project?.builder?.lastResult) generatedOutputs += 1;
            });

            safeChatMessages.forEach((message) => addEvent(message?.timestamp || message?.createdAt));
            safeQuizRooms.forEach((room) => addEvent(room?.updatedAt || room?.createdAt));

            const activityData = Array(7).fill(0);
            const activeDays = new Set();
            const hourBuckets = Array(6).fill(0);

            events.forEach((timestamp) => {
                if (!Number.isFinite(timestamp)) return;
                const eventDate = new Date(timestamp);
                const eventDay = new Date(eventDate);
                eventDay.setHours(0, 0, 0, 0);

                const diffDays = Math.floor((today.getTime() - eventDay.getTime()) / dayMs);
                if (diffDays >= 0 && diffDays < 7) {
                    activityData[6 - diffDays] += 1;
                    activeDays.add(eventDay.getTime());
                }

                const hour = eventDate.getHours();
                const bucket = Math.min(5, Math.floor(hour / 4));
                hourBuckets[bucket] += 1;
            });

            return {
                cards: {
                    projects: safeProjects.length,
                    aiInteractions: safeChatMessages.length + notebookMessages,
                    savedSources,
                    activeDays: activeDays.size
                },
                activityLabels: getLast7DayLabels(),
                activityData,
                focusData: [
                    safeProjects.length,
                    savedSources,
                    safeSearchHistory.length,
                    safeChatMessages.length,
                    safeQuizRooms.length,
                    generatedOutputs
                ],
                timeData: hourBuckets
            };
        }

        function getStatisticsText() {
            const statsPack = settingsPack().statistics || {};
            return {
                labels: {
                    focus: statsPack.labels?.focus || ['Projects', 'Sources', 'Search', 'AI chat', 'Private quiz', 'Generated output'],
                    hours: statsPack.labels?.hours || ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00']
                },
                datasets: {
                    activity: statsPack.datasets?.activity || 'Activity',
                    focus: statsPack.datasets?.focus || 'Usage level',
                    time: statsPack.datasets?.time || 'Frequency'
                }
            };
        }

        function setChartData(chart, config) {
            chart.data.labels = config.labels;
            chart.data.datasets = config.datasets;
            chart.update();
        }

        function initStats(force = false) {
            const statsText = getStatisticsText();
            const stats = collectRealStats();
            const palette = getChartPalette();

            const projectsEl = document.getElementById('stats-projects');
            const aiEl = document.getElementById('stats-ai-interactions');
            const sourcesEl = document.getElementById('stats-sources');
            const activeDaysEl = document.getElementById('stats-active-days');

            if (projectsEl) projectsEl.textContent = formatMetric(stats.cards.projects);
            if (aiEl) aiEl.textContent = formatMetric(stats.cards.aiInteractions);
            if (sourcesEl) sourcesEl.textContent = formatMetric(stats.cards.savedSources);
            if (activeDaysEl) activeDaysEl.textContent = formatMetric(stats.cards.activeDays);

            const activityConfig = {
                labels: stats.activityLabels,
                datasets: [{
                    label: statsText.datasets.activity,
                    data: stats.activityData,
                    backgroundColor: palette.accentFill,
                    borderColor: palette.accent,
                    borderWidth: 1.5,
                    borderRadius: 12,
                    maxBarThickness: 42
                }]
            };

            const topicConfig = {
                labels: statsText.labels.focus,
                datasets: [{
                    label: statsText.datasets.focus,
                    data: stats.focusData,
                    backgroundColor: palette.accentSoft,
                    borderColor: palette.accent,
                    pointBackgroundColor: palette.accent,
                    pointBorderColor: palette.accent,
                    pointHoverBackgroundColor: '#ffffff',
                    pointHoverBorderColor: palette.accent
                }]
            };

            const timeConfig = {
                labels: statsText.labels.hours,
                datasets: [{
                    label: statsText.datasets.time,
                    data: stats.timeData,
                    borderColor: palette.secondary,
                    tension: 0.35,
                    fill: true,
                    backgroundColor: palette.secondaryFill,
                    pointBackgroundColor: palette.secondary,
                    pointBorderColor: palette.secondary,
                    pointRadius: 4
                }]
            };

            const ctx1 = document.getElementById('activityChart')?.getContext('2d');
            const ctx2 = document.getElementById('topicChart')?.getContext('2d');
            const ctx3 = document.getElementById('timeChart')?.getContext('2d');

            const commonPlugins = {
                legend: {
                    display: false,
                    labels: { color: palette.text }
                },
                tooltip: {
                    displayColors: false
                }
            };

            if (ctx1) {
                if (!activityChart || force) {
                    if (activityChart && force) activityChart.destroy();
                    activityChart = new Chart(ctx1, {
                        type: 'bar',
                        data: activityConfig,
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: commonPlugins,
                            scales: {
                                x: {
                                    ticks: { color: palette.text },
                                    grid: { display: false }
                                },
                                y: {
                                    beginAtZero: true,
                                    ticks: { color: palette.text, precision: 0 },
                                    grid: { color: palette.grid }
                                }
                            }
                        }
                    });
                } else {
                    setChartData(activityChart, activityConfig);
                }
            }

            if (ctx2) {
                if (!topicChart || force) {
                    if (topicChart && force) topicChart.destroy();
                    topicChart = new Chart(ctx2, {
                        type: 'radar',
                        data: topicConfig,
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: commonPlugins,
                            scales: {
                                r: {
                                    beginAtZero: true,
                                    angleLines: { color: palette.grid },
                                    grid: { color: palette.grid },
                                    pointLabels: { color: palette.text, font: { size: 11 } },
                                    ticks: { display: false }
                                }
                            }
                        }
                    });
                } else {
                    setChartData(topicChart, topicConfig);
                }
            }

            if (ctx3) {
                if (!timeChart || force) {
                    if (timeChart && force) timeChart.destroy();
                    timeChart = new Chart(ctx3, {
                        type: 'line',
                        data: timeConfig,
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: commonPlugins,
                            scales: {
                                x: {
                                    ticks: { color: palette.text },
                                    grid: { color: palette.grid }
                                },
                                y: {
                                    beginAtZero: true,
                                    ticks: { color: palette.text, precision: 0 },
                                    grid: { color: palette.grid }
                                }
                            }
                        }
                    });
                } else {
                    setChartData(timeChart, timeConfig);
                }
            }
        }



        tabs.forEach(tab => {

            tab.addEventListener('click', () => {

                const target = tab.dataset.tab;

                tabs.forEach(t => t.classList.remove('active'));

                panels.forEach(p => p.classList.remove('active'));

                tab.classList.add('active');

                document.getElementById(`tab-${target}`).classList.add('active');

                gsap.from(`#tab-${target}`, { x: 14, opacity: 0, duration: 0.22, ease: 'power2.out' });

                

                if (target === 'statistics') {

                    setTimeout(initStats, 300);

                }

            });

        });



        themeCards.forEach(card => {

            card.addEventListener('click', () => setTheme(card.dataset.theme));

        });



        const savedTheme = localStorage.getItem('skemi-theme') || 'light';

        setTheme(savedTheme);



        const themeToggle = document.getElementById('themeToggle');

        if (themeToggle) {

            themeToggle.addEventListener('click', () => {

                const current = localStorage.getItem('skemi-theme') || 'light';

                const next = current === 'light' ? 'dark' : 'light';

                setTheme(next);

            });

        }



        const sidebar = document.getElementById('appSidebar');

        const toggleBtn = document.getElementById('toggleSidebar');

        if (toggleBtn) {

            toggleBtn.addEventListener('click', () => {

                sidebar.classList.toggle('collapsed');

                toggleBtn.querySelector('span').innerText = sidebar.classList.contains('collapsed') ? '▶' : '◀';

            });

        }



        function loadUserData() {

            try {

                const saved = localStorage.getItem('skemi_user_data');

                return saved ? JSON.parse(saved) : {};

            } catch {

                return {};

            }

        }



        function saveUserData(patch) {

            const current = loadUserData();

            const next = {
                ...current,
                ...patch,
                settings: {
                    ...(current.settings || {}),
                    ...(patch?.settings || {})
                }
            };

            localStorage.setItem('skemi_user_data', JSON.stringify(next));

            return next;

        }

        function applyStoredSettingsToControls(settings = {}) {
            if (typeof settings.quota_warn === 'boolean') document.getElementById('quotaWarnToggle').checked = settings.quota_warn;
            if (typeof settings.security_warn === 'boolean') document.getElementById('securityWarnToggle').checked = settings.security_warn;
            if (typeof settings.ephemeral_chat === 'boolean') document.getElementById('ephemeralChatToggle').checked = settings.ephemeral_chat;
            if (typeof settings.desktop_notify === 'boolean') document.getElementById('desktopNotifyToggle').checked = settings.desktop_notify;
            if (typeof settings.sound_notify === 'boolean') document.getElementById('soundNotifyToggle').checked = settings.sound_notify;
            if (typeof settings.email_notify === 'boolean') document.getElementById('emailNotifyToggle').checked = settings.email_notify;
            if (typeof settings.startup_tips === 'boolean') document.getElementById('startupTipsToggle').checked = settings.startup_tips;
            if (typeof settings.compact_mode === 'boolean') document.getElementById('compactModeToggle').checked = settings.compact_mode;
            if (typeof settings.animations_enabled === 'boolean') document.getElementById('animationsToggle').checked = settings.animations_enabled;
            if (typeof settings.ai_personalize === 'boolean') document.getElementById('aiPersonalizeToggle').checked = settings.ai_personalize;
            
            // v1.1.23: Skemi Control toggles
            if (typeof settings.auto_create_desktop === 'boolean') document.getElementById('autoCreateDesktopToggle').checked = settings.auto_create_desktop;
            if (typeof settings.prefer_app === 'boolean') document.getElementById('preferAppToggle').checked = settings.prefer_app;
        }



        const userData = loadUserData();

        document.getElementById('ageTag').value = userData.age_group || 'middle';

        document.getElementById('ageRange').value = userData.age_range || '';
        applyStoredSettingsToControls(userData.settings || {});

        const settingsPack = () => window.languageManager?.pack?.settings || {};

        const authPack = () => window.languageManager?.pack?.auth || {};



        document.getElementById('saveChangesBtn').addEventListener('click', async () => {

            const next = saveUserData({

                age_group: document.getElementById('ageTag').value,

                age_range: document.getElementById('ageRange').value.trim(),

                theme: localStorage.getItem('skemi-theme') || 'light',

                language: localStorage.getItem('skemi_language') || 'vi',

                settings: collectSettingsState()

            });

            await syncUserProfile(next);

            hideSaveBar();

            if (window.showToast) {

                window.showToast(settingsPack().profileSaved || 'Settings saved.', 'success');

            }

        });



        document.getElementById('discardChangesBtn').addEventListener('click', () => {

            // Reload saved values from localStorage

            const stored = loadUserData();

            document.getElementById('ageTag').value = stored.age_group || 'middle';

            document.getElementById('ageRange').value = stored.age_range || '';
            applyStoredSettingsToControls(stored.settings || {});

            hideSaveBar();

        });



        document.getElementById('saveProfileBtn')?.addEventListener('click', async () => {

            const next = saveUserData({

                age_group: document.getElementById('ageTag').value,

                age_range: document.getElementById('ageRange').value.trim(),

                theme: localStorage.getItem('skemi-theme') || 'light',

                language: localStorage.getItem('skemi_language') || 'vi',

                settings: collectSettingsState()

            });

            await syncUserProfile(next);

            if (window.showToast) {

                window.showToast(settingsPack().profileSaved || 'Account information saved.', 'success');

            } else {

                alert(settingsPack().profileSaved || 'Account information saved.');

            }

        });



        document.getElementById('resetProfileBtn')?.addEventListener('click', async () => {

            document.getElementById('ageTag').value = 'middle';

            document.getElementById('ageRange').value = '';

            const next = saveUserData({
                age_group: 'middle',
                age_range: '',
                theme: localStorage.getItem('skemi-theme') || 'light',
                language: localStorage.getItem('skemi_language') || 'vi',
                settings: collectSettingsState()
            });

            await syncUserProfile(next);

        });



        document.getElementById('clearLocalDataBtn').addEventListener('click', async () => {

            const keepTheme = localStorage.getItem('skemi-theme');

            const keepLang = localStorage.getItem('skemi_language');

            localStorage.clear();
            try {
                sessionStorage.clear();
            } catch {}

            if (keepTheme) localStorage.setItem('skemi-theme', keepTheme);

            if (keepLang) localStorage.setItem('skemi_language', keepLang);

            if (currentAuthUser) await syncUserProfile({ theme: keepTheme || 'light', language: keepLang || 'en' });

            alert(settingsPack().localCleared || 'Local browser data cleared.');

            location.reload();

        });



        const TRACKED_TOGGLES = ['quotaWarnToggle', 'securityWarnToggle', 'ephemeralChatToggle',
            'desktopNotifyToggle', 'soundNotifyToggle', 'emailNotifyToggle',
            'startupTipsToggle', 'compactModeToggle', 'animationsToggle', 'aiPersonalizeToggle',
            'autoCreateDesktopToggle', 'preferAppToggle'];



        // --- Floating Save Bar logic (Event Delegation for dynamic support) ---

        const saveBar = document.getElementById('saveBar');



        function showSaveBar() { saveBar.classList.add('visible'); }

        function hideSaveBar() { saveBar.classList.remove('visible'); }



        document.addEventListener('change', (e) => {

            if (e.target.classList.contains('settings-trackable')) {

                showSaveBar();

            }

        });

        document.addEventListener('input', (e) => {

            if (e.target.classList.contains('settings-trackable')) {

                showSaveBar();

            }

        });





        const applyAuthView = (user) => {
            const isGuest = !user;
            document.body.classList.remove('auth-pending');
            document.body.classList.toggle('guest-mode', isGuest);
            if (authGuard) authGuard.hidden = !isGuest;
            if (settingsLayout) settingsLayout.setAttribute('aria-hidden', isGuest ? 'true' : 'false');
            if (logoutBtn) logoutBtn.style.display = isGuest ? 'none' : '';
        };

        const renderAuthState = (user) => {

            const display = document.getElementById('user-display');

            const email = document.getElementById('user-email');

            const avatar = document.getElementById('user-avatar-large');

            const verification = document.getElementById('verificationStatus');



            if (user) {

                const name = user.displayName || user.email?.split('@')[0] || settingsPack().defaultUser || 'Skemi user';

                display.textContent = name;

                email.textContent = user.email || '';

                avatar.textContent = name.charAt(0).toUpperCase();



                verification.textContent = user.emailVerified

                    ? (settingsPack().verified || 'Email verified.')

                    : (settingsPack().unverified || 'Email not verified. Please verify it to protect your account.');

            } else {

                display.textContent = authPack().guest || 'Guest';

                email.textContent = authPack().sync || 'Log in to sync your data.';

                avatar.textContent = 'G';

                verification.textContent = settingsPack().notLoggedIn || 'Not logged in.';

            }

        };



        onAuthStateChanged(auth, async (user) => {
            currentAuthUser = user;
            applyAuthView(user);

            if (user) {

                await loadRemoteSettings(user);

                const remoteTheme = localStorage.getItem('skemi-theme') || 'light';

                setTheme(remoteTheme);

            }

            renderAuthState(user);

        });

        window.addEventListener('load', () => {
            setTimeout(() => {
                if (document.body.classList.contains('auth-pending')) {
                    const fallbackUser = auth.currentUser || null;
                    currentAuthUser = fallbackUser;
                    applyAuthView(fallbackUser);
                    renderAuthState(fallbackUser);
                }
            }, 1200);
        });



        window.addEventListener('languageChanged', () => {
            renderAuthState(currentAuthUser);
            if (activityChart || topicChart || timeChart || document.getElementById('tab-statistics')?.classList.contains('active')) {
                requestAnimationFrame(() => initStats(true));
            }
            void syncUserProfile({ language: localStorage.getItem('skemi_language') || 'en' });
        });

        window.addEventListener('themeChanged', () => {
            if (activityChart || topicChart || timeChart || document.getElementById('tab-statistics')?.classList.contains('active')) {
                requestAnimationFrame(() => initStats(true));
            }
        });



        document.getElementById('logoutBtn').addEventListener('click', async () => {

            try {

                if (auth.currentUser) {

                    await signOut(auth);

                }

            } catch (error) {

                console.error('Sign out error', error);

            }

            window.location.href = 'Login.html';

        });

