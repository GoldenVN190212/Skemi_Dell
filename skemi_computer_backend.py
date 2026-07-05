import asyncio
import json
import math
import os
import random
import re
import time
import uuid
import unicodedata
from typing import Any, Dict, List, Optional, AsyncGenerator
from urllib.parse import quote_plus

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

try:
    import httpx
except Exception:
    httpx = None

try:
    from playwright.async_api import BrowserContext, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    async_playwright = None
    Page = None
    BrowserContext = None
    PLAYWRIGHT_AVAILABLE = False


class ComputerSurfaceReadyRequest(BaseModel):
    reuse_session_id: Optional[str] = None
    sticky: bool = True
    transport_preference: str = "mjpeg"
    browser_shell: str = "chrome_like"


class ComputerManualActionRequest(BaseModel):
    session_id: str
    action: str = "click"
    payload: Dict[str, Any] = Field(default_factory=dict)


class ComputerSurfaceResetRequest(BaseModel):
    session_id: str


class ComputerSurfaceNavigateRequest(BaseModel):
    session_id: str
    url: str
    wait_until: str = "domcontentloaded"


class ComputerSurfaceActionRequest(BaseModel):
    session_id: str
    action: str = "observe"
    params: Dict[str, Any] = Field(default_factory=dict)


class ComputerSurfaceAgentRunRequest(BaseModel):
    session_id: str
    command: str
    max_steps: int = 4


class ComputerSurfaceTabRequest(BaseModel):
    session_id: str
    action: str = "list"
    index: int = 0
    url: str = "about:blank"


class ComputerSessionCreateRequest(BaseModel):
    goal: str
    mode: str = "operator"
    preferred_surface: str = ""
    surface_type: str = "server_vm"
    final_response_only: bool = False
    show_live_plan: bool = True
    show_step_log: bool = True
    workflow_id: str = ""
    workspace_id: str = ""
    user_id: str = "default_user"


class ComputerSessionActionRequest(BaseModel):
    note: str = ""
    user_id: str = "default_user"


class ComputerWebRTCOfferRequest(BaseModel):
    session_id: str
    sdp: str
    type: str


class ComputerConfirmRequest(BaseModel):
    session_id: str
    approved: bool


class ComputerResumeRequest(BaseModel):
    session_id: str


class ComputerStopRequest(BaseModel):
    session_id: str


class ComputerPrivacyEvaluateRequest(BaseModel):
    session_id: str
    user_id: str = "default_user"


computer_surface_sessions: Dict[str, Dict[str, Any]] = {}
computer_surface_lock = asyncio.Lock()
computer_sessions: Dict[str, Dict[str, Any]] = {}
computer_sessions_lock = asyncio.Lock()
computer_surface_pool: List[str] = []
computer_pool_target = 1
computer_pool_boot_task: Optional[asyncio.Task] = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
OLLAMA_GENERATE_URL = os.getenv("SKEMI_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate")
SURFACE_AGENT_MODEL = os.getenv("SKEMI_COMPUTER_AGENT_MODEL", "gpt-oss:120b-cloud")


def _human_delay(min_ms: int = 20, max_ms: int = 80) -> float:
    return random.uniform(min_ms / 1000.0, max_ms / 1000.0)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _ease_in_out(value: float) -> float:
    return 3 * value * value - 2 * value * value * value


def _bezier(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    omt = 1.0 - t
    return (
        (omt ** 3) * p0
        + 3 * (omt ** 2) * t * p1
        + 3 * omt * (t ** 2) * p2
        + (t ** 3) * p3
    )


def _human_jitter(x: float, y: float, radius: float = 2.2) -> Dict[str, float]:
    return {
        "x": x + random.uniform(-radius, radius),
        "y": y + random.uniform(-radius, radius),
    }


async def _human_move(page: Page, session: Dict[str, Any], x: float, y: float) -> None:
    viewport = session.get("viewport") or {"width": 1366, "height": 768}
    current = session.get("mouse_position") or {
        "x": viewport["width"] * 0.5 + random.uniform(-90, 90),
        "y": viewport["height"] * 0.5 + random.uniform(-60, 60),
    }
    start_x = _clamp(float(current.get("x", x)), 0.0, float(viewport["width"]) - 1.0)
    start_y = _clamp(float(current.get("y", y)), 0.0, float(viewport["height"]) - 1.0)
    end_x = _clamp(float(x), 0.0, float(viewport["width"]) - 1.0)
    end_y = _clamp(float(y), 0.0, float(viewport["height"]) - 1.0)

    distance = max(math.hypot(end_x - start_x, end_y - start_y), 1.0)
    spread = min(max(distance * 0.28, 22.0), 180.0)
    c1x = start_x + (end_x - start_x) * random.uniform(0.18, 0.32) + random.uniform(-spread, spread)
    c1y = start_y + (end_y - start_y) * random.uniform(0.10, 0.22) + random.uniform(-spread, spread)
    c2x = start_x + (end_x - start_x) * random.uniform(0.65, 0.82) + random.uniform(-spread, spread)
    c2y = start_y + (end_y - start_y) * random.uniform(0.72, 0.90) + random.uniform(-spread, spread)
    steps = min(max(int(distance / 18), 10), 34)

    for index in range(1, steps + 1):
        t = _ease_in_out(index / steps)
        jitter = (1.0 - t) * 0.9
        px = _clamp(
            _bezier(start_x, c1x, c2x, end_x, t) + random.uniform(-jitter, jitter),
            0.0,
            float(viewport["width"]) - 1.0,
        )
        py = _clamp(
            _bezier(start_y, c1y, c2y, end_y, t) + random.uniform(-jitter, jitter),
            0.0,
            float(viewport["height"]) - 1.0,
        )
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.002, 0.008))

    session["mouse_position"] = {"x": end_x, "y": end_y}


async def _human_click(page: Page, session: Dict[str, Any], x: float, y: float) -> Dict[str, float]:
    point = _human_jitter(x, y)
    await _human_move(page, session, point["x"], point["y"])
    await asyncio.sleep(_human_delay(30, 90))
    await page.mouse.down()
    await asyncio.sleep(_human_delay(18, 60))
    await page.mouse.up()
    session["mouse_position"] = {"x": point["x"], "y": point["y"]}
    return point


async def _human_type(page: Page, text: str, min_ms: int = 18, max_ms: int = 45) -> None:
    for ch in text:
        try:
            await page.keyboard.type(ch, delay=random.randint(min_ms, max_ms))
        except Exception:
            await page.keyboard.insert_text(ch)


def _surface_user_dir(session_id: str) -> str:
    root = os.path.join(DATA_DIR, "browser_profiles")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, f"session_{session_id}")


