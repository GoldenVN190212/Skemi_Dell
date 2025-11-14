import { auth } from "./Firebase_config.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";

document.addEventListener("DOMContentLoaded", () => {

  const authButtons = document.getElementById("auth-buttons");
  const logoutBtn = document.getElementById("logoutBtn");

  onAuthStateChanged(auth, async (user) => {
    // Xóa toàn bộ nút cũ
    authButtons.innerHTML = "";

    if (!user) {
      // Chưa đăng nhập
      authButtons.innerHTML = `
        <button class="tab" id="signupBtn">Sign up</button>
        <button class="tab" id="loginBtn">Log in</button>
      `;

      document.getElementById("signupBtn").onclick = () =>
        (window.location.href = "Register.html");
      document.getElementById("loginBtn").onclick = () =>
        (window.location.href = "Login.html");

      return;
    }

    // Đã đăng nhập
    const email = user.email;
    const username = email.split("@")[0];

    const userBtn = document.createElement("button");
    userBtn.className = "tab user-btn";
    userBtn.innerText = `🔒 ${username}`;
    authButtons.appendChild(userBtn);

    // Logout
    if (logoutBtn) {
      logoutBtn.style.display = "block";
      logoutBtn.onclick = async () => {
        await signOut(auth);
        window.location.href = "Login.html";
      };
    }
  });
});
