

const WORKFLOW_STORAGE_KEY = () => 'skemi_active_workflow_id_v1';
const SESSION_STORAGE_KEY = () => 'skemi_active_computer_session_v1';
const COMPUTER_MODE_KEY = () => 'skemi_computer_mode';
const COMPUTER_PHANTOM_INDEX_KEY = () => 'skemi_computer_phantom_index';
const FORCE_FINAL_ONLY_VIEW = false;

const goalInput = document.getElementById("computerGoalInput");
const modeSelect = document.getElementById("computerModeSelect");
const preferredSurfaceSelect = document.getElementById("computerTargetSurface");
const surfaceTypeSelect = document.getElementById("computerSurfaceType");
const createBtn = document.getElementById("createComputerSessionBtn");
const refreshBtn = document.getElementById("refreshComputerSessionBtn");
const resumeBtn = document.getElementById("resumeComputerSessionBtn");
const interruptBtn = document.getElementById("interruptComputerSessionBtn");
const takeoverBtn = document.getElementById("takeoverComputerSessionBtn");
const approveBtn = document.getElementById("approveComputerSessionBtn");
const denyBtn = document.getElementById("denyComputerSessionBtn");
const openSurfaceBtn = document.getElementById("openPlannedSurfaceBtn");
const privacyBtn = document.getElementById("evaluatePrivacyBtn");
const loadingEl = document.getElementById("computerLoading");

const workflowContextEl = document.getElementById("computerWorkflowContext");
const summaryEl = document.getElementById("computerSummary");
const targetEl = document.getElementById("computerTarget");
const sessionMetaEl = document.getElementById("computerSessionMeta");
const workspaceMetaEl = document.getElementById("computerWorkspaceMeta");
const actionListEl = document.getElementById("computerActionList");
const safetyListEl = document.getElementById("computerSafetyList");
const artifactListEl = document.getElementById("computerArtifactList");
const handoffEl = document.getElementById("computerHandoff");
const eventListEl = document.getElementById("computerEventList");
const privacyStateEl = document.getElementById("computerPrivacyState");

const runtimeSummaryEl = document.getElementById("computerRuntimeSummary");
const observationListEl = document.getElementById("computerObservationList");
const interactionListEl = document.getElementById("computerInteractionList");
const antiBotListEl = document.getElementById("computerAntiBotList");
const humanControlListEl = document.getElementById("computerHumanControlList");
const escapeListEl = document.getElementById("computerEscapeList");
const blockerListEl = document.getElementById("computerBlockerList");
const milestoneListEl = document.getElementById("computerMilestoneList");
const diagnosticsDetailsEl = document.getElementById("computerDiagnosticsDetails");
const runtimeDetailsEl = document.getElementById("computerRuntimeDetails");
const metaPanelEl = document.getElementById("computerMetaPanel");
const artifactPanelEl = document.getElementById("computerArtifactPanel");

const virtualBrowserTab = document.getElementById("virtualBrowserTab");
const localComputerTab = document.getElementById("localComputerTab");
const surfaceResetBtn = document.getElementById("surfaceResetBtn");
const surfaceManualBtn = document.getElementById("surfaceManualBtn");
const surfaceFullscreenBtn = document.getElementById("surfaceFullscreenBtn");
const surfaceRevealBtn = document.getElementById("desktopRevealBtn");
const surfaceStage = document.getElementById("surfaceStage");
const surfaceImage = document.getElementById("surfaceImage");
const surfaceStatus = document.getElementById("surfaceStatus");
const surfaceOverlayStatus = document.getElementById("surfaceOverlayStatus");
const surfaceOverlay = document.getElementById("surfaceOverlay");
const surfaceTimeline = document.getElementById("surfaceTimeline");
const surfaceTimelineRange = document.getElementById("surfaceTimelineRange");
const surfaceTimelineLabel = document.getElementById("surfaceTimelineLabel");
const surfaceLiveBtn = document.getElementById("surfaceLiveBtn");
const surfaceBrowserTitle = document.getElementById("surfaceBrowserTitle");
const surfaceBrowserUrl = document.getElementById("surfaceBrowserUrl");
const surfaceTitleMeta = document.getElementById("surfaceTitleMeta");
const surfaceUrlMeta = document.getElementById("surfaceUrlMeta");
const surfaceQueueMeta = document.getElementById("surfaceQueueMeta");
const surfaceTransportMeta = document.getElementById("surfaceTransportMeta");
const surfaceWarmMeta = document.getElementById("surfaceWarmMeta");
const surfaceCommandInput = document.getElementById("surfaceCommandInput");
const surfaceRunBtn = document.getElementById("surfaceRunBtn");
const surfaceResponseText = document.getElementById("surfaceResponseText");
const surfaceResponseTone = document.getElementById("surfaceResponseTone");
const surfaceActivityLog = document.getElementById("surfaceActivityLog");
const surfaceChatFeed = document.getElementById("surfaceChatFeed");
const surfaceThinkingStrip = document.getElementById("surfaceThinkingStrip");
const surfaceThinkingText = document.getElementById("surfaceThinkingText");
const surfaceStreamToggleBtn = document.getElementById("surfaceStreamToggleBtn");
const surfaceStreamToggleLabel = document.getElementById("surfaceStreamToggleLabel");
const surfaceConsoleLabel = document.getElementById("surfaceConsoleLabel");
const surfaceQueueLabel = document.getElementById("surfaceQueueLabel");
const surfaceSessionLabel = document.getElementById("surfaceSessionLabel");
const surfaceAddressLabel = document.getElementById("surfaceAddressLabel");
const surfaceActivityLabel = document.getElementById("surfaceActivityLabel");
const surfaceTimelineGhostTab = document.getElementById("surfaceTimelineGhostTab");
const surfaceWorkspace = document.getElementById("surfaceWorkspace");
const surfaceBrowserPanel = document.getElementById("surfaceBrowserPanel");
const localComputerPanel = document.getElementById("localComputerPanel");
const localComputerStatusPill = document.getElementById("localComputerStatusPill");
const localComputerVersionPill = document.getElementById("localComputerVersionPill");
const localComputerMachineLabel = document.getElementById("localComputerMachineLabel");
const localComputerLastSeen = document.getElementById("localComputerLastSeen");
const localComputerNotes = document.getElementById("localComputerNotes");
const localComputerRefreshBtn = document.getElementById("localComputerRefreshBtn");
const localComputerMockConnectBtn = document.getElementById("localComputerMockConnectBtn");
const localComputerDisconnectBtn = document.getElementById("localComputerDisconnectBtn");
const localDualModeBtn = document.getElementById("localDualModeBtn");
const localPhantomModeBtn = document.getElementById("localPhantomModeBtn");
const localPhantomPreview = document.getElementById("localPhantomPreview");
const localPhantomImage = document.getElementById("localPhantomImage");
const localPhantomPlaceholder = document.getElementById("localPhantomPlaceholder");
const localComputerCommandInput = document.getElementById("localComputerCommandInput");
const localComputerRunBtn = document.getElementById("localComputerRunBtn");

const privacyProcessInput = document.getElementById("privacyProcessInput");
const privacyTitleInput = document.getElementById("privacyWindowTitleInput");
const privacyRolesInput = document.getElementById("privacyRoleInput");
const privacySignalsInput = document.getElementById("privacySignalInput");
const privacyBlacklistInput = document.getElementById("privacyBlacklistInput");
const privacyAllowOverrideInput = document.getElementById("privacyAllowOverride");

let currentSession = null;
let latestTargetHref = "";
let localComputerPollTimer = null;
let localComputerModeTransitioning = false; 

const SURFACE_SESSION_KEY = "skemi_surface_session_id_v1";
const SURFACE_LAST_COMMAND_KEY = "skemi_surface_last_command_v1";
let surfaceSessionId = "";
let surfaceLastObservation = null;
let surfaceHandoffActive = false;
let surfaceManualEnabled = false;
let surfacePlaybackMode = "live";
let surfaceHistory = [];
let surfaceHistoryTimer = null;
let surfaceStatusTimer = null;
let lastFrameUrl = "";
let surfaceOverlayTimer = null;
let surfaceHistoryEnabled = false;
let surfacePulseEl = null;
let lastFrameTs = 0;
let surfaceKeyHandlerAttached = false;
let surfaceStreamVisible = true;
let surfaceActionChain = Promise.resolve();
let surfaceTextBuffer = "";
let surfaceTextBufferTimer = null;
const SURFACE_TEXT_BUFFER_MAX = 12;
const SURFACE_TEXT_BUFFER_IDLE_MS = 140;
let surfaceLastStatusText = "";
let surfaceLastRawStatus = "";
let surfaceBootPromise = null;
let localPhantomVideo = null;
let localPhantomPeer = null;
let localPhantomPeerSessionId = "";
let localPhantomWebRtcPending = null;

if (surfaceImage) {
    surfaceImage.decoding = "async";
    surfaceImage.loading = "eager";
    surfaceImage.fetchPriority = "high";
}

function ensureLocalPhantomVideo() {
    if (localPhantomVideo) return localPhantomVideo;
    const phantomScreen = localPhantomPreview?.querySelector?.(".local-phantom-screen") || localPhantomPreview;
    if (!phantomScreen) return null;
    const video = document.createElement("video");
    video.id = "localPhantomVideo";
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.disablePictureInPicture = true;
    video.hidden = true;
    video.style.width = "100%";
    video.style.height = "100%";
    video.style.objectFit = "contain";
    video.style.background = "#020617";
    video.style.display = "block";
    if (localPhantomImage?.parentNode === phantomScreen) {
        phantomScreen.insertBefore(video, localPhantomImage);
    } else {
        phantomScreen.appendChild(video);
    }
    localPhantomVideo = video;
    return localPhantomVideo;
}

function stopLocalPhantomWebRtc(resetVideo = false) {
    localPhantomWebRtcPending = null;
    localPhantomPeerSessionId = "";
    if (localPhantomPeer) {
        try {
            localPhantomPeer.ontrack = null;
            localPhantomPeer.onconnectionstatechange = null;
            localPhantomPeer.close();
        } catch (error) {}
        localPhantomPeer = null;
    }
    if (localPhantomVideo && resetVideo) {
        try {
            localPhantomVideo.pause();
            localPhantomVideo.srcObject = null;
        } catch (error) {}
        localPhantomVideo.hidden = true;
    }
}

