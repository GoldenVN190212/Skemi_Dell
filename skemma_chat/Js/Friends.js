// FILE: Friends.js ( SA LI HON CHNH)
import { db, auth } from "./Firebase_config.js";
import {
  collection,
  query,
  where,
  getDocs,
  getDoc,
  doc,
  updateDoc,
  arrayUnion,
  arrayRemove,
  onSnapshot,
  setDoc,
  orderBy,
  limit,
  addDoc,
  serverTimestamp
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";
import { getCurrentLanguage, getPack, localizeText } from "./SharedSettings.js?v=20260624c";

// DOM Elements
const searchInput = document.getElementById("friendSearchInput");
const addFriendBtn = document.getElementById("addFriendBtn");
const searchResults = document.getElementById("searchResults");
const friendsList = document.getElementById("friendsList");

function chatPack() {
  const current = repairFriendText(getPack(getCurrentLanguage()).chat || {});
  const fallback = repairFriendText(getPack('en').chat || {});
  const merged = { ...fallback, ...current };
  Object.keys(merged).forEach((key) => {
    if (typeof merged[key] === 'string' && /[\uFFFDÃÂáºá»ðŸâœâ€]/.test(merged[key])) {
      merged[key] = typeof fallback[key] === 'string' ? fallback[key] : repairFriendText(merged[key]);
    }
  });
  return merged;
}

function relativeLabel(key, count = null) {
  const pack = chatPack();
  const fallback = (getPack('en').chat || {})[key];
  const value = typeof pack[key] === 'string' ? pack[key] : (typeof fallback === 'string' ? fallback : '');
  const resolved = repairFriendText(value.replace('{count}', count == null ? '' : String(count)));
  if (/[\uFFFDÃÂáºá»ðŸâœâ€]/.test(resolved) && typeof fallback === 'string') {
    return repairFriendText(fallback.replace('{count}', count == null ? '' : String(count)));
  }
  return resolved;
}

function friendText(vi, en) {
  return localizeText(vi, en, getCurrentLanguage());
}

function repairFriendText(value) {
  if (Array.isArray(value)) {
    return value.map((item) => repairFriendText(item));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, repairFriendText(v)]));
  }
  if (typeof value !== 'string') return value;
  if (!/[ÃÂÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßáºá»ðŸâœ]/.test(value)) return value;
  try {
    return new TextDecoder('utf-8', { fatal: false }).decode(
      Uint8Array.from(value.split('').map((char) => char.charCodeAt(0) & 0xff))
    );
  } catch {}
  try {
    return decodeURIComponent(escape(value));
  } catch {
    return value;
  }
}

// =======================================================
//  CHATBOT CONSTANTS
// =======================================================
const CHATBOT_UID = "CHATBOT_SKEMI";
const CHATBOT_NAME = "Skemi AI";
const ENABLE_CHATBOT_FRIEND = true;

async function cleanupDisabledChatbotFriend() {
  if (ENABLE_CHATBOT_FRIEND || !currentUserUid) return;

  delete unreadCountsCache[CHATBOT_UID];
  delete lastMessagesCache[CHATBOT_UID];

  try {
    const storageKey = `unread_${currentUserUid}`;
    const parsed = JSON.parse(localStorage.getItem(storageKey) || '{}');
    if (parsed && typeof parsed === 'object' && CHATBOT_UID in parsed) {
      delete parsed[CHATBOT_UID];
      localStorage.setItem(storageKey, JSON.stringify(parsed));
    }
  } catch {}

  try {
    const userRef = doc(db, "users", currentUserUid);
    await updateDoc(userRef, {
      friends: arrayRemove(CHATBOT_UID)
    });
  } catch {}

  document.querySelectorAll(`[data-uid='${CHATBOT_UID}']`).forEach((node) => node.remove());
}

function isSkemiBotLabel(value = "") {
  return /^(skemi|skemma)(\s+ai)?$/i.test(String(value).trim());
}

function getSkemmaOrbAvatarMarkup() {
  return `
    <span class="skemma-nova-glow"></span>
    <span class="skemma-nova-orbit skemma-nova-orbit-a"></span>
    <span class="skemma-nova-orbit skemma-nova-orbit-b"></span>
    <span class="skemma-nova-core"></span>
    <span class="skemma-nova-gem"></span>
    <span class="skemma-nova-spark skemma-nova-spark-a"></span>
    <span class="skemma-nova-spark skemma-nova-spark-b"></span>
  `;
}

function getOriginalFriendMessageText(message) {
  return repairFriendText(message?.rawText || message?.text || message?.content || "");
}

function applyBotAvatarMarkup(avatarDiv) {
  if (!avatarDiv) return;
  avatarDiv.className = 'friend-avatar skemma-orb-avatar';
  avatarDiv.innerHTML = getSkemmaOrbAvatarMarkup();
  avatarDiv.textContent = '';
  avatarDiv.style.background = 'transparent';
  avatarDiv.style.backgroundImage = 'none';
  avatarDiv.style.color = 'transparent';
}

// To container cho tabs
const tabContainer = document.createElement("div");
tabContainer.style.cssText = `
  margin-top: 10px;
  display: flex;
  border-bottom: 1px solid rgba(255,255,255,0.1);
`;

// To cc tab
const friendsTab = document.createElement("button");
friendsTab.id = "friendsTab";
friendsTab.textContent = ` ${chatPack().friends}`;
friendsTab.style.cssText = `
  flex: 1;
  padding: 10px;
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  font-size: 14px;
  border-bottom: 2px solid transparent;
  transition: all 0.3s;
`;

const searchTab = document.createElement("button");
searchTab.id = "searchTab";
searchTab.textContent = ` ${chatPack().search}`;
searchTab.style.cssText = `
  flex: 1;
  padding: 10px;
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  font-size: 14px;
  border-bottom: 2px solid transparent;
  transition: all 0.3s;
`;

const createGroupBtn = document.createElement("button");
createGroupBtn.id = "createGroupBtn";
createGroupBtn.innerHTML = '<i class="fas fa-users"></i>';
createGroupBtn.title = chatPack().createGroup;
createGroupBtn.style.cssText = `
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  font-size: 16px;
  padding: 0 10px;
`;

// Thm tabs vo container
tabContainer.appendChild(friendsTab);
tabContainer.appendChild(searchTab);

// Chn tabs vo sau search box
const searchSection = document.querySelector('.search-section');
if (searchSection) {
  searchSection.appendChild(tabContainer);
  // Add create group button to search box area or header
  const searchBox = document.querySelector('.search-box');
  if (searchBox) {
      searchBox.appendChild(createGroupBtn);
  }
}

// To container ring cho search results
const searchResultsContainer = document.createElement("div");
searchResultsContainer.id = "searchResultsContainer";
searchResultsContainer.style.cssText = `
  display: none;
  margin-top: 15px;
  max-height: 400px;
  overflow-y: auto;
`;
searchResultsContainer.innerHTML = `
  <div style="padding: 10px 15px; color: rgba(255,255,255,0.7); font-size: 13px;">
    <i class="fas fa-search"></i> ${chatPack().search}</div>
  <div id="actualSearchResults" style="padding: 0 15px;"></div>
`;

// Thm search results container
searchSection.appendChild(searchResultsContainer);

window.addEventListener('languageChanged', () => {
  friendsTab.textContent = ` ${chatPack().friends}`;
  searchTab.textContent = ` ${chatPack().search}`;
  createGroupBtn.title = chatPack().createGroup;
  const header = searchResultsContainer.querySelector('div');
  if (header) {
    header.innerHTML = `<i class=\"fas fa-search\"></i> ${chatPack().search}`;
  }
});

let selectedUserToInvite = null;
let currentUserUid = null;
let currentChatFriendUid = null;
let currentUserData = {};
let userListenerUnsubscribe = null;

// Bin cache
let lastMessagesCache = {};
let unreadCountsCache = {};
let activeTab = "friends"; // 'friends' hoc 'search'

