// Home.js

const fileInput = document.getElementById("fileInput");
const importBtn = document.getElementById("importBtn");
const summaryBtn = document.getElementById("summaryBtn");
const detailBtn = document.getElementById("detailBtn");
const canvas = document.getElementById("mindmapCanvas");
const ctx = canvas.getContext("2d");
const dropArea = document.getElementById("dropArea"); 
const browseBtn = document.getElementById("browseBtn");
const clearBtn = document.getElementById("clearBtn"); 

let lastMindmapData = null;
let selectedFile = null; 
let mindmapDetailNodes = null; 
let mindmapSummaryNodes = null; 
let isProcessing = false; 

// -------------------------
// XỬ LÝ KÉO THẢ & PASTE
// -------------------------
browseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", function() {
    if (this.files.length > 0) {
        handleFile(this.files[0]);
    }
});

dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropArea.classList.add("drag-active");
    dropArea.querySelector("p").innerText = "Thả file vào đây để tải lên";
});

dropArea.addEventListener("dragleave", () => {
    dropArea.classList.remove("drag-active");
    dropArea.querySelector("p").innerText = "Kéo thả hình ảnh/tài liệu vào đây";
});

dropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    dropArea.classList.remove("drag-active");
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const dataTransfer = new DataTransfer();
        for (let i = 0; i < files.length; i++) {
             dataTransfer.items.add(files[i]);
        }
        fileInput.files = dataTransfer.files;
        handleFile(files[0]);
    } else {
        alert("⚠️ Để lấy ảnh từ web khác, vui lòng chuột phải vào ảnh chọn 'Sao chép hình ảnh' (Copy Image) rồi nhấn Ctrl+V tại đây.");
    }
});

document.addEventListener("paste", (e) => {
    if (isProcessing) return; 
    
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf("image") !== -1) {
            const blob = items[i].getAsFile();
            const file = new File([blob], "pasted_image.png", { type: "image/png" });
            
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;
            
            handleFile(file);
            break;
        }
    }
});

function handleFile(file) {
    selectedFile = file;
    dropArea.innerHTML = `
        <div class="icon">✅</div>
        <p class="file-info">Đã chọn: ${file.name}</p>
        <p class="small-text">Nhấn nút "Phân tích" bên dưới để bắt đầu</p>
        <button id="browseBtn" class="browse-btn">📂 Chọn file khác</button>
    `;
    clearBtn.disabled = false; 
    const newBrowseBtn = document.getElementById("browseBtn");
    if (newBrowseBtn) {
        newBrowseBtn.addEventListener("click", () => fileInput.click());
    }
}

// -------------------------
// CHỨC NĂNG XÓA FILE
// -------------------------
clearBtn.addEventListener("click", () => {
    if (isProcessing) {
        alert("🛑 Hệ thống đang phân tích. Vui lòng chờ quá trình hoàn tất!");
        return;
    }
    
    fileInput.value = ""; 
    selectedFile = null;
    lastMindmapData = null;
    mindmapDetailNodes = null;
    mindmapSummaryNodes = null;
    clearBtn.disabled = true;
    summaryBtn.disabled = true;
    detailBtn.disabled = true;

    dropArea.innerHTML = `
        <div class="icon">☁️</div>
        <p>Kéo thả hình ảnh/tài liệu vào đây</p>
        <p class="small-text">hoặc nhấn <strong>Ctrl+V</strong> để dán ảnh copy từ web</p>
        <input type="file" id="fileInput" accept=".txt,.pdf,.png,.jpg,.jpeg,.docx,.pptx" hidden />
        <button id="browseBtn" class="browse-btn">📂 Chọn file từ máy</button>
    `;
    
    const newFileInput = document.getElementById("fileInput");
    newFileInput.addEventListener("change", function() {
        if (this.files.length > 0) {
            handleFile(this.files[0]);
        }
    });
    document.getElementById("browseBtn").addEventListener("click", () => newFileInput.click());
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "26px Arial";
    ctx.fillStyle = "#444";
    ctx.fillText("Mindmap đã được xóa. Sẵn sàng cho bài học mới!", 100, 200);
});


