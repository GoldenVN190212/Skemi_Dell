// ================= FIREBASE IMPORT =================
import { auth, db } from "./Firebase_config.js";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  FacebookAuthProvider,
  signInWithPopup,
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import {
  setDoc,
  doc,
  getDoc,
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";

export { auth, db, signOut };

// =================== HÀM KIỂM TRA ===================
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// =================== DOM EVENTS ===================
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
        const userCredential = await createUserWithEmailAndPassword(
          auth,
          email,
          password
        );
        const user = userCredential.user;

        // Lưu thông tin vào Firestore
        await setDoc(doc(db, "users", user.uid), {
          email,
          username,
          createdAt: new Date(),
        });

        alert(`✅ Chào mừng ${username} đến với Skemi!`);
        window.location.href = "Home.html";
      } catch (error) {
        let message = "❌ Đăng ký thất bại!";
        switch (error.code) {
          case "auth/email-already-in-use":
            message = "⚠️ Email này đã được sử dụng, vui lòng thử email khác!";
            break;
          case "auth/invalid-email":
          case "auth/invalid-credential":
            message = "⚠️ Email hoặc password không chính xác!";
            break;
          case "auth/weak-password":
            message = "⚠️ Mật khẩu quá yếu, vui lòng dùng ít nhất 6 ký tự!";
            break;
            
          default:
            message = `⚠️ Lỗi: ${error.message}`;
        }
        alert(message);
        console.error(error);
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
        const userCredential = await signInWithEmailAndPassword(
          auth,
          email,
          password
        );
        const user = userCredential.user;

        // Lấy username từ Firestore
        let username = "bạn";
        try {
          const userDoc = await getDoc(doc(db, "users", user.uid));
          if (userDoc.exists()) {
            username = userDoc.data().username;
          }
        } catch (err) {
          console.error("Lỗi lấy username:", err);
        }

        alert(`✅ Chào mừng ${username} đã quay trở lại Skemi!`);
        window.location.href = "Home.html";
      } catch (error) {
        console.error(error);
        let message = "❌ Đăng nhập thất bại!";

        switch (error.code) {
          case "auth/invalid-email":
          case "auth/wrong-password":
          case "auth/invalid-credential":
            message = "⚠️ Email hoặc mật khẩu không chính xác!";
            break;
          case "auth/user-disabled":
            message = "🚫 Tài khoản này đã bị vô hiệu hóa!";
            break;
          case "auth/user-not-found":
            message = "❌ Không tìm thấy tài khoản với email này!";
            break;
          default:
            message = `⚠️ Lỗi: ${error.code}`;
        }

        alert(message);
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

        // Nếu là lần đầu đăng nhập → lưu Firestore
        const userDoc = await getDoc(doc(db, "users", user.uid));
        if (!userDoc.exists()) {
          await setDoc(doc(db, "users", user.uid), {
            email: user.email,
            username: user.displayName || user.email.split("@")[0],
            createdAt: new Date(),
            provider: "Google",
          });
        }

        alert(`✅ Xin chào ${user.displayName || user.email}!`);
        window.location.href = "Home.html";
      } catch (error) {
        // Nếu người dùng đóng popup giữa chừng thì không báo lỗi
        if (error.code === "auth/popup-closed-by-user") {
          console.log("Người dùng đóng popup đăng nhập Google giữa chừng.");
          return;
        }

        alert("❌ Lỗi đăng nhập Google!");
        console.error(error);
      }
    });
  }
});

// =================== ĐĂNG NHẬP FACEBOOK ===================
const facebookBtn = document.getElementById("facebookLogin");
if (facebookBtn) {
  const fbProvider = new FacebookAuthProvider();
  facebookBtn.addEventListener("click", async () => {
    try {
      const result = await signInWithPopup(auth, fbProvider);
      const user = result.user;

      // Nếu là lần đầu đăng nhập → lưu Firestore
      const userDoc = await getDoc(doc(db, "users", user.uid));
      if (!userDoc.exists()) {
        await setDoc(doc(db, "users", user.uid), {
          email: user.email,
          username: user.displayName || user.email.split("@")[0],
          createdAt: new Date(),
          provider: "Facebook",
        });
      }

      alert(`✅ Xin chào ${user.displayName || user.email}!`);
      window.location.href = "Home.html";
    } catch (error) {
      // Nếu người dùng đóng popup giữa chừng thì không báo lỗi
      if (error.code === "auth/popup-closed-by-user") {
        console.log("Người dùng đóng popup Facebook giữa chừng.");
        return;
      }

      alert("❌ Lỗi đăng nhập Facebook!");
      console.error(error);
    }
  });
}