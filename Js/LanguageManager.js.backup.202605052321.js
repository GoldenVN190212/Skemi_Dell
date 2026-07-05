/**
 * LanguageManager v2 — Skemi
 * Unicode Escaped Version
 */

// Import additional language packs (loaded via script tag before this module)
const EXT_PACKS = (typeof window !== 'undefined' && window.I18N_PACKS) ? window.I18N_PACKS : {};

const LANGUAGE_CODES = ['vi','en','zh','ja','ko','es','fr','de','it','pt','ru','ar','hi','th','id','ms','tr','pl','nl','sv','no','da','fi','cs','sk','hu','ro','bg','hr','sr','sl','et','lv','lt','uk','el','he','fa','ur','bn','ta','te','ml','kn','gu','pa','mr','ne','si','my','km','lo','tl','sw','zu','af','xh','st','tn','sn','ny','mg','rw','so','am','ti','om','ha','yo','ig','ee','ak','bm','wo','ff','ln','ts','ve','nr','ca','eu','gl','is','ga','cy','mt','sq','mk','bs','be','kk','uz','az','ka','hy','mn','ps','sd','ckb','ug','ky','tg','tk'];

// 52+ Full UI Packs - Real-time translation without API calls
const FULL_UI_PACKS = new Set([
  'vi', 'en',                        // Existing
  'zh', 'ja', 'ko',                  // East Asian
  'es', 'fr', 'de', 'it', 'pt',      // European major
  'ru', 'pl', 'nl', 'sv', 'no', 'da', 'fi', 'cs',           // European
  'uk', 'el', 'ro', 'hu', 'bg', 'hr', 'sr', 'sk', 'sl',     // Eastern European
  'et', 'lv', 'lt',                                         // Baltic
  'tr', 'ar', 'he', 'fa', 'ur',                             // Middle East
  'hi', 'bn', 'ta', 'te', 'ml', 'kn', 'gu', 'pa', 'mr', 'ne', 'si', // Indian/South Asian
  'th', 'id', 'ms', 'my', 'km', 'lo', 'tl',                 // Southeast Asian
  'sw', 'zu', 'af', 'xh', 'st', 'tn', 'sn', 'ny', 'mg', 'rw', 'so', 'am', 'ti', 'om', 'ha', 'yo', 'ig', // African
  'ee', 'ak', 'bm', 'wo', 'ff', 'ln', 'ts', 've', 'nr',     // African (more)
  'ca', 'eu', 'gl', 'is', 'ga', 'cy', 'mt', 'sq', 'mk', 'bs', 'be', 'kk', 'uz', 'az', 'ka', 'hy', 'mn', // Others
  'ps', 'sd', 'ckb', 'ug', 'ky', 'tg', 'tk'                 // Central Asian
]);
const ICONS = {
  sparkles: '✨',
  quick: '⚡',
  study: '📚',
  research: '🔬',
  work: '💼',
  brain: '🧠',
  builder: '🧩',
  presentation: '🖥️',
  chart: '📊',
  dashboard: '📈',
  palette: '🎨',
  report: '📄',
  flashcard: '🗂️',
  podcast: '🎙️',
  video: '🎬',
  quiztest: '🧪',
  visual: '🖼️',
  notebook: '📓',
  chat: '💬',
  profile: '👤',
  appearance: '🎨',
  security: '🔒',
  subscription: '💳',
  text: '📝',
  upload: '📁',
  robot: '🤖',
  notifications: '🔔'
};

(function(){})('LanguageManager v2.1 Loading...');

const DEFAULT_UI_SETTINGS = {
  compact_mode: false,
  animations_enabled: true
};
const PROTECTED_UI_BRANDS = Object.freeze(['Skemi', 'Skemma']);
const CHAT_BOOT_KEY = 'skemi_chat_bootstrap_ready_v1';
const INTERNAL_NAV_KEY = 'skemi_internal_navigation_v1';
const RUNTIME_UI_PACK_CACHE_KEY = 'skemi_runtime_ui_pack_cache_v1';
const RUNTIME_UI_TEXT_CACHE_KEY = 'skemi_runtime_ui_text_cache_v2';

function readJsonStorage(key, fallback = {}) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || 'null');
    if (parsed && typeof parsed === 'object') return parsed;
  } catch {}
  return fallback;
}

const runtimeUiPackCache = readJsonStorage(RUNTIME_UI_PACK_CACHE_KEY, {});
const runtimeUiTextCache = new Map(
  Object.entries(readJsonStorage(RUNTIME_UI_TEXT_CACHE_KEY, {}))
);

function persistRuntimeUiPackCache() {
  try {
    localStorage.setItem(RUNTIME_UI_PACK_CACHE_KEY, JSON.stringify(runtimeUiPackCache));
  } catch {}
}

function persistRuntimeUiTextCache() {
  try {
    const snapshot = Object.fromEntries(runtimeUiTextCache.entries());
    localStorage.setItem(RUNTIME_UI_TEXT_CACHE_KEY, JSON.stringify(snapshot));
  } catch {}
}

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
const MOJIBAKE_MARKERS = /(?:\u00C3.|\u00C2.|\u00C6.|\u00C4.|\u00E1\u00BA|\u00E1\u00BB|\u00E2\u20AC\u00A6|\u00E2\u20AC\u201C|\u00E2\u20AC\u201D|\u00E2\u20AC|\u00F0\u0178|\u00D0.|\u00D1.)/;

function stripControlChars(value) {
  return String(value).replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');
}

function looksLikeMojibake(value) {
  return typeof value === 'string' && MOJIBAKE_MARKERS.test(value);
}

function cp1252Byte(char) {
  const code = char.charCodeAt(0);
  if (code <= 0xFF) return code;
  return CP1252_BYTE_MAP[char] ?? 0x3F;
}

function mojibakeScore(input) {
  if (typeof input !== 'string') return Number.POSITIVE_INFINITY;
  const text = stripControlChars(input);
  return (text.match(SUSPICIOUS_MOJIBAKE_PAIR) || []).length + (text.match(/\uFFFD/g) || []).length;
}

function decodeMojibakeCandidate(value) {
  return new TextDecoder('utf-8', { fatal: false }).decode(
    Uint8Array.from(Array.from(value, cp1252Byte))
  );
}

function loadUiSettings() {
  try {
    const profile = JSON.parse(localStorage.getItem('skemi_user_data') || '{}');
    return {
      compact_mode: profile?.settings?.compact_mode === true,
      animations_enabled: profile?.settings?.animations_enabled !== false,
      theme: String(localStorage.getItem('skemi-theme') || profile?.settings?.theme || profile?.theme || 'light').trim().toLowerCase(),
      language: String(localStorage.getItem('skemi_language') || profile?.settings?.language || profile?.language || 'vi').trim().toLowerCase()
    };
  } catch {
    return { ...DEFAULT_UI_SETTINGS };
  }
}

function loadSavedProfile() {
  try {
    const profile = JSON.parse(localStorage.getItem('skemi_user_data') || '{}');
    return profile && typeof profile === 'object' ? profile : {};
  } catch {
    return {};
  }
}

function getSavedProfileLanguage() {
  const profile = loadSavedProfile();
  const candidates = [
    profile?.settings?.language,
    profile?.language,
    profile?.preferences?.language
  ].map((value) => String(value || '').trim().toLowerCase()).filter(Boolean);

  return candidates.find((code) => LANGUAGE_CODES.includes(code)) || '';
}

function getSavedTheme() {
  const profile = loadSavedProfile();
  const candidates = [
    localStorage.getItem('skemi-theme'),
    profile?.settings?.theme,
    profile?.theme,
    profile?.preferences?.theme
  ].map((value) => String(value || '').trim().toLowerCase()).filter(Boolean);

  const resolved = candidates.find((theme) => ['light', 'dark', 'galaxy'].includes(theme));
  return resolved || 'light';
}

function persistProfileLanguage(code) {
  if (!LANGUAGE_CODES.includes(code)) return;
  const profile = loadSavedProfile();
  const nextProfile = {
    ...profile,
    language: code,
    settings: {
      ...(profile?.settings || {}),
      language: code
    }
  };
  try {
    localStorage.setItem('skemi_user_data', JSON.stringify(nextProfile));
  } catch {}
}

function applyUiPreferenceClasses() {
  const settings = loadUiSettings();
  if (!document.body) return settings;
  document.body.classList.toggle('compact-mode', !!settings.compact_mode);
  document.body.classList.toggle('reduce-motion', settings.animations_enabled === false);
  return settings;
}

