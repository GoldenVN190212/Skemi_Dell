// ========================================
// AI CHAT WIDGET - Inline Chat Integration
// ========================================

const AI_COMMAND_SCHEMA_NOTE = '{"commands":[{"type":"search.run","targetPage":"search","displayText":"...","executePayload":{"query":"..."},"requiresApproval":false,"returnSummary":true}]}';

class AIChatWidget {
    constructor() {
        if (AIChatWidget.instance) {
            return AIChatWidget.instance;
        }

        this.chatStorage = this.resolvePersistentStorage();
        this._baseChatHistoryKey = 'skemi_ai_chat_history_v2';
        this._baseSessionIdKey = 'skemi_ai_session_id_v1';
        this._basePendingCommandKey = 'skemi_ai_pending_command_v1';
        this._baseWorkflowStateKey = 'skemi_ai_workflow_state_v1';
        this._basePendingAssistantJobKey = 'skemi_ai_pending_assistant_job_v1';
        this._baseProjectStorageKey = 'skemi_studio_projects_v1';
        this._baseSearchStateKey = 'skemi_search_state_v3';
        this._baseQuizRoomStorageKey = 'skemi_private_quiz_rooms_v1';

        this.sessionId = this.loadOrCreateSessionId();
        this.ageGroup = 'middle'; // young, middle, senior
        this.isOpen = false;
        this.isLoading = false;
        this.messages = [];
        this.loadingMessageEl = null;
        this.apiBaseUrl = this.resolveApiBaseUrl();
        this.visibilityObserver = null;
        this.uiWatchdog = null;
        this.maxHistoryMessages = 80;
        this.maxMessageChars = 12000;
        this.pendingApproval = null;
        this.pendingWorkflows = this.loadWorkflowState();
        this.capabilityRegistry = this.buildCapabilityRegistry();
        this.controlAuraTimer = null;
        this.requestAbortController = null;
        this.userStoppedRequest = false;
        this.autoScrollThreshold = 88;
        this.stopBtn = null;
        this.scrollBottomBtn = null;

        AIChatWidget.instance = this;

        this.init();
    }

    // Dynamic keys based on User UID to prevent data leakage across accounts.
    // BUG FIXED: this used to read `skemi_user_data.uid` — but the profile
    // object Login.html/Register.html mirror to that key never actually
    // contains a `uid` field (checked: Firestore snap.data(), the sign-up
    // fallback, and Register's initialData all omit it), so this ALWAYS
    // resolved to '_guest' for every signed-in account, silently colliding
    // every user's Studio projects / chat history / session state into one
    // shared slot on a given browser. `skemi_user_id` is the field Auth.js
    // actually populates from the real Firebase uid on every sign-in — same
    // source account-storage.js's getCurrentUid() already uses correctly.
    get _uidSuffix() {
        try {
            const uid = localStorage.getItem('skemi_user_id');
            return uid ? `_${uid}` : '_guest';
        } catch {
            return '_guest';
        }
    }

    get chatHistoryKey() { return this._baseChatHistoryKey + this._uidSuffix; }
    get sessionIdKey() { return this._baseSessionIdKey + this._uidSuffix; }
    get pendingCommandKey() { return this._basePendingCommandKey + this._uidSuffix; }
    get workflowStateKey() { return this._baseWorkflowStateKey + this._uidSuffix; }
    get pendingAssistantJobKey() { return this._basePendingAssistantJobKey + this._uidSuffix; }
    get projectStorageKey() { return this._baseProjectStorageKey + this._uidSuffix; }
    get searchStateKey() { return this._baseSearchStateKey + this._uidSuffix; }
    get quizRoomStorageKey() { return this._baseQuizRoomStorageKey + this._uidSuffix; }

    resolveApiBaseUrl() {
        const candidates = [
            window.SKEMI_AI_API_BASE,
            window.SKEMI_CORE_API_BASE,
            window.SKEMMA_CORE_API_BASE,
            window.SKEMI_API_BASE
        ].map((value) => String(value || '').trim()).filter(Boolean);

        if (candidates.length > 0) {
            return candidates[0].replace(/\/+$/, '');
        }

        const port = String(window.location.port || '').trim();
        if (port === '8010') {
            return window.location.origin.replace(/\/+$/, '');
        }
        if (port === '8001' || port === '5500' || !port) {
            return 'http://127.0.0.1:8010';
        }
        return window.location.origin.replace(/\/+$/, '');
    }

    resolvePersistentStorage() {
        try {
            return window.localStorage;
        } catch {
            try {
                return window.sessionStorage;
            } catch {
                return null;
            }
        }
    }

    generateSessionId() {
        return `session_${Math.random().toString(36).slice(2, 11)}_${Date.now()}`;
    }

    loadOrCreateSessionId() {
        const existing = this.chatStorage?.getItem(this.sessionIdKey);
        if (existing) return existing;
        const created = this.generateSessionId();
        try {
            this.chatStorage?.setItem(this.sessionIdKey, created);
        } catch {}
        return created;
    }

    registerEphemeralLifecycle() {
        window.addEventListener('skemi:clear-ai-chat-history', (event) => {
            const notifyBackend = event?.detail?.notifyBackend !== false;
            this.clearEphemeralSession({ notifyBackend });
        });
    }

