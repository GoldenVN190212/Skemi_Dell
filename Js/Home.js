/* Home.js - phiên bản đã sửa đổi dùng Vis.js Network */

// --- Cấu hình ---
const API_ENDPOINT = "http://localhost:8000/generate_mindmap"; // <-- đổi nếu cần

// --- DOM Elements ---
const fileInput = document.getElementById("fileInput");
const importBtn = document.getElementById("importBtn");
const clearBtn = document.getElementById("clearBtn");
const summaryBtn = document.getElementById("summaryBtn");
const detailBtn = document.getElementById("detailBtn");
const canvas = document.getElementById("mindmapCanvas"); 
const dropArea = document.getElementById("dropArea");

const modeAI = document.getElementById('mode-ai');
const modeManual = document.getElementById('mode-manual');
const aiModeSection = document.getElementById('ai-mode');
const manualModeSection = document.getElementById('manual-mode');
const infoPanel = document.querySelector('.info-panel');
const summaryContainer = document.getElementById('summaryContainer');
const detailContainer = document.getElementById('detailContainer');

const inputModeText = document.getElementById('input-mode-text');
const inputModeFile = document.getElementById('input-mode-file');
const textInputArea = document.getElementById('text-input-area');
const fileUploadArea = document.getElementById('file-upload-area');
const textPrompt = document.getElementById('textPrompt');
const generateTextBtn = document.getElementById('generateTextBtn');

const addNodeBtn = document.getElementById('addNodeBtn');
const connectNodesBtn = document.getElementById('connectNodesBtn');
const editNodeBtn = document.getElementById('editNodeBtn');
const saveManualBtn = document.getElementById('saveManualBtn');

const projectList = document.getElementById('project-list');

if (!canvas) throw new Error("mindmapCanvas element not found!");

let selectedFile = null;
let isProcessing = false;
let lastMindmapData = null; 

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 600;
canvas.width = CANVAS_WIDTH;
canvas.height = CANVAS_HEIGHT;

// ----------------- Vis.js Global Instance -----------------
let visNetworkInstance = null; 


// ----------------- Utility -----------------
function setLoadingState(on, opts = {}) {
    if (opts.for === 'text') {
        generateTextBtn.disabled = on;
        generateTextBtn.textContent = on ? '⏳ Đang xử lý...' : '🚀 Tạo Mindmap từ Văn bản';
    } else {
        importBtn.disabled = on;
        clearBtn.disabled = on;
        importBtn.textContent = on ? '⏳ Đang phân tích file...' : '🚀 Phân tích & Tạo Mindmap';
    }
    isProcessing = on;
}

function showSingleTopicAlert(topic) {
    alert(`📌 Chủ đề: ${topic}`);
}

function safeText(s) {
    return String(s || '').replace(/</g, "&lt;").replace(/>/g, "&gt;");
}


// ----------------- Sidebar (Giữ nguyên) -----------------
function loadSidebarData() {
    if (!projectList) return;
    projectList.innerHTML = '';
    const projects = [
        {id: 1, name: "Dự án 1: Lý thuyết Hóa học", type: "AI"},
        {id: 2, name: "Dự án 2: Lịch sử Việt Nam", type: "Thủ công"},
        {id: 3, name: "Dự án 3: Lập trình Web", type: "AI"},
    ];
    projects.forEach(p => {
        const li = document.createElement('li');
        li.textContent = p.name + (p.type ? ` (${p.type})` : '');
        li.setAttribute('data-project-id', p.id);
        projectList.appendChild(li);
    });
}


// ----------------- Vis.js Data Transformer -----------------

function convertTreeToVisData(treeNodes, parentId, visNodes, visEdges, rootNodeId) {
    if (!treeNodes) return;
    
    let parentLevel = visNodes.find(n => n.id === parentId)?.level || 0;

    treeNodes.forEach((node, index) => {
        const nodeId = node.id ? String(node.id) : `${parentId}-c${index}`; 
        const level = parentId === rootNodeId ? 1 : parentLevel + 1;
        
        let nodeColor, nodeShape;
        
        if (level === 1) {
            nodeColor = '#4d4dff'; 
            nodeShape = 'box';
        } else if (level === 2) {
            nodeColor = '#00b33c'; 
            nodeShape = 'ellipse';
        } else {
            nodeColor = '#ff6666'; 
            nodeShape = 'circle';
        }

        // --- 1. Thêm Node ---
        visNodes.push({
            id: nodeId,
            label: node.text || "Node",
            color: nodeColor,
            shape: nodeShape,
            font: { size: 16 + (4 - Math.min(level, 4)) * 2, color: 'white' },
            level: level, 
        });

        // --- 2. Thêm Edge (nối với Parent) ---
        if (parentId !== null && parentId !== nodeId) {
            visEdges.push({
                from: parentId,
                to: nodeId,
                color: { color: nodeColor, highlight: '#aaa' },
                width: Math.max(3 - (level - 1), 1), 
                arrows: 'to',
                smooth: true 
            });
        }

        // --- 3. Đệ quy cho Children ---
        convertTreeToVisData(node.children || [], nodeId, visNodes, visEdges, rootNodeId);
    });
}