function legacyRepairMojibake(value) {
  if (Array.isArray(value)) {
    return value.map((item) => legacyRepairMojibake(item));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, legacyRepairMojibake(item)])
    );
  }
  if (typeof value !== 'string') return value;
  if (!looksLikeMojibake(value)) {
    return value.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');
  }
  if (!/[\u00C2-\u00C6\u00D0-\u00DF\u00E1\u00E2\u00F0\u0153\u0178]/.test(value)) {
    return value.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');
  }

  let best = value;
  let bestScore = Number.POSITIVE_INFINITY;
  const scoreBadMarkers = (input) => {
    if (typeof input !== 'string') return Number.POSITIVE_INFINITY;
    const markers = ['\u00C3', '\u00C2', '\u00E1\u00BA', '\u00E1\u00BB', '\u00F0\u0178', '\u00E2\u0153', '\u00E2\u20AC', '\uFFFD'];
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
    const score = scoreBadMarkers(candidate);
    if (candidate && score < bestScore) {
      best = candidate;
      bestScore = score;
    }
  });

  return best.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');
}

function repairMojibake(value) {
  if (Array.isArray(value)) {
    return value.map((item) => repairMojibake(item));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, repairMojibake(item)])
    );
  }
  if (typeof value !== 'string') return value;

  const cleanValue = stripControlChars(value);
  if (!looksLikeMojibake(cleanValue)) return cleanValue;
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
    if (cleanedCandidate && score < bestScore) {
      best = cleanedCandidate;
      bestScore = score;
    }
  });

  return best;
}

function repairDomText(root = document.body) {
  if (!root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parentTag = node.parentElement?.tagName;
    if (parentTag === 'SCRIPT' || parentTag === 'STYLE' || parentTag === 'NOSCRIPT') continue;
    nodes.push(node);
  }

  nodes.forEach((node) => {
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

  if (document.title) {
    const fixedTitle = repairMojibake(document.title);
    if (fixedTitle !== document.title) {
      document.title = fixedTitle;
    }
  }
  document.querySelectorAll('meta[name="description"], meta[property="og:title"], meta[property="og:description"]').forEach((meta) => {
    const currentContent = meta.getAttribute('content');
    const fixedContent = repairMojibake(currentContent);
    if (fixedContent && fixedContent !== currentContent) meta.setAttribute('content', fixedContent);
  });
}

function startMojibakeObserver() {
  if (!document.body || document.body.dataset.languageObserverReady === '1') return;
  document.body.dataset.languageObserverReady = '1';
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
    attributeFilter: ['placeholder', 'title', 'aria-label', 'content']
  });
}

function protectUiBrandNames(text) {
  let next = String(text || '');
  const placeholders = [];
  PROTECTED_UI_BRANDS.forEach((brand, index) => {
    const token = `__UI_BRAND_${index}__`;
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

async function translateUiText(text, target, source = 'en') {
  const trimmed = String(text || '').trim();
  if (!trimmed || FULL_UI_PACKS.has(target)) return trimmed;
  const cacheKey = `${source}:${target}:${trimmed}`;
  if (runtimeUiTextCache.has(cacheKey)) return runtimeUiTextCache.get(cacheKey);
  const protectedPayload = protectUiBrandNames(trimmed);

  try {
    const response = await fetch('/api/translate-ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: protectedPayload.text, source, target, format: 'text' })
    });
    if (!response.ok) return trimmed;
    const data = await response.json();
    const translated = restoreUiBrandNames(String(data?.translatedText || '').trim() || trimmed, protectedPayload.placeholders);
    runtimeUiTextCache.set(cacheKey, translated);
    persistRuntimeUiTextCache();
    return translated;
  } catch {
    return trimmed;
  }
}

async function translateUiBatch(texts, target, source = 'auto') {
  const cleaned = Array.from(new Set((texts || []).map((item) => String(item || '').trim()).filter(Boolean)));
  if (!cleaned.length || FULL_UI_PACKS.has(target)) return cleaned;
  const resolved = new Map();
  const misses = [];
  cleaned.forEach((item) => {
    const cacheKey = `${source}:${target}:${item}`;
    if (runtimeUiTextCache.has(cacheKey)) {
      resolved.set(item, runtimeUiTextCache.get(cacheKey));
    } else {
      misses.push(item);
    }
  });
  if (!misses.length) {
    return cleaned.map((item) => resolved.get(item) || item);
  }

  const protectedBatch = misses.map((item) => protectUiBrandNames(item));

  try {
    const response = await fetch('/api/translate-ui-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: protectedBatch.map((item) => item.text), source, target })
    });
    if (!response.ok) return cleaned.map((item) => resolved.get(item) || item);
    const data = await response.json();
    const translations = Array.isArray(data?.translations) ? data.translations : protectedBatch.map((item) => item.text);
    protectedBatch.forEach((item, index) => {
      const original = misses[index];
      const translated = String(translations[index] || item.text || original).trim() || original;
      const restored = restoreUiBrandNames(translated, item.placeholders || []);
      runtimeUiTextCache.set(`${source}:${target}:${original}`, restored);
      resolved.set(original, restored);
    });
    persistRuntimeUiTextCache();
    return cleaned.map((item) => resolved.get(item) || item);
  } catch {
    return cleaned.map((item) => resolved.get(item) || item);
  }
}

const PACKS = {
  vi: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - không gian AI, trình dựng và sổ tay theo từng project.' },
    nav: { studio: 'Studio', dashboard: 'Studio', search: 'Tra cứu', quiz: 'Quiz', chat: 'Chat', settings: 'Cài đặt', version: 'Skemi v1.0', notifications: 'Thông báo' },
    common: { themeToggle: 'Chuyển giao diện sáng hoặc tối', sidebarCollapse: 'Thu gọn menu', save: 'Lưu', close: 'Đóng', send: 'Gửi', use: 'Dùng', active: 'Đang dùng', delete: 'Xóa', loading: 'Đang tải...' },
    auth: { signup: 'Đăng ký', login: 'Đăng nhập', logout: 'Đăng xuất', profileMenu: 'Chuột phải để đăng xuất', guest: 'Khách', sync: 'Đăng nhập để đồng bộ nội dung.' },
    settings: {
      tabs: ['Hồ sơ', 'Thống kê & Thông số', 'Giao diện & Ngôn ngữ', 'Thông báo', 'Bảo mật', 'Gói dịch vụ'],
      statistics: {
        title: 'Tổng quan thông số',
        help: 'Theo dõi hiệu suất học tập và các hoạt động AI của bạn.',
        cards: {
          totalMessages: 'Tổng tương tác AI',
          prompts: 'Prompts khả dụng',
          uploads: 'Lượt upload file',
          quizWins: 'Top 3 Quiz'
        },
        charts: {
          activityTitle: '📈 Hoạt động 7 ngày qua',
          topicTitle: '⚖️ Trọng tâm chủ đề',
          timeTitle: '⏳ Thời gian tương tác'
        },
        datasets: {
          activity: 'Lượt tương tác',
          interest: 'Sự quan tâm',
          time: 'Hoạt động'
        },
        labels: {
          weekdays: ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'],
          topics: ['Toán học', 'Lập trình', 'Ngoại ngữ', 'Khoa học', 'Lịch sử', 'Kinh tế'],
          hours: ['0h', '4h', '8h', '12h', '16h', '20h']
        }
      },
      accountTitle: 'Thông tin tài khoản',
      accountHelp: 'Quản lý thông tin cá nhân và cài đặt định danh của bạn.',
      ageTag: 'Nhóm tuổi của bạn',
      ageRange: 'Nhóm tuổi cụ thể',
      ageRangePlaceholder: 'Ví dụ: 18-35',
      appearanceTitle: 'Giao diện',
      appearanceHelp: 'Chọn một giao diện duy nhất để tránh lỗi hiển thị sáng/tối không đồng bộ.',
      themes: ['Sáng', 'Tối', 'Galaxy'],
      languageTitle: 'Ngôn ngữ',
      languageHelp: 'Hỗ trợ hơn 100 ngôn ngữ. Tên thương hiệu Skemi được giữ nguyên trên toàn bộ ứng dụng.',
      securityTitle: 'Bảo mật & Quyền riêng tư',
      verifyLabel: 'Trạng thái xác thực',
      verifyChecking: 'Đang kiểm tra...',
      warnings: {
        1: { title: 'Thông báo bảo mật', desc: 'Nhận cảnh báo khi có đăng nhập từ thiết bị lạ.' }
      },
      dangerTitle: 'Vùng nguy hiểm',
      dangerDesc: 'Xóa toàn bộ dữ liệu cục bộ trên trình duyệt này.',
      clearLocal: 'Xóa dữ liệu cục bộ',
      subscriptionTitle: 'Gói dịch vụ',
      subscriptionHelp: 'Nâng cấp để mở rộng giới hạn sử dụng AI.',
      currentPlan: 'Gói hiện tại',
      pro: 'Nâng cấp Pro',
      profileSaved: 'Đã lưu thông tin tài khoản.',
      localCleared: 'Đã xóa dữ liệu trình duyệt.',
      verified: 'Đã xác thực email.',
      unverified: 'Chưa xác thực email. Vui lòng kiểm tra hộp thư.',
      notLoggedIn: 'Chưa đăng nhập.',
      saveBarText: 'Bạn có thay đổi chưa lưu.',
      saveChanges: 'Lưu thay đổi',
      discardChanges: 'Hủy'
    },
    home: { title: 'Skemi Studio', project: { kicker: 'Workspace theo project', desc: 'Hãy tạo dự án trước khi bắt đầu để toàn bộ dữ liệu AI Workspace, Builder và Source Notebook được quản lý tập trung.', current: 'Project hiện tại', placeholder: 'Ví dụ: Ôn thi giữa kỳ Toán 12', create: 'Tạo project', save: 'Lưu project', required: '<strong>Bạn chưa chọn project.</strong> Hãy tạo project mới hoặc chọn project có sẵn để bắt đầu.' } },
    notebook: { welcome: 'Chào mừng đế với Skemi Studio. Hãy đặt câu hỏi về tài liệu của bạn.' },
    aichat: {
      placeholder: 'Nhập yêu cầu của bạn...',
      close: 'Đóng',
      send: 'Gửi',
      emptyTitle: 'Chưa có tin nhắn',
      emptyDesc: 'Hãy bắt đầu cuộc trò chuyện với AI.'
    },
    age: { young: 'Học sinh', middle: 'Người lao động', senior: 'Người lớn tuổi' },
    status: { ready: 'Đang sẵn sàng' }
  },
  en: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - AI workspace, builder, and notebook by project.' },
    nav: { studio: 'Studio', dashboard: 'Studio', search: 'Search', quiz: 'Quiz', chat: 'Chat', settings: 'Settings', version: 'Skemi v1.0', notifications: 'Notifications' },
    common: { themeToggle: 'Switch theme', sidebarCollapse: 'Collapse menu', save: 'Save', close: 'Close', send: 'Send', use: 'Use', active: 'Active', delete: 'Delete', loading: 'Loading...' },
    auth: { signup: 'Sign up', login: 'Log in', logout: 'Log out', profileMenu: 'Right click to log out', guest: 'Guest', sync: 'Log in to sync your data.' },
    settings: {
      tabs: ['Profile', 'Statistics & Metrics', 'Appearance & Language', 'Notifications', 'Security', 'Subscription'],
      statistics: {
        title: 'Statistics Overview',
        help: 'Track your learning momentum and AI activity across the week.',
        cards: {
          totalMessages: 'Total AI interactions',
          prompts: 'Available prompts',
          uploads: 'File uploads',
          quizWins: 'Top 3 Quiz finishes'
        },
        charts: {
          activityTitle: '📈 Activity over the last 7 days',
          topicTitle: '⚖️ Topic focus',
          timeTitle: '⏳ Time spent engaging'
        },
        datasets: {
          activity: 'Interactions',
          interest: 'Interest level',
          time: 'Activity'
        },
        labels: {
          weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
          topics: ['Mathematics', 'Programming', 'Languages', 'Science', 'History', 'Economics'],
          hours: ['0h', '4h', '8h', '12h', '16h', '20h']
        }
      },
      accountTitle: 'Account Information',
      accountHelp: 'Manage your personal details and identity settings.',
      ageTag: 'Your age group',
      ageRange: 'Specific age range',
      ageRangePlaceholder: 'Example: 18-35',
      appearanceTitle: 'Appearance',
      appearanceHelp: 'Choose a theme to ensure consistent lighting across the app.',
      themes: ['Light', 'Dark', 'Galaxy'],
      languageTitle: 'Language',
      languageHelp: 'Supports over 100 languages. Skemi remains the product name across the app.',
      securityTitle: 'Security & Privacy',
      verifyLabel: 'Verification Status',
      verifyChecking: 'Checking...',
      warnings: {
        1: { title: 'Security Alerts', desc: 'Get notified of logins from unknown devices.' }
      },
      dangerTitle: 'Danger Zone',
      dangerDesc: 'Clear all local data stored on this browser.',
      clearLocal: 'Clear Local Data',
      subscriptionTitle: 'Subscription Plan',
      subscriptionHelp: 'Upgrade to expand your AI usage limits.',
      currentPlan: 'Current Plan',
      pro: 'Upgrade to Pro',
      profileSaved: 'Profile settings saved.',
      localCleared: 'Local data cleared.',
      verified: 'Email verified.',
      unverified: 'Email not verified. Please check your inbox.',
      notLoggedIn: 'Not logged in.',
      saveBarText: 'You have unsaved changes.',
      saveChanges: 'Save Changes',
      discardChanges: 'Discard'
    },
    home: { project: { kicker: 'Project workspace', desc: 'Start with a project to keep AI Workspace, Builder, and Source Notebook organized in one place.' } },
    notebook: { welcome: 'Welcome to Skemi Studio. Ask questions about your documents.' },
    aichat: {
      placeholder: 'Enter your request...',
      close: 'Close',
      send: 'Send',
      emptyTitle: 'No messages yet',
      emptyDesc: 'Start a conversation with AI.'
    },
    age: { young: 'Student', middle: 'Professional', senior: 'Senior' },
    status: { ready: 'Ready' }
  }
};