// -------------------------
// DRAW MINDMAP UTILS (RECURSIVE)
// -------------------------
async function typeCanvasText(x, y, text, speed = 20) {
    ctx.font = ctx.font; 
    ctx.fillStyle = ctx.fillStyle; 
    
    let current = "";
    const textMeasure = ctx.measureText(text);
    const textWidth = textMeasure.width;
    const clearWidth = textWidth + 50; 
    
    for (let char of text) {
        current += char;
        if (speed > 0) {
            ctx.clearRect(x, y - 20, clearWidth, 30);
        }
        ctx.fillText(current, x, y);
        await new Promise(r => setTimeout(r, speed));
    }
}


async function drawRecursiveNode(node, parentX, parentY, isSummaryMode = false) {
    const x = node.x;
    const y = node.y;
    const text = node.text;
    const speed = isSummaryMode ? 0 : 5; 
    
    // --- 1. VẼ ĐƯỜNG NỐI ---
    if (parentX !== null && parentY !== null) {
        ctx.strokeStyle = "#4070f4";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(parentX, parentY);
        const midX = (parentX + x) / 2;
        ctx.bezierCurveTo(midX, parentY, midX, y, x, y); 
        ctx.stroke();
    }
    
    // --- 2. TÍNH KÍCH THƯỚC VÀ VẼ KHUNG ---
    const fontSize = isSummaryMode ? "20px" : (node.children && node.children.length > 0 ? "20px" : "18px");
    ctx.font = `${fontSize} Arial`;
    
    const padding = 15; 
    const textWidth = ctx.measureText(text).width;
    const boxHeight = 35; 
    const radius = 8; 
    
    const boxX = x - 5; 
    const boxY = y - (boxHeight / 2) - 5; 
    const boxW = textWidth + padding + 10;

    ctx.fillStyle = isSummaryMode ? "#e0e0e0" : "#fff9c4"; 
    ctx.strokeStyle = isSummaryMode ? "#4070f4" : "#ff6f61";
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    if (typeof ctx.roundRect === 'function') {
         ctx.roundRect(boxX, boxY, boxW, boxHeight, radius);
    } else {
         ctx.rect(boxX, boxY, boxW, boxHeight); 
    }
    ctx.fill();
    ctx.stroke(); 

    
    // --- 3. VẼ TEXT ---
    const textDrawX = x + padding/2 - 5; 
    const textDrawY = y + 5; 

    ctx.fillStyle = "#000"; 
    await typeCanvasText(textDrawX, textDrawY, text, speed); 

    // --- 4. ĐỆ QUY VẼ CON ---
    if (node.children && node.children.length > 0 && !isSummaryMode) {
        for (let child of node.children) {
            await drawRecursiveNode(child, x + 5, y + 5, isSummaryMode); 
        }
    }

    if (speed > 0) {
        await new Promise(r => setTimeout(r, 50));
    }
}


async function drawMindmap(topic, nodes, isSummaryMode = false) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const topicX = 400; 
    const topicY = 60;
    
    // --- VẼ NODE GỐC (TOPIC) ---
    ctx.font = "bold 30px Arial";
    const topicWidth = ctx.measureText(topic).width;
    ctx.fillStyle = "#ff6f61"; 
    
    ctx.beginPath();
    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(topicX - topicWidth / 2 - 20, topicY - 35, topicWidth + 40, 50, 10);
    } else {
        ctx.rect(topicX - topicWidth / 2 - 20, topicY - 35, topicWidth + 40, 50); 
    }
    ctx.fill();

    ctx.fillStyle = "#fff"; 
    await typeCanvasText(topicX - topicWidth / 2, topicY, topic, 0); 
    ctx.fillStyle = "#000"; 

    // --- VẼ CÁC NODE CON CẤP 1 (TRUYỀN VÀO) ---
    for (let node of nodes) {
        await drawRecursiveNode(node, topicX, topicY, isSummaryMode); 
    }
}


