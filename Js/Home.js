

// Make sure this points to the canonical Skemi backend
const getApiBase = () => {
    if (window.SKEMI_API_BASE) return window.SKEMI_API_BASE.trim().replace(/\/+$/, '');
    if (window.location.port === '8001' || window.location.port === '5500' || !window.location.port) {
        return 'http://127.0.0.1:8010';
    }
    return '';
};
const API_BASE = getApiBase();
const studioData = new UserDataManager('studio');
const EXTERNAL_SEED_KEY = 'skemi_workspace_seed_v1';
const AI_COMMAND_KEY = () => 'skemi_ai_pending_command_v1';
const NOTEBOOK_SEARCH_JOB_KEY = 'skemi_notebook_search_job_v3';
const runtimeSessionStorage = (() => {
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

const STATUS_FALLBACK_PACK = {
    vi: {
        ready: 'Studio đã sẵn sàng.',
        enterProjectName: 'Vui lòng nhập tên dự án.',
        created: 'Đã tạo dự án: {name}',
        switched: 'Đã chuyển sang dự án mới.',
        saved: 'Đã lưu dự án thành công.',
        selectProject: 'Vui lòng tạo hoặc chọn dự án trước khi tiếp tục.',
        generating: 'AI đang xử lý yêu cầu của bạn...',
        enterRequest: 'Vui lòng nhập yêu cầu của bạn.',
        uploadFirst: 'Hãy tải file hoặc ảnh trước khi tạo nội dung.',
        provideInput: 'Vui lòng cung cấp dữ liệu đầu vào.',
        generated: 'Đã tạo nội dung thành công.',
        generateError: 'Không thể tạo nội dung lúc này. Vui lòng thử lại.',
        builderCreated: 'Đã tạo nội dung từ Builder.',
        sourceAdded: 'Đã thêm nguồn vào Notebook.',
        noConversation: 'Notebook chưa có hội thoại để tạo nội dung.',
        notebookCreated: 'Đã tạo {type} từ Notebook.',
        deleteBranch: 'Vui lòng chọn nhánh cần xoá.',
        templateLoaded: 'Đã nạp mẫu. Bạn có thể bấm Tạo nội dung ngay.',
        fileSelected: 'Đã chọn file: {name} ({size} KB)',
        timeout: 'Yêu cầu đã hết thời gian xử lý.'
    },
    en: {
        ready: 'Studio is ready.',
        enterProjectName: 'Please enter a project name.',
        created: 'Project created: {name}',
        switched: 'Project switched successfully.',
        saved: 'Project saved successfully.',
        selectProject: 'Create or select a project before continuing.',
        generating: 'AI is generating your content...',
        enterRequest: 'Please enter your request.',
        uploadFirst: 'Upload a file or image before generating content.',
        provideInput: 'Please provide input data.',
        generated: 'Content generated successfully.',
        generateError: 'Unable to generate content right now. Please try again.',
        builderCreated: 'Content generated from Builder.',
        sourceAdded: 'Notebook source added.',
        noConversation: 'Notebook has no conversation to generate content from.',
        notebookCreated: 'Created {type} from Notebook.',
        deleteBranch: 'Please select a branch to delete.',
        templateLoaded: 'Template loaded. You can generate content now.',
        fileSelected: 'Selected file: {name} ({size} KB)',
        timeout: 'Request timed out.'
    }
};

let chartLoaderPromise = null;
let d3LoaderPromise = null;
let workspaceChartInstance = null;
let builderChartInstance = null;
let viewerChartInstance = null;
const MINDMAP_STYLES = ['auto', 'orbit', 'radial', 'executive', 'neon', 'organic'];
const CREATIVE_LEVELS = ['balanced', 'creative', 'explosive'];

const state = {
    projects: [],
    currentProjectId: null,
    workspaceMode: 'text',
    workspaceType: 'mindmap',
    workspaceMindmapStyle: 'auto',
    workspaceCreativeLevel: 'creative',
    workspaceFile: null,
    builder: {
        title: '',
        type: 'mindmap',
        color: '#6366f1',
        branches: [],
        selectedBranchId: null
    },
    notebook: {
        sources: [],
        activeSourceId: null,
        messages: []
    },
    isGenerating: false,
    isLibrarySearching: false,
    librarySearchQuery: '',
    generateProgress: 0,
    generateProgressTimer: null
};

const el = {
    // Core Layout
    projectHub: document.getElementById('projectHub'),
    studioWorkbench: document.getElementById('studioWorkbench'),
    projectList: document.getElementById('projectList'),
    projectHubName: document.getElementById('projectHubName'),
    projectHubStatus: document.getElementById('projectHubStatus'),
    projectHubCreateBtn: document.getElementById('projectHubCreateBtn'),
    backToProjectsBtn: document.getElementById('backToProjectsBtn'),
    activeProjectTitle: document.getElementById('activeProjectTitle'),
    createProjectArea: document.getElementById('createProjectArea'),
    cancelCreateBtn: document.getElementById('cancelCreateBtn'),
    confirmCreateBtn: document.getElementById('confirmCreateBtn'),

    // Workbench Panels
    tabs: document.querySelectorAll('.studio-tab'),
    studioTabs: document.getElementById('studioTabs'),
    panels: document.querySelectorAll('.studio-pane'),

    // Library
    notebookSourceList: document.getElementById('notebookSourceList'),
    noSourcesPlaceholder: document.getElementById('noSourcesPlaceholder'),
    sourceCountLabel: document.getElementById('sourceCountLabel'),
    sourceProgressBar: document.getElementById('sourceProgressBar'),
    openSourceModalBtn: document.getElementById('openSourceModalBtn'),
    sourceModal: document.getElementById('sourceModal'),
    closeSourceModalBtn: document.getElementById('closeSourceModalBtn'),
    notebookFileInput: document.getElementById('notebookFileInput'),

    // Forge (Chat)
    notebookMessages: document.getElementById('notebookMessages'),
    notebookInput: document.getElementById('notebookInput'),
    notebookSendBtn: document.getElementById('notebookSendBtn'),

    // Alchemist (Synthesis)
    studioPreview: document.getElementById('studioPreview'),
    actionCards: document.querySelectorAll('.action-card'),
    
    // Builder
    builderPreview: document.getElementById('builderPreview'),
    builderBranchList: document.getElementById('builderBranchList'),
    builderTitle: document.getElementById('builderTitle'),
    builderType: document.getElementById('builderType'),
    builderColor: document.getElementById('builderColor'),
    branchInput: document.getElementById('branchInput'),

    // Library Search
    libSearchInput: document.getElementById('libSearchInput'),
    btnLibSearch: document.getElementById('btnLibSearch'),
    btnLibDeepSearch: document.getElementById('btnLibDeepSearch'),
    libDeepSearchToggle: document.getElementById('libDeepSearchToggle') || document.querySelector('.deep-research-toggle'),

    // Notebook UI
    notebookGuide: document.getElementById('notebookGuide'),
    selectAllSources: document.getElementById('selectAllSources'),
    selectAllSourcesRow: document.getElementById('selectAllSourcesRow'),
    guideCards: document.querySelectorAll('.guide-card'),

    // Source Viewer
    sourceDetailOverlay: document.getElementById('sourceDetailOverlay'),
    sourceDetailTitle: document.getElementById('sourceDetailTitle'),
    sourceDetailSummary: document.getElementById('sourceDetailSummary'),
    sourceDetailFullText: document.getElementById('sourceDetailFullText'),
    btnCloseSourceDetail: document.getElementById('btnCloseSourceDetail'),

    // Search Staging
    searchStagingOverlay: document.getElementById('searchStagingOverlay'),
    stagingList: document.getElementById('stagingList'),
    stagingLoading: document.getElementById('stagingLoading'),
    stagingCount: document.getElementById('stagingCount'),
    btnConfirmStaging: document.getElementById('btnConfirmStaging'),
    btnCloseStaging: document.getElementById('btnCloseStaging'),
    btnCancelStaging: document.getElementById('btnCancelStaging'),

    // Legacy/Safe refs for events
    templateCards: document.querySelectorAll('.template-card'),
    arenaModeButtons: document.querySelectorAll('.arena-btn'),
    workspaceTypeButtons: document.querySelectorAll('.type-btn'),
    notebookCreateButtons: document.querySelectorAll('.btn-notebook-create'),
    clearStudioPreviewBtn: document.getElementById('clearStudioPreviewBtn')
};

function t(path, params = {}) {
    const resolvedPath = path.startsWith('home.status.') ? path.replace('home.status.', 'status.') : path;
    if (window.languageManager?.t) {
        const translated = window.languageManager.t(resolvedPath, params);
        if (translated && translated !== resolvedPath) {
            return translated;
        }
    }
    if (resolvedPath.startsWith('status.')) {
        const lang = (window.languageManager?.base || 'vi') === 'vi' ? 'vi' : 'en';
        const key = resolvedPath.slice('status.'.length);
        const template = STATUS_FALLBACK_PACK[lang]?.[key];
        if (template) {
            return String(template).replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''));
        }
    }
    return resolvedPath;
}

function isVi() {
    return (window.languageManager?.base || 'vi') === 'vi';
}

function tx(viText, enText) {
    return isVi() ? viText : enText;
}

function showToast(message, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
        return;
    }
    (function(){})(`[${type}] ${message}`);
}

function setStatus(text, type = 'info') {
    const color = type === 'error'
        ? '#ef4444'
        : (type === 'success' ? '#10b981' : 'var(--text-secondary)');

    if (el.projectStatus) {
        el.projectStatus.textContent = text;
        el.projectStatus.style.color = color;
    }

    if (el.projectHubStatus) {
        el.projectHubStatus.textContent = text;
        el.projectHubStatus.style.color = color;
    }
}

function uid(prefix) {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function escapeHtml(text) {
    return String(text || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function consumeExternalSeed() {
    let payload = null;
    try {
        payload = JSON.parse(localStorage.getItem(EXTERNAL_SEED_KEY) || 'null');
    } catch (error) {
        console.warn('Invalid external seed payload:', error);
    }

    localStorage.removeItem(EXTERNAL_SEED_KEY);
    if (!payload || !payload.prompt) return;

    if (!state.currentProjectId) {
        if (state.projects.length > 0) {
            openProject(state.projects[0].id);
        } else {
            const quickProject = defaultProjectData(tx('Project nhanh', 'Quick Project'));
            state.projects.unshift(quickProject);
            saveProjects();
            renderProjectList();
            openProject(quickProject.id);
        }
    }

    setWorkspaceMode('text');
    if (el.workspacePrompt) {
        el.workspacePrompt.value = payload.prompt;
    }
    if (payload.type) {
        setWorkspaceType(payload.type);
    }
    if (payload.mindmapStyle) {
        state.workspaceMindmapStyle = normalizeMindmapStyle(payload.mindmapStyle);
        if (el.mindmapStyleSelect) el.mindmapStyleSelect.value = state.workspaceMindmapStyle;
    }
    if (payload.creativeLevel) {
        state.workspaceCreativeLevel = normalizeCreativeLevel(payload.creativeLevel);
        if (el.creativeLevelSelect) el.creativeLevelSelect.value = state.workspaceCreativeLevel;
    }
    switchTab('workspace');
    if (state.currentProjectId) {
        persistCurrentProject();
    }
    setStatus(tx('Đã nạp gợi ý từ Tra cứu sang Studio.', 'Loaded the suggestion from Search into Studio.'), 'success');
}

function escapeSelector(value) {
    if (window.CSS?.escape) return window.CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '_');
}

function getCurrentProject() {
    return state.projects.find((project) => project.id === state.currentProjectId) || null;
}

async function saveProjects() {
    await studioData.set('projects', state.projects);
}

async function loadProjects() {
    await studioData.load();
    state.projects = studioData.get('projects', []);

    if (!Array.isArray(state.projects)) {
        state.projects = [];
    }
    state.currentProjectId = null;
}

function defaultProjectData(name) {
    return {
        id: uid('project'),
        name,
        createdAt: new Date().toISOString(),
        workspace: {
            mode: 'text',
            type: 'mindmap',
            mindmapStyle: 'auto',
            creativeLevel: 'creative',
            prompt: '',
            lastResult: null
        },
        builder: {
            title: '',
            type: 'mindmap',
            color: '#6366f1',
            branches: [],
            lastResult: null
        },
        notebook: {
            sources: [],
            activeSourceId: null,
            messages: []
        }
    };
}

function renderProjectSelect() {
    if (!el.projectSelect) return;

    el.projectSelect.innerHTML = '';

    if (state.projects.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = t('home.project.empty');
        el.projectSelect.appendChild(option);
        el.projectRequired?.classList.add('active');
        return;
    }

    state.projects.forEach((project) => {
        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        el.projectSelect.appendChild(option);
    });

    el.projectSelect.value = state.currentProjectId || state.projects[0].id;
    el.projectRequired?.classList.remove('active');
}

function setStudioStage(isWorkbenchVisible) {
    el.projectHub?.classList.toggle('hidden', isWorkbenchVisible);
    el.studioWorkbench?.classList.toggle('hidden', !isWorkbenchVisible);
}

function renderProjectList() {
    if (!el.projectList) return;
    el.projectList.innerHTML = '';
    
    // Add "Create Notebook" card as the first item
    const createCard = document.createElement('div');
    createCard.className = 'create-notebook-card animate-fadeInFast';
    createCard.innerHTML = `
        <div class="create-icon-wrap">+</div>
        <span>Tạo sổ ghi chú mới</span>
    `;
    createCard.addEventListener('click', () => {
        el.createProjectArea?.classList.remove('hidden');
        el.projectHubName?.focus();
    });
    el.projectList.appendChild(createCard);
    
    if (state.projects.length === 0) {
        return; // the create card is enough
    }

    state.projects.forEach((project) => {
        const item = document.createElement('div');
        item.className = 'project-list-item animate-fadeInFast';
        
        const dateStr = new Date(project.createdAt).toLocaleDateString(navigator.language, {
            month: 'short', day: 'numeric', year: 'numeric'
        });
        
        const sourceCount = project.notebook?.sources?.length || 0;
        const noteCount = project.builder?.branches?.length || 0;

        item.innerHTML = `
            <div class="project-card-main">
                <div class="project-icon-v2">📓</div>
                <div class="project-options-container">
                    <div class="project-options-icon">⋮</div>
                    <div class="project-options-dropdown hidden">
                        <div class="dropdown-item rename-btn">Đổi tên</div>
                        <div class="dropdown-item delete-btn">Xóa</div>
                    </div>
                </div>
                <h3>${escapeHtml(project.name)}</h3>
            </div>
            <div class="project-meta-v2">
                <span class="meta-pill">${escapeHtml(dateStr)}</span>
                ${sourceCount > 0 ? `<span class="meta-dot">•</span><span class="meta-pill">${sourceCount} ${tx('nguồn', 'sources')}</span>` : ''}
            </div>
        `;
        
        item.querySelector('.project-options-icon').addEventListener('click', (e) => {
            e.stopPropagation();
            const dropdown = item.querySelector('.project-options-dropdown');
            document.querySelectorAll('.project-options-dropdown').forEach(d => {
                if (d !== dropdown) d.classList.add('hidden');
            });
            dropdown.classList.toggle('hidden');
        });
        
        item.querySelector('.rename-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            const newName = prompt('Nhập tên sổ ghi chú mới:', project.name);
            if (newName && newName.trim() !== '') {
                project.name = newName.trim();
                saveProjects();
                renderProjectList();
            }
            document.querySelectorAll('.project-options-dropdown').forEach(d => d.classList.add('hidden'));
        });
        
        item.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (confirm('Bạn có chắc chắn muốn xóa sổ ghi chú này?')) {
                state.projects = state.projects.filter(p => p.id !== project.id);
                saveProjects();
                renderProjectList();
            }
        });

        item.querySelector('.project-card-main').addEventListener('click', () => {
             openProject(project.id);
        });
        
        item.querySelector('.project-meta-v2').addEventListener('click', () => {
             openProject(project.id);
        });
        el.projectList.appendChild(item);
    });
}

// Global listener to close dropdowns when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.project-options-container')) {
        document.querySelectorAll('.project-options-dropdown').forEach(d => d.classList.add('hidden'));
    }
});

function applyProjectToUI() {
    const project = getCurrentProject();
    if (!project) return;

    if (el.activeProjectTitle) {
        el.activeProjectTitle.textContent = project.name;
    }
    
    // Sync state
    state.builder = { ...project.builder };
    state.notebook = { ...project.notebook };
    
    // Toggle Notebook Guide based on sources
    const sources = project.notebook?.sources || [];
    const hasSources = sources.length > 0;
    
    if (el.notebookGuide) {
        el.notebookGuide.classList.toggle('hidden', !hasSources);
    }

    renderNotebookSources();
    renderNotebookMessages();
    renderBranchList();
    
    // Restore Alchemist preview if exists
    if (el.studioPreview && project.workspace.lastResult) {
        renderPreview(project.workspace.lastResult, el.studioPreview);
    }

    // Auto-scroll chat to bottom
    if (el.notebookMessages) {
        el.notebookMessages.scrollTop = el.notebookMessages.scrollHeight;
    }
}

function openProject(projectId) {
    if (!projectId) return;
    state.currentProjectId = projectId;
    
    applyProjectToUI();
    setStudioStage(true);
    switchTab('workspace');
    
    // Smooth transition animations
    if (window.gsap) {
        gsap.from('.column-library', { x: -30, opacity: 0, duration: 0.6, ease: 'power2.out' });
        gsap.from('.column-alchemist', { x: 30, opacity: 0, duration: 0.6, ease: 'power2.out' });
        gsap.from('.column-forge', { y: 20, opacity: 0, duration: 0.8, delay: 0.2, ease: 'power3.out' });
        
        const hasSources = (getCurrentProject()?.notebook?.sources?.length || 0) > 0;
        if (hasSources && el.notebookGuide) {
            gsap.from(el.notebookGuide, { scale: 0.95, opacity: 0, duration: 0.7, delay: 0.4, ease: "back.out(1.7)" });
        }
    }
}

function goProjectHub() {
    if (state.currentProjectId) {
        persistCurrentProject();
    }
    state.currentProjectId = null;
    renderProjectSelect();
    renderProjectList();
    setStudioStage(false);
}

function persistCurrentProject() {
    const project = getCurrentProject();
    if (!project) return;

    project.workspace.mode = state.workspaceMode;
    project.workspace.type = state.workspaceType;
    project.workspace.mindmapStyle = normalizeMindmapStyle(state.workspaceMindmapStyle);
    project.workspace.creativeLevel = normalizeCreativeLevel(state.workspaceCreativeLevel);
    project.workspace.prompt = el.workspacePrompt?.value.trim() || '';

    project.builder = {
        ...project.builder,
        title: state.builder.title,
        type: state.builder.type,
        color: state.builder.color,
        branches: [...state.builder.branches],
        lastResult: project.builder.lastResult || buildBuilderResult()
    };

    project.notebook = {
        ...project.notebook,
        sources: [...state.notebook.sources],
        activeSourceId: state.notebook.activeSourceId,
        messages: [...state.notebook.messages]
    };

    saveProjects();
}

function createProjectByName(name, options = {}) {
    const safeName = String(name || '').trim();
    if (!safeName) {
        return null;
    }

    const project = defaultProjectData(safeName);
    if (typeof options.prompt === 'string' && options.prompt.trim()) {
        project.workspace.prompt = options.prompt.trim();
    }
    if (typeof options.workspaceType === 'string' && options.workspaceType.trim()) {
        project.workspace.type = options.workspaceType.trim();
    }
    if (typeof options.mindmapStyle === 'string') {
        project.workspace.mindmapStyle = normalizeMindmapStyle(options.mindmapStyle);
    }
    if (typeof options.creativeLevel === 'string') {
        project.workspace.creativeLevel = normalizeCreativeLevel(options.creativeLevel);
    }

    state.projects.unshift(project);
    state.currentProjectId = project.id;

    saveProjects();
    renderProjectList();
    renderProjectSelect();
    openProject(project.id);

    return project;
}

// Redundant createProject function removed, logic moved to bindProjectEvents handlers.

function switchTab(panelId) {
    el.tabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.panel === panelId));
    el.panels.forEach((panel) => panel.classList.toggle('active', panel.id === `panel-${panelId}`));
}

function setWorkspaceMode(mode) {
    state.workspaceMode = mode;
    el.inputSwitchButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.inputMode === mode));
    el.workspaceTextBlock?.classList.toggle('hidden', mode !== 'text');
    el.workspaceFileBlock?.classList.toggle('hidden', mode !== 'file');
}

function setWorkspaceType(type) {
    state.workspaceType = type;
    el.workspaceTypeButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.type === type));
    updateWorkspaceStyleVisibility();
}

function normalizeMindmapStyle(style) {
    const value = String(style || '').trim().toLowerCase();
    return MINDMAP_STYLES.includes(value) ? value : 'auto';
}

function normalizeCreativeLevel(level) {
    const value = String(level || '').trim().toLowerCase();
    return CREATIVE_LEVELS.includes(value) ? value : 'creative';
}

