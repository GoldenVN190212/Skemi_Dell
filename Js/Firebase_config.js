// ================= FIREBASE INIT =================
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";
import { getStorage } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-storage.js";


// 🔥 Thêm cấu hình Firebase của cậu chủ tại đây:
const firebaseConfig = {
  apiKey: "AIzaSyBYAgeL5xl2yfKMcmgiln5etyy-I-fvot0",
  authDomain: "skemivn.firebaseapp.com",
  projectId: "skemivn",
  storageBucket: "skemivn.firebasestorage.app",
  messagingSenderId: "430145480951",
  appId: "1:430145480951:web:dd640a426315a19aadcbf2"
};

// Khởi tạo Firebase
const app = initializeApp(firebaseConfig);

// Các service
const auth = getAuth(app);
const db = getFirestore(app);
const storage = getStorage(app);

// Export ra ngoài
export { auth, db, storage };
export {app};