// ----------------- Draw Mindmap (dùng Vis.js) -----------------

function drawMindmapVis(data) {
    if (visNetworkInstance) {
        visNetworkInstance.destroy(); 
        visNetworkInstance = null;
    }

    if (!data || !Array.isArray(data.nodes) || data.nodes.length === 0) {
        // Fallback drawing text when no data
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
        ctx.font = "26px Arial";
        ctx.fillStyle = "#444";
        ctx.textAlign = 'center';
        ctx.fillText("Chưa có Sơ đồ Tư duy nào. Hãy nhập Text hoặc File.", CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2);
        ctx.textAlign = 'start';
        return;
    }
    
    const visNodesData = [];
    const visEdgesData = [];
    const rootNodeId = 'root-topic';
    const topic = data.title || 'MAIN TOPIC';
    
    // Thêm Node Trung tâm (Root Node - Cấp 0)
    visNodesData.push({
        id: rootNodeId,
        label: topic,
        color: { background: '#ff6666', border: '#e64d4d' },
        font: { color: 'white', size: 24, multi: 'html' },
        shape: 'box',
        level: 0,
        fixed: true, 
        x: CANVAS_WIDTH / 2, 
        y: CANVAS_HEIGHT / 2,
    });

    // Chuyển đổi các node con
    convertTreeToVisData(data.nodes, rootNodeId, visNodesData, visEdgesData, rootNodeId);
    
    // Chuẩn bị Dữ liệu Vis.js
    const visData = {
        nodes: new vis.DataSet(visNodesData),
        edges: new vis.DataSet(visEdgesData)
    };
    
    // Cấu hình Tùy chọn (Layout & Physics)
    const options = {
        physics: {
            enabled: true,
            barnesHut: {
                gravitationalConstant: -3000, 
                centralGravity: 0.1,
                springLength: 150, 
                springConstant: 0.08,
                damping: 0.09,
                avoidOverlap: 1 
            },
            solver: 'barnesHut',
            stabilization: { iterations: 200 } 
        },
        interaction: {
            dragNodes: true, 
            dragView: true,  
            zoomView: true   
        },
        layout: {
            hierarchical: { enabled: false }
        },
        edges: {
            smooth: { enabled: true, type: 'continuous' }
        },
        nodes: {
            margin: 10,
            chosen: true,
            shadow: true,
        }
    };
    
    // Khởi tạo Network
    visNetworkInstance = new vis.Network(canvas, visData, options);
    
    // Thêm tương tác phụ
    visNetworkInstance.on("doubleClick", function (params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = visData.nodes.get(nodeId);
            if (node) {
                alert(`Chi tiết Node: ${node.label}`);
            }
        }
    });
}

// Wrapper cho drawMindmap
function drawMindmap(data) {
    let visData = {
        title: data?.title || 'Không xác định',
        nodes: data?.nodes || [] 
    };
    
    drawMindmapVis(visData);
}


// ----------------- Input mode UI (Giữ nguyên) -----------------

function switchInputMode(mode) {
    if (mode === 'file') {
        textInputArea.classList.add('hidden');
        fileUploadArea.classList.remove('hidden');
        inputModeFile.classList.add('active');
        inputModeText.classList.remove('active');
    } else {
        textInputArea.classList.remove('hidden');
        fileUploadArea.classList.add('hidden');
        inputModeFile.classList.remove('active');
        inputModeText.classList.add('active');
    }
}

function switchMode(mode) {
    if (mode === 'ai') {
        aiModeSection.classList.remove('hidden');
        manualModeSection.classList.add('hidden');
        modeAI.classList.add('active');
        modeManual.classList.remove('active');
        infoPanel.classList.remove('hidden');
        
        drawMindmap(lastMindmapData); 

    } else {
        aiModeSection.classList.add('hidden');
        manualModeSection.classList.remove('hidden');
        modeAI.classList.remove('active');
        modeManual.classList.add('active');
        infoPanel.classList.add('hidden');
        
        if (visNetworkInstance) {
            visNetworkInstance.destroy();
            visNetworkInstance = null;
        }
        
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
        ctx.font = "26px Arial";
        ctx.fillStyle = "#444";
        ctx.textAlign = 'center';
        ctx.fillText("✍️ Khu vực vẽ Mindmap Thủ công", CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 30);
        ctx.fillText("Sử dụng các nút bên trên để bắt đầu vẽ.", CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 + 10);
        ctx.textAlign = 'start';
        toggleInfoContainers(false, false);
        summaryBtn.disabled = true;
        detailBtn.disabled = true;
    }
}

