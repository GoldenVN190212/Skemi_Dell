

const searchData = new UserDataManager('search_history');
const studioData = new UserDataManager('studio');
const aiCommandData = new UserDataManager('ai_command');
const _searchUDM = new UserDataManager('search');

// UI Helper Functions
function showSearchLoading() {
    const btn = document.getElementById('searchBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Đang tra cứu...';
    }
    const container = document.getElementById('search-results-section');
    if (container) {
        container.style.display = 'none';
    }
    const errorContainer = document.getElementById('search-error');
    if (errorContainer) {
        errorContainer.style.display = 'none';
    }
}

function hideSearchLoading() {
    const btn = document.getElementById('searchBtn');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Phân tích';
    }
}

function clearSearchResults() {
    const briefEl = document.getElementById('search-brief');
    if (briefEl) briefEl.textContent = '';
    const sourcesEl = document.getElementById('search-sources');
    if (sourcesEl) sourcesEl.innerHTML = '';
    const tracksEl = document.getElementById('search-tracks');
    if (tracksEl) tracksEl.innerHTML = '';
    const container = document.getElementById('search-results-section');
    if (container) container.style.display = 'none';
}

function updateSearchStatus(message) {
    const statusEl = document.getElementById('search-status');
    if (statusEl) statusEl.textContent = message || '';
}

function renderSearchResults(analysis) {
    if (!analysis) return;
    const brief   = analysis.brief || analysis.answer || '';
    const sources = analysis.sources || analysis.sources_drawer || [];
    const tracks  = analysis.tracks || [];
    
    // Render into DOM
    const briefEl = document.getElementById('search-brief');
    if (briefEl) briefEl.textContent = brief;
    
    const sourcesEl = document.getElementById('search-sources');
    if (sourcesEl) {
        sourcesEl.innerHTML = sources.map(s => 
            `<div class="search-source-item"><a href="${s.url}" target="_blank" rel="noopener">${s.title || s.url}</a></div>`
        ).join('');
    }
    
    const tracksEl = document.getElementById('search-tracks');
    if (tracksEl) {
        tracksEl.innerHTML = tracks.map(t => 
            `<div class="search-track-item"><strong>${t.label || t.key}</strong>: ${t.description}</div>`
        ).join('');
    }
    
    const container = document.getElementById('search-results-section');
    if (container) container.style.display = 'block';
}

function showSearchError(message) {
    const errorContainer = document.getElementById('search-error');
    if (errorContainer) {
        errorContainer.textContent = message || (lang() === 'vi' ? 'Lỗi không xác định' : 'Unknown error');
        errorContainer.style.display = 'block';
    }
    hideSearchLoading();
}

async function _saveSearchHistory(query) {
    await _searchUDM.load();
    const raw = _searchUDM.get('history', []);
    // Older/corrupt storage may hold a non-array → guard against .filter crash.
    const history = Array.isArray(raw) ? raw.filter(h => h && typeof h === 'object') : [];
    const updated = [{ query, time: Date.now() },
                     ...history.filter(h => h.query !== query)
                    ].slice(0, 50);
    await _searchUDM.set('history', updated);
}

const SEARCH_STATE_KEY = 'skemi_search_state_v7';
const SEARCH_ANALYSIS_KEY = 'skemi_search_analysis_v5';
const SEARCH_ACTIVE_JOB_KEY = 'skemi_search_active_job_v4';
const searchStorage = (() => {
    try {
        return window.sessionStorage;
    } catch {
        try {
            return window.localStorage;
        } catch {
            return null;
        }
    }
})();
// Ensure API_BASE works even if port differs
const getApiBase = () => {
    if (window.SKEMI_API_BASE) return window.SKEMI_API_BASE.trim().replace(/\/+$/, '');
    if (window.location.port === '8001' || window.location.port === '5500' || !window.location.port) {
        return 'http://127.0.0.1:8010'; 
    }
    return '';
};
const API_BASE = getApiBase();
const apiUrl = (path) => (API_BASE ? `${API_BASE}${path}` : path);
const SEARCH_COMMAND_GUARD_KEY = 'skemi_search_last_command_v3';

function getHistory() {
    return searchData.get('history', []);
}

async function saveToHistory(query) {
    if (!query || query.length < 3) return;
    const history = getHistory();
    const clean = query.trim();
    if (history[0] === clean) return;
    const updated = [clean, ...history.filter(q => q !== clean)].slice(0, 20);
    await searchData.set('history', updated);
    updateGhostText();
}

function updateGhostText() {
    const input = el.searchInput;
    const ghost = document.getElementById('ghostSearchText');
    if (!input || !ghost) return;

    const val = input.value;
    if (!val) {
        ghost.textContent = '';
        return;
    }

    const history = getHistory();
    const match = history.find(q => q.toLowerCase().startsWith(val.toLowerCase()));
    
    if (match && match.toLowerCase() !== val.toLowerCase()) {
        ghost.textContent = val + match.slice(val.length);
    } else {
        ghost.textContent = '';
    }
}
let currentUser = null;
let activeWorkflow = null;

const CATEGORY_ICONS = {
    '': '✨',
    general: '🧭',
    tech: '💻',
    business: '💼',
    world: '🌐',
    sports: '⚡',
    science: '🧪',
    entertainment: '🎨',
    health: '🩺',
    education: '🎓'
};

const SAMPLE_QUERIES = {
    vi: [
        ['education', 'Lập kế hoạch học Vật lý lớp 8', 'Tách chủ đề thành mục tiêu, mindmap và flashcard.'],
        ['science', 'Tóm tắt tài liệu về năng lượng tái tạo', 'Biến tài liệu thành hướng nghiên cứu và báo cáo.'],
        ['business', 'Xây quy trình onboarding cho nhân viên mới', 'Tạo khung triển khai, checklist và trình bày.'],
        ['tech', 'Học AI agent từ cơ bản đến ứng dụng', 'Tạo lộ trình, nhánh chính và prompt cho Studio.'],
        ['health', 'Tìm hiểu dinh dưỡng cho người lớn tuổi', 'Chia thành ý chính, lưu ý và nguồn nên đọc.'],
        ['world', 'Phân tích chuyển đổi số trong giáo dục', 'Rút ra góc nhìn học tập, nghiên cứu và ứng dụng.']
    ],
    en: [
        ['education', 'Create an 8th grade physics study plan', 'Split the topic into goals, a mindmap, and flashcards.'],
        ['science', 'Summarize renewable energy materials', 'Turn the topic into research directions and a report.'],
        ['tech', 'Compare the newest MiniMax and Qwen models', 'Separate the latest releases, evidence, and what still needs verification.'],
        ['tech', 'Learn AI agents from basics to real use cases', 'Build a roadmap and Studio-ready prompts.'],
        ['health', 'Explore nutrition guidance for seniors', 'Break the topic into key ideas and supporting sources.'],
        ['world', 'Analyze digital transformation in education', 'Extract study, research, and execution angles.']
    ]
};

const TEXT = {
    vi: {
        title: 'Skemi Tra cứu',
        metaDescription: 'Skemi Tra cứu - chuyển một chủ đề thành chiến lược học tập, nghiên cứu và triển khai thực tế.',
        subtitle: 'Biến một chủ đề thành brief rõ ràng, góc nhìn quan trọng, bước đi tiếp theo và đầu ra sẵn sàng đưa sang Studio.',
        placeholder: 'Nhập chủ đề, câu hỏi hoặc vấn đề...',
        button: 'Phân tích chủ đề',
        chips: ['Tất cả hướng', 'Tổng quan', 'Công nghệ', 'Kinh doanh', 'Bối cảnh', 'Thực hành', 'Nghiên cứu', 'Sáng tạo', 'Sức khỏe', 'Ôn tập'],
        briefEyebrow: 'Tra cứu thông minh',
        briefTitle: 'Bản tóm lược cho "{query}"',
        briefDescription: 'Skemi không chỉ hiển thị kết quả. Trang này gợi ý cách học, cách nghiên cứu, cách triển khai công việc và cách đưa chủ đề sang Studio.',
        sourcesTitle: 'Nguồn đã tham chiếu',
        sourcesDescription: 'Các nguồn dùng để tổng hợp kết quả tra cứu.',
        keywordTitle: 'Từ khóa mở rộng',
        keywordDescription: 'Bấm vào từ khóa để thay truy vấn hoặc mở rộng chủ đề rồi phân tích tiếp.',
        actionMindmap: 'Đưa mindmap sang Studio',
        actionFlashcard: 'Đưa flashcard sang Studio',
        actionReport: 'Đưa báo cáo sang Studio',
        resultsCount: '{count} hướng triển khai sẵn sàng',
        mainGroupTitle: 'Đầu ra sẵn sàng triển khai',
        mainGroupDescription: 'Các gợi ý dưới đây có thể đưa thẳng sang Studio để tạo kết quả trực quan ngay.',
        sideGroupTitle: 'Gợi ý khai thác tiếp',
        sideGroupDescription: 'Nếu muốn đi sâu hơn, hãy bổ sung các góc tiếp cận và nguồn dữ liệu sau.',
        creativeTitle: 'Bùng nổ sáng tạo',
        creativeDescription: 'Ba ý tưởng bùng nổ để mở rộng chủ đề theo góc nhìn sản phẩm, nội dung và thử nghiệm.',
        creativeUse: 'Dùng ý tưởng này',
        creativeCopy: 'Chép ý tưởng',
        promptLabel: 'Gợi ý cho Studio',
        useInStudio: 'Dùng trong Studio',
        copyPrompt: 'Chép nội dung',
        copied: 'Đã chép nội dung',
        sampleTitle: 'Bệ phóng tra cứu',
        stats: ['Cụm tình huống', 'Lớp kiểm chứng', 'Bước đi nhanh', 'Cập nhật'],
        emptyTitle: 'Chưa có chủ đề',
        emptyText: 'Nhập một chủ đề để Skemi phân tích và lập kế hoạch.',
        needQuery: 'Hãy nhập chủ đề trước.',
        cards: [
            ['🎯', 'Học tập', 'Tổ chức kiến thức nhanh', 'Tách ý chính trước, rồi mới bung nhánh chi tiết và điểm cần nhớ.'],
            ['🧠', 'Nghiên cứu', 'Dò khoảng trống thông tin', 'Tách nền tảng, dữ liệu, câu hỏi mở và phần còn thiếu nguồn.'],
            ['🛠️', 'Làm việc', 'Chuyển chủ đề thành hành động', 'Biến chủ đề thành bước làm, checklist và cách theo dõi.'],
            ['🚀', 'Tiếp theo', 'Biến thành đầu ra cụ thể', 'Từ brief này, bạn có thể chuyển sang mindmap, report, flashcard hoặc checklist hành động.']
        ],
        sourceHints: [
            ['Nguồn nên chuẩn bị', 'Tải file bài giảng, ghi chú, PDF, ảnh hoặc bảng dữ liệu liên quan để kết quả chính xác hơn.'],
            ['Câu hỏi nên đào sâu', 'Xác định 3 đến 5 câu hỏi trọng tâm để làm rõ nền tảng, ứng dụng và phần dễ nhầm.'],
            ['Tiêu chí kiểm tra kết quả', 'Kiểm tra xem đầu ra đã có cấu trúc, ví dụ minh họa, phần thực hành và phần còn thiếu dữ liệu chưa.'],
            ['Bước tiếp theo trong Skemi', 'Sau khi chốt hướng, hãy chuyển prompt sang Studio hoặc Notebook để tạo nội dung trực quan.']
        ],
        types: { mindmap: 'Mindmap', flashcard: 'Flashcard', report: 'Báo cáo', presentation: 'Bảng trình bày', infographic: 'Bảng đồ họa', chart: 'Biểu đồ' },
        modes: { study: 'Học tập', research: 'Nghiên cứu', work: 'Làm việc', synthesis: 'Tổng hợp' },
        categoryLabels: { general: 'Tổng quan', tech: 'Công nghệ', business: 'Kinh doanh', world: 'Bối cảnh', sports: 'Thực hành', science: 'Nghiên cứu', entertainment: 'Sáng tạo', health: 'Sức khỏe', education: 'Ôn tập' },
        filters: { time: ['Mọi thời điểm', '1 giờ qua', '24 giờ qua', '7 ngày qua', '30 ngày qua'], sort: ['Phù hợp nhất', 'Mới nhất'], lang: ['Tất cả ngôn ngữ', 'Tiếng Việt', 'English'] },
        updated: 'Vừa xong'
    },
    en: {
        title: 'Skemi Search',
        metaDescription: 'Skemi Search - turn one topic into execution-ready study, research, and work plans.',
        subtitle: 'Turn one topic into a clear brief, useful angles, next moves, and Studio-ready outputs.',
        placeholder: 'Enter a topic, question, or problem...',
        button: 'Analyze topic',
        chips: ['All angles', 'General', 'Tech', 'Business', 'Context', 'Practical', 'Research', 'Creative', 'Health', 'Review'],
        briefEyebrow: 'Smart search',
        briefTitle: 'Brief for "{query}"',
        briefDescription: 'This page does more than search. It suggests how to learn the topic, research it, operationalize it, and move it into Studio.',
        sourcesTitle: 'Sources used',
        sourcesDescription: 'Sources used to compile this brief.',
        keywordTitle: 'Expansion keywords',
        keywordDescription: 'Click a keyword to replace the query or expand the topic, then analyze again.',
        actionMindmap: 'Send mindmap to Studio',
        actionFlashcard: 'Send flashcard to Studio',
        actionReport: 'Send report to Studio',
        resultsCount: '{count} ready-to-build directions',
        mainGroupTitle: 'Execution-ready outputs',
        mainGroupDescription: 'These suggestions can go straight into Studio to create visual outputs immediately.',
        sideGroupTitle: 'Next things to explore',
        sideGroupDescription: 'If you want deeper output, add the following angles and supporting sources.',
        creativeTitle: 'Creative burst',
        creativeDescription: 'Three high-impact ideas to expand the topic into product, content, and experiment directions.',
        creativeUse: 'Use this idea',
        creativeCopy: 'Copy idea',
        promptLabel: 'Studio guide',
        useInStudio: 'Use in Studio',
        copyPrompt: 'Copy content',
        copied: 'Copied',
        sampleTitle: 'Search launchpad',
        stats: ['Use cases', 'Verification layers', 'Fast next moves', 'Updated'],
        emptyTitle: 'No topic yet',
        emptyText: 'Enter a topic and Skemi will analyse it and plan it out.',
        needQuery: 'Enter a topic first.',
        cards: [
            ['🎯', 'Study', 'Organize knowledge fast', 'Show the main ideas first, then expand into details and memory anchors.'],
            ['🧠', 'Research', 'Find information gaps', 'Break the topic into foundations, data, open questions, and missing sources.'],
            ['🛠️', 'Work', 'Turn the topic into action', 'Translate the topic into steps, checklists, and progress tracking.'],
            ['🚀', 'Next', 'Turn it into output', 'Use the brief to create a mindmap, report, flashcards, or an action checklist next.']
        ],
        sourceHints: [
            ['Sources to prepare', 'Upload lecture notes, PDFs, images, or personal documents so the output is stronger.'],
            ['Questions to deepen', 'Define three to five core questions to clarify foundations, applications, and confusing points.'],
            ['Result quality checks', 'Check whether the output has structure, examples, practice value, and clearly marked missing data.'],
            ['Next step in Skemi', 'Once the direction is clear, move the prompt into Studio or Notebook to build visual output.']
        ],
        types: { mindmap: 'Mindmap', flashcard: 'Flashcard', report: 'Report', presentation: 'Presentation', infographic: 'Infographic', chart: 'Chart' },
        modes: { study: 'Study', research: 'Research', work: 'Work', synthesis: 'Synthesis' },
        categoryLabels: { general: 'General', tech: 'Tech', business: 'Business', world: 'Context', sports: 'Practical', science: 'Research', entertainment: 'Creative', health: 'Health', education: 'Review' },
        filters: { time: ['Any time', 'Past hour', 'Past 24 hours', 'Past 7 days', 'Past 30 days'], sort: ['Most relevant', 'Newest'], lang: ['All languages', 'Vietnamese', 'English'] },
        updated: 'Just now'
    }
};

const state = {
    query: '',
    rawQuery: '',
    category: '',
    time: '',
    sort: 'relevance',
    lang: '',
    selectedSuggestionIndex: -1,
    analysis: null,
    activeJobId: '',
    requestKey: '',
    jobStatus: '',
    suppressResumeToast: false,
    stateUpdatedAt: 0
};
const el = {
    hero: document.getElementById('searchHero'),
    searchInput: document.getElementById('searchInput'),
    searchBtn: document.getElementById('searchBtn'),
    suggestions: document.getElementById('suggestionsDropdown'),
    chips: document.querySelectorAll('.filter-chip'),
    researchBrief: document.getElementById('researchBrief'),
    briefEyebrow: document.getElementById('briefEyebrow'),
    briefTitle: document.getElementById('briefTitle'),
    briefDescription: document.getElementById('briefDescription'),
    briefActions: document.getElementById('briefActions'),
    briefGrid: document.getElementById('briefGrid'),
    briefSources: document.getElementById('briefSources'),
    briefSourcesTitle: document.getElementById('briefSourcesTitle'),
    briefSourcesDesc: document.getElementById('briefSourcesDesc'),
    briefSourcesList: document.getElementById('briefSourcesList'),
    keywordTitle: document.getElementById('keywordBoardTitle'),
    keywordDescription: document.getElementById('keywordBoardDesc'),
    keywordGroup: document.getElementById('keywordChipGroup'),
    resultsArea: document.getElementById('resultsArea'),
    resultsHeader: document.getElementById('resultsHeader'),
    resultsCount: document.getElementById('resultsCount'),
    resultsQueryWrap: document.getElementById('resultsQueryWrap'),
    resultsQuery: document.getElementById('resultsQuery'),
    resultsContainer: document.getElementById('resultsContainer'),
    timeFilter: document.getElementById('timeFilter'),
    sortFilter: document.getElementById('sortFilter'),
    langFilter: document.getElementById('langFilter'),
    trendingTitle: document.querySelector('.trending-section .section-title'),
    trendingGrid: document.getElementById('trendingGrid'),
    trendingSection: document.getElementById('trendingSection'),
    statsBar: document.getElementById('statsBar'),
    statArticles: document.getElementById('statArticles'),
    statSources: document.getElementById('statSources'),
    statDbSize: document.getElementById('statDbSize'),
    statLastUpdate: document.getElementById('statLastUpdate'),
    researchConsole: document.getElementById('researchConsole'),
    quickSummaryBox: document.getElementById('quickSummaryBox'),
    summaryContent: document.getElementById('summaryContent'),
};