const CLEAN_PACKS = {
  vi: {
    meta: {
      homeTitle: 'Skemi Studio',
      homeDesc: 'Skemi Studio - không gian AI, dựng nội dung và sổ tay theo từng dự án.',
      settingsTitle: 'Cài đặt - Skemi'
    },
    nav: {
      studio: 'Studio',
      dashboard: 'Studio',
      search: 'Tra cứu',
      quiz: 'Quiz',
      chat: 'Chat',
      settings: 'Cài đặt',
      version: 'Skemi v1.0',
      notifications: 'Thông báo'
    },
    common: {
      themeToggle: 'Chuyển giao diện',
      sidebarCollapse: 'Thu gọn thanh bên',
      save: 'Lưu',
      close: 'Đóng',
      send: 'Gửi',
      use: 'Dùng',
      active: 'Đang dùng',
      delete: 'Xóa',
      loading: 'Đang tải...'
    },
    auth: {
      signup: 'Đăng ký',
      login: 'Đăng nhập',
      logout: 'Đăng xuất',
      profileMenu: 'Nhấn chuột phải để đăng xuất',
      guest: 'Khách',
      sync: 'Đăng nhập để đồng bộ dữ liệu.'
    },
    settings: {
      tabs: ['Hồ sơ', 'Thống kê & Chỉ số', 'Giao diện & Ngôn ngữ', 'Thông báo', 'Bảo mật', 'Gói dịch vụ'],
      accountTitle: 'Thông tin tài khoản',
      accountHelp: 'Quản lý hồ sơ cá nhân, độ tuổi và trạng thái đồng bộ của tài khoản Skemi.',
      defaultUser: 'Người dùng Skemi',
      ageTag: 'Nhóm tuổi của bạn',
      ageRange: 'Khoảng tuổi cụ thể',
      ageRangePlaceholder: 'Ví dụ: 18-35',
      appearanceTitle: 'Giao diện',
      appearanceHelp: 'Chọn một giao diện thống nhất để toàn bộ ứng dụng hiển thị ổn định và dễ nhìn.',
      themes: ['Sáng', 'Tối', 'Galaxy'],
      languageTitle: 'Ngôn ngữ',
      languageHelp: 'Skemi ưu tiên ngôn ngữ bạn chọn trên toàn bộ ứng dụng. Tên thương hiệu Skemi được giữ nguyên.',
      statistics: {
        title: 'Tổng quan hoạt động',
        help: 'Các chỉ số này được tính từ dữ liệu người dùng đang lưu trên thiết bị hiện tại, không dùng quota hay số liệu giả.',
        cards: {
          projects: 'Dự án đã tạo',
          aiInteractions: 'Tương tác AI',
          savedSources: 'Nguồn đã lưu',
          activeDays: 'Ngày hoạt động (7 ngày)'
        },
        charts: {
          activityTitle: 'Hoạt động 7 ngày gần đây',
          focusTitle: 'Trọng tâm sử dụng',
          timeTitle: 'Khung giờ hoạt động'
        },
        datasets: {
          activity: 'Lượt hoạt động',
          focus: 'Mức sử dụng',
          time: 'Tần suất'
        },
        labels: {
          focus: ['Dự án', 'Nguồn', 'Tra cứu', 'Chat AI', 'Quiz riêng', 'Kết quả tạo'],
          hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00']
        }
      },
      notifications: {
        title: 'Thông báo & Tính năng',
        help: 'Bật hoặc tắt các thông báo và tùy chọn giao diện cơ bản của ứng dụng.',
        desktop: {
          title: 'Thông báo trên trình duyệt',
          desc: 'Hiện thông báo desktop khi có tin nhắn chat mới hoặc lời mời quiz.'
        },
        sound: {
          title: 'Âm thanh thông báo',
          desc: 'Phát âm báo khi có tin nhắn và lời mời mới.'
        },
        email: {
          title: 'Email thông báo',
          desc: 'Nhận email tổng hợp về các hoạt động quan trọng.'
        },
        startup: {
          title: 'Gợi ý khi mở trang',
          desc: 'Hiện hướng dẫn nhanh khi vào chat lần đầu trong ngày.'
        },
        compact: {
          title: 'Chế độ giao diện gọn',
          desc: 'Tối giản hóa giao diện cho màn hình nhỏ.'
        },
        animations: {
          title: 'Hoạt ảnh giao diện',
          desc: 'Bật hoặc tắt hiệu ứng chuyển cảnh và hoạt ảnh. Tắt để tăng tốc độ.'
        },
        aiTitle: 'Hoạt động AI',
        aiHelp: 'Tùy chỉnh cách AI của Skemi hoạt động khi bạn dùng chatbot và tạo học liệu.',
        ephemeral: {
          title: 'Lưu hội thoại AI tạm thời',
          desc: 'Lưu hội thoại AI theo phiên truy cập hiện tại để bạn tiếp tục nhanh hơn.'
        },
        personalize: {
          title: 'Cá nhân hóa phản hồi AI',
          desc: 'Cho phép AI dùng thông tin độ tuổi và dữ liệu học tập để tinh chỉnh phản hồi.'
        },
        usage: {
          title: 'Cảnh báo giới hạn sử dụng',
          desc: 'Thông báo khi các hoạt động AI trong phiên của bạn tiến gần ngưỡng sử dụng.'
        }
      },
      securityTitle: 'Đăng nhập & Bảo mật',
      verifyLabel: 'Trạng thái xác thực email',
      verifyChecking: 'Đang kiểm tra...',
      warnings: {
        1: {
          title: 'Cảnh báo bảo mật',
          desc: 'Nhận cảnh báo khi có đăng nhập từ thiết bị lạ.'
        }
      },
      dangerTitle: 'Vùng nguy hiểm',
      dangerDesc: 'Xóa toàn bộ dữ liệu cục bộ trên trình duyệt này nhưng giữ lại giao diện và ngôn ngữ đã chọn.',
      clearLocal: 'Xóa dữ liệu cục bộ',
      subscriptionTitle: 'Gói dịch vụ',
      subscriptionHelp: 'Nâng cấp để mở rộng mức sử dụng AI, khả năng lưu trữ và quyền truy cập tính năng.',
      currentPlan: 'Gói hiện tại',
      pro: 'Nâng cấp Pro',
      plans: {
        free: {
          name: 'Free',
          price: '0đ',
          period: '/tháng',
          features: [
            'Số lượt AI cơ bản theo chu kỳ',
            'Studio, Search và Quiz tiêu chuẩn',
            'Đồng bộ tài khoản mặc định',
            'Không gian làm việc cá nhân'
          ],
          button: 'Gói hiện tại'
        },
        pro: {
          name: 'Pro',
          price: '79.000đ',
          period: '/tháng',
          features: [
            'Nhiều lượt AI hơn cho học tập và làm việc',
            'Ưu tiên xử lý nhanh hơn',
            'Lưu trữ quiz riêng và lịch sử dài hơn',
            'Đồng bộ nâng cao giữa các trang'
          ],
          button: 'Nâng cấp Pro'
        },
        advanced: {
          name: 'Advanced',
          price: '189.000đ',
          period: '/tháng',
          features: [
            'Mức sử dụng AI và lưu trữ cao nhất',
            'Ưu tiên hàng đợi tối đa',
            'Truy cập sớm tính năng mới',
            'Không gian làm việc dài hạn cho nhóm'
          ],
          button: 'Chọn Advanced'
        }
      },
      authGuard: {
        badge: 'Secure Settings Access',
        title: 'Đăng nhập để mở toàn bộ Settings',
        text: 'Khu vực này chỉ dành cho tài khoản đã đăng nhập. Sau khi vào tài khoản, bạn mới có thể chỉnh hồ sơ, giao diện, ngôn ngữ, bảo mật và đồng bộ cài đặt trên toàn hệ thống.',
        points: [
          'Đồng bộ hồ sơ và ngôn ngữ theo tài khoản',
          'Mở khóa toàn bộ tùy chọn giao diện và quyền riêng tư',
          'Giữ trải nghiệm nhất quán giữa các trang trong Skemi'
        ],
        login: 'Đăng nhập',
        register: 'Tạo tài khoản'
      },
      profileSaved: 'Đã lưu thông tin tài khoản.',
      localCleared: 'Đã xóa dữ liệu trình duyệt.',
      verified: 'Email đã được xác thực.',
      unverified: 'Email chưa được xác thực. Vui lòng kiểm tra hộp thư.',
      notLoggedIn: 'Chưa đăng nhập.',
      saveBarText: 'Bạn có thay đổi chưa lưu.',
      saveChanges: 'Lưu thay đổi',
      discardChanges: 'Hủy',
      buttons: {
        saveProfile: 'Lưu thông tin',
        resetProfile: 'Đặt lại'
      }
    },
    home: {
      title: 'Skemi Studio',
      project: {
        kicker: 'Workspace theo dự án',
        desc: 'Hãy tạo một dự án trước khi bắt đầu để quản lý AI Workspace, Builder và Source Notebook tập trung.',
        current: 'Dự án hiện tại',
        placeholder: 'Ví dụ: Ôn thi giữa kỳ Toán 12',
        create: 'Tạo dự án',
        save: 'Lưu dự án',
        required: '<strong>Bạn chưa chọn dự án.</strong> Hãy tạo dự án mới hoặc chọn dự án có sẵn để bắt đầu.'
      }
    },
    notebook: {
      welcome: 'Chào mừng đến với Skemi Studio. Hãy đặt câu hỏi về tài liệu của bạn.'
    },
    aichat: {
      placeholder: 'Nhập yêu cầu của bạn...',
      close: 'Đóng',
      send: 'Gửi',
      emptyTitle: 'Chưa có tin nhắn',
      emptyDesc: 'Hãy bắt đầu cuộc trò chuyện với AI.',
      switchMode: 'Đã chuyển sang {label}',
      apiError: 'Không thể kết nối AI lúc này.',
      connectError: 'Kết nối AI đang tạm gián đoạn. Vui lòng thử lại.',
      thinking: 'AI đang suy nghĩ...'
    },
    age: {
      young: 'Học sinh',
      middle: 'Người đi làm',
      senior: 'Người lớn tuổi'
    },
    status: {
      ready: 'Sẵn sàng'
    }
  },
  en: {
    meta: {
      homeTitle: 'Skemi Studio',
      homeDesc: 'Skemi Studio - an AI workspace, builder, and notebook organized by project.',
      settingsTitle: 'Settings - Skemi'
    },
    nav: {
      studio: 'Studio',
      dashboard: 'Studio',
      search: 'Search',
      quiz: 'Quiz',
      chat: 'Chat',
      settings: 'Settings',
      version: 'Skemi v1.0',
      notifications: 'Notifications'
    },
    common: {
      themeToggle: 'Switch theme',
      sidebarCollapse: 'Collapse sidebar',
      save: 'Save',
      close: 'Close',
      send: 'Send',
      use: 'Use',
      active: 'Active',
      delete: 'Delete',
      loading: 'Loading...'
    },
    auth: {
      signup: 'Sign up',
      login: 'Log in',
      logout: 'Log out',
      profileMenu: 'Right click to log out',
      guest: 'Guest',
      sync: 'Log in to sync your data.'
    },
    settings: {
      tabs: ['Profile', 'Statistics & Metrics', 'Appearance & Language', 'Notifications', 'Security', 'Subscription'],
      accountTitle: 'Account Information',
      accountHelp: 'Manage your personal details, age profile, and account sync status.',
      defaultUser: 'Skemi user',
      ageTag: 'Your age group',
      ageRange: 'Specific age range',
      ageRangePlaceholder: 'Example: 18-35',
      appearanceTitle: 'Appearance',
      appearanceHelp: 'Choose one consistent theme so the whole app stays stable and readable.',
      themes: ['Light', 'Dark', 'Galaxy'],
      languageTitle: 'Language',
      languageHelp: 'Skemi applies your preferred language across the app while keeping Skemi as the product name.',
      statistics: {
        title: 'Activity Overview',
        help: 'These metrics are calculated from real user data stored on this device, not from quotas or placeholder numbers.',
        cards: {
          projects: 'Projects created',
          aiInteractions: 'AI interactions',
          savedSources: 'Saved sources',
          activeDays: 'Active days (7d)'
        },
        charts: {
          activityTitle: 'Activity over the last 7 days',
          focusTitle: 'Usage focus',
          timeTitle: 'Most active hours'
        },
        datasets: {
          activity: 'Activity',
          focus: 'Usage level',
          time: 'Frequency'
        },
        labels: {
          focus: ['Projects', 'Sources', 'Search', 'AI chat', 'Private quiz', 'Generated output'],
          hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00']
        }
      },
      notifications: {
        title: 'Notifications & Features',
        help: 'Turn core notifications and interface behaviors on or off.',
        desktop: {
          title: 'Browser notifications',
          desc: 'Show desktop alerts when new chat messages or quiz invites arrive.'
        },
        sound: {
          title: 'Notification sounds',
          desc: 'Play a sound when a new message or invite appears.'
        },
        email: {
          title: 'Email updates',
          desc: 'Receive summary emails for important activity.'
        },
        startup: {
          title: 'Startup tips',
          desc: 'Show quick guidance when you open chat for the first time in a day.'
        },
        compact: {
          title: 'Compact layout',
          desc: 'Use a denser layout for smaller screens.'
        },
        animations: {
          title: 'Interface animations',
          desc: 'Turn transitions and motion effects on or off. Disable for better speed.'
        },
        aiTitle: 'AI behavior',
        aiHelp: 'Control how Skemi AI behaves when you chat or generate study materials.',
        ephemeral: {
          title: 'Keep temporary AI sessions',
          desc: 'Store AI conversation state for the current browsing session so you can resume faster.'
        },
        personalize: {
          title: 'Personalize AI responses',
          desc: 'Let AI use age profile and study context to refine its responses.'
        },
        usage: {
          title: 'Usage limit alerts',
          desc: 'Notify you when your current AI activity is close to session limits.'
        }
      },
      securityTitle: 'Sign-in & Security',
      verifyLabel: 'Email verification status',
      verifyChecking: 'Checking...',
      warnings: {
        1: {
          title: 'Security alerts',
          desc: 'Get alerted when your account is accessed from an unknown device.'
        }
      },
      dangerTitle: 'Danger zone',
      dangerDesc: 'Clear all local browser data while keeping your selected theme and language.',
      clearLocal: 'Clear local data',
      subscriptionTitle: 'Subscription',
      subscriptionHelp: 'Upgrade to unlock more AI usage, storage, and feature access.',
      currentPlan: 'Current plan',
      pro: 'Upgrade to Pro',
      plans: {
        free: {
          name: 'Free',
          price: '$0',
          period: '/month',
          features: [
            'Core AI usage on a standard cycle',
            'Standard Studio, Search, and Quiz access',
            'Default account sync',
            'Personal workspace'
          ],
          button: 'Current plan'
        },
        pro: {
          name: 'Pro',
          price: '$3.10',
          period: '/month',
          features: [
            'Higher AI usage for study and work',
            'Faster processing priority',
            'Longer history and more private quiz storage',
            'Enhanced sync across pages'
          ],
          button: 'Upgrade to Pro'
        },
        advanced: {
          name: 'Advanced',
          price: '$7.50',
          period: '/month',
          features: [
            'Highest AI and storage capacity',
            'Maximum queue priority',
            'Early access to new features',
            'Long-term workspace support for teams'
          ],
          button: 'Choose Advanced'
        }
      },
      authGuard: {
        badge: 'Secure Settings Access',
        title: 'Log in to unlock all settings',
        text: 'This area is only available to signed-in accounts. Once you log in, you can manage your profile, appearance, language, security, and system-wide sync.',
        points: [
          'Sync your profile and language preferences',
          'Unlock all appearance and privacy controls',
          'Keep the same experience across Skemi pages'
        ],
        login: 'Log in',
        register: 'Create account'
      },
      profileSaved: 'Account information saved.',
      localCleared: 'Browser data cleared.',
      verified: 'Email verified.',
      unverified: 'Email is not verified yet. Please check your inbox.',
      notLoggedIn: 'Not logged in.',
      saveBarText: 'You have unsaved changes.',
      saveChanges: 'Save changes',
      discardChanges: 'Discard',
      buttons: {
        saveProfile: 'Save profile',
        resetProfile: 'Reset'
      }
    },
    home: {
      title: 'Skemi Studio',
      project: {
        kicker: 'Project workspace',
        desc: 'Start with a project to keep AI Workspace, Builder, and Source Notebook organized in one place.',
        current: 'Current project',
        placeholder: 'Example: Midterm math revision',
        create: 'Create project',
        save: 'Save project',
        required: '<strong>No project selected.</strong> Create a new project or choose an existing one to begin.'
      }
    },
    notebook: {
      welcome: 'Welcome to Skemi Studio. Ask questions about your documents.'
    },
    aichat: {
      placeholder: 'Enter your request...',
      close: 'Close',
      send: 'Send',
      emptyTitle: 'No messages yet',
      emptyDesc: 'Start a conversation with AI.',
      switchMode: 'Switched to {label}',
      apiError: 'AI is unavailable right now.',
      connectError: 'AI connection is temporarily unavailable. Please try again.',
      thinking: 'AI is thinking...'
    },
    age: {
      young: 'Student',
      middle: 'Professional',
      senior: 'Senior'
    },
    status: {
      ready: 'Ready'
    }
  }
};

