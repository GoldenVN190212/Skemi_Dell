// ================= FIREBASE IMPORT =================
import { auth, db } from "./Firebase_config.js";
import { getDoc, doc } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";

// =================== Khai báo phần tử =================
const sendBtn = document.getElementById("sendBtn");
const userInput = document.getElementById("userInput");
const chatContainer = document.getElementById("chatContainer");
const chatTitle = document.getElementById("chatTitle");

// =================== Tạo session tự động =================
let sessionId = localStorage.getItem("chat_session_id");
if (!sessionId) {
  sessionId = "sess_" + Math.random().toString(36).substring(2, 10);
  localStorage.setItem("chat_session_id", sessionId);
}

// =================== Lấy username từ Firestore =================
function loadUsername() {
  auth.onAuthStateChanged(async (user) => {
    let username = "bạn"; // mặc định

    if (user) {
      try {
        const userDoc = await getDoc(doc(db, "users", user.uid));
        if (userDoc.exists()) {
          username = userDoc.data().username;
          localStorage.setItem("username", username); // cập nhật lại
        }
      } catch (err) {
        console.error("Lỗi lấy username từ Firestore:", err);
      }
    }

    if (chatTitle) {
      chatTitle.textContent = `Xin chào ${username}, hôm nay bạn muốn học bài toán nào?`;
    }
  });
}


// Gọi hàm khi load trang
window.addEventListener("DOMContentLoaded", loadUsername);

// =================== Hiển thị tin nhắn =================
function appendMessage(sender, text, loading = false) {
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

// =================== Gửi câu hỏi =================
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
      body: JSON.stringify({
        session_id: sessionId,
        question: question
      })
    });

    const data = await res.json();
    chatContainer.removeChild(loadingMsg);
    appendMessage("AI", data.answer || "Không có câu trả lời.");
  } catch (err) {
    chatContainer.removeChild(loadingMsg);
    appendMessage("AI", "Server đang tạm dừng để bảo trì.");
    console.error(err);
  }
}

// =================== Nút Gửi & Enter =================
sendBtn.addEventListener("click", sendQuestion);
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
});

// =================== Xóa session khi rời trang =================
window.addEventListener("beforeunload", async () => {
  try {
    await fetch("http://127.0.0.1:8000/end_session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId })
    });
  } catch (err) {
    console.warn("Không xóa được session:", err);
  }
});
