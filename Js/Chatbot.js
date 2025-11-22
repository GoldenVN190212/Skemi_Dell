import { auth } from "./Auth.js";

// --- ELEMENTS ---
const sendBtn = document.getElementById("sendBtn");
const stopBtn = document.getElementById("stopBtn")
const userInput = document.getElementById("userInput");
const chatContainer = document.getElementById("chatContainer");
const chatTitle = document.getElementById("chatTitle");

// --- STATE MANAGEMENT ---
let sessionId = localStorage.getItem("chat_session_id");
if (!sessionId) {
    sessionId = "sess_" + Math.random().toString(36).substring(2, 10);
    localStorage.setItem("chat_session_id", sessionId);
}
let isProcessing = false;
let abortController = null;

// --- UI STATE FUNCTIONS ---
function setUIState(processing) {
    isProcessing = processing;
    userInput.disabled = processing;
    sendBtn.disabled = processing;
    
    // Hiển thị/Ẩn nút Dừng
    if (stopBtn) { 
        stopBtn.style.display = processing ? 'inline-block' : 'none';
        sendBtn.style.display = processing ? 'none' : 'inline-block';
    }
    
    if (processing) {
        userInput.placeholder = "AI đang trả lời, vui lòng chờ...";
    } else {
        userInput.placeholder = "Nhập câu hỏi của bạn...";
    }
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
    
    // *** KHẮC PHỤC LỖI CUỘN ***
    // Chỉ cuộn xuống cuối khi tin nhắn mới được thêm vào, 
    // không cuộn trong quá trình gõ chữ (typeText)
    if (!loading) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
    return msg;
}

// Biến toàn cục để lưu trữ tin nhắn đang tải (loading message)
let currentLoadingMsg = null; 

// --- TYPE TEXT EFFECT (Đã sửa lỗi thêm chữ Dừng lặp lại) ---
async function typeText(element, text, speed = 30) {
    element.textContent = "";
    // Vòng lặp gõ chữ chỉ thêm từng ký tự
    for (let char of text) {
        // Nếu request bị hủy, DỪNG GÕ chữ NGAY LẬP TỨC
        if (abortController && abortController.signal.aborted) {
            return; // KHÔNG thêm bất kỳ chữ nào ở đây
        }
        element.textContent += char;
        await new Promise(r => setTimeout(r, speed));
    }
    // Sau khi gõ xong, cuộn xuống cuối để hiển thị kết quả hoàn chỉnh
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// --- SEND QUESTION (Đã sửa lỗi thêm chữ Dừng lặp lại) ---
async function sendQuestion() {
    if (isProcessing) return; // Ngăn chặn gửi khi đang xử lý

    const question = userInput.value.trim();
    if (!question) return;

    appendMessage("Bạn", question);
    userInput.value = "";
    setUIState(true); // Vô hiệu hóa input
    
    abortController = new AbortController(); // Tạo Controller mới
    const loadingMsg = appendMessage("AI", "", true);
    currentLoadingMsg = loadingMsg; // Lưu lại reference của loading message

    try {
        const res = await fetch("http://127.0.0.1:8000/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, question }),
            signal: abortController.signal // Gắn signal vào request
        });
        
        if (res.ok) {
            const data = await res.json();
            await typeText(loadingMsg, `(${data.model}) ${data.answer}`);
            // typeText đã hoàn thành, không cần thêm class loading nữa
            loadingMsg.className = "ai-msg"; 
        } else {
            loadingMsg.className = "ai-msg";
            loadingMsg.textContent = `Lỗi Server: ${res.status}. Vui lòng kiểm tra lại Server Python.`;
        }

    } catch (err) {
        if (err.name === 'AbortError') {
            // Lỗi AbortError sẽ được xử lý trong khối finally
            // Đảm bảo không có console.error ở đây để tránh thông báo đỏ không cần thiết
        } else {
            loadingMsg.className = "ai-msg";
            loadingMsg.textContent = "Server đang tạm dừng hoặc bị lỗi kết nối.";
            console.error(err);
        }
    } finally {
        // --- LOGIC CUỐI CÙNG ĐỂ XỬ LÝ TRẠNG THÁI LOADING VÀ THÔNG BÁO DỪNG ---
        if (abortController && abortController.signal.aborted) {
            // Nếu request bị hủy
            if (currentLoadingMsg) {
                 // Đảm bảo nội dung chỉ là "Quá trình tạo phản hồi đã dừng."
                 // hoặc thêm vào cuối nếu đã có chữ nào đó từ typeText
                 if (currentLoadingMsg.textContent === "AI đang trả lời...") {
                     currentLoadingMsg.textContent = "";
                 } else if (!currentLoadingMsg.textContent.includes("(Dừng)")) {
                     currentLoadingMsg.textContent += ' (Dừng)';
                 }
                 currentLoadingMsg.className = "ai-msg error-msg"; // Tắt nhấp nháy, có thể đổi màu nếu muốn
            }
        } else if (currentLoadingMsg && currentLoadingMsg.className.includes("loading")) {
             // Nếu không bị hủy, nhưng vẫn còn trạng thái loading (ví dụ: typeText chưa kịp hoàn tất)
             currentLoadingMsg.className = "ai-msg"; 
        }
        
        currentLoadingMsg = null; // Xóa reference
        setUIState(false); // Kích hoạt lại input
        abortController = null;
        // reset session
        sessionId = "sess_" + Math.random().toString(36).substring(2, 10);
        localStorage.setItem("chat_session_id", sessionId);
    }
}

// --- STOP GENERATION FUNCTION ---
function stopGeneration() {
    if (abortController) {
        abortController.abort(); // Hủy request đang chờ
    }
}

// --- EVENT LISTENERS ---
sendBtn.addEventListener("click", sendQuestion);
stopBtn.addEventListener("click", stopGeneration); // <--- Mới: Gắn sự kiện dừng

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