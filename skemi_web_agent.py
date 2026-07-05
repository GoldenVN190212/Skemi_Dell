"""
skemi_web_agent.py — human-like WEB control via Chrome DevTools Protocol (Playwright).

UI Automation can't see modern web-app content (YouTube video links etc. are not in
the UIA tree — verified). So web tasks are driven through CDP: launch the AI's own
Chrome with --remote-debugging-port (off-screen, own profile, no focus steal), then
connect Playwright over CDP and act on the DOM directly — click any link/button by
its visible text, type into fields, navigate, scroll. This NEVER moves the user's
mouse or steals focus (events are dispatched to the page, not the OS).

Playwright's sync API is thread-bound, so the whole web-agent loop runs inside ONE
thread (the FastAPI to_thread worker), connecting/closing within that thread.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import win32gui
    import win32process
    import win32con
    _WIN = True
except Exception:
    _WIN = False

OFFSCREEN = (-32000, -32000)
# On-screen rectangle the hidden browser RESTORES to, so a normal taskbar click
# (or the "show window" button) brings it back where the user can see it.
RESTORE_RECT = (200, 120, 200 + 1280, 120 + 820)


def _safe_int(v, default: int = -1) -> int:
    """Parse an LLM-supplied element ref to int without crashing. The model
    sometimes returns a string label or null for 'ref'; a raw int() then raised
    and (since run_web_task's loop has only a finally, no except) killed the whole
    web task. -1 → click/fill report 'not found' and the agent re-plans."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _hide_window_minimized(hwnd: int) -> None:
    """Hide the AI browser by MINIMISING it (not parking it off-screen) and set its
    restore position ON-SCREEN. This way it's invisible by default BUT a normal
    click on its taskbar icon restores it like any window. CDP page screenshots
    keep working while minimised, so the live stream is unaffected."""
    if not (_WIN and hwnd):
        return
    with _supp():
        win32gui.SetWindowPlacement(
            hwnd, (0, win32con.SW_SHOWMINIMIZED, (-1, -1), (-1, -1), RESTORE_RECT))


def _sqlite_snapshot(src: str, dst: str) -> bool:
    """Copy a LIVE Chrome SQLite DB (Cookies/Login Data/Web Data) even while the
    user's Chrome holds it open. shutil.copy2 fails on the exclusive/WAL lock; the
    SQLite online-backup API with immutable=1 reads a consistent snapshot past the
    lock — this is what lets the AI browser inherit the user's REAL logins (FB,
    Google, …) while their own Chrome is running."""
    import sqlite3
    try:
        s = sqlite3.connect(f"file:{src}?mode=ro&immutable=1", uri=True, timeout=3)
        try:
            d = sqlite3.connect(dst)
            try:
                s.backup(d)
            finally:
                d.close()
        finally:
            s.close()
        return True
    except Exception:
        return False


def _seed_ai_profile(user_data: str, ai_dir: str) -> int:
    """Copy the USER's login state (cookies / logins) into the AI's dedicated
    profile so the AI browser is signed into the SAME accounts (YouTube/Google/FB)
    even when the user's own Chrome is open and its real profile dir is locked.
    Runs as the same Windows user, so the DPAPI-wrapped cookie key in Local State
    decrypts fine. Best-effort: locked files are snapshotted via SQLite backup."""
    import shutil
    if not (user_data and os.path.isdir(user_data)):
        return 0
    src_def = os.path.join(user_data, "Default")
    dst_def = os.path.join(ai_dir, "Default")
    copied = 0
    try:
        os.makedirs(os.path.join(dst_def, "Network"), exist_ok=True)
    except Exception:
        return 0
    # Always refresh Local State (holds the DPAPI-wrapped cookie key) — plain file.
    for s, d in [
        (os.path.join(user_data, "Local State"), os.path.join(ai_dir, "Local State")),
        (os.path.join(src_def, "Preferences"), os.path.join(dst_def, "Preferences")),
    ]:
        if os.path.exists(s):
            with _supp():
                shutil.copy2(s, d)
    # SQLite DBs (Login Data / Web Data) — snapshot past Chrome's lock.
    for s, d in [
        (os.path.join(src_def, "Login Data"), os.path.join(dst_def, "Login Data")),
        (os.path.join(src_def, "Web Data"), os.path.join(dst_def, "Web Data")),
    ]:
        if os.path.exists(s) and not _sqlite_snapshot(s, d):
            with _supp():
                shutil.copy2(s, d)
    # The COOKIES DB carries the real login (FB/Google/YouTube). It's almost always
    # LOCKED while the user's Chrome runs → plain copy fails, so snapshot it via the
    # SQLite backup API (immutable read past the lock). Re-seed EVERY launch so the
    # login stays fresh. Fall back to copy2, then to a prior seed.
    for s, d in [
        (os.path.join(src_def, "Network", "Cookies"), os.path.join(dst_def, "Network", "Cookies")),
        (os.path.join(src_def, "Cookies"), os.path.join(dst_def, "Cookies")),
    ]:
        if os.path.exists(s):
            if _sqlite_snapshot(s, d):
                copied += 1
            else:
                with _supp():
                    shutil.copy2(s, d); copied += 1
        elif os.path.exists(d):
            copied += 1   # already seeded from a prior run → still signed in
    return copied


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _chrome_path() -> str:
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")):
        if os.path.exists(p):
            return p
    # Edge fallback (Chromium-based, same CDP)
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return ""


def _is_edge(exe: str) -> bool:
    return "msedge" in (exe or "").lower()


def _user_browser_data_dir(exe: str) -> str:
    """Path to the USER's real browser profile dir (Chrome/Edge), so the AI's
    browser is signed into their accounts (YouTube/Google) instead of a blank
    guest profile."""
    if _is_edge(exe):
        p = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")
    else:
        p = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    return p if os.path.isdir(p) else ""


def _browser_running(exe: str) -> bool:
    """Is the user's Chrome/Edge already running? If so we can't claim its real
    profile with a fresh --remote-debugging-port (the profile dir is locked and
    the new launch just hands off to the existing instance), so we fall back to a
    dedicated profile instead of breaking automation."""
    image = "msedge.exe" if _is_edge(exe) else "chrome.exe"
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                             capture_output=True, text=True, timeout=6)
        return image.lower() in (out.stdout or "").lower()
    except Exception:
        return False