const STATUS_PACK_DEFAULTS = {
  vi: {
    ready: 'Sẵn sàng',
    created: 'Đã tạo dự án {name}.',
    fileSelected: 'Đã chọn {name} • {size} KB',
    timeout: 'Yêu cầu đang mất nhiều thời gian hơn dự kiến.',
    generating: 'Đang tạo nội dung...',
    selectProject: 'Hãy chọn một dự án trước.',
    enterRequest: 'Hãy nhập yêu cầu trước.',
    uploadFirst: 'Hãy tải tệp lên trước.',
    provideInput: 'Hãy cung cấp nội dung đầu vào.',
    generated: 'Đã tạo nội dung thành công.',
    generateError: 'Không thể tạo nội dung lúc này.',
    templateLoaded: 'Đã nạp mẫu thành công.',
    deleteBranch: 'Không thể xóa nhánh này.',
    builderCreated: 'Đã tạo Builder từ nguồn hiện tại.',
    noConversation: 'Chưa có hội thoại nào để chuyển đổi.',
    notebookCreated: 'Đã tạo {type} từ Notebook.',
    enterProjectName: 'Hãy nhập tên dự án.',
    switched: 'Đã chuyển chế độ thành công.',
    saved: 'Đã lưu thay đổi.'
  },
  en: {
    ready: 'Ready',
    created: 'Created project {name}.',
    fileSelected: 'Selected {name} • {size} KB',
    timeout: 'The request is taking longer than expected.',
    generating: 'Generating content...',
    selectProject: 'Choose a project first.',
    enterRequest: 'Enter a request first.',
    uploadFirst: 'Upload a file first.',
    provideInput: 'Provide input to continue.',
    generated: 'Content generated successfully.',
    generateError: 'Could not generate the content right now.',
    templateLoaded: 'Template loaded successfully.',
    deleteBranch: 'Could not delete this branch.',
    builderCreated: 'Builder created from the current sources.',
    noConversation: 'There is no conversation to convert yet.',
    notebookCreated: 'Created {type} from the notebook.',
    enterProjectName: 'Enter a project name.',
    switched: 'Switched successfully.',
    saved: 'Saved successfully.'
  }
};

