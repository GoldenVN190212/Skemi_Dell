import asyncio
import base64
import contextlib
import json
import time
import uuid
from io import BytesIO
from typing import Any, Awaitable, Callable, Dict, Optional

import numpy as np
from PIL import Image

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from aiortc.rtcrtpsender import RTCRtpSender
    from av import VideoFrame
    AIORTC_AVAILABLE = True
except Exception:  # pragma: no cover - fallback path
    RTCPeerConnection = None  # type: ignore[assignment]
    RTCSessionDescription = None  # type: ignore[assignment]
    VideoStreamTrack = object  # type: ignore[assignment]
    RTCRtpSender = None  # type: ignore[assignment]
    VideoFrame = None  # type: ignore[assignment]
    AIORTC_AVAILABLE = False


def _frame_signature(image_payload: str) -> str:
    text = str(image_payload or "")
    if not text:
        return ""
    if len(text) <= 256:
        return text
    return f"{len(text)}:{text[:128]}:{text[-64:]}"


def _decode_image_to_rgb(payload: str) -> np.ndarray:
    encoded = str(payload or "")
    if encoded.startswith("data:"):
        encoded = encoded.split(",", 1)[-1]
    binary = base64.b64decode(encoded)
    with Image.open(BytesIO(binary)) as image:
        return np.array(image.convert("RGB"))


