

const AI_COMMAND_KEY = 'skemi_ai_pending_command_v1';

class FeaturesController {
    constructor() {
        this.roomStorageKey = 'skemi_private_quiz_rooms_v1';
        this.userStorageKey = 'skemi_user_data';
        this.editingRoomId = null;
        this.editingQuestionIndex = null;
        this.draftQuestions = [];
        this.userData = this.loadUserData();
        this.init();
    }

    get isQuizPage() {
        return Boolean(document.getElementById('quiz-section'));
    }

    get lang() {
        return (window.languageManager?.base || 'vi') === 'vi' ? 'vi' : 'en';
    }

    text() {
        return this.lang === 'vi'
            ? {
                quota: ['Lượt hỏi', 'Lượt upload', 'Phòng Quiz', 'Gói'],
                noRooms: 'Bạn đã hết lượt tạo phòng quiz. Hãy nâng cấp gói để mở rộng hạn mức.',
                roomCreated: 'Đã lưu phòng quiz private.',
                roomUpdated: 'Đã cập nhật phòng quiz private.',
                roomDeleted: 'Đã xóa phòng quiz private.',
                missingRoomTitle: 'Hãy nhập tên phòng quiz.',
                missingQuestion: 'Hãy nhập nội dung câu hỏi.',
                missingOptions: 'Mỗi câu hỏi cần đủ 4 đáp án.',
                missingQuestions: 'Phòng quiz private cần ít nhất 1 câu hỏi.',
                questionAdded: 'Đã thêm câu hỏi vào phòng.',
                questionUpdated: 'Đã cập nhật câu hỏi.',
                builderEyebrow: 'Trình tạo phòng private',
                builderTitle: 'Tạo phòng quiz private',
                builderDesc: 'Người dùng tự nhập từng câu hỏi, từng đáp án và lưu thành phòng riêng.',
                roomTitle: 'Tên phòng',
                roomTitlePlaceholder: 'Ví dụ: Ôn tập Hóa học lớp 8',
                audience: 'Nhóm tuổi phù hợp',
                summary: 'Mô tả ngắn',
                summaryPlaceholder: 'Mục tiêu của phòng quiz này là gì?',
                questionEyebrow: 'Trình tạo câu hỏi',
                questionTitle: 'Nhập từng câu hỏi thủ công',
                questionDesc: 'Mỗi câu hỏi gồm nội dung, 4 đáp án, đáp án đúng và giải thích ngắn.',
                questionText: 'Câu hỏi',
                questionPlaceholder: 'Nhập nội dung câu hỏi',
                answer: 'Đáp án đúng',
                explanation: 'Giải thích ngắn',
                explanationPlaceholder: 'Giải thích vì sao đáp án này đúng',
                addQuestion: 'Thêm câu hỏi',
                updateQuestion: 'Cập nhật câu hỏi',
                resetQuestion: 'Xóa khung câu hỏi',
                draftTitle: 'Danh sách câu hỏi trong phòng',
                draftCount: '{count} câu hỏi',
                resetRoom: 'Làm mới phòng',
                saveRoom: 'Lưu phòng private',
                updateRoom: 'Cập nhật phòng',
                savedRoomsEyebrow: 'Phòng đã lưu',
                savedRoomsTitle: 'Phòng private đã tạo',
                savedRoomsDesc: 'Tất cả câu hỏi bạn tự nhập sẽ được lưu ở đây để mở lại, sửa tiếp hoặc mời người khác.',
                publicTitle: 'Quiz công khai theo tháng',
                publicDesc: 'Mỗi tháng có 3 chủ đề public theo 3 nhóm tuổi khác nhau. Người chơi có thể nhận thêm prompt và lượt upload nếu đạt thứ hạng cao.',
                emptyDraft: 'Chưa có câu hỏi nào. Hãy nhập câu hỏi đầu tiên.',
                emptyRooms: 'Bạn chưa tạo phòng private nào.',
                privateBadge: 'Riêng tư',
                publicBadge: 'Công khai',
                participants: '{count} người tham gia',
                questions: '{count} câu hỏi',
                edit: 'Sửa',
                delete: 'Xóa',
                view: 'Xem câu hỏi',
                loadBuilder: 'Mở trình tạo phòng',
                reward: 'Thưởng top 1-3',
                join: 'Vào quiz',
                questionNumber: 'Câu {count}',
                correctAnswer: 'Đáp án',
                ages: { young: 'Học sinh', middle: 'Người lao động', senior: 'Người lớn tuổi' },
                monthly: [
                    ['Học sinh', 'Ôn tập môn học, kỹ năng tư duy và bài tập thực hành.', 168],
                    ['Người lao động', 'Công việc, tài chính, công nghệ ứng dụng và năng suất.', 112],
                    ['Người lớn tuổi', 'Sức khỏe, trí nhớ, đời sống số và kết nối gia đình.', 74]
                ]
            }
            : {
                quota: ['Prompts', 'Uploads', 'Quiz rooms', 'Plan'],
                noRooms: 'You have no quiz room quota left. Upgrade your plan to expand the limit.',
                roomCreated: 'Private quiz room saved.',
                roomUpdated: 'Private quiz room updated.',
                roomDeleted: 'Private quiz room deleted.',
                missingRoomTitle: 'Enter a room title.',
                missingQuestion: 'Enter the question text.',
                missingOptions: 'Each question needs all 4 answer options.',
                missingQuestions: 'A private quiz room needs at least 1 question.',
                questionAdded: 'Question added to the room.',
                questionUpdated: 'Question updated.',
                builderEyebrow: 'Private quiz builder',
                builderTitle: 'Create a private quiz room',
                builderDesc: 'Users enter each question and answer manually, then save the room privately.',
                roomTitle: 'Room title',
                roomTitlePlaceholder: 'Example: Grade 8 chemistry review',
                audience: 'Target age group',
                summary: 'Short summary',
                summaryPlaceholder: 'What is this quiz room for?',
                questionEyebrow: 'Question builder',
                questionTitle: 'Enter questions manually',
                questionDesc: 'Each question includes content, 4 answers, the correct answer, and a short explanation.',
                questionText: 'Question',
                questionPlaceholder: 'Enter the question text',
                answer: 'Correct answer',
                explanation: 'Short explanation',
                explanationPlaceholder: 'Explain why this answer is correct',
                addQuestion: 'Add question',
                updateQuestion: 'Update question',
                resetQuestion: 'Clear question form',
                draftTitle: 'Questions in this room',
                draftCount: '{count} questions',
                resetRoom: 'Reset room',
                saveRoom: 'Save private room',
                updateRoom: 'Update room',
                savedRoomsEyebrow: 'Saved rooms',
                savedRoomsTitle: 'Saved private rooms',
                savedRoomsDesc: 'All questions you enter are stored here so you can reopen, edit, or invite others later.',
                publicTitle: 'Monthly public quizzes',
                publicDesc: 'Every month there are 3 public themes mapped to 3 age groups. High-ranked players can earn extra prompts and uploads.',
                emptyDraft: 'No questions yet. Enter the first one.',
                emptyRooms: 'You have not created any private room yet.',
                privateBadge: 'Private',
                publicBadge: 'Public',
                participants: '{count} participants',
                questions: '{count} questions',
                edit: 'Edit',
                delete: 'Delete',
                view: 'View questions',
                loadBuilder: 'Open builder',
                reward: 'Top 1-3 rewards',
                join: 'Join quiz',
                questionNumber: 'Question {count}',
                correctAnswer: 'Correct answer',
                ages: { young: 'Student', middle: 'Working adult', senior: 'Senior' },
                monthly: [
                    ['Students', 'School review, thinking skills, and practical exercises.', 168],
                    ['Working adults', 'Work, finance, applied technology, and productivity.', 112],
                    ['Seniors', 'Health, memory, digital life, and family connection.', 74]
                ]
            };
    }

