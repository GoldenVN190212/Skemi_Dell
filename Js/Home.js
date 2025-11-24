// Home.js (PHIÊN BẢN MỚI: BỎ LOGIC GIẢ LẬP CỐ ĐỊNH, THAY BẰNG MÔ PHỎNG GỌI SERVER)

// Khai báo các biến DOM cố định
const fileInput = document.getElementById("fileInput");
const importBtn = document.getElementById("importBtn"); // Nút cho chế độ File/Image
const clearBtn = document.getElementById("clearBtn");
const summaryBtn = document.getElementById("summaryBtn");
const detailBtn = document.getElementById("detailBtn");
const canvas = document.getElementById("mindmapCanvas");
const dropArea = document.getElementById("dropArea");

// Elements cho chuyển đổi chế độ chính (AI vs Manual)
const modeAI = document.getElementById('mode-ai');
const modeManual = document.getElementById('mode-manual');
const aiModeSection = document.getElementById('ai-mode');
const manualModeSection = document.getElementById('manual-mode');
const infoPanel = document.querySelector('.info-panel');
const summaryContainer = document.getElementById('summaryContainer');
const detailContainer = document.getElementById('detailContainer');

// Elements cho chế độ nhập liệu AI
const inputModeText = document.getElementById('input-mode-text');
const inputModeFile = document.getElementById('input-mode-file');
const textInputArea = document.getElementById('text-input-area');
const fileUploadArea = document.getElementById('file-upload-area');
const textPrompt = document.getElementById('textPrompt');
const generateTextBtn = document.getElementById('generateTextBtn');

// Elements cho chế độ Thủ công
const addNodeBtn = document.getElementById('addNodeBtn');
const connectNodesBtn = document.getElementById('connectNodesBtn');
const editNodeBtn = document.getElementById('editNodeBtn');
const saveManualBtn = document.getElementById('saveManualBtn');

// Elements cho Sidebar
const projectList = document.getElementById('project-list');

if (!canvas) throw new Error("mindmapCanvas element not found!");
const ctx = canvas.getContext("2d");

let selectedFile = null; 
let isProcessing = false; 

// KHỞI TẠO DỮ LIỆU RỖNG BAN ĐẦU
let lastMindmapData = null; 

// Cấu hình Canvas
const CANVAS_WIDTH = 800; 
const CANVAS_HEIGHT = 600; 
canvas.width = CANVAS_WIDTH;
canvas.height = CANVAS_HEIGHT;


// --- UTILITY FUNCTIONS ---

function loadSidebarData() {
    if (projectList) {
        projectList.innerHTML = '';
        const projects = [
            {id: 1, name: "Dự án 1: Lý thuyết Hóa học", type: "AI"},
            {id: 2, name: "Dự án 2: Lịch sử Việt Nam", type: "Thủ công"},
            {id: 3, name: "Dự án 3: Lập trình Web", type: "AI"},
        ];

        if (projects.length === 0) {
            projectList.innerHTML = '<li>Chưa có dự án nào được lưu.</li>';
        } else {
            projects.forEach(project => {
                const li = document.createElement('li');
                li.textContent = project.name + (project.type ? ` (${project.type})` : '');
                li.setAttribute('data-project-id', project.id);
                projectList.appendChild(li);
            });
        }
    }
}

function handleFile(file) {
    selectedFile = file;
    dropArea.innerHTML = `
        <div class="icon">✅</div>
        <p class="file-info">Đã chọn: ${file.name}</p>
        <p class="small-text">Nhấn nút "Phân tích" bên dưới để bắt đầu</p>
        <button id="browseBtn" class="browse-btn">📂 Chọn file khác</button>
    `;
    clearBtn.disabled = false; 
    importBtn.disabled = false;
}

function resetDropArea() {
    selectedFile = null;
    clearBtn.disabled = true;
    importBtn.disabled = true;
    dropArea.innerHTML = `
        <div class="icon">☁️</div>
        <p>Kéo thả hình ảnh/tài liệu (.pdf, .docx, .png, .jpg...)</p>
        <p class="small-text">hoặc nhấn <strong>Ctrl+V</strong> để dán ảnh</p>
        <button id="browseBtn" class="browse-btn">📂 Chọn file từ máy</button>
    `;
}

