import { auth, db } from "./Firebase_config.js";
import { doc, getDoc, setDoc } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js";

export const SKEMI_CONFIG = {
  AUTH_BASE: 'http://127.0.0.1:8010/api/auth',
  SETTINGS_BASE: 'http://127.0.0.1:8010/api/user',
  CHAT_BASE: 'http://127.0.0.1:8010'
};

export function getAuthToken() {
  return localStorage.getItem('skemi_token')
    || document.cookie.match(/(?:^|;\s*)skemi_token=([^;]+)/)?.[1]
    || '';
}

export async function loadUserSettings() {
  try {
    const token = getAuthToken();
    if (!token) return {};
    const res = await fetch(`${SKEMI_CONFIG.SETTINGS_BASE}/settings`, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      credentials: 'include'
    });
    if (!res.ok) return {};
    const data = await res.json();
    const settings = data?.settings || {};
    if (settings.theme) {
      localStorage.setItem('skemi-theme', settings.theme);
      localStorage.setItem('chat-theme', settings.theme);
    }
    if (settings.language) {
      localStorage.setItem('skemi_language', settings.language);
    }
    if (settings.bg_color) {
      document.documentElement.style.setProperty('--bg', settings.bg_color);
    }
    if (settings.accent_color) {
      document.documentElement.style.setProperty('--accent', settings.accent_color);
    }
    window.dispatchEvent(new CustomEvent('themeChanged'));
    window.dispatchEvent(new StorageEvent('storage', { key: 'skemi_language', newValue: settings.language || '' }));
    return settings;
  } catch (e) {
    return {};
  }
}