    init() {
        this.bindSidebarEvents();
        this.updateQuotaDisplay();
        this.initPerformanceToggle();
        if (!this.isQuizPage) return;
        this.bindQuizEvents();
        this.applyQuizCopy();
        this.renderDraftQuestions();
        this.renderPrivateRooms();
        this.renderPublicRooms();
        window.addEventListener('languageChanged', () => {
            this.applyQuizCopy();
            this.updateQuotaDisplay();
            this.renderDraftQuestions();
            this.renderPrivateRooms();
            this.renderPublicRooms();
        });
        window.addEventListener('skemi:ai-command', (event) => {
            const command = event?.detail;
            if (!command || (command.target && command.target !== 'quiz')) return;
            if (this.applyAIQuizCommand(command)) {
                localStorage.removeItem(AI_COMMAND_KEY);
            }
        });
        this.consumeAIQuizCommand();

        onAuthStateChanged(auth, (user) => {
            if (!user) {
                const requireLogin = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    window.location.href = 'Login.html';
                };
                
                const btnIds = ['createQuizBtn', 'addQuizQuestionBtn', 'resetQuestionEditorBtn', 'resetPrivateQuizBtn', 'savePrivateQuizBtn'];
                btnIds.forEach(id => {
                    const btn = document.getElementById(id);
                    if (btn) btn.addEventListener('click', requireLogin, true);
                });
                
                const containers = ['draftQuestions', 'privateQuizGrid', 'publicQuizGrid'];
                containers.forEach(id => {
                    const node = document.getElementById(id);
                    if (node) node.addEventListener('click', requireLogin, true);
                });

                const inputs = ['privateRoomTitle', 'privateRoomAudience', 'privateRoomSummary', 'quizQuestionText', 'quizOptionA', 'quizOptionB', 'quizOptionC', 'quizOptionD', 'quizCorrectAnswer', 'quizQuestionExplain'];
                inputs.forEach(id => {
                    const node = document.getElementById(id);
                    if (node) {
                        if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') node.readOnly = true;
                        if (node.tagName === 'SELECT') node.disabled = true;
                        node.addEventListener('click', requireLogin, true);
                    }
                });
            }
        });
    }

    initPerformanceToggle() {
        const toggle = document.getElementById('performance3DToggle');
        if (!toggle) return;
        
        const current = localStorage.getItem('skemi-performance-3d') !== 'false';
        toggle.checked = current;
        
        toggle.addEventListener('change', () => {
            localStorage.setItem('skemi-performance-3d', toggle.checked);
            // Dispatch storage event manually for same-tab listeners
            window.dispatchEvent(new StorageEvent('storage', {
                key: 'skemi-performance-3d',
                newValue: String(toggle.checked)
            }));
        });
    }

    loadUserData() {
        try {
            const saved = JSON.parse(localStorage.getItem(this.userStorageKey) || 'null');
            if (saved) return saved;
        } catch {}
        return {
            age_group: 'middle',
            subscription: 'free',
            prompts_remaining: 10,
            uploads_remaining: 3,
            quiz_rooms_remaining: 3,
            last_prompt_reset: Date.now()
        };
    }

    saveUserData() {
        localStorage.setItem(this.userStorageKey, JSON.stringify(this.userData));
    }

    rooms() {
        try {
            return JSON.parse(localStorage.getItem(this.roomStorageKey) || '[]');
        } catch {
            return [];
        }
    }

    saveRooms(rooms) {
        localStorage.setItem(this.roomStorageKey, JSON.stringify(rooms));
    }

    normalizeAudience(value) {
        const audience = String(value || '').trim().toLowerCase();
        if (audience === 'young' || audience === 'middle' || audience === 'senior') {
            return audience;
        }
        return 'young';
    }

    normalizeQuestions(rawQuestions) {
        if (!Array.isArray(rawQuestions)) return [];
        return rawQuestions
            .map((item) => {
                const question = String(item?.question || '').trim();
                const options = Array.isArray(item?.options)
                    ? item.options.map((option) => String(option || '').trim()).slice(0, 4)
                    : [];
                const answer = Number(item?.answer ?? item?.correctAnswer ?? 0);
                const explanation = String(item?.explanation || '').trim();
                if (!question || options.length !== 4 || options.some((option) => !option)) return null;
                return {
                    question,
                    options,
                    answer: Math.max(0, Math.min(3, Number.isFinite(answer) ? answer : 0)),
                    explanation
                };
            })
            .filter(Boolean)
            .slice(0, 12);
    }

    arenaBlueprint(mode) {
        const normalizedMode = ['vortex', 'strife', 'core'].includes(String(mode || '').toLowerCase())
            ? String(mode).toLowerCase()
            : 'vortex';
        const isVi = this.lang === 'vi';

        if (normalizedMode === 'strife') {
            return {
                mode: normalizedMode,
                title: isVi ? 'Arena STRIFE · Tranh luận 1v1' : 'STRIFE Arena · 1v1 debate',
                summary: isVi
                    ? 'Tranh luận theo 3 hiệp, chấm điểm theo logic, bằng chứng và phản biện.'
                    : 'Three-round debate scored by logic, evidence, and rebuttal.',
                audience: 'middle',
                questions: [
                    {
                        question: isVi ? 'Luận điểm mở đầu nào mạnh nhất để bảo vệ ý kiến của bạn?' : 'Which opening argument is strongest to defend your position?',
                        options: isVi ? ['Nêu số liệu kiểm chứng', 'Nói cảm tính', 'Lặp lại đề bài', 'Đổi chủ đề'] : ['Present verifiable data', 'Use pure emotion', 'Repeat the prompt', 'Change the topic'],
                        answer: 0,
                        explanation: isVi ? 'Mở đầu dựa trên dữ liệu giúp tăng độ tin cậy ngay từ hiệp 1.' : 'A data-backed opening increases credibility in round one.'
                    },
                    {
                        question: isVi ? 'Khi đối thủ phản biện mạnh, bước xử lý tối ưu là gì?' : 'When the opponent delivers a strong rebuttal, what is the best response?',
                        options: isVi ? ['Thừa nhận điểm đúng rồi phản công có cấu trúc', 'Né câu hỏi', 'Công kích cá nhân', 'Lặp lại ý cũ'] : ['Acknowledge valid points and counter structurally', 'Avoid the question', 'Attack the person', 'Repeat old claims'],
                        answer: 0,
                        explanation: isVi ? 'Phản biện có cấu trúc giữ nhịp tranh luận chuyên nghiệp.' : 'Structured rebuttal keeps the debate professional and coherent.'
                    },
                    {
                        question: isVi ? 'Tiêu chí nào giúp bạn chốt hiệp cuối hiệu quả?' : 'Which criterion helps you close the final round effectively?',
                        options: isVi ? ['Tóm tắt luận điểm + đề xuất hành động', 'Nói dài hơn đối thủ', 'Đưa thông tin mới ngoài đề', 'Nêu khẩu hiệu'] : ['Summarize arguments + actionable close', 'Speak longer than the opponent', 'Introduce unrelated info', 'Use slogans'],
                        answer: 0,
                        explanation: isVi ? 'Kết thúc rõ ràng giúp trọng tài chấm điểm nhất quán.' : 'A clear close improves judging consistency.'
                    }
                ]
            };
        }

        if (normalizedMode === 'core') {
            return {
                mode: normalizedMode,
                title: isVi ? 'Arena CORE · Sửa Mindmap' : 'CORE Arena · Mindmap repair',
                summary: isVi
                    ? 'Sắp xếp lại nhánh tư duy dưới áp lực thời gian để khôi phục mạch logic.'
                    : 'Rebuild scattered branches under time pressure to restore logical flow.',
                audience: 'young',
                questions: [
                    {
                        question: isVi ? 'Bước đầu tiên khi mindmap bị xáo trộn là gì?' : 'What is the first step when a mindmap is scrambled?',
                        options: isVi ? ['Xác định node trung tâm', 'Chỉnh màu trước', 'Xóa node ngẫu nhiên', 'Thêm icon'] : ['Identify the central node', 'Change colors first', 'Delete random nodes', 'Add icons'],
                        answer: 0,
                        explanation: isVi ? 'Node trung tâm giúp khôi phục lại cấu trúc tổng thể nhanh nhất.' : 'The central node restores overall structure fastest.'
                    },
                    {
                        question: isVi ? 'Cách nhóm nhánh nào hiệu quả nhất?' : 'Which branch grouping strategy is most effective?',
                        options: isVi ? ['Theo mục tiêu và luồng nguyên nhân-kết quả', 'Theo độ dài chữ', 'Theo màu sắc', 'Theo thứ tự tạo'] : ['By objective and cause-effect flow', 'By text length', 'By colors', 'By creation order'],
                        answer: 0,
                        explanation: isVi ? 'Nhóm theo logic giúp tránh bỏ sót nhánh quan trọng.' : 'Logic-first grouping prevents missing critical branches.'
                    },
                    {
                        question: isVi ? 'Khi gần hết thời gian, nên ưu tiên gì?' : 'Near time-out, what should be prioritized?',
                        options: isVi ? ['Hoàn thiện xương sống + điểm neo', 'Trang trí giao diện', 'Viết mô tả dài', 'Tạo nhánh mới'] : ['Complete the backbone + anchor points', 'Decorate UI', 'Write long descriptions', 'Create new branches'],
                        answer: 0,
                        explanation: isVi ? 'Xương sống tốt đảm bảo khả năng mở rộng sau khi hết giờ.' : 'A strong backbone keeps the map extendable after timeout.'
                    }
                ]
            };
        }

        return {
            mode: 'vortex',
            title: isVi ? 'Arena VORTEX · Quyết định nhanh' : 'VORTEX Arena · Rapid decisions',
            summary: isVi
                ? 'Giải tình huống khó, chọn hướng xử lý và đánh giá hiệu ứng dây chuyền.'
                : 'Handle tough scenarios, choose responses, and evaluate ripple effects.',
            audience: 'middle',
            questions: [
                {
                    question: isVi ? 'Khi dữ liệu mâu thuẫn, quyết định tốt nhất là gì?' : 'When data conflicts, what is the best decision approach?',
                    options: isVi ? ['Ưu tiên nguồn tin cậy và kiểm chứng chéo', 'Tin nguồn mới nhất ngay', 'Bỏ qua dữ liệu cũ', 'Ra quyết định theo cảm giác'] : ['Prioritize trusted sources and cross-check', 'Trust the latest source immediately', 'Ignore historical data', 'Decide by intuition only'],
                    answer: 0,
                    explanation: isVi ? 'Kiểm chứng chéo giảm rủi ro quyết định sai.' : 'Cross-validation lowers decision risk.'
                },
                {
                    question: isVi ? 'Yếu tố nào cần xem trước khi hành động?' : 'Which factor should be reviewed before acting?',
                    options: isVi ? ['Ảnh hưởng ngắn hạn và dài hạn', 'Mức độ phức tạp giao diện', 'Ý kiến ngẫu nhiên', 'Số lượng tài liệu'] : ['Short-term and long-term impact', 'UI complexity', 'Random opinions', 'Number of documents'],
                    answer: 0,
                    explanation: isVi ? 'Đánh giá 2 tầng tác động giúp chọn phương án bền vững.' : 'Two-layer impact review supports sustainable choices.'
                },
                {
                    question: isVi ? 'Sau khi chọn phương án, cần làm gì tiếp?' : 'After choosing an option, what should come next?',
                    options: isVi ? ['Đặt chỉ số theo dõi và ngưỡng điều chỉnh', 'Đợi phản hồi tự nhiên', 'Thay đổi toàn bộ kế hoạch', 'Bỏ qua khâu đo lường'] : ['Set monitoring metrics and adjustment thresholds', 'Wait passively', 'Replace the entire plan', 'Skip measurement'],
                    answer: 0,
                    explanation: isVi ? 'Theo dõi chủ động giúp điều chỉnh sớm khi rủi ro tăng.' : 'Active monitoring enables early adjustment when risk rises.'
                }
            ]
        };
    }

    saveIncomingRoom(payload, successMessage) {
        const rooms = this.rooms();
        rooms.unshift(payload);
        this.saveRooms(rooms);

        if (this.userData.quiz_rooms_remaining > 0) {
            this.userData.quiz_rooms_remaining -= 1;
            this.saveUserData();
        }

        this.switchTab('private');
        this.updateQuotaDisplay();
        this.renderPrivateRooms();
        this.showToast(successMessage || this.text().roomCreated, 'success');
    }

    pulseAIControlState(duration = 2000) {
        document.body.classList.add('skemi-ai-controlling');
        document.body.setAttribute('data-skemi-ai-state', this.lang === 'vi'
            ? 'Skemi AI đang điều khiển trang web...'
            : 'Skemi AI is controlling this page...');
        window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
            detail: { active: true, source: 'quiz', until: Date.now() + duration }
        }));
        if (window.__skemiAIPulseTimer) {
            window.clearTimeout(window.__skemiAIPulseTimer);
        }
        window.__skemiAIPulseTimer = window.setTimeout(() => {
            document.body.classList.remove('skemi-ai-controlling');
            document.body.removeAttribute('data-skemi-ai-state');
            window.__skemiAIPulseTimer = null;
            window.dispatchEvent(new CustomEvent('skemi:ai-control-state', {
                detail: { active: false, source: 'quiz' }
            }));
        }, duration);
    }

    applyAIQuizCommand(command) {
        if (!command || typeof command !== 'object') return false;
        if (command.controlPulse) {
            const duration = Math.max(1600, Number(command.controlDurationMs || 5200));
            this.pulseAIControlState(duration);
        }
        const type = String(command.type || '').toLowerCase();
        if (!type.startsWith('quiz.')) return false;

        if (type === 'quiz.create_room') {
            const title = String(command.title || '').trim();
            const summary = String(command.summary || '').trim();
            const audience = this.normalizeAudience(command.audience);
            const questions = this.normalizeQuestions(command.questions);

            if (!title || questions.length === 0) {
                return false;
            }

            const payload = {
                id: `room_${Date.now()}`,
                title,
                summary,
                audience,
                questions,
                createdAt: Date.now(),
                updatedAt: Date.now(),
                participants: Math.floor(Math.random() * 5) + 1
            };
            this.saveIncomingRoom(payload, this.text().roomCreated);
            return true;
        }

        if (type === 'quiz.create_arena') {
            const blueprint = this.arenaBlueprint(command.mode);
            const payload = {
                id: `room_${blueprint.mode}_${Date.now()}`,
                title: blueprint.title,
                summary: blueprint.summary,
                audience: blueprint.audience,
                questions: blueprint.questions,
                createdAt: Date.now(),
                updatedAt: Date.now(),
                participants: Math.floor(Math.random() * 8) + 3
            };
            const modeLabel = String(blueprint.mode || 'vortex').toUpperCase();
            const successMessage = this.lang === 'vi'
                ? `Đã khởi tạo phòng Arena ${modeLabel}.`
                : `Arena room ${modeLabel} has been created.`;
            this.saveIncomingRoom(payload, successMessage);
            return true;
        }

        if (type === 'quiz.open') {
            const tab = String(command.tab || '').toLowerCase() === 'public' ? 'public' : 'private';
            this.switchTab(tab);
            return true;
        }

        return false;
    }

    consumeAIQuizCommand() {
        let payload = null;
        try {
            payload = JSON.parse(localStorage.getItem(AI_COMMAND_KEY) || 'null');
        } catch {
            localStorage.removeItem(AI_COMMAND_KEY);
            return;
        }

        if (!payload) return;
        if (payload.target && payload.target !== 'quiz') return;

        const isExpired = Number(payload.createdAt || 0) > 0 && (Date.now() - Number(payload.createdAt)) > (10 * 60 * 1000);
        if (isExpired) {
            localStorage.removeItem(AI_COMMAND_KEY);
            return;
        }

        if (this.applyAIQuizCommand(payload)) {
            localStorage.removeItem(AI_COMMAND_KEY);
        }
    }

    showToast(message, type = 'info') {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
            return;
        }
        (function(){})(`[${type}] ${message}`);
    }

    format(template, params = {}) {
        return String(template).replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? ''));
    }

    escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    bindSidebarEvents() {
        // The setup/builder area (#quiz-section) is hidden by default so the Quiz
        // landing stays clean; these buttons reveal it (with a slide-in) on demand.
        const revealSetup = (tab) => {
            const sec = document.getElementById('quiz-section');
            if (sec) {
                sec.classList.remove('hidden');
                sec.classList.remove('quiz-reveal');
                void sec.offsetWidth;            // restart the animation
                sec.classList.add('quiz-reveal');
            }
            this.switchTab(tab);
            setTimeout(() => {
                if (tab === 'private') {
                    document.getElementById('privateRoomTitle')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    document.getElementById('privateRoomTitle')?.focus();
                } else {
                    document.getElementById('quiz-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }, 90);
        };

        document.getElementById('createQuizBtn')?.addEventListener('click', () => revealSetup('private'));
        document.getElementById('browsePublicBtn')?.addEventListener('click', () => revealSetup('public'));
        document.getElementById('collapseQuizBtn')?.addEventListener('click', () => {
            const sec = document.getElementById('quiz-section');
            if (sec) { sec.classList.add('hidden'); sec.classList.remove('quiz-reveal'); }
            document.getElementById('quiz-section')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
            document.querySelector('.quiz-main-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    bindQuizEvents() {
        document.querySelectorAll('.quiz-tab').forEach((tab) => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
        });

        document.getElementById('addQuizQuestionBtn')?.addEventListener('click', () => this.upsertDraftQuestion());
        document.getElementById('resetQuestionEditorBtn')?.addEventListener('click', () => this.resetQuestionEditor());
        document.getElementById('resetPrivateQuizBtn')?.addEventListener('click', () => this.resetRoomBuilder());
        document.getElementById('savePrivateQuizBtn')?.addEventListener('click', () => this.savePrivateRoom());

        document.getElementById('draftQuestions')?.addEventListener('click', (event) => {
            const action = event.target.closest('[data-question-action]');
            if (!action) return;
            const index = Number(action.dataset.questionIndex);
            if (action.dataset.questionAction === 'edit') this.loadQuestionIntoEditor(index);
            if (action.dataset.questionAction === 'delete') this.deleteDraftQuestion(index);
            if (action.dataset.questionAction === 'up') this.moveDraftQuestion(index, -1);
            if (action.dataset.questionAction === 'down') this.moveDraftQuestion(index, 1);
        });

        document.getElementById('privateQuizGrid')?.addEventListener('click', (event) => {
            const action = event.target.closest('[data-room-action]');
            if (!action) return;
            const roomId = action.dataset.roomId;
            if (action.dataset.roomAction === 'edit') this.loadRoomIntoBuilder(roomId);
            if (action.dataset.roomAction === 'delete') this.deleteRoom(roomId);
        });

        document.querySelectorAll('[data-arena-launch]').forEach((button) => {
            button.addEventListener('click', () => {
                this.applyAIQuizCommand({
                    type: 'quiz.create_arena',
                    target: 'quiz',
                    mode: button.dataset.arenaLaunch
                });
            });
        });
    }

    switchTab(name) {
        document.querySelectorAll('.quiz-tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.tab === name));
        document.querySelectorAll('.quiz-content').forEach((content) => content.classList.toggle('active', content.id === `${name}-quiz`));
    }

    updateQuotaDisplay() {
        const t = this.text();
        document.querySelectorAll('.user-quota').forEach((node) => {
            node.innerHTML = `
                <div class="quota-item"><span class="quota-label">${this.escapeHtml(t.quota[0])}</span><span class="quota-value">${this.userData.prompts_remaining}</span></div>
                <div class="quota-item"><span class="quota-label">${this.escapeHtml(t.quota[1])}</span><span class="quota-value">${this.userData.uploads_remaining}</span></div>
                <div class="quota-item"><span class="quota-label">${this.escapeHtml(t.quota[2])}</span><span class="quota-value">${this.userData.quiz_rooms_remaining}</span></div>
                <div class="quota-item"><span class="quota-label">${this.escapeHtml(t.quota[3])}</span><span class="quota-value subscription-${this.userData.subscription}">${this.userData.subscription.toUpperCase()}</span></div>
            `;
        });
    }

    applyQuizCopy() {
        const t = this.text();
        const setText = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
        const setPlaceholder = (id, value) => { const node = document.getElementById(id); if (node) node.placeholder = value; };

        setText('privateBuilderEyebrow', t.builderEyebrow);
        setText('privateBuilderTitle', t.builderTitle);
        setText('privateBuilderDesc', t.builderDesc);
        setText('privateRoomTitleLabel', t.roomTitle);
        setPlaceholder('privateRoomTitle', t.roomTitlePlaceholder);
        setText('privateRoomAudienceLabel', t.audience);
        setText('privateRoomSummaryLabel', t.summary);
        setPlaceholder('privateRoomSummary', t.summaryPlaceholder);
        setText('questionBuilderEyebrow', t.questionEyebrow);
        setText('questionBuilderTitle', t.questionTitle);
        setText('questionBuilderDesc', t.questionDesc);
        setText('questionTextLabel', t.questionText);
        setPlaceholder('quizQuestionText', t.questionPlaceholder);
        setPlaceholder('quizOptionA', this.lang === 'vi' ? 'Đáp án A' : 'Option A');
        setPlaceholder('quizOptionB', this.lang === 'vi' ? 'Đáp án B' : 'Option B');
        setPlaceholder('quizOptionC', this.lang === 'vi' ? 'Đáp án C' : 'Option C');
        setPlaceholder('quizOptionD', this.lang === 'vi' ? 'Đáp án D' : 'Option D');
        setText('questionAnswerLabel', t.answer);
        setText('questionExplainLabel', t.explanation);
        setPlaceholder('quizQuestionExplain', t.explanationPlaceholder);
        setText('resetQuestionEditorBtn', t.resetQuestion);
        setText('draftQuestionsTitle', t.draftTitle);
        setText('resetPrivateQuizBtn', t.resetRoom);
        setText('privateRoomsEyebrow', t.savedRoomsEyebrow);
        setText('privateRoomsTitle', t.savedRoomsTitle);
        setText('privateRoomsDesc', t.savedRoomsDesc);
        setText('publicQuizTitle', t.publicTitle);
        setText('publicQuizDesc', t.publicDesc);
        document.querySelector('#privateRoomAudience option[value="young"]').textContent = t.ages.young;
        document.querySelector('#privateRoomAudience option[value="middle"]').textContent = t.ages.middle;
        document.querySelector('#privateRoomAudience option[value="senior"]').textContent = t.ages.senior;
        document.getElementById('addQuizQuestionBtn').textContent = this.editingQuestionIndex === null ? t.addQuestion : t.updateQuestion;
        document.getElementById('savePrivateQuizBtn').textContent = this.editingRoomId ? t.updateRoom : t.saveRoom;
        document.getElementById('draftQuestionCount').textContent = this.format(t.draftCount, { count: this.draftQuestions.length });
    }

    readQuestionForm() {
        return {
            question: document.getElementById('quizQuestionText')?.value.trim() || '',
            options: ['quizOptionA', 'quizOptionB', 'quizOptionC', 'quizOptionD'].map((id) => document.getElementById(id)?.value.trim() || ''),
            answer: Number(document.getElementById('quizCorrectAnswer')?.value || 0),
            explanation: document.getElementById('quizQuestionExplain')?.value.trim() || ''
        };
    }

    resetQuestionEditor() {
        ['quizQuestionText', 'quizOptionA', 'quizOptionB', 'quizOptionC', 'quizOptionD', 'quizQuestionExplain'].forEach((id) => {
            const node = document.getElementById(id);
            if (node) node.value = '';
        });
        document.getElementById('quizCorrectAnswer').value = '0';
        this.editingQuestionIndex = null;
        this.applyQuizCopy();
    }

    resetRoomBuilder() {
        this.editingRoomId = null;
        this.draftQuestions = [];
        ['privateRoomTitle', 'privateRoomSummary'].forEach((id) => {
            const node = document.getElementById(id);
            if (node) node.value = '';
        });
        document.getElementById('privateRoomAudience').value = 'young';
        this.resetQuestionEditor();
        this.renderDraftQuestions();
        this.applyQuizCopy();
    }

    upsertDraftQuestion() {
        const t = this.text();
        const payload = this.readQuestionForm();
        if (!payload.question) return this.showToast(t.missingQuestion, 'error');
        if (payload.options.some((option) => !option)) return this.showToast(t.missingOptions, 'error');
        if (this.editingQuestionIndex === null) {
            this.draftQuestions.push(payload);
            this.showToast(t.questionAdded, 'success');
        } else {
            this.draftQuestions[this.editingQuestionIndex] = payload;
            this.showToast(t.questionUpdated, 'success');
        }
        this.resetQuestionEditor();
        this.renderDraftQuestions();
    }

    renderDraftQuestions() {
        const t = this.text();
        const container = document.getElementById('draftQuestions');
        if (!container) return;
        document.getElementById('draftQuestionCount').textContent = this.format(t.draftCount, { count: this.draftQuestions.length });
        if (!this.draftQuestions.length) {
            container.innerHTML = `<div class="quiz-empty-state">${this.escapeHtml(t.emptyDraft)}</div>`;
            return;
        }
        container.innerHTML = this.draftQuestions.map((item, index) => `
            <article class="draft-question-card">
                <div class="draft-question-top">
                    <strong>${this.escapeHtml(this.format(t.questionNumber, { count: index + 1 }))}</strong>
                    <div class="draft-question-actions">
                        <button class="btn btn-outline" data-question-action="up" data-question-index="${index}">↑</button>
                        <button class="btn btn-outline" data-question-action="down" data-question-index="${index}">↓</button>
                        <button class="btn btn-outline" data-question-action="edit" data-question-index="${index}">${this.escapeHtml(t.edit)}</button>
                        <button class="btn btn-outline danger-btn" data-question-action="delete" data-question-index="${index}">${this.escapeHtml(t.delete)}</button>
                    </div>
                </div>
                <p class="draft-question-text">${this.escapeHtml(item.question)}</p>
                <ol class="draft-option-list">${item.options.map((option) => `<li>${this.escapeHtml(option)}</li>`).join('')}</ol>
                <div class="draft-answer">${this.escapeHtml(t.correctAnswer)}: ${['A', 'B', 'C', 'D'][item.answer] || 'A'}</div>
                ${item.explanation ? `<div class="draft-explanation">${this.escapeHtml(item.explanation)}</div>` : ''}
            </article>
        `).join('');
    }

    loadQuestionIntoEditor(index) {
        const item = this.draftQuestions[index];
        if (!item) return;
        document.getElementById('quizQuestionText').value = item.question;
        ['quizOptionA', 'quizOptionB', 'quizOptionC', 'quizOptionD'].forEach((id, idx) => {
            document.getElementById(id).value = item.options[idx] || '';
        });
        document.getElementById('quizCorrectAnswer').value = String(item.answer);
        document.getElementById('quizQuestionExplain').value = item.explanation || '';
        this.editingQuestionIndex = index;
        this.applyQuizCopy();
    }

    deleteDraftQuestion(index) {
        this.draftQuestions.splice(index, 1);
        if (this.editingQuestionIndex === index) this.resetQuestionEditor();
        this.renderDraftQuestions();
    }

    moveDraftQuestion(index, delta) {
        const next = index + delta;
        if (next < 0 || next >= this.draftQuestions.length) return;
        [this.draftQuestions[index], this.draftQuestions[next]] = [this.draftQuestions[next], this.draftQuestions[index]];
        this.renderDraftQuestions();
    }

    savePrivateRoom() {
        const t = this.text();
        const title = document.getElementById('privateRoomTitle')?.value.trim() || '';
        const summary = document.getElementById('privateRoomSummary')?.value.trim() || '';
        const audience = document.getElementById('privateRoomAudience')?.value || 'young';
        if (!title) return this.showToast(t.missingRoomTitle, 'error');
        if (!this.draftQuestions.length) return this.showToast(t.missingQuestions, 'error');

        const rooms = this.rooms();
        if (!this.editingRoomId && this.userData.quiz_rooms_remaining <= 0) {
            return this.showToast(t.noRooms, 'error');
        }

        const payload = {
            id: this.editingRoomId || `room_${Date.now()}`,
            title,
            summary,
            audience,
            questions: this.draftQuestions,
            updatedAt: Date.now()
        };

        const index = rooms.findIndex((room) => room.id === payload.id);
        if (index >= 0) rooms[index] = { ...rooms[index], ...payload };
        else {
            rooms.unshift({ ...payload, createdAt: Date.now(), participants: Math.floor(Math.random() * 5) + 1 });
            this.userData.quiz_rooms_remaining -= 1;
            this.saveUserData();
        }

        this.saveRooms(rooms);
        this.updateQuotaDisplay();
        this.renderPrivateRooms();
        this.showToast(index >= 0 ? t.roomUpdated : t.roomCreated, 'success');
        this.resetRoomBuilder();
    }

    loadRoomIntoBuilder(roomId) {
        const room = this.rooms().find((item) => item.id === roomId);
        if (!room) return;
        this.switchTab('private');
        this.editingRoomId = room.id;
        this.draftQuestions = Array.isArray(room.questions) ? [...room.questions] : [];
        document.getElementById('privateRoomTitle').value = room.title || '';
        document.getElementById('privateRoomSummary').value = room.summary || '';
        document.getElementById('privateRoomAudience').value = room.audience || 'young';
        this.resetQuestionEditor();
        this.renderDraftQuestions();
        this.applyQuizCopy();
        document.getElementById('privateRoomTitle')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    deleteRoom(roomId) {
        const rooms = this.rooms().filter((room) => room.id !== roomId);
        this.saveRooms(rooms);
        this.renderPrivateRooms();
        this.showToast(this.text().roomDeleted, 'success');
    }

    renderPrivateRooms() {
        const t = this.text();
        const container = document.getElementById('privateQuizGrid');
        if (!container) return;
        const rooms = this.rooms();
        if (!rooms.length) {
            container.innerHTML = `<div class="quiz-empty-state">${this.escapeHtml(t.emptyRooms)}</div>`;
            return;
        }

        container.innerHTML = rooms.map((room) => `
            <article class="quiz-room-card" style="opacity: 0; transform: translateY(20px);">
                <div class="quiz-room-header">
                    <h3 class="quiz-room-title">${this.escapeHtml(room.title)}</h3>
                    <span class="quiz-room-badge">${this.escapeHtml(t.privateBadge)}</span>
                </div>
                <p class="quiz-room-participants">${this.escapeHtml(this.format(t.questions, { count: room.questions.length }))}</p>
                <p class="quiz-room-summary">${this.escapeHtml(room.summary || '')}</p>
                <details class="quiz-room-details">
                    <summary>${this.escapeHtml(t.view)}</summary>
                    <ol>${room.questions.map((question) => `<li>${this.escapeHtml(question.question)}</li>`).join('')}</ol>
                </details>
                <div class="quiz-room-actions">
                    <button class="btn btn-outline" data-room-action="edit" data-room-id="${room.id}">${this.escapeHtml(t.loadBuilder)}</button>
                    <button class="btn btn-outline danger-btn" data-room-action="delete" data-room-id="${room.id}">${this.escapeHtml(t.delete)}</button>
                </div>
            </article>
        `).join('');

        if (window.gsap) {
            gsap.to(container.querySelectorAll('.quiz-room-card'), {
                opacity: 1, y: 0, duration: 0.6, stagger: 0.1, ease: 'power3.out'
            });
        }
    }

    renderPublicRooms() {
        const t = this.text();
        const container = document.getElementById('publicQuizGrid');
        if (!container) return;
        container.innerHTML = t.monthly.map(([title, desc, participants]) => `
            <article class="quiz-room-card" style="opacity: 0; transform: translateY(20px);">
                <div class="quiz-room-header">
                    <h3 class="quiz-room-title">${this.escapeHtml(title)}</h3>
                    <span class="quiz-room-badge">${this.escapeHtml(t.publicBadge)}</span>
                </div>
                <p class="quiz-room-participants">${this.escapeHtml(this.format(t.participants, { count: participants }))}</p>
                <p class="quiz-room-summary">${this.escapeHtml(desc)}</p>
                <div class="quiz-room-reward">${this.escapeHtml(t.reward)}</div>
                <div class="quiz-room-actions">
                    <button class="btn btn-primary">${this.escapeHtml(t.join)}</button>
                </div>
            </article>
        `).join('');

        if (window.gsap) {
            gsap.to(container.querySelectorAll('.quiz-room-card'), {
                opacity: 1, y: 0, duration: 0.6, stagger: 0.1, ease: 'power3.out'
            });
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.featuresController = new FeaturesController();
});