function updateWorkspaceStyleVisibility() {
    if (!el.workspaceStyleRow) return;
    el.workspaceStyleRow.classList.toggle('is-hidden', state.workspaceType !== 'mindmap');
}

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => resolve(event.target.result);
        reader.onerror = reject;

        if (file.type.startsWith('image/')) {
            reader.readAsDataURL(file);
        } else {
            reader.readAsText(file);
        }
    });
}

function setWorkspaceFile(file) {
    state.workspaceFile = file;
    if (!el.workspaceFileMeta) return;

    if (!file) {
        el.workspaceFileMeta.textContent = '';
        return;
    }

    el.workspaceFileMeta.textContent = t('status.fileSelected', {
        name: file.name,
        size: Math.max(1, Math.round(file.size / 1024))
    });
}

function withTimeout(promise, timeoutMs = 90000, message = t('status.timeout')) {
    return Promise.race([
        promise,
        new Promise((_, reject) => setTimeout(() => reject(new Error(message)), timeoutMs))
    ]);
}

function setGenerateLoading(isLoading, label = null) {
    if (!el.workspaceGenerateBtn) return;
    state.isGenerating = isLoading;
    el.workspaceGenerateBtn.disabled = isLoading;
    el.workspaceGenerateBtn.textContent = label || (isLoading ? t('status.generating') : t('home.workspace.generate'));

    // Global AI Activity Monitoring
    if (window.SkemiAI) {
        window.SkemiAI.setWorking('studio', isLoading);
    }
}

function clearGenerateProgressTimer() {
    if (state.generateProgressTimer) {
        clearInterval(state.generateProgressTimer);
        state.generateProgressTimer = null;
    }
}

function setGenerateProgress(percent, label = null, stateLabel = 'running') {
    if (!el.generateProgress) return;

    const nextPercent = Math.max(0, Math.min(100, Math.round(percent)));
    state.generateProgress = nextPercent;

    el.generateProgress.dataset.state = stateLabel;
    if (el.generateProgressLabel) {
        el.generateProgressLabel.textContent = label || tx('Đang tạo nội dung', 'Generating content');
    }
    if (el.generateProgressValue) {
        el.generateProgressValue.textContent = `${nextPercent}%`;
    }
    if (el.generateProgressBar) {
        el.generateProgressBar.style.width = `${nextPercent}%`;
    }

    if (state.isGenerating) {
        setGenerateLoading(true, `${tx('Đang tạo', 'Generating')} ${nextPercent}%`);
    }
}

function resetGenerateProgressUI() {
    clearGenerateProgressTimer();
    state.generateProgress = 0;
    if (!el.generateProgress) return;
    el.generateProgress.dataset.state = 'idle';
    if (el.generateProgressLabel) {
        el.generateProgressLabel.textContent = tx('Sẵn sàng tạo nội dung', 'Ready to generate content');
    }
    if (el.generateProgressValue) {
        el.generateProgressValue.textContent = '0%';
    }
    if (el.generateProgressBar) {
        el.generateProgressBar.style.width = '0%';
    }
}

function startGenerateProgress() {
    clearGenerateProgressTimer();
    setGenerateProgress(4, tx('Đang chuẩn bị dữ liệu', 'Preparing data'), 'running');

    state.generateProgressTimer = setInterval(() => {
        if (!state.isGenerating) return;
        const limit = state.workspaceType === 'mindmap' ? 89 : 93;
        if (state.generateProgress >= limit) return;
        const remaining = limit - state.generateProgress;
        const step = Math.max(1, Math.ceil(remaining * 0.12));
        setGenerateProgress(state.generateProgress + step, tx('Đang tạo nội dung', 'Generating content'), 'running');
    }, 240);
}

function finishGenerateProgress(success = true) {
    clearGenerateProgressTimer();
    if (success) {
        setGenerateProgress(100, tx('Hoàn tất tạo nội dung', 'Generation complete'), 'success');
        return;
    }

    const fallback = Math.max(state.generateProgress, 12);
    setGenerateProgress(fallback, tx('Tạo nội dung thất bại', 'Generation failed'), 'error');
}

// --- Studio background-job layer --------------------------------------------
// Studio generation now runs as a server-side background job so the page can be
// left and re-entered mid-generation without losing the work or the live status
// (parity with Search/Chat). studioJobFetch() creates/adopts a job and polls it,
// but ALWAYS falls back to the original direct request if anything about the job
// path fails — so generation never regresses.
const STUDIO_JOB_KEY = 'skemi_studio_active_job_v1';
// Account-scoped + localStorage-backed (was sessionStorage) so the pointer to
// an in-flight job survives a FULL browser close, not just a reload — the
// server job (asyncio background task) keeps running either way; this is
// what lets the user actually find the result again afterward. Routes
// through loadUserData/saveUserData so CloudSync.js also mirrors it to the
// server (see /studio/jobs GET, the account-wide fallback used below).
function persistStudioJob(rec) { try { window.saveUserData && window.saveUserData(STUDIO_JOB_KEY, JSON.stringify(rec)); } catch {} }
function readStudioJob() { try { return JSON.parse((window.loadUserData && window.loadUserData(STUDIO_JOB_KEY)) || 'null'); } catch { return null; } }
function clearStudioJob(jobId) { try { const c = readStudioJob(); if (!jobId || !c || c.jobId === jobId) window.removeUserData && window.removeUserData(STUDIO_JOB_KEY); } catch {} }

// Recovery path when the LOCAL pointer itself is gone (new device, cleared
// storage, or the localStorage write above never landed before close) but
// the account is signed in — ask the server which jobs belong to this
// account instead of relying solely on the client-remembered job_id.
async function recoverStudioJobsFromServer() {
    try {
        const token = window.SkemiAuth?.getTokenSync?.();
        if (!token || readStudioJob()) return; // already have a local pointer, or not signed in
        const res = await fetch('/studio/jobs', { headers: { 'Authorization': `Bearer ${token}` } });
        if (!res.ok) return;
        const json = await res.json();
        const jobs = (json && json.jobs) || [];
        const active = jobs.find((j) => j.status === 'queued' || j.status === 'running')
            || jobs.find((j) => j.status === 'completed' && (Date.now() / 1000 - (j.completed_at || 0)) < 600);
        if (active) persistStudioJob({ jobId: active.job_id, kind: active.kind, savedAt: Date.now() });
    } catch (e) { /* best-effort — normal generation flow still works without this */ }
}

// Stop Studio generation the moment the tab actually closes (not a normal
// navigation — User_navbar.js sets skemi_in_app_nav on every same-origin
// link click, so leaving for Search/Chat/etc. and coming back still resumes
// the live job, only an actual close cancels it) — the server keeps whatever
// it already produced, it just stops spending more compute/tokens on a user
// who's gone. sendBeacon fires reliably even mid-unload (a normal fetch often
// gets aborted before it lands).
window.addEventListener('pagehide', () => {
    if (sessionStorage.getItem('skemi_in_app_nav')) { sessionStorage.removeItem('skemi_in_app_nav'); return; }
    const pending = readStudioJob();
    if (!pending || !pending.jobId) return;
    try { navigator.sendBeacon(`/api/jobs/${encodeURIComponent(pending.jobId)}/cancel`, new Blob([], { type: 'application/json' })); }
    catch (e) { /* best-effort */ }
});

// Resume a Studio generation that was still running when the user navigated away.
// Re-enters the normal generate flow; studioJobFetch() adopts the in-flight job
// (matched by kind) so the live status, progress and final result all come back
// instead of the page resetting to an idle "ready" state.
let studioResumeAttempted = false;
function resumeStudioJob() {
    if (studioResumeAttempted) return;
    const pending = readStudioJob();
    if (!pending?.jobId) return;
    studioResumeAttempted = true;
    if (Date.now() - Number(pending.savedAt || 0) > 30 * 60 * 1000) { clearStudioJob(pending.jobId); return; }
    if (typeof getCurrentProject === 'function' && !getCurrentProject()) { clearStudioJob(pending.jobId); return; }
    setStatus(tx('Đang nối lại phiên tạo nội dung…', 'Resuming your generation…'), 'info');
    try { onWorkspaceGenerate(); } catch (e) { clearStudioJob(pending.jobId); return; }
    // If generation didn't actually start (e.g. inputs gone after reload), don't
    // leave a stale job record behind.
    setTimeout(() => { if (!state.isGenerating) clearStudioJob(pending.jobId); }, 1600);
}

async function pollStudioJob(jobId) {
    let fails = 0;
    const startedAt = Date.now();
    while (Date.now() - startedAt < 240000) {
        await new Promise(r => setTimeout(r, 1200));
        let job = null;
        try {
            const r = await fetch(`${API_BASE}/studio/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            job = await r.json();
            fails = 0;
        } catch (e) {
            // A vanished job (server restarted / TTL expired) shouldn't hang forever.
            if (++fails >= 4) throw new Error('studio-job-vanished');
            continue;
        }
        const status = String(job.status || '').toLowerCase();
        if (status === 'completed') return job.result;
        if (status === 'failed') throw new Error(job.error || job.detail || 'Studio job failed');
    }
    throw new Error('studio-job-timeout');
}

async function studioJobFetch(kind, params, fallbackFetch) {
    try {
        const pending = readStudioJob();
        // Only one Studio generation runs at a time → adopt an in-flight job of the
        // same kind (this is what makes "leave the page and come back" resume work).
        let jobId = (pending && pending.kind === kind && pending.jobId) ? pending.jobId : '';
        if (!jobId) {
            const res = await fetch(`${API_BASE}/studio/jobs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind, ...params })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const created = await res.json();
            jobId = created.job_id;
            if (!jobId) throw new Error('no studio job id');
        }
        persistStudioJob({ jobId, kind, savedAt: Date.now() });
        const raw = await pollStudioJob(jobId);
        clearStudioJob(jobId);
        return raw;
    } catch (e) {
        clearStudioJob();
        if (typeof fallbackFetch === 'function') return fallbackFetch(); // never regress
        throw e;
    }
}

async function generateMindmapFromText(prompt) {
    const data = await studioJobFetch('mindmap_text', { text: prompt }, async () => {
        const response = await withTimeout(fetch(`${API_BASE}/generate_mindmap_from_text`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: prompt })
        }));
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    });
    if (data.error) {
        throw new Error(data.error);
    }

    return {
        type: 'mindmap',
        title: data.topic || 'Mindmap',
        nodes: data.mindmap_nodes || data.nodes || [],
        summary: data.summary || [],
        detail: data.detail || []
    };
}

async function generateMindmapFromFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await withTimeout(fetch(`${API_BASE}/generate_mindmap`, {
        method: 'POST',
        body: formData
    }));

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    if (data.error) {
        throw new Error(data.error);
    }

    return {
        type: 'mindmap',
        title: data.topic || file.name,
        nodes: data.mindmap_nodes || [],
        summary: data.summary || [],
        detail: data.detail || []
    };
}

function mapWorkspaceTypeToDiagramType(type) {
    const typeMap = {
        mindmap: 'mindmap',
        presentation: 'flowchart',
        chart: 'chart',
        infographic: 'flowchart',
        report: 'timeline',
        flashcard: 'mindmap',
        dashboard: 'chart',
        podcast: 'mindmap',
        video: 'flowchart',
        quiztest: 'mindmap',
        comic: 'mindmap',
        book: 'mindmap'
    };
    return typeMap[type] || 'mindmap';
}

function extractDiagramTopics(diagram) {
    const topics = [];
    const push = (value) => {
        const text = String(value || '').trim();
        if (text) topics.push(text);
    };

    const readItems = (items) => {
        if (!Array.isArray(items)) return;
        items.forEach((item) => {
            if (typeof item === 'string') {
                push(item);
                return;
            }
            if (!item || typeof item !== 'object') return;
            push(item.label);
            push(item.title);
            push(item.text);
            push(item.name);
            if (Array.isArray(item.children)) {
                readItems(item.children);
            }
        });
    };

    readItems(diagram?.nodes);
    readItems(diagram?.steps);
    readItems(diagram?.items);
    readItems(diagram?.stages);
    readItems(diagram?.events);
    return [...new Set(topics)].slice(0, 20);
}

