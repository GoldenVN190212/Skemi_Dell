"""
Skemi Control Agent — Real-time Playwright Browser Automation
Launches a real Chromium browser, AI analyzes screenshots to decide actions,
streams results via SSE events.
"""

import asyncio
import ast
import base64
import contextlib
import ctypes
import hashlib
import json
import os
import random
import re
import time
import unicodedata
import uuid
from io import BytesIO
import desktop_agent
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from urllib.parse import quote, quote_plus, urlparse

# Playwright import (lazy load to avoid blocking server startup)
_playwright_module = None
_async_playwright = None
_browser_pyautogui = None
_browser_imagegrab = None
_browser_pil_image = None
_browser_win32gui = None
_browser_win32ui = None
_browser_win32con = None
_browser_user32 = None


def _ensure_browser_desktop():
    global _browser_pyautogui, _browser_imagegrab, _browser_pil_image
    if _browser_pyautogui is None:
        import pyautogui
        from PIL import Image, ImageGrab

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.02
        pyautogui.MINIMUM_DURATION = 0.02
        pyautogui.MINIMUM_SLEEP = 0.01

        _browser_pyautogui = pyautogui
        _browser_imagegrab = ImageGrab
        _browser_pil_image = Image
    return _browser_pyautogui, _browser_imagegrab


def _ensure_browser_win32():
    global _browser_win32gui
    if _browser_win32gui is None:
        import win32gui
        _browser_win32gui = win32gui
    return _browser_win32gui


def _ensure_browser_win32_modules():
    global _browser_win32gui, _browser_win32ui, _browser_win32con
    if _browser_win32gui is None or _browser_win32ui is None or _browser_win32con is None:
        import win32con
        import win32gui
        import win32ui

        _browser_win32gui = win32gui
        _browser_win32ui = win32ui
        _browser_win32con = win32con
    return _browser_win32gui, _browser_win32ui, _browser_win32con


def _ensure_browser_user32():
    global _browser_user32
    if _browser_user32 is None:
        _browser_user32 = ctypes.WinDLL("user32", use_last_error=True)
    return _browser_user32


def _ensure_playwright():
    global _playwright_module, _async_playwright
    if _playwright_module is None:
        from playwright.async_api import async_playwright
        _playwright_module = True
        _async_playwright = async_playwright
    return _async_playwright