# JS that returns the visible, interactable elements of the page with stable refs.
_OBSERVE_JS = r"""
() => {
  const out = [];
  // Include DROPDOWN/MENU OPTION roles — without these, an open model-picker /
  // combobox shows nothing clickable to the agent, so it just re-clicks the trigger.
  const sel = 'a,button,input,textarea,select,[role=button],[role=link],[role=tab],'
            + '[role=menuitem],[role=menuitemradio],[role=menuitemcheckbox],[role=option],'
            + '[role=switch],[role=combobox],[role=radio],[role=checkbox],summary,label,'
            + '[onclick],ytd-video-renderer,[contenteditable=true]';
  let nodes = Array.from(document.querySelectorAll(sel));
  // When a menu/listbox/dialog is OPEN, also grab its direct clickable-looking
  // children (custom React menus often use plain <div>/<li> with no role/onclick).
  document.querySelectorAll('[role=menu],[role=listbox],[role=dialog],[aria-expanded="true"]+*,[data-state="open"]').forEach((m) => {
    m.querySelectorAll('li,div[tabindex],div[class*="option"],div[class*="item"],div[class*="model"]').forEach((c) => { if (nodes.indexOf(c) === -1) nodes.push(c); });
  });
  let i = 0;
  for (const el of nodes) {
    if (i >= 60) break;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    if (r.bottom < 0 || r.top > (window.innerHeight + 600)) continue;  // near viewport
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    // NEVER read .value of a password (or otherwise sensitive) field — it is the
    // real secret and would be sent to the cloud LLM. Use aria-label/placeholder
    // for those, and a masked marker if the field has content.
    const itype = (el.tagName === 'INPUT' ? (el.getAttribute('type') || 'text').toLowerCase() : '');
    const sensitive = (itype === 'password') ||
                      /pass|otp|cvv|card|secret|pin/i.test((el.getAttribute('name')||'') + (el.getAttribute('autocomplete')||''));
    const safeVal = (sensitive ? '' : (el.value || ''));
    let label = (el.getAttribute('aria-label') || el.getAttribute('title') ||
                 safeVal || el.placeholder || el.innerText || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,80);
    if (!label && sensitive) label = (itype === 'password' ? 'ô mật khẩu' : 'ô nhập bảo mật');
    if (!label && el.querySelector) {
      const t = el.querySelector('#video-title, [title]');
      if (t) label = (t.getAttribute('title') || t.textContent || '').trim().slice(0,80);
    }
    if (!label) continue;
    // Mark actual VIDEO result links with ▶ so the agent clicks a real video (not a
    // filter chip / nav link). A watch link is the reliable "play this" target.
    try {
      const href = (el.getAttribute && (el.getAttribute('href') || '')) || (el.href || '');
      const isVid = el.id === 'video-title' || el.tagName === 'YTD-VIDEO-RENDERER' ||
                    (typeof href === 'string' && href.indexOf('/watch') !== -1) ||
                    (el.querySelector && el.querySelector('a[href*="/watch"]'));
      if (isVid) label = '▶ ' + label;
    } catch (e) {}
    el.setAttribute('data-skemi-ref', String(i));
    out.push({ ref: i, tag: el.tagName.toLowerCase(),
               role: el.getAttribute('role') || '', label: label,
               x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) });
    i++;
  }
  return { url: location.href, title: document.title, count: out.length, elements: out };
}
"""


