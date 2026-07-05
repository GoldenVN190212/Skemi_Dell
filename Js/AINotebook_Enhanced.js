# ========================================
# AI Notebook Controller - Enhanced with Ollama Integration
# ========================================

class AINotebookController {
    constructor() {
        this.currentFiles = [];
        this.activeFile = null;
        this.diagramType = 'mindmap';
        this.searchMode = false;
        this.chatHistory = [];
        this.isDrawing = false;
        this.currentDrawingTool = 'select';
        this.modelSystem = 'ollama'; // 'ollama' or 'mock'
        
        this.init();
    }

    async init() {
        this.setupLayout();
        this.bindEvents();
        await this.checkModelSystem();
        this.loadLibraries();
    }

    async checkModelSystem() {
        try {
            const response = await fetch('http://127.0.0.1:8010/model_info');
            const modelInfo = await response.json();
            this.modelSystem = modelInfo.system || 'ollama';
            
            if (this.modelSystem === 'ollama' || this.modelSystem === 'ollama_http') {
                this.showNotification('✅ Đã kết nối Ollama models', 'success');
            } else {
                this.showNotification('⚠️ Đang dùng chế độ giả lập', 'warning');
            }
        } catch (error) {
            console.error('Model check error:', error);
            this.modelSystem = 'offline';
        }
    }

