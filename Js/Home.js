import {
  getAuth,
  signOut,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import { app } from "./Auth.js";
import { findClosestTopic } from "./Topicmatch.js";

const auth = getAuth(app);

// ======================= AUTH =======================
onAuthStateChanged(auth, (user) => {
  if (!user) {
    window.location.href = "Login.html";
  } else {
    console.log("🔐 Người dùng:", user.email);
  }
});

document.getElementById("logoutBtn")?.addEventListener("click", async () => {
  try {
    await signOut(auth);
    alert("👋 Đăng xuất thành công!");
    window.location.href = "Login.html";
  } catch (error) {
    alert("❌ Lỗi khi đăng xuất: " + error.message);
  }
});

// ======================= DOM ELEMENTS =======================
const fileInput = document.getElementById("fileInput");
const importBtn = document.getElementById("importBtn");
const summaryBtn = document.getElementById("summaryBtn");
const detailBtn = document.getElementById("detailBtn");
const completeBtn = document.getElementById("completeBtn");
const canvas = document.getElementById("mindmapCanvas");
const ctx = canvas.getContext("2d");

let lastMindmapImage = null;

// ======================= NÚT =======================
importBtn?.addEventListener("click", async () => {
  await generateMindmap("summary");
});

summaryBtn?.addEventListener("click", async () => {
  await generateMindmap("summary");
});

detailBtn?.addEventListener("click", async () => {
  await generateMindmap("detail");
});

completeBtn?.addEventListener("click", () => {
  alert("🎯 Đang tạo bài tập luyện tập cho chủ đề này...");
});

// ======================= TẠO MINDMAP =======================
async function generateMindmap(mode) {
  const file = fileInput?.files?.[0];
  if (!file) {
    alert("⚠️ Vui lòng chọn tệp tài liệu trước!");
    return;
  }

  const text = await extractText(file);

  const response = await fetch("http://127.0.0.1:5000/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) throw new Error("Server không phản hồi");

  const result = await response.json();
  const aiTopic = result.topic || "Chủ đề chưa xác định";
  const vectorTopic = (await findClosestTopic(text))?.name;
  let topic =
    aiTopic !== "Chủ đề chưa xác định"
      ? aiTopic
      : vectorTopic || "Chủ đề chưa xác định";

  if (topic === "Chủ đề chưa xác định") {
    const manualTopic = prompt("❓ Không xác định được chủ đề. Bạn muốn gán chủ đề nào?");
    if (!manualTopic) return;
    topic = manualTopic;
  }

  alert(`🧠 Chủ đề được nhận diện: ${topic}`);

  const subRes = await fetch("http://127.0.0.1:5000/extract_subtopics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, mode }),
  });
  const subData = await subRes.json();
  const subTopics = subData.subtopics || ["Ý 1", "Ý 2", "Ý 3"];

  drawMindmap(topic, subTopics);
}

// ======================= VẼ MINDMAP ĐẸP =======================
function drawMindmap(mainTopic, subTopics) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // nền mịn
  const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
  gradient.addColorStop(0, "#121212");
  gradient.addColorStop(1, "#1f1f1f");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;

  // ô trung tâm
  drawBubble(centerX, centerY, 120, "#00ffc8", mainTopic, true);

  const radius = 220;
  subTopics.forEach((topic, i) => {
    const angle = (i / subTopics.length) * Math.PI * 2;
    const x = centerX + Math.cos(angle) * radius;
    const y = centerY + Math.sin(angle) * radius;

    // vẽ đường nối
    ctx.strokeStyle = "rgba(0,255,200,0.5)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(x, y);
    ctx.stroke();

    // vẽ bong bóng
    drawBubble(x, y, 90, "#00b8ff", topic, false);
  });

  // lưu ảnh
  lastMindmapImage = canvas.toDataURL("image/png");
  localStorage.setItem("skemi_last_mindmap", lastMindmapImage);
}

// ======================= VẼ Ô TRÒN TỰ CO CHỮ =======================
function drawBubble(x, y, radius, color, text, isCenter = false) {
  ctx.shadowBlur = 20;
  ctx.shadowColor = color;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowBlur = 0;
  ctx.fillStyle = "#000";
  ctx.textAlign = "center";

  const maxWidth = radius * 1.6;
  const lines = wrapText(ctx, text, maxWidth, isCenter ? 18 : 14);

  const lineHeight = isCenter ? 20 : 16;
  const startY = y - ((lines.length - 1) * lineHeight) / 2;

  lines.forEach((line, i) => {
    ctx.fillText(line, x, startY + i * lineHeight);
  });
}

// ======================= TỰ XUỐNG DÒNG =======================
function wrapText(ctx, text, maxWidth, baseFont) {
  let words = text.split(" ");
  let lines = [];
  let line = "";

  ctx.font = `${baseFont}px Poppins`;

  words.forEach((word) => {
    const testLine = line + word + " ";
    const metrics = ctx.measureText(testLine);
    if (metrics.width > maxWidth && line !== "") {
      lines.push(line.trim());
      line = word + " ";
    } else {
      line = testLine;
    }
  });

  lines.push(line.trim());
  return lines;
}

// ======================= KHÔI PHỤC MINDMAP =======================
window.addEventListener("load", () => {
  const saved = localStorage.getItem("skemi_last_mindmap");
  if (saved) {
    const img = new Image();
    img.src = saved;
    img.onload = () => ctx.drawImage(img, 0, 0);
  }
});

// ======================= ĐỌC FILE =======================
async function extractText(file) {
  const ext = file.name.split(".").pop().toLowerCase();

  if (file.type.startsWith("image/")) {
    const result = await Tesseract.recognize(file, "vie+eng");
    return result.data.text;
  }

  if (ext === "pdf") {
    const buffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buffer }).promise;
    let text = "";
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      text += content.items.map((t) => t.str).join(" ");
    }
    return text;
  }

  if (ext === "docx") {
    const arrayBuffer = await file.arrayBuffer();
    const doc = await mammoth.extractRawText({ arrayBuffer });
    return doc.value;
  }

  if (ext === "pptx") {
    return await extractTextFromPPTX(file);
  }

  if (file.type.startsWith("text/") || ext === "json") {
    return await file.text();
  }

  return "Không thể đọc được loại file này.";
}

async function extractTextFromPPTX(file) {
  const zip = await JSZip.loadAsync(file);
  let text = "";
  const slides = Object.keys(zip.files).filter((f) =>
    f.startsWith("ppt/slides/slide")
  );
  for (const slide of slides) {
    const xml = await zip.file(slide).async("string");
    const matches = xml.match(/<a:t>(.*?)<\/a:t>/g);
    if (matches) {
      text += matches.map((t) => t.replace(/<\/?a:t>/g, "")).join(" ");
    }
  }
  return text;
}

// ======================= CHỐNG RELOAD =======================
document.querySelectorAll("button").forEach((btn) => {
  btn.type = "button";
});