function toggleInfoContainers(showSummary = false, showDetail = false) {
    summaryContainer.classList.toggle('hidden', !showSummary);
    detailContainer.classList.toggle('hidden', !showDetail);
    summaryBtn.classList.toggle('active', showSummary);
    detailBtn.classList.toggle('active', showDetail);
}

function drawMindmap(data) {
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    if (!data || data.nodes.length === 0) {
        ctx.font = "26px Arial";
        ctx.fillStyle = "#444";
        ctx.textAlign = 'center';
        ctx.fillText("Chưa có Sơ đồ Tư duy nào. Hãy nhập Text hoặc File.", CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2);
        ctx.textAlign = 'start';
        return;
    }

    // 1. Vẽ các đường nối 
    ctx.strokeStyle = '#4d4dff';
    ctx.lineWidth = 2;
    data.connections.forEach(conn => {
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

    // 2. Vẽ các Node
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
        
    } else if (mode === 'manual') {
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

// ------------------------------------
// CHỨC NĂNG FETCH MODEL CHO FILE (MÔ PHỎNG GỌI SERVER)
// ------------------------------------
/**
 * Gửi file đã chọn lên API AI để nhận về Mindmap và Tóm tắt
 * @param {File} file File hình ảnh/tài liệu được chọn
 */
async function fetchMindmapFromAI(file) {
    if (isProcessing) return;

    isProcessing = true;
    importBtn.textContent = '⏳ Đang gửi file lên Server...';
    importBtn.disabled = true;
    clearBtn.disabled = true;

    // Thay thế bằng endpoint API Server Mindmap thực tế của bạn
    const API_ENDPOINT = 'YOUR_FILE_AI_MODEL_API_ENDPOINT_HERE'; 
    const formData = new FormData();
    formData.append('file', file);
    
    let fileTitle = file.name;
    let extractedTopic = `Phân tích cho file: ${fileTitle}`;
    
    try {
        // --- GIẢ LẬP GỌI API SERVER ---
        
        // **BƯỚC 1: MÔ PHỎNG GỬI FILE VÀ CHỜ PHẢN HỒI**
        importBtn.textContent = '⏳ Đang chờ AI Server xử lý...';
        
        // Bạn sẽ cần thay thế Promise/setTimeout bằng lệnh fetch() thực tế
        /* const response = await fetch(API_ENDPOINT, { method: 'POST', body: formData });
        if (!response.ok) throw new Error(`Lỗi Server HTTP: ${response.status}`);
        const apiResult = await response.json(); 
        // Lấy dữ liệu thực tế: 
        extractedTopic = apiResult.topic || extractedTopic;
        const mindmapDataFromServer = apiResult.mindmapData;
        const summaryText = apiResult.summary;
        const detailText = apiResult.detail;
        */
        
        await new Promise(resolve => setTimeout(resolve, 3000)); // Chờ 3 giây để giả lập kết nối Server
        
        // **BƯỚC 2: PHẢN HỒI GIẢ LẬP**
        
        alert(`✅ AI Server đã phản hồi! Chủ đề trích xuất: ${extractedTopic}`);
        
        // Dữ liệu Mindmap nhận được (MOCK DATA để đảm bảo giao diện chạy)
        const mockData = { 
            title: extractedTopic,
            nodes: [
                { id: 'chinh', text: extractedTopic, x: 400, y: 100, color: 'salmon' },
                { id: 'nhanh_a', text: 'Nhánh A (Từ Server)', x: 200, y: 300, color: '#add8e6' },
                { id: 'nhanh_b', text: 'Nhánh B (Từ Server)', x: 600, y: 300, color: '#90ee90' },
            ],
            connections: [
                { from: 'chinh', to: 'nhanh_a' },
                { from: 'chinh', to: 'nhanh_b' },
            ]
        };
        
        const summaryText = `Tóm tắt từ File **${file.name}**: Server AI đã xác định chủ đề là **${extractedTopic}** và tạo Mindmap thành công.`;
        const detailText = `Nội dung chi tiết trích xuất từ Server AI cho File ${fileTitle}:\n[Dữ liệu Mindmap, Tóm tắt, và Chi tiết đã được Server AI tạo ra hoàn toàn]`;

        const result = {
            mindmapData: mockData,
            summary: summaryText,
            detail: detailText,
        };
        // --- KẾT THÚC GIẢ LẬP PHẢN HỒI SERVER ---

        // 4. Cập nhật giao diện
        summaryContainer.innerHTML = `<h3>📝 Tóm tắt ý chính</h3><p>${result.summary}</p>`;
        detailContainer.innerHTML = `<h3>🔍 Chi tiết nội dung trích xuất</h3><p>${result.detail.replace(/\n/g, '<br>')}</p>`;

        lastMindmapData = result.mindmapData; 
        drawMindmap(lastMindmapData);
        
        summaryBtn.disabled = false;
        detailBtn.disabled = false;
        toggleInfoContainers(true, false);
        alert(`Tạo Mindmap từ Server cho file "${fileTitle}" hoàn tất!`);

    } catch (error) {
        console.error("Lỗi khi fetch Mindmap từ Server AI:", error);
        alert(`Lỗi kết nối Server: Không thể nhận phản hồi từ API Server. Chi tiết: ${error.message}`);
    } finally {
        isProcessing = false;
        importBtn.textContent = '🚀 Phân tích & Tạo Mindmap';
        importBtn.disabled = false;
        clearBtn.disabled = false;
    }
}

// ------------------------------------
// CHỨC NĂNG FETCH MODEL CHO TEXT (GIỮ NGUYÊN)
// ------------------------------------
async function fetchMindmapFromText(prompt) {
    if (isProcessing) return;

    isProcessing = true;
    generateTextBtn.textContent = '⏳ Đang xử lý...';
    generateTextBtn.disabled = true;

    const API_ENDPOINT = 'YOUR_TEXT_AI_MODEL_API_ENDPOINT_HERE'; 
    const data = { prompt: prompt };

    try {
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        const result = {
            mindmapData: { // Dữ liệu giả lập cho Text
                title: "Kết quả từ Prompt",
                nodes: [
                    { id: 'root', text: 'Mindmap từ Prompt', x: 400, y: 100, color: '#f0e68c' },
                    { id: 'nhanh1', text: 'Phân tích từ khóa', x: 200, y: 300, color: '#f08080' },
                    { id: 'nhanh2', text: 'Tổng hợp cấu trúc', x: 600, y: 300, color: '#87cefa' },
                ],
                connections: [
                    { from: 'root', to: 'nhanh1' },
                    { from: 'root', to: 'nhanh2' },
                ]
            }, 
            summary: `Tóm tắt từ Prompt: Nội dung Mindmap được tạo theo yêu cầu của bạn.`,
            detail: `Yêu cầu của bạn: **${prompt}**\n\nNội dung chi tiết được sử dụng để tạo Mindmap:\n[Văn bản chi tiết từ AI dựa trên prompt]`,
        };
        
        alert(`✅ AI đã nhận yêu cầu: "${prompt.substring(0, 30)}..."`);
        
        summaryContainer.innerHTML = `<h3>📝 Tóm tắt ý chính</h3><p>${result.summary}</p>`;
        detailContainer.innerHTML = `<h3>🔍 Chi tiết nội dung trích xuất</h3><p>${result.detail.replace(/\n/g, '<br>')}</p>`;

        lastMindmapData = result.mindmapData; 
        drawMindmap(lastMindmapData);
        
        summaryBtn.disabled = false;
        detailBtn.disabled = false;
        toggleInfoContainers(true, false);
        alert("Tạo Mindmap từ Văn bản hoàn tất!");

    } catch (error) {
        console.error("Lỗi khi fetch Mindmap từ Text AI:", error);
        alert(`Lỗi tạo Mindmap: Không thể kết nối với mô hình AI. Chi tiết: ${error.message}`);
    } finally {
        isProcessing = false;
        generateTextBtn.textContent = '🚀 Tạo Mindmap từ Văn bản';
        generateTextBtn.disabled = false;
    }
}


// -------------------------
// INITIALIZATION
// -------------------------
document.addEventListener("DOMContentLoaded", () => {
    // 1. Tải dữ liệu Sidebar
    loadSidebarData();

    // 2. Gắn sự kiện chuyển đổi chế độ chính (AI vs Manual)
    if (modeAI) modeAI.addEventListener('click', () => switchMode('ai'));
    if (modeManual) modeManual.addEventListener('click', () => switchMode('manual'));
    
    // 3. Gắn sự kiện chuyển đổi chế độ nhập liệu AI (Text vs File)
    if (inputModeText) inputModeText.addEventListener('click', () => switchInputMode('text'));
    if (inputModeFile) inputModeFile.addEventListener('click', () => switchInputMode('file'));

    // Đảm bảo chế độ mặc định Text-to-Mindmap là ẩn File-upload-area
    if (fileUploadArea) fileUploadArea.classList.add('hidden');


    // 4. Khởi tạo chức năng cho các nút Thủ công
    initManualModeListeners();
    
    // 5. Thiết lập chế độ mặc định và vẽ Mindmap mẫu
    switchMode('ai'); 

    // 6. Gắn sự kiện cho các input/button liên quan đến file upload
    document.body.addEventListener("click", (e) => {
        if (e.target.id === "browseBtn") {
            if (fileInput) fileInput.click();
        }
    });

    if (fileInput) fileInput.addEventListener("change", function() {
        if (this.files.length > 0) {
            handleFile(this.files[0]);
        }
    });
    
    // 7. Sự kiện xóa file
    if (clearBtn) clearBtn.addEventListener("click", () => {
        resetDropArea();
        lastMindmapData = null; 
        drawMindmap(lastMindmapData);
    });

    // 8. Sự kiện Phân tích & Tạo Mindmap 
    
    // a) File/Image-to-Mindmap
    if (importBtn) importBtn.addEventListener('click', () => {
        if (selectedFile) {
            fetchMindmapFromAI(selectedFile); // Gọi hàm fetch model cho File
        } else {
            alert("Vui lòng chọn một file trước khi phân tích.");
        }
    });
    
    // b) Text-to-Mindmap
    if (generateTextBtn) generateTextBtn.addEventListener('click', () => {
        const prompt = textPrompt.value.trim();
        if (prompt.length > 10) {
            fetchMindmapFromText(prompt); // Gọi hàm fetch model cho Text
        } else {
            alert("Vui lòng nhập yêu cầu có độ dài lớn hơn 10 ký tự.");
        }
    });


    // 9. Sự kiện Tóm tắt/Chi tiết
    if (summaryBtn) summaryBtn.addEventListener('click', () => toggleInfoContainers(true, false));
    if (detailBtn) detailBtn.addEventListener('click', () => toggleInfoContainers(false, true));


    // 10. Sự kiện Kéo thả (Drag and Drop)
    if (dropArea) {
        dropArea.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropArea.classList.add("drag-active");
            dropArea.querySelector("p").innerText = "Thả file vào đây để tải lên";
        });
        dropArea.addEventListener("dragleave", (e) => {
            e.preventDefault();
            dropArea.classList.remove("drag-active");
            
            if (selectedFile) {
                 dropArea.querySelector(".small-text").innerText = "Nhấn nút \"Phân tích\" bên dưới để bắt đầu";
            } else {
                 dropArea.querySelector("p").innerText = "Kéo thả hình ảnh/tài liệu (.pdf, .docx, .png, .jpg...)";
            }
        });
        dropArea.addEventListener("drop", (e) => {
            e.preventDefault();
            dropArea.classList.remove("drag-active");
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(files[0]);
                fileInput.files = dataTransfer.files;
                handleFile(files[0]);
            }
        });
    }
});