def _default_host_browser_user_data_dir() -> str:
    override = str(os.getenv("SKEMI_BROWSER_USER_DATA_DIR", "") or "").strip()
    if override and os.path.isdir(override):
        return override
    if os.name != "nt":
        return ""
    local_app_data = os.getenv("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Google", "Chrome", "User Data"),
        os.path.join(local_app_data, "Microsoft", "Edge", "User Data"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return ""


def _native_input_safety_allows(reason: str = "native input") -> bool:
    try:
        guard = getattr(desktop_agent, "_physical_mouse_safety_allows", None)
        if callable(guard):
            return bool(guard(reason))
    except Exception:
        pass
    if str(os.getenv("SKEMI_MOUSE_SAFETY_LOCK", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
        return True
    try:
        pyautogui, _ = _ensure_browser_desktop()
        threshold = max(1, int(os.getenv("SKEMI_MOUSE_SAFETY_THRESHOLD_PX", "2")))
        timeout = max(0.5, float(os.getenv("SKEMI_MOUSE_SAFETY_TIMEOUT", "6")))
        quiet_for = max(0.08, float(os.getenv("SKEMI_MOUSE_SAFETY_QUIET_SECONDS", "0.28")))
        deadline = time.time() + timeout
        last = pyautogui.position()
        stable_since = time.time()
        while time.time() < deadline:
            time.sleep(0.045)
            current = pyautogui.position()
            if abs(current.x - last.x) > threshold or abs(current.y - last.y) > threshold:
                last = current
                stable_since = time.time()
                continue
            if time.time() - stable_since >= quiet_for:
                return True
        return False
    except Exception:
        return True


# ── Config ────────────────────────────────────────────────────────────

OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
TEXT_MODEL = os.getenv("SKEMI_MODEL_MAIN", "gpt-oss:120b-cloud")
MAX_STEPS = int(os.getenv("SKEMI_COMPUTER_MAX_STEPS", "90"))
STEP_TIMEOUT = float(os.getenv("SKEMI_COMPUTER_STEP_TIMEOUT", "30"))
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800
LIVE_CAPTURE_INTERVAL = float(os.getenv("SKEMI_COMPUTER_LIVE_CAPTURE_INTERVAL", "0.028"))
LIVE_CAPTURE_QUALITY = int(os.getenv("SKEMI_COMPUTER_LIVE_CAPTURE_QUALITY", "28"))
ANALYSIS_CAPTURE_QUALITY = int(os.getenv("SKEMI_COMPUTER_ANALYSIS_CAPTURE_QUALITY", "56"))
LIVE_CAPTURE_MAX_WIDTH = int(os.getenv("SKEMI_COMPUTER_LIVE_CAPTURE_MAX_WIDTH", "960"))
LIVE_CAPTURE_MAX_HEIGHT = int(os.getenv("SKEMI_COMPUTER_LIVE_CAPTURE_MAX_HEIGHT", "620"))
BROWSER_PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".skemi_browser")
BROWSER_STORAGE_STATE_PATH = os.path.join(BROWSER_PROFILE_DIR, "storage_state.json")
BROWSER_SELECTOR_MEMORY_PATH = os.path.join(BROWSER_PROFILE_DIR, "selector_memory.json")
BROWSER_DECISION_CACHE_PATH = os.path.join(BROWSER_PROFILE_DIR, "decision_cache.json")
HOST_BROWSER_USER_DATA_DIR = _default_host_browser_user_data_dir()
BROWSER_USER_DATA_DIR = HOST_BROWSER_USER_DATA_DIR or os.path.join(BROWSER_PROFILE_DIR, "profile")
BROWSER_GUEST_PROFILE_DIR = os.path.join(BROWSER_PROFILE_DIR, "guest")
BROWSER_GUEST_STORAGE_STATE_PATH = os.path.join(BROWSER_PROFILE_DIR, "guest_storage_state.json")
BROWSER_GUEST_SELECTOR_MEMORY_PATH = os.path.join(BROWSER_PROFILE_DIR, "guest_selector_memory.json")
BROWSER_GUEST_DECISION_CACHE_PATH = os.path.join(BROWSER_PROFILE_DIR, "guest_decision_cache.json")
BROWSER_WINDOW_PROFILE_DIR = BROWSER_USER_DATA_DIR
BROWSER_WINDOW_STORAGE_STATE_PATH = os.path.join(BROWSER_PROFILE_DIR, "window_storage_state.json")
BROWSER_WINDOW_SELECTOR_MEMORY_PATH = os.path.join(BROWSER_PROFILE_DIR, "window_selector_memory.json")
BROWSER_WINDOW_DECISION_CACHE_PATH = os.path.join(BROWSER_PROFILE_DIR, "window_decision_cache.json")
BROWSER_POST_DONE_LIVE_SECONDS = float(os.getenv("SKEMI_COMPUTER_POST_DONE_LIVE_SECONDS", "60"))
BROWSER_SESSION_IDLE_TTL = float(os.getenv("SKEMI_COMPUTER_SESSION_IDLE_TTL", "1800"))
BROWSER_SESSION_REUSE_TTL = float(os.getenv("SKEMI_COMPUTER_SESSION_REUSE_TTL", "900"))
BROWSER_PERSISTENT_CONTEXT = os.getenv("SKEMI_COMPUTER_PERSISTENT_CONTEXT", "1").strip().lower() in {"1", "true", "yes"}
BROWSER_DECISION_CACHE_TTL = float(os.getenv("SKEMI_COMPUTER_DECISION_CACHE_TTL", "180"))
BROWSER_DECISION_CACHE_MAX = int(os.getenv("SKEMI_COMPUTER_DECISION_CACHE_MAX", "180"))
VIRTUAL_BROWSER_HOME_URL = str(os.getenv("SKEMI_VIRTUAL_BROWSER_HOME_URL", "https://www.google.com/") or "https://www.google.com/").strip()
# Virtual Browser must stay isolated from the user's real desktop by default.
# Native-window capture is kept as an opt-in debug path only.
BROWSER_HEADLESS = os.getenv("SKEMI_COMPUTER_HEADLESS", "1").strip().lower() in {"1", "true", "yes"}
BROWSER_NATIVE_WINDOW = os.getenv("SKEMI_COMPUTER_NATIVE_WINDOW", "0").strip().lower() in {"1", "true", "yes"}
BROWSER_VIRTUAL_WINDOW_EXPERIMENTAL = os.getenv("SKEMI_COMPUTER_VIRTUAL_WINDOW_EXPERIMENTAL", "0").strip().lower() in {"1", "true", "yes"}


# ── Active Sessions ───────────────────────────────────────────────────

active_sessions: Dict[str, "BrowserAgentSession"] = {}


def _cleanup_stale_sessions(max_age: float = BROWSER_SESSION_IDLE_TTL):
    """Remove sessions that have been idle for too long."""
    now = time.time()
    stale = []
    for sid, session in list(active_sessions.items()):
        last_active = float(getattr(session, "last_active_at", getattr(session, "created_at", now)) or now)
        execute_task = getattr(session, "_execute_task", None)
        is_busy = bool(execute_task and not execute_task.done())
        if is_busy:
            continue
        if now - last_active > max_age:
            stale.append(sid)
    for sid in stale:
        session = active_sessions.pop(sid, None)
        if session:
            asyncio.create_task(session.close())


# ── SSE Event Helper ──────────────────────────────────────────────────

def sse_event(event_type: str, data: dict, silent: bool = False) -> str:
    """Format a Server-Sent Event string."""
    payload_data = {"type": event_type, **data}
    if silent:
        payload_data["silent"] = True
    payload = json.dumps(payload_data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


def _coerce_number(value: Any, default: float) -> float:
    """Accept loose model outputs such as lists, dicts, or numeric strings."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return float(default)
        match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", "."))
        if match:
            try:
                return float(match.group(0))
            except Exception:
                return float(default)
        return float(default)
    if isinstance(value, (list, tuple)):
        return _coerce_number(value[0], default) if value else float(default)
    if isinstance(value, dict):
        for key in ("value", "x", "y", "left", "top", "cx", "cy"):
            if key in value:
                return _coerce_number(value.get(key), default)
        for nested in value.values():
            return _coerce_number(nested, default)
    return float(default)


def _coerce_axis(value: Any, default: int, limit: int) -> int:
    if isinstance(value, str) and value.strip().endswith("%"):
        pct = _coerce_number(value[:-1], default)
        scaled = round((pct / 100.0) * max(limit - 1, 0))
        return max(0, min(limit - 1, int(scaled)))
    numeric = round(_coerce_number(value, default))
    return max(0, min(limit - 1, int(numeric)))

def _get_chrome_profile_directory(user_data_dir: str) -> str:
    """Read Chrome's Local State to find the last used profile instead of defaulting to 'Default'."""
    try:
        if not user_data_dir or not os.path.isdir(user_data_dir):
            return ""
        local_state_path = os.path.join(user_data_dir, "Local State")
        if os.path.exists(local_state_path):
            with open(local_state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get("profile", {}).get("last_used", "")).strip()
    except Exception:
        pass
    return ""


def _resolve_point(params: Any, default_x: int, default_y: int, width: int, height: int) -> tuple[int, int]:
    params = params if isinstance(params, dict) else {}

    x_source = params.get("x")
    y_source = params.get("y")

    if isinstance(x_source, (list, tuple)) and y_source is None:
        if len(x_source) >= 2:
            x_source, y_source = x_source[0], x_source[1]
        elif len(x_source) == 1:
            x_source = x_source[0]

    point = params.get("point") or params.get("coordinates") or params.get("coord") or params.get("target")
    if (x_source is None or y_source is None) and isinstance(point, (list, tuple)) and len(point) >= 2:
        x_source = point[0] if x_source is None else x_source
        y_source = point[1] if y_source is None else y_source
    elif (x_source is None or y_source is None) and isinstance(point, dict):
        x_source = point.get("x", point.get("left", point.get("cx"))) if x_source is None else x_source
        y_source = point.get("y", point.get("top", point.get("cy"))) if y_source is None else y_source

    bbox = params.get("bbox") or params.get("box") or params.get("rect")
    if (x_source is None or y_source is None) and isinstance(bbox, dict):
        left = _coerce_number(bbox.get("x", bbox.get("left", default_x)), default_x)
        top = _coerce_number(bbox.get("y", bbox.get("top", default_y)), default_y)
        box_w = max(1.0, _coerce_number(bbox.get("width", bbox.get("w", 1)), 1))
        box_h = max(1.0, _coerce_number(bbox.get("height", bbox.get("h", 1)), 1))
        x_source = left + (box_w / 2.0)
        y_source = top + (box_h / 2.0)

    return (
        _coerce_axis(x_source, default_x, width),
        _coerce_axis(y_source, default_y, height),
    )


def _coerce_seconds(value: Any, default: int = 2) -> int:
    numeric = _coerce_number(value, default)
    return max(0, min(30, int(round(numeric))))


def _normalize_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _token_overlap_score(needle: str, haystack: str) -> int:
    left = {token for token in re.split(r"\W+", str(needle or "").lower()) if token}
    right = {token for token in re.split(r"\W+", str(haystack or "").lower()) if token}
    if not left or not right:
        return 0
    return len(left & right)


def _fold_text(value: Any) -> str:
    text = str(value or "")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def _detect_user_language(command: str) -> str:
    folded = _fold_text(command)
    vietnamese_signals = (
        " ban ",
        " vao ",
        " mo ",
        " web ",
        " hoi ",
        " tim ",
        " giup ",
        " cho toi ",
        " nguoi dung ",
    )
    if any(signal in f" {folded} " for signal in vietnamese_signals):
        return "vi"
    return "en"


def _ui_text(language: str, vi: str, en: str) -> str:
    return vi if language == "vi" else en


def _load_json_dict(path: str) -> Dict[str, Any]:
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
                if isinstance(payload, dict):
                    return payload
    except Exception:
        pass
    return {}


def _save_json_dict(path: str, payload: Dict[str, Any]) -> None:
    try:
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen = set()
    output: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        output.append(token)
    return output


def _selector_token(value: Any, limit: int = 90) -> str:
    folded = _fold_text(value)
    cleaned = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return cleaned[:limit]


def _escape_selector_value(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _css_attr_selector(attr: str, value: Any, tag: str = "") -> str:
    safe = _escape_selector_value(value)
    if not safe:
        return ""
    prefix = str(tag or "").strip()
    return f'{prefix}[{attr}="{safe}"]' if prefix else f'[{attr}="{safe}"]'


def _has_text_selector(selector: str, text: Any) -> str:
    safe_text = _escape_selector_value(text)
    if not safe_text:
        return ""
    return f'{selector}:has-text("{safe_text}")'


def _extract_prompt_text(command: str) -> str:
    patterns = [
        r"(?:hỏi nó|hoi no|hỏi gemini|hoi gemini|hỏi chatgpt|hoi chatgpt|hỏi claude|hoi claude)\s+(.+)$",
        r"(?:ask it|ask gemini|ask chatgpt|ask claude|ask)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, command, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" .,!?:;\"'")
    return ""


def _dom_has_human_verification(url: str, dom_text: str) -> bool:
    current_url = str(url or "").lower()
    text = _normalize_label(dom_text)
    return any((
        "google.com/sorry" in current_url,
        "recaptcha" in text,
        "cloudflare" in text,
        "khong phai la nguoi may" in text,
        "xac minh ban la con nguoi" in text,
        "verify you are human" in text,
        "verify you are a human" in text,
        "turnstile" in text,
    ))


def _build_browser_task_profile(command: str) -> Dict[str, str]:
    lowered = _fold_text(command)
    language = _detect_user_language(command)
    prompt_text = _extract_prompt_text(command)
    site_name = "web"
    start_url = ""

    direct_url_match = re.search(
        r"(https?://\S+|[\w.-]+\.(?:com|org|net|io|vn|co|edu|gov)\S*)",
        command,
        re.IGNORECASE,
    )
    if direct_url_match:
        raw = direct_url_match.group(1)
        start_url = raw if raw.startswith("http") else f"https://{raw}"
        site_name = raw
    elif "google gemini" in lowered or re.search(r"\bgemini\b", lowered):
        start_url = "https://gemini.google.com/app"
        site_name = "Google Gemini"
    elif re.search(r"\bchatgpt\b|\bopenai\b", lowered):
        start_url = "https://chatgpt.com/"
        site_name = "ChatGPT"
    elif re.search(r"\bclaude\b|\banthropic\b", lowered):
        start_url = "https://claude.ai/"
        site_name = "Claude"
    elif any(kw in lowered for kw in ["youtube"]):
        start_url = "https://www.youtube.com"
        site_name = "YouTube"
    elif any(kw in lowered for kw in ["facebook"]):
        start_url = "https://www.facebook.com"
        site_name = "Facebook"
    elif any(kw in lowered for kw in ["github"]):
        start_url = "https://github.com"
        site_name = "GitHub"
    elif any(kw in lowered for kw in ["canva"]):
        start_url = "https://www.canva.com"
        site_name = "Canva"
    elif any(kw in lowered for kw in ["google", "tim kiem", "search", "tra cuu"]):
        cleaned = re.sub(
            r"(?:mở|mo|open|tìm|tim|search|go to|navigate|tìm kiếm|tim kiem|tra cứu|tra cuu)\s*",
            "",
            command,
            flags=re.IGNORECASE,
        ).strip()
        start_url = f"https://www.google.com/search?q={quote_plus(cleaned)}" if cleaned else "https://www.google.com"
        site_name = "Google"
    else:
        start_url = f"https://www.google.com/search?q={quote_plus(command)}"
        site_name = "Google"

    if prompt_text:
        goal = _ui_text(
            language,
            f"Mở {site_name} và gửi chính xác câu hỏi sau: \"{prompt_text}\". Sau khi có câu trả lời, trả về kết quả cuối cùng cho người dùng bằng tiếng Việt có dấu.",
            f"Open {site_name} and submit this exact question: \"{prompt_text}\". After the answer appears, return the final result to the user in English.",
        )
    else:
        goal = _ui_text(
            language,
            f"Thực hiện đúng yêu cầu của người dùng trên {site_name} và chỉ dừng khi đã hoàn thành hoặc cần người dùng tiếp quản thủ công.",
            f"Complete the user's request on {site_name} and stop only when it is finished or when manual user takeover is required.",
        )

    return {
        "language": language,
        "start_url": start_url,
        "site_name": site_name,
        "prompt_text": prompt_text,
        "goal": goal,
    }


# ── AI Helper ─────────────────────────────────────────────────────────

def _extract_prompt_text_v2(command: str) -> str:
    normalized = re.sub(r"\s+", " ", str(command or "")).strip()
    folded = _fold_text(normalized)
    patterns = [
        r"(?:hoi no|hoi gemini|hoi chatgpt|hoi claude)\s+(.+)$",
        r"(?:ask it|ask gemini|ask chatgpt|ask claude|ask)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, folded, flags=re.IGNORECASE)
        if match:
            start_index = match.start(1)
            original_tail = normalized[start_index:]
            return re.sub(r"\s+", " ", original_tail).strip(" .,!?:;\"'")
    return ""


def _build_browser_task_profile_v2(command: str) -> Dict[str, str]:
    lowered = _fold_text(command)
    language = _detect_user_language(command)
    prompt_text = _extract_prompt_text_v2(command)
    site_name = "web"
    start_url = ""

    direct_url_match = re.search(
        r"(https?://\S+|[\w.-]+\.(?:com|org|net|io|vn|co|edu|gov)\S*)",
        command,
        re.IGNORECASE,
    )
    if direct_url_match:
        raw = direct_url_match.group(1)
        start_url = raw if raw.startswith("http") else f"https://{raw}"
        site_name = raw
    elif "google gemini" in lowered or re.search(r"\bgemini\b", lowered):
        start_url = "https://gemini.google.com/app"
        site_name = "Google Gemini"
    elif re.search(r"\bchatgpt\b|\bopenai\b", lowered):
        start_url = "https://chatgpt.com/"
        site_name = "ChatGPT"
    elif re.search(r"\bclaude\b|\banthropic\b", lowered):
        start_url = "https://claude.ai/"
        site_name = "Claude"
    elif "youtube" in lowered:
        start_url = "https://www.youtube.com"
        site_name = "YouTube"
    elif "facebook" in lowered:
        start_url = "https://www.facebook.com"
        site_name = "Facebook"
    elif "github" in lowered:
        start_url = "https://github.com"
        site_name = "GitHub"
    elif "canva" in lowered:
        start_url = "https://www.canva.com"
        site_name = "Canva"
    elif any(kw in lowered for kw in ("google", "tim kiem", "search", "tra cuu")):
        cleaned = re.sub(
            r"(?:mở|mo|open|tìm|tim|search|go to|navigate|tìm kiếm|tim kiem|tra cứu|tra cuu)\s*",
            "",
            command,
            flags=re.IGNORECASE,
        ).strip()
        start_url = f"https://www.google.com/search?q={quote_plus(cleaned)}" if cleaned else "https://www.google.com"
        site_name = "Google"
    else:
        start_url = f"https://www.google.com/search?q={quote_plus(command)}"
        site_name = "Google"

    if prompt_text:
        goal = _ui_text(
            language,
            f"Mở {site_name} và gửi chính xác câu hỏi sau: \"{prompt_text}\". Sau khi có câu trả lời, trả về kết quả cuối cùng cho người dùng bằng tiếng Việt có dấu.",
            f"Open {site_name} and submit this exact question: \"{prompt_text}\". After the answer appears, return the final result to the user in English.",
        )
    else:
        goal = _ui_text(
            language,
            f"Thực hiện đúng yêu cầu của người dùng trên {site_name} và chỉ dừng khi đã hoàn thành hoặc cần người dùng tiếp quản thủ công.",
            f"Complete the user's request on {site_name} and stop only when it is finished or when manual user takeover is required.",
        )

    return {
        "language": language,
        "start_url": start_url,
        "site_name": site_name,
        "prompt_text": prompt_text,
        "goal": goal,
    }


def _domain_name(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower()
    except Exception:
        return ""


def _is_known_chat_surface(url: str) -> bool:
    host = _domain_name(url)
    return any(domain in host for domain in ("gemini.google.com", "chatgpt.com", "claude.ai"))


def _chat_surface_name(url: str) -> str:
    host = _domain_name(url)
    if "gemini.google.com" in host:
        return "Google Gemini"
    if "chatgpt.com" in host:
        return "ChatGPT"
    if "claude.ai" in host:
        return "Claude"
    return "web"


def _explicit_chat_surface_target(command: str) -> str:
    lowered = _fold_text(command)
    if "google gemini" in lowered or re.search(r"\bgemini\b", lowered):
        return "gemini.google.com"
    if re.search(r"\bchatgpt\b|\bopenai\b", lowered):
        return "chatgpt.com"
    if re.search(r"\bclaude\b|\banthropic\b", lowered):
        return "claude.ai"
    return ""


def _has_explicit_browser_navigation_signal(command: str) -> bool:
    raw = str(command or "")
    lowered = _fold_text(raw)
    if re.search(r"(https?://|www\.|[\w.-]+\.(?:com|org|net|io|vn|co|edu|gov)\b)", raw, re.IGNORECASE):
        return True
    search_pattern = r"\b(search|tim kiem|t[iì]m ki[eế]m|tra cuu|tra c[uứ]u|google)\b"
    if re.search(search_pattern, lowered, re.IGNORECASE):
        return True
    nav_pattern = r"\b(mo|m[oở]|open|vao|v[aà]o|go to|navigate|visit|truy cap|truy c[aậ]p)\b"
    surface_pattern = r"\b(web|website|trang|browser|chatgpt|gemini|claude|google|youtube|facebook|github|canva)\b"
    return bool(re.search(nav_pattern, lowered, re.IGNORECASE) and re.search(surface_pattern, lowered, re.IGNORECASE))


def _is_navigation_only_command(command: str) -> bool:
    raw = str(command or "").strip()
    if not raw:
        return False
    lowered = _fold_text(raw)
    if _extract_prompt_text_v2(raw):
        return False
    if _followup_prompt_text(raw):
        return False
    if any(marker in lowered for marker in ("tim kiem", "tìm kiếm", "search", "tra cuu", "tra cứu", "hoi ", "hỏi ", "ask ")):
        return False
    direct_url = bool(re.search(r"(https?://|www\.|[\w.-]+\.(?:com|org|net|io|vn|co|edu|gov)\b)", raw, re.IGNORECASE))
    if direct_url:
        return True
    return _has_explicit_browser_navigation_signal(raw)


def _followup_prompt_text(command: str) -> str:
    extracted = _extract_prompt_text_v2(command)
    if extracted:
        return extracted
    normalized = re.sub(r"\s+", " ", str(command or "")).strip()
    folded = _fold_text(normalized)
    tail_patterns = [
        r"(?:hay\s+)?hoi\s+(?:no|gemini|chatgpt|claude)\s+(.+)$",
        r"(?:please\s+)?ask\s+(?:it|gemini|chatgpt|claude)\s+(.+)$",
    ]
    for pattern in tail_patterns:
        match = re.search(pattern, folded, flags=re.IGNORECASE)
        if match:
            start_index = match.start(1)
            original_tail = normalized[start_index:]
            return re.sub(r"\s+", " ", original_tail).strip(" .,!?:;\"'")
    normalized = re.sub(
        r"^(?:hay|hãy|please|vui lòng|vui long|giup toi|giúp tôi|lam on|làm ơn)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    return normalized.strip(" .,!?:;\"'")


def _is_chat_followup_instruction(command: str) -> bool:
    folded = _fold_text(command)
    if not folded:
        return False
    followup_patterns = (
        r"\b(hay|hãy|please)\s+(hoi|hỏi|ask)\b",
        r"\b(hoi|hỏi|ask)\s+(no|nó|it|gemini|chatgpt|claude)\b",
        r"\b(tiep tuc|tiếp tục|continue)\b",
        r"\b(tra loi tiep|trả lời tiếp|reply next|follow up)\b",
    )
    return any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in followup_patterns)


def _should_continue_current_chat_surface(command: str, current_url: str) -> bool:
    if not _is_known_chat_surface(current_url):
        return False
    explicit_target = _explicit_chat_surface_target(command)
    if explicit_target and explicit_target not in _domain_name(current_url):
        return False
    if _is_chat_followup_instruction(command):
        return bool(_followup_prompt_text(command))
    if _has_explicit_browser_navigation_signal(command):
        return False
    return bool(_followup_prompt_text(command))


def _looks_like_auth_wall(url: str, snapshot: Dict[str, Any]) -> bool:
    host = _domain_name(url)
    body_text = _normalize_label((snapshot or {}).get("body_text"))
    auth_signals = (
        "đăng nhập",
        "dang nhap",
        "sign in",
        "log in",
        "continue with google",
        "continue with account",
        "verify you are human",
        "xác minh",
        "xac minh",
    )
    if "accounts.google.com" in host:
        return True
    return any(signal in body_text for signal in auth_signals)


def _description_is_generic(value: Any) -> bool:
    folded = _fold_text(value)
    if not folded:
        return True
    generic_markers = (
        "hoan thanh nhiem vu",
        "muc tieu da hoan thanh",
        "phien thao tac da hoan tat",
        "da cung cap thong tin",
        "task completed",
        "goal completed",
        "session is complete",
        "provided the information",
        "completed the request",
    )
    return any(marker in folded for marker in generic_markers)


def _trim_result_text(value: Any, limit: int = 2400) -> str:
    text = str(value or "").replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _contains_sensitive_terms(*values: Any) -> bool:
    haystack = " ".join(_fold_text(value) for value in values if value)
    if not haystack:
        return False
    sensitive_terms = (
        "tai khoan",
        "account",
        "dang nhap",
        "login",
        "sign in",
        "password",
        "mat khau",
        "security",
        "bao mat",
        "billing",
        "thanh toan",
        "payment",
        "wallet",
        "bank",
        "ngan hang",
        "admin",
        "quan tri",
        "settings",
        "cai dat",
        "delete",
        "xoa",
        "remove",
        "install",
        "system",
    )
    return any(term in haystack for term in sensitive_terms)


async def _ask_vision_model(screenshot_b64: str, prompt: str) -> str:
    """Send base64 screenshot and prompt to vision model via Ollama."""
    # Dynamically read and apply proxy override
    v_model = os.environ.get("SKEMI_MODEL_VISION", "qwen3-vl:235b-cloud")
    
    try:
        async with httpx.AsyncClient(timeout=STEP_TIMEOUT) as client:
            resp = await client.post(OLLAMA_GENERATE_URL, json={
                "model": v_model,
                "prompt": prompt,
                "images": [screenshot_b64],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 500}
            })
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return data.get("response", "").strip()
                except Exception as parse_e:
                    print(f"!!! [COMPUTER AGENT] JSON Parse error: {parse_e} - Raw: {resp.text[:100]}")
            else:
                print(f"!!! [COMPUTER AGENT] HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"!!! [COMPUTER AGENT] Vision model error: {e}")
    return ""


async def _ask_text_model(prompt: str) -> str:
    """Ask text-only model for planning / URL inference."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(OLLAMA_GENERATE_URL, json={
                "model": TEXT_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300}
            })
            if resp.status_code == 200:
                full = ""
                for line in resp.text.splitlines():
                    if line.strip():
                        try:
                            part = json.loads(line)
                            if "response" in part:
                                full += part["response"]
                            if part.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
                return full.strip()
    except Exception as e:
        print(f"[COMPUTER AGENT] Text model error: {e}")
    return ""


def _infer_start_url(command: str) -> str:
    """Extract or infer the starting URL from user command."""
    profile = _build_browser_task_profile_v2(command)
    if profile.get("start_url"):
        return profile["start_url"]

    # Direct URL in command
    url_match = re.search(
        r'(https?://\S+|[\w.-]+\.(?:com|org|net|io|vn|co|edu|gov)\S*)',
        command, re.IGNORECASE
    )
    if url_match:
        raw = url_match.group(1)
        return raw if raw.startswith("http") else f"https://{raw}"

    # Keyword-based inference
    lower = command.lower()
    if any(kw in lower for kw in ["google", "tìm kiếm", "search"]):
        # Extract search query
        search_terms = re.sub(
            r'(?:mở|open|tìm|search|go to|navigate|tìm kiếm|tra cứu)\s*',
            '', command, flags=re.IGNORECASE
        ).strip()
        if search_terms:
            from urllib.parse import quote_plus
            return f"https://www.google.com/search?q={quote_plus(search_terms)}"
        return "https://www.google.com"

    if "youtube" in lower:
        return "https://www.youtube.com"
    if "facebook" in lower:
        return "https://www.facebook.com"
    if "github" in lower:
        return "https://github.com"
    if "canva" in lower:
        return "https://www.canva.com"

    # Default: Google search with the command
    from urllib.parse import quote_plus
    return f"https://www.google.com/search?q={quote_plus(command)}"


# ── Public Helper ───────────────────────────────────────────────────

def _balanced_json_objects(text: str) -> list[str]:
    candidates: list[str] = []
    if not text:
        return candidates
    start = -1
    depth = 0
    in_string = False
    quote_char = ""
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
            continue
        if char in {'"', "'"}:
            in_string = True
            quote_char = char
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth <= 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(text[start:index + 1])
                start = -1
    return candidates


def _json_candidates_from_text(text: str) -> list[str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE):
        block = str(match.group(1) or "").strip()
        if block:
            candidates.append(block)
    candidates.extend(_balanced_json_objects(cleaned))
    if cleaned.startswith("{") and cleaned.endswith("}"):
        candidates.append(cleaned)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _sanitize_json_candidate(candidate: str) -> str:
    sanitized = str(candidate or "").strip()
    sanitized = sanitized.replace("\u201c", '"').replace("\u201d", '"')
    sanitized = sanitized.replace("\u2018", "'").replace("\u2019", "'")
    sanitized = re.sub(r",(\s*[}\]])", r"\1", sanitized)
    return sanitized


def _coerce_action_payload(data: Any) -> dict:
    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict)), {})
    if not isinstance(data, dict):
        return {}
    action_type = str(data.get("action", "observe") or "observe").strip().lower()
    params = data.get("params", {})
    if isinstance(params, list):
        params = {"x": params[0], "y": params[1]} if len(params) >= 2 else {}
    elif not isinstance(params, dict):
        params = {}
    if not params:
        params = {
            key: value
            for key, value in data.items()
            if key not in {"thought", "plan", "action", "verification", "description"}
        }
    plan = data.get("plan", [])
    if isinstance(plan, str):
        plan = [line.strip("- ").strip() for line in plan.splitlines() if line.strip()]
    elif not isinstance(plan, list):
        plan = []
    return {
        "thought": str(data.get("thought", "") or ""),
        "plan": plan,
        "action": action_type,
        "params": params,
        "verification": str(data.get("verification", "") or ""),
        "description": str(data.get("description", "") or desc_from_action(action_type, params)),
        "_parsed_ok": True,
    }


def _parse_ai_action(text: str) -> dict:
    """Parse model action output into the runtime schema."""
    cleaned = str(text or "").strip()
    parse_errors: list[str] = []

    for candidate in _json_candidates_from_text(cleaned):
        sanitized = _sanitize_json_candidate(candidate)
        for variant in (candidate, sanitized):
            try:
                return _coerce_action_payload(json.loads(variant))
            except Exception as exc:
                parse_errors.append(str(exc))
        try:
            pythonish = sanitized
            pythonish = re.sub(r"\btrue\b", "True", pythonish, flags=re.IGNORECASE)
            pythonish = re.sub(r"\bfalse\b", "False", pythonish, flags=re.IGNORECASE)
            pythonish = re.sub(r"\bnull\b", "None", pythonish, flags=re.IGNORECASE)
            payload = _coerce_action_payload(ast.literal_eval(pythonish))
            if payload:
                return payload
        except Exception as exc:
            parse_errors.append(str(exc))

    lower = cleaned.lower()
    if "click" in lower:
        m = re.search(r'(\d{1,4})[\s,]+(\d{1,4})', cleaned)
        if m:
            return {
                "action": "click",
                "params": {"x": int(m.group(1)), "y": int(m.group(2))},
                "description": "Nhap chuot (fallback)",
                "_parsed_ok": False,
            }
    action_match = re.search(r"\b(click|type|hover|press|scroll|navigate|wait|done)\b", lower)
    if parse_errors:
        print(f"[COMPUTER AGENT] Parse error: {parse_errors[0]}")
    return {
        "action": action_match.group(1) if action_match else "observe",
        "thought": cleaned[:240],
        "description": "Dang quan sat...",
        "_parsed_ok": False,
    }


def _overlay_targets(snapshot: Dict[str, Any], limit: int = 18) -> list[Dict[str, Any]]:
    output: list[Dict[str, Any]] = []
    items = list((snapshot or {}).get("items") or [])
    for item in items:
        if len(output) >= limit:
            break
        tag = str(item.get("tag") or "").strip().lower()
        role = str(item.get("role") or "").strip().lower()
        label = str(
            item.get("text")
            or item.get("aria_label")
            or item.get("placeholder")
            or item.get("name")
            or item.get("id")
            or item.get("href")
            or ""
        ).strip()
        if not label and tag not in {"input", "textarea", "button", "a", "select"} and role not in {"button", "link", "textbox", "searchbox", "combobox"}:
            continue
        output.append({
            "skemi_id": str(item.get("skemi_id") or ""),
            "x": int(item.get("x") or 0),
            "y": int(item.get("y") or 0),
            "left": int(item.get("left") or 0),
            "top": int(item.get("top") or 0),
            "width": int(item.get("width") or 0),
            "height": int(item.get("height") or 0),
            "tag": tag,
            "role": role,
            "label": label[:80],
        })
    return output

def desc_from_action(action: str, params: dict) -> str:
    if action == "click": return f"Nhấp chuột tại {params.get('x')}, {params.get('y')}"
    if action == "type": return f"Nhập văn bản: \"{params.get('text', '')}\""
    if action == "navigate": return f"Mở trang: {params.get('url')}"
    if action == "scroll": return f"Cuộn trang {params.get('direction', 'down')}"
    if action == "hover": return f"Rê chuột đến {params.get('x')}, {params.get('y')}"
    if action == "press": return f"Nhấn phím: {params.get('key')}"
    if action == "wait": return f"Đang chờ {params.get('seconds', 2)}s..."
    if action == "done": return "✅ Hoàn thành mục tiêu"
    return "Đang xử lý..."


# ── Browser Agent Session ─────────────────────────────────────────────

class BrowserAgentSession:
    """A single browser automation session controlled by AI."""

    def __init__(self, session_id: str, command: str, browser_shell: str = "virtual", bypass_safety: bool = False):
        self.session_id = session_id
        self.command = command
        self.browser_shell = str(browser_shell or "virtual").strip().lower() or "virtual"
        self.bypass_safety = bool(bypass_safety)
        if self.browser_shell == "virtual_window" and not BROWSER_VIRTUAL_WINDOW_EXPERIMENTAL:
            self.browser_shell = "virtual"
        if self.browser_shell == "virtual_window" and os.name != "nt":
            self.browser_shell = "virtual"
        self.command_profile = _build_browser_task_profile_v2(command)
        self.user_language = self.command_profile.get("language", "vi")
        self.execution_goal = self.command_profile.get("goal", command)
        self.prompt_text = self.command_profile.get("prompt_text", "")
        self.start_url = self.command_profile.get("start_url", "")
        self.site_name = self.command_profile.get("site_name", "web")
        self.created_at = time.time()
        self.last_active_at = self.created_at
        self.last_completed_at = 0.0
        self.state = "idle"
        self.cancelled = False
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self.current_url = ""
        self.session_memory = []
        self.screenshots = []
        self.step_count = 0
        self.consecutive_observe = 0
        self.history = []  # List of previous actions
        self.plan = []     # Current multi-step plan
        self.last_verification = "" # What we expected to see
        self.last_sc_b64 = ""      # Last screenshot for comparison
        self.last_action_stuck = False # Flag if page didn't change
        self.last_dom_snapshot: Dict[str, Any] = {}
        self.prompt_dispatched = False
        self.prompt_dispatched_step = 0
        self.prompt_dispatched_at = 0.0
        self.latest_result_text = ""
        self.result_stable_count = 0
        self.session_continuation_hint = ""
        self.continue_current_surface = False
        self.latest_live_b64 = ""
        self.latest_live_at = 0.0
        self._capture_lock = asyncio.Lock()
        self._live_capture_task: Optional[asyncio.Task] = None
        self.stop_reason = _ui_text(self.user_language, "Da dung theo yeu cau.", "Stopped as requested.")
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._close_requested = False
        self._execute_task: Optional[asyncio.Task] = None
        self.pending_confirmation: Optional[Dict[str, Any]] = None
        self._confirmation_event = asyncio.Event()
        self._confirmation_approved = False
        self.pending_manual_takeover: Optional[Dict[str, Any]] = None
        self._manual_resume_event = asyncio.Event()
        self._tabs: Dict[str, Any] = {}
        self._active_tab_id = ""
        self._tab_seq = 0
        self._browser_window_hwnd = 0
        self._browser_window_rect = None
        self._browser_content_rect = None
        self._browser_window_capture_size = (0, 0)
        self._headless = BROWSER_HEADLESS
        self._native_browser_surface = BROWSER_NATIVE_WINDOW and not self._headless and os.name == "nt"
        if self.browser_shell == "virtual_window" and os.name == "nt":
            self._headless = False
            self._native_browser_surface = True
        if self.browser_shell == "chrome_guest" and os.name == "nt":
            self._headless = False
            self._native_browser_surface = True
        self._window_boot_marker = f"Skemi Virtual Browser {self.session_id}"
        self._cdp_session = None
        self._cdp_screencast_enabled = False
        self._last_screencast_at = 0.0
        self.storage_state_path = BROWSER_STORAGE_STATE_PATH
        self.selector_memory_path = BROWSER_SELECTOR_MEMORY_PATH
        self.decision_cache_path = BROWSER_DECISION_CACHE_PATH
        self.user_data_dir = BROWSER_USER_DATA_DIR
        if self.browser_shell == "virtual_window":
            self.storage_state_path = BROWSER_WINDOW_STORAGE_STATE_PATH
            self.selector_memory_path = BROWSER_WINDOW_SELECTOR_MEMORY_PATH
            self.decision_cache_path = BROWSER_WINDOW_DECISION_CACHE_PATH
            self.user_data_dir = BROWSER_WINDOW_PROFILE_DIR
        if self.browser_shell == "chrome_guest":
            self.storage_state_path = BROWSER_GUEST_STORAGE_STATE_PATH
            self.selector_memory_path = BROWSER_GUEST_SELECTOR_MEMORY_PATH
            self.decision_cache_path = BROWSER_GUEST_DECISION_CACHE_PATH
            self.user_data_dir = BROWSER_GUEST_PROFILE_DIR
        self.persistent_context = BROWSER_PERSISTENT_CONTEXT
        self.selector_memory: Dict[str, Any] = _load_json_dict(self.selector_memory_path)
        self.decision_cache: Dict[str, Any] = _load_json_dict(self.decision_cache_path)

    def _touch(self) -> None:
        self.last_active_at = time.time()

    def can_accept_new_command(self) -> bool:
        if self.cancelled or self._close_requested:
            return False
        if not self._context:
            return False
        if self._execute_task and not self._execute_task.done():
            return False
        return True

    def prepare_for_command(self, command: str) -> None:
        previous_result = str(self.latest_result_text or "").strip()
        previous_goal = str(self.execution_goal or "").strip()
        previous_command = str(self.command or "").strip()
        previous_url = str(self.current_url or "").strip()
        previous_site = str(self.site_name or "").strip()
        previous_prompt = str(self.prompt_text or "").strip()
        if previous_command or previous_goal or previous_result or previous_url:
            memory_entry = {
                "command": previous_command[:240],
                "goal": previous_goal[:240],
                "result": previous_result[:360],
                "url": previous_url[:240],
                "completed_at": float(self.last_completed_at or self.last_active_at or time.time()),
            }
            self.session_memory = [entry for entry in self.session_memory if isinstance(entry, dict)]
            self.session_memory.append(memory_entry)
            self.session_memory = self.session_memory[-6:]
        self.command = str(command or "").strip()
        self.command_profile = _build_browser_task_profile_v2(self.command)
        self.user_language = self.command_profile.get("language", "vi")
        self.execution_goal = self.command_profile.get("goal", self.command)
        self.prompt_text = self.command_profile.get("prompt_text", "")
        self.start_url = self.command_profile.get("start_url", "")
        self.site_name = self.command_profile.get("site_name", "web")
        self.continue_current_surface = False
        if previous_url and _should_continue_current_chat_surface(self.command, previous_url):
            self.start_url = previous_url
            self.site_name = previous_site or _chat_surface_name(previous_url)
            self.prompt_text = _followup_prompt_text(self.command) or self.prompt_text or self.command
            self.continue_current_surface = True
            self.execution_goal = _ui_text(
                self.user_language,
                f"Tiếp tục ngay trên {self.site_name} hiện tại và gửi chính xác câu hỏi sau: \"{self.prompt_text}\". Không mở lại Google hay điều hướng sang web khác nếu chưa cần.",
                f"Continue on the current {self.site_name} page and submit this exact question: \"{self.prompt_text}\". Do not restart from Google or navigate elsewhere unless required.",
            )
        continuity_bits = []
        if previous_site:
            continuity_bits.append(f"prev_site={previous_site}")
        if previous_url:
            continuity_bits.append(f"prev_url={previous_url[:220]}")
        if previous_prompt:
            continuity_bits.append(f"prev_prompt={previous_prompt[:180]}")
        if previous_result:
            continuity_bits.append(f"prev_result={previous_result[:240]}")
        self.session_continuation_hint = " | ".join(continuity_bits)
        self.cancelled = False
        self.step_count = 0
        self.consecutive_observe = 0
        self.history = []
        self.plan = []
        self.last_verification = ""
        self.last_sc_b64 = ""
        self.last_action_stuck = False
        self.last_dom_snapshot = {}
        self.prompt_dispatched = False
        self.prompt_dispatched_step = 0
        self.prompt_dispatched_at = 0.0
        self.latest_result_text = ""
        self.result_stable_count = 0
        self.pending_confirmation = None
        self._confirmation_event = asyncio.Event()
        self._confirmation_approved = False
        self.pending_manual_takeover = None
        self._manual_resume_event = asyncio.Event()
        self.stop_reason = _ui_text(self.user_language, "Da dung theo yeu cau.", "Stopped as requested.")
        self.state = "idle"
        self._touch()

    async def launch(self):
        """Start Playwright and launch Chromium."""
        if self._context is not None:
            page = None
            with contextlib.suppress(Exception):
                pages = list(getattr(self._context, "pages", []) or [])
                pages = [candidate for candidate in pages if not candidate.is_closed()]
                if pages:
                    page = pages[-1]
            if page is None and self._context is not None:
                page = await self._context.new_page()
            if page is not None:
                await self._configure_page(page, make_active=True)
            self._start_live_capture()
            self._touch()
            return
        playwright_factory = _ensure_playwright()
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._pw_cm = playwright_factory()
        self._playwright = await self._pw_cm.__aenter__()
        browser_lang = "vi-VN" if self.user_language == "vi" else "en-US"
        accept_language = f"{browser_lang},en-US;q=0.9,en;q=0.8"
        launch_args = [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            f"--lang={browser_lang}",
            "--window-size=1440,980",
        ]
        
        # Guest Session Fix: If we are using the user's real User Data directory,
        # we must specify the correct profile directory (e.g. Profile 1, Profile 2),
        # otherwise Playwright creates/uses a blank 'Default' profile.
        if self.user_data_dir and os.path.basename(self.user_data_dir).lower() == "user data":
            active_profile = _get_chrome_profile_directory(self.user_data_dir)
            if active_profile:
                launch_args.append(f"--profile-directory={active_profile}")
        if self.browser_shell == "virtual_window":
            launch_args.extend([
                "--window-position=-24000,-24000",
                "--force-device-scale-factor=1",
            ])
        if self.browser_shell == "chrome_guest":
            launch_args.extend([
                "--guest",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
            ])
        launch_kwargs = {
            "headless": self._headless,
            "args": launch_args,
        }
        context_kwargs = {
            "viewport": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            "screen": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            "device_scale_factor": 1,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": browser_lang,
            "timezone_id": "Asia/Ho_Chi_Minh" if self.user_language == "vi" else "UTC",
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "ignore_https_errors": True,
            "extra_http_headers": {
                "Accept-Language": accept_language,
            },
        }
        browser = None
        if self.persistent_context:
            persistent_kwargs = {**launch_kwargs, **context_kwargs}
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    self.user_data_dir,
                    channel="chrome",
                    **persistent_kwargs,
                )
            except Exception:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    self.user_data_dir,
                    **persistent_kwargs,
                )
            self._browser = getattr(self._context, "browser", None)
        else:
            try:
                browser = await self._playwright.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                browser = None
            if browser is None:
                browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._browser = browser
            if self.storage_state_path and os.path.exists(self.storage_state_path):
                context_kwargs["storage_state"] = self.storage_state_path
            try:
                self._context = await self._browser.new_context(**context_kwargs)
            except Exception:
                context_kwargs.pop("storage_state", None)
                self._context = await self._browser.new_context(**context_kwargs)
        with contextlib.suppress(Exception):
            self._context.on("page", lambda page: asyncio.create_task(self._capture_new_context_page(page)))
        await self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
            window.chrome = window.chrome || { runtime: {} };
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            const originalQuery = navigator.permissions && navigator.permissions.query;
            if (originalQuery) {
                navigator.permissions.query = (parameters) => {
                    if (parameters && parameters.name === 'notifications') {
                        return Promise.resolve({ state: Notification.permission });
                    }
                    return originalQuery.call(navigator.permissions, parameters);
                };
            }
            """
        )
        initial_page = None
        with contextlib.suppress(Exception):
            pages = list(getattr(self._context, "pages", []) or [])
            if pages:
                initial_page = pages[0]
        if initial_page is None:
            initial_page = await self._context.new_page()
        await self._configure_page(initial_page, make_active=True)
        if self._native_browser_surface:
            boot_html = (
                f"<html><head><title>{self._window_boot_marker}</title></head>"
                "<body style='font-family:Segoe UI,Arial,sans-serif;background:#0b1220;color:#d1fae5;"
                "display:flex;align-items:center;justify-content:center;height:100vh;'>"
                "<div><h1 style='font-size:28px;margin-bottom:12px;'>Skemi Virtual Browser</h1>"
                "<p style='opacity:.75;'>Initializing dedicated virtual Chrome window...</p></div>"
                "</body></html>"
            )
            with contextlib.suppress(Exception):
                await initial_page.goto(f"data:text/html;charset=utf-8,{quote(boot_html)}", wait_until="domcontentloaded", timeout=8000)
        await asyncio.sleep(0.45)
        bound = await self._bind_browser_window_by_marker()
        if self._native_browser_surface and not bound and self.browser_shell == "virtual_window":
            self._native_browser_surface = False
            self.browser_shell = "virtual"
        self._start_live_capture()
        self._touch()

    async def _persist_storage_state(self) -> None:
        if not self._context or not self.storage_state_path:
            return
        with contextlib.suppress(Exception):
            os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
        with contextlib.suppress(Exception):
            await self._context.storage_state(path=self.storage_state_path)

    def _next_tab_id(self) -> str:
        self._tab_seq += 1
        return f"tab-{self._tab_seq}"

    async def _configure_page(self, page: Any, make_active: bool = False, tab_id: Optional[str] = None) -> str:
        if page is None:
            return ""
        for existing_id, existing_page in list(self._tabs.items()):
            if existing_page is page:
                tab_id = existing_id
                break
        if not tab_id:
            tab_id = self._next_tab_id()
        try:
            page.set_default_timeout(2800)
            page.set_default_navigation_timeout(18000)
        except Exception:
            pass
        with contextlib.suppress(Exception):
            await page.route("**/*.{mp4,webm,ogg,mp3,wav,avi}", lambda route: route.abort())
        self._tabs[tab_id] = page
        if make_active or not self._page:
            self._page = page
            self._active_tab_id = tab_id
            with contextlib.suppress(Exception):
                await page.bring_to_front()
            self.current_url = str(getattr(page, "url", "") or self.current_url or "")
            await self._attach_cdp_session(page)
        return tab_id

    async def _capture_new_context_page(self, page: Any) -> None:
        await self._configure_page(page, make_active=True)
        with contextlib.suppress(Exception):
            self.current_url = str(getattr(page, "url", "") or self.current_url or "")

    async def _attach_cdp_session(self, page: Any) -> bool:
        if self._native_browser_surface or not self._context or page is None:
            return False
        previous = self._cdp_session
        self._cdp_session = None
        self._cdp_screencast_enabled = False
        if previous is not None:
            with contextlib.suppress(Exception):
                await previous.send("Page.stopScreencast")
        try:
            session = await self._context.new_cdp_session(page)
        except Exception:
            return False

        async def _ack_frame(params: Dict[str, Any]) -> None:
            data = str((params or {}).get("data") or "")
            session_id = (params or {}).get("sessionId")
            if data:
                self.latest_live_b64 = data
                self.latest_live_at = time.time()
                self._last_screencast_at = self.latest_live_at
            if session_id is not None:
                with contextlib.suppress(Exception):
                    await session.send("Page.screencastFrameAck", {"sessionId": session_id})

        def _on_frame(params: Dict[str, Any]) -> None:
            if not self._loop:
                return
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(_ack_frame(dict(params or {}))))

        try:
            session.on("Page.screencastFrame", _on_frame)
            await session.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": max(22, min(LIVE_CAPTURE_QUALITY, 72)),
                "maxWidth": max(640, min(LIVE_CAPTURE_MAX_WIDTH, VIEWPORT_WIDTH)),
                "maxHeight": max(420, min(LIVE_CAPTURE_MAX_HEIGHT, VIEWPORT_HEIGHT)),
                "everyNthFrame": 1,
            })
            self._cdp_session = session
            self._cdp_screencast_enabled = True
            return True
        except Exception:
            with contextlib.suppress(Exception):
                await session.send("Page.stopScreencast")
            return False

    async def _ensure_active_page(self) -> bool:
        page = self._page
        try:
            if page is not None and not page.is_closed():
                return True
        except Exception:
            pass

        for tab_id, candidate in list(self._tabs.items()):
            try:
                if candidate is not None and not candidate.is_closed():
                    self._page = candidate
                    self._active_tab_id = tab_id
                    self.current_url = str(getattr(candidate, "url", "") or self.current_url or "")
                    return True
            except Exception:
                self._tabs.pop(tab_id, None)
                continue

        if not self._context:
            return False
        try:
            candidate = await self._context.new_page()
            await self._configure_page(candidate, make_active=True)
            self.current_url = str(getattr(candidate, "url", "") or self.current_url or "")
            return True
        except Exception:
            return False

    def _resolve_browser_content_rect_sync(
        self,
        hwnd: int,
        window_rect: Optional[tuple[int, int, int, int]] = None,
    ) -> Optional[tuple[int, int, int, int]]:
        try:
            win32gui = _ensure_browser_win32()
            if not hwnd or not win32gui.IsWindow(hwnd):
                return None
            left, top, right, bottom = window_rect or win32gui.GetWindowRect(hwnd)
            child_hits: list[tuple[int, tuple[int, int, int, int]]] = []

            def _enum_child(child_hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(child_hwnd):
                        return
                    c_left, c_top, c_right, c_bottom = win32gui.GetWindowRect(child_hwnd)
                    width = int(c_right - c_left)
                    height = int(c_bottom - c_top)
                    if width < 360 or height < 220:
                        return
                    if c_left < left - 4 or c_top < top - 4 or c_right > right + 4 or c_bottom > bottom + 4:
                        return
                    child_hits.append((width * height, (int(c_left), int(c_top), int(c_right), int(c_bottom))))
                except Exception:
                    return

            with contextlib.suppress(Exception):
                win32gui.EnumChildWindows(hwnd, _enum_child, None)
            if child_hits:
                child_hits.sort(key=lambda pair: pair[0], reverse=True)
                return child_hits[0][1]

            client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
            top_left = win32gui.ClientToScreen(hwnd, (client_left, client_top))
            bottom_right = win32gui.ClientToScreen(hwnd, (client_right, client_bottom))
            return (
                int(top_left[0]),
                int(top_left[1]),
                int(bottom_right[0]),
                int(bottom_right[1]),
            )
        except Exception:
            return None

    def _bind_browser_window_by_marker_sync(self) -> bool:
        if not self._native_browser_surface:
            return False
        try:
            win32gui = _ensure_browser_win32()
            marker = str(self._window_boot_marker or "").strip().lower()
            matches: list[int] = []

            def _enum(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return
                    class_name = str(win32gui.GetClassName(hwnd) or "")
                    title = str(win32gui.GetWindowText(hwnd) or "")
                    if "Chrome_WidgetWin" not in class_name:
                        return
                    if marker and marker in title.lower():
                        matches.append(int(hwnd))
                except Exception:
                    return

            win32gui.EnumWindows(_enum, None)
            hwnd = matches[-1] if matches else 0
            if hwnd and win32gui.IsWindow(hwnd):
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                self._browser_window_hwnd = int(hwnd)
                self._browser_window_rect = (int(left), int(top), int(right), int(bottom))
                self._browser_content_rect = self._resolve_browser_content_rect_sync(hwnd, self._browser_window_rect)
                return True
        except Exception:
            return False
        return False

    async def _bind_browser_window_by_marker(self, retries: int = 24, delay: float = 0.15) -> bool:
        if not self._native_browser_surface:
            return False
        for _ in range(max(1, retries)):
            matched = await asyncio.to_thread(self._bind_browser_window_by_marker_sync)
            if matched:
                return True
            await asyncio.sleep(delay)
        return False

    async def _adopt_foreground_browser_window(self) -> bool:
        if not self._native_browser_surface:
            return False
        try:
            resolved = await asyncio.to_thread(self._resolve_browser_window_sync)
            return bool(resolved)
        except Exception:
            return False

    def _resolve_browser_window_sync(self) -> Optional[tuple[int, tuple[int, int, int, int]]]:
        if not self._native_browser_surface:
            return None
        try:
            win32gui = _ensure_browser_win32()
            hwnd = int(self._browser_window_hwnd or 0)
            if hwnd and win32gui.IsWindow(hwnd):
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if right - left >= 200 and bottom - top >= 160:
                    self._browser_window_rect = (int(left), int(top), int(right), int(bottom))
                    self._browser_content_rect = self._resolve_browser_content_rect_sync(hwnd, self._browser_window_rect)
                    return hwnd, self._browser_window_rect
            if self._bind_browser_window_by_marker_sync():
                hwnd = int(self._browser_window_hwnd or 0)
                if hwnd and self._browser_window_rect:
                    return hwnd, self._browser_window_rect
        except Exception:
            return None
        return None

    def _surface_metrics_payload(self) -> Dict[str, Any]:
        if self._native_browser_surface:
            self._resolve_browser_window_sync()
            window_rect = self._browser_window_rect
            content_rect = self._browser_content_rect
            capture_w, capture_h = self._browser_window_capture_size
            if window_rect and content_rect:
                left, top, right, bottom = window_rect
                c_left, c_top, c_right, c_bottom = content_rect
                window_w = max(1, int(right - left))
                window_h = max(1, int(bottom - top))
                base_w = max(1, int(capture_w or window_w))
                base_h = max(1, int(capture_h or window_h))
                scale_x = base_w / window_w
                scale_y = base_h / window_h
                return {
                    "mode": "native_window",
                    "capture_width": base_w,
                    "capture_height": base_h,
                    "content_left": int(round((c_left - left) * scale_x)),
                    "content_top": int(round((c_top - top) * scale_y)),
                    "content_width": int(round((c_right - c_left) * scale_x)),
                    "content_height": int(round((c_bottom - c_top) * scale_y)),
                    "page_width": VIEWPORT_WIDTH,
                    "page_height": VIEWPORT_HEIGHT,
                }
        return {
            "mode": "page",
            "capture_width": VIEWPORT_WIDTH,
            "capture_height": VIEWPORT_HEIGHT,
            "content_left": 0,
            "content_top": 0,
            "content_width": VIEWPORT_WIDTH,
            "content_height": VIEWPORT_HEIGHT,
            "page_width": VIEWPORT_WIDTH,
            "page_height": VIEWPORT_HEIGHT,
        }

    def _capture_browser_window_sync(self, quality: int) -> str:
        target = self._resolve_browser_window_sync()
        if not target:
            return ""
        hwnd, rect = target
        left, top, right, bottom = rect
        width = max(1, int(right - left))
        height = max(1, int(bottom - top))
        image = None
        if self.browser_shell == "virtual_window":
            image = self._capture_browser_window_printwindow_sync(hwnd, width, height)
        if image is None:
            _, ImageGrab = _ensure_browser_desktop()
            image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=False)
        image = image.convert("RGB")
        self._browser_window_capture_size = (int(image.width), int(image.height))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=max(20, min(int(quality), 90)), optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _capture_browser_window_printwindow_sync(self, hwnd: int, width: int, height: int):
        try:
            win32gui, win32ui, win32con = _ensure_browser_win32_modules()
            _ensure_browser_desktop()
            Image = _browser_pil_image
            if not hwnd or width < 2 or height < 2 or Image is None:
                return None
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            if not hwnd_dc:
                return None
            src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            mem_dc = src_dc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(src_dc, width, height)
            mem_dc.SelectObject(bmp)
            try:
                user32 = _ensure_browser_user32()
                flags = 0x00000002
                result = int(user32.PrintWindow(int(hwnd), mem_dc.GetSafeHdc(), flags))
                if result != 1:
                    result = int(user32.PrintWindow(int(hwnd), mem_dc.GetSafeHdc(), 0))
                if result != 1:
                    return None
                bmp_info = bmp.GetInfo()
                bmp_bytes = bmp.GetBitmapBits(True)
                if not bmp_bytes:
                    return None
                return Image.frombuffer(
                    "RGB",
                    (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                    bmp_bytes,
                    "raw",
                    "BGRX",
                    0,
                    1,
                )
            finally:
                win32gui.DeleteObject(bmp.GetHandle())
                mem_dc.DeleteDC()
                src_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            return None

    def _window_point_to_screen(self, x: int, y: int) -> tuple[int, int]:
        rect = self._browser_window_rect or (0, 0, 0, 0)
        capture_w, capture_h = self._browser_window_capture_size
        left, top, right, bottom = rect
        rect_w = max(1, int(right - left))
        rect_h = max(1, int(bottom - top))
        base_w = capture_w or rect_w
        base_h = capture_h or rect_h
        sx = int(left + max(0, min(base_w - 1, int(x))) * (rect_w / max(1, base_w)))
        sy = int(top + max(0, min(base_h - 1, int(y))) * (rect_h / max(1, base_h)))
        return sx, sy

    def _capture_point_to_page(self, x: int, y: int) -> Optional[tuple[int, int]]:
        metrics = self._surface_metrics_payload()
        if str(metrics.get("mode") or "") != "native_window":
            return (
                _coerce_axis(x, VIEWPORT_WIDTH // 2, VIEWPORT_WIDTH),
                _coerce_axis(y, VIEWPORT_HEIGHT // 2, VIEWPORT_HEIGHT),
            )
        capture_w = max(1, int(metrics.get("capture_width") or self._browser_window_capture_size[0] or 1))
        capture_h = max(1, int(metrics.get("capture_height") or self._browser_window_capture_size[1] or 1))
        safe_x = _coerce_axis(x, capture_w // 2, capture_w)
        safe_y = _coerce_axis(y, capture_h // 2, capture_h)
        content_left = int(metrics.get("content_left") or 0)
        content_top = int(metrics.get("content_top") or 0)
        content_width = max(1, int(metrics.get("content_width") or capture_w))
        content_height = max(1, int(metrics.get("content_height") or capture_h))
        if not (content_left <= safe_x <= content_left + content_width and content_top <= safe_y <= content_top + content_height):
            return None
        page_width = max(1, int(metrics.get("page_width") or VIEWPORT_WIDTH))
        page_height = max(1, int(metrics.get("page_height") or VIEWPORT_HEIGHT))
        rel_x = safe_x - content_left
        rel_y = safe_y - content_top
        page_x = int(round(rel_x * (page_width / max(1, content_width))))
        page_y = int(round(rel_y * (page_height / max(1, content_height))))
        return (
            _coerce_axis(page_x, VIEWPORT_WIDTH // 2, VIEWPORT_WIDTH),
            _coerce_axis(page_y, VIEWPORT_HEIGHT // 2, VIEWPORT_HEIGHT),
        )

    def _native_click_sync(self, screen_x: int, screen_y: int, click_count: int = 1) -> bool:
        pyautogui, _ = _ensure_browser_desktop()
        previous = pyautogui.position()
        if getattr(desktop_agent, "PHYSICAL_INPUT_LOCKED", False):
            # print("[SHIELD] computer_agent blocked physical click")
            return False
        try:
            pyautogui.click(int(screen_x), int(screen_y), clicks=max(1, int(click_count or 1)), interval=0.04, duration=0.02)
            return True
        finally:
            with contextlib.suppress(Exception):
                pyautogui.moveTo(previous.x, previous.y, duration=0.02)

    def _native_scroll_sync(self, direction: str, screen_x: int, screen_y: int) -> bool:
        pyautogui, _ = _ensure_browser_desktop()
        previous = pyautogui.position()
        amount = 520 if str(direction).lower().startswith("up") else -520
        if getattr(desktop_agent, "PHYSICAL_INPUT_LOCKED", False):
            # print("[SHIELD] computer_agent blocked physical scroll")
            return False
        try:
            pyautogui.moveTo(int(screen_x), int(screen_y), duration=0.02)
            pyautogui.scroll(amount)
            return True
        finally:
            with contextlib.suppress(Exception):
                pyautogui.moveTo(previous.x, previous.y, duration=0.02)

    def _native_press_sync(self, key: str) -> bool:
        pyautogui, _ = _ensure_browser_desktop()
        token = str(key or "").strip()
        if not token:
            return False
        if getattr(desktop_agent, "PHYSICAL_INPUT_LOCKED", False):
            # print("[SHIELD] computer_agent blocked physical keypress")
            return False
        if len(combo) >= 2:
            pyautogui.hotkey(*combo, interval=0.02)
        else:
            pyautogui.press(token.lower())
        return True

    def _native_type_sync(self, text: str) -> bool:
        pyautogui, _ = _ensure_browser_desktop()
        if getattr(desktop_agent, "PHYSICAL_INPUT_LOCKED", False):
            # print("[SHIELD] computer_agent blocked physical type")
            return False
        pyautogui.write(value, interval=0.008)
        return True

    async def get_tabs_payload(self) -> Dict[str, Any]:
        tabs: list[Dict[str, Any]] = []
        for tab_id, page in list(self._tabs.items()):
            try:
                if page.is_closed():
                    self._tabs.pop(tab_id, None)
                    continue
            except Exception:
                pass
            title = ""
            with contextlib.suppress(Exception):
                title = str(await page.title() or "").strip()
            url = str(getattr(page, "url", "") or "about:blank")
            if not title:
                parsed = urlparse(url)
                title = (parsed.netloc or parsed.path or "Tab mới").strip()[:48]
            tabs.append({
                "id": tab_id,
                "title": title[:56],
                "url": url,
                "active": tab_id == self._active_tab_id,
            })
        tabs.sort(key=lambda item: int(re.search(r"(\d+)$", item["id"]).group(1)) if re.search(r"(\d+)$", item["id"]) else 0)
        if self._active_tab_id not in {tab["id"] for tab in tabs} and tabs:
            self._active_tab_id = tabs[0]["id"]
            self._page = self._tabs.get(self._active_tab_id)
            self.current_url = str(getattr(self._page, "url", "") or self.current_url or "")
        return {"tabs": tabs, "active_tab_id": self._active_tab_id, "url": self.current_url}

    async def runtime_snapshot(self) -> Dict[str, Any]:
        current_title = str(((self.last_dom_snapshot or {}) or {}).get("title") or "").strip()
        if self._page:
            with contextlib.suppress(Exception):
                self.current_url = str(getattr(self._page, "url", "") or self.current_url or "")
            if not current_title:
                with contextlib.suppress(Exception):
                    current_title = str(await self._page.title() or "").strip()
        tabs_payload = await self.get_tabs_payload()
        if self.pending_manual_takeover:
            runtime_message = _ui_text(
                self.user_language,
                "Virtual Browser đang chờ bạn tiếp quản thủ công.",
                "Virtual Browser is waiting for your manual takeover.",
            )
        elif self.pending_confirmation:
            runtime_message = _ui_text(
                self.user_language,
                "Skemi đang chờ bạn xác nhận thao tác nhạy cảm.",
                "Skemi is waiting for your confirmation.",
            )
        elif str(self.state or "").strip().lower() == "idle":
            runtime_message = _ui_text(
                self.user_language,
                "Chrome ảo của AI đã sẵn sàng.",
                "The AI virtual Chrome is ready.",
            )
        elif self.latest_result_text:
            runtime_message = str(self.latest_result_text or "")[:400]
        else:
            runtime_message = _ui_text(
                self.user_language,
                "Skemi đang thao tác trên browser ảo hiện tại.",
                "Skemi is working in the current virtual browser.",
            )
        return {
            "session_id": self.session_id,
            "state": str(self.state or "idle"),
            "browser_shell": str(self.browser_shell or "virtual"),
            "current_url": str(self.current_url or ""),
            "current_title": current_title[:240],
            "message": runtime_message,
            "image": str(self.latest_live_b64 or "")[:10_000_000],
            "surface_metrics": self._surface_metrics_payload(),
            "targets": _overlay_targets(self.last_dom_snapshot),
            "prompt_text": str(self.prompt_text or ""),
            "last_result": str(self.latest_result_text or "")[:2000],
            "session_memory": list(self.session_memory[-6:]),
            "decision_cache_ref": str(self.decision_cache_path or ""),
            "decision_cache_size": len(self.decision_cache),
            "pending_manual_takeover": dict(self.pending_manual_takeover or {}),
            "pending_confirmation": dict(self.pending_confirmation or {}),
            "prompt_dispatched": bool(self.prompt_dispatched),
            "prompt_dispatched_step": int(self.prompt_dispatched_step or 0),
            "last_active_at": float(self.last_active_at or time.time()),
            "created_at": float(self.created_at or time.time()),
            "site_name": str(self.site_name or ""),
            "tabs": list(tabs_payload.get("tabs") or []),
            "active_tab_id": str(tabs_payload.get("active_tab_id") or ""),
        }

    async def ensure_ready(self, home_url: str = "") -> Dict[str, Any]:
        await self.launch()
        target_url = str(home_url or VIRTUAL_BROWSER_HOME_URL or "").strip()
        current_url = str(self.current_url or getattr(self._page, "url", "") or "").strip()
        if target_url and (not current_url or current_url in {"about:blank", "data:,"}):
            with contextlib.suppress(Exception):
                await self.navigate(target_url)
                current_url = str(self.current_url or getattr(self._page, "url", "") or "").strip()
        screenshot_b64 = await self.screenshot(quality=LIVE_CAPTURE_QUALITY, store_in_history=False)
        snapshot = await self.dom_snapshot()
        self.state = "idle"
        self._touch()
        return {
            "session_id": self.session_id,
            "browser_shell": str(self.browser_shell or "virtual"),
            "current_url": str(self.current_url or current_url or ""),
            "current_title": str((snapshot or {}).get("title") or ""),
            "image": screenshot_b64,
            "targets": _overlay_targets(snapshot),
            "surface_metrics": self._surface_metrics_payload(),
        }

    async def open_tab(self, url: str = "about:blank") -> Dict[str, Any]:
        if not self._context:
            return {"tabs": [], "active_tab_id": "", "url": ""}
        page = await self._context.new_page()
        tab_id = await self._configure_page(page, make_active=True)
        target_url = str(url or "about:blank").strip() or "about:blank"
        if target_url and target_url != "about:blank":
            with contextlib.suppress(Exception):
                await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                self.current_url = page.url
        payload = await self.get_tabs_payload()
        payload["opened_tab_id"] = tab_id
        return payload

    async def switch_tab(self, tab_id: str) -> Dict[str, Any]:
        target_id = str(tab_id or "").strip()
        page = self._tabs.get(target_id)
        if page:
            self._page = page
            self._active_tab_id = target_id
            with contextlib.suppress(Exception):
                await page.bring_to_front()
            self.current_url = str(getattr(page, "url", "") or self.current_url or "")
        payload = await self.get_tabs_payload()
        payload["success"] = bool(page)
        return payload

    async def close_tab(self, tab_id: str) -> Dict[str, Any]:
        target_id = str(tab_id or "").strip()
        page = self._tabs.pop(target_id, None)
        if page:
            with contextlib.suppress(Exception):
                await page.close()
        if self._active_tab_id == target_id:
            remaining_ids = list(self._tabs.keys())
            if remaining_ids:
                await self.switch_tab(remaining_ids[-1])
            elif self._context:
                await self.open_tab("about:blank")
        return await self.get_tabs_payload()

    def _start_live_capture(self):
        if self._live_capture_task and not self._live_capture_task.done():
            return
        self._live_capture_task = asyncio.create_task(self._live_capture_loop())

    async def _live_capture_loop(self):
        while not self.cancelled:
            if not self._page:
                await asyncio.sleep(LIVE_CAPTURE_INTERVAL)
                continue
            if self._cdp_screencast_enabled and (time.time() - self._last_screencast_at) <= 1.0:
                await asyncio.sleep(max(0.02, LIVE_CAPTURE_INTERVAL * 0.5))
                continue
            try:
                await self.screenshot(quality=LIVE_CAPTURE_QUALITY, store_in_history=False)
            except Exception:
                pass
            await asyncio.sleep(LIVE_CAPTURE_INTERVAL)

    async def screenshot(self, quality: int = ANALYSIS_CAPTURE_QUALITY, store_in_history: bool = True) -> str:
        """Take a screenshot and return base64 JPEG."""
        if not await self._ensure_active_page():
            return ""
        try:
            if (
                not self._native_browser_surface
                and self._cdp_screencast_enabled
                and quality <= LIVE_CAPTURE_QUALITY
                and self.latest_live_b64
                and (time.time() - self._last_screencast_at) <= 1.0
            ):
                b64 = self.latest_live_b64
                if store_in_history:
                    self.screenshots.append(b64)
                    if len(self.screenshots) > 24:
                        self.screenshots = self.screenshots[-24:]
                return b64
            if self._native_browser_surface:
                async with self._capture_lock:
                    native_b64 = await asyncio.to_thread(self._capture_browser_window_sync, quality)
                if native_b64:
                    b64 = native_b64
                else:
                    async with self._capture_lock:
                        jpeg_bytes = await self._page.screenshot(type="jpeg", quality=max(20, min(quality, 90)))
                    b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
            else:
                async with self._capture_lock:
                    jpeg_bytes = await self._page.screenshot(type="jpeg", quality=max(20, min(quality, 90)))
                b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
            self.latest_live_b64 = b64
            self.latest_live_at = time.time()
            if store_in_history:
                self.screenshots.append(b64)
                if len(self.screenshots) > 24:
                    self.screenshots = self.screenshots[-24:]
            return b64
        except Exception as e:
            print(f"[COMPUTER AGENT] Screenshot error: {e}")
            return ""

    async def dom_snapshot(self) -> Dict[str, Any]:
        if not await self._ensure_active_page():
            return {}
        try:
            snapshot = await self._page.evaluate(
                """
                () => {
                    const viewportW = window.innerWidth || 1280;
                    const viewportH = window.innerHeight || 800;
                    const selectors = [
                        "button",
                        "a[href]",
                        "input",
                        "textarea",
                        "select",
                        "[role='button']",
                        "[role='link']",
                        "[role='textbox']",
                        "[role='searchbox']",
                        "[role='combobox']",
                        "[contenteditable='true']",
                        "label",
                        "summary"
                    ];
                    const items = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll(selectors.join(","))) {
                        if (!(el instanceof HTMLElement) || seen.has(el)) continue;
                        seen.add(el);
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        const visible = style.display !== "none" && style.visibility !== "hidden" && rect.width >= 4 && rect.height >= 4;
                        const inView = rect.bottom >= 0 && rect.right >= 0 && rect.top <= viewportH && rect.left <= viewportW;
                        if (!visible || !inView) continue;
                        const skemiId = String(items.length + 1);
                        el.setAttribute("data-skemi-id", skemiId);
                        items.push({
                            skemi_id: skemiId,
                            tag: el.tagName.toLowerCase(),
                            role: (el.getAttribute("role") || el.tagName || "").toLowerCase(),
                            type: (el.getAttribute("type") || "").toLowerCase(),
                            contenteditable: !!el.isContentEditable,
                            text: (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 160),
                            aria_label: (el.getAttribute("aria-label") || "").replace(/\\s+/g, " ").trim().slice(0, 160),
                            placeholder: (el.getAttribute("placeholder") || "").replace(/\\s+/g, " ").trim().slice(0, 160),
                            name: (el.getAttribute("name") || "").replace(/\\s+/g, " ").trim().slice(0, 120),
                            id: (el.id || "").trim().slice(0, 120),
                            href: (el.getAttribute("href") || "").trim().slice(0, 200),
                            value: ("value" in el ? String(el.value || "") : "").slice(0, 120),
                            disabled: !!el.disabled,
                            checked: !!el.checked,
                            x: Math.round(rect.left + (rect.width / 2)),
                            y: Math.round(rect.top + (rect.height / 2)),
                            left: Math.round(rect.left),
                            top: Math.round(rect.top),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                        if (items.length >= 80) break;
                    }

                    const active = document.activeElement instanceof HTMLElement
                        ? {
                            skemi_id: document.activeElement.getAttribute("data-skemi-id") || "",
                            tag: document.activeElement.tagName.toLowerCase(),
                            role: (document.activeElement.getAttribute("role") || document.activeElement.tagName || "").toLowerCase(),
                            id: document.activeElement.id || "",
                            aria_label: document.activeElement.getAttribute("aria-label") || "",
                            placeholder: document.activeElement.getAttribute("placeholder") || "",
                            name: document.activeElement.getAttribute("name") || "",
                            text: (document.activeElement.innerText || document.activeElement.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 120),
                            contenteditable: !!document.activeElement.isContentEditable
                        }
                        : null;

                    return {
                        title: document.title || "",
                        url: location.href,
                        scroll: {
                            x: Math.round(window.scrollX || 0),
                            y: Math.round(window.scrollY || 0),
                            max_y: Math.max(0, Math.round((document.scrollingElement?.scrollHeight || document.body?.scrollHeight || 0) - (window.innerHeight || 0))),
                            viewport_h: Math.round(window.innerHeight || 0),
                            can_scroll_down: ((window.scrollY || 0) + (window.innerHeight || 0) + 12) < (document.scrollingElement?.scrollHeight || document.body?.scrollHeight || 0),
                            can_scroll_up: (window.scrollY || 0) > 12
                        },
                        active,
                        items,
                        body_text: (document.body?.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 2500)
                    };
                }
                """
            )
            self.last_dom_snapshot = snapshot if isinstance(snapshot, dict) else {}
            return self.last_dom_snapshot
        except Exception as e:
            print(f"[COMPUTER AGENT] DOM snapshot error: {e}")
            self.last_dom_snapshot = {}
            return {}

    def _format_dom_summary(self, snapshot: Dict[str, Any], limit: int = 40) -> str:
        items = list((snapshot or {}).get("items") or [])[:limit]
        scroll = dict((snapshot or {}).get("scroll") or {})
        lines = [
            f"scroll_y={scroll.get('y', 0)} max_scroll_y={scroll.get('max_y', 0)} "
            f"can_scroll_down={bool(scroll.get('can_scroll_down'))} can_scroll_up={bool(scroll.get('can_scroll_up'))}"
        ]
        for item in items:
            parts = [
                f"[{item.get('skemi_id', '-')}]",
                item.get("tag", ""),
                f"role={item.get('role', '')}",
                f"text={json.dumps(str(item.get('text') or '')[:80], ensure_ascii=False)}",
            ]
            if item.get("placeholder"):
                parts.append(f"placeholder={json.dumps(str(item.get('placeholder'))[:60], ensure_ascii=False)}")
            if item.get("aria_label"):
                parts.append(f"aria={json.dumps(str(item.get('aria_label'))[:60], ensure_ascii=False)}")
            parts.append(f"center=({item.get('x')},{item.get('y')})")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def _context_window_payload(self, snapshot: Dict[str, Any], step_num: int = 0) -> Dict[str, Any]:
        active = dict((snapshot or {}).get("active") or {})
        scroll = dict((snapshot or {}).get("scroll") or {})
        items = list((snapshot or {}).get("items") or [])[:10]
        compact_items = []
        for item in items:
            compact_items.append({
                "skemi_id": item.get("skemi_id"),
                "tag": item.get("tag"),
                "role": item.get("role"),
                "text": str(item.get("text") or "")[:90],
                "placeholder": str(item.get("placeholder") or "")[:50],
                "aria_label": str(item.get("aria_label") or "")[:50],
                "disabled": bool(item.get("disabled")),
            })
        return {
            "step": int(step_num or self.step_count or 0),
            "goal": self.execution_goal,
            "site_name": self.site_name,
            "current_url": self.current_url,
            "title": str((snapshot or {}).get("title") or ""),
            "prompt_text": self.prompt_text,
            "prompt_dispatched": bool(self.prompt_dispatched),
            "prompt_dispatched_step": int(self.prompt_dispatched_step or 0),
            "prompt_age_sec": round(max(0.0, time.time() - float(self.prompt_dispatched_at or 0.0)), 2) if self.prompt_dispatched_at else 0.0,
            "latest_result_text": str(self.latest_result_text or "")[:600],
            "last_verification": str(self.last_verification or "")[:300],
            "last_action_stuck": bool(self.last_action_stuck),
            "recent_history": list(self.history[-8:]),
            "recent_plan": list(self.plan[-6:]) if isinstance(self.plan, list) else [],
            "session_memory": list(self.session_memory[-4:]),
            "continuation_hint": str(self.session_continuation_hint or "")[:500],
            "manual_takeover": dict(self.pending_manual_takeover or {}),
            "pending_confirmation": dict(self.pending_confirmation or {}),
            "active_element": {
                "tag": active.get("tag"),
                "role": active.get("role"),
                "text": str(active.get("text") or "")[:120],
                "placeholder": str(active.get("placeholder") or "")[:80],
                "aria_label": str(active.get("aria_label") or "")[:80],
            },
            "scroll": {
                "y": scroll.get("y", 0),
                "max_y": scroll.get("max_y", 0),
                "can_scroll_down": bool(scroll.get("can_scroll_down")),
                "can_scroll_up": bool(scroll.get("can_scroll_up")),
            },
            "visible_items": compact_items,
        }

    def _context_window_text(self, snapshot: Dict[str, Any], step_num: int = 0) -> str:
        return json.dumps(
            self._context_window_payload(snapshot, step_num=step_num),
            ensure_ascii=False,
            indent=2,
        )

    def _decision_cache_key(self, snapshot: Dict[str, Any]) -> str:
        host = _domain_name(self.current_url or self.start_url) or self.site_name or "global"
        items = list((snapshot or {}).get("items") or [])[:14]
        key_payload = {
            "host": host,
            "goal": self.execution_goal,
            "prompt_text": self.prompt_text,
            "prompt_dispatched": bool(self.prompt_dispatched),
            "current_url": self.current_url,
            "title": str((snapshot or {}).get("title") or ""),
            "active": dict((snapshot or {}).get("active") or {}),
            "scroll": dict((snapshot or {}).get("scroll") or {}),
            "items": [
                {
                    "skemi_id": item.get("skemi_id"),
                    "tag": item.get("tag"),
                    "role": item.get("role"),
                    "text": str(item.get("text") or "")[:90],
                    "placeholder": str(item.get("placeholder") or "")[:50],
                    "aria_label": str(item.get("aria_label") or "")[:50],
                    "disabled": bool(item.get("disabled")),
                }
                for item in items
            ],
        }
        digest = hashlib.sha1(json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"{_selector_token(host, limit=60) or 'global'}:{digest}"

    def _recall_decision(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cached = self.decision_cache.get(str(cache_key or "").strip())
        if not isinstance(cached, dict):
            return None
        try:
            age = time.time() - float(cached.get("ts") or 0.0)
        except Exception:
            return None
        if age < 0 or age > BROWSER_DECISION_CACHE_TTL:
            return None
        action_data = cached.get("action_data")
        if not isinstance(action_data, dict):
            return None
        return dict(action_data)

    def _remember_decision(self, cache_key: str, action_data: Dict[str, Any]) -> None:
        if not cache_key or not isinstance(action_data, dict):
            return
        action_type = str(action_data.get("action") or "").strip().lower()
        params = action_data.get("params") if isinstance(action_data.get("params"), dict) else {}
        if action_type not in {"click", "type", "scroll", "press", "wait", "navigate"}:
            return
        if action_type in {"click", "type"} and not (params.get("skemi_id") or params.get("selector")):
            return
        self.decision_cache[str(cache_key)] = {
            "ts": time.time(),
            "action_data": action_data,
        }
        keys = sorted(
            self.decision_cache.keys(),
            key=lambda key: float((self.decision_cache.get(key) or {}).get("ts") or 0.0),
            reverse=True,
        )
        trimmed = {key: self.decision_cache[key] for key in keys[:max(20, BROWSER_DECISION_CACHE_MAX)]}
        self.decision_cache = trimmed
        _save_json_dict(self.decision_cache_path, self.decision_cache)

    def _selector_host_key(self) -> str:
        host = _domain_name(self.current_url or self.start_url) or self.site_name or "global"
        return _selector_token(host, limit=120) or "global"

    def _selector_bucket(self) -> Dict[str, str]:
        host_key = self._selector_host_key()
        bucket = self.selector_memory.get(host_key)
        if not isinstance(bucket, dict):
            bucket = {}
            self.selector_memory[host_key] = bucket
        return bucket

    def _selector_memory_keys(self, params: Dict[str, Any], action_type: str, item: Optional[Dict[str, Any]] = None) -> list[str]:
        hints = [
            params.get("target_text"),
            params.get("label"),
            params.get("target_label"),
            params.get("placeholder"),
            params.get("name"),
            params.get("id"),
            (item or {}).get("text"),
            (item or {}).get("aria_label"),
            (item or {}).get("placeholder"),
            (item or {}).get("name"),
            (item or {}).get("id"),
        ]
        keys = []
        for hint in hints:
            token = _selector_token(hint)
            if token:
                keys.append(f"{action_type}:{token}")
        if action_type == "type":
            keys.append("type:active-input")
        return _dedupe_preserve(keys)[:6]

    def _recall_selector(self, memory_key: str) -> str:
        bucket = self._selector_bucket()
        selector = bucket.get(str(memory_key or "").strip())
        return str(selector or "").strip()

    def _remember_selector(self, memory_keys: list[str], selector: str) -> None:
        clean_selector = str(selector or "").strip()
        if not clean_selector:
            return
        bucket = self._selector_bucket()
        changed = False
        for memory_key in memory_keys:
            key = str(memory_key or "").strip()
            if not key or bucket.get(key) == clean_selector:
                continue
            bucket[key] = clean_selector
            changed = True
        if changed:
            _save_json_dict(self.selector_memory_path, self.selector_memory)

    def _selector_candidates_from_item(self, item: Optional[Dict[str, Any]]) -> list[str]:
        if not item:
            return []
        tag = str(item.get("tag") or "").strip().lower()
        text = str(item.get("text") or "").strip()
        selectors = [
            _css_attr_selector("id", item.get("id")),
            _css_attr_selector("name", item.get("name"), tag),
            _css_attr_selector("placeholder", item.get("placeholder"), tag or "textarea"),
            _css_attr_selector("placeholder", item.get("placeholder"), "input"),
            _css_attr_selector("aria-label", item.get("aria_label"), tag),
        ]
        role = str(item.get("role") or "").strip()
        if role and text:
            selectors.append(_has_text_selector(_css_attr_selector("role", role), text))
        if tag in {"button", "a", "label", "summary", "div", "span"} and text and len(text) <= 80:
            selectors.extend([
                _has_text_selector(tag, text),
                _has_text_selector('[role="button"]', text),
            ])
        return _dedupe_preserve(selectors)

    def _find_chat_input_item(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        items = list((snapshot or {}).get("items") or [])
        best_item = None
        best_score = -1
        keywords = (
            "ask",
            "message",
            "prompt",
            "send a message",
            "chat",
            "nhập",
            "hoi",
            "hỏi",
            "gemini",
            "chatgpt",
            "claude",
        )
        for item in items:
            if item.get("disabled"):
                continue
            tag = str(item.get("tag") or "").lower()
            role = str(item.get("role") or "").lower()
            searchable = " ".join(
                str(item.get(key) or "")
                for key in ("text", "aria_label", "placeholder", "name", "id", "type")
            ).lower()
            score = 0
            if tag in {"textarea", "input"}:
                score += 40
            if item.get("contenteditable"):
                score += 28
            if role in {"textbox", "searchbox", "combobox"}:
                score += 35
            if any(keyword in searchable for keyword in keywords):
                score += 25
            if item.get("placeholder"):
                score += 10
            if score > best_score:
                best_score = score
                best_item = item
        return best_item if best_score >= 35 else None

    def _find_submit_item(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        items = list((snapshot or {}).get("items") or [])
        best_item = None
        best_score = -1
        keywords = ("send", "submit", "gửi", "gui", "ask", "run")
        for item in items:
            if item.get("disabled"):
                continue
            tag = str(item.get("tag") or "").lower()
            role = str(item.get("role") or "").lower()
            searchable = " ".join(
                str(item.get(key) or "")
                for key in ("text", "aria_label", "placeholder", "name", "id", "type")
            ).lower()
            score = 0
            if tag == "button" or role == "button":
                score += 30
            if any(keyword in searchable for keyword in keywords):
                score += 30
            if score > best_score:
                best_score = score
                best_item = item
        return best_item if best_score >= 45 else None

    async def _chat_surface_ready_for_prompt(self, snapshot: Dict[str, Any]) -> bool:
        if not _is_known_chat_surface(self.current_url):
            return False
        if self._find_chat_input_item(snapshot):
            return True
        direct_input = await self._known_chat_input_locator()
        if direct_input is not None:
            return True
        body_text = _fold_text((snapshot or {}).get("body_text") or "")
        ready_markers = (
            "ready when you are",
            "ask anything",
            "message chatgpt",
            "hoi bat ky dieu gi",
            "hom nay ban co y tuong gi",
            "hay bat dau",
            "talk to claude",
            "hoi gemini",
        )
        return any(marker in body_text for marker in ready_markers)

    async def _first_visible_locator(self, selectors: list[str], memory_keys: Optional[list[str]] = None):
        if not self._page:
            return None
        candidate_selectors = list(selectors or [])
        for memory_key in memory_keys or []:
            remembered = self._recall_selector(memory_key)
            if remembered:
                candidate_selectors.insert(0, remembered)
        for selector in _dedupe_preserve(candidate_selectors):
            try:
                locator = self._page.locator(selector).first
                if await locator.count() and await locator.is_visible(timeout=400):
                    if memory_keys:
                        self._remember_selector(memory_keys, selector)
                    return locator
            except Exception:
                continue
        return None

    async def _known_chat_input_locator(self):
        host = _domain_name(self.current_url)
        selectors: list[str] = []
        if "gemini.google.com" in host:
            selectors = [
                'rich-textarea [contenteditable="true"]',
                '[contenteditable="true"][role="textbox"]',
                'textarea[aria-label*="prompt"]',
                'textarea[placeholder*="prompt"]',
                'div[contenteditable="true"]',
            ]
        elif "chatgpt.com" in host:
            selectors = [
                '#prompt-textarea',
                'textarea[placeholder*="Message"]',
                'textarea[placeholder*="message"]',
                '[contenteditable="true"][role="textbox"]',
                'div[contenteditable="true"]',
            ]
        elif "claude.ai" in host:
            selectors = [
                'div[contenteditable="true"][role="textbox"]',
                'div[contenteditable="true"][data-placeholder]',
                'textarea[placeholder*="Claude"]',
                'textarea[placeholder*="message"]',
                'div[contenteditable="true"]',
            ]
        return await self._first_visible_locator(selectors, memory_keys=["type:known-chat-input"])

    async def _known_chat_send_locator(self):
        host = _domain_name(self.current_url)
        selectors: list[str] = []
        if "gemini.google.com" in host:
            selectors = [
                'button[aria-label*="Send"]',
                'button[aria-label*="Submit"]',
                'button[aria-label*="Run"]',
                'button[type="submit"]',
            ]
        elif "chatgpt.com" in host:
            selectors = [
                'button[data-testid="send-button"]',
                'button[aria-label*="Send"]',
                'button[type="submit"]',
            ]
        elif "claude.ai" in host:
            selectors = [
                'button[aria-label*="Send"]',
                'button[data-testid="send-button"]',
                'button[type="submit"]',
            ]
        return await self._first_visible_locator(selectors, memory_keys=["click:known-chat-send"])

    async def _click_locator_direct(self, locator) -> tuple[int, int]:
        await locator.scroll_into_view_if_needed(timeout=1200)
        box = await locator.bounding_box()
        target_x = 640
        target_y = 400
        if box:
            target_x = max(0, min(VIEWPORT_WIDTH - 1, int(round(box["x"] + (box["width"] / 2)))))
            target_y = max(0, min(VIEWPORT_HEIGHT - 1, int(round(box["y"] + (box["height"] / 2)))))
        try:
            await locator.click(timeout=1500, force=True)
        except Exception:
            try:
                await locator.evaluate(
                    """(el) => {
                        if (typeof el.click === 'function') {
                            el.click();
                        }
                    }"""
                )
            except Exception:
                await self.click_at(target_x, target_y)
        return target_x, target_y

    async def _locator_prefers_visible_typing(self, locator) -> bool:
        try:
            result = await locator.evaluate(
                """(el) => {
                    if (!(el instanceof HTMLElement)) return false;
                    const tag = String(el.tagName || '').toLowerCase();
                    const role = String(el.getAttribute('role') || '').toLowerCase();
                    return !!(
                        el.isContentEditable ||
                        tag === 'textarea' ||
                        tag === 'input' ||
                        role === 'textbox' ||
                        role === 'searchbox' ||
                        role === 'combobox'
                    );
                }"""
            )
            return bool(result)
        except Exception:
            return False

    async def _human_type_into_active(self, text_value: str) -> None:
        if not await self._ensure_active_page():
            return
        value = str(text_value or "")
        if not value:
            return
        try:
            with contextlib.suppress(Exception):
                await self._page.bring_to_front()
            with contextlib.suppress(Exception):
                await self._page.evaluate("() => { try { window.focus(); } catch (e) {} }")
            with contextlib.suppress(Exception):
                await self._page.keyboard.press("Control+A")
                await asyncio.sleep(0.025)
                await self._page.keyboard.press("Backspace")
                await asyncio.sleep(0.03)

            for index, ch in enumerate(value):
                if ch == "\n":
                    await self._page.keyboard.press("Shift+Enter")
                    await asyncio.sleep(0.045)
                    continue
                delay = 14 + ((index * 11) % 28) + random.randint(0, 6)
                await self._page.keyboard.type(ch, delay=delay)
                if index and index % 18 == 0:
                    await asyncio.sleep(0.05)
        except Exception:
            await self._page.keyboard.type(value, delay=18)

    async def _fill_locator_direct(self, locator, text_value: str) -> tuple[int, int]:
        await locator.scroll_into_view_if_needed(timeout=1200)
        box = await locator.bounding_box()
        target_x = 640
        target_y = 400
        if box:
            target_x = max(0, min(VIEWPORT_WIDTH - 1, int(round(box["x"] + (box["width"] / 2)))))
            target_y = max(0, min(VIEWPORT_HEIGHT - 1, int(round(box["y"] + (box["height"] / 2)))))
        try:
            await locator.click(timeout=1200, force=True)
        except Exception:
            pass
        prefers_visible_typing = _is_known_chat_surface(self.current_url) or await self._locator_prefers_visible_typing(locator)
        if prefers_visible_typing:
            try:
                await self._human_type_into_active(text_value)
                return target_x, target_y
            except Exception:
                pass
        try:
            await locator.fill(text_value, timeout=1500)
            return target_x, target_y
        except Exception:
            pass
        try:
            await locator.evaluate(
                """(el, value) => {
                    el.focus();
                    if ('value' in el) {
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return;
                    }
                    if (el.isContentEditable) {
                        el.textContent = value;
                        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
                        return;
                    }
                    el.textContent = value;
                }""",
                text_value,
            )
            return target_x, target_y
        except Exception:
            pass
        await self.type_text(text_value)
        return target_x, target_y

    async def _live_point_for_snapshot_item(self, item: Optional[Dict[str, Any]]) -> Optional[tuple[int, int]]:
        if not item:
            return None
        fallback_x = max(0, min(VIEWPORT_WIDTH - 1, int(_coerce_number(item.get("x"), VIEWPORT_WIDTH // 2))))
        fallback_y = max(0, min(VIEWPORT_HEIGHT - 1, int(_coerce_number(item.get("y"), VIEWPORT_HEIGHT // 2))))
        if not self._page:
            return (fallback_x, fallback_y)

        skemi_id = str(item.get("skemi_id") or "").strip()
        if not skemi_id:
            return (fallback_x, fallback_y)
        try:
            point = await self._page.evaluate(
                """(targetId) => {
                    const escaped = (window.CSS && typeof CSS.escape === 'function')
                        ? CSS.escape(String(targetId))
                        : String(targetId).replace(/["\\\\]/g, '\\\\$&');
                    const node = document.querySelector(`[data-skemi-id="${escaped}"]`);
                    if (!(node instanceof HTMLElement)) return null;
                    node.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                    const rect = node.getBoundingClientRect();
                    if (rect.width < 2 || rect.height < 2) return null;
                    return {
                        x: Math.round(rect.left + (rect.width / 2)),
                        y: Math.round(rect.top + (rect.height / 2)),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    };
                }""",
                skemi_id,
            )
            if point:
                return (
                    max(0, min(VIEWPORT_WIDTH - 1, int(_coerce_number(point.get("x"), fallback_x)))),
                    max(0, min(VIEWPORT_HEIGHT - 1, int(_coerce_number(point.get("y"), fallback_y)))),
                )
        except Exception:
            pass
        return (fallback_x, fallback_y)

    async def _verify_point_matches_target(
        self,
        target_x: int,
        target_y: int,
        item: Optional[Dict[str, Any]],
        params: Dict[str, Any],
    ) -> bool:
        if not self._page:
            return True
        expected_id = str((item or {}).get("skemi_id") or params.get("skemi_id") or "").strip()
        expected_text = _normalize_label(
            (item or {}).get("text")
            or (item or {}).get("aria_label")
            or params.get("target_text")
            or params.get("label")
            or params.get("target_label")
            or params.get("text")
        )
        try:
            hit = await self._page.evaluate(
                """({x, y}) => {
                    const el = document.elementFromPoint(x, y);
                    if (!(el instanceof HTMLElement)) return null;
                    const target = el.closest('[data-skemi-id]') || el;
                    return {
                        skemi_id: String(target.getAttribute('data-skemi-id') || ''),
                        tag: (target.tagName || '').toLowerCase(),
                        role: (target.getAttribute('role') || '').toLowerCase(),
                        text: (
                            (target.innerText || target.textContent || '') + ' ' +
                            (target.getAttribute('aria-label') || '') + ' ' +
                            (target.getAttribute('placeholder') || '')
                        ).replace(/\\s+/g, ' ').trim().slice(0, 200)
                    };
                }""",
                {"x": target_x, "y": target_y},
            )
        except Exception:
            return not expected_text

        if not hit:
            return False
        hit_id = str(hit.get("skemi_id") or "").strip()
        if expected_id and hit_id and hit_id == expected_id:
            return True
        hit_text = _normalize_label(hit.get("text"))
        if expected_text and hit_text and expected_text in hit_text:
            return True
        return not expected_text

    async def _focus_snapshot_item(self, item: Optional[Dict[str, Any]]) -> tuple[int, int]:
        point = await self._live_point_for_snapshot_item(item)
        if point is None:
            return (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2)
        target_x, target_y = point
        await self.click_at(target_x, target_y)
        return (target_x, target_y)

    async def _dom_click_snapshot_item(self, item: Optional[Dict[str, Any]]) -> bool:
        if not self._page or not item:
            return False
        skemi_id = str(item.get("skemi_id") or "").strip()
        if not skemi_id:
            return False
        try:
            clicked = await self._page.evaluate(
                """(targetId) => {
                    const escaped = (window.CSS && typeof CSS.escape === 'function')
                        ? CSS.escape(String(targetId))
                        : String(targetId).replace(/["\\\\]/g, '\\\\$&');
                    const el = document.querySelector(`[data-skemi-id="${escaped}"]`);
                    if (!(el instanceof HTMLElement)) return false;
                    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                    el.focus?.();
                    const target = el.closest('button,a,label,[role="button"]') || el;
                    if (typeof target.click === 'function') {
                        target.click();
                        return true;
                    }
                    return false;
                }""",
                skemi_id,
            )
            return bool(clicked)
        except Exception:
            return False

    async def _dom_fill_snapshot_item(self, item: Optional[Dict[str, Any]], text_value: str) -> bool:
        if not self._page or not item:
            return False
        skemi_id = str(item.get("skemi_id") or "").strip()
        if not skemi_id:
            return False
        try:
            filled = await self._page.evaluate(
                """({ targetId, value }) => {
                    const escaped = (window.CSS && typeof CSS.escape === 'function')
                        ? CSS.escape(String(targetId))
                        : String(targetId).replace(/["\\\\]/g, '\\\\$&');
                    const el = document.querySelector(`[data-skemi-id="${escaped}"]`);
                    if (!(el instanceof HTMLElement)) return false;
                    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                    el.focus?.();
                    if ('value' in el) {
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    if (el.isContentEditable) {
                        el.textContent = value;
                        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
                        return true;
                    }
                    return false;
                }""",
                {"targetId": skemi_id, "value": text_value},
            )
            return bool(filled)
        except Exception:
            return False

    async def _dispatch_prompt_if_ready(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, int]]:
        if not self.prompt_text or self.prompt_dispatched or not _is_known_chat_surface(self.current_url):
            return None

        direct_input = await self._known_chat_input_locator()
        if direct_input is not None:
            target_x, target_y = await self._fill_locator_direct(direct_input, self.prompt_text)
            await asyncio.sleep(0.08)
            direct_send = await self._known_chat_send_locator()
            if direct_send is not None:
                target_x, target_y = await self._click_locator_direct(direct_send)
            else:
                await self.press_key("Enter")

            self.prompt_dispatched = True
            self.history.append(
                _ui_text(
                    self.user_language,
                    f'Đã gửi câu hỏi tới {self.site_name}: "{self.prompt_text}"',
                    f'Submitted the question to {self.site_name}: "{self.prompt_text}"',
                )
            )
            self.last_verification = _ui_text(
                self.user_language,
                "Mong thấy cuộc trò chuyện bắt đầu và câu trả lời của AI xuất hiện.",
                "Expect the conversation to start and the AI answer to appear.",
            )
            self.prompt_dispatched_at = time.time()
            await self._persist_storage_state()
            return {"x": target_x, "y": target_y}

        input_item = self._find_chat_input_item(snapshot)
        if not input_item:
            return None

        params = {
            "skemi_id": input_item.get("skemi_id"),
            "text": self.prompt_text,
            "placeholder": input_item.get("placeholder"),
            "label": input_item.get("aria_label") or input_item.get("text"),
        }
        target_x, target_y = await self._fill_target(params)
        await asyncio.sleep(0.2)

        refreshed = await self.dom_snapshot()
        submit_item = self._find_submit_item(refreshed)
        if submit_item and submit_item.get("skemi_id"):
            target_x, target_y = await self._click_target({"skemi_id": submit_item.get("skemi_id")})
        else:
            await self.press_key("Enter")

        self.prompt_dispatched = True
        self.history.append(
            _ui_text(
                self.user_language,
                f'Đã gửi câu hỏi tới {self.site_name}: "{self.prompt_text}"',
                f'Submitted the question to {self.site_name}: "{self.prompt_text}"',
            )
        )
        self.last_verification = _ui_text(
            self.user_language,
            "Mong thấy cuộc trò chuyện bắt đầu và câu trả lời của AI xuất hiện.",
            "Expect the conversation to start and the AI answer to appear.",
        )
        self.prompt_dispatched_at = time.time()
        await self._persist_storage_state()
        return {"x": target_x, "y": target_y}

    async def _extract_known_chat_answer(self) -> str:
        if not self._page or not self.prompt_dispatched or not _is_known_chat_surface(self.current_url):
            return ""

        host = _domain_name(self.current_url)
        root_selectors = ["main"]
        ignore_exact = [
            "Gemini",
            "ChatGPT",
            "Claude",
            "Hỏi Gemini",
            "Message ChatGPT",
            "Talk to Claude",
            "Đăng nhập",
            "Sign in",
            "Log in",
            "Công cụ",
            "Tools",
            "Nhanh",
            "Fast",
            "Viết",
            "Lên kế hoạch",
            "Nghiên cứu",
            "Học tập",
            "New chat",
        ]
        ignore_prefixes = [
            "Giới thiệu về Gemini",
            "Ứng dụng Gemini",
            "Gói thuê bao",
            "Cho doanh nghiệp",
            "Gemini có thể mắc sai sót",
            "By messaging ChatGPT",
            "ChatGPT can make mistakes",
            "Claude can make mistakes",
            "Continue with Google",
            "Chúng tôi sử dụng cookie",
            "Quản lý cookie",
            "Từ chối cookie không thiết yếu",
            "Chấp nhận tất cả",
            "Nhận phản hồi phù hợp",
            "Đăng nhập để nhận câu trả lời",
        ]

        if "chatgpt.com" in host:
            root_selectors = ["main", "article", "[data-testid='conversation-turn-0']"]
        elif "claude.ai" in host:
            root_selectors = ["main", "section", "article"]

        try:
            if "chatgpt.com" in host:
                assistant_only = await self._page.evaluate(
                    """
                    ({ promptText }) => {
                        const normalize = (value) =>
                            String(value || "")
                                .replace(/\u00a0/g, " ")
                                .replace(/\s+/g, " ")
                                .trim();
                        const fold = (value) =>
                            normalize(value)
                                .normalize("NFD")
                                .replace(/[\u0300-\u036f]/g, "")
                                .toLowerCase();
                        const promptFold = fold(promptText);
                        const ignoreFragments = [
                            "chatgpt can make mistakes",
                            "by messaging chatgpt",
                            "cookie",
                            "quản lý cookie",
                            "quan ly cookie",
                            "đăng nhập",
                            "dang nhap",
                            "sign in",
                            "log in",
                        ];
                        const visible = (el) => {
                            if (!(el instanceof HTMLElement)) return false;
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width >= 4
                                && rect.height >= 4;
                        };
                        const nodes = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
                        const messages = [];
                        for (const node of nodes) {
                            if (!visible(node)) continue;
                            const text = normalize(node.innerText || node.textContent || "");
                            const folded = fold(text);
                            if (!text || text.length < 40 || !folded) continue;
                            if (promptFold && folded === promptFold) continue;
                            if (ignoreFragments.some(fragment => folded.includes(fragment))) continue;
                            messages.push(text);
                        }
                        return messages.length ? messages[messages.length - 1] : "";
                    }
                    """,
                    {"promptText": self.prompt_text},
                )
                assistant_only = _trim_result_text(assistant_only, limit=2400)
                if len(assistant_only) >= 80:
                    return assistant_only

            raw_text = await self._page.evaluate(
                """
                ({ rootSelectors, ignoreExact, ignorePrefixes, promptText }) => {
                    const normalize = (value) =>
                        String(value || "")
                            .replace(/\u00a0/g, " ")
                            .replace(/\s+/g, " ")
                            .trim();
                    const fold = (value) =>
                        normalize(value)
                            .normalize("NFD")
                            .replace(/[\u0300-\u036f]/g, "")
                            .toLowerCase();
                    const promptFold = fold(promptText);
                    const ignoreExactFold = ignoreExact.map(fold);
                    const ignorePrefixFold = ignorePrefixes.map(fold);
                    const isVisible = (el) => {
                        if (!(el instanceof HTMLElement)) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none"
                            && style.visibility !== "hidden"
                            && rect.width >= 4
                            && rect.height >= 4
                            && rect.bottom >= 0
                            && rect.right >= 0
                            && rect.top <= (window.innerHeight || 800)
                            && rect.left <= (window.innerWidth || 1280);
                    };
                    const roots = [];
                    for (const selector of rootSelectors) {
                        const element = document.querySelector(selector);
                        if (element && isVisible(element)) roots.push(element);
                    }
                    if (!roots.length) {
                        const fallback = document.querySelector("main") || document.body;
                        if (fallback) roots.push(fallback);
                    }
                    const ignoreSelector = "script,style,noscript,nav,header,footer,aside,form,textarea,input,button,select,dialog,[contenteditable='true']";
                    const lines = [];
                    const seen = new Set();
                    const addLine = (rawValue) => {
                        const text = normalize(rawValue);
                        if (!text || text.length < 2) return;
                        const folded = fold(text);
                        if (!folded) return;
                        if (promptFold) {
                            if (folded === promptFold) return;
                            if (folded.includes(promptFold) && Math.abs(folded.length - promptFold.length) <= 20) return;
                        }
                        if (ignoreExactFold.includes(folded)) return;
                        if (ignorePrefixFold.some((prefix) => prefix && folded.startsWith(prefix))) return;
                        if (seen.has(folded)) return;
                        seen.add(folded);
                        lines.push(text);
                    };
                    for (const root of roots) {
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
                            acceptNode(node) {
                                const parent = node.parentElement;
                                if (!parent || !isVisible(parent)) return NodeFilter.FILTER_REJECT;
                                if (parent.closest(ignoreSelector)) return NodeFilter.FILTER_REJECT;
                                const text = normalize(node.textContent || "");
                                if (!text) return NodeFilter.FILTER_REJECT;
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        });
                        let node = walker.nextNode();
                        while (node) {
                            addLine(node.textContent || "");
                            node = walker.nextNode();
                        }
                    }
                    return lines.join("\\n");
                }
                """,
                {
                    "rootSelectors": root_selectors,
                    "ignoreExact": ignore_exact,
                    "ignorePrefixes": ignore_prefixes,
                    "promptText": self.prompt_text,
                },
            )
        except Exception:
            return ""

        lines = []
        prompt_folded = _fold_text(self.prompt_text)
        for raw_line in str(raw_text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" \t-•")
            if len(line) < 2:
                continue
            folded = _fold_text(line)
            if prompt_folded and (folded == prompt_folded or (prompt_folded in folded and abs(len(folded) - len(prompt_folded)) <= 20)):
                continue
            if folded in {"gemini", "chatgpt", "claude"}:
                continue
            if lines and _fold_text(lines[-1]) == folded:
                continue
            lines.append(line)

        cleaned = _trim_result_text("\n".join(lines))
        if len(cleaned) < 60 and "\n" not in cleaned:
            return ""
        return cleaned

    async def _known_chat_generation_active(self) -> bool:
        if not self._page or not _is_known_chat_surface(self.current_url):
            return False
        host = _domain_name(self.current_url)
        try:
            return bool(await self._page.evaluate(
                """(host) => {
                    const visible = (el) => {
                        if (!(el instanceof HTMLElement)) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none"
                            && style.visibility !== "hidden"
                            && rect.width >= 4
                            && rect.height >= 4;
                    };
                    const selectors = [];
                    if (host.includes("chatgpt.com")) {
                        selectors.push('[data-testid="stop-button"]', 'button[aria-label*="Stop"]', 'button[aria-label*="Dừng"]');
                    } else if (host.includes("gemini.google.com")) {
                        selectors.push('button[aria-label*="Stop"]', 'button[aria-label*="Dừng"]', 'button[mattooltip*="Stop"]');
                    } else if (host.includes("claude.ai")) {
                        selectors.push('button[aria-label*="Stop"]', 'button[aria-label*="Dừng"]');
                    }
                    for (const selector of selectors) {
                        const node = document.querySelector(selector);
                        if (node && visible(node)) return true;
                    }
                    return false;
                }""",
                host,
            ))
        except Exception:
            return False

    async def _extract_generic_page_result(self) -> str:
        if not self._page:
            return ""
        try:
            raw_text = await self._page.evaluate(
                """
                () => {
                    const normalize = (value) =>
                        String(value || "")
                            .replace(/\\u00a0/g, " ")
                            .replace(/\\s+/g, " ")
                            .trim();
                    const selectors = ["main", "article", "section", "[role='main']", "body"];
                    const roots = [];
                    for (const selector of selectors) {
                        const node = document.querySelector(selector);
                        if (node instanceof HTMLElement) {
                            roots.push(node);
                        }
                    }
                    const seen = new Set();
                    const lines = [];
                    for (const root of roots) {
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                        let current = walker.nextNode();
                        while (current) {
                            const parent = current.parentElement;
                            if (parent instanceof HTMLElement) {
                                const style = window.getComputedStyle(parent);
                                const rect = parent.getBoundingClientRect();
                                const visible = style.display !== "none" && style.visibility !== "hidden" && rect.width >= 4 && rect.height >= 4;
                                if (visible) {
                                    const text = normalize(current.textContent || "");
                                    if (text.length >= 12) {
                                        const folded = text.toLowerCase();
                                        if (!seen.has(folded)) {
                                            seen.add(folded);
                                            lines.push(text);
                                        }
                                    }
                                }
                            }
                            current = walker.nextNode();
                        }
                        if (lines.length >= 20) break;
                    }
                    return lines.slice(0, 20).join("\\n");
                }
                """
            )
        except Exception:
            return ""
        cleaned = _trim_result_text(raw_text, limit=1800)
        return cleaned if len(cleaned) >= 80 else ""

    async def _maybe_finish_known_chat_prompt(self, step_num: int, current_image: str) -> Optional[Dict[str, Any]]:
        if not self.prompt_dispatched or not _is_known_chat_surface(self.current_url):
            return None

        if await self._known_chat_generation_active():
            self.result_stable_count = 0
            return None

        extracted = await self._extract_known_chat_answer()
        if not extracted:
            self.result_stable_count = 0
            return None

        folded = _fold_text(extracted)
        if folded and folded == _fold_text(self.latest_result_text):
            self.result_stable_count += 1
        else:
            self.latest_result_text = extracted
            self.result_stable_count = 1

        enough_content = len(extracted) >= 120 or extracted.count("\n") >= 2
        waited_enough = self.prompt_dispatched_step and (step_num - self.prompt_dispatched_step) >= 3
        stable_enough = self.result_stable_count >= 2
        if enough_content and (stable_enough or waited_enough):
            return {
                "step": step_num,
                "image": current_image,
                "description": _ui_text(self.user_language, "Đã lấy được kết quả từ trang.", "Captured the result from the page."),
                "result": extracted,
            }
        return None

    def _find_snapshot_item(self, params: Dict[str, Any], action_type: str) -> Optional[Dict[str, Any]]:
        snapshot_items = list((self.last_dom_snapshot or {}).get("items") or [])
        if not snapshot_items:
            return None

        skemi_id = str(params.get("skemi_id") or "").strip()
        if skemi_id:
            for item in snapshot_items:
                if str(item.get("skemi_id")) == skemi_id:
                    return item

        preferred = [
            params.get("target_text"),
            params.get("label"),
            params.get("target_label"),
            params.get("placeholder"),
            params.get("name"),
        ]
        if action_type != "type":
            preferred.append(params.get("text"))

        needle = _normalize_label(next((value for value in preferred if value), ""))
        role_filter = _normalize_label(params.get("role"))
        if needle:
            candidates = []
            for item in snapshot_items:
                if role_filter and role_filter not in _normalize_label(item.get("role")):
                    continue
                haystack = " ".join(
                    _normalize_label(item.get(key))
                    for key in ("text", "aria_label", "placeholder", "name", "id", "href")
                ).strip()
                if not haystack or needle not in haystack:
                    continue
                score = len(needle)
                if haystack.startswith(needle):
                    score += 10
                if item.get("tag") in {"button", "input", "textarea", "select"}:
                    score += 5
                candidates.append((score, item))
            if candidates:
                candidates.sort(key=lambda pair: pair[0], reverse=True)
                if len(candidates) >= 2 and abs(candidates[0][0] - candidates[1][0]) <= 2:
                    return None
                return candidates[0][1]

        if params.get("x") is not None and params.get("y") is not None:
            target_x, target_y = _resolve_point(params, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            hinted_text = _normalize_label(
                params.get("target_text")
                or params.get("label")
                or params.get("target_label")
                or params.get("text")
                or ""
            )
            role_hint = _normalize_label(params.get("role"))
            scored_hits = []
            for item in snapshot_items:
                if item.get("disabled"):
                    continue
                item_role = _normalize_label(item.get("role"))
                if role_hint and role_hint not in item_role and role_hint not in _normalize_label(item.get("tag")):
                    continue

                left = int(item.get("left") or 0)
                top = int(item.get("top") or 0)
                width = max(0, int(item.get("width") or 0))
                height = max(0, int(item.get("height") or 0))
                center_x = int(item.get("x") or 0)
                center_y = int(item.get("y") or 0)
                if width < 4 or height < 4:
                    continue

                inside = left <= target_x <= (left + width) and top <= target_y <= (top + height)
                distance = abs(center_x - target_x) + abs(center_y - target_y)
                if not inside and distance > 120:
                    continue

                text_haystack = " ".join(
                    _normalize_label(item.get(key))
                    for key in ("text", "aria_label", "placeholder", "name", "id", "href")
                ).strip()
                text_bonus = 0
                if hinted_text and text_haystack:
                    if hinted_text in text_haystack:
                        text_bonus += 48
                    text_bonus += _token_overlap_score(hinted_text, text_haystack) * 8

                type_bonus = 0
                tag = str(item.get("tag") or "").lower()
                if action_type == "click":
                    if tag in {"button", "a", "summary"}:
                        type_bonus += 26
                    if item_role in {"button", "link"}:
                        type_bonus += 18
                    if tag in {"input", "textarea", "select"}:
                        type_bonus += 8
                elif action_type == "type":
                    if tag in {"input", "textarea", "select"}:
                        type_bonus += 42
                    if item_role in {"textbox", "searchbox", "combobox"}:
                        type_bonus += 26
                    if item.get("placeholder"):
                        type_bonus += 10

                area_penalty = min(80, (width * height) // 5000)
                score = (
                    (220 if inside else max(0, 120 - distance))
                    + type_bonus
                    + text_bonus
                    - area_penalty
                )
                scored_hits.append((score, distance, area_penalty, item))

            if scored_hits:
                scored_hits.sort(key=lambda row: (row[0], -row[1], -row[2]), reverse=True)
                top_score = scored_hits[0][0]
                if len(scored_hits) == 1 or top_score >= (scored_hits[1][0] + 12):
                    return scored_hits[0][3]

        if action_type == "type":
            active = (self.last_dom_snapshot or {}).get("active") or {}
            active_id = str(active.get("skemi_id") or "").strip()
            if active_id:
                for item in snapshot_items:
                    if str(item.get("skemi_id")) == active_id:
                        return item
            for item in snapshot_items:
                if item.get("tag") in {"input", "textarea", "select"} and not item.get("disabled"):
                    return item
        return None

    async def _locator_from_params(self, params: Dict[str, Any], action_type: str):
        if not self._page:
            return None

        item = self._find_snapshot_item(params, action_type)
        memory_keys = self._selector_memory_keys(params, action_type, item)
        selector = str(params.get("selector") or "").strip()
        if selector:
            locator = await self._first_visible_locator([selector], memory_keys=memory_keys)
            if locator is not None:
                return locator

        if item and item.get("skemi_id"):
            try:
                locator = self._page.locator(f'[data-skemi-id="{item["skemi_id"]}"]').first
                if await locator.count() and await locator.is_visible(timeout=400):
                    return locator
            except Exception:
                pass

        candidate_selectors = []
        candidate_selectors.extend(self._selector_candidates_from_item(item))

        placeholder = str(params.get("placeholder") or "").strip()
        if placeholder:
            candidate_selectors.extend([
                _css_attr_selector("placeholder", placeholder, "textarea"),
                _css_attr_selector("placeholder", placeholder, "input"),
            ])

        label = str(
            params.get("target_text")
            or params.get("label")
            or params.get("target_label")
            or ""
        ).strip()
        if label and len(label) <= 80:
            candidate_selectors.extend([
                _has_text_selector("button", label),
                _has_text_selector("a", label),
                _has_text_selector('[role="button"]', label),
                _has_text_selector("label", label),
            ])

        locator = await self._first_visible_locator(candidate_selectors, memory_keys=memory_keys)
        if locator is not None:
            return locator

        return None

    async def _click_target(self, params: Dict[str, Any]) -> tuple[int, int]:
        item = self._find_snapshot_item(params, "click")
        locator = await self._locator_from_params(params, "click")
        if locator is not None:
            try:
                return await self._click_locator_direct(locator)
            except Exception:
                pass

        if item is not None:
            point = await self._live_point_for_snapshot_item(item)
            target_x, target_y = point or _resolve_point(params, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            clicked = await self._dom_click_snapshot_item(item)
            if clicked:
                return target_x, target_y
        else:
            target_x, target_y = _resolve_point(params, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
        if (self.last_dom_snapshot or {}).get("items"):
            hit_ok = await self._verify_point_matches_target(target_x, target_y, item, params)
            if not hit_ok:
                raise RuntimeError("Click was blocked because Skemi could not verify the intended target at that position.")
        await self.click_at(target_x, target_y)
        return target_x, target_y

    async def _fill_target(self, params: Dict[str, Any]) -> tuple[int, int]:
        text_value = str(params.get("text") or params.get("value") or "")
        item = self._find_snapshot_item(params, "type")
        locator = await self._locator_from_params(params, "type")
        if locator is not None:
            try:
                return await self._fill_locator_direct(locator, text_value)
            except Exception:
                pass

        if item is None and _is_known_chat_surface(self.current_url):
            chat_item = self._find_chat_input_item(self.last_dom_snapshot or {})
            if chat_item is not None:
                item = chat_item
            else:
                known_chat_locator = await self._known_chat_input_locator()
                if known_chat_locator is not None:
                    try:
                        return await self._fill_locator_direct(known_chat_locator, text_value)
                    except Exception:
                        pass

        if item is not None:
            point = await self._live_point_for_snapshot_item(item)
            target_x, target_y = point or _resolve_point(params, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            if await self._dom_fill_snapshot_item(item, text_value):
                return target_x, target_y
            target_x, target_y = await self._focus_snapshot_item(item)
            await asyncio.sleep(0.04)
            await self.type_text(text_value)
            return target_x, target_y

        active = (self.last_dom_snapshot or {}).get("active") or {}
        active_tag = str(active.get("tag") or "").lower()
        has_active_target = active_tag in {"input", "textarea", "select"} or bool(active.get("skemi_id"))
        if not has_active_target and _is_known_chat_surface(self.current_url):
            snapshot = self.last_dom_snapshot or {}
            fallback_chat_item = self._find_chat_input_item(snapshot)
            if fallback_chat_item is not None:
                target_x, target_y = await self._focus_snapshot_item(fallback_chat_item)
                await asyncio.sleep(0.05)
                await self.type_text(text_value)
                return target_x, target_y
            known_chat_locator = await self._known_chat_input_locator()
            if known_chat_locator is not None:
                return await self._fill_locator_direct(known_chat_locator, text_value)
        if not has_active_target and not text_value:
            raise RuntimeError("Typing was blocked because there is no precise active input target.")
        if not has_active_target and not active.get("text") and not active.get("placeholder"):
            raise RuntimeError("Typing was blocked because Skemi could not verify a focused input field.")

        await self.type_text(text_value)
        return _resolve_point(params, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)

    def _snapshot_signature(self, snapshot: Dict[str, Any]) -> str:
        snapshot = snapshot or {}
        active = snapshot.get("active") or {}
        scroll = snapshot.get("scroll") or {}
        parts = [
            str(snapshot.get("title") or ""),
            str(snapshot.get("url") or ""),
            str(active.get("skemi_id") or ""),
            str(active.get("tag") or ""),
            str(scroll.get("y") or 0),
            _fold_text(str(snapshot.get("body_text") or "")[:420]),
        ]
        return "|".join(parts)

    def _snapshot_changed(self, before: Dict[str, Any], after: Dict[str, Any]) -> bool:
        return self._snapshot_signature(before) != self._snapshot_signature(after)

    async def _verify_fill_result(self, params: Dict[str, Any], expected_text: str) -> bool:
        expected_fold = _fold_text(expected_text)
        if not expected_fold:
            return True
        locator = await self._locator_from_params(params, "type")
        if locator is None:
            return False
        try:
            content = await locator.evaluate(
                """(el) => {
                    if ('value' in el) return String(el.value || '');
                    if (el.isContentEditable) return String(el.innerText || el.textContent || '');
                    return String(el.textContent || '');
                }"""
            )
            return expected_fold in _fold_text(content)
        except Exception:
            return False

    async def _retry_action_if_needed(
        self,
        action_type: str,
        params: Dict[str, Any],
        before_snapshot: Dict[str, Any],
        before_url: str,
    ) -> bool:
        if action_type not in {"click", "type"}:
            return False
        after_snapshot = await self.dom_snapshot()
        url_changed = str(before_url or "") != str(self.current_url or "")
        if action_type == "type":
            expected = str(params.get("text") or params.get("value") or "")
            if await self._verify_fill_result(params, expected):
                return False
            locator = await self._locator_from_params(params, "type")
            if locator is None:
                return False
            await self._fill_locator_direct(locator, expected)
            await asyncio.sleep(0.08)
            return True
        if url_changed or self._snapshot_changed(before_snapshot, after_snapshot):
            return False
        locator = await self._locator_from_params(params, "click")
        if locator is None:
            return False
        await self._click_locator_direct(locator)
        await asyncio.sleep(0.08)
        return True

    def _requires_confirmation(self, action_type: str, params: Dict[str, Any]) -> Optional[str]:
        if self.bypass_safety:
            return None
        if action_type not in {"click", "type", "press", "navigate"}:
            return None
        snapshot_item = self._find_snapshot_item(params, action_type)
        target_parts = [
            self.command,
            self.current_url,
            params.get("url"),
            params.get("text"),
            params.get("target_text"),
            params.get("label"),
            params.get("placeholder"),
            (snapshot_item or {}).get("text"),
            (snapshot_item or {}).get("aria_label"),
            (self.last_dom_snapshot or {}).get("title"),
            (self.last_dom_snapshot or {}).get("body_text"),
        ]
        host = _domain_name(self.current_url)
        sensitive_host = any(token in host for token in (
            "account",
            "billing",
            "bank",
            "wallet",
            "paypal",
            "stripe",
            "admin",
            "settings",
            "security",
        ))
        if sensitive_host or _contains_sensitive_terms(*target_parts):
            action_label = {
                "click": "nhan nut/duong dan",
                "type": "nhap du lieu",
                "press": "bam phim chuc nang",
                "navigate": "mo trang moi",
            }.get(action_type, "thao tac")
            target_label = str(
                (snapshot_item or {}).get("text")
                or params.get("target_text")
                or params.get("label")
                or params.get("url")
                or self.current_url
            ).strip()
            return f"Tac vu nhay cam ({action_label}) co the anh huong toi tai khoan, he thong hoac du lieu quan trong: {target_label or 'muc tieu quan trong'}."
        return None

    async def _request_confirmation(self, reason: str, action_type: str, params: Dict[str, Any], description: str) -> bool:
        self.pending_confirmation = {
            "reason": reason,
            "action_type": action_type,
            "description": description,
            "params": params,
            "requested_at": time.time(),
        }
        self._confirmation_approved = False
        self._confirmation_event.clear()
        return True

    async def wait_for_confirmation(self) -> bool:
        while not self.cancelled:
            await self._confirmation_event.wait()
            approved = self._confirmation_approved
            self._confirmation_event.clear()
            if approved:
                self.pending_confirmation = None
                return True
            self.pending_confirmation = None
            return False
        return False

    def resolve_confirmation(self, approved: bool) -> bool:
        if not self.pending_confirmation:
            return False
        self._confirmation_approved = bool(approved)
        self._confirmation_event.set()
        return True

    async def request_manual_takeover(self, reason: str, description: str, takeover_type: str = "manual_verification") -> bool:
        self.pending_manual_takeover = {
            "reason": str(reason or "").strip(),
            "description": str(description or "").strip(),
            "takeover_type": str(takeover_type or "manual_verification").strip(),
            "requested_at": time.time(),
        }
        self._manual_resume_event.clear()
        return True

    async def wait_for_manual_resume(self) -> bool:
        while not self.cancelled and self.pending_manual_takeover:
            try:
                await asyncio.wait_for(self._manual_resume_event.wait(), timeout=0.45)
            except asyncio.TimeoutError:
                if await self._manual_takeover_cleared():
                    self.pending_manual_takeover = None
                    await self._persist_storage_state()
                    return True
                continue
            self._manual_resume_event.clear()
            if self.cancelled:
                return False
            if not self.pending_manual_takeover:
                await self._persist_storage_state()
                return True
        return not self.cancelled

    def resume_manual_takeover(self) -> bool:
        if not self.pending_manual_takeover:
            return False
        self.pending_manual_takeover = None
        self._manual_resume_event.set()
        return True

    async def _manual_takeover_cleared(self) -> bool:
        takeover = dict(self.pending_manual_takeover or {})
        if not takeover or not self._page:
            return False
        try:
            self.current_url = self._page.url or self.current_url
        except Exception:
            pass

        snapshot = await self.dom_snapshot()
        dom_text = _normalize_label((snapshot or {}).get("body_text"))
        current_url = str(self.current_url or "")
        takeover_type = str(takeover.get("takeover_type") or "").strip().lower()

        captcha_markers = (
            "google.com/sorry" in current_url.lower()
            or "recaptcha" in dom_text
            or "cloudflare" in dom_text
            or "khong phai la nguoi may" in dom_text
            or "xac minh ban la con nguoi" in dom_text
            or "verify you are human" in dom_text
        )
        if takeover_type == "captcha":
            if captcha_markers:
                return False
            if self.prompt_text and _is_known_chat_surface(current_url):
                if self._find_chat_input_item(snapshot):
                    return True
                if _looks_like_auth_wall(current_url, snapshot):
                    return False
            return True

        if takeover_type == "auth_wall":
            if self.prompt_text and _is_known_chat_surface(current_url):
                return bool(self._find_chat_input_item(snapshot))
            return not _looks_like_auth_wall(current_url, snapshot)

        return False

    async def _stream_preview(self, duration: float = 0.45, interval: float = 0.15) -> AsyncGenerator[str, None]:
        deadline = time.time() + max(0.0, duration)
        while time.time() < deadline and not self.cancelled:
            sc = self.latest_live_b64 or await self.screenshot(quality=LIVE_CAPTURE_QUALITY, store_in_history=False)
            if sc:
                yield sse_event("screenshot", {
                    "image": sc,
                    "url": self.current_url,
                    "surface_metrics": self._surface_metrics_payload(),
                }, silent=True)
            await asyncio.sleep(interval)

    async def _stream_preview_until_done(self, task: "asyncio.Task[str]", interval: float = 0.08) -> AsyncGenerator[str, None]:
        while not task.done() and not self.cancelled:
            sc = self.latest_live_b64 or await self.screenshot(quality=LIVE_CAPTURE_QUALITY, store_in_history=False)
            if sc:
                yield sse_event("screenshot", {
                    "image": sc,
                    "url": self.current_url,
                    "surface_metrics": self._surface_metrics_payload(),
                }, silent=True)
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def navigate(self, url: str):
        """Navigate to a URL."""
        if not await self._ensure_active_page():
            return
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            with contextlib.suppress(Exception):
                await self._page.wait_for_load_state("load", timeout=1200)
            with contextlib.suppress(Exception):
                await self._page.wait_for_load_state("networkidle", timeout=1200)
            self.current_url = self._page.url
            if self._native_browser_surface:
                await asyncio.sleep(0.18)
                await self._adopt_foreground_browser_window()
        except Exception as e:
            print(f"[COMPUTER AGENT] Navigate error: {e}")
            self.current_url = url

    async def click_at(self, x: int, y: int, click_count: int = 1):
        if not await self._ensure_active_page():
            return
        try:
            safe_x, safe_y = _resolve_point({"x": x, "y": y}, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            with contextlib.suppress(Exception):
                await self._page.bring_to_front()
            with contextlib.suppress(Exception):
                await self._page.evaluate("() => { try { window.focus(); } catch (e) {} }")
            await self._page.mouse.move(safe_x, safe_y, steps=10)
            await asyncio.sleep(0.028)
            if click_count <= 1:
                await self._page.mouse.down()
                await asyncio.sleep(0.026)
                await self._page.mouse.up()
            else:
                await self._page.mouse.click(safe_x, safe_y, click_count=click_count, delay=18)
        except Exception as e:
            print(f"[COMPUTER AGENT] Click error: {e}")

    async def hover_at(self, x: int, y: int):
        if not await self._ensure_active_page():
            return
        try:
            safe_x, safe_y = _resolve_point({"x": x, "y": y}, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            await self._page.mouse.move(safe_x, safe_y, steps=5)
        except Exception as e:
            print(f"[COMPUTER AGENT] Hover error: {e}")

    async def press_key(self, key: str):
        if not await self._ensure_active_page():
            return
        try:
            await self._page.keyboard.press(key)
        except Exception as e:
            print(f"[COMPUTER AGENT] Press key error: {e}")

    async def type_text(self, text: str):
        if not await self._ensure_active_page():
            return
        try:
            await self._human_type_into_active(text)
        except Exception as e:
            print(f"[COMPUTER AGENT] Type error: {e}")

    async def scroll(self, direction: str = "down"):
        if not await self._ensure_active_page():
            return
        try:
            multiplier = 1 if str(direction).lower() == "down" else -1
            target_x = VIEWPORT_WIDTH // 2
            target_y = max(120, min(VIEWPORT_HEIGHT - 120, int(VIEWPORT_HEIGHT * 0.55)))
            await self._page.mouse.move(target_x, target_y, steps=6)

            for delta in (220, 220, 180):
                await self._page.mouse.wheel(0, multiplier * delta)
                await asyncio.sleep(0.03)

            scroll_result = await self._page.evaluate(
                """(dir) => {
                    const direction = dir === 'down' ? 1 : -1;
                    const centerEl = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
                    const canScroll = (node) => {
                        if (!(node instanceof HTMLElement)) return false;
                        const style = window.getComputedStyle(node);
                        const overflowY = style.overflowY || '';
                        return /(auto|scroll|overlay)/.test(overflowY) && node.scrollHeight > node.clientHeight + 16;
                    };
                    let target = centerEl;
                    while (target && !canScroll(target)) target = target.parentElement;
                    target = target || document.scrollingElement || document.documentElement || document.body;
                    const before = target.scrollTop || window.scrollY || 0;
                    const amount = Math.max(260, Math.round((window.innerHeight || 800) * 0.72)) * direction;
                    if (typeof target.scrollBy === 'function') {
                        target.scrollBy({ top: amount, behavior: 'instant' });
                    } else {
                        target.scrollTop = before + amount;
                    }
                    const after = target.scrollTop || window.scrollY || 0;
                    return { before, after, changed: Math.abs(after - before) > 4 };
                }""",
                "down" if multiplier > 0 else "up",
            )

            if not (scroll_result or {}).get("changed"):
                await self._page.keyboard.press("PageDown" if multiplier > 0 else "PageUp")
        except Exception as e:
            print(f"[COMPUTER AGENT] Scroll error: {e}")

    async def manual_click(self, x: int, y: int, click_count: int = 1) -> Dict[str, Any]:
        if self.browser_shell == "virtual_window":
            page_point = self._capture_point_to_page(x, y)
            if not page_point:
                return {"ok": False, "reason": "outside_page_content"}
            page_x, page_y = page_point
            await self.click_at(page_x, page_y, click_count=max(1, int(click_count or 1)))
            return {"ok": True, "x": page_x, "y": page_y, "space": "page"}
        if self._native_browser_surface and self._resolve_browser_window_sync():
            capture_w, capture_h = self._browser_window_capture_size
            safe_x, safe_y = _resolve_point({"x": x, "y": y}, capture_w // 2 or 1, capture_h // 2 or 1, max(1, capture_w), max(1, capture_h))
            screen_x, screen_y = self._window_point_to_screen(safe_x, safe_y)
            success = await asyncio.to_thread(self._native_click_sync, screen_x, screen_y, max(1, int(click_count or 1)))
            return {"ok": bool(success), "x": safe_x, "y": safe_y, "screen_x": screen_x, "screen_y": screen_y}
        safe_x, safe_y = _resolve_point({"x": x, "y": y}, VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
        await self.click_at(safe_x, safe_y, click_count=max(1, int(click_count or 1)))
        return {"ok": True, "x": safe_x, "y": safe_y}

    async def manual_scroll(self, direction: str = "down") -> Dict[str, Any]:
        normalized = "up" if str(direction or "").lower().startswith("up") else "down"
        if self.browser_shell == "virtual_window":
            await self.scroll(normalized)
            return {"ok": True, "direction": normalized, "space": "page"}
        if self._native_browser_surface and self._resolve_browser_window_sync():
            capture_w, capture_h = self._browser_window_capture_size
            point_x = max(1, capture_w // 2)
            point_y = max(1, capture_h // 2)
            screen_x, screen_y = self._window_point_to_screen(point_x, point_y)
            success = await asyncio.to_thread(self._native_scroll_sync, normalized, screen_x, screen_y)
            return {"ok": bool(success), "direction": normalized}
        await self.scroll(normalized)
        return {"ok": True, "direction": normalized}

    async def manual_press(self, key: str) -> Dict[str, Any]:
        token = str(key or "").strip()
        if not token:
            return {"ok": False, "reason": "key_required"}
        if self.browser_shell == "virtual_window":
            await self.press_key(token)
            return {"ok": True, "key": token, "space": "page"}
        if self._native_browser_surface and self._resolve_browser_window_sync():
            success = await asyncio.to_thread(self._native_press_sync, token)
            return {"ok": bool(success), "key": token}
        await self.press_key(token)
        return {"ok": True, "key": token}

    async def manual_type(self, text: str) -> Dict[str, Any]:
        value = str(text or "")
        if not value:
            return {"ok": False, "reason": "text_required"}
        if self.browser_shell == "virtual_window":
            await self.type_text(value)
            return {"ok": True, "text_length": len(value), "space": "page"}
        if self._native_browser_surface and self._resolve_browser_window_sync():
            success = await asyncio.to_thread(self._native_type_sync, value)
            return {"ok": bool(success), "text_length": len(value)}
        await self.type_text(value)
        return {"ok": True, "text_length": len(value)}

    async def close(self):
        """Cleanup browser resources."""
        try:
            self.state = "closing"
            self.cancelled = True
            self._close_requested = True
            if self._cdp_session is not None:
                with contextlib.suppress(Exception):
                    await self._cdp_session.send("Page.stopScreencast")
                self._cdp_session = None
                self._cdp_screencast_enabled = False
            if self._live_capture_task:
                self._live_capture_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._live_capture_task
                self._live_capture_task = None
            if self._context:
                with contextlib.suppress(Exception):
                    await self._context.storage_state(path=self.storage_state_path)
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw_cm:
                await self._pw_cm.__aexit__(None, None, None)
        except Exception as e:
            print(f"[COMPUTER AGENT] Close error: {e}")
        finally:
            self._page = None
            self._tabs.clear()
            self._active_tab_id = ""
            self._context = None
            self._browser = None
            self._playwright = None
            self._pw_cm = None
            self._close_requested = False
            self.state = "closed"
            self._touch()
            active_sessions.pop(self.session_id, None)

    def request_cancel(self, reason: Optional[str] = None) -> None:
        self.cancelled = True
        if reason:
            self.stop_reason = str(reason)
        self._confirmation_event.set()
        self._manual_resume_event.set()
        if self._loop and self._execute_task and not self._execute_task.done():
            self._loop.call_soon_threadsafe(self._execute_task.cancel)
        if self._loop and not self._close_requested:
            self._close_requested = True
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self.close()))

    async def execute(self) -> AsyncGenerator[str, None]:
        """
        Main execution loop. Yields SSE event strings.
        1. Plan initial URL from command
        2. Navigate
        3. Screenshot → AI analyze → decide action → execute → repeat
        """
        try:
            self._execute_task = asyncio.current_task()
            self._loop = asyncio.get_running_loop()
            self.state = "running"
            self._touch()
            completed = False
            stopped_with_error = False
            final_message = _ui_text(self.user_language, "Phiên thao tác đã hoàn tất.", "The automation session is complete.")
            # Step 0: Launch browser
            yield sse_event("step", {
                "step": 0,
                "action": "launch",
                "description": "Khởi tạo Chromium browser...",
                "url": "",
            })

            await self.launch()

            yield sse_event("step", {
                "step": 0,
                "action": "launched",
                "description": "✅ Browser đã sẵn sàng",
                "url": "",
            })

            # Step 1: Determine start URL
            start_url = self.start_url or self.current_url or _build_browser_task_profile_v2(self.command).get("start_url", "")
            if (
                self.current_url
                and start_url
                and self.prompt_text
                and _is_known_chat_surface(self.current_url)
                and _domain_name(self.current_url) == _domain_name(start_url)
            ):
                start_url = self.current_url
            self.current_url = start_url
            continue_current_surface = bool(
                self.continue_current_surface
                and self._page is not None
                and self.current_url
                and start_url
                and _is_known_chat_surface(self.current_url)
                and _domain_name(self.current_url) == _domain_name(start_url)
            )

            if continue_current_surface:
                try:
                    self.current_url = self._page.url or self.current_url or start_url
                except Exception:
                    self.current_url = self.current_url or start_url
                yield sse_event("step", {
                    "step": 1,
                    "action": "reuse_surface",
                    "description": f"Tiếp tục ngay trên phiên {self.site_name or 'chat'} hiện tại",
                    "url": self.current_url,
                })
                await asyncio.sleep(0.18)
            else:
                yield sse_event("step", {
                    "step": 1,
                    "action": "navigate",
                    "description": f"Điều hướng đến {start_url}",
                    "url": start_url,
                })

                await self.navigate(start_url)
                await asyncio.sleep(1)  # Let page render

            # Take initial screenshot
            sc = await self.screenshot()
            if sc:
                yield sse_event("screenshot", {
                    "step": 1,
                    "image": sc,
                    "url": self.current_url,
                    "description": f"Đã mở: {self.current_url}",
                    "surface_metrics": self._surface_metrics_payload(),
                })
            initial_snapshot = await self.dom_snapshot()
            if initial_snapshot:
                yield sse_event("targets", {
                    "step": 1,
                    "items": _overlay_targets(initial_snapshot),
                    "url": self.current_url,
                    "title": str((initial_snapshot or {}).get("title") or ""),
                    "surface_metrics": self._surface_metrics_payload(),
                }, silent=True)

            self.step_count = 1

            navigation_only = (
                not self.prompt_text
                and _is_navigation_only_command(self.command)
                and not _dom_has_human_verification(self.current_url, _normalize_label((initial_snapshot or {}).get("body_text")))
            )
            if navigation_only:
                completed = True
                self.last_completed_at = time.time()
                final_message = _ui_text(
                    self.user_language,
                    f"Đã truy cập thành công vào {self.site_name or self.current_url or 'trang web'}.",
                    f"Successfully opened {self.site_name or self.current_url or 'the website'}.",
                )
                self.latest_result_text = str(final_message or "")
                yield sse_event("step", {
                    "step": 1,
                    "action": "ready",
                    "description": final_message,
                    "url": self.current_url,
                }, silent=True)

            # Step 2+: AI-driven action loop
            self.consecutive_observe = 0
            for step_num in range(2, MAX_STEPS + 1):
                if completed:
                    break
                if self.cancelled:
                    yield sse_event("stopped", {
                        "step": step_num,
                        "description": "⏹ Đã dừng theo yêu cầu",
                    })
                    final_message = _ui_text(self.user_language, "Đã dừng theo yêu cầu.", "Stopped as requested.")
                    break

                # Take screenshot for this step
                sc_for_analysis = await self.screenshot()
                if not sc_for_analysis: break
                dom_snapshot = await self.dom_snapshot()
                dom_summary = self._format_dom_summary(dom_snapshot)
                runtime_context = self._context_window_text(dom_snapshot, step_num=step_num)
                dom_text = _normalize_label((dom_snapshot or {}).get("body_text"))
                chat_ready_for_prompt = False
                if self.prompt_text and _is_known_chat_surface(self.current_url):
                    with contextlib.suppress(Exception):
                        chat_ready_for_prompt = await self._chat_surface_ready_for_prompt(dom_snapshot, self.current_url)
                yield sse_event("targets", {
                    "step": step_num,
                    "items": _overlay_targets(dom_snapshot),
                    "url": self.current_url,
                    "title": str((dom_snapshot or {}).get("title") or ""),
                    "surface_metrics": self._surface_metrics_payload(),
                }, silent=True)

                if _dom_has_human_verification(self.current_url, dom_text) and not chat_ready_for_prompt:
                    description = _ui_text(
                        self.user_language,
                        "Trang đang yêu cầu CAPTCHA/xác minh người dùng. Skemi giữ phiên browser và stream sống để bạn tự xác minh trực tiếp trên khung browser, rồi bấm 'Tiếp tục AI'.",
                        "This page requires CAPTCHA or human verification. Skemi is keeping the browser session and stream alive so you can verify directly in the browser viewport, then press 'Resume AI'.",
                    )
                    reason = _ui_text(
                        self.user_language,
                        "Skemi không tự vượt hoặc giải CAPTCHA. Bạn cần tự hoàn tất bước xác minh này.",
                        "Skemi will not solve or bypass CAPTCHA automatically. You need to complete this verification step yourself.",
                    )
                    await self.request_manual_takeover(reason, description, takeover_type="captcha")
                    yield sse_event("manual_takeover_required", {
                        "step": step_num,
                        "description": description,
                        "reason": reason,
                        "url": self.current_url,
                        "takeover_type": "captcha",
                    })
                    resumed = await self.wait_for_manual_resume()
                    if not resumed:
                        final_message = self.stop_reason
                        break
                    yield sse_event("manual_takeover_resumed", {
                        "step": step_num,
                        "description": _ui_text(
                            self.user_language,
                            "Đã nhận tín hiệu tiếp tục. Skemi đang tiếp tục từ phiên browser hiện tại.",
                            "Resume received. Skemi is continuing from the current browser session.",
                        ),
                        "url": self.current_url,
                    }, silent=True)
                    await asyncio.sleep(0.35)
                    self.step_count = step_num
                    continue

                chat_surface_ready = False
                if self.prompt_text and _is_known_chat_surface(self.current_url):
                    chat_surface_ready = await self._chat_surface_ready_for_prompt(dom_snapshot)

                if self.prompt_text and _is_known_chat_surface(self.current_url) and not chat_surface_ready and _looks_like_auth_wall(self.current_url, dom_snapshot):
                    description = _ui_text(
                        self.user_language,
                        f"Skemi đã vào {self.site_name} nhưng trang đang yêu cầu đăng nhập hoặc xác minh. Phiên browser vẫn đang mở để bạn tự xử lý rồi bấm 'Tiếp tục AI'.",
                        f"Skemi reached {self.site_name}, but the page requires sign-in or verification. The browser session is still open so you can handle it manually, then press 'Resume AI'.",
                    )
                    reason = _ui_text(
                        self.user_language,
                        "Trang hiện chưa sẵn sàng cho agent thao tác tiếp. Bạn cần hoàn tất đăng nhập hoặc xác minh thủ công.",
                        "The page is not ready for the agent yet. Please finish sign-in or verification manually first.",
                    )
                    await self.request_manual_takeover(reason, description, takeover_type="auth_wall")
                    yield sse_event("manual_takeover_required", {
                        "step": step_num,
                        "description": description,
                        "reason": reason,
                        "url": self.current_url,
                        "takeover_type": "auth_wall",
                    })
                    resumed = await self.wait_for_manual_resume()
                    if not resumed:
                        final_message = self.stop_reason
                        break
                    yield sse_event("manual_takeover_resumed", {
                        "step": step_num,
                        "description": _ui_text(
                            self.user_language,
                            "Đã tiếp tục sau khi bạn xử lý đăng nhập/xác minh thủ công.",
                            "Continuing after your manual sign-in or verification.",
                        ),
                        "url": self.current_url,
                    }, silent=True)
                    await asyncio.sleep(0.35)
                    self.step_count = step_num
                    continue

                if _dom_has_human_verification(self.current_url, dom_text):
                    stopped_with_error = True
                    yield sse_event("error", {
                        "step": step_num,
                        "message": _ui_text(
                            self.user_language,
                            "Trang đang yêu cầu CAPTCHA/xác minh người dùng. Skemi tạm dừng để bạn tiếp quản thủ công.",
                            "This page requires CAPTCHA or human verification. Skemi paused so you can take over manually.",
                        ),
                        "url": self.current_url,
                    })
                    break

                if self.prompt_text and _is_known_chat_surface(self.current_url) and not chat_surface_ready and _looks_like_auth_wall(self.current_url, dom_snapshot):
                    stopped_with_error = True
                    yield sse_event("error", {
                        "step": step_num,
                        "message": _ui_text(
                            self.user_language,
                            f"Skemi đã vào {self.site_name} nhưng trang đang yêu cầu đăng nhập hoặc xác minh. Bạn hãy đăng nhập/xác minh trước rồi chạy lại lệnh.",
                            f"Skemi reached {self.site_name}, but the page requires sign-in or verification. Please finish that step first, then run the command again.",
                        ),
                        "url": self.current_url,
                    })
                    break

                dispatched_point = await self._dispatch_prompt_if_ready(dom_snapshot)
                if dispatched_point:
                    if not self.prompt_dispatched_step:
                        self.prompt_dispatched_step = step_num
                    yield sse_event("step", {
                        "step": step_num,
                        "action": "type",
                        "url": self.current_url,
                        "x": dispatched_point["x"],
                        "y": dispatched_point["y"],
                    }, silent=True)
                    await asyncio.sleep(0.12)
                    async for preview_event in self._stream_preview(duration=0.65, interval=0.08):
                        yield preview_event
                    yield sse_event("targets", {
                        "step": step_num,
                        "items": _overlay_targets(await self.dom_snapshot()),
                        "url": self.current_url,
                        "title": str(((self.last_dom_snapshot or {}) or {}).get("title") or ""),
                        "surface_metrics": self._surface_metrics_payload(),
                    }, silent=True)
                    self.step_count = step_num
                    continue

                known_chat_result = await self._maybe_finish_known_chat_prompt(step_num, sc_for_analysis)
                if known_chat_result:
                    completed = True
                    final_message = known_chat_result.get("result") or _ui_text(
                        self.user_language,
                        "Đã lấy được kết quả từ trang.",
                        "Captured the result from the page.",
                    )
                    self.step_count = step_num
                    yield sse_event("screenshot", {
                        "step": step_num,
                        "image": known_chat_result.get("image") or sc_for_analysis,
                        "description": known_chat_result.get("description") or _ui_text(
                            self.user_language,
                            "Đã lấy được kết quả từ trang.",
                            "Captured the result from the page.",
                        ),
                        "surface_metrics": self._surface_metrics_payload(),
                    })
                    break

                if self.prompt_dispatched and self.prompt_dispatched_step and step_num - self.prompt_dispatched_step <= 2:
                    await asyncio.sleep(0.22)
                    async for preview_event in self._stream_preview(duration=0.7, interval=0.08):
                        yield preview_event
                    self.step_count = step_num
                    continue

                yield sse_event("step", {
                    "step": step_num,
                    "action": "analyzing",
                    "description": "🧠 AI đang suy luận bước tiếp theo...",
                    "url": self.current_url,
                }, silent=True)

                # Build Manus-style prompt
                history_str = "\n".join([f"- {h}" for h in self.history[-5:]])
                stuck_warning = (
                    "\n⚠️ LƯU Ý: Thao tác click/type trước đó có vẻ KHÔNG làm thay đổi nội dung màn hình. "
                    "Hãy kiểm tra lại tọa độ (phải nhắm đúng tâm chính giữa của nút/ô nhập) hoặc thử nhấn lệch đi một chút nếu cần."
                ) if self.last_action_stuck else ""
                
                verification_prompt = f"HÀNH ĐỘNG TRƯỚC ĐÓ: {self.history[-1] if self.history else 'Bắt đầu'}\nXÁC MINH CẦN KIỂM TRA: {self.last_verification}{stuck_warning}\n" if self.last_verification else ""
                
                dom_prompt = (
                    "You are Skemi Browser Operator. Plan the next browser action using DOM first and coordinates only as fallback.\n"
                    f"USER_LANGUAGE: {self.user_language}\n"
                    f"RAW_COMMAND: {self.command}\n"
                    f"GOAL: {self.execution_goal}\n"
                    f"CURRENT_URL: {self.current_url}\n"
                    f"START_URL: {self.start_url}\n"
                    f"PROMPT_TO_SUBMIT: {json.dumps(self.prompt_text, ensure_ascii=False)}\n"
                    f"RECENT_HISTORY:\n{history_str}\n\n"
                    f"{verification_prompt}"
                    f"RUNTIME_CONTEXT:\n{runtime_context}\n\n"
                    f"ACTIVE_ELEMENT: {json.dumps((dom_snapshot or {}).get('active') or {}, ensure_ascii=False)}\n"
                    f"DOM_ITEMS:\n{dom_summary or '[no actionable items]'}\n\n"
                    "Return JSON only with keys: thought, plan, action, params, verification, description.\n"
                    "If a target exists in DOM_ITEMS, always prefer params.skemi_id with that exact label id instead of x/y.\n"
                    "When params.skemi_id is available, do not also invent fallback x/y unless the target is truly off-DOM.\n"
                    "Use params.selector only when the target is clear but skemi_id is not stable.\n"
                    "For type actions, include params.text as the exact text to enter.\n"
                    "If PROMPT_TO_SUBMIT is not empty and a chat composer exists, prioritize typing that exact text and submitting it.\n"
                    "If content may be below the fold and can_scroll_down=true, use action=scroll before guessing coordinates.\n"
                    "When action=done, description must be the final user-facing result in USER_LANGUAGE with natural wording.\n"
                    "If the page relates to account, security, billing, payment, settings, admin, or deletion, avoid guessing and describe the exact target clearly.\n"
                    "If a click target is not unambiguous in DOM_ITEMS, do not guess; prefer scroll, wait, or a more precise skemi_id/selector.\n"
                    "Use x/y only when the target is completely missing from DOM_ITEMS.\n"
                    "Allowed actions: click, type, hover, press, scroll, navigate, wait, done.\n"
                )

                ai_prompt = (
                    "Bạn là Skemi Manus-style Agent. Bạn điều khiển trình duyệt bằng thị giác máy tính.\n"
                    f"MỤC TIÊU: \"{self.command}\"\n"
                    f"URL HIỆN TẠI: {self.current_url}\n"
                    f"LỊCH SỬ THAO TÁC GẦN ĐÂY:\n{history_str}\n\n"
                    f"{verification_prompt}"
                    f"RUNTIME_CONTEXT:\n{runtime_context}\n\n"
                    "NHIỆM VỤ: Hãy quan sát ảnh và phản hồi JSON để hoàn thành mục tiêu.\n\n"
                    "CẤU TRÚC JSON:\n"
                    "{\n"
                    "  \"thought\": \"Suy nghĩ chi tiết. Nếu đang bị kẹt (stuck), hãy giải thích tại sao và đề xuất tọa độ mới chuẩn xác hơn.\",\n"
                    "  \"plan\": [\"Bước tới 1\", \"Bước tới 2\", ...],\n"
                    "  \"action\": \"click|type|hover|press|scroll|navigate|wait|done\",\n"
                    "  \"params\": {\"x\": 640, \"y\": 400, \"text\": \"...\", \"url\": \"...\", \"key\": \"Enter\", \"seconds\": 2},\n"
                    "  \"verification\": \"Tôi mong đợi thấy gì ở screenshot sau khi thực hiện hành động này?\",\n"
                    "  \"description\": \"Mô tả việc làm. Neu action=done thi day la phan hoi cuoi gui cho nguoi dung.\"\n"
                    "}\n\n"
                    "QUY TẮC QUAN TRỌNG:\n"
                    "- Tọa độ x(0-1279), y(0-799). PHẢI NHẮM ĐÚNG TÂM CỦA ĐỐI TƯỢNG.\n"
                    "- Neu co the cuon them va thong tin muc tieu chua hien tren man hinh, uu tien action=scroll truoc.\n"
                    "- Neu trang bi CAPTCHA hoac xac minh nguoi dung thi khong co gang giai; chuyen sang done voi mo ta rang can nguoi dung tiep quan.\n"
                    "- Nếu hoàn thành mục tiêu, sử dụng 'done'.\n"
                    "- Chỉ trả về JSON, không giải thích gì thêm."
                )

                ai_response = ""
                decision_cache_key = self._decision_cache_key(dom_snapshot)
                cached_action = None if self.last_action_stuck else self._recall_decision(decision_cache_key)
                if cached_action:
                    action_data = dict(cached_action)
                    thought = str(action_data.get("thought") or "")
                    cached_plan = action_data.get("plan") if isinstance(action_data.get("plan"), list) else []
                    action_data["plan"] = list(cached_plan)
                else:
                    if dom_summary:
                        text_task = asyncio.create_task(_ask_text_model(dom_prompt))
                        async for preview_event in self._stream_preview_until_done(text_task, interval=0.08):
                            yield preview_event
                        ai_response = await text_task
                    if not ai_response.strip():
                        vision_task = asyncio.create_task(_ask_vision_model(sc_for_analysis, ai_prompt + f"\n\nDOM SNAPSHOT:\n{dom_summary}"))
                        async for preview_event in self._stream_preview_until_done(vision_task, interval=0.08):
                            yield preview_event
                        ai_response = await vision_task
                    if self.cancelled: break
                    action_data = _parse_ai_action(ai_response)
                    if action_data.get("_parsed_ok"):
                        self._remember_decision(decision_cache_key, action_data)
                action_type = action_data.get("action", "observe")
                params = action_data.get("params", {}) if isinstance(action_data.get("params", {}), dict) else {}
                thought = action_data.get("thought", "")
                plan = action_data.get("plan", [])
                self.last_verification = action_data.get("verification", "")
                snapshot_item = self._find_snapshot_item(params, action_type)
                if snapshot_item:
                    live_point = await self._live_point_for_snapshot_item(snapshot_item)
                    if live_point:
                        target_x, target_y = live_point
                    else:
                        target_x = int(snapshot_item.get("x") or 640)
                        target_y = int(snapshot_item.get("y") or 400)
                else:
                    target_x, target_y = _resolve_point(params, 640, 400, VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
                desc = action_data.get("description", "Đang thao tác...")
                confirmation_reason = self._requires_confirmation(action_type, params)
                if confirmation_reason and action_type != "done":
                    await self._request_confirmation(confirmation_reason, action_type, params, desc)
                    yield sse_event("confirm_required", {
                        "step": step_num,
                        "session_id": self.session_id,
                        "description": _ui_text(
                            self.user_language,
                            "Skemi cần bạn xác nhận trước khi thao tác mục nhạy cảm.",
                            "Skemi needs your confirmation before performing a sensitive action.",
                        ),
                        "reason": confirmation_reason,
                        "action": action_type,
                        "target": str(
                            (snapshot_item or {}).get("text")
                            or params.get("target_text")
                            or params.get("label")
                            or params.get("url")
                            or self.current_url
                        ).strip(),
                    })
                    approved = await self.wait_for_confirmation()
                    if not approved:
                        yield sse_event("stopped", {
                            "step": step_num,
                            "description": _ui_text(
                                self.user_language,
                                "Đã hủy thao tác nhạy cảm theo lựa chọn của bạn.",
                                "Cancelled the sensitive action based on your choice.",
                            ),
                        })
                        final_message = _ui_text(
                            self.user_language,
                            "Đã hủy thao tác nhạy cảm theo lựa chọn của bạn.",
                            "Cancelled the sensitive action based on your choice.",
                        )
                        break

                # Update state
                self.plan = plan
                self.history.append(desc)

                # Emit only the cursor/action shell so the frontend can stay final-only.
                yield sse_event("step", {
                    "step": step_num,
                    "action": action_type,
                    "url": self.current_url,
                    "x": target_x, "y": target_y
                }, silent=True)

                # Execute action
                # Store current screenshot for "stuck" detection
                pre_action_sc = sc_for_analysis
                pre_action_snapshot = dom_snapshot
                pre_action_url = self.current_url

                if action_type == "done":
                    extracted_result = await self._extract_known_chat_answer()
                    if self.prompt_dispatched and _is_known_chat_surface(self.current_url) and not extracted_result:
                        self.last_verification = _ui_text(
                            self.user_language,
                            "Chưa có câu trả lời hoàn chỉnh từ AI. Tiếp tục chờ và giữ live stream.",
                            "There is no completed AI answer yet. Keep waiting and preserve the live stream.",
                        )
                        await asyncio.sleep(0.3)
                        async for preview_event in self._stream_preview(duration=0.9, interval=0.08):
                            yield preview_event
                        self.step_count = step_num
                        continue
                    if not extracted_result and not _is_known_chat_surface(self.current_url):
                        extracted_result = await self._extract_generic_page_result()
                    completed = True
                    final_message = extracted_result or desc or _ui_text(self.user_language, "Hoàn thành nhiệm vụ.", "Task completed.")
                    self.latest_result_text = str(final_message or "")
                    if extracted_result and _description_is_generic(desc):
                        final_message = extracted_result
                        self.latest_result_text = str(final_message or "")
                    self.step_count = step_num
                    yield sse_event("screenshot", {
                        "step": step_num,
                        "image": sc_for_analysis,
                        "description": "Nhiệm vụ hoàn tất",
                        "surface_metrics": self._surface_metrics_payload(),
                    })
                    break
                
                elif action_type == "click":
                    target_x, target_y = await self._click_target(params)
                elif action_type == "type":
                    target_x, target_y = await self._fill_target(params)
                elif action_type == "hover":
                    hover_item = self._find_snapshot_item(params, "hover")
                    if hover_item:
                        target_x = int(hover_item.get("x") or target_x)
                        target_y = int(hover_item.get("y") or target_y)
                    await self.hover_at(target_x, target_y)
                elif action_type == "press":
                    await self.press_key(params.get("key", "Enter"))
                elif action_type == "scroll":
                    await self.scroll(params.get("direction", "down"))
                elif action_type == "navigate":
                    await self.navigate(params.get("url", ""))
                elif action_type == "wait":
                    await asyncio.sleep(_coerce_seconds(params.get("seconds", 2)))
                else:
                    await asyncio.sleep(0.15)
                
                if self._page:
                    self.current_url = self._page.url

                retried = False
                if action_type in ["click", "type"] and not self.cancelled:
                    try:
                        retried = await self._retry_action_if_needed(action_type, params, pre_action_snapshot, pre_action_url)
                    except Exception as retry_error:
                        print(f"[COMPUTER AGENT] Retry error: {retry_error}")

                await asyncio.sleep(0.08)
                async for preview_event in self._stream_preview(duration=0.55, interval=0.08):
                    yield preview_event
                
                # Check for "stuck" state: did the page change?
                if action_type in ["click", "type", "press"]:
                    post_action_sc = await self.screenshot()
                    # Simple base64 prefix comparison to see if major layout changed
                    # (more robust than whole string as some dynamic elements might shift)
                    if pre_action_sc and post_action_sc:
                        # Compare first 5000 chars of base64 (usually contains header + initial image data)
                        if pre_action_sc[:5000] == post_action_sc[:5000]:
                            self.last_action_stuck = True
                        else:
                            self.last_action_stuck = False
                        if retried and not self.last_action_stuck:
                            self.history.append(
                                _ui_text(
                                    self.user_language,
                                    "Skemi da tu dong retry thao tac bang DOM de dat dung muc tieu.",
                                    "Skemi automatically retried the action through DOM targeting.",
                                )
                            )
                else:
                    self.last_action_stuck = False

                self.step_count = step_num
            else:
                # Hit max steps
                completed = True
                self.step_count = MAX_STEPS
                final_message = _ui_text(
                    self.user_language,
                    f"Đã đạt giới hạn {MAX_STEPS} bước trước khi hoàn tất yêu cầu.",
                    f"Reached the {MAX_STEPS}-step limit before finishing the request.",
                )
                yield sse_event("step", {
                    "step": MAX_STEPS,
                    "action": "max_steps",
                    "description": f"Đã đạt giới hạn {MAX_STEPS} bước",
                    "url": self.current_url,
                })

            # ── Done event ──
            if completed and not stopped_with_error and not self.cancelled:
                yield sse_event("done", {
                    "total_steps": self.step_count,
                    "final_url": self.current_url,
                    "description": final_message,
                })
                yield sse_event("targets", {
                    "step": self.step_count,
                    "items": [],
                    "url": self.current_url,
                    "title": str(((self.last_dom_snapshot or {}) or {}).get("title") or ""),
                    "surface_metrics": self._surface_metrics_payload(),
                }, silent=True)
                async for preview_event in self._stream_preview(
                    duration=max(0.0, BROWSER_POST_DONE_LIVE_SECONDS),
                    interval=0.08,
                ):
                    yield preview_event

        except asyncio.CancelledError:
            yield sse_event("stopped", {
                "description": self.stop_reason or _ui_text(self.user_language, "Đã dừng theo yêu cầu.", "Stopped as requested."),
                "step": self.step_count,
            })
            yield sse_event("targets", {
                "step": self.step_count,
                "items": [],
                "url": self.current_url,
                "title": str(((self.last_dom_snapshot or {}) or {}).get("title") or ""),
                "surface_metrics": self._surface_metrics_payload(),
            }, silent=True)
        except Exception as e:
            print(f"[COMPUTER AGENT] Execute error: {e}")
            yield sse_event("error", {
                "message": str(e),
                "step": self.step_count,
            })
            yield sse_event("targets", {
                "step": self.step_count,
                "items": [],
                "url": self.current_url,
                "title": str(((self.last_dom_snapshot or {}) or {}).get("title") or ""),
                "surface_metrics": self._surface_metrics_payload(),
            }, silent=True)
        finally:
            self._execute_task = None
            self.last_completed_at = time.time()
            self._touch()
            if self.cancelled or self._close_requested:
                await self.close()
            else:
                self.state = "idle"


# ── Public API ────────────────────────────────────────────────────────

def _pick_reusable_browser_session(preferred_session_id: str = "", browser_shell: str = "virtual") -> Optional[BrowserAgentSession]:
    now = time.time()
    preferred = str(preferred_session_id or "").strip()
    desired_shell = str(browser_shell or "virtual").strip().lower() or "virtual"
    if preferred:
        session = active_sessions.get(preferred)
        if (
            session
            and str(getattr(session, "browser_shell", "virtual") or "virtual").strip().lower() == desired_shell
            and session.can_accept_new_command()
            and (now - float(getattr(session, "last_active_at", now) or now)) <= BROWSER_SESSION_REUSE_TTL
        ):
            return session
    candidates = []
    for session in active_sessions.values():
        if str(getattr(session, "browser_shell", "virtual") or "virtual").strip().lower() != desired_shell:
            continue
        if not session.can_accept_new_command():
            continue
        last_active = float(getattr(session, "last_active_at", now) or now)
        if (now - last_active) > BROWSER_SESSION_REUSE_TTL:
            continue
        candidates.append((last_active, session))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def run_browser_agent(command: str, reuse_session_id: str = "", sticky: bool = True, browser_shell: str = "virtual", bypass_safety: bool = False) -> tuple:
    """
    Create and start a browser agent session.
    Returns (session_id, async_generator_of_sse_events).
    """
    _cleanup_stale_sessions()
    reusable = _pick_reusable_browser_session(reuse_session_id if sticky else "", browser_shell=browser_shell)
    if reusable is None and sticky:
        reusable = _pick_reusable_browser_session("", browser_shell=browser_shell)
    if reusable is not None:
        reusable.prepare_for_command(command)
        return reusable.session_id, reusable.execute()
    session_id = str(uuid.uuid4())[:8]
    session = BrowserAgentSession(session_id, command, browser_shell=browser_shell, bypass_safety=bypass_safety)
    active_sessions[session_id] = session
    return session_id, session.execute()


async def ensure_browser_ready(reuse_session_id: str = "", sticky: bool = True, browser_shell: str = "virtual", bypass_safety: bool = False) -> Dict[str, Any]:
    _cleanup_stale_sessions()
    reusable = _pick_reusable_browser_session(reuse_session_id if sticky else "", browser_shell=browser_shell)
    if reusable is None and sticky:
        reusable = _pick_reusable_browser_session("", browser_shell=browser_shell)
    if reusable is None:
        session_id = str(uuid.uuid4())[:8]
        reusable = BrowserAgentSession(session_id, "Mo tab moi va cho lenh tiep theo.", browser_shell=browser_shell, bypass_safety=bypass_safety)
        active_sessions[session_id] = reusable
    return await reusable.ensure_ready(VIRTUAL_BROWSER_HOME_URL)


def stop_session(session_id: str) -> bool:
    """Cancel a running session."""
    session = active_sessions.get(session_id)
    if session:
        session.request_cancel("Da dung Virtual Browser theo yeu cau.")
        return True
    return False
