/* Home.js - phiên bản fetch thực + loading UI + 1 alert chủ đề duy nhất */

// --- Cấu hình ---
// Thay bằng endpoint thật của bạn
const API_ENDPOINT = "http://localhost:8000/generate_mindmap"; // <-- đổi nếu cần


// --- DOM Elements (giữ tương thích với file gốc) ---
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
const ctx = canvas.getContext("2d");

let selectedFile = null;
let isProcessing = false;
let lastMindmapData = null;

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 600;
canvas.width = CANVAS_WIDTH;
canvas.height = CANVAS_HEIGHT;


// ----------------- Utility -----------------
function setLoadingState(on, opts = {}) {
    // on: boolean
    // opts: { for: 'import'|'text' }
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
    // 1 alert duy nhất, ngắn gọn (the user requested)
    alert(`📌 Chủ đề: ${topic}`);
}

function safeText(s) {
    return String(s || '').replace(/</g, "&lt;").replace(/>/g, "&gt;");
}


// ----------------- Sidebar (unchanged) -----------------
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


// ----------------- Canvas draw (kept from your code) -----------------
function drawMindmap(data) {
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    if (!data || !Array.isArray(data.nodes) || data.nodes.length === 0) {
        ctx.font = "26px Arial";
        ctx.fillStyle = "#444";
        ctx.textAlign = 'center';
        ctx.fillText("Chưa có Sơ đồ Tư duy nào. Hãy nhập Text hoặc File.", CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2);
        ctx.textAlign = 'start';
        return;
    }

    // connections (optional)
    ctx.strokeStyle = '#4d4dff';
    ctx.lineWidth = 2;
    (data.connections || []).forEach(conn => {
        const fromNode = data.nodes.find(n => n.id === conn.from);
        const toNode = data.nodes.find(n => n.id === conn.to);
        if (fromNode && toNode) {
            ctx.beginPath();
            ctx.moveTo(fromNode.x, fromNode.y);
            const midX = (fromNode.x + toNode.x) / 2;
            const controlY = Math.min(fromNode.y, toNode.y) - 100;
            ctx.quadraticCurveTo(midX, controlY, toNode.x, toNode.y);
            ctx.stroke();
        }
    });

    // nodes
    data.nodes.forEach(node => {
        const paddingX = 15;
        const paddingY = 8;
        ctx.font = "18px Arial";
        ctx.textAlign = 'center';
        const textMetrics = ctx.measureText(node.text);
        const width = textMetrics.width + 2 * paddingX;
        const height = 18 + 2 * paddingY;
        const x = node.x - width / 2;
        const y = node.y - height / 2;
        const radius = 8;

        ctx.fillStyle = node.color || '#ff6666';
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1;

        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.arcTo(x + width, y, x + width, y + radius, radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.arcTo(x + width, y + height, x + width - radius, y + height, radius);
        ctx.lineTo(x + radius, y + height);
        ctx.arcTo(x, y + height, x, y + height - radius, radius);
        ctx.lineTo(x, y + radius);
        ctx.arcTo(x, y, x + radius, y, radius);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = 'black';
        ctx.fillText(node.text, node.x, node.y + paddingY / 2);
    });

    ctx.textAlign = 'start';
}


// ----------------- Input mode UI -----------------
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
/**
 * Gửi file (File object) lên server và xử lý kết quả
 * Server expected JSON response:
 * {
 * topic: "string",
 * mindmap_nodes: [ ... ]  // optional: nodes with x,y,color,id,text
 * detail: ["...","..."],
 * summary: ["...","..."] or string
 * }
 */
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
        // Gọi fetch thực
        const resp = await fetch(API_ENDPOINT, {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            // Đọc body nếu có thông tin lỗi
            let text = await resp.text().catch(() => '');
            throw new Error(`Server trả lỗi: ${resp.status} ${resp.statusText}${text ? ' — ' + text : ''}`);
        }

        const json = await resp.json();

        // Lấy topic an toàn
        const topic = json.topic || json.top || (json.mindmap && json.mindmap.title) || 'Không xác định';

        // Hiển thị tóm tắt / chi tiết (nếu có)
        const summaryText = Array.isArray(json.summary) ? json.summary.join(' • ') : (json.summary || '');
        const detailText = Array.isArray(json.detail) ? json.detail.join('\n') : (json.detail || '');

        summaryContainer.innerHTML = `<h3>📝 Tóm tắt ý chính</h3><p>${safeText(summaryText)}</p>`;
        detailContainer.innerHTML = `<h3>🔍 Chi tiết nội dung trích xuất</h3><p>${safeText(detailText).replace(/\n/g, '<br>')}</p>`;

        // Chuẩn bị dữ liệu cho vẽ mindmap: nếu server trả về nodes/còn thiếu connections, normalize
        const nodesFromServer = json.mindmap_nodes || json.mindmap?.nodes || (json.nodes || []);
        const connectionsFromServer = json.connections || json.mindmap?.connections || [];

        // Nếu server chỉ trả dạng cây (nodes with children), bạn có thể muốn convert sang flat nodes with coords.
        // Ở đây giả sử server đã trả nodes có x,y ; nếu không, ta sẽ fallback minimal.
        let mindmapData = {
            title: topic,
            nodes: [],
            connections: []
        };

        if (Array.isArray(nodesFromServer) && nodesFromServer.length > 0) {
            // copy nodes, ensure id/text,x,y,color exist
            mindmapData.nodes = nodesFromServer.map((n, idx) => ({
                id: n.id || `n${idx}`,
                text: n.text || n.title || `Node ${idx + 1}`,
                x: (typeof n.x === 'number') ? n.x : (100 + (idx * 150) % (CANVAS_WIDTH - 200)),
                y: (typeof n.y === 'number') ? n.y : (150 + Math.floor(idx / 4) * 120),
                color: n.color || undefined
            }));
            mindmapData.connections = Array.isArray(connectionsFromServer) ? connectionsFromServer : [];
        } else {
            // fallback: create basic nodes from summary/detail if server didn't send nodes
            const fallbackList = summaryText ? summaryText.split('•').map(s => s.trim()).filter(Boolean) : (detailText ? detailText.split('\n').slice(0, 4) : []);
            mindmapData.nodes = fallbackList.map((t, i) => ({
                id: `f${i}`,
                text: t || `Ý ${i + 1}`,
                x: 200 + i * 180,
                y: 300,
                color: undefined
            }));
            // connect all to first if multiple
            if (mindmapData.nodes.length > 0) {
                 mindmapData.connections = mindmapData.nodes.slice(1).map(n => ({ from: mindmapData.nodes[0].id, to: n.id }));
            }
        }

        lastMindmapData = mindmapData;
        drawMindmap(lastMindmapData);

        // Enable summary/detail buttons
        summaryBtn.disabled = false;
        detailBtn.disabled = false;
        toggleInfoContainers(true, false);

        // --- ALERT DUY NHẤT ---
        showSingleTopicAlert(topic);

    } catch (err) {
        console.error("fetchMindmapFromAI error:", err);
        // Hiển thị alert ngắn gọn, kèm console để debug
        alert(`❌ Lỗi khi phân tích file: ${err.message || err}`);
    } finally {
        setLoadingState(false, { for: 'import' });
    }
}