async function startLocalPhantomWebRtc(sessionId) {
    const safeSessionId = String(sessionId || "").trim();
    if (!safeSessionId || typeof RTCPeerConnection === "undefined") return false;
    const video = ensureLocalPhantomVideo();
    if (!video) return false;
    if (
        localPhantomPeer &&
        localPhantomPeerSessionId === safeSessionId &&
        !["failed", "closed", "disconnected"].includes(String(localPhantomPeer.connectionState || "").toLowerCase())
    ) {
        return true;
    }
    if (localPhantomWebRtcPending && localPhantomPeerSessionId === safeSessionId) {
        return localPhantomWebRtcPending;
    }

    stopLocalPhantomWebRtc(true);
    localPhantomPeerSessionId = safeSessionId;
    localPhantomWebRtcPending = (async () => {
        try {
            const pc = new RTCPeerConnection({ iceServers: [] });
            localPhantomPeer = pc;
            pc.addTransceiver("video", { direction: "recvonly" });
            pc.ontrack = (event) => {
                if (localPhantomPeer !== pc || !localPhantomVideo) return;
                const stream = event.streams && event.streams[0] ? event.streams[0] : null;
                if (!stream) return;
                localPhantomVideo.srcObject = stream;
                localPhantomVideo.hidden = false;
                localPhantomVideo.play?.().catch?.(() => {});
                if (localPhantomImage) localPhantomImage.hidden = true;
                if (localPhantomPlaceholder) localPhantomPlaceholder.hidden = true;
            };
            pc.onconnectionstatechange = () => {
                const state = String(pc.connectionState || "").toLowerCase();
                if (["failed", "closed", "disconnected"].includes(state) && localPhantomPeer === pc) {
                    stopLocalPhantomWebRtc(true);
                }
            };

            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            
            // 5-second timeout for WebRTC offer/answer negotiation
            const offerPromise = Promise.race([
                fetch("/api/local-computer/webrtc/offer", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        session_id: safeSessionId,
                        sdp: String(offer.sdp || ""),
                        type: String(offer.type || "offer"),
                    }),
                }),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error("WebRTC offer timeout")), 5000)
                )
            ]);
            
            const response = await offerPromise;
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload?.sdp) {
                throw new Error(payload?.detail || payload?.error || "Local WebRTC offer failed.");
            }
            await pc.setRemoteDescription({
                type: String(payload.type || "answer"),
                sdp: String(payload.sdp || ""),
            });
            return true;
        } catch (error) {
            stopLocalPhantomWebRtc(true);
            return false;
        } finally {
            localPhantomWebRtcPending = null;
        }
    })();
    return localPhantomWebRtcPending;
}

function getUiLanguage() {
    const lang = String(document.documentElement.lang || localStorage.getItem("skemi_language") || "vi").trim().toLowerCase();
    return lang.startsWith("en") ? "en" : "vi";
}

function t(vi, en) {
    return getUiLanguage() === "en" ? en : vi;
}

function normalizeSurfaceStatusText(text) {
    const value = String(text || "").trim();
    if (!value) return t("San sang.", "Ready.");
    const mappings = [
        [/Google Chrome ready/i, t("Google Chrome đã sẵn sàng.", "Google Chrome is ready.")],
        [/Chromium ready/i, t("Chromium đã sẵn sàng.", "Chromium is ready.")],
        [/Launching Virtual Browser/i, t("Đang mở Virtual Browser...", "Launching Virtual Browser...")],
        [/Navigation complete/i, t("Đã mở xong trang.", "Navigation complete.")],
        [/Executing click/i, t("Đang click...", "Executing click...")],
        [/Executing type/i, t("Đang nhập...", "Đang nhập...")],
        [/Manual control ready/i, t("Điều khiển tay đã sẵn sàng.", "Manual control is ready.")],
        [/Session reset/i, t("Đã làm mới phiên.", "Session reset.")],
        [/Reconnecting live view/i, t("Đang nối lại live view...", "Reconnecting live view...")],
        [/Connecting live view/i, t("Đang kết nối live view...", "Connecting live view...")],
        [/Connecting virtual browser/i, t("Đang kết nối browser ảo...", "Connecting virtual browser...")],
    ];
    for (const [pattern, replacement] of mappings) {
        if (pattern.test(value)) return replacement;
    }
    return value;
}

function setSurfaceStatus(text) {
    surfaceLastRawStatus = String(text || "");
    const normalized = normalizeSurfaceStatusText(surfaceLastRawStatus);
    surfaceLastStatusText = normalized;
    if (surfaceStatus) surfaceStatus.textContent = normalized;
    if (surfaceOverlayStatus) surfaceOverlayStatus.textContent = normalized;
    if (surfaceResponseTone) surfaceResponseTone.textContent = normalized;
}

function getActiveAssistantBody() {
    return surfaceChatFeed?.querySelector(".surface-chat-message-assistant.surface-chat-message-active .surface-chat-message-body") || surfaceResponseText;
}

function scrollSurfaceChatToBottom() {
    if (!surfaceChatFeed) return;
    surfaceChatFeed.scrollTop = surfaceChatFeed.scrollHeight;
}

function createSurfaceChatMessage(role, text, options = {}) {
    if (!surfaceChatFeed) return null;
    const message = document.createElement("div");
    message.className = `surface-chat-message surface-chat-message-${role}${options.active ? " surface-chat-message-active" : ""}`;
    message.dataset.role = role;

    const meta = document.createElement("div");
    meta.className = "surface-chat-message-meta";
    meta.innerHTML = role === "user"
        ? `<span>${t("Bạn", "You")}</span>`
        : `<span>Skemi</span><span class="surface-chat-message-model">${options.model || "gpt-oss:120b-cloud"}</span>`;

    const body = document.createElement("div");
    body.className = "surface-chat-message-body";
    body.textContent = text;

    message.appendChild(meta);
    message.appendChild(body);
    surfaceChatFeed.appendChild(message);
    scrollSurfaceChatToBottom();
    return body;
}

function beginSurfaceAssistantTurn(initialText) {
    if (!surfaceChatFeed) return surfaceResponseText;
    surfaceChatFeed
        .querySelectorAll(".surface-chat-message-assistant.surface-chat-message-active")
        .forEach((node) => node.classList.remove("surface-chat-message-active"));
    return createSurfaceChatMessage("assistant", initialText, { active: true }) || surfaceResponseText;
}

function setSurfaceResponse(message) {
    const body = getActiveAssistantBody();
    if (body) body.textContent = message;
    scrollSurfaceChatToBottom();
}

function setSurfaceThinking(visible, text = "") {
    if (surfaceThinkingStrip) {
        surfaceThinkingStrip.hidden = !visible;
        surfaceThinkingStrip.classList.toggle("is-active", Boolean(visible));
        surfaceThinkingStrip.setAttribute("aria-busy", visible ? "true" : "false");
    }
    if (visible && surfaceThinkingText) {
        surfaceThinkingText.textContent = text || t("Dang phan tich yeu cau", "Analyzing your request");
    } else if (!visible && surfaceThinkingText) {
        surfaceThinkingText.textContent = "";
    }
}

function pushSurfaceActivity(message, detail = "") {
    if (!surfaceActivityLog) return;
    const empty = surfaceActivityLog.querySelector(".surface-log-empty");
    if (empty) empty.remove();
    const item = document.createElement("div");
    item.className = "surface-log-item";
    const title = document.createElement("strong");
    title.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    item.appendChild(title);
    item.append(document.createTextNode(detail ? `${message} ${detail}`.trim() : message));
    surfaceActivityLog.prepend(item);
    while (surfaceActivityLog.children.length > 8) {
        surfaceActivityLog.removeChild(surfaceActivityLog.lastChild);
    }
}

function updateSurfaceMeta(meta = {}) {
    const title = String(meta.current_title || meta.title || "").trim() || "Virtual Browser";
    const url = String(meta.current_url || meta.url || "").trim() || "about:blank";
    const queued = Number(meta.queued_actions || 0);
    const transport = String(meta.transport || "mjpeg").toUpperCase();
    const warm = meta.warm_pool
        ? t("Warm pool", "Warm pool")
        : (meta.prewarmed ? t("Đã làm nóng", "Prewarmed") : t("Phiên trực tiếp", "Live session"));

    if (surfaceBrowserTitle) surfaceBrowserTitle.textContent = title;
    if (surfaceBrowserUrl) surfaceBrowserUrl.textContent = url;
    if (surfaceTitleMeta) surfaceTitleMeta.textContent = title;
    if (surfaceUrlMeta) surfaceUrlMeta.textContent = url;
    if (surfaceQueueMeta) surfaceQueueMeta.textContent = queued > 0 ? `${queued}` : t("Sẵn sàng", "Ready");
    if (surfaceTransportMeta) surfaceTransportMeta.textContent = `${transport} ${t("live", "live")}`;
    if (surfaceWarmMeta) surfaceWarmMeta.textContent = warm;
}

function setButtonText(button, vi, en) {
    if (button) button.textContent = t(vi, en);
}

function applyComputerCopy() {
    document.title = "Skemi - Computer";

    const navLabels = [
        ["Home.html", t("Studio", "Studio")],
        ["Search.html", t("Tra cứu", "Search")],
        ["Quiz.html", "Quiz"],
        ["/Chat.html", "Chat"],
    ];
    for (const [href, label] of navLabels) {
        const node = document.querySelector(`.navbar-shortcuts a[href='${href}'] span:last-child`);
        if (node) node.textContent = label;
    }

    const sidebarLabels = [
        ["mindmap-link", t("Studio", "Studio")],
        ["search-link", t("Tra cứu", "Search")],
        ["quiz-link", "Quiz"],
        ["chat-link", "Chat"],
        ["prompt-agent-link", t("Prompt Agent", "Prompt Agent")],
        ["computer-link", t("Skemi Control", "Skemi Control")],
        ["settings-link", t("Cài đặt", "Settings")],
    ];
    for (const [id, label] of sidebarLabels) {
        const node = document.querySelector(`#${id} span:last-child`);
        if (node) node.textContent = label;
    }

    const toggleBtn = document.getElementById("toggleSidebar");
    if (toggleBtn) toggleBtn.title = t("Thu gọn menu", "Collapse menu");

    if (surfaceConsoleLabel) surfaceConsoleLabel.textContent = t("Skemi Control", "Skemi Control");
    if (virtualBrowserTab) virtualBrowserTab.innerHTML = `<i class="fas fa-globe"></i> ${t("Virtual Browser", "Virtual Browser")}`;
    if (localComputerTab) localComputerTab.innerHTML = `<i class="fas fa-desktop"></i> ${t("Local Computer", "Local Computer")}`;
    if (surfaceQueueLabel) surfaceQueueLabel.textContent = t("Queue", "Queue");
    if (surfaceSessionLabel) surfaceSessionLabel.textContent = t("Phiên", "Mode");
    if (surfaceAddressLabel) surfaceAddressLabel.textContent = "URL";
    if (surfaceActivityLabel) surfaceActivityLabel.textContent = t("Hoạt động", "Activity");
    if (surfaceTimelineGhostTab) surfaceTimelineGhostTab.textContent = "Timeline";
    if (surfaceCommandInput) {
        surfaceCommandInput.placeholder = t(
            "Ví dụ: mở google.com hoặc tìm giá vàng",
            "Example: open google.com or search gold prices today"
        );
    }
    setButtonText(surfaceRunBtn, "Gửi", "Send");
    setButtonText(surfaceResetBtn, "Reset", "Reset");
    setButtonText(surfaceFullscreenBtn, "Toàn màn hình", "Fullscreen");
    if (surfaceManualBtn) {
        surfaceManualBtn.textContent = surfaceManualEnabled
            ? t("Manual: Bật", "Manual: On")
            : t("Điều khiển tay", "Manual control");
    }
    if (surfaceLiveBtn) surfaceLiveBtn.textContent = "Live";
    if (surfaceTimelineLabel && surfacePlaybackMode === "live") {
        surfaceTimelineLabel.textContent = "Live";
    }
    if (!surfaceLastRawStatus) {
        setSurfaceStatus("Ready.");
    } else {
        setSurfaceStatus(surfaceLastRawStatus);
    }
    if (surfaceResponseText) {
        const current = String(surfaceResponseText.textContent || "").trim();
        if (!current || current.includes("Nhập yêu cầu") || current.includes("Enter a request")) {
            setSurfaceResponse(t(
                "Nhập yêu cầu để mình mở web, thao tác và báo lại song song như một operator trực tiếp.",
                "Enter a request and I'll open the site, operate it, and narrate progress in real time."
            ));
        }
    }
    if (surfaceThinkingText && surfaceThinkingStrip?.hidden === false) {
        surfaceThinkingText.textContent = t("Đang phân tích yêu cầu", "Analyzing your request");
    }
    setSurfaceStreamVisible(surfaceStreamVisible);
    const emptyLog = surfaceActivityLog?.querySelector(".surface-log-empty");
    if (emptyLog) {
        emptyLog.textContent = t("Chưa có hoạt động.", "No activity yet.");
    }
    if (localComputerRefreshBtn) localComputerRefreshBtn.textContent = t("Làm mới", "Refresh");
    if (localComputerMockConnectBtn) localComputerMockConnectBtn.textContent = t("Kết nối thử", "Test connect");
    if (localComputerDisconnectBtn) localComputerDisconnectBtn.textContent = t("Ngắt", "Disconnect");
    if (localComputerRunBtn) localComputerRunBtn.textContent = t("Chạy", "Run");
}