async function generateStudioOutput(type, seedText) {
    const payload = await studioJobFetch('studio', { analysis: seedText, format: type, search_mode: false }, async () => {
        const response = await fetch(`${API_BASE}/generate_studio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis: seedText, format: type, search_mode: false })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    });
    if (!payload.success) throw new Error(payload.error || tx('Không tạo được nội dung', 'Generation failed'));
    const data = payload.data || {};
    if (type === 'comic') {
        return {
            type: 'comic',
            title: data.title || tx('Truyện tranh', 'Comic'),
            logline: data.logline || '',
            panels: Array.isArray(data.panels) ? data.panels : [],
            summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), tx('Kịch bản truyện tranh', 'Comic script')]
        };
    }
    return {
        type: 'book',
        title: data.title || tx('Sách', 'Book'),
        subtitle: data.subtitle || '',
        blurb: data.blurb || '',
        chapters: Array.isArray(data.chapters) ? data.chapters : [],
        summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), tx('Sách ngắn', 'Short book')]
    };
}

async function generateModelOutput(type, seedText) {
    if (type === 'comic' || type === 'book') {
        return generateStudioOutput(type, seedText);
    }
    const diagramType = mapWorkspaceTypeToDiagramType(type);
    const payload = await studioJobFetch('diagram', { analysis: seedText, type: diagramType, search_mode: false }, async () => {
        const response = await fetch(`${API_BASE}/generate_diagram`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis: seedText, type: diagramType, search_mode: false })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    });
    if (!payload.success) {
        throw new Error(payload.error || 'Không tạo được sơ đồ');
    }

    const diagram = payload.diagram || {};
    const diagramTopics = extractDiagramTopics(diagram);

    if (diagramType === 'mindmap') {
        const specialMindmapTypes = new Set(['podcast', 'quiztest']);
        if (specialMindmapTypes.has(type)) {
            return {
                type,
                title: diagram.topic || `${tx('Kết quả', 'Result')} ${type}`,
                nodes: diagram.nodes || [],
                topics: [...diagramTopics, ...collectNodeLabels(diagram.nodes || [])].slice(0, 14),
                summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), 'Mindmap']
            };
        }
        return {
            type: 'mindmap',
            title: diagram.topic || `${tx('Kết quả', 'Result')} ${type}`,
            nodes: diagram.nodes || [],
            summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), 'Mindmap'],
            detail: []
        };
    }

    if (diagramType === 'chart') {
        const labels = diagram?.data?.labels || [];
        const resultType = type === 'dashboard' ? 'dashboard' : 'chart';
        return {
            type: resultType,
            title: `${tx('Kết quả', 'Result')} ${type}`,
            chartConfig: diagram,
            topics: (labels.slice(0, 8).map((label) => String(label))).concat(diagramTopics).slice(0, 10),
            summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), 'Chart.js']
        };
    }

    if (diagramType === 'timeline') {
        const events = Array.isArray(diagram.events) ? diagram.events : [];
        return {
            type,
            title: `${tx('Kết quả', 'Result')} ${type}`,
            topics: events.map((event) => `${event.date || ''} - ${event.title || ''}`),
            summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), 'Timeline']
        };
    }

    return {
        type,
        title: `${tx('Kết quả', 'Result')} ${type}`,
        topics: diagramTopics.length > 0 ? diagramTopics : extractTopicsFromText(seedText),
        summary: [tx('Nguồn: AI tổng hợp', 'Source: AI synthesis'), diagramType]
    };
}

function extractTopicsFromText(text) {
    return String(text || '')
        .split(/[.,\n]/)
        .map((item) => item.trim())
        .filter(Boolean)
        .slice(0, 10);
}

function createGenericOutput(type, seedText) {
    const topics = extractTopicsFromText(seedText);
    const safeTopics = topics.length > 0 ? topics : ['Nội dung chính', 'Phân tích', 'Hành động'];

    return {
        type,
        title: `${tx('Kết quả', 'Result')} ${type}`,
        topics: safeTopics,
        summary: [
            `${tx('Loại', 'Type')}: ${type}`,
            `${tx('Nguồn', 'Source')}: ${state.workspaceMode === 'text' ? tx('Văn bản', 'Text') : tx('File/ảnh', 'File/image')}`
        ]
    };
}

function normalizeForKeyword(value) {
    return String(value || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');
}

function inferTopicIcon(topic, depth = 0) {
    const value = normalizeForKeyword(topic);
    const rules = [
        { pattern: /(ai|tri tue|machine|model|llm|du lieu|data|phan tich|analysis)/, icon: '🤖' },
        { pattern: /(hoc|study|learning|giao duc|education|exam|quiz)/, icon: '📘' },
        { pattern: /(nghiên cứu|research|khoa hoc|science|experiment)/, icon: '🔬' },
        { pattern: /(kế hoạch|plan|roadmap|strategy|chien luoc)/, icon: '🧭' },
        { pattern: /(code|lap trinh|developer|api|backend|frontend)/, icon: '💻' },
        { pattern: /(design|sang tao|creative|media|video|podcast|presentation)/, icon: '🎨' },
        { pattern: /(risk|rui ro|warning|bao mat|security)/, icon: '⚠️' },
        { pattern: /(action|hanh dong|execute|thuc thi|kpi|metric)/, icon: '⚡' },
        { pattern: /(business|kinh doanh|market|finance|tai chinh)/, icon: '💼' },
        { pattern: /(health|y te|medical|benh|suc khoe)/, icon: '🩺' }
    ];
    const matched = rules.find((rule) => rule.pattern.test(value));
    if (matched) return matched.icon;
    const fallback = ['🧠', '🌱', '🧩', '📌', '✨', '🛰️'];
    return fallback[Math.max(0, depth) % fallback.length];
}

function buildTopicBadge(topic) {
    const words = String(topic || '')
        .replace(/[^\p{L}\p{N}\s]/gu, ' ')
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2);
    if (words.length === 0) return 'SK';
    return words.map((word) => word[0]).join('').toUpperCase();
}

function buildNodeThumbDataUri(topic, icon, style) {
    const badge = buildTopicBadge(topic);
    const palettes = {
        orbit: ['#3b82f6', '#a855f7'],
        radial: ['#0ea5e9', '#22d3ee'],
        executive: ['#1e293b', '#334155'],
        neon: ['#10b981', '#22d3ee'],
        organic: ['#22c55e', '#84cc16']
    };
    const [from, to] = palettes[style] || ['#3b82f6', '#8b5cf6'];
    const safeIcon = String(icon || '✨').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const safeBadge = String(badge).replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52" viewBox="0 0 52 52">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${from}"/>
      <stop offset="100%" stop-color="${to}"/>
    </linearGradient>
  </defs>
  <rect x="1" y="1" width="50" height="50" rx="14" fill="url(#g)"/>
  <text x="12" y="22" font-size="12">${safeIcon}</text>
  <text x="10" y="39" font-size="13" font-family="Arial, sans-serif" fill="#ffffff" font-weight="700">${safeBadge}</text>
</svg>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function resolveMindmapStyle(selectedStyle, result = null, seedText = '') {
    const normalized = normalizeMindmapStyle(selectedStyle);
    if (normalized !== 'auto') return normalized;
    const seed = `${result?.title || ''}|${extractResultTopics(result).join('|')}|${seedText}`;
    const styles = ['orbit', 'radial', 'executive', 'neon', 'organic'];
    return styles[hashToRange(seed, 0, styles.length - 1)];
}

function resolveMindmapStyleLabel(style) {
    const labels = {
        orbit: tx('Orbit', 'Orbit'),
        radial: tx('Radial', 'Radial'),
        executive: tx('Executive', 'Executive'),
        neon: tx('Neon Pulse', 'Neon Pulse'),
        organic: tx('Organic', 'Organic')
    };
    return labels[style] || tx('Auto', 'Auto');
}

function attachWorkspaceVisualMeta(result, seedText = '') {
    if (!result || typeof result !== 'object') return result;
    const output = result;
    output.creativeLevel = normalizeCreativeLevel(output.creativeLevel || state.workspaceCreativeLevel);

    if (!Array.isArray(output.summary)) {
        output.summary = [];
    }
    if (output.creativeLevel === 'explosive') {
        output.summary = [
            tx('Creative mode: Bùng nổ', 'Creative mode: Explosive'),
            ...output.summary
        ].slice(0, 8);
    } else if (output.creativeLevel === 'creative') {
        output.summary = [
            tx('Creative mode: Sáng tạo', 'Creative mode: Creative'),
            ...output.summary
        ].slice(0, 8);
    }

    if (output.type === 'mindmap') {
        output.mindmapStyle = resolveMindmapStyle(output.mindmapStyle || state.workspaceMindmapStyle, output, seedText);
    }

    return output;
}

function extractSeedText() {
    if (state.workspaceMode === 'text') {
        return el.workspacePrompt?.value.trim() || '';
    }
    return state.workspaceFile ? state.workspaceFile.name : 'Nội dung từ file đã tải lên';
}

function collectNodeLabels(nodes, output = []) {
    (nodes || []).forEach((node) => {
        const label = String(node?.text || node?.label || '').trim();
        if (label) output.push(label);
        collectNodeLabels(node?.children || [], output);
    });
    return output;
}

function extractResultTopics(result) {
    const directTopics = Array.isArray(result?.topics) ? result.topics.map((item) => String(item || '').trim()).filter(Boolean) : [];
    const nodeTopics = collectNodeLabels(result?.nodes || []);
    const merged = [...new Set([...directTopics, ...nodeTopics])];
    
    // Filter meta-items like "Item 1", "instructional text", "priority category"
    return merged
        .filter(item => {
            const low = item.toLowerCase();
            return !low.startsWith('item ') && 
                   !low.includes('priority category') && 
                   !low.includes('found 3 verified') &&
                   !low.includes('search research:');
        })
        .slice(0, 18);
}

function selectOutputTopics(result, limit = 12) {
    const baseTopics = extractResultTopics(result);
    const level = normalizeCreativeLevel(result?.creativeLevel || state.workspaceCreativeLevel);
    const summaryTopics = (Array.isArray(result?.summary) ? result.summary : [])
        .map((item) => String(item || '').trim())
        .filter(Boolean);

    let pool = [...baseTopics];
    if (level !== 'balanced') {
        pool = [...new Set([...pool, ...summaryTopics])];
    }

    if (level === 'explosive' && pool.length >= 2) {
        const combos = [];
        for (let i = 0; i < Math.min(3, pool.length); i += 1) {
            for (let j = i + 1; j < Math.min(5, pool.length); j += 1) {
                combos.push(isVi()
                    ? `${pool[i]} → ứng dụng với ${pool[j]}`
                    : `${pool[i]} -> applied with ${pool[j]}`);
            }
        }
        pool = [...pool, ...combos];
    }

    if (pool.length === 0) {
        pool = isVi()
            ? ['Tổng quan', 'Điểm chính', 'Hành động tiếp theo']
            : ['Overview', 'Core point', 'Next action'];
    }

    return [...new Set(pool)].slice(0, limit);
}

function hashToRange(seedText, min, max) {
    const text = String(seedText || '');
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) {
        hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
    }
    const span = Math.max(1, max - min + 1);
    return min + (hash % span);
}

function renderMindmapTree(nodes) {
    if (!Array.isArray(nodes) || nodes.length === 0) {
        return `<p class="preview-empty">${escapeHtml(tx('Không có node để hiển thị.', 'No nodes to display.'))}</p>`;
    }

    const renderChildren = (items) => {
        if (!Array.isArray(items) || items.length === 0) return '';
        const children = items.map((item) => {
            const title = item.text || item.label || 'Node';
            const icon = inferTopicIcon(title, 1);
            return `<li class="preview-node"><strong>${escapeHtml(icon)} ${escapeHtml(title)}</strong>${renderChildren(item.children || [])}</li>`;
        }).join('');
        return `<ul class="preview-tree">${children}</ul>`;
    };

    return renderChildren(nodes);
}

function normalizeMindmapNodes(result) {
    if (Array.isArray(result?.nodes) && result.nodes.length > 0) {
        return result.nodes
            .map((node) => ({
                ...node,
                text: String(node?.text || node?.label || '').trim(),
                children: normalizeMindmapNodes({ nodes: node?.children || [] })
            }))
            .filter((node) => node.text);
    }

    return extractResultTopics(result).map((topic, index) => ({
        id: `topic_${index + 1}`,
        text: topic,
        children: []
    }));
}

function buildStudyBullets(topic, summary, index) {
    const safeTopic = String(topic || '').trim() || `${tx('Chủ đề', 'Topic')} ${index + 1}`;
    const safeSummary = Array.isArray(summary) && summary.length > 0 ? summary[index % summary.length] : 'Ý chính';
    return [
        `${tx('Trọng tâm', 'Focus')}: ${safeTopic}`,
        `${tx('Mở rộng', 'Expand')}: ${safeSummary}`,
        `${tx('Gợi ý hành động', 'Action hint')}: ${isVi() ? `áp dụng hoặc ôn lại phần "${safeTopic}"` : `apply or review the section "${safeTopic}"`}`
    ];
}

function deriveFlashcards(result) {
    const topics = selectOutputTopics(result, 12);
    const summary = Array.isArray(result?.summary) ? result.summary : [];
    return topics.slice(0, 12).map((topic, index) => ({
        id: `card_${index + 1}`,
        front: topic,
        back: buildStudyBullets(topic, summary, index).join('. '),
        tag: summary[index % Math.max(summary.length, 1)] || `Thẻ ${index + 1}`
    }));
}

function deriveSlides(result) {
    const topics = selectOutputTopics(result, 8);
    const summary = Array.isArray(result?.summary) ? result.summary : [];
    return topics.slice(0, 8).map((topic, index) => ({
        id: `slide_${index + 1}`,
        icon: inferTopicIcon(topic, index),
        kicker: summary[index % Math.max(summary.length, 1)] || `Slide ${index + 1}`,
        title: topic,
        bullets: buildStudyBullets(topic, summary, index),
        visualCue: isVi()
            ? `Cảnh ${index + 1}: dùng biểu tượng ${inferTopicIcon(topic, index)} + highlight 1 số liệu`
            : `Scene ${index + 1}: use ${inferTopicIcon(topic, index)} icon + highlight one metric`,
        presenterNote: isVi()
            ? `Nhấn mạnh tác động thực tế của "${topic}" trong 20 giây đầu.`
            : `Emphasize the practical impact of "${topic}" in the first 20 seconds.`
    }));
}

function deriveSections(result) {
    const topics = selectOutputTopics(result, 10);
    const summary = Array.isArray(result?.summary) ? result.summary : [];
    return topics.slice(0, 10).map((topic, index) => ({
        id: `section_${index + 1}`,
        title: topic,
        body: buildStudyBullets(topic, summary, index),
        label: summary[index % Math.max(summary.length, 1)] || `Mục ${index + 1}`
    }));
}

function deriveInfoBlocks(result) {
    const topics = selectOutputTopics(result, 9);
    const summary = Array.isArray(result?.summary) ? result.summary : [];
    const variants = ['variant-a', 'variant-b', 'variant-c'];
    return topics.slice(0, 9).map((topic, index) => ({
        id: `info_${index + 1}`,
        icon: inferTopicIcon(topic, index),
        title: topic,
        desc: buildStudyBullets(topic, summary, index)[1],
        action: buildStudyBullets(topic, summary, index)[2],
        metric: `${hashToRange(`${topic}:metric`, 72, 98)}%`,
        index: `${index + 1}`.padStart(2, '0'),
        variant: variants[index % variants.length]
    }));
}

function deriveDashboardMetrics(result) {
    const topics = selectOutputTopics(result, 12);
    const seed = `${result?.title || ''}:${topics.join('|')}`;
    const labels = isVi()
        ? ['Coverage', 'Depth', 'Action items', 'Risk flags']
        : ['Coverage', 'Depth', 'Action items', 'Risk flags'];

    const values = [
        `${hashToRange(`${seed}:coverage`, 78, 97)}%`,
        `${hashToRange(`${seed}:depth`, 70, 96)}%`,
        `${hashToRange(`${seed}:actions`, 4, 14)}`,
        `${hashToRange(`${seed}:risk`, 1, 6)}`
    ];

    const descs = isVi()
        ? [
            'Mức bao phủ chủ đề từ nguồn hiện có.',
            'Độ sâu phân tích theo nhánh nội dung.',
            'Số hạng mục có thể triển khai ngay.',
            'Các điểm cần kiểm soát thêm dữ liệu.'
        ]
        : [
            'Topic coverage based on available sources.',
            'Analysis depth across key branches.',
            'Items that can be executed immediately.',
            'Areas that still need source validation.'
        ];

    return labels.map((label, index) => ({
        label,
        value: values[index],
        desc: descs[index],
        delta: `${hashToRange(`${seed}:${label}:delta`, 2, 18)}%`,
        trend: ['up', 'flat', 'down'][hashToRange(`${seed}:${label}:trend`, 0, 2)]
    }));
}

function derivePodcastDuel(result) {
    const topics = selectOutputTopics(result, 10);
    const first = isVi() ? 'Host A · Lạc quan' : 'Host A · Optimist';
    const second = isVi() ? 'Host B · Phản biện' : 'Host B · Skeptic';
    const hostProfiles = [
        {
            name: first,
            icon: '🎙️',
            tone: isVi() ? 'Tông giọng tích cực, thiên về cơ hội.' : 'Positive tone focused on opportunities.'
        },
        {
            name: second,
            icon: '🧠',
            tone: isVi() ? 'Tông giọng phân tích, thiên về rủi ro và kiểm chứng.' : 'Analytical tone focused on risks and validation.'
        }
    ];

    const lines = (topics.length ? topics : [tx('Ý chính', 'Key point')]).slice(0, 8).map((topic, index) => ({
        speaker: index % 2 === 0 ? first : second,
        text: index % 2 === 0
            ? tx(`Luận điểm: "${topic}" là cơ hội nên ưu tiên triển khai.`, `Argument: "${topic}" is an opportunity to prioritize.`)
            : tx(`Phản biện: cần kiểm tra thêm dữ liệu trước khi chốt "${topic}".`, `Counterpoint: validate data before finalizing "${topic}".`)
    }));

    return {
        title: result?.title || tx('Podcast Duel', 'Podcast Duel'),
        hosts: hostProfiles,
        lines
    };
}

function deriveVideoStoryboard(result) {
    const topics = selectOutputTopics(result, 8);
    const shots = (topics.length ? topics : [tx('Mở đầu chủ đề', 'Topic intro')]).slice(0, 6).map((topic, index) => ({
        time: `${String(index * 16).padStart(2, '0')}s`,
        title: topic,
        icon: inferTopicIcon(topic, index),
        action: tx('Zoom vào điểm chính + subtitle ngắn', 'Zoom on key point + short subtitle'),
        camera: ['Push-in', 'Pan-right', 'Focus-pull', 'Cutaway', 'Dolly-in', 'Wide shot'][index % 6]
    }));

    const scriptLines = shots.map((shot, index) => (
        isVi()
            ? `${index + 1}. Trình bày ngắn gọn về "${shot.title}" và liên kết với mục tiêu thực tế.`
            : `${index + 1}. Explain "${shot.title}" concisely and connect it to practical outcomes.`
    ));

    return {
        title: result?.title || tx('AI Cinematic Presentation', 'AI Cinematic Presentation'),
        presenter: isVi() ? 'Presenter AI' : 'AI Presenter',
        shots,
        scriptLines
    };
}

function deriveQuizArena(result) {
    if (Array.isArray(result?.questions) && result.questions.length > 0) {
        return result.questions.slice(0, 8).map((item, index) => ({
            question: String(item.question || '').trim() || `${tx('Câu hỏi', 'Question')} ${index + 1}`,
            options: Array.isArray(item.options) ? item.options.slice(0, 4) : [],
            answer: Number(item.answer ?? 0),
            explanation: String(item.explanation || '').trim()
        }));
    }

    const topics = selectOutputTopics(result, 8);
    const seeds = (topics.length ? topics : [tx('Tổng quan chủ đề', 'Topic overview')]).slice(0, 6);
    return seeds.map((topic, index) => {
        const opts = [
            tx(`Ý cốt lõi của "${topic}"`, `Core idea of "${topic}"`),
            tx(`Ví dụ áp dụng cho "${topic}"`, `Applied example of "${topic}"`),
            tx(`Rủi ro nếu làm sai "${topic}"`, `Risk if "${topic}" is handled poorly`),
            tx(`Kế hoạch hành động cho "${topic}"`, `Action plan for "${topic}"`)
        ];
        return {
            question: isVi()
                ? `${index + 1}. Thành phần nào cần ưu tiên đầu tiên khi triển khai "${topic}"?`
                : `${index + 1}. Which element should be prioritized first when executing "${topic}"?`,
            options: opts,
            answer: hashToRange(`${topic}:${index}`, 0, 3),
            explanation: isVi()
                ? 'Đáp án dựa trên mức độ tác động và khả năng triển khai ngay.'
                : 'The answer is based on impact and immediate feasibility.'
        };
    });
}

function buildFallbackChartConfig(result) {
    const labels = selectOutputTopics(result, 6);
    const values = labels.map((label, index) => Math.max(3, label.split(/\s+/).filter(Boolean).length + index + 2));

    return {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: result?.title || tx('Mức độ', 'Level'),
                data: values
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    };
}

function deriveChartInsights(chartConfig) {
    const labels = chartConfig?.data?.labels || [];
    const dataset = chartConfig?.data?.datasets?.[0]?.data || [];
    const values = dataset.map((value) => Number(value) || 0);
    const total = values.reduce((sum, value) => sum + value, 0);
    const maxValue = values.length > 0 ? Math.max(...values) : 0;
    const maxIndex = values.findIndex((value) => value === maxValue);
    const average = values.length > 0 ? (total / values.length).toFixed(1) : '0';

    return [
        {
            title: tx('Đỉnh cao nhất', 'Top value'),
            value: labels[maxIndex] || tx('Chưa có dữ liệu', 'No data yet'),
            desc: maxValue > 0 ? `${tx('Giá trị nổi bật', 'Highlighted value')}: ${maxValue}` : tx('Chưa có điểm nhấn rõ ràng.', 'No clear highlight yet.')
        },
        {
            title: tx('Mức trung bình', 'Average level'),
            value: average,
            desc: tx('Giúp bạn đọc nhanh mặt bằng chung của biểu đồ.', 'Helps you quickly scan the overall level of the chart.')
        },
        {
            title: tx('Số hạng mục', 'Item count'),
            value: `${labels.length}`,
            desc: tx('Tổng số nhóm dữ liệu đang được so sánh.', 'The total number of data groups being compared.')
        }
    ];
}

function ensureChartLoaded() {
    if (typeof window !== 'undefined' && window.Chart) {
        return Promise.resolve(window.Chart);
    }

    if (chartLoaderPromise) return chartLoaderPromise;

    chartLoaderPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
        script.onload = () => {
            if (!window.Chart) {
                reject(new Error('Không tải được Chart.js'));
                return;
            }
            resolve(window.Chart);
        };
        script.onerror = () => reject(new Error('Lỗi tải thư viện Chart.js'));
        document.head.appendChild(script);
    });

    return chartLoaderPromise;
}

function ensureD3Loaded() {
    if (typeof window !== 'undefined' && window.d3) {
        return Promise.resolve(window.d3);
    }

    if (d3LoaderPromise) return d3LoaderPromise;

    d3LoaderPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js';
        script.onload = () => {
            if (!window.d3) {
                reject(new Error('Không tải được D3'));
                return;
            }
            resolve(window.d3);
        };
        script.onerror = () => reject(new Error('Lỗi tải thư viện D3'));
        document.head.appendChild(script);
    });

    return d3LoaderPromise;
}

function destroyChartInstance(slot) {
    if (slot === 'workspace' && workspaceChartInstance) {
        workspaceChartInstance.destroy();
        workspaceChartInstance = null;
    }

    if (slot === 'builder' && builderChartInstance) {
        builderChartInstance.destroy();
        builderChartInstance = null;
    }

    if (slot === 'viewer' && viewerChartInstance) {
        viewerChartInstance.destroy();
        viewerChartInstance = null;
    }
}

function setChartInstance(slot, instance) {
    if (slot === 'workspace') workspaceChartInstance = instance;
    if (slot === 'builder') builderChartInstance = instance;
    if (slot === 'viewer') viewerChartInstance = instance;
}

function resolveRenderSlot(options = {}) {
    if (options.fullscreenMode) return 'viewer';
    if (options.source === 'builder') return 'builder';
    return 'workspace';
}

function renderOutputShell(targetEl, config) {
    const stats = Array.isArray(config.stats) ? config.stats.filter(Boolean) : [];
    const statsHtml = stats.length > 0
        ? `<div class="visual-stat-row">${stats.map((item) => `<span class="visual-stat">${escapeHtml(item)}</span>`).join('')}</div>`
        : '';
    const zoomActions = config.showZoom
        ? `
            <button class="btn btn-outline visual-action-btn" data-visual-action="zoom-out">-</button>
            <button class="btn btn-outline visual-action-btn" data-visual-action="zoom-in">+</button>
            <button class="btn btn-outline visual-action-btn" data-visual-action="zoom-reset">Reset</button>
        `
        : '';
    const fullscreenAction = config.allowFullscreen === false
        ? ''
        : `<button class="btn btn-outline visual-action-btn" data-visual-action="fullscreen">${tx('Toàn màn hình', 'Fullscreen')}</button>`;

    targetEl.innerHTML = `
        <div class="visual-shell">
            <div class="visual-toolbar">
                <div class="visual-meta">
                    <h4>${escapeHtml(config.title || tx('Kết quả', 'Result'))}</h4>
                    ${config.subtitle ? `<p>${escapeHtml(config.subtitle)}</p>` : ''}
                </div>
                <div class="visual-actions">
                    ${config.extraActionsHtml || ''}
                    ${zoomActions}
                    ${fullscreenAction}
                </div>
            </div>
            ${statsHtml}
            <div class="visual-body"></div>
        </div>
    `;

    const refs = {
        body: targetEl.querySelector('.visual-body'),
        zoomInBtn: targetEl.querySelector('[data-visual-action="zoom-in"]'),
        zoomOutBtn: targetEl.querySelector('[data-visual-action="zoom-out"]'),
        zoomResetBtn: targetEl.querySelector('[data-visual-action="zoom-reset"]'),
        fullscreenBtn: targetEl.querySelector('[data-visual-action="fullscreen"]')
    };

    refs.fullscreenBtn?.addEventListener('click', () => {
        openFullscreenViewer(config.result, {
            source: config.source || 'workspace',
            editable: config.editable || false
        });
    });

    return refs;
}

function openFullscreenViewer(result, options = {}) {
    if (!el.fullscreenViewer || !el.viewerContent || !result) return;

    el.viewerTitle.textContent = result.title || t('home.viewer.title');
    el.fullscreenViewer.classList.add('active');
    el.fullscreenViewer.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';

    renderVisualResult(result, el.viewerContent, {
        source: options.source || 'workspace',
        editable: options.editable || false,
        allowFullscreen: false,
        fullscreenMode: true
    });
}

function closeFullscreenViewer() {
    if (!el.fullscreenViewer || !el.viewerContent) return;

    destroyChartInstance('viewer');
    el.fullscreenViewer.classList.remove('active');
    el.fullscreenViewer.setAttribute('aria-hidden', 'true');
    el.viewerContent.innerHTML = '';
    document.body.style.overflow = '';

    if (document.fullscreenElement && document.fullscreenElement.contains(el.fullscreenViewer)) {
        document.exitFullscreen?.().catch(() => {});
    }
}

function toggleViewerBrowserFullscreen() {
    if (!el.fullscreenViewer) return;

    if (document.fullscreenElement) {
        document.exitFullscreen?.().catch(() => {});
        return;
    }

    el.fullscreenViewer.requestFullscreen?.().catch(() => {});
}

function buildMindmapHierarchy(result, style = 'orbit') {
    return {
        id: 'root',
        label: result?.title || 'Mindmap',
        icon: '🧠',
        badge: buildTopicBadge(result?.title || 'Mindmap'),
        thumb: buildNodeThumbDataUri(result?.title || 'Mindmap', '🧠', style),
        children: normalizeMindmapNodes(result).map((node, index) => buildMindmapChild(node, 1, index, style))
    };
}

function buildMindmapChild(node, depth, index, style = 'orbit') {
    const label = String(node?.text || node?.label || '').trim();
    const icon = inferTopicIcon(label, depth);
    return {
        id: node?.id || node?.builderBranchId || `node_${depth}_${index + 1}`,
        builderBranchId: node?.builderBranchId || null,
        label,
        icon,
        badge: buildTopicBadge(label),
        thumb: buildNodeThumbDataUri(label, icon, style),
        depth,
        children: (node?.children || []).map((child, childIndex) => buildMindmapChild(child, depth + 1, childIndex, style))
    };
}

function renderMindmapDiagram(result, targetEl, options = {}) {
    const mindmapStyle = resolveMindmapStyle(result?.mindmapStyle || state.workspaceMindmapStyle, result);
    const hierarchyData = buildMindmapHierarchy(result, mindmapStyle);
    const styleAccentMap = {
        orbit: '#8b5cf6',
        radial: '#06b6d4',
        executive: '#1d4ed8',
        neon: '#10b981',
        organic: '#65a30d'
    };
    const accent = result?.builderColor
        || (options.source === 'builder' ? state.builder.color : styleAccentMap[mindmapStyle] || '#8b5cf6');
    const shell = renderOutputShell(targetEl, {
        title: result?.title || 'Mindmap',
        subtitle: options.editable
            ? tx('Chỉ hiện ý chính trước. Bấm nút mũi tên trên node để bung nhánh chi tiết, kéo để pan và cuộn để zoom.', 'Main ideas appear first. Use the arrow button on each node to reveal details, drag to pan, and scroll to zoom.')
            : tx('Chỉ hiện ý chính trước. Bấm nút mũi tên trên node để bung nhánh chi tiết và bấm node để đọc nhanh.', 'Main ideas appear first. Use the arrow button on each node to reveal details and click a node to inspect it.'),
        stats: [
            `${extractResultTopics(result).length} ${tx('ý chính', 'key points')}`,
            options.editable ? tx('Builder trực tiếp', 'Live builder') : tx('Sơ đồ bung nhánh', 'Expandable diagram'),
            `${tx('Style', 'Style')}: ${resolveMindmapStyleLabel(mindmapStyle)}`
        ],
        showZoom: true,
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        editable: options.editable,
        result
    });

    shell.body.innerHTML = `
        <div class="mindmap-layout mindmap-theme-${escapeHtml(mindmapStyle)}">
            <div class="mindmap-canvas">
                <svg class="mindmap-svg" aria-label="Mindmap interactive"></svg>
            </div>
            <aside class="mindmap-inspector">
                <span class="section-kicker">${escapeHtml(tx('Chi tiết node', 'Node details'))}</span>
                <h5>${escapeHtml(result?.title || 'Mindmap')}</h5>
                <p>${escapeHtml(tx('Ý chính sẽ hiện trước. Bấm nút mũi tên trên từng node để bung nhánh chi tiết giống NotebookLM.', 'Main ideas appear first. Use the arrow button on each node to reveal detailed branches similar to NotebookLM.'))}</p>
                <p><strong>${escapeHtml(tx('Style đang dùng', 'Current style'))}:</strong> ${escapeHtml(resolveMindmapStyleLabel(mindmapStyle))}</p>
            </aside>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));

    ensureD3Loaded()
        .then((d3) => {
            const svgEl = shell.body.querySelector('.mindmap-svg');
            const inspector = shell.body.querySelector('.mindmap-inspector');
            const canvas = shell.body.querySelector('.mindmap-canvas');
            if (!svgEl || !inspector || !canvas) return;

            const svg = d3.select(svgEl)
                .attr('preserveAspectRatio', 'xMidYMid meet');
            const graph = svg.append('g');
            const styleNodeSizeMap = {
                orbit: [102, 254],
                radial: [96, 236],
                executive: [108, 268],
                neon: [100, 246],
                organic: [112, 258]
            };
            const nodeSize = styleNodeSizeMap[mindmapStyle] || [100, 246];
            const tree = d3.tree().nodeSize(nodeSize);
            const boxWidth = mindmapStyle === 'executive' ? 210 : 202;
            const boxHeight = 98;
            let selectedNodeId = 'root';

            const root = d3.hierarchy(hierarchyData, (node) => node.children);
            root.x0 = 0;
            root.y0 = 0;

            const collapseBranch = (node) => {
                if (!node.children) return;
                node.children.forEach(collapseBranch);
                node._children = node.children;
                node.children = null;
            };

            root.children?.forEach(collapseBranch);

            const linkPath = d3.linkHorizontal()
                .x((node) => node.y)
                .y((node) => node.x);

            const updateInspector = (node) => {
                const path = node.ancestors().reverse().map((item) => item.data.label).join(' > ');
                const branchCount = (node.children?.length || 0) + (node._children?.length || 0);
                inspector.innerHTML = `
                    <span class="section-kicker">${escapeHtml(tx('Chi tiết node', 'Node details'))}</span>
                    <h5>${escapeHtml(node.data.icon || '✨')} ${escapeHtml(node.data.label)}</h5>
                    <p><strong>${escapeHtml(tx('Đường dẫn', 'Path'))}:</strong> ${escapeHtml(path)}</p>
                    <p><strong>${escapeHtml(tx('Cấp độ', 'Depth'))}:</strong> ${node.depth}</p>
                    <p><strong>${escapeHtml(tx('Nhánh con', 'Child branches'))}:</strong> ${branchCount}</p>
                    <p>${escapeHtml(options.editable ? tx('Nháy đúp để đổi tên node trong Builder. Bấm mũi tên để bung hoặc thu các nhánh con.', 'Double-click to rename the node in Builder. Use the arrow button to expand or collapse child branches.') : tx('Node này thuộc sơ đồ trực quan vừa được tạo từ nội dung của bạn. Bấm mũi tên để xem sâu hơn.', 'This node belongs to the visual diagram generated from your content. Use the arrow button to go deeper.'))}</p>
                `;
            };

            const selectNode = (node) => {
                selectedNodeId = node.data.id;
                shell.body.querySelectorAll('.mindmap-node-card').forEach((card) => card.classList.remove('is-selected'));
                shell.body.querySelector(`[data-node-id="${escapeSelector(node.data.id)}"]`)?.classList.add('is-selected');
                updateInspector(node);

                if (options.editable && node.depth > 0) {
                    state.builder.selectedBranchId = node.data.builderBranchId || node.data.id;
                    if (el.branchInput) {
                        el.branchInput.value = node.data.label || '';
                    }
                    renderBranchList();
                    updateBuilderPrimaryAction();
                }
            };

            const editNode = (node) => {
                if (!options.editable) return;

                const promptLabel = node.depth === 0
                    ? tx('Sửa tiêu đề mindmap', 'Edit mindmap title')
                    : tx('Sửa tên nhánh', 'Edit branch name');
                const nextValue = window.prompt(promptLabel, node.data.label || '');
                const cleaned = String(nextValue || '').trim();
                if (!cleaned || cleaned === node.data.label) return;

                if (node.depth === 0) {
                    state.builder.title = cleaned;
                    if (el.builderTitle) {
                        el.builderTitle.value = cleaned;
                    }
                } else {
                    const branchId = node.data.builderBranchId || node.data.id;
                    const branch = state.builder.branches.find((item) => item.id === branchId);
                    if (!branch) return;
                    branch.text = cleaned;
                    state.builder.selectedBranchId = branch.id;
                    if (el.branchInput) {
                        el.branchInput.value = cleaned;
                    }
                }

                renderBranchList();
                updateBuilderPrimaryAction();
                refreshBuilderPreview(true);
                if (options.fullscreenMode && el.viewerContent) {
                    renderVisualResult(buildBuilderResult(), el.viewerContent, {
                        source: 'builder',
                        editable: true,
                        allowFullscreen: false,
                        fullscreenMode: true
                    });
                }
            };

            const renderNodeCard = (node) => {
                const childCount = (node.children?.length || 0) + (node._children?.length || 0);
                return `
                    <div xmlns="http://www.w3.org/1999/xhtml" class="mindmap-node-card depth-${Math.min(node.depth, 5)}" data-node-id="${escapeHtml(node.data.id)}">
                        <div class="mindmap-node-head">
                            <span class="mindmap-node-icon">${escapeHtml(node.data.icon || '✨')}</span>
                            <span class="mindmap-node-badge">${escapeHtml(node.data.badge || 'SK')}</span>
                            <img class="mindmap-node-thumb" src="${escapeHtml(node.data.thumb || '')}" alt="thumb">
                        </div>
                        <div class="mindmap-node-label">${escapeHtml(node.data.label)}</div>
                        <div class="mindmap-node-meta">${tx('Cấp', 'Depth')} ${node.depth}</div>
                        ${childCount ? `<div class="mindmap-node-branch-count">${childCount} ${escapeHtml(tx('nhánh', 'branches'))}</div>` : ''}
                    </div>
                `;
            };

            const syncSelectedVisualState = (fallbackNode = root) => {
                const visibleNode = root.descendants().find((item) => item.data.id === selectedNodeId) || fallbackNode || root;
                selectedNodeId = visibleNode.data.id;
                shell.body.querySelectorAll('.mindmap-node-card').forEach((card) => {
                    card.classList.toggle('is-selected', card.dataset.nodeId === selectedNodeId);
                });
                shell.body.querySelectorAll('.mindmap-toggle').forEach((toggle) => {
                    toggle.classList.toggle('is-selected', toggle.dataset.nodeId === selectedNodeId);
                });
                updateInspector(visibleNode);
            };

            const toggleNode = (node) => {
                if (node.children) {
                    node._children = node.children;
                    node.children = null;
                } else if (node._children) {
                    node.children = node._children;
                    node._children = null;
                } else {
                    return;
                }
                selectNode(node);
                update(node);
            };

            const update = (source) => {
                tree(root);

                const nodes = root.descendants();
                const links = root.links();
                const minX = d3.min(nodes, (node) => node.x) ?? 0;
                const maxX = d3.max(nodes, (node) => node.x) ?? 0;
                const maxY = d3.max(nodes, (node) => node.y) ?? 0;
                const width = Math.max(canvas.clientWidth || 920, maxY + 360);
                const height = Math.max(460, maxX - minX + 280);

                svg.attr('viewBox', [0, minX - 140, width, height]);

                const transition = svg.transition().duration(260);
                const origin = { x: source.x0 ?? source.x ?? 0, y: source.y0 ?? source.y ?? 0 };
                const linkStroke = mindmapStyle === 'executive'
                    ? 'rgba(30, 64, 175, 0.56)'
                    : (mindmapStyle === 'neon' ? 'rgba(16, 185, 129, 0.62)' : accent);
                const linkDash = mindmapStyle === 'executive' ? '2 7' : (mindmapStyle === 'organic' ? '4 5' : '0');
                const linkOpacity = mindmapStyle === 'neon' ? 0.6 : 0.42;
                const linkWidth = mindmapStyle === 'executive' ? 2.6 : 2.2;

                const linkSelection = graph.selectAll('path.mindmap-link')
                    .data(links, (node) => node.target.data.id);

                linkSelection.enter()
                    .append('path')
                    .attr('class', 'mindmap-link')
                    .attr('fill', 'none')
                    .attr('stroke', linkStroke)
                    .attr('stroke-opacity', linkOpacity)
                    .attr('stroke-width', linkWidth)
                    .attr('stroke-dasharray', linkDash)
                    .attr('d', linkPath({ source: origin, target: origin }))
                    .merge(linkSelection)
                    .transition(transition)
                    .attr('stroke', linkStroke)
                    .attr('stroke-opacity', linkOpacity)
                    .attr('stroke-width', linkWidth)
                    .attr('stroke-dasharray', linkDash)
                    .attr('d', linkPath);

                linkSelection.exit()
                    .transition(transition)
                    .attr('d', linkPath({ source: origin, target: origin }))
                    .remove();

                const nodeSelection = graph.selectAll('g.mindmap-node-group')
                    .data(nodes, (node) => node.data.id);

                const nodeEnter = nodeSelection.enter()
                    .append('g')
                    .attr('class', 'mindmap-node-group')
                    .attr('transform', `translate(${origin.y},${origin.x})`)
                    .style('cursor', 'pointer');

                nodeEnter.append('foreignObject')
                    .attr('x', -boxWidth / 2)
                    .attr('y', -boxHeight / 2)
                    .attr('width', boxWidth)
                    .attr('height', boxHeight)
                    .html(renderNodeCard);

                const toggleEnter = nodeEnter.append('g')
                    .attr('class', 'mindmap-toggle');

                toggleEnter.append('circle')
                    .attr('class', 'mindmap-toggle-circle')
                    .attr('r', 15);

                toggleEnter.append('text')
                    .attr('class', 'mindmap-toggle-icon')
                    .attr('text-anchor', 'middle')
                    .attr('dy', '0.35em');

                const nodeMerge = nodeEnter.merge(nodeSelection);

                nodeMerge.transition(transition)
                    .attr('transform', (node) => `translate(${node.y},${node.x})`);

                nodeMerge.select('foreignObject').html(renderNodeCard);

                nodeMerge.select('.mindmap-toggle')
                    .attr('data-node-id', (node) => node.data.id)
                    .attr('transform', `translate(${boxWidth / 2 - 20},${-boxHeight / 2 + 18})`)
                    .style('display', (node) => ((node.children?.length || 0) + (node._children?.length || 0)) > 0 ? null : 'none');

                nodeMerge.select('.mindmap-toggle-circle')
                    .classed('is-open', (node) => Boolean(node.children))
                    .classed('is-closed', (node) => Boolean(node._children));

                nodeMerge.select('.mindmap-toggle-icon')
                    .text((node) => node.children ? '▾' : '▸');

                nodeSelection.exit()
                    .transition(transition)
                    .attr('transform', `translate(${origin.y},${origin.x})`)
                    .remove();

                nodeMerge.on('click', (event, node) => {
                    event.preventDefault();
                    selectNode(node);
                });

                nodeMerge.on('dblclick', (event, node) => {
                    event.preventDefault();
                    editNode(node);
                });

                nodeMerge.select('.mindmap-toggle').on('click', (event, node) => {
                    event.preventDefault();
                    event.stopPropagation();
                    toggleNode(node);
                });

                nodes.forEach((node) => {
                    node.x0 = node.x;
                    node.y0 = node.y;
                });

                syncSelectedVisualState(source);
            };

            const zoom = d3.zoom()
                .scaleExtent([0.45, 2.3])
                .on('zoom', (event) => {
                    graph.attr('transform', event.transform);
                });

            const initialTransform = d3.zoomIdentity
                .translate(140, 0)
                .scale(options.fullscreenMode ? 0.94 : 0.84);

            svg.call(zoom).call(zoom.transform, initialTransform);

            shell.zoomInBtn?.addEventListener('click', () => svg.transition().duration(180).call(zoom.scaleBy, 1.15));
            shell.zoomOutBtn?.addEventListener('click', () => svg.transition().duration(180).call(zoom.scaleBy, 0.86));
            shell.zoomResetBtn?.addEventListener('click', () => svg.transition().duration(220).call(zoom.transform, initialTransform));

            update(root);
            selectNode(root);
        })
        .catch((error) => {
            console.error('Mindmap render error:', error);
            shell.body.innerHTML = `
                <div class="mindmap-empty">
                    <p class="preview-empty">Không thể dựng mindmap tương tác. Hiển thị dạng cây thay thế.</p>
                    ${renderMindmapTree(result?.nodes || [])}
                </div>
            `;
        });
}

function renderChartDiagram(result, targetEl, options = {}) {
    const slot = resolveRenderSlot(options);
    const shell = renderOutputShell(targetEl, {
        title: result?.title || 'Chart',
        subtitle: tx('Biểu đồ có tooltip, legend và phần đọc nhanh dữ liệu.', 'The chart includes tooltips, a legend, and a quick insight panel.'),
        stats: [`${extractResultTopics(result).length} ${tx('nhãn', 'labels')}`, tx('Chart tương tác', 'Interactive chart')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="chart-layout">
            <div class="preview-chart-wrap chart-surface">
                <canvas class="preview-chart-canvas"></canvas>
            </div>
            <div class="insight-panel"></div>
        </div>
    `;

    const canvas = shell.body.querySelector('canvas');
    const insightPanel = shell.body.querySelector('.insight-panel');
    const baseConfig = result?.chartConfig || buildFallbackChartConfig(result);
    const chartConfig = JSON.parse(JSON.stringify(baseConfig));
    const palette = ['#60a5fa', '#8b5cf6', '#2dd4bf', '#f59e0b', '#fb7185', '#22c55e'];

    chartConfig.data = chartConfig.data || {};
    chartConfig.data.datasets = (chartConfig.data.datasets || []).map((dataset, index) => ({
        borderRadius: 12,
        tension: 0.34,
        fill: false,
        borderWidth: 2,
        ...dataset,
        backgroundColor: dataset.backgroundColor || palette.map((_, paletteIndex) => palette[paletteIndex % palette.length]),
        borderColor: dataset.borderColor || palette[index % palette.length]
    }));
    chartConfig.options = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
            legend: {
                labels: {
                    color: document.body.classList.contains('dark-mode') || document.body.classList.contains('galaxy-mode')
                        ? '#e5eefc'
                        : '#1f2937'
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    color: document.body.classList.contains('dark-mode') || document.body.classList.contains('galaxy-mode')
                        ? '#d7e0ef'
                        : '#334155'
                },
                grid: { color: 'rgba(148, 163, 184, 0.16)' }
            },
            y: {
                ticks: {
                    color: document.body.classList.contains('dark-mode') || document.body.classList.contains('galaxy-mode')
                        ? '#d7e0ef'
                        : '#334155'
                },
                grid: { color: 'rgba(148, 163, 184, 0.16)' }
            }
        },
        ...(chartConfig.options || {})
    };

    insightPanel.innerHTML = deriveChartInsights(chartConfig).map((item) => `
        <div class="insight-card">
            <h5>${escapeHtml(item.title)}</h5>
            <p><strong>${escapeHtml(item.value)}</strong></p>
            <p>${escapeHtml(item.desc)}</p>
        </div>
    `).join('');

    destroyChartInstance(slot);
    ensureChartLoaded()
        .then((ChartLib) => {
            if (!canvas) return;
            const instance = new ChartLib(canvas, chartConfig);
            setChartInstance(slot, instance);
        })
        .catch((error) => {
            console.error('Chart render error:', error);
            shell.body.innerHTML = '<p class="preview-empty">Không thể dựng biểu đồ tương tác.</p>';
        });
}

function renderFlashcardDeck(result, targetEl, options = {}) {
    const cards = deriveFlashcards(result);
    const shell = renderOutputShell(targetEl, {
        title: result?.title || t('common.flashcard'),
        subtitle: tx('Bấm vào từng thẻ để lật mặt trước và mặt sau.', 'Click each card to flip between the front and back.'),
        stats: [`${cards.length} ${tx('thẻ', 'cards')}`, tx('Ôn tập tương tác', 'Interactive review')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result,
        extraActionsHtml: `<button class="btn btn-outline visual-action-btn" data-visual-action="shuffle">${escapeHtml(tx('Xáo thẻ', 'Shuffle cards'))}</button>`
    });

    const shuffleBtn = targetEl.querySelector('[data-visual-action="shuffle"]');

    const renderCards = (items) => {
        shell.body.innerHTML = `
            <div class="flashcard-board">
                <div class="flashcard-grid">
                    ${items.map((card) => `
                        <div class="flashcard-card">
                            <div class="flashcard-card-inner">
                                <article class="flashcard-face front">
                                    <span class="flashcard-tag">${escapeHtml(card.tag)}</span>
                                    <div class="flashcard-title">${escapeHtml(card.front)}</div>
                                    <div class="flashcard-desc">${escapeHtml(tx('Bấm để xem phần gợi ý hoặc diễn giải.', 'Click to view the hint or explanation.'))}</div>
                                </article>
                                <article class="flashcard-face back">
                                    <span class="flashcard-tag">${escapeHtml(tx('Mặt sau', 'Back side'))}</span>
                                    <div class="flashcard-title">${escapeHtml(card.front)}</div>
                                    <div class="flashcard-desc">${escapeHtml(card.back)}</div>
                                </article>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        shell.body.querySelectorAll('.flashcard-card').forEach((cardEl) => {
            cardEl.addEventListener('click', () => {
                cardEl.classList.toggle('is-flipped');
            });
        });
    };

    shuffleBtn?.addEventListener('click', () => {
        const shuffled = [...cards].sort(() => Math.random() - 0.5);
        renderCards(shuffled);
    });

    renderCards(cards);
    destroyChartInstance(resolveRenderSlot(options));
}

function renderPresentationDeck(result, targetEl, options = {}) {
    const slides = deriveSlides(result);
    let activeIndex = 0;
    const shell = renderOutputShell(targetEl, {
        title: result?.title || t('common.presentation'),
        subtitle: tx('Đi qua từng slide để đọc theo luồng ngắn gọn và trực quan.', 'Move through each slide in a concise and visual flow.'),
        stats: [`${slides.length} slide`, tx('Điều hướng tương tác', 'Interactive navigation')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result,
        extraActionsHtml: `
            <button class="btn btn-outline visual-action-btn" data-visual-action="prev-slide">Trước</button>
            <button class="btn btn-outline visual-action-btn" data-visual-action="next-slide">Sau</button>
        `
    });

    const prevBtn = targetEl.querySelector('[data-visual-action="prev-slide"]');
    const nextBtn = targetEl.querySelector('[data-visual-action="next-slide"]');

    const updateSlide = () => {
        const slide = slides[activeIndex];
        if (!slide) {
            shell.body.innerHTML = '<p class="preview-empty">Chưa có slide để hiển thị.</p>';
            return;
        }

        shell.body.innerHTML = `
            <div class="presentation-board">
                <div class="slide-nav">
                    <span class="slide-progress">Slide ${activeIndex + 1}/${slides.length}</span>
                </div>
                <div class="presentation-stage">
                    <div class="slide-shell">
                        <div class="slide-main">
                            <span class="slide-kicker">${escapeHtml(slide.kicker)}</span>
                            <h3 class="slide-title">${escapeHtml(slide.icon || '✨')} ${escapeHtml(slide.title)}</h3>
                            <div class="slide-points">
                                ${slide.bullets.map((bullet) => `<div class="slide-point">${escapeHtml(bullet)}</div>`).join('')}
                            </div>
                        </div>
                        <aside class="slide-side">
                            <span class="section-kicker">Ghi chú</span>
                            <p>Slide này phù hợp để trình bày nhanh hoặc chuyển sang báo cáo.</p>
                            <p><strong>Tập trung:</strong> ${escapeHtml(slide.title)}</p>
                            <p><strong>${escapeHtml(tx('Visual cue', 'Visual cue'))}:</strong> ${escapeHtml(slide.visualCue)}</p>
                            <p><strong>${escapeHtml(tx('Presenter', 'Presenter'))}:</strong> ${escapeHtml(slide.presenterNote)}</p>
                        </aside>
                    </div>
                </div>
            </div>
        `;
    };

    prevBtn?.addEventListener('click', () => {
        activeIndex = (activeIndex - 1 + slides.length) % Math.max(slides.length, 1);
        updateSlide();
    });

    nextBtn?.addEventListener('click', () => {
        activeIndex = (activeIndex + 1) % Math.max(slides.length, 1);
        updateSlide();
    });

    updateSlide();
    destroyChartInstance(resolveRenderSlot(options));
}

function renderReportBoard(result, targetEl, options = {}) {
    const sections = deriveSections(result);
    const shell = renderOutputShell(targetEl, {
        title: result?.title || t('common.report'),
        subtitle: tx('Đọc theo từng mục và mở rộng chi tiết bằng accordion.', 'Read section by section and expand details with accordions.'),
        stats: [`${sections.length} ${tx('phần', 'sections')}`, tx('Bố cục báo cáo', 'Report layout')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="report-board">
            <section class="report-summary">
                <h4>${escapeHtml(result?.title || t('common.report'))}</h4>
                <p>${escapeHtml((result?.summary || []).join(' • ') || tx('Bản tóm tắt tổng hợp từ nội dung của bạn.', 'A synthesized summary generated from your content.'))}</p>
            </section>
            <div class="report-grid">
                ${sections.map((section, index) => `
                    <details class="report-section" ${index === 0 ? 'open' : ''}>
                        <summary>${escapeHtml(section.label)} - ${escapeHtml(section.title)}</summary>
                        <div class="report-section-body">
                            ${section.body.map((line) => `<p>${escapeHtml(line)}</p>`).join('')}
                        </div>
                    </details>
                `).join('')}
            </div>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderInfographicBoard(result, targetEl, options = {}) {
    const blocks = deriveInfoBlocks(result);
    const shell = renderOutputShell(targetEl, {
        title: result?.title || tx('Bảng đồ họa', 'Infographic'),
        subtitle: tx('Các thẻ nội dung nhiều màu, dễ đọc và dễ quét nhanh.', 'Colorful content cards designed for quick scanning.'),
        stats: [`${blocks.length} ${tx('khối', 'blocks')}`, tx('Bố cục infographic', 'Infographic layout')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="infographic-board">
            <div class="infographic-grid">
                ${blocks.map((block) => `
                    <article class="info-card ${block.variant}">
                        <div class="info-card-index">${tx('Khối', 'Block')} ${escapeHtml(block.index)}</div>
                        <div>
                            <h5>${escapeHtml(block.icon || '✨')} ${escapeHtml(block.title)}</h5>
                            <p>${escapeHtml(block.desc)}</p>
                            <div class="info-card-meta">
                                <span class="info-card-metric">${escapeHtml(block.metric)}</span>
                                <span class="info-card-action">${escapeHtml(block.action)}</span>
                            </div>
                        </div>
                    </article>
                `).join('')}
            </div>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderDashboardBoard(result, targetEl, options = {}) {
    const kpis = deriveDashboardMetrics(result);
    const sections = deriveSections(result).slice(0, 4);
    const shell = renderOutputShell(targetEl, {
        title: result?.title || tx('Dashboard điều hành', 'Operational dashboard'),
        subtitle: tx('Bảng điều khiển tương tác để đọc nhanh chỉ số và ưu tiên triển khai.', 'Interactive board to scan metrics and execution priorities quickly.'),
        stats: [`${kpis.length} KPI`, tx('Realtime board', 'Realtime board')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="dashboard-shell">
            <section>
                <div class="dashboard-kpi-grid">
                    ${kpis.map((kpi) => `
                        <article class="dashboard-kpi-card">
                            <span class="label">${escapeHtml(kpi.label)}</span>
                            <strong class="value">${escapeHtml(kpi.value)}</strong>
                            <span class="kpi-delta ${escapeHtml(kpi.trend)}">${escapeHtml(kpi.trend === 'down' ? '▼' : (kpi.trend === 'flat' ? '■' : '▲'))} ${escapeHtml(kpi.delta)}</span>
                            <p>${escapeHtml(kpi.desc)}</p>
                        </article>
                    `).join('')}
                </div>
            </section>
            <aside class="insight-panel">
                ${sections.map((section) => `
                    <article class="insight-card">
                        <h5>${escapeHtml(section.title)}</h5>
                        <p>${escapeHtml(section.body[0] || '')}</p>
                    </article>
                `).join('')}
            </aside>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderPodcastStudio(result, targetEl, options = {}) {
    const duel = derivePodcastDuel(result);
    const shell = renderOutputShell(targetEl, {
        title: duel.title,
        subtitle: tx('Podcast duel mô phỏng hai góc nhìn trái chiều từ cùng nguồn dữ liệu.', 'Podcast duel simulates two opposing views from the same source data.'),
        stats: [`${duel.lines.length} ${tx('lượt thoại', 'dialog turns')}`, tx('Audio concept', 'Audio concept')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="podcast-stage">
            <div class="podcast-head">
                <h4>${escapeHtml(tx('Podcast Duel Room', 'Podcast Duel Room'))}</h4>
                <span class="podcast-status">${escapeHtml(tx('On-air', 'On-air'))}</span>
            </div>
            <div class="podcast-duel-grid">
                ${duel.hosts.map((host) => `
                    <article class="podcast-voice-card">
                        <h5>${escapeHtml(host.icon || '🎙️')} ${escapeHtml(host.name || '')}</h5>
                        <p>${escapeHtml(host.tone || tx('Giọng đọc mô phỏng chuyên gia theo bối cảnh chủ đề.', 'Voice profile tuned for topic-specific expert tone.'))}</p>
                    </article>
                `).join('')}
            </div>
            <div class="podcast-lines">
                ${duel.lines.map((line) => `
                    <div class="podcast-line"><strong>${escapeHtml(line.speaker)}:</strong> ${escapeHtml(line.text)}</div>
                `).join('')}
            </div>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderVideoStudio(result, targetEl, options = {}) {
    const video = deriveVideoStoryboard(result);
    const shell = renderOutputShell(targetEl, {
        title: video.title,
        subtitle: tx('Kịch bản video AI gồm presenter, script và timeline từng cảnh.', 'AI video script with presenter, narration, and shot timeline.'),
        stats: [`${video.shots.length} ${tx('cảnh', 'shots')}`, tx('Cinematic flow', 'Cinematic flow')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="video-stage">
            <div class="video-frame">
                <section class="video-script">
                    <h4>${escapeHtml(tx('Script highlights', 'Script highlights'))}</h4>
                    ${video.scriptLines.map((line) => `<div class="video-script-line">${escapeHtml(line)}</div>`).join('')}
                </section>
                <aside class="video-presenter">
                    <div class="presenter-avatar" aria-hidden="true"></div>
                    <h5>${escapeHtml(video.presenter)}</h5>
                    <p>${escapeHtml(tx('Avatar presenter đồng bộ nhịp nói và chuyển cảnh.', 'Presenter avatar synced with narration rhythm and transitions.'))}</p>
                </aside>
            </div>
            <div class="video-timeline">
                ${video.shots.map((shot) => `
                    <div class="video-shot">
                        <strong>${escapeHtml(shot.time)} · ${escapeHtml(shot.camera || 'Cut')}</strong>
                        <p>${escapeHtml(shot.title)}</p>
                        <small>${escapeHtml(shot.icon || '✨')} ${escapeHtml(shot.action || '')}</small>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderQuizArenaBoard(result, targetEl, options = {}) {
    const questions = deriveQuizArena(result);
    const total = questions.length;
    const score = hashToRange(`${result?.title || ''}:${total}`, Math.max(0, total - 2), Math.max(1, total));

    const shell = renderOutputShell(targetEl, {
        title: result?.title || tx('AI Test Arena', 'AI Test Arena'),
        subtitle: tx('Bài kiểm tra sinh từ nguồn dữ liệu và hội thoại để khóa đúng lỗ hổng kiến thức.', 'Assessment generated from source data and chat context to target knowledge gaps.'),
        stats: [`${total} ${tx('câu hỏi', 'questions')}`, tx('Arena lock mode', 'Arena lock mode')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="quiztest-board">
            <div class="quiztest-meta">
                <span class="quiztest-pill">${escapeHtml(tx('Chế độ', 'Mode'))}: Arena Lock</span>
                <span class="quiztest-pill">${escapeHtml(tx('Nguồn', 'Source'))}: ${escapeHtml(tx('Notebook + Workspace', 'Notebook + Workspace'))}</span>
            </div>
            ${questions.map((question, index) => `
                <article class="quiztest-question-card">
                    <h5>${escapeHtml(tx('Câu', 'Question'))} ${index + 1}: ${escapeHtml(question.question)}</h5>
                    <div class="quiztest-options">
                        ${(question.options || []).map((option, optionIndex) => `
                            <button class="quiztest-option ${optionIndex === question.answer ? 'is-correct' : ''}" type="button">
                                ${escapeHtml(String.fromCharCode(65 + optionIndex))}. ${escapeHtml(option)}
                            </button>
                        `).join('')}
                    </div>
                    ${question.explanation ? `<p>${escapeHtml(question.explanation)}</p>` : ''}
                </article>
            `).join('')}
            <div class="quiztest-score">
                <strong>${escapeHtml(tx('Điểm gợi ý', 'Estimated score'))}: ${score}/${Math.max(total, 1)}</strong>
                <p>${escapeHtml(tx('AI gợi ý ôn lại các câu sai trước khi mở vòng mới.', 'AI recommends reviewing missed items before launching a new round.'))}</p>
            </div>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderGenericStructuredOutput(result, targetEl, options = {}) {
    const sections = deriveSections(result);
    const shell = renderOutputShell(targetEl, {
        title: result?.title || tx('Kết quả', 'Result'),
        subtitle: tx('Bản trình bày trực quan được dựng từ nội dung vừa tạo.', 'A visual presentation generated from the content you just created.'),
        stats: [`${sections.length} ${tx('mục', 'items')}`, tx('Tương tác cơ bản', 'Basic interaction')],
        allowFullscreen: options.allowFullscreen,
        source: options.source,
        result
    });

    shell.body.innerHTML = `
        <div class="report-board">
            <div class="report-grid">
                ${sections.map((section) => `
                    <article class="insight-card">
                        <h5>${escapeHtml(section.title)}</h5>
                        ${section.body.map((line) => `<p>${escapeHtml(line)}</p>`).join('')}
                    </article>
                `).join('')}
            </div>
        </div>
    `;

    destroyChartInstance(resolveRenderSlot(options));
}

function renderVisualResult(result, targetEl, options = {}) {
    if (!targetEl) return;

    if (!result) {
        targetEl.innerHTML = `<p class="preview-empty">${escapeHtml(tx('Chưa có dữ liệu để hiển thị.', 'No data to display.'))}</p>`;
        destroyChartInstance(resolveRenderSlot(options));
        return;
    }

    if (result.type === 'mindmap') {
        renderMindmapDiagram(result, targetEl, options);
        return;
    }

    if (result.type === 'chart') {
        renderChartDiagram(result, targetEl, options);
        return;
    }

    if (result.type === 'flashcard') {
        renderFlashcardDeck(result, targetEl, options);
        return;
    }

    if (result.type === 'presentation') {
        renderPresentationDeck(result, targetEl, options);
        return;
    }

    if (result.type === 'report') {
        renderReportBoard(result, targetEl, options);
        return;
    }

    if (result.type === 'infographic') {
        renderInfographicBoard(result, targetEl, options);
        return;
    }

    if (result.type === 'dashboard') {
        renderDashboardBoard(result, targetEl, options);
        return;
    }

    if (result.type === 'podcast') {
        renderPodcastStudio(result, targetEl, options);
        return;
    }

    if (result.type === 'video') {
        renderVideoStudio(result, targetEl, options);
        return;
    }

    if (result.type === 'quiztest') {
        renderQuizArenaBoard(result, targetEl, options);
        return;
    }

    if (result.type === 'comic') {
        renderComicStudio(result, targetEl, options);
        return;
    }

    if (result.type === 'book') {
        renderBookStudio(result, targetEl, options);
        return;
    }

    renderGenericStructuredOutput(result, targetEl, options);
}

// ── Comic studio: real sequential comic script (scene + narration + dialogue) ──
function renderComicStudio(result, targetEl, options = {}) {
    if (!targetEl) return;
    const title = result?.title || tx('Truyện tranh', 'Comic');
    const logline = result?.logline || '';
    let panels = Array.isArray(result?.panels) ? result.panels.filter(p => p && (p.scene || p.caption || (p.dialogue && p.dialogue.length))) : [];
    if (!panels.length) {
        panels = collectStudioScenes(result, 6).map((scene) => ({ scene, caption: '', dialogue: [], sfx: '' }));
    }
    const palette = ['#6366f1', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#8b5cf6'];
    const emoji = ['💥', '🗯️', '✨', '🔥', '🎬', '🌀'];

    const panelHtml = panels.map((p, i) => {
        const grad = `linear-gradient(135deg,${palette[i % palette.length]},${palette[(i + 2) % palette.length]})`;
        const caption = p.caption ? `<div class="comic-caption">${escapeHtml(p.caption)}</div>` : '';
        const scene = p.scene ? `<p class="comic-scene">${escapeHtml(p.scene)}</p>` : '';
        const sfx = p.sfx ? `<span class="comic-sfx" style="background:${grad};">${escapeHtml(p.sfx)}</span>` : '';
        const bubbles = (p.dialogue || []).map((d) => `
            <div class="comic-bubble">
                ${d.speaker && d.speaker !== '—' ? `<span class="comic-speaker">${escapeHtml(d.speaker)}</span>` : ''}
                <span class="comic-line">${escapeHtml(d.text || '')}</span>
            </div>`).join('');
        return `
        <figure class="comic-panel">
            <div class="comic-panel-head" style="background:${grad};">
                <span class="comic-panel-no">${tx('Khung', 'Panel')} ${i + 1}</span>
                <span class="comic-panel-icon">${emoji[i % emoji.length]}</span>
            </div>
            <div class="comic-panel-body">
                ${caption}
                ${scene}
                ${sfx}
                ${bubbles ? `<div class="comic-bubbles">${bubbles}</div>` : ''}
            </div>
        </figure>`;
    }).join('');

    targetEl.classList?.remove('hidden');
    targetEl.innerHTML = `
        <div class="comic-studio">
            <div class="comic-header">
                <span class="comic-mast">👀 ${tx('TRUYỆN TRANH', 'COMIC')}</span>
                <h4 class="comic-title">${escapeHtml(title)}</h4>
                ${logline ? `<p class="comic-logline">${escapeHtml(logline)}</p>` : ''}
            </div>
            <div class="comic-grid">${panelHtml}</div>
        </div>`;
}

// ── Book studio: real short book with cover, blurb and readable chapter prose ──
function renderBookStudio(result, targetEl, options = {}) {
    if (!targetEl) return;
    const title = result?.title || tx('Sách', 'Book');
    const subtitle = result?.subtitle || '';
    const blurb = result?.blurb || '';
    let chapters = Array.isArray(result?.chapters) ? result.chapters.filter(c => c && (c.title || (c.paragraphs && c.paragraphs.length))) : [];
    if (!chapters.length) {
        chapters = collectStudioChapters(result, 8).map((c) => ({ title: c.title, summary: '', paragraphs: c.points }));
    }

    const toc = chapters.map((ch, i) => `
        <li class="book-toc-item" data-chapter="${i}">
            <span class="book-toc-no">${i + 1}</span>
            <span class="book-toc-title">${escapeHtml(ch.title || `${tx('Chương', 'Chapter')} ${i + 1}`)}</span>
        </li>`).join('');

    const reader = chapters.map((ch, i) => {
        const paras = (ch.paragraphs || []).map((p) => `<p class="book-para">${escapeHtml(p)}</p>`).join('');
        return `
        <article class="book-chapter" id="book-chapter-${i}">
            <header class="book-chapter-head">
                <span class="book-chapter-no">${tx('Chương', 'Chapter')} ${i + 1}</span>
                <h5 class="book-chapter-title">${escapeHtml(ch.title || '')}</h5>
                ${ch.summary ? `<p class="book-chapter-summary">${escapeHtml(ch.summary)}</p>` : ''}
            </header>
            <div class="book-chapter-body">${paras || `<p class="book-para">${escapeHtml(tx('Chưa có nội dung.', 'No content yet.'))}</p>`}</div>
        </article>`;
    }).join('');

    targetEl.classList?.remove('hidden');
    targetEl.innerHTML = `
        <div class="book-studio">
            <aside class="book-rail">
                <div class="book-cover">
                    <span class="book-cover-icon">📖</span>
                    <strong class="book-cover-title">${escapeHtml(title)}</strong>
                    ${subtitle ? `<span class="book-cover-subtitle">${escapeHtml(subtitle)}</span>` : ''}
                    <span class="book-cover-meta">${chapters.length} ${tx('chương', 'chapters')}</span>
                </div>
                ${blurb ? `<p class="book-blurb">${escapeHtml(blurb)}</p>` : ''}
                <div class="book-toc-label">${tx('Mục lục', 'Contents')}</div>
                <ul class="book-toc">${toc}</ul>
            </aside>
            <div class="book-reader">${reader}</div>
        </div>`;

    targetEl.querySelectorAll('.book-toc-item').forEach((el) => {
        el.addEventListener('click', () => {
            const idx = el.getAttribute('data-chapter');
            const target = targetEl.querySelector(`#book-chapter-${idx}`);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });
}

// Flatten a studio result into a list of "scene" strings (fallback for comics).
function collectStudioScenes(result, max = 6) {
    const out = [];
    const seen = new Set();
    const add = (v) => {
        const s = String(v || '').trim();
        if (s && !seen.has(s) && s.length > 1) { seen.add(s); out.push(s); }
    };
    (result?.topics || []).forEach(add);
    (result?.nodes || []).forEach((n) => { add(n?.label || n?.title); (n?.children || []).forEach((c) => add(c?.label || c?.title)); });
    if (!out.length) add(tx('Chưa có nội dung — hãy thêm nguồn hoặc nhập ý tưởng.', 'No content yet — add a source or enter an idea.'));
    return out.slice(0, max);
}

// Flatten a studio result into chapters (title + sub-points) — fallback for books.
function collectStudioChapters(result, max = 8) {
    const nodes = Array.isArray(result?.nodes) ? result.nodes : [];
    let chapters = nodes.map((n) => ({
        title: String(n?.label || n?.title || '').trim(),
        points: (n?.children || []).map((c) => String(c?.label || c?.title || '').trim()).filter(Boolean).slice(0, 4)
    })).filter((c) => c.title);
    if (!chapters.length) {
        chapters = (result?.topics || []).map((tp) => ({ title: String(tp || '').trim(), points: [] })).filter((c) => c.title);
    }
    if (!chapters.length) chapters = [{ title: tx('Chương 1: Giới thiệu', 'Chapter 1: Introduction'), points: [] }];
    return chapters.slice(0, max);
}

function renderPreview(result, targetEl) {
    if (!targetEl) return;

    if (!result) {
        targetEl.innerHTML = `<p class="preview-empty">${escapeHtml(tx('Chưa có dữ liệu.', 'No data yet.'))}</p>`;
        return;
    }

    // Unhide the minimalist viewport
    targetEl.classList.remove('hidden');

    const topics = extractResultTopics(result);
    const summary = Array.isArray(result?.summary) ? result.summary : [];

    if (result.type === 'mindmap') {
        const styleLabel = resolveMindmapStyleLabel(resolveMindmapStyle(result?.mindmapStyle || state.workspaceMindmapStyle, result));
        targetEl.innerHTML = `
            <h4>${escapeHtml(result.title || t('common.mindmap'))}</h4>
            ${renderMindmapTree(result.nodes || [])}
            <span class="preview-chip">${escapeHtml(tx('Style', 'Style'))}: ${escapeHtml(styleLabel)}</span>
            ${summary.map((item) => `<span class="preview-chip">${escapeHtml(item)}</span>`).join('')}
        `;
        return;
    }

    if (result.type === 'comic') { renderComicStudio(result, targetEl); return; }
    if (result.type === 'book') { renderBookStudio(result, targetEl); return; }

    targetEl.innerHTML = `
        <div class="preview-header">
            <h4>${escapeHtml(result.title || tx('Tổng hợp nội dung', 'Synthesis Content'))}</h4>
            <div class="result-badge">${escapeHtml(result.type || 'General')}</div>
        </div>
        <div class="preview-body">
            ${topics.length > 0 ? `
                <div class="topic-grid">
                    ${topics.map(topic => `
                        <div class="topic-card">
                            <span class="topic-dot"></span>
                            <span class="topic-text">${escapeHtml(topic)}</span>
                        </div>
                    `).join('')}
                </div>
            ` : `<p class="preview-empty">Dữ liệu đang được phân tích...</p>`}
        </div>
        <div class="preview-footer">
            ${summary.map((item) => `<span class="preview-chip">${escapeHtml(item)}</span>`).join('')}
        </div>
    `;
}

function renderVisualOutput(result) {
    renderVisualResult(result, el.workspaceVisualOutput, {
        source: 'workspace',
        editable: false,
        allowFullscreen: true
    });
}

async function onWorkspaceGenerate(typeOverride = null) {
    if (state.isGenerating) return;
    if (typeOverride && typeof typeOverride === 'string') {
        state.workspaceType = normalizeWorkspaceType(typeOverride);
    }

    const project = getCurrentProject();
    if (!project) {
        setStatus(t('status.selectProject'), 'error');
        return;
    }

    setGenerateLoading(true);
    setStatus(t('status.generating'), 'info');
    startGenerateProgress();

    // Collect notebook sources if this is a synthesis request
    if (typeOverride && project.notebook.sources.length > 0) {
        const context = project.notebook.sources.map(s => `[Source: ${s.name}]\n${s.content || ''}`).join('\n\n');
        try {
            const result = await generateModelOutput(state.workspaceType, `Yêu cầu: Tổng hợp các nguồn sau đây thành ${state.workspaceType}.\n\nNguồn dữ liệu:\n${context}`);
            renderPreview(result, el.studioPreview);
            finishGenerateProgress(true);
            return;
        } catch (err) {
            console.error(err);
        }
    }

    try {
        let result = null;
        let seedForMeta = '';

        if (state.workspaceType === 'mindmap') {
            if (state.workspaceMode === 'text') {
                const prompt = el.workspacePrompt?.value.trim() || '';
                if (!prompt) {
                    setStatus(t('status.enterRequest'), 'error');
                    finishGenerateProgress(false);
                    return;
                }
                seedForMeta = prompt;
                try {
                    result = await generateMindmapFromText(prompt);
                } catch {
                    result = await generateModelOutput('mindmap', prompt);
                }
            } else {
                if (!state.workspaceFile) {
                    setStatus(t('status.uploadFirst'), 'error');
                    finishGenerateProgress(false);
                    return;
                }
                seedForMeta = state.workspaceFile.name;
                try {
                    result = await generateMindmapFromFile(state.workspaceFile);
                } catch {
                    result = await generateModelOutput('mindmap', state.workspaceFile.name);
                }
            }
        } else {
            const seed = extractSeedText();
            if (!seed) {
                setStatus(t('status.provideInput'), 'error');
                finishGenerateProgress(false);
                return;
            }
            seedForMeta = seed;
            try {
                result = await generateModelOutput(state.workspaceType, seed);
            } catch {
                result = createGenericOutput(state.workspaceType, seed);
            }
        }

        result = attachWorkspaceVisualMeta(result, seedForMeta);

        project.workspace.lastResult = result;
        project.workspace.mode = state.workspaceMode;
        project.workspace.type = state.workspaceType;
        project.workspace.prompt = el.workspacePrompt?.value.trim() || '';

        renderPreview(result, el.studioPreview);
        renderVisualOutput(result);
        persistCurrentProject();
        finishGenerateProgress(true);
        setStatus(t('status.generated'), 'success');
    } catch (error) {
        console.error(error);
        finishGenerateProgress(false);
        setStatus(t('status.generateError'), 'error');
    } finally {
        setTimeout(() => {
            setGenerateLoading(false);
            resetGenerateProgressUI();
        }, 900);
    }
}

function templatePayload(key) {
    const map = {
        study: {
            prompt: tx('Lập kế hoạch học tập 4 tuần theo từng chủ đề, gồm mục tiêu, tài liệu và bài tập.', 'Create a four-week study plan by topic, including goals, materials, and exercises.'),
            type: 'mindmap'
        },
        research: {
            prompt: tx('Tổng hợp các ý chính của tài liệu nghiên cứu và đề xuất hướng phát triển tiếp theo.', 'Summarize the key points of the research material and propose next directions.'),
            type: 'report'
        },
        work: {
            prompt: tx('Tối ưu quy trình công việc theo từng bước, người phụ trách và KPI.', 'Optimize the workflow by steps, owners, and KPIs.'),
            type: 'presentation'
        },
        exam: {
            prompt: tx('Tạo bộ flashcard ôn thi theo chủ đề và mức độ ưu tiên.', 'Create a review flashcard set by topic and priority.'),
            type: 'flashcard'
        },
        podcast: {
            prompt: tx('Tạo podcast duel gồm 2 AI tranh luận trái chiều dựa trên nguồn dữ liệu và chốt insight hành động.', 'Create a podcast duel where two AI hosts debate opposing views from the source data and conclude with actionable insights.'),
            type: 'podcast'
        },
        video: {
            prompt: tx('Tạo video AI trình bày theo dạng cinematic: mở đầu, ý chính, ví dụ và kết luận hành động.', 'Create an AI cinematic presentation video flow: opener, core points, examples, and action-oriented conclusion.'),
            type: 'video'
        }
    };
    return map[key] || null;
}

function onTemplateClick(templateKey) {
    const payload = templatePayload(templateKey);
    if (!payload) return;

    setWorkspaceMode('text');
    if (el.workspacePrompt) {
        el.workspacePrompt.value = payload.prompt;
    }
    setWorkspaceType(payload.type);
    showToast(t('status.templateLoaded'), 'success');
}

function buildBuilderResult() {
    const title = (state.builder.title || '').trim() || (isVi() ? 'Bản đồ từ Builder' : 'Builder map');
    const type = state.builder.type || 'mindmap';
    const color = state.builder.color || '#6366f1';
    const branches = state.builder.branches.map((branch) => ({
        text: branch.text,
        id: branch.id,
        builderBranchId: branch.id,
        children: []
    }));

    return {
        type,
        title,
        mindmapStyle: resolveMindmapStyle(state.workspaceMindmapStyle, { title, topics: state.builder.branches.map((branch) => branch.text) }, title),
        creativeLevel: normalizeCreativeLevel(state.workspaceCreativeLevel),
        builderColor: color,
        topics: state.builder.branches.map((branch) => branch.text),
        nodes: branches,
        summary: [
            isVi() ? `Màu Builder: ${color}` : `Builder color: ${color}`,
            isVi() ? 'Dữ liệu từ trình dựng' : 'Data from builder'
        ]
    };
}

function updateBuilderPrimaryAction() {
    if (!el.addBranchBtn) return;
    el.addBranchBtn.textContent = state.builder.selectedBranchId ? t('home.builder.saveBranch') : t('home.builder.add');
}

function selectBuilderBranch(branchId) {
    state.builder.selectedBranchId = branchId || null;
    const branch = state.builder.branches.find((item) => item.id === state.builder.selectedBranchId);

    if (el.branchInput) {
        el.branchInput.value = branch ? branch.text : '';
    }

    renderBranchList();
    updateBuilderPrimaryAction();
}

function refreshBuilderPreview(shouldPersist = false) {
    const project = getCurrentProject();
    const hasData = (state.builder.title || '').trim() || state.builder.branches.length > 0;

    if (!hasData) {
        if (el.builderPreview) {
            el.builderPreview.innerHTML = `<p class="preview-empty">${escapeHtml(isVi() ? 'Builder sẽ hiển thị mindmap hoặc layout trực quan ngay tại đây.' : 'Builder will show a mindmap or visual layout here.')}</p>`;
        }
        if (project) {
            project.builder.lastResult = null;
            if (shouldPersist) persistCurrentProject();
        }
        return;
    }

    const result = attachWorkspaceVisualMeta(buildBuilderResult(), state.builder.title);
    if (project) {
        project.builder.lastResult = result;
        if (shouldPersist) persistCurrentProject();
    }

    renderVisualResult(result, el.builderPreview, {
        source: 'builder',
        editable: true,
        allowFullscreen: true
    });
}

function renderBranchList() {
    if (!el.builderBranchList) return;

    el.builderBranchList.innerHTML = '';

    if (state.builder.branches.length === 0) {
        const li = document.createElement('li');
        li.className = 'branch-item';
        li.innerHTML = `<span class="branch-index">${escapeHtml(t('home.builder.noBranches'))}</span>`;
        el.builderBranchList.appendChild(li);
        return;
    }

    state.builder.branches.forEach((branch, index) => {
        const li = document.createElement('li');
        li.className = `branch-item ${branch.id === state.builder.selectedBranchId ? 'active' : ''}`;
        li.innerHTML = `
            <div>
                <div><strong>${escapeHtml(branch.text)}</strong></div>
                <div class="branch-index">${escapeHtml(t('home.builder.branch', { index: index + 1 }))} • ${escapeHtml(t('home.builder.clickToEdit'))}</div>
            </div>
            <span class="branch-index">${escapeHtml(t('home.builder.select'))}</span>
        `;

        li.addEventListener('click', () => {
            selectBuilderBranch(branch.id === state.builder.selectedBranchId ? null : branch.id);
        });

        el.builderBranchList.appendChild(li);
    });
}

function addOrUpdateBranch() {
    const text = (el.branchInput?.value || '').trim();
    if (!text) {
        setStatus(isVi() ? 'Hãy nhập nội dung nhánh trước.' : 'Enter branch content first.', 'error');
        return;
    }

    if (state.builder.selectedBranchId) {
        const branch = state.builder.branches.find((item) => item.id === state.builder.selectedBranchId);
        if (!branch) {
            setStatus(isVi() ? 'Không tìm thấy nhánh đang sửa.' : 'Cannot find the branch being edited.', 'error');
            return;
        }
        branch.text = text;
        showToast(isVi() ? 'Đã cập nhật nhánh.' : 'Branch updated.', 'success');
        selectBuilderBranch(null);
    } else {
        state.builder.branches.push({ id: uid('branch'), text });
        showToast(isVi() ? 'Đã thêm nhánh mới.' : 'New branch added.', 'success');
        if (el.branchInput) {
            el.branchInput.value = '';
        }
    }

    renderBranchList();
    updateBuilderPrimaryAction();
    refreshBuilderPreview(true);
}

function moveBranch(offset) {
    const branchId = state.builder.selectedBranchId;
    const index = state.builder.branches.findIndex((item) => item.id === branchId);
    if (index < 0) return;

    const nextIndex = index + offset;
    if (nextIndex < 0 || nextIndex >= state.builder.branches.length) return;

    const [branch] = state.builder.branches.splice(index, 1);
    state.builder.branches.splice(nextIndex, 0, branch);

    renderBranchList();
    refreshBuilderPreview(true);
}

function deleteBranch() {
    const branchId = state.builder.selectedBranchId;
    if (!branchId) {
        setStatus(t('status.deleteBranch'), 'error');
        return;
    }

    state.builder.branches = state.builder.branches.filter((item) => item.id !== branchId);
    selectBuilderBranch(null);
    renderBranchList();
    refreshBuilderPreview(true);
}

function buildFromBuilder() {
    const project = getCurrentProject();
    if (!project) {
        setStatus(t('status.selectProject'), 'error');
        return;
    }

    state.builder.title = (el.builderTitle?.value || '').trim() || (isVi() ? 'Bản đồ từ Builder' : 'Builder map');
    state.builder.type = el.builderType?.value || 'mindmap';
    state.builder.color = el.builderColor?.value || '#6366f1';

    const result = buildBuilderResult();
    project.builder.lastResult = result;
    project.builder.title = state.builder.title;
    project.builder.type = state.builder.type;
    project.builder.color = state.builder.color;
    project.builder.branches = [...state.builder.branches];

    project.workspace.lastResult = result;
    project.workspace.type = result.type;
    project.workspace.mode = 'text';
    project.workspace.mindmapStyle = normalizeMindmapStyle(state.workspaceMindmapStyle);
    project.workspace.creativeLevel = normalizeCreativeLevel(state.workspaceCreativeLevel);

    refreshBuilderPreview(false);
    renderPreview(result, el.studioPreview);
    renderVisualOutput(result);
    persistCurrentProject();
    setStatus(t('status.builderCreated'), 'success');
}

function renderBuilderPreview(result) {
    if (!result) {
        refreshBuilderPreview(false);
        return;
    }

    renderVisualResult(result, el.builderPreview, {
        source: 'builder',
        editable: true,
        allowFullscreen: true
    });
}

function formatSize(size) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
}

async function onNotebookFiles(files) {
    const fileList = Array.from(files || []);
    if (fileList.length === 0) return;

    for (const file of fileList) {
        const content = await readFile(file);
        state.notebook.sources.push({
            id: uid('source'),
            name: file.name,
            size: file.size,
            type: file.type,
            content
        });
        state.notebook.activeSourceId = state.notebook.sources[state.notebook.sources.length - 1].id;
    }

    renderNotebookSources();
    persistCurrentProject();
    appendChatMessage('system', `Bộ nhớ đã được cập nhật với ${fileList.length} tài liệu mới.`);
}

function renderNotebookSources() {
    if (!el.notebookSourceList) return;
    const existingShimmer = el.notebookSourceList.querySelector('.search-searching-shimmer');
    el.notebookSourceList.innerHTML = '';
    
    // Re-add shimmer if search is still active
    if (state.isLibrarySearching) {
        if (existingShimmer) {
            el.notebookSourceList.appendChild(existingShimmer);
        } else {
            injectSearchShimmer(state.librarySearchQuery || runtimeSessionStorage?.getItem('skemi_search_notebook_q') || '');
        }
    }
    
    const project = getCurrentProject();
    const sources = project?.notebook?.sources || [];
    
    const sourceCount = sources.length;
    const maxSources = 100;
    if (el.sourceCountLabel) el.sourceCountLabel.textContent = `${sourceCount} / ${maxSources} ${tx('Nguồn', 'Sources')}`;
    if (el.sourceProgressBar) el.sourceProgressBar.style.width = `${Math.min((sourceCount / maxSources) * 100, 100)}%`;

    el.noSourcesPlaceholder?.classList.toggle('hidden', sourceCount > 0);
    
    // Update Guide visibility dynamically if sources changed
    if (el.notebookGuide) {
        el.notebookGuide.classList.toggle('hidden', sourceCount === 0);
    }

    sources.forEach((source) => {
        const item = document.createElement('li');
        item.className = `source-item animate-fadeInFast ${source.id === state.notebook.activeSourceId ? 'active' : ''}`;
        
        // NotebookLM style icons with Favicon fallback
        let iconHtml = '<span class="icon">📄</span>';
        const fileName = (source.name || '').toLowerCase();
        let iconClass = 'source-type-txt';
        
        if (fileName.endswith?.('.pdf') || fileName.endsWith('.pdf')) { iconHtml = '<span class="icon">📕</span>'; iconClass = 'source-type-pdf'; }
        else if (fileName.endswith?.('.doc') || fileName.endsWith('.doc') || fileName.endsWith('.docx')) { iconHtml = '<span class="icon">📘</span>'; iconClass = 'source-type-doc'; }
        else if (source.type === 'web' || source.url) { 
            const url = source.url || '';
            let faviconUrl = '';
            
            if (url) {
                try {
                    const host = new URL(url).hostname;
                    faviconUrl = `https://www.google.com/s2/favicons?domain=${host}&sz=64`;
                    
                    if (host.includes('reddit.com')) iconHtml = '<img src="https://www.redditstatic.com/desktop2x/img/favicon/favicon-32x32.png" alt="reddit">';
                    else if (host.includes('wikipedia.org')) iconHtml = '<span class="icon">📖</span>';
                    else if (host.includes('youtube.com')) iconHtml = '<span class="icon">🎬</span>';
                    else iconHtml = `<img src="${faviconUrl}" onerror="this.src='';this.parentElement.innerHTML='🌐';" alt="web">`;
                } catch(e) {
                    iconHtml = '<span class="icon">🌐</span>';
                }
            } else {
                iconHtml = '<span class="icon">🌐</span>';
            }
            iconClass = 'source-type-web'; 
        }
        
        // Improved layout with distinct containers for stability
        item.innerHTML = `
            <div class="source-item-inner" style="display:flex; align-items:center; gap:10px; width:100%; overflow:hidden;">
                <div class="source-type-icon ${iconClass}" style="flex-shrink:0;">${iconHtml}</div>
                <div class="source-details" style="flex:1; min-width:0; overflow:hidden;">
                    <span class="source-name" style="display:block; font-size:0.85rem; font-weight:500; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(source.name)}">${escapeHtml(source.name)}</span>
                </div>
                <div class="source-actions" style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
                    <button class="btn-delete" title="${tx('Xóa nguồn', 'Delete source')}">🗑️</button>
                    <input type="checkbox" class="source-checkbox" checked data-source-id="${source.id}" onclick="event.stopPropagation()">
                </div>
            </div>
        `;

        item.addEventListener('click', (e) => {
            if (e.target.classList.contains('source-checkbox') || e.target.classList.contains('btn-delete')) return;
            showSourceDetail(source);
        });

        item.querySelector('.btn-delete')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const currentProject = getCurrentProject();
            if (currentProject?.notebook?.sources) {
                currentProject.notebook.sources = currentProject.notebook.sources.filter((s) => s.id !== source.id);
                if (state.notebook.activeSourceId === source.id) state.notebook.activeSourceId = null;
                renderNotebookSources();
                persistCurrentProject();
            }
        });

        el.notebookSourceList.appendChild(item);
    });
}

async function showSourceDetail(source) {
    if (!el.sourceDetailOverlay) return;
    
    el.sourceDetailTitle.textContent = source.name;
    el.sourceDetailFullText.innerHTML = `<p>${escapeHtml(source.content || '').replace(/\n/g, '<br>')}</p>`;
    el.sourceDetailSummary.innerHTML = '<i>AI đang tóm tắt nguồn này cho bạn...</i>';
    el.sourceDetailOverlay.classList.remove('hidden');

    if (source.summary) {
        el.sourceDetailSummary.innerHTML = String(source.summary).replace(/\*\*/g, '');
    } else {
        try {
            const prompt = `Bạn là trợ lý AI chuyên nghiệp. Hãy đọc nội dung sau và cung cấp một bản tóm tắt cực kỳ ngắn gọn, súc tích (khoảng 3-5 câu), làm nổi bật các ý chính CỦA RIÊNG NGUỒN NÀY (Không nói chung chung).
            TUYỆT ĐỐI KHÔNG sử dụng định dạng Markdown in đậm (dấu **). Chỉ sử dụng văn bản thuần tuý.
            
            Nội dung:
            ${source.content.substring(0, 5000)}`;

            const response = await fetch(`${API_BASE}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: prompt, age_group: 'middle' })
            });

            if (response.ok) {
                const data = await response.json();
                const summary = String(data.answer || 'Không thể tạo tóm tắt.').replace(/\*\*/g, '');
                source.summary = summary; // Cache it
                el.sourceDetailSummary.innerHTML = summary;
                persistCurrentProject();
            } else {
                el.sourceDetailSummary.innerHTML = 'Không thể kết nối với AI để tóm tắt.';
            }
        } catch (err) {
            el.sourceDetailSummary.innerHTML = 'Lỗi tóm tắt: ' + err.message;
        }
    }
}

function closeSourceDetail() {
    el.sourceDetailOverlay?.classList.add('hidden');
}


function pushNotebookMessage(role, content) {
    state.notebook.messages.push({ role, content, ts: Date.now() });
    renderNotebookMessages();
    persistCurrentProject();
}

function renderNotebookMessages() {
    if (!el.notebookMessages) return;
    el.notebookMessages.innerHTML = '';

    const messages = state.notebook.messages.length > 0
        ? state.notebook.messages
        : [{
            role: 'system',
            content: 'Chào mừng đến với sổ ghi chú. Bạn có thể hỏi bất kỳ điều gì.'
        }];

    messages.forEach((message) => {
        const div = document.createElement('div');
        div.className = `message ${message.role}`;
        div.innerHTML = `<div class="message-bubble">${escapeHtml(message.content)}</div>`;
        el.notebookMessages.appendChild(div);
    });

    el.notebookMessages.scrollTop = el.notebookMessages.scrollHeight;
}

function getActiveSource() {
    return state.notebook.sources.find((source) => source.id === state.notebook.activeSourceId) || null;
}

async function sendNotebookMessage() {
    const question = (el.notebookInput?.value || '').trim();
    if (!question) return;

    // Show user message
    appendChatMessage('user', question);
    el.notebookInput.value = '';
    el.notebookInput.style.height = 'auto';

    const aiMsgEl = document.createElement('div');
    aiMsgEl.className = 'message ai animate-fadeInFast';
    aiMsgEl.innerHTML = '<div class="message-bubble">...</div>';
    el.notebookMessages.appendChild(aiMsgEl);
    const messageBubble = aiMsgEl.querySelector('.message-bubble');
    el.notebookMessages.scrollTop = el.notebookMessages.scrollHeight;

    const sendBtn = el.notebookSendBtn;
    const sendIcon = sendBtn?.querySelector('.send-icon');
    const spinner = sendBtn?.querySelector('.spinner');

    if (sendBtn) sendBtn.classList.add('active');
    if (sendIcon) sendIcon.classList.add('hidden');
    if (spinner) spinner.classList.remove('hidden');

    try {
        const project = getCurrentProject();
        // Filter based on checkboxes
        const selectedIds = Array.from(document.querySelectorAll('.source-checkbox:checked')).map(cb => cb.dataset.sourceId);
        const selectedSources = (project.notebook.sources || []).filter(s => selectedIds.includes(s.id));
        
        if (selectedSources.length === 0 && (project.notebook.sources || []).length > 0) {
            showToast(tx('Vui lòng chọn ít nhất một nguồn.', 'Please select at least one source.'), 'warning');
            return;
        }

        const sourcesContext = selectedSources.map(s => `[Source: ${s.name}]\n${s.content}`).join('\n\n');
        
        const systemPrompt = `Bạn là trợ lý AI chuyên nghiệp của Skemi Studio. 
Hãy phân tích ${selectedSources.length} nguồn dữ liệu được cung cấp dưới đây để trả lời câu hỏi của người dùng.
1. Ưu tiên tuyệt đối việc sử dụng thông tin từ nguồn dữ liệu.
2. Nếu thông tin có trong nguồn, hãy tổng hợp và trả lời chi tiết. Tránh trả lời chung chung.
3. Nếu thông tin KHÔNG có trong nguồn, hãy trả lời dựa trên kiến thức của bạn và ghi chú lịch sự.
4. TUYỆT ĐỐI KHÔNG sử dụng định dạng Markdown in đậm (dấu **). Chỉ sử dụng văn bản thuần hoặc xuống dòng.
5. Model: skemi-pro-v3.`;

        const response = await fetch(`${API_BASE}/notebook_chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                projectId: state.currentProjectId,
                sources: selectedSources, // Use filtered sources
                systemPrompt: systemPrompt,
                message: question,
                model: 'gpt-oss:120b-cloud'
            })
        });

        if (!response.ok) throw new Error('Cổng hội thoại không phản hồi.');
        const data = await response.json();
        const reply = data.answer || data.response;
        
        if (reply) {
            const cleanedReply = String(reply || '').replace(/\*\*/g, '');
            messageBubble.textContent = cleanedReply;
            state.notebook.messages.push({ role: 'user', content: question });
            state.notebook.messages.push({ role: 'ai', content: cleanedReply });
            persistCurrentProject();
        } else {
            messageBubble.textContent = 'Tôi không tìm thấy câu trả lời phù hợp.';
        }
        
    } catch (err) {
        messageBubble.textContent = 'Có lỗi xảy ra: ' + err.message;
    } finally {
        if (sendBtn) sendBtn.classList.remove('active');
        if (sendIcon) sendIcon.classList.remove('hidden');
        if (spinner) spinner.classList.add('hidden');
    }
}

function injectSearchShimmer(query) {
    if (!el.notebookSourceList) return;
    const shimmer = document.createElement('div');
    shimmer.className = 'search-searching-shimmer';
    shimmer.innerHTML = `
        <div style="text-align:center; padding:15px; background: var(--bg-secondary); border-radius: 12px; margin-bottom: 12px; border: 1px dashed var(--brand-primary); overflow: hidden;">
            <span style="font-size:0.8rem; color:var(--brand-primary); font-weight:700; display:block; white-space:nowrap;">✨ Đang tìm kiếm...</span>
            <span style="font-size:0.7rem; color:var(--text-muted); font-style:italic; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:180px; margin: 4px auto;">"${query}"</span>
            <div class="staging-loading" style="margin-top:10px;">
                <div class="shimmer-card" style="height:6px; opacity:0.6; border-radius:4px;"></div>
            </div>
        </div>
    `;
    if (el.noSourcesPlaceholder) el.noSourcesPlaceholder.classList.add('hidden');
    el.notebookSourceList.prepend(shimmer);
}

function persistNotebookSearchJob(job, meta = {}) {
    if (!job?.id) {
        runtimeSessionStorage?.removeItem(NOTEBOOK_SEARCH_JOB_KEY);
        return;
    }
    runtimeSessionStorage?.setItem(NOTEBOOK_SEARCH_JOB_KEY, JSON.stringify({
        jobId: job.id,
        requestKey: job.request_key || meta.requestKey || '',
        query: job.query || meta.query || '',
        deep: Boolean(meta.deep),
        status: job.status || meta.status || 'queued',
        savedAt: Date.now()
    }));
}

function readNotebookSearchJob() {
    try {
        const saved = JSON.parse(runtimeSessionStorage?.getItem(NOTEBOOK_SEARCH_JOB_KEY) || 'null');
        return saved && typeof saved === 'object' ? saved : null;
    } catch {
        return null;
    }
}

async function createNotebookSearchJob(query, deep) {
    const response = await fetch(`${API_BASE}/search/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query,
            deep_research: deep,
            lang: state.language || 'vi',
            search_context: 'studio-library'
        })
    });
    if (!response.ok) throw new Error('Lỗi tìm kiếm');
    const data = await response.json();
    if (!data?.success || !data?.job) throw new Error(data?.error || 'Lỗi tìm kiếm');
    return data.job;
}

async function fetchNotebookSearchJob(jobId) {
    const response = await fetch(`${API_BASE}/search/jobs/${encodeURIComponent(jobId)}`);
    if (!response.ok) throw new Error('Lỗi tải trạng thái tìm kiếm');
    const data = await response.json();
    if (!data?.success || !data?.job) throw new Error(data?.error || 'Không tìm thấy job');
    return data.job;
}

let notebookSearchPollTimer = null;
function clearNotebookSearchPolling() {
    if (notebookSearchPollTimer) {
        clearInterval(notebookSearchPollTimer);
        notebookSearchPollTimer = null;
    }
}

function finishNotebookSearch(job, analysis) {
    clearNotebookSearchPolling();
    state.isLibrarySearching = false;
    statusSearching(false);
    persistNotebookSearchJob(null);
    runtimeSessionStorage?.removeItem('skemi_search_notebook_active');
    document.querySelectorAll('.search-searching-shimmer').forEach((node) => node.remove());
    if (analysis?.sources?.length) {
        if (job?.request_key) {
            window.SkemiJobs?.cacheResult(job.request_key, analysis);
        }
        showSearchStaging(analysis.sources);
        setStatus(tx('Đã tìm thấy nguồn mới.', 'New sources are ready.'), 'success');
    } else {
        renderNotebookSources();
        setStatus(tx('Không tìm thấy kết quả phù hợp.', 'No matching result found.'), 'warning');
    }
}

function resumeNotebookSearchJob(jobId, options = {}) {
    if (!jobId) return;
    clearNotebookSearchPolling();
    notebookSearchPollTimer = setInterval(async () => {
        try {
            const job = await fetchNotebookSearchJob(jobId);
            persistNotebookSearchJob(job, {
                query: job.query || state.librarySearchQuery || '',
                deep: Boolean(options.deep)
            });
            window.SkemiJobs?.update(job.id, {
                status: job.status,
                requestKey: job.request_key || '',
                analysis: job.analysis || null,
                query: job.query || state.librarySearchQuery || '',
                context: 'studio-library'
            });
            const status = String(job.status || '').toLowerCase();
            if (status === 'completed') {
                finishNotebookSearch(job, job.analysis || null);
            } else if (status === 'failed') {
                clearNotebookSearchPolling();
                state.isLibrarySearching = false;
                statusSearching(false);
                persistNotebookSearchJob(null);
                renderNotebookSources();
                setStatus(job.error || tx('Lỗi khi tìm kiếm.', 'Search failed.'), 'error');
            }
        } catch (err) {
            console.warn('Notebook search polling failed', err);
        }
    }, 2200);
}

async function performLibrarySearchWithJobs(deep = false, manualQuery = null) {
    const query = manualQuery || (el.libSearchInput?.value || '').trim();
    if (!query) return;

    if (!manualQuery && state.isLibrarySearching) {
        setStatus(tx('Đang có tìm kiếm đang chạy...', 'A search is already in progress...'), 'warning');
        return;
    }

    setStatus(deep ? 'Đang nghiên cứu sâu...' : 'Đang tìm kiếm nguồn...', 'info');
    statusSearching(true);
    state.isLibrarySearching = true;
    state.librarySearchQuery = query;
    runtimeSessionStorage?.setItem('skemi_search_notebook_active', '1');
    runtimeSessionStorage?.setItem('skemi_search_notebook_q', query);
    runtimeSessionStorage?.setItem('skemi_search_notebook_deep', deep ? '1' : '0');
    injectSearchShimmer(query);

    try {
        const job = await createNotebookSearchJob(query, deep);
        persistNotebookSearchJob(job, { query, deep });
        window.SkemiJobs?.register(job, {
            context: 'studio-library',
            page: 'Home.html',
            kind: 'library_search',
            query,
            requestKey: job.request_key || '',
            status: job.status,
            analysis: job.analysis || null
        });

        if (String(job.status || '').toLowerCase() === 'completed') {
            finishNotebookSearch(job, job.analysis || null);
        } else {
            resumeNotebookSearchJob(job.id, { deep });
        }
    } catch (err) {
        document.querySelectorAll('.search-searching-shimmer').forEach((node) => node.remove());
        console.error(err);
        setStatus('Lỗi khi tìm kiếm: ' + err.message, 'error');
        renderNotebookSources();
        state.isLibrarySearching = false;
        statusSearching(false);
        persistNotebookSearchJob(null);
        runtimeSessionStorage?.removeItem('skemi_search_notebook_active');
    }
}

async function performLibrarySearch(deep = false, manualQuery = null) {
    return performLibrarySearchWithJobs(deep, manualQuery);
}

function statusSearching(active) {
    const searchBtn = el.btnLibSearch;
    const searchIcon = searchBtn?.querySelector('.icon');
    const spinner = searchBtn?.querySelector('.spinner');

    if (searchBtn) searchBtn.classList.toggle('active', active);
    if (searchIcon) searchIcon.classList.toggle('hidden', active);
    if (spinner) spinner.classList.toggle('hidden', !active);

    // Global sidebar indicator - finding the tab with data-panel="notebook"
    el.tabs?.forEach(tab => {
        if (tab.dataset.panel === 'notebook' || tab.id === 'notebook-link') {
            tab.classList.toggle('status-working', active);
        }
    });

    // Update global state for other pages
    if (active) runtimeSessionStorage?.setItem('skemi_global_pulse_notebook', '1');
    else runtimeSessionStorage?.removeItem('skemi_global_pulse_notebook');
}

let currentStagingSources = [];
function showSearchStaging(sources) {
    // Re-acquire if lost
    if (!el.searchStagingOverlay) el.searchStagingOverlay = document.getElementById('searchStagingOverlay');
    if (!el.stagingList) el.stagingList = document.getElementById('stagingList');
    
    if (!el.searchStagingOverlay) {
        console.error('Search staging overlay not found in DOM');
        setStatus('Giao diện hiển thị nguồn đang lỗi, hãy F5 trang.', 'error');
        return;
    }
    
    currentStagingSources = sources.map(s => ({ ...s, selected: true }));
    el.searchStagingOverlay.classList.remove('hidden');
    renderStagingList();
}

function renderStagingList() {
    if (!el.stagingList) return;
    el.stagingList.innerHTML = '';
    
    let selectedCount = 0;
    currentStagingSources.forEach((src, idx) => {
        if (src.selected) selectedCount++;
        const item = document.createElement('div');
        item.className = `staging-item ${src.selected ? 'selected' : ''}`;
        item.innerHTML = `
            <div class="staging-info">
                <span class="staging-title">${escapeHtml(src.title)}</span>
                <p class="staging-snippet">${escapeHtml(src.snippet || 'Không có bản xem trước')}</p>
            </div>
            <input type="checkbox" class="staging-checkbox" ${src.selected ? 'checked' : ''} onclick="event.stopPropagation()">
        `;
        
        item.addEventListener('click', () => {
            currentStagingSources[idx].selected = !currentStagingSources[idx].selected;
            renderStagingList();
        });
        
        el.stagingList.appendChild(item);
    });
    
    if (!el.stagingCount) el.stagingCount = document.getElementById('stagingCount');
    if (!el.btnConfirmStaging) el.btnConfirmStaging = document.getElementById('btnConfirmStaging');
    
    if (el.stagingCount) el.stagingCount.textContent = selectedCount;
    if (el.btnConfirmStaging) {
        el.btnConfirmStaging.disabled = (selectedCount === 0);
        el.btnConfirmStaging.classList.toggle('disabled', selectedCount === 0);
    }
}

async function confirmStaging() {
    const selected = currentStagingSources.filter(s => s.selected);
    if (selected.length === 0) return;
    
    selected.forEach(res => {
        const newSource = {
            id: uid('source'),
            name: res.title || 'Kết quả tìm kiếm',
            content: res.content || res.snippet || '',
            url: res.url,
            type: 'web',
            summary: null 
        };
        state.notebook.sources.push(newSource);
        autoSummarizeSource(newSource);
    });
    
    el.searchStagingOverlay.classList.add('hidden');
    el.libSearchInput.value = '';
    persistCurrentProject();
    renderNotebookSources();
    setStatus(`Đã thêm ${selected.length} nguồn mới.`, 'success');
}

async function autoSummarizeSource(source) {
    if (!source.content) return;
    try {
        const prompt = `Tóm tắt chủ đề chính (3-5 câu) bằng Tiếng Việt của nguồn tài liệu này. Hãy cụ thể và chi tiết, đừng nói chung chung.
        TUYỆT ĐỐI KHÔNG dùng dấu sao ** hay định dạng Markdown in đậm. Chỉ trả về văn bản thường.
        Nội dung: ${source.content.substring(0, 3000)}`;

        const response = await fetch(`${API_BASE}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: prompt, age_group: 'middle' })
        });

        if (response.ok) {
            const data = await response.json();
            source.summary = String(data.answer || '').replace(/\*\*/g, '');
            persistCurrentProject();
        }
    } catch (err) {
        console.warn('Auto-summary failed', err);
    }
}

function appendChatMessage(role, content) {
    if (!el.notebookMessages) return;
    const msg = document.createElement('div');
    msg.className = `message ${role}`;
    // Strip markdown bolding as requested
    const cleanedContent = String(content || '').replace(/\*\*/g, '');
    msg.innerHTML = `<div class="message-bubble">${escapeHtml(cleanedContent)}</div>`;
    el.notebookMessages.appendChild(msg);
    el.notebookMessages.scrollTop = el.notebookMessages.scrollHeight;
    return msg;
}

function createFromNotebook(type) {
    const merged = state.notebook.messages
        .map((message) => `${message.role === 'user' ? 'User' : 'Assistant'}: ${message.content}`)
        .join('. ')
        .trim();

    if (!merged) {
        setStatus(t('status.noConversation'), 'error');
        return;
    }

    const project = getCurrentProject();
    if (!project) return;

    (async () => {
        let result;
        try {
            result = await generateModelOutput(type, merged);
        } catch {
            result = createGenericOutput(type, merged);
        }
        result = attachWorkspaceVisualMeta(result, merged);

        project.workspace.lastResult = result;
        project.workspace.type = type;
        project.workspace.mindmapStyle = normalizeMindmapStyle(state.workspaceMindmapStyle);
        project.workspace.creativeLevel = normalizeCreativeLevel(state.workspaceCreativeLevel);
        renderPreview(result, el.studioPreview);
        renderVisualOutput(result);
        persistCurrentProject();
        switchTab('workspace');
        const typeLabelMap = {
            mindmap: t('common.mindmap'),
            report: t('common.report'),
            presentation: t('common.presentation'),
            infographic: t('common.infographic'),
            chart: t('common.chart'),
            flashcard: t('common.flashcard'),
            dashboard: tx('Dashboard', 'Dashboard'),
            podcast: tx('Podcast Duel', 'Podcast Duel'),
            video: tx('Video AI', 'AI Video'),
            quiztest: tx('AI Test', 'AI Test'),
            comic: tx('Truyện tranh', 'Comic'),
            book: tx('Sách', 'Book')
        };
        setStatus(t('status.notebookCreated', { type: typeLabelMap[type] || type }), 'success');
    })();
}



function normalizeWorkspaceType(type) {
    const allowed = new Set(['mindmap', 'presentation', 'chart', 'infographic', 'report', 'flashcard', 'dashboard', 'podcast', 'video', 'quiztest', 'comic', 'book']);
    return allowed.has(type) ? type : 'mindmap';
}

function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getVisibleElement(...candidates) {
    return candidates.find((candidate) => {
        if (!candidate) return false;
        const rect = candidate.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }) || null;
}

async function ensureElementInViewport(element) {
    if (!element) return false;
    element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
    await wait(320);
    const rect = element.getBoundingClientRect();
    return rect.top >= 0
        && rect.left >= 0
        && rect.bottom <= window.innerHeight
        && rect.right <= window.innerWidth;
}

function pulseElement(element) {
    if (!element) return;
    const previousTransition = element.style.transition;
    const previousBoxShadow = element.style.boxShadow;
    const previousTransform = element.style.transform;
    const previousBorder = element.style.borderColor;

    element.style.transition = 'all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
    element.style.boxShadow = '0 0 0 4px rgba(34, 197, 94, 0.6), 0 0 35px rgba(16, 185, 129, 0.5)';
    element.style.transform = 'scale(1.03)';
    element.style.borderColor = '#10b981';

    window.setTimeout(() => {
        element.style.transition = previousTransition;
        element.style.boxShadow = previousBoxShadow;
        element.style.transform = previousTransform;
        element.style.borderColor = previousBorder;
    }, 1200); // Giữ hiệu ứng lâu hơn
}

async function simulateAIInput(element, value, options = {}) {
    if (!element) return false;
    const text = String(value || '');
    // Làm chậm tốc độ gõ phím để người dùng thấy rõ
    const interval = Math.max(60, Number(options.intervalMs || 75)); 
    await ensureElementInViewport(element);
    pulseElement(element);
    element.focus();
    await wait(600); // Đợi một chút sau khi focus rồi mới gõ

    if (!options.preserveExisting) {
        element.value = '';
        element.dispatchEvent(new Event('input', { bubbles: true }));
        await wait(300);
    }
    for (const char of text) {
        element.value += char;
        element.dispatchEvent(new Event('input', { bubbles: true }));
        // Thêm âm thanh phím gõ giả lập nếu cần (hiện tại dùng hiệu ứng chờ)
        await wait(interval); 
    }
    element.dispatchEvent(new Event('change', { bubbles: true }));
    await wait(400); // Nghỉ sau khi gõ xong
    return true;
}

async function simulateAISelect(selectElement, value) {
    if (!selectElement) return false;
    await ensureElementInViewport(selectElement);
    pulseElement(selectElement);
    selectElement.focus();
    await wait(120);
    selectElement.value = value;
    selectElement.dispatchEvent(new Event('change', { bubbles: true }));
    await wait(180);
    return true;
}

async function simulateAIClick(element) {
    if (!element) return false;
    await ensureElementInViewport(element);
    pulseElement(element);
    element.focus?.();
    await wait(160);
    element.click();
    await wait(260);
    return true;
}

async function simulateWorkspaceTypeSelection(type) {
    const targetType = normalizeWorkspaceType(type);
    const button = Array.from(el.workspaceTypeButtons || []).find((item) => item.dataset.type === targetType);
    if (!button) {
        setWorkspaceType(targetType);
        return;
    }
    await simulateAIClick(button);
}

async function simulateStudioTabSwitch(tab) {
    const target = String(tab || 'workspace').trim();
    const button = Array.from(el.tabs || []).find((item) => item.dataset.panel === target);
    if (!button) {
        switchTab(target);
        return;
    }
    await simulateAIClick(button);
}

function deriveProjectNameFromPrompt(prompt) {
    const quoted = String(prompt || '').match(/["'“”]([^"'“”]{2,80})["'“”]/);
    if (quoted?.[1]) {
        return quoted[1].trim();
    }
    const cleaned = String(prompt || '')
        .replace(/[.,;:!?]+/g, ' ')
        .replace(/\b(tao|create|lam|generate|giup|help|cho toi|cho mình|cho minh|de|để|with|using|make|xay dung|xây dựng|mindmap|report|presentation|infographic|flashcard|podcast|video|quiz|quiztest|dashboard|chart|workspace|studio)\b/gi, ' ')
        .replace(/\s{2,}/g, ' ')
        .trim();
    if (!cleaned) {
        return tx('Dự án mới', 'New Project');
    }
    return cleaned.split(' ').slice(0, 6).join(' ').trim();
}

async function ensureProjectForAI(command) {
    const explicitName = String(command?.projectName || command?.name || '').trim();
    const fallbackName = deriveProjectNameFromPrompt(command?.prompt || '');
    const projectName = explicitName || fallbackName;
    if (!projectName) {
        return null;
    }

    const existing = state.projects.find((project) => project.name.trim().toLowerCase() === projectName.toLowerCase());
    if (existing) {
        if (el.projectSelect && el.projectSelect.value !== existing.id) {
            await simulateAISelect(el.projectSelect, existing.id);
        } else {
            openProject(existing.id);
        }
        return existing;
    }

    const nameInput = getVisibleElement(el.projectHubName, el.projectName);
    const createBtn = getVisibleElement(el.projectHubCreateBtn, el.createProjectBtn);
    if (nameInput && createBtn) {
        await simulateAIInput(nameInput, projectName, { intervalMs: 42 });
        await simulateAIClick(createBtn);
    }

    const created = state.projects.find((project) => project.name.trim().toLowerCase() === projectName.toLowerCase()) || createProjectByName(projectName);
    return created || null;
}

async function runAIStudioSequence(command) {
    const type = String(command?.type || '').toLowerCase();

    if (type === 'studio.create_project') {
        const project = await ensureProjectForAI(command);
        if (!project) {
            setStatus(t('status.enterProjectName'), 'error');
            return false;
        }

        const workspaceType = normalizeWorkspaceType(String(command.workspaceType || project.workspace.type || 'mindmap').trim());
        if (String(command.prompt || '').trim()) {
            await simulateStudioTabSwitch('workspace');
            await simulateWorkspaceTypeSelection(workspaceType);
            if (el.workspacePrompt) {
                await simulateAIInput(el.workspacePrompt, String(command.prompt || '').trim(), { intervalMs: 26 });
            }
            project.workspace.prompt = String(command.prompt || '').trim();
            project.workspace.type = workspaceType;
            state.workspaceType = workspaceType;
            persistCurrentProject();
            if (command.autoGenerate && el.workspaceGenerateBtn) {
                await simulateAIClick(el.workspaceGenerateBtn);
            }
        }
        setStatus(t('status.created', { name: project.name }), 'success');
        return true;
    }

    if (type === 'studio.seed_prompt') {
        const project = getCurrentProject() || await ensureProjectForAI(command);
        if (!project) {
            setStatus(t('status.enterProjectName'), 'error');
            return false;
        }

        const prompt = String(command.prompt || '').trim();
        if (!prompt) return false;

        const workspaceType = normalizeWorkspaceType(String(command.workspaceType || project.workspace.type || 'mindmap').trim());
        await simulateStudioTabSwitch('workspace');
        await simulateWorkspaceTypeSelection(workspaceType);
        setWorkspaceMode('text');
        if (el.workspacePrompt) {
            await simulateAIInput(el.workspacePrompt, prompt, { intervalMs: 24 });
        }
        project.workspace.prompt = prompt;
        project.workspace.type = workspaceType;
        state.workspaceType = workspaceType;
        persistCurrentProject();
        if (command.autoGenerate && el.workspaceGenerateBtn) {
            await simulateAIClick(el.workspaceGenerateBtn);
        }
        setStatus(tx('Đã nạp yêu cầu từ Skemi AI vào Studio.', 'Loaded the AI request into Studio.'), 'success');
        return true;
    }

    if (type === 'studio.switch_tab') {
        await simulateStudioTabSwitch(command.tab);
        setStatus(t('status.switched'), 'success');
        return true;
    }

    if (type === 'studio.notebook_create') {
        if (!getCurrentProject()) {
            return false;
        }
        await simulateStudioTabSwitch('notebook');
        const createType = normalizeWorkspaceType(String(command.createType || 'mindmap').trim());
        const button = Array.from(el.notebookCreateButtons || []).find((item) => item.dataset.createType === createType);
        if (button) {
            await simulateAIClick(button);
        } else {
            createFromNotebook(createType);
        }
        return true;
    }

    return false;
}

function pulseAIControlState(duration = 2000) {
    document.body.classList.add('skemi-ai-controlling');
    document.body.setAttribute('data-skemi-ai-state', tx('Skemi AI đang điều khiển trang web...', 'Skemi AI is controlling this page...'));
    window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
        detail: { active: true, source: 'home', until: Date.now() + duration }
    }));
    if (window.__skemiAIPulseTimer) {
        window.clearTimeout(window.__skemiAIPulseTimer);
    }
    window.__skemiAIPulseTimer = window.setTimeout(() => {
        document.body.classList.remove('skemi-ai-controlling');
        document.body.removeAttribute('data-skemi-ai-state');
        window.__skemiAIPulseTimer = null;
        window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
            detail: { active: false, source: 'home' }
        }));
    }, duration);
}

