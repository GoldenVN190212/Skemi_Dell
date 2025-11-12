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

  onAuthStateChanged(auth, async (user) => {
    if (!navbar) return;

    // Xóa nút cũ tránh trùng
    navbar.querySelectorAll("#signupBtn,#loginBtn,#userBtn").forEach(b => b.remove());

    if (!user) {
      // 🔹 Nếu chưa đăng nhập
      navbar.innerHTML += `
        <button class="tab" id="signupBtn">Sign up</button>
        <button class="tab" id="loginBtn">Log in</button>
      `;
      if (logout) logout.style.display = "none";

      document.getElementById("signupBtn").onclick = () =>
        (window.location.href = "Register.html");
      document.getElementById("loginBtn").onclick = () =>
        (window.location.href = "Login.html");
    } else {
      // 🔹 Nếu đã đăng nhập
      let username = "Người dùng";
      const email = user.email; // 🔹 Lấy email để hiển thị trong console

      // Nếu user đăng ký bằng email/password → lấy username trong Firestore
      try {
        const docRef = doc(db, "users", user.uid);
        const userDoc = await getDoc(docRef);
        if (userDoc.exists()) {
          username = userDoc.data().username || user.displayName || email.split("@")[0];
        } else {
          // Nếu là Google / Facebook → lấy tên từ displayName
          username = user.displayName || email.split("@")[0];
        }
      } catch (e) {
        console.error("Lỗi khi lấy username:", e);
        username = user.displayName || email.split("@")[0];
      }

      // 🔹 Tạo nút hiển thị user (hiển thị username)
      const userBtn = document.createElement("button");
      userBtn.className = "tab user-btn";
      userBtn.id = "userBtn";
      userBtn.innerHTML = `🔒 ${username}`;

      navbar.appendChild(userBtn);

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
