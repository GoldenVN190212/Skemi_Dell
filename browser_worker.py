import asyncio
import contextlib
import json
import multiprocessing as mp
import os
import queue
import threading
import traceback
import uuid
from typing import Any, AsyncGenerator, Dict, Optional


class BrowserWorkerError(RuntimeError):
    pass


class BrowserWorkerSessionNotFound(BrowserWorkerError):
    pass


class BrowserWorkerHost:
    def __init__(self) -> None:
        self._ctx = mp.get_context("spawn")
        self._command_queue: Optional[mp.Queue] = None
        self._event_queue: Optional[mp.Queue] = None
        self._process: Optional[mp.Process] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._reader_stop = threading.Event()
        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._session_queues: Dict[str, asyncio.Queue] = {}
        self._buffered_events: Dict[str, list[str]] = {}
        self._closed_sessions: set[str] = set()
        self._alive_sessions: set[str] = set()
        self._warmed = False

    def bind_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._loop = loop or asyncio.get_running_loop()

    def ensure_started(self) -> None:
        with self._lock:
            if self._process and self._process.is_alive():
                if not self._listener_thread or not self._listener_thread.is_alive():
                    self._start_listener_thread_locked()
                return

            self._command_queue = self._ctx.Queue()
            self._event_queue = self._ctx.Queue()
            self._reader_stop.clear()
            self._process = self._ctx.Process(
                target=_browser_worker_entry,
                args=(self._command_queue, self._event_queue),
                name="SkemiBrowserWorker",
            )
            self._process.start()
            self._start_listener_thread_locked()

    def has_session(self, session_id: str) -> bool:
        sid = str(session_id or "").strip()
        return bool(sid and sid in self._alive_sessions)

    async def start_session(
        self,
        command: str,
        *,
        reuse_session_id: str = "",
        sticky: bool = True,
        browser_shell: str = "virtual",
        bypass_safety: bool = False,
    ) -> tuple[str, AsyncGenerator[str, None]]:
        self.bind_loop()
        self.ensure_started()
        if not self._warmed:
            with contextlib.suppress(Exception):
                await self.warmup()
        response = await self._request(
            "start",
            command=str(command or ""),
            reuse_session_id=str(reuse_session_id or "").strip(),
            sticky=bool(sticky),
            browser_shell=str(browser_shell or "virtual").strip() or "virtual",
            bypass_safety=bool(bypass_safety),
            timeout=45.0,
        )
        session_id = str(response.get("session_id") or "").strip()
        if not session_id:
            raise BrowserWorkerError("Browser worker did not return a session_id")
        self._alive_sessions.add(session_id)
        session_queue = self._attach_session_queue(session_id)
        return session_id, self._session_event_generator(session_id, session_queue)

    async def ensure_idle_session(
        self,
        *,
        reuse_session_id: str = "",
        sticky: bool = True,
        browser_shell: str = "virtual",
        bypass_safety: bool = False,
    ) -> Dict[str, Any]:
        self.bind_loop()
        self.ensure_started()
        if not self._warmed:
            with contextlib.suppress(Exception):
                await self.warmup()
        response = await self._request(
            "ensure_idle",
            reuse_session_id=str(reuse_session_id or "").strip(),
            sticky=bool(sticky),
            browser_shell=str(browser_shell or "virtual").strip() or "virtual",
            bypass_safety=bool(bypass_safety),
            timeout=45.0,
        )
        session_id = str(response.get("session_id") or "").strip()
        if not session_id:
            raise BrowserWorkerError("Browser worker did not return a session_id")
        self._alive_sessions.add(session_id)
        return dict(response)

    async def stop_session(self, session_id: str) -> bool:
        response = await self._request("stop", session_id=str(session_id or "").strip(), auto_start=False)
        return bool(response.get("stopped"))

    async def confirm_session(self, session_id: str, approved: bool) -> bool:
        response = await self._request(
            "confirm",
            session_id=str(session_id or "").strip(),
            approved=bool(approved),
            auto_start=False,
        )
        return bool(response.get("resolved"))

    async def manual_action(
        self,
        session_id: str,
        action: str,
        *,
        x: Optional[float] = None,
        y: Optional[float] = None,
        text: Optional[str] = None,
        key: Optional[str] = None,
        direction: Optional[str] = None,
        click_count: int = 1,
    ) -> Dict[str, Any]:
        response = await self._request(
            "manual_action",
            session_id=str(session_id or "").strip(),
            manual_action=str(action or "").strip().lower(),
            x=x,
            y=y,
            text=text,
            key=key,
            direction=direction,
            click_count=max(1, int(click_count or 1)),
            auto_start=False,
        )
        result = dict(response.get("result") or {})
        if "url" in response and "url" not in result:
            result["url"] = response.get("url")
        return result

    async def resume_session(self, session_id: str) -> bool:
        response = await self._request("resume", session_id=str(session_id or "").strip(), auto_start=False)
        return bool(response.get("resumed"))

    async def get_tabs_payload(self, session_id: str) -> Dict[str, Any]:
        response = await self._request("tabs", session_id=str(session_id or "").strip(), auto_start=False)
        return dict(response.get("payload") or {})

    async def open_tab(self, session_id: str, url: str = "about:blank") -> Dict[str, Any]:
        response = await self._request(
            "tab_open",
            session_id=str(session_id or "").strip(),
            url=str(url or "about:blank"),
            auto_start=False,
        )
        return dict(response.get("payload") or {})

    async def switch_tab(self, session_id: str, tab_id: str) -> Dict[str, Any]:
        response = await self._request(
            "tab_switch",
            session_id=str(session_id or "").strip(),
            tab_id=str(tab_id or "").strip(),
            auto_start=False,
        )
        return dict(response.get("payload") or {})

    async def close_tab(self, session_id: str, tab_id: str) -> Dict[str, Any]:
        response = await self._request(
            "tab_close",
            session_id=str(session_id or "").strip(),
            tab_id=str(tab_id or "").strip(),
            auto_start=False,
        )
        return dict(response.get("payload") or {})

    async def get_session_snapshot(self, session_id: str) -> Dict[str, Any]:
        response = await self._request(
            "snapshot",
            session_id=str(session_id or "").strip(),
            auto_start=False,
        )
        return dict(response.get("payload") or {})

    async def shutdown(self) -> None:
        self.bind_loop()
        process = self._process
        if process and process.is_alive():
            try:
                await self._request("shutdown", timeout=5.0, auto_start=False)
            except Exception:
                pass
            try:
                process.join(timeout=3)
            except Exception:
                pass
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)

        self._reader_stop.set()
        with self._lock:
            event_queue = self._event_queue
            listener = self._listener_thread
            self._process = None
            self._command_queue = None
            self._event_queue = None
            self._listener_thread = None
        if event_queue is not None:
            try:
                event_queue.put_nowait(None)
            except Exception:
                pass
        if listener and listener.is_alive():
            listener.join(timeout=1)
        self._handle_worker_down()

    async def warmup(self) -> bool:
        self.bind_loop()
        self.ensure_started()
        response = await self._request("warmup", timeout=45.0)
        self._warmed = bool(response.get("warmed"))
        return self._warmed

    async def _request(
        self,
        action: str,
        *,
        timeout: float = 12.0,
        auto_start: bool = True,
        **payload: Any,
    ) -> Dict[str, Any]:
        self.bind_loop()
        if auto_start:
            self.ensure_started()
        if not self._process or not self._process.is_alive() or not self._command_queue:
            raise BrowserWorkerError("Browser worker is offline")

        request_id = uuid.uuid4().hex
        future: asyncio.Future = self._loop.create_future()  # type: ignore[union-attr]
        with self._lock:
            self._pending[request_id] = future

        try:
            self._command_queue.put(
                {
                    "type": "request",
                    "request_id": request_id,
                    "action": str(action or "").strip(),
                    **payload,
                }
            )
            response = await asyncio.wait_for(future, timeout=timeout)
            return dict(response or {})
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def _start_listener_thread_locked(self) -> None:
        if self._listener_thread and self._listener_thread.is_alive():
            return
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            name="SkemiBrowserWorkerListener",
            daemon=True,
        )
        self._listener_thread.start()

    def _attach_session_queue(self, session_id: str) -> asyncio.Queue:
        sid = str(session_id or "").strip()
        with self._lock:
            self._closed_sessions.discard(sid)
            session_queue = self._session_queues.get(sid)
            if session_queue is None:
                session_queue = asyncio.Queue()
                self._session_queues[sid] = session_queue
            buffered = list(self._buffered_events.pop(sid, []))
            closed = False

        for chunk in buffered:
            session_queue.put_nowait(chunk)
        if closed:
            session_queue.put_nowait(None)
        return session_queue

    async def _session_event_generator(self, session_id: str, session_queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        sid = str(session_id or "").strip()
        try:
            while True:
                chunk = await session_queue.get()
                if chunk is None:
                    break
                yield str(chunk)
        finally:
            with self._lock:
                if self._session_queues.get(sid) is session_queue:
                    self._session_queues.pop(sid, None)
                self._closed_sessions.discard(sid)

    def _listener_loop(self) -> None:
        while not self._reader_stop.is_set():
            try:
                if not self._event_queue:
                    break
                message = self._event_queue.get(timeout=0.5)
            except queue.Empty:
                process = self._process
                if process and not process.is_alive():
                    if self._loop:
                        self._loop.call_soon_threadsafe(self._handle_worker_down)
                    break
                continue
            except (EOFError, OSError):
                if self._loop:
                    self._loop.call_soon_threadsafe(self._handle_worker_down)
                break

            if message is None:
                continue

            if self._loop:
                self._loop.call_soon_threadsafe(self._handle_worker_message, message)

    def _handle_worker_message(self, message: Dict[str, Any]) -> None:
        msg_type = str((message or {}).get("type") or "").strip().lower()
        if msg_type == "response":
            request_id = str(message.get("request_id") or "").strip()
            future = self._pending.get(request_id)
            if future and not future.done():
                if message.get("success", True):
                    future.set_result(message)
                else:
                    error_text = str(message.get("error") or "Browser worker request failed")
                    if message.get("error_type") == "session_not_found":
                        future.set_exception(BrowserWorkerSessionNotFound(error_text))
                    else:
                        future.set_exception(BrowserWorkerError(error_text))
            return

        if msg_type == "event":
            session_id = str(message.get("session_id") or "").strip()
            chunk = str(message.get("chunk") or "")
            if not session_id or not chunk:
                return
            queue_ref = self._session_queues.get(session_id)
            if queue_ref:
                queue_ref.put_nowait(chunk)
            else:
                self._buffered_events.setdefault(session_id, []).append(chunk)
            return

        if msg_type == "session_closed":
            session_id = str(message.get("session_id") or "").strip()
            if not session_id:
                return
            self._alive_sessions.discard(session_id)
            self._closed_sessions.add(session_id)
            queue_ref = self._session_queues.get(session_id)
            if queue_ref:
                queue_ref.put_nowait(None)
            return

    def _handle_worker_down(self) -> None:
        with self._lock:
            pending = list(self._pending.values())
            session_queues = list(self._session_queues.values())
            self._pending.clear()
            self._session_queues.clear()
            self._buffered_events.clear()
            self._alive_sessions.clear()
            self._closed_sessions.clear()
            self._warmed = False

        for future in pending:
            if not future.done():
                future.set_exception(BrowserWorkerError("Browser worker went offline"))
        for session_queue in session_queues:
            session_queue.put_nowait(None)


async def _worker_handle_request(message: Dict[str, Any], event_queue: mp.Queue) -> bool:
    import computer_agent

    request_id = str(message.get("request_id") or "").strip()
    action = str(message.get("action") or "").strip().lower()

    def _respond(success: bool, **payload: Any) -> None:
        event_queue.put(
            {
                "type": "response",
                "request_id": request_id,
                "success": bool(success),
                **payload,
            }
        )

    def _require_session() -> "computer_agent.BrowserAgentSession":
        session_id = str(message.get("session_id") or "").strip()
        session = computer_agent.active_sessions.get(session_id)
        if not session:
            raise BrowserWorkerSessionNotFound("Active browser session not found")
        return session

    try:
        if action == "warmup":
            try:
                computer_agent._ensure_playwright()
            except Exception:
                pass
            _respond(True, warmed=True)
            return False

        if action == "start":
            command = str(message.get("command") or "").strip()
            reuse_session_id = str(message.get("reuse_session_id") or "").strip()
            sticky = bool(message.get("sticky", True))
            browser_shell = str(message.get("browser_shell") or "virtual").strip() or "virtual"
            bypass_safety = bool(message.get("bypass_safety", False))
            session_id, event_generator = await computer_agent.run_browser_agent(
                command,
                reuse_session_id=reuse_session_id,
                sticky=sticky,
                browser_shell=browser_shell,
                bypass_safety=bypass_safety,
            )
            asyncio.create_task(_worker_forward_session(session_id, event_generator, event_queue))
            _respond(True, session_id=session_id)
            return False

        if action == "ensure_idle":
            reuse_session_id = str(message.get("reuse_session_id") or "").strip()
            sticky = bool(message.get("sticky", True))
            browser_shell = str(message.get("browser_shell") or "virtual").strip() or "virtual"
            bypass_safety = bool(message.get("bypass_safety", False))
            payload = await computer_agent.ensure_browser_ready(
                reuse_session_id=reuse_session_id,
                sticky=sticky,
                browser_shell=browser_shell,
                bypass_safety=bypass_safety,
            )
            _respond(True, session_id=str(payload.get("session_id") or ""), payload=payload)
            return False

        if action == "stop":
            session_id = str(message.get("session_id") or "").strip()
            stopped = computer_agent.stop_session(session_id)
            _respond(True, session_id=session_id, stopped=bool(stopped))
            return False

        if action == "confirm":
            session = _require_session()
            approved = bool(message.get("approved"))
            resolved = session.resolve_confirmation(approved)
            _respond(True, session_id=session.session_id, approved=approved, resolved=bool(resolved))
            return False

        if action == "manual_action":
            session = _require_session()
            manual_action = str(message.get("manual_action") or "").strip().lower()
            if manual_action == "click":
                result = await session.manual_click(
                    int(message.get("x") or 0),
                    int(message.get("y") or 0),
                    click_count=max(1, int(message.get("click_count") or 1)),
                )
            elif manual_action == "scroll":
                result = await session.manual_scroll(str(message.get("direction") or "down"))
            elif manual_action == "press":
                result = await session.manual_press(str(message.get("key") or ""))
            elif manual_action == "type":
                result = await session.manual_type(str(message.get("text") or ""))
            else:
                raise BrowserWorkerError("Unsupported manual action")
            _respond(True, session_id=session.session_id, result=result, url=getattr(session, "current_url", ""))
            return False

        if action == "resume":
            session = _require_session()
            resumed = session.resume_manual_takeover()
            _respond(True, session_id=session.session_id, resumed=bool(resumed))
            return False

        if action == "tabs":
            session = _require_session()
            payload = await session.get_tabs_payload()
            _respond(True, session_id=session.session_id, payload=payload)
            return False

        if action == "tab_open":
            session = _require_session()
            payload = await session.open_tab(str(message.get("url") or "about:blank"))
            _respond(True, session_id=session.session_id, payload=payload)
            return False

        if action == "tab_switch":
            session = _require_session()
            payload = await session.switch_tab(str(message.get("tab_id") or ""))
            _respond(True, session_id=session.session_id, payload=payload)
            return False

        if action == "tab_close":
            session = _require_session()
            payload = await session.close_tab(str(message.get("tab_id") or ""))
            _respond(True, session_id=session.session_id, payload=payload)
            return False

        if action == "snapshot":
            session = _require_session()
            payload = await session.runtime_snapshot()
            _respond(True, session_id=session.session_id, payload=payload)
            return False

        if action == "shutdown":
            _respond(True, shutdown=True)
            return True

        raise BrowserWorkerError(f"Unsupported browser worker action: {action}")
    except BrowserWorkerSessionNotFound as exc:
        _respond(False, error=str(exc), error_type="session_not_found")
        return False
    except Exception as exc:
        _respond(False, error=f"{type(exc).__name__}: {exc}")
        return False


async def _worker_forward_session(session_id: str, event_generator: AsyncGenerator[str, None], event_queue: mp.Queue) -> None:
    sid = str(session_id or "").strip()
    try:
        async for chunk in event_generator:
            event_queue.put({"type": "event", "session_id": sid, "chunk": str(chunk)})
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        error_payload = json.dumps({"message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
        error_chunk = (
            "event: error\n"
            f"data: {error_payload}\n\n"
        )
        event_queue.put({"type": "event", "session_id": sid, "chunk": error_chunk})
    finally:
        event_queue.put({"type": "session_closed", "session_id": sid})


async def _browser_worker_main(command_queue: mp.Queue, event_queue: mp.Queue) -> None:
    while True:
        message = await asyncio.to_thread(command_queue.get)
        if message is None:
            continue
        should_stop = await _worker_handle_request(dict(message or {}), event_queue)
        if should_stop:
            break


def _browser_worker_entry(command_queue: mp.Queue, event_queue: mp.Queue) -> None:
    os.environ.setdefault("SKEMI_COMPUTER_HEADLESS", "1")
    os.environ.setdefault("SKEMI_COMPUTER_NATIVE_WINDOW", "0")
    try:
        asyncio.run(_browser_worker_main(command_queue, event_queue))
    except KeyboardInterrupt:
        pass
    except Exception:
        event_queue.put(
            {
                "type": "response",
                "request_id": "__worker_boot__",
                "success": False,
                "error": traceback.format_exc(limit=4),
            }
        )


browser_worker_host = BrowserWorkerHost()
