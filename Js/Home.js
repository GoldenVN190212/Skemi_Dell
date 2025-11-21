// Js/Home.js (Full Code)

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
// --- BIẾN MỚI LƯU DỮ LIỆU ĐỂ CHUYỂN ĐỔI GIỮA 2 CHẾ ĐỘ ---
let mindmapDetailNodes = null; 
let mindmapSummaryNodes = null; 
// --------------------------------------------------------
let isProcessing = false; 

// -------------------------
// XỬ LÝ KÉO THẢ & PASTE
// -------------------------

// 1. Bấm nút chọn file
browseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", function() {
    if (this.files.length > 0) {
        handleFile(this.files[0]);
    }
});

// 2. Hiệu ứng khi kéo file vào
dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropArea.classList.add("drag-active");
    dropArea.querySelector("p").innerText = "Thả file vào đây để tải lên";
});

dropArea.addEventListener("dragleave", () => {
    dropArea.classList.remove("drag-active");
    dropArea.querySelector("p").innerText = "Kéo thả hình ảnh/tài liệu vào đây";
});

// 3. Xử lý khi THẢ file (DROP)
dropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    dropArea.classList.remove("drag-active");
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files; 
        handleFile(files[0]);
    } else {
        alert("⚠️ Để lấy ảnh từ web khác, vui lòng chuột phải vào ảnh chọn 'Sao chép hình ảnh' (Copy Image) rồi nhấn Ctrl+V tại đây.");
    }
});

// 4. Xử lý dán ảnh (PASTE - Ctrl+V) 
document.addEventListener("paste", (e) => {
    if (isProcessing) return; // Không dán khi đang xử lý
    
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

// Hàm hiển thị thông tin file sau khi chọn/thả/paste
function handleFile(file) {
    selectedFile = file;
    dropArea.innerHTML = `
        <div class="icon">✅</div>
        <p class="file-info">Đã chọn: ${file.name}</p>
        <p class="small-text">Nhấn nút "Phân tích" bên dưới để bắt đầu</p>
    `;
    clearBtn.disabled = false; // Kích hoạt nút xóa
    // Đảm bảo nút browseBtn mới được gán lại sự kiện
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
    
    // Đặt lại trạng thái file và dữ liệu
    fileInput.value = ""; 
    selectedFile = null;
    lastMindmapData = null;
    mindmapDetailNodes = null;
    mindmapSummaryNodes = null;
    clearBtn.disabled = true;

    // Đặt lại giao diện Drop Area
    dropArea.innerHTML = `
        <div class="icon">☁️</div>
        <p>Kéo thả hình ảnh/tài liệu vào đây</p>
        <p class="small-text">hoặc nhấn <strong>Ctrl+V</strong> để dán ảnh copy từ web</p>
        <input type="file" id="fileInput" accept=".txt,.pdf,.png,.jpg,.jpeg,.docx,.pptx" hidden />
        <button id="browseBtn" class="browse-btn">📂 Chọn file từ máy</button>
    `;
    
    // Phải gán lại event listener cho nút browseBtn và fileInput
    const newFileInput = document.getElementById("fileInput");
    newFileInput.addEventListener("change", function() {
        if (this.files.length > 0) {
            handleFile(this.files[0]);
        }
    });
    document.getElementById("browseBtn").addEventListener("click", () => newFileInput.click());
    
    // Xóa Mindmap cũ trên canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "26px Arial";
    ctx.fillStyle = "#444";
    ctx.fillText("Mindmap đã được xóa. Sẵn sàng cho bài học mới!", 100, 200);
});


// -------------------------
// DRAW MINDMAP UTILS (RECURSIVE)
// -------------------------
async function drawRecursiveNode(node, parentX, parentY, isTextList = false) {
    const x = node.x;
    const y = node.y;
    const text = node.text;
    const speed = isTextList ? 0 : 5; 
    
    // --- 1. VẼ ĐƯỜNG NỐI ---
    if (parentX !== null && parentY !== null && !isTextList) {
        ctx.strokeStyle = "#4070f4";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(parentX, parentY);
        const midX = (parentX + x) / 2;
        ctx.bezierCurveTo(midX, parentY, midX, y, x, y); 
        ctx.stroke();
    }
    
    // --- 2. TÍNH KÍCH THƯỚC VÀ VẼ KHUNG ---
    const fontSize = isTextList ? "18px" : (node.children && node.children.length > 0 ? "20px" : "18px");
    ctx.font = `${fontSize} Arial`;
    
    const padding = 15; 
    const textWidth = ctx.measureText(text).width;
    const boxHeight = 35; 
    const radius = 8; 
    
    const boxX = x - 5; 
    const boxY = y - (boxHeight / 2) - 5; 
    const boxW = textWidth + padding + 10;

    if (!isTextList) {
        ctx.fillStyle = "#e0e0e0"; 
        ctx.beginPath();
        // Giả định ctx.roundRect được hỗ trợ hoặc đã có polyfill
        if (typeof ctx.roundRect === 'function') {
             ctx.roundRect(boxX, boxY, boxW, boxHeight, radius);
        } else {
             ctx.rect(boxX, boxY, boxW, boxHeight); // Fallback
        }
        ctx.fill();
    }
    
    // --- 3. VẼ TEXT ---
    const textDrawX = x + padding/2 - 5; 
    const textDrawY = y + 5; 

    ctx.fillStyle = isTextList ? "#fff" : "#000"; 
    await typeCanvasText(textDrawX, textDrawY, text, speed); 

    // --- 4. ĐỆ QUY VẼ CON ---
    if (node.children && node.children.length > 0) {
        for (let child of node.children) {
            await drawRecursiveNode(child, x, y + 5, isTextList); 
        }
    }

    if (isTextList) {
        await new Promise(r => setTimeout(r, 50));
    }
}


async function drawMindmap(topic, nodes, isTextList = false) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const topicX = 400; 
    const topicY = 60;
    
    ctx.font = "bold 30px Arial";
    const topicWidth = ctx.measureText(topic).width;
    ctx.fillStyle = "#ff6f61"; 
    
    ctx.beginPath();
    // Giả định ctx.roundRect được hỗ trợ
    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(topicX - topicWidth / 2 - 20, topicY - 35, topicWidth + 40, 50, 10);
    } else {
        ctx.rect(topicX - topicWidth / 2 - 20, topicY - 35, topicWidth + 40, 50); // Fallback
    }
    ctx.fill();

    ctx.fillStyle = "#fff"; 
    await typeCanvasText(topicX - topicWidth / 2, topicY, topic, 0); 
    ctx.fillStyle = "#000"; 

    for (let node of nodes) {
        await drawRecursiveNode(node, topicX, topicY, isTextList); 
    }
}