// Thm CSS animation
document.addEventListener('DOMContentLoaded', function() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes badgePulse {
      0%, 100% { 
        transform: translateY(-50%) scale(1); 
        box-shadow: 0 2px 10px rgba(255,107,157,.5);
      }
      50% { 
        transform: translateY(-50%) scale(1.1); 
        box-shadow: 0 4px 20px rgba(255,107,157,.8);
      }
    }
    
    .active-tab {
      color: white !important;
      border-bottom-color: #00d4ff !important;
      background: rgba(0, 212, 255, 0.1) !important;
    }
    
    .search-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 15px;
      border-radius: 10px;
      margin-bottom: 8px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      transition: all 0.3s;
    }
    
    .search-item:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(0, 212, 255, 0.3);
      transform: translateY(-2px);
    }
    
    .friend-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 15px;
      border-radius: 10px;
      margin-bottom: 8px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      transition: all 0.3s;
      position: relative;
      cursor: pointer;
    }
    
    .friend-item:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(0, 212, 255, 0.3);
    }
    
    .friend-item.active {
      background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(255, 107, 157, 0.15));
      border-color: rgba(0, 212, 255, 0.4);
      box-shadow: 0 4px 15px rgba(0, 212, 255, 0.15);
    }
    
    .chatbot-item {
      border-left: 3px solid #00d4ff !important;
    }
    
    .chatbot-item:hover {
      background: rgba(0, 212, 255, 0.1) !important;
    }
    
    .chatbot-item.active {
      background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(0, 168, 204, 0.15)) !important;
      border-color: #00a8cc !important;
    }

    .chatbot-alias-item .friend-avatar {
      background: transparent !important;
      color: transparent !important;
    }
    
    .add-friend-btn-small {
      background: linear-gradient(135deg, #00d4ff, #ff6b9d) !important;
      color: white !important;
      border: none !important;
      padding: 6px 12px !important;
      border-radius: 20px !important;
      font-size: 12px !important;
      cursor: pointer !important;
      display: flex;
      align-items: center;
      gap: 5px;
      transition: all 0.3s;
    }
    
    .add-friend-btn-small:hover {
      transform: scale(1.05);
      box-shadow: 0 3px 10px rgba(0, 212, 255, 0.4);
    }
    
    .add-friend-btn-small:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    
    .friend-avatar {
      width: 45px;
      height: 45px;
      border-radius: 50%;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: bold;
      font-size: 18px;
      flex-shrink: 0;
    }
    
    .skemma-orb-avatar {
      position: relative;
      overflow: hidden;
      background:
        radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.14) 18%, transparent 34%),
        linear-gradient(145deg, #11d5ff 0%, #6c4dff 52%, #ff5db1 100%) !important;
      box-shadow:
        inset 0 1px 10px rgba(255, 255, 255, 0.28),
        0 10px 18px rgba(98, 73, 255, 0.28);
    }

    .skemma-nova-glow {
      position: absolute;
      inset: 2px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0) 68%);
      filter: blur(2px);
    }

    .skemma-nova-orbit {
      position: absolute;
      border-radius: 50%;
      border: 1px solid rgba(255, 255, 255, 0.28);
      opacity: 0.78;
    }

    .skemma-nova-orbit-a {
      inset: 5px;
      transform: rotate(24deg);
    }

    .skemma-nova-orbit-b {
      inset: 9px 3px;
      transform: rotate(-28deg);
    }

    .skemma-nova-core {
      position: absolute;
      inset: 12px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #ffffff 0%, #d9eeff 38%, #79d4ff 66%, #5b6dff 100%);
      box-shadow: 0 0 12px rgba(155, 222, 255, 0.42);
    }

    .skemma-nova-gem {
      position: absolute;
      width: 11px;
      height: 11px;
      top: 8px;
      right: 8px;
      border-radius: 4px;
      background: linear-gradient(135deg, #ffe37b, #ff7bb5);
      transform: rotate(45deg);
      box-shadow: 0 0 10px rgba(255, 203, 122, 0.5);
    }

    .skemma-nova-spark {
      position: absolute;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.95);
      box-shadow: 0 0 8px rgba(255,255,255,0.7);
    }

    .skemma-nova-spark-a {
      left: 9px;
      bottom: 10px;
    }

    .skemma-nova-spark-b {
      left: 16px;
      top: 8px;
    }
    
    .friend-info {
      flex: 1;
      margin-left: 12px;
      min-width: 0;
    }
    
    .friend-name {
      font-weight: bold;
      font-size: 14px;
      color: var(--text);
      margin-bottom: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .chatbot-name {
      color: var(--text);
    }
    
    .friend-last-msg {
      font-size: 12px;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    
    .friend-meta {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 3px;
    }
    
    .friend-time {
      font-size: 11px;
      color: var(--text-muted);
    }
    
    .menu-dots {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 20px;
      padding: 5px;
      border-radius: 4px;
      line-height: 1;
    }
    
    .menu-dots:hover {
      background: rgba(255,255,255,0.1);
    }
    
    .empty-friends {
      text-align: center;
      padding: 40px 20px;
      color: var(--text-muted);
    }
    
    .empty-icon {
      font-size: 48px;
      margin-bottom: 15px;
    }
    
    .empty-text {
      font-size: 16px;
      font-weight: 500;
      margin-bottom: 8px;
    }
    
    .empty-subtext {
      font-size: 13px;
      color: rgba(255,255,255,0.4);
    }
  `;
  document.head.appendChild(style);
});

// =======================================================
//  TAB SWITCHING
// =======================================================
function switchTab(tabName) {
  activeTab = tabName;
  
  // Cp nht UI tabs
  if (tabName === "friends") {
    friendsTab.classList.add("active-tab");
    searchTab.classList.remove("active-tab");
    searchResultsContainer.style.display = "none";
    friendsList.style.display = "block";
  } else {
    friendsTab.classList.remove("active-tab");
    searchTab.classList.add("active-tab");
    searchResultsContainer.style.display = "block";
    friendsList.style.display = "none";
  }
}

// Event listeners cho tabs
friendsTab.addEventListener("click", () => {
  switchTab("friends");
  searchInput.value = ""; // Xa search khi chuyn tab
  clearSearchResults();
});

searchTab.addEventListener("click", () => {
  switchTab("search");
  searchInput.focus(); // T ng focus vo  tm kim
});

// =======================================================
//  HM LY THNG TIN USER
// =======================================================
async function fetchCurrentUserData() {
    if (!currentUserUid) return null;
    
    try {
        const userRef = doc(db, "users", currentUserUid);
        const userSnap = await getDoc(userRef);
        
        if (userSnap.exists()) {
            currentUserData = userSnap.data();
            console.log("  load user data:", currentUserData.username);
            return currentUserData;
        }
    } catch (error) {
        console.error(" Li fetch user data:", error);
    }
    return null;
}

// =======================================================
//  HM LOAD FRIENDS LIST
// =======================================================
async function loadFriendsList() {
    if (!currentUserUid) return;
    
    try {
        console.log(" ang load danh sch bn b...");
        await renderFriendsList(currentUserData);
    } catch (error) {
        console.error(" Li load friends list:", error);
    }
}

// =======================================================
//  AUTH STATE CHANGED
// =======================================================
auth.onAuthStateChanged(async (user) => {
    if (user) {
        currentUserUid = user.uid;
        console.log(" User logged in:", currentUserUid);
        
        // Ti user data trc
        await fetchCurrentUserData();
        
        // Thm chatbot vo danh sch bn b
        if (ENABLE_CHATBOT_FRIEND) {
          await addChatbotToFriends();
        } else {
          await cleanupDisabledChatbotFriend();
        }
        
        // Ti unread counts
        loadUnreadCounts();
        
        // Load danh sch bn b
        await loadFriendsList();
        
        // Load friend requests
        loadFriendRequests();
    } else {
        currentUserUid = null;
        currentUserData = {};
        
        // Clear UI
        if (friendsList) {
            friendsList.innerHTML = `
                <div class="empty-friends">
                    <div class="empty-icon"></div>
                    <div class="empty-text">${getCurrentLanguage() === 'vi' ? 'Chưa đăng nhập' : 'Not signed in'}</div>
                    <div class="empty-subtext">${getCurrentLanguage() === 'vi' ? 'Vui lòng đăng nhập để xem bạn bè' : 'Sign in to view friends'}</div>
                </div>
            `;
        }
    }
});

// =======================================================
//  THM CHATBOT VO DANH SCH BN B
// =======================================================
async function addChatbotToFriends() {
    if (!ENABLE_CHATBOT_FRIEND) return;
    if (!currentUserUid || !currentUserData) return;
    
    try {
        console.log(" Kim tra chatbot trong danh sch bn b...");
        
        const userRef = doc(db, "users", currentUserUid);
        const userSnap = await getDoc(userRef);
        
        if (userSnap.exists()) {
            const userData = userSnap.data();
            const friends = userData?.friends || [];
            
            // KIM TRA CHATBOT  C CHA
            const hasChatbot = friends.includes(CHATBOT_UID);
            
            if (!hasChatbot) {
                console.log(` ang thm ${CHATBOT_NAME} vo danh sch bn b...`);
                
                try {
                    // Cp nht Firestore
                    await updateDoc(userRef, {
                        friends: arrayUnion(CHATBOT_UID)
                    });
                    
                    console.log(`  thm ${CHATBOT_NAME} vo danh sch bn b`);
                    
                    // Cp nht currentUserData
                    currentUserData.friends = [...friends, CHATBOT_UID];
                    
                    // To tin nhn cho mng
                    setTimeout(() => {
                        createWelcomeMessage();
                    }, 1000);
                    
                } catch (updateError) {
                    console.error(" Li khi cp nht Firestore:", updateError);
                }
            } else {
                console.log(` ${CHATBOT_NAME}  c trong danh sch bn b`);
            }
        }
    } catch (error) {
        console.error(" Li kim tra chatbot:", error);
    }
}

// =======================================================
//  TO TIN NHN CHO MNG
// =======================================================
async function createWelcomeMessage() {
    if (!currentUserUid) return;
    
    try {
        console.log(" ang to tin nhn cho mng...");
        
        const chatId = [currentUserUid, CHATBOT_UID].sort().join("_");
        const messagesRef = collection(db, "chats", chatId, "messages");
        
        // Kim tra xem  c tin nhn cha
        const q = query(messagesRef, limit(1));
        const snapshot = await getDocs(q);
        
        if (snapshot.empty) {
            // To tin nhn cho mng
            await addDoc(messagesRef, {
                from: CHATBOT_UID,
                to: currentUserUid,
                content: friendText(
                  `Xin chào! Tôi là ${CHATBOT_NAME}. Tôi có thể giúp gì cho bạn hôm nay?`,
                  `Hello! I am ${CHATBOT_NAME}. How can I help you today?`
                ),
                type: "text",
                timestamp: serverTimestamp(),
                status: "sent",
                isBot: true,
                isWelcome: true
            });
            
            console.log("  to tin nhn cho mng t chatbot");
        } else {
            console.log("  c tin nhn vi chatbot");
        }
    } catch (error) {
        console.error(" Li to tin nhn cho mng:", error);
    }
}

// =======================================================
//  LNG NGHE S KIN T CHAT.JS
// =======================================================
// Khi c tin nhn mi
window.addEventListener('newMessageForFriend', (e) => {
    const { friendUid, message, unreadCount } = e.detail;
    console.log(" Nhn tin nhn mi cho bn:", friendUid, "Unread:", unreadCount);
    
    // Cp nht last message cache
    lastMessagesCache[friendUid] = {
        text: message.text,
        rawText: message.rawText || message.text,
        type: message.type,
        timestamp: new Date(message.timestamp),
        sender: message.sender
    };
    
    // Nu KHNG ang chat vi ngi ny, cp nht unread count
    if (friendUid !== currentChatFriendUid) {
        if (unreadCount !== undefined) {
            unreadCountsCache[friendUid] = unreadCount;
        } else {
            if (!unreadCountsCache[friendUid]) unreadCountsCache[friendUid] = 0;
            unreadCountsCache[friendUid]++;
        }
        
        // Lu vo localStorage
        if (currentUserUid) {
            const storageKey = `unread_${currentUserUid}`;
            localStorage.setItem(storageKey, JSON.stringify(unreadCountsCache));
        }
        
        // Cp nht UI v a ln u danh sch
        updateFriendItemUI(friendUid);
        moveFriendToTop(friendUid);
        highlightFriendItem(friendUid);
    }
});

// Khi last message c cp nht
window.addEventListener('lastMessageUpdated', (e) => {
    const { friendUid, message } = e.detail;
    lastMessagesCache[friendUid] = {
        text: message.text,
        rawText: message.rawText || message.text,
        type: message.type,
        timestamp: new Date(message.timestamp),
        sender: message.sender
    };
    updateFriendItemUI(friendUid);
});

// Khi unread count thay i
window.addEventListener('unreadCountUpdated', (e) => {
    const { friendUid, count } = e.detail;
    unreadCountsCache[friendUid] = count;
    updateFriendItemUI(friendUid);
});

// Khi reset unread count
window.addEventListener('resetUnreadForFriend', (e) => {
    const { friendUid, count } = e.detail;
    console.log(` Reset unread count cho ${friendUid}: ${count}`);
    
    unreadCountsCache[friendUid] = count || 0;
    
    // Lu vo localStorage
    if (currentUserUid) {
        const storageKey = `unread_${currentUserUid}`;
        localStorage.setItem(storageKey, JSON.stringify(unreadCountsCache));
    }
    
    // Cp nht UI
    updateFriendItemUI(friendUid);
});

// =======================================================
//  HM A BN B C TIN NHN MI LN U
// =======================================================
function moveFriendToTop(friendUid) {
    const friendItem = document.querySelector(`[data-uid='${friendUid}']`);
    if (!friendItem) return;
    
    const parent = friendItem.parentElement;
    if (parent && friendItem !== parent.firstElementChild) {
        parent.insertBefore(friendItem, parent.firstElementChild);
    }
}

// =======================================================
//  HM HIGHLIGHT BN B C TIN NHN MI
// =======================================================
function highlightFriendItem(friendUid) {
    const friendItem = document.querySelector(`[data-uid='${friendUid}']`);
    if (!friendItem) return;
    
    friendItem.style.backgroundColor = 'rgba(255, 107, 157, 0.15)';
    friendItem.style.borderLeft = '3px solid #ff6b9d';
    friendItem.style.transition = 'all 0.3s ease';
    
    setTimeout(() => {
        if (friendUid !== currentChatFriendUid) {
            friendItem.style.backgroundColor = '';
            friendItem.style.borderLeft = '';
        }
    }, 3000);
}

// =======================================================
//  HM LOAD UNREAD COUNTS KHI NG NHP
// =======================================================
function loadUnreadCounts() {
  if (!currentUserUid) return;
  
  const storageKey = `unread_${currentUserUid}`;
  
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      unreadCountsCache = JSON.parse(saved);
      console.log(" Loaded unread counts t Chat.js:", unreadCountsCache);
    } else {
      unreadCountsCache = {};
    }
  } catch (error) {
    console.error(" Li parse unread counts:", error);
    unreadCountsCache = {};
  }
}

// =======================================================
//  HM CP NHT UNREAD COUNT UI
// =======================================================
function updateUnreadCountUI(friendUid, count) {
  const friendItem = document.querySelector(`[data-uid='${friendUid}']`);
  if (!friendItem) return;
  
  unreadCountsCache[friendUid] = count;
  
  let badge = friendItem.querySelector('.unread-badge');
  
  if (count > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'unread-badge';
      friendItem.appendChild(badge);
    }
    
    if (count <= 9) {
      badge.textContent = count.toString();
    } else if (count <= 99) {
      badge.textContent = '10+';
    } else {
      badge.textContent = '99+';
    }
    
    badge.style.cssText = `
      background: linear-gradient(135deg, #ff6b9d, #ff3838);
      color: white;
      border-radius: 50%;
      min-width: 20px;
      height: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: bold;
      padding: 0 5px;
      box-shadow: 0 2px 10px rgba(255,107,157,.5);
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      animation: badgePulse 2s infinite;
      z-index: 1;
    `;
    
    badge.style.animation = 'badgePulse 0.5s ease-out 3';
    
  } else if (badge) {
    badge.remove();
  }
}

// =======================================================
//  HM CP NHT LAST MESSAGE UI
// =======================================================
function updateLastMessageUI(friendUid, message) {
  const friendItem = document.querySelector(`[data-uid='${friendUid}']`);
  if (!friendItem) return;
  
  lastMessagesCache[friendUid] = message;
  
  const lastMsgElement = friendItem.querySelector('.friend-last-msg');
  const timeElement = friendItem.querySelector('.friend-time');
  
  if (lastMsgElement) {
    let messageText = '';
    const originalText = getOriginalFriendMessageText(message);
    
    if (message.type === 'image') {
      messageText = ` ${chatPack().imageLabel}`;
    } else if (message.type === 'video') {
      messageText = ` ${chatPack().videoLabel}`;
    } else if (message.sender === currentUserUid) {
      messageText = `${chatPack().youPrefix} ${originalText}`;
    } else {
      messageText = originalText;
    }
    
    if (messageText.length > 25) {
      messageText = messageText.substring(0, 22) + '...';
    }
    
    lastMsgElement.textContent = messageText;
  }
  
  if (timeElement && message.timestamp) {
    timeElement.textContent = formatTimeForMessage(message.timestamp);
  }
}

// =======================================================
// HM UPDATE FRIEND ITEM UI
// =======================================================
function updateFriendItemUI(friendUid) {
  const friendItem = document.querySelector(`[data-uid='${friendUid}']`);
  if (!friendItem) return;
  
  const lastMsg = lastMessagesCache[friendUid];
  if (lastMsg) {
    updateLastMessageUI(friendUid, lastMsg);
  }
  
  const unreadCount = unreadCountsCache[friendUid] || 0;
  updateUnreadCountUI(friendUid, unreadCount);
}

// =======================================================
// HM RENDER FRIENDS LIST
// =======================================================
async function renderFriendsList(data) {
  console.log(" ang render danh sch bn b...");
  friendsList.innerHTML = "";
  
  if (!data || !data.friends || data.friends.length === 0) {
    friendsList.innerHTML = `
      <div class="empty-friends">
        <div class="empty-icon"></div>
        <div class="empty-text">${chatPack().friendsEmpty}</div>
        <div class="empty-subtext">${chatPack().friendsEmptySubtext}</div>
      </div>
    `;
    return;
  }

  // To danh sch friends mi vi chatbot
  let friends = [...data.friends].filter((uid) => ENABLE_CHATBOT_FRIEND || uid !== CHATBOT_UID);

  // Sp xp: c unread  last message mi  theo tn
  const sortedFriends = [...friends].sort((a, b) => {
    const unreadA = unreadCountsCache[a] || 0;
    const unreadB = unreadCountsCache[b] || 0;
    
    if (unreadA !== unreadB) {
      return unreadB - unreadA;
    }
    
    const timeA = lastMessagesCache[a]?.timestamp?.getTime() || 0;
    const timeB = lastMessagesCache[b]?.timestamp?.getTime() || 0;
    
    if (timeA !== timeB) {
      return timeB - timeA;
    }
    
    return a.localeCompare(b);
  });

  console.log(" S lng bn b cn render:", sortedFriends.length);

  // To array  x l bt ng b
  const friendPromises = sortedFriends.map(async (uid) => {
    // X L CHATBOT C BIT
    if (uid === CHATBOT_UID) {
      return createChatbotFriendItem();
    }
    
    // X L BN B THNG THNG
    try {
      const friendRef = doc(db, "users", uid);
      const friendSnap = await getDoc(friendRef);
      const friendData = friendSnap.data();
      const friendName = friendData?.username || chatPack().userFallback;
      
      return createRegularFriendItem(uid, friendName);
    } catch (error) {
      console.error(` Li load friend ${uid}:`, error);
      return createErrorFriendItem(uid);
    }
  });

  try {
    // i tt c friend items c to
    const friendItems = await Promise.all(friendPromises);
    
    // Thm tt c vo DOM
    friendItems.forEach(item => {
      if (item) {
        friendsList.appendChild(item);
      }
    });
    
    console.log(`  render ${friendItems.length} bn b`);
    
  } catch (error) {
    console.error(" Li render friends list:", error);
    friendsList.innerHTML = `
      <div class="empty-friends">
        <div class="empty-icon"></div>
        <div class="empty-text">${chatPack().loadingFriendsError}</div>
        <div class="empty-subtext">${chatPack().tryAgainLater}</div>
      </div>
    `;
  }
}

// =======================================================
//  TO CHATBOT FRIEND ITEM
// =======================================================
function createChatbotFriendItem() {
  if (!ENABLE_CHATBOT_FRIEND) return null;
  const friendItem = document.createElement("div");
  friendItem.className = "friend-item chatbot-item";
  friendItem.dataset.uid = CHATBOT_UID;
  friendItem.dataset.name = CHATBOT_NAME;
  
  // Highlight nu ang active
  if (CHATBOT_UID === currentChatFriendUid) {
    friendItem.classList.add("active");
  }

  // Phn bn tri: Avatar + Info
  const leftDiv = document.createElement("div");
  leftDiv.style.display = "flex";
  leftDiv.style.alignItems = "center";
  leftDiv.style.gap = "12px";
  leftDiv.style.flex = "1";
  leftDiv.style.overflow = "hidden";
  
  // Avatar c bit cho chatbot
  const avatarDiv = document.createElement("div");
  applyBotAvatarMarkup(avatarDiv);
  
  // Info
  const infoDiv = document.createElement("div");
  infoDiv.className = "friend-info";
  
  // Tn chatbot
  const nameDiv = document.createElement("div");
  nameDiv.className = "friend-name chatbot-name";
  nameDiv.textContent = CHATBOT_NAME;
  
  // Last message
  const lastMsgDiv = document.createElement("div");
  lastMsgDiv.className = "friend-last-msg";
  
  // Khi to last message t cache
  const lastMsg = lastMessagesCache[CHATBOT_UID];
  if (lastMsg) {
    let messageText = getOriginalFriendMessageText(lastMsg);
    
    if (messageText.length > 25) {
      messageText = messageText.substring(0, 22) + '...';
    }
    
    lastMsgDiv.textContent = messageText;
  } else {
    lastMsgDiv.textContent = getCurrentLanguage() === 'vi'
      ? 'Xin chào! Tôi có thể giúp gì cho bạn?'
      : 'Hello! How can I help you?';
    lastMsgDiv.style.color = "var(--text-secondary)";
    lastMsgDiv.style.fontStyle = "italic";
  }
  
  infoDiv.appendChild(nameDiv);
  infoDiv.appendChild(lastMsgDiv);
  leftDiv.appendChild(avatarDiv);
  leftDiv.appendChild(infoDiv);
  friendItem.appendChild(leftDiv);
  
  // Phn bn phi: Time + Menu
  const rightDiv = document.createElement("div");
  rightDiv.className = "friend-meta";
  
  // Thi gian
  const timeDiv = document.createElement("div");
  timeDiv.className = "friend-time";
  
  if (lastMsg && lastMsg.timestamp) {
    timeDiv.textContent = formatTimeForMessage(lastMsg.timestamp);
  }
  
  rightDiv.appendChild(timeDiv);
  
  // Nt menu (n i vi chatbot)
  const menuBtn = document.createElement("button");
  menuBtn.className = "menu-dots";
  menuBtn.innerHTML = "";
  menuBtn.style.display = "none"; // n menu cho chatbot
  
  rightDiv.appendChild(menuBtn);
  friendItem.appendChild(rightDiv);
  
  // S kin click chn chatbot
  friendItem.onclick = (e) => {
    if (e.target === menuBtn || menuBtn.contains(e.target)) return;
    
    // B highlight tt c
    document.querySelectorAll('.friend-item').forEach(item => {
      item.classList.remove("active");
    });
    
    // Highlight item c chn
    friendItem.classList.add("active");
    
    currentChatFriendUid = CHATBOT_UID;
    
    // Reset unread count khi m chat
    if (unreadCountsCache[CHATBOT_UID] > 0) {
      unreadCountsCache[CHATBOT_UID] = 0;
      
      // Lu vo localStorage
      if (currentUserUid) {
        const storageKey = `unread_${currentUserUid}`;
        localStorage.setItem(storageKey, JSON.stringify(unreadCountsCache));
      }
      
      // Dispatch event n Chat.js  ng b
      window.dispatchEvent(new CustomEvent('resetUnreadForFriend', {
        detail: { friendUid: CHATBOT_UID, count: 0 }
      }));
      
      // Cp nht UI
      updateUnreadCountUI(CHATBOT_UID, 0);
    }
    
    // Dispatch event n Chat.js
    const event = new CustomEvent("friendSelected", {
      detail: { 
        uid: CHATBOT_UID, 
        name: CHATBOT_NAME,
        isChatbot: true 
      }
    });
    window.dispatchEvent(event);
  };
  
  // Cp nht unread badge nu c
  const unreadCount = unreadCountsCache[CHATBOT_UID] || 0;
  if (unreadCount > 0) {
    updateUnreadCountUI(CHATBOT_UID, unreadCount);
  }
  
  return friendItem;
}

// =======================================================
//  TO REGULAR FRIEND ITEM
// =======================================================
function createRegularFriendItem(uid, friendName) {
  const friendItem = document.createElement("div");
  const isBotStyledFriend = isSkemiBotLabel(friendName);
  friendItem.className = `friend-item${isBotStyledFriend ? " chatbot-item chatbot-alias-item" : ""}`;
  friendItem.dataset.uid = uid;
  friendItem.dataset.name = friendName;
  
  // Highlight nu ang active
  if (uid === currentChatFriendUid) {
    friendItem.classList.add("active");
  }

  const isBlocked = currentUserData.blockedUsers?.includes(uid);
  
  // Phn bn tri: Avatar + Info
  const leftDiv = document.createElement("div");
  leftDiv.style.display = "flex";
  leftDiv.style.alignItems = "center";
  leftDiv.style.gap = "12px";
  leftDiv.style.flex = "1";
  leftDiv.style.overflow = "hidden";
  
  // Avatar
  const avatarDiv = document.createElement("div");
  avatarDiv.className = 'friend-avatar';
  if (isBotStyledFriend) {
    applyBotAvatarMarkup(avatarDiv);
  } else {
    avatarDiv.textContent = friendName.charAt(0).toUpperCase();
  }
  
  // Info
  const infoDiv = document.createElement("div");
  infoDiv.className = "friend-info";
  
  // Tn
  const nameDiv = document.createElement("div");
  nameDiv.className = `friend-name${isBotStyledFriend ? " chatbot-name" : ""}`;
  nameDiv.textContent = isBotStyledFriend ? CHATBOT_NAME : friendName;
  nameDiv.style.color = isBlocked ? "#888" : "inherit";
  
  // Last message
  const lastMsgDiv = document.createElement("div");
  lastMsgDiv.className = "friend-last-msg";
  
  // Khi to last message t cache
  const lastMsg = lastMessagesCache[uid];
  if (lastMsg) {
    let messageText = '';
    
    if (lastMsg.type === 'image') {
      messageText = ` ${chatPack().imageLabel}`;
    } else if (lastMsg.type === 'video') {
      messageText = ` ${chatPack().videoLabel}`;
    } else if (lastMsg.sender === currentUserUid) {
      messageText = `${chatPack().youPrefix} ${getOriginalFriendMessageText(lastMsg)}`;
    } else {
      messageText = getOriginalFriendMessageText(lastMsg);
    }
    
    if (messageText.length > 25) {
      messageText = messageText.substring(0, 22) + '...';
    }
    
    lastMsgDiv.textContent = messageText;
  } else {
    lastMsgDiv.textContent = chatPack().noMessages;
  }
  
  infoDiv.appendChild(nameDiv);
  infoDiv.appendChild(lastMsgDiv);
  leftDiv.appendChild(avatarDiv);
  leftDiv.appendChild(infoDiv);
  friendItem.appendChild(leftDiv);
  
  // Phn bn phi: Time + Menu
  const rightDiv = document.createElement("div");
  rightDiv.className = "friend-meta";
  
  // Thi gian
  const timeDiv = document.createElement("div");
  timeDiv.className = "friend-time";
  
  if (lastMsg && lastMsg.timestamp) {
    timeDiv.textContent = formatTimeForMessage(lastMsg.timestamp);
  }
  
  rightDiv.appendChild(timeDiv);
  
  // Nt menu
  const menuBtn = document.createElement("button");
  menuBtn.className = "menu-dots";
  menuBtn.innerHTML = "";
  
  menuBtn.onclick = (e) => {
    e.stopPropagation();
    showFriendContextMenu(e, friendItem, uid, friendName, isBlocked);
  };
  
  rightDiv.appendChild(menuBtn);
  friendItem.appendChild(rightDiv);
  
  // S kin click chn bn b
  friendItem.onclick = (e) => {
    if (e.target === menuBtn || menuBtn.contains(e.target)) return;
    
    // B highlight tt c
    document.querySelectorAll('.friend-item').forEach(item => {
      item.classList.remove("active");
    });
    
    // Highlight item c chn
    friendItem.classList.add("active");
    
    currentChatFriendUid = uid;
    
    // Reset unread count khi m chat
    if (unreadCountsCache[uid] > 0) {
      unreadCountsCache[uid] = 0;
      
      // Lu vo localStorage
      if (currentUserUid) {
        const storageKey = `unread_${currentUserUid}`;
        localStorage.setItem(storageKey, JSON.stringify(unreadCountsCache));
      }
      
      // Dispatch event n Chat.js  ng b
      window.dispatchEvent(new CustomEvent('resetUnreadForFriend', {
        detail: { friendUid: uid, count: 0 }
      }));
      
      // Cp nht UI
      updateUnreadCountUI(uid, 0);
    }
    
    // Dispatch event n Chat.js
    const event = new CustomEvent("friendSelected", {
      detail: { uid, name: friendName }
    });
    window.dispatchEvent(event);
  };
  
  // Cp nht unread badge nu c
  const unreadCount = unreadCountsCache[uid] || 0;
  if (unreadCount > 0) {
    updateUnreadCountUI(uid, unreadCount);
  }
  
  return friendItem;
}

// =======================================================
//  TO ERROR FRIEND ITEM (fallback)
// =======================================================
function createErrorFriendItem(uid) {
  const friendItem = document.createElement("div");
  friendItem.className = "friend-item error-item";
  friendItem.dataset.uid = uid;
  
  const leftDiv = document.createElement("div");
  leftDiv.style.display = "flex";
  leftDiv.style.alignItems = "center";
  leftDiv.style.gap = "12px";
  leftDiv.style.flex = "1";
  
  const avatarDiv = document.createElement("div");
  avatarDiv.className = "friend-avatar";
  avatarDiv.textContent = "?";
  avatarDiv.style.background = "#888";
  
  const infoDiv = document.createElement("div");
  infoDiv.className = "friend-info";
  
  const nameDiv = document.createElement("div");
  nameDiv.className = "friend-name";
  nameDiv.textContent = chatPack().notFound;
  nameDiv.style.color = "#888";
  
  const lastMsgDiv = document.createElement("div");
  lastMsgDiv.className = "friend-last-msg";
  lastMsgDiv.textContent = chatPack().couldNotLoadInfo;
  lastMsgDiv.style.color = "#888";
  
  infoDiv.appendChild(nameDiv);
  infoDiv.appendChild(lastMsgDiv);
  leftDiv.appendChild(avatarDiv);
  leftDiv.appendChild(infoDiv);
  friendItem.appendChild(leftDiv);
  
  return friendItem;
}

// =======================================================
// HM FORMAT TIME (ging Zalo/Facebook)
// =======================================================
function formatTimeForMessage(timestamp) {
  if (!timestamp) return '';
  
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  
  if (diffMins < 1) return chatPack().justNow;
  if (diffMins < 60) return relativeLabel('minutesAgo', diffMins);
  if (diffHours < 24) return relativeLabel('hoursAgo', diffHours);
  if (diffDays === 1) return chatPack().yesterday;
  if (diffDays < 7) return relativeLabel('daysAgo', diffDays);
  
  if (date.getFullYear() === now.getFullYear()) {
    return date.toLocaleDateString('vi-VN', { 
      day: '2-digit', 
      month: '2-digit' 
    });
  }
  
  return date.toLocaleDateString('vi-VN', { 
    day: '2-digit', 
    month: '2-digit',
    year: 'numeric'
  });
}

// =======================================================
// SEARCH USERS - HOT NG TRN TAB TM KIM
// =======================================================
function clearSearchResults() {
  const actualSearchResults = document.getElementById("actualSearchResults");
  actualSearchResults.innerHTML = "";
}

function renderSearchResults(users) {
  const actualSearchResults = document.getElementById("actualSearchResults");
  actualSearchResults.innerHTML = "";
  
  if (users.length === 0) {
    actualSearchResults.innerHTML = `
      <div style="text-align: center; padding: 30px 15px; color: rgba(255,255,255,0.5);">
        <i class="fas fa-search" style="font-size: 40px; margin-bottom: 15px; display: block;"></i>
        <div>${chatPack().searchNoUsers}</div>
        <div style="font-size: 12px; margin-top: 5px;">${chatPack().searchTryOther}</div>
      </div>
    `;
    return;
  }

  users.forEach(user => {
    const searchItem = document.createElement("div");
    searchItem.className = "search-item";
    searchItem.dataset.uid = user.uid;
    
    // Kim tra trng thi
    const isFriend = currentUserData?.friends?.includes(user.uid);
    const isBlocked = currentUserData?.blockedUsers?.includes(user.uid);
    const hasSentRequest = false; // Cn kim tra trong friendRequests
    
    searchItem.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
        <div class="friend-avatar" style="width: 45px; height: 45px;">
          ${(user.username || "U").charAt(0).toUpperCase()}
        </div>
        <div style="flex: 1; min-width: 0;">
          <div style="font-weight: bold; font-size: 14px;">${user.username || chatPack().userFallback}</div>
          <div style="font-size: 12px; color: rgba(255,255,255,0.6);">
            ${user.email || ""}
          </div>
        </div>
      </div>
      <button class="add-friend-btn-small" 
              data-uid="${user.uid}"
              ${isFriend ? 'disabled' : ''}>
        ${isFriend ? chatPack().alreadyFriend : 
          isBlocked ? chatPack().blocked : 
          hasSentRequest ? chatPack().sent : 
          `<i class="fas fa-user-plus"></i> ${chatPack().addFriend}`}
      </button>
    `;
    
    // S kin click chn user
    searchItem.onclick = (e) => {
      if (e.target.closest('.add-friend-btn-small')) return;
      
      // Xa highlight c
      document.querySelectorAll('.search-item').forEach(item => {
        item.style.background = "";
        item.style.borderLeft = "";
      });
      
      // Highlight item c chn
      searchItem.style.background = "rgba(255, 204, 0, 0.2)";
      searchItem.style.borderLeft = "3px solid #ffcc00";
      selectedUserToInvite = user;
    };
    
    // S kin cho nt thm bn
    const addBtn = searchItem.querySelector('.add-friend-btn-small');
    if (addBtn && !isFriend && !isBlocked && !hasSentRequest) {
      addBtn.onclick = async (e) => {
        e.stopPropagation();
        await sendFriendRequest(user.uid, user.username);
        
        // Update button state
        addBtn.innerHTML = `<i class="fas fa-clock"></i> ${chatPack().sent}`;
        addBtn.disabled = true;
      };
    }
    
    actualSearchResults.appendChild(searchItem);
  });
}

