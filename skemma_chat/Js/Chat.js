// =======================================================
// ✅ CHAT.JS - SESSION-ONLY CHATBOT (ĐÃ SỬA LỖI)
// =======================================================

import { db, auth, storage, rtdb } from "./Firebase_config.js";
import {
    collection, doc, getDoc, addDoc, serverTimestamp, updateDoc,
    query, orderBy, limit, getDocs, where, setDoc, onSnapshot,
    deleteDoc, writeBatch
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";
import {
    ref as dbRef, push, onChildAdded, onChildChanged, onChildRemoved,
    onValue, set, remove, update, get
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-database.js";
import {
    ref as storageRef, uploadBytesResumable, getDownloadURL
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-storage.js";
import {
    onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import {
    getCurrentLanguage,
    getCurrentTheme,
    THEME_ORDER,
    getPack,
    getSkemiHomeUrl,
    localizeText,
    setLocalTheme,
    setLocalLanguage,
    ensureLocalPreferencesDefaults,
    resetGuestPreferences,
    loadRemoteUserProfile,
    loadLocalUserData,
    loadAppSettings,
    applyPreferenceClasses
} from "./SharedSettings.js?v=20260624c";

const CP1252_BYTE_MAP = Object.freeze({
    '\u20AC': 0x80,
    '\u201A': 0x82,
    '\u0192': 0x83,
    '\u201E': 0x84,
    '\u2026': 0x85,
    '\u2020': 0x86,
    '\u2021': 0x87,
    '\u02C6': 0x88,
    '\u2030': 0x89,
    '\u0160': 0x8A,
    '\u2039': 0x8B,
    '\u0152': 0x8C,
    '\u017D': 0x8E,
    '\u2018': 0x91,
    '\u2019': 0x92,
    '\u201C': 0x93,
    '\u201D': 0x94,
    '\u2022': 0x95,
    '\u2013': 0x96,
    '\u2014': 0x97,
    '\u02DC': 0x98,
    '\u2122': 0x99,
    '\u0161': 0x9A,
    '\u203A': 0x9B,
    '\u0153': 0x9C,
    '\u017E': 0x9E,
    '\u0178': 0x9F
});
const SUSPICIOUS_MOJIBAKE_PAIR = /[\u00C0-\u00FF][\u0080-\u00BF\u20AC\u201A\u0192\u201E\u2026\u2020\u2021\u02C6\u2030\u0160\u2039\u0152\u017D\u2018\u2019\u201C\u201D\u2022\u2013\u2014\u02DC\u2122\u0161\u203A\u0153\u017E\u0178]/g;

function stripControlChars(value) {
    return String(value).replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, "");
}

function cp1252Byte(char) {
    const code = char.charCodeAt(0);
    if (code <= 0xFF) return code;
    return CP1252_BYTE_MAP[char] ?? 0x3F;
}

function mojibakeScore(input) {
    if (typeof input !== "string") return Number.POSITIVE_INFINITY;
    const text = stripControlChars(input);
    return (text.match(SUSPICIOUS_MOJIBAKE_PAIR) || []).length + (text.match(/\uFFFD/g) || []).length;
}

function decodeMojibakeCandidate(value) {
    return new TextDecoder("utf-8", { fatal: false }).decode(
        Uint8Array.from(Array.from(value, cp1252Byte))
    );
}

function fixMojibakeText(value) {
    if (typeof value !== "string" || !value) return value;
    if (!/[ÃÂâðŸ�]/.test(value)) {
        return value.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, "");
    }

    try {
        const bytes = Uint8Array.from([...value].map((ch) => ch.charCodeAt(0) & 0xff));
        const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
        return decoded.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, "");
    } catch (_) {
        return value.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, "");
    }
}

function sanitizeConsoleArgs(args) {
    return args.map((arg) => {
        if (typeof arg === "string") return fixMojibakeText(arg);
        if (Array.isArray(arg)) return arg.map((v) => (typeof v === "string" ? fixMojibakeText(v) : v));
        if (arg && typeof arg === "object") {
            try {
                const clone = structuredClone(arg);
                Object.keys(clone).forEach((k) => {
                    if (typeof clone[k] === "string") clone[k] = fixMojibakeText(clone[k]);
                });
                return clone;
            } catch (_) {
                return arg;
            }
        }
        return arg;
    });
}

const __nativeConsole = {
    log: console.log.bind(console),
    warn: console.warn.bind(console),
    error: console.error.bind(console)
};

console.log = (...args) => __nativeConsole.log(...sanitizeConsoleArgs(args));
console.warn = (...args) => __nativeConsole.warn(...sanitizeConsoleArgs(args));
console.error = (...args) => __nativeConsole.error(...sanitizeConsoleArgs(args));

// --- Socket.IO Client Setup ---
const LOCAL_HTTP_PROTOCOL = window.location.protocol === 'https:' ? 'https' : 'http';
const LOCAL_HOSTNAME = window.location.hostname || '127.0.0.1';
const SAME_ORIGIN_API = `${window.location.origin.replace(/\/$/, '')}/api`;
const SOCKET_URL = window.__SKEMMA_SOCKET_ORIGIN__
    || (window.location.port === '8001'
        ? window.location.origin
        : `${LOCAL_HTTP_PROTOCOL}://${LOCAL_HOSTNAME}:8001`);
const AI_URL = `${SOCKET_URL.replace(/\/$/, '')}/api`;
const API_BASE_CANDIDATES = Array.from(new Set(
    [
        SAME_ORIGIN_API,
        ...(Array.isArray(window.__SKEMMA_AI_BASE_CANDIDATES__) ? window.__SKEMMA_AI_BASE_CANDIDATES__ : []),
        AI_URL,
        `${LOCAL_HTTP_PROTOCOL}://${LOCAL_HOSTNAME}:8010`,
        'http://127.0.0.1:8010',
        'http://localhost:8010',
        'http://127.0.0.1:8010/api'
    ].filter(Boolean).map((value) => String(value).replace(/\/$/, ''))
));
let API_BASE_URL = API_BASE_CANDIDATES[0];
const SOCKET_BASE_URL = SOCKET_URL;
const SOCKET_SERVER_ENABLED = window.location.port === '8001' || window.__SKEMMA_ENABLE_SOCKET__ === true;
const FINAL_ONLY_CHAT_MODE = true;
const STREAM_STATUS_UI_ENABLED = false;
const RESEARCH_PLAN_UI_ENABLED = false;
const HIDDEN_REASONING_SECTION_LABELS = Object.freeze([
    'REASONING'
]);
let socket = null;
let socketProbePromise = null;
let aiUnavailableToastShown = false;
const CHAT_BOOT_KEY = window.__SKEMMA_CHAT_BOOT_KEY__ || 'skemma_chat_bootstrap_ready_v1';
const SITE_INTERNAL_NAV_KEY = 'skemi_internal_navigation_v1';
const CHAT_SESSION_PRESERVE_KEY = 'skemma_preserve_chat_session_v1';
let appSettings = loadAppSettings();

function refreshAppSettings() {
    appSettings = loadAppSettings();
    applyPreferenceClasses(document.body, appSettings);
    const limitNotification = document.getElementById('limitNotification');
    if (limitNotification && !isSettingEnabled('quota_warn', true)) {
        limitNotification.classList.remove('visible');
    }
    return appSettings;
}

function isSettingEnabled(key, fallback = true) {
    return (appSettings?.[key] ?? fallback) !== false;
}

async function probeSocketServer() {
    if (!SOCKET_SERVER_ENABLED) {
        return false;
    }
    if (socketProbePromise) return socketProbePromise;

    socketProbePromise = (async () => {
        try {
            const response = await fetch(`${SOCKET_BASE_URL}/health?_t=${Date.now()}`, {
                method: 'GET',
                mode: 'cors',
                cache: 'no-store'
            });
            return response.ok;
        } catch {
            return false;
        }
    })();

    try {
        return await socketProbePromise;
    } finally {
        socketProbePromise = null;
    }
}

function getEffectiveAgeGroup() {
    if (!isSettingEnabled('ai_personalize', true)) return 'middle';
    const profile = loadLocalUserData();
    return profile?.age_group || 'middle';
}

function shouldSkipInitialLoadingOverlay() {
    refreshAppSettings();
    return window.__SKEMMA_SKIP_LOADING_OVERLAY__ === true || !isSettingEnabled('startup_tips', true);
}

function markChatBootReady() {
    try {
        sessionStorage.setItem(CHAT_BOOT_KEY, '1');
    } catch {}
    window.__SKEMMA_SKIP_LOADING_OVERLAY__ = true;
    document.documentElement.dataset.skemmaChatSkipLoading = '1';
}

window.addEventListener('storage', (event) => {
    if (event.key === 'skemi_user_data') {
        refreshAppSettings();
    }
});
window.addEventListener('skemiSettingsChanged', refreshAppSettings);
document.addEventListener('click', (event) => {
    const link = event.target.closest?.('a[href]');
    if (!link || event.defaultPrevented) return;
    if (link.target && link.target !== '_self') return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    try {
        const targetUrl = new URL(link.href, window.location.href);
        const sameOrigin = targetUrl.origin === window.location.origin;
        const isChatPage = /\/(skemma\/)?Chat\.html$/i.test(targetUrl.pathname);
        if (sameOrigin) {
            sessionStorage.setItem(SITE_INTERNAL_NAV_KEY, '1');
            if (!isChatPage && isSettingEnabled('ephemeral_chat', true)) {
                sessionStorage.setItem(CHAT_SESSION_PRESERVE_KEY, '1');
            }
        }
    } catch {}
}, true);
try {
    sessionStorage.removeItem(CHAT_SESSION_PRESERVE_KEY);
} catch {}

console.log("API Configuration:");
console.log("  Window origin:", window.location.origin);
console.log("  Window protocol:", window.location.protocol);
console.log("  AI_URL:", AI_URL);
console.log("  Socket URL:", SOCKET_URL);
console.log("  API candidates:", API_BASE_CANDIDATES);

// DOM Elements
const CHATBOT_UID = "CHATBOT_SKEMI";
const CHATBOT_NAME = "Skemi AI";
const CHATBOT_ENABLED = true;

function isDisabledChatbotUid(uid) {
    return !CHATBOT_ENABLED && uid === CHATBOT_UID;
}

function cleanupDisabledChatbotState() {
    if (CHATBOT_ENABLED) return;

    delete lastMessages[CHATBOT_UID];
    delete unreadCounts[CHATBOT_UID];
    delete onlinePresence[CHATBOT_UID];

    if (selectedFriendUid === CHATBOT_UID) {
        selectedFriendUid = null;
        selectedFriendName = null;
    }

    try {
        document.querySelectorAll(`[data-uid='${CHATBOT_UID}']`).forEach((node) => node.remove());
    } catch {}

    if (currentUserUid) {
        try {
            const unreadKey = `unread_${currentUserUid}`;
            const parsed = JSON.parse(localStorage.getItem(unreadKey) || '{}');
            if (parsed && typeof parsed === 'object' && CHATBOT_UID in parsed) {
                delete parsed[CHATBOT_UID];
                localStorage.setItem(unreadKey, JSON.stringify(parsed));
            }
        } catch {}

        try {
            sessionStorage.removeItem(`chatbot_session_${currentUserUid}`);
        } catch {}
    }
}
const messagesDiv = document.getElementById("messages");
const msgInput = document.getElementById("msg");
const chatHeader = document.getElementById("chatHeader");
const friendNameDisplay = document.getElementById("friendNameDisplay");
const friendStatusDisplay = document.getElementById("friendStatus");
let emojiBtn = document.getElementById("emojiBtn");
let attachBtn = document.getElementById("attachBtn");
let fileInput = document.getElementById("fileInput");
let attachmentPreview = document.getElementById("attachmentPreview");
let attachmentThumb = document.getElementById("attachmentThumb");
let attachmentName = document.getElementById("attachmentName");
let attachmentSize = document.getElementById("attachmentSize");
let removeAttachmentBtn = document.getElementById("removeAttachmentBtn");
const themeToggle = document.getElementById("themeToggle");
const chatInputArea = document.querySelector(".input-area");
const welcomeState = document.getElementById("welcomeState");
const emptyChatState = document.getElementById("emptyChatState");
const typingIndicator = document.getElementById("typingIndicator");
const sidebarToggle = document.getElementById("sidebarToggle");
const friendsSidebar = document.getElementById("friendsSidebar");
const jumpToLatestBtn = document.getElementById("jumpToLatestBtn");

const AUTO_SCROLL_THRESHOLD_PX = 120;
let shouldAutoScroll = true;
let newContentWhilePaused = false;
let scrollControllerInitialized = false;
let suppressAutoScrollTracking = false;

function isNearBottom(threshold = AUTO_SCROLL_THRESHOLD_PX) {
    if (!messagesDiv) return true;
    const distanceFromBottom = messagesDiv.scrollHeight - messagesDiv.scrollTop - messagesDiv.clientHeight;
    return distanceFromBottom <= threshold;
}

function updateJumpToLatestButton() {
    if (!jumpToLatestBtn) return;
    const visible = !shouldAutoScroll && newContentWhilePaused;
    jumpToLatestBtn.classList.toggle('visible', visible);
    jumpToLatestBtn.setAttribute('aria-hidden', visible ? 'false' : 'true');
}

function pauseAutoScrollOnUserScroll() {
    if (!messagesDiv || suppressAutoScrollTracking) return;
    if (isNearBottom()) {
        shouldAutoScroll = true;
        newContentWhilePaused = false;
    } else {
        shouldAutoScroll = false;
    }
    updateJumpToLatestButton();
}

function scrollToBottomIfAllowed(force = false, behavior = 'auto') {
    if (!messagesDiv) return;
    const canAutoScroll = force || shouldAutoScroll || isNearBottom();
    if (!canAutoScroll) {
        newContentWhilePaused = true;
        updateJumpToLatestButton();
        return;
    }

    suppressAutoScrollTracking = true;
    if (force) {
        shouldAutoScroll = true;
    }
    newContentWhilePaused = false;
    if (typeof messagesDiv.scrollTo === 'function') {
        messagesDiv.scrollTo({ top: messagesDiv.scrollHeight, behavior });
    } else {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    updateJumpToLatestButton();
    requestAnimationFrame(() => {
        suppressAutoScrollTracking = false;
    });
}

function initMessageScrollController() {
    if (!messagesDiv || scrollControllerInitialized) return;
    scrollControllerInitialized = true;
    messagesDiv.addEventListener('scroll', pauseAutoScrollOnUserScroll, { passive: true });
    if (jumpToLatestBtn) {
        jumpToLatestBtn.addEventListener('click', () => {
            scrollToBottomIfAllowed(true, 'smooth');
        });
    }
    updateJumpToLatestButton();
}

// Current chat
let currentUserUid = null;
let currentUserName = "User Name";
let selectedFriendUid = null;
let selectedFriendName = null;
let convId = null;
let messagesRef = null;
let isCurrentUserBlockedByFriend = false;

// Call elements
let muteBtn, videoToggleBtn, incomingCallCard, callArea, callTimer;
let declineCallBtn, acceptCallBtn, localVideo, remoteVideo, endCallBtn;
let voiceCallBtn, videoCallBtn, callAnimationContainer, headerAudioBtn;
let switchBtn, speakerBtn, backBtn, localAvatar, remoteAvatar;
let sendBtn = null;
let voiceBtn = null;

// Storage
let unreadCounts = {};
let lastMessages = {};
let typingTimeout = null;
let lastTypingTime = 0;
let activeMessagesUnsubscribe = null;
let selectedFriendStatusTimer = null;
let typingStatusTimer = null;
const onlinePresence = {};

// AudioContext
let audioContext = null;
let audioContextInitialized = false;

// =======================================================
// ✅ BIẾN THEO DÕI TIN NHẮN ĐÃ XỬ LÝ
// =======================================================
const processedMessageIds = new Set();




// Streaming & Control
let isStreamingActive = false;
let botStreamingPaused = false;
let currentStreamController = null;
let chatbotSession = {
    messages: [],
    sessionId: null,
    lastUpdated: Date.now(),
    isActive: false
};

let isBotTyping = false;
let botTypingIndicator = null;
let botTypingTimeout = null;
let currentBotMessageElement = null;
let botResponseQueue = [];
let botStreamingContent = "";
let speechRecognition = null;
let speechRecognitionSupported = false;
let isVoiceRecognitionActive = false;
let voiceRecognitionManualStop = false;
let voiceInputAnchorText = "";
let suppressVoiceRecognitionResults = false;
let currentStreamingText = "";
let streamingMessageId = null;
// Force-search flag (set by search button) - one-time toggle
let forceSearchFlag = false;
// Deep research flag - one-time toggle for comprehensive search
let deepResearchFlag = false;
let liveSearchPreviewSources = [];
let fileAnalysisMode = 'assistant';
const FILE_ANALYSIS_MODE_ORDER = ['assistant', 'structured', 'concise'];
const MAX_PROMPT_WORDS = 500; // Proxy for tokens
let pendingAttachment = null;
let pendingAttachmentUrl = null;
const MAX_FILE_BYTES_CLIENT = 50 * 1024 * 1024; // 50MB

function chatPack() {
    const current = repairMojibake(getPack(getCurrentLanguage()).chat || {});
    const fallback = repairMojibake(getPack('en').chat || {});
    const merged = { ...fallback, ...current };
    Object.keys(merged).forEach((key) => {
        const MOJIBAKE = /[�]|Ã[-¿]|Â[-¿]|áº|á»|â€|âœ|ðŸ/;
        if (typeof merged[key] === 'string' && MOJIBAKE.test(merged[key])) {
            merged[key] = typeof fallback[key] === 'string' ? fallback[key] : repairMojibake(merged[key]);
        }
    });
    return merged;
}

function settingsPack() {
    const current = repairMojibake(getPack(getCurrentLanguage()).settings || {});
    const fallback = repairMojibake(getPack('en').settings || {});
    const merged = { ...fallback, ...current };
    Object.keys(merged).forEach((key) => {
        const MOJIBAKE = /[�]|Ã[-¿]|Â[-¿]|áº|á»|â€|âœ|ðŸ/;
        if (typeof merged[key] === 'string' && MOJIBAKE.test(merged[key])) {
            merged[key] = typeof fallback[key] === 'string' ? fallback[key] : repairMojibake(merged[key]);
        }
    });
    return merged;
}

function chatText(key, params = {}) {
    const pack = chatPack();
    const fallback = (getPack('en').chat || {})[key];
    let value = pack[key];
    if (typeof value !== 'string') value = typeof fallback === 'string' ? fallback : '';
    Object.entries(params).forEach(([paramKey, paramValue]) => {
        value = value.replace(`{${paramKey}}`, String(paramValue));
    });
    value = repairMojibake(value);
    if (/[\uFFFDÃÂáºá»ðŸâœâ€]/.test(value) && typeof fallback === 'string') {
        let cleanFallback = fallback;
        Object.entries(params).forEach(([paramKey, paramValue]) => {
            cleanFallback = cleanFallback.replace(`{${paramKey}}`, String(paramValue));
        });
        return repairMojibake(cleanFallback);
    }
    return value;
}

function uiText(vi, en) {
    return localizeText(vi, en, getCurrentLanguage());
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

function getOriginalMessageText(message) {
    return repairMojibake(message?.rawText ?? message?.text ?? message?.content ?? "");
}

function renderPlainTextContent(text) {
    const rawText = repairMojibake(text || "");
    return `<span class="plain-text-content">${escapeHtml(rawText).replace(/\n/g, '<br>')}</span>`;
}

function sanitizeRenderedHtml(html) {
    const dirtyHtml = repairMojibake(String(html || ""));
    if (window.DOMPurify && typeof window.DOMPurify.sanitize === 'function') {
        return window.DOMPurify.sanitize(dirtyHtml);
    }
    return dirtyHtml.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '');
}

function normalizeHiddenReasoningLabel(line = '') {
    return String(line || '')
        .toUpperCase()
        .replace(/[^A-Z]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function isHiddenReasoningHeading(line = '') {
    const normalized = normalizeHiddenReasoningLabel(line);
    if (!normalized || normalized.length > 80) return false;
    return HIDDEN_REASONING_SECTION_LABELS.some((label) => normalized === label || normalized.endsWith(label));
}

function stripHiddenReasoningSections(text) {
    const rawText = repairMojibake(String(text || ''));
    if (!rawText) return '';

    const lines = rawText.split(/\r?\n/);
    const cleaned = [];
    let skipping = false;

    for (const line of lines) {
        const trimmed = line.trim();

        if (isHiddenReasoningHeading(trimmed)) {
            skipping = true;
            continue;
        }

        if (skipping) {
            if (!trimmed) {
                skipping = false;
            }
            continue;
        }

        cleaned.push(line);
    }

    return cleaned.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function renderBotMarkdown(text) {
    const rawText = stripHiddenReasoningSections(text || "");
    if (!rawText) return '';

    let rendered = '';
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
        try {
            rendered = marked.parse(rawText, {
                gfm: true,
                breaks: false,
                headerIds: false,
                mangle: false
            });
        } catch (error) {
            console.warn('Markdown render fallback:', error);
        }
    }

    if (!rendered) {
        rendered = formatMessageContent(rawText);
    }

    return `<div class="bot-markdown">${sanitizeRenderedHtml(rendered)}</div>`;
}

function getChatbotTimeoutMessage() {
    return getCurrentLanguage() === 'vi'
        ? 'Skemi đang phản hồi chậm hơn bình thường. Vui lòng thử lại sau ít phút hoặc gửi câu hỏi ngắn hơn.'
        : 'Skemi is taking longer than usual to respond. Please try again in a moment or send a shorter question.';
}

function getChatbotUnavailableMessage(reason = null) {
    if (typeof reason === 'number') {
        return getCurrentLanguage() === 'vi'
            ? `Mình chưa thể hoàn tất phản hồi vì kết nối tới dịch vụ AI đang tạm thời gián đoạn (HTTP ${reason}). Bạn hãy thử lại sau ít phút hoặc gửi lại câu hỏi ngắn hơn.`
            : `I could not finish the reply because the AI service is temporarily unavailable (HTTP ${reason}). Please try again in a moment or resend a shorter question.`;
    }
    return getCurrentLanguage() === 'vi'
        ? 'Mình chưa thể hoàn tất phản hồi vì kết nối tới dịch vụ AI đang tạm thời gián đoạn. Bạn hãy thử lại sau ít phút hoặc gửi lại câu hỏi ngắn hơn.'
        : 'I could not finish the reply because the AI service is temporarily unavailable. Please try again in a moment or resend a shorter question.';
}

function analysisModeLabels() {
    const pack = chatPack();
    return {
        assistant: pack.analysisAssistant || 'Assistant',
        structured: pack.analysisStructured || 'Structured',
        concise: pack.analysisConcise || 'Concise'
    };
}

function legacyRepairMojibake(value) {
    if (Array.isArray(value)) {
        return value.map((item) => legacyRepairMojibake(item));
    }
    if (value && typeof value === 'object') {
        return Object.fromEntries(
            Object.entries(value).map(([k, v]) => [k, legacyRepairMojibake(v)])
        );
    }
    if (typeof value !== 'string') return value;
    if (!/[ÃÂÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßáºá»ðŸâœ]/.test(value)) return value;

    let best = value;
    let bestScore = Number.POSITIVE_INFINITY;
    const badScore = (input) => {
        if (typeof input !== 'string') return Number.POSITIVE_INFINITY;
        const markers = ['Ã', 'Â', 'áº', 'á»', 'ðŸ', 'âœ', 'â€', '\uFFFD'];
        return markers.reduce((sum, marker) => sum + (input.split(marker).length - 1), 0);
    };

    const candidates = [value];
    try {
        candidates.push(new TextDecoder('utf-8', { fatal: false }).decode(
            Uint8Array.from(value.split('').map((char) => char.charCodeAt(0) & 0xff))
        ));
    } catch {}
    try {
        candidates.push(decodeURIComponent(escape(value)));
    } catch {}
    try {
        const fixed = value
            .split('')
            .map((char) => String.fromCharCode(char.charCodeAt(0) & 0xff))
            .join('');
        candidates.push(decodeURIComponent(escape(fixed)));
    } catch {}

    candidates.forEach((candidate) => {
        const score = badScore(candidate);
        if (score < bestScore && candidate) {
            best = candidate;
            bestScore = score;
        }
    });

    return best;
}

function repairMojibake(value) {
    if (Array.isArray(value)) {
        return value.map((item) => repairMojibake(item));
    }
    if (value && typeof value === 'object') {
        return Object.fromEntries(
            Object.entries(value).map(([k, v]) => [k, repairMojibake(v)])
        );
    }
    if (typeof value !== 'string') return value;

    const cleanValue = stripControlChars(value);
    const originalScore = mojibakeScore(cleanValue);
    if (originalScore === 0) return cleanValue;

    let best = cleanValue;
    let bestScore = originalScore;
    const candidates = [cleanValue];
    try {
        candidates.push(decodeMojibakeCandidate(cleanValue));
    } catch {}
    try {
        candidates.push(decodeURIComponent(escape(cleanValue)));
    } catch {}
    try {
        const fixed = Array.from(cleanValue, (char) => String.fromCharCode(cp1252Byte(char))).join('');
        candidates.push(decodeURIComponent(escape(fixed)));
    } catch {}

    candidates.forEach((candidate) => {
        const cleanedCandidate = stripControlChars(candidate);
        const score = mojibakeScore(cleanedCandidate);
        if (score < bestScore && cleanedCandidate) {
            best = cleanedCandidate;
            bestScore = score;
        }
    });

    return best;
}

const _rawConsole = {
    log: console.log.bind(console),
    info: console.info.bind(console),
    warn: console.warn.bind(console),
    error: console.error.bind(console)
};

function sanitizeConsoleArg(arg) {
    if (typeof arg !== 'string') return arg;
    return repairMojibake(arg).replace(/\uFFFD/g, '?');
}

console.log = (...args) => _rawConsole.log(...args.map(sanitizeConsoleArg));
console.info = (...args) => _rawConsole.info(...args.map(sanitizeConsoleArg));
console.warn = (...args) => _rawConsole.warn(...args.map(sanitizeConsoleArg));
console.error = (...args) => _rawConsole.error(...args.map(sanitizeConsoleArg));

function repairDomText(root = document.body) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) {
        textNodes.push(walker.currentNode);
    }
    textNodes.forEach((node) => {
        const fixed = repairMojibake(node.nodeValue);
        if (fixed !== node.nodeValue) node.nodeValue = fixed;
    });

    const attrTargets = [];
    if (root.nodeType === Node.ELEMENT_NODE) {
        attrTargets.push(root);
    }
    attrTargets.push(...root.querySelectorAll('[title],[placeholder],[aria-label]'));
    attrTargets.forEach((el) => {
        if (el.hasAttribute('title')) {
            const currentTitle = el.getAttribute('title');
            const fixedTitle = repairMojibake(currentTitle);
            if (fixedTitle && fixedTitle !== currentTitle) el.setAttribute('title', fixedTitle);
        }
        if (el.hasAttribute('placeholder')) {
            const currentPlaceholder = el.getAttribute('placeholder');
            const fixedPlaceholder = repairMojibake(currentPlaceholder);
            if (fixedPlaceholder && fixedPlaceholder !== currentPlaceholder) el.setAttribute('placeholder', fixedPlaceholder);
        }
        if (el.hasAttribute('aria-label')) {
            const currentAriaLabel = el.getAttribute('aria-label');
            const fixedAriaLabel = repairMojibake(currentAriaLabel);
            if (fixedAriaLabel && fixedAriaLabel !== currentAriaLabel) el.setAttribute('aria-label', fixedAriaLabel);
        }
    });
}

function startMojibakeObserver() {
    if (!document.body || document.body.dataset.mojibakeObserver === '1') return;
    document.body.dataset.mojibakeObserver = '1';
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.type === 'characterData') {
                const textNode = mutation.target;
                const fixed = repairMojibake(textNode.nodeValue);
                if (fixed !== textNode.nodeValue) textNode.nodeValue = fixed;
                return;
            }
            if (mutation.type === 'attributes') {
                const element = mutation.target;
                const attributeName = mutation.attributeName;
                if (!element || !attributeName || !element.hasAttribute?.(attributeName)) return;
                const currentValue = element.getAttribute(attributeName);
                const fixedValue = repairMojibake(currentValue);
                if (fixedValue && fixedValue !== currentValue) element.setAttribute(attributeName, fixedValue);
                return;
            }
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === Node.TEXT_NODE) {
                    const fixed = repairMojibake(node.nodeValue);
                    if (fixed !== node.nodeValue) node.nodeValue = fixed;
                    return;
                }
                if (node.nodeType === Node.ELEMENT_NODE) {
                    repairDomText(node);
                }
            });
        });
    });
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['placeholder', 'title', 'aria-label']
    });
}

function applyThemePreference(theme = getCurrentTheme()) {
    document.body.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    if (themeToggle) {
        const themeIcon = themeToggle.querySelector('i');
        if (themeIcon) {
            themeIcon.className = 'fas fa-circle-half-stroke';
        }
    }
}

