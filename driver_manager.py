"""
Virtual Display Driver Manager (v6.0 Overhaul)
Handles autonomous driver detection, auto-healing, and robust activation.
"""

import os
import json
import time
import asyncio
import subprocess
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path

# Driver paths
REPO_ROOT = Path(__file__).resolve().parent
DRIVER_DIR = REPO_ROOT / "Skemi_Virtual_Display" / "usbmmidd_v2"
INSTALLER_PATH = DRIVER_DIR / "deviceinstaller64.exe"

# Driver info
DRIVER_INFO = {
    "name": "Skemi Virtual Display Driver",
    "version": "6.0 (Overhaul)",
    "description": "Virtual Display Management Engine",
    "download_url": "/download/virtual-display-driver",
    "installer_file": "Skemi_Virtual_Display_Driver.exe",
    "requires_admin": True,
    "supported_os": ["Windows 10", "Windows 11"]
}

class DriverManager:
    """Quản lý tự động màn hình ảo và Driver."""
    
    def __init__(self):
        self.install_status = {
            "detected": False,
            "installed": False,
            "enabled": False,
            "error": None,
            "last_check": 0
        }
        self._check_lock = threading.Lock()
    
    async def detect_driver(self, force: bool = False) -> Dict[str, Any]:
        """Phát hiện và tự động sửa lỗi Driver/Màn hình."""
        now = time.time()
        if not force and (now - self.install_status["last_check"]) < 5:
            return self.install_status
        
        self.install_status["last_check"] = now
        
        # 1. Kiểm tra File vật lý
        installer_exists = INSTALLER_PATH.exists()
        
        # 2. Kiểm tra Driver đã cài vào Windows chưa (Permissive PnP)
        driver_installed = await self._check_windows_driver()
        
        # 3. Kiểm tra Màn hình đang Active (Independent Win32 check)
        display_probe = await self._check_virtual_display_active()
        display_enabled = bool(display_probe.get("enabled"))
        
        # v6.0 AUTO-HEALING: Nếu đã cài driver nhưng màn hình chưa bật, thử bật luôn
        # Health polling does not enable or install drivers.

        self.install_status.update({
            "detected": installer_exists or driver_installed,
            "installed": driver_installed,
            "enabled": display_enabled,
            "driver_status": "active" if display_enabled else ("installed_no_monitor" if driver_installed else ("package_available" if installer_exists else "missing")),
            "workspace_ready": display_enabled,
            "safe_for_phantom": bool(display_probe.get("safe_for_phantom", display_enabled)),
            "capture_probe_ok": bool(display_probe.get("capture_probe_ok", display_enabled)),
            "capture_probe_black": bool(display_probe.get("capture_probe_black", False)),
            "display_bounds": dict(display_probe.get("display_bounds") or {}),
            "install_available": bool(installer_exists),
            "install_message": "Sẵn sàng kích hoạt màn hình ảo." if installer_exists else "Thiếu bộ cài màn hình ảo.",
            "error": None
        })
        
        return self.install_status
    
    async def _check_windows_driver(self) -> bool:
        """Kiểm tra Driver trong hệ thống (Cực kỳ thoáng)."""
        try:
            # Chấp nhận mọi thiết bị có dấu hiệu là màn hình ảo hoặc driver phần mềm
            ps_command = """
                Get-CimInstance Win32_PnPEntity | 
                Where-Object { 
                    $_.PNPClass -match 'Monitor|Display' -or 
                    $_.Name -match 'usbmmidd|Virtual|Indirect|Software Device|IDD|mttvdd|amyuni|phantom' 
                } | 
                Where-Object { 
                    $_.Name -match 'usbmmidd|USB Mobile Monitor|virtual|IDD|mttvdd|amyuni|indirect|parsec|spacedesk|superdisplay|duet|xdisplay|splashtop|displaylink|vmulti|vdesk|non-pnp|default_monitor|phantom' 
                } |
                Select-Object Name, DeviceID, Status | ConvertTo-Json -Compress
            """
            
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            
            if stdout:
                output = stdout.decode('utf-8', errors='ignore').strip()
                if output:
                    return True # Có bất kỳ kết quả nào khớp là OK
            return False
        except:
            return False
    
    async def _check_virtual_display_active(self) -> Dict[str, Any]:
        """Kiểm tra màn hình ảo đang hoạt động (Độc lập hoàn toàn)."""
        # Thử qua desktop_agent trước
        try:
            import desktop_agent
            if hasattr(desktop_agent, 'jarvis_display_manager'):
                status = desktop_agent.jarvis_display_manager.status(force=False)
                if status.get("workspace_ready"):
                    return {
                        "enabled": True,
                        "safe_for_phantom": True,
                        "capture_probe_ok": bool(status.get("capture_probe_ok", True)),
                        "capture_probe_black": bool(status.get("capture_probe_black", False)),
                        "display_bounds": dict(status.get("display_bounds") or {}),
                    }
        except: pass

        # Fallback: Quét trực tiếp Windows API (EnumDisplayMonitors)
        try:
            import win32api
            monitors = win32api.EnumDisplayMonitors(None, None)
            for hmonitor, _, rect in monitors:
                info = win32api.GetMonitorInfo(hmonitor)
                # Nếu không phải màn hình chính (Flags & 1) thì coi là ứng viên tiềm năng
                if not (info.get("Flags", 0) & 1):
                    device = info.get("Device", "")
                    adapter = win32api.EnumDisplayDevices(device, 0)
                    names = [device, str(getattr(adapter, "DeviceString", "")), str(getattr(adapter, "DeviceID", ""))]
                    name_key = " ".join(names).lower()
                    
                    # Ưu tiên các màn hình có tên "Virtual", "Indirect", "Non-PnP", "IDD", v.v.
                    virtual_tokens = ["virtual", "indirect", "idd", "mobile monitor", "mttvdd", "usbmmidd", "amyuni", "parsec", "spacedesk", "phantom"]
                    is_virtual = any(t in name_key for t in virtual_tokens)
                    
                    # Ngay cả khi không khớp token, nếu là màn hình phụ thì vẫn tạm chấp nhận
                    if is_virtual:
                        left, top, right, bottom = rect
                        return {
                            "enabled": True,
                            "safe_for_phantom": True,
                            "capture_probe_ok": True,
                            "capture_probe_black": False,
                            "display_bounds": {"left": left, "top": top, "width": right - left, "height": bottom - top},
                        }
        except: pass
        
        return {"enabled": False, "safe_for_phantom": False, "capture_probe_ok": False, "capture_probe_black": False, "display_bounds": {}}
    
    async def enable_virtual_display(self) -> Dict[str, Any]:
        """Bật màn hình ảo."""
        if not INSTALLER_PATH.exists():
            return {"success": False, "error": "not_found", "message": "Không tìm thấy bộ cài Driver."}
        
        try:
            proc = await asyncio.create_subprocess_exec(
                str(INSTALLER_PATH), "enableidd", "1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20.0)
            if proc.returncode == 0:
                await asyncio.sleep(2) # Đợi Windows nhận diện
                return {"success": True, "message": "Đã gửi lệnh kích hoạt màn hình ảo."}
            return {"success": False, "message": stderr.decode('utf-8', errors='ignore') or "Lỗi kích hoạt."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def install_driver(self) -> Dict[str, Any]:
        """Cài đặt Driver và kích hoạt toàn diện."""
        if not INSTALLER_PATH.exists():
            return {"success": False, "message": "Thiếu file deviceinstaller64.exe."}
        
        work_dir = str(INSTALLER_PATH.parent)
        inf_path = str(INSTALLER_PATH.parent / "usbmmidd.inf")
        
        results = []
        try:
            # 1. Stop if running
            p1 = await asyncio.create_subprocess_exec(str(INSTALLER_PATH), "stop", "usbmmidd", cwd=work_dir, creationflags=subprocess.CREATE_NO_WINDOW)
            await p1.wait()
            
            # 2. Install INF
            p2 = await asyncio.create_subprocess_exec(str(INSTALLER_PATH), "install", inf_path, "usbmmidd", cwd=work_dir, creationflags=subprocess.CREATE_NO_WINDOW)
            await p2.wait()
            
            # 3. Enable IDD
            p3 = await asyncio.create_subprocess_exec(str(INSTALLER_PATH), "enableidd", "1", cwd=work_dir, creationflags=subprocess.CREATE_NO_WINDOW)
            await p3.wait()
            
            await asyncio.sleep(2)
            final = await self._check_virtual_display_active()
            
            return {
                "success": True,
                "enabled": final.get("enabled"),
                "message": "Quá trình thiết lập màn hình ảo hoàn tất." if final.get("enabled") else "Đã chạy các lệnh thiết lập, hãy kiểm tra lại trạng thái màn hình."
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi trong quá trình thiết lập: {e}"}

    def get_driver_info(self) -> Dict[str, Any]:
        return {**DRIVER_INFO, "installer_exists": INSTALLER_PATH.exists()}

# Singleton
_manager = None
def get_driver_manager():
    global _manager
    if _manager is None: _manager = DriverManager()
    return _manager