// Tm kim realtime
let searchTimeout;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  
  const keyword = searchInput.value.trim().toLowerCase();
  if (!keyword) {
    clearSearchResults();
    return;
  }
  
  searchTimeout = setTimeout(async () => {
    try {
      const usersRef = collection(db, "users");
      const snapshot = await getDocs(usersRef);
      const results = [];

      snapshot.forEach(docSnap => {
        const user = docSnap.data();
        const uid = docSnap.id;
        
        if (uid === currentUserUid || uid === CHATBOT_UID) return;
        
        const username = user.username || "";
        const email = user.email || "";
        
        if (username.toLowerCase().includes(keyword) || 
            email.toLowerCase().includes(keyword)) {
          results.push({ 
            uid: uid, 
            username: username,
            email: email,
            ...user 
          });
        }
      });

      renderSearchResults(results);
      
    } catch (error) {
      console.error(" Li tm kim:", error);
      const actualSearchResults = document.getElementById("actualSearchResults");
      actualSearchResults.innerHTML = `
        <div style="color: #ff4757; padding: 15px; text-align: center;">
          <i class="fas fa-exclamation-triangle"></i> C li xy ra khi tm kim
        </div>`;
    }
  }, 300); // Debounce 300ms
});

// Nt thm bn bn cnh  tm kim
addFriendBtn.addEventListener("click", async () => {
  if (activeTab !== "search") {
    switchTab("search");
    searchInput.focus();
    return;
  }
  
  if (selectedUserToInvite) {
    await sendFriendRequest(selectedUserToInvite.uid, selectedUserToInvite.username);
    selectedUserToInvite = null;
  } else {
    // Hin th gi  nu cha chn ngi dng
    const searchText = searchInput.value.trim();
    if (searchText) {
      // T ng tm kim
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      // Hin th thng bo
      alert(friendText("Vui lòng tìm kiếm và chọn một người dùng để thêm bạn", "Please search and select a user to add"));
    }
  }
});

