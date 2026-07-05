import asyncio
import ctypes

# v1.2.5: Force DPI Awareness to fix capture jitter and coordinate mismatch
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1) # PROCESS_SYSTEM_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import base64
import contextlib
import ctypes
from ctypes import wintypes
import glob
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

import win32api
import win32con
import win32gui
import win32process
import win32service
import win32ui
from PIL import Image, ImageDraw, ImageFont

try:
    from fastapi import FastAPI, WebSocket
    app = FastAPI()
except Exception:
    WebSocket = object
    class _DummyApp:
        def post(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
        def get(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
        def websocket(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
    app = _DummyApp()

try:
    import desktop_web_worker
except Exception:
    desktop_web_worker = None

try:
    import uiautomation as uia
except Exception:
    uia = None

try:
    import winreg
except Exception:
    winreg = None

try:
    from ai_semantics import get_semantics_analyzer, AISemanticsAnalyzer
except Exception:
    get_semantics_analyzer = None
    AISemanticsAnalyzer = None

# ── Concurrency Control ───────────────────────────────────────────────
GLOBAL_VISION_SEMAPHORE = asyncio.Semaphore(1)

# ── Configuration & Constants ──────────────────────────────────────────
VISION_SYSTEM_PROMPT = """
Bạn là AI agent điều khiển máy tính qua stream màn hình.

Trả về JSON duy nhất:
{
  "action": "click" | "type" | "key" | "done",
  "x_pct": <0.0 đến 1.0 — vị trí ngang trong ảnh stream>,
  "y_pct": <0.0 đến 1.0 — vị trí dọc trong ảnh stream>,
  "text": "<text cần gõ nếu action=type>",
  "key": "<tên phím nếu action=key: enter/tab/esc/backspace>",
  "description": "<mô tả ngắn đang làm gì>",
  "done": true | false,
  "summary": "<kết quả nếu done=true>"
}

QUAN TRỌNG:
- Dùng x_pct và y_pct (0.0-1.0), không phải pixel tuyệt đối
- KHÔNG mở app bằng lệnh, chỉ click icon trên màn hình
- Nếu cần mở app, click vào icon trên desktop hoặc thanh Search
- Thao tác từng bước, chờ màn hình phản hồi trước khi bước tiếp
"""

PROMPT_SYSTEM_VISION = VISION_SYSTEM_PROMPT

COMPRESS_DESKTOP_WIDTH = 1280
DESKTOP_CONTROL_MEMORY_PATH = os.path.join(os.environ.get("APPDATA", ""), "Skemi", "control_memory.json")
HIDDEN_WINDOW_WIDTH = 1280
HIDDEN_WINDOW_HEIGHT = 900

SKEMI_COMPANION_VERSION = "0.2.0"
PHANTOM_BOOTSTRAP_URL = "/api/local-computer/bootstrap/package"
PHANTOM_UPDATE_URL = os.getenv("SKEMI_PHANTOM_UPDATE_URL", PHANTOM_BOOTSTRAP_URL)
PHANTOM_DRIVER_TOKEN_DEFAULTS = (
    "skemi",
    "skemi phantom",
    "skemi virtual display",
    "skemi phantom display",
    "phantom display",
    "phantom monitor",
    "skemi idd",
    "virtual display driver",
    "mttvdd",
    "mtt1337",
    "vdd by mtt",
    "mikethetech",
    "iddsampledriver",
    "iddsampledriver device hdr",
    "usbmmidd",
    "amyuni",
    "displaylink",
    "dlacx",
    "dlproduction",
    "vmulti",
    "vdesk",
    "mobile monitor",
    "mobilemonitor",
    "generic monitor",
    "generic non-pnp monitor",
    "default_monitor",
    "non-pnp"
)


def _phantom_driver_tokens() -> Tuple[str, ...]:
    raw = os.getenv("SKEMI_PHANTOM_DRIVER_TOKENS", "")
    tokens = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return tuple(tokens or PHANTOM_DRIVER_TOKEN_DEFAULTS)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "required"}


def _phantom_debug_enabled() -> bool:
    return _env_flag("SKEMI_DEBUG_PHANTOM", False)


def _phantom_debug(message: str) -> None:
    if _phantom_debug_enabled():
        print(message)


def _version_tuple(value: Any) -> Tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts[:4]) if parts else (0,)


def _phantom_update_status(driver_version: str = "") -> Dict[str, Any]:
    latest_companion = os.getenv("SKEMI_COMPANION_LATEST_VERSION", "").strip()
    latest_driver = os.getenv("SKEMI_PHANTOM_DRIVER_LATEST_VERSION", "").strip()
    explicit_available = _env_flag("SKEMI_PHANTOM_UPDATE_AVAILABLE", False)
    required = _env_flag("SKEMI_PHANTOM_UPDATE_REQUIRED", False)
    companion_update = bool(latest_companion and _version_tuple(latest_companion) > _version_tuple(SKEMI_COMPANION_VERSION))
    driver_update = bool(latest_driver and driver_version and _version_tuple(latest_driver) > _version_tuple(driver_version))
    available = bool(explicit_available or companion_update or driver_update or required)
    state = "required" if required else ("available" if available else "current")
    message = os.getenv("SKEMI_PHANTOM_UPDATE_MESSAGE", "").strip()
    if available and not message:
        message = "A Phantom update is available. Skemi waits for user approval before installing it."
    return {
        "update_state": state,
        "update_available": available,
        "update_required": required,
        "latest_companion_version": latest_companion,
        "latest_driver_version": latest_driver,
        "update_url": os.getenv("SKEMI_PHANTOM_UPDATE_URL", PHANTOM_UPDATE_URL).strip() or PHANTOM_BOOTSTRAP_URL,
        "update_size_mb": os.getenv("SKEMI_PHANTOM_UPDATE_SIZE_MB", "").strip(),
        "update_requires_admin": _env_flag("SKEMI_PHANTOM_UPDATE_REQUIRES_ADMIN", True),
        "update_message": message,
    }

# APP_LAUNCH_ALIASES - Deprecated: Now using AI-based semantic matching
# Kept for backward compatibility but no longer the primary method
APP_LAUNCH_ALIASES: Dict[str, List[str]] = {}

async def _resolve_app_ai(query: str, installed_apps: List[Dict]) -> Optional[str]:
    """AI-based app resolution - no hardcoded aliases"""
    if not query or not installed_apps:
        return None
    
    # Try AI semantics
    if get_semantics_analyzer:
        try:
            analyzer = get_semantics_analyzer()
            target = await analyzer.resolve_app(query, installed_apps)
            if target:
                return target
        except:
            pass
    
    # Smart semantic matching
    query_lower = query.lower()
    query_words = set(re.findall(r'\b\w+\b', query_lower))
    
    best_match = None
    best_score = 0
    
    for app in installed_apps:
        app_name = app.get("name", "").lower()
        display_name = app.get("display_name", "").lower()
        target = app.get("target", "")
        
        if not target:
            continue
        
        # Multiple matching strategies
        names_to_check = [app_name, display_name, Path(target).stem.lower()]
        
        for name in names_to_check:
            if not name:
                continue
            
            # Exact match
            if query_lower == name:
                return target
            
            # Contains match (query in app name)
            if query_lower in name:
                score = len(query_lower) / len(name)
                if score > best_score:
                    best_score = score
                    best_match = target
            
            # Contains match (app name in query)
            if name in query_lower:
                score = len(name) / len(query_lower)
                if score > best_score:
                    best_score = score
                    best_match = target
            
            # Word overlap
            name_words = set(re.findall(r'\b\w+\b', name))
            overlap = query_words & name_words
            if overlap:
                score = len(overlap) / max(len(query_words), len(name_words))
                if score > best_score:
                    best_score = score
                    best_match = target
    
    # Return if confidence is high enough
    if best_score >= 0.5:
        return best_match
    
    return None

FUZZY_WEB_MAP = {
    "chatgpt": "https://chatgpt.com",
    "chatgtp": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "youtube": "https://youtube.com",
    "facebook": "https://facebook.com",
    "gmail": "https://mail.google.com",
    "bing": "https://bing.com",
    "google": "https://google.com",
}

APP_WEB_FALLBACKS = {
    "discord": "https://discord.com/channels/@me",
    "zalo": "https://chat.zalo.me",
    "telegram": "https://web.telegram.org",
    "messenger": "https://www.messenger.com",
    "slack": "https://slack.com/signin",
    "teams": "https://teams.microsoft.com",
    "spotify": "https://open.spotify.com",
}

_START_APPS_CACHE: Dict[str, Any] = {"loaded_at": 0.0, "items": []}
_START_MENU_SHORTCUTS_CACHE: Dict[str, Any] = {"loaded_at": 0.0, "items": []}

_LAUNCH_INTENT_PATTERN = re.compile(
    r"\b(?:open|launch|start|run|show|visit|browse|go\s+to|switch\s+to|"
    r"m[oở]|b[aậ]t|ch[aạ]y|v[aà]o|m[oơ]\s+l[eê]n|hi[eệ]n)\b",
    re.I,
)

_FOLDER_INTENT_PATTERN = re.compile(
    r"\b(?:folder|directory|thu muc|file explorer|explorer|mo thu muc|vao thu muc|trong thu muc|noi dung thu muc)\b",
    re.I,
)
_POST_LAUNCH_ACTION_PATTERN = re.compile(
    r"\b(?:click|type|press|scroll|search|find|play|watch|listen|login|sign in|select|choose|send|message|chat|reply|dm|inbox|"
    r"upload|download|paste|copy|bat|phat|nghe|xem|tim|tra cuu|dang nhap|nhap|chon|gui|nhan|nhan tin|chat voi|tra loi|go|viet|"
    r"noi|bao|keu|tai xuong|tai len)\b",
    re.I,
)
_SENSITIVE_CONFIRM_PATTERN = re.compile(
    r"\b(?:delete|remove|uninstall|install|format|wipe|erase|factory reset|shutdown|restart|reboot|share|upload|publish|"
    r"password|passcode|otp|token|2fa|bank|wallet|payment|pay|purchase|buy|system settings|registry)\b",
    re.I,
)

_GENERIC_WINDOW_TITLES = {
    "desktopwindowxamlsource",
    "default ime",
    "msctfime ui",
    "program manager",
}
_GENERIC_WINDOW_CLASS_TERMS = (
    "desktopwindowxamlsource",
    "tooltips_class32",
    "sysshadow",
)

active_sessions: Dict[str, "DesktopAgentSession"] = {}
is_isolated = False 
PHYSICAL_INPUT_LOCKED = False 
_last_capture_error = "" 
_input_shield_lock = threading.Lock()
AI_CONTROL_ACTIVE = False # v7.0: Global guard against mouse jitter on startup
_last_physical_mouse_pos = (-1, -1)
_safety_lock_tripped = False

def check_safety_lock() -> bool:
    global _last_physical_mouse_pos, _safety_lock_tripped, AI_CONTROL_ACTIVE
    if _safety_lock_tripped:
        return True
    try:
        curr = win32api.GetCursorPos()
        if _last_physical_mouse_pos != (-1, -1):
            dx = curr[0] - _last_physical_mouse_pos[0]
            dy = curr[1] - _last_physical_mouse_pos[1]
            if dx*dx + dy*dy > 400: # 20 pixels threshold
                _safety_lock_tripped = True
                AI_CONTROL_ACTIVE = False
                print("[SAFETY LOCK] Physical mouse moved! Pausing AI.")
                return True
        _last_physical_mouse_pos = curr
    except Exception:
        pass
    return False

def _set_ai_control_active(active: bool) -> None:
    global AI_CONTROL_ACTIVE, _safety_lock_tripped, _last_physical_mouse_pos
    if active:
        _safety_lock_tripped = False
        try:
            _last_physical_mouse_pos = win32api.GetCursorPos()
        except Exception:
            _last_physical_mouse_pos = (-1, -1)
    AI_CONTROL_ACTIVE = bool(active)

def _has_active_phantom_task() -> bool:
    """v6.9: Check if there's a real (non-preview) phantom session actively running.
    Only non-preview sessions should ever block the user's physical input."""
    return any(
        getattr(s, 'mode', '') == 'phantom' and not getattr(s, 'preview_only', False)
        for s in active_sessions.values()
    )

def _has_active_live_control() -> bool:
    """Live Control: AI is acting on the user's REAL desktop using background
    ghost-input (PostMessage to the window under the target point). Like Phantom,
    a controlling live session must NEVER move the physical cursor or steal focus
    — the user keeps full control of their own mouse/keyboard. Only preview /
    watch-only live sessions are exempt (they never inject input at all)."""
    return any(
        getattr(s, 'mode', '') == 'live' and not getattr(s, 'preview_only', False)
        for s in active_sessions.values()
    )

def _safe_set_foreground_window(hwnd: int):
    """v1.2.4: Strictly block focus stealing in Phantom Mode."""
    if _has_active_phantom_task():
        return
    try:
        import win32gui
        win32gui.SetForegroundWindow(hwnd)
    except: pass

def _safe_set_cursor_pos(x: int, y: int):
    if not AI_CONTROL_ACTIVE:
        return # Strictly block all AI-originated mouse moves if not in active session
    # v1.2.2: Block physical cursor move if AI is working in Phantom mode to prevent jitter
    if _has_active_phantom_task():
        return
    # Live Control acts via background ghost-input only; never hijack the real cursor.
    if _has_active_live_control():
        return
    try:
        win32api.SetCursorPos((x, y))
    except Exception: pass

def _safe_mouse_event(flags: int, x: int, y: int, data: int, extra: int):
    if not AI_CONTROL_ACTIVE:
        return
    with _input_shield_lock:
        phantom_task_active = any(
            getattr(s, 'mode', '') == 'phantom' and not getattr(s, 'preview_only', False)
            for s in active_sessions.values()
        )
        if phantom_task_active:
            # v1.2.3: Strictly block physical cursor updates to prevent jitter
            return
        # Live Control never moves the physical cursor — ghost-input only.
        if _has_active_live_control():
            return
        try:
            win32api.mouse_event(flags, x, y, data, extra)
        except Exception: pass

def _should_block_system_mouse(hwnd: int) -> bool:
    """Check if physical mouse input should be blocked.
    
    In phantom mode with virtual display, we block PHYSICAL input (mouse_event, SetCursorPos) to prevent
    cursor jitter on user's desktop. But we allow PostMessage-based ghost input
    for windows that are on the virtual display.
    
    v6.9 FIX: Only block when we have an active NON-PREVIEW phantom session with a target window.
    Preview sessions (stream-only) must NEVER block the user's physical mouse.
    """
    # v8.5: Always block when any non-preview phantom session is active to prevent jitter
    for s in active_sessions.values():
        if (
            getattr(s, 'mode', '') == 'phantom'
            and not getattr(s, 'preview_only', False)
        ):
            return True
    return False

# ── Input Helpers ──────────────────────────────────────────────────────

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort)]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("iu", INPUT_UNION)]

def _send_input(inputs: List[INPUT]):
    if not AI_CONTROL_ACTIVE:
        return
    with _input_shield_lock:
        # v6.9 FIX: Only block if a real phantom task is running
        if _has_active_phantom_task():
            return
    n = len(inputs)
    lpInput = (INPUT * n)(*inputs)
    ctypes.windll.user32.SendInput(n, ctypes.pointer(lpInput), ctypes.sizeof(INPUT))

def _get_target_point(hwnd, x_norm, y_norm):
    try:
        rect = win32gui.GetClientRect(hwnd)
        w, h = rect[2], rect[3]
        return int(x_norm * w / 1000), int(y_norm * h / 1000)
    except: return 0, 0

def _find_input_target_child(hwnd):
    # Chromium apps (Chrome, Edge, Discord) often require targeting the RenderWidget child
    target = [hwnd]
    def enum_child(h, _):
        cls = win32gui.GetClassName(h)
        if "RenderWidget" in cls or "Intermediate D3D Window" in cls:
            target[0] = h
            return False # Stop enumeration
        return True
    try: win32gui.EnumChildWindows(hwnd, enum_child, None)
    except: pass
    return target[0]


def _grab_user_fg() -> int:
    try:
        return int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return 0


def _restore_user_fg(prev_hwnd: int) -> None:
    """Give the user's foreground window back after a launched app grabbed it
    (notepad/chrome SetForegroundWindow on self). Uses AttachThreadInput so the
    SetForegroundWindow actually takes effect across the foreground lock. This is
    what keeps "không cướp focus" true even when AI opens apps on the shared desktop."""
    if not prev_hwnd:
        return
    try:
        import ctypes as _ct
        user32 = _ct.windll.user32
        kernel32 = _ct.windll.kernel32
        if not user32.IsWindow(int(prev_hwnd)):
            return
        if int(user32.GetForegroundWindow() or 0) == int(prev_hwnd):
            return
        cur = kernel32.GetCurrentThreadId()
        fg_t = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        tg_t = user32.GetWindowThreadProcessId(int(prev_hwnd), None)
        user32.AttachThreadInput(cur, fg_t, True)
        user32.AttachThreadInput(cur, tg_t, True)
        user32.SetForegroundWindow(int(prev_hwnd))
        user32.AttachThreadInput(cur, tg_t, False)
        user32.AttachThreadInput(cur, fg_t, False)
    except Exception:
        pass


def _find_edit_child(hwnd):
    """Find an Edit/RichEdit child so background WM_SETTEXT lands (Win11 Notepad,
    classic edit controls). Returns 0 if none — caller falls back to WM_CHAR."""
    found = [0]
    edit_classes = ("edit", "richedit", "richeditd2dpt", "richedit20w",
                    "richedit50w", "scintilla", "richeditd2d")
    def _cb(h, _):
        try:
            cls = (win32gui.GetClassName(h) or "").lower()
            if any(k in cls for k in edit_classes):
                found[0] = h
                return False
        except Exception:
            pass
        return True
    try: win32gui.EnumChildWindows(hwnd, _cb, None)
    except Exception: pass
    return found[0]

def _move_mouse_smooth(screen_x: int, screen_y: int, steps: int = 6, duration: float = 0.08):
    if _should_block_system_mouse(0):
        if os.getenv("SKEMI_DEBUG_INPUT", "0").strip().lower() in {"1", "true", "yes", "on"}:
            print(f"[INPUT TRACE] Blocked smooth mouse move to ({screen_x}, {screen_y})")
        return
    try:
        start_x, start_y = win32api.GetCursorPos()
    except Exception:
        start_x, start_y = screen_x, screen_y
    safe_steps = max(1, int(steps or 1))
    for index in range(1, safe_steps + 1):
        ratio = index / safe_steps
        next_x = int(start_x + ((screen_x - start_x) * ratio))
        next_y = int(start_y + ((screen_y - start_y) * ratio))
        if os.getenv("SKEMI_DEBUG_INPUT", "0").strip().lower() in {"1", "true", "yes", "on"}:
            print(f"[INPUT TRACE] SetCursorPos -> ({next_x}, {next_y})")
        _safe_set_cursor_pos(next_x, next_y)
        time.sleep(max(0.002, float(duration or 0.0) / safe_steps))

def _window_uses_human_input(hwnd: int) -> bool:
    # v1.0.2: User strictly requested NO focus/mouse stealing ("không cướp chuột hay cướp focus").
    # We will ALWAYS use PostMessage (Ghost Input) now.
    return False

def _window_point_to_screen(hwnd: int, x_norm: int, y_norm: int) -> tuple[int, int]:
    target_h = _find_input_target_child(hwnd)
    lx, ly = _get_target_point(target_h, x_norm, y_norm)
    try:
        sx, sy = win32gui.ClientToScreen(target_h, (lx, ly))
        return int(sx), int(sy)
    except Exception:
        rect = win32gui.GetWindowRect(hwnd)
        return int(rect[0] + lx), int(rect[1] + ly)


def manual_click(x: int, y: int, hwnd: int = 0):
    if not AI_CONTROL_ACTIVE or check_safety_lock():
        return
    if _should_block_system_mouse(hwnd):
        _phantom_debug('[INPUT] Physical mouse blocked. Attempting background injection...')
        # v8.5: Redirect to phantom session if available
        for s in active_sessions.values():
            if getattr(s, 'mode', '') == 'phantom' and not getattr(s, 'preview_only', False):
                # We use internal coordinate space (0-1000) for phantom injection
                # or absolute if we can resolve it. But manual_click usually gets absolute.
                # So we convert back to 0-1000 if needed, or just use s._post_phantom_click_sync
                # with absolute coords if we modify it.
                # Actually, s._post_phantom_click_sync handles normalization.
                # Let's assume manual_click (x,y) are from vision (0-1000).
                s._post_phantom_click_sync({"x": x, "y": y})
                return
        return
    
    if not hwnd or not win32gui.IsWindow(hwnd):
        nx = int(x * 65535 / win32api.GetSystemMetrics(win32con.SM_CXSCREEN))
        ny = int(y * 65535 / win32api.GetSystemMetrics(win32con.SM_CYSCREEN))
        _safe_mouse_event(win32con.MOUSEEVENTF_ABSOLUTE | win32con.MOUSEEVENTF_MOVE, nx, ny, 0, 0)
        _safe_mouse_event(win32con.MOUSEEVENTF_ABSOLUTE | win32con.MOUSEEVENTF_LEFTDOWN, nx, ny, 0, 0)
        _safe_mouse_event(win32con.MOUSEEVENTF_ABSOLUTE | win32con.MOUSEEVENTF_LEFTUP, nx, ny, 0, 0)
    elif _window_uses_human_input(hwnd):
        screen_x, screen_y = _window_point_to_screen(hwnd, x, y)
        _move_mouse_smooth(screen_x, screen_y)
        _safe_set_cursor_pos(screen_x, screen_y)
        _safe_mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        _safe_mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    else:
        target_h = _find_input_target_child(hwnd)
        lx, ly = _get_target_point(target_h, x, y)
        lparam = win32api.MAKELONG(lx, ly)
        win32gui.PostMessage(target_h, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.01)
        win32gui.PostMessage(target_h, win32con.WM_LBUTTONUP, 0, lparam)

def manual_type(text: str, hwnd: int = 0):
    if not AI_CONTROL_ACTIVE or check_safety_lock():
        return
    if _should_block_system_mouse(hwnd):
        _phantom_debug('[INPUT] Physical keyboard blocked. Attempting background injection...')
        for s in active_sessions.values():
            if getattr(s, 'mode', '') == 'phantom' and not getattr(s, 'preview_only', False):
                s._post_phantom_type_sync(text)
                return
        return
    if not hwnd or not win32gui.IsWindow(hwnd):
        if _has_active_phantom_task():
            _phantom_debug('[INPUT] No window for typing in Phantom mode; skipping physical fallback.')
            return
        import pyautogui
        pyautogui.write(str(text), interval=0.01)
        return
    target_h = _find_input_target_child(hwnd)
    if _window_uses_human_input(hwnd):
        if _has_active_phantom_task():
            for char in str(text):
                if char == '\n': manual_press('enter', hwnd)
                else: win32gui.PostMessage(target_h, win32con.WM_CHAR, ord(char), 0)
            return
        with contextlib.suppress(Exception): _safe_set_foreground_window(hwnd)
        import pyautogui
        pyautogui.write(str(text), interval=0.01)
    else:
        # Prefer background WM_SETTEXT into an Edit/RichEdit child (Win11 Notepad,
        # classic edits) — reliable, no focus. Only when the whole string has no
        # newlines (WM_SETTEXT replaces all content; newlines need per-key Enter).
        edit_child = _find_edit_child(hwnd)
        if edit_child and '\n' not in str(text):
            with contextlib.suppress(Exception):
                win32gui.SendMessage(edit_child, win32con.WM_SETTEXT, 0, str(text))
                return
        for char in str(text):
            if char == '\n': manual_press('enter', hwnd)
            else: win32gui.PostMessage(target_h, win32con.WM_CHAR, ord(char), 0)

def manual_press(key: str, hwnd: int = 0):
    if not AI_CONTROL_ACTIVE or check_safety_lock():
        return
    if _should_block_system_mouse(hwnd):
        _phantom_debug('[INPUT] Blocking system key press to prevent jitter.')
        return
    key = str(key).lower().strip()
    vk_map = {'enter': win32con.VK_RETURN, 'tab': win32con.VK_TAB, 'backspace': win32con.VK_BACK, 'esc': win32con.VK_ESCAPE, 'up': win32con.VK_UP, 'down': win32con.VK_DOWN, 'left': win32con.VK_LEFT, 'right': win32con.VK_RIGHT}
    vk = vk_map.get(key)
    if not vk and len(key) == 1: vk = ctypes.windll.user32.VkKeyScanW(ord(key)) & 0xFF
    if not vk: return
    
    if not hwnd or not win32gui.IsWindow(hwnd):
        if _has_active_phantom_task():
            _phantom_debug(f'[INPUT] No window for key {key} in Phantom mode; skipping physical fallback.')
            return
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    elif _window_uses_human_input(hwnd) and not _has_active_phantom_task():
        with contextlib.suppress(Exception): _safe_set_foreground_window(hwnd)
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    else:
        target_h = _find_input_target_child(hwnd)
        win32gui.PostMessage(target_h, win32con.WM_KEYDOWN, vk, 0)
        time.sleep(0.01)
        win32gui.PostMessage(target_h, win32con.WM_KEYUP, vk, 0)

def manual_scroll(amount: int, hwnd: int = 0):
    if not AI_CONTROL_ACTIVE or check_safety_lock():
        return
    if _should_block_system_mouse(hwnd):
        _phantom_debug('[INPUT] Blocking system scroll to prevent jitter.')
        return
    delta = int(amount or 0) or -120
    if not hwnd or not win32gui.IsWindow(hwnd):
        if not _has_active_phantom_task(): win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        return
    if _window_uses_human_input(hwnd):
        if _has_active_phantom_task():
            target_h = _find_input_target_child(hwnd)
            wparam = (int(delta) & 0xFFFF) << 16
            win32gui.PostMessage(target_h, win32con.WM_MOUSEWHEEL, wparam, 0)
            return
        # v5.1: Disable cursor movement during scroll to prevent jitter
        # cx, cy = (rect[0]+rect[2])//2, (rect[1]+rect[3])//2
        # with contextlib.suppress(Exception): win32api.SetCursorPos((cx, cy))
        if not _has_active_phantom_task(): win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
    else:
        target_h = _find_input_target_child(hwnd)
        wparam = (int(delta) & 0xFFFF) << 16
        win32gui.PostMessage(target_h, win32con.WM_MOUSEWHEEL, wparam, 0)

def _normalize_text(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", str(value or "").lower())
        if not unicodedata.combining(ch)
    )


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return ordered


def _pretty_host_label(raw_url: str) -> str:
    try:
        host = str(urlparse(str(raw_url or "")).netloc or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return ""
    host = re.sub(r"^www\.", "", host)
    parts = [
        part for part in re.split(r"[.\-]+", host)
        if part and part not in {"com", "vn", "org", "net", "app", "io", "co"}
    ]
    if not parts:
        return ""
    return " ".join(part.capitalize() for part in parts[:3]).strip()


def _is_generic_window_identity(title: str = "", cls: str = "") -> bool:
    normalized_title = _normalize_text(title).strip()
    normalized_class = _normalize_text(cls).strip()
    if not normalized_title and not normalized_class:
        return False
    if normalized_title in _GENERIC_WINDOW_TITLES:
        return True
    if any(term in normalized_class for term in _GENERIC_WINDOW_CLASS_TERMS):
        return True
    if "desktopwindowxamlsource" in normalized_title:
        return True
    return False


def _surface_label(title: str = "", *, url: str = "", fallback: str = "") -> str:
    clean_title = str(title or "").strip()
    if clean_title and not _is_generic_window_identity(clean_title, ""):
        return clean_title
    url_label = _pretty_host_label(url)
    if url_label:
        return url_label
    clean_fallback = str(fallback or "").strip()
    if clean_fallback and not _is_generic_window_identity(clean_fallback, ""):
        return clean_fallback
    return "the target window"


def _extract_app_launch_phrase(query: str) -> str:
    raw_query = str(query or "").strip()
    if not raw_query:
        return ""
    normalized = _normalize_text(raw_query)
    match = re.search(
        r"\b(?:open|launch|start|run|show|switch to|mo|bat|chay|vao|hien)\b\s+(.+)",
        normalized,
    )
    if not match:
        return ""
    candidate = re.split(r"\b(?:va|and|then|roi|de|to)\b", match.group(1), maxsplit=1)[0]
    candidate = re.sub(r"[^a-z0-9.+_ -]+", " ", candidate).strip(" ,.;:-")
    return candidate


def _lookup_app_path_from_registry(executable_name: str) -> str:
    if winreg is None:
        return ""
    exe_name = os.path.basename(str(executable_name or "").strip())
    if not exe_name:
        return ""
    subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
    for root in (getattr(winreg, "HKEY_CURRENT_USER", None), getattr(winreg, "HKEY_LOCAL_MACHINE", None)):
        if root is None:
            continue
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _ = winreg.QueryValueEx(key, None)
            path = str(value or "").strip().strip('"')
            if path and os.path.exists(path):
                return path
        except Exception:
            continue
    return ""


def _which_executable(command_name: str) -> str:
    candidate = str(command_name or "").strip().strip('"')
    if not candidate:
        return ""
    if os.path.isabs(candidate) and os.path.exists(candidate):
        return candidate

    where_targets = [candidate]
    if not candidate.lower().endswith(".exe"):
        where_targets.append(f"{candidate}.exe")

    for target in _dedupe_preserve(where_targets):
        try:
            proc = subprocess.run(
                ["where.exe", target],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    path = str(line or "").strip().strip('"')
                    if path and os.path.exists(path):
                        return path
        except Exception:
            pass

    for target in _dedupe_preserve(where_targets):
        resolved = _lookup_app_path_from_registry(target)
        if resolved:
            return resolved
    return ""


def _resolve_launchable_executables(query: str) -> List[str]:
    return [cmd[0] for cmd in _resolve_launchable_commands(query) if cmd]


async def _match_app_alias_ai(raw_query: str, installed_apps: List[Dict]) -> str:
    """AI-based app matching - no hardcoded aliases"""
    if not raw_query or not raw_query.strip():
        return ""
    
    # Use AI resolver
    target = await _resolve_app_ai(raw_query, installed_apps)
    if target:
        return target
    
    return ""

def _match_app_alias(raw_query: str) -> str:
    """Sync wrapper - kept for compatibility"""
    # Return empty - async version should be used instead
    return ""


_APP_QUERY_FILLER_WORDS = {
    "a", "an", "the", "please", "pls", "giup", "giup toi", "cho", "toi",
    "minh", "ban", "nhe", "di", "len", "ra", "vao", "mo", "bat", "chay",
    "open", "launch", "start", "run", "show", "switch", "to", "app",
    "ung", "dung", "ung dung", "phan", "mem", "software", "desktop",
    "local", "computer", "ai", "web", "website", "browser", "trinh", "duyet",
}


def _clean_app_lookup_query(query: str) -> str:
    raw = _extract_app_launch_phrase(query) or str(query or "")
    normalized = _normalize_text(raw)
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9.+_ -]+", " ", normalized)
    words = [part for part in re.split(r"\s+", normalized) if part]
    filtered = [word for word in words if word not in _APP_QUERY_FILLER_WORDS]
    return " ".join(filtered or words).strip()


def _app_match_score(name: str, query: str) -> int:
    target = re.sub(r"[^a-z0-9.+_ -]+", " ", _normalize_text(name))
    lookup = _clean_app_lookup_query(query)
    if not target or not lookup:
        return 0
    target_words = [part for part in re.split(r"[^a-z0-9]+", target) if part]
    lookup_words = [part for part in re.split(r"[^a-z0-9]+", lookup) if part]
    if not target_words or not lookup_words:
        return 0
    target_joined = " ".join(target_words)
    lookup_joined = " ".join(lookup_words)
    score = 0
    if target_joined == lookup_joined:
        score += 1000
    if target_joined.startswith(lookup_joined):
        score += 760 + len(lookup_joined)
    elif lookup_joined in target_joined:
        score += 650 + len(lookup_joined)
    matched_all = True
    for token in lookup_words:
        if token in target_words:
            score += 90
        elif any(word.startswith(token) for word in target_words):
            score += 70
        elif token in target_joined:
            score += 40
        else:
            matched_all = False
    if matched_all:
        score += 300 + (40 * len(lookup_words))
    return score


def _load_start_apps_sync(force: bool = False) -> List[Dict[str, str]]:
    now = time.time()
    if not force and _START_APPS_CACHE["items"] and (now - float(_START_APPS_CACHE["loaded_at"] or 0.0)) < 120.0:
        return list(_START_APPS_CACHE["items"])
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
        )
        data = json.loads(str(proc.stdout or "").strip() or "[]")
        if isinstance(data, dict):
            data = [data]
        items: List[Dict[str, str]] = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name") or "").strip()
            app_id = str(item.get("AppID") or "").strip()
            if name and app_id:
                items.append({"name": name, "appid": app_id})
        _START_APPS_CACHE["loaded_at"] = now
        _START_APPS_CACHE["items"] = items
        return list(items)
    except Exception as exc:
        _phantom_debug(f"[LAUNCH] StartApps inventory unavailable: {exc}")
        return list(_START_APPS_CACHE["items"] or [])


def _start_menu_shortcut_dirs() -> List[str]:
    candidates = [
        os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.environ.get("PUBLIC", ""), "Desktop"),
    ]
    return [path for path in _dedupe_preserve(candidates) if path and os.path.isdir(path)]


def _load_start_menu_shortcuts_sync(force: bool = False) -> List[Dict[str, str]]:
    now = time.time()
    if not force and _START_MENU_SHORTCUTS_CACHE["items"] and (now - float(_START_MENU_SHORTCUTS_CACHE["loaded_at"] or 0.0)) < 120.0:
        return list(_START_MENU_SHORTCUTS_CACHE["items"])
    items: List[Dict[str, str]] = []
    try:
        for base in _start_menu_shortcut_dirs():
            for root, _dirs, files in os.walk(base):
                for filename in files:
                    if not filename.lower().endswith((".lnk", ".url")):
                        continue
                    path = os.path.join(root, filename)
                    name = os.path.splitext(filename)[0].strip()
                    if name and os.path.exists(path):
                        items.append({"name": name, "path": path})
        _START_MENU_SHORTCUTS_CACHE["loaded_at"] = now
        _START_MENU_SHORTCUTS_CACHE["items"] = items
    except Exception as exc:
        _phantom_debug(f"[LAUNCH] Start Menu shortcut inventory unavailable: {exc}")
    return list(items)


