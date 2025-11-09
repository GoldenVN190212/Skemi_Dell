// ================= FIREBASE INIT =================
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js";
import { 
  getAuth, 
  createUserWithEmailAndPassword, 
  signInWithEmailAndPassword 
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";

// 🔥 Thêm cấu hình Firebase của cậu chủ tại đây:
const firebaseConfig = {
  apiKey: "AIzaSyBYAgeL5xl2yfKMcmgiln5etyy-I-fvot0",
  authDomain: "skemivn.firebaseapp.com",
  projectId: "skemivn",
  storageBucket: "skemivn.firebasestorage.app",
  messagingSenderId: "430145480951",
  appId: "1:430145480951:web:dd640a426315a19aadcbf2"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// ================= ĐĂNG KÝ =================
const registerForm = document.getElementById("registerForm");
if (registerForm) {
  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (password !== confirmPassword) {
      alert("⚠️ Mật khẩu xác nhận không khớp!");
      return;
    }

    try {
      await createUserWithEmailAndPassword(auth, email, password);
      alert("✅ Tạo tài khoản thành công!");
      window.location.href = "Home.html";
    } catch (error) {
      alert("❌ Lỗi: " + error.message);
    }
  });
}

// ================= ĐĂNG NHẬP =================
const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;

    try {
      await signInWithEmailAndPassword(auth, email, password);
      alert("✅ Đăng nhập thành công!");
      window.location.href = "Home.html"; // Trang chính Skemi
    } catch (error) {
      alert("❌ Lỗi: " + error.message);
    }
  });
}

export { app }; 
