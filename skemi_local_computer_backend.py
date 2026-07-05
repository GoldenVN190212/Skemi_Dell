import asyncio
import base64
import contextlib
import json
import os
import re
import time
import subprocess
import unicodedata
import zipfile
from io import BytesIO
from typing import AsyncGenerator, Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import desktop_companion
import desktop_agent
from desktop_agent import _phantom_debug

SKEMI_COMPANION_VERSION = "0.2.0"
PHANTOM_BOOTSTRAP_URL = "/api/local-computer/bootstrap/package"
PHANTOM_SHORT_SETUP_ERROR = "Phantom setup is required on this computer."
PHANTOM_UPDATE_URL = os.getenv("SKEMI_PHANTOM_UPDATE_URL", PHANTOM_BOOTSTRAP_URL)
PHANTOM_DRIVER_INF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivers", "phantom-display", "skemi_phantom_display.inf")

# Local Computer DNA State (Real-time Mirroring)
local_computer_state = {
    "status": "connected", # idle, starting, running, connected, done, stopped, error
    "task_state": "stopped",
    "stream_state": "ended",
    "voice_state": "standby",
    "route": "chat",
    "tasks": [],
    "current_task_index": -1,
    "automation_mode": "blocked",
    "surface_mode": "live",
    "local_state": "live_viewer",
    "requires_consent": False,
    "consent_reason": "",
    "final_result": "",
    "connected": True,
    "mode": "live",
    "target_desktop_index": -1, # legacy UI marker; Phantom uses a real virtual display
    "locked_desktop_index": -1,
    "locked_desktop_name": "",
    "locked_desktop_guid": "",
    "phantom_lock_token": "",
    "phantom_lock_active": False,
    "phantom_lock_last_heartbeat": 0.0,
    "preview_only": False,
    "machine_label": "This device",
    "companion_version": SKEMI_COMPANION_VERSION,
    "last_seen_at": 0.0,
    "session_id": "",
    "stream_url": "",
    "notes": ["Sẵn sàng kết nối Local Computer."],
    "pending_confirmation": {},
    "frame_version": 0,
    "target_window_hwnd": 0,
    "target_window_title": "",
    "target_window_class": "",
    "consent_granted": False,
    "voice_control_enabled": False,
    "voice_phase": "standby",
    "voice_transcript": "",
    "speech_to_text_engine": f"faster-whisper {os.getenv('SKEMI_WHISPER_MODEL', 'small')} vi",
    "text_to_speech_engine": "edge-tts vi-VN-NamMinhNeural",
    "last_ai_action_desc": "",
    "is_voice_session": False,
    "voice_route": "auto",
    "voice_chat_session_id": "local-computer-voice",
    "workspace_kind": "virtual_display",
    "workspace_ready": False,
    "setup_state": "missing_driver",
    "driver_status": "missing",
    "driver_version": "",
    "driver_provider": "",
    "bootstrap_required": True,
    "bootstrap_url": PHANTOM_BOOTSTRAP_URL,
    "pairing_status": "paired_localhost",
    "pairing_required": False,
    "display_id": "",
    "workspace_label": "",
    "public_display_label": "",
    "display_role": "",
    "isolation_level": "",
    "display_bounds": {},
    "launch_policy": "vision-only GUI control on the locked desktop",
    "last_launch_error": "",
    "last_launch_error_code": "",
    "cursor_overlay": {},
    "update_state": "current",
    "update_available": False,
    "update_required": False,
    "latest_companion_version": "",
    "latest_driver_version": "",
    "update_url": PHANTOM_UPDATE_URL,
    "update_size_mb": "",
    "update_requires_admin": True,
    "update_message": "",
    "driver_package_present": False,
    "driver_package_path": PHANTOM_DRIVER_INF_PATH,
}

_local_events = []
_local_lock = asyncio.Lock()
_local_task = None
_phantom_release_task = None
_phantom_heartbeat_task = None
_latest_frame = b""
_voice_chat_history: list[dict[str, str]] = []
_last_voice_progress_spoken_at = 0.0
_last_voice_progress_text = ""
PHANTOM_HEARTBEAT_TIMEOUT_SECONDS = 10.0

class LocalComputerConnectRequest(BaseModel):
    consent: bool = True
    machine_label: Optional[str] = "This device"
    companion_version: Optional[str] = "built-in"

class LocalComputerRunRequest(BaseModel):
    command: str
    plan: Optional[Dict[str, Any]] = None
    mode: Optional[str] = "live"
    consent: bool = True
    source: Optional[str] = "manual"
    desktop_index: Optional[int] = -1 # legacy UI marker; ignored for Phantom display selection
    lock_token: Optional[str] = ""

class LocalComputerModeRequest(BaseModel):
    mode: str
    desktop_index: Optional[int] = -1
    lock_token: Optional[str] = ""
    preserve_lock: Optional[bool] = True
    use_virtual_display: Optional[bool] = False

class LocalComputerPhantomReleaseRequest(BaseModel):
    lock_token: Optional[str] = ""
    session_id: Optional[str] = ""

class LocalComputerPhantomLockRequest(BaseModel):
    desktop_index: Optional[int] = -1
    desktop_guid: Optional[str] = ""
    lock_token: Optional[str] = ""
    preserve_lock: Optional[bool] = True

class LocalComputerPhantomHeartbeatRequest(BaseModel):
    lock_token: Optional[str] = ""
    session_id: Optional[str] = ""

def _normalize_mode(mode: str) -> str:
    m = str(mode or "live").lower().strip()
    if m in {"live", "mirror", "dual_control"}: return "live"
    if m in {"background", "phantom", "ghost"}: return "phantom"
    if m in {"isolated", "super", "super_phantom"}: return "super"
    return "live"

def _agent_mode(mode: str) -> str:
    m = _normalize_mode(mode)
    if m == "live": return "live"
    if m == "super": return "super"
    return "phantom"

def _int_or(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "required"}


def _phantom_debug_enabled() -> bool:
    return _env_flag("SKEMI_DEBUG_PHANTOM", False)


def _version_tuple(value: Any) -> tuple[int, ...]:
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
    size_raw = os.getenv("SKEMI_PHANTOM_UPDATE_SIZE_MB", "").strip()
    message = os.getenv("SKEMI_PHANTOM_UPDATE_MESSAGE", "").strip()
    if available and not message:
        message = "A Phantom update is available. Skemi will wait for user approval before installing it."
    return {
        "update_state": state,
        "update_available": available,
        "update_required": required,
        "latest_companion_version": latest_companion,
        "latest_driver_version": latest_driver,
        "update_url": os.getenv("SKEMI_PHANTOM_UPDATE_URL", PHANTOM_UPDATE_URL).strip() or PHANTOM_BOOTSTRAP_URL,
        "update_size_mb": size_raw,
        "update_requires_admin": _env_flag("SKEMI_PHANTOM_UPDATE_REQUIRES_ADMIN", True),
        "update_message": message,
    }

def _phantom_driver_package_info() -> Dict[str, Any]:
    configured = os.getenv("SKEMI_PHANTOM_DRIVER_INF", "").strip()
    path = configured or ""
    if not path:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        bundled_dir = os.path.join(base_dir, "Skemi_Virtual_Display")
        for root, _dirs, files in os.walk(bundled_dir):
            for filename in files:
                if filename.lower() == "usbmmidd.inf":
                    path = os.path.join(root, filename)
                    break
            if path:
                break
    path = path or PHANTOM_DRIVER_INF_PATH
    installer_path = os.path.join(os.path.dirname(path), "deviceinstaller64.exe") if path else ""
    return {
        "driver_package_present": bool(path and os.path.exists(path)),
        "driver_package_path": path,
        "driver_installer_present": bool(installer_path and os.path.exists(installer_path)),
        "driver_installer_path": installer_path if installer_path and os.path.exists(installer_path) else "",
    }