/**
 * Adds a new line to the hacker-style research console.
 * @param {string} text 
 */

const RGP_PHASES = ['search', 'read', 'cross', 'synth'];
function _rgpPhaseFor(text) {
    const t = (text || '').toLowerCase();
    if (/(tìm|tim|search|nguồn|nguon|truy|query)/.test(t)) return 'search';
    if (/(đọc|doc|read|trích|trich|crawl|extract|bóc|boc)/.test(t)) return 'read';
    if (/(đối soát|doi soat|cross|verif|kiểm|kiem|fact|đối chiếu)/.test(t)) return 'cross';
    if (/(tổng hợp|tong hop|synth|báo cáo|bao cao|hoàn|hoan|viết|viet)/.test(t)) return 'cross'; // synthesis handled below
    return null;
}

// Drive the animated phase tracker (no terminal). Maps a backend progress message
// to a phase, lights it up, marks earlier phases done, advances the progress bar.
function updateResearchConsole(text) {
    const statusEl = document.getElementById('rgpStatus');
    if (statusEl && text) {
        statusEl.style.opacity = '0';
        setTimeout(() => { statusEl.textContent = text; statusEl.style.opacity = '1'; }, 120);
    }
    let phase = _rgpPhaseFor(text);
    const t = (text || '').toLowerCase();
    if (/(tổng hợp|tong hop|synth|báo cáo|bao cao|hoàn thi|hoan thi|viết|viet)/.test(t)) phase = 'synth';
    if (!phase) return;
    const idx = RGP_PHASES.indexOf(phase);
    document.querySelectorAll('.rgp-phase').forEach((el2) => {
        const p = el2.getAttribute('data-phase');
        const pi = RGP_PHASES.indexOf(p);
        el2.classList.toggle('active', pi === idx);
        el2.classList.toggle('done', pi < idx);
    });
    const bar = document.getElementById('neuralProgressBar');
    if (bar) bar.style.width = Math.min(95, 15 + idx * 25 + 10) + '%';
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

function stripControlChars(value) {
    return String(value ?? '').replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');
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

function repairText(value) {
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
        if (cleanedCandidate && score < bestScore) {
            best = cleanedCandidate;
            bestScore = score;
        }
    });

    return best;
}

function repairData(value) {
    if (Array.isArray(value)) return value.map((item) => repairData(item));
    if (value && typeof value === 'object') {
        return Object.fromEntries(
            Object.entries(value).map(([key, item]) => [key, repairData(item)])
        );
    }
    return repairText(value);
}

function getConfiguredLanguage() {
    const stored = String(localStorage.getItem('skemi_language') || '').trim().toLowerCase();
    if (stored === 'vi' || stored === 'en') return stored;
    const managerLanguage = String(window.languageManager?.base || window.languageManager?.currentLanguage || '').trim().toLowerCase();
    if (managerLanguage === 'vi' || managerLanguage === 'en') return managerLanguage;
    return 'en';
}