export async function saveUserSetting(key, value) {
  try {
    await fetch(`${SKEMI_CONFIG.SETTINGS_BASE}/settings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      credentials: 'include',
      body: JSON.stringify({ key, value })
    });
  } catch (e) {
    // ignore network failures
  }
  try {
    localStorage.setItem(`skemi_${key}`, JSON.stringify(value));
  } catch (e) { }
}

export const LANGUAGE_CODES = ['vi','en','zh','ja','ko','es','fr','de','it','pt','ru','ar','hi','th','id','ms','tr','pl','nl','sv','no','da','fi','cs','sk','hu','ro','bg','hr','sr','sl','et','lv','lt','uk','el','he','fa','ur','bn','ta','te','ml','kn','gu','pa','mr','ne','si','my','km','lo','tl','sw','zu','af','xh','st','tn','sn','ny','mg','rw','so','am','ti','om','ha','yo','ig','ee','ak','bm','wo','ff','ln','ts','ve','nr','ca','eu','gl','is','ga','cy','mt','sq','mk','bs','be','kk','uz','az','ka','hy','mn','ps','sd','ckb','ug','ky','tg','tk'];
export const THEME_ORDER = ['light', 'dark', 'galaxy'];

export const DEFAULT_USER_DATA = {
  age_group: 'middle',
  age_range: '',
  subscription: 'free',
  prompts_remaining: 10,
  uploads_remaining: 3,
  quiz_rooms_remaining: 3,
  last_prompt_reset: Date.now(),
  email_verified: false,
  provider: 'email',
  // Match the main Skemi app's defaults (galaxy theme, Vietnamese) so a guest /
  // brand-new user visiting Chat doesn't get the whole app flipped to light+English.
  theme: 'galaxy',
  language: 'vi',
  linked_apps: {
    skemi: true,
    skemma_chat: true
  },
  settings: {
    quota_warn: true,
    security_warn: true,
    ephemeral_chat: true,
    desktop_notify: true,
    desktop_notifications: true,
    sound_notify: true,
    sound_effects: true,
    message_preview: true,
    email_notify: true,
    email_updates: false,
    startup_tips: true,
    compact_mode: false,
    animations_enabled: true,
    ai_personalize: true,
    read_receipts: true,
    show_online_status: true,
    safe_search: true,
    auto_translate_content: true,
    enter_to_send: true
  }
};
const PROTECTED_UI_BRANDS = Object.freeze(['Skemi', 'Skemma']);

const PACKS = {
  vi: {
    common: {
      settings: 'Cài đặt',
      openSkemi: 'Mở Skemi',
      backToSkemi: 'Quay lại Skemi',
      logout: 'Đăng xuất',
      save: 'Lưu thay đổi',
      reset: 'Khôi phục mặc định',
      cancel: 'Hủy',
      linked: 'Đã liên kết',
      notLoggedIn: 'Bạn chưa đăng nhập.',
      syncDone: 'Đã đồng bộ cài đặt tài khoản.',
      syncFailed: 'Không thể đồng bộ cài đặt.'
    },
    auth: {
      invalidEmail: 'Email không hợp lệ.',
      weakPassword: 'Mật khẩu phải có ít nhất 8 ký tự, gồm chữ và số.',
      passwordMismatch: 'Mật khẩu xác nhận không khớp.',
      ageTagRequired: 'Bạn cần chọn nhóm độ tuổi.',
      loginSuccess: 'Đăng nhập thành công.',
      signupSuccess: 'Đăng ký thành công. Hãy kiểm tra email để xác thực tài khoản.',
      emailUnverified: 'Tài khoản chưa xác thực email. Vui lòng kiểm tra hộp thư.',
      googleFailed: 'Đăng nhập Google thất bại.',
      facebookFailed: 'Đăng nhập Facebook thất bại.',
      loginFailed: 'Đăng nhập thất bại.',
      signupFailed: 'Đăng ký thất bại.'
    },
    settings: {
      pageTitle: 'Cài đặt Chat - Skemma',
      title: 'Cài đặt Chat',
      subtitle: 'Quản lý hồ sơ, giao diện, ngôn ngữ và liên kết giữa Skemma Chat với Skemi.',
      profile: 'Hồ sơ',
      appearance: 'Giao diện',
      security: 'Tùy chọn',
      links: 'Ứng dụng',
      displayName: 'Tên hiển thị',
      email: 'Email',
      ageTag: 'Tag độ tuổi',
      ageRange: 'Khoảng tuổi',
      ageRangePlaceholder: 'Ví dụ: 18-35',
      theme: 'Giao diện',
      language: 'Ngôn ngữ',
      themeHelp: 'Theme sẽ đồng bộ giữa Skemi và Skemma Chat khi bạn dùng cùng tài khoản Firebase.',
      languageHelp: 'Ngôn ngữ này sẽ được ưu tiên ở các trang có hỗ trợ đa ngôn ngữ.',
      light: 'Sáng',
      dark: 'Tối',
      galaxy: 'Galaxy',
      notificationsGroupTitle: 'Thông báo',
      notificationsGroupHelp: 'Chọn cách Skemma Chat thông báo cho bạn.',
      chatGroupTitle: 'Nội dung và chat',
      chatGroupHelp: 'Điều khiển hành vi nhập liệu, lịch sử và nội dung AI.',
      privacyGroupTitle: 'Quyền riêng tư',
      privacyGroupHelp: 'Quản lý khả năng hiển thị và mức độ an toàn của nội dung.',
      quotaWarn: 'Cảnh báo quota thấp',
      securityWarn: 'Cảnh báo bảo mật',
      ephemeral: 'Lưu hội thoại AI tạm thời',
      notifications: 'Thông báo trên trình duyệt',
      soundEffects: 'Âm thanh thông báo',
      emailUpdates: 'Email cập nhật',
      messagePreview: 'Xem trước nội dung thông báo',
      readReceipts: 'Báo đã xem',
      onlineStatus: 'Hiển thị trạng thái hoạt động',
      safeSearch: 'Lọc nội dung an toàn',
      autoTranslate: 'Tự dịch nhãn giao diện hỗ trợ',
      enterToSend: 'Nhấn Enter để gửi',
      linkedAppsTitle: 'Ứng dụng đã liên kết',
      linkedAppsDesc: 'Skemma Chat và Skemi dùng chung hồ sơ người dùng trong Firestore.',
      openChat: 'Mở Skemma Chat',
      openSkemiBtn: 'Mở Skemi',
      linkedStatus: 'Đang liên kết bằng cùng tài khoản Firebase',
      saveSuccess: 'Đã lưu cài đặt và đồng bộ với tài khoản.',
      resetSuccess: 'Đã khôi phục cài đặt mặc định của Chat.',
      clearLocal: 'Xóa cache local',
      clearLocalDone: 'Đã xóa dữ liệu local, giữ lại tài khoản hiện tại.',
      verified: 'Email đã xác thực.',
      unverified: 'Email chưa xác thực.',
      guestName: 'Khách',
      defaultName: 'Người dùng Skemma',
      young: 'Học sinh',
      middle: 'Người lao động',
      senior: 'Người lớn tuổi'
    },
    chat: {
      searchFriends: 'Tìm bạn bè...',
      friends: 'Bạn bè',
      search: 'Tìm kiếm',
      addFriend: 'Thêm bạn',
      createGroup: 'Tạo nhóm',
      chooseFriend: 'Chọn bạn để nhắn tin',
      assistant: 'Trợ lý AI',
      offline: 'Không hoạt động',
      voiceCall: 'Gọi thoại',
      videoCall: 'Gọi video',
      typing: 'Đang soạn tin...',
      placeholder: 'Nhập tin nhắn...',
      loading: 'Đang tải tin nhắn...',
      checkingNetwork: 'Đang kiểm tra mạng...',
      mediumConnection: 'Kết nối trung bình',
      fastConnection: 'Kết nối nhanh',
      slowConnection: 'Kết nối chậm',
      networkTip: 'Kiểm tra kết nối mạng để có trải nghiệm tốt nhất',
      retry: 'Thử lại',
      continue: 'Tiếp tục',
      friendsEmpty: 'Chưa có bạn bè',
      friendsEmptySubtext: 'Tìm và thêm bạn để bắt đầu trò chuyện',
      welcomeTitle: 'Chào mừng đến với Skemma Chat',
      welcomeSubtitle: 'Chọn một người bạn để bắt đầu trò chuyện',
      featureThemeTitle: 'Đổi giao diện',
      featureThemeHint: 'Nhấn vào nút mặt trăng',
      featureFriendsTitle: 'Danh sách bạn bè',
      featureFriendsHint: 'Nhấn vào nút menu',
      featureEmojiTitle: 'Biểu tượng cảm xúc',
      featureEmojiHint: 'Thêm emoji vào tin nhắn',
      featureAttachTitle: 'Đính kèm file',
      featureAttachHint: 'Gửi hình ảnh, video, tài liệu',
      featureVoiceTitle: 'Tin nhắn thoại',
      featureVoiceHint: 'Nhấn giữ để ghi âm',
      featureCallTitle: 'Gọi điện & Video call',
      featureCallHint: 'Kết nối trực tiếp với bạn bè',
      noMessagesWith: 'Bạn chưa có tin nhắn nào với {name}',
      noMessagesPrompt: 'Hãy bắt đầu cuộc trò chuyện bằng cách gửi một lời chào.',
      greetingHello: 'Xin chào',
      greetingMeet: 'Làm quen',
      greetingCheckin: 'Hỏi thăm',
      greetingTalk: 'Trò chuyện',
      greetingHelloText: '👋 Xin chào!',
      greetingMeetText: '😊 Rất vui được làm quen!',
      greetingCheckinText: '👍 Bạn khỏe không?',
      greetingTalkText: '💬 Bạn đang làm gì đấy?',
      removeAttachment: 'Bỏ file đính kèm',
      emojiTitle: 'Biểu tượng cảm xúc',
      attachTitle: 'Đính kèm file',
      deepResearchTitle: 'Nghiên cứu sâu (tìm kiếm toàn diện)',
      sendTitle: 'Gửi tin nhắn',
      stopTitle: 'Dừng',
      researchPlan: 'Kế hoạch nghiên cứu',
      edit: 'Chỉnh sửa',
      startResearch: 'Bắt đầu nghiên cứu',
      sources: 'Nguồn trích dẫn',
      analysisAssistant: 'Trợ lý',
      analysisStructured: 'Cấu trúc',
      analysisConcise: 'Ngắn gọn',
      analysisModeChanged: 'Chế độ phân tích: {mode}',
      voiceInputTitle: 'Nhập bằng giọng nói',
      voiceInputStopTitle: 'Dừng nhập giọng nói',
      voiceInputUnsupported: 'Trình duyệt này không hỗ trợ nhập giọng nói.',
      voiceInputListening: 'Đang nghe để chuyển thành văn bản...',
      voiceInputPermissionDenied: 'Không thể dùng mic. Vui lòng cấp quyền truy cập microphone.',
      voiceInputError: 'Không thể nhận giọng nói lúc này.',
      loadingErrorTitle: 'Kết nối có vấn đề',
      loadingErrorMessage: 'Đang cố gắng kết nối lại...',
      timeoutTitle: 'Đang mất nhiều thời gian hơn dự kiến',
      timeoutSubtitle: 'Kiểm tra kết nối internet của bạn',
      replying: 'Đang trả lời... Vui lòng đợi',
      sendNewMessage: 'Bạn có thể nhắn tin mới...',
      researchRunning: 'Đang thực hiện nghiên cứu theo kế hoạch...',
      stoppedResponse: 'Đã dừng phản hồi.',
      imageLabel: '[Hình ảnh]',
      videoLabel: '[Video]',
      youPrefix: 'Bạn:',
      noMessages: 'Chưa có tin nhắn',
      loadingFriendsError: 'Lỗi tải danh sách bạn bè',
      tryAgainLater: 'Vui lòng thử lại sau',
      userFallback: 'Người dùng',
      notFound: 'Không tìm thấy',
      couldNotLoadInfo: 'Không thể tải thông tin',
      justNow: 'Vừa xong',
      minutesAgo: '{count} phút',
      hoursAgo: '{count} giờ',
      yesterday: 'Hôm qua',
      daysAgo: '{count} ngày',
      searchNoUsers: 'Không tìm thấy người dùng nào',
      searchTryOther: 'Hãy thử tìm kiếm với từ khóa khác',
      alreadyFriend: 'Đã là bạn',
      blocked: 'Đang chặn',
      sent: 'Đã gửi',
      stableConnection: 'Kết nối ổn định',
      internetDisconnected: 'Mất kết nối internet',
      networkCheckFailed: 'Lỗi kiểm tra mạng',
      seen: 'Đã xem',
      themeChanged: 'Đã đổi giao diện sang {theme}.',
      deepResearchOn: 'Đã bật chế độ nghiên cứu sâu.',
      deepResearchOff: 'Đã tắt chế độ nghiên cứu sâu.'
    }
  },
  en: {
    common: {
      settings: 'Settings',
      openSkemi: 'Open Skemi',
      backToSkemi: 'Back to Skemi',
      logout: 'Log out',
      save: 'Save changes',
      reset: 'Reset defaults',
      cancel: 'Cancel',
      linked: 'Linked',
      notLoggedIn: 'You are not logged in.',
      syncDone: 'Account settings synced.',
      syncFailed: 'Could not sync settings.'
    },
    auth: {
      invalidEmail: 'Invalid email address.',
      weakPassword: 'Password must be at least 8 characters with letters and numbers.',
      passwordMismatch: 'Password confirmation does not match.',
      ageTagRequired: 'Please choose an age tag.',
      loginSuccess: 'Login successful.',
      signupSuccess: 'Sign-up successful. Please verify your email.',
      emailUnverified: 'Your email is not verified yet. Please check your inbox.',
      googleFailed: 'Google sign-in failed.',
      facebookFailed: 'Facebook sign-in failed.',
      loginFailed: 'Login failed.',
      signupFailed: 'Sign-up failed.'
    },
    settings: {
      pageTitle: 'Chat Settings - Skemma',
      title: 'Chat Settings',
      subtitle: 'Manage profile, appearance, language, and the shared account link between Skemma Chat and Skemi.',
      profile: 'Profile',
      appearance: 'Appearance',
      security: 'Preferences',
      links: 'Apps',
      displayName: 'Display name',
      email: 'Email',
      ageTag: 'Age tag',
      ageRange: 'Age range',
      ageRangePlaceholder: 'Example: 18-35',
      theme: 'Theme',
      language: 'Language',
      themeHelp: 'Theme syncs between Skemi and Skemma Chat when you use the same Firebase account.',
      languageHelp: 'This language is preferred across pages that support localization.',
      light: 'Light',
      dark: 'Dark',
      galaxy: 'Galaxy',
      notificationsGroupTitle: 'Notifications',
      notificationsGroupHelp: 'Choose how Skemma Chat alerts you.',
      chatGroupTitle: 'Content and chat',
      chatGroupHelp: 'Control input behavior, AI history, and content assistance.',
      privacyGroupTitle: 'Privacy and safety',
      privacyGroupHelp: 'Manage visibility and content safety for your account.',
      quotaWarn: 'Low quota alerts',
      securityWarn: 'Security alerts',
      ephemeral: 'Keep temporary AI chat history',
      notifications: 'Browser notifications',
      soundEffects: 'Notification sounds',
      emailUpdates: 'Email updates',
      messagePreview: 'Message previews in notifications',
      readReceipts: 'Read receipts',
      onlineStatus: 'Show online status',
      safeSearch: 'Safe content filter',
      autoTranslate: 'Auto-translate supported UI labels',
      enterToSend: 'Press Enter to send',
      linkedAppsTitle: 'Linked apps',
      linkedAppsDesc: 'Skemma Chat and Skemi use the same Firestore user profile.',
      openChat: 'Open Skemma Chat',
      openSkemiBtn: 'Open Skemi',
      linkedStatus: 'Linked through the same Firebase account',
      saveSuccess: 'Settings saved and synced to your account.',
      resetSuccess: 'Chat settings restored to defaults.',
      clearLocal: 'Clear local cache',
      clearLocalDone: 'Local data cleared while keeping the current account.',
      verified: 'Email verified.',
      unverified: 'Email not verified.',
      guestName: 'Guest',
      defaultName: 'Skemma user',
      young: 'Student',
      middle: 'Working adult',
      senior: 'Senior'
    },
    chat: {
      searchFriends: 'Search friends...',
      friends: 'Friends',
      search: 'Search',
      addFriend: 'Add friend',
      createGroup: 'Create group',
      chooseFriend: 'Choose a friend to chat',
      assistant: 'AI assistant',
      offline: 'Offline',
      voiceCall: 'Voice call',
      videoCall: 'Video call',
      typing: 'Typing...',
      placeholder: 'Type a message...',
      loading: 'Loading messages...',
      checkingNetwork: 'Checking network...',
      mediumConnection: 'Average connection',
      fastConnection: 'Fast connection',
      slowConnection: 'Slow connection',
      networkTip: 'Check your network connection for the best experience',
      retry: 'Retry',
      continue: 'Continue',
      friendsEmpty: 'No friends yet',
      friendsEmptySubtext: 'Find and add friends to start chatting',
      welcomeTitle: 'Welcome to Skemma Chat',
      welcomeSubtitle: 'Choose a friend to start chatting',
      featureThemeTitle: 'Switch theme',
      featureThemeHint: 'Tap the moon button',
      featureFriendsTitle: 'Friends list',
      featureFriendsHint: 'Tap the menu button',
      featureEmojiTitle: 'Emojis',
      featureEmojiHint: 'Add emoji to your message',
      featureAttachTitle: 'File attachments',
      featureAttachHint: 'Send images, video, or documents',
      featureVoiceTitle: 'Voice message',
      featureVoiceHint: 'Hold to record',
      featureCallTitle: 'Voice & video calls',
      featureCallHint: 'Connect directly with friends',
      noMessagesWith: 'You have no messages with {name} yet',
      noMessagesPrompt: 'Start the conversation by sending a greeting.',
      greetingHello: 'Say hi',
      greetingMeet: 'Introduce',
      greetingCheckin: 'Check in',
      greetingTalk: 'Chat',
      greetingHelloText: '👋 Hello!',
      greetingMeetText: '😊 Nice to meet you!',
      greetingCheckinText: '👍 How are you?',
      greetingTalkText: '💬 What are you up to?',
      removeAttachment: 'Remove attachment',
      emojiTitle: 'Emojis',
      attachTitle: 'Attach file',
      deepResearchTitle: 'Deep research (comprehensive search)',
      sendTitle: 'Send message',
      stopTitle: 'Stop',
      researchPlan: 'Research plan',
      edit: 'Edit',
      startResearch: 'Start research',
      sources: 'Sources',
      analysisAssistant: 'Assistant',
      analysisStructured: 'Structured',
      analysisConcise: 'Concise',
      analysisModeChanged: 'Analysis mode: {mode}',
      voiceInputTitle: 'Voice input',
      voiceInputStopTitle: 'Stop voice input',
      voiceInputUnsupported: 'This browser does not support voice input.',
      voiceInputListening: 'Listening and converting speech to text...',
      voiceInputPermissionDenied: 'Microphone access is required for voice input.',
      voiceInputError: 'Voice recognition is not available right now.',
      loadingErrorTitle: 'Connection issue',
      loadingErrorMessage: 'Trying to reconnect...',
      timeoutTitle: 'This is taking longer than expected',
      timeoutSubtitle: 'Check your internet connection',
      replying: 'Generating a reply... Please wait',
      sendNewMessage: 'You can send a new message...',
      researchRunning: 'Running research based on the plan...',
      stoppedResponse: 'Response stopped.',
      imageLabel: '[Image]',
      videoLabel: '[Video]',
      youPrefix: 'You:',
      noMessages: 'No messages yet',
      loadingFriendsError: 'Could not load friend list',
      tryAgainLater: 'Please try again later',
      userFallback: 'User',
      notFound: 'Not found',
      couldNotLoadInfo: 'Could not load info',
      justNow: 'Just now',
      minutesAgo: '{count} min',
      hoursAgo: '{count} hr',
      yesterday: 'Yesterday',
      daysAgo: '{count} d',
      searchNoUsers: 'No users found',
      searchTryOther: 'Try a different keyword',
      alreadyFriend: 'Already friends',
      blocked: 'Blocked',
      sent: 'Sent',
      stableConnection: 'Stable connection',
      internetDisconnected: 'Internet disconnected',
      networkCheckFailed: 'Network check failed',
      seen: 'Seen',
      themeChanged: 'Theme changed to {theme}.',
      deepResearchOn: 'Deep research mode enabled.',
      deepResearchOff: 'Deep research mode disabled.'
    }
  }
};

function safeParse(value, fallback = {}) {
  try {
    return JSON.parse(value || 'null') || fallback;
  } catch {
    return fallback;
  }
}

export const DEFAULT_APP_SETTINGS = Object.freeze({
  desktop_notify: true,
  sound_notify: true,
  message_preview: true,
  startup_tips: true,
  compact_mode: false,
  animations_enabled: true,
  ephemeral_chat: true,
  ai_personalize: true,
  quota_warn: true,
  security_warn: true
});

function readBooleanSetting(source, keys, fallback) {
  for (const key of keys) {
    if (typeof source?.[key] === 'boolean') return source[key];
  }
  return fallback;
}

function withCompatibilitySettings(settings = {}) {
  const normalized = {
    desktop_notify: readBooleanSetting(settings, ['desktop_notify', 'desktop_notifications'], DEFAULT_APP_SETTINGS.desktop_notify),
    sound_notify: readBooleanSetting(settings, ['sound_notify', 'sound_effects'], DEFAULT_APP_SETTINGS.sound_notify),
    message_preview: readBooleanSetting(settings, ['message_preview', 'email_notify', 'email_updates'], DEFAULT_APP_SETTINGS.message_preview),
    startup_tips: readBooleanSetting(settings, ['startup_tips'], DEFAULT_APP_SETTINGS.startup_tips),
    compact_mode: readBooleanSetting(settings, ['compact_mode'], DEFAULT_APP_SETTINGS.compact_mode),
    animations_enabled: readBooleanSetting(settings, ['animations_enabled', 'animations'], DEFAULT_APP_SETTINGS.animations_enabled),
    ephemeral_chat: readBooleanSetting(settings, ['ephemeral_chat'], DEFAULT_APP_SETTINGS.ephemeral_chat),
    ai_personalize: readBooleanSetting(settings, ['ai_personalize'], DEFAULT_APP_SETTINGS.ai_personalize),
    quota_warn: readBooleanSetting(settings, ['quota_warn'], DEFAULT_APP_SETTINGS.quota_warn),
    security_warn: readBooleanSetting(settings, ['security_warn'], DEFAULT_APP_SETTINGS.security_warn)
  };

  return {
    ...settings,
    ...normalized,
    desktop_notifications: normalized.desktop_notify,
    sound_effects: normalized.sound_notify,
    email_notify: normalized.message_preview,
    email_updates: normalized.message_preview,
    animations: normalized.animations_enabled
  };
}

const I18N_PACK_CACHE_KEY = 'skemi_i18n_pack_cache_v5';
const I18N_TEXT_CACHE_KEY = 'skemi_i18n_text_cache_v5';
const BASE_LANGUAGE_CODES = ['vi', 'en'];
const unavailableTranslationEndpoints = new Set();
let runtimeTranslationDisabled = false;

function buildTranslationEndpoints(pathname) {
  const endpoints = [];
  const currentOrigin = String(window.location.origin || '').replace(/\/+$/, '');
  const currentProtocol = String(window.location.protocol || 'http:');
  const currentHostname = String(window.location.hostname || '127.0.0.1');
  const currentPort = String(window.location.port || '').trim();
  const normalizedPath = String(pathname || 'translate-ui').replace(/^\/+/, '');

  if (currentOrigin) {
    endpoints.push(`${currentOrigin}/api/${normalizedPath}`);
    endpoints.push(`/api/${normalizedPath}`);
    if (currentPort === '8010') {
      endpoints.push(`${currentProtocol}//${currentHostname}:8001/api/${normalizedPath}`);
    } else {
      endpoints.push(`${currentProtocol}//${currentHostname}:8010/api/${normalizedPath}`);
    }
  } else {
    endpoints.push(`/api/${normalizedPath}`);
  }

  return [...new Set(endpoints)];
}