def _normalize_workspace_status(status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = dict(status or {})
    
    # v6.0 OVERHAUL: Absolute Priority on Secondary Monitors
    # If any non-primary monitor is detected as enabled, we MUST consider it ready.
    ready = bool(data.get("workspace_ready", False) or data.get("enabled", False) or data.get("driver_status") == "active")
    
    workspace_kind = str(data.get("workspace_kind") or "virtual_display")
    setup_state = str(data.get("setup_state") or ("ready" if ready else "missing_driver"))
    driver_status = str(data.get("driver_status") or ("ready" if ready else "missing"))
    bootstrap_required = bool(data.get("bootstrap_required", not ready))
    
    if workspace_kind == "window_capture":
        ready = True
        setup_state = "ready"
        driver_status = str(data.get("driver_status") or "not_required")
        bootstrap_required = False
        data["update_required"] = False
        data["update_available"] = False
        data.setdefault("display_id", "app_window")
        data.setdefault("display_role", "window_capture")
        data.setdefault("isolation_level", "window_only")
        data.setdefault("setup_message", "Phantom streams the locked desktop.")
        data.setdefault("launch_policy", "vision-only GUI control on the locked desktop")
    
    update_info = _phantom_update_status(str(data.get("driver_version") or ""))
    for key, value in update_info.items():
        data.setdefault(key, value)
        
    package_info = _phantom_driver_package_info()
    for key, value in package_info.items():
        data.setdefault(key, value)
        
    if bool(data.get("update_required")):
        setup_state = "update_available"
        bootstrap_required = True
    elif bool(data.get("update_available")) and setup_state == "ready":
        setup_state = "update_available"

    default_launch_error = ""
    if ready:
        default_launch_error = ""
    elif setup_state == "missing_companion":
        default_launch_error = "Phantom needs the local companion."
    elif setup_state == "missing_driver":
        default_launch_error = "Phantom driver not found. Please run the setup again."
    elif setup_state == "driver_installed_no_monitor":
        default_launch_error = "Driver installed but Phantom Desktop is not active. Try restarting."
    elif setup_state == "driver_error":
        driver_err = str(data.get("driver_error") or "")
        default_launch_error = f"Phantom driver error: {driver_err}" if driver_err else "Phantom driver reported a Windows error. Check Device Manager and run setup again."
    else:
        default_launch_error = "Phantom Desktop missing."

    data.update({
        "workspace_kind": workspace_kind,
        "workspace_ready": ready,
        "setup_state": setup_state,
        "driver_status": driver_status,
        "driver_version": str(data.get("driver_version") or ""),
        "driver_provider": str(data.get("driver_provider") or ""),
        "bootstrap_required": bootstrap_required,
        "bootstrap_url": str(data.get("bootstrap_url") or ("" if workspace_kind == "window_capture" else PHANTOM_BOOTSTRAP_URL)),
        "pairing_status": str(data.get("pairing_status") or "paired_localhost"),
        "pairing_required": bool(data.get("pairing_required", False)),
        "display_id": str(data.get("display_id") or ""),
        "workspace_label": str(data.get("workspace_label") or _workspace_label()),
        "public_display_label": str(data.get("public_display_label") or _workspace_label()),
        "display_role": str(data.get("display_role") or ""),
        "isolation_level": str(data.get("isolation_level") or ""),
        "display_bounds": dict(data.get("display_bounds") or {}),
        "safe_for_phantom": bool(data.get("safe_for_phantom", ready)),
        "capture_probe_ok": bool(data.get("capture_probe_ok", ready)),
        "capture_probe_black": bool(data.get("capture_probe_black", False)),
        "setup_required": bool(data.get("setup_required", not ready)) if not ready else False,
        "install_available": bool(data.get("install_available", data.get("driver_package_present", False))),
        "install_message": str(data.get("install_message") or ("" if ready else ("Kích hoạt màn hình ảo ngay (Driver đã có sẵn)." if data.get("driver_package_present") else "Thiết lập Driver màn hình ảo."))),
        "launch_policy": str(data.get("launch_policy") or "Vision-only GUI control (Chế độ Phantom)"),
        "last_launch_error": str(data.get("last_launch_error") or default_launch_error),
        "last_launch_error_code": str(data.get("last_launch_error_code") or ""),
        "setup_message": str(data.get("setup_message") or ("" if ready else "Run Skemi Bootstrap as Administrator once, then press Check again.")),
        "update_url": "" if workspace_kind == "window_capture" else str(data.get("update_url") or PHANTOM_UPDATE_URL),
        "update_size_mb": str(data.get("update_size_mb") or ""),
        "update_requires_admin": False if workspace_kind == "window_capture" else bool(data.get("update_requires_admin", True)),
        "update_message": str(data.get("update_message") or ""),
        "driver_package_present": bool(data.get("driver_package_present", False)),
        "driver_package_path": str(data.get("driver_package_path") or PHANTOM_DRIVER_INF_PATH),
    })
    return data

def _copy_workspace_status_to_state(status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = _normalize_workspace_status(status)
    for key in (
        "workspace_kind",
        "workspace_ready",
        "setup_state",
        "driver_status",
        "driver_version",
        "driver_provider",
        "bootstrap_required",
        "bootstrap_url",
        "pairing_status",
        "pairing_required",
        "display_id",
        "workspace_label",
        "public_display_label",
        "display_role",
        "isolation_level",
        "display_bounds",
        "safe_for_phantom",
        "capture_probe_ok",
        "capture_probe_black",
        "setup_required",
        "install_available",
        "install_message",
        "launch_policy",
        "last_launch_error",
        "last_launch_error_code",
        "setup_message",
        "update_state",
        "update_available",
        "update_required",
        "latest_companion_version",
        "latest_driver_version",
        "update_url",
        "update_size_mb",
        "update_requires_admin",
        "update_message",
        "driver_package_present",
        "driver_package_path",
        "driver_installer_present",
        "driver_installer_path",
    ):
        local_computer_state[key] = data.get(key)
    return data

def _short_phantom_setup_message(status: Optional[Dict[str, Any]] = None) -> str:
    data = _normalize_workspace_status(status)
    setup_state = str(data.get("setup_state") or "")
    if bool(data.get("update_required")):
        return "Phantom update required."
    if bool(data.get("update_available")) or setup_state == "update_available":
        return "Phantom update available."
    if setup_state == "missing_companion":
        return "Phantom needs the local companion."
    if setup_state == "missing_driver":
        return "Phantom is not installed on this computer."
    if setup_state == "driver_installed_no_monitor":
        return "Phantom Desktop is not active."
    if setup_state == "driver_error":
        return "Driver Phantom lỗi."
    return PHANTOM_SHORT_SETUP_ERROR


def _cancel_phantom_release_task() -> None:
    global _phantom_release_task
    task = _phantom_release_task
    if task and not task.done():
        task.cancel()
    _phantom_release_task = None


def _cancel_phantom_heartbeat_task() -> None:
    global _phantom_heartbeat_task
    task = _phantom_heartbeat_task
    if task and not task.done():
        task.cancel()
    _phantom_heartbeat_task = None


def _phantom_desktop_name(index: int) -> str:
    safe_index = _int_or(index, -1)
    if desktop_agent and safe_index >= 0:
        with contextlib.suppress(Exception):
            for item in desktop_agent._get_all_desktops_sync():
                if _int_or(item.get("index"), -1) == safe_index:
                    name = str(item.get("name") or "").strip()
                    if name:
                        return name
    return f"Desktop {safe_index + 1}" if safe_index >= 0 else ""


def _workspace_label(index: Optional[int] = None) -> str:
    idx = _int_or(index if index is not None else local_computer_state.get("locked_desktop_index"), -1)
    if idx >= 0:
        return _phantom_desktop_name(idx) or f"Desktop {idx + 1}"
    return "Phantom Desktop"


def _public_workspace_status(status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = _normalize_workspace_status(status)
    label = str(data.get("workspace_label") or data.get("public_display_label") or _workspace_label() or "Phantom Desktop")
    data["workspace_label"] = label
    data["public_display_label"] = label
    for key in ("setup_message", "last_launch_error", "launch_policy"):
        if key in data:
            data[key] = re.sub(r"\\\\?\.\\DISPLAY\d+", "", str(data.get(key) or ""), flags=re.IGNORECASE)
            data[key] = data[key].replace("Phantom display", "Phantom Desktop").replace("Phantom Display", "Phantom Desktop").strip()
    if not _phantom_debug_enabled():
        data["display_id"] = ""
        data["driver_provider"] = ""
        data.pop("displays", None)
        data.pop("allowed_driver_tokens", None)
    return data


def _local_state_from_values(mode: str, status: str, workspace_ready: bool, locked: bool) -> str:
    mode = _normalize_mode(mode)
    status = str(status or "").lower()
    if mode != "phantom":
        return "live_viewer"
    if not workspace_ready:
        return "phantom_blocked"
    if locked:
        if status == "running":
            return "phantom_running"
        return "phantom_locked"
    return "phantom_ready"


def _phantom_desktop_payload() -> Dict[str, Any]:
    """v6.7: Report Windows Task View desktops, not physical monitors. Virtual display is the display backend."""
    if not desktop_agent:
        return {
            "success": True,
            "count": 1,
            "current": 0,
            "desktops": [
                {"id": "desktop_0", "name": "Desktop 1", "index": 0, "is_current": True, "eligible": True}
            ]
        }
    
    try:
        # Check if virtual display is ready (this is the backend)
        workspace_status = _jarvis_display_status(force=False)
        if not workspace_status.get("workspace_ready"):
            # Virtual display not ready - return error
            return {
                "success": False,
                "error": "phantom_setup_required",
                "count": 0,
                "desktops": [],
                "message": workspace_status.get("last_launch_error") or "Phantom Desktop không sẵn sàng. Cài driver rồi kiểm tra lại.",
                "locked_desktop_index": -1,
                "locked_desktop_name": "",
                "locked_desktop_guid": "",
            }
        
        # Virtual display is ready - get Windows Task View desktops
        try:
            virtual_desktops = desktop_agent._get_all_desktops_sync()
            current_idx = desktop_agent._get_current_virtual_desktop_index_sync()
            
            desktops = [
                {
                    **d,
                    "guid": str(d.get("guid") or d.get("id") or ""),
                    "eligible": True,  # All desktops are eligible for Phantom lock
                    "is_current": bool(d.get("is_current", False)),
                }
                for d in virtual_desktops
            ]
            
            return {
                "success": True,
                "count": len(desktops),
                "current": current_idx,
                "desktops": desktops,
                "locked_desktop_index": _int_or(local_computer_state.get("locked_desktop_index"), -1),
                "locked_desktop_name": str(local_computer_state.get("locked_desktop_name") or ""),
                "locked_desktop_guid": str(local_computer_state.get("locked_desktop_guid") or ""),
            }
        except Exception as e:
            _phantom_debug(f"[PHANTOM PAYLOAD] Failed to get Task View desktops: {e}")
            # Fallback to single default desktop
            return {
                "success": True,
                "count": 1,
                "current": 0,
                "desktops": [
                    {"id": "desktop_0", "name": "Desktop 1", "index": 0, "is_current": True, "eligible": True}
                ],
                "locked_desktop_index": _int_or(local_computer_state.get("locked_desktop_index"), -1),
                "locked_desktop_name": str(local_computer_state.get("locked_desktop_name") or ""),
            }
    except Exception as e:
        _phantom_debug(f"[PHANTOM PAYLOAD] Error: {e}")
        return {
            "success": False,
            "error": str(e),
            "desktops": [],
            "locked_desktop_index": -1,
            "locked_desktop_name": "",
        }


def _resolve_desktop_index_from_guid(desktop_guid: str) -> int:
    guid = str(desktop_guid or "").strip().lower()
    if not guid or not desktop_agent:
        return -1
    try:
        for item in desktop_agent._get_all_desktops_sync():
            if str(item.get("guid") or item.get("id") or "").strip().lower() == guid:
                return _int_or(item.get("index"), -1)
    except Exception:
        return -1
    return -1


def _set_phantom_lock(desktop_index: int, lock_token: str = "", desktop_guid: str = "") -> Dict[str, Any]:
    index = _int_or(desktop_index, -1)
    guid_hint = str(desktop_guid or "").strip()
    if index < 0 and guid_hint:
        index = _resolve_desktop_index_from_guid(guid_hint)
    if index < 0:
        return {"locked_desktop_index": -1, "locked_desktop_name": "", "locked_desktop_guid": ""}
    
    # Use GUID-based locking
    if guid_hint and desktop_agent and hasattr(desktop_agent, 'lock_to_existing_desktop'):
        lock_result = desktop_agent.lock_to_existing_desktop(guid_hint)
        if not lock_result.get("success"):
            return {"locked_desktop_index": -1, "locked_desktop_name": "", "locked_desktop_guid": ""}
        guid = lock_result.get("guid", guid_hint)
        name = lock_result.get("name", "")
        index = _resolve_desktop_index_from_guid(guid) if _resolve_desktop_index_from_guid(guid) >= 0 else index
    elif desktop_agent and hasattr(desktop_agent, 'lock_to_desktop'):
        lock_result = desktop_agent.lock_to_desktop(index)
        if not lock_result.get("success"):
            return {"locked_desktop_index": -1, "locked_desktop_name": "", "locked_desktop_guid": ""}
        guid = lock_result.get("guid", "")
        name = lock_result.get("name", "")
    else:
        # Fallback to old method
        name = _phantom_desktop_name(index)
        guid = ""
    
    local_computer_state["target_desktop_index"] = index
    local_computer_state["locked_desktop_index"] = index
    local_computer_state["locked_desktop_name"] = name
    local_computer_state["locked_desktop_guid"] = guid
    if desktop_agent:
        desktop_agent._target_desktop_index = index
    token = str(lock_token or local_computer_state.get("phantom_lock_token") or "").strip()
    if token:
        local_computer_state["phantom_lock_token"] = token
    local_computer_state["phantom_lock_active"] = True
    local_computer_state["phantom_lock_last_heartbeat"] = time.time()
    local_computer_state["mode"] = "phantom"
    local_computer_state["surface_mode"] = "phantom"
    local_computer_state["local_state"] = "phantom_locked"
    local_computer_state["workspace_label"] = name or _workspace_label(index)
    local_computer_state["public_display_label"] = local_computer_state["workspace_label"]
    local_computer_state["stream_url"] = local_computer_state.get("stream_url") or "/api/local-computer/mjpeg"
    local_computer_state["last_seen_at"] = time.time()
    return {"locked_desktop_index": index, "locked_desktop_name": name, "locked_desktop_guid": guid}


def _clear_phantom_lock_fields() -> None:
    local_computer_state["target_desktop_index"] = -1
    local_computer_state["locked_desktop_index"] = -1
    local_computer_state["locked_desktop_name"] = ""
    local_computer_state["locked_desktop_guid"] = ""
    local_computer_state["phantom_lock_active"] = False
    local_computer_state["phantom_lock_token"] = ""
    local_computer_state["phantom_lock_last_heartbeat"] = 0.0
    local_computer_state["local_state"] = "live_viewer"
    if desktop_agent:
        desktop_agent._target_desktop_index = -1


def _schedule_phantom_heartbeat_release(token: str, session_id: str = "") -> None:
    global _phantom_heartbeat_task
    token = str(token or "").strip()
    if not token:
        return
    _cancel_phantom_heartbeat_task()

    async def release_if_stale(expected_token: str, expected_session_id: str) -> None:
        try:
            await asyncio.sleep(PHANTOM_HEARTBEAT_TIMEOUT_SECONDS)
            async with _local_lock:
                current_token = str(local_computer_state.get("phantom_lock_token") or "").strip()
                current_session = str(local_computer_state.get("session_id") or "").strip()
                last_beat = float(local_computer_state.get("phantom_lock_last_heartbeat") or 0.0)
                if current_token != expected_token:
                    return
                if expected_session_id and current_session and current_session != expected_session_id:
                    return
                if time.time() - last_beat < PHANTOM_HEARTBEAT_TIMEOUT_SECONDS:
                    return
                await _stop_current_session_locked("Browser session heartbeat expired; Phantom lock released.")
                local_computer_state["mode"] = "live"
                local_computer_state["surface_mode"] = "live"
                _clear_phantom_lock_fields()
                local_computer_state["preview_only"] = False
                local_computer_state["notes"] = _mode_notes("live", connected=True, running=False)
                if desktop_agent:
                    with contextlib.suppress(Exception):
                        desktop_agent.agent_module_update_mode("live")
        except asyncio.CancelledError:
            return

    _phantom_heartbeat_task = asyncio.create_task(
        release_if_stale(token, session_id),
        name="skemi-phantom-heartbeat-release",
    )


def _jarvis_display_status(force: bool = False) -> Dict[str, Any]:
    try:
        if desktop_agent and hasattr(desktop_agent, "agent_module_jarvis_display_status"):
            status = desktop_agent.agent_module_jarvis_display_status(force=force)
            return _normalize_workspace_status(status or {})
    except Exception as exc:
        return _normalize_workspace_status({
            "workspace_kind": "virtual_display",
            "workspace_ready": False,
            "setup_state": "driver_error",
            "driver_status": "error",
            "bootstrap_required": True,
            "bootstrap_url": PHANTOM_BOOTSTRAP_URL,
            "display_id": "",
            "display_role": "",
            "isolation_level": "",
            "display_bounds": {},
            "last_launch_error": "Phantom driver error.",
            "setup_message": f"Phantom Desktop status unavailable: {exc}",
            "launch_policy": "vision-only GUI control on the locked desktop",
        })
    return _normalize_workspace_status({
        "workspace_kind": "virtual_display",
        "workspace_ready": False,
        "setup_state": "missing_companion",
        "driver_status": "unknown",
        "bootstrap_required": True,
        "bootstrap_url": PHANTOM_BOOTSTRAP_URL,
        "display_id": "",
        "display_role": "",
        "isolation_level": "",
        "display_bounds": {},
        "last_launch_error": "Phantom local companion is not ready.",
        "setup_message": "Start the Skemi Local Companion, then retry Phantom.",
        "launch_policy": "vision-only GUI control on the locked desktop",
    })


def _set_jarvis_display_block(reason: str, workspace_status: Optional[Dict[str, Any]] = None, *, route: str = "computer_task") -> Dict[str, Any]:
    status = _copy_workspace_status_to_state(workspace_status or {})
    message = str(reason or status.get("last_launch_error") or _short_phantom_setup_message(status)).strip()
    if "virtual display" in message.lower() or "display missing" in message.lower() or "driver" in message.lower():
        message = _short_phantom_setup_message(status)
    local_computer_state["workspace_ready"] = False
    local_computer_state["last_launch_error"] = message
    local_computer_state["last_launch_error_code"] = str(status.get("last_launch_error_code") or status.get("setup_state") or "phantom_not_ready")
    local_computer_state["status"] = "error"
    local_computer_state["task_state"] = "blocked"
    local_computer_state["stream_state"] = "blocked"
    local_computer_state["automation_mode"] = "blocked"
    local_computer_state["local_state"] = "phantom_blocked"
    local_computer_state["surface_mode"] = "phantom"
    local_computer_state["mode"] = "phantom"
    local_computer_state["route"] = route
    local_computer_state["tasks"] = []
    local_computer_state["current_task_index"] = -1
    local_computer_state["final_result"] = message
    local_computer_state["last_ai_action_desc"] = message
    local_computer_state["notes"] = [message]
    local_computer_state["session_id"] = local_computer_state.get("session_id") or "phantom-pending"
    local_computer_state["stream_url"] = "/api/local-computer/mjpeg"
    local_computer_state["preview_only"] = True
    local_computer_state["requires_consent"] = False
    local_computer_state["pending_confirmation"] = {}
    local_computer_state["last_seen_at"] = time.time()
    _append_event({"type": "final_result", "route": route, "result": message, "task_state": "blocked"})
    return _local_payload()


def _mode_notes(mode: str, connected: bool = False, running: bool = False) -> list[str]:
    if not connected:
        return ["Local Computer Companion is not connected.", "Open Skemi on this device to start."]
    mode = _normalize_mode(mode)
    if mode == "live":
        if running:
            return [
                "Live Control is showing your current desktop.",
                "AI acts via background ghost-input — your cursor and focus stay yours.",
            ]
        return [
            "Live Control ready.",
            "AI operates your current desktop via ghost-input — no cursor/focus stealing, no Phantom driver.",
        ]
    if mode == "phantom":
        desktop_name = _workspace_label()
        if running:
            return [
                f"AI controlling {desktop_name}.",
                "AI sees the full locked desktop and uses GUI clicks, typing, keys, and scroll.",
                "The web stream is only a viewer.",
            ]
        return [
            f"Phantom ready for {desktop_name}.",
            "AI control requires a safe locked virtual display.",
        ]
    return ["Unknown mode."]


async def warm_start() -> bool:
    """Start the built-in desktop companion early so Computer.html is ready immediately."""
    try:
        desktop_companion.desktop_companion_host.ensure_started()
        with contextlib.suppress(Exception):
            await desktop_companion.desktop_companion_host.warmup()
        mode = _normalize_mode(str(local_computer_state.get("mode") or "live"))
        local_computer_state["connected"] = True
        if str(local_computer_state.get("status") or "") in {"idle", "", "connected"}:
            local_computer_state["status"] = "connected"
        local_computer_state["machine_label"] = "This device"
        local_computer_state["companion_version"] = SKEMI_COMPANION_VERSION
        local_computer_state["last_seen_at"] = time.time()
        local_computer_state["notes"] = _mode_notes(mode, connected=True, running=False)
        # Warm the companion at startup, but do not open the microphone or speak
        # until the user explicitly enables voice from the UI.
        auto_voice = str(os.getenv("SKEMI_AUTO_START_VOICE", "0")).strip().lower() not in {"0", "false", "off", "no"}
        if auto_voice:
            with contextlib.suppress(Exception):
                enabled = await desktop_companion.desktop_companion_host.start_voice_control()
                local_computer_state["voice_control_enabled"] = bool(enabled)
                local_computer_state["voice_phase"] = "listening" if enabled else "standby"
                local_computer_state["voice_transcript"] = ""
                if enabled:
                    local_computer_state["last_ai_action_desc"] = "Voice mode is listening. Say Skemi, then speak your command."
                    local_computer_state["notes"] = ["Voice mode is listening. Say Skemi, then speak your command."] + local_computer_state["notes"][:2]
        return True
    except Exception as exc:
        local_computer_state["connected"] = False
        local_computer_state["status"] = "error"
        local_computer_state["notes"] = [f"Local Computer warm start failed: {exc}"]
        return False


def _append_event(event: Dict[str, Any]):
    event = dict(event or {})
    if not _phantom_debug_enabled():
        for key in ("display_id", "display_bounds", "displays", "allowed_driver_tokens", "hardware_id"):
            event.pop(key, None)
        if "driver_provider" in event:
            event["driver_provider"] = ""
    for key, value in list(event.items()):
        if isinstance(value, str):
            cleaned = re.sub(r"\\\\?\.\\DISPLAY\d+", "", value, flags=re.IGNORECASE)
            cleaned = cleaned.replace("Phantom display", "Phantom Desktop").replace("Phantom Display", "Phantom Desktop").strip()
            event[key] = cleaned
    event["ts"] = time.time()
    _local_events.append(event)
    if len(_local_events) > 100:
        _local_events.pop(0)
    local_computer_state["last_event"] = event


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    with contextlib.suppress(Exception):
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        with contextlib.suppress(Exception):
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else {}
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        with contextlib.suppress(Exception):
            parsed = json.loads(raw[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    with contextlib.suppress(Exception):
        return max(0.0, min(1.0, float(value)))
    return default


def _normalize_router_plan(plan: Dict[str, Any], command: str) -> Dict[str, Any]:
    allowed_routes = {"chat", "computer_task", "clarify", "consent_required", "stop"}
    route = str(plan.get("route") or plan.get("intent") or "").strip().lower()
    if route in {"computer", "task", "desktop", "local_computer"}:
        route = "computer_task"
    if route not in allowed_routes:
        route = "clarify"

    tasks: List[Dict[str, Any]] = []
    raw_tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or item.get("target") or f"Task {index + 1}").strip()
        goal = str(item.get("goal") or item.get("command") or item.get("instruction") or title).strip()
        modality = str(item.get("modality") or item.get("route") or "unknown").strip().lower()
        if modality not in {"web", "native_app", "file", "system", "unknown"}:
            modality = "unknown"
        risk = str(item.get("safety_risk") or item.get("risk") or "none").strip().lower()
        if risk not in {"none", "low", "medium", "high"}:
            risk = "medium" if risk else "none"
        tasks.append({
            "id": str(item.get("id") or f"task_{index + 1}"),
            "title": title or f"Task {index + 1}",
            "goal": goal or title or str(command or "").strip(),
            "target": str(item.get("target") or "").strip(),
            "action": str(item.get("action") or "complete").strip() or "complete",
            "modality": modality,
            "safety_risk": risk,
            "requires_consent": bool(item.get("requires_consent", False)),
            "completion_criteria": str(item.get("completion_criteria") or item.get("done_when") or "").strip(),
            "status": str(item.get("status") or "pending"),
            "result": str(item.get("result") or ""),
        })

    if route == "computer_task" and not tasks:
        tasks.append({
            "id": "task_1",
            "title": str(command or "Computer task").strip() or "Computer task",
            "goal": str(command or "").strip(),
            "target": "",
            "action": "complete",
            "modality": "unknown",
            "safety_risk": "medium",
            "requires_consent": False,
            "completion_criteria": "",
            "status": "pending",
            "result": "",
        })

    confidence = _coerce_float(plan.get("confidence"), 0.75 if route in allowed_routes else 0.0)
    if route == "computer_task" and confidence < 0.35:
        route = "clarify"

    requires_consent = bool(plan.get("requires_consent", False)) or any(bool(task.get("requires_consent")) for task in tasks)
    if requires_consent and route == "computer_task":
        route = "consent_required"

    return {
        "route": route,
        "confidence": confidence,
        "reply": str(plan.get("reply") or plan.get("message") or "").strip(),
        "requires_consent": requires_consent,
        "consent_reason": str(plan.get("consent_reason") or plan.get("reason") or "").strip(),
        "tasks": tasks,
        "raw_command": str(command or "").strip(),
    }


def _deterministic_router_plan(command: str) -> Optional[Dict[str, Any]]:
    raw = str(command or "").strip()
    key = _speech_intent_key(raw)
    if not key:
        return None

    stop_phrases = {
        "dung", "dung lai", "ngung", "ngung lai", "thoi", "huy", "huy di",
        "stop", "cancel", "pause", "tam dung", "dung tac vu", "ngung tac vu",
    }
    if _voice_contains_any(key, stop_phrases):
        return _normalize_router_plan({
            "route": "stop",
            "confidence": 0.98,
            "reply": "",
            "tasks": [],
        }, raw)

    action_or_control = {
        "mo", "bat", "vao", "truy cap", "di toi", "chay", "launch", "open",
        "run", "start", "click", "bam", "chon", "go", "nhap", "dien",
        "type", "search", "tim", "tim kiem", "google", "scroll", "cuon",
        "copy", "paste", "download", "upload", "play", "phat", "nghe", "xem",
    }
    generic_computer_targets = {
        "browser", "web", "website", "site", "trinh duyet", "folder", "file",
        "thu muc", "tap tin", "app", "ung dung", "phan mem", "cua so",
        "window", "desktop", "local computer", "may tinh",
    }
    looks_like_url = bool(re.search(r"(?:https?://|www\.|[a-z0-9-]+\.[a-z]{2,})(?:\S*)?$", key))
    looks_machine_action = (
        _voice_contains_any(key, action_or_control)
        or _voice_contains_any(key, generic_computer_targets)
        or looks_like_url
    )
    inferred_modality = ""
    if not looks_machine_action:
        short_words = [part for part in re.split(r"[^a-z0-9.+_-]+", key) if part]
        if 1 <= len(short_words) <= 4:
            try:
                dynamic_commands = desktop_agent._resolve_launchable_commands(raw)
            except Exception:
                dynamic_commands = []
            if dynamic_commands:
                looks_machine_action = True
                inferred_modality = "native_app"
    if not looks_machine_action:
        return None

    sensitive = {
        "xoa", "delete", "remove", "uninstall", "cai dat", "install", "format",
        "shutdown", "restart", "reboot", "pay", "purchase", "buy", "mua",
        "password", "mat khau", "otp", "token", "bank", "wallet", "thanh toan",
    }
    requires_consent = _voice_contains_any(key, sensitive)
    modality = inferred_modality or "unknown"
    if looks_like_url or _voice_contains_any(key, {"web", "website", "browser", "site", "trinh duyet"}):
        modality = "web"
    elif _voice_contains_any(key, {"app", "ung dung", "phan mem", "cua so", "window"}) or _voice_contains_any(key, {"mo", "bat", "chay", "launch", "open", "run", "start"}):
        modality = "native_app"

    return _normalize_router_plan({
        "route": "consent_required" if requires_consent else "computer_task",
        "confidence": 0.96,
        "requires_consent": requires_consent,
        "consent_reason": "Tác vụ này có thể thay đổi dữ liệu, cài/xóa phần mềm hoặc ảnh hưởng tài khoản." if requires_consent else "",
        "tasks": [{
            "id": "task_1",
            "title": raw,
            "goal": raw,
            "target": "",
            "action": "complete",
            "modality": modality,
            "safety_risk": "medium" if requires_consent else "low",
            "requires_consent": requires_consent,
            "completion_criteria": "Complete the requested computer action.",
        }],
    }, raw)


def _router_prompt(command: str, mode: str, source: str) -> str:
    return f"""
You are Skemi's intent router for a Jarvis-like local computer assistant.
Return ONLY strict JSON. Do not include markdown.

Classify the user request semantically, not by fixed keywords.
Allowed route values:
- chat: normal conversation; do not open or control apps.
- computer_task: operate the local computer in the selected mode.
- clarify: ask one short clarifying question because the task is underspecified.
- consent_required: pause before a sensitive action.
- stop: stop the current computer task.

If the request contains multiple computer tasks, decompose them into tasks[].
For each task.goal, remove polite filler and keep the actionable instruction only.
Ask consent before sending/posting messages, deleting, paying, uploading, installing,
entering secrets/OTP/tokens/account credentials, or changing system settings.

Each task object must include:
title, goal, target, action, modality(web/native_app/file/system/unknown),
safety_risk(none/low/medium/high), requires_consent, completion_criteria.

Selected local computer mode: {mode}
Input source: {source}
User request:
{command}

JSON schema:
{{
  "route": "chat|computer_task|clarify|consent_required|stop",
  "confidence": 0.0,
  "reply": "",
  "requires_consent": false,
  "consent_reason": "",
  "tasks": []
}}
""".strip()


async def _route_user_intent(command: str, *, mode: str, source: str, existing_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(existing_plan, dict) and existing_plan:
        return _normalize_router_plan(existing_plan, command)
    deterministic = _deterministic_router_plan(command)
    if deterministic and deterministic.get("route") in {"computer_task", "consent_required", "stop"}:
        return deterministic
    try:
        from ChatBackend import _generate_text_once, MODEL_ROUTER, MODEL_MAIN
        text = await _generate_text_once(
            MODEL_ROUTER or MODEL_MAIN,
            _router_prompt(command, mode, source),
            timeout=45.0,
            num_predict=900,
        )
        normalized = _normalize_router_plan(_extract_json_object(text), command)
        if normalized["route"] == "clarify" and deterministic:
            return deterministic
        if normalized["route"] == "clarify" and not normalized.get("reply"):
            normalized["reply"] = "Mình chưa hiểu đủ rõ để làm an toàn. Bạn nói cụ thể hơn một chút nhé?"
        return normalized
    except Exception as exc:
        return {
            "route": "clarify",
            "confidence": 0.0,
            "reply": f"Mình chưa hiểu đủ rõ để làm an toàn vì router gặp lỗi: {exc}",
            "requires_consent": False,
            "consent_reason": "",
            "tasks": [],
            "raw_command": str(command or "").strip(),
        }


def _speech_intent_key(text: str) -> str:
    raw = str(text or "").lower()
    raw = "".join(
        ch for ch in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(ch)
    )
    raw = raw.replace("đ", "d")
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _voice_contains_any(key: str, phrases: set[str]) -> bool:
    haystack = f" {str(key or '').strip()} "
    return any(f" {phrase} " in haystack for phrase in phrases)


def _classify_voice_intent(text: str) -> Dict[str, str]:
    key = _speech_intent_key(text)
    if not key:
        return {"route": "ignore", "reason": "empty"}

    greeting_words = {"alo", "skemi", "hi", "hey", "hello", "chao", "oi", "nay", "e", "uh", "um", "a", "da", "troi", "vai"}
    parts = key.split()
    if parts and all(part in greeting_words for part in parts):
        return {"route": "ignore", "reason": "greeting"}

    stop_phrases = {
        "dung", "dung lai", "ngung", "ngung lai", "thoi", "huy", "huy di",
        "stop", "cancel", "pause", "tam dung", "dung tac vu", "ngung tac vu",
    }
    if _voice_contains_any(key, stop_phrases):
        media_targets = {"nhac", "video", "youtube", "bai hat", "phim", "audio"}
        explicit_task_stop = _voice_contains_any(key, {"tac vu", "viec nay", "dang lam", "may tinh"})
        if _voice_contains_any(key, media_targets) and not explicit_task_stop:
            return {"route": "computer", "reason": "media_control"}
        return {"route": "stop", "reason": "user_stop"}

    computer_phrases = {
        "mo", "bat", "vao", "truy cap", "di toi", "tim", "tim kiem", "search",
        "google", "phat", "nghe", "xem", "play", "nhan", "gui", "nhan tin",
        "go", "nhap", "dien", "click", "bam", "chon", "keo", "cuon", "scroll",
        "dong", "copy", "paste", "xoa", "tai", "cai", "chay", "launch",
        "open", "type", "send", "message", "login", "dang nhap", "youtube",
        "chrome", "edge", "browser", "web", "website", "discord", "facebook",
        "gmail", "file", "folder", "thu muc", "download", "desktop", "may tinh",
        "app", "ung dung", "cua so",
    }
    if _voice_contains_any(key, computer_phrases):
        return {"route": "computer", "reason": "computer_action"}

    chat_phrases = {
        "noi chuyen", "tro chuyen", "tam su", "giai thich", "la gi", "tai sao",
        "vi sao", "nhu the nao", "nhu nao", "ban nghi", "the nao", "ke chuyen",
        "hoi", "tra loi", "cam on", "xin chao",
    }
    question_starters = {"ai", "cai gi", "o dau", "khi nao", "bao gio", "sao", "tai sao", "vi sao"}
    if _voice_contains_any(key, chat_phrases) or any(key.startswith(prefix + " ") or key == prefix for prefix in question_starters):
        return {"route": "chat", "reason": "conversation"}

    # Natural Jarvis default: if it is not clearly a machine action, talk back.
    return {"route": "chat", "reason": "default_chat"}


def _queue_voice_reply(text: str, *, force: bool = False) -> None:
    if not bool(local_computer_state.get("voice_control_enabled", False)):
        return
    if not force and not bool(local_computer_state.get("is_voice_session", False)):
        return
    reply = str(text or "").strip()
    if not reply:
        return
    
    # Auto-translate common English status to Vietnamese before speaking
    if "Could not launch" in reply:
        reply = "Không tìm thấy ứng dụng yêu cầu."
    elif "Task completed" in reply:
        reply = "Đã hoàn thành nhiệm vụ."
    elif "Starting" in reply:
        reply = "Bắt đầu xử lý."
        
    try:
        asyncio.create_task(desktop_companion.desktop_companion_host.speak(reply))
    except RuntimeError:
        pass


def _maybe_queue_voice_progress(text: str) -> None:
    global _last_voice_progress_spoken_at, _last_voice_progress_text
    if not bool(local_computer_state.get("is_voice_session", False)):
        return
    desc = re.sub(r"\s+", " ", str(text or "").strip())
    if not desc:
        return
    lower = desc.lower()
    if lower in {"analyzing current screen...", "observing screen details...", "working", "running"}:
        return
    now = time.time()
    if desc == _last_voice_progress_text and now - _last_voice_progress_spoken_at < 20:
        return
    if now - _last_voice_progress_spoken_at < 5:
        return
    _last_voice_progress_spoken_at = now
    _last_voice_progress_text = desc
    _queue_voice_reply(desc, force=True)


async def _voice_chat_reply(text: str) -> str:
    question = str(text or "").strip()
    if not question:
        return ""
    try:
        import ChatBackend as backend

        history = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in _voice_chat_history[-8:]
        )
        prompt = f"""Bạn là Skemi ở chế độ giọng nói kiểu Jarvis.
Nhiệm vụ: trả lời hội thoại tự nhiên, ngắn gọn, tiếng Việt, thân thiện.
Nếu người dùng chỉ trò chuyện, không được nói rằng bạn đang mở app hay thao tác máy tính.
Nếu họ muốn làm việc trên máy tính thì chỉ nói ngắn rằng hãy nói rõ hành động; router ngoài sẽ xử lý hành động rõ ràng.
Không dùng markdown. Không liệt kê dài. Trả lời 1-3 câu.

Lịch sử gần đây:
{history or "(chưa có)"}

Người dùng vừa nói: {question}

Skemi trả lời:"""
        reply = await backend._generate_text_once(
            getattr(backend, "MODEL_MAIN", "") or getattr(backend, "MODEL_ROUTER", ""),
            prompt,
            timeout=45.0,
            num_predict=260,
        )
        reply = re.sub(r"\s+", " ", str(reply or "").strip())
        reply = re.sub(r"^Skemi\s*:\s*", "", reply, flags=re.I).strip()
        if not reply:
            reply = "Mình nghe đây. Bạn muốn trò chuyện hay muốn mình thao tác gì trên máy?"
        _voice_chat_history.append({"role": "user", "content": question})
        _voice_chat_history.append({"role": "assistant", "content": reply})
        del _voice_chat_history[:-12]
        return reply[:700]
    except Exception as exc:
        return f"Mình nghe được rồi, nhưng phần trả lời bằng model đang gặp lỗi: {exc}"


def _voice_reply_from_event(event: Dict[str, Any], event_type: str, fallback: str = "") -> str:
    for key in ("final_result", "result", "message", "description", "status_text"):
        value = str((event or {}).get(key) or "").strip()
        if value and value.lower() not in {"done", "stopped", "error"}:
            return value
    if event_type == "stopped":
        current = str(local_computer_state.get("last_ai_action_desc") or "").strip()
        return f"Đã dừng. Trạng thái hiện tại: {current or fallback or 'chưa có kết quả cuối.'}"
    if event_type == "error":
        return fallback or "Tác vụ bị lỗi. Mình đã cập nhật chi tiết trên màn hình."
    return fallback or "Đã hoàn thành nhiệm vụ."


def _local_payload() -> Dict[str, Any]:
    # PRODUCTION FIX: If there's an active phantom lock, ALWAYS report phantom mode
    # regardless of what mode is stored in state or desktop type. The lock is the source of truth.
    has_active_lock = bool(local_computer_state.get("phantom_lock_active", False))
    
    if has_active_lock:
        # Force phantom mode - user has explicitly locked AI to a desktop
        mode = "phantom"
        local_computer_state["mode"] = mode
        local_computer_state["surface_mode"] = "phantom"
    else:
        mode = _normalize_mode(str(local_computer_state.get("mode") or "live"))
        local_computer_state["mode"] = mode
    connected = local_computer_state.get("connected", False)
    status = str(local_computer_state.get("status") or "idle")
    companion_ready = bool(desktop_companion.desktop_companion_host.is_started())
    if companion_ready and status == "idle":
        status = "connected"
        local_computer_state["status"] = status
        local_computer_state["connected"] = True
        connected = True
    running = status == "running"
    stream_url = str(local_computer_state.get("stream_url", ""))
    if (running or (status in {"done", "stopped", "error"} and _latest_frame)) and not stream_url:
        stream_url = "/api/local-computer/mjpeg"
    
    # v7.0 ALWAYS populate workspace status for display enumeration
    # regardless of mode - needed for Phantom desktop selection
    workspace_status = _jarvis_display_status(force=False)
    if workspace_status:
        workspace_status = _copy_workspace_status_to_state(workspace_status)
    workspace_label = _workspace_label()
    display_id_public = str(local_computer_state.get("display_id") or "") if _phantom_debug_enabled() else ""
    local_state = _local_state_from_values(
        mode,
        status,
        bool(local_computer_state.get("workspace_ready", False)),
        bool(local_computer_state.get("phantom_lock_active", False)),
    )
    local_computer_state["local_state"] = local_state
    local_computer_state["workspace_label"] = workspace_label
    local_computer_state["public_display_label"] = workspace_label
    driver_provider_public = str(local_computer_state.get("driver_provider") or "") if _phantom_debug_enabled() else ""

    return {
        "ok": True,
        "status": status,
        "task_state": str(local_computer_state.get("task_state") or ("working" if running else status)),
        "stream_state": str(local_computer_state.get("stream_state") or ("live" if stream_url else "ended")),
        "voice_state": str(local_computer_state.get("voice_state") or local_computer_state.get("voice_phase") or "standby"),
        "route": str(local_computer_state.get("route") or "chat"),
        "tasks": list(local_computer_state.get("tasks") or []),
        "current_task_index": int(local_computer_state.get("current_task_index") if local_computer_state.get("current_task_index") is not None else -1),
        "automation_mode": str(local_computer_state.get("automation_mode") or "blocked"),
        "local_state": local_state,
        "surface_mode": str(local_computer_state.get("surface_mode") or mode),
        "requires_consent": bool(local_computer_state.get("requires_consent", False)),
        "consent_reason": str(local_computer_state.get("consent_reason") or ""),
        "final_result": str(local_computer_state.get("final_result") or ""),
        "connected": connected,
        "mode": mode,
        "target_desktop_index": _int_or(local_computer_state.get("target_desktop_index"), -1),
        "locked_desktop_index": _int_or(local_computer_state.get("locked_desktop_index"), -1),
        "locked_desktop_name": str(local_computer_state.get("locked_desktop_name") or ""),
        "phantom_lock_active": bool(local_computer_state.get("phantom_lock_active", False)),
        "phantom_lock_token": str(local_computer_state.get("phantom_lock_token") or ""),
        "phantom_lock_last_heartbeat": float(local_computer_state.get("phantom_lock_last_heartbeat") or 0.0),
        "preview_only": bool(local_computer_state.get("preview_only", False)),
        "last_seen_at": local_computer_state.get("last_seen_at", 0.0),
        "machine_label": local_computer_state.get("machine_label", "No local companion"),
        "stream_url": stream_url,
        "workspace_kind": str(local_computer_state.get("workspace_kind") or "virtual_display"),
        "workspace_ready": bool(local_computer_state.get("workspace_ready", False)),
        "setup_state": str(local_computer_state.get("setup_state") or ("ready" if bool(local_computer_state.get("workspace_ready", False)) else "missing_driver")),
        "driver_status": str(local_computer_state.get("driver_status") or ""),
        "driver_version": str(local_computer_state.get("driver_version") or ""),
        "driver_provider": driver_provider_public,
        "bootstrap_required": bool(local_computer_state.get("bootstrap_required", False)),
        "bootstrap_url": str(local_computer_state.get("bootstrap_url") or PHANTOM_BOOTSTRAP_URL),
        "pairing_status": str(local_computer_state.get("pairing_status") or "paired_localhost"),
        "pairing_required": bool(local_computer_state.get("pairing_required", False)),
        "display_id": display_id_public,
        "workspace_label": workspace_label,
        "public_display_label": workspace_label,
        "display_role": str(local_computer_state.get("display_role") or ""),
        "isolation_level": str(local_computer_state.get("isolation_level") or ""),
        "display_bounds": dict(local_computer_state.get("display_bounds") or {}),
        "safe_for_phantom": bool(local_computer_state.get("safe_for_phantom", local_computer_state.get("workspace_ready", False))),
        "capture_probe_ok": bool(local_computer_state.get("capture_probe_ok", local_computer_state.get("workspace_ready", False))),
        "capture_probe_black": bool(local_computer_state.get("capture_probe_black", False)),
        "setup_required": bool(local_computer_state.get("setup_required", not bool(local_computer_state.get("workspace_ready", False)))),
        "install_available": bool(local_computer_state.get("install_available", local_computer_state.get("driver_package_present", False))),
        "install_message": str(local_computer_state.get("install_message") or ""),
        "launch_policy": str(local_computer_state.get("launch_policy") or "vision-only GUI control on the locked desktop"),
        "last_launch_error": str(local_computer_state.get("last_launch_error") or ""),
        "last_launch_error_code": str(local_computer_state.get("last_launch_error_code") or ""),
        "setup_message": str(local_computer_state.get("setup_message") or ""),
        "update_state": str(local_computer_state.get("update_state") or "current"),
        "update_available": bool(local_computer_state.get("update_available", False)),
        "update_required": bool(local_computer_state.get("update_required", False)),
        "latest_companion_version": str(local_computer_state.get("latest_companion_version") or ""),
        "latest_driver_version": str(local_computer_state.get("latest_driver_version") or ""),
        "update_url": str(local_computer_state.get("update_url") or PHANTOM_UPDATE_URL),
        "update_size_mb": str(local_computer_state.get("update_size_mb") or ""),
        "update_requires_admin": bool(local_computer_state.get("update_requires_admin", True)),
        "update_message": str(local_computer_state.get("update_message") or ""),
        "driver_package_present": bool(local_computer_state.get("driver_package_present", False)),
        "driver_package_path": str(local_computer_state.get("driver_package_path") or PHANTOM_DRIVER_INF_PATH),
        "driver_installer_present": bool(local_computer_state.get("driver_installer_present", False)),
        "driver_installer_path": str(local_computer_state.get("driver_installer_path") or ""),
        "cursor_overlay": dict(local_computer_state.get("cursor_overlay", {})),
        "notes": list(local_computer_state.get("notes") or _mode_notes(mode, connected=connected, running=running)),
        "session_id": local_computer_state.get("session_id", ""),
        "pending_confirmation": dict(local_computer_state.get("pending_confirmation") or {}),
        "last_event": dict(local_computer_state.get("last_event") or {}),
        "frame_version": int(local_computer_state.get("frame_version") or 0),
        "event_tail": list(_local_events)[-12:],
        "target_window_title": str(local_computer_state.get("target_window_title", "")),
        "target_window_hwnd": int(local_computer_state.get("target_window_hwnd") or 0),
        "target_window_class": str(local_computer_state.get("target_window_class", "")),
        "last_ai_action_desc": str(local_computer_state.get("last_ai_action_desc", "")),
        "voice_control_enabled": bool(local_computer_state.get("voice_control_enabled", False)),
        "companion_ready": companion_ready,
        "companion_version": str(local_computer_state.get("companion_version") or SKEMI_COMPANION_VERSION),
        "voice_status": str(local_computer_state.get("voice_phase") or ("listening" if bool(local_computer_state.get("voice_control_enabled", False)) else "standby")),
        "voice_phase": str(local_computer_state.get("voice_phase") or "standby"),
        "voice_transcript": str(local_computer_state.get("voice_transcript") or ""),
        "voice_route": str(local_computer_state.get("voice_route") or "auto"),
        "speech_to_text_engine": str(local_computer_state.get("speech_to_text_engine") or ""),
        "text_to_speech_engine": str(local_computer_state.get("text_to_speech_engine") or ""),
        "voice_capabilities": {
            "wake_word": False,
            "direct_prompt": True,
            "partial_transcript": True,
            "silence_endpointing": True,
            "dispatches_to_local_computer": True,
        },
    }


def _parse_sse_chunks(chunk: str) -> list[Dict[str, Any]]:
    parsed: list[Dict[str, Any]] = []
    for block in str(chunk or "").split("\n\n"):
        if not block.strip(): continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except Exception:
            payload = {"message": "\n".join(data_lines)}
        if isinstance(payload, dict):
            payload.setdefault("type", event_name)
            parsed.append(payload)
    return parsed


def _decode_frame(data_uri: str) -> bytes:
    payload = str(data_uri or "")
    if not payload:
        return b""
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[-1]
    try:
        return base64.b64decode(payload)
    except Exception:
        return b""


def _placeholder_svg(label: str = "Phantom waiting...") -> bytes:
    raw = str(label or "").strip().lower()
    title = "PHANTOM DESKTOP"
    subtitle = "Waiting for viewer"
    if "missing" in raw or "setup" in raw or "driver" in raw:
        title = "PHANTOM SETUP"
        subtitle = "Desktop workspace required"
    elif "ready" in raw or "viewing" in raw or "stream" in raw:
        title = "PHANTOM DESKTOP"
        subtitle = "AI desktop stream"
    title = title.replace("&", "&amp;").replace("<", "&lt;")
    subtitle = subtitle.replace("&", "&amp;").replace("<", "&lt;")
    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' viewBox='0 0 1280 720'>
<rect width='1280' height='720' fill='#080b12'/>
<rect x='56' y='56' width='1168' height='608' rx='14' fill='#0d1320' stroke='#263244' stroke-width='2'/>
<text x='640' y='340' text-anchor='middle' fill='#e5e7eb' font-family='Arial, sans-serif' font-size='30' font-weight='700'>{title}</text>
<text x='640' y='382' text-anchor='middle' fill='#94a3b8' font-family='Arial, sans-serif' font-size='18'>{subtitle}</text>
</svg>""".encode("utf-8")
    if "waiting for app window" in raw or "window capture" in raw:
        title = "PHANTOM WINDOW"
        subtitle = "Waiting for app window"
    elif "virtual display" in raw or "display missing" in raw:
        title = "PHANTOM SETUP"
        subtitle = "Virtual display required"
    elif "boot" in raw or "ready" in raw or "waiting" in raw:
        title = "PHANTOM BOOTING"
        subtitle = "Preparing isolated display stream"
    else:
        title = "PHANTOM WAITING"
        subtitle = "Standing by"
    title = title.replace("&", "&amp;").replace("<", "&lt;")
    subtitle = subtitle.replace("&", "&amp;").replace("<", "&lt;")
    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' viewBox='0 0 1280 720'>
<defs>
  <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
    <stop stop-color='#070b16'/><stop offset='.55' stop-color='#101827'/><stop offset='1' stop-color='#160b24'/>
  </linearGradient>
  <radialGradient id='glow' cx='50%' cy='44%' r='38%'>
    <stop stop-color='#22d3ee' stop-opacity='.22'/><stop offset='1' stop-color='#22d3ee' stop-opacity='0'/>
  </radialGradient>
  <style>
    @keyframes pulse {{ 0% {{ r: 28; opacity: .32; }} 100% {{ r: 116; opacity: 0; }} }}
    @keyframes breathe {{ 0%,100% {{ opacity: .82; transform: scale(1); }} 50% {{ opacity: 1; transform: scale(1.08); }} }}
    .ring {{ animation: pulse 1.8s ease-out infinite; transform-origin: 640px 322px; }}
    .ring.two {{ animation-delay: .55s; }}
    .core {{ animation: breathe 1.6s ease-in-out infinite; transform-origin: 640px 322px; }}
  </style>
</defs>
<rect width='1280' height='720' fill='url(#bg)'/>
<rect width='1280' height='720' fill='url(#glow)'/>
<g opacity='.18' stroke='#38bdf8' stroke-width='1'>
  <path d='M0 120H1280M0 240H1280M0 360H1280M0 480H1280M0 600H1280'/>
  <path d='M160 0V720M320 0V720M480 0V720M640 0V720M800 0V720M960 0V720M1120 0V720'/>
</g>
<circle class='ring' cx='640' cy='322' r='32' fill='none' stroke='#22d3ee' stroke-width='3'/>
<circle class='ring two' cx='640' cy='322' r='32' fill='none' stroke='#a855f7' stroke-width='3'/>
<circle class='core' cx='640' cy='322' r='18' fill='#22d3ee'/>
<text x='640' y='404' text-anchor='middle' fill='#e5f6ff' font-family='Arial, sans-serif' font-size='30' font-weight='700' letter-spacing='2'>{title}</text>
<text x='640' y='442' text-anchor='middle' fill='#8fb6c8' font-family='Arial, sans-serif' font-size='18'>{subtitle}</text>
</svg>""".encode("utf-8")


async def _stop_current_session_locked(reason: str = "Stopped by user") -> None:
    global _local_task, _latest_frame
    session_id = str(local_computer_state.get("session_id") or "").strip()
    if session_id:
        try:
            await desktop_companion.desktop_companion_host.stop_session(session_id)
        except Exception:
            pass
    if _local_task and not _local_task.done():
        _local_task.cancel()
    _local_task = None
    local_computer_state["status"] = "idle"
    local_computer_state["task_state"] = "stopped"
    local_computer_state["stream_state"] = "ended"
    local_computer_state["session_id"] = ""
    local_computer_state["stream_url"] = ""
    local_computer_state["preview_only"] = False
    local_computer_state["frame_version"] = 0
    _latest_frame = b""
    local_computer_state["pending_confirmation"] = {}
    local_computer_state["notes"] = [reason]
    local_computer_state["last_seen_at"] = time.time()
    local_computer_state["mode"] = "live"
    local_computer_state["surface_mode"] = "live"
    local_computer_state["phantom_lock_active"] = False
    local_computer_state["preview_only"] = False
    _clear_phantom_lock_fields()


async def _start_phantom_preview_locked(*, desktop_index: int = -1, lock_token: str = "", use_virtual: bool = False) -> Dict[str, Any]:
    """Start an idle Phantom session so the virtual display streams before any command."""
    global _local_task, _latest_frame
    _cancel_phantom_release_task()
    mode = "phantom"
    desktop_index = _int_or(desktop_index, -1)
    local_computer_state["use_virtual_display"] = bool(use_virtual)
    
    # If no explicit desktop index was passed, restore previous target/locked desktop
    if desktop_index < 0:
        for candidate in (
            local_computer_state.get("locked_desktop_index"),
            local_computer_state.get("target_desktop_index"),
        ):
            restored = _int_or(candidate, -1)
            if restored >= 0:
                desktop_index = restored
                break
    if desktop_index < 0:
        return {
            "success": False,
            "ok": False,
            "error": "desktop_required",
            "message": "Choose an existing desktop or create a new desktop before starting Phantom.",
            "locked_desktop_index": -1,
            "locked_desktop_name": "",
        }
    
    # Check if the desktop actually exists
    if desktop_agent:
        all_desktops = desktop_agent._get_all_desktops_sync()
        if not any(_int_or(d.get("index"), -1) == desktop_index for d in all_desktops):
            return {
                "success": False,
                "ok": False,
                "error": "desktop_not_found",
                "message": f"Desktop {desktop_index + 1} no longer exists. Please select an existing desktop or create a new one.",
                "locked_desktop_index": -1,
                "locked_desktop_name": "",
            }
    local_computer_state["target_desktop_index"] = desktop_index
        
    lock_token = str(lock_token or local_computer_state.get("phantom_lock_token") or "").strip()
    _set_phantom_lock(desktop_index, lock_token)
    if lock_token:
        _schedule_phantom_heartbeat_release(lock_token, str(local_computer_state.get("session_id") or ""))
    if desktop_agent and hasattr(desktop_agent, "activate_virtual_desktop_index"):
        with contextlib.suppress(Exception):
            # v1.2.0: AI now works silently on the target desktop without forcing a physical switch
            # desktop_agent.activate_virtual_desktop_index(desktop_index)
            pass
    
    # v1.2.6: Force a monitor refresh to ensure accurate capture bounds
    workspace_status = _copy_workspace_status_to_state(desktop_agent.jarvis_display_manager.ensure_ready(force=True))
    if not bool(workspace_status.get("workspace_ready")) or bool(workspace_status.get("update_required")):
        if str(local_computer_state.get("session_id") or "").strip() and _local_task and not _local_task.done():
            await _stop_current_session_locked("Phantom Desktop unavailable; unsafe Local Computer session stopped.")
        _latest_frame = b""
        return _set_jarvis_display_block(
            str(workspace_status.get("last_launch_error") or _short_phantom_setup_message(workspace_status)),
            workspace_status,
            route="preview",
        )
    existing_sid = str(local_computer_state.get("session_id") or "").strip()
    existing_preview = bool(local_computer_state.get("preview_only", False))
    if existing_sid and not existing_preview:
        local_computer_state["mode"] = mode
        local_computer_state["stream_url"] = local_computer_state.get("stream_url") or "/api/local-computer/mjpeg"
        return _local_payload()
    if existing_sid and existing_preview:
        current_index = _int_or(local_computer_state.get("target_desktop_index"), -1)
        if current_index == desktop_index and str(local_computer_state.get("mode") or "") == mode:
            local_computer_state["stream_url"] = local_computer_state.get("stream_url") or "/api/local-computer/mjpeg"
            return _local_payload()
        await _stop_current_session_locked("Restarting Phantom Desktop preview.")

    local_computer_state["mode"] = mode
    local_computer_state["connected"] = True
    local_computer_state["consent_granted"] = True
    local_computer_state["machine_label"] = "This device"
    local_computer_state["status"] = "running"
    local_computer_state["task_state"] = "preview"
    local_computer_state["stream_state"] = "connecting"
    local_computer_state["frame_version"] = 0
    _latest_frame = b""
    local_computer_state["automation_mode"] = "preview"
    local_computer_state["surface_mode"] = mode
    local_computer_state["preview_only"] = True
    local_computer_state["final_result"] = ""
    if bool(workspace_status.get("workspace_ready")):
        local_computer_state["last_ai_action_desc"] = f"AI is viewing {_workspace_label(desktop_index)}."
    else:
        local_computer_state["last_ai_action_desc"] = str(workspace_status.get("last_launch_error") or _short_phantom_setup_message(workspace_status))
    desktop_name = str(local_computer_state.get("locked_desktop_name") or _phantom_desktop_name(desktop_index) or "").strip()
    local_computer_state["notes"] = _mode_notes(mode, connected=True, running=True)
    if desktop_name:
        local_computer_state["notes"] = [f"AI controlling {desktop_name}"] + local_computer_state["notes"][:2]

    plan = {"route": "preview", "preview_only": True, "tasks": [], "desktop_index": desktop_index}
    try:
        # Add 8-second timeout for session startup to prevent hanging
        session_id, event_generator = await asyncio.wait_for(
            desktop_companion.desktop_companion_host.start_session(
                "__skemi_phantom_preview__",
                mode="phantom",
                bypass_safety=True,
                plan=plan,
                source="preview",
                desktop_index=desktop_index,
            ),
            timeout=8.0
        )
    except asyncio.TimeoutError:
        # If session startup times out, return error payload
        return _set_jarvis_display_block(
            "Phantom session startup timeout. Please check system performance and retry.",
            workspace_status,
            route="preview",
        )
    
    local_computer_state["session_id"] = session_id
    local_computer_state["stream_url"] = "/api/local-computer/mjpeg"
    if lock_token:
        _schedule_phantom_heartbeat_release(lock_token, session_id)
    _append_event({"type": "started", "session_id": session_id, "mode": mode, "preview_only": True, "desktop_index": desktop_index})
    _local_task = asyncio.create_task(_consume_desktop_events(session_id, event_generator, mode), name=f"skemi-local-preview-{session_id}")
    
    payload = _local_payload()
    payload["success"] = True
    payload["ok"] = True
    payload["locked_desktop_index"] = desktop_index
    payload["locked_desktop_name"] = desktop_name or _phantom_desktop_name(desktop_index)
    payload["desktop_name"] = payload["locked_desktop_name"]
    payload["workspace_label"] = payload["locked_desktop_name"]
    payload["public_display_label"] = payload["locked_desktop_name"]
    payload["message"] = f"AI đang hoạt động trên {payload['locked_desktop_name']}"
    return payload


async def _start_live_viewer_locked(*, preserve_lock: bool = True) -> Dict[str, Any]:
    """Start a Live Control preview (watch-only stream) of the user's current desktop."""
    global _local_task, _latest_frame
    existing_sid = str(local_computer_state.get("session_id") or "").strip()
    existing_preview = bool(local_computer_state.get("preview_only", False))
    
    if existing_sid:
        if not preserve_lock or existing_preview:
            await _stop_current_session_locked("Switching to Live Control.")
        else:
            local_computer_state["mode"] = "live"
            local_computer_state["surface_mode"] = "live"
            local_computer_state["local_state"] = "live_viewer"
            local_computer_state["notes"] = _mode_notes("live", connected=True, running=True)
            local_computer_state["last_ai_action_desc"] = "Live Control preview is watch-only. Existing AI task was not interrupted."
            if desktop_agent:
                desktop_agent.agent_module_update_mode("live")
            return _local_payload()

    if not preserve_lock:
        _cancel_phantom_heartbeat_task()
        _clear_phantom_lock_fields()

    local_computer_state["mode"] = "live"
    local_computer_state["surface_mode"] = "live"
    local_computer_state["local_state"] = "live_viewer"
    local_computer_state["connected"] = True
    local_computer_state["consent_granted"] = True
    local_computer_state["machine_label"] = "This device"
    local_computer_state["status"] = "running"
    local_computer_state["task_state"] = "preview"
    local_computer_state["stream_state"] = "connecting"
    local_computer_state["automation_mode"] = "preview"
    local_computer_state["preview_only"] = True
    local_computer_state["final_result"] = ""
    local_computer_state["last_ai_action_desc"] = "Live Control is showing your current desktop."
    local_computer_state["notes"] = _mode_notes("live", connected=True, running=True)
    local_computer_state["frame_version"] = 0
    _latest_frame = b""

    plan = {"route": "preview", "preview_only": True, "tasks": []}
    session_id, event_generator = await desktop_companion.desktop_companion_host.start_session(
        "__skemi_live_viewer__",
        mode="live",
        bypass_safety=True,
        plan=plan,
        source="preview",
        desktop_index=-1,
    )
    local_computer_state["session_id"] = session_id
    local_computer_state["stream_url"] = "/api/local-computer/mjpeg"
    _append_event({"type": "started", "session_id": session_id, "mode": "live", "preview_only": True})
    _local_task = asyncio.create_task(_consume_desktop_events(session_id, event_generator, "live"), name=f"skemi-local-live-{session_id}")
    return _local_payload()


async def _consume_desktop_events(session_id: str, event_generator: AsyncGenerator[str, None], mode: str) -> None:
    global _latest_frame
    try:
        async for chunk in event_generator:
            for event in _parse_sse_chunks(chunk):
                event_type = str(event.get("type") or "message").lower()
                local_computer_state["last_seen_at"] = time.time()
                if "task_state" in event:
                    local_computer_state["task_state"] = str(event.get("task_state") or local_computer_state.get("task_state") or "")
                if "stream_state" in event:
                    local_computer_state["stream_state"] = str(event.get("stream_state") or local_computer_state.get("stream_state") or "")
                if "voice_state" in event:
                    local_computer_state["voice_state"] = str(event.get("voice_state") or local_computer_state.get("voice_state") or "")
                if "route" in event:
                    local_computer_state["route"] = str(event.get("route") or local_computer_state.get("route") or "chat")
                if isinstance(event.get("tasks"), list):
                    local_computer_state["tasks"] = event.get("tasks") or []
                if "current_task_index" in event:
                    with contextlib.suppress(Exception):
                        local_computer_state["current_task_index"] = int(event.get("current_task_index"))
                if "automation_mode" in event:
                    local_computer_state["automation_mode"] = str(event.get("automation_mode") or local_computer_state.get("automation_mode") or "blocked")
                if "surface_mode" in event:
                    local_computer_state["surface_mode"] = str(event.get("surface_mode") or mode)
                for field in [
                    "workspace_kind", "workspace_ready", "setup_state", "driver_status", "driver_version",
                    "driver_provider", "bootstrap_required", "bootstrap_url", "pairing_status", "pairing_required",
                    "display_id", "display_role", "isolation_level", "display_bounds", "launch_policy",
                    "safe_for_phantom", "capture_probe_ok", "capture_probe_black", "setup_required",
                    "install_available", "install_message",
                    "last_launch_error", "last_launch_error_code", "setup_message",
                    "update_state", "update_available", "update_required", "latest_companion_version",
                    "latest_driver_version", "update_url", "update_size_mb", "update_requires_admin",
                    "update_message", "driver_package_present", "driver_package_path", "cursor_overlay",
                ]:
                    if field in event:
                        local_computer_state[field] = event[field]
                if event_type == "agent_event":
                    desc = str(event.get("description") or "").strip()
                    if desc:
                        local_computer_state["last_ai_action_desc"] = desc
                        _maybe_queue_voice_progress(desc)
                    _append_event({"topic": "agent", "msg": desc or "AI is taking action..."})
                if event.get("image"):
                    frame = _decode_frame(str(event.get("image") or ""))
                    if frame:
                        _latest_frame = frame
                        local_computer_state["frame_version"] = int(local_computer_state.get("frame_version") or 0) + 1
                        local_computer_state["stream_url"] = "/api/local-computer/mjpeg"
                        local_computer_state["stream_state"] = "live"
                description = str(event.get("result") or event.get("description") or event.get("message") or event_type)
                if event_type in {"route_decided", "task_started", "action_started", "action_done", "task_done", "stream_state_changed", "voice_state_changed"}:
                    if event_type == "task_started":
                        local_computer_state["task_state"] = "working"
                    elif event_type == "task_done":
                        local_computer_state["task_state"] = "working"
                    elif event_type == "stream_state_changed":
                        local_computer_state["stream_state"] = str(event.get("stream_state") or local_computer_state.get("stream_state") or "live")
                elif event_type in {"confirm_required", "consent_required"}:
                    local_computer_state["pending_confirmation"] = dict(event)
                    local_computer_state["status"] = "awaiting_confirmation"
                    local_computer_state["task_state"] = "awaiting_consent"
                    local_computer_state["requires_consent"] = True
                    local_computer_state["consent_reason"] = str(event.get("consent_reason") or event.get("message") or description)
                elif event_type in {"done", "stopped"}:
                    local_computer_state["status"] = event_type
                    local_computer_state["task_state"] = event_type
                    local_computer_state["final_result"] = description
                    local_computer_state["requires_consent"] = False
                    local_computer_state["pending_confirmation"] = {}
                    _queue_voice_reply(_voice_reply_from_event(event, event_type, description))
                elif event_type == "error":
                    local_computer_state["status"] = "error"
                    local_computer_state["task_state"] = "error"
                    local_computer_state["final_result"] = description
                    local_computer_state["requires_consent"] = False
                    local_computer_state["pending_confirmation"] = {}
                    _queue_voice_reply(_voice_reply_from_event(event, event_type, description))
                elif event_type == "final_result":
                    local_computer_state["final_result"] = description
                    local_computer_state["task_state"] = str(event.get("task_state") or local_computer_state.get("task_state") or "done")
                    _queue_voice_reply(_voice_reply_from_event(event, "done", description))
                elif event_type == "telemetry":
                    for field in ["target_window_hwnd", "target_window_title", "target_window_class"]:
                        if field in event:
                            local_computer_state[field] = event[field]
                elif event_type in {"start", "status", "screenshot"}:
                    if bool(local_computer_state.get("preview_only", False)):
                        local_computer_state["status"] = "running"
                        local_computer_state["task_state"] = "preview"
                else:
                    if local_computer_state.get("status") not in {"awaiting_confirmation", "error"}:
                        local_computer_state["status"] = "running"
                        local_computer_state["task_state"] = "working"
                
                local_computer_state["notes"] = _mode_notes(mode, connected=True, running=local_computer_state.get("status") == "running")[:2] + [description]
                _append_event(event)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        local_computer_state["status"] = "error"
        local_computer_state["notes"] = [f"Local Computer stream error: {exc}"]
        _append_event({"type": "error", "message": str(exc)})
    finally:
        if str(local_computer_state.get("session_id") or "") == session_id and local_computer_state.get("status") == "running":
            local_computer_state["status"] = "idle"
            local_computer_state["notes"] = _mode_notes(mode, connected=True, running=False)


async def on_voice_status(payload: Dict[str, Any]):
    phase = str((payload or {}).get("phase") or "status").strip().lower()
    transcript = str((payload or {}).get("transcript") or "").strip()
    local_computer_state["voice_phase"] = phase or "status"
    local_computer_state["voice_state"] = phase or "status"
    local_computer_state["voice_transcript"] = transcript
    local_computer_state["connected"] = True
    local_computer_state["machine_label"] = "This device"
    local_computer_state["last_seen_at"] = time.time()

    if phase == "listening":
        message = "Mic đang nghe. Nói yêu cầu như khi bạn nhập prompt."
    elif phase == "hearing":
        message = "Đang nghe giọng nói..."
    elif phase == "partial" and transcript:
        message = f"Đang nghe: {transcript}"
    elif phase == "transcribing":
        message = "Đang dịch giọng nói..."
    elif phase == "speaking":
        message = "Skemi đang trả lời..."
    elif phase == "final" and transcript:
        message = f"Đã nhận lệnh giọng nói: {transcript}"
    elif phase == "dispatching" and transcript:
        message = f"Đang hiểu yêu cầu: {transcript}"
    elif phase == "timeout":
        message = "Chưa nghe rõ yêu cầu hoàn chỉnh. Hãy nói lại hoặc nhập prompt."
    else:
        message = "Voice mode đang hoạt động."

    if phase not in {"listening", "hearing", "partial"}:
        local_computer_state["last_ai_action_desc"] = message
        local_computer_state["notes"] = [message] + list(local_computer_state.get("notes") or [])[:2]
    _append_event({
        "type": "voice_state_changed",
        "voice_state": phase,
        "phase": phase,
        "transcript": transcript,
        "message": message,
    })


def register(app: FastAPI) -> None:
    # v1.2.4: Ensure fresh startup state
    local_computer_state["mode"] = "live"
    local_computer_state["phantom_lock_active"] = False
    _clear_phantom_lock_fields()
    
    @app.get("/health")
    async def local_companion_health():
        workspace_status = _copy_workspace_status_to_state(_jarvis_display_status(force=False))
        return {
            "ok": True,
            "success": True,
            "companion_ready": True,
            "companion_version": SKEMI_COMPANION_VERSION,
            "pairing_status": "paired_localhost",
            "pairing_required": False,
            "origin_allowed": True,
            **workspace_status,
        }

    @app.get("/api/local-computer/bootstrap/script")
    async def local_computer_bootstrap_script():
        info = _phantom_driver_package_info()
        return {
            "success": bool(info.get("driver_package_present")),
            "setup_required": True,
            "install_available": bool(info.get("driver_package_present")),
            "download_url": "/download/virtual-display-driver",
            "message": "Install the local Skemi virtual display driver, then press Check again.",
            **info,
        }

    @app.get("/api/local-computer/bootstrap/package")
    async def local_computer_bootstrap_package():
        zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usbmmidd_v2.zip")
        if not os.path.exists(zip_path):
            raise HTTPException(status_code=404, detail="Local virtual display driver package is missing.")
        return FileResponse(zip_path, media_type="application/zip", filename="Skemi_Virtual_Display_Driver.zip")

    @app.get("/download/virtual-display-driver")
    async def download_virtual_display_driver():
        zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usbmmidd_v2.zip")
        if not os.path.exists(zip_path):
            raise HTTPException(status_code=404, detail="Local virtual display driver package is missing.")
        return FileResponse(zip_path, media_type="application/zip", filename="Skemi_Virtual_Display_Driver.zip")

    @app.get("/api/local-computer/status")
    async def local_computer_status():
        # v8.6: Proactive Self-Healing
        # If the user is in Phantom Mode but the workspace isn't ready, 
        # trigger a non-blocking check to see if we can activate the driver.
        if local_computer_state.get("mode") == "phantom":
            ws_ready = bool(local_computer_state.get("workspace_ready", False))
            last_check = float(local_computer_state.get("last_workspace_check_at", 0))
            if not ws_ready and (time.time() - last_check > 5.0):
                local_computer_state["last_workspace_check_at"] = time.time()
                _copy_workspace_status_to_state(_jarvis_display_status(force=False))

        local_computer_state["last_seen_at"] = time.time()
        return _local_payload()

    @app.get("/api/local-computer/displays")
    async def local_computer_displays():
        status = _copy_workspace_status_to_state(_jarvis_display_status(force=True))
        return {"success": True, **_public_workspace_status(status)}

    @app.get("/api/local-computer/phantom/health")
    async def local_computer_phantom_health(force: bool = False):
        """v7.0 Optimized Health Engine - Fast with Smart Caching"""
        if force:
            status = await asyncio.to_thread(_jarvis_display_status, True)
        else:
            status = _copy_workspace_status_to_state(_jarvis_display_status(force=False))
        
        driver_detection: Dict[str, Any] = {}
        try:
            if force or not bool(status.get("workspace_ready")):
                from driver_manager import get_driver_manager
                manager = get_driver_manager()
                driver_detection = await asyncio.wait_for(
                    manager.detect_driver(force=force),
                    timeout=3.0
                )
                if driver_detection.get("enabled"):
                    status["workspace_ready"] = True
                    status["setup_state"] = "ready"
                    status["driver_status"] = "active"
                    status["setup_required"] = False
                    status["safe_for_phantom"] = True
                    status["capture_probe_ok"] = True
                    status["display_bounds"] = driver_detection.get("display_bounds", status.get("display_bounds", {}))
        except (asyncio.TimeoutError, Exception):
            pass

        if driver_detection:
            status["install_available"] = bool(driver_detection.get("install_available", status.get("install_available", False)))
            status["install_message"] = str(driver_detection.get("install_message") or status.get("install_message") or "")

        return {
            "ok": True,
            "success": True,
            **_public_workspace_status(status),
            "safe_for_phantom": bool(status.get("safe_for_phantom", status.get("workspace_ready", False))),
            "capture_probe_ok": bool(status.get("capture_probe_ok", status.get("workspace_ready", False))),
            "capture_probe_black": bool(status.get("capture_probe_black", False)),
            "setup_required": bool(status.get("setup_required", not bool(status.get("workspace_ready")))),
            "install_available": bool(status.get("install_available", False)),
            "install_message": str(status.get("install_message") or ""),
            "download_url": str(status.get("download_url") or "/download/virtual-display-driver"),
            **{k: v for k, v in _phantom_desktop_payload().items() if k in {"count", "current", "locked_desktop_index", "locked_desktop_name", "locked_desktop_guid"}},
            "mode": "phantom" if bool(local_computer_state.get("phantom_lock_active", False)) else str(local_computer_state.get("mode") or "live"),
            "phantom_lock_active": bool(local_computer_state.get("phantom_lock_active", False)),
            "phantom_lock_last_heartbeat": float(local_computer_state.get("phantom_lock_last_heartbeat") or 0.0),
        }

    @app.post("/api/local-computer/phantom/install-driver")
    async def local_computer_phantom_install_driver():
        base_dir = os.getcwd()
        target_dir = os.path.join(base_dir, "Skemi_Virtual_Display")
        
        current = _copy_workspace_status_to_state(_jarvis_display_status(force=True))
        if current.get("workspace_ready"):
            return {
                "success": True,
                "already_ready": True,
                "message": "A safe virtual display is already active. No driver install needed.",
                **_public_workspace_status(current),
            }
        
        # Use only the local bundled package. Do not download external drivers here.
        installer_path = None
        inf_path = None
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                if f.lower() == "deviceinstaller64.exe":
                    installer_path = os.path.join(root, f)
                if f.lower() == "usbmmidd.inf":
                    inf_path = os.path.join(root, f)
            if installer_path and inf_path:
                break

        if not installer_path or not inf_path:
            return {
                "success": False,
                "error": "driver_package_missing",
                "install_available": False,
                "download_url": "/download/virtual-display-driver",
                "message": "Local Skemi virtual display driver files are missing. Download/install the package, then press Check again.",
            }
        
        work_dir = os.path.dirname(installer_path)
        
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run([installer_path, "stop", "usbmmidd"], capture_output=True, timeout=10, cwd=work_dir, creationflags=creationflags)
            result = subprocess.run(
                [installer_path, "install", inf_path, "usbmmidd"],
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=30,
                creationflags=creationflags,
            )
            output = "\n".join([str(result.stdout or ""), str(result.stderr or "")]).strip()
            if result.returncode != 0 and "already" not in output.lower():
                elevation = "740" in output or "elevation" in output.lower() or "admin" in output.lower()
                return {
                    "success": False,
                    "error": "elevation_required" if elevation else "driver_install_failed",
                    "requires_admin": elevation,
                    "install_available": True,
                    "download_url": "/download/virtual-display-driver",
                    "message": "Administrator approval is required. Run the installer, then press Check again." if elevation else "Driver install failed. Press Check again after resolving the driver error.",
                    "output": output,
                }
            enable = subprocess.run(
                [installer_path, "enableidd", "1"],
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=15,
                creationflags=creationflags,
            )
            enable_output = "\n".join([str(enable.stdout or ""), str(enable.stderr or "")]).strip()
            await asyncio.sleep(1.5)
            latest = _copy_workspace_status_to_state(_jarvis_display_status(force=True))
            return {
                "success": True,
                "workspace_ready": bool(latest.get("workspace_ready", False)),
                "setup_required": not bool(latest.get("workspace_ready", False)),
                "install_available": True,
                "message": "Đã chạy lệnh kích hoạt driver. Skemi đang kiểm tra lại màn hình ảo..." if not latest.get("workspace_ready") else "Màn hình ảo đã được kích hoạt và sẵn sàng.",
                "output": f"Install Log:\n{output}\n\nEnable Log:\n{enable_output}",
                **_public_workspace_status(latest),
            }
        except Exception as e:
            return {
                "success": False,
                "error": "driver_install_exception",
                "install_available": True,
                "download_url": "/download/virtual-display-driver",
                "message": "Could not run the local driver installer. Install it manually, then press Check again.",
                "detail": str(e),
            }

    @app.get("/api/local-computer/phantom/driver-status")
    async def local_computer_phantom_driver_status(force: bool = False):
        """Get virtual display driver detection status"""
        from driver_manager import get_driver_manager
        manager = get_driver_manager()
        status = await manager.detect_driver(force=force)
        info = manager.get_driver_info()
        return {
            "success": True,
            **status,
            "driver_info": info
        }

    @app.post("/api/local-computer/phantom/driver-enable")
    async def local_computer_phantom_driver_enable():
        """Enable virtual display (requires admin)"""
        from driver_manager import get_driver_manager
        manager = get_driver_manager()
        result = await manager.enable_virtual_display()
        return result

    @app.post("/api/local-computer/phantom/driver-disable")
    async def local_computer_phantom_driver_disable():
        """Disable virtual display"""
        from driver_manager import get_driver_manager
        manager = get_driver_manager()
        result = await manager.disable_virtual_display()
        return result

    @app.get("/api/local-computer/phantom/driver-download-info")
    async def local_computer_phantom_driver_download_info():
        """Get driver download information"""
        from driver_manager import get_driver_manager
        manager = get_driver_manager()
        info = manager.get_driver_info()
        return {
            "success": True,
            **info
        }

    @app.post("/api/local-computer/phantom/open-settings")
    async def local_computer_phantom_open_settings():
        import subprocess
        try:
            subprocess.Popen(["control", "desk.cpl"])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/local-computer/phantom/preview")
    async def local_computer_phantom_preview():
        import subprocess, sys, os, ctypes
        script_path = os.path.join(os.getcwd(), "phantom_preview_window.py")
        bat_path = os.path.join(os.getcwd(), "run_preview.bat")
        if not os.path.exists(script_path):
            # (Keeping existing script creation logic...)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("""
import cv2, numpy as np, time, sys, os
try:
    from desktop_agent import jarvis_display_manager
except ImportError:
    sys.path.append(os.getcwd())
    from desktop_agent import jarvis_display_manager

def main():
    print("Skemi Phantom Preview Window Started.")
    win_name = "Skemi Phantom - Native Preview"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1)
    
    waiting = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(waiting, "Waiting for Phantom Desktop...", (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
    cv2.putText(waiting, "Press 'Q' to exit this window", (150, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)

    while True:
        try:
            status = jarvis_display_manager.status(force=True)
            if status.get("workspace_ready"):
                img = jarvis_display_manager.capture()
                if img:
                    frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    cv2.imshow(win_name, frame)
                else:
                    cv2.imshow(win_name, waiting)
            else:
                cv2.imshow(win_name, waiting)
        except Exception as e:
            print(f"Error in preview loop: {e}")
            time.sleep(1)
        
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'): break
        try:
            if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1: break
        except: break
        
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
""")
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                # Add pause to preview bat so we can see errors
                f.write(f'@echo off\ntitle Skemi Phantom Preview\ncd /d "{os.getcwd()}"\n"{sys.executable}" "{script_path}"\necho.\necho Preview closed or failed.\npause\n')
            
            ctypes.windll.shell32.ShellExecuteW(None, "open", "cmd.exe", f'/c "{bat_path}"', os.getcwd(), 1)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/local-computer/phantom/uninstall-driver")
    async def local_computer_phantom_uninstall_driver():
        import subprocess, sys, os
        script_path = os.path.join(os.getcwd(), "uninstall_virtual_display.py")
        if not os.path.exists(script_path):
            return {"success": False, "error": "Script not found", "message": "uninstall_virtual_display.py is missing."}
        try:
            subprocess.Popen([sys.executable, script_path], cwd=os.getcwd(), creationflags=subprocess.CREATE_NEW_CONSOLE)
            return {"success": True, "message": "Uninstallation started. Please accept UAC prompt."}
        except Exception as e:
            return {"success": False, "error": str(e), "message": "Failed to launch uninstaller."}

    @app.post("/api/local-computer/phantom/toggle-virtual-display")
    async def local_computer_phantom_toggle_virtual_display():
        import subprocess, sys, os
        base_dir = os.getcwd()
        target_dir = os.path.join(base_dir, "Skemi_Virtual_Display")
        # Find deviceinstaller64.exe
        installer_path = None
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                if f.lower() == "deviceinstaller64.exe":
                    installer_path = os.path.join(root, f)
                    break
            if installer_path:
                break
        if not installer_path:
            print(f"[VIRTUAL DISPLAY ERROR] deviceinstaller64.exe not found in {target_dir}")
            return {"success": False, "error": "Installer not found", "message": "deviceinstaller64.exe not found in Skemi_Virtual_Display."}
        work_dir = os.path.dirname(installer_path)
        print(f"[VIRTUAL DISPLAY] Found installer at: {installer_path}, work_dir: {work_dir}")
        try:
            # Re-enable the virtual display
            print(f"[VIRTUAL DISPLAY] Running: enableidd 1")
            result1 = subprocess.run([installer_path, "enableidd", "1"], capture_output=True, text=True, cwd=work_dir, timeout=30)
            print(f"[VIRTUAL DISPLAY] enableidd stdout: {result1.stdout}, stderr: {result1.stderr}, returncode: {result1.returncode}")
            
            # Also restart the driver
            print(f"[VIRTUAL DISPLAY] Running: stop usbmmidd")
            result2 = subprocess.run([installer_path, "stop", "usbmmidd"], capture_output=True, text=True, cwd=work_dir, timeout=10)
            print(f"[VIRTUAL DISPLAY] stop stdout: {result2.stdout}, stderr: {result2.stderr}")
            
            inf_path = os.path.join(work_dir, "usbmmidd.inf")
            print(f"[VIRTUAL DISPLAY] Running: install {inf_path} usbmmidd")
            result3 = subprocess.run([installer_path, "install", inf_path, "usbmmidd"], capture_output=True, text=True, cwd=work_dir, timeout=30)
            print(f"[VIRTUAL DISPLAY] install stdout: {result3.stdout}, stderr: {result3.stderr}")
            
            print(f"[VIRTUAL DISPLAY] Running: enableidd 1 (final)")
            result4 = subprocess.run([installer_path, "enableidd", "1"], capture_output=True, text=True, cwd=work_dir, timeout=30)
            print(f"[VIRTUAL DISPLAY] final enableidd stdout: {result4.stdout}, stderr: {result4.stderr}")
            
            return {"success": True, "message": "Virtual display re-enabled successfully."}
        except Exception as e:
            print(f"[VIRTUAL DISPLAY ERROR] Exception: {e}")
            return {"success": False, "error": str(e), "message": "Failed to toggle virtual display."}

    @app.get("/api/local-computer/phantom/desktops")
    def local_computer_phantom_desktops():
        """v1.2.0: Synchronous def runs in FastAPI thread pool, preventing event loop block."""
        return _phantom_desktop_payload()

    @app.post("/api/local-computer/phantom/create-desktop")
    async def local_computer_phantom_create_desktop():
        """v1.2.0: Explicit endpoint for creating a new virtual desktop."""
        if not desktop_agent:
            return {"success": False, "error": "agent_missing"}
        
        try:
            res = desktop_agent.create_and_lock()
            return {
                "success": res.get("success", False),
                "guid": str(res.get("guid") or ""),
                "name": str(res.get("name") or ""),
                "index": _resolve_desktop_index_from_guid(str(res.get("guid") or "")),
                "message": res.get("message", ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/computer/desktops")
    async def get_computer_desktops():
        """v1.1.31: Return Task View desktop count and current index."""
        if not desktop_agent:
            return {"success": True, "count": 1, "current": 0}
        return {
            "success": True,
            "count": desktop_agent._get_virtual_desktop_count_sync(),
            "current": desktop_agent._get_current_virtual_desktop_index_sync(),
            "desktops": desktop_agent._get_all_desktops_sync()
        }


    @app.post("/api/local-computer/connect")
    async def local_computer_connect(req: LocalComputerConnectRequest):
        mode = _normalize_mode(str(local_computer_state.get("mode") or "live"))
        local_computer_state["status"] = "connected"
        local_computer_state["connected"] = True
        local_computer_state["consent_granted"] = bool(req.consent)
        local_computer_state["companion_version"] = req.companion_version or "built-in-native"
        local_computer_state["machine_label"] = req.machine_label or "This device"
        local_computer_state["last_seen_at"] = time.time()
        local_computer_state["notes"] = _mode_notes(mode, connected=True, running=False)
        return _local_payload()

    @app.post("/api/local-computer/create-desktop")
    async def create_local_desktop():
        status = _copy_workspace_status_to_state(_jarvis_display_status(force=True))
        if not status.get("workspace_ready"):
            return {
                "success": False,
                "status": "setup_required",
                "error": "phantom_setup_required",
                "message": str(status.get("last_launch_error") or _short_phantom_setup_message(status)),
                **_public_workspace_status(status),
            }
        token = str(local_computer_state.get("phantom_lock_token") or f"phantom-{int(time.time() * 1000)}")
        async with _local_lock:
            try:
                if not hasattr(desktop_agent, "create_and_lock"):
                    raise RuntimeError("Desktop creation helper is unavailable")
                created = desktop_agent.create_and_lock()
                if not created.get("success"):
                    raise RuntimeError(created.get("error", "Unknown error"))
                guid = created.get("guid", "")
                desktop_name = created.get("name", "")
                new_index = _resolve_desktop_index_from_guid(guid)
                if new_index < 0:
                    new_index = len(desktop_agent.get_virtual_desktops()) - 1  # Last-resort index only after GUID lookup.
                _phantom_debug(f"[CREATE] Created and locked Windows Virtual Desktop guid={guid} name={desktop_name}")
            except Exception as e:
                _phantom_debug(f"[CREATE] Failed to create desktop: {e}")
                return {
                    "success": False,
                    "status": "error",
                    "error": "desktop_create_failed",
                    "message": str(e) or "Windows không tạo được desktop mới",
                    "locked_desktop_index": -1,
                    "locked_desktop_name": "",
                }

            payload = await _start_phantom_preview_locked(desktop_index=new_index, lock_token=token, use_virtual=True)
            payload.update({
                "success": bool(payload.get("success", True)),
                "index": new_index,
                "name": desktop_name,
                "guid": guid,
                "desktop_name": desktop_name,
                "locked_desktop_index": new_index,
                "locked_desktop_name": desktop_name,
                "locked_desktop_guid": guid,
                "desktop_name": desktop_name,
                "message": f"AI đang hoạt động trên {desktop_name}",
            })
            return payload

    @app.post("/api/local-computer/switch-desktop")
    async def switch_local_desktop(req: Optional[Dict[str, Any]] = None):
        index = int((req or {}).get("index", -1))
        if desktop_agent and index >= 0:
            desktop_agent._target_desktop_index = index
            local_computer_state["target_desktop_index"] = index
            return {"status": "success", "index": index, "switched_user_view": False}
        return {
            "status": "error",
            "message": "Switching the user's visible desktop is disabled. Phantom requires a real virtual display instead.",
            "switched_user_view": False,
        }


    
    @app.post("/api/local-computer/set-target-desktop")
    async def set_target_desktop(req: Dict[str, Any]):
        """Set target desktop for Phantom mode - handles both new desktop creation and existing desktop selection."""
        if not desktop_agent:
            return {"status": "error", "message": "Desktop agent not initialized."}
        
        # v6.8 FIX: Get request parameters correctly
        index = _int_or(req.get("index"), -1)
        action = str(req.get("action") or "").lower().strip()  # "create" or "select"
        token = str(req.get("lock_token") or "").strip()
        
        # Check workspace status
        workspace_status = _jarvis_display_status(force=True)
        if not workspace_status.get("workspace_ready"):
            return {
                "status": "error",
                "error": "phantom_setup_required",
                "message": workspace_status.get("last_launch_error") or "Phantom Desktop chưa sẵn sàng.",
                "locked_desktop_index": -1,
                "locked_desktop_name": "",
            }
        
        # Get available desktops
        try:
            all_desktops = desktop_agent._get_all_desktops_sync()
            desktop_count = len(all_desktops) if all_desktops else 1
        except Exception:
            desktop_count = 1
            all_desktops = []
        
        # Handle desktop selection/creation logic
        if action == "create" or index == -1:
            # Create new desktop
            try:
                if hasattr(desktop_agent, "create_new_desktop"):
                    created = desktop_agent.create_new_desktop()
                    index = _int_or(created.get("index"), -1)
                else:
                    raise RuntimeError("Desktop creation helper is unavailable")
                if index < 0:
                    raise RuntimeError("Windows did not return a valid desktop index")
            except Exception as e:
                _phantom_debug(f"[DESKTOP CREATE] Failed to create new desktop: {e}")
                return {
                    "status": "error",
                    "error": "desktop_create_failed",
                    "message": str(e) or "Windows không tạo được desktop mới",
                    "locked_desktop_index": -1,
                    "locked_desktop_name": "",
                }
        elif index >= 0:
            # Validate selected desktop exists
            if desktop_count > 0 and index >= desktop_count:
                return {
                    "status": "error",
                    "message": f"Desktop index {index} không tồn tại. Hiện có {desktop_count} desktop.",
                    "available_count": desktop_count,
                    "locked_desktop_index": -1,
                }
        else:
            # index is -1 and action is not "create" - ask user to create or select
            if desktop_count <= 1:
                return {
                    "status": "requires_action",
                    "message": "Chỉ có 1 desktop. Vui lòng tạo desktop mới hoặc sử dụng chế độ Live Control.",
                    "action_required": "create_desktop",
                    "available_count": desktop_count,
                }
            else:
                return {
                    "status": "requires_selection",
                    "message": "Vui lòng chọn desktop hoặc tạo desktop mới.",
                    "available_count": desktop_count,
                }
        
        # Lock to the target desktop
        if index >= 0:
            if not token:
                token = f"phantom-{int(time.time() * 1000)}"
            
            _set_phantom_lock(index, token)
            local_computer_state["use_virtual_display"] = True
            if token:
                _schedule_phantom_heartbeat_release(token, str(local_computer_state.get("session_id") or ""))
            
            desktop_name = _phantom_desktop_name(index)
            return {
                "status": "success",
                "index": index,
                "locked_desktop_index": index,
                "locked_desktop_name": desktop_name,
                "use_virtual_display": True,
                "message": f"Đã khóa AI vào {desktop_name}.",
            }
        
        return {"status": "error", "message": "Could not determine target desktop."}

    @app.post("/api/local-computer/phantom/lock")
    async def local_computer_phantom_lock(req: LocalComputerPhantomLockRequest):
        try:
            index = _int_or(req.desktop_index, -1)
            desktop_guid = str(req.desktop_guid or "").strip()
            if index < 0 and desktop_guid:
                index = _resolve_desktop_index_from_guid(desktop_guid)
            if index < 0:
                return {
                    "success": False,
                    "ok": False,
                    "error": "desktop_required",
                    "message": "Choose an existing desktop or create a new desktop before starting Phantom.",
                    "locked_desktop_index": -1,
                    "locked_desktop_name": "",
                }
            workspace_status = _jarvis_display_status(force=False)
            if not bool(workspace_status.get("workspace_ready")):
                # If not ready, do ONE force scan to be sure (with timeout)
                try:
                    workspace_status = await asyncio.wait_for(
                        asyncio.to_thread(_jarvis_display_status, True),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    pass  # Use the non-forced status if force check times out
            if not bool(workspace_status.get("workspace_ready")) or bool(workspace_status.get("update_required")):
                status = _copy_workspace_status_to_state(workspace_status)
                local_computer_state["mode"] = "phantom"
                local_computer_state["surface_mode"] = "phantom"
                local_computer_state["local_state"] = "phantom_blocked"
                payload = _local_payload()
                payload.update(_phantom_desktop_payload())
                payload.update({
                    "success": False,
                    "error": "phantom_setup_required",
                    "message": str(status.get("last_launch_error") or _short_phantom_setup_message(status)),
                    **_public_workspace_status(status),
                })
                return payload
            token = str(req.lock_token or "").strip()
            if not token:
                token = f"phantom-{int(time.time() * 1000)}"
            async with _local_lock:
                _set_phantom_lock(index, token, desktop_guid=desktop_guid)
                # Add timeout protection for session startup (10-second hard limit)
                try:
                    payload = await asyncio.wait_for(
                        _start_phantom_preview_locked(desktop_index=index, lock_token=token, use_virtual=True),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    # If session startup times out, return partial success with minimal state
                    payload = {
                        "success": False,
                        "ok": False,
                        "error": "session_startup_timeout",
                        "message": "Phantom session startup timeout. Please try again.",
                        "locked_desktop_index": index,
                        "locked_desktop_name": _phantom_desktop_name(index),
                        "workspace_ready": False,
                        "task_state": "timeout"
                    }
            payload["success"] = bool(payload.get("workspace_ready", False)) and str(payload.get("task_state") or "").lower() not in {"blocked", "error", "timeout"}
            payload["locked_desktop_index"] = index
            payload["locked_desktop_name"] = str(local_computer_state.get("locked_desktop_name") or _phantom_desktop_name(index))
            payload["locked_desktop_guid"] = str(local_computer_state.get("locked_desktop_guid") or desktop_guid or "")
            payload["desktop_name"] = payload["locked_desktop_name"]
            payload["workspace_label"] = payload["locked_desktop_name"]
            payload["public_display_label"] = payload["locked_desktop_name"]
            payload["message"] = f"AI đang hoạt động trên {payload['locked_desktop_name']}"
            payload["display_id"] = str(local_computer_state.get("display_id") or payload.get("display_id") or "") if _phantom_debug_enabled() else ""
            payload["stream_url"] = str(payload.get("stream_url") or "/api/local-computer/mjpeg")
            return payload
        except Exception as e:
            _phantom_debug(f"[PHANTOM LOCK ERROR] {e}")
            return {
                "success": False,
                "ok": False,
                "error": "internal_server_error",
                "message": "Internal server error while locking Phantom. See backend logs for details.",
                "locked_desktop_index": -1,
                "locked_desktop_name": "",
            }

    @app.post("/api/local-computer/phantom/heartbeat")
    async def local_computer_phantom_heartbeat(req: LocalComputerPhantomHeartbeatRequest):
        token = str(req.lock_token or "").strip()
        session_id = str(req.session_id or "").strip()
        current = str(local_computer_state.get("phantom_lock_token") or "").strip()
        if not token or not current or token != current:
            return {"success": False, "active": False, "reason": "lock token is missing or expired"}
        local_computer_state["phantom_lock_active"] = True
        local_computer_state["phantom_lock_last_heartbeat"] = time.time()
        local_computer_state["mode"] = "phantom"
        local_computer_state["surface_mode"] = "phantom"
        local_computer_state["last_seen_at"] = time.time()
        _schedule_phantom_heartbeat_release(token, session_id or str(local_computer_state.get("session_id") or ""))
        payload = _local_payload()
        payload["success"] = True
        payload["active"] = True
        return payload

    @app.post("/api/local-computer/reveal")
    async def reveal_local_app():
        """Pull the AI's target window back to the user's Default desktop."""
        try:
            # We need to find the active session to reveal its window
            for session in desktop_agent.active_sessions.values():
                session.reveal_target_window()
            return {"status": "success", "message": "Attempting to reveal target windows."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/local-computer/mode")
    async def local_computer_mode(req: LocalComputerModeRequest):
        mode = _normalize_mode(req.mode)
        desktop_index = _int_or(req.desktop_index if req.desktop_index is not None else local_computer_state.get("target_desktop_index", -1), -1)
        lock_token = str(req.lock_token or "").strip()
        if desktop_index >= 0:
            local_computer_state["target_desktop_index"] = desktop_index
            if desktop_agent:
                desktop_agent._target_desktop_index = desktop_index
        if lock_token:
            local_computer_state["phantom_lock_token"] = lock_token
        if mode == "phantom":
            workspace_status = _jarvis_display_status(force=True)
            if desktop_index < 0:
                desktop_index = _int_or(local_computer_state.get("locked_desktop_index"), -1)
            if desktop_index < 0:
                return {
                    "success": False,
                    "ok": False,
                    "error": "desktop_required",
                    "message": "Choose an existing desktop or create a new desktop before starting Phantom.",
                    "locked_desktop_index": -1,
                    "locked_desktop_name": "",
                }
            local_computer_state["target_desktop_index"] = desktop_index
            async with _local_lock:
                payload = await _start_phantom_preview_locked(desktop_index=desktop_index, lock_token=lock_token, use_virtual=True)
            if desktop_agent:
                desktop_agent.agent_module_update_mode("phantom")
            return payload
        if mode == "live":
            async with _local_lock:
                payload = await _start_live_viewer_locked(preserve_lock=bool(req.preserve_lock))
            if desktop_agent:
                desktop_agent.agent_module_update_mode("live")
            return payload
        local_computer_state["mode"] = mode
        if mode != "phantom":
            _cancel_phantom_heartbeat_task()
            _clear_phantom_lock_fields()
        local_computer_state["last_seen_at"] = time.time()
        local_computer_state["notes"] = _mode_notes(mode, connected=bool(local_computer_state.get("connected")), running=False)
        
        if desktop_agent:
            desktop_agent.agent_module_update_mode(mode)
            
        return _local_payload()

    @app.post("/api/local-computer/phantom/start")
    async def local_computer_phantom_start(req: LocalComputerModeRequest):
        use_virtual = True
        desktop_index = _int_or(req.desktop_index if req.desktop_index is not None else -1, -1)
        if desktop_index < 0:
            desktop_index = _int_or(local_computer_state.get("locked_desktop_index"), -1)
        if desktop_index < 0:
            desktop_index = _int_or(local_computer_state.get("target_desktop_index"), -1)
        if desktop_index < 0:
            return {
                "success": False,
                "ok": False,
                "error": "desktop_required",
                "message": "Choose an existing desktop or create a new desktop before starting Phantom.",
                "locked_desktop_index": -1,
                "locked_desktop_name": "",
            }
        lock_token = str(req.lock_token or "").strip()
            
        local_computer_state["use_virtual_display"] = True
        local_computer_state["target_desktop_index"] = desktop_index
        if desktop_agent:
            desktop_agent._target_desktop_index = desktop_index
        if lock_token:
            local_computer_state["phantom_lock_token"] = lock_token
        async with _local_lock:
            return await _start_phantom_preview_locked(desktop_index=desktop_index, lock_token=lock_token, use_virtual=use_virtual)

    @app.post("/api/local-computer/phantom/release")
    @app.post("/api/local-computer/release-phantom-lock")
    async def release_phantom_lock(req: LocalComputerPhantomReleaseRequest):
        async with _local_lock:
            # v1.2.5: IMMEDIATE RELEASE - User requested stop, don't wait.
            token = str(req.lock_token or "").strip()
            current_token = str(local_computer_state.get("phantom_lock_token") or "").strip()
            if token and current_token and token != current_token:
                return {"success": False, "ignored": True, "reason": "token mismatch"}
            
            _cancel_phantom_release_task()
            _cancel_phantom_heartbeat_task()
            await _stop_current_session_locked("User explicitly released Phantom lock.")
            local_computer_state["mode"] = "live"
            local_computer_state["surface_mode"] = "live"
            _clear_phantom_lock_fields()
            local_computer_state["preview_only"] = False
            if desktop_agent:
                with contextlib.suppress(Exception):
                    desktop_agent.agent_module_update_mode("live")
            return {"success": True, "message": "Phantom lock released immediately."}
    
    @app.post("/api/local-computer/run")
    async def local_computer_run(req: LocalComputerRunRequest):
        global _local_task
        command = str(req.command or "").strip()
        if not command:
            return {"success": False, "error": "Missing local computer command."}
        mode = _normalize_mode(req.mode or str(local_computer_state.get("mode") or "live"))
        if not req.consent and not local_computer_state.get("consent_granted"):
            return {"success": False, "error": "Local Computer requires explicit consent before running."}
        source = str(req.source or "manual").strip().lower()
        # ==== UNIFIED AGENT: every desktop command runs on the iso agent (UIA tree
        # + PostMessage ghost-input; it NEVER touches the physical mouse or focus).
        # This legacy pipeline below drove the screen with real SendInput/cursor
        # moves → "chuột giật liên tục, mất focus", and its blind vision typed the
        # message into the wrong window (the My Documents incident). Delegate and
        # return the finished result directly; legacy code runs ONLY if the
        # delegation itself crashes.
        try:
            import Server as _srv
            res = await _srv.iso_run_unified(command)
            summary = str((res or {}).get("summary") or (res or {}).get("error") or "Hoàn thành.")
            ok = bool((res or {}).get("success"))
            local_computer_state["status"] = "done"
            local_computer_state["task_state"] = "done" if ok else "error"
            local_computer_state["last_ai_action_desc"] = summary
            local_computer_state["final_result"] = summary
            return {
                "success": True, "ok": True, "status": "done",
                "task_state": "done" if ok else "error",
                "final_result": summary, "last_ai_action_desc": summary,
                "session_id": "", "execution_surface": "iso_agent",
                "stream_url": str(local_computer_state.get("stream_url") or "/api/local-computer/mjpeg"),
            }
        except Exception as _iso_exc:
            # Do NOT fall through to the legacy desktop_agent pipeline below: it
            # drives the screen with REAL SendInput/SetCursorPos (the user's #1
            # complaint — "chuột giật liên tục, mất focus") and needs a vision model
            # that isn't installed. If the iso agent itself failed, the legacy path
            # would be worse, not a recovery. Return a clean error instead so the
            # ghost-input guarantee is never silently broken.
            with contextlib.suppress(Exception):
                print(f"[UNIFIED] iso delegation failed: {_iso_exc!r}")
            msg = "Không khởi tạo được môi trường AI. Hãy thử lại."
            local_computer_state["status"] = "error"
            local_computer_state["task_state"] = "error"
            local_computer_state["last_ai_action_desc"] = msg
            local_computer_state["final_result"] = msg
            return {"success": False, "ok": False, "status": "error",
                    "task_state": "error", "final_result": msg,
                    "last_ai_action_desc": msg, "session_id": "",
                    "execution_surface": "iso_agent"}
        desktop_index = _int_or(req.desktop_index if req.desktop_index is not None else -1, -1)
        if desktop_index < 0:
            desktop_index = _int_or(local_computer_state.get("target_desktop_index"), -1)
        lock_token = str(req.lock_token or "").strip()
        if mode != "phantom":
            # Live Control: the AI operates the user's REAL desktop directly using
            # background ghost-input (PostMessage to the window under each target
            # point). It never moves the physical cursor or steals focus, so the
            # user keeps full control of their mouse/keyboard. No virtual display
            # or desktop lock is required — we act on whatever is already on screen.
            mode = "live"
            local_computer_state["mode"] = "live"
            local_computer_state["surface_mode"] = "live"
            local_computer_state["local_state"] = "live_control"
            local_computer_state["status"] = "thinking"
            local_computer_state["task_state"] = "thinking"
            local_computer_state["last_ai_action_desc"] = "Đang phân tích yêu cầu của bạn" if source == "voice" else "Analyzing your request"
        if mode == "phantom":
            if desktop_index < 0:
                desktop_index = _int_or(local_computer_state.get("locked_desktop_index"), -1)
            if desktop_index < 0:
                return {
                    "success": False,
                    "error": "desktop_required",
                    "message": "Choose an existing desktop or create a new desktop before running AI.",
                    "locked_desktop_index": -1,
                    "locked_desktop_name": "",
                }
            _set_phantom_lock(desktop_index, lock_token)
            if lock_token:
                _schedule_phantom_heartbeat_release(lock_token, str(local_computer_state.get("session_id") or ""))
            _cancel_phantom_release_task()
        
        # v54.9: Support session reuse
        existing_sid = str(local_computer_state.get("session_id") or "").strip()
        existing_task_active = bool(existing_sid and _local_task and not _local_task.done())
        workspace_status = _jarvis_display_status(force=True) if mode == "phantom" else {}
        if (
            mode == "phantom"
            and workspace_status
            and (not workspace_status.get("workspace_ready") or bool(workspace_status.get("update_required")))
        ):
            if existing_task_active:
                async with _local_lock:
                    await _stop_current_session_locked("Phantom Desktop unavailable; unsafe Local Computer session stopped.")
                existing_task_active = False
            reason = str(workspace_status.get("last_launch_error") or _short_phantom_setup_message(workspace_status))
            return _set_jarvis_display_block(reason, workspace_status, route="computer_task")
        # v1.0.2: Provide immediate 'thinking' feedback
        local_computer_state["status"] = "thinking"
        local_computer_state["task_state"] = "thinking"
        local_computer_state["last_ai_action_desc"] = "Đang phân tích yêu cầu của bạn" if source == "voice" else "Analyzing your request"

        router_plan = {
            "route": "computer_task",
            "confidence": 1.0,
            "tasks": [{"action": "gui", "goal": command, "status": "pending"}],
            "requires_consent": False,
            "consent_reason": "",
        }

        if existing_task_active:
            router_plan["reuse_session_id"] = existing_sid
        router_plan["desktop_index"] = desktop_index

        route = str(router_plan.get("route") or "clarify")
        if _phantom_debug_enabled():
            print(f"[LOCAL ROUTER] {command!r} -> {route} (confidence={router_plan.get('confidence')})")
        local_computer_state["route"] = route
        local_computer_state["tasks"] = list(router_plan.get("tasks") or [])
        local_computer_state["current_task_index"] = 0 if local_computer_state["tasks"] else -1
        local_computer_state["requires_consent"] = bool(router_plan.get("requires_consent", False))
        local_computer_state["consent_reason"] = str(router_plan.get("consent_reason") or "")
        local_computer_state["voice_route"] = route
        _append_event({"type": "route_decided", "route": route, "confidence": router_plan.get("confidence"), "tasks": router_plan.get("tasks") or []})

        if route == "chat":
            reply = str(router_plan.get("reply") or "").strip() or await _voice_chat_reply(command)
            local_computer_state["status"] = "connected"
            local_computer_state["task_state"] = "done"
            local_computer_state["final_result"] = reply
            local_computer_state["last_ai_action_desc"] = reply
            local_computer_state["notes"] = [reply] + list(local_computer_state.get("notes") or [])[:2]
            _append_event({"type": "final_result", "route": route, "result": reply, "task_state": "done"})
            if source == "voice":
                _queue_voice_reply(reply, force=True)
                local_computer_state["voice_phase"] = "listening"
                local_computer_state["voice_state"] = "listening"
            return _local_payload()

        if route == "clarify":
            reply = str(router_plan.get("reply") or "Mình chưa hiểu đủ rõ để làm an toàn. Bạn nói cụ thể hơn một chút nhé?").strip()
            local_computer_state["status"] = "connected"
            local_computer_state["task_state"] = "blocked"
            local_computer_state["automation_mode"] = "blocked"
            local_computer_state["final_result"] = reply
            local_computer_state["last_ai_action_desc"] = reply
            local_computer_state["notes"] = [reply] + list(local_computer_state.get("notes") or [])[:2]
            _append_event({"type": "final_result", "route": route, "result": reply, "task_state": "blocked"})
            if source == "voice":
                _queue_voice_reply(reply, force=True)
                local_computer_state["voice_phase"] = "listening"
                local_computer_state["voice_state"] = "listening"
            return _local_payload()

        if route == "stop":
            async with _local_lock:
                current = str(local_computer_state.get("last_ai_action_desc") or "").strip()
                await _stop_current_session_locked("User requested stop.")
                reply = f"Đã dừng tác vụ. Trạng thái gần nhất: {current or 'chưa có bước đang chạy rõ ràng.'}"
                local_computer_state["status"] = "stopped"
                local_computer_state["task_state"] = "stopped"
                local_computer_state["final_result"] = reply
                local_computer_state["last_ai_action_desc"] = reply
                local_computer_state["notes"] = [reply] + _mode_notes(mode, connected=True, running=False)[:2]
                _append_event({"type": "final_result", "route": route, "result": reply, "task_state": "stopped"})
            if source == "voice":
                _queue_voice_reply(reply, force=True)
                local_computer_state["voice_phase"] = "listening"
                local_computer_state["voice_state"] = "listening"
            return _local_payload()

        if route == "consent_required":
            reason = str(router_plan.get("consent_reason") or "Tác vụ này có thể ảnh hưởng tới tài khoản, dữ liệu hoặc hành động gửi/xóa/thay đổi.").strip()
            local_computer_state["status"] = "awaiting_confirmation"
            local_computer_state["task_state"] = "awaiting_consent"
            local_computer_state["requires_consent"] = True
            local_computer_state["consent_reason"] = reason
            local_computer_state["pending_confirmation"] = {
                "type": "consent_required",
                "command": command,
                "reason": reason,
                "plan": router_plan,
            }
            local_computer_state["last_ai_action_desc"] = reason
            local_computer_state["notes"] = [reason] + _mode_notes(mode, connected=True, running=False)[:2]
            _append_event({"type": "consent_required", "route": route, "message": reason, "tasks": router_plan.get("tasks") or []})
            if source == "voice":
                _queue_voice_reply(reason, force=True)
            return _local_payload()

        if mode == "phantom" and workspace_status and not workspace_status.get("workspace_ready"):
            reason = str(workspace_status.get("last_launch_error") or _short_phantom_setup_message(workspace_status))
            if existing_task_active:
                async with _local_lock:
                    await _stop_current_session_locked("Phantom Desktop unavailable; unsafe Local Computer session stopped.")
                existing_task_active = False
            if source == "voice":
                _queue_voice_reply(reason, force=True)
            return _set_jarvis_display_block(reason, workspace_status, route=route)

        async with _local_lock:
            reuse_existing = bool(str(router_plan.get("reuse_session_id") or "").strip() and existing_task_active)
            if workspace_status:
                workspace_status = _copy_workspace_status_to_state(workspace_status)
            if not reuse_existing:
                await _stop_current_session_locked("Previous Local Computer session stopped before starting a new one.")
            local_computer_state["mode"] = mode
            local_computer_state["connected"] = True
            local_computer_state["consent_granted"] = True
            local_computer_state["machine_label"] = "This device"
            local_computer_state["status"] = "starting"
            local_computer_state["task_state"] = "launching"
            local_computer_state["stream_state"] = "connecting"
            local_computer_state["automation_mode"] = "blocked"
            local_computer_state["local_state"] = "phantom_running" if mode == "phantom" else "live_control"
            local_computer_state["surface_mode"] = mode
            local_computer_state["preview_only"] = False
            local_computer_state["final_result"] = ""
            local_computer_state["is_voice_session"] = source == "voice"
            if mode == "phantom" and workspace_status and not workspace_status.get("workspace_ready"):
                local_computer_state["notes"] = [str(workspace_status.get("last_launch_error") or "Phantom virtual display is not ready.")]
            else:
                local_computer_state["notes"] = ["Đang chuẩn bị Local Computer..."]
            if not (mode == "phantom" and workspace_status and not workspace_status.get("workspace_ready")):
                local_computer_state["notes"] = [f"AI controlling {_workspace_label(desktop_index)}." if mode == "phantom" else "Live Control active — AI is operating your desktop via ghost-input."]
            agent_mode = _agent_mode(mode)
            session_id, event_generator = await desktop_companion.desktop_companion_host.start_session(
                command,
                mode=agent_mode,
                bypass_safety=True,
                plan=router_plan,
                source=source,
                desktop_index=desktop_index,
            )
            local_computer_state["session_id"] = session_id
            local_computer_state["status"] = "running"
            local_computer_state["task_state"] = "working"
            local_computer_state["stream_url"] = "/api/local-computer/mjpeg"
            local_computer_state["notes"] = _mode_notes(mode, connected=True, running=True)
            _append_event({"type": "started", "session_id": session_id, "mode": mode, "command": command, "route": route, "tasks": router_plan.get("tasks") or [], "desktop_index": desktop_index})
            if not (reuse_existing and session_id == existing_sid):
                _local_task = asyncio.create_task(_consume_desktop_events(session_id, event_generator, mode), name=f"skemi-local-{session_id}")
        return _local_payload()

    @app.get("/api/local-computer/events")
    async def local_computer_events():
        return {"success": True, "events": list(_local_events), "state": _local_payload()}

    @app.post("/api/local-computer/disconnect")
    async def local_computer_disconnect():
        async with _local_lock:
            await _stop_current_session_locked("Local companion disconnected.")
            local_computer_state["connected"] = False
            local_computer_state["consent_granted"] = False
            local_computer_state["stream_url"] = ""
        return _local_payload()

    @app.post("/api/local-computer/voice/toggle")
    async def local_computer_voice_toggle():
        current = bool(local_computer_state.get("voice_control_enabled", False))
        next_state = not current
        local_computer_state["connected"] = True
        local_computer_state["machine_label"] = "This device"
        local_computer_state["last_seen_at"] = time.time()
        
        if next_state:
            enabled = await desktop_companion.desktop_companion_host.start_voice_control()
            local_computer_state["voice_control_enabled"] = bool(enabled)
            if enabled:
                if str(local_computer_state.get("status") or "") in {"idle", "connected", ""}:
                    local_computer_state["status"] = "connected"
                local_computer_state["voice_phase"] = "listening"
                local_computer_state["voice_transcript"] = ""
                local_computer_state["last_ai_action_desc"] = ""
            else:
                local_computer_state["voice_phase"] = "error"
                local_computer_state["last_ai_action_desc"] = "Lỗi mic."
            return _local_payload()
        else:
            await desktop_companion.desktop_companion_host.stop_voice_control()
            local_computer_state["voice_control_enabled"] = False
            local_computer_state["voice_phase"] = "standby"
            local_computer_state["voice_state"] = "standby"
            local_computer_state["voice_transcript"] = ""
            return _local_payload()

    @app.get("/api/local-computer/mjpeg")
    async def local_computer_mjpeg():
        from fastapi.responses import StreamingResponse as _MJPEGResponse
        async def frame_gen():
            last_v = -1
            last_placeholder_at = 0.0
            last_direct_capture_at = 0.0
            have_direct = False  # v9.1: once a real frame is served, never flicker back to placeholder
            placeholder = b""
            placeholder_key = ""
            while True:
                # ==== UNIFIED MODE: stream the iso desktop — the app window the AI
                # is working on, or its clean placeholder. NEVER the user's physical
                # screen: the old companion loop captured the real desktop
                # continuously, which (a) leaked the user's screen into the viewer
                # after the app closed and (b) loaded the GPU → mouse stutter.
                iso_frame = b""
                try:
                    import Server as _srv
                    # GET, never CREATE: a viewer tab connecting must not spawn a
                    # Live-Control desktop (+ enable the IDD) as a side effect. Only
                    # stream once a real command has created the shared desktop;
                    # until then fall through to the clean placeholder below.
                    mgr = _srv._iso_mgr()
                    uid = _srv._UNIFIED_ISO.get("id") or ""
                    d = mgr.get(uid) if uid else None
                    if d is not None:
                        iso_frame = await asyncio.to_thread(d.capture_jpeg, 70)
                except Exception:
                    iso_frame = b""
                if iso_frame:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + iso_frame + b"\r\n")
                    await asyncio.sleep(0.30)
                    continue
                # No iso desktop yet (no command has run). Serve a NEUTRAL placeholder
                # and loop — do NOT fall through to the legacy direct-capture path
                # below, which screen-grabs the user's PHYSICAL desktop (the "tắt app
                # rồi nó stream màn hình vật lý" bug). The legacy block is kept only
                # as dead fallback for non-unified deployments.
                with contextlib.suppress(Exception):
                    from io import BytesIO as _BIO
                    from PIL import Image as _PImg, ImageDraw as _PDraw
                    ph_img = _PImg.new("RGB", (1280, 720), (16, 18, 30))
                    _PDraw.Draw(ph_img).text(
                        (430, 340), "Skemi — chưa có ứng dụng nào",
                        fill=(150, 160, 190))
                    _b = _BIO(); ph_img.save(_b, format="JPEG", quality=70)
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _b.getvalue() + b"\r\n")
                await asyncio.sleep(0.5)
                continue
                curr_v = int(local_computer_state.get("frame_version") or 0)
                if curr_v != last_v and _latest_frame:
                    last_v = curr_v
                    have_direct = True
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _latest_frame + b"\r\n")
                elif not _latest_frame:
                    # v9.0: Direct capture fallback — if companion hasn't produced
                    # frames yet but workspace is ready, capture directly from the
                    # server process so the MJPEG stream isn't stuck on placeholder.
                    now = time.time()
                    direct_frame = b""
                    if (now - last_direct_capture_at) > 0.18 and bool(local_computer_state.get("workspace_ready")):
                        last_direct_capture_at = now
                        try:
                            import desktop_agent as _da
                            img = _da.jarvis_display_manager.capture()
                            if img is not None:
                                from io import BytesIO as _BIO
                                buf = _BIO()
                                img.convert("RGB").save(buf, format="JPEG", quality=70)
                                direct_frame = buf.getvalue()
                        except Exception:
                            pass
                    if direct_frame:
                        have_direct = True
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + direct_frame + b"\r\n")
                    elif not have_direct and now - last_placeholder_at > 2.0:
                        # Only show the "getting ready" placeholder until the first real
                        # frame arrives. After that we hold the last live frame (the client
                        # keeps the most recent MJPEG part) instead of flickering.
                        last_placeholder_at = now
                        status_text = str(local_computer_state.get("last_launch_error") or local_computer_state.get("last_ai_action_desc") or "Phantom Desktop is getting ready...")
                        if status_text != placeholder_key or not placeholder:
                            placeholder_key = status_text
                            placeholder = _placeholder_svg(status_text)
                        yield (b"--frame\r\nContent-Type: image/svg+xml\r\n\r\n" + placeholder + b"\r\n")
                await asyncio.sleep(0.04 if _latest_frame else (0.18 if have_direct else 0.25))
        return _MJPEGResponse(frame_gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    async def on_voice_command_triggered(cmd: str):
        try:
            global _last_voice_progress_spoken_at, _last_voice_progress_text
            mode = _normalize_mode(str(local_computer_state.get("mode") or "live"))
            local_computer_state["voice_transcript"] = cmd
            local_computer_state["voice_phase"] = "dispatching"
            local_computer_state["voice_state"] = "dispatching"
            local_computer_state["voice_route"] = "routing"
            local_computer_state["connected"] = True
            local_computer_state["last_seen_at"] = time.time()
            local_computer_state["status"] = "starting"
            local_computer_state["is_voice_session"] = True
            local_computer_state["last_ai_action_desc"] = f"Đang hiểu yêu cầu bằng giọng nói: {cmd}"
            local_computer_state["notes"] = [local_computer_state["last_ai_action_desc"]] + _mode_notes(mode, connected=True, running=True)[:2]
            _last_voice_progress_spoken_at = 0.0
            _last_voice_progress_text = ""
            _append_event({"type": "voice_command_received", "command": cmd, "mode": mode})
            await local_computer_run(LocalComputerRunRequest(command=cmd, mode=mode, consent=True, source="voice"))
        except Exception as e:
            print(f"[VOICE ERROR] Failed to execute voice command: {e}")
            local_computer_state["voice_phase"] = "error"
            local_computer_state["last_ai_action_desc"] = f"Voice gặp lỗi khi xử lý yêu cầu: {e}"
            _queue_voice_reply(local_computer_state["last_ai_action_desc"], force=True)

    desktop_companion.desktop_companion_host.voice_event_callback = on_voice_status
    desktop_companion.desktop_companion_host.voice_callback = on_voice_command_triggered

    # v7.1: Monitor to turn off voice if client disconnects
    async def _voice_disconnect_monitor():
        while True:
            await asyncio.sleep(5)
            if local_computer_state.get("voice_control_enabled"):
                last_seen = float(local_computer_state.get("last_seen_at", time.time()))
                if time.time() - last_seen > 30:
                    print("[VOICE MONITOR] Client disconnected (no status poll > 30s). Stopping voice control.")
                    await desktop_companion.desktop_companion_host.stop_voice_control()
                    local_computer_state["voice_control_enabled"] = False
                    local_computer_state["voice_phase"] = "standby"
                    local_computer_state["voice_state"] = "standby"
                    local_computer_state["voice_transcript"] = ""

    @app.on_event("startup")
    async def start_voice_monitor():
        asyncio.create_task(_voice_disconnect_monitor())