def _resolve_start_app_commands(query: str, limit: int = 5) -> List[List[str]]:
    if not _should_try_startapps_search(query):
        return []
    lookup = _clean_app_lookup_query(query)
    scored: List[Tuple[int, Dict[str, str]]] = []
    for item in _load_start_apps_sync():
        score = _app_match_score(item.get("name", ""), lookup)
        if score >= 140:
            scored.append((score, item))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    commands: List[List[str]] = []
    for _score, item in scored[:max(1, int(limit or 1))]:
        app_id = str(item.get("appid") or "").strip()
        if app_id:
            commands.append(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
    return commands


def _resolve_start_menu_shortcut_commands(query: str, limit: int = 5) -> List[List[str]]:
    if not _should_try_startapps_search(query):
        return []
    lookup = _clean_app_lookup_query(query)
    scored: List[Tuple[int, Dict[str, str]]] = []
    for item in _load_start_menu_shortcuts_sync():
        score = _app_match_score(item.get("name", ""), lookup)
        if score >= 140:
            scored.append((score, item))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    commands: List[List[str]] = []
    for _score, item in scored[:max(1, int(limit or 1))]:
        path = str(item.get("path") or "").strip()
        if path and os.path.exists(path):
            commands.append(["explorer.exe", path])
    return commands


def _resolve_dynamic_app_commands(query: str, limit: int = 6) -> List[List[str]]:
    commands: List[List[str]] = []
    commands.extend(_resolve_start_app_commands(query, limit=limit))
    commands.extend(_resolve_start_menu_shortcut_commands(query, limit=limit))
    deduped: List[List[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in commands:
        key = tuple(str(part).lower() for part in command if str(part or "").strip())
        if key and key not in seen:
            seen.add(key)
            deduped.append(command)
    return deduped[:max(1, int(limit or 1))]


def _match_app_web_fallback(raw_query: str) -> str:
    alias = _match_app_alias(raw_query)
    if alias and alias in APP_WEB_FALLBACKS:
        return APP_WEB_FALLBACKS[alias]
    normalized = _normalize_text(raw_query)
    for key, url in APP_WEB_FALLBACKS.items():
        if re.search(rf"\b{re.escape(_normalize_text(key))}\b", normalized):
            return url
    return ""


def _split_executable_hint(hint: str) -> Tuple[str, List[str]]:
    raw = str(hint or "").strip().strip('"')
    if not raw:
        return "", []
    match = re.search(r"\.exe\b", raw, re.I)
    if not match:
        return raw, []
    exe_part = raw[:match.end()].strip().strip('"')
    arg_text = raw[match.end():].strip()
    if not arg_text:
        return exe_part, []
    try:
        import shlex
        return exe_part, shlex.split(arg_text, posix=False)
    except Exception:
        return exe_part, [part for part in arg_text.split() if part]


def _resolve_launchable_commands(query: str) -> List[List[str]]:
    raw_query = str(query or "").strip()
    if not raw_query:
        return []

    normalized = _normalize_text(raw_query)
    hints: List[str] = []
    if os.path.isabs(raw_query) or raw_query.lower().endswith(".exe"):
        hints.append(raw_query)

    # AI-based app resolution - no hardcoded aliases
    # Get installed apps for context
    installed_apps = []
    try:
        from skemi_local_computer_backend import _scan_start_menu_shortcuts_sync
        installed_apps = _scan_start_menu_shortcuts_sync()[:20]  # Limit for performance
    except:
        pass
    
    if installed_apps:
        # Use AI to find matching app
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule async task
                pass  # Will be resolved elsewhere
            else:
                ai_match = loop.run_until_complete(_resolve_app_ai(raw_query, installed_apps))
                if ai_match:
                    hints.append(ai_match)
        except:
            pass
    
    # Fallback: extract words from query
    parts = [part for part in re.split(r"[^a-z0-9.+_-]+", normalized) if part]
    if parts:
        hints.append(parts[0])
        hints.append(f"{parts[0]}.exe")
    if len(parts) >= 2:
        hints.append("".join(parts[:2]))
        hints.append(f"{''.join(parts[:2])}.exe")

    resolved: List[List[str]] = []
    for hint in _dedupe_preserve(hints):
        exe_hint, hint_args = _split_executable_hint(hint)
        expanded_hints = [exe_hint]
        if any(ch in exe_hint for ch in ("*", "?")):
            expanded_hints = sorted(glob.glob(exe_hint)) or [exe_hint]
        for expanded in expanded_hints:
            if os.path.isabs(expanded) and os.path.exists(expanded):
                resolved.append([expanded, *hint_args])
                continue
            match = _which_executable(expanded)
            if match:
                resolved.append([match, *hint_args])
            continue
        match = _which_executable(hint)
        if match:
            resolved.append([match])

    resolved.extend(_resolve_dynamic_app_commands(raw_query))

    deduped: List[List[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in resolved:
        key = tuple(str(part).lower() for part in command if str(part or "").strip())
        if key and key not in seen:
            seen.add(key)
            deduped.append(command)
    return deduped


def _extract_existing_path(query: str) -> str:
    raw_query = str(query or "").strip()
    if not raw_query:
        return ""
    direct = raw_query.strip("\"'")
    if direct and os.path.exists(direct):
        return os.path.abspath(direct)
    for pattern in (r'"([^"]+)"', r"'([^']+)'", r"([A-Za-z]:\\[^:*?\"<>|\r\n]+)"):
        for match in re.finditer(pattern, raw_query):
            candidate = str(match.group(1) or "").strip().strip("\"'").rstrip(".,;")
            if candidate and os.path.exists(candidate):
                return os.path.abspath(candidate)
    return ""


def _known_shell_folders() -> Dict[str, str]:
    home = os.path.expanduser("~")
    candidates = {
        "downloads": os.path.join(home, "Downloads"),
        "desktop": os.path.join(home, "Desktop"),
        "documents": os.path.join(home, "Documents"),
        "pictures": os.path.join(home, "Pictures"),
        "videos": os.path.join(home, "Videos"),
        "music": os.path.join(home, "Music"),
    }
    return {name: path for name, path in candidates.items() if path and os.path.exists(path)}


async def _has_folder_intent_ai(query: str) -> bool:
    """AI-based folder intent detection"""
    if not query or not query.strip():
        return False
    
    # Try AI semantics
    if get_semantics_analyzer:
        try:
            analyzer = get_semantics_analyzer()
            intent = await analyzer.analyze_intent(query)
            return intent.intent_type == "folder"
        except:
            pass
    
    # Smart context detection (not hardcoded keywords)
    normalized = _normalize_text(query)
    
    # Semantic understanding: context matters more than specific words
    # Check if query is about accessing a location
    access_patterns = [
        r'\b(mo|vao|xem|truy\s+cap|tim|mo\s+ra)\s+(.+?)(\s+folder|\s+thu\s+muc)?\b',
        r'\b(open|access|browse|view|go\s+to|enter|show)\s+(.+?)(\s+folder)?\b',
    ]
    
    for pattern in access_patterns:
        if re.search(pattern, normalized, re.I):
            return True
    
    # Check for folder references
    folders = _known_shell_folders()
    for folder_key in folders.keys():
        if folder_key in normalized:
            return True
    
    return False

def _has_folder_intent(query: str) -> bool:
    """Sync wrapper"""
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            return loop.run_until_complete(_has_folder_intent_ai(query))
    except:
        pass
    return False


async def _resolve_shell_folder_path_ai(query: str) -> str:
    """AI-based folder resolution - no keyword matching"""
    if not query or not query.strip():
        return ""
    
    # Try AI semantics first
    if get_semantics_analyzer:
        try:
            from pathlib import Path
            home = Path.home()
            analyzer = get_semantics_analyzer()
            folder_path = await analyzer.resolve_folder(query, home)
            if folder_path:
                return str(folder_path)
        except Exception as e:
            pass
    
    # Fallback: semantic understanding without hardcoded keywords
    normalized = _normalize_text(query)
    folders = _known_shell_folders()
    
    # Smart matching based on context, not fixed keywords
    query_words = set(re.findall(r'\b\w+\b', normalized))
    
    for folder_key, folder_path in folders.items():
        if not folder_path:
            continue
            
        # Check if folder name appears in query contextually
        folder_words = set(folder_key.lower().split())
        
        # Context detection: words that suggest folder access
        access_indicators = {"mo", "vao", "xem", "truy cap", "tim", "trong", 
                            "open", "access", "browse", "view", "go", "enter", "show"}
        has_access_context = bool(query_words & access_indicators)
        
        # Match folder name in query
        if folder_key in normalized or any(word in normalized for word in folder_words):
            if has_access_context or len(query_words) <= 3:  # Short queries likely direct references
                return folder_path
    
    return ""

# Keep sync version for backward compatibility
def _resolve_shell_folder_path(query: str) -> str:
    """Synchronous wrapper - will be deprecated"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running in async context, schedule task
            future = asyncio.ensure_future(_resolve_shell_folder_path_ai(query))
            # Return empty for now, async version will be used properly
            return ""
        else:
            return loop.run_until_complete(_resolve_shell_folder_path_ai(query))
    except:
        return ""


async def _requires_post_launch_interaction_ai(query: str) -> bool:
    """AI-based detection of post-launch interaction needs"""
    if not query or not query.strip():
        return False
    
    # Try AI semantics
    if get_semantics_analyzer:
        try:
            analyzer = get_semantics_analyzer()
            intent = await analyzer.analyze_intent(query)
            # Any interaction beyond simple launch requires follow-up
            return intent.intent_type in ["interaction", "sensitive", "system"]
        except:
            pass
    
    # Smart detection: length and complexity indicate interaction needs
    words = query.lower().split()
    
    # Multi-step commands usually need interaction
    if len(words) >= 4:
        return True
    
    # Check for sequence indicators (then, after, and, etc.)
    sequence_words = {"roi", "sau", "do", "tiep", "va", "then", "after", "also", "next"}
    if any(word in sequence_words for word in words):
        return True
    
    return False

def _requires_post_launch_interaction(query: str) -> bool:
    """Sync wrapper"""
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            return loop.run_until_complete(_requires_post_launch_interaction_ai(query))
    except:
        pass
    
    # Fallback: length heuristic
    return len(query.split()) >= 4


async def _should_try_startapps_search_ai(query: str) -> bool:
    """AI-based detection for searching Start Menu apps"""
    if not query or not query.strip():
        return False
    
    # Check for existing path/folder first
    folder_path = await _resolve_shell_folder_path_ai(query)
    if folder_path:
        return False
    
    # Try AI semantics
    if get_semantics_analyzer:
        try:
            analyzer = get_semantics_analyzer()
            intent = await analyzer.analyze_intent(query)
            # Only search apps for launch intent
            return intent.intent_type in ["launch", "interaction"]
        except:
            pass
    
    # Smart detection: not folder-related, likely app launch
    normalized = _normalize_text(query)
    words = [part for part in re.split(r"[^a-z0-9]+", normalized) if part]
    
    # Short queries (likely app names) or queries suggesting opening something
    if len(words) <= 3:
        return True
    
    return False

def _should_try_startapps_search(query: str) -> bool:
    """Sync wrapper"""
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            return loop.run_until_complete(_should_try_startapps_search_ai(query))
    except:
        pass
    
    # Fallback: simple length check
    words = query.lower().split()
    return len(words) <= 3

def _window_process_id(hwnd: int) -> int:
    try:
        return int(win32process.GetWindowThreadProcessId(hwnd)[1] or 0)
    except Exception:
        return 0

def _window_class_name(hwnd: int) -> str:
    try:
        return str(win32gui.GetClassName(hwnd) or "")
    except Exception:
        return ""


def _virtual_screen_bounds() -> tuple[int, int, int, int]:
    try:
        left = int(win32api.GetSystemMetrics(getattr(win32con, "SM_XVIRTUALSCREEN", 76)) or 0)
        top = int(win32api.GetSystemMetrics(getattr(win32con, "SM_YVIRTUALSCREEN", 77)) or 0)
        width = max(1, int(win32api.GetSystemMetrics(getattr(win32con, "SM_CXVIRTUALSCREEN", 78)) or win32api.GetSystemMetrics(0) or 1280))
        height = max(1, int(win32api.GetSystemMetrics(getattr(win32con, "SM_CYVIRTUALSCREEN", 79)) or win32api.GetSystemMetrics(1) or 720))
        return left, top, width, height
    except Exception:
        return 0, 0, 1280, 720


def find_virtual_display() -> dict:
    """
    Tìm HMONITOR của màn hình ảo IDD.
    Không fallback về màn hình vật lý nếu không tìm thấy IDD.

    The ADAPTER name (EnumDisplayDevices(None, i).DeviceString — e.g. "USB Mobile
    Monitor Virtual Display Driver" for Amyuni/USBMMIDD) is the ONLY reliable
    signal: the monitor CHILD reads "Generic PnP Monitor" / "Generic Non-PnP
    Monitor" for both virtual AND ordinary physical monitors. Matching on the
    monitor child (or on a registry "an IDD exists somewhere" hint and then
    grabbing the first non-primary monitor) is exactly what made Skemi stream the
    user's real second monitor (e.g. 2400×1350) instead of the virtual display.
    """
    # 1) Strongest source of truth: phantom_core's adapter-based detector. It
    #    matches the virtual-display ADAPTER string and refuses to return a
    #    physical monitor, so it never streams the user's real screen.
    try:
        import phantom_core  # lazy import to avoid circulars
        strong = phantom_core.find_idd_monitor()
        if strong.get("found"):
            rect = strong.get("rect") or []
            if len(rect) == 4:
                x1, y1, x2, y2 = (int(v) for v in rect)
                return {
                    "found": True,
                    "hmonitor": int(strong.get("hmonitor") or 0),
                    "rect": [x1, y1, x2, y2],
                    "width": int(strong.get("width") or (x2 - x1)),
                    "height": int(strong.get("height") or (y2 - y1)),
                    "device": str(strong.get("device") or ""),
                }
    except Exception as exc:
        _phantom_debug(f"[FIND_IDD] phantom_core detector unavailable: {exc}")

    # 2) Local fallback — match on the ADAPTER DeviceString only (strong tokens).
    STRONG_ADAPTER_TOKENS = [
        "usb mobile monitor", "mobile monitor", "usbmmidd", "usbmm", "amyuni",
        "indirect", "idd", "virtualdisplay", "virtual display", "mttvdd",
        "itsmikethetech", "parsec", "parsecvda", "parsecvdd", "spacedesk",
        "skemi phantom",
    ]

    def is_strong_adapter(value: str) -> bool:
        if not value:
            return False
        lower = str(value).lower()
        return any(token in lower for token in STRONG_ADAPTER_TOKENS)

    try:
        monitors = win32api.EnumDisplayMonitors(None, None)
    except Exception as exc:
        return {"found": False, "message": str(exc)}

    # Build DISPLAYn -> adapter DeviceString map (the reliable signal).
    adapter_strings: Dict[str, str] = {}
    try:
        i = 0
        while i < 64:
            dev = win32api.EnumDisplayDevices(None, i)
            if not dev:
                break
            dn = str(getattr(dev, "DeviceName", "") or "")
            if not dn:
                break
            adapter_strings[dn] = str(getattr(dev, "DeviceString", "") or "")
            i += 1
    except Exception:
        pass

    for hMon, _, rect in monitors:
        try:
            info = win32api.GetMonitorInfo(hMon)
            device = str(info.get("Device", "") or "")
            if int(info.get("Flags") or 0) & 1:
                continue  # never the primary monitor
            adapter = adapter_strings.get(device, "")
            if is_strong_adapter(adapter) or is_strong_adapter(device):
                x1, y1, x2, y2 = rect
                return {
                    "found": True,
                    "hmonitor": int(hMon),
                    "rect": [x1, y1, x2, y2],
                    "width": x2 - x1,
                    "height": y2 - y1,
                    "device": f"{device} | {adapter}",
                }
        except Exception:
            continue

    # NO registry fallback that returns an arbitrary non-primary monitor — that
    # streamed the user's physical screen. If we can't positively identify the
    # IDD adapter, report not-found so Phantom routes to install/activate.
    return {
        "found": False,
        "message": "Không tìm thấy virtual display driver (IDD). Cần cài hoặc bật driver trước."
    }


def _capture_screen_region_sync(bounds: Dict[str, int]) -> Optional[Image.Image]:
    global _last_capture_error
    hdc_raw = 0
    src_dc = mem_dc = bmp = None
    try:
        _last_capture_error = ""
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        width = max(1, int(bounds.get("width", 0) or 0))
        height = max(1, int(bounds.get("height", 0) or 0))

        # v8.6: Use monitor-specific DC if device_name is provided to avoid DPI/coordinate confusion
        device_name = bounds.get("device")
        used_create_dc = False
        if device_name:
            # CRITICAL: a headless server process caches its display geometry (it has
            # no message pump to receive WM_DISPLAYCHANGE), so the width/height passed
            # in from GetMonitorInfo can be STALE (e.g. 2400x1350) while the device's
            # ACTUAL framebuffer is 1920x1080. BitBlt'ing the stale, larger size from
            # the smaller framebuffer yields content + a black L-shaped border — the
            # exact "black areas" bug. EnumDisplaySettings queries the driver directly
            # (not the cached geometry), so use it to get the true current resolution.
            with contextlib.suppress(Exception):
                live = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
                lw, lh = int(live.PelsWidth), int(live.PelsHeight)
                if lw > 0 and lh > 0:
                    width, height = lw, lh
            hdc_raw = win32gui.CreateDC("DISPLAY", device_name, None)
            used_create_dc = True
        else:
            hdc_raw = win32gui.GetDC(0)
            
        if not hdc_raw:
            return None
            
        src_dc = win32ui.CreateDCFromHandle(hdc_raw)
        mem_dc = src_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(src_dc, width, height)
        mem_dc.SelectObject(bmp)
        # v1.2.5: REMOVED CAPTUREBLT (0x40000000) - this flag causes physical mouse cursor jitter/flicker
        # If we are using a specific monitor DC, the coordinates are relative to THAT monitor (0,0)
        src_x = 0 if device_name else left
        src_y = 0 if device_name else top
        mem_dc.BitBlt((0, 0), (width, height), src_dc, (src_x, src_y), win32con.SRCCOPY)
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1).convert("RGB")
        
        # v5.3: Enhanced Black Screen detection and PIL fallback
        if img and img.getbbox() is None:
            _phantom_debug("[CAPTURE] GDI returned black. Using ImageGrab fallback.")
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)
            
        return img
    except Exception as e:
        import traceback
        _last_capture_error = f"GDI failed: {e}"
        
        # v1.1.81: Fallback to PIL ImageGrab which uses different internal APIs
        try:
            from PIL import ImageGrab
            # ImageGrab.grab(all_screens=True) works for multiple monitors
            full_img = ImageGrab.grab(all_screens=True)
            # Crop to requested bounds
            # Note: ImageGrab might have different coordinate system if DPI is weird
            # but usually it matches the virtual desktop.
            box = (left, top, left + width, top + height)
            fallback_img = full_img.crop(box)
            if fallback_img and fallback_img.getbbox() is not None:
                # print(f"[CAPTURE] Successfully used ImageGrab fallback for {bounds}")
                return fallback_img.convert("RGB")
        except Exception as fexc:
            _last_capture_error = f"ImageGrab failed: {fexc}"
            _phantom_debug(f"[CAPTURE ERROR] ImageGrab fallback also failed: {fexc}")

        # v1.1.78: Recursive retry once for GDI if fallback also failed
        time.sleep(0.05)
        try:
            if not getattr(_capture_screen_region_sync, "_is_retry", False):
                _capture_screen_region_sync._is_retry = True
                res = _capture_screen_region_sync(bounds)
                _capture_screen_region_sync._is_retry = False
                return res
        except Exception: pass
        _last_capture_error = _last_capture_error or "Unknown capture error."
        return None
    finally:
        with contextlib.suppress(Exception):
            if mem_dc:
                mem_dc.DeleteDC()
        with contextlib.suppress(Exception):
            if src_dc:
                src_dc.DeleteDC()
        with contextlib.suppress(Exception):
            if bmp:
                win32gui.DeleteObject(bmp.GetHandle())
        with contextlib.suppress(Exception):
            if hdc_raw:
                # A DC from CreateDC must be freed with DeleteDC; one from GetDC(0)
                # must be freed with ReleaseDC. Using the wrong one leaks GDI
                # objects every frame and eventually starves capture → black frames.
                if used_create_dc:
                    win32gui.DeleteDC(hdc_raw)
                else:
                    win32gui.ReleaseDC(0, hdc_raw)


class JarvisDisplayManager:
    """Find, capture, and place windows on the monitor reserved for Jarvis."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_display: Dict[str, Any] = {}
        self._last_status: Dict[str, Any] = {}
        self._last_scan_at = 0.0
        self._last_driver_probe_at = 0.0
        self._last_driver_probe: Dict[str, Any] = {
            "driver_detected": False,
            "driver_status": "missing",
            "driver_version": "",
            "driver_provider": "",
        }
        self._guardian_active = False
        self._guardian_thread = None
        self._watched_pids = set()
        self._last_guardian_scan = 0.0

    def start_guardian(self):
        with self._lock:
            if self._guardian_active:
                return
            self._guardian_active = True
            self._guardian_thread = threading.Thread(target=self._guardian_loop, daemon=True)
            self._guardian_thread.start()
            _phantom_debug("[GUARDIAN] Started Jarvis Parallel Workspace isolation loop.")

    def stop_guardian(self):
        with self._lock:
            self._guardian_active = False
            self._watched_pids.clear()
            _phantom_debug("[GUARDIAN] Stopped isolation loop.")

    def add_watched_pid(self, pid: int):
        if not pid: return
        with self._lock:
            self._watched_pids.add(int(pid))
            _phantom_debug(f"[GUARDIAN] Now watching PID {pid} for isolation.")

    def _guardian_loop(self):
        while self._guardian_active:
            try:
                time.sleep(0.5) # Fast but non-blocking scan
                
                # Only proceed if we have an active phantom display
                status = self.ensure_ready(force=False)
                if not status.get("workspace_ready"):
                    continue

                # Snatch AI windows
                def enum_cb(hwnd, _):
                    if not win32gui.IsWindow(hwnd): return True
                    if not win32gui.IsWindowVisible(hwnd): return True
                    
                    pid = _window_process_id(hwnd)
                    with self._lock:
                        if pid in self._watched_pids:
                            # Verify if window is inside the workspace
                            if not self.contains_hwnd(hwnd):
                                _phantom_debug(f"[GUARDIAN] Snatching window {hwnd} (PID {pid}) to Jarvis Workspace.")
                                self.move_window_here(hwnd, maximize=True)
                    return True

                win32gui.EnumWindows(enum_cb, None)
                self._last_guardian_scan = time.time()

            except Exception as e:
                _phantom_debug(f"[GUARDIAN ERROR] {e}")
                time.sleep(2.0)


    def _driver_presence_hint(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force and (now - self._last_driver_probe_at) < 30.0:
            return dict(self._last_driver_probe)
        
        probe = {
            "driver_detected": False,
            "driver_status": "missing",
            "driver_version": "",
            "driver_provider": "",
        }
        
        # v2.0: Check for ANY virtual display driver (not just Skemi specific)
        # Look for virtual monitors/displays using multiple detection methods
        try:
            # Method 1: Check for virtual display/monitors in PnP
            ps = (
                "Get-CimInstance Win32_PnPEntity | "
                "Where-Object { $_.PNPClass -match 'Monitor|Display' } | "
                "Select-Object Name,Status,ConfigManagerErrorCode,DeviceID | ConvertTo-Json -Compress"
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=5.0,
                creationflags=creationflags,
            )
            output = result.stdout or ""
            
            # Check for any virtual display indicators
            virtual_tokens = [
                "virtual", "usbmmidd", "mttvdd", "iddsample", "amyuni", "indirect",
                "parsec", "spacedesk", "superdisplay", "duet", "xdisplay", "splashtop",
                "displaylink", "dlacx", "dlproduction", "vmulti", "vdesk", "mobile monitor",
                "mobilemonitor", "generic monitor", "generic pnp monitor", "pnp-monitor"
            ]
            
            try:
                entities = json.loads(output) if output.strip() else []
                if not isinstance(entities, list):
                    entities = [entities] if entities else []
                
                for ent in entities:
                    if not ent:
                        continue
                    name = str(ent.get("Name") or "").lower()
                    device_id = str(ent.get("DeviceID") or "").lower()
                    code = ent.get("ConfigManagerErrorCode")
                    status = str(ent.get("Status") or "").upper()
                    
                    # v8.6: Explicit usbmmidd detection
                    if "usbmmidd" in device_id or "usbmmidd" in name:
                        probe["driver_detected"] = True
                        probe["driver_status"] = "active" if status == "OK" and (not code or code == 0) else "inactive"
                        probe["driver_provider"] = "USB Mobile Monitor (usbmmidd)"
                        _phantom_debug(f"  [DRIVER] usbmmidd detected: {status} (Code {code})")
                        break
                    
                    # Check if it's a virtual display (not just our specific tokens)
                    is_virtual = any(t in name or t in device_id for t in virtual_tokens)
                    is_generic_virtual = "usb\\vid_" in device_id and "monitor" in name
                    
                    if is_virtual or is_generic_virtual:
                        _phantom_debug(f"[DRIVER PROBE] Detected virtual: {name} ({device_id})")
                        probe["driver_detected"] = True
                        probe["driver_provider"] = ent.get("Name", "Virtual Display Driver")
                        
                        # Check if driver is working properly
                        if (code is not None and code != 0) or status == "ERROR":
                            probe["driver_status"] = "error"
                            probe["driver_error"] = f"Driver has error code {code}. Check Device Manager."
                        else:
                            probe["driver_status"] = "installed_no_monitor"
                        break
                        
            except Exception:
                pass
            
            # Method 2: Check if virtual display files exist (Amyuni)
            if not probe["driver_detected"]:
                try:
                    base_dir = os.getcwd()
                    target_dir = os.path.join(base_dir, "Skemi_Virtual_Display")
                    for root, dirs, files in os.walk(target_dir):
                        if "deviceinstaller64.exe" in [f.lower() for f in files]:
                            probe["driver_detected"] = True
                            probe["driver_status"] = "installed_no_monitor"
                            probe["driver_provider"] = "Amyuni USBMMIDD"
                            break
                except Exception:
                    pass
            
            # Method 3: Check for MTTVDD (VirtualDrivers package)
            if not probe["driver_detected"]:
                try:
                    package_root = os.path.join(
                        os.environ.get("LOCALAPPDATA", ""),
                        "Microsoft",
                        "WinGet",
                        "Packages",
                    )
                    if os.path.isdir(package_root):
                        for name in os.listdir(package_root):
                            if "virtualdisplay" in name.lower():
                                probe["driver_detected"] = True
                                probe["driver_status"] = "installed_no_monitor"
                                probe["driver_provider"] = "VirtualDrivers Package"
                                break
                except Exception:
                    pass
                    
        except Exception as exc:
            probe["driver_status"] = "error"
            probe["driver_error"] = str(exc)
            
        self._last_driver_probe_at = now
        self._last_driver_probe = dict(probe)
        return dict(probe)

    def enumerate_displays(self) -> List[Dict[str, Any]]:
        displays: List[Dict[str, Any]] = []
        skemi_tokens = _phantom_driver_tokens()
        try:
            monitors = win32api.EnumDisplayMonitors(None, None)
            _phantom_debug(f"[ENUM DEBUG] Found {len(monitors)} monitors from win32api")
        except Exception as e:
            _phantom_debug(f"[ENUM DEBUG] win32api.EnumDisplayMonitors failed: {e}")
            monitors = []
        for index, item in enumerate(monitors):
            try:
                hmonitor = item[0]
                try:
                    hmonitor_handle = int(hmonitor)
                except Exception:
                    hmonitor_handle = 0
                info = win32api.GetMonitorInfo(hmonitor)
                rect = tuple(int(v) for v in info.get("Monitor", tuple(item[2])))
                work = tuple(int(v) for v in info.get("Work", rect))
                left, top, right, bottom = rect
                width = max(0, right - left)
                height = max(0, bottom - top)
                _phantom_debug(f"[ENUM DEBUG] Monitor {index}: rect={rect} width={width} height={height}")
                if width <= 0 or height <= 0:
                    _phantom_debug(f"[ENUM DEBUG] Skipping monitor {index}: invalid dimensions")
                    continue
                device = str(info.get("Device") or f"DISPLAY{index + 1}")
                flags = int(info.get("Flags") or 0)
                primary = bool(flags & 1)
                display_names = [device]
                direct_display_names = [device]
                with contextlib.suppress(Exception):
                    adapter = win32api.EnumDisplayDevices(device, 0)
                    adapter_names = [
                        str(getattr(adapter, "DeviceString", "") or ""),
                        str(getattr(adapter, "DeviceID", "") or ""),
                    ]
                    display_names.extend(adapter_names)
                    direct_display_names.extend(adapter_names)
                with contextlib.suppress(Exception):
                    monitor_adapter = win32api.EnumDisplayDevices(device, 1)
                    monitor_names = [
                        str(getattr(monitor_adapter, "DeviceName", "") or ""),
                        str(getattr(monitor_adapter, "DeviceString", "") or ""),
                        str(getattr(monitor_adapter, "DeviceID", "") or ""),
                    ]
                    display_names.extend(monitor_names)
                    direct_display_names.extend(monitor_names)
                    
                    # v8.6: Explicitly check for usbmmidd or other known virtual driver IDs
                    for m_id in monitor_names:
                        if any(token in m_id.lower() for token in ["usbmmidd", "mttvdd", "iddsample", "parsec", "spacedesk"]):
                            skemi_driver_hint = True
                            strong_virtual_hint = True
                            _phantom_debug(f"  [ENUM] Strong virtual match found in ID: {m_id}")
                
                # The rest of the display metadata is optional and can be slow on some systems.
                # We already have enough information from EnumDisplayDevices to detect virtual displays.
                direct_name_key = _normalize_text(" ".join(direct_display_names))
                name_key = _normalize_text(" ".join(display_names))
                
                # Check device name directly for virtual display keywords
                device_lower = device.lower()
                device_virtual_hint = any(keyword.lower() in device_lower for keyword in ["IDD", "Virtual", "Indirect"])
                
                # v6.0 OVERHAUL: Definitive prioritized tokens
                strong_virtual_tokens = [
                    "virtual", "idd", "indirect", "indirectdisplay", "amyuni", "iddsample", "mttvdd",
                    "usbmmidd", "usbmm", "parsec", "spacedesk", "superdisplay", "duet", "xdisplay",
                    "splashtop", "displaylink", "usbdisplay", "mobilemonitor", "mobile monitor",
                    "vmulti", "vdesk", "phantom", "default_monitor",
                ]
                weak_virtual_tokens = [
                    "generic monitor", "generic pnp monitor", "pnp-monitor", "non-pnp", "nonpnp",
                ]
                skemi_tokens_extended = skemi_tokens + ("skemi", "phantom")
                
                strong_virtual_hint = device_virtual_hint or any(token in direct_name_key for token in strong_virtual_tokens)
                generic_virtual_hint = strong_virtual_hint or any(token in direct_name_key for token in weak_virtual_tokens)
                skemi_driver_hint = any(token in direct_name_key for token in skemi_tokens_extended)
                
                # Auto-detect driver provider from display name
                driver_provider = ""
                if skemi_driver_hint:
                    driver_provider = "Skemi Phantom Display"
                elif "usbmmidd" in name_key or "amyuni" in name_key:
                    driver_provider = "Amyuni USBMMIDD"
                elif "mttvdd" in name_key:
                    driver_provider = "MTTVDD Virtual Display"
                elif "parsec" in name_key:
                    driver_provider = "Parsec Virtual Display"
                elif "spacedesk" in name_key:
                    driver_provider = "Spacedesk"
                elif generic_virtual_hint:
                    driver_provider = "Virtual Display Driver"
                
                def _best_display_name(names):
                    # Prefer human-readable monitor titles over generic driver/device ids
                    # First pass: look for brand names in parentheses like (MSI MP251L E2)
                    for n in names:
                        if not n:
                            continue
                        if '(' in n and ')' in n:
                            # Extract content from last parentheses like "(MSI MP251L E2)"
                            start = n.rfind('(')
                            end = n.rfind(')')
                            if end > start:
                                candidate = n[start + 1:end].strip()
                                if candidate and len(candidate) > 3 and not candidate.lower().startswith('generic'):
                                    return candidate
                    
                    # Second pass: prefer names that don't look like device paths or generic names
                    for n in names:
                        if not n:
                            continue
                        clean = str(n).strip()
                        if not clean:
                            continue
                        lowered = clean.lower()
                        # Skip device paths and system identifiers
                        if lowered.startswith('\\\\.\\display'):
                            continue
                        if lowered.startswith('monitor\\'):
                            continue
                        if lowered.startswith('@system32'):
                            continue
                        if lowered.startswith('default_monitor'):
                            continue
                        if lowered.startswith('virtual display') or lowered.startswith('skemi phantom display'):
                            continue
                        if '\\' in clean and '{' in clean:  # Device ID format
                            continue
                        # Skip purely generic names unless they're our last resort
                        if 'generic' not in lowered and 'pnp' not in lowered:
                            return clean
                    
                    # Fall back to any non-empty name not just raw device id
                    for n in names:
                        if n and not str(n).strip().lower().startswith('\\\\.\\display'):
                            return str(n).strip()
                    return None
                
                friendly_name = _best_display_name(display_names)
                if not friendly_name:
                    friendly_name = device
                if friendly_name.lower().startswith('generic') or friendly_name.lower().startswith('default_monitor'):
                    if width and height:
                        friendly_name = f"Màn hình {index + 1} ({width}x{height})"
                    else:
                        friendly_name = f"Màn hình {index + 1}"
                
                _phantom_debug(f"  [ENUM] Display {index}: {friendly_name} strong={strong_virtual_hint} virtual={generic_virtual_hint} skemi={skemi_driver_hint}")
                displays.append({
                    "index": index,
                    "hmonitor": hmonitor_handle,
                    "id": device,
                    "device": device,
                    "name": friendly_name,
                    "driver_provider": driver_provider,
                    "hardware_id": next((name for name in display_names if "\\" in name or "DISPLAY" in name.upper()), ""),
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "width": width,
                    "height": height,
                    "work": {
                        "left": work[0],
                        "top": work[1],
                        "right": work[2],
                        "bottom": work[3],
                        "width": max(0, work[2] - work[0]),
                        "height": max(0, work[3] - work[1]),
                    },
                    "primary": primary,
                    "dpi_scale": 1.0,
                    "strong_virtual_hint": strong_virtual_hint,
                    "generic_virtual_hint": generic_virtual_hint,
                    "skemi_driver_hint": skemi_driver_hint,
                    "display_names": [name for name in display_names if name],
                })
                _phantom_debug(f"[ENUM DEBUG] Added display {index}: {friendly_name}")
            except Exception as e:
                _phantom_debug(f"  [ENUM ERROR] Monitor {index}: {type(e).__name__}: {e}")
                import traceback
                _phantom_debug(f"  [ENUM TRACEBACK] {traceback.format_exc()}")
                continue
        _phantom_debug(f"[ENUM DEBUG] Returning {len(displays)} displays")
        return displays

    def _select_display(self, displays: List[Dict[str, Any]], force: bool = False) -> Dict[str, Any]:
        # v8.6: CRITICAL - If we are in Phantom Mode, only accept displays that have virtual driver hints.
        # If no virtual display is active, return {} rather than falling back to a physical monitor.
        
        # First, try to find the exact IDD monitor
        virtual_info = find_virtual_display()
        if virtual_info["found"]:
            lr = virtual_info.get("rect") or []
            live = None
            if len(lr) == 4:
                lx, lty, lrr, lb = (int(v) for v in lr)
                lw, lh = max(0, lrr - lx), max(0, lb - lty)
                if lw > 0 and lh > 0:
                    live = {"left": lx, "top": lty, "right": lrr, "bottom": lb,
                            "width": lw, "height": lh}
            # Find the matching display in our list
            for d in displays:
                if d.get("hmonitor") == virtual_info["hmonitor"] and virtual_info["hmonitor"]:
                    _phantom_debug(f"  [SELECT] Selected IDD virtual display: {d.get('name')} (HMONITOR: {virtual_info['hmonitor']})")
                    d["display_role"] = "virtual_display"
                    d["isolation_level"] = "virtual_display"
                    # Overlay LIVE geometry from find_virtual_display (driver-direct via
                    # EnumDisplaySettings). enumerate_displays' bounds come from the
                    # server's CACHED GetMonitorInfo, which can be stale; placement
                    # (move_window_here) uses these, so they MUST be live.
                    if live:
                        d.update(live)
                        d["work"] = dict(live)
                    return d
            # No monitor matched (stale GDI cache missed the IDD, or hmonitor=0 from
            # the driver-direct fallback). Synthesize a display record from the live
            # rect so Phantom still works instead of reporting "no virtual display".
            if live:
                _phantom_debug(f"  [SELECT] IDD not in monitor list; synthesizing from live rect {lr}")
                dev = str(virtual_info.get("device") or "").split("|")[0].strip()
                synth = {
                    "index": -1,
                    "hmonitor": int(virtual_info.get("hmonitor") or 0),
                    "id": dev,
                    "device": dev,
                    "device_name": dev,
                    "name": f"Phantom Display ({live['width']}x{live['height']})",
                    "driver_provider": "",
                    "primary": False,
                    "display_role": "virtual_display",
                    "isolation_level": "virtual_display",
                    "strong_virtual_hint": True,
                    "skemi_driver_hint": False,
                    "dpi_scale": 1.0,
                }
                synth.update(live)
                synth["work"] = dict(live)
                return synth

        # Strict fallback: only strong virtual-driver evidence is acceptable.
        candidates = [d for d in displays if d.get("strong_virtual_hint") or d.get("skemi_driver_hint")]
        if candidates:
            # Prefer the one with the strongest hint
            selected = sorted(candidates, key=lambda x: (x.get("strong_virtual_hint", False), x.get("skemi_driver_hint", False)), reverse=True)[0]
            _phantom_debug(f"  [SELECT] Selected virtual display (fallback): {selected.get('name')} (ID: {selected.get('id')})")
            
            # Map old role system to the new strict selection
            selected["display_role"] = "virtual_display"
            selected["isolation_level"] = "virtual_display"
            return selected
        
        _phantom_debug("  [SELECT] No virtual displays found. Phantom Mode will wait for driver activation.")
        return {}

    def _ensure_idd_resolution(self, selected: Dict[str, Any],
                               min_width: int = 1280, min_height: int = 720,
                               target_width: int = 1920, target_height: int = 1080) -> Dict[str, Any]:
        """Bump the IDD virtual display to at least `target_width`×`target_height`.

        USBMMIDD / MttVDD often boot at a tiny default (640×480 or a vertical
        sliver).  We bump it so the streamed capture looks like a normal desktop.
        Returns the (possibly updated) `selected` dict.
        """
        width = int(selected.get("width") or 0)
        height = int(selected.get("height") or 0)
        if width >= min_width and height >= min_height:
            return selected  # already big enough

        device = str(selected.get("device_name") or selected.get("id") or "").split("|")[0].strip()
        if not device:
            # Try the first name-like value in the display record
            for key in ("id", "device_name", "device"):
                val = str(selected.get(key) or "").strip()
                if val and val.startswith("\\\\.\\"):
                    device = val
                    break
        if not device:
            _phantom_debug("[IDD_RES] Cannot determine device name for resolution bump.")
            return selected

        try:
            devmode = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
            devmode.PelsWidth = int(target_width)
            devmode.PelsHeight = int(target_height)
            devmode.BitsPerPel = 32
            devmode.Fields = (win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_BITSPERPEL)
            result = win32api.ChangeDisplaySettingsEx(device, devmode, win32con.CDS_UPDATEREGISTRY)
            if result == 0:
                _phantom_debug(f"[IDD_RES] Bumped {device} to {target_width}×{target_height}")
                # Re-enumerate to get the updated rect
                time.sleep(0.3)
                for d in self.enumerate_displays():
                    d_id = str(d.get("id") or "")
                    if d_id == device or str(d.get("device_name") or "") == device:
                        # Preserve role/isolation from original selection
                        d.setdefault("display_role", selected.get("display_role", "virtual_display"))
                        d.setdefault("isolation_level", selected.get("isolation_level", "virtual_display"))
                        d.setdefault("strong_virtual_hint", selected.get("strong_virtual_hint", True))
                        d.setdefault("skemi_driver_hint", selected.get("skemi_driver_hint", False))
                        return d
            else:
                _phantom_debug(f"[IDD_RES] ChangeDisplaySettingsEx returned {result}")
        except Exception as exc:
            _phantom_debug(f"[IDD_RES] Failed to bump resolution: {exc}")
        return selected

    def ensure_ready(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            _phantom_debug("[ENSURE_READY DEBUG] Called with force={}".format(force))
            now = time.time()
            # v8.5: Dynamic cache TTL - shorter if not ready, longer if healthy
            cache_ttl = 3.0 if not (self._last_status or {}).get("workspace_ready") else 12.0
            if not force and self._last_status and (now - self._last_scan_at) < cache_ttl:
                _phantom_debug("[ENSURE_READY DEBUG] Returning cached status (TTL={})".format(cache_ttl))
                return dict(self._last_status)
            _phantom_debug("[ENSURE_READY DEBUG] Calling enumerate_displays()")
            displays = self.enumerate_displays()
            _phantom_debug("[ENSURE_READY DEBUG] enumerate_displays() returned {} displays".format(len(displays)))
            selected = self._select_display(displays, force=force)

            # v9.0: Ensure IDD resolution is usable (USBMMIDD defaults to tiny)
            if selected:
                selected = self._ensure_idd_resolution(selected)

            # v5.2: Allow primary if it's a virtual display (role contains "virtual_display")
            is_virtual_display = selected and "virtual" in str(selected.get("display_role") or "").lower()
            ready = bool(selected and (not bool(selected.get("primary")) or is_virtual_display))
            capture_probe_ok = False
            capture_probe_black = False
            driver_probe = {"driver_detected": False, "driver_status": "missing", "driver_version": "", "driver_provider": ""}
            if ready:
                bounds_probe = {
                    "left": int(selected.get("left", 0)),
                    "top": int(selected.get("top", 0)),
                    "width": int(selected.get("width", 0)),
                    "height": int(selected.get("height", 0)),
                }
                probe_img = _capture_screen_region_sync(bounds_probe) if bounds_probe["width"] > 0 and bounds_probe["height"] > 0 else None
                capture_probe_ok = probe_img is not None
                capture_probe_black = bool(probe_img is not None and probe_img.getbbox() is None)
                if not capture_probe_ok:
                    ready = False
                    selected = {}
                    setup_state = "capture_unavailable"
                    driver_status = "installed_no_monitor"
                else:
                    setup_state = "ready"
                    driver_status = "ready"
                driver_probe = self._driver_presence_hint(force=force)
                bootstrap_required = False
                driver_provider = str(selected.get("driver_provider") or driver_probe.get("driver_provider") or "Virtual Display Driver") if selected else ""
            else:
                driver_probe = self._driver_presence_hint(force=force)
                
                # Health checks must be read-only. Driver install/enable is only
                # allowed from explicit user-triggered setup endpoints.

                if ready:
                    pass # already handled above
                elif str(driver_probe.get("driver_status") or "") == "error":
                    setup_state = "driver_error"
                    driver_status = "error"
                elif bool(driver_probe.get("driver_detected")):
                    setup_state = "driver_installed_no_monitor"
                    driver_status = "installed_no_monitor"
                else:
                    setup_state = "missing_driver"
                    driver_status = "missing"
                bootstrap_required = False
                driver_provider = ""

            # Check if selected is a virtual display (for primary allowance)
            is_virtual_display = selected and "virtual" in str(selected.get("display_role") or "").lower()
            
            reason = ""
            if not displays:
                reason = "Phantom Desktop unavailable."
                if setup_state == "missing_driver":
                    setup_state = "missing_driver"
                    driver_status = "missing"
                    bootstrap_required = False
            elif not selected:
                if setup_state == "missing_driver":
                    reason = "Phantom is not installed on this computer."
                elif setup_state == "driver_installed_no_monitor":
                    reason = "Phantom driver is installed, but the Phantom Desktop is not active."
                else:
                    reason = "Phantom Desktop missing."
            elif bool(selected.get("primary")) and not is_virtual_display:
                # Only reject primary if it's NOT a virtual display
                reason = "Phantom refuses to use the primary monitor to ensure isolation."
                selected = {}
            
            # v8.6: Localized setup messages
            setup_message = ""
            if not ready:
                if driver_probe.get("driver_detected"):
                    if driver_probe.get("driver_status") == "inactive":
                        setup_message = "Màn hình ảo đã cài nhưng chưa bật. Đang thử kích hoạt (Vui lòng chọn 'Yes' nếu hiện bảng UAC)."
                    else:
                        setup_message = "Driver ok nhưng chưa thấy màn hình ảo. Hãy đảm bảo usbmmidd đã được bật."
                else:
                    setup_message = "Chưa tìm thấy Driver màn hình ảo. Skemi cần driver để hoạt động Jarvis/Phantom."
            
            display_role = str(selected.get("display_role") or "") if selected else ""
            isolation_level = str(selected.get("isolation_level") or display_role or "") if selected else ""
            update_info = _phantom_update_status(str(driver_probe.get("driver_version") or ""))
            if bool(update_info.get("update_required")):
                setup_state = "update_available"
                bootstrap_required = True
            elif ready and bool(update_info.get("update_available")):
                setup_state = "update_available"
            status = {
                "workspace_kind": "virtual_display",
                "workspace_ready": ready,
                "setup_state": setup_state,
                "driver_status": driver_status if ready else driver_status,
                "driver_version": str(driver_probe.get("driver_version") or ""),
                "driver_provider": driver_provider,
                "bootstrap_required": False,
                "bootstrap_url": "",
                "display_id": str(selected.get("id") or "") if ready else "",
                "hmonitor": int(selected.get("hmonitor") or 0) if ready else 0,
                "display_role": display_role if ready else "",
                "isolation_level": isolation_level if ready else "none",
                "workspace_label": str(selected.get("name") or "Phantom Workspace") if ready else "Phantom Desktop",
                "display_bounds": {
                    "left": int(selected.get("left", 0)) if selected else 0,
                    "top": int(selected.get("top", 0)) if selected else 0,
                    "width": int(selected.get("width", 0)) if selected else 0,
                    "height": int(selected.get("height", 0)) if selected else 0,
                    "right": int(selected.get("right", 0)) if selected else 0,
                    "bottom": int(selected.get("bottom", 0)) if selected else 0,
                },
                "display_count": len(displays),
                "displays": displays,
                "safe_for_phantom": bool(ready and capture_probe_ok),
                "capture_probe_ok": bool(capture_probe_ok),
                "capture_probe_black": bool(capture_probe_black),
                "setup_required": not bool(ready),
                "install_available": bool(driver_probe.get("driver_detected", False)),
                "install_message": "" if ready else "Install or enable a virtual display, then check again.",
                "allowed_driver_tokens": list(_phantom_driver_tokens()),
                "last_launch_error": reason,
                "setup_message": setup_message if not ready else "",
                "launch_policy": "vision-only GUI control on the locked Phantom desktop",
                **update_info,
            }
            self._active_display = dict(selected) if ready else {}
            self._last_status = dict(status)
            self._last_scan_at = time.time()
            if ready:
                self.start_guardian()
            if ready and _phantom_debug_enabled():
                b = status.get("display_bounds", {})
                _phantom_debug(f"[DISPLAY] Ready: {status.get('display_id')} at ({b.get('left')},{b.get('top')}) size {b.get('width')}x{b.get('height')}")
            return dict(status)

    def status(self, force: bool = False) -> Dict[str, Any]:
        return self.ensure_ready(force=force)

    def active_bounds(self) -> Dict[str, int]:
        status = self.ensure_ready(force=False)
        return dict(status.get("display_bounds") or {}) if status.get("workspace_ready") else {}

    def capture(self) -> Optional[Image.Image]:
        status = self.ensure_ready(force=False)
        if not status.get("workspace_ready"):
            return None
        bounds = dict(status.get("display_bounds") or {})
        hmonitor = int(status.get("hmonitor") or 0)
        if hmonitor:
            with contextlib.suppress(Exception):
                info = win32api.GetMonitorInfo(hmonitor)
                rect = tuple(int(v) for v in info.get("Monitor", ()))
                if len(rect) == 4:
                    left, top, right, bottom = rect
                    bounds = {
                        "device": str(info.get("Device") or ""),
                        "left": left,
                        "top": top,
                        "right": right,
                        "bottom": bottom,
                        "width": max(0, right - left),
                        "height": max(0, bottom - top),
                    }
        img = _capture_screen_region_sync(bounds)
        if img is None:
            return None
        return img

    def move_window_here(self, hwnd: int, *, maximize: bool = True) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        status = self.ensure_ready(force=False)
        if not status.get("workspace_ready"):
            return False
        
        bounds = dict(status.get("display_bounds") or {})
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        width = max(320, int(bounds.get("width", 1280) or 1280))
        height = max(240, int(bounds.get("height", 720) or 720))
        display_id = status.get("display_id", "unknown")
        try:
            # v1.1.99: Force placement on monitor coordinates
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 4) # SW_SHOWNOACTIVATE
            
            # Remove any flags that might keep it on top of user monitor
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOPMOST:
                win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

            _phantom_debug(f"[MOVE] Setting window {hwnd} to ({left}, {top}) size {width}x{height} on {display_id}")
            flags = win32con.SWP_NOOWNERZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, left, top, width, height, flags)
            
            if maximize:
                with contextlib.suppress(Exception):
                    win32gui.ShowWindow(hwnd, 4) # SW_SHOWNOACTIVATE
            
            time.sleep(0.15) # Wait for OS to reposition
            rect = win32gui.GetWindowRect(hwnd)
            cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            _phantom_debug(f"[MOVE] Window now at {rect}, center ({cx}, {cy}), bounds ({left}, {top}, {left+width}, {top+height})")
            result = self.contains_hwnd(hwnd)
            _phantom_debug(f"[MOVE] contains_hwnd: {result}")
            return result
        except Exception as e:
            _phantom_debug(f"[DISPLAY] Move window here failed: {e}")
            return False

    def contains_hwnd(self, hwnd: int) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        status = self.ensure_ready(force=False)
        if not status.get("workspace_ready"):
            return False
        bounds = dict(status.get("display_bounds") or {})
        try:
            left = int(bounds.get("left", 0))
            top = int(bounds.get("top", 0))
            right = int(bounds.get("right", left + int(bounds.get("width", 0))))
            bottom = int(bounds.get("bottom", top + int(bounds.get("height", 0))))
            rect = win32gui.GetWindowRect(hwnd)
            cx = int((rect[0] + rect[2]) / 2)
            cy = int((rect[1] + rect[3]) / 2)
            return left <= cx < right and top <= cy < bottom
        except Exception:
            return False



jarvis_display_manager = JarvisDisplayManager()


def _foreground_window_handle() -> int:
    try:
        return int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return 0

def _find_window_for_pid(
    pid: int,
    prefer_tokens: Optional[List[str]] = None,
    *,
    include_hidden: bool = False,
    desktop_handle: Any = None,
    reject_handles: Optional[set[int]] = None,
) -> int:
    if not pid:
        return 0
    tokens = [token for token in (_normalize_text(item) for item in (prefer_tokens or []) if token)]
    candidates: list[tuple[int, int]] = []

    def enum_cb(hwnd, _):
        try:
            if not win32gui.IsWindow(hwnd):
                return True
            if int(hwnd) in rejected:
                return True
            if not include_hidden and not win32gui.IsWindowVisible(hwnd):
                return True
            if _window_process_id(hwnd) != pid:
                return True
            rect = win32gui.GetWindowRect(hwnd)
            width = max(0, rect[2] - rect[0])
            height = max(0, rect[3] - rect[1])
            area = width * height
            if area <= 0:
                return True
            title = _normalize_text(win32gui.GetWindowText(hwnd))
            cls = _normalize_text(_window_class_name(hwnd))
            if _is_generic_window_identity(title, cls):
                return True
            score = area
            if title:
                score += 10000 # v1.1.101: Prefer windows with titles
            if win32gui.IsWindowVisible(hwnd):
                score += 50000 # v1.1.101: Heavily prefer visible windows
            if "chrome" in cls or "edge" in cls or "widget" in cls:
                score += 8000
            if any(token in title for token in tokens):
                score += 30000
            candidates.append((score, hwnd))
        except Exception:
            pass
        return True

    try:
        if desktop_handle:
            win32gui.EnumDesktopWindows(desktop_handle, enum_cb, None)
        else:
            win32gui.EnumWindows(enum_cb, None)
    except Exception:
        return 0
    if not candidates:
        return 0
    candidates.sort(key=lambda item: item[0], reverse=True)
    return int(candidates[0][1] or 0)

def _wait_for_window_for_pid(
    pid: int,
    timeout: float = 6.0,
    prefer_tokens: Optional[List[str]] = None,
    *,
    include_hidden: bool = False,
    desktop_handle: Any = None,
    reject_handles: Optional[set[int]] = None,
) -> int:
    deadline = time.time() + max(0.2, float(timeout or 0.0))
    while time.time() < deadline:
        hwnd = _find_window_for_pid(
            pid,
            prefer_tokens=prefer_tokens,
            include_hidden=include_hidden,
            desktop_handle=desktop_handle,
            reject_handles=reject_handles,
        )
        if hwnd:
            return hwnd
        time.sleep(0.03 if include_hidden else 0.12)
    return 0

# ── Agent Session ──────────────────────────────────────────────────────

# --- ARCHITECTURAL CONSTANTS (v49.0) ---
PHANTOM_DESKTOP_NAME = "SkemiPhantom"
PHANTOM_DESKTOP_SHORT_NAME = "SkemiPhantom"

_global_mode = "live"
_has_created_virtual_desktop = False # Volatile flag for current server run
_target_desktop_index = -1 # legacy UI marker only; Jarvis workspaces use real virtual displays

# GUID của desktop AI đang khoá vào
locked_desktop_guid = None
locked_desktop_name = None

# Global flag for phantom agent loop
ai_phantom_active = False


class _WinGuid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_uuid_text(value: str) -> "_WinGuid":
    import uuid
    raw = uuid.UUID(str(value)).bytes_le
    guid = _WinGuid()
    guid.Data1 = int.from_bytes(raw[0:4], "little")
    guid.Data2 = int.from_bytes(raw[4:6], "little")
    guid.Data3 = int.from_bytes(raw[6:8], "little")
    guid.Data4 = (ctypes.c_ubyte * 8).from_buffer_copy(raw[8:16])
    return guid


def _uuid_text_from_winguid(value: "_WinGuid") -> str:
    import uuid
    raw = (
        int(value.Data1).to_bytes(4, "little")
        + int(value.Data2).to_bytes(2, "little")
        + int(value.Data3).to_bytes(2, "little")
        + bytes(bytearray(value.Data4))
    )
    return str(uuid.UUID(bytes_le=raw))


def _get_virtual_desktop_uuid_text_sync(index: int) -> str:
    try:
        import uuid
        import winreg
        if index < 0:
            return ""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            ids_blob, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
        offset = int(index) * 16
        if offset < 0 or offset + 16 > len(ids_blob):
            return ""
        return str(uuid.UUID(bytes_le=bytes(ids_blob[offset:offset + 16])))
    except Exception as exc:
        _phantom_debug(f"[DESKTOP] Could not read virtual desktop GUID for index {index}: {exc}")
        return ""

def _get_virtual_desktop_count_sync() -> int:
    """v1.1.31: Returns the number of Task View virtual desktops using the registry."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            try:
                # Primary method for Win 10/11: VirtualDesktopIDs contains all 16-byte GUIDs
                ids_blob, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
                return len(ids_blob) // 16
            except Exception:
                pass
        
        # Fallback: Count subkeys in VirtualDesktops\Desktops
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path + r"\Desktops") as key:
            i = 0
            while True:
                try:
                    winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break
            return max(1, i)
    except Exception as e:
        _phantom_debug(f"[DESKTOP DEBUG] Failed to count virtual desktops: {e}")
        return 1

def _get_all_desktops_sync() -> List[Dict[str, Any]]:
    """v1.1.32: Returns a list of all virtual desktops found in the registry."""
    desktops = []
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
        count = _get_virtual_desktop_count_sync()
        curr_idx = _get_current_virtual_desktop_index_sync()
        ids_blob = b""
        with contextlib.suppress(Exception):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                ids_blob, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
        
        for i in range(count):
            desktop_uuid = ""
            if ids_blob and (i * 16) + 16 <= len(ids_blob):
                with contextlib.suppress(Exception):
                    desktop_uuid = str(uuid.UUID(bytes_le=bytes(ids_blob[i * 16:(i * 16) + 16])))
            name = f"Desktop {i+1}"
            if desktop_uuid:
                with contextlib.suppress(Exception):
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path + rf"\Desktops\{desktop_uuid}") as desktop_key:
                        custom_name, _ = winreg.QueryValueEx(desktop_key, "Name")
                        custom_name = str(custom_name or "").strip()
                        if custom_name:
                            name = custom_name
            desktops.append({
                "id": desktop_uuid or f"desktop_{i}",
                "name": name,
                "index": i,
                "is_current": (i == curr_idx)
            })
    except Exception as e:
        _phantom_debug(f"[DESKTOP DEBUG] Failed to list desktops: {e}")
        desktops = [{"id": "desktop_0", "name": "Desktop 1", "index": 0, "is_current": True}]
    return desktops


def _get_window_desktop_uuid_text_sync(hwnd: int) -> str:
    if hwnd <= 0:
        return ""
    try:
        if not win32gui.IsWindow(hwnd):
            return ""
        ole32 = ctypes.OleDLL("ole32")
        clsid = _guid_from_uuid_text("{aa509086-5ca9-4c25-8f95-589d3c07b48a}")
        iid = _guid_from_uuid_text("{a5cd92ff-29be-454c-8d04-d82879fb3f1b}")
        manager = ctypes.c_void_p()
        vtbl = None
        coinit_hr = ole32.CoInitialize(None)
        did_init = coinit_hr >= 0
        try:
            hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(manager))
            if hr < 0 or not manager.value:
                return ""
            vtbl = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            get_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(_WinGuid))(vtbl[4])
            actual_guid = _WinGuid()
            hr = get_fn(manager, wintypes.HWND(int(hwnd)), ctypes.byref(actual_guid))
            if hr < 0:
                return ""
            return _uuid_text_from_winguid(actual_guid)
        finally:
            if manager.value:
                with contextlib.suppress(Exception):
                    if vtbl:
                        release_fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
                        release_fn(manager)
            if did_init:
                with contextlib.suppress(Exception):
                    ole32.CoUninitialize()
    except Exception:
        return ""


def _get_current_virtual_desktop_index_sync() -> int:
    """v1.1.31: Returns the 0-indexed position of the current virtual desktop."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
        all_ids = []
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            ids_blob, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
            for i in range(0, len(ids_blob), 16):
                all_ids.append(ids_blob[i:i+16])
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                curr_id, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
                if curr_id in all_ids:
                    return all_ids.index(curr_id)
        except: pass
        return -1
    except:
        return -1

def _switch_to_virtual_desktop_index_sync(target_index: int, force_user_view: bool = False):
    """Switch to target virtual desktop for AI isolation. User stays on their desktop."""
    try:
        if target_index < 0:
            return
        current = _get_current_virtual_desktop_index_sync()
        if current == target_index:
            return
        
        # Calculate direction
        diff = target_index - current
        if diff > 0:
            # Move right
            for _ in range(diff):
                _send_key_combo_sync(["win", "ctrl", "right"])
                time.sleep(0.1)
        else:
            # Move left
            for _ in range(-diff):
                _send_key_combo_sync(["win", "ctrl", "left"])
                time.sleep(0.1)
        
        _phantom_debug(f"[DESKTOP] AI switched to virtual desktop {target_index}")
    except Exception as e:
        _phantom_debug(f"[DESKTOP ERROR] Failed to switch: {e}")

def activate_virtual_desktop_index(target_index: int) -> bool:
    """Activate the selected Windows virtual desktop before Phantom capture starts."""
    try:
        target_index = int(target_index)
    except Exception:
        return False
    if target_index < 0:
        return False
    try:
        from pyvda import get_virtual_desktops

        desktops = list(get_virtual_desktops())
        if target_index >= len(desktops):
            return False
        # v1.2.0: Prevent physical desktop switch which disrupts user focus
        # desktops[target_index].go() 
        time.sleep(0.4)
        return True
    except Exception as exc:
        # v1.2.4: DISABLE FALLBACK HOTKEYS - they disrupt user focus and cause "jumping"
        # _switch_to_virtual_desktop_index_sync(target_index)
        time.sleep(0.4)
        # return _get_current_virtual_desktop_index_sync() == target_index
        return True # Return true anyway; let capture engine handle it

def _send_key_combo_sync(keys: List[str]):
    vkeys = {"win": 0x5B, "ctrl": 0x11, "left": 0x25, "right": 0x27, "d": 0x44}
    # Press keys in order
    for k in keys:
        ctypes.windll.user32.keybd_event(vkeys[k.lower()], 0, 0, 0)
        time.sleep(0.05)
    time.sleep(0.2) # Increased hold time for OS detection
    # Release keys in reverse order
    for k in reversed(keys):
        ctypes.windll.user32.keybd_event(vkeys[k.lower()], 0, 2, 0)
        time.sleep(0.02)

def create_new_desktop() -> Dict[str, Any]:
    """Create a Windows virtual desktop and return the actual new index."""
    try:
        from pyvda import VirtualDesktop, get_virtual_desktops

        before = len(get_virtual_desktops())
        VirtualDesktop.create()
        time.sleep(0.4)
        after = get_virtual_desktops()

        if len(after) <= before:
            raise RuntimeError("Windows không tạo được desktop mới")

        new_index = len(after) - 1
        return {
            "success": True,
            "index": new_index,
            "name": f"Desktop {new_index + 1}",
            "desktop_obj": after[-1]
        }
    except Exception as pyvda_error:
        raise RuntimeError(f"Windows did not create a new desktop via pyvda: {pyvda_error}")


def lock_to_desktop(desktop_index: int) -> dict:
    global locked_desktop_guid, locked_desktop_name

    desktops = get_virtual_desktops()
    if desktop_index >= len(desktops):
        return {"success": False, "error": "Desktop index không hợp lệ"}

    target = desktops[desktop_index]
    locked_desktop_guid = target.id  # GUID — không đổi khi tạo/xoá desktop khác
    locked_desktop_name = f"Desktop {desktop_index + 1}"

    # KHÔNG gọi target.go() — không switch màn hình user
    # Chỉ lưu GUID để track

    return {
        "success": True,
        "guid": str(locked_desktop_guid),
        "name": locked_desktop_name
    }


def create_and_lock() -> dict:
    global locked_desktop_guid, locked_desktop_name

    before = get_virtual_desktops()
    before_guids = {d.id for d in before}

    VirtualDesktop.create()

    # Poll cho đến khi desktop mới xuất hiện
    for _ in range(30):
        time.sleep(0.1)
        after = get_virtual_desktops()
        new_ones = [d for d in after if d.id not in before_guids]
        if new_ones:
            target = new_ones[0]
            locked_desktop_guid = target.id
            locked_desktop_name = f"Desktop {len(after)}"
            # KHÔNG gọi go() — không switch màn hình user
            return {
                "success": True,
                "guid": str(locked_desktop_guid),
                "name": locked_desktop_name
            }

    return {"success": False, "error": "Không tạo được desktop mới"}


def _find_desktop_shell_window() -> int:
    for cls in ("WorkerW", "Progman"):
        try:
            hwnd = win32gui.FindWindow(cls, None)
            if hwnd and win32gui.IsWindow(hwnd):
                return hwnd
        except Exception:
            continue
    return 0


async def run_agent_loop(command: str, websocket, virtual_display_rect: list):
    """ 
    Vòng lặp AI agent thao tác trên Desktop đã khoá.
    Chỉ dùng PostMessage, không dùng SendInput hay subprocess.
    """
    global ai_phantom_active
    ai_phantom_active = True

    vx1, vy1, vx2, vy2 = virtual_display_rect
    vw = vx2 - vx1
    vh = vy2 - vy1

    max_steps = 20
    step = 0

    await ws_send(websocket, {"type": "agent_start", "command": command})

    while step < max_steps and ai_phantom_active:
        step += 1

        # 1. Capture màn hình ảo
        frame_b64 = capture_virtual_display(virtual_display_rect)
        if not frame_b64:
            break

        await ws_send(websocket, {
            "type": "thinking",
            "step": step,
            "message": f"Bước {step}: Đang phân tích..."
        })

        # 2. Hỏi vision model
        action = await ask_vision_model(frame_b64, command, step)
        if not action:
            break

        if action.get("done"):
            await ws_send(websocket, {
                "type": "agent_done",
                "message": action.get("summary", action.get("description", "Hoàn thành."))
            })
            break

        action_type = str(action.get("action") or "").lower()
        rel_x = float(action.get("x_pct", 0))  # % chiều ngang stream
        rel_y = float(action.get("y_pct", 0))  # % chiều dọc stream

        # Normalize coordinates
        rel_x = max(0.0, min(1.0, rel_x))
        rel_y = max(0.0, min(1.0, rel_y))

        # Tính tọa độ tuyệt đối trên màn hình ảo
        abs_x = int(vx1 + rel_x * vw)
        abs_y = int(vy1 + rel_y * vh)

        # Tìm HWND tại tọa độ đó trên màn hình ảo
        hwnd = 0
        try:
            hwnd = win32gui.WindowFromPoint((abs_x, abs_y))
        except Exception:
            hwnd = 0

        if not hwnd or not win32gui.IsWindow(hwnd):
            hwnd = _find_desktop_shell_window()

        executed = False
        if action_type == "click" and hwnd:
            client_pt = win32gui.ScreenToClient(hwnd, (abs_x, abs_y))
            ai_click(hwnd, client_pt[0], client_pt[1])
            executed = True

        elif action_type == "type" and hwnd:
            text = action.get("text", "")
            ai_type(hwnd, text)
            executed = True

        elif action_type == "key" and hwnd:
            key = action.get("key", "")
            vk_map = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08}
            vk = vk_map.get(key.lower(), 0)
            if vk:
                ai_key(hwnd, vk)
                executed = True

        await ws_send(websocket, {
            "type": "executing",
            "action": action_type,
            "message": action.get("description", "") if executed else "No valid target window found"
        })

        await asyncio.sleep(0.8)

        # 4. Capture frame mới gửi về frontend
        new_frame = capture_virtual_display(virtual_display_rect)
        if new_frame:
            await ws_send(websocket, {"type": "frame", "image": new_frame})

        if action.get("done"):
            await ws_send(websocket, {
                "type": "agent_done",
                "message": action.get("summary", "Hoàn thành.")
            })
            break

    ai_phantom_active = False


def ai_click(hwnd: int, client_x: int, client_y: int):
    """
    Inject click trực tiếp vào cửa sổ trên Desktop AI.
    Con chuột vật lý của user không bị ảnh hưởng.
    """
    lParam = win32api.MAKELONG(client_x, client_y)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN,
                         win32con.MK_LBUTTON, lParam)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)


def ai_type(hwnd: int, text: str):
    """Gõ text vào cửa sổ, không dùng bàn phím vật lý."""
    for char in text:
        win32api.PostMessage(hwnd, win32con.WM_CHAR, ord(char), 0)


def ai_key(hwnd: int, vk_code: int):
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)


def capture_virtual_display(virtual_display_rect: list) -> Optional[str]:
    """
    Capture màn hình ảo IDD và trả về base64.
    """
    if virtual_display_rect:
        # Use provided rect
        vx1, vy1, vx2, vy2 = virtual_display_rect
        bounds = {
            "left": vx1,
            "top": vy1,
            "width": vx2 - vx1,
            "height": vy2 - vy1,
            "device": None  # Not needed for region capture
        }
    else:
        # Fallback to auto-detect
        virtual_info = find_virtual_display()
        if not virtual_info["found"]:
            return None
        
        bounds = {
            "left": virtual_info["rect"][0],
            "top": virtual_info["rect"][1],
            "width": virtual_info["width"],
            "height": virtual_info["height"],
            "device": virtual_info["device"]
        }
    
    img = _capture_screen_region_sync(bounds)
    if img is None:
        return None
    
    # Convert to base64
    from io import BytesIO
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return img_str



## PHẦN 2 — QUẢN LÝ DESKTOP BẰNG GUID

try:
    from pyvda import VirtualDesktop, get_virtual_desktops
except ImportError:
    VirtualDesktop = None
    def get_virtual_desktops() -> list:
        return []
    _phantom_debug("pyvda unavailable: desktop GUID management disabled")

import time

# State toàn cục
locked_desktop_guid = None
locked_desktop_name = None
virtual_display_info = None
ai_phantom_active = False


def list_desktops() -> list:
    """Liệt kê tất cả desktop hiện có, gọi fresh không cache."""
    try:
        desktops = get_virtual_desktops()
        current = VirtualDesktop.current()
        return [
            {
                "index": i,
                "guid": str(d.id),
                "name": f"Desktop {i + 1}",
                "is_current": d.id == current.id
            }
            for i, d in enumerate(desktops)
        ]
    except Exception as e:
        return []


def lock_to_existing_desktop(desktop_guid: str) -> dict:
    """
    Khoá AI vào desktop đã có theo GUID.
    KHÔNG gọi go() — không switch màn hình user.
    """
    global locked_desktop_guid, locked_desktop_name

    try:
        desktops = get_virtual_desktops()
        target = next((d for d in desktops if str(d.id) == desktop_guid), None)

        if not target:
            return {"success": False, "error": "Không tìm thấy desktop với GUID này"}

        index = desktops.index(target)
        locked_desktop_guid = target.id
        locked_desktop_name = f"Desktop {index + 1}"

        # TUYỆT ĐỐI KHÔNG GỌI target.go() Ở ĐÂY
        # User vẫn ở desktop của họ

        return {
            "success": True,
            "guid": str(locked_desktop_guid),
            "name": locked_desktop_name
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_and_lock_new_desktop() -> dict:
    """
    Tạo desktop mới, khoá AI vào đó.
    KHÔNG switch màn hình user.
    """
    global locked_desktop_guid, locked_desktop_name

    try:
        before_desktops = get_virtual_desktops()
        before_guids = {d.id for d in before_desktops}

        VirtualDesktop.create()

        # Poll cho đến khi desktop mới xuất hiện, tối đa 5 giây
        for _ in range(50):
            time.sleep(0.1)
            after = get_virtual_desktops()
            new_ones = [d for d in after if d.id not in before_guids]
            if new_ones:
                target = new_ones[0]
                locked_desktop_guid = target.id
                locked_desktop_name = f"Desktop {len(after)}"
                # KHÔNG gọi go()
                return {
                    "success": True,
                    "guid": str(locked_desktop_guid),
                    "name": locked_desktop_name
                }

        return {"success": False, "error": "Windows không tạo được desktop mới sau 5 giây"}
    except Exception as e:
        return {"success": False, "error": str(e)}


## PHẦN 3 — STREAM MÀN HÌNH ẢO QUA WEBRTC

# pip install aiortc opencv-python-headless numpy Pillow
import asyncio, base64, io
import numpy as np
from PIL import Image
import win32api, win32gui, win32ui, win32con
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
import av

class VirtualDisplayTrack(VideoStreamTrack):
    """
    Capture màn hình ảo theo HMONITOR, stream qua WebRTC.
    Target 60fps.
    """
    def __init__(self, hmonitor: int, rect: list):
        super().__init__()
        self.hmonitor = hmonitor
        self.x1, self.y1, self.x2, self.y2 = rect
        self.width = self.x2 - self.x1
        self.height = self.y2 - self.y1

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        frame_bytes = self._capture_monitor()
        if not frame_bytes:
            # Trả frame đen nếu lỗi
            arr = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        else:
            img = Image.open(io.BytesIO(frame_bytes)).convert('RGB')
            arr = np.array(img)

        video_frame = av.VideoFrame.from_ndarray(arr, format='rgb24')
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def _capture_monitor(self) -> bytes:
        """Capture theo tọa độ rect của màn hình ảo."""
        try:
            hdc_screen = win32gui.GetDC(0)
            mfc_dc = win32ui.CreateDCFromHandle(hdc_screen)
            save_dc = mfc_dc.CreateCompatibleDC()

            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, self.width, self.height)
            save_dc.SelectObject(bitmap)

            # BitBlt từ tọa độ của màn hình ảo
            save_dc.BitBlt(
                (0, 0), (self.width, self.height),
                mfc_dc, (self.x1, self.y1),
                win32con.SRCCOPY
            )

            bmp_info = bitmap.GetInfo()
            bmp_data = bitmap.GetBitmapBits(True)

            img = Image.frombuffer(
                'RGB',
                (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_data, 'raw', 'BGRX', 0, 1
            )

            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)

            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(0, hdc_screen)

            return buf.getvalue()
        except Exception as e:
            return b''


# WebRTC peer connections
pcs = set()
active_track = None


@app.post("/webrtc/offer")
async def webrtc_offer(params: dict):
    global active_track

    if not virtual_display_info or not virtual_display_info.get("found"):
        return {"error": "Chưa tìm thấy virtual display"}

    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            await pc.close()
            pcs.discard(pc)

    active_track = VirtualDisplayTrack(
        hmonitor=virtual_display_info["hmonitor"],
        rect=virtual_display_info["rect"]
    )
    pc.addTrack(active_track)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }


@app.post("/webrtc/stop")
async def webrtc_stop():
    for pc in list(pcs):
        await pc.close()
    pcs.clear()
    return {"success": True}


## PHẦN 4 — AI AGENT THAO TÁC TRỰC TIẾP

import win32api, win32con, win32gui, ctypes, asyncio

ai_phantom_active = False


def ai_click(abs_x: int, abs_y: int):
    """
    Click tại tọa độ tuyệt đối trên màn hình ảo.
    Tìm HWND tại điểm đó rồi PostMessage — không dùng SendInput.
    Chuột vật lý của user không bị ảnh hưởng.
    """
    if not ai_phantom_active:
        return

    hwnd = win32gui.WindowFromPoint((abs_x, abs_y))
    if not hwnd:
        return

    # Convert sang tọa độ client của cửa sổ
    client_pt = win32gui.ScreenToClient(hwnd, (abs_x, abs_y))
    cx, cy = client_pt
    lParam = win32api.MAKELONG(cx, cy)

    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)