function applyChatLanguage() {
    const pack = chatPack();
    const common = getPack(getCurrentLanguage()).common;
    const friendSearchInput = document.getElementById('friendSearchInput');
    const friendStatus = document.getElementById('friendStatus');
    const msgBox = document.getElementById('msg');
    const loadingTitle = document.querySelector('.loading-text');
    const loadingTipEl = document.getElementById('loadingTip');
    const typingText = document.querySelector('.typing-text');
    const themeTitle = document.getElementById('themeToggle');
    const settingsLink = document.getElementById('settingsLink');
    const sidebarToggleBtn = document.getElementById('sidebarToggle');
    const loadingErrorTitle = document.getElementById('errorTitle');
    const loadingErrorMessage = document.getElementById('errorMessage');
    const retryButton = document.getElementById('retryButton');
    const continueButton = document.getElementById('continueButton');
    const networkStatusTextEl = document.getElementById('networkStatusText');
    const timeoutWarning = document.getElementById('timeoutWarning');
    const timeoutStrong = timeoutWarning?.querySelector('strong');
    const timeoutSmall = timeoutWarning?.querySelector('small');
    const friendsHeading = document.querySelector('.search-section h3');
    const backToSkemiLink = document.getElementById('backToSkemiLink');
    const backToSkemiLabel = document.querySelector('#backToSkemiLink span');
    const welcomeTitle = document.querySelector('.welcome-title');
    const welcomeSubtitle = document.querySelector('.welcome-subtitle');
    const featureStrong = document.querySelectorAll('.feature-text strong');
    const featureSmall = document.querySelectorAll('.feature-text small');
    const friendGreeting = document.getElementById('friendGreeting');
    const emptyChatSubtext = document.querySelector('#emptyChatState .empty-subtext');
    const greetingButtons = document.querySelectorAll('.greeting-btn');
    const removeAttachmentBtnEl = document.getElementById('removeAttachmentBtn');
    const deepResearchBtnEl = document.getElementById('deepResearchBtn');
    const sendBtnEl = document.getElementById('sendBtn');
    const stopBtnEl = document.getElementById('stopBtn');
    const voiceBtnEl = document.getElementById('voiceBtn');
    const researchTitle = document.querySelector('.research-header h3');
    const editResearchBtn = document.getElementById('editResearchBtn');
    const startResearchBtn = document.getElementById('startResearchBtn');
    const sourcesTitle = document.querySelector('.sources-header h3');
    const jumpToLatestLabelEl = jumpToLatestBtn?.querySelector('.jump-to-latest-label');

    document.documentElement.lang = getCurrentLanguage();
    if (friendSearchInput) friendSearchInput.placeholder = pack.searchFriends;
    if (friendNameDisplay && !selectedFriendUid) friendNameDisplay.textContent = pack.chooseFriend;
    if (friendStatus && !selectedFriendUid) friendStatus.textContent = pack.offline;
    if (msgBox && !isBotTyping) msgBox.placeholder = pack.placeholder;
    if (loadingTitle) loadingTitle.textContent = pack.loading;
    if (networkStatusTextEl && (!networkStatusTextEl.textContent || /ki|mạng|Checking|Ká»/i.test(networkStatusTextEl.textContent))) {
        networkStatusTextEl.textContent = pack.checkingNetwork;
    }
    if (loadingTipEl) loadingTipEl.textContent = pack.networkTip;
    if (typingText) typingText.textContent = pack.typing;
    if (voiceCallBtn) voiceCallBtn.title = pack.voiceCall;
    if (videoCallBtn) videoCallBtn.title = pack.videoCall;
    if (themeTitle) themeTitle.title = settingsPack().theme;
    if (settingsLink) settingsLink.title = settingsPack().pageTitle;
    if (sidebarToggleBtn) sidebarToggleBtn.title = pack.friends;
    if (loadingErrorTitle) loadingErrorTitle.textContent = pack.loadingErrorTitle;
    if (loadingErrorMessage) loadingErrorMessage.textContent = pack.loadingErrorMessage;
    if (retryButton) retryButton.innerHTML = `<i class="fas fa-redo"></i> ${pack.retry}`;
    if (continueButton) continueButton.innerHTML = `<i class="fas fa-forward"></i> ${pack.continue}`;
    if (timeoutStrong) timeoutStrong.textContent = pack.timeoutTitle;
    if (timeoutSmall) timeoutSmall.textContent = pack.timeoutSubtitle;
    if (friendsHeading) friendsHeading.innerHTML = `<i class="fas fa-user-friends"></i> ${pack.friends}`;
    if (backToSkemiLink) {
        backToSkemiLink.href = getSkemiHomeUrl();
        backToSkemiLink.title = common.backToSkemi || common.openSkemi;
    }
    if (backToSkemiLabel) backToSkemiLabel.textContent = common.backToSkemi || common.openSkemi;
    if (welcomeTitle) welcomeTitle.textContent = pack.welcomeTitle;
    if (welcomeSubtitle) welcomeSubtitle.textContent = pack.welcomeSubtitle;
    if (featureStrong[0]) featureStrong[0].textContent = pack.featureThemeTitle;
    if (featureStrong[1]) featureStrong[1].textContent = pack.featureFriendsTitle;
    if (featureStrong[2]) featureStrong[2].textContent = pack.featureEmojiTitle;
    if (featureStrong[3]) featureStrong[3].textContent = pack.featureAttachTitle;
    if (featureStrong[4]) featureStrong[4].textContent = pack.featureVoiceTitle;
    if (featureStrong[5]) featureStrong[5].textContent = pack.featureCallTitle;
    if (featureSmall[0]) featureSmall[0].textContent = pack.featureThemeHint;
    if (featureSmall[1]) featureSmall[1].textContent = pack.featureFriendsHint;
    if (featureSmall[2]) featureSmall[2].textContent = pack.featureEmojiHint;
    if (featureSmall[3]) featureSmall[3].textContent = pack.featureAttachHint;
    if (featureSmall[4]) featureSmall[4].textContent = pack.featureVoiceHint;
    if (featureSmall[5]) featureSmall[5].textContent = pack.featureCallHint;
    if (friendGreeting && !selectedFriendUid) friendGreeting.innerHTML = pack.noMessagesWith.replace('{name}', '<span id="friendNameGreeting"></span>');
    if (emptyChatSubtext) emptyChatSubtext.textContent = pack.noMessagesPrompt;
    if (greetingButtons[0]) {
        greetingButtons[0].dataset.text = pack.greetingHelloText;
        greetingButtons[0].querySelector('small').textContent = pack.greetingHello;
    }
    if (greetingButtons[1]) {
        greetingButtons[1].dataset.text = pack.greetingMeetText;
        greetingButtons[1].querySelector('small').textContent = pack.greetingMeet;
    }
    if (greetingButtons[2]) {
        greetingButtons[2].dataset.text = pack.greetingCheckinText;
        greetingButtons[2].querySelector('small').textContent = pack.greetingCheckin;
    }
    if (greetingButtons[3]) {
        greetingButtons[3].dataset.text = pack.greetingTalkText;
        greetingButtons[3].querySelector('small').textContent = pack.greetingTalk;
    }
    if (removeAttachmentBtnEl) removeAttachmentBtnEl.title = pack.removeAttachment;
    if (emojiBtn) emojiBtn.title = pack.emojiTitle;
    if (attachBtn) attachBtn.title = pack.attachTitle;
    if (deepResearchBtnEl) deepResearchBtnEl.title = pack.deepResearchTitle;
    if (sendBtnEl) sendBtnEl.title = pack.sendTitle;
    if (stopBtnEl) stopBtnEl.title = pack.stopTitle;
    if (jumpToLatestBtn) {
        const jumpLabel = uiText('Tin nhan moi', 'New messages');
        const jumpTitle = uiText('Xuong tin nhan moi nhat', 'Jump to latest messages');
        jumpToLatestBtn.title = jumpTitle;
        jumpToLatestBtn.setAttribute('aria-label', jumpTitle);
        if (jumpToLatestLabelEl) jumpToLatestLabelEl.textContent = jumpLabel;
    }
    if (voiceBtnEl) {
        voiceBtnEl.title = isVoiceRecognitionActive ? chatText('voiceInputStopTitle') : chatText('voiceInputTitle');
        voiceBtnEl.setAttribute('aria-label', voiceBtnEl.title);
    }
    if (researchTitle) researchTitle.innerHTML = `<i class="fas fa-microscope"></i> ${pack.researchPlan}`;
    if (editResearchBtn) editResearchBtn.innerHTML = `<i class="fas fa-edit"></i> ${pack.edit}`;
    if (startResearchBtn) startResearchBtn.innerHTML = `<i class="fas fa-play"></i> ${pack.startResearch}`;
    if (sourcesTitle) sourcesTitle.innerHTML = `<i class="fas fa-book-open"></i> ${pack.sources}`;
    ensureAnalysisModeToggle();
    repairDomText(document.body);
    updateVoiceButtonState();
}

// =======================================================
// ✅ DEBUG LOG - KIỂM TRA KHI LOAD
// =======================================================
console.log("=== CHAT.JS DEBUG ===");
console.log("Window location:", window.location.href);
console.log("Protocol:", window.location.protocol);
console.log("Hostname:", window.location.hostname);

// =======================================================
// ✅ HÀM LẤY URL API - FIXED: LUÔN DÙNG HTTP
// =======================================================
function getBotApiUrl(endpoint = "ask_stream") {
    // QUAN TRỌNG: LUÔN dùng HTTP cho development
    return `${API_BASE_URL}/${endpoint}`;
}

function formatRelativeLastSeen(lastSeenTs) {
    const pack = chatPack();
    const ts = Number(lastSeenTs || 0);
    if (!ts) return pack.offline;
    const diffMs = Date.now() - ts;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return getCurrentLanguage() === 'vi' ? "Vừa hoạt động" : "Active just now";
    if (diffMins < 60) return getCurrentLanguage() === 'vi' ? `Hoạt động ${diffMins} phút trước` : `Active ${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return getCurrentLanguage() === 'vi' ? `Hoạt động ${diffHours} giờ trước` : `Active ${diffHours} hr ago`;
    const diffDays = Math.floor(diffHours / 24);
    return getCurrentLanguage() === 'vi' ? `Hoạt động ${diffDays} ngày trước` : `Active ${diffDays} d ago`;
}

function setFriendStatusText(text) {
    if (friendStatusDisplay) friendStatusDisplay.textContent = text || chatPack().offline;
}

function updateSelectedFriendStatus(forceText = null) {
    if (!friendStatusDisplay) return;
    if (forceText) {
        setFriendStatusText(forceText);
        return;
    }
    if (!selectedFriendUid) {
        setFriendStatusText(chatPack().offline);
        return;
    }
    if (selectedFriendUid === CHATBOT_UID) {
        setFriendStatusText(chatPack().assistant);
        return;
    }

    const p = onlinePresence[selectedFriendUid] || {};
    if (p.online) {
        setFriendStatusText(getCurrentLanguage() === 'vi' ? "Đang hoạt động" : "Active now");
        return;
    }
    setFriendStatusText(formatRelativeLastSeen(p.lastSeen));
}

function emitLastMessageUpdated(friendUid, message) {
    if (!friendUid || !message) return;
    const safeMsg = {
        text: message.text || "",
        rawText: message.rawText || message.text || "",
        type: message.type || "text",
        timestamp: message.timestamp || Date.now(),
        sender: message.sender || currentUserUid
    };
    lastMessages[friendUid] = safeMsg;
    window.dispatchEvent(new CustomEvent('lastMessageUpdated', {
        detail: { friendUid, message: safeMsg }
    }));
}

function emitNewMessageForFriend(friendUid, message, unreadCount) {
    if (!friendUid || !message) return;
    window.dispatchEvent(new CustomEvent('newMessageForFriend', {
        detail: { friendUid, message, unreadCount }
    }));
}

function updateAnalysisModeButton(button = null) {
    const mode = fileAnalysisMode || 'assistant';

    const options = document.querySelectorAll('.analysis-mode-option');
    options.forEach((opt) => {
        const isActive = opt.getAttribute('data-mode') === mode;
        opt.classList.toggle('active', isActive);
        opt.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
}

function setFileAnalysisMode(mode, notify = true) {
    const normalized = FILE_ANALYSIS_MODE_ORDER.includes(mode) ? mode : 'assistant';
    fileAnalysisMode = normalized;
    updateAnalysisModeButton();
    if (notify) {
        const labels = analysisModeLabels();
        showToast(chatText('analysisModeChanged', { mode: labels[normalized] || normalized }), 'info');
    }
}

function ensureAnalysisModeToggle() {
    const wrap = document.getElementById('analysisModeWrap');
    if (!wrap) return;

    const labels = analysisModeLabels();
    wrap.innerHTML = FILE_ANALYSIS_MODE_ORDER.map((mode) => {
        const label = labels[mode] || mode;
        return `
            <button type="button" class="analysis-mode-option analysis-mode-chip" data-mode="${mode}" aria-pressed="false">
                ${label}
            </button>
        `;
    }).join('');

    if (!wrap.dataset.bound) {
        wrap.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const option = e.target.closest('.analysis-mode-option');
            if (!option) return;
            const mode = option.getAttribute('data-mode') || 'assistant';
            setFileAnalysisMode(mode, true);
        });
        wrap.dataset.bound = '1';
    }
    updateAnalysisModeButton();
}

function getSpeechRecognitionLang() {
    const current = String(getCurrentLanguage() || 'en').toLowerCase();
    const map = {
        vi: 'vi-VN',
        en: 'en-US',
        es: 'es-ES'
    };
    return map[current] || current || 'en-US';
}

function updateVoiceButtonState() {
    if (!voiceBtn) voiceBtn = document.getElementById('voiceBtn');
    if (!voiceBtn) return;

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    speechRecognitionSupported = !!SpeechRecognitionCtor;
    voiceBtn.disabled = !speechRecognitionSupported;
    voiceBtn.classList.toggle('recording', isVoiceRecognitionActive);

    const icon = voiceBtn.querySelector('i');
    if (icon) {
        icon.className = !speechRecognitionSupported
            ? 'fas fa-microphone-slash'
            : (isVoiceRecognitionActive ? 'fas fa-stop' : 'fas fa-microphone');
    }

    const title = !speechRecognitionSupported
        ? chatText('voiceInputUnsupported')
        : (isVoiceRecognitionActive ? chatText('voiceInputStopTitle') : chatText('voiceInputTitle'));
    voiceBtn.title = title;
    voiceBtn.setAttribute('aria-label', title);
}

function stopVoiceRecognition(manual = true, suppressResults = false) {
    voiceRecognitionManualStop = manual;
    suppressVoiceRecognitionResults = suppressResults || suppressVoiceRecognitionResults;
    if (!speechRecognition) {
        isVoiceRecognitionActive = false;
        updateVoiceButtonState();
        return;
    }
    if (!isVoiceRecognitionActive) {
        updateVoiceButtonState();
        return;
    }
    try {
        speechRecognition.stop();
    } catch (error) {
        console.warn('Voice recognition stop failed:', error);
        isVoiceRecognitionActive = false;
        updateVoiceButtonState();
    }
}

function initVoiceRecognition() {
    if (!voiceBtn) voiceBtn = document.getElementById('voiceBtn');
    if (!voiceBtn || voiceBtn.dataset.bound === '1') {
        updateVoiceButtonState();
        return;
    }

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    speechRecognitionSupported = !!SpeechRecognitionCtor;

    if (speechRecognitionSupported && !speechRecognition) {
        speechRecognition = new SpeechRecognitionCtor();
        speechRecognition.continuous = true;
        speechRecognition.interimResults = true;
        speechRecognition.maxAlternatives = 1;

        speechRecognition.onstart = () => {
            isVoiceRecognitionActive = true;
            voiceRecognitionManualStop = false;
            updateVoiceButtonState();
            showToast(chatText('voiceInputListening'), 'info');
        };

        speechRecognition.onresult = (event) => {
            if (!msgInput) return;
            if (suppressVoiceRecognitionResults) return;
            let finalTranscript = '';
            let interimTranscript = '';
            for (let i = 0; i < event.results.length; i++) {
                const transcript = String(event.results[i][0]?.transcript || '').trim();
                if (!transcript) continue;
                if (event.results[i].isFinal) {
                    finalTranscript += `${transcript} `;
                } else {
                    interimTranscript += `${transcript} `;
                }
            }

            const segments = [
                voiceInputAnchorText.trim(),
                finalTranscript.trim(),
                interimTranscript.trim()
            ].filter(Boolean);
            msgInput.value = segments.join(' ').trim();
            msgInput.dispatchEvent(new Event('input', { bubbles: true }));
        };

        speechRecognition.onerror = (event) => {
            isVoiceRecognitionActive = false;
            updateVoiceButtonState();
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                showToast(chatText('voiceInputPermissionDenied'), 'error');
                return;
            }
            if (event.error !== 'aborted' && event.error !== 'no-speech') {
                showToast(chatText('voiceInputError'), 'error');
            }
        };

        speechRecognition.onend = () => {
            isVoiceRecognitionActive = false;
            voiceRecognitionManualStop = false;
            suppressVoiceRecognitionResults = false;
            updateVoiceButtonState();
        };
    }

    voiceBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!speechRecognitionSupported) {
            showToast(chatText('voiceInputUnsupported'), 'warning');
            updateVoiceButtonState();
            return;
        }
        if (isVoiceRecognitionActive) {
            stopVoiceRecognition(true, false);
            return;
        }
        if (!msgInput) return;
        voiceInputAnchorText = msgInput.value.trim();
        speechRecognition.lang = getSpeechRecognitionLang();
        try {
            speechRecognition.start();
        } catch (error) {
            console.warn('Voice recognition start failed:', error);
            showToast(chatText('voiceInputError'), 'error');
            isVoiceRecognitionActive = false;
            updateVoiceButtonState();
        }
    });

    voiceBtn.dataset.bound = '1';
    updateVoiceButtonState();
}

function insertEmojiIntoInput(emoji) {
    if (!msgInput) return;
    const before = msgInput.value || '';
    const start = msgInput.selectionStart ?? before.length;
    const end = msgInput.selectionEnd ?? before.length;
    msgInput.value = before.slice(0, start) + emoji + before.slice(end);
    msgInput.dispatchEvent(new Event('input', { bubbles: true }));
    msgInput.focus();
    const caret = start + emoji.length;
    msgInput.setSelectionRange(caret, caret);
}

function ensureQuickEmojiRail() {
    if (!chatInputArea) return;
    const existing = document.getElementById('emojiRail');
    if (existing) return;

    const rail = document.createElement('div');
    rail.id = 'emojiRail';
    rail.className = 'emoji-rail';
    const quickEmojis = ['\u{1F602}', '\u{1F60D}', '\u{1F44D}', '\u{1F525}', '\u{1F389}', '\u{1F62D}'];
    quickEmojis.forEach((emoji) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'emoji-rail-btn';
        btn.textContent = emoji;
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            insertEmojiIntoInput(emoji);
        });
        rail.appendChild(btn);
    });

    const anchor = document.getElementById('emojiBtn');
    if (anchor && anchor.parentNode) {
        anchor.parentNode.insertBefore(rail, anchor);
    } else {
        chatInputArea.prepend(rail);
    }
}


// =======================================================
// ✅ HÀM HIỂN THỊ BOT TYPING - PERSISTENT
// =======================================================
function getBotPhaseChipFinalOnly(meta = {}) {
    const phase = String(meta?.phase || '').trim().toLowerCase();
    switch (phase) {
        case 'routing':
            return uiText('Định tuyến', 'Routing');
        case 'planning_search':
            return uiText('Lập kế hoạch', 'Planning');
        case 'searching':
            return uiText('Tìm kiếm', 'Searching');
        case 'fetching':
            return uiText('Đọc nguồn', 'Fetching');
        case 'ranking':
            return uiText('Chọn lọc', 'Ranking');
        case 'summarizing':
            return uiText('Tổng hợp', 'Summarizing');
        case 'streaming_reply':
            return uiText('Đang viết', 'Writing');
        case 'analyzing':
            return uiText('Đang nghĩ', 'Thinking');
        default:
            return uiText('Đang nghĩ', 'Thinking');
    }
}

function getBotDefaultStatusFinalOnly(meta = {}) {
    const phase = String(meta?.phase || '').trim().toLowerCase();
    switch (phase) {
        case 'routing':
            return uiText('Đang chọn hướng trả lời phù hợp', 'Choosing the best response path');
        case 'planning_search':
            return uiText('Đang chuẩn bị kế hoạch tìm kiếm', 'Preparing a focused search plan');
        case 'searching':
            return uiText('Đang tìm nguồn mới nhất', 'Searching for fresh sources');
        case 'fetching':
            return uiText('Đang đọc và đối chiếu nguồn', 'Reading and checking sources');
        case 'ranking':
            return uiText('Đang chọn lọc nguồn tốt nhất', 'Selecting the strongest sources');
        case 'summarizing':
            return uiText('Đang tổng hợp thông tin', 'Synthesizing the findings');
        case 'streaming_reply':
            return uiText('Đang viết câu trả lời', 'Writing the answer');
        case 'analyzing':
            return uiText('Đang hiểu yêu cầu của bạn', 'Understanding your request');
        default:
            return uiText('Đang suy nghĩ', 'Thinking');
    }
}

getBotPhaseChip = getBotPhaseChipFinalOnly;
getBotDefaultStatus = getBotDefaultStatusFinalOnly;

function getBotStatusText(statusText = "", meta = {}) {
    const explicit = repairMojibake(String(statusText || meta?.status || '').trim());
    if (explicit) return explicit;
    return getBotDefaultStatus(meta);
}

function getBotStatusDetail(meta = {}) {
    const explicitDetail = repairMojibake(String(meta?.detail || '').trim());
    if (explicitDetail && explicitDetail !== String(meta?.status || '').trim() && explicitDetail !== String(meta?.label || '').trim()) {
        return explicitDetail;
    }

    const query = repairMojibake(String(meta?.query || '').trim());
    if (query) {
        return query.length > 72 ? `${query.slice(0, 69)}...` : query;
    }

    const resultCount = Number(meta?.result_count);
    const phase = String(meta?.phase || '').trim().toLowerCase();
    if (Number.isFinite(resultCount) && resultCount > 0 && ['searching', 'fetching', 'ranking', 'summarizing'].includes(phase)) {
        return uiText(`Đang đối chiếu ${resultCount} nguồn`, `Cross-checking ${resultCount} sources`);
    }

    return '';
}

function shouldIgnoreLegacyStatusPayload(data = {}) {
    const status = String(data?.status || '').trim();
    if (!status) return false;
    return /(?:Đang tìm kiếm|Searching)\s*\(\d+\/\d+\)\s*:/i.test(status);
}

function getLiveSourceModeLabel(mode = 'candidate') {
    return mode === 'accepted'
        ? uiText('đã chọn', 'kept')
        : uiText('đang quét', 'live');
}

function getBotPhaseChip(meta = {}) {
    const phase = String(meta?.phase || '').trim().toLowerCase();
    switch (phase) {
        case 'routing':
        case 'planning_search':
            return uiText('Dang chuan bi', 'Preparing');
        case 'searching':
            return uiText('Tim kiem', 'Searching');
        case 'fetching':
            return uiText('Doc nguon', 'Fetching');
        case 'ranking':
            return uiText('Chon loc', 'Ranking');
        case 'summarizing':
            return uiText('Tong hop', 'Summarizing');
        case 'streaming_reply':
            return uiText('Dang viet', 'Writing');
        case 'analyzing':
        default:
            return uiText('Dang xu ly', 'Working');
    }
}

function getBotDefaultStatus(meta = {}) {
    const phase = String(meta?.phase || '').trim().toLowerCase();
    switch (phase) {
        case 'routing':
        case 'planning_search':
            return uiText('Dang chuan bi phan hoi', 'Preparing the reply');
        case 'searching':
            return uiText('Dang tim nguon moi nhat', 'Searching for fresh sources');
        case 'fetching':
            return uiText('Dang doc va doi chieu nguon', 'Reading and checking sources');
        case 'ranking':
            return uiText('Dang chon loc nguon tot nhat', 'Selecting the strongest sources');
        case 'summarizing':
            return uiText('Dang tong hop thong tin', 'Synthesizing the findings');
        case 'streaming_reply':
            return uiText('Dang viet cau tra loi', 'Writing the answer');
        case 'analyzing':
        default:
            return uiText('Dang xu ly yeu cau', 'Working on your request');
    }
}

function showBotTypingIndicator() {
    if (!messagesDiv || selectedFriendUid !== CHATBOT_UID) {
        console.log('⚠️ Không thể hiển thị indicator:', {
            isBotTyping,
            hasMessagesDiv: !!messagesDiv,
            isChatbot: selectedFriendUid === CHATBOT_UID
        });
        return;
    }

    console.log('🤖 Bắt đầu hiển thị bot typing indicator');

    // Nếu đang có indicator rồi thì chỉ cập nhật text
    if (isBotTyping && botTypingIndicator) {
        updateBotStatus();
        return;
    }

    // Xóa indicator cũ nếu có
    removeBotTypingIndicator(true);

    isBotTyping = true;

    botTypingIndicator = document.createElement('div');
    botTypingIndicator.className = 'chatbot-typing typing-persist';
    botTypingIndicator.id = 'botTypingIndicator';
    botTypingIndicator.style.cssText = `
        opacity: 1;
        display: flex;
        animation: typingPersist 0.3s ease-out forwards !important;
    `;

    botTypingIndicator.innerHTML = `
        <div class="chatbot-avatar">
            ${getSkemmaOrbAvatarMarkup()}
        </div>
        <div class="ai-typing-stack">
            <div class="ai-status-shell status-refresh" data-phase="thinking">
                <div class="ai-status-topline">
                    <span class="ai-phase-chip">${escapeHtml(uiText('Đang nghĩ', 'Thinking'))}</span>
                    <span class="ai-status-orbit" aria-hidden="true"><span></span><span></span><span></span></span>
                </div>
                <div class="ai-status-copy">
                    <span class="ai-status-text">${escapeHtml(uiText('Đang suy nghĩ', 'Thinking'))}</span>
                    <span class="ai-status-detail" hidden></span>
                </div>
                <div class="ai-status-track" aria-hidden="true">
                    <span class="ai-status-track-bar"></span>
                </div>
            </div>
            <div class="ai-live-sources"></div>
        </div>
    `;

    messagesDiv.appendChild(botTypingIndicator);
    const initialPhaseChip = botTypingIndicator.querySelector('.ai-phase-chip');
    const initialStatusText = botTypingIndicator.querySelector('.ai-status-text');
    if (initialPhaseChip) initialPhaseChip.textContent = uiText('Dang xu ly', 'Working');
    if (initialStatusText) initialStatusText.textContent = uiText('Dang xu ly yeu cau', 'Working on your request');
    scrollToBottomIfAllowed();

    // Timeout tự động xóa sau 300 giây nếu không có phản hồi (Tăng từ 120s)
    if (botTypingTimeout) clearTimeout(botTypingTimeout);
    botTypingTimeout = setTimeout(() => {
        if (isBotTyping) {
            console.warn('⚠️ Bot typing timeout exceeded 300s');
            removeBotTypingIndicator(true);
            appendBotSystemMessage(getChatbotTimeoutMessage(), { isError: true });
            isStreamingActive = false;
            
            if (msgInput) {
                msgInput.disabled = false;
                msgInput.placeholder = chatText('placeholder');
            }
            if (sendBtn) sendBtn.disabled = false;
        }
    }, 300000);

    console.log('✅ Bot typing indicator hiển thị');
}

// =======================================================
// ✅ HÀM CẬP NHẬT TRẠNG THÁI BOT (SUY NGHĨ, TÌM KIẾM...)
// =======================================================
function updateBotStatus(statusText = "", meta = {}) {
    if (!messagesDiv || selectedFriendUid !== CHATBOT_UID) return;

    // Nếu chưa có indicator thì tạo mới
    if (!isBotTyping || !botTypingIndicator) {
        showBotTypingIndicator();
    }

    const statusShell = botTypingIndicator?.querySelector('.ai-status-shell');
    const phaseNode = botTypingIndicator?.querySelector('.ai-phase-chip');
    const statusNode = botTypingIndicator?.querySelector('.ai-status-text');
    const detailNode = botTypingIndicator?.querySelector('.ai-status-detail');
    if (statusShell) {
        const phaseName = String(meta?.phase || '').trim().toLowerCase() || 'thinking';
        statusShell.dataset.phase = phaseName;
        statusShell.classList.remove('status-refresh');
        void statusShell.offsetWidth;
        statusShell.classList.add('status-refresh');
    }
    if (phaseNode) {
        phaseNode.textContent = getBotPhaseChip(meta);
    }
    if (statusNode) {
        statusNode.textContent = getBotStatusText(statusText, meta);
    }
    if (detailNode) {
        const nextDetail = getBotStatusDetail(meta);
        detailNode.textContent = nextDetail;
        detailNode.hidden = !nextDetail;
    }

    // RESET TIMEOUT khi backend còn trả trạng thái
    if (botTypingTimeout) {
        clearTimeout(botTypingTimeout);
        botTypingTimeout = setTimeout(() => {
            if (isBotTyping) {
                console.warn('⚠️ Bot typing timeout exceeded after status update');
                removeBotTypingIndicator(true);
                appendBotSystemMessage(getChatbotTimeoutMessage(), { isError: true });
                isStreamingActive = false;
                if (msgInput) msgInput.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
            }
        }, 300000);
    }
}

// =======================================================
// ✅ SỬA HÀM XÓA BOT TYPING - LUÔN XÓA KHI ĐƯỢC GỌI
// =======================================================
function updateLiveSourcePreview(source, mode = 'candidate') {
    if (!botTypingIndicator || !source?.url) return;

    const url = String(source.url || '').trim();
    if (!url) return;

    let domain = '';
    try {
        domain = new URL(url).hostname.replace(/^www\./, '');
    } catch {
        domain = repairMojibake(String(source.domain || url));
    }

    const title = repairMojibake(String(source.title || domain || url));
    const favicon = source.favicon_url || `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`;
    const existingIndex = liveSearchPreviewSources.findIndex((item) => item.url === url);
    const nextItem = { url, title, domain, favicon, mode };

    if (existingIndex >= 0) {
        liveSearchPreviewSources[existingIndex] = nextItem;
    } else {
        liveSearchPreviewSources.unshift(nextItem);
    }
    liveSearchPreviewSources = liveSearchPreviewSources.slice(0, 3);

    const container = botTypingIndicator.querySelector('.ai-live-sources');
    if (!container) return;
    container.innerHTML = liveSearchPreviewSources.map((item) => `
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="ai-live-source" data-mode="${escapeHtml(item.mode)}">
            <img src="${escapeHtml(item.favicon)}" alt="" width="16" height="16" class="ai-live-source-icon">
            <span class="ai-live-source-meta">
                <span class="ai-live-source-title">${escapeHtml(item.title)}</span>
                <span class="ai-live-source-domain">${escapeHtml(item.domain)}</span>
            </span>
            <span class="ai-live-source-badge">${escapeHtml(getLiveSourceModeLabel(item.mode))}</span>
        </a>
    `).join('');
}

function removeBotTypingIndicator(force = false) {
    console.log('🗑️ removeBotTypingIndicator called:', {
        force,
        isBotTyping,
        isStreamingActive,
        botStreamingPaused
    });

    // LUÔN xóa nếu có force hoặc đang không streaming
    if (force || !isStreamingActive || botStreamingPaused) {
        console.log('✅ Điều kiện xóa indicator thỏa mãn');

        if (botTypingIndicator && botTypingIndicator.parentNode) {
            console.log('🗑️ Đang xóa indicator khỏi DOM...');
            botTypingIndicator.style.animation = 'fadeOut 0.3s ease-out forwards';
            setTimeout(() => {
                if (botTypingIndicator && botTypingIndicator.parentNode) {
                    botTypingIndicator.parentNode.removeChild(botTypingIndicator);
                    console.log('✅ Đã xóa indicator khỏi DOM');
                }
                botTypingIndicator = null;
                liveSearchPreviewSources = [];
            }, 300);
        }

        isBotTyping = false;

        if (botTypingTimeout) {
            clearTimeout(botTypingTimeout);
            botTypingTimeout = null;
            console.log('✅ Đã xóa botTypingTimeout');
        }

        console.log('✅ Bot typing indicator đã được xóa hoàn toàn');
    } else {
        console.log('⚠️ Chưa xóa indicator vì đang streaming và không paused');
    }
}


// =======================================================
// ✅ HÀM ĐẢM BẢO TẮT TYPING INDICATOR TRONG MỌI TRƯỜNG HỢP
// =======================================================
function ensureBotTypingIndicatorIsRemoved() {
    console.log('🔍 Đảm bảo bot typing indicator đã bị xóa...');

    // Luôn đặt trạng thái về false
    isBotTyping = false;

    // Xóa timeout nếu có
    if (botTypingTimeout) {
        clearTimeout(botTypingTimeout);
        botTypingTimeout = null;
    }

    // Xóa indicator khỏi DOM nếu có
    if (botTypingIndicator && botTypingIndicator.parentNode) {
        botTypingIndicator.style.animation = 'fadeOut 0.3s ease-out forwards';
        setTimeout(() => {
            if (botTypingIndicator && botTypingIndicator.parentNode) {
                botTypingIndicator.parentNode.removeChild(botTypingIndicator);
            }
            botTypingIndicator = null;
            liveSearchPreviewSources = [];
        }, 300);
    }

    // Xóa indicator bằng ID nếu vẫn còn
    const indicatorById = document.getElementById('botTypingIndicator');
    if (indicatorById && indicatorById.parentNode) {
        indicatorById.style.animation = 'fadeOut 0.3s ease-out forwards';
        setTimeout(() => {
            if (indicatorById && indicatorById.parentNode) {
                indicatorById.parentNode.removeChild(indicatorById);
            }
        }, 300);
    }

    console.log('✅ Đã đảm bảo bot typing indicator bị xóa');
}

// =======================================================
// ✅ HÀM TẠO TIN NHẮN BOT VỚI STREAMING
// =======================================================
function createBotMessageStreaming(text, options = {}, skipRemoveIndicator = false) {
    if (!messagesDiv) return null;
    text = stripHiddenReasoningSections(text);

    // LOGIC MỚI: Chỉ xóa typing indicator nếu không có cờ skip.
    if (!skipRemoveIndicator) {
        removeBotTypingIndicator(true);
    }

    const box = document.createElement("div");
    box.className = "msg-box bot-box";
    box.dataset.botMessage = "true";

    // THÊM STYLE TRỰC TIẾP ĐỂ ĐẢM BẢO HIỂN THỊ
    box.style.cssText = `
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        position: relative !important;
        z-index: 10 !important;
        margin: 8px 0 !important;
        max-width: 85% !important;
        align-self: flex-start !important;
        animation: msgSlideIn 0.3s ease-out forwards !important;
        transform: translateX(0) !important;
    `;

    const messageId = `bot_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    box.id = messageId;
    const time = formatTime(Date.now());

        box.innerHTML = `
            <div class="msg bot is-streaming" style="
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                position: relative !important;
                z-index: 11 !important;
                border-radius: 18px 18px 18px 4px !important;
                padding: 12px 16px !important;
                backdrop-filter: blur(10px) !important;
                font-size: 15px !important;
                line-height: 1.5 !important;
                word-wrap: break-word !important;
                word-break: break-word !important;
                overflow-wrap: break-word !important;
                max-width: 100% !important;
                min-height: 40px !important;
            ">
                <div class="msg-actions">
                    <button class="action-btn copy-btn" title="${uiText('Sao chép', 'Copy')}"><i class="fas fa-copy"></i></button>
                </div>
                <div class="streaming-text" id="streaming_${messageId}" style="
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                font-size: 15px !important;
                line-height: inherit !important;
                white-space: pre-wrap !important;
                word-wrap: break-word !important;
                word-break: break-word !important;
                overflow-wrap: break-word !important;
                width: 100% !important;
                max-width: 100% !important;
                min-width: 0 !important;
            "></div>
        </div>
        <div class="time" style="
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            font-size: 11px !important;
            margin-top: 4px !important;
            margin-left: 10px !important;
            text-align: left !important;
        ">${time}</div>
    `;

    messagesDiv.appendChild(box);

    // SCROLL NGAY LẬP TỨC
    setTimeout(() => {
        if (messagesDiv) {
            scrollToBottomIfAllowed();
        }
    }, 50);

    const streamingElement = document.getElementById(`streaming_${messageId}`);

    // Debug: LOG để kiểm tra
    console.log('🎯 Bot message created:', messageId);

    // Đặt trạng thái streaming
    isStreamingActive = true;

    // Bắt đầu streaming nếu có text (thường là rỗng khi mới tạo)
    if (text) {
        startTextStreaming(text, messageId, options);
    }

    return messageId;
}