// =======================================================
// HM GI LI MI KT BN
// =======================================================
async function sendFriendRequest(friendUid, friendName) {
  if (!friendUid || !currentUserUid) return;
  
  try {
    // Kim tra  gi li mi cha
    const reqId = [currentUserUid, friendUid].sort().join("_");
    const reqRef = doc(db, "friendRequests", reqId);
    const reqSnap = await getDoc(reqRef);
    
    if (reqSnap.exists()) {
      alert(friendText("Bạn đã gửi lời mời kết bạn trước đó!", "You already sent a friend request earlier!"));
      return;
    }
    
    // Kim tra  l bn cha
    if (currentUserData?.friends?.includes(friendUid)) {
      alert(friendText("Người này đã là bạn của bạn!", "This person is already your friend!"));
      return;
    }
    
    // Gi li mi
    await setDoc(reqRef, {
      from: currentUserUid,
      to: friendUid,
      fromName: currentUserData?.username || chatPack().userFallback,
      timestamp: Date.now(),
      accepted: false,
      status: "pending"
    });
    
    alert(friendText(`Đã gửi lời mời kết bạn đến ${friendName}`, `Friend request sent to ${friendName}`));
    searchInput.value = "";
    selectedUserToInvite = null;
    clearSearchResults();
    
  } catch (error) {
    console.error(" Li gi li mi:", error);
    alert(friendText("Có lỗi khi gửi lời mời kết bạn", "Failed to send the friend request"));
  }
}