def ai_double_click(abs_x: int, abs_y: int):
    if not ai_phantom_active:
        return
    ai_click(abs_x, abs_y)
    import time; time.sleep(0.05)
    ai_click(abs_x, abs_y)


def ai_right_click(abs_x: int, abs_y: int):
    if not ai_phantom_active:
        return
    hwnd = win32gui.WindowFromPoint((abs_x, abs_y))
    if not hwnd:
        return
    client_pt = win32gui.ScreenToClient(hwnd, (abs_x, abs_y))
    lParam = win32api.MAKELONG(client_pt[0], client_pt[1])
    win32api.PostMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
    win32api.PostMessage(hwnd, win32con.WM_RBUTTONUP, 0, lParam)


def ai_type(abs_x: int, abs_y: int, text: str):
    if not ai_phantom_active:
        return
    hwnd = win32gui.WindowFromPoint((abs_x, abs_y))
    if not hwnd:
        return
    for char in text:
        win32api.PostMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
        import time; time.sleep(0.02)


def ai_key(abs_x: int, abs_y: int, vk_code: int):
    if not ai_phantom_active:
        return
    hwnd = win32gui.WindowFromPoint((abs_x, abs_y))
    if not hwnd:
        return
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
    import time; time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)


def ai_scroll(abs_x: int, abs_y: int, direction: str):
    if not ai_phantom_active:
        return
    hwnd = win32gui.WindowFromPoint((abs_x, abs_y))
    if not hwnd:
        return
    delta = -120 if direction == "down" else 120
    client_pt = win32gui.ScreenToClient(hwnd, (abs_x, abs_y))
    lParam = win32api.MAKELONG(client_pt[0], client_pt[1])
    win32api.PostMessage(hwnd, win32con.WM_MOUSEWHEEL,
                         win32api.MAKELONG(0, delta), lParam)


