import asyncio
import contextlib
import ctypes
import difflib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from ctypes import wintypes
from typing import Any, Dict, Iterable, List, Optional, Tuple


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDD_KEYWORDS = (
    "idd", "indirect", "virtualdisplay", "virtual display", "mttvdd", "itsmikethetech",
    # USBMMIDD (Amyuni) shows up as "Generic Non-PnP Monitor" with "Default_Monitor" hardware ID
    "usbmmidd", "usbmm", "amyuni", "default_monitor", "non-pnp", "nonpnp",
    # ParsecVDD and other modern IDDs
    "parsec", "parsecvdd",
)
# Split the IDD signatures by confidence. STRONG terms only ever appear on a real
# virtual-display ADAPTER (Amyuni / USBMMIDD / Parsec / itsmikethetech IDD), so
# matching them outright is safe. WEAK terms ("Generic Non-PnP Monitor" /
# "Default_Monitor") ALSO appear on ordinary physical monitors, so they must never
# be enough ON THEIR OWN to choose a display to stream — otherwise we end up
# capturing the user's real second monitor instead of the phantom display.
STRONG_IDD_KEYWORDS = (
    "idd", "indirect", "virtualdisplay", "virtual display", "mttvdd",
    "itsmikethetech", "usbmmidd", "usbmm", "amyuni", "usb mobile monitor",
    "mobile monitor", "parsec", "parsecvdd",
)
WEAK_IDD_KEYWORDS = ("default_monitor", "non-pnp", "nonpnp", "non pnp")
LLM_ACTION_KEYS = (
    "action",
    "app",
    "window_title",
    "element_name",
    "element_type",
    "text",
    "key",
    "description",
    "done",
    "summary",
)


try:
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore
    import win32process  # type: ignore
    import win32ui  # type: ignore
except Exception:
    win32api = None  # type: ignore
    win32con = None  # type: ignore
    win32gui = None  # type: ignore
    win32process = None  # type: ignore
    win32ui = None  # type: ignore

try:
    import numpy as np  # type: ignore
    from PIL import Image  # type: ignore
except Exception:
    np = None  # type: ignore
    Image = None  # type: ignore

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack  # type: ignore
    from av import VideoFrame  # type: ignore
    AIORTC_AVAILABLE = True
except Exception:
    RTCPeerConnection = None  # type: ignore
    RTCSessionDescription = None  # type: ignore
    VideoFrame = None  # type: ignore
    AIORTC_AVAILABLE = False

    class VideoStreamTrack:  # type: ignore
        kind = "video"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


locked_desktop_guid: str = ""
locked_desktop_name: str = ""
locked_idd_rect: List[int] = []
ai_phantom_active = False
_pcs: set = set()
# Tracks every window the Phantom agent has spawned this session.
# `get_desktop_state` returns these instead of filtering by Windows virtual
# desktop GUID — windows actually live at the IDD rect on the user's CURRENT
# desktop (off-screen for the physical monitor, visible on the IDD monitor for
# BitBlt). Moving them to a separate Windows virtual desktop would hide them
# from BitBlt because Windows virtual desktops are global per session, not
# per-monitor. This keeps the WebRTC stream non-empty while still meeting the
# "user is not switched" requirement.
_ai_windows: set = set()

_mouse_hook_handle = None
_mouse_hook_callback_ref = None
_mouse_hook_thread: Optional[threading.Thread] = None

# --- Display-change listener -------------------------------------------------
# A long-lived headless process (the Skemi server) freezes its GDI view of the
# monitors at first use: EnumDisplayMonitors / GetMonitorInfo return whatever was
# true when the process started and NEVER update, because the OS only refreshes a
# process's display cache after it pumps a WM_DISPLAYCHANGE message — which needs a
# top-level window + message loop. Without this, the server can report the IDD as
# "not found" or at a stale resolution/position even though it changed. We spin up
# a hidden window + pump in a daemon thread so the server stays current.
_display_listener_thread: Optional[threading.Thread] = None
_display_listener_started = False


def _ensure_display_change_listener() -> None:
    global _display_listener_thread, _display_listener_started
    if _display_listener_started or os.name != "nt":
        return
    _display_listener_started = True

    def _run() -> None:
        try:
            import win32gui  # type: ignore
            import win32con  # type: ignore

            def _wndproc(hwnd, msg, wparam, lparam):
                # WM_DISPLAYCHANGE (0x007E) arrives here; DefWindowProc + the act of
                # having pumped it is what refreshes this process's monitor cache.
                return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

            wc = win32gui.WNDCLASS()
            wc.lpszClassName = "SkemiDisplayListener"
            wc.lpfnWndProc = _wndproc
            try:
                atom = win32gui.RegisterClass(wc)
            except Exception:
                atom = "SkemiDisplayListener"
            hwnd = win32gui.CreateWindow(
                atom, "SkemiDisplayListener", 0, 0, 0, 0, 0, 0, 0, 0, 0, None)
            while True:
                win32gui.PumpWaitingMessages()
                time.sleep(0.2)
        except Exception:
            pass

    _display_listener_thread = threading.Thread(
        target=_run, name="skemi-display-listener", daemon=True)
    _display_listener_thread.start()
_mouse_hook_stop: Optional[threading.Event] = None
_mouse_boundary_rect: Tuple[int, int, int, int] = (0, 0, 0, 0)


class _WinGuid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_uuid_text(value: str) -> "_WinGuid":
    raw = uuid.UUID(str(value).strip("{}")).bytes_le
    guid = _WinGuid()
    guid.Data1 = int.from_bytes(raw[0:4], "little")
    guid.Data2 = int.from_bytes(raw[4:6], "little")
    guid.Data3 = int.from_bytes(raw[6:8], "little")
    guid.Data4 = (ctypes.c_ubyte * 8).from_buffer_copy(raw[8:16])
    return guid


def _uuid_text_from_winguid(value: "_WinGuid") -> str:
    raw = (
        int(value.Data1).to_bytes(4, "little")
        + int(value.Data2).to_bytes(2, "little")
        + int(value.Data3).to_bytes(2, "little")
        + bytes(bytearray(value.Data4))
    )
    return str(uuid.UUID(bytes_le=raw))


