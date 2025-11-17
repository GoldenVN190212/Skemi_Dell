// ----------------------------
// HOME.JS (FULL FIXED v2)
// Hiện topic + vẽ mindmap
// ----------------------------

const fileInput = document.getElementById("fileInput");
const importBtn = document.getElementById("importBtn");
const summaryBtn = document.getElementById("summaryBtn");
const detailBtn = document.getElementById("detailBtn");
const canvas = document.getElementById("mindmapCanvas");
const ctx = canvas.getContext("2d");

let lastMindmapData = null;

// ----------------------------
// Typing text effect on canvas
// ----------------------------
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

// ----------------------------
// Draw mindmap
// ----------------------------
async function drawMindmap(topic, subtopics) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Main topic typing
    await typeCanvasText(300, 60, topic);

    // Subtopics
    ctx.font = "18px Arial";
    let y = 120;
    for (let s of subtopics) {
        await typeCanvasText(50, y, "- " + s, 10);
        y += 30;
    }
}

// ----------------------------
// IMPORT FILE → SERVER
// ----------------------------
importBtn.addEventListener("click", async () => {
    if (!fileInput.files.length) {
        alert("⚠️ Vui lòng chọn file trước!");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        importBtn.innerText = "⏳ Đang xử lý...";
        importBtn.disabled = true;

        const res = await fetch("http://localhost:8000/generate_mindmap", {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        console.log("Server trả về:", data);

        if (data.error) {
            alert("❌ Lỗi server: " + data.error);
            return;
        }

        // Save returned data
        lastMindmapData = data;

        // ✔️ Thông báo chủ đề
        alert(`📌 Chủ đề chính của tài liệu là:\n\n👉 ${data.topic}`);

        // ✔️ Vẽ mindmap
        drawMindmap(data.topic, data.detail);

    } catch (e) {
        console.error(e);
        alert("❌ Lỗi không gửi được file!");
    } finally {
        importBtn.innerText = "📥 Import tài liệu";
        importBtn.disabled = false;
    }
});

// ----------------------------
// NÚT TÓM TẮT
// ----------------------------
summaryBtn.addEventListener("click", () => {
    if (!lastMindmapData) return alert("Bạn chưa import file!");

    alert("📘 TÓM TẮT:\n\n" + lastMindmapData.summary.join("\n"));
});

// ----------------------------
// NÚT CHI TIẾT
// ----------------------------
detailBtn.addEventListener("click", () => {
    if (!lastMindmapData) return alert("Bạn chưa import file!");

    alert("📙 CHI TIẾT:\n\n" + lastMindmapData.detail.join("\n"));
});