    setupLayout() {
        // Check if notebook section exists
        const existingSection = document.getElementById('notebook-section');
        if (existingSection) {
            return; // Already initialized
        }

        // Create notebook layout
        const notebookHTML = `
            <div class="ai-notebook-section" id="notebook-section">
                <div class="notebook-container">
                    <!-- Files Panel -->
                    <div class="notebook-files-panel">
                        <h3>📁 Files & Analysis</h3>
                        <div class="notebook-upload-area" id="uploadArea">
                            <div class="upload-icon">📤</div>
                            <p>Drop files here or click to browse</p>
                            <p style="font-size: 0.8rem; color: var(--text-muted);">
                                Supports: PDF, DOCX, TXT, Images, Excel, PowerPoint
                            </p>
                            <input type="file" id="fileInput" multiple accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.xlsx,.pptx" hidden>
                        </div>
                        
                        <div class="model-info" id="modelInfo" style="margin-bottom: 20px; padding: 12px; background: var(--brand-light); border-radius: var(--radius-md); font-size: 0.85rem;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span>🤖</span>
                                <span id="modelStatus">Checking models...</span>
                            </div>
                        </div>
                        
                        <div class="diagram-type-selector">
                            <div class="diagram-type-card selected" data-type="mindmap">
                                <div class="diagram-icon">🧠</div>
                                <div class="diagram-title">Mindmap</div>
                                <div class="diagram-desc">Sơ đồ tư duy</div>
                            </div>
                            <div class="diagram-type-card" data-type="flowchart">
                                <div class="diagram-icon">📊</div>
                                <div class="diagram-title">Flowchart</div>
                                <div class="diagram-desc">Sơ đồ luồng</div>
                            </div>
                            <div class="diagram-type-card" data-type="chart">
                                <div class="diagram-icon">📈</div>
                                <div class="diagram-title">Chart</div>
                                <div class="diagram-desc">Biểu đồ & Đồ thị</div>
                            </div>
                            <div class="diagram-type-card" data-type="timeline">
                                <div class="diagram-icon">📅</div>
                                <div class="diagram-title">Timeline</div>
                                <div class="diagram-desc">Dòng thời gian</div>
                            </div>
                        </div>
                        
                        <div class="file-list" id="fileList">
                            <!-- Files will be listed here -->
                        </div>
                    </div>

                    <!-- Canvas Panel -->
                    <div class="notebook-canvas-panel">
                        <div class="canvas-toolbar">
                            <button class="toolbar-btn active" id="autoGenerateBtn">🤖 AI Generate</button>
                            <button class="toolbar-btn" id="manualDrawBtn">✏️ Manual Draw</button>
                            <button class="toolbar-btn" id="exportBtn">💾 Export</button>
                            <button class="toolbar-btn" id="clearBtn">🗑️ Clear</button>
                        </div>
                        <div class="drawing-tools" id="drawingTools" style="display: none;">
                            <div class="drawing-tool active" data-tool="select">↖️</div>
                            <div class="drawing-tool" data-tool="rectangle">▭</div>
                            <div class="drawing-tool" data-tool="circle">○</div>
                            <div class="drawing-tool" data-tool="line">╱</div>
                            <div class="drawing-tool" data-tool="text">T</div>
                            <div class="drawing-tool" data-tool="arrow">→</div>
                        </div>
                        <div class="canvas-area">
                            <div id="diagramContainer" class="diagram-canvas"></div>
                        </div>
                    </div>

                    <!-- AI Chat Panel -->
                    <div class="notebook-chat-panel">
                        <div class="chat-header">
                            <span>💬 AI Assistant</span>
                            <button class="search-toggle" id="searchToggle">🔍 Search Web</button>
                        </div>
                        <div class="chat-messages" id="chatMessages">
                            <div class="notebook-message ai">
                                <p>Xin chào! Tôi là AI Assistant của Skemi. Upload file và tôi sẽ giúp bạn phân tích và tạo các sơ đồ, biểu đồ chuyên nghiệp.</p>
                            </div>
                        </div>
                        <div class="chat-input-area">
                            <div class="chat-input-container">
                                <textarea 
                                    class="chat-input" 
                                    id="chatInput" 
                                    placeholder="Hỏi về file đã upload hoặc yêu cầu tạo sơ đồ..."
                                    rows="1"
                                ></textarea>
                                <button class="chat-send-btn" id="chatSendBtn">➤</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Replace existing sections or add to main content
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.innerHTML = notebookHTML;
        }
    }

    bindEvents() {
        // File upload events
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        
        if (uploadArea && fileInput) {
            uploadArea.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => this.handleFileUpload(e.target.files));
            
            // Drag and drop
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

        // Diagram type selection
        document.querySelectorAll('.diagram-type-card').forEach(card => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.diagram-type-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                this.diagramType = card.dataset.type;
            });
        });

        // Toolbar events
        this.bindToolbarEvents();

        // Chat events
        this.bindChatEvents();

        // Search toggle
        const searchToggle = document.getElementById('searchToggle');
        if (searchToggle) {
            searchToggle.addEventListener('click', () => {
                this.searchMode = !this.searchMode;
                searchToggle.classList.toggle('active');
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

        // Drawing tools
        document.querySelectorAll('.drawing-tool').forEach(tool => {
            tool.addEventListener('click', () => {
                document.querySelectorAll('.drawing-tool').forEach(t => t.classList.remove('active'));
                tool.classList.add('active');
                this.currentDrawingTool = tool.dataset.tool;
            });
        });
    }

    bindChatEvents() {
        const chatInput = document.getElementById('chatInput');
        const chatSendBtn = document.getElementById('chatSendBtn');
        
        if (chatInput && chatSendBtn) {
            chatSendBtn.addEventListener('click', () => this.sendChatMessage());
            chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendChatMessage();
                }
            });

            // Auto-resize textarea
            chatInput.addEventListener('input', () => {
                chatInput.style.height = 'auto';
                chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
            });
        }
    }

    loadLibraries() {
        // Load Mermaid for diagrams
        if (typeof mermaid === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
            script.onload = () => {
                mermaid.initialize({ startOnLoad: false });
            };
            document.head.appendChild(script);
        }

        // Load Chart.js for charts
        if (typeof Chart === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
            document.head.appendChild(script);
        }
    }

    async handleFileUpload(files) {
        for (let file of files) {
            if (this.validateFile(file)) {
                const fileData = await this.processFile(file);
                this.currentFiles.push(fileData);
                this.updateFileList();
                
                if (this.currentFiles.length === 1) {
                    this.activeFile = fileData;
                    await this.analyzeFile(fileData);
                }
            }
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
        
        const maxSize = 50 * 1024 * 1024; // 50MB
        
        if (!allowedTypes.includes(file.type)) {
            this.showNotification('File type not supported', 'error');
            return false;
        }
        
        if (file.size > maxSize) {
            this.showNotification('File size too large (max 50MB)', 'error');
            return false;
        }
        
        return true;
    }

    async processFile(file) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            
            reader.onload = (e) => {
                resolve({
                    id: Date.now() + '_' + Math.random().toString(36).substr(2, 9),
                    name: file.name,
                    type: file.type,
                    size: file.size,
                    content: e.target.result,
                    uploadedAt: new Date().toISOString()
                });
            };
            
            if (file.type.startsWith('image/')) {
                reader.readAsDataURL(file);
            } else {
                reader.readAsText(file);
            }
        });
    }

    updateFileList() {
        const fileList = document.getElementById('fileList');
        if (!fileList) return;
        
        fileList.innerHTML = this.currentFiles.map(file => `
            <div class="file-item ${file.id === this.activeFile?.id ? 'active' : ''}" data-file-id="${file.id}">
                <div class="file-icon">${this.getFileIcon(file.type)}</div>
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-meta">${this.formatFileSize(file.size)} • ${new Date(file.uploadedAt).toLocaleString()}</div>
                </div>
                <div class="file-remove" data-file-id="${file.id}">✕</div>
            </div>
        `).join('');

        // Add click events to file items
        fileList.querySelectorAll('.file-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (!e.target.classList.contains('file-remove')) {
                    const fileId = item.dataset.fileId;
                    this.selectFile(fileId);
                }
            });
        });

        // Add remove events
        fileList.querySelectorAll('.file-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const fileId = btn.dataset.fileId;
                this.removeFile(fileId);
            });
        });
    }

    getFileIcon(type) {
        if (type.startsWith('image/')) return '🖼️';
        if (type.includes('pdf')) return '📄';
        if (type.includes('word')) return '📝';
        if (type.includes('excel')) return '📊';
        if (type.includes('powerpoint')) return '📽';
        if (type.includes('text')) return '📄';
        return '📄';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    selectFile(fileId) {
        this.activeFile = this.currentFiles.find(f => f.id === fileId);
        this.updateFileList();
        this.analyzeFile(this.activeFile);
    }

    removeFile(fileId) {
        this.currentFiles = this.currentFiles.filter(f => f.id !== fileId);
        if (this.activeFile?.id === fileId) {
            this.activeFile = this.currentFiles[0] || null;
        }
        this.updateFileList();
        if (this.activeFile) {
            this.analyzeFile(this.activeFile);
        }
    }

    async analyzeFile(fileData) {
        this.addMessage('ai', `Đang phân tích file "${fileData.name}"...`);
        
        try {
            const response = await fetch('http://127.0.0.1:8010/analyze_file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_data: fileData,
                    diagram_type: this.diagramType
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.addMessage('ai', `Đã phân tích xong! Tôi đề xuất tạo ${this.diagramType} với các chủ đề chính: ${result.topics.join(', ')}`);
                this.generateDiagram(result.analysis);
            } else {
                this.addMessage('ai', 'Xin lỗi, có lỗi xảy ra khi phân tích file. Vui lòng thử lại.');
            }
        } catch (error) {
            console.error('File analysis error:', error);
            this.addMessage('ai', 'Service is temporarily unavailable. Please check your network and try again.');
        }
    }

    async generateDiagram(analysis) {
        const container = document.getElementById('diagramContainer');
        if (container) {
            container.innerHTML = '<div class="loading-spinner"></div>';
        }
        
        try {
            const response = await fetch('http://127.0.0.1:8010/generate_diagram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis: analysis,
                    type: this.diagramType,
                    search_mode: this.searchMode
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.renderDiagram(result.diagram);
                this.addMessage('ai', `Đã tạo ${this.diagramType} thành công!`, result.sources);
            } else {
                this.addMessage('ai', 'Không thể tạo diagram. Vui lòng thử lại.');
            }
        } catch (error) {
            console.error('Diagram generation error:', error);
            this.addMessage('ai', 'Lỗi kết nối server khi tạo diagram.');
        }
    }

    renderDiagram(diagramData) {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        switch (this.diagramType) {
            case 'mindmap':
            case 'flowchart':
                this.renderMermaidDiagram(diagramData);
                break;
            case 'chart':
                this.renderChart(diagramData);
                break;
            case 'timeline':
                this.renderTimeline(diagramData);
                break;
            default:
                container.innerHTML = '<p>Diagram type not supported</p>';
        }
    }

    renderMermaidDiagram(diagramData) {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        container.innerHTML = `<div class="mermaid">${diagramData.mermaid || 'graph TD; A[Node1]; B[Node2]; A --> B;'}</div>`;
        
        if (typeof mermaid !== 'undefined') {
            mermaid.run();
        }
    }

    renderChart(chartData) {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        container.innerHTML = '<canvas id="chartCanvas"></canvas>';
        
        if (typeof Chart !== 'undefined') {
            new Chart(document.getElementById('chartCanvas'), {
                type: chartData.type || 'bar',
                data: chartData.data || {
                    labels: ['Category A', 'Category B', 'Category C'],
                    datasets: [{
                        label: 'Data',
                        data: [12, 19, 8],
                        backgroundColor: ['#6366f1', '#10b981', '#f59e0b']
                    }]
                },
                options: chartData.options || {}
            });
        }
    }

    renderTimeline(timelineData) {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        const events = timelineData.events || [
            { date: '2024-01-15', title: 'Phase 1: Analysis', description: 'Initial analysis and planning' },
            { date: '2024-02-01', title: 'Phase 2: Implementation', description: 'Execute the plan' },
            { date: '2024-03-15', title: 'Phase 3: Review', description: 'Evaluate and optimize' }
        ];
        
        container.innerHTML = `
            <div style="padding: 20px;">
                ${events.map(event => `
                    <div style="margin-bottom: 20px; padding: 15px; background: var(--bg-tertiary); border-radius: var(--radius-md); border-left: 4px solid var(--brand-primary);">
                        <strong>${event.date}</strong><br>
                        ${event.title}<br>
                        <small style="color: var(--text-muted);">${event.description}</small>
                    </div>
                `).join('')}
            </div>
        `;
    }

    toggleMode(mode) {
        this.isDrawing = mode === 'manual';
        const autoBtn = document.getElementById('autoGenerateBtn');
        const manualBtn = document.getElementById('manualDrawBtn');
        const drawingTools = document.getElementById('drawingTools');
        
        if (autoBtn && manualBtn && drawingTools) {
            if (mode === 'manual') {
                autoBtn.classList.remove('active');
                manualBtn.classList.add('active');
                drawingTools.style.display = 'flex';
                this.initManualDrawing();
            } else {
                manualBtn.classList.remove('active');
                autoBtn.classList.add('active');
                drawingTools.style.display = 'none';
            }
        }
    }

    initManualDrawing() {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        container.innerHTML = '<canvas id="drawingCanvas" style="width: 100%; height: 400px; border: 1px solid var(--border-light); border-radius: var(--radius-md);"></canvas>';
        
        const canvas = document.getElementById('drawingCanvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // Set canvas size
        canvas.width = canvas.offsetWidth;
        canvas.height = 400;
        
        let isDrawing = false;
        let startX, startY;
        
        canvas.addEventListener('mousedown', (e) => {
            isDrawing = true;
            startX = e.offsetX;
            startY = e.offsetY;
        });
        
        canvas.addEventListener('mousemove', (e) => {
            if (!isDrawing) return;
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = '#6366f1';
            ctx.lineWidth = 2;
            
            if (this.currentDrawingTool === 'line') {
                ctx.beginPath();
                ctx.moveTo(startX, startY);
                ctx.lineTo(e.offsetX, e.offsetY);
                ctx.stroke();
            }
        });
        
        canvas.addEventListener('mouseup', () => {
            isDrawing = false;
        });
    }

    async sendChatMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        
        if (!message) return;
        
        this.addMessage('user', message);
        input.value = '';
        input.style.height = 'auto';
        
        // Simulate AI response
        setTimeout(() => {
            this.processAIMessage(message);
        }, 1000);
    }

    async processAIMessage(message) {
        try {
            const response = await fetch('http://127.0.0.1:8010/notebook_chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    file_context: this.activeFile,
                    search_mode: this.searchMode
                })
            });
            
            const result = await response.json();
            this.addMessage('ai', result.response, result.sources);
        } catch (error) {
            console.error('Chat error:', error);
            this.addMessage('ai', 'Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.');
        }
    }

    addMessage(type, content, sources = null) {
        const messagesContainer = document.getElementById('chatMessages');
        if (!messagesContainer) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `notebook-message ${type}`;
        
        let messageHTML = `<p>${content}</p>`;
        
        if (sources && sources.length > 0) {
            messageHTML += `
                <div class="message-sources">
                    <strong>Nguồn:</strong>
                    ${sources.map(source => `
                        <div class="source-item">
                            <a href="${source.url}" target="_blank" class="source-link">${source.title}</a>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        messageDiv.innerHTML = messageHTML;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    exportDiagram() {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        // Simple export as image using html2canvas if available
        if (typeof html2canvas !== 'undefined') {
            html2canvas(container).then(canvas => {
                const link = document.createElement('a');
                link.download = `diagram_${Date.now()}.png`;
                link.href = canvas.toDataURL();
                link.click();
            }).catch(() => {
                this.exportAsText();
            });
        } else {
            this.exportAsText();
        }
    }

    exportAsText() {
        const container = document.getElementById('diagramContainer');
        if (!container) return;
        
        const content = container.innerText;
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.download = `diagram_${Date.now()}.txt`;
        link.href = url;
        link.click();
    }

    clearCanvas() {
        const container = document.getElementById('diagramContainer');
        if (container) {
            container.innerHTML = '';
        }
        this.addMessage('ai', 'Đã xóa diagram. Bạn có thể bắt đầu lại.');
    }

    showNotification(message, type = 'info') {
        // Simple notification (can be enhanced)
        (function(){})(`${type.toUpperCase()}: ${message}`);
        
        // Also show in model info area if available
        const modelStatus = document.getElementById('modelStatus');
        if (modelStatus) {
            modelStatus.textContent = message;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on notebook section
    if (document.getElementById('notebook-section')) {
        window.aiNotebookController = new AINotebookController();
    }
});