// =======================================================
// ✅ QUẢN LÝ TIN NHẮN CHATBOT TRONG SESSION
// =======================================================
function initChatbotSession() {
    if (!currentUserUid) return;

    chatbotSession.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    chatbotSession.messages = [];
    chatbotSession.lastUpdated = Date.now();
    chatbotSession.isActive = false;
    if (!isSettingEnabled('ephemeral_chat', true)) {
        try {
            sessionStorage.removeItem(`chatbot_session_${currentUserUid}`);
        } catch {}
        return;
    }

    // Load từ sessionStorage nếu có
    try {
        const sessionKey = `chatbot_session_${currentUserUid}`;
        const stored = sessionStorage.getItem(sessionKey);
        if (stored) {
            const data = JSON.parse(stored);
            chatbotSession.messages = data.messages || [];
            console.log(`📋 Loaded ${chatbotSession.messages.length} chatbot messages from session (session-only)`);
        }
    } catch (error) {
        console.error("❌ Error loading chatbot session:", error);
    }

    console.log('✅ Chatbot session initialized (session-only)');
}

// =======================================================
// ✅ LƯU BOT MESSAGE VÀO SESSION
// =======================================================
function saveBotMessageToSession(text, messageId) {
    if (!currentUserUid || selectedFriendUid !== CHATBOT_UID) return;

    try {
        const cleanText = stripHiddenReasoningSections(text);
        const botMessage = {
            id: messageId || `bot_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            type: "bot_message",
            text: cleanText,
            rawText: cleanText,
            timestamp: Date.now(),
            sender: CHATBOT_UID,
            receiver: currentUserUid
        };

        saveToChatbotSession(botMessage);
        console.log('✅ Bot message saved to session (NOT Firestore):', botMessage.id);

    } catch (error) {
        console.error('❌ Error saving bot message to session:', error);
    }
}

// =======================================================
// ✅ HÀM LƯU VÀO CHATBOT SESSION (SESSION STORAGE)
// =======================================================
function saveToChatbotSession(message) {
    if (!currentUserUid || !message) return;
    if (!isSettingEnabled('ephemeral_chat', true)) return;

    try {
        // Kiểm tra xem tin nhắn đã tồn tại chưa để tránh trùng lặp
        const existingIndex = chatbotSession.messages.findIndex(m => m.id === message.id);

        if (existingIndex !== -1) {
            // Cập nhật tin nhắn cũ
            chatbotSession.messages[existingIndex] = {
                ...chatbotSession.messages[existingIndex],
                ...message
            };
            console.log('🔄 Updated existing message in session:', message.id);
        } else {
            // Thêm mới
            chatbotSession.messages.push(message);
            console.log('💾 Added new message to session:', message.id);
        }

        chatbotSession.lastUpdated = Date.now();
        chatbotSession.isActive = true;

        // Lưu vào sessionStorage (tạm thời cho tab hiện tại)
        const sessionKey = `chatbot_session_${currentUserUid}`;
        const sessionData = {
            messages: chatbotSession.messages.slice(-50), // Giữ 50 tin nhắn gần nhất
            lastUpdated: Date.now(),
            sessionId: chatbotSession.sessionId,
            isActive: true
        };
        sessionStorage.setItem(sessionKey, JSON.stringify(sessionData));

    } catch (error) {
        console.error('❌ Error saving to session:', error);
    }
}

// =======================================================
// ✅ HÀM LOAD TIN NHẮN CHATBOT TỪ SESSION
// =======================================================
function loadChatbotMessagesFromSession() {
    if (!currentUserUid || selectedFriendUid !== CHATBOT_UID) return [];
    if (!isSettingEnabled('ephemeral_chat', true)) return [];

    try {
        // FIX: Ưu tiên dữ liệu trong RAM nếu đang có để không bị mất nội dung đang stream khi chuyển tab
        if (chatbotSession.messages && chatbotSession.messages.length > 0) {
            console.log('🧠 Using in-memory chatbot messages (Preserving stream state)');
            return chatbotSession.messages;
        }

        const sessionKey = `chatbot_session_${currentUserUid}`;
        const stored = sessionStorage.getItem(sessionKey);

        if (stored) {
            const data = JSON.parse(stored);
            chatbotSession.messages = data.messages || [];
            chatbotSession.lastUpdated = data.lastUpdated || Date.now();
            chatbotSession.sessionId = data.sessionId || chatbotSession.sessionId;
            chatbotSession.isActive = data.isActive || false;

            console.log(`📋 Loaded ${chatbotSession.messages.length} chatbot messages from session`);
            return chatbotSession.messages;
        }

        return [];

    } catch (error) {
        console.error('❌ Error loading chatbot session:', error);
        return [];
    }
}

// =======================================================
// ✅ HÀM LƯU USER MESSAGE (GỬI ĐẾN CHATBOT) - CHỈ LƯU SESSION
// =======================================================
function saveUserMessageToSession(text, options = {}) {
    if (!currentUserUid || selectedFriendUid !== CHATBOT_UID) return null;

    try {
        const {
            type = "user_message",
            mediaURL = null,
            fileName = null,
            prompt = null
        } = options;

        const userMessage = {
            id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            type: type,
            text: text,
            rawText: text,
            mediaURL: mediaURL,
            fileName: fileName,
            prompt: prompt,
            timestamp: Date.now(),
            sender: currentUserUid,
            receiver: CHATBOT_UID
        };

        saveToChatbotSession(userMessage);
        console.log('✅ User message saved to session (NOT Firestore):', userMessage.id);
        return userMessage.id;

    } catch (error) {
        console.error('❌ Error saving user message to session:', error);
        return null;
    }
}

// =======================================================
// ✅ HÀM XÓA TOÀN BỘ CHATBOT SESSION
// =======================================================
function handleVisibilityChange() {
    if (document.hidden) {
        console.log('👁️ Tab hidden, sẽ không tự động xóa session');
        // KHÔNG tự động xóa session nữa
        // Chỉ đánh dấu là inactive
        if (selectedFriendUid === CHATBOT_UID) {
            chatbotSession.isActive = false;
        }
    } else {
        // Tab visible trở lại
        console.log('👁️ Tab visible again');
        if (selectedFriendUid === CHATBOT_UID) {
            chatbotSession.isActive = true;
            chatbotSession.lastUpdated = Date.now();
        }
    }
}

// =======================================================
// ✅ HÀM XỬ LÝ KHI RỜI TRANG
// =======================================================
let isUnloading = false;
function handlePageUnload() {
    if (isUnloading) return;
    isUnloading = true;

    console.log('🚪 Page unloading...');

    // LUÔN xóa session chatbot khi rời trang
    try {
        const preserveInternalNavigation = sessionStorage.getItem(SITE_INTERNAL_NAV_KEY) === '1';
        if (preserveInternalNavigation) {
            sessionStorage.removeItem(SITE_INTERNAL_NAV_KEY);
        }
        if (sessionStorage.getItem(CHAT_SESSION_PRESERVE_KEY) === '1') {
            sessionStorage.removeItem(CHAT_SESSION_PRESERVE_KEY);
            if (preserveInternalNavigation) return;
        }
        if (preserveInternalNavigation) {
            return;
        }
        sessionStorage.removeItem(CHAT_BOOT_KEY);
    } catch {}
    clearChatbotSession();
}

// =======================================================
// ✅ CẬP NHẬT HÀM CLEAR SESSION - THÊM KIỂM TRA
// =======================================================
function clearChatbotSession() {
    if (!currentUserUid) return;

    try {
        // Gọi backend để xóa memory vĩnh viễn (Theo yêu cầu: tắt là xóa)
        fetch(`${API_BASE_URL}/clear_memory?user_id=${currentUserUid}`, { method: 'POST' })
            .then(r => r.json())
            .then(d => console.log('🧠 Backend memory cleared:', d))
            .catch(e => console.error('❌ Failed to clear backend memory:', e));

        // Xóa container điều khiển nếu có
        if (pauseResumeContainer && pauseResumeContainer.parentNode) {
            pauseResumeContainer.remove();
            pauseResumeContainer = null;
        }

        // Ngắt streaming nếu đang chạy
        if (botStreamingController) {
            botStreamingController.abort();
            botStreamingController = null;
        }

        // Xóa khỏi sessionStorage
        const sessionKey = `chatbot_session_${currentUserUid}`;
        sessionStorage.removeItem(sessionKey);

        // Reset session
        chatbotSession.messages = [];
        chatbotSession.lastUpdated = Date.now();
        chatbotSession.isActive = false;

        // Reset streaming state
        resetBotStreamingState();

        console.log('🗑️ Chatbot session cleared (tin nhắn chatbot đã xóa, out web là mất)');

    } catch (error) {
        console.error('❌ Error clearing chatbot session:', error);
    }
}

// =======================================================
// ✅ THÊM EVENT LISTENERS ĐỂ TỰ ĐỘNG XÓA SESSION
// =======================================================
window.addEventListener('beforeunload', handlePageUnload);
document.addEventListener('visibilitychange', handleVisibilityChange);

// =======================================================
// ✅ LOADING FUNCTIONS
// =======================================================
let loadTimeout = null;
let networkCheckInterval = null;
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');
const loadingProgress = document.getElementById('loadingProgress');
const progressFill = loadingProgress?.querySelector('.progress-fill');
const loadingPercent = document.getElementById('loadingPercent');
const loadingError = document.getElementById('loadingError');
const errorTitle = document.getElementById('errorTitle');
const errorMessage = document.getElementById('errorMessage');
const timeoutWarning = document.getElementById('timeoutWarning');
const retryButton = document.getElementById('retryButton');
const continueButton = document.getElementById('continueButton');
const wifiIcon = document.getElementById('wifiIcon');
const networkStatusText = document.getElementById('networkStatusText');
const networkSpeed = document.getElementById('networkSpeed');
const loadingTip = document.getElementById('loadingTip');
const timeoutCountdown = document.getElementById('timeoutCountdown');

function hideLoadingOverlayImmediately() {
    if (!loadingOverlay) return;
    loadingOverlay.classList.add('hidden');
    loadingOverlay.style.display = 'none';
}

if (shouldSkipInitialLoadingOverlay()) {
    hideLoadingOverlayImmediately();
}

// =======================================================
// ✅ CẬP NHẬT LOADING PROGRESS
// =======================================================
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

function loadingStepText(step) {
    const isVi = getCurrentLanguage() === 'vi';
    const map = {
        1: isVi ? 'Đang tải thông tin người dùng...' : 'Loading user profile...',
        2: isVi ? 'Đang kiểm tra kết nối mạng...' : 'Checking network connection...',
        3: isVi ? 'Đang khởi tạo dữ liệu...' : 'Initializing data...',
        4: isVi ? 'Đang kết nối chat...' : 'Connecting chat...',
        5: isVi ? 'Đang tải tin nhắn...' : 'Loading messages...',
        6: isVi ? 'Đang thiết lập thông báo...' : 'Preparing notifications...',
        7: isVi ? 'Sẵn sàng!' : 'Ready!'
    };
    return map[step] || chatPack().loading;
}
let currentLoadingPercent = 0;
let loadingStartedAt = Date.now();
function updateLoadingProgress(step, message) {
    message = repairMojibake(message);
    console.log(`Step ${step}: ${message}`);

    if (loadingText) {
        loadingText.textContent = message;
    }

    if (progressFill) {
        const stepPercentMap = {
            1: 14,
            2: 28,
            3: 42,
            4: 57,
            5: 71,
            6: 85,
            7: 100
        };
        const mapped = stepPercentMap[step] ?? 0;
        const progress = Math.max(currentLoadingPercent, Math.min(mapped, 100));
        currentLoadingPercent = progress;
        progressFill.style.width = `${progress}%`;
        if (loadingPercent) {
            loadingPercent.textContent = `${progress}%`;
        }
    }
}

function completeLoadingWithMinimum(minDurationMs = 1200) {
    const elapsed = Date.now() - loadingStartedAt;
    const waitMs = Math.max(0, minDurationMs - elapsed);
    setTimeout(completeLoading, waitMs);
}

// =======================================================
// ✅ HÀM COMPLETE LOADING
// =======================================================
function completeLoading() {
    console.log("✅ Loading complete");

    if (loadingOverlay) {
        loadingOverlay.classList.add('hidden');
        setTimeout(() => {
            loadingOverlay.style.display = 'none';
        }, 500);
    }

    if (loadTimeout) {
        clearTimeout(loadTimeout);
        loadTimeout = null;
    }

    if (networkCheckInterval) {
        clearInterval(networkCheckInterval);
        networkCheckInterval = null;
    }
}

// =======================================================
// ✅ KIỂM TRA KẾT NỐI MẠNG
// =======================================================
function checkNetworkStatus() {
    const pack = chatPack();
    if (!navigator.onLine) {
        if (wifiIcon) wifiIcon.className = 'fas fa-wifi-slash network-offline';
        if (networkStatusText) networkStatusText.textContent = pack.internetDisconnected || 'Internet disconnected';
        if (networkSpeed) networkSpeed.textContent = '';
        return 'offline';
    }

    // Thay đổi cách kiểm tra network
    const startTime = Date.now();

    // Tạo một promise để đo latency
    const latencyPromise = new Promise((resolve) => {
        // Dùng Google DNS để test kết nối
        const img = new Image();
        img.onload = () => {
            const latency = Date.now() - startTime;
            resolve(latency);
        };
        img.onerror = () => {
            resolve(999); // Giá trị cao nếu lỗi
        };
        img.src = 'https://www.google.com/images/phd/px.gif?t=' + startTime;
    });

    latencyPromise.then((latency) => {
        let status = 'good';
        let statusText = pack.stableConnection || 'Stable connection';
        let speedText = '';

        if (latency < 100) {
            status = 'good';
            statusText = pack.fastConnection;
            speedText = `< ${latency}ms`;
        } else if (latency < 500) {
            status = 'fair';
            statusText = pack.mediumConnection;
            speedText = `< ${latency}ms`;
        } else {
            status = 'poor';
            statusText = pack.slowConnection;
            speedText = `> ${latency}ms`;
        }

        if (wifiIcon) {
            wifiIcon.className = `fas fa-wifi network-${status}`;
        }
        if (networkStatusText) {
            networkStatusText.textContent = statusText;
        }
        if (networkSpeed) {
            networkSpeed.textContent = speedText;
        }
    }).catch(() => {
        if (wifiIcon) wifiIcon.className = 'fas fa-wifi-slash network-offline';
        if (networkStatusText) networkStatusText.textContent = pack.networkCheckFailed || 'Network check failed';
    });

    return navigator.onLine ? 'online' : 'offline';
}

// ======================================================= 
// ✅ HÀM CẬP NHẬT TRẠNG THÁI CHAT UI
// ======================================================= 
// ======================================================= 
// ✅ CẬP NHẬT HÀM CẬP NHẬT TRẠNG THÁI CHAT UI
// ======================================================= 
function updateChatUIState() {
    const chatContainer = document.querySelector('.chat-container');
    const hasFriend = typeof selectedFriendUid === 'string' && selectedFriendUid.trim().length > 0;

    if (chatContainer) {
        if (hasFriend) {
            chatContainer.classList.add('has-friend');
            chatContainer.classList.remove('no-friend');

            if (welcomeState) welcomeState.style.display = 'none';
            if (chatInputArea) chatInputArea.style.display = 'flex';

            // QUẢN LÝ INPUT KHI CHAT VỚI CHATBOT
            if (msgInput && selectedFriendUid === CHATBOT_UID) {
                if (isStreamingActive && !botStreamingPaused) {
                    // Đang streaming và KHÔNG bị dừng => VÔ HIỆU HÓA
                    msgInput.disabled = true;
                    msgInput.placeholder = chatText('replying');
                    msgInput.classList.add('chat-input-disabled');

                    if (sendBtn) {
                        sendBtn.disabled = true;
                        sendBtn.classList.add('btn-disabled');
                    }
                } else if (isStreamingActive && botStreamingPaused) {
                    // Đang streaming nhưng ĐÃ DỪNG => CHO PHÉP NHẬP
                    msgInput.disabled = false;
                    msgInput.placeholder = chatText('sendNewMessage');
                    msgInput.classList.remove('chat-input-disabled');

                    if (sendBtn) {
                        sendBtn.disabled = false;
                        sendBtn.classList.remove('btn-disabled');
                    }
                } else {
                    // Không streaming => BÌNH THƯỜNG
                    msgInput.disabled = false;
                    msgInput.placeholder = chatText('placeholder');
                    msgInput.classList.remove('chat-input-disabled');

                    if (sendBtn) {
                        sendBtn.disabled = false;
                        sendBtn.classList.remove('btn-disabled');
                    }
                }
            }

            // Vô hiệu hóa nút gọi cho chatbot
            if (voiceCallBtn && videoCallBtn) {
                voiceCallBtn.disabled = selectedFriendUid === CHATBOT_UID;
                videoCallBtn.disabled = selectedFriendUid === CHATBOT_UID;
            }
        } else {
            chatContainer.classList.add('no-friend');
            chatContainer.classList.remove('has-friend');

            if (welcomeState) welcomeState.style.display = 'flex';
            if (emptyChatState) emptyChatState.style.display = 'none';
            if (chatInputArea) chatInputArea.style.display = 'none';

            if (voiceCallBtn && videoCallBtn) {
                voiceCallBtn.disabled = true;
                videoCallBtn.disabled = true;
            }
        }
    }
}

// ======================================================= 
// ✅ HÀM KIỂM TRA VÀ HIỂN THỊ TRẠNG THÁI RỖNG
// ======================================================= 
function checkAndShowEmptyState() {
    if (!selectedFriendUid || !messagesDiv) return;

    const hasMessages = messagesDiv.querySelectorAll('.msg-box').length > 0;

    if (hasMessages) {
        if (emptyChatState) emptyChatState.style.display = 'none';
        if (welcomeState) welcomeState.style.display = 'none';
    } else {
        if (emptyChatState) {
            emptyChatState.style.display = 'flex';

            const friendNameGreeting = document.getElementById('friendNameGreeting');
            if (friendNameGreeting && selectedFriendName) {
                friendNameGreeting.textContent = selectedFriendName;
            }

            const friendAvatarLarge = document.getElementById('friendAvatarLarge');
            if (friendAvatarLarge && selectedFriendName) {
                friendAvatarLarge.textContent = selectedFriendName.charAt(0).toUpperCase();
            }

            document.querySelectorAll('.greeting-btn').forEach(btn => {
                btn.onclick = function () {
                    const text = this.getAttribute('data-text');
                    if (text && msgInput) {
                        msgInput.value = text;
                        sendTextMessage();
                    }
                };
            });
        }
        if (welcomeState) welcomeState.style.display = 'none';
    }
}

// =======================================================
// ✅ HÀM KIỂM TRA VÀ CẬP NHẬT INPUT STATE
// =======================================================
function checkAndUpdateInputState() {
    if (!msgInput || selectedFriendUid !== CHATBOT_UID) return;

    if (isStreamingActive && !botStreamingPaused) {
        // Đang streaming => vô hiệu hóa
        msgInput.disabled = true;
        msgInput.placeholder = chatText('replying');
        msgInput.classList.add('chat-input-disabled');

        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.classList.add('btn-disabled');
        }
    } else {
        // Không streaming hoặc đã dừng => bình thường
        msgInput.disabled = false;
        msgInput.placeholder = chatText('placeholder');
        msgInput.classList.remove('chat-input-disabled');

        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.classList.remove('btn-disabled');
        }
    }
}

// Gọi hàm này khi thay đổi trạng thái streaming
window.addEventListener('streamingStateChanged', checkAndUpdateInputState);

// ======================================================= 
// ✅ KHỞI TẠO AUDIO CONTEXT
// ======================================================= 
function initAudioContext() {
    if (audioContextInitialized || !window.AudioContext) return;

    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioContextInitialized = true;
        console.log("✅ AudioContext initialized");
    } catch (error) {
        console.error("❌ Không thể khởi tạo AudioContext:", error);
    }
}

// ======================================================= 
// ✅ KHỞI TẠO UNREAD COUNTS
// ======================================================= 
async function initializeUnreadCounts() {
    if (!currentUserUid) return;

    try {
        const stored = localStorage.getItem(`unread_${currentUserUid}`);
        if (stored) {
            unreadCounts = JSON.parse(stored);
            console.log("✅ Đã load unread counts từ localStorage:", unreadCounts);
        } else {
            unreadCounts = {};
            localStorage.setItem(`unread_${currentUserUid}`, JSON.stringify(unreadCounts));
        }
    } catch (error) {
        console.error("❌ Lỗi load unread counts:", error);
        unreadCounts = {};
    }
}

// ======================================================= 
// ✅ HÀM PHÁT ÂM THANH THÔNG BÁO
// ======================================================= 
function playNotificationSound() {
    if (!isSettingEnabled('sound_notify', true)) return;
    try {
        if (!audioContextInitialized) {
            console.log("⚠️ AudioContext chưa được khởi tạo, bỏ qua âm thanh");
            return;
        }

        if (audioContext.state === 'suspended') {
            audioContext.resume().then(() => {
                console.log("✅ AudioContext resumed");
                playSound();
            }).catch(err => {
                console.error("❌ Không thể resume AudioContext:", err);
            });
        } else {
            playSound();
        }

        function playSound() {
            try {
                const oscillator = audioContext.createOscillator();
                const gainNode = audioContext.createGain();

                oscillator.connect(gainNode);
                gainNode.connect(audioContext.destination);

                oscillator.frequency.value = 800;
                oscillator.type = 'sine';

                gainNode.gain.setValueAtTime(0.2, audioContext.currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.3);
            } catch (soundError) {
                console.log("⚠️ Không thể phát âm thanh:", soundError);
            }
        }
    } catch (error) {
        console.log("⚠️ Lỗi AudioContext:", error);
    }
}

// ======================================================= 
// ✅ HÀM HIỂN THỊ NOTIFICATION TRONG APP
// ======================================================= 
function showInAppNotification(msg) {
    if (!isSettingEnabled('message_preview', true)) return;
    try {
        const pack = chatPack();
        const oldNotifications = document.querySelectorAll('.in-app-notification');
        oldNotifications.forEach(n => {
            n.style.animation = 'slideOutNotification 0.3s ease-out forwards';
            setTimeout(() => n.remove(), 300);
        });

        const senderName = repairMojibake(msg.senderName || selectedFriendName || (getCurrentLanguage() === 'vi' ? 'Ai đó' : 'Someone'));
        let messageText = '';

        if (msg.type === 'image') {
            messageText = `📷 ${pack.imageLabel}`;
        } else if (msg.type === 'video') {
            messageText = `🎥 ${pack.videoLabel}`;
        } else if (msg.type === 'file') {
            messageText = getCurrentLanguage() === 'vi' ? '📎 [Tệp]' : '📎 [File]';
        } else {
            messageText = repairMojibake(msg.text || msg.content || (getCurrentLanguage() === 'vi' ? '📨 Tin nhắn mới' : '📨 New message'));
        }

        const notification = document.createElement('div');
        notification.className = 'in-app-notification';
        notification.dataset.sender = msg.sender;

        notification.innerHTML = `
            <div class="notification-content">
                <div class="notification-avatar">
                    ${senderName.charAt(0).toUpperCase()}
                </div>
                <div class="notification-body">
                    <div class="notification-name">${senderName}</div>
                    <div class="notification-message">${messageText}</div>
                    <div class="notification-time">${pack.justNow}</div>
                </div>
            </div>
            <div class="notification-close">&times;</div>
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        notification.querySelector('.notification-close').onclick = () => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        };

        notification.onclick = (e) => {
            if (!e.target.classList.contains('notification-close')) {
                const event = new CustomEvent("friendSelected", {
                    detail: {
                        uid: msg.sender,
                        name: senderName
                    }
                });
                window.dispatchEvent(event);
                notification.classList.remove('show');
                setTimeout(() => notification.remove(), 300);
            }
        };

        setTimeout(() => {
            if (notification.parentNode) {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.remove();
                    }
                }, 300);
            }
        }, 5000);

    } catch (error) {
        console.error("❌ Lỗi show in-app notification:", error);
    }
}

// ======================================================= 
// ✅ HÀM XỬ LÝ TIN NHẮN ĐẾN
// ======================================================= 
function showDesktopNotification(msg) {
    if (!isSettingEnabled('desktop_notify', true)) return;
    if (document.visibilityState === 'visible' && document.hasFocus()) return;
    if (!("Notification" in window) || Notification.permission !== 'granted') return;

    try {
        const senderName = repairMojibake(msg.senderName || selectedFriendName || (getCurrentLanguage() === 'vi' ? '\u0041i \u0111\u00f3' : 'Someone'));
        const body = isSettingEnabled('message_preview', true)
            ? repairMojibake(msg.text || msg.content || (getCurrentLanguage() === 'vi' ? '\u0042\u1ea1n c\u00f3 tin nh\u1eafn m\u1edbi.' : 'You have a new message.'))
            : (getCurrentLanguage() === 'vi' ? '\u0042\u1ea1n c\u00f3 tin nh\u1eafn m\u1edbi.' : 'You have a new message.');
        const notification = new Notification(senderName, {
            body,
            tag: `chat-${msg.sender || 'unknown'}`,
            renotify: true
        });
        notification.onclick = () => {
            window.focus();
            const event = new CustomEvent('friendSelected', {
                detail: {
                    uid: msg.sender,
                    name: senderName
                }
            });
            window.dispatchEvent(event);
            notification.close();
        };
        setTimeout(() => notification.close(), 5000);
    } catch (error) {
        console.error('Desktop notification error:', error);
    }
}

async function handleIncomingMessage(msg) {
    if (isDisabledChatbotUid(msg?.sender) || isDisabledChatbotUid(msg?.receiver) || isDisabledChatbotUid(msg?.from) || isDisabledChatbotUid(msg?.to)) {
        return;
    }
    if (processedMessageIds.has(msg.key) || processedMessageIds.has(msg.firestoreId) || processedMessageIds.has(msg.messageId)) {
        console.log("📌 Tin nhắn đã xử lý, bỏ qua");
        return;
    }

    console.log("📩 Nhận tin nhắn mới:", msg);

    const isForMe = msg.receiver === currentUserUid;
    const isFromMe = msg.sender === currentUserUid;
    const isChattingWithSender = (selectedFriendUid === msg.sender);
    const friendUid = isFromMe ? msg.receiver : msg.sender;

    if (msg.key) processedMessageIds.add(msg.key);
    if (msg.firestoreId) processedMessageIds.add(msg.firestoreId);
    if (msg.messageId) processedMessageIds.add(msg.messageId);

    if (isForMe && !isFromMe) {
        if (!isChattingWithSender) {
            playNotificationSound();

            const currentUnread = unreadCounts[msg.sender] || 0;
            const newUnread = await updateUnreadCount(msg.sender, 'set', currentUnread + 1);

            showDesktopNotification(msg);
            showInAppNotification(msg);
            emitNewMessageForFriend(friendUid, {
                text: msg.text || msg.content || "",
                rawText: msg.rawText || msg.text || msg.content || "",
                type: msg.type || "text",
                timestamp: msg.timestamp || Date.now(),
                sender: msg.sender
            }, newUnread);
        }
    }

    emitLastMessageUpdated(friendUid, {
        text: msg.text || msg.content || msg.fileName || "",
        rawText: msg.rawText || msg.text || msg.content || msg.fileName || "",
        type: msg.type || "text",
        timestamp: msg.timestamp || Date.now(),
        sender: msg.sender
    });

    if (!activeMessagesUnsubscribe && selectedFriendUid && (selectedFriendUid === msg.sender || selectedFriendUid === msg.receiver)) {
        renderMessage(msg);

        if (emptyChatState) emptyChatState.style.display = 'none';
        if (messagesDiv) scrollToBottomIfAllowed();
    }
}

