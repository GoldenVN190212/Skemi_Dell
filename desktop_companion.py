import asyncio
import contextlib
import multiprocessing as mp
import queue
import threading
import traceback
import uuid
import logging
from typing import Any, AsyncGenerator, Callable, Dict, Optional


class DesktopCompanionError(RuntimeError):
    pass


class DesktopCompanionSessionNotFound(DesktopCompanionError):
    pass


class DesktopCompanionHost:
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
        self._alive_sessions: set[str] = set()
        self.voice_callback: Optional[Callable[[str], Any]] = None
        self.voice_event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self._voice_enabled = False

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
                target=_desktop_companion_entry,
                args=(self._command_queue, self._event_queue),
                name="SkemiDesktopCompanion",
            )
            self._process.start()
            self._start_listener_thread_locked()

    async def start_session(self, command: str, mode: str = "live", bypass_safety: bool = True, plan: Optional[Dict[str, Any]] = None, source: str = "manual", desktop_index: int = -1) -> tuple[str, AsyncGenerator[str, None]]:
        self.bind_loop()
        self.ensure_started()
        response = await self._request(
            "start",
            command=str(command or ""),
            mode=str(mode or "live"),
            bypass_safety=bool(bypass_safety),
            plan=dict(plan or {}),
            source=str(source or "manual"),
            desktop_index=int(desktop_index),
            timeout=45.0,
        )

        session_id = str(response.get("session_id") or "").strip()
        if not session_id:
            raise DesktopCompanionError("Desktop companion did not return a session_id")
        self._alive_sessions.add(session_id)
        return session_id, self._session_event_generator(session_id, self._attach_session_queue(session_id))

    async def warmup(self) -> bool:
        self.bind_loop()
        self.ensure_started()
        response = await self._request("warmup", timeout=20.0, auto_start=False)
        return bool(response.get("ready"))

    async def start_voice_control(self) -> bool:
        self.bind_loop()
        self.ensure_started()
        response = await self._request("voice_start", timeout=45.0, auto_start=False)
        self._voice_enabled = bool(response.get("voice_enabled"))
        return self._voice_enabled

    async def stop_voice_control(self) -> bool:
        self.bind_loop()
        if not self._process or not self._process.is_alive():
            self._voice_enabled = False
            return True
        response = await self._request("voice_stop", timeout=10.0, auto_start=False)
        self._voice_enabled = bool(response.get("voice_enabled"))
        return not self._voice_enabled

    async def speak(self, text: str) -> bool:
        self.bind_loop()
        self.ensure_started()
        response = await self._request("voice_speak", text=str(text or ""), timeout=8.0, auto_start=False)
        return bool(response.get("spoken"))

    def is_started(self) -> bool:
        process = self._process
        return bool(process and process.is_alive())

    def is_voice_enabled(self) -> bool:
        return bool(self._voice_enabled)

    async def stop_session(self, session_id: str) -> bool:
        response = await self._request("stop", session_id=str(session_id or "").strip(), auto_start=False)
        return bool(response.get("stopped"))

    async def close_session(self, session_id: str) -> bool:
        response = await self._request("close", session_id=str(session_id or "").strip(), auto_start=False)
        return bool(response.get("closed"))

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
        return dict(response.get("result") or {})

    async def resume_session(self, session_id: str) -> bool:
        response = await self._request("resume", session_id=str(session_id or "").strip(), auto_start=False)
        return bool(response.get("resumed"))

    def has_session(self, session_id: str) -> bool:
        sid = str(session_id or "").strip()
        return bool(sid and sid in self._alive_sessions)

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
            with contextlib.suppress(Exception):
                await self._request("shutdown", timeout=5.0, auto_start=False)
            with contextlib.suppress(Exception):
                process.join(timeout=3)
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
            with contextlib.suppress(Exception):
                event_queue.put_nowait(None)
        if listener and listener.is_alive():
            listener.join(timeout=1)
        self._handle_worker_down()

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
            raise DesktopCompanionError("Desktop companion is offline")
        request_id = uuid.uuid4().hex
        future: asyncio.Future = self._loop.create_future()  # type: ignore[union-attr]
        with self._lock:
            self._pending[request_id] = future
        try:
            self._command_queue.put(
                {
                    "type": "request",
                    "request_id": request_id,
                    "action": str(action or "").strip().lower(),
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
            name="SkemiDesktopCompanionListener",
            daemon=True,
        )
        self._listener_thread.start()

    def _post_to_loop(self, callback, *args) -> None:
        """Schedule a callback on the event loop from the listener thread, but
        tolerate shutdown: during teardown the loop may already be closed, in which
        case call_soon_threadsafe raises 'Event loop is closed'. Swallow it instead
        of letting the thread crash with a noisy traceback."""
        loop = self._loop
        if not loop:
            return
        try:
            if loop.is_closed():
                return
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            # Loop closed between the check and the call (shutdown race) — ignore.
            pass

    def _listener_loop(self) -> None:
        while not self._reader_stop.is_set():
            try:
                if not self._event_queue:
                    break
                message = self._event_queue.get(timeout=0.5)
            except queue.Empty:
                process = self._process
                if process and not process.is_alive():
                    self._post_to_loop(self._handle_worker_down)
                    break
                continue
            except (EOFError, OSError):
                self._post_to_loop(self._handle_worker_down)
                break
            if message is None:
                continue
            self._post_to_loop(self._handle_worker_message, message)

    def _attach_session_queue(self, session_id: str) -> asyncio.Queue:
        sid = str(session_id or "").strip()
        with self._lock:
            session_queue = self._session_queues.get(sid)
            if session_queue is None:
                session_queue = asyncio.Queue()
                self._session_queues[sid] = session_queue
            buffered = list(self._buffered_events.pop(sid, []))
        for chunk in buffered:
            session_queue.put_nowait(chunk)
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
                self._alive_sessions.discard(sid)

    def _handle_worker_message(self, message: Dict[str, Any]) -> None:
        msg_type = str((message or {}).get("type") or "").strip().lower()
        if msg_type == "response":
            request_id = str(message.get("request_id") or "").strip()
            future = self._pending.get(request_id)
            if future and not future.done():
                if message.get("success", True):
                    future.set_result(message)
                else:
                    error_text = str(message.get("error") or "Desktop companion request failed")
                    if message.get("error_type") == "session_not_found":
                        future.set_exception(DesktopCompanionSessionNotFound(error_text))
                    else:
                        future.set_exception(DesktopCompanionError(error_text))
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
            queue_ref = self._session_queues.get(session_id)
            if queue_ref:
                queue_ref.put_nowait(None)
            return
        if msg_type == "voice_status":
            payload = dict(message.get("payload") or {})
            if self.voice_event_callback and self._loop:
                callback = self.voice_event_callback
                self._loop.call_soon_threadsafe(lambda: asyncio.create_task(callback(payload)))
            return
        if msg_type == "voice_command":
            cmd = str(message.get("command") or "").strip()
            if self.voice_callback and cmd:
                if self._loop:
                    self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self.voice_callback(cmd)))
            return

    def _handle_worker_down(self) -> None:
        with self._lock:
            pending = list(self._pending.values())
            session_queues = list(self._session_queues.values())
            self._pending.clear()
            self._session_queues.clear()
            self._buffered_events.clear()
            self._alive_sessions.clear()
        for future in pending:
            if not future.done():
                future.set_exception(DesktopCompanionError("Desktop companion went offline"))
        for session_queue in session_queues:
            session_queue.put_nowait(None)