for (const [lang, defaults] of Object.entries(STATUS_PACK_DEFAULTS)) {
  if (PACKS[lang]) {
    PACKS[lang].status = { ...defaults, ...(PACKS[lang].status || {}) };
  }
  if (CLEAN_PACKS[lang]) {
    CLEAN_PACKS[lang].status = { ...defaults, ...(CLEAN_PACKS[lang].status || {}) };
  }
}

function collectPackStrings(root, output = []) {
  if (typeof root === 'string') {
    const text = String(root || '').trim();
    if (text) output.push(text);
    return output;
  }
  if (Array.isArray(root)) {
    root.forEach((item) => collectPackStrings(item, output));
    return output;
  }
  if (root && typeof root === 'object') {
    Object.values(root).forEach((value) => collectPackStrings(value, output));
  }
  return output;
}

function flattenPackEntries(root, path = [], output = []) {
  if (typeof root === 'string') {
    const text = repairMojibake(String(root || ''));
    output.push({ path: path.join('.'), value: text });
    return output;
  }
  if (Array.isArray(root)) {
    root.forEach((item, index) => flattenPackEntries(item, [...path, index], output));
    return output;
  }
  if (root && typeof root === 'object') {
    Object.entries(root).forEach(([key, value]) => flattenPackEntries(value, [...path, key], output));
  }
  return output;
}