// ======================================================= 
// ✅ HÀM CẬP NHẬT UNREAD COUNT
// ======================================================= 
async function updateUnreadCount(friendUid, action = 'increment', value = 0) {
    if (!friendUid || !currentUserUid) return 0;

    try {
        if (Object.keys(unreadCounts).length === 0) {
            const stored = localStorage.getItem(`unread_${currentUserUid}`);
            unreadCounts = stored ? JSON.parse(stored) : {};
        }

        if (!unreadCounts[friendUid]) unreadCounts[friendUid] = 0;

        let newCount = unreadCounts[friendUid];

        switch (action) {
            case 'increment':
                newCount++;
                break;
            case 'reset':
                newCount = 0;
                break;
            case 'decrement':
                if (newCount > 0) newCount--;
                break;
            case 'set':
                newCount = value;
                break;
        }

        unreadCounts[friendUid] = newCount;

        localStorage.setItem(`unread_${currentUserUid}`, JSON.stringify(unreadCounts));

        console.log(`🔢 Unread count [${friendUid}]: ${newCount}`);

        const event = new CustomEvent('unreadCountUpdated', {
            detail: {
                friendUid,
                count: newCount,
                action: action
            }
        });
        window.dispatchEvent(event);

        return newCount;
    } catch (error) {
        console.error("❌ Lỗi update unread count:", error);
        return 0;
    }
}

// ======================================================= 
// ✅ LƯU TIN NHẮN VÀO FIRESTORE (KHÔNG CHATBOT)
// ======================================================= 
async function saveMessageToFirestore(messageData) {
    // 🔴 KHÔNG lưu tin nhắn chatbot vào Firestore
    if (messageData.receiver === CHATBOT_UID || messageData.sender === CHATBOT_UID) {
        console.log('🤖 Tin nhắn chatbot - KHÔNG lưu Firestore');
        return null;
    }

    if (!currentUserUid || !messageData.sender || !messageData.receiver) {
        console.error("❌ Thiếu thông tin người gửi/người nhận");
        return null;
    }

    try {
        const chatId = [messageData.sender, messageData.receiver].sort().join("_");
        const messagesRef = collection(db, "chats", chatId, "messages");

        const firestoreMessage = {
            from: messageData.sender,
            to: messageData.receiver,
            content: messageData.text || "",
            type: messageData.type || "text",
            timestamp: serverTimestamp(),
            status: "sent",
            replyTo: messageData.reply ? {
                messageId: messageData.reply.key,
                content: messageData.reply.text,
                type: messageData.reply.type
            } : null,
            mediaURL: messageData.mediaURL || null,
            createdAt: Date.now(),
            localMsgId: messageData.localMsgId || null,
            messageId: messageData.messageId || null
        };

        const docRef = await addDoc(messagesRef, firestoreMessage);
        console.log("✅ Tin nhắn đã lưu vào Firestore:", docRef.id);
        return docRef.id;
    } catch (error) {
        console.error("❌ Lỗi lưu tin nhắn vào Firestore:", error);
        return null;
    }
}

// ======================================================= 
// ✅ HÀM ĐÁNH DẤU TIN NHẮN ĐÃ XEM
// ======================================================= 
async function markMessageAsSeen(msg) {
    if (!msg.key || !convId) return;

    try {
        console.log("👀 Đánh dấu đã xem tin nhắn:", msg.key);

        if (msg.firestoreId) {
            try {
                const messageRef = doc(db, "chats", convId, "messages", msg.firestoreId);
                await updateDoc(messageRef, {
                    status: "seen",
                    seenAt: serverTimestamp()
                });
                console.log(`✅ Đã đánh dấu đã xem Firestore: ${msg.firestoreId}`);
            } catch (firestoreError) {
                console.error("❌ Lỗi cập nhật Firestore:", firestoreError);
            }
        }

        const box = document.querySelector(`[data-key='${msg.key}']`);
        if (box) {
            const statusDiv = box.querySelector(".status-message");
            if (statusDiv && msg.sender === currentUserUid) {
                statusDiv.textContent = uiText('Đã xem', 'Seen');
                statusDiv.className = "status-message seen";
                statusDiv.style.animation = 'none';
                void statusDiv.offsetWidth;
                statusDiv.style.animation = 'seenStatus 0.5s ease-out';
            }
        }

        if (socket && msg.sender !== currentUserUid) {
            socket.emit('message_seen', {
                messageId: msg.key,
                sender: msg.sender,
                receiver: currentUserUid,
                convId: convId
            });
        }

    } catch (error) {
        console.error("❌ Lỗi đánh dấu đã xem:", error);
    }
}

// =======================================================
// ✅ CHATBOT MESSAGE HANDLER
// =======================================================
// Cập nhật hàm handleChatbotMessage
async function handleChatbotMessage(text, options = {}) {
    const { skipUserBox = false, skipSave = false, confirmedPlan = null } = options;
    const stopBtn = document.getElementById('stopBtn');
    
    if (isStreamingActive && !botStreamingPaused) {
        showToast(uiText('Vui lòng đợi AI phản hồi xong.', 'Please wait until the AI response is complete.'), 'warning');
        return;
    }

    stopVoiceRecognition(true, true);

    if (msgInput) {
        msgInput.value = "";
        msgInput.style.height = 'auto'; // Reset textarea height
        const scrollBtns = document.querySelector('.textarea-scroll-btns');
        if (scrollBtns) scrollBtns.classList.remove('visible');
        msgInput.disabled = true;
        msgInput.placeholder = chatPack().typing;
    }
    if (sendBtn) sendBtn.disabled = true;
    if (stopBtn) stopBtn.style.display = 'flex';

    if (!skipUserBox && !confirmedPlan) {
        const userBox = document.createElement("div");
        userBox.id = `user_${Date.now()}`;
        userBox.className = "msg-box me-box";
        userBox.innerHTML = `
            <div class="msg me">
                <div class="msg-actions">
                    <button class="action-btn edit-btn" title="Edit"><i class="fas fa-edit"></i></button>
                    <button class="action-btn copy-btn" title="${uiText('Sao chép', 'Copy')}"><i class="fas fa-copy"></i></button>
                </div>
                <div class="msg-text">${renderPlainTextContent(text)}</div>
            </div>
            <div class="time">${formatTime(Date.now())}</div>
        `;
        messagesDiv.appendChild(userBox);
        scrollToBottomIfAllowed(true);
    }

    if (!skipSave && !confirmedPlan) saveUserMessageToSession(text);
    
    if (confirmedPlan) {
        updateBotStatus(chatText('researchRunning'));
    }

    const historySource = chatbotSession.messages.filter((msg) => !msg.excludeFromHistory);
    const history = historySource
        .slice(-11, -1)
        .map((msg) => ({
            role: msg.sender === CHATBOT_UID ? 'assistant' : 'user',
            content: msg.prompt || getOriginalMessageText(msg)
        }))
        .filter((msg) => !!msg.content);

    resetBotStreamingState();
    liveSearchPreviewSources = [];
    showBotTypingIndicator(); // Always show animation while waiting
    isStreamingActive = true;
    let botMessageId = null;
    let firstTokenReceived = false;
    let firstTokenWatchdog = null;

    try {
        currentStreamController = new AbortController();
        firstTokenWatchdog = setTimeout(() => {
            if (!firstTokenReceived && isStreamingActive) {
                updateBotStatus(
                    uiText('Hệ thống vẫn đang xử lý yêu cầu...', 'Still working on your request...'),
                    { phase: 'thinking', label: uiText('Đang nghĩ', 'Thinking') }
                );
            }
        }, 4500);

        const response = await fetch(`${API_BASE_URL}/ask_stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
            body: JSON.stringify({
                question: text,
                history: history,
                user_id: currentUserUid || "guest_user",
                age_group: getEffectiveAgeGroup(),
                force_search: forceSearchFlag,
                deep_research: deepResearchFlag,
                confirmed_plan: confirmedPlan,
                final_response_only: FINAL_ONLY_CHAT_MODE,
                show_status: STREAM_STATUS_UI_ENABLED,
                show_research_plan: RESEARCH_PLAN_UI_ENABLED,
                show_internal_reasoning: false
            }),
            signal: currentStreamController.signal
        });

        forceSearchFlag = false;
        const sb = document.getElementById('searchBtn');
        if (sb) sb.classList.remove('active');
        
        if (!response.ok) {
            clearTimeout(firstTokenWatchdog);
            throw new Error(`HTTP Error ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let botResponse = "";
        let isFirstToken = true;

        while (true) {
            if (botStreamingPaused) {
                reader.cancel();
                break;
            }
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const events = chunk.split('\n\n');
            for (const event of events) {
                if (event.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(event.substring(6));
                        const isSourceEvent = data.event === 'source_candidate' || data.event === 'source_accepted';
                        if (STREAM_STATUS_UI_ENABLED && !isSourceEvent && !shouldIgnoreLegacyStatusPayload(data) && (data.status || data.label || data.detail)) {
                            updateBotStatus(data.status || '', data);
                        }

                        if (data.is_limit_reached) {
                            showLimitNotification(data.reset_time);
                            reader.cancel();
                            return;
                        }

                        if (RESEARCH_PLAN_UI_ENABLED && data.research_plan) {
                            showResearchPlan(data.research_plan, text);
                            reader.cancel();
                            return;
                        }

                        if (STREAM_STATUS_UI_ENABLED && !data.status && data.query && (data.event === 'query_started' || data.event === 'query_planned')) {
                            updateBotStatus('', data);
                        }

                        if (data.source) {
                            updateLiveSourcePreview(data.source, data.event || 'candidate');
                        }

                        if (data.token) {
                            firstTokenReceived = true;
                            clearTimeout(firstTokenWatchdog);
                            if (isFirstToken) {
                                isFirstToken = false;
                                ensureBotTypingIndicatorIsRemoved();
                                botMessageId = createBotMessageStreaming("", {}, true);
                                saveBotMessageToSession("", botMessageId);
                            }
                            botResponse += data.token;
                            const streamingElement = document.getElementById(`streaming_${botMessageId}`);
                            if (streamingElement) {
                                streamingElement.innerHTML = renderBotMarkdown(botResponse);
                                scrollToBottomIfAllowed();
                            }
                            updateCurrentBotMessageInSession(botMessageId, botResponse);
                        }

                        if (data.complete) {
                            if (data.sources && data.sources.length > 0) {
                                updateMessageSourcesInSession(botMessageId, data.sources);
                                showSourcePill(botMessageId, data.sources);
                            }
                        }
                    } catch (e) {
                        console.error("Error parsing SSE data:", e);
                    }
                }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Stream aborted by user');
        } else {
            console.error(error);
            const fallbackMessage = /HTTP Error (\d+)/.test(String(error?.message || ''))
                ? getChatbotUnavailableMessage(Number(String(error.message).match(/HTTP Error (\d+)/)?.[1] || 0))
                : getChatbotUnavailableMessage();
            if (!firstTokenReceived) {
                appendBotSystemMessage(fallbackMessage, { isError: true });
            }
        }
    } finally {
        if (firstTokenWatchdog) {
            clearTimeout(firstTokenWatchdog);
            firstTokenWatchdog = null;
        }
        if (botMessageId) {
            const streamingElement = document.getElementById(`streaming_${botMessageId}`);
            if (streamingElement) {
                streamingElement.classList.remove('streaming-text');
                streamingElement.closest('.msg.bot')?.classList.remove('is-streaming');
                const resp = chatbotSession.messages.find(m => m.id === botMessageId)?.text || "";
                streamingElement.innerHTML = renderBotMarkdown(resp);
                const msg = chatbotSession.messages.find(m => m.id === botMessageId);
                if (msg && msg.sources) showSourcePill(botMessageId, msg.sources);
            }
        }
        isStreamingActive = false;
        if (msgInput) {
            msgInput.disabled = false;
            msgInput.placeholder = chatText('placeholder');
        }
        if (sendBtn) sendBtn.disabled = false;
        if (stopBtn) stopBtn.style.display = 'none';
        resetBotStreamingState();
        liveSearchPreviewSources = [];
        ensureBotTypingIndicatorIsRemoved();
        currentStreamController = null;
    }
}

function updateMessageSourcesInSession(messageId, sources) {
    const msg = chatbotSession.messages.find(m => m.id === messageId);
    if (msg) {
        msg.sources = sources;
        try {
            const sessionKey = `chatbot_session_${currentUserUid}`;
            const sessionData = {
                messages: chatbotSession.messages.slice(-50),
                lastUpdated: Date.now(),
                sessionId: chatbotSession.sessionId,
                isActive: true
            };
            sessionStorage.setItem(sessionKey, JSON.stringify(sessionData));
        } catch(e) {
            console.error('Error saving sources to session:', e);
        }
    }
}

function showSourcePill(messageId, sources) {
    const streamingElement = document.getElementById(`streaming_${messageId}`);
    if (!streamingElement) return;
    const botBox = streamingElement.closest('.msg.bot');
    if (!botBox) return;
    const oldPill = botBox.querySelector('.source-pill');
    if (oldPill) oldPill.remove();
    const pill = document.createElement('div');
    pill.className = 'source-pill';
    pill.innerHTML = `<i class="fas fa-link"></i> ${sources.length} ${uiText('nguồn', 'sources')}`;
    pill.onclick = (e) => {
        e.stopPropagation();
        openSourcesSidebar(sources);
    };
    botBox.appendChild(pill);
}

function openSourcesSidebar(sources) {
    const sidebar = document.getElementById('sourcesSidebar');
    const body = document.getElementById('sourcesBody');
    const headerTitle = sidebar ? sidebar.querySelector('.sources-header h3') : null;
    if (!sidebar || !body) return;

    if (headerTitle) {
        headerTitle.innerHTML = `<i class="fas fa-book-open"></i> ${sources.length} ${uiText('nguồn trích dẫn', 'cited sources')}`;
    }

    body.innerHTML = '';
    sources.forEach(source => {
        const item = document.createElement('a');
        item.className = 'source-item';
        item.href = source.url;
        item.target = '_blank';
        item.rel = 'noopener noreferrer';
        let domain = "";
        try {
            domain = new URL(source.url).hostname;
        } catch(e) { domain = source.url; }
        
        item.innerHTML = `
            <span class="source-item-title">${escapeHtml(source.title || domain)}</span>
            <span class="source-item-url">${escapeHtml(domain)}</span>
            <span class="source-item-snippet">${escapeHtml(source.snippet || '')}</span>
        `;
        body.appendChild(item);
    });
    sidebar.classList.add('active');
}

function closeSourcesSidebar() {
    const sidebar = document.getElementById('sourcesSidebar');
    if (sidebar) sidebar.classList.remove('active');
}

function showGroundednessBadge(messageId, score) {
    const streamingElement = document.getElementById(`streaming_${messageId}`);
    if (!streamingElement) return;
    const botBox = streamingElement.closest('.msg.bot');
    if (!botBox) return;
    const oldBadge = botBox.querySelector('.groundedness-badge');
    if (oldBadge) oldBadge.remove();
    const percentage = Math.round(score * 100);
    const color = percentage > 80 ? '#00ff88' : (percentage > 50 ? '#ffc107' : '#ff4444');
    const badge = document.createElement('div');
    badge.className = 'groundedness-badge';
    badge.innerHTML = `<i class="fas fa-shield-alt"></i> <span>${uiText('Độ tin cậy', 'Confidence')}: ${percentage}%</span>`;
    badge.style.color = color;
    botBox.appendChild(badge);
}

function initLimitUI() {
    if (!document.getElementById('limitNotification')) {
        const notif = document.createElement('div');
        notif.id = 'limitNotification';
        notif.innerHTML = `<div class="limit-icon">\u26A0\uFE0F</div><div class="limit-title">${uiText('Đã đạt giới hạn tin nhắn', 'Message limit reached')}</div><div class="limit-timer" id="limitTimer">--:--:--</div>`;
        document.body.appendChild(notif);
    }
}

function showLimitNotification(resetTimeStr) {
    const notif = document.getElementById('limitNotification');
    const timer = document.getElementById('limitTimer');
    if (notif && timer && isSettingEnabled('quota_warn', true)) {
        timer.textContent = resetTimeStr;
        notif.classList.add('visible');
    } else if (notif) {
        notif.classList.remove('visible');
    }
    if (msgInput) {
        msgInput.disabled = true;
        msgInput.placeholder = uiText('Đã hết lượt tin nhắn...', 'No message quota left...');
    }
}

function setupInputLimitListener() {
    if (!msgInput) return;
    msgInput.addEventListener('input', function() {
        const text = this.value.trim();
        const wordCount = text ? text.split(/\s+/).length : 0;
        if (wordCount > 500) {
            this.classList.add('limit-exceeded');
            if (sendBtn) sendBtn.disabled = true;
        } else {
            this.classList.remove('limit-exceeded');
            if (!isStreamingActive && sendBtn) sendBtn.disabled = false;
        }
    });

}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initLimitUI();
    setupInputLimitListener();
});

// Also run immediately in case DOM is already ready
initLimitUI();
setupInputLimitListener();

function initializeDOMElements() {
    console.log('✅ Skemi 1.0 - Initializing DOM Elements...');
    // initModelSelector đã được gọi trong DOMContentLoaded

    // Get DOM elements
    emojiBtn = document.getElementById("emojiBtn");
    attachBtn = document.getElementById("attachBtn");
    voiceBtn = document.getElementById("voiceBtn");
    fileInput = document.getElementById("fileInput");
    attachmentPreview = document.getElementById("attachmentPreview");
    attachmentThumb = document.getElementById("attachmentThumb");
    attachmentName = document.getElementById("attachmentName");
    attachmentSize = document.getElementById("attachmentSize");
    removeAttachmentBtn = document.getElementById("removeAttachmentBtn");
    muteBtn = document.getElementById("muteBtn");
    callAnimationContainer = document.getElementById("ringingAnimation");
    sendBtn = document.getElementById("sendBtn");
    videoToggleBtn = document.getElementById("videoToggleBtn");
    callArea = document.getElementById("callArea");
    callTimer = document.getElementById("callTimer");
    declineCallBtn = document.getElementById("declineCallBtn");
    acceptCallBtn = document.getElementById("acceptCallBtn");
    localVideo = document.getElementById("localVideo");
    remoteVideo = document.getElementById("remoteVideo");
    endCallBtn = document.getElementById("endCallBtn");
    voiceCallBtn = document.getElementById("voiceCallBtn");
    videoCallBtn = document.getElementById("videoCallBtn");
    incomingCallCard = document.getElementById("incomingCallCard");
    headerAudioBtn = document.getElementById("headerAudioBtn");
    switchBtn = document.getElementById("switchBtn");
    speakerBtn = document.getElementById("speakerBtn");
    backBtn = document.getElementById("backBtn");
    localAvatar = document.getElementById("localAvatar");
    remoteAvatar = document.getElementById("remoteAvatar");
    
    // Sources Sidebar
    const closeSourcesBtn = document.getElementById('closeSourcesBtn');
    if (closeSourcesBtn) {
        closeSourcesBtn.onclick = closeSourcesSidebar;
    }

    // Close sidebar when clicking outside on mobile or on messages
    if (messagesDiv) {
        messagesDiv.addEventListener('click', closeSourcesSidebar);
    }
    ensureAnalysisModeToggle();
    // ensureQuickEmojiRail(); // Disabled according to user feedback for a cleaner UI
    initVoiceRecognition();

    // --- NEW/REFACTORED Event Listeners ---
    if (sendBtn) {
        // Use the new sendMessage function
        sendBtn.addEventListener("click", () => {
            if (pendingAttachment) {
                sendPendingAttachment();
                return;
            }

            if (selectedFriendUid === CHATBOT_UID) {
                const text = msgInput ? msgInput.value.trim() : '';
                if (text) handleChatbotMessage(text);
                return;
            }

            sendMessage({ type: 'text' });
        });
    }

    // Search toggle button (force web search for next message)
    const searchBtnEl = document.getElementById('searchBtn');
    if (searchBtnEl) {
        searchBtnEl.addEventListener('click', (e) => {
            e.preventDefault();
            forceSearchFlag = !forceSearchFlag;
            searchBtnEl.classList.toggle('active', forceSearchFlag);
            showToast(
                forceSearchFlag
                    ? uiText('Đã bật tìm kiếm cho tin nhắn kế tiếp.', 'Search is enabled for the next message.')
                    : uiText('Đã tắt tìm kiếm cho tin nhắn kế tiếp.', 'Search is disabled for the next message.'),
                'info'
            );
        });
    }

    // Deep Research toggle button (comprehensive search with multiple queries)
    const deepResearchBtnEl = document.getElementById('deepResearchBtn');
    if (deepResearchBtnEl) {
        deepResearchBtnEl.addEventListener('click', (e) => {
            e.preventDefault();
            deepResearchFlag = !deepResearchFlag;
            deepResearchBtnEl.classList.toggle('active', deepResearchFlag);
            showToast(deepResearchFlag ? chatPack().deepResearchOn : chatPack().deepResearchOff, 'info');
        });
    }

    // Trong initializeDOMElements(), sửa phần này:
    if (msgInput) {
        msgInput.addEventListener("keydown", async (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                const text = msgInput.value.trim();
                const words = text ? text.split(/\s+/).length : 0;
                
                if (words > MAX_PROMPT_WORDS && selectedFriendUid === CHATBOT_UID) {
                    showToast(
                        uiText(
                            `Tin nhắn quá dài (${words}/${MAX_PROMPT_WORDS} từ). Vui lòng rút ngắn lại.`,
                            `Message is too long (${words}/${MAX_PROMPT_WORDS} words). Please shorten it.`
                        ),
                        'error'
                    );
                    return;
                }

                if (selectedFriendUid === CHATBOT_UID) {
                    if (pendingAttachment) {
                        sendPendingAttachment();
                    } else {
                        await handleChatbotMessage(text);
                    }
                } else {
                    if (pendingAttachment) {
                        sendPendingAttachment();
                    } else {
                        await sendMessage({ type: 'text' });
                    }
                }
            }
        });

        // Paste image/file directly into input
        msgInput.addEventListener("paste", (e) => {
            const items = e.clipboardData?.items || [];
            for (const item of items) {
                if (item.kind === "file") {
                    const file = item.getAsFile();
                    if (!file) continue;
                    if (file.size > MAX_FILE_BYTES_CLIENT) {
                        showToast(uiText('File quá lớn (tối đa 50MB)', 'File is too large (max 50MB)'), 'error');
                        return;
                    }
                    pendingAttachment = file;
                    showAttachmentPreview(file);
                    e.preventDefault();
                    return;
                }
            }
        });

        let typingTimer;

        msgInput.addEventListener("input", () => {
            clearTimeout(typingTimer);
            typingTimer = setTimeout(() => handleTyping(), 500);
        });
    }

    // Emoji button (custom picker: recent + packs)
    if (emojiBtn) {
        const emojiPacks = {
            vibe: ['\u{1F600}', '\u{1F602}', '\u{1F970}', '\u{1F60E}', '\u{1F914}', '\u{1F973}', '\u{1F64C}', '\u{1F525}'],
            love: ['\u2764\uFE0F', '\u{1F49E}', '\u{1F496}', '\u{1F495}', '\u{1F60D}', '\u{1F618}', '\u{1F97A}', '\u{1F64F}'],
            react: ['\u{1F44D}', '\u{1F44E}', '\u{1F44F}', '\u{1F44C}', '\u{1F91D}', '\u{1F389}', '\u{1F631}', '\u{1F62D}']
        };
        let activePack = 'vibe';
        let recentEmojis = ['\u{1F600}', '\u2764\uFE0F', '\u{1F44D}', '\u{1F389}'];

        const insertEmoji = (emoji) => {
            if (!msgInput) return;
            const before = msgInput.value || '';
            const start = msgInput.selectionStart ?? before.length;
            const end = msgInput.selectionEnd ?? before.length;
            msgInput.value = before.slice(0, start) + emoji + before.slice(end);
            msgInput.dispatchEvent(new Event('input', { bubbles: true }));
            msgInput.focus();
            const caret = start + emoji.length;
            msgInput.setSelectionRange(caret, caret);
            recentEmojis = [emoji, ...recentEmojis.filter((x) => x !== emoji)].slice(0, 6);
        };

        const renderEmojiGrid = (container, emojis) => {
            container.innerHTML = '';
            emojis.forEach((emoji) => {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = emoji;
                button.className = 'emoji-picker-button';
                button.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    insertEmoji(emoji);
                });
                container.appendChild(button);
            });
        };

        emojiBtn.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();

            const existing = document.querySelector('.emoji-picker');
            if (existing) {
                existing.remove();
                return;
            }

            const emojiPicker = document.createElement('div');
            emojiPicker.className = 'emoji-picker';

            const recentRow = document.createElement('div');
            recentRow.className = 'emoji-recent';
            renderEmojiGrid(recentRow, recentEmojis);
            emojiPicker.appendChild(recentRow);

            const tabRow = document.createElement('div');
            tabRow.className = 'emoji-pack-tabs';
            const tabs = [
                { id: 'vibe', icon: '\u{1F600}' },
                { id: 'love', icon: '\u2764\uFE0F' },
                { id: 'react', icon: '\u{1F44D}' }
            ];
            tabs.forEach((tab) => {
                const t = document.createElement('button');
                t.type = 'button';
                t.className = `emoji-pack-btn ${activePack === tab.id ? 'active' : ''}`;
                t.textContent = tab.icon;
                t.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    activePack = tab.id;
                    tabRow.querySelectorAll('.emoji-pack-btn').forEach((b) => b.classList.remove('active'));
                    t.classList.add('active');
                    renderEmojiGrid(grid, emojiPacks[activePack] || []);
                });
                tabRow.appendChild(t);
            });
            emojiPicker.appendChild(tabRow);

            const grid = document.createElement('div');
            grid.className = 'emoji-grid';
            renderEmojiGrid(grid, emojiPacks[activePack]);
            emojiPicker.appendChild(grid);

            if (chatInputArea) {
                chatInputArea.appendChild(emojiPicker);
            }
        });
    }

    // Close emoji picker when clicking outside
    document.addEventListener('click', (event) => {
        const picker = document.querySelector('.emoji-picker');
        if (picker && !picker.contains(event.target) && (!emojiBtn || !emojiBtn.contains(event.target))) {
            picker.remove();
        }
    });

    // Attach file button
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileUpload);
    }

    if (removeAttachmentBtn) {
        removeAttachmentBtn.addEventListener('click', () => resetPendingAttachment());
    }

    // Drag & drop files into input area
    if (chatInputArea) {
        chatInputArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            chatInputArea.classList.add('drag-over');
        });
        chatInputArea.addEventListener('dragleave', (e) => {
            if (!chatInputArea.contains(e.relatedTarget)) {
                chatInputArea.classList.remove('drag-over');
            }
        });
        chatInputArea.addEventListener('drop', (e) => {
            e.preventDefault();
            chatInputArea.classList.remove('drag-over');
            const file = e.dataTransfer?.files?.[0];
            if (!file) return;
            if (file.size > MAX_FILE_BYTES_CLIENT) {
                showToast(uiText('File quá lớn (tối đa 50MB)', 'File is too large (max 50MB)'), 'error');
                return;
            }
            pendingAttachment = file;
            showAttachmentPreview(file);
        });
    }

    // --- OTHER UI Event Listeners (unchanged) ---
    if (voiceCallBtn) voiceCallBtn.addEventListener('click', () => startCall('voice'));
    if (videoCallBtn) videoCallBtn.addEventListener('click', () => startCall('video'));
    if (endCallBtn) endCallBtn.addEventListener('click', () => endCall());
    if (backBtn) backBtn.addEventListener('click', () => { if (callArea) callArea.classList.remove('active'); });
    if (acceptCallBtn) acceptCallBtn.addEventListener('click', () => answerCall(true));
    if (declineCallBtn) declineCallBtn.addEventListener('click', () => answerCall(false));
    if (muteBtn) muteBtn.addEventListener('click', toggleMic);
    if (videoToggleBtn) videoToggleBtn.addEventListener('click', toggleCamera);
    if (switchBtn) switchBtn.addEventListener('click', switchCamera);
    if (speakerBtn) speakerBtn.addEventListener('click', toggleSpeaker);
    bindThemeToggleForAllUsers();
    if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
    if (retryButton) retryButton.addEventListener('click', () => location.reload());
    if (continueButton) continueButton.addEventListener('click', completeLoading);

    // Greeting buttons (👋, 😊, etc.)
    const greetingBtns = document.querySelectorAll('.greeting-btn');
    greetingBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            const text = btn.getAttribute('data-text');
            if (text && selectedFriendUid === CHATBOT_UID) {
                await handleChatbotMessage(text);
            }
        });
    });

    console.log('✅ All DOM elements and event listeners initialized.');
    updateChatUIState();
    resetPendingAttachment();
}


// =======================================================
// ✅ HÀM CLEANUP ĐỂ DỌN DẸP INTERVALS
// =======================================================
function cleanupIntervals() {
    console.log('🧹 Cleaning up intervals...');

    // Clear watchdog interval
    if (watchdogInterval) {
        clearInterval(watchdogInterval);
        watchdogInterval = null;
        console.log('✅ Cleared watchdog interval');
    }

    // Clear debug intervals
    if (window.debugIntervals) {
        window.debugIntervals.forEach(interval => {
            clearInterval(interval);
        });
        window.debugIntervals = [];
        console.log('✅ Cleared debug intervals');
    }

    // Clear bot typing timeout
    if (botTypingTimeout) {
        clearTimeout(botTypingTimeout);
        botTypingTimeout = null;
    }

    // Clear call timeout
    if (callTimeout) {
        clearTimeout(callTimeout);
        callTimeout = null;
    }

    if (selectedFriendStatusTimer) {
        clearInterval(selectedFriendStatusTimer);
        selectedFriendStatusTimer = null;
    }

    if (typingStatusTimer) {
        clearTimeout(typingStatusTimer);
        typingStatusTimer = null;
    }

    if (activeMessagesUnsubscribe) {
        activeMessagesUnsubscribe();
        activeMessagesUnsubscribe = null;
    }
}


// =======================================================
// ✅ THÊM DEBUG EVENT LISTENERS
// =======================================================
function addDebugEventListeners() {
    console.log('🔍 Adding debug event listeners...');

    // Log khi state thay đổi
    const originalStates = {
        isBotTyping: isBotTyping,
        isStreamingActive: isStreamingActive,
        botStreamingPaused: botStreamingPaused
    };

    const stateCheckInterval = setInterval(() => {
        if (originalStates.isBotTyping !== isBotTyping) {
            console.log(`🔄 isBotTyping thay đổi: ${originalStates.isBotTyping} -> ${isBotTyping}`);
            originalStates.isBotTyping = isBotTyping;
        }
        if (originalStates.isStreamingActive !== isStreamingActive) {
            console.log(`🔄 isStreamingActive thay đổi: ${originalStates.isStreamingActive} -> ${isStreamingActive}`);
            originalStates.isStreamingActive = isStreamingActive;
        }
        if (originalStates.botStreamingPaused !== botStreamingPaused) {
            console.log(`🔄 botStreamingPaused thay đổi: ${originalStates.botStreamingPaused} -> ${botStreamingPaused}`);
            originalStates.botStreamingPaused = botStreamingPaused;
        }
    }, 1000);

    // Thêm nút debug manual (Ctrl+D)
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'd') {
            console.log('=== DEBUG INFO ===');
            console.log('isBotTyping:', isBotTyping);
            console.log('isStreamingActive:', isStreamingActive);
            console.log('botStreamingPaused:', botStreamingPaused);
            console.log('botTypingIndicator exists:', !!botTypingIndicator);
            console.log('botTypingTimeout exists:', !!botTypingTimeout);

            const indicatorInDOM = document.getElementById('botTypingIndicator');
            console.log('Indicator in DOM:', !!indicatorInDOM);

            // Force remove if stuck
            if (indicatorInDOM) {
                console.log('🛠️ Force removing stuck indicator...');
                indicatorInDOM.remove();
                isBotTyping = false;
                botTypingIndicator = null;
            }
        }
    });

    // Lưu interval để có thể clear nếu cần
    window.debugIntervals = window.debugIntervals || [];
    window.debugIntervals.push(stateCheckInterval);
}

