"""
skemi_iso_desktop.py — TRUE isolated AI desktop environments.

Each "AI desktop" is a real Windows **Desktop object** (CreateDesktop), NOT a
Task View virtual desktop. Why this matters (the user's hard requirements):

  * ISOLATION: apps launched here live on a separate desktop object, so they do
    NOT appear in the user's taskbar / Alt+Tab and never touch the user's apps.
  * INDEPENDENT INSTANCES: the SAME app can run on multiple AI desktops at once
    (Task View couldn't — launching an already-open app just switched to it).
  * NO INTERFERENCE: the user keeps working on their Default desktop; the AI
    operates only the windows it spawned on its own desktop.
  * CAPTURABLE: even though the desktop isn't the visible/input desktop, its
    windows render via PrintWindow(PW_RENDERFULLCONTENT) — proven non-black.
  * GHOST INPUT: PostMessage / WM_SETTEXT reach the windows session-wide without
    moving the user's cursor or stealing focus.

Launch MUST go through win32process.CreateProcess with STARTUPINFO.lpDesktop —
Python's subprocess.STARTUPINFO silently ignores lpDesktop, which is why earlier
attempts leaked apps onto the user's Default desktop.
"""
from __future__ import annotations

import contextlib
import ctypes
import threading
import time
import uuid
from ctypes import wintypes
from typing import Any, Dict, List, Optional

try:
    import win32api      # type: ignore
    import win32con      # type: ignore
    import win32gui      # type: ignore
    import win32process  # type: ignore
    import win32service  # type: ignore
    import win32ui       # type: ignore
    _WIN = True
except Exception:  # pragma: no cover
    _WIN = False

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

# Windows Graphics Capture (WGC) — captures DirectComposition / Direct2D content
# that PrintWindow renders BLACK (Win11 Notepad text area, WinUI apps, browsers).
# Works on OFF-SCREEN (non-minimized) windows. We use it as the primary capture
# for native app windows and fall back to PrintWindow when unavailable.
try:
    from windows_capture import WindowsCapture, Frame, InternalCaptureControl  # type: ignore
    _HAS_WGC = True
except Exception:  # pragma: no cover
    _HAS_WGC = False


_WGC_CACHE: dict = {"title": None, "img": None, "ts": 0.0}


def _wgc_grab(window_title: str, timeout: float = 1.5):
    """One-shot WGC capture of the window whose title matches `window_title`.
    Returns a PIL RGB Image or None. Runs a background capture session, waits for
    the first frame, then stops — so a non-capturable (e.g. minimized) window
    times out instead of hanging.

    Throttled (~4 fps): each call creates a D3D device + capture session; the
    /frame stream polled this 10×/s which loaded the GPU/DWM enough to make the
    USER'S mouse stutter. Within 250 ms we serve the cached frame instead."""
    if not (_HAS_WGC and Image and window_title):
        return None
    now = time.time()
    if (_WGC_CACHE["title"] == window_title and _WGC_CACHE["img"] is not None
            and (now - _WGC_CACHE["ts"]) < 0.25):
        return _WGC_CACHE["img"]
    result = {"img": None}
    done = threading.Event()
    try:
        cap = WindowsCapture(cursor_capture=False, draw_border=False,
                             monitor_index=None, window_name=window_title)
    except Exception:
        return None

    @cap.event
    def on_frame_arrived(frame, capture_control):  # type: ignore
        try:
            buf = frame.frame_buffer  # (H, W, 4) — DXGI B8G8R8A8 = BGRA order!
            # Reverse the channel order BGR→RGB. Taking [:, :, :3] as "RGB" swapped
            # red/blue — every WGC-streamed app showed completely wrong colors
            # ("màu khác hoàn toàn"); PrintWindow frames were fine (raw "BGRX").
            result["img"] = Image.fromarray(buf[:, :, 2::-1].copy(), "RGB")
        except Exception:
            result["img"] = None
        finally:
            done.set()
            with contextlib.suppress(Exception):
                capture_control.stop()

    @cap.event
    def on_closed():  # type: ignore
        done.set()

    control = None
    try:
        control = cap.start_free_threaded()
    except Exception:
        return None
    done.wait(timeout)
    with contextlib.suppress(Exception):
        if control is not None:
            control.stop()
    if result["img"] is not None:
        _WGC_CACHE.update(title=window_title, img=result["img"], ts=now)
    return result["img"]


WINSTA = "WinSta0"
PW_RENDERFULLCONTENT = 0x00000002
CANVAS_W, CANVAS_H = 1920, 1080

# Window classes that are not real app windows (IME / tooltips / helpers).
_SKIP_CLASSES = {
    "IME", "MSCTFIME UI", "Default IME", "tooltips_class32",
    "GDI+ Hook Window Class", "OleMainThreadWndClass", "Chrome_WidgetWin_0",
    # Desktop / taskbar SHELL windows — never an app the agent operates. Without
    # these, "Program Manager" (Progman = the desktop) was classed as an app
    # window and polluted enumeration / could be matched by _find_running_window.
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Shell_CharmWindow", "EdgeUiInputTopWndClass", "ForegroundStaging",
}


_STARTAPPS_CACHE: Dict[str, Any] = {"ts": 0.0, "items": []}


def _startapps_index() -> List[tuple]:
    """All Start-menu entries (Win32 shortcuts AND packaged/Store apps) as
    (name_lower, AppID). Get-StartApps is the ONLY source that lists MSIX/Store
    apps (Claude desktop, Zalo, etc.) — those have an AppUserModelID, no .lnk in
    the shortcut roots that _find_shortcut walks, so the old resolver missed them
    and the router wrongly sent them to the browser. Cached ~60s (cheap, robust)."""
    import time as _t
    now = _t.time()
    if _STARTAPPS_CACHE["items"] and (now - _STARTAPPS_CACHE["ts"] < 60):
        return _STARTAPPS_CACHE["items"]
    items: List[tuple] = []
    try:
        import subprocess as _sp, json as _j
        CREATE_NO_WINDOW = 0x08000000
        out = _sp.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
             "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
            capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW,
        )
        raw = (out.stdout or b"").decode("utf-8", "replace").strip()
        data = _j.loads(raw or "[]")
        if isinstance(data, dict):
            data = [data]
        for it in data:
            nm = (it.get("Name") or "").strip()
            aid = (it.get("AppID") or "").strip()
            if nm and aid:
                items.append((nm.lower(), aid))
    except Exception:
        pass
    if items:
        _STARTAPPS_CACHE["items"] = items
        _STARTAPPS_CACHE["ts"] = now
    return items


def _resolve_startapp(app_name: str) -> str:
    """Fuzzy-match app_name against Get-StartApps. Returns a LAUNCHABLE target:
    a packaged app (AUMID) → 'shell:AppsFolder\\<AUMID>' (opened via explorer),
    a Win32 entry whose AppID is already a path → that path. '' if no good match."""
    import difflib
    q = "".join(c for c in (app_name or "").lower() if c.isalnum())
    if not q or len(q) < 2:
        return ""
    best = (0.0, "")
    for nm, aid in _startapps_index():
        label = "".join(c for c in nm if c.isalnum())
        if not label:
            continue
        if q == label:
            score = 1.0
        elif (len(q) >= 4 and q in label) or (len(label) >= 4 and label in q and len(label) >= 0.8 * len(q)):
            # `label in q` (installed app's name is a substring of the user's word)
            # is only safe when the label is MOST of the query — else a short app
            # name that's a PREFIX of a different word false-matches
            # ("photos" ⊂ "photoshop" → opened Microsoft Photos for "photoshop").
            score = 0.9
        elif label.startswith(q) or (q.startswith(label) and len(label) >= 0.8 * len(q)):
            # `label.startswith(q)`: user typed a prefix of the app name (calc→calculator) = safe.
            # `q.startswith(label)`: user word starts with a shorter app name
            # ("photoshop".startswith("photos")) — guard with the 0.8 length ratio.
            score = 0.85
        else:
            r = difflib.SequenceMatcher(None, q, label).ratio()
            # A loose ratio between strings of very different length is the
            # prefix-extension trap: "photoshop" vs "photos" scores 0.80 purely from
            # the shared prefix. Reject when lengths differ by >20% so we fall back
            # to the web rather than launch a different app.
            if min(len(q), len(label)) < 0.8 * max(len(q), len(label)):
                r = 0.0
            score = r
        if score > best[0]:
            best = (score, aid)
    if best[0] < 0.72:
        return ""
    aid = best[1]
    low = aid.lower()
    if "\\" in aid or low.endswith((".exe", ".lnk", ".url")):
        return aid                       # Win32 AppID is a real path
    return "shell:AppsFolder\\" + aid    # packaged/Store AUMID → launch via the Apps folder


def _fold_vn(s: str) -> str:
    """Diacritic/space-insensitive fold for matching on-screen text. Strips NFD
    combining marks (ì→i, ặ→a), lowercases, NBSP→space, and maps atomic Latin
    letters NFD does NOT decompose — critically đ/Đ (the model writes 'd', the
    screen shows 'đ' → 'dang' must match 'Đặng')."""
    import unicodedata as _ud
    s = _ud.normalize("NFD", str(s or "")).lower().replace("\xa0", " ")
    s = "".join(ch for ch in s if not _ud.combining(ch))
    for _a, _b in (("đ", "d"), ("ø", "o"), ("ł", "l"), ("æ", "ae"), ("œ", "oe"), ("ß", "ss")):
        s = s.replace(_a, _b)
    return s


def _resolve_exe(app_name: str) -> str:
    """Resolve an app name to a launchable target. Tries, in order: phantom_core's
    canonical system-exe table, its Start-Menu shortcut scan, then Get-StartApps
    (which alone covers packaged/Store apps like Claude desktop). Returns '' if the
    app isn't installed at all → the router then opens its web version."""
    try:
        import phantom_core
        hit = phantom_core._resolve_system_exe(app_name) or phantom_core._find_shortcut(app_name)
        if hit:
            return hit
    except Exception:
        pass
    # Packaged/Store + any Start-menu app the shortcut scan missed.
    with contextlib.suppress(Exception):
        s = _resolve_startapp(app_name)
        if s:
            return s
    # Minimal built-in fallback (works even if phantom_core import failed).
    table = {"notepad": "notepad.exe", "calc": "calc.exe", "calculator": "calc.exe",
             "mspaint": "mspaint.exe", "paint": "mspaint.exe", "explorer": "explorer.exe",
             "wordpad": "write.exe", "cmd": "cmd.exe"}
    return table.get((app_name or "").strip().lower(), "")