function clonePackWithTranslations(root, translationMap, path = []) {
  if (typeof root === 'string') {
    return translationMap.get(path.join('.')) || root;
  }
  if (Array.isArray(root)) {
    return root.map((item, index) => clonePackWithTranslations(item, translationMap, [...path, index]));
  }
  if (root && typeof root === 'object') {
    return Object.fromEntries(
      Object.entries(root).map(([key, value]) => [key, clonePackWithTranslations(value, translationMap, [...path, key])])
    );
  }
  return root;
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

class LanguageManager {
  constructor() {
    // Merge external language packs (i18n-packs.js) into PACKS
    this._mergeExternalPacks();
    
    this.currentLanguage = 'vi';
    this.translatedPack = null;
    this.translatedPackCacheKey = '';
    this.pendingTranslatedPack = null;
    
    this.loadSavedLanguage();
    this.applyTheme();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.applyLanguage(), { once: true });
    } else {
      this.applyLanguage();
    }
    window.languageManager = this;
    document.documentElement.__lm = this;
  }
  }
  
  _mergeExternalPacks() {
    // Merge EXT_PACKS into PACKS and CLEAN_PACKS for full UI support
    if (typeof EXT_PACKS === 'object' && EXT_PACKS !== null) {
      Object.keys(EXT_PACKS).forEach(lang => {
        const pack = EXT_PACKS[lang];
        if (pack && typeof pack === 'object') {
          // Merge into PACKS
          if (PACKS[lang]) {
            PACKS[lang] = { ...PACKS[lang], ...pack };
          } else {
            PACKS[lang] = pack;
          }
          // Also set in CLEAN_PACKS for consistency
          if (CLEAN_PACKS[lang]) {
            CLEAN_PACKS[lang] = { ...CLEAN_PACKS[lang], ...pack };
          } else {
            CLEAN_PACKS[lang] = pack;
          }
        }
      });
    }
  }

  loadSavedLanguage() {
    const profileLanguage = getSavedProfileLanguage();
    const saved = String(localStorage.getItem('skemi_language') || '').trim().toLowerCase();
    const resolved = profileLanguage || saved;
    if (resolved && LANGUAGE_CODES.includes(resolved)) {
      this.currentLanguage = resolved;
      document.documentElement.lang = resolved;
    }
  }

  init() {
    this.loadSavedLanguage();
    this.applyTheme();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.applyLanguage(), { once: true });
    } else {
      this.applyLanguage();
    }
    window.languageManager = this;
    document.documentElement.__lm = this;
  }

  applyTheme() {
    const theme = getSavedTheme();
    document.body.classList.remove('dark-mode', 'galaxy-mode');
    document.body.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    if (theme === 'dark') document.body.classList.add('dark-mode');
    if (theme === 'galaxy') document.body.classList.add('galaxy-mode', 'dark-mode');
    applyUiPreferenceClasses();
    (function(){})('Syncing theme:', theme);
  }

  syncFromSettings() {
    const nextLanguage = getSavedProfileLanguage() || String(localStorage.getItem('skemi_language') || '').trim().toLowerCase();
    this.applyTheme();
    if (nextLanguage && LANGUAGE_CODES.includes(nextLanguage) && nextLanguage !== this.currentLanguage) {
      this.currentLanguage = nextLanguage;
    }
    this.applyLanguage({ skipTranslatedPack: false });
  }

  loadSavedLanguage() {
    const profileLanguage = getSavedProfileLanguage();
    const saved = String(localStorage.getItem('skemi_language') || '').trim().toLowerCase();
    const resolved = profileLanguage || saved;
    if (resolved && LANGUAGE_CODES.includes(resolved)) {
      this.currentLanguage = resolved;
      document.documentElement.lang = resolved;
    }
  }

  get base() { return this.currentLanguage === 'vi' ? 'vi' : 'en'; }
  getResolvedBasePack(baseLang = this.base) {
    const pack = CLEAN_PACKS[baseLang] || PACKS[baseLang] || CLEAN_PACKS.vi || PACKS.vi;
    if (!pack) console.error('Language pack not found for base:', baseLang);
    return repairMojibake(pack || CLEAN_PACKS.vi || PACKS.vi || {});
  }

  getTranslatedPackCacheKey(targetLanguage = this.currentLanguage, baseLang = this.base) {
    const serialized = stableSerializePackNode(this.getResolvedBasePack(baseLang));
    return `${baseLang}:${targetLanguage}:${hashString(serialized)}`;
  }

  loadTranslatedPackFromCache(targetLanguage = this.currentLanguage, baseLang = this.base) {
    const cacheKey = this.getTranslatedPackCacheKey(targetLanguage, baseLang);
    const cached = runtimeUiPackCache[cacheKey];
    if (!cached || typeof cached !== 'object') return null;
    const repaired = repairMojibake(cached);
    this.translatedPack = repaired;
    this.translatedPackCacheKey = cacheKey;
    return repaired;
  }

  get pack() {
    const basePack = this.getResolvedBasePack();
    if (FULL_UI_PACKS.has(this.currentLanguage)) return basePack;

    const expectedKey = this.getTranslatedPackCacheKey();
    if (this.translatedPack && this.translatedPackCacheKey === expectedKey) {
      return repairMojibake(this.translatedPack);
    }

    const cached = this.loadTranslatedPackFromCache();
    if (cached) return cached;

    return basePack;
  }

  async ensureTranslatedPack(force = false) {
    if (FULL_UI_PACKS.has(this.currentLanguage)) {
      this.translatedPack = null;
      this.translatedPackCacheKey = '';
      this.pendingTranslatedPack = null;
      return this.getResolvedBasePack();
    }

    const targetLanguage = this.currentLanguage;
    const baseLang = this.base;
    const cacheKey = this.getTranslatedPackCacheKey(targetLanguage, baseLang);

    if (!force) {
      if (this.translatedPack && this.translatedPackCacheKey === cacheKey) {
        return this.translatedPack;
      }
      const cached = this.loadTranslatedPackFromCache(targetLanguage, baseLang);
      if (cached) return cached;
    }

    if (this.pendingTranslatedPack?.key === cacheKey) {
      return this.pendingTranslatedPack.promise;
    }

    const task = (async () => {
      const basePack = this.getResolvedBasePack(baseLang);
      const entries = flattenPackEntries(basePack).filter(({ value }) => {
        const text = String(value || '').trim();
        if (!text) return false;
        if (text.length > 260) return false;
        if (/skemi|skemma/i.test(text)) return false;
        return true;
      });

      if (!entries.length) return basePack;

      const uniqueTexts = Array.from(new Set(entries.map((entry) => entry.value)));
      const translatedStrings = await translateUiBatch(uniqueTexts, targetLanguage, baseLang);
      const bySourceText = new Map();
      uniqueTexts.forEach((text, index) => {
        bySourceText.set(text, translatedStrings[index] || text);
      });
      const translationMap = new Map();
      entries.forEach((entry) => {
        translationMap.set(entry.path, bySourceText.get(entry.value) || entry.value);
      });

      const translatedPack = repairMojibake(clonePackWithTranslations(basePack, translationMap));
      Object.keys(runtimeUiPackCache).forEach((key) => {
        if (key.startsWith(`${baseLang}:${targetLanguage}:`) && key !== cacheKey) {
          delete runtimeUiPackCache[key];
        }
      });
      runtimeUiPackCache[cacheKey] = translatedPack;
      persistRuntimeUiPackCache();
      this.translatedPack = translatedPack;
      this.translatedPackCacheKey = cacheKey;
      return translatedPack;
    })();

    this.pendingTranslatedPack = { key: cacheKey, promise: task };
    try {
      return await task;
    } finally {
      if (this.pendingTranslatedPack?.key === cacheKey) {
        this.pendingTranslatedPack = null;
      }
    }
  }

  t(path, params = {}) {
    const parts = path.split('.');
    const resolve = (root) => {
      let value = root;
      for (const part of parts) {
        value = value?.[part];
        if (value === undefined) break;
      }
      return value;
    };

    let value = resolve(this.pack);
    if (value === undefined || value === null) value = resolve(CLEAN_PACKS.en);
    if (value === undefined || value === null) value = resolve(CLEAN_PACKS.vi);
    if (value === undefined || value === null) value = resolve(PACKS.en);
    if (value === undefined || value === null) value = resolve(PACKS.vi);
    
    if (value === undefined || value === null) {
      console.warn(`Translation key not found: ${path} (Base: ${this.base})`);
      return path;
    }

    if (typeof value === 'string') {
      return repairMojibake(value).replace(/\{(\w+)\}/g, (_, k) => params[k] ?? '');
    }

    return repairMojibake(value);
  }

  setText(selector, value) { document.querySelectorAll(selector).forEach(el => { el.textContent = repairMojibake(value); }); }
  setHTML(selector, value) { document.querySelectorAll(selector).forEach(el => { el.innerHTML = repairMojibake(value); }); }
  setPlaceholder(selector, value) { document.querySelectorAll(selector).forEach(el => { el.placeholder = repairMojibake(value); }); }
  setTitle(selector, value) { document.querySelectorAll(selector).forEach(el => { const fixed = repairMojibake(value); el.title = fixed; el.setAttribute('aria-label', fixed); }); }

  applyShared() {
    this.setText('#mindmap-link span:last-child', this.pack.nav.studio);
    this.setText('#search-link span:last-child', this.pack.nav.search);
    this.setText('#quiz-link span:last-child', this.pack.nav.quiz);
    this.setText('#chat-link span:last-child', this.pack.nav.chat);
    this.setText('#settings-link span:last-child', this.pack.nav.settings);
    this.setText('#top-studio-link span:last-child', this.pack.nav.studio);
    this.setText('#top-search-link span:last-child', this.pack.nav.search);
    this.setText('#top-quiz-link span:last-child', this.pack.nav.quiz);
    this.setText('#top-chat-link span:last-child', this.pack.nav.chat);
    this.setText('.sidebar-footer > div', this.pack.nav.version);
    this.setTitle('#toggleSidebar', this.pack.common.sidebarCollapse);

    // Update i18n data attributes if any
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const translated = this.t(key);
        if (translated !== key) {
          if (typeof translated === 'string' && translated.includes('<')) {
            el.innerHTML = translated;
          } else {
            el.textContent = repairMojibake(translated);
          }
        }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        const translated = this.t(key);
        if (translated !== key) el.placeholder = repairMojibake(translated);
    });

    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        const translated = this.t(key);
        if (translated !== key) {
          const fixed = repairMojibake(translated);
          el.title = fixed;
          el.setAttribute('aria-label', fixed);
        }
    });
  }

  applyHome() {
    if (!document.getElementById('studioWorkbench')) return;
    const isVi = this.currentLanguage === 'vi';
    this.setText('.project-kicker', this.t('home.project.kicker'));
    this.setText('.hub-header p', this.t('home.project.desc'));
    this.setText('#backToProjectsBtn', isVi ? 'Studio Hub' : 'Studio Hub');

    document.querySelectorAll('.guide-card').forEach(card => {
        const action = card.dataset.guideAction;
        if (action === 'faq') {
            card.querySelector('h5').textContent = 'FAQ';
            card.querySelector('p').textContent = isVi ? 'C\u00e2u h\u1ecfi th\u01b0\u1eddng g\u1eb7p t\u1eeb t\u00e0i li\u1ec7u.' : 'Frequently asked questions from documents.';
        } else if (action === 'toc') {
            card.querySelector('h5').textContent = isVi ? 'M\u1ee5c l\u1ee5c' : 'Table of Contents';
            card.querySelector('p').textContent = isVi ? 'C\u1ea5u tr\u00fac ch\u00ednh c\u1ee7a n\u1ed9i dung.' : 'Main structure of the content.';
        } else if (action === 'study') {
            card.querySelector('h5').textContent = isVi ? 'H\u01b0\u1edbng d\u1eabn h\u1ecdc' : 'Study Guide';
            card.querySelector('p').textContent = isVi ? 'L\u1ed9 tr\u00ecnh n\u1eafm b\u1eaft ki\u1ebfn th\u1ee9c.' : 'Path to master knowledge.';
        }
    });

    const welcomeBubble = document.querySelector('#notebookMessages .message.system .message-bubble');
    if (welcomeBubble) welcomeBubble.textContent = this.t('notebook.welcome');
    this.setPlaceholder('#notebookInput', isVi ? 'H\u1ecfi AI v\u1ec1 c\u00e1c t\u00e0i li\u1ec7u...' : 'Ask AI about documents...');
    
    this.setText('.preview-header-minimal span', isVi ? 'B\u1ea3n xem tr\u01b0\u1edbc' : 'Preview');
    this.setTitle('#clearStudioPreviewBtn', isVi ? 'X\u00f3a n\u1ed9i dung' : 'Clear Content');
  }

  applySettingsPage() {
    if (!document.querySelector('.settings-layout')) return;

    const settings = this.pack.settings || {};
    const titleEl = document.querySelector('title');
    if (titleEl && this.pack.meta?.settingsTitle) {
      titleEl.textContent = this.pack.meta.settingsTitle;
    }

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      metaDesc.setAttribute(
        'content',
        this.base === 'vi'
          ? 'Skemi cài đặt - quản lý tài khoản, ngôn ngữ, giao diện, bảo mật và gói dịch vụ.'
          : 'Skemi settings - manage your account, language, appearance, security, and plans.'
      );
    }

    const authGuard = settings.authGuard || {};
    const guard = document.getElementById('authGuard');
    if (guard) {
      const badge = guard.querySelector('.auth-guard-badge');
      const heading = guard.querySelector('.auth-guard-title');
      const text = guard.querySelector('.auth-guard-text');
      const points = guard.querySelectorAll('.auth-guard-point');
      const actions = guard.querySelectorAll('.auth-guard-actions a');
      if (badge && authGuard.badge) badge.textContent = authGuard.badge;
      if (heading && authGuard.title) heading.textContent = authGuard.title;
      if (text && authGuard.text) text.textContent = authGuard.text;
      if (points.length && Array.isArray(authGuard.points)) {
        points.forEach((item, index) => {
          if (authGuard.points[index]) item.textContent = authGuard.points[index];
        });
      }
      if (actions[0] && authGuard.login) actions[0].textContent = authGuard.login;
      if (actions[1] && authGuard.register) actions[1].textContent = authGuard.register;
    }

    const planCards = document.querySelectorAll('#tab-subscription .plan-card');
    const plans = settings.plans || {};
    const orderedPlans = [plans.free, plans.pro, plans.advanced];
    planCards.forEach((card, index) => {
      const plan = orderedPlans[index];
      if (!plan) return;
      const heading = card.querySelector('div[style*="font-weight:800"]');
      const price = card.querySelector('.plan-price');
      const list = card.querySelector('.plan-list');
      const button = card.querySelector('button');
      if (heading && plan.name) heading.textContent = plan.name;
      if (price && plan.price && plan.period) {
        price.innerHTML = `${plan.price} <span>${plan.period}</span>`;
      }
      if (list && Array.isArray(plan.features)) {
        list.innerHTML = plan.features.map((feature) => `<li>&#10004; ${feature}</li>`).join('');
      }
      if (button && plan.button) button.textContent = plan.button;
    });
  }

  renderLanguageSelector() {
    const container = document.getElementById('language-settings');
    if (!container) return;

    const names = {
      vi: 'Ti?ng Vi?t', en: 'English', zh: '??', ja: '???', ko: '???', es: 'Espa?ol', fr: 'Fran?ais',
      de: 'Deutsch', it: 'Italiano', pt: 'Portugu?s', ru: '???????', th: '???', id: 'Bahasa Indonesia',
      ar: '???????', hi: '??????', ms: 'Bahasa Melayu', tr: 'T?rk?e', pl: 'Polski', nl: 'Nederlands',
      sv: 'Svenska', no: 'Norsk', da: 'Dansk', fi: 'Suomi', uk: '??????????'
    };

    container.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'settings-language-control';
    wrapper.innerHTML = `
      <label class="settings-language-label" for="skemiLanguageSelect">
        <span>${this.base === 'vi' ? 'Ng?n ng? web' : 'Website language'}</span>
        <small>${this.base === 'vi' ? 'D?ch giao di?n c? s?n. Kh?ng d?ch tin nh?n, t?n ng??i d?ng, AI output ho?c th??ng hi?u.' : 'Translates built-in UI only. User text, AI output, and brand names stay untouched.'}</small>
      </label>
      <div class="settings-language-select-wrap">
        <select id="skemiLanguageSelect" class="settings-trackable"></select>
      </div>
    `;
    const select = wrapper.querySelector('#skemiLanguageSelect');
    LANGUAGE_CODES.forEach((code) => {
      const option = document.createElement('option');
      option.value = code;
      option.textContent = `${names[code] || code.toUpperCase()} (${code.toUpperCase()})`;
      option.selected = this.currentLanguage === code;
      select.appendChild(option);
    });
    select.addEventListener('change', () => this.changeLanguage(select.value));
    container.appendChild(wrapper);
  }

  async applyRuntimeLanguage() {
    const target = this.currentLanguage;
    const shouldSkipElement = (el) => {
      if (!el || el.nodeType !== Node.ELEMENT_NODE) return true;
      const tag = el.tagName?.toLowerCase();
      if (['script', 'style', 'textarea', 'input', 'code', 'pre', 'canvas', 'svg'].includes(tag)) return true;
      if (el.closest('[data-no-translate], [data-preserve-language], [data-message-content], .ai-message, #aiChatMessages, #notebookMessages, .chat-messages, .message, .search-results, #resultsContainer, .surface-chat-feed, [contenteditable="true"]')) return true;
      return false;
    };

    const restoreNodes = () => {
      document.querySelectorAll('[data-skemi-source-text]').forEach((el) => {
        if (shouldSkipElement(el)) return;
        const source = el.getAttribute('data-skemi-source-text');
        if (source) el.textContent = source;
      });
      document.querySelectorAll('[data-skemi-source-placeholder]').forEach((el) => {
        const source = el.getAttribute('data-skemi-source-placeholder');
        if (source) el.setAttribute('placeholder', source);
      });
      document.querySelectorAll('[data-skemi-source-title]').forEach((el) => {
        const source = el.getAttribute('data-skemi-source-title');
        if (source) el.setAttribute('title', source);
      });
    };

    if (FULL_UI_PACKS.has(target)) {
      restoreNodes();
      return;
    }

    await this.ensureTranslatedPack().catch(() => null);

    const roots = [document.querySelector('.top-navbar'), document.querySelector('.sidebar'), document.querySelector('main'), document.querySelector('.settings-layout')].filter(Boolean);
    const textNodes = [];
    roots.forEach((root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => {
          const parent = node.parentElement;
          if (!parent || shouldSkipElement(parent)) return NodeFilter.FILTER_REJECT;
          const text = String(node.nodeValue || '').replace(/\s+/g, ' ').trim();
          if (!text || text.length < 2 || text.length > 180) return NodeFilter.FILTER_REJECT;
          if (/^(Skemi|Skemma)$/i.test(text)) return NodeFilter.FILTER_REJECT;
          if (/^[\d\W_]+$/.test(text)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });
      let node;
      while ((node = walker.nextNode())) textNodes.push(node);
    });

    const sourceTexts = [];
    textNodes.forEach((node) => {
      const parent = node.parentElement;
      const current = String(node.nodeValue || '').replace(/\s+/g, ' ').trim();
      const source = parent.getAttribute('data-skemi-source-text') || current;
      parent.setAttribute('data-skemi-source-text', source);
      sourceTexts.push(source);
    });

    const attrTargets = [];
    document.querySelectorAll('[placeholder], [title]').forEach((el) => {
      if (shouldSkipElement(el)) return;
      const placeholder = el.getAttribute('placeholder');
      if (placeholder && placeholder.trim() && placeholder.length <= 180) {
        const source = el.getAttribute('data-skemi-source-placeholder') || placeholder.trim();
        el.setAttribute('data-skemi-source-placeholder', source);
        attrTargets.push({ el, attr: 'placeholder', source });
        sourceTexts.push(source);
      }
      const title = el.getAttribute('title');
      if (title && title.trim() && title.length <= 180) {
        const source = el.getAttribute('data-skemi-source-title') || title.trim();
        el.setAttribute('data-skemi-source-title', source);
        attrTargets.push({ el, attr: 'title', source });
        sourceTexts.push(source);
      }
    });

    const unique = Array.from(new Set(sourceTexts));
    if (!unique.length) return;
    const translated = await translateUiBatch(unique, target, this.base);
    const map = new Map(unique.map((item, index) => [item, translated[index] || item]));

    textNodes.forEach((node) => {
      const parent = node.parentElement;
      const source = parent?.getAttribute('data-skemi-source-text');
      if (source && map.has(source)) node.nodeValue = map.get(source);
    });
    attrTargets.forEach(({ el, attr, source }) => {
      if (map.has(source)) el.setAttribute(attr, map.get(source));
    });
  }

  async prewarmCurrentLanguageCache() {
    if (FULL_UI_PACKS.has(this.currentLanguage)) return;
    await this.ensureTranslatedPack();
  }

  applyLanguage(options = {}) {
    (function(){})('Applying language:', this.currentLanguage);
    document.documentElement.__lm = this; // Backup access
    document.documentElement.lang = this.currentLanguage;
    applyUiPreferenceClasses();
    this.applyShared();
    this.applyHome();
    this.applyAIChat();
    this.applySettingsPage();
    this.renderLanguageSelector();
    repairDomText(document.body);
    startMojibakeObserver();
    window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang: this.currentLanguage } }));
    this.applyRuntimeLanguage().catch(() => {});
    if (!FULL_UI_PACKS.has(this.currentLanguage) && !options.skipTranslatedPack) {
      const requestedLanguage = this.currentLanguage;
      const requestedKey = this.getTranslatedPackCacheKey(requestedLanguage, this.base);
      if (this.translatedPackCacheKey !== requestedKey) {
        this.prewarmCurrentLanguageCache()
          .then(() => {
            if (this.currentLanguage !== requestedLanguage) return;
            if (this.translatedPackCacheKey !== requestedKey) return;
            this.applyLanguage({ skipTranslatedPack: true });
          })
          .catch(() => {});
      }
    }
  }

  applyAIChat() {
    const input = document.getElementById('aiChatInput');
    if (input) input.placeholder = this.t('aichat.placeholder');
  }

  changeLanguage(code) {
    const next = LANGUAGE_CODES.includes(code) ? code : 'en';
    this.currentLanguage = next;
    if (FULL_UI_PACKS.has(next)) {
      this.translatedPack = null;
      this.translatedPackCacheKey = '';
    }
    localStorage.setItem('skemi_language', next);
    persistProfileLanguage(next);
    this.applyLanguage();
  }
}