// ----------------- Fetch from text to model (giữ nguyên nhưng thực) -----------------
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
        const summaryText = Array.isArray(json.summary) ? json.summary.join(' • ') : (json.summary || '');
        const detailText = Array.isArray(json.detail) ? json.detail.join('\n') : (json.detail || '');

        summaryContainer.innerHTML = `<h3>📝 Tóm tắt ý chính</h3><p>${safeText(summaryText)}</p>`;
        detailContainer.innerHTML = `<h3>🔍 Chi tiết nội dung trích xuất</h3><p>${safeText(detailText).replace(/\n/g, '<br>')}</p>`;

        // nodes handling similar to file path
        const nodes = json.mindmap_nodes || json.nodes || [];
        lastMindmapData = {
            title: topic,
            nodes: Array.isArray(nodes) && nodes.length ? nodes.map((n,i) => ({
                id: n.id || `n${i}`,
                text: n.text || n.title || `Node ${i+1}`,
                x: n.x || (100 + i * 150),
                y: n.y || 200 + Math.floor(i/4)*120,
                color: n.color || undefined
            })) : [],
            connections: json.connections || []
        };
        drawMindmap(lastMindmapData);
        toggleInfoContainers(true, false);
        summaryBtn.disabled = false;
        detailBtn.disabled = false;

        // single alert with topic
        showSingleTopicAlert(topic);

    } catch (err) {
        console.error("fetchMindmapFromText error:", err);
        alert(`❌ Lỗi khi tạo Mindmap từ văn bản: ${err.message || err}`);
    } finally {
        setLoadingState(false, { for: 'text' });
    }
}


// ----------------- Drag & Drop + input handlers -----------------
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
    `;    clearBtn.disabled = false;
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
}

function toggleInfoContainers(showSummary, showDetail) {
    if (summaryContainer) summaryContainer.classList.toggle('hidden', !showSummary);
    if (detailContainer) detailContainer.classList.toggle('hidden', !showDetail);
    if (summaryBtn) summaryBtn.classList.toggle('active', showSummary);
    if (detailBtn) detailBtn.classList.toggle('active', showDetail);
}


// ----------------- Init and wiring events -----------------
document.addEventListener("DOMContentLoaded", () => {
    loadSidebarData();
    initManualModeListeners();

    if (modeAI) modeAI.addEventListener('click', () => switchMode('ai'));
    if (modeManual) modeManual.addEventListener('click', () => switchMode('manual'));

    if (inputModeText) inputModeText.addEventListener('click', () => switchInputMode('text'));
    if (inputModeFile) inputModeFile.addEventListener('click', () => switchInputMode('file'));
    if (fileUploadArea) fileUploadArea.classList.add('hidden');

    // browseBtn handler delegated
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

    // Actual upload button: send selectedFile to server
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

    // Drag & drop handlers
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