// ======================================================= 
// ✅ TYPING INDICATOR FUNCTIONS
// ======================================================= 
function handleTyping() {
    if (!selectedFriendUid || isCurrentUserBlockedByFriend) return;

    const now = Date.now();
    if (now - lastTypingTime > 1000) {
        sendTypingStatus(true);
        lastTypingTime = now;
    }

    if (typingTimeout) clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        sendTypingStatus(false);
    }, 5000);
}

function sendTypingStatus(isTyping) {
    if (socket && selectedFriendUid && currentUserUid) {
        socket.emit('typing', {
            sender: currentUserUid,
            receiver: selectedFriendUid,
            isTyping: isTyping,
            senderName: currentUserName,
            timestamp: Date.now()
        });
        console.log(`⌨️ Gửi typing status: ${isTyping ? 'đang gõ' : 'dừng gõ'}`);
    }
}

// ======================================================= 
// ✅ FILE ATTACHMENT (PREVIEW IN INPUT, SEND ON CLICK)
// ======================================================= 

function resetPendingAttachment() {
    if (pendingAttachmentUrl) {
        URL.revokeObjectURL(pendingAttachmentUrl);
        pendingAttachmentUrl = null;
    }
    pendingAttachment = null;
    if (attachmentPreview) attachmentPreview.style.display = 'none';
    if (attachmentThumb) attachmentThumb.innerHTML = '<i class="fas fa-file"></i>';
    if (attachmentName) attachmentName.textContent = '';
    if (attachmentSize) attachmentSize.textContent = '';
    if (fileInput) fileInput.value = '';
}

function showAttachmentPreview(file) {
    if (!attachmentPreview || !attachmentThumb || !attachmentName || !attachmentSize) return;

    attachmentName.textContent = file.name;
    attachmentSize.textContent = `${(file.size / 1024).toFixed(1)} KB`;

    if (pendingAttachmentUrl) {
        URL.revokeObjectURL(pendingAttachmentUrl);
        pendingAttachmentUrl = null;
    }

    if (file.type.startsWith('image/')) {
        pendingAttachmentUrl = URL.createObjectURL(file);
        attachmentThumb.innerHTML = `<img src="${pendingAttachmentUrl}" alt="Preview">`;
    } else {
        attachmentThumb.innerHTML = '<i class="fas fa-file"></i>';
    }

    attachmentPreview.style.display = 'flex';
}

function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file || !selectedFriendUid) {
        if (!selectedFriendUid) {
            showToast(uiText('Vui lòng chọn bạn bè trước khi gửi tệp', 'Please choose a friend before sending a file'), 'error');
        }
        e.target.value = '';
        return;
    }

    if (file.size > MAX_FILE_BYTES_CLIENT) {
        showToast(uiText('File quá lớn (tối đa 50MB)', 'File is too large (max 50MB)'), 'error');
        e.target.value = '';
        return;
    }

    console.log('📁 File selected:', file.name, file.type);
    pendingAttachment = file;
    showAttachmentPreview(file);
    e.target.value = '';
}

function getFileType(fileName) {
    const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'];
    const videoExtensions = ['mp4', 'webm', 'ogg', 'mov', 'avi'];
    const extension = fileName.split('.').pop().toLowerCase();

    if (imageExtensions.includes(extension)) return 'image';
    if (videoExtensions.includes(extension)) return 'video';
    return 'file';
}

function updateProgressOverlay(msgBox, percent, label = "") {
    if (!msgBox) return;
    const progressOverlay = msgBox.querySelector('.upload-progress-overlay');
    const progressBar = msgBox.querySelector('.upload-progress-bar');
    const progressText = msgBox.querySelector('.upload-progress-text');

    const safePercent = Math.max(0, Math.min(100, Math.round(percent || 0)));
    if (progressOverlay) progressOverlay.style.display = 'flex';
    if (progressBar) progressBar.style.width = safePercent + '%';
    if (progressText) {
        const cleanLabel = label ? label.replace(/\.\.\.$/, '').trim() : '';
        progressText.textContent = cleanLabel ? `${cleanLabel} ${safePercent}%` : `${safePercent}%`;
    }
}


function updateTempFileBox(tempId, downloadURL, fileType, fileName, captionText) {
    const msgBox = document.querySelector(`[data-id='${tempId}']`);
    if (!msgBox) return;

    const msgContainer = msgBox.querySelector('.msg.me');
    if (!msgContainer) return;

    let previewContent = '';
    if (fileType === 'image') {
        previewContent = `<img src="${downloadURL}" class="msg-media-preview" alt="Image preview">`;
    } else if (fileType === 'video') {
        previewContent = `<video src="${downloadURL}" controls class="msg-media-preview"></video>`;
    } else {
        previewContent = `
            <div class="file-message">
                <i class="fas fa-file"></i>
                <span>${escapeHtml(fileName || uiText('Tệp đính kèm', 'Attachment'))}</span>
                <a href="${downloadURL}" download>${uiText('Tải xuống', 'Download')}</a>
            </div>
        `;
    }
    if (captionText) {
        previewContent += `<div class="file-caption">${escapeHtml(captionText)}</div>`;
    }

    msgContainer.innerHTML = `
        ${previewContent}
        <div class="upload-progress-overlay">
            <div class="upload-progress-bar"></div>
            <span class="upload-progress-text">100%</span>
        </div>
    `;
}

async function parseFileOnServer(file, onProgress = null) {
    const makeFormData = () => {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('analysis_mode', fileAnalysisMode || 'assistant');
        return fd;
    };

    const parseStream = async () => {
        const res = await fetch(`${API_BASE_URL}/parse_file_stream`, {
            method: 'POST',
            body: makeFormData(),
            headers: { 'Accept': 'text/event-stream' }
        });

        if (!res.ok) {
            const text = await res.text();
            throw new Error(`Lỗi đọc file (${res.status}): ${text}`);
        }
        if (!res.body) {
            throw new Error('Trình duyệt không hỗ trợ streaming');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let finalData = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            let idx;
            while ((idx = buffer.indexOf('\n\n')) >= 0) {
                const raw = buffer.slice(0, idx);
                buffer = buffer.slice(idx + 2);

                const lines = raw.split('\n');
                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const jsonText = line.slice(5).trim();
                    if (!jsonText) continue;

                    let payload;
                    try {
                        payload = JSON.parse(jsonText);
                    } catch {
                        continue;
                    }

                    if (payload.progress !== undefined && onProgress) {
                        onProgress(payload.progress, payload.status);
                    }
                    if (payload.result) {
                        finalData = payload.result;
                    }
                    if (payload.error) {
                        return { error: payload.error };
                    }
                    if (payload.complete) {
                        return finalData || { error: uiText('Không nhận được kết quả', 'No result was returned') };
                    }
                }
            }
        }
        return finalData || { error: 'Kết nối bị ngắt khi đọc file' };
    };

    try {
        return await parseStream();
    } catch (e) {
        console.warn('parse_file_stream failed, fallback to parse_file:', e);
        try {
            const res = await fetch(`${API_BASE_URL}/parse_file`, {
                method: 'POST',
                body: makeFormData()
            });

            if (!res.ok) {
                const text = await res.text();
                return { error: `Lỗi đọc file (${res.status}): ${text}` };
            }

            const data = await res.json();
            return data;
        } catch (err) {
            return { error: `Lỗi kết nối khi đọc file: ${err.message || err}` };
        }
    }
}