const lang = () => {
    const explicit = String(state.lang || '').trim().toLowerCase();
    if (explicit === 'vi' || explicit === 'en') return explicit;
    return getConfiguredLanguage();
};
const t = () => repairData(TEXT[lang()]);
const format = (template, params = {}) => repairText(String(template).replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? '')));
const escapeHtml = (value) => String(value || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
const normalized = (value) => String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const showToast = (message, type = 'info') => (typeof window.showToast === 'function' ? window.showToast(message, type) : (function(){})(`[${type}] ${message}`));

function uniqueTokensFromQuery(query) {
    return [...new Set(
        String(query || '')
            .split(/[^0-9A-Za-z\u00C0-\u1EF9]+/u)
            .map((item) => repairText(item).trim())
            .filter((item) => item.length >= 3)
    )].slice(0, 8);
}

function fallbackSearchActions(uiLanguage = lang()) {
    if (uiLanguage === 'vi') {
        return [
            { id: 'open-computer', label: 'Chạy bằng Computer', kind: 'computer' },
            { id: 'brief-to-studio', label: 'Đẩy vào Studio', kind: 'studio' },
            { id: 'deepen-search', label: 'Đào sâu thêm', kind: 'search' }
        ];
    }
    return [
        { id: 'open-computer', label: 'Run with Computer', kind: 'computer' },
        { id: 'brief-to-studio', label: 'Send to Studio', kind: 'studio' },
        { id: 'deepen-search', label: 'Go deeper', kind: 'search' }
    ];
}

function fallbackSearchTracks(uiLanguage = lang()) {
    return uiLanguage === 'vi'
        ? [
            { key: 'study', icon: '🎯', label: 'Học tập', title: 'Tổ chức kiến thức nhanh', description: 'Tách chủ đề thành các ý chính, sau đó mở rộng bằng chi tiết, ví dụ và điểm cần nhớ.' },
            { key: 'research', icon: '🧠', label: 'Nghiên cứu', title: 'Xác định phần cần kiểm chứng', description: 'Đánh dấu các điểm đã có nguồn, phần còn thiếu dữ liệu và câu hỏi cần làm rõ thêm.' },
            { key: 'work', icon: '🛠️', label: 'Làm việc', title: 'Biến kết quả thành bước làm', description: 'Chuyển brief thành checklist, bước triển khai và đầu việc tiếp theo.' },
            { key: 'next', icon: '🚀', label: 'Tiếp theo', title: 'Đẩy sang Studio', description: 'Dùng kết quả này để tạo mindmap, report, flashcard hoặc notebook flow.' }
        ]
        : [
            { key: 'study', icon: '🎯', label: 'Study', title: 'Organize knowledge fast', description: 'Break the topic into core ideas, then expand with details, examples, and memory anchors.' },
            { key: 'research', icon: '🧠', label: 'Research', title: 'Mark what still needs proof', description: 'Separate confirmed points, weak evidence, and questions that still need verification.' },
            { key: 'work', icon: '🛠️', label: 'Work', title: 'Turn the result into action', description: 'Translate the brief into steps, checklists, and practical next moves.' },
            { key: 'next', icon: '🚀', label: 'Next', title: 'Push it into Studio', description: 'Use the result to create a mindmap, report, flashcards, or a notebook workflow.' }
        ];
}

function fallbackSearchOutputs(displayQuery, uiLanguage = lang()) {
    if (uiLanguage === 'vi') {
        return [
            {
                type: 'mindmap',
                mode: 'study',
                title: `Mindmap: ${displayQuery}`,
                summary: `Dựng mindmap cho "${displayQuery}" với các ý chính, nhánh mở rộng và ví dụ ngắn.`,
                prompt: `Tạo mindmap cho "${displayQuery}".\n- Bắt đầu từ ý chính.\n- Tách thành các nhánh con rõ ràng.\n- Thêm ví dụ hoặc tín hiệu cần nhớ.`
            },
            {
                type: 'report',
                mode: 'research',
                title: `Báo cáo: ${displayQuery}`,
                summary: `Viết brief có cấu trúc cho "${displayQuery}" với điểm đã xác minh, điểm còn mơ hồ và bước tiếp theo.`,
                prompt: `Viết báo cáo ngắn cho "${displayQuery}".\n- Tóm tắt điểm đã xác minh.\n- Đánh dấu phần chưa rõ.\n- Đề xuất hướng nghiên cứu tiếp theo.`
            },
            {
                type: 'flashcard',
                mode: 'study',
                title: `Flashcard: ${displayQuery}`,
                summary: `Tạo bộ flashcard cho "${displayQuery}" để ôn nhanh và ghi nhớ dài hơn.`,
                prompt: `Tạo bộ flashcard cho "${displayQuery}".\n- Chia theo khái niệm, ví dụ, câu hỏi ôn tập.\n- Mỗi thẻ ngắn và rõ.`
            }
        ];
    }
    return [
        {
            type: 'mindmap',
            mode: 'study',
            title: `Mindmap: ${displayQuery}`,
            summary: `Create a mindmap for "${displayQuery}" with core branches, supporting details, and examples.`,
            prompt: `Create a mindmap for "${displayQuery}".\n- Start from the core idea.\n- Split into clear branches.\n- Add examples or memory anchors.`
        },
        {
            type: 'report',
            mode: 'research',
            title: `Report: ${displayQuery}`,
            summary: `Write a structured brief for "${displayQuery}" with verified points, unclear areas, and next questions.`,
            prompt: `Write a short report for "${displayQuery}".\n- Summarize verified points.\n- Mark unclear areas.\n- Propose follow-up research.`
        },
        {
            type: 'flashcard',
            mode: 'study',
            title: `Flashcards: ${displayQuery}`,
            summary: `Build a flashcard pack for "${displayQuery}" for fast review and long-term retention.`,
            prompt: `Create flashcards for "${displayQuery}".\n- Split by concept, example, and review question.\n- Keep each card concise and clear.`
        }
    ];
}

function fallbackSearchCreative(displayQuery, uiLanguage = lang()) {
    return uiLanguage === 'vi'
        ? [
            {
                title: 'Góc phản biện',
                summary: `Viết một brief phản biện cho "${displayQuery}" để lộ ra điểm mù và giả định ẩn.`,
                prompt: `Viết brief phản biện cho "${displayQuery}".\n- Chỉ ra giả định ẩn.\n- Nêu rủi ro nếu kết luận quá sớm.\n- Đề xuất 3 câu hỏi cần kiểm chứng.`,
                type: 'report'
            },
            {
                title: 'Decision map',
                summary: `Biến "${displayQuery}" thành bản đồ quyết định để chọn hướng học, nghiên cứu hoặc triển khai.`,
                prompt: `Tạo decision map cho "${displayQuery}".\n- Chia theo học tập, nghiên cứu và triển khai.\n- Mỗi nhánh có tín hiệu để chọn hoặc bỏ.`,
                type: 'mindmap'
            }
        ]
        : [
            {
                title: 'Counter-position brief',
                summary: `Write a counter-position brief for "${displayQuery}" to surface blind spots and hidden assumptions.`,
                prompt: `Write a counter-position brief for "${displayQuery}".\n- Surface hidden assumptions.\n- Highlight risks of premature conclusions.\n- End with 3 verification questions.`,
                type: 'report'
            },
            {
                title: 'Decision map',
                summary: `Turn "${displayQuery}" into a decision map for study, research, or execution.`,
                prompt: `Create a decision map for "${displayQuery}".\n- Split by study, research, and execution goals.\n- Add signals for when to choose or reject each path.`,
                type: 'mindmap'
            }
        ];
}

function sanitizeSearchText(value) {
    return repairText(String(value || ''))
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/[|]+/g, ' ')
        .replace(/(?:\s*-\s*){3,}/g, '. ')
        .replace(/[*_`#>~]+/g, ' ')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

function looksLikeLatestModelQuery(displayQuery = '') {
    const query = normalized(displayQuery || '');
    if (!query) return false;
    const latestMarkers = ['latest', 'newest', 'current', 'moi nhat', 'mới nhất', 'hien tai', 'hiện tại', 'release', 'version', 'phien ban', 'phiên bản', 'cap nhat', 'cập nhật'];
    const modelMarkers = ['model', 'models', 'mo hinh', 'mô hình', 'chatgpt', 'claude', 'gemini', 'grok', 'minimax', 'qwen', 'gpt'];
    return latestMarkers.some((marker) => query.includes(normalized(marker))) && modelMarkers.some((marker) => query.includes(normalized(marker)));
}

function buildDynamicTracksFallback(displayQuery, uiLanguage = lang()) {
    const query = sanitizeSearchText(displayQuery || '');
    const latestQuery = looksLikeLatestModelQuery(query);
    if (latestQuery && uiLanguage === 'vi') {
        return [
            { key: 'overview', icon: '🧭', label: 'Toàn cảnh', title: `Toàn cảnh hiện tại của ${query}`, description: `Skemi sẽ gom phần cập nhật mới nhất của ${query} thành một bức tranh ngắn gọn, ưu tiên tên phiên bản, điểm mới và mốc thời gian đang nổi bật.` },
            { key: 'highlights', icon: '✨', label: 'Nổi bật', title: 'Những chi tiết nổi bật nên đọc trước', description: `Tập trung vào các mô tả cụ thể nhất như tên model, thay đổi chính, khả năng mới và phần đang được nhắc nhiều nhất quanh ${query}.` },
            { key: 'changes', icon: '🔄', label: 'Thay đổi', title: 'Các thay đổi hoặc nhánh mới đáng chú ý', description: `Tách riêng phần nào là bản mới, phần nào là nhánh khác, và phần nào là thay đổi so với giai đoạn trước để tránh đọc dồn vào một đoạn.` },
            { key: 'timeline', icon: '🚀', label: 'Nhịp cập nhật', title: 'Mốc thời gian và hướng đọc tiếp', description: `Giữ mốc cập nhật gần nhất của ${query} và mở tiếp theo hướng thay đổi mới, khác biệt với bản trước, hoặc ứng dụng thực tế.` }
        ];
    }
    if (latestQuery) {
        return [
            { key: 'overview', icon: '🧭', label: 'Overview', title: `Current overview for ${query}`, description: `Skemi compresses the newest ${query} update layer into a short read focused on model names, major changes, and the freshest timing.` },
            { key: 'highlights', icon: '✨', label: 'Highlights', title: 'Details worth reading first', description: `Focus on the clearest concrete descriptions around ${query}, especially model naming, key capability shifts, and the points repeated across the newest material.` },
            { key: 'changes', icon: '🔄', label: 'Changes', title: 'What new branches or changes are showing up', description: `Separate the newer branch, the previous phase, and the difference between them so the topic does not collapse into one vague summary.` },
            { key: 'timeline', icon: '🚀', label: 'Timeline', title: 'Timing and next reading direction', description: `Keep the freshest update timing for ${query}, then continue with what changed, what differs from the previous version, or how the model is being used.` }
        ];
    }
    return uiLanguage === 'vi'
        ? [
            { key: 'focus', icon: '🧭', label: 'Trọng tâm', title: `Điểm chính về ${query}`, description: `Tóm nhanh phần cốt lõi nhất đang bám trực tiếp vào ${query}.` },
            { key: 'details', icon: '✨', label: 'Chi tiết', title: 'Các chi tiết nổi bật nên đọc trước', description: `Tách riêng những ý cụ thể nhất của ${query} để bạn nắm nhanh thay vì đọc một khối dài.` },
            { key: 'angles', icon: '🧩', label: 'Góc nhìn', title: 'Các nhánh nên tách ra để hiểu rõ hơn', description: `Mở ${query} theo từng nhánh như bối cảnh, điểm mới, ứng dụng và phần dễ nhầm để nội dung không bị dồn cục.` },
            { key: 'next', icon: '🚀', label: 'Tiếp tục', title: 'Nên đào sâu tiếp theo hướng nào', description: `Đi tiếp theo hướng thay đổi mới, khác biệt với giai đoạn trước hoặc ứng dụng thực tế của ${query}.` }
        ]
        : [
            { key: 'focus', icon: '🧭', label: 'Focus', title: `Core takeaway about ${query}`, description: `A quick read on the most direct point tied to ${query}.` },
            { key: 'details', icon: '✨', label: 'Details', title: 'Details worth reading first', description: `Pull out the clearest concrete details around ${query} so the answer does not collapse into a generic paragraph.` },
            { key: 'angles', icon: '🧩', label: 'Angles', title: 'Which branches should be separated', description: `Break ${query} into context, new details, practical use, and confusing side branches to keep the topic readable.` },
            { key: 'next', icon: '🚀', label: 'Next', title: 'Where to go deeper next', description: `Continue with what changed most recently, what differs from the previous phase, or how ${query} is applied in practice.` }
        ];
}

function setDiscoveryVisibility(showDiscovery) {
    if (el.trendingSection) {
        el.trendingSection.style.display = showDiscovery ? '' : 'none';
    }
    if (el.statsBar) {
        el.statsBar.style.display = showDiscovery ? '' : 'none';
    }
}

function buildFollowUpsFallback(displayQuery, uiLanguage = lang()) {
    const query = sanitizeSearchText(displayQuery || '');
    return uiLanguage === 'vi'
        ? [
            `Điểm mới nhất đã được xác thực về ${query} là gì`,
            `Nguồn chính thức nào nói rõ nhất về ${query}`,
            `${query} khác gì so với giai đoạn trước`,
            `Phần nào của ${query} vẫn còn thiếu xác nhận`
        ]
        : [
            `What is the latest verified update about ${query}`,
            `Which official source explains ${query} most clearly`,
            `How does ${query} differ from the previous phase`,
            `What about ${query} still lacks verification`
        ];
}

function buildVerificationFallback(uiLanguage = lang()) {
    return uiLanguage === 'vi'
        ? [
            'Ưu tiên nguồn chính thức hoặc tài liệu kỹ thuật trước bài viết tổng hợp lại.',
            'So ngày xuất bản để chắc rằng thông tin mới đã thay phần cũ.',
            'Giữ riêng các ý đã xác thực và các ý mới chỉ được nhắc tới.',
            'Nếu truy vấn hỏi bản mới nhất, bỏ các chi tiết lịch sử không còn tác dụng.'
        ]
        : [
            'Prioritize official or technical sources before secondary roundups.',
            'Compare publication dates so the newer evidence truly replaces older claims.',
            'Separate verified points from claims that are only mentioned once.',
            'If the query asks for the latest answer, remove historical details that no longer matter.'
        ];
}

function buildDecisionPathsFallback(displayQuery, uiLanguage = lang()) {
    const query = sanitizeSearchText(displayQuery || '');
    return uiLanguage === 'vi'
        ? [
            { title: 'Đào sâu tiếp', description: `Mở một lượt tra cứu tiếp theo để kiểm tra phần nguồn chính thức của ${query}.`, action: 'follow-up', query: `nguồn chính thức mới nhất về ${query}` },
            { title: 'Biến thành mindmap', description: `Chuyển phần đã xác thực của ${query} thành sơ đồ ý trong Studio.`, action: 'studio', type: 'mindmap' },
            { title: 'Lập checklist', description: `Tạo checklist để tách phần mới, phần cũ và phần còn cần kiểm chứng của ${query}.`, action: 'copy' }
        ]
        : [
            { title: 'Go deeper', description: `Open one more search pass focused on official evidence for ${query}.`, action: 'follow-up', query: `latest official source about ${query}` },
            { title: 'Turn it into a mindmap', description: `Convert the verified part of ${query} into a visual map in Studio.`, action: 'studio', type: 'mindmap' },
            { title: 'Build a checklist', description: `Create a checklist that separates new, old, and still-unverified points about ${query}.`, action: 'copy' }
        ];
}

function buildGenericAnalysisFallback(rawQuery, displayQuery, uiLanguage = lang()) {
    const visibleQuery = repairText(displayQuery || rawQuery || '');
    const raw = repairText(rawQuery || displayQuery || '');
    return {
        raw_query: raw,
        query: visibleQuery,
        display_query: visibleQuery,
        language: uiLanguage,
        freshness_mode: 'standard',
        brief: '',
        answer: '',
        headline: visibleQuery,
        status_line: '',
        keywords: uniqueTokensFromQuery(visibleQuery),
        tracks: buildDynamicTracksFallback(visibleQuery, uiLanguage),
        actions: fallbackSearchActions(uiLanguage),
        outputs: fallbackSearchOutputs(visibleQuery, uiLanguage),
        creative: fallbackSearchCreative(visibleQuery, uiLanguage),
        follow_ups: buildFollowUpsFallback(visibleQuery, uiLanguage),
        verification_checks: buildVerificationFallback(uiLanguage),
        decision_paths: buildDecisionPathsFallback(visibleQuery, uiLanguage),
        sources: []
    };
}

function emitWorkflowEvent(name, detail = {}) {
    const payload = repairData({
        targetPage: 'search',
        timestamp: Date.now(),
        ...detail
    });
    window.dispatchEvent(new CustomEvent(`skemi:workflow-${name}`, { detail: payload }));
}

function typeIntoInput(input, text, options = {}) {
    if (!input) return Promise.resolve();
    const value = String(text ?? '');
    const interval = Math.max(12, Number(options.intervalMs || 22));
    const clear = options.clear !== false;
    if (clear) input.value = '';
    input.focus();
    return new Promise((resolve) => {
        let idx = 0;
        const timer = window.setInterval(() => {
            idx += 1;
            input.value = value.slice(0, idx);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            if (idx >= value.length) {
                window.clearInterval(timer);
                resolve();
            }
        }, interval);
    });
}

function isReloadNavigation() {
    try {
        const nav = performance.getEntriesByType('navigation')[0];
        if (nav && nav.type) return nav.type === 'reload';
        if (performance.navigation) return performance.navigation.type === 1;
    } catch {}
    return false;
}
function persistState() {
    if (!searchStorage) return;
    state.stateUpdatedAt = Date.now();
    searchStorage.setItem(SEARCH_STATE_KEY, JSON.stringify({
        query: state.query,
        rawQuery: state.rawQuery,
        category: state.category,
        time: state.time,
        sort: state.sort,
        lang: state.lang,
        activeJobId: state.activeJobId,
        requestKey: state.requestKey,
        jobStatus: state.jobStatus,
        updatedAt: state.stateUpdatedAt
    }));
}

function persistActiveJob() {
    if (!searchStorage) return;
    if (!state.activeJobId) {
        searchStorage.removeItem(SEARCH_ACTIVE_JOB_KEY);
        return;
    }
    searchStorage.setItem(SEARCH_ACTIVE_JOB_KEY, JSON.stringify({
        jobId: state.activeJobId,
        requestKey: state.requestKey,
        query: state.query,
        rawQuery: state.rawQuery,
        status: state.jobStatus,
        savedAt: Date.now()
    }));
}

function persistAnalysis(analysis) {
    if (!searchStorage) return;
    if (!analysis) {
        searchStorage.removeItem(SEARCH_ANALYSIS_KEY);
        return;
    }
    const normalizedAnalysis = normalizeAnalysisPayload(
        analysis,
        state.rawQuery || analysis?.raw_query || analysis?.query || '',
        state.query || analysis?.display_query || analysis?.query || ''
    );
    searchStorage.setItem(SEARCH_ANALYSIS_KEY, JSON.stringify({
        query: state.query,
        rawQuery: state.rawQuery,
        analysis: normalizedAnalysis,
        savedAt: Date.now()
    }));
}

function restoreState() {
    try {
        if (!searchStorage) return;
        const saved = JSON.parse(searchStorage.getItem(SEARCH_STATE_KEY) || 'null');
        if (!saved) return;
        state.query = saved.query || '';
        state.rawQuery = saved.rawQuery || saved.query || '';
        state.category = saved.category || '';
        state.time = saved.time || '';
        state.sort = saved.sort || 'relevance';
        state.lang = saved.lang || '';
        state.activeJobId = saved.activeJobId || '';
        state.requestKey = saved.requestKey || '';
        state.jobStatus = saved.jobStatus || '';
        state.stateUpdatedAt = Number(saved.updatedAt || 0) || 0;
    } catch {
        searchStorage?.removeItem(SEARCH_STATE_KEY);
    }
}

function restoreActiveJob() {
    try {
        if (!searchStorage) return;
        const saved = JSON.parse(searchStorage.getItem(SEARCH_ACTIVE_JOB_KEY) || 'null');
        if (!saved) return;
        if (!state.activeJobId) state.activeJobId = saved.jobId || '';
        if (!state.requestKey) state.requestKey = saved.requestKey || '';
        if (!state.query) state.query = saved.query || '';
        if (!state.rawQuery) state.rawQuery = saved.rawQuery || saved.query || '';
        if (!state.jobStatus) state.jobStatus = saved.status || '';
    } catch {
        searchStorage?.removeItem(SEARCH_ACTIVE_JOB_KEY);
    }
}

function restoreAnalysis() {
    try {
        if (!searchStorage) return;
        const saved = JSON.parse(searchStorage.getItem(SEARCH_ANALYSIS_KEY) || 'null');
        if (!saved || !saved.analysis) return;
        if (!state.query) {
            state.query = saved.query || '';
        }
        if (!state.rawQuery) {
            state.rawQuery = saved.rawQuery || saved.query || '';
        }
        if (state.query && saved.query && saved.query !== state.query) return;
        state.analysis = normalizeAnalysisPayload(
            saved.analysis,
            state.rawQuery || saved.rawQuery || saved.query || '',
            state.query || saved.query || ''
        );
        if (!state.requestKey) {
            state.requestKey = repairText(saved.analysis?.search_meta?.request_key || '');
        }
        if (!state.jobStatus && state.analysis) {
            state.jobStatus = 'completed';
        }
        state.stateUpdatedAt = Math.max(state.stateUpdatedAt || 0, Number(saved.savedAt || 0) || 0);
    } catch {
        searchStorage?.removeItem(SEARCH_ANALYSIS_KEY);
    }
}

function buildBriefFallbackText(analysis) {
    const lines = [];
    const statusLine = sanitizeSearchText(analysis?.status_line || '');
    if (statusLine) lines.push(statusLine);
    const tracks = Array.isArray(analysis?.tracks) ? analysis.tracks : [];
    tracks.slice(0, 2).forEach((track) => {
        const text = sanitizeSearchText(track?.description || '');
        if (text) lines.push(text);
    });
    return lines.filter(Boolean).join(' ');
}

function compactBriefText(text, maxLength = 360) {
    const clean = sanitizeSearchText(text || '');
    if (!clean) return '';
    if (clean.length <= maxLength) return clean;
    const sliced = clean.slice(0, maxLength);
    return `${sliced.slice(0, sliced.lastIndexOf(' ') > 120 ? sliced.lastIndexOf(' ') : maxLength).trim()}...`;
}

function extractLatestSubjects(analysis) {
    const subjects = analysis?.search_meta?.latest_subjects;
    return Array.isArray(subjects)
        ? subjects.map((item) => sanitizeSearchText(item)).filter(Boolean)
        : [];
}

function buildOfficialDrilldownQuery(analysis) {
    const subjects = extractLatestSubjects(analysis);
    const anchor = subjects.length ? subjects.join(', ') : sanitizeSearchText(analysis?.display_query || analysis?.query || state.query || '');
    if (!anchor) return '';
    return lang() === 'vi'
        ? `nguồn chính thức mới nhất về ${anchor}`
        : `latest official source about ${anchor}`;
}

function buildDeepenQuery(analysis) {
    const followUp = Array.isArray(analysis?.follow_ups)
        ? sanitizeSearchText(analysis.follow_ups.find((item) => sanitizeSearchText(item)))
        : '';
    if (followUp) return followUp;
    return buildOfficialDrilldownQuery(analysis);
}

function buildComparePreviousQuery(analysis) {
    const subjects = extractLatestSubjects(analysis);
    const anchor = subjects.length ? subjects.join(', ') : sanitizeSearchText(analysis?.display_query || analysis?.query || state.query || '');
    if (!anchor) return '';
    return lang() === 'vi'
        ? `${anchor} khác gì so với bản trước`
        : `${anchor} versus the previous version`;
}

function buildUncertaintyQuery(analysis) {
    const anchor = sanitizeSearchText(analysis?.display_query || analysis?.query || state.query || '');
    if (!anchor) return '';
    return lang() === 'vi'
        ? `điểm nào của ${anchor} vẫn chưa được xác nhận rõ`
        : `what about ${anchor} is still not clearly confirmed`;
}

function clearCompletedSearchPersistence() {
    state.analysis = null;
    state.activeJobId = '';
    state.requestKey = '';
    state.jobStatus = '';
    persistState();
    persistActiveJob();
    persistAnalysis(null);
}

function categoryLabel(category) {
    return category ? (t().categoryLabels[category] || category) : t().chips[0];
}

function setCompact(enabled) {
    el.hero?.classList.toggle('compact', enabled);
}

function setChipState() {
    el.chips.forEach((chip) => chip.classList.toggle('active', (chip.dataset.category || '') === state.category));
}

function updateStats() {
    const labels = document.querySelectorAll('.stats-bar .stat-label');
    labels.forEach((node, index) => {
        if (t().stats[index]) node.textContent = t().stats[index];
    });
    if (el.statArticles) el.statArticles.textContent = String(SAMPLE_QUERIES[lang()].length).padStart(2, '0');
    if (el.statSources) el.statSources.textContent = '04';
    if (el.statDbSize) el.statDbSize.textContent = '03';
    if (el.statLastUpdate) el.statLastUpdate.textContent = t().updated;
}

function applyStaticText() {
    document.title = t().title;
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.content = t().metaDescription;
    const title = document.querySelector('.hero-title .text-gradient');
    if (title) title.textContent = t().title;
    const subtitle = document.querySelector('.hero-subtitle');
    if (subtitle) subtitle.textContent = t().subtitle;
    if (el.searchInput) el.searchInput.placeholder = t().placeholder;
    if (el.searchBtn) el.searchBtn.textContent = t().button;
    el.chips.forEach((chip, index) => {
        if (t().chips[index]) chip.textContent = t().chips[index];
    });
    if (el.briefEyebrow) el.briefEyebrow.textContent = t().briefEyebrow;
    if (el.keywordTitle) el.keywordTitle.textContent = t().keywordTitle;
    if (el.keywordDescription) el.keywordDescription.textContent = t().keywordDescription;
    if (el.trendingTitle) el.trendingTitle.textContent = t().sampleTitle;

    const timeValues = ['', '1h', '24h', '7d', '30d'];
    timeValues.forEach((value, index) => {
        const option = el.timeFilter?.querySelector(`option[value="${value}"]`);
        if (option) option.textContent = t().filters.time[index];
    });
    const relevance = el.sortFilter?.querySelector('option[value="relevance"]');
    const newest = el.sortFilter?.querySelector('option[value="date"]');
    if (relevance) relevance.textContent = t().filters.sort[0];
    if (newest) newest.textContent = t().filters.sort[1];
    const langAll = el.langFilter?.querySelector('option[value=""]');
    const langVi = el.langFilter?.querySelector('option[value="vi"]');
    const langEn = el.langFilter?.querySelector('option[value="en"]');
    if (langAll) langAll.textContent = t().filters.lang[0];
    if (langVi) langVi.textContent = t().filters.lang[1];
    if (langEn) langEn.textContent = t().filters.lang[2];
    if (el.resultsQueryWrap) {
        // Legacy/hidden node: keep the strong slot but never render a literal
        // "for" / "cho" prefix (caused a stray `for ""` to flash on screen).
        el.resultsQueryWrap.classList.add('hidden');
        if (!el.resultsQuery) {
            el.resultsQueryWrap.innerHTML = '<strong id="resultsQuery"></strong>';
            el.resultsQuery = document.getElementById('resultsQuery');
        }
    }
    updateStats();
}

function inferCategory(query) {
    if (state.category) return state.category;
    const q = normalized(query);
    const rules = [
        ['education', /(hoc|on tap|bai hoc|lop|exam|study|lesson|school|review)/],
        ['tech', /(ai|agent|lap trinh|code|cong nghe|software|programming|developer|technology)/],
        ['business', /(kinh doanh|marketing|ban hang|onboarding|van hanh|tai chinh|business|sales|operations|finance)/],
        ['health', /(suc khoe|dinh duong|thuoc|benh|health|nutrition|wellness|medical|senior)/],
        ['science', /(nghien cuu|thi nghiem|du lieu|khoa hoc|research|science|experiment|dataset)/],
        ['world', /(chuyen doi so|chinh sach|xa hoi|the gioi|context|policy|society|global)/],
        ['sports', /(thuc hanh|kế hoạch|routine|practice|exercise|workout)/],
        ['entertainment', /(sang tao|noi dung|creative|content|media|design)/]
    ];
    const hit = rules.find(([, regex]) => regex.test(q));
    return hit ? hit[0] : 'general';
}

function buildKeywords(query, category) {
    const prefix = categoryLabel(category);
    const raw = lang() === 'vi'
        ? [query, `${query} mindmap`, `${query} câu hỏi trọng tâm`, `${query} ví dụ minh họa`, `${query} lộ trình học`, `${query} checklist thực hành`, `${prefix} ${query}`, `${query} tóm tắt nhanh`]
        : [query, `${query} mindmap`, `${query} core questions`, `${query} worked examples`, `${query} learning roadmap`, `${query} execution checklist`, `${prefix} ${query}`, `${query} quick summary`];
    const seen = new Set();
    return raw.filter((item) => {
        const key = normalized(item);
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
    }).slice(0, 8);
}

function recommendedTypes(category) {
    const map = {
        education: ['mindmap', 'flashcard', 'quiztest', 'report'],
        tech: ['dashboard', 'report', 'presentation', 'video'],
        business: ['dashboard', 'presentation', 'report', 'podcast'],
        science: ['report', 'chart', 'dashboard', 'presentation'],
        health: ['mindmap', 'flashcard', 'podcast', 'report'],
        world: ['report', 'podcast', 'dashboard', 'video'],
        sports: ['presentation', 'flashcard', 'quiztest', 'infographic'],
        entertainment: ['video', 'podcast', 'infographic', 'presentation'],
        general: ['mindmap', 'report', 'presentation', 'podcast']
    };
    return map[category] || map.general;
}

function outputMode(type) {
    return ({
        mindmap: 'study',
        flashcard: 'study',
        quiztest: 'study',
        report: 'research',
        presentation: 'work',
        infographic: 'work',
        chart: 'synthesis',
        dashboard: 'synthesis',
        podcast: 'work',
        video: 'work'
    })[type] || 'synthesis';
}

function typeLabel(type) {
    const builtIn = t().types?.[type];
    if (builtIn) return builtIn;
    const fallback = lang() === 'vi'
        ? { dashboard: 'Dashboard', podcast: 'Podcast duel', video: 'Video AI', quiztest: 'AI test' }
        : { dashboard: 'Dashboard', podcast: 'Podcast duel', video: 'AI video', quiztest: 'AI test' };
    return fallback[type] || type;
}

function buildPrompt(type, query, category) {
    const categoryText = categoryLabel(category);
    if (lang() === 'vi') {
        const prompts = {
            mindmap: `Tạo mindmap cho chủ đề "${query}".\n- Hiển thị các ý chính trước, sau đó bung nhánh chi tiết.\n- Tách rõ nền tảng, ứng dụng và điểm cần ghi nhớ.\n- Danh mục trọng tâm: ${categoryText}.`,
            flashcard: `Tạo bộ flashcard cho chủ đề "${query}".\n- Chia thẻ theo khái niệm, ví dụ và câu hỏi ôn tập.\n- Mỗi thẻ ngắn, rõ, có đáp án súc tích.\n- Danh mục trọng tâm: ${categoryText}.`,
            report: `Viết báo cáo có cấu trúc cho chủ đề "${query}".\n- Tóm tắt bối cảnh, ý chính, ví dụ và phần còn thiếu nguồn.\n- Giữ bố cục rõ, dùng được cho học tập hoặc nghiên cứu.\n- Danh mục trọng tâm: ${categoryText}.`,
            presentation: `Tạo bảng trình bày cho chủ đề "${query}".\n- Chia thành các slide hoặc khối ý rõ ràng.\n- Nhấn mạnh ý chính, ví dụ, số liệu và hành động tiếp theo.\n- Danh mục trọng tâm: ${categoryText}.`,
            infographic: `Tạo bảng đồ họa cho chủ đề "${query}".\n- Tách thông tin thành khối trực quan, ít chữ, rõ điểm nhấn.\n- Có tổng quan, ý quan trọng và ứng dụng thực tế.\n- Danh mục trọng tâm: ${categoryText}.`,
            chart: `Tạo cấu trúc biểu đồ cho chủ đề "${query}".\n- Đề xuất loại biểu đồ phù hợp và dữ liệu cần có.\n- Nếu thiếu dữ liệu, nêu rõ cần bổ sung gì.\n- Danh mục trọng tâm: ${categoryText}.`,
            dashboard: `Tạo dashboard điều hành cho "${query}".\n- Có KPI chính, chỉ số rủi ro và ưu tiên hành động.\n- Bố cục để đọc nhanh trong 30 giây.\n- Danh mục trọng tâm: ${categoryText}.`,
            podcast: `Tạo podcast duel cho "${query}".\n- 2 vai AI tranh luận trái chiều dựa trên cùng dữ liệu.\n- Có phần kết luận và hành động đề xuất.\n- Danh mục trọng tâm: ${categoryText}.`,
            video: `Tạo kịch bản video AI trình bày cho "${query}".\n- Chia timeline theo cảnh, script và nhấn ý chính.\n- Có mở đầu, ví dụ, kết luận hành động.\n- Danh mục trọng tâm: ${categoryText}.`,
            quiztest: `Tạo bài AI test cho "${query}".\n- Sinh câu hỏi theo mức độ hiểu sai thường gặp.\n- Mỗi câu có 4 lựa chọn và giải thích ngắn.\n- Danh mục trọng tâm: ${categoryText}.`
        };
        return prompts[type];
    }

    const prompts = {
        mindmap: `Create a mindmap for "${query}".\n- Show the main ideas first, then expand into detailed branches.\n- Separate foundations, applications, and memory anchors.\n- Priority category: ${categoryText}.`,
        flashcard: `Create a flashcard set for "${query}".\n- Split cards into concepts, examples, and review questions.\n- Keep each card short, clear, and answer-focused.\n- Priority category: ${categoryText}.`,
        report: `Write a structured report for "${query}".\n- Summarize context, core ideas, examples, and missing-source gaps.\n- Keep the layout useful for study or research.\n- Priority category: ${categoryText}.`,
        presentation: `Create a presentation structure for "${query}".\n- Break it into clear slides or content blocks.\n- Highlight main ideas, examples, metrics, and next actions.\n- Priority category: ${categoryText}.`,
        infographic: `Create an infographic structure for "${query}".\n- Turn the information into visual blocks with clear highlights.\n- Include overview, key points, and practical use.\n- Priority category: ${categoryText}.`,
        chart: `Create a chart structure for "${query}".\n- Recommend the best chart type and the data needed.\n- If data is missing, explicitly list what is required.\n- Priority category: ${categoryText}.`,
        dashboard: `Create an operational dashboard for "${query}".\n- Include core KPIs, risk indicators, and execution priorities.\n- Keep the layout scannable within 30 seconds.\n- Priority category: ${categoryText}.`,
        podcast: `Create a podcast duel for "${query}".\n- Two AI hosts debate opposing views using the same source base.\n- End with practical takeaways and actions.\n- Priority category: ${categoryText}.`,
        video: `Create an AI presentation video script for "${query}".\n- Split into scenes, script lines, and visual focus points.\n- Include opener, examples, and action-oriented closing.\n- Priority category: ${categoryText}.`,
        quiztest: `Create an AI test for "${query}".\n- Generate questions based on common misunderstanding points.\n- Each item includes four options and short explanations.\n- Priority category: ${categoryText}.`
    };
    return prompts[type];
}

function buildCreativeBursts(query, category) {
    const categoryText = categoryLabel(category);
    if (lang() === 'vi') {
        return [
            {
                title: 'Sản phẩm mini 7 ngày',
                summary: `Thiết kế một sản phẩm thử nghiệm liên quan "${query}" trong 7 ngày với mục tiêu đo kết quả rõ ràng.`,
                prompt: `Tạo kế hoạch 7 ngày để xây một sản phẩm mini về "${query}" (${categoryText}).\n- Mục tiêu kinh doanh/học tập\n- Danh sách tính năng tối thiểu\n- KPI theo ngày\n- Rủi ro và phương án xử lý`,
                type: 'presentation'
            },
            {
                title: 'Chiến dịch nội dung 3 lớp',
                summary: `Biến chủ đề "${query}" thành chuỗi nội dung gồm cấp cơ bản, nâng cao và ứng dụng thực chiến.`,
                prompt: `Xây chiến dịch nội dung 3 lớp cho "${query}" (${categoryText}).\n- Lớp 1: giải thích nền tảng\n- Lớp 2: phân tích chuyên sâu\n- Lớp 3: tình huống ứng dụng\n- Lịch đăng và tiêu chí đo hiệu quả`,
                type: 'report'
            },
            {
                title: 'Lab thử nghiệm đột phá',
                summary: `Tạo bộ giả thuyết và 5 thử nghiệm nhanh để khám phá hướng đi mới cho "${query}".`,
                prompt: `Thiết kế "Creative Lab" cho "${query}" (${categoryText}).\n- 5 giả thuyết sáng tạo\n- 5 thử nghiệm nhanh chi phí thấp\n- Tiêu chí chọn thử nghiệm ưu tiên\n- Cách tổng hợp bài học sau thử nghiệm`,
                type: 'mindmap'
            },
            {
                title: 'Arena kiểm tra tư duy',
                summary: `Tạo một bài AI test theo phong cách Arena để đo độ hiểu thực chiến về "${query}".`,
                prompt: `Thiết kế bài kiểm tra Arena cho "${query}" (${categoryText}).\n- 10 câu hỏi theo 3 mức độ\n- Có giải thích ngắn cho từng đáp án\n- Nêu lỗ hổng kiến thức theo nhóm\n- Đề xuất kế hoạch ôn lại`,
                type: 'quiztest'
            }
        ];
    }

    return [
        {
            title: '7-day product sprint',
            summary: `Design a 7-day mini product experiment around "${query}" with measurable outcomes.`,
            prompt: `Create a 7-day execution plan for a mini product around "${query}" (${categoryText}).\n- Goal and success criteria\n- MVP feature set\n- Daily KPI checkpoints\n- Risk and mitigation plan`,
            type: 'presentation'
        },
        {
            title: '3-layer content strategy',
            summary: `Turn "${query}" into a layered content strategy: fundamentals, deep dive, and real-world application.`,
            prompt: `Build a 3-layer content strategy for "${query}" (${categoryText}).\n- Layer 1: fundamentals\n- Layer 2: deep analysis\n- Layer 3: practical application\n- Publishing cadence and measurement criteria`,
            type: 'report'
        },
        {
            title: 'Breakthrough experiment lab',
            summary: `Generate hypotheses and rapid experiments to discover bold directions for "${query}".`,
            prompt: `Design a creative experiment lab for "${query}" (${categoryText}).\n- 5 high-potential hypotheses\n- 5 low-cost rapid experiments\n- Prioritization matrix\n- Post-experiment learning loop`,
            type: 'mindmap'
        },
        {
            title: 'Arena-style skill challenge',
            summary: `Create an Arena-style AI test to measure practical mastery of "${query}".`,
            prompt: `Design an Arena challenge for "${query}" (${categoryText}).\n- 10 questions across 3 difficulty levels\n- Include short rationale per answer\n- Identify knowledge gaps by cluster\n- Propose a focused remediation plan`,
            type: 'quiztest'
        }
    ];
}

function buildAnalysis(query) {
    const category = inferCategory(query);
    return {
        query,
        category,
        keywords: buildKeywords(query, category),
        creative: buildCreativeBursts(query, category),
        outputs: recommendedTypes(category).map((type) => ({
            type,
            mode: outputMode(type),
            title: `${typeLabel(type)}: ${query}`,
            summary: lang() === 'vi'
                ? `Dùng để triển khai chủ đề "${query}" theo dạng ${typeLabel(type).toLowerCase()}.`
                : `Use this to turn "${query}" into a ${typeLabel(type).toLowerCase()} output.`,
            prompt: buildPrompt(type, query, category)
        }))
    };
}

function normalizeAnalysisPayload(analysis, rawQuery, displayQuery = rawQuery) {
    const safe = repairData(analysis && typeof analysis === 'object' ? analysis : {});
    const uiLanguage = String(safe.language || lang() || 'en').trim().toLowerCase() === 'vi' ? 'vi' : 'en';
    const normalizedDisplayQuery = repairText(
        String(safe.display_query || safe.query || displayQuery || rawQuery || '').trim()
    ) || repairText(displayQuery || rawQuery || '');
    const normalizedRawQuery = repairText(
        String(safe.raw_query || rawQuery || normalizedDisplayQuery || '').trim()
    ) || normalizedDisplayQuery;
    const base = repairData(buildGenericAnalysisFallback(normalizedRawQuery, normalizedDisplayQuery, uiLanguage));
    const rawTracks = Array.isArray(safe.tracks) && safe.tracks.length
        ? safe.tracks.map((track) => ({
            ...track,
            key: sanitizeSearchText(track?.key || ''),
            icon: sanitizeSearchText(track?.icon || '✨') || '✨',
            label: sanitizeSearchText(track?.label || ''),
            title: sanitizeSearchText(track?.title || ''),
            description: sanitizeSearchText(track?.description || '')
        })).filter((track) => {
            return /(chứng|nguồn|xác thực|lọc nhiễu|evidence|official|noise filter|verification)/i.test(
                `${track.label} ${track.title} ${track.description}`
            );
        })
        : base.tracks;
    const shouldReplaceTracks = rawTracks.some((track) =>
        /(bằng chứng|nguồn|xác thực|lọc nhiễu|evidence|official|noise filter|verification)/i.test(
            `${track.label} ${track.title} ${track.description}`
        )
    );
    const normalizedTracks = shouldReplaceTracks ? base.tracks : rawTracks;

    const normalizedStatusLine = sanitizeSearchText(safe.status_line || '');
    const normalizedBrief = sanitizeSearchText(typeof safe.brief === 'string'
        ? safe.brief
        : (typeof safe.answer === 'string' ? safe.answer : ''));
    const migratedBrief = looksLikeLatestModelQuery(normalizedDisplayQuery)
        && /(nguồn|bằng chứng|xác thực|official|evidence|source layer|chưa đủ nguồn|không đủ nguồn)/i.test(normalizedBrief)
        ? [normalizedTracks[0]?.description, normalizedTracks[1]?.description].filter(Boolean).join(' ')
        : normalizedBrief;
    const incomingActions = Array.isArray(safe.actions) && safe.actions.length ? safe.actions : [];
    const shouldReplaceActions = incomingActions.some((action) =>
        ['official-search', 'mindmap', 'flashcard', 'quiz'].includes(String(action?.id || '').trim().toLowerCase())
    );

    return repairData({
        ...base,
        ...safe,
        raw_query: normalizedRawQuery,
        query: normalizedDisplayQuery,
        display_query: normalizedDisplayQuery,
        language: uiLanguage,
        category: safe.category || '',
        freshness_mode: safe.freshness_mode || base.freshness_mode,
        headline: sanitizeSearchText(safe.headline || normalizedDisplayQuery),
        status_line: normalizedStatusLine,
        brief: migratedBrief || normalizedStatusLine || buildBriefFallbackText({ tracks: normalizedTracks }),
        keywords: Array.isArray(safe.keywords) && safe.keywords.length
            ? safe.keywords.map((item) => sanitizeSearchText(item)).filter(Boolean)
            : base.keywords,
        creative: Array.isArray(safe.creative) && safe.creative.length ? safe.creative : base.creative,
        outputs: Array.isArray(safe.outputs) && safe.outputs.length ? safe.outputs : base.outputs,
        tracks: normalizedTracks,
        actions: shouldReplaceActions ? base.actions : (incomingActions.length ? incomingActions : base.actions),
        follow_ups: Array.isArray(safe.follow_ups) && safe.follow_ups.length
            ? safe.follow_ups.map((item) => sanitizeSearchText(item)).filter(Boolean)
            : base.follow_ups,
        verification_checks: Array.isArray(safe.verification_checks) && safe.verification_checks.length
            ? safe.verification_checks.map((item) => sanitizeSearchText(item)).filter(Boolean)
            : base.verification_checks,
        decision_paths: Array.isArray(safe.decision_paths) && safe.decision_paths.length
            ? safe.decision_paths.map((item) => ({
                ...item,
                title: sanitizeSearchText(item?.title || ''),
                description: sanitizeSearchText(item?.description || ''),
                action: sanitizeSearchText(item?.action || 'follow-up') || 'follow-up',
                query: sanitizeSearchText(item?.query || ''),
                type: sanitizeSearchText(item?.type || 'report') || 'report',
                prompt: sanitizeSearchText(item?.prompt || '')
            })).filter((item) => item.title && item.description)
            : base.decision_paths,
        sources: Array.isArray(safe.sources) && safe.sources.length
            ? safe.sources
            : (Array.isArray(safe.sources_drawer) ? safe.sources_drawer : [])
    });
}
// Some weaker models return icon NAMES ("chart", "robot") instead of emoji.
// Normalize so the report always looks vivid.
const DR_ICON_MAP = {
    chart: '📊', graph: '📈', bar: '📊', trend: '📈', stats: '📊', data: '🗃️',
    robot: '🤖', ai: '🤖', brain: '🧠', cpu: '🧠', chip: '💡',
    timer: '⏱️', clock: '🕒', time: '🕒', calendar: '🗓️', date: '🗓️',
    rocket: '🚀', launch: '🚀', star: '⭐', spark: '✨', fire: '🔥',
    money: '💰', cost: '💰', price: '🏷️', dollar: '💵', chart_up: '📈',
    globe: '🌐', world: '🌍', map: '🗺️', target: '🎯', goal: '🎯',
    warning: '⚠️', alert: '⚠️', risk: '⚠️', check: '✅', shield: '🛡️',
    book: '📖', news: '📰', doc: '📄', search: '🔎', idea: '💡',
    crystal: '🔮', future: '🔮', forecast: '🔮', lightning: '⚡', bolt: '⚡',
    people: '👥', person: '👤', org: '🏢', company: '🏢', build: '🏗️',
    gear: '⚙️', tool: '🛠️', lock: '🔒', key: '🔑', link: '🔗', tag: '🏷️'
};
function iconEmoji(raw, fallback) {
    const v = String(raw || '').trim();
    if (!v) return fallback;
    // Already an emoji / symbol (non-ASCII first char) → keep as-is.
    if (/[^\x00-\x7f]/.test(v)) return v;
    const key = v.toLowerCase().replace(/[^a-z_]/g, '');
    return DR_ICON_MAP[key] || fallback;
}

function confidenceMeta(level) {
    const vi = lang() === 'vi';
    if (level === 'high') return { cls: 'high', label: vi ? 'Độ tin cậy cao' : 'High confidence' };
    if (level === 'low') return { cls: 'low', label: vi ? 'Cần kiểm chứng' : 'Needs verification' };
    return { cls: 'medium', label: vi ? 'Độ tin cậy vừa' : 'Medium confidence' };
}

function horizonMeta(horizon) {
    const vi = lang() === 'vi';
    if (horizon === 'near') return { icon: '⚡', label: vi ? 'Ngắn hạn' : 'Near term' };
    if (horizon === 'long') return { icon: '🌌', label: vi ? 'Dài hạn' : 'Long term' };
    return { icon: '🛰️', label: vi ? 'Trung hạn' : 'Mid term' };
}

// Build the vivid, multi-module deep-research report. Returns '' if there is no
// usable structured report so the caller can fall back to the plain brief.
function buildDeepReportHtml(report, brief) {
    if (!report || typeof report !== 'object') return '';
    const vi = lang() === 'vi';
    const tldr = Array.isArray(report.tldr) ? report.tldr.filter(Boolean) : [];
    const sections = Array.isArray(report.sections) ? report.sections : [];
    const findings = Array.isArray(report.key_findings) ? report.key_findings : [];
    const entities = Array.isArray(report.entities) ? report.entities : [];
    const timeline = Array.isArray(report.timeline) ? report.timeline : [];
    const outlook = Array.isArray(report.outlook) ? report.outlook : [];
    const contradictions = Array.isArray(report.contradictions) ? report.contradictions : [];
    const consensus = sanitizeSearchText(String(report.consensus || '').trim());

    // Require a minimum of real content. Kept lenient (any one structured block is
    // enough) so the segmented report cards show whenever the model returns ANY
    // structure — instead of collapsing to a flat wall of text the moment it returns
    // slightly less than before.
    if (tldr.length < 1 && sections.length < 1 && findings.length < 1
        && timeline.length < 1 && entities.length < 1 && !consensus) return '';

    const blocks = [];

    // TL;DR — punchy takeaways
    if (tldr.length) {
        blocks.push(`
            <div class="dr-module dr-tldr">
                <div class="dr-head"><span class="dr-ico">✨</span>${vi ? 'Điểm cốt lõi' : 'Key takeaways'}</div>
                <div class="dr-tldr-grid">
                    ${tldr.slice(0, 5).map((t, i) => `
                        <div class="dr-tldr-card">
                            <span class="dr-tldr-num">${String(i + 1).padStart(2, '0')}</span>
                            <span class="dr-tldr-text">${escapeHtml(sanitizeSearchText(String(t)))}</span>
                        </div>`).join('')}
                </div>
            </div>`);
    }

    // Themed sections
    if (sections.length) {
        blocks.push(`
            <div class="dr-module dr-sections">
                ${sections.map(s => `
                    <div class="dr-section-card">
                        <div class="dr-section-head"><span class="dr-section-ico">${escapeHtml(iconEmoji(s.icon, '✦'))}</span>${escapeHtml(sanitizeSearchText(String(s.heading || '')))}</div>
                        <p class="dr-section-body">${escapeHtml(sanitizeSearchText(String(s.body || '')))}</p>
                    </div>`).join('')}
            </div>`);
    }

    // Key findings with confidence
    if (findings.length) {
        blocks.push(`
            <div class="dr-module dr-findings">
                <div class="dr-head"><span class="dr-ico">🔎</span>${vi ? 'Phát hiện chính' : 'Key findings'}</div>
                <div class="dr-finding-list">
                    ${findings.map(f => {
                        const c = confidenceMeta(f.confidence);
                        return `
                        <div class="dr-finding">
                            <span class="dr-conf dr-conf-${c.cls}" title="${c.label}"></span>
                            <div class="dr-finding-body">
                                <span class="dr-finding-label">${escapeHtml(sanitizeSearchText(String(f.label || '')))}</span>
                                <span class="dr-finding-detail">${escapeHtml(sanitizeSearchText(String(f.detail || '')))}</span>
                            </div>
                            <span class="dr-conf-tag dr-conf-${c.cls}">${c.label}</span>
                        </div>`;
                    }).join('')}
                </div>
            </div>`);
    }

    // Future outlook — Skemi's signature predictive module
    if (outlook.length) {
        blocks.push(`
            <div class="dr-module dr-outlook">
                <div class="dr-head"><span class="dr-ico">🔮</span>${vi ? 'Dự báo tương lai' : 'Future outlook'}</div>
                <div class="dr-outlook-grid">
                    ${outlook.map(o => {
                        const h = horizonMeta(o.horizon);
                        const c = confidenceMeta(o.confidence);
                        return `
                        <div class="dr-outlook-card">
                            <div class="dr-outlook-top"><span class="dr-horizon">${h.icon} ${h.label}</span><span class="dr-conf-tag dr-conf-${c.cls}">${c.label}</span></div>
                            <p class="dr-outlook-text">${escapeHtml(sanitizeSearchText(String(o.prediction || '')))}</p>
                        </div>`;
                    }).join('')}
                </div>
            </div>`);
    }

    // Timeline
    if (timeline.length) {
        blocks.push(`
            <div class="dr-module dr-timeline">
                <div class="dr-head"><span class="dr-ico">🗓️</span>${vi ? 'Dòng thời gian' : 'Timeline'}</div>
                <div class="dr-timeline-track">
                    ${timeline.map(t => `
                        <div class="dr-tl-item">
                            <span class="dr-tl-dot"></span>
                            <span class="dr-tl-date">${escapeHtml(sanitizeSearchText(String(t.date || '')))}</span>
                            <span class="dr-tl-event">${escapeHtml(sanitizeSearchText(String(t.event || '')))}</span>
                        </div>`).join('')}
                </div>
            </div>`);
    }

    // Entities
    if (entities.length) {
        blocks.push(`
            <div class="dr-module dr-entities">
                <div class="dr-head"><span class="dr-ico">🧩</span>${vi ? 'Thực thể nổi bật' : 'Key entities'}</div>
                <div class="dr-entity-grid">
                    ${entities.map(e => `
                        <div class="dr-entity" title="${escapeHtml(sanitizeSearchText(String(e.note || '')))}">
                            <span class="dr-entity-name">${escapeHtml(sanitizeSearchText(String(e.name || '')))}</span>
                            <span class="dr-entity-type">${escapeHtml(sanitizeSearchText(String(e.type || '')))}</span>
                        </div>`).join('')}
                </div>
            </div>`);
    }

    // Contradictions
    if (contradictions.length) {
        blocks.push(`
            <div class="dr-module dr-contra">
                <div class="dr-head"><span class="dr-ico">⚖️</span>${vi ? 'Quan điểm trái chiều' : 'Conflicting views'}</div>
                ${contradictions.map(c => `
                    <div class="dr-contra-row">
                        <div class="dr-contra-claim"><span class="dr-contra-tag">${vi ? 'Quan điểm' : 'Claim'}</span>${escapeHtml(sanitizeSearchText(String(c.claim || '')))}</div>
                        <div class="dr-contra-counter"><span class="dr-contra-tag alt">${vi ? 'Đối lập' : 'Counter'}</span>${escapeHtml(sanitizeSearchText(String(c.counter || '')))}</div>
                    </div>`).join('')}
            </div>`);
    }

    // Consensus banner
    if (consensus) {
        blocks.push(`
            <div class="dr-module dr-consensus">
                <span class="dr-ico">🤝</span>
                <div><span class="dr-consensus-label">${vi ? 'Đồng thuận' : 'Consensus'}</span><p>${escapeHtml(consensus)}</p></div>
            </div>`);
    }

    // Full brief available but collapsed — never a wall of text by default.
    const briefClean = sanitizeSearchText(String(brief || '').trim());
    if (briefClean) {
        blocks.push(`
            <details class="dr-module dr-fulltext">
                <summary>${vi ? 'Đọc bản phân tích đầy đủ' : 'Read the full analysis'}</summary>
                <div class="dr-fulltext-body">${smartFormatBrief(briefClean)}</div>
            </details>`);
    }

    return `<div class="deep-report">${blocks.join('')}</div>`;
}

function renderBrief(analysis) {
    const hub = document.getElementById('nexusIntelligenceHub');
    if (hub) {
        hub.classList.remove('hidden');
        hub.style.display = 'block';
    }

    // Hide old containers
    if (el.researchBrief) el.researchBrief.classList.add('hidden');
    if (el.resultsArea) el.resultsArea.classList.add('hidden');
    
    // Manage HUD
    const hud = document.getElementById('researchHUD');
    if (hud) hud.classList.add('hidden'); // Auto-hide HUD on completion

    // Reset Progress Bar to full
    const progressBar = document.getElementById('neuralProgressBar');
    if (progressBar) progressBar.style.width = '100%';

    // Reset Search Button
    if (el.searchBtn) {
        el.searchBtn.classList.remove('loading');
        el.searchBtn.disabled = false;
        const icon = el.searchBtn.querySelector('i');
        if (icon) icon.className = 'fas fa-search';
        const txt = document.getElementById('searchBtnLang');
        if (txt) txt.textContent = lang() === 'vi' ? 'Tra cứu' : 'Search';
    }

    if (window.relaxSphere) window.relaxSphere();

    const queryTitle = analysis.display_query || analysis.query;
    const brief = sanitizeSearchText(String(analysis.brief || analysis.answer || '').trim()) || buildBriefFallbackText(analysis);

    // Single source-of-truth count so the report header and the "đã đối soát"
    // sources panel never disagree (user saw "160 nguồn" up top but "150" in the
    // panel — caused by the panel slicing the list to 150 then counting that).
    const _drawerAll = Array.isArray(analysis.sources_drawer) ? analysis.sources_drawer : [];
    const _primaryAll = Array.isArray(analysis.sources) ? analysis.sources : [];
    const allReviewedSources = _drawerAll.length >= _primaryAll.length ? _drawerAll : _primaryAll;
    // Prefer the REAL gathered total from the backend (search_meta.total_sources_gathered).
    // The arrays above are capped for display (160/200) so their length is always a
    // round cap value — using the true deduped pool size shows the genuine, non-round
    // count (e.g. 173, not a suspiciously perfect 160). Falls back to the list length.
    // total_sources_gathered is the full deduped pool; the display arrays are always
    // a subset of it, so it's the authoritative (and naturally non-round) count.
    const _metaTotal = Number(analysis?.search_meta?.total_sources_gathered || 0);
    const reviewedCount = _metaTotal > 0 ? _metaTotal : allReviewedSources.length;

    // 1. Expert Identity Card
    const identityCard = document.getElementById('expertIdentityCard');
    if (identityCard) {
        // Clean, professional report header (replaces the cluttered sci-fi panel
        // that also overflowed horizontally). Just title + source/time meta.
        const nSrc = reviewedCount;
        const today = new Date().toLocaleDateString(lang() === 'vi' ? 'vi-VN' : 'en-US',
            { day: '2-digit', month: '2-digit', year: 'numeric' });
        identityCard.innerHTML = `
            <div class="report-head">
                <div class="report-head-tag">${lang() === 'vi' ? 'BÁO CÁO NGHIÊN CỨU' : 'RESEARCH REPORT'}</div>
                <h2 class="report-head-title">${queryTitle || (lang() === 'vi' ? 'Kết quả nghiên cứu' : 'Research result')}</h2>
                <div class="report-head-meta">
                    <span><i class="fas fa-database"></i> ${nSrc} ${lang() === 'vi' ? 'nguồn' : 'sources'}</span>
                    <span><i class="fas fa-clock"></i> ${today}</span>
                    <span><i class="fas fa-circle" style="color:#34d399;font-size:.55em;vertical-align:middle"></i> ${lang() === 'vi' ? 'Dữ liệu tươi' : 'Fresh data'}</span>
                </div>
            </div>
        `;
    }

    // 2. Synthesis Core (Main Content) — vivid deep-research report, fallback to brief
    const synthesisContent = document.getElementById('synthesisContent');
    if (synthesisContent) {
        const reportHtml = buildDeepReportHtml(analysis.report, brief);
        synthesisContent.innerHTML = reportHtml || smartFormatBrief(brief);
        if (reportHtml && window.gsap) {
            window.gsap.from(synthesisContent.querySelectorAll('.dr-module'), {
                opacity: 0, y: 16, stagger: 0.07, duration: 0.5, ease: 'power2.out'
            });
        }
    }

    // 3. Sources — show the FULL drawer (every gathered source), not a tiny slice.
    const sourcesGrid = document.getElementById('briefSourcesGrid');
    if (sourcesGrid) {
        // Reuse the same reviewed-source list/count as the report header so the two
        // numbers always match; render up to 250 rows (covers the full set in practice).
        const sources = allReviewedSources.slice(0, 250);
        const titleEl = document.getElementById('sourcesPanelTitle');
        if (titleEl) titleEl.textContent = (lang() === 'vi' ? `${reviewedCount} nguồn đã đối soát` : `${reviewedCount} sources reviewed`);
        sourcesGrid.innerHTML = sources.map((s, i) => {
            const dom = s.domain || (s.url ? String(s.url).replace(/^https?:\/\/(www\.)?/, '').split('/')[0] : 'Nguồn');
            const url = String(s.url || '#').replace(/"/g, '%22');
            return `
            <a class="src-row" href="${url}" target="_blank" rel="noopener" title="${escapeHtml(s.title || dom)}">
                <span class="src-num">${i + 1}</span>
                <span class="src-body">
                    <span class="src-title">${escapeHtml(s.title || dom)}</span>
                    <span class="src-dom">${escapeHtml(dom)}</span>
                </span>
                <span class="src-go">↗</span>
            </a>`;
        }).join('') || `<p style="font-size:.8rem;opacity:.5">${lang() === 'vi' ? 'Chưa có nguồn.' : 'No sources.'}</p>`;
    }

    // 4. Reasoning Axis (Historical Steps)
    const reasoningSteps = document.getElementById('reasoningSteps');
    if (reasoningSteps) {
        const fullSteps = [...(state.activeJob?.analysis_steps || [])];
        reasoningSteps.innerHTML = fullSteps.slice(-5).reverse().map(step => `
            <div class="reasoning-step" style="font-size: 0.75rem; color: rgba(255,255,255,0.5); padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #c084fc; margin-right: 8px;">></span> ${escapeHtml(step)}
            </div>
        `).join('');
    }

    // 5. Strategic Axes (Execution Paths)
    const executionGrid = document.getElementById('executionGrid');
    if (executionGrid) {
        const paths = Array.isArray(analysis.decision_paths) ? analysis.decision_paths.slice(0, 4) : [];
        executionGrid.innerHTML = paths.map((p, idx) => `
            <button class="stratagem-btn" data-decision-action="${p.action || 'follow-up'}" data-decision-index="${idx}">
                <div style="font-weight: 700; color: #fff; margin-bottom: 4px;">${escapeHtml(p.title)}</div>
                <div style="font-size: 0.7rem; opacity: 0.6;">${escapeHtml(p.description)}</div>
            </button>
        `).join('') || `<p style="font-size: 0.75rem; opacity: 0.5;">${lang() === 'vi' ? 'Đang phân tích nước đi kế tiếp...' : 'Analyzing next moves...'}</p>`;
    }

    // 6. Verification Layer (Fact Grid)
    const verificationGrid = document.getElementById('verificationGrid');
    if (verificationGrid) {
        const checks = Array.isArray(analysis.verification_checks) ? analysis.verification_checks.slice(0, 5) : [];
        verificationGrid.innerHTML = checks.map(c => `
            <div style="display: flex; gap: 10px; margin-bottom: 8px; font-size: 0.75rem; color: rgba(255,255,255,0.7);">
                <span style="color: #4ade80;">✓</span>
                <span>${escapeHtml(c)}</span>
            </div>
        `).join('') || `<p style="font-size: 0.75rem; opacity: 0.5;">Consistency verified.</p>`;
    }

    // Action Hub (Legacy container clearing)
    if (el.briefActions) el.briefActions.innerHTML = '';

    // Final animations
    if (window.gsap) {
        window.gsap.from('.glass-panel', { 
            opacity: 0, 
            y: 20, 
            stagger: 0.1, 
            duration: 0.6, 
            ease: 'power2.out' 
        });
    }

    markSearchWorking(false);
}

function buildDeepCompareData(analysis) {
    const subjects = extractLatestSubjects(analysis).slice(0, 2);
    if (subjects.length < 2) return null;
    const tracks = Array.isArray(analysis?.tracks) ? analysis.tracks : [];
    return {
        left: {
            subject: subjects[0],
            overview: tracks[0]?.description || '',
            detail: tracks[2]?.description || ''
        },
        right: {
            subject: subjects[1],
            overview: tracks[1]?.description || '',
            detail: tracks[3]?.description || ''
        },
        difference: tracks[2]?.description || '',
        summary: sanitizeSearchText(analysis?.brief || '')
    };
}

// Multi-agent squad launcher in the Search results — only when the user enabled
// the "Đội quân AI" skill. Dispatches the topic to a real Legion (manager →
// role-specialised workers → synthesis) and renders the combined intel + each
// agent's contribution, using the user's saved roster.
function renderSearchSquad(query) {
    const box = document.getElementById('searchSquad');
    if (!box) return;
    if (!(window.SkemiLegion && window.SkemiLegion.active())) { box.innerHTML = ''; return; }
    const n = window.SkemiLegion.agentCount();
    box.innerHTML = `<div class="brief-card" style="margin-top:14px;border:1px dashed color-mix(in srgb,#a855f7 45%,transparent)">
        <h3 style="margin:0 0 6px">🛡️ Đội quân AI nghiên cứu sâu</h3>
        <p style="margin:0 0 10px;font-size:.85rem;opacity:.75">${n} tác tử (theo phân vai của bạn) cùng đào sâu chủ đề này, rồi Chỉ huy tổng hợp.</p>
        <button id="searchSquadBtn" class="stratagem-btn" style="background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff">⚡ Triển khai đội quân cho "${escapeHtml((query||'').slice(0,48))}"</button>
        <div id="searchSquadOut" style="margin-top:12px"></div></div>`;
    const btn = document.getElementById('searchSquadBtn');
    btn && btn.addEventListener('click', async () => {
        const out = document.getElementById('searchSquadOut');
        btn.disabled = true; btn.textContent = '⏳ Đội quân đang nghiên cứu…';
        out.innerHTML = `<p style="opacity:.6;font-size:.85rem">${n} tác tử đang chạy song song…</p>`;
        try {
            const data = await window.SkemiLegion.runTask('Nghiên cứu sâu, đa góc nhìn và đề xuất giải pháp cho: ' + query, { agents: n });
            if (!data || !data.success) { out.textContent = 'Đội quân chưa chạy được. Thử lại.'; return; }
            const agentsHtml = (data.agents || []).map(a =>
                `<div class="brief-card" style="margin:8px 0"><b>🤖 ${escapeHtml(a.id)} — ${escapeHtml(a.function)}</b> <span style="opacity:.55;font-size:.72rem">(${Math.round((a.ms||0)/1000)}s)</span>
                 <div style="font-size:.84rem;line-height:1.55;opacity:.85;white-space:pre-wrap;margin-top:4px">${escapeHtml((a.output||'').slice(0,650))}</div></div>`).join('');
            out.innerHTML = `<div class="brief-card" style="border-color:color-mix(in srgb,#a855f7 40%,transparent)"><b>🧠 Tổng hợp của Chỉ huy</b>
                <div style="font-size:.9rem;line-height:1.7;white-space:pre-wrap;margin-top:6px">${escapeHtml(data.result||'')}</div></div>
                <details style="margin-top:10px"><summary style="cursor:pointer;font-weight:700;font-size:.85rem">Đóng góp từng tác tử (${data.workers_ok}/${data.worker_count})</summary>${agentsHtml}</details>`;
        } catch (e) {
            out.textContent = 'Lỗi gọi đội quân: ' + (e.message || e);
        } finally {
            btn.disabled = false; btn.textContent = '⚡ Triển khai lại đội quân';
        }
    });
}

function renderResults(analysis) {
    if (!el.resultsArea || !el.resultsContainer) return;
    // Results are rendering (fresh search OR restored on load) → reveal the 3D
    // knowledge-map + research-Lab buttons + multi-agent squad launcher.
    if (analysis) {
        document.body.classList.add('search-has-results');
        try { renderSearchSquad(analysis.display_query || analysis.query || state.query || ''); } catch (e) {}
    }
    var sources = Array.isArray(analysis.sources) ? analysis.sources.slice(0, 8) : [];
    var checklist = Array.isArray(analysis.verification_checks) ? analysis.verification_checks.slice(0, 5) : [];
    var decisions = Array.isArray(analysis.decision_paths) ? analysis.decision_paths.slice(0, 4) : [];
    var hasPanels = Boolean(sources.length || checklist.length || decisions.length);
    el.resultsArea.style.display = hasPanels ? '' : 'none';
    el.resultsArea.classList.remove('hidden');
    if (el.resultsHeader) el.resultsHeader.style.display = 'none';
    if (el.resultsCount) el.resultsCount.textContent = '';
    if (el.resultsQuery) el.resultsQuery.textContent = '';
    el.resultsContainer.style.display = hasPanels ? 'grid' : 'none';
    if (!hasPanels) { el.resultsContainer.innerHTML = ''; return; }
    var html = '<div class="search-main-stack">';
    if (sources.length) {
        html += '<section class="insight-panel"><div class="panel-head">';
        html += '<span class="panel-kicker">' + (lang() === 'vi' ? 'DEEP INTELLIGENCE MATRIX' : 'DEEP INTELLIGENCE MATRIX') + '</span>';
        html += '<h3>' + (lang() === 'vi' ? 'Nguồn Tri Thức Đã Phân Tích' : 'Analyzed Knowledge Sources') + '</h3>';
        html += '<p>' + (lang() === 'vi' ? 'Skemi đã phân tích ' + sources.length + ' nguồn tin cậy.' : 'Skemi analyzed ' + sources.length + ' trusted sources.') + '</p>';
        html += '</div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;">';
        sources.forEach(function(source) {
            var domain = source.domain || '';
            if (!domain && source.url) { try { domain = new URL(source.url).hostname; } catch(e) { domain = ''; } }
            var favicon = domain ? 'https://www.google.com/s2/favicons?domain=' + domain + '&sz=32' : '';
            html += '<a href="' + escapeHtml(source.url || '#') + '" target="_blank" rel="noopener" class="brief-card" style="text-decoration:none;padding:14px 16px;cursor:pointer;display:flex;gap:12px;align-items:flex-start;">';
            html += '<div style="flex-shrink:0;width:36px;height:36px;border-radius:10px;background:rgba(168,85,247,0.08);border:1px solid rgba(168,85,247,0.12);display:flex;align-items:center;justify-content:center;">';
            if (favicon) { html += '<img src="' + favicon + '" width="18" height="18" style="border-radius:4px;" onerror="this.style.display=\'none\'" alt="">'; }
            else { html += '<span style="font-size:0.8rem;">📄</span>'; }
            html += '</div><div style="flex:1;min-width:0;">';
            html += '<div style="font-size:0.84rem;font-weight:600;color:#e2e8f0;line-height:1.35;">' + escapeHtml(repairText(source.title || source.url || 'Source')) + '</div>';
            html += '<div style="font-size:0.72rem;color:rgba(255,255,255,0.35);margin-top:4px;"><span style="color:#c084fc;">' + escapeHtml(domain) + '</span></div>';
            html += '</div></a>';
        });
        html += '</div></section>';
    }
    if (checklist.length) {
        html += '<section class="insight-panel"><div class="panel-head">';
        html += '<span class="panel-kicker">' + (lang() === 'vi' ? 'CROSS-VERIFICATION' : 'CROSS-VERIFICATION') + '</span>';
        html += '<h3>' + (lang() === 'vi' ? 'Lớp Xác Minh Chéo' : 'Verification Layer') + '</h3>';
        html += '</div><div style="display:flex;flex-direction:column;gap:8px;">';
        checklist.forEach(function(item) {
            html += '<div style="display:flex;align-items:flex-start;gap:12px;padding:12px 14px;border-radius:14px;background:rgba(16,185,129,0.04);border:1px solid rgba(16,185,129,0.08);">';
            html += '<span style="width:20px;height:20px;border-radius:50%;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.2);display:flex;align-items:center;justify-content:center;font-size:0.6rem;color:#34d399;flex-shrink:0;">✓</span>';
            html += '<span style="font-size:0.84rem;color:rgba(255,255,255,0.7);line-height:1.45;">' + escapeHtml(item) + '</span></div>';
        });
        html += '</div></section>';
    }
    if (decisions.length) {
        html += '<section class="insight-panel"><div class="panel-head">';
        html += '<span class="panel-kicker">' + (lang() === 'vi' ? 'EXECUTION PATHS' : 'EXECUTION PATHS') + '</span>';
        html += '<h3>' + (lang() === 'vi' ? 'Nước Đi Tiếp Theo' : 'Next Execution Paths') + '</h3>';
        html += '</div><div class="dashboard-action-stack" style="gap:10px;">';
        decisions.forEach(function(item, index) {
            html += '<button class="brief-action-btn" data-decision-action="' + escapeHtml(item.action || 'follow-up') + '" data-decision-index="' + index + '" style="padding:14px 18px;border-radius:14px;text-align:left;display:flex;align-items:center;gap:10px;">';
            html += '<span style="width:28px;height:28px;border-radius:8px;background:rgba(251,146,60,0.1);border:1px solid rgba(251,146,60,0.15);display:flex;align-items:center;justify-content:center;font-size:0.8rem;flex-shrink:0;">→</span>';
            html += '<span>' + escapeHtml(repairText(item.title || (lang() === 'vi' ? 'Nước đi tiếp theo' : 'Next move'))) + '</span></button>';
        });
        html += '</div></section>';
    }
    html += '</div>';
    el.resultsContainer.innerHTML = html;
}


function renderEmptyState() {
    // No analysed topic on screen → hide the 3D map + Lab buttons again.
    document.body.classList.remove('search-has-results');
    setDiscoveryVisibility(true);
    if (el.researchBrief) {
        el.researchBrief.classList.add('hidden');
        el.researchBrief.style.display = 'none';
    }
    // Stop 3D sphere animation on empty state
    if (window.relaxSphere) window.relaxSphere();
    if (el.resultsArea) el.resultsArea.style.display = '';
    if (el.resultsHeader) el.resultsHeader.style.display = 'none';
    if (el.resultsContainer) el.resultsContainer.style.display = '';
    if (el.resultsContainer) {
        el.resultsContainer.innerHTML = `
            <div class="no-results" data-i18n-allow>
                <div class="no-results-icon">💡</div>
                <h3 class="no-results-title">${t().emptyTitle}</h3>
                <p class="no-results-text">${t().emptyText}</p>
            </div>
        `;
    }
    setCompact(false);
    markSearchWorking(false);
}

function renderTrending() {
    const samples = repairData(SAMPLE_QUERIES[lang()]).filter(([category]) => !state.category || category === state.category).slice(0, 6);
    if (!el.trendingGrid) return;
    el.trendingGrid.innerHTML = samples.map(([category, query, note]) => `
        <button class="sample-query-card trending-card" data-query="${escapeHtml(query)}" data-category="${category}">
            <div class="trending-card-body">
                <span class="trending-card-category">${repairText(CATEGORY_ICONS[category] || '✨')} ${escapeHtml(categoryLabel(category))}</span>
                <h3 class="trending-card-title">${escapeHtml(query)}</h3>
                <p class="sample-query-note">${escapeHtml(note)}</p>
                <div class="trending-card-footer">
                    <span>${escapeHtml(typeLabel(recommendedTypes(category)[0]))}</span>
                    <span class="trending-card-source">Skemi</span>
                </div>
            </div>
        </button>
    `).join('');
}

function renderSuggestions(rawValue) {
    if (!el.suggestions) return;
    const value = rawValue.trim();
    if (!value) {
        el.suggestions.classList.remove('show');
        el.suggestions.innerHTML = '';
        state.selectedSuggestionIndex = -1;
        return;
    }
    const matches = repairData(SAMPLE_QUERIES[lang()]).filter(([, query]) => normalized(query).includes(normalized(value))).slice(0, 5);
    if (!matches.length) {
        el.suggestions.classList.remove('show');
        el.suggestions.innerHTML = '';
        state.selectedSuggestionIndex = -1;
        return;
    }
    el.suggestions.innerHTML = matches.map(([category, query, note]) => `
        <div class="suggestion-item" data-query="${escapeHtml(query)}" data-category="${category}">
            <span class="suggestion-icon">${repairText(CATEGORY_ICONS[category] || '✨')}</span>
            <div><div>${escapeHtml(query)}</div><small>${escapeHtml(note)}</small></div>
        </div>
    `).join('');
    el.suggestions.classList.add('show');
    state.selectedSuggestionIndex = -1;
}

function syncControls() {
    if (el.searchInput) el.searchInput.value = state.query;
    const ghost = document.getElementById('ghostSearchText');
    if (ghost) ghost.textContent = '';
    if (el.timeFilter) el.timeFilter.value = state.time;
    if (el.sortFilter) el.sortFilter.value = state.sort;
    if (el.langFilter) el.langFilter.value = state.lang;
    setChipState();
}

async function seedStudio(prompt, type) {
    await studioData.set('seed', { prompt, type });
    window.location.href = 'Home.html';
}

function findBestOutput(analysis, preferredType) {
    const outputs = Array.isArray(analysis?.outputs) ? analysis.outputs : [];
    if (!outputs.length) return null;
    return outputs.find((output) => output.type === preferredType) || outputs[0];
}

function buildBriefStudioPrompt(analysis, preferredType = 'report') {
    const output = findBestOutput(analysis, preferredType);
    if (!output) return '';
    const sources = Array.isArray(analysis?.sources) ? analysis.sources.slice(0, 4) : [];
    const keywords = Array.isArray(analysis?.keywords) ? analysis.keywords.slice(0, 6) : [];
    const sections = [
        repairText(output.prompt || ''),
        '',
        lang() === 'vi' ? 'Brief đã tổng hợp:' : 'Compiled brief:',
        repairText(analysis?.brief || ''),
        '',
        keywords.length ? (lang() === 'vi' ? `Từ khóa mở rộng: ${keywords.join(', ')}` : `Expansion keywords: ${keywords.join(', ')}`) : '',
        '',
        sources.length ? (lang() === 'vi' ? 'Nguồn ưu tiên:' : 'Priority sources:') : '',
        ...sources.map((source, index) => `${index + 1}. ${repairText(source.title || source.url || '')}${source.url ? ` - ${repairText(source.url)}` : ''}`)
    ].filter(Boolean);
    return sections.join('\n');
}

async function openQuizFromSearch(tab = 'private') {
    const command = {
        id: `cmd_${Date.now()}`,
        type: 'quiz.open',
        target: 'quiz',
        tab,
        createdAt: Date.now()
    };
    await aiCommandData.set('pending', command);
    window.location.href = 'Quiz.html';
}

async function copyBriefSnapshot(analysis) {
    const payload = [
        repairText(analysis?.query || ''),
        '',
        repairText(analysis?.brief || '')
    ].join('\n');
    try {
        await navigator.clipboard.writeText(payload);
    } catch {}
    showToast(lang() === 'vi' ? 'Đã chép brief tra cứu.' : 'Search brief copied.', 'success');
}

function openComputerFromSearch(analysis) {
    const query = sanitizeSearchText(String(analysis?.display_query || analysis?.query || '').trim());
    if (!query) return;
    try {
        localStorage.setItem('skemi_computer_seed_v1', JSON.stringify({
            query,
            source: 'search',
            createdAt: Date.now()
        }));
    } catch {}
    window.location.href = `Computer.html?from=search&query=${encodeURIComponent(query)}`;
}

async function copyVerificationChecklist(analysis) {
    const checks = Array.isArray(analysis?.verification_checks) ? analysis.verification_checks : [];
    const payload = [
        repairText(analysis?.display_query || analysis?.query || ''),
        '',
        ...(checks.length
            ? checks.map((item, index) => `${index + 1}. ${repairText(item)}`)
            : [lang() === 'vi' ? 'Chưa có checklist xác minh.' : 'No verification checklist available.'])
    ].join('\n');
    try {
        await navigator.clipboard.writeText(payload);
    } catch {}
    showToast(lang() === 'vi' ? 'Đã chép checklist xác minh.' : 'Verification checklist copied.', 'success');
}

async function copyPrompt(prompt) {
    try {
        await navigator.clipboard.writeText(prompt);
    } catch {}
    showToast(t().copied, 'success');
}

let activeSearchPollTimer = null;
let activeResumePromise = null;
let lastResumeJobId = '';
let lastResumeFetchAt = 0;

function clearSearchPolling() {
    if (activeSearchPollTimer) {
        window.clearTimeout(activeSearchPollTimer);
        window.clearInterval(activeSearchPollTimer);
        activeSearchPollTimer = null;
    }
}

function markSearchWorking(active) {
    if (window.SkemiAI?.setWorking) {
        window.SkemiAI.setWorking('search', active);
    }
    // Single source of truth for the analyze button's busy state. Every path that
    // marks search working/idle — fresh submit, resume after navigating away and
    // back, polling start, completion, failure — flows through here, so the button
    // stays dimmed + spinning while the job runs (instead of springing back to a
    // fresh clickable look on reload, which is the bug the user reported).
    if (el.searchBtn) {
        el.searchBtn.disabled = !!active;
        el.searchBtn.classList.toggle('is-loading', !!active);
        el.searchBtn.classList.toggle('loading', !!active);
        el.searchBtn.setAttribute('aria-busy', active ? 'true' : 'false');
    }
    // Body flag so any section-level "is researching" CSS (status bars, animated
    // borders) can key off a single class and survive a page reload too.
    document.body.classList.toggle('search-working', !!active);
}


async function createSearchJob(query) {
    // Send the auth token so the server can resolve the account and meter
    // tokens / gate Deep Research against the user's subscription tier.
    const headers = { 'Content-Type': 'application/json' };
    try {
        const tok = (window.SkemiAuth && typeof window.SkemiAuth.getTokenSync === 'function')
            ? window.SkemiAuth.getTokenSync() : '';
        if (tok) headers['Authorization'] = 'Bearer ' + tok;
    } catch (e) { /* anonymous */ }

    const response = await fetch(apiUrl('/search/jobs'), {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({
            query,
            deep_research: true,
            category: state.category || '',
            time_range: state.time || '',
            sort: state.sort || 'relevance',
            lang: state.lang || getConfiguredLanguage(),
            search_context: 'search-page'
        })
    });

    // Monthly token budget exhausted → server returns 402 with an entitlement
    // payload. Show the upgrade nudge instead of a raw error.
    if (response.status === 402) {
        let body = null;
        try { body = await response.json(); } catch (e) { }
        try {
            if (window.SkemiEntitlements) window.SkemiEntitlements.handle402(response, body);
            else if (window.SkemiUpgrade) window.SkemiUpgrade.limit('prompts');
        } catch (e) { }
        const msg = body && body.entitlement && body.entitlement.message
            ? (body.entitlement.message[(localStorage.getItem('skemi_language') || 'vi').slice(0, 2)] || body.entitlement.message.vi)
            : 'Token budget exhausted';
        const err = new Error(msg);
        err.entitlement = body && body.entitlement;
        throw err;
    }
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!payload || !payload.success || !payload.job) {
        throw new Error(payload?.error || 'Empty job');
    }
    // Deep Research was downgraded to basic for this tier → gentle nudge.
    if (payload.entitlement && window.SkemiEntitlements) {
        try { window.SkemiEntitlements.handleDowngrade(payload); } catch (e) { }
    }
    return payload.job;
}

// Stop the AI compute the moment the tab actually closes (not just navigates
// within the app — User_navbar.js sets skemi_in_app_nav on every same-origin
// link click, so clicking to Studio/Chat/etc. and back never interrupts a
// running research, only an actual close does) — the server keeps whatever it
// already logged/produced up to that point, it just stops spending more
// tokens/compute on a user who's gone. sendBeacon fires reliably even as the
// page is unloading (fetch would often get aborted before it lands).
window.addEventListener('pagehide', () => {
    if (sessionStorage.getItem('skemi_in_app_nav')) { sessionStorage.removeItem('skemi_in_app_nav'); return; }
    const jobId = state && state.activeJobId;
    if (!jobId) return;
    try { navigator.sendBeacon(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, new Blob([], { type: 'application/json' })); }
    catch (e) { /* best-effort */ }
});

async function fetchSearchJob(jobId) {
    const response = await fetch(apiUrl(`/search/jobs/${encodeURIComponent(jobId)}`), {
        method: 'GET'
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!payload || !payload.success || !payload.job) {
        throw new Error(payload?.error || 'Missing job');
    }
    return payload.job;
}

function adoptJobState(job, options = {}) {
    if (!job?.id) return null;
    state.activeJobId = job.id;
    state.requestKey = job.request_key || state.requestKey || '';
    state.jobStatus = job.status || state.jobStatus || '';
    if (!state.query && job.query) state.query = job.query;
    if (!state.rawQuery && job.query) state.rawQuery = job.query;
    persistState();
    persistActiveJob();
    window.SkemiJobs?.register(job, {
        context: 'search-page',
        page: 'Search.html',
        kind: 'search_analysis',
        query: state.query || job.query || '',
        requestKey: state.requestKey,
        status: state.jobStatus,
        analysis: options.analysis || null
    });
    return job;
}

// Build the knowledge-MAP straight from the COMPLETED deep-research report, so the
// 3D map just VISUALISES what we already searched (no separate/second search). The
// report's themes → core pillars, findings/entities/outlook/cautions → branch nodes.
// Clean a string into a SHORT, human node label. Rejects raw URLs / tracking junk
// (these leak in from scraped result links — e.g. "/clev?event=StartpageResultClick…")
// and long token blobs, strips "Title \ Site" tails, and trims at a word boundary so
// labels read fully instead of cutting mid-word with an ellipsis.
function cleanGraphLabel(s, maxLen) {
    s = (s || '').toString().trim();
    if (!s) return '';
    if (/^https?:\/\//i.test(s)) return '';                       // full URL
    if (/^[\/.]/.test(s)) return '';                              // path like /clev?…
    if (/[?&](sc|event|payload|utm_|q|ref)=/i.test(s)) return ''; // query/tracking junk
    if (/StartpageResultClick|clev\?|\/url\?|googleadservices/i.test(s)) return '';
    if (/^[A-Za-z0-9_\-]{22,}$/.test(s)) return '';               // opaque token blob
    s = s.replace(/\s+/g, ' ')
         .replace(/\s*[\\|/]\s*[^\\|/]{0,24}$/, '')               // drop " \ Anthropic" / " | Site" tail
         .replace(/[–—:•·\-]\s*$/, '')
         .trim();
    if (!s) return '';
    const max = maxLen || 38;
    if (s.length > max) {
        const cut = s.slice(0, max);
        const sp = cut.lastIndexOf(' ');
        s = (sp > max * 0.5 ? cut.slice(0, sp) : cut).trim() + '…';
    }
    return s;
}

function buildGraphFromAnalysis(a) {
    if (!a) return null;
    const topic = (a.display_query || a.query || 'Chủ đề').toString();
    const rep = a.report || {};
    const tldr = Array.isArray(a.tldr) ? a.tldr : (Array.isArray(rep.tldr) ? rep.tldr : []);
    const nodes = [{ id: 'root', label: cleanGraphLabel(topic, 40) || 'Chủ đề', group: 'root', importance: 5,
        body: (tldr.join(' ') || a.brief || topic).slice(0, 600) }];
    const edges = [];
    const seen = new Set([nodes[0].label.toLowerCase()]);
    let i = 0;
    const add = (label, group, body, rel, imp) => {
        const clean = cleanGraphLabel(label, 38);          // reject URLs/junk, trim at a word
        if (!clean) return null;
        const key = clean.toLowerCase();
        if (seen.has(key)) return null;                    // de-duplicate
        seen.add(key);
        const id = 'n' + (i++);
        nodes.push({ id, label: clean, group, importance: imp || 3, body: (body || '').toString().slice(0, 500) });
        edges.push({ source: 'root', target: id, relation: rel || '' });
        return id;
    };
    const coreIds = [];
    (rep.sections || []).slice(0, 6).forEach((s) => { const id = add(s.heading, 'core', s.body, 'chủ điểm', 4); if (id) coreIds.push(id); });
    // Findings link to ROOT only — the extra finding→core cross-edges made the wires
    // "chằng chịt, chồng chéo". A clean radial reads far clearer.
    (rep.key_findings || []).slice(0, 6).forEach((f) => add(f.label, 'component', f.detail, 'phát hiện', 3));
    (rep.entities || []).slice(0, 5).forEach((e) => add(e.name, 'application', (e.type ? e.type + ' — ' : '') + (e.note || ''), 'liên quan', 2));
    (rep.outlook || []).slice(0, 3).forEach((o) => add(o.prediction, 'example', o.prediction, 'dự báo', 2));
    (rep.contradictions || []).slice(0, 2).forEach((c) => add(typeof c === 'string' ? c : (c.point || c.label), 'caution', typeof c === 'string' ? c : (c.detail || ''), 'lưu ý', 2));
    // Use the sources ALREADY FETCHED by the search so the map NEVER has to re-search.
    // Each becomes a node carrying its clean title + real source URL (cleaned of junk).
    const srcs = Array.isArray(a.sources) ? a.sources : (Array.isArray(rep.sources) ? rep.sources : []);
    srcs.slice(0, 8).forEach((s) => {
        const id = add(s.title || s.name, 'application', s.snippet || s.summary || '', 'nguồn', 2);
        if (id) { const nd = nodes[nodes.length - 1]; if (nd && s.url) { nd.url = s.url; nd.detail = (s.domain || ''); } }
    });
    if (nodes.length < 3) return null;   // genuinely nothing usable
    return { overview: a.brief || rep.summary || '', nodes, edges, topic, success: true, fromSearch: true };
}

function finalizeSearchAnalysis(analysis, options = {}) {
    const normalized = normalizeAnalysisPayload(
        analysis,
        state.rawQuery || analysis?.raw_query || analysis?.query || '',
        state.query || analysis?.display_query || analysis?.query || ''
    );
    state.analysis = normalized;
    // Expose a map built from THIS search so the 3D map button just renders it
    // (no second search). Keyed by topic so a stale graph isn't reused.
    try {
        const g = buildGraphFromAnalysis(normalized);
        const key = (normalized.display_query || normalized.query || '').toString().trim().toLowerCase();
        if (g) {
            window.__skemiSearchGraph = { topic: key, data: g };
            // Persist the FULL graph so the knowledge-map REUSES this completed research
            // (no re-search / re-synthesise) and survives closing + re-opening the map.
            try { sessionStorage.setItem('skemi_research_graph', JSON.stringify({ topic: key, data: g, ts: Date.now() })); } catch (e) {}
            // Persist the knowledge map so the LAB can hydrate its whiteboard from it
            // (the "bản đồ tri thức kết nối với phòng lab" link). Survives navigation.
            try {
                localStorage.setItem('skemi_search_map', JSON.stringify({
                    topic: normalized.display_query || normalized.query || '',
                    overview: g.overview || normalized.brief || '',
                    nodes: (g.nodes || []).map(n => ({ id: n.id, label: n.label, group: n.group, body: (n.body || '').slice(0, 280) })),
                    edges: (g.edges || []).map(e => ({ source: e.source, target: e.target, relation: e.relation || '' })),
                    ts: Date.now()
                }));
            } catch (e) { /* quota — non-fatal */ }
        }
        // Also expose the full analysis so the "Trực quan tổng thể" visual can be built
        // FROM the completed research (no extra LLM call → always rich, even when the
        // cloud model is rate-limited).
        window.__skemiSearchAnalysis = { topic: key, data: normalized };
    } catch (e) { /* non-fatal */ }
    state.jobStatus = 'completed';
    if (options.requestKey) state.requestKey = options.requestKey;
    persistState();
    persistAnalysis(normalized);
    persistActiveJob();
    if (state.requestKey) {
        window.SkemiJobs?.cacheResult(state.requestKey, normalized);
        window.SkemiJobs?.update(state.activeJobId, {
            status: 'completed',
            requestKey: state.requestKey,
            analysis: normalized
        });
    }
    renderBrief(normalized);
    renderTrending();
    // Results are on screen → reveal the 3D knowledge-map + research-Lab buttons.
    document.body.classList.add('search-has-results');
    renderSearchSquad(normalized.display_query || normalized.query || state.query || '');
    markSearchWorking(false);
    if (activeWorkflow?.id) {
        emitWorkflowEvent('result', {
            workflowId: activeWorkflow.id,
            type: activeWorkflow.type,
            rawQuery: state.rawQuery || normalized.raw_query || '',
            displayQuery: normalized.display_query || state.query || '',
            summary: normalized.brief || '',
            language: normalized.language || lang(),
            sources: (normalized.sources || []).slice(0, 5),
            analysis: {
                display_query: normalized.display_query || state.query || '',
                brief: normalized.brief || '',
                actions: normalized.actions || [],
                freshness_mode: normalized.freshness_mode || 'standard'
            }
        });
        activeWorkflow = null;
    }
}

function handleSearchJobResult(job, options = {}) {
    if (!job) return;
    adoptJobState(job);
    const status = String(job.status || '').toLowerCase();
    if (status === 'completed' && job.analysis) {
        finalizeSearchAnalysis(job.analysis, { requestKey: job.request_key || state.requestKey });
        clearSearchPolling();
        return;
    }
    if (status === 'failed') {
        clearSearchPolling();
        markSearchWorking(false);
        window.SkemiJobs?.update?.(job.id, {
            status: 'failed',
            error: job.error || ''
        });
        if (!options.silent) {
            showToast(job.error || (lang() === 'vi' ? 'Không thể tra cứu lúc này.' : 'Search is unavailable right now.'), 'error');
        }
        return;
    }
    markSearchWorking(true);
    startSearchPolling(job.id, { silent: options.silent !== false });
}

function startSearchPolling(jobId, options = {}) {
    if (!jobId) return;
    clearSearchPolling();
    markSearchWorking(true);
    // On resume (page reload mid-job) the console is empty — prime it immediately
    // so the user sees live status right away instead of a blank panel until the
    // first poll lands.
    if (options.resumed && el.researchConsole && !el.researchConsole.querySelector('.console-line')) {
        updateResearchConsole(lang() === 'vi' ? 'Đang nối lại phiên nghiên cứu…' : 'Reconnecting to research session…');
    }
    let pollCount = 0;
    let pollFailStreak = 0;
    const basePollInterval = 3500;
    const maxPollInterval = 12000;

    async function doPoll() {
        try {
            const job = await fetchSearchJob(jobId);
            const status = String(job.status || '').toLowerCase();
            adoptJobState(job);
            window.SkemiJobs?.update(job.id, {
                status: job.status,
                requestKey: job.request_key || state.requestKey,
                analysis: job.analysis || null,
                error: job.error || ''
            });

            // Progress Rendering
            if (job.progress_label && job.progress_label !== 'running' && job.progress_label !== 'completed') {
                const displayQuery = state.query || job.query || '';
                if (!displayQuery) {
                    if (el.briefTitle) el.briefTitle.textContent = '';
                } else {
                    if (el.briefTitle) el.briefTitle.textContent = format(t().briefTitle, { query: displayQuery });
                }
                
                // Update Console
                updateResearchConsole(job.progress_label);
                
                const statusDot = document.querySelector('.sc-status-dot');
                if (statusDot) {
                    statusDot.style.animation = 'livePulse 1s ease-in-out infinite';
                }
            }
            
            // Neural Progress Simulation
            const progressBar = document.getElementById('neuralProgressBar');
            if (progressBar && status !== 'completed') {
                // Mock progress: Start at 5%, go up to 95% over time
                const simulatedPercent = Math.min(95, 5 + (pollCount * 12));
                progressBar.style.width = simulatedPercent + '%';
            }
            
            // Handle multiple steps if available
            if (Array.isArray(job.research_steps)) {
                const currentStepCount = el.researchConsole ? el.researchConsole.querySelectorAll('.console-line').length : 0;
                if (job.research_steps.length > currentStepCount) {
                    for (let i = currentStepCount; i < job.research_steps.length; i++) {
                        updateResearchConsole(job.research_steps[i]);
                    }
                }
            }

            pollFailStreak = 0; // a successful poll clears the failure streak
            if (status === 'completed' && job.analysis) {
                clearSearchPolling();
                finalizeSearchAnalysis(job.analysis, { requestKey: job.request_key || state.requestKey });
                return;
            } else if (status === 'failed') {
                clearSearchPolling();
                markSearchWorking(false);
                if (!options.silent) {
                    showToast(job.error || (lang() === 'vi' ? 'Không thể tra cứu lúc này.' : 'Search is unavailable right now.'), 'error');
                }
                return;
            }
        } catch (error) {
            console.warn('Search polling failed:', error);
            // Guard against a vanished job (server restarted / job expired). Without
            // this the button would stay disabled forever on resume, since we faithfully
            // mirror "job running". After a few consecutive failures, give up cleanly so
            // the user can search again instead of being stuck.
            pollFailStreak++;
            if (pollFailStreak >= 4) {
                clearSearchPolling();
                state.activeJobId = '';
                state.jobStatus = '';
                try { persistState(); persistActiveJob(); } catch (e) {}
                markSearchWorking(false);
                setCompact(Boolean(state.query));
                if (!options.silent) {
                    showToast(lang() === 'vi'
                        ? 'Phiên nghiên cứu trước đã kết thúc. Hãy bấm tra cứu lại.'
                        : 'The previous research session has ended. Please search again.', 'info');
                }
                return;
            }
        }
        // Adaptive backoff: increase interval after 10 polls
        pollCount++;
        const nextInterval = pollCount > 10 ? Math.min(basePollInterval + (pollCount - 10) * 800, maxPollInterval) : basePollInterval;
        activeSearchPollTimer = window.setTimeout(doPoll, nextInterval);
    }

    // First poll: near-immediate when resuming (so restored status appears fast),
    // otherwise after the normal interval since the submit path already shows the
    // boot console + skeletons.
    activeSearchPollTimer = window.setTimeout(doPoll, options.resumed ? 700 : basePollInterval);
}

async function copyTextValue(text, successMessage) {
    const clean = String(text || '').trim();
    if (!clean) return;
    try {
        await navigator.clipboard.writeText(clean);
        showToast(successMessage || t().copied, 'success');
    } catch {
        showToast(lang() === 'vi' ? 'Không thể chép nội dung lúc này.' : 'Could not copy the content right now.', 'error');
    }
}

function runBriefActionById(actionId, analysis = state.analysis) {
    if (!analysis) return;
    const action = String(actionId || '').trim().toLowerCase();
    if (!action) return;
    if (action === 'brief-to-studio') {
        seedStudio(buildBriefStudioPrompt(analysis, 'report'), 'report');
        return;
    }
    if (action === 'open-computer') {
        openComputerFromSearch(analysis);
        return;
    }
    if (action === 'deepen-search') {
        const nextQuery = buildDeepenQuery(analysis);
        if (nextQuery) {
            if (el.searchInput) el.searchInput.value = nextQuery;
            runSearch(nextQuery, { displayQuery: nextQuery });
        }
        return;
    }
    if (action === 'copy-brief') {
        void copyBriefSnapshot(analysis);
        return;
    }
}

async function runSearch(query) {
    if (!query?.trim()) return;
    showSearchLoading();
    clearSearchResults();

    try {
        const res = await fetch('/search/jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json',
                       ...SkemiAuth.getHeaders() },
            credentials: 'include',
            body: JSON.stringify({ query: query.trim() })
        });
        // Monthly token budget exhausted → upgrade nudge, not a raw error.
        if (res.status === 402) {
            let body = null;
            try { body = await res.json(); } catch (_) { }
            try {
                if (window.SkemiEntitlements) window.SkemiEntitlements.handle402(res, body);
                else if (window.SkemiUpgrade) window.SkemiUpgrade.limit('prompts');
            } catch (_) { }
            hideSearchLoading();
            const m = body && body.entitlement && body.entitlement.message;
            showSearchError(m ? (m.vi || m.en) : 'Bạn đã dùng hết hạn mức token hôm nay. Mai sẽ làm mới.');
            return;
        }
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        const responseBody = await res.json();
        const { job } = responseBody;
        // Deep Research downgraded to basic for this tier → gentle nudge.
        if (responseBody.entitlement && window.SkemiEntitlements) {
            try { window.SkemiEntitlements.handleDowngrade(responseBody); } catch (_) { }
        }
        const jobId = job.id || job.job_id;

        if (job.status === 'completed' && job.analysis) {
            renderSearchResults(job.analysis);
            hideSearchLoading();
            return;
        }

        // Poll
        for (let i = 0; i < 90; i++) {
            await new Promise(r => setTimeout(r, 1000));
            const poll = await fetch(`/search/jobs/${jobId}`,
                { headers: SkemiAuth.getHeaders() });
            const pd = await poll.json();
            const status = pd?.job?.status;
            updateSearchStatus(pd?.job?.progress_label || 'Đang phân tích...');

            if (status === 'completed') {
                renderSearchResults(pd.job.analysis);
                hideSearchLoading();
                await _saveSearchHistory(query);
                return;
            }
            if (status === 'failed') throw new Error(pd.job.error || 'Search thất bại');
        }
        throw new Error('Timeout');

    } catch (e) {
        hideSearchLoading();
        showSearchError(e.message);
    }
}

function resumeActiveSearch(options = {}) {
    const requestKey = state.requestKey || '';
    const cached = requestKey ? window.SkemiJobs?.getCachedResult(requestKey) : null;
    if (cached?.analysis) {
        finalizeSearchAnalysis(cached.analysis, { requestKey });
        return true;
    }
    const storedJob = state.activeJobId ? window.SkemiJobs?.get(state.activeJobId) : null;
    if (storedJob?.analysis && String(storedJob.status || '').toLowerCase() === 'completed') {
        finalizeSearchAnalysis(storedJob.analysis, { requestKey: storedJob.requestKey || requestKey });
        return true;
    }
    if (!state.activeJobId) return false;
    // A job is still active → reflect the busy state on the button right away,
    // even while we're re-fetching its status, so it doesn't look clickable.
    markSearchWorking(true);
    const now = Date.now();
    if (activeResumePromise && lastResumeJobId === state.activeJobId && (now - lastResumeFetchAt) < 1800) {
        return true;
    }
    if (!options.hydrateOnly) {
        renderLoading({ status: 'init' });
        injectSearchSkeletons();
    }
    lastResumeJobId = state.activeJobId;
    lastResumeFetchAt = now;
    activeResumePromise = fetchSearchJob(state.activeJobId)
        .then((job) => handleSearchJobResult(job, { silent: options.silent !== false, hydrateOnly: options.hydrateOnly }))
        .catch((error) => {
            console.warn('Resume search failed:', error);
        })
        .finally(() => {
            activeResumePromise = null;
        });
    return true;
}

function hydrateActiveSearchFromStore() {
    const requestKey = state.requestKey || '';
    const cached = requestKey ? window.SkemiJobs?.getCachedResult(requestKey) : null;
    if (cached?.analysis) {
        finalizeSearchAnalysis(cached.analysis, { requestKey });
        return true;
    }
    const storedJob = state.activeJobId ? window.SkemiJobs?.get(state.activeJobId) : null;
    if (storedJob?.analysis && String(storedJob.status || '').toLowerCase() === 'completed') {
        finalizeSearchAnalysis(storedJob.analysis, { requestKey: storedJob.requestKey || requestKey });
        return true;
    }
    if (state.activeJobId && !state.analysis) {
        setCompact(true);
        renderLoading({ status: 'init' });
        injectSearchSkeletons(); // restore the rich shimmer panels on resume (not empty boxes)
        markSearchWorking(true);
        startSearchPolling(state.activeJobId, { resumed: true });
        return true;
    }
    return false;
}

function pulseAIControlState(duration = 2000) {
    document.body.classList.add('skemi-ai-controlling');
    document.body.setAttribute('data-skemi-ai-state', lang() === 'vi' ? 'Skemi AI đang điều khiển trang web...' : 'Skemi AI is controlling this page...');
    window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
        detail: { active: true, source: 'search', until: Date.now() + duration }
    }));
    if (window.__skemiAIPulseTimer) {
        window.clearTimeout(window.__skemiAIPulseTimer);
    }
    window.__skemiAIPulseTimer = window.setTimeout(() => {
        document.body.classList.remove('skemi-ai-controlling');
        document.body.removeAttribute('data-skemi-ai-state');
        window.__skemiAIPulseTimer = null;
        window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
            detail: { active: false, source: 'search' }
        }));
    }, duration);
}

function readLastSearchCommandId() {
    try {
        return String(searchStorage?.getItem(SEARCH_COMMAND_GUARD_KEY) || '').trim();
    } catch {
        return '';
    }
}

function rememberSearchCommandId(commandId) {
    if (!commandId) return;
    try {
        searchStorage?.setItem(SEARCH_COMMAND_GUARD_KEY, String(commandId));
    } catch {}
}

function shouldIgnoreAISearchCommand(payload) {
    if (!payload || typeof payload !== 'object') return true;
    if (payload.target && payload.target !== 'search') return true;

    const commandId = String(payload.id || payload.workflowId || '').trim();
    if (commandId && commandId === readLastSearchCommandId()) {
        return true;
    }

    const createdAt = Number(payload.createdAt || 0) || 0;
    const maxAgeMs = Math.max(30_000, Number(payload.maxAgeMs || payload.ttlMs || 90_000) || 90_000);
    const isExpired = createdAt > 0 && (Date.now() - createdAt) > maxAgeMs;
    if (isExpired) {
        return true;
    }

    const hasLiveState = Boolean(state.analysis || state.activeJobId || state.query);
    const stateTimestamp = Number(state.stateUpdatedAt || 0) || 0;
    if ((hasLiveState && !payload.forceReplace) || (stateTimestamp && createdAt && createdAt <= stateTimestamp)) {
        return true;
    }

    return false;
}

async function applyGuardedAISearchCommand(payload, options = {}) {
    const commandId = String(payload?.id || payload?.workflowId || '').trim();
    if (shouldIgnoreAISearchCommand(payload)) {
        if (options.consumeStorage) {
            await aiCommandData.delete('pending');
        }
        if (commandId) rememberSearchCommandId(commandId);
        return false;
    }

    const applied = applyAISearchCommand(payload);
    if (applied) {
        if (options.consumeStorage) {
            await aiCommandData.delete('pending');
        }
        if (commandId) rememberSearchCommandId(commandId);
    }
    return applied;
}

function applyAISearchCommand(command) {
    if (!command || typeof command !== 'object') return false;
    if (command.controlPulse) {
        const duration = Math.max(1600, Number(command.controlDurationMs || 5200));
        pulseAIControlState(duration);
    }
    const type = String(command.type || '').toLowerCase();

    if (type === 'search.run') {
        const executePayload = command.executePayload && typeof command.executePayload === 'object'
            ? command.executePayload
            : {};
        const query = String(executePayload.query || command.query || '').trim();
        const displayText = String(command.displayText || executePayload.display_query || executePayload.displayText || query).trim() || query;
        if (!query) return false;
        state.category = String(executePayload.category || command.category || '').trim();
        state.lang = String(executePayload.language || command.language || state.lang || '').trim().toLowerCase();
        syncControls();
        emitWorkflowEvent('accepted', {
            workflowId: command.workflowId || command.id || '',
            type,
            query,
            displayQuery: displayText
        });
        if (el.searchInput) {
            typeIntoInput(el.searchInput, displayText, { intervalMs: 26 }).then(() => {
                runSearch(query, { scroll: true, displayQuery: displayText, workflow: command });
            });
        } else {
            runSearch(query, { scroll: true, displayQuery: displayText, workflow: command });
        }
        return true;
    }

    if (type === 'search.open') {
        setCompact(Boolean(state.query));
        return true;
    }

    return false;
}

async function consumeAISearchCommand() {
    let payload = null;
    try {
        payload = aiCommandData.get('pending', null);
    } catch {
        await aiCommandData.delete('pending');
        return;
    }

    if (!payload) return;
    await applyGuardedAISearchCommand(payload, { consumeStorage: true });
}

async function handleSubmit() {
    const value = el.searchInput?.value.trim() || '';
    if (!value) {
        showToast(t().needQuery, 'error');
        return;
    }
    // Use the RICH job flow that renders into the Nexus hub (#synthesisContent,
    // #briefSourcesGrid, …). The old runSearch()/renderSearchResults() wrote to
    // #search-brief / #search-results-section which no longer exist in the HTML,
    // so results never appeared. We also show the hub + live console immediately
    // so the (multi-second) deep research has visible progress.
    state.rawQuery = value;
    state.query = value;
    state.analysis = null;
    try { persistState(); } catch (e) {}
    setCompact(true);
    setDiscoveryVisibility(false);
    // Clear the "Chưa có chủ đề" empty-state placeholder so it doesn't linger
    // beneath the live research hub while the deep search runs.
    if (el.resultsContainer) el.resultsContainer.innerHTML = '';
    renderLoading({ status: 'init' });
    injectSearchSkeletons();
    markSearchWorking(true); // owns button disabled + busy spinner now
    updateResearchConsole(lang() === 'vi' ? 'Khởi động lõi nghiên cứu sâu…' : 'Booting deep-research core…');
    try {
        const job = await createSearchJob(value);
        adoptJobState(job);
        handleSearchJobResult(job, { silent: false });
        try { _saveSearchHistory(value); } catch (e) {}
    } catch (e) {
        markSearchWorking(false); // re-enables the button
        clearSearchPolling();
        // Don't leave the skeletons spinning forever — show a clear message in the
        // hub instead (e.g. on 402 quota-exhausted or network error).
        const isVi = lang() === 'vi';
        const quota = e && (e.entitlement || /402|quota|token|hạn mức|budget/i.test(String(e.message || '')));
        const msg = quota
            ? (isVi ? 'Bạn đã dùng hết hạn mức tra cứu. Hạn mức sẽ làm mới, hoặc nâng cấp để dùng tiếp.'
                    : 'Your research quota is used up. It resets later, or upgrade to continue.')
            : (isVi ? 'Không thể tra cứu lúc này. Thử lại sau giây lát.'
                    : 'Search is unavailable right now. Please try again.');
        const syn = document.getElementById('synthesisContent');
        if (syn) syn.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text-secondary);font-size:1rem;line-height:1.7">⚠️ ${msg}</div>`;
        ['briefSourcesGrid','reasoningSteps','executionGrid','verificationGrid','expertIdentityCard']
            .forEach(id => { const x = document.getElementById(id); if (x) x.innerHTML = ''; });
        const hud = document.getElementById('researchHUD'); if (hud) hud.classList.add('hidden');
        showToast((e && e.message) || msg, 'error');
    }
}

function bindEvents() {
    el.searchBtn?.addEventListener('click', handleSubmit);
    el.searchInput?.addEventListener('input', (event) => {
        renderSuggestions(event.target.value);
        updateGhostText();
    });
    el.searchInput?.addEventListener('keydown', (event) => {
        const ghost = document.getElementById('ghostSearchText');
        
        // Completion on Tab or ArrowRight
        if ((event.key === 'Tab' || event.key === 'ArrowRight') && ghost && ghost.textContent.length > el.searchInput.value.length) {
            // Need to check if cursor is at the end for ArrowRight
            if (event.key === 'ArrowRight' && el.searchInput.selectionStart < el.searchInput.value.length) return;
            
            event.preventDefault();
            el.searchInput.value = ghost.textContent;
            ghost.textContent = '';
            return;
        }

        if (event.key === 'Enter') {
            event.preventDefault();
            // If ghost text exists, complete it first
            if (ghost && ghost.textContent.length > el.searchInput.value.length) {
                el.searchInput.value = ghost.textContent;
                ghost.textContent = '';
            }
            handleSubmit();
        }
        if (event.key === 'Escape') {
            el.suggestions?.classList.remove('show');
            if (ghost) ghost.textContent = '';
        }
    });
    document.addEventListener('click', (event) => {
        if (!event.target.closest('.search-bar-container')) el.suggestions?.classList.remove('show');
    });
    el.suggestions?.addEventListener('click', (event) => {
        const item = event.target.closest('.suggestion-item');
        if (!item) return;
        state.category = item.dataset.category || '';
        syncControls();
        runSearch(item.dataset.query || '');
    });
    el.chips.forEach((chip) => chip.addEventListener('click', () => {
        state.category = chip.dataset.category || '';
       // Internal state syncing
    syncControls();
    
    // HUD Toggle Listeners
    const toggleBtn = document.getElementById('toggleResearchHUD');
    const hud = document.getElementById('researchHUD');
    const closeBtn = document.getElementById('closeHUD');
    
    if (toggleBtn && hud) {
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = hud.classList.contains('hidden');
            hud.classList.toggle('hidden', !isHidden);
            if (isHidden && window.gsap) {
                window.gsap.fromTo(hud, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 });
            }
        });
    }
    
    if (closeBtn && hud) {
        closeBtn.addEventListener('click', () => hud.classList.add('hidden'));
    }
        persistState();
        syncControls();
        renderTrending();
    }));
    el.timeFilter?.addEventListener('change', (event) => { state.time = event.target.value; persistState(); });
    el.sortFilter?.addEventListener('change', (event) => { state.sort = event.target.value; persistState(); });
    el.langFilter?.addEventListener('change', (event) => { state.lang = event.target.value; persistState(); });
    el.briefActions?.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-brief-action]');
        if (!btn || !state.analysis) return;
        runBriefActionById(btn.dataset.briefAction, state.analysis);
    });
    el.keywordGroup?.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-keyword]');
        if (!btn) return;
        if (el.searchInput) el.searchInput.value = btn.dataset.keyword || '';
        runSearch(btn.dataset.keyword || '');
    });
    el.resultsContainer?.addEventListener('click', (event) => {
        const keywordBtn = event.target.closest('[data-keyword]');
        if (keywordBtn) {
            if (el.searchInput) el.searchInput.value = keywordBtn.dataset.keyword || '';
            runSearch(keywordBtn.dataset.keyword || '', { displayQuery: keywordBtn.dataset.keyword || '' });
            return;
        }

        const followBtn = event.target.closest('[data-follow-query]');
        if (followBtn) {
            const nextQuery = sanitizeSearchText(followBtn.dataset.followQuery || '');
            if (nextQuery) {
                if (el.searchInput) el.searchInput.value = nextQuery;
                runSearch(nextQuery, { displayQuery: nextQuery });
            }
            return;
        }

        const decisionBtn = event.target.closest('[data-decision-action]');
        if (decisionBtn && state.analysis) {
            const item = state.analysis.decision_paths?.[Number(decisionBtn.dataset.decisionIndex)];
            if (!item) return;
            const action = String(decisionBtn.dataset.decisionAction || item.action || 'follow-up').toLowerCase();
            if (action === 'studio') {
                const type = item.type || 'mindmap';
                const prompt = item.prompt || buildBriefStudioPrompt(state.analysis, type);
                seedStudio(prompt, type);
            } else if (action === 'copy') {
                void copyVerificationChecklist(state.analysis);
            } else {
                const nextQuery = sanitizeSearchText(item.query || '');
                if (nextQuery) {
                    if (el.searchInput) el.searchInput.value = nextQuery;
                    runSearch(nextQuery, { displayQuery: nextQuery });
                }
            }
            return;
        }

    });
    el.trendingGrid?.addEventListener('click', (event) => {
        const card = event.target.closest('[data-query]');
        if (!card) return;
        state.category = card.dataset.category || '';
        syncControls();
        runSearch(card.dataset.query || '');
    });
    window.addEventListener('languageChanged', () => {
        state.lang = getConfiguredLanguage();
        applyStaticText();
        syncControls();
        renderTrending();
        if (state.analysis) {
            renderBrief(state.analysis);
            renderResults(state.analysis);
        } else {
            renderEmptyState();
        }
    });
    window.addEventListener('pageshow', () => {
        if (state.activeJobId && !state.analysis && !activeSearchPollTimer) {
            if (!hydrateActiveSearchFromStore() && !window.SkemiJobs?.list) {
                resumeActiveSearch({ silent: true, hydrateOnly: true });
            }
        }
    });
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && state.activeJobId && state.jobStatus !== 'completed' && !activeSearchPollTimer) {
            if (!hydrateActiveSearchFromStore() && !window.SkemiJobs?.list) {
                resumeActiveSearch({ silent: true, hydrateOnly: true });
            }
        }
    });
    window.addEventListener('skemi:job-event', (event) => {
        const detail = event?.detail || {};
        if (!detail) return;
        const requestKey = detail.requestKey || state.requestKey || '';
        const matchesCurrentJob = (detail.jobId && state.activeJobId && detail.jobId === state.activeJobId)
            || (state.requestKey && detail.requestKey && detail.requestKey === state.requestKey);
        if (matchesCurrentJob) {
            const cached = requestKey ? window.SkemiJobs?.getCachedResult(requestKey) : null;
            const storedJob = detail.jobId ? window.SkemiJobs?.get(detail.jobId) : null;
            const analysis = cached?.analysis || storedJob?.analysis || null;
            if (analysis) {
                finalizeSearchAnalysis(analysis, { requestKey: requestKey || storedJob?.requestKey || state.requestKey });
            }
        }
    });

    // GLOBAL INTEGRATION: Throw to IDE
    window.addEventListener('skemi:throw_to_ide', (e) => {
        const { title, content } = e.detail;
        if (window.showConfetti) window.showConfetti();
        
        const msg = lang() === 'vi' 
            ? `Đã triển khai kiến thức về "${title}" vào Studio.` 
            : `Deployed "${title}" intelligence to Studio.`;
            
        if (typeof showNotification === 'function') {
            showNotification(msg, 'success');
        } else if (typeof showToast === 'function') {
            showToast(msg, 'success');
        }
        
        // Actually seed the studio
        if (typeof seedStudio === 'function') {
            // Wait a bit for the notification/confetti to be seen
            setTimeout(() => {
                seedStudio(content, 'mindmap');
            }, 1500);
        }
    });
}