window.languageManager = new LanguageManager();
window.addEventListener('storage', (event) => {
  if (event.key === 'skemi_user_data' || event.key === 'skemi-theme' || event.key === 'skemi_language') {
    window.languageManager?.syncFromSettings();
  }
});
window.addEventListener('skemiSettingsChanged', () => {
  window.languageManager?.syncFromSettings();
});
window.addEventListener('themeChanged', () => {
  window.languageManager?.applyTheme();
});
document.addEventListener('click', (event) => {
  const link = event.target.closest?.('a[href]');
  if (!link || event.defaultPrevented) return;
  if (link.target && link.target !== '_self') return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  try {
    const targetUrl = new URL(link.href, window.location.href);
    if (targetUrl.origin === window.location.origin) {
      sessionStorage.setItem(INTERNAL_NAV_KEY, '1');
    }
  } catch {}
}, true);
window.addEventListener('beforeunload', () => {
  try {
    if (sessionStorage.getItem(INTERNAL_NAV_KEY) === '1') {
      sessionStorage.removeItem(INTERNAL_NAV_KEY);
      return;
    }
    sessionStorage.removeItem(CHAT_BOOT_KEY);
  } catch {}
});
window.skemiT = (path, params = {}) => window.languageManager.t(path, params);
export default window.languageManager;