const TRANSLATION_ENDPOINTS = buildTranslationEndpoints('translate-ui');
const TRANSLATION_BATCH_ENDPOINTS = buildTranslationEndpoints('translate-ui-batch');

const runtimePackCache = safeParse(localStorage.getItem(I18N_PACK_CACHE_KEY), {});
const runtimeTextCache = safeParse(localStorage.getItem(I18N_TEXT_CACHE_KEY), {});
const pendingTranslations = new Map();
const pendingPackLoads = new Map();
const pendingLanguageRefresh = new Map();

function persistTranslationCaches() {
  try {
    localStorage.setItem(I18N_PACK_CACHE_KEY, JSON.stringify(runtimePackCache));
    localStorage.setItem(I18N_TEXT_CACHE_KEY, JSON.stringify(runtimeTextCache));
  } catch {}
}

function shouldUseRuntimeTranslation(code) {
  return !!code && !BASE_LANGUAGE_CODES.includes(code);
}

function emitLanguageChanged(code, ready = true) {
  window.dispatchEvent(new CustomEvent('languageChanged', {
    detail: { language: code, baseLanguage: getBaseLanguage(code), ready }
  }));
}

function scheduleLanguageRefresh(code, delay = 120) {
  if (!code || runtimeTranslationDisabled) return;
  if (pendingLanguageRefresh.has(code)) {
    clearTimeout(pendingLanguageRefresh.get(code));
  }
  const timer = setTimeout(() => {
    pendingLanguageRefresh.delete(code);
    if (getCurrentLanguage() !== code) return;
    emitLanguageChanged(code, true);
  }, delay);
  pendingLanguageRefresh.set(code, timer);
}

