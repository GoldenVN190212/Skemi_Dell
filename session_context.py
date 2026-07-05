import os
import threading
import time
from typing import Any, Dict, List


_DEFAULT_TTL_SECONDS = int(os.getenv("SKEMI_SESSION_TTL_SECONDS", "1800"))
_DEFAULT_MAX_MESSAGES = int(os.getenv("SKEMI_SESSION_MAX_MESSAGES", "24"))

_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> float:
    return time.time()


def create_session(user_id: str, session_id: str, max_messages: int = _DEFAULT_MAX_MESSAGES) -> Dict[str, Any]:
    created = {
        "user_id": str(user_id or "default_user").strip() or "default_user",
        "session_id": str(session_id or "").strip(),
        "messages": [],
        "max_messages": max(8, int(max_messages or _DEFAULT_MAX_MESSAGES)),
        "created_at": _now(),
        "updated_at": _now(),
    }
    if not created["session_id"]:
        raise ValueError("session_id is required")

    with _lock:
        _sessions[created["session_id"]] = created
        return dict(created)


def touch_session(session_id: str) -> bool:
    sid = str(session_id or "").strip()
    if not sid:
        return False
    with _lock:
        session = _sessions.get(sid)
        if not session:
            return False
        session["updated_at"] = _now()
        return True


def append_message(session_id: str, role: str, content: str) -> bool:
    sid = str(session_id or "").strip()
    if not sid:
        return False
    message = {
        "role": str(role or "user").strip() or "user",
        "content": str(content or "").strip(),
        "timestamp": _now(),
    }
    if not message["content"]:
        return False

    with _lock:
        session = _sessions.get(sid)
        if not session:
            return False
        session["messages"].append(message)
        max_messages = max(8, int(session.get("max_messages") or _DEFAULT_MAX_MESSAGES))
        if len(session["messages"]) > max_messages:
            session["messages"] = session["messages"][-max_messages:]
        session["updated_at"] = _now()
        return True


def get_context(session_id: str) -> List[Dict[str, Any]]:
    sid = str(session_id or "").strip()
    if not sid:
        return []
    with _lock:
        session = _sessions.get(sid)
        if not session:
            return []
        return [dict(item) for item in session.get("messages", [])]


def delete_session(session_id: str) -> bool:
    sid = str(session_id or "").strip()
    if not sid:
        return False
    with _lock:
        return _sessions.pop(sid, None) is not None


def cleanup_expired_sessions(ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> int:
    ttl = max(60, int(ttl_seconds or _DEFAULT_TTL_SECONDS))
    cutoff = _now() - ttl
    deleted = 0

    with _lock:
        expired_ids = [
            sid
            for sid, session in _sessions.items()
            if float(session.get("updated_at") or 0.0) < cutoff
        ]
        for sid in expired_ids:
            _sessions.pop(sid, None)
            deleted += 1

    return deleted


def get_session_stats() -> Dict[str, Any]:
    now_ts = _now()
    with _lock:
        session_items = list(_sessions.values())
    active = len(session_items)
    if not session_items:
        return {
            "active_sessions": 0,
            "total_messages": 0,
            "oldest_session_age_seconds": 0,
            "newest_session_age_seconds": 0,
            "ttl_seconds": _DEFAULT_TTL_SECONDS,
            "max_messages_default": _DEFAULT_MAX_MESSAGES,
        }

    ages = [max(0.0, now_ts - float(item.get("updated_at") or now_ts)) for item in session_items]
    total_messages = sum(len(item.get("messages") or []) for item in session_items)
    return {
        "active_sessions": active,
        "total_messages": total_messages,
        "oldest_session_age_seconds": int(max(ages)),
        "newest_session_age_seconds": int(min(ages)),
        "ttl_seconds": _DEFAULT_TTL_SECONDS,
        "max_messages_default": _DEFAULT_MAX_MESSAGES,
    }