// =======================================================
// LOAD FRIEND REQUESTS
// =======================================================
async function loadFriendRequests() {
  if (!currentUserUid) return;
  
  const q = query(
    collection(db, "friendRequests"),
    where("to", "==", currentUserUid),
    where("accepted", "==", false)
  );

  onSnapshot(q, async (snap) => {
    // To hoc ly container cho friend requests
    let container = document.getElementById("friendRequestsContainer");
    
    // Kim tra xem c tab khng
    const searchSection = document.querySelector('.search-section');
    if (!searchSection) return;
    
    if (!container) {
      // To container mi nu cha c
      container = document.createElement("div");
      container.id = "friendRequestsContainer";
      container.className = "friend-requests-panel";
      
      // Chn vo v tr ph hp (sau tabs nhng trc danh sch)
      if (friendsList && friendsList.parentNode) {
        friendsList.parentNode.insertBefore(container, friendsList);
      }
    }
    
    // Hin th tiu 
    container.innerHTML = `<div class="friend-requests-title">
      <i class="fas fa-user-clock"></i> ${friendText('Lời mời kết bạn', 'Friend requests')}
    </div>`;
    
    if (snap.empty) {
      container.innerHTML += `
        <div class="friend-request-empty">
          ${friendText('Không có lời mời kết bạn nào', 'No friend requests')}
        </div>
      `;
      return;
    }
    
    // To array  x l bt ng b
    const requestsPromises = [];
    snap.forEach((docSnap) => {
      const req = docSnap.data();
      
      // To promise  x l tng request
      const promise = (async () => {
        try {
          const fromRef = doc(db, "users", req.from);
          const fromSnap = await getDoc(fromRef);
          const fromData = fromSnap.data();
          const senderName = fromData?.username || req.from;
          
          return { id: docSnap.id, req, senderName };
        } catch (error) {
          console.error(" Li load user info:", error);
          return { id: docSnap.id, req, senderName: req.from };
        }
      })();
      
      requestsPromises.push(promise);
    });
    
    try {
      // i tt c requests c x l
      const requests = await Promise.all(requestsPromises);
      
      // Xa ni dung c (gi li tiu )
      const titleHtml = container.querySelector('div:first-child')?.outerHTML || '';
      container.innerHTML = titleHtml;
      
      // Hin th tng request
      requests.forEach(({ id, req, senderName }) => {
        const requestItem = document.createElement("div");
        requestItem.className = "friend-request-item";
        
        requestItem.innerHTML = `
          <div class="friend-request-content">
            <div class="friend-request-name">${senderName}</div>
            <div class="friend-request-meta">
              ${friendText('Muốn kết bạn với bạn', 'Wants to connect with you')}
            </div>
          </div>
          <div class="friend-request-actions">
            <button class="friend-request-btn decline decline-request-btn">
              <i class="fas fa-times"></i>
            </button>
            <button class="friend-request-btn accept accept-request-btn">
              <i class="fas fa-check"></i> ${friendText('Chấp nhận', 'Accept')}
            </button>
          </div>
        `;

        const acceptBtn = requestItem.querySelector('.accept-request-btn');
        const declineBtn = requestItem.querySelector('.decline-request-btn');
        
        // S kin chp nhn
        acceptBtn.onclick = async (e) => {
          e.stopPropagation();
          
          try {
            // 1. Cp nht friend request
            await updateDoc(doc(db, "friendRequests", id), {
              accepted: true,
              acceptedAt: Date.now()
            });

            // 2. Thm vo danh sch bn b ca c hai bn
            await updateDoc(doc(db, "users", currentUserUid), {
              friends: arrayUnion(req.from)
            });

            await updateDoc(doc(db, "users", req.from), {
              friends: arrayUnion(currentUserUid)
            });

            // 3. Hin th thng bo
            showFriendRequestToast(friendText(`Đã chấp nhận lời mời kết bạn từ ${senderName}`, `Accepted the friend request from ${senderName}`), 'success');
            
            // 4. Xa khi danh sch hin th
            requestItem.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => {
              if (requestItem.parentNode) {
                requestItem.remove();
              }
            }, 300);
            
          } catch (error) {
            console.error(" Li khi chp nhn li mi:", error);
            showFriendRequestToast(friendText("Có lỗi khi chấp nhận lời mời", "Failed to accept the request"), 'error');
          }
        };
        
        // S kin t chi
        declineBtn.onclick = async (e) => {
          e.stopPropagation();
          
          if (confirm(friendText(`Bạn có chắc muốn từ chối lời mời kết bạn từ ${senderName}?`, `Do you want to decline the friend request from ${senderName}?`))) {
            try {
              await updateDoc(doc(db, "friendRequests", id), {
                accepted: false,
                status: "rejected",
                rejectedAt: Date.now()
              });
              
              showFriendRequestToast(friendText(`Đã từ chối lời mời từ ${senderName}`, `Declined the request from ${senderName}`), 'info');
              
              requestItem.style.animation = 'fadeOut 0.3s ease-out';
              setTimeout(() => {
                if (requestItem.parentNode) {
                  requestItem.remove();
                }
              }, 300);
              
            } catch (error) {
              console.error(" Li khi t chi li mi:", error);
              showFriendRequestToast(friendText("Có lỗi khi từ chối lời mời", "Failed to decline the request"), 'error');
            }
          }
        };
        
        container.appendChild(requestItem);
      });
      
    } catch (error) {
      console.error(" Li khi x l friend requests:", error);
      container.innerHTML += `
        <div style="color: #ff4757; padding: 15px; text-align: center;">
          <i class="fas fa-exclamation-triangle"></i> ${friendText('Có lỗi khi tải lời mời kết bạn', 'Failed to load friend requests')}
        </div>
      `;
    }
  });
}

