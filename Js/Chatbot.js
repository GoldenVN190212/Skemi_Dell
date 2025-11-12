const sendBtn = document.getElementById("sendBtn");
const userInput = document.getElementById("userInput");
const chatContainer = document.getElementById("chatContainer");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");

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

// Gửi câu hỏi tới server
async function sendQuestion() {
  const question = userInput.value.trim();
  if (!question) return;

  appendMessage("Bạn", question);
  userInput.value = "";

  const loadingMsg = document.createElement("div");
  loadingMsg.className = "ai-msg loading";
  loadingMsg.textContent = "AI đang trả lời...";
  chatContainer.appendChild(loadingMsg);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const res = await fetch("http://127.0.0.1:8000/ask", {
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
}

sendBtn.addEventListener("click", sendQuestion);

// Nhấn Enter để gửi
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
});

// Upload file
uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) return alert("Chọn file để upload");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("http://127.0.0.1:8000/upload", { method: "POST", body: formData });
    const data = await res.json();
    alert(data.message || "Upload xong");
  } catch (err) {
    console.error(err);
    alert("Upload thất bại");
  }
});