function applyAIStudioCommand(command) {
    if (!command) return false;

    // Show notification to user that AI is taking control
    if (command.type && command.type.startsWith('studio.')) {
        setStatus(tx('Skemi AI đang thực hiện lệnh trong Studio...', 'Skemi AI is performing a command in Studio...'), 'info');
    }
    
    // Nếu là một mảng lệnh, thực hiện tuần tự và cực kỳ chậm
    if (Array.isArray(command)) {
        const executeBatch = async (list) => {
            (function(){})('AI Batch Execution Started: ', list.length, ' steps');
            for (const cmd of list) {
                // Đảm bảo lệnh trước đã "thấm" vào UI
                const success = await applyAIStudioCommand(cmd);
                if (success) {
                    // Nghỉ 2 giây giữa mỗi hành động lớn để người dùng kịp quan sát
                    await new Promise(r => setTimeout(r, 2200)); 
                }
            }
            (function(){})('AI Batch Execution Finished.');
        };
        executeBatch(command);
        return true;
    }

    if (typeof command !== 'object') return false;

    if (command.controlPulse) {
        const duration = Math.max(3000, Number(command.controlDurationMs || 6000));
        pulseAIControlState(duration);
    }

    const type = String(command.type || '').toLowerCase();
    if (!type.startsWith('studio.')) return false;

    if (type === 'studio.create_project') {
        const name = String(command.name || '').trim();
        if (!name) return false;
        setStatus(tx('Skemi AI đang tạo project trong Studio...', 'Skemi AI is creating the project in Studio...'));
        void runAIStudioSequence(command);
        return true;
    }

    if (type === 'studio.seed_prompt') {
        const prompt = String(command.prompt || '').trim();
        if (!prompt) return false;
        setStatus(tx('Skemi AI đang nhập yêu cầu vào Studio...', 'Skemi AI is entering your request into Studio...'));
        void runAIStudioSequence(command);
        return true;
    }

    if (type === 'studio.switch_tab') {
        const tab = String(command.tab || '').trim();
        if (!getCurrentProject()) {
            setStatus(t('status.selectProject'), 'error');
            return true;
        }

        if (!['workspace', 'builder', 'notebook'].includes(tab)) {
            return false;
        }

        void runAIStudioSequence(command);
        return true;
    }

    if (type === 'studio.notebook_create') {
        const createType = normalizeWorkspaceType(String(command.createType || 'mindmap').trim());
        if (!getCurrentProject()) {
            setStatus(t('status.selectProject'), 'error');
            return true;
        }
        switchTab('notebook');
        createFromNotebook(createType);
        return true;
    }

    return false;
}