// =======================================================
// HM HIN TH TOAST CHO FRIEND REQUESTS
// =======================================================
function showFriendRequestToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = 'friend-request-toast';
  toast.textContent = repairFriendText(message);
  
  toast.style.cssText = `
    position: fixed;
    top: 18px;
    left: 50%;
    transform: translateX(-50%);
    background: ${type === 'success' ? 'linear-gradient(135deg, #00d4ff, #00a8cc)' : 
                type === 'error' ? 'linear-gradient(135deg, #ff4757, #ff3838)' : 
                'linear-gradient(135deg, #667eea, #764ba2)'};
    color: white;
    padding: 12px 20px;
    border-radius: 10px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    z-index: 9999;
    animation: slideIn 0.3s ease-out;
    width: max-content;
    max-width: min(520px, calc(100vw - 32px));
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.2);
    font-weight: 500;
    text-align: center;
  `;
  
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease-out forwards';
    setTimeout(() => {
      if (toast.parentNode) {
        toast.remove();
      }
    }, 300);
  }, 3000);
}

// =======================================================
// CREATE GROUP LOGIC
// =======================================================
const createGroupModal = document.getElementById("createGroupModal");
const closeGroupModal = document.getElementById("closeGroupModal");
const confirmCreateGroupBtn = document.getElementById("confirmCreateGroupBtn");
const groupNameInput = document.getElementById("groupNameInput");
const friendsSelectionList = document.getElementById("friendsSelectionList");

