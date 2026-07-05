import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";
import { getDatabase } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-database.js";
import { getStorage } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-storage.js";
import { getAuth, signOut } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyC_X2pMyDU_3YIVMGBDMddIPll_vQRf5Gw",
  authDomain: "skemma-efe9b.firebaseapp.com",
  databaseURL: "https://skemma-efe9b-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "skemma-efe9b",
  storageBucket: "skemma-efe9b.appspot.com",
  messagingSenderId: "783277922550",
  appId: "1:783277922550:web:63051241ddc7d185e3f4d7"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const rtdb = getDatabase(app);
const storage = getStorage(app);
const auth = getAuth(app);

export { app, auth, db, rtdb, storage, signOut };