function formatLocalSeen(value) {
    const stamp = Number(value || 0);
    if (!stamp) return t("Mở companion để kích hoạt Local Computer.", "Open the companion to activate Local Computer.");
    return `${t("Lần cuối hoạt động", "Last seen")} ${new Date(stamp * 1000).toLocaleTimeString()}`;
}

function sanitizeLocalComputerText(value = "") {
    return String(value || "")
        .replace(/\\+\.\\DISPLAY\d+/gi, "")
        .replace(/\\\\\.\\DISPLAY\d+/gi, "")
        .replace(/\\\.\\DISPLAY\d+/gi, "")
        .replace(/\bPhantom\s+Display\b/gi, "Phantom Desktop")
        .replace(/\bDual-Control\b/gi, "Live Control")
        .replace(/\s{2,}/g, " ")
        .trim();
}

function renderLocalComputerStatus(payload = {}) {
    const connected = Boolean(payload.connected);
    const mode = String(payload.mode || "live").toLowerCase();
    const status = String(payload.status || (connected ? "connected" : "idle"));
    const streamUrl = String(payload.stream_url || "").trim();
    const sessionId = String(payload.session_id || "").trim();
    const wantsLocalVideo = mode === "phantom" && connected && !!sessionId && typeof RTCPeerConnection !== "undefined";
    
    if (localComputerStatusPill) {
        localComputerStatusPill.textContent = connected
            ? t(`Local ${status}`, `Local ${status}`)
            : t("Companion dang cho", "Companion idle");
    }
    if (localComputerVersionPill) localComputerVersionPill.textContent = mode === "phantom" ? "Skemi Phantom" : "Live Control";
    if (localComputerMachineLabel) localComputerMachineLabel.textContent = sanitizeLocalComputerText(payload.machine_label) || t("Chua co local companion", "No local companion");
    if (localComputerLastSeen) localComputerLastSeen.textContent = formatLocalSeen(payload.last_seen_at);
    if (localDualModeBtn) localDualModeBtn.classList.toggle("surface-btn-accent", mode !== "phantom");
    if (localPhantomModeBtn) localPhantomModeBtn.classList.toggle("surface-btn-accent", mode === "phantom");
    if (localPhantomPreview) localPhantomPreview.hidden = mode !== "phantom" && !streamUrl && !wantsLocalVideo;
    
    const phantomScreen = localPhantomPreview?.querySelector?.(".local-phantom-screen");
    phantomScreen?.classList.toggle("has-stream", Boolean(streamUrl || (localPhantomVideo && !localPhantomVideo.hidden)));
    
    if (wantsLocalVideo && ["starting", "running", "awaiting_confirmation", "done", "stopped", "error"].includes(status)) {
        void startLocalPhantomWebRtc(sessionId);
    } else if (!wantsLocalVideo) {
        stopLocalPhantomWebRtc(true);
    }
    
    if (localPhantomImage) {
        const hasVideoTrack = Boolean(
            localPhantomVideo &&
            !localPhantomVideo.hidden &&
            localPhantomVideo.srcObject &&
            Number(localPhantomVideo.videoWidth || 0) > 0 &&
            Number(localPhantomVideo.videoHeight || 0) > 0
        );
        if (streamUrl && !hasVideoTrack) {
            const nextSrc = `${streamUrl}${streamUrl.includes("?") ? "&" : "?"}ts=${Date.now()}`;
            if (!localPhantomImage.src || !localPhantomImage.src.includes(streamUrl)) {
                localPhantomImage.src = nextSrc;
            }
            localPhantomImage.hidden = false;
            if (localPhantomPlaceholder) localPhantomPlaceholder.hidden = true;
        } else {
            localPhantomImage.removeAttribute("src");
            localPhantomImage.hidden = true;
            if (localPhantomPlaceholder) localPhantomPlaceholder.hidden = hasVideoTrack;
        }
    }

    if (localComputerDisconnectBtn) {
        localComputerDisconnectBtn.textContent = (status === "running" || status === "awaiting_confirmation") ? "Stop" : "Disconnect";
    }
    const cleanNotes = Array.isArray(payload.notes) ? payload.notes.map(sanitizeLocalComputerText).filter(Boolean) : payload.notes;
    renderList(localComputerNotes, cleanNotes, t("Local companion chua ket noi.", "Local companion has not connected yet."));

    // Update Nexus Command Bar Status
    const scStatusDisplay = document.getElementById("scStatusDisplay");
    const scStatusText = document.getElementById("scStatusText");
    const actionDesc = sanitizeLocalComputerText(payload.last_ai_action_desc || payload.status_text || "") || (connected ? (status === "running" ? t("Đang xử lý nhiệm vụ...", "Working on task...") : t("Sẵn sàng.", "Ready.")) : t("Chưa kết nối.", "Not connected."));
    if (scStatusDisplay) {
        scStatusDisplay.classList.toggle("working", status === "running" || status === "awaiting_confirmation");
        scStatusDisplay.classList.toggle("thinking", status === "thinking" || status === "analyzing");
    }

    // Sync to Chat transient status
    if (window.chatWidget && (status === "running" || status === "thinking" || status === "analyzing")) {
        window.chatWidget.setTransientStatus(actionDesc);
    } else if (window.chatWidget && status === "done") {
        window.chatWidget.setTransientStatus(null);
    }

    const uninstallBtn = document.getElementById("btnUninstallVirtualDriver");
    if (uninstallBtn) {
        const driverActive = payload.workspace_kind === 'virtual_display' && payload.driver_status === 'active';
        uninstallBtn.classList.toggle("hidden", !driverActive);
    }

    if ((status === "running" || status === "awaiting_confirmation") && !localComputerPollTimer) {
        localComputerPollTimer = setInterval(() => void refreshLocalComputerStatus(), 1000); // 1.0s for high-activity tasks
    } else if (status !== "running" && status !== "awaiting_confirmation" && localComputerPollTimer) {
        clearInterval(localComputerPollTimer);
        localComputerPollTimer = null;
    }
}

async function refreshLocalComputerStatus() {
    if (localComputerModeTransitioning) return; // Skip polling while we are actively changing modes
    try {
        const response = await fetch("/api/local-computer/status", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Local Computer is unavailable.");
        }
        renderLocalComputerStatus(payload);
    } catch (error) {
        renderLocalComputerStatus({
            connected: false,
            notes: [error.message || "Local Computer is unavailable."],
        });
    }
}