function launchArenaFromStudio(mode) {
    const normalizedMode = ['vortex', 'strife', 'core'].includes(String(mode || '').toLowerCase())
        ? String(mode).toLowerCase()
        : 'vortex';

    const command = {
        id: uid('cmd'),
        type: 'quiz.create_arena',
        target: 'quiz',
        mode: normalizedMode,
        createdAt: Date.now()
    };

    localStorage.setItem(AI_COMMAND_KEY(), JSON.stringify(command));
    window.dispatchEvent(new CustomEvent('skemi:ai-command', { detail: command }));
    setStatus(tx('Đang mở Arena trong Quiz...', 'Opening Arena in Quiz...'), 'success');

    setTimeout(() => {
        window.location.href = 'Quiz.html';
    }, 260);
}

function consumeAIStudioCommand() {
    let payload = null;
    try {
        payload = JSON.parse(localStorage.getItem(AI_COMMAND_KEY()) || 'null');
    } catch (error) {
        console.warn('Invalid AI command payload:', error);
        localStorage.removeItem(AI_COMMAND_KEY());
        return;
    }

    if (!payload) return;
    if (payload.target && payload.target !== 'home') return;

    const isExpired = Number(payload.createdAt || 0) > 0 && (Date.now() - Number(payload.createdAt)) > (10 * 60 * 1000);
    if (isExpired) {
        localStorage.removeItem(AI_COMMAND_KEY());
        return;
    }

    if (applyAIStudioCommand(payload)) {
        localStorage.removeItem(AI_COMMAND_KEY());
    }
}

