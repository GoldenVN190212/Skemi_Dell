// Home.js
const fileInput = document.getElementById("fileInput");
const importBtn = document.getElementById("importBtn");
const summaryBtn = document.getElementById("summaryBtn");
const detailBtn = document.getElementById("detailBtn");
const canvas = document.getElementById("mindmapCanvas");
const ctx = canvas.getContext("2d");

let lastMindmapData = null;

// -------------------------
// EFFECT: TYPE TEXT
// -------------------------
async function typeCanvasText(x, y, text, speed = 20) {
    ctx.font = "20px Arial";
    ctx.fillStyle = "#000";
    let current = "";
    for (let char of text) {
        current += char;
        ctx.clearRect(x, y - 20, 800, 30);
        ctx.fillText(current, x, y);
        await new Promise(r => setTimeout(r, speed));
    }
}

// -------------------------
// VẼ SƠ ĐỒ
// -------------------------
async function drawMindmap(topic, subtopics) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    await typeCanvasText(300, 60, topic);
    ctx.font = "18px Arial";
    let y = 120;
    for (let s of subtopics) {
        await typeCanvasText(50, y, "- " + s, 10);
        y += 30;
    }
}

// -------------------------
// IMPORT FILE
// -------------------------
importBtn.addEventListener("click", async () => {
    if (!fileInput.files.length) return alert("⚠️ Vui lòng chọn file trước!");

    const file = fileInput.files[0];
    const fileName = file.name.toLowerCase();

    // -----------------------------
    // KIỂM TRA ĐÚNG FILE POWERPOINT
    // -----------------------------
    let fileType = "Tài liệu";

    if (fileName.endsWith(".ppt") || fileName.endsWith(".pptx")) {
        fileType = "PowerPoint";
    } else if (fileName.endsWith(".pdf")) {
        fileType = "PDF";
    } else if (fileName.endsWith(".doc") || fileName.endsWith(".docx")) {
        fileType = "Word";
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
        importBtn.innerText = "⏳ Đang xử lý...";
        importBtn.disabled = true;

        const res = await fetch("http://localhost:8000/generate_mindmap", {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        if (data.error) return alert("❌ Lỗi server: " + data.error);

        lastMindmapData = data;

        // -----------------------------
        // ALERT CHỦ ĐỀ + LOẠI FILE
        // -----------------------------
        alert(
            `📌 Bạn vừa import file ${fileType}\n\n` +
            `👉 Chủ đề chính: ${data.topic}\n\n` +
            `👉 Có mô tả không? ${data.detail.length > 0 ? "Có" : "Không"}`
        );

        // -----------------------------
        // VẼ MINDMAP SAU KHI CÓ DỮ LIỆU
        // -----------------------------
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillText("✨ Đang vẽ sơ đồ nội dung...", 100, 200);

        setTimeout(() => {
            drawMindmap(data.topic, data.detail);
        }, 800);

    } catch (e) {
        console.error(e);
        alert("❌ Lỗi không gửi được file!");
    } finally {
        importBtn.innerText = "📥 Import tài liệu";
        importBtn.disabled = false;
    }
});

// -----------------------------
// NÚT XEM TÓM TẮT
// -----------------------------
summaryBtn.addEventListener("click", () => {
    if (!lastMindmapData) return alert("Bạn chưa import file!");
    alert("📘 TÓM TẮT:\n\n" + lastMindmapData.summary.join("\n"));
});

// -----------------------------
// NÚT XEM CHI TIẾT
// -----------------------------
detailBtn.addEventListener("click", () => {
    if (!lastMindmapData) return alert("Bạn chưa import file!");
    alert("📙 CHI TIẾT:\n\n" + lastMindmapData.detail.join("\n"));
});