function uploadFile(file, tempId, captionText, sessionMsgId = null, botPromptBase = null, options = {}) {
    const { skipBotResponse = false, skipUploadProgress = false } = options;
    const msgBox = document.querySelector(`[data-id='${tempId}']`);
    if (!skipUploadProgress) {
        updateProgressOverlay(msgBox, 0, 'Tải lên');
    }

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/upload`, true);

    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const progress = (e.loaded / e.total) * 100;
            if (!skipUploadProgress) {
                updateProgressOverlay(msgBox, progress, 'Tải lên');
            }
            console.log('Upload is ' + progress + '% done');
        }
    };

    xhr.onerror = () => {
        console.error("❌ Lỗi upload file");
        showToast(uiText('Upload file thất bại', 'File upload failed'), 'error');
        const statusDiv = msgBox?.querySelector(".status-message");
        if (statusDiv) {
            statusDiv.className = "status-message error";
            statusDiv.innerHTML = "❌";
        }
    };

    xhr.onload = () => {
        if (xhr.status < 200 || xhr.status >= 300) {
            xhr.onerror();
            return;
        }

        let response;
        try {
            response = JSON.parse(xhr.responseText);
        } catch (e) {
            xhr.onerror();
            return;
        }

        const downloadURL = response.url;
        const fileType = getFileType(file.name);

        updateTempFileBox(tempId, downloadURL, fileType, file.name, captionText || "");

        if (selectedFriendUid !== CHATBOT_UID) {
            sendMessage({
                type: fileType,
                text: captionText || "",
                mediaURL: downloadURL,
                fileName: file.name
            }, tempId);
        } else {
            const statusDiv = msgBox?.querySelector(".status-message");
            if (statusDiv) {
                statusDiv.className = "status-message sent";
                statusDiv.innerHTML = "✓";
            }
            const progressOverlay = msgBox?.querySelector('.upload-progress-overlay');
            if (progressOverlay) progressOverlay.style.display = 'none';
        }

        if (selectedFriendUid === CHATBOT_UID) {
            const base = botPromptBase || (() => {
                const parts = [];
                if (captionText) parts.push(`Ghi chú: ${captionText}`);
                parts.push(`Tệp: ${file.name}`);
                return parts.join('\n');
            })();
            const botPrompt = `${base}\nURL: ${downloadURL}`;

            if (sessionMsgId) {
                const msgIndex = chatbotSession.messages.findIndex(m => m.id === sessionMsgId);
                if (msgIndex !== -1) {
                    chatbotSession.messages[msgIndex].mediaURL = downloadURL;
                    chatbotSession.messages[msgIndex].fileName = file.name;
                    chatbotSession.messages[msgIndex].prompt = botPrompt;
                    saveToChatbotSession(chatbotSession.messages[msgIndex]);
                }
            }
            if (!skipBotResponse) {
                handleChatbotMessage(botPrompt, { skipUserBox: true, skipSave: true });
            }
        }
    };

    xhr.send(formData);
}

async function sendPendingAttachment() {
    if (!pendingAttachment || !selectedFriendUid) return;

    const file = pendingAttachment;
    const caption = msgInput ? msgInput.value.trim() : '';
    const tempId = `temp_${Date.now()}`;
    const fileType = file.type.startsWith('image/') ? 'image' :
        file.type.startsWith('video/') ? 'video' : 'file';

    const box = document.createElement("div");
    box.className = "msg-box me-box";
    box.dataset.id = tempId;

    const time = formatTime(Date.now());
    let previewContent = `
        <div class="file-message">
            <i class="fas fa-file"></i>
            <span>${escapeHtml(file.name)}</span>
            <div class="file-size">${(file.size / 1024).toFixed(1)} KB</div>
        </div>
    `;
    if (fileType === 'image') {
        const previewUrl = URL.createObjectURL(file);
        previewContent = `<img src="${previewUrl}" class="msg-media-preview" alt="Image preview">`;
    } else if (fileType === 'video') {
        const previewUrl = URL.createObjectURL(file);
        previewContent = `<video src="${previewUrl}" class="msg-media-preview" controls></video>`;
    }
    if (caption) {
        previewContent += `<div class="file-caption">${escapeHtml(caption)}</div>`;
    }

    box.innerHTML = `
        <div class="msg me">
            ${previewContent}
            <div class="upload-progress-overlay">
                <div class="upload-progress-bar"></div>
                <span class="upload-progress-text">0%</span>
            </div>
        </div>
        <div class="time">${time}</div>
        <div class="status-message sending">
            <div class="sending-dots"><span></span><span></span><span></span></div>
        </div>
    `;

    if (messagesDiv) {
        messagesDiv.appendChild(box);
        scrollToBottomIfAllowed(true);
    }

    if (msgInput) msgInput.value = '';
    resetPendingAttachment();

    let sessionMsgId = null;
    let botPromptBase = null;
    let skipBotResponse = false;
    if (selectedFriendUid === CHATBOT_UID) {
        showToast(uiText('Đang đọc nội dung file...', 'Reading file content...'), 'info');
        updateProgressOverlay(box, 0, uiText('Đang phân tích', 'Analyzing'));
        const parseResult = await parseFileOnServer(file, (percent, status) => {
            const label = status ? status.replace(/\.\.\.$/, '').trim() : uiText('Đang phân tích', 'Analyzing');
            updateProgressOverlay(box, percent, label);
        });
        updateProgressOverlay(box, 100, uiText('Hoàn tất', 'Complete'));
        const isImage = parseResult?.file_type === 'image';
        let extractedText = parseResult?.extracted_text || '';
        if (isImage && /(không thể ocr|could not ocr)/i.test(extractedText)) {
            extractedText = '';
        }
        const aiAnalysisRaw = parseResult?.ai_analysis || '';
        const normalizedMode = parseResult?.analysis_mode || fileAnalysisMode || 'assistant';
        const modeLabel = analysisModeLabels()[normalizedMode] || normalizedMode;
        const aiAnalysisLabel = isImage ? uiText('Phân tích ảnh (AI)', 'Image analysis (AI)') : uiText('Phân tích AI', 'AI analysis');
        const aiAnalysisBlock = aiAnalysisRaw ? `${aiAnalysisLabel}:\n${aiAnalysisRaw}` : '';
        const parseError = parseResult?.error || '';
        const truncatedNote = parseResult?.truncated ? `\n[${uiText('Lưu ý: Nội dung đã được rút gọn', 'Note: Content was shortened')}]` : '';

        if (parseError) {
            botPromptBase = `${uiText('Không đọc được file', 'Could not read file')}: ${parseError}\n${uiText('Tệp', 'File')}: ${file.name}`;
        } else {
        const hasVisionError = !!aiAnalysisRaw && /(Không có model vision|Lỗi|Error|Timeout|time out|không thể)/i.test(aiAnalysisRaw);
        const includeOcr = !(isImage && aiAnalysisRaw && !hasVisionError);
        const extractedBlock = includeOcr && extractedText
                            ? (isImage
                                ? `${uiText('Văn bản OCR', 'OCR text')}:
${extractedText}${truncatedNote}`
                                : `${uiText('Nội dung trích xuất', 'Extracted content')}:
${extractedText}${truncatedNote}`)
                            : (includeOcr && !isImage ? uiText('Không trích xuất được nội dung.', 'Could not extract content.') : null);
            botPromptBase = [
                caption ? `${uiText('Ghi chú', 'Note')}: ${caption}` : null,
                `${uiText('Tệp', 'File')}: ${file.name}`,
                `${uiText('Loại', 'Type')}: ${parseResult?.file_type || 'unknown'}`,
                `${uiText('Chế độ phân tích', 'Analysis mode')}: ${modeLabel}`,
                aiAnalysisBlock || null,
                extractedBlock || null
            ].filter(Boolean).join('\n');
        }

        sessionMsgId = saveUserMessageToSession(caption || "", {
            type: fileType,
            mediaURL: null,
            fileName: file.name,
            prompt: botPromptBase
        });

        if (botPromptBase) {
            skipBotResponse = true;
            Promise.resolve(handleChatbotMessage(botPromptBase, { skipUserBox: true, skipSave: true }))
                .catch((err) => console.error("Chatbot send error:", err));
        }
    }

    uploadFile(file, tempId, caption, sessionMsgId, botPromptBase, { skipBotResponse, skipUploadProgress: skipBotResponse });
}

// Universal Send Message Function
async function sendMessage(messageData, tempIdToUpdate = null) {
    const text = messageData.text || (msgInput ? msgInput.value.trim() : '');
    const messageType = messageData.type || 'text';
    const fileName = messageData.fileName || null;

    stopVoiceRecognition(true, true);

    if (!text && messageType === 'text') {
        showToast(uiText('Vui lòng nhập tin nhắn', 'Please enter a message'), 'error');
        return;
    }

    if (!selectedFriendUid) {
        showToast(uiText('Vui lòng chọn bạn để nhắn tin', 'Please choose a friend to message'), 'error');
        return;
    }

    // --- Chatbot Logic ---
    if (selectedFriendUid === CHATBOT_UID) {
        await handleChatbotMessage(text);
        return;
    }

    // --- Regular User Message Logic ---
    if (msgInput && messageType === 'text') {
        msgInput.value = "";
    }

    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    processedMessageIds.add(messageId);

    let box;
    if (tempIdToUpdate) {
        box = document.querySelector(`[data-id='${tempIdToUpdate}']`);
        console.log(`Updating existing message box for tempId: ${tempIdToUpdate}`);
    } else {
        box = document.createElement("div");
        box.className = "msg-box me-box";

        const time = formatTime(Date.now());
        let contentHtml = renderPlainTextContent(text);

        // This part is for new text messages, file messages are pre-rendered
        box.innerHTML = `
            <div class="msg me">${contentHtml}</div>
            <div class="time">${time}</div>
            <div class="status-message sending">
                <div class="sending-dots"><span></span><span></span><span></span></div>
            </div>
        `;

        if (messagesDiv) {
            messagesDiv.appendChild(box);
            scrollToBottomIfAllowed(true);
        }
    }
    box.dataset.id = messageId;
    box.style.opacity = "1";

    try {
        const chatId = [currentUserUid, selectedFriendUid].sort().join("_");
        const messagesRef = collection(db, "chats", chatId, "messages");

        const firestoreMsg = {
            from: currentUserUid,
            to: selectedFriendUid,
            content: text,
            type: messageType,
            mediaURL: messageData.mediaURL || null,
            timestamp: serverTimestamp(),
            status: "sent",
            messageId: messageId,
            fileName: fileName
        };

        const docRef = await addDoc(messagesRef, firestoreMsg);
        const firestoreId = docRef.id;

        box.dataset.firestoreId = firestoreId;

        const statusDiv = box.querySelector(".status-message");
        if (statusDiv) {
            statusDiv.className = "status-message sent";
            statusDiv.innerHTML = "✓";
        }
        // Hide progress bar on success
        const progressOverlay = box.querySelector('.upload-progress-overlay');
        if (progressOverlay) progressOverlay.style.display = 'none';

        if (socket.connected) {
            socket.emit('send_message', {
                ...firestoreMsg,
                timestamp: Date.now(), // Send current time for immediate display
                firestoreId: firestoreId,
            });
        }

        emitLastMessageUpdated(selectedFriendUid, {
            text: text || fileName || "",
            rawText: text || fileName || "",
            type: messageType,
            timestamp: Date.now(),
            sender: currentUserUid
        });
        emitNewMessageForFriend(selectedFriendUid, {
            text: text || fileName || "",
            rawText: text || fileName || "",
            type: messageType,
            timestamp: Date.now(),
            sender: currentUserUid
        }, 0);

        console.log(`✅ Tin nhắn ${messageType} đã gửi - ID:`, firestoreId);
        if (messageType === 'text') sendTypingStatus(false);

    } catch (error) {
        console.error("❌ Lỗi Gửi tin nhắn:", error);

        const statusDiv = box.querySelector(".status-message");
        if (statusDiv) {
            statusDiv.className = "status-message error";
            statusDiv.innerHTML = "❌";
        }
    }
}


// ======================================================= 
// ✅ THEME TOGGLE FUNCTION
// ======================================================= 
function toggleTheme() {
    const currentTheme = document.body.getAttribute('data-theme') || getCurrentTheme();
    const currentIndex = Math.max(0, THEME_ORDER.indexOf(currentTheme));
    const nextTheme = THEME_ORDER[(currentIndex + 1) % THEME_ORDER.length];
    setLocalTheme(nextTheme);
    applyThemePreference(nextTheme);
    showToast(chatPack().themeChanged.replace('{theme}', nextTheme), 'success');
}

function bindThemeToggleForAllUsers() {
    if (!themeToggle || themeToggle.dataset.bound === '1') return;
    themeToggle.addEventListener('click', toggleTheme);
    themeToggle.dataset.bound = '1';
}

// ======================================================= 
// ✅ SIDEBAR TOGGLE FUNCTION
// ======================================================= 
function toggleSidebar() {
    if (friendsSidebar) {
        const isHidden = friendsSidebar.style.transform === 'translateX(-100%)';
        friendsSidebar.style.transform = isHidden ? 'translateX(0)' : 'translateX(-100%)';

        // Update icon
        const sidebarIcon = sidebarToggle.querySelector('i');
        if (sidebarIcon) {
            sidebarIcon.className = isHidden ? 'fas fa-times' : 'fas fa-bars';
        }
    }
}


// ======================================================= 
// ✅ YÊU CẦU QUYỀN NOTIFICATION
// ======================================================= 
async function requestNotificationPermission() {
    if (!isSettingEnabled('desktop_notify', true)) return;
    if ("Notification" in window) {
        if (Notification.permission === "default") {
            try {
                const permission = await Notification.requestPermission();
                console.log("🔔 Notification permission:", permission);
            } catch (error) {
                console.error("❌ Lỗi request notification permission:", error);
            }
        } else if (Notification.permission === "denied") {
            console.warn("⚠️ Notification permission bị từ chối");
        }
    }
}

// =======================================================
// ✅ AUTH STATE CHANGED - THÊM KHỞI TẠO SESSION
// =======================================================
onAuthStateChanged(auth, async (user) => {
    refreshAppSettings();
    if (!user) {
        const guestProfile = resetGuestPreferences();
        applyThemePreference(guestProfile.theme);
        applyChatLanguage();

        // Staggered loading for guests - OPTIMIZED SPEED
        updateLoadingProgress(1, loadingStepText(1));
        await sleep(150);
        updateLoadingProgress(2, loadingStepText(2));
        await sleep(150);
        updateLoadingProgress(3, loadingStepText(3));
        await sleep(150);
        updateLoadingProgress(5, loadingStepText(5)); // Skip 4 for guests
        await sleep(200);
        updateLoadingProgress(7, loadingStepText(7));
        await sleep(100);

        markChatBootReady();
        loadTimeout = setTimeout(() => completeLoadingWithMinimum(50), 50);
        return;
    }

    currentUserUid = user.uid;

    try {
        const remoteProfile = await loadRemoteUserProfile(user);
        if (remoteProfile) {
            currentUserName = remoteProfile.username || currentUserName;
            applyThemePreference(remoteProfile.theme);
            setLocalLanguage(remoteProfile.language || getCurrentLanguage());
            refreshAppSettings();
            applyChatLanguage();
        }

        // Realistic staggered loading - OPTIMIZED SPEED
        updateLoadingProgress(1, loadingStepText(1));
        await sleep(150);

        updateLoadingProgress(2, loadingStepText(2));
        checkNetworkStatus();
        networkCheckInterval = setInterval(checkNetworkStatus, 5000);
        
        // Concurrent health check
        probeSocketServer().catch(() => null);
        await sleep(200);

        const userDoc = await getDoc(doc(db, "users", user.uid));
        if (userDoc.exists()) {
            currentUserName = userDoc.data().username || "User Name";
        }

        updateLoadingProgress(3, loadingStepText(3));
        await initializeUnreadCounts();
        await sleep(150);

        updateLoadingProgress(4, loadingStepText(4));
        if (CHATBOT_ENABLED) {
            initChatbotSession();
        } else {
            cleanupDisabledChatbotState();
        }
        initializeDOMElements();
        connectSocket();
        await sleep(200);

        updateLoadingProgress(5, loadingStepText(5));
        await loadLastMessagesFromFirestore();
        cleanupDisabledChatbotState();
        await sleep(150);

        updateLoadingProgress(6, loadingStepText(6));
        await requestNotificationPermission();
        await sleep(150);

        updateLoadingProgress(7, loadingStepText(7));
        await sleep(100);

        console.log("✅ User authenticated:", currentUserUid);
        markChatBootReady();
        completeLoadingWithMinimum(50);

    } catch (error) {
        console.error("❌ Lỗi trong quá trình khởi tạo:", error);
        showNetworkError(uiText('Lỗi khởi tạo', 'Initialization error'), uiText('Không thể tải dữ liệu. Vui lòng kiểm tra kết nối mạng và thử lại.', 'Could not load data. Please check your network connection and try again.'));
    }
});

// ======================================================= 
// ✅ LOAD LAST MESSAGES TỪ FIRESTORE
// ======================================================= 
async function loadLastMessagesFromFirestore() {
    if (!currentUserUid) return;

    try {
        const userDoc = await getDoc(doc(db, "users", currentUserUid));
        const userData = userDoc.data();
        const friends = (userData?.friends || []).filter((friendUid) => !isDisabledChatbotUid(friendUid));

        for (const friendUid of friends) {
            const chatId = [currentUserUid, friendUid].sort().join("_");
            const messagesRef = collection(db, "chats", chatId, "messages");
            const q = query(messagesRef, orderBy("timestamp", "desc"), limit(1));
            const snapshot = await getDocs(q);

            if (!snapshot.empty) {
                const doc = snapshot.docs[0];
                const msgData = doc.data();

                lastMessages[friendUid] = {
                    text: msgData.content || msgData.fileName || '',
                    type: msgData.type || 'text',
                    timestamp: msgData.timestamp?.toDate() || new Date(),
                    sender: msgData.from
                };

                const event = new CustomEvent('lastMessageUpdated', {
                    detail: { friendUid: friendUid, message: lastMessages[friendUid] }
                });
                window.dispatchEvent(event);
            }
        }

        console.log("✅ Đã load last messages:", lastMessages);
    } catch (error) {
        console.error("❌ Lỗi load last messages:", error);
    }
}

// Socket.IO connection
async function connectSocket() {
    if (!SOCKET_SERVER_ENABLED) {
        return;
    }
    if (socket && (socket.connected || socket.active)) return;

    const socketReady = await probeSocketServer();
    if (!socketReady) {
        console.warn("Socket server is offline. Keeping AI/direct-backend mode available.");
        return;
    }

    console.log("Connecting to Socket.IO server...");

    const SOCKET_URL = SOCKET_BASE_URL;

    socket = io(SOCKET_URL, {
        transports: ["polling", "websocket"],
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000,
        forceNew: false,
        path: '/socket.io/',
        auth: {
            uid: currentUserUid,
            username: currentUserName
        }
    });


    socket.on('connect', () => {
        console.log("Socket.IO connected successfully");
    });

    socket.on('connected', (data) => {
        console.log(`[Socket.IO] Connected: ${data.message}`);
        socket.emit('join_user_room', {
            uid: currentUserUid,
            username: currentUserName
        });
        console.log(`Joined room: user_${currentUserUid}`);

        // Test Gửi tin nhắn test để kiểm tra kết nối
        socket.emit('test_connection', {
            uid: currentUserUid,
            timestamp: Date.now()
        });

        if (selectedFriendUid) {
            loadMessagesFromFirestore(selectedFriendUid);
            markAllMessagesAsSeen(selectedFriendUid);
        }
    });

    socket.on('presence_sync', (data = {}) => {
        const users = data.users || {};
        Object.keys(users).forEach((uid) => {
            onlinePresence[uid] = {
                online: !!users[uid].online,
                lastSeen: users[uid].lastSeen || null
            };
        });
        updateSelectedFriendStatus();
    });

    socket.on('presence_update', (data = {}) => {
        if (!data.uid) return;
        onlinePresence[data.uid] = {
            online: !!data.online,
            lastSeen: data.lastSeen || null
        };
        if (data.uid === selectedFriendUid) {
            updateSelectedFriendStatus();
        }
    });

    socket.on('test_response', (data) => {
        console.log("Socket.IO test response:", data);
    });

    socket.on('receive_message', async (msg) => {
        console.log("[Socket.IO] Incoming message:", msg.messageId || msg.firestoreId);

        if (processedMessageIds.has(msg.messageId) || processedMessageIds.has(msg.firestoreId)) {
            console.log("Message already processed");
            return;
        }

        processedMessageIds.add(msg.messageId || msg.firestoreId);
        await handleIncomingMessage(msg);
    });

    socket.on('typing', (data) => {
        console.log(`Typing event from ${data.sender}:`, data.isTyping);

        if (data.sender === selectedFriendUid && typingIndicator) {
            if (data.isTyping) {
                const senderName = data.senderName || selectedFriendName;
                typingIndicator.innerHTML = `
                    <div class="typing-dots">
                        <span></span><span></span><span></span>
                    </div>
                    <div class="typing-text">${senderName} ${uiText('đang soạn tin...', 'is typing...')}</div>
                `;
                typingIndicator.style.display = 'flex';
                updateSelectedFriendStatus(`${senderName} ${uiText('đang nhập tin nhắn...', 'is typing...')}`);

                if (typingStatusTimer) clearTimeout(typingStatusTimer);
                typingStatusTimer = setTimeout(() => {
                    typingIndicator.style.display = 'none';
                    updateSelectedFriendStatus();
                }, 3000);
            } else {
                typingIndicator.style.display = 'none';
                updateSelectedFriendStatus();
            }
        }
    });

    socket.on('message_seen', (data) => {
        console.log("Message seen:", data.messageId);
        const box = document.querySelector(`[data-key='${data.messageId}']`);
        if (box) {
            const statusDiv = box.querySelector(".status-message");
            if (statusDiv) {
                statusDiv.textContent = chatPack().seen || 'Seen';
                statusDiv.className = "status-message seen";
            }
        }
    });

    socket.on('disconnect', () => {
        console.warn("[Socket.IO] Disconnected");
        showToast(uiText('Mất kết nối với server. Đang thử kết nối lại...', 'Disconnected from the server. Trying to reconnect...'), 'error');
        if (selectedFriendUid && selectedFriendUid !== CHATBOT_UID) {
            setFriendStatusText(uiText('Mất kết nối', 'Disconnected'));
        }
    });

    socket.on('reconnect', (attempt) => {
        console.log("Reconnected after", attempt, "attempts");
        socket.emit('join_user_room', { uid: currentUserUid, username: currentUserName });
        showToast(uiText('Đã kết nối lại với server', 'Reconnected to the server'), 'success');
        updateSelectedFriendStatus();
    });

    socket.on('incoming_call', (data) => {
        console.log("Incoming call from:", data.senderName);
        handleIncomingCall(data);
    });

    socket.on('call_response', (data) => {
        console.log("Call response:", data.accepted);
        handleCallResponse(data);
    });

    socket.on('call_end', (data = {}) => {
        console.log("Call ended");
        endCall({ notifyPeer: false, outcome: data.outcome || 'remote_end' });
    });

    socket.on('webrtc_sdp', async (data) => {
        console.log("Received SDP from:", data.sender);
        await handleWebRTCSDP(data);
    });

    socket.on('webrtc_ice_candidate', (data) => {
        console.log("Received ICE candidate from:", data.sender);
        handleWebRTCCandidate(data);
    });

    socket.on("connect_error", (err) => {
        console.error("Socket connection error:", err.message);
        console.log("Check if `node server.js` is running.");
        console.log("Current socket URL:", SOCKET_URL);
    });

    socket.on('error', (error) => {
        console.error("Socket.IO error:", error);
    });
}

// =======================================================
// ✅ BIẾN QUẢN LÝ DỪNG/TIẾP TỤC PHẢN HỒI
// =======================================================
let botStreamingPausedAt = 0;
let pauseResumeContainer = null;
let pauseBtn = null;
let resumeBtn = null;
let stopStreamingBtn = null;
let botStreamingController = null;

// =======================================================
// ✅ CẬP NHẬT HÀM RESET STREAMING STATE
// =======================================================
function resetBotStreamingState() {
    isStreamingActive = false;
    botStreamingPaused = false;
    botStreamingPausedAt = 0;
    botStreamingContent = "";
    currentStreamingText = "";
    streamingMessageId = null;
    botStreamingController = null;

    // Đảm bảo xóa indicator
    ensureBotTypingIndicatorIsRemoved();

    // Xóa container nút điều khiển nếu có
    if (pauseResumeContainer && pauseResumeContainer.parentNode) {
        pauseResumeContainer.remove();
        pauseResumeContainer = null;
    }

    // Bật lại input
    if (msgInput) {
        msgInput.disabled = false;
        msgInput.placeholder = chatText('placeholder');
        msgInput.classList.remove('chat-input-disabled');
    }

    // Bật lại nút gửi
    if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.classList.remove('btn-disabled');
    }
}

// =======================================================
// ✅ HÀM TẠO NÚT ĐIỀU KHIỂN DỪNG/TIẾP TỤC
// =======================================================
function createBotStreamingControls(messageId) {
    // Xóa container cũ nếu có
    if (pauseResumeContainer && pauseResumeContainer.parentNode) {
        pauseResumeContainer.remove();
    }

    pauseResumeContainer = document.createElement('div');
    pauseResumeContainer.className = 'bot-streaming-controls';
    pauseResumeContainer.style.cssText = `
        display: flex;
        justify-content: center;
        gap: 10px;
        margin: 15px 0;
        padding: 10px;
        background: rgba(0, 212, 255, 0.05);
        border-radius: 12px;
        border: 1px solid rgba(0, 212, 255, 0.1);
        backdrop-filter: blur(10px);
    `;

    // Nút Dừng
    pauseBtn = document.createElement('button');
    pauseBtn.id = 'pauseBotStreaming';
    pauseBtn.className = 'streaming-control-btn pause-btn';
    pauseBtn.innerHTML = `<i class="fas fa-pause"></i> ${uiText('Tạm dừng', 'Pause')}`;
    pauseBtn.onclick = () => pauseBotStreaming(messageId);

    // Nút Tiếp tục (ban đầu ẩn)
    resumeBtn = document.createElement('button');
    resumeBtn.id = 'resumeBotStreaming';
    resumeBtn.className = 'streaming-control-btn resume-btn';
    resumeBtn.style.display = 'none';
    resumeBtn.innerHTML = `<i class="fas fa-play"></i> ${uiText('Tiếp tục', 'Resume')}`;
    resumeBtn.onclick = () => resumeBotStreaming(messageId);

    // Nút Dừng hẳn
    stopStreamingBtn = document.createElement('button');
    stopStreamingBtn.id = 'stopBotStreaming';
    stopStreamingBtn.className = 'streaming-control-btn stop-btn';
    stopStreamingBtn.innerHTML = `<i class="fas fa-stop"></i> ${uiText('Dừng hẳn', 'Stop')}`;
    stopStreamingBtn.onclick = () => stopBotStreaming(messageId);

    pauseResumeContainer.appendChild(pauseBtn);
    pauseResumeContainer.appendChild(resumeBtn);
    pauseResumeContainer.appendChild(stopStreamingBtn);

    // Thêm vào sau tin nhắn bot đang streaming
    const botMessage = document.getElementById(messageId);
    if (botMessage) {
        botMessage.parentNode.insertBefore(pauseResumeContainer, botMessage.nextSibling);
    } else {
        messagesDiv.appendChild(pauseResumeContainer);
    }

    console.log('🎛️ Đã tạo nút điều khiển streaming');
}

// =======================================================
// ✅ HÀM DỪNG STREAMING
// =======================================================
function pauseBotStreaming(messageId) {
    if (!isStreamingActive || botStreamingPaused) return;

    console.log('⏸️ Dừng streaming...');
    botStreamingPaused = true;
    botStreamingPausedAt = Date.now();

    // Ngắt kết nối streaming controller
    if (botStreamingController) {
        botStreamingController.abort();
        botStreamingController = null;
    }

    // Cập nhật UI
    if (pauseBtn) pauseBtn.style.display = 'none';
    if (resumeBtn) resumeBtn.style.display = 'inline-flex';

    // Hiển thị trạng thái
    const streamingElement = document.getElementById(`streaming_${messageId}`);
    if (streamingElement) {
        streamingElement.innerHTML += ` <span class="paused-indicator" style="color: #ffaa00; font-style: italic;">[${uiText('Đã tạm dừng', 'Paused')}]</span>`;
    }

    showToast(uiText('Đã tạm dừng phản hồi', 'Response paused'), 'info');

    // Cho phép nhập tin nhắn mới khi đã dừng
    if (msgInput) {
        msgInput.disabled = false;
        msgInput.placeholder = chatText('sendNewMessage');
        msgInput.classList.remove('chat-input-disabled');
    }
}

// =======================================================
// ✅ HÀM TIẾP TỤC STREAMING
// =======================================================
function resumeBotStreaming(messageId) {
    if (!botStreamingPaused) return;
    console.log('▶️ Tiếp tục streaming bằng cách Gửi tin nhắn mới...');
    botStreamingPaused = false;

    // Cập nhật UI
    if (pauseBtn) pauseBtn.style.display = 'inline-flex';
    if (resumeBtn) resumeBtn.style.display = 'none';

    // Xóa container điều khiển
    if (pauseResumeContainer && pauseResumeContainer.parentNode) {
        pauseResumeContainer.remove();
        pauseResumeContainer = null;
    }

    // Xóa indicator đã dừng
    const streamingElement = document.getElementById(`streaming_${messageId}`);
    if (streamingElement) {
        const pausedIndicator = streamingElement.querySelector('.paused-indicator');
        if (pausedIndicator) pausedIndicator.remove();
    }

    // Simulate user typing "continue" and sending
    if (msgInput) {
        msgInput.value = uiText('tiếp tục', 'continue');
        sendTextMessage();
    }

    showToast(uiText('Đang yêu cầu AI tiếp tục...', 'Requesting the AI to continue...'), 'info');
}


// =======================================================
// ✅ HÀM Gửi tin nhắn CHATBOT (WRAPPER)
// =======================================================
async function sendTextMessage() {
    const text = msgInput.value.trim();
    if (!text || !selectedFriendUid) return;

    // Check limit
    const words = text.split(/\s+/).length;
    if (words > MAX_PROMPT_WORDS && selectedFriendUid === CHATBOT_UID) {
        showToast(
            uiText(
                `Tin nhắn quá dài (${words}/${MAX_PROMPT_WORDS} từ). Vui lòng rút ngắn lại.`,
                `Message is too long (${words}/${MAX_PROMPT_WORDS} words). Please shorten it.`
            ),
            'error'
        );
        return;
    }

    // Nếu là chatbot
    if (selectedFriendUid === CHATBOT_UID) {
        await handleChatbotMessage(text);
        return;
    }

    // Nếu là user thường
    await sendMessage({
        type: 'text',
        text: text
    });
}

// =======================================================
// ✅ HÀM DỪNG HẲN STREAMING
// =======================================================
function stopBotStreaming(messageId) {
    console.log('⏹️ Dừng hẳn streaming...');

    // Ngắt kết nối controller
    if (botStreamingController) {
        botStreamingController.abort();
        botStreamingController = null;
    }

    // Đánh dấu kết thúc
    isStreamingActive = false;
    botStreamingPaused = false;

    // Cập nhật UI
    const streamingElement = document.getElementById(`streaming_${messageId}`);
    if (streamingElement) {
        streamingElement.innerHTML += ` <span class="stopped-indicator" style="color: #ff6b6b; font-style: italic;">[${uiText('Đã dừng', 'Stopped')}]</span>`;
    }

    // Xóa container điều khiển
    if (pauseResumeContainer && pauseResumeContainer.parentNode) {
        pauseResumeContainer.remove();
        pauseResumeContainer = null;
    }

    // Bật lại input và nút gửi
    if (msgInput) {
        msgInput.disabled = false;
        msgInput.placeholder = chatText('placeholder');
        msgInput.classList.remove('chat-input-disabled');
    }

    if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.classList.remove('btn-disabled');
    }

    showToast(uiText('Đã dừng phản hồi', 'Response stopped'), 'info');
}

// =======================================================
// ✅ SỬA HÀM startTextStreaming - ĐẢM BẢO TẮT INDICATOR KHI HOÀN TẤT
// =======================================================
function startTextStreaming(fullText, messageId, options = {}) {
    const streamingElement = document.getElementById(`streaming_${messageId}`);
    if (!streamingElement) return;

    console.log('🤖 Bắt đầu streaming text...');

    const typingSpeed = options.speed || 30;
    const batchSize = options.batchSize || 1;
    const startFrom = options.startFrom || 0;
    let index = startFrom;

    // Lưu nội dung đầy đủ để có thể tiếp tục sau này
    if (startFrom === 0) {
        botStreamingContent = fullText;
        streamingElement.textContent = "";
    }

    // Tạo AbortController để có thể dừng
    botStreamingController = new AbortController();

    // Streaming function
    function streamNext() {
        if (botStreamingPaused || !isStreamingActive) {
            console.log('⏸️ Streaming bị tạm dừng');
            return;
        }

        if (index < fullText.length) {
            // Lấy batch ký tự tiếp theo
            const batch = fullText.substr(index, batchSize);
            streamingElement.textContent = streamingElement.textContent + batch;
            index += batchSize;

            // Cuộn xuống
            if (index % 40 === 0 || index === fullText.length) {
                scrollToBottomIfAllowed();
            }

            // Lên lịch cho batch tiếp theo
            setTimeout(streamNext, typingSpeed);
        } else {
            // KẾT THÚC STREAMING - ĐẢM BẢO TẮT MỌI THỨ
            console.log('🎯 Kết thúc streaming, đảm bảo tắt indicator...');

            // 1. Đặt trạng thái - QUAN TRỌNG: RESET TẤT CẢ BIẾN
            isStreamingActive = false;
            botStreamingPaused = false;

            // 2. ĐẢM BẢO TẮT TYPING INDICATOR
            ensureBotTypingIndicatorIsRemoved();

            // 4. Xóa container điều khiển
            if (pauseResumeContainer && pauseResumeContainer.parentNode) {
                pauseResumeContainer.remove();
                pauseResumeContainer = null;
            }

            // 5. Xóa cursor
            streamingElement.classList.remove('streaming-text');
            streamingElement.closest('.msg.bot')?.classList.remove('is-streaming');

            // 5.5 CHUYỂN ĐỔI SANG HTML (CODE BLOCKS) KHI HOÀN TẤT
            streamingElement.innerHTML = renderBotMarkdown(fullText);

            // 6. Lưu tin nhắn vào session
            saveBotMessageToSession(fullText, messageId);

            // 7. GỌI RESET STATE ĐỂ ĐẢM BẢO MỌI THỨ ĐỀU BẬT LẠI
            resetBotStreamingState();

            console.log('✅ Bot message streaming complete - Tất cả đã được reset');
        }
    }

    // Bắt đầu streaming
    streamNext();
}

// =======================================================
// ✅ CẬP NHẬT TIN NHẮN BOT ĐANG STREAMING VÀO SESSION
// =======================================================
function updateCurrentBotMessageInSession(messageId, text) {
    if (!currentUserUid) return;
    const cleanText = stripHiddenReasoningSections(text);

    // Tìm tin nhắn trong mảng session
    const msgIndex = chatbotSession.messages.findIndex(m => m.id === messageId);

    if (msgIndex !== -1) {
        // Cập nhật nội dung
        chatbotSession.messages[msgIndex].text = cleanText;
        chatbotSession.messages[msgIndex].rawText = cleanText;
        // Không cần lưu vào sessionStorage liên tục để tránh lag, 
        // chỉ cần cập nhật biến chatbotSession.messages là đủ để chuyển tab
    }
}

// =======================================================
// ✅ sendTextMessage is now refactored and removed.
// =======================================================


// =======================================================
// ✅ LOAD MESSAGES TỪ FIRESTORE - BỎ QUA CHATBOT
// =======================================================
async function loadMessagesFromFirestore(friendUid) {
    if (!currentUserUid || !friendUid) return;

    if (isDisabledChatbotUid(friendUid)) {
        cleanupDisabledChatbotState();
        updateChatUIState();
        return;
    }

    if (activeMessagesUnsubscribe) {
        activeMessagesUnsubscribe();
        activeMessagesUnsubscribe = null;
    }

    // =======================================================
    // 🔴 NẾU LÀ CHATBOT: LOAD TỪ SESSION (KHÔNG FIRESTORE)
    // =======================================================
    if (friendUid === CHATBOT_UID) {
        console.log('🤖 Loading chatbot messages from session (NOT Firestore)');

        if (messagesDiv) messagesDiv.innerHTML = "";
        processedMessageIds.clear();

        const sessionMessages = loadChatbotMessagesFromSession();

        if (sessionMessages.length === 0) {
            if (emptyChatState) {
                emptyChatState.style.display = 'flex';
                const friendNameGreeting = document.getElementById('friendNameGreeting');
                if (friendNameGreeting && selectedFriendName) {
                    friendNameGreeting.textContent = selectedFriendName;
                }
            }
        } else {
            if (emptyChatState) emptyChatState.style.display = 'none';

            sessionMessages.forEach(msg => {
                const messageData = {
                    sender: msg.sender,
                    receiver: msg.receiver,
                    text: msg.text,
                    rawText: msg.rawText || msg.text,
                    type: msg.type || "text",
                    mediaURL: msg.mediaURL || null,
                    fileName: msg.fileName || null,
                    timestamp: msg.timestamp || Date.now(),
                    isBot: msg.type === "bot_message",
                    isFromSession: true,
                    messageId: msg.id
                };

                if (msg.id) processedMessageIds.add(msg.id);
                renderMessage(messageData);
            });
        }

        // KHÔI PHỤC TRẠNG THÁI NẾU ĐANG STREAMING HOẶC TYPING
        if (isBotTyping) {
            console.log('🤖 Đang typing, khôi phục indicator...');
            showBotTypingIndicator();
        }

        if (messagesDiv) scrollToBottomIfAllowed(true);
        console.log(`✅ Đã load ${sessionMessages.length} tin nhắn chatbot từ session`);
        return;
    }

    // =======================================================
    // ⚪ NẾU LÀ BẠN BÈ THÔNG THƯỜNG: LOAD TỪ FIRESTORE
    // =======================================================
    try {
        const chatId = [currentUserUid, friendUid].sort().join("_");
        convId = chatId;

        const messagesRef = collection(db, "chats", chatId, "messages");
        const q = query(messagesRef, orderBy("timestamp", "asc"));

        activeMessagesUnsubscribe = onSnapshot(q, (snapshot) => {
            if (selectedFriendUid !== friendUid) return;

            if (messagesDiv) messagesDiv.innerHTML = "";
            processedMessageIds.clear();

            if (snapshot.empty) {
                if (emptyChatState) {
                    emptyChatState.style.display = 'flex';
                    const friendNameGreeting = document.getElementById('friendNameGreeting');
                    if (friendNameGreeting && selectedFriendName) {
                        friendNameGreeting.textContent = selectedFriendName;
                    }
                }
            } else {
                if (emptyChatState) emptyChatState.style.display = 'none';

                snapshot.forEach((doc) => {
                    const msgData = doc.data();
                    const msg = {
                        firestoreId: doc.id,
                        messageId: msgData.messageId,
                        sender: msgData.from,
                        receiver: msgData.to,
                        text: msgData.content,
                        rawText: msgData.content,
                        type: msgData.type || "text",
                        fileName: msgData.fileName || null,
                        timestamp: msgData.timestamp?.toDate()?.getTime() || Date.now(),
                        seen: msgData.status === 'seen',
                        callMeta: msgData.callMeta || null
                    };

                    if (msg.firestoreId) processedMessageIds.add(msg.firestoreId);
                    if (msg.messageId) processedMessageIds.add(msg.messageId);
                    renderMessage(msg);
                });

                const lastDoc = snapshot.docs[snapshot.docs.length - 1];
                if (lastDoc) {
                    const lastData = lastDoc.data();
                    emitLastMessageUpdated(friendUid, {
                        text: lastData.content || lastData.fileName || "",
                        rawText: lastData.content || lastData.fileName || "",
                        type: lastData.type || "text",
                        timestamp: lastData.timestamp?.toDate()?.getTime() || Date.now(),
                        sender: lastData.from
                    });
                }
            }

            if (messagesDiv) scrollToBottomIfAllowed(true);
            console.log(`✅ Realtime sync ${snapshot.size} tin nhắn từ Firestore`);
        }, (error) => {
            console.error("❌ Lỗi realtime messages:", error);
        });

    } catch (error) {
        console.error("❌ Lỗi load messages:", error);
    }
}

// =======================================================
// ✅ SELECT FRIEND - CẬP NHẬT CHO CHATBOT
// =======================================================
window.addEventListener("friendSelected", async (e) => {
    selectedFriendUid = typeof e?.detail?.uid === 'string' ? e.detail.uid : null;
    selectedFriendName = e?.detail?.name || null;

    if (isDisabledChatbotUid(selectedFriendUid)) {
        cleanupDisabledChatbotState();
    }

    if (!selectedFriendUid) {
        if (friendNameDisplay) {
            friendNameDisplay.innerText = chatText('chooseFriend');
        }
        if (friendStatusDisplay) {
            friendStatusDisplay.textContent = chatText('offline');
            friendStatusDisplay.className = 'friend-status';
        }
        updateChatUIState();
        if (messagesDiv) messagesDiv.innerHTML = '';
        if (welcomeState) welcomeState.style.display = 'flex';
        if (emptyChatState) emptyChatState.style.display = 'none';
        return;
    }

    if (friendNameDisplay) {
        friendNameDisplay.innerText = selectedFriendName;
    }
    updateSelectedFriendStatus();

    if (selectedFriendStatusTimer) clearInterval(selectedFriendStatusTimer);
    selectedFriendStatusTimer = setInterval(() => {
        if (selectedFriendUid && selectedFriendUid !== CHATBOT_UID) {
            updateSelectedFriendStatus();
        }
    }, 30000);

    // Vô hiệu hóa nút gọi cho chatbot
    const isChatbot = selectedFriendUid === CHATBOT_UID;
    if (voiceCallBtn) voiceCallBtn.disabled = isChatbot;
    if (videoCallBtn) videoCallBtn.disabled = isChatbot;

    updateChatUIState();

    if (unreadCounts[selectedFriendUid] > 0) {
        await updateUnreadCount(selectedFriendUid, 'reset');

        const event = new CustomEvent('resetUnreadForFriend', {
            detail: {
                friendUid: selectedFriendUid,
                count: 0
            }
        });
        window.dispatchEvent(event);
    }

    // KHÔNG kiểm tra block status cho chatbot
    if (selectedFriendUid !== CHATBOT_UID) {
        await checkBlockStatusByRecipient(selectedFriendUid);
    }

    if (isCurrentUserBlockedByFriend && selectedFriendUid !== CHATBOT_UID) {
        if (msgInput) msgInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
        if (voiceCallBtn) voiceCallBtn.disabled = true;
        if (videoCallBtn) videoCallBtn.disabled = true;
        showToast(uiText('Bạn đã bị chặn bởi người này', 'You have been blocked by this user'), 'error');
    } else {
        if (msgInput) msgInput.disabled = false;
        if (sendBtn) sendBtn.disabled = false;

        convId = [currentUserUid, selectedFriendUid].sort().join("_");

        await loadMessagesFromFirestore(selectedFriendUid);
        await markAllMessagesAsSeen(selectedFriendUid);
    }

    if (typingIndicator) typingIndicator.style.display = 'none';

    // Model selector removed (single-model mode)
});


// =======================================================
// ✅ HÀM TỰ ĐỘNG SỬA LỖI TYPING INDICATOR (GỌI MỖI 5 GIÂY)
// =======================================================
// =======================================================
// ✅ HÀM TỰ ĐỘNG SỬA LỖI TYPING INDICATOR (GỌI MỖI 5 GIÂY)
// =======================================================
let watchdogInterval = null;

function startIndicatorWatchdog() {
    // Nếu đã có watchdog chạy rồi, không tạo mới
    if (watchdogInterval) {
        console.log('⚠️ Watchdog đã chạy, không tạo mới');
        return;
    }

    console.log('🛡️ Bắt đầu Indicator Watchdog...');

    watchdogInterval = setInterval(() => {
        // Kiểm tra nếu đã không còn streaming nhưng indicator vẫn hiện
        // 🔴 TẠM TẮT: Logic này quá nhạy, gây xóa nhầm khi đang kết nối server
        // if (!isStreamingActive && isBotTyping && !botStreamingPaused) {
        //     console.warn('⚠️ Phát hiện lỗi: Indicator vẫn hiện khi không streaming');
        //     console.log('🛠️ Tự động sửa lỗi...');
        //     ensureBotTypingIndicatorIsRemoved();
        // }

        // Kiểm tra indicator trong DOM nhưng không có trong state
        const domIndicator = document.getElementById('botTypingIndicator');
        // 🔴 TẮT CHECK NÀY: Nó gây ra lỗi biến mất indicator khi mạng lag hoặc model load lâu
        // if (domIndicator && !isBotTyping) {
        //     console.warn('⚠️ Phát hiện indicator trong DOM nhưng state không khớp');
        //     console.log('🛠️ Tự động xóa indicator DOM...');
        //     domIndicator.remove();
        // }

        // Kiểm tra timeout quá lâu (trên 35 giây)
        if (isBotTyping && botTypingTimeout) {
            console.log('⏰ Watchdog: Bot typing đang active, kiểm tra timeout');
        }
    }, 10000); // Kiểm tra mỗi 10 giây

    console.log('✅ Watchdog đã bắt đầu');
}


// =======================================================
// ✅ KIỂM TRA BLOCK STATUS
// =======================================================
async function checkBlockStatusByRecipient(recipientUid) {
    isCurrentUserBlockedByFriend = false;

    if (!recipientUid) return;

    try {
        const recipientRef = doc(db, "users", recipientUid);
        const recipientSnap = await getDoc(recipientRef);
        const recipientData = recipientSnap.data();

        if (recipientData && recipientData.blockedUsers?.includes(currentUserUid)) {
            isCurrentUserBlockedByFriend = true;
        }

    } catch (error) {
        console.warn("⚠️ Lỗi khi kiểm tra trạng thái chặn:", error);
        isCurrentUserBlockedByFriend = false;
    }
}

// =======================================================
// ✅ FORMAT TIME
// =======================================================
function formatTime(ts) {
    const d = new Date(ts);
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

// Full "HH:MM · DD/MM/YYYY" for the hover tooltip on each bubble.
function formatFullTime(ts) {
    const d = new Date(ts);
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) + " · " +
        d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// Facebook-style day label for the divider inserted before the first message of a day.
function formatDayLabel(d) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const that = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diff = Math.round((today - that) / 86400000);
    if (diff === 0) return uiText('Hôm nay', 'Today');
    if (diff === 1) return uiText('Hôm qua', 'Yesterday');
    return d.toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
}

// Inserts a date separator before the first message of a new day (DOM-derived, so it
// resets automatically whenever the message list is cleared on conversation switch).
function maybeInsertDayDivider(ts) {
    if (!messagesDiv) return;
    const d = new Date(ts || Date.now());
    const dayKey = d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate();
    const dividers = messagesDiv.querySelectorAll(".day-divider");
    const last = dividers.length ? dividers[dividers.length - 1] : null;
    if (last && last.dataset.day === dayKey) return;
    const div = document.createElement("div");
    div.className = "day-divider";
    div.dataset.day = dayKey;
    div.innerHTML = `<span>${formatDayLabel(d)}</span>`;
    messagesDiv.appendChild(div);
}

// =======================================================
// ✅ TIỆN ÍCH - ESCAPE HTML (CHỐNG XSS)
// =======================================================
function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function normalizeSchoolMathNotation(input) {
    if (!input) return '';
    const lines = String(input).split('\n');

    const isLikelyMathLine = (line) => {
        const s = (line || '').trim();
        if (!s) return false;
        if (/\\(frac|sqrt|cdot|times|div|leq|geq|neq|pm|approx|sum|int|begin|end|left|right)/i.test(s)) return true;
        if (/\\\[|\\\]|\\\(|\\\)/.test(s)) return true;
        if (/[=<>]/.test(s) && /[A-Za-z0-9]/.test(s)) return true;
        if (/\b[A-Za-z][A-Za-z0-9]*\s*\^\s*-?[0-9]+/.test(s)) return true;
        if (/\b[A-Za-z][A-Za-z0-9]*_\d+/.test(s)) return true;
        if (/\b\d+\s*[\+\-\*x×:\/]\s*\d+\b/.test(s)) return true;
        if (/\([^)]+\)\s*\([^)]+\)/.test(s)) return true;
        return false;
    };

    const normalizeMathLine = (line) => {
        let out = line;

        // Remove common LaTeX wrappers
        out = out
            .replace(/\\\[/g, '')
            .replace(/\\\]/g, '')
            .replace(/\\\(/g, '')
            .replace(/\\\)/g, '')
            .replace(/\\begin\{aligned\}/g, '')
            .replace(/\\end\{aligned\}/g, '')
            .replace(/\\left/g, '')
            .replace(/\\right/g, '')
            .replace(/\\\\/g, '\n');

        // Fractions: \frac{a}{b} -> (a/b)
        for (let i = 0; i < 5; i++) {
            const next = out.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1/$2)');
            if (next === out) break;
            out = next;
        }

        // Root and relational symbols
        out = out
            .replace(/\\sqrt\{([^{}]+)\}/g, '√($1)')
            .replace(/\\leq/g, '≤')
            .replace(/\\geq/g, '≥')
            .replace(/\\neq/g, '≠')
            .replace(/\\approx/g, '≈')
            .replace(/\\pm/g, '±');

        // Multiplication/division in common form
        out = out
            .replace(/\\cdot/g, ' × ')
            .replace(/\\times/g, ' × ')
            .replace(/\\div/g, ' : ');

        // Convert braced exponents/subscripts
        out = out
            .replace(/\^\{([^{}]+)\}/g, '^$1')
            .replace(/_\{([^{}]+)\}/g, '_$1');

        // Convert exponents/subscripts to readable HTML
        out = out
            .replace(/([A-Za-z0-9)\]])\^(-?\d+)/g, '$1<sup>$2</sup>')
            .replace(/([A-Za-z0-9)\]])\^([A-Za-z]+)/g, '$1<sup>$2</sup>')
            .replace(/([A-Za-z])_(\d+)/g, '$1<sub>$2</sub>');

        // Remove noisy escaped punctuation
        out = out
            .replace(/\\([+\-=()])/g, '$1')
            .replace(/\\;/g, ' ')
            .replace(/\\,/g, ' ')
            .replace(/[ \t]{2,}/g, ' ');

        return out.trimEnd();
    };

    return lines.map((line) => (isLikelyMathLine(line) ? normalizeMathLine(line) : line)).join('\n');
}

// =======================================================
// ✅ HÀM FORMAT NỘI DUNG TIN NHẮN (CODE BLOCK + COPY)
// =======================================================
function formatMessageContent(text) {
    if (!text) return '';
    text = String(text)
        .replace(/\r\n/g, '\n')
        .replace(/\n{4,}/g, '\n\n\n');

    // Step 1: Preserve Code Blocks
    const codeBlocks = [];
    let placeholderIdx = 0;
    const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
    text = text.replace(codeBlockRegex, (match, lang, code) => {
        const language = lang || 'code';
        const codeId = 'code_' + Math.random().toString(36).substr(2, 9);
        const placeholder = `__CODE_BLOCK_${placeholderIdx++}__`;
        const html = `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-block-lang">${escapeHtml(language)}</span>
                    <button class="copy-btn" onclick="copyCodeBlock('${codeId}', this)">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
                <pre class="code-block-content" id="${codeId}">${escapeHtml(code.trim())}</pre>
            </div>
        `;
        codeBlocks.push({ placeholder, html });
        return placeholder;
    });

    // Step 1.5: Auto-normalize math notation for non-code content
    text = normalizeSchoolMathNotation(text);

    // Step 2: Inline Code
    text = text.replace(/`([^`]+)`/g, (match, code) => `<span class="inline-code">${escapeHtml(code)}</span>`);

    // Step 3: Tables
    const lines = text.split('\n');
    let inTable = false;
    let tableHtml = '';
    const newLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line.startsWith('|') && line.endsWith('|')) {
            if (!inTable) {
                inTable = true;
                tableHtml = '<table>';
            }
            const cells = line.split('|').filter(c => c.trim().length > 0 || line.includes('||'));
            if (line.includes('---')) continue; // Skip separator line

            const tag = tableHtml === '<table>' ? 'th' : 'td';
            tableHtml += '<tr>' + cells.map(c => `<${tag}>${formatInlineMarkdown(c.trim())}</${tag}>`).join('') + '</tr>';
        } else {
            if (inTable) {
                tableHtml += '</table>';
                newLines.push(tableHtml);
                inTable = false;
                tableHtml = '';
            }
            newLines.push(lines[i]);
        }
    }
    if (inTable) newLines.push(tableHtml + '</table>');
    text = newLines.join('\n');

    // Step 4: Blocks & Hierarchy
    // Headings (MUST be done before lists to avoid confusion with # sign in some contexts, though Markdown # usually start lines)
    text = text.replace(/^#### (.*$)/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gm, '<h1>$1</h1>');

    // Lists (simplified list detection)
    text = text.replace(/^\s*[-*+]\s+(.*$)/gm, '<ul><li>$1</li></ul>');
    text = text.replace(/^\s*(\d+)\.\s+(.*$)/gm, '<ol><li>$2</li></ol>');

    // Fix nested lists (merge adjacent ul/ol)
    text = text.replace(/<\/ul>\s*<ul>/g, '');
    text = text.replace(/<\/ol>\s*<ol>/g, '');

    // Bold & Italic
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Blockquotes
    text = text.replace(/^>\s+(.*$)/gm, '<blockquote>$1</blockquote>');

    // Step 5: Handling paragraphs & newlines
    const blockTags = ['table', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'div', 'pre'];
    text = text.split('\n').map(line => {
        const trimmed = line.trim();
        if (!trimmed) return '<br>';
        const isBlock = blockTags.some(tag => trimmed.includes(`<${tag}`) || trimmed.includes(`</${tag}>`));
        return isBlock ? trimmed : trimmed + '<br>';
    }).join('\n');
    text = text.replace(/(<br>\s*){3,}/g, '<br><br>');

    // Step 6: Restore Code Blocks
    codeBlocks.forEach(item => {
        text = text.replace(item.placeholder, item.html);
    });

    return text;
}