if (createGroupBtn) {
    createGroupBtn.addEventListener("click", () => {
        openCreateGroupModal();
    });
}

if (closeGroupModal) {
    closeGroupModal.addEventListener("click", () => {
        createGroupModal.style.display = "none";
    });
}

if (confirmCreateGroupBtn) {
    confirmCreateGroupBtn.addEventListener("click", async () => {
        await createGroup();
    });
}

function openCreateGroupModal() {
    if (!createGroupModal) return;
    createGroupModal.style.display = "flex";
    groupNameInput.value = "";
    renderFriendsSelection();
}

function renderFriendsSelection() {
    friendsSelectionList.innerHTML = "";
    
    if (!currentUserData || !currentUserData.friends) return;
    
    currentUserData.friends.forEach(async (uid) => {
        if (uid === CHATBOT_UID) return; // Don't add chatbot to groups
        
        try {
            const friendRef = doc(db, "users", uid);
            const friendSnap = await getDoc(friendRef);
            const friendData = friendSnap.data();
            const friendName = friendData?.username || chatPack().userFallback;
            
            const item = document.createElement("label");
            item.className = "friend-select-item";
            item.innerHTML = `
                <input type="checkbox" value="${uid}" class="friend-checkbox">
                <div class="friend-avatar" style="width: 30px; height: 30px; font-size: 12px; margin-right: 10px;">
                    ${friendName.charAt(0).toUpperCase()}
                </div>
                <span>${friendName}</span>
            `;
            
            friendsSelectionList.appendChild(item);
        } catch (e) {
            console.error("Error loading friend for selection", e);
        }
    });
}

