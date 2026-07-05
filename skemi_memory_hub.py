import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


DEFAULT_MEMORY_DB = "skemi_memory_stream.db"


class SkemiMemoryHub:
    def __init__(self, db_path: str = DEFAULT_MEMORY_DB) -> None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(base_dir, db_path)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    area TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    embedding BLOB,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_events_user_time "
                "ON memory_events(user_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_events_area_time "
                "ON memory_events(area, created_at DESC)"
            )

    def append_event(
        self,
        *,
        user_id: str = "default_user",
        area: str,
        title: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        clean_area = str(area or "").strip().lower()
        clean_title = str(title or "").strip()
        clean_summary = str(summary or "").strip()
        clean_user = str(user_id or "default_user").strip() or "default_user"
        if not clean_area or not clean_title or not clean_summary:
            return None

        payload = {
            "user_id": clean_user,
            "area": clean_area,
            "title": clean_title[:240],
            "summary": clean_summary[:4000],
            "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
            "tags_json": json.dumps(list(tags or []), ensure_ascii=False),
            "created_at": float(time.time()),
        }
        # v1.0: Generate vector embedding via Ollama
        embedding = self._get_embedding(f"{clean_title} {clean_summary}")
        embedding_blob = None
        if embedding:
            import array
            embedding_blob = array.array('f', embedding).tobytes()

        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO memory_events (user_id, area, title, summary, metadata_json, tags_json, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["user_id"],
                    payload["area"],
                    payload["title"],
                    payload["summary"],
                    payload["metadata_json"],
                    payload["tags_json"],
                    embedding_blob,
                    payload["created_at"],
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        payload["id"] = event_id
        payload["metadata"] = metadata or {}
        payload["tags"] = list(tags or [])
        return payload

    def get_recent(
        self,
        *,
        user_id: str = "default_user",
        areas: Optional[List[str]] = None,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        clean_user = str(user_id or "default_user").strip() or "default_user"
        cap = max(1, min(int(limit or 12), 50))
        area_list = [str(item or "").strip().lower() for item in (areas or []) if str(item or "").strip()]
        sql = (
            "SELECT id, user_id, area, title, summary, metadata_json, tags_json, created_at "
            "FROM memory_events WHERE user_id = ?"
        )
        params: List[Any] = [clean_user]
        if area_list:
            placeholders = ", ".join("?" for _ in area_list)
            sql += f" AND area IN ({placeholders})"
            params.extend(area_list)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(cap)

        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def clear(self, *, user_id: str = "default_user") -> int:
        clean_user = str(user_id or "default_user").strip() or "default_user"
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM memory_events WHERE user_id = ?", (clean_user,))
            return int(cursor.rowcount or 0)

    def build_context_window(
        self,
        *,
        user_id: str = "default_user",
        limit: int = 8,
        max_chars: int = 2200,
        areas: Optional[List[str]] = None,
    ) -> str:
        events = self.get_recent(user_id=user_id, areas=areas, limit=limit)
        lines: List[str] = []
        total = 0
        for event in reversed(events):
            metadata = event.get("metadata") or {}
            detail_bits: List[str] = []
            for key in ("query", "url", "mode", "status"):
                value = str(metadata.get(key) or "").strip()
                if value:
                    detail_bits.append(f"{key}={value}")
            detail = f" ({', '.join(detail_bits)})" if detail_bits else ""
            line = f"- [{event['area']}] {event['title']}: {event['summary']}{detail}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(lines).strip()

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Fetch vector embedding from local Ollama service."""
        try:
            import httpx
            with httpx.Client(timeout=10.0) as client:
                # Use a fast embedding model, fallback to llama3.2 if needed
                for model in ["nomic-embed-text", "llama3.2:1b", "all-minilm"]:
                    try:
                        resp = client.post(
                            "http://127.0.0.1:11434/api/embeddings",
                            json={"model": model, "prompt": text},
                        )
                        if resp.status_code == 200:
                            return resp.json().get("embedding")
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def search_semantic(self, query: str, limit: int = 5, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """Vector-based semantic search for relevant memories."""
        query_vec = self._get_embedding(query)
        if not query_vec:
            return self.get_recent(user_id=user_id, limit=limit)

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, area, title, summary, metadata_json, tags_json, embedding, created_at "
                "FROM memory_events WHERE user_id = ? AND embedding IS NOT NULL",
                (user_id,)
            ).fetchall()

        if not rows:
            return []

        import array
        import math

        results = []
        for row in rows:
            try:
                stored_blob = row["embedding"]
                stored_vec = array.array('f', stored_blob).tolist()
                
                # Cosine Similarity
                dot = sum(a * b for a, b in zip(query_vec, stored_vec))
                norm_a = math.sqrt(sum(a * a for a in query_vec))
                norm_b = math.sqrt(sum(b * b for b in stored_vec))
                score = dot / (norm_a * norm_b) if norm_a and norm_b else 0
                
                results.append((score, self._row_to_dict(row)))
            except Exception:
                continue

        results.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in results[:limit]]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        metadata = {}
        tags: List[str] = []
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        try:
            parsed_tags = json.loads(row["tags_json"] or "[]")
            if isinstance(parsed_tags, list):
                tags = [str(item) for item in parsed_tags]
        except Exception:
            tags = []
        return {
            "id": int(row["id"]),
            "user_id": str(row["user_id"]),
            "area": str(row["area"]),
            "title": str(row["title"]),
            "summary": str(row["summary"]),
            "metadata": metadata,
            "tags": tags,
            "created_at": float(row["created_at"]),
        }