// -------------------------
// IMPORT FILE (LOGIC CHÍNH)
// -------------------------
importBtn.addEventListener("click", async () => {
    const files = fileInput.files;
    
    if (files.length === 0) return alert("⚠️ Vui lòng chọn/kéo thả/dán file trước!");
    
    if (isProcessing) return alert("🛑 Hệ thống đang bận!");

    const file = files[0];
    const fileName = file.name.toLowerCase();

    let fileType = "Tài liệu";

    if (fileName.endsWith(".ppt") || fileName.endsWith(".pptx")) {
        fileType = "PowerPoint";
    } else if (fileName.endsWith(".pdf")) {
        fileType = "PDF";
    } else if (fileName.endsWith(".doc") || fileName.endsWith(".docx")) {
        fileType = "Word";
    } else if (fileName.endsWith(".png") || fileName.endsWith(".jpg") || fileName.endsWith(".jpeg")) {
        fileType = "Hình ảnh";
    }

    // -----------------------------
    // Hiển thị thông báo đang xử lý
    // -----------------------------
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "26px Arial";
    ctx.fillStyle = "#444";
    ctx.fillText("⏳ AI đang phân tích " + fileType + "...", 100, 200);
    ctx.fillText("Vui lòng chờ trong giây lát...", 100, 250);

    const formData = new FormData();
    formData.append("file", file);

    try {
        isProcessing = true;
        importBtn.innerText = "⏳ Đang xử lý...";
        importBtn.disabled = true;
        summaryBtn.disabled = true;
        detailBtn.disabled = true;

        const res = await fetch("http://localhost:8000/generate_mindmap", {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        if (data.error) return alert("❌ Lỗi server: " + data.error);

        lastMindmapData = data;

        mindmapDetailNodes = data.mindmap_nodes;
        
        mindmapSummaryNodes = data.mindmap_nodes.slice(0, 4).map(node => ({
            ...node, 
            children: [] 
        })); 
        
        summaryBtn.disabled = false;
        detailBtn.disabled = false;


        // -----------------------------
        // ALERT CHỦ ĐỀ
        // -----------------------------
        alert(
            `📌 Bạn vừa import file ${fileType}\n\n` +
            `👉 Chủ đề chính: ${data.topic}\n\n` +
            `👉 Tổng số ý chính (Cấp 1): ${data.mindmap_nodes.length}`
        );

        // -----------------------------
        // VẼ MINDMAP CHI TIẾT LẦN ĐẦU
        // -----------------------------
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillText("✨ Đang vẽ sơ đồ chi tiết...", 100, 200);

        setTimeout(async () => {
            await drawMindmap(data.topic, mindmapDetailNodes, false);
            detailBtn.classList.add('active');
            summaryBtn.classList.remove('active');
        }, 800);

    } catch (e) {
        console.error(e);
        alert("❌ Lỗi kết nối server hoặc gửi file thất bại!");
    } finally {
        isProcessing = false; 
        importBtn.innerText = "🚀 Phân tích & Tạo Mindmap";
        importBtn.disabled = false;
    }
});

// -------------------------
// XEM TÓM TẮT & CHI TIẾT
// -------------------------
summaryBtn.addEventListener("click", async () => {
    if (!lastMindmapData || !mindmapSummaryNodes) return alert("Bạn chưa phân tích file!");
    
    alert("📘 TÓM TẮT:\n\n" + lastMindmapData.summary.join("\n")); 
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    await drawMindmap(lastMindmapData.topic, mindmapSummaryNodes, true); 
    
    summaryBtn.classList.add('active');
    detailBtn.classList.remove('active');
});

detailBtn.addEventListener("click", async () => {
    if (!lastMindmapData || !mindmapDetailNodes) return alert("Bạn chưa phân tích file!");
    
    alert("📙 CHI TIẾT:\n\n" + lastMindmapData.detail.join("\n"));
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    await drawMindmap(lastMindmapData.topic, mindmapDetailNodes, false); 
    
    detailBtn.classList.add('active');
    summaryBtn.classList.remove('active');
});