function initManualModeListeners() {
    if (addNodeBtn) addNodeBtn.addEventListener('click', () => {
        alert("Chế độ Thủ công: Thêm Node đang được kích hoạt. Hãy click lên canvas.");
    });
    if (connectNodesBtn) connectNodesBtn.addEventListener('click', () => {
        alert("Chế độ Thủ công: Nối Nodes đang được kích hoạt. Hãy chọn hai node.");
    });
    if (editNodeBtn) editNodeBtn.addEventListener('click', () => {
        alert("Chế độ Thủ công: Sửa Node đang được kích hoạt. Double click vào node để sửa.");
    });
    if (saveManualBtn) saveManualBtn.addEventListener('click', () => {
        if (confirm("Bạn có muốn lưu dự án Mindmap Thủ công này không?")) {
            alert("Lưu Dự án đang được thực hiện...");
        }
    });
}


// ----------------- Fetch file -> server (thực) -----------------
async function fetchMindmapFromAI(file) {
    if (isProcessing) return;
    if (!file) {
        alert("Vui lòng chọn một file trước khi phân tích.");
        return;
    }

    setLoadingState(true, { for: 'import' });

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch(API_ENDPOINT, {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            let text = await resp.text().catch(() => '');
            throw new Error(`Server trả lỗi: ${resp.status} ${resp.statusText}${text ? ' — ' + text : ''}`);
        }

        const json = await resp.json();

        const topic = json.topic || 'Không xác định';
        const nodesFromServer = json.mindmap_nodes || []; 
        const summaryText = Array.isArray(json.summary) ? json.summary.join(' • ') : (json.summary || '');
        const detailText = Array.isArray(json.detail) ? json.detail.join('\n') : (json.detail || '');

        summaryContainer.innerHTML = `<h3>📝 Tóm tắt ý chính</h3><p>${safeText(summaryText)}</p>`;
        detailContainer.innerHTML = `<h3>🔍 Chi tiết nội dung trích xuất</h3><p>${safeText(detailText).replace(/\n/g, '<br>')}</p>`;

        lastMindmapData = {
            title: topic,
            nodes: nodesFromServer 
        };

        drawMindmap(lastMindmapData); 

        summaryBtn.disabled = false;
        detailBtn.disabled = false;
        toggleInfoContainers(true, false);

        showSingleTopicAlert(topic);

    } catch (err) {
        console.error("fetchMindmapFromAI error:", err);
        alert(`❌ Lỗi khi phân tích file: ${err.message || err}`);
    } finally {
        setLoadingState(false, { for: 'import' });
    }
}


// ----------------- Fetch from text to model (Giữ nguyên) -----------------
async function fetchMindmapFromText(prompt) {
    if (isProcessing) return;
    if (!prompt || prompt.trim().length < 5) {
        alert("Vui lòng nhập prompt có độ dài phù hợp (>=5 ký tự).");
        return;
    }

    setLoadingState(true, { for: 'text' });

    const TEXT_API = API_ENDPOINT.replace('/generate_mindmap', '/generate_mindmap_from_text') || '/generate_mindmap_from_text';

    try {
        const resp = await fetch(TEXT_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });

        if (!resp.ok) {
            const txt = await resp.text().catch(() => '');
            throw new Error(`Server trả lỗi: ${resp.status} ${resp.statusText}${txt ? ' — ' + txt : ''}`);
        }

        const json = await resp.json();

        const topic = json.topic || 'Không xác định';
        const nodesFromServer = json.mindmap_nodes || json.nodes || []; 
        const summaryText = Array.isArray(json.summary) ? json.summary.join(' • ') : (json.summary || '');
        const detailText = Array.isArray(json.detail) ? json.detail.join('\n') : (json.detail || '');

        summaryContainer.innerHTML = `<h3>📝 Tóm tắt ý chính</h3><p>${safeText(summaryText)}</p>`;
        detailContainer.innerHTML = `<h3>🔍 Chi tiết nội dung trích xuất</h3><p>${safeText(detailText).replace(/\n/g, '<br>')}</p>`;

        lastMindmapData = {
            title: topic,
            nodes: nodesFromServer 
        };

        drawMindmap(lastMindmapData);
        toggleInfoContainers(true, false);
        summaryBtn.disabled = false;
        detailBtn.disabled = false;

        showSingleTopicAlert(topic);

    } catch (err) {
        console.error("fetchMindmapFromText error:", err);
        alert(`❌ Lỗi khi tạo Mindmap từ văn bản: ${err.message || err}`);
    } finally {
        setLoadingState(false, { for: 'text' });
    }
}