function protectUiBrandNames(text) {
  let next = String(text || '');
  const placeholders = [];
  PROTECTED_UI_BRANDS.forEach((brand, index) => {
    const token = `__CHAT_BRAND_${index}__`;
    if (next.includes(brand)) {
      next = next.split(brand).join(token);
      placeholders.push([token, brand]);
    }
  });
  return { text: next, placeholders };
}

function restoreUiBrandNames(text, placeholders = []) {
  let next = String(text || '');
  placeholders.forEach(([token, brand]) => {
    next = next.split(token).join(brand);
  });
  return next;
}

async function translateRawText(text, target, source = 'en') {
  if (!text || !target || source === target) return text;
  const trimmed = String(text).trim();
  if (!trimmed) return text;
  if (runtimeTranslationDisabled) return trimmed;

  const cacheKey = `${source}:${target}:${trimmed}`;
  if (runtimeTextCache[cacheKey]) return runtimeTextCache[cacheKey];
  if (pendingTranslations.has(cacheKey)) return pendingTranslations.get(cacheKey);
  const protectedPayload = protectUiBrandNames(trimmed);

  const task = (async () => {
    let hadEndpointFailure = false;
    for (const endpoint of TRANSLATION_ENDPOINTS) {
      if (unavailableTranslationEndpoints.has(endpoint)) continue;
      try {
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            q: protectedPayload.text,
            source,
            target,
            format: 'text'
          })
        });
        if (!resp.ok) {
          hadEndpointFailure = true;
          if (resp.status === 404 || resp.status === 501 || resp.status >= 500) {
            unavailableTranslationEndpoints.add(endpoint);
          }
          continue;
        }
        const data = await resp.json();
        const translated = restoreUiBrandNames(String(data?.translatedText || '').trim(), protectedPayload.placeholders);
        if (translated) {
          runtimeTextCache[cacheKey] = translated;
          persistTranslationCaches();
          return translated;
        }
      } catch {
        hadEndpointFailure = true;
        unavailableTranslationEndpoints.add(endpoint);
      }
    }
    if (hadEndpointFailure) {
      runtimeTranslationDisabled = true;
      pendingLanguageRefresh.forEach((timer) => clearTimeout(timer));
      pendingLanguageRefresh.clear();
    }
    return trimmed;
  })();

  pendingTranslations.set(cacheKey, task);
  try {
    return await task;
  } finally {
    pendingTranslations.delete(cacheKey);
  }
}

