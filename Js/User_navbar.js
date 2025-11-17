import { auth, signOut } from "./Auth.js";

document.addEventListener("DOMContentLoaded",()=>{
  const authButtons=document.getElementById("auth-buttons");
  const logoutBtn=document.getElementById("logoutBtn");

  if(!authButtons) return;

  auth.onAuthStateChanged(async user=>{
    authButtons.innerHTML="";

    if(!user){
      authButtons.innerHTML=`
        <button class="tab" id="signupBtn">Sign up</button>
        <button class="tab" id="loginBtn">Log in</button>
      `;
      document.getElementById("signupBtn").onclick=()=>window.location.href="Register.html";
      document.getElementById("loginBtn").onclick=()=>window.location.href="Login.html";
      return;
    }

    const username=user.email.split("@")[0];
    const userBtn=document.createElement("button");
    userBtn.className="tab user-btn";
    userBtn.innerText=`🔒 ${username}`;
    authButtons.appendChild(userBtn);

    if(logoutBtn){
      logoutBtn.style.display="block";
      logoutBtn.onclick=async()=>{
        await signOut(auth);
        window.location.href="Login.html";
      }
    }
  });
});