// Helper for inline elements within tables/lists
function formatInlineMarkdown(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<span class="inline-code">$1</span>');
}


// =======================================================
// ✅ HÀM COPY CODE BLOCK (GLOBAL)
// =======================================================
window.copyCodeBlock = function (codeId, buttonElement) {
    const codeElement = document.getElementById(codeId);
    if (!codeElement) return;

    const textToCopy = codeElement.textContent || codeElement.innerText;

    navigator.clipboard.writeText(textToCopy).then(() => {
        // Thay đổi nút thành "Copied"
        const originalHtml = buttonElement.innerHTML;
        buttonElement.innerHTML = '<i class="fas fa-check"></i> Copied';
        buttonElement.classList.add('copied');

        // Sau 5 giây, đổi lại
        setTimeout(() => {
            buttonElement.innerHTML = originalHtml;
            buttonElement.classList.remove('copied');
        }, 5000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        // Fallback cho trình duyệt cũ
        const textarea = document.createElement('textarea');
        textarea.value = textToCopy;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);

        buttonElement.innerHTML = '<i class="fas fa-check"></i> Copied';
        buttonElement.classList.add('copied');
        setTimeout(() => {
            buttonElement.innerHTML = '<i class="fas fa-copy"></i> Copy';
            buttonElement.classList.remove('copied');
        }, 5000);
    });
};



// =======================================================
// ✅ RENDER TIN NHẮN - CẬP NHẬT CHO CHATBOT
// =======================================================
function renderMessage(msg) {
    // Kiểm tra xem có đang streaming không
    // SỬA: Cho phép render lại tin nhắn đang streaming khi chuyển tab quay lại
    // Chỉ bỏ qua nếu nó ĐANG ĐƯỢC TẠO MỚI bởi hàm createBotMessageStreaming
    // if (isStreamingActive && (msg.sender === CHATBOT_UID || msg.isBot)) {
    //    console.log('🤖 Đang streaming, bỏ qua render thường');
    //    return;
    // }

    const existingMsg = msg.firestoreId ? document.querySelector(`[data-firestore-id='${msg.firestoreId}']`) :
        msg.messageId ? document.querySelector(`[data-message-id='${msg.messageId}']`) : null;

    if (existingMsg) {
        console.log("⏩ Bỏ qua render tin nhắn đã tồn tại");
        return;
    }

    if (msg.firestoreId) processedMessageIds.add(msg.firestoreId);
    if (msg.messageId) processedMessageIds.add(msg.messageId);

    const originalText = getOriginalMessageText(msg);

    // Xử lý tin nhắn từ chatbot
    if (msg.sender === CHATBOT_UID || msg.isBot) {
        // Đang có streaming indicator thì bỏ qua render bình thường
        // SỬA: Nếu đang typing (chưa có chữ nào) thì không render message cũ/mới đè lên
        // Nhưng nếu là message đang streaming (có nội dung) thì vẫn render
        if (isBotTyping && !originalText) {
            return;
        }

        const box = document.createElement("div");
        box.className = "msg-box bot-box";

        if (msg.firestoreId) box.dataset.firestoreId = msg.firestoreId;
        if (msg.messageId) box.dataset.messageId = msg.messageId;

        const time = formatTime(msg.timestamp || Date.now());

        // Sử dụng formatMessageContent cho bot messages để hỗ trợ code blocks
        let contentHtml = renderBotMarkdown(originalText);
        if (msg.isError) {
            contentHtml = `<span class="chatbot-error-text" style="color: #ff6b6b;">${renderPlainTextContent(originalText)}</span>`;
        }


        // Nếu đây là tin nhắn đang streaming (tin cuối cùng), thêm ID streaming để code JS tìm thấy
        const isStreamingMsg = isStreamingActive && msg.messageId === chatbotSession.messages[chatbotSession.messages.length - 1]?.id;

        box.innerHTML = `
            <div class="msg bot ${msg.isError ? 'chatbot-error' : ''}" title="${formatFullTime(msg.timestamp || Date.now())}">
                <div class="msg-actions">
                    <button class="action-btn copy-btn" title="${uiText('Sao chép', 'Copy')}"><i class="fas fa-copy"></i></button>
                </div>
                <div id="${isStreamingMsg ? 'streaming_' + msg.messageId : ''}" class="${isStreamingMsg ? 'streaming-text' : ''}">${contentHtml}</div>
            </div>
            <div class="time">${time}</div>
        `;

        if (messagesDiv) {
            maybeInsertDayDivider(msg.timestamp || Date.now());
            messagesDiv.appendChild(box);
            scrollToBottomIfAllowed();
        }

        return;
    }

    const box = document.createElement("div");
    const isMe = msg.sender === currentUserUid;
    box.className = isMe ? "msg-box me-box" : "msg-box friend-box";

    if (msg.firestoreId) box.dataset.firestoreId = msg.firestoreId;
    if (msg.messageId) box.dataset.messageId = msg.messageId;

    const time = formatTime(msg.timestamp || Date.now());

    if (msg.type === "call_event") {
        box.className = isMe ? "msg-box me-box call-event-box me-call-event" : "msg-box friend-box call-event-box friend-call-event";
        const meta = msg.callMeta || {};
        const callText = originalText || buildCallEventText(meta.callType, meta.outcome, meta.durationSec);

        box.innerHTML = `
            <div class="msg ${isMe ? 'me' : 'other'} call-event-pill">
                <i class="fas fa-phone-alt call-event-icon"></i>
                <div class="call-event-content">
                    <div class="call-event-title">${escapeHtml(callText)}</div>
                </div>
            </div>
            <div class="time">${time}</div>
        `;
        if (messagesDiv) {
            maybeInsertDayDivider(msg.timestamp || Date.now());
            messagesDiv.appendChild(box);
            scrollToBottomIfAllowed();
        }
        return;
    }

    let contentHtml = renderPlainTextContent(originalText);
    if (msg.type === "image") {
        contentHtml = `<img src="${msg.mediaURL || originalText}" class="msg-media">`;
        if (originalText) {
            contentHtml += `<div class="file-caption">${escapeHtml(originalText)}</div>`;
        }
    } else if (msg.type === "video") {
        contentHtml = `<video src="${msg.mediaURL || originalText}" controls class="msg-media"></video>`;
        if (originalText) {
            contentHtml += `<div class="file-caption">${escapeHtml(originalText)}</div>`;
        }
    } else if (msg.type === "file") {
        const displayName = msg.fileName || originalText || uiText('Tệp đính kèm', 'Attachment');
        contentHtml = `<div class="file-message">
            <i class="fas fa-file"></i>
            <span>${escapeHtml(displayName)}</span>
            <a href="${msg.mediaURL || '#'}" download>${uiText('Tải xuống', 'Download')}</a>
        </div>`;
        if (originalText && msg.fileName && originalText !== msg.fileName) {
            contentHtml += `<div class="file-caption">${escapeHtml(originalText)}</div>`;
        }
    }

    const statusIcon = getStatusIcon(msg.seen ? 'seen' : (msg.status || 'sent'));

    box.innerHTML = `
        <div class="msg ${isMe ? 'me' : 'other'}" title="${formatFullTime(msg.timestamp || Date.now())}">
            <div class="msg-actions">
                ${isMe ? '<button class="action-btn edit-btn" title="Edit"><i class="fas fa-edit"></i></button>' : ''}
                <button class="action-btn copy-btn" title="${uiText('Sao chép', 'Copy')}"><i class="fas fa-copy"></i></button>
            </div>
            <div class="msg-text">${contentHtml}</div>
        </div>
        <div class="time">${time}</div>
        ${isMe ? `<div class="status-message ${msg.seen ? 'seen' : 'sent'}">${statusIcon}</div>` : ""}
    `;

    if (messagesDiv) {
        maybeInsertDayDivider(msg.timestamp || Date.now());
        messagesDiv.appendChild(box);
        scrollToBottomIfAllowed();
    }
}

// =======================================================
// ✅ CẬP NHẬT TRẠNG THÁI TIN NHẮN
// =======================================================
function updateMessageStatus(msgId, status) {
    const msgElement = document.querySelector(`[data-firestore-id='${msgId}']`) ||
        document.querySelector(`[data-key='${msgId}']`);

    if (msgElement && status) {
        const statusDiv = msgElement.querySelector(".status-message");
        if (statusDiv) {
            statusDiv.className = `status-message ${status}`;
            statusDiv.innerHTML = getStatusIcon(status);
        }
    }
}

// =======================================================
// ✅ TIỆN ÍCH - GET STATUS ICON
// =======================================================
function getStatusIcon(status) {
    switch (status) {
        case "sending":
            return `<div class="sending-dots"><span></span><span></span><span></span></div>`;
        case "sent":
            return "✓";
        case "delivered":
            return "✓✓";
        case "seen":
            return "✓✓";
        default:
            return "✓";
    }
}

// =======================================================
// ✅ CALL FUNCTIONS (GIỮ NGUYÊN)
// =======================================================

let currentCallerUid = null;
let currentCallerName = null;
let peerConnection = null;
let localStream = null;
let currentCallType = null;
let isCaller = false;
let currentReceiver = null;
let isCallInProgress = false;
let incomingOfferSDP = null;
let callTimeout = null;
let callConnectTimestamp = null;

const peerConfiguration = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
        { urls: 'stun:stun.1und1.de:3478' }
    ],
    sdpSemantics: 'unified-plan'
};

async function startCall(callType) {
    console.log(`📞 startCall called: ${callType}, socket:`, socket?.connected);

    if (isCallInProgress) {
        showToast(uiText('Đang trong cuộc gọi khác', 'Another call is already in progress'), 'error');
        return;
    }

    if (!selectedFriendUid) {
        showToast(uiText('Vui lòng chọn bạn để gọi', 'Please choose a friend to call'), 'error');
        return;
    }

    if (!socket || !socket.connected) {
        showToast(uiText('Không thể kết nối. Vui lòng thử lại sau.', 'Connection failed. Please try again later.'), 'error');
        return;
    }

    console.log(`📞 Bắt đầu cuộc gọi ${callType} đến ${selectedFriendName}`);

    // Hiển thị call area
    if (callArea) {
        callArea.style.display = 'flex';
        callArea.classList.add('active');
    }

    // Cập nhật tên người gọi
    const callFriendName = document.getElementById('callFriendName');
    const callStatusText = document.getElementById('callStatusText');
    if (callFriendName) callFriendName.textContent = selectedFriendName;
    if (callStatusText) callStatusText.textContent = uiText('Đang kết nối...', 'Connecting...');
    if (callTimer) callTimer.textContent = '00:00';

    if (callAnimationContainer) callAnimationContainer.style.display = 'flex';

    // Lấy media (mic/camera)
    if (!await getMedia(callType)) {
        if (callAnimationContainer) {
            callAnimationContainer.style.display = 'none';
        }
        return;
    }

    isCaller = true;
    isCallInProgress = true;
    currentCallType = callType;
    currentReceiver = selectedFriendUid;
    callConnectTimestamp = null;

    // Tạo peer connection
    try {
        createPeerConnection();

        // Thêm tracks từ local stream
        localStream.getTracks().forEach(track => {
            if (peerConnection) {
                peerConnection.addTrack(track, localStream);
            }
        });

        // Tạo offer
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);

        // Gửi yêu cầu gọi qua socket
        socket.emit('call_request', {
            sender: currentUserUid,
            receiver: selectedFriendUid,
            callType: callType,
            senderName: currentUserName,
            timestamp: Date.now()
        });

        // Gửi SDP offer
        socket.emit('webrtc_sdp', {
            sender: currentUserUid,
            receiver: selectedFriendUid,
            sdp: peerConnection.localDescription
        });

        if (callStatusText) callStatusText.textContent = uiText('Đang đổ chuông...', 'Ringing...');

        // Timeout sau 30 giây
        if (callTimeout) clearTimeout(callTimeout);
        callTimeout = setTimeout(() => {
            if (isCallInProgress) {
                endCall({ isTimeout: true, outcome: 'no_answer' });
                if (callStatusText) callStatusText.textContent = uiText('Không trả lời', 'No answer');
                if (callAnimationContainer) {
                    callAnimationContainer.style.display = 'none';
                }
                setTimeout(() => {
                    if (callArea) {
                        callArea.style.display = 'none';
                        callArea.classList.remove('active');
                    }
                }, 3000);
            }
        }, 30000);

        console.log('✅ Đã gửi yêu cầu gọi');

    } catch (error) {
        console.error('❌ Lỗi tạo offer:', error);
        endCall({ outcome: 'media_error' });
        showToast(uiText('Lỗi khi bắt đầu cuộc gọi', 'Failed to start the call'), 'error');
    }
}

function appendBotSystemMessage(text, options = {}) {
    const { isError = false, persist = true, excludeFromHistory = true } = options;
    const rawText = repairMojibake(text || "");
    if (!rawText) return null;

    const messageId = `bot_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const timestamp = Date.now();

    if (persist && currentUserUid) {
        saveToChatbotSession({
            id: messageId,
            type: "bot_message",
            text: rawText,
            rawText: rawText,
            timestamp,
            sender: CHATBOT_UID,
            receiver: currentUserUid,
            excludeFromHistory
        });
    }

    renderMessage({
        sender: CHATBOT_UID,
        receiver: currentUserUid,
        text: rawText,
        rawText: rawText,
        type: "bot_message",
        timestamp,
        isBot: true,
        isError,
        messageId
    });

    return messageId;
}

function resetCallState() {
    console.log('🔄 Resetting call state');

    if (callTimeout) {
        clearTimeout(callTimeout);
        callTimeout = null;
    }

    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }

    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }

    isCallInProgress = false;
    isCaller = false;
    currentCallType = null;
    currentReceiver = null;
    currentCallerUid = null;
    currentCallerName = null;
    incomingOfferSDP = null;

    if (localVideo) {
        localVideo.srcObject = null;
        localVideo.style.display = 'none';
        localVideo.pause();
    }
    if (remoteVideo) {
        remoteVideo.srcObject = null;
        remoteVideo.style.display = 'none';
        remoteVideo.pause();
    }

    if (endCallBtn) endCallBtn.style.display = 'none';
    if (acceptCallBtn) acceptCallBtn.style.display = 'none';
    if (declineCallBtn) declineCallBtn.style.display = 'none';

    if (callArea) {
        callArea.style.display = 'none';
        callArea.classList.remove('active');
    }
    if (incomingCallCard) incomingCallCard.style.display = 'none';
    if (callAnimationContainer) callAnimationContainer.style.display = 'none';

    if (localAvatar) localAvatar.style.display = 'none';
    if (remoteAvatar) remoteAvatar.style.display = 'flex'; // Default to flex

    const callStatusText = document.getElementById('callStatusText');
    if (callStatusText) callStatusText.textContent = '';
    if (callTimer) callTimer.textContent = '';

    if (muteBtn) {
        muteBtn.innerHTML = '<i class="fas fa-microphone"></i>';
        muteBtn.classList.remove('active');
        muteBtn.style.display = 'none';
    }
    if (videoToggleBtn) {
        videoToggleBtn.innerHTML = '<i class="fas fa-video"></i>';
        videoToggleBtn.classList.remove('active');
        videoToggleBtn.style.display = 'none';
    }

    // Bật lại nút gọi nếu không bị block
    if (!isCurrentUserBlockedByFriend) {
        if (voiceCallBtn) voiceCallBtn.disabled = false;
        if (videoCallBtn) videoCallBtn.disabled = false;
    }

    console.log("[Call] ✅ All call state reset complete.");
}

async function getMedia(callType) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.error("❌ MediaDevices API not supported on this browser.");
        showToast(uiText('Trình duyệt của bạn không hỗ trợ tính năng gọi.', 'Your browser does not support calling.'), "error");
        resetCallState();
        return false;
    }

    try {
        const constraints = {
            audio: true,
            video: callType === 'video' ? {
                facingMode: 'user'
            } : false
        };

        console.log('🎙️ Requesting media with constraints:', constraints);

        localStream = await navigator.mediaDevices.getUserMedia(constraints);

        if (localVideo) {
            localVideo.srcObject = localStream;
            localVideo.style.display = callType === 'video' ? 'block' : 'none';

            if (localAvatar) {
                localAvatar.style.display = callType === 'voice' ? 'flex' : 'none';
            }

            localVideo.onloadedmetadata = () => {
                localVideo.play().catch(err => console.error('❌ Lỗi play local video:', err));
            };
        }

        if (muteBtn) {
            muteBtn.style.display = 'flex';
            muteBtn.classList.add('active');
        }

        if (videoToggleBtn) {
            videoToggleBtn.style.display = callType === 'video' ? 'flex' : 'none';
            if (callType === 'video') videoToggleBtn.classList.add('active');
        }

        if (switchBtn) {
            switchBtn.style.display = callType === 'video' ? 'flex' : 'none';
        }

        if (speakerBtn) {
            speakerBtn.style.display = 'flex';
            speakerBtn.classList.add('active');
        }

        console.log('✅ Media đã sẵn sàng:', callType);
        return true;

    } catch (error) {
        console.error('❌ Lỗi lấy media:', error);

        let errorMsg = uiText('Không thể truy cập microphone/camera. ', 'Could not access the microphone/camera. ');
        if (error.name === 'NotAllowedError') {
            errorMsg += uiText('Vui lòng cấp quyền truy cập.', 'Please grant permission.');
        } else if (error.name === 'NotFoundError') {
            errorMsg += uiText('Không tìm thấy thiết bị.', 'No device was found.');
        } else {
            errorMsg += error.message;
        }

        const callStatusText = document.getElementById('callStatusText');
        if (callStatusText) callStatusText.textContent = errorMsg;
        showToast(errorMsg, 'error');

        resetCallState();
        return false;
    }
}

function createPeerConnection() {
    peerConnection = new RTCPeerConnection(peerConfiguration);

    peerConnection.onicecandidate = (event) => {
        if (event.candidate && socket) {
            socket.emit('webrtc_ice_candidate', {
                sender: currentUserUid,
                receiver: isCaller ? currentReceiver : currentCallerUid,
                candidate: event.candidate
            });
        }
    };

    peerConnection.ontrack = (event) => {
        console.log('📹 Nhận remote track:', event.track.kind);

        if (remoteVideo && event.streams && event.streams[0]) {
            remoteVideo.srcObject = event.streams[0];
            remoteVideo.style.display = currentCallType === 'video' ? 'block' : 'none';

            if (remoteAvatar) {
                remoteAvatar.style.display = currentCallType === 'voice' ? 'flex' : 'none';
            }

            remoteVideo.onloadedmetadata = () => {
                remoteVideo.play().catch(err => console.error('❌ Lỗi play remote video:', err));
            };

            if (callAnimationContainer) {
                callAnimationContainer.style.display = 'none';
            }

            startCallTimer();
            if (!callConnectTimestamp) callConnectTimestamp = Date.now();

            const callStatusText = document.getElementById('callStatusText');
            if (callStatusText) {
                callStatusText.textContent = uiText('Đã kết nối', 'Connected');
            }
        }
    };

    peerConnection.onconnectionstatechange = () => {
        console.log('🔗 Connection state:', peerConnection.connectionState);

        if (peerConnection.connectionState === 'connected') {
            if (callTimeout) {
                clearTimeout(callTimeout);
                callTimeout = null;
            }
        } else if (peerConnection.connectionState === 'failed' ||
            peerConnection.connectionState === 'disconnected') {
            console.warn('⚠️ Connection failed/disconnected');
            endCall({ outcome: 'network_error' });
            showToast(uiText('Cuộc gọi bị ngắt kết nối', 'Call connection was lost'), 'error');
        }
    };

    peerConnection.oniceconnectionstatechange = () => {
        console.log('🧊 ICE state:', peerConnection.iceConnectionState);

        if (peerConnection.iceConnectionState === 'failed') {
            console.error('❌ ICE connection failed');
            endCall({ outcome: 'network_error' });
            showToast(uiText('Lỗi kết nối mạng', 'Network connection error'), 'error');
        }
    };

    console.log('✅ Peer connection đã được tạo');
}

// Call timer
let callStartTime = null;
let callTimerInterval = null;

function startCallTimer() {
    callStartTime = Date.now();
    if (callTimerInterval) clearInterval(callTimerInterval);

    callTimerInterval = setInterval(() => {
        if (callStartTime && callTimer) {
            const elapsed = Date.now() - callStartTime;
            const minutes = Math.floor(elapsed / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            callTimer.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

function stopCallTimer() {
    if (callTimerInterval) {
        clearInterval(callTimerInterval);
        callTimerInterval = null;
    }
    callStartTime = null;
}

function formatCallDuration(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function buildCallEventText(callType, outcome, durationSec) {
    const label = callType === 'video' ? uiText('Cuộc gọi video', 'Video call') : uiText('Cuộc gọi thoại', 'Voice call');
    if (outcome === 'declined') return `${label} ${uiText('đã bị từ chối', 'was declined')}`;
    if (outcome === 'no_answer') return `${label} ${uiText('không trả lời', 'was not answered')}`;
    if (outcome === 'missed') return uiText(`Cuộc gọi nhỡ (${callType === 'video' ? 'video' : 'thoại'})`, `Missed ${callType === 'video' ? 'video' : 'voice'} call`);
    if (outcome === 'media_error') return uiText(`${label} thất bại (lỗi thiết bị)`, `${label} failed (device error)`);
    if (outcome === 'network_error') return uiText(`${label} bị ngắt kết nối`, `${label} lost connection`);
    if ((outcome === 'ended' || outcome === 'remote_end') && durationSec > 0) {
        return `${label} • ${formatCallDuration(durationSec)}`;
    }
    return uiText(`${label} đã kết thúc`, `${label} ended`);
}

async function logCallEventToChat({ peerUid, callType, outcome, durationSec = 0 }) {
    if (!peerUid || !currentUserUid || peerUid === CHATBOT_UID) return;
    try {
        const chatId = [currentUserUid, peerUid].sort().join("_");
        const messagesRef = collection(db, "chats", chatId, "messages");
        const messageId = `call_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
        const content = buildCallEventText(callType, outcome, durationSec);
        const callMeta = {
            callType: callType || "voice",
            outcome: outcome || "ended",
            durationSec: Math.max(0, Math.floor(Number(durationSec) || 0))
        };

        const firestoreMsg = {
            from: currentUserUid,
            to: peerUid,
            content,
            type: "call_event",
            callMeta,
            timestamp: serverTimestamp(),
            status: "sent",
            messageId: messageId
        };

        const docRef = await addDoc(messagesRef, firestoreMsg);
        const ts = Date.now();
        if (socket && socket.connected) {
            socket.emit('send_message', {
                ...firestoreMsg,
                timestamp: ts,
                firestoreId: docRef.id
            });
        }

        emitLastMessageUpdated(peerUid, {
            text: content,
            rawText: content,
            type: "call_event",
            timestamp: ts,
            sender: currentUserUid
        });
        emitNewMessageForFriend(peerUid, {
            text: content,
            rawText: content,
            type: "call_event",
            timestamp: ts,
            sender: currentUserUid
        }, 0);

        if (!activeMessagesUnsubscribe && selectedFriendUid === peerUid) {
            renderMessage({
                firestoreId: docRef.id,
                messageId,
                sender: currentUserUid,
                receiver: peerUid,
                text: content,
                rawText: content,
                type: "call_event",
                callMeta,
                timestamp: ts
            });
        }
    } catch (err) {
        console.error("Lỗi lưu call_event:", err);
    }
}

function handleIncomingCall(data) {
    console.log('📞 Cuộc gọi đến từ:', data.senderName);

    currentCallerUid = data.sender;
    currentCallerName = data.senderName;
    currentCallType = data.callType;

    if (incomingCallCard) {
        const callerNameLabel = document.getElementById('callerNameLabel');
        const callerTypeLabel = document.getElementById('callerTypeLabel');

        if (callerNameLabel) callerNameLabel.textContent = data.senderName;

        // Cập nhật tên vào call area trước khi nhấc máy
        const callFriendName = document.getElementById('callFriendName');
        if (callFriendName) callFriendName.textContent = data.senderName;

        const remoteName = document.getElementById('remoteName');
        if (remoteName) remoteName.textContent = data.senderName.charAt(0).toUpperCase();

        if (callerTypeLabel) {
            callerTypeLabel.textContent = data.callType === 'video' ? uiText('Cuộc gọi video', 'Video call') : uiText('Cuộc gọi thoại', 'Voice call');
        }

        incomingCallCard.style.display = 'flex';
    }

    if (callTimeout) clearTimeout(callTimeout);
    callTimeout = setTimeout(() => {
        if (incomingCallCard && incomingCallCard.style.display === 'flex') {
            answerCall(false, 'NoAnswer');
        }
    }, 30000);
}

async function answerCall(accept, declineReason = "Declined") {
    if (callTimeout) {
        clearTimeout(callTimeout);
        callTimeout = null;
    }

    if (!accept) {
        if (socket && currentCallerUid) {
            socket.emit('call_response', {
                sender: currentCallerUid,
                receiver: currentUserUid,
                accepted: false,
                reason: declineReason
            });
        }

        if (incomingCallCard) incomingCallCard.style.display = 'none';
        resetCallState();
        showToast(uiText('Đã từ chối cuộc gọi', 'Call declined'), 'info');
        return;
    }

    console.log('✅ Chấp nhận cuộc gọi từ:', currentCallerName);

    if (incomingCallCard) incomingCallCard.style.display = 'none';
    if (callArea) {
        callArea.style.display = 'flex';
        callArea.classList.add('active');
    }

    const callStatusText = document.getElementById('callStatusText');
    if (callStatusText) callStatusText.textContent = uiText('Đang kết nối...', 'Connecting...');
    if (callTimer) callTimer.textContent = '00:00';

    if (!await getMedia(currentCallType)) {
        socket.emit('call_response', {
            sender: currentCallerUid,
            receiver: currentUserUid,
            accepted: false,
            reason: "Media Error"
        });
        return;
    }

    isCallInProgress = true;
    isCaller = false;
    callConnectTimestamp = null;

    createPeerConnection();

    localStream.getTracks().forEach(track => {
        peerConnection.addTrack(track, localStream);
    });

    if (incomingOfferSDP) {
        try {
            await peerConnection.setRemoteDescription(new RTCSessionDescription(incomingOfferSDP));

            const answer = await peerConnection.createAnswer();
            await peerConnection.setLocalDescription(answer);

            socket.emit('webrtc_sdp', {
                sender: currentUserUid,
                receiver: currentCallerUid,
                sdp: peerConnection.localDescription
            });

            socket.emit('call_response', {
                sender: currentCallerUid,
                receiver: currentUserUid,
                accepted: true,
                callType: currentCallType
            });

            if (endCallBtn) endCallBtn.style.display = 'block';
            if (acceptCallBtn) acceptCallBtn.style.display = 'none';
            if (declineCallBtn) declineCallBtn.style.display = 'none';

            console.log('✅ Đã gửi answer và chấp nhận cuộc gọi');

        } catch (error) {
            console.error('❌ Lỗi khi chấp nhận cuộc gọi:', error);
            endCall({ outcome: 'media_error' });
            showToast(uiText('Lỗi khi chấp nhận cuộc gọi', 'Failed to accept the call'), 'error');
        }
    }
}

function endCall(options = {}) {
    const isTimeout = options === true ? true : !!options.isTimeout;
    const notifyPeer = typeof options === 'object' && options.notifyPeer === false ? false : true;
    const outcome = (typeof options === 'object' && options.outcome) ? options.outcome : (isTimeout ? 'no_answer' : 'ended');
    console.log('📞 Kết thúc cuộc gọi...');

    const receiver = isCaller ? currentReceiver : currentCallerUid;
    const callType = currentCallType || 'voice';
    const durationSec = callConnectTimestamp ? Math.floor((Date.now() - callConnectTimestamp) / 1000) : 0;

    stopCallTimer();

    if (socket && isCallInProgress && notifyPeer) {
        if (receiver) {
            socket.emit('call_end', {
                sender: currentUserUid,
                receiver: receiver,
                outcome: outcome
            });
        }
    }
    if (receiver && isCaller) {
        logCallEventToChat({ peerUid: receiver, callType, outcome, durationSec });
    }

    resetCallState();

    if (isTimeout) {
        showToast(uiText('Cuộc gọi đã kết thúc', 'The call has ended'), 'info');
    } else {
        showToast(uiText('Đã kết thúc cuộc gọi', 'Call ended'), 'info');
    }
}

async function handleWebRTCSDP(data) {
    if (!peerConnection) return;

    try {
        if (data.sdp.type === 'offer') {
            incomingOfferSDP = data.sdp;

            if (!isCaller && currentCallerUid === data.sender) {
                await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));

                const answer = await peerConnection.createAnswer();
                await peerConnection.setLocalDescription(answer);

                socket.emit('webrtc_sdp', {
                    sender: currentUserUid,
                    receiver: data.sender,
                    sdp: peerConnection.localDescription
                });
            }
        } else if (data.sdp.type === 'answer') {
            await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
        }
    } catch (error) {
        console.error('❌ Lỗi xử lý SDP:', error);
    }
}

function handleWebRTCCandidate(data) {
    if (!peerConnection) return;

    try {
        peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
    } catch (error) {
        console.error('❌ Lỗi xử lý ICE candidate:', error);
    }
}

function handleCallResponse(data) {
    if (data.accepted) {
        console.log('✅ Cuộc gọi được chấp nhận');
        callConnectTimestamp = Date.now();
        const callStatusText = document.getElementById('callStatusText');
        if (callStatusText) callStatusText.textContent = uiText('Đã kết nối', 'Connected');
        if (callAnimationContainer) callAnimationContainer.style.display = 'none';
        showToast(uiText('Cuộc gọi đã được chấp nhận', 'Call accepted'), 'success');
    } else {
        console.log('❌ Cuộc gọi bị từ chối:', data.reason);
        const outcome = data.reason === 'Declined' ? 'declined' : 'no_answer';
        endCall({ notifyPeer: false, outcome });

        const callStatusText = document.getElementById('callStatusText');
        if (callStatusText) {
            callStatusText.textContent = data.reason === 'Declined' ? uiText('Đã từ chối', 'Declined') : uiText('Không trả lời', 'No answer');
        }
        showToast(
            uiText(`Cuộc gọi bị từ chối: ${data.reason}`, `Call was declined: ${data.reason}`),
            'error'
        );
    }
}

function toggleMic() {
    if (!localStream || !muteBtn) return;
    const track = localStream.getAudioTracks()[0];
    if (track) {
        track.enabled = !track.enabled;
        muteBtn.innerHTML = track.enabled ? '<i class="fas fa-microphone"></i>' : '<i class="fas fa-microphone-slash"></i>';
        muteBtn.classList.toggle('active');
        showToast(track.enabled ? uiText('Đã bật mic', 'Microphone enabled') : uiText('Đã tắt mic', 'Microphone muted'), 'info');
    }
}

