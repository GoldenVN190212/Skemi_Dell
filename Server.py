import asyncio
import base64
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import warnings
import time
import ctypes

# On networks behind a TLS-inspecting proxy (common on managed/corporate
# machines), Python libraries that bundle their own CA list (certifi —
# requests, httpx's default) fail to validate otherwise-legitimate HTTPS
# endpoints like Google's cert servers, even though the OS trust store
# already trusts the proxy's root CA. `truststore` bridges Python's ssl
# module to the OS-native trust store instead, fixing this at the source
# rather than disabling certificate verification (which the codebase
# resorted to in a couple of places before this was added). Safe no-op
# if the package isn't installed.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

# v8.6: Force Per-Monitor DPI awareness to ensure accurate coordinate capture and display enumeration
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore", message=r"Using `TRANSFORMERS_CACHE` is deprecated.*", category=FutureWarning)
warnings.filterwarnings("ignore", message=r".*on_event is deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import httpx
import uvicorn
from urllib.parse import urlparse
try:
    # Credential-free Firebase ID token signature verification (fetches Google's
    # public certs over HTTPS — no service-account key needed). Used to replace
    # the base64-decode-without-verification path in _resolve_account_id so a
    # forged `uid` claim can no longer read/write another account's data.
    from google.oauth2 import id_token as _google_id_token
    from google.auth.transport import requests as _google_auth_requests
    from google.auth import exceptions as _google_auth_exceptions
    _google_auth_request = _google_auth_requests.Request()
    _FIREBASE_TOKEN_VERIFY_AVAILABLE = True
except Exception:
    _FIREBASE_TOKEN_VERIFY_AVAILABLE = False
from fastapi import FastAPI, Body, File, HTTPException, Request, UploadFile, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import difflib
import session_context as ephemeral_session_store
import browser_worker
import computer_webrtc
import desktop_companion
import session_store
from skemi_memory_hub import SkemiMemoryHub
import ChatBackend as backend
import skemi_computer_backend
import skemi_local_computer_backend

app: FastAPI = backend.app


def _launch_feature_services() -> None:
    """Best-effort auto-start of the embedded feature services that power the
    "Arena" (gamification) and "Skemi CLI" (workspace) sections.

    Additive & safe: each service is skipped if its port is already listening
    (so uvicorn --reload never double-spawns), if Node or the folder is missing,
    or if disabled via SKEMI_AUTOSTART_FEATURES=0. Never raises into startup.
    """
    if os.environ.get("SKEMI_AUTOSTART_FEATURES", "1").strip() not in ("1", "true", "True"):
        return
    import socket
    import subprocess

    def _pick(*cands):
        for c in cands:
            if (c / "server.js").is_file():
                return c
        return cands[0]

    parent = BASE_DIR.parent
    chat_port = int(os.getenv("SKEMMA_CHAT_PORT", os.getenv("SKEMI_CHAT_PORT", "8001")))
    # Prefer the copies merged INTO Skemi (1); fall back to the original siblings.
    services = [
        ("Arena (gamification)", 5000, _pick(BASE_DIR / "gamification" / "backend", parent / "gamification" / "backend")),
        ("Skemi CLI (workspace)", 3000, _pick(BASE_DIR / "skemi_cli_web", parent / "Skemi CLI Web")),
        ("Chat (real-time signaling)", chat_port, _pick(
            BASE_DIR / "skemma_chat" / "backend",
            parent / "Skemma-main (1)" / "Skemma-main" / "Skemma-main (1) (1)",
        )),
    ]
    node = shutil.which("node")
    if not node:
        print("[FEATURES] Node not found on PATH — Arena/Skemi CLI sections will show an offline notice.")
        return
    for name, port, cwd in services:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.4)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    continue  # already running — leave it alone
            if not (cwd.is_dir() and (cwd / "server.js").is_file()):
                print(f"[FEATURES] {name}: server.js not found at {cwd} — skipped.")
                continue
            creationflags = 0
            if os.name == "nt":
                # New process group + no console window so it dies cleanly and stays quiet.
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x08000000
            # Pin the child's PORT explicitly. The CLI service reads
            # process.env.PORT and would otherwise inherit OUR PORT (e.g. 8010
            # from the launcher/preview) and fail to bind. Arena hardcodes 5000
            # and ignores this — harmless to set.
            child_env = dict(os.environ)
            child_env["PORT"] = str(port)
            subprocess.Popen(
                [node, "server.js"],
                cwd=str(cwd),
                env=child_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            print(f"[FEATURES] launching {name} on :{port}")
        except Exception as exc:  # noqa: BLE001 — auto-start must never break the app
            print(f"[FEATURES] could not start {name}: {exc}")


_launch_feature_services()

# ── Legion AI Agent Control — independent multi-agent command center ──────────
try:
    import legion_backend
    app.include_router(legion_backend.router)
    print("[LEGION] Agent Control router mounted at /api/legion")
except Exception as _legion_exc:  # never block boot
    print(f"[LEGION] router not loaded: {_legion_exc}")

try:
    import lab_backend
    app.include_router(lab_backend.router)
    print("[LAB] Idea Lab router mounted at /api/lab")
except Exception as _lab_exc:  # never block boot
    print(f"[LAB] router not loaded: {_lab_exc}")

# ── Skemi Quiz — real matches (ELO, matchmaking, WebSocket PvP, bot training) ──
# Lives at gamification/skemi_quiz/backend (a namespace package, no __init__.py
# at the skemi_quiz/ level — needs `gamification/` on sys.path to resolve the
# `skemi_quiz.backend...` import, per that module's own app.py docstring).
try:
    _quiz_pkg_root = str(BASE_DIR / "gamification")
    if _quiz_pkg_root not in sys.path:
        sys.path.insert(0, _quiz_pkg_root)
    from skemi_quiz.backend.routes import api_router as _quiz_api_router
    from skemi_quiz.backend.models.db import init_db as _quiz_init_db
    _quiz_init_db()
    app.include_router(_quiz_api_router, prefix="/api/quiz")
    _quiz_frontend_dir = str(BASE_DIR / "gamification" / "skemi_quiz" / "frontend")
    app.mount("/quiz", StaticFiles(directory=_quiz_frontend_dir, html=True), name="skemi-quiz-frontend")
    print("[QUIZ] Skemi Quiz router mounted at /api/quiz, frontend at /quiz")
except Exception as _quiz_exc:  # never block boot
    print(f"[QUIZ] router not loaded: {_quiz_exc}")

# Shared Global State
AUTH_DB_PATH = os.path.join(str(BASE_DIR), "skemi_auth.db")
SEARCH_JOB_TYPE = "search_analysis_v4"
SEARCH_JOB_TTL_SECONDS = 6 * 60 * 60
SEARCH_JOB_MAX_CACHE_ROWS = 18
search_jobs: Dict[str, Dict[str, Any]] = {}
search_job_lock = asyncio.Lock()
ai_chat_jobs: Dict[str, Dict[str, Any]] = {} # Track global chat progress
AI_CHAT_JOB_TTL_SECONDS = 900
studio_jobs: Dict[str, Dict[str, Any]] = {} # Track Studio generation as background jobs (resume on navigation)
STUDIO_JOB_TTL_SECONDS = 1800
# Real asyncio.Task handles for cancellable background jobs (search + studio),
# keyed by job_id. Cancelling here actually interrupts the coroutine (raises
# CancelledError inside it, including mid-await on an LLM call) — not just a
# status flag the job would ignore. Product decision: AI compute should STOP
# the moment the user closes the tab (saves tokens/compute for someone who's
# gone), while whatever was already logged/produced up to that point stays.
_cancellable_job_tasks: Dict[str, "asyncio.Task"] = {}
global_agent_jobs: Dict[str, Dict[str, Any]] = {} # Track global agent sessions
SESSION_TTL = timedelta(hours=6)
chat_sessions: Dict[str, Dict[str, Any]] = {}
agent_session_store = session_store.SQLiteSessionStore()
shared_memory_hub = SkemiMemoryHub()

class SkemiGlobalCache:
    def __init__(self, db_path: str = "skemi_cache.db"):
        self.db_path = os.path.join(os.path.dirname(__file__), db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT UNIQUE,
                    result TEXT,
                    query_type TEXT,
                    created_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query ON ai_cache(query)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON ai_cache(query_type)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ui_translation_cache (
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (source_lang, target_lang, text_hash)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ui_translation_langs "
                "ON ui_translation_cache(source_lang, target_lang)"
            )


    def get(
        self,
        query: str,
        query_type: str = "general",
        threshold: float = 0.88,
        max_age_seconds: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        query_clean = query.strip().lower()
        if not query_clean: return None
        
        try:
            now_ts = time.time()

            def _is_expired(created_at: Any) -> bool:
                if not max_age_seconds:
                    return False
                try:
                    created_value = float(created_at or 0)
                except Exception:
                    return True
                return (now_ts - created_value) > float(max_age_seconds)

            # Exact match first
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT result, created_at FROM ai_cache WHERE query = ? AND query_type = ?",
                    (query_clean, query_type),
                )
                row = cursor.fetchone()
                if row:
                    if _is_expired(row[1]):
                        return None
                    # print(f"CACHE HIT (Exact): '{query_clean}'")
                    return json.loads(row[0])

                # Semantic/Fuzzy match
                cursor = conn.execute(
                    "SELECT query, result, created_at FROM ai_cache WHERE query_type = ?",
                    (query_type,),
                )
                potential_matches = cursor.fetchall()
                
                best_match = None
                highest_score = 0.0
                
                # Use difflib for similarity
                for cached_query, cached_result, created_at in potential_matches:
                    if _is_expired(created_at):
                        continue
                    score = difflib.SequenceMatcher(None, query_clean, cached_query).ratio()
                    if score > highest_score:
                        highest_score = score
                        best_match = cached_result

                if highest_score >= threshold:
                    # print(f"CACHE HIT (Fuzzy {highest_score:.2f}): '{query_clean}' matching '{best_match[:30]}...'")
                    return json.loads(best_match)
        except Exception as e:
            # print(f"CACHE GET ERROR: {e}")
            pass
        return None

    def set(self, query: str, result: Dict[str, Any], query_type: str = "general"):
        query_clean = query.strip().lower()
        if not query_clean: return
        result_json = json.dumps(result)
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO ai_cache (query, result, query_type, created_at) VALUES (?, ?, ?, ?)",
                    (query_clean, result_json, query_type, time.time())
                )
        except Exception as e:
            # print(f"CACHE SET ERROR: {e}")
            pass

    def _ui_translation_hash(self, text: str) -> str:
        normalized = str(text or "").strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_ui_translation(self, text: str, source: str, target: str) -> Optional[str]:
        normalized = str(text or "").strip()
        if not normalized:
            return None

        source_lang = str(source or "auto").strip().lower() or "auto"
        target_lang = str(target or "en").strip().lower() or "en"
        text_hash = self._ui_translation_hash(normalized)

        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT translated_text
                    FROM ui_translation_cache
                    WHERE source_lang = ? AND target_lang = ? AND text_hash = ?
                    """,
                    (source_lang, target_lang, text_hash),
                ).fetchone()
                if row and row[0]:
                    return str(row[0])
        except Exception as exc:
            # print(f"UI TRANSLATION CACHE GET ERROR: {exc}")
            pass
        return None

    def get_ui_translations(self, texts: List[str], source: str, target: str) -> Dict[str, str]:
        normalized_texts = [str(item or "").strip() for item in texts or []]
        normalized_texts = [item for item in normalized_texts if item]
        if not normalized_texts:
            return {}

        source_lang = str(source or "auto").strip().lower() or "auto"
        target_lang = str(target or "en").strip().lower() or "en"
        hash_map = {self._ui_translation_hash(text): text for text in normalized_texts}
        placeholders = ",".join("?" for _ in hash_map)
        if not placeholders:
            return {}

        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    f"""
                    SELECT text_hash, translated_text
                    FROM ui_translation_cache
                    WHERE source_lang = ? AND target_lang = ? AND text_hash IN ({placeholders})
                    """,
                    [source_lang, target_lang, *hash_map.keys()],
                ).fetchall()
            return {
                hash_map[str(text_hash)]: str(translated_text)
                for text_hash, translated_text in rows
                if str(text_hash) in hash_map and translated_text
            }
        except Exception as exc:
            # print(f"UI TRANSLATION CACHE BATCH GET ERROR: {exc}")
            return {}

    def set_ui_translations(self, translations: Dict[str, str], source: str, target: str) -> None:
        items = []
        source_lang = str(source or "auto").strip().lower() or "auto"
        target_lang = str(target or "en").strip().lower() or "en"
        for source_text, translated_text in (translations or {}).items():
            normalized_source = str(source_text or "").strip()
            normalized_translated = str(translated_text or "").strip()
            if not normalized_source or not normalized_translated:
                continue
            items.append(
                (
                    source_lang,
                    target_lang,
                    self._ui_translation_hash(normalized_source),
                    normalized_source,
                    normalized_translated,
                    time.time(),
                )
            )
        if not items:
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO ui_translation_cache
                    (source_lang, target_lang, text_hash, source_text, translated_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    items,
                )
        except Exception as exc:
            # print(f"UI TRANSLATION CACHE SET ERROR: {exc}")
            pass

# agent_session_store moved to top
# shared_memory_hub moved to top

global_cache = SkemiGlobalCache()

TEMP_LOCAL_STORAGE_KEYS = {
    "skemi_search_history_v1",
    "skemi_search_result_cache_v3",
    "skemi_job_notify_state_v1",
    "skemi_job_event_v3",
    "skemi_ai_working_v1",
    "skemi_ai_pending_command_v1",
    "skemi_search_last_command_v3",
    "skemi_surface_session_id_v1",
    "skemi_active_computer_session_v1",
    "skemi_active_workflow_id_v1",
}

TEMP_SESSION_STORAGE_KEYS = {
    "skemi_search_state_v7",
    "skemi_search_analysis_v5",
    "skemi_search_active_job_v4",
    "skemi_background_jobs_v3",
    "skemi_notebook_search_job_v3",
    "skemi_search_notebook_active",
    "skemi_search_notebook_q",
    "skemi_search_notebook_deep",
    "skemi_global_pulse_notebook",
}


def _safe_remove_tree(path: Path) -> None:
    try:
        if path.exists() and path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


async def _cleanup_skemi_runtime_data(*, user_id: str = "default_user", session_id: str = "") -> Dict[str, Any]:
    deleted: Dict[str, Any] = {
        "chat_sessions": 0,
        "search_jobs": 0,
        "memory_events": 0,
        "computer_sessions": 0,
        "surface_sessions": 0,
        "browser_profiles": 0,
    }

    sid = str(session_id or "").strip()
    if sid:
        if chat_sessions.pop(sid, None) is not None:
            deleted["chat_sessions"] += 1
        if hasattr(backend, "delete_session"):
            with contextlib.suppress(Exception):
                backend.delete_session(sid)

    deleted["memory_events"] = shared_memory_hub.clear(user_id=str(user_id or "default_user"))

    async with search_job_lock:
        deleted["search_jobs"] = len(search_jobs)
        search_jobs.clear()

    with contextlib.suppress(Exception):
        stale_ids = list(global_agent_jobs.keys())
        for job_id in stale_ids:
            job = global_agent_jobs.pop(job_id, None)
            if job:
                deleted["computer_sessions"] += 1
                agent_session_store.delete(job_id)
        await browser_worker.browser_worker_host.shutdown()

    with contextlib.suppress(Exception):
        async with skemi_computer_backend.computer_surface_lock:
            surface_ids = list(skemi_computer_backend.computer_surface_sessions.keys())
            sessions_to_close = [skemi_computer_backend.computer_surface_sessions.pop(item, None) for item in surface_ids]
            deleted["surface_sessions"] = len([item for item in sessions_to_close if item])
            skemi_computer_backend.computer_surface_pool.clear()
        for session in sessions_to_close:
            if session:
                with contextlib.suppress(Exception):
                    await skemi_computer_backend._surface_close_worker(session)

    with contextlib.suppress(Exception):
        async with skemi_computer_backend.computer_sessions_lock:
            deleted["computer_sessions"] += len(skemi_computer_backend.computer_sessions)
            skemi_computer_backend.computer_sessions.clear()

    browser_root = Path(skemi_computer_backend.DATA_DIR) / "browser_profiles"
    if browser_root.exists():
        for child in browser_root.iterdir():
            if child.is_dir():
                _safe_remove_tree(child)
                deleted["browser_profiles"] += 1

    return deleted

# Search Configuration moved to top


def _normalize_ui_translation_text(value: Any) -> str:
    """Clean up an LLM translation string. Small models sometimes wrap output
    like `{'ar': 'تسجيل الدخول'}` or `["مرحبا"]` or `Output: مرحبا` instead of
    returning the bare translation — strip those wrappers so the value we
    cache is the plain translated text."""
    if value is None:
        return ""
    if isinstance(value, dict):
        # qwen2.5:3b often returns {"ar": "..."} or {"text": "..."}
        for k in ("translation", "text", "output", "result"):
            if k in value and value[k]:
                return _normalize_ui_translation_text(value[k])
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    if isinstance(value, list):
        for item in value:
            normalized = _normalize_ui_translation_text(item)
            if normalized:
                return normalized
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Strip surrounding quotes if the entire string is quoted.
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        if len(text) >= 2:
            text = text[1:-1].strip()
    # Strip JSON-shaped wrappers the LLM emitted as raw text.
    # Examples seen: "{'ar': 'تسجيل الدخول'}", "{\"text\": \"...\"}", "['مرحبا']"
    if text.startswith("{") and text.endswith("}"):
        import re as _re
        match = _re.search(r"['\"]\s*[a-z_-]{1,8}\s*['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1).strip()
    if text.startswith("[") and text.endswith("]"):
        import re as _re
        match = _re.search(r"['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1).strip()
    # Strip common labels like "Translation:" or "Output:"
    for prefix in ("Translation:", "Output:", "Result:", "Answer:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    return text


def _chunk_ui_translation_texts(texts: List[str], max_items: int = 20, max_chars: int = 2600) -> List[List[str]]:
    chunks: List[List[str]] = []
    current: List[str] = []
    current_chars = 0
    for text in texts:
        item = _normalize_ui_translation_text(text)
        if not item:
            continue
        item_len = len(item)
        if current and (len(current) >= max_items or current_chars + item_len > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_len
    if current:
        chunks.append(current)
    return chunks


def _extract_json_object(raw: Any) -> Dict[str, Any]:
    payload = str(raw or "").strip()
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    try:
        match = re.search(r"\{[\s\S]*\}", payload)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return {}


async def _translate_via_web(texts: List[str], source_lang: str, target_lang: str) -> Dict[str, str]:
    """LLM-free UI translation via the free Google endpoint. Works without Ollama
    — only needs internet. verify=False because this host can't verify external
    certs (TLS inspection/proxy). Newline-batched to cut round-trips, with a
    per-string fallback. Best-effort; never raises."""
    out: Dict[str, str] = {}
    if not texts:
        return out
    src = "auto" if (not source_lang or source_lang == "auto") else source_lang
    import urllib.parse
    import asyncio

    def _join_segs(data: Any) -> str:
        try:
            segs = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else []
            return "".join(seg[0] for seg in segs if isinstance(seg, list) and seg and isinstance(seg[0], str))
        except Exception:
            return ""

    sem = asyncio.Semaphore(4)

    async def _raw(client, q: str):
        """One Google call for a (possibly newline-joined) query. Returns the
        translated text or None. Retries on 429 with backoff."""
        for _attempt in range(3):
            try:
                url = (f"https://translate.googleapis.com/translate_a/single"
                       f"?client=gtx&sl={src}&tl={target_lang}&dt=t&q={urllib.parse.quote(q)}")
                r = await client.get(url)
                if r.status_code == 200:
                    return _join_segs(r.json())
                if r.status_code == 429:
                    await asyncio.sleep(0.7 * (_attempt + 1))
                    continue
            except Exception:
                await asyncio.sleep(0.25)
        return None

    async def _one(client, text: str):
        async with sem:
            tr = await _raw(client, text)
        return text, (tr or "").strip()

    import re as _re
    _FW_DIGITS = {0xFF10 + i: 0x30 + i for i in range(10)}  # ０-９ → 0-9
    _NUM_LINE = _re.compile(r'^\s*(\d{1,3})\s*[\.\)、．:]\s*(.+)$')

    def _parse_numbered(tr: str, group: List[str]):
        by_idx: Dict[int, str] = {}
        for line in tr.translate(_FW_DIGITS).split("\n"):
            m = _NUM_LINE.match(line)
            if not m:
                continue
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(group) and idx not in by_idx:
                by_idx[idx] = m.group(2).strip()
        if len(by_idx) == len(group):
            return {group[i]: by_idx[i] for i in range(len(group)) if by_idx.get(i)}
        return None

    async def _chunk(client, group: List[str]) -> Dict[str, str]:
        # Translate up to ~20 strings in ONE request to avoid the per-string rate
        # limiting that stalls a full-page sweep. NUMBERED lines survive target
        # reflow (CJK has no spaces and merges bare newlines) so we can realign the
        # response by index; we then fall back to bare-newline, then per-string, so
        # correctness always holds even if the batching heuristics miss.
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(group))
        async with sem:
            tr = await _raw(client, numbered)
        if tr:
            parsed = _parse_numbered(tr, group)
            if parsed is not None:
                return parsed
            parts = tr.split("\n")
            if len(parts) == len(group):
                cleaned = [_re.sub(r'^\s*\d{1,3}\s*[\.\)、．:]\s*', '', p).strip() for p in parts]
                return {group[i]: cleaned[i] for i in range(len(group)) if cleaned[i]}
        pairs: Dict[str, str] = {}
        for res in await asyncio.gather(*[_one(client, t) for t in group], return_exceptions=True):
            if isinstance(res, tuple) and res[1]:
                pairs[res[0]] = res[1]
        return pairs

    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            groups = [texts[i:i + 20] for i in range(0, len(texts), 20)]
            for res in await asyncio.gather(*[_chunk(client, g) for g in groups], return_exceptions=True):
                if isinstance(res, dict):
                    out.update(res)
    except Exception:
        pass
    return out


async def _translate_ui_texts_with_model(texts: List[str], source: str = "auto", target: str = "en") -> List[str]:
    originals = [_normalize_ui_translation_text(item) for item in (texts or [])]
    originals = [item for item in originals if item]
    if not originals:
        return []

    source_lang = str(source or "auto").strip().lower() or "auto"
    target_lang = str(target or "en").strip().lower() or "en"
    if source_lang == target_lang:
        return originals

    # Translation needs a model that's actually reachable. Order of preference:
    #   1. Explicit SKEMI_TRANSLATE_MODEL env var (user override)
    #   2. Backend MODEL_ROUTER / MODEL_MAIN (the main chat model)
    #   3. qwen2.5:1.5b — small local multilingual fallback that ships if the
    #      backend's primary models are Ollama-Cloud (which require auth our
    #      sandbox doesn't have). Pre-tested to handle 60+ languages including
    #      Arabic, Chinese, Japanese.
    candidates = []
    env_override = os.getenv("SKEMI_TRANSLATE_MODEL", "").strip()
    if env_override:
        candidates.append(env_override)
    # Preferred cloud translator. gemini-3-flash-preview:cloud returns HTTP 403
    # on this account, so minimax-m2:cloud (verified working after `ollama signin`)
    # is the working default; MODEL_ROUTER / MODEL_MAIN below cover overrides.
    candidates.append("devstral-2:123b-cloud")
    candidates.append(getattr(backend, "MODEL_ROUTER", None))
    candidates.append(getattr(backend, "MODEL_MAIN", None))
    candidates.append("qwen2.5:3b")     # 3B fallback — handles JSON schema reliably when offline / cloud auth missing
    candidates.append("qwen2.5:1.5b")   # 1.5B last-resort fallback
    model = next((m for m in candidates if m), None)
    if not model or not hasattr(backend, "_generate_text_once"):
        return originals

    translations_map: Dict[str, str] = dict(global_cache.get_ui_translations(originals, source_lang, target_lang))
    misses = [text for text in originals if text not in translations_map]

    # Try each candidate model in order until one returns real translations.
    # Cloud-only models in our sandbox return "" with `unauthorized` — fall
    # through to qwen2.5:1.5b which is local.
    valid_candidates = [m for m in candidates if m]

    async def _call_model_for_chunk(chunk_):
        prompt = (
            "Translate this JSON array of static web UI strings.\n"
            f"Source language: {source_lang}\n"
            f"Target language: {target_lang}\n"
            "Return JSON only with schema {\"translations\": [ ... ]}.\n"
            "Rules:\n"
            "- Keep the exact array order and same number of items.\n"
            "- Preserve placeholders like {name}, {count}, HTML entities, punctuation, emoji, and line breaks.\n"
            "- Keep product names such as Skemi and Skemma unchanged.\n"
            "- Do not translate tokens like __CHAT_BRAND_0__ or __UI_BRAND_0__.\n\n"
            f"Input JSON:\n{json.dumps(chunk_, ensure_ascii=False)}"
        )
        for candidate_model in valid_candidates:
            raw = await backend._generate_text_once(
                candidate_model,
                prompt,
                timeout=max(30.0, min(90.0, 18.0 + len(chunk_) * 2.0)),
                num_predict=max(320, len(chunk_) * 80),
            )
            if raw and raw.strip():
                return raw, candidate_model
        return "", ""

    # ── FAST PATH FIRST: the free web translator ──────────────────────────────
    # It's concurrent and localizes a whole page in ~1-2s across 100+ languages,
    # versus the LLM's ~6s PER STRING on a cold cache (which left cold languages
    # untranslated because the client's sweep windows expired first). Try it for
    # every miss up front; the LLM below only mops up whatever the web path can't
    # reach (offline, or items it returns unchanged). Brand names are already
    # tokenised by the client (__UI_BRAND_n__), which the web API leaves intact.
    # Both paths write the cache, so repeat visits are instant and fully offline.
    if misses:
        try:
            web_pairs = await _translate_via_web(misses, source_lang, target_lang)
        except Exception:
            web_pairs = {}
        web_pairs = {k: v for k, v in (web_pairs or {}).items() if v and v.strip() and v.strip() != k}
        if web_pairs:
            translations_map.update(web_pairs)
            try:
                global_cache.set_ui_translations(web_pairs, source_lang, target_lang)
            except Exception:
                pass
        misses = [text for text in originals if text not in translations_map]

    # ── LLM BACKSTOP: only whatever the web path couldn't translate ────────────
    for chunk in _chunk_ui_translation_texts(misses):
        raw, used_model = await _call_model_for_chunk(chunk)
        parsed = _extract_json_object(raw)
        chunk_translations = parsed.get("translations") if isinstance(parsed, dict) else None

        if isinstance(chunk_translations, list) and len(chunk_translations) == len(chunk):
            resolved = {
                source_text: _normalize_ui_translation_text(chunk_translations[idx]) or source_text
                for idx, source_text in enumerate(chunk)
            }
            translations_map.update(resolved)
            global_cache.set_ui_translations(resolved, source_lang, target_lang)
            continue

        fallback_pairs: Dict[str, str] = {}
        for source_text in chunk:
            cached_single = global_cache.get_ui_translation(source_text, source_lang, target_lang)
            if cached_single:
                fallback_pairs[source_text] = cached_single
                continue

            single_prompt = (
                "Translate the following static web UI text exactly.\n"
                f"Source language: {source_lang}\n"
                f"Target language: {target_lang}\n"
                "Rules:\n"
                "- Return only the translated text.\n"
                "- Preserve placeholders like {name}, HTML entities, punctuation, emoji, and line breaks.\n"
                "- Keep product names such as Skemi and Skemma unchanged.\n"
                "- Do not translate tokens like __CHAT_BRAND_0__ or __UI_BRAND_0__.\n\n"
                f"Text:\n{source_text}"
            )
            translated = ""
            for candidate_model in valid_candidates:
                translated = await backend._generate_text_once(candidate_model, single_prompt, timeout=25.0, num_predict=220)
                if translated and translated.strip():
                    break
            fallback_pairs[source_text] = _normalize_ui_translation_text(translated) or source_text

        translations_map.update(fallback_pairs)
        global_cache.set_ui_translations(fallback_pairs, source_lang, target_lang)

    return [translations_map.get(text, text) for text in originals]



def _resolve_loopback_host(host: str) -> str:
    host = str(host or "").strip() or "127.0.0.1"
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def _normalize_chat_server_url(raw_url: Optional[str], default_port: int) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return f"http://127.0.0.1:{default_port}/Chat.html"

    candidate = candidate.rstrip("/")
    if candidate.endswith("/Chat.html"):
        return candidate
    return f"{candidate}/Chat.html"


SERVER_HOST = os.getenv("SKEMI_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SKEMI_PORT", "8010"))
SERVER_CONNECT_HOST = _resolve_loopback_host(os.getenv("SKEMI_CONNECT_HOST", SERVER_HOST))
SERVER_BASE_URL = f"http://{SERVER_CONNECT_HOST}:{SERVER_PORT}"
CHAT_SERVER_PORT = int(os.getenv("SKEMMA_CHAT_PORT", os.getenv("SKEMI_CHAT_PORT", "8001")))
CHAT_SERVER_URL = _normalize_chat_server_url(
    os.getenv("SKEMI_CHAT_SERVER_URL") or os.getenv("SKEMMA_CHAT_SERVER_URL"),
    CHAT_SERVER_PORT,
)
CHAT_SERVER_BASE_URL = CHAT_SERVER_URL[:-10] if CHAT_SERVER_URL.endswith("/Chat.html") else CHAT_SERVER_URL.rstrip("/")

# Keep the local backend and proxy on the same runtime config.
os.environ["SKEMMA_CHAT_PORT"] = str(CHAT_SERVER_PORT)
os.environ["SKEMMA_CHAT_SERVER_URL"] = CHAT_SERVER_BASE_URL
os.environ["SKEMI_CHAT_SERVER_URL"] = CHAT_SERVER_URL

current_ai_server_url = str(os.getenv("SKEMMA_AI_SERVER_URL", "")).rstrip("/")
legacy_ai_server_urls = {
    "",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://0.0.0.0:8000",
}
if current_ai_server_url in legacy_ai_server_urls:
    os.environ["SKEMMA_AI_SERVER_URL"] = SERVER_BASE_URL

FRONTEND_ROOT = Path(__file__).resolve().parent
# Chat (Messenger) is fully consolidated INSIDE Skemi (1): UI/assets at
# ./skemma_chat and the real-time signaling backend (Socket.IO + uploads,
# auto-launched by _launch_feature_services) at ./skemma_chat/backend. Prefer
# the in-folder copy; fall back to the legacy external sibling only if it's
# ever missing (same defensive pattern as the Arena/Skemi-CLI services above).
_SKEMMA_CHAT_LOCAL = FRONTEND_ROOT / "skemma_chat"
_SKEMMA_CHAT_EXTERNAL = Path(__file__).resolve().parent.parent / "Skemma-main (1)" / "Skemma-main" / "Skemma-main (1) (1)"
SKEMMA_CHAT_ROOT = _SKEMMA_CHAT_LOCAL if (_SKEMMA_CHAT_LOCAL / "Chat.html").exists() else _SKEMMA_CHAT_EXTERNAL

# Core Backends moved to top
app.skemi_search_engine = getattr(backend, "search_engine", None)

# CORSMiddleware moved to top
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add auth middleware for production-level authentication
try:
    from auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
except Exception as e:
    print(f"[AUTH] Middleware not loaded: {e}")

# CSRF / drive-by guard. The server controls the real desktop (open apps, type,
# click), so a state-changing request must NOT be drivable by a random website the
# user happens to visit: a browser will SEND a cross-origin POST even though CORS
# blocks reading the response — the side effect (a desktop command) still fires.
# Reject state-changing /api/ calls whose Origin is a DIFFERENT host than the
# server. Same-origin (the Skemi frontend), no-Origin (curl / internal), and
# localhost are allowed; only genuine cross-origin browser requests are blocked.
@app.middleware("http")
async def _same_origin_guard(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlparse
            oh = urlparse(origin).netloc.lower()
            host = (request.headers.get("host") or "").lower()
            oh_host = oh.split(":")[0]
            if oh != host and oh_host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
                return JSONResponse(status_code=403, content={
                    "success": False, "error": "cross_origin_blocked",
                    "message": "Yêu cầu từ nguồn khác bị chặn (bảo vệ chống điều khiển từ web lạ)."})
    return await call_next(request)


# Register the rebuilt Computer backends before the legacy routes below so the
# live app resolves the new Virtual Browser / Local Computer handlers first.
skemi_computer_backend.register(app)
skemi_local_computer_backend.register(app)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    # Bind the calling account so token spend during this request is metered
    # against the right tier. Set before call_next so the endpoint inherits it.
    try:
        import entitlements as _ent
        _ent.set_current_account(_resolve_account_id(request))
    except Exception:
        pass
    response = await call_next(request)
    path = str(request.url.path or "")
    if path in {"/", "/Home.html", "/Search.html", "/Settings.html", "/Quiz.html", "/Chat.html", "/PromptAgent.html", "/Computer.html"} or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/ping")
async def ping():
    return {"status": "ok", "server": "skemi-python", "time": str(datetime.utcnow())}

# ─── Authentication API ─────────────────────────────────────────────────────────

from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

class AuthResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    token: Optional[str] = None
    role: Optional[str] = None

@app.post("/api/auth/register", response_model=AuthResponse)
async def auth_register(payload: RegisterRequest):
    """Register new user account"""
    email = (payload.email or "").strip().lower()
    if email:
        if "@" not in email:
            raise HTTPException(status_code=400, detail="Email không hợp lệ")
        domain = email.split("@")[-1]
        trusted_domains = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "me.com", "live.com", "msn.com"}
        if domain not in trusted_domains:
            raise HTTPException(
                status_code=400,
                detail="Email domain không được hỗ trợ để tránh tài khoản clone"
            )
            
    from auth_manager import get_auth_manager
    auth = get_auth_manager()
    
    success, message, user_id = auth.register_user(
        username=payload.username,
        password=payload.password,
        email=email or None,
        role="user"
    )
    
    return AuthResponse(
        success=success,
        message=message,
        user_id=user_id if success else None
    )

@app.post("/api/auth/login")
async def auth_login(payload: LoginRequest, request: Request):
    from auth_manager import get_auth_manager
    auth = get_auth_manager()

    # Get client info
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    success, message, user_id, token = auth.authenticate_user(
        username=payload.username,
        password=payload.password,
        ip_address=ip_address,
        user_agent=user_agent
    )

    if not success or not token:
        return {"success": False, "message": message or "Đăng nhập thất bại"}

    # Get user role
    role = None
    if user_id:
        user = auth.get_user(user_id)
        if user:
            role = user.role

    from fastapi.responses import JSONResponse
    resp = JSONResponse(content={
        "success": True,
        "message": message,
        "token": token,
        "user_id": user_id,
        "username": payload.username,
        "role": role
    })
    resp.set_cookie(
        key="skemi_token",
        value=token,
        httponly=True,
        secure=False,      # True khi dùng HTTPS
        samesite="lax",
        max_age=7 * 24 * 3600  # 7 ngày
    )
    return resp

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get("skemi_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if token:
        with contextlib.suppress(Exception):
            from auth_manager import get_auth_manager
            get_auth_manager().logout(token)
    resp = {"success": True, "message": "Đã đăng xuất"}
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content=resp)
    resp.delete_cookie("skemi_token")
    return resp

@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Get current user info"""
    from auth_manager import get_auth_manager
    auth = get_auth_manager()
    
    # Get token
    token = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("skemi_token", "")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    valid, payload = auth.verify_token(token)
    if not valid or not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = payload.get("user_id")
    user = auth.get_user(user_id) if user_id else None
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role
    }


def _get_user_id(request: Request) -> str:
    try:
        from auth_manager import get_auth_manager
        auth = get_auth_manager()

        # Authorization header
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:].strip()
            if token:
                valid, payload = auth.verify_token(token)
                if valid and payload:
                    return str(payload.get("user_id", ""))

        # Cookie — thử nhiều tên
        for name in ["skemi_token", "auth_token", "token"]:
            token = request.cookies.get(name, "")
            if token:
                valid, payload = auth.verify_token(token)
                if valid and payload:
                    return str(payload.get("user_id", ""))
    except Exception:
        pass
    return ""


FIREBASE_PROJECT_ID = os.getenv("SKEMI_FIREBASE_PROJECT_ID", "skemma-efe9b")


def _decode_jwt_payload_unverified(token: str) -> dict:
    """Best-effort base64 decode of a JWT payload WITHOUT signature checks.

    ONLY used as a last-resort fallback in _verify_firebase_uid when Google's
    cert endpoint is genuinely unreachable (infra outage) — never as the
    primary path. See _verify_firebase_uid for the real, cryptographically
    verified path.
    """
    try:
        import base64 as _b64
        import json as _json
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        seg = parts[1]
        seg += "=" * (-len(seg) % 4)  # restore base64 padding
        raw = _b64.urlsafe_b64decode(seg.encode("ascii"))
        data = _json.loads(raw.decode("utf-8", "replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _verify_firebase_uid(token: str) -> Optional[str]:
    """Return the uid from a Firebase ID token ONLY if its signature, issuer,
    audience and expiry all check out — cryptographically verified against
    Google's public certs (no service-account key required).

    A tampered/forged token (e.g. hand-edited to claim someone else's uid)
    fails verification and returns None here, so the caller falls through to
    "guest" rather than trusting an attacker-controlled uid claim. This is
    what gates /api/user/data — without it, anyone could read or overwrite
    another account's synced data by sending a forged bearer token.

    Falls back to the unverified decode ONLY on a genuine network/transport
    failure reaching Google's cert endpoint (so an outage doesn't lock every
    legitimate user out) — never on a verification failure, which always
    means "reject this token."
    """
    if not token:
        return None
    if not _FIREBASE_TOKEN_VERIFY_AVAILABLE:
        payload = _decode_jwt_payload_unverified(token)
        return str(payload["uid"]) if payload.get("uid") else (str(payload["user_id"]) if payload.get("user_id") else (str(payload["sub"]) if payload.get("sub") else None))
    try:
        claims = _google_id_token.verify_firebase_token(
            token, _google_auth_request, audience=FIREBASE_PROJECT_ID
        )
        if not claims:
            return None
        uid = claims.get("user_id") or claims.get("uid") or claims.get("sub")
        return str(uid) if uid else None
    except ValueError:
        # Genuine verification failure: bad signature, expired, wrong
        # audience/issuer, malformed token. Reject — do NOT fall back.
        return None
    except (_google_auth_exceptions.TransportError, OSError, TimeoutError):
        # Couldn't reach Google's cert endpoint — infra hiccup, not an
        # attacker-controlled path. Degrade to unverified rather than lock
        # out every signed-in user during a transient outage.
        payload = _decode_jwt_payload_unverified(token)
        uid = payload.get("user_id") or payload.get("uid") or payload.get("sub")
        return str(uid) if uid else None
    except Exception:
        return None


def _resolve_account_id(request: Request) -> str:
    """Resolve a stable account id for entitlement/quota bookkeeping AND for
    gating per-account storage (/api/user/data) — so this uid must be trusted.

    Order: (1) verified server JWT user_id; (2) SIGNATURE-VERIFIED Firebase ID
    token uid, namespaced as ``fb:<uid>``; (3) ``guest``.
    """
    # 1) Authoritative server JWT.
    uid = _get_user_id(request)
    if uid:
        return str(uid)

    # 2) Firebase ID token (header or cookie) — cryptographically verified.
    candidates = []
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        candidates.append(header[7:].strip())
    for name in ["skemi_token", "auth_token", "token", "firebase_token", "idToken"]:
        c = request.cookies.get(name, "")
        if c:
            candidates.append(c)
    for tok in candidates:
        if not tok:
            continue
        fid = _verify_firebase_uid(tok)
        if fid:
            return "fb:" + str(fid)

    # 3) Anonymous.
    return "guest"


def _get_storage_account_id(request: Request) -> str:
    """Account id for per-user storage (user_data / settings).

    Unlike _get_user_id (which accepts only a verified server HS256 JWT and so
    rejects the Firebase ID tokens the live frontend actually sends — causing
    the /api/user/data 401s), this attributes the request to the same stable
    ``fb:<uid>`` namespace already used by entitlements via _resolve_account_id.
    Returns "" for anonymous/guest so callers keep their existing 401 behavior
    and the client falls back to localStorage.

    SECURITY: the Firebase uid is decoded WITHOUT signature verification (the
    same trust level as entitlement bookkeeping). Real RS256 verification of
    Firebase ID tokens is tracked as pre-launch hardening — do NOT rely on this
    for privileged access, only for per-account data partitioning.
    """
    acct = _resolve_account_id(request)
    if not acct or acct == "guest":
        return ""
    return acct


def _init_user_data_table():
    db = os.path.join(os.path.dirname(__file__), "skemi_auth.db")
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(user_id, namespace, key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_udm
            ON user_data(user_id, namespace)
        """)
        conn.commit()


_init_user_data_table()


@app.get("/api/user/profile")
async def get_user_profile(request: Request):
    user_id = _get_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    from auth_manager import get_auth_manager
    user = get_auth_manager().get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")

    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
    }


# ============================================================
# Entitlements / subscription tiers (token + feature metering)
# ============================================================
@app.get("/api/entitlements")
async def get_entitlements(request: Request):
    # NOTE: feature gating retuned 2026-07-01 to the 4-tier plan (see entitlements.py).
    """Return the caller's current tier, usage and the full plan catalog.

    Safe for anonymous callers (returns the ``guest``/free snapshot). The
    frontend uses this to gate features client-side and to render the current
    plan on the Subscription page + navbar.
    """
    try:
        import entitlements as _ent
        account = _resolve_account_id(request)
        return _ent.snapshot(account)
    except Exception as e:
        print(f"[ENTITLEMENTS] /api/entitlements failed: {e}")
        # Never break the UI on a metering hiccup — degrade to free.
        return {
            "account": "guest",
            "tier": "free",
            "error": "entitlements_unavailable",
        }


class SetTierPayload(BaseModel):
    account_id: Optional[str] = None
    tier: str
    source: Optional[str] = "admin"


@app.post("/api/entitlements/set-tier")
async def set_entitlement_tier(request: Request, payload: SetTierPayload):
    """Admin/payment hook to grant a tier to an account.

    Guarded by the ``SKEMI_ADMIN_KEY`` env secret (sent as ``X-Admin-Key``
    header or ``admin_key`` field). This is the seam a real payment gateway /
    back-office will call after a successful charge — Skemi does NOT process
    real payments here.
    """
    import entitlements as _ent

    admin_key = os.getenv("SKEMI_ADMIN_KEY", "").strip()
    provided = (
        request.headers.get("X-Admin-Key", "")
        or request.query_params.get("admin_key", "")
    ).strip()
    # When no secret is configured, only allow self-service downgrade to free
    # (so the box still works in dev without granting paid tiers for free).
    if not admin_key:
        raise HTTPException(
            status_code=503,
            detail="Tier management is not configured (set SKEMI_ADMIN_KEY).",
        )
    if provided != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    tier = (payload.tier or "").strip().lower()
    if not _ent.valid_tier(tier):
        raise HTTPException(status_code=400, detail=f"Unknown tier: {tier}")

    account = (payload.account_id or "").strip() or _resolve_account_id(request)
    _ent.set_tier(account, tier, source=payload.source or "admin")
    return {"success": True, "account": _ent.normalize_account(account), "tier": tier}


class UserSettingPayload(BaseModel):
    key: str
    value: Any


@app.post("/api/user/settings")
async def save_user_settings(request: Request, payload: UserSettingPayload):
    user_id = _get_storage_account_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_at REAL NOT NULL,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        INSERT INTO user_settings (user_id, key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    """, (
        user_id,
        payload.key,
        json.dumps(payload.value),
        time.time()
    ))
    conn.commit()
    conn.close()

    return {"success": True}


class UserDataPostPayload(BaseModel):
    namespace: str
    key: str
    value: Any





@app.post("/api/user/data")
async def post_user_data(request: Request, payload: UserDataPostPayload):
    user_id = _get_storage_account_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    _init_user_data_table()
    conn = sqlite3.connect(AUTH_DB_PATH)
    stored_value = payload.value if isinstance(payload.value, str) else json.dumps(payload.value, ensure_ascii=False)
    try:
        conn.execute(
            """
            INSERT INTO user_data (user_id, namespace, key, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, namespace, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (user_id, payload.namespace, payload.key, stored_value, time.time())
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    conn.close()
    return {"success": True}


@app.delete("/api/user/data")
async def delete_user_data(request: Request, namespace: str, key: str):
    user_id = _get_storage_account_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.execute(
        "DELETE FROM user_data WHERE user_id = ? AND namespace = ? AND key = ?",
        (user_id, namespace, key)
    )
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/user/settings")
async def get_user_settings(request: Request):
    user_id = _get_storage_account_id(request)
    if not user_id:
        return {"settings": {}}

    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT key, value FROM user_settings WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    conn.close()

    return {
        "settings": {
            row["key"]: json.loads(row["value"] or "null") for row in rows
        }
    }


# ─── Centered User Data API ───────────────────────────────────────────────────

class UserDataPayload(BaseModel):
    namespace: str
    key: str
    value: Any

class BulkItem(BaseModel):
    key: str
    value: Any

class UserDataBulkPayload(BaseModel):
    namespace: str
    items: List[BulkItem]

class UserDataDeletePayload(BaseModel):
    namespace: str
    key: str


@app.post("/api/user/data")
async def save_user_data(request: Request, payload: UserDataPayload):
    user_id = _get_storage_account_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(user_id, namespace, key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_data ON user_data(user_id, namespace)")
    
    conn.execute("""
        INSERT INTO user_data (user_id, namespace, key, value, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, namespace, key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    """, (
        user_id,
        payload.namespace,
        payload.key,
        json.dumps(payload.value),
        time.time()
    ))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/user/data")
async def api_get_user_data(namespace: str, request: Request):
    uid = _get_storage_account_id(request)
    if not uid:
        raise HTTPException(401, "Unauthorized")
    _init_user_data_table()
    with sqlite3.connect(AUTH_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT key, value FROM user_data WHERE user_id=? AND namespace=?",
            (uid, namespace)
        ).fetchall()
    return {"success": True,
            "data": [{"key": r[0], "value": r[1]} for r in rows]}


@app.post("/api/user/data/bulk")
async def save_user_data_bulk(request: Request, payload: UserDataBulkPayload):
    user_id = _get_storage_account_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(user_id, namespace, key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_data ON user_data(user_id, namespace)")
    
    now = time.time()
    for item in payload.items:
        conn.execute("""
            INSERT INTO user_data (user_id, namespace, key, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, namespace, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (
            user_id,
            payload.namespace,
            item.key,
            json.dumps(item.value),
            now
        ))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/user/data/bulk")
async def get_user_data_bulk(request: Request, namespace: str):
    return await api_get_user_data(namespace, request)


@app.post("/api/user/data/delete")
@app.delete("/api/user/data")
async def delete_user_data(request: Request, payload: UserDataDeletePayload):
    user_id = _get_storage_account_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(user_id, namespace, key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_data ON user_data(user_id, namespace)")
    
    conn.execute(
        "DELETE FROM user_data WHERE user_id = ? AND namespace = ? AND key = ?",
        (user_id, payload.namespace, payload.key)
    )
    conn.commit()
    conn.close()
    return {"success": True}


# ─── Prompt Agent API ───────────────────────────────────────────────────────────

class PhantomLockPayload(BaseModel):
    guid: str
    idd_rect: Optional[List[int]] = None


class PhantomWebRTCOfferPayload(BaseModel):
    sdp: str
    type: str = "offer"


def _phantom_core():
    import phantom_core
    return phantom_core


@app.get("/api/phantom/check-driver")
async def phantom_check_driver():
    """Return both states: `installed` (USBMMIDD adapter registered with Windows)
    and `monitor_active` / `found` (a usable IDD monitor is enumerable RIGHT NOW).

    After install we deliberately disable the virtual monitor (enableidd 0)
    so the user can't accidentally drag windows onto an invisible display, so
    `found` will be False while `installed` is True until the Phantom flow
    re-enables it. The frontend uses `installed` to gate the activation UI
    and `found` to gate the actual capture/stream.
    """
    core = _phantom_core()
    monitor = await asyncio.to_thread(core.find_idd_monitor)
    adapter = await asyncio.to_thread(core.find_idd_adapter)
    monitor_active = bool(monitor.get("found"))
    installed = bool(adapter.get("installed")) or monitor_active
    return {
        **monitor,
        "found": monitor_active,
        "installed": installed,
        "monitor_active": monitor_active,
        "adapter": adapter.get("adapter"),
    }


@app.post("/api/phantom/enable-monitor")
async def phantom_enable_monitor():
    """Turn the bundled USBMMIDD virtual monitor ON. Called right before
    locking the AI onto a desktop. Does not need UAC after the driver is
    installed."""
    return await asyncio.to_thread(_phantom_core().set_idd_monitor_enabled, True)


@app.post("/api/phantom/disable-monitor")
async def phantom_disable_monitor():
    """Turn the bundled USBMMIDD virtual monitor OFF. Called after install
    (so the user can't drag windows onto it) and when the Phantom session
    ends. The driver stays installed."""
    return await asyncio.to_thread(_phantom_core().set_idd_monitor_enabled, False)


def _phantom_driver_inf_candidates() -> List[str]:
    """Return possible INF paths for the bundled Phantom Display driver.

    Looks in:
      drivers/phantom-display/        (preferred — signed IDD release)
      drivers/Virtual-Display-Driver/ (itsmikethetech naming)
      drivers/IddSampleDriver/        (Microsoft sample)
      Skemi_Virtual_Display/usbmmidd_v2/  (bundled USB-MMIDD fallback)
    """
    root_dir = os.path.dirname(os.path.abspath(__file__))
    search_roots: List[str] = [
        os.path.join(root_dir, "drivers", "phantom-display"),
        os.path.join(root_dir, "drivers", "Virtual-Display-Driver"),
        os.path.join(root_dir, "drivers", "VirtualDisplayDriver"),
        os.path.join(root_dir, "drivers", "IddSampleDriver"),
        os.path.join(root_dir, "Skemi_Virtual_Display", "usbmmidd_v2"),
    ]
    candidates: List[str] = []
    for folder in search_roots:
        if not os.path.isdir(folder):
            continue
        try:
            for entry in os.listdir(folder):
                full = os.path.join(folder, entry)
                if entry.lower().endswith(".inf"):
                    candidates.append(full)
                elif os.path.isdir(full):
                    # one level deep (e.g. .../x64/foo.inf)
                    try:
                        for sub_entry in os.listdir(full):
                            if sub_entry.lower().endswith(".inf"):
                                candidates.append(os.path.join(full, sub_entry))
                    except Exception:
                        continue
        except Exception:
            continue
    return candidates


def _is_usbmmidd_inf(inf_path: str) -> bool:
    """USBMMIDD = Amyuni's signed virtual display driver (the bundled fallback)."""
    inf_dir = os.path.dirname(inf_path)
    inf_name = os.path.basename(inf_path).lower()
    has_installer = os.path.isfile(os.path.join(inf_dir, "deviceinstaller64.exe")) \
                 or os.path.isfile(os.path.join(inf_dir, "deviceinstaller.exe"))
    return inf_name in ("usbmmidd.inf",) and has_installer


def _write_usbmmidd_install_bat(inf_dir: str, log_path: str, enable_only: bool = False) -> str:
    """Generate a one-shot UAC-elevated BAT (ONE consent prompt).

    enable_only=False (fresh machine): `install usbmmidd.inf` then `enableidd 1`.
    enable_only=True  (already installed): ONLY `enableidd 1` — re-running install
      spawns duplicate virtual-monitor instances and causes repeated display
      flicker, so we never re-install.

    The monitor stays enabled; the user's cursor is kept out of it by a mouse
    boundary hook (install_mouse_boundary), not by disabling/parking it.
    """
    arch_64 = os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64").upper() in ("AMD64", "ARM64")
    installer_exe = "deviceinstaller64.exe" if arch_64 else "deviceinstaller.exe"
    bat_path = os.path.join(inf_dir, "skemi_install_idd.bat")
    # CRITICAL: only run `install usbmmidd.inf` on a FRESH machine. Running it again
    # when the driver is already present spawns ANOTHER virtual-monitor instance
    # (that's how DISPLAY7..10 accumulated) and each instance attaching causes a
    # display-reconfigure flicker. When already installed we ONLY enableidd 1.
    if enable_only:
        bat_body = (
            "@echo off\r\n"
            f'cd /d "{inf_dir}"\r\n'
            f'echo [%date% %time%] Skemi: re-activating existing virtual monitor > "{log_path}"\r\n'
            f'{installer_exe} enableidd 1 >> "{log_path}" 2>&1\r\n'
            "if errorlevel 1 (\r\n"
            f'  echo [FAIL] enableidd 1 returned errorlevel %errorlevel% >> "{log_path}"\r\n'
            "  exit /b 2\r\n"
            ")\r\n"
            f'echo [SUCCESS] virtual monitor re-activated >> "{log_path}"\r\n'
            "exit /b 0\r\n"
        )
    else:
        bat_body = (
            "@echo off\r\n"
            f'cd /d "{inf_dir}"\r\n'
            f'echo [%date% %time%] Skemi: installing USBMMIDD virtual display > "{log_path}"\r\n'
            f'{installer_exe} install usbmmidd.inf usbmmidd >> "{log_path}" 2>&1\r\n'
            "if errorlevel 1 (\r\n"
            f'  echo [FAIL] {installer_exe} install returned errorlevel %errorlevel% >> "{log_path}"\r\n'
            "  exit /b 1\r\n"
            ")\r\n"
            f'echo [OK] driver installed, activating virtual monitor... >> "{log_path}"\r\n'
            f'{installer_exe} enableidd 1 >> "{log_path}" 2>&1\r\n'
            "if errorlevel 1 (\r\n"
            f'  echo [FAIL] enableidd 1 returned errorlevel %errorlevel% >> "{log_path}"\r\n'
            "  exit /b 2\r\n"
            ")\r\n"
            f'echo [WAIT] letting Windows finish PnP registration... >> "{log_path}"\r\n'
            'timeout /t 3 /nobreak >NUL 2>&1\r\n'
            f'echo [SUCCESS] driver installed permanently, virtual monitor active >> "{log_path}"\r\n'
            "exit /b 0\r\n"
        )
    with open(bat_path, "w", encoding="ascii", newline="") as fh:
        fh.write(bat_body)
    return bat_path


def _phantom_install_driver_sync() -> Dict[str, Any]:
    """Install bundled IDD driver + activate 1 virtual monitor in one UAC click.

    For USBMMIDD (Amyuni — signed driver shipped with Skemi):
      ShellExecuteW(runas, skemi_install_idd.bat) → runs:
        1. deviceinstaller64.exe install usbmmidd.inf usbmmidd
        2. deviceinstaller64.exe enableidd 1
      A virtual monitor appears in Display Settings within ~5–10 seconds.

    For other IDD drivers (phantom-display / IddSampleDriver):
      ShellExecuteW(runas, pnputil.exe /add-driver <inf> /install)
    """
    if os.name != "nt":
        return {"success": False, "error": "Phantom driver install is only supported on Windows"}

    inf_candidates = _phantom_driver_inf_candidates()
    if not inf_candidates:
        return {
            "success": False,
            "error": "No INF file found. Please ensure Skemi_Virtual_Display/usbmmidd_v2/ is bundled.",
            "searched": [os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivers"),
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "Skemi_Virtual_Display")],
        }

    # Prefer pnputil-friendly drivers first (itsmikethetech VDD, IddSampleDriver) per
    # /goal spec — pnputil /add-driver /install on these auto-instantiates a monitor.
    # USBMMIDD is the offline fallback because it requires the extra deviceinstaller
    # step. Search order: drivers/phantom-display > drivers/Virtual-Display-Driver >
    # drivers/IddSampleDriver > Skemi_Virtual_Display/usbmmidd_v2 (last).
    non_usbmm = next((p for p in inf_candidates if not _is_usbmmidd_inf(p)), None)
    inf_path = non_usbmm if non_usbmm else inf_candidates[0]

    try:
        shell32 = ctypes.windll.shell32
        SW_SHOWNORMAL = 1

        if _is_usbmmidd_inf(inf_path):
            inf_dir = os.path.dirname(inf_path)
            log_path = os.path.join(inf_dir, "skemi_install_idd.log")
            # If the USBMMIDD adapter is ALREADY registered, do NOT re-install
            # (that spawns duplicate monitors + flicker) — only re-activate it.
            already = bool(_phantom_core().find_idd_adapter().get("installed"))
            bat_path = _write_usbmmidd_install_bat(inf_dir, log_path, enable_only=already)
            # ShellExecuteW runs the BAT elevated. UAC appears once; the BAT then
            # runs the deviceinstaller command(s) without further prompts.
            rc = shell32.ShellExecuteW(None, "runas", bat_path, None, inf_dir, SW_SHOWNORMAL)
            if int(rc) <= 32:
                err_code = ctypes.GetLastError()
                return {
                    "success": False,
                    "error": f"UAC declined or ShellExecuteW failed (rc={rc}, last_error={err_code}).",
                    "inf": inf_path,
                }
            return {
                "success": True,
                "inf": inf_path,
                "method": "deviceinstaller64.exe",
                "driver": "USBMMIDD v2 (Amyuni Technologies — signed virtual display driver)",
                "trust": "Catalog-signed (usbmmidd.cat). Used by commercial virtual-monitor products since 2009.",
                "bat": bat_path,
                "log": log_path,
                "message": "Đang cài driver, kích hoạt, rồi tự động ngắt kết nối an toàn. Khoảng 8-12 giây.",
            }

        # Generic IDD: pnputil only (some drivers auto-instantiate, some need extra step)
        rc = shell32.ShellExecuteW(
            None,
            "runas",
            "pnputil.exe",
            f'/add-driver "{inf_path}" /install',
            None,
            SW_SHOWNORMAL,
        )
        if int(rc) <= 32:
            err_code = ctypes.GetLastError()
            return {
                "success": False,
                "error": f"UAC declined or ShellExecuteW failed (rc={rc}, last_error={err_code}).",
                "inf": inf_path,
            }
        return {
            "success": True,
            "inf": inf_path,
            "method": "pnputil",
            "message": "Driver install launched. Polling for IDD monitor...",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "inf": inf_path}


@app.post("/api/phantom/install-driver")
async def phantom_install_driver():
    """
    Install the bundled IDD driver. Requires Windows + UAC elevation.
    After this returns success, the frontend should poll /api/phantom/check-driver
    until {found: true} or 30 seconds elapse.
    """
    return await asyncio.to_thread(_phantom_install_driver_sync)


def _phantom_guard_cursor_sync(enable: bool) -> Dict[str, Any]:
    """DISABLED. The old WH_MOUSE_LL boundary hook caused continuous system-wide
    mouse stutter: a Python low-level mouse hook must acquire the GIL on every
    mouse event, so when the server is busy (frame capture, LLM, JPEG encode)
    Windows stalls ALL mouse input waiting on the hook (up to LowLevelHooksTimeout
    = 300ms each). In the current design the AI's windows live on the INVISIBLE
    virtual monitor (off the physical layout), so the user can't accidentally drag
    onto it, and "Bring to view" recovers any window — the guard is unnecessary.
    We always tear down any existing hook and never install a new one."""
    with contextlib.suppress(Exception):
        _phantom_core().remove_mouse_boundary()
    return {"success": True, "guarding": False, "disabled": True}


@app.post("/api/phantom/guard-cursor")
async def phantom_guard_cursor():
    """Block the user's real cursor from entering the virtual-display rect so they
    can't accidentally drag windows onto it. AI's synthetic input still passes."""
    return await asyncio.to_thread(_phantom_guard_cursor_sync, True)


@app.post("/api/phantom/unguard-cursor")
async def phantom_unguard_cursor():
    """Remove the cursor guard (e.g. when leaving Phantom mode)."""
    return await asyncio.to_thread(_phantom_guard_cursor_sync, False)


@app.post("/api/phantom/normalize-monitor")
async def phantom_normalize_monitor():
    """Ensure the IDD virtual monitor is at a clean 1920×1080 so the streamed
    capture fills the viewport without black bars. Does NOT move/disable it."""
    return await asyncio.to_thread(_phantom_core().normalize_idd_resolution)


# ===========================================================================
# ISOLATED AI DESKTOPS (real Windows Desktop objects — true isolation)
# Each desktop = a separate CreateDesktop object. Apps launched here are invisible
# to the user's taskbar/Alt+Tab, the same app runs independently on multiple
# desktops, and the AI never touches the user's own apps. Capture = PrintWindow,
# input = background PostMessage (no cursor/focus steal). See skemi_iso_desktop.py.
# ===========================================================================
def _iso_mgr():
    import skemi_iso_desktop
    return skemi_iso_desktop.get_manager()


@app.post("/api/phantom/iso/create")
async def iso_create(payload: Dict[str, Any] = Body(default={})):
    label = str((payload or {}).get("label") or "")
    # Default to USER-DESKTOP mode: the app runs on the USER's own desktop, so its
    # icon shows in the taskbar ("thấy icon app đang chạy") and it can be brought up
    # normally — it's just launched MINIMISED/off-view so the window doesn't pop up at
    # first. A separate desktop (user_desktop=false) hides it from the taskbar entirely,
    # which the user does NOT want. Focus-steal + first-flash are handled by launching
    # SW_SHOWMINNOACTIVE + the focus-reassert guard.
    user_desktop = bool((payload or {}).get("user_desktop", True))
    return await asyncio.to_thread(_iso_mgr().create, label, user_desktop)


def _iso_ensure_display_sync() -> Dict[str, Any]:
    """Make sure ONE Amyuni virtual display is active to host the AI's app windows.

    The AI's native windows are placed on this virtual monitor so Windows renders
    them fully (modern Direct2D/WinUI content is NOT black like it is off-screen),
    while the user never sees them (no physical panel). The driver is already
    bundled+installed on Skemi machines, so this only needs `enableidd 1` — ONE
    UAC click, NO re-install (re-installing would spawn duplicate monitors)."""
    core = _phantom_core()
    info = core.find_idd_monitor()
    if info.get("found") and info.get("rect"):
        return {"success": True, "active": True, "rect": info.get("rect"),
                "message": "Màn hình ảo đã sẵn sàng."}
    # Not active yet → enable it (enable-only path when adapter already present).
    res = _phantom_install_driver_sync()
    return {"success": bool(res.get("success")), "active": False,
            "launched": res, "message": res.get("message")
            or "Đang bật màn hình ảo (1 lần UAC)…"}


@app.post("/api/phantom/iso/ensure-display")
async def iso_ensure_display():
    return await asyncio.to_thread(_iso_ensure_display_sync)


@app.post("/api/phantom/iso/bring-to-view")
async def iso_bring_to_view(payload: Dict[str, Any] = Body(default={})):
    # Fall back to the shared unified Live-Control desktop when the given id is
    # missing/unknown — a command sent via /api/local-computer/run runs on
    # `_UNIFIED_ISO` (different id than the frontend's isoDesktopId), so "Hiện cửa
    # sổ" must reach it too, else the user can't summon a unified-path app.
    mgr = _iso_mgr()
    d = mgr.get(str((payload or {}).get("id") or "")) or mgr.get(_UNIFIED_ISO.get("id") or "")
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    hwnd = int((payload or {}).get("hwnd", 0) or 0)
    return await asyncio.to_thread(d.bring_to_user, hwnd)


@app.get("/api/phantom/iso/list")
async def iso_list():
    return {"success": True, "desktops": await asyncio.to_thread(_iso_mgr().list)}


@app.post("/api/phantom/iso/open-app")
async def iso_open_app(payload: Dict[str, Any] = Body(default={})):
    desktop_id = str((payload or {}).get("id") or "")
    app = str((payload or {}).get("app") or "")
    args = str((payload or {}).get("args") or "")
    url = str((payload or {}).get("url") or "")
    d = _iso_mgr().get(desktop_id)
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    return await asyncio.to_thread(d.launch, app, args, url)


async def _iso_plan_with_llm(command: str) -> Dict[str, Any]:
    """Ask the configured ollama model to turn a natural command into an action
    plan for the isolated desktop. Returns {} on any failure (caller falls back to
    a heuristic), so the feature degrades gracefully when ollama isn't signed in."""
    import httpx
    model = os.getenv("SKEMI_MODEL_MAIN", "devstral-2:123b-cloud")
    sys_prompt = (
        "You convert a user's natural-language request into a JSON plan to run on an "
        "ISOLATED Windows desktop (the AI's own desktop). Output ONLY JSON:\n"
        '{"steps":[{"action":"open_app|open_url|type|key|wait","app":"<exe or name>",'
        '"url":"<full https url>","text":"<text>","key":"<enter|tab|...>","seconds":<n>}],'
        '"summary":"<short>"}\n'
        "Rules: to play music/video or open a website, use open_url with a full https URL "
        "(e.g. YouTube search: https://www.youtube.com/results?search_query=<query>). "
        "To open a desktop program use open_app with its name (notepad, calc, word...). "
        "Keep it minimal. No prose, JSON only."
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("http://localhost:11434/api/chat", json={
                "model": model, "stream": False,
                "messages": [{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": command}],
            })
            data = r.json()
            content = (((data or {}).get("message") or {}).get("content") or "")
            m = re.search(r"\{[\s\S]*\}", content)
            if not m:
                return {}
            plan = json.loads(m.group(0))
            return plan if isinstance(plan, dict) and plan.get("steps") else {}
    except Exception:
        return {}


def _iso_plan_heuristic(command: str) -> Dict[str, Any]:
    """Keyword-free-ish fallback: infer intent from a natural command without an LLM,
    so the isolated desktop still does the obvious things (open a site / play music /
    open an app / type) when ollama is unavailable."""
    from urllib.parse import quote_plus
    c = (command or "").strip()
    low = c.lower()
    # Music / video / YouTube → open a separate browser at a YouTube search.
    if any(k in low for k in ("youtube", "nhạc", "nhac", "music", "bài hát", "bai hat", "phát", "phat", "play", "video", "mv")):
        q = re.sub(r"\b(mở|mo|bật|bat|phát|phat|play|nghe|tìm|tim|trên|tren|youtube|giúp|giup|hãy|hay|nhạc|nhac|music|video|cho tôi|cho toi|đi|di)\b", " ", low)
        q = re.sub(r"\s+", " ", q).strip() or c
        return {"steps": [{"action": "open_url", "app": "chrome",
                           "url": f"https://www.youtube.com/results?search_query={quote_plus(q)}"}],
                "summary": f"Mở YouTube tìm: {q}"}
    # Generic website / search.
    if any(k in low for k in ("google", "tìm kiếm", "tim kiem", "search", "tra cứu", "website", "trang web", "mở web", "mo web")):
        q = re.sub(r"\b(mở|mo|tìm|tim|kiếm|kiem|search|google|trên|tren|web|website|giúp|giup|hãy|hay)\b", " ", low)
        q = re.sub(r"\s+", " ", q).strip() or c
        return {"steps": [{"action": "open_url", "app": "chrome",
                           "url": f"https://www.google.com/search?q={quote_plus(q)}"}],
                "summary": f"Tìm Google: {q}"}
    # Direct URL.
    if re.match(r"^https?://", low) or re.search(r"\b[\w.-]+\.(com|net|org|vn|io|dev)\b", low):
        url = c if low.startswith("http") else "https://" + re.search(r"[\w.-]+\.[a-z]{2,}\S*", low).group(0)
        return {"steps": [{"action": "open_url", "app": "chrome", "url": url}], "summary": f"Mở {url}"}
    # Type into the focused app.
    m = re.match(r"^(?:gõ|go|type|nhập|nhap|viết|viet)\s+([\s\S]+)$", c, re.IGNORECASE)
    if m:
        return {"steps": [{"action": "type", "text": m.group(1)}], "summary": "Gõ nội dung"}
    # Otherwise treat the (cleaned) command as an app to open.
    app = re.sub(r"^(?:mở|mo|bật|bat|chạy|chay|open|launch|run)\s+", "", c, flags=re.IGNORECASE).strip() or c
    return {"steps": [{"action": "open_app", "app": app}], "summary": f"Mở {app}"}


def _ollama_text_sync(prompt: str, timeout: int = 45, model: str = "") -> str:
    """Synchronous single-shot text completion via an ollama model. Defaults to the
    AGENTIC model (minimax-m2, a reasoning model) for the iso loop, but callers can
    pass a FAST model (e.g. gemini-3-flash-preview:cloud) for quick structured
    outputs like the research graph / lab synthesis, which otherwise time out on the
    slow reasoning model and fall back to an empty skeleton."""
    import urllib.request as _u, json as _j
    # Default the desktop AGENT to minimax-m2 — much FASTER per round than the 123B
    # devstral (the user's #1 complaint is speed). The improved prompt (compose,
    # anti-loop, finish-before-done, context) keeps it from looping. Override with
    # SKEMI_MODEL_AGENT=devstral-2:123b-cloud for max planning quality at lower speed.
    model = model or os.getenv("SKEMI_MODEL_AGENT", "minimax-m2:cloud")
    body = {"model": model, "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.1}}
    req = _u.Request("http://localhost:11434/api/chat",
                     data=_j.dumps(body).encode(),
                     headers={"Content-Type": "application/json"})
    with _u.urlopen(req, timeout=timeout) as r:
        data = _j.loads(r.read().decode())
    return (((data or {}).get("message") or {}).get("content") or "")


def _web_search_sync(query: str, n: int = 10) -> List[Dict[str, str]]:
    """Free web search via the ddgs library (no key, no subscription). Returns
    [{title, url, snippet}]. Used to GROUND the knowledge map in real, current web
    content when the (paid) cloud LLM is unavailable."""
    try:
        try:
            from ddgs import DDGS  # newer package name
        except Exception:
            from duckduckgo_search import DDGS  # legacy name
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    try:
        with DDGS() as d:
            for item in d.text(query, max_results=n):
                url = str(item.get("href") or item.get("url") or "").strip()
                if not url:
                    continue
                out.append({
                    "title": str(item.get("title") or url).strip()[:140],
                    "url": url,
                    "snippet": str(item.get("body") or item.get("snippet") or "").strip()[:400],
                })
    except Exception:
        pass
    return out


def _graph_from_search(topic: str, vi: bool) -> Optional[Dict[str, Any]]:
    """Build a knowledge graph grounded on real web results — every node carries a
    genuine snippet + source URL, so the map has actual information even with NO
    LLM. This is what makes deep-research work without a paid model."""
    results = _web_search_sync(topic, 10)
    if not results:
        return None
    import re as _re
    groups = ["core", "component", "application", "example", "core", "component", "application", "example", "core", "component"]
    nodes = [{"id": "n1", "label": topic[:42], "group": "root", "importance": 5,
              "detail": topic,
              "body": (f"Tổng hợp từ {len(results)} nguồn web về “{topic}”. Bấm từng node để đọc trích đoạn và mở nguồn gốc."
                       if vi else f"Synthesised from {len(results)} web sources on “{topic}”. Open each node to read the excerpt and source.")}]
    edges = []
    def _clean_label(title: str, url: str) -> str:
        t = (title or "").strip()
        # A title that is actually a URL or tracking redirect (empty/junk results give
        # "/clev?event=StartpageResultClick…") must NEVER become a node label.
        if (not t or _re.match(r"^https?://", t) or _re.match(r"^[/.]", t)
                or "StartpageResultClick" in t or _re.search(r"[?&](sc|event|utm_|payload|ref)=", t)):
            t = ""
        dom = _re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]
        if not t:
            # Fall back to a clean site name (e.g. "Bbc"), never the raw tracking URL.
            if dom and "?" not in dom and "." in dom:
                return dom.split(".")[0][:24].capitalize()
            return ""
        t = _re.sub(r"\s*[\\|]\s*\S.*$", "", t).strip()   # drop " \ Anthropic" / " | Site" tail
        return " ".join(t.split()[:6])[:46]
    idx = 0
    for r in results[:12]:
        label = _clean_label(r.get("title"), r.get("url"))
        if not label:
            continue                                  # skip pure tracking/redirect junk
        nid = f"s{idx}"; idx += 1
        dom = _re.sub(r"^https?://(www\.)?", "", r["url"]).split("/")[0][:40]
        _body = (r["snippet"] or r["title"] or "").strip() or (
            (f"Nguồn từ {dom} liên quan đến “{topic}”. Mở nguồn để đọc chi tiết."
             if vi else f"A source from {dom} relevant to “{topic}”. Open it to read more."))
        nodes.append({"id": nid, "label": label, "group": groups[(idx - 1) % len(groups)],
                      "importance": 3, "detail": dom,
                      "body": _body, "url": r["url"]})
        edges.append({"source": "n1", "target": nid, "relation": ("nguồn" if vi else "source")})
    # NO source→source cross-links — they made the wires "chằng chịt, chồng chéo".
    # A clean radial (root → sources) reads far clearer.
    if idx == 0:
        return None
    return {"overview": (f"Tổng hợp nhanh từ {len(results)} nguồn web cho “{topic}”."
                          if vi else f"Synthesised from {len(results)} web sources for “{topic}”."),
            "nodes": nodes, "edges": edges, "grounded": "web", "success": True, "topic": topic}


def _research_graph_sync(topic: str, language: str = "vi") -> Dict[str, Any]:
    """Turn a topic into a structured CONCEPT GRAPH for the deep-research view:
    roots, components and the relationships that link them. Powers the interactive
    knowledge map (and the Iron-Man gesture canvas) on the Search page."""
    import json as _j, re as _re
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "empty topic"}
    vi = str(language or "vi").startswith("vi")
    lang_name = "Vietnamese" if vi else "English"
    prompt = (
        f"You are a knowledge-graph engine. For the topic: \"{topic}\".\n"
        f"Return STRICT JSON (no markdown) describing a RICH, deep-research concept map.\n"
        f"All human-readable text MUST be in {lang_name}.\n"
        "Schema:\n"
        '{"overview":"2-3 sentence essence",'
        '"nodes":[{"id":"n1","label":"concept","group":"root|core|component|application|example|caution","importance":1..5,'
        '"detail":"1 short sentence why it matters","body":"2-3 informative sentences with concrete facts, numbers or a real example"}],'
        '"edges":[{"source":"n1","target":"n2","relation":"short verb phrase"}]}\n'
        "Rules: 13-16 nodes — focused, NOT crowded, so each is big & readable. Exactly ONE node group=\"root\" (the topic). "
        "Build TWO LEVELS of branches: 4-5 main \"core\" pillars off the root, and under EACH "
        "core pillar 1-2 deeper child nodes (component/application/example), plus 1 \"caution\" node. "
        "EVERY node — including leaves — MUST have a non-empty, genuinely informative `body` "
        "(2-3 sentences of real substance: a definition, key facts, a figure and a concrete example). Never leave body empty or generic. "
        "EDGES: a connected WEB, not a flat star. Wire root->core, core->its children, AND add "
        "several cross-links between related nodes in different branches (aim edges ~= 1.4 x nodes). "
        "Every non-root node connects via >=1 edge. Keep labels <= 4 words. "
        "Answer DIRECTLY with the JSON — do not over-think. Output ONLY the JSON object."
    )
    raw = ""
    # Default to minimax-m2:cloud — the user's subscription covers it (gemini-flash
    # does NOT). Set SKEMI_MODEL_GRAPH="web" to skip the LLM and use fast web search.
    _graph_model = os.getenv("SKEMI_MODEL_GRAPH", "minimax-m2:cloud")
    if _graph_model.lower() != "web":
        # minimax is a reasoning model → give it ample time for a FULL 16-20 node
        # graph. The old 75s cap fired before the rich graph finished (~80-110s),
        # silently dropping users to the flatter web-grounded map. 150s lets the
        # high-quality branched graph land; only a real error/offline falls back.
        # ONE fast retry if the FIRST call returns empty QUICKLY (a transient cloud
        # error, not a real timeout) — recovers the rich graph instead of dropping to
        # the sparse skeleton. We do NOT retry after a near-full-timeout (genuinely slow).
        for _attempt in (1, 2):
            _t0 = time.time()
            with contextlib.suppress(Exception):
                raw = _ollama_text_sync(prompt, timeout=150, model=_graph_model) or ""
            if raw.strip() or (time.time() - _t0) > 45:
                break  # got a result, or it was a real slow/timeout (don't double the wait)
    if not raw.strip():
        # No usable LLM → build the map straight from real web results (fast, free).
        grounded = _graph_from_search(topic, vi)
        if grounded:
            return grounded
    raw = _re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=_re.IGNORECASE)
    obj = None
    m = _re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            obj = _j.loads(m.group(0))
        except Exception:
            obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get("nodes"), list) or not obj["nodes"]:
        # LLM unavailable (e.g. paid cloud model not subscribed) → GROUND the map on
        # real, free web search so nodes carry actual info + sources.
        grounded = _graph_from_search(topic, vi)
        if grounded:
            return grounded
    if not isinstance(obj, dict) or not isinstance(obj.get("nodes"), list) or not obj["nodes"]:
        # Last-resort deterministic skeleton (web search also unavailable/offline).
        ov = (f"Chưa kết nối được bộ máy nghiên cứu sâu cho “{topic}”. Đây là bản đồ khung — bấm "
              "“Đào sâu node này” để Skemi nghiên cứu thêm khi mô hình sẵn sàng."
              if vi else
              f"Couldn't reach the deep-research engine for “{topic}”. This is a skeleton map — "
              "use “Drill node” to expand once the model is available.")
        obj = {
            "overview": ov,
            "nodes": [
                {"id": "n1", "label": topic[:40], "group": "root", "importance": 5,
                 "detail": topic,
                 "body": (f"Chủ đề bạn muốn nghiên cứu: “{topic}”. Bấm “Đào sâu node này” để mở rộng thành các khái niệm con."
                          if vi else f"Your topic: “{topic}”. Use Drill to expand into sub-concepts.")},
                {"id": "n2", "label": ("Khái niệm cốt lõi" if vi else "Core idea"),
                 "group": "core", "importance": 4,
                 "detail": ("Ý chính của chủ đề" if vi else "The central idea"),
                 "body": ("Những ý tưởng trung tâm tạo nên chủ đề. Đào sâu để Skemi liệt kê chi tiết." if vi else "The central ideas. Drill to detail them.")},
                {"id": "n3", "label": ("Ứng dụng" if vi else "Application"),
                 "group": "application", "importance": 3,
                 "detail": ("Cách dùng trong thực tế" if vi else "Real-world uses"),
                 "body": ("Chủ đề này được áp dụng ở đâu trong thực tế. Đào sâu để xem ví dụ cụ thể." if vi else "Where this applies in practice. Drill for examples.")},
                {"id": "n4", "label": ("Nguồn gốc" if vi else "Origins"),
                 "group": "component", "importance": 3,
                 "detail": ("Bối cảnh, lịch sử" if vi else "Background & history"),
                 "body": ("Nền tảng và lịch sử hình thành. Đào sâu để tìm hiểu thêm." if vi else "Background and history. Drill to learn more.")},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "relation": ("gồm" if vi else "includes")},
                {"source": "n1", "target": "n3", "relation": ("dùng cho" if vi else "used for")},
                {"source": "n1", "target": "n4", "relation": ("bắt nguồn" if vi else "rooted in")},
                {"source": "n4", "target": "n2", "relation": ("hình thành" if vi else "shapes")},
                {"source": "n2", "target": "n3", "relation": ("hỗ trợ" if vi else "enables")},
            ],
            "fallback": True,
        }
    # Normalise: GUARANTEE every node carries a non-empty, useful `body` (rich text)
    # for the node-world view — the user's rule "mọi node đều có thông tin". Prefer the
    # LLM body, fall back to the short detail, and as a last resort synthesise a line
    # from the label so a node is NEVER blank.
    try:
        for _n in obj.get("nodes", []):
            if not isinstance(_n, dict):
                continue
            _b = (str(_n.get("body") or "")).strip()
            if not _b:
                _b = (str(_n.get("detail") or "")).strip()
            if not _b:
                _lbl = str(_n.get("label") or topic)
                _b = (f"“{_lbl}” là một khía cạnh của “{topic}”. Bấm “Đào sâu node này” để Skemi nghiên cứu chi tiết hơn."
                      if vi else f"“{_lbl}” is an aspect of “{topic}”. Use “Drill” for Skemi to research it in depth.")
            _n["body"] = _b
    except Exception:
        pass
    obj["success"] = True
    obj["topic"] = topic
    return obj


@app.post("/api/research/graph")
async def research_graph(payload: Dict[str, Any] = Body(default={})):
    topic = str((payload or {}).get("topic") or (payload or {}).get("query") or "")
    language = str((payload or {}).get("language") or "vi")
    return await asyncio.to_thread(_research_graph_sync, topic, language)


def _research_synthesize_sync(a: str, b: str, topic: str = "", language: str = "vi") -> Dict[str, Any]:
    """LAB: combine two concepts the user wired together into a NEW idea — what
    their connection creates and whether it's feasible. Powers "nối lại → tạo ra
    cái gì" in the knowledge-map Lab mode."""
    import json as _j, re as _re
    a = (a or "").strip(); b = (b or "").strip()
    if not a or not b:
        return {"success": False, "error": "need two concepts"}
    vi = str(language or "vi").startswith("vi")
    lang_name = "Vietnamese" if vi else "English"
    prompt = (
        f"In the context of \"{topic or a}\", a researcher connects two concepts:\n"
        f"A = \"{a}\"\nB = \"{b}\"\n"
        f"Think like an innovation lab. Return STRICT JSON (no markdown), all text in {lang_name}:\n"
        '{"label":"<=5 word name of the new combined idea",'
        '"body":"2-3 sentences: what combining A and B creates, why it could work or not",'
        '"feasible":true|false,"score":0..100}\n'
        "Be concrete and creative but honest about feasibility. Output ONLY the JSON."
    )
    raw = ""
    _syn_model = os.getenv("SKEMI_MODEL_GRAPH", "minimax-m2:cloud")
    if _syn_model.lower() == "web":
        _syn_model = "minimax-m2:cloud"
    try:
        raw = _ollama_text_sync(prompt, timeout=60, model=_syn_model) or ""
    except Exception:
        raw = ""
    raw = _re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=_re.IGNORECASE)
    obj = None
    m = _re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            obj = _j.loads(m.group(0))
        except Exception:
            obj = None
    if not isinstance(obj, dict) or not obj.get("label"):
        obj = {
            "label": (f"{a} × {b}")[:40],
            "body": (f"Kết hợp “{a}” với “{b}” có thể mở ra hướng mới — cần kiểm chứng thêm dữ liệu để biết mức khả thi."
                     if vi else f"Combining “{a}” with “{b}” may open a new direction — needs more evidence to gauge feasibility."),
            "feasible": True, "score": 55, "fallback": True,
        }
    obj["success"] = True
    return obj


@app.post("/api/research/synthesize")
async def research_synthesize(payload: Dict[str, Any] = Body(default={})):
    a = str((payload or {}).get("a") or "")
    b = str((payload or {}).get("b") or "")
    topic = str((payload or {}).get("topic") or "")
    language = str((payload or {}).get("language") or "vi")
    return await asyncio.to_thread(_research_synthesize_sync, a, b, topic, language)


def _research_parts_sync(label: str, topic: str = "", language: str = "vi") -> Dict[str, Any]:
    """Describe an object/concept as a 3D SCHEMATIC of its main parts — an exploded
    engineering diagram the user can take apart, rotate and inspect. Powers the 3D
    Component Lab on a node ("mô hình 3D, tháo lắp từng phần tử, y chang bản thiết kế")."""
    import json as _j, re as _re
    label = (label or "").strip()
    if not label:
        return {"success": False, "error": "empty label"}
    vi = str(language or "vi").startswith("vi")
    lang_name = "Vietnamese" if vi else "English"
    prompt = (
        f"You are a 3D modeler. Build a RECOGNIZABLE low-poly model of \"{label}\""
        f"{(' (context: ' + topic + ')') if topic else ''} from primitive parts, arranged so the assembled "
        f"result ACTUALLY LOOKS LIKE the real object (correct silhouette & proportions — NOT random blocks). "
        f"Return STRICT JSON (no markdown), all text in {lang_name}:\n"
        '{"object":"<short name>","parts":[{"name":"<part name>","desc":"<1-2 sentences: function/role>",'
        '"shape":"box|cylinder|sphere|cone|torus","color":"<#hex>","size":[w,h,d],"pos":[x,y,z],"rot":[rx,ry,rz]}],'
        '"note":"<1 sentence how they assemble>"}\n'
        "Rules: 8-14 parts. Choose the RIGHT primitive for each part and ROTATE it (rot in DEGREES) so it sits "
        "correctly — e.g. wheels/tyres = torus or cylinder rotated [90,0,0]; a barrel/limb = cylinder rotated; "
        "a roof = box. Coordinates & sizes in roughly [-3..3], positioned and PROPORTIONED so the parts clearly "
        "form the object's real shape (a car looks like a car, a flower like a flower). Distinct, realistic colors. "
        "Be faithful to how the real object looks. Output ONLY the JSON object."
    )
    raw = ""
    _model = os.getenv("SKEMI_MODEL_GRAPH", "minimax-m2:cloud")
    if _model.lower() == "web":
        _model = "minimax-m2:cloud"
    with contextlib.suppress(Exception):
        # Generous timeout — the richer 8-14 part model takes longer; the old 60s cap
        # fell back to generic blocks ("chả ra hình gì") when the model ran long.
        raw = _ollama_text_sync(prompt, timeout=120, model=_model) or ""
    raw = _re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=_re.IGNORECASE)
    obj = None
    m = _re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            obj = _j.loads(m.group(0))
        except Exception:
            obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get("parts"), list) or not obj["parts"]:
        # Generic schematic fallback so the lab always renders something to take apart.
        pal = ["#60a5fa", "#a855f7", "#34d399", "#fbbf24", "#fb7185", "#22d3ee"]
        names_vi = ["Lớp vỏ ngoài", "Khung chính", "Bộ phận lõi", "Mô-đun chức năng", "Lớp nền", "Chi tiết phụ"]
        names_en = ["Outer shell", "Main frame", "Core unit", "Function module", "Base layer", "Accessory"]
        names = names_vi if vi else names_en
        parts = []
        for i in range(6):
            parts.append({
                "name": names[i], "shape": ["box", "cylinder", "box", "sphere", "box", "cone"][i],
                "color": pal[i], "size": [1.4, 0.6, 1.4] if i % 2 == 0 else [0.9, 0.9, 0.9],
                "pos": [0, 1.6 - i * 0.7, 0],
                "desc": (f"Thành phần “{names[i]}” của {label}. Bấm để xem chi tiết." if vi
                         else f"The “{names[i]}” component of {label}. Click for details."),
            })
        obj = {"object": label[:40], "parts": parts,
               "note": ("Mô hình khung — bấm Tháo rời để xem từng phần tử." if vi else "Schematic model — use Explode to inspect each part."),
               "fallback": True}
    obj["success"] = True
    obj["label"] = label
    return obj


@app.post("/api/research/parts")
async def research_parts(payload: Dict[str, Any] = Body(default={})):
    label = str((payload or {}).get("label") or (payload or {}).get("topic") or "")
    topic = str((payload or {}).get("topic") or "")
    language = str((payload or {}).get("language") or "vi")
    return await asyncio.to_thread(_research_parts_sync, label, topic, language)


def _research_visual_sync(topic: str, language: str = "vi") -> Dict[str, Any]:
    """ONE adaptive visual for the WHOLE topic. Flexible: a concrete physical object →
    a 3D model (parts); an abstract topic/process → a vivid INFOGRAPHIC (key figures +
    pillars + an insight). Helps the user see the topic at a glance and find ideas."""
    import json as _j, re as _re
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "empty topic"}
    vi = str(language or "vi").startswith("vi")
    lang_name = "Vietnamese" if vi else "English"
    prompt = (
        f"Decide how best to VISUALISE the whole topic \"{topic}\" at a glance, then return STRICT JSON "
        f"(no markdown), all text in {lang_name}.\n"
        "If the topic is a CONCRETE PHYSICAL OBJECT with parts (vehicle, machine, organism, device, building): "
        '{"kind":"3d","object":"<name>","parts":[{"name":"","desc":"","shape":"box|cylinder|sphere|cone|torus",'
        '"color":"#hex","size":[w,h,d],"pos":[x,y,z],"rot":[rx,ry,rz]}]}  (8-14 parts forming the real shape, rot in degrees).\n'
        "OTHERWISE (abstract idea, process, field, event): "
        '{"kind":"infographic","headline":"<1 punchy line capturing the topic>",'
        '"stats":[{"value":"<short number/figure>","label":"<what it is>"}],'
        '"pillars":[{"icon":"<1 emoji>","name":"<short>","desc":"<1 sentence>"}],'
        '"insight":"<1-2 sentences: the key takeaway or a path to a new solution>"}  (3-5 stats, 3-6 pillars).\n'
        "Pick exactly ONE kind. Be concrete and faithful to the real topic. Output ONLY the JSON object."
    )
    raw = ""
    _model = os.getenv("SKEMI_MODEL_GRAPH", "minimax-m2:cloud")
    if _model.lower() == "web":
        _model = "minimax-m2:cloud"
    with contextlib.suppress(Exception):
        raw = _ollama_text_sync(prompt, timeout=120, model=_model) or ""
    raw = _re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=_re.IGNORECASE)
    obj = None
    m = _re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            obj = _j.loads(m.group(0))
        except Exception:
            obj = None
    kind = str((obj or {}).get("kind") or "").lower()
    if isinstance(obj, dict) and kind == "3d" and isinstance(obj.get("parts"), list) and obj["parts"]:
        obj["success"] = True
        obj["kind"] = "3d"
        return obj
    if isinstance(obj, dict) and kind == "infographic" and (obj.get("pillars") or obj.get("stats")):
        obj["success"] = True
        obj["kind"] = "infographic"
        obj.setdefault("headline", topic)
        obj.setdefault("stats", [])
        obj.setdefault("pillars", [])
        obj.setdefault("insight", "")
        return obj
    # Fallback: a minimal infographic so something always renders.
    return {
        "success": True, "kind": "infographic", "headline": topic,
        "stats": [], "pillars": [], "fallback": True,
        "insight": ("Chưa dựng được hình ảnh trực quan chi tiết — thử lại để Skemi tổng hợp."
                    if vi else "Couldn't build a detailed visual — try again."),
    }


@app.post("/api/research/visual")
async def research_visual(payload: Dict[str, Any] = Body(default={})):
    topic = str((payload or {}).get("topic") or (payload or {}).get("label") or "")
    language = str((payload or {}).get("language") or "vi")
    return await asyncio.to_thread(_research_visual_sync, topic, language)


def _is_web_task(command: str, d) -> bool:
    """Route web tasks (or follow-ups once a browser is open) to the CDP web agent;
    native-app tasks go to the UIA agent."""
    low = (command or "").lower()
    # AUTOMATIC (no hardcoded list, consistent with the fast-path): if the command
    # names an app that is INSTALLED or already RUNNING on this machine → native.
    # This catches Claude desktop etc. that the web_kw list below would otherwise
    # wrongly send to the browser ("claude" is web-only ONLY when not installed).
    with contextlib.suppress(Exception):
        import skemi_iso_desktop as _iso
        _GEN = {"chat", "web", "mail", "game", "play", "video", "music", "file", "app",
                "apps", "search", "site", "online", "session", "model", "mode", "windows",
                "window", "desktop", "media", "store", "google", "chrome", "edge",
                "firefox", "browser", "tìm", "tim"}
        for t in dict.fromkeys(re.findall(r"[a-z][a-z0-9+#\.]{3,}", low)):
            if t in _GEN or re.search(rf"(?:về|about)\s+{re.escape(t)}", low):
                continue
            if d._find_running_window(t) or _iso._resolve_exe(t):
                return False
    # A clear desktop-app intent always wins (even mid web session).
    app_kw = ("notepad", "word", "excel", "powerpoint", "calc", "máy tính", "may tinh",
              "paint", "explorer", "file ", "thư mục", "thu muc", "vscode", "visual studio",
              "discord", "zalo", "steam", "settings", "cài đặt", "cai dat")
    if any(k in low for k in app_kw):
        return False
    web_kw = ("youtube", "google", "web", "website", "trang web", "url", "http", ".com",
              ".vn", "search", "tìm kiếm", "tim kiem", "nhạc", "nhac", "music", "video",
              "phát", "phat", "play", "facebook", "gmail", "tra cứu", "tra cuu", "browser",
              "chrome", "tải", "duyệt", "tìm ", "tim ",
              # web-only services with no desktop app installed → drive the website
              "claude", "chatgpt", "gemini", "copilot", "perplexity", "grok")
    if any(k in low for k in web_kw):
        return True
    # An explicit "OPEN <something>" that we could NOT resolve as an installed app
    # and that isn't a native builtin → per the user's rule ("không có thì dùng trình
    # duyệt"), open its website rather than fail trying to launch it natively.
    if re.search(r"\b(mở|mo|bật|bat|chạy|chay|vào|vao|open|launch|run|goto|go to)\b", low):
        return True
    # Follow-up with no clear app intent while a browser session is open → web.
    return getattr(d, "web", None) is not None


def _route_surface_sync(command: str, d) -> str:
    """Decide WEB (browser) vs APP (native) for a command — no per-app keyword list.
    The user's rule: if the named app is INSTALLED on the machine → run it natively
    (launched hidden the first time); if NOT installed → open its web version in the
    browser. Plus CONTINUITY: a follow-up that names nothing new stays in whatever is
    already open. The target-app name is extracted by the LLM (generic), then checked
    against the real Start-Menu/registry resolver — so it's automatic, not hardcoded."""
    low = (command or "").lower()
    if re.search(r"https?://\S+", low):
        return "web"
    # 0a) EXPLICIT WEB intent → web surface, overriding app-continuity. A command
    #     that names a search engine or says "search the web / on google" clearly
    #     wants the browser, even if an app (Claude/Zalo…) is already open — without
    #     this, "tìm trên google" got hijacked into the open app by the continuity
    #     branch. (Browser names alone are handled in the skip-set below.)
    if re.search(r"\bgoogle\b|\bbing\b|search the web|trên (?:google|web|mạng|internet)|"
                 r"lên (?:google|mạng|web)|tra (?:google|cứu trên)|search (?:on|google)", low):
        return "web"
    # 0) FAST local match — no LLM round-trip (the LLM extraction alone took ~25-30s
    #    on the cloud model, the user's 'siêu lâu' complaint). If a word of the
    #    command directly names an app that is RUNNING or INSTALLED on this machine
    #    (live lists — fully generic, no per-app table), route native immediately.
    with contextlib.suppress(Exception):
        import skemi_iso_desktop as _iso
        _GENERIC = {"chat", "web", "mail", "game", "play", "video", "music", "file",
                    "app", "apps", "search", "site", "online", "wiki", "session",
                    "model", "mode", "windows", "window", "desktop", "media", "store",
                    "files", "folder", "page", "information",
                    # browsers / search engines name the WEB surface, not a native app
                    # to drive via UIA — e.g. "tìm trên google …" must stay web, not
                    # open Chrome.lnk and poke at it.
                    "google", "chrome", "edge", "firefox", "browser", "cốc", "coccoc",
                    "brave", "opera", "bing", "trình", "duyệt"}
        toks = [t for t in re.findall(r"[a-z][a-z0-9+#\.]{3,}", low) if t not in _GENERIC]
        for t in dict.fromkeys(toks[:12]):
            # 'tìm về claude', 'search about X' = a TOPIC, not the app to open.
            if re.search(rf"(?:về|about)\s+{re.escape(t)}", low):
                continue
            if d._find_running_window(t) or _iso._resolve_exe(t):
                return "app"
    web_open = getattr(d, "web", None) is not None
    apps = []
    with contextlib.suppress(Exception):
        for w in (d.list_windows() or [])[:6]:
            t = (w.get("title") or "").strip()
            if t:
                apps.append(t[:40])
    last = ""
    with contextlib.suppress(Exception):
        last = (getattr(d, "web_history", []) or [])[-1][:80]
    # 1) Ask the LLM ONE thing: which app/service does this OPEN/USE (canonical name),
    #    or 'none' for a generic web action / a follow-up on something already open.
    name = ""
    nprompt = (
        "A user gave a command for their computer. If it wants to OPEN or USE a specific "
        "named application or service, output ONLY its short canonical name (e.g. discord, "
        "spotify, word, excel, powerpoint, notepad, telegram, zalo, vscode, steam, photoshop, "
        "obs, claude, chatgpt, gemini, notion, figma, canva). If it's a generic web action "
        "(google/搜索/search, open some website, watch/play media, read info) OR a follow-up "
        "that continues something already open, output exactly: none.\n"
        f"Already open → browser:{'yes' if web_open else 'no'}, apps:{apps or 'none'}, last:{last or '-'}\n"
        f"Command: {command}\n"
        "App/service name (one word) or none:"
    )
    with contextlib.suppress(Exception):
        name = (_ollama_text_sync(nprompt, timeout=12, model="minimax-m2:cloud") or "").strip()
        name = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()[:30]
    if name and name != "none":
        # 2) Is it INSTALLED or already RUNNING on THIS machine? Resolver covers
        #    Start-Menu / registry / system-exe AND packaged/Store apps (Get-StartApps,
        #    e.g. Claude desktop). Running-check adopts an app the user already has open.
        #    Either → native; neither → its web version.
        exe = ""; running = 0
        with contextlib.suppress(Exception):
            import skemi_iso_desktop as _iso
            exe = _iso._resolve_exe(name) or ""
        with contextlib.suppress(Exception):
            running = d._find_running_window(name)
        return "app" if (exe or running) else "web"
    # 3) 'none' → generic / follow-up: stay where work already is.
    if web_open and not apps:
        return "web"
    if apps and not web_open:
        return "app"
    if not web_open and not apps:
        return "web" if _is_web_task(command, d) else "app"
    # Both open → let the LLM pick the surface that continues the current work.
    cur_url = ""
    if web_open:
        with contextlib.suppress(Exception):
            cur_url = (d.web._page.url or "")[:90]
    cprompt = (
        "Continue the user's work in the right place. Browser open at: "
        f"{cur_url or '(none)'}; desktop apps open: {', '.join(apps) or 'none'}; "
        f"last: {last or '-'}. Command: {command}\n"
        "Reply ONE word: WEB (continue in the browser) or APP (continue in a desktop app)."
    )
    with contextlib.suppress(Exception):
        ans = (_ollama_text_sync(cprompt, timeout=12, model="minimax-m2:cloud") or "").strip().lower()
        if "web" in ans and "app" not in ans:
            return "web"
        if "app" in ans and "web" not in ans:
            return "app"
    return "web" if _is_web_task(command, d) else "app"


def _web_start_url(command: str) -> str:
    from urllib.parse import quote_plus
    c = (command or "").strip(); low = c.lower()
    m = re.search(r"https?://\S+", c)
    if m:
        return m.group(0)
    if "youtube" in low or any(k in low for k in ("nhạc", "nhac", "music", "video", "mv", "bài hát", "bai hat")):
        # Go to the YouTube HOMEPAGE and let the agent OPERATE the search box like a
        # human (type the query, Enter, click the first result) — instead of typing a
        # constructed results URL (which is the "nó cứ nhập link" complaint and left
        # junk like "và phonk" in the search bar).
        return "https://www.youtube.com/"
    # Named website with no desktop app → open the SITE directly (don't Google-search
    # it). The agent then acts on the real page. Covers the common ones.
    _SITES = {
        "facebook": "https://www.facebook.com/", "messenger": "https://www.messenger.com/",
        "gmail": "https://mail.google.com/", "youtube": "https://www.youtube.com/",
        "instagram": "https://www.instagram.com/", "twitter": "https://twitter.com/",
        " x ": "https://twitter.com/", "tiktok": "https://www.tiktok.com/",
        "reddit": "https://www.reddit.com/", "github": "https://github.com/",
        "chatgpt": "https://chatgpt.com/", "gemini": "https://gemini.google.com/",
        "claude": "https://claude.ai/", "copilot": "https://copilot.microsoft.com/",
        "perplexity": "https://www.perplexity.ai/", "grok": "https://grok.com/",
        "drive": "https://drive.google.com/", "maps": "https://maps.google.com/",
        "linkedin": "https://www.linkedin.com/", "twitch": "https://www.twitch.tv/",
        "netflix": "https://www.netflix.com/", "shopee": "https://shopee.vn/",
    }
    for kw, dest in _SITES.items():
        if kw.strip() in low:
            return dest
    # generic → google search of the cleaned command
    q = re.sub(r"\b(mở|mo|tìm|tim|kiếm|kiem|search|google|trên|tren|web|website|giúp|giup|hãy|hay|cho tôi|cho toi)\b", " ", low)
    q = re.sub(r"\s+", " ", q).strip() or c
    return f"https://www.google.com/search?q={quote_plus(q)}"


@app.post("/api/phantom/iso/agent")
async def iso_agent(payload: Dict[str, Any] = Body(default={})):
    """Full autonomous agent. Web tasks → CDP/Playwright (DOM control, like a human);
    native-app tasks → UIA tree + ghost input. Neither steals the user's mouse/focus."""
    d = _iso_mgr().get(str((payload or {}).get("id") or ""))
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    command = str((payload or {}).get("command") or "").strip()
    if not command:
        return {"success": False, "error": "empty_command"}
    # CONCURRENCY GUARD: the unified Live-Control desktop is SHARED across every
    # command. Two overlapping run_agent loops on the same windows (each on its own
    # to_thread → different COM thread) would fight over UIA/clicks. Atomically
    # reject a second command while one is still running, rather than interleaving.
    with d._lock:
        if getattr(d, "busy", False):
            return {"success": False, "busy": True,
                    "summary": "⏳ Đang xử lý lệnh trước — đợi xong rồi gửi lệnh tiếp."}
        d.busy = True
    try:
        surface = await asyncio.to_thread(_route_surface_sync, command, d)
        if surface == "web":
            # Continue in the SAME browser/tab if one is open (no navigation); only
            # build a start URL when opening the browser fresh for this command.
            start_url = "" if getattr(d, "web", None) is not None else _web_start_url(command)
            return await asyncio.to_thread(d.run_web, command, _ollama_text_sync, start_url)
        max_steps = int((payload or {}).get("max_steps", 12) or 12)
        # Un-park (re-show) any AI-launched window minimized between commands so the
        # agent can operate + capture it this round.
        with contextlib.suppress(Exception):
            await asyncio.to_thread(d._unpark_windows)
        res = await asyncio.to_thread(d.run_agent, command, _ollama_text_sync, max_steps)
        with contextlib.suppress(Exception):
            if not hasattr(d, "app_history"):
                d.app_history = []
            d.app_history.append(f"{command} → {str((res or {}).get('summary') or '')[:70]}")
            d.app_history = d.app_history[-8:]
        return res
    finally:
        d.busy = False
        # Between commands, park AI-launched windows minimized with an on-screen
        # restore rect → a raw taskbar-icon click summons them on-screen natively.
        with contextlib.suppress(Exception):
            await asyncio.to_thread(d._park_idle_windows)


_UNIFIED_ISO = {"id": ""}   # shared iso desktop for legacy Live-Control commands


async def iso_run_unified(command: str) -> Dict[str, Any]:
    """Run a desktop command on the ONE fixed agent (UIA + PostMessage ghost-input —
    never SendInput/SetCursorPos). The legacy /api/local-computer/run pipeline
    delegated here so Live Control, Phantom and Skemi Control all share the same
    engine: the old vision loop physically moved the user's mouse (jitter), stole
    focus and typed blind into the wrong window."""
    d = await unified_iso_desktop()
    if d is None:
        return {"success": False, "summary": "Không khởi tạo được môi trường AI."}
    return await iso_agent({"id": _UNIFIED_ISO["id"], "command": command})


async def unified_iso_desktop():
    """Get-or-create the shared iso desktop used by the legacy Live-Control paths
    (commands AND the mjpeg stream)."""
    mgr = _iso_mgr()
    d = mgr.get(_UNIFIED_ISO["id"]) if _UNIFIED_ISO["id"] else None
    if d is None:
        info = await asyncio.to_thread(mgr.create, "Live Control", True)  # user_desktop
        _UNIFIED_ISO["id"] = str((info or {}).get("id") or "")
        d = mgr.get(_UNIFIED_ISO["id"])
    return d


@app.post("/api/phantom/iso/stop")
async def iso_stop(payload: Dict[str, Any] = Body(default={})):
    """Stop button → abort the running agent loop ASAP (web or native).

    Cancels the desktop named by `id` AND the shared unified Live-Control desktop:
    commands sent via /api/local-computer/run run on `_UNIFIED_ISO` (a different id
    than the frontend's `isoDesktopId`), so a Stop must reach both — otherwise a
    unified-path command (a blocking /run) couldn't be interrupted. Idempotent and
    safe when an id is missing/duplicate."""
    mgr = _iso_mgr()
    cancelled = False
    seen = set()
    for did in (str((payload or {}).get("id") or ""), _UNIFIED_ISO.get("id") or ""):
        if not did or did in seen:
            continue
        seen.add(did)
        d = mgr.get(did)
        if d is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(d.cancel)
                cancelled = True
    return {"success": cancelled} if cancelled else {"success": False, "error": "desktop_not_found"}


@app.post("/api/phantom/iso/run")
async def iso_run(payload: Dict[str, Any] = Body(default={})):
    """Autonomous: turn ANY natural command into actions and run them on the
    isolated desktop. LLM-first (ollama), heuristic fallback — no fixed keywords."""
    d = _iso_mgr().get(str((payload or {}).get("id") or ""))
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    command = str((payload or {}).get("command") or "").strip()
    if not command:
        return {"success": False, "error": "empty_command"}
    plan = await _iso_plan_with_llm(command)
    used = "llm"
    if not plan or not plan.get("steps"):
        plan = _iso_plan_heuristic(command)
        used = "heuristic"
    results = []
    for step in (plan.get("steps") or [])[:8]:
        act = str(step.get("action") or "").lower()
        if act == "open_url":
            results.append(await asyncio.to_thread(d.launch, step.get("app") or "chrome", "", step.get("url") or ""))
        elif act == "open_app":
            results.append(await asyncio.to_thread(d.launch, step.get("app") or "", step.get("args") or "", ""))
        elif act == "type":
            results.append(await asyncio.to_thread(d.type_text, step.get("text") or "", 0))
        elif act == "key":
            results.append(await asyncio.to_thread(d.press_key, step.get("key") or "enter", 0))
        elif act == "wait":
            await asyncio.sleep(min(5.0, float(step.get("seconds") or 1)))
            results.append({"success": True, "waited": True})
    return {"success": True, "planner": used, "summary": plan.get("summary") or "",
            "steps": plan.get("steps"), "results": results}


def _placeholder_jpeg() -> bytes:
    """A tiny always-valid JPEG served when capture returns nothing, so /frame is
    NEVER a 503. The frontend only swaps its <img> on a SUCCESSFUL load, so a 503
    froze the last (stale) frame — the 'app đã tắt mà vẫn thấy cửa sổ' symptom.
    Cached after first build."""
    cached = getattr(_placeholder_jpeg, "_cache", None)
    if cached:
        return cached
    data = b""
    with contextlib.suppress(Exception):
        from PIL import Image as _I
        import io as _io
        im = _I.new("RGB", (640, 360), (16, 18, 30))
        b = _io.BytesIO(); im.save(b, format="JPEG", quality=60); data = b.getvalue()
    if not data:
        # Hardcoded 1x1 gray JPEG (last resort if PIL is unavailable).
        import base64 as _b64
        data = _b64.b64decode(
            "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////"
            "////////////////////////////////////////////////////wgALCAABAAEB"
            "AREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")
    _placeholder_jpeg._cache = data
    return data


@app.get("/api/phantom/iso/frame")
async def iso_frame(id: str):
    d = _iso_mgr().get(id)
    if not d:
        raise HTTPException(status_code=404, detail="desktop_not_found")
    jpeg = await asyncio.to_thread(d.capture_jpeg, 80)
    if not jpeg:
        # Serve a placeholder rather than 503 — a 503 freezes the frontend's last
        # frame (it only swaps the <img> on a successful load). Never freeze.
        jpeg = _placeholder_jpeg()
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/phantom/iso/windows")
async def iso_windows(id: str):
    d = _iso_mgr().get(id)
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    return {"success": True, "windows": await asyncio.to_thread(d.list_windows)}


@app.post("/api/phantom/iso/click")
async def iso_click(payload: Dict[str, Any] = Body(default={})):
    d = _iso_mgr().get(str((payload or {}).get("id") or ""))
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    x = float((payload or {}).get("x", 0.5))
    y = float((payload or {}).get("y", 0.5))
    hwnd = int((payload or {}).get("hwnd", 0) or 0)
    return await asyncio.to_thread(d.click, x, y, hwnd)


@app.post("/api/phantom/iso/type")
async def iso_type(payload: Dict[str, Any] = Body(default={})):
    d = _iso_mgr().get(str((payload or {}).get("id") or ""))
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    text = str((payload or {}).get("text") or "")
    hwnd = int((payload or {}).get("hwnd", 0) or 0)
    return await asyncio.to_thread(d.type_text, text, hwnd)


@app.post("/api/phantom/iso/key")
async def iso_key(payload: Dict[str, Any] = Body(default={})):
    d = _iso_mgr().get(str((payload or {}).get("id") or ""))
    if not d:
        return {"success": False, "error": "desktop_not_found"}
    key = str((payload or {}).get("key") or "enter")
    hwnd = int((payload or {}).get("hwnd", 0) or 0)
    return await asyncio.to_thread(d.press_key, key, hwnd)


@app.post("/api/phantom/iso/close")
async def iso_close(payload: Dict[str, Any] = Body(default={})):
    return await asyncio.to_thread(_iso_mgr().remove, str((payload or {}).get("id") or ""))


@app.get("/api/phantom/install-log")
async def phantom_install_log():
    """Return the contents of the most recent USBMMIDD install log, if any."""
    inf_candidates = _phantom_driver_inf_candidates()
    if not inf_candidates:
        return {"success": False, "error": "No INF found"}
    inf_path = next((p for p in inf_candidates if _is_usbmmidd_inf(p)), inf_candidates[0])
    log_path = os.path.join(os.path.dirname(inf_path), "skemi_install_idd.log")
    if not os.path.isfile(log_path):
        return {"success": True, "log": "", "exists": False}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        return {"success": True, "log": content, "exists": True, "path": log_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _phantom_remove_driver_sync() -> Dict[str, Any]:
    """Disable and remove the USBMMIDD virtual monitor (uninstall path)."""
    if os.name != "nt":
        return {"success": False, "error": "Only supported on Windows"}
    inf_candidates = _phantom_driver_inf_candidates()
    if not inf_candidates:
        return {"success": False, "error": "No driver folder found"}
    inf_path = next((p for p in inf_candidates if _is_usbmmidd_inf(p)), None)
    if not inf_path:
        return {"success": False, "error": "Remove is only supported for the bundled USBMMIDD driver"}
    inf_dir = os.path.dirname(inf_path)
    arch_64 = os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64").upper() in ("AMD64", "ARM64")
    installer_exe = "deviceinstaller64.exe" if arch_64 else "deviceinstaller.exe"
    log_path = os.path.join(inf_dir, "skemi_remove_idd.log")
    bat_path = os.path.join(inf_dir, "skemi_remove_idd.bat")
    # LOOP the stop/remove: `remove usbmmidd` clears ONE device node per call, but
    # repeated installs can leave MANY duplicate USBMMIDD adapter entries (seen: 16
    # on one machine) — a single remove leaves the rest, so the IDD keeps flapping
    # after a "clean" reinstall. Running remove ~24× clears every duplicate; extra
    # calls when none remain are harmless no-ops → a truly clean slate.
    bat_body = (
        "@echo off\r\n"
        f'cd /d "{inf_dir}"\r\n'
        f'echo [%date% %time%] Skemi: disabling + removing ALL virtual monitors > "{log_path}"\r\n'
        f'{installer_exe} enableidd 0 >> "{log_path}" 2>&1\r\n'
        f'for /L %%i in (1,1,24) do {installer_exe} stop usbmmidd >> "{log_path}" 2>&1\r\n'
        f'for /L %%i in (1,1,24) do {installer_exe} remove usbmmidd >> "{log_path}" 2>&1\r\n'
        f'echo [DONE — removed all duplicate USBMMIDD adapters] >> "{log_path}"\r\n'
        "exit /b 0\r\n"
    )
    with open(bat_path, "w", encoding="ascii", newline="") as fh:
        fh.write(bat_body)
    try:
        shell32 = ctypes.windll.shell32
        rc = shell32.ShellExecuteW(None, "runas", bat_path, None, inf_dir, 1)
        if int(rc) <= 32:
            return {"success": False, "error": f"UAC declined (rc={rc})"}
        return {"success": True, "log": log_path, "message": "Đang gỡ driver. Chờ 5 giây."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/api/phantom/remove-driver")
async def phantom_remove_driver():
    """Uninstall the bundled USBMMIDD virtual display driver."""
    return await asyncio.to_thread(_phantom_remove_driver_sync)


@app.get("/api/phantom/desktops")
async def phantom_desktops():
    desktops = await asyncio.to_thread(_phantom_core().list_desktops)
    return {"success": True, "desktops": desktops}


@app.post("/api/phantom/create-desktop")
async def phantom_create_desktop():
    return await asyncio.to_thread(_phantom_core().create_new_desktop)


@app.post("/api/phantom/lock")
async def phantom_lock(payload: PhantomLockPayload):
    return await asyncio.to_thread(
        _phantom_core().lock_ai_to_desktop,
        payload.guid,
        payload.idd_rect or [],
    )


@app.post("/api/phantom/stop")
async def phantom_stop():
    return await _phantom_core().stop_phantom()


class PhantomDebugOpenAppPayload(BaseModel):
    app: str
    idd_rect: Optional[List[int]] = None


@app.post("/api/phantom/debug/open-app")
async def phantom_debug_open_app(payload: PhantomDebugOpenAppPayload):
    """Test hook: launch app at IDD rect without going through the LLM loop.
    Used to live-verify open_app_on_desktop end-to-end."""
    core = _phantom_core()
    rect = payload.idd_rect or core.locked_idd_rect or []
    return await asyncio.to_thread(core.open_app_on_desktop, payload.app, rect)


class PhantomDebugTypePayload(BaseModel):
    hwnd: int
    text: str
    element_name: str = ""


@app.post("/api/phantom/debug/type")
async def phantom_debug_type(payload: PhantomDebugTypePayload):
    """Test hook: send text to a window via uiautomation."""
    core = _phantom_core()
    return await asyncio.to_thread(core.ai_type_text, payload.hwnd, payload.element_name, payload.text)


class PhantomDebugCaptureRectPayload(BaseModel):
    rect: List[int]


@app.post("/api/phantom/debug/capture-rect")
async def phantom_debug_capture_rect(payload: PhantomDebugCaptureRectPayload):
    """Capture ARBITRARY screen rect (not just IDD) — for test #4 we need to
    sample the user's main monitor rect too and prove notepad does NOT appear."""
    import io, base64
    core = _phantom_core()
    if len(payload.rect) != 4:
        raise HTTPException(status_code=400, detail="rect must be [left, top, right, bottom]")
    try:
        arr = await asyncio.to_thread(core._capture_idd_rgb, list(payload.rect))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Capture failed: {exc}")
    try:
        from PIL import Image  # type: ignore
        img = Image.fromarray(arr)
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"skemi_capture_{payload.rect[0]}_{payload.rect[1]}.png")
        img.save(out_path, "PNG")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"success": True, "rect": payload.rect, "width": int(arr.shape[1]), "height": int(arr.shape[0]), "path": out_path}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Encode failed: {exc}")


@app.get("/api/phantom/debug/state")
async def phantom_debug_state():
    """Expose phantom_core module state for live verification (test #6)."""
    core = _phantom_core()
    return {
        "locked_desktop_guid": core.locked_desktop_guid,
        "locked_idd_rect": list(core.locked_idd_rect) if core.locked_idd_rect else [],
        "ai_phantom_active": bool(core.ai_phantom_active),
        "ai_windows_count": len(core._ai_windows),
        "mouse_hook_alive": bool(core._mouse_hook_thread and core._mouse_hook_thread.is_alive()),
        "mouse_hook_handle": int(core._mouse_hook_handle or 0),
        "mouse_boundary_rect": list(core._mouse_boundary_rect),
    }


@app.get("/api/phantom/debug/capture")
async def phantom_debug_capture():
    """Capture one BitBlt frame of the locked IDD rect as base64 PNG so the
    user (or automated tests) can verify the WebRTC stream sees the AI's
    workspace. Saves to /tmp/skemi_phantom_capture.png for inspection."""
    import io, base64
    core = _phantom_core()
    rect = core.locked_idd_rect
    if not rect:
        # fall back to whatever monitor find_idd_monitor reports
        info = await asyncio.to_thread(core.find_idd_monitor)
        if not info.get("found"):
            raise HTTPException(status_code=400, detail="No IDD monitor and no lock — call /lock first")
        rect = info["rect"]
    try:
        arr = await asyncio.to_thread(core._capture_idd_rgb, list(rect))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Capture failed: {exc}")
    try:
        from PIL import Image  # type: ignore
        img = Image.fromarray(arr)
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skemi_phantom_capture.png")
        img.save(out_path, "PNG")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
            "success": True,
            "rect": list(rect),
            "width": int(arr.shape[1]),
            "height": int(arr.shape[0]),
            "path": out_path,
            "png_base64": b64,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Encode failed: {exc}")


@app.post("/api/phantom/webrtc/offer")
async def phantom_webrtc_offer(payload: PhantomWebRTCOfferPayload):
    try:
        return await _phantom_core().create_webrtc_answer(payload.sdp, payload.type)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.websocket("/ws/phantom")
async def phantom_socket(ws: WebSocket):
    await ws.accept()
    core = _phantom_core()
    agent_task = None
    try:
        await ws.send_json({"type": "ready"})
        while True:
            message = await ws.receive_json()
            msg_type = str(message.get("type") or "").lower()
            if msg_type in {"command", "start"}:
                command = str(message.get("command") or message.get("text") or "").strip()
                if not command:
                    await ws.send_json({"type": "error", "message": "command is required"})
                    continue
                if agent_task and not agent_task.done():
                    core.ai_phantom_active = False
                    agent_task.cancel()
                    with contextlib.suppress(Exception):
                        await agent_task
                desktop_guid = str(message.get("desktop_guid") or message.get("guid") or core.locked_desktop_guid or "")
                idd_rect = message.get("idd_rect") or core.locked_idd_rect or []
                agent_task = asyncio.create_task(core.run_phantom_agent(command, ws, desktop_guid, idd_rect))
            elif msg_type == "stop":
                core.ai_phantom_active = False
                if agent_task and not agent_task.done():
                    agent_task.cancel()
                await ws.send_json({"type": "stopped"})
    except WebSocketDisconnect:
        pass
    finally:
        core.ai_phantom_active = False
        if agent_task and not agent_task.done():
            agent_task.cancel()


# ─── Remote-control RELAY (TeamViewer-style) ─────────────────────────────────────
# A device registers by ID + password; a controller connects through this relay and
# the server forwards messages both ways (controller→device commands, device→controller
# screen frames + results). Works cross-machine when every party hits the same server
# (a deployed Skemi acts as the signaling relay); on one machine it's loopback-testable
# with two tabs. In-memory only (no persistence) — rooms vanish when the device leaves.
_remote_rooms: Dict[str, Dict[str, Any]] = {}


@app.websocket("/ws/remote")
async def remote_relay(ws: WebSocket):
    await ws.accept()
    role = ""
    room_id = ""
    try:
        hello = await ws.receive_json()
        role = str(hello.get("role") or "").lower()
        room_id = str(hello.get("id") or "").replace(" ", "").strip()
        password = str(hello.get("password") or "")
        if not room_id or role not in ("device", "controller"):
            await ws.send_json({"type": "error", "message": "bad hello"}); await ws.close(); return

        if role == "device":
            room = _remote_rooms.get(room_id) or {}
            controllers = room.get("controllers") or set()
            _remote_rooms[room_id] = {
                "password": password, "device": ws, "controllers": controllers,
                "name": str(hello.get("name") or ("Máy " + room_id)),
                "os": str(hello.get("os") or "unknown"),
            }
            await ws.send_json({"type": "registered", "id": room_id})
            for c in list(controllers):                       # tell waiting controllers it's back
                with contextlib.suppress(Exception):
                    await c.send_json({"type": "device_online"})
            while True:                                        # device → all its controllers
                msg = await ws.receive_json()
                room = _remote_rooms.get(room_id) or {}
                for c in list(room.get("controllers") or set()):
                    with contextlib.suppress(Exception):
                        await c.send_json(msg)

        else:  # controller
            room = _remote_rooms.get(room_id)
            if not room:
                await ws.send_json({"type": "error", "code": "offline", "message": "Thiết bị không trực tuyến hoặc chưa bật cho phép điều khiển."}); await ws.close(); return
            if room.get("password") and password != room.get("password"):
                await ws.send_json({"type": "error", "code": "auth", "message": "Sai mật khẩu thiết bị."}); await ws.close(); return
            room["controllers"].add(ws)
            await ws.send_json({"type": "connected", "device": {"name": room.get("name"), "os": room.get("os")}})
            with contextlib.suppress(Exception):
                await room["device"].send_json({"type": "controller_joined"})
            while True:                                        # controller → the device
                msg = await ws.receive_json()
                room = _remote_rooms.get(room_id)
                dev = room.get("device") if room else None
                if dev:
                    with contextlib.suppress(Exception):
                        await dev.send_json(msg)
                else:
                    await ws.send_json({"type": "device_offline"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "error", "message": str(exc)[:120]})
    finally:
        room = _remote_rooms.get(room_id) if room_id else None
        if room:
            if role == "device" and room.get("device") is ws:
                for c in list(room.get("controllers") or set()):
                    with contextlib.suppress(Exception):
                        await c.send_json({"type": "device_offline"})
                _remote_rooms.pop(room_id, None)
            elif role == "controller":
                with contextlib.suppress(Exception):
                    room.get("controllers", set()).discard(ws)


class PromptAgentRequest(BaseModel):
    idea: str
    mode: str = "research"

@app.post("/api/prompt-agent")
async def prompt_agent(payload: PromptAgentRequest):
    idea = str(payload.idea or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="idea is required")

    # Cap input at 80000 CHARACTERS — the character-equivalent of the ~20000-token
    # budget (≈4 chars/token), a clean round number. The UI shows a live char count.
    if len(idea) > 80000:
        raise HTTPException(status_code=413, detail="idea exceeds 80000 character limit")

    # UNIVERSAL optimizer — no manual mode/domain picker (the 4-mode selector was
    # needless friction). The model first INFERS the ideal expert role + domain from
    # the idea itself, then emits a structured, production-grade prompt.
    system_prompt = (
        "Bạn là Skemi Prompt Agent — chuyên gia tối ưu hoá prompt đẳng cấp thế giới. "
        "Nhiệm vụ: biến một ý tưởng sơ khai thành một prompt chặt chẽ, mạnh mẽ, để bất kỳ "
        "AI nào cũng hiểu và thực thi chính xác.\n\n"
        f"Ý tưởng gốc của người dùng:\n{idea}\n\n"
        "BƯỚC 1 — Tự xác định LĨNH VỰC và VAI TRÒ CHUYÊN GIA phù hợp nhất với ý tưởng này "
        "(nghiên cứu, chiến lược, lập trình, sáng tạo nội dung, phân tích dữ liệu, giáo dục, "
        "marketing, pháp lý, v.v.).\n"
        "BƯỚC 2 — Viết prompt tối ưu theo đúng format dưới đây, điền nội dung phù hợp với lĩnh vực đã chọn:\n\n"
        "# SYSTEM ROLE\n[Vai trò chuyên gia cụ thể, cấp cao, phù hợp nhất với ý tưởng]\n\n"
        "# CONTEXT\n[Diễn giải đầy đủ bối cảnh & ý định, nêu rõ giả định nếu có]\n\n"
        "# OBJECTIVE\n[Mục tiêu rõ ràng, đo lường được]\n\n"
        "# CONSTRAINTS\n[3-5 ràng buộc cụ thể, phù hợp lĩnh vực: chất lượng, nguồn dẫn, định dạng, phạm vi...]\n\n"
        "# REASONING PROCESS\n[Các bước lập luận: phân rã yêu cầu → lập kế hoạch → tự kiểm tra]\n\n"
        "# OUTPUT FORMAT\n[Mô tả định dạng đầu ra lý tưởng cho loại yêu cầu này]\n\n"
        "# QUALITY GATE\n- Không bịa đặt; không chắc thì nói rõ\n- Bám sát mục tiêu, không lan man\n- Trình bày có cấu trúc, dễ hành động\n\n"
        "Chỉ trả về prompt tối ưu hoàn chỉnh, KHÔNG giải thích thêm, KHÔNG bọc trong markdown."
    )

    try:
        result = await _generate_text(system_prompt, num_predict=1500)
        return {"prompt": result.strip(), "mode": "auto"}
    except Exception as exc:
        print(f"PROMPT AGENT ERROR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Computer Browser Agent API ─────────────────────────────────────────────────

class ComputerBrowserRequest(BaseModel):
    command: str

@app.post("/api/computer/browser")
async def computer_browser_agent(payload: ComputerBrowserRequest):
    command = str(payload.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    # Use AI to analyze what the user wants and simulate browser actions
    analysis_prompt = (
        "Bạn là Skemi Control — AI Agent vận hành trình duyệt. "
        "Người dùng ra lệnh bằng ngôn ngữ tự nhiên, bạn phân tích và mô tả "
        "các bước thao tác trình duyệt sẽ thực hiện.\n\n"
        f"Lệnh: {command}\n\n"
        "Trả lời JSON format:\n"
        '{\n'
        '  "url": "URL mà trình duyệt sẽ mở",\n'
        '  "steps": ["Bước 1: ...", "Bước 2: ..."],\n'
        '  "result": "Kết quả tóm tắt"\n'
        '}\n\n'
        "Chỉ trả về JSON, không giải thích thêm."
    )

    # If the command seems to be a search query, actually search for info
    search_keywords = ["tìm", "search", "tra cứu", "giá", "thông tin", "mới nhất", "latest", "find"]
    should_search = any(kw in command.lower() for kw in search_keywords)

    search_context = ""
    if should_search:
        try:
            search_result = await _smart_search(command, deep_research=False)
            if search_result:
                search_text = _search_result_to_text(search_result) if isinstance(search_result, dict) else str(search_result)
                search_context = search_text[:2000] if search_text else ""
        except Exception as e:
            print(f"COMPUTER BROWSER SEARCH ERROR: {e}")

    synthesis_prompt = (
        "Bạn là Skemi Control Browser Agent. "
        f"Người dùng ra lệnh: \"{command}\"\n\n"
    )
    if search_context:
        synthesis_prompt += f"Dữ liệu tìm được từ web:\n{search_context}\n\n"

    synthesis_prompt += (
        "Hãy tổng hợp thông tin và trả lời ngắn gọn, hữu ích. "
        "Nếu có số liệu cụ thể, ưu tiên đưa ra. "
        "Trả lời bằng tiếng Việt, không dùng markdown bold."
    )

    try:
        result = await _generate_text(synthesis_prompt, num_predict=600)
        # Try to extract URL from command
        import re as _re
        url_match = _re.search(r'(https?://\S+|[\w.-]+\.(?:com|org|net|io|vn|co)\S*)', command, _re.IGNORECASE)
        inferred_url = ""
        if url_match:
            raw_url = url_match.group(1)
            inferred_url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
        elif any(kw in command.lower() for kw in ["google", "tìm", "search"]):
            inferred_url = "https://www.google.com"

        return {
            "result": result.strip(),
            "url": inferred_url,
            "status": "completed",
        }
    except Exception as exc:
        print(f"COMPUTER BROWSER ERROR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Background Job Management for Computer & Desktop Agents ───────────────
import asyncio

class BackgroundAgentJob:
    def __init__(self, session_id, agent_type="computer", mode: str = "live"):
        self.session_id = session_id
        self.agent_type = str(agent_type or "computer").strip().lower() or "computer"
        self.mode = str(mode or "live").strip().lower() or "live"
        self.command = ""
        self.user_language = ""
        self.prompt_text = ""
        self.transport_preference = "auto"
        self.browser_shell = "virtual"
        self.runtime_agent_type = self.agent_type
        self.execution_surface = "visible_live" if self.mode == "live" else "app_hidden"
        self.sticky = True
        self.history = []
        self.done = False
        self.subscribers = []  # List of asyncio.Queue for multi-tab support
        self.surface_subscribers = []  # List of asyncio.Queue for live surface clients
        self.surface_video_frames = asyncio.Queue(maxsize=30)  # High-performance VideoFrame queue
        self.latest_image = ""
        self.latest_url = ""
        self.current_title = ""
        self.latest_surface_metrics = {}
        self.latest_targets = []
        self.latest_cursor = {}
        self.target_window_hwnd = 0
        self.target_window_title = ""
        self.target_window_class = ""
        self.frame_version = 0
        self.runner_task: Optional[asyncio.Task] = None
        self.stop_requested = False
        self.state = "running"
        self.message = ""
        self.last_result = ""
        self.final_result = ""
        self.status_text = ""
        self.task_state = "launching"
        self.stream_state = "connecting"
        self.surface_mode = self.mode
        self.automation_mode = "vision_fallback"
        self.stream_health = "booting"
        self.stall_reason = ""
        self.requires_consent = False
        self.consent_reason = ""
        self.session_memory: list[Dict[str, Any]] = []
        self.decision_cache_ref = ""
        self.pending_manual_takeover: Dict[str, Any] = {}
        self.pending_confirmation: Dict[str, Any] = {}
        self.created_at = time.time()
        self.last_active_at = self.created_at
        self.last_frame_at = 0.0
        self.last_action_at = self.created_at
        self.surface_history: list[Dict[str, Any]] = []
        self._last_history_capture_at = 0.0
        self._last_history_signature = ""
        self._history_horizon_seconds = 600.0
        self._history_max_frames = 360
        self._last_surface_signature = {"screenshot": "", "targets": "", "cursor": ""}
        self._surface_seq = 0
        self._state_seq = 0

    def apply_request_context(
        self,
        *,
        command: str = "",
        sticky: bool = True,
        transport_preference: str = "auto",
        browser_shell: str = "virtual",
        user_language: str = "",
        prompt_text: str = "",
    ) -> None:
        self.command = str(command or "").strip()
        self.sticky = bool(sticky)
        self.transport_preference = str(transport_preference or "auto").strip() or "auto"
        self.browser_shell = str(browser_shell or "virtual").strip() or "virtual"
        self.user_language = str(user_language or "").strip()
        self.prompt_text = str(prompt_text or "").strip()
        self.last_action_at = time.time()
        self._touch(state_changed=True)

    def _touch(self, *, state_changed: bool = False) -> None:
        self.last_active_at = time.time()
        if state_changed:
            self._state_seq += 1

    def _infer_execution_surface(self) -> str:
        runtime_agent = str(self.runtime_agent_type or self.agent_type or "computer").strip().lower()
        if runtime_agent == "computer":
            return "browser_hidden" if self.mode in {"background", "isolated", "phantom", "super"} else "visible_live"
        if self.mode in {"background", "isolated", "phantom", "super"}:
            return "app_hidden"
        return "visible_live"

    def _refresh_health(self) -> None:
        now = time.time()
        state = str(self.state or "").strip().lower() or "idle"
        self.execution_surface = str(self.execution_surface or self._infer_execution_surface()).strip().lower() or self._infer_execution_surface()
        self.requires_consent = bool(self.pending_confirmation)
        self.consent_reason = str(
            self.consent_reason
            or (self.pending_confirmation or {}).get("reason")
            or (self.pending_confirmation or {}).get("description")
            or ""
        ).strip()
        if state in {"pending_confirmation"} or self.requires_consent:
            self.stream_health = "degraded"
            self.stall_reason = self.consent_reason or "waiting_for_consent"
            return
        if state in {"stopped", "done", "error", "closed"} or self.done:
            frame_age = now - float(self.last_frame_at or 0.0) if self.last_frame_at else None
            if str(self.stream_state or "").strip().lower() in {"live", "frozen"} and frame_age is not None and frame_age <= 4.0:
                self.stream_health = "live"
            else:
                self.stream_health = "stopped"
            if state == "error" and not self.stall_reason:
                self.stall_reason = str(self.message or self.last_result or "runtime_error").strip()
            elif state != "error":
                self.stall_reason = ""
            return
        frame_age = now - float(self.last_frame_at or 0.0) if self.last_frame_at else None
        action_age = now - float(self.last_action_at or self.created_at or now)
        if frame_age is not None and frame_age <= 4.0:
            self.stream_health = "live"
            self.stall_reason = ""
            return
        if action_age <= 5.0 or state in {"idle", "starting", "booting"}:
            self.stream_health = "booting"
            self.stall_reason = ""
            return
        if state in {"running", "pending_manual_takeover"}:
            self.stream_health = "stalled"
            if not self.stall_reason:
                self.stall_reason = "no_recent_frame"
            return
        self.stream_health = "degraded"

    def state_snapshot(self) -> Dict[str, Any]:
        self._refresh_health()
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "runtime_agent_type": self.runtime_agent_type,
            "mode": self.mode,
            "state": self.state,
            "message": self.message,
            "status_text": self.status_text or self.message,
            "done": self.done,
            "sticky": self.sticky,
            "current_url": self.latest_url,
            "current_title": self.current_title,
            "transport_preference": self.transport_preference,
            "browser_shell": self.browser_shell,
            "session_memory": list(self.session_memory[-6:]),
            "decision_cache_ref": self.decision_cache_ref,
            "pending_manual_takeover": dict(self.pending_manual_takeover or {}),
            "pending_confirmation": dict(self.pending_confirmation or {}),
            "last_result": self.last_result,
            "final_result": self.final_result or self.last_result,
            "task_state": self.task_state,
            "stream_state": self.stream_state,
            "surface_mode": self.surface_mode or self.mode,
            "automation_mode": self.automation_mode,
            "last_active_at": self.last_active_at,
            "created_at": self.created_at,
            "execution_surface": self.execution_surface,
            "stream_health": self.stream_health,
            "last_frame_at": float(self.last_frame_at or 0.0),
            "last_action_at": float(self.last_action_at or 0.0),
            "stall_reason": self.stall_reason,
            "requires_consent": bool(self.requires_consent),
            "consent_reason": self.consent_reason,
            "state_seq": self._state_seq,
            "target_window_hwnd": int(self.target_window_hwnd or 0),
            "target_window_title": str(self.target_window_title or ""),
            "target_window_class": str(self.target_window_class or ""),
            "frame_version": int(self.frame_version or 0),
            "surface_metrics": dict(self.latest_surface_metrics or {}),
        }

    def session_state_packet(self) -> Dict[str, Any]:
        snapshot = self.state_snapshot()
        return {
            "type": "session_state",
            **snapshot,
            "pending_manual_takeover": dict(self.pending_manual_takeover or {}),
            "pending_confirmation": dict(self.pending_confirmation or {}),
        }

    def session_state_chunk(self) -> str:
        return (
            "event: session_state\n"
            f"data: {json.dumps(self.session_state_packet(), ensure_ascii=False)}\n\n"
        )

    def initial_surface_packets(self, stamp: bool = True) -> list[dict[str, Any]]:
        packets: list[dict[str, Any]] = []
        if self.latest_image:
            packet = {
                "type": "screenshot",
                "image": str(self.latest_image),
                "url": str(self.latest_url or ""),
                "title": str(self.current_title or ""),
                "surface_metrics": dict(self.latest_surface_metrics or {}),
            }
            packets.append(self._stamp_surface_packet(packet) if stamp else {**packet, "surface_seq": self._surface_seq})
        if self.latest_targets:
            packet = {
                "type": "targets",
                "items": list(self.latest_targets or []),
                "url": str(self.latest_url or ""),
                "title": str(self.current_title or ""),
                "surface_metrics": dict(self.latest_surface_metrics or {}),
            }
            packets.append(self._stamp_surface_packet(packet) if stamp else {**packet, "surface_seq": self._surface_seq})
        if self.latest_cursor:
            packet = {
                "type": "cursor",
                "x": self.latest_cursor.get("x"),
                "y": self.latest_cursor.get("y"),
                "url": str(self.latest_url or ""),
                "title": str(self.current_title or ""),
                "surface_metrics": dict(self.latest_surface_metrics or {}),
            }
            packets.append(self._stamp_surface_packet(packet) if stamp else {**packet, "surface_seq": self._surface_seq})
        return packets

    def surface_snapshot_packets(self) -> list[dict[str, Any]]:
        return self.initial_surface_packets(stamp=False)

    def history_manifest(self) -> Dict[str, Any]:
        frames = [
            {
                "index": index,
                "captured_at": float(item.get("captured_at") or 0.0),
                "url": str(item.get("url") or ""),
                "title": str(item.get("title") or ""),
                "surface_seq": int(item.get("surface_seq") or 0),
            }
            for index, item in enumerate(self.surface_history)
        ]
        return {
            "session_id": self.session_id,
            "frames": frames,
            "live_index": len(frames) - 1,
            "history_seconds": self._history_horizon_seconds,
            "browser_shell": self.browser_shell,
        }

    def history_frame(self, index: int) -> Optional[Dict[str, Any]]:
        if not self.surface_history:
            return None
        safe_index = max(0, min(len(self.surface_history) - 1, int(index)))
        frame = dict(self.surface_history[safe_index])
        frame["index"] = safe_index
        return frame

    def _parse_surface_updates(self, chunk: str) -> tuple[list[dict[str, Any]], bool]:
        packets: list[dict[str, Any]] = []
        state_changed = False
        try:
            event_name = ""
            for line in str(chunk or "").splitlines():
                if line.startswith("event: "):
                    event_name = line[7:].strip()
                    continue
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                payload_type = str(payload.get("type") or event_name or "").strip().lower()
                state_changed = self._update_state_from_payload(payload_type, payload) or state_changed
                image = payload.get("image") or payload.get("screenshot") or ""
                if image:
                    self.latest_image = str(image)
                    packets.append({
                        "type": payload.get("type") or event_name or "screenshot",
                        "image": str(image),
                        "url": str(payload.get("url") or self.latest_url or ""),
                        "title": str(payload.get("title") or self.current_title or ""),
                        "surface_metrics": dict(payload.get("surface_metrics") or self.latest_surface_metrics or {}),
                    })
                if payload.get("url"):
                    self.latest_url = str(payload.get("url") or "")
                if payload.get("title"):
                    self.current_title = str(payload.get("title") or "")
                if payload.get("surface_metrics"):
                    self.latest_surface_metrics = dict(payload.get("surface_metrics") or {})
                if payload.get("type") == "targets" and isinstance(payload.get("items"), list):
                    self.latest_targets = list(payload.get("items") or [])
                    packets.append({
                        "type": "targets",
                        "items": self.latest_targets,
                        "url": str(payload.get("url") or self.latest_url or ""),
                        "title": str(payload.get("title") or self.current_title or ""),
                        "surface_metrics": dict(payload.get("surface_metrics") or self.latest_surface_metrics or {}),
                    })
                if payload.get("x") is not None and payload.get("y") is not None:
                    self.latest_cursor = {
                        "x": payload.get("x"),
                        "y": payload.get("y"),
                    }
                    packets.append({
                        "type": payload.get("type") or event_name or "cursor",
                        "x": payload.get("x"),
                        "y": payload.get("y"),
                        "url": str(payload.get("url") or self.latest_url or ""),
                        "title": str(payload.get("title") or self.current_title or ""),
                        "surface_metrics": dict(payload.get("surface_metrics") or self.latest_surface_metrics or {}),
                    })
        except Exception:
            return [], state_changed
        return packets, state_changed

    def _update_state_from_payload(self, payload_type: str, payload: Dict[str, Any]) -> bool:
        changed = False
        state_type = str(payload_type or "").strip().lower()
        description = str(payload.get("description") or payload.get("message") or "").strip()
        result_text = str(payload.get("result") or "").strip()
        if payload.get("url"):
            url = str(payload.get("url") or "").strip()
            if url != self.latest_url:
                self.latest_url = url
                changed = True
        if payload.get("title"):
            title = str(payload.get("title") or "").strip()
            if title != self.current_title:
                self.current_title = title
                changed = True
        if payload.get("execution_surface"):
            execution_surface = str(payload.get("execution_surface") or "").strip().lower()
            if execution_surface and execution_surface != self.execution_surface:
                self.execution_surface = execution_surface
                changed = True
        if payload.get("runtime_agent_type"):
            runtime_agent_type = str(payload.get("runtime_agent_type") or "").strip().lower()
            if runtime_agent_type and runtime_agent_type != self.runtime_agent_type:
                self.runtime_agent_type = runtime_agent_type
                changed = True
        if payload.get("state"):
            explicit_state = str(payload.get("state") or "").strip().lower()
            if explicit_state and explicit_state != self.state:
                self.state = explicit_state
                changed = True
        if payload.get("task_state"):
            task_state = str(payload.get("task_state") or "").strip().lower()
            if task_state and task_state != self.task_state:
                self.task_state = task_state
                changed = True
        if payload.get("stream_state"):
            stream_state = str(payload.get("stream_state") or "").strip().lower()
            if stream_state and stream_state != self.stream_state:
                self.stream_state = stream_state
                changed = True
        if payload.get("automation_mode"):
            automation_mode = str(payload.get("automation_mode") or "").strip().lower()
            if automation_mode and automation_mode != self.automation_mode:
                self.automation_mode = automation_mode
                changed = True
        if payload.get("surface_mode"):
            surface_mode = str(payload.get("surface_mode") or "").strip().lower()
            if surface_mode and surface_mode != self.surface_mode:
                self.surface_mode = surface_mode
                changed = True
        if payload.get("status_text"):
            status_text = str(payload.get("status_text") or "").strip()
            if status_text and status_text != self.status_text:
                self.status_text = status_text
                changed = True
        if payload.get("message"):
            message_text = str(payload.get("message") or "").strip()
            if message_text and message_text != self.message:
                self.message = message_text
                changed = True
        if payload.get("final_result"):
            final_result = str(payload.get("final_result") or "").strip()
            if final_result and final_result != self.final_result:
                self.final_result = final_result
                changed = True

        if state_type == "session":
            self.state = "running"
            self.message = description or self.message
            self.status_text = description or self.status_text
            self.last_action_at = time.time()
            changed = True
        elif state_type == "confirm_required":
            self.state = "pending_confirmation"
            self.pending_confirmation = dict(payload or {})
            self.requires_consent = True
            self.consent_reason = str(payload.get("reason") or description or "").strip()
            self.last_action_at = time.time()
            changed = True
        elif state_type == "manual_takeover_required":
            self.state = "pending_manual_takeover"
            self.pending_manual_takeover = dict(payload or {})
            self.last_action_at = time.time()
            changed = True
        elif state_type == "manual_takeover_resumed":
            self.pending_manual_takeover = {}
            self.state = "running"
            self.message = description or self.message
            self.last_action_at = time.time()
            changed = True
        elif state_type == "done":
            self.state = "done"
            self.message = description or self.message
            self.last_result = result_text or description or self.last_result
            self.final_result = self.last_result
            self.status_text = description or self.status_text
            self.pending_manual_takeover = {}
            self.pending_confirmation = {}
            self.requires_consent = False
            self.consent_reason = ""
            self.last_action_at = time.time()
            changed = True
        elif state_type == "error":
            self.state = "error"
            self.message = description or self.message
            self.last_result = result_text or description or self.last_result
            self.final_result = self.last_result
            self.status_text = description or self.status_text
            self.pending_manual_takeover = {}
            self.pending_confirmation = {}
            self.requires_consent = False
            self.consent_reason = ""
            self.stall_reason = str(description or result_text or self.stall_reason or "runtime_error").strip()
            self.last_action_at = time.time()
            changed = True
        elif state_type == "stopped":
            self.state = "stopped"
            self.message = description or self.message
            self.last_result = result_text or description or self.last_result
            self.final_result = self.last_result
            self.status_text = description or self.status_text
            self.pending_manual_takeover = {}
            self.pending_confirmation = {}
            self.requires_consent = False
            self.consent_reason = ""
            self.last_action_at = time.time()
            changed = True
        elif state_type == "step" and description:
            self.state = "running"
            self.message = description
            self.last_action_at = time.time()
            changed = True
        elif state_type == "status":
            self.state = str(payload.get("state") or self.state or "running").strip().lower() or "running"
            if description:
                self.message = description
            self.last_action_at = time.time()
            changed = True

        if changed:
            self._touch(state_changed=True)
            if self.agent_type == "desktop":
                with contextlib.suppress(Exception):
                    import skemi_local_computer_backend
                    lc_state = skemi_local_computer_backend.local_computer_state
                    lc_state["status"] = self.state
                    lc_state["session_id"] = self.session_id
                    lc_state["pending_confirmation"] = dict(self.pending_confirmation or {})
                    lc_state["pending_manual_takeover"] = dict(self.pending_manual_takeover or {})
                    # Use description for notes if available
                    if description:
                        # Keep existing notes structure [mode_note1, mode_note2, dynamic_description]
                        existing_notes = lc_state.get("notes") or []
                        if len(existing_notes) >= 2:
                            lc_state["notes"] = existing_notes[:2] + [description]
                        else:
                            lc_state["notes"] = [description]
        else:
            self._touch(state_changed=False)
        return changed

    def _stamp_surface_packet(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        stamped = dict(packet or {})
        self._surface_seq += 1
        stamped["surface_seq"] = self._surface_seq
        return stamped

    def _surface_signature(self, packet: Dict[str, Any]) -> str:
        packet_type = str((packet or {}).get("type") or "").strip().lower()
        if packet_type == "targets":
            items = packet.get("items") or []
            return json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        if packet_type == "cursor":
            return f"{packet.get('x')}:{packet.get('y')}"
        if packet_type in {"screenshot", "step"}:
            return str(packet.get("image") or packet.get("screenshot") or "")
        return json.dumps(packet or {}, ensure_ascii=False, separators=(",", ":"))

    def _append_surface_history(self, packet: Dict[str, Any], *, stamped_packet: Optional[Dict[str, Any]] = None) -> None:
        packet_type = str((packet or {}).get("type") or "").strip().lower()
        image = str((packet or {}).get("image") or (packet or {}).get("screenshot") or "")
        if packet_type != "screenshot" or not image:
            return
        now = time.time()
        signature = self._surface_signature(packet)
        if signature == self._last_history_signature and (now - self._last_history_capture_at) < 2.0:
            return
        if self._last_history_capture_at and (now - self._last_history_capture_at) < 0.75:
            return
        source = stamped_packet or packet or {}
        self.surface_history.append({
            "captured_at": now,
            "image": image,
            "url": str(source.get("url") or self.latest_url or ""),
            "title": str(source.get("title") or self.current_title or ""),
            "surface_metrics": dict(source.get("surface_metrics") or self.latest_surface_metrics or {}),
            "surface_seq": int(source.get("surface_seq") or self._surface_seq or 0),
        })
        cutoff = now - self._history_horizon_seconds
        self.surface_history = [
            item for item in self.surface_history
            if float(item.get("captured_at") or 0.0) >= cutoff
        ][-self._history_max_frames:]
        self._last_history_capture_at = now
        self._last_history_signature = signature

    async def _publish_surface_packet(self, packet: Dict[str, Any]) -> None:
        packet_type = str((packet or {}).get("type") or "").strip().lower()
        if packet_type in {"screenshot", "targets", "cursor"}:
            signature = self._surface_signature(packet)
            if signature and self._last_surface_signature.get(packet_type) == signature:
                return
            self._last_surface_signature[packet_type] = signature
        stamped_packet = self._stamp_surface_packet(packet)
        self._append_surface_history(packet, stamped_packet=stamped_packet)
        if packet_type == "screenshot":
            self.last_frame_at = time.time()
            self.stream_health = "live"
            self.stall_reason = ""
        elif packet_type in {"cursor", "targets"}:
            self.last_action_at = time.time()
        for q in list(self.surface_subscribers):
            if packet_type == "screenshot":
                while q.qsize() >= 1:
                    with contextlib.suppress(asyncio.QueueEmpty):
                        q.get_nowait()
            elif packet_type in {"targets", "cursor"}:
                while q.qsize() >= 2:
                    with contextlib.suppress(asyncio.QueueEmpty):
                        q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(stamped_packet)
        
        # Synchronization for Desktop Agent (Local Computer)
        if self.agent_type == "desktop":
            if packet_type == "screenshot":
                with contextlib.suppress(Exception):
                    import skemi_local_computer_backend
                    import base64
                    image_data = str(stamped_packet.get("image") or "")
                    if image_data.startswith("data:"):
                        image_data = image_data.split(",", 1)[-1]
                    if image_data:
                        skemi_local_computer_backend._latest_frame = base64.b64decode(image_data)
                        skemi_local_computer_backend.local_computer_state["frame_version"] = int(skemi_local_computer_backend.local_computer_state.get("frame_version") or 0) + 1
            elif packet_type == "cursor":
                 with contextlib.suppress(Exception):
                    import skemi_local_computer_backend
                    skemi_local_computer_backend.local_computer_state["cursor_overlay"] = {
                        "visible": True,
                        "x": stamped_packet.get("x", 0),
                        "y": stamped_packet.get("y", 0),
                        "color": "#22d3ee"
                    }

    async def request_stop(self, description: str = "Đã dừng theo yêu cầu.", *, close_runtime: bool = False):
        if self.done:
            return
        self.stop_requested = True
        self.state = "stopped"
        self.message = str(description or "").strip()
        self.last_result = self.message or self.last_result or "Stopped."
        self.final_result = self.last_result
        self.status_text = self.message
        self.pending_manual_takeover = {}
        self.pending_confirmation = {}
        self._touch(state_changed=True)
        chunk = (
            "event: stopped\n"
            f"data: {json.dumps({'type': 'stopped', 'description': description}, ensure_ascii=False)}\n\n"
        )
        self.history.append(chunk)
        for q in list(self.subscribers):
            await q.put(chunk)
        stop_packet = {
            "type": "stopped",
            "description": description,
            "result": self.last_result,
            "image": str(self.latest_image or ""),
            "url": str(self.latest_url or ""),
            "title": str(self.current_title or ""),
            "surface_metrics": dict(self.latest_surface_metrics or {}),
            "frame_version": int(self.frame_version or 0),
            "target_window_hwnd": int(self.target_window_hwnd or 0),
            "target_window_title": str(self.target_window_title or ""),
            "target_window_class": str(self.target_window_class or ""),
        }
        await self._publish_surface_packet(stop_packet)
        if close_runtime and self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()

    async def run_loop(self, event_generator):
        keep_surface_open = False
        try:
            async for chunk in event_generator:
                self.history.append(chunk)
                surface_packets, state_changed = self._parse_surface_updates(chunk)
                if state_changed:
                    _persist_job_record(self)
                    state_chunk = self.session_state_chunk()
                    self.history.append(state_chunk)
                    for q in self.subscribers:
                        await q.put(state_chunk)
                for q in self.subscribers:
                    await q.put(chunk)
                for packet in surface_packets:
                    await self._publish_surface_packet(packet)
        except asyncio.CancelledError:
            if not self.stop_requested:
                err = (
                    "event: error\n"
                    f"data: {json.dumps({'message': 'Runner cancelled unexpectedly'}, ensure_ascii=False)}\n\n"
                )
                self.history.append(err)
                for q in list(self.subscribers):
                    await q.put(err)
                err_packet = {"type": "error", "message": "Runner cancelled unexpectedly"}
                await self._publish_surface_packet(err_packet)
        except Exception as e:
            err = f"event: error\ndata: {{\"message\": \"{type(e).__name__}: {str(e)}\"}}\n\n"
            self.history.append(err)
            for q in list(self.subscribers):
                await q.put(err)
            err_packet = {"type": "error", "message": f"{type(e).__name__}: {str(e)}"}
            await self._publish_surface_packet(err_packet)
        finally:
            self.runner_task = None
            runtime_idle = False
            if self.agent_type == "computer":
                with contextlib.suppress(Exception):
                    if browser_worker.browser_worker_host.has_session(self.session_id):
                        payload = await browser_worker.browser_worker_host.get_session_snapshot(self.session_id)
                        payload_state = str(payload.get("state") or "").strip().lower()
                        if payload_state == "idle":
                            runtime_idle = True
                            keep_surface_open = True
                            self.done = False
                            self.stop_requested = False
                            self.state = "idle"
                            self.message = str(payload.get("message") or "Virtual Browser đã sẵn sàng.")
                            self.latest_url = str(payload.get("current_url") or self.latest_url or "")
                            self.current_title = str(payload.get("current_title") or self.current_title or "")
                            self.last_result = str(payload.get("last_result") or self.last_result or "")
                            session_memory = list(payload.get("session_memory") or [])
                            self.session_memory = [entry for entry in session_memory if isinstance(entry, dict)][-6:]
                            self.decision_cache_ref = str(payload.get("decision_cache_ref") or self.decision_cache_ref or "")
                            self.pending_manual_takeover = dict(payload.get("pending_manual_takeover") or {})
                            self.pending_confirmation = dict(payload.get("pending_confirmation") or {})
            if not runtime_idle:
                self.done = True
                if self.state not in {"done", "stopped", "error"}:
                    self.state = "done"
            self._touch(state_changed=True)
            _persist_job_record(self)
            for q in list(self.subscribers):
                await q.put(None)
            if not keep_surface_open:
                for q in list(self.surface_subscribers):
                    await q.put(None)

global_agent_jobs: dict[str, BackgroundAgentJob] = {}


def _job_record_from_job(job: BackgroundAgentJob) -> session_store.AgentSessionRecord:
    existing = agent_session_store.get(job.session_id)
    created_at = float(getattr(existing, "created_at", job.created_at) or job.created_at)
    existing_session_memory = list(getattr(existing, "session_memory", []) or [])
    existing_session_memory = [entry for entry in existing_session_memory if isinstance(entry, dict)]
    job_session_memory = list(getattr(job, "session_memory", []) or [])
    job_session_memory = [entry for entry in job_session_memory if isinstance(entry, dict)]
    session_memory = (job_session_memory or existing_session_memory)[-6:]
    decision_cache_ref = str(getattr(job, "decision_cache_ref", "") or getattr(existing, "decision_cache_ref", "") or "")
    record = session_store.AgentSessionRecord(
        session_id=job.session_id,
        agent_type=job.agent_type,
        mode=job.mode,
        state=job.state,
        current_url=str(job.latest_url or ""),
        current_title=str(job.current_title or ""),
        sticky=bool(job.sticky),
        user_language=str(job.user_language or ""),
        prompt_text=str(job.prompt_text or job.command or ""),
        session_memory=session_memory,
        decision_cache_ref=decision_cache_ref,
        pending_manual_takeover=dict(job.pending_manual_takeover or {}),
        pending_confirmation=dict(job.pending_confirmation or {}),
        last_result=str(job.last_result or ""),
        transport_preference=str(job.transport_preference or "auto"),
        metadata={
            "message": str(job.message or ""),
            "history_count": len(job.history),
            "surface_seq": int(job._surface_seq),
            "state_seq": int(job._state_seq),
            "browser_shell": str(job.browser_shell or "virtual"),
            "runtime_agent_type": str(job.runtime_agent_type or job.agent_type or "computer"),
            "execution_surface": str(job.execution_surface or ""),
            "stream_health": str(job.stream_health or ""),
            "last_frame_at": float(job.last_frame_at or 0.0),
            "last_action_at": float(job.last_action_at or 0.0),
            "stall_reason": str(job.stall_reason or ""),
            "requires_consent": bool(job.requires_consent),
            "consent_reason": str(job.consent_reason or ""),
        },
        created_at=created_at,
        last_active_at=float(job.last_active_at or time.time()),
        expires_at=float(job.last_active_at or time.time()) + session_store.DEFAULT_IDLE_TTL,
    )
    return record


def _persist_job_record(job: BackgroundAgentJob) -> session_store.AgentSessionRecord:
    return agent_session_store.upsert(_job_record_from_job(job))


async def _sync_job_runtime_state(job: BackgroundAgentJob) -> Dict[str, Any]:
    if not job:
        return {}
    payload: Dict[str, Any] = {}
    runtime_agent_type = str(getattr(job, "runtime_agent_type", job.agent_type) or job.agent_type or "computer").strip().lower() or "computer"
    try:
        if runtime_agent_type == "computer" and browser_worker.browser_worker_host.has_session(job.session_id):
            payload = await browser_worker.browser_worker_host.get_session_snapshot(job.session_id)
        elif runtime_agent_type == "desktop":
            payload = await desktop_companion.desktop_companion_host.get_session_snapshot(job.session_id)
    except Exception:
        return {}
    if not payload:
        return {}
    job.mode = str(payload.get("mode") or job.mode or "live").strip().lower() or "live"
    job.state = str(payload.get("state") or job.state or "running").strip().lower() or "running"
    job.task_state = str(payload.get("task_state") or job.task_state or job.state or "working").strip().lower() or job.state or "working"
    job.stream_state = str(payload.get("stream_state") or job.stream_state or "connecting").strip().lower() or "connecting"
    job.latest_url = str(payload.get("current_url") or job.latest_url or "")
    job.current_title = str(payload.get("current_title") or job.current_title or "")
    job.last_result = str(payload.get("last_result") or job.last_result or "")
    job.final_result = str(payload.get("final_result") or job.final_result or job.last_result or "")
    job.status_text = str(payload.get("status_text") or payload.get("message") or job.status_text or "").strip()
    session_memory = list(payload.get("session_memory") or [])
    job.session_memory = [entry for entry in session_memory if isinstance(entry, dict)][-6:]
    job.decision_cache_ref = str(payload.get("decision_cache_ref") or job.decision_cache_ref or "")
    job.pending_manual_takeover = dict(payload.get("pending_manual_takeover") or {})
    job.pending_confirmation = dict(payload.get("pending_confirmation") or {})
    image = str(payload.get("image") or "").strip()
    if image:
        job.latest_image = image if image.startswith("data:") else f"data:image/jpeg;base64,{image}"
        job.last_frame_at = time.time()
    targets = payload.get("targets")
    if isinstance(targets, list):
        job.latest_targets = list(targets)
    surface_metrics = payload.get("surface_metrics")
    if isinstance(surface_metrics, dict) and surface_metrics:
        job.latest_surface_metrics = dict(surface_metrics)
    job.runtime_agent_type = str(payload.get("runtime_agent_type") or job.runtime_agent_type or runtime_agent_type or job.agent_type or "computer").strip().lower() or "computer"
    job.execution_surface = str(payload.get("execution_surface") or job.execution_surface or job._infer_execution_surface()).strip().lower() or job._infer_execution_surface()
    job.surface_mode = str(payload.get("surface_mode") or job.surface_mode or job.mode or "live").strip().lower() or job.mode or "live"
    job.automation_mode = str(payload.get("automation_mode") or job.automation_mode or "vision_fallback").strip().lower() or "vision_fallback"
    job.target_window_hwnd = int(payload.get("target_window_hwnd") or job.target_window_hwnd or 0)
    job.target_window_title = str(payload.get("target_window_title") or job.target_window_title or "")
    job.target_window_class = str(payload.get("target_window_class") or job.target_window_class or "")
    job.frame_version = int(payload.get("frame_version") or job.frame_version or 0)
    job.browser_shell = str(payload.get("browser_shell") or job.browser_shell or "virtual")
    with contextlib.suppress(Exception):
        job.last_active_at = float(payload.get("last_active_at") or job.last_active_at or time.time())
    metadata_message = str(payload.get("message") or "").strip()
    if metadata_message:
        job.message = metadata_message
    elif job.status_text:
        job.message = job.status_text
    job.requires_consent = bool(payload.get("requires_consent") or job.pending_confirmation)
    job.consent_reason = str(payload.get("consent_reason") or job.consent_reason or (job.pending_confirmation or {}).get("reason") or "").strip()
    if payload.get("last_action_at") is not None:
        with contextlib.suppress(Exception):
            job.last_action_at = float(payload.get("last_action_at") or job.last_action_at or time.time())
    elif job.pending_manual_takeover or job.pending_confirmation:
        job.last_action_at = time.time()
    job.stall_reason = str(payload.get("stall_reason") or job.stall_reason or "").strip()
    job.stream_health = str(payload.get("stream_health") or job.stream_health or "").strip().lower() or job.stream_health
    job._refresh_health()
    job._touch(state_changed=True)
    _persist_job_record(job)
    return payload


async def _refresh_live_surface(job: BackgroundAgentJob) -> Optional[Dict[str, Any]]:
    payload = await _sync_job_runtime_state(job)
    if not payload:
        return None
    packet = None
    if job.latest_image:
        packet = {
            "type": "screenshot",
            "image": str(job.latest_image),
            "url": str(job.latest_url or ""),
            "title": str(job.current_title or ""),
            "surface_metrics": dict(job.latest_surface_metrics or {}),
        }
        job._append_surface_history(packet)
    return packet


async def _mjpeg_stream(job: BackgroundAgentJob):
    last_sent = ""
    start_time = time.time()
    last_emit = start_time

    def _session_frame() -> str:
        try:
            runtime_agent_type = str(getattr(job, "runtime_agent_type", job.agent_type) or job.agent_type or "computer").strip().lower()
            if runtime_agent_type == "computer":
                session = computer_agent.active_sessions.get(job.session_id)
            elif runtime_agent_type == "desktop":
                session = desktop_agent.active_sessions.get(job.session_id)
            else:
                session = None
            live = str(getattr(session, "latest_live_b64", "") or "")
            if live:
                return live if live.startswith("data:") else f"data:image/jpeg;base64,{live}"
            # Fallback to local computer backend frame if desktop session matches
            if runtime_agent_type == "desktop":
                import skemi_local_computer_backend
                local_session = skemi_local_computer_backend.local_computer_state.get("session_id")
                if local_session and local_session == job.session_id:
                    frame = skemi_local_computer_backend._latest_frame
                    if frame:
                        return f"data:image/jpeg;base64,{base64.b64encode(frame).decode()}"
        except Exception:
            return ""
        return ""

    def _session_alive() -> bool:
        try:
            runtime_agent_type = str(getattr(job, "runtime_agent_type", job.agent_type) or job.agent_type or "computer").strip().lower()
            if runtime_agent_type == "computer":
                if browser_worker.browser_worker_host.has_session(job.session_id):
                    return True
                if job.runner_task is not None and not job.runner_task.done():
                    return True
                return job.session_id in computer_agent.active_sessions
            if runtime_agent_type == "desktop":
                if desktop_companion.desktop_companion_host.has_session(job.session_id):
                    return True
                if job.runner_task is not None and not job.runner_task.done():
                    return True
                if job.session_id in desktop_agent.active_sessions:
                    return True
                # Check local computer backend
                import skemi_local_computer_backend
                local_session = skemi_local_computer_backend.local_computer_state.get("session_id")
                return bool(local_session and local_session == job.session_id)
        except Exception:
            return False
        return False

    while True:
        frame = _session_frame() or str(job.latest_image or "")
        now = time.time()
        session_alive = _session_alive()
        post_done_window = float(getattr(desktop_agent, "DESKTOP_POST_DONE_LIVE_SECONDS", 3600.0) or 3600.0)
        state = str(getattr(job, "state", "") or "").strip().lower()
        allow_post_done_stream = bool(frame) and state in {"done", "stopped", "error", "blocked"} and (now - float(getattr(job, "last_active_at", start_time) or start_time)) <= post_done_window
        
        # DEAD SESSION CLEANUP: Release resource if session is clearly gone
        # GRACE PERIOD: Allow the desktop agent time to initialize or keep a post-done stream alive.
        if not session_alive and not allow_post_done_stream and (now - start_time) > 30.0:
            print(f"[MJPEG] Terminating stream for dead session/expired: {job.session_id}")
            break

        # FRAME THROTTLING & STABILITY
        # v54.7: Increase to 50 FPS for fluid video
        should_emit = bool(frame) and (frame != last_sent or (now - last_emit) >= 0.02)
        
        if should_emit:
            payload = frame.split(",", 1)[-1]
            try:
                jpeg_bytes = base64.b64decode(payload)
                if jpeg_bytes:
                    last_sent = frame
                    last_emit = now
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' + str(len(jpeg_bytes)).encode() + b'\r\n\r\n'
                           + jpeg_bytes + b'\r\n')
            except Exception:
                pass
        
        # Crucial wait to prevent CPU saturation while maintaining high responsiveness
        await asyncio.sleep(0.015) 

# ─── Computer Browser Agent: Real-time Background Stream ─────────────────────

import computer_agent

class ComputerStreamRequest(BaseModel):
    command: str
    mode: str = "live"
    reuse_session_id: str = ""
    sticky: bool = True
    reset_session: bool = False
    transport_preference: str = "auto"
    browser_shell: str = "virtual"
    desktop_index: int = -1
    lock_token: str = ""


class ComputerWebRTCOfferRequest(BaseModel):
    session_id: str
    sdp: str
    type: str = "offer"


class ComputerReadyRequest(BaseModel):
    reuse_session_id: str = ""
    sticky: bool = True
    browser_shell: str = "virtual"


def _build_ready_browser_job(session_id: str, payload: Dict[str, Any], *, sticky: bool = True, browser_shell: str = "virtual") -> BackgroundAgentJob:
    job = global_agent_jobs.get(session_id)
    if job is None:
        job = BackgroundAgentJob(session_id, "computer", "live")
        global_agent_jobs[session_id] = job
    job.done = False
    job.stop_requested = False
    job.runner_task = None
    job.state = "idle"
    job.message = "Virtual Browser đã sẵn sàng."
    job.last_result = ""
    job.runtime_agent_type = "computer"
    job.execution_surface = "browser_hidden"
    job.apply_request_context(
        command="",
        sticky=sticky,
        transport_preference="webrtc",
        browser_shell=browser_shell,
    )
    job.latest_url = str(payload.get("current_url") or job.latest_url or "")
    job.current_title = str(payload.get("current_title") or job.current_title or "")
    job.latest_image = str(payload.get("image") or job.latest_image or "")
    job.latest_targets = list(payload.get("targets") or [])
    job.latest_surface_metrics = dict(payload.get("surface_metrics") or job.latest_surface_metrics or {})
    if job.latest_image:
        job.last_frame_at = time.time()
        job._append_surface_history({
            "type": "screenshot",
            "image": str(job.latest_image or ""),
            "url": str(job.latest_url or ""),
            "title": str(job.current_title or ""),
            "surface_metrics": dict(job.latest_surface_metrics or {}),
        })
    job.history = [
        "event: session\n"
        f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'mode': job.mode, 'agent_type': job.agent_type, 'runtime_agent_type': job.runtime_agent_type, 'execution_surface': job.execution_surface, 'browser_shell': job.browser_shell}, ensure_ascii=False)}\n\n"
    ]
    job.history.append(job.session_state_chunk())
    _persist_job_record(job)
    return job


_BROWSER_TASK_PATTERN = re.compile(
    r"(https?://|www\.|youtube|youtu\.be|google|bing|gmail|facebook|chatgpt|chatgtp|gemini|chrome|browser|tab|website|web|url|link|search|tracuu|tra\s*cuu|t[iì]m\s+ki[eế]m|m[oở]\s+web|m[oở]\s+chrome|phat\s+video|ph[aá]t\s+video|play\s+video|xem\s+video|nghe\s+nh[aạ]c|music)",
    re.I,
)


def _normalize_local_mode(mode: str) -> str:
    value = str(mode or "live").strip().lower()
    if value in {"background", "phantom"} or value.startswith("phan") or value.startswith("back"):
        return "background"
    if value in {"isolated", "super"} or value.startswith("iso") or value.startswith("super"):
        return "isolated"
    return "live"


def _looks_like_browser_task(command: str) -> bool:
    text = str(command or "").strip()
    if not text:
        return False
    normalized = _normalize_text(text)
    if _BROWSER_TASK_PATTERN.search(text) or _BROWSER_TASK_PATTERN.search(normalized):
        return True
    return any(
        token in normalized
        for token in (
            "video",
            "youtube",
            "music",
            "nhac",
            "watch",
            "play",
            "google",
            "bing",
            "gmail",
            "facebook",
            "chatgpt",
            "gemini",
            "chrome",
            "browser",
            "search",
            "tim kiem",
            "tra cuu",
            "url",
            "link",
            "website",
            "web",
        )
    )


def _route_local_computer_command(command: str, mode: str) -> Dict[str, str]:
    normalized_mode = _normalize_local_mode(mode)
    # Local Computer must stay on the native desktop runtime even for browser/web tasks.
    # The desktop agent is responsible for launching and controlling the user's real apps.
    return {
        "runtime_agent_type": "desktop",
        "execution_surface": "app_hidden" if normalized_mode in {"background", "isolated"} else "visible_live",
        "browser_shell": "native",
    }


def _find_ready_browser_job(*, browser_shell: str = "virtual", preferred_session_id: str = "") -> Optional[BackgroundAgentJob]:
    desired_shell = str(browser_shell or "virtual").strip().lower() or "virtual"
    preferred = str(preferred_session_id or "").strip()
    candidates: list[tuple[float, BackgroundAgentJob]] = []
    for job in list(global_agent_jobs.values()):
        if job.agent_type != "computer":
            continue
        if str(getattr(job, "browser_shell", "virtual") or "virtual").strip().lower() != desired_shell:
            continue
        if str(getattr(job, "state", "") or "").strip().lower() != "idle":
            continue
        if not browser_worker.browser_worker_host.has_session(job.session_id):
            continue
        score = float(getattr(job, "last_active_at", 0.0) or 0.0)
        if preferred and job.session_id == preferred:
            score += 1_000_000_000
        candidates.append((score, job))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def _get_or_rehydrate_computer_job(session_id: str) -> Optional[BackgroundAgentJob]:
    sid = str(session_id or "").strip()
    if not sid:
        return None
    job = global_agent_jobs.get(sid)
    if job and job.agent_type == "computer":
        return job
    if not browser_worker.browser_worker_host.has_session(sid):
        return None
    payload = await browser_worker.browser_worker_host.get_session_snapshot(sid)
    record = agent_session_store.get(sid)
    browser_shell = str(
        payload.get("browser_shell")
        or getattr(record, "metadata", {}).get("browser_shell")
        or "virtual"
    )
    sticky = bool(getattr(record, "sticky", True))
    return _build_ready_browser_job(
        sid,
        payload,
        sticky=sticky,
        browser_shell=browser_shell,
    )

@app.api_route("/api/computer/stream", methods=["GET", "POST"])
async def computer_stream(request: Request, payload: ComputerStreamRequest = None):
    # Support polling connection for existing session via HTTP GET
    if request.method == "GET":
        session_id = request.query_params.get("session_id", "").strip()
        if not session_id or session_id not in global_agent_jobs:
            raise HTTPException(status_code=404, detail="Active job not found")
        job = global_agent_jobs[session_id]
        
    else:
        command = str(payload.command or "").strip()
        if not command:
            raise HTTPException(status_code=400, detail="command is required")

        reuse_session_id = str(getattr(payload, "reuse_session_id", "") or "").strip()
        sticky = bool(getattr(payload, "sticky", True))
        transport_preference = str(getattr(payload, "transport_preference", "auto") or "auto").strip() or "auto"
        browser_shell = str(getattr(payload, "browser_shell", "virtual") or "virtual").strip() or "virtual"
        if bool(getattr(payload, "reset_session", False)) and reuse_session_id:
            with contextlib.suppress(Exception):
                await browser_worker.browser_worker_host.stop_session(reuse_session_id)
            with contextlib.suppress(Exception):
                if reuse_session_id in global_agent_jobs:
                    await global_agent_jobs[reuse_session_id].request_stop("Da reset browser session.")
            with contextlib.suppress(Exception):
                agent_session_store.delete(reuse_session_id)
        session_id, event_generator = await browser_worker.browser_worker_host.start_session(
            command,
            reuse_session_id=reuse_session_id,
            sticky=sticky,
            browser_shell=browser_shell,
        )
        
        # Register background task
        browser_profile = {}
        with contextlib.suppress(Exception):
            browser_profile = computer_agent._build_browser_task_profile_v2(command)
        job = global_agent_jobs.get(session_id)
        if job is None:
            job = BackgroundAgentJob(session_id, "computer", "live")
            global_agent_jobs[session_id] = job
        else:
            job.done = False
            job.stop_requested = False
            job.runner_task = None
            job.state = "running"
            job.message = ""
            job.pending_manual_takeover = {}
            job.pending_confirmation = {}
            job.last_result = ""
            job.history = []
        job.apply_request_context(
            command=command,
            sticky=sticky,
            transport_preference=transport_preference,
            browser_shell=browser_shell,
            user_language=str(browser_profile.get("language") or ""),
            prompt_text=str(browser_profile.get("prompt_text") or ""),
        )
        job.history.append(
            "event: session\n"
            f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'mode': job.mode, 'agent_type': job.agent_type, 'browser_shell': job.browser_shell}, ensure_ascii=False)}\n\n"
        )
        _persist_job_record(job)
        job.runner_task = asyncio.create_task(job.run_loop(event_generator))

    async def sse_generator():
        # First push history down the pipe
        for chunk in job.history:
            yield chunk

        # Subscribe to new events
        q = asyncio.Queue()
        job.subscribers.append(q)
        try:
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if q in job.subscribers:
                job.subscribers.remove(q)

    from fastapi.responses import StreamingResponse as _SSEStreamingResponse
    return _SSEStreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/computer/ready")
async def computer_ready(payload: ComputerReadyRequest):
    reuse_session_id = str(getattr(payload, "reuse_session_id", "") or "").strip()
    sticky = bool(getattr(payload, "sticky", True))
    browser_shell = str(getattr(payload, "browser_shell", "virtual") or "virtual").strip() or "virtual"
    reusable_job = _find_ready_browser_job(browser_shell=browser_shell, preferred_session_id=reuse_session_id if sticky else "")
    if reusable_job is not None:
        ready_payload = {
            "session_id": reusable_job.session_id,
            "browser_shell": str(reusable_job.browser_shell or browser_shell or "virtual"),
            "current_url": str(reusable_job.latest_url or ""),
            "current_title": str(reusable_job.current_title or ""),
            "image": str(reusable_job.latest_image or ""),
            "targets": list(reusable_job.latest_targets or []),
            "surface_metrics": dict(reusable_job.latest_surface_metrics or {}),
        }
        _build_ready_browser_job(
            reusable_job.session_id,
            ready_payload,
            sticky=sticky,
            browser_shell=str(ready_payload.get("browser_shell") or browser_shell or "virtual"),
        )
        return {"success": True, "session_id": reusable_job.session_id, **ready_payload}
    response = await browser_worker.browser_worker_host.ensure_idle_session(
        reuse_session_id=reuse_session_id,
        sticky=sticky,
        browser_shell=browser_shell,
    )
    ready_payload = dict(response.get("payload") or {})
    session_id = str(response.get("session_id") or ready_payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=503, detail="Virtual Browser did not return a ready session")
    _build_ready_browser_job(
        session_id,
        ready_payload,
        sticky=sticky,
        browser_shell=str(ready_payload.get("browser_shell") or browser_shell or "virtual"),
    )
    return {"success": True, "session_id": session_id, **ready_payload}

class ComputerStopRequest(BaseModel):
    session_id: str


class ComputerConfirmRequest(BaseModel):
    session_id: str
    approved: bool = False


class ComputerManualActionRequest(BaseModel):
    session_id: str
    action: str
    x: Optional[float] = None
    y: Optional[float] = None
    text: Optional[str] = None
    key: Optional[str] = None
    direction: Optional[str] = None
    click_count: int = 1


class ComputerResumeRequest(BaseModel):
    session_id: str


class ComputerTabOpenRequest(BaseModel):
    session_id: str
    url: Optional[str] = None


class ComputerTabSwitchRequest(BaseModel):
    session_id: str
    tab_id: str

@app.post("/api/computer/stop")
async def computer_stop(payload: ComputerStopRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    if sid in global_agent_jobs:
        with contextlib.suppress(Exception):
            await _sync_job_runtime_state(global_agent_jobs[sid])
    try:
        stopped = await browser_worker.browser_worker_host.stop_session(sid)
    except browser_worker.BrowserWorkerSessionNotFound:
        stopped = computer_agent.stop_session(sid)
    except browser_worker.BrowserWorkerError:
        stopped = computer_agent.stop_session(sid)
    if sid in global_agent_jobs:
        await global_agent_jobs[sid].request_stop("Đã dừng Virtual Browser ngay lập tức.")
        _persist_job_record(global_agent_jobs[sid])
    else:
        with contextlib.suppress(Exception):
            agent_session_store.touch(sid, state="stopped")
    return {"stopped": stopped, "session_id": sid}


@app.post("/api/computer/confirm")
async def computer_confirm(payload: ComputerConfirmRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        resolved = await browser_worker.browser_worker_host.confirm_session(sid, bool(payload.approved))
    except browser_worker.BrowserWorkerSessionNotFound:
        session = computer_agent.active_sessions.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Active computer session not found")
        resolved = session.resolve_confirmation(bool(payload.approved))
    except browser_worker.BrowserWorkerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    job = global_agent_jobs.get(sid)
    if job:
        job.pending_confirmation = {}
        job.state = "running" if resolved and payload.approved else ("stopped" if resolved else job.state)
        job._touch(state_changed=True)
        with contextlib.suppress(Exception):
            await _sync_job_runtime_state(job)
        _persist_job_record(job)
    else:
        with contextlib.suppress(Exception):
            agent_session_store.touch(sid, pending_confirmation={}, state="running" if resolved and payload.approved else "stopped")
    return {"success": resolved, "session_id": sid, "approved": bool(payload.approved)}


@app.post("/api/computer/manual-action")
@app.post("/api/desktop/manual-action")
@app.post("/api/local-computer/manual-action")
async def computer_manual_action(payload: ComputerManualActionRequest, request: Request):
    if request.url.path.rstrip("/").endswith("/local-computer/manual-action"):
        return {
            "ok": False,
            "success": False,
            "reason": "local_computer_viewer_is_watch_only",
            "message": "Local Computer viewer is watch-only; AI control runs through the locked Phantom desktop.",
        }
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    action = str(payload.action or "").strip().lower()
    current_url = ""
    job = global_agent_jobs.get(sid)
    runtime_agent_type = _job_runtime_agent_type(job)
    if runtime_agent_type == "computer":
        try:
            result = await browser_worker.browser_worker_host.manual_action(
                sid,
                action,
                x=payload.x,
                y=payload.y,
                text=payload.text,
                key=payload.key,
                direction=payload.direction,
                click_count=payload.click_count,
            )
            current_url = str((result or {}).get("url") or "")
        except browser_worker.BrowserWorkerSessionNotFound:
            session = computer_agent.active_sessions.get(sid)
            if not session:
                raise HTTPException(status_code=404, detail="Active computer session not found")
            if action == "click":
                result = await session.manual_click(int(payload.x or 0), int(payload.y or 0), click_count=max(1, int(payload.click_count or 1)))
            elif action == "scroll":
                result = await session.manual_scroll(payload.direction or "down")
            elif action == "press":
                result = await session.manual_press(payload.key or "")
            elif action == "type":
                result = await session.manual_type(payload.text or "")
            else:
                raise HTTPException(status_code=400, detail="Unsupported manual action")
            current_url = getattr(session, "current_url", "")
        except browser_worker.BrowserWorkerError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    else:
        try:
            result = await desktop_companion.desktop_companion_host.manual_action(
                sid,
                action,
                x=payload.x,
                y=payload.y,
                text=payload.text,
                key=payload.key,
                direction=payload.direction,
                click_count=payload.click_count,
            )
        except desktop_companion.DesktopCompanionSessionNotFound:
            session = desktop_agent.active_sessions.get(sid)
            if not session:
                raise HTTPException(status_code=404, detail="Active desktop session not found")
            if action == "click":
                result = await session.manual_click(int(payload.x or 0), int(payload.y or 0), click_count=max(1, int(payload.click_count or 1)))
            elif action == "scroll":
                result = await session.manual_scroll(payload.direction or "down")
            elif action == "press":
                result = await session.manual_press(payload.key or "")
            elif action == "type":
                result = await session.manual_type(payload.text or "")
            else:
                raise HTTPException(status_code=400, detail="Unsupported manual action")
        except desktop_companion.DesktopCompanionError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        current_url = str((result or {}).get("url") or (job.latest_url if job else "") or "Local PC")

    if job:
        if current_url:
            job.latest_url = current_url
        job.last_action_at = time.time()
        job._touch(state_changed=False)
        with contextlib.suppress(Exception):
            await _sync_job_runtime_state(job)
        cursor_x = payload.x if payload.x is not None else (result or {}).get("x")
        cursor_y = payload.y if payload.y is not None else (result or {}).get("y")
        if cursor_x is not None and cursor_y is not None:
            job.latest_cursor = {"x": cursor_x, "y": cursor_y}
            with contextlib.suppress(Exception):
                await job._publish_surface_packet({
                    "type": "cursor",
                    "x": cursor_x,
                    "y": cursor_y,
                    "url": str(job.latest_url or ""),
                    "title": str(job.current_title or ""),
                    "surface_metrics": dict(job.latest_surface_metrics or {}),
                })
        if job.latest_image:
            with contextlib.suppress(Exception):
                await job._publish_surface_packet({
                    "type": "screenshot",
                    "image": str(job.latest_image or ""),
                    "url": str(job.latest_url or ""),
                    "title": str(job.current_title or ""),
                    "surface_metrics": dict(job.latest_surface_metrics or {}),
                })
        if job.latest_targets:
            with contextlib.suppress(Exception):
                await job._publish_surface_packet({
                    "type": "targets",
                    "items": list(job.latest_targets or []),
                    "url": str(job.latest_url or ""),
                    "title": str(job.current_title or ""),
                    "surface_metrics": dict(job.latest_surface_metrics or {}),
                })
        _persist_job_record(job)

    return {
        "success": bool(result.get("ok")),
        "session_id": sid,
        "action": action,
        "result": result,
        "url": str(current_url or ""),
    }


@app.post("/api/computer/resume")
@app.post("/api/desktop/resume")
@app.post("/api/local-computer/resume")
async def computer_resume(payload: ComputerResumeRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    job = global_agent_jobs.get(sid)
    resumed = await _resume_local_job_runtime(sid, job)
    if job:
        job.pending_manual_takeover = {}
        job.state = "running" if resumed else job.state
        job._touch(state_changed=True)
        with contextlib.suppress(Exception):
            await _sync_job_runtime_state(job)
        _persist_job_record(job)
    else:
        with contextlib.suppress(Exception):
            if resumed:
                agent_session_store.touch(sid, pending_manual_takeover={}, state="running")
            else:
                agent_session_store.touch(sid, pending_manual_takeover={})
    return {"success": resumed, "session_id": sid}


@app.get("/api/computer/tabs")
async def computer_tabs(session_id: str):
    sid = str(session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        payload = await browser_worker.browser_worker_host.get_tabs_payload(sid)
    except browser_worker.BrowserWorkerSessionNotFound:
        session = computer_agent.active_sessions.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Active computer session not found")
        payload = await session.get_tabs_payload()
    except browser_worker.BrowserWorkerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    job = global_agent_jobs.get(sid)
    if job:
        job.latest_url = str(payload.get("url") or job.latest_url or "")
        job._touch(state_changed=False)
        _persist_job_record(job)
    return {"success": True, "session_id": sid, **payload}


@app.post("/api/computer/tab/open")
async def computer_tab_open(payload: ComputerTabOpenRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        tabs_payload = await browser_worker.browser_worker_host.open_tab(sid, payload.url or "about:blank")
    except browser_worker.BrowserWorkerSessionNotFound:
        session = computer_agent.active_sessions.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Active computer session not found")
        tabs_payload = await session.open_tab(payload.url or "about:blank")
    except browser_worker.BrowserWorkerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    job = global_agent_jobs.get(sid)
    if job:
        job.latest_url = str(tabs_payload.get("url") or job.latest_url or "")
        job._touch(state_changed=False)
        _persist_job_record(job)
    return {"success": True, "session_id": sid, **tabs_payload}


@app.post("/api/computer/tab/switch")
async def computer_tab_switch(payload: ComputerTabSwitchRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        tabs_payload = await browser_worker.browser_worker_host.switch_tab(sid, payload.tab_id)
    except browser_worker.BrowserWorkerSessionNotFound:
        session = computer_agent.active_sessions.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Active computer session not found")
        tabs_payload = await session.switch_tab(payload.tab_id)
    except browser_worker.BrowserWorkerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    job = global_agent_jobs.get(sid)
    if job:
        job.latest_url = str(tabs_payload.get("url") or job.latest_url or "")
        job._touch(state_changed=False)
        _persist_job_record(job)
    return {"success": bool(tabs_payload.get("success", True)), "session_id": sid, **tabs_payload}


@app.post("/api/computer/tab/close")
async def computer_tab_close(payload: ComputerTabSwitchRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        tabs_payload = await browser_worker.browser_worker_host.close_tab(sid, payload.tab_id)
    except browser_worker.BrowserWorkerSessionNotFound:
        session = computer_agent.active_sessions.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Active computer session not found")
        tabs_payload = await session.close_tab(payload.tab_id)
    except browser_worker.BrowserWorkerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    job = global_agent_jobs.get(sid)
    if job:
        job.latest_url = str(tabs_payload.get("url") or job.latest_url or "")
        job._touch(state_changed=False)
        _persist_job_record(job)
    return {"success": True, "session_id": sid, **tabs_payload}


@app.get("/api/computer/live")
async def computer_live(session_id: str):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer job not found")
    from fastapi.responses import StreamingResponse as _MJPEGStreamingResponse
    return _MJPEGStreamingResponse(
        _mjpeg_stream(job),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/computer/history")
async def computer_history(session_id: str):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer job not found")
    with contextlib.suppress(Exception):
        await _refresh_live_surface(job)
    return {"success": True, **job.history_manifest()}


@app.get("/api/computer/history/manifest")
async def computer_history_manifest(session_id: str):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer job not found")
    with contextlib.suppress(Exception):
        await _refresh_live_surface(job)
    manifest = job.history_manifest()
    return {
        "success": True,
        "session_id": sid,
        "transport": "dvr",
        **manifest,
    }


@app.get("/api/computer/history/frame")
async def computer_history_frame(session_id: str, index: int = 0):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer job not found")
    frame = job.history_frame(index)
    if not frame:
        raise HTTPException(status_code=404, detail="Browser history frame not found")
    return {"success": True, "session_id": sid, **frame}


@app.get("/api/computer/history/segment")
async def computer_history_segment(session_id: str, index: int = 0):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer history segment not found")
    frame = job.history_frame(index)
    if not frame:
        raise HTTPException(status_code=404, detail="Browser history segment not found")
    return {
        "success": True,
        "session_id": sid,
        "segment_index": int(index),
        "kind": "frame",
        **frame,
    }


@app.get("/api/computer/history/state")
async def computer_history_state(session_id: str):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer job not found")
    manifest = job.history_manifest()
    state = str(job.state or "").strip().lower() or "idle"
    reconnectable = False
    with contextlib.suppress(Exception):
        reconnectable = browser_worker.browser_worker_host.has_session(sid) or (job.runner_task is not None and not job.runner_task.done())
    return {
        "success": True,
        "session_id": sid,
        "state": state,
        "live_edge": manifest.get("live_index", -1),
        "frame_count": len(manifest.get("frames") or []),
        "current_url": str(job.latest_url or ""),
        "current_title": str(job.current_title or ""),
        "pending_manual_takeover": bool(job.pending_manual_takeover),
        "pending_confirmation": bool(job.pending_confirmation),
        "reconnectable": bool(reconnectable),
        "history_horizon_seconds": int(getattr(job, "_history_horizon_seconds", 600.0) or 600),
    }


@app.get("/api/computer/surface")
async def computer_surface(session_id: str):
    sid = str(session_id or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        raise HTTPException(status_code=404, detail="Active computer job not found")

    async def surface_generator():
        last_idle_image = ""
        for packet in job.initial_surface_packets():
            yield f"data: {json.dumps(packet, ensure_ascii=False)}\n\n"
            if str(packet.get("type") or "").strip().lower() == "screenshot":
                last_idle_image = str(packet.get("image") or "")

        surface_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        job.surface_subscribers.append(surface_queue)
        try:
            while True:
                try:
                    packet = await asyncio.wait_for(surface_queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    refreshed = await _refresh_live_surface(job)
                    refreshed_image = str((refreshed or {}).get("image") or "")
                    if refreshed and refreshed_image and refreshed_image != last_idle_image:
                        last_idle_image = refreshed_image
                        yield f"data: {json.dumps(refreshed, ensure_ascii=False)}\n\n"
                        continue
                    yield f"data: {json.dumps({'type': 'surface_keepalive', 'session_id': sid}, ensure_ascii=False)}\n\n"
                    continue
                if packet is None:
                    break
                if str(packet.get("type") or "").strip().lower() == "screenshot":
                    last_idle_image = str(packet.get("image") or "")
                yield f"data: {json.dumps(packet, ensure_ascii=False)}\n\n"
        finally:
            if surface_queue in job.surface_subscribers:
                job.surface_subscribers.remove(surface_queue)

    from fastapi.responses import StreamingResponse as _SurfaceStreamingResponse
    return _SurfaceStreamingResponse(
        surface_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/ws/computer/surface")
async def computer_surface_socket(websocket: WebSocket):
    await websocket.accept()
    sid = str(websocket.query_params.get("session_id") or "").strip()
    job = await _get_or_rehydrate_computer_job(sid)
    if not sid or not job or job.agent_type != "computer":
        await websocket.send_json({"type": "error", "message": "Active computer job not found"})
        await websocket.close(code=4404)
        return

    surface_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    job.surface_subscribers.append(surface_queue)
    try:
        last_idle_image = ""
        async def _send_surface_packet(packet: Dict[str, Any]) -> None:
            packet_type = str((packet or {}).get("type") or "").strip().lower()
            if packet_type == "screenshot":
                image_payload = str(packet.get("image") or "")
                nonlocal last_idle_image
                last_idle_image = image_payload
                binary_payload = image_payload
                if binary_payload.startswith("data:"):
                    binary_payload = binary_payload.split(",", 1)[-1]
                meta_packet = {
                    key: value
                    for key, value in packet.items()
                    if key != "image"
                }
                meta_packet["type"] = "screenshot_meta"
                await websocket.send_json(meta_packet)
                try:
                    await websocket.send_bytes(base64.b64decode(binary_payload))
                except Exception:
                    fallback_packet = dict(packet)
                    fallback_packet["type"] = "screenshot"
                    await websocket.send_json(fallback_packet)
                return
            await websocket.send_json(packet)

        for packet in job.initial_surface_packets():
            await _send_surface_packet(packet)
        while True:
            try:
                packet = await asyncio.wait_for(surface_queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                refreshed = await _refresh_live_surface(job)
                refreshed_image = str((refreshed or {}).get("image") or "")
                if refreshed and refreshed_image and refreshed_image != last_idle_image:
                    await _send_surface_packet(refreshed)
                    continue
                await websocket.send_json({"type": "surface_keepalive", "session_id": sid})
                continue
            if packet is None:
                break
            await _send_surface_packet(packet)
    except WebSocketDisconnect:
        pass
    finally:
        if surface_queue in job.surface_subscribers:
            job.surface_subscribers.remove(surface_queue)

# ─── Local Desktop Agent: Real-time Background Stream ────────────────────────

async def _surface_webrtc_offer(payload: ComputerWebRTCOfferRequest, *, agent_type: str):
    if not computer_webrtc.AIORTC_AVAILABLE:
        raise HTTPException(status_code=503, detail="WebRTC surface streaming is unavailable on this runtime")
    sid = str(payload.session_id or "").strip()
    normalized_agent_type = str(agent_type or "computer").strip().lower() or "computer"
    if normalized_agent_type == "computer":
        job = await _get_or_rehydrate_computer_job(sid)
        missing_detail = "Active computer job not found"
    else:
        job = global_agent_jobs.get(sid)
        if (not job or job.agent_type != normalized_agent_type) and sid:
            with contextlib.suppress(Exception):
                restored = agent_session_store.get(sid)
                if restored and restored.agent_type == normalized_agent_type:
                    job = BackgroundAgentJob(sid, restored.agent_type, restored.mode or "live")
                    job.sticky = bool(restored.sticky)
                    job.transport_preference = str(restored.transport_preference or "auto").strip() or "auto"
                    job.browser_shell = str((restored.metadata or {}).get("browser_shell") or "virtual")
                    job.latest_url = str(restored.current_url or "")
                    job.current_title = str(restored.current_title or "")
                    job.session_memory = list(restored.session_memory or [])[-6:]
                    job.decision_cache_ref = str(restored.decision_cache_ref or "")
                    job.pending_manual_takeover = dict(restored.pending_manual_takeover or {})
                    job.pending_confirmation = dict(restored.pending_confirmation or {})
                    job.last_result = str(restored.last_result or "")
                    job.state = str(restored.state or "running").strip().lower() or "running"
                    job.last_active_at = float(restored.last_active_at or time.time())
                    global_agent_jobs[sid] = job
        if (not job or job.agent_type != normalized_agent_type) and sid:
            with contextlib.suppress(Exception):
                import skemi_local_computer_backend
                local_sid = str(skemi_local_computer_backend.local_computer_state.get("session_id") or "").strip()
                if local_sid and local_sid == sid:
                    local_mode = str(skemi_local_computer_backend.local_computer_state.get("mode") or "phantom").strip().lower() or "phantom"
                    job = BackgroundAgentJob(sid, normalized_agent_type, local_mode)
                    job.runtime_agent_type = "desktop"
                    job.execution_surface = "local_computer"
                    job.surface_mode = local_mode
                    job.state = str(skemi_local_computer_backend.local_computer_state.get("status") or "running").strip().lower() or "running"
                    frame = skemi_local_computer_backend._latest_frame
                    if frame:
                        job.latest_image = f"data:image/jpeg;base64,{base64.b64encode(frame).decode()}"
                    global_agent_jobs[sid] = job
        missing_detail = "Active desktop job not found"
    if not sid or not job or job.agent_type != normalized_agent_type:
        raise HTTPException(status_code=404, detail=missing_detail)
    try:
        job.transport_preference = "webrtc"
        job._touch(state_changed=False)
        _persist_job_record(job)
        with contextlib.suppress(Exception):
            await _refresh_live_surface(job)
        answer = await computer_webrtc.browser_webrtc_hub.create_answer(
            sid,
            offer_sdp=str(payload.sdp or ""),
            offer_type=str(payload.type or "offer"),
            job=job,
            frame_refresh_cb=lambda: _refresh_live_surface(job),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"success": True, "session_id": sid, **answer}


@app.post("/api/computer/webrtc/offer")
async def computer_webrtc_offer(payload: ComputerWebRTCOfferRequest):
    return await _surface_webrtc_offer(payload, agent_type="computer")


@app.post("/api/desktop/webrtc/offer")
@app.post("/api/local-computer/webrtc/offer")
async def desktop_webrtc_offer(payload: ComputerWebRTCOfferRequest):
    return await _surface_webrtc_offer(payload, agent_type="desktop")


@app.post("/api/computer/reset-session")
async def computer_reset_session(payload: ComputerStopRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    with contextlib.suppress(Exception):
        await browser_worker.browser_worker_host.stop_session(sid)
    if sid in global_agent_jobs:
        with contextlib.suppress(Exception):
            await global_agent_jobs[sid].request_stop("Da reset browser session.")
        global_agent_jobs.pop(sid, None)
    agent_session_store.delete(sid)
    return {"success": True, "session_id": sid}


import desktop_agent
desktop_agent.register(app)


def _job_runtime_agent_type(job: Optional[BackgroundAgentJob]) -> str:
    if not job:
        return "desktop"
    return str(getattr(job, "runtime_agent_type", job.agent_type) or job.agent_type or "desktop").strip().lower() or "desktop"


def _job_host_has_session(job: Optional[BackgroundAgentJob], session_id: str = "") -> bool:
    sid = str(session_id or getattr(job, "session_id", "") or "").strip()
    runtime_agent_type = _job_runtime_agent_type(job)
    if not sid:
        return False
    if runtime_agent_type == "computer":
        return bool(browser_worker.browser_worker_host.has_session(sid))
    return bool(desktop_companion.desktop_companion_host.has_session(sid))


async def _stop_local_job_runtime(session_id: str, job: Optional[BackgroundAgentJob] = None) -> bool:
    sid = str(session_id or "").strip()
    runtime_agent_type = _job_runtime_agent_type(job or global_agent_jobs.get(sid))
    if not job and runtime_agent_type != "computer" and browser_worker.browser_worker_host.has_session(sid):
        runtime_agent_type = "computer"
    if runtime_agent_type == "computer":
        with contextlib.suppress(browser_worker.BrowserWorkerSessionNotFound):
            return bool(await browser_worker.browser_worker_host.stop_session(sid))
        return False
    try:
        return bool(await desktop_companion.desktop_companion_host.stop_session(sid))
    except desktop_companion.DesktopCompanionSessionNotFound:
        return bool(desktop_agent.stop_session(sid))
    except desktop_companion.DesktopCompanionError:
        return bool(desktop_agent.stop_session(sid))


async def _close_local_job_runtime(session_id: str, job: Optional[BackgroundAgentJob] = None) -> bool:
    sid = str(session_id or "").strip()
    runtime_agent_type = _job_runtime_agent_type(job or global_agent_jobs.get(sid))
    if not job and runtime_agent_type != "computer" and browser_worker.browser_worker_host.has_session(sid):
        runtime_agent_type = "computer"
    if runtime_agent_type == "computer":
        with contextlib.suppress(browser_worker.BrowserWorkerSessionNotFound):
            return bool(await browser_worker.browser_worker_host.stop_session(sid))
        return False
    try:
        return bool(await desktop_companion.desktop_companion_host.close_session(sid))
    except desktop_companion.DesktopCompanionSessionNotFound:
        return bool(desktop_agent.close_session(sid))
    except desktop_companion.DesktopCompanionError:
        return bool(desktop_agent.close_session(sid))


async def _confirm_local_job_runtime(session_id: str, approved: bool, job: Optional[BackgroundAgentJob] = None) -> bool:
    sid = str(session_id or "").strip()
    runtime_agent_type = _job_runtime_agent_type(job or global_agent_jobs.get(sid))
    if not job and runtime_agent_type != "computer" and browser_worker.browser_worker_host.has_session(sid):
        runtime_agent_type = "computer"
    if runtime_agent_type == "computer":
        try:
            return bool(await browser_worker.browser_worker_host.confirm_session(sid, bool(approved)))
        except browser_worker.BrowserWorkerSessionNotFound:
            session = computer_agent.active_sessions.get(sid)
            if not session:
                raise HTTPException(status_code=404, detail="Active Local Computer session not found")
            return bool(session.resolve_confirmation(bool(approved)))
        except browser_worker.BrowserWorkerError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    try:
        return bool(await desktop_companion.desktop_companion_host.confirm_session(sid, bool(approved)))
    except desktop_companion.DesktopCompanionSessionNotFound:
        session = desktop_agent.active_sessions.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Active desktop session not found")
        return bool(session.resolve_confirmation(bool(approved)))
    except desktop_companion.DesktopCompanionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


async def _resume_local_job_runtime(session_id: str, job: Optional[BackgroundAgentJob] = None) -> bool:
    sid = str(session_id or "").strip()
    runtime_agent_type = _job_runtime_agent_type(job or global_agent_jobs.get(sid))
    if not job and runtime_agent_type != "computer" and browser_worker.browser_worker_host.has_session(sid):
        runtime_agent_type = "computer"
    if runtime_agent_type == "computer":
        try:
            return bool(await browser_worker.browser_worker_host.resume_session(sid))
        except browser_worker.BrowserWorkerSessionNotFound:
            session = computer_agent.active_sessions.get(sid)
            if not session or not hasattr(session, "resume_manual_takeover"):
                raise HTTPException(status_code=404, detail="Active Local Computer session not found")
            return bool(session.resume_manual_takeover())
        except browser_worker.BrowserWorkerError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    session = desktop_agent.active_sessions.get(sid)
    if session and hasattr(session, "resume_manual_takeover"):
        return bool(session.resume_manual_takeover())
    raise HTTPException(status_code=400, detail="Manual resume is not supported for this Local Computer session")

@app.api_route("/api/desktop/stream", methods=["GET", "POST"])
@app.api_route("/api/local-computer/stream", methods=["GET", "POST"])
async def desktop_stream(request: Request, payload: Optional[ComputerStreamRequest] = Body(None)):
    """
    Real-time Desktop Streaming Endpoint.
    Handles session initialization (POST) and status polling (GET).
    """
    # Support polling connection for existing session via HTTP GET
    if request.method == "GET":
        session_id = request.query_params.get("session_id", "").strip()
        if not session_id or session_id not in global_agent_jobs:
            raise HTTPException(status_code=404, detail="Active job not found")
        job = global_agent_jobs[session_id]

    else:
        # POST: Start a new session
        if not payload:
            raise HTTPException(status_code=400, detail="Missing request body")
            
        command = str(payload.command or "").strip()
        if not command:
            raise HTTPException(status_code=400, detail="command is required")
        with contextlib.suppress(Exception):
            skemi_local_computer_backend.local_computer_state["is_voice_session"] = False

        mode = _normalize_local_mode(str(payload.mode or "live").strip().lower() or "live")
        route = _route_local_computer_command(command, mode)
        runtime_agent_type = str(route.get("runtime_agent_type") or "desktop").strip().lower() or "desktop"
        browser_shell = str(route.get("browser_shell") or "virtual").strip() or "virtual"
        transport_preference = str(getattr(payload, "transport_preference", "auto") or "auto").strip() or "auto"
        try:
            desktop_index = int(getattr(payload, "desktop_index", -1))
        except Exception:
            desktop_index = -1
        if desktop_index < 0:
            with contextlib.suppress(Exception):
                desktop_index = int(skemi_local_computer_backend.local_computer_state.get("target_desktop_index"))
        lock_token = str(getattr(payload, "lock_token", "") or "").strip()
        if mode in {"background", "isolated"} and desktop_index >= 0:
            with contextlib.suppress(Exception):
                skemi_local_computer_backend.local_computer_state["target_desktop_index"] = desktop_index
                skemi_local_computer_backend.local_computer_state["phantom_lock_active"] = True
                if lock_token:
                    skemi_local_computer_backend.local_computer_state["phantom_lock_token"] = lock_token
                desktop_agent._target_desktop_index = desktop_index
        if runtime_agent_type == "computer":
            transport_preference = "mjpeg"

        stale_desktop_sessions = [
            existing_sid
            for existing_sid, existing_job in list(global_agent_jobs.items())
            if existing_sid and existing_sid != str(payload.reuse_session_id or "").strip()
            and str(getattr(existing_job, "agent_type", "") or "").strip().lower() == "desktop"
        ]
        for existing_sid in stale_desktop_sessions:
            existing_job = global_agent_jobs.get(existing_sid)
            with contextlib.suppress(Exception):
                await _close_local_job_runtime(existing_sid, existing_job)
            if existing_sid in global_agent_jobs:
                global_agent_jobs.pop(existing_sid, None)
            with contextlib.suppress(Exception):
                agent_session_store.delete(existing_sid)
        if runtime_agent_type == "desktop":
            with contextlib.suppress(Exception):
                if bool(skemi_local_computer_backend.local_computer_state.get("preview_only", False)):
                    async with skemi_local_computer_backend._local_lock:
                        await skemi_local_computer_backend._stop_current_session_locked(
                            "Phantom preview replaced by a real desktop task."
                        )
        
        try:
            if runtime_agent_type == "computer":
                session_id, event_generator = await browser_worker.browser_worker_host.start_session(
                    command,
                    reuse_session_id="",
                    sticky=False,
                    browser_shell=browser_shell,
                    bypass_safety=True,
                )
            else:
                session_id, event_generator = await desktop_companion.desktop_companion_host.start_session(
                    command,
                    mode=mode,
                    bypass_safety=True,
                    desktop_index=desktop_index,
                    plan={"desktop_index": desktop_index} if desktop_index >= 0 else None,
                )
        except Exception as e:
            print(f"!!! [SERVER] Failed to start desktop session: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": f"Không thể khởi động Local Computer: {str(e)}",
                    "detail": "Hãy đảm bảo Skemi Agent đang được chạy và không có phiên khác đang hoạt động."
                }
            )

        # Register background task
        job = BackgroundAgentJob(session_id, "desktop", mode)
        job.runtime_agent_type = runtime_agent_type
        job.execution_surface = str(route.get("execution_surface") or job._infer_execution_surface()).strip().lower() or job._infer_execution_surface()
        job.browser_shell = browser_shell
        browser_profile = {}
        if runtime_agent_type == "computer":
            with contextlib.suppress(Exception):
                browser_profile = computer_agent._build_browser_task_profile_v2(command)
        job.apply_request_context(
            command=command,
            sticky=False,
            transport_preference=transport_preference,
            browser_shell=browser_shell,
            user_language=str(browser_profile.get("language") or ""),
            prompt_text=str(browser_profile.get("prompt_text") or ""),
        )
        job.history.append(
            "event: session\n"
            f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'mode': job.mode, 'agent_type': job.agent_type, 'runtime_agent_type': job.runtime_agent_type, 'execution_surface': job.execution_surface, 'browser_shell': job.browser_shell}, ensure_ascii=False)}\n\n"
        )
        job.history.append(job.session_state_chunk())
        global_agent_jobs[session_id] = job
        _persist_job_record(job)
        if runtime_agent_type == "desktop":
            with contextlib.suppress(Exception):
                skemi_local_computer_backend.local_computer_state["mode"] = "phantom" if mode in {"background", "isolated"} else "live"
                skemi_local_computer_backend.local_computer_state["surface_mode"] = mode
                skemi_local_computer_backend.local_computer_state["status"] = "running"
                skemi_local_computer_backend.local_computer_state["task_state"] = "working"
                skemi_local_computer_backend.local_computer_state["stream_state"] = "live"
                skemi_local_computer_backend.local_computer_state["session_id"] = session_id
                skemi_local_computer_backend.local_computer_state["stream_url"] = "/api/local-computer/live"
                skemi_local_computer_backend.local_computer_state["preview_only"] = False
                skemi_local_computer_backend.local_computer_state["last_ai_action_desc"] = "Local Computer is working on the locked desktop."
                skemi_local_computer_backend.local_computer_state["last_seen_at"] = time.time()
        job.runner_task = asyncio.create_task(job.run_loop(event_generator))

    async def sse_generator():
        # First push history down the pipe
        for chunk in job.history:
            yield chunk

        # Subscribe to new events
        q = asyncio.Queue()
        job.subscribers.append(q)
        try:
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if q in job.subscribers:
                job.subscribers.remove(q)

    from fastapi.responses import StreamingResponse as _SSEStreamingResponse
    return _SSEStreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/desktop/stop")
@app.post("/api/local-computer/stop")
async def desktop_stop(payload: ComputerStopRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    job = global_agent_jobs.get(sid)
    if job:
        with contextlib.suppress(Exception):
            await _sync_job_runtime_state(job)
    stopped = await _stop_local_job_runtime(sid, job)
    stop_message = "Local Computer stopped by user."
    if sid in global_agent_jobs:
        await global_agent_jobs[sid].request_stop(stop_message)
        _persist_job_record(global_agent_jobs[sid])
    else:
        with contextlib.suppress(Exception):
            agent_session_store.touch(sid, state="stopped")
    response_payload = {"stopped": stopped, "session_id": sid}
    with contextlib.suppress(Exception):
        lc_state = skemi_local_computer_backend.local_computer_state
        if str(lc_state.get("session_id") or "").strip() == sid:
            lc_state["status"] = "stopped"
            lc_state["pending_confirmation"] = {}
            lc_state["last_seen_at"] = time.time()
            mode = str(lc_state.get("mode") or "live")
            base_notes = list(skemi_local_computer_backend._mode_notes(mode, connected=bool(lc_state.get("connected")), running=False)[:2])
            current_detail = str(lc_state.get("last_ai_action_desc") or "").strip()
            spoken_stop = f"Đã dừng. Trạng thái hiện tại: {current_detail or stop_message}"
            lc_state["last_ai_action_desc"] = spoken_stop
            lc_state["notes"] = base_notes + [spoken_stop]
            with contextlib.suppress(Exception):
                skemi_local_computer_backend._queue_voice_reply(spoken_stop)
            if job and str(job.latest_image or "").strip():
                lc_state["stream_url"] = str(lc_state.get("stream_url") or "/api/local-computer/mjpeg")
            response_payload.update(skemi_local_computer_backend._local_payload())
    return response_payload


@app.post("/api/desktop/confirm")
@app.post("/api/local-computer/confirm")
async def desktop_confirm(payload: ComputerConfirmRequest):
    sid = str(payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    job = global_agent_jobs.get(sid)
    resolved = await _confirm_local_job_runtime(sid, bool(payload.approved), job)
    if job:
        job.pending_confirmation = {}
        job.requires_consent = False
        job.consent_reason = ""
        job.state = "running" if resolved and payload.approved else ("stopped" if resolved else job.state)
        job._touch(state_changed=True)
        with contextlib.suppress(Exception):
            await _sync_job_runtime_state(job)
        _persist_job_record(job)
    else:
        with contextlib.suppress(Exception):
            agent_session_store.touch(sid, pending_confirmation={}, state="running" if resolved and payload.approved else "stopped")
    return {"success": resolved, "session_id": sid, "approved": bool(payload.approved)}


@app.post("/api/desktop/update-mode")
@app.post("/api/local-computer/update-mode")
async def desktop_update_mode(payload: Dict[str, Any]):
    sid = str(payload.get("session_id") or "").strip()
    mode = _normalize_local_mode(str(payload.get("mode") or "").strip())
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    success = False
    job = global_agent_jobs.get(sid)
    if job:
        job.mode = mode or job.mode
        if not str(getattr(job, "execution_surface", "") or "").strip():
            job.execution_surface = job._infer_execution_surface()
        job._touch(state_changed=True)
        _persist_job_record(job)
        success = True
    return {"success": success, "session_id": sid, "mode": mode}

@app.post("/api/desktop/reset-session")
@app.post("/api/local-computer/reset-session")
async def desktop_reset_session(payload: Dict[str, Any]):
    sid = str(payload.get("session_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    job = global_agent_jobs.get(sid)
    stopped = await _close_local_job_runtime(sid, job)
    if sid in global_agent_jobs:
        with contextlib.suppress(Exception):
            await global_agent_jobs[sid].request_stop("Da reset local session.", close_runtime=True)
        global_agent_jobs.pop(sid, None)
    agent_session_store.delete(sid)
    return {"success": True, "stopped": bool(stopped), "session_id": sid}


@app.get("/api/desktop/live")
@app.get("/api/local-computer/live")
async def desktop_live(session_id: str):
    sid = str(session_id or "").strip()
    job = global_agent_jobs.get(sid)
    if not sid or not job or job.agent_type != "desktop":
        raise HTTPException(status_code=404, detail="Active desktop job not found")
    from fastapi.responses import StreamingResponse as _MJPEGStreamingResponse
    return _MJPEGStreamingResponse(
        _mjpeg_stream(job),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/api/computer/status")
async def computer_status():
    """Returns active background computer/desktop jobs."""
    with contextlib.suppress(Exception):
        agent_session_store.cleanup_expired()
    sync_tasks = [
        _sync_job_runtime_state(job)
        for job in list(global_agent_jobs.values())
        if not bool(getattr(job, "done", False))
    ]
    if sync_tasks:
        with contextlib.suppress(Exception):
            await asyncio.gather(*sync_tasks, return_exceptions=True)
    active_jobs = []
    seen_ids = set()
    def _should_hide_stale_job(state: str, reconnectable: bool, pending_manual_takeover: Dict[str, Any], pending_confirmation: Dict[str, Any]) -> bool:
        normalized_state = str(state or "").strip().lower()
        if reconnectable:
            return False
        if pending_manual_takeover or pending_confirmation:
            return False
        return normalized_state in {"idle", "ready", "stopped", "closed", "done"}
    for sid, job in list(global_agent_jobs.items()):
        snapshot = job.state_snapshot()
        runtime_agent_type = str(snapshot.get("runtime_agent_type") or _job_runtime_agent_type(job)).strip().lower() or _job_runtime_agent_type(job)
        reconnectable = _job_host_has_session(job, sid) or (job.runner_task is not None and not job.runner_task.done())
        state = str(snapshot.get("state") or "").strip().lower() or "idle"
        pending_manual_takeover = dict(snapshot.get("pending_manual_takeover") or {})
        pending_confirmation = dict(snapshot.get("pending_confirmation") or {})
        if _should_hide_stale_job(state, reconnectable, pending_manual_takeover, pending_confirmation):
            continue
        active_jobs.append({
            "id": sid,
            "type": job.agent_type,
            "mode": getattr(job, "mode", "live"),
            "done": bool(job.done),
            "state": state,
            "message": snapshot.get("message") or ("Đang chạy ngầm..." if not job.done else "Đã hoàn thành"),
            "history_count": len(job.history),
            "sticky": bool(snapshot.get("sticky")),
            "runtime_agent_type": runtime_agent_type,
            "execution_surface": snapshot.get("execution_surface") or getattr(job, "execution_surface", ""),
            "stream_health": snapshot.get("stream_health") or getattr(job, "stream_health", "booting"),
            "last_frame_at": snapshot.get("last_frame_at") or 0.0,
            "last_action_at": snapshot.get("last_action_at") or 0.0,
            "stall_reason": snapshot.get("stall_reason") or "",
            "requires_consent": bool(snapshot.get("requires_consent")),
            "consent_reason": snapshot.get("consent_reason") or "",
            "browser_shell": snapshot.get("browser_shell") or getattr(job, "browser_shell", "virtual"),
            "current_url": snapshot.get("current_url") or "",
            "current_title": snapshot.get("current_title") or "",
            "pending_manual_takeover": pending_manual_takeover,
            "pending_confirmation": pending_confirmation,
            "last_result": snapshot.get("last_result") or "",
            "transport_preference": snapshot.get("transport_preference") or "auto",
            "last_active_at": snapshot.get("last_active_at") or time.time(),
            "reconnectable": bool(reconnectable),
        })
        seen_ids.add(sid)
    for record in agent_session_store.list_active():
        if record.session_id in seen_ids:
            continue
        reconnectable = False
        live_payload: Dict[str, Any] = {}
        runtime_agent_type = str((record.metadata or {}).get("runtime_agent_type") or record.agent_type or "computer").strip().lower() or "computer"
        if runtime_agent_type == "computer":
            with contextlib.suppress(Exception):
                reconnectable = browser_worker.browser_worker_host.has_session(record.session_id)
                if reconnectable:
                    live_payload = await browser_worker.browser_worker_host.get_session_snapshot(record.session_id)
        elif runtime_agent_type == "desktop":
            with contextlib.suppress(Exception):
                reconnectable = desktop_companion.desktop_companion_host.has_session(record.session_id)
                if reconnectable:
                    live_payload = await desktop_companion.desktop_companion_host.get_session_snapshot(record.session_id)
        state = str(live_payload.get("state") or record.state or "").strip().lower() or "done"
        current_url = str(live_payload.get("current_url") or record.current_url or "")
        current_title = str(live_payload.get("current_title") or record.current_title or "")
        pending_manual_takeover = dict(live_payload.get("pending_manual_takeover") or record.pending_manual_takeover or {})
        pending_confirmation = dict(live_payload.get("pending_confirmation") or record.pending_confirmation or {})
        last_result = str(live_payload.get("last_result") or record.last_result or "")
        transport_preference = str(live_payload.get("transport_preference") or record.transport_preference or "auto")
        metadata_message = str(live_payload.get("message") or (record.metadata or {}).get("message") or "")
        if _should_hide_stale_job(state, reconnectable, pending_manual_takeover, pending_confirmation):
            continue
        active_jobs.append({
            "id": record.session_id,
            "type": record.agent_type,
            "mode": record.mode,
            "done": not reconnectable and state not in {"idle", "running", "pending_confirmation", "pending_manual_takeover"},
            "state": state,
            "message": metadata_message,
            "history_count": int((record.metadata or {}).get("history_count") or 0),
            "sticky": bool(record.sticky),
            "runtime_agent_type": runtime_agent_type,
            "execution_surface": str(live_payload.get("execution_surface") or (record.metadata or {}).get("execution_surface") or ""),
            "stream_health": str(live_payload.get("stream_health") or (record.metadata or {}).get("stream_health") or "booting"),
            "last_frame_at": float(live_payload.get("last_frame_at") or (record.metadata or {}).get("last_frame_at") or 0.0),
            "last_action_at": float(live_payload.get("last_action_at") or (record.metadata or {}).get("last_action_at") or 0.0),
            "stall_reason": str(live_payload.get("stall_reason") or (record.metadata or {}).get("stall_reason") or ""),
            "requires_consent": bool(live_payload.get("requires_consent") or (record.metadata or {}).get("requires_consent")),
            "consent_reason": str(live_payload.get("consent_reason") or (record.metadata or {}).get("consent_reason") or ""),
            "browser_shell": str(live_payload.get("browser_shell") or (record.metadata or {}).get("browser_shell") or "virtual"),
            "current_url": current_url,
            "current_title": current_title,
            "pending_manual_takeover": pending_manual_takeover,
            "pending_confirmation": pending_confirmation,
            "last_result": last_result,
            "transport_preference": transport_preference,
            "last_active_at": float(live_payload.get("last_active_at") or record.last_active_at),
            "reconnectable": reconnectable,
        })
    active_jobs.sort(
        key=lambda item: (
            1 if bool(item.get("reconnectable")) else 0,
            1 if str(item.get("state") or "").strip().lower() == "running" else 0,
            float(item.get("last_active_at") or 0.0),
        ),
        reverse=True,
    )
    return {"success": True, "jobs": active_jobs}

def _safe_queue_size(queue: Any) -> int:
    try:
        return int(queue.qsize())
    except Exception:
        return 0


def _read_global_cache_stats() -> Dict[str, Any]:
    try:
        with sqlite3.connect(global_cache.db_path) as conn:
            row_count = int(conn.execute("SELECT COUNT(*) FROM ai_cache").fetchone()[0] or 0)
            newest = conn.execute("SELECT MAX(created_at) FROM ai_cache").fetchone()[0]
        return {
            "db_path": global_cache.db_path,
            "entries": row_count,
            "latest_entry_at": newest,
        }
    except Exception as exc:
        return {"db_path": global_cache.db_path, "entries": 0, "error": str(exc)}


async def _probe_searxng_status(base_url: str) -> Dict[str, Any]:
    candidate = str(base_url or "").strip().rstrip("/")
    if not candidate:
        return {"enabled": False, "reachable": False, "error": "missing_base_url"}

    started = time.time()
    probe_url = f"{candidate}/search"
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            response = await client.get(
                probe_url,
                params={"q": "skemi health", "format": "json"},
                headers={"Accept": "application/json"},
            )
        latency_ms = round((time.time() - started) * 1000.0, 1)
        result_count = 0
        if "json" in str(response.headers.get("content-type", "")).lower():
            try:
                payload = response.json()
                result_count = len(payload.get("results") or [])
            except Exception:
                result_count = 0
        return {
            "enabled": True,
            "reachable": response.status_code == 200,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "result_count": result_count,
            "base_url": candidate,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "reachable": False,
            "base_url": candidate,
            "error": str(exc),
        }


async def _collect_search_engine_status() -> Dict[str, Any]:
    search_engine_info: Dict[str, Any] = {}
    local_search_engine = getattr(app, "skemi_search_engine", None) or getattr(backend, "search_engine", None)
    if local_search_engine and hasattr(local_search_engine, "get_engine_info"):
        try:
            search_engine_info = local_search_engine.get_engine_info()
        except Exception as exc:
            search_engine_info = {"error": str(exc)}

    providers = dict(search_engine_info.get("providers") or {})
    searxng_cfg = dict(providers.get("searxng") or {})
    searxng_status = await _probe_searxng_status(searxng_cfg.get("base_url")) if searxng_cfg.get("enabled") else {
        "enabled": False,
        "reachable": False,
    }

    return {
        "engine_info": search_engine_info,
        "provider_status": {
            "searxng": searxng_status,
            "duckduckgo_html": {"enabled": bool((providers.get("duckduckgo_html") or {}).get("enabled", False))},
            "brave_html": {"enabled": bool((providers.get("brave_html") or {}).get("enabled", False))},
            "startpage_html": {"enabled": bool((providers.get("startpage_html") or {}).get("enabled", False))},
            "qwant_html": {"enabled": bool((providers.get("qwant_html") or {}).get("enabled", False))},
            "mojeek_html": {"enabled": bool((providers.get("mojeek_html") or {}).get("enabled", False))},
        },
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


@app.get("/search/engine_info")
async def search_engine_info():
    return await _collect_search_engine_status()


@app.get("/system/status")
async def system_status():
    ephemeral_session_store.cleanup_expired_sessions()
    search_status = await _collect_search_engine_status()
    return {
        "status": "ok",
        "server": {
            "name": "skemi-canonical-local",
            "base_url": SERVER_BASE_URL,
            "chat_server_url": CHAT_SERVER_URL,
            "frontend_root": str(FRONTEND_ROOT),
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "chat_backend": {
            "main_model": getattr(backend, "MODEL_MAIN", ""),
            "router_model": getattr(backend, "MODEL_ROUTER", ""),
            "vision_model": getattr(backend, "MODEL_VISION", ""),
            "request_queue_size": _safe_queue_size(getattr(backend, "request_queue", None)),
        },
        "ephemeral_sessions": ephemeral_session_store.get_session_stats(),
        "cache": _read_global_cache_stats(),
        "search": search_status,
    }


class AskRequest(BaseModel):
    session_id: str = "default"
    question: str
    age_group: str = "middle"
    force_search: bool = False
    deep_research: bool = False


class AIChatJobRequest(BaseModel):
    session_id: str = "default"
    question: str
    age_group: str = "middle"
    force_search: bool = False
    deep_research: bool = False


class NotebookRequest(BaseModel):
    message: str
    file_context: Optional[Dict[str, Any]] = None
    sources: Optional[List[Dict[str, Any]]] = None
    systemPrompt: Optional[str] = None
    strict_source: bool = False  # Default to False for better multi-turn chat
    search_mode: bool = False


class DiagramRequest(BaseModel):
    analysis: str
    type: str = "mindmap"
    search_mode: bool = False


class MindmapTextRequest(BaseModel):
    text: str


class AnalyzeFileRequest(BaseModel):
    file_data: Dict[str, Any] = {}
    diagram_type: str = "mindmap"


class TranslateUIRequest(BaseModel):
    q: str
    source: str = "en"
    target: str = "en"
    format: str = "text"


class TranslateUIBatchRequest(BaseModel):
    texts: List[str] = []
    source: str = "auto"
    target: str = "en"


class MemoryEventRequest(BaseModel):
    user_id: str = "default_user"
    area: str
    title: str
    summary: str
    metadata: Dict[str, Any] = {}
    tags: List[str] = []


# SESSION_TTL, chat_sessions, and ai_chat_jobs moved to top

def _has_route(path: str) -> bool:
    return any(getattr(route, "path", None) == path for route in app.router.routes)


class _Utf8StaticFiles(StaticFiles):
    """StaticFiles that forces charset=utf-8 on JS/CSS/HTML so Vietnamese
    (and CJK/Thai/Arabic) diacritics never get mangled by the browser."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        ct = response.headers.get("content-type", "")
        if ct and ("javascript" in ct or "css" in ct or "html" in ct) and "charset" not in ct:
            response.headers["content-type"] = ct + "; charset=utf-8"
        return response


def _mount_static(path: str, directory: Path, name: str) -> None:
    if directory.exists() and not _has_route(path):
        app.mount(path, _Utf8StaticFiles(directory=str(directory)), name=name)


_mount_static("/Css", FRONTEND_ROOT / "Css", "css")
_mount_static("/Js", FRONTEND_ROOT / "Js", "js")
_mount_static("/uploads", FRONTEND_ROOT / "uploads", "uploads")
_mount_static("/skemma_chat_assets", SKEMMA_CHAT_ROOT, "skemma-chat-assets")


# ── Same-origin reverse proxy for the embedded Node apps ──────────────────────
# The Quiz Arena (:5000) and Skemi CLI / NOVA (:3000) are separate Node services
# that the Skemi server already auto-launches. Proxying them under /arena and /nova
# lets the whole app be served from ONE Skemi origin (no separate ports in the URL,
# no cross-origin) — the "đưa hết vào Skemi (1)" the user asked for — WITHOUT
# rewriting the apps (which would lose their realtime features). A small shim is
# injected so the apps' root-absolute `/api`, `/socket.io`, XHR and WebSocket calls
# are rewritten to go back through the same prefix.
_proxy_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False)
ARENA_UPSTREAM = "http://127.0.0.1:5000"
NOVA_UPSTREAM = "http://127.0.0.1:3000"
_HOP_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive"}


def _proxy_shim(prefix: str) -> str:
    p = json.dumps(prefix)
    return (
        "<script>(function(){var P=" + p + ";"
        "function fix(u){try{if(typeof u==='string'&&u.charAt(0)==='/'&&u.indexOf(P+'/')!==0&&u.indexOf(P)!==0){return P+u;}}catch(e){}return u;}"
        "var of=window.fetch;if(of){window.fetch=function(u,o){if(u&&u.url)return of(u,o);return of(fix(u),o);};}"
        "var ox=window.XMLHttpRequest;if(ox){var op=ox.prototype.open;ox.prototype.open=function(m,u){return op.apply(this,[m,fix(u)].concat([].slice.call(arguments,2)));};}"
        "var OW=window.WebSocket;if(OW){var nw=function(url,pr){try{if(typeof url==='string'){var a=document.createElement('a');a.href=url;if(a.pathname.indexOf(P)!==0){url=(location.protocol==='https:'?'wss://':'ws://')+location.host+P+a.pathname+a.search;}}}catch(e){}return pr?new OW(url,pr):new OW(url);};nw.prototype=OW.prototype;nw.CONNECTING=OW.CONNECTING;nw.OPEN=OW.OPEN;nw.CLOSING=OW.CLOSING;nw.CLOSED=OW.CLOSED;window.WebSocket=nw;}"
        "})();</script>"
    )


async def _proxy_http(request: Request, upstream: str, prefix: str, path: str) -> Response:
    url = upstream + "/" + path
    if request.url.query:
        url += "?" + request.url.query
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host",)}
    body = await request.body()
    try:
        r = await _proxy_client.request(request.method, url, headers=headers, content=body)
    except Exception as exc:  # upstream node app not up yet
        return Response(content=f"Dịch vụ chưa sẵn sàng ({exc}).", status_code=502)
    ctype = r.headers.get("content-type", "")
    content = r.content
    if "text/html" in ctype.lower():
        try:
            html = content.decode("utf-8", "replace")
            shim = _proxy_shim(prefix)
            # The proxied page lives at e.g. "/arena" (no trailing slash), so the app's
            # RELATIVE asset paths ("src/js/state.js", "src/css/style.css") resolve
            # against the Skemi ROOT and 404. A <base> pointing at the prefix makes them
            # resolve under the proxy instead. It must come BEFORE any asset tag, so
            # inject it right after the opening <head>. (Only relative, non-slash URLs
            # are affected; the shim above still handles root-relative fetch/XHR/WS.)
            if "<base" not in html.lower():
                _hi = html.lower().find("<head")
                if _hi != -1:
                    _he = html.find(">", _hi)
                    if _he != -1:
                        html = html[:_he + 1] + f'<base href="{prefix}/">' + html[_he + 1:]
            # <base> only fixes RELATIVE asset paths. Some proxied apps (NOVA) use
            # root-relative ones instead (href="/styles.css", src="/app.js") -- those
            # resolve against the Skemi origin regardless of <base> and 404. Rewrite
            # them to live under the proxy prefix, skipping anything already prefixed
            # or protocol-relative ("//host/...").
            def _rewrite_root_asset(m):
                attr, url = m.group(1), m.group(2)
                if url.startswith("/" + prefix.strip("/") + "/") or url.startswith(prefix + "/"):
                    return m.group(0)
                return f'{attr}="{prefix}{url}"'
            html = re.sub(r'\b(href|src)="(/(?!/)[^"]*)"', _rewrite_root_asset, html)
            html = html.replace("</head>", shim + "</head>", 1) if "</head>" in html else (shim + html)
            content = html.encode("utf-8")
        except Exception:
            pass
    out_headers = {k: v for k, v in r.headers.items() if k.lower() not in _HOP_HEADERS}
    return Response(content=content, status_code=r.status_code, headers=out_headers, media_type=ctype or None)


async def _proxy_ws(client_ws: WebSocket, upstream_ws_base: str, path: str) -> None:
    import websockets as _wslib
    await client_ws.accept()
    q = client_ws.url.query
    up_url = upstream_ws_base + "/" + path + (("?" + q) if q else "")
    try:
        async with _wslib.connect(up_url, max_size=None) as up:
            async def c2u():
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if msg.get("text") is not None:
                            await up.send(msg["text"])
                        elif msg.get("bytes") is not None:
                            await up.send(msg["bytes"])
                except Exception:
                    pass
            async def u2c():
                try:
                    async for m in up:
                        if isinstance(m, (bytes, bytearray)):
                            await client_ws.send_bytes(m)
                        else:
                            await client_ws.send_text(m)
                except Exception:
                    pass
            await asyncio.gather(c2u(), u2c())
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            await client_ws.close()


@app.api_route("/arena", methods=["GET"])
async def _arena_root(request: Request):
    return await _proxy_http(request, ARENA_UPSTREAM, "/arena", "")

@app.api_route("/arena/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def _arena_proxy(path: str, request: Request):
    return await _proxy_http(request, ARENA_UPSTREAM, "/arena", path)

@app.api_route("/nova", methods=["GET"])
async def _nova_root(request: Request):
    return await _proxy_http(request, NOVA_UPSTREAM, "/nova", "")

@app.api_route("/nova/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def _nova_proxy(path: str, request: Request):
    return await _proxy_http(request, NOVA_UPSTREAM, "/nova", path)

@app.websocket("/nova/{path:path}")
async def _nova_ws(websocket: WebSocket, path: str):
    await _proxy_ws(websocket, "ws://127.0.0.1:3000", path)

@app.websocket("/arena/{path:path}")
async def _arena_ws(websocket: WebSocket, path: str):
    await _proxy_ws(websocket, "ws://127.0.0.1:5000", path)


def serve_html_page(filename: str) -> FileResponse:
    # PATH-TRAVERSAL guard: a route param can carry "../" or (URL-decoded) "..\" on
    # Windows, so a plain `FRONTEND_ROOT / filename` could resolve OUTSIDE the
    # webroot and serve arbitrary files. Resolve and require the result to stay
    # inside FRONTEND_ROOT.
    root = FRONTEND_ROOT.resolve()
    try:
        page = (FRONTEND_ROOT / filename).resolve()
        page.relative_to(root)   # raises ValueError if escaped the root
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Page not found")
    if not page.is_file():
        raise HTTPException(status_code=404, detail=f"Page not found: {filename}")
    # Force charset=utf-8 in the HTTP Content-Type header. The header ALWAYS wins
    # over an in-document <meta charset>, so Vietnamese decodes correctly even if a
    # page's <head> is large or malformed — kills the "Tra c?u / C?i ??t" mojibake.
    return FileResponse(page, media_type="text/html; charset=utf-8")


def serve_skemma_chat_page() -> Response:
    page = SKEMMA_CHAT_ROOT / "Chat.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Skemma-main chat UI not found.")

    html = page.read_text(encoding="utf-8", errors="replace")
    asset_version = "bridge20260624e"
    html = re.sub(
        r'''href=(["'])(?:\./|/)?Css/(Chat|AIChat)\.css(?:\?v=[^"']*)?\1''',
        lambda match: f'href="/skemma_chat_assets/Css/{match.group(2)}.css?v={asset_version}"',
        html,
    )
    html = re.sub(
        r'''src=(["'])(?:\./|/)?Js/(Chat|User_navbar|Friends|SharedSettings|AIChat)\.js(?:\?v=[^"']*)?\1''',
        lambda match: f'src="/skemma_chat_assets/Js/{match.group(2)}.js?v={asset_version}"',
        html,
    )
    runtime_script = (
        "<script>"
        f"window.__SKEMMA_SOCKET_ORIGIN__={json.dumps(CHAT_SERVER_BASE_URL)};"
        f"window.__SKEMMA_AI_BASE_CANDIDATES__={json.dumps([f'{SERVER_BASE_URL}/api', CHAT_SERVER_BASE_URL + '/api', 'http://127.0.0.1:8001/api'])};"
        f"window.__SKEMMA_HOME_URL__={json.dumps(f'{SERVER_BASE_URL}/Home.html')};"
        "window.__SKEMMA_ENABLE_SOCKET__=false;"
        "</script>"
    )
    # Theme bootstrap — runs before skemma's Chat.js so the skemma bundle inherits
    # the Skemi-wide theme choice instead of falling back to its own DEFAULT_USER_DATA.theme='light'.
    # Reads skemi-theme / chat-theme from localStorage (set by Preferences.js across the rest of the app)
    # and writes data-theme to <html> and <body> early in <head>. Without this, Chat.html
    # renders dark text on dark bg / invisible buttons when user has dark theme active.
    # Theme bootstrap: align the skemma bundle with Skemi's chosen theme.
    # The skemma SharedSettings.js reads skemi_user_data.theme as the source of
    # truth (its DEFAULT_USER_DATA.theme is 'light') and calls setLocalTheme
    # which writes both keys back. So we must (a) set skemi-theme/chat-theme,
    # (b) patch skemi_user_data.theme, and (c) intercept the storage event from
    # any later "reset" so the user's choice survives. A MutationObserver re-asserts
    # data-theme/body class if skemma later flips them.
    theme_bootstrap = (
        "<script>(function(){try{"
        "var t=localStorage.getItem('skemi-theme')||localStorage.getItem('chat-theme')||'dark';"
        "if(t!=='light'&&t!=='dark'&&t!=='galaxy')t='dark';"
        "localStorage.setItem('skemi-theme',t);localStorage.setItem('chat-theme',t);"
        "try{var p=JSON.parse(localStorage.getItem('skemi_user_data')||'{}');p.theme=t;localStorage.setItem('skemi_user_data',JSON.stringify(p));}catch(e){}"
        "document.documentElement.setAttribute('data-theme',t);"
        "var apply=function(){"
        "if(!document.body)return;"
        "document.body.setAttribute('data-theme',t);"
        "document.body.classList.remove('light-mode','dark-mode','galaxy-mode');"
        "document.body.classList.add(t+'-mode');"
        "if(t==='galaxy')document.body.classList.add('dark-mode');"
        "};"
        "document.addEventListener('DOMContentLoaded',apply);"
        "window.addEventListener('load',function(){"
        "apply();"
        "var observer=new MutationObserver(function(){"
        "if(document.body.getAttribute('data-theme')!==t||document.documentElement.getAttribute('data-theme')!==t){"
        "document.documentElement.setAttribute('data-theme',t);apply();"
        "}});"
        "observer.observe(document.body,{attributes:true,attributeFilter:['data-theme','class']});"
        "observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});"
        "});"
        "}catch(e){}})();</script>"
    )
    # Language bootstrap — mirror of the theme bootstrap. The skemma SharedSettings.js
    # treats skemi_language as its own and, for a guest/new profile, resets it to its
    # DEFAULT 'en' (and syncs skemi_user_data.language back), which flipped the WHOLE
    # Skemi app to English after a single Chat visit. Here we capture the app's chosen
    # language (default 'vi') and patch skemi_user_data.language to match, so skemma
    # INHERITS the Skemi-wide language instead of overwriting it.
    lang_bootstrap = (
        "<script>(function(){try{"
        "var l=(localStorage.getItem('skemi_language')||'').trim().toLowerCase();"
        "if(!l)l='vi';"
        "localStorage.setItem('skemi_language',l);"
        "try{var p=JSON.parse(localStorage.getItem('skemi_user_data')||'{}');p.language=l;localStorage.setItem('skemi_user_data',JSON.stringify(p));}catch(e){}"
        "document.documentElement.lang=l;"
        "}catch(e){}})();</script>"
    )
    bridge_script = f'<script src="/Js/JobNotifier.js?v={asset_version}"></script>'
    user_data_script = f'<script src="/Js/UserDataManager.js?v={asset_version}"></script>'
    html = html.replace("</head>", f"{theme_bootstrap}{lang_bootstrap}{runtime_script}{bridge_script}{user_data_script}</head>", 1)
    return Response(content=html, media_type="text/html; charset=utf-8")


def _now() -> datetime:
    return datetime.utcnow()


def _cleanup_sessions() -> None:
    now = _now()
    expired = [
        session_id
        for session_id, payload in chat_sessions.items()
        if now - payload.get("updated_at", now) > SESSION_TTL
    ]
    for session_id in expired:
        chat_sessions.pop(session_id, None)


def _extract_json_block(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        snippet = raw[start : end + 1]
        try:
            parsed = json.loads(snippet)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_text(value: Any) -> str:
    res = str(value or "").strip()
    # Aggressively strip bolding as requested for clean UI
    return res.replace("**", "").replace("__", "")


def _decode_data_url(raw_content: str) -> bytes:
    payload = str(raw_content or "").strip()
    if not payload:
        return b""
    if ";base64," in payload:
        payload = payload.split(";base64,", 1)[1]
    try:
        return base64.b64decode(payload)
    except Exception:
        return b""


def _split_points(text: str, limit: int = 6) -> List[str]:
    chunks = re.split(r"[\n\r]+|(?<=[.!?])\s+", str(text or ""))
    points: List[str] = []
    for chunk in chunks:
        clean = re.sub(r"\s+", " ", chunk).strip(" -â€¢\t")
        if len(clean) >= 8:
            points.append(clean[:160])
        if len(points) >= limit:
            break
    return points


def _fallback_nodes(text: str, topic: str = "Mindmap") -> List[Dict[str, Any]]:
    return [{"text": point, "children": []} for point in _split_points(text, limit=8)]


def _sanitize_nodes(nodes: Any, depth: int = 0, max_depth: int = 4) -> List[Dict[str, Any]]:
    if depth >= max_depth or not isinstance(nodes, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    for item in nodes[:10]:
        if isinstance(item, str):
            text = item.strip()
            if text:
                cleaned.append({"text": text[:160], "children": []})
            continue

        if not isinstance(item, dict):
            continue

        text = _normalize_text(item.get("text") or item.get("label") or item.get("title"))
        if not text:
            continue

        children = _sanitize_nodes(item.get("children") or item.get("nodes") or [], depth + 1, max_depth)
        cleaned.append({"text": text[:160], "children": children})
    return cleaned


def _build_mermaid(topic: str, nodes: List[Dict[str, Any]]) -> str:
    safe_topic = _normalize_text(topic or "Mindmap").replace('"', "'")[:120]
    lines = ["graph TD", f'ROOT["{safe_topic}"]']
    counter = {"value": 0}

    def next_id() -> str:
        counter["value"] += 1
        return f"N{counter['value']}"

    def walk(parent_id: str, items: List[Dict[str, Any]]) -> None:
        for item in items:
            node_id = next_id()
            label = _normalize_text(item.get("text", "Node")).replace('"', "'")[:120]
            lines.append(f'{node_id}["{label}"]')
            lines.append(f"{parent_id} --> {node_id}")
            walk(node_id, item.get("children") or [])

    walk("ROOT", nodes)
    return "\n".join(lines)


async def _generate_text(prompt: str, model: Optional[str] = None, num_predict: int = 1200) -> str:
    chosen_model = model or getattr(backend, "MODEL_MAIN", "")
    return await backend._generate_text_once(
        chosen_model,
        prompt,
        timeout=float(getattr(backend, "CHAT_TIMEOUT_SECONDS", 90)),
        num_predict=num_predict,
    )


async def _smart_search(query: str, deep_research: bool = False) -> Any:
    search_engine = getattr(app, "skemi_search_engine", None) or getattr(backend, "search_engine", None)
    if search_engine is None:
        return ""

    try:
        return await search_engine.smart_search(
            query,
            recency_priority="medium",
            deep_research=deep_research,
            query_class="general",
        )
    except Exception as e:
        print(f"Search engine error: {e}")
        return ""


_SEARCH_RANGE_DAYS = {
    "1h": 1 / 24,
    "24h": 1,
    "7d": 7,
    "30d": 30,
}


def _search_result_to_text(search_result: Any) -> str:
    if isinstance(search_result, dict):
        return _normalize_text(
            search_result.get("knowledge_base")
            or search_result.get("answer")
            or search_result.get("analysis")
            or search_result.get("context")
            or ""
        )
    return _normalize_text(search_result)


def _search_result_to_sources(search_result: Any) -> List[Dict[str, Any]]:
    if not isinstance(search_result, dict):
        return []

    rows: List[Dict[str, Any]] = []
    
    # Handle V2 format (list of strings/URLs or list of dicts)
    v2_sources = search_result.get("sources", [])
    if v2_sources:
        for item in v2_sources:
            if isinstance(item, str):
                rows.append({
                    "title": "Search Result",
                    "url": item,
                    "snippet": "",
                    "content": "",
                    "source": urlparse(item).netloc
                })
            elif isinstance(item, dict):
                rows.append({
                    "title": item.get("title", "Search Result"),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                    "content": item.get("content", ""),
                    "source": item.get("source") or urlparse(item.get("url", "")).netloc
                })
        return rows

    # Legacy formats
    raw_items: List[Dict[str, Any]] = []
    for key in ("items", "sources", "urls"):
        value = search_result.get(key)
        if isinstance(value, list):
            raw_items = value
            break

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": _normalize_text(item.get("title") or item.get("name") or "Search result"),
                "snippet": _normalize_text(item.get("snippet") or item.get("content") or ""),
                "content": _normalize_text(item.get("content") or item.get("snippet") or ""),
                "url": _normalize_text(item.get("url")),
                "published_at": _normalize_text(item.get("published_at") or item.get("publishedAt") or item.get("date")),
                "source": _normalize_text(item.get("source") or item.get("domain")),
                "category": _normalize_text(item.get("category")),
                "language": _normalize_text(item.get("language") or item.get("lang")),
            }
        )
    return rows


def _parse_published_at(value: Any) -> Optional[datetime]:
    raw = _normalize_text(value)
    if not raw:
        return None
    cleaned = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt)
        except Exception:
            continue
    return None


def _query_requests_historical_info(text: str) -> bool:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return False

    years = sorted({int(y) for y in re.findall(r"(19\d{2}|20\d{2})", normalized)})
    if len(years) >= 2:
        return True
    current_year = datetime.utcnow().year
    return any(year <= current_year - 2 for year in years)


def _normalize_search_language(value: Any) -> str:
    lang = _normalize_text(value).lower()
    return lang if lang in {"vi", "en"} else ""


def _normalize_search_sort(value: Any) -> str:
    sort = _normalize_text(value).lower()
    return sort if sort in {"relevance", "date", "popular"} else "date"


def _format_local_source(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": _normalize_text(item.get("title") or item.get("title_hl") or "Search result"),
        "snippet": _normalize_text(item.get("description") or item.get("desc_hl") or ""),
        "content": _normalize_text(item.get("description") or item.get("desc_hl") or ""),
        "url": _normalize_text(item.get("url")),
        "published_at": _normalize_text(item.get("published_at")),
        "source": _normalize_text(item.get("source") or item.get("domain")),
        "domain": _normalize_text(item.get("domain") or _source_domain(item.get("url"))),
        "category": _normalize_text(item.get("category")),
        "language": _normalize_text(item.get("language")),
        "is_official_source": bool(item.get("is_official_source")),
        "source_trust_tier": _normalize_text(item.get("source_trust_tier")),
    }


def _deduplicate_sources(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (_normalize_text(row.get("url")) or _normalize_text(row.get("title"))).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _build_search_variants(query: str, deep: bool = False) -> List[str]:
    base = _normalize_text(query)
    if not base:
        return []

    current_year = datetime.utcnow().year
    variants = [base]
    lower = base.lower()
    if str(current_year) not in lower and not _query_requests_historical_info(base):
        variants.append(f"{base} {current_year}")
    if deep:
        current_month = datetime.utcnow().strftime("%Y-%m")
        if current_month.lower() not in lower:
            variants.append(f"{base} {current_month}")

    deduped: List[str] = []
    for variant in variants:
        cleaned = _normalize_text(variant)
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[: (5 if deep else 3)]


def _collect_local_search_sources(
    query: str,
    *,
    category: str = "",
    language: str = "",
    time_range: str = "",
    sort_by: str = "date",
    deep: bool = False,
    historical: bool = False,
) -> List[Dict[str, Any]]:
    if local_search_engine is None or not hasattr(local_search_engine, "search"):
        return []

    effective_sort = sort_by if historical else "date"
    collected: List[Dict[str, Any]] = []
    for index, variant in enumerate(_build_search_variants(query, deep=deep)):
        try:
            result = local_search_engine.search(
                variant,
                category=category,
                language=language,
                time_range=time_range,
                page=1,
                per_page=(12 if index == 0 else 8),
                sort_by=effective_sort,
            )
        except Exception as exc:
            print(f"LOCAL SEARCH ERROR [{variant}]: {exc}")
            continue

        for item in result.get("results", []) or []:
            collected.append(_format_local_source(item))
    return _deduplicate_sources(collected)


def _filter_latest_sources(
    rows: List[Dict[str, Any]],
    query: str,
    time_range: str = "",
    *,
    historical: bool = False,
    query_class: str = "general",
) -> List[Dict[str, Any]]:
    rows = _deduplicate_sources(rows)
    if not rows:
        return []

    local_search_engine = getattr(app, "skemi_search_engine", None) or getattr(backend, "search_engine", None)
    is_latest_model = str(query_class or "").strip().lower() == "latest_model"
    latest_policy: Dict[str, Set[str]] = {}
    if is_latest_model and local_search_engine and hasattr(local_search_engine, "_latest_model_domain_policy"):
        try:
            latest_policy = local_search_engine._latest_model_domain_policy(query)
            allowed_domains = latest_policy.get("allowed") or set()
            if allowed_domains and hasattr(local_search_engine, "_domain_matches_any"):
                latest_rows = [
                    row for row in rows
                    if local_search_engine._domain_matches_any(_source_domain(row.get("url")), allowed_domains)
                ]
                if latest_rows:
                    rows = latest_rows
        except Exception:
            latest_policy = {}

    focus_tokens: List[str] = []
    try:
        if local_search_engine and hasattr(local_search_engine, "_query_focus_tokens"):
            focus_tokens = sorted(
                set(local_search_engine._query_focus_tokens(query)),
                key=lambda item: (-len(item), item),
            )[:6]
    except Exception:
        focus_tokens = []
    if not focus_tokens:
        focus_tokens = [
            token
            for token in re.split(r"[^0-9A-Za-zÀ-ỹ._+-]+", _normalize_text(query).lower())
            if len(token) >= 3 and not token.isdigit()
        ]
        focus_tokens = sorted(set(focus_tokens), key=lambda item: (-len(item), item))[:6]

    dated = []
    undated = []
    for row in rows:
        dt = _parse_published_at(row.get("published_at"))
        if dt:
            dated.append({**row, "_published_dt": dt})
        else:
            undated.append(row)

    dated.sort(key=lambda item: item.get("_published_dt", datetime.min), reverse=True)

    if historical:
        ordered = dated + undated
    elif dated:
        latest_dt = dated[0]["_published_dt"]
        default_days = _SEARCH_RANGE_DAYS.get(time_range) or 180
        cutoff = latest_dt - timedelta(days=float(default_days))
        ordered = [item for item in dated if item.get("_published_dt") and item["_published_dt"] >= cutoff]
        minimum_keep = min(160, len(dated))
        if len(ordered) < minimum_keep:
            ordered = dated[:minimum_keep]
        if len(ordered) < 160:
            ordered.extend(undated[: max(0, 160 - len(ordered))])
    else:
        ordered = rows[:160]

    scored: List[Dict[str, Any]] = []
    now_dt = datetime.utcnow()
    for row in ordered:
        item = dict(row)
        title = _normalize_text(item.get("title")).lower()
        snippet = _normalize_text(item.get("snippet") or item.get("content")).lower()
        url = _normalize_text(item.get("url")).lower()
        text_blob = " ".join([title, snippet, url])
        low_signal_penalty = 0.0
        if local_search_engine and hasattr(local_search_engine, "_search_low_signal_penalty"):
            try:
                low_signal_penalty = float(local_search_engine._search_low_signal_penalty(title, snippet, url) or 0.0)
            except Exception:
                low_signal_penalty = 0.0

        focus_hits = sum(1 for token in focus_tokens if token in text_blob)
        trust_score = 0.0
        if item.get("is_official_source"):
            trust_score = 3.0
        elif _normalize_text(item.get("source_trust_tier")):
            trust_score = 2.0
        if is_latest_model and latest_policy and local_search_engine and hasattr(local_search_engine, "_domain_matches_any"):
            domain = _source_domain(item.get("url"))
            if local_search_engine._domain_matches_any(domain, latest_policy.get("official", set())):
                item["is_official_source"] = True
                item["source_trust_tier"] = _normalize_text(item.get("source_trust_tier")) or "official"
                trust_score += 2.5
            elif local_search_engine._domain_matches_any(domain, latest_policy.get("official_families", set())):
                item["is_official_source"] = True
                item["source_trust_tier"] = _normalize_text(item.get("source_trust_tier")) or "official_family"
                trust_score += 2.0
            elif local_search_engine._domain_matches_any(domain, latest_policy.get("press", set())):
                item["source_trust_tier"] = _normalize_text(item.get("source_trust_tier")) or "major_press"
                trust_score += 1.2
        if is_latest_model and low_signal_penalty >= 4.0 and not _search_source_is_high_trust(item):
            continue

        recency_score = 0.0
        published_dt = item.get("_published_dt")
        if isinstance(published_dt, datetime):
            age_days = max(0.0, (now_dt - published_dt).total_seconds() / 86400.0)
            if age_days <= 7:
                recency_score = 2.0
            elif age_days <= 30:
                recency_score = 1.5
            elif age_days <= 180:
                recency_score = 1.0
            else:
                recency_score = 0.4
            if not historical and age_days > 365:
                recency_score -= 0.9
            if not historical and age_days > 730:
                recency_score -= 1.6
            if not historical and age_days > 1460 and not _search_source_is_high_trust(item):
                recency_score -= 2.4
        if is_latest_model and re.search(r"\b(vs|versus|comparison|compare|so sanh|đối đầu)\b", text_blob):
            recency_score -= 0.9

        item["_quality_score"] = (focus_hits * 2.0) + trust_score + recency_score - (low_signal_penalty * 1.4)
        scored.append(item)

    scored.sort(
        key=lambda item: (
            float(item.get("_quality_score", 0.0)),
            item.get("_published_dt", datetime.min),
        ),
        reverse=True,
    )

    cleaned: List[Dict[str, Any]] = []
    # Deep research surfaces 100+ ranked sources (user goal). This is the final
    # display ceiling for the ranked source list.
    for row in scored[:160]:
        item = dict(row)
        item.pop("_published_dt", None)
        item.pop("_quality_score", None)
        cleaned.append(item)
    return cleaned


def _resolve_search_query_class(query: str) -> str:
    local_search_engine = getattr(app, "skemi_search_engine", None) or getattr(backend, "search_engine", None)
    try:
        if local_search_engine and hasattr(local_search_engine, "_is_latest_model_query") and local_search_engine._is_latest_model_query(query):
            return "latest_model"
    except Exception:
        pass
    lower = _normalize_text(query).lower()
    latest_like = bool(
        re.search(
            r"\b(latest|newest|current|recent|release|version)\b|mới nhất|moi nhat|hiện tại|hien tai|cập nhật|cap nhat|phiên bản|phien ban",
            lower,
            re.IGNORECASE,
        )
    )
    model_like = bool(
        re.search(
            r"\b(chatgpt|gpt|claude|gemini|grok|qwen|minimax|model|models)\b|mô hình|mo hinh",
            lower,
            re.IGNORECASE,
        )
    )
    if latest_like and model_like:
        return "latest_model"
    return "general"


def _extract_search_subjects(query: str, extra_queries: Optional[List[str]] = None) -> List[str]:
    local_search_engine = getattr(app, "skemi_search_engine", None) or getattr(backend, "search_engine", None)
    try:
        if local_search_engine and hasattr(local_search_engine, "_extract_latest_subjects"):
            seeds = [_normalize_text(query)]
            for item in extra_queries or []:
                cleaned = _normalize_text(item)
                if cleaned:
                    seeds.append(cleaned)

            extracted: List[Dict[str, Any]] = []
            for seed_index, seed in enumerate(seeds):
                for item in (local_search_engine._extract_latest_subjects(seed) or []):
                    value = _normalize_text(item).lower()
                    tokens = [token for token in re.findall(r"[a-z0-9]+", value) if len(token) > 1]
                    if value and tokens:
                        extracted.append({"value": value, "tokens": tokens, "seed_index": seed_index})

            if extracted:
                seed_count = len(seeds)
                token_frequency: Dict[str, int] = {}
                for item in extracted:
                    for token in set(item["tokens"]):
                        token_frequency[token] = token_frequency.get(token, 0) + 1

                support_floor = 2 if seed_count <= 3 else (seed_count // 2 + 1)
                grouped: Dict[str, Dict[str, Any]] = {}
                for item in extracted:
                    tokens = list(item["tokens"])
                    compressed_tokens = [
                        token for token in tokens if token_frequency.get(token, 0) >= support_floor
                    ]
                    if not compressed_tokens:
                        strongest = max(token_frequency.get(token, 0) for token in tokens)
                        compressed_tokens = [
                            token for token in tokens if token_frequency.get(token, 0) == strongest
                        ]
                    compressed_value = " ".join(compressed_tokens).strip()
                    if not compressed_value:
                        continue
                    group = grouped.setdefault(
                        compressed_value,
                        {"value": compressed_value, "tokens": compressed_tokens, "rows": []},
                    )
                    group["rows"].append(item)

                scored: List[tuple[float, str, List[str]]] = []
                unique_values = set(grouped.keys())
                for value, group in grouped.items():
                    tokens = list(group.get("tokens") or [])
                    rows = list(group.get("rows") or [])
                    if not tokens or not rows:
                        continue
                    avg_support = sum(token_frequency.get(token, 0) for token in set(tokens)) / max(1, len(set(tokens)))
                    router_bonus = 0.9 if any(row["seed_index"] > 0 for row in rows) else 0.0
                    coverage_bonus = len({row["seed_index"] for row in rows}) / max(1, seed_count)
                    group_bonus = min(1.2, 0.35 * len(rows))
                    compactness_bonus = 1.0 / max(1, len(tokens))
                    containment_bonus = 0.8 if any(
                        other != value and len(other.split()) > len(tokens) and value in other
                        for other in unique_values
                    ) else 0.0
                    score = avg_support + router_bonus + coverage_bonus + group_bonus + compactness_bonus + containment_bonus
                    scored.append((score, value, tokens))

                scored.sort(key=lambda item: (-item[0], len(item[2]), item[1]))
                selected: List[str] = []
                selected_token_sets: List[Set[str]] = []
                for _, value, tokens in scored:
                    token_set = set(tokens)
                    if any(token_set <= existing or existing <= token_set for existing in selected_token_sets):
                        if any(existing <= token_set and len(existing) < len(token_set) for existing in selected_token_sets):
                            continue
                    if value not in selected:
                        selected.append(value)
                        selected_token_sets.append(token_set)
                    if len(selected) >= 4:
                        break
                if selected:
                    stabilized: List[str] = []
                    seen_values: Set[str] = set()
                    for value in selected:
                        tokens = [token for token in re.findall(r"[a-z0-9]+", value) if len(token) > 1]
                        if not tokens:
                            continue
                        stable_tokens = [
                            token
                            for token in tokens
                            if token_frequency.get(token, 0) >= support_floor
                            and any(row["seed_index"] > 0 and token in row["tokens"] for row in extracted)
                        ]
                        if not stable_tokens:
                            stable_tokens = [
                                token for token in tokens if token_frequency.get(token, 0) >= support_floor
                            ]
                        if not stable_tokens:
                            stable_tokens = [
                                max(tokens, key=lambda token: (token_frequency.get(token, 0), -len(token), token))
                            ]
                        stable_value = " ".join(stable_tokens[:4]).strip()
                        if stable_value and stable_value not in seen_values:
                            seen_values.add(stable_value)
                            stabilized.append(stable_value)
                    if stabilized:
                        return stabilized[:4]
    except Exception:
        pass
    return []


def _select_router_queries_seed(query: str, router_queries: List[str], query_class: str) -> List[str]:
    normalized_query = _normalize_text(query)
    normalized_year_query = f"{normalized_query} {datetime.utcnow().year}".strip()
    deduped: List[str] = []
    seen: Set[str] = set()

    for item in router_queries or []:
        cleaned = _normalize_text(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)

    if not deduped:
        return [normalized_query] if normalized_query else []

    if str(query_class or "").strip().lower() != "latest_model":
        return deduped[:5]

    token_frequency: Dict[str, int] = {}
    token_map: Dict[str, List[str]] = {}
    query_tokens = [token for token in re.findall(r"[a-z0-9]+", normalized_query.lower()) if len(token) > 1 and not token.isdigit()]
    query_token_set = set(query_tokens)
    for item in deduped:
        tokens = [token for token in re.findall(r"[a-z0-9]+", item.lower()) if len(token) > 1 and not token.isdigit()]
        token_map[item] = tokens
        for token in set(tokens):
            token_frequency[token] = token_frequency.get(token, 0) + 1

    latest_markers = {"latest", "newest", "current", "official", "release", "version", "model", "moi", "nhat", "phien", "ban", "cap", "nhat", "ra", "mat"}
    scored: List[tuple[float, str]] = []
    for item in deduped:
        key = item.lower()
        tokens = token_map.get(item, [])
        token_set = set(tokens)
        support_score = sum(token_frequency.get(token, 0) for token in token_set)
        overlap_bonus = len(token_set & query_token_set) * 0.7
        latest_bonus = 0.8 if token_set & latest_markers else 0.0
        year_bonus = 0.5 if str(datetime.utcnow().year) in key else 0.0
        orphan_penalty = sum(1 for token in token_set if token_frequency.get(token, 0) == 1)
        raw_penalty = 1.4 if key in {normalized_query.lower(), normalized_year_query.lower()} else 0.0
        length_penalty = max(0, len(tokens) - 7) * 0.15
        score = support_score + overlap_bonus + latest_bonus + year_bonus - orphan_penalty * 1.35 - raw_penalty - length_penalty
        scored.append((score, item))

    scored.sort(key=lambda row: (-row[0], len(token_map.get(row[1], [])), row[1]))
    raw_keys = {normalized_query.lower(), normalized_year_query.lower()}
    clean_ranked = [item for _, item in scored if item.lower() not in raw_keys]
    if len(clean_ranked) >= 2:
        selected = clean_ranked[:3]
    else:
        selected = [item for _, item in scored[:3]]
    return selected or deduped[:3]


def _build_planned_search_queries(
    query: str,
    router_queries: List[str],
    language: str,
    query_class: str,
    latest_subjects: Optional[List[str]] = None,
) -> List[str]:
    cleaned: List[str] = []
    seen: Set[str] = set()

    def _push(candidate: str) -> None:
        value = _normalize_text(candidate)
        if not value:
            return
        key = value.lower()
        if key in seen:
            return
        seen.add(key)
        cleaned.append(value)

    if str(query_class or "").strip().lower() == "latest_model":
        current_year = datetime.utcnow().year
        current_month = datetime.utcnow().strftime("%Y-%m")
        for item in router_queries or []:
            _push(item)
            if len(cleaned) >= 5:
                return cleaned[:5]
        if not cleaned:
            _push(query)
        if len(cleaned) == 1 and str(current_year) not in cleaned[0]:
            _push(f"{cleaned[0]} {current_year}")
        if latest_subjects and len(cleaned) < 8:
            for subject in latest_subjects[:3]:
                if language == "vi":
                    _push(f"m? h?nh m?i nh?t c?a {subject}")
                    _push(f"ngu?n ch?nh th?c {subject} model m?i nh?t {current_year}")
                    _push(f"{subject} release notes {current_month}")
                else:
                    _push(f"latest {subject} model")
                    _push(f"official source {subject} latest model {current_year}")
                    _push(f"{subject} release notes {current_month}")
                if any(token in subject.lower() for token in ("chatgpt", "openai", "gpt")):
                    _push(f"site:openai.com latest ChatGPT model {current_year}")
                    _push(f"site:help.openai.com ChatGPT release notes {current_year}")
                elif any(token in subject.lower() for token in ("claude", "anthropic")):
                    _push(f"site:anthropic.com latest Claude model {current_year}")
                    _push(f"site:docs.anthropic.com Claude models overview {current_year}")
                if len(cleaned) >= 8:
                    break
        return cleaned[:8]


    for item in router_queries or []:
        _push(item)
        if len(cleaned) >= 4:
            break
    _push(query)
    return cleaned[:5] or [query]


def _infer_search_category(query: str, sources: List[Dict[str, Any]]) -> str:
    ranked = [
        src.get("category", "")
        for src in sources
        if _normalize_text(src.get("category")) and _normalize_text(src.get("category")) not in {"all", "general"}
    ]
    if ranked:
        return ranked[0]

    lower = _normalize_text(query).lower()
    rules = {
        "technology": ("ai", "model", "grok", "claude", "openai", "xai", "chip", "gpu", "software", "tech"),
        "business": ("stock", "market", "economy", "business", "startup", "finance"),
        "science": ("research", "science", "paper", "lab"),
        "health": ("health", "medical", "drug", "hospital", "doctor"),
        "education": ("study", "learning", "education", "school", "quiz"),
        "world": ("war", "election", "government", "world", "country"),
    }
    for category, markers in rules.items():
        if any(marker in lower for marker in markers):
            return category
    return ""


def _build_search_brief(
    query: str,
    sources: List[Dict[str, Any]],
    language: str = "vi",
    historical: bool = False,
    query_class: str = "general",
    latest_subjects: Optional[List[str]] = None,
) -> str:
    if not sources:
        return (
            "Chưa xác minh đủ nguồn mới và đủ tin cậy cho truy vấn này. Hãy thử rõ hơn mốc thời gian hoặc từ khóa cần tra cứu."
            if language != "en"
            else "Skemi could not verify enough fresh and reliable sources for this query yet. Try a clearer time range or a more specific keyword set."
        )

    if str(query_class or "").strip().lower() == "latest_model":
        subjects = list(latest_subjects or _extract_search_subjects(query))
        if subjects:
            subject_summaries = [
                _latest_model_subject_summary(subject, sources, language=language)
                for subject in subjects[:2]
            ]
            return " ".join(_clean_search_ui_text(item) for item in subject_summaries if item)

        latest_date = _clean_search_ui_text(next((item.get("published_at") for item in sources if item.get("published_at")), ""))
        detail_bits = _search_snippet_samples(sources, limit=2, max_chars=180)
        detail_text = " ".join(detail_bits).strip()
        if language != "en":
            return _clean_search_ui_text(
                "Các chi tiết bám trực tiếp vào chủ đề này hiện nằm ở lớp cập nhật mới nhất. "
                + (f"{detail_text} " if detail_text else "")
                + (f"Mốc gần nhất thấy rõ là {latest_date}." if latest_date else "")
            )
        return _clean_search_ui_text(
            "The retained detail is clustering around the newest topic-aligned update layer. "
            + (f"{detail_text} " if detail_text else "")
            + (f"The clearest recent date is {latest_date}." if latest_date else "")
        )

    intro = (
        "Skemi đã gom phần nội dung liên quan trực tiếp nhất theo đúng truy vấn của bạn."
        if language != "en"
        else "Skemi condensed the most directly relevant content for your query."
    )

    parts: List[str] = []
    for source in sources[:3]:
        snippet = re.sub(r"\s+", " ", _normalize_text(source.get("snippet") or source.get("content"))).strip()
        if len(snippet) > 180:
            snippet = snippet[:180].rsplit(" ", 1)[0] + "..."
        published = _parse_published_at(source.get("published_at"))
        date_label = published.strftime("%Y-%m-%d") if published else ""
        if snippet:
            parts.append(f"{snippet} {date_label}".strip())

    return " ".join([intro] + parts)

async def _build_mindmap_payload(source_text: str, topic_hint: str = "") -> Dict[str, Any]:
    source = _normalize_text(source_text)
    if not source:
        return {
            "topic": topic_hint or "Mindmap",
            "mindmap_nodes": [],
            "summary": [],
            "detail": [],
            "mermaid": "graph TD; ROOT[No data]",
        }

    prompt = (
        "Return valid JSON only with schema "
        '{"topic":"...","nodes":[{"text":"...","children":[...]}]}. '
        "Build a mindmap hierarchy with the main ideas first, then detailed branches. "
        f"Topic hint: {topic_hint or 'Mindmap'}.\n\nSource:\n{source[:8000]}"
    )
    raw = await _generate_text(prompt, model=getattr(backend, "MODEL_ROUTER", None), num_predict=900)
    parsed = _extract_json_block(raw)

    topic = _normalize_text(parsed.get("topic") or topic_hint or "Mindmap")
    nodes = _sanitize_nodes(parsed.get("nodes") or parsed.get("outline") or [])
    if not nodes:
        nodes = _fallback_nodes(source, topic)

    detail = []
    for node in nodes:
        detail.append(node["text"])
        for child in node.get("children", [])[:8]:
            detail.append(child.get("text", ""))

    return {
        "topic": topic,
        "mindmap_nodes": nodes,
        "summary": detail[:4],
        "detail": [item for item in detail if item],
        "mermaid": _build_mermaid(topic, nodes),
    }


async def _build_chart_payload(source_text: str) -> Dict[str, Any]:
    source = _normalize_text(source_text)
    prompt = (
        "Return valid JSON only with schema "
        '{"type":"bar","data":{"labels":[...],"datasets":[{"label":"...","data":[...]}]},"options":{}}. '
        "Create a compact Chart.js config from the source.\n\n"
        f"Source:\n{source[:6000]}"
    )
    raw = await _generate_text(prompt, model=getattr(backend, "MODEL_ROUTER", None), num_predict=700)
    parsed = _extract_json_block(raw)
    if isinstance(parsed.get("data"), dict):
        parsed.setdefault("type", "bar")
        parsed.setdefault("options", {"responsive": True, "maintainAspectRatio": False})
        return parsed

    labels = _split_points(source, limit=5)
    return {
        "type": "bar",
        "data": {
            "labels": labels or ["Item 1", "Item 2", "Item 3"],
            "datasets": [
                {
                    "label": "Value",
                    "data": [max(4, len(label.split()) * 3) for label in (labels or ["Item 1", "Item 2", "Item 3"])],
                    "backgroundColor": ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#06b6d4"],
                }
            ],
        },
        "options": {"responsive": True, "maintainAspectRatio": False},
    }


async def _build_timeline_payload(source_text: str) -> Dict[str, Any]:
    source = _normalize_text(source_text)
    prompt = (
        "Return valid JSON only with schema "
        '{"events":[{"date":"Phase 1","title":"...","description":"..."}]}. '
        "Create a practical timeline from the source.\n\n"
        f"Source:\n{source[:6000]}"
    )
    raw = await _generate_text(prompt, model=getattr(backend, "MODEL_ROUTER", None), num_predict=700)
    parsed = _extract_json_block(raw)
    events = parsed.get("events")
    if isinstance(events, list) and events:
        return {"events": events[:12]}

    points = _split_points(source, limit=5)
    return {
        "events": [
            {"date": f"Step {index + 1}", "title": point[:80], "description": point}
            for index, point in enumerate(points or ["Define scope", "Collect inputs", "Build output"])
        ]
    }


def _clean_line(value: Any, limit: int = 400) -> str:
    text = _normalize_text(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


async def _build_comic_payload(source_text: str) -> Dict[str, Any]:
    """Turn any source into a real sequential comic script (panels with scene,
    narration caption, character dialogue and a sound effect)."""
    source = _normalize_text(source_text)
    if not source:
        return {"title": "Comic", "logline": "", "panels": []}

    prompt = (
        "You are a comic-book scriptwriter. Convert the SOURCE into a vivid, sequential "
        "comic script of 6 panels that actually tells a story (setup -> rising action -> "
        "climax -> resolution). Each panel needs a concrete visual scene, a short narration "
        "caption, and 1-2 lines of character dialogue. Write in the SAME language as the source.\n"
        "Return valid JSON only, no markdown, with this exact schema:\n"
        '{"title":"...","logline":"one punchy sentence","panels":['
        '{"scene":"what the reader sees","caption":"narration box text",'
        '"dialogue":[{"speaker":"name","text":"line"}],"sfx":"BOOM"}]}\n\n'
        f"SOURCE:\n{source[:7000]}"
    )
    raw = await _generate_text(prompt, num_predict=1400)
    parsed = _extract_json_block(raw)

    title = _clean_line(parsed.get("title"), 120) or "Comic"
    logline = _clean_line(parsed.get("logline"), 200)
    panels: List[Dict[str, Any]] = []
    for item in (parsed.get("panels") or [])[:8]:
        if not isinstance(item, dict):
            continue
        dialogue: List[Dict[str, str]] = []
        for line in (item.get("dialogue") or [])[:3]:
            if isinstance(line, dict):
                spk = _clean_line(line.get("speaker") or line.get("name"), 40)
                txt = _clean_line(line.get("text") or line.get("line"), 240)
                if txt:
                    dialogue.append({"speaker": spk or "—", "text": txt})
            elif isinstance(line, str) and line.strip():
                dialogue.append({"speaker": "—", "text": _clean_line(line, 240)})
        scene = _clean_line(item.get("scene") or item.get("visual") or item.get("description"), 320)
        caption = _clean_line(item.get("caption") or item.get("narration"), 240)
        if not (scene or caption or dialogue):
            continue
        panels.append({
            "scene": scene,
            "caption": caption,
            "dialogue": dialogue,
            "sfx": _clean_line(item.get("sfx") or item.get("sound"), 24),
        })

    if not panels:
        beats = _split_points(source, limit=6)
        labels = ["Mở đầu", "Dẫn dắt", "Xung đột", "Cao trào", "Bước ngoặt", "Kết"]
        panels = [
            {"scene": beat, "caption": labels[i] if i < len(labels) else "", "dialogue": [], "sfx": ""}
            for i, beat in enumerate(beats or ["No content yet — add a source."])
        ]

    return {"title": title, "logline": logline, "panels": panels}


async def _build_book_payload(source_text: str) -> Dict[str, Any]:
    """Turn any source into a real short-book structure: cover blurb plus chapters
    that contain actual readable prose, not just an outline."""
    source = _normalize_text(source_text)
    if not source:
        return {"title": "Book", "subtitle": "", "blurb": "", "chapters": []}

    prompt = (
        "You are a non-fiction author. Turn the SOURCE into a concise, engaging short book "
        "with 5 chapters. Each chapter must contain REAL prose (2 to 3 full paragraphs that a "
        "reader could read end to end), not bullet points. Write in the SAME language as the "
        "source. Keep it accurate to the source; do not invent facts.\n"
        "Return valid JSON only, no markdown, with this exact schema:\n"
        '{"title":"...","subtitle":"...","blurb":"back-cover paragraph",'
        '"chapters":[{"title":"...","summary":"one line","body":"2-3 paragraphs of prose"}]}\n\n'
        f"SOURCE:\n{source[:7000]}"
    )
    raw = await _generate_text(prompt, num_predict=1800)
    parsed = _extract_json_block(raw)

    title = _clean_line(parsed.get("title"), 140) or "Book"
    subtitle = _clean_line(parsed.get("subtitle"), 200)
    blurb = _clean_line(parsed.get("blurb"), 600)
    chapters: List[Dict[str, Any]] = []
    for item in (parsed.get("chapters") or [])[:10]:
        if not isinstance(item, dict):
            continue
        ch_title = _clean_line(item.get("title"), 160)
        body = item.get("body") or item.get("content") or item.get("text") or ""
        if isinstance(body, list):
            body = "\n\n".join(_clean_line(p, 1200) for p in body if p)
        else:
            body = _normalize_text(body).strip()
        paragraphs = [p.strip() for p in re.split(r"\n{2,}|\r\n\r\n", body) if p.strip()]
        if not paragraphs and body:
            paragraphs = [body]
        if not (ch_title or paragraphs):
            continue
        chapters.append({
            "title": ch_title or f"Chapter {len(chapters) + 1}",
            "summary": _clean_line(item.get("summary"), 240),
            "paragraphs": [p[:1600] for p in paragraphs][:6],
        })

    if not chapters:
        points = _split_points(source, limit=5)
        chapters = [
            {"title": f"Chương {i + 1}", "summary": "", "paragraphs": [pt]}
            for i, pt in enumerate(points or ["No content yet — add a source."])
        ]

    return {"title": title, "subtitle": subtitle, "blurb": blurb, "chapters": chapters}


async def _answer_question(
    question: str,
    session_id: str,
    age_group: str = "middle",
    source_context: str = "",
    force_search: bool = False,
    deep_research: bool = False,
    strict_source: bool = False,
) -> str:
    if not source_context and not force_search and not deep_research:
        cached = global_cache.get(question, f"ai_answer_{age_group}")
        if cached and isinstance(cached, dict) and "answer" in cached:
            return cached["answer"]

    _cleanup_sessions()

    if session_id not in chat_sessions:
        chat_sessions[session_id] = {"messages": [], "updated_at": _now()}

    session = chat_sessions[session_id]
    if "messages" not in session or not isinstance(session["messages"], list):
        session["messages"] = []

    session["messages"].append({"role": "user", "content": question})
    session["updated_at"] = _now()

    tone = {
        "young": "Use simple, clear language for a student.",
        "senior": "Use calm, explicit language with short sentences.",
        "middle": "Use direct, professional language.",
    }.get(age_group, "Use direct, professional language.")

    source_block = ""
    if source_context:
        if strict_source:
            source_block = (
                "Only answer from the provided source. "
                "If the answer is not present in the source, say clearly that more source material is needed.\n\n"
                f"Source:\n{source_context[:12000]}"
            )
        else:
            source_block = f"Primary source context:\n{source_context[:24000]}"

    search_block = ""
    search_text = ""
    if force_search or deep_research:
        search_result = await _smart_search(question, deep_research=deep_research)
        search_text = _search_result_to_text(search_result)
        if search_text:
            search_block = f"\n\nSearch context:\n{search_text[:12000]}"

    history = session["messages"][-8:-1]
    history_block = "\n".join(
        f"{item['role'].upper()}: {item['content']}"
        for item in history
        if item.get("content")
    )

    grounding_required = bool(source_context or search_text or strict_source or force_search or deep_research)
    answer_rule = (
        "Answer only from the provided source/search context. "
        "Do not add facts from general knowledge. "
        "If the context does not verify the latest answer, say clearly that updated verified information is not available yet. "
        "When the user does not ask for history, ignore older details and keep only the latest verified information."
        if grounding_required
        else "Answer the user's question directly and concisely."
    )

    prompt = (
        "You are Skemi AI.\n"
        f"{tone}\n\n"
        f"{source_block}{search_block}\n\n"
        f"Recent conversation:\n{history_block or '(no prior context)'}\n\n"
        f"User question:\n{question}\n\n"
        f"{answer_rule} "
        "CRITICAL: Do NOT use markdown bolding (double asterisks like **text**). "
        "NEVER use **. Use plain text only for emphasis."
    )

    if "system_prompt" in session and session["system_prompt"]:
        prompt = f"{session['system_prompt']}\n\n{prompt}"

    answer = await _generate_text(prompt, model=getattr(backend, "MODEL_MAIN", None), num_predict=1400)
    answer = _normalize_text(answer) or "No response generated."
    answer = answer.replace("**", "")
    session["messages"].append({"role": "assistant", "content": answer})
    session["updated_at"] = _now()

    if not source_context and not force_search and not deep_research:
        global_cache.set(question, {"answer": answer}, f"ai_answer_{age_group}")

    return answer

@app.on_event("startup")
async def _log_frontend_links() -> None:
    print("\n======================================================")
    print("SKEMI FRONTEND")
    print("======================================================")
    print(f"Frontend: {SERVER_BASE_URL}/")
    print(f"Studio:   {SERVER_BASE_URL}/Home.html")
    print(f"Search:   {SERVER_BASE_URL}/Search.html")
    print(f"Settings: {SERVER_BASE_URL}/Settings.html")
    print(f"Chat:     {SERVER_BASE_URL}/Chat.html")
    print("======================================================\n")
    try:
        conn = sqlite3.connect(AUTH_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(user_id, namespace, key)
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_data_lookup ON user_data(user_id, namespace);
        """)
        conn.commit()
        conn.close()
        print("User data SQLite table: initialized")
    except Exception as exc:
        print(f"User data DB startup warning: {exc}")
    try:
        agent_session_store.cleanup_expired()
        print("Virtual Browser backend: Skemi surface v2")
    except Exception as exc:
        print(f"Startup warning: {exc}")
    try:
        ready = await skemi_local_computer_backend.warm_start()
        print(f"Local Computer backend: {'ready' if ready else 'warm-start failed'}")
    except Exception as exc:
        print(f"Local Computer startup warning: {exc}")


app.state.skemi_extra_startup = _log_frontend_links


# Top 20 most-spoken languages by user base — pre-translated on startup so
# users see instant UI when they switch. The remainder of LANGUAGE_CODES is
# translated on demand and cached.
PRETRANSLATE_TOP_LANGS = [
    "en", "zh", "ja", "ko", "fr", "es", "de", "ru", "ar", "hi",
    "pt", "it", "tr", "nl", "pl", "id", "th", "uk", "ro", "sv",
]


async def _pretranslate_worker_run() -> None:
    """Translate the master UI string set into PRETRANSLATE_TOP_LANGS in the
    background so the first user who picks a popular language gets instant
    rendering instead of waiting for the LLM. Cache hits are skipped — each
    (text, target_lang) pair is requested at most once across runs."""
    await asyncio.sleep(15)  # Let backend/Ollama warm up
    try:
        # Collect every UI string from the i18n JSON pack on disk.
        packs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Js", "i18n-packs.js")
        if not os.path.isfile(packs_path):
            return
        with open(packs_path, "r", encoding="utf-8") as fh:
            raw_pack = fh.read()
        # Crude string harvest — pick anything in double-quoted English-looking
        # strings from the en pack section. Misses are fine; the on-demand
        # endpoint will fill gaps live.
        candidate_strings = set()
        for match in re.finditer(r'"([^"\\\\]{3,120})"', raw_pack):
            value = match.group(1).strip()
            if 3 <= len(value) <= 120 and any(c.isalpha() for c in value):
                candidate_strings.add(value)
        master_strings = sorted(candidate_strings)[:300]
        if not master_strings:
            return
        print(f"[pretranslate] Starting background pre-translate for {len(PRETRANSLATE_TOP_LANGS)} langs × {len(master_strings)} strings")
        for target in PRETRANSLATE_TOP_LANGS:
            if target == "en":
                continue  # Identity, no need to call LLM
            cached = global_cache.get_ui_translations(master_strings, "en", target)
            missing = [s for s in master_strings if s not in cached]
            if not missing:
                continue
            try:
                await _translate_ui_texts_with_model(missing, source="en", target=target)
                print(f"[pretranslate] {target}: cached {len(missing)} new strings")
            except Exception as exc:
                print(f"[pretranslate] {target}: ERROR {exc}")
            # Yield to other tasks between languages
            await asyncio.sleep(0.5)
        print("[pretranslate] Done")
    except Exception as exc:
        print(f"[pretranslate] Worker failed: {exc}")


@app.on_event("startup")
async def _start_pretranslate_worker() -> None:
    asyncio.create_task(_pretranslate_worker_run())


@app.on_event("shutdown")
async def _shutdown_browser_worker() -> None:
    return None


@app.get("/PromptAgent.html")
async def prompt_agent_direct():
    return serve_html_page("PromptAgent.html")


@app.get("/Computer.html")
async def computer_direct():
    return serve_html_page("Computer.html")


@app.get("/")

async def root_page():
    return serve_html_page("Home.html")


@app.get("/Home.html")
async def home_page():
    return serve_html_page("Home.html")


@app.get("/Search.html")
async def search_page():
    return serve_html_page("Search.html")


@app.get("/Quiz.html")
async def quiz_page():
    return serve_html_page("Quiz.html")


@app.get("/Settings.html")
async def settings_page():
    return serve_html_page("Settings.html")


# Duplicate routes removed.


@app.get("/Login.html")
async def login_page():
    return serve_html_page("Login.html")


@app.get("/Register.html")
async def register_page():
    return serve_html_page("Register.html")


@app.get("/Chart.html")
async def chart_page():
    return serve_html_page("Chart.html")


@app.get("/Chat.html")
async def chat_page():
    return serve_skemma_chat_page()


@app.get("/api/health")
async def api_health():
    return await backend.health()


@app.post("/api/ask_stream")
async def api_ask_stream(request: Request, req: backend.ChatRequest):
    return await backend.ask_stream(request, req)


@app.post("/api/clear_memory")
async def api_clear_memory(user_id: str):
    return await backend.clear_memory(user_id)


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    uploads_dir = FRONTEND_ROOT / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    import uuid
    file_ext = Path(file.filename or "").suffix
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = uploads_dir / unique_filename
    
    content = await file.read()
    file_path.write_bytes(content)
    
    return {
        "url": f"/uploads/{unique_filename}",
        "file_name": file.filename,
        "size": len(content)
    }


import fastapi

@app.post("/api/parse_file_stream")
async def api_parse_file_stream(
    file: UploadFile = File(...),
    analysis_mode: str = fastapi.Form("assistant"),
):
    return await backend.parse_file_stream(file, analysis_mode)


@app.post("/api/parse_file")
async def api_parse_file(
    file: UploadFile = File(...),
    analysis_mode: str = fastapi.Form("assistant"),
):
    return await backend.parse_file(file, analysis_mode)


def _cleanup_ai_chat_jobs() -> None:
    now = time.time()
    expired = [
        job_id
        for job_id, job in ai_chat_jobs.items()
        if now - float(job.get("updated_at", job.get("created_at", now)) or now) > AI_CHAT_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        ai_chat_jobs.pop(job_id, None)


async def _run_ai_chat_job(job_id: str, req: AIChatJobRequest) -> None:
    job = ai_chat_jobs.get(job_id)
    if not job:
        return
    job.update({"status": "running", "stage": "thinking", "detail": "Skemi AI is preparing a response.", "updated_at": time.time()})
    try:
        answer = await _answer_question(
            req.question,
            req.session_id,
            req.age_group,
            force_search=req.force_search,
            deep_research=req.deep_research,
        )
        job.update({
            "status": "completed",
            "stage": "completed",
            "detail": "Response ready.",
            "answer": answer,
            "session_id": req.session_id,
            "updated_at": time.time(),
            "completed_at": time.time(),
        })
    except Exception as exc:
        job.update({
            "status": "failed",
            "stage": "failed",
            "detail": str(exc) or "Skemi AI job failed.",
            "error": str(exc) or "Skemi AI job failed.",
            "updated_at": time.time(),
            "completed_at": time.time(),
        })


@app.post("/api/aichat/jobs")
async def api_aichat_job_create(req: AIChatJobRequest):
    question = str(req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")
    _cleanup_ai_chat_jobs()
    job_id = f"aichat_{int(time.time() * 1000)}_{hashlib.sha1(question.encode('utf-8', 'ignore')).hexdigest()[:8]}"
    ai_chat_jobs[job_id] = {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "stage": "routing",
        "detail": "Skemi AI is deciding the best route.",
        "question": question,
        "session_id": req.session_id,
        "age_group": req.age_group,
        "created_at": time.time(),
        "updated_at": time.time(),
        "answer": "",
    }
    asyncio.create_task(_run_ai_chat_job(job_id, req))
    return {"success": True, "job_id": job_id, "status": "queued", "stage": "routing"}


@app.get("/api/aichat/jobs/{job_id}")
async def api_aichat_job_status(job_id: str):
    _cleanup_ai_chat_jobs()
    job = ai_chat_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="AI chat job not found")
    return dict(job)


@app.delete("/api/aichat/jobs/{job_id}")
async def api_aichat_job_delete(job_id: str):
    removed = ai_chat_jobs.pop(job_id, None)
    return {"success": True, "deleted": bool(removed)}


# --- Studio background jobs -------------------------------------------------
# Studio generation (comic / book / diagram / mindmap-from-text) used to be a
# blocking request, so navigating away mid-generation killed the work and the UI
# reset. These endpoints run the SAME generation logic as a background task so the
# Studio page can leave + come back and resume the live status (like Search/Chat).
# The original /generate_* routes are kept untouched as a fallback.

class StudioJobRequest(BaseModel):
    kind: str = "studio"          # 'studio' | 'diagram' | 'mindmap_text'
    text: str = ""                # mindmap_text source
    analysis: str = ""            # studio / diagram source
    format: str = "comic"         # studio: comic | book
    type: str = "mindmap"         # diagram: mindmap | flowchart | chart | timeline
    search_mode: bool = False
    label: str = ""               # short human label for notifications


def _cleanup_studio_jobs() -> None:
    now = time.time()
    expired = [
        job_id
        for job_id, job in studio_jobs.items()
        if now - float(job.get("updated_at", job.get("created_at", now)) or now) > STUDIO_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        studio_jobs.pop(job_id, None)


async def _run_studio_job(job_id: str, req: StudioJobRequest) -> None:
    job = studio_jobs.get(job_id)
    if not job:
        return
    job.update({"status": "running", "stage": "generating", "detail": "Skemi is generating your content.", "updated_at": time.time()})
    try:
        kind = (req.kind or "studio").strip().lower()
        if kind == "mindmap_text":
            data = await _build_mindmap_payload(req.text or req.analysis, "Mindmap")
        elif kind == "diagram":
            data = await generate_diagram(DiagramRequest(analysis=req.analysis, type=req.type, search_mode=req.search_mode))
        else:
            data = await generate_studio(StudioRequest(analysis=req.analysis, format=req.format, search_mode=req.search_mode))
        job.update({
            "status": "completed",
            "stage": "completed",
            "detail": "Content ready.",
            "result": data,
            "updated_at": time.time(),
            "completed_at": time.time(),
        })
    except asyncio.CancelledError:
        # User closed the tab — stop spending compute on it, but leave the
        # job record (whatever stage it reached) instead of erasing it, so
        # it still shows up in /studio/jobs as "cancelled" rather than
        # silently vanishing or being mistaken for a crash.
        job.update({"status": "cancelled", "stage": "cancelled", "detail": "Stopped — tab was closed.", "updated_at": time.time()})
        raise
    except Exception as exc:
        job.update({
            "status": "failed",
            "stage": "failed",
            "detail": str(exc) or "Studio job failed.",
            "error": str(exc) or "Studio job failed.",
            "updated_at": time.time(),
            "completed_at": time.time(),
        })
    finally:
        _cancellable_job_tasks.pop(job_id, None)


@app.post("/studio/jobs")
async def api_studio_job_create(request: Request, req: StudioJobRequest):
    _cleanup_studio_jobs()
    seed = (req.text or req.analysis or "").strip()
    if not seed:
        raise HTTPException(status_code=400, detail="No content to generate")
    job_id = f"studio_{int(time.time() * 1000)}_{hashlib.sha1(seed.encode('utf-8', 'ignore')).hexdigest()[:8]}"
    # Tied to the account (when signed in) so /studio/jobs?mine=1 can find it
    # again even if the tab/browser was fully closed and the sessionStorage
    # pointer to this job_id is gone — the job itself keeps running server-side
    # via create_task() below regardless of whether the client is even connected.
    studio_jobs[job_id] = {
        "success": True,
        "job_id": job_id,
        "user_id": _resolve_account_id(request),
        "status": "queued",
        "stage": "queued",
        "detail": "Skemi queued your Studio request.",
        "kind": req.kind,
        "label": req.label or seed[:80],
        "created_at": time.time(),
        "updated_at": time.time(),
        "result": None,
    }
    _cancellable_job_tasks[job_id] = asyncio.create_task(_run_studio_job(job_id, req))
    return {"success": True, "job_id": job_id, "status": "queued", "stage": "queued"}


@app.get("/studio/jobs/{job_id}")
async def api_studio_job_status(job_id: str):
    _cleanup_studio_jobs()
    job = studio_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Studio job not found")
    return dict(job)


@app.get("/studio/jobs")
async def api_studio_job_list(request: Request):
    """List this account's Studio jobs — the recovery path when the client's
    sessionStorage job_id pointer is gone (browser fully closed, not just
    reloaded) but the job itself finished or is still running server-side."""
    _cleanup_studio_jobs()
    uid = _resolve_account_id(request)
    if not uid or uid == "guest":
        return {"success": True, "jobs": []}
    mine = sorted(
        (dict(j) for j in studio_jobs.values() if j.get("user_id") == uid),
        key=lambda j: j.get("created_at", 0),
        reverse=True,
    )
    return {"success": True, "jobs": mine[:20]}


@app.delete("/studio/jobs/{job_id}")
async def api_studio_job_delete(job_id: str):
    removed = studio_jobs.pop(job_id, None)
    return {"success": True, "deleted": bool(removed)}


@app.get("/api/memory-stream/recent")
async def api_memory_stream_recent(user_id: str = "default_user", limit: int = 12, areas: str = ""):
    area_list = [item.strip() for item in str(areas or "").split(",") if item.strip()]
    return {
        "success": True,
        "items": shared_memory_hub.get_recent(user_id=user_id, areas=area_list, limit=limit),
    }


@app.get("/api/memory-stream/context")
async def api_memory_stream_context(user_id: str = "default_user", limit: int = 8, max_chars: int = 2200, areas: str = ""):
    area_list = [item.strip() for item in str(areas or "").split(",") if item.strip()]
    context_text = shared_memory_hub.build_context_window(
        user_id=user_id,
        limit=limit,
        max_chars=max_chars,
        areas=area_list,
    )
    return {"success": True, "context": context_text}


@app.post("/api/memory-stream/append")
async def api_memory_stream_append(payload: MemoryEventRequest):
    item = shared_memory_hub.append_event(
        user_id=payload.user_id,
        area=payload.area,
        title=payload.title,
        summary=payload.summary,
        metadata=dict(payload.metadata or {}),
        tags=list(payload.tags or []),
    )
    if not item:
        return JSONResponse({"success": False, "error": "Missing memory payload"}, status_code=400)
    return {"success": True, "item": item}


@app.post("/api/memory-stream/clear")
async def api_memory_stream_clear(user_id: str = "default_user"):
    deleted = shared_memory_hub.clear(user_id=user_id)
    return {"success": True, "deleted": deleted}


@app.post("/api/translate-ui")
async def api_translate_ui(payload: TranslateUIRequest):
    text = str(payload.q or "")
    source = str(payload.source or "en").strip().lower()
    target = str(payload.target or "en").strip().lower()
    if not text:
        return JSONResponse({"error": "Missing text", "translatedText": ""}, status_code=400)
    if source == target:
        return {"translatedText": text}
    translations = await _translate_ui_texts_with_model([text], source, target)
    translated = translations[0] if translations else text
    return {"translatedText": translated or text}


@app.post("/api/translate-ui-batch")
async def api_translate_ui_batch(payload: TranslateUIBatchRequest):
    texts = [str(item or "").strip() for item in (payload.texts or [])]
    texts = [item for item in texts if item]
    source = str(payload.source or "auto").strip().lower()
    target = str(payload.target or "en").strip().lower()

    if not texts:
        return {"translations": []}
    if source == target:
        return {"translations": texts}

    translations = await _translate_ui_texts_with_model(texts, source, target)
    if translations and len(translations) == len(texts):
        return {"translations": translations}
    return {"translations": texts, "passthrough": True}


@app.get("/{filename}.html")
async def serve_arbitrary_html(filename: str):
    return serve_html_page(f"{filename}.html")


@app.api_route("/skemma/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

async def proxy_skemma(request: Request, path: str):
    normalized_path = str(path or "").strip().lower()
    if normalized_path == "chat.html":
        return RedirectResponse(url="/Chat.html", status_code=307)
    raise HTTPException(status_code=404, detail="Legacy routes are no longer available in Skemi.")


@app.post("/ask")
async def ask_ai(payload: AskRequest):
    answer = await _answer_question(payload.question, payload.session_id, payload.age_group)
    return JSONResponse({"model": getattr(backend, "MODEL_MAIN", "model"), "answer": answer})


@app.post("/ask_multi")
async def ask_ai_multi(payload: AskRequest):
    answer = await _answer_question(
        payload.question,
        payload.session_id,
        payload.age_group,
        force_search=payload.force_search,
        deep_research=payload.deep_research,
    )
    return JSONResponse(
        {
            "model": getattr(backend, "MODEL_MAIN", "model"),
            "answer": answer,
            "session_id": payload.session_id,
            "age_group": payload.age_group,
        }
    )


@app.post("/end_session")
async def end_session(data: Dict[str, Any]):
    session_id = str(data.get("session_id", "")).strip()
    user_id = str(data.get("user_id", "default_user")).strip() or "default_user"
    clear_runtime = bool(data.get("clear_runtime", True))
    if clear_runtime:
        deleted = await _cleanup_skemi_runtime_data(user_id=user_id, session_id=session_id)
        return {
            "message": "Session cleared",
            "deleted": deleted,
            "preserved": {
                "studio_projects": "skemi_studio_projects_v1",
                "settings": ["skemi-theme", "skemi_language", "skemi_user_data"],
            },
        }

    if session_id:
        chat_sessions.pop(session_id, None)
        if hasattr(backend, "delete_session"):
            try:
                backend.delete_session(session_id)
            except Exception as exc:
                print(f"END SESSION BACKEND CLEANUP ERROR: {exc}")
    return {"message": "Session cleared"}


@app.post("/generate_mindmap_from_text")
async def generate_mindmap_from_text(data: MindmapTextRequest):
    return JSONResponse(await _build_mindmap_payload(data.text, "Mindmap"))


@app.post("/generate_mindmap")
async def generate_mindmap(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    content_type = str(file.content_type or "")
    if content_type.startswith("image/"):
        source = await backend.analyze_image_with_vision_model(raw, output_language="en", analysis_mode="assistant")
    else:
        extracted, _detected_type = backend.extract_text_by_extension(file.filename or "", raw)
        source = extracted or raw.decode("utf-8", errors="ignore")

    return JSONResponse(await _build_mindmap_payload(source, file.filename or "Mindmap"))


@app.post("/analyze_file")
async def analyze_file(payload: AnalyzeFileRequest):
    file_data = payload.file_data or {}
    file_name = _normalize_text(file_data.get("name") or "uploaded_file")
    file_type = _normalize_text(file_data.get("type"))
    raw_content = file_data.get("content", "")

    if file_type.startswith("image/"):
        image_bytes = _decode_data_url(str(raw_content))
        analysis = await backend.analyze_image_with_vision_model(image_bytes, output_language="en", analysis_mode="assistant")
    else:
        analysis = _normalize_text(file_data.get("analysis") or raw_content)

    analysis = analysis or "No analyzable content was found."
    outline_payload = await _build_mindmap_payload(analysis, file_name)

    return {
        "success": True,
        "file_name": file_name,
        "diagram_type": payload.diagram_type,
        "analysis": analysis,
        "analysis_source": analysis[:12000],
        "topics": [node.get("text", "") for node in outline_payload["mindmap_nodes"][:8]],
        "outline": outline_payload["mindmap_nodes"],
        "suggested_diagrams": ["mindmap", "flowchart", "chart", "timeline"],
    }


@app.post("/generate_diagram")
async def generate_diagram(payload: DiagramRequest):
    source = _normalize_text(payload.analysis)
    if payload.search_mode:
        search_result = await _smart_search(source, deep_research=True)
        search_text = _search_result_to_text(search_result)
        if search_text:
            source = f"{source}\n\nSearch context:\n{search_text[:12000]}"

    diagram_type = payload.type or "mindmap"
    if diagram_type in {"mindmap", "flowchart"}:
        mindmap = await _build_mindmap_payload(source, "Diagram")
        return {"success": True, "diagram": {"type": "mermaid", "topic": mindmap["topic"], "nodes": mindmap["mindmap_nodes"], "mermaid": mindmap["mermaid"]}, "sources": []}
    if diagram_type == "chart":
        return {"success": True, "diagram": await _build_chart_payload(source), "sources": []}
    if diagram_type == "timeline":
        return {"success": True, "diagram": await _build_timeline_payload(source), "sources": []}

    return {"success": False, "error": f"Unsupported diagram type: {diagram_type}"}


class StudioRequest(BaseModel):
    analysis: str
    format: str = "comic"
    search_mode: bool = False


@app.post("/generate_studio")
async def generate_studio(payload: StudioRequest):
    """Rich Studio conversions that need real authored content (comic script,
    short book) rather than a reshaped mindmap."""
    source = _normalize_text(payload.analysis)
    if payload.search_mode and source:
        search_result = await _smart_search(source, deep_research=True)
        search_text = _search_result_to_text(search_result)
        if search_text:
            source = f"{source}\n\nSearch context:\n{search_text[:12000]}"

    fmt = (payload.format or "comic").strip().lower()
    try:
        if fmt == "comic":
            return {"success": True, "format": "comic", "data": await _build_comic_payload(source)}
        if fmt == "book":
            return {"success": True, "format": "book", "data": await _build_book_payload(source)}
    except Exception as exc:
        print(f"GENERATE STUDIO ERROR ({fmt}): {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    return {"success": False, "error": f"Unsupported studio format: {fmt}"}


def _source_domain(url: str) -> str:
    try:
        return urlparse(str(url or "")).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _compact_search_sources(sources: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in _deduplicate_sources(sources)[:limit]:
        url = _normalize_text(item.get("url"))
        domain = _source_domain(url)
        rows.append(
            {
                "title": _normalize_text(item.get("title") or domain or "Search result"),
                "url": url,
                "snippet": _normalize_text(item.get("snippet") or item.get("content")),
                "published_at": _normalize_text(item.get("published_at")),
                "source": _normalize_text(item.get("source") or domain),
                "domain": domain,
                "is_official_source": bool(item.get("is_official_source")),
                "source_trust_tier": _normalize_text(item.get("source_trust_tier")),
                "favicon_url": f"https://icons.duckduckgo.com/ip3/{domain}.ico" if domain else "",
                "open_in_new_tab": True,
            }
        )
    return rows


def _analysis_keywords(query: str, sources: List[Dict[str, Any]]) -> List[str]:
    candidates = []
    base = [token for token in re.split(r"[^0-9A-Za-zÀ-ỹ._+-]+", query) if len(token) >= 3]
    candidates.extend(base)
    for source in sources[:8]:
        candidates.extend([token for token in re.split(r"[^0-9A-Za-zÀ-ỹ._+-]+", _normalize_text(source.get("title"))) if len(token) >= 4])
    deduped: List[str] = []
    for token in candidates:
        clean = _normalize_text(token)
        if clean and clean.lower() not in {item.lower() for item in deduped}:
            deduped.append(clean)
        if len(deduped) >= 10:
            break
    return deduped


def _clean_search_ui_text(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"[#*_`~>]+", " ", text)
    text = text.replace("|", " ")
    text = re.sub(r"(?:\s*-\s*){3,}", ". ", text)
    text = re.sub(r"\s*-\s*-\s*", " - ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" \n\r\t-")


def _search_text_structure_penalty(value: Any) -> int:
    text = _clean_search_ui_text(value)
    if not text:
        return 10

    penalty = 0
    dash_segments = [item for item in re.split(r"\s*-\s*", text) if item.strip()]
    pipe_segments = [item for item in re.split(r"\s*\|\s*", text) if item.strip()]
    slash_segments = [item for item in re.split(r"\s*/\s*", text) if item.strip()]
    colon_count = text.count(":")

    if len(dash_segments) >= 6:
        penalty += 4
    elif len(dash_segments) >= 4:
        penalty += 2

    if len(pipe_segments) >= 5:
        penalty += 3

    if len(slash_segments) >= 5:
        penalty += 2

    if colon_count >= 4:
        penalty += 2

    if len(text) > 110 and text[:80].count("-") >= 3:
        penalty += 2

    return penalty


def _trim_list_texts(values: List[Any], limit: int = 4) -> List[str]:
    rows: List[str] = []
    for value in values or []:
        cleaned = _clean_search_ui_text(value)
        if cleaned and cleaned.lower() not in {item.lower() for item in rows}:
            rows.append(cleaned)
        if len(rows) >= limit:
            break
    return rows


def _brief_sentences(text: str, limit: int = 2) -> List[str]:
    cleaned = _clean_search_ui_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    rows: List[str] = []
    for part in parts:
        item = _clean_search_ui_text(part)
        if item:
            rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def _source_title_samples(sources: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    rows: List[str] = []
    for source in sources or []:
        title = _clean_search_ui_text(source.get("title") or source.get("source") or source.get("domain"))
        if title and title.lower() not in {item.lower() for item in rows}:
            rows.append(title)
        if len(rows) >= limit:
            break
    return rows


def _search_snippet_samples(sources: List[Dict[str, Any]], limit: int = 3, max_chars: int = 220) -> List[str]:
    rows: List[str] = []
    seen: List[str] = []
    for source in sources or []:
        snippet = _clean_search_ui_text(source.get("snippet") or source.get("content"))
        if not snippet:
            continue
        if _search_text_structure_penalty(snippet) >= 4:
            continue
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rsplit(" ", 1)[0].strip() + "..."
        key = snippet.lower()
        if not snippet or key in seen:
            continue
        seen.append(key)
        rows.append(snippet)
        if len(rows) >= limit:
            break
    return rows


def _search_source_is_officialish(source: Dict[str, Any]) -> bool:
    tier = _normalize_text(source.get("source_trust_tier")).strip().lower()
    return bool(source.get("is_official_source")) or tier in {"official", "official_family", "docs"}


def _search_source_is_high_trust(source: Dict[str, Any]) -> bool:
    tier = _normalize_text(source.get("source_trust_tier")).strip().lower()
    return _search_source_is_officialish(source) or tier in {"major_press", "press"}


def _search_source_matches_subject(source: Dict[str, Any], subject: str) -> bool:
    subject_text = _normalize_text(subject).lower()
    if not subject_text:
        return False
    blob = " ".join(
        [
            _normalize_text(source.get("title")),
            _normalize_text(source.get("snippet") or source.get("content")),
            _normalize_text(source.get("url")),
        ]
    ).lower()
    return subject_text in blob


def _subject_aliases(subject: str) -> List[str]:
    base = _normalize_text(subject).lower()
    aliases: List[str] = [base] if base else []
    if base == "chatgpt":
        aliases.extend(["gpt", "openai"])
    elif base == "claude":
        aliases.extend(["anthropic"])
    elif base == "gemini":
        aliases.extend(["google"])
    elif base == "qwen":
        aliases.extend(["alibaba"])
    elif base == "minimax":
        aliases.extend(["mini max"])
    deduped: List[str] = []
    for item in aliases:
        cleaned = _normalize_text(item).lower()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _extract_latest_model_candidates(subject: str, sources: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    version_token = r"(?:o\d(?:-[a-z0-9]+)?|\d+(?:\.\d+)+(?:-[a-z0-9]+)?)"
    candidates: List[str] = []
    seen: Set[str] = set()
    for alias in _subject_aliases(subject):
        escaped_alias = re.escape(alias)
        patterns = [
            re.compile(rf"\b{escaped_alias}(?:\s+[A-Za-z][A-Za-z0-9.+-]*){{0,2}}\s+{version_token}\b", re.IGNORECASE),
            re.compile(rf"\b{escaped_alias}-{version_token}\b", re.IGNORECASE),
        ]
        for source in sources or []:
            text_parts = [
                _normalize_text(source.get("title")),
                _normalize_text(source.get("snippet") or source.get("content")),
            ]
            for text in text_parts:
                if not text:
                    continue
                for pattern in patterns:
                    for match in pattern.finditer(text):
                        value = _clean_search_ui_text(match.group(0))
                        normalized_value = value.lower()
                        if not value or normalized_value in seen:
                            continue
                        seen.add(normalized_value)
                        candidates.append(value)
                        if len(candidates) >= limit:
                            return candidates
    return candidates


def _latest_model_official_seed_urls(subject: str) -> List[str]:
    normalized = _normalize_text(subject).lower()
    seed_urls: List[str] = []
    if any(token in normalized for token in ("chatgpt", "openai", "gpt")):
        seed_urls.extend([
            "https://help.openai.com/en/articles/9624314-model-release-notes",
            "https://help.openai.com/en/articles/6825453-chatgpt-release-notes",
            "https://platform.openai.com/docs/changelog",
        ])
    if any(token in normalized for token in ("claude", "anthropic")):
        seed_urls.extend([
            "https://www.anthropic.com/news/claude-opus-4-6",
            "https://docs.anthropic.com/en/docs/about-claude/models/all-models",
            "https://docs.anthropic.com/en/release-notes/overview",
        ])
    if any(token in normalized for token in ("gemini", "google")):
        seed_urls.extend([
            "https://deepmind.google/models/gemini/",
            "https://ai.google.dev/gemini-api/docs/models",
            "https://blog.google/technology/google-deepmind/",
        ])
    if any(token in normalized for token in ("minimax",)):
        seed_urls.extend([
            "https://www.minimax.io/news",
            "https://www.minimax.io/",
        ])
    return list(dict.fromkeys(seed_urls))


async def _fetch_latest_model_seed_sources(subjects: List[str]) -> List[Dict[str, Any]]:
    urls: List[str] = []
    for subject in subjects or []:
        urls.extend(_latest_model_official_seed_urls(subject))
    urls = list(dict.fromkeys(urls))[:10]
    if not urls:
        return []

    async def _fetch_one(client: httpx.AsyncClient, url: str) -> Optional[Dict[str, Any]]:
        try:
            response = await client.get(url, timeout=8.0, follow_redirects=True)
            if response.status_code != 200:
                return None
            html = response.text or ""
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = _clean_search_ui_text(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else url
            published = None
            published_patterns = [
                r"article:published_time[^>]*content=[\"']([^\"']+)",
                r"name=[\"']publish_date[\"'][^>]*content=[\"']([^\"']+)",
                r"name=[\"']date[\"'][^>]*content=[\"']([^\"']+)",
                r"<time[^>]*datetime=[\"']([^\"']+)",
            ]
            for pattern in published_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    published = _parse_published_at(match.group(1))
                    if published:
                        break
            text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
            text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = _clean_search_ui_text(text)
            snippet = text[:1600]
            return {
                "title": title or url,
                "url": str(response.url),
                "snippet": snippet[:420],
                "content": snippet,
                "published_at": published or "",
                "is_official_source": True,
                "source_trust_tier": "official_seed",
                "source_rejection_reason": "",
            }
        except Exception:
            return None

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        results = await asyncio.gather(*[_fetch_one(client, url) for url in urls])
    return [item for item in results if item and _normalize_text(item.get("content") or item.get("snippet"))]


def _latest_model_subject_bundle(subject: str, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    relevant = [source for source in sources if _search_source_matches_subject(source, subject)] or list(sources)
    official = [source for source in relevant if _search_source_is_officialish(source)]
    high_trust = [source for source in relevant if _search_source_is_high_trust(source)]
    official_candidates = _extract_latest_model_candidates(subject, official, limit=3) if official else []
    candidate_pool = official if official_candidates else (high_trust or relevant)
    candidates = official_candidates or _extract_latest_model_candidates(subject, candidate_pool, limit=3)
    working = official or high_trust or relevant
    titles = _source_title_samples(working, limit=3)
    latest_date = _clean_search_ui_text(
        next((item.get("published_at") for item in working if item.get("published_at")), "")
    )
    return {
        "subject": subject,
        "relevant": relevant,
        "official": official,
        "high_trust": high_trust,
        "titles": titles,
        "latest_date": latest_date,
        "candidates": candidates,
    }


def _latest_model_focus_sources(subject: str, sources: List[Dict[str, Any]], candidates: List[str]) -> List[Dict[str, Any]]:
    aliases = _subject_aliases(subject)
    release_markers = [
        "latest",
        "newest",
        "current",
        "update",
        "updated",
        "release",
        "released",
        "announcement",
        "announced",
        "model",
        "version",
        "cap nhat",
        "cập nhật",
        "moi nhat",
        "mới nhất",
        "ra mat",
        "ra mắt",
        "phien ban",
        "phiên bản",
    ]
    low_signal_markers = [
        "table of contents",
        "introduction",
        "mục lục",
        "giới thiệu",
        "noi dung chinh",
        "nội dung chính",
        "mau prompt",
        "mẫu prompt",
        "cau lenh",
        "câu lệnh",
        "huong dan",
        "hướng dẫn",
    ]
    version_pattern = re.compile(r"(?:chatgpt|gpt|claude|gemini|grok|qwen|minimax)(?:\s+[a-z0-9.+-]+){0,2}\s+\d+(?:\.\d+)+(?:-[a-z0-9]+)?", re.IGNORECASE)

    scored: List[tuple[int, Dict[str, Any]]] = []
    for source in sources or []:
        title = _normalize_text(source.get("title"))
        snippet = _normalize_text(source.get("snippet") or source.get("content"))
        blob = f"{title} {snippet}".lower()
        score = 0
        if any(alias in blob for alias in aliases):
            score += 4
        if any(marker in blob for marker in release_markers):
            score += 3
        if version_pattern.search(blob):
            score += 4
        if any(candidate.lower() in blob for candidate in candidates or []):
            score += 5
        if _search_source_is_officialish(source):
            score += 4
        elif _search_source_is_high_trust(source):
            score += 2
        if source.get("published_at"):
            score += 1
        if any(marker in blob for marker in low_signal_markers):
            score -= 4
        if score > 0:
            scored.append((score, source))

    scored.sort(key=lambda item: item[0], reverse=True)
    focused = [item[1] for item in scored[:5]]
    return focused or list(sources or [])


def _latest_model_detail_points(subject: str, sources: List[Dict[str, Any]], candidates: List[str], limit: int = 3) -> List[str]:
    aliases = _subject_aliases(subject)
    candidate_keys = [_normalize_text(item).lower() for item in candidates or [] if _normalize_text(item)]
    detail_markers = [
        "token",
        "context",
        "window",
        "benchmark",
        "swe-bench",
        "reasoning",
        "agent",
        "coding",
        "voice",
        "tool",
        "vision",
        "released",
        "release",
        "announced",
        "announcement",
        "update",
        "updated",
        "million",
        "triệu",
        "ra mắt",
        "ra mat",
        "cập nhật",
        "cap nhat",
        "opus",
        "sonnet",
        "pro",
        "flash",
        "thinking",
    ]
    generic_markers = [
        "với những cải tiến không ngừng",
        "làm thay đổi cách chúng ta tương tác",
        "thị trường ai tạo sinh",
        "cuộc đua đếm số",
        "kỷ nguyên inference compute",
        "hidden thought layer",
        "table of contents",
        "introduction",
        "mục lục",
        "giới thiệu",
        "noi dung chinh",
        "nội dung chính",
        "mau prompt",
        "mẫu prompt",
        "cau lenh",
        "câu lệnh",
        "huong dan",
        "hướng dẫn",
        "with continuous improvements",
        "changing how we interact",
        "generative ai market",
        "the market has moved",
    ]
    version_pattern = re.compile(
        r"(?:chatgpt|gpt|claude|gemini|grok|qwen|minimax)(?:\s+[a-z0-9.+-]+){0,2}\s+\d+(?:\.\d+)+(?:-[a-z0-9]+)?",
        re.IGNORECASE,
    )
    date_pattern = re.compile(r"\b(?:20\d{2}(?:[-/]\d{2}(?:[-/]\d{2})?)?|[A-Z][a-z]{2,8}\s+\d{1,2},?\s+20\d{2})\b")

    scored: List[tuple[int, str]] = []
    seen: Set[str] = set()
    for source in sources or []:
        officialish = _search_source_is_officialish(source)
        high_trust = _search_source_is_high_trust(source)
        for raw_text in [
            _normalize_text(source.get("title")),
            _normalize_text(source.get("snippet") or source.get("content")),
        ]:
            clean_text = _clean_search_ui_text(raw_text)
            if not clean_text:
                continue
            parts = [clean_text] if len(clean_text) <= 180 else re.split(r"(?<=[.!?])\s+", clean_text)
            for part in parts:
                row = _clean_search_ui_text(part)
                if not row or len(row) < 38:
                    continue
                blob = row.lower()
                score = 0
                if any(alias in blob for alias in aliases):
                    score += 3
                if version_pattern.search(blob):
                    score += 5
                if any(candidate in blob for candidate in candidate_keys):
                    score += 6
                if any(marker in blob for marker in detail_markers):
                    score += 2
                if date_pattern.search(row):
                    score += 1
                if officialish:
                    score += 3
                elif high_trust:
                    score += 1
                if any(marker in blob for marker in generic_markers):
                    score -= 3
                score -= _search_text_structure_penalty(row)
                if score < 4:
                    continue
                row = re.sub(r"\s+", " ", row).strip()
                if len(row) > 220:
                    row = row[:220].rsplit(" ", 1)[0].strip() + "..."
                key = row.lower()
                if key in seen:
                    continue
                seen.add(key)
                scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def _latest_model_subject_summary(subject: str, sources: List[Dict[str, Any]], language: str = "vi") -> str:
    bundle = _latest_model_subject_bundle(subject, sources)
    names = bundle["candidates"]
    latest_date = bundle["latest_date"]
    focused_sources = _latest_model_focus_sources(subject, bundle["relevant"] or sources, names)
    detail_points = _latest_model_detail_points(subject, focused_sources, names, limit=2)
    detail_text = " ".join(detail_points).strip()

    if language == "vi":
        lead = (
            f"Các tên model đang nổi bật nhất quanh {subject} hiện là {', '.join(names)}."
            if names
            else f"Nội dung bám sát {subject} hiện tập trung vào lớp cập nhật mới nhất."
        )
        support = detail_text
        date_line = f"Mốc cập nhật gần nhất thấy rõ là {latest_date}." if latest_date else ""
        return _clean_search_ui_text(f"{lead} {support} {date_line}")

    lead = (
        f"The model names surfacing most directly around {subject} are {', '.join(names)}."
        if names
        else f"The retained detail around {subject} is clustering around the newest update layer."
    )
    support = detail_text
    date_line = f"The clearest recent date in the retained layer is {latest_date}." if latest_date else ""
    return _clean_search_ui_text(f"{lead} {support} {date_line}")


def _build_search_actions(language: str = "vi") -> List[Dict[str, Any]]:
    if language == "vi":
        return [
            {"id": "brief-to-studio", "label": "Mở trong Studio", "kind": "studio"},
            {"id": "deepen-search", "label": "Đào sâu thêm", "kind": "search"},
            {"id": "compare-previous", "label": "So với bản trước", "kind": "search"},
        ]
    return [
        {"id": "brief-to-studio", "label": "Open in Studio", "kind": "studio"},
        {"id": "deepen-search", "label": "Go deeper", "kind": "search"},
        {"id": "compare-previous", "label": "Compare previous", "kind": "search"},
    ]


def _build_search_outputs(query: str, brief: str, language: str = "vi") -> List[Dict[str, Any]]:
    short_brief = _clean_search_ui_text(" ".join(_brief_sentences(brief, limit=2)))
    if language == "vi":
        return [
            {
                "type": "report",
                "mode": "research",
                "title": f"Báo cáo nhanh: {query}",
                "summary": f"Tổng hợp điểm mới nhất, nguồn xác thực và khoảng trống cần kiểm chứng về {query}.",
                "prompt": f"Viết báo cáo ngắn về {query}. Dựa trên brief sau: {short_brief}",
            },
            {
                "type": "mindmap",
                "mode": "study",
                "title": f"Mindmap: {query}",
                "summary": f"Tách {query} thành ý chính, nguồn xác nhận và phần cần theo dõi tiếp.",
                "prompt": f"Tạo mindmap cho {query}. Bám vào brief này: {short_brief}",
            },
            {
                "type": "flashcard",
                "mode": "study",
                "title": f"Flashcard: {query}",
                "summary": f"Chuyển {query} thành bộ flashcard để ôn nhanh phần thông tin đã được xác thực.",
                "prompt": f"Tạo bộ flashcard cho {query}. Chỉ dùng phần đã xác thực trong brief này: {short_brief}",
            },
        ]
    return [
        {
            "type": "report",
            "mode": "research",
            "title": f"Quick report: {query}",
            "summary": f"Summarize the latest verified points, supporting evidence, and open gaps about {query}.",
            "prompt": f"Write a short report about {query}. Use this brief as the source: {short_brief}",
        },
        {
            "type": "mindmap",
            "mode": "study",
            "title": f"Mindmap: {query}",
            "summary": f"Break {query} into core ideas, confirming evidence, and follow-up items.",
            "prompt": f"Create a mindmap for {query}. Use this brief as the source: {short_brief}",
        },
        {
            "type": "flashcard",
            "mode": "study",
            "title": f"Flashcards: {query}",
            "summary": f"Turn {query} into flashcards focused on the verified information.",
            "prompt": f"Create flashcards for {query}. Use only the verified parts of this brief: {short_brief}",
        },
    ]


def _build_search_tracks_fallback(
    query: str,
    brief: str,
    sources: List[Dict[str, Any]],
    language: str = "vi",
    historical: bool = False,
    query_class: str = "general",
    latest_subjects: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    brief_bits = _brief_sentences(brief, limit=2)
    latest_date = _clean_search_ui_text(next((item.get("published_at") for item in sources if item.get("published_at")), ""))
    snippet_bits = _search_snippet_samples(sources, limit=4, max_chars=190)
    latest_subjects = list(latest_subjects or (_extract_search_subjects(query) if str(query_class or "").strip().lower() == "latest_model" else []))
    if len(latest_subjects) == 1:
        subject = latest_subjects[0]
        bundle = _latest_model_subject_bundle(subject, sources)
        subject_latest_date = bundle["latest_date"] or latest_date
        subject_focus_sources = _latest_model_focus_sources(subject, bundle["relevant"], bundle["candidates"])
        subject_details = _latest_model_detail_points(subject, subject_focus_sources, bundle["candidates"], limit=3)
        subject_snippets = _search_snippet_samples(subject_focus_sources, limit=4, max_chars=190)
        candidate_text = ", ".join(bundle["candidates"])
        overview = " ".join(brief_bits[:2]).strip() or _latest_model_subject_summary(subject, sources, language=language)
        if language == "vi":
            track_rows = [
                {
                    "key": "overview",
                    "icon": "🧭",
                    "label": "Toàn cảnh",
                    "title": f"Toàn cảnh hiện tại của {subject}",
                    "description": overview,
                },
                {
                    "key": "highlights",
                    "icon": "✨",
                    "label": "Nổi bật",
                    "title": "Những chi tiết nổi bật nhất",
                    "description": (
                        subject_details[0]
                        if subject_details
                        else brief_bits[1]
                        if len(brief_bits) > 1
                        else brief_bits[0]
                        if brief_bits
                        else subject_snippets[0]
                        if subject_snippets
                        else f"Phần thông tin đang bám trực tiếp vào {subject} hiện nằm trong lớp cập nhật mới nhất."
                    )
                },
                {
                    "key": "changes",
                    "icon": "🔄",
                    "label": "Thay đổi",
                    "title": "Điểm thay đổi đáng chú ý",
                    "description": (
                        (
                            f"Các tên model và nhánh cập nhật đang nổi lên quanh {candidate_text}. "
                            if candidate_text else
                            f"Phần thay đổi đang nổi lên quanh {subject}. "
                        )
                        + (
                            subject_details[1]
                            if len(subject_details) > 1
                            else brief_bits[1]
                            if len(brief_bits) > 1
                            else brief_bits[0]
                            if brief_bits
                            else subject_snippets[1]
                            if len(subject_snippets) > 1
                            else f"Phần quan trọng là tách rõ tên model, khả năng chính và khác biệt so với giai đoạn trước."
                        )
                    ),
                },
                {
                    "key": "timeline",
                    "icon": "🚀",
                    "label": "Nhịp cập nhật",
                    "title": "Mốc cập nhật đang thấy",
                    "description": (
                        (
                            f"Mốc gần nhất đang giữ lại là {subject_latest_date}. "
                            if subject_latest_date else
                            f"Lớp nội dung hiện tại của {subject} chưa tách ra một mốc ngày thật sự nổi bật. "
                        )
                        + (
                            subject_details[2]
                            if len(subject_details) > 2
                            else brief_bits[1]
                            if len(brief_bits) > 1
                            else brief_bits[0]
                            if brief_bits
                            else subject_snippets[2]
                            if len(subject_snippets) > 2
                            else f"Khi cần chốt nhanh, hãy nhìn vào tên model, khác biệt chính và phần mới hơn so với lớp trước."
                        )
                    ),
                },
            ]
        else:
            track_rows = [
                {
                    "key": "overview",
                    "icon": "🧭",
                    "label": "Overview",
                    "title": f"Current overview for {subject}",
                    "description": overview,
                },
                {
                    "key": "highlights",
                    "icon": "✨",
                    "label": "Highlights",
                    "title": "The strongest current details",
                    "description": (
                        subject_details[0]
                        if subject_details
                        else brief_bits[1]
                        if len(brief_bits) > 1
                        else brief_bits[0]
                        if brief_bits
                        else subject_snippets[0]
                        if subject_snippets
                        else f"The retained detail around {subject} is staying close to the newest update layer."
                    )
                },
                {
                    "key": "changes",
                    "icon": "🔄",
                    "label": "Changes",
                    "title": "The most relevant changes",
                    "description": (
                        (
                            f"The current update branch keeps surfacing {candidate_text}. "
                            if candidate_text else
                            f"The current change layer for {subject} is opening into a few newer detail clusters. "
                        )
                        + (
                            subject_details[1]
                            if len(subject_details) > 1
                            else brief_bits[1]
                            if len(brief_bits) > 1
                            else brief_bits[0]
                            if brief_bits
                            else subject_snippets[1]
                            if len(subject_snippets) > 1
                            else f"The useful move is to separate the model name, key capability changes, and the difference from the previous phase."
                        )
                    ),
                },
                {
                    "key": "timeline",
                    "icon": "🚀",
                    "label": "Timeline",
                    "title": "The current timing signal",
                    "description": (
                        (
                            f"The clearest retained date is {subject_latest_date}. "
                            if subject_latest_date else
                            f"The retained material for {subject} does not separate one dominant date yet. "
                        )
                        + (
                            subject_details[2]
                            if len(subject_details) > 2
                            else brief_bits[1]
                            if len(brief_bits) > 1
                            else brief_bits[0]
                            if brief_bits
                            else subject_snippets[2]
                            if len(subject_snippets) > 2
                            else f"If you want the next pass, focus on model naming, the main capability shifts, and what changed from the earlier version."
                        )
                    ),
                },
            ]
        return [{"description": _clean_search_ui_text(item.get("description")), **item} for item in track_rows]
    if len(latest_subjects) >= 2:
        primary_subjects = latest_subjects[:2]
        first_bundle = _latest_model_subject_bundle(primary_subjects[0], sources)
        second_bundle = _latest_model_subject_bundle(primary_subjects[1], sources)
        first_focus_sources = _latest_model_focus_sources(primary_subjects[0], first_bundle["relevant"], first_bundle["candidates"])
        second_focus_sources = _latest_model_focus_sources(primary_subjects[1], second_bundle["relevant"], second_bundle["candidates"])
        first_details = _latest_model_detail_points(primary_subjects[0], first_focus_sources, first_bundle["candidates"], limit=2)
        second_details = _latest_model_detail_points(primary_subjects[1], second_focus_sources, second_bundle["candidates"], limit=2)
        first_snippets = _search_snippet_samples(
            first_focus_sources,
            limit=2,
            max_chars=180,
        )
        second_snippets = _search_snippet_samples(
            second_focus_sources,
            limit=2,
            max_chars=180,
        )
        first_candidates = ", ".join(first_bundle["candidates"])
        second_candidates = ", ".join(second_bundle["candidates"])
        if language == "vi":
            track_rows = [
                {
                    "key": "subject_1",
                    "icon": "🧠",
                    "label": "Chủ thể 1",
                    "title": f"Toàn cảnh hiện tại của {primary_subjects[0]}",
                    "description": _latest_model_subject_summary(primary_subjects[0], sources, language=language),
                },
                {
                    "key": "subject_2",
                    "icon": "⚙️",
                    "label": "Chủ thể 2",
                    "title": f"Toàn cảnh hiện tại của {primary_subjects[1]}",
                    "description": _latest_model_subject_summary(primary_subjects[1], sources, language=language),
                },
                {
                    "key": "difference",
                    "icon": "🔀",
                    "label": "Khác biệt",
                    "title": "Điểm khác nhau đang lộ rõ",
                    "description": (
                        f"{primary_subjects[0]} đang xoay quanh {first_candidates}. "
                        if first_candidates else
                        f"{primary_subjects[0]} đang hiện ra như một nhánh cập nhật riêng. "
                    )
                    + (
                        f"{primary_subjects[1]} thì đang xoay quanh {second_candidates}. "
                        if second_candidates else
                        f"{primary_subjects[1]} cũng đang nổi lên theo một nhánh khác. "
                    )
                    + (
                        first_details[0]
                        if first_details
                        else second_details[0]
                        if second_details
                        else first_snippets[0]
                        if first_snippets
                        else second_snippets[0]
                        if second_snippets
                        else f"Cách đọc tốt nhất là tách riêng từng chủ thể trước khi so điểm giống và khác."
                    ),
                },
                {
                    "key": "big_picture",
                    "icon": "🌐",
                    "label": "Bức tranh chung",
                    "title": "Nếu nhìn cả hai cùng lúc thì đang thấy gì",
                    "description": (
                        brief_bits[0]
                        if brief_bits else
                        f"Lượt tra cứu này cho thấy {primary_subjects[0]} và {primary_subjects[1]} đang được nhắc tới theo hai nhịp cập nhật riêng, nên nên đọc theo từng nhánh rồi mới tổng hợp."
                    ),
                },
            ]
        else:
            track_rows = [
                {
                    "key": "subject_1",
                    "icon": "🧠",
                    "label": "Subject 1",
                    "title": f"Current overview for {primary_subjects[0]}",
                    "description": _latest_model_subject_summary(primary_subjects[0], sources, language=language),
                },
                {
                    "key": "subject_2",
                    "icon": "⚙️",
                    "label": "Subject 2",
                    "title": f"Current overview for {primary_subjects[1]}",
                    "description": _latest_model_subject_summary(primary_subjects[1], sources, language=language),
                },
                {
                    "key": "difference",
                    "icon": "🔀",
                    "label": "Difference",
                    "title": "What difference is starting to show",
                    "description": (
                        f"{primary_subjects[0]} is surfacing around {first_candidates}. "
                        if first_candidates else
                        f"{primary_subjects[0]} is appearing as its own update branch. "
                    )
                    + (
                        f"{primary_subjects[1]} is surfacing around {second_candidates}. "
                        if second_candidates else
                        f"{primary_subjects[1]} is also forming a separate branch. "
                    )
                    + (
                        first_details[0]
                        if first_details
                        else second_details[0]
                        if second_details
                        else first_snippets[0]
                        if first_snippets
                        else second_snippets[0]
                        if second_snippets
                        else f"The practical move is to read each subject separately before synthesizing them together."
                    ),
                },
                {
                    "key": "big_picture",
                    "icon": "🌐",
                    "label": "Big picture",
                    "title": "What the combined picture looks like",
                    "description": (
                        brief_bits[0]
                        if brief_bits else
                        f"This search pass shows {primary_subjects[0]} and {primary_subjects[1]} moving on separate update rhythms, so read them branch by branch before merging conclusions."
                    ),
                },
            ]
        return [{"description": _clean_search_ui_text(item.get("description")), **item} for item in track_rows]
    if language == "vi":
        track_rows = [
            {
                "key": "focus",
                "icon": "🧭",
                "label": "Trọng tâm",
                "title": f"Điểm chính về {query}",
                "description": brief_bits[0] if brief_bits else f"Skemi đã gom phần cốt lõi nhất liên quan trực tiếp đến {query}.",
            },
            {
                "key": "details",
                "icon": "✨",
                "label": "Chi tiết",
                "title": "Các chi tiết nổi bật đang xuất hiện",
                "description": (
                    snippet_bits[0]
                    if snippet_bits else
                    brief_bits[1] if len(brief_bits) > 1 else f"Skemi đang gom các mô tả cụ thể nhất xoay quanh {query}."
                ),
            },
            {
                "key": "angles",
                "icon": "🧩",
                "label": "Góc nhìn",
                "title": "Các nhánh nên tách ra để đọc rõ hơn",
                "description": (
                    snippet_bits[1]
                    if len(snippet_bits) > 1 else
                    f"Khi đọc {query}, nên tách riêng bối cảnh, điểm mới, phần ứng dụng và các nhánh phụ để không bị dồn mọi thứ vào một đoạn."
                ),
            },
            {
                "key": "next",
                "icon": "🚀",
                "label": "Tiếp tục",
                "title": "Nên đọc tiếp theo hướng nào",
                "description": (
                    (
                        f"Mốc thời gian gần nhất trong lượt tra cứu này là {latest_date}. "
                        if latest_date else
                        ""
                    )
                    + (
                        snippet_bits[2]
                        if len(snippet_bits) > 2 else
                        f"Nếu muốn đi sâu hơn, hãy mở tiếp theo hướng thay đổi mới nhất, phần khác với giai đoạn trước hoặc ứng dụng thực tế của {query}."
                    )
                ),
            },
        ]
    else:
        track_rows = [
            {
                "key": "focus",
                "icon": "🧭",
                "label": "Focus",
                "title": f"Core takeaway about {query}",
                "description": brief_bits[0] if brief_bits else f"Skemi pulled out the most central point directly tied to {query}.",
            },
            {
                "key": "details",
                "icon": "✨",
                "label": "Details",
                "title": "What details are standing out",
                "description": (
                    snippet_bits[0]
                    if snippet_bits else
                    brief_bits[1] if len(brief_bits) > 1 else f"Skemi is consolidating the clearest concrete details around {query}."
                ),
            },
            {
                "key": "angles",
                "icon": "🧩",
                "label": "Angles",
                "title": "Which angles should be separated out",
                "description": (
                    snippet_bits[1]
                    if len(snippet_bits) > 1 else
                    f"To read {query} cleanly, split it into context, the newest details, practical use, and any side branches instead of compressing everything into one block."
                ),
            },
            {
                "key": "next",
                "icon": "🚀",
                "label": "Next",
                "title": "What direction to read next",
                "description": (
                    (
                        f"The most recent retained date in this search pass is {latest_date}. "
                        if latest_date else
                        ""
                    )
                    + (
                        snippet_bits[2]
                        if len(snippet_bits) > 2 else
                        f"If you want to go deeper, open the next pass around what changed most recently, what differs from the previous phase, or the practical use of {query}."
                    )
                ),
            },
        ]
    return [{"description": _clean_search_ui_text(item.get("description")), **item} for item in track_rows]


def _build_search_followups_fallback(query: str, language: str = "vi") -> List[str]:
    if language == "vi":
        return [
            f"Điểm mới nhất về {query} là gì",
            f"Chi tiết nào của {query} đang nổi bật nhất lúc này",
            f"{query} khác gì so với bản trước hoặc giai đoạn trước",
            f"{query} đang được ứng dụng hoặc nhắc tới nhiều nhất ở điểm nào",
        ]
    return [
        f"What is the latest update about {query}",
        f"Which detail about {query} is standing out most right now",
        f"How does {query} differ from the previous version or phase",
        f"Where is {query} being applied or discussed most right now",
    ]


def _build_search_verification_checks_fallback(query: str, language: str = "vi") -> List[str]:
    if language == "vi":
        return [
            "Ưu tiên phần nội dung đi thẳng vào trạng thái hiện tại thay vì đoạn mở bài hoặc phần giới thiệu dài.",
            "So mốc thời gian để chắc rằng thông tin mới hơn thực sự thay thế phần cũ.",
            f"Nếu truy vấn là “mới nhất”, chỉ giữ thông tin trực tiếp nói về {query} ở hiện tại.",
            "Tách riêng những điểm đã lặp lại nhiều lần với những điểm mới chỉ xuất hiện rải rác.",
        ]
    return [
        "Prioritize content that speaks directly to the current state instead of long intros or generic setup.",
        "Compare timing markers so newer information actually replaces older claims.",
        f"If the query asks for the latest answer, keep only information directly tied to the current state of {query}.",
        "Separate repeated core points from one-off details that still look unstable.",
    ]


def _build_search_decision_paths_fallback(query: str, brief: str, language: str = "vi") -> List[Dict[str, Any]]:
    short_brief = _clean_search_ui_text(" ".join(_brief_sentences(brief, limit=2)))
    if language == "vi":
        return [
            {
                "title": "Đào sâu tiếp",
                "description": f"Mở rộng {query} thành một lượt tra cứu tiếp theo để làm rõ phần mới nhất và phần còn mơ hồ.",
                "action": "follow-up",
                "query": f"điểm mới nhất của {query}",
            },
            {
                "title": "Biến thành mindmap",
                "description": f"Chuyển brief hiện tại của {query} thành sơ đồ ý để học nhanh hoặc trình bày lại trong Studio.",
                "action": "studio",
                "type": "mindmap",
                "prompt": f"Tạo mindmap về {query}. Brief làm gốc: {short_brief}",
            },
            {
                "title": "Lập checklist xác minh",
                "description": f"Biến kết quả tra cứu về {query} thành checklist kiểm chứng để tránh lẫn thông tin cũ và mới.",
                "action": "copy",
            },
        ]
    return [
        {
            "title": "Go deeper",
            "description": f"Expand {query} into a follow-up search focused on official evidence and unresolved details.",
            "action": "follow-up",
            "query": f"latest official source about {query}",
        },
        {
            "title": "Turn it into a mindmap",
            "description": f"Convert the current brief for {query} into a visual map for study or presentation in Studio.",
            "action": "studio",
            "type": "mindmap",
            "prompt": f"Create a mindmap about {query}. Use this brief as the base: {short_brief}",
        },
        {
            "title": "Create a verification checklist",
            "description": f"Turn the search result for {query} into a checklist that separates current evidence from stale claims.",
            "action": "copy",
        },
    ]


async def _build_search_ui_enhancements(
    query: str,
    language: str,
    context_text: str,
    sources: List[Dict[str, Any]],
    brief: str,
    historical: bool,
    query_class: str = "general",
    latest_subjects: Optional[List[str]] = None,
) -> Dict[str, Any]:
    topic_query = ", ".join((latest_subjects or [])[:2]).strip() or query
    fallback_headline = _clean_search_ui_text(topic_query if str(query_class or "").strip().lower() == "latest_model" else query)
    fallback = {
        "headline": fallback_headline,
        "status_line": _clean_search_ui_text(
            (
                "Skemi đã gom phần nội dung gần nhất thành bản đọc nhanh theo đúng truy vấn."
                if language == "vi"
                else "Skemi condensed the newest relevant content into a quick read for this query."
            )
        ),
        "brief": _clean_search_ui_text(brief),
        "tracks": _build_search_tracks_fallback(
            query,
            brief,
            sources,
            language=language,
            historical=historical,
            query_class=query_class,
            latest_subjects=latest_subjects,
        ),
        "follow_ups": _build_search_followups_fallback(topic_query, language=language),
        "verification_checks": _build_search_verification_checks_fallback(topic_query, language=language),
        "decision_paths": _build_search_decision_paths_fallback(topic_query, brief, language=language),
    }

    clean_context = _normalize_text(context_text)
    if len(clean_context) < 600 or len(sources) < 2:
        return fallback
    topic_label = topic_query

    prompt = (
        "You are designing the Search UI response for Skemi.\n"
        f"Write everything in {'Vietnamese' if language == 'vi' else 'English'}.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "headline": "...",\n'
        '  "status_line": "...",\n'
        '  "brief": "...",\n'
        '  "tracks": [{"key":"...", "icon":"...", "label":"...", "title":"...", "description":"..."}],\n'
        '  "follow_ups": ["..."],\n'
        '  "verification_checks": ["..."],\n'
        '  "decision_paths": [{"title":"...", "description":"...", "action":"follow-up|studio|copy", "query":"...", "type":"mindmap|report|flashcard", "prompt":"..."}]\n'
        "}\n"
        "Rules:\n"
        "- Plain text only. No markdown. No tables. No pipe characters.\n"
        "- Focus on the user's exact query.\n"
        "- Ignore navigation text, menus, section headings, table-of-contents text, intro filler, promotional filler, and repeated boilerplate.\n"
        "- If the user asks for latest/current/newest information, keep only the latest verified facts and explicitly avoid older details unless they are needed to explain a change.\n"
        "- Do not talk about sources, evidence quality, or verification process in the visible answer unless the user explicitly asks for that.\n"
        "- For latest-model queries, answer in a topic-first way: current model/version names, standout changes, timing, and what differs from the previous phase.\n"
        "- If the raw user query contains typos or noisy variants, follow the resolved topic label instead of echoing the typo.\n"
        "- The 4 tracks must be 4 clearly different angles of the same topic.\n"
        "- If the query mentions multiple products or vendors, dedicate separate tracks to the main named subjects before adding cross-cutting tracks.\n"
        "- Keep the brief concise but specific.\n"
        "- follow_ups must be search-ready questions.\n"
        "- verification_checks must be practical checks, not vague advice.\n"
        "- decision_paths must be directly useful next moves.\n\n"
        f"User query: {query}\n"
        f"Resolved topic label: {topic_label}\n"
        f"Historical mode: {'yes' if historical else 'no'}\n"
        f"Query class: {query_class}\n"
        f"Current brief: {_clean_search_ui_text(brief)}\n\n"
        f"Grounded source context:\n{clean_context[:24000]}"
    )

    raw = await _generate_text(prompt, model=getattr(backend, "MODEL_MAIN", None), num_predict=1800)
    parsed = _extract_json_block(raw)
    if not parsed:
        return fallback

    tracks = parsed.get("tracks") if isinstance(parsed.get("tracks"), list) else []
    normalized_tracks: List[Dict[str, Any]] = []
    for index, item in enumerate(tracks):
        if not isinstance(item, dict):
            continue
        title = _clean_search_ui_text(item.get("title"))
        description = _clean_search_ui_text(item.get("description"))
        if not title or not description:
            continue
        normalized_tracks.append(
            {
                "key": _clean_search_ui_text(item.get("key") or f"angle_{index + 1}") or f"angle_{index + 1}",
                "icon": _clean_search_ui_text(item.get("icon") or "✨") or "✨",
                "label": _clean_search_ui_text(item.get("label") or ""),
                "title": title,
                "description": description,
            }
        )
        if len(normalized_tracks) >= 4:
            break

    decision_paths = parsed.get("decision_paths") if isinstance(parsed.get("decision_paths"), list) else []
    normalized_paths: List[Dict[str, Any]] = []
    for item in decision_paths:
        if not isinstance(item, dict):
            continue
        title = _clean_search_ui_text(item.get("title"))
        description = _clean_search_ui_text(item.get("description"))
        if not title or not description:
            continue
        normalized_paths.append(
            {
                "title": title,
                "description": description,
                "action": _clean_search_ui_text(item.get("action") or "follow-up") or "follow-up",
                "query": _clean_search_ui_text(item.get("query") or ""),
                "type": _clean_search_ui_text(item.get("type") or "report") or "report",
                "prompt": _clean_search_ui_text(item.get("prompt") or ""),
            }
        )
        if len(normalized_paths) >= 3:
            break

    result = {
        "headline": _clean_search_ui_text(parsed.get("headline")) or fallback["headline"],
        "status_line": _clean_search_ui_text(parsed.get("status_line")) or fallback["status_line"],
        "brief": _clean_search_ui_text(parsed.get("brief")) or fallback["brief"],
        "tracks": normalized_tracks if len(normalized_tracks) >= 4 else fallback["tracks"],
        "follow_ups": _trim_list_texts(parsed.get("follow_ups") if isinstance(parsed.get("follow_ups"), list) else [], limit=4) or fallback["follow_ups"],
        "verification_checks": _trim_list_texts(parsed.get("verification_checks") if isinstance(parsed.get("verification_checks"), list) else [], limit=4) or fallback["verification_checks"],
        "decision_paths": normalized_paths if len(normalized_paths) >= 3 else fallback["decision_paths"],
    }
    if str(query_class or "").strip().lower() == "latest_model":
        result["headline"] = fallback["headline"]
        result["brief"] = fallback["brief"]
        result["tracks"] = fallback["tracks"]
    return result


def _canonical_search_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "query": _normalize_text(payload.get("query")),
        "category": _normalize_text(payload.get("category")),
        "time": _normalize_text(payload.get("time") or payload.get("time_range")),
        "sort": _normalize_text(payload.get("sort")) or "relevance",
        "lang": _normalize_text(payload.get("language") or payload.get("lang")) or "vi",
        "deep_research": bool(payload.get("deep_research", False)),
        "search_context": _normalize_text(payload.get("search_context") or "search_page"),
    }


def _build_search_request_key(payload: Dict[str, Any]) -> str:
    canonical = _canonical_search_request_payload(payload)
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _search_cache_policy(payload: Dict[str, Any], query_class: str) -> Dict[str, Any]:
    query = _normalize_text(payload.get("query"))
    time_filter = _normalize_text(payload.get("time"))
    sort_mode = _normalize_text(payload.get("sort")) or "relevance"
    latest_like_query = bool(
        re.search(
            r"\b(latest|newest|current|recent|today)\b|mới nhất|moi nhat|gần đây|gan day|hiện tại|hien tai|hôm nay|hom nay",
            query,
            re.IGNORECASE,
        )
    )
    bypass_cache = (
        str(query_class or "").strip().lower() == "latest_model"
        or latest_like_query
        or bool(time_filter)
        or sort_mode == "date"
    )
    return {
        "enabled": not bypass_cache,
        "max_age_seconds": 60 if not bypass_cache else 0,
    }


def _cleanup_search_jobs() -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=SEARCH_JOB_TTL_SECONDS)
    stale_ids = [
        job_id
        for job_id, job in search_jobs.items()
        if datetime.fromtimestamp(float(job.get("updated_at", 0) or 0)) < cutoff
    ]
    for job_id in stale_ids:
        search_jobs.pop(job_id, None)


def _search_job_public_view(job: Dict[str, Any], include_analysis: bool = False) -> Dict[str, Any]:
    payload = {
        "id": job.get("id"),
        "request_key": job.get("request_key"),
        "query": job.get("query"),
        "status": job.get("status"),
        "context": job.get("context") or "search",
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error") or "",
        "progress_label": job.get("progress_label") or "",
    }
    if include_analysis and job.get("analysis"):
        payload["analysis"] = job.get("analysis")
    return payload

async def _polish_search_brief(
    query: str,
    language: str,
    context_text: str,
    historical: bool,
    query_class: str = "general",
    latest_subjects: Optional[List[str]] = None,
) -> str:
    clean_context = _normalize_text(context_text)
    if len(clean_context) < 120:
        return ""
    topic_label = ", ".join((latest_subjects or [])[:2]).strip() or query
    current_clock = backend.get_current_datetime()["full"] if hasattr(backend, "get_current_datetime") else datetime.utcnow().isoformat(timespec="seconds") + "Z"

    prompt = (
        "You are Skemi, a high-level Intelligence Analyst.\n"
        f"Write a structured, professional, and detailed research report in {'Vietnamese' if language == 'vi' else 'English'} about: {topic_label}\n"
        "Formatting Requirements:\n"
        "- Use Markdown for clarity (headers, bold text, bullet points).\n"
        "- Break content into logical sections with descriptive ## headers.\n"
        "- Use numbered lists for sequential points or rankings.\n"
        "- Ensure paragraphs are separated by clear double newlines.\n"
        "- Do not mention links, sources, search engines, or backend internals.\n"
        "Content Rules:\n"
        "- Use only the grounded context below.\n"
        "- Treat the provided Vietnam time as the true current time.\n"
        "- Prefer newer grounded facts over older conflicting ones.\n"
        "- Start with a clear EXECUTIVE SUMMARY paragraph.\n"
        "- If the query asks for the 'latest', focus aggressively on current status/versions.\n"
        "- Minimum 2500 characters, maximum 4500 characters.\n"
        f"- Historical mode: {'yes' if historical else 'no'}.\n"
        f"- Query class: {query_class}.\n"
        f"- Current local time: {current_clock}.\n"
        f"- User query: {query}.\n\n"
        f"Grounded context:\n{clean_context[:22000]}"
    )
    # Higher budget so the brief isn't cut off mid-sentence (user saw it stop at
    # "Định nghĩa:").
    polished = await _generate_text(prompt, model=getattr(backend, "MODEL_MAIN", None), num_predict=2400)
    return _normalize_text(polished)


def _confidence_level(value: Any) -> str:
    token = _clean_search_ui_text(value).strip().lower()
    if token in ("high", "cao", "strong", "chắc chắn", "chac chan"):
        return "high"
    if token in ("low", "thấp", "thap", "weak", "uncertain", "không chắc", "khong chac"):
        return "low"
    return "medium"


async def _build_deep_research_report(
    query: str,
    language: str,
    context_text: str,
    sources: List[Dict[str, Any]],
    brief: str,
    historical: bool,
    query_class: str = "general",
    latest_subjects: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """One extra grounded JSON call that turns the raw research context into a
    vivid, multi-module report (NOT a wall of text). Returns {} on any failure
    so the frontend can fall back to the plain brief."""
    clean_context = _normalize_text(context_text)
    # Token guard: only spend the extra call when there is real material.
    if len(clean_context) < 900 or len(sources) < 3:
        return {}
    topic_label = ", ".join((latest_subjects or [])[:2]).strip() or query
    current_clock = (
        backend.get_current_datetime()["full"]
        if hasattr(backend, "get_current_datetime")
        else datetime.utcnow().isoformat(timespec="seconds") + "Z"
    )

    prompt = (
        "You are Skemi Deep Research, the world's most trusted research analyst.\n"
        f"Write every value in {'Vietnamese' if language == 'vi' else 'English'}.\n"
        "Turn the grounded context into a VIVID, EASY-TO-ABSORB intelligence report — "
        "NOT a long wall of text. Be concrete, specific and lively.\n"
        "Return JSON ONLY with this exact schema:\n"
        "{\n"
        '  "tldr": ["punchy takeaway", "..."],\n'
        '  "sections": [{"icon":"emoji","heading":"...","body":"2-4 tight sentences"}],\n'
        '  "key_findings": [{"label":"short label","detail":"one sentence","confidence":"high|medium|low"}],\n'
        '  "entities": [{"name":"...","type":"person|org|product|place|concept","note":"why it matters"}],\n'
        '  "timeline": [{"date":"YYYY or YYYY-MM or label","event":"what happened"}],\n'
        '  "outlook": [{"horizon":"near|mid|long","prediction":"forward-looking call","confidence":"high|medium|low"}],\n'
        '  "contradictions": [{"claim":"...","counter":"the conflicting view"}],\n'
        '  "consensus": "one sentence on where sources agree"\n'
        "}\n"
        "Rules:\n"
        "- Plain text values only. No markdown, no pipe characters, no source/URL mentions.\n"
        "- Ground every statement in the context; never invent facts.\n"
        "- tldr: 3-5 items, each a vivid standalone insight.\n"
        "- sections: 3-5 DIFFERENT thematic angles, each with a fitting emoji icon.\n"
        "- key_findings: 3-6 items with honest confidence.\n"
        "- entities: 3-8 of the most important named things.\n"
        "- timeline: 0-6 dated milestones in chronological order; omit if none.\n"
        "- outlook: 2-4 forward-looking / predictive calls (this is what makes Skemi special). "
        "Treat the provided current time as true and reason about what likely comes next.\n"
        "- contradictions: 0-4 genuine conflicts between sources; omit if none.\n"
        "- consensus: where the evidence broadly agrees.\n"
        f"- Resolved topic: {topic_label}\n"
        f"- Historical mode: {'yes' if historical else 'no'}\n"
        f"- Query class: {query_class}\n"
        f"- Current local time: {current_clock}\n"
        f"- User query: {query}\n\n"
        f"Grounded source context:\n{clean_context[:24000]}"
    )

    # Larger budget so the structured JSON report isn't cut off mid-object (which
    # made _extract_json_block fail → empty report → the UI fell back to a flat brief
    # and looked like the segmented cards "disappeared").
    raw = await _generate_text(prompt, model=getattr(backend, "MODEL_MAIN", None), num_predict=3200)
    parsed = _extract_json_block(raw)
    if not isinstance(parsed, dict):
        return {}

    tldr = _trim_list_texts(parsed.get("tldr") if isinstance(parsed.get("tldr"), list) else [], limit=5)

    sections: List[Dict[str, Any]] = []
    for item in parsed.get("sections") if isinstance(parsed.get("sections"), list) else []:
        if not isinstance(item, dict):
            continue
        heading = _clean_search_ui_text(item.get("heading"))
        body = _clean_search_ui_text(item.get("body"))
        if not heading or not body:
            continue
        sections.append({
            "icon": _clean_search_ui_text(item.get("icon") or "✦") or "✦",
            "heading": heading,
            "body": body,
        })
        if len(sections) >= 5:
            break

    key_findings: List[Dict[str, Any]] = []
    for item in parsed.get("key_findings") if isinstance(parsed.get("key_findings"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_search_ui_text(item.get("label"))
        detail = _clean_search_ui_text(item.get("detail"))
        if not label and not detail:
            continue
        key_findings.append({
            "label": label or detail[:48],
            "detail": detail,
            "confidence": _confidence_level(item.get("confidence")),
        })
        if len(key_findings) >= 6:
            break

    entities: List[Dict[str, Any]] = []
    for item in parsed.get("entities") if isinstance(parsed.get("entities"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_search_ui_text(item.get("name"))
        if not name:
            continue
        entities.append({
            "name": name,
            "type": _clean_search_ui_text(item.get("type") or "concept") or "concept",
            "note": _clean_search_ui_text(item.get("note") or ""),
        })
        if len(entities) >= 8:
            break

    timeline: List[Dict[str, Any]] = []
    for item in parsed.get("timeline") if isinstance(parsed.get("timeline"), list) else []:
        if not isinstance(item, dict):
            continue
        event = _clean_search_ui_text(item.get("event"))
        if not event:
            continue
        timeline.append({
            "date": _clean_search_ui_text(item.get("date") or ""),
            "event": event,
        })
        if len(timeline) >= 6:
            break

    outlook: List[Dict[str, Any]] = []
    for item in parsed.get("outlook") if isinstance(parsed.get("outlook"), list) else []:
        if not isinstance(item, dict):
            continue
        prediction = _clean_search_ui_text(item.get("prediction"))
        if not prediction:
            continue
        horizon = _clean_search_ui_text(item.get("horizon") or "mid").strip().lower()
        if horizon not in ("near", "mid", "long"):
            horizon = "mid"
        outlook.append({
            "horizon": horizon,
            "prediction": prediction,
            "confidence": _confidence_level(item.get("confidence")),
        })
        if len(outlook) >= 4:
            break

    contradictions: List[Dict[str, Any]] = []
    for item in parsed.get("contradictions") if isinstance(parsed.get("contradictions"), list) else []:
        if not isinstance(item, dict):
            continue
        claim = _clean_search_ui_text(item.get("claim"))
        counter = _clean_search_ui_text(item.get("counter"))
        if not claim or not counter:
            continue
        contradictions.append({"claim": claim, "counter": counter})
        if len(contradictions) >= 4:
            break

    consensus = _clean_search_ui_text(parsed.get("consensus") or "")

    # Need at least a couple of meaningful modules to be worth showing.
    if len(sections) < 2 and len(key_findings) < 2 and not tldr:
        return {}

    return {
        "tldr": tldr,
        "sections": sections,
        "key_findings": key_findings,
        "entities": entities,
        "timeline": timeline,
        "outlook": outlook,
        "contradictions": contradictions,
        "consensus": consensus,
    }


async def _expand_deep_research_queries(query: str, base_queries: List[str], language: str) -> List[str]:
    """Build a DIVERSE, BILINGUAL deep-research query set so the engine gathers 100+
    UNIQUE sources instead of near-duplicates of one phrasing. Topic × aspect, in
    Vietnamese AND English (the English variant unlocks the huge international web)."""
    q = (query or "").strip()
    if not q:
        return base_queries or [query]
    out: List[str] = list(base_queries or [])
    # Keep the fan-out MODEST: too many queries overwhelm a slow/limited connection
    # (only one engine may respond) → everything times out → ZERO sources. A handful of
    # high-value aspects + an English variant is the safe sweet spot.
    # Modest fan-out for CONTENT diversity (the 100+ source COUNT is guaranteed
    # separately by the Wikipedia-reference harvest, so we don't need a huge query
    # fan-out here — that just adds latency when engines are slow).
    vi_aspects = ["giải pháp", "thực trạng và thách thức"]
    en_aspects = ["solutions and statistics", "latest research"]
    for a in vi_aspects:
        out.append(f"{q} {a}".strip())
    # Translate the topic to English ONCE to unlock international sources.
    en_topic = q
    try:
        raw = await _generate_text(
            "Translate this search topic into a concise English search query. "
            "Reply with ONLY the query — no quotes, no explanation:\n" + q,
            num_predict=40,
        )
        cand = ""
        if raw:
            cand = _normalize_text(raw).strip().strip('"').splitlines()[0][:120]
        if cand and len(cand) >= 3 and cand.lower() != q.lower():
            en_topic = cand
    except Exception:
        pass
    for a in en_aspects:
        out.append(f"{en_topic} {a}".strip())
    # Dedup (order-preserving) and cap so the fan-out latency stays bounded.
    seen: Set[str] = set()
    uniq: List[str] = []
    for item in out:
        k = _normalize_text(item).lower().strip()
        if k and k not in seen:
            seen.add(k)
            uniq.append(item)
    return uniq[:6]


def _wikipedia_sources_harvest(topic: str, vi: bool, max_sources: int = 150) -> List[Dict[str, Any]]:
    """RELIABLE 100+ source path. Wikipedia's API stays reachable even when the
    HTML-scraping search engines are blocked/rate-limited, and every article's
    reference section holds DOZENS of real, curated external sources. We search
    Wikipedia (VI + EN), add the articles themselves, then harvest the external
    links (references) of the top articles → a deep, reputable source pool. This is
    what makes deep research ALWAYS source-rich instead of hostage to flaky scrapers."""
    import urllib.request as _u, urllib.parse as _up, json as _j
    def _api(host: str, params: dict):
        url = f"https://{host}/w/api.php?" + _up.urlencode(params)
        req = _u.Request(url, headers={"User-Agent": "SkemiResearch/1.0 (deep research tool)"})
        return _j.loads(_u.urlopen(req, timeout=10).read())
    topic = (topic or "").strip()
    if not topic:
        return []
    hosts = ["vi.wikipedia.org", "en.wikipedia.org"] if vi else ["en.wikipedia.org", "vi.wikipedia.org"]
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for host in hosts:
        try:
            sd = _api(host, {"action": "query", "list": "search", "srsearch": topic,
                             "srlimit": 7, "format": "json"})
            titles = [s.get("title", "") for s in sd.get("query", {}).get("search", []) if s.get("title")]
        except Exception:
            continue
        for tt in titles:                      # the Wikipedia articles themselves
            wurl = f"https://{host}/wiki/" + _up.quote(tt.replace(" ", "_"))
            if wurl not in seen:
                seen.add(wurl)
                rows.append({"title": tt, "url": wurl, "domain": host,
                             "snippet": (f"Bài Wikipedia: {tt}" if vi else f"Wikipedia article: {tt}")})
        for tt in titles[:3]:                  # harvest references of the top articles
            try:
                ed = _api(host, {"action": "query", "titles": tt, "prop": "extlinks",
                                 "ellimit": 300, "format": "json"})
                for _pid, pg in ed.get("query", {}).get("pages", {}).items():
                    for e in pg.get("extlinks", []):
                        u = (e.get("*") or "").strip()
                        if u.startswith("//"):
                            u = "https:" + u
                        if not u.startswith("http") or u in seen:
                            continue
                        seen.add(u)
                        try:
                            dom = _up.urlparse(u).netloc.replace("www.", "")
                        except Exception:
                            dom = ""
                        rows.append({"title": dom or u[:70], "url": u, "domain": dom,
                                     "snippet": (f"Nguồn tham khảo trong bài “{tt}”" if vi else f"Reference cited in “{tt}”")})
                        if len(rows) >= max_sources:
                            return rows
            except Exception:
                continue
        if len(rows) >= max_sources:
            return rows
    return rows


async def _compute_search_analysis(payload: Dict[str, Any], job_id: Optional[str] = None) -> Dict[str, Any]:
    canonical_payload = _canonical_search_request_payload(payload)
    query = canonical_payload["query"]
    if not query:
        return {"success": False, "error": "Query is empty"}

    research_steps = []
    def _add_step(step: str):
        if not job_id: return
        research_steps.append(step)
        async def _update():
            async with search_job_lock:
                job = search_jobs.get(job_id)
                if job:
                    job["progress_label"] = step
                    job["research_steps"] = list(research_steps)
                    job["updated_at"] = time.time()
        asyncio.create_task(_update())

    requested_language = _normalize_search_language(canonical_payload.get("lang"))
    _add_step("Khởi tạo hệ thống phân tích đa luồng..." if requested_language == "vi" else "Initializing multi-threaded analysis system...")
    
    request_key = _build_search_request_key(canonical_payload)
    historical = False
    language = requested_language or "vi" 

    router_result = await backend.pure_model_router(
        query,
        conversation_context="",
        deep_research=bool(canonical_payload.get("deep_research", False)),
    )
    
    # Update language based on router if requested_language was not explicit
    language = requested_language or _normalize_search_language(router_result.get("language")) or "vi"
    historical = str(router_result.get("topic_type") or "").strip().lower() == "historical"
    
    _add_step(f"Đang định tuyến mô hình: {router_result.get('topic_type', 'General')}" if language == "vi" else f"Routing model: {router_result.get('topic_type', 'General')}")
    recency_priority = "low" if historical else str(router_result.get("recency_priority", "medium")).strip().lower()
    query_class = _resolve_search_query_class(query)
    cache_policy = _search_cache_policy(canonical_payload, query_class)
    if cache_policy["enabled"]:
        cached = global_cache.get(
            request_key,
            SEARCH_JOB_TYPE,
            threshold=2.0,
            max_age_seconds=cache_policy["max_age_seconds"],
        )
        if isinstance(cached, dict) and cached.get("success") and cached.get("analysis"):
            return cached
    router_queries_seed = _select_router_queries_seed(query, list(router_result.get("search_queries") or [query]), query_class)
    latest_subjects = _extract_search_subjects(query, router_queries_seed) if query_class == "latest_model" else []
    planned_queries = router_queries_seed if router_queries_seed else [query]
    _add_step(f"Đã lập kế hoạch {len(planned_queries)} truy vấn chuyên sâu..." if language == "vi" else f"Planned {len(planned_queries)} deep queries...")
    planned_queries = [item for item in planned_queries if _normalize_text(item)]
    if not planned_queries:
        planned_queries = [query]

    initial_deep = bool(canonical_payload.get("deep_research", False))
    # DEEP research: widen the net toward 100+ UNIQUE sources by searching DIVERSE
    # aspects in BOTH Vietnamese AND English (the same phrasing returns near-dups; the
    # aspect × bilingual fan-out taps the local + vast international web).
    if initial_deep and query_class != "latest_model":
        planned_queries = await _expand_deep_research_queries(query, planned_queries, language)
        _add_step(f"Mở rộng thành {len(planned_queries)} hướng truy vấn đa nguồn (Việt + Anh)..."
                  if language == "vi" else f"Expanded to {len(planned_queries)} multi-source query angles (VI + EN)...")
    # Deep research targets 100+ sources + richer context; standard stays lean/fast.
    target_context_chars = 18000 if initial_deep else 12000
    target_sources_per_query = 3 if initial_deep else 2
    target_total_sources = 100 if initial_deep else 10
    target_brief_chars = 3000

    async def _run_search_pass(planned_query: str, deep_mode: bool) -> Dict[str, Any]:
        _add_step(f"Phân tích lớp dữ liệu cho: {planned_query}" if language == "vi" else f"Analyzing data layer for: {planned_query}")
        try:
            result = await backend.fast_web_search(
                planned_query,
                recency_priority=recency_priority,
                deep_research=deep_mode,
                user_id=canonical_payload.get("search_context") or "search_page",
                query_class=query_class,
                on_progress=_add_step,
            )
        except Exception as exc:
            print(f"SEARCH ANALYZE QUERY ERROR [{planned_query}]: {exc}")
            return {"query": planned_query, "deep": deep_mode, "context": "", "urls": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"query": planned_query, "deep": deep_mode, "context": "", "urls": [], "error": "invalid_result"}
        urls = [item for item in (result.get("urls") or []) if isinstance(item, dict)]
        _add_step(f"Trích xuất thành công {len(urls)} nguồn từ: {planned_query}" if language == "vi" else f"Successfully extracted {len(urls)} sources from: {planned_query}")
        return {
            "query": planned_query,
            "deep": deep_mode,
            "context": _normalize_text(result.get("context")),
            "urls": urls,
        }

    async def _run_search_batch(queries_to_run: List[str], deep_mode: bool) -> List[Dict[str, Any]]:
        # BOUNDED CONCURRENCY: run queries in small waves instead of all-at-once.
        # Firing 12+ deep searches simultaneously saturates the network → every engine
        # times out → ZERO sources (worse than fewer queries). Waves of `WAVE` keep the
        # wide bilingual fan-out from overwhelming any connection (graceful degradation).
        WAVE = 3
        normalized: List[Dict[str, Any]] = []
        for w in range(0, len(queries_to_run), WAVE):
            chunk = queries_to_run[w:w + WAVE]
            results = await asyncio.gather(
                *[_run_search_pass(pq, deep_mode) for pq in chunk],
                return_exceptions=True,
            )
            for index, item in enumerate(results):
                if isinstance(item, Exception):
                    normalized.append({
                        "query": chunk[index], "deep": deep_mode,
                        "context": "", "urls": [], "error": str(item),
                    })
                else:
                    normalized.append(item)
        return normalized

    _add_step("Đang truy xuất dữ liệu từ các nguồn uy tín..." if language == "vi" else "Retrieving data from trusted sources...")
    search_runs = await _run_search_batch(planned_queries, initial_deep)
    query_records: Dict[str, Dict[str, Any]] = {
        planned_query: {"query": planned_query, "contexts": [], "urls": [], "passes": []}
        for planned_query in planned_queries
    }

    def _merge_search_run(run: Dict[str, Any]) -> None:
        planned_query = str(run.get("query") or "").strip()
        if not planned_query:
            return
        record = query_records.setdefault(planned_query, {"query": planned_query, "contexts": [], "urls": [], "passes": []})
        context_block = _normalize_text(run.get("context"))
        if context_block:
            record["contexts"].append(context_block)
        for source in run.get("urls") or []:
            if isinstance(source, dict):
                record["urls"].append(source)
        record["passes"].append(
            {
                "deep": bool(run.get("deep")),
                "context_chars": len(context_block),
                "source_count": len(_deduplicate_sources(run.get("urls") or [])),
                "error": _normalize_text(run.get("error")),
            }
        )

    for run in search_runs:
        _merge_search_run(run)

    def _merged_context_chars() -> int:
        return sum(len(_normalize_text("\n\n".join(record.get("contexts") or []))) for record in query_records.values())

    def _accepted_total_sources() -> int:
        merged: List[Dict[str, Any]] = []
        for record in query_records.values():
            merged.extend(record.get("urls") or [])
        return len(_deduplicate_sources(merged))

    underfilled_queries = [
        planned_query
        for planned_query, record in query_records.items()
        if len(_deduplicate_sources(record.get("urls") or [])) < target_sources_per_query
    ]

    if (not initial_deep) and (_accepted_total_sources() < target_total_sources and _merged_context_chars() < target_context_chars):
        _add_step("Mở rộng phạm vi tìm kiếm (Deep Research Pass 2)..." if language == "vi" else "Expanding search scope (Deep Research Pass 2)...")
        second_pass_queries = underfilled_queries or planned_queries
        second_pass_runs = await _run_search_batch(second_pass_queries, True)
        for run in second_pass_runs:
            _merge_search_run(run)
        search_runs.extend(second_pass_runs)

    if _accepted_total_sources() < target_total_sources or _merged_context_chars() < target_context_chars:
        broadening_queries: List[str] = []
        current_year = datetime.utcnow().year
        current_month = datetime.utcnow().strftime("%Y-%m")
        if query_class == "latest_model" and latest_subjects:
            broad_candidates = []
            for subject in latest_subjects[:4]:
                if language == "vi":
                    broad_candidates.extend([
                        f"{subject} model mới nhất {current_year}",
                        f"{subject} model mới nhất {current_month}",
                        f"nguồn chính thức {subject} model mới nhất {current_year}",
                    ])
                else:
                    broad_candidates.extend([
                        f"{subject} latest model {current_year}",
                        f"{subject} latest model {current_month}",
                        f"official source {subject} latest model {current_year}",
                    ])
        else:
            broad_candidates = [query, f"{query} {current_year}", f"{query} {current_month}"]
            for existing_query in planned_queries:
                if str(current_year) not in _normalize_text(existing_query):
                    broad_candidates.append(f"{existing_query} {current_year}")
        for candidate in broad_candidates:
            cleaned_candidate = _normalize_text(candidate)
            if cleaned_candidate and cleaned_candidate not in query_records and cleaned_candidate not in broadening_queries:
                broadening_queries.append(cleaned_candidate)
            if len(broadening_queries) >= 4:
                break
        if broadening_queries:
            fallback_runs = await _run_search_batch(broadening_queries, True)
            for run in fallback_runs:
                _merge_search_run(run)
            search_runs.extend(fallback_runs)

    context_blocks: List[str] = []
    raw_sources: List[Dict[str, Any]] = []
    query_stats: List[Dict[str, Any]] = []
    ordered_queries = planned_queries + [candidate for candidate in query_records.keys() if candidate not in planned_queries]
    for planned_query in ordered_queries:
        record = query_records.get(planned_query, {})
        merged_context = _normalize_text("\n\n".join(record.get("contexts") or []))
        deduped_query_sources = _deduplicate_sources(record.get("urls") or [])
        if merged_context:
            context_blocks.append(f"[query] {planned_query}\n{merged_context}")
        raw_sources.extend(deduped_query_sources)
        query_stats.append(
            {
                "query": planned_query,
                "passes": len(record.get("passes") or []),
                "accepted_sources": len(deduped_query_sources),
                "context_chars": len(merged_context),
                "deepened": any(bool(pass_info.get("deep")) for pass_info in record.get("passes") or []),
            }
        )

    deduped_raw_sources = _deduplicate_sources(raw_sources)
    # DEEP research source guarantee: top up toward 100+ with Wikipedia references
    # (curated real sources) — reliable even when the scraping engines are
    # blocked/throttled. Always runs for deep research so the source pool is rich.
    if initial_deep and len(deduped_raw_sources) < target_total_sources:
        try:
            _wiki_rows = await asyncio.to_thread(
                _wikipedia_sources_harvest, query, str(language or "vi").startswith("vi"),
                max(150, target_total_sources + 30),
            )
            if _wiki_rows:
                deduped_raw_sources = _deduplicate_sources(deduped_raw_sources + _wiki_rows)
                _add_step(f"Bổ sung {len(_wiki_rows)} nguồn tham khảo từ Wikipedia (đối soát)..."
                          if language == "vi" else f"Added {len(_wiki_rows)} Wikipedia reference sources...")
        except Exception as _wexc:
            print(f"[WIKI-HARVEST] skipped: {_wexc}")
    official_seed_contexts: List[str] = []
    if query_class == "latest_model" and latest_subjects:
        seed_sources = await _fetch_latest_model_seed_sources(latest_subjects)
        if seed_sources:
            deduped_raw_sources = _deduplicate_sources(deduped_raw_sources + seed_sources)
            for seed in seed_sources[:6]:
                seed_title = _clean_search_ui_text(seed.get("title") or seed.get("url") or "Official source")
                seed_body = _normalize_text(seed.get("content") or seed.get("snippet"))[:1400]
                if seed_body:
                    official_seed_contexts.append(f"[official] {seed_title}\n{seed_body}")
    filtered_sources = _filter_latest_sources(
        deduped_raw_sources,
        query,
        canonical_payload.get("time"),
        historical=historical,
        query_class=query_class,
    )
    if len(filtered_sources) < target_total_sources and len(deduped_raw_sources) >= target_total_sources:
        fallback_pool = [item for item in deduped_raw_sources if item not in filtered_sources]
        filtered_sources.extend(fallback_pool[: max(0, target_total_sources - len(filtered_sources))])
    official_source_count = len([item for item in filtered_sources if _search_source_is_officialish(item)])
    compact_sources = _compact_search_sources(filtered_sources, limit=(160 if initial_deep else 50))
    # The DRAWER lists every gathered source (full deduped pool), not just the ranked
    # primary set — so the user sees the maximum source coverage (deep research goal).
    compact_drawer = _compact_search_sources(deduped_raw_sources, limit=(200 if initial_deep else 60)) or compact_sources
    combined_context = "\n\n".join(context_blocks + official_seed_contexts)
    polished_brief = ""
    _add_step("Đang bóc tách và tổng hợp dữ liệu nơ-ron..." if language == "vi" else "Synthesizing and extracting neural data...")
    if len(filtered_sources) >= max(3, target_sources_per_query) and len(combined_context) >= 500:
        polished_brief = await _polish_search_brief(
            query,
            language,
            combined_context,
            historical,
            query_class=query_class,
            latest_subjects=latest_subjects,
        )
    brief = polished_brief or _build_search_brief(
        query,
        filtered_sources,
        language=language,
        historical=historical,
        query_class=query_class,
        latest_subjects=latest_subjects,
    )
    _add_step("Đang tối ưu hóa giao diện và chiến lược thực thi..." if language == "vi" else "Optimizing UI and execution strategy...")
    ui_enhancements = await _build_search_ui_enhancements(
        query=query,
        language=language,
        context_text=combined_context,
        sources=compact_sources,
        brief=brief,
        historical=historical,
        query_class=query_class,
        latest_subjects=latest_subjects,
    )
    # Deep research report: vivid multi-module synthesis (only on deep mode to save tokens).
    deep_report: Dict[str, Any] = {}
    if initial_deep:
        _add_step(
            "Đang dựng báo cáo nghiên cứu chuyên sâu trực quan..."
            if language == "vi"
            else "Building the vivid deep-research report..."
        )
        try:
            deep_report = await _build_deep_research_report(
                query=query,
                language=language,
                context_text=combined_context,
                sources=compact_sources,
                brief=brief,
                historical=historical,
                query_class=query_class,
                latest_subjects=latest_subjects,
            )
        except Exception as exc:
            print(f"DEEP RESEARCH REPORT ERROR: {exc}")
            deep_report = {}
    latest_dates = sorted([item.get("published_at") for item in filtered_sources if item.get("published_at")], reverse=True)
    targets_met = (
        len(filtered_sources) >= target_total_sources
        or len(combined_context) >= target_context_chars
    )
    insufficient_queries = [
        item["query"]
        for item in query_stats
        if item["accepted_sources"] < target_sources_per_query
    ]
    search_engine_info = {}
    local_search_engine = getattr(app, "skemi_search_engine", None) or getattr(backend, "search_engine", None)
    if local_search_engine and hasattr(local_search_engine, "get_engine_info"):
        try:
            search_engine_info = local_search_engine.get_engine_info()
        except Exception:
            search_engine_info = {}
    if local_search_engine and not search_engine_info.get("engine"):
        search_engine_info["engine"] = type(local_search_engine).__name__

    ui_brief = _clean_search_ui_text(ui_enhancements.get("brief") or "")
    base_brief = _clean_search_ui_text(brief)
    final_brief = base_brief if query_class == "latest_model" and base_brief else (ui_brief or base_brief)
    if len(final_brief) < 120 and len(base_brief) > len(final_brief):
        final_brief = base_brief
    if len(final_brief) < target_brief_chars and len(base_brief) >= target_brief_chars:
        final_brief = base_brief
    final_status_line = _clean_search_ui_text(ui_enhancements.get("status_line"))
    if query_class == "latest_model":
        final_status_line = (
            "Đọc nhanh lớp nội dung mới nhất bám trực tiếp vào chủ đề."
            if language == "vi"
            else "Quick read of the newest retained detail for this topic."
        )
    display_query = query
    if query_class == "latest_model":
        display_query = _normalize_text(router_queries_seed[0] if router_queries_seed else "") or (
            _normalize_text(", ".join(latest_subjects[:2])) if latest_subjects else query
        )
    analysis = {
        "query": query,
        "raw_query": query,
        "display_query": display_query,
        "language": language,
        "freshness_mode": "historical" if historical else recency_priority,
        "headline": _clean_search_ui_text(ui_enhancements.get("headline") or display_query or query),
        "status_line": final_status_line,
        "brief": final_brief,
        "answer": final_brief,
        "report": deep_report,
        "keywords": _analysis_keywords(query, compact_sources),
        "actions": _build_search_actions(language),
        "tracks": ui_enhancements.get("tracks") or _build_search_tracks_fallback(
            query,
            final_brief,
            compact_sources,
            language=language,
            historical=historical,
            query_class=query_class,
            latest_subjects=latest_subjects,
        ),
        "outputs": _build_search_outputs(query, final_brief, language=language),
        "follow_ups": ui_enhancements.get("follow_ups") or _build_search_followups_fallback(query, language=language),
        "verification_checks": ui_enhancements.get("verification_checks") or _build_search_verification_checks_fallback(query, language=language),
        "decision_paths": ui_enhancements.get("decision_paths") or _build_search_decision_paths_fallback(query, final_brief, language=language),
        "sources": compact_sources,
        "sources_drawer": compact_drawer,
        "search_meta": {
            "request_key": request_key,
            "query_class": query_class,
            "latest_subjects": latest_subjects,
            "planned_queries": planned_queries,
            "executed_queries": len(search_runs),
            "query_stats": query_stats,
            "accepted_sources": len(filtered_sources),
            "total_sources_gathered": len(deduped_raw_sources),
            "official_source_count": official_source_count,
            "target_total_sources": target_total_sources,
            "source_domains": len({_source_domain(item.get("url")) for item in filtered_sources if item.get("url")}),
            "context_chars": len(combined_context),
            "target_context_chars": target_context_chars,
            "target_sources_per_query": target_sources_per_query,
            "targets_met": targets_met,
            "insufficient_queries": insufficient_queries,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "latest_published_at": latest_dates[0] if latest_dates else "",
            "recency_priority": recency_priority,
            "used_search": True,
            "engine_info": search_engine_info,
        },
    }
    response_payload = {"success": True, "analysis": analysis}
    if cache_policy["enabled"]:
        global_cache.set(request_key, response_payload, SEARCH_JOB_TYPE)
    return response_payload


async def _run_search_job(job_id: str, payload: Dict[str, Any]) -> None:
    # Bind the active account so model-token spend is metered against it.
    try:
        import entitlements as _ent
        _ent.set_current_account(str(payload.get("__account_id__") or "guest"))
    except Exception:
        pass

    async with search_job_lock:
        job = search_jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["progress_label"] = "running"
        job["updated_at"] = time.time()

    try:
        async with search_job_lock:
            job = search_jobs.get(job_id)
            if job:
                job["progress_label"] = "Đang kích hoạt Mạng Nơ-ron..."
                job["updated_at"] = time.time()

        # Step 1: Query planning
        await asyncio.sleep(0.5) # UX Delay
        async with search_job_lock:
            job = search_jobs.get(job_id)
            if job:
                job["progress_label"] = "Đang lập kế hoạch truy vấn đa chiều..."

        result = await _compute_search_analysis(payload, job_id=job_id)
        
        async with search_job_lock:
            job = search_jobs.get(job_id)
            if not job:
                return
            if result.get("success") and result.get("analysis"):
                job["status"] = "completed"
                job["analysis"] = result["analysis"]
                job["error"] = ""
                job["progress_label"] = "completed"
                analysis = result["analysis"] or {}
                with contextlib.suppress(Exception):
                    shared_memory_hub.append_event(
                        user_id=str(payload.get("user_id") or "default_user"),
                        area="search",
                        title=str(analysis.get("display_query") or payload.get("query") or "Search"),
                        summary=str(analysis.get("brief") or analysis.get("status_line") or "Search completed."),
                        metadata={
                            "query": str(payload.get("query") or ""),
                            "status": "completed",
                            "mode": "deep_research" if bool(payload.get("deep_research")) else "search",
                            "sources": int((analysis.get("search_meta") or {}).get("accepted_sources") or 0),
                        },
                        tags=["search", str((analysis.get("freshness_mode") or "standard"))],
                    )
            else:
                job["status"] = "failed"
                job["analysis"] = None
                job["error"] = _clean_search_ui_text(result.get("error") or "Search failed")
                job["progress_label"] = "failed"
            job["updated_at"] = time.time()
    except asyncio.CancelledError:
        # User closed the tab — stop the research, keep the job record (and
        # whatever progress_label it last reached) as "cancelled" rather than
        # letting it hang at "running" forever or vanishing without a trace.
        async with search_job_lock:
            job = search_jobs.get(job_id)
            if job:
                job["status"] = "cancelled"
                job["progress_label"] = "cancelled"
                job["updated_at"] = time.time()
        raise
    except Exception as exc:
        print(f"SEARCH JOB ERROR: {exc}")
        async with search_job_lock:
            job = search_jobs.get(job_id)
            if not job:
                return
            job["status"] = "failed"
            job["analysis"] = None
            job["error"] = _clean_search_ui_text(str(exc) or "Search failed")
            job["progress_label"] = "failed"
            job["updated_at"] = time.time()
    finally:
        _cancellable_job_tasks.pop(job_id, None)


@app.post("/search/jobs")
async def create_search_job(payload: Dict[str, Any], request: Request):
    canonical_payload = _canonical_search_request_payload(payload)
    if not canonical_payload.get("query"):
        return {"success": False, "error": "Query is empty"}

    # ---- Entitlements: token budget + deep-research gating ----
    # Hard-block only on monthly token exhaustion (the real cost lever).
    # Deep Research is DOWNGRADED to basic search for non-entitled tiers so
    # free users still get a useful result instead of an error.
    account_id = "guest"
    upgrade_hint = None
    try:
        import entitlements as _ent
        account_id = _resolve_account_id(request)
        budget = _ent.check_token_budget(account_id)
        if not budget.allowed:
            return JSONResponse(
                status_code=402,
                content={
                    "success": False,
                    "error": "token_budget_exhausted",
                    "entitlement": budget.to_dict(),
                },
            )
        if bool(canonical_payload.get("deep_research")):
            feat = _ent.check_feature(account_id, "deep_research")
            if not feat.allowed:
                canonical_payload["deep_research"] = False
                upgrade_hint = feat.to_dict()
    except Exception as e:
        print(f"[ENTITLEMENTS] search gate skipped: {e}")

    request_key = _build_search_request_key(canonical_payload)
    query_class = _resolve_search_query_class(canonical_payload["query"])
    cache_policy = _search_cache_policy(canonical_payload, query_class)
    if cache_policy["enabled"]:
        cached = global_cache.get(
            request_key,
            SEARCH_JOB_TYPE,
            threshold=2.0,
            max_age_seconds=cache_policy["max_age_seconds"],
        )
        if isinstance(cached, dict) and cached.get("success") and cached.get("analysis"):
            job_id = f"search_cached_{request_key[:12]}"
            completed_job = {
                "id": job_id,
                "request_key": request_key,
                "query": canonical_payload["query"],
                "status": "completed",
                "context": canonical_payload.get("search_context") or "search",
                "analysis": cached["analysis"],
                "error": "",
                "progress_label": "completed",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            async with search_job_lock:
                search_jobs[job_id] = completed_job
            return {"success": True, "job": _search_job_public_view(completed_job, include_analysis=True), "cached": True}

    async with search_job_lock:
        _cleanup_search_jobs()
        for existing in search_jobs.values():
            if existing.get("request_key") == request_key and existing.get("status") in {"queued", "running"}:
                return {"success": True, "job": _search_job_public_view(existing, include_analysis=False), "deduped": True}

        job_id = f"search_{int(time.time() * 1000)}_{request_key[:8]}"
        job = {
            "id": job_id,
            "request_key": request_key,
            "query": canonical_payload["query"],
            "status": "queued",
            "context": canonical_payload.get("search_context") or "search",
            "analysis": None,
            "error": "",
            "progress_label": "queued",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        search_jobs[job_id] = job

    # Attribute background token spend to the resolved account (set explicitly
    # inside the task — see _run_search_job).
    canonical_payload["__account_id__"] = account_id

    _cancellable_job_tasks[job_id] = asyncio.create_task(_run_search_job(job_id, canonical_payload))
    resp = {"success": True, "job": _search_job_public_view(job, include_analysis=False), "cached": False}
    if upgrade_hint:
        resp["entitlement"] = upgrade_hint  # deep_research downgraded → nudge
    return resp


@app.get("/api/global/status")
async def get_global_status():
    """ma
    Unified endpoint for monitoring all background AI tasks across the Skemi platform.
    Used by GlobalStatus.js for notifications.
    """
    jobs = []
    now = time.time()

    def normalize_global_job_status(value: str) -> str:
        status = str(value or "").strip().lower()
        if status in {"running", "queued", "starting", "thinking", "working", "preview", "phantom"}:
            return "running"
        if status in {"completed", "complete", "success", "done"}:
            return "done"
        if status in {"failed", "error"}:
            return "error"
        if status in {"stopped", "cancelled", "canceled"}:
            return "stopped"
        return status or "idle"
    
        # 1. Computer/Browser Agents
    for sid, job in global_agent_jobs.items():
        jobs.append({
            "id": sid,
            "type": "computer" if str(getattr(job, "agent_type", "")).lower() == "computer" else "browser",
            "status": normalize_global_job_status(job.state), 
            "message": job.status_text or job.message or "",
            "description": job.goal if hasattr(job, "goal") else "",
            "updated_at": job.last_active_at if hasattr(job, "last_active_at") else now
        })
    
    # 1b. Local Computer (Phantom Mode)
    import skemi_local_computer_backend
    lc_state = skemi_local_computer_backend.local_computer_state
    if lc_state.get("mode") == "phantom" or lc_state.get("phantom_lock_active"):
        locked_name = str(lc_state.get("locked_desktop_name") or "").strip()
        if not locked_name:
            locked_index = int(lc_state.get("locked_desktop_index") or lc_state.get("target_desktop_index") or -1)
            locked_name = f"Desktop {locked_index + 1}" if locked_index >= 0 else "Phantom"
        jobs.append({
            "id": "local-phantom",
            "type": "computer",
            "status": normalize_global_job_status(lc_state.get("task_state") or lc_state.get("status") or "running"),
            "message": f"Phantom đang chạy tại {locked_name}",
            "description": str(lc_state.get("last_ai_action_desc") or "Phantom Mode đang hoạt động"),
            "updated_at": lc_state.get("last_seen_at", now)
        })


    
    # 2. AI Chat jobs
    _cleanup_ai_chat_jobs()
    for jid, job in list(ai_chat_jobs.items()):
        status = normalize_global_job_status(str(job.get("status") or ""))
        if status in {"running", "queued", "done", "error"}:
            jobs.append({
                "id": jid,
                "type": "chat",
                "status": status,
                "message": job.get("detail") or job.get("stage") or "AI Chat đang xử lý",
                "description": job.get("question") or "",
                "updated_at": job.get("updated_at", now),
            })

    # 3. Deep Research / Search Jobs
    async with search_job_lock:
        for jid, job in search_jobs.items():
            status = job.get("status", "unknown")
            if status in {"running", "queued", "completed", "error", "failed"}:
                jobs.append({
                    "id": jid,
                    "type": "search",
                    "status": normalize_global_job_status(status),
                    "message": job.get("progress_label") or job.get("query"),
                    "description": job.get("query", ""),
                    "updated_at": job.get("updated_at", now)
                })
                
    return {"success": True, "jobs": jobs}


@app.get("/search/jobs/{job_id}")
async def get_search_job(job_id: str):
    async with search_job_lock:
        _cleanup_search_jobs()
        job = search_jobs.get(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        include_analysis = job.get("status") == "completed" and bool(job.get("analysis"))
        return {"success": True, "job": _search_job_public_view(job, include_analysis=include_analysis)}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_background_job(job_id: str):
    """Stop an in-flight AI job (Search deep-research or Studio generation) the
    moment the user closes the tab — called via navigator.sendBeacon on
    beforeunload/pagehide. Actually cancels the asyncio.Task (interrupts it
    mid-await, e.g. mid LLM-call), not just a status flag; whatever the job
    already logged/produced before cancellation is left in place, matching the
    "stop the work, keep the log" behavior."""
    task = _cancellable_job_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        return {"success": True, "cancelled": True}
    return {"success": True, "cancelled": False, "detail": "Job already finished or not found."}


@app.post("/search/analyze")
async def search_analyze(payload: Dict[str, Any]):
    try:
        return await _compute_search_analysis(payload)
    except Exception as exc:
        print(f"SEARCH ANALYZE ERROR: {exc}")
        return {"success": False, "error": "Search analyze failed"}

@app.post("/notebook_chat")
async def notebook_chat(payload: NotebookRequest):
    message = _normalize_text(payload.message)
    if not message:
        return {"response": "Please enter a question.", "sources": []}

    # Consolidate multiple sources if provided
    source_content = ""
    sources_info = []
    
    # print(f"DEBUG: Notebook chat request received. Message: {message[:50]}...")
    # print(f"DEBUG: Sources size: {len(payload.sources) if payload.sources else 0}")
    
    # Store system prompt in session if provided
    if payload.systemPrompt:
        session_id = "notebook_session"
        if session_id not in chat_sessions:
            chat_sessions[session_id] = {"messages": [], "updated_at": _now()}
        chat_sessions[session_id]["system_prompt"] = payload.systemPrompt

    # Handle 'sources' list (new format)
    if payload.sources:
        for s in payload.sources:
            name = s.get("name") or s.get("title") or "Source"
            content = s.get("content") or s.get("snippet") or ""
            if content:
                source_content += f"\n--- SOURCE: {name} ---\n{content}\n"
                sources_info.append({"title": name, "url": s.get("url", ""), "type": s.get("type", "web")})
    
    # print(f"DEBUG: Final source_content length: {len(source_content)}")

    # Fallback to 'file_context' (old format)
    if not source_content and payload.file_context:
        ctx = payload.file_context
        name = ctx.get("name") or "Uploaded source"
        content = ctx.get("analysis") or ctx.get("extracted_text") or ctx.get("content") or ""
        if content:
            source_content = content
            sources_info.append({"title": name, "url": "", "type": "uploaded_file"})

    if not source_content:
        # Don't tell the AI "No source provided" in a way that makes it give up
        source_content = "" # Let it use general knowledge if empty
        strict_source = False
    else:
        # Use payload strict_source or default to False if search_mode is on
        strict_source = payload.strict_source and not payload.search_mode

    response = await _answer_question(
        question=message,
        session_id="notebook_session", 
        age_group="middle",
        source_context=source_content,
        force_search=payload.search_mode,
        deep_research=payload.search_mode,
        strict_source=strict_source,
    )

    return {
        "response": response,
        "sources": sources_info,
    }


@app.get("/model_info")
async def model_info():
    return {
        "system": "skemi-canonical-local",
        "main_model": getattr(backend, "MODEL_MAIN", ""),
        "router_model": getattr(backend, "MODEL_ROUTER", ""),
        "vision_model": getattr(backend, "MODEL_VISION", ""),
        "backend_root": str(FRONTEND_ROOT),
    }


if __name__ == "__main__":
    print("\n======================================================")
    print("    SKEMI JARVIS SYSTEM - STATUS: ONLINE")
    print("======================================================")
    print(f"Frontend: http://{SERVER_CONNECT_HOST}:{SERVER_PORT}/")
    print(f"Studio:   http://{SERVER_CONNECT_HOST}:{SERVER_PORT}/Home.html")
    print(f"Search:   http://{SERVER_CONNECT_HOST}:{SERVER_PORT}/Search.html")
    print(f"Computer: http://{SERVER_CONNECT_HOST}:{SERVER_PORT}/Computer.html")
    print(f"Chat:     http://{SERVER_CONNECT_HOST}:{SERVER_PORT}/Chat.html")
    print("\nMemory Hub: Vector Embedding Engine READY")
    print("Stealth Engine: Zero-Flash Perfect Stealth ACTIVE")
    print("Voice Engine: Whisper Proactive Feedback ACTIVE")
    print("======================================================")
    print("Jarvis: Tôi đã sẵn sàng phục vụ bạn.")
    print("======================================================\n")
    uvicorn.run("Server:app", host=SERVER_HOST, port=SERVER_PORT, reload=False, access_log=False)