async function postLocalComputerAction(path, body = {}) {
    if (path === "mode" || path === "phantom/start" || path === "phantom/lock") {
        localComputerModeTransitioning = true;
        window.__skemi_poll_paused = true; // Pause polling in Computer.html
        if (window.desktopAgent) {
            window.desktopAgent._modeChangeInProgress = true;
            window.desktopAgent._lastModeChangeStartAt = Date.now();
        }
        // Auto-unlock after 15 seconds if backend fails to respond
        setTimeout(() => { 
            localComputerModeTransitioning = false; 
            window.__skemi_poll_paused = false;
            if (window.desktopAgent) window.desktopAgent._modeChangeInProgress = false;
        }, 15000);
    }
    
    const response = await fetch(`/api/local-computer/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (data.ok || data.success === true) {
        if (path === "mode" || path === "phantom/start" || path === "phantom/lock") {
            // Give the backend more time to stabilize state (e.g. 4s)
            setTimeout(() => {
                localComputerModeTransitioning = false;
                window.__skemi_poll_paused = false;
                if (window.desktopAgent) {
                    window.desktopAgent._modeChangeInProgress = false;
                    if (data.mode) {
                        window.desktopAgent.mode = data.mode;
                        localStorage.setItem(COMPUTER_MODE_KEY(), data.mode);
                    }
                    // Persist phantom lock if backend confirms it
                    if (data.mode === 'phantom' && data.phantom_lock_active) {
                        const rawDesktopIdx = Number(data.locked_desktop_index ?? data.target_desktop_index);
                        const desktopIdx = Number.isFinite(rawDesktopIdx) && (rawDesktopIdx > 0 || rawDesktopIdx === -2) ? rawDesktopIdx : -1;
                        if (desktopIdx !== -1) {
                            // Ensure a valid lock token exists — use backend's, or generate one if missing
                            let lockToken = String(data.phantom_lock_token || '').trim();
                            if (!lockToken) {
                                lockToken = window.desktopAgent.getPhantomLockToken();
                            }
                            window.desktopAgent.phantomLockToken = lockToken;
                            try { sessionStorage.setItem(window.desktopAgent.phantomLockTokenKey, lockToken); } catch(e) {}
                            window.desktopAgent.selectedDesktopIndex = desktopIdx;
                            try {
                                sessionStorage.setItem(window.desktopAgent.phantomDesktopSessionKey, String(desktopIdx));
                                localStorage.setItem(COMPUTER_PHANTOM_INDEX_KEY(), String(desktopIdx));
                            } catch(e) {}
                        }
                    }
                    // Sync UI labels and modeButtons
                    window.desktopAgent.syncConversationModeLabel();
                    const modeButtons = window.desktopAgent.dom.modeSwitch ? Array.from(window.desktopAgent.dom.modeSwitch.querySelectorAll('[data-mode]')) : [];
                    modeButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === window.desktopAgent.mode));
                    if (window.desktopAgent.dom.modeNote) {
                        window.desktopAgent.dom.modeNote.innerHTML = window.desktopAgent.mode === 'phantom'
                            ? '<i class="fas fa-ghost"></i> <strong>Phantom:</strong> AI controls a separate locked desktop. The stream is watch-only for you.'
                            : '<i class="fas fa-bolt"></i> <strong>Live Control:</strong> AI operates your current desktop via background ghost-input — your mouse and focus stay yours.';
                    }
                    window.desktopAgent.ingestLocalComputerStatus(data);
                    window.desktopAgent.updateRuntimeMeta(data);
                }
                // Mode switching is now handled by the AgentController class in Computer.html
                // to ensure synchronized state and UI overlays.
                void refreshLocalComputerStatus();
            }, 4000);
        }
        renderLocalComputerStatus(data);
    }
    return data;
}



async function runLocalComputerCommand() {
    const commandField = document.getElementById("scLocalCommand") || localComputerCommandInput;
    const command = String(commandField?.value || "").trim();
    if (!command) {
        renderLocalComputerStatus({
            connected: false,
            mode: "live",
            notes: [t("Hay nhap yeu cau cho Local Computer.", "Enter a Local Computer request.")],
        });
        return;
    }
    if (commandField) commandField.value = "";
    if (localComputerRunBtn) {
        localComputerRunBtn.disabled = true;
        localComputerRunBtn.textContent = "Starting...";
    }
    try {
        const mode = localPhantomModeBtn?.classList.contains("surface-btn-accent") ? "phantom" : "live";
        const body = { command, mode, consent: true };
        if (mode === "phantom" && window.desktopAgent && (Number(window.desktopAgent.selectedDesktopIndex) > 0 || Number(window.desktopAgent.selectedDesktopIndex) === -2)) {
            body.desktop_index = Number(window.desktopAgent.selectedDesktopIndex);
            body.lock_token = window.desktopAgent.getPhantomLockToken?.() || "";
        }
        const payload = await postLocalComputerAction("run", body);
        renderLocalComputerStatus({
            ...payload,
            notes: [
                `${mode === "phantom" ? "Skemi Phantom" : "Live Control"}: ${command}`,
                t("Local Companion dang chay that, co stream va kill switch.", "Local Companion is running with stream and kill switch."),
                ...(Array.isArray(payload.notes) ? payload.notes : []),
            ],
        });
    } catch (error) {
        renderLocalComputerStatus({
            connected: false,
            notes: [error.message || "Local Computer command failed."],
        });
    } finally {
        if (localComputerRunBtn) {
            localComputerRunBtn.disabled = false;
            localComputerRunBtn.textContent = t("Chay", "Run");
        }
    }
}

function setSurfaceOverlayVisible(visible, text = "") {
    if (!surfaceOverlay) return;
    if (text) setSurfaceStatus(text);
    surfaceOverlay.classList.toggle("hidden", !visible);
}

function showSurfacePulse(point) {
    if (!surfaceStage || !point) return;
    if (!surfacePulseEl) {
        surfacePulseEl = document.createElement("div");
        surfacePulseEl.className = "surface-pulse";
        surfaceStage.appendChild(surfacePulseEl);
    }
    const rect = surfaceStage.getBoundingClientRect();
    const x = Math.min(Math.max(point.x, 0), rect.width);
    const y = Math.min(Math.max(point.y, 0), rect.height);
    surfacePulseEl.style.left = `${x}px`;
    surfacePulseEl.style.top = `${y}px`;
    surfacePulseEl.classList.remove("show");
    void surfacePulseEl.offsetWidth;
    surfacePulseEl.classList.add("show");
}

function setSurfaceTimelineVisible(visible) {
    if (!surfaceTimeline) return;
    surfaceTimeline.classList.toggle("show", Boolean(visible));
}
function setSurfaceStreamVisible(visible) {
    surfaceStreamVisible = Boolean(visible);
    surfaceBrowserPanel?.classList.toggle("surface-main-hidden", !surfaceStreamVisible);
    if (surfaceStreamToggleBtn) {
        surfaceStreamToggleBtn.setAttribute("aria-pressed", String(surfaceStreamVisible));
    }
    if (surfaceStreamToggleLabel) {
        surfaceStreamToggleLabel.textContent = surfaceStreamVisible
            ? t("Ẩn stream", "Hide stream")
            : t("Hiện stream", "Show stream");
    }
}

async function requestSurfaceAssistantStream(commandText) {
    const language = getUiLanguage();
    const prompt = language === "vi"
        ? `Bạn là giọng phản hồi của Skemi Control đang điều khiển Virtual Browser. Hãy phản hồi ngắn, rõ, chuyên nghiệp bằng tiếng Việt, mô tả bạn đang làm gì cho người dùng theo thời gian thực, không nhắc tới prompt này. Yêu cầu của người dùng: ${commandText}`
        : `You are the live operator voice for Skemi Control controlling a virtual browser. Reply briefly, clearly, and professionally in English, describing what you are doing in real time. Do not mention this prompt. User request: ${commandText}`;
    const response = await fetch("/api/ask_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            question: prompt,
            language,
            user_id: "computer_surface",
            deep_research: false,
        }),
    });
    if (!response.ok || !response.body) {
        throw new Error(t("AI phản hồi tạm thời không khả dụng.", "Live AI response is temporarily unavailable."));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let answer = "";

    while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";

        for (const chunk of chunks) {
            const dataLine = chunk
                .split("\n")
                .map((line) => line.trim())
                .find((line) => line.startsWith("data: "));
            if (!dataLine) continue;
            try {
                const payload = JSON.parse(dataLine.slice(6));
                if (payload.status || payload.label) {
                    setSurfaceThinking(true, payload.label || payload.status);
                }
                if (payload.token) {
                    answer += String(payload.token);
                    if (!surfaceHandoffActive) {
                        setSurfaceResponse(answer.trim() || payload.token);
                    }
                }
                if (payload.result && !answer) {
                    answer = String(payload.result);
                    if (!surfaceHandoffActive) {
                        setSurfaceResponse(answer);
                    }
                }
                if (payload.complete) {
                    return answer.trim() || String(payload.result || "").trim();
                }
            } catch {
                // ignore malformed sse chunk
            }
        }

        if (done) break;
    }

    return answer.trim();
}

function setActiveSurfaceTab(tab) {
    if (!virtualBrowserTab || !localComputerTab) return;
    const isVirtual = tab === "virtual";
    virtualBrowserTab.classList.toggle("active", isVirtual);
    localComputerTab.classList.toggle("active", !isVirtual);
    if (surfaceWorkspace) surfaceWorkspace.hidden = !isVirtual;
    if (localComputerPanel) localComputerPanel.hidden = isVirtual;
}

function getSurfaceSessionId() {
    return String(localStorage.getItem(SURFACE_SESSION_KEY) || "").trim();
}

function setSurfaceSessionId(value) {
    const normalized = String(value || "").trim();
    if (!normalized) {
        localStorage.removeItem(SURFACE_SESSION_KEY);
        return;
    }
    localStorage.setItem(SURFACE_SESSION_KEY, normalized);
}

async function revealPhantomWindow() {
    if (!surfaceSessionId) return;
    try {
        await fetch("/api/computer/manual-action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: surfaceSessionId,
                action: "reveal"
            })
        });
        setSurfaceResponse(t("Đã gửi lệnh hiện cửa sổ. Vui lòng kiểm tra màn hình máy tính của bạn.", "Reveal command sent. Please check your computer screen."));
    } catch (error) {
        setSurfaceResponse(t("Lỗi khi thực hiện hiện cửa sổ.", "Error revealing window."));
    }
}

async function ensureSurfaceReady() {
    try {
        setSurfaceOverlayVisible(true, t("Đang kết nối Chrome ảo...", "Connecting virtual Chrome..."));
        const reuseId = getSurfaceSessionId();
        const response = await fetch("/api/computer/ready", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                reuse_session_id: reuseId || null,
                sticky: true,
                transport_preference: "mjpeg",
                browser_shell: "chrome_like",
            }),
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Surface not ready.");
        }
        surfaceSessionId = String(payload.session_id || reuseId || "").trim();
        setSurfaceSessionId(surfaceSessionId);
        setSurfaceStatus(payload.state_label || t("Chrome ảo sẵn sàng.", "Virtual Chrome is ready."));
        updateSurfaceMeta(payload);
        pushSurfaceActivity(t("Đã sẵn sàng", "Ready"), payload.current_url || "about:blank");
        if (surfaceOverlayTimer) clearTimeout(surfaceOverlayTimer);
        surfaceOverlayTimer = setTimeout(() => setSurfaceOverlayVisible(false), 600);
        return surfaceSessionId;
    } catch (error) {
        setSurfaceStatus(error.message || t("Virtual Browser đang ngoại tuyến.", "Virtual browser is offline."));
        setSurfaceOverlayVisible(true);
        return "";
    }
}

async function enableSurfaceHistory() {
    if (!surfaceSessionId || surfaceHistoryEnabled) return;
    try {
        const response = await fetch("/api/computer/history/enable", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: surfaceSessionId }),
        });
        const payload = await response.json();
        if (response.ok && payload.success) {
            surfaceHistoryEnabled = true;
            await fetchSurfaceHistory();
        }
    } catch {
        // ignore
    }
}

function stopSurfaceStreams() {
    if (surfaceHistoryTimer) {
        clearInterval(surfaceHistoryTimer);
        surfaceHistoryTimer = null;
    }
    if (surfaceStatusTimer) {
        clearInterval(surfaceStatusTimer);
        surfaceStatusTimer = null;
    }
}

async function pollSurfaceStatus() {
    if (!surfaceSessionId) return;
    try {
        const response = await fetch(`/api/computer/status?session_id=${encodeURIComponent(surfaceSessionId)}`, {
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Surface status unavailable.");
        }
        updateSurfaceMeta(payload);
        const fragments = [payload.state_label || t("Virtual Browser sẵn sàng.", "Virtual browser ready.")];
        if (Number(payload.queued_actions || 0) > 0) {
            fragments.push(t(`${payload.queued_actions} tác vụ chờ`, `${payload.queued_actions} queued`));
        }
        setSurfaceStatus(fragments.join(" | "));
        
        if (surfaceRevealBtn) {
            const isPhantom = surfaceMode === "background" || surfaceMode === "phantom";
            surfaceRevealBtn.style.display = (isPhantom && payload.state === "running") ? "inline-block" : "none";
        }
    } catch {
        if (surfacePlaybackMode === "live") {
            setSurfaceOverlayVisible(true, t("Đang nối lại màn hình live...", "Reconnecting live view..."));
        }
    }
}

async function fetchSurfaceHistory() {
    if (!surfaceSessionId) return;
    try {
        const response = await fetch(`/api/computer/history/manifest?session_id=${encodeURIComponent(surfaceSessionId)}`);
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            return;
        }
        surfaceHistory = Array.isArray(payload.segments) ? payload.segments : [];
        surfaceHistoryEnabled = Boolean(payload.history_enabled);
        if (surfaceTimelineRange) {
            surfaceTimelineRange.max = Math.max(0, surfaceHistory.length - 1);
        }
        setSurfaceTimelineVisible(surfaceHistoryEnabled && (surfaceHistory.length > 1 || surfacePlaybackMode !== "live"));
    } catch {
        // ignore
    }
}

function setSurfaceFrame(url) {
    if (!surfaceImage || !url || url === lastFrameUrl) return;
    try {
        const parsed = new URL(url, window.location.origin);
        const tsParam = Number(parsed.searchParams.get("ts") || 0);
        if (tsParam && tsParam < lastFrameTs) {
            return;
        }
        if (tsParam) lastFrameTs = tsParam;
    } catch {
        // ignore parse errors
    }
    lastFrameUrl = url;
    surfaceImage.src = url;
    surfaceImage.onload = () => setSurfaceOverlayVisible(false);
    surfaceImage.onerror = () => {
        if (surfacePlaybackMode === "live") {
            setSurfaceOverlayVisible(true, "Reconnecting live view...");
        }
    };
}

function startSurfaceStream() {
    if (!surfaceSessionId) return;
    stopSurfaceStreams();
    surfacePlaybackMode = "live";
    setSurfaceTimelineVisible(surfaceHistoryEnabled && surfaceHistory.length > 1);
    if (surfaceTimelineLabel) surfaceTimelineLabel.textContent = "Live";
    if (surfaceTimelineRange) surfaceTimelineRange.value = surfaceTimelineRange.max || 0;
    setSurfaceOverlayVisible(true, t("Đang kết nối màn hình live...", "Connecting live view..."));
    lastFrameUrl = "";
    lastFrameTs = 0;
    setSurfaceFrame(`/api/computer/mjpeg?session_id=${encodeURIComponent(surfaceSessionId)}&ts=${Date.now()}`);
    surfaceHistoryTimer = setInterval(fetchSurfaceHistory, 3000);
    surfaceStatusTimer = setInterval(() => {
        void pollSurfaceStatus();
    }, 1000);
    void pollSurfaceStatus();
}

async function enterSurfacePlayback(index) {
    if (!surfaceSessionId) return;
    const resolvedIndex = Math.max(0, Math.min(Number(index) || 0, surfaceHistory.length - 1));
    surfacePlaybackMode = "playback";
    setSurfaceTimelineVisible(true);
    if (surfaceTimelineLabel) {
        surfaceTimelineLabel.textContent = `Playback ${resolvedIndex + 1}/${surfaceHistory.length}`;
    }
    try {
        const response = await fetch(`/api/computer/history/segment?session_id=${encodeURIComponent(surfaceSessionId)}&index=${resolvedIndex}`);
        const payload = await response.json();
        if (!response.ok || payload.success === false) return;
        if (payload.frame_url) {
            setSurfaceFrame(payload.frame_url);
        }
    } catch {
        // ignore
    }
}

function enableSurfaceManual(enabled) {
    surfaceManualEnabled = Boolean(enabled);
    if (surfaceManualBtn) {
        surfaceManualBtn.classList.toggle("active", surfaceManualEnabled);
        surfaceManualBtn.textContent = surfaceManualEnabled
            ? t("Điều khiển tay: Bật", "Manual control: On")
            : t("Điều khiển tay", "Manual control");
    }
    if (surfaceManualEnabled) {
        surfaceStage?.focus({ preventScroll: true });
        setSurfaceResponse(t(
            "Điều khiển tay đang bật. Bạn có thể click, cuộn và gõ trực tiếp trong khung trình duyệt.",
            "Manual control is on. You can click, scroll, and type directly in the browser frame."
        ));
        pushSurfaceActivity(t("Bật điều khiển tay", "Manual control enabled"));
    } else {
        flushSurfaceTextBuffer();
        pushSurfaceActivity(t("Tắt điều khiển tay", "Manual control disabled"));
    }
}

async function postSurfaceManualAction(type, payload) {
    const response = await fetch("/api/computer/manual-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: surfaceSessionId,
            action: type,
            payload: payload || {},
        }),
    });
    const payloadData = await response.json().catch(() => ({}));
    if (!response.ok || payloadData.success === false) {
        throw new Error(payloadData.error || "Manual control failed.");
    }
    const queueCount = Number(payloadData.queued_actions || 0);
    updateSurfaceMeta({ queued_actions: queueCount });
    setSurfaceStatus(
        queueCount > 0
            ? t(`Điều khiển tay | ${queueCount} tác vụ chờ`, `Manual control | ${queueCount} queued`)
            : t("Điều khiển tay đã sẵn sàng.", "Manual control is ready.")
    );
}

function queueSurfaceManualAction(type, payload = {}) {
    if (!surfaceSessionId || !surfaceManualEnabled) return;
    surfaceActionChain = surfaceActionChain
        .then(() => postSurfaceManualAction(type, payload))
        .catch((error) => {
            setSurfaceStatus(error?.message || "Manual control failed.");
            throw error;
        })
        .catch(() => {});
}

function flushSurfaceTextBuffer() {
    if (surfaceTextBufferTimer) {
        clearTimeout(surfaceTextBufferTimer);
        surfaceTextBufferTimer = null;
    }
    const text = surfaceTextBuffer;
    surfaceTextBuffer = "";
    if (!text) return;
    queueSurfaceManualAction("type", { text });
}

function bufferSurfaceText(text) {
    if (!text) return;
    surfaceTextBuffer += text;
    if (surfaceTextBuffer.length >= SURFACE_TEXT_BUFFER_MAX) {
        flushSurfaceTextBuffer();
        return;
    }
    if (surfaceTextBufferTimer) clearTimeout(surfaceTextBufferTimer);
    surfaceTextBufferTimer = setTimeout(() => flushSurfaceTextBuffer(), SURFACE_TEXT_BUFFER_IDLE_MS);
}

function sendSurfaceManualAction(type, payload) {
    if (!surfaceSessionId || !surfaceManualEnabled) return;
    if (type !== "type" && type !== "type_buffer") {
        flushSurfaceTextBuffer();
    }
    queueSurfaceManualAction(type, payload || {});
}

function getSurfaceRelativePoint(evt) {
    if (!surfaceStage) return null;
    const rect = surfaceStage.getBoundingClientRect();
    const x = Math.min(Math.max(evt.clientX - rect.left, 0), rect.width);
    const y = Math.min(Math.max(evt.clientY - rect.top, 0), rect.height);
    return { x, y, width: rect.width, height: rect.height, fit: "contain" };
}

function handleSurfaceKeydown(evt) {
    if (!surfaceManualEnabled) return;
    if (evt.ctrlKey || evt.metaKey || evt.altKey) return;
    const key = evt.key;
    if (["Backspace", "Delete", "Enter", "Escape", "Tab", "Home", "End", "PageUp", "PageDown"].includes(key) || key.startsWith("Arrow")) {
        evt.preventDefault();
        flushSurfaceTextBuffer();
        sendSurfaceManualAction("key", { key });
        return;
    }
    if (key && key.length === 1) {
        evt.preventDefault();
        bufferSurfaceText(key);
    }
}

function attachSurfaceListeners() {
    if (!surfaceStage) return;
    surfaceStage.setAttribute("tabindex", "0");
    surfaceStage.addEventListener("click", (evt) => {
        const point = getSurfaceRelativePoint(evt);
        if (!point) return;
        showSurfacePulse(point);
        sendSurfaceManualAction("click", point);
        surfaceStage.focus({ preventScroll: true });
    });
    surfaceStage.addEventListener("wheel", (evt) => {
        if (!surfaceManualEnabled) return;
        evt.preventDefault();
        const point = getSurfaceRelativePoint(evt);
        if (!point) return;
        sendSurfaceManualAction("scroll", { ...point, deltaY: evt.deltaY });
    }, { passive: false });
    surfaceStage.addEventListener("keydown", handleSurfaceKeydown);

    if (!surfaceKeyHandlerAttached) {
        document.addEventListener("keydown", (evt) => {
            const target = evt.target;
            const tag = target?.tagName;
            if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
            if (surfaceStage && (target === surfaceStage || surfaceStage.contains(target))) return;
            handleSurfaceKeydown(evt);
        });
        surfaceKeyHandlerAttached = true;
    }
}

function toggleSurfaceFullscreen() {
    if (!surfaceStage) return;
    const root = document.documentElement;
    if (!document.fullscreenElement) {
        surfaceStage.requestFullscreen?.();
        root.classList.add("surface-fullscreen");
        return;
    }
    document.exitFullscreen?.();
    root.classList.remove("surface-fullscreen");
}

async function resetSurfaceSession() {
    if (!surfaceSessionId) return;
    flushSurfaceTextBuffer();
    await fetch("/api/computer/reset-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: surfaceSessionId }),
    }).catch(() => {});
    stopSurfaceStreams();
    surfaceSessionId = "";
    setSurfaceSessionId("");
    setSurfaceStatus("Session reset.");
    updateSurfaceMeta({ title: "Virtual Browser", url: "about:blank", queued_actions: 0, transport: "mjpeg", prewarmed: false });
    setSurfaceTimelineVisible(false);
    surfaceActionChain = Promise.resolve();
    surfaceBootPromise = null;
    setSurfaceResponse(t(
        "Phiên đã được làm mới. Nhập yêu cầu mới để mở lại trình duyệt.",
        "The session has been reset. Enter a new request to relaunch the browser."
    ));
    pushSurfaceActivity(t("Làm mới phiên", "Session reset"));
}

function normalizeLooseText(value) {
    return String(value || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\u0111/g, "d")
        .trim();
}

function surfaceCommandHasExplicitUrl(value) {
    return /^(https?:\/\/|www\.|[a-z0-9-]+\.[a-z]{2,})(\/.*)?$/i.test(String(value || "").trim())
        || /\b(https?:\/\/|www\.)/i.test(String(value || ""));
}

function isSurfaceResumeCommand(input) {
    const raw = String(input || "").trim();
    if (!raw || surfaceCommandHasExplicitUrl(raw)) return false;
    const normalized = normalizeLooseText(raw);
    const exactCommands = new Set([
        "tiep tuc",
        "continue",
        "resume",
        "observe",
        "check again",
        "nhin lai",
        "quan sat lai",
        "kiem tra lai",
        "lam tiep",
        "tiep tuc lam",
    ]);
    if (exactCommands.has(normalized)) return true;
    return [
        "vao lai web do",
        "vo lai web do",
        "vao lai trang do",
        "vo lai trang do",
        "mo lai trang do",
    ].some((phrase) => normalized.includes(phrase));
}

function rememberSurfaceCommand(record = {}) {
    try {
        localStorage.setItem(SURFACE_LAST_COMMAND_KEY, JSON.stringify({
            ...record,
            at: Date.now(),
        }));
    } catch {
        // localStorage may be unavailable in restricted browser contexts.
    }
}

function getRememberedSurfaceCommand() {
    try {
        return JSON.parse(localStorage.getItem(SURFACE_LAST_COMMAND_KEY) || "null") || null;
    } catch {
        return null;
    }
}

function formatSurfacePageLabel(payload = {}, observation = {}) {
    const title = String(observation.visible_title || payload.current_title || "").trim();
    const url = String(observation.visible_url || payload.current_url || "").trim();
    if (title && url) return `${title} - ${url}`;
    return title || url || "about:blank";
}

function renderSurfaceObservation(payload = {}, options = {}) {
    const observation = payload.observation || payload.last_observation || {};
    surfaceLastObservation = observation;
    updateSurfaceMeta(payload);

    const status = String(observation.status || "unknown");
    const signals = Array.isArray(observation.signals) ? observation.signals : [];
    const summary = String(observation.summary || "Skemi da quan sat trang hien tai.").trim();
    const pageLabel = formatSurfacePageLabel(payload, observation);
    const signalLabel = signals.length ? ` (${signals.join(", ")})` : "";
    const isBlocked = Boolean(observation.needs_user) || status === "challenge";
    surfaceHandoffActive = isBlocked;

    if (isBlocked) {
        const vi = `${summary}\n\nMinh se dung dieu khien tu dong o day de khong bao done gia. Ban xu ly checkpoint/CAPTCHA/canh bao truc tiep trong stream, roi nhap "tiep tuc" de Skemi nhin lai va lam tiep.${signalLabel}`;
        const en = `${summary}\n\nI will pause automatic control here instead of pretending it is done. Please handle the checkpoint/CAPTCHA/browser warning in the stream, then type "continue" so Skemi can observe again and resume.${signalLabel}`;
        setSurfaceStatus(t("Can ban xu ly checkpoint trong stream.", "Manual checkpoint needed in the stream."));
        setSurfaceResponse(t(vi, en));
        setSurfaceThinking(false);
        pushSurfaceActivity(t("Can handoff", "Handoff needed"), pageLabel);
        return { payload, observation, status, blocked: true };
    }

    if (status === "blank" || status === "loading_or_empty" || status === "not_ready") {
        const vi = `${summary}\n\nNeu trang vua duoc ban xu ly xong, nhap "tiep tuc" de minh quan sat lai thay vi dieu huong lung tung.`;
        const en = `${summary}\n\nIf you just handled the page manually, type "continue" and I will observe again instead of navigating away.`;
        setSurfaceStatus(summary);
        setSurfaceResponse(t(vi, en));
        pushSurfaceActivity(t("Dang quan sat", "Observing"), pageLabel);
        return { payload, observation, status, blocked: false };
    }

    const finalText = options.isResume
        ? t(`Minh da nhin lai trang hien tai: ${pageLabel}. Gui buoc tiep theo hoac noi ro viec can lam tren trang nay.`, `I observed the current page: ${pageLabel}. Send the next step or tell me exactly what to do on this page.`)
        : t(`Da mo va quan sat trang: ${pageLabel}. Minh se khong coi la hoan tat neu con buoc can lam tiep.`, `Opened and observed: ${pageLabel}. I will not treat this as complete if more work is needed.`);
    setSurfaceStatus(summary);
    if (!options.keepAssistantText) {
        setSurfaceResponse(finalText);
    }
    pushSurfaceActivity(options.isResume ? t("Da quan sat lai", "Observed again") : t("Da quan sat", "Observed"), pageLabel);
    return { payload, observation, status, blocked: false };
}

async function observeSurface(sourceText = "", options = {}) {
    const response = await fetch(`/api/computer/observe?session_id=${encodeURIComponent(surfaceSessionId)}&ts=${Date.now()}`, {
        cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
        throw new Error(payload.error || t("Khong the quan sat trang hien tai.", "Could not observe the current page."));
    }
    const outcome = renderSurfaceObservation(payload, { ...options, isResume: Boolean(options.isResume) });
    return outcome;
}

function normalizeSurfaceCommand(input) {
    const raw = String(input || "").trim();
    if (!raw) return { mode: "empty", value: "" };
    if (isSurfaceResumeCommand(raw)) return { mode: "observe", value: raw };

    const lowered = raw.toLowerCase();
    const prefixes = [
        "mở ",
        "truy cập ",
        "đi tới ",
        "vào ",
        "open ",
        "visit ",
        "go to ",
        "navigate to ",
    ];
    for (const prefix of prefixes) {
        if (lowered.startsWith(prefix)) {
            return normalizeSurfaceCommand(raw.slice(prefix.length));
        }
    }

    const searchPrefixes = ["tìm ", "tra cứu ", "search ", "find "];
    for (const prefix of searchPrefixes) {
        if (lowered.startsWith(prefix)) {
            return { mode: "search", value: raw.slice(prefix.length).trim() };
        }
    }

    const looksLikeUrl = surfaceCommandHasExplicitUrl(raw);
    if (looksLikeUrl) {
        const normalizedUrl = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
        return { mode: "navigate", value: normalizedUrl };
    }

    return { mode: "search", value: raw };
}

async function runSurfaceAgentCommand(commandText) {
    const response = await fetch("/api/computer/agent-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: surfaceSessionId,
            command: commandText,
            max_steps: 4,
        }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
        throw new Error(payload.error || t("Agent browser khong thuc thi duoc.", "Browser agent could not run."));
    }
    startSurfaceStream();
    updateSurfaceMeta(payload);
    const targetCount = Array.isArray(payload.targets) ? payload.targets.length : 0;
    const tabCount = Array.isArray(payload.tabs) ? payload.tabs.length : 0;
    pushSurfaceActivity(t("Agent loop da verify", "Agent loop verified"), `${targetCount} targets | ${tabCount} tabs`);
    return renderSurfaceObservation(payload, { sourceText: commandText });
}

async function navigateSurface(targetUrl, sourceText = "") {
    const response = await fetch("/api/computer/navigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: surfaceSessionId,
            url: targetUrl,
            wait_until: "domcontentloaded",
        }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
        throw new Error(payload.error || t("Khong the mo trang nay.", "Could not open that page."));
    }
    startSurfaceStream();
    updateSurfaceMeta(payload);
    pushSurfaceActivity(t("Da gui lenh dieu huong", "Navigation sent"), payload.current_url || targetUrl);
    return renderSurfaceObservation(payload, { sourceText, targetUrl });
}

async function runSurfaceCommand() {
    const rawCommand = String(surfaceCommandInput?.value || "").trim();
    if (!rawCommand) {
        surfaceCommandInput?.focus();
        setSurfaceResponse(t("Hay nhap yeu cau truoc da.", "Please enter a request first."));
        return;
    }

    const originalLabel = surfaceRunBtn?.textContent || "";
    if (surfaceRunBtn) {
        surfaceRunBtn.disabled = true;
        surfaceRunBtn.textContent = t("Dang chay...", "Running...");
    }

    try {
        const existingId = surfaceSessionId || getSurfaceSessionId();
        if (existingId && !surfaceSessionId) {
            surfaceSessionId = existingId;
        }
        const readyId = existingId || await bootSurface();
        if (!readyId) {
            throw new Error(t("Khong the khoi tao Virtual Browser.", "Could not initialize the Virtual Browser."));
        }

        const command = normalizeSurfaceCommand(rawCommand);
        if (command.mode === "empty" || !command.value) {
            setSurfaceResponse(t("Hay nhap yeu cau ro hon mot chut.", "Please enter a clearer request."));
            return;
        }

        createSurfaceChatMessage("user", rawCommand);
        beginSurfaceAssistantTurn(
            t(
                "Da nhan yeu cau. Minh se nhin trang that truoc khi bao ket qua.",
                "Request received. I will observe the real page state before reporting completion."
            )
        );
        setSurfaceThinking(true, t("Dang quan sat browser...", "Observing the browser..."));

        if (command.mode === "observe") {
            setSurfaceResponse(t("Dang nhin lai trang hien tai...", "Observing the current page again..."));
            pushSurfaceActivity(t("Yeu cau quan sat lai", "Observe request"), rawCommand);
            const outcome = await observeSurface(rawCommand, { isResume: true });
            if (!outcome.blocked && outcome.status === "ready") {
                const remembered = getRememberedSurfaceCommand();
                const pageLabel = formatSurfacePageLabel(outcome.payload, outcome.observation);
                const resumePrompt = remembered?.rawCommand
                    ? `Nguoi dung vua xu ly handoff va yeu cau tiep tuc. Yeu cau goc: ${remembered.rawCommand}. Trang hien tai: ${pageLabel}. Hay bao trang thai that, ngan gon; neu chua thuc hien buoc tiep theo thi dung noi done.`
                    : `Nguoi dung yeu cau tiep tuc. Trang hien tai: ${pageLabel}. Hay bao trang thai that, ngan gon; neu chua thuc hien buoc tiep theo thi dung noi done.`;
                await requestSurfaceAssistantStream(resumePrompt).catch((error) => {
                    const fallback = error?.message || t("AI phan hoi tam thoi khong kha dung.", "Live AI response is temporarily unavailable.");
                    setSurfaceResponse(fallback);
                    return fallback;
                });
            }
            surfaceCommandInput?.select();
            return;
        }

        rememberSurfaceCommand({ rawCommand, mode: command.mode, value: command.value });
        setSurfaceResponse(
            command.mode === "navigate"
                ? t(`Dang mo ${command.value} va se verify trang that...`, `Opening ${command.value} and verifying the real page state...`)
                : t(`Dang de agent loop xu ly: ${command.value}`, `Running agent loop for: ${command.value}`)
        );
        pushSurfaceActivity(
            command.mode === "navigate" ? t("Yeu cau mo trang", "Open request") : t("Yeu cau agent", "Agent request"),
            rawCommand
        );

        const narrationCommand = `${rawCommand}\nLuu y cho Skemi: dung noi da xong/da vao thanh cong neu agent-run tra ve needs_user, CAPTCHA, can dang nhap, bi Chrome chan, hoac chua quan sat duoc noi dung.`;
        const narrationPromise = requestSurfaceAssistantStream(narrationCommand).catch((error) => {
            const fallback = error?.message || t("AI phan hoi tam thoi khong kha dung.", "Live AI response is temporarily unavailable.");
            setSurfaceResponse(fallback);
            return fallback;
        });
        const agentPromise = runSurfaceAgentCommand(rawCommand);
        const [agentResult] = await Promise.allSettled([agentPromise, narrationPromise]);

        if (agentResult.status === "rejected") {
            throw agentResult.reason;
        }
        const agentOutcome = agentResult.value;
        if (agentOutcome?.blocked) {
            renderSurfaceObservation(agentOutcome.payload, { sourceText: rawCommand });
        }
        surfaceCommandInput?.select();
    } catch (error) {
        const message = error?.message || t("Lenh khong thuc thi duoc.", "The command could not be completed.");
        setSurfaceStatus(message);
        setSurfaceResponse(message);
        pushSurfaceActivity(t("Loi", "Error"), message);
    } finally {
        setSurfaceThinking(false);
        if (surfaceRunBtn) {
            surfaceRunBtn.disabled = false;
            surfaceRunBtn.textContent = originalLabel || t("Gui", "Send");
        }
    }
}

async function bootSurface() {
    if (surfaceBootPromise) return surfaceBootPromise;
    surfaceBootPromise = (async () => {
        const readyId = await ensureSurfaceReady();
        if (!readyId) return "";
        await fetchSurfaceHistory();
        startSurfaceStream();
        if (!surfaceBrowserUrl || surfaceBrowserUrl.textContent.trim() === "about:blank") {
            setSurfaceOverlayVisible(true, t(
                "Nhập yêu cầu ở ô phía trên để bắt đầu làm việc với Virtual Browser.",
                "Enter a request above to start working with the Virtual Browser."
            ));
        }
        return readyId;
    })();
    try {
        return await surfaceBootPromise;
    } finally {
        surfaceBootPromise = null;
    }
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function setLoading(isLoading) {
    loadingEl?.classList.toggle("visible", isLoading);
    if (createBtn) createBtn.disabled = isLoading;
    if (refreshBtn) refreshBtn.disabled = isLoading;
}

function getWorkflowId() {
    return String(window.localStorage.getItem(WORKFLOW_STORAGE_KEY()) || "").trim();
}

function getSessionId() {
    return String(window.localStorage.getItem(SESSION_STORAGE_KEY()) || "").trim();
}

function setSessionId(sessionId) {
    const normalized = String(sessionId || "").trim();
    if (!normalized) {
        window.localStorage.removeItem(SESSION_STORAGE_KEY());
        return;
    }
    window.localStorage.setItem(SESSION_STORAGE_KEY(), normalized);
}

function parseListInput(value) {
    return String(value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function renderList(listEl, items, emptyText = "No data yet.") {
    if (!listEl) return;
    const normalized = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!normalized.length) {
        listEl.innerHTML = `<li class="agent-empty">${escapeHtml(emptyText)}</li>`;
        return;
    }
    listEl.innerHTML = normalized.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderMiniCardList(container, items, emptyText) {
    if (!container) return;
    const normalized = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!normalized.length) {
        container.innerHTML = `<p class="agent-empty">${escapeHtml(emptyText)}</p>`;
        return;
    }
    container.innerHTML = normalized.map((item) => `
        <div class="agent-mini-card">
            <strong>${escapeHtml(item.label || item.name || "Item")}</strong>
            <span>${escapeHtml(item.value || item.detail || "")}</span>
        </div>
    `).join("");
}

function renderArtifacts(artifacts) {
    const items = Array.isArray(artifacts) ? artifacts.filter(Boolean) : [];
    if (!artifactListEl) return;
    if (!items.length) {
        artifactListEl.innerHTML = '<p class="agent-empty">No workspace artifacts yet.</p>';
        return;
    }
    artifactListEl.innerHTML = items.map((artifact) => `
        <div class="agent-artifact-item">
            <strong>${escapeHtml(artifact.filename || artifact.artifact_id || "Artifact")}</strong>
            <span>${escapeHtml(artifact.workspace_path || "")}</span>
            <span>${escapeHtml(artifact.summary || artifact.source_stage || "")}</span>
        </div>
    `).join("");
}

function renderEvents(events) {
    const items = Array.isArray(events) ? events.filter(Boolean) : [];
    if (!eventListEl) return;
    if (!items.length) {
        eventListEl.innerHTML = '<p class="agent-empty">No event log yet.</p>';
        return;
    }
    eventListEl.innerHTML = items.slice().reverse().map((event) => `
        <div class="agent-history-item">
            <strong>${escapeHtml(event.type || "event")}</strong>
            <span>${escapeHtml(event.message || "")}</span>
            <span>${escapeHtml(event.ts || "")}</span>
        </div>
    `).join("");
}

function formatHandoffNote(note) {
    if (!note || typeof note !== "object") {
        return "No handoff note yet.";
    }

    const lines = [];
    if (note.stage_name) lines.push(`Stage: ${note.stage_name}`);
    if (note.done_summary) lines.push(`Done: ${note.done_summary}`);
    if (Array.isArray(note.key_findings) && note.key_findings.length) {
        lines.push("");
        lines.push("Key findings:");
        note.key_findings.slice(0, 4).forEach((item) => lines.push(`- ${item}`));
    }
    if (Array.isArray(note.artifacts_created) && note.artifacts_created.length) {
        lines.push("");
        lines.push("Artifacts:");
        note.artifacts_created.slice(0, 4).forEach((item) => {
            const label = typeof item === "string"
                ? item
                : `${item.filename || item.artifact_id || "artifact"} | ${item.workspace_path || ""}`;
            lines.push(`- ${label}`);
        });
    }
    if (note.recommended_next_action) {
        lines.push("");
        lines.push(`Next: ${note.recommended_next_action}`);
    }
    if (Array.isArray(note.open_risks) && note.open_risks.length) {
        lines.push("");
        lines.push("Open risks:");
        note.open_risks.slice(0, 3).forEach((item) => lines.push(`- ${item}`));
    }
    if (note.operator_notes) {
        lines.push("");
        lines.push(`Operator notes: ${note.operator_notes}`);
    }
    return lines.join("\n").trim() || "No handoff note yet.";
}

function resolveTargetHref(target) {
    const normalized = String(target || "").trim().toLowerCase();
    const map = {
        home: "Home.html",
        studio: "Home.html",
        search: "Search.html",
        quiz: "Quiz.html",
        chat: "Chat.html",
        settings: "Settings.html",
        promptagent: "PromptAgent.html",
        computer: "Computer.html",
        synapse: "Synapse.html",
    };
    return map[normalized] || "";
}

function renderRuntimeBlueprint(runtime) {
    const blueprint = runtime && typeof runtime === "object" ? runtime : {};
    if (runtimeSummaryEl) runtimeSummaryEl.textContent = blueprint.runtime_summary || "No runtime blueprint yet.";
    if (observationListEl) renderList(observationListEl, blueprint.observation_stack, "No observation stack yet.");
    if (interactionListEl) renderList(interactionListEl, blueprint.interaction_stack, "No interaction stack yet.");
    if (antiBotListEl) renderList(antiBotListEl, blueprint.anti_bot_strategy, "No anti-bot notes yet.");
    if (humanControlListEl) renderList(humanControlListEl, blueprint.human_control, "No human-control plan yet.");
    if (escapeListEl) renderList(escapeListEl, blueprint.escape_hatches, "No escape hatches yet.");
    if (blockerListEl) renderList(blockerListEl, blueprint.release_blockers, "No release blockers yet.");
    if (milestoneListEl) renderList(milestoneListEl, blueprint.build_milestones, "No build milestones yet.");
}

function renderDisplayPolicy(policy) {
    const displayPolicy = policy && typeof policy === "object" ? policy : {};
    const finalOnly = Boolean(displayPolicy.final_response_only);
    const showDiagnostics = !finalOnly && Boolean(displayPolicy.show_step_log);
    if (diagnosticsDetailsEl) {
        diagnosticsDetailsEl.hidden = !showDiagnostics;
        diagnosticsDetailsEl.open = showDiagnostics;
    }
    if (runtimeDetailsEl) {
        runtimeDetailsEl.hidden = finalOnly;
        runtimeDetailsEl.open = !finalOnly;
    }
    if (metaPanelEl) {
        metaPanelEl.hidden = finalOnly;
    }
    if (artifactPanelEl) {
        artifactPanelEl.hidden = finalOnly;
    }
}

function updateContext() {
    const workflowId = getWorkflowId();
    const sessionId = getSessionId();
    const parts = [];
    if (workflowId) parts.push(`workflow ${workflowId}`);
    if (sessionId) parts.push(`session ${sessionId}`);
    if (workflowContextEl) {
        workflowContextEl.textContent = parts.length
            ? `Connected to ${parts.join(" | ")}.`
            : "No workflow or session active yet.";
    }
}

function clearSessionView(message = "No session yet.") {
    currentSession = null;
    if (summaryEl) summaryEl.textContent = message;
    if (targetEl) targetEl.textContent = "The first target surface will appear after session creation.";
    if (sessionMetaEl) renderMiniCardList(sessionMetaEl, [], "No session metadata yet.");
    if (workspaceMetaEl) renderMiniCardList(workspaceMetaEl, [], "No workspace metadata yet.");
    if (actionListEl) renderList(actionListEl, [], "No action queue yet.");
    if (safetyListEl) renderList(safetyListEl, [], "No safety rules yet.");
    if (typeof renderArtifacts === 'function') renderArtifacts([]);
    if (handoffEl) handoffEl.textContent = "No handoff note yet.";
    if (typeof renderEvents === 'function') renderEvents([]);
    if (typeof renderRuntimeBlueprint === 'function') renderRuntimeBlueprint(null);
    if (typeof renderDisplayPolicy === 'function') renderDisplayPolicy(null);
    if (privacyStateEl) privacyStateEl.textContent = "Privacy not evaluated yet.";
    latestTargetHref = "";
}

function renderSession(session) {
    currentSession = session || null;
    if (!session) {
        clearSessionView();
        return;
    }

    const runtime = session.runtime_blueprint || {};
    const displayPolicy = session.display_policy || session.policy_state?.display_policy || {};
    const finalOnly = Boolean(displayPolicy.final_response_only);
    
    if (summaryEl) summaryEl.textContent = session.summary || "Session ready.";
    if (targetEl) targetEl.textContent = session.target_surface_label || session.target_surface || "Unknown";
    latestTargetHref = resolveTargetHref(session.target_surface);

    if (sessionMetaEl) {
        renderMiniCardList(sessionMetaEl, [
            { label: "Session ID", value: session.session_id || "-" },
            { label: "Status", value: session.status || "active" },
            { label: "Mode", value: session.mode || "operator" },
            { label: "Surface", value: session.surface_type || "server_vm" },
            { label: "Observer", value: runtime.primary_observer || "-" },
            { label: "Actor", value: runtime.primary_actor || "-" },
            { label: "Typing", value: runtime.typing_strategy || "-" },
            { label: "Kill switch", value: runtime.kill_switch || session.kill_switch || "-" },
            { label: "Report mode", value: finalOnly ? "Final only" : "Verbose" },
            { label: "Approval", value: session.approval_required ? "Required" : "Clear" },
            { label: "Privacy", value: session.privacy_state || "safe" },
        ], "No session metadata yet.");
    }

    if (workspaceMetaEl) {
        renderMiniCardList(workspaceMetaEl, [
            { label: "Workspace ID", value: session.workspace_id || "-" },
            { label: "Path", value: session.workspace_root || "-" },
            { label: "VM mount", value: session.vm_mount_path || "/mnt/skemi_shared" },
            { label: "Clipboard", value: "Text only" },
            { label: "Manifest", value: String(session.artifact_manifest_version || 1) },
            { label: "Stream", value: runtime.stream_transport || session.stream_transport || "-" },
            { label: "Human control", value: runtime.human_control_mode || "-" },
            { label: "Blocked reason", value: session.blocked_reason || "none" },
        ], "No workspace metadata yet.");
    }

    if (actionListEl) renderList(actionListEl, finalOnly ? [] : session.action_queue, "No action queue yet.");
    if (safetyListEl) renderList(safetyListEl, session.safety_rules, "No safety rules yet.");
    if (typeof renderArtifacts === 'function') renderArtifacts(session.artifacts);
    if (handoffEl) handoffEl.textContent = formatHandoffNote(session.handoff_note);
    if (typeof renderEvents === 'function') renderEvents(finalOnly ? [] : session.events);
    if (typeof renderRuntimeBlueprint === 'function') renderRuntimeBlueprint(runtime);
    if (typeof renderDisplayPolicy === 'function') renderDisplayPolicy(displayPolicy);

    if (privacyStateEl) {
        privacyStateEl.textContent = session.privacy_state === "blocked_by_privacy"
            ? `Blocked: ${session.blocked_reason || "privacy protected"}`
            : `${session.privacy_state || "safe"} | redaction ${session.stream_redaction_active ? "on" : "off"}`;
    }
}

async function createSession() {
    const goal = String(goalInput?.value || "").trim();
    if (!goal) {
        clearSessionView("Please enter a goal before creating a session.");
        return;
    }
    setLoading(true);
    try {
        const response = await fetch("/api/computer/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                goal,
                mode: String(modeSelect?.value || "operator").trim(),
                preferred_surface: String(preferredSurfaceSelect?.value || "").trim(),
                surface_type: String(surfaceTypeSelect?.value || "server_vm").trim(),
                final_response_only: false,
                show_live_plan: true,
                show_step_log: true,
                workflow_id: getWorkflowId(),
            }),
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Could not create the session.");
        }
        const session = payload.session || null;
        setSessionId(session?.session_id || "");
        updateContext();
        renderSession(session);
        await enableSurfaceHistory();
    } catch (error) {
        clearSessionView(error.message || "Failed to create the session.");
    } finally {
        setLoading(false);
    }
}

async function loadSession() {
    const sessionId = getSessionId();
    if (!sessionId) {
        clearSessionView();
        updateContext();
        return;
    }
    setLoading(true);
    try {
        const response = await fetch(`/api/computer/sessions/${encodeURIComponent(sessionId)}`);
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Could not load the session.");
        }
        renderSession(payload.session || null);
    } catch (error) {
        clearSessionView(error.message || "Failed to load the session.");
    } finally {
        updateContext();
        setLoading(false);
    }
}

async function postSessionAction(path, note = "") {
    const sessionId = getSessionId();
    if (!sessionId) return;
    setLoading(true);
    try {
        const response = await fetch(`/api/computer/sessions/${encodeURIComponent(sessionId)}/${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ note }),
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || `Could not run action ${path}.`);
        }
        renderSession(payload.session || null);
    } catch (error) {
        clearSessionView(error.message || `Failed to run ${path}.`);
    } finally {
        setLoading(false);
    }
}