async function translateRawTextBatch(texts, target, source = 'en') {
  const originals = Array.from(new Set((texts || []).map((item) => String(item || '').trim()).filter(Boolean)));
  if (!originals.length || !target || source === target) return originals;
  if (runtimeTranslationDisabled) return originals;

  const resolved = new Map();
  const misses = [];
  originals.forEach((text) => {
    const cacheKey = `${source}:${target}:${text}`;
    if (runtimeTextCache[cacheKey]) {
      resolved.set(text, runtimeTextCache[cacheKey]);
    } else {
      misses.push(text);
    }
  });
  if (!misses.length) {
    return originals.map((text) => resolved.get(text) || text);
  }

  const protectedBatch = misses.map((item) => protectUiBrandNames(item));
  let hadEndpointFailure = false;
  for (const endpoint of TRANSLATION_BATCH_ENDPOINTS) {
    if (unavailableTranslationEndpoints.has(endpoint)) continue;
    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          texts: protectedBatch.map((item) => item.text),
          source,
          target
        })
      });
      if (!resp.ok) {
        hadEndpointFailure = true;
        if (resp.status === 404 || resp.status === 501 || resp.status >= 500) {
          unavailableTranslationEndpoints.add(endpoint);
        }
        continue;
      }
      const data = await resp.json();
      const translations = Array.isArray(data?.translations) ? data.translations : [];
      if (translations.length !== protectedBatch.length) {
        hadEndpointFailure = true;
        continue;
      }

      protectedBatch.forEach((entry, index) => {
        const original = misses[index];
        const translated = restoreUiBrandNames(String(translations[index] || '').trim() || original, entry.placeholders);
        const cacheKey = `${source}:${target}:${original}`;
        runtimeTextCache[cacheKey] = translated;
        resolved.set(original, translated);
      });
      persistTranslationCaches();
      return originals.map((text) => resolved.get(text) || text);
    } catch {
      hadEndpointFailure = true;
      unavailableTranslationEndpoints.add(endpoint);
    }
  }

  if (hadEndpointFailure) {
    return Promise.all(originals.map((text) => translateRawText(text, target, source)));
  }
  return originals;
}