def _surface_placeholder_svg(session: Dict[str, Any]) -> bytes:
    label = session.get("state_label", "Virtual browser ready.")
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'>
    <rect width='100%' height='100%' fill='#0f172a'/>
    <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle'
          fill='#e2e8f0' font-family='Arial' font-size='18'>{label}</text>
    </svg>"""
    return svg.encode("utf-8")


def _surface_map_point(payload: Dict[str, Any], viewport: Dict[str, Any]) -> Optional[Dict[str, float]]:
    try:
        width = max(float(payload.get("width", 1) or 1), 1.0)
        height = max(float(payload.get("height", 1) or 1), 1.0)
        x = float(payload.get("x", 0) or 0)
        y = float(payload.get("y", 0) or 0)
        vw = max(float(viewport.get("width", 1) or 1), 1.0)
        vh = max(float(viewport.get("height", 1) or 1), 1.0)
        fit = str(payload.get("fit", "contain") or "contain").strip().lower()
        scale = min(width / vw, height / vh) if fit == "contain" else max(width / vw, height / vh)
        render_w = vw * scale
        render_h = vh * scale
        offset_x = (width - render_w) / 2.0
        offset_y = (height - render_h) / 2.0
        mapped_x = (x - offset_x) / scale
        mapped_y = (y - offset_y) / scale
        mapped_x = _clamp(mapped_x, 0.0, vw - 1.0)
        mapped_y = _clamp(mapped_y, 0.0, vh - 1.0)
        return {"x": mapped_x, "y": mapped_y}
    except Exception:
        return None


async def _surface_has_active_input(page: Page) -> bool:
    try:
        return bool(await page.evaluate("""
        () => {
            const el = document.activeElement;
            if (!el) return false;
            const tag = el.tagName;
            return tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable;
        }
        """))
    except Exception:
        return False


async def _surface_append_text(page: Page, text: str) -> bool:
    try:
        return bool(await page.evaluate("""
        (txt) => {
            const el = document.activeElement;
            if (!el) return false;
            const tag = el.tagName;
            const isInput = tag === 'INPUT' || tag === 'TEXTAREA';
            const isEditable = el.isContentEditable;
            if (!isInput && !isEditable) return false;
            const current = isEditable ? (el.innerText ?? '') : (el.value ?? '');
            const next = current + txt;
            if (isEditable) {
                el.innerText = next;
            } else {
                el.value = next;
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        """, text))
    except Exception:
        return False


async def _surface_sync_page_state(session: Dict[str, Any], page: Optional[Page]) -> None:
    if not page:
        return
    try:
        session["current_url"] = page.url or ""
    except Exception:
        session["current_url"] = ""
    try:
        session["current_title"] = await page.title()
    except Exception:
        session["current_title"] = ""


async def _surface_observe_page(session: Dict[str, Any], page: Optional[Page]) -> Dict[str, Any]:
    if not _surface_page_alive(page):
        observation = {
            "status": "not_ready",
            "needs_user": False,
            "summary": "Virtual browser is not ready yet.",
            "reason": "page_not_ready",
            "signals": [],
        }
        session["last_observation"] = observation
        session["pending_manual_takeover"] = False
        return observation

    await _surface_sync_page_state(session, page)
    title = str(session.get("current_title") or "")
    url = str(session.get("current_url") or "")
    try:
        page_probe = await page.evaluate("""
        () => {
            const selectors = ['main', 'article', 'body'];
            let text = '';
            for (const selector of selectors) {
                const node = document.querySelector(selector);
                text = (node?.innerText || '').replace(/\s+/g, ' ').trim();
                if (text) break;
            }
            const challengeNodes = [
                'iframe[src*="challenges.cloudflare.com"]',
                'iframe[src*="captcha"]',
                'iframe[src*="recaptcha"]',
                'iframe[src*="hcaptcha"]',
                'input[name="cf-turnstile-response"]',
                '.cf-turnstile',
                '[data-sitekey]'
            ];
            return {
                text: text.slice(0, 2200),
                hasChallengeNode: challengeNodes.some((selector) => Boolean(document.querySelector(selector))),
                readyState: document.readyState || '',
                activeElement: document.activeElement?.tagName || '',
            };
        }
        """)
    except Exception:
        page_probe = {"text": "", "hasChallengeNode": False, "readyState": "", "activeElement": ""}

    body_text = str((page_probe or {}).get("text") or "")
    has_challenge_node = bool((page_probe or {}).get("hasChallengeNode"))
    ready_state = str((page_probe or {}).get("readyState") or "")
    haystack_raw = " ".join([title, url, body_text]).lower()
    haystack_fold_source = haystack_raw.replace(chr(273), "d").replace(chr(272), "d")
    haystack_folded = unicodedata.normalize("NFD", haystack_fold_source).encode("ascii", "ignore").decode("ascii")
    # The folded text lets Vietnamese/curly browser messages match ASCII patterns too.
    haystack = f"{haystack_raw} {haystack_folded}"
    challenge_patterns = {
        "cloudflare": ["cloudflare", "checking your browser", "just a moment", "verify you are human", "turnstile"],
        "captcha": ["captcha", "recaptcha", "hcaptcha", "i am not a robot", "toi khong phai la nguoi may"],
        "browser_block": [
            "this site can't be reached", "this site cant be reached", "your connection is not private",
            "privacy error", "deceptive site ahead", "err_", "dns_probe", "refused to connect",
            "khong the truy cap trang web nay", "ket noi cua ban khong phai la ket noi rieng tu",
        ],
        "access_block": ["access denied", "blocked", "security check", "unusual traffic", "automated queries"],
        "login_gate": ["sign in to continue", "log in to continue", "dang nhap de tiep tuc"],
    }
    signals: List[str] = []
    for name, patterns in challenge_patterns.items():
        if any(pattern in haystack for pattern in patterns):
            signals.append(name)
    if has_challenge_node and "captcha" not in signals and "cloudflare" not in signals:
        signals.append("challenge_widget")
    if url.startswith("chrome-error://") and "browser_block" not in signals:
        signals.append("browser_block")

    if signals:
        status = "challenge"
        needs_user = True
        if "browser_block" in signals:
            summary = "Chrome dang chan hoac chua mo duoc trang. Skemi can ban kiem tra trong stream, xu ly canh bao/ket noi neu an toan, roi nhap 'tiep tuc' de minh quan sat lai."
        elif "login_gate" in signals:
            summary = "Trang dang yeu cau dang nhap hoac xac nhan quyen truy cap. Ban xu ly truc tiep trong stream, roi nhap 'tiep tuc' de Skemi nhin lai va lam tiep."
        else:
            summary = "Trang dang o checkpoint bao mat/CAPTCHA. Skemi se khong bao done gia; ban xu ly truc tiep trong stream roi nhap 'tiep tuc' de minh quan sat lai."
    elif url in {"", "about:blank"}:
        status = "blank"
        needs_user = False
        summary = "Browser chua mo noi dung web nao."
    elif not body_text and ready_state not in {"complete", "interactive"}:
        status = "loading_or_empty"
        needs_user = False
        summary = "Trang van dang tai hoac chua co noi dung nhin thay. Nhap 'tiep tuc' de Skemi kiem tra lai."
    elif not body_text and title:
        status = "loading_or_empty"
        needs_user = False
        summary = f"Trang da toi {title}, nhung noi dung nhin thay con it hoac dang tai. Nhap 'tiep tuc' de Skemi kiem tra lai."
    else:
        status = "ready"
        needs_user = False
        clean_title = title or url or "trang hien tai"
        summary = f"Skemi dang thay {clean_title}."

    observation = {
        "status": status,
        "needs_user": needs_user,
        "summary": summary,
        "reason": signals[0] if signals else status,
        "signals": signals,
        "visible_title": title,
        "visible_url": url,
        "visible_text": body_text[:800],
        "ready_state": ready_state,
    }
    session["last_observation"] = observation
    session["pending_manual_takeover"] = bool(needs_user)
    session["state_label"] = summary
    return observation

async def _surface_collect_targets(page: Optional[Page], limit: int = 90) -> List[Dict[str, Any]]:
    if not _surface_page_alive(page):
        return []
    try:
        targets = await page.evaluate("""
        (limit) => {
            const selector = [
                'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select',
                '[contenteditable="true"]', '[contenteditable=""]', '[role="button"]',
                '[role="link"]', '[role="textbox"]', '[tabindex]:not([tabindex="-1"])'
            ].join(',');
            const seen = new Set();
            const out = [];
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                if (rect.width < 4 || rect.height < 4) return false;
                const style = window.getComputedStyle(el);
                return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity || 1) > 0.02;
            };
            const labelFor = (el) => {
                const aria = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder') || '';
                const text = (el.innerText || el.value || el.textContent || '').replace(/\s+/g, ' ').trim();
                return (aria || text || el.getAttribute('href') || el.tagName || '').slice(0, 180);
            };
            for (const el of Array.from(document.querySelectorAll(selector))) {
                if (out.length >= limit) break;
                if (!(el instanceof HTMLElement) || seen.has(el) || !visible(el)) continue;
                seen.add(el);
                const rect = el.getBoundingClientRect();
                const id = `skemi_target_${out.length + 1}`;
                el.setAttribute('data-skemi-target-id', id);
                out.push({
                    id,
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    label: labelFor(el),
                    href: el.getAttribute('href') || '',
                    input_type: el.getAttribute('type') || '',
                    x: Math.round(rect.left + rect.width / 2),
                    y: Math.round(rect.top + rect.height / 2),
                    left: Math.round(rect.left),
                    top: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                });
            }
            return out;
        }
        """, int(limit))
        return list(targets or [])
    except Exception:
        return []


async def _surface_tab_state(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    context: BrowserContext = session.get("context")
    active_page = session.get("page")
    if not context:
        return []
    tabs: List[Dict[str, Any]] = []
    for index, page in enumerate(list(context.pages or [])):
        try:
            tabs.append({
                "index": index,
                "active": page is active_page,
                "url": page.url or "",
                "title": await page.title(),
            })
        except Exception:
            tabs.append({"index": index, "active": page is active_page, "url": "", "title": ""})
    session["tabs"] = tabs
    return tabs


async def _surface_switch_tab(session: Dict[str, Any], index: int) -> None:
    context: BrowserContext = session.get("context")
    if not context or not context.pages:
        return
    safe_index = max(0, min(int(index), len(context.pages) - 1))
    page = context.pages[safe_index]
    session["page"] = page
    try:
        await page.bring_to_front()
    except Exception:
        pass
    await _surface_sync_page_state(session, page)


def _surface_remember(session: Dict[str, Any], event: Dict[str, Any]) -> None:
    memory = session.setdefault("task_memory", [])
    memory.append({**dict(event or {}), "ts": time.time()})
    if len(memory) > 80:
        del memory[: len(memory) - 80]


async def _surface_click_target_id(page: Page, session: Dict[str, Any], target_id: str) -> bool:
    try:
        rect = await page.evaluate("""
        (targetId) => {
            const el = document.querySelector(`[data-skemi-target-id="${targetId}"]`);
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
            const next = el.getBoundingClientRect();
            return {x: next.left + next.width / 2, y: next.top + next.height / 2, width: next.width, height: next.height};
        }
        """, str(target_id or ""))
        if not rect:
            return False
        point = await _human_click(page, session, float(rect.get("x") or 0), float(rect.get("y") or 0))
        session["last_click"] = {"x": point["x"], "y": point["y"], "ts": time.time()}
        return True
    except Exception:
        return False


async def _surface_execute_action_schema(session: Dict[str, Any], action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    await _surface_ensure_worker(session)
    page: Page = session.get("page")
    if not _surface_page_alive(page):
        return {"success": False, "error": "Virtual browser is not ready."}
    action = str(action or "observe").strip().lower()
    params = dict(params or {})
    try:
        if action == "navigate":
            url = str(params.get("url") or "").strip()
            if not url:
                return {"success": False, "error": "Missing url."}
            await page.goto(url, wait_until=str(params.get("wait_until") or "domcontentloaded"), timeout=20000)
        elif action == "click":
            target_id = str(params.get("target_id") or params.get("id") or "").strip()
            if target_id:
                if not await _surface_click_target_id(page, session, target_id):
                    return {"success": False, "error": f"Target not found: {target_id}"}
            else:
                x = float(params.get("x", 0) or 0)
                y = float(params.get("y", 0) or 0)
                point = await _human_click(page, session, x, y)
                session["last_click"] = {"x": point["x"], "y": point["y"], "ts": time.time()}
        elif action == "type":
            target_id = str(params.get("target_id") or params.get("id") or "").strip()
            text = str(params.get("text") or "")
            if target_id:
                await _surface_click_target_id(page, session, target_id)
            await _surface_prepare_text_input(page, session)
            await _human_type(page, text)
        elif action in {"press", "key"}:
            await page.keyboard.press(str(params.get("key") or "Enter"))
        elif action == "scroll":
            delta_y = float(params.get("delta_y") or params.get("deltaY") or 520)
            await page.mouse.wheel(0, delta_y)
        elif action == "wait":
            await asyncio.sleep(max(0.05, min(float(params.get("seconds") or 0.8), 8.0)))
        elif action == "new_tab":
            context: BrowserContext = session.get("context")
            new_page = await context.new_page()
            session["page"] = new_page
            url = str(params.get("url") or "about:blank")
            await new_page.goto(url, wait_until="domcontentloaded", timeout=15000)
        elif action == "switch_tab":
            await _surface_switch_tab(session, int(params.get("index") or 0))
        elif action == "close_tab":
            context: BrowserContext = session.get("context")
            tabs = list(context.pages or []) if context else []
            if len(tabs) > 1:
                index = max(0, min(int(params.get("index") or 0), len(tabs) - 1))
                closing = tabs[index]
                await closing.close()
                session["page"] = list(context.pages or [])[max(0, min(index, len(context.pages) - 1))]
        elif action == "observe":
            pass
        else:
            return {"success": False, "error": f"Unsupported action: {action}"}
    except Exception as exc:
        session["state_label"] = f"Action error: {type(exc).__name__}: {exc}"
        return {"success": False, "error": str(exc), "action": action}

    observation = await _surface_observe_page(session, session.get("page"))
    targets = await _surface_collect_targets(session.get("page"))
    tabs = await _surface_tab_state(session)
    _surface_remember(session, {"action": action, "params": params, "observation": observation})
    return {
        "success": True,
        "session_id": session.get("session_id"),
        "action": action,
        "current_url": session.get("current_url", ""),
        "current_title": session.get("current_title", ""),
        "observation": observation,
        "targets": targets,
        "tabs": tabs,
        "task_memory": list(session.get("task_memory") or [])[-12:],
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


async def _surface_plan_action_with_model(
    session: Dict[str, Any],
    command: str,
    observation: Dict[str, Any],
    targets: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if httpx is None:
        return None
    compact_targets = [
        {
            "id": item.get("id"),
            "tag": item.get("tag"),
            "role": item.get("role"),
            "label": item.get("label"),
            "x": item.get("x"),
            "y": item.get("y"),
        }
        for item in targets[:45]
    ]
    prompt = (
        "You are Skemi Virtual Browser Operator. Return JSON only.\n"
        "Goal: choose exactly one safe next browser action, then Skemi will observe/verify again.\n"
        "Allowed actions: click, type, press, scroll, wait, navigate, observe, ask_user.\n"
        "Never claim done unless the observation proves the task is complete.\n"
        "If the page has CAPTCHA, Cloudflare, login, or browser security warning, action must be ask_user.\n"
        "Prefer target_id from DOM_TARGETS instead of coordinates.\n"
        "JSON schema: {\"action\":\"...\",\"params\":{...},\"reason\":\"short reason\"}\n\n"
        f"USER_COMMAND: {command}\n"
        f"CURRENT_URL: {session.get('current_url','')}\n"
        f"CURRENT_TITLE: {session.get('current_title','')}\n"
        f"OBSERVATION: {json.dumps(observation, ensure_ascii=False)[:1600]}\n"
        f"DOM_TARGETS: {json.dumps(compact_targets, ensure_ascii=False)[:6000]}\n"
        f"TASK_MEMORY: {json.dumps(list(session.get('task_memory') or [])[-8:], ensure_ascii=False)[:2400]}\n"
    )
    try:
        async with httpx.AsyncClient(timeout=28.0) as client:
            response = await client.post(
                OLLAMA_GENERATE_URL,
                json={
                    "model": SURFACE_AGENT_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.15},
                },
            )
        if response.status_code >= 400:
            return None
        data = response.json()
        parsed = _extract_json_object(str(data.get("response") or data.get("message") or ""))
        action = str(parsed.get("action") or "").strip().lower()
        params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
        if action in {"click", "type", "press", "key", "scroll", "wait", "navigate", "observe", "ask_user"}:
            return {"action": action, "params": params, "reason": str(parsed.get("reason") or "")}
    except Exception:
        return None
    return None


async def _surface_run_simple_agent(session: Dict[str, Any], command: str, max_steps: int = 4) -> Dict[str, Any]:
    raw = str(command or "").strip()
    lowered = raw.lower()
    folded = unicodedata.normalize("NFD", lowered.replace(chr(273), "d")).encode("ascii", "ignore").decode("ascii")
    max_steps = max(1, min(int(max_steps or 4), 8))

    # First, observe if the user is resuming after a manual handoff.
    if folded in {"tiep tuc", "continue", "resume", "observe", "nhin lai", "quan sat lai"}:
        return await _surface_execute_action_schema(session, "observe", {})

    url = ""
    words = raw.split()
    for word in words:
        if word.startswith("http://") or word.startswith("https://") or ("." in word and " " not in word):
            url = word.strip(".,;()[]{}<>")
            break
    if any(folded.startswith(prefix) for prefix in ["mo ", "vao ", "truy cap ", "open ", "visit ", "go to ", "navigate "]) and url:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return await _surface_execute_action_schema(session, "navigate", {"url": url})

    observation = await _surface_observe_page(session, session.get("page"))
    targets = await _surface_collect_targets(session.get("page"))
    tabs = await _surface_tab_state(session)
    if observation.get("needs_user"):
        _surface_remember(session, {"action": "ask_user", "reason": observation.get("reason"), "observation": observation})
        return {
            "success": True,
            "session_id": session.get("session_id"),
            "action": "ask_user",
            "current_url": session.get("current_url", ""),
            "current_title": session.get("current_title", ""),
            "observation": observation,
            "targets": targets,
            "tabs": tabs,
            "task_memory": list(session.get("task_memory") or [])[-12:],
        }

    planned = await _surface_plan_action_with_model(session, raw, observation, targets)
    if planned:
        planned_action = str(planned.get("action") or "observe")
        planned_params = dict(planned.get("params") or {})
        if planned_action == "ask_user":
            observation["needs_user"] = True
            observation["status"] = "challenge"
            observation["summary"] = planned.get("reason") or observation.get("summary") or "Skemi needs user handoff before continuing."
            session["last_observation"] = observation
            session["pending_manual_takeover"] = True
            session["state_label"] = observation["summary"]
            _surface_remember(session, {"action": "ask_user", "reason": planned.get("reason"), "observation": observation})
            return {
                "success": True,
                "session_id": session.get("session_id"),
                "action": "ask_user",
                "current_url": session.get("current_url", ""),
                "current_title": session.get("current_title", ""),
                "observation": observation,
                "targets": targets,
                "tabs": tabs,
                "task_memory": list(session.get("task_memory") or [])[-12:],
                "model_plan": planned,
            }
        result = await _surface_execute_action_schema(session, planned_action, planned_params)
        result["model_plan"] = planned
        return result

    # Click by visible label when the command explicitly names a UI target.
    if any(token in folded for token in ["click", "bam", "nhan"]):
        for target in targets:
            label = unicodedata.normalize("NFD", str(target.get("label") or "").lower().replace(chr(273), "d")).encode("ascii", "ignore").decode("ascii")
            if label and any(part and part in folded for part in label.split()[:4]):
                return await _surface_execute_action_schema(session, "click", {"target_id": target.get("id")})

    if any(token in folded for token in ["go", "hoi", "nhap", "type", "ask"]):
        text = raw
        for sep in [":", " la ", " noi dung "]:
            if sep in text:
                text = text.split(sep, 1)[-1].strip()
        text_targets = [item for item in targets if item.get("tag") in {"input", "textarea"} or item.get("role") == "textbox"]
        params = {"text": text}
        if text_targets:
            params["target_id"] = text_targets[0].get("id")
        result = await _surface_execute_action_schema(session, "type", params)
        if result.get("success"):
            result = await _surface_execute_action_schema(session, "press", {"key": "Enter"})
        return result

    # Default: keep the browser useful by searching, but verify after navigation.
    return await _surface_execute_action_schema(session, "navigate", {"url": f"https://www.google.com/search?q={quote_plus(raw)}"})


def _surface_page_alive(page: Optional[Page]) -> bool:
    if not page:
        return False
    try:
        return not page.is_closed()
    except Exception:
        return False


async def _surface_focus_text_target(page: Page, session: Dict[str, Any]) -> bool:
    last_click = session.get("last_click") or session.get("mouse_position")
    point = None
    if isinstance(last_click, dict):
        point = {
            "x": float(last_click.get("x", 0) or 0),
            "y": float(last_click.get("y", 0) or 0),
        }
    try:
        focused = bool(await page.evaluate(
            """
            (point) => {
                const isTextTarget = (node) => {
                    if (!(node instanceof HTMLElement)) return false;
                    if (node.isContentEditable) return true;
                    const tag = node.tagName;
                    if (tag === 'TEXTAREA') return !node.disabled && !node.readOnly;
                    if (tag !== 'INPUT') return false;
                    const type = (node.getAttribute('type') || 'text').toLowerCase();
                    return !['hidden', 'checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'range', 'color'].includes(type)
                        && !node.disabled
                        && !node.readOnly;
                };
                const visible = (node) => {
                    if (!(node instanceof HTMLElement)) return false;
                    const rect = node.getBoundingClientRect();
                    if (rect.width < 6 || rect.height < 6) return false;
                    const style = window.getComputedStyle(node);
                    return style.visibility !== 'hidden' && style.display !== 'none';
                };
                const tryFocus = (node) => {
                    let current = node;
                    while (current) {
                        if (isTextTarget(current) && visible(current)) {
                            current.focus({ preventScroll: true });
                            if (typeof current.click === 'function') current.click();
                            return true;
                        }
                        current = current.parentElement;
                    }
                    return false;
                };
                if (point && Number.isFinite(point.x) && Number.isFinite(point.y)) {
                    if (tryFocus(document.elementFromPoint(point.x, point.y))) return true;
                }
                const candidates = Array.from(document.querySelectorAll(
                    "input:not([type='hidden']):not([disabled]), textarea:not([disabled]), [contenteditable=''], [contenteditable='true']"
                ));
                for (const candidate of candidates) {
                    if (tryFocus(candidate)) return true;
                }
                return false;
            }
            """,
            point,
        ))
        if focused:
            await asyncio.sleep(_human_delay(25, 55))
            return True
    except Exception:
        pass
    return False


async def _surface_prepare_text_input(page: Page, session: Dict[str, Any]) -> bool:
    if await _surface_has_active_input(page):
        return True
    if await _surface_focus_text_target(page, session) and await _surface_has_active_input(page):
        return True
    last_click = session.get("last_click")
    if last_click:
        await _human_click(page, session, float(last_click.get("x", 0) or 0), float(last_click.get("y", 0) or 0))
    else:
        viewport = session.get("viewport") or {"width": 1366, "height": 768}
        point = await _human_click(page, session, viewport["width"] * 0.5, viewport["height"] * 0.5)
        session["last_click"] = {"x": point["x"], "y": point["y"], "ts": time.time()}
    if await _surface_has_active_input(page):
        return True
    return await _surface_focus_text_target(page, session)


async def _surface_execute_manual_action(session: Dict[str, Any], action: str, payload: Dict[str, Any]) -> None:
    page: Page = session.get("page")
    if not page:
        return

    if action == "click":
        viewport = session.get("viewport") or {"width": 1, "height": 1}
        mapped = _surface_map_point(payload, viewport)
        if mapped:
            point = await _human_click(page, session, mapped["x"], mapped["y"])
            session["last_click"] = {"x": point["x"], "y": point["y"], "ts": time.time()}
        return

    if action == "scroll":
        viewport = session.get("viewport") or {"width": 1, "height": 1}
        mapped = _surface_map_point(payload, viewport)
        if mapped:
            await _human_move(page, session, mapped["x"], mapped["y"])
        delta_y = float(payload.get("deltaY", 0) or 0)
        steps = max(1, min(10, int(abs(delta_y) // 120) + 1))
        step_delta = delta_y / steps
        for _ in range(steps):
            await page.mouse.wheel(0, step_delta)
            await asyncio.sleep(_human_delay(12, 36))
        return

    if action in {"type", "type_buffer"}:
        text = str(payload.get("text", "") or "")
        if not text:
            return
        if await _surface_prepare_text_input(page, session):
            try:
                await _human_type(page, text, 24, 58)
            except Exception:
                await _surface_append_text(page, text)
        else:
            await _human_type(page, text, 24, 58)
        return

    if action == "key":
        key = str(payload.get("key", "") or "")
        if not key:
            return
        if len(key) == 1 and key not in {"\n", "\r", "\t"}:
            if await _surface_prepare_text_input(page, session):
                try:
                    await _human_type(page, key, 18, 42)
                except Exception:
                    await _surface_append_text(page, key)
            else:
                await _human_type(page, key, 18, 42)
            return
        await page.keyboard.press(key)


async def _surface_control_loop(session_id: str) -> None:
    while True:
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            if not session or session.get("closing"):
                break
            queue: asyncio.Queue = session.get("control_queue")
        if not queue:
            await asyncio.sleep(0.05)
            continue
        try:
            action_item = await queue.get()
        except asyncio.CancelledError:
            break
        if action_item is None:
            break
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            if not session:
                break
            session["queued_actions"] = queue.qsize()
            session["last_active_at"] = time.time()
            session["state_label"] = f"Executing {action_item['action']}..."
        try:
            await _surface_execute_manual_action(session, action_item["action"], action_item["payload"])
            await _surface_sync_page_state(session, session.get("page"))
            async with computer_surface_lock:
                session = computer_surface_sessions.get(session_id)
                if session:
                    session["last_action_at"] = time.time()
                    session["last_action"] = action_item["action"]
                    session["state_label"] = "Manual control ready."
                    session["queued_actions"] = queue.qsize()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            recovered = False
            if "closed" in str(exc).lower() or not _surface_page_alive(session.get("page")):
                try:
                    await _surface_ensure_worker(session)
                    if _surface_page_alive(session.get("page")):
                        await _surface_execute_manual_action(session, action_item["action"], action_item["payload"])
                        await _surface_sync_page_state(session, session.get("page"))
                        recovered = True
                except Exception as retry_exc:
                    exc = retry_exc
            async with computer_surface_lock:
                session = computer_surface_sessions.get(session_id)
                if session:
                    if recovered:
                        session["state_label"] = "Manual control ready."
                        session["last_error"] = ""
                    else:
                        session["state_label"] = f"Manual action error: {type(exc).__name__}"
                        session["last_error"] = str(exc)
                    session["queued_actions"] = queue.qsize()
        finally:
            queue.task_done()


async def _surface_capture_loop(session_id: str) -> None:
    last_meta_sync = 0.0
    while True:
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            if not session or session.get("closing"):
                break
            page: Page = session.get("page")
        if not page:
            await asyncio.sleep(0.2)
            continue
        try:
            frame = await page.screenshot(type="jpeg", quality=42, scale="css")
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.2)
            continue

        now = time.time()
        ts_ms = int(now * 1000)
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            if not session:
                break
            session["latest_frame"] = frame
            session["latest_frame_ts"] = now
            session["latest_frame_version"] = int(session.get("latest_frame_version", 0)) + 1
            if session.get("history_enabled") and now - float(session.get("last_history_at", 0.0) or 0.0) >= 1.5:
                frame_url = f"/api/computer/live?session_id={session_id}&ts={ts_ms}"
                _surface_register_history(session, ts_ms, frame_url)
                session["last_history_at"] = now

        if now - last_meta_sync >= 0.5:
            await _surface_sync_page_state(session, page)
            last_meta_sync = now

        await asyncio.sleep(0.033)


async def _surface_launch_context(pw: Any, user_dir: str, launch_kwargs: Dict[str, Any]):
    attempts = [
        {"label": "Google Chrome", "headless": True, "channel": "chrome"},
        {"label": "Chromium", "headless": True},
        {"label": "Google Chrome", "headless": False, "channel": "chrome"},
        {"label": "Chromium", "headless": False},
    ]
    last_error = None
    for attempt in attempts:
        kwargs = dict(launch_kwargs)
        channel = attempt.get("channel")
        if channel:
            kwargs["channel"] = channel
        try:
            context = await pw.chromium.launch_persistent_context(
                user_dir,
                headless=attempt["headless"],
                **kwargs,
            )
            return context, attempt["headless"], attempt["label"]
        except Exception as exc:
            last_error = exc
    raise last_error


async def _surface_ensure_worker(session: Dict[str, Any]) -> None:
    if session.get("worker_ready") and _surface_page_alive(session.get("page")):
        return
    if session.get("worker_ready") and not _surface_page_alive(session.get("page")):
        await _surface_close_worker(session)
        session["worker_ready"] = False
        session["closing"] = False
        session["context"] = None
        session["page"] = None
        session["playwright"] = None
    if not PLAYWRIGHT_AVAILABLE:
        session["state_label"] = "Playwright missing. Install it to enable Virtual Browser."
        return
    session_id = str(session.get("session_id") or "")
    pw = None
    context = None
    try:
        session["state_label"] = "Launching Virtual Browser..."
        pw = await async_playwright().start()
        user_dir = _surface_user_dir(session_id)
        viewport = {"width": 1366, "height": 768}
        launch_kwargs = {
            "viewport": viewport,
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
            "args": [
                "--window-size=1366,768",
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        context, headless_mode, browser_label = await _surface_launch_context(pw, user_dir, launch_kwargs)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
        session["playwright"] = pw
        session["context"] = context
        session["page"] = page
        session["viewport"] = viewport
        session["headless_mode"] = headless_mode
        session["browser_label"] = browser_label
        session["worker_ready"] = True
        session["current_url"] = page.url or "about:blank"
        session["current_title"] = await page.title()
        session["state_label"] = f"{browser_label} ready."
        session["control_queue"] = asyncio.Queue(maxsize=512)
        session["control_task"] = asyncio.create_task(_surface_control_loop(session_id))
        session["capture_task"] = asyncio.create_task(_surface_capture_loop(session_id))
    except Exception as exc:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass
        session["state_label"] = f"Browser worker error: {type(exc).__name__}: {exc}"


async def _surface_close_worker(session: Dict[str, Any]) -> None:
    session["closing"] = True
    queue: Optional[asyncio.Queue] = session.get("control_queue")
    if queue:
        try:
            queue.put_nowait(None)
        except Exception:
            pass
    for task_name in ("control_task", "capture_task"):
        task = session.get(task_name)
        if task:
            task.cancel()
    context: BrowserContext = session.get("context")
    if context:
        try:
            await context.close()
        except Exception:
            pass
    pw = session.get("playwright")
    if pw:
        try:
            await pw.stop()
        except Exception:
            pass


def _surface_make_session(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "state": "ready",
        "state_label": "Virtual browser ready.",
        "history": [],
        "history_enabled": False,
        "worker_ready": False,
        "latest_frame_version": 0,
        "queued_actions": 0,
        "current_url": "",
        "current_title": "",
        "transport": "mjpeg",
        "input_pipeline": "queued_direct_control",
        "task_memory": [],
        "tabs": [],
    }


def _surface_register_history(session: Dict[str, Any], ts_ms: int, frame_url: str) -> None:
    history = session.setdefault("history", [])
    history.append({"index": len(history), "ts": ts_ms, "frame_url": frame_url})
    if len(history) > 300:
        del history[: len(history) - 300]


async def _surface_spawn_session(session_id: Optional[str] = None) -> Dict[str, Any]:
    created_id = str(session_id or uuid.uuid4().hex[:12]).strip()
    async with computer_surface_lock:
        session = computer_surface_sessions.get(created_id)
        if not session:
            session = _surface_make_session(created_id)
            session["warm_pool"] = True
            computer_surface_sessions[created_id] = session
    await _surface_ensure_worker(session)
    return session


async def _surface_fill_pool(target: Optional[int] = None) -> None:
    desired = max(0, int(target if target is not None else computer_pool_target))
    while True:
        async with computer_surface_lock:
            computer_surface_pool[:] = [
                session_id
                for session_id in computer_surface_pool
                if session_id in computer_surface_sessions
                and computer_surface_sessions[session_id].get("worker_ready")
                and not computer_surface_sessions[session_id].get("closing")
            ]
            deficit = desired - len(computer_surface_pool)
        if deficit <= 0:
            return
        session = await _surface_spawn_session()
        async with computer_surface_lock:
            session["warm_pool"] = True
            if session["session_id"] not in computer_surface_pool:
                computer_surface_pool.append(session["session_id"])


async def _surface_acquire_session(reuse_id: str = "") -> Dict[str, Any]:
    normalized = str(reuse_id or "").strip()
    if normalized:
        async with computer_surface_lock:
            session = computer_surface_sessions.get(normalized)
            if session:
                session["warm_pool"] = False
                session["last_active_at"] = time.time()
                try:
                    computer_surface_pool.remove(normalized)
                except ValueError:
                    pass
        if session:
            await _surface_ensure_worker(session)
            return session
        return await _surface_spawn_session(normalized)

    acquired: Optional[Dict[str, Any]] = None
    async with computer_surface_lock:
        while computer_surface_pool:
            session_id = computer_surface_pool.pop(0)
            session = computer_surface_sessions.get(session_id)
            if session and session.get("worker_ready") and not session.get("closing"):
                session["warm_pool"] = False
                session["last_active_at"] = time.time()
                acquired = session
                break
    if acquired:
        asyncio.create_task(_surface_fill_pool())
        return acquired

    session = await _surface_spawn_session()
    session["warm_pool"] = False
    asyncio.create_task(_surface_fill_pool())
    return session


async def _surface_shutdown_all() -> None:
    async with computer_surface_lock:
        sessions = list(computer_surface_sessions.values())
        computer_surface_sessions.clear()
        computer_surface_pool.clear()
    for session in sessions:
        try:
            await _surface_close_worker(session)
        except Exception:
            pass


# ---------- Session helpers ----------

def _new_session(payload: ComputerSessionCreateRequest) -> Dict[str, Any]:
    session_id = uuid.uuid4().hex[:12]
    return {
        "session_id": session_id,
        "status": "active",
        "mode": payload.mode or "operator",
        "surface_type": payload.surface_type or "server_vm",
        "summary": "Session ready.",
        "target_surface": payload.preferred_surface or "Search",
        "target_surface_label": payload.preferred_surface or "Search",
        "approval_required": False,
        "privacy_state": "safe",
        "blocked_reason": "",
        "stream_redaction_active": False,
        "action_queue": [],
        "safety_rules": [],
        "artifacts": [],
        "events": [],
        "handoff_note": "",
        "workspace_id": payload.workspace_id or session_id,
        "workspace_root": os.path.join(DATA_DIR, "workspace", session_id),
        "vm_mount_path": "/mnt/skemi_shared",
        "artifact_manifest_version": 1,
        "display_policy": {
            "final_response_only": bool(payload.final_response_only),
            "show_step_log": bool(payload.show_step_log),
        },
        "runtime_blueprint": {
            "primary_observer": "skemi",
            "primary_actor": "skemi",
            "typing_strategy": "queued_real_keys",
            "kill_switch": "manual",
            "runtime_summary": "Direct-control Virtual Browser ready.",
            "observation_stack": [],
            "interaction_stack": [],
            "anti_bot_strategy": [
                "persistent browser session",
                "human-paced mouse movement",
                "human-paced keyboard events",
                "manual handoff for CAPTCHA or login checks",
            ],
            "human_control": [
                "Manual control stays available at all times.",
                "If a challenge page appears, hand it to the user and resume after it clears.",
            ],
            "escape_hatches": ["Reset session", "Manual takeover"],
            "release_blockers": [],
            "build_milestones": [],
            "stream_transport": "mjpeg",
            "human_control_mode": "queued_direct_control",
        },
    }


def register(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _computer_startup():
        global computer_pool_boot_task
        if computer_pool_boot_task and not computer_pool_boot_task.done():
            return
        computer_pool_boot_task = asyncio.create_task(_surface_fill_pool())

    @app.on_event("shutdown")
    async def _computer_shutdown():
        await _surface_shutdown_all()

    @app.get("/Computer.html")
    async def computer_page():
        return FileResponse(os.path.join(BASE_DIR, "Computer.html"))

    @app.post("/api/computer/ready")
    async def computer_surface_ready(req: ComputerSurfaceReadyRequest):
        reuse_id = str(req.reuse_session_id or "").strip()
        session = await _surface_acquire_session(reuse_id)
        return {
            "success": True,
            "session_id": session["session_id"],
            "state": session.get("state", "ready"),
            "state_label": session.get("state_label", "Virtual browser ready."),
            "transport": session.get("transport", "mjpeg"),
            "current_url": session.get("current_url", ""),
            "current_title": session.get("current_title", ""),
            "prewarmed": bool(session.get("worker_ready")),
            "warm_pool": bool(session.get("warm_pool")),
            "observation": session.get("last_observation") or {},
        }

    @app.get("/api/computer/status")
    async def computer_surface_status(session_id: str = ""):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            if not session_id:
                jobs = []
                for active_id, active_session in computer_surface_sessions.items():
                    jobs.append({
                        "id": active_id,
                        "type": "computer",
                        "mode": "operator",
                        "done": False,
                        "state": active_session.get("state", "ready"),
                        "message": active_session.get("state_label", "Virtual browser ready."),
                        "history_count": len(active_session.get("history", [])),
                        "sticky": True,
                        "browser_shell": "chrome_like",
                        "current_url": active_session.get("current_url", ""),
                        "current_title": active_session.get("current_title", ""),
                        "pending_manual_takeover": {},
                        "pending_confirmation": {},
                        "last_result": "",
                        "transport_preference": active_session.get("transport", "mjpeg"),
                        "last_active_at": float(active_session.get("last_active_at", time.time()) or time.time()),
                        "reconnectable": True,
                    })
                return {"success": True, "jobs": jobs}
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found.", "jobs": []}
        return {
            "success": True,
            "session_id": session_id,
            "state": session.get("state", "ready"),
            "state_label": session.get("state_label", "Virtual browser ready."),
            "current_url": session.get("current_url", ""),
            "current_title": session.get("current_title", ""),
            "pending_manual_takeover": bool(session.get("pending_manual_takeover")),
            "pending_confirmation": False,
            "reconnectable": True,
            "queued_actions": int(session.get("queued_actions", 0) or 0),
            "transport": session.get("transport", "mjpeg"),
            "worker_ready": bool(session.get("worker_ready")),
            "input_pipeline": session.get("input_pipeline", "queued_direct_control"),
            "warm_pool": bool(session.get("warm_pool")),
            "pool_available": len(computer_surface_pool),
            "observation": session.get("last_observation") or {},
            "jobs": [],
        }

    @app.get("/api/computer/observe")
    async def computer_surface_observe(session_id: str = ""):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        await _surface_ensure_worker(session)
        page: Page = session.get("page")
        observation = await _surface_observe_page(session, page)
        return {
            "success": True,
            "session_id": session_id,
            "current_url": session.get("current_url", ""),
            "current_title": session.get("current_title", ""),
            "observation": observation,
        }

    @app.get("/api/computer/dom")
    async def computer_surface_dom(session_id: str = ""):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        await _surface_ensure_worker(session)
        page: Page = session.get("page")
        observation = await _surface_observe_page(session, page)
        targets = await _surface_collect_targets(page)
        tabs = await _surface_tab_state(session)
        return {
            "success": True,
            "session_id": session_id,
            "current_url": session.get("current_url", ""),
            "current_title": session.get("current_title", ""),
            "observation": observation,
            "targets": targets,
            "tabs": tabs,
            "task_memory": list(session.get("task_memory") or [])[-12:],
        }

    @app.post("/api/computer/action")
    async def computer_surface_action(req: ComputerSurfaceActionRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        return await _surface_execute_action_schema(session, req.action, dict(req.params or {}))

    @app.post("/api/computer/agent-run")
    async def computer_surface_agent_run(req: ComputerSurfaceAgentRunRequest):
        session_id = str(req.session_id or "").strip()
        command = str(req.command or "").strip()
        if not command:
            return {"success": False, "error": "Missing command."}
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        result = await _surface_run_simple_agent(session, command, req.max_steps)
        result["agent_loop"] = {
            "policy": "observe-plan-act-observe-verify-report",
            "schema": "click|type|press|scroll|wait|navigate|observe|new_tab|switch_tab|close_tab|ask_user",
            "verified": bool(result.get("observation")),
            "needs_user": bool((result.get("observation") or {}).get("needs_user")),
        }
        return result

    @app.post("/api/computer/tabs")
    async def computer_surface_tabs(req: ComputerSurfaceTabRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        await _surface_ensure_worker(session)
        action = str(req.action or "list").strip().lower()
        if action == "new":
            await _surface_execute_action_schema(session, "new_tab", {"url": req.url or "about:blank"})
        elif action == "switch":
            await _surface_switch_tab(session, req.index)
        elif action == "close":
            await _surface_execute_action_schema(session, "close_tab", {"index": req.index})
        page: Page = session.get("page")
        observation = await _surface_observe_page(session, page)
        tabs = await _surface_tab_state(session)
        return {"success": True, "session_id": session_id, "tabs": tabs, "observation": observation}

    @app.post("/api/computer/navigate")
    async def computer_surface_navigate(req: ComputerSurfaceNavigateRequest):
        session_id = str(req.session_id or "").strip()
        target_url = str(req.url or "").strip()
        if not session_id or not target_url:
            return {"success": False, "error": "Missing session_id or url."}
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        await _surface_ensure_worker(session)
        page: Page = session.get("page")
        if not _surface_page_alive(page):
            return {"success": False, "error": "Virtual browser is not ready."}
        try:
            await page.goto(target_url, wait_until=req.wait_until or "domcontentloaded", timeout=20000)
            observation = await _surface_observe_page(session, page)
            return {
                "success": True,
                "session_id": session_id,
                "current_url": session.get("current_url", ""),
                "current_title": session.get("current_title", ""),
                "observation": observation,
                "needs_user": bool(observation.get("needs_user")),
            }
        except Exception as exc:
            session["state_label"] = f"Navigation error: {type(exc).__name__}"
            return {"success": False, "error": str(exc)}

    @app.get("/api/computer/live")
    async def computer_surface_live(session_id: str):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return Response(content=b"", media_type="image/svg+xml", status_code=404)
        frame = session.get("latest_frame")
        if frame:
            return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
        svg = _surface_placeholder_svg(session)
        return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    @app.get("/api/computer/mjpeg")
    async def computer_surface_mjpeg(session_id: str):
        session_id = str(session_id or "").strip()

        async def frame_generator():
            last_version = -1
            last_emit = 0.0
            while True:
                async with computer_surface_lock:
                    session = computer_surface_sessions.get(session_id)
                    if not session:
                        break
                    frame = session.get("latest_frame")
                    version = int(session.get("latest_frame_version", 0) or 0)
                now = time.time()
                if frame and (version != last_version or now - last_emit >= 1.0):
                    last_version = version
                    last_emit = now
                    headers = (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                    )
                    yield headers + frame + b"\r\n"
                await asyncio.sleep(0.03)

        return StreamingResponse(
            frame_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/api/computer/stream")
    async def computer_surface_stream(session_id: str):
        session_id = str(session_id or "").strip()

        async def event_generator():
            last_version = -1
            while True:
                async with computer_surface_lock:
                    session = computer_surface_sessions.get(session_id)
                if not session:
                    break
                version = int(session.get("latest_frame_version", 0) or 0)
                now = time.time()
                if version != last_version:
                    last_version = version
                    ts_ms = int(now * 1000)
                    payload = {
                        "type": "state",
                        "ts": ts_ms,
                        "frame_url": f"/api/computer/live?session_id={session_id}&ts={ts_ms}",
                        "state_label": session.get("state_label", "Virtual browser ready."),
                        "current_url": session.get("current_url", ""),
                        "current_title": session.get("current_title", ""),
                        "queued_actions": int(session.get("queued_actions", 0) or 0),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/api/computer/history/manifest")
    async def computer_surface_history_manifest(session_id: str):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            history = list(session.get("history", [])) if session else []
        if not session:
            return {"success": False, "error": "Surface session not found."}
        return {
            "success": True,
            "session_id": session_id,
            "segments": history,
            "count": len(history),
            "live_edge": history[-1]["index"] if history else 0,
            "history_enabled": bool(session.get("history_enabled")),
        }

    @app.get("/api/computer/history/segment")
    async def computer_surface_history_segment(session_id: str, index: int = 0):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            history = list(session.get("history", [])) if session else []
        if not session:
            return {"success": False, "error": "Surface session not found."}
        if not history:
            return {"success": False, "error": "No history yet."}
        resolved_index = max(0, min(int(index), len(history) - 1))
        entry = history[resolved_index]
        return {"success": True, "frame_url": entry.get("frame_url", ""), "ts": entry.get("ts", 0)}

    @app.get("/api/computer/history/state")
    async def computer_surface_history_state(session_id: str):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            history = list(session.get("history", [])) if session else []
        if not session:
            return {"success": False, "error": "Surface session not found."}
        return {
            "success": True,
            "session_id": session_id,
            "count": len(history),
            "live_edge": history[-1]["index"] if history else 0,
            "reconnectable": True,
            "history_enabled": bool(session.get("history_enabled")),
        }

    @app.post("/api/computer/history/enable")
    async def computer_surface_history_enable(req: ComputerSurfaceResetRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            if session:
                session["history_enabled"] = True
                session["last_active_at"] = time.time()
        if not session:
            return {"success": False, "error": "Surface session not found."}
        return {"success": True, "session_id": session_id, "history_enabled": True}

    @app.post("/api/computer/manual-action")
    async def computer_surface_manual_action(req: ComputerManualActionRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}
        if not session.get("worker_ready"):
            await _surface_ensure_worker(session)
        if not session.get("worker_ready"):
            return {"success": False, "error": session.get("state_label", "Virtual browser is not ready.")}
        if not _surface_page_alive(session.get("page")):
            await _surface_ensure_worker(session)
            if not session.get("worker_ready") or not _surface_page_alive(session.get("page")):
                return {"success": False, "error": "Virtual browser worker needs recovery."}

        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
            if not session:
                return {"success": False, "error": "Surface session not found."}
            queue: asyncio.Queue = session.get("control_queue")
            if not queue:
                queue = asyncio.Queue(maxsize=512)
                session["control_queue"] = queue
                session["control_task"] = asyncio.create_task(_surface_control_loop(session_id))
            action_id = int(session.get("next_action_id", 1) or 1)
            session["next_action_id"] = action_id + 1
            action_item = {
                "id": action_id,
                "action": str(req.action or "click"),
                "payload": dict(req.payload or {}),
                "queued_at": time.time(),
            }
            try:
                queue.put_nowait(action_item)
            except asyncio.QueueFull:
                return {"success": False, "error": "Manual control queue is full."}
            session["queued_actions"] = queue.qsize()
            session["last_active_at"] = time.time()
            session["state_label"] = f"Queued {action_item['action']} ({session['queued_actions']} pending)."
        return {
            "success": True,
            "session_id": session_id,
            "action_id": action_id,
            "queued_actions": int(session.get("queued_actions", 0) or 0),
        }

    @app.post("/api/computer/reset-session")
    async def computer_surface_reset(req: ComputerSurfaceResetRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.pop(session_id, None)
            try:
                computer_surface_pool.remove(session_id)
            except ValueError:
                pass
        if session:
            await _surface_close_worker(session)
        asyncio.create_task(_surface_fill_pool())
        return {"success": True, "session_id": session_id}

    # ---- Session endpoints (lightweight) ----
    @app.post("/api/computer/sessions")
    async def computer_sessions_create(req: ComputerSessionCreateRequest):
        session = _new_session(req)
        async with computer_sessions_lock:
            computer_sessions[session["session_id"]] = session
        return {"success": True, "session": session}

    @app.get("/api/computer/sessions/{session_id}")
    async def computer_sessions_get(session_id: str):
        async with computer_sessions_lock:
            session = computer_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Session not found."}
        return {"success": True, "session": session}

    @app.post("/api/computer/sessions/{session_id}/{action}")
    async def computer_sessions_action(session_id: str, action: str, req: ComputerSessionActionRequest):
        async with computer_sessions_lock:
            session = computer_sessions.get(session_id)
            if not session:
                return {"success": False, "error": "Session not found."}
            session["status"] = action
            session["summary"] = f"{action.title()} requested."
        return {"success": True, "session": session}

    @app.post("/api/computer/sessions/{session_id}/privacy/evaluate")
    async def computer_sessions_privacy(session_id: str, req: ComputerPrivacyEvaluateRequest):
        async with computer_sessions_lock:
            session = computer_sessions.get(session_id)
            if not session:
                return {"success": False, "error": "Session not found."}
            session["privacy_state"] = "safe"
            session["blocked_reason"] = ""
        return {"success": True, "session": session}

    @app.get("/api/computer/history")
    async def computer_surface_history(session_id: str, ts: Optional[int] = None):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}

        history = list(session.get("history", []))
        return {
            "success": True,
            "session_id": session_id,
            "frames": history,
            "live_index": len(history) - 1 if history else -1
        }

    @app.get("/api/computer/history/frame")
    async def computer_surface_history_frame(session_id: str, index: int, ts: Optional[int] = None):
        session_id = str(session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}

        history = list(session.get("history", []))
        if index < 0 or index >= len(history):
            return {"success": False, "error": "Frame index out of bounds."}

        frame = history[index]
        return {
            "success": True,
            "image": frame.get("image") or frame.get("screenshot") or "",
            "surface_metrics": frame.get("surface_metrics") or session.get("surface_metrics"),
            "url": frame.get("url") or "",
            "title": frame.get("title") or ""
        }

    @app.post("/api/computer/webrtc/offer")
    async def computer_surface_webrtc_offer(req: ComputerWebRTCOfferRequest):
        from computer_webrtc import browser_webrtc_hub
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}

        await _surface_ensure_worker(session)

        async def _force_refresh():
            # A placeholder for future use if background refresh is needed
            pass

        try:
            answer = await browser_webrtc_hub.create_answer(
                session_id=session_id,
                offer_sdp=req.sdp,
                offer_type=req.type,
                job=session, # We pass the session dict as the 'job' as it has 'latest_image'
                frame_refresh_cb=_force_refresh
            )
            return answer
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @app.get("/api/computer/surface")
    async def computer_surface_sse(session_id: str, ts: Optional[int] = None):
        session_id = str(session_id or "").strip()

        async def event_generator():
            import base64
            last_version = -1
            while True:
                async with computer_surface_lock:
                    session = computer_surface_sessions.get(session_id)
                if not session:
                    break

                version = int(session.get("latest_frame_version", 0) or 0)
                if version != last_version:
                    last_version = version
                    payload = {
                        "type": "screenshot",
                        "image": base64.b64encode(session.get("latest_frame")).decode("ascii") if session.get("latest_frame") else "",
                        "surface_metrics": session.get("surface_metrics"),
                        "url": session.get("current_url"),
                        "title": session.get("current_title"),
                        "surface_seq": version
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                # Also send periodic keepalives or state updates
                await asyncio.sleep(0.12)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.post("/api/computer/confirm")
    async def computer_surface_confirm(req: ComputerConfirmRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}

        session["pending_confirmation"] = None
        session["user_approved"] = req.approved
        # Signal the waiting loop if any
        return {"success": True}

    @app.post("/api/computer/resume")
    async def computer_surface_resume(req: ComputerResumeRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Surface session not found."}

        session["pending_manual_takeover"] = None
        session["state"] = "running"
        return {"success": True}

    @app.post("/api/computer/stop")
    async def computer_surface_stop(req: ComputerSurfaceResetRequest):
        session_id = str(req.session_id or "").strip()
        async with computer_surface_lock:
            session = computer_surface_sessions.get(session_id)
        if session:
            session["state"] = "stopped"
            session["closing"] = True
            # We don't necessarily pop it immediately to allow last looks?
            # But the frontend calls stop to actually end it.
            # Usually stop = reset/close.
        return await computer_surface_reset(req)