function toggleCamera() {
    if (!localStream || !videoToggleBtn) return;
    const track = localStream.getVideoTracks()[0];
    if (track) {
        track.enabled = !track.enabled;
        videoToggleBtn.innerHTML = track.enabled ? '<i class="fas fa-video"></i>' : '<i class="fas fa-video-slash"></i>';
        videoToggleBtn.classList.toggle('active', track.enabled);
        showToast(track.enabled ? uiText('Đã bật camera', 'Camera enabled') : uiText('Đã tắt camera', 'Camera disabled'), 'info');
    }
}

async function switchCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.error("❌ MediaDevices API not supported on this browser.");
        showToast(uiText('Trình duyệt của bạn không hỗ trợ tính năng này.', 'Your browser does not support this feature.'), "error");
        return;
    }

    if (!localStream || currentCallType !== 'video') return;

    try {
        const videoTrack = localStream.getVideoTracks()[0];
        if (!videoTrack) return;

        const settings = videoTrack.getSettings();
        const currentFacingMode = settings ? settings.facingMode : 'user';
        const newFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';

        console.log(`🔄 Switching camera to: ${newFacingMode}`);

        const newStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: newFacingMode }
        });

        const newVideoTrack = newStream.getVideoTracks()[0];

        if (peerConnection) {
            const sender = peerConnection.getSenders().find(s => s.track.kind === 'video');
            if (sender) {
                sender.replaceTrack(newVideoTrack);
            }
        }

        localStream.removeTrack(videoTrack);
        videoTrack.stop();
        localStream.addTrack(newVideoTrack);

        if (localVideo) {
            localVideo.srcObject = localStream;
        }

        showToast(
            uiText(
                `Đã chuyển sang camera ${newFacingMode === 'user' ? 'trước' : 'sau'}`,
                `Switched to the ${newFacingMode === 'user' ? 'front' : 'rear'} camera`
            ),
            'info'
        );

    } catch (error) {
        console.error('❌ Lỗi chuyển camera:', error);
        showToast(uiText('Không thể chuyển camera', 'Could not switch camera'), 'error');
    }
}

function toggleSpeaker() {
    if (!speakerBtn) return;
    // Note: Browser doesn't give direct control over speaker/earpiece on most devices
    // We just toggle the UI state as a representation
    const isActive = speakerBtn.classList.toggle('active');
    speakerBtn.innerHTML = isActive ? '<i class="fas fa-volume-up"></i>' : '<i class="fas fa-volume-mute"></i>';
    showToast(isActive ? uiText('Đã bật loa ngoài', 'Speaker enabled') : uiText('Đã tắt loa ngoài', 'Speaker disabled'), 'info');
}

// =======================================================
// ✅ ĐÁNH DẤU TẤT CẢ TIN NHẮN LÀ ĐÃ XEM
// =======================================================
async function markAllMessagesAsSeen(friendUid) {
    if (!currentUserUid || !friendUid || !convId) return;

    try {
        console.log(`👀 Đang đánh dấu tất cả tin nhắn từ ${friendUid} là đã xem...`);

        document.querySelectorAll(`[data-firestore-id]`).forEach(box => {
            const statusDiv = box.querySelector(".status-message");
            if (statusDiv) {
                statusDiv.textContent = uiText('Đã xem', 'Seen');
                statusDiv.className = "status-message seen";
            }
        });

        const messagesRef = collection(db, "chats", convId, "messages");
        const q = query(messagesRef,
            where("to", "==", currentUserUid),
            where("status", "in", ["sent", "delivered"])
        );

        const snapshot = await getDocs(q);
        const batch = [];

        snapshot.forEach((doc) => {
            const docRef = doc.ref;
            batch.push(updateDoc(docRef, {
                status: "seen",
                seenAt: serverTimestamp()
            }));
        });

        if (batch.length > 0) {
            await Promise.all(batch);
            console.log(`✅ Đã đánh dấu ${batch.length} tin nhắn là đã xem trong Firestore`);
        }

        if (socket) {
            socket.emit('mark_all_seen', {
                sender: friendUid,
                receiver: currentUserUid,
                convId: convId
            });
        }

        await updateUnreadCount(friendUid, 'reset');

    } catch (error) {
        console.error("❌ Lỗi khi đánh dấu tất cả tin nhắn đã xem:", error);
    }
}

// =======================================================
// ✅ TIỆN ÍCH - HÀM THÔNG BÁO
// =======================================================
function showToast(message, type = 'info') {
    message = repairMojibake(message);
    // Xóa toast cũ nếu có
    const oldToasts = document.querySelectorAll('.toast');
    oldToasts.forEach(toast => {
        toast.style.animation = 'slideOut 0.3s ease-out forwards';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 300);
    });

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

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
// ✅ KHỞI TẠO AUDIO CONTEXT KHI NGƯỜI DÙNG TƯƠNG TÁC
// =======================================================
document.addEventListener('click', initAudioContext);
document.addEventListener('keydown', initAudioContext);

// =======================================================
// ✅ LOAD THEME TỪ LOCALSTORAGE
// =======================================================
function loadThemeFromStorage() {
    applyThemePreference(getCurrentTheme());
}

// =======================================================
// ✅ THÊM CSS CHO ANIMATIONS
// =======================================================
function addCustomStyles() {
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(-50%) translateY(-16px);
                opacity: 0;
            }
            to {
                transform: translateX(-50%) translateY(0);
                opacity: 1;
            }
        }
        
        @keyframes slideOut {
            from {
                transform: translateX(-50%) translateY(0);
                opacity: 1;
            }
            to {
                transform: translateX(-50%) translateY(-16px);
                opacity: 0;
            }
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: scale(0.9); }
            to { opacity: 1; transform: scale(1); }
        }
        
        @keyframes pulse {
            0%,
            100% {
                transform: scale(1);
                opacity: 1;
            }
            50% {
                transform: scale(1.1);
                opacity: 0.8;
            }
        }
        
        .emoji-picker button:hover {
            background: rgba(255,255,255,0.1) !important;
            transform: scale(1.1) !important;
        }
        .emoji-picker {
            position: absolute;
            bottom: 58px;
            left: 10px;
            width: 320px;
            max-width: calc(100vw - 24px);
            background: rgba(15, 17, 35, 0.98);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.45);
            padding: 10px;
            z-index: 50;
        }
        .emoji-recent {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 6px;
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .emoji-pack-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
        }
        .emoji-pack-btn {
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(255,255,255,0.04);
            color: #fff;
            border-radius: 10px;
            width: 36px;
            height: 32px;
            cursor: pointer;
        }
        .emoji-pack-btn.active {
            border-color: rgba(0,212,255,0.6);
            background: rgba(0,212,255,0.14);
        }
        .emoji-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 6px;
        }
        .emoji-picker-button {
            border: none;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            height: 36px;
            font-size: 20px;
            cursor: pointer;
        }
        .emoji-rail {
            width: 100%;
            display: flex;
            gap: 8px;
            padding: 0 4px 6px 4px;
            overflow-x: auto;
            scrollbar-width: none;
        }
        .emoji-rail::-webkit-scrollbar {
            display: none;
        }
        .emoji-rail-btn {
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(255,255,255,0.06);
            border-radius: 10px;
            min-width: 34px;
            height: 30px;
            font-size: 18px;
            line-height: 1;
            cursor: pointer;
            flex: 0 0 auto;
        }
        .call-event-box {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            margin: 14px 0;
        }
        .me-call-event {
            align-items: flex-end;
        }
        .call-event-pill {
            display: inline-flex;
            align-items: flex-start;
            gap: 10px;
            padding: 12px 16px;
            min-width: 320px;
            max-width: min(82%, 560px);
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(0,212,255,0.16), rgba(255,107,157,0.14));
            border: 1px solid rgba(0,212,255,0.4);
            color: rgba(255,255,255,0.96);
            font-size: 14px;
            box-shadow: 0 8px 18px rgba(0,0,0,0.25);
        }
        .call-event-icon {
            margin-top: 2px;
        }
        .call-event-content {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .call-event-title {
            font-weight: 600;
            line-height: 1.2;
        }
        .call-event-meta {
            font-size: 12px;
            color: rgba(255,255,255,0.82);
        }
        
        .recording-indicator {
            animation: pulse 1s infinite !important;
        }
        
        .call-overlay.active {
            display: flex !important;
            animation: fadeIn 0.3s ease-out;
        }
        
        /* Fix cho nút gọi trong header */
        .chat-container.has-friend #voiceCallBtn:not(:disabled),
        .chat-container.has-friend #videoCallBtn:not(:disabled) {
            opacity: 1 !important;
            pointer-events: auto !important;
            cursor: pointer !important;
        }
        
        .chat-container.has-friend #voiceCallBtn:hover:not(:disabled),
        .chat-container.has-friend #videoCallBtn:hover:not(:disabled) {
            transform: scale(1.1) !important;
            box-shadow: 0 5px 15px rgba(0, 212, 255, 0.4) !important;
        }
        
        /* Animations cho chatbot */
        @keyframes fadeOut {
            from { opacity: 1; transform: translateY(0); }
            to { opacity: 0; transform: translateY(10px); }
        }
        
        .typing-persist {
            animation: typingPersist 0.5s ease-out forwards !important;
            animation-iteration-count: 1 !important;
        }
        
        @keyframes typingPersist {
            0% {
                opacity: 0;
                transform: translateY(10px);
            }
            50% {
                opacity: 0.5;
                transform: translateY(5px);
            }
            100% {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        /* CSS cho chatbot typing */
        .chatbot-typing {
            display: flex;
            align-items: center;
            padding: 10px 15px;
            background: rgba(0, 212, 255, 0.1);
            border-radius: 15px;
            margin: 10px;
            border: 1px solid rgba(0, 212, 255, 0.2);
            backdrop-filter: blur(10px);
        }
        
        .chatbot-avatar {
            width: 30px;
            height: 30px;
            background: linear-gradient(135deg, #00d4ff, #0099ff);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            margin-right: 10px;
        }
        
        .ai-typing-dots {
            display: flex;
            gap: 4px;
            margin-right: 10px;
        }
        
        .ai-typing-dots span {
            width: 8px;
            height: 8px;
            background: #00d4ff;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out both;
        }
        
        .ai-typing-dots span:nth-child(1) { animation-delay: -0.32s; }
        .ai-typing-dots span:nth-child(2) { animation-delay: -0.16s; }
        
        .typing-text {
            color: #00d4ff;
            font-size: 14px;
            font-weight: 500;
        }
        
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1.0); }
        }
        
        .bot-box .msg.bot {
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(100, 126, 234, 0.1));
            border: 1px solid rgba(0, 212, 255, 0.2);
        }
        
        .ai-badge {
            position: absolute;
            bottom: 5px;
            right: 10px;
            font-size: 10px;
            color: #00d4ff;
            background: rgba(0, 212, 255, 0.1);
            padding: 2px 6px;
            border-radius: 10px;
        }
        
        .response-time {
            position: absolute;
            top: 5px;
            right: 10px;
            font-size: 11px;
            color: #888;
            font-style: italic;
        }
        
        /* CSS cho nút điều khiển streaming */
        .bot-streaming-controls {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin: 15px 0;
            padding: 10px;
            background: rgba(0, 212, 255, 0.05);
            border-radius: 12px;
            border: 1px solid rgba(0, 212, 255, 0.1);
            backdrop-filter: blur(10px);
            animation: fadeIn 0.3s ease-out;
        }
        
        .streaming-control-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            color: white;
        }
        
        .streaming-control-btn i {
            font-size: 12px;
        }
        
        .pause-btn {
            background: linear-gradient(135deg, #ffaa00, #ff8800);
            box-shadow: 0 4px 10px rgba(255, 170, 0, 0.3);
        }
        
        .pause-btn:hover {
            background: linear-gradient(135deg, #ffbb33, #ff9900);
            transform: translateY(-2px);
            box-shadow: 0 6px 15px rgba(255, 170, 0, 0.4);
        }
        
        .resume-btn {
            background: linear-gradient(135deg, #00d4ff, #0099ff);
            box-shadow: 0 4px 10px rgba(0, 212, 255, 0.3);
        }
        
        .resume-btn:hover {
            background: linear-gradient(135deg, #33ddff, #33aaff);
            transform: translateY(-2px);
            box-shadow: 0 6px 15px rgba(0, 212, 255, 0.4);
        }
        
        .stop-btn {
            background: linear-gradient(135deg, #ff6b6b, #ff4757);
            box-shadow: 0 4px 10px rgba(255, 107, 107, 0.3);
        }
        
        .stop-btn:hover {
            background: linear-gradient(135deg, #ff8585, #ff6161);
            transform: translateY(-2px);
            box-shadow: 0 6px 15px rgba(255, 107, 107, 0.4);
        }
        
        .streaming-control-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        
        /* CSS cho input bị vô hiệu hóa */
        .chat-input-disabled {
            opacity: 0.6 !important;
            cursor: not-allowed !important;
            background: rgba(255, 255, 255, 0.05) !important;
        }
        
        .chat-input-disabled::placeholder {
            color: rgba(255, 255, 255, 0.4) !important;
        }
        
        .btn-disabled {
            opacity: 0.6 !important;
            cursor: not-allowed !important;
            pointer-events: none !important;
        }
        
        /* Indicator cho trạng thái đã dừng */
        .paused-indicator, .stopped-indicator {
            font-size: 12px;
            margin-left: 8px;
            font-weight: 500;
        }
        
        /* Animation cho controls */
        @keyframes controlsFadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .bot-streaming-controls {
            animation: controlsFadeIn 0.3s ease-out;
        }
        
        /* Responsive cho mobile */
        @media (max-width: 768px) {
            .bot-streaming-controls {
                flex-wrap: wrap;
                justify-content: center;
            }
            
            .streaming-control-btn {
                flex: 1;
                min-width: 120px;
                justify-content: center;
            }
        }
    `;
    document.head.appendChild(style);
}

// =======================================================
// ✅ THÊM HÀM KIỂM TRA KẾT NỐI SERVER
// =======================================================
async function testBotConnection() {
    for (const candidate of API_BASE_CANDIDATES) {
        try {
            const testUrl = `${candidate}/health?_t=${Date.now()}`;
            console.log('Testing AI Connection:', testUrl);

            const response = await fetch(testUrl, {
                method: 'GET',
                mode: 'cors',
                cache: 'no-store'
            });

            if (!response.ok) {
                console.warn('AI health responded with status:', response.status, candidate);
                continue;
            }

            const data = await response.json();
            API_BASE_URL = candidate;
            console.log('AI Server health:', data, 'via', candidate);
            return true;
        } catch (error) {
            console.warn('AI connection failed via', candidate, error);
        }
    }
    return false;
}

function notifyAiUnavailable(message) {
    console.warn('AI availability notice suppressed in toast layer:', message);
}

// =======================================================
// ✅ INITIALIZE ON LOAD
// =======================================================
document.addEventListener('DOMContentLoaded', async function () {
    console.log("Skemi web app loading...");
    loadingStartedAt = Date.now();
    currentLoadingPercent = 0;
    if (progressFill) progressFill.style.width = '0%';
    if (loadingPercent) loadingPercent.textContent = '0%';
    ensureLocalPreferencesDefaults();
    refreshAppSettings();
    loadThemeFromStorage();
    bindThemeToggleForAllUsers();
    repairDomText(document.body);
    startMojibakeObserver();
    applyChatLanguage();
    addCustomStyles();

    // Khởi tạo model selector ngay lập tức
    setTimeout(() => {
        // Model selector removed (single-model mode)
    }, 500);

    // Kiểm tra kết nối server AI
    const isBotConnected = await testBotConnection();
    if (!isBotConnected) {
        console.warn("AI server is unavailable. Chatbot may not respond.");
    }
});

// =======================================================
// ✅ HÀM HIỂN THỊ LỖI MẠNG
// =======================================================
function showNetworkError(title, message) {
    if (loadingError) {
        errorTitle.textContent = repairMojibake(title || (getCurrentLanguage() === 'vi' ? 'Lỗi kết nối' : 'Connection error'));
        errorMessage.textContent = repairMojibake(message || (getCurrentLanguage() === 'vi'
            ? 'Không thể kết nối đến server. Vui lòng kiểm tra mạng và thử lại.'
            : 'Could not connect to the server. Please check your network and try again.'));
        loadingError.style.display = 'block';
        loadingOverlay.style.display = 'flex';
    } else {
        console.error(`${title}: ${message}`);
        showToast(message || (getCurrentLanguage() === 'vi' ? 'Lỗi kết nối' : 'Connection error'), 'error');
    }
}

// =======================================================
// ✅ HÀM LOAD MESSAGES TỪ RTDB (BACKUP)
// =======================================================
async function loadMessagesFromRTDB(friendUid) {
    if (!currentUserUid || !friendUid) return;

    try {
        const chatId = [currentUserUid, friendUid].sort().join("_");
        const rtdbRef = dbRef(rtdb, `chats/${chatId}/messages`);

        onValue(rtdbRef, (snapshot) => {
            if (snapshot.exists()) {
                const messages = snapshot.val();
                Object.entries(messages).forEach(([key, msg]) => {
                    // Kiểm tra xem tin nhắn đã xử lý chưa
                    if (!processedMessageIds.has(key) && !processedMessageIds.has(msg.messageId)) {
                        const formattedMsg = {
                            key: key,
                            firestoreId: msg.firestoreId,
                            messageId: msg.messageId,
                            sender: msg.from || msg.sender,
                            receiver: msg.to || msg.receiver,
                            text: msg.content || msg.text,
                            rawText: msg.content || msg.text,
                            type: msg.type || "text",
                            fileName: msg.fileName || null,
                            timestamp: msg.timestamp || Date.now(),
                            status: msg.status || "sent"
                        };

                        if (formattedMsg.key) processedMessageIds.add(formattedMsg.key);
                        if (formattedMsg.messageId) processedMessageIds.add(formattedMsg.messageId);

                        // Chỉ render nếu đang chat với người này
                        if (selectedFriendUid === friendUid) {
                            renderMessage(formattedMsg);
                        }
                    }
                });
            }
        }, (error) => {
            console.error("❌ Lỗi load messages từ RTDB:", error);
        });

    } catch (error) {
        console.error("❌ Lỗi khi kết nối RTDB:", error);
    }
}

// =======================================================
// ✅ HÀM ĐỒNG BỘ RTDB → FIRESTORE
// =======================================================
async function syncRTDBToFirestore() {
    if (!currentUserUid) return;

    try {
        // Lấy tất cả bạn bè
        const userDoc = await getDoc(doc(db, "users", currentUserUid));
        const userData = userDoc.data();
        const friends = userData?.friends || [];

        for (const friendUid of friends) {
            const chatId = [currentUserUid, friendUid].sort().join("_");
            const rtdbRef = dbRef(rtdb, `chats/${chatId}/messages`);

            const snapshot = await get(rtdbRef);
            if (!snapshot.exists()) continue;

            const messages = snapshot.val();
            const firestoreRef = collection(db, "chats", chatId, "messages");

            // Kiểm tra từng tin nhắn trong RTDB
            for (const [key, msg] of Object.entries(messages)) {
                // Nếu tin nhắn chưa có firestoreId và chưa failed trước đó
                if (!msg.firestoreId && !msg.firestoreFailed) {
                    try {
                        const firestoreMsg = {
                            from: msg.from || msg.sender,
                            to: msg.to || msg.receiver,
                            content: msg.content || msg.text || "",
                            type: msg.type || "text",
                            fileName: msg.fileName || null,
                            timestamp: serverTimestamp(),
                            status: msg.status || "sent",
                            localMsgId: msg.localMsgId || null
                        };

                        const docRef = await addDoc(firestoreRef, firestoreMsg);

                        // Cập nhật RTDB với firestoreId
                        await update(dbRef(rtdb, `chats/${chatId}/messages/${key}`), {
                            firestoreId: docRef.id,
                            syncedAt: Date.now()
                        });

                        console.log(`✅ Đã đồng bộ tin nhắn ${key} sang Firestore`);

                    } catch (error) {
                        console.error(`Lỗi đồng bộ tin nhắn ${key}:`, error);

                        // Đánh dấu là failed để không thử lại liên tục
                        await update(dbRef(rtdb, `chats/${chatId}/messages/${key}`), {
                            firestoreFailed: true,
                            firestoreError: error.message
                        });
                    }
                }
            }
        }

    } catch (error) {
        console.error("Lỗi khi đồng bộ RTDB → Firestore:", error);
    }
}


// =======================================================
// ✅ HÀM KIỂM TRA TRẠNG THÁI SOCKET
// =======================================================
function checkSocketStatus() {
    return {
        connected: socket ? socket.connected : false,
        socketId: socket ? socket.id : null,
        userId: currentUserUid,
        timestamp: Date.now()
    };
}

// =======================================================
// ✅ CẬP NHẬT PHẦN EXPORT
// =======================================================
window.ChatModule = {
    loadMessages: loadMessagesFromFirestore,
    sendMessage: sendTextMessage,
    startTyping: sendTypingStatus,
    stopTyping: () => sendTypingStatus(false),
    markMessagesAsSeen: markAllMessagesAsSeen,
    updateUnreadCount: updateUnreadCount,
    getUnreadCounts: () => unreadCounts,
    getChatbotMessageCount: () => chatbotSession.messages.length,
    copyMessageText: copyMessageText,
    confirmEdit: confirmEdit,
    startCall: startCall,
    endCall: endCall,
    checkSocketStatus: checkSocketStatus,
    testBotStreaming: () => {
        if (selectedFriendUid === CHATBOT_UID) {
            const testMessages = [
                "Tôi đang xử lý yêu cầu của bạn...",
                "Đây là kết quả từ AI chatbot với hiệu ứng streaming realtime!"
            ];
            const randomMessage = testMessages[Math.floor(Math.random() * testMessages.length)];
            createBotMessageStreaming(randomMessage, {
                speed: 30,
                batchSize: 2
            });
        }
    },
        clearChatbotSession: clearChatbotSession
};

// =======================================================
// ✅ HÀM XỬ LÝ COPY TIN NHẮN
// =======================================================
async function copyMessageText(box) {
    const textElement = box.querySelector('.msg-text') || box.querySelector('.msg div:not(.msg-actions)');
    if (!textElement) return;

    const textToCopy = textElement.innerText;
    try {
        await navigator.clipboard.writeText(textToCopy);
        showToast(uiText('Đã sao chép tin nhắn!', 'Message copied!'), "success");
    } catch (err) {
        console.error('Lỗi khi copy:', err);
        showToast(uiText('Không thể sao chép tin nhắn', 'Could not copy the message'), "error");
    }
}

// =======================================================
// ✅ HÀM XỬ LÝ EDIT TIN NHẮN (DÀNH CHO USER)
// =======================================================
function enterEditMode(box) {
    if (isStreamingActive) {
        showToast(uiText('Vui lòng đợi AI phản hồi xong trước khi sửa.', 'Please wait for the AI response to finish before editing.'), "warning");
        return;
    }

    const msgElement = box.querySelector('.msg.me');
    const textContainer = box.querySelector('.msg-text');
    if (!msgElement || !textContainer) return;

    const originalText = textContainer.innerText;
    msgElement.classList.add('edit-mode');

    // Lưu nội dung cũ để cancel
    box.dataset.originalText = originalText;

    msgElement.innerHTML = `
        <textarea class="edit-input">${originalText}</textarea>
        <div class="edit-controls">
            <button class="cancel-edit-btn">${uiText('Hủy', 'Cancel')}</button>
            <button class="confirm-edit-btn">${uiText('Gửi lại', 'Resend')}</button>
        </div>
    `;

    const textarea = msgElement.querySelector('.edit-input');
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    // Event listeners cho các nút trong chế độ edit
    msgElement.querySelector('.cancel-edit-btn').onclick = () => exitEditMode(box, originalText);
    msgElement.querySelector('.confirm-edit-btn').onclick = () => confirmEdit(box);
}

function exitEditMode(box, text) {
    const msgElement = box.querySelector('.msg.me');
    if (!msgElement) return;
    
    msgElement.classList.remove('edit-mode');

    msgElement.innerHTML = `
        <div class="msg-actions">
            <button class="action-btn edit-btn" title="${uiText('Chỉnh sửa', 'Edit')}"><i class="fas fa-edit"></i></button>
            <button class="action-btn copy-btn" title="${uiText('Sao chép', 'Copy')}"><i class="fas fa-copy"></i></button>
        </div>
        <div class="msg-text">${renderPlainTextContent(text)}</div>
    `;
}

async function confirmEdit(box) {
    const newText = box.querySelector('.edit-input').value.trim();
    if (!newText) return;

    const originalText = box.dataset.originalText;
    if (newText === originalText) {
        exitEditMode(box, originalText);
        return;
    }

    console.log("✏️ Confirming edit and re-generating AI response...");

    // 1. Tìm tin nhắn AI ngay sau tin nhắn này (nếu có)
    let nextElement = box.nextElementSibling;
    while (nextElement && !nextElement.classList.contains('bot-box') && !nextElement.dataset.botMessage) {
        nextElement = nextElement.nextElementSibling;
    }

    // 2. Xóa tin nhắn AI cũ khỏi giao diện
    if (nextElement && (nextElement.classList.contains('bot-box') || nextElement.dataset.botMessage)) {
        nextElement.remove();
    }

    // 3. Cập nhật tin nhắn user trong session và UI
    exitEditMode(box, newText);
    
    // Tìm message ID trong session
    const msgId = box.dataset.messageId;
    if (msgId) {
        const msgIndex = chatbotSession.messages.findIndex(m => m.id === msgId);
        if (msgIndex !== -1) {
            // Xóa tất cả các tin nhắn từ vị trí này trở đi trong history để regenerate
            chatbotSession.messages = chatbotSession.messages.slice(0, msgIndex);
        }
    }

    // 4. Gửi lại yêu cầu tới chatbot
    handleChatbotMessage(newText);
}

// =======================================================
// ✅ EVENT DELEGATION CHO MESSAGE ACTIONS
// =======================================================
document.addEventListener('DOMContentLoaded', () => {
    const messagesDiv = document.getElementById("messages");
    if (messagesDiv) {
        messagesDiv.addEventListener('click', (e) => {
            const copyBtn = e.target.closest('.copy-btn');
            const editBtn = e.target.closest('.edit-btn');
            const box = e.target.closest('.msg-box');

            if (copyBtn && box) {
                copyMessageText(box);
            } else if (editBtn && box) {
                enterEditMode(box);
            }
        });
    }
});

// =======================================================
// ✅ INTERACTIVE RESEARCH PLAN FUNCTIONS
// =======================================================
let currentResearchQuestion = "";

function showResearchPlan(plan, question) {
    if (!RESEARCH_PLAN_UI_ENABLED) return;
    currentResearchQuestion = question;
    const sidebar = document.getElementById('researchSidebar');
    const body = document.getElementById('researchBody');
    if (!sidebar || !body) return;

    body.innerHTML = '';
    plan.forEach((step, index) => {
        const stepEl = document.createElement('div');
        stepEl.className = 'research-step';
        stepEl.textContent = step;
        body.appendChild(stepEl);
    });

    sidebar.classList.add('active');
    
    // Auto-scroll to sidebar if on mobile
    if (window.innerWidth <= 480) {
        sidebar.scrollIntoView({ behavior: 'smooth' });
    }
}

function initResearchSidebar() {
    const closeBtn = document.getElementById('closeResearchBtn');
    const editBtn = document.getElementById('editResearchBtn');
    const startBtn = document.getElementById('startResearchBtn');
    const sidebar = document.getElementById('researchSidebar');
    if (!RESEARCH_PLAN_UI_ENABLED) {
        if (sidebar) {
            sidebar.classList.remove('active');
            sidebar.hidden = true;
            sidebar.setAttribute('aria-hidden', 'true');
        }
        return;
    }

    if (closeBtn) closeBtn.addEventListener('click', () => sidebar.classList.remove('active'));
    
    if (editBtn) {
        editBtn.addEventListener('click', () => {
            const steps = document.querySelectorAll('.research-step');
            const isEditing = editBtn.classList.toggle('editing');
            
            steps.forEach(step => {
                step.contentEditable = isEditing;
                if (isEditing) {
                    step.style.boxShadow = '0 0 10px rgba(0, 212, 255, 0.3)';
                } else {
                    step.style.boxShadow = 'none';
                }
            });
            
            editBtn.innerHTML = isEditing ? `<i class="fas fa-save"></i> ${uiText('Lưu', 'Save')}` : `<i class="fas fa-edit"></i> ${uiText('Chỉnh sửa', 'Edit')}`;
        });
    }

    if (startBtn) {
        startBtn.addEventListener('click', () => {
            const steps = Array.from(document.querySelectorAll('.research-step')).map(s => s.textContent.trim());
            sidebar.classList.remove('active');
            handleChatbotMessage(currentResearchQuestion, { confirmedPlan: steps });
        });
    }

    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            if (currentStreamController) {
                currentStreamController.abort();
                isStreamingActive = false;
                if (stopBtn) stopBtn.style.display = 'none';
                if (sendBtn) sendBtn.disabled = false;
                if (msgInput) {
                    msgInput.disabled = false;
                    msgInput.placeholder = chatText('placeholder');
                }
                updateBotStatus(chatText('stoppedResponse'));
                ensureBotTypingIndicatorIsRemoved();
            }
        });
    }
}

// Initialize sidebar events
document.addEventListener('DOMContentLoaded', initResearchSidebar);
document.addEventListener('DOMContentLoaded', initMessageScrollController);

// =======================================================
// ✅ TEXTAREA AUTO-RESIZE & SCROLL BUTTONS
// =======================================================
function initTextareaAutoResize() {
    const textarea = document.getElementById('msg');
    const scrollBtns = document.querySelector('.textarea-scroll-btns');
    const scrollUpBtn = document.getElementById('scrollUpBtn');
    const scrollDownBtn = document.getElementById('scrollDownBtn');
    if (!textarea) return;

    function autoResize() {
        // Reset height to auto to measure scrollHeight correctly
        textarea.style.height = 'auto';
        const newHeight = Math.min(textarea.scrollHeight, 160);
        textarea.style.height = newHeight + 'px';

        // Show/hide scroll buttons when content overflows
        const isOverflowing = textarea.scrollHeight > 160;
        if (scrollBtns) scrollBtns.classList.toggle('visible', isOverflowing);
    }

    textarea.addEventListener('input', autoResize);
    textarea.addEventListener('keydown', (e) => {
        // Reset on Ctrl+Enter submission proxy
        if (e.key === 'Enter' && !e.shiftKey) {
            setTimeout(() => {
                textarea.style.height = 'auto';
                if (scrollBtns) scrollBtns.classList.remove('visible');
            }, 50);
        }
    });

    if (scrollUpBtn) {
        scrollUpBtn.addEventListener('click', () => {
            textarea.scrollTop -= 60;
        });
    }

    if (scrollDownBtn) {
        scrollDownBtn.addEventListener('click', () => {
            textarea.scrollTop += 60;
        });
    }

    autoResize();
}

document.addEventListener('DOMContentLoaded', initTextareaAutoResize);

console.log("✅ Chat.js updated with Interactive Research Plan handling");




window.addEventListener('storage', (event) => { if (event.key === 'skemi-theme' || event.key === 'chat-theme') { applyThemePreference(getCurrentTheme()); } if (event.key === 'skemi_language') { applyChatLanguage(); } });
window.addEventListener('themeChanged', () => applyThemePreference(getCurrentTheme()));
window.addEventListener('languageChanged', () => applyChatLanguage());