function bindProjectEvents() {
    el.projectHubCreateBtn?.addEventListener('click', () => {
        el.createProjectArea?.classList.remove('hidden');
        el.projectHubName?.focus();
    });

    el.cancelCreateBtn?.addEventListener('click', () => {
        el.createProjectArea?.classList.add('hidden');
        if (el.projectHubName) el.projectHubName.value = '';
    });

    el.confirmCreateBtn?.addEventListener('click', () => {
        const name = el.projectHubName?.value.trim();
        if (name) {
            createProjectByName(name);
            el.createProjectArea?.classList.add('hidden');
            el.projectHubName.value = '';
            setStatus(t('status.created', { name }), 'success');
        } else {
            showToast(t('status.enterProjectName'), 'warning');
        }
    });

    el.projectHubName?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') el.confirmCreateBtn?.click();
        if (e.key === 'Escape') el.cancelCreateBtn?.click();
    });

    el.backToProjectsBtn?.addEventListener('click', goProjectHub);

    el.projectSelect?.addEventListener('change', () => {
        openProject(el.projectSelect.value);
        setStatus(t('status.switched'), 'success');
    });

    el.saveProjectBtn?.addEventListener('click', () => {
        persistCurrentProject();
        setStatus(t('status.saved'), 'success');
    });
}