// ----------------- Drag & Drop + input handlers (Giữ nguyên) -----------------
function handleFileSelection(file) {
    handleFile(file); // update UI
}

function handleFile(file) {
    selectedFile = file;
    if (!dropArea) return;
    dropArea.innerHTML = `
        <div class="icon">✅</div>
        <p class="file-info">Đã chọn: ${safeText(file.name)}</p>
        <p class="small-text">Nhấn nút "Phân tích" bên dưới để bắt đầu</p>
        <button id="browseBtn" class="browse-btn">📂 Chọn file khác</button>
    `; 	clearBtn.disabled = false;
    importBtn.disabled = false;
}

function resetDropArea() {
    selectedFile = null;
    clearBtn.disabled = true;
    importBtn.disabled = true;
    if (!dropArea) return;
    dropArea.innerHTML = `
        <div class="icon">☁️</div>
        <p>Kéo thả hình ảnh/tài liệu (.pdf, .docx, .png, .jpg...)</p>
        <p class="small-text">hoặc nhấn <strong>Ctrl+V</strong> để dán ảnh</p>
        <button id="browseBtn" class="browse-btn">📂 Chọn file từ máy</button>
    `;
    lastMindmapData = null;
    drawMindmap(lastMindmapData); 
}

function toggleInfoContainers(showSummary, showDetail) {
    if (summaryContainer) summaryContainer.classList.toggle('hidden', !showSummary);
    if (detailContainer) detailContainer.classList.toggle('hidden', !showDetail);
    if (summaryBtn) summaryBtn.classList.toggle('active', showSummary);
    if (detailBtn) detailBtn.classList.toggle('active', showDetail);
}


// ----------------- Init and wiring events (Giữ nguyên) -----------------
document.addEventListener("DOMContentLoaded", () => {
    loadSidebarData();
    initManualModeListeners();

    if (modeAI) modeAI.addEventListener('click', () => switchMode('ai'));
    if (modeManual) modeManual.addEventListener('click', () => switchMode('manual'));

    if (inputModeText) inputModeText.addEventListener('click', () => switchInputMode('text'));
    if (inputModeFile) inputModeFile.addEventListener('click', () => switchInputMode('file'));
    if (fileUploadArea) fileUploadArea.classList.add('hidden');

    document.body.addEventListener("click", (e) => {
        if (e.target && e.target.id === "browseBtn") {
            if (fileInput) fileInput.click();
        }
    });

    if (fileInput) fileInput.addEventListener("change", function() {
        if (this.files && this.files.length > 0) {
            handleFile(this.files[0]);
        }
    });

    if (clearBtn) clearBtn.addEventListener("click", () => {
        resetDropArea();
        lastMindmapData = null;
        drawMindmap(lastMindmapData);
    });

    if (importBtn) importBtn.addEventListener("click", () => {
        if (!selectedFile) {
            alert("Vui lòng chọn một file trước khi phân tích.");
            return;
        }
        fetchMindmapFromAI(selectedFile);
    });

    if (generateTextBtn) generateTextBtn.addEventListener("click", () => {
        const prompt = textPrompt.value.trim();
        if (prompt.length > 10) {
            fetchMindmapFromText(prompt);
        } else {
            alert("Vui lòng nhập yêu cầu có độ dài lớn hơn 10 ký tự.");
        }
    });

    if (summaryBtn) summaryBtn.addEventListener('click', () => toggleInfoContainers(true, false));
    if (detailBtn) detailBtn.addEventListener('click', () => toggleInfoContainers(false, true));

    // Drag & drop handlers (Giữ nguyên logic)
    if (dropArea) {
        dropArea.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropArea.classList.add("drag-active");
            const p = dropArea.querySelector("p");
            if (p) p.innerText = "Thả file vào đây để tải lên";
        });
        dropArea.addEventListener("dragleave", (e) => {
            e.preventDefault();
            dropArea.classList.remove("drag-active");
            const p = dropArea.querySelector("p");
            if (selectedFile) {
                const st = dropArea.querySelector(".small-text");
                if (st) st.innerText = "Nhấn nút \"Phân tích\" bên dưới để bắt đầu";
            } else {
                if (p) p.innerText = "Kéo thả hình ảnh/tài liệu (.pdf, .docx, .png, .jpg...)";
            }
        });
        dropArea.addEventListener("drop", (e) => {
            e.preventDefault();
            dropArea.classList.remove("drag-active");
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const dt = new DataTransfer();
                dt.items.add(files[0]);
                fileInput.files = dt.files;
                handleFile(files[0]);
            }
        });
    }

    // default mode
    switchMode('ai');
    toggleInfoContainers(false, false);
});