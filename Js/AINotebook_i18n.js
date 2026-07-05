// ========================================
// AI Notebook Controller - Source Grounded
// ========================================

class AINotebookController {
    constructor() {
        this.currentFiles = [];
        this.activeFile = null;
        this.diagramType = 'mindmap';
        this.searchMode = false;
        this.isDrawing = false;
        this.currentDrawingTool = 'select';
        this.modelSystem = 'ollama';
        this.apiBaseUrl = this.resolveApiBaseUrl();
        this.currentChart = null;

        this.init();
    }

    resolveApiBaseUrl() {
        const fromWindow = (window.SKEMI_API_BASE || '').trim();
        if (fromWindow) {
            return fromWindow.replace(/\/+$/, '');
        }

        return 'http://127.0.0.1:8010';
    }

    t(key, fallback, params = null) {
        let text = fallback;
        if (window.languageManager && typeof window.languageManager.t === 'function') {
            const translated = window.languageManager.t(key);
            text = translated && translated !== key ? translated : fallback;
        }

        if (params && typeof params === 'object') {
            Object.keys(params).forEach((k) => {
                text = text.replaceAll(`{${k}}`, params[k]);
            });
        }

        return text;
    }

    isVietnameseUI() {
        return (window.languageManager?.base || 'vi') === 'vi';
    }

    uiText(vi, en) {
        return this.isVietnameseUI() ? vi : en;
    }

    async init() {
        this.setupLayout();
        this.bindEvents();
        this.loadLibraries();
        await this.checkModelSystem();
        this.applyLanguage();

        window.addEventListener('languageChanged', () => {
            this.applyLanguage();
        });
    }

    setupLayout() {
        const dashboardContent = document.getElementById('dashboard-content');
        if (!dashboardContent) {
            return;
        }

        dashboardContent.innerHTML = this.getNotebookHTML();
    }