## PHẦN 5 — AI AGENT VÒNG LẶP

async def run_agent_loop(command: str, websocket):
    """
    Vòng lặp AI agent.
    AI nhìn stream → quyết định action → PostMessage vào HWND.
    Không dùng subprocess, không dùng SendInput global.
    """
    global ai_phantom_active
    ai_phantom_active = True

    if not virtual_display_info or not virtual_display_info.get("found"):
        await ws_send(websocket, {
            "type": "error",
            "message": "Chưa có virtual display. Setup trước."
        })
        return

    vx1 = virtual_display_info["rect"][0]
    vy1 = virtual_display_info["rect"][1]
    vw  = virtual_display_info["width"]
    vh  = virtual_display_info["height"]

    await ws_send(websocket, {"type": "agent_start", "command": command})

    max_steps = 20
    step = 0

    while step < max_steps and ai_phantom_active:
        step += 1

        # 1. Capture màn hình ảo
        if not active_track:
            break
        frame_bytes = active_track._capture_monitor()
        if not frame_bytes:
            break

        frame_b64 = base64.b64encode(frame_bytes).decode()

        await ws_send(websocket, {
            "type": "thinking",
            "step": step,
            "message": f"Bước {step}: Đang phân tích màn hình..."
        })

        # 2. Hỏi vision model
        action = await ask_vision_model(frame_b64, command, step)
        if not action:
            break

        action_type = action.get("action", "")

        # 3. Tính tọa độ tuyệt đối từ phần trăm trong stream
        rel_x = float(action.get("x_pct", 0.5))
        rel_y = float(action.get("y_pct", 0.5))
        abs_x = int(vx1 + rel_x * vw)
        abs_y = int(vy1 + rel_y * vh)

        await ws_send(websocket, {
            "type": "executing",
            "step": step,
            "action": action_type,
            "message": action.get("description", "")
        })

        # 4. Thực thi action
        vk_map = {
            "enter": win32con.VK_RETURN,
            "tab": win32con.VK_TAB,
            "esc": win32con.VK_ESCAPE,
            "backspace": win32con.VK_BACK,
            "space": win32con.VK_SPACE,
            "delete": win32con.VK_DELETE,
            "up": win32con.VK_UP,
            "down": win32con.VK_DOWN,
            "left": win32con.VK_LEFT,
            "right": win32con.VK_RIGHT,
        }

        if action_type == "click":
            ai_click(abs_x, abs_y)
        elif action_type == "double_click":
            ai_double_click(abs_x, abs_y)
        elif action_type == "right_click":
            ai_right_click(abs_x, abs_y)
        elif action_type == "type":
            ai_type(abs_x, abs_y, action.get("text", ""))
        elif action_type == "key":
            vk = vk_map.get(action.get("key", "").lower(), 0)
            if vk:
                ai_key(abs_x, abs_y, vk)
        elif action_type == "scroll":
            ai_scroll(abs_x, abs_y, action.get("direction", "down"))
        elif action_type == "done":
            await ws_send(websocket, {
                "type": "agent_done",
                "message": action.get("summary", "Hoàn thành.")
            })
            break

        # 5. Đợi UI phản hồi
        await asyncio.sleep(0.8)

        # 6. Frame mới gửi về frontend
        new_frame = active_track._capture_monitor()
        if new_frame:
            await ws_send(websocket, {
                "type": "frame",
                "image": base64.b64encode(new_frame).decode()
            })

    ai_phantom_active = False


async def ask_vision_model(frame_b64: str, command: str, step: int) -> dict:
    """Gọi vision model, trả về action dict."""
    import httpx, json, re

    system_prompt = """Bạn là AI agent điều khiển máy tính qua stream màn hình.

Trả về JSON duy nhất, không giải thích thêm:
{
  "action": "click" | "double_click" | "right_click" | "type" | "key" | "scroll" | "done",
  "x_pct": <0.0 đến 1.0 — vị trí ngang trong ảnh stream, 0=trái, 1=phải>,
  "y_pct": <0.0 đến 1.0 — vị trí dọc trong ảnh stream, 0=trên, 1=dưới>,
  "text": "<text cần gõ, chỉ khi action=type>",
  "key": "<tên phím: enter/tab/esc/backspace/space/delete/up/down/left/right>",
  "direction": "<up hoặc down, chỉ khi action=scroll>",
  "description": "<mô tả ngắn gọn đang làm gì>",
  "done": true | false,
  "summary": "<kết quả tóm tắt nếu done=true>"
}

QUY TẮC QUAN TRỌNG:
- KHÔNG bao giờ dùng lệnh terminal hay subprocess để mở app
- Muốn mở app: double_click vào icon trên desktop hoặc click thanh Search rồi gõ tên app
- Thao tác từng bước, một action mỗi lần
- x_pct và y_pct là phần trăm trong ảnh stream (0.0 đến 1.0)
- Nếu không thấy mục tiêu rõ ràng, scroll để tìm hoặc mở Start Menu"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Thay URL và model theo stack đang dùng trong project
            resp = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "moondream:latest",  # vision model đang có
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Lệnh: {command}\nBước: {step}"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{frame_b64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "stream": False
                }
            )

        raw = resp.json().get("message", {}).get("content", "")
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"Vision model error: {e}")

    return None


## PHẦN 6 — WEBSOCKET + API ENDPOINTS

from fastapi import WebSocket
import asyncio, json

active_ws_clients = set()


async def ws_send(ws: WebSocket, data: dict):
    try:
        await ws.send_json(data)
    except Exception:
        pass


@app.websocket("/ws/phantom")
async def phantom_ws(ws: WebSocket):
    await ws.accept()
    active_ws_clients.add(ws)
    agent_task = None

    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")

            if msg_type == "command":
                command = msg.get("command", "").strip()
                if not command:
                    continue
                if agent_task and not agent_task.done():
                    agent_task.cancel()
                agent_task = asyncio.create_task(
                    run_agent_loop(command, ws)
                )

            elif msg_type == "stop":
                global ai_phantom_active
                ai_phantom_active = False
                if agent_task:
                    agent_task.cancel()
                await ws_send(ws, {"type": "stopped"})

    except Exception:
        pass
    finally:
        active_ws_clients.discard(ws)
        ai_phantom_active = False
        if agent_task:
            agent_task.cancel()


# API Endpoints
@app.get("/api/phantom/check-driver")
async def api_check_driver():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, find_virtual_display)
    return result


@app.get("/api/phantom/list-desktops")
async def api_list_desktops():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, list_desktops)
    return {"desktops": result}


@app.post("/api/phantom/lock-desktop")
async def api_lock_desktop(params: dict):
    action = params.get("action")  # "existing" hoặc "new"
    guid = params.get("guid", "")

    loop = asyncio.get_event_loop()

    if action == "new":
        result = await loop.run_in_executor(None, create_and_lock_new_desktop)
    else:
        result = await loop.run_in_executor(
            None, lock_to_existing_desktop, guid
        )

    if result.get("success"):
        # Tìm và lưu virtual display info
        global virtual_display_info
        vd = await loop.run_in_executor(None, find_virtual_display)
        if not vd.get("found"):
            return {"success": False, "error": "Không tìm thấy virtual display sau khi khoá desktop"}
        virtual_display_info = vd

    return result


@app.post("/api/phantom/start-stream")
async def api_start_stream():
    if not virtual_display_info or not virtual_display_info.get("found"):
        return {"success": False, "error": "Chưa có virtual display"}
    global ai_phantom_active
    ai_phantom_active = True
    return {
        "success": True,
        "desktop_name": locked_desktop_name,
        "display": f"{virtual_display_info['width']}×{virtual_display_info['height']}"
    }


@app.post("/api/phantom/stop")
async def api_stop():
    global ai_phantom_active
    ai_phantom_active = False
    await webrtc_stop()
    return {"success": True}

_VISION_MODEL_MISSING: set = set()   # model names that 404'd (not installed) — fail fast


async def ask_vision_model(frame_b64: str, command: str, step: int):
    """
    Ask vision model for next action using x_pct/y_pct coordinates.
    """
    import httpx
    import json

    try:
        # Use the vision API to get action
        url = "http://127.0.0.1:11434/api/generate"
        model = os.environ.get("SKEMI_MODEL_VISION", "moondream:latest")
        if model in _VISION_MODEL_MISSING:
            # Model isn't installed — every call would 404. Without this guard the
            # loop hammered ollama ~1 req/s for minutes ("HTTP/1.1 404 Not Found"
            # storm in the server log) before giving a vague pause message.
            return {"action": "done", "done": True,
                    "description": f"Vision model '{model}' chưa được cài (ollama pull {model}).",
                    "summary": f"Thiếu model vision '{model}' — hãy cài bằng: ollama pull {model}"}
        prompt = VISION_SYSTEM_PROMPT + f"\n\nLệnh: {command}\nBước: {step}"

        # GLOBAL CONCURRENCY LOCK: Serializes all Ollama calls across all sessions
        async with GLOBAL_VISION_SEMAPHORE:
            for attempt in range(3):
                try:
                    payload = {"model": model, "prompt": prompt, "stream": False, "images": [frame_b64]}
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        r = await client.post(url, json=payload)
                        if r.status_code == 429:
                            wait_sec = (attempt + 1) * 2
                            await asyncio.sleep(wait_sec)
                            continue
                        if r.status_code == 404:
                            # Model not installed — remember it so the NEXT calls fail
                            # fast instead of re-hitting ollama every second.
                            _VISION_MODEL_MISSING.add(model)
                            return {"action": "done", "done": True,
                                    "description": f"Vision model '{model}' chưa được cài.",
                                    "summary": f"Thiếu model vision '{model}' — hãy cài bằng: ollama pull {model}"}
                        if r.status_code != 200:
                            if attempt == 2:
                                return {
                                    "action": "done",
                                    "description": f"Vision API error: HTTP {r.status_code}",
                                    "done": True,
                                    "summary": "Vision service returned error"
                                }
                            await asyncio.sleep(1)
                            continue

                        response = r.json().get("response", "")
                        if isinstance(response, dict):
                            return response
                        if isinstance(response, list) and response:
                            response = response[0]
                        response_text = str(response or "")
                        _phantom_debug(f"[VISION] Raw response: {response_text[:200]}...")

                        # Parse JSON response
                        try:
                            result = json.loads(response_text.strip())
                            return result
                        except json.JSONDecodeError:
                            # Try to extract JSON from response
                            import re
                            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                            if json_match:
                                result = json.loads(json_match.group())
                                return result
                            else:
                                return {
                                    "action": "done",
                                    "description": f"Vision parse error: {response_text[:100]}",
                                    "done": True,
                                    "summary": "Failed to parse vision response"
                                }

                except Exception as e:
                    if attempt == 2:
                        return {
                            "action": "done",
                            "description": f"Vision API error: {e}",
                            "done": True,
                            "summary": "Vision service unavailable"
                        }
                    await asyncio.sleep(1)

        return {
            "action": "done",
            "description": "Vision timeout",
            "done": True,
            "summary": "Vision request timed out"
        }

    except Exception as e:
        _phantom_debug(f"[VISION] Error: {e}")
        return {
            "action": "done",
            "description": f"Vision error: {e}",
            "done": True,
            "summary": "Vision system error"
        }

def create_visible_virtual_desktop():
    """Visible hotkey desktop creation is disabled for Phantom safety."""
    return _get_virtual_desktop_count_sync()


def create_virtual_desktop_safe() -> Dict[str, Any]:
    """Create a Windows Virtual Desktop through pyvda without switching user view."""
    before = _get_virtual_desktop_count_sync()
    try:
        created = create_new_desktop()
        after = _get_virtual_desktop_count_sync()
        return {
            "success": bool(created.get("success")),
            "safe": True,
            "count": int(after or before or 1),
            "index": int(created.get("index", -1)),
            "message": "Windows created a new desktop without switching the user's view.",
        }
    except Exception as exc:
        return {
            "success": False,
            "safe": True,
            "count": before,
            "message": str(exc),
        }


def _is_window_on_desktop_index_sync(hwnd: int, target_idx: int) -> bool:
    if hwnd <= 0 or target_idx < 0:
        return False
    target_uuid = _get_virtual_desktop_uuid_text_sync(int(target_idx))
    if not target_uuid:
        return False
    actual_uuid = _get_window_desktop_uuid_text_sync(int(hwnd))
    return bool(actual_uuid and actual_uuid.lower() == target_uuid.lower())


def _move_window_to_desktop_index_sync(hwnd: int, target_idx: int):
    """Move a window to a Windows Virtual Desktop by GUID without switching the user's view."""
    if hwnd <= 0 or target_idx <= 0:
        return False
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        target_uuid = _get_virtual_desktop_uuid_text_sync(int(target_idx))
        if not target_uuid:
            return False
        ole32 = ctypes.OleDLL("ole32")
        clsid = _guid_from_uuid_text("{aa509086-5ca9-4c25-8f95-589d3c07b48a}")
        iid = _guid_from_uuid_text("{a5cd92ff-29be-454c-8d04-d82879fb3f1b}")
        manager = ctypes.c_void_p()
        vtbl = None
        coinit_hr = ole32.CoInitialize(None)
        did_init = coinit_hr >= 0
        try:
            hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(manager))
            if hr < 0 or not manager.value:
                return False
            vtbl = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            move_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(_WinGuid))(vtbl[5])
            target_guid = _guid_from_uuid_text(target_uuid)
            hr = move_fn(manager, wintypes.HWND(int(hwnd)), ctypes.byref(target_guid))
            if hr < 0:
                return False
            time.sleep(0.05)
            return True
        finally:
            if manager.value:
                with contextlib.suppress(Exception):
                    if vtbl:
                        release_fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
                        release_fn(manager)
            if did_init:
                with contextlib.suppress(Exception):
                    ole32.CoUninitialize()
    except Exception as exc:
        _phantom_debug(f"[DESKTOP] MoveWindowToDesktop failed: {exc}")
        return False

def _phantom_window_capture_enabled() -> bool:
    # v2.0: Always use virtual_display mode for full desktop isolation
    # Window capture mode is deprecated - it causes mouse jitter and small stream
    return False

