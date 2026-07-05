import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_SESSION_DB = os.getenv(
    "SKEMI_AGENT_SESSION_DB",
    os.path.join(os.path.dirname(__file__), "skemi_agent_sessions.db"),
)
DEFAULT_IDLE_TTL = float(os.getenv("SKEMI_AGENT_SESSION_IDLE_TTL_SECONDS", str(15 * 60)))


def _now() -> float:
    return time.time()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return "{}"


def _json_loads(value: Any, fallback: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _ensure_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _ensure_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


@dataclass
class AgentSessionRecord:
    session_id: str
    user_id: str = "guest"  # Data isolation per user
    agent_type: str = "computer"
    mode: str = "live"
    state: str = "running"
    current_url: str = ""
    current_title: str = ""
    sticky: bool = True
    user_language: str = ""
    prompt_text: str = ""
    session_memory: List[Dict[str, Any]] = field(default_factory=list)
    decision_cache_ref: str = ""
    pending_manual_takeover: Dict[str, Any] = field(default_factory=dict)
    pending_confirmation: Dict[str, Any] = field(default_factory=dict)
    last_result: str = ""
    transport_preference: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=_now)
    last_active_at: float = field(default_factory=_now)
    expires_at: float = field(default_factory=lambda: _now() + DEFAULT_IDLE_TTL)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "AgentSessionRecord":
        return cls(
            session_id=str(row["session_id"] or ""),
            user_id=str(row["user_id"] or "guest"),
            agent_type=str(row["agent_type"] or ""),
            mode=str(row["mode"] or "live"),
            state=str(row["state"] or "running"),
            current_url=str(row["current_url"] or ""),
            current_title=str(row["current_title"] or ""),
            sticky=bool(int(row["sticky"] or 0)),
            user_language=str(row["user_language"] or ""),
            prompt_text=str(row["prompt_text"] or ""),
            session_memory=_ensure_list_of_dicts(_json_loads(row["session_memory"], [])),
            decision_cache_ref=str(row["decision_cache_ref"] or ""),
            pending_manual_takeover=_ensure_dict(_json_loads(row["pending_manual_takeover"], {})),
            pending_confirmation=_ensure_dict(_json_loads(row["pending_confirmation"], {})),
            last_result=str(row["last_result"] or ""),
            transport_preference=str(row["transport_preference"] or "auto"),
            metadata=_json_loads(row["metadata"], {}),
            created_at=float(row["created_at"] or _now()),
            last_active_at=float(row["last_active_at"] or _now()),
            expires_at=float(row["expires_at"] or (_now() + DEFAULT_IDLE_TTL)),
        )

    def to_sql_params(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["sticky"] = 1 if self.sticky else 0
        payload["session_memory"] = _json_dumps(_ensure_list_of_dicts(self.session_memory))
        payload["pending_manual_takeover"] = _json_dumps(_ensure_dict(self.pending_manual_takeover))
        payload["pending_confirmation"] = _json_dumps(_ensure_dict(self.pending_confirmation))
        payload["metadata"] = _json_dumps(_ensure_dict(self.metadata))
        return payload


class SessionStore:
    def upsert(self, record: AgentSessionRecord) -> AgentSessionRecord:
        raise NotImplementedError

    def get(self, session_id: str) -> Optional[AgentSessionRecord]:
        raise NotImplementedError

    def list_active(self, agent_type: str = "", include_done: bool = True) -> List[AgentSessionRecord]:
        raise NotImplementedError

    def touch(self, session_id: str, **fields: Any) -> Optional[AgentSessionRecord]:
        raise NotImplementedError

    def delete(self, session_id: str) -> bool:
        raise NotImplementedError

    def cleanup_expired(self) -> int:
        raise NotImplementedError


class SQLiteSessionStore(SessionStore):
    def __init__(self, db_path: str = DEFAULT_SESSION_DB, idle_ttl_seconds: float = DEFAULT_IDLE_TTL) -> None:
        self.db_path = str(db_path or DEFAULT_SESSION_DB)
        self.idle_ttl_seconds = max(60.0, float(idle_ttl_seconds or DEFAULT_IDLE_TTL))
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'guest',
                    agent_type TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    state TEXT NOT NULL,
                    current_url TEXT,
                    current_title TEXT,
                    sticky INTEGER NOT NULL DEFAULT 1,
                    user_language TEXT,
                    prompt_text TEXT,
                    session_memory TEXT,
                    decision_cache_ref TEXT,
                    pending_manual_takeover TEXT,
                    pending_confirmation TEXT,
                    last_result TEXT,
                    transport_preference TEXT,
                    metadata TEXT,
                    created_at REAL NOT NULL,
                    last_active_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_sessions_active "
                "ON agent_sessions(agent_type, state, expires_at, last_active_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_sessions_user "
                "ON agent_sessions(user_id, last_active_at)"
            )

    def upsert(self, record: AgentSessionRecord) -> AgentSessionRecord:
        record.last_active_at = max(float(record.last_active_at or 0.0), _now())
        record.expires_at = max(float(record.expires_at or 0.0), record.last_active_at + self.idle_ttl_seconds)
        payload = record.to_sql_params()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (
                    session_id, user_id, agent_type, mode, state, current_url, current_title, sticky,
                    user_language, prompt_text, session_memory, decision_cache_ref,
                    pending_manual_takeover, pending_confirmation, last_result,
                    transport_preference, metadata, created_at, last_active_at, expires_at
                ) VALUES (
                    :session_id, :user_id, :agent_type, :mode, :state, :current_url, :current_title, :sticky,
                    :user_language, :prompt_text, :session_memory, :decision_cache_ref,
                    :pending_manual_takeover, :pending_confirmation, :last_result,
                    :transport_preference, :metadata, :created_at, :last_active_at, :expires_at
                )
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    agent_type=excluded.agent_type,
                    mode=excluded.mode,
                    state=excluded.state,
                    current_url=excluded.current_url,
                    current_title=excluded.current_title,
                    sticky=excluded.sticky,
                    user_language=excluded.user_language,
                    prompt_text=excluded.prompt_text,
                    session_memory=excluded.session_memory,
                    decision_cache_ref=excluded.decision_cache_ref,
                    pending_manual_takeover=excluded.pending_manual_takeover,
                    pending_confirmation=excluded.pending_confirmation,
                    last_result=excluded.last_result,
                    transport_preference=excluded.transport_preference,
                    metadata=excluded.metadata,
                    last_active_at=excluded.last_active_at,
                    expires_at=excluded.expires_at
                """,
                payload,
            )
        return record

    def get(self, session_id: str) -> Optional[AgentSessionRecord]:
        sid = str(session_id or "").strip()
        if not sid:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sessions WHERE session_id = ?",
                (sid,),
            ).fetchone()
        return AgentSessionRecord.from_row(row) if row else None

    def list_active(self, agent_type: str = "", include_done: bool = True) -> List[AgentSessionRecord]:
        now = _now()
        clauses = ["expires_at >= ?"]
        params: List[Any] = [now]
        agent_token = str(agent_type or "").strip().lower()
        if agent_token:
            clauses.append("agent_type = ?")
            params.append(agent_token)
        if not include_done:
            clauses.append("state NOT IN ('done', 'stopped', 'error', 'closed')")
        sql = (
            "SELECT * FROM agent_sessions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY last_active_at DESC"
        )
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [AgentSessionRecord.from_row(row) for row in rows]

    def touch(self, session_id: str, **fields: Any) -> Optional[AgentSessionRecord]:
        current = self.get(session_id)
        if not current:
            return None
        current.last_active_at = _now()
        current.expires_at = current.last_active_at + self.idle_ttl_seconds
        for key, value in fields.items():
            if not hasattr(current, key):
                continue
            if value is None:
                continue
            setattr(current, key, value)
        return self.upsert(current)

    def delete(self, session_id: str) -> bool:
        sid = str(session_id or "").strip()
        if not sid:
            return False
        with self._lock, self._connect() as conn:
            result = conn.execute("DELETE FROM agent_sessions WHERE session_id = ?", (sid,))
        return bool(result.rowcount)

    def cleanup_expired(self) -> int:
        with self._lock, self._connect() as conn:
            result = conn.execute("DELETE FROM agent_sessions WHERE expires_at < ?", (_now(),))
        return int(result.rowcount or 0)