async function translateObjectDeep(node, target, source = 'en') {
  if (Array.isArray(node)) {
    return Promise.all(node.map((item) => translateObjectDeep(item, target, source)));
  }
  if (node && typeof node === 'object') {
    const entries = await Promise.all(
      Object.entries(node).map(async ([k, v]) => [k, await translateObjectDeep(v, target, source)])
    );
    return Object.fromEntries(entries);
  }
  if (typeof node === 'string') {
    return translateRawText(node, target, source);
  }
  return node;
}

function flattenPackStrings(node, path = [], out = []) {
  if (Array.isArray(node)) {
    node.forEach((item, index) => flattenPackStrings(item, [...path, index], out));
    return out;
  }
  if (node && typeof node === 'object') {
    Object.entries(node).forEach(([key, value]) => flattenPackStrings(value, [...path, key], out));
    return out;
  }
  if (typeof node === 'string') {
    out.push({ path: path.join('.'), value: node });
  }
  return out;
}

function clonePackWithTranslations(node, translationMap, path = []) {
  if (Array.isArray(node)) {
    return node.map((item, index) => clonePackWithTranslations(item, translationMap, [...path, index]));
  }
  if (node && typeof node === 'object') {
    return Object.fromEntries(
      Object.entries(node).map(([key, value]) => [key, clonePackWithTranslations(value, translationMap, [...path, key])])
    );
  }
  if (typeof node === 'string') {
    return translationMap.get(path.join('.')) || node;
  }
  return node;
}

function stableSerializePackNode(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerializePackNode(item)).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableSerializePackNode(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function hashString(value) {
  let hash = 2166136261;
  const input = String(value || '');
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function getPackCacheKey(code = getCurrentLanguage()) {
  const baseLanguage = getBaseLanguage(code);
  const basePack = PACKS[baseLanguage] || PACKS.en;
  return `${baseLanguage}:${code}:${hashString(stableSerializePackNode(basePack))}`;
}

function getCachedRuntimePack(code = getCurrentLanguage()) {
  const cacheKey = getPackCacheKey(code);
  const cached = runtimePackCache[cacheKey];
  if (cached && typeof cached === 'object') return cached;
  return null;
}

export async function ensureLanguagePack(code = getCurrentLanguage()) {
  if (!shouldUseRuntimeTranslation(code)) return getPack(code);
  if (runtimeTranslationDisabled) return PACKS.en;
  const cacheKey = getPackCacheKey(code);
  const cached = getCachedRuntimePack(code);
  if (cached) return cached;
  if (pendingPackLoads.has(cacheKey)) return pendingPackLoads.get(cacheKey);

  const task = (async () => {
    const baseLanguage = getBaseLanguage(code);
    const basePack = PACKS[baseLanguage] || PACKS.en;
    const flattened = flattenPackStrings(basePack);
    const uniqueTexts = Array.from(new Set(flattened.map((entry) => entry.value)));
    const translatedStrings = await translateRawTextBatch(uniqueTexts, code, baseLanguage);
    const bySourceText = new Map();
    uniqueTexts.forEach((text, index) => {
      bySourceText.set(text, translatedStrings[index] || text);
    });
    const translationMap = new Map();
    flattened.forEach((entry) => {
      translationMap.set(entry.path, bySourceText.get(entry.value) || entry.value);
    });
    const translated = clonePackWithTranslations(basePack, translationMap);
    if (runtimeTranslationDisabled) return basePack;
    Object.keys(runtimePackCache).forEach((key) => {
      if (key.startsWith(`${baseLanguage}:${code}:`) && key !== cacheKey) {
        delete runtimePackCache[key];
      }
    });
    delete runtimePackCache[code];
    runtimePackCache[cacheKey] = translated;
    persistTranslationCaches();
    scheduleLanguageRefresh(code, 0);
    return translated;
  })();

  pendingPackLoads.set(cacheKey, task);
  try {
    return await task;
  } finally {
    pendingPackLoads.delete(cacheKey);
  }
}

export function getCurrentLanguage() {
  const saved = localStorage.getItem('skemi_language') || 'en';
  return LANGUAGE_CODES.includes(saved) ? saved : 'en';
}

export function getBaseLanguage(code = getCurrentLanguage()) {
  return code === 'vi' ? 'vi' : 'en';
}

export function getPack(code = getCurrentLanguage()) {
  if (code === 'vi') return PACKS.vi;
  if (code === 'en') return PACKS.en;
  if (runtimeTranslationDisabled) return PACKS.en;
  const cached = getCachedRuntimePack(code);
  if (cached) return cached;
  ensureLanguagePack(code).catch(() => {});
  return PACKS.en;
}

export function t(path, params = {}, code = getCurrentLanguage()) {
  const pack = getPack(code);
  const value = path.split('.').reduce((acc, part) => acc?.[part], pack) ?? path;
  if (typeof value !== 'string') return value;
  return value.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? ''));
}