async function typeCanvasText(x, y, text, speed = 20) {
    ctx.font = ctx.font; // Giữ nguyên font đã set từ hàm gọi
    ctx.fillStyle = ctx.fillStyle; // Giữ nguyên màu đã set từ hàm gọi
    let current = "";
    for (let char of text) {
        current += char;
        if (speed > 0) {
              ctx.clearRect(x, y - 20, 800, 30);
        }
        ctx.fillText(current, x, y);
        await new Promise(r => setTimeout(r, speed));
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
    let fileType = "Tài liệu";

    // ... (Phần xác định fileType giữ nguyên) ...

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

        // --- LƯU TRỮ VÀ XỬ LÝ DỮ LIỆU VẼ ---
        let nodesToDraw = [];
        if (data.mindmap_nodes && data.mindmap_nodes.length > 0) { 
            mindmapDetailNodes = data.mindmap_nodes;
            
            // TẠO DỮ LIỆU TÓM TẮT (4 nhánh chính đầu tiên, bỏ nodes con)
            mindmapSummaryNodes = mindmapDetailNodes.slice(0, 4).map(node => ({
                ...node, 
                children: [] 
            }));
            
            nodesToDraw = mindmapDetailNodes; 
        } else {
             // Xử lý trường hợp không có mindmap_nodes (chỉ có detail/summary list)
            alert("Không có cấu trúc Mindmap, chỉ có Tóm tắt/Chi tiết dạng liệt kê.");
            return;
        }

        alert(
            `📌 Phân tích xong!\n` +
            `👉 Chủ đề: ${data.topic}\n`
        );

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillText("✨ Đang vẽ sơ đồ chi tiết...", 100, 200);

        setTimeout(() => {
            // VẼ LẦN ĐẦU (CHẾ ĐỘ CHI TIẾT)
            drawMindmap(data.topic, nodesToDraw, false); 
        }, 800);

    } catch (e) {
        console.error(e);
        alert("❌ Lỗi kết nối server!");
    } finally {
        isProcessing = false; 
        importBtn.innerText = "🚀 Phân tích & Tạo Mindmap";
        importBtn.disabled = false;
        summaryBtn.disabled = false;
        detailBtn.disabled = false;
    }
});

// -------------------------
// XEM TÓM TẮT & CHI TIẾT
// -------------------------
summaryBtn.addEventListener("click", () => {
    if (!lastMindmapData || !mindmapSummaryNodes) return alert("Bạn chưa phân tích file!");
    
    // 1. Hiển thị Tóm tắt dạng Alert
    alert("📘 TÓM TẮT:\n\n" + lastMindmapData.summary.join("\n")); 
    
    // 2. VẼ MINDMAP TÓM TẮT (4 nhánh)
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawMindmap(lastMindmapData.topic, mindmapSummaryNodes, false);
});

detailBtn.addEventListener("click", () => {
    if (!lastMindmapData || !mindmapDetailNodes) return alert("Bạn chưa phân tích file!");
    
    // 1. Hiển thị Chi tiết dạng Alert
    alert("📙 CHI TIẾT:\n\n" + lastMindmapData.detail.join("\n"));
    
    // 2. VẼ MINDMAP CHI TIẾT (7+ nhánh)
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawMindmap(lastMindmapData.topic, mindmapDetailNodes, false);
});