async def _worker_handle_request(message: Dict[str, Any], event_queue: mp.Queue) -> bool:
    import desktop_agent

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

    def _require_session():
        session_id = str(message.get("session_id") or "").strip()
        session = desktop_agent.active_sessions.get(session_id)
        if not session:
            raise DesktopCompanionSessionNotFound("Active desktop session not found")
        return session

    try:
        if action == "warmup":
            _respond(True, ready=True)
            return False
        if action == "voice_start":
            enabled = _worker_start_voice(event_queue)
            _respond(True, voice_enabled=bool(enabled))
            return False
        if action == "voice_stop":
            _worker_stop_voice()
            _respond(True, voice_enabled=False)
            return False
        if action == "voice_speak":
            spoken = _worker_speak(str(message.get("text") or ""))
            _respond(True, spoken=bool(spoken))
            return False
        if action == "start":
            command = str(message.get("command") or "").strip()
            mode = str(message.get("mode") or "live").strip().lower() or "live"
            bypass_safety = bool(message.get("bypass_safety", True))
            plan = message.get("plan") if isinstance(message.get("plan"), dict) else {}
            source = str(message.get("source") or "manual").strip().lower()
            desktop_index = int(message.get("desktop_index") if message.get("desktop_index") is not None else -1)
            session_id, event_generator = await desktop_agent.run_desktop_agent(command, mode=mode, bypass_safety=bypass_safety, plan=plan, source=source, desktop_index=desktop_index)

            if event_generator is not None:
                asyncio.create_task(_worker_forward_session(session_id, event_generator, event_queue))
            _respond(True, session_id=session_id)
            return False
        if action == "stop":
            session_id = str(message.get("session_id") or "").strip()
            stopped = desktop_agent.stop_session(session_id)
            _respond(True, session_id=session_id, stopped=bool(stopped))
            return False
        if action == "close":
            session_id = str(message.get("session_id") or "").strip()
            closed = desktop_agent.close_session(session_id)
            _respond(True, session_id=session_id, closed=bool(closed))
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
            elif manual_action == "reveal":
                success = bool(session.reveal_target_window()) if hasattr(session, "reveal_target_window") else False
                result = {"ok": success}
            else:
                raise DesktopCompanionError(f"Unsupported manual action: {manual_action}")
            _respond(True, session_id=session.session_id, result=result)
            return False
        if action == "resume":
            session = _require_session()
            resumed = bool(session.resume_manual_takeover()) if hasattr(session, "resume_manual_takeover") else False
            _respond(True, session_id=session.session_id, resumed=resumed)
            return False
        if action == "snapshot":
            session = _require_session()
            payload = await session.runtime_snapshot()
            _respond(True, session_id=session.session_id, payload=payload)
            return False
        if action == "shutdown":
            _respond(True, shutting_down=True)
            return True
        _respond(False, error=f"Unsupported action: {action}")
    except DesktopCompanionSessionNotFound as exc:
        _respond(False, error=str(exc), error_type="session_not_found")
    except Exception as exc:
        traceback.print_exc()
        _respond(False, error=str(exc), error_type=type(exc).__name__)
    return False