class BrowserSurfaceTrack(VideoStreamTrack):
    kind = "video"

    def __init__(
        self,
        job: Any,
        fps: float = 30.0,
        frame_refresh_cb: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> None:
        super().__init__()
        self.job = job
        target_fps = max(20.0, min(60.0, float(fps or 30.0)))
        self.frame_interval = 1.0 / target_fps
        self._last_frame_clock = 0.0
        self._last_signature = ""
        self._last_rgb: Optional[np.ndarray] = None
        self._fallback_rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
        self._frame_refresh_cb = frame_refresh_cb
        self._refresh_interval = max(0.045, min(0.09, self.frame_interval * 2.0))
        self._last_refresh_attempt = 0.0
        self._last_frame_update = 0.0
        self._decode_sleep = max(0.004, min(0.012, self.frame_interval * 0.35))
        self._video_frame_queue: Optional[asyncio.Queue] = None
        if hasattr(job, "surface_video_frames"):
             self._video_frame_queue = job.surface_video_frames
        self._decode_task = asyncio.create_task(self._decode_loop(), name=f"skemi-webrtc-decode-{id(self)}")

    async def recv(self) -> VideoFrame:
        if self.readyState != "live":
            raise asyncio.CancelledError
        now = time.perf_counter()
        delay = self.frame_interval - (now - self._last_frame_clock)
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_frame_clock = time.perf_counter()
        pts, time_base = await self.next_timestamp()
        if self._last_rgb is None and self._frame_refresh_cb and (time.perf_counter() - self._last_refresh_attempt) >= self._refresh_interval:
            self._last_refresh_attempt = time.perf_counter()
            with contextlib.suppress(Exception):
                await self._frame_refresh_cb()
        
        # Priority 1: Direct VideoFrame from high-performance capture
        if self._video_frame_queue:
            try:
                frame = await asyncio.wait_for(self._video_frame_queue.get(), timeout=0.01)
                if frame:
                    frame.pts = pts
                    frame.time_base = time_base
                    return frame
            except: pass

        # Priority 2: Fallback to decoded RGB frame
        rgb = self._get_rgb_frame()
        frame = VideoFrame.from_ndarray(rgb, format="rgb24")
        frame = frame.reformat(format="yuv420p")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    async def _decode_loop(self) -> None:
        while self.readyState == "live":
            payload = str(getattr(self.job, "latest_image", "") or "")
            now = time.perf_counter()
            if (not payload or (now - self._last_frame_update) >= self._refresh_interval) and self._frame_refresh_cb:
                if (now - self._last_refresh_attempt) >= self._refresh_interval:
                    self._last_refresh_attempt = now
                    with contextlib.suppress(Exception):
                        await self._frame_refresh_cb()
                    payload = str(getattr(self.job, "latest_image", "") or "")
            signature = _frame_signature(payload)
            if payload and signature != self._last_signature:
                try:
                    self._last_rgb = await asyncio.to_thread(_decode_image_to_rgb, payload)
                    self._last_signature = signature
                    self._last_frame_update = time.perf_counter()
                except Exception:
                    pass
            await asyncio.sleep(self._decode_sleep)

    def _get_rgb_frame(self) -> np.ndarray:
        return self._last_rgb if self._last_rgb is not None else self._fallback_rgb

    def stop(self) -> None:
        if self._decode_task and not self._decode_task.done():
            self._decode_task.cancel()
        super().stop()


class BrowserWebRTCHub:
    def __init__(self) -> None:
        self._peers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def shutdown(self) -> None:
        async with self._lock:
            peer_ids = list(self._peers.keys())
        for peer_id in peer_ids:
            await self.close_peer(peer_id)

    async def close_peer(self, peer_id: str) -> None:
        async with self._lock:
            peer = self._peers.pop(str(peer_id or "").strip(), None)
        if not peer:
            return
        for task in list(peer.get("tasks") or []):
            task.cancel()
            with contextlib.suppress(Exception):
                await task
        queue_ref = peer.get("surface_queue")
        job = peer.get("job")
        if job and queue_ref and queue_ref in getattr(job, "surface_subscribers", []):
            with contextlib.suppress(ValueError):
                job.surface_subscribers.remove(queue_ref)
        track = peer.get("track")
        if track:
            with contextlib.suppress(Exception):
                track.stop()
        pc = peer.get("pc")
        if pc:
            with contextlib.suppress(Exception):
                await pc.close()

    async def create_answer(
        self,
        session_id: str,
        offer_sdp: str,
        offer_type: str,
        job: Any,
        frame_refresh_cb: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> Dict[str, Any]:
        if not AIORTC_AVAILABLE:
            raise RuntimeError("aiortc is not available")
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        peer_id = uuid.uuid4().hex
        pc = RTCPeerConnection()
        track = BrowserSurfaceTrack(job, frame_refresh_cb=frame_refresh_cb)
        pc.addTrack(track)
        await self._prefer_h264(pc)
        meta_channel = pc.createDataChannel("surface-meta", ordered=True)
        surface_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        getattr(job, "surface_subscribers", []).append(surface_queue)

        async def _metadata_loop() -> None:
            last_state_seq = -1
            try:
                if hasattr(job, "surface_snapshot_packets"):
                    for packet in job.surface_snapshot_packets():
                        await self._send_metadata(meta_channel, packet)
                if hasattr(job, "state_snapshot"):
                    snapshot = job.state_snapshot()
                    last_state_seq = int(snapshot.get("state_seq") or -1)
                    await self._send_metadata(meta_channel, {"type": "session_state", **snapshot})
                while True:
                    try:
                        packet = await asyncio.wait_for(surface_queue.get(), timeout=0.12)
                    except asyncio.TimeoutError:
                        if frame_refresh_cb is not None:
                            with contextlib.suppress(Exception):
                                await frame_refresh_cb()
                        if hasattr(job, "state_snapshot"):
                            snapshot = job.state_snapshot()
                            state_seq = int(snapshot.get("state_seq") or -1)
                            if state_seq != last_state_seq:
                                last_state_seq = state_seq
                                await self._send_metadata(meta_channel, {"type": "session_state", **snapshot})
                        continue
                    if packet is None:
                        break
                    await self._send_metadata(meta_channel, packet)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

        async def _handle_connection_state() -> None:
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                await self.close_peer(peer_id)

        @pc.on("connectionstatechange")
        async def _on_connectionstatechange() -> None:
            await _handle_connection_state()

        offer = RTCSessionDescription(sdp=str(offer_sdp or ""), type=str(offer_type or "offer"))
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        metadata_task = asyncio.create_task(_metadata_loop(), name=f"skemi-browser-meta-{peer_id}")
        async with self._lock:
            self._peers[peer_id] = {
                "pc": pc,
                "track": track,
                "job": job,
                "surface_queue": surface_queue,
                "tasks": [metadata_task],
                "session_id": sid,
                "created_at": time.time(),
            }

        return {
            "peer_id": peer_id,
            "sdp": str(pc.localDescription.sdp),
            "type": str(pc.localDescription.type),
        }

    async def _prefer_h264(self, pc: RTCPeerConnection) -> None:
        if RTCRtpSender is None:
            return
        capabilities = RTCRtpSender.getCapabilities("video")
        if not capabilities:
            return
        codecs = [codec for codec in capabilities.codecs if codec.mimeType.lower() == "video/h264"]
        if not codecs:
            return
        for transceiver in pc.getTransceivers():
            if getattr(transceiver, "kind", "") == "video":
                with contextlib.suppress(Exception):
                    transceiver.setCodecPreferences(codecs)

    async def _send_metadata(self, channel: Any, packet: Dict[str, Any]) -> None:
        if getattr(channel, "readyState", "") != "open":
            for _ in range(20):
                await asyncio.sleep(0.05)
                if getattr(channel, "readyState", "") == "open":
                    break
            else:
                return
        payload = dict(packet or {})
        if payload.get("type") == "screenshot":
            payload.pop("image", None)
            payload["type"] = "screenshot_meta"
        channel.send(json.dumps(payload, ensure_ascii=False))


browser_webrtc_hub = BrowserWebRTCHub()