class IsoDesktop:
    """One isolated AI desktop = one Windows Desktop object + its app processes."""

    # Off-screen anchor for user-desktop mode: apps live here — shown (so they
    # capture + are UIA-controllable) but invisible to the user, no focus steal.
    OFFSCREEN_X, OFFSCREEN_Y = -32000, -32000

    def __init__(self, name: str, label: str = "", user_desktop: bool = False):
        self.name = name                      # id, e.g. "Skemi_ab12"
        self.label = label or name            # human label, e.g. "AI Desktop 1"
        self.full = f"{WINSTA}\\{name}"
        self.hdesk = None
        self.user_desktop = bool(user_desktop)  # operate on the USER's desktop?
        self.processes: List[int] = []        # launched PIDs
        self.ai_windows: List[int] = []       # tracked top-level HWNDs
        self.adopted_windows: set = set()     # USER-opened windows we operate IN PLACE
                                              # (never stash off-screen, never steal
                                              #  focus back from them — they're the user's)
        self.launched_apps: List[str] = []    # alnum-normalised names we launched
                                              # (re-find their LIVE window by title)
        self.created_at = time.time()
        self._last_render: Dict[str, Any] = {}
        self.web = None                        # lazy WebController for web tasks
        self.cancelled = False                 # Stop button → abort the running agent
        self.busy = False                      # an agent loop is currently running
        self.active_surface = "app"            # "web" | "app" — what /frame streams
        self._render_rect: Optional[tuple] = None   # cached IDD monitor rect
        self._render_rect_ts = 0.0
        self._lock = threading.RLock()
        if _WIN and not self.user_desktop:
            # Separate Desktop object (full isolation). Skipped in user_desktop mode.
            access = win32con.GENERIC_ALL
            self.hdesk = win32service.CreateDesktop(name, 0, access, None)

    # ----- launching -------------------------------------------------------
    def _is_browser(self, exe: str) -> str:
        low = (exe or "").lower()
        if "chrome.exe" in low: return "chrome"
        if "msedge.exe" in low or "\\edge" in low: return "edge"
        if "brave.exe" in low: return "brave"
        if "firefox.exe" in low: return "firefox"
        return ""

    def _sweep_user_escapees(self, before_user: set, user_fg: int) -> int:
        """Minimise every NEW window that appeared on the USER's desktop since launch
        (pure-UWP apps escape the iso desktop there, sometimes as several windows).
        Minimised ⇒ cannot be foreground (no focus steal) and not on screen. Returns
        how many were contained, then hands focus back to the user."""
        n = 0
        for h in self._all_user_windows():
            if h in before_user:
                continue
            with contextlib.suppress(Exception):
                if not (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h)):
                    continue
                if win32gui.GetWindow(h, win32con.GW_OWNER):
                    continue  # skip owned dialogs
                cls = win32gui.GetClassName(h) or ""
                if cls in _SKIP_CLASSES:
                    continue
                win32gui.ShowWindow(h, 11)  # SW_FORCEMINIMIZE → never foreground, off-screen
                with self._lock:
                    if h not in self.ai_windows:
                        self.ai_windows.append(h)
                n += 1
        if n and user_fg and user_fg not in self.ai_windows:
            for _ in range(2):
                self._reassert_user_focus(user_fg)
                time.sleep(0.1)
        return n

    def _is_uwp_launch(self, app_name: str, exe: str) -> bool:
        """Heuristic: is this a pure-UWP / Store app whose AppModel broker launches it
        on the INPUT desktop (ignoring lpDesktop)? Those need the SwitchDesktop dance
        to be confined to the iso desktop."""
        a = (app_name or "").strip().lower()
        e = (exe or "").lower()
        UWP_NAMES = {"calc", "calculator", "may tinh", "photos", "anh", "camera",
                     "settings", "cai dat", "store", "microsoft store", "mail",
                     "calendar", "clock", "alarm", "maps", "weather", "people",
                     "snip", "snipping tool", "phone link", "your phone", "xbox"}
        if a in UWP_NAMES or a.startswith("calc"):
            return True
        for stub in ("\\calc.exe", "windowsapps", "\\systemapps\\", "applicationframehost"):
            if stub in e:
                return True
        return False

    def _switch_to_iso_desktop(self) -> bool:
        with contextlib.suppress(Exception):
            if getattr(self, "hdesk", None):
                self.hdesk.SwitchDesktop()
                return True
        return False

    def _switch_to_user_desktop(self) -> None:
        # ALWAYS return the user to their own desktop (called in finally → never stuck).
        with contextlib.suppress(Exception):
            import win32service
            DESKTOP_SWITCHDESKTOP = 0x0100
            d0 = win32service.OpenDesktop("Default", 0, False, DESKTOP_SWITCHDESKTOP)
            d0.SwitchDesktop()

    def launch(self, app_name: str, args: str = "", url: str = "") -> Dict[str, Any]:
        if not _WIN:
            return {"success": False, "error": "Windows only"}
        # Remember the app name (alnum) so _primary_window can re-find its LIVE
        # window by title if the tracked handle dies (Electron splash → real window).
        _akey = "".join(c for c in (app_name or "").lower() if c.isalnum())
        if _akey and len(_akey) >= 3:
            with self._lock:
                if _akey not in self.launched_apps:
                    self.launched_apps.append(_akey)
        # (0) ALREADY RUNNING? Adopt the user's open window and operate it IN PLACE —
        # never launch a 2nd copy, never fall back to the website. This is the core
        # "app đang BẬT trên máy → dùng tiếp" fix. Only for app launches (no url).
        if not url:
            running = self._find_running_window(app_name)
            if running:
                with self._lock:
                    if running not in self.ai_windows:
                        self.ai_windows.append(running)
                    self.adopted_windows.add(running)
                # USER-OPENED window → ABSOLUTE NO-OP on the window. Per the user's
                # rule: "dùng tiếp app đang mở thì để NGUYÊN đó, không hiện, không
                # ẩn". We do NOT move it, resize it, restore it, or touch its
                # styles — not even if it's minimized. The AI operates it purely via
                # background UIA/PostMessage; the stream captures it wherever it is
                # (a minimized one shows a placeholder until the user restores it).
                # This is the only behaviour that never disturbs the user's layout.
                return {"success": True, "pid": 0, "hwnd": int(running),
                        "app": app_name, "exe": "(already running)", "adopted": True,
                        "mode": "user_desktop" if self.user_desktop else "iso"}
        exe = _resolve_exe(app_name)
        if not exe:
            return {"success": False, "error": f"App not found: {app_name}"}
        # Resolve a .lnk to its real .exe FIRST — CreateProcess can't target a desktop
        # object with a shell link, and browser detection needs the real exe path.
        # Preserve the shortcut's ARGUMENTS (e.g. Discord's Squirrel
        # `--processStart Discord.exe`) so the real app launches, not its updater.
        lnk_args = ""
        is_store = exe.lower().startswith("shell:")
        if exe.lower().endswith(".lnk"):
            tgt, lnk_args = self._resolve_lnk_full(exe)
            exe = tgt or exe
        # Browser independence: open a SEPARATE instance (its own profile dir) so it
        # does NOT consolidate into the user's Chrome/Edge on Desktop 1, opened
        # directly at `url` (e.g. a YouTube search). This is how the AI plays music
        # on the isolated desktop while the user keeps their own browser untouched.
        browser = self._is_browser(exe)
        if browser:
            import tempfile, os as _os
            prof = _os.path.join(tempfile.gettempdir(), f"skemi_iso_{self.name}_{browser}")
            # Sanitize + QUOTE the URL so it's a single CreateProcess argument. An
            # unquoted URL with a space would inject extra browser CLI flags
            # (e.g. "https://x --disable-web-security --load-extension=..."). Strip
            # quotes/newlines (no breakout) and wrap in quotes (one positional arg).
            target_raw = (url or args or "").strip().replace('"', '').replace('\n', ' ').replace('\r', ' ')
            target = f'"{target_raw}"' if target_raw else ''
            if browser in ("chrome", "edge", "brave"):
                # --force-renderer-accessibility makes Chrome expose WEB CONTENT in
                # its UI Automation tree, so the agent can see/click page elements.
                # OPEN DIRECTLY ON THE HIDDEN MONITOR (IDD) via --window-position so
                # the browser NEVER flashes on the user's screen ( --start-maximized
                # was removed: it forced a big visible window that stole the screen).
                _rr = self._get_render_rect()
                if _rr:
                    pos = f'--window-position={_rr[0]},{_rr[1]} --window-size={_rr[2]-_rr[0]},{_rr[3]-_rr[1]}'
                else:
                    pos = '--window-position=-32000,-32000'
                cmdline = (f'"{exe}" --user-data-dir="{prof}" --new-window '
                           f'--no-first-run --no-default-browser-check '
                           f'--force-renderer-accessibility {pos} '
                           f'--disable-session-crashed-bubble {target}').strip()
            else:  # firefox
                cmdline = f'"{exe}" -profile "{prof}" -new-window {target}'.strip()
        elif is_store:
            # Packaged/Store app (e.g. Claude desktop): CreateProcess can't run a
            # 'shell:' verb, so let explorer activate it via the AppsFolder. The
            # AppModel broker spawns the real process (often a different pid) — the
            # window is then caught by title in _wait_for_user_window(app_name=...).
            cmdline = f'explorer.exe "{exe}"'
        else:
            extra = (url or args or lnk_args or "").strip()
            cmdline = f'"{exe}" {extra}'.strip()
        try:
            si = win32process.STARTUPINFO()
            si.dwFlags = win32con.STARTF_USESHOWWINDOW
            CREATE_NO_WINDOW = 0x08000000
            if self.user_desktop:
                # USER-DESKTOP mode: launch on the user's own desktop, MINIMIZED +
                # no-activate so it doesn't pop up or steal focus, then move it
                # off-screen (shown) so it's invisible but fully capturable +
                # UIA-controllable, and present in the taskbar.
                si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
                before = set(self._all_user_windows())
                # Remember the user's CURRENT window so we can hand focus straight
                # back — many apps (Win11 Notepad, Electron) self-activate on launch
                # despite SW_SHOWMINNOACTIVE, which would yank focus while the user
                # is typing. We refuse to keep it.
                user_fg = 0
                with contextlib.suppress(Exception):
                    _f = win32gui.GetForegroundWindow()
                    if _f and _f not in self.ai_windows:
                        user_fg = _f
                hProc, hThread, pid, tid = win32process.CreateProcess(
                    None, cmdline, None, None, False, CREATE_NO_WINDOW, None, None, si)
                with contextlib.suppress(Exception):
                    win32api.CloseHandle(hThread)
                with self._lock:
                    self.processes.append(int(pid))
                # Squirrel/Electron apps (Discord, Teams, Slack…) launch via a
                # helper (Update.exe) and create their window only after several
                # seconds with a DIFFERENT pid — give them time so the window gets
                # tracked (otherwise the stream has nothing to capture → black).
                hwnd = self._wait_for_user_window(before, int(pid), deadline=20.0, app_name=app_name)
                if hwnd:
                    self._stash_offscreen(hwnd)
                    with self._lock:
                        if hwnd not in self.ai_windows:
                            self.ai_windows.append(hwnd)
                    if not hasattr(self, "_win_first_seen"):
                        self._win_first_seen = {}
                    self._win_first_seen[hwnd] = time.time()
                # Give focus back to the user (the app may have self-activated).
                for _ in range(3):
                    self._reassert_user_focus(user_fg)
                    time.sleep(0.15)
                return {"success": True, "pid": int(pid), "hwnd": int(hwnd or 0),
                        "app": app_name, "exe": exe, "mode": "user_desktop"}
            # ISOLATED mode: separate Desktop object.
            si.lpDesktop = self.full
            si.wShowWindow = win32con.SW_SHOWNORMAL
            before = set(self._enum_windows())
            before_user = set(self._all_user_windows())   # to detect UWP that escapes
            user_fg0 = win32gui.GetForegroundWindow()
            # ABSOLUTE UWP isolation (opt-in via SKEMI_UWP_ISOLATE): pure-UWP apps are
            # launched by Windows on the INPUT desktop regardless of lpDesktop. To
            # confine them, make the iso desktop the input desktop DURING launch, then
            # switch back. Brief screen flicker is the trade-off, so it's off by
            # default. The switch-back is in `finally` → the user is NEVER left stuck.
            import os as _os
            _uwp_iso = (self._is_uwp_launch(app_name, exe) and
                        _os.environ.get("SKEMI_UWP_ISOLATE", "").lower() in ("1", "true", "yes", "on"))
            _switched = False
            try:
                if _uwp_iso:
                    _switched = self._switch_to_iso_desktop()
                    time.sleep(0.25)
                hProc, hThread, pid, tid = win32process.CreateProcess(
                    None, cmdline, None, None, False, CREATE_NO_WINDOW, None, None, si)
                with contextlib.suppress(Exception):
                    win32api.CloseHandle(hThread)
                with self._lock:
                    self.processes.append(int(pid))
                hwnd = self._wait_for_window(int(pid), before, deadline=8.0 if _uwp_iso else 10.0)
            finally:
                if _switched:
                    self._switch_to_user_desktop()
            # ALWAYS sweep the USER's desktop for windows that escaped there. Pure-UWP
            # apps (Calculator/Photos/Settings) are launched by Windows' AppModel broker
            # on the user's ACTIVE desktop (ignoring lpDesktop), often as SEVERAL windows
            # — and that can happen even when one window did land on our iso desktop.
            # MINIMISE every escapee: a minimised window can NEVER be the foreground
            # window (hard Windows guarantee) → it cannot steal the user's focus, and it's
            # not on the screen (taskbar only). Fixes BOTH bugs for UWP, no flicker.
            esc_n = self._sweep_user_escapees(before_user, user_fg0)
            if hwnd:
                self._fit_window(hwnd)
                with self._lock:
                    if hwnd not in self.ai_windows:
                        self.ai_windows.append(hwnd)
                return {"success": True, "pid": int(pid), "hwnd": int(hwnd),
                        "app": app_name, "exe": exe, "escaped_uwp": bool(esc_n)}
            return {"success": True, "pid": int(pid), "hwnd": 0,
                    "app": app_name, "exe": exe, "escaped_uwp": bool(esc_n)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _all_user_windows(self) -> List[int]:
        out: List[int] = []
        if not _WIN:
            return out
        def _cb(h, _):
            if win32gui.IsWindow(h):
                out.append(h)
            return True
        with contextlib.suppress(Exception):
            win32gui.EnumWindows(_cb, None)
        return out

    @staticmethod
    def _proc_image_name(pid: int) -> str:
        """Base name of the EXE for a pid (e.g. 'claude.exe'), '' on failure."""
        if not _WIN or not pid:
            return ""
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    import os as _os
                    return _os.path.basename(buf.value)
            finally:
                k32.CloseHandle(h)
        except Exception:
            pass
        return ""

    def _find_running_window(self, app_name: str) -> int:
        """Find a top-level window of an app that's ALREADY OPEN on the user's
        machine (matched by window title OR process exe name). Lets the agent
        reuse the user's running Claude/Discord/etc. instead of launching a fresh
        copy or — worse — opening the website. Returns hwnd or 0.

        Skips browser windows: a website open in Chrome is NOT the native app."""
        if not _WIN:
            return 0
        key = "".join(c for c in (app_name or "").lower() if c.isalnum())
        # ≥4 chars: a 3-char key ("app") is a coincidental substring of host exes
        # ("app" ⊂ "applicationframehost") and titles.
        if not key or len(key) < 4:
            return 0
        # Generic HOST / shell processes host arbitrary apps — matching an app to one
        # by its exe name is always wrong ("app" ⊂ "applicationframehost" matched a
        # UWP app's host). Match those windows by TITLE only.
        HOST_EXES = {"applicationframehost", "explorer", "svchost", "dllhost",
                     "rundll32", "sihost", "textinputhost", "runtimebroker",
                     "shellexperiencehost", "startmenuexperiencehost", "searchhost"}

        def _word_match(k: str, text_words: list) -> bool:
            # token-boundary aware: k equals a title word, or one is a ≥0.9-length
            # prefix of the other. 0.9 kills the plural trap ("window" vs "windows" =
            # 0.857) while keeping near-identical names; claude/zalo/discord appear as
            # exact whole words anyway.
            for w in text_words:
                if not w:
                    continue
                if k == w:
                    return True
                if (w.startswith(k) or k.startswith(w)) and min(len(k), len(w)) >= 0.9 * max(len(k), len(w)):
                    return True
            return False

        candidates = []
        for h in self._all_user_windows():
            with contextlib.suppress(Exception):
                if not self._is_app_window(h):
                    continue
                raw_title = (win32gui.GetWindowText(h) or "").lower()
                import re as _re2
                title_words = [w for w in _re2.split(r"[^a-z0-9]+", raw_title) if w]
                _, wpid = win32process.GetWindowThreadProcessId(h)
                exe = self._proc_image_name(int(wpid)).lower()
                if self._is_browser(exe):
                    continue  # a tab in the user's browser ≠ the native app
                pkey = "".join(c for c in exe.replace(".exe", "") if c.isalnum())
                title_hit = _word_match(key, title_words)
                # exe match: NOT for host/shell processes, and require prefix/equality
                # (not arbitrary substring) so a short key can't ride a long host name.
                exe_hit = (bool(pkey) and pkey not in HOST_EXES
                           and (pkey == key or pkey.startswith(key) or key.startswith(pkey))
                           and min(len(key), len(pkey)) >= 0.8 * max(len(key), len(pkey)))
                if title_hit or exe_hit:
                    # Prefer an exact-ish title hit (the focused/real window) over a
                    # mere process match (helpers share the exe name).
                    candidates.append((2 if title_hit else 1, h))
        if not candidates:
            return 0
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]

    def _wait_for_user_window(self, before: set, pid: int, deadline: float = 10.0,
                              app_name: str = "") -> int:
        """Find the newly launched top-level window on the user's desktop. Squirrel/
        Electron apps (Discord, Teams, Slack…) spawn their window LATE via a helper
        process (different pid) AND it may already-ish exist, so we match by THREE
        signals: (1) a NEW app window, (2) the launched pid, (3) a window whose TITLE
        contains the app name (catches Discord = 'Friends - Discord')."""
        name_key = "".join(ch for ch in (app_name or "").lower() if ch.isalnum())
        end = time.time() + deadline
        title_match = 0
        while time.time() < end:
            # (1) a brand-new app window since launch — HIDE it the instant it's seen
            # (stash off-screen BEFORE returning) so it never flashes on the user's
            # screen, even if the app ignored SW_SHOWMINNOACTIVE (Electron/Chromium).
            for h in self._all_user_windows():
                if h in before:
                    continue
                if self._is_app_window(h):
                    self._stash_offscreen(h)
                    return h
            # (2) pid match — also definitely ours → hide on sight
            for h in self._all_user_windows():
                with contextlib.suppress(Exception):
                    _, wp = win32process.GetWindowThreadProcessId(h)
                    if int(wp) == pid and self._is_app_window(h):
                        self._stash_offscreen(h)
                        return h
            # (3) title contains the app name (even if it already existed) — remember
            # it but prefer a new window; fall back to it if nothing newer shows up.
            if name_key and len(name_key) >= 3:
                for h in self._all_user_windows():
                    with contextlib.suppress(Exception):
                        t = "".join(ch for ch in (win32gui.GetWindowText(h) or "").lower() if ch.isalnum())
                        if name_key in t and self._is_app_window(h):
                            title_match = h
                            break
            time.sleep(0.08)   # tight poll → catch + hide the window ASAP (less flash)
        return title_match

    def _get_render_rect(self) -> Optional[tuple]:
        """Return the Amyuni virtual-display (IDD) monitor rect (left,top,right,
        bottom) if one is active, else None. Cached briefly. This is the surface
        the AI's native windows are placed on: a REAL composited monitor Windows
        renders fully (so modern Direct2D/WinUI content is NOT black) but with no
        physical panel, so the user never sees it. Off-screen (-32000) can't do
        this — DWM marks off-screen windows occluded and modern apps skip drawing."""
        now = time.time()
        if self._render_rect is not None and (now - self._render_rect_ts) < 5.0:
            return self._render_rect
        rect = None
        try:
            import phantom_core
            info = phantom_core.find_idd_monitor()
            if info.get("found") and info.get("rect"):
                l, t, r, b = (int(v) for v in info["rect"])
                if (r - l) > 0 and (b - t) > 0:
                    rect = (l, t, r, b)
        except Exception:
            rect = None
        self._render_rect = rect
        self._render_rect_ts = now
        return rect

    def _stash_offscreen(self, hwnd: int) -> None:
        """Place a window where it stays invisible to the user yet fully rendered
        and UIA/WGC-capturable. Prefers the virtual-display (IDD) monitor — a real
        composited surface so modern Direct2D apps render (no black). Falls back to
        the -32000 off-screen anchor (fine for legacy GDI apps) when no IDD is
        active. Never activates / steals focus."""
        try:
            # ORDER MATTERS: un-minimize FIRST, set WS_EX_NOACTIVATE second.
            # Verified live: SetWindowPlacement(showCmd=4, rcNormal=IDD) restores a
            # minimized Notepad onto the hidden monitor — but the SAME call is
            # ignored once WS_EX_NOACTIVATE is already on the window (it stayed
            # iconic at -25600 → black capture).
            if win32gui.IsIconic(hwnd):
                # Un-minimize DIRECTLY ONTO the hidden monitor via SetWindowPlacement
                # (showCmd=SW_SHOWNOACTIVATE + normal rect = IDD). A plain
                # ShowWindow(4) followed immediately by SetWindowPos raced the
                # restore animation and left the window iconic (black capture).
                rr0 = self._get_render_rect()
                if rr0 is not None:
                    with contextlib.suppress(Exception):
                        pl = list(win32gui.GetWindowPlacement(hwnd))
                        pl[1] = 4  # SW_SHOWNOACTIVATE
                        pl[4] = (rr0[0], rr0[1], rr0[2], rr0[3])
                        win32gui.SetWindowPlacement(hwnd, tuple(pl))
            # Mark the window WS_EX_NOACTIVATE: it then CANNOT become the foreground/
            # active window — clicks, UIA Invoke, and self-activation can no longer
            # steal the user's focus while they type. (Removed again in bring_to_user
            # when the user explicitly wants to interact.)
            GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
            with contextlib.suppress(Exception):
                ex = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
                if not (ex & WS_EX_NOACTIVATE):
                    win32gui.SetWindowLong(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
            win32gui.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE (un-minimize, no focus)
            flags = (win32con.SWP_NOACTIVATE | getattr(win32con, "SWP_NOOWNERZORDER", 0x0200)
                     | win32con.SWP_NOZORDER)
            rect = self._get_render_rect()
            if rect is not None:
                l, t, r, b = rect
                # Resize to FILL the virtual monitor via SetWindowPos with
                # SWP_NOACTIVATE — this gives a clean full-screen view WITHOUT
                # activating the window. (SW_MAXIMIZE was removed: it activates the
                # window and STEALS the user's focus — forbidden.)
                win32gui.SetWindowPos(hwnd, 0, l, t, r - l, b - t, flags)
            else:
                win32gui.SetWindowPos(hwnd, 0, self.OFFSCREEN_X, self.OFFSCREEN_Y,
                                      CANVAS_W, CANVAS_H, flags)
        except Exception:
            pass

    def _unstash_to_user(self, h: int) -> None:
        """The USER summoned an AI-launched hidden window (taskbar click): clear
        WS_EX_NOACTIVATE and place it CENTRED on their primary monitor. From then on
        it's treated like an adopted window — left wherever the user puts it, the
        stream/agent keep operating it in place."""
        GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
        with _suppress():
            ex = win32gui.GetWindowLong(h, GWL_EXSTYLE)
            if ex & WS_EX_NOACTIVATE:
                win32gui.SetWindowLong(h, GWL_EXSTYLE, ex & ~WS_EX_NOACTIVATE)
        with _suppress():
            sw = win32api.GetSystemMetrics(0); sh = win32api.GetSystemMetrics(1)
            w, hh = min(1280, sw - 120), min(800, sh - 120)
            win32gui.SetWindowPos(h, 0, (sw - w) // 2, (sh - hh) // 2, w, hh,
                                  win32con.SWP_NOZORDER)
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
        with self._lock:
            self.adopted_windows.add(h)   # user took it → never re-stash

    def _rescue_strays_from_idd(self) -> None:
        """Any USER window that somehow lands on the hidden virtual monitor (a
        drag that slipped through, an app restoring its last position there…) is
        invisible to them — bring it back to the primary monitor automatically,
        centred, without activating it. AI-tracked windows are left alone."""
        now = time.time()
        if now - getattr(self, "_stray_check_ts", 0.0) < 1.0:
            return
        self._stray_check_ts = now
        rr = self._get_render_rect()
        if not rr:
            return
        with self._lock:
            mine = set(self.ai_windows)
        for h in self._all_user_windows():
            if h in mine:
                continue
            with _suppress():
                if not self._is_app_window(h):
                    continue
                r = win32gui.GetWindowRect(h)
                cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                if rr[0] <= cx < rr[2] and rr[1] <= cy < rr[3]:
                    sw = win32api.GetSystemMetrics(0); sh = win32api.GetSystemMetrics(1)
                    w = min(r[2] - r[0], sw - 80); hh = min(r[3] - r[1], sh - 80)
                    win32gui.SetWindowPos(h, 0, (sw - w) // 2, (sh - hh) // 2, w, hh,
                                          win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER)

    def _check_user_summon(self) -> None:
        """A tracked window parked on the hidden monitor became FOREGROUND. Two very
        different causes need opposite reactions:
          * LAUNCH SELF-ACTIVATION — a freshly started process is allowed to
            SetForegroundWindow itself (Electron apps do). That used to be misread
            as a user summon → the window was pulled onto the user's screen + kept
            their focus ("app cứ hiện lên màn hình tôi" + focus steal). Within the
            launch grace window we now GIVE FOCUS BACK and leave the window hidden.
          * USER TASKBAR CLICK (after the grace) — the user wants the window: bring
            it onto their screen."""
        with _suppress():
            fg = win32gui.GetForegroundWindow()
            if not fg:
                return
            if fg not in self.ai_windows:
                self._last_user_fg = fg          # remember where the user really is
                return
            if fg in getattr(self, "adopted_windows", set()):
                return                            # the user's OWN app → never touch it
            if not self._is_on_render_rect(fg):
                return                            # visible window — leave it
            if not hasattr(self, "_win_first_seen"):
                self._win_first_seen = {}
            first = self._win_first_seen.setdefault(fg, time.time())
            if (time.time() - first) < 20.0:
                # Launch-time self-activation. DO NOTHING here: the window is already
                # WS_EX_NOACTIVATE'd (it can't truly hold foreground), and launch()
                # already handed focus back 3×. Calling _reassert_user_focus from the
                # per-FRAME capture thread (~3fps) ran AttachThreadInput continuously
                # → that merged input queues = the residual mouse stutter. So no
                # focus work on the hot stream path.
                return
            self._unstash_to_user(fg)

    def _is_on_render_rect(self, h: int) -> bool:
        """True if the window's centre is on the hidden virtual monitor (IDD) or at
        the off-screen anchor — i.e. NOT on the user's visible screen."""
        try:
            r = win32gui.GetWindowRect(h)
            cx = (r[0] + r[2]) // 2
            if cx <= -20000:
                return True
            rr = self._get_render_rect()
            return bool(rr and rr[0] <= cx < rr[2])
        except Exception:
            return False

    def _is_ai_window(self, h: int) -> bool:
        """True if a window belongs to the AI (so the focus-guard must NOT treat it
        as the user's window). UWP apps (Calculator) expose several window objects
        that aren't all in ai_windows, so we also recognise AI windows by their
        WS_EX_NOACTIVATE style or by being positioned on the hidden IDD monitor."""
        if not (_WIN and h):
            return False
        with self._lock:
            if h in self.ai_windows:
                return True
        try:
            ex = win32gui.GetWindowLong(h, -20)  # GWL_EXSTYLE
            if ex & 0x08000000:                  # WS_EX_NOACTIVATE
                return True
            rr = self._get_render_rect()
            if rr:
                r = win32gui.GetWindowRect(h)
                cx = (r[0] + r[2]) // 2
                if rr[0] <= cx < rr[2]:          # window centre is on the IDD
                    return True
        except Exception:
            pass
        return False

    def _reassert_user_focus(self, user_fg: int) -> None:
        """If an agent action stole the foreground onto one of OUR (AI) windows,
        immediately hand focus BACK to the user's window. Guarantees the user can
        keep typing while the AI works ('không cướp focus'). AttachThreadInput
        bypasses the SetForegroundWindow restriction. No-op if the user still has
        focus or focus is on a non-AI window (a real dialog the user opened)."""
        if not (_WIN and user_fg):
            return
        try:
            import ctypes, win32process, win32api
            cur = win32gui.GetForegroundWindow()
            if cur == user_fg or not self._is_ai_window(cur):
                return
            # ADOPTED window = the user's OWN app we operate in place (e.g. their open
            # Claude). If it's foreground, the USER focused it themselves — posted
            # messages can't change the foreground. Yanking focus away from it after
            # every agent action caused focus-flapping + AttachThreadInput queue
            # merging = the 'con chuột siêu giật' regression. Leave it alone.
            if cur in getattr(self, "adopted_windows", set()):
                return
            u = ctypes.windll.user32
            # Disable the foreground-lock timeout (else background SetForegroundWindow
            # is silently ignored). pvParam carries the value (0 ms) for SPI_SET.
            with _suppress():
                u.SystemParametersInfoW(0x2001, 0, ctypes.c_void_p(0), 0)  # SPI_SETFOREGROUNDLOCKTIMEOUT
            t_cur = win32process.GetWindowThreadProcessId(cur)[0]
            t_usr = win32process.GetWindowThreadProcessId(user_fg)[0]
            me = win32api.GetCurrentThreadId()
            for t in {t_cur, t_usr, me}:
                with _suppress():
                    win32process.AttachThreadInput(me, t, True)
            with _suppress():
                # GENTLE restore — just hand the foreground back. No SwitchToThisWindow
                # (the Alt-Tab call) and no HWND_BOTTOM z-order demotion: those caused
                # visible mouse/window jitter when this ran repeatedly.
                u.SetForegroundWindow(int(user_fg))
            for t in {t_cur, t_usr, me}:
                with _suppress():
                    win32process.AttachThreadInput(me, t, False)
        except Exception:
            pass

    def _start_focus_guard(self) -> None:
        """DISABLED on purpose. The old version polled every 0.1s and, whenever an AI
        window was foreground, forcefully SwitchToThisWindow/SetForegroundWindow'd the
        user's window back — which caused CONSTANT mouse jitter + focus flapping while
        the user typed ('chuột giật giật, mất focus liên tục'). The AI now operates the
        target app purely via BACKGROUND messages (PostMessage clicks, WM_CHAR typing,
        UIA Invoke) that never bring a window to the foreground, so nothing to fight —
        the only self-activation is once at launch, handled by a single post-launch
        restore in launch(). No background thread = no jitter, no stolen focus."""
        return

    def _stop_focus_guard(self) -> None:
        ev = getattr(self, "_focus_guard_stop", None)
        if ev is not None:
            ev.set()
            self._focus_guard_stop = None

    def bring_to_user(self, hwnd: int = 0) -> Dict[str, Any]:
        """Move the AI's window onto the user's visible screen so they can watch /
        take over directly (the 'view live' button)."""
        # ISO (separate-desktop) mode: the window lives on another desktop and CANNOT
        # be moved onto the user's screen. To let the user watch / take over, switch
        # the physical display to the AI desktop. (Ctrl+Alt+Del then Esc, or the
        # 'Về desktop của tôi' control, returns them to their own desktop.)
        if not self.user_desktop and getattr(self, "hdesk", None):
            try:
                self.hdesk.SwitchDesktop()
                return {"success": True, "switched_desktop": True,
                        "note": "Đã chuyển sang desktop AI. Nhấn Ctrl+Alt+Del rồi Esc để quay lại desktop của bạn."}
            except Exception as exc:
                return {"success": False, "error": f"switch desktop: {exc}"}
        h = int(hwnd) or self._primary_window()
        if not h:
            return {"success": False, "error": "no window"}
        try:
            # The user explicitly wants this window now → CLEAR WS_EX_NOACTIVATE so it
            # can take focus again, then restore + place it on-screen + activate.
            GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
            with _suppress():
                ex = win32gui.GetWindowLong(h, GWL_EXSTYLE)
                win32gui.SetWindowLong(h, GWL_EXSTYLE, ex & ~WS_EX_NOACTIVATE)
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
            win32gui.SetWindowPos(h, 0, 200, 120, CANVAS_W, CANVAS_H,
                                  getattr(win32con, "SWP_NOZORDER", 0x0004))
            with _suppress():
                win32gui.SetForegroundWindow(h)
            return {"success": True, "hwnd": h}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _resolve_lnk_target(self, lnk: str) -> str:
        return self._resolve_lnk_full(lnk)[0]

    def _resolve_lnk_full(self, lnk: str):
        """Return (target_exe, arguments) for a .lnk. Many apps (Discord, Teams,
        Spotify, GitHub Desktop…) ship a Squirrel shortcut whose target is
        Update.exe with args like `--processStart Discord.exe` — dropping the args
        launches the updater (nothing visible). Preserving them launches the app."""
        try:
            import pythoncom  # type: ignore
            from win32com.shell import shell  # type: ignore
            sl = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                            pythoncom.CLSCTX_INPROC_SERVER,
                                            shell.IID_IShellLink)
            sl.QueryInterface(pythoncom.IID_IPersistFile).Load(lnk)
            path, _ = sl.GetPath(shell.SLGP_RAWPATH)
            args = ""
            with contextlib.suppress(Exception):
                args = sl.GetArguments() or ""
            return (path or "", args or "")
        except Exception:
            return ("", "")

    def _enum_windows(self) -> List[int]:
        out: List[int] = []
        if not _WIN:
            return out
        if self.user_desktop:
            # Only the windows the AI launched — keeps it focused on its own apps
            # and never reasons about the user's other windows.
            with self._lock:
                return [h for h in self.ai_windows if win32gui.IsWindow(h)]
        if not self.hdesk:
            return out

        def _cb(h, _):
            try:
                out.append(h)
            except Exception:
                pass
            return True
        try:
            win32gui.EnumDesktopWindows(self.hdesk, _cb, None)
        except Exception:
            pass
        return out

    def _wait_for_window(self, pid: int, before: Optional[set] = None,
                         deadline: float = 10.0) -> int:
        before = before or set()
        end = time.time() + deadline
        while time.time() < end:
            wins = self._enum_windows()
            # 1) Prefer a window owned by the launched pid.
            for h in wins:
                try:
                    _, wpid = win32process.GetWindowThreadProcessId(h)
                    if int(wpid) == pid and self._is_app_window(h):
                        return h
                except Exception:
                    continue
            # 2) Fallback: any NEW app window that appeared since launch (some apps
            #    re-parent to a broker process, so the pid won't match).
            for h in wins:
                if h not in before and self._is_app_window(h):
                    return h
            time.sleep(0.2)
        return 0

    def _is_app_window(self, h: int) -> bool:
        try:
            if not win32gui.IsWindow(h):
                return False
            cls = win32gui.GetClassName(h) or ""
            if cls in _SKIP_CLASSES:
                return False
            # Top-level only (no owner).
            if win32gui.GetWindow(h, win32con.GW_OWNER):
                return False
            style = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
            if not (style & win32con.WS_VISIBLE):
                return False
            # We launch apps MINIMISED on purpose (no focus steal). A minimised
            # window has a tiny off-screen rect, so the size check below would
            # wrongly reject it — accept it as long as it has a real title.
            if win32gui.IsIconic(h):
                return bool((win32gui.GetWindowText(h) or "").strip())
            rect = win32gui.GetWindowRect(h)
            if (rect[2] - rect[0]) < 80 or (rect[3] - rect[1]) < 60:
                return False
            return True
        except Exception:
            return False

    def _fit_window(self, hwnd: int) -> None:
        """Maximize a window on the isolated desktop so it fills the frame cleanly.
        It's a different desktop, so this never disturbs the user's foreground."""
        try:
            # SW_MAXIMIZE (3) fills the isolated desktop's work area. Because the
            # window lives on a non-input desktop, this can't steal the user's focus.
            win32gui.ShowWindow(hwnd, 3)
        except Exception:
            pass

    # ----- capture ---------------------------------------------------------
    def _print_window(self, hwnd: int):
        if Image is None:
            return None
        # GDI handles freed in `finally` — the stream polls capture continuously, so
        # leaking a DC/bitmap on ANY exception path (PrintWindow / GetBitmapBits can
        # throw on a resizing or oversized window) would exhaust the ~10k per-process
        # GDI limit over time and kill the whole stream.
        hdc = src = mem = bmp = None
        try:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w <= 0 or h <= 0:
                return None
            hdc = win32gui.GetWindowDC(hwnd)
            src = win32ui.CreateDCFromHandle(hdc)
            mem = src.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(src, w, h)
            mem.SelectObject(bmp)
            ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), PW_RENDERFULLCONTENT)
            info = bmp.GetInfo()
            bits = bmp.GetBitmapBits(True)
            img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
            if img.getbbox() is None:
                return None  # black
            return img.convert("RGB"), rect
        except Exception:
            return None
        finally:
            if bmp is not None:
                with _suppress(): win32gui.DeleteObject(bmp.GetHandle())
            if mem is not None:
                with _suppress(): mem.DeleteDC()
            if src is not None:
                with _suppress(): src.DeleteDC()
            if hdc is not None:
                with _suppress(): win32gui.ReleaseDC(hwnd, hdc)

    def _grab_screen_rect(self, rect):
        """BitBlt a SCREEN REGION (e.g. the whole IDD virtual monitor) → PIL RGB.
        Capturing a real composited monitor is reliable for Electron/Chromium apps
        (Discord, Teams…) that per-window PrintWindow renders BLACK. The AI's
        windows are stashed maximised on the IDD, so this grabs them cleanly."""
        hdc = srcdc = memdc = bmp = None
        try:
            import win32ui
            l, t, r, b = (int(v) for v in rect)
            w, h = r - l, b - t
            if w <= 0 or h <= 0:
                return None
            hdc = win32gui.GetDC(0)
            srcdc = win32ui.CreateDCFromHandle(hdc)
            memdc = srcdc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(srcdc, w, h)
            memdc.SelectObject(bmp)
            memdc.BitBlt((0, 0), (w, h), srcdc, (l, t), win32con.SRCCOPY)
            info = bmp.GetInfo()
            bits = bmp.GetBitmapBits(True)
            return Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
        except Exception:
            return None
        finally:
            # Always release the DCs/bitmap — see _print_window (GDI-limit leak).
            if bmp is not None:
                with _suppress(): win32gui.DeleteObject(bmp.GetHandle())
            if memdc is not None:
                with _suppress(): memdc.DeleteDC()
            if srcdc is not None:
                with _suppress(): srcdc.DeleteDC()
            if hdc is not None:
                with _suppress(): win32gui.ReleaseDC(0, hdc)

    def _grab_window(self, hwnd: int):
        """Return (PIL RGB image, window_rect) for one window. Tries WGC first
        (renders modern Direct2D/WinUI content that PrintWindow shows black),
        then falls back to PrintWindow. Rect is the on-screen window rect so
        click() coordinate mapping stays correct."""
        if not hwnd:
            return None
        title = ""
        with _suppress():
            title = win32gui.GetWindowText(hwnd)
        if _HAS_WGC and title:
            img = _wgc_grab(title)
            if img is not None and img.getbbox() is not None:
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                except Exception:
                    rect = (0, 0, img.size[0], img.size[1])
                return img, rect
        return self._print_window(hwnd)

    def capture(self):
        """Render the isolated desktop to a CANVAS_W x CANVAS_H frame.

        Default: show the PRIMARY app window (the AI's current focus — largest /
        most-recently launched) scaled to fill, so the stream is a clean single-app
        view. If several windows are open we letterbox the primary and leave the
        rest accessible via list_windows(). Returns a PIL RGB image."""
        if Image is None:
            return None
        canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (12, 14, 22))
        # The stream loop runs continuously → cheap place to notice the user
        # summoning a hidden app via its taskbar icon, and to rescue any USER
        # window that strayed onto the invisible virtual monitor.
        self._check_user_summon()
        self._rescue_strays_from_idd()
        primary = self._primary_window()
        # No app open → show a clean placeholder, NOT the virtual-monitor wallpaper
        # ("tự nhiên stream màn hình đó"). The stream LOCKS onto the app window only.
        if not primary:
            self._draw_placeholder(canvas, "Chưa có ứng dụng nào mở — ra lệnh để Skemi mở & thao tác.")
            return canvas
        # Bring the CURRENT app to the front (no-activate, no focus steal) so the
        # stream + the agent's clicks/typing target the right window — but ONLY if
        # it sits on the hidden virtual monitor. This runs per FRAME (~10×/s): doing
        # it to a window on the user's VISIBLE screen kept shoving it on top of
        # everything they did ("app cứ liên tục hiện lên màn hình tôi").
        with _suppress():
            if self._is_on_render_rect(primary):
                win32gui.SetWindowPos(primary, getattr(win32con, "HWND_TOP", 0), 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        wins = [h for h in self._enum_windows() if self._is_app_window(h)]
        order = ([primary] if primary else []) + [w for w in wins if w != primary]
        # 1) Lock onto the app WINDOW: WGC renders modern content, else PrintWindow.
        shot = None
        for h in order:
            shot = self._grab_window(h)
            if shot and shot[0] is not None and shot[0].getbbox() is not None:
                break
            shot = None
        if shot:
            img, rect = shot
            iw, ih = img.size
            if iw > 0 and ih > 0:
                scale = min(CANVAS_W / iw, CANVAS_H / ih)
                nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
                ox, oy = (CANVAS_W - nw) // 2, (CANVAS_H - nh) // 2
                with _suppress():
                    canvas.paste(img.resize((nw, nh)), (ox, oy))
                self._last_render = {"hwnd": order[0] if order else 0, "rect": list(rect),
                                     "ox": ox, "oy": oy, "scale": scale, "nw": nw, "nh": nh}
                return canvas
        # 2) Electron/Chromium fallback (per-window WGC came back black): BitBlt the
        #    app WINDOW'S screen rect — locks onto the window, NOT the whole monitor
        #    (so no wallpaper around it). Works because the window is placed on the
        #    composited virtual monitor.
        with _suppress():
            wr = win32gui.GetWindowRect(primary)
            if wr and (wr[2] - wr[0]) > 60 and (wr[3] - wr[1]) > 60 and wr[0] > -30000:
                mon = self._grab_screen_rect(wr)
                if mon is not None and mon.getbbox() is not None:
                    iw, ih = mon.size
                    scale = min(CANVAS_W / iw, CANVAS_H / ih)
                    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
                    ox, oy = (CANVAS_W - nw) // 2, (CANVAS_H - nh) // 2
                    canvas.paste(mon.resize((nw, nh)), (ox, oy))
                    self._last_render = {"hwnd": primary, "rect": list(wr),
                                         "ox": ox, "oy": oy, "scale": scale, "nw": nw, "nh": nh}
                    return canvas
        self._draw_placeholder(canvas, "Đang tải ứng dụng…")
        return canvas

    def _draw_placeholder(self, canvas, text: str) -> None:
        """Clean 'no app' placeholder so the stream never shows a scary black box or
        the virtual-monitor wallpaper when nothing is running. Soft gradient + clear,
        larger centred message."""
        try:
            from PIL import ImageDraw, ImageFont
            d = ImageDraw.Draw(canvas)
            # soft vertical gradient (dark slate → indigo) instead of flat black
            for y in range(0, CANVAS_H, 4):
                t = y / CANVAS_H
                col = (int(16 + 14 * t), int(18 + 10 * t), int(30 + 28 * t))
                d.rectangle([0, y, CANVAS_W, y + 4], fill=col)
            font = None
            for _f in ("segoeui.ttf", "arial.ttf"):
                try:
                    font = ImageFont.truetype(_f, 30); break
                except Exception:
                    continue
            msg = str(text)
            try:
                tw = d.textlength(msg, font=font) if hasattr(d, "textlength") else len(msg) * 15
            except Exception:
                tw = len(msg) * 15
            d.text(((CANVAS_W - tw) / 2, CANVAS_H / 2 - 18), msg, fill=(190, 198, 220), font=font)
        except Exception:
            pass

    def list_windows(self) -> List[Dict[str, Any]]:
        out = []
        for h in self._enum_windows():
            if not self._is_app_window(h):
                continue
            with _suppress():
                out.append({"hwnd": int(h), "title": win32gui.GetWindowText(h),
                            "class": win32gui.GetClassName(h)})
        return out

    def capture_jpeg(self, quality: int = 80) -> bytes:
        # Fully exception-safe: the /iso/frame stream polls this continuously, so
        # ANY exception here must be swallowed (return b"") rather than propagate
        # and drop the connection (the "stream chụp rồi đứng / reset" symptom).
        import io
        try:
            # Stream whichever surface the AI last acted on. For WEB we serve the
            # cached Playwright screenshot (last_shot); Playwright's sync API is
            # thread-bound to the web-agent worker so we must NOT call web.shot()
            # from this HTTP thread. For native apps we fall through to capture().
            # (WEB is served FIRST, before the native busy-throttle below: web frames
            # are cheap CDP screenshots that don't contend with UIA, and serving the
            # stale native _jpeg_cache during a web task would show the wrong surface.)
            if getattr(self, "active_surface", "app") == "web":
                web = getattr(self, "web", None)
                # Only serve the cached page screenshot if the browser is STILL ALIVE.
                # Otherwise it's a STALE frame of a closed page ("app đã tắt mà vẫn
                # thấy cửa sổ") → fall through to a live capture / placeholder instead.
                alive = False
                with _suppress():
                    alive = bool(web and web.proc and web.proc.poll() is None)
                shot = getattr(web, "last_shot", b"") if alive else b""
                if shot:
                    return shot
            # THROTTLE WHILE THE AGENT IS WORKING (native surface only). A real
            # capture (WGC/PrintWindow + EnumWindows in summon/rescue) is GPU/GDI
            # heavy; the stream polls it ~3×/s. Running that concurrently with the
            # agent's cross-process UIA starved the agent → it couldn't focus/type
            # ("siêu lag, thao tác không được khi xem stream"). While busy, serve the
            # LAST native jpeg, refreshing at most ~1.1s.
            now = time.time()
            if getattr(self, "busy", False) and getattr(self, "_jpeg_cache", b""):
                if (now - getattr(self, "_jpeg_cache_ts", 0.0)) < 1.1:
                    return self._jpeg_cache
            img = self.capture()
            if img is None and Image is not None:
                # Never return empty → the frontend only updates the <img> when a new
                # frame LOADS, so a 503 freezes the last (stale) frame. Always emit a
                # fresh placeholder instead.
                img = Image.new("RGB", (CANVAS_W, CANVAS_H), (16, 18, 30))
                self._draw_placeholder(img, "Chưa có ứng dụng nào mở")
            if img is None:
                return b""
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            data = buf.getvalue()
            self._jpeg_cache = data
            self._jpeg_cache_ts = time.time()
            return data
        except Exception:
            # Last-resort placeholder so the stream stays live (no frozen frame).
            try:
                if Image is not None:
                    ph = Image.new("RGB", (CANVAS_W, CANVAS_H), (16, 18, 30))
                    self._draw_placeholder(ph, "Đang chờ…")
                    b = io.BytesIO(); ph.save(b, format="JPEG", quality=quality)
                    return b.getvalue()
            except Exception:
                pass
            return b""

    # ----- ghost input (no cursor / no focus steal) ------------------------
    def _adopt_new_windows(self) -> None:
        """Generic window tracking: any top-level app window that appeared since the
        command baseline is the AI's → adopt + hide it (works for Explorer/Office/
        Electron/anything, regardless of title or pid)."""
        if not (_WIN and self.user_desktop):
            return
        base = getattr(self, "_cmd_baseline", None)
        if base is None:
            return
        # Pids of ADOPTED (user-owned) windows: their new windows/popups (menus,
        # dialogs, a new session window) belong to the USER's visible app — track
        # them so the agent can operate them, but NEVER stash them off-screen.
        adopted_pids = set()
        with _suppress():
            for ah in list(getattr(self, "adopted_windows", set())):
                if win32gui.IsWindow(ah):
                    adopted_pids.add(win32process.GetWindowThreadProcessId(ah)[1])
        for h in self._all_user_windows():
            if h in base:
                continue
            with _suppress():
                if not self._is_app_window(h):
                    continue
                with self._lock:
                    new = h not in self.ai_windows
                    if new:
                        self.ai_windows.append(h)
                if new:
                    if not hasattr(self, "_win_first_seen"):
                        self._win_first_seen = {}
                    self._win_first_seen[h] = time.time()
                    pid = 0
                    with _suppress():
                        pid = win32process.GetWindowThreadProcessId(h)[1]
                    if pid in adopted_pids:
                        # New window/popup of a USER-opened app: it's the user's own
                        # app behaving normally — track it (operable, process never
                        # killed) but do NOT touch its placement.
                        self.adopted_windows.add(h)
                    else:
                        self._stash_offscreen(h)   # AI-launched → hidden virtual monitor

    def _park_idle_windows(self) -> None:
        """BETWEEN commands, park AI-LAUNCHED windows MINIMIZED with an ON-SCREEN
        restore rect. A raw taskbar-icon click on a minimized window does SW_RESTORE
        → it comes back ON-SCREEN natively (validated), so the user can summon the
        AI's app with a normal taskbar click — no NOACTIVATE blocking, no detection
        needed. ADOPTED (user-opened) windows are NEVER touched. Clears
        WS_EX_NOACTIVATE so the restore activates normally."""
        if not _WIN:
            return
        GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
        with _suppress():
            sw = win32api.GetSystemMetrics(0); sh = win32api.GetSystemMetrics(1)
        w, hh = min(1280, sw - 160), min(840, sh - 160)
        x, y = (sw - w) // 2, (sh - hh) // 2
        restore = (x, y, x + w, y + hh)
        with self._lock:
            targets = [h for h in self.ai_windows if h not in self.adopted_windows]
        for h in targets:
            with _suppress():
                if not win32gui.IsWindow(h):
                    continue
                ex = win32gui.GetWindowLong(h, GWL_EXSTYLE)
                if ex & WS_EX_NOACTIVATE:
                    win32gui.SetWindowLong(h, GWL_EXSTYLE, ex & ~WS_EX_NOACTIVATE)
                pl = list(win32gui.GetWindowPlacement(h))
                pl[1] = win32con.SW_SHOWMINIMIZED
                pl[4] = restore
                win32gui.SetWindowPlacement(h, tuple(pl))

    def _unpark_windows(self) -> None:
        """Re-show AI-launched windows (un-minimize back onto the hidden monitor /
        off-screen) at the START of a command so the agent can operate + capture
        them. Adopted (user-opened) windows are left exactly as the user has them."""
        if not _WIN:
            return
        with self._lock:
            targets = [h for h in self.ai_windows if h not in self.adopted_windows]
        for h in targets:
            with _suppress():
                if win32gui.IsWindow(h) and win32gui.IsIconic(h):
                    self._stash_offscreen(h)   # ShowWindow(SW_SHOWNOACTIVATE) + off-screen

    def _prune_dead_windows(self) -> None:
        """Drop closed HWNDs from the tracking collections. The unified Live-Control
        desktop is long-lived (shared across every command), and ai_windows/
        adopted_windows/_win_first_seen are only ever appended to — without pruning
        they accumulate dead handles for the whole server lifetime (slow leak, and a
        stale handle could be re-used by a NEW unrelated window)."""
        if not _WIN:
            return
        with self._lock:
            alive = [h for h in self.ai_windows if win32gui.IsWindow(h)]
            self.ai_windows = alive
            aset = set(alive)
            self.adopted_windows = {h for h in getattr(self, "adopted_windows", set()) if h in aset}
            fs = getattr(self, "_win_first_seen", None)
            if isinstance(fs, dict):
                for h in [k for k in fs if not win32gui.IsWindow(k)]:
                    fs.pop(h, None)

    def _primary_window(self) -> int:
        with self._lock:
            # Most-recently adopted live window first (the app the AI just opened).
            for h in reversed(self.ai_windows):
                if _WIN and win32gui.IsWindow(h):
                    return h
        # Tracked window(s) died — e.g. Electron (Discord/Teams/Slack) opens a
        # transient splash that closes, then the REAL window opens with a new hwnd.
        # Re-find the LIVE window of any app we launched, by title, and re-adopt it
        # so UIA/typing/capture target the actual app (not a dead handle).
        if _WIN and self.launched_apps:
            for h in self._all_user_windows():
                with _suppress():
                    if not self._is_app_window(h):
                        continue
                    t = "".join(c for c in (win32gui.GetWindowText(h) or "").lower() if c.isalnum())
                    if not t:
                        continue
                    if any(name and name in t for name in self.launched_apps):
                        with self._lock:
                            if h not in self.ai_windows:
                                self.ai_windows.append(h)
                        return h
        wins = [h for h in self._enum_windows() if self._is_app_window(h)]
        return wins[0] if wins else 0

    def _edit_child(self, hwnd: int) -> int:
        found = [0]
        classes = ("edit", "richedit", "richeditd2dpt", "scintilla")
        def _cb(h, _):
            try:
                if any(k in (win32gui.GetClassName(h) or "").lower() for k in classes):
                    found[0] = h
                    return False
            except Exception:
                pass
            return True
        with _suppress():
            win32gui.EnumChildWindows(hwnd, _cb, None)
        return found[0]

    def click(self, x_norm: float, y_norm: float, hwnd: int = 0) -> Dict[str, Any]:
        """Background click at canvas-normalized (0..1) coords. No cursor move,
        no focus steal. Translates through the last capture's letterbox mapping so
        what the AI 'sees' lines up with where the click lands."""
        r = self._last_render or {}
        target = int(hwnd) or int(r.get("hwnd") or 0) or self._primary_window()
        if not target:
            return {"success": False, "error": "no window"}
        try:
            # Canvas pixel from normalized coords.
            px, py = x_norm * CANVAS_W, y_norm * CANVAS_H
            if r and r.get("hwnd") == target and r.get("scale"):
                # Undo letterbox: canvas -> window-image pixel -> client coord.
                wx = (px - r["ox"]) / r["scale"]
                wy = (py - r["oy"]) / r["scale"]
                rect = r.get("rect") or win32gui.GetWindowRect(target)
                # window-image pixel is relative to the window's top-left (window DC).
                sx, sy = int(rect[0] + wx), int(rect[1] + wy)
            else:
                rect = win32gui.GetWindowRect(target)
                sx = int(rect[0] + x_norm * (rect[2] - rect[0]))
                sy = int(rect[1] + y_norm * (rect[3] - rect[1]))
            return self._click_screen_point(target, sx, sy)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _leaf_at_point(self, target: int, sx: int, sy: int) -> int:
        """Deepest visible child window of `target` under SCREEN point (sx,sy) —
        the window the OS hit-test would deliver mouse input to."""
        leaf = int(target)
        for _ in range(12):
            try:
                pt = win32gui.ScreenToClient(leaf, (int(sx), int(sy)))
                ch = win32gui.ChildWindowFromPoint(leaf, pt)
                if not ch or ch == leaf or not win32gui.IsWindowVisible(ch):
                    break
                leaf = ch
            except Exception:
                break
        return leaf

    def _click_screen_point(self, target: int, sx: int, sy: int) -> Dict[str, Any]:
        """Post a background click at SCREEN pixel (sx,sy) to the window that would
        actually receive it. Critical for Chromium/Electron (Claude, Discord, VS Code):
        mouse messages are only processed by the Chrome_RenderWidgetHostHWND CHILD —
        posting to the top-level frame is silently dropped (clicks 'did nothing').
        Descend to the deepest visible child at the point, like the OS hit-test."""
        try:
            leaf = self._leaf_at_point(target, sx, sy)
            cx, cy = win32gui.ScreenToClient(leaf, (int(sx), int(sy)))
            lp = (int(cy) & 0xFFFF) << 16 | (int(cx) & 0xFFFF)
            WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
            win32gui.PostMessage(leaf, WM_MOUSEMOVE, 0, lp)
            win32gui.PostMessage(leaf, WM_LBUTTONDOWN, 0x0001, lp)
            win32gui.PostMessage(leaf, WM_LBUTTONUP, 0, lp)
            return {"success": True, "hwnd": target, "leaf": int(leaf)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def type_text(self, text: str, hwnd: int = 0, append: bool = False) -> Dict[str, Any]:
        """Focus-free text entry into the focused window's edit/document surface.
        Verified working on Win11 Notepad's RichEditD2DPT via WM_SETTEXT. When
        append=True the current content is read back and the new text added, so
        multi-step editing ('add a second line') doesn't wipe earlier text."""
        target = int(hwnd) or self._primary_window()
        if not target:
            return {"success": False, "error": "no window"}
        WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH, WM_CHAR = 0x000C, 0x000D, 0x000E, 0x0102
        edit = self._edit_child(target)
        # 1) Standard Win32 edit/RichEdit (Notepad, classic apps) → WM_SETTEXT (fast, exact).
        if edit:
            try:
                new_text = str(text)
                if append:
                    try:
                        import ctypes
                        n = win32gui.SendMessage(edit, WM_GETTEXTLENGTH, 0, 0) or 0
                        if n > 0:
                            buf = ctypes.create_unicode_buffer(int(n) + 2)
                            win32gui.SendMessage(edit, WM_GETTEXT, int(n) + 1, buf)
                            cur = buf.value or ""
                            sep = "" if (not cur or cur.endswith("\n")) else "\r\n"
                            new_text = cur + sep + str(text)
                    except Exception:
                        pass
                win32gui.SendMessage(edit, WM_SETTEXT, 0, new_text)
                return {"success": True, "hwnd": target, "method": "wm_settext", "appended": append}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        # 2) No standard edit → Electron/Chromium contenteditable (Discord/Slack/Teams/
        #    VS Code). WM_SETTEXT does nothing there. Send REAL characters to the
        #    keyboard-FOCUSED child element (focus-free PostMessage, no SendInput so the
        #    user's cursor/focus is untouched). The box must be focused first (click it).
        try:
            # Find the app's keyboard-focused child via GetGUIThreadInfo — reads the
            # info WITHOUT AttachThreadInput. Attaching merged OUR (busy) python
            # thread's input queue with the app's — while merged, the USER's real
            # mouse/keyboard processing stalls in bursts ('con chuột siêu giật').
            foc = self._focused_child(target)
            for ch in str(text):
                with _suppress():
                    self._post_wm_char(foc, ch)   # surrogate-pair aware (emoji safe)
                time.sleep(0.006)
            return {"success": True, "hwnd": target, "method": "wm_char_electron"}
        except Exception as exc:
            with _suppress():
                win32gui.SendMessage(target, WM_SETTEXT, 0, str(text))
            return {"success": True, "hwnd": target, "method": "wm_settext_fallback", "warn": str(exc)}

    @staticmethod
    def _post_wm_char(hwnd: int, ch: str) -> None:
        """PostMessage a single character as WM_CHAR. WM_CHAR carries a 16-bit UTF-16
        code unit, so a non-BMP char (emoji 😏 = U+1F60F, CJK-ext) MUST be sent as a
        surrogate PAIR — `ord(ch)` alone (>0xFFFF) gets truncated to garbage."""
        WM_CHAR = 0x0102
        o = ord(ch)
        if o > 0xFFFF:
            o -= 0x10000
            win32gui.PostMessage(hwnd, WM_CHAR, 0xD800 + (o >> 10), 0)
            win32gui.PostMessage(hwnd, WM_CHAR, 0xDC00 + (o & 0x3FF), 0)
        else:
            win32gui.PostMessage(hwnd, WM_CHAR, o, 0)

    def _focused_child(self, target: int) -> int:
        """The keyboard-focused child window of `target`'s GUI thread, read via
        GetGUIThreadInfo (NO AttachThreadInput — attaching merges input queues and
        stalls the user's real mouse). Falls back to `target` itself."""
        try:
            import win32process
            class _GTI(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                            ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                            ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                            ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                            ("rcCaret", wintypes.RECT)]
            tid = win32process.GetWindowThreadProcessId(target)[0]
            gti = _GTI(); gti.cbSize = ctypes.sizeof(_GTI)
            if ctypes.windll.user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
                return int(gti.hwndFocus)
        except Exception:
            pass
        return int(target)

    def press_key(self, key: str, hwnd: int = 0) -> Dict[str, Any]:
        target = int(hwnd) or self._primary_window()
        if not target:
            return {"success": False, "error": "no window"}
        # Win32 edit child if any; else the app's real focused child (Electron:
        # Enter must reach the renderer child that holds the caret — posting to the
        # top-level frame is dropped, the message never 'sends').
        edit = self._edit_child(target) or self._focused_child(target)
        vk_map = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
                  "backspace": 0x08, "bksp": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
                  "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
                  "arrowup": 0x26, "arrowdown": 0x28, "arrowleft": 0x25, "arrowright": 0x27,
                  "space": 0x20, "spacebar": 0x20, "home": 0x24, "end": 0x23,
                  "pageup": 0x21, "pagedown": 0x22, "pgup": 0x21, "pgdn": 0x22, "pgdown": 0x22,
                  "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
                  "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B}
        # Normalize: lowercase, strip braces/spaces, and common separators
        # ("Arrow Down" / "page_down" → "arrowdown"/"pagedown").
        _k = str(key).lower().strip().strip("{}").replace(" ", "").replace("_", "").replace("-", "")
        vk = vk_map.get(_k)
        try:
            WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
            if vk is not None:
                win32gui.PostMessage(edit, WM_KEYDOWN, vk, 0)
                win32gui.PostMessage(edit, WM_KEYUP, vk, 0)
            elif len(str(key)) == 1:
                self._post_wm_char(edit, str(key))   # surrogate-pair aware (emoji safe)
            return {"success": True, "hwnd": target}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ----- UIA semantic tree + autonomous agent ---------------------------
    def _uia_interactables(self):
        """Walk the primary window's UI Automation tree and return interactable
        controls as (list_of_dicts, refs). Each dict: {id,type,name,value}. refs maps
        id -> live control object (used to act in the SAME call/thread — UIA/COM
        objects are apartment-bound, so enumerate + act must share a thread)."""
        out, refs = [], {}
        try:
            import uiautomation as uia
        except Exception:
            return out, refs
        hwnd = self._primary_window()
        if not hwnd:
            return out, refs
        # WAKE Chromium/Electron accessibility: Discord/Teams/Slack/VS Code expose
        # NOTHING to UIA until an a11y client asks. Requesting the MSAA client object
        # (WM_GETOBJECT + AccessibleObjectFromWindow) flips Chromium into a11y mode so
        # its real tree (buttons, DM list, message box) becomes visible to UIA.
        if not getattr(self, "_a11y_woken", None):
            self._a11y_woken = set()
        if hwnd not in self._a11y_woken:
            with _suppress():
                import ctypes
                from ctypes import wintypes
                OBJID_CLIENT = 0xFFFFFFFC
                ctypes.windll.user32.SendMessageTimeoutW(
                    int(hwnd), 0x003D, 0, OBJID_CLIENT, 0x0002, 300, ctypes.byref(wintypes.DWORD()))
                # also via oleacc, which is what screen readers use
                guid = (ctypes.c_byte * 16)(0x18, 0xCA, 0xE5, 0x61, 0x84, 0x6E, 0x46, 0x4B,
                                            0x95, 0x79, 0x70, 0x6C, 0x0C, 0xCF, 0xC7, 0xD8)
                acc = ctypes.c_void_p()
                ctypes.windll.oleacc.AccessibleObjectFromWindow(
                    int(hwnd), OBJID_CLIENT, ctypes.byref(guid), ctypes.byref(acc))
            self._a11y_woken.add(hwnd)
        try:
            uia.SetGlobalSearchTimeout(2)
            root = uia.ControlFromHandle(int(hwnd))
        except Exception:
            return out, refs
        INTERACT = {"ButtonControl", "HyperlinkControl", "EditControl", "ListItemControl",
                    "TabItemControl", "MenuItemControl", "ComboBoxControl", "CheckBoxControl",
                    "RadioButtonControl", "TreeItemControl", "SplitButtonControl", "TextControl",
                    "DocumentControl"}
        # Editable surfaces (Notepad/Word/RichEdit) are DocumentControl/EditControl with
        # an EMPTY name+value when blank — must still be listed so the agent can type.
        EDITABLE = {"EditControl", "DocumentControl"}
        idx = [0]
        seen_names = set()

        t0 = time.monotonic()
        wrect = (0, 0, 0, 0)
        with _suppress():
            wrect = win32gui.GetWindowRect(hwnd)

        def walk(c, depth):
            # Depth 40 reaches Chromium/React trees (Claude/Discord nest 20-40 deep;
            # 14 stopped at the titlebar). The 4s time budget bounds the cross-process
            # COM cost on huge trees so a round never hangs the agent.
            if depth > 40 or idx[0] > 90 or (time.monotonic() - t0) > 4.0:
                return
            try:
                children = c.GetChildren()
            except Exception:
                children = []
            for ch in children:
                try:
                    ct = ch.ControlTypeName or ""
                    nm = (ch.Name or "").strip()
                    if ct == "DocumentControl":
                        # Chromium/Electron: the web content's a11y tree starts at the
                        # Document and nests 20-40 levels deep (React). A flat depth
                        # cap of 14 stopped above the real UI (Claude showed only the
                        # 4 titlebar buttons) — reset the budget inside the document.
                        depth = 0
                    val = ""
                    # NEVER read the value of a password field — UIA usually masks it,
                    # but custom/Electron controls may not; defense-in-depth so a
                    # secret never reaches the cloud LLM (parity with _OBSERVE_JS).
                    _is_pw = False
                    with contextlib.suppress(Exception):
                        _is_pw = bool(ch.IsPassword)
                    if not _is_pw:
                        try:
                            vp = ch.GetValuePattern()
                            if vp:
                                val = (vp.Value or "")[:40]
                        except Exception:
                            pass
                    if ct in EDITABLE and not nm:
                        # Unnamed empty editable: real text areas (Notepad's RichEdit)
                        # have a real on-screen rectangle. Chromium's webview wrapper
                        # is also an unnamed 'Document' but with an EMPTY rect — it
                        # can't take input; listing it as '(text area)' lured the
                        # model into clicking/typing it forever ('-> miss' loops).
                        _real = False
                        with contextlib.suppress(Exception):
                            _br = ch.BoundingRectangle
                            _w, _h = (_br.right - _br.left), (_br.bottom - _br.top)
                            _wa = max(1, (wrect[2] - wrect[0]) * (wrect[3] - wrect[1]))
                            # Real editors have a real rect but NOT the whole window:
                            # Chromium's unnamed webview Document spans 100% of the
                            # window (Notepad's editor ≈ 60%) — that's a wrapper.
                            _real = bool(_br and _w > 40 and _h > 20
                                         and (_w * _h) / _wa < 0.85)
                        if not _real:
                            walk(ch, depth + 1)
                            continue
                    if ct in INTERACT and (nm or val or ct in EDITABLE):
                        # Empty editable surfaces get a synthetic name so the LLM
                        # knows it's the place to type.
                        disp = nm or (val and "") or ("(text area)" if ct in EDITABLE else "")
                        key = f"{ct}|{(nm or disp)[:40]}"
                        if key not in seen_names:
                            seen_names.add(key)
                            # Rough on-window position — lets the model tell a chat
                            # COMPOSER (bottom of the window) from a SEARCH box (top),
                            # which it confused in Zalo (typed the message into search).
                            pos = ""
                            try:
                                br = ch.BoundingRectangle
                                if br and br.bottom > br.top and wrect[3] > wrect[1]:
                                    rel = ((br.top + br.bottom) / 2 - wrect[1]) / (wrect[3] - wrect[1])
                                    pos = "top" if rel < 0.25 else ("bottom" if rel > 0.72 else "")
                            except Exception:
                                pos = ""
                            i = idx[0]; idx[0] += 1
                            out.append({"id": i, "type": ct.replace("Control", ""),
                                        "name": disp[:60], "value": val, "pos": pos})
                            refs[i] = ch
                    walk(ch, depth + 1)
                except Exception:
                    continue
        walk(root, 0)
        return out, refs

    def _act_on_ref(self, ctrl, action: str, text: str = "") -> bool:
        """Invoke / set value on a UIA control object — no cursor, no focus steal."""
        try:
            if action == "type":
                # Verified on Win11 Notepad (RichEditD2DPT / DocumentControl):
                # ValuePattern.SetValue and LegacyIAccessible.SetValue both work
                # focus-free. Try them, then native WM_SETTEXT, then per-char WM_CHAR.
                try:
                    vp = ctrl.GetValuePattern()
                    if vp:
                        vp.SetValue(text)
                        return True
                except Exception:
                    pass
                try:
                    lp = ctrl.GetLegacyIAccessiblePattern()
                    if lp:
                        lp.SetValue(text)
                        return True
                except Exception:
                    pass
                nh = 0
                try:
                    nh = int(getattr(ctrl, "NativeWindowHandle", 0) or 0)
                except Exception:
                    nh = 0
                if nh:
                    try:
                        win32gui.SendMessage(nh, 0x000C, 0, str(text))  # WM_SETTEXT
                        return True
                    except Exception:
                        pass
                    try:
                        for chx in str(text):  # last resort: post characters
                            self._post_wm_char(nh, chx)   # surrogate-pair aware (emoji safe)
                        return True
                    except Exception:
                        pass
                return False
            # click-like. ORDER MATTERS by app type:
            #  * Chromium/Electron (Claude, Discord…): UIA Invoke fires only a DOM
            #    'click' — Radix/React menus (Claude's model picker) open on
            #    POINTERDOWN, so Invoke silently does nothing. A background mouse
            #    message to the renderer child = real pointer events = works like a
            #    human click. So: coordinate click FIRST, patterns as fallback.
            #  * Win32/UWP apps: patterns are exact and verified — keep them first.
            _chromium = False
            with _suppress():
                _chromium = "Chrome_WidgetWin" in (win32gui.GetClassName(self._primary_window()) or "")
            def _coord_click() -> bool:
                try:
                    r = ctrl.BoundingRectangle   # SCREEN pixels
                    sx = (int(r.left) + int(r.right)) // 2
                    sy = (int(r.top) + int(r.bottom)) // 2
                    if r.right <= r.left or r.bottom <= r.top:
                        return False
                    top = self._primary_window()
                    with _suppress():
                        nh = int(getattr(ctrl, "NativeWindowHandle", 0) or 0)
                        if nh:
                            top = win32gui.GetAncestor(nh, 2) or top  # GA_ROOT
                    return self._click_screen_point(top, sx, sy).get("success", False)
                except Exception:
                    return False
            if _chromium and _coord_click():
                return True
            for getter, method in (("GetInvokePattern", "Invoke"),
                                   ("GetSelectionItemPattern", "Select"),
                                   ("GetTogglePattern", "Toggle"),
                                   ("GetExpandCollapsePattern", "Expand")):
                try:
                    g = getattr(ctrl, getter, None)
                    if not g:
                        continue
                    p = g()
                    if p:
                        getattr(p, method)()
                        return True
                except Exception:
                    continue
            # last resort: background click at the control's center (screen coords)
            try:
                return _coord_click()
            except Exception:
                return False
        except Exception:
            return False

    def _focused_title(self) -> str:
        try:
            h = self._primary_window()
            return win32gui.GetWindowText(h) if h else ""
        except Exception:
            return ""

    def _exec_action(self, act: Dict[str, Any], refs: Dict[int, Any], launched: set) -> str:
        """Execute ONE action; return a short human-readable result line."""
        a = str(act.get("action") or "").lower()
        if a == "open_app":
            app = (act.get("app") or "").strip()
            if app.lower() in launched:
                return f"{app} already open (skip relaunch)"
            launched.add(app.lower())
            r = self.launch(app, act.get("args") or "", "")
            return f"open_app {app} -> {'ok' if r.get('success') else r.get('error')}"
        if a == "open_url":
            if "__url__" in launched:
                # A browser is already open — don't spawn another window; the agent
                # should interact with the page that's already loaded.
                return "browser already open (interact with the current page, do not re-open)"
            launched.add("__url__")
            r = self.launch(act.get("app") or "chrome", "", act.get("url") or "")
            return f"open_url {str(act.get('url'))[:50]} -> {'ok' if r.get('success') else r.get('error')}"
        if a == "click":
            idv = act.get("id", -1)
            ref = None
            if str(idv).lstrip("-").isdigit():
                ref = refs.get(int(idv))
            else:
                # The model sometimes passes the control NAME (e.g. "Nine") instead of
                # the numeric [id]. Resolve it by matching a control's name so the click
                # still lands (keypad buttons "One".."Nine", "Plus", "Equals", …).
                q = str(idv).strip().lower()
                for rc in refs.values():
                    try:
                        if (getattr(rc, "Name", "") or "").strip().lower() == q:
                            ref = rc
                            break
                    except Exception:
                        continue
            ok = self._act_on_ref(ref, "click") if ref is not None else False
            return f"click[{idv}] -> {'ok' if ok else 'miss'}"
        if a == "type":
            idv = act.get("id", -1)
            ref = refs.get(int(idv)) if str(idv).lstrip("-").isdigit() else None
            txt = act.get("text") or ""
            append = bool(act.get("append"))
            ok = False
            if ref is not None:
                # Click the intended element FIRST, like a human (background pointer
                # events — no OS focus change), so the app's internal/DOM focus lands
                # in the right box before the keystrokes. Without this, WM_CHAR went
                # to whatever happened to hold focus — which once sent the agent's
                # question into the USER'S OWN open conversation. (UIA SetFocus was
                # rejected: it can ACTIVATE the window = focus steal.)
                clicked_ok = False
                with _suppress():
                    br = ref.BoundingRectangle
                    if br and br.right > br.left and br.bottom > br.top:
                        top = self._primary_window()
                        nh = int(getattr(ref, "NativeWindowHandle", 0) or 0)
                        if nh:
                            top = win32gui.GetAncestor(nh, 2) or top  # GA_ROOT
                        clicked_ok = self._click_screen_point(
                            top, (br.left + br.right) // 2,
                            (br.top + br.bottom) // 2).get("success", False)
                        if clicked_ok:
                            time.sleep(0.25)
                ok = self._act_on_ref(ref, "type", txt)
                if not ok and clicked_ok:
                    ok = self.type_text(txt, append=append).get("success")
                elif not ok:
                    # The addressed element couldn't even be clicked (empty rect =
                    # wrapper/ghost element). Blind-typing here sprays keystrokes
                    # into whatever holds focus — that's how text once leaked into
                    # the user's own conversation. Refuse instead.
                    return f"type '{txt[:30]}' -> miss (ô [{idv}] không nhận được — chọn ô khác)"
                # VERIFY the text landed in THIS element (readback via UIA). If the
                # element is readable and our text is NOT there, the keystrokes went
                # to the wrong place — report a miss so the plan aborts instead of
                # pressing Enter into someone else's composer. SKIP for password
                # fields: UIA masks their Value (returns "") so the readback would
                # ALWAYS report a false miss → the agent could never fill a login
                # password. We clicked the right element + typed, so trust it.
                _pw = False
                with _suppress():
                    _pw = bool(ref.IsPassword)
                if ok and not _pw:
                    val = None
                    for getter in ("GetValuePattern", "GetLegacyIAccessiblePattern"):
                        with _suppress():
                            p = getattr(ref, getter)()
                            v = getattr(p, "Value", None)
                            if isinstance(v, str):
                                val = v
                                break
                    if isinstance(val, str) and txt.strip() and txt.strip()[:20] not in val:
                        return f"type '{txt[:30]}' -> miss (chữ không vào đúng ô [{idv}])"
            else:
                # No target id → only safe for plain editor windows (Notepad-style).
                ok = self.type_text(txt, append=append).get("success")
            return f"type '{txt[:30]}' -> {'ok' if ok else 'miss'}"
        if a == "key":
            self.press_key(act.get("key") or "enter")
            return f"key {act.get('key')}"
        if a == "scroll":
            self._scroll(str(act.get("dir") or "down"))
            return f"scroll {act.get('dir') or 'down'}"
        if a == "wait":
            time.sleep(float(act.get("seconds") or 1.5))
            return "wait"
        if a == "click_text":
            # Click on VISIBLE TEXT read by OCR — works on ANY app/web even when UIA
            # doesn't expose the control (Electron without a11y, web, canvases, etc.).
            _fold = _fold_vn   # module-level (diacritic + đ/Đ fold), testable
            q = _fold((act.get("text") or act.get("name") or "").strip())
            if not q:
                return "click_text (no text)"
            def _try(rows) -> bool:
                for r in (rows or []):
                    if q in _fold(r.get("text") or ""):
                        # Restore the EXACT capture mapping the OCR text came from (the
                        # live stream may have overwritten _last_render) so the click
                        # lands precisely.
                        snap = getattr(self, "_ocr_render", None)
                        if snap:
                            self._last_render = snap
                        self.click(r["cx"], r["cy"])
                        return True
                return False
            if _try(getattr(self, "_last_ocr", None)):
                return f"click_text '{q[:30]}' -> ok"
            # Not in the round's snapshot — the screen may have JUST changed (e.g. a
            # previous action in this same plan opened a menu, so its options weren't
            # captured yet). Re-OCR the live screen once and retry before giving up.
            fresh = self._ocr_screen()
            self._last_ocr = fresh
            if _try(fresh):
                return f"click_text '{q[:30]}' -> ok (sau khi chụp lại màn hình)"
            return f"click_text '{q[:30]}' -> not found on screen"
        return f"(unknown action {a})"

    def _ocr_screen(self):
        """OCR the current captured frame via built-in Windows OCR (no model / no
        subscription) → [{text, cx, cy}] in CANVAS-normalized coords. Gives the agent
        a 'vision-lite' READ of any visible app/web (counts, results, labels) and the
        ability to CLICK text UIA can't see. Runs in a short worker thread to avoid
        COM-apartment conflicts; fully guarded."""
        if Image is None:
            return []
        img = self.capture()
        if img is None:
            return []
        # Snapshot the canvas→window mapping FROM THIS capture, so click_text maps its
        # OCR coords through the SAME frame — the live /frame stream calls capture()
        # ~10×/sec and overwrites self._last_render, which otherwise made click_text
        # land in the wrong place (e.g. hit 'Friends' instead of 'Nitro').
        self._ocr_render = dict(self._last_render or {})
        out = []
        def _worker():
            try:
                import io as _io, asyncio as _aio
                import winsdk.windows.media.ocr as wocr
                import winsdk.windows.graphics.imaging as wimg
                import winsdk.windows.storage.streams as wstr
                import winsdk.windows.globalization as wglob
                buf = _io.BytesIO(); img.save(buf, "PNG"); data = buf.getvalue()
                async def _run():
                    st = wstr.InMemoryRandomAccessStream()
                    wr = wstr.DataWriter(st); wr.write_bytes(data); await wr.store_async(); st.seek(0)
                    dec = await wimg.BitmapDecoder.create_async(st)
                    sb = await dec.get_software_bitmap_async()
                    eng = wocr.OcrEngine.try_create_from_user_profile_languages() or \
                          wocr.OcrEngine.try_create_from_language(wglob.Language("en-US"))
                    if not eng:
                        return []
                    res = await eng.recognize_async(sb)
                    W, H, rows = float(CANVAS_W), float(CANVAS_H), []
                    for line in res.lines:
                        words = list(line.words)
                        if not words:
                            continue
                        xs = [w.bounding_rect.x for w in words]
                        ys = [w.bounding_rect.y for w in words]
                        xe = [w.bounding_rect.x + w.bounding_rect.width for w in words]
                        ye = [w.bounding_rect.y + w.bounding_rect.height for w in words]
                        rows.append({"text": line.text,
                                     "cx": (min(xs) + max(xe)) / 2 / W,
                                     "cy": (min(ys) + max(ye)) / 2 / H})
                    return rows
                out.extend(_aio.run(_run()))
            except Exception:
                pass
        th = threading.Thread(target=_worker, daemon=True)
        th.start(); th.join(8)
        return out

    def run_agent(self, command: str, llm, max_steps: int = 8) -> Dict[str, Any]:
        """Autonomous agent (runs in ONE thread for COM coherence). Each ROUND the
        LLM sees the current screen + state and returns a PLAN of several actions to
        run in sequence — like a human who opens an app once then acts fast — instead
        of one slow action per LLM call. Tracks open apps (no relaunch loop), detects
        being stuck (screen unchanged), and supports long tasks via many rounds.
        `llm` is a SYNC callable str->str. Control is by element NAME (UIA), no vision."""
        import json as _json, re as _re
        self.active_surface = "app"  # native command -> stream the app window
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except Exception:
            pass
        if self.user_desktop:
            self._start_focus_guard()   # keep the user's focus the WHOLE session
        history: List[str] = []
        launched: set = set()
        action_counts: Dict[str, int] = {}   # anti-loop: count of each action sig
        llm_fails = 0                          # consecutive model errors (retry, don't abort)
        last_screen_sig = None
        stuck = 0
        self.cancelled = False; self.busy = True   # Stop button can abort mid-loop
        self._prune_dead_windows()                  # drop closed HWNDs (long-lived shared desktop)
        opened_round = -99                          # round an app was last launched (grace window)
        last_typed = None; sent_texts: Dict[str, int] = {}  # text -> round it was sent
                                                    # (anti-spam, EXPIRES after 2 rounds:
                                                    #  re-sending after a state change —
                                                    #  new chat, model switched — is legit)
        clicked_names: Dict[str, int] = {}          # run-wide click log (anti re-click:
                                                    # re-pressing 'New chat' resets state)
        # Cross-command continuity: what the AI did in PREVIOUS commands, so a follow-up
        # continues in the SAME app/window instead of re-opening (general continuation).
        if not hasattr(self, "app_history"):
            self.app_history = []
        prev_ctx = " · ".join(self.app_history[-3:])
        # Baseline of existing windows BEFORE this command → any window that appears
        # during the command is the AI's (generic: catches Explorer's folder window,
        # Office, Electron, anything — no per-app title/pid matching needed).
        if self.user_desktop:
            self._cmd_baseline = set(self._all_user_windows())
        rounds = max(2, min(14, max_steps))  # each round runs up to ~6 actions
        # TOTAL wall-clock budget — a slow/throttled cloud LLM can make rounds drag,
        # and the synchronous /agent request (+ the user) would hang. Return honestly
        # when spent. ~3.5 min covers a normal multi-round native task.
        _budget = 210.0
        _t0 = time.monotonic()
        unproductive = 0   # consecutive rounds where NO action succeeded ("-> ok").
                           # Catches the "screen wiggles each round (so `stuck` keeps
                           # resetting) but every action is blocked/misses" flail that
                           # otherwise burns the whole budget before failing honestly.
        for rnd in range(rounds):
            if self.cancelled:
                self.busy = False
                return {"success": True, "rounds": rnd, "history": history,
                        "summary": "⏹ Đã dừng theo yêu cầu."}
            if time.monotonic() - _t0 > _budget:
                self.busy = False
                return {"success": False, "rounds": rnd, "history": history,
                        "summary": "⚠ Chưa hoàn thành — quá thời gian cho phép (mô hình phản hồi chậm)."}
            self._adopt_new_windows()   # track + hide any app window that opened
            self._check_user_summon()   # user clicked the hidden app's taskbar icon?
            # If the app being operated was CLOSED mid-task (e.g. by the user), STOP
            # and ASK instead of silently relaunching or flailing ("có tắt thì hỏi
            # lại người dùng").
            if rnd > 0 and (self.adopted_windows or launched):
                _alive = []
                with self._lock:
                    _alive = [h for h in self.ai_windows if win32gui.IsWindow(h)]
                if not _alive and not self._primary_window():
                    self.busy = False
                    return {"success": False, "rounds": rnd, "history": history,
                            "ask_user": True,
                            "summary": "⚠ Cửa sổ ứng dụng đã bị đóng giữa chừng nhiệm vụ. "
                                       "Bạn muốn tôi mở lại app và làm tiếp không?"}
            # Titles of windows currently open/tracked → lets the agent CONTINUE in an
            # already-open app rather than re-launching it.
            open_titles = []
            with _suppress():
                for _h in list(self.ai_windows):
                    if win32gui.IsWindow(_h):
                        _t = (win32gui.GetWindowText(_h) or "").strip()
                        if _t:
                            open_titles.append(_t[:40])
            controls, refs = self._uia_interactables()
            title = self._focused_title()
            # Show the WHOLE list (up to the walker's cap). Truncating at 55 hid the
            # very controls the task needed (Claude's composer was [62], the Model
            # button [65] — the planner never saw them and clicked sidebar noise).
            ctrl_lines = "\n".join(
                f'[{c["id"]}] {c["type"]} "{c["name"]}"'
                + (f' = "{c["value"]}"' if c["value"] else "")
                + (f' @{c["pos"]}' if c.get("pos") else "")
                for c in controls[:90]) or "(no interactable controls visible yet)"
            # Surface answer-bearing text (counts/numbers) so even a weak model can
            # READ the result ("9 items", "143 bạn bè") instead of clicking forever.
            _facts = [c["name"] for c in controls
                      if _re.search(r"\d", c.get("name","")) and
                      _re.search(r"item|mục|file|bạn|friend|kết quả|ket qua|result|tin nhắn|message|%", c.get("name",""), _re.I)]
            facts_line = ("\nVISIBLE NUMBERS (may be the answer — read these, don't click): "
                          + " | ".join(_facts[:6])) if _facts else ""
            # OCR the visible frame → the agent can READ + click text UIA can't see.
            # OCR feeds click_text (operate things UIA doesn't expose — custom Electron
            # dropdowns/menus like the Claude model picker, web widgets). Run it when
            # UIA is sparse OR the focused app is Chromium/Electron (which exposes some
            # controls but NOT its custom UI). Pure Win32 rich-control apps (Notepad,
            # Word, Explorer) skip OCR for speed.
            _prim = self._primary_window()
            _is_chromium = False
            with _suppress():
                _is_chromium = "Chrome_WidgetWin" in (win32gui.GetClassName(_prim) or "")
            # OCR only when UIA is sparse or we're stuck — the deep walk now exposes
            # Chromium/Electron trees fully (Claude: 100+ controls), so the old
            # always-OCR-for-chromium rule just added 1-2s per round for nothing.
            ocr_rows = self._ocr_screen() if (len(controls) < 12 or stuck >= 1) else []
            self._last_ocr = ocr_rows
            ocr_line = ("\nTEXT VISIBLE ON SCREEN (OCR — you can READ these to answer, and "
                        "CLICK any of them with action click_text:\"<the text>\"):\n"
                        + "\n".join("• " + (r.get("text") or "")[:80] for r in ocr_rows[:35])) if ocr_rows else ""
            # Signature over a WIDE slice of the tree (names+values). The old first-10
            # version saw only the static sidebar in apps like Zalo — opening a chat
            # changed nothing in the sig, so real progress was misread as 'stuck' and
            # the agent kept re-clicking / gave up while the click had WORKED.
            screen_sig = f"{title}|{len(controls)}|" + str(hash(tuple(
                (c["name"][:24], c["value"][:16]) for c in controls[:45])))
            if screen_sig == last_screen_sig:
                stuck += 1
            else:
                stuck = 0
                action_counts.clear()  # screen changed = progress → forget repeat-history
                                       # (so legitimate repeated clicks like a keypad digit
                                       #  aren't wrongly blocked; only true no-progress loops are)
            last_screen_sig = screen_sig
            prompt = (
                "You are an autonomous computer-use agent on an ISOLATED Windows desktop "
                "(your own — separate from the user). Work efficiently like a human: open "
                "an app/site ONCE, then do several actions in a row.\n\n"
                f"GOAL: {command}\n\n"
                + (f"Earlier this session you did: {prev_ctx}\n" if prev_ctx else "")
                + f"Windows ALREADY OPEN now (to CONTINUE a task, operate one of these "
                f"directly — only open_app if you truly need a NEW app): {open_titles or '(none)'}\n"
                f"STATE — apps/sites already opened this session: "
                f"{sorted(x for x in launched if x != '__url__') or '(none)'}"
                + (" + a browser" if "__url__" in launched else "") + "\n"
                + (f"CLICKED BUTTONS so far (do NOT click these again): "
                   f"{ {k: v for k, v in clicked_names.items()} }\n" if clicked_names else "")
                + f"Focused window: \"{title or '(none)'}\"\n"
                f"What you've done so far:\n" + ("\n".join(history[-8:]) or "(nothing yet)") + "\n\n"
                f"Interactable controls on the focused window NOW:\n{ctrl_lines}\n"
                + facts_line + ocr_line + "\n\n"
                + ("NOTE: the screen has NOT changed since your last actions — your plan "
                   "isn't working. Try a DIFFERENT approach (different control id, scroll, "
                   "or a direct URL). Do NOT repeat the same failing action.\n\n" if stuck >= 1 else "")
                + "Return ONE JSON object — a PLAN of the next actions to run in order:\n"
                '{"plan":[{"action":"open_app|open_url|click|click_text|type|key|scroll|wait",'
                '"app":"<name>","url":"<https url>","id":<control id>,"text":"<text>",'
                '"append":<true|false>,"key":"<enter|tab|..>","dir":"up|down","seconds":<n>}],'
                '"done":<true|false>,"summary":"<short status in Vietnamese>"}\n\n'
                "RULES:\n"
                "- Put 1-6 actions in 'plan' that you can do BEFORE needing to see the screen "
                "again (e.g. [open_app, wait] then next round you click a control).\n"
                "- Do NOT re-open an app/site already in STATE.\n"
                "- IMPORTANT — APP vs WEB: if the GOAL names a DESKTOP APPLICATION "
                "(e.g. Discord, Zalo, Telegram, Messenger, Spotify, Steam, Word, Excel, "
                "PowerPoint, Notepad, Outlook, Slack, VS Code, OBS…), you MUST use "
                "open_app with that app name — the system locates and launches the "
                "INSTALLED app on this machine (signed into the user's real account). "
                "NEVER open the app's website in a browser as a substitute. Then operate "
                "it via its [id] controls (type/click).\n"
                "- Use open_url ONLY for genuine websites / web search / online video "
                "(YouTube search: https://www.youtube.com/results?search_query=...). After "
                "it loads, click a result by its [id].\n"
                "- If open_app fails (App not found), the app likely isn't installed — say "
                "so in summary; do NOT silently fall back to its website.\n"
                "- COMPOSE content from the INTENT — do NOT type the instruction verbatim. "
                "E.g. 'nhắn lời chào lưu manh' means WRITE a short cheeky/playful greeting "
                "yourself (e.g. 'Ê thằng quỷ, lặn đâu mất tiêu vậy 😏') and send THAT — never "
                "literally type the words 'lời chào lưu manh'. 'viết email xin nghỉ' = compose "
                "a real email body, etc.\n"
                "- MULTI-STEP (e.g. send a chat message) — you MUST finish ALL steps, do NOT "
                "stop after opening the chat: (1) click the target person/channel [id]; "
                "(2) click the message box (Edit/Document, often '(text area)' or empty); "
                "(3) type the COMPOSED message; (4) key 'enter' to SEND ONCE; (5) RE-OBSERVE and "
                "confirm the message actually appears in the conversation, then done=true. "
                "Opening the chat is NOT 'done'. CRITICAL: send the message ONLY ONCE — after "
                "you pressed enter, do NOT type or send the same message again (it spams the "
                "chat). If you're unsure it sent, scroll the conversation to LOOK for it rather "
                "than re-sending.\n"
                "- A click only counts if the screen/controls then change; if a control "
                "you need is NOT in the list, it isn't exposed — try scrolling or report "
                "that the app doesn't expose it (don't loop the same click).\n"
                "- NEVER use alt+tab / window-switching keys — the target window is "
                "already focused for input on this desktop; alt+tab does nothing here.\n"
                "- Do NOT click the SAME [id] more than twice; if it didn't help, pick a "
                "DIFFERENT control or finish.\n"
                "- To READ/COUNT something (files in a folder, a number, friend count): "
                "look in the controls list AND in 'TEXT VISIBLE ON SCREEN' (OCR) — e.g. "
                "'9 items', '143 friends' — put the answer in 'summary' and set done=true. "
                "Don't click aimlessly; if the info is visible, just report it.\n"
                "- PREFER clicking by [id] from the controls list (exact). Use click_text "
                "ONLY for targets NOT in the controls list — it's OCR-based and can miss "
                "small glyphs (e.g. a single digit).\n"
                "- For a CALCULATOR / number keypad: each digit & operator is a Button in the "
                "controls list, e.g. [44] Button \"Nine\". Click using the NUMBER in brackets "
                "(id=44), NEVER the name. Plan the WHOLE sequence in one round — for 12+34 emit "
                "click id=<One>, id=<Two>, id=<Plus>, id=<Three>, id=<Four>, id=<Equals> using "
                "each button's bracket number. Do NOT use click_text for digits.\n"
                "- click_text:\"<exact visible text>\" clicks on ANYTHING you can SEE in the "
                "OCR list even if it's NOT a control (web links, Electron items, buttons, "
                "icons with labels). Use it when the control list is sparse/empty — this is "
                "how you operate apps that don't expose controls.\n"
                "- CUSTOM DROPDOWN / MODEL PICKER / MENU (Electron apps like Claude/Discord): "
                "(1) click the trigger button by [id] (e.g. 'Model: Sonnet 4.6'); (2) re-observe "
                "— the options appear as RadioButton/MenuItem controls; (3) click the desired "
                "option by [id] (e.g. 'Haiku 4.5'). If the options did NOT appear, the menu "
                "toggled closed — click the trigger ONCE more. Verify the trigger shows the new "
                "value before done=true. Use click_text only if no [id] exists.\n"
                "- DO THE GOAL'S STEPS IN ORDER. Do not send a message/question before the "
                "earlier steps (new session, switching mode/model…) are CONFIRMED done — "
                "sending first then changing settings does NOT apply retroactively.\n"
                "- EACH ROUND: check which GOAL steps are ALREADY DONE from the current "
                "controls/state (e.g. a button 'Model: Haiku 4.5' means the model is already "
                "switched; an empty new chat means the session exists). Work ONLY on the FIRST "
                "step that is NOT yet done. If every step shows evidence of being done and "
                "the answer/result is visible, set done=true and put it in summary.\n"
                "- Control [id] numbers are RE-NUMBERED every round — use ONLY ids from the "
                "CURRENT list above, never an id remembered from an earlier round.\n"
                "- PROTOCOL for ANY chat app (messenger / AI chat): (1) need a new "
                "conversation? click its new-chat/new-session button ONCE. (2) need a "
                "different model/setting? if the trigger button ALREADY shows the wanted "
                "value, skip; else click the trigger (e.g. 'Model: …'), re-observe, click the "
                "wanted option's [id], confirm the trigger label changed. (3) type the "
                "message into the composer Edit BY ITS [id], then key enter. (4) wait, "
                "re-observe, READ the reply from the Text controls and put it in summary "
                "with done=true.\n"
                "- NEVER re-click a button that already worked (see CLICKED BUTTONS). "
                "Re-clicking 'New chat'/'New session' style buttons DESTROYS progress: it "
                "resets the conversation and settings you already changed.\n"
                "- In File Explorer, open a folder by clicking its [id] in the left tree "
                "(e.g. 'Downloads'); the item count shows in a status Text ('N items').\n"
                "- To write into Notepad/editor: use type with the text. The text area "
                "appears in the controls list as a Document/Edit \"(text area)\" — pass its "
                "[id], or omit id to target the focused editor. type REPLACES the content; "
                "set \"append\":true to ADD to existing text (e.g. add a new line).\n"
                "- To type a chat MESSAGE/PROMPT you MUST pass the composer Edit's [id] "
                "(find it in the controls list, e.g. 'Write your prompt…'). NEVER type a "
                "message without an id — the keystrokes can land in the wrong box.\n"
                "- The MESSAGE COMPOSER is the Edit at the BOTTOM of the conversation "
                "(marked @bottom). A SEARCH box ('Tìm kiếm'/'Search', usually @top) is NOT "
                "a composer — NEVER type a message into a search field. To open a person's "
                "chat: click their name in the conversation list (or search → click the "
                "person in results), THEN type into the @bottom composer.\n"
                "- To SEND a typed message/prompt, use action key:enter. Do NOT click a "
                "send/submit button by [id] — ids are renumbered each round, a missed "
                "click loses the send, and Enter is what a human presses. After you have "
                "typed into the composer, the very NEXT action must be key:enter.\n"
                "- AFTER you have sent a question/message (see 'What you've done so far' — "
                "a type then key enter), do NOT type again. WAIT, then re-observe and READ "
                "the reply from the Text controls / OCR; put that reply in summary and set "
                "done=true. Re-typing the instruction is wrong — it was already sent.\n"
                "- COMPOSE follow-ups from context: a continuation like 'nhân kết quả với 3' "
                "means compute/ask using the PREVIOUS answer (e.g. send '10 nhân 3 = ?'), "
                "never type the instruction sentence verbatim.\n"
                "- Set done=true ONLY when the goal is fully achieved (you can see evidence)."
            )
            try:
                # ADAPTIVE PLANNER: only the VERY FIRST plan (round 0) uses the fast
                # model so a genuinely trivial task still finishes instantly; from round
                # 1 on we use the strong 123B planner. Users reported even "simple"
                # tasks looping/failing on the fast model (it re-clicked 'New chat' and
                # never touched the Model button), so don't keep it past the first try.
                # Also escalate immediately when stuck.
                if stuck >= 1 or rnd >= 1:
                    try:
                        raw = llm(prompt, model="devstral-2:123b-cloud") or ""
                    except TypeError:
                        raw = llm(prompt) or ""
                else:
                    raw = llm(prompt) or ""
                llm_fails = 0
            except Exception as exc:
                # A transient model timeout (devstral-123b is slow) must NOT abort the
                # whole task — retry next round; only give up after repeated failures,
                # and ALWAYS return a meaningful Vietnamese message ("trả lời khi xong").
                llm_fails += 1
                history.append(f"round{rnd}: model lỗi/timeout — thử lại ({str(exc)[:40]})")
                if llm_fails >= 2:
                    return {"success": False, "error": f"LLM error: {exc}", "history": history,
                            "summary": "Model điều khiển bị lỗi/timeout. Hãy thử lại; muốn "
                            "nhanh hơn, đặt biến SKEMI_MODEL_AGENT=minimax-m2:cloud."}
                time.sleep(1.0)
                continue
            raw = _re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=_re.IGNORECASE)
            obj = None
            m = _re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    obj = _json.loads(m.group(0))
                except Exception:
                    obj = None
            if obj is None:
                history.append(f"round{rnd}: no parseable plan")
                stuck = max(stuck, 1)   # escalate to the strong planner next round
                if stuck >= 2:
                    break
                continue
            plan = obj.get("plan")
            if not isinstance(plan, list):
                # single-action compatibility
                plan = [obj] if obj.get("action") else []
            # Generous cap: the summary often carries the ANSWER the user asked for
            # (e.g. the chatbot's reply) — 120 chars cut it off mid-sentence.
            summary = str(obj.get("summary") or "")[:500]
            round_productive = False   # set True if any action this round returns "-> ok"
            # Allow a longer chained sequence per round so a full keypad/typing run
            # (e.g. 999+1= = 6 clicks, or a phone number) completes in ONE round
            # instead of stalling across slow LLM rounds.
            for act in plan[:12]:
                if self.cancelled:
                    break
                # ANTI-LOOP (code-enforced): a weak text model tends to repeat the
                # same click forever. After 2 identical actions, refuse + tell it to
                # do something different — don't burn rounds on a no-op.
                sig = f"{str(act.get('action','')).lower()}:{act.get('id', act.get('url', act.get('app','')))}"
                action_counts[sig] = action_counts.get(sig, 0) + 1
                # Only block when we're genuinely STUCK (screen unchanged across rounds).
                # When the screen keeps changing (progress) counts are cleared each round,
                # so legitimate repeats (e.g. pressing the same keypad digit again) are fine.
                if stuck >= 1 and action_counts[sig] > 2 and str(act.get("action","")).lower() in ("click", "open_app", "open_url"):
                    history.append(f"round{rnd}: BLOCKED {sig} (lặp lại mà màn hình không đổi) — hãy chọn control KHÁC hoặc đọc kết quả đang hiển thị")
                    continue
                # ANTI-DUPLICATE-SEND: once a message text has been typed AND sent
                # (Enter), never type/send the SAME text again — otherwise a chat
                # greeting gets spammed 3-4× when the agent can't confirm the 1st send.
                _a = str(act.get("action","")).lower()
                _txt = str(act.get("text") or "").strip()
                if _a == "type" and _txt and (rnd - sent_texts.get(_txt, -99)) <= 2:
                    history.append(f"round{rnd}: bỏ qua — tin '{_txt[:24]}' vừa gửi rồi (không gửi lại)")
                    continue
                # ALREADY-TYPED → SEND, don't re-type. If this exact text was typed
                # OK earlier but not yet sent (e.g. the plan paired the type with a
                # click-to-send that missed, so Enter never ran), pressing Enter now
                # sends what's already in the box. Re-typing instead led to a
                # readback-miss loop ("chữ không vào đúng ô") on chat composers.
                if _a == "type" and _txt and _txt == last_typed:
                    self.press_key("enter")
                    sent_texts[_txt] = rnd; last_typed = None
                    history.append(f"round{rnd}: '{_txt[:24]}' đã gõ rồi → nhấn Enter để gửi")
                    continue
                # RUN-WIDE re-click cap: the same named button clicked 2+ times across
                # the whole task is almost always a planner loop — and re-pressing
                # state-resetting buttons ('New chat') destroys completed steps (it
                # reset the model the agent had just switched). Hard-skip the 3rd+.
                _cname = ""
                if _a in ("click", "click_text"):
                    _cname = str(act.get("text") or act.get("name") or "").strip().lower()
                    if not _cname and str(act.get("id", "")).lstrip("-").isdigit():
                        with _suppress():
                            _r = refs.get(int(act.get("id")))
                            _cname = (getattr(_r, "Name", "") or "").strip().lower()
                    # Short names (keypad digits 'Nine', 'Plus'…) repeat legitimately.
                    if _cname and len(_cname) > 5 and clicked_names.get(_cname, 0) >= 2:
                        history.append(f"round{rnd}: BỎ QUA click '{_cname[:30]}' — đã bấm "
                                       f"{clicked_names[_cname]} lần rồi, làm BƯỚC TIẾP THEO đi")
                        continue
                # Remember the user's REAL foreground window right before acting, so if
                # the action steals focus to an AI window we can give it straight back.
                _ufg = 0
                with _suppress():
                    _fg = win32gui.GetForegroundWindow()
                    if _fg and _fg not in self.ai_windows:
                        _ufg = _fg
                line = self._exec_action(act, refs, launched)
                self._reassert_user_focus(_ufg)   # never hold the user's focus
                history.append(f"round{rnd}: {line}")
                if "-> ok" in line:
                    round_productive = True
                if _cname and "-> ok" in line:
                    clicked_names[_cname] = clicked_names.get(_cname, 0) + 1
                if "not found on screen" in line or "-> miss" in line:
                    # The plan was built from a now-stale view (each click can change
                    # the screen). Marching on would click/type into the WRONG state —
                    # abort the rest, re-observe next round and re-plan from reality.
                    history.append(f"round{rnd}: dừng phần còn lại của kế hoạch — quan sát lại")
                    break
                if _a == "type" and _txt and "-> ok" in line:
                    last_typed = _txt
                elif _a == "key" and str(act.get("key","")).lower().strip("{}") in ("enter", "return") and last_typed:
                    sent_texts[last_typed] = rnd   # this text is now sent → don't repeat (soon)
                    last_typed = None
                if _a in ("open_app", "open_url") and "-> ok" in line:
                    opened_round = rnd   # start the "app is loading" grace window
                time.sleep(0.4)  # brief settle between chained actions
            if obj.get("done") is True:
                return {"success": True, "rounds": rnd + 1, "history": history,
                        "summary": summary or "Hoàn thành."}
            # PATIENCE: an app we just opened (esp. Electron like Discord/Slack/Teams)
            # can take 10-20s to render its window + expose controls. While in that
            # grace window with few controls, WAIT + keep re-adopting/​waking — do NOT
            # bail as "stuck" or let the model give up prematurely.
            if (rnd - opened_round) <= 4 and len(controls) < 4:
                history.append(f"round{rnd}: chờ ứng dụng tải xong…")
                stuck = 0
                time.sleep(2.2)
                continue
            # THRASH GUARD: a round where nothing succeeded counts as unproductive.
            # Any real progress (a click/type/open/key that returned "-> ok", or a
            # finished task) resets it. Bail honestly after 6 dead rounds instead of
            # flailing through the whole round/time budget — this is the "làm được
            # chút rồi loay hoay rất lâu, cuối cùng vẫn không xong" case.
            if round_productive:
                unproductive = 0
            else:
                unproductive += 1
            if unproductive >= 6 and stuck < 3:
                return {"success": False, "rounds": rnd + 1, "history": history,
                        "summary": "⚠ Chưa hoàn thành — đã thử nhiều cách nhưng không "
                                   "thao tác được gì thêm. " + (summary or "")[:160]}
            if stuck >= 3:
                # HONEST failure: don't return the model's optimistic in-progress
                # summary ('Đang mở menu…') as if it succeeded — the frontend showed
                # that with a ✅ while nothing had happened.
                return {"success": False, "rounds": rnd + 1, "history": history,
                        "summary": "⚠ Chưa hoàn thành: " + (summary or "thao tác") +
                        " — màn hình không phản hồi sau nhiều lần thử."}
            time.sleep(0.6)  # let the UI settle before the next observation
        return {"success": False, "rounds": rounds, "history": history,
                "summary": "⚠ Chưa hoàn thành — đã chạy hết số lượt cho phép mà chưa "
                           "thấy bằng chứng hoàn tất."}

    def _scroll(self, direction: str) -> None:
        try:
            h = self._primary_window()
            if not h:
                return
            delta = 120 if direction == "up" else -120
            # WM_MOUSEWHEEL must go to the child under the pointer WITH screen coords
            # in lParam — Chromium routes the wheel by those coords; a zero lParam to
            # the top-level frame is ignored (scroll 'did nothing' on Electron apps).
            rect = win32gui.GetWindowRect(h)
            sx, sy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            leaf = self._leaf_at_point(h, sx, sy)
            lp = (int(sy) & 0xFFFF) << 16 | (int(sx) & 0xFFFF)
            win32gui.PostMessage(leaf, 0x020A, (delta & 0xFFFF) << 16, lp)  # WM_MOUSEWHEEL
        except Exception:
            pass

    # ----- WEB tasks (CDP / Playwright — for every website, like a human) ---
    def run_web(self, command: str, llm, start_url: str = "") -> Dict[str, Any]:
        """Drive a real Chrome via CDP for web tasks (UIA can't see web content).
        Launches the AI's browser once (off-screen, own profile), tracks its window
        for streaming, and runs the DOM-level agent loop. No mouse/focus steal."""
        self.active_surface = "web"  # web command -> stream the page screenshot
        self.cancelled = False; self.busy = True   # Stop button can abort the web loop
        try:
            import skemi_web_agent as _wa
        except Exception as exc:
            return {"success": False, "error": f"web engine unavailable: {exc}"}
        with self._lock:
            if getattr(self, "web", None) is None:
                self.web = _wa.WebController(off_screen=True)
                r = self.web.launch(start_url or "about:blank")
                if not r.get("success"):
                    self.web = None
                    return {"success": False, "error": r.get("error", "chrome launch failed")}
                # Track the browser window so /iso/frame streams the page.
                if r.get("hwnd"):
                    if r["hwnd"] not in self.ai_windows:
                        self.ai_windows.append(int(r["hwnd"]))
                time.sleep(1.0)
                # Start the dedicated live-capture thread so the stream stays live
                # (keeps refreshing last_shot) instead of freezing after the task.
                with contextlib.suppress(Exception):
                    self.web.start_stream()
        # SESSION AWARENESS: feed what the AI did in previous commands so it stays
        # in-context (knows a video is already playing, acts in the SAME tab).
        if not hasattr(self, "web_history"):
            self.web_history = []
        ctx = " · ".join(self.web_history[-3:])
        result = self.web.run_web_task(command, llm, start_url=start_url, max_rounds=8, context=ctx)
        # remember this command's outcome for the next one
        with contextlib.suppress(Exception):
            self.web_history.append(f"{command} → {str(result.get('summary') or '')[:80]}")
            self.web_history = self.web_history[-8:]
        # Tell the user how to get their own account if we had to use a guest
        # profile (their browser was already open, so its real profile was locked).
        mode = getattr(self.web, "profile_mode", "guest")
        result["profile_mode"] = mode
        if mode == "guest" and result.get("success"):
            note = "  (Mẹo: đóng Chrome đang mở để lần sau AI dùng đúng tài khoản của bạn.)"
            result["summary"] = (str(result.get("summary") or "") + note)[:240]
        return result

    def cancel(self) -> Dict[str, Any]:
        """Stop button: abort the currently-running agent loop ASAP. The run_agent /
        run_web loops check self.cancelled between every action and bail out."""
        self.cancelled = True
        with contextlib.suppress(Exception):
            if getattr(self, "web", None) is not None:
                self.web.cancelled = True   # the web loop checks this too
        return {"success": True, "cancelled": True, "was_busy": bool(self.busy)}

    # ----- teardown --------------------------------------------------------
    def _restore_adopted(self) -> None:
        """RESCUE pass for the USER's own (adopted) windows. Normally we never touch
        their placement at all — but earlier sessions (or a crash mid-stash) can have
        left one marooned off-screen / WS_EX_NOACTIVATE'd. If so, clear the style and
        bring it to a sane centred rect; windows that look normal are left alone.
        Their processes are never killed (not in self.processes)."""
        GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
        for h in list(getattr(self, "adopted_windows", set())):
            with _suppress():
                if not win32gui.IsWindow(h):
                    continue
                if win32gui.IsIconic(h):
                    # Minimized = the user's own choice. Its GetWindowRect reports
                    # iconic off-screen coords (~-32000) but that is NOT "marooned" —
                    # un-minimizing + centring it here would pop the user's app open
                    # on session close. Leave it exactly as it is.
                    continue
                ex = win32gui.GetWindowLong(h, GWL_EXSTYLE)
                if ex & WS_EX_NOACTIVATE:
                    win32gui.SetWindowLong(h, GWL_EXSTYLE, ex & ~WS_EX_NOACTIVATE)
                # Judge "marooned" by the NORMAL (restored) position, not the current
                # rect — a real stray has its rcNormalPosition itself off-screen.
                pl = win32gui.GetWindowPlacement(h)
                marooned = bool(pl and pl[4][0] <= -20000)
                if marooned:
                    sw = win32api.GetSystemMetrics(0); sh = win32api.GetSystemMetrics(1)
                    w, hh = min(1280, sw - 120), min(800, sh - 120)
                    win32gui.SetWindowPos(h, 0, (sw - w) // 2, (sh - hh) // 2, w, hh,
                                          win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER)
                    win32gui.ShowWindow(h, 4)   # SW_SHOWNOACTIVATE

    def close(self) -> None:
        with _suppress():
            self._stop_focus_guard()   # stop the focus-restore thread
        with _suppress():
            self._restore_adopted()    # hand the user's own windows back where they were
        with _suppress():
            if getattr(self, "web", None) is not None:
                self.web.kill()
                self.web = None
        with self._lock:
            pids = list(self.processes)
        for pid in pids:
            with _suppress():
                h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                if h:
                    win32api.TerminateProcess(h, 0)
                    win32api.CloseHandle(h)
        with _suppress():
            if self.hdesk:
                self.hdesk.CloseDesktop()
        self.hdesk = None

    def info(self) -> Dict[str, Any]:
        wins = [h for h in self._enum_windows() if self._is_app_window(h)]
        return {"id": self.name, "label": self.label,
                "windows": len(wins), "processes": len(self.processes),
                "created_at": self.created_at}


class _suppress:
    def __enter__(self): return self
    def __exit__(self, *a): return True


class IsoDesktopManager:
    def __init__(self):
        self._desktops: Dict[str, IsoDesktop] = {}
        self._lock = threading.RLock()
        self._counter = 0

    def create(self, label: str = "", user_desktop: bool = False) -> Dict[str, Any]:
        if not _WIN:
            return {"success": False, "error": "Windows only"}
        with self._lock:
            self._reap_idle_locked()
            self._counter += 1
            name = f"Skemi_{uuid.uuid4().hex[:8]}"
            lbl = label or f"AI Desktop {self._counter}"
            try:
                d = IsoDesktop(name, lbl, user_desktop=user_desktop)
            except Exception as exc:
                return {"success": False, "error": f"Create workspace failed: {exc}"}
            self._desktops[name] = d
            return {"success": True, "user_desktop": user_desktop, **d.info()}

    def _reap_idle_locked(self, cap: int = 8) -> None:
        """Bound accumulation of orphaned desktops. The frontend creates a desktop on
        each AI-mode entry but only closes it on an explicit exit — a page reload/tab
        close leaks it (and any Chrome subprocess it spawned) into _desktops forever.
        When we exceed `cap`, close the OLDEST desktops that are safe to drop: NOT
        busy, NOT the shared unified one. Conservative (only fires after real
        accumulation) so it can't close a desktop a live session is using."""
        try:
            import Server as _srv
            unified = _srv._UNIFIED_ISO.get("id") or ""
        except Exception:
            unified = ""
        if len(self._desktops) <= cap:
            return
        victims = sorted(
            (d for nm, d in self._desktops.items()
             if nm != unified and not getattr(d, "busy", False)),
            key=lambda d: getattr(d, "created_at", 0.0))
        # close oldest first until we're back under the cap
        for d in victims[: max(0, len(self._desktops) - cap)]:
            self._desktops.pop(d.name, None)
            with contextlib.suppress(Exception):
                d.close()

    def get(self, desktop_id: str) -> Optional[IsoDesktop]:
        with self._lock:
            return self._desktops.get(desktop_id)

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [d.info() for d in self._desktops.values()]

    def remove(self, desktop_id: str) -> Dict[str, Any]:
        with self._lock:
            d = self._desktops.pop(desktop_id, None)
        if not d:
            return {"success": False, "error": "not found"}
        d.close()
        return {"success": True, "id": desktop_id}


_MANAGER: Optional[IsoDesktopManager] = None


def get_manager() -> IsoDesktopManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = IsoDesktopManager()
    return _MANAGER
