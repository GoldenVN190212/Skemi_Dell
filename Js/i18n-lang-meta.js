/**
 * i18n-lang-meta.js — Native names + flag emoji + RTL set for every language
 * code Skemi supports. Loaded BEFORE LanguageManager.js so the Settings
 * dropdown can render properly.
 *
 * Keep keys aligned with LANGUAGE_CODES in LanguageManager.js. Falls back to
 * UPPERCASE code if a code is missing.
 */
(function () {
    const LANGUAGE_NAMES_NATIVE = {
        // Skemi base
        vi: { native: 'Tiếng Việt', flag: '🇻🇳' },
        en: { native: 'English', flag: '🇬🇧' },
        // East Asian
        zh: { native: '中文', flag: '🇨🇳' },
        'zh-CN': { native: '简体中文', flag: '🇨🇳' },
        'zh-TW': { native: '繁體中文', flag: '🇹🇼' },
        ja: { native: '日本語', flag: '🇯🇵' },
        ko: { native: '한국어', flag: '🇰🇷' },
        // European
        fr: { native: 'Français', flag: '🇫🇷' },
        es: { native: 'Español', flag: '🇪🇸' },
        de: { native: 'Deutsch', flag: '🇩🇪' },
        it: { native: 'Italiano', flag: '🇮🇹' },
        pt: { native: 'Português', flag: '🇵🇹' },
        nl: { native: 'Nederlands', flag: '🇳🇱' },
        pl: { native: 'Polski', flag: '🇵🇱' },
        ru: { native: 'Русский', flag: '🇷🇺' },
        uk: { native: 'Українська', flag: '🇺🇦' },
        cs: { native: 'Čeština', flag: '🇨🇿' },
        sk: { native: 'Slovenčina', flag: '🇸🇰' },
        hu: { native: 'Magyar', flag: '🇭🇺' },
        ro: { native: 'Română', flag: '🇷🇴' },
        bg: { native: 'Български', flag: '🇧🇬' },
        sv: { native: 'Svenska', flag: '🇸🇪' },
        no: { native: 'Norsk', flag: '🇳🇴' },
        da: { native: 'Dansk', flag: '🇩🇰' },
        fi: { native: 'Suomi', flag: '🇫🇮' },
        el: { native: 'Ελληνικά', flag: '🇬🇷' },
        is: { native: 'Íslenska', flag: '🇮🇸' },
        ga: { native: 'Gaeilge', flag: '🇮🇪' },
        cy: { native: 'Cymraeg', flag: '🏴󠁧󠁢󠁷󠁬󠁳󠁿' },
        mt: { native: 'Malti', flag: '🇲🇹' },
        sq: { native: 'Shqip', flag: '🇦🇱' },
        mk: { native: 'Македонски', flag: '🇲🇰' },
        bs: { native: 'Bosanski', flag: '🇧🇦' },
        hr: { native: 'Hrvatski', flag: '🇭🇷' },
        sr: { native: 'Српски', flag: '🇷🇸' },
        sl: { native: 'Slovenščina', flag: '🇸🇮' },
        et: { native: 'Eesti', flag: '🇪🇪' },
        lv: { native: 'Latviešu', flag: '🇱🇻' },
        lt: { native: 'Lietuvių', flag: '🇱🇹' },
        be: { native: 'Беларуская', flag: '🇧🇾' },
        ca: { native: 'Català', flag: '🏴' },
        eu: { native: 'Euskara', flag: '🏴' },
        gl: { native: 'Galego', flag: '🏴' },
        // Middle East / RTL
        ar: { native: 'العربية', flag: '🇸🇦', rtl: true },
        he: { native: 'עברית', flag: '🇮🇱', rtl: true },
        fa: { native: 'فارسی', flag: '🇮🇷', rtl: true },
        ur: { native: 'اردو', flag: '🇵🇰', rtl: true },
        ps: { native: 'پښتو', flag: '🇦🇫', rtl: true },
        sd: { native: 'سنڌي', flag: '🇵🇰', rtl: true },
        ckb: { native: 'کوردی', flag: '🏴', rtl: true },
        ug: { native: 'ئۇيغۇرچە', flag: '🇨🇳', rtl: true },
        tr: { native: 'Türkçe', flag: '🇹🇷' },
        // South Asian
        hi: { native: 'हिन्दी', flag: '🇮🇳' },
        bn: { native: 'বাংলা', flag: '🇧🇩' },
        ta: { native: 'தமிழ்', flag: '🇮🇳' },
        te: { native: 'తెలుగు', flag: '🇮🇳' },
        ml: { native: 'മലയാളം', flag: '🇮🇳' },
        kn: { native: 'ಕನ್ನಡ', flag: '🇮🇳' },
        gu: { native: 'ગુજરાતી', flag: '🇮🇳' },
        pa: { native: 'ਪੰਜਾਬੀ', flag: '🇮🇳' },
        mr: { native: 'मराठी', flag: '🇮🇳' },
        ne: { native: 'नेपाली', flag: '🇳🇵' },
        si: { native: 'සිංහල', flag: '🇱🇰' },
        // Southeast Asian
        th: { native: 'ไทย', flag: '🇹🇭' },
        id: { native: 'Bahasa Indonesia', flag: '🇮🇩' },
        ms: { native: 'Bahasa Melayu', flag: '🇲🇾' },
        fil: { native: 'Filipino', flag: '🇵🇭' },
        tl: { native: 'Tagalog', flag: '🇵🇭' },
        my: { native: 'မြန်မာ', flag: '🇲🇲' },
        km: { native: 'ភាសាខ្មែរ', flag: '🇰🇭' },
        lo: { native: 'ລາວ', flag: '🇱🇦' },
        // Central Asian
        mn: { native: 'Монгол', flag: '🇲🇳' },
        ka: { native: 'ქართული', flag: '🇬🇪' },
        hy: { native: 'Հայերեն', flag: '🇦🇲' },
        az: { native: 'Azərbaycan', flag: '🇦🇿' },
        kk: { native: 'Қазақ тілі', flag: '🇰🇿' },
        uz: { native: 'Oʻzbekcha', flag: '🇺🇿' },
        ky: { native: 'Кыргызча', flag: '🇰🇬' },
        tg: { native: 'Тоҷикӣ', flag: '🇹🇯' },
        tk: { native: 'Türkmençe', flag: '🇹🇲' },
        // African
        af: { native: 'Afrikaans', flag: '🇿🇦' },
        sw: { native: 'Kiswahili', flag: '🇰🇪' },
        am: { native: 'አማርኛ', flag: '🇪🇹' },
        zu: { native: 'isiZulu', flag: '🇿🇦' },
        xh: { native: 'isiXhosa', flag: '🇿🇦' },
        st: { native: 'Sesotho', flag: '🇱🇸' },
        tn: { native: 'Setswana', flag: '🇧🇼' },
        sn: { native: 'chiShona', flag: '🇿🇼' },
        ny: { native: 'Chichewa', flag: '🇲🇼' },
        mg: { native: 'Malagasy', flag: '🇲🇬' },
        rw: { native: 'Kinyarwanda', flag: '🇷🇼' },
        so: { native: 'Soomaali', flag: '🇸🇴' },
        ti: { native: 'ትግርኛ', flag: '🇪🇷' },
        om: { native: 'Afaan Oromoo', flag: '🇪🇹' },
        ha: { native: 'Hausa', flag: '🇳🇬' },
        yo: { native: 'Yorùbá', flag: '🇳🇬' },
        ig: { native: 'Igbo', flag: '🇳🇬' },
        ee: { native: 'Eʋegbe', flag: '🇬🇭' },
        ak: { native: 'Akan', flag: '🇬🇭' },
        bm: { native: 'Bamanankan', flag: '🇲🇱' },
        wo: { native: 'Wolof', flag: '🇸🇳' },
        ff: { native: 'Fulfulde', flag: '🇸🇳' },
        ln: { native: 'Lingála', flag: '🇨🇩' },
        ts: { native: 'Xitsonga', flag: '🇿🇦' },
        ve: { native: 'Tshivenda', flag: '🇿🇦' },
        nr: { native: 'isiNdebele', flag: '🇿🇦' },
    };

    // Languages that need RTL layout. Documents are flipped via dir="rtl"
    // on <html> when the user picks one of these.
    const RTL_LANGUAGES = new Set(
        Object.entries(LANGUAGE_NAMES_NATIVE)
            .filter(([_, meta]) => meta && meta.rtl)
            .map(([code]) => code)
    );

    if (typeof window !== 'undefined') {
        window.LANGUAGE_NAMES_NATIVE = LANGUAGE_NAMES_NATIVE;
        window.RTL_LANGUAGES = RTL_LANGUAGES;
    }
})();