# JS that finds and clicks any visible "skip ad" / "close ad" control. Runs IN the
# page (no OS mouse/focus), so ads get skipped silently even while the window is
# hidden. Covers YouTube's skip buttons + generic Skip/"Bỏ qua" buttons + overlay
# close buttons. Returns how many it clicked.
_SKIP_ADS_JS = r"""
() => {
  let clicked = 0;
  const click = (b) => { try { if (b && b.offsetParent !== null) { b.click(); clicked++; } } catch (e) {} };
  // YouTube skip + overlay-close (covers old + modern markup)
  ['.ytp-ad-skip-button','.ytp-ad-skip-button-modern','.ytp-skip-ad-button',
   '.ytp-ad-skip-button-container button','.ytp-ad-overlay-close-button',
   '.ytp-ad-overlay-close-container button','.ytp-ad-overlay-close-button button',
   'button.ytp-ad-skip-button-modern','[id^="skip-button"] button','.videoAdUiSkipButton'
  ].forEach((s) => document.querySelectorAll(s).forEach(click));
  // Generic text-based skip buttons (any site / language)
  const texts = ['skip ad','skip ads','skip','bỏ qua quảng cáo','bỏ qua','skip intro'];
  document.querySelectorAll('button,[role="button"],a').forEach((b) => {
    const t = (b.innerText || b.textContent || '').trim().toLowerCase();
    if (!t || t.length > 24) return;
    if (texts.includes(t) || /^skip\b/.test(t) || t.startsWith('bỏ qua')) click(b);
  });
  return clicked;
}
"""