function bindTabEvents() {
    el.tabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            if (!getCurrentProject()) {
                setStatus(t('status.selectProject'), 'error');
                return;
            }
            switchTab(tab.dataset.panel);
        });
    });
}

function bindWorkspaceEvents() {
    // Notebook Guide
    el.guideCards?.forEach((card) => {
        card.addEventListener('click', () => {
            onGuideAction(card.dataset.guideAction);
        });
    });

    // Action Cards logic
    el.actionCards.forEach((card) => {
        card.addEventListener('click', () => {
            const action = card.dataset.action;
            // Map actions to existing build/synthesis flows
            onWorkspaceGenerate(action); 
        });
    });

    // Modal Events
    el.openSourceModalBtn?.addEventListener('click', () => {
        el.sourceModal?.classList.add('active');
    });

    el.closeSourceModalBtn?.addEventListener('click', () => {
        el.sourceModal?.classList.remove('active');
    });

    el.btnCloseSourceDetail?.addEventListener('click', () => {
        closeSourceDetail();
    });

    window.addEventListener('click', (e) => {
        if (e.target === el.sourceModal) el.sourceModal.classList.remove('active');
        if (e.target === el.sourceDetailOverlay) closeSourceDetail();
        if (e.target === el.searchStagingOverlay) el.searchStagingOverlay.classList.add('hidden');
    });

    el.btnCloseStaging?.addEventListener('click', () => el.searchStagingOverlay?.classList.add('hidden'));
    el.btnCancelStaging?.addEventListener('click', () => el.searchStagingOverlay?.classList.add('hidden'));
    el.btnConfirmStaging?.addEventListener('click', () => confirmStaging());
    
    // Ensure they are definitely bound even if el was slow
    document.getElementById('btnCloseStaging')?.addEventListener('click', () => {
        document.getElementById('searchStagingOverlay')?.classList.add('hidden');
    });
    document.getElementById('btnCancelStaging')?.addEventListener('click', () => {
        document.getElementById('searchStagingOverlay')?.classList.add('hidden');
    });

    el.notebookInput?.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    el.selectAllSources?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        document.querySelectorAll('.source-checkbox').forEach(cb => {
            cb.checked = checked;
        });
    });

    el.btnLibSearch?.addEventListener('click', () => {
        const isDeep = el.libDeepSearchToggle?.classList.contains('active') || false;
        performLibrarySearch(isDeep);
    });
    
    el.btnLibDeepSearch?.addEventListener('click', (e) => {
        e.stopPropagation();
        const isActive = el.btnLibDeepSearch.classList.toggle('active');
        // Visual feedback based on user description (Stitch button etc)
        const label = el.btnLibDeepSearch.querySelector('span') || el.btnLibDeepSearch;
        if (isActive) {
            el.btnLibDeepSearch.style.background = 'var(--brand-primary)';
            el.btnLibDeepSearch.style.color = 'white';
            showToast('Nghiên cứu sâu: ĐÃ BẬT', 'info');
        } else {
            el.btnLibDeepSearch.style.background = '';
            el.btnLibDeepSearch.style.color = '';
            showToast('Nghiên cứu sâu: ĐÃ TẮT', 'info');
        }
        // DO NOT trigger search here - just toggle state
    });

    el.libSearchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const isDeep = el.btnLibDeepSearch?.classList.contains('active') || false;
            performLibrarySearch(isDeep);
        }
    });

    el.clearStudioPreviewBtn?.addEventListener('click', () => {
        const project = getCurrentProject();
        if (project) {
            project.workspace.lastResult = null;
            saveProjects();
        }
        if (el.studioPreview) {
            el.studioPreview.innerHTML = '';
            el.studioPreview.classList.add('hidden');
        }
        showToast(tx('Đã xóa nội dung xem trước.', 'Preview content cleared.'));
    });
}

