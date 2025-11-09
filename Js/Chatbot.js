const sendBtn = document.getElementById("sendBtn");
const userInput = document.getElementById("userInput");
const chatContainer = document.getElementById("chatContainer");

// append tin nhắn
function appendMessage(sender, text, loading=false) {
  const msg = document.createElement("div");
  if (loading) {
    msg.className = "ai-msg loading";
    msg.textContent = "AI đang trả lời...";
  } else {
    msg.className = sender === "Bạn" ? "user-msg" : "ai-msg";
    msg.textContent = text;
  }
  chatContainer.appendChild(msg);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Gửi tin nhắn
sendBtn.addEventListener("click", async () => {
  const question = userInput.value.trim();
  if (!question) return;

  appendMessage("Bạn", question);
  userInput.value = "";

  // hiệu ứng chờ AI
  const loadingMsg = document.createElement("div");
  loadingMsg.className = "ai-msg loading";
  loadingMsg.textContent = "AI đang trả lời...";
  chatContainer.appendChild(loadingMsg);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });

    const data = await res.json();
    chatContainer.removeChild(loadingMsg);
    appendMessage("AI", data.answer || "Không có câu trả lời.");
  } catch (err) {
    chatContainer.removeChild(loadingMsg);
    appendMessage("AI", "Lỗi kết nối server.");
    console.error(err);
  }
});

// File upload tạm thời
document.getElementById("uploadBtn").addEventListener("click", async () => {
  const file = document.getElementById("fileInput").files[0];
  if (!file) return alert("Chọn file để upload");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();
    alert(data.message || "Upload xong");
  } catch (err) {
    console.error(err);
    alert("Upload thất bại");
  }
});
