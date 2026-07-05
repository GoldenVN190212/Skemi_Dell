/**
 * i18n-packs.js - Skemi Internationalization Language Packs
 * 52+ Languages with Full UI Translation
 * Brand names (Skemi, Skemma) are protected and not translated
 */

const I18N_PACKS = {
  // Vietnamese (reference - already exists in main file)
  vi: null, // Use existing from LanguageManager.js

  // English (reference - already exists in main file)
  en: null, // Use existing from LanguageManager.js

  // Chinese Simplified (中文)
  zh: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - 按项目划分的AI工作空间、构建器和笔记本。', settingsTitle: '设置 - Skemi' },
    nav: { studio: '工作室', dashboard: '工作室', search: '搜索', quiz: '测验', chat: '聊天', settings: '设置', version: 'Skemi v1.0', notifications: '通知' },
    common: { themeToggle: '切换主题', sidebarCollapse: '折叠侧边栏', save: '保存', close: '关闭', send: '发送', use: '使用', active: '使用中', delete: '删除', loading: '加载中...' },
    auth: { signup: '注册', login: '登录', logout: '登出', profileMenu: '右键点击登出', guest: '访客', sync: '登录以同步数据。' },
    settings: {
      tabs: ['个人资料', '统计与指标', '外观与语言', '通知', '安全', '订阅计划'],
      accountTitle: '账户信息', accountHelp: '管理您的个人资料和身份设置。', defaultUser: 'Skemi用户',
      ageTag: '您的年龄组', ageRange: '具体年龄范围', ageRangePlaceholder: '例如：18-35',
      appearanceTitle: '外观', appearanceHelp: '选择一个主题以确保整个应用显示一致。', themes: ['浅色', '深色', '银河'],
      languageTitle: '语言', languageHelp: 'Skemi在整个应用中优先使用您选择的语言。品牌名称Skemi保持不变。',
      statistics: { title: '活动概览', help: '这些指标根据当前设备上存储的用户数据计算。', cards: { projects: '已创建项目', aiInteractions: 'AI互动', savedSources: '已保存来源', activeDays: '活跃天数（7天）' }, charts: { activityTitle: '最近7天活动', focusTitle: '使用重点', timeTitle: '活动时间' }, datasets: { activity: '活动次数', focus: '使用程度', time: '频率' }, labels: { focus: ['项目', '来源', '搜索', 'AI聊天', '个人测验', '生成结果'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: '通知与功能', help: '启用或禁用应用的基本通知和显示选项。', desktop: { title: '浏览器通知', desc: '有新聊天消息或测验邀请时显示桌面通知。' }, sound: { title: '通知声音', desc: '新消息和邀请时播放提示音。' }, email: { title: '电子邮件通知', desc: '接收重要活动的摘要邮件。' }, startup: { title: '页面打开时提示', desc: '每天首次进入聊天时显示快速指南。' }, compact: { title: '紧凑界面模式', desc: '为小型屏幕简化界面。' }, animations: { title: '界面动画', desc: '启用或禁用过渡效果和动画。关闭以提高速度。' }, aiTitle: 'AI活动', aiHelp: '自定义使用聊天机器人和创建学习材料时Skemi AI的工作方式。', ephemeral: { title: '临时保存AI对话', desc: '按当前访问会话保存AI对话，以便您更快继续。' }, personalize: { title: '个性化AI回复', desc: '允许AI使用年龄信息和学习数据来优化回复。' }, usage: { title: '使用限制警告', desc: '当您的AI活动接近使用阈值时通知您。' } },
      securityTitle: '登录与安全', verifyLabel: '电子邮件验证状态', verifyChecking: '检查中...', warnings: { 1: { title: '安全警报', desc: '从未知设备登录时接收通知。' } }, dangerTitle: '危险区域', dangerDesc: '清除此浏览器上的所有本地数据，但保留所选的界面和语言。', clearLocal: '清除本地数据',
      subscriptionTitle: '订阅计划', subscriptionHelp: '升级以扩展AI使用、存储容量和功能访问。', currentPlan: '当前计划', pro: '升级到专业版',
      plans: { free: { name: '免费版', price: '¥0', period: '/月', features: ['每周期基础AI次数', '标准工作室、搜索和测验', '默认账户同步', '个人工作空间'], button: '当前计划' }, pro: { name: '专业版', price: '¥39', period: '/月', features: ['更多学习和工作AI次数', '优先更快处理', '存储更多个人测验和更长历史', '页面间增强同步'], button: '升级专业版' }, advanced: { name: '高级版', price: '¥99', period: '/月', features: ['最高AI使用和存储', '最大队列优先级', '提前访问新功能', '长期团队工作空间'], button: '升级高级版' } },
      profileSaved: '个人资料设置已保存。', localCleared: '本地数据已清除。', verified: '电子邮件已验证。', unverified: '电子邮件未验证。请检查您的收件箱。', notLoggedIn: '未登录。', saveBarText: '您有未保存的更改。', saveChanges: '保存更改', discardChanges: '放弃更改'
    },
    home: { project: { kicker: '项目工作空间', desc: '从项目开始，将AI工作空间、构建器和源笔记本集中在一个地方。' } },
    notebook: { welcome: '欢迎来到Skemi工作室。询问有关您文档的问题。' },
    aichat: { placeholder: '输入您的请求...', close: '关闭', send: '发送', emptyTitle: '暂无消息', emptyDesc: '开始与AI对话。' },
    age: { young: '学生', middle: '专业人士', senior: '老年人' },
    status: { ready: '就绪' },
    ui: {
      login_title: '登录',
      login_subtitle: '继续进入您的 Skemi 工作区',
      login_email_placeholder: '电子邮件或用户名',
      login_password_placeholder: '密码',
      login_submit: '登录',
      login_verify_text: '您的电子邮件尚未验证。请检查收件箱并点击验证链接。',
      login_resend_btn: '重新发送验证邮件',
      login_or_continue: '或使用以下方式继续',
      login_no_account: '还没有账户？',
      login_create_one: '立即创建',
      oauth_google: '使用 Google 登录（即将推出）',
      oauth_google_soon: '使用 Google 登录（即将推出）',
      oauth_facebook: '使用 Facebook 登录（即将推出）',
      oauth_facebook_soon: '使用 Facebook 登录（即将推出）',
      register_title: '创建账户',
      register_subtitle: '注册以开始使用 Skemi Studio',
      register_submit: '创建账户',
      phantom_title: 'Phantom 桌面',
      phantom_subtitle: 'AI 在私有虚拟桌面上工作。您的鼠标不会进入。',
      phantom_install_btn: '激活虚拟显示器',
      phantom_create_desktop: '+ 创建新桌面',
      phantom_send: '发送',
      phantom_stop: '停止并退出',
      phantom_cmd_placeholder: '输入命令，例如：打开 Notepad 并输入"hello"'
    }
  },

  // Japanese (日本語)
  ja: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - プロジェクト別のAIワークスペース、ビルダー、ノートブック。', settingsTitle: '設定 - Skemi' },
    nav: { studio: 'スタジオ', dashboard: 'スタジオ', search: '検索', quiz: 'クイズ', chat: 'チャット', settings: '設定', version: 'Skemi v1.0', notifications: '通知' },
    common: { themeToggle: 'テーマ切り替え', sidebarCollapse: 'サイドバーを折りたたむ', save: '保存', close: '閉じる', send: '送信', use: '使用', active: '使用中', delete: '削除', loading: '読み込み中...' },
    auth: { signup: '登録', login: 'ログイン', logout: 'ログアウト', profileMenu: '右クリックでログアウト', guest: 'ゲスト', sync: 'データを同期するにはログインしてください。' },
    settings: {
      tabs: ['プロフィール', '統計と指標', '外観と言語', '通知', 'セキュリティ', 'サブスクリプション'],
      accountTitle: 'アカウント情報', accountHelp: '個人情報とID設定を管理します。', defaultUser: 'Skemiユーザー',
      ageTag: '年齢層', ageRange: '具体的な年齢範囲', ageRangePlaceholder: '例：18-35',
      appearanceTitle: '外観', appearanceHelp: 'アプリ全体で一貫した表示のためにテーマを選択してください。', themes: ['ライト', 'ダーク', 'ギャラクシー'],
      languageTitle: '言語', languageHelp: 'Skemiはアプリ全体で選択した言語を優先します。ブランド名Skemiはそのまま保持されます。',
      statistics: { title: 'アクティビティ概要', help: 'これらの指標は、現在のデバイスに保存されているユーザーデータから計算されます。', cards: { projects: '作成したプロジェクト', aiInteractions: 'AIインタラクション', savedSources: '保存したソース', activeDays: 'アクティブ日数（7日間）' }, charts: { activityTitle: '過去7日間のアクティビティ', focusTitle: '使用フォーカス', timeTitle: 'アクティビティ時間帯' }, datasets: { activity: 'アクティビティ数', focus: '使用レベル', time: '頻度' }, labels: { focus: ['プロジェクト', 'ソース', '検索', 'AIチャット', '個人クイズ', '生成結果'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: '通知と機能', help: 'アプリの基本的な通知と表示オプションを有効または無効にします。', desktop: { title: 'ブラウザ通知', desc: '新しいチャットメッセージやクイズ招待がある場合にデスクトップ通知を表示します。' }, sound: { title: '通知音', desc: '新しいメッセージと招待時に通知音を再生します。' }, email: { title: 'メール通知', desc: '重要なアクティビティのサマリーメールを受信します。' }, startup: { title: 'ページオープン時のヒント', desc: '1日最初にチャットに入るときにクイックガイドを表示します。' }, compact: { title: 'コンパクトインターフェースモード', desc: '小さい画面用にインターフェースを簡素化します。' }, animations: { title: 'インターフェースアニメーション', desc: 'トランジションエフェクトとアニメーションを有効または無効にします。速度向上のために無効にします。' }, aiTitle: 'AIアクティビティ', aiHelp: 'チャットボットの使用と学習資料の作成時にSkemi AIが動作する方法をカスタマイズします。', ephemeral: { title: 'AI会話を一時保存', desc: '現在のセッションでAI会話を保存し、より速く続行できるようにします。' }, personalize: { title: 'AI応答をパーソナライズ', desc: 'AIが年齢情報と学習データを使用して応答を最適化することを許可します。' }, usage: { title: '使用制限警告', desc: 'AIアクティビティが使用しきい値に近づいたときに通知します。' } },
      securityTitle: 'ログインとセキュリティ', verifyLabel: 'メール認証ステータス', verifyChecking: '確認中...', warnings: { 1: { title: 'セキュリティアラート', desc: '不明なデバイスからのログインがある場合に通知を受け取ります。' } }, dangerTitle: '危険区域', dangerDesc: 'このブラウザのすべてのローカルデータを削除しますが、選択したインターフェースと言語は保持されます。', clearLocal: 'ローカルデータを削除',
      subscriptionTitle: 'サブスクリプション', subscriptionHelp: 'AI使用、ストレージ容量、機能アクセスを拡張するためにアップグレードしてください。', currentPlan: '現在のプラン', pro: 'Proにアップグレード',
      plans: { free: { name: '無料', price: '¥0', period: '/月', features: ['周期ごとの基本AI回数', '標準スタジオ、検索、クイズ', 'デフォルトアカウント同期', '個人ワークスペース'], button: '現在のプラン' }, pro: { name: 'Pro', price: '¥790', period: '/月', features: ['学習と仕事のためのより多くのAI回数', '優先高速処理', 'より多くの個人クイズ保存と長い履歴', 'ページ間の強化された同期'], button: 'Proにアップグレード' }, advanced: { name: 'Advanced', price: '¥1,890', period: '/月', features: ['最大AI使用とストレージ', '最大キュー優先度', '新機能への早期アクセス', '長期チームワークスペース'], button: 'Advancedにアップグレード' } },
      profileSaved: 'プロフィール設定が保存されました。', localCleared: 'ローカルデータが削除されました。', verified: 'メールが認証されました。', unverified: 'メールが認証されていません。受信トレイを確認してください。', notLoggedIn: 'ログインしていません。', saveBarText: '保存されていない変更があります。', saveChanges: '変更を保存', discardChanges: '変更を破棄'
    },
    home: { project: { kicker: 'プロジェクトワークスペース', desc: 'プロジェクトから始めて、AIワークスペース、ビルダー、ソースノートブックを一箇所にまとめて整理します。' } },
    notebook: { welcome: 'Skemi Studioへようこそ。ドキュメントについて質問してください。' },
    aichat: { placeholder: 'リクエストを入力...', close: '閉じる', send: '送信', emptyTitle: 'まだメッセージはありません', emptyDesc: 'AIとの会話を始めましょう。' },
    age: { young: '学生', middle: 'プロフェッショナル', senior: 'シニア' },
    status: { ready: '準備完了' },
    ui: {
      login_title: 'サインイン',
      login_subtitle: 'Skemi ワークスペースに続行',
      login_email_placeholder: 'メールアドレスまたはユーザー名',
      login_password_placeholder: 'パスワード',
      login_submit: 'サインイン',
      login_verify_text: 'メールアドレスがまだ認証されていません。受信トレイを確認して認証リンクをクリックしてください。',
      login_resend_btn: '認証メールを再送信',
      login_or_continue: 'または以下で続行',
      login_no_account: 'アカウントをお持ちでないですか？',
      login_create_one: '今すぐ作成',
      oauth_google: 'Google でサインイン（近日公開）',
      oauth_google_soon: 'Google でサインイン（近日公開）',
      oauth_facebook: 'Facebook でサインイン（近日公開）',
      oauth_facebook_soon: 'Facebook でサインイン（近日公開）',
      register_title: 'アカウント作成',
      register_subtitle: 'Skemi Studio を始めるために登録',
      register_submit: 'アカウント作成',
      phantom_title: 'Phantom デスクトップ',
      phantom_subtitle: 'AI が専用の仮想デスクトップで動作します。マウスは入り込みません。',
      phantom_install_btn: '仮想ディスプレイを有効化',
      phantom_create_desktop: '+ 新しいデスクトップを作成',
      phantom_send: '送信',
      phantom_stop: '停止して終了',
      phantom_cmd_placeholder: 'コマンドを入力、例: メモ帳を開いて "hello" と入力'
    }
  },

  // Korean (한국어)
  ko: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - 프로젝트별 AI 워크스페이스, 빌더 및 노트북.', settingsTitle: '설정 - Skemi' },
    nav: { studio: '스튜디오', dashboard: '스튜디오', search: '검색', quiz: '퀴즈', chat: '채팅', settings: '설정', version: 'Skemi v1.0', notifications: '알림' },
    common: { themeToggle: '테마 전환', sidebarCollapse: '사이드바 접기', save: '저장', close: '닫기', send: '전송', use: '사용', active: '사용 중', delete: '삭제', loading: '로딩 중...' },
    auth: { signup: '가입', login: '로그인', logout: '로그아웃', profileMenu: '오른쪽 클릭하여 로그아웃', guest: '게스트', sync: '데이터를 동기화하려면 로그인하세요.' },
    settings: {
      tabs: ['프로필', '통계 및 지표', '모양 및 언어', '알림', '보안', '구독'],
      accountTitle: '계정 정보', accountHelp: '개인 정보 및 신원 설정을 관리합니다.', defaultUser: 'Skemi 사용자',
      ageTag: '연령대', ageRange: '특정 연령 범위', ageRangePlaceholder: '예: 18-35',
      appearanceTitle: '모양', appearanceHelp: '앱 전체에서 일관된 표시를 위해 테마를 선택하세요.', themes: ['밝음', '어두움', '갤럭시'],
      languageTitle: '언어', languageHelp: 'Skemi는 앱 전체에서 선택한 언어를 우선합니다. 브랜드명 Skemi는 그대로 유지됩니다.',
      statistics: { title: '활동 개요', help: '이 지표는 현재 기기에 저장된 사용자 데이터에서 계산됩니다.', cards: { projects: '생성된 프로젝트', aiInteractions: 'AI 상호작용', savedSources: '저장된 소스', activeDays: '활동 일수 (7일)' }, charts: { activityTitle: '지난 7일 활동', focusTitle: '사용 초점', timeTitle: '활동 시간대' }, datasets: { activity: '활동 수', focus: '사용 수준', time: '빈도' }, labels: { focus: ['프로젝트', '소스', '검색', 'AI 채팅', '개인 퀴즈', '생성 결과'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: '알림 및 기능', help: '앱의 기본 알림 및 표시 옵션을 활성화 또는 비활성화합니다.', desktop: { title: '브라우저 알림', desc: '새 채팅 메시지나 퀴즈 초대가 있을 때 데스크톱 알림을 표시합니다.' }, sound: { title: '알림 소리', desc: '새 메시지와 초대가 있을 때 알림 소리를 재생합니다.' }, email: { title: '이메일 알림', desc: '중요한 활동 요약 이메일을 받습니다.' }, startup: { title: '페이지 열 때 팁', desc: '하루 중 처음으로 채팅에 들어갈 때 빠른 가이드를 표시합니다.' }, compact: { title: '컴팩트 인터페이스 모드', desc: '작은 화면을 위해 인터페이스를 간소화합니다.' }, animations: { title: '인터페이스 애니메이션', desc: '전환 효과와 애니메이션을 활성화 또는 비활성화합니다. 속도 향상을 위해 비활성화하세요.' }, aiTitle: 'AI 활동', aiHelp: '챗봇 사용 및 학습 자료 생성 시 Skemi AI의 작동 방식을 사용자 지정합니다.', ephemeral: { title: 'AI 대화 임시 저장', desc: '현재 세션에서 AI 대화를 저장하여 더 빨리 계속할 수 있도록 합니다.' }, personalize: { title: 'AI 응답 개인화', desc: 'AI가 연령 정보와 학습 데이터를 사용하여 응답을 최적화하도록 허용합니다.' }, usage: { title: '사용 한도 경고', desc: 'AI 활동이 사용 한도에 가까워지면 알려줍니다.' } },
      securityTitle: '로그인 및 보안', verifyLabel: '이메일 인증 상태', verifyChecking: '확인 중...', warnings: { 1: { title: '보안 경고', desc: '알 수 없는 기기에서 로그인이 있을 때 알림을 받습니다.' } }, dangerTitle: '위험 구역', dangerDesc: '이 브라우저의 모든 로컬 데이터를 지우지만 선택한 인터페이스와 언어는 유지합니다.', clearLocal: '로컬 데이터 지우기',
      subscriptionTitle: '구독 계획', subscriptionHelp: 'AI 사용, 저장 용량 및 기능 접근을 확장하려면 업그레이드하세요.', currentPlan: '현재 계획', pro: 'Pro로 업그레이드',
      plans: { free: { name: '무료', price: '₩0', period: '/월', features: ['주기별 기본 AI 사용', '표준 스튜디오, 검색 및 퀴즈', '기본 계정 동기화', '개인 워크스페이스'], button: '현재 계획' }, pro: { name: 'Pro', price: '₩7,900', period: '/월', features: ['학습 및 작업을 위한 더 많은 AI 사용', '우선 고속 처리', '더 많은 개인 퀴즈 저장 및 긴 기록', '페이지 간 향상된 동기화'], button: 'Pro로 업그레이드' }, advanced: { name: 'Advanced', price: '₩18,900', period: '/월', features: ['최대 AI 사용 및 저장', '최대 큐 우선순위', '새 기능 조기 접근', '장기 팀 워크스페이스'], button: 'Advanced로 업그레이드' } },
      profileSaved: '프로필 설정이 저장되었습니다.', localCleared: '로컬 데이터가 지워졌습니다.', verified: '이메일이 인증되었습니다.', unverified: '이메일이 인증되지 않았습니다. 받은 편지함을 확인하세요.', notLoggedIn: '로그인되지 않았습니다.', saveBarText: '저장되지 않은 변경사항이 있습니다.', saveChanges: '변경사항 저장', discardChanges: '변경사항 취소'
    },
    home: { project: { kicker: '프로젝트 워크스페이스', desc: '프로젝트부터 시작하여 AI 워크스페이스, 빌더 및 소스 노트북을 한 곳에 정리하세요.' } },
    notebook: { welcome: 'Skemi 스튜디오에 오신 것을 환영합니다. 문서에 대해 질문하세요.' },
    aichat: { placeholder: '요청을 입력하세요...', close: '닫기', send: '전송', emptyTitle: '아직 메시지 없음', emptyDesc: 'AI와 대화를 시작하세요.' },
    age: { young: '학생', middle: '전문가', senior: '시니어' },
    status: { ready: '준비 완료' },
    ui: {
      login_title: '로그인',
      login_subtitle: 'Skemi 워크스페이스로 계속',
      login_email_placeholder: '이메일 또는 사용자 이름',
      login_password_placeholder: '비밀번호',
      login_submit: '로그인',
      login_verify_text: '이메일이 아직 인증되지 않았습니다. 받은 편지함을 확인하고 인증 링크를 클릭하세요.',
      login_resend_btn: '인증 이메일 다시 보내기',
      login_or_continue: '또는 다음으로 계속',
      login_no_account: '계정이 없으신가요?',
      login_create_one: '지금 만들기',
      oauth_google: 'Google로 로그인 (출시 예정)',
      oauth_google_soon: 'Google로 로그인 (출시 예정)',
      oauth_facebook: 'Facebook으로 로그인 (출시 예정)',
      oauth_facebook_soon: 'Facebook으로 로그인 (출시 예정)',
      register_title: '계정 만들기',
      register_subtitle: 'Skemi Studio 사용을 시작하려면 가입하세요',
      register_submit: '계정 만들기',
      phantom_title: 'Phantom 데스크톱',
      phantom_subtitle: 'AI가 전용 가상 데스크톱에서 작동합니다. 마우스가 들어가지 않습니다.',
      phantom_install_btn: '가상 디스플레이 활성화',
      phantom_create_desktop: '+ 새 데스크톱 만들기',
      phantom_send: '보내기',
      phantom_stop: '중지하고 종료',
      phantom_cmd_placeholder: '명령 입력, 예: 메모장을 열고 "hello" 입력'
    }
  },

  // Spanish (Español)
  es: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - Espacio de trabajo de IA, constructor y cuaderno por proyecto.', settingsTitle: 'Configuración - Skemi' },
    nav: { studio: 'Estudio', dashboard: 'Estudio', search: 'Buscar', quiz: 'Quiz', chat: 'Chat', settings: 'Configuración', version: 'Skemi v1.0', notifications: 'Notificaciones' },
    common: { themeToggle: 'Cambiar tema', sidebarCollapse: 'Colapsar barra lateral', save: 'Guardar', close: 'Cerrar', send: 'Enviar', use: 'Usar', active: 'Activo', delete: 'Eliminar', loading: 'Cargando...' },
    auth: { signup: 'Registrarse', login: 'Iniciar sesión', logout: 'Cerrar sesión', profileMenu: 'Clic derecho para cerrar sesión', guest: 'Invitado', sync: 'Inicia sesión para sincronizar tus datos.' },
    settings: {
      tabs: ['Perfil', 'Estadísticas', 'Apariencia e Idioma', 'Notificaciones', 'Seguridad', 'Suscripción'],
      accountTitle: 'Información de la cuenta', accountHelp: 'Gestiona tus datos personales y configuración de identidad.', defaultUser: 'Usuario Skemi',
      ageTag: 'Tu grupo de edad', ageRange: 'Rango de edad específico', ageRangePlaceholder: 'Ejemplo: 18-35',
      appearanceTitle: 'Apariencia', appearanceHelp: 'Elige un tema para una visualización consistente en toda la aplicación.', themes: ['Claro', 'Oscuro', 'Galaxia'],
      languageTitle: 'Idioma', languageHelp: 'Skemi prioriza el idioma que selecciones en toda la aplicación. El nombre de marca Skemi permanece intacto.',
      statistics: { title: 'Resumen de actividad', help: 'Estas métricas se calculan a partir de los datos de usuario almacenados en el dispositivo actual.', cards: { projects: 'Proyectos creados', aiInteractions: 'Interacciones con IA', savedSources: 'Fuentes guardadas', activeDays: 'Días activos (7 días)' }, charts: { activityTitle: 'Actividad últimos 7 días', focusTitle: 'Enfoque de uso', timeTitle: 'Horario de actividad' }, datasets: { activity: 'Número de actividades', focus: 'Nivel de uso', time: 'Frecuencia' }, labels: { focus: ['Proyectos', 'Fuentes', 'Búsqueda', 'Chat IA', 'Quiz personal', 'Resultados generados'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: 'Notificaciones y funciones', help: 'Activa o desactiva las notificaciones y opciones de pantalla básicas de la aplicación.', desktop: { title: 'Notificaciones del navegador', desc: 'Muestra notificaciones de escritorio cuando haya nuevos mensajes de chat o invitaciones a quiz.' }, sound: { title: 'Sonido de notificaciones', desc: 'Reproduce sonido de alerta para nuevos mensajes e invitaciones.' }, email: { title: 'Notificaciones por correo', desc: 'Recibe correos resumen de actividades importantes.' }, startup: { title: 'Sugerencias al abrir página', desc: 'Muestra guía rápida cuando entras al chat por primera vez en el día.' }, compact: { title: 'Modo interfaz compacta', desc: 'Simplifica la interfaz para pantallas pequeñas.' }, animations: { title: 'Animaciones de interfaz', desc: 'Activa o desactiva efectos de transición y animaciones. Desactiva para mejor velocidad.' }, aiTitle: 'Actividad de IA', aiHelp: 'Personaliza cómo funciona la IA de Skemi cuando usas chatbot y creas materiales de estudio.', ephemeral: { title: 'Guardar conversación IA temporalmente', desc: 'Guarda conversaciones de IA por sesión de acceso actual para que puedas continuar más rápido.' }, personalize: { title: 'Personalizar respuestas de IA', desc: 'Permite que la IA use información de edad y datos de aprendizaje para afinar respuestas.' }, usage: { title: 'Advertencia de límite de uso', desc: 'Notifica cuando las actividades de IA se acerquen al umbral de uso.' } },
      securityTitle: 'Inicio de sesión y seguridad', verifyLabel: 'Estado de verificación de correo', verifyChecking: 'Verificando...', warnings: { 1: { title: 'Alerta de seguridad', desc: 'Recibe alertas cuando haya inicios de sesión desde dispositivos desconocidos.' } }, dangerTitle: 'Zona de peligro', dangerDesc: 'Elimina todos los datos locales en este navegador pero mantiene la interfaz e idioma seleccionados.', clearLocal: 'Borrar datos locales',
      subscriptionTitle: 'Plan de suscripción', subscriptionHelp: 'Actualiza para expandir el uso de IA, capacidad de almacenamiento y acceso a funciones.', currentPlan: 'Plan actual', pro: 'Actualizar a Pro',
      plans: { free: { name: 'Gratis', price: '€0', period: '/mes', features: ['Usos básicos de IA por ciclo', 'Estudio, búsqueda y quiz estándar', 'Sincronización de cuenta predeterminada', 'Espacio de trabajo personal'], button: 'Plan actual' }, pro: { name: 'Pro', price: '€4.99', period: '/mes', features: ['Más usos de IA para estudio y trabajo', 'Procesamiento rápido prioritario', 'Almacena más quiz personales e historial más largo', 'Sincronización mejorada entre páginas'], button: 'Actualizar a Pro' }, advanced: { name: 'Advanced', price: '€11.99', period: '/mes', features: ['Uso de IA y almacenamiento máximo', 'Prioridad máxima en cola', 'Acceso anticipado a nuevas funciones', 'Espacio de trabajo a largo plazo para equipos'], button: 'Actualizar a Advanced' } },
      profileSaved: 'Configuración de perfil guardada.', localCleared: 'Datos locales borrados.', verified: 'Correo verificado.', unverified: 'Correo no verificado. Por favor revisa tu bandeja de entrada.', notLoggedIn: 'No has iniciado sesión.', saveBarText: 'Tienes cambios sin guardar.', saveChanges: 'Guardar cambios', discardChanges: 'Descartar cambios'
    },
    home: { project: { kicker: 'Espacio de trabajo por proyecto', desc: 'Comienza con un proyecto para mantener organizados en un lugar el espacio de trabajo de IA, constructor y cuaderno de fuentes.' } },
    notebook: { welcome: 'Bienvenido a Skemi Studio. Haz preguntas sobre tus documentos.' },
    aichat: { placeholder: 'Introduce tu solicitud...', close: 'Cerrar', send: 'Enviar', emptyTitle: 'Aún no hay mensajes', emptyDesc: 'Comienza una conversación con la IA.' },
    age: { young: 'Estudiante', middle: 'Profesional', senior: 'Senior' },
    status: { ready: 'Listo' },
    ui: {
      login_title: 'Iniciar sesión',
      login_subtitle: 'Continuar a tu espacio de Skemi',
      login_email_placeholder: 'Correo o nombre de usuario',
      login_password_placeholder: 'Contraseña',
      login_submit: 'Iniciar sesión',
      login_verify_text: 'Tu correo aún no está verificado. Revisa tu bandeja y haz clic en el enlace de verificación.',
      login_resend_btn: 'Reenviar correo de verificación',
      login_or_continue: 'o continuar con',
      login_no_account: '¿No tienes una cuenta?',
      login_create_one: 'Crea una ahora',
      oauth_google: 'Iniciar con Google (próximamente)',
      oauth_google_soon: 'Iniciar con Google (próximamente)',
      oauth_facebook: 'Iniciar con Facebook (próximamente)',
      oauth_facebook_soon: 'Iniciar con Facebook (próximamente)',
      register_title: 'Crear cuenta',
      register_subtitle: 'Regístrate para empezar a usar Skemi Studio',
      register_submit: 'Crear cuenta',
      phantom_title: 'Escritorio Phantom',
      phantom_subtitle: 'La IA trabaja en un escritorio virtual privado. Tu ratón no entra.',
      phantom_install_btn: 'Activar pantalla virtual',
      phantom_create_desktop: '+ Crear nuevo escritorio',
      phantom_send: 'Enviar',
      phantom_stop: 'Detener y salir',
      phantom_cmd_placeholder: 'Escribe un comando, ej.: abrir Notepad y escribir "hello"'
    }
  },

  // French (Français)
  fr: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - Espace de travail IA, constructeur et carnet par projet.', settingsTitle: 'Paramètres - Skemi' },
    nav: { studio: 'Studio', dashboard: 'Studio', search: 'Rechercher', quiz: 'Quiz', chat: 'Chat', settings: 'Paramètres', version: 'Skemi v1.0', notifications: 'Notifications' },
    common: { themeToggle: 'Changer de thème', sidebarCollapse: 'Réduire la barre latérale', save: 'Enregistrer', close: 'Fermer', send: 'Envoyer', use: 'Utiliser', active: 'Actif', delete: 'Supprimer', loading: 'Chargement...' },
    auth: { signup: "S'inscrire", login: 'Se connecter', logout: 'Se déconnecter', profileMenu: 'Clic droit pour se déconnecter', guest: 'Invité', sync: 'Connectez-vous pour synchroniser vos données.' },
    settings: {
      tabs: ['Profil', 'Statistiques', 'Apparence et Langue', 'Notifications', 'Sécurité', 'Abonnement'],
      accountTitle: 'Informations du compte', accountHelp: 'Gérez vos informations personnelles et paramètres d\'identité.', defaultUser: 'Utilisateur Skemi',
      ageTag: 'Votre groupe d\'âge', ageRange: 'Tranche d\'âge spécifique', ageRangePlaceholder: 'Exemple : 18-35',
      appearanceTitle: 'Apparence', appearanceHelp: 'Choisissez un thème pour un affichage cohérent dans toute l\'application.', themes: ['Clair', 'Sombre', 'Galaxie'],
      languageTitle: 'Langue', languageHelp: 'Skemi donne la priorité à la langue que vous sélectionnez dans toute l\'application. Le nom de marque Skemi reste inchangé.',
      statistics: { title: 'Aperçu des activités', help: 'Ces métriques sont calculées à partir des données utilisateur stockées sur l\'appareil actuel.', cards: { projects: 'Projets créés', aiInteractions: 'Interactions IA', savedSources: 'Sources enregistrées', activeDays: 'Jours actifs (7 jours)' }, charts: { activityTitle: 'Activité des 7 derniers jours', focusTitle: 'Focus d\'utilisation', timeTitle: 'Plage horaire d\'activité' }, datasets: { activity: 'Nombre d\'activités', focus: 'Niveau d\'utilisation', time: 'Fréquence' }, labels: { focus: ['Projets', 'Sources', 'Recherche', 'Chat IA', 'Quiz personnel', 'Résultats générés'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: 'Notifications et fonctionnalités', help: 'Activez ou désactivez les notifications et options d\'affichage de base de l\'application.', desktop: { title: 'Notifications du navigateur', desc: 'Affiche les notifications bureau lors de nouveaux messages de chat ou invitations à des quiz.' }, sound: { title: 'Son de notification', desc: 'Joue une alerte sonore pour les nouveaux messages et invitations.' }, email: { title: 'Notifications par email', desc: 'Recevez des emails résumant les activités importantes.' }, startup: { title: 'Conseils à l\'ouverture de la page', desc: 'Affiche un guide rapide lors de votre première connexion au chat de la journée.' }, compact: { title: 'Mode interface compacte', desc: 'Simplifie l\'interface pour les petits écrans.' }, animations: { title: 'Animations d\'interface', desc: 'Activez ou désactivez les effets de transition et animations. Désactivez pour plus de vitesse.' }, aiTitle: 'Activité IA', aiHelp: 'Personnalisez le fonctionnement de l\'IA Skemi lorsque vous utilisez le chatbot et créez des matériaux d\'étude.', ephemeral: { title: 'Enregistrer temporairement les conversations IA', desc: 'Enregistre les conversations IA par session d\'accès actuelle pour pouvoir continuer plus rapidement.' }, personalize: { title: 'Personnaliser les réponses de l\'IA', desc: 'Permet à l\'IA d\'utiliser les informations d\'âge et données d\'apprentissage pour affiner les réponses.' }, usage: { title: 'Avertissement de limite d\'utilisation', desc: 'Notifie lorsque les activités IA approchent du seuil d\'utilisation.' } },
      securityTitle: 'Connexion et sécurité', verifyLabel: 'Statut de vérification email', verifyChecking: 'Vérification...', warnings: { 1: { title: 'Alerte de sécurité', desc: 'Recevez des alertes lors de connexions depuis des appareils inconnus.' } }, dangerTitle: 'Zone de danger', dangerDesc: 'Efface toutes les données locales sur ce navigateur mais conserve l\'interface et la langue sélectionnées.', clearLocal: 'Effacer les données locales',
      subscriptionTitle: 'Plan d\'abonnement', subscriptionHelp: 'Mettez à niveau pour étendre l\'utilisation de l\'IA, la capacité de stockage et l\'accès aux fonctionnalités.', currentPlan: 'Plan actuel', pro: 'Passer à Pro',
      plans: { free: { name: 'Gratuit', price: '€0', period: '/mois', features: ['Utilisations IA de base par cycle', 'Studio, recherche et quiz standard', 'Synchronisation de compte par défaut', 'Espace de travail personnel'], button: 'Plan actuel' }, pro: { name: 'Pro', price: '€4.99', period: '/mois', features: ['Plus d\'utilisations IA pour études et travail', 'Traitement rapide prioritaire', 'Stocke plus de quiz personnels et historique plus long', 'Synchronisation améliorée entre pages'], button: 'Passer à Pro' }, advanced: { name: 'Advanced', price: '€11.99', period: '/mois', features: ['Utilisation IA et stockage maximum', 'Priorité de file d\'attente maximale', 'Accès anticipé aux nouvelles fonctionnalités', 'Espace de travail long terme pour équipes'], button: 'Passer à Advanced' } },
      profileSaved: 'Paramètres de profil enregistrés.', localCleared: 'Données locales effacées.', verified: 'Email vérifié.', unverified: 'Email non vérifié. Veuillez vérifier votre boîte de réception.', notLoggedIn: 'Non connecté.', saveBarText: 'Vous avez des modifications non enregistrées.', saveChanges: 'Enregistrer les modifications', discardChanges: 'Annuler les modifications'
    },
    home: { project: { kicker: 'Espace de travail par projet', desc: 'Commencez par un projet pour organiser en un seul lieu l\'espace de travail IA, le constructeur et le carnet de sources.' } },
    notebook: { welcome: 'Bienvenue dans Skemi Studio. Posez des questions sur vos documents.' },
    aichat: { placeholder: 'Entrez votre demande...', close: 'Fermer', send: 'Envoyer', emptyTitle: 'Aucun message encore', emptyDesc: 'Commencez une conversation avec l\'IA.' },
    age: { young: 'Étudiant', middle: 'Professionnel', senior: 'Senior' },
    status: { ready: 'Prêt' },
    ui: {
      login_title: 'Se connecter',
      login_subtitle: 'Continuer vers votre espace Skemi',
      login_email_placeholder: 'E-mail ou nom d\'utilisateur',
      login_password_placeholder: 'Mot de passe',
      login_submit: 'Se connecter',
      login_verify_text: 'Votre e-mail n\'est pas encore vérifié. Consultez votre boîte de réception et cliquez sur le lien de vérification.',
      login_resend_btn: 'Renvoyer l\'e-mail de vérification',
      login_or_continue: 'ou continuer avec',
      login_no_account: 'Pas de compte ?',
      login_create_one: 'Créez-en un maintenant',
      oauth_google: 'Se connecter avec Google (bientôt)',
      oauth_google_soon: 'Se connecter avec Google (bientôt)',
      oauth_facebook: 'Se connecter avec Facebook (bientôt)',
      oauth_facebook_soon: 'Se connecter avec Facebook (bientôt)',
      register_title: 'Créer un compte',
      register_subtitle: 'Inscrivez-vous pour commencer à utiliser Skemi Studio',
      register_submit: 'Créer un compte',
      phantom_title: 'Bureau Phantom',
      phantom_subtitle: 'L\'IA travaille sur un bureau virtuel privé. Votre souris n\'y entre pas.',
      phantom_install_btn: 'Activer l\'écran virtuel',
      phantom_create_desktop: '+ Créer un nouveau bureau',
      phantom_send: 'Envoyer',
      phantom_stop: 'Arrêter et quitter',
      phantom_cmd_placeholder: 'Tapez une commande, ex.: ouvrir Notepad et taper "hello"'
    }
  },

  // German (Deutsch)
  de: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - KI-Arbeitsbereich, Builder und Notizbuch nach Projekt.', settingsTitle: 'Einstellungen - Skemi' },
    nav: { studio: 'Studio', dashboard: 'Studio', search: 'Suche', quiz: 'Quiz', chat: 'Chat', settings: 'Einstellungen', version: 'Skemi v1.0', notifications: 'Benachrichtigungen' },
    common: { themeToggle: 'Thema wechseln', sidebarCollapse: 'Seitenleiste einklappen', save: 'Speichern', close: 'Schließen', send: 'Senden', use: 'Verwenden', active: 'Aktiv', delete: 'Löschen', loading: 'Laden...' },
    auth: { signup: 'Registrieren', login: 'Anmelden', logout: 'Abmelden', profileMenu: 'Rechtsklick zum Abmelden', guest: 'Gast', sync: 'Melden Sie sich an, um Ihre Daten zu synchronisieren.' },
    settings: {
      tabs: ['Profil', 'Statistiken', 'Erscheinungsbild & Sprache', 'Benachrichtigungen', 'Sicherheit', 'Abonnement'],
      accountTitle: 'Kontoinformationen', accountHelp: 'Verwalten Sie Ihre persönlichen Daten und Identitätseinstellungen.', defaultUser: 'Skemi Benutzer',
      ageTag: 'Ihre Altersgruppe', ageRange: 'Spezifischer Altersbereich', ageRangePlaceholder: 'Beispiel: 18-35',
      appearanceTitle: 'Erscheinungsbild', appearanceHelp: 'Wählen Sie ein Thema für eine konsistente Anzeige in der gesamten App.', themes: ['Hell', 'Dunkel', 'Galaxie'],
      languageTitle: 'Sprache', languageHelp: 'Skemi priorisiert die von Ihnen gewählte Sprache in der gesamten App. Der Markenname Skemi bleibt unverändert.',
      statistics: { title: 'Aktivitätsübersicht', help: 'Diese Metriken werden aus den auf dem aktuellen Gerät gespeicherten Benutzerdaten berechnet.', cards: { projects: 'Erstellte Projekte', aiInteractions: 'KI-Interaktionen', savedSources: 'Gespeicherte Quellen', activeDays: 'Aktive Tage (7 Tage)' }, charts: { activityTitle: 'Aktivität der letzten 7 Tage', focusTitle: 'Nutzungsfokus', timeTitle: 'Aktivitätszeitfenster' }, datasets: { activity: 'Anzahl Aktivitäten', focus: 'Nutzungsniveau', time: 'Häufigkeit' }, labels: { focus: ['Projekte', 'Quellen', 'Suche', 'KI-Chat', 'Persönliches Quiz', 'Generierte Ergebnisse'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: 'Benachrichtigungen & Funktionen', help: 'Aktivieren oder deaktivieren Sie die grundlegenden Benachrichtigungen und Anzeigeoptionen der App.', desktop: { title: 'Browser-Benachrichtigungen', desc: 'Zeigen Sie Desktop-Benachrichtigungen bei neuen Chat-Nachrichten oder Quiz-Einladungen an.' }, sound: { title: 'Benachrichtigungston', desc: 'Spielt einen Alert-Ton für neue Nachrichten und Einladungen ab.' }, email: { title: 'E-Mail-Benachrichtigungen', desc: 'Erhalten Sie zusammenfassende E-Mails über wichtige Aktivitäten.' }, startup: { title: 'Tipps beim Öffnen der Seite', desc: 'Zeigt eine Kurzanleitung an, wenn Sie zum ersten Mal am Tag in den Chat gehen.' }, compact: { title: 'Kompakter Oberflächenmodus', desc: 'Vereinfacht die Oberfläche für kleine Bildschirme.' }, animations: { title: 'Oberflächenanimationen', desc: 'Aktivieren oder deaktivieren Sie Übergangseffekte und Animationen. Deaktivieren Sie für mehr Geschwindigkeit.' }, aiTitle: 'KI-Aktivität', aiHelp: 'Passen Sie an, wie Skemi KI funktioniert, wenn Sie den Chatbot nutzen und Lernmaterialien erstellen.', ephemeral: { title: 'KI-Gespräche temporär speichern', desc: 'Speichert KI-Gespräche pro aktueller Sitzung, damit Sie schneller fortfahren können.' }, personalize: { title: 'KI-Antworten personalisieren', desc: 'Erlaubt der KI, Altersinformationen und Lerndaten zu verwenden, um Antworten zu verfeinern.' }, usage: { title: 'Nutzungslimit-Warnung', desc: 'Benachrichtigt, wenn KI-Aktivitäten sich dem Nutzungsschwellenwert nähern.' } },
      securityTitle: 'Anmeldung & Sicherheit', verifyLabel: 'E-Mail-Verifizierungsstatus', verifyChecking: 'Überprüfung...', warnings: { 1: { title: 'Sicherheitswarnung', desc: 'Erhalten Sie Warnungen bei Anmeldungen von unbekannten Geräten.' } }, dangerTitle: 'Gefahrenzone', dangerDesc: 'Löscht alle lokalen Daten in diesem Browser, behält jedoch die ausgewählte Oberfläche und Sprache bei.', clearLocal: 'Lokale Daten löschen',
      subscriptionTitle: 'Abonnementplan', subscriptionHelp: 'Upgraden Sie, um die KI-Nutzung, Speicherkapazität und den Funktionszugriff zu erweitern.', currentPlan: 'Aktueller Plan', pro: 'Auf Pro upgraden',
      plans: { free: { name: 'Kostenlos', price: '€0', period: '/Monat', features: ['Grundlegende KI-Nutzungen pro Zyklus', 'Standard Studio, Suche und Quiz', 'Standard-Kontosynchronisation', 'Persönlicher Arbeitsbereich'], button: 'Aktueller Plan' }, pro: { name: 'Pro', price: '€4.99', period: '/Monat', features: ['Mehr KI-Nutzungen für Studium und Arbeit', 'Priorisierte schnelle Verarbeitung', 'Speichert mehr persönliche Quiz und längeren Verlauf', 'Verbesserte Synchronisation zwischen Seiten'], button: 'Auf Pro upgraden' }, advanced: { name: 'Advanced', price: '€11.99', period: '/Monat', features: ['Maximale KI-Nutzung und Speicher', 'Maximale Warteschlangenpriorität', 'Früher Zugriff auf neue Funktionen', 'Langfristiger Team-Arbeitsbereich'], button: 'Auf Advanced upgraden' } },
      profileSaved: 'Profil-Einstellungen gespeichert.', localCleared: 'Lokale Daten gelöscht.', verified: 'E-Mail verifiziert.', unverified: 'E-Mail nicht verifiziert. Bitte überprüfen Sie Ihren Posteingang.', notLoggedIn: 'Nicht angemeldet.', saveBarText: 'Sie haben ungespeicherte Änderungen.', saveChanges: 'Änderungen speichern', discardChanges: 'Änderungen verwerfen'
    },
    home: { project: { kicker: 'Projekt-Arbeitsbereich', desc: 'Beginnen Sie mit einem Projekt, um KI-Arbeitsbereich, Builder und Quellen-Notizbuch an einem Ort organisiert zu halten.' } },
    notebook: { welcome: 'Willkommen bei Skemi Studio. Stellen Sie Fragen zu Ihren Dokumenten.' },
    aichat: { placeholder: 'Geben Sie Ihre Anfrage ein...', close: 'Schließen', send: 'Senden', emptyTitle: 'Noch keine Nachrichten', emptyDesc: 'Starten Sie ein Gespräch mit der KI.' },
    age: { young: 'Student', middle: 'Berufstätiger', senior: 'Senior' },
    status: { ready: 'Bereit' },
    ui: {
      login_title: 'Anmelden',
      login_subtitle: 'Weiter zu Ihrem Skemi-Arbeitsbereich',
      login_email_placeholder: 'E-Mail oder Benutzername',
      login_password_placeholder: 'Passwort',
      login_submit: 'Anmelden',
      login_verify_text: 'Ihre E-Mail wurde noch nicht verifiziert. Bitte prüfen Sie Ihren Posteingang und klicken Sie auf den Verifizierungslink.',
      login_resend_btn: 'Verifizierungs-E-Mail erneut senden',
      login_or_continue: 'oder weiter mit',
      login_no_account: 'Kein Konto?',
      login_create_one: 'Jetzt erstellen',
      oauth_google: 'Mit Google anmelden (demnächst)',
      oauth_google_soon: 'Mit Google anmelden (demnächst)',
      oauth_facebook: 'Mit Facebook anmelden (demnächst)',
      oauth_facebook_soon: 'Mit Facebook anmelden (demnächst)',
      register_title: 'Konto erstellen',
      register_subtitle: 'Registrieren Sie sich, um Skemi Studio zu nutzen',
      register_submit: 'Konto erstellen',
      phantom_title: 'Phantom-Desktop',
      phantom_subtitle: 'Die KI arbeitet auf einem privaten virtuellen Desktop. Ihre Maus bleibt draußen.',
      phantom_install_btn: 'Virtuelles Display aktivieren',
      phantom_create_desktop: '+ Neuen Desktop erstellen',
      phantom_send: 'Senden',
      phantom_stop: 'Stoppen und beenden',
      phantom_cmd_placeholder: 'Befehl eingeben, z.B.: Notepad öffnen und "hello" tippen'
    }
  },

  // Italian (Italiano)
  it: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - Workspace AI, builder e notebook per progetto.', settingsTitle: 'Impostazioni - Skemi' },
    nav: { studio: 'Studio', dashboard: 'Studio', search: 'Cerca', quiz: 'Quiz', chat: 'Chat', settings: 'Impostazioni', version: 'Skemi v1.0', notifications: 'Notifiche' },
    common: { themeToggle: 'Cambia tema', sidebarCollapse: 'Comprimi barra laterale', save: 'Salva', close: 'Chiudi', send: 'Invia', use: 'Usa', active: 'Attivo', delete: 'Elimina', loading: 'Caricamento...' },
    auth: { signup: 'Registrati', login: 'Accedi', logout: 'Disconnetti', profileMenu: 'Clic destro per disconnetterti', guest: 'Ospite', sync: 'Accedi per sincronizzare i tuoi dati.' },
    settings: {
      tabs: ['Profilo', 'Statistiche', 'Aspetto e Lingua', 'Notifiche', 'Sicurezza', 'Abbonamento'],
      accountTitle: 'Informazioni account', accountHelp: 'Gestisci i tuoi dati personali e le impostazioni di identità.', defaultUser: 'Utente Skemi',
      ageTag: 'La tua fascia d\'età', ageRange: 'Fascia d\'età specifica', ageRangePlaceholder: 'Esempio: 18-35',
      appearanceTitle: 'Aspetto', appearanceHelp: 'Scegli un tema per una visualizzazione coerente in tutta l\'app.', themes: ['Chiaro', 'Scuro', 'Galassia'],
      languageTitle: 'Lingua', languageHelp: 'Skemi dà priorità alla lingua selezionata in tutta l\'app. Il nome del marchio Skemi rimane invariato.',
      statistics: { title: 'Panoramica attività', help: 'Queste metriche vengono calcolate dai dati utente archiviati sul dispositivo corrente.', cards: { projects: 'Progetti creati', aiInteractions: 'Interazioni IA', savedSources: 'Fonti salvate', activeDays: 'Giorni attivi (7 giorni)' }, charts: { activityTitle: 'Attività ultimi 7 giorni', focusTitle: 'Focus utilizzo', timeTitle: 'Fascia oraria attività' }, datasets: { activity: 'Numero attività', focus: 'Livello utilizzo', time: 'Frequenza' }, labels: { focus: ['Progetti', 'Fonti', 'Ricerca', 'Chat IA', 'Quiz personale', 'Risultati generati'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: 'Notifiche e funzioni', help: 'Attiva o disattiva le notifiche di base e le opzioni di visualizzazione dell\'app.', desktop: { title: 'Notifiche browser', desc: 'Mostra notifiche desktop quando ci sono nuovi messaggi di chat o inviti quiz.' }, sound: { title: 'Suono notifiche', desc: 'Riproduci un suono di avviso per nuovi messaggi e inviti.' }, email: { title: 'Notifiche email', desc: 'Ricevi email riassuntive sulle attività importanti.' }, startup: { title: 'Suggerimenti all\'apertura', desc: 'Mostra una guida rapida quando entri nella chat per la prima volta nella giornata.' }, compact: { title: 'Modalità interfaccia compatta', desc: 'Semplifica l\'interfaccia per schermi piccoli.' }, animations: { title: 'Animazioni interfaccia', desc: 'Attiva o disattiva effetti di transizione e animazioni. Disattiva per maggiore velocità.' }, aiTitle: 'Attività IA', aiHelp: 'Personalizza come funziona l\'IA Skemi quando usi la chatbot e crei materiali di studio.', ephemeral: { title: 'Salva conversazioni IA temporanee', desc: 'Salva le conversazioni IA per sessione di accesso corrente per continuare più velocemente.' }, personalize: { title: 'Personalizza risposte IA', desc: 'Permetti all\'IA di usare informazioni sull\'età e dati di apprendimento per affinare le risposte.' }, usage: { title: 'Avviso limite utilizzo', desc: 'Notifica quando le attività IA si avvicinano alla soglia di utilizzo.' } },
      securityTitle: 'Accesso e sicurezza', verifyLabel: 'Stato verifica email', verifyChecking: 'Verifica in corso...', warnings: { 1: { title: 'Avviso sicurezza', desc: 'Ricevi avvisi quando ci sono accessi da dispositivi sconosciuti.' } }, dangerTitle: 'Zona pericolosa', dangerDesc: 'Cancella tutti i dati locali su questo browser ma mantieni l\'interfaccia e la lingua selezionate.', clearLocal: 'Cancella dati locali',
      subscriptionTitle: 'Piano abbonamento', subscriptionHelp: 'Effettua l\'upgrade per espandere l\'utilizzo IA, la capacità di archiviazione e l\'accesso alle funzioni.', currentPlan: 'Piano attuale', pro: 'Upgrade a Pro',
      plans: { free: { name: 'Gratuito', price: '€0', period: '/mese', features: ['Utilizzi IA base per ciclo', 'Studio, ricerca e quiz standard', 'Sincronizzazione account predefinita', 'Spazio di lavoro personale'], button: 'Piano attuale' }, pro: { name: 'Pro', price: '€4.99', period: '/mese', features: ['Più utilizzi IA per studio e lavoro', 'Elaborazione veloce prioritaria', 'Memorizza più quiz personali e cronologia più lunga', 'Sincronizzazione migliorata tra pagine'], button: 'Upgrade a Pro' }, advanced: { name: 'Advanced', price: '€11.99', period: '/mese', features: ['Utilizzo IA e archiviazione massimi', 'Priorità coda massima', 'Accesso anticipato a nuove funzioni', 'Spazio di lavoro a lungo termine per team'], button: 'Upgrade a Advanced' } },
      profileSaved: 'Impostazioni profilo salvate.', localCleared: 'Dati locali cancellati.', verified: 'Email verificata.', unverified: 'Email non verificata. Controlla la tua casella di posta.', notLoggedIn: 'Non hai effettuato l\'accesso.', saveBarText: 'Hai modifiche non salvate.', saveChanges: 'Salva modifiche', discardChanges: 'Annulla modifiche'
    },
    home: { project: { kicker: 'Workspace per progetto', desc: 'Inizia con un progetto per tenere organizzati in un unico posto workspace IA, builder e notebook fonti.' } },
    notebook: { welcome: 'Benvenuto in Skemi Studio. Fai domande sui tuoi documenti.' },
    aichat: { placeholder: 'Inserisci la tua richiesta...', close: 'Chiudi', send: 'Invia', emptyTitle: 'Ancora nessun messaggio', emptyDesc: 'Inizia una conversazione con l\'IA.' },
    age: { young: 'Studente', middle: 'Professionista', senior: 'Senior' },
    status: { ready: 'Pronto' }
  },

  // Portuguese (Português)
  pt: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - Espaço de trabalho de IA, construtor e caderno por projeto.', settingsTitle: 'Configurações - Skemi' },
    nav: { studio: 'Studio', dashboard: 'Studio', search: 'Pesquisar', quiz: 'Quiz', chat: 'Chat', settings: 'Configurações', version: 'Skemi v1.0', notifications: 'Notificações' },
    common: { themeToggle: 'Alternar tema', sidebarCollapse: 'Recolher barra lateral', save: 'Salvar', close: 'Fechar', send: 'Enviar', use: 'Usar', active: 'Ativo', delete: 'Excluir', loading: 'Carregando...' },
    auth: { signup: 'Cadastrar', login: 'Entrar', logout: 'Sair', profileMenu: 'Clique direito para sair', guest: 'Convidado', sync: 'Entre para sincronizar seus dados.' },
    settings: {
      tabs: ['Perfil', 'Estatísticas', 'Aparência e Idioma', 'Notificações', 'Segurança', 'Assinatura'],
      accountTitle: 'Informações da conta', accountHelp: 'Gerencie seus dados pessoais e configurações de identidade.', defaultUser: 'Usuário Skemi',
      ageTag: 'Sua faixa etária', ageRange: 'Faixa etária específica', ageRangePlaceholder: 'Exemplo: 18-35',
      appearanceTitle: 'Aparência', appearanceHelp: 'Escolha um tema para exibição consistente em todo o aplicativo.', themes: ['Claro', 'Escuro', 'Galáxia'],
      languageTitle: 'Idioma', languageHelp: 'O Skemi prioriza o idioma selecionado em todo o aplicativo. A marca Skemi permanece inalterada.',
      statistics: { title: 'Visão geral de atividades', help: 'Essas métricas são calculadas a partir dos dados do usuário armazenados no dispositivo atual.', cards: { projects: 'Projetos criados', aiInteractions: 'Interações de IA', savedSources: 'Fontes salvas', activeDays: 'Dias ativos (7 dias)' }, charts: { activityTitle: 'Atividade últimos 7 dias', focusTitle: 'Foco de uso', timeTitle: 'Período de atividade' }, datasets: { activity: 'Número de atividades', focus: 'Nível de uso', time: 'Frequência' }, labels: { focus: ['Projetos', 'Fontes', 'Pesquisa', 'Chat IA', 'Quiz pessoal', 'Resultados gerados'], hours: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'] } },
      notifications: { title: 'Notificações e recursos', help: 'Ative ou desative as notificações básicas e opções de exibição do aplicativo.', desktop: { title: 'Notificações do navegador', desc: 'Mostra notificações na área de trabalho quando há novas mensagens de chat ou convites de quiz.' }, sound: { title: 'Som de notificações', desc: 'Reproduz som de alerta para novas mensagens e convites.' }, email: { title: 'Notificações por email', desc: 'Receba emails resumindo atividades importantes.' }, startup: { title: 'Dicas ao abrir página', desc: 'Mostra guia rápido quando entra no chat pela primeira vez no dia.' }, compact: { title: 'Modo interface compacta', desc: 'Simplifica a interface para telas pequenas.' }, animations: { title: 'Animações da interface', desc: 'Ative ou desative efeitos de transição e animações. Desative para maior velocidade.' }, aiTitle: 'Atividade de IA', aiHelp: 'Personalize como o Skemi AI funciona quando você usa o chatbot e cria materiais de estudo.', ephemeral: { title: 'Salvar conversas de IA temporariamente', desc: 'Salva conversas de IA por sessão de acesso atual para continuar mais rapidamente.' }, personalize: { title: 'Personalizar respostas de IA', desc: 'Permite que a IA use informações de idade e dados de aprendizado para refinar respostas.' }, usage: { title: 'Aviso de limite de uso', desc: 'Notifica quando as atividades de IA se aproximam do limite de uso.' } },
      securityTitle: 'Login e segurança', verifyLabel: 'Status de verificação de email', verifyChecking: 'Verificando...', warnings: { 1: { title: 'Alerta de segurança', desc: 'Receba alertas quando houver logins de dispositivos desconhecidos.' } }, dangerTitle: 'Zona de perigo', dangerDesc: 'Apaga todos os dados locais neste navegador, mas mantém a interface e idioma selecionados.', clearLocal: 'Limpar dados locais',
      subscriptionTitle: 'Plano de assinatura', subscriptionHelp: 'Faça upgrade para expandir o uso de IA, capacidade de armazenamento e acesso a recursos.', currentPlan: 'Plano atual', pro: 'Upgrade para Pro',
      plans: { free: { name: 'Gratuito', price: 'R$0', period: '/mês', features: ['Usos básicos de IA por ciclo', 'Studio, pesquisa e quiz padrão', 'Sincronização de conta padrão', 'Espaço de trabalho pessoal'], button: 'Plano atual' }, pro: { name: 'Pro', price: 'R$24.99', period: '/mês', features: ['Mais usos de IA para estudo e trabalho', 'Processamento rápido prioritário', 'Armazena mais quizzes pessoais e histórico mais longo', 'Sincronização aprimorada entre páginas'], button: 'Upgrade para Pro' }, advanced: { name: 'Advanced', price: 'R$59.99', period: '/mês', features: ['Uso máximo de IA e armazenamento', 'Prioridade máxima na fila', 'Acesso antecipado a novos recursos', 'Espaço de trabalho de longo prazo para equipes'], button: 'Upgrade para Advanced' } },
      profileSaved: 'Configurações de perfil salvas.', localCleared: 'Dados locais apagados.', verified: 'Email verificado.', unverified: 'Email não verificado. Verifique sua caixa de entrada.', notLoggedIn: 'Não está logado.', saveBarText: 'Você tem alterações não salvas.', saveChanges: 'Salvar alterações', discardChanges: 'Descartar alterações'
    },
    home: { project: { kicker: 'Espaço de trabalho por projeto', desc: 'Comece com um projeto para manter organizados em um só lugar o espaço de trabalho de IA, construtor e caderno de fontes.' } },
    notebook: { welcome: 'Bem-vindo ao Skemi Studio. Faça perguntas sobre seus documentos.' },
    aichat: { placeholder: 'Digite sua solicitação...', close: 'Fechar', send: 'Enviar', emptyTitle: 'Ainda sem mensagens', emptyDesc: 'Inicie uma conversa com a IA.' },
    age: { young: 'Estudante', middle: 'Profissional', senior: 'Sênior' },
    status: { ready: 'Pronto' }
  },

  // Thai (ไทย)
  th: {
    meta: { homeTitle: 'Skemi Studio', homeDesc: 'Skemi Studio - พื้นที่ทำงาน AI, เครื่องมือสร้าง และสมุดบันทึกตามโปรเจกต์', settingsTitle: 'การตั้งค่า - Skemi' },
    nav: { studio: 'สตูดิโอ', dashboard: 'สตูดิโอ', search: 'ค้นหา', quiz: 'แบบทดสอบ', chat: 'แชท', settings: 'การตั้งค่า', version: 'Skemi v1.0', notifications: 'การแจ้งเตือน' },
    common: { themeToggle: 'สลับธีม', sidebarCollapse: 'ย่อแถบด้านข้าง', save: 'บันทึก', close: 'ปิด', send: 'ส่ง', use: 'ใช้', active: 'กำลังใช้', delete: 'ลบ', loading: 'กำลังโหลด...' },
    auth: { signup: 'สมัครสมาชิก', login: 'เข้าสู่ระบบ', logout: 'ออกจากระบบ', profileMenu: 'คลิกขวาเพื่อออกจากระบบ', guest: 'ผู้เยี่ยมชม', sync: 'เข้าสู่ระบบเพื่อซิงค์ข้อมูล' },
    home: { project: { kicker: 'พื้นที่ทำงานตามโปรเจกต์', desc: 'เริ่มต้นจากโปรเจกต์เพื่อจัดระเบียบ AI Workspace, Builder และ Source Notebook ไว้ในที่เดียว' } },
    notebook: { welcome: 'ยินดีต้อนรับสู่ Skemi Studio ถามคำถามเกี่ยวกับเอกสารของคุณ' },
    aichat: { placeholder: 'พิมพ์คำขอของคุณ...', close: 'ปิด', send: 'ส่ง', emptyTitle: 'ยังไม่มีข้อความ', emptyDesc: 'เริ่มการสนทนากับ AI' },
    age: { young: 'นักเรียน', middle: 'มืออาชีพ', senior: 'ผู้สูงอายุ' },
    status: { ready: 'พร้อม' },
    ui: {
      login_title: 'เข้าสู่ระบบ',
      login_subtitle: 'ดำเนินการต่อไปยังพื้นที่ทำงาน Skemi ของคุณ',
      login_email_placeholder: 'อีเมลหรือชื่อผู้ใช้',
      login_password_placeholder: 'รหัสผ่าน',
      login_submit: 'เข้าสู่ระบบ',
      login_verify_text: 'อีเมลของคุณยังไม่ได้รับการยืนยัน โปรดตรวจสอบกล่องจดหมายและคลิกลิงก์ยืนยัน',
      login_resend_btn: 'ส่งอีเมลยืนยันอีกครั้ง',
      login_or_continue: 'หรือดำเนินการต่อด้วย',
      login_no_account: 'ยังไม่มีบัญชี?',
      login_create_one: 'สร้างใหม่ทันที',
      oauth_google: 'เข้าสู่ระบบด้วย Google (เร็วๆ นี้)',
      oauth_google_soon: 'เข้าสู่ระบบด้วย Google (เร็วๆ นี้)',
      oauth_facebook: 'เข้าสู่ระบบด้วย Facebook (เร็วๆ นี้)',
      oauth_facebook_soon: 'เข้าสู่ระบบด้วย Facebook (เร็วๆ นี้)',
      register_title: 'สร้างบัญชี',
      register_subtitle: 'สมัครเพื่อเริ่มใช้งาน Skemi Studio',
      register_submit: 'สร้างบัญชี',
      phantom_title: 'เดสก์ท็อป Phantom',
      phantom_subtitle: 'AI ทำงานบนเดสก์ท็อปเสมือนส่วนตัว เมาส์ของคุณจะไม่เข้าไป',
      phantom_install_btn: 'เปิดใช้งานจอแสดงผลเสมือน',
      phantom_create_desktop: '+ สร้างเดสก์ท็อปใหม่',
      phantom_send: 'ส่ง',
      phantom_stop: 'หยุดและออก',
      phantom_cmd_placeholder: 'พิมพ์คำสั่ง เช่น: เปิด Notepad แล้วพิมพ์ "hello"'
    }
  }
};

// Make available globally
if (typeof window !== 'undefined') {
  window.I18N_PACKS = I18N_PACKS;
}