class WebController:
    """Owns one AI Chrome (debug port) + Playwright CDP connection."""

    def __init__(self, off_screen: bool = True, use_user_profile: bool = True):
        self.port = _free_port()
        # STABLE dedicated profile (not per-port) so a one-time seed of the user's
        # login persists across launches → the AI stays signed into their accounts.
        self.profile = os.path.join(tempfile.gettempdir(), "skemi_ai_browser")
        self.proc: Optional[subprocess.Popen] = None
        self.hwnd = 0
        self.off_screen = off_screen
        self.use_user_profile = use_user_profile
        self.profile_mode = "guest"   # "user" | "guest" — which profile we ended up using
        self._pw = None
        self._browser = None
        self._page = None
        self.last_shot: bytes = b""   # last page screenshot (for streaming)
        self.cancelled = False        # Stop button → abort the run_web_task loop
        self._stream_stop: Optional[threading.Event] = None
        self._stream_thread: Optional[threading.Thread] = None

    def launch(self, url: str = "about:blank") -> Dict[str, Any]:
        exe = _chrome_path()
        if not exe:
            return {"success": False, "error": "Chrome/Edge not found"}
        before = self._all_windows()
        # Prefer the USER's real browser profile (so the AI is signed into their
        # YouTube/Google account — "bật như người dùng bật"). We can only claim it
        # with a debug port when the browser isn't already running (otherwise the
        # profile is locked and the launch hands off to the existing instance with
        # no CDP). When it's already running we fall back to a dedicated profile so
        # automation never breaks.
        user_dir = _user_browser_data_dir(exe) if self.use_user_profile else ""
        if user_dir and not _browser_running(exe):
            # Best case: their browser is closed → drive their REAL profile live.
            data_dir = user_dir
            self.profile_mode = "user"
            extra = ["--profile-directory=Default", "--restore-last-session"]
        else:
            # Their browser is open (real profile locked) → use a dedicated profile
            # SEEDED with their cookies so the AI is still signed into their real
            # accounts (YouTube/Google), not a blank guest.
            data_dir = self.profile
            n = _seed_ai_profile(user_dir, data_dir) if user_dir else 0
            self.profile_mode = "user-clone" if n else "guest"
            extra = ["--profile-directory=Default"]
        args = [exe, f"--remote-debugging-port={self.port}",
                f"--user-data-dir={data_dir}", "--new-window",
                "--no-first-run", "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                # keep rendering/audio alive while minimised (so music/video and the
                # live stream don't get throttled when the window is hidden)
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows"] + extra
        if self.off_screen:
            # launch off-screen first (no visible flash); we minimise it below
            args.append(f"--window-position={OFFSCREEN[0]},{OFFSCREEN[1]}")
        args.append("--window-size=1280,820")
        args.append(url or "about:blank")
        self.proc = subprocess.Popen(args)
        # find the chrome window (for window management / taskbar restore)
        end = time.time() + 8
        while time.time() < end and not self.hwnd:
            for h in set(self._all_windows()) - set(before):
                with _supp():
                    if _WIN and win32gui.IsWindow(h) and win32gui.GetWindowText(h):
                        cls = win32gui.GetClassName(h) or ""
                        if "Chrome" in cls or "Chrome" in win32gui.GetWindowText(h) or "Edge" in win32gui.GetWindowText(h):
                            self.hwnd = h
                            break
            time.sleep(0.3)
        # Hide by MINIMISING (with an on-screen restore rect) instead of leaving it
        # parked off-screen — so the user can click its taskbar icon to show it
        # normally. CDP screenshots keep the stream live while minimised.
        if self.off_screen and self.hwnd:
            time.sleep(0.4)
            _hide_window_minimized(self.hwnd)
        return {"success": True, "port": self.port, "hwnd": self.hwnd,
                "profile_mode": self.profile_mode}

    def _all_windows(self) -> List[int]:
        out: List[int] = []
        if not _WIN:
            return out
        def cb(h, _):
            if win32gui.IsWindow(h):
                out.append(h)
            return True
        with _supp():
            win32gui.EnumWindows(cb, None)
        return out

    def connect(self) -> bool:
        """Connect Playwright over CDP (call in the SAME thread you'll act in)."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return False
        end = time.time() + 12
        last = None
        while time.time() < end:
            try:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.connect_over_cdp(f"http://localhost:{self.port}")
                ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                self._page = ctx.pages[0] if ctx.pages else ctx.new_page()
                return True
            except Exception as e:
                last = e
                with _supp():
                    if self._pw:
                        self._pw.stop()
                self._pw = self._browser = self._page = None
                time.sleep(0.6)
        return False

    def shot(self) -> bytes:
        """Screenshot the current page (reliable for web, incl. video) and cache it."""
        try:
            if self._page:
                self.last_shot = self._page.screenshot(type="jpeg", quality=70, timeout=5000)
        except Exception:
            pass
        return self.last_shot

    def start_stream(self, interval: float = 0.45) -> None:
        """Keep `last_shot` LIVE with a dedicated capture thread that owns its OWN
        Playwright/CDP connection (a 2nd client to the same Chrome). This is why the
        stream no longer freezes on a single frame when a task finishes: the action
        loop's connection is thread-bound and dies with its worker, but this thread
        runs continuously, re-screenshotting the front tab every ~0.45s. Two CDP
        clients on one browser is supported."""
        if self._stream_thread and self._stream_thread.is_alive():
            return
        self._stream_stop = threading.Event()

        def _loop() -> None:
            try:
                from playwright.sync_api import sync_playwright
            except Exception:
                return
            pw = browser = None
            try:
                pw = sync_playwright().start()
                for _ in range(24):
                    if self._stream_stop.is_set():
                        return
                    try:
                        browser = pw.chromium.connect_over_cdp(f"http://localhost:{self.port}")
                        break
                    except Exception:
                        time.sleep(0.5)
                if not browser:
                    return
                tick = 0
                while not self._stream_stop.is_set():
                    try:
                        ctx = browser.contexts[0] if browser.contexts else None
                        pg = ctx.pages[-1] if (ctx and ctx.pages) else None
                        if pg:
                            # AUTO-SKIP ADS continuously — even while the window is
                            # hidden and no command is running, so a mid-video ad
                            # never interrupts what the user is listening to.
                            if tick % 3 == 0:
                                with _supp():
                                    pg.evaluate(_SKIP_ADS_JS)
                            self.last_shot = pg.screenshot(type="jpeg", quality=68, timeout=4000)
                    except Exception:
                        pass
                    tick += 1
                    if self._stream_stop:
                        self._stream_stop.wait(interval)
            finally:
                with _supp():
                    if browser:
                        browser.close()
                with _supp():
                    if pw:
                        pw.stop()

        self._stream_thread = threading.Thread(target=_loop, name="skemi-web-stream", daemon=True)
        self._stream_thread.start()

    def stop_stream(self) -> None:
        if self._stream_stop:
            self._stream_stop.set()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=1.5)
        self._stream_thread = None
        self._stream_stop = None

    def skip_ads(self, page=None) -> int:
        """Click any visible skip/close-ad control on the page (in-DOM, no OS
        focus). Safe to call repeatedly; returns how many controls it clicked."""
        pg = page or self._page
        if not pg:
            return 0
        try:
            return int(pg.evaluate(_SKIP_ADS_JS) or 0)
        except Exception:
            return 0

    def observe(self) -> Dict[str, Any]:
        if not self._page:
            return {"url": "", "elements": []}
        try:
            self._page.wait_for_timeout(300)
            return self._page.evaluate(_OBSERVE_JS)
        except Exception as e:
            return {"url": getattr(self._page, "url", ""), "elements": [], "error": str(e)}

    def navigate(self, url: str) -> str:
        try:
            u = (url or "").strip().strip('"\'')
            if not u:
                return "navigate err: empty url"
            # Playwright's goto REQUIRES a scheme. The model often emits a bare domain
            # ("youtube.com") or even a search phrase as the 'url' → normalize:
            #   has scheme         → as-is
            #   bare domain (dot, no space) → prepend https://
            #   anything else (a phrase)    → Google-search it
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://', u):
                if ' ' not in u and '.' in u and not u.startswith('.'):
                    u = 'https://' + u
                else:
                    from urllib.parse import quote_plus
                    u = 'https://www.google.com/search?q=' + quote_plus(u)
            self._page.goto(u, wait_until="domcontentloaded", timeout=20000)
            return f"navigate {u[:50]} ok"
        except Exception as e:
            return f"navigate err {e}"

    def click(self, ref: int) -> str:
        try:
            url0 = self._page.url
            # Prefer the real navigable link inside a card/container (e.g. YouTube's
            # ytd-video-renderer wraps the clickable <a#video-title>). Clicking the
            # container often does nothing; the inner <a href> actually navigates.
            handle = self._page.evaluate_handle(
                """(ref) => {
                    const el = document.querySelector('[data-skemi-ref="'+ref+'"]');
                    if (!el) return null;
                    if (el.tagName === 'A' || el.tagName === 'BUTTON') return el;
                    return el.querySelector('a#video-title, a[href*="/watch"], a[href]') || el;
                }""", ref)
            el = handle.as_element() if handle else None
            if not el:
                el = self._page.query_selector(f'[data-skemi-ref="{ref}"]')
            if not el:
                return f"click[{ref}] not found"
            with _supp():
                el.scroll_into_view_if_needed(timeout=3000)
            # Robust click chain: normal → force (skip the covered/stable wait) → JS
            # .click() (fires the React/onClick handler directly). Dropdown OPTIONS
            # (model picker) are in popups that fail the actionability check, so the
            # plain .click() times out — the force/JS fallbacks handle them.
            ok = False
            try:
                el.click(timeout=2500); ok = True
            except Exception:
                pass
            if not ok:
                try:
                    el.click(force=True, timeout=2000); ok = True
                except Exception:
                    pass
            if not ok:
                with _supp():
                    el.evaluate("e => e.click()"); ok = True
            self._page.wait_for_timeout(900)
            moved = self._page.url != url0
            return f"click[{ref}] ok" + (" (navigated)" if moved else "")
        except Exception as e:
            return f"click[{ref}] err {str(e)[:60]}"

    def fill(self, ref: int, text: str) -> str:
        try:
            el = self._page.query_selector(f'[data-skemi-ref="{ref}"]')
            if not el:
                return f"fill[{ref}] not found"
            el.click(timeout=4000)
            el.fill(text, timeout=4000)
            return f"fill[{ref}] ok"
        except Exception as e:
            # contenteditable / search boxes may need type()
            try:
                self._page.keyboard.type(text)
                return f"type ok"
            except Exception as e2:
                return f"fill err {e2}"

    def press(self, key: str) -> str:
        try:
            k = (key or "").strip()
            _km = {"enter": "Enter", "return": "Enter", "tab": "Tab", "escape": "Escape", "esc": "Escape",
                   "space": "Space", "backspace": "Backspace", "delete": "Delete", "del": "Delete",
                   "down": "ArrowDown", "up": "ArrowUp", "left": "ArrowLeft", "right": "ArrowRight",
                   "arrowdown": "ArrowDown", "arrowup": "ArrowUp",
                   "arrowleft": "ArrowLeft", "arrowright": "ArrowRight",
                   # multi-word keys: .title() would mangle these (PageDown→"Pagedown",
                   # which Playwright rejects) — map them explicitly.
                   "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown",
                   "pgup": "PageUp", "pgdn": "PageDown"}
            pk = _km.get(k.lower().replace(" ", "").replace("_", ""), k if len(k) == 1 else k.title())
            self._page.keyboard.press(pk)
            return f"press {pk}"
        except Exception as e:
            return f"press err {e}"

    def media_control(self, op: str) -> str:
        """Control the CURRENT <video>/<audio> on the page directly (reliable, no
        focus needed, works on any HTML5 media site) — for in-place follow-ups like
        'giảm âm lượng', 'tạm dừng', without navigating or opening a new tab."""
        op = (op or "").lower().strip().replace(" ", "")
        # Accept natural variants the model may emit instead of the canonical op.
        _alias = {
            "volumedown": "voldown", "lower": "voldown", "decrease": "voldown",
            "quieter": "voldown", "turndown": "voldown", "down": "voldown",
            "giảm": "voldown", "giam": "voldown",
            "volumeup": "volup", "raise": "volup", "increase": "volup",
            "louder": "volup", "turnup": "volup", "up": "volup",
            "tăng": "volup", "tang": "volup",
            "silence": "mute", "muteaudio": "mute",
            "stop": "pause", "tạmdừng": "pause", "tamdung": "pause", "dừng": "pause", "dung": "pause",
            "resume": "play", "continue": "play", "unpause": "play",
            "phát": "play", "phat": "play", "tiếptục": "play", "tieptuc": "play",
        }
        op = _alias.get(op, op)
        js = {
            "voldown": "()=>{const v=document.querySelector('video,audio');if(!v)return'no media';v.muted=false;v.volume=Math.max(0,Math.round((v.volume-0.2)*100)/100);return 'âm lượng '+Math.round(v.volume*100)+'%';}",
            "volup":   "()=>{const v=document.querySelector('video,audio');if(!v)return'no media';v.muted=false;v.volume=Math.min(1,Math.round((v.volume+0.2)*100)/100);return 'âm lượng '+Math.round(v.volume*100)+'%';}",
            "mute":    "()=>{const v=document.querySelector('video,audio');if(!v)return'no media';v.muted=true;return 'đã tắt tiếng';}",
            "unmute":  "()=>{const v=document.querySelector('video,audio');if(!v)return'no media';v.muted=false;return 'đã bật tiếng';}",
            "pause":   "()=>{const v=document.querySelector('video,audio');if(!v)return'no media';v.pause();return 'đã tạm dừng';}",
            "play":    "()=>{const v=document.querySelector('video,audio');if(!v)return'no media';v.play();return 'đang phát';}",
        }.get(op)
        if not js:
            return f"media: op không hỗ trợ ({op})"
        try:
            return f"media {op}: " + str(self._page.evaluate(js))
        except Exception as e:
            return f"media err {e}"

    def scroll(self, direction: str = "down") -> str:
        try:
            self._page.mouse.wheel(0, 600 if direction == "down" else -600)
            return f"scroll {direction}"
        except Exception as e:
            return f"scroll err {e}"

    def close_pw(self) -> None:
        with _supp():
            if self._browser:
                self._browser.close()   # detaches CDP, leaves Chrome running
        with _supp():
            if self._pw:
                self._pw.stop()
        self._pw = self._browser = self._page = None

    def kill(self) -> None:
        self.stop_stream()
        self.close_pw()
        with _supp():
            if self.proc:
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/F", "/T"],
                               capture_output=True)

    # ------- the web agent loop -------------------------------------------
    def run_web_task(self, command: str, llm: Callable[[str], str],
                     start_url: str = "", max_rounds: int = 8,
                     context: str = "") -> Dict[str, Any]:
        """Full human-like web loop: observe DOM → LLM picks ONE action → act →
        repeat until done. `llm` is sync str->str. `context` carries what the AI
        did in PREVIOUS commands so it stays aware of the session (e.g. it knows a
        video is already playing and acts in the SAME tab)."""
        if not self.connect():
            return {"success": False, "error": "Could not connect Playwright over CDP",
                    "history": []}
        history: List[str] = []
        if start_url:
            history.append(self.navigate(start_url))
            with _supp():
                self._page.wait_for_timeout(2200)  # let the SPA render results
        last_url = None; stuck = 0; click_counts = {}; just_sent = 0
        self.cancelled = False
        # TOTAL wall-clock budget. A multi-step task with a slow/throttled cloud LLM
        # can otherwise run many minutes — the synchronous /run request (and the
        # user) would hang. Return honestly when the budget is spent instead of
        # blocking indefinitely. ~3 min is generous for ≤8 rounds at normal latency.
        _budget = 180.0
        _t0 = time.time()
        try:
            for rnd in range(max_rounds):
                if self.cancelled:
                    return {"success": True, "rounds": rnd, "history": history,
                            "summary": "⏹ Đã dừng theo yêu cầu."}
                if time.time() - _t0 > _budget:
                    return {"success": False, "rounds": rnd, "history": history,
                            "summary": "⚠ Chưa hoàn thành — quá thời gian cho phép trên web (mô hình phản hồi chậm)."}
                with _supp():
                    self.skip_ads()   # clear any ad before reading/acting on the page
                obs = self.observe()
                els = obs.get("elements") or []
                lines = "\n".join(f'[{e["ref"]}] {e["tag"]}/{e.get("role","")} "{e["label"]}"'
                                  for e in els[:45]) or "(no interactable elements seen)"
                cur_url = obs.get("url", "")
                # READABLE page text so the agent can ANSWER questions (counts, info,
                # results) — not just click. Without this it's blind to page content.
                page_text = ""
                with _supp():
                    page_text = (self._page.evaluate(
                        "() => (document.body && document.body.innerText || '')"
                        ".replace(/\\n{2,}/g,'\\n').trim().slice(0, 2200)") or "")
                # "stuck" must consider the ELEMENT SET too, not just the URL — opening a
                # dropdown/menu (model picker) changes the elements but NOT the url, and
                # that IS progress. Signature = url + element labels.
                el_sig = cur_url + "|" + "|".join((e.get("label") or "")[:12] for e in els[:20])
                stuck = stuck + 1 if el_sig == last_url else 0
                if el_sig != last_url:
                    click_counts = {}   # page changed = progress → reset repeat guard
                last_url = el_sig
                prompt = (
                    "You are a web agent controlling a real Chrome page (DOM-level, like a "
                    "human). Achieve the GOAL with ONE action per step. You operate in ONE "
                    "persistent tab across commands — STAY in the current tab/page, do not "
                    "assume a fresh window.\n\n"
                    + (f"Earlier in this session you: {context}\n" if context else "")
                    + f"GOAL: {command}\n"
                    f"Current page: {obs.get('title','')[:60]} | {cur_url[:70]}\n"
                    f"Done so far:\n" + ("\n".join(history[-6:]) or "(none)") + "\n\n"
                    f"Clickable / fillable elements on the page now:\n{lines}\n\n"
                    + (f"VISIBLE TEXT ON PAGE (read this to ANSWER questions — counts, numbers, "
                       f"info; the answer is often already here):\n{page_text}\n\n" if page_text else "")
                    + "Reply ONE JSON: "
                    '{"action":"navigate|click|fill|press|scroll|wait|media|done",'
                    '"url":"<https url>","ref":<element ref>,"text":"<text for fill>",'
                    '"key":"<Enter|Tab|ArrowDown|..>","dir":"down|up",'
                    '"op":"<voldown|volup|mute|unmute|pause|play>","why":"<short VN>","done":false}\n'
                    "RULES (be decisive, act like a human — do NOT scroll aimlessly):\n"
                    "- GENERAL (works on ANY website, not just one): operate the page like a "
                    "person — find the search box / input / link you need, type into it, click "
                    "results/buttons, fill & submit forms, follow links. The video/YouTube notes "
                    "below are just EXAMPLES of this same skill; apply the same approach to "
                    "Google, shopping, docs, dashboards, any site. NEVER tell the user to do it "
                    "themselves; do it.\n"
                    "- DROPDOWN / PICKER / DIALOG: click the trigger to open it ONCE, then in "
                    "the next step CLICK THE OPTION you want (a DIFFERENT [ref], e.g. the model "
                    "name like 'Claude Haiku 4.5') — do NOT re-click the trigger. If a dialog "
                    "has a CONFIRM button (Start New Chat / OK / Apply / Áp dụng / Lưu / Bắt "
                    "đầu), click it to APPLY the selection before moving on.\n"
                    "- If the GOAL is to READ/FIND info (a count, a number, a fact, 'how many', "
                    "'bao nhiêu'): look in 'VISIBLE TEXT ON PAGE' — if the answer is there, put "
                    "it in 'why' and set done=true. Navigate to the right page first if needed "
                    "(e.g. a profile/friends page), then read it. Don't click aimlessly.\n"
                    "- If the page is a LOGIN/sign-in wall for a site that needs the user's "
                    "account (Facebook, etc.), do NOT try to log in. Set done=true and in 'why' "
                    "tell the user (Vietnamese) the exact fix: 'Trình duyệt AI chưa đăng nhập "
                    "<site> (Chrome khoá cookie). Hãy ĐÓNG Chrome của bạn để AI dùng hồ sơ thật "
                    "đã đăng nhập, hoặc đăng nhập <site> 1 lần trong cửa sổ này.'\n"
                    "- To PLAY music/video: extract ONLY the song/topic from the GOAL (e.g. "
                    "'mở youtube và bật nhạc phonk' → search just 'phonk'; drop words like mở/"
                    "bật/phát/nhạc/youtube/và/cho/giúp). FILL the search box [ref] with that, "
                    "then press Enter. On the results page, CLICK the [ref] of the FIRST item "
                    "whose label STARTS WITH '▶' (that marks a real video link). Do NOT click "
                    "filter chips/nav. Operate the page — don't type a results URL.\n"
                    "- ADS: after the url is '/watch', there is often an AD first. If you see a "
                    "'Skip'/'Bỏ qua quảng cáo'/'Skip Ad' button OR the page text shows it's an ad, "
                    "CLICK that skip button (or wait) — do NOT set done while an ad is playing. "
                    "Only set done=true when the REAL video is playing (no skip button, url '/watch').\n"
                    "- CONTINUATION on the CURRENT video/song (giảm/tăng âm lượng, tạm dừng, "
                    "phát tiếp, tắt/bật tiếng): use action 'media' with op = voldown | volup | "
                    "pause | play | mute | unmute. It controls the video PLAYING IN THIS TAB "
                    "directly — do NOT navigate or open a new tab/window. After it, set done=true. "
                    "(e.g. 'giảm âm lượng video đang chạy' → {\"action\":\"media\",\"op\":\"voldown\","
                    "\"why\":\"đã giảm âm lượng\",\"done\":true})\n"
                    "- Only scroll if NOTHING relevant is in the list."
                    + ("\nNOTE: url unchanged since last step — pick a DIFFERENT clickable [ref] "
                       "(a video title), do not repeat scroll.\n" if stuck >= 1 else "")
                )
                try:
                    raw = llm(prompt) or ""
                except Exception as e:
                    # The LLM call (_ollama_text_sync) can raise on a transient
                    # timeout / ollama hiccup / bad model. This loop's try has only a
                    # finally (no except), so an unguarded raise would CRASH the whole
                    # web task. Treat it as a retryable empty round instead.
                    history.append(f"r{rnd}: model lỗi/timeout — thử lại ({str(e)[:40]})")
                    if stuck >= 2:
                        break
                    with _supp():
                        self._page.wait_for_timeout(1000)
                    continue
                raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I)
                m = re.search(r"\{[\s\S]*\}", raw)
                if not m:
                    history.append(f"r{rnd}: no action");
                    if stuck >= 2: break
                    continue
                try:
                    act = json.loads(m.group(0))
                except Exception:
                    history.append(f"r{rnd}: bad json"); continue
                a = str(act.get("action") or "").lower()
                if a == "done" or act.get("done") is True:
                    history.append(f"r{rnd}: done — {act.get('why','')}")
                    self.shot()
                    return {"success": True, "rounds": rnd + 1, "history": history,
                            "summary": act.get("why") or "Đã xong trên web."}
                if a == "navigate":
                    history.append(f"r{rnd}: " + self.navigate(act.get("url") or ""))
                elif a == "click":
                    _ref = _safe_int(act.get("ref"))
                    click_counts[_ref] = click_counts.get(_ref, 0) + 1
                    if click_counts[_ref] > 2:
                        # Clicking the SAME element 3× without the page changing = stuck
                        # (e.g. re-toggling a dropdown TRIGGER). Force a different target.
                        history.append(f"r{rnd}: BỎ QUA click[{_ref}] (đã bấm 2 lần) — hãy chọn phần tử KHÁC, ví dụ một MỤC trong danh sách/menu vừa mở (ref khác), đừng bấm lại nút mở.")
                    else:
                        history.append(f"r{rnd}: " + self.click(_ref))
                elif a == "fill":
                    history.append(f"r{rnd}: " + self.fill(_safe_int(act.get("ref")), act.get("text") or ""))
                elif a == "press":
                    _k = act.get("key") or "Enter"
                    history.append(f"r{rnd}: " + self.press(_k))
                    # Sending a chat message (Enter) → the answer streams in over a few
                    # seconds. Give it time + mark so we DON'T bail as "stuck" while the
                    # reply is generating (the duck.ai "đang chờ phản hồi" case).
                    if str(_k).lower() in ("enter", "return"):
                        just_sent = 2
                        with _supp():
                            self._page.wait_for_timeout(3500)
                elif a == "scroll":
                    history.append(f"r{rnd}: " + self.scroll(str(act.get("dir") or "down")))
                elif a == "wait":
                    self._page.wait_for_timeout(1500); history.append(f"r{rnd}: wait")
                elif a == "media":
                    history.append(f"r{rnd}: " + self.media_control(act.get("op") or act.get("text") or ""))
                self.shot()  # update the stream frame after each action
                if just_sent > 0:
                    just_sent -= 1   # grace: a reply is generating → don't bail as stuck
                elif stuck >= 3:
                    # HONEST failure — no done signal + page unchanged. Returning
                    # success=True here showed a ✅ for a stalled task (the "báo ✅
                    # giả" complaint); the native agent already returns False here.
                    return {"success": False, "rounds": rnd + 1, "history": history,
                            "summary": "⚠ Chưa hoàn thành — trang web không đổi sau nhiều bước."}
                self._page.wait_for_timeout(1200)
            return {"success": False, "rounds": max_rounds, "history": history,
                    "summary": "⚠ Chưa hoàn thành — đã chạy hết số bước cho phép trên web."}
        finally:
            self.close_pw()


class _supp:
    def __enter__(self): return self
    def __exit__(self, *a): return True