export function normalizeTheme(theme) {
  const raw = String(theme || '').trim().toLowerCase();
  if (THEME_ORDER.includes(raw)) return raw;
  if (raw === 'pink' || raw === 'purple' || raw === 'space' || raw === 'cosmic') return 'galaxy';
  if (raw === 'black' || raw === 'night') return 'dark';
  if (raw === 'white') return 'light';
  return DEFAULT_USER_DATA.theme;
}

export function getCurrentTheme() {
  return normalizeTheme(localStorage.getItem('skemi-theme') || localStorage.getItem('chat-theme') || DEFAULT_USER_DATA.theme);
}

export function applyThemeToDocument(theme = getCurrentTheme(), root = document.body) {
  if (!root) return;
  const normalizedTheme = normalizeTheme(theme);
  root.setAttribute('data-theme', normalizedTheme);
  document.documentElement.setAttribute('data-theme', normalizedTheme);
}

export function setLocalTheme(theme) {
  const normalizedTheme = normalizeTheme(theme);
  localStorage.setItem('skemi-theme', normalizedTheme);
  localStorage.setItem('chat-theme', normalizedTheme);
  const localProfile = safeParse(localStorage.getItem('skemi_user_data'), null);
  if (localProfile && typeof localProfile === 'object') {
    localProfile.theme = normalizedTheme;
    localStorage.setItem('skemi_user_data', JSON.stringify(localProfile));
  }
  applyThemeToDocument(normalizedTheme);
  window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: normalizedTheme } }));
}

export function setLocalLanguage(language) {
  const next = LANGUAGE_CODES.includes(language) ? language : 'en';
  localStorage.setItem('skemi_language', next);
  document.documentElement.lang = next;
  const cached = getCachedRuntimePack(next);
  emitLanguageChanged(next, !shouldUseRuntimeTranslation(next) || !!cached);
  if (!runtimeTranslationDisabled && shouldUseRuntimeTranslation(next) && !cached) {
    ensureLanguagePack(next).catch(() => {});
  }
}

export function localizeText(viText, enText, code = getCurrentLanguage()) {
  if (code === 'vi') return viText;
  if (code === 'en') return enText;
  const key = `en:${code}:${enText}`;
  if (runtimeTextCache[key]) return runtimeTextCache[key];
  if (runtimeTranslationDisabled) return enText;
  translateRawText(enText, code, 'en').then((translated) => {
    if (getCurrentLanguage() === code) {
      if (!translated || translated === enText) return;
      scheduleLanguageRefresh(code, 160);
    }
  }).catch(() => {});
  return enText;
}

export function loadLocalUserData() {
  return safeParse(localStorage.getItem('skemi_user_data'), { ...DEFAULT_USER_DATA });
}

export function loadAppSettings() {
  const profile = loadLocalUserData();
  return withCompatibilitySettings(profile.settings || {});
}

export function saveAppSettings(patch = {}) {
  const current = loadLocalUserData();
  const mergedSettings = withCompatibilitySettings({
    ...(current.settings || {}),
    ...patch
  });
  saveLocalUserData({ settings: mergedSettings });
  return mergedSettings;
}

export function applyPreferenceClasses(root = document.body, settings = loadAppSettings()) {
  if (!root) return settings;
  root.classList.toggle('compact-mode', !!settings.compact_mode);
  root.classList.toggle('reduce-motion', settings.animations_enabled === false);
  return settings;
}

export function ensureLocalPreferencesDefaults() {
  let changed = false;
  const storedTheme = localStorage.getItem('skemi-theme') || localStorage.getItem('chat-theme');
  const storedLanguage = localStorage.getItem('skemi_language');
  const storedProfile = safeParse(localStorage.getItem('skemi_user_data'), null);

  if (!storedTheme) {
    localStorage.setItem('skemi-theme', DEFAULT_USER_DATA.theme);
    localStorage.setItem('chat-theme', DEFAULT_USER_DATA.theme);
    changed = true;
  }

  if (!storedLanguage || !LANGUAGE_CODES.includes(storedLanguage)) {
    localStorage.setItem('skemi_language', DEFAULT_USER_DATA.language);
    changed = true;
  }

  if (!storedProfile) {
    localStorage.setItem('skemi_user_data', JSON.stringify(DEFAULT_USER_DATA));
    changed = true;
  } else {
    const normalizedProfile = {
      ...storedProfile,
      settings: withCompatibilitySettings(storedProfile.settings || {})
    };
    localStorage.setItem('skemi_user_data', JSON.stringify(normalizedProfile));
  }

  document.documentElement.lang = getCurrentLanguage();
  return changed;
}

