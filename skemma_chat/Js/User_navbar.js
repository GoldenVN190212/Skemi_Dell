import { auth } from "./Firebase_config.js";
import { onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";
import {
  ensureLocalPreferencesDefaults,
  resetGuestPreferences,
  loadRemoteUserProfile,
  getCurrentLanguage,
  getPack,
  getSkemiHomeUrl
} from "./SharedSettings.js?v=20260624c";

class NavbarManager {
  constructor() {
    this.currentUser = null;
    this.currentProfile = null;
    this.container = document.getElementById('userNavContainer');
    this.bindAuth();
  }

  get pack() {
    return getPack(getCurrentLanguage());
  }

  bindAuth() {
    onAuthStateChanged(auth, async (user) => {
      this.currentUser = user;
      if (!this.container) return;
      if (!user) {
        this.currentProfile = resetGuestPreferences();
        this.renderGuest();
        return;
      }
      this.currentProfile = await loadRemoteUserProfile(user);
      this.renderUser();
    });

    window.addEventListener('languageChanged', () => {
      if (!this.container) return;
      if (!this.currentUser) {
        this.renderGuest();
        return;
      }
      this.renderUser();
    });
  }

  renderGuest() {
    this.container.innerHTML = `
      <a class="user-chip guest-chip" href="./Login.html">${this.pack.common.notLoggedIn}</a>
    `;
  }

  renderUser() {
    const profile = this.currentProfile || {};
    const name = profile.username || this.currentUser?.displayName || this.currentUser?.email?.split('@')[0] || 'User';
    const email = profile.email || this.currentUser?.email || '';
    const initial = name.charAt(0).toUpperCase();
    const skemiUrl = getSkemiHomeUrl();

    this.container.innerHTML = `
      <div class="user-shell">
        <button type="button" class="user-chip" id="userChip">
          <span class="user-chip-avatar">${initial}</span>
          <span class="user-chip-name">${name}</span>
        </button>
        <div class="user-menu" id="userMenu">
          <div class="user-menu-head">
            <div class="user-menu-title">${name}</div>
            <div class="user-menu-subtitle">${email}</div>
          </div>
          <a class="user-menu-item" href="./Settings.html"><i class="fas fa-gear"></i><span>${this.pack.common.settings}</span></a>
          <a class="user-menu-item" href="${skemiUrl}" target="_blank" rel="noreferrer"><i class="fas fa-arrow-up-right-from-square"></i><span>${this.pack.common.openSkemi}</span></a>
          <button class="user-menu-item danger" type="button" id="logoutMenuBtn"><i class="fas fa-right-from-bracket"></i><span>${this.pack.common.logout}</span></button>
        </div>
      </div>
    `;

    const chip = document.getElementById('userChip');
    const menu = document.getElementById('userMenu');
    const logoutBtn = document.getElementById('logoutMenuBtn');

    chip?.addEventListener('click', (event) => {
      event.stopPropagation();
      menu?.classList.toggle('active');
    });

    logoutBtn?.addEventListener('click', async () => {
      await signOut(auth);
      resetGuestPreferences();
      window.location.href = './Login.html';
    });

    document.addEventListener('click', (event) => {
      if (!menu || !chip) return;
      if (!menu.contains(event.target) && !chip.contains(event.target)) {
        menu.classList.remove('active');
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  ensureLocalPreferencesDefaults();
  new NavbarManager();
});
