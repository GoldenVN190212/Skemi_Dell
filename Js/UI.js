const SkemiUI = {
    showToast(msg, type='success', duration=3000) {
        const t = document.createElement('div');
        t.className = `toast toast-${type}`;
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), duration);
    },

    showLoading(el, text='Đang tải...') {
        if (!el) return;
        el._original = el.innerHTML;
        el.innerHTML = `<span class="spinner"></span> ${text}`;
        el.disabled = true;
    },

    hideLoading(el) {
        if (!el || !el._original) return;
        el.innerHTML = el._original;
        el.disabled = false;
    },

    showError(container, msg) {
        if (!container) return;
        container.innerHTML = `
            <div class="card" style="border-color:var(--red);text-align:center;padding:24px">
                <div style="font-size:24px;margin-bottom:8px">⚠️</div>
                <div style="color:var(--red);font-weight:500">${msg}</div>
            </div>`;
    }
};
window.SkemiUI = SkemiUI;