function onGuideAction(action) {
    let promptText = '';
    const project = getCurrentProject();
    if (!project || (project.notebook?.sources?.length || 0) === 0) {
        showToast(tx('Hãy thêm nguồn tài liệu trước.', 'Please add sources first.'), 'warning');
        return;
    }

    switch(action) {
        case 'faq':
            promptText = tx('Dựa trên tài liệu, hãy liệt kê 5 câu hỏi thường gặp nhất và trả lời chúng.', 'Based on the documents, list the 5 most frequently asked questions and answer them.');
            break;
        case 'toc':
            promptText = tx('Hãy tạo một mục lục chi tiết tóm tắt cấu trúc của các tài liệu này.', 'Create a detailed table of contents summarizing the structure of these documents.');
            break;
        case 'study':
            promptText = tx('Lập một lộ trình học tập hiệu quả dựa trên nội dung các nguồn tài liệu này.', 'Create an effective study guide based on the content of these sources.');
            break;
    }

    if (promptText && el.notebookInput) {
        el.notebookInput.value = promptText;
        sendNotebookMessage();
        
        if (window.gsap && el.notebookGuide) {
            gsap.to(el.notebookGuide, { opacity: 0, y: -20, duration: 0.4, ease: "power2.in", onComplete: () => {
                el.notebookGuide.classList.add('hidden');
                el.notebookGuide.style.opacity = '1';
                el.notebookGuide.style.transform = '';
            }});
        } else if (el.notebookGuide) {
            el.notebookGuide.classList.add('hidden');
        }
    }
}

function bindBuilderEvents() {
    el.builderTitle?.addEventListener('input', () => {
        state.builder.title = el.builderTitle.value;
        refreshBuilderPreview(true);
    });

    el.builderType?.addEventListener('change', () => {
        state.builder.type = el.builderType.value;
        refreshBuilderPreview(true);
    });

    el.builderColor?.addEventListener('change', () => {
        state.builder.color = el.builderColor.value;
        refreshBuilderPreview(true);
    });

    el.branchInput?.addEventListener('input', updateBuilderPrimaryAction);

    el.addBranchBtn?.addEventListener('click', addOrUpdateBranch);
    el.moveUpBtn?.addEventListener('click', () => moveBranch(-1));
    el.moveDownBtn?.addEventListener('click', () => moveBranch(1));
    el.deleteBranchBtn?.addEventListener('click', deleteBranch);
    el.builderRenderBtn?.addEventListener('click', buildFromBuilder);
}

function bindNotebookEvents() {
    el.notebookDropZone?.addEventListener('click', () => el.notebookFileInput?.click());

    el.notebookFileInput?.addEventListener('change', (event) => {
        onNotebookFiles(event.target.files);
    });

    el.notebookDropZone?.addEventListener('dragover', (event) => {
        event.preventDefault();
        el.notebookDropZone.classList.add('dragover');
    });

    el.notebookDropZone?.addEventListener('dragleave', () => {
        el.notebookDropZone.classList.remove('dragover');
    });

    el.notebookDropZone?.addEventListener('drop', (event) => {
        event.preventDefault();
        el.notebookDropZone.classList.remove('dragover');
        onNotebookFiles(event.dataTransfer.files);
    });

    el.notebookSendBtn?.addEventListener('click', sendNotebookMessage);

    el.notebookInput?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendNotebookMessage();
        }
    });

    el.notebookCreateButtons?.forEach((btn) => {
        btn.addEventListener('click', () => createFromNotebook(btn.dataset.createType));
    });

    // Library Search Events
    const deepToggleBtn = document.getElementById('btnLibDeepSearchToggle');
    if (deepToggleBtn) {
        deepToggleBtn.addEventListener('click', () => {
            deepToggleBtn.classList.toggle('active');
        });
    }

    el.btnLibSearch?.addEventListener('click', () => {
        const isDeep = deepToggleBtn ? deepToggleBtn.classList.contains('active') : false;
        performLibrarySearch(isDeep);
    });
    
    el.libSearchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const isDeep = deepToggleBtn ? deepToggleBtn.classList.contains('active') : false;
            performLibrarySearch(isDeep);
        }
    });

    // Staging Modal Events
    const btnConfirm = document.getElementById('btnConfirmStaging');
    const btnCancel = document.getElementById('btnCancelStaging');
    if (btnConfirm) btnConfirm.addEventListener('click', confirmStaging);
    if (btnCancel) {
        btnCancel.addEventListener('click', () => {
            el.searchStagingOverlay?.classList.add('hidden');
        });
    }
}

function bindViewerEvents() {
    el.fullscreenBackdrop?.addEventListener('click', closeFullscreenViewer);
    el.viewerCloseBtn?.addEventListener('click', closeFullscreenViewer);
    el.viewerBrowserFullscreenBtn?.addEventListener('click', toggleViewerBrowserFullscreen);

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && el.fullscreenViewer?.classList.contains('active')) {
            closeFullscreenViewer();
        }
    });
}

async function init() {
    await loadProjects();
    renderProjectList();
    renderProjectSelect();

    if (state.currentProjectId) {
        setStudioStage(true);
        applyProjectToUI();
    } else {
        setStudioStage(false);
        refreshBuilderPreview(false);
    }

    bindProjectEvents();
    
    // Updated Tab Events for Studio 2.0
    el.tabs?.forEach((tab) => {
        tab.addEventListener('click', () => {
            const panelId = tab.dataset.panel;
            switchTab(panelId);
        });
    });

    bindWorkspaceEvents();
    bindBuilderEvents();
    bindNotebookEvents();
    bindViewerEvents();
    if (el.mindmapStyleSelect) el.mindmapStyleSelect.value = state.workspaceMindmapStyle;
    if (el.creativeLevelSelect) el.creativeLevelSelect.value = state.workspaceCreativeLevel;
    updateWorkspaceStyleVisibility();
    resetGenerateProgressUI();
    window.addEventListener('languageChanged', () => {
        renderProjectList();
        renderProjectSelect();
        if (state.currentProjectId) {
            setStudioStage(true);
            applyProjectToUI();
        } else {
            setStudioStage(false);
            refreshBuilderPreview(false);
        }
        updateBuilderPrimaryAction();
        renderBranchList();
        renderNotebookSources();
        renderNotebookMessages();
        setGenerateLoading(state.isGenerating);
        if (!state.isGenerating) {
            resetGenerateProgressUI();
        }
        // Project UI is now restored — safe to resume an in-flight Studio generation.
        // Check the server for an account-wide job FIRST (covers "closed the
        // whole browser and came back" — the local job pointer alone can't
        // survive that), then resume from whatever pointer is now available.
        recoverStudioJobsFromServer().finally(resumeStudioJob);
    });
    window.addEventListener('skemi:ai-command', (event) => {
        const command = event?.detail;
        if (!command || (command.target && command.target !== 'home')) {
            return;
        }
        if (applyAIStudioCommand(command)) {
            localStorage.removeItem(AI_COMMAND_KEY());
        }
    });

    switchTab('workspace');
    setStatus(t('status.ready'));

    // PERSISTENCE RECOVERY: resume an existing notebook-search job instead of starting over
    const savedNotebookJob = readNotebookSearchJob();
    if (savedNotebookJob?.jobId) {
        const cachedResult = savedNotebookJob.requestKey
            ? window.SkemiJobs?.getCachedResult(savedNotebookJob.requestKey)
            : null;
        state.librarySearchQuery = savedNotebookJob.query || '';
        state.isLibrarySearching = true;
        statusSearching(true);
        injectSearchShimmer(savedNotebookJob.query || '');
        if (cachedResult?.analysis) {
            finishNotebookSearch(
                {
                    id: savedNotebookJob.jobId,
                    request_key: savedNotebookJob.requestKey || ''
                },
                cachedResult.analysis
            );
        } else {
            resumeNotebookSearchJob(savedNotebookJob.jobId, { deep: Boolean(savedNotebookJob.deep) });
        }
    } else if (runtimeSessionStorage?.getItem('skemi_global_pulse_notebook') === '1') {
        // Just show the pulse if it's active elsewhere but not this specific task
        statusSearching(true);
    }

    consumeExternalSeed();
    consumeAIStudioCommand();
}

document.addEventListener('DOMContentLoaded', init);