async function evaluatePrivacy() {
    const sessionId = getSessionId();
    if (!sessionId) return;
    setLoading(true);
    try {
        const response = await fetch(`/api/computer/sessions/${encodeURIComponent(sessionId)}/privacy/evaluate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                active_process: String(privacyProcessInput?.value || "").trim(),
                window_title: String(privacyTitleInput?.value || "").trim(),
                ui_roles: parseListInput(privacyRolesInput?.value),
                sensitive_signals: parseListInput(privacySignalsInput?.value),
                user_blacklist: parseListInput(privacyBlacklistInput?.value),
                allow_override: Boolean(privacyAllowOverrideInput?.checked),
            }),
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Could not evaluate privacy.");
        }
        renderSession(payload.session || null);
    } catch (error) {
        clearSessionView(error.message || "Privacy evaluation failed.");
    } finally {
        setLoading(false);
    }
}

function openTargetSurface() {
    if (!latestTargetHref) return;
    window.location.href = latestTargetHref;
}

document.addEventListener("DOMContentLoaded", () => {
    applyComputerCopy();
    updateContext();
    setActiveSurfaceTab("virtual");
    createBtn?.addEventListener("click", () => void createSession());
    refreshBtn?.addEventListener("click", () => void loadSession());
    resumeBtn?.addEventListener("click", () => void postSessionAction("resume", "Resume requested from Skemi Control UI."));
    interruptBtn?.addEventListener("click", () => void postSessionAction("interrupt", "Interrupted from Skemi Control UI."));
    takeoverBtn?.addEventListener("click", () => void postSessionAction("takeover", "User requested takeover from Skemi Control UI."));
    approveBtn?.addEventListener("click", () => void postSessionAction("approve", "Approved from Skemi Control UI."));
    denyBtn?.addEventListener("click", () => void postSessionAction("deny", "Denied from Skemi Control UI."));
    privacyBtn?.addEventListener("click", () => void evaluatePrivacy());
    openSurfaceBtn?.addEventListener("click", openTargetSurface);
    void loadSession();

    if (virtualBrowserTab && localComputerTab) {
        virtualBrowserTab.addEventListener("click", () => {
            setActiveSurfaceTab("virtual");
            void bootSurface();
        });
        localComputerTab.addEventListener("click", () => {
            setActiveSurfaceTab("local");
            void refreshLocalComputerStatus();
        });
    }
    surfaceResetBtn?.addEventListener("click", () => void resetSurfaceSession());
    surfaceRevealBtn?.addEventListener("click", () => void revealPhantomWindow());
    surfaceManualBtn?.addEventListener("click", () => enableSurfaceManual(!surfaceManualEnabled));
    surfaceFullscreenBtn?.addEventListener("click", toggleSurfaceFullscreen);
    surfaceStreamToggleBtn?.addEventListener("click", () => setSurfaceStreamVisible(!surfaceStreamVisible));
    surfaceRunBtn?.addEventListener("click", () => void runSurfaceCommand());
    surfaceCommandInput?.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter") {
            evt.preventDefault();
            void runSurfaceCommand();
        }
    });
    document.addEventListener("fullscreenchange", () => {
        if (!document.fullscreenElement) {
            document.documentElement.classList.remove("surface-fullscreen");
        }
    });
    surfaceLiveBtn?.addEventListener("click", () => startSurfaceStream());
    surfaceTimelineRange?.addEventListener("input", (evt) => {
        const value = evt.target?.value ?? 0;
        void enterSurfacePlayback(value);
    });
    localComputerRefreshBtn?.addEventListener("click", () => void refreshLocalComputerStatus());
    
    // btnUninstallVirtualDriver is handled by AgentController in Computer.html
    
    // Phantom Workflow Handlers
    document.getElementById("btnPhantomCreateNew")?.addEventListener("click", () => window.desktopAgent?.startPhantomWorkflow?.());
    document.getElementById("btnPhantomSelectExisting")?.addEventListener("click", () => window.desktopAgent?.startPhantomWorkflow?.());
    document.getElementById("btnPhantomCancel")?.addEventListener("click", () => {
        document.getElementById("scPhantomChoiceOverlay")?.classList.remove("active");
        if (typeof window.__phantom_workflow_resolve === 'function') {
            window.__phantom_workflow_resolve(false);
            window.__phantom_workflow_resolve = null;
        }
    });
    document.getElementById("btnPhantomPickerBack")?.addEventListener("click", () => {
        document.getElementById("scPhantomPickerOverlay")?.classList.remove("active");
        document.getElementById("scPhantomChoiceOverlay")?.classList.add("active");
    });
    document.getElementById("btnPhantomPickerCancel")?.addEventListener("click", () => {
        document.getElementById("scPhantomPickerOverlay")?.classList.remove("active");
        if (typeof window.__phantom_workflow_resolve === 'function') {
            window.__phantom_workflow_resolve(false);
            window.__phantom_workflow_resolve = null;
        }
    });
    document.getElementById("btnPhantomPickerCreateNew")?.addEventListener("click", () => window.desktopAgent?.startPhantomWorkflow?.());

    localComputerRunBtn?.addEventListener("click", () => void runLocalComputerCommand());
    localComputerCommandInput?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") void runLocalComputerCommand();
    });
    document.getElementById("scMicBtn")?.addEventListener("click", () => toggleLocalVoice());
    localComputerMockConnectBtn?.addEventListener("click", () => void postLocalComputerAction("connect", {
        machine_label: "This device",
        companion_version: "built-in-native",
        consent: true,
    }));
    localComputerDisconnectBtn?.addEventListener("click", async () => {
        const status = String(localComputerStatusPill?.textContent || "").toLowerCase();
        await postLocalComputerAction(status.includes("running") || status.includes("awaiting") ? "stop" : "disconnect");
    });
    // document.getElementById("scVoiceToggleBtn")?.addEventListener("click", () => void toggleVoiceControl());
    attachSurfaceListeners();
    setSurfaceStreamVisible(true);
    
    // V19.0: Persistent Status Recovery
    const lastSessionId = getSessionId();
    if (lastSessionId) {
        (function(){})("[Computer] Restoring active session:", lastSessionId);
        surfaceSessionId = lastSessionId;
        void pollSurfaceStatus();
        startSurfaceStream();
    }
    
    void refreshLocalComputerStatus();
    void bootSurface();
});

window.addEventListener("languageChanged", () => {
    applyComputerCopy();
});

// ===== VOICE BACKUP (Manual Mic) =====
let localRecognition = null;
function toggleLocalVoice() {
    const micBtn = document.getElementById("scMicBtn");
    const commandInput = document.getElementById("scLocalCommand") || localComputerCommandInput;

    if (localRecognition) {
        localRecognition.stop();
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        const vi = "Trình duyệt của bạn không hỗ trợ nhận dạng giọng nói.";
        const en = "Your browser does not support Speech Recognition.";
        alert(t(vi, en));
        return;
    }

    localRecognition = new SpeechRecognition();
    localRecognition.lang = 'vi-VN';
    localRecognition.continuous = false;
    localRecognition.interimResults = false;

    localRecognition.onstart = () => {
        micBtn?.classList.add("active");
        if (commandInput) commandInput.placeholder = t("Đang nghe...", "Listening...");
    };

    localRecognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        if (commandInput) {
            commandInput.value = text;
            // Auto run
            runLocalComputerCommand();
        }
    };

    localRecognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        stopLocalVoiceUI();
    };

    localRecognition.onend = () => {
        stopLocalVoiceUI();
    };

    try {
        localRecognition.start();
    } catch (e) {
        console.error(e);
        stopLocalVoiceUI();
    }
}

function stopLocalVoiceUI() {
    const micBtn = document.getElementById("scMicBtn");
    const commandInput = document.getElementById("scLocalCommand") || localComputerCommandInput;
    micBtn?.classList.remove("active");
    if (commandInput) {
        commandInput.placeholder = t("Nhập lệnh hoặc nói 'Skemi'...", "Enter command or say 'Skemi'...");
    }
    localRecognition = null;
}

