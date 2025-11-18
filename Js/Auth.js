// ================= FIREBASE IMPORT =================
import { auth, db } from "./Firebase_config.js";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  FacebookAuthProvider,
  signInWithPopup,
  signOut
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";

import {
  setDoc,
  doc,
  getDoc,
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";

// Export cho navbar dùng
export { auth, db, signOut };

// =================== VALIDATION ===================
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// =================== MAIN ===================
document.addEventListener("DOMContentLoaded", () => {

  // =================== ĐĂNG KÝ ===================
  const signupForm = document.getElementById("registerForm");
  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const username = document.getElementById("signupUsername").value.trim();
      const email = document.getElementById("signupEmail").value.trim();
      const password = document.getElementById("signupPassword").value;
      const confirmPassword = document.getElementById("confirmPassword").value;

      if (!isValidEmail(email)) return alert("⚠️ Email không hợp lệ!");
      if (password !== confirmPassword)
        return alert("⚠️ Mật khẩu xác nhận không khớp!");

      try {
        const userCredential = await createUserWithEmailAndPassword(auth, email, password);
        const user = userCredential.user;

        await setDoc(doc(db, "users", user.uid), {
          email,
          username,
          createdAt: new Date(),
        });

        alert(`🎉 Chào mừng ${username} đến với Skemi!`);
        window.location.href = "Home.html";

      } catch (error) {
        console.error(error);
        let msg = "❌ Đăng ký thất bại!";
        switch (error.code) {
          case "auth/email-already-in-use":
            msg = "⚠️ Email này đã được sử dụng!";
            break;
          case "auth/weak-password":
            msg = "⚠️ Mật khẩu quá yếu!";
            break;
          case "auth/invalid-email":
          case "auth/invalid-credential":
            msg = "⚠️ Email hoặc mật khẩu không hợp lệ!";
            break;
        }
        alert(msg);
      }
    });
  }

  // =================== ĐĂNG NHẬP ===================
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const email = document.getElementById("loginEmail").value.trim();
      const password = document.getElementById("loginPassword").value;

      try {
        const userCredential = await signInWithEmailAndPassword(auth, email, password);
        const user = userCredential.user;

        // Lấy username
        let username = "bạn";
        const snap = await getDoc(doc(db, "users", user.uid));
        if (snap.exists()) username = snap.data().username;

        alert(`👋 Chào mừng ${username} quay lại Skemi!`);
        window.location.href = "Home.html";

      } catch (error) {
        console.error(error);
        let msg = "❌ Đăng nhập thất bại!";
        switch (error.code) {
          case "auth/wrong-password":
          case "auth/invalid-email":
          case "auth/user-not-found":
          case "auth/invalid-credential":
            msg = "⚠️ Email hoặc mật khẩu không chính xác!";
            break;
          case "auth/user-disabled":
            msg = "🚫 Tài khoản đã bị vô hiệu hóa!";
            break;
        }
        alert(msg);
      }
    });
  }

  // =================== ĐĂNG NHẬP GOOGLE ===================
  const googleBtn = document.getElementById("googleLogin");
  if (googleBtn) {
    const provider = new GoogleAuthProvider();

    googleBtn.addEventListener("click", async () => {
      try {
        const result = await signInWithPopup(auth, provider);
        const user = result.user;

        const snap = await getDoc(doc(db, "users", user.uid));
        if (!snap.exists()) {
          await setDoc(doc(db, "users", user.uid), {
            email: user.email,
            username: user.displayName || user.email.split("@")[0],
            provider: "Google",
            createdAt: new Date(),
          });
        }

        alert(`🎉 Xin chào ${user.displayName || user.email}!`);
        window.location.href = "Home.html";

      } catch (error) {
        console.error(error);
        alert("⚠️ Lỗi đăng nhập Google!");
      }
    });
  }

  // =================== ĐĂNG NHẬP FACEBOOK ===================
  const facebookBtn = document.getElementById("facebookLogin");
  if (facebookBtn) {
    const provider = new FacebookAuthProvider();

    facebookBtn.addEventListener("click", async () => {
      try {
        const result = await signInWithPopup(auth, provider);
        const user = result.user;

        const snap = await getDoc(doc(db, "users", user.uid));
        if (!snap.exists()) {
          await setDoc(doc(db, "users", user.uid), {
            email: user.email,
            username: user.displayName || user.email.split("@")[0],
            provider: "Facebook",
            createdAt: new Date(),
          });
        }

        alert(`🎉 Xin chào ${user.displayName || user.email}!`);
        window.location.href = "Home.html";

      } catch (error) {
        console.error(error);
        alert("⚠️ Lỗi đăng nhập Facebook!");
      }
    });
  }

});
