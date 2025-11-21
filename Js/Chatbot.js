import { auth } from "./Auth.js";

// --- ELEMENTS ---
const sendBtn = document.getElementById("sendBtn");
const userInput = document.getElementById("userInput");
const chatContainer = document.getElementById("chatContainer");
const chatTitle = document.getElementById("chatTitle");

// --- SESSION ---
let sessionId = localStorage.getItem("chat_session_id");
if (!sessionId) {
  sessionId = "sess_" + Math.random().toString(36).substring(2, 10);
  localStorage.setItem("chat_session_id", sessionId);
}

// --- UPDATE TITLE BASED ON AUTH ---
auth.onAuthStateChanged(user => {
  if (user) {
    const username = user.email.split("@")[0];
    chatTitle.textContent = `Xin chào ${username}, hôm nay bạn muốn học bài toán nào?`;
  } else {
    chatTitle.textContent = "Xin chào bạn, hôm nay bạn muốn học bài toán nào?";
  }
});

// --- APPEND MESSAGE ---
function appendMessage(sender, text = "", loading = false) {
  const msg = document.createElement("div");
  msg.className = loading ? "ai-msg loading" : (sender === "Bạn" ? "user-msg" : "ai-msg");
  msg.textContent = loading ? "AI đang trả lời..." : text;
  chatContainer.appendChild(msg);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return msg;
}

// --- TYPE TEXT EFFECT ---
async function typeText(element, text, speed = 30) {
  element.textContent = "";
  for (let char of text) {
    element.textContent += char;
    chatContainer.scrollTop = chatContainer.scrollHeight;
    await new Promise(r => setTimeout(r, speed));
  }
}

// --- SEND QUESTION ---
async function sendQuestion() {
  const question = userInput.value.trim();
  if (!question) return;

  appendMessage("Bạn", question);
  userInput.value = "";

  const loadingMsg = appendMessage("AI", "", true);

  try {
    const res = await fetch("http://127.0.0.1:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, question })
    });
    const data = await res.json();
    await typeText(loadingMsg, `(${data.model}) ${data.answer}`);
    loadingMsg.className = "ai-msg";
  } catch (err) {
    loadingMsg.className = "ai-msg";
    loadingMsg.textContent = "Server đang tạm dừng để bảo trì.";
    console.error(err);
  }

  // reset session
  sessionId = "sess_" + Math.random().toString(36).substring(2, 10);
  localStorage.setItem("chat_session_id", sessionId);
}

// --- EVENT LISTENERS ---
sendBtn.addEventListener("click", sendQuestion);

userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
});

// --- BEFORE UNLOAD SESSION CLEANUP ---
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