async function createGroup() {
    const groupName = groupNameInput.value.trim();
    if (!groupName) {
        alert(friendText("Vui lòng nhập tên nhóm", "Please enter a group name"));
        return;
    }
    
    const checkboxes = document.querySelectorAll(".friend-checkbox:checked");
    const selectedUids = Array.from(checkboxes).map(cb => cb.value);
    
    if (selectedUids.length === 0) {
        alert(friendText("Vui lòng chọn ít nhất 1 thành viên", "Please select at least one member"));
        return;
    }
    
    // Add current user to members
    const members = [currentUserUid, ...selectedUids];
    
    try {
        // Create group in Firestore
        const groupRef = await addDoc(collection(db, "groups"), {
            name: groupName,
            members: members,
            admin: currentUserUid,
            createdAt: serverTimestamp(),
            type: "group"
        });
        
        alert(`  to nhm "${groupName}" thnh cng!`);
        createGroupModal.style.display = "none";
        
    } catch (error) {
        console.error("Error creating group:", error);
        alert("Li khi to nhm");
    }
}

// Thm animation vo CSS
document.addEventListener('DOMContentLoaded', function() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes fadeOut {
      from { opacity: 1; transform: translateX(0); }
      to { opacity: 0; transform: translateX(20px); }
    }
    
    @keyframes slideIn {
      from {
        transform: translateX(100%) translateY(-20px);
        opacity: 0;
      }
      to {
        transform: translateX(0) translateY(0);
        opacity: 1;
      }
    }
    
    @keyframes slideOut {
      from {
        transform: translateX(0) translateY(0);
        opacity: 1;
      }
      to {
        transform: translateX(100%) translateY(-20px);
        opacity: 0;
      }
    }
    
    .friend-request-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px;
      margin-bottom: 8px;
      border-radius: 12px;
      border-left: 3px solid #00d4ff;
      background: rgba(255, 255, 255, 0.06);
      transition: all 0.3s ease;
    }

    .friend-requests-panel {
      margin-top: 10px;
      padding: 15px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      border: 1px solid var(--border);
      color: var(--text);
    }

    .friend-requests-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
    }

    .friend-request-empty {
      padding: 15px;
      text-align: center;
      color: var(--text-muted);
      font-size: 13px;
    }

    .friend-request-content {
      flex: 1;
      min-width: 0;
    }

    .friend-request-name {
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
    }

    .friend-request-meta {
      margin-top: 2px;
      font-size: 12px;
      color: var(--text-secondary);
    }

    .friend-request-actions {
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }

    .friend-request-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12px;
      transition: all 0.2s ease;
    }

    .friend-request-btn.accept {
      background: linear-gradient(135deg, #00d4ff, #ff6b9d);
      border: none;
      color: #ffffff;
    }

    .friend-request-btn.decline {
      background: rgba(255, 71, 87, 0.12);
      border: 1px solid rgba(255, 71, 87, 0.35);
      color: #ff5a67;
    }

    .friend-request-btn.accept:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 18px rgba(0, 212, 255, 0.24);
    }

    .friend-request-btn.decline:hover {
      background: rgba(255, 71, 87, 0.18);
    }
    
    .friend-request-item:hover {
      background: rgba(255, 255, 255, 0.08) !important;
      transform: translateY(-2px);
    }
  `;
  document.head.appendChild(style);
});

// =======================================================
// BLOCK / UNBLOCK LOGIC
// =======================================================
async function toggleBlockUser(friendUid, isCurrentlyBlocked) {
  const userRef = doc(db, "users", currentUserUid);

  if (isCurrentlyBlocked) {
    await updateDoc(userRef, {
      blockedUsers: arrayRemove(friendUid)
    });

    alert(friendText("Đã bỏ chặn người dùng", "User unblocked"));
  } else {
    await updateDoc(userRef, {
      blockedUsers: arrayUnion(friendUid)
    });

    alert(friendText("Đã chặn người dùng", "User blocked"));
  }

  // Update UI chat instantly
  if (currentChatFriendUid === friendUid) {
    const li = document.querySelector(`[data-uid='${friendUid}']`);

    const name = li
      ? li.dataset.name
      : friendUid;

    const event = new CustomEvent("friendSelected", {
      detail: {
        uid: friendUid,
        name,
        isBlocked: !isCurrentlyBlocked
      }
    });

    window.dispatchEvent(event);
  }
}

// =======================================================
// FRIEND CONTEXT MENU
// =======================================================
function showFriendContextMenu(e, li, friendUid, friendName, isBlocked) {
  const existingMenu = document.getElementById("friendContextMenu");
  if (existingMenu) existingMenu.remove();

  const menu = document.createElement("div");
  menu.id = "friendContextMenu";
  menu.style.cssText = `
    position: absolute;
    background: rgba(25, 25, 45, 0.95);
    backdrop-filter: blur(20px);
    color: #fff;
    padding: 8px 0;
    border-radius: 10px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    z-index: 9999;
    min-width: 180px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    font-size: 14px;
  `;

  // Block / Unblock
  const blockBtn = document.createElement("div");
  blockBtn.innerHTML = isBlocked ? 
    `<i class="fas fa-user-check" style="margin-right: 8px;"></i> ${friendText('Bỏ chặn', 'Unblock')}` : 
    '<i class="fas fa-user-slash" style="margin-right: 8px;"></i> Chặn tin nhắn';
  blockBtn.style.cssText = `
    padding: 10px 15px;
    cursor: pointer;
    display: flex;
    align-items: center;
    transition: all 0.2s;
  `;
  
  blockBtn.onmouseenter = () => blockBtn.style.background = "rgba(255, 255, 255, 0.1)";
  blockBtn.onmouseleave = () => blockBtn.style.background = "transparent";
  blockBtn.onclick = async () => {
    await toggleBlockUser(friendUid, isBlocked);
    menu.remove();
  };

  menu.appendChild(blockBtn);

  // Remove friend
  const removeBtn = document.createElement("div");
  removeBtn.innerHTML = `<i class="fas fa-user-minus" style="margin-right: 8px;"></i> ${friendText('Xóa bạn bè', 'Remove friend')}`;
  removeBtn.style.cssText = `
    padding: 10px 15px;
    cursor: pointer;
    display: flex;
    align-items: center;
    transition: all 0.2s;
    color: #ff6b9d;
  `;
  
  removeBtn.onmouseenter = () => removeBtn.style.background = "rgba(255, 255, 255, 0.1)";
  removeBtn.onmouseleave = () => removeBtn.style.background = "transparent";
  removeBtn.onclick = async () => {
    if (confirm(friendText(`Bạn có chắc muốn xóa ${friendName} khỏi danh sách bạn bè?`, `Do you want to remove ${friendName} from your friend list?`))) {
      await updateDoc(doc(db, "users", currentUserUid), {
        friends: arrayRemove(friendUid)
      });

      await updateDoc(doc(db, "users", friendUid), {
        friends: arrayRemove(currentUserUid)
      });

      li.remove();
      alert(friendText(`Đã xóa ${friendName} khỏi danh sách bạn bè`, `Removed ${friendName} from your friend list`));
    }
    menu.remove();
  };

  menu.appendChild(removeBtn);

  document.body.appendChild(menu);

  // Tnh ton v tr
  const rect = e.target.getBoundingClientRect();
  menu.style.left = `${rect.right + 5}px`;
  menu.style.top = `${rect.top}px`;

  // ng menu khi click bt c u
  document.addEventListener("click", () => menu.remove(), { once: true });
}

// Khi to tab mc nh
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(() => {
    switchTab("friends");
  }, 1000);
});

// Export cc hm cn thit
export default {
  loadFriendsList,
  loadFriendRequests,
  updateFriendItemUI,
  getChatbotInfo: () => ({ uid: CHATBOT_UID, name: CHATBOT_NAME })
};