def _normalize(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _token_match(value: Any, tokens: Iterable[str] = IDD_KEYWORDS) -> bool:
    lower = str(value or "").lower()
    return any(token.lower() in lower for token in tokens)


def _rect_tuple(rect: Any) -> Tuple[int, int, int, int]:
    if isinstance(rect, dict):
        left = int(rect.get("left", rect.get("x", 0)) or 0)
        top = int(rect.get("top", rect.get("y", 0)) or 0)
        if "right" in rect and "bottom" in rect:
            right = int(rect.get("right") or left)
            bottom = int(rect.get("bottom") or top)
        else:
            right = left + int(rect.get("width", 0) or 0)
            bottom = top + int(rect.get("height", 0) or 0)
        return left, top, right, bottom
    values = list(rect or [])
    if len(values) < 4:
        return 0, 0, 0, 0
    left, top, right, bottom = [int(float(v or 0)) for v in values[:4]]
    return left, top, right, bottom


def _rect_size(rect: Any) -> Tuple[int, int, int, int, int, int]:
    left, top, right, bottom = _rect_tuple(rect)
    width = max(1, right - left)
    height = max(1, bottom - top)
    return left, top, right, bottom, width, height


def _hmonitor_int(handle: Any) -> int:
    try:
        return int(handle)
    except Exception:
        return int(getattr(handle, "handle", 0) or 0)


def _refine_idd_rect_live(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Override a monitor candidate's rect/size with the LIVE values from
    EnumDisplaySettings(device, ENUM_CURRENT_SETTINGS).

    A headless server process caches its monitor geometry (EnumDisplayMonitors /
    GetMonitorInfo) and never refreshes it without a WM_DISPLAYCHANGE message pump,
    so the rect built from GetMonitorInfo can be stale (e.g. 2400x1350 @ old pos)
    while the IDD is really 1920x1080 at a new position. EnumDisplaySettings reads
    the display driver directly and is NOT subject to that per-process cache, so it
    yields the true current resolution AND position. Capture, the cursor guard, and
    the UI all then agree with reality.
    """
    if win32api is None:
        return candidate
    device = str(candidate.get("device") or "").split(" | ")[0].strip()
    if not device.startswith("\\\\.\\"):
        return candidate
    try:
        live = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
        lw, lh = int(live.PelsWidth), int(live.PelsHeight)
        lx, ly = int(getattr(live, "Position_x", 0)), int(getattr(live, "Position_y", 0))
        if lw > 0 and lh > 0:
            out = dict(candidate)
            out["rect"] = [lx, ly, lx + lw, ly + lh]
            out["width"] = lw
            out["height"] = lh
            return out
    except Exception:
        pass
    return candidate


def find_idd_monitor() -> Dict[str, Any]:
    if win32api is None:
        return {"found": False, "message": "pywin32 is not available"}
    # Keep this process's monitor cache live (see _ensure_display_change_listener).
    _ensure_display_change_listener()

    try:
        monitors = win32api.EnumDisplayMonitors(None, None)
    except Exception as exc:
        return {"found": False, "message": f"EnumDisplayMonitors failed: {exc}"}

    # Adapter map: "\\.\DISPLAYn" -> adapter DeviceString. The ADAPTER name
    # (e.g. "USB Mobile Monitor Virtual Display Driver" for Amyuni vs
    # "NVIDIA GeForce ..." for a real GPU) is what reliably separates a virtual
    # display from a physical one — the monitor child can read "Generic Non-PnP
    # Monitor" for BOTH.
    adapter_strings: Dict[str, str] = {}
    with contextlib.suppress(Exception):
        i = 0
        while i < 64:
            dev = win32api.EnumDisplayDevices(None, i)
            if not dev:
                break
            dn = str(getattr(dev, "DeviceName", "") or "")
            if not dn:
                break
            adapter_strings[dn] = str(getattr(dev, "DeviceString", "") or "")
            i += 1

    inspected: List[Dict[str, Any]] = []
    strong_hit = None
    weak_hits: List[Dict[str, Any]] = []
    for hmonitor, _, raw_rect in monitors:
        try:
            info = win32api.GetMonitorInfo(hmonitor)
            rect = tuple(int(v) for v in info.get("Monitor", raw_rect))
            left, top, right, bottom = rect
            width = max(0, right - left)
            height = max(0, bottom - top)
            flags = int(info.get("Flags") or 0)
            primary = bool(flags & 1)
            device = str(info.get("Device") or "")
            names = [device, adapter_strings.get(device, "")]

            for index in (0, 1):
                with contextlib.suppress(Exception):
                    display = win32api.EnumDisplayDevices(device, index)
                    names.extend(
                        [
                            str(getattr(display, "DeviceName", "") or ""),
                            str(getattr(display, "DeviceString", "") or ""),
                            str(getattr(display, "DeviceID", "") or ""),
                        ]
                    )

            names = [n for n in names if n]
            inspected.append({"device": device, "rect": list(rect), "primary": primary, "names": names})
            if primary:
                continue

            candidate = {
                "found": True,
                "hmonitor": _hmonitor_int(hmonitor),
                "rect": [left, top, right, bottom],
                "width": width,
                "height": height,
                "device": " | ".join(names) or device,
            }
            if any(_token_match(name, STRONG_IDD_KEYWORDS) for name in names):
                if strong_hit is None:
                    strong_hit = candidate
            elif any(_token_match(name, WEAK_IDD_KEYWORDS) for name in names):
                weak_hits.append(candidate)
        except Exception:
            continue

    # 1) An unambiguous virtual-display adapter always wins.
    if strong_hit is not None:
        return _refine_idd_rect_live(strong_hit)
    # 2) Otherwise accept a weak ("Generic Non-PnP") match ONLY if it is the sole
    #    candidate. Two or more weak monitors means we cannot tell the real IDD
    #    from the user's physical second monitor — refuse rather than stream the
    #    wrong screen.
    if len(weak_hits) == 1:
        return _refine_idd_rect_live(weak_hits[0])

    # 3) Cache-independent fallback. EnumDisplayMonitors/GetMonitorInfo are cached
    #    per-process and can MISS the IDD entirely in a long-lived server that
    #    started before the IDD settled. EnumDisplayDevices + EnumDisplaySettings
    #    read the display driver/registry directly (not the GDI monitor cache), so
    #    they see the IDD even when the monitor enumeration above came up empty.
    adapter_hit = _find_idd_via_display_settings()
    if adapter_hit is not None:
        return adapter_hit

    return {
        "found": False,
        "message": (
            "No IDD virtual display could be uniquely identified. "
            "Physical monitors are not used as Phantom fallback. "
            f"Inspected {len(inspected)} monitor(s)."
        ),
        "monitors": inspected,
    }


def _find_idd_via_display_settings() -> Optional[Dict[str, Any]]:
    """Find the IDD by walking display ADAPTERS via EnumDisplayDevices and reading
    each one's live mode via EnumDisplaySettings. Independent of the GDI monitor
    cache, so it works in a long-lived server whose EnumDisplayMonitors view is
    stale. Matches the virtual-display ADAPTER string (strong tokens only)."""
    if win32api is None or win32con is None:
        return None
    try:
        i = 0
        while i < 64:
            dev = win32api.EnumDisplayDevices(None, i)
            if not dev:
                break
            name = str(getattr(dev, "DeviceName", "") or "")  # \\.\DISPLAYn
            string = str(getattr(dev, "DeviceString", "") or "")
            dev_id = str(getattr(dev, "DeviceID", "") or "")
            flags = int(getattr(dev, "StateFlags", 0) or 0)
            i += 1
            if not name:
                break
            haystack = f"{string} {dev_id}".lower()
            if not any(tok in haystack for tok in STRONG_IDD_KEYWORDS):
                continue
            # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
            if not (flags & 0x1):
                continue
            try:
                mode = win32api.EnumDisplaySettings(name, win32con.ENUM_CURRENT_SETTINGS)
                w, h = int(mode.PelsWidth), int(mode.PelsHeight)
                x, y = int(getattr(mode, "Position_x", 0)), int(getattr(mode, "Position_y", 0))
                if w <= 0 or h <= 0:
                    continue
                return {
                    "found": True,
                    "hmonitor": 0,  # unknown here; capture uses the device name
                    "rect": [x, y, x + w, y + h],
                    "width": w,
                    "height": h,
                    "device": f"{name} | {string}",
                }
            except Exception:
                continue
    except Exception:
        return None
    return None


def find_idd_adapter() -> Dict[str, Any]:
    """Detect whether the USBMMIDD / IDD adapter is registered with Windows,
    even when its virtual monitor has been disabled (enableidd 0).

    Used by the Phantom UI to tell "driver installed but currently disconnected"
    apart from "driver missing". After install we deliberately disable the
    monitor so the user can't accidentally drag windows onto an invisible
    display — so the regular EnumDisplayMonitors check fails, but the adapter
    is still listed by EnumDisplayDevices and visible to SetupDiEnumDeviceInfo.
    """
    if win32api is None:
        return {"installed": False, "message": "pywin32 not available"}

    adapters: List[Dict[str, Any]] = []
    tokens = ("usbmmidd", "usbmm", "amyuni", "usb mobile monitor", "mobile monitor")
    # Match INSIDE the loop: EnumDisplayDevices can raise at a high index AFTER the
    # IDD, and a collect-then-match design would lose the hit to the except clause.
    i = 0
    while i < 64:
        try:
            dev = win32api.EnumDisplayDevices(None, i)
        except Exception:
            break
        i += 1
        if not dev:
            break
        name = str(getattr(dev, "DeviceName", "") or "")
        if not name:
            break
        string = str(getattr(dev, "DeviceString", "") or "")
        dev_id = str(getattr(dev, "DeviceID", "") or "")
        adapters.append({"name": name, "string": string, "id": dev_id})
        haystack = f"{string} {dev_id}".lower()
        if any(token in haystack for token in tokens):
            return {"installed": True, "adapter": {"name": name, "string": string, "id": dev_id}}

    # SetupAPI fallback (driver registered but adapter dynamically detached)
    try:
        result = subprocess.run(
            ["pnputil", "/enum-drivers"],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = (result.stdout or "") + (result.stderr or "")
        low = text.lower()
        if "usbmmidd" in low or "amyuni" in low or "usb mobile monitor" in low:
            return {"installed": True, "adapter": {"source": "pnputil"}}
    except Exception:
        pass

    return {"installed": False, "adapters": adapters}


def _physical_monitors_extent() -> Tuple[int, int]:
    """Return the bottom-right CORNER of the RIGHTMOST physical (non-IDD) monitor —
    the anchor where the IDD is parked so it touches that monitor at a single corner
    point (mouse can't cross a zero-length edge, so windows can't be dragged onto it).

    Returning the rightmost monitor's OWN (right, bottom) — rather than the max of
    right and bottom taken independently across monitors — guarantees the anchor is
    a REAL monitor corner. With mismatched-size monitors (an L-shaped layout) the
    independent max could land at a point touching NO monitor → Windows sees a gap
    and snaps/rejects the IDD."""
    if win32api is None:
        return (1920, 1080)
    idd = find_idd_monitor()
    idd_device = ""
    if idd.get("found"):
        idd_device = str(idd.get("device") or "").split(" | ")[0].strip()
    best_right, best_bottom, best = -1, 0, None
    try:
        for hmon, _, _ in win32api.EnumDisplayMonitors(None, None):
            with contextlib.suppress(Exception):
                info = win32api.GetMonitorInfo(hmon)
                dev = str(info.get("Device") or "")
                if idd_device and dev == idd_device:
                    continue  # skip the IDD itself
                rect = info.get("Monitor") or (0, 0, 0, 0)
                if int(rect[2]) > best_right:
                    best_right = int(rect[2]); best_bottom = int(rect[3]); best = rect
    except Exception:
        pass
    if best is None or best_right <= 0:
        return (1920, 1080)
    return (best_right, best_bottom)


def _detached_idd_device() -> Optional[str]:
    """Return the \\\\.\\DISPLAYn name of a registered-but-DETACHED USBMMIDD adapter
    (StateFlags has no ATTACHED_TO_DESKTOP bit), or None. Repeated installs can
    leave several (DISPLAY7..10); we just need one to attach."""
    if win32api is None:
        return None
    try:
        i = 0
        while i < 64:
            dev = win32api.EnumDisplayDevices(None, i)
            i += 1
            if not dev:
                break
            name = str(getattr(dev, "DeviceName", "") or "")
            if not name:
                break
            string = str(getattr(dev, "DeviceString", "") or "")
            flags = int(getattr(dev, "StateFlags", 0) or 0)
            haystack = string.lower()
            if any(tok in haystack for tok in STRONG_IDD_KEYWORDS) and not (flags & 0x1):
                return name
    except Exception:
        return None
    return None


def attach_idd_monitor(target_w: int = 1920, target_h: int = 1080) -> Dict[str, Any]:
    """Re-attach a detached USBMMIDD virtual monitor.

    USBMMIDD's detached state has NO valid display mode (EnumDisplaySettings
    reports 0x0), so ChangeDisplaySettingsEx cannot attach it — only the driver's
    own `deviceinstaller enableidd 1` instantiates the monitor, and that needs
    admin (one UAC). In the fixed flow the monitor is enabled once at install and
    NEVER detached, so this recovery path is rare (only if something external
    disabled it). Returns needs_activation when the monitor is detached, so the
    UI can route to the one-click activate step instead of silently failing.
    """
    if win32api is None or win32con is None:
        return {"success": False, "error": "win32api not available"}
    if find_idd_monitor().get("found"):
        return {"success": True, "already_attached": True}
    device = _detached_idd_device()
    if not device:
        return {"success": False, "error": "No detached USBMMIDD adapter found"}
    # enableidd 1 (admin). set_idd_monitor_enabled handles the UAC elevation and
    # waits for the elevated process to finish.
    res = set_idd_monitor_enabled(True)
    if not res.get("success"):
        return {"success": False, "needs_activation": True,
                "error": res.get("error") or "enableidd 1 failed", "device": device}
    for _ in range(20):
        time.sleep(0.25)
        m = find_idd_monitor()
        if m.get("found"):
            return {"success": True, "attached": True, "device": device,
                    "rect": m.get("rect"), "width": m.get("width"),
                    "height": m.get("height")}
    return {"success": False, "needs_activation": True,
            "error": "Monitor did not attach after enableidd 1", "device": device}


def normalize_idd_resolution(target_w: int = 1920, target_h: int = 1080) -> Dict[str, Any]:
    """Force the USBMMIDD virtual monitor to a clean `target_w`x`target_h`
    (default 1920x1080) AND move it to positive coordinates just past the
    physical monitors. Returns only once the change has SETTLED.

    Two independent bugs made the stream show black areas; both are fixed here:

    1. NEGATIVE position. The IDD booted at [-2400,-1350,0,0]; the main device-DC
       capture tolerates that but the ImageGrab black-screen fallback uses ABSOLUTE
       coords and produced "black + a sliver of the real screen". Moving it to
       positive, contiguous coords fixes every capture path.

    2. BROKEN native mode. USBMMIDD reports a "2400x1350" mode whose actual
       framebuffer is smaller — capturing it yields content in the top-left and
       BLACK everywhere else (verified empirically). Its 1920x1080 mode renders a
       full, clean framebuffer. So we force 1920x1080. The driver re-asserts
       2400x1350 after a display re-scan / server restart, which is why the lock
       flow calls this every time it binds the AI.

    We do NOT park it far away (-30000 broke capture and Windows auto-snaps gaps).
    The user's cursor is kept out of this rect by install_mouse_boundary instead.

    Safe no-op if pywin32 isn't available or no IDD monitor is found.
    """
    if win32api is None or win32con is None:
        return {"success": False, "error": "win32api not available"}
    monitor = find_idd_monitor()
    if not monitor.get("found"):
        # Detached. Do NOT auto-enable here (that needs admin/UAC and, if called
        # from the lock/poll path, caused repeated UAC + display flicker). The
        # caller must run the explicit activate step first. Just report it.
        return {"success": False, "needs_activation": True,
                "error": monitor.get("message", "IDD not attached")}
    device = str(monitor.get("device") or "").split(" | ")[0].strip()
    if not device:
        return {"success": False, "error": "IDD device name unknown"}

    cur_w = int(monitor.get("width") or 0)
    cur_h = int(monitor.get("height") or 0)
    cur_rect = monitor.get("rect") or [0, 0, 0, 0]

    # Park the IDD CORNER-ONLY (diagonally below-right of the physical monitors).
    # It then shares a single corner POINT with the real desktop — Windows accepts
    # that as a connected arrangement, but a zero-length shared edge means the
    # MOUSE CAN NEVER CROSS onto it, so the user cannot drag (and lose) a window
    # there. The previous side-by-side placement shared a full edge → windows
    # could be dragged onto the invisible monitor ("lỡ kéo qua rồi sao kéo lại").
    # (Parking it FAR away is not an option: Windows auto-snaps gaps closed.)
    ext_x, ext_bottom = _physical_monitors_extent()
    target_x, target_y = int(ext_x), int(ext_bottom)
    needs_move = (int(cur_rect[0]) != target_x) or (int(cur_rect[1]) != target_y)

    if cur_w == int(target_w) and cur_h == int(target_h) and not needs_move:
        return {"success": True, "changed": False, "rect": cur_rect,
                "width": cur_w, "height": cur_h, "settled": True}

    try:
        devmode = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
        devmode.PelsWidth = int(target_w)
        devmode.PelsHeight = int(target_h)
        devmode.BitsPerPel = 32
        fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_BITSPERPEL
        if needs_move:
            devmode.Position_x = int(target_x)
            devmode.Position_y = int(target_y)
            fields |= win32con.DM_POSITION
        devmode.Fields = fields
        result = win32api.ChangeDisplaySettingsEx(
            device, devmode, win32con.CDS_UPDATEREGISTRY)
        if result != 0:
            return {"success": False, "error": f"ChangeDisplaySettingsEx returned {result}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    # Wait for the mode change to settle. USBMMIDD applies the new mode a few
    # seconds after ChangeDisplaySettingsEx returns, so we poll the resolution
    # (the thing that matters for clean capture) for up to ~12s and accept the
    # first read where width/height match the target.
    new_monitor = find_idd_monitor()
    settled = False
    for _ in range(48):
        time.sleep(0.25)
        probe = find_idd_monitor()
        new_monitor = probe
        if (int(probe.get("width") or 0) == int(target_w)
                and int(probe.get("height") or 0) == int(target_h)):
            settled = True
            break
    return {
        "success": True,
        "changed": True,
        "rect": new_monitor.get("rect"),
        "width": int(new_monitor.get("width") or target_w),
        "height": int(new_monitor.get("height") or target_h),
        "settled": settled,
    }


def set_idd_monitor_enabled(enable: bool) -> Dict[str, Any]:
    """Toggle the USBMMIDD virtual monitor on/off via deviceinstaller64.exe.

    Used by the Phantom flow: enable right before locking AI to a desktop,
    disable when the session ends or right after install (so the user can't
    accidentally drag a window to an invisible display).

    deviceinstaller's enableidd uses SetupDi APIs which require admin, so when
    the Skemi server is running unelevated we fall back to ShellExecuteW(runas)
    + a small one-shot BAT. The user sees one UAC consent per toggle.
    """
    if os.name != "nt":
        return {"success": False, "error": "Only supported on Windows"}

    inf_dir = os.path.join(BASE_DIR, "Skemi_Virtual_Display", "usbmmidd_v2")
    if not os.path.isdir(inf_dir):
        return {"success": False, "error": f"USBMMIDD bundle missing at {inf_dir}"}

    arch_64 = os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64").upper() in ("AMD64", "ARM64")
    installer = "deviceinstaller64.exe" if arch_64 else "deviceinstaller.exe"
    installer_path = os.path.join(inf_dir, installer)
    if not os.path.isfile(installer_path):
        return {"success": False, "error": f"{installer} not found in {inf_dir}"}

    arg = "1" if enable else "0"

    # First try in-process — works if Skemi was launched elevated.
    try:
        result = subprocess.run(
            [installer_path, "enableidd", arg],
            capture_output=True, text=True, cwd=inf_dir, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode == 0:
            return {"success": True, "enabled": bool(enable), "output": out,
                    "elevated": False}
        if "740" not in out and "elevat" not in out.lower():
            return {"success": False, "error": out or f"returncode {result.returncode}"}
        # Fall through to UAC path
    except Exception as exc:
        # Fall through to UAC path
        out = str(exc)
        if "740" not in out and "elevat" not in out.lower():
            return {"success": False, "error": out}

    # Elevated path — ShellExecuteW(runas) with a tiny BAT, then wait for it.
    label = "enable" if enable else "disable"
    log_path = os.path.join(inf_dir, f"skemi_{label}_monitor.log")
    bat_path = os.path.join(inf_dir, f"skemi_{label}_monitor.bat")
    bat_body = (
        "@echo off\r\n"
        f'cd /d "{inf_dir}"\r\n'
        f'echo [%date% %time%] Skemi: {label} virtual monitor > "{log_path}"\r\n'
        f'{installer} enableidd {arg} >> "{log_path}" 2>&1\r\n'
        f'echo [DONE rc=%errorlevel%] >> "{log_path}"\r\n'
        "exit /b %errorlevel%\r\n"
    )
    try:
        with open(bat_path, "w", encoding="ascii", newline="") as fh:
            fh.write(bat_body)
    except Exception as exc:
        return {"success": False, "error": f"Could not write toggle bat: {exc}"}

    try:
        shell32 = ctypes.windll.shell32
        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SEE_MASK_NO_CONSOLE = 0x00008000

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("hIcon", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
        sei.lpVerb = "runas"
        sei.lpFile = bat_path
        sei.lpDirectory = inf_dir
        sei.nShow = 0  # SW_HIDE
        if not shell32.ShellExecuteExW(ctypes.byref(sei)):
            err = ctypes.GetLastError()
            return {"success": False, "error": f"ShellExecuteExW failed (err={err})"}
        if not sei.hProcess:
            return {"success": False, "error": "ShellExecuteExW returned no process handle"}
        # Wait up to 15 seconds for the BAT to finish
        WaitForSingleObject = ctypes.windll.kernel32.WaitForSingleObject
        GetExitCodeProcess = ctypes.windll.kernel32.GetExitCodeProcess
        CloseHandle = ctypes.windll.kernel32.CloseHandle
        WaitForSingleObject(sei.hProcess, 15000)
        exit_code = wintypes.DWORD(0)
        GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))
        CloseHandle(sei.hProcess)
        if int(exit_code.value) != 0:
            return {"success": False, "error": f"toggle bat exited with {exit_code.value}",
                    "log": log_path}
        return {"success": True, "enabled": bool(enable), "elevated": True,
                "log": log_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _load_pyvda():
    from pyvda import VirtualDesktop, get_virtual_desktops

    return VirtualDesktop, get_virtual_desktops


def _desktop_guid(desktop: Any) -> str:
    for attr in ("id", "guid", "desktop_id"):
        value = getattr(desktop, attr, "")
        if callable(value):
            with contextlib.suppress(Exception):
                value = value()
        if value:
            return str(value).strip("{}")
    return ""


def _desktop_name(desktop: Any, index: int) -> str:
    for attr in ("name", "Name"):
        value = getattr(desktop, attr, "")
        if callable(value):
            with contextlib.suppress(Exception):
                value = value()
        if value:
            return str(value)
    return f"Desktop {index + 1}"


def list_desktops() -> List[Dict[str, Any]]:
    try:
        VirtualDesktop, get_virtual_desktops = _load_pyvda()
        desktops = list(get_virtual_desktops())
        current_guid = ""
        with contextlib.suppress(Exception):
            current_guid = _desktop_guid(VirtualDesktop.current()).lower()
        result = []
        for index, desktop in enumerate(desktops):
            guid = _desktop_guid(desktop)
            result.append(
                {
                    "guid": guid,
                    "name": _desktop_name(desktop, index),
                    "index": index,
                    "is_current": bool(guid and guid.lower() == current_guid),
                }
            )
        return result
    except Exception:
        return []


def create_new_desktop() -> Dict[str, Any]:
    try:
        VirtualDesktop, get_virtual_desktops = _load_pyvda()
        before = list(get_virtual_desktops())
        before_guids = {_desktop_guid(desktop).lower() for desktop in before if _desktop_guid(desktop)}
        VirtualDesktop.create()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            time.sleep(0.1)
            after = list(get_virtual_desktops())
            for index, desktop in enumerate(after):
                guid = _desktop_guid(desktop)
                if guid and guid.lower() not in before_guids:
                    return {
                        "success": True,
                        "guid": guid,
                        "name": _desktop_name(desktop, index),
                        "index": index,
                    }
        return {"success": False, "error": "Windows did not expose the new virtual desktop within 5 seconds"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _enum_windows() -> List[int]:
    if win32gui is None:
        return []
    handles: List[int] = []

    def _callback(hwnd: int, _: Any) -> bool:
        handles.append(int(hwnd))
        return True

    with contextlib.suppress(Exception):
        win32gui.EnumWindows(_callback, None)
    return handles


def _window_title(hwnd: int) -> str:
    if win32gui is None:
        return ""
    with contextlib.suppress(Exception):
        return str(win32gui.GetWindowText(hwnd) or "")
    return ""


def _window_class(hwnd: int) -> str:
    if win32gui is None:
        return ""
    with contextlib.suppress(Exception):
        return str(win32gui.GetClassName(hwnd) or "")
    return ""


def _window_pid(hwnd: int) -> int:
    if win32process is None:
        return 0
    with contextlib.suppress(Exception):
        return int(win32process.GetWindowThreadProcessId(hwnd)[1] or 0)
    return 0


def _is_visible_window(hwnd: int) -> bool:
    if win32gui is None:
        return False
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (right - left) > 0 and (bottom - top) > 0
    except Exception:
        return False


def _window_desktop_guid(hwnd: int) -> str:
    if not hwnd:
        return ""
    ole32 = None
    manager = ctypes.c_void_p()
    vtbl = None
    did_init = False
    try:
        ole32 = ctypes.OleDLL("ole32")
        coinit_hr = ole32.CoInitialize(None)
        did_init = coinit_hr >= 0
        clsid = _guid_from_uuid_text("aa509086-5ca9-4c25-8f95-589d3c07b48a")
        iid = _guid_from_uuid_text("a5cd92ff-29be-454c-8d04-d82879fb3f1b")
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(manager))
        if hr < 0 or not manager.value:
            return ""
        vtbl = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(_WinGuid))(vtbl[4])
        actual_guid = _WinGuid()
        hr = get_fn(manager, wintypes.HWND(int(hwnd)), ctypes.byref(actual_guid))
        if hr < 0:
            return ""
        return _uuid_text_from_winguid(actual_guid)
    except Exception:
        return ""
    finally:
        if manager.value and vtbl:
            with contextlib.suppress(Exception):
                release_fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
                release_fn(manager)
        if ole32 is not None and did_init:
            with contextlib.suppress(Exception):
                ole32.CoUninitialize()


def _move_window_to_desktop(hwnd: int, desktop_guid: str) -> bool:
    if not hwnd or not desktop_guid:
        return False
    ole32 = None
    manager = ctypes.c_void_p()
    vtbl = None
    did_init = False
    try:
        ole32 = ctypes.OleDLL("ole32")
        coinit_hr = ole32.CoInitialize(None)
        did_init = coinit_hr >= 0
        clsid = _guid_from_uuid_text("aa509086-5ca9-4c25-8f95-589d3c07b48a")
        iid = _guid_from_uuid_text("a5cd92ff-29be-454c-8d04-d82879fb3f1b")
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(manager))
        if hr < 0 or not manager.value:
            return False
        vtbl = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        move_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(_WinGuid))(vtbl[5])
        target_guid = _guid_from_uuid_text(desktop_guid)
        hr = move_fn(manager, wintypes.HWND(int(hwnd)), ctypes.byref(target_guid))
        return hr >= 0
    except Exception:
        return False
    finally:
        if manager.value and vtbl:
            with contextlib.suppress(Exception):
                release_fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
                release_fn(manager)
        if ole32 is not None and did_init:
            with contextlib.suppress(Exception):
                ole32.CoUninitialize()


def _move_window_to_rect(hwnd: int, rect: Any) -> bool:
    """Move + resize a window into `rect`. Un-minimizes/un-hides first because
    Phantom launches apps minimized via SW_SHOWMINNOACTIVE (so they don't flash
    at the user's monitor), and SetWindowPos alone won't restore a minimized
    window — it just moves the minimized stub coords."""
    if win32gui is None or win32con is None or not hwnd:
        return False
    left, top, _, _, width, height = _rect_size(rect)
    try:
        SW_SHOWNOACTIVATE = 4  # un-minimize to last size WITHOUT activating.
        # CRITICAL: do NOT use SW_RESTORE (9) — it ACTIVATES the window and steals
        # the user's foreground focus (e.g. yanks them off Chrome). SW_SHOWNOACTIVATE
        # restores a minimized window to its previous size/pos and leaves the active
        # window active. Then SetWindowPos with SWP_NOACTIVATE repositions it onto the
        # IDD without focus change. This is the "không cướp focus" requirement.
        ctypes.windll.user32.ShowWindow(int(hwnd), SW_SHOWNOACTIVATE)
        flags = (getattr(win32con, "SWP_SHOWWINDOW", 0x0040)
                 | getattr(win32con, "SWP_NOACTIVATE", 0x0010)
                 | getattr(win32con, "SWP_NOOWNERZORDER", 0x0200))
        # HWND_BOTTOM (1) keeps it off the top of the user's z-order too.
        win32gui.SetWindowPos(int(hwnd), 1, left, top, width, height, flags)
        return True
    except Exception:
        return False


def _get_foreground_window() -> int:
    try:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def _restore_foreground(prev_hwnd: int) -> None:
    """Give the user's foreground window back after we launched an app that grabbed
    it. A freshly-launched process (e.g. notepad) calls SetForegroundWindow on
    itself; on the shared desktop that yanks the user off their window. We can't
    stop it, so we restore the PREVIOUS foreground using the AttachThreadInput
    trick (bypasses the foreground-lock so SetForegroundWindow actually works)."""
    if not prev_hwnd or win32gui is None:
        return
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.IsWindow(int(prev_hwnd)):
            return
        if int(user32.GetForegroundWindow() or 0) == int(prev_hwnd):
            return
        cur_tid = kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        tgt_tid = user32.GetWindowThreadProcessId(int(prev_hwnd), None)
        user32.AttachThreadInput(cur_tid, fg_tid, True)
        user32.AttachThreadInput(cur_tid, tgt_tid, True)
        user32.SetForegroundWindow(int(prev_hwnd))
        user32.AttachThreadInput(cur_tid, tgt_tid, False)
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    except Exception:
        pass


def _find_windows_by_pid(pid: int, deadline: float = 4.0) -> List[int]:
    if not pid:
        return []
    end = time.time() + deadline
    while time.time() < end:
        windows = [hwnd for hwnd in _enum_windows() if _is_visible_window(hwnd) and _window_pid(hwnd) == int(pid)]
        if windows:
            return windows
        time.sleep(0.1)
    return []


def _find_explorer_windows() -> List[int]:
    classes = {"CabinetWClass", "ExploreWClass"}
    return [hwnd for hwnd in _enum_windows() if _is_visible_window(hwnd) and _window_class(hwnd) in classes]


def _desktop_by_guid(desktop_guid: str) -> Optional[Dict[str, Any]]:
    target = str(desktop_guid or "").strip("{}").lower()
    for desktop in list_desktops():
        if str(desktop.get("guid") or "").strip("{}").lower() == target:
            return desktop
    return None


def _ensure_idd_resolution(min_width: int = 1280, min_height: int = 720,
                           target_width: int = 1920, target_height: int = 1080) -> Dict[str, Any]:
    """Make sure the IDD virtual display is at least `min_width` x `min_height`.

    USBMMIDD / MttVDD often boot at a tiny default (640x480 or even a vertical
    sliver) which makes the streamed capture look like a thin strip with no
    taskbar or icons. We bump it to `target_width` x `target_height` so the
    rendered desktop looks like a normal Windows desktop.

    Returns the new IDD monitor rect on success, an error dict otherwise.
    Safe to call even if win32 modules aren't loaded.
    """
    if win32api is None or win32con is None:
        return {"success": False, "error": "win32api not available"}
    monitor = find_idd_monitor()
    if not monitor.get("found"):
        return {"success": False, "error": monitor.get("message", "IDD not found")}
    width = int(monitor.get("width") or 0)
    height = int(monitor.get("height") or 0)
    if width >= min_width and height >= min_height:
        return {"success": True, "changed": False, "rect": monitor["rect"],
                "width": width, "height": height}

    device = str(monitor.get("device") or "").split(" | ")[0].strip()
    if not device:
        return {"success": False, "error": "IDD device name unknown"}

    # EnumDisplaySettingsEx → DEVMODE; mutate width/height/bpp; ChangeDisplaySettingsEx
    try:
        devmode = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
        devmode.PelsWidth = int(target_width)
        devmode.PelsHeight = int(target_height)
        devmode.BitsPerPel = 32
        devmode.Fields = (win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
                          | win32con.DM_BITSPERPEL)
        result = win32api.ChangeDisplaySettingsEx(device, devmode,
                                                  win32con.CDS_UPDATEREGISTRY)
        if result != 0:  # DISP_CHANGE_SUCCESSFUL == 0
            return {"success": False, "error": f"ChangeDisplaySettingsEx returned {result}"}
    except Exception as exc:
        return {"success": False, "error": f"ChangeDisplaySettingsEx failed: {exc}"}

    # Re-read the IDD monitor rect now that Windows has applied the new mode.
    new_monitor = find_idd_monitor()
    if not new_monitor.get("found"):
        return {"success": False, "error": "IDD disappeared after resize"}
    return {"success": True, "changed": True, "rect": new_monitor["rect"],
            "width": int(new_monitor.get("width") or target_width),
            "height": int(new_monitor.get("height") or target_height)}


def lock_ai_to_desktop(desktop_guid: str, idd_rect: list) -> Dict[str, Any]:
    """
    Lock the Phantom agent onto a specific virtual desktop without switching the
    user away. We do NOT spawn explorer or any subprocess on the visible desktop;
    instead we simply record the target GUID and IDD rect, then install the
    mouse boundary hook. Apps will be opened later by open_app_on_desktop()
    using SW_HIDE + SetWindowPos so they never appear on the user's screen.
    """
    global locked_desktop_guid, locked_desktop_name, locked_idd_rect

    desktop = _desktop_by_guid(desktop_guid)
    if not desktop:
        return {"success": False, "error": "Desktop GUID was not found"}

    # Bump IDD to a usable resolution BEFORE we capture the rect, so the rect we
    # remember matches the new (full-size) virtual display.
    _ensure_idd_resolution()

    rect = list(_rect_tuple(idd_rect))
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        monitor = find_idd_monitor()
        if not monitor.get("found"):
            return {"success": False, "error": monitor.get("message", "IDD display was not found")}
        rect = list(monitor["rect"])
    else:
        # Even if the caller supplied a rect, re-resolve against the live IDD
        # monitor — the resolution bump above may have moved the rect.
        monitor = find_idd_monitor()
        if monitor.get("found"):
            rect = list(monitor["rect"])

    locked_desktop_guid = str(desktop["guid"])
    locked_desktop_name = str(desktop["name"])
    locked_idd_rect = rect

    install_mouse_boundary(tuple(rect))
    left, top, right, bottom, width, height = _rect_size(rect)
    return {
        "success": True,
        "name": locked_desktop_name,
        "guid": locked_desktop_guid,
        "display": {"rect": [left, top, right, bottom], "width": width, "height": height},
        "windows": [],
    }


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


def install_mouse_boundary(rect: tuple):
    """DISABLED to eliminate system-wide mouse stutter.

    A WH_MOUSE_LL hook hosted in this (busy) Python process must acquire the GIL
    in its callback for EVERY mouse event; while the server is doing frame
    capture / LLM / JPEG work, Windows stalls all mouse input waiting on the hook
    (up to LowLevelHooksTimeout ≈ 300ms each), which the user sees as continuous
    cursor stutter. The AI's windows now live on the invisible virtual monitor, so
    the boundary is unnecessary. We keep the rect (for callers that read it) but
    never install the hook."""
    global _mouse_boundary_rect
    _mouse_boundary_rect = _rect_tuple(rect)
    remove_mouse_boundary()


def remove_mouse_boundary():
    global _mouse_hook_stop, _mouse_hook_thread, _mouse_hook_handle, _mouse_hook_callback_ref
    if _mouse_hook_stop:
        _mouse_hook_stop.set()
    if _mouse_hook_thread and _mouse_hook_thread.is_alive():
        _mouse_hook_thread.join(timeout=0.5)
    _mouse_hook_thread = None
    _mouse_hook_stop = None
    _mouse_hook_callback_ref = None
    _mouse_hook_handle = None


def get_desktop_state(desktop_guid: str) -> Dict[str, Any]:
    """Return the windows the AI agent owns, plus any window whose rect intersects
    the IDD rect. Filtering by Windows virtual desktop GUID is deliberately
    skipped — AI windows live on the user's current desktop at off-screen IDD
    coords (see open_app_on_desktop). The GUID is kept on the response only as
    metadata so the LLM knows which workspace it was assigned to.
    """
    target_guid = str(desktop_guid or locked_desktop_guid or "").strip("{}").lower()
    windows: List[Dict[str, Any]] = []
    idd_rect = tuple(locked_idd_rect) if locked_idd_rect else None

    def _intersects_idd(hwnd: int) -> bool:
        if not idd_rect or win32gui is None:
            return False
        try:
            wl, wt, wr, wb = win32gui.GetWindowRect(int(hwnd))
        except Exception:
            return False
        il, it, ir, ib = idd_rect
        return not (wr <= il or wl >= ir or wb <= it or wt >= ib)

    seen: set = set()
    for hwnd in list(_ai_windows) + list(_enum_windows()):
        hwnd = int(hwnd)
        if hwnd in seen:
            continue
        seen.add(hwnd)
        if not _is_visible_window(hwnd):
            continue
        title = _window_title(hwnd)
        class_name = _window_class(hwnd)
        if not title and class_name not in {"CabinetWClass", "ApplicationFrameWindow"}:
            continue
        # Keep AI-spawned windows; for everything else, only include if it intersects IDD rect
        # so the agent doesn't reason about windows on the user's physical monitor.
        if hwnd not in _ai_windows and not _intersects_idd(hwnd):
            continue
        windows.append({"hwnd": hwnd, "title": title, "class": class_name, "pid": _window_pid(hwnd)})

    focused: Optional[Dict[str, Any]] = None
    if win32gui is not None:
        with contextlib.suppress(Exception):
            hwnd = int(win32gui.GetForegroundWindow() or 0)
            if hwnd and (hwnd in _ai_windows or _intersects_idd(hwnd)):
                focused = {"hwnd": hwnd, "title": _window_title(hwnd), "class": _window_class(hwnd), "pid": _window_pid(hwnd)}

    names = [item["title"] or item["class"] for item in windows[:8]]
    summary = f"{len(windows)} windows on phantom workspace"
    if names:
        summary += ": " + "; ".join(names)
    return {"windows": windows, "focused": focused, "summary": summary, "desktop_guid": target_guid}


def _shortcut_roots() -> List[str]:
    roots = [
        os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
    ]
    return [root for root in roots if root and os.path.isdir(root)]


def _find_shortcut(app_name: str) -> str:
    query = _normalize(app_name)
    if not query:
        return ""
    candidates: List[Tuple[float, str]] = []
    for root in _shortcut_roots():
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in {".lnk", ".url", ".exe"}:
                    continue
                label = _normalize(os.path.splitext(filename)[0])
                if not label:
                    continue
                score = 0.0
                if query == label:
                    score = 1.0
                elif (len(query) >= 4 and query in label) or (len(label) >= 4 and label in query and len(label) >= 0.8 * len(query)):
                    # Require the contained string to be ≥4 chars: a 2-3 char label
                    # like "ea"/"x" is almost always a COINCIDENTAL substring of a
                    # longer query (e.g. "ea" inside "fak-ea-pp") and would launch a
                    # totally unrelated app. Short exact names still hit the == branch.
                    # Also, when the LABEL is contained in the QUERY, require it to be
                    # ≥80% of the query — else a short app name that's a PREFIX of a
                    # different word false-matches ("photos" ⊂ "photoshop").
                    score = 0.9
                elif label.startswith(query) or (query.startswith(label) and len(label) >= 0.8 * len(query)):
                    # query.startswith(label) is the prefix-extension trap
                    # ("photoshop".startswith("photos")) — guard with the 0.8 ratio.
                    score = 0.85
                else:
                    score = difflib.SequenceMatcher(None, query, label).ratio()
                    # Reject loose ratio matches between very-different-length names
                    # (the prefix trap: "photoshop" vs "photos" ≈ 0.80 from the shared
                    # prefix) → fall back to web instead of launching a different app.
                    if min(len(query), len(label)) < 0.8 * max(len(query), len(label)):
                        score = 0.0
                # Cutoff raised 0.45 → 0.72: 0.45 matched WRONG apps (e.g. "claude" →
                # "TLauncher" at ~0.45), so the AI operated a totally different app. A
                # high bar means a near-miss returns "" → caller falls back (e.g. open
                # the web version) instead of launching garbage.
                if score >= 0.72:
                    candidates.append((score, os.path.join(dirpath, filename)))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
    return candidates[0][1]


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _shell_execute_hidden(path: str) -> int:
    """Launch `path` and return the PID the OS assigned to the new process.

    Uses ShellExecuteEx with SEE_MASK_NOCLOSEPROCESS + SW_SHOWMINNOACTIVE so we
    get the process handle back without stealing focus from the user. PID is
    needed by open_app_on_desktop to locate the spawned window (which appears
    hidden/minimised initially, so EnumDesktopWindows wouldn't find it through
    the normal visibility filter).
    Returns 0 on failure.
    """
    try:
        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SW_SHOWMINNOACTIVE = 7  # minimized + no focus steal; we re-position immediately after.
        info = _SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "open"
        info.lpFile = path
        info.nShow = SW_SHOWMINNOACTIVE
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            return 0
        if not info.hProcess:
            return 0
        kernel32 = ctypes.windll.kernel32
        pid = kernel32.GetProcessId(info.hProcess)
        with contextlib.suppress(Exception):
            kernel32.CloseHandle(info.hProcess)
        return int(pid or 0)
    except Exception:
        return 0


def _resolve_system_exe(app_name: str) -> str:
    """Map common system app names to their direct .exe so Win11 boxes
    without Start-Menu shortcuts (e.g. Notepad after 22H2) still launch.
    Returns empty string if no canonical exe is known for this name."""
    key = _normalize(app_name)
    if not key:
        return ""
    table = {
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "calculator": "calc.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "powershell": "powershell.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "mspaint": "mspaint.exe",
        "paint": "mspaint.exe",
        "wordpad": "wordpad.exe",
        "regedit": "regedit.exe",
        "taskmgr": "taskmgr.exe",
        "task manager": "taskmgr.exe",
        "snippingtool": "snippingtool.exe",
        "snipping tool": "snippingtool.exe",
    }
    return table.get(key, "")


def open_app_on_desktop(app_name: str, idd_rect: list) -> Dict[str, Any]:
    """Launch app and position its window inside the IDD rect.

    Windows API note: we deliberately DO NOT move the window to
    `locked_desktop_guid` via VirtualDesktopManager. Windows virtual desktops
    are global per session — every monitor switches together — so moving the
    window to a different desktop would hide it from BitBlt of the IDD rect
    while the user stays on their own desktop. Instead the window lives at
    IDD coordinates (e.g. [4800, 0, 6080, 960]) on the user's CURRENT
    desktop. Those coords sit outside the user's physical monitor rect, so
    the user never sees the AI's app, but the IDD monitor — which extends the
    desktop into that rect — does, and BitBlt captures it for streaming.
    """
    # Prefer a canonical system .exe (notepad.exe, calc.exe, etc.) when the user
    # asks for a built-in Windows tool — Win11 strips many Start-Menu .lnk files,
    # which makes the fuzzy shortcut search match unrelated apps (e.g. "notepad"
    # → "OneNote.lnk"). For anything else fall back to the .lnk search.
    path = _resolve_system_exe(app_name) or _find_shortcut(app_name)
    if not path:
        return {"success": False, "error": f"Application shortcut was not found: {app_name}"}
    # Remember the user's foreground window so we can hand focus back after the
    # launched app inevitably grabs it (notepad et al. SetForegroundWindow on self).
    prev_fg = _get_foreground_window()
    before = set(_enum_windows())
    pid = _shell_execute_hidden(path)
    if not pid:
        return {"success": False, "error": f"Could not launch {path}"}
    # Discover the new window via PID rather than visibility. The launched
    # process is minimized (SW_SHOWMINNOACTIVE) so EnumWindows+visibility
    # would skip it. _find_windows_by_pid walks top-level windows of that PID
    # until the app has rendered one (up to its own deadline).
    launched = _find_windows_by_pid(pid, deadline=10.0)
    if not launched:
        # Fallback: any new top-level window that appeared since `before`.
        deadline = time.time() + 4.0
        while time.time() < deadline and not launched:
            launched = [hwnd for hwnd in _enum_windows() if hwnd not in before]
            if launched:
                break
            time.sleep(0.2)
    target_rect = idd_rect or locked_idd_rect
    for hwnd in launched:
        _move_window_to_rect(hwnd, target_rect)
        _ai_windows.add(int(hwnd))
    # Hand focus back to the user's window — they keep working uninterrupted while
    # the AI's app lives on the virtual display ("không cướp focus").
    time.sleep(0.2)
    _restore_foreground(prev_fg)
    return {
        "success": True,
        "app": app_name,
        "path": path,
        "rect": list(target_rect or []),
        "windows": [int(hwnd) for hwnd in launched],
        "focus_restored_to": int(prev_fg or 0),
    }


def _find_uia_control(hwnd: int, name: str = "", ctrl_type: str = "") -> Any:
    import uiautomation as uia  # type: ignore

    root = uia.ControlFromHandle(int(hwnd))
    target_name = _normalize(name)
    target_type = _normalize(ctrl_type).replace("control", "").strip()
    queue = [root]
    best = None
    while queue:
        control = queue.pop(0)
        try:
            control_name = str(getattr(control, "Name", "") or "")
            control_type = str(getattr(control, "ControlTypeName", "") or "")
            name_ok = not target_name or target_name in _normalize(control_name)
            type_ok = not target_type or target_type in _normalize(control_type).replace("control", "")
            if name_ok and type_ok:
                return control
            if best is None and type_ok:
                best = control
            queue.extend(list(control.GetChildren()))
        except Exception:
            continue
    return best or root


# ---------------------------------------------------------------------------
# GHOST INPUT — operate windows WITHOUT touching the user's cursor or focus.
#
# The user stays on their own desktop; the AI drives apps on the IDD virtual
# display in parallel. So every action must avoid:
#   * moving the physical mouse cursor (UIA Click / SetCursorPos do this — banned)
#   * stealing keyboard focus (SetFocus / SetForegroundWindow — banned)
#   * global SendKeys / SendInput (go to whatever the USER is focused on — banned)
#
# Strategy, in order of preference:
#   1. UIA control patterns (Invoke / Toggle / SelectionItem / Value) — these act
#      on the control directly, no cursor, no focus change.
#   2. PostMessage of WM_* input messages straight to the target window — delivered
#      to that window's queue without focus, no cursor.
# ---------------------------------------------------------------------------

# Virtual-key codes for the keys the LLM commonly emits.
_VK_MAP = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "spacebar": 0x20, "backspace": 0x08, "back": 0x08,
    "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "insert": 0x2D,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def _deepest_edit_child(hwnd: int) -> int:
    """Find an editable child window (Edit / RichEdit / RichEditD2DPT / Scintilla)
    inside `hwnd` so background WM_SETTEXT/WM_CHAR actually lands. Modern apps
    (Win11 Notepad, etc.) host the text in a child control, not the top window."""
    if win32gui is None:
        return int(hwnd)
    found = [int(hwnd)]
    edit_classes = ("edit", "richedit", "richeditd2dpt", "richedit20w", "richedit50w",
                    "scintilla", "richeditd2d")

    def _cb(h, _):
        try:
            cls = (win32gui.GetClassName(h) or "").lower()
            if any(k in cls for k in edit_classes):
                found[0] = h
                return False
        except Exception:
            pass
        return True

    with contextlib.suppress(Exception):
        win32gui.EnumChildWindows(int(hwnd), _cb, None)
    return found[0]


def _bg_set_edit_text(hwnd: int, text: str) -> bool:
    """Set an edit control's text in the background via WM_SETTEXT (marshalled
    cross-process by Windows). No focus, no cursor. Returns True on apparent OK."""
    if win32gui is None:
        return False
    edit = _deepest_edit_child(hwnd)
    try:
        WM_SETTEXT = 0x000C
        # win32gui.SendMessage marshals the Python string for WM_SETTEXT.
        win32gui.SendMessage(int(edit), WM_SETTEXT, 0, str(text))
        return True
    except Exception:
        return False


def _uia_invoke_no_focus(control) -> bool:
    """Activate a control via UIA patterns — no cursor, no focus steal."""
    for getter, method in (
        ("GetInvokePattern", "Invoke"),       # buttons, menu items, links
        ("GetTogglePattern", "Toggle"),       # checkboxes, toggle buttons
        ("GetSelectionItemPattern", "Select"),  # list/tab items
        ("GetExpandCollapsePattern", "Expand"),  # combo boxes, tree items
    ):
        try:
            get = getattr(control, getter, None)
            if not get:
                continue
            pattern = get()
            if pattern is None:
                continue
            getattr(pattern, method)()
            return True
        except Exception:
            continue
    return False


def _post_background_click(hwnd: int, control) -> bool:
    """Click a control by PostMessage'ing WM_LBUTTONDOWN/UP to the window at the
    control's client-relative center — background, no cursor movement."""
    if win32gui is None:
        return False
    try:
        rect = getattr(control, "BoundingRectangle", None)
        if rect is None:
            return False
        # Screen center of the control.
        sx = int((int(rect.left) + int(rect.right)) / 2)
        sy = int((int(rect.top) + int(rect.bottom)) / 2)
        # Map to the window's client coordinates.
        cx, cy = win32gui.ScreenToClient(int(hwnd), (sx, sy))
        lparam = (int(cy) & 0xFFFF) << 16 | (int(cx) & 0xFFFF)
        WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
        MK_LBUTTON = 0x0001
        win32gui.PostMessage(int(hwnd), WM_MOUSEMOVE, 0, lparam)
        win32gui.PostMessage(int(hwnd), WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        win32gui.PostMessage(int(hwnd), WM_LBUTTONUP, 0, lparam)
        return True
    except Exception:
        return False


def ai_click_element(hwnd, name, ctrl_type) -> Dict[str, Any]:
    """Click WITHOUT moving the user's cursor: UIA pattern first, then a
    background PostMessage click on the control. Never uses the physical mouse."""
    try:
        control = _find_uia_control(int(hwnd), str(name or ""), str(ctrl_type or ""))
        method = ""
        if _uia_invoke_no_focus(control):
            method = "uia_pattern"
        elif _post_background_click(int(hwnd), control):
            method = "postmessage"
        else:
            return {"success": False, "error": "No focus-free way to activate this control"}
        return {"success": True, "hwnd": int(hwnd), "name": str(name or ""),
                "ctrl_type": str(ctrl_type or ""), "method": method}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def ai_type_text(hwnd, name, text) -> Dict[str, Any]:
    """Type WITHOUT stealing focus: UIA ValuePattern.SetValue (no focus needed),
    then a background WM_CHAR stream to the control's window as fallback."""
    text = str(text or "")
    try:
        control = _find_uia_control(int(hwnd), str(name or ""), "EditControl")
        # 1) ValuePattern.SetValue — sets the text directly, no focus, no cursor.
        try:
            vp = control.GetValuePattern()
            if vp is not None:
                vp.SetValue(text)
                return {"success": True, "hwnd": int(hwnd), "name": str(name or ""),
                        "text": text, "method": "value_pattern"}
        except Exception:
            pass
        # 2) Background WM_SETTEXT to the edit child — reliable for Edit/RichEdit
        #    (incl. Win11 Notepad), no focus, no cursor.
        if _bg_set_edit_text(int(hwnd), text):
            return {"success": True, "hwnd": int(hwnd), "name": str(name or ""),
                    "text": text, "method": "wm_settext"}
        # 3) Last resort: WM_CHAR stream to the edit child.
        target = _deepest_edit_child(int(hwnd))
        if win32gui is not None and target:
            WM_CHAR = 0x0102
            for ch in text:
                win32gui.PostMessage(target, WM_CHAR, ord(ch), 0)
            return {"success": True, "hwnd": int(hwnd), "name": str(name or ""),
                    "text": text, "method": "wm_char"}
        return {"success": False, "error": "No focus-free way to type into this control"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def ai_press_key(hwnd, key) -> Dict[str, Any]:
    """Press a key WITHOUT stealing focus: PostMessage WM_KEYDOWN/WM_KEYUP straight
    to the target window (or WM_CHAR for a single printable char)."""
    key_text = str(key or "").strip()
    try:
        target = int(hwnd or 0)
        if target and win32gui is not None:
            # Prefer the focused child control inside the target window.
            with contextlib.suppress(Exception):
                control = _find_uia_control(target)
                nh = int(getattr(control, "NativeWindowHandle", 0) or 0)
                if nh:
                    target = nh
        if not target or win32gui is None:
            return {"success": False, "error": "No target window for key press"}
        WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
        vk = _VK_MAP.get(key_text.lower().strip("{}"))
        if vk is not None:
            win32gui.PostMessage(target, WM_KEYDOWN, vk, 0)
            win32gui.PostMessage(target, WM_KEYUP, vk, 0)
        elif len(key_text) == 1:
            win32gui.PostMessage(target, WM_CHAR, ord(key_text), 0)
        else:
            # Default to Enter for unknown key names.
            win32gui.PostMessage(target, WM_KEYDOWN, 0x0D, 0)
            win32gui.PostMessage(target, WM_KEYUP, 0x0D, 0)
        return {"success": True, "hwnd": int(hwnd or 0), "key": key_text, "method": "postmessage"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _extract_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", str(text or ""))
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def ask_llm(command, state, history, step) -> Dict[str, Any]:
    system_prompt = (
        "You are the Skemi Phantom desktop agent. Read the provided window list and decide the next UI action. "
        "Do not use screenshots or image reasoning. Return one JSON object only with keys: "
        + ", ".join(LLM_ACTION_KEYS)
        + ". Valid actions: open_app, click, type, key, wait, done. "
        "Use element_name and element_type for UI Automation targets. Mark done only after the state proves the task is complete."
    )
    payload = {
        "command": str(command or ""),
        "step": int(step or 0),
        "state": state,
        "history": history[-6:] if isinstance(history, list) else [],
    }
    model = os.getenv("SKEMI_PHANTOM_MODEL", os.getenv("SKEMI_MODEL_MAIN", "llama3.1:8b"))
    try:
        import httpx  # type: ignore

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                os.getenv("SKEMI_OLLAMA_CHAT_URL", "http://127.0.0.1:11434/api/chat"),
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
            )
        raw = resp.json().get("message", {}).get("content", "")
        action = _extract_json_object(raw)
        if action:
            return {key: action.get(key, False if key == "done" else "") for key in LLM_ACTION_KEYS}
    except Exception as exc:
        return {
            "action": "wait",
            "app": "",
            "window_title": "",
            "element_name": "",
            "element_type": "",
            "text": "",
            "key": "",
            "description": f"LLM unavailable: {exc}",
            "done": False,
            "summary": "",
        }
    return {
        "action": "wait",
        "app": "",
        "window_title": "",
        "element_name": "",
        "element_type": "",
        "text": "",
        "key": "",
        "description": "No valid LLM action was returned",
        "done": False,
        "summary": "",
    }


async def _ws_send(ws: Any, data: Dict[str, Any]) -> None:
    if ws is None:
        return
    with contextlib.suppress(Exception):
        await ws.send_json(data)


def _match_window(state: Dict[str, Any], title: str = "") -> int:
    windows = list(state.get("windows") or [])
    query = _normalize(title)
    if query:
        for window in windows:
            if query in _normalize(window.get("title", "")):
                return int(window.get("hwnd") or 0)
    focused = state.get("focused") or {}
    if focused.get("hwnd"):
        return int(focused.get("hwnd") or 0)
    return int(windows[0].get("hwnd") or 0) if windows else 0


async def run_phantom_agent(command, ws, desktop_guid, idd_rect):
    global ai_phantom_active
    ai_phantom_active = True
    history: List[Dict[str, Any]] = []
    await _ws_send(ws, {"type": "agent_start", "command": str(command or ""), "desktop_guid": str(desktop_guid or "")})
    for step in range(1, 31):
        if not ai_phantom_active:
            break
        state = await asyncio.to_thread(get_desktop_state, str(desktop_guid or locked_desktop_guid or ""))
        await _ws_send(ws, {"type": "state", "step": step, **state})
        action = await asyncio.to_thread(ask_llm, command, state, history, step)
        action_name = str(action.get("action") or "wait").lower()
        await _ws_send(ws, {"type": "thinking", "step": step, "action": action})

        if action.get("done") and step > 1:
            await _ws_send(ws, {"type": "agent_done", "summary": action.get("summary") or action.get("description") or "Done"})
            break

        result: Dict[str, Any] = {"success": True, "action": action_name}
        if action_name == "open_app":
            result = await asyncio.to_thread(open_app_on_desktop, str(action.get("app") or ""), idd_rect or locked_idd_rect)
        elif action_name == "click":
            hwnd = _match_window(state, str(action.get("window_title") or ""))
            result = await asyncio.to_thread(ai_click_element, hwnd, action.get("element_name", ""), action.get("element_type", ""))
        elif action_name == "type":
            hwnd = _match_window(state, str(action.get("window_title") or ""))
            result = await asyncio.to_thread(ai_type_text, hwnd, action.get("element_name", ""), action.get("text", ""))
        elif action_name == "key":
            hwnd = _match_window(state, str(action.get("window_title") or ""))
            result = await asyncio.to_thread(ai_press_key, hwnd, action.get("key", "ENTER"))
        elif action_name == "done":
            result = {"success": False, "message": "Done was deferred until state confirms completion"}
        else:
            await asyncio.sleep(0.5)

        history.append({"step": step, "action": action, "result": result})
        await _ws_send(ws, {"type": "executed", "step": step, "result": result})
        await asyncio.sleep(0.8)
    ai_phantom_active = False
    await _ws_send(ws, {"type": "agent_stopped"})


def _capture_idd_rgb(rect: Any):
    if win32gui is None or win32ui is None or win32con is None or Image is None or np is None:
        raise RuntimeError("Capture dependencies are not available")
    left, top, _, _, width, height = _rect_size(rect)
    hdc_screen = 0
    src_dc = None
    mem_dc = None
    bitmap = None
    try:
        hdc_screen = win32gui.GetDC(0)
        src_dc = win32ui.CreateDCFromHandle(hdc_screen)
        mem_dc = src_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(src_dc, width, height)
        mem_dc.SelectObject(bitmap)
        mem_dc.BitBlt((0, 0), (width, height), src_dc, (left, top), win32con.SRCCOPY)
        info = bitmap.GetInfo()
        bits = bitmap.GetBitmapBits(True)
        image = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1).convert("RGB")
        return np.array(image)
    finally:
        with contextlib.suppress(Exception):
            if bitmap:
                win32gui.DeleteObject(bitmap.GetHandle())
        with contextlib.suppress(Exception):
            if mem_dc:
                mem_dc.DeleteDC()
        with contextlib.suppress(Exception):
            if src_dc:
                src_dc.DeleteDC()
        with contextlib.suppress(Exception):
            if hdc_screen:
                win32gui.ReleaseDC(0, hdc_screen)


class IDDVideoTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, rect, fps: float = 30.0) -> None:
        super().__init__()
        self.rect = list(_rect_tuple(rect))
        self.frame_interval = 1.0 / max(1.0, min(60.0, float(fps or 30.0)))
        self._last_frame = 0.0

    async def recv(self):
        if not AIORTC_AVAILABLE or VideoFrame is None or np is None:
            raise RuntimeError("aiortc, av, numpy, and Pillow are required for WebRTC")
        delay = self.frame_interval - (time.perf_counter() - self._last_frame)
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_frame = time.perf_counter()
        pts, time_base = await self.next_timestamp()
        left, top, right, bottom, width, height = _rect_size(self.rect)
        try:
            arr = await asyncio.to_thread(_capture_idd_rgb, [left, top, right, bottom])
        except Exception:
            arr = np.zeros((height, width, 3), dtype=np.uint8)
        frame = VideoFrame.from_ndarray(arr, format="rgb24")
        frame = frame.reformat(format="yuv420p")
        frame.pts = pts
        frame.time_base = time_base
        return frame


async def create_webrtc_answer(sdp: str, offer_type: str = "offer", rect: Optional[list] = None) -> Dict[str, Any]:
    if not AIORTC_AVAILABLE or RTCPeerConnection is None or RTCSessionDescription is None:
        raise RuntimeError("WebRTC is unavailable on this runtime")
    target_rect = rect or locked_idd_rect
    if not target_rect:
        monitor = find_idd_monitor()
        if not monitor.get("found"):
            raise RuntimeError(str(monitor.get("message") or "IDD display was not found"))
        target_rect = list(monitor["rect"])
    pc = RTCPeerConnection()
    _pcs.add(pc)

    @pc.on("connectionstatechange")
    async def _on_connection_state_change() -> None:
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            with contextlib.suppress(Exception):
                await pc.close()
            _pcs.discard(pc)

    pc.addTrack(IDDVideoTrack(target_rect))
    offer = RTCSessionDescription(sdp=str(sdp or ""), type=str(offer_type or "offer"))
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


async def stop_phantom() -> Dict[str, Any]:
    global ai_phantom_active
    ai_phantom_active = False
    remove_mouse_boundary()
    # Close every window the agent opened this session so the user's machine returns
    # to a clean state. Skip silently if a window is already gone.
    if win32gui is not None and win32con is not None:
        for hwnd in list(_ai_windows):
            with contextlib.suppress(Exception):
                win32gui.PostMessage(int(hwnd), win32con.WM_CLOSE, 0, 0)
    _ai_windows.clear()
    for pc in list(_pcs):
        with contextlib.suppress(Exception):
            await pc.close()
        _pcs.discard(pc)
    return {"success": True}
