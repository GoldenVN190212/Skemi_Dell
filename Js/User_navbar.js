import { auth, db } from "./Firebase_config.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import {
  doc,
  getDoc
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";

document.addEventListener("DOMContentLoaded", () => {
  const navbar = document.getElementById("navbar");
  const logout = document.getElementById("logoutBtn");
  const authButtons = document.getElementById("auth-buttons"); // 👈 THÊM DÒNG NÀY
  
  onAuthStateChanged(auth, async (user) => {
    // if (!navbar) return; // Không cần thiết nếu authButtons được thêm vào

    // Xóa nút cũ tránh trùng. Cập nhật selector
    authButtons.querySelectorAll("#signupBtn,#loginBtn,#userBtn").forEach(b => b.remove()); // 👈 CẬP NHẬT DÒNG NÀY

    // ... (Tiếp tục từ User_navbar.js)

    if (!user) {
      // 🔹 Nếu chưa đăng nhập
      authButtons.innerHTML += `
        <button class="tab" id="signupBtn">Sign up</button>
        <button class="tab" id="loginBtn">Log in</button>
      `; // 👈 CHÈN VÀO authButtons

      if (logout) logout.style.display = "none";
      
      // 👇 BỔ SUNG LẠI ĐOẠN CODE GÁN SỰ KIỆN CLICK CHO NÚT
      document.getElementById("signupBtn").onclick = () =>
        (window.location.href = "Register.html");
      document.getElementById("loginBtn").onclick = () =>
        (window.location.href = "Login.html");
      // 👆 KẾT THÚC PHẦN BỔ SUNG

    } else {

      
      // 🔹 Tạo nút hiển thị user (hiển thị username)
      const userBtn = document.createElement("button");
      userBtn.className = "tab user-btn";
      userBtn.id = "userBtn";
      userBtn.innerHTML = `🔒 ${username}`;

      authButtons.appendChild(userBtn); // 👈 CHÈN VÀO authButtons
      

      // 🔹 Console log email
      console.log(`🔒 Đã đăng nhập với email: ${email}`);

      // 🔹 Nút Logout
      if (logout) {
        logout.style.display = "block";
        logout.onclick = async () => {
          await signOut(auth);
          window.location.href = "Login.html";
        };
      }
    }
  });
});
