// ================= FIREBASE INIT =================
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";
import { getStorage } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-storage.js";


// 🔥 Thêm cấu hình Firebase của cậu chủ tại đây:
const firebaseConfig = {
  apiKey: "AIzaSyC_X2pMyDU_3YIVMGBDMddIPll_vQRf5Gw",
  authDomain: "skemma-efe9b.firebaseapp.com",
  databaseURL: "https://skemma-efe9b-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "skemma-efe9b",
  storageBucket: "skemma-efe9b.firebasestorage.app",
  messagingSenderId: "783277922550",
  appId: "1:783277922550:web:63051241ddc7d185e3f4d7"
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