    clearEphemeralSession(options = {}) {
        const notifyBackend = options.notifyBackend !== false;
        const payload = JSON.stringify({ session_id: this.sessionId || '' });
        try {
            this.chatStorage?.removeItem(this.chatHistoryKey);
            this.chatStorage?.removeItem(this.sessionIdKey);
        } catch {}
        this.messages = [];

        if (!notifyBackend || !this.sessionId) return;
        try {
            const endpoint = `${this.apiBaseUrl}/end_session`;
            if (navigator.sendBeacon) {
                navigator.sendBeacon(endpoint, new Blob([payload], { type: 'application/json' }));
            } else {
                fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payload,
                    keepalive: true
                }).catch(() => {});
            }
        } catch {}
    }

    loadWorkflowState() {
        try {
            const parsed = JSON.parse(localStorage.getItem(this.workflowStateKey) || '{}');
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch {
            return {};
        }
    }

    persistWorkflowState() {
        try {
            localStorage.setItem(this.workflowStateKey, JSON.stringify(this.pendingWorkflows || {}));
        } catch {}
    }

    rememberWorkflow(workflow) {
        const workflowId = String(workflow?.workflowId || '').trim();
        if (!workflowId) return;
        this.pendingWorkflows[workflowId] = {
            ...this.pendingWorkflows[workflowId],
            ...workflow,
            workflowId
        };
        this.persistWorkflowState();
    }

    forgetWorkflow(workflowId) {
        const id = String(workflowId || '').trim();
        if (!id) return;
        delete this.pendingWorkflows[id];
        this.persistWorkflowState();
    }

    getWorkflow(workflowId) {
        const id = String(workflowId || '').trim();
        return id ? this.pendingWorkflows[id] || null : null;
    }

    buildCapabilityRegistry() {
        return {
            search: {
                page: 'search',
                actions: ['search.run', 'search.open'],
                description: this.isVietnamese()
                    ? 'Viết lại truy vấn, mở Search, chạy phân tích và trả tóm tắt kèm nguồn.'
                    : 'Rewrite the query, open Search, run analysis, and return a grounded summary with sources.'
            },
            studio: {
                page: 'home',
                actions: ['studio.open', 'studio.create_project', 'studio.seed_prompt', 'studio.switch_tab', 'studio.notebook_create'],
                description: this.isVietnamese()
                    ? 'Mở project, nạp prompt, đổi tab và tạo output trong Studio.'
                    : 'Open projects, seed prompts, switch tabs, and create outputs in Studio.'
            },
            quiz: {
                page: 'quiz',
                actions: ['quiz.open', 'quiz.create_room', 'quiz.create_arena'],
                description: this.isVietnamese()
                    ? 'Mở Quiz, tạo phòng quiz draft hoặc khởi tạo Arena.'
                    : 'Open Quiz, create quiz room drafts, or launch an Arena.'
            },
            chat: {
                page: 'chat',
                actions: ['chat.open', 'chat.prefill', 'chat.send'],
                description: this.isVietnamese()
                    ? 'Mở hội thoại, điền nội dung nhắn và gửi tin nhắn khi được phép.'
                    : 'Open conversations, prefill message content, and send messages with approval.'
            },
            settings: {
                page: 'settings',
                actions: ['settings.open', 'settings.update_ai_profile', 'settings.toggle_autoreply'],
                description: this.isVietnamese()
                    ? 'Đọc hoặc cập nhật cài đặt AI, ngôn ngữ và auto-reply.'
                    : 'Read or update AI, language, and auto-reply settings.'
            }
        };
    }

    init() {
        this.createWidget();
        this.bindEvents();
        window.addEventListener('skemi:ai-control-state', () => this.updateStopButtonVisibility());
        window.addEventListener('skemi:workflow-accepted', (event) => this.handleWorkflowAccepted(event?.detail));
        window.addEventListener('skemi:workflow-started', (event) => this.handleWorkflowStarted(event?.detail));
        window.addEventListener('skemi:workflow-result', (event) => this.handleWorkflowResult(event?.detail));
        window.addEventListener('skemi:workflow-failed', (event) => this.handleWorkflowFailed(event?.detail));
        window.addEventListener('languageChanged', () => this.applyLanguage());
        this.registerEphemeralLifecycle();
        this.applyLanguage();
        this.loadChatHistory();
        this.resumePendingAssistantJob();
        this.updateScrollButtonVisibility();
        this.updateStopButtonVisibility();
    }

    t(path, params = {}) {
        if (window.languageManager?.t) {
            return window.languageManager.t(path, params);
        }
        return path;
    }

    getBrandTitle() {
        return 'Skemi AI';
    }

    getBrandAvatarMarkup(_size = 'title') {
        return '<span class="ai-brand-emoji" aria-hidden="true">🤖</span>';
    }

    getSendButtonMarkup(loading = false) {
        if (loading) {
            return '<span class="ai-send-wait" aria-hidden="true"></span>';
        }
        return '<span class="ai-send-icon" aria-hidden="true">&#9658;</span>';
    }

    getScrollBottomLabel() {
        return this.isVietnamese() ? 'Xuống tin nhắn mới nhất' : 'Jump to latest message';
    }

    getStopButtonLabel() {
        return this.isVietnamese() ? 'Tạm dừng' : 'Pause';
    }

    getStopButtonTitle() {
        return this.isVietnamese()
            ? 'Dừng phản hồi hoặc dừng điều khiển'
            : 'Stop response or control action';
    }

    isNearBottom(threshold = this.autoScrollThreshold) {
        if (!this.messagesContainer) return true;
        const { scrollTop, scrollHeight, clientHeight } = this.messagesContainer;
        return (scrollHeight - (scrollTop + clientHeight)) <= threshold;
    }

    scrollToLatest(smooth = false) {
        if (!this.messagesContainer) return;
        this.messagesContainer.scrollTo({
            top: this.messagesContainer.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
        this.updateScrollButtonVisibility();
    }

    updateScrollButtonVisibility() {
        if (!this.scrollBottomBtn || !this.messagesContainer) return;
        const hasMessages = this.messagesContainer.querySelectorAll('.ai-message').length > 0;
        const shouldShow = hasMessages && !this.isNearBottom();
        this.scrollBottomBtn.classList.toggle('show', shouldShow);
        this.scrollBottomBtn.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');
    }

    isControlVisualActive() {
        return document.body.classList.contains('skemi-ai-controlling')
            || this.root?.classList.contains('is-controlling');
    }

    updateStopButtonVisibility() {
        if (!this.stopBtn) return;
        const active = this.isLoading || this.isControlVisualActive() || Boolean(this.pendingApproval);
        this.stopBtn.classList.toggle('show', active);
        this.stopBtn.disabled = false;
    }

    escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    safeParseHistory(raw) {
        try {
            const parsed = JSON.parse(String(raw || ''));
            if (!parsed || typeof parsed !== 'object') return null;
            if (!Array.isArray(parsed.messages)) parsed.messages = [];
            return parsed;
        } catch {
            return null;
        }
    }

    normalizeHistoryMessage(msg) {
        if (!msg || typeof msg !== 'object') return null;
        const type = String(msg.type || 'assistant');
        const content = String(msg.content || '').slice(0, this.maxMessageChars);
        const rawTs = Number(msg.timestamp || Date.now());
        const timestamp = Number.isFinite(rawTs) ? rawTs : Date.now();
        if (!content) return null;
        return { type, content, timestamp };
    }

    mergeHistoryMessages(baseMessages, incomingMessages) {
        const merged = [];
        const seen = new Set();
        const pushUnique = (msg) => {
            const normalized = this.normalizeHistoryMessage(msg);
            if (!normalized) return;
            const key = `${normalized.type}|${normalized.timestamp}|${normalized.content.slice(0, 128)}`;
            if (seen.has(key)) return;
            seen.add(key);
            merged.push(normalized);
        };

        (Array.isArray(baseMessages) ? baseMessages : []).forEach(pushUnique);
        (Array.isArray(incomingMessages) ? incomingMessages : []).forEach(pushUnique);

        merged.sort((a, b) => a.timestamp - b.timestamp);
        return merged;
    }

    normalizeSchoolMathNotation(input) {
        if (!input) return '';
        return String(input)
            .replace(/\\\[/g, '')
            .replace(/\\\]/g, '')
            .replace(/\\\(/g, '')
            .replace(/\\\)/g, '')
            .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1/$2)')
            .replace(/\\sqrt\{([^{}]+)\}/g, 'sqrt($1)')
            .replace(/\\cdot|\\times/g, ' x ')
            .replace(/\\div/g, ' / ')
            .replace(/\\leq/g, '<=')
            .replace(/\\geq/g, '>=')
            .replace(/\\neq/g, '!=')
            .replace(/\\approx/g, '~=')
            .replace(/\\pm/g, '+/-')
            .replace(/\u2264/g, '<=')
            .replace(/\u2265/g, '>=')
            .replace(/\u2260/g, '!=')
            .replace(/\u2248/g, '~=')
            .replace(/\u00b1/g, '+/-')
            .replace(/[\u00d7\u2715]/g, ' x ')
            .replace(/\u00f7/g, ' / ')
            .replace(/\u221a/g, 'sqrt')
            .replace(/[ \t]{2,}/g, ' ')
            .trim();
    }

    sanitizeAssistantRaw(input) {
        let text = String(input || '')
            .replace(/\r\n/g, '\n')
            .replace(/\n{4,}/g, '\n\n\n');

        text = text.replace(/[ \t]*\|\|+[ \t]*/g, '\n');

        text = text.split('\n').map((line) => {
            const trimmed = line.trim();
            const isTableLine = trimmed.startsWith('|') && trimmed.endsWith('|');
            if (isTableLine) {
                const pipeCount = (trimmed.match(/\|/g) || []).length;
                if (pipeCount <= 2) {
                    return trimmed.slice(1, -1).trim();
                }
                return line;
            }
            if (trimmed && trimmed.includes('|')) {
                return line.replace(/\s*\|\s*/g, ' - ');
            }
            return line;
        }).join('\n');

        const strongCount = (text.match(/\*\*/g) || []).length;
        if (strongCount % 2 !== 0) {
            text = text.replace(/\*\*/g, '');
        }
        text = text.replace(/\*{3,}/g, '**');

        return this.normalizeSchoolMathNotation(text);
    }

    hasMeaningfulMarkdown(text) {
        const value = String(text || '');
        return /```[\s\S]*?```/.test(value)
            || /`[^`\n]+`/.test(value)
            || /^\s{0,3}#{1,4}\s+\S+/m.test(value)
            || /^\s{0,3}[-*+]\s+\S+/m.test(value)
            || /^\s{0,3}\d+\.\s+\S+/m.test(value)
            || /^\s{0,3}>\s+\S+/m.test(value)
            || /^\s*\|.+\|\s*$/m.test(value)
            || /\*\*[^*\n]+?\*\*/.test(value);
    }

    renderAssistantHtml(rawText) {
        const cleaned = this.sanitizeAssistantRaw(rawText);
        if (!this.hasMeaningfulMarkdown(cleaned)) {
            return this.escapeHtml(cleaned).replace(/\n/g, '<br>');
        }

        let html = this.escapeHtml(cleaned);
        const codeBlocks = [];
        html = html.replace(/```(\w+)?\n?([\s\S]*?)```/g, (_, lang = 'code', code = '') => {
            const token = `__AI_CHAT_CODE_${codeBlocks.length}__`;
            codeBlocks.push(`
                <div class="ai-md-code">
                    <div class="ai-md-code-head">${this.escapeHtml(lang)}</div>
                    <pre><code>${code.trim()}</code></pre>
                </div>
            `);
            return token;
        });

        html = html.replace(/`([^`\n]+)`/g, '<code class="ai-md-inline">$1</code>');
        html = html.replace(/^###\s+(.*)$/gm, '<h4>$1</h4>');
        html = html.replace(/^##\s+(.*)$/gm, '<h3>$1</h3>');
        html = html.replace(/^#\s+(.*)$/gm, '<h2>$1</h2>');
        html = html.replace(/^\s*[-*+]\s+(.*)$/gm, '- $1');
        html = html.replace(/^\s*\d+\.\s+(.*)$/gm, '<strong>$1</strong>');
        html = html.replace(/^\s*>\s+(.*)$/gm, '<em>$1</em>');
        html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\n/g, '<br>');
        html = html.replace(/(<br>\s*){3,}/g, '<br><br>');

        codeBlocks.forEach((block, index) => {
            html = html.replace(`__AI_CHAT_CODE_${index}__`, block);
        });

        return html;
    }

    applyMessageContent(messageDiv, type, content, extraClass = '') {
        if (type === 'assistant' && extraClass !== 'loading') {
            messageDiv.innerHTML = this.renderAssistantHtml(content);
            return;
        }
        messageDiv.textContent = content;
    }

    createWidget() {
        const existingRoot = document.getElementById('aiChatWidgetRoot');
        if (existingRoot) {
            this.root = existingRoot;
            this.toggleBtn = document.getElementById('aiChatToggle');
            this.container = document.getElementById('aiChatContainer');
            this.closeBtn = document.getElementById('aiChatClose');
            this.messagesContainer = document.getElementById('aiChatMessages');
            this.input = document.getElementById('aiChatInput');
            this.sendBtn = document.getElementById('aiChatSend');
            this.stopBtn = document.getElementById('aiChatStop');
            this.scrollBottomBtn = document.getElementById('aiChatScrollBottom');
            this.ageButtons = document.querySelectorAll('.ai-age-btn');
            if (this.toggleBtn) {
                this.toggleBtn.title = this.getBrandTitle();
                this.toggleBtn.innerHTML = this.getBrandAvatarMarkup('toggle');
            }
            const emptyIcon = document.querySelector('.ai-chat-empty .icon');
            if (emptyIcon) emptyIcon.innerHTML = this.getBrandAvatarMarkup('empty');
            if (this.sendBtn) this.sendBtn.innerHTML = this.getSendButtonMarkup(false);
            if (this.closeBtn) this.closeBtn.innerHTML = '&times;';
            if (this.stopBtn) {
                this.stopBtn.textContent = this.getStopButtonLabel();
                this.stopBtn.title = this.getStopButtonTitle();
            }
            if (this.scrollBottomBtn) {
                this.scrollBottomBtn.title = this.getScrollBottomLabel();
                this.scrollBottomBtn.setAttribute('aria-label', this.getScrollBottomLabel());
            }
            return;
        }

        const widgetHTML = `
            <div class="ai-chat-widget" id="aiChatWidgetRoot">
                <button class="ai-chat-toggle" id="aiChatToggle" title="${this.getBrandTitle()}" aria-label="${this.getBrandTitle()}">
                    ${this.getBrandAvatarMarkup('toggle')}
                </button>

                <div class="ai-chat-container" id="aiChatContainer">
                    <div class="ai-chat-header">
                        <div class="ai-chat-title" data-no-translate="true">${this.getBrandAvatarMarkup('title')}<span>${this.getBrandTitle()}</span></div>
                        <button class="ai-chat-close" id="aiChatClose" title="${this.t('aichat.close')}">&times;</button>
                    </div>

                    <div class="ai-chat-messages-wrap">
                        <div class="ai-chat-messages" id="aiChatMessages">
                            <div class="ai-chat-empty">
                                <div class="icon">${this.getBrandAvatarMarkup('empty')}</div>
                                <h3>${this.t('aichat.emptyTitle')}</h3>
                                <p>${this.t('aichat.emptyDesc')}</p>
                            </div>
                        </div>
                        <button class="ai-chat-scroll-bottom" id="aiChatScrollBottom" title="${this.getScrollBottomLabel()}" aria-label="${this.getScrollBottomLabel()}">&#8595;</button>
                    </div>

                    <div class="ai-chat-age-selector">
                            <button class="ai-age-btn" data-age="young">${this.t('age.young')}</button>
                            <button class="ai-age-btn active" data-age="middle">${this.t('age.middle')}</button>
                            <button class="ai-age-btn" data-age="senior">${this.t('age.senior')}</button>
                    </div>

                    <div class="ai-chat-input-container">
                        <textarea
                            class="ai-chat-input"
                            id="aiChatInput"
                            placeholder="${this.t('aichat.placeholder')}"
                            rows="1"
                        ></textarea>
                        <button class="ai-chat-stop" id="aiChatStop" title="${this.getStopButtonTitle()}">${this.getStopButtonLabel()}</button>
                        <button class="ai-chat-send" id="aiChatSend" title="${this.t('aichat.send')}">${this.getSendButtonMarkup(false)}</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', widgetHTML);

        this.root = document.getElementById('aiChatWidgetRoot');
        this.toggleBtn = document.getElementById('aiChatToggle');
        this.container = document.getElementById('aiChatContainer');
        this.closeBtn = document.getElementById('aiChatClose');
        this.messagesContainer = document.getElementById('aiChatMessages');
        this.input = document.getElementById('aiChatInput');
        this.sendBtn = document.getElementById('aiChatSend');
        this.stopBtn = document.getElementById('aiChatStop');
        this.scrollBottomBtn = document.getElementById('aiChatScrollBottom');
        this.ageButtons = document.querySelectorAll('.ai-age-btn');
    }

    applyLanguage() {
        const brandTitle = this.getBrandTitle();
        if (this.toggleBtn) {
            this.toggleBtn.title = brandTitle;
            this.toggleBtn.setAttribute('aria-label', brandTitle);
            this.toggleBtn.innerHTML = this.getBrandAvatarMarkup('toggle');
        }
        const titleEl = document.querySelector('.ai-chat-title');
        if (titleEl) {
            titleEl.innerHTML = `${this.getBrandAvatarMarkup('title')}<span>${this.escapeHtml(brandTitle)}</span>`;
        }
        const emptyIcon = document.querySelector('.ai-chat-empty .icon');
        if (emptyIcon) emptyIcon.innerHTML = this.getBrandAvatarMarkup('empty');
        if (this.closeBtn) {
            this.closeBtn.title = this.t('aichat.close');
            this.closeBtn.innerHTML = '&times;';
        }
        const emptyTitle = document.querySelector('.ai-chat-empty h3');
        if (emptyTitle) emptyTitle.textContent = this.t('aichat.emptyTitle');
        const emptyDesc = document.querySelector('.ai-chat-empty p');
        if (emptyDesc) emptyDesc.textContent = this.t('aichat.emptyDesc');
        if (this.input) this.input.placeholder = this.t('aichat.placeholder');
        if (this.sendBtn) {
            this.sendBtn.title = this.t('aichat.send');
            this.sendBtn.innerHTML = this.getSendButtonMarkup(this.isLoading);
        }
        if (this.stopBtn) {
            this.stopBtn.textContent = this.getStopButtonLabel();
            this.stopBtn.title = this.getStopButtonTitle();
        }
        if (this.scrollBottomBtn) {
            const label = this.getScrollBottomLabel();
            this.scrollBottomBtn.title = label;
            this.scrollBottomBtn.setAttribute('aria-label', label);
        }
        const labels = [this.t('age.young'), this.t('age.middle'), this.t('age.senior')];
        this.ageButtons.forEach((btn, index) => {
            if (labels[index]) btn.textContent = labels[index];
        });
        if (this.messages.length > 0) {
            this.restoreMessages();
        }
        this.updateStopButtonVisibility();
        this.updateScrollButtonVisibility();
    }

    formatWorkflowSources(sources = []) {
        const items = Array.isArray(sources) ? sources.slice(0, 4) : [];
        if (!items.length) return '';
        const lines = items.map((source) => {
            const title = String(source?.title || source?.url || '').trim();
            const url = String(source?.url || '').trim();
            return `- ${title}${url ? `: ${url}` : ''}`;
        });
        if (this.isVietnamese()) {
            return `\n\nNguồn chính:\n${lines.join('\n')}`;
        }
        return `\n\nTop sources:\n${lines.join('\n')}`;
    }

    describeWorkflowQuery(detail = {}) {
        return String(detail?.displayQuery || detail?.query || detail?.rawQuery || '').trim();
    }

    handleWorkflowAccepted(detail = {}) {
        const workflowId = String(detail?.workflowId || '').trim();
        if (!workflowId) return;
        this.rememberWorkflow({
            workflowId,
            type: detail?.type || 'search.run',
            targetPage: detail?.targetPage || 'search',
            query: detail?.query || '',
            displayQuery: detail?.displayQuery || ''
        });
    }

    handleWorkflowStarted(detail = {}) {
        const workflowId = String(detail?.workflowId || '').trim();
        const existing = this.getWorkflow(workflowId);
        if (!existing) return;
        if (existing.startedShown) return;
        const query = this.describeWorkflowQuery(detail) || this.describeWorkflowQuery(existing);
        const message = this.isVietnamese()
            ? `Skemi AI đang thao tác trên web để xử lý "${query || 'yêu cầu này'}".`
            : `Skemi AI is operating the website to handle "${query || 'this request'}".`;
        this.addMessage('system', message, true);
        this.rememberWorkflow({ ...existing, startedShown: true });
    }

    handleWorkflowResult(detail = {}) {
        const workflowId = String(detail?.workflowId || '').trim();
        const workflow = this.getWorkflow(workflowId);
        if (!workflow) return;
        const query = this.describeWorkflowQuery(detail) || this.describeWorkflowQuery(workflow);
        const summary = String(detail?.summary || detail?.analysis?.brief || '').trim();
        if (String(detail?.type || workflow.type).toLowerCase() === 'search.run') {
            const prefix = this.isVietnamese()
                ? `Đã hoàn tất Search cho "${query || 'truy vấn'}".`
                : `Search finished for "${query || 'the query'}".`;
            const body = summary || (this.isVietnamese()
                ? 'Skemi đã chạy Search và trả về kết quả từ nguồn web hiện có.'
                : 'Skemi ran Search and returned grounded web results.');
            this.addMessage('assistant', `${prefix}\n\n${body}${this.formatWorkflowSources(detail?.sources)}`, true);
        } else {
            const message = summary || (this.isVietnamese() ? 'Tác vụ trên web đã hoàn tất.' : 'The web task is complete.');
            this.addMessage('assistant', message, true);
        }
        this.forgetWorkflow(workflowId);
    }

    handleWorkflowFailed(detail = {}) {
        const workflowId = String(detail?.workflowId || '').trim();
        const workflow = this.getWorkflow(workflowId);
        if (!workflow) return;
        const query = this.describeWorkflowQuery(detail) || this.describeWorkflowQuery(workflow);
        const errorText = String(detail?.error || '').trim();
        const message = this.isVietnamese()
            ? `Skemi AI không hoàn tất được thao tác cho "${query || 'yêu cầu này'}".${errorText ? `\n\nChi tiết: ${errorText}` : ''}`
            : `Skemi AI could not complete the action for "${query || 'this request'}".${errorText ? `\n\nDetails: ${errorText}` : ''}`;
        this.addMessage('assistant', message, true);
        this.forgetWorkflow(workflowId);
    }

    forceOpenUI() {
        this.container.classList.add('active');
        this.toggleBtn.classList.add('active');
        this.container.style.display = 'flex';
        this.container.style.visibility = 'visible';
        this.container.style.opacity = '1';
        this.container.style.pointerEvents = 'auto';
    }

    bindEvents() {
        this.toggleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.toggleChat();
        });

        this.closeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.closeChat();
        });

        this.container.addEventListener('click', (e) => e.stopPropagation());

        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.stopBtn?.addEventListener('click', () => this.stopCurrentAction());
        this.scrollBottomBtn?.addEventListener('click', () => this.scrollToLatest(true));
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.input.addEventListener('input', () => {
            this.input.style.height = 'auto';
            this.input.style.height = `${Math.min(this.input.scrollHeight, 100)}px`;
        });

        this.messagesContainer?.addEventListener('scroll', () => {
            this.updateScrollButtonVisibility();
        });

        this.ageButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                this.ageButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.ageGroup = btn.dataset.age;
                this.addMessage('system', this.t('aichat.switchMode', { label: btn.textContent }), false);
            });
        });

        // Keep chat stable: do not auto-close on outside click.
    }

    toggleChat() {
        if (this.isOpen) {
            this.closeChat();
        } else {
            this.openChat();
        }
    }

    openChat() {
        this.isOpen = true;
        this.forceOpenUI();
        this.input.focus();
        this.scrollToLatest(false);
        this.updateStopButtonVisibility();

        this.attachVisibilityObserver();
        this.startUiWatchdog();

        if (typeof gsap !== 'undefined') {
            gsap.from(this.container, {
                scale: 0.88,
                opacity: 0,
                duration: 0.28,
                ease: 'back.out(1.5)'
            });
        }
    }

    closeChat() {
        this.isOpen = false;
        this.detachVisibilityObserver();
        this.stopUiWatchdog();
        this.container.classList.remove('active');
        this.toggleBtn.classList.remove('active');
        this.container.style.display = '';
        this.container.style.visibility = '';
        this.container.style.opacity = '';
        this.container.style.pointerEvents = '';
    }

    startUiWatchdog() {
        this.stopUiWatchdog();
        this.uiWatchdog = window.setInterval(() => {
            if (!this.isOpen || !this.container) {
                return;
            }

            const style = window.getComputedStyle(this.container);
            const hiddenByCss = style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0;
            if (hiddenByCss || !this.container.classList.contains('active')) {
                this.forceOpenUI();
            }

            const visibleMessages = this.messagesContainer?.querySelectorAll('.ai-message').length || 0;
            if (visibleMessages === 0 && this.messages.length > 0) {
                this.restoreMessages();
            }

            this.updateScrollButtonVisibility();
            this.updateStopButtonVisibility();
        }, 400);
    }

    stopUiWatchdog() {
        if (this.uiWatchdog) {
            window.clearInterval(this.uiWatchdog);
            this.uiWatchdog = null;
        }
    }

    attachVisibilityObserver() {
        this.detachVisibilityObserver();
        this.visibilityObserver = new MutationObserver(() => {
            if (!this.isOpen) {
                return;
            }

            const hiddenByClass = !this.container.classList.contains('active');
            const hiddenByStyle = this.container.style.display === 'none';
            if (hiddenByClass || hiddenByStyle) {
                this.forceOpenUI();
            }
        });

        this.visibilityObserver.observe(this.container, {
            attributes: true,
            attributeFilter: ['class', 'style']
        });
    }

    detachVisibilityObserver() {
        if (this.visibilityObserver) {
            this.visibilityObserver.disconnect();
            this.visibilityObserver = null;
        }
    }

    isVietnamese() {
        return (window.languageManager?.base || 'vi') === 'vi';
    }

    normalizeForMatch(value) {
        return String(value || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    cleanProjectName(value) {
        let name = String(value || '').trim();
        if (!name) return '';
        name = name
            .replace(/^[`"'“”‘’]+|[`"'“”‘’]+$/g, '')
            .replace(/\s{2,}/g, ' ')
            .trim();
        return name.slice(0, 80).trim();
    }

    deriveProjectNameFromPrompt(prompt) {
        const quoted = this.extractQuotedSegment(prompt);
        if (quoted) {
            return this.cleanProjectName(quoted);
        }

        const cleaned = String(prompt || '')
            .replace(/[.,;:!?]+/g, ' ')
            .replace(/\b(tao|create|lam|generate|giup|help|cho toi|cho mình|cho minh|de|để|with|using|make|xay dung|xây dựng)\b/gi, ' ')
            .replace(/\b(mindmap|report|presentation|infographic|flashcard|podcast|video|quiz|quiztest|dashboard|chart|workspace|studio|project|du an|dự án|he thong|hệ thống)\b/gi, ' ')
            .replace(/\s{2,}/g, ' ')
            .trim();

        if (!cleaned) {
            return this.isVietnamese() ? 'Du an moi' : 'New Project';
        }

        return this.cleanProjectName(cleaned.split(' ').slice(0, 6).join(' '));
    }

    looksLikeControlIntent(message) {
        const normalized = this.normalizeForMatch(message);
        // Ưu tiên dấu gạch chéo, nhưng cũng chấp nhận các từ khóa hành động tự nhiên ở bất kỳ đâu
        return message.trim().startsWith('/') || /(tao|create|lam|generate|open|mo|bat|vao|xem|chuẩn bị|search|tim|tra cuu|chuyen|switch|project|du an|duan|studio|workspace|mindmap|report|presentation|infographic|flashcard|podcast|video|quiz|arena)/.test(normalized);
    }

    normalizePlannedCommand(plan, rawMessage) {
        if (!plan || typeof plan !== 'object') return null;

        const type = String(plan.type || '').trim().toLowerCase();
        if (!type || type === 'none') return null;
        const workflowId = `wf_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

        if (type === 'studio.create_project') {
            const rawName = plan.name || plan.projectName || '';
            const prompt = String(plan.prompt || '').trim();
            // Nếu không có tên, tự động suy diễn từ nội dung hoặc dùng tên mặc định, không báo lỗi
            const name = this.cleanProjectName(rawName || this.deriveProjectNameFromPrompt(prompt || rawMessage));
            return {
                type,
                target: 'home',
                name: name || (this.isVietnamese() ? 'Dự án AI mới' : 'New AI Project'),
                prompt,
                workspaceType: this.detectWorkspaceType(plan.workspaceType || prompt || rawMessage),
                autoGenerate: Boolean(plan.autoGenerate || prompt),
                targetPage: 'home',
                executePayload: {
                    name: name || (this.isVietnamese() ? 'Dự án AI mới' : 'New AI Project'),
                    prompt,
                    workspaceType: this.detectWorkspaceType(plan.workspaceType || prompt || rawMessage)
                },
                requiresApproval: false,
                returnSummary: false
            };
        }

        if (type === 'studio.seed_prompt') {
            const prompt = String(plan.prompt || rawMessage || '').trim();
            if (!prompt) return null;
            return {
                type,
                target: 'home',
                prompt,
                projectName: this.cleanProjectName(plan.projectName || this.deriveProjectNameFromPrompt(prompt)),
                workspaceType: this.detectWorkspaceType(plan.workspaceType || prompt || rawMessage),
                autoGenerate: Boolean(plan.autoGenerate || /tao|create|generate|lam/i.test(prompt)),
                targetPage: 'home',
                executePayload: {
                    prompt,
                    projectName: this.cleanProjectName(plan.projectName || this.deriveProjectNameFromPrompt(prompt)),
                    workspaceType: this.detectWorkspaceType(plan.workspaceType || prompt || rawMessage)
                },
                requiresApproval: false,
                returnSummary: false
            };
        }

        if (type === 'studio.switch_tab') {
            const tab = String(plan.tab || '').trim().toLowerCase();
            if (!['workspace', 'builder', 'notebook'].includes(tab)) return null;
            return {
                type,
                target: 'home',
                tab,
                targetPage: 'home',
                executePayload: { tab },
                requiresApproval: false,
                returnSummary: false
            };
        }

        if (type === 'studio.notebook_create') {
            return {
                type,
                target: 'home',
                createType: this.detectWorkspaceType(plan.createType || plan.workspaceType || rawMessage),
                targetPage: 'home',
                executePayload: {
                    createType: this.detectWorkspaceType(plan.createType || plan.workspaceType || rawMessage)
                },
                requiresApproval: false,
                returnSummary: false
            };
        }

        if (type === 'search.run') {
            const query = String(plan.query || rawMessage || '').trim();
            if (!query) return null;
            return {
                type,
                target: 'search',
                query,
                targetPage: 'search',
                displayText: String(plan.displayText || plan.rewrittenText || query).trim() || query,
                executePayload: {
                    query,
                    language: this.isVietnamese() ? 'vi' : 'en',
                    category: String(plan.category || '').trim()
                },
                workflowId,
                requiresApproval: false,
                returnSummary: true
            };
        }

        if (type === 'search.open') return { type, target: 'search', targetPage: 'search', requiresApproval: false, returnSummary: false };
        if (type === 'quiz.open') return { type, target: 'quiz', targetPage: 'quiz', requiresApproval: false, returnSummary: false };
        if (type === 'studio.open') return { type, target: 'home', targetPage: 'home', requiresApproval: false, returnSummary: false };
        if (type === 'settings.open') return { type, target: 'settings', targetPage: 'settings', requiresApproval: false, returnSummary: false };
        if (type === 'chat.open') return { type, target: 'chat', targetPage: 'chat', requiresApproval: false, returnSummary: false };

        if (type === 'quiz.create_room') {
            const title = String(plan.title || rawMessage || '').trim();
            return {
                type,
                target: 'quiz',
                title: title || this.buildDefaultQuizTitle(),
                audience: this.ageGroup,
                targetPage: 'quiz',
                executePayload: {
                    title: title || this.buildDefaultQuizTitle(),
                    audience: this.ageGroup
                },
                requiresApproval: false,
                returnSummary: false
            };
        }

        if (type === 'quiz.create_arena') {
            const mode = String(plan.mode || '').trim().toLowerCase();
            if (!['vortex', 'strife', 'core'].includes(mode)) return null;
            return {
                type,
                target: 'quiz',
                mode,
                targetPage: 'quiz',
                executePayload: { mode },
                requiresApproval: false,
                returnSummary: false
            };
        }

        return null;
    }

    async planCommandWithAI(rawMessage) {
        const capabilityLines = Object.values(this.capabilityRegistry)
            .map((item) => `- ${item.page}: ${item.actions.join(', ')} | ${item.description}`)
            .join('\n');
        let question = this.isVietnamese()
            ? `Phan loai yeu cau dieu khien web. Tra ve JSON chua danh sach cac lenh can thuc hien theo schema ${AI_COMMAND_SCHEMA_NOTE}. QUY TẮC: Luon tu dat ten (name/projectName) dua tren chu de neu nguoi dung quen noi. Neu nguoi dung yeu cau nhieu viec (vd: "tao project X roi search Y"), hay tach thanh nhieu lenh. Neu chi la chat, tra ve {"commands": []}. Yêu cầu: ${rawMessage}`
            : `Classify web control requests. Return a JSON with a list of commands in "commands" array following schema ${AI_COMMAND_SCHEMA_NOTE}. RULE: Always suggest a name/projectName if the user forgot. If the user asks for multiple things, split them into multiple command objects. If chat, return {"commands": []}. User request: ${rawMessage}`;

        try {
            const data = await this.requestAssistant({
                session_id: this.sessionId,
                question,
                age_group: this.ageGroup
            });
            const parsed = this.parseJsonObject(data?.answer || '');
            if (!parsed || !Array.isArray(parsed.commands) || parsed.commands.length === 0) return null;
            
            const normalized = parsed.commands
                .map(cmd => this.normalizePlannedCommand(cmd, rawMessage))
                .filter(Boolean);
            
            return normalized.length > 0 ? normalized : null;
        } catch (error) {
            console.warn('AI command planner failed.', error);
            return null;
        }
    }

    async resolveCommand(message, slash) {
        if (slash?.kind === 'command') {
            return slash.command;
        }

        const planned = await this.planCommandWithAI(message);
        if (planned) {
            return planned;
        }

        return null;
    }

    currentPage() {
        const path = String(window.location.pathname || '').toLowerCase();
        if (path.endsWith('/search.html') || path === '/search.html') return 'search';
        if (path.endsWith('/quiz.html') || path === '/quiz.html') return 'quiz';
        if (path.endsWith('/settings.html') || path === '/settings.html') return 'settings';
        if (path.includes('/skemma/chat.html') || path.endsWith('/chat.html') || path === '/chat.html') return 'chat';
        if (path.endsWith('/home.html') || path === '/home.html' || path === '/' || path.endsWith('/')) return 'home';
        return '';
    }

    pageUrl(page) {
        const map = {
            home: 'Home.html',
            search: 'Search.html',
            quiz: 'Quiz.html',
            settings: 'Settings.html',
            chat: 'Chat.html'
        };
        return map[page] || 'Home.html';
    }

    extractQuotedSegment(text) {
        const match = String(text || '').match(/["“”']([^"“”']{2,120})["“”']/);
        return match ? match[1].trim() : '';
    }

    detectWorkspaceType(text) {
        const normalized = this.normalizeForMatch(text);
        if (normalized.includes('mindmap')) return 'mindmap';
        if (normalized.includes('flashcard')) return 'flashcard';
        if (normalized.includes('report') || normalized.includes('bao cao')) return 'report';
        if (normalized.includes('presentation') || normalized.includes('trinh bay')) return 'presentation';
        if (normalized.includes('infographic') || normalized.includes('do hoa')) return 'infographic';
        if (normalized.includes('chart') || normalized.includes('bieu do')) return 'chart';
        if (normalized.includes('dashboard')) return 'dashboard';
        if (normalized.includes('podcast')) return 'podcast';
        if (normalized.includes('video')) return 'video';
        if (normalized.includes('ai test') || normalized.includes('quiz test') || normalized.includes('bai kiem tra')) return 'quiztest';
        return 'mindmap';
    }

    buildDefaultQuizTitle() {
        const stamp = new Date().toLocaleString(this.isVietnamese() ? 'vi-VN' : 'en-US', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
        return this.isVietnamese() ? `Quiz nhanh ${stamp}` : `Quick quiz ${stamp}`;
    }

    extractQuizTopic(raw) {
        const normalized = this.normalizeForMatch(raw);
        const removalPhrases = [
            'tao', 'create', 'lam', 'generate',
            'cho toi', 'giup toi', 'help me',
            'mot', 'một', 'bai', 'bài',
            'phong quiz', 'quiz room', 'quiz', 'ai test', 'test',
            've', 'về', 'about', 'for'
        ];

        let candidate = String(raw || '').trim();
        removalPhrases.forEach((phrase) => {
            const pattern = new RegExp(`\\b${this.normalizeForMatch(phrase)}\\b`, 'gi');
            candidate = this.normalizeForMatch(candidate).replace(pattern, ' ');
        });

        candidate = candidate
            .replace(/[:\-]/g, ' ')
            .replace(/\s{2,}/g, ' ')
            .trim();

        if (!candidate || candidate.length < 3) {
            return '';
        }

        if (candidate.length > 80) {
            return candidate.slice(0, 80).trim();
        }

        return candidate;
    }

    isControlCommand(command) {
        const type = String(command?.type || '').toLowerCase();
        return new Set([
            'studio.create_project',
            'studio.seed_prompt',
            'studio.switch_tab',
            'studio.notebook_create',
            'studio.open',
            'search.run',
            'search.open',
            'quiz.open',
            'quiz.create_room',
            'quiz.create_arena'
        ]).has(type);
    }

    describeControlCommand(command) {
        const type = String(command?.type || '').toLowerCase();
        const isVi = this.isVietnamese();

        if (type === 'studio.create_project') {
            return isVi
                ? `tao/mo project "${String(command.name || '').trim() || 'moi'}" trong Studio`
                : `create/open project "${String(command.name || '').trim() || 'new'}" in Studio`;
        }
        if (type === 'studio.seed_prompt') {
            return isVi ? 'nap yeu cau vao Studio' : 'seed your prompt into Studio';
        }
        if (type === 'studio.switch_tab') {
            return isVi ? `chuyen tab ${String(command.tab || 'workspace')}` : `switch to ${String(command.tab || 'workspace')} tab`;
        }
        if (type === 'studio.notebook_create') {
            return isVi ? 'tao noi dung tu Notebook' : 'create output from Notebook';
        }
        if (type === 'search.run') {
            return isVi ? `chay truy van Search "${String(command.query || '').trim()}"` : `run Search query "${String(command.query || '').trim()}"`;
        }
        if (type === 'quiz.create_room') {
            return isVi ? `tao phong quiz "${String(command.title || '').trim()}"` : `create quiz room "${String(command.title || '').trim()}"`;
        }
        if (type === 'quiz.create_arena') {
            return isVi ? `khoi tao Arena ${String(command.mode || 'vortex').toUpperCase()}` : `launch ${String(command.mode || 'vortex').toUpperCase()} Arena`;
        }
        if (type === 'search.open' || type === 'quiz.open' || type === 'studio.open') {
            return isVi ? 'chuyen sang trang ban yeu cau' : 'navigate to the requested page';
        }

        return isVi ? 'thuc hien thao tac tren web Skemi' : 'perform the requested action on Skemi web';
    }

    hasInlineApproval(text) {
        const normalized = this.normalizeForMatch(text);
        return /(cho phep|dong y|xac nhan|thuc hien ngay|ok|okay|yes|approve|allow)/.test(normalized);
    }

    isApprovalReply(text) {
        const normalized = this.normalizeForMatch(text);
        return /^\/?(cho phep|dong y|xac nhan|thuc hien|ok|okay|yes|approve|allow)\b/.test(normalized)
            || /(dong y thuc hien|xac nhan thuc hien|approve command|allow command)/.test(normalized);
    }

    isDeclineReply(text) {
        const normalized = this.normalizeForMatch(text);
        return /^\/?(khong|huy|dung|stop|cancel|deny|tu choi|bo qua)\b/.test(normalized)
            || /(khong cho phep|tu choi lenh|cancel command)/.test(normalized);
    }

    buildApprovalPrompt(command) {
        const action = this.describeControlCommand(command);
        if (this.isVietnamese()) {
            return [
                `Minh xin phep ${action}.`,
                'Chi dieu khien trong web Skemi nay (khong dieu khien chuot hay tab he thong).',
                'Tra loi "cho phep" (hoặc /allow) de thuc hien, hoặc "huy" (hoặc /cancel) de bo qua.'
            ].join('\n');
        }
        return [
            `Requesting permission to ${action}.`,
            'Control is limited to this Skemi website only (no OS mouse or external tab control).',
            'Reply "allow" (or /allow) to run, or "cancel" (or /cancel) to skip.'
        ].join('\n');
    }

    activateControlAura(durationMs = 5200) {
        document.body.classList.add('skemi-ai-controlling');
        document.body.setAttribute(
            'data-skemi-ai-state',
            this.isVietnamese() ? 'Skemi AI đang điều khiển trang web...' : 'Skemi AI is controlling this page...'
        );
        this.root?.classList.add('is-controlling');
        window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
            detail: { active: true, source: 'aichat', until: Date.now() + durationMs }
        }));

        if (this.controlAuraTimer) {
            window.clearTimeout(this.controlAuraTimer);
        }
        this.controlAuraTimer = window.setTimeout(() => this.deactivateControlAura(), durationMs);
        this.updateStopButtonVisibility();
    }

    deactivateControlAura() {
        document.body.classList.remove('skemi-ai-controlling');
        document.body.removeAttribute('data-skemi-ai-state');
        this.root?.classList.remove('is-controlling');
        if (this.controlAuraTimer) {
            window.clearTimeout(this.controlAuraTimer);
            this.controlAuraTimer = null;
        }
        window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
            detail: { active: false, source: 'aichat' }
        }));
        this.updateStopButtonVisibility();
    }

    abortCurrentRequest() {
        if (!this.requestAbortController) return false;
        this.userStoppedRequest = true;
        this.clearPendingAssistantJob();
        this.requestAbortController.abort();
        this.requestAbortController = null;
        return true;
    }

    forceStopControl() {
        if (window.__skemiAIPulseTimer) {
            window.clearTimeout(window.__skemiAIPulseTimer);
            window.__skemiAIPulseTimer = null;
        }
        this.deactivateControlAura();
        document.body.classList.remove('skemi-ai-controlling');
        document.body.removeAttribute('data-skemi-ai-state');
        this.pendingApproval = null;
        this.updateStopButtonVisibility();
    }

    stopCurrentAction() {
        let changed = false;

        if (this.pendingApproval) {
            this.pendingApproval = null;
            changed = true;
        }

        if (this.isLoading || this.requestAbortController) {
            this.abortCurrentRequest();
            this.setLoading(false);
            changed = true;
        }

        if (this.isControlVisualActive()) {
            this.forceStopControl();
            changed = true;
        }

        if (changed) {
            this.addMessage('system', this.isVietnamese()
                ? 'Đã tạm dừng thao tác hiện tại.'
                : 'The current action has been paused.', true);
            return;
        }

        this.addMessage('system', this.isVietnamese()
            ? 'Hiện không có thao tác nào đang chạy.'
            : 'There is no active action to stop.', true);
    }

    async runApprovedCommand(commandOrList) {
        const commands = Array.isArray(commandOrList) ? commandOrList : [commandOrList];
        
        // Nếu tất cả lệnh đều nhắm tới Studio (home), gửi nguyên mảng để thực hiện tuần tự chậm rãi
        const allHome = commands.every(c => c.target === 'home');
        if (allHome && commands.length > 1) {
            this.activateControlAura(commands.length * 7000); // Hào quang lâu hơn
            // Gửi nguyên mảng lệnh
            this.dispatchAICommand(commands); 
            
            // AI Chat cũng sẽ "chờ" cùng với người dùng để tạo cảm giác đồng bộ
            await new Promise(r => setTimeout(r, commands.length * 6500));
            return null;
        }

        let finalNavigation = null;
        const totalDuration = Math.max(6000, commands.length * 5500);
        this.activateControlAura(totalDuration);

        for (const cmd of commands) {
            if (this.userStoppedRequest) break;
            
            try {
                const result = await this.executeLocalCommand(cmd);
                if (result?.answer) {
                    this.addMessage('assistant', result.answer, true);
                }
                if (result?.navigateTo) {
                    finalNavigation = result.navigateTo;
                }
                // Nghỉ rất chậm giữa các tin nhắn phản hồi
                await new Promise(r => setTimeout(r, 2500)); 
            } catch (err) {
                console.error('Error in chain:', err);
            }
        }
        
        if (finalNavigation) {
            setTimeout(() => {
                if (!this.userStoppedRequest) window.location.href = finalNavigation;
            }, 1000);
        }
        return null;
    }

    buildSlashHelpText(reason = '') {
        const base = this.isVietnamese()
            ? [
                'Lệnh điều khiển nhanh:',
                '/search <nội dung> - chạy truy vấn ở Search',
                '/open <studio|search|quiz|chat|settings> - chuyển trang',
                '/tab <workspace|builder|notebook> - chuyển tab Studio',
                '/project <tên dự án> - tạo/mở project',
                '/create <yêu cầu> - tạo nội dung trong Studio',
                '/prompt <yêu cầu> - nạp yêu cầu vào Studio',
                '/notebook <mindmap|report|presentation|infographic|flashcard|podcast|video|quiztest>',
                '/quiz <chủ đề> - tạo phòng quiz',
                '/arena <vortex|strife|core> - mở Arena',
                '/stop - dừng phản hồi hoặc dừng điều khiển'
            ]
            : [
                'Quick control commands:',
                '/search <query> - run query in Search',
                '/open <studio|search|quiz|chat|settings> - navigate page',
                '/tab <workspace|builder|notebook> - switch Studio tab',
                '/project <project name> - create/open project',
                '/create <request> - create content in Studio',
                '/prompt <request> - seed prompt into Studio',
                '/notebook <mindmap|report|presentation|infographic|flashcard|podcast|video|quiztest>',
                '/quiz <topic> - create quiz room',
                '/arena <vortex|strife|core> - launch Arena',
                '/stop - stop response or control'
            ];
        if (!reason) return base.join('\n');
        return `${reason}\n\n${base.join('\n')}`;
    }

    parseSlashCommand(rawMessage) {
        const raw = String(rawMessage || '').trim();
        if (!raw.startsWith('/')) {
            return { kind: 'none' };
        }

        // Hỗ trợ chuỗi lệnh cách nhau bởi && hoặc ;
        const parts = raw.split(/\s*(&&|;)\s*/).filter(p => p !== '&&' && p !== ';');
        if (parts.length > 1) {
            const commands = parts.map(p => this.parseSlashCommand(p.trim())).filter(c => c.kind === 'command').map(c => c.command);
            return commands.length > 0 ? { kind: 'command', command: commands } : { kind: 'help' };
        }

        const line = raw.slice(1).trim();
        if (!line) {
            return { kind: 'help' };
        }

        const firstSpace = line.indexOf(' ');
        const command = (firstSpace >= 0 ? line.slice(0, firstSpace) : line).toLowerCase();
        const args = (firstSpace >= 0 ? line.slice(firstSpace + 1) : '').trim();

        if (command === 'help' || command === '?') {
            return { kind: 'help' };
        }
        if (['allow', 'approve', 'yes', 'ok', 'okay'].includes(command)) {
            return { kind: 'none' };
        }
        if (command === 'stop' || command === 'pause' || command === 'cancel') {
            return { kind: 'stop' };
        }

        if (command === 'search') {
            if (!args) return { kind: 'help', reason: this.isVietnamese() ? 'Thiếu nội dung cho /search.' : 'Missing query for /search.' };
            return {
                kind: 'command',
                command: {
                    type: 'search.run',
                    target: 'search',
                    targetPage: 'search',
                    query: args,
                    displayText: args,
                    executePayload: { query: args, language: this.isVietnamese() ? 'vi' : 'en' },
                    workflowId: `wf_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
                    requiresApproval: false,
                    returnSummary: true
                }
            };
        }

        if (command === 'open') {
            const target = args.toLowerCase();
            if (target === 'studio' || target === 'home') return { kind: 'command', command: { type: 'studio.open', target: 'home', targetPage: 'home', requiresApproval: false, returnSummary: false } };
            if (target === 'search') return { kind: 'command', command: { type: 'search.open', target: 'search', targetPage: 'search', requiresApproval: false, returnSummary: false } };
            if (target === 'quiz') return { kind: 'command', command: { type: 'quiz.open', target: 'quiz', targetPage: 'quiz', requiresApproval: false, returnSummary: false } };
            if (target === 'settings') return { kind: 'command', command: { type: 'settings.open', target: 'settings', targetPage: 'settings', requiresApproval: false, returnSummary: false } };
            if (target === 'chat') return { kind: 'command', command: { type: 'chat.open', target: 'chat', targetPage: 'chat', requiresApproval: false, returnSummary: false } };
            
            // Chi tiết hơn: Hỗ trợ /open project <tên>
            const projectMatch = args.match(/^(project|du an)\s+(.+)$/i);
            if (projectMatch) {
                return { 
                    kind: 'command', 
                    command: { type: 'studio.create_project', target: 'home', targetPage: 'home', name: projectMatch[2].trim(), requiresApproval: false, returnSummary: false } 
                };
            }
            
            return { kind: 'help', reason: this.isVietnamese() ? 'Giá trị /open không hợp lệ. Thử "/open studio" hoặc "/open project <tên>".' : 'Invalid /open target. Try "/open studio" or "/open project <name>".' };
        }

        if (command === 'tab') {
            const tab = args.toLowerCase();
            if (!['workspace', 'builder', 'notebook'].includes(tab)) {
                return { kind: 'help', reason: this.isVietnamese() ? 'Tab không hợp lệ cho /tab.' : 'Invalid tab value for /tab.' };
            }
            return { kind: 'command', command: { type: 'studio.switch_tab', target: 'home', targetPage: 'home', tab, executePayload: { tab }, requiresApproval: false, returnSummary: false } };
        }

        if (command === 'project') {
            if (!args) return { kind: 'help', reason: this.isVietnamese() ? 'Thiếu tên dự án cho /project.' : 'Missing project name for /project.' };
            return { kind: 'command', command: { type: 'studio.create_project', target: 'home', name: args, prompt: '', workspaceType: 'mindmap', forceApproval: false } };
        }

        if (command === 'prompt' || command === 'studio' || command === 'create') {
            if (!args) {
                return {
                    kind: 'help',
                    reason: this.isVietnamese()
                        ? `Thiếu nội dung cho /${command}.`
                        : `Missing prompt text for /${command}.`
                };
            }
            return {
                kind: 'command',
                command: {
                    type: 'studio.seed_prompt',
                    target: 'home',
                    prompt: args,
                    projectName: this.deriveProjectNameFromPrompt(args),
                    workspaceType: this.detectWorkspaceType(args),
                    autoGenerate: true,
                    forceApproval: false
                }
            };
        }

        if (command === 'notebook') {
            const createType = this.detectWorkspaceType(args);
            return { kind: 'command', command: { type: 'studio.notebook_create', target: 'home', createType, forceApproval: false } };
        }

        if (command === 'quiz') {
            if (!args) return { kind: 'help', reason: this.isVietnamese() ? 'Thiếu chủ đề cho /quiz.' : 'Missing topic for /quiz.' };
            return { kind: 'command', command: { type: 'quiz.create_room', target: 'quiz', title: args, audience: this.ageGroup, forceApproval: false } };
        }

        if (command === 'arena') {
            const mode = args.toLowerCase();
            if (!['vortex', 'strife', 'core'].includes(mode)) {
                return { kind: 'help', reason: this.isVietnamese() ? 'Mode không hợp lệ cho /arena.' : 'Invalid mode for /arena.' };
            }
            return { kind: 'command', command: { type: 'quiz.create_arena', target: 'quiz', mode, forceApproval: false } };
        }

        return {
            kind: 'help',
            reason: this.isVietnamese() ? `Không nhận diện lệnh "/${command}".` : `Unknown command "/${command}".`
        };
    }

    parseCommand(message) {
        const raw = String(message || '').trim();
        if (!raw) return null;

        const normalized = this.normalizeForMatch(raw);
        const quoted = this.extractQuotedSegment(raw);

        const searchMatch = normalized.match(/^(search|tim|tra cuu)\s*[:\-]?\s*(.+)$/i);
        if (searchMatch && searchMatch[2]) {
            let query = '';
            const sepIndex = raw.search(/[:\-]/);
            if (sepIndex >= 0) {
                query = raw.slice(sepIndex + 1).trim();
            } else {
                const firstSpace = raw.indexOf(' ');
                if (firstSpace >= 0) {
                    query = raw.slice(firstSpace + 1).trim();
                }
            }
            return {
                type: 'search.run',
                target: 'search',
                query: query || searchMatch[2].trim()
            };
        }

        if (/(mo|vao|open|go to).*(search|tra cuu)/.test(normalized)) {
            return { type: 'search.open', target: 'search' };
        }

        if (/(mo|vao|open|go to).*(quiz)/.test(normalized)) {
            return { type: 'quiz.open', target: 'quiz' };
        }

        if (/(mo|vao|open|go to).*(studio|home)/.test(normalized)) {
            return { type: 'studio.open', target: 'home' };
        }

        const directStudioPrompt = raw.match(/^(studio|workspace)\s*[:\-]\s*(.+)$/i);
        if (directStudioPrompt?.[2]) {
            return {
                type: 'studio.seed_prompt',
                target: 'home',
                prompt: directStudioPrompt[2].trim(),
                workspaceType: this.detectWorkspaceType(raw)
            };
        }

        const seedPromptMatch = normalized.match(/\b(nhap|dien|set)\b.*\b(prompt|yeu cau)\b.*\b(studio|workspace)\b\s*[:\-]?\s*(.+)$/i);
        if (seedPromptMatch?.[4]) {
            let prompt = '';
            const sepIndex = raw.search(/[:\-]/);
            if (sepIndex >= 0) {
                prompt = raw.slice(sepIndex + 1).trim();
            }
            return {
                type: 'studio.seed_prompt',
                target: 'home',
                prompt: prompt || seedPromptMatch[4].trim(),
                workspaceType: this.detectWorkspaceType(raw)
            };
        }

        if (/(tao|create)\s+(project|du an)/.test(normalized)) {
            let name = quoted;
            if (!name) {
                const fromColon = raw.match(/[:\-]\s*(.+)$/);
                if (fromColon?.[1]) name = fromColon[1].trim();
            }
            if (!name) {
                const fromNamed = normalized.match(/\b(la|named|ten)\s+(.+)$/i);
                if (fromNamed?.[2]) name = fromNamed[2].trim();
            }

            if (!name) {
                return { type: 'studio.create_project_missing' };
            }

            const promptMatch = normalized.match(/\b(voi|with)\s+(noi dung|prompt)\s*[:\-]?\s*(.+)$/i);
            return {
                type: 'studio.create_project',
                target: 'home',
                name,
                prompt: promptMatch?.[3]?.trim() || '',
                workspaceType: this.detectWorkspaceType(raw)
            };
        }

        const notebookIntent = /(notebook|so tay)/.test(normalized);
        const genericQuizIntent = /(tao|create|generate|lam).*(phong quiz|quiz room|quiz|bai kiem tra|ai test|test)/.test(normalized);
        if (!notebookIntent && genericQuizIntent) {
            let title = quoted;
            if (!title) {
                const fromColon = raw.match(/[:\-]\s*(.+)$/);
                if (fromColon?.[1]) title = fromColon[1].trim();
            }
            if (!title) {
                const aboutMatch = normalized.match(/\b(ve|for|about)\s+(.+)$/i);
                if (aboutMatch?.[2]) title = aboutMatch[2].trim();
            }
            if (!title) {
                title = this.extractQuizTopic(raw);
            }
            if (!title) {
                title = this.buildDefaultQuizTitle();
            }
            return {
                type: 'quiz.create_room',
                target: 'quiz',
                title,
                summary: this.isVietnamese()
                    ? `Phòng quiz do Skemi AI tạo cho chủ đề "${title}".`
                    : `Quiz room generated by Skemi AI for "${title}".`,
                audience: this.ageGroup
            };
        }

        if (/(tao|create).*(notebook|so tay).*(mindmap|flashcard|report|presentation|infographic|chart|dashboard|podcast|video|test|quiztest)/
            .test(normalized)
            || /(tao|create).*(mindmap|flashcard|report|presentation|infographic|chart|dashboard|podcast|video|test|quiztest).*(notebook|so tay)/
                .test(normalized)) {
            return {
                type: 'studio.notebook_create',
                target: 'home',
                createType: this.detectWorkspaceType(raw)
            };
        }

        if (/(vortex|strife|core)/.test(normalized) && /(arena|game|quiz|phong)/.test(normalized)) {
            let mode = 'vortex';
            if (normalized.includes('strife')) mode = 'strife';
            if (normalized.includes('core')) mode = 'core';
            return {
                type: 'quiz.create_arena',
                target: 'quiz',
                mode
            };
        }

        if (/^(vortex|strife|core)$/.test(normalized)) {
            return {
                type: 'quiz.create_arena',
                target: 'quiz',
                mode: normalized
            };
        }

        if (/(mo|chuyen|switch|open).*(workspace|khong gian ai)/.test(normalized)) {
            return { type: 'studio.switch_tab', target: 'home', tab: 'workspace' };
        }
        if (/(mo|chuyen|switch|open).*(builder|trinh dung)/.test(normalized)) {
            return { type: 'studio.switch_tab', target: 'home', tab: 'builder' };
        }
        if (/(mo|chuyen|switch|open).*(notebook|so tay)/.test(normalized)) {
            return { type: 'studio.switch_tab', target: 'home', tab: 'notebook' };
        }

        return null;
    }

    getOperatorSettings() {
        try {
            const stored = JSON.parse(localStorage.getItem('skemi_user_data') || '{}');
            const settings = stored?.settings && typeof stored.settings === 'object' ? stored.settings : {};
            return {
                ai_operator_mode: String(settings.ai_operator_mode || 'hybrid').trim().toLowerCase() || 'hybrid',
                ai_rewrite_mode: String(settings.ai_rewrite_mode || 'smart').trim().toLowerCase() || 'smart'
            };
        } catch {
            return { ai_operator_mode: 'hybrid', ai_rewrite_mode: 'smart' };
        }
    }

    shouldRequireApproval(command) {
        if (Array.isArray(command)) return command.some((item) => this.shouldRequireApproval(item));
        if (!command || typeof command !== 'object') return false;
        if (typeof command.requiresApproval === 'boolean') return command.requiresApproval;
        const type = String(command.type || '').toLowerCase();
        return type === 'chat.send'
            || type === 'settings.toggle_autoreply'
            || type === 'settings.update_ai_profile';
    }

    async rewriteOperatorDisplayText(rawText, contextType = 'search.run') {
        const source = String(rawText || '').trim();
        if (!source) return '';
        const settings = this.getOperatorSettings();
        if (settings.ai_rewrite_mode === 'exact') return source;

        const prompt = this.isVietnamese()
            ? `Viết lại ngắn gọn và tự nhiên nội dung nhập cho thao tác ${contextType}. Giữ nguyên ý định, không thêm suy đoán, không trả lời câu hỏi. Chỉ trả về đúng một dòng văn bản để điền vào input. Nội dung gốc: ${source}`
            : `Rewrite the text-entry content for action ${contextType}. Keep the same intent, add no speculation, and do not answer the question. Return exactly one natural single-line input string. Raw input: ${source}`;

        try {
            const data = await this.requestAssistant({
                session_id: this.sessionId,
                question: prompt,
                age_group: this.ageGroup
            });
            const candidate = String(data?.answer || '').replace(/^["'`]+|["'`]+$/g, '').trim();
            return candidate || source;
        } catch {
            return source;
        }
    }

    async prepareSearchCommand(command) {
        const rawQuery = String(command?.executePayload?.query || command?.query || '').trim();
        if (!rawQuery) return command;

        const explicitExact = /\b(exact|y chang|giu nguyen|giữ nguyên|verbatim)\b/i.test(String(command?.query || ''));
        const displayText = explicitExact
            ? rawQuery
            : await this.rewriteOperatorDisplayText(String(command?.displayText || rawQuery), 'search.run');

        return {
            ...command,
            target: 'search',
            targetPage: 'search',
            displayText: displayText || rawQuery,
            workflowId: String(command?.workflowId || `wf_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`),
            executePayload: {
                ...(command?.executePayload || {}),
                query: rawQuery,
                language: this.isVietnamese() ? 'vi' : 'en'
            },
            requiresApproval: false,
            returnSummary: true
        };
    }

    buildCommandPayload(command) {
        const isControl = this.isControlCommand(command);
        const dynamicDuration = 3200
            + (String(command?.name || command?.projectName || '').length * 42)
            + (String(command?.prompt || command?.query || command?.displayText || '').length * 18)
            + (command?.autoGenerate ? 1800 : 0);
        const controlDurationMs = Number(command?.controlDurationMs || Math.max(5200, dynamicDuration));
        return {
            ...command,
            source: 'aichat',
            controlScope: 'web',
            controlPulse: command?.controlPulse === false ? false : isControl,
            controlDurationMs: isControl ? controlDurationMs : 0,
            createdAt: Date.now(),
            id: String(command?.id || `cmd_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`)
        };
    }

    dispatchAICommand(command) {
        const payload = Array.isArray(command)
            ? command.map((item) => this.buildCommandPayload(item))
            : this.buildCommandPayload(command);

        const commands = Array.isArray(payload) ? payload : [payload];
        commands.forEach((item) => {
            if (item?.returnSummary && item?.workflowId) {
                this.rememberWorkflow({
                    workflowId: item.workflowId,
                    type: item.type,
                    targetPage: item.targetPage || item.target || '',
                    query: item.executePayload?.query || item.query || '',
                    displayQuery: item.displayText || item.query || ''
                });
            }
        });

        localStorage.setItem(this.pendingCommandKey, JSON.stringify(payload));
        window.dispatchEvent(new CustomEvent('skemi:ai-command', { detail: payload }));
        return payload;
    }

    parseJsonObject(text) {
        const raw = String(text || '').trim();
        if (!raw) return null;
        try {
            return JSON.parse(raw);
        } catch (_) {
            const start = raw.indexOf('{');
            const end = raw.lastIndexOf('}');
            if (start < 0 || end <= start) return null;
            try {
                return JSON.parse(raw.slice(start, end + 1));
            } catch {
                return null;
            }
        }
    }

    parseStreamAnswer(rawText) {
        const lines = String(rawText || '')
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter((line) => line.startsWith('data:'));

        if (lines.length === 0) return '';

        let answer = '';
        lines.forEach((line) => {
            const payload = line.slice(5).trim();
            if (!payload) return;
            try {
                const parsed = JSON.parse(payload);
                if (typeof parsed.token === 'string') {
                    answer += parsed.token;
                } else if (typeof parsed.answer === 'string' && !answer) {
                    answer = parsed.answer;
                }
            } catch {
                answer += payload;
            }
        });

        return answer.trim();
    }

    createStreamingAssistantMessage() {
        const emptyState = this.messagesContainer.querySelector('.ai-chat-empty');
        if (emptyState) emptyState.remove();
        const staleLoading = this.messagesContainer?.querySelectorAll('.ai-message.loading') || [];
        staleLoading.forEach((node) => node.remove());
        if (this.loadingMessageEl?.parentElement) {
            this.loadingMessageEl.remove();
        }
        this.loadingMessageEl = null;

        const root = document.createElement('div');
        root.className = 'ai-message assistant ai-message-streaming';
        root.setAttribute('data-preserve-language', 'true');
        root.setAttribute('data-message-content', 'true');
        root.setAttribute('data-no-translate', 'true');
        root.innerHTML = `
            <div class="ai-activity-rail" hidden>
                <div class="ai-activity-head">
                    <span class="ai-activity-badge">${this.escapeHtml(this.t('aichat.thinking'))}</span>
                    <span class="ai-activity-loader" aria-hidden="true"><i></i><i></i><i></i></span>
                    <span class="ai-activity-detail"></span>
                </div>
                <div class="ai-activity-query"></div>
                <div class="ai-activity-sources"></div>
            </div>
            <div class="ai-message-body"></div>
        `;

        this.messagesContainer.appendChild(root);
        this.scrollToLatest(false);

        return {
            root,
            rail: root.querySelector('.ai-activity-rail'),
            badge: root.querySelector('.ai-activity-badge'),
            detail: root.querySelector('.ai-activity-detail'),
            query: root.querySelector('.ai-activity-query'),
            sources: root.querySelector('.ai-activity-sources'),
            body: root.querySelector('.ai-message-body'),
            answerText: '',
            liveSources: new Map()
        };
    }

    renderStreamingSources(view) {
        if (!view?.sources) return;
        const items = Array.from(view.liveSources.values()).slice(-4);
        if (!items.length) {
            view.sources.innerHTML = '';
            return;
        }
        view.sources.innerHTML = items.map((item) => `
            <a class="ai-activity-source" href="${this.escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer">
                <img class="ai-activity-source-icon" src="${this.escapeHtml(item.favicon_url || '')}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">
                <span class="ai-activity-source-copy">
                    <span class="ai-activity-source-title">${this.escapeHtml(item.title || item.domain || 'Source')}</span>
                    <span class="ai-activity-source-domain">${this.escapeHtml(item.domain || '')}</span>
                </span>
            </a>
        `).join('');
    }

    applyStreamStatus(view, payload = {}) {
        if (!view?.rail) return;
        const label = String(payload.label || payload.status || '').trim();
        let detail = String(payload.detail || '').trim();
        const query = String(payload.query || '').trim();
        const provider = String(payload.provider || '').trim();
        const resultCount = Number(payload.result_count);
        const metaBits = [];

        if (provider) metaBits.push(provider.replace(/_/g, ' '));
        if (Number.isFinite(resultCount) && resultCount >= 0) {
            metaBits.push(`${resultCount} result${resultCount === 1 ? '' : 's'}`);
        }
        if (metaBits.length) {
            detail = detail ? `${detail} (${metaBits.join(' • ')})` : metaBits.join(' • ');
        }

        if (!label && !detail && !query && !payload.source) return;

        view.rail.hidden = false;
        if (label) view.badge.textContent = label;
        if (detail) {
            view.detail.textContent = detail;
        } else {
            view.detail.textContent = '';
        }
        if (query) {
            view.query.textContent = query;
        } else if (!payload.source) {
            view.query.textContent = '';
        }

        if (payload.source?.url) {
            view.liveSources.set(payload.source.url, payload.source);
            this.renderStreamingSources(view);
        }
        this.updateScrollButtonVisibility();
    }

    handleAssistantStreamEvent(view, payload = {}) {
        if (!view) return;
        const eventName = String(payload.event || '').trim().toLowerCase();

        if (typeof payload.token === 'string' && payload.token) {
            view.answerText += payload.token;
            view.body.innerHTML = this.renderAssistantHtml(view.answerText);
            this.scrollToLatest(false);
        }

        if (eventName && eventName !== 'token' && eventName !== 'complete') {
            this.applyStreamStatus(view, payload);
        }
    }

    finalizeAssistantStream(view, answer) {
        if (!view?.root) return;
        const finalAnswer = String(answer || view.answerText || '').trim();
        if (finalAnswer) {
            view.body.innerHTML = this.renderAssistantHtml(finalAnswer);
            this.messages.push({
                type: 'assistant',
                content: finalAnswer,
                timestamp: Date.now()
            });
            this.saveChatHistory();
        } else {
            view.root.remove();
        }

        if (view.rail) {
            view.rail.hidden = true;
            view.sources.innerHTML = '';
        }
        view.root.classList.remove('ai-message-streaming');
        this.scrollToLatest(false);
    }

    cancelAssistantStream(view) {
        if (!view?.root) return;
        const partial = String(view.answerText || '').trim();
        if (partial) {
            this.finalizeAssistantStream(view, partial);
        } else {
            view.root.remove();
        }
    }

    async consumeStreamResponse(response, handlers = {}) {
        if (!response?.body) {
            const rawText = await response.text();
            const answer = this.parseStreamAnswer(rawText);
            if (answer) {
                handlers.onEvent?.({ event: 'token', token: answer });
            }
            return { answer };
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let answer = '';
        let lastPayload = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            let boundaryIndex = buffer.indexOf('\n\n');
            while (boundaryIndex >= 0) {
                const rawEvent = buffer.slice(0, boundaryIndex);
                buffer = buffer.slice(boundaryIndex + 2);
                const dataLines = rawEvent
                    .split(/\r?\n/)
                    .map((line) => line.trim())
                    .filter((line) => line.startsWith('data:'));

                dataLines.forEach((line) => {
                    const rawPayload = line.slice(5).trim();
                    if (!rawPayload) return;
                    let parsed;
                    try {
                        parsed = JSON.parse(rawPayload);
                    } catch {
                        parsed = { event: 'token', token: rawPayload };
                    }
                    lastPayload = parsed;
                    if (typeof parsed.token === 'string') {
                        answer += parsed.token;
                    }
                    handlers.onEvent?.(parsed);
                });

                boundaryIndex = buffer.indexOf('\n\n');
            }
        }

        return {
            answer: answer.trim(),
            payload: lastPayload
        };
    }

    sleep(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, ms));
    }

    savePendingAssistantJob(job) {
        try {
            localStorage.setItem(this.pendingAssistantJobKey, JSON.stringify({
                ...job,
                savedAt: Date.now()
            }));
        } catch {}
    }

    readPendingAssistantJob() {
        try {
            const parsed = JSON.parse(localStorage.getItem(this.pendingAssistantJobKey) || 'null');
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch {
            return null;
        }
    }

    clearPendingAssistantJob(jobId = '') {
        try {
            const current = this.readPendingAssistantJob();
            if (!jobId || !current?.job_id || current.job_id === jobId) {
                localStorage.removeItem(this.pendingAssistantJobKey);
            }
        } catch {}
    }

    async startAssistantJob(payload, options = {}) {
        const candidates = [this.apiBaseUrl, 'http://127.0.0.1:8010', 'http://127.0.0.1:8000']
            .filter((value, index, arr) => value && arr.indexOf(value) === index);
        let lastError = null;
        for (const baseUrl of candidates) {
            try {
                const response = await fetch(`${baseUrl}/api/aichat/jobs`, {
                    method: 'POST',
                    signal: options.signal,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (!data?.job_id) throw new Error('Missing AI job id');
                if (this.apiBaseUrl !== baseUrl) this.apiBaseUrl = baseUrl;
                return { ...data, baseUrl };
            } catch (error) {
                lastError = error;
            }
        }
        throw lastError || new Error(this.t('aichat.apiError'));
    }

    async fetchAssistantJob(baseUrl, jobId) {
        const response = await fetch(`${baseUrl}/api/aichat/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    async pollAssistantJob(jobId, options = {}) {
        const startedAt = Date.now();
        const baseUrl = options.baseUrl || this.apiBaseUrl || window.location.origin;
        const view = options.view;
        let lastStatus = '';
        while (Date.now() - startedAt < 180000) {
            const data = await this.fetchAssistantJob(baseUrl, jobId);
            const status = String(data.status || '').toLowerCase();
            const stage = String(data.stage || status || 'thinking');
            const detail = String(data.detail || '').trim();
            if (view && `${stage}:${detail}` !== lastStatus) {
                lastStatus = `${stage}:${detail}`;
                this.applyStreamStatus(view, {
                    event: stage,
                    label: stage === 'completed' ? 'Ready' : stage === 'running' ? 'Thinking' : 'Routing',
                    detail: detail || (this.isVietnamese() ? 'Skemi AI ?ang x? l?...' : 'Skemi AI is working...'),
                    query: options.question || data.question || ''
                });
            }
            if (status === 'completed') return data;
            if (status === 'failed') throw new Error(data.error || data.detail || 'AI chat job failed');
            await this.sleep(900);
        }
        throw new Error(this.isVietnamese() ? 'Ph?n h?i qu? l?u, h?y th? l?i.' : 'The response took too long. Please try again.');
    }

    resumePendingAssistantJob() {
        const pending = this.readPendingAssistantJob();
        if (!pending?.job_id) return;
        if (Date.now() - Number(pending.savedAt || 0) > 20 * 60 * 1000) {
            this.clearPendingAssistantJob(pending.job_id);
            return;
        }
        const view = this.createStreamingAssistantMessage();
        this.applyStreamStatus(view, {
            event: 'resume',
            label: this.isVietnamese() ? '?ang n?i l?i' : 'Resuming',
            detail: this.isVietnamese() ? 'Trang v?a ??i, Skemi ?ang l?y ph?n h?i c?n dang d?.' : 'Page changed; Skemi is retrieving the unfinished response.',
            query: pending.question || ''
        });
        this.setLoading(true, { placeholder: false });
        this.pollAssistantJob(pending.job_id, {
            baseUrl: pending.baseUrl || this.apiBaseUrl,
            view,
            question: pending.question || ''
        }).then((data) => {
            this.finalizeAssistantStream(view, data.answer || '');
            this.clearPendingAssistantJob(pending.job_id);
        }).catch((error) => {
            console.error('Resume AI job error:', error);
            view.root.remove();
            this.addMessage('assistant', this.t('aichat.connectError'), true);
            this.clearPendingAssistantJob(pending.job_id);
        }).finally(() => {
            this.setLoading(false);
        });
    }

    async requestAssistantStream(payload, options = {}) {
        const candidates = [this.apiBaseUrl, 'http://127.0.0.1:8010', 'http://127.0.0.1:8000']
            .filter((value, index, arr) => value && arr.indexOf(value) === index);
        const requestSignal = options.signal || this.requestAbortController?.signal;
        let lastError = null;

        for (const baseUrl of candidates) {
            try {
                const streamResponse = await fetch(`${baseUrl}/ask_stream`, {
                    method: 'POST',
                    signal: requestSignal,
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload)
                });

                if (!streamResponse.ok) {
                    throw new Error(`HTTP ${streamResponse.status}`);
                }

                if (this.apiBaseUrl !== baseUrl) {
                    this.apiBaseUrl = baseUrl;
                }
                const data = await this.consumeStreamResponse(streamResponse, options);
                return {
                    answer: data.answer,
                    session_id: payload?.session_id || this.sessionId,
                    payload: data.payload || null
                };
            } catch (error) {
                lastError = error;
            }
        }

        throw lastError || new Error(this.t('aichat.apiError'));
    }

    async requestAssistant(payload, options = {}) {
        const candidates = [this.apiBaseUrl, 'http://127.0.0.1:8000', 'http://127.0.0.1:8010']
            .filter((value, index, arr) => value && arr.indexOf(value) === index);
        const requestSignal = options.signal || this.requestAbortController?.signal;

        let lastError = null;

        for (const baseUrl of candidates) {
            try {
                const currentResponse = await fetch(`${baseUrl}/ask_multi`, {
                    method: 'POST',
                    signal: requestSignal,
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload)
                });

                if (!currentResponse.ok) {
                    throw new Error(`HTTP ${currentResponse.status}`);
                }

                if (this.apiBaseUrl !== baseUrl) {
                    this.apiBaseUrl = baseUrl;
                }
                return currentResponse.json();
            } catch (error) {
                lastError = error;
            }

            try {
                const streamResponse = await fetch(`${baseUrl}/ask_stream`, {
                    method: 'POST',
                    signal: requestSignal,
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        question: payload?.question || ''
                    })
                });

                if (!streamResponse.ok) {
                    throw new Error(`HTTP ${streamResponse.status}`);
                }

                const rawStream = await streamResponse.text();
                const answer = this.parseStreamAnswer(rawStream);
                if (!answer) {
                    throw new Error('Empty stream response');
                }

                if (this.apiBaseUrl !== baseUrl) {
                    this.apiBaseUrl = baseUrl;
                }
                return {
                    answer,
                    session_id: payload?.session_id || this.sessionId
                };
            } catch (error) {
                lastError = error;
            }
        }

        throw lastError || new Error(this.t('aichat.apiError'));
    }

    createProjectRecord(name, options = {}) {
        return {
            id: `project_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            name,
            createdAt: new Date().toISOString(),
            workspace: {
                mode: 'text',
                type: options.workspaceType || 'mindmap',
                prompt: options.prompt || '',
                lastResult: null
            },
            builder: {
                title: '',
                type: 'mindmap',
                color: '#6366f1',
                branches: [],
                lastResult: null
            },
            notebook: {
                sources: [],
                activeSourceId: null,
                messages: []
            }
        };
    }

    saveProjectToStorage(command) {
        let projects = [];
        try {
            projects = JSON.parse(localStorage.getItem(this.projectStorageKey) || '[]');
        } catch {
            projects = [];
        }

        const projectName = String(command.name || '').trim();
        const prompt = String(command.prompt || '').trim();
        const workspaceType = String(command.workspaceType || 'mindmap').trim();

        const existingIndex = projects.findIndex((project) => String(project?.name || '').trim().toLowerCase() === projectName.toLowerCase());
        let project = null;

        if (existingIndex >= 0) {
            project = projects[existingIndex];
            project.workspace = project.workspace || {};
            if (prompt) project.workspace.prompt = prompt;
            project.workspace.type = workspaceType || project.workspace.type || 'mindmap';
            projects.splice(existingIndex, 1);
            projects.unshift(project);
        } else {
            project = this.createProjectRecord(projectName, { prompt, workspaceType });
            projects.unshift(project);
        }

        localStorage.setItem(this.projectStorageKey, JSON.stringify(projects));
        return project;
    }

    buildFallbackQuizQuestions(topic) {
        const isVi = this.isVietnamese();
        const base = String(topic || '').trim() || (isVi ? 'Chủ đề tổng hợp' : 'General topic');
        const pairs = isVi
            ? [
                ['Mục tiêu chính của chủ đề này là gì?', ['Hiểu bản chất', 'Học thuộc máy móc', 'Chỉ nhớ định nghĩa', 'Bỏ qua ứng dụng'], 0],
                ['Bước đầu tiên nên làm khi bắt đầu học chủ đề này?', ['Xác định nền tảng', 'Làm tất cả cùng lúc', 'Bỏ qua ví dụ', 'Không cần kế hoạch'], 0],
                ['Tiêu chí đánh giá một kết quả tốt?', ['Có cấu trúc và ví dụ rõ', 'Viết dài nhất có thể', 'Nhiều thuật ngữ khó', 'Không cần kiểm chứng'], 0],
                ['Nếu thiếu dữ liệu thì nên làm gì?', ['Bổ sung nguồn tin cậy', 'Đoán theo cảm tính', 'Bỏ qua phần thiếu', 'Sao chép nguồn bất kỳ'], 0],
                ['Hành động tiếp theo phù hợp trong Skemi?', ['Đưa sang Studio để tạo đầu ra', 'Dừng lại ngay', 'Xóa toàn bộ ghi chú', 'Chuyển chủ đề ngẫu nhiên'], 0]
            ]
            : [
                ['What is the primary objective of this topic?', ['Understand the core idea', 'Memorize blindly', 'Skip application', 'Ignore structure'], 0],
                ['What should be the first step?', ['Define the foundations', 'Do everything at once', 'Skip examples', 'Avoid planning'], 0],
                ['What marks a high-quality result?', ['Clear structure with examples', 'Longest text possible', 'Complex wording only', 'No validation'], 0],
                ['What should you do when data is missing?', ['Add reliable sources', 'Guess from intuition', 'Ignore the gap', 'Use random references'], 0],
                ['Best next action in Skemi?', ['Move to Studio for output creation', 'Stop immediately', 'Delete all notes', 'Pick a random topic'], 0]
            ];

        return pairs.map(([question, options, answer], index) => ({
            question: isVi ? `${base}: ${question}` : `${base}: ${question}`,
            options,
            answer,
            explanation: isVi ? `Câu ${index + 1} tập trung vào tư duy có cấu trúc.` : `Question ${index + 1} reinforces structured reasoning.`
        }));
    }

    async generateQuizQuestionsWithAI(topic) {
        const prompt = this.isVietnamese()
            ? `Tạo 5 câu hỏi trắc nghiệm cho chủ đề "${topic}". Trả về JSON duy nhất theo schema {"questions":[{"question":"...","options":["A","B","C","D"],"answer":0,"explanation":"..."}]}. Không thêm văn bản ngoài JSON.`
            : `Create 5 multiple-choice questions for "${topic}". Return JSON only with this schema: {"questions":[{"question":"...","options":["A","B","C","D"],"answer":0,"explanation":"..."}]}. Do not add extra text.`;

        try {
            const data = await this.requestAssistant({
                session_id: this.sessionId,
                question: prompt,
                age_group: this.ageGroup
            });
            const parsed = this.parseJsonObject(data?.answer || '');
            const questions = Array.isArray(parsed?.questions) ? parsed.questions : [];
            const normalized = questions
                .map((item) => {
                    const question = String(item?.question || '').trim();
                    const options = Array.isArray(item?.options)
                        ? item.options.map((option) => String(option || '').trim()).slice(0, 4)
                        : [];
                    const answer = Number(item?.answer ?? 0);
                    const explanation = String(item?.explanation || '').trim();
                    if (!question || options.length !== 4 || options.some((option) => !option)) return null;
                    return {
                        question,
                        options,
                        answer: Math.max(0, Math.min(3, Number.isFinite(answer) ? answer : 0)),
                        explanation
                    };
                })
                .filter(Boolean)
                .slice(0, 8);

            if (normalized.length >= 3) {
                return normalized;
            }
        } catch (error) {
            console.warn('AI quiz generation failed, using fallback questions.', error);
        }

        return this.buildFallbackQuizQuestions(topic);
    }

    async executeLocalCommand(command) {
        if (!command) return null;

        if (command.type === 'studio.create_project_missing' || (command.type === 'studio.create_project' && !command.name)) {
            // Tu dong sua loi thieu ten ngay tai day
            command.type = 'studio.create_project';
            command.name = command.name || this.deriveProjectNameFromPrompt(command.prompt || '');
        }

        if (command.type === 'studio.create_project') {
            const project = this.saveProjectToStorage(command);
            this.dispatchAICommand({
                type: 'studio.create_project',
                target: 'home',
                name: project.name,
                prompt: command.prompt || '',
                workspaceType: command.workspaceType || 'mindmap'
            });

            return {
                answer: this.isVietnamese()
                    ? `Đã tạo project "${project.name}" và sẵn sàng trong Studio.`
                    : `Project "${project.name}" has been created and is ready in Studio.`,
                navigateTo: this.currentPage() === 'home' ? '' : this.pageUrl('home')
            };
        }

        if (command.type === 'studio.switch_tab') {
            const prepared = await this.prepareSearchCommand(command);
            this.dispatchAICommand(prepared);
            return {
                answer: this.isVietnamese()
                    ? `Đã chuyển sang tab ${command.tab} trong Studio.`
                    : `Switched to the ${command.tab} tab in Studio.`,
                navigateTo: this.currentPage() === 'home' ? '' : this.pageUrl('home')
            };
        }

        if (command.type === 'studio.seed_prompt') {
            this.dispatchAICommand(command);
            return {
                answer: this.isVietnamese()
                    ? 'Đã nạp yêu cầu vào Studio để bạn tiếp tục tạo nội dung.'
                    : 'The prompt has been loaded into Studio for content generation.',
                navigateTo: this.currentPage() === 'home' ? '' : this.pageUrl('home')
            };
        }

        if (command.type === 'studio.notebook_create') {
            this.dispatchAICommand(command);
            return {
                answer: this.isVietnamese()
                    ? 'Đã gửi lệnh tạo nội dung từ Notebook trong Studio.'
                    : 'Notebook-to-output command has been sent to Studio.',
                navigateTo: this.currentPage() === 'home' ? '' : this.pageUrl('home')
            };
        }

        if (command.type === 'search.run') {
            this.dispatchAICommand(command);
            return {
                answer: this.isVietnamese()
                    ? `Đã chuẩn bị truy vấn "${command.query}" trong Search.`
                    : `Prepared "${command.query}" in Search.`,
                navigateTo: this.currentPage() === 'search' ? '' : this.pageUrl('search')
            };
        }

        if (
            command.type === 'search.open'
            || command.type === 'quiz.open'
            || command.type === 'studio.open'
            || command.type === 'chat.open'
            || command.type === 'settings.open'
        ) {
            return {
                answer: this.isVietnamese()
                    ? 'Đang chuyển trang theo yêu cầu của bạn.'
                    : 'Navigating to the requested page.',
                navigateTo: this.pageUrl(command.target || 'home')
            };
        }

        if (command.type === 'studio.create_project_missing' || command.type === 'quiz.create_room_missing') {
            // Khong bao loi nua, tu dong thuc hien voi ten mac dinh bang cach goi lai chinh no voi du lieu du
            return this.executeLocalCommand({
                ...command,
                type: command.type.replace('_missing', ''),
                name: command.name || (this.isVietnamese() ? 'Dự án thông minh' : 'Smart Project'),
                title: command.title || this.buildDefaultQuizTitle()
            });
        }

        if (command.type === 'quiz.create_room') {
            const questions = await this.generateQuizQuestionsWithAI(command.title);
            this.dispatchAICommand({
                ...command,
                questions
            });

            return {
                answer: this.isVietnamese()
                    ? `Đã tạo phòng quiz "${command.title}" với ${questions.length} câu hỏi.`
                    : `Created quiz room "${command.title}" with ${questions.length} questions.`,
                navigateTo: this.currentPage() === 'quiz' ? '' : this.pageUrl('quiz')
            };
        }

        if (command.type === 'quiz.create_arena') {
            const mode = ['vortex', 'strife', 'core'].includes(String(command.mode || '').toLowerCase())
                ? String(command.mode).toLowerCase()
                : 'vortex';
            this.dispatchAICommand({
                type: 'quiz.create_arena',
                target: 'quiz',
                mode
            });

            const modeName = mode.toUpperCase();
            return {
                answer: this.isVietnamese()
                    ? `Đã khởi tạo Arena ${modeName}.`
                    : `Arena ${modeName} has been initialized.`,
                navigateTo: this.currentPage() === 'quiz' ? '' : this.pageUrl('quiz')
            };
        }

        return null;
    }

    async sendMessage() {
        const message = this.input.value.trim();
        if (!message || this.isLoading) return;

        this.input.value = '';
        this.input.style.height = 'auto';

        this.addMessage('user', message, true);

        const slash = this.parseSlashCommand(message);
        if (slash.kind === 'help') {
            this.addMessage('assistant', this.buildSlashHelpText(slash.reason || ''), true);
            return;
        }
        if (slash.kind === 'stop') {
            this.stopCurrentAction();
            return;
        }

        if (this.pendingApproval) {
            if (this.isApprovalReply(message)) {
                const approved = this.pendingApproval.command;
                this.pendingApproval = null;
                this.updateStopButtonVisibility();
                this.setLoading(true);
                this.userStoppedRequest = false;
                this.requestAbortController = new AbortController();
                try {
                    await this.runApprovedCommand(approved);
                } catch (error) {
                    if (error?.name === 'AbortError' || this.userStoppedRequest) {
                        return;
                    }
                    console.error('Approval execution error:', error);
                    this.addMessage('assistant', this.t('aichat.connectError'), true);
                } finally {
                    this.requestAbortController = null;
                    this.userStoppedRequest = false;
                    this.setLoading(false);
                }
                return;
            }

            if (this.isDeclineReply(message)) {
                this.pendingApproval = null;
                this.updateStopButtonVisibility();
                this.addMessage('assistant', this.isVietnamese()
                    ? 'Da huy thao tac dieu khien.'
                    : 'Control action cancelled.', true);
                return;
            }

            this.addMessage('assistant', this.isVietnamese()
                ? 'Minh dang cho phep dieu khien. Tra loi "cho phep" de chay lenh, hoặc "huy" de bo qua.'
                : 'I am waiting for permission. Reply "allow" to run, or "cancel" to skip.', true);
            return;
        }

        this.setLoading(true, { placeholder: false });
        this.userStoppedRequest = false;
        this.requestAbortController = new AbortController();
        let streamView = this.createStreamingAssistantMessage();
        
        let initialLabel = this.isVietnamese() ? 'Suy nghĩ' : 'Thinking';
        let initialDetail = this.isVietnamese() ? 'Skemi đang phân tích...' : 'Skemi is analyzing...';
        
        this.applyStreamStatus(streamView, {
            event: 'thinking',
            label: initialLabel,
            detail: initialDetail,
            query: message
        });

            // AGENTIC WEB CONTROL INTERCEPTION
            const textLower = message.toLowerCase().trim();
            if (textLower.startsWith('/search ') || textLower.includes('tìm kiếm hộ tôi') || textLower.includes('tra cứu hộ tớ')) {
                const query = message.replace(/\/search/gi, '').replace(/tìm kiếm hộ tôi/gi, '').replace(/tra cứu hộ tớ/gi, '').trim();
                this.addMessage('assistant', this.isVietnamese() ? `[Skemi Phantom] Nhận lệnh. Đang tự hành thao tác tra cứu: "${query}"...` : `[Skemi Phantom] Acknowledged. Navigating to run search: "${query}"...`, true);
                
                // V19.0 persistence flag
            
            
            if (window.sessionStorage) window.sessionStorage.setItem('skemi_agent_search_query', query);
            
            setTimeout(() => {
                if (window.location.pathname.includes('Search.html')) {
                    // Already on Search page, dispatch event
                    window.dispatchEvent(new CustomEvent('skemi:ai-command', { detail: { target: 'search', action: 'write-and-submit', value: query } }));
                } else {
                    window.location.href = 'Search.html';
                }
            }, 1000);
            this.setLoading(false);
            return;
        }

        // Visual UX step: show "Thinking" briefly, then shift to "Routing"
        setTimeout(() => {
            if (!this.requestAbortController || !streamView) return;
            this.applyStreamStatus(streamView, {
                event: 'routing',
                label: this.isVietnamese() ? 'Định tuyến' : 'Routing',
                detail: this.isVietnamese() ? 'Skemi đang chọn cách trả lời tốt nhất...' : 'Skemi is choosing the best response path...',
                query: message
            });
        }, 1200);

        try {
            const command = await this.resolveCommand(message, slash);
            if (command) {
                const requiresApproval = false;
                if (requiresApproval) {
                    this.pendingApproval = { command, askedAt: Date.now() };
                    if (streamView?.root) streamView.root.remove();
                    streamView = null;
                    this.addMessage('assistant', this.buildApprovalPrompt(command), true);
                    this.updateStopButtonVisibility();
                    return;
                }

                if (streamView?.root) streamView.root.remove();
                streamView = null;
                await this.runApprovedCommand(command);
                return;
            }

            this.applyStreamStatus(streamView, {
                event: 'queued',
                label: this.isVietnamese() ? 'Đang chuẩn bị' : 'Preparing',
                detail: this.isVietnamese() ? 'Tạo job nền để không mất phản hồi khi đổi trang.' : 'Creating a background job so the answer survives page changes.',
                query: message
            });
            const job = await this.startAssistantJob({
                session_id: this.sessionId,
                question: message,
                age_group: this.ageGroup
            }, {
                signal: this.requestAbortController.signal
            });
            this.savePendingAssistantJob({
                job_id: job.job_id,
                baseUrl: job.baseUrl || this.apiBaseUrl,
                question: message,
                session_id: this.sessionId,
                age_group: this.ageGroup
            });
            const data = await this.pollAssistantJob(job.job_id, {
                baseUrl: job.baseUrl || this.apiBaseUrl,
                view: streamView,
                question: message
            });
            this.finalizeAssistantStream(streamView, data.answer);
            this.clearPendingAssistantJob(job.job_id);

            if (data.session_id && data.session_id !== this.sessionId) {
                this.sessionId = data.session_id;
                try {
                    this.chatStorage?.setItem(this.sessionIdKey, this.sessionId);
                } catch {}
            }
        } catch (error) {
            if (error?.name === 'AbortError' || this.userStoppedRequest) {
                if (streamView) this.cancelAssistantStream(streamView);
                return;
            }
            console.error('Chat error:', error);
            if (streamView) {
                streamView.root.remove();
            }
            this.addMessage('assistant', this.t('aichat.connectError'), true);
        } finally {
            this.requestAbortController = null;
            this.userStoppedRequest = false;
            this.setLoading(false);
        }
    }

    addMessage(type, content, shouldAnimate = false, extraClass = '') {
        const emptyState = this.messagesContainer.querySelector('.ai-chat-empty');
        if (emptyState) {
            emptyState.remove();
        }

        const wasNearBottom = this.isNearBottom();

        const messageDiv = document.createElement('div');
        messageDiv.className = `ai-message ${type}${extraClass ? ` ${extraClass}` : ''}`;
        messageDiv.setAttribute('data-preserve-language', 'true');
        messageDiv.setAttribute('data-message-content', 'true');
        messageDiv.setAttribute('data-no-translate', 'true');
        this.applyMessageContent(messageDiv, type, content, extraClass);

        if (type === 'system') {
            messageDiv.style.fontStyle = 'italic';
            messageDiv.style.opacity = '0.7';
            messageDiv.style.fontSize = '0.8rem';
            messageDiv.style.textAlign = 'center';
            messageDiv.style.alignSelf = 'center';
            messageDiv.style.background = 'transparent';
            messageDiv.style.border = 'none';
            messageDiv.style.color = 'var(--text-muted)';
        } else {
            messageDiv.style.opacity = '1';
            messageDiv.style.filter = 'none';
        }

        this.messagesContainer.appendChild(messageDiv);
        if (wasNearBottom || type === 'user' || extraClass === 'loading') {
            this.scrollToLatest(false);
        } else {
            this.updateScrollButtonVisibility();
        }

        if (shouldAnimate && typeof gsap !== 'undefined') {
            gsap.from(messageDiv, {
                opacity: 0,
                y: 16,
                duration: 0.24,
                ease: 'power2.out'
            });
        }

        if (type !== 'system' && extraClass !== 'loading') {
            this.messages.push({ type, content, timestamp: Date.now() });
            this.saveChatHistory();
        }

        this.updateStopButtonVisibility();

        return messageDiv;
    }

    restoreMessages() {
        if (!this.messagesContainer) {
            return;
        }

        this.messagesContainer.innerHTML = '';
        this.messages.slice(-this.maxHistoryMessages).forEach((msg) => {
            const div = document.createElement('div');
            div.className = `ai-message ${msg.type}`;
            div.setAttribute('data-preserve-language', 'true');
            div.setAttribute('data-message-content', 'true');
            div.setAttribute('data-no-translate', 'true');
            this.applyMessageContent(div, msg.type, msg.content);
            this.messagesContainer.appendChild(div);
        });
        this.scrollToLatest(false);
        this.updateStopButtonVisibility();
    }

    setTransientStatus(text) {
        if (!this.messagesContainer) return;
        
        // Clear all transient messages
        if (!text || text.trim() === '') {
            const allTransient = this.messagesContainer.querySelectorAll('.ai-message.transient');
            allTransient.forEach(el => {
                el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                el.style.opacity = '0';
                el.style.transform = 'translateY(-4px)';
                setTimeout(() => el.remove(), 320);
            });
            return;
        }

        // Check if this exact text already exists
        const existing = this.messagesContainer.querySelectorAll('.ai-message.transient');
        for (const el of existing) {
            if (el.textContent.trim() === text.trim()) return; // Don't duplicate
        }

        // Limit to max 4 transient messages
        if (existing.length >= 4) {
            const oldest = existing[0];
            oldest.style.transition = 'opacity 0.2s ease';
            oldest.style.opacity = '0';
            setTimeout(() => oldest.remove(), 220);
        }

        const transientDiv = document.createElement('div');
        transientDiv.className = 'ai-message transient';
        const span = document.createElement('span');
        span.className = 'shimmer-text';
        span.textContent = text;
        transientDiv.appendChild(span);
        this.messagesContainer.appendChild(transientDiv);
        this.scrollToLatest(true);
    }

    setLoading(loading, options = {}) {
        const showPlaceholder = options.placeholder !== false;
        this.isLoading = loading;
        this.sendBtn.disabled = loading;
        this.input.disabled = loading;

        if (loading) {
            if (this.loadingMessageEl && this.loadingMessageEl.parentElement) {
                this.loadingMessageEl.remove();
            }
            const staleLoading = this.messagesContainer?.querySelectorAll('.ai-message.loading') || [];
            staleLoading.forEach((node) => node.remove());
            this.loadingMessageEl = showPlaceholder
                ? this.addMessage('assistant', this.t('aichat.thinking'), false, 'loading')
                : null;
            this.sendBtn.innerHTML = this.getSendButtonMarkup(true);
        } else {
            if (this.loadingMessageEl && this.loadingMessageEl.parentElement) {
                this.loadingMessageEl.remove();
            }
            // Clear transient status when loading ends (final response received)
            this.setTransientStatus(null);
            
            const staleLoading = this.messagesContainer?.querySelectorAll('.ai-message.loading') || [];
            staleLoading.forEach((node) => node.remove());
            this.loadingMessageEl = null;
            this.sendBtn.innerHTML = this.getSendButtonMarkup(false);
        }
        this.updateStopButtonVisibility();
    }

    saveChatHistory() {
        try {
            if (!this.chatStorage) return;
            const currentMessages = this.messages
                .map((msg) => this.normalizeHistoryMessage(msg))
                .filter(Boolean);
            const saved = this.safeParseHistory(this.chatStorage.getItem(this.chatHistoryKey));
            const mergedMessages = this.mergeHistoryMessages(saved?.messages || [], currentMessages)
                .slice(-Math.max(this.maxHistoryMessages, 10));

            let maxCount = mergedMessages.length;
            while (maxCount >= 10) {
                const history = {
                    sessionId: saved?.sessionId || this.sessionId,
                    ageGroup: this.ageGroup,
                    messages: mergedMessages.slice(-maxCount)
                };
                const serialized = JSON.stringify(history);
                if (serialized.length <= 220000) {
                    this.chatStorage.setItem(this.chatHistoryKey, serialized);
                    this.messages = history.messages.slice(-this.maxHistoryMessages);
                    return;
                }
                maxCount -= 2;
            }

            const compact = {
                sessionId: saved?.sessionId || this.sessionId,
                ageGroup: this.ageGroup,
                messages: mergedMessages.slice(-10).map((msg) => ({
                    ...msg,
                    content: msg.content.slice(0, 1200)
                }))
            };
            this.chatStorage.setItem(this.chatHistoryKey, JSON.stringify(compact));
            this.messages = compact.messages.slice(-this.maxHistoryMessages);
        } catch (e) {
            console.warn('Could not save chat history:', e);
        }
    }

    loadChatHistory() {
        try {
            if (!this.chatStorage) return;
            const saved = this.chatStorage.getItem(this.chatHistoryKey);
            if (!saved) return;

            const history = this.safeParseHistory(saved);
            if (!history) return;
            const now = Date.now();
            const recentMessages = (history.messages || [])
                .map((msg) => this.normalizeHistoryMessage(msg))
                .filter(Boolean)
                .filter((msg) => now - msg.timestamp < 7 * 24 * 60 * 60 * 1000)
                .slice(-this.maxHistoryMessages);

            if (recentMessages.length > 0) {
                const emptyState = this.messagesContainer.querySelector('.ai-chat-empty');
                if (emptyState) emptyState.remove();

                this.messages = recentMessages;
                this.restoreMessages();

                this.sessionId = history.sessionId || this.sessionId;
                this.ageGroup = history.ageGroup || this.ageGroup;

                this.ageButtons.forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.age === this.ageGroup);
                });
            }
        } catch (e) {
            console.warn('Could not load chat history:', e);
        }
    }

    openWithMessage(message) {
        this.openChat();
        setTimeout(() => {
            this.input.value = message;
            this.input.focus();
            this.updateScrollButtonVisibility();
        }, 250);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const pathname = String(window.location.pathname || '').toLowerCase();
    const isLegacyChatPortal = pathname.includes('/skemma/chat.html');
    if (isLegacyChatPortal) {
        return;
    }

    if (window.aiChatWidget || document.getElementById('aiChatWidgetRoot')) {
        return;
    }

    if (true) {
        window.aiChatWidget = new AIChatWidget();
        const shouldAutoOpen = pathname.endsWith('/chat.html') || pathname === '/chat.html' || new URLSearchParams(window.location.search).get('openChat') === '1';
        if (shouldAutoOpen) {
            document.body.classList.add('ai-chat-page');
            window.setTimeout(() => window.aiChatWidget?.openChat(), 40);
        }

        window.openAIChat = (message) => {
            if (window.aiChatWidget) {
                window.aiChatWidget.openWithMessage(message);
            }
        };
    }
});

export default AIChatWidget;