def _phantom_window_workspace_status(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = dict(base or {})
    status = {
        "workspace_kind": "window_capture",
        "workspace_ready": True,
        "setup_state": "ready",
        "driver_status": "not_required",
        "driver_version": "",
        "driver_provider": "",
        "bootstrap_required": False,
        "bootstrap_url": "",
        "display_id": "app_window",
        "display_role": "window_capture",
        "isolation_level": "window_only",
        "display_bounds": {},
        "display_count": int(data.get("display_count") or 0),
        "displays": list(data.get("displays") or []),
        "allowed_driver_tokens": [],
        "last_launch_error": "",
        "last_launch_error_code": "",
        "setup_message": "Phantom streams the locked desktop.",
        "launch_policy": "vision-only GUI control on the locked desktop",
        "update_state": "current",
        "update_available": False,
        "update_required": False,
        "latest_companion_version": "",
        "latest_driver_version": "",
        "update_url": "",
        "update_size_mb": "",
        "update_requires_admin": False,
        "update_message": "",
        "driver_package_present": False,
        "driver_package_path": "",
    }
    return status

def _jarvis_workspace_status(force: bool = False) -> Dict[str, Any]:
    # v6.5 Dynamic Display & Driver Detection
    # Always try to use jarvis_display_manager for accurate real-time display enumeration
    try:
        if jarvis_display_manager:
            status = jarvis_display_manager.status(force=force)
            # If driver is active/ready, ensure we report it as such to the UI
            if status.get("workspace_ready"):
                status["driver_status"] = "active"
                status["setup_state"] = "ready"
            return status
    except Exception as e:
        _phantom_debug(f"[WORKSPACE] jarvis_display_manager.status() failed: {e}")
    
    # v6.5: Fallback - enumerate displays directly to get accurate count and status
    try:
        displays = jarvis_display_manager.enumerate_displays() if jarvis_display_manager else []
        selected = jarvis_display_manager._select_display(displays, force=force) if jarvis_display_manager and displays else {}
        
        if selected and jarvis_display_manager:
            # Capture and check the selected display
            bounds = {
                "left": int(selected.get("left", 0)),
                "top": int(selected.get("top", 0)),
                "width": int(selected.get("width", 0)),
                "height": int(selected.get("height", 0)),
            }
            probe_img = _capture_screen_region_sync(bounds) if bounds["width"] > 0 and bounds["height"] > 0 else None
            capture_ok = probe_img is not None
            
            return {
                "workspace_kind": "virtual_display",
                "workspace_ready": bool(capture_ok),
                "setup_state": "ready" if capture_ok else "capture_unavailable",
                "driver_status": "active" if capture_ok else "installed_no_monitor",
                "driver_version": str(selected.get("driver_version") or ""),
                "driver_provider": str(selected.get("driver_provider") or "Virtual Display Driver"),
                "bootstrap_required": False,
                "bootstrap_url": "",
                "display_id": str(selected.get("id") or ""),
                "display_role": str(selected.get("display_role") or "virtual_display"),
                "isolation_level": str(selected.get("isolation_level") or "virtual_display"),
                "display_bounds": bounds,
                "display_count": len(displays),
                "displays": displays,
                "allowed_driver_tokens": [],
                "last_launch_error": "" if capture_ok else "Display capture unavailable",
                "last_launch_error_code": "" if capture_ok else "capture_unavailable",
                "setup_message": "Phantom streams the locked desktop.",
                "launch_policy": "vision-only GUI control on the locked desktop",
                "update_state": "current",
                "update_available": False,
                "update_required": False,
                "latest_companion_version": "",
                "latest_driver_version": "",
                "update_url": "",
                "update_size_mb": "",
                "update_requires_admin": False,
                "update_message": "",
                "driver_package_present": False,
                "driver_package_path": "",
            }
    except Exception as e:
        _phantom_debug(f"[WORKSPACE] Fallback enumeration failed: {e}")

    # Final fallback to native behavior if manager is missing
    try:
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
    except:
        width, height = 1920, 1080

    return {
        "workspace_kind": "virtual_display",
        "workspace_ready": False,
        "setup_state": "missing_driver",
        "driver_status": "missing",
        "driver_version": "",
        "driver_provider": "",
        "bootstrap_required": True,
        "bootstrap_url": PHANTOM_BOOTSTRAP_URL,
        "display_id": "",
        "display_role": "",
        "isolation_level": "",
        "display_bounds": {
            "left": 0,
            "top": 0,
            "width": width,
            "height": height
        },
        "display_count": 0,
        "displays": [],
        "allowed_driver_tokens": [],
        "last_launch_error": "Phantom Desktop unavailable.",
        "last_launch_error_code": "phantom_not_available",
        "setup_message": "No Phantom Desktop detected on this computer.",
        "launch_policy": "vision-only GUI control on the locked desktop",
        "update_state": "current",
        "update_available": False,
        "update_required": False,
        "latest_companion_version": "",
        "latest_driver_version": "",
        "update_url": "",
        "update_size_mb": "",
        "update_requires_admin": False,
        "update_message": "",
        "driver_package_present": False,
        "driver_package_path": "",
    }


def agent_module_jarvis_display_status(force: bool = False) -> Dict[str, Any]:
    return _jarvis_workspace_status(force=force)

def agent_module_update_mode(mode: str):
    global _global_mode
    _global_mode = mode
    
    if mode == "phantom":
        status = agent_module_jarvis_display_status(force=True)
        if status.get("workspace_ready"):
            _phantom_debug(f"[PHANTOM] Ready ({status.get('workspace_kind')}) target={status.get('display_id')}")
        else:
            _phantom_debug(f"[PHANTOM] Not ready: {status.get('last_launch_error')}")
    
    # Update all active sessions
    for session in active_sessions.values():
        session.update_mode(mode)

def switch_to_isolated_desktop() -> bool:
    """Switch AI context to the isolated phantom desktop."""
    try:
        desktop = get_or_create_phantom_desktop()
        if desktop:
            desktop.SetThreadDesktop()
            _phantom_debug("[DESKTOP] AI context switched to phantom desktop")
            return True
    except Exception as e:
        _phantom_debug(f"[DESKTOP ERROR] {e}")
    return False

def switch_to_default_desktop() -> bool:
    """Switch AI context back to default desktop."""
    try:
        h_desk = win32service.OpenDesktop("Default", 0, False, win32con.MAXIMUM_ALLOWED)
        if h_desk:
            h_desk.SetThreadDesktop()
            _phantom_debug("[DESKTOP] AI context switched to default desktop")
            return True
    except Exception as e:
        _phantom_debug(f"[DESKTOP ERROR] {e}")
    return False

def get_or_create_phantom_desktop():
    try:
        access = win32con.MAXIMUM_ALLOWED
        try:
            h_desk = win32service.OpenDesktop(PHANTOM_DESKTOP_SHORT_NAME, 0, False, access)
            if h_desk:
                _phantom_debug(f"[DESKTOP] Successfully opened existing isolated desktop: {PHANTOM_DESKTOP_SHORT_NAME}")
                return h_desk
        except Exception:
            h_desk = None
        
        _phantom_debug(f"[DESKTOP] Creating new isolated desktop: {PHANTOM_DESKTOP_SHORT_NAME}...")
        return win32service.CreateDesktop(PHANTOM_DESKTOP_SHORT_NAME, 0, access, None)
    except Exception as e:
        _phantom_debug(f"[DESKTOP ERROR] Failed to manage isolated desktop: {e}")
        return None

def _reset_thread_to_default_desktop():
    """Force current thread to connect back to the user's primary desktop."""
    try:
        h_desk = win32service.OpenDesktop("Default", 0, False, win32con.MAXIMUM_ALLOWED)
        if h_desk:
            # v1.1.17: Use handle method correctly
            h_desk.SetThreadDesktop()
            _phantom_debug("[DESKTOP] Thread successfully reset to Default desktop.")
            return True
    except Exception as e:
        if "requested resource is in use" not in str(e).lower():
            _phantom_debug(f"[DESKTOP] Failed to reset to Default desktop: {e}")
    return False

class DesktopAgentSession:
    def __init__(self, session_id: str, command: str, mode: str = "live", bypass_safety: bool = True, plan: Optional[Dict[str, Any]] = None, source: str = "manual", desktop_index: int = -1):
        global _target_desktop_index

        self.session_id = session_id
        self.command = command
        self.source = str(source or "manual").strip().lower()
        self.plan = dict(plan or {})
        self.route = str(self.plan.get("route") or "computer_task")
        self.tasks = self._normalize_plan_tasks(self.plan, command)
        self.current_task_index = 0 if self.tasks else -1
        self.task_results: List[Dict[str, Any]] = []
        self.mode = "live"  # default; overridden below
        self.bypass_safety = bool(bypass_safety)
        self.h_phantom_desk = None
        self.step_count = 0
        self.cancelled = self.agent_stopped = False
        self.target_window_hwnd = 0
        self._phantom_input_hwnd = 0
        self._live_last_target_hwnd = 0  # Live Control: last window the AI ghost-clicked
        self.target_window_title = ""
        self.target_window_class = ""
        self.target_process_id = 0
        self.current_url = ""
        self.web_interactive_elements: List[Dict[str, Any]] = []
        self.recent_actions: List[str] = []
        self.launch_target_tokens: List[str] = []
        self.last_model_thought = ""
        self._last_ai_action_desc = "Initializing..."
        self.last_result = ""
        self.session_error = ""
        self.is_thinking = False
        self.latest_live_b64 = ""
        self.latest_live_at = 0.0
        self.frame_version = 0
        self._capture_lock = asyncio.Lock()
        self._capture_task = None
        self.runtime_state = "starting"
        self._last_stream_img = None
        self._lost_frame_time = None
        self.h_desktop = None
        self._loop = None
        self.scale_x = self.scale_y = 1.0
        self.capture_w = self.capture_h = 0
        self._is_rate_limited = False
        self._last_rate_limit_time = 0.0
        self.vision_model_override = None
        self.capture_strategy_index = 0
        self.last_strategy_change_at = 0.0
        self._execute_task = None
        self.session_closed = False
        self.pending_confirmation: Dict[str, Any] = {}
        self.consent_reason = ""
        self._confirmation_future = None
        self.automation_mode = "vision_fallback"
        self.browser_cdp_port = 0
        self.browser_profile_dir = ""
        self.browser_offscreen = False
        self.offscreen_browser_pids: set[int] = set()
        self.user_revealed_target = False
        self._has_stealth_hidden_once = False
        self._stealth_first_hidden_at = 0.0
        self._stealth_sentry_running = False
        self._launch_baseline_handles: set[int] = set()
        self._owned_target_handles: set[int] = set()
        self.web_surface = None
        self.web_viewport_width = 1280
        self.web_viewport_height = 900
        self._last_web_snapshot_at = 0.0
        self._last_web_connect_attempt_at = 0.0
        self.action_overlay: Dict[str, Any] = {}
        self.workspace_kind = "screen"
        self.workspace_ready = False
        self.jarvis_display_status: Dict[str, Any] = {}
        self.last_launch_error = ""
        self.last_launch_error_code = ""
        
        # v1.1.17: Dedicated capture state for phantom isolation
        self._phantom_capture_img = None
        self._phantom_capture_thread = None
        self._phantom_capture_stop = threading.Event()
        self._phantom_capture_lock = threading.Lock()
        self._phantom_capture_frame = None
        
        # v52.0: Reliability Engine
        self.consecutive_black_frames = 0
        self.vision_health_status = "Healthy"
        self.desktop_index = int(desktop_index)
        self.preview_only = bool(self.plan.get("preview_only", False))
        self._last_virtual_desktop_preview_img = None
        self._last_virtual_desktop_preview_at = 0.0
        self._return_desktop_index = -1
        if self.desktop_index >= 0:
            _target_desktop_index = self.desktop_index
        
        self.update_mode(mode)
        active_sessions[self.session_id] = self
        # v6.9 FIX: Only lock physical input for NON-preview phantom sessions.
        # Preview sessions just stream the display and should NEVER block the user's mouse.
        if self.mode == "phantom" and not self.preview_only:
            with _input_shield_lock:
                global PHYSICAL_INPUT_LOCKED, is_isolated
                PHYSICAL_INPUT_LOCKED = True
                is_isolated = True


    def _normalize_plan_tasks(self, plan: Dict[str, Any], command: str) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        raw_tasks = plan.get("tasks") if isinstance(plan, dict) else []
        if isinstance(raw_tasks, list):
            for index, item in enumerate(raw_tasks):
                if not isinstance(item, dict):
                    continue
                goal = str(item.get("goal") or item.get("command") or item.get("title") or "").strip()
                title = str(item.get("title") or item.get("target") or goal or f"Task {index + 1}").strip()
                tasks.append({
                    "id": str(item.get("id") or f"task_{index + 1}"),
                    "title": title,
                    "goal": goal or title,
                    "target": str(item.get("target") or "").strip(),
                    "action": str(item.get("action") or "complete").strip() or "complete",
                    "modality": str(item.get("modality") or "unknown").strip().lower() or "unknown",
                    "requires_consent": bool(item.get("requires_consent", False)),
                    "status": str(item.get("status") or "pending"),
                    "result": str(item.get("result") or ""),
                })
        if not tasks and str(command or "").strip():
            tasks.append({
                "id": "task_1",
                "title": str(command).strip(),
                "goal": str(command).strip(),
                "target": "",
                "action": "complete",
                "modality": "unknown",
                "requires_consent": False,
                "status": "pending",
                "result": "",
            })
        return tasks

    @property
    def last_ai_action_desc(self) -> str:
        return getattr(self, "_last_ai_action_desc", "")

    @last_ai_action_desc.setter
    def last_ai_action_desc(self, value: str):
        val = str(value or "").strip()
        # v1.0.0: Throttle transient messages to prevent chat flickering
        transient = {"reading the current interface...", "looking for the next safe step...", "working", "analyzing..."}
        if val.lower() in transient and getattr(self, "_last_ai_action_desc", ""):
            # Only update transient messages every 3 seconds
            if time.time() - getattr(self, "_last_transient_update", 0) < 3.0:
                return
            self._last_transient_update = time.time()
        self._last_ai_action_desc = val

    def speak(self, text: str):
        """Skemi voice feedback via the shared voice engine (Only if source is voice)."""
        if self.source != "voice":
            print(f"[SKEMI JARVIS]: {text}")
            return
            
        import skemi_voice_engine
        voice = skemi_voice_engine.get_voice_engine()
        if not voice:
            # v1.0.9: Try to initialize engine if missing
            try:
                from skemi_voice_engine import SkemiVoiceEngine
                voice = SkemiVoiceEngine()
            except: pass
            
        if voice:
            voice.speak(text)
        else:
            print(f"[SKEMI JARVIS]: {text}")

    def update_mode(self, mode: str):
        old_mode = getattr(self, "mode", "live")
        # Normalize modes from various UI names
        m = str(mode or "").lower()
        if any(token in m for token in ("phantom", "super", "isolated")):
            self.mode = "phantom"  # v1.1: Phantom is now fully isolated by default
        elif any(token in m for token in ("live", "viewer", "dual")):
            self.mode = "live"
        else:
            self.mode = "phantom"
            
        if self.mode == "phantom" and old_mode != "phantom":
            # v1.1.4: Force isolation - close any web surface that might be on the Default desktop
            if self.web_surface:
                _phantom_debug("[ISOLATION] Closing existing web surface to force re-launch in isolated environment.")
                with contextlib.suppress(Exception):
                    self.web_surface.disconnect()
                self.web_surface = None
                self.browser_cdp_port = 0
            
        # Desktop Management: Phantom only uses a real virtual display.
        # Windows Task View desktops are not treated as captureable workspaces.
        if self.mode == "phantom":
            self._refresh_jarvis_display_status(force=False)
            self.h_phantom_desk = None
        else:
            self._stop_phantom_capture_thread()
            self.h_phantom_desk = None
            _reset_thread_to_default_desktop()
            
        _phantom_debug(f"[MODE] Switched to: {self.mode}")

    def _refresh_jarvis_display_status(self, force: bool = False) -> Dict[str, Any]:
        status = _jarvis_workspace_status(force=force)
        self.jarvis_display_status = dict(status)
        self.workspace_kind = str(status.get("workspace_kind") or "virtual_display")
        self.workspace_ready = bool(status.get("workspace_ready"))
        self.last_launch_error = str(status.get("last_launch_error") or "")
        if self.mode == "phantom" and not self.workspace_ready:
            self.last_launch_error_code = str(status.get("setup_state") or "phantom_display_missing")
        if self.mode == "phantom" and not self.workspace_ready:
            self.vision_health_status = self.last_launch_error or "Phantom virtual display is not ready."
            if not self.last_ai_action_desc or self.last_ai_action_desc == "Initializing...":
                self.last_ai_action_desc = self.vision_health_status
        return dict(status)

    def _jarvis_display_ready(self) -> bool:
        return bool(self._refresh_jarvis_display_status(force=False).get("workspace_ready"))

    def _configure_startup_for_jarvis_display(self, startupinfo: subprocess.STARTUPINFO) -> None:
        if self.mode != "phantom" or not startupinfo:
            return
        status = self._refresh_jarvis_display_status(force=False)
        if not status.get("workspace_ready"):
            return
        bounds = dict(status.get("display_bounds") or {})
        with contextlib.suppress(Exception):
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USEPOSITION", 0x00000004)
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESIZE", 0x00000002)
            startupinfo.dwX = int(bounds.get("left", 0))
            startupinfo.dwY = int(bounds.get("top", 0))
            startupinfo.dwXSize = max(640, int(bounds.get("width", 1280) or 1280))
            startupinfo.dwYSize = max(480, int(bounds.get("height", 720) or 720))

    def _place_window_on_jarvis_display(self, hwnd: int) -> bool:
        if self.mode != "phantom":
            return False
        status = self._refresh_jarvis_display_status(force=False)
        if not status.get("workspace_ready"):
            _phantom_debug("[PLACEMENT] FAIL: virtual display not ready")
            return False
        # v2.0: Always use virtual_display mode - move window to virtual display bounds
        bounds = status.get("display_bounds", {})
        _phantom_debug(f"[PLACEMENT] Moving HWND {hwnd} to virtual display {status.get('display_id')} at ({bounds.get('left')}, {bounds.get('top')})")
        moved = jarvis_display_manager.move_window_here(hwnd, maximize=True)
        if moved:
            if int(getattr(self, "desktop_index", -1) or -1) > 0:
                if self._move_window_to_desktop_index_sync(hwnd, int(self.desktop_index)):
                    _phantom_debug(f"[PLACEMENT] Window assigned to Windows desktop {int(self.desktop_index) + 1}")
                else:
                    _phantom_debug("[PLACEMENT] Window stayed on current Task View desktop; Phantom isolation remains active")
            _phantom_debug("[PLACEMENT] SUCCESS: Window moved to virtual display")
            self.browser_offscreen = False
            self._has_stealth_hidden_once = True
            self._stealth_first_hidden_at = self._stealth_first_hidden_at or time.time()
            self.vision_health_status = "Healthy"
            self.last_launch_error = ""
            self.last_launch_error_code = ""
        else:
            _phantom_debug("[PLACEMENT] FAIL: move_window_here returned False")
        return bool(moved)

    async def _run_sync(self, func, *args):
        return await asyncio.to_thread(func, *args)

    def _public_mode(self) -> str:
        if self.mode == "super":
            return "isolated"
        if self.mode == "phantom":
            return "background"
        return "live"

    def _task_state(self) -> str:
        state = str(self.runtime_state or "").strip().lower()
        if state == "preview":
            return "preview"
        if state in {"starting", "launching"}:
            return "launching"
        if state == "pending_confirmation":
            return "awaiting_consent"
        if state == "stopping":
            return "stopping"
        if state in {"done", "stopped", "error", "blocked"}:
            return state
        if self.mode != "live" and self._has_locked_target_window() and self.step_count <= 0 and not self.user_revealed_target:
            return "hidden_ready"
        return "working"

    def _stream_state(self) -> str:
        if self.session_closed and not self.latest_live_b64:
            return "ended"
        if self.latest_live_b64:
            if self.consecutive_black_frames > 0 or str(self.vision_health_status or "").strip().lower() != "healthy":
                return "degraded"
            if self.agent_stopped and not self.session_closed:
                return "frozen"
            return "live"
        if self.agent_stopped:
            return "ended"
        return "connecting"

    def _current_surface_label(self, fallback: str = "") -> str:
        default_label = fallback or (self.launch_target_tokens[0] if self.launch_target_tokens else "")
        return _surface_label(self.target_window_title, url=self.current_url, fallback=default_label)

    def _command_requires_confirmation(self) -> Dict[str, Any]:
        if isinstance(self.plan, dict) and (self.plan.get("requires_consent") or any(bool(task.get("requires_consent")) for task in self.tasks)):
            target = self._current_surface_label()
            reason = str(self.plan.get("consent_reason") or "sensitive_action").strip() or "sensitive_action"
            return {
                "type": "consent_required",
                "reason": reason,
                "consent_reason": reason,
                "description": f"Skemi cần bạn xác nhận trước khi tiếp tục tác vụ nhạy cảm trong {target}.",
                "target": target,
                "tasks": self.tasks,
            }
        # AI-based sensitive action detection (sync version for compatibility)
        is_sensitive = False
        # Note: async AI detection happens in async context
        # Here we use smart heuristic detection
        
        # Smart heuristic for sensitive actions
        normalized = _normalize_text(self.command)
        # Check for high-risk patterns contextually
        risk_indicators = ["xóa", "delete", "format", "uninstall", "gỡ", 
                         "cài", "install", "shutdown", "restart", "khởi động lại"]
        is_sensitive = any(ind in normalized for ind in risk_indicators)
        
        if not is_sensitive:
            return {}
        
        target = self._current_surface_label()
        description = f"Vui lòng xác nhận trước khi tôi thực hiện hành động này trong {target}."
        return {
            "type": "confirm_required",
            "reason": "sensitive_action",
            "description": description,
            "target": target,
        }

    async def _await_confirmation_if_needed(self) -> bool:
        request = self._command_requires_confirmation()
        if not request:
            return True
        if self.pending_confirmation:
            return False
        loop = self._loop or asyncio.get_running_loop()
        self.pending_confirmation = dict(request)
        self.consent_reason = str(request.get("reason") or "").strip()
        self.runtime_state = "pending_confirmation"
        self.last_ai_action_desc = str(request.get("description") or "Waiting for confirmation...")
        self.last_active_at = time.time()
        self._confirmation_future = loop.create_future()
        approved = False
        try:
            approved = bool(await self._confirmation_future)
        finally:
            self._confirmation_future = None
            self.pending_confirmation = {}
            self.consent_reason = ""
        if not approved:
            self.cancelled = True
            self.runtime_state = "stopped"
            self.last_result = self._human_result("Cancelled before executing a sensitive action.", state="stopped")
            self.last_ai_action_desc = self.last_result
            return False
        self.runtime_state = "working"
        self.last_ai_action_desc = "Confirmation received. Continuing the task."
        self.last_active_at = time.time()
        return True

    def resolve_confirmation(self, approved: bool) -> bool:
        future = self._confirmation_future
        if future is None or future.done():
            return False
        future.set_result(bool(approved))
        return True

    def _desktop_search_handle(self):
        # v1.1: Always search the isolated desktop in Phantom mode
        if self.mode == "phantom" and self.h_phantom_desk:
            return self.h_phantom_desk
        return None

    def _prefers_vietnamese(self) -> bool:
        normalized = _normalize_text(self.command)
        return bool(re.search(r"\b(?:mo|bat|xem|nghe|nhac|thu muc|tim|vao|dang nhap|chon|gui|tai)\b", normalized))

    def _has_post_launch_intent(self) -> bool:
        """Check if the command implies any action beyond just opening.
        Returns True for most multi-word commands since they usually want interaction."""
        normalized = _normalize_text(self.command)
        if not normalized:
            return False
        # Commands with 4+ words almost always want interaction
        words = [w for w in normalized.split() if len(w) > 1]
        if len(words) >= 4:
            return True
        # Check for specific intent words that _requires_post_launch_interaction might miss
        extra_patterns = (
            r"\b(?:roi|sau do|xong|tiep|va|then|and|after|next|also|nhap|go|viet|dien|danh"
            r"|bat nhac|phat nhac|phat video|bat video|xem phim|nghe nhac|nghe bai|xem bai"
            r"|nhan|gui tin|chat|noi chuyen|lien lac|goi|call"
            r"|dang nhap|sign|log|login|register"
            r"|mua|dat hang|thanh toan|order|buy|pay|system settings|registry)\b"
        )
        if re.search(extra_patterns, normalized):
            return True
        return False

    def _remember_action(self, text: str) -> None:
        message = str(text or "").strip()
        if not message:
            return
        normalized = message.lower()
        if normalized in {
            "analyzing current screen...",
            "observing screen details...",
            "waiting for target window lock...",
            "thinking...",
            "processing...",
        }:
            return
        if self.recent_actions and self.recent_actions[-1] == message:
            return
        self.recent_actions.append(message)
        self.recent_actions = self.recent_actions[-8:]

    def _summarize_recent_actions(self) -> str:
        if not self.recent_actions:
            return ""
        tail = self.recent_actions[-3:]
        if self._prefers_vietnamese():
            return " | ".join(tail)
        return " | ".join(tail)

    def _move_window_to_desktop_index_sync(self, hwnd: int, target_index: int):
        """Move a window to the locked virtual desktop without switching the user's view."""
        return _move_window_to_desktop_index_sync(hwnd, target_index)

    def _human_result(self, fallback: str = "", *, state: str = "done") -> str:
        title_or_url = self._current_surface_label()
        recent = self._summarize_recent_actions()
        fallback_text = str(fallback or "").strip()
        prefers_vi = self._prefers_vietnamese()

        if state == "open_only":
            if prefers_vi:
                return f"Đã mở {title_or_url} và sẵn sàng thao tác tiếp." if title_or_url else "Đã mở xong cửa sổ theo yêu cầu."
            return f"Opened {title_or_url} and it is ready for the next action."
        if state == "step_limit":
            if prefers_vi:
                base = f"Mình đã thao tác trong {title_or_url} nhưng chưa thể hoàn tất trước khi chạm giới hạn an toàn."
                return f"{base} {recent}".strip() if recent else base
            base = f"I was working inside {title_or_url} but could not finish before hitting the safety limit."
            return f"{base} {recent}".strip() if recent else base
        if state == "idle_limit":
            if prefers_vi:
                base = f"Mình đã tạm dừng vì chưa xác định được bước tiếp theo đủ chắc chắn trong {title_or_url}. Bạn có thể nói bước tiếp theo cụ thể hơn hoặc dùng reveal để mình tiếp tục an toàn."
                return f"{base} {recent}".strip() if recent else base
            base = f"I paused because the next safe step in {title_or_url} was not clear enough. You can give a more specific next step or reveal the window so I can continue safely."
            return f"{base} {recent}".strip() if recent else base
        if state == "idle_limit":
            if prefers_vi:
                base = f"Mình đã mở {title_or_url} nhưng chưa tìm thấy bước tiếp theo đủ rõ để làm tiếp an toàn."
                return f"{base} {recent}".strip() if recent else base
            base = f"I opened {title_or_url} but could not find a clear enough next step to continue safely."
            return f"{base} {recent}".strip() if recent else base
        if state == "error":
            if prefers_vi:
                return fallback_text or f"Có lỗi khi thao tác trong {title_or_url}."
            return fallback_text or f"I hit an error while working in {title_or_url}."
        if state == "stopped":
            if prefers_vi:
                return fallback_text or "Mình đã dừng phiên theo yêu cầu."
            return fallback_text or "I stopped the task as requested."
        if fallback_text:
            generic_terms = {
                "opened the requested app or folder.",
                "task completed.",
                "desktop runtime crashed",
                "task stopped.",
            }
            if fallback_text.lower() not in generic_terms:
                return fallback_text
        if prefers_vi:
            base = f"Đã hoàn thành thao tác trong {title_or_url}."
            return f"{base} {recent}".strip() if recent else base
        base = f"Completed the requested work in {title_or_url}."
        return f"{base} {recent}".strip() if recent else base

    async def _build_web_context_async(self) -> str:
        worker = self.web_surface
        if worker is None or not getattr(worker, "is_connected", False):
            return ""
        self.automation_mode = "web_semantic"
        try:
            snapshot = await worker.snapshot()
        except Exception:
            snapshot = {}
        if not isinstance(snapshot, dict) or not snapshot:
            return ""
        self.current_url = str(snapshot.get("url") or self.current_url or "")
        self.target_window_title = str(snapshot.get("title") or self.target_window_title or "Chromium")
        self.web_viewport_width = max(1, int(snapshot.get("viewport_width") or self.web_viewport_width or 1280))
        self.web_viewport_height = max(1, int(snapshot.get("viewport_height") or self.web_viewport_height or 900))
        elements = list(snapshot.get("interactive_elements") or [])[:18]
        self.web_interactive_elements = [item for item in elements if isinstance(item, dict)]
        lines = [
            f"current_url: {self.current_url}",
            f"page_title: {self.target_window_title}",
            f"viewport: {self.web_viewport_width}x{self.web_viewport_height}",
        ]
        if self.web_interactive_elements:
            lines.append("visible_interactive_elements:")
            for index, item in enumerate(self.web_interactive_elements[:12], start=1):
                text = str(item.get("text") or "").strip()
                class_name = str(item.get("class_name") or "").strip()
                x = int(item.get("x") or 0)
                y = int(item.get("y") or 0)
                width = int(item.get("width") or 0)
                height = int(item.get("height") or 0)
                label = text or class_name or f"element_{index}"
                lines.append(f"{index}. {label} @ ({x},{y}) size {width}x{height}")
        return "\n".join(line for line in lines if line.strip())

    def _uia_context_sync(self, max_nodes: int = 80) -> str:
        if uia is None or not self.target_window_hwnd or not win32gui.IsWindow(self.target_window_hwnd):
            return ""
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        
        # v1.0.3: Use official UIA thread initializer
        with getattr(uia, 'UIAutomationInitializerInThread', contextlib.nullcontext)():
            try:
                root = uia.ControlFromHandle(int(self.target_window_hwnd))
            except Exception:
                return ""
            rows: List[str] = []
            def walk(ctrl, depth: int = 0) -> None:
                if len(rows) >= max_nodes or depth > 5:
                    return
                try:
                    name = str(getattr(ctrl, "Name", "") or "").strip()
                    ctype = str(getattr(ctrl, "ControlTypeName", "") or "").strip()
                    enabled = bool(getattr(ctrl, "IsEnabled", True))
                    focusable = bool(getattr(ctrl, "IsKeyboardFocusable", False))
                    if name or ctype:
                        rows.append(f"{'  ' * depth}- {ctype or 'Control'} name={name!r} enabled={enabled} focusable={focusable}")
                    for child in list(ctrl.GetChildren() or [])[:30]:
                        walk(child, depth + 1)
                except Exception:
                    return
            walk(root)
            if rows:
                self.automation_mode = "native_uia"
                return "Native UIA tree:\n" + "\n".join(rows)
        return ""

    def _uia_find_control_sync(self, query: str = "", want_edit: bool = False):
        if uia is None or not self.target_window_hwnd or not win32gui.IsWindow(self.target_window_hwnd):
            return None
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        with getattr(uia, 'UIAutomationInitializerInThread', contextlib.nullcontext)():
            try:
                root = uia.ControlFromHandle(int(self.target_window_hwnd))
            except Exception:
                return None
            query_key = _normalize_text(query)
            stack = [root]
            while stack:
                ctrl = stack.pop(0)
                try:
                    name = str(getattr(ctrl, "Name", "") or "")
                    ctype = str(getattr(ctrl, "ControlTypeName", "") or "")
                    ctype_key = ctype.lower()
                    if want_edit and ("edit" in ctype_key or "document" in ctype_key):
                        return ctrl
                    if query_key and query_key in _normalize_text(f"{name} {ctype}"):
                        return ctrl
                    stack.extend(list(ctrl.GetChildren() or [])[:40])
                except Exception:
                    continue
        return None

    def _execute_native_uia_action_sync(self, action: str, params: Dict[str, Any]) -> bool:
        if self.mode == "phantom":
            if not self._jarvis_display_ready():
                return False
            workspace_kind = str(self.jarvis_display_status.get("workspace_kind") or self.workspace_kind or "")
            if (
                workspace_kind == "virtual_display"
                and self.target_window_hwnd
                and not jarvis_display_manager.contains_hwnd(int(self.target_window_hwnd))
            ):
                return False
        if uia is None:
            return False
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        
        with getattr(uia, 'UIAutomationInitializerInThread', contextlib.nullcontext)():
            action = str(action or "").strip().lower()
            try:
                if action == "type":
                    text = str(params.get("text") or "")
                    if not text:
                        return False
                    ctrl = self._uia_find_control_sync(str(params.get("label") or ""), want_edit=True)
                    if ctrl is None:
                        return False
                    # Avoid SetFocus in Jarvis mode to prevent stealing the user's desktop.
                    if self.mode != "phantom":
                        with contextlib.suppress(Exception):
                            ctrl.SetFocus()
                    with contextlib.suppress(Exception):
                        ctrl.GetValuePattern().SetValue(text)
                        self.automation_mode = "native_uia"
                        return True
                    with contextlib.suppress(Exception):
                        ctrl.SendKeys(text, waitTime=0.01)
                        self.automation_mode = "native_uia"
                        return True
                if action == "key":
                    key = str(params.get("key") or "enter").strip()
                    if not key:
                        return False
                    uia.SendKeys("{" + key.upper() + "}" if len(key) > 1 else key, waitTime=0.01)
                    self.automation_mode = "native_uia"
                    return True
                if action == "click":
                    label = str(params.get("label") or params.get("text") or "").strip()
                    if not label:
                        return False
                    ctrl = self._uia_find_control_sync(label, want_edit=False)
                    if ctrl is None:
                        return False
                    with contextlib.suppress(Exception):
                        ctrl.GetInvokePattern().Invoke()
                        self.automation_mode = "native_uia"
                        return True
                    with contextlib.suppress(Exception):
                        ctrl.Click(simulateMove=False)
                        self.automation_mode = "native_uia"
                        return True
            except Exception:
                pass
        return False

    def _phantom_desktop_label(self) -> str:
        idx = int(getattr(self, "desktop_index", -1) or -1)
        if idx > 0:
            return f"Desktop {idx + 1}"
        return "Phantom Desktop"

    def _phantom_desktop_status_text(self) -> str:
        return f"AI is viewing {self._phantom_desktop_label()}."

    def _phantom_screen_point(self, x_norm: Any, y_norm: Any) -> Optional[Tuple[int, int]]:
        if self.mode != "phantom" or not self._jarvis_display_ready():
            return None
        bounds = jarvis_display_manager.active_bounds()
        if not bounds:
            return None
        def norm(value: Any) -> float:
            try:
                return max(0.0, min(1000.0, float(str(value))))
            except Exception:
                return 500.0
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        width = max(1, int(bounds.get("width", 1)))
        height = max(1, int(bounds.get("height", 1)))
        sx = left + int(round((norm(x_norm) / 1000.0) * max(0, width - 1)))
        sy = top + int(round((norm(y_norm) / 1000.0) * max(0, height - 1)))
        return sx, sy

    def _phantom_target_at_point(self, x_norm: Any, y_norm: Any) -> Tuple[int, int, int]:
        point = self._phantom_screen_point(x_norm, y_norm)
        if not point:
            return 0, 0, 0
        sx, sy = point
        hwnd = 0
        with contextlib.suppress(Exception):
            hwnd = int(win32gui.WindowFromPoint((sx, sy)) or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return 0, sx, sy
        target_h = hwnd
        with contextlib.suppress(Exception):
            child = win32gui.ChildWindowFromPointEx(
                hwnd,
                win32gui.ScreenToClient(hwnd, (sx, sy)),
                getattr(win32con, "CWP_SKIPINVISIBLE", 0x0001),
            )
            if child and win32gui.IsWindow(child):
                target_h = int(child)
        return int(target_h), sx, sy

    def _post_phantom_click_sync(self, params: Dict[str, Any], button: str = "left") -> bool:
        """Inject a background click at coordinates provided in params."""
        hwnd, sx, sy = self._phantom_target_at_point(params.get("x", 500), params.get("y", 500))
        if not hwnd or not win32gui.IsWindow(hwnd):
            # Fallback to desktop window if no child window resolved
            hwnd = win32gui.GetDesktopWindow()
            
        # v8.6: CRITICAL SAFETY CHECK - ensure coordinates are within the ACTIVE PHANTOM BOUNDS
        bounds = jarvis_display_manager.active_bounds()
        if bounds:
            left = int(bounds.get("left", 0))
            top = int(bounds.get("top", 0))
            right = left + int(bounds.get("width", 0))
            bottom = top + int(bounds.get("height", 0))
            if not (left <= sx <= right and top <= sy <= bottom):
                _phantom_debug(f"[SAFETY] Blocked click at ({sx}, {sy}) - Outside phantom bounds ({left}, {top}, {right}, {bottom})")
                return False
        try:
            lx, ly = win32gui.ScreenToClient(hwnd, (sx, sy))
            lparam = win32api.MAKELONG(int(lx), int(ly))
            
            down_msg = win32con.WM_LBUTTONDOWN if button == "left" else win32con.WM_RBUTTONDOWN
            up_msg = win32con.WM_LBUTTONUP if button == "left" else win32con.WM_RBUTTONUP
            mk_flag = win32con.MK_LBUTTON if button == "left" else win32con.MK_RBUTTON
            
            # v8.6: Enhanced simulation with cursor notification
            win32gui.PostMessage(hwnd, win32con.WM_SETCURSOR, hwnd, win32api.MAKELONG(win32con.HTCLIENT, down_msg))
            win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            win32gui.PostMessage(hwnd, down_msg, mk_flag, lparam)
            time.sleep(0.045) # Stability delay
            win32gui.PostMessage(hwnd, up_msg, 0, lparam)
            self._phantom_input_hwnd = hwnd
            return True
        except Exception as e:
            _phantom_debug(f"[PHANTOM CLICK ERROR] {e}")
            return False

    def _post_phantom_type_sync(self, text: str) -> bool:
        hwnd = int(getattr(self, "_phantom_input_hwnd", 0) or self.target_window_hwnd or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            for char in str(text or ""):
                if char == "\n":
                    self._post_phantom_key_sync("enter")
                else:
                    win32gui.PostMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
                    time.sleep(0.004)
            return True
        except Exception:
            return False

    def _post_phantom_key_sync(self, key: str) -> bool:
        hwnd = int(getattr(self, "_phantom_input_hwnd", 0) or self.target_window_hwnd or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        key_name = str(key or "enter").strip().lower()
        vk_map = {
            "enter": win32con.VK_RETURN,
            "return": win32con.VK_RETURN,
            "tab": win32con.VK_TAB,
            "backspace": win32con.VK_BACK,
            "delete": win32con.VK_DELETE,
            "esc": win32con.VK_ESCAPE,
            "escape": win32con.VK_ESCAPE,
            "space": win32con.VK_SPACE,
            "up": win32con.VK_UP,
            "down": win32con.VK_DOWN,
            "left": win32con.VK_LEFT,
            "right": win32con.VK_RIGHT,
            "home": win32con.VK_HOME,
            "end": win32con.VK_END,
            "pageup": win32con.VK_PRIOR,
            "pagedown": win32con.VK_NEXT,
        }
        vk = vk_map.get(key_name)
        if not vk and len(key_name) == 1:
            vk = ctypes.windll.user32.VkKeyScanW(ord(key_name)) & 0xFF
        if not vk:
            return False
        try:
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, int(vk), 0)
            time.sleep(0.012)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, int(vk), 0)
            return True
        except Exception:
            return False

    def _post_phantom_scroll_sync(self, amount: Any, params: Optional[Dict[str, Any]] = None) -> bool:
        params = params or {}
        hwnd, sx, sy = self._phantom_target_at_point(params.get("x", 500), params.get("y", 500))
        if not hwnd:
            hwnd = int(getattr(self, "_phantom_input_hwnd", 0) or self.target_window_hwnd or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            wparam = (int(amount) & 0xFFFF) << 16
            win32gui.PostMessage(hwnd, win32con.WM_MOUSEWHEEL, wparam, 0)
            return True
        except Exception:
            return False

    def _execute_phantom_desktop_action_sync(self, action: str, params: Dict[str, Any]) -> bool:
        if self.mode != "phantom" or not self._jarvis_display_ready():
            return False
        action = str(action or "").strip().lower()
        params = params or {}
        if action == "click":
            return self._post_phantom_click_sync(params)
        if action == "double_click":
            first = self._post_phantom_click_sync(params)
            time.sleep(0.05)
            second = self._post_phantom_click_sync(params)
            return bool(first and second)
        if action == "right_click":
            return self._post_phantom_click_sync(params, button="right")
        if action == "type":
            hwnd, _, _ = self._phantom_target_at_point(params.get("x", 500), params.get("y", 500))
            if hwnd and win32gui.IsWindow(hwnd):
                self._phantom_input_hwnd = hwnd
            return self._post_phantom_type_sync(str(params.get("text") or ""))
        if action == "key":
            hwnd, _, _ = self._phantom_target_at_point(params.get("x", 500), params.get("y", 500))
            if hwnd and win32gui.IsWindow(hwnd):
                self._phantom_input_hwnd = hwnd
            return self._post_phantom_key_sync(str(params.get("key") or "enter"))
        if action == "scroll":
            return self._post_phantom_scroll_sync(params.get("amount"), params)
        return False
        
    def _get_user_chrome_info(self) -> Dict[str, str]:
        """Auto-detect Chrome/Edge executable and default profile paths on Windows."""
        res = {
            "exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "user_data": os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\User Data"),
            "profile": "Default"
        }
        if not os.path.exists(res["exe"]):
            res["exe"] = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            res["user_data"] = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\User Data")
        if not os.path.exists(res["exe"]):
            res["exe"] = "chrome.exe"
        local_state_path = os.path.join(res["user_data"], "Local State")
        try:
            if os.path.exists(local_state_path):
                with open(local_state_path, "r", encoding="utf-8") as handle:
                    local_state = json.load(handle)
                profile_state = local_state.get("profile") or {}
                last_used = str(
                    profile_state.get("last_used")
                    or (profile_state.get("last_active_profiles") or [""])[0]
                    or ""
                ).strip()
                if last_used:
                    res["profile"] = last_used
        except Exception:
            pass
        return res

    def _alloc_browser_debug_port(self) -> int:
        seed = 0
        try:
            seed = int(str(self.session_id or "0")[:4], 16)
        except Exception:
            seed = int(time.time()) % 400
        return 9222 + (seed % 400)

    def _ensure_web_surface(self):
        if self.web_surface is None and desktop_web_worker is not None:
            with contextlib.suppress(Exception):
                self.web_surface = desktop_web_worker.SkemiWebWorker()
        return self.web_surface

    async def _connect_web_surface_async(self, port: int) -> bool:
        worker = self._ensure_web_surface()
        if worker is None:
            return False
        connected = await worker.connect(port=int(port or 0))
        if connected:
            snapshot = await worker.snapshot()
            self.browser_cdp_port = int(port or 0)
            self.target_window_class = "chromium_cdp"
            self.target_window_title = str(snapshot.get("title") or self.target_window_title or "Chromium")
            self.current_url = str(snapshot.get("url") or self.current_url or "")
            self.web_viewport_width = max(1, int(snapshot.get("viewport_width") or self.web_viewport_width or 1280))
            self.web_viewport_height = max(1, int(snapshot.get("viewport_height") or self.web_viewport_height or 900))
            self.web_interactive_elements = [item for item in list(snapshot.get("interactive_elements") or []) if isinstance(item, dict)][:18]
            self.last_active_at = time.time()
        return bool(connected)

    def _connect_web_surface_sync(self, port: int, timeout: float = 12.0) -> bool:
        if not self._loop:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self._connect_web_surface_async(port), self._loop)
            return bool(future.result(timeout=max(2.0, float(timeout or 0.0))))
        except Exception:
            return False

    async def _capture_web_surface_async(self) -> str:
        worker = self.web_surface
        if worker is None or not getattr(worker, "is_connected", False):
            return ""
        self.automation_mode = "web_semantic"
        captured = await worker.capture_jpeg_base64()
        if not captured:
            return ""
        now = time.time()
        if (now - self._last_web_snapshot_at) >= 0.25:
            snapshot = await worker.snapshot()
            self._last_web_snapshot_at = now
            self.target_window_title = str(snapshot.get("title") or self.target_window_title or "Chromium")
            self.target_window_class = "chromium_cdp"
            self.current_url = str(snapshot.get("url") or self.current_url or "")
            self.web_viewport_width = max(1, int(snapshot.get("viewport_width") or self.web_viewport_width or 1280))
            self.web_viewport_height = max(1, int(snapshot.get("viewport_height") or self.web_viewport_height or 900))
            self.web_interactive_elements = [item for item in list(snapshot.get("interactive_elements") or []) if isinstance(item, dict)][:18]
        self.capture_w = int(self.web_viewport_width or 1280)
        self.capture_h = int(self.web_viewport_height or 900)
        self.latest_live_b64 = captured
        self.latest_live_at = now
        self.frame_version += 1
        return captured

    def _stashed_window_rect(self) -> tuple[int, int, int, int]:
        left, top, width, _height = _virtual_screen_bounds()
        stash_left = int(left + width + 48)
        stash_top = int(top + 48)
        return stash_left, stash_top, HIDDEN_WINDOW_WIDTH, HIDDEN_WINDOW_HEIGHT

    async def _ensure_web_surface_ready_async(self, *, force: bool = False) -> bool:
        if not self.browser_cdp_port:
            return False
        worker = self._ensure_web_surface()
        if worker is None:
            return False
        if getattr(worker, "is_connected", False):
            with contextlib.suppress(Exception):
                return bool(await worker.ensure_page())
            return True
        now = time.time()
        if not force and (now - float(self._last_web_connect_attempt_at or 0.0)) < 0.6:
            return False
        self._last_web_connect_attempt_at = now
        connected = await self._connect_web_surface_async(self.browser_cdp_port)
        if connected:
            self.last_active_at = time.time()
        return bool(connected)

    def _prime_youtube_playback_sync(self, url: str) -> bool:
        worker = self.web_surface
        if not self._loop or worker is None or not getattr(worker, "is_connected", False):
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(worker.ensure_youtube_playing(url), self._loop)
            result = future.result(timeout=18.0)
            if isinstance(result, dict) and result.get("success"):
                self.last_ai_action_desc = "YouTube playback started."
                return True
        except Exception:
            return False
        return False

    def _capture_hidden_desktop_sync(self):
        """Capture the isolated phantom desktop. Uses cached frame from dedicated thread if available."""
        if not self.h_phantom_desk or self.browser_offscreen:
            return None
        # v1.0.0: Use dedicated capture thread's cached frame to avoid desktop switching
        if self._phantom_capture_img is not None:
            return self._phantom_capture_img.copy()
        # Fallback: direct capture (only if dedicated thread not started yet)
        return self._capture_phantom_desktop_direct()

    def _capture_phantom_desktop_direct(self):
        """Direct capture of phantom desktop — called from dedicated thread."""
        if not self.h_phantom_desk:
            return None
        hdc_raw = 0
        target_dc = mem_dc = bmp = None
        try:
            # v1.1.16: Use 'DISPLAY' device context to capture the desktop the thread is currently bound to
            hdc_raw = win32gui.CreateDC("DISPLAY", None, None)
            if not hdc_raw:
                return None
            target_dc = win32ui.CreateDCFromHandle(hdc_raw)
            mem_dc = target_dc.CreateCompatibleDC()
            width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(target_dc, width, height)
            mem_dc.SelectObject(bmp)
            # Use SRCCOPY (0xCC0020) without CAPTUREBLT to prevent physical mouse jitter
            mem_dc.BitBlt((0, 0), (width, height), target_dc, (0, 0), 0xCC0020)
            info = bmp.GetInfo()
            bits = bmp.GetBitmapBits(True)
            return Image.frombuffer(
                "RGB",
                (info["bmWidth"], info["bmHeight"]),
                bits,
                "raw",
                "BGRX",
                0,
                1,
            ).convert("RGB")
        except Exception:
            return None
        finally:
            with contextlib.suppress(Exception):
                if mem_dc:
                    mem_dc.DeleteDC()
            with contextlib.suppress(Exception):
                if target_dc:
                    target_dc.DeleteDC()
            with contextlib.suppress(Exception):
                if bmp:
                    win32gui.DeleteObject(bmp.GetHandle())
            with contextlib.suppress(Exception):
                if hdc_raw:
                    win32gui.ReleaseDC(0, hdc_raw)

    def _start_phantom_capture_thread(self):
        """Start a dedicated thread that stays on the phantom desktop for capture.
        This avoids the flickering caused by SetThreadDesktop() on the main thread."""
        if self._phantom_capture_thread is not None:
            return
        if not self.h_phantom_desk:
            return
        self._phantom_capture_stop.clear()

        def _phantom_worker():
            # Lock this thread to the phantom desktop ONCE
            try:
                # v1.1.17: Revert to handle-method for SetThreadDesktop
                self.h_phantom_desk.SetThreadDesktop()
            except Exception as e:
                _phantom_debug(f"[PHANTOM CAPTURE] Failed to bind to phantom desktop: {e}")
                return
            while not self._phantom_capture_stop.is_set():
                try:
                    img = self._capture_phantom_desktop_direct()
                    if img:
                        self._phantom_capture_img = img
                except Exception:
                    pass
                time.sleep(0.07)  # ~14 FPS

        self._phantom_capture_thread = threading.Thread(
            target=_phantom_worker,
            name="SkemiPhantomCapture",
            daemon=True,
        )
        self._phantom_capture_thread.start()

    def _stop_phantom_capture_thread(self):
        self._phantom_capture_stop.set()
        if self._phantom_capture_thread:
            self._phantom_capture_thread.join(timeout=2)
            self._phantom_capture_thread = None

    def _terminate_offscreen_browsers_sync(self) -> None:
        """Forcefully kill all processes associated with this phantom session."""
        _phantom_debug(f"[CLEANUP] Terminating all isolated processes for session {self.session_id}")
        pids = [int(pid) for pid in list(self.offscreen_browser_pids or set()) if int(pid or 0) > 0]
        self.offscreen_browser_pids.clear()
        
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=3)
            except Exception:
                pass
                
        # Also kill any stray browser processes using our session-specific profile
        if self.mode == "phantom":
            try:
                # v1.1.5: Hunt down any process mentioning our session ID to stop audio
                subprocess.run(["wmic", "process", "where", f"commandline like '%{self.session_id[:8]}%'", "call", "terminate"], capture_output=True)
            except Exception:
                pass

        if self.web_surface:
            with contextlib.suppress(Exception):
                self.web_surface.disconnect()
            self.web_surface = None

    def _normalized_to_web_point(self, x_norm: int, y_norm: int) -> tuple[int, int]:
        width = max(1, int(self.web_viewport_width or 1280))
        height = max(1, int(self.web_viewport_height or 900))
        safe_x = max(0, min(1000, int(x_norm or 0)))
        safe_y = max(0, min(1000, int(y_norm or 0)))
        return (
            int(round((safe_x / 1000.0) * width)),
            int(round((safe_y / 1000.0) * height)),
        )

    async def _execute_web_action_async(self, action: str, params: Dict[str, Any]) -> bool:
        if not await self._ensure_web_surface_ready_async(force=True):
            return False
        worker = self.web_surface
        if worker is None or not getattr(worker, "is_connected", False):
            return False
        payload = dict(params or {})
        if action in {"click", "type"}:
            x = payload.get("x")
            y = payload.get("y")
            if x is not None and y is not None:
                try:
                    px, py = self._normalized_to_web_point(int(float(str(x))), int(float(str(y))))
                    payload["x"] = px
                    payload["y"] = py
                except Exception:
                    pass
        if action == "scroll" and "direction" not in payload:
            amount = payload.get("amount")
            try:
                payload["direction"] = "up" if float(str(amount)) > 0 else "down"
            except Exception:
                payload["direction"] = "down"
        result = await worker.execute_action(action, payload)
        if result.get("success"):
            self.last_active_at = time.time()
            return True
        return False

    def _bind_target_window(self, hwnd: int, target_pid: int = 0) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        self.target_window_hwnd = int(hwnd)
        raw_title = str(win32gui.GetWindowText(hwnd) or "").strip()
        raw_class = _window_class_name(hwnd)
        self.target_window_class = raw_class
        if raw_title and not _is_generic_window_identity(raw_title, raw_class):
            self.target_window_title = raw_title
        elif _is_generic_window_identity(self.target_window_title, self.target_window_class) or not str(self.target_window_title or "").strip():
            self.target_window_title = self._current_surface_label(fallback=raw_title or raw_class or "")
        resolved_pid = int(target_pid or _window_process_id(hwnd) or 0)
        if resolved_pid:
            self.target_process_id = resolved_pid
            if self.mode == "phantom":
                jarvis_display_manager.add_watched_pid(resolved_pid)
        self.last_active_at = time.time()
        return True

    def _set_launch_baseline(self, handles: Optional[set[int]] = None) -> None:
        self._launch_baseline_handles = {
            int(hwnd) for hwnd in (handles or set()) if int(hwnd or 0) > 0
        }
        self._owned_target_handles.clear()

    def _is_claimable_target_window(self, hwnd: int) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        if self.mode == "live" or not self._launch_baseline_handles:
            return True
        handle = int(hwnd)
        return handle not in self._launch_baseline_handles or handle in self._owned_target_handles

    def _claim_target_window(self, hwnd: int, target_pid: int = 0) -> bool:
        if not self._is_claimable_target_window(hwnd):
            return False
        if not self._bind_target_window(hwnd, target_pid):
            return False
        self._owned_target_handles.add(int(hwnd))
        return True

    def _has_locked_target_window(self) -> bool:
        hwnd = int(self.target_window_hwnd or 0)
        return bool(hwnd and win32gui.IsWindow(hwnd))

    def _target_is_user_foreground(self, hwnd: int) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        fg_hwnd = _foreground_window_handle()
        if not fg_hwnd or not win32gui.IsWindow(fg_hwnd):
            return False
        if int(fg_hwnd) == int(hwnd):
            return True
        fg_pid = _window_process_id(fg_hwnd)
        target_pid = int(self.target_process_id or _window_process_id(hwnd) or 0)
        return bool(target_pid and fg_pid and fg_pid == target_pid)

    def _window_is_presented_to_user(self, hwnd: int) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            if win32gui.IsIconic(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return False
            rect = win32gui.GetWindowRect(hwnd)
            if not rect or rect[2] <= rect[0] or rect[3] <= rect[1]:
                return False
            left, top, width, height = _virtual_screen_bounds()
            right = left + width
            bottom = top + height
            return rect[2] > left and rect[0] < right and rect[3] > top and rect[1] < bottom
        except Exception:
            return False

    def _inside_initial_stealth_grace(self) -> bool:
        if not self._has_stealth_hidden_once or not self._stealth_first_hidden_at:
            return True
        return (time.time() - float(self._stealth_first_hidden_at or 0.0)) < 1.0

    def _restore_target_window_for_user(self, hwnd: int, *, activate: bool = False) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        if self.mode == "phantom":
            return False
        try:
            self.browser_offscreen = False
            self.user_revealed_target = True
            left, top, width, height = _virtual_screen_bounds()
            rect = win32gui.GetWindowRect(hwnd)
            current_w = max(320, int(rect[2] - rect[0]) or HIDDEN_WINDOW_WIDTH)
            current_h = max(240, int(rect[3] - rect[1]) or HIDDEN_WINDOW_HEIGHT)
            target_w = min(current_w, max(520, width - 120))
            target_h = min(current_h, max(360, height - 120))
            target_left = int(left + 60)
            target_top = int(top + 60)
            with contextlib.suppress(Exception):
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Restore full opacity and remove stealth flags
            with contextlib.suppress(Exception):
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                ex_style = ex_style & ~win32con.WS_EX_TRANSPARENT & ~win32con.WS_EX_TOOLWINDOW
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
                if ex_style & win32con.WS_EX_LAYERED:
                    win32gui.SetLayeredWindowAttributes(hwnd, 0, 255, win32con.LWA_ALPHA)
            flags = win32con.SWP_SHOWWINDOW
            if not activate:
                flags |= win32con.SWP_NOACTIVATE
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, target_left, target_top, target_w, target_h, flags)
            if activate:
                if not (PHYSICAL_INPUT_LOCKED or is_isolated):
                    with contextlib.suppress(Exception):
                        _safe_set_foreground_window(hwnd)
            return True
        except Exception:
            return False

    def _stash_window_offscreen_sync(self, hwnd: int) -> None:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return
        try:
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if not (ex_style & win32con.WS_EX_LAYERED):
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style | win32con.WS_EX_LAYERED)
            win32gui.SetLayeredWindowAttributes(hwnd, 0, 1, win32con.LWA_ALPHA)
            win32gui.SetWindowPos(hwnd, win32con.HWND_BOTTOM, -32000, -32000, 0, 0,
                                 win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_HIDEWINDOW)
        except Exception: 
            pass
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_BOTTOM, -32000, -32000, 0, 0,
                                 win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            self.browser_offscreen = True
        except Exception:
            pass
        if not self._has_stealth_hidden_once:
            self._stealth_first_hidden_at = time.time()
        self._has_stealth_hidden_once = True

    def _close_failed_launch_window_sync(
        self,
        hwnd: int,
        pid: int = 0,
        prelaunch_handles: Optional[set[int]] = None,
        *,
        close_new_handle: bool = True,
        kill_pid: bool = False,
    ) -> None:
        if hwnd and win32gui.IsWindow(hwnd):
            handle = int(hwnd)
            prelaunch = {int(item) for item in (prelaunch_handles or set())}
            window_pid = _window_process_id(hwnd)
            same_process = bool(pid and window_pid and int(pid) == int(window_pid))
            new_handle = handle not in prelaunch
            if same_process or (close_new_handle and new_handle):
                with contextlib.suppress(Exception):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        if kill_pid and pid:
            with contextlib.suppress(Exception):
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))], capture_output=True, timeout=3)

    def _stealth_target_window(self, hwnd: int) -> bool:
        if self.mode != "phantom" or not hwnd or not win32gui.IsWindow(hwnd):
            return False

        if self._place_window_on_jarvis_display(hwnd):
            return True
        if not self._jarvis_display_ready():
            self.last_launch_error_code = "phantom_display_missing"
            self.last_ai_action_desc = self.last_launch_error or "Phantom virtual display is not ready."
            return False
        self.last_launch_error = "Window could not be placed inside the Phantom virtual display."
        self.last_launch_error_code = "phantom_window_placement_failed"
        self.last_ai_action_desc = self.last_launch_error
        return False

    def _track_launched_window(self, pid: int, prefer_tokens: Optional[List[str]] = None) -> bool:
        if not pid:
            return False
        self.target_process_id = int(pid)
        hwnd = _wait_for_window_for_pid(
            pid,
            prefer_tokens=prefer_tokens,
            include_hidden=self.mode == "phantom",
            desktop_handle=self._desktop_search_handle(),
            reject_handles=self._launch_baseline_handles if self.mode != "live" else None,
        )
        if not hwnd:
            return False
        if not self._claim_target_window(hwnd, pid):
            return False
        if self.mode != "live":
            moved = self._stealth_target_window(hwnd)
            if self.mode == "phantom" and not moved:
                return False
        self._start_stealth_sentry(target_pid=pid, target_hwnd=hwnd)
        return True

    def _launch_explorer_target_sync(
        self,
        target: str,
        *,
        startupinfo: Optional[subprocess.STARTUPINFO] = None,
        prefer_tokens: Optional[List[str]] = None,
    ) -> bool:
        safe_target = str(target or "").strip().strip("\"'")
        if not safe_target:
            return False
        explorer_arg = safe_target if os.path.isdir(safe_target) else f"/select,{safe_target}"
        prelaunch_handles = self._snapshot_window_handles(include_hidden=True)
        self._set_launch_baseline(prelaunch_handles)
        try:
            popen_kwargs: Dict[str, Any] = {
                "startupinfo": startupinfo,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            launch_proc = subprocess.Popen(["explorer.exe", explorer_arg], **popen_kwargs)
            pid = int(getattr(launch_proc, "pid", 0) or 0)
            hwnd = self._find_new_window_from_snapshot(
                prelaunch_handles,
                prefer_tokens=prefer_tokens,
                pid_hint=pid,
                timeout=7.0,
                include_hidden=True,
            )
            if hwnd:
                self._claim_target_window(hwnd, pid)
                if self.mode == "phantom":
                    # Force the window to stay on the target desktop ONLY
                    # v1.1.70: Use the 'Invisible Anchor' strategy
                    if not self._stealth_target_window(hwnd):
                        self.last_ai_action_desc = self.last_launch_error or "Could not place the launched window on the Jarvis virtual display."
                        self._close_failed_launch_window_sync(hwnd, pid, prelaunch_handles, close_new_handle=True)
                        return False
            else:
                if not self._track_launched_window(pid, prefer_tokens=prefer_tokens):
                    return False
                self._start_stealth_sentry(target_pid=pid, existing_handles=prelaunch_handles, prefer_tokens=prefer_tokens)
            return True
        except Exception as exc:
            _phantom_debug(f"[LAUNCH ERROR] Failed to open Explorer target: {exc}")
            return False

    def _launch_browser_target_sync(
        self,
        target_url: str,
        *,
        startupinfo: Optional[subprocess.STARTUPINFO] = None,
        prefer_tokens: Optional[List[str]] = None,
    ) -> bool:
        url = str(target_url or "").strip()
        if not url:
            return False
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
            url = "https://" + url
        info = self._get_user_chrome_info()
        browser_exe = str(info.get("exe") or "chrome.exe")
        port = self._alloc_browser_debug_port()
        profile_root = os.path.join(os.environ.get("LOCALAPPDATA", os.getcwd()), "Skemi", "phantom_browser_profiles")
        profile_dir = os.path.join(profile_root, re.sub(r"[^A-Za-z0-9_.-]+", "_", self.session_id or str(port)))
        os.makedirs(profile_dir, exist_ok=True)
        args = [
            browser_exe,
            "--new-window",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=Translate,HardwareMediaKeyHandling",
        ]
        if self.mode == "phantom":
            status = self._refresh_jarvis_display_status(force=False)
            if status.get("workspace_ready"):
                bounds = dict(status.get("display_bounds") or {})
                args.extend([
                    f"--window-position={int(bounds.get('left', 0))},{int(bounds.get('top', 0))}",
                    f"--window-size={max(640, int(bounds.get('width', 1280) or 1280))},{max(480, int(bounds.get('height', 720) or 720))}",
                ])
        args.append(url)
        prelaunch_handles = self._snapshot_window_handles(include_hidden=True)
        self._set_launch_baseline(prelaunch_handles)
        try:
            popen_kwargs: Dict[str, Any] = {
                "startupinfo": startupinfo,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(args, **popen_kwargs)

            pid = int(getattr(proc, "pid", 0) or 0)
            if pid:
                self.offscreen_browser_pids.add(pid)
            host_token = ""
            with contextlib.suppress(Exception):
                host_token = urlparse(url).netloc
            tokens = [item for item in [host_token, "chrome", "edge", *(prefer_tokens or [])] if item]
            hwnd = self._find_new_window_from_snapshot(
                prelaunch_handles,
                prefer_tokens=tokens,
                pid_hint=pid,
                timeout=12.0,
                include_hidden=True,
            )
            if not hwnd:
                return False
            if not self._claim_target_window(hwnd, pid):
                return False
            if self.mode == "phantom":
                moved = self._stealth_target_window(hwnd)
                if not moved:
                    self.last_launch_error_code = self.last_launch_error_code or "phantom_window_placement_failed"
                    self.last_ai_action_desc = self.last_launch_error or "Could not place the browser window on Phantom Desktop."
                    self._close_failed_launch_window_sync(hwnd, pid, prelaunch_handles, close_new_handle=True, kill_pid=True)
                    return False
            self.browser_cdp_port = int(port)
            self.browser_profile_dir = profile_dir
            self._connect_web_surface_sync(port, timeout=8.0)
            self.last_ai_action_desc = f"Opened browser on Phantom Desktop: {url}"
            return True
        except Exception as exc:
            _phantom_debug(f"[LAUNCH ERROR] Failed to open isolated browser: {exc}")
            return False

    def _snapshot_window_handles(self, include_hidden: bool = False) -> set[int]:
        handles: set[int] = set()

        def enum_cb(hwnd, _):
            try:
                if not win32gui.IsWindow(hwnd):
                    return True
                cls = _window_class_name(hwnd)
                if include_hidden or win32gui.IsWindowVisible(hwnd) or "widget" in cls.lower() or "chrome" in cls.lower():
                    handles.add(int(hwnd))
            except Exception:
                pass
            return True

        try:
            desktop_handle = self._desktop_search_handle()
            if desktop_handle:
                win32gui.EnumDesktopWindows(desktop_handle, enum_cb, None)
            else:
                win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass
        return handles

    def _find_new_window_from_snapshot(
        self,
        existing_handles: set[int],
        *,
        prefer_tokens: Optional[List[str]] = None,
        pid_hint: int = 0,
        timeout: float = 6.0,
        include_hidden: bool = False,
    ) -> int:
        tokens = [token for token in (_normalize_text(item) for item in (prefer_tokens or []) if token)]
        while time.time() < deadline:
            candidates: list[tuple[int, int, int]] = []

            def enum_cb(hwnd, _):
                try:
                    if not win32gui.IsWindow(hwnd):
                        return True
                    if not include_hidden and not win32gui.IsWindowVisible(hwnd):
                        return True
                    if self.mode != "live" and int(hwnd) in existing_handles and int(hwnd) not in self._owned_target_handles:
                        return True
                    cls = _normalize_text(_window_class_name(hwnd))
                    title = _normalize_text(win32gui.GetWindowText(hwnd))
                    if _is_generic_window_identity(title, cls):
                        return True
                    pid = _window_process_id(hwnd)
                    rect = win32gui.GetWindowRect(hwnd)
                    width = max(0, rect[2] - rect[0])
                    height = max(0, rect[3] - rect[1])
                    area = width * height
                    if area <= 0:
                        return True
                    score = area
                    if int(hwnd) not in existing_handles:
                        score += 120000
                    if pid_hint and pid == pid_hint:
                        score += 24000
                    if "chrome" in cls or "edge" in cls or "widget" in cls:
                        score += 12000
                    if title:
                        score += 2000
                    if any(token in title for token in tokens):
                        score += 32000
                    if score > area:
                        candidates.append((score, int(hwnd), pid))
                except Exception:
                    pass
                return True

            try:
                desktop_handle = self._desktop_search_handle()
                if desktop_handle:
                    win32gui.EnumDesktopWindows(desktop_handle, enum_cb, None)
                else:
                    win32gui.EnumWindows(enum_cb, None)
            except Exception:
                candidates = []
            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                best_score, best_hwnd, best_pid = candidates[0]
                if best_score > 25000:
                    if self._claim_target_window(best_hwnd, best_pid):
                        return int(best_hwnd)
            time.sleep(0.1)
        return 0

    def _extract_browser_query(self, query: str, site_key: str) -> str:
        residual = _normalize_text(query)
        residual = re.sub(rf"\b{re.escape(site_key)}\b", " ", residual, count=1)
        residual = re.sub(
            r"\b(?:vao|mo|truy|cap|trang|web|app|ung|dung|hay|giup|di|toi|den|tren|va|roi|nha|go)\b",
            " ",
            residual,
        )
        residual = re.sub(r"\s+", " ", residual).strip(" ,;-")
        for pattern in (
            r"\b(?:ten la|named|called)\s+(.+)$",
            r"\b(?:search|tim kiem|tim|play|phat|bat|mo|open|go)\s+(.+)$",
        ):
            match = re.search(pattern, residual)
            if match:
                residual = match.group(1).strip()
                break
        residual = re.sub(r"^(?:video\s+)?(?:nghe\s+nhac|xem\s+video|xem|nghe)\s+", "", residual)
        residual = re.sub(r"^(?:bai nhac|bai hat|video|bai|nhac)\s+", "", residual)
        residual = re.sub(r"\b(?:video nghe nhac|nghe nhac|xem video)\b", " ", residual)
        residual = re.sub(r"\s+", " ", residual).strip(" ,;-")
        return residual

    def _resolve_youtube_watch_url(self, search_phrase: str) -> str:
        phrase = _normalize_text(search_phrase)
        if not phrase:
            return ""
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(phrase)}"
        try:
            req = Request(
                search_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            with urlopen(req, timeout=8) as response:
                html = response.read().decode("utf-8", errors="ignore")
            match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
            if not match:
                match = re.search(r'/watch\?v=([A-Za-z0-9_-]{11})', html)
            if match:
                video_id = match.group(1)
                return f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        except Exception:
            return ""
        return ""

    def _is_frame_invalid(self, img: Image.Image) -> bool:
        if not img: return True
        try:
            # v1.1.88: Strict black screen detection
            if img.getbbox() is None:
                return True
            # Check if mostly black (max intensity < 5)
            stat = img.convert("L").getextrema()
            if stat[1] < 5: return True 
            return False
        except: return True

    def _generate_premium_splash(self, mode: str = "phantom") -> Image.Image:
        """Generate an animated premium splash frame with gradient, sparkles and grid."""
        import random
        import math
        
        W, H = 1280, 720
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        # Use time for subtle animation between frames
        t = time.time()
        phase = (t % 8.0) / 8.0  # 0..1 cycle over 8 seconds
        
        # Deep dark gradient background with subtle color shift
        for y in range(H):
            r_frac = y / H
            # Dark navy to deep purple gradient
            r = int(6 + 12 * r_frac + 4 * math.sin(phase * math.pi * 2))
            g = int(8 + 6 * r_frac)
            b = int(18 + 22 * r_frac + 6 * math.sin(phase * math.pi * 2 + 1.0))
            draw.line([(0, y), (W, y)], fill=(max(0, min(r, 40)), max(0, min(g, 20)), max(0, min(b, 50))))
        
        # Radial ambient glow at center
        cx, cy = W // 2, H // 2 - 40
        for radius in range(200, 10, -3):
            alpha_factor = max(0.0, 1.0 - (radius / 200.0))
            intensity = int(alpha_factor * 18 * (0.7 + 0.3 * math.sin(phase * math.pi * 2)))
            glow_color = (
                max(0, min(255, 8 + intensity)),
                max(0, min(255, 12 + intensity // 2)),
                max(0, min(255, 28 + intensity * 2)),
            )
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=glow_color,
            )
        
        # Sparkle dots — scattered across the screen
        random.seed(42)  # Consistent positions
        for i in range(80):
            sx = random.randint(20, W - 20)
            sy = random.randint(20, H - 20)
            # Each sparkle has its own phase offset for twinkling
            sparkle_phase = (t * 0.8 + i * 0.37) % 1.0
            brightness = int(60 + 140 * abs(math.sin(sparkle_phase * math.pi)))
            size = 1 if i > 40 else 2
            # Teal/cyan sparkles
            sparkle_r = max(0, min(255, brightness // 4))
            sparkle_g = max(0, min(255, brightness // 2 + 30))
            sparkle_b = max(0, min(255, brightness))
            if size == 2:
                draw.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(sparkle_r, sparkle_g, sparkle_b))
            else:
                draw.point((sx, sy), fill=(sparkle_r, sparkle_g, sparkle_b))
        
        # v1.0.7: Dynamic Moving Grid
        for i in range(0, H, 30):
            offset = int(5 * math.sin(t + i/100.0))
            draw.line([(0, i + offset), (W, i + offset)], fill=(20, 30, 45), width=1)
        for i in range(0, W, 30):
            offset = int(5 * math.cos(t + i/100.0))
            draw.line([(i + offset, 0), (i + offset, H)], fill=(20, 30, 45), width=1)

        # Center text — clean, modern
        mode_label = {"super": "SUPER PHANTOM", "phantom": "PHANTOM", "live": "LIVE"}.get(mode, mode.upper())
        
        # Status text
        status_text = self.vision_health_status if self.vision_health_status != "Healthy" else "Skemi: Đang chuẩn bị cửa sổ ngầm..."
        if (
            not self.target_window_hwnd
            and mode != "live"
            and self.vision_health_status == "Healthy"
        ):
            status_text = "Skemi: Đang tìm kiếm và khóa ứng dụng..."
            
        if self.runtime_state == "launching":
            status_text = "Skemi: Đang khởi động... Vui lòng không thao tác."
        elif self.runtime_state == "hidden_ready":
            status_text = "Skemi: Đã sẵn sàng. Bạn có thể bật ứng dụng bất cứ lúc nào."
            
        # v1.1.85: Show detailed AI action if available
        ai_action = str(self.last_ai_action_desc or "").strip()
        if ai_action and ai_action != status_text:
            status_text = f"{status_text}\n{ai_action}"
            
        # v1.1.92: Show capture diagnostics if black screen is persistent
        if self.consecutive_black_frames > 5 and _last_capture_error:
            status_text = f"{status_text}\n[DIAGNOSTIC: {_last_capture_error}]"
        
        # Draw with font if possible
        try:
            f_main = ImageFont.truetype("arial.ttf", 28)
            f_sub = ImageFont.truetype("arial.ttf", 18)
        except:
            f_main = f_sub = None

        if f_main:
            # Center the logo icon
            draw.text((W // 2 - 15, H // 2 - 60), "✦", fill=(45, 212, 191), font=f_main)
            # Center the title
            tw = draw.textbbox((0,0), f"SKEMI {mode_label}", font=f_main)[2]
            draw.text(((W - tw) // 2, H // 2 - 20), f"SKEMI {mode_label}", fill=(120, 200, 220), font=f_main)
            # Center the status
            sw = draw.textbbox((0,0), status_text, font=f_sub)[2]
            draw.text(((W - sw) // 2, H // 2 + 25), status_text, fill=(80, 120, 160), font=f_sub)
        else:
            draw.text((W // 2 - 30, H // 2 - 30), "✦", fill=(45, 212, 191))
            draw.text((W // 2 - 60, H // 2 + 5), f"SKEMI {mode_label}", fill=(120, 200, 220))
            draw.text((W // 2 - 70, H // 2 + 30), status_text, fill=(80, 120, 160))
        
        # Thin accent line
        line_y = H // 2 + 55
        line_w = int(160 * (0.6 + 0.4 * math.sin(phase * math.pi * 2)))
        draw.line(
            [(W // 2 - line_w, line_y), (W // 2 + line_w, line_y)],
            fill=(34, 211, 238),
            width=1,
        )
        
        return img

    def _capture_current_display_sync(self):
        hdc_raw = 0
        src_dc = mem_dc = bmp = None
        try:
            # v8.6: Confine capture to the targeted virtual monitor only.
            # This fixes the "tiny stream/black space" issue caused by SM_CXVIRTUALSCREEN.
            try:
                return jarvis_display_manager.capture()
            except Exception as e:
                _phantom_debug(f"[CAPTURE ERROR] {e}")
                return None
        except Exception:
            return None
        finally:
            with contextlib.suppress(Exception):
                if mem_dc:
                    mem_dc.DeleteDC()
            with contextlib.suppress(Exception):
                if src_dc:
                    src_dc.DeleteDC()
            with contextlib.suppress(Exception):
                if bmp:
                    win32gui.DeleteObject(bmp.GetHandle())
            with contextlib.suppress(Exception):
                if hdc_raw:
                    win32gui.ReleaseDC(0, hdc_raw)

    def _capture_target_virtual_desktop_sync(self):
        status = self._refresh_jarvis_display_status(force=False)
        if not status.get("workspace_ready"):
            self.vision_health_status = str(status.get("last_launch_error") or "Phantom Desktop is not ready.")
            return None
        # v2.0: Always capture full virtual desktop
        img = jarvis_display_manager.capture()
        if img is None:
            self.vision_health_status = "Phantom Desktop capture is not producing frames yet."
            return None
        self.vision_health_status = "Healthy"
        return img

    def _grab_for_stream_sync(self):
        img = None
        target_hwnd = self.target_window_hwnd
        mode = self.mode
        phantom_locked = mode == "phantom"
        
        # 1. Phantom Mode: Full Virtual Desktop Capture
        if phantom_locked:
            # Try virtual display first
            img = self._capture_target_virtual_desktop_sync()
            
            # If virtual display not ready, try Task View Desktop capture (for existing desktop selection)
            if img is None and self.desktop_index >= 0 and self.h_phantom_desk:
                img = self._capture_hidden_desktop_sync()
                if img:
                    self.vision_health_status = f"Streaming Desktop {self.desktop_index + 1}"
            
            # Z-Order enforcement for targeted window (every 30 frames)
            if (
                target_hwnd
                and win32gui.IsWindow(target_hwnd)
                and self.frame_version % 30 == 0
                and jarvis_display_manager.contains_hwnd(target_hwnd)
            ):
                with contextlib.suppress(Exception):
                    # Bring to top of virtual desktop without stealing focus
                    win32gui.SetWindowPos(target_hwnd, win32con.HWND_TOP, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

            if img is None or self._is_frame_invalid(img):
                # v8.5: If phantom capture failed, DO NOT fallback to primary monitor.
                # Use a splash screen instead to maintain privacy.
                self.consecutive_black_frames += 1
                if self._last_stream_img and self.consecutive_black_frames < 30:
                    img = self._last_stream_img
                else:
                    img = self._generate_premium_splash("phantom")
                    self.vision_health_status = "Phantom Syncing..."
            else:
                self.consecutive_black_frames = 0
                self.vision_health_status = "Healthy"
                # Set AI control active after first successful phantom frame
                if not self.preview_only:
                    _set_ai_control_active(True)
            self.capture_w, self.capture_h = img.size
            self._last_stream_img = img
            return img.convert("RGB")

        # 2. Live Control: full desktop capture used by both the watch-only
        # preview and the ghost-input control path. This capture branch itself
        # never injects input, focuses windows, or depends on a target app window.
        if mode == "live" and not target_hwnd:
            width = max(1, int(win32api.GetSystemMetrics(win32con.SM_CXSCREEN) or 1280))
            height = max(1, int(win32api.GetSystemMetrics(win32con.SM_CYSCREEN) or 720))
            img = _capture_screen_region_sync({"left": 0, "top": 0, "width": width, "height": height})

        # 3. Window Capture (legacy standard sessions)
        if img is None:
            src_hwnd = target_hwnd or self._resolve_window_handle_sync()
            if src_hwnd and win32gui.IsWindow(src_hwnd):
                img = self._capture_window_printwindow_sync(src_hwnd, flags=3)
                if img is None or self._is_frame_invalid(img):
                    img = self._capture_window_printwindow_sync(src_hwnd, flags=2)
        
        # 3. Final Fallback: Splash or Last Good Frame
        if img is None or self._is_frame_invalid(img):
            self.consecutive_black_frames += 1
            if self._last_stream_img and self.consecutive_black_frames < 20:
                img = self._last_stream_img
            else:
                img = self._generate_premium_splash()
                self._last_stream_img = img
                self.vision_health_status = "Waiting..."
        else:
            self.consecutive_black_frames = 0
            self.vision_health_status = "Healthy"

        if img:
            self.capture_w, self.capture_h = img.size
            self._last_stream_img = img
            return img.convert("RGB")
        return None

    def _capture_window_printwindow_sync(self, hwnd: int, flags: int = 2):
        try:
            # Handle minimized state for capture
            is_min = win32gui.IsIconic(hwnd)
            if is_min:
                # Try to capture without restore first (PW_RENDERFULLCONTENT)
                pass 

            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2]-rect[0], rect[3]-rect[1]
            if w <= 0 or h <= 0: return None
            hdc = win32gui.GetWindowDC(hwnd)
            src_dc, mem_dc = win32ui.CreateDCFromHandle(hdc), win32ui.CreateDCFromHandle(hdc).CreateCompatibleDC()
            bmp = win32ui.CreateBitmap(); bmp.CreateCompatibleBitmap(src_dc, w, h); mem_dc.SelectObject(bmp)
            ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), flags)
            
            # v1.0.1: BitBlt Fallback for Hardware Accelerated windows (Discord/Zalo/Chrome)
            # If PrintWindow fails or returns black, BitBlt can sometimes catch it if CAPTUREBLT is used
            # but it requires the window to be somewhat 'active' or on-screen. 
            # For off-screen windows, BitBlt usually fails, but we try as a last resort.
            info, bits = bmp.GetInfo(), bmp.GetBitmapBits(True)
            img = Image.frombuffer("RGB", (info['bmWidth'], info['bmHeight']), bits, "raw", "BGRX", 0, 1)
            
            if self._is_frame_invalid(img):
                # Try BitBlt from Window DC (sometimes works for off-screen if NOT hardware accelerated)
                mem_dc.BitBlt((0, 0), (w, h), src_dc, (0, 0), win32con.SRCCOPY | 0x40000000)
                info, bits = bmp.GetInfo(), bmp.GetBitmapBits(True)
                img = Image.frombuffer("RGB", (info['bmWidth'], info['bmHeight']), bits, "raw", "BGRX", 0, 1)

            win32gui.ReleaseDC(hwnd, hdc)
            return img.convert("RGB")
        except: return None

    async def _background_streaming_loop(self):
        """High-frequency background capture loop to ensure smooth, persistent video."""
        _phantom_debug(f"[STREAM] Background worker started for session {self.session_id}")
        try:
            while not self.cancelled:
                # Keep this conservative; the main capture loop already streams.
                await self._capture_screen_async(force=True)
                await asyncio.sleep(0.40 if self.mode == "phantom" else 0.50)
        except Exception as e:
            _phantom_debug(f"[STREAM] Worker crashed: {e}")
        finally:
            _phantom_debug(f"[STREAM] Worker stopped for session {self.session_id}")

    async def _capture_screen_async(self, force=False):
        if self.mode == "phantom":
            self.automation_mode = "vision_fallback"
            async with self._capture_lock:
                quality = 55 if self.is_thinking else 75
                img = await self._run_sync(self._grab_for_stream_sync)
            if img is None:
                return ""
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            captured = base64.b64encode(buf.getvalue()).decode("utf-8")
            self.latest_live_b64, self.latest_live_at = captured, time.time()
            self.frame_version += 1
            if captured and not self.preview_only:
                _set_ai_control_active(True)
            return captured

        await self._ensure_web_surface_ready_async(force=bool(force))
        if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
            captured = await self._capture_web_surface_async()
            if captured:
                return captured
        self.automation_mode = "vision_fallback"
        async with self._capture_lock:
            # Speed Buff: Dynamic frame quality based on thinking state
            quality = 55 if self.is_thinking else 75
            img = await self._run_sync(self._grab_for_stream_sync)
        
        # Scale and format
        if img is None:
            return ""
        
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        captured = base64.b64encode(buf.getvalue()).decode("utf-8")
        self.latest_live_b64, self.latest_live_at = captured, time.time()
        self.frame_version += 1
        if captured and not self.preview_only:
            _set_ai_control_active(True)
        return captured

    async def _continuous_capture_loop(self):
        """High-speed mirroring loop that keeps latest_live_b64 fresh for streaming."""
        while not self.cancelled and not self.agent_stopped and not self.session_closed:
            try:
                await self._capture_screen_async(force=True)
            except Exception as exc:
                _phantom_debug(f"[CAPTURE_LOOP] Exception in capture: {exc}")
            await asyncio.sleep(0.75 if self.mode == "live" else 0.50)

    async def runtime_snapshot(self):
        metrics_mode = "browser_page" if self.web_surface is not None and getattr(self.web_surface, "is_connected", False) else ("native_window" if self.mode != "live" else "screen")
        metrics_width = int(self.web_viewport_width or self.capture_w or 1280)
        metrics_height = int(self.web_viewport_height or self.capture_h or 900)
        stream_state = self._stream_state()
        workspace_status = self._refresh_jarvis_display_status(force=False) if self.mode == "phantom" else {}
        self.automation_mode = "web_semantic" if (self.web_surface is not None and getattr(self.web_surface, "is_connected", False) and self.mode != "live") else ("app_hidden" if self.mode != "live" else "visible_live")
        return {
            "session_id": self.session_id, "state": self.runtime_state, "mode": self._public_mode(),
            "task_state": self._task_state(),
            "stream_state": stream_state,
            "status_text": str(self.last_ai_action_desc or ""),
            "final_result": str(self.last_result or ""),
            "surface_mode": self._public_mode(),
            "automation_mode": self.automation_mode,
            "current_title": str(self._current_surface_label("Desktop")),
            "current_url": str(self.current_url or ""),
            "message": str(self.last_ai_action_desc),
            "image": self.latest_live_b64,
            "is_thinking": self.is_thinking,
            "runtime_agent_type": "desktop",
            "execution_surface": "browser_hidden" if (self.web_surface is not None and getattr(self.web_surface, "is_connected", False) and self.mode != "live") else ("app_hidden" if self.mode != "live" else "visible_live"),
            "stream_health": "live" if stream_state in {"live", "frozen"} else ("booting" if stream_state == "connecting" else ("degraded" if stream_state == "degraded" else "stopped")),
            "last_action_at": float(self.last_active_at or time.time()),
            "last_result": str(self.last_result or self.last_ai_action_desc or ""),
            "requires_consent": bool(self.pending_confirmation),
            "consent_reason": str(self.consent_reason or ""),
            "pending_confirmation": dict(self.pending_confirmation or {}),
            "pending_manual_takeover": {},
            "target_window_hwnd": int(self.target_window_hwnd or 0),
            "target_window_title": str(self._current_surface_label()),
            "target_window_class": str(self.target_window_class or ""),
            "frame_version": int(self.frame_version or 0),
            "workspace_kind": str(workspace_status.get("workspace_kind") or self.workspace_kind),
            "workspace_ready": bool(workspace_status.get("workspace_ready", self.workspace_ready)),
            "setup_state": str(workspace_status.get("setup_state") or ""),
            "driver_status": str(workspace_status.get("driver_status") or ""),
            "driver_version": str(workspace_status.get("driver_version") or ""),
            "driver_provider": str(workspace_status.get("driver_provider") or ""),
            "bootstrap_required": bool(workspace_status.get("bootstrap_required", False)),
            "bootstrap_url": str(workspace_status.get("bootstrap_url") or PHANTOM_BOOTSTRAP_URL),
            "display_id": str(workspace_status.get("display_id") or "") if _phantom_debug_enabled() else "",
            "display_role": str(workspace_status.get("display_role") or ""),
            "isolation_level": str(workspace_status.get("isolation_level") or ""),
            "display_bounds": dict(workspace_status.get("display_bounds") or {}),
            "launch_policy": str(workspace_status.get("launch_policy") or ""),
            "last_launch_error": str(self.last_launch_error or workspace_status.get("last_launch_error") or ""),
            "last_launch_error_code": str(self.last_launch_error_code or workspace_status.get("last_launch_error_code") or ""),
            "update_state": str(workspace_status.get("update_state") or "current"),
            "update_available": bool(workspace_status.get("update_available", False)),
            "update_required": bool(workspace_status.get("update_required", False)),
            "latest_companion_version": str(workspace_status.get("latest_companion_version") or ""),
            "latest_driver_version": str(workspace_status.get("latest_driver_version") or ""),
            "update_url": str(workspace_status.get("update_url") or PHANTOM_UPDATE_URL),
            "update_size_mb": str(workspace_status.get("update_size_mb") or ""),
            "update_requires_admin": bool(workspace_status.get("update_requires_admin", True)),
            "update_message": str(workspace_status.get("update_message") or ""),
            "cursor_overlay": dict(self.action_overlay or {}),
            "surface_metrics": {
                "capture_width": metrics_width,
                "capture_height": metrics_height,
                "mode": metrics_mode,
                "page_width": metrics_width,
                "page_height": metrics_height,
                "content_width": metrics_width,
                "content_height": metrics_height,
                "content_left": 0,
                "content_top": 0,
            },
            "last_active_at": float(self.last_active_at or time.time()),
        }

    async def manual_click(self, x: int, y: int, click_count: int = 1):
        if self.cancelled or self.agent_stopped:
            return {"ok": False, "reason": "stopped"}
        if self.mode == "live":
            if self.preview_only:
                return {"ok": False, "reason": "live_preview_watch_only"}
            lx = int(x or 0)
            ly = int(y or 0)
            clicks = max(1, int(click_count or 1))
            act = "double_click" if clicks >= 2 else "click"
            ok = await self._run_sync(self._live_ghost_action_sync, act, {"x": lx, "y": ly})
            self.last_ai_action_desc = f"Live control click at ({lx}, {ly})"
            self.last_active_at = time.time()
            await self._capture_screen_async(force=True)
            return {"ok": bool(ok), "x": lx, "y": ly, "mode": "live"}
        safe_x = int(x or 0)
        safe_y = int(y or 0)
        clicks = max(1, int(click_count or 1))
        if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
            for _ in range(clicks):
                await self._execute_web_action_async("click", {"x": safe_x, "y": safe_y})
        else:
            hwnd = int(self.target_window_hwnd or 0)
            if not hwnd or not win32gui.IsWindow(hwnd):
                return {"ok": False, "reason": "target_lock_required"}
            for _ in range(clicks):
                await self._run_sync(manual_click, safe_x, safe_y, hwnd)
        self.last_ai_action_desc = f"Manual click at ({safe_x}, {safe_y})"
        self.last_active_at = time.time()
        await self._capture_screen_async(force=True)
        return {"ok": True, "x": safe_x, "y": safe_y}

    async def manual_scroll(self, direction: str = "down"):
        if self.cancelled or self.agent_stopped:
            return {"ok": False, "reason": "stopped"}
        if self.mode == "live":
            if self.preview_only:
                return {"ok": False, "reason": "live_preview_watch_only"}
            norm = str(direction or "down").strip().lower()
            amount = 120 if norm == "up" else -120
            ok = await self._run_sync(self._live_ghost_action_sync, "scroll", {"x": 500, "y": 500, "amount": amount})
            self.last_ai_action_desc = f"Live control scroll {norm}"
            self.last_active_at = time.time()
            await self._capture_screen_async(force=True)
            return {"ok": bool(ok), "direction": norm, "mode": "live"}
        normalized = str(direction or "down").strip().lower()
        amount = 120 if normalized == "up" else -120
        if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
            await self._execute_web_action_async("scroll", {"amount": amount})
        else:
            hwnd = int(self.target_window_hwnd or 0)
            if not hwnd or not win32gui.IsWindow(hwnd):
                return {"ok": False, "reason": "target_lock_required"}
            await self._run_sync(self._run_action_on_target_desktop_sync, manual_scroll, amount, hwnd)
        self.last_ai_action_desc = f"Manual scroll {normalized}"
        self.last_active_at = time.time()
        await self._capture_screen_async(force=True)
        return {"ok": True, "direction": normalized}

    async def manual_press(self, key: str = ""):
        if self.cancelled or self.agent_stopped:
            return {"ok": False, "reason": "stopped"}
        if self.mode == "live":
            if self.preview_only:
                return {"ok": False, "reason": "live_preview_watch_only"}
            lkey = str(key or "").strip() or "enter"
            ok = await self._run_sync(self._live_ghost_action_sync, "key", {"key": lkey})
            self.last_ai_action_desc = f"Live control key: {lkey}"
            self.last_active_at = time.time()
            await self._capture_screen_async(force=True)
            return {"ok": bool(ok), "key": lkey, "mode": "live"}
        safe_key = str(key or "").strip() or "enter"
        if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
            await self._execute_web_action_async("key", {"key": safe_key})
        else:
            hwnd = int(self.target_window_hwnd or 0)
            if not hwnd or not win32gui.IsWindow(hwnd):
                return {"ok": False, "reason": "target_lock_required"}
            await self._run_sync(manual_press, safe_key, hwnd)
        self.last_ai_action_desc = f"Manual key: {safe_key}"
        self.last_active_at = time.time()
        await self._capture_screen_async(force=True)
        return {"ok": True, "key": safe_key}

    async def manual_type(self, text: str = ""):
        if self.cancelled or self.agent_stopped:
            return {"ok": False, "reason": "stopped"}
        if self.mode == "live":
            if self.preview_only:
                return {"ok": False, "reason": "live_preview_watch_only"}
            ltext = str(text or "")
            if not ltext:
                return {"ok": False, "reason": "text_required"}
            ok = await self._run_sync(self._live_ghost_action_sync, "type", {"text": ltext})
            self.last_ai_action_desc = f"Live control type: {ltext[:48]}"
            self.last_active_at = time.time()
            await self._capture_screen_async(force=True)
            return {"ok": bool(ok), "text": ltext, "mode": "live"}
        safe_text = str(text or "")
        if not safe_text:
            return {"ok": False, "reason": "text_required"}
        if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
            await self._execute_web_action_async("type", {"text": safe_text})
        else:
            hwnd = int(self.target_window_hwnd or 0)
            if not hwnd or not win32gui.IsWindow(hwnd):
                return {"ok": False, "reason": "target_lock_required"}
            await self._run_sync(manual_type, safe_text, hwnd)
        self.last_ai_action_desc = f"Manual type: {safe_text[:48]}"
        self.last_active_at = time.time()
        await self._capture_screen_async(force=True)
        return {"ok": True, "text": safe_text}

    def resume_manual_takeover(self) -> bool:
        self.manual_mode = False
        return True

    def reveal_target_window(self) -> bool:
        hwnd = int(self.target_window_hwnd or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):
            hwnd = int(self._resolve_window_handle_sync() or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        self.browser_offscreen = False
        self.user_revealed_target = True
        return self._restore_target_window_for_user(hwnd, activate=True)

    def _proactive_launch_sync(self, query: str) -> bool:
        self.last_ai_action_desc = "Skemi is analyzing your request"
        self.last_active_at = time.time()
        if self.mode == "phantom":
            self.tasks = []
            self.last_ai_action_desc = self._phantom_desktop_status_text()
            return True
        
        # v1.0: Multi-App Task Planner (Discord, Zalo, YouTube...)
        import re
        query = query.strip()
        # Split by "và", "and", ",", ";"
        parts = re.split(r'\b(?:và|and)\b|[;,]', query, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) > 1:
            self.tasks = []
            for p in parts:
                self.tasks.append({"action": "launch", "goal": p, "status": "pending"})
            self.last_ai_action_desc = f"Skemi: Đã nhận lệnh. Sẽ thực hiện {len(self.tasks)} nhiệm vụ theo trình tự."
            self.speak(f"Skemi đã rõ. Sẽ thực hiện lần lượt {len(self.tasks)} yêu cầu này.")
            return True # Main loop handles tasks
        
        return self._proactive_launch_single_sync(query)

    def _launch_plan_tasks_sync(self) -> bool:
        """Launch decomposed tasks one by one instead of treating the prompt as an app name."""
        if self.mode == "phantom":
            self.tasks = []
            self.last_ai_action_desc = self._phantom_desktop_status_text()
            return True
        if not self.tasks:
            return self._proactive_launch_sync(self.command)
        any_launched = False
        self.task_results = []
        for index, task in enumerate(self.tasks):
            if self.cancelled or self.agent_stopped:
                break
            self.current_task_index = index
            goal = str(task.get("goal") or task.get("title") or "").strip()
            target = str(task.get("target") or "").strip()
            query = goal or target or self.command
            if not query:
                task["status"] = "failed"
                task["result"] = "Task did not include a usable goal."
                self.task_results.append(dict(task))
                continue
            self.last_ai_action_desc = f"Skemi: Đang xử lý nhiệm vụ {index + 1}/{len(self.tasks)}: {task.get('goal') or query}"
            self.speak(f"Tiếp theo, Skemi sẽ xử lý: {task.get('goal') or query}")
            self.recent_actions.append(self.last_ai_action_desc)
            
            launched = self._proactive_launch_single_sync(query)
            
            task["status"] = "done" if launched else "failed"
            task["result"] = "Hoàn tất." if launched else "Không thể mở."
            self.task_results.append(dict(task))
            any_launched = any_launched or bool(launched)
            
            # v1.0.9: Wait for OS to stabilize between launches
            if index < len(self.tasks) - 1:
                time.sleep(2.5)
                
        if any_launched:
            self.speak("Tôi đã chuẩn bị xong môi trường cho bạn. Bắt đầu xử lý chi tiết.")
        return any_launched

    def _task_result_summary(self) -> str:
        if not self.task_results:
            return ""
        prefers_vi = self._prefers_vietnamese()
        lines = []
        for index, task in enumerate(self.task_results, start=1):
            title = str(task.get("title") or task.get("goal") or f"Task {index}").strip()
            status = str(task.get("status") or "unknown")
            result = str(task.get("result") or "").strip()
            if prefers_vi:
                state = "xong" if status == "done" else "chưa xong"
                lines.append(f"{index}. {title}: {state}. {result}".strip())
            else:
                lines.append(f"{index}. {title}: {status}. {result}".strip())
        if prefers_vi:
            return "Kết quả các tác vụ: " + " ".join(lines)
        return "Task results: " + " ".join(lines)

    def _switch_to_target_for_launch(self):
        return

    def _switch_back_after_launch(self):
        return

    def _switch_to_desktop_2_sync(self):
        """Legacy no-op: Jarvis uses a real virtual display, not Task View desktops."""
        return

    def _ensure_user_returned_to_desktop_1_sync(self):
        """Legacy no-op retained for callers; Jarvis never switches the user desktop."""
        return

    def _live_ghost_action_sync(self, action: str, params: dict) -> bool:
        """Live Control engine.

        Act on whatever window currently sits under the AI's target point on the
        user's REAL desktop, using background PostMessage ghost-input. This never
        moves the physical cursor and never calls SetForegroundWindow, so the user
        keeps full control of their own mouse/keyboard while Skemi works — exactly
        like quietly sharing the same machine.

        Vision coordinates arrive as 0-1000 normalized values over the full screen.
        Best-effort: works for Win32 / browser / Office / Electron windows that
        honour background messages; hardware-accelerated games/canvas may ignore
        background input (Phantom mode remains the universal fallback).

        Returns True when an input message was successfully posted.
        """
        try:
            action = str(action or "").strip().lower()
            params = params or {}
            screen_w = max(1, int(win32api.GetSystemMetrics(win32con.SM_CXSCREEN) or 1280))
            screen_h = max(1, int(win32api.GetSystemMetrics(win32con.SM_CYSCREEN) or 720))

            def _norm_to_screen(nx, ny):
                try:
                    fx = int(float(str(nx)))
                except Exception:
                    fx = 500
                try:
                    fy = int(float(str(ny)))
                except Exception:
                    fy = 500
                sx = int(max(0, min(1000, fx)) * screen_w / 1000)
                sy = int(max(0, min(1000, fy)) * screen_h / 1000)
                return sx, sy

            def _resolve_target(sx, sy):
                handle = 0
                try:
                    handle = int(win32gui.WindowFromPoint((sx, sy)) or 0)
                except Exception:
                    handle = 0
                if handle and win32gui.IsWindow(handle):
                    # Walk up to the owning top-level so ScreenToClient maps correctly,
                    # then back down to the real input child (Chromium RenderWidget etc.)
                    try:
                        root = int(ctypes.windll.user32.GetAncestor(handle, 2) or handle)  # GA_ROOT
                    except Exception:
                        root = handle
                    if root and win32gui.IsWindow(root):
                        self._live_last_target_hwnd = root
                        return _find_input_target_child(root)
                fg = int(win32gui.GetForegroundWindow() or 0)
                if fg and win32gui.IsWindow(fg):
                    self._live_last_target_hwnd = fg
                    return _find_input_target_child(fg)
                return 0

            if action in {"click", "double_click", "right_click"}:
                sx, sy = _norm_to_screen(params.get("x", 500), params.get("y", 500))
                target = _resolve_target(sx, sy)
                if not target:
                    return False
                try:
                    lx, ly = win32gui.ScreenToClient(target, (sx, sy))
                except Exception:
                    lx, ly = 0, 0
                lparam = win32api.MAKELONG(int(lx), int(ly))
                if action == "right_click":
                    down, up, btn = win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON
                else:
                    down, up, btn = win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON
                reps = 2 if action == "double_click" else 1
                for _ in range(reps):
                    win32gui.PostMessage(target, down, btn, lparam)
                    time.sleep(0.01)
                    win32gui.PostMessage(target, up, 0, lparam)
                    time.sleep(0.01)
                return True

            if action == "scroll":
                amount = params.get("amount", -120)
                try:
                    amount = int(float(str(amount)))
                except Exception:
                    amount = -120
                sx, sy = _norm_to_screen(params.get("x", 500), params.get("y", 500))
                target = _resolve_target(sx, sy)
                if not target:
                    return False
                # WM_MOUSEWHEEL: wParam high word = delta, lParam = screen coords.
                wheel = win32api.MAKELONG(0, amount)
                lparam = win32api.MAKELONG(int(sx), int(sy))
                with contextlib.suppress(Exception):
                    win32gui.PostMessage(target, win32con.WM_MOUSEWHEEL, wheel, lparam)
                return True

            if action in {"type", "key"}:
                target = int(getattr(self, "_live_last_target_hwnd", 0) or 0)
                if not target or not win32gui.IsWindow(target):
                    target = int(win32gui.GetForegroundWindow() or 0)
                if not target or not win32gui.IsWindow(target):
                    return False
                focus = _find_input_target_child(target)
                if action == "type":
                    text = str(params.get("text", "") or "")
                    if not text:
                        return False
                    for ch in text:
                        if ch == '\n':
                            win32gui.PostMessage(focus, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                            win32gui.PostMessage(focus, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                        else:
                            win32gui.PostMessage(focus, win32con.WM_CHAR, ord(ch), 0)
                        time.sleep(0.005)
                    if params.get("submit"):
                        win32gui.PostMessage(focus, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                        win32gui.PostMessage(focus, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                    return True
                key = str(params.get("key", "enter") or "enter").lower().strip()
                vk_map = {
                    'enter': win32con.VK_RETURN, 'return': win32con.VK_RETURN, 'tab': win32con.VK_TAB,
                    'backspace': win32con.VK_BACK, 'esc': win32con.VK_ESCAPE, 'escape': win32con.VK_ESCAPE,
                    'up': win32con.VK_UP, 'down': win32con.VK_DOWN, 'left': win32con.VK_LEFT,
                    'right': win32con.VK_RIGHT, 'space': win32con.VK_SPACE, 'delete': win32con.VK_DELETE,
                    'home': win32con.VK_HOME, 'end': win32con.VK_END,
                }
                vk = vk_map.get(key)
                if not vk and len(key) == 1:
                    vk = ctypes.windll.user32.VkKeyScanW(ord(key)) & 0xFF
                if not vk:
                    return False
                win32gui.PostMessage(focus, win32con.WM_KEYDOWN, vk, 0)
                win32gui.PostMessage(focus, win32con.WM_KEYUP, vk, 0)
                return True
        except Exception as exc:
            _phantom_debug(f"[LIVE CONTROL] ghost action failed: {exc}")
        return False

    def _run_action_on_target_desktop_sync(self, func, *args):
        """Run the action without touching the user's active desktop."""
        return func(*args)

    def _proactive_launch_single_sync(self, query: str) -> bool:
        if not query: return False
        self._switch_to_target_for_launch()
        try:
            return self._proactive_launch_inner_sync(query)
        finally:
            time.sleep(0.1)
            self._switch_back_after_launch()

    def _proactive_launch_inner_sync(self, query: str) -> bool:
        cmd = _normalize_text(query)
        si = subprocess.STARTUPINFO()
        if sys.platform == "win32":
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = win32con.SW_SHOWNORMAL
            si.lpDesktop = None
            self._configure_startup_for_jarvis_display(si)

        explicit_web = bool(re.search(r"\b(web|website|browser|site|trang web)\b", cmd))
        if self.mode == "phantom" and not self._jarvis_display_ready():
            self.last_launch_error_code = "phantom_display_missing"
            self.last_ai_action_desc = self.last_launch_error or "Phantom Desktop is not ready."
            self.last_result = self.last_ai_action_desc
            return False

        self._is_launching = True
        try:
            # 1. Local App Check (High Priority)
            app_lookup_query = _extract_app_launch_phrase(query) or cmd
            app_alias = _match_app_alias(app_lookup_query)
            launch_commands = list(_resolve_launchable_commands(app_lookup_query))
            fallback_url = _match_app_web_fallback(app_lookup_query) or _match_app_web_fallback(query)
            native_attempted = False
            native_isolation_blocked = False
            if launch_commands and not explicit_web:
                for launch_command in launch_commands:
                    native_attempted = True
                    executable = launch_command[0]
                    _phantom_debug(f"[LAUNCH] Native App Match: {' '.join(launch_command)}")
                    if self._safe_popen_and_claim(launch_command, si, [app_lookup_query, os.path.splitext(os.path.basename(executable))[0]]):
                        return True
                    if self.mode == "phantom" and "outside Phantom" in str(self.last_launch_error or ""):
                        native_isolation_blocked = True
                        break
            if native_isolation_blocked:
                return False

            # 2. Local Path Check
            resolved_path = _extract_existing_path(query) or _resolve_shell_folder_path(query)
            if resolved_path:
                _phantom_debug(f"[LAUNCH] Explorer target: {resolved_path}")
                return self._launch_explorer_target_sync(resolved_path, startupinfo=si, prefer_tokens=[os.path.basename(resolved_path)])

            # 3. Web Redirection
            matched_web = next((key for key in FUZZY_WEB_MAP if re.search(rf"\b{re.escape(key)}\b", cmd)), "")
            looks_like_url = "." in cmd and (" " not in cmd or cmd.startswith("http"))
            wants_browser = bool(matched_web or looks_like_url or any(term in cmd for term in ("browser", "chrome", "edge", "website", "web", "site")))
            target_url = ""
            if wants_browser and fallback_url:
                target_url = fallback_url
            elif matched_web:
                target_url = FUZZY_WEB_MAP.get(matched_web, "")
            elif looks_like_url:
                target_url = query.strip()
            elif wants_browser:
                target_url = f"https://www.google.com/search?q={quote_plus(query)}"
            if wants_browser and self.web_surface and getattr(self.web_surface, "is_connected", False):
                try:
                    self.last_ai_action_desc = f"Skemi: Đang mở tab mới cho bạn: {query}"
                    asyncio.run_coroutine_threadsafe(self._execute_web_action_async("navigate", {"url": target_url}), self._loop)
                    return True
                except Exception: pass
            if wants_browser and target_url:
                return self._launch_browser_target_sync(
                    target_url,
                    startupinfo=si,
                    prefer_tokens=[matched_web, query],
                )

            # 4. Fallback (General AppID search)
            if not explicit_web:
                if self._launch_app_by_query_sync(query, startupinfo=si):
                    return True
                if self.mode == "phantom" and "outside Phantom" in str(self.last_launch_error or ""):
                    return False
            if native_attempted:
                self.last_ai_action_desc = "Native app was found, but Windows did not create a controllable window on Phantom Desktop. I will not take over the user's existing app instance."
                self.last_launch_error = self.last_ai_action_desc
                self.last_launch_error_code = "native_cannot_be_isolated"
                return False
            if fallback_url:
                if explicit_web:
                    self.last_ai_action_desc = "Opening the requested web version on Phantom Desktop."
                    _phantom_debug(f"[LAUNCH] Explicit web request on Phantom Desktop: {fallback_url}")
                    return self._launch_browser_target_sync(
                        fallback_url,
                        startupinfo=si,
                        prefer_tokens=[app_alias or app_lookup_query, query],
                    )
                self.last_launch_error = (
                    "Native app was not found or could not be isolated on Phantom. "
                    "Skemi will not automatically open the web version unless you ask for the web version explicitly."
                )
                self.last_launch_error_code = "native_cannot_be_isolated"
                self.last_ai_action_desc = self.last_launch_error
                return False
            return False
        finally:
            self._is_launching = False

    def _safe_popen_and_claim(self, args: List[str], si: Optional[subprocess.STARTUPINFO], prefer_tokens: List[str]) -> bool:
        """Launch, claim only a new/Phantom-owned window, then place it on Phantom display."""
        prelaunch = self._snapshot_window_handles(include_hidden=True)
        self._set_launch_baseline(prelaunch)
        try:
            # v1.1.90: Aggressive existing window/process discovery
            existing_hwnd = 0 if self.mode == "phantom" else self._find_new_window_from_snapshot(set(), prefer_tokens=prefer_tokens, pid_hint=0, timeout=0.1, include_hidden=True)
            
            # If no window found, check for existing process (e.g. Discord, Chrome)
            if not existing_hwnd:
                import psutil
                process_names = {token.lower() for token in prefer_tokens if len(token) > 2}
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        p_name = str(p.info['name'] or "").lower()
                        if any(token in p_name for token in process_names):
                            # Found a matching process! Try to find its window.
                            existing_hwnd = _find_window_for_pid(p.info['pid'], prefer_tokens=prefer_tokens, include_hidden=True)
                            if existing_hwnd: break
                    except (psutil.NoSuchProcess, psutil.AccessDenied): continue

            if existing_hwnd and win32gui.IsWindow(existing_hwnd):
                _phantom_debug(f"[LAUNCH] Found existing window for {prefer_tokens}: HWND {existing_hwnd}")
                if self.mode == "phantom":
                    if not jarvis_display_manager.contains_hwnd(existing_hwnd):
                        self.last_launch_error = (
                            "Native app already has a running window outside Phantom; native cannot be isolated. "
                            "Skemi will not resize, minimize, move, or steal the user's existing app instance. "
                            "Ask for the web version explicitly if you want a browser fallback."
                        )
                        self.last_launch_error_code = "native_cannot_be_isolated"
                        self.last_ai_action_desc = self.last_launch_error
                        return False
                if self._claim_target_window(existing_hwnd, 0):
                    if self.mode == "phantom": self._stealth_target_window(existing_hwnd)
                    return True
            
            popen_kwargs: Dict[str, Any] = {
                "startupinfo": si,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            # Remember the user's foreground so we can hand it back after the newly
            # launched app grabs focus (phantom mode = AI must not steal focus).
            prev_fg = _grab_user_fg() if self.mode == "phantom" else 0
            proc = subprocess.Popen(args, **popen_kwargs)

            pid = int(getattr(proc, "pid", 0) or 0)
            hwnd = self._find_new_window_from_snapshot(prelaunch, prefer_tokens=prefer_tokens, pid_hint=pid, timeout=12.0, include_hidden=True)
            if hwnd:
                if not self._claim_target_window(hwnd, pid):
                    return False
                if self.mode == "phantom":
                    moved = self._stealth_target_window(hwnd)
                    if not moved:
                        _phantom_debug(f"[LAUNCH WARNING] Could not isolate HWND {hwnd} on Phantom Desktop; closing the launched window.")
                        self.last_launch_error = self.last_launch_error or "Could not place the launched window inside Phantom Desktop."
                        self.last_launch_error_code = "phantom_window_placement_failed"
                        self.last_ai_action_desc = self.last_launch_error
                        self._close_failed_launch_window_sync(hwnd, pid, prelaunch, close_new_handle=True, kill_pid=True)
                        return False
                    # App is on the virtual display; return focus to the user.
                    time.sleep(0.15)
                    _restore_user_fg(prev_fg)
                    return True
                return True
        except Exception as e:
            _phantom_debug(f"[LAUNCH ERROR] {e}")
        return False

    def _launch_app_by_query_sync(self, query: str, startupinfo: Optional[subprocess.STARTUPINFO] = None) -> bool:
        if self.mode == "phantom":
            self.last_ai_action_desc = self._phantom_desktop_status_text()
            return False
        try:
            app_lookup = _extract_app_launch_phrase(query) or query
            for launch_command in _resolve_dynamic_app_commands(app_lookup, limit=8):
                _phantom_debug(f"[LAUNCH] Dynamic App Match: {' '.join(launch_command)}")
                if self._safe_popen_and_claim(launch_command, startupinfo, [app_lookup]):
                    return True
                if self.mode == "phantom" and "outside Phantom" in str(self.last_launch_error or ""):
                    return False
        except Exception: pass
        return False

    def _start_stealth_sentry(
        self,
        target_pid: int = 0,
        target_hwnd: int = 0,
        existing_handles: Optional[set[int]] = None,
        prefer_tokens: Optional[List[str]] = None,
    ):
        if self.h_phantom_desk and self.mode != "live" and not self.browser_offscreen:
            return
        if self._stealth_sentry_running:
            return
        self._stealth_sentry_running = True
        def sentry():
            import time
            seen_hwnd = int(target_hwnd or 0)
            seen_pid = int(target_pid or 0)
            tokens = [token for token in (prefer_tokens or []) if token]

            try:
                while not self.cancelled and not self.agent_stopped and self.runtime_state not in {"done", "error", "stopped"}:
                    hwnd = 0
                    if seen_hwnd and win32gui.IsWindow(seen_hwnd):
                        hwnd = seen_hwnd
                    elif existing_handles:
                        hwnd = self._find_new_window_from_snapshot(
                            existing_handles,
                            prefer_tokens=[self.command, self.target_window_title, *tokens],
                            pid_hint=seen_pid,
                            timeout=0.04,
                            include_hidden=True,
                        )
                    if not hwnd and seen_pid:
                        hwnd = _find_window_for_pid(
                            seen_pid,
                            prefer_tokens=[self.target_window_title, *self.launch_target_tokens, self.command, *tokens],
                            include_hidden=True,
                            reject_handles=self._launch_baseline_handles if self.mode != "live" else None,
                        )
                    if not hwnd and existing_handles:
                        hwnd = self._find_new_window_from_snapshot(
                            existing_handles,
                            prefer_tokens=[self.command, self.target_window_title, *tokens],
                            pid_hint=0,
                            timeout=0.04,
                            include_hidden=True,
                        )
                    elif self.target_window_hwnd and win32gui.IsWindow(self.target_window_hwnd):
                        hwnd = self.target_window_hwnd
                    if hwnd:
                        if not self._claim_target_window(hwnd, seen_pid):
                            time.sleep(1.0)
                            continue
                        seen_hwnd = int(hwnd or 0)
                        seen_pid = int(self.target_process_id or seen_pid or 0)
                        if self.mode != "live":
                            if self.user_revealed_target:
                                # User explicitly revealed via UI — keep it visible
                                self.browser_offscreen = False
                                self._restore_target_window_for_user(hwnd, activate=False)
                            else:
                                # Only re-stash if window is NOT on virtual display
                                if not jarvis_display_manager.contains_hwnd(hwnd):
                                    self._stealth_target_window(hwnd)
                    # v1.0.5: Reduced polling to prevent jitter
                    p_start = getattr(self, "_sentry_start_at", 0) or time.time()
                    
                    if not getattr(self, "_sentry_start_at", 0): self._sentry_start_at = p_start
                    
                    if time.time() - p_start < 5.0:
                        time.sleep(1.0)
                    else:
                        time.sleep(2.0)
            finally:
                self._stealth_sentry_running = False
        threading.Thread(target=sentry, daemon=True).start()

    async def _call_vision_model_async(self, image_b64: str, extra_context: str = ""):
        import httpx
        url = "http://127.0.0.1:11434/api/generate"
        model = self.vision_model_override or os.environ.get("SKEMI_MODEL_VISION", "moondream:latest")
        if model in _VISION_MODEL_MISSING:
            return f"Error: vision model '{model}' chưa được cài (ollama pull {model})"
        prompt = f"{PROMPT_SYSTEM_VISION}\n\nUser command: {self.command}"
        if str(extra_context or "").strip():
            prompt += f"\n\nAuthoritative structured context:\n{extra_context.strip()}\n"
        
        # GLOBAL CONCURRENCY LOCK: Serializes all Ollama calls across all sessions
        async with GLOBAL_VISION_SEMAPHORE:
            for attempt in range(6):
                try:
                    payload = {"model": model, "prompt": prompt, "stream": False, "images": [image_b64]}
                    async with httpx.AsyncClient(timeout=80.0) as client:
                        r = await client.post(url, json=payload)
                        if r.status_code == 429:
                            self._is_rate_limited = True
                            
                            # Fallback to local model if cloud fails too many times
                            if attempt >= 3 and "cloud" in model.lower() and not self.vision_model_override:
                                _phantom_debug("[HARDENING] Cloud 429 too frequent. Switching to Local Moondream fallback.")
                                self.vision_model_override = "moondream:latest"
                                model = self.vision_model_override
                            
                            wait_sec = (attempt + 1) * 3
                            self.last_ai_action_desc = f"Wait turn ({attempt+1}/6)..."
                            await asyncio.sleep(wait_sec)
                            continue
                        
                        if r.status_code == 404:
                            _VISION_MODEL_MISSING.add(model)
                            return f"Error: vision model '{model}' chưa được cài (ollama pull {model})"
                        self._is_rate_limited = False
                        return r.json().get("response", "")
                except Exception as e:
                    if attempt == 5: return f"Error: {e}"
                    await asyncio.sleep(2)
        return ""

    async def _step_loop_task(self):
        # Streaming is handled by run_session's single capture loop. Starting a
        # second capture worker made the user's cursor/rendering visibly stutter.
        if self.preview_only:
            self.runtime_state = "preview"
            self.route = "preview"
            if self.mode == "live":
                self.last_ai_action_desc = "Live Control: showing your current desktop."
            else:
                status = self._refresh_jarvis_display_status(force=False)
                if status.get("workspace_ready"):
                    self.last_ai_action_desc = self._phantom_desktop_status_text()
                else:
                    self.last_ai_action_desc = str(status.get("last_launch_error") or "Phantom Desktop is not ready.")
            while self.preview_only and not self.cancelled and not self.agent_stopped and not self.session_closed:
                await asyncio.sleep(0.25)
            if self.cancelled or self.agent_stopped or self.session_closed:
                return
        try:
            self.runtime_state = "launching"
            _set_ai_control_active(False)
            first_frame_deadline = time.time() + 6.0
            while (
                not self.latest_live_b64
                and time.time() < first_frame_deadline
                and not self.cancelled
                and not self.agent_stopped
                and not self.session_closed
            ):
                await asyncio.sleep(0.1)
            if self.latest_live_b64:
                _set_ai_control_active(True)
            await asyncio.sleep(0.2)
            
            if self.mode == "phantom":
                launched = True
                self.target_window_hwnd = 0
                self.last_ai_action_desc = "Observing Phantom Desktop..."
            elif self.mode == "live":
                # Live Control works on whatever is already open on the user's real
                # desktop. We do NOT auto-launch an app (that would be wrong when the
                # user just wants the AI to operate the current screen). The AI can
                # still open apps itself via ghost-clicks (Start menu / taskbar).
                launched = True
                self.target_window_hwnd = 0
                self.last_ai_action_desc = "Live Control: reading your screen..."
            else:
                launched = await self._run_sync(self._proactive_launch_sync, self.command)
            
            # If multi-tasks were generated, execute the sequence
            if self.mode != "phantom" and launched and len(self.tasks) > 1:
                launched = await self._run_sync(self._launch_plan_tasks_sync)
                # If these are purely launch actions, we can stop here or continue to interaction
                launch_actions = {"open", "launch", "start", "mở", "bật"}
                if launched and all(str(task.get("action") or "").strip().lower() in launch_actions for task in self.tasks):
                    # Check if the LAST task was a web/search task that requires interaction
                    last_goal = str(self.tasks[-1].get("goal") or "").lower()
                    if not any(kw in last_goal for kw in ["youtube", "google", "search", "tìm", "nghe"]):
                        self.runtime_state = "done"
                        self.last_result = self._task_result_summary() or self._human_result("Task completed.", state="done")
                        self.last_ai_action_desc = self.last_result
                        return
            
            # v1.0.8: If launch failed but a window is already locked, just continue (fixes 'Skip Ad' etc)
            if not launched and self.mode != "phantom":
                existing_hwnd = await self._run_sync(self._resolve_window_handle_sync)
                if existing_hwnd:
                    if self.mode == "phantom":
                        launched = await self._run_sync(self._stealth_target_window, existing_hwnd)
                    else:
                        launched = True
                    if launched:
                        self._bind_target_window(existing_hwnd)

            if not launched:
                self.runtime_state = "error"
                self.session_error = "Không thể mở ứng dụng hoặc trình duyệt yêu cầu."
                self.last_ai_action_desc = self.session_error
                self.last_result = self._human_result(self.session_error, state="error")
                return
            self.runtime_state = "hidden_ready" if self.mode != "live" else "working"
            self.last_ai_action_desc = "Đang phân tích giao diện..." if self.source == "voice" else "Analyzing interface..."
            if not await self._await_confirmation_if_needed():
                return
            # v1.0.1: Always continue interacting after launch. No keyword checks.
            idle_cycles = 0
            max_action_steps = 80
            max_idle_cycles = 60
            while not self.cancelled and not self.agent_stopped:
                # Prevent processing while a launch is in progress to stop spam
                if getattr(self, "_is_launching", False):
                    await asyncio.sleep(1.0)
                    continue

                self.runtime_state = "working"
                hwnd = await self._run_sync(self._resolve_window_handle_sync)
                if hwnd:
                    self._bind_target_window(hwnd)
                    # v1.0.6 Smart Restore: If user clicks the taskbar icon, restore automatically
                    if self.mode == "phantom" and not self.user_revealed_target:
                        fg = win32gui.GetForegroundWindow()
                        is_our_window = (fg == hwnd)
                        if not is_our_window and fg:
                            with contextlib.suppress(Exception):
                                _, fg_pid = win32process.GetWindowThreadProcessId(fg)
                                if fg_pid == self.target_process_id:
                                    is_our_window = True
                        
                        if is_our_window:
                            self.last_ai_action_desc = "Skemi: Đã khôi phục cửa sổ theo yêu cầu."
                            self._restore_target_window_for_user(hwnd, activate=True)
                            self.user_revealed_target = True

                    # v1.0.9: Auto Skip Ad Reflex
                    self._reflex_auto_skip_ad_sync()
                elif self.mode not in {"live", "phantom"}:
                    # v1.1.70: Anti-Spam Launch Protection
                    now = time.time()
                    last_launch = getattr(self, "_last_proactive_launch_at", 0.0)
                    if now - last_launch < 15.0:
                        # Be patient. App might be starting.
                        self.last_ai_action_desc = "Waiting for window to initialize..."
                        await asyncio.sleep(2.0)
                        continue

                    self.last_ai_action_desc = "Target window lost. Attempting recovery..."
                    # Only speak once every 60 seconds about window loss
                    last_speak = getattr(self, "_last_window_lost_speak_at", 0.0)
                    if now - last_speak > 60.0:
                        self.speak("I noticed the target window is missing. Let me try to reopen it for you.")
                        self._last_window_lost_speak_at = now

                    self._last_proactive_launch_at = now
                    launched = await self._run_sync(self._proactive_launch_sync, self.command)
                    if not launched:
                        self.runtime_state = "error"
                        self.last_ai_action_desc = "Could not recover the target window."
                        return
                    
                    # Wait a bit longer after launch for the window to actually appear
                    await asyncio.sleep(3.0)
                    continue

                self.is_thinking = True
                self.last_ai_action_desc = "Đang quan sát màn hình..." if self.source == "voice" else "Observing screen..."
                img_b64 = await self._capture_screen_async(force=True)
                web_context = ""
                if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
                    web_context = await self._build_web_context_async()
                elif hwnd:
                    native_context = await self._run_sync(self._uia_context_sync)
                    if native_context:
                        web_context = native_context
                self.last_ai_action_desc = "Đang suy nghĩ hành động tiếp theo..." if self.source == "voice" else "Thinking of next step..."
                resp = await self._call_vision_model_async(img_b64, extra_context=web_context)
                
                # Reset thinking flag after model returns
                self.is_thinking = False

                try:
                    # Robust JSON extraction (Moondream fix)
                    json_str = ""
                    match = re.search(r'\{.*\}', resp, re.DOTALL)
                    if match:
                        json_str = match.group(0)
                        try:
                            data = json.loads(json_str)
                        except json.JSONDecodeError:
                            # Emergency regex extraction for Moondream's broken JSON
                            data = {
                                "thought": (re.search(r'"thought":\s*"([^"]*)"', json_str) or re.search(r'thought:\s*([^,\n}]*)', json_str)).group(1) if "thought" in json_str else "Healing JSON...",
                                "action": (re.search(r'"action":\s*"([^"]*)"', json_str) or re.search(r'action:\s*([^,\n}]*)', json_str)).group(1) if "action" in json_str else "observe",
                                "description": (re.search(r'"description":\s*"([^"]*)"', json_str) or re.search(r'description:\s*([^,\n}]*)', json_str)).group(1) if "description" in json_str else "Processing..."
                            }
                            # Extract coordinates
                            x_m = re.search(r'"x":\s*(\d+)', json_str)
                            y_m = re.search(r'"y":\s*(\d+)', json_str)
                            t_m = re.search(r'"text":\s*"([^"]*)"', json_str)
                            k_m = re.search(r'"key":\s*"([^"]*)"', json_str)
                            data["params"] = {
                                "x": x_m.group(1) if x_m else 500,
                                "y": y_m.group(1) if y_m else 500,
                                "text": t_m.group(1) if t_m else "",
                                "key": k_m.group(1) if k_m else ""
                            }

                        action_executed = False
                        action = str(data.get("action", "observe")).lower()
                        self.last_model_thought = str(data.get("thought", "") or "").strip()
                        p = data.get("params") or {}
                        if not isinstance(p, dict):
                            p = {}
                        if "x" not in p and data.get("x_pct") is not None:
                            with contextlib.suppress(Exception):
                                p["x"] = int(max(0.0, min(1.0, float(data.get("x_pct")))) * 1000)
                        if "y" not in p and data.get("y_pct") is not None:
                            with contextlib.suppress(Exception):
                                p["y"] = int(max(0.0, min(1.0, float(data.get("y_pct")))) * 1000)
                        for key in ("text", "key", "direction", "amount"):
                            if key not in p and data.get(key) is not None:
                                p[key] = data.get(key)
                        if action == "scroll" and "amount" not in p:
                            p["amount"] = 120 if str(p.get("direction") or "").lower() == "up" else -120
                        raw_desc = str(data.get("description", "Thinking...") or "Thinking...")
                        
                        # v1.1.2: Active status feedback
                        action = str(data.get("action", "observe")).lower()
                        if action == "observe" or action == "wait":
                            self.last_ai_action_desc = "Đang kiểm tra kết quả..." if self.source == "voice" else "Checking results..."
                        else:
                            self.last_ai_action_desc = raw_desc

                        def parse_coord(v):
                            try:
                                return int(float(str(v)))
                            except Exception:
                                return 500

                        final_x, final_y = parse_coord(p.get("x")), parse_coord(p.get("y"))
                        hwnd = self.target_window_hwnd
                        use_web_surface = bool(self.web_surface is not None and getattr(self.web_surface, "is_connected", False))
                        self.automation_mode = "web_semantic" if use_web_surface else "vision_fallback"
                        if (not hwnd or not win32gui.IsWindow(hwnd)) and action in {"click", "double_click", "right_click", "type", "key", "hover", "scroll"}:
                            if not use_web_surface and self.mode != "phantom" and self.mode != "live":
                                self.last_ai_action_desc = "Waiting to lock onto the target window..."
                                idle_cycles += 1
                                self.is_thinking = False
                                await asyncio.sleep(0.4)
                                continue
                        if action in {"click", "double_click", "right_click"}:
                            self.action_overlay = {"type": "click", "x": final_x, "y": final_y, "ts": time.time()}
                            handled = False
                            if use_web_surface:
                                handled = await self._execute_web_action_async("click", {"x": final_x, "y": final_y})
                            elif self.mode == "phantom":
                                handled = await self._run_sync(self._execute_phantom_desktop_action_sync, action, p)
                            elif self.mode == "live":
                                handled = await self._run_sync(self._live_ghost_action_sync, action, {"x": final_x, "y": final_y})
                            elif await self._run_sync(self._execute_native_uia_action_sync, "click", p):
                                handled = True
                            if not handled:
                                if self.mode == "phantom":
                                    self.last_ai_action_desc = "Waiting for the Phantom desktop to accept the click..."
                                    await asyncio.sleep(0.4)
                                    continue
                                if self.mode != "live":
                                    self.automation_mode = "vision_fallback"
                                    await self._run_sync(self._run_action_on_target_desktop_sync, manual_click, final_x, final_y, hwnd)
                            action_executed = True
                        elif action == "type":
                            typed_preview = str(p.get("text", "") or "")
                            self.action_overlay = {"type": "type", "x": final_x, "y": final_y, "text": typed_preview[:32], "ts": time.time()}
                            handled = False
                            if use_web_surface:
                                handled = await self._execute_web_action_async(
                                    "type",
                                    {"x": final_x, "y": final_y, "text": p.get("text", ""), "submit": bool(p.get("submit", False))},
                                )
                            elif self.mode == "phantom":
                                handled = await self._run_sync(self._execute_phantom_desktop_action_sync, "type", p)
                            elif self.mode == "live":
                                handled = await self._run_sync(self._live_ghost_action_sync, "type", {"text": p.get("text", ""), "submit": bool(p.get("submit", False))})
                            elif await self._run_sync(self._execute_native_uia_action_sync, "type", p):
                                handled = True
                            if not handled:
                                if self.mode == "phantom":
                                    self.last_ai_action_desc = "Waiting for the Phantom desktop to accept typing..."
                                    await asyncio.sleep(0.4)
                                    continue
                                if self.mode != "live":
                                    self.automation_mode = "vision_fallback"
                                    await self._run_sync(self._run_action_on_target_desktop_sync, manual_type, p.get("text", ""), hwnd)
                            action_executed = True
                        elif action == "key":
                            self.action_overlay = {"type": "key", "x": final_x, "y": final_y, "text": str(p.get("key", "enter")), "ts": time.time()}
                            handled = False
                            if use_web_surface:
                                handled = await self._execute_web_action_async("key", {"key": p.get("key", "enter")})
                            elif self.mode == "phantom":
                                handled = await self._run_sync(self._execute_phantom_desktop_action_sync, "key", p)
                            elif self.mode == "live":
                                handled = await self._run_sync(self._live_ghost_action_sync, "key", {"key": p.get("key", "enter")})
                            elif await self._run_sync(self._execute_native_uia_action_sync, "key", p):
                                handled = True
                            if not handled:
                                if self.mode == "phantom":
                                    self.last_ai_action_desc = "Waiting for the Phantom desktop to accept the key..."
                                    await asyncio.sleep(0.4)
                                    continue
                                if self.mode != "live":
                                    self.automation_mode = "vision_fallback"
                                    await self._run_sync(self._run_action_on_target_desktop_sync, manual_press, p.get("key", "enter"), hwnd)
                            action_executed = True
                        elif action == "scroll":
                            amount = p.get("amount")
                            try:
                                amount = int(float(str(amount)))
                            except Exception:
                                amount = -120
                            handled = False
                            if use_web_surface:
                                handled = await self._execute_web_action_async("scroll", {"amount": amount})
                            elif self.mode == "phantom":
                                handled = await self._run_sync(self._execute_phantom_desktop_action_sync, "scroll", {**p, "amount": amount})
                            elif self.mode == "live":
                                handled = await self._run_sync(self._live_ghost_action_sync, "scroll", {"x": final_x, "y": final_y, "amount": amount})
                            if not handled:
                                if self.mode == "phantom":
                                    self.last_ai_action_desc = "Waiting for the Phantom desktop to accept scrolling..."
                                    await asyncio.sleep(0.4)
                                    continue
                                if self.mode != "live":
                                    await self._run_sync(self._run_action_on_target_desktop_sync, manual_scroll, amount, hwnd)
                            action_executed = True
                        elif action == "wait":
                            pause_for = p.get("seconds", 1.0)
                            try:
                                pause_for = max(0.2, min(float(str(pause_for)), 3.0))
                            except Exception:
                                pause_for = 1.0
                            await asyncio.sleep(pause_for)
                            action_executed = True
                        elif action == "hover":
                            self.last_ai_action_desc = data.get("description", "Holding pointer position...")
                        elif action == "done":
                            self._remember_action(self.last_ai_action_desc)
                            self.last_result = self._human_result(data.get("description", "Task completed."), state="done")
                            self.last_ai_action_desc = self.last_result
                            
                            # v1.0.9: Skemi stays in the window. Wait for next command or cancellation.
                            self.runtime_state = "done"
                            old_cmd = self.command
                            while not self.cancelled and not self.agent_stopped and self.command == old_cmd:
                                # Continue reflex actions (Skip Ad) even while idle
                                self._reflex_auto_skip_ad_sync()
                                await asyncio.sleep(1)
                            
                            if not self.cancelled and not self.agent_stopped:
                                # New command arrived!
                                self.step_count = 0
                                idle_cycles = 0
                                continue 
                            
                            action_executed = True
                        else:
                            self.last_ai_action_desc = "Looking for the next safe step..."

                        if action_executed and action != "done":
                            self.step_count += 1
                            idle_cycles = 0
                            self._remember_action(self.last_ai_action_desc)
                            self.last_ai_action_desc = f"Step {self.step_count}: {self.last_ai_action_desc}"
                            if self.step_count >= max_action_steps:
                                self.runtime_state = "stopped"
                                self.last_ai_action_desc = self._human_result(
                                    "Stopped after reaching the safety step limit.",
                                    state="step_limit",
                                )
                                self.last_result = self.last_ai_action_desc
                                break
                        elif action == "done":
                            idle_cycles = 0
                        else:
                            idle_cycles += 1
                    else:
                        self.last_ai_action_desc = "Looking for the next safe step..."
                        idle_cycles += 1
                except Exception as e:
                    _phantom_debug(f"[LOOP ERROR] {e}")
                    idle_cycles += 1
                if idle_cycles >= max_idle_cycles:
                    self.runtime_state = "stopped"
                    self.last_ai_action_desc = self._human_result(
                        "Stopped after too many observation-only cycles without a clear actionable screen.",
                        state="idle_limit",
                    )
                    self.last_result = self.last_ai_action_desc
                    break
                self.is_thinking = False
                await asyncio.sleep(0.2 if self.web_surface is not None and getattr(self.web_surface, "is_connected", False) else 0.4)
        except Exception as e:
            self.runtime_state = "error"
            self.session_error = str(e)
            self.last_ai_action_desc = f"Desktop agent failed: {e}"
            self.last_result = self._human_result(self.last_ai_action_desc, state="error")
        finally:
            self.is_thinking = False
            if self.cancelled and self.runtime_state != "error":
                self.runtime_state = "stopped"
                self.last_result = self.last_result or self._human_result("Task stopped.", state="stopped")
            elif self.runtime_state not in {"error", "stopped"}:
                self.runtime_state = "done"
                self.last_result = self.last_result or self._human_result(self.last_ai_action_desc or "Task completed.", state="done")
            self.agent_stopped = True

    def _resolve_window_handle_sync(self) -> int:
        if self.target_window_hwnd and win32gui.IsWindow(self.target_window_hwnd):
            return int(self.target_window_hwnd)
        if self.target_process_id:
            hwnd = _find_window_for_pid(
                self.target_process_id,
                prefer_tokens=[self.target_window_title, self.command],
                include_hidden=self.mode != "live",
                desktop_handle=self._desktop_search_handle(),
            )
            if hwnd:
                self._bind_target_window(hwnd, self.target_process_id)
                return int(hwnd)

        def cb(h, res):
            if win32gui.IsWindowVisible(h): 
                t = win32gui.GetWindowText(h)
                if t: res.append((h, t.lower()))
        
        wins = []
        # v51.0: Cross-Desktop Discovery
        desktop_handle = self._desktop_search_handle()
        if desktop_handle:
            win32gui.EnumDesktopWindows(desktop_handle, cb, wins)
        else:
            win32gui.EnumWindows(cb, wins)
        
        # Use clean query logic for better window matching
        words = self.command.lower().split()
        stop_words = {"vao", "mo", "bat", "truy", "cap", "di", "toi", "hay", "giup", "tinh", "kiem", "tim", "app", "ung", "dung", "phan", "mem", "web", "trang"}
        filtered = [w for w in words if "".join(ch for ch in unicodedata.normalize("NFKD", w) if not unicodedata.combining(ch)) not in stop_words]
        launch_words = [_normalize_text(token) for token in self.launch_target_tokens if token]
        match_words = [word for word in launch_words if word] or filtered or words
        
        # Extra points for apps actually requested (e.g. "zalo", "discord", "chrome")
        best_h, best_s = 0, 0
        for h, t in wins:
            cls = _window_class_name(h)
            if _is_generic_window_identity(t, cls):
                continue
            # Score: Exact app matches vs generic words
            s = sum(5 if w in t else 0 for w in match_words)
            if s > 0:
                s += 1
            if s > best_s: best_s, best_h = s, h
        if best_h:
            self._bind_target_window(best_h)
        return best_h

    async def _continuous_capture_loop_final(self):
        """Post-task capture loop that keeps the stream alive after execution ends."""
        while not self.session_closed:
            try:
                await self._capture_screen_async(force=False)
            except Exception as e:
                _phantom_debug(f"[STREAM ERROR] {e}")
            await asyncio.sleep(0.75)

    async def run_session(self):
        global _target_desktop_index
        self._loop = asyncio.get_running_loop()
        if self.mode == "phantom":
            _set_ai_control_active(False)
        
        # Legacy desktop_index is kept only as a session marker; Jarvis never
        # switches or captures Windows Task View desktops.
        if self.mode == "phantom":
            if self.desktop_index >= 0:
                _target_desktop_index = self.desktop_index
                # v1.2.2: AI context is now isolated; do not force a physical switch for the user
                # activate_virtual_desktop_index(self.desktop_index)
                pass
            else:
                _target_desktop_index = -1
            status = self._refresh_jarvis_display_status(force=False)
            if status.get("workspace_ready"):
                _phantom_debug(f"[PHANTOM] Phantom lock active on {status.get('display_id')} ({status.get('display_bounds', {}).get('width')}x{status.get('display_bounds', {}).get('height')})")
            else:
                _phantom_debug(f"[PHANTOM] ERROR: Virtual display not ready - {status.get('last_launch_error')}")

        # v1.0.0: Start dedicated phantom capture thread if in super mode
        if self.mode == "super" and self.h_phantom_desk:
            self._start_phantom_capture_thread()
        try:
            self._capture_task = asyncio.create_task(self._continuous_capture_loop())
            self._execute_task = asyncio.create_task(self._step_loop_task())
            
            # v1.1.8: Target Loss Sensor (Cảm biến mất mục tiêu)
            # If we are in phantom mode, monitor if the target window is still in focus/valid
            if self.mode == "phantom":
                async def _target_loss_sensor():
                    while not self.agent_stopped:
                        await asyncio.sleep(5.0)
                        if self.target_window_hwnd and not win32gui.IsWindow(self.target_window_hwnd):
                            _phantom_debug("[SENSOR] Target window lost!")
                            self.last_ai_action_desc = "Cảnh báo: Mất mục tiêu! Cửa sổ ứng dụng đã bị đóng hoặc mất kết nối."
                            # Stop the session to avoid runaway actions
                            await self.stop_agent("Mất kết nối với ứng dụng mục tiêu.")
                            break
                asyncio.create_task(_target_loss_sensor())
                
            await self._execute_task
            # Switch to post-task capture loop
            if self._capture_task and not self._capture_task.done():
                self._capture_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._capture_task
            self._capture_task = asyncio.create_task(self._continuous_capture_loop_final())
            while not self.session_closed:
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            self.cancelled = True
            self.runtime_state = "stopped"
            self.last_ai_action_desc = "Task cancelled."
            self.last_result = self.last_ai_action_desc
        except Exception as e:
            self.runtime_state = "error"
            self.session_error = str(e)
            self.last_ai_action_desc = f"Desktop runtime crashed: {e}"
            self.last_result = self.last_ai_action_desc
        finally:
            self.session_closed = True
            self.agent_stopped = True
            active_sessions.pop(self.session_id, None)
            if not any(getattr(s, 'mode', '') == 'phantom' for s in active_sessions.values()):
                with _input_shield_lock:
                    global PHYSICAL_INPUT_LOCKED, is_isolated, AI_CONTROL_ACTIVE
                    PHYSICAL_INPUT_LOCKED = False
                    is_isolated = False
                    AI_CONTROL_ACTIVE = False # v7.0: Restore physical input safety
            # Stop phantom capture thread
            self._stop_phantom_capture_thread()
            if self._capture_task and not self._capture_task.done():
                self._capture_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._capture_task
            if self.web_surface is not None and getattr(self.web_surface, "is_connected", False):
                with contextlib.suppress(Exception):
                    await self.web_surface.disconnect()
            self.browser_offscreen = False

    def _reflex_auto_skip_ad_sync(self):
        """Skemi background reflex: Always click Skip Ad if visible."""
        # Only for web sessions with active CDP
        if not self.web_surface or not getattr(self.web_surface, "is_connected", False):
            return
        
        # Try common selectors for Skip Ad buttons
        # We do this every few cycles to avoid overhead
        if self.step_count % 3 != 0:
            return
            
        async def _do_reflex():
            selectors = [".ytp-ad-skip-button-modern", ".ytp-ad-skip-button", ".ytp-ad-skip-button-text"]
            for sel in selectors:
                with contextlib.suppress(Exception):
                    # Check if exists and click
                    await self._execute_web_action_async("click", {"selector": sel})
                    self.last_ai_action_desc = "Skemi: Tự động bỏ qua quảng cáo cho bạn."
                    break

        asyncio.create_task(_do_reflex())

# ── Entry ──────────────────────────────────────────────────────────────

async def run_desktop_agent(command: str, mode: str = "live", bypass_safety: bool = True, plan: Optional[Dict[str, Any]] = None, source: str = "manual", desktop_index: int = -1) -> Tuple[str, AsyncGenerator[str, None]]:

    # v1.0.9: Contextual Continuity - Reuse session if it's for the same goal/context
    existing_session_id = str(plan.get("reuse_session_id") or "").strip()
    if existing_session_id and existing_session_id in active_sessions:
        session = active_sessions[existing_session_id]
        if not session.agent_stopped:
            session.command = command
            session.plan = dict(plan or {})
            session.route = str(session.plan.get("route") or "computer_task")
            session.tasks = session._normalize_plan_tasks(plan, command)
            session.current_task_index = 0 if session.tasks else -1
            session.preview_only = bool(session.plan.get("preview_only", False))
            session.last_result = ""
            session.session_error = ""
            session.cancelled = False
            session.runtime_state = "launching" # Trigger re-init
            return existing_session_id, None # Backend should handle reconnection
            
    session_id = uuid.uuid4().hex[:8]
    session = DesktopAgentSession(session_id, command, mode, bypass_safety=bypass_safety, plan=plan, source=source, desktop_index=desktop_index)

    active_sessions[session_id] = session
    async def events():
        session_task = None
        try:
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'route': session.route, 'tasks': session.tasks, 'current_task_index': session.current_task_index}, ensure_ascii=False)}\n\n"
            session_task = asyncio.create_task(session.run_session())
            last_status_signature = None
            last_frame_version = -1
            last_telemetry_signature = None
            last_confirmation_signature = None
            final_sent = False
            while True:
                await asyncio.sleep(0.25)
                if session.frame_version != last_frame_version and session.latest_live_b64:
                    last_frame_version = int(session.frame_version or 0)
                    screenshot_payload = {
                        "type": "screenshot",
                        "session_id": session_id,
                        "image": session.latest_live_b64,
                        "frame_version": last_frame_version,
                        "description": session.last_ai_action_desc,
                        "url": str(session.current_url or ""),
                        "title": str(session._current_surface_label()),
                    }
                    yield f"data: {json.dumps(screenshot_payload, ensure_ascii=False)}\n\n"
                telemetry_payload = {
                    "type": "telemetry",
                    "session_id": session_id,
                    "route": session.route,
                    "tasks": session.tasks,
                    "current_task_index": int(session.current_task_index),
                    "surface_mode": session.mode,
                    "target_window_hwnd": int(session.target_window_hwnd or 0),
                    "target_window_title": str(session._current_surface_label()),
                    "target_window_class": str(session.target_window_class or ""),
                }
                if session.mode == "phantom":
                    telemetry_payload.update(session._refresh_jarvis_display_status(force=False))
                telemetry_signature = json.dumps(telemetry_payload, ensure_ascii=False, sort_keys=True)
                if telemetry_signature != last_telemetry_signature:
                    last_telemetry_signature = telemetry_signature
                    yield f"data: {json.dumps(telemetry_payload, ensure_ascii=False)}\n\n"
                confirmation_payload = dict(session.pending_confirmation or {})
                confirmation_signature = json.dumps(confirmation_payload, ensure_ascii=False, sort_keys=True)
                if confirmation_payload and confirmation_signature != last_confirmation_signature:
                    last_confirmation_signature = confirmation_signature
                    yield f"data: {json.dumps(confirmation_payload, ensure_ascii=False)}\n\n"
                payload = {
                    "type": "status",
                    "state": session.runtime_state,
                    "task_state": session._task_state(),
                    "stream_state": session._stream_state(),
                    "route": session.route,
                    "tasks": session.tasks,
                    "current_task_index": int(session.current_task_index),
                    "surface_mode": session.mode,
                    "message": session.last_ai_action_desc,
                    "status_text": session.last_ai_action_desc,
                    "final_result": session.last_result,
                    "is_thinking": session.is_thinking,
                    "step_count": session.step_count,
                    "target_window_title": session._current_surface_label(),
                    "execution_surface": "browser_hidden" if (session.web_surface is not None and getattr(session.web_surface, "is_connected", False) and session.mode != "live") else ("app_hidden" if session.mode != "live" else "visible_live"),
                    "automation_mode": session.automation_mode,
                    "requires_consent": bool(session.pending_confirmation),
                    "consent_reason": str(session.consent_reason or ""),
                    "pending_confirmation": dict(session.pending_confirmation or {}),
                    "pending_manual_takeover": {},
                    "target_window_hwnd": int(session.target_window_hwnd or 0),
                    "target_window_title": str(session._current_surface_label()),
                    "target_window_class": str(session.target_window_class or ""),
                    "frame_version": int(session.frame_version or 0),
                    "workspace_kind": str(session.workspace_kind),
                    "workspace_ready": bool(session.workspace_ready),
                    "setup_state": str(session.jarvis_display_status.get("setup_state") or ""),
                    "driver_status": str(session.jarvis_display_status.get("driver_status") or ""),
                    "driver_version": str(session.jarvis_display_status.get("driver_version") or ""),
                    "driver_provider": str(session.jarvis_display_status.get("driver_provider") or ""),
                    "bootstrap_required": bool(session.jarvis_display_status.get("bootstrap_required", False)),
                    "bootstrap_url": str(session.jarvis_display_status.get("bootstrap_url") or PHANTOM_BOOTSTRAP_URL),
                    "display_id": str(session.jarvis_display_status.get("display_id") or ""),
                    "display_role": str(session.jarvis_display_status.get("display_role") or ""),
                    "isolation_level": str(session.jarvis_display_status.get("isolation_level") or ""),
                    "display_bounds": dict(session.jarvis_display_status.get("display_bounds") or {}),
                    "last_launch_error": str(session.last_launch_error or session.jarvis_display_status.get("last_launch_error") or ""),
                    "last_launch_error_code": str(session.last_launch_error_code or session.jarvis_display_status.get("last_launch_error_code") or ""),
                    "update_state": str(session.jarvis_display_status.get("update_state") or "current"),
                    "update_available": bool(session.jarvis_display_status.get("update_available", False)),
                    "update_required": bool(session.jarvis_display_status.get("update_required", False)),
                    "latest_companion_version": str(session.jarvis_display_status.get("latest_companion_version") or ""),
                    "latest_driver_version": str(session.jarvis_display_status.get("latest_driver_version") or ""),
                    "update_url": str(session.jarvis_display_status.get("update_url") or PHANTOM_UPDATE_URL),
                    "update_size_mb": str(session.jarvis_display_status.get("update_size_mb") or ""),
                    "update_requires_admin": bool(session.jarvis_display_status.get("update_requires_admin", True)),
                    "update_message": str(session.jarvis_display_status.get("update_message") or ""),
                    "cursor_overlay": dict(session.action_overlay or {}),
                    "surface_metrics": {
                        "capture_width": int(session.capture_w or 0),
                        "capture_height": int(session.capture_h or 0),
                    },
                }
                if session.mode == "phantom":
                    payload.update(session._refresh_jarvis_display_status(force=False))
                    payload["last_launch_error"] = str(session.last_launch_error or payload.get("last_launch_error") or "")
                    payload["last_launch_error_code"] = str(session.last_launch_error_code or payload.get("last_launch_error_code") or "")
                    payload["cursor_overlay"] = dict(session.action_overlay or {})
                signature = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                if signature != last_status_signature:
                    last_status_signature = signature
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if not final_sent and session.agent_stopped and session.runtime_state in {"done", "stopped", "error"}:
                    final_sent = True
                    final_type = "error" if session.runtime_state == "error" else ("stopped" if session.runtime_state == "stopped" else "done")
                    final_payload = {
                        "type": final_type,
                        "state": session.runtime_state,
                        "task_state": session._task_state(),
                        "stream_state": session._stream_state(),
                        "route": session.route,
                        "tasks": session.tasks,
                        "current_task_index": int(session.current_task_index),
                        "surface_mode": session.mode,
                        "description": session.last_result or session.last_ai_action_desc,
                        "result": session.last_result or session.last_ai_action_desc,
                        "final_result": session.last_result or session.last_ai_action_desc,
                        "message": session.session_error or session.last_ai_action_desc,
                        "session_id": session_id,
                        "image": session.latest_live_b64,
                        "frame_version": int(session.frame_version or 0),
                        "url": str(session.current_url or ""),
                        "title": str(session._current_surface_label()),
                        "target_window_hwnd": int(session.target_window_hwnd or 0),
                        "target_window_title": str(session._current_surface_label()),
                        "target_window_class": str(session.target_window_class or ""),
                        "execution_surface": "browser_hidden" if (session.web_surface is not None and getattr(session.web_surface, "is_connected", False) and session.mode != "live") else ("app_hidden" if session.mode != "live" else "visible_live"),
                        "automation_mode": session.automation_mode,
                        "workspace_kind": str(session.workspace_kind),
                        "workspace_ready": bool(session.workspace_ready),
                        "setup_state": str(session.jarvis_display_status.get("setup_state") or ""),
                        "driver_status": str(session.jarvis_display_status.get("driver_status") or ""),
                        "driver_version": str(session.jarvis_display_status.get("driver_version") or ""),
                        "driver_provider": str(session.jarvis_display_status.get("driver_provider") or ""),
                        "bootstrap_required": bool(session.jarvis_display_status.get("bootstrap_required", False)),
                        "bootstrap_url": str(session.jarvis_display_status.get("bootstrap_url") or PHANTOM_BOOTSTRAP_URL),
                        "display_id": str(session.jarvis_display_status.get("display_id") or ""),
                        "display_role": str(session.jarvis_display_status.get("display_role") or ""),
                        "isolation_level": str(session.jarvis_display_status.get("isolation_level") or ""),
                        "display_bounds": dict(session.jarvis_display_status.get("display_bounds") or {}),
                        "last_launch_error": str(session.last_launch_error or session.jarvis_display_status.get("last_launch_error") or ""),
                        "last_launch_error_code": str(session.last_launch_error_code or session.jarvis_display_status.get("last_launch_error_code") or ""),
                        "update_state": str(session.jarvis_display_status.get("update_state") or "current"),
                        "update_available": bool(session.jarvis_display_status.get("update_available", False)),
                        "update_required": bool(session.jarvis_display_status.get("update_required", False)),
                        "latest_companion_version": str(session.jarvis_display_status.get("latest_companion_version") or ""),
                        "latest_driver_version": str(session.jarvis_display_status.get("latest_driver_version") or ""),
                        "update_url": str(session.jarvis_display_status.get("update_url") or PHANTOM_UPDATE_URL),
                        "update_size_mb": str(session.jarvis_display_status.get("update_size_mb") or ""),
                        "update_requires_admin": bool(session.jarvis_display_status.get("update_requires_admin", True)),
                        "update_message": str(session.jarvis_display_status.get("update_message") or ""),
                        "cursor_overlay": dict(session.action_overlay or {}),
                        "surface_metrics": {
                            "capture_width": int(session.capture_w or 0),
                            "capture_height": int(session.capture_h or 0),
                        },
                    }
                    yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"
                if session.session_closed:
                    break
        finally:
            if session_task and not session_task.done():
                session_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await session_task
            active_sessions.pop(session_id, None)
    return session_id, events()

def stop_session(session_id: str) -> bool:
    s = active_sessions.get(session_id)
    if s:
        if s._confirmation_future is not None and not s._confirmation_future.done():
            s._confirmation_future.set_result(False)
        s.cancelled = True
        s.runtime_state = "stopping"
        s.last_ai_action_desc = "Stopping the current task..."
        s.last_active_at = time.time()
        return True
    return False


def close_session(session_id: str) -> bool:
    s = active_sessions.get(session_id)
    if not s:
        return False
    if s._confirmation_future is not None and not s._confirmation_future.done():
        s._confirmation_future.set_result(False)
    s.cancelled = True
    s.agent_stopped = True
    s.session_closed = True
    if s._execute_task and not s._execute_task.done():
        s._execute_task.cancel()
    return True


def register(app: FastAPI) -> None:
    """Register desktop agent routes with the main FastAPI app"""
    # Phantom mode WebRTC endpoints
    @app.post("/api/phantom/webrtc/offer")
    async def webrtc_offer(params: dict):
        return await webrtc_offer_impl(params)
    
    @app.post("/api/phantom/webrtc/stop")
    async def webrtc_stop():
        return await webrtc_stop_impl()
        
    # Other phantom endpoints
    @app.get("/api/phantom/check-driver")
    async def check_driver():
        return await check_driver_impl()
        
    @app.get("/api/phantom/list-desktops")
    async def list_desktops():
        return await list_desktops_impl()
        
    @app.post("/api/phantom/lock-desktop")
    async def lock_desktop(params: dict):
        return await lock_desktop_impl(params)
        
    @app.post("/api/phantom/start-stream")
    async def start_stream(params: dict):
        return await start_stream_impl(params)
        
    @app.post("/api/phantom/stop")
    async def phantom_stop(params: dict):
        return await phantom_stop_impl(params)

# Helper functions to maintain original signatures
async def webrtc_offer_impl(params: dict):
    return webrtc_offer(params)

async def webrtc_stop_impl():
    return webrtc_stop()

async def check_driver_impl():
    return check_driver()

async def list_desktops_impl():
    return list_desktops()

async def lock_desktop_impl(params: dict):
    return lock_desktop(params)

async def start_stream_impl(params: dict):
    return start_stream(params)

async def phantom_stop_impl(params: dict):
    return phantom_stop(params)