function init() {
    if (!el.searchInput) return;
    restoreState();
    restoreActiveJob();
    restoreAnalysis();
    if (!state.lang) state.lang = getConfiguredLanguage();
    applyStaticText();
    syncControls();
    bindEvents();
    renderTrending();
    window.addEventListener('skemi:ai-command', (event) => {
        const command = event?.detail;
        if (!command || (command.target && command.target !== 'search')) {
            return;
        }
        applyGuardedAISearchCommand(command, { consumeStorage: true });
    });
    consumeAISearchCommand();

    // Toggle the multi-agent squad launcher live when the user flips the skill.
    window.addEventListener('skemiSkillsChanged', () => {
        if (state.analysis) {
            try { renderSearchSquad(state.analysis.display_query || state.analysis.query || state.query || ''); } catch (e) {}
        }
    });

    // AGENT AUTO EXECUTOR
    if (window.sessionStorage) {
        const agentQuery = window.sessionStorage.getItem('skemi_agent_search_query');
        if (agentQuery) {
            window.sessionStorage.removeItem('skemi_agent_search_query');
            setTimeout(async () => {
                if (el.searchInput) {
                    await typeIntoInput(el.searchInput, agentQuery, { intervalMs: 30 });
                    if (el.searchBtn) el.searchBtn.click();
                }
            }, 800);
        }
    }

    // SYNC SIDEBAR PULSE FROM NOTEBOOK
    const notebookLink = document.getElementById('mindmap-link') || Array.from(document.querySelectorAll('.sidebar-links a')).find(a => a.href.includes('Home.html'));
    const notebookPulseActive = (() => {
        try {
            if (window.sessionStorage) {
                return window.sessionStorage.getItem('skemi_global_pulse_notebook') === '1';
            }
            return localStorage.getItem('skemi_global_pulse_notebook') === '1';
        } catch {
            return localStorage.getItem('skemi_global_pulse_notebook') === '1';
        }
    })();
    if (notebookLink && notebookPulseActive) {
        notebookLink.classList.add('status-working');
    }

    if (state.analysis) {
        setCompact(true);
        renderBrief(state.analysis);
        renderResults(state.analysis);
    } else if (state.activeJobId) {
        setCompact(true);
        renderLoading({ status: 'init' }); // Show Omni-Synapse Neural Net loading state immediately
        injectSearchSkeletons(); // rich shimmer panels so resume isn't empty white boxes
        if (!hydrateActiveSearchFromStore() && !window.SkemiJobs?.list) {
            resumeActiveSearch({ silent: true, hydrateOnly: true });
        }
    } else if (state.query) {
        setCompact(true);
        renderEmptyState();
    } else {
        setCompact(false);
        renderEmptyState();
    }

    onAuthStateChanged(auth, async (user) => {
        currentUser = user;
        if (!user) {
            const requireLogin = (e) => {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = 'Login.html';
            };
            
            if (el.searchInput) {
                el.searchInput.readOnly = true;
                el.searchInput.addEventListener('click', requireLogin, true);
            }
            if (el.searchBtn) el.searchBtn.addEventListener('click', requireLogin, true);
            
            // Disable chips
            el.chips.forEach(chip => chip.addEventListener('click', requireLogin, true));
            
            // We intercept container clicks to enforce login
            if (el.resultsContainer) el.resultsContainer.addEventListener('click', requireLogin, true);
            if (el.briefActions) el.briefActions.addEventListener('click', requireLogin, true);
            if (el.keywordGroup) el.keywordGroup.addEventListener('click', requireLogin, true);
            if (el.trendingGrid) el.trendingGrid.addEventListener('click', requireLogin, true);
        } else {
            await Promise.all([
                searchData.load(),
                studioData.load(),
                aiCommandData.load()
            ]);
            updateGhostText();
            await consumeAISearchCommand();
        }
    });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
else init();

function injectSearchSkeletons() {
    // Modern shimmer placeholders so the panels look like they're LOADING (not
    // empty broken gray boxes) while deep research runs. renderBrief() overwrites
    // them with real content on completion.
    const line = (w) => `<div class="skel skel-line" style="width:${w}"></div>`;
    const card = () => `<div class="skel skel-card"></div>`;
    const set = (id, html) => { const e = document.getElementById(id); if (e) e.innerHTML = html; };
    set('synthesisContent',
        `<div class="skel skel-title"></div>` +
        line('100%') + line('97%') + line('92%') + line('99%') + line('68%') +
        `<div style="height:16px"></div>` +
        line('100%') + line('94%') + line('88%') + line('96%') + line('60%'));
    set('briefSourcesGrid', card() + card() + card());
    set('reasoningSteps', line('92%') + line('80%') + line('86%'));
    set('executionGrid', card() + card());
    set('verificationGrid', line('88%') + line('72%'));
    const ide = document.getElementById('expertIdentityCard');
    if (ide) ide.innerHTML = `<div class="skel skel-line" style="width:42%;height:18px"></div>`;
}

function renderLoading(job = {}) {
    const hub = document.getElementById('nexusIntelligenceHub');
    if (hub) { hub.classList.remove('hidden'); hub.style.display = 'block'; }

    // Show the animated progress tracker (NOT a terminal).
    const hud = document.getElementById('researchHUD');
    if (hud) hud.classList.remove('hidden');

    if (job.status === 'init') {
        // Reset phases → first one active, set the opening status.
        const isVi = lang() === 'vi';
        const st = document.getElementById('rgpStatus');
        if (st) st.textContent = isVi ? 'Đang tìm các nguồn mới nhất…' : 'Finding the latest sources…';
        document.querySelectorAll('.rgp-phase').forEach((el2, i) => {
            el2.classList.toggle('active', i === 0);
            el2.classList.remove('done');
        });
        const bar = document.getElementById('neuralProgressBar');
        if (bar) bar.style.width = '12%';
    }

    const steps = Array.isArray(job.analysis_steps) ? job.analysis_steps : [];
    if (steps.length > 0) updateResearchConsole(steps[steps.length - 1]);

    if (window.intensifySphere) window.intensifySphere();
}

function smartFormatBrief(text) {
    if (!text) return '';
    
    // Preliminary cleanup
    let clean = text.trim();
    
    // Convert Headers first
    clean = clean.replace(/^## (.*$)/gm, '<h2 class="nexus-header-v2">$1</h2>')
                 .replace(/^### (.*$)/gm, '<h3 class="nexus-header-v3">$1</h3>');

    // Handle Numbered Lists (1. 2. 3. )
    clean = clean.replace(/^\d+[\.\)]\s+(.*$)/gm, '<li class="nexus-list-item nexus-numbered">$1</li>');
    
    // Handle Bullet Lists (- or *)
    clean = clean.replace(/^[\-\*]\s+(.*$)/gm, '<li class="nexus-list-item">$1</li>');

    // Handle Bold and Italic
    clean = clean.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
                 .replace(/\*\*(.*?)\*\*/g, '<strong class="highlight-term">$1</strong>')
                 .replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Wrap continuous list items into <ul> or <ol> containers? 
    // For simplicity, we'll just style individual <li> tags in CSS, or do a replacement:
    // But let's wrap paragraphs first.
    
    const lines = clean.split('\n');
    let html = '';
    let inList = false;

    lines.forEach(line => {
        const trimmed = line.trim();
        if (!trimmed) {
            if (inList) { html += '</ul>'; inList = false; }
            return;
        }

        if (trimmed.startsWith('<li')) {
            if (!inList) { html += '<ul class="nexus-brief-list">'; inList = true; }
            html += trimmed;
        } else if (trimmed.startsWith('<h')) {
            if (inList) { html += '</ul>'; inList = false; }
            html += trimmed;
        } else {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<p class="nexus-brief-p">${trimmed}</p>`;
        }
    });

    if (inList) html += '</ul>';

    return `<div class="synthesis-text-wrapper">${html}</div>`;
}