export function resetGuestPreferences() {
  // Preserve the Skemi-wide language/theme the user already chose — only fall back
  // to defaults when nothing valid is stored. Without this, a guest visiting Chat
  // had the whole app's language/theme hard-reset to skemma's defaults.
  const existingLang = String(localStorage.getItem('skemi_language') || '').trim().toLowerCase();
  const existingTheme = String(localStorage.getItem('skemi-theme') || localStorage.getItem('chat-theme') || '').trim().toLowerCase();
  const lang = LANGUAGE_CODES.includes(existingLang) ? existingLang : DEFAULT_USER_DATA.language;
  const theme = THEME_ORDER.includes(existingTheme) ? existingTheme : DEFAULT_USER_DATA.theme;
  const profile = { ...DEFAULT_USER_DATA, language: lang, theme };
  localStorage.setItem('skemi_user_data', JSON.stringify(profile));
  setLocalTheme(theme);
  setLocalLanguage(lang);
  return profile;
}

export function saveLocalUserData(patch = {}) {
  const current = loadLocalUserData();
  const nextSettings = patch.settings !== undefined
    ? withCompatibilitySettings({
        ...(current.settings || {}),
        ...(patch.settings || {})
      })
    : withCompatibilitySettings(current.settings || {});
  const next = {
    ...current,
    ...patch,
    linked_apps: {
      ...DEFAULT_USER_DATA.linked_apps,
      ...(current.linked_apps || {}),
      ...(patch.linked_apps || {})
    },
    settings: nextSettings
  };
  localStorage.setItem('skemi_user_data', JSON.stringify(next));
  return next;
}

export function normalizeUserProfile(data = {}, user = null) {
  const localData = loadLocalUserData();
  const mergedSettings = withCompatibilitySettings({
    ...DEFAULT_USER_DATA.settings,
    ...(localData.settings || {}),
    ...(data.settings || {})
  });
  return {
    email: data.email || user?.email || localData.email || '',
    username: data.username || user?.displayName || localData.username || user?.email?.split('@')[0] || 'User',
    age_group: data.age_group || localData.age_group || DEFAULT_USER_DATA.age_group,
    age_range: data.age_range || localData.age_range || DEFAULT_USER_DATA.age_range,
    subscription: data.subscription || localData.subscription || DEFAULT_USER_DATA.subscription,
    prompts_remaining: Number.isFinite(data.prompts_remaining) ? data.prompts_remaining : (Number.isFinite(localData.prompts_remaining) ? localData.prompts_remaining : DEFAULT_USER_DATA.prompts_remaining),
    uploads_remaining: Number.isFinite(data.uploads_remaining) ? data.uploads_remaining : (Number.isFinite(localData.uploads_remaining) ? localData.uploads_remaining : DEFAULT_USER_DATA.uploads_remaining),
    quiz_rooms_remaining: Number.isFinite(data.quiz_rooms_remaining) ? data.quiz_rooms_remaining : (Number.isFinite(localData.quiz_rooms_remaining) ? localData.quiz_rooms_remaining : DEFAULT_USER_DATA.quiz_rooms_remaining),
    last_prompt_reset: data.last_prompt_reset || localData.last_prompt_reset || DEFAULT_USER_DATA.last_prompt_reset,
    email_verified: user?.emailVerified ?? data.email_verified ?? localData.email_verified ?? DEFAULT_USER_DATA.email_verified,
    provider: data.provider || localData.provider || user?.providerData?.[0]?.providerId || DEFAULT_USER_DATA.provider,
    theme: normalizeTheme(data.theme || localData.theme || getCurrentTheme()),
    language: data.language || localData.language || getCurrentLanguage(),
    linked_apps: {
      ...DEFAULT_USER_DATA.linked_apps,
      ...(localData.linked_apps || {}),
      ...(data.linked_apps || {})
    },
    settings: mergedSettings,
    createdAt: data.createdAt || new Date()
  };
}

export async function ensureUserProfile(user, overrides = {}) {
  if (!user) return null;
  const ref = doc(db, 'users', user.uid);
  const snap = await getDoc(ref);
  const merged = normalizeUserProfile({ ...(snap.exists() ? snap.data() : {}), ...overrides }, user);
  await setDoc(ref, merged, { merge: true });
  saveLocalUserData(merged);
  setLocalTheme(merged.theme);
  setLocalLanguage(merged.language);
  return merged;
}

export async function loadRemoteUserProfile(user) {
  if (!user) return null;
  const ref = doc(db, 'users', user.uid);
  const snap = await getDoc(ref);
  if (!snap.exists()) {
    return ensureUserProfile(user);
  }
  const merged = normalizeUserProfile(snap.data(), user);
  saveLocalUserData(merged);
  setLocalTheme(merged.theme);
  setLocalLanguage(merged.language);
  return merged;
}

export async function saveRemoteSettings(user, patch = {}) {
  if (!user) return null;
  const current = await loadRemoteUserProfile(user);
  const merged = normalizeUserProfile({ ...current, ...patch }, user);
  if (patch.settings) {
    merged.settings = {
      ...DEFAULT_USER_DATA.settings,
      ...(current?.settings || {}),
      ...patch.settings
    };
  }
  if (patch.linked_apps) {
    merged.linked_apps = {
      ...DEFAULT_USER_DATA.linked_apps,
      ...(current?.linked_apps || {}),
      ...patch.linked_apps
    };
  }
  await setDoc(doc(db, 'users', user.uid), merged, { merge: true });
  saveLocalUserData(merged);
  if (patch.theme || merged.theme) setLocalTheme(patch.theme || merged.theme);
  if (patch.language || merged.language) setLocalLanguage(patch.language || merged.language);
  return merged;
}

export function getSkemiHomeUrl() {
  const stored = localStorage.getItem('skemi_home_url');
  if (stored) return stored;

  const runtimeHome = globalThis?.__SKEMMA_HOME_URL__;
  if (runtimeHome) return runtimeHome;

  if (typeof window !== 'undefined' && window.location) {
    return new URL('./Home.html', window.location.href).href;
  }

  return './Home.html';
}

export function getChatSettingsSummary() {
  const profile = loadLocalUserData();
  return {
    theme: getCurrentTheme(),
    language: getCurrentLanguage(),
    age_group: profile.age_group || DEFAULT_USER_DATA.age_group,
    subscription: profile.subscription || DEFAULT_USER_DATA.subscription
  };
}

export { auth, db };