    getNotebookHTML() {
        return `
            <div class="ai-notebook-section active" id="notebook-section">
                <div class="notebook-container">
                    <div class="notebook-files-panel">
                        <h3 data-i18n="dashboard.files.title">Files và phan tich</h3>
                        <div class="notebook-upload-area" id="uploadArea">
                            <div class="upload-icon">Upload</div>
                            <p data-i18n="dashboard.upload.area">Kéo thả file vào đây hoặc bam de chon</p>
                            <p style="font-size: 0.8rem; color: var(--text-muted);" data-i18n="dashboard.upload.supports">
                                Ho tro: PDF, DOCX, TXT, PNG, JPG, XLSX, PPTX
                            </p>
                            <input type="file" id="fileInput" multiple accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.xlsx,.pptx" hidden>
                        </div>

                        <div class="model-info" style="margin-bottom: 16px; padding: 12px; background: var(--brand-light); border-radius: var(--radius-md); font-size: 0.85rem;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span id="modelStatus">Dang kiem tra dich vu AI...</span>
                            </div>
                        </div>

                        <div class="diagram-type-selector">
                            <div class="diagram-type-card selected" data-type="mindmap">
                                <div class="diagram-title" data-i18n="dashboard.diagram.mindmap">Mindmap</div>
                                <div class="diagram-desc" data-i18n="dashboard.diagram.mindmap.desc">So do tu duy</div>
                            </div>
                            <div class="diagram-type-card" data-type="flowchart">
                                <div class="diagram-title" data-i18n="dashboard.diagram.flowchart">Flowchart</div>
                                <div class="diagram-desc" data-i18n="dashboard.diagram.flowchart.desc">So do luong</div>
                            </div>
                            <div class="diagram-type-card" data-type="chart">
                                <div class="diagram-title" data-i18n="dashboard.diagram.chart">Chart</div>
                                <div class="diagram-desc" data-i18n="dashboard.diagram.chart.desc">Bieu do</div>
                            </div>
                            <div class="diagram-type-card" data-type="timeline">
                                <div class="diagram-title" data-i18n="dashboard.diagram.timeline">Timeline</div>
                                <div class="diagram-desc" data-i18n="dashboard.diagram.timeline.desc">Đóng thoi gian</div>
                            </div>
                        </div>

                        <div class="file-list" id="fileList"></div>
                    </div>

                    <div class="notebook-canvas-panel">
                        <div class="canvas-toolbar">
                            <button class="toolbar-btn active" id="autoGenerateBtn" data-i18n="dashboard.canvas.toolbar.auto">AI tao tu dong</button>
                            <button class="toolbar-btn" id="manualDrawBtn" data-i18n="dashboard.canvas.toolbar.manual">Ve thu cong</button>
                            <button class="toolbar-btn" id="exportBtn" data-i18n="dashboard.canvas.toolbar.export">Xuat</button>
                            <button class="toolbar-btn" id="clearBtn" data-i18n="dashboard.canvas.toolbar.clear">Xoa</button>
                        </div>
                        <div class="drawing-tools" id="drawingTools" style="display:none;">
                            <div class="drawing-tool active" data-tool="line">Line</div>
                            <div class="drawing-tool" data-tool="rectangle">Rect</div>
                            <div class="drawing-tool" data-tool="circle">Circle</div>
                            <div class="drawing-tool" data-tool="text">Text</div>
                        </div>
                        <div class="canvas-area">
                            <div id="diagramContainer" class="diagram-canvas">
                                <div style="padding:24px;color:var(--text-muted);">Chua co so do. Hay upload file hoặc dat cau hoi.</div>
                            </div>
                        </div>
                    </div>

                    <div class="notebook-chat-panel">
                        <div class="chat-header">
                            <span data-i18n="dashboard.chat.title">Skemi AI Notebook</span>
                            <button class="search-toggle" id="searchToggle" title="Che do nay chi tra loi tu nguồn upload">nguồn upload</button>
                        </div>
                        <div class="chat-messages" id="chatMessages">
                            <div class="notebook-message ai">
                                <p data-i18n="dashboard.chat.welcome">Xin chào. Upload tài liệu, toi se tra loi dua tren noi dung trong tài liệu do.</p>
                            </div>
                        </div>
                        <div class="chat-input-area">
                            <div class="chat-input-container">
                                <textarea
                                    class="chat-input"
                                    id="chatInput"
                                    data-i18n-placeholder="dashboard.chat.placeholder"
                                    placeholder="Hoi ve noi dung file da upload..."
                                    rows="1"
                                ></textarea>
                                <button class="chat-send-btn" id="chatSendBtn" data-i18n="dashboard.chat.send">Send</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    applyLanguage() {
        if (window.languageManager && typeof window.languageManager.applyLanguage === 'function') {
            window.languageManager.applyLanguage();
        }

        const setText = (selector, text) => {
            document.querySelectorAll(selector).forEach((el) => {
                el.textContent = text;
            });
        };

        setText('[data-i18n="dashboard.files.title"]', this.uiText('Files và phan tich', 'Files & analysis'));
        setText('[data-i18n="dashboard.upload.area"]', this.uiText('Kéo thả file vào đây hoặc bam de chon', 'Drop files here or click to choose'));
        setText('[data-i18n="dashboard.upload.supports"]', this.uiText('Ho tro: PDF, DOCX, TXT, PNG, JPG, XLSX, PPTX', 'Supports: PDF, DOCX, TXT, PNG, JPG, XLSX, PPTX'));
        setText('#modelStatus', this.uiText('Dang kiem tra dich vu AI...', 'Checking AI service...'));
        setText('[data-i18n="dashboard.diagram.mindmap.desc"]', this.uiText('So do tu duy', 'Mind map'));
        setText('[data-i18n="dashboard.diagram.flowchart.desc"]', this.uiText('So do luong', 'Flow chart'));
        setText('[data-i18n="dashboard.diagram.chart.desc"]', this.uiText('Bieu do', 'Chart'));
        setText('[data-i18n="dashboard.diagram.timeline.desc"]', this.uiText('Đóng thoi gian', 'Timeline'));
        setText('[data-i18n="dashboard.canvas.toolbar.auto"]', this.uiText('AI tao tu dong', 'AI auto generate'));
        setText('[data-i18n="dashboard.canvas.toolbar.manual"]', this.uiText('Ve thu cong', 'Manual draw'));
        setText('[data-i18n="dashboard.canvas.toolbar.export"]', this.uiText('Xuat', 'Export'));
        setText('[data-i18n="dashboard.canvas.toolbar.clear"]', this.uiText('Xoa', 'Clear'));
        setText('[data-i18n="dashboard.chat.title"]', 'Skemi AI Notebook');
        setText('[data-i18n="dashboard.chat.welcome"]', this.uiText('Xin chào. Upload tài liệu, toi se tra loi dua tren noi dung trong tài liệu do.', 'Hello. Upload a document and I will answer from that content.'));
        setText('[data-i18n="dashboard.chat.send"]', this.uiText('Goi', 'Send'));

        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.placeholder = this.uiText('Hoi ve noi dung file da upload...', 'Ask about the uploaded file content...');
        }

        const searchToggle = document.getElementById('searchToggle');
        if (searchToggle) {
            searchToggle.title = this.searchMode
                ? this.uiText('Che do tra loi theo nguồn và web', 'Answer mode from sources and web')
                : this.uiText('Che do nay chi tra loi tu nguồn upload', 'This mode answers only from uploaded sources');
            searchToggle.textContent = this.searchMode
                ? this.uiText('nguồn + web', 'Sources + web')
                : this.uiText('nguồn upload', 'Uploaded sources');
        }

        const diagramContainer = document.getElementById('diagramContainer');
        if (diagramContainer && !diagramContainer.children.length) {
            diagramContainer.textContent = this.uiText('Chua co so do. Hay upload file hoặc dat cau hoi.', 'No diagram yet. Upload a file or ask a question.');
        }
    }

    bindEvents() {
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');

        if (uploadArea && fileInput) {
            uploadArea.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => this.handleFileUpload(e.target.files));

            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                this.handleFileUpload(e.dataTransfer.files);
            });
        }

        document.querySelectorAll('.diagram-type-card').forEach((card) => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.diagram-type-card').forEach((c) => c.classList.remove('selected'));
                card.classList.add('selected');
                this.diagramType = card.dataset.type;

                if (this.activeFile) {
                    this.analyzeFile(this.activeFile);
                }
            });
        });

        this.bindToolbarEvents();
        this.bindChatEvents();

        const searchToggle = document.getElementById('searchToggle');
        if (searchToggle) {
            searchToggle.addEventListener('click', () => {
                this.searchMode = !this.searchMode;
                searchToggle.classList.toggle('active', this.searchMode);
                searchToggle.textContent = this.searchMode
                    ? this.uiText('nguồn + web', 'Sources + web')
                    : this.uiText('nguồn upload', 'Uploaded sources');
                this.addMessage('ai', this.searchMode
                    ? this.uiText('Da Bật chế độ tham khao web. Neu strict source bat, AI van uu tien nguồn upload.', 'Web reference mode is on. If strict source is enabled, AI still prioritizes uploaded sources.')
                    : this.uiText('Da tat tham khao web. AI se chi dua tren nguồn upload.', 'Web reference mode is off. AI now answers only from uploaded sources.'));
            });
        }
    }

    bindToolbarEvents() {
        const autoBtn = document.getElementById('autoGenerateBtn');
        const manualBtn = document.getElementById('manualDrawBtn');
        const exportBtn = document.getElementById('exportBtn');
        const clearBtn = document.getElementById('clearBtn');

        autoBtn?.addEventListener('click', () => this.toggleMode('auto'));
        manualBtn?.addEventListener('click', () => this.toggleMode('manual'));
        exportBtn?.addEventListener('click', () => this.exportDiagram());
        clearBtn?.addEventListener('click', () => this.clearCanvas());

        document.querySelectorAll('.drawing-tool').forEach((tool) => {
            tool.addEventListener('click', () => {
                document.querySelectorAll('.drawing-tool').forEach((t) => t.classList.remove('active'));
                tool.classList.add('active');
                this.currentDrawingTool = tool.dataset.tool;
            });
        });
    }

    bindChatEvents() {
        const chatInput = document.getElementById('chatInput');
        const chatSendBtn = document.getElementById('chatSendBtn');

        if (!chatInput || !chatSendBtn) {
            return;
        }

        chatSendBtn.addEventListener('click', () => this.sendChatMessage());
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendChatMessage();
            }
        });

        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = `${Math.min(chatInput.scrollHeight, 100)}px`;
        });
    }

    loadLibraries() {
        if (typeof mermaid === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
            script.onload = () => {
                mermaid.initialize({ startOnLoad: false });
            };
            document.head.appendChild(script);
        }

        if (typeof Chart === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
            document.head.appendChild(script);
        }
    }

    async checkModelSystem() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/model_info`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const modelInfo = await response.json();
            this.modelSystem = modelInfo.system || 'ollama';
            if (this.modelSystem === 'ollama' || this.modelSystem === 'ollama_http') {
                this.showNotification('Dich vu AI da san sang', 'success');
            } else {
                this.showNotification('Dang chay o che do du phong', 'warning');
            }
        } catch (error) {
            console.error('Model check error:', error);
            this.modelSystem = 'offline';
            this.showNotification('Dich vu AI tam thoi gian doan. Vui long thu lai sau.', 'warning');
        }
    }

    validateFile(file) {
        const allowedTypes = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain',
            'image/png',
            'image/jpeg',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        ];

        const maxSize = 50 * 1024 * 1024;

        if (!allowedTypes.includes(file.type)) {
            this.showNotification('Dinh dang file chua ho tro', 'error');
            return false;
        }

        if (file.size > maxSize) {
            this.showNotification('File vuot qua 50MB', 'error');
            return false;
        }

        return true;
    }

    async readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                resolve({
                    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                    name: file.name,
                    type: file.type,
                    size: file.size,
                    content: e.target.result,
                    uploadedAt: new Date().toISOString()
                });
            };
            reader.onerror = reject;

            if (file.type.startsWith('image/')) {
                reader.readAsDataURL(file);
            } else {
                reader.readAsText(file);
            }
        });
    }

    async handleFileUpload(files) {
        const fileArray = Array.from(files || []);
        if (fileArray.length === 0) {
            return;
        }

        for (const file of fileArray) {
            if (!this.validateFile(file)) {
                continue;
            }

            const fileData = await this.readFile(file);
            this.currentFiles.push(fileData);
            this.activeFile = fileData;
            this.updateFileList();
            await this.analyzeFile(fileData);
        }
    }

    updateFileList() {
        const fileList = document.getElementById('fileList');
        if (!fileList) {
            return;
        }

        fileList.innerHTML = '';
        this.currentFiles.forEach((file) => {
            const item = document.createElement('div');
            item.className = `file-item ${file.id === this.activeFile?.id ? 'active' : ''}`;

            const info = document.createElement('div');
            info.className = 'file-info';

            const name = document.createElement('div');
            name.className = 'file-name';
            name.textContent = file.name;

            const meta = document.createElement('div');
            meta.className = 'file-meta';
            meta.textContent = `${this.formatFileSize(file.size)} | ${new Date(file.uploadedAt).toLocaleString()}`;

            info.appendChild(name);
            info.appendChild(meta);

            const removeBtn = document.createElement('button');
            removeBtn.className = 'file-remove';
            removeBtn.type = 'button';
            removeBtn.textContent = 'x';

            item.appendChild(info);
            item.appendChild(removeBtn);

            item.addEventListener('click', () => {
                this.activeFile = file;
                this.updateFileList();
                this.analyzeFile(file);
            });

            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.currentFiles = this.currentFiles.filter((f) => f.id !== file.id);
                if (this.activeFile?.id === file.id) {
                    this.activeFile = this.currentFiles[0] || null;
                }
                this.updateFileList();
            });

            fileList.appendChild(item);
        });
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    }

    async analyzeFile(fileData) {
        this.addMessage('ai', `${this.uiText('Dang phan tich file', 'Analyzing file')}: ${fileData.name}`);

        try {
            const response = await fetch(`${this.apiBaseUrl}/analyze_file`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_data: fileData,
                    diagram_type: this.diagramType
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Analyze failed');
            }

            this.addMessage('ai', `${this.uiText('Da phan tich xong. Dang tao', 'Analysis complete. Generating')} ${this.diagramType}.`);
            await this.generateDiagram(result.analysis);
        } catch (error) {
            console.error('analyzeFile error:', error);
            this.addMessage('ai', this.uiText('Khong phan tich duoc file nay. Vui long thu file khac.', 'This file could not be analyzed. Please try another file.'));
        }
    }

    async generateDiagram(analysis) {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        container.innerHTML = '<div class="loading-spinner"></div>';

        try {
            const response = await fetch(`${this.apiBaseUrl}/generate_diagram`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis,
                    type: this.diagramType,
                    search_mode: this.searchMode
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Diagram failed');
            }

            this.renderDiagram(result.diagram);
        } catch (error) {
            console.error('generateDiagram error:', error);
            container.innerHTML = '<div style="padding:20px;color:var(--accent-rose);">Khong tao duoc so do.</div>';
        }
    }

    renderDiagram(diagramData) {
        if (this.diagramType === 'chart') {
            this.renderChart(diagramData);
            return;
        }

        if (this.diagramType === 'timeline') {
            this.renderTimeline(diagramData);
            return;
        }

        this.renderMermaid(diagramData);
    }

    renderMermaid(diagramData) {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        const mermaidText = diagramData?.mermaid || 'graph TD; A[Bắt đầu] --> B[Khong co du lieu];';
        container.innerHTML = `<div class="mermaid">${mermaidText}</div>`;
        if (typeof mermaid !== 'undefined') {
            mermaid.run({ querySelector: '.mermaid' });
        }
    }

    renderChart(chartData) {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        container.innerHTML = '<canvas id="notebookChartCanvas"></canvas>';
        const chartCanvas = document.getElementById('notebookChartCanvas');
        if (!chartCanvas || typeof Chart === 'undefined') {
            return;
        }

        if (this.currentChart) {
            this.currentChart.destroy();
            this.currentChart = null;
        }

        this.currentChart = new Chart(chartCanvas, {
            type: chartData?.type || 'bar',
            data: chartData?.data || {
                labels: ['A', 'B', 'C'],
                datasets: [{
                    label: 'Gia tri',
                    data: [10, 6, 12],
                    backgroundColor: ['#6366f1', '#8b5cf6', '#0ea5e9']
                }]
            },
            options: chartData?.options || { responsive: true, maintainAspectRatio: false }
        });
    }

    renderTimeline(timelineData) {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        const events = timelineData?.events || [];
        if (events.length === 0) {
            container.innerHTML = '<div style="padding:20px;color:var(--text-muted);">Khong co moc thoi gian.</div>';
            return;
        }

        const html = events.map((event) => (
            `<div style="margin:12px 0;padding:12px;background:var(--bg-tertiary);border-left:4px solid var(--brand-primary);border-radius:8px;">
                <strong>${event.date || ''}</strong><br>
                <span>${event.title || ''}</span><br>
                <small style="color:var(--text-muted);">${event.description || ''}</small>
            </div>`
        )).join('');

        container.innerHTML = `<div style="padding:16px;">${html}</div>`;
    }

    toggleMode(mode) {
        const autoBtn = document.getElementById('autoGenerateBtn');
        const manualBtn = document.getElementById('manualDrawBtn');
        const drawingTools = document.getElementById('drawingTools');

        if (!autoBtn || !manualBtn || !drawingTools) {
            return;
        }

        this.isDrawing = mode === 'manual';
        autoBtn.classList.toggle('active', mode === 'auto');
        manualBtn.classList.toggle('active', mode === 'manual');
        drawingTools.style.display = mode === 'manual' ? 'flex' : 'none';

        if (mode === 'manual') {
            this.initManualDrawing();
        }
    }

    initManualDrawing() {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        container.innerHTML = '<canvas id="manualCanvas" style="width:100%;height:420px;border:1px solid var(--border-light);border-radius:12px;background:#fff"></canvas>';
        const canvas = document.getElementById('manualCanvas');
        if (!canvas) {
            return;
        }

        canvas.width = canvas.clientWidth;
        canvas.height = 420;

        const ctx = canvas.getContext('2d');
        let drawing = false;
        let startX = 0;
        let startY = 0;

        canvas.addEventListener('mousedown', (e) => {
            drawing = true;
            startX = e.offsetX;
            startY = e.offsetY;
        });

        canvas.addEventListener('mousemove', (e) => {
            if (!drawing) {
                return;
            }

            if (this.currentDrawingTool === 'line') {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.strokeStyle = '#6366f1';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(startX, startY);
                ctx.lineTo(e.offsetX, e.offsetY);
                ctx.stroke();
            }
        });

        canvas.addEventListener('mouseup', () => {
            drawing = false;
        });
    }

    async sendChatMessage() {
        const input = document.getElementById('chatInput');
        const message = input?.value.trim();
        if (!message) {
            return;
        }

        this.addMessage('user', message);
        input.value = '';
        input.style.height = 'auto';

        if (!this.activeFile) {
            this.addMessage('ai', this.uiText('Ban chua upload nguồn. Hay upload file/anh truoc khi dat cau hoi.', 'No source has been uploaded yet. Upload a file or image before asking.'));
            return;
        }

        await this.processAIMessage(message);
    }

    async processAIMessage(message) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/notebook_chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    file_context: this.activeFile,
                    search_mode: this.searchMode,
                    strict_source: true
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            this.addMessage('ai', result.response || this.uiText('Chua nhan duoc phan hoi. Vui long thu lai.', 'No response received yet. Please try again.'), result.sources || []);
        } catch (error) {
            console.error('Notebook chat error:', error);
            this.addMessage('ai', this.uiText('Notebook tam thoi chua kha dung. Vui long thu lai sau.', 'Notebook is temporarily unavailable. Please try again later.'));
        }
    }

    addMessage(type, content, sources = []) {
        const messagesContainer = document.getElementById('chatMessages');
        if (!messagesContainer) {
            return;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `notebook-message ${type}`;
        messageDiv.setAttribute('data-preserve-language', 'true');
        messageDiv.setAttribute('data-message-content', 'true');
        messageDiv.setAttribute('data-no-translate', 'true');

        const textP = document.createElement('p');
        textP.setAttribute('data-preserve-language', 'true');
        textP.setAttribute('data-message-content', 'true');
        textP.setAttribute('data-no-translate', 'true');
        textP.textContent = content;
        messageDiv.appendChild(textP);

        if (Array.isArray(sources) && sources.length > 0) {
            const sourceBox = document.createElement('div');
            sourceBox.className = 'message-sources';
            sourceBox.setAttribute('data-preserve-language', 'true');
            sourceBox.setAttribute('data-no-translate', 'true');

            const sourceTitle = document.createElement('strong');
            sourceTitle.textContent = this.uiText('nguồn:', 'Sources:');
            sourceBox.appendChild(sourceTitle);

            sources.forEach((source) => {
                const row = document.createElement('div');
                row.className = 'source-item';

                if (source.url) {
                    const a = document.createElement('a');
                    a.className = 'source-link';
                    a.href = source.url;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.textContent = source.title || source.url;
                    row.appendChild(a);
                } else {
                    const span = document.createElement('span');
                    span.textContent = source.title || this.uiText('nguồn upload', 'Uploaded source');
                    row.appendChild(span);
                }

                sourceBox.appendChild(row);
            });

            messageDiv.appendChild(sourceBox);
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    exportDiagram() {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        if (typeof html2canvas === 'undefined') {
            this.exportAsText();
            return;
        }

        html2canvas(container)
            .then((canvas) => {
                const link = document.createElement('a');
                link.download = `diagram_${Date.now()}.png`;
                link.href = canvas.toDataURL();
                link.click();
            })
            .catch(() => {
                this.exportAsText();
            });
    }

    exportAsText() {
        const container = document.getElementById('diagramContainer');
        if (!container) {
            return;
        }

        const blob = new Blob([container.innerText || ''], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `diagram_${Date.now()}.txt`;
        link.click();
        URL.revokeObjectURL(url);
    }

    clearCanvas() {
        const container = document.getElementById('diagramContainer');
        if (container) {
            container.innerHTML = '<div style="padding:24px;color:var(--text-muted);">Da xoa noi dung.</div>';
        }

        if (this.currentChart) {
            this.currentChart.destroy();
            this.currentChart = null;
        }

        this.addMessage('ai', this.uiText('Da xoa noi dung so do hiện tại.', 'The current diagram content has been cleared.'));
    }

    showNotification(message, type = 'info') {
        const modelStatus = document.getElementById('modelStatus');
        if (modelStatus) {
            modelStatus.textContent = message;
        }

        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
            return;
        }

        if (type === 'error') {
            console.error(message);
        } else {
            (function(){})(message);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const dashboardContent = document.getElementById('dashboard-content');
    if (!dashboardContent) {
        return;
    }

    if (!window.aiNotebookController) {
        window.aiNotebookController = new AINotebookController();
    }
});