async def _worker_forward_session(session_id: str, event_generator: AsyncGenerator[str, None], event_queue: mp.Queue) -> None:
    if event_generator is None:
        return
    try:
        async for chunk in event_generator:
            event_queue.put(
                {
                    "type": "event",
                    "session_id": session_id,
                    "chunk": chunk,
                }
            )
    except Exception:
        traceback.print_exc()
    finally:
        event_queue.put({"type": "session_closed", "session_id": session_id})


def _desktop_companion_entry(command_queue: mp.Queue, event_queue: mp.Queue) -> None:
    asyncio.run(_desktop_worker_main(command_queue, event_queue))


_worker_voice_engine = None


def _worker_start_voice(event_queue: mp.Queue) -> bool:
    global _worker_voice_engine
    if _worker_voice_engine is not None and getattr(_worker_voice_engine, "is_listening", False):
        event_queue.put({
            "type": "voice_status",
            "payload": {"phase": "listening", "transcript": ""},
        })
        return True
    try:
        from skemi_voice_engine import SkemiVoiceEngine
        _worker_voice_engine = SkemiVoiceEngine()

        def on_voice_event(phase, payload):
            safe_payload = dict(payload or {})
            safe_payload["phase"] = str(phase or safe_payload.get("phase") or "status")
            event_queue.put({
                "type": "voice_status",
                "payload": safe_payload,
            })

        def on_voice_command(text):
            logging.info(f"[VOICE] Voice command detected: {text}")
            event_queue.put({
                "type": "voice_status",
                "payload": {"phase": "dispatching", "transcript": str(text or "")},
            })
            event_queue.put({
                "type": "voice_command",
                "command": text,
            })

        if _worker_voice_engine.start(on_voice_command, event_callback=on_voice_event):
            pass # Removed noisy print per user request
            return True
        print("[VOICE] Skemi Voice Control could not be started (missing dependencies or model).")
    except Exception as e:
        print(f"[VOICE] Failed to initialize voice engine: {e}")
    return False


def _worker_stop_voice() -> None:
    global _worker_voice_engine
    if _worker_voice_engine is not None:
        with contextlib.suppress(Exception):
            _worker_voice_engine.stop()


def _worker_speak(text: str) -> bool:
    global _worker_voice_engine
    spoken_text = str(text or "").strip()
    if not spoken_text:
        return False
    try:
        if _worker_voice_engine is None:
            from skemi_voice_engine import SkemiVoiceEngine
            _worker_voice_engine = SkemiVoiceEngine()
        _worker_voice_engine.speak(spoken_text)
        return True
    except Exception as exc:
        print(f"[VOICE] TTS failed: {exc}")
        return False


async def _desktop_worker_main(command_queue: mp.Queue, event_queue: mp.Queue) -> None:
    loop = asyncio.get_running_loop()
    while True:
        message = await asyncio.to_thread(command_queue.get)
        if message is None:
            continue
        should_exit = await _worker_handle_request(message, event_queue)
        if should_exit:
            break


desktop_companion_host = DesktopCompanionHost()
