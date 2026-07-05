import asyncio
import websockets
import json
import base64
from PIL import Image
import io

class SkemiDesktopBridge:
    def __init__(self, websocket_url="ws://localhost:8080/stream/"):
        self.websocket_url = websocket_url
        self.websocket = None
        self.connected = False
    
    async def connect(self):
        """Kết nối đến WebSocket server của ứng dụng C#"""
        try:
            self.websocket = await websockets.connect(self.websocket_url)
            self.connected = True
            print("Connected to Skemi Desktop Capture service")
            return True
        except Exception as e:
            print(f"Failed to connect to desktop capture: {e}")
            return False
    
    async def get_desktop_frame(self):
        """Nhận frame desktop từ ứng dụng C#"""
        if not self.connected:
            if not await self.connect():
                return None
        
        try:
            # Gửi yêu cầu frame
            await self.websocket.send(json.dumps({"action": "get_frame"}))
            
            # Nhận frame data (JPEG bytes)
            frame_data = await self.websocket.recv()
            
            # Convert sang PIL Image
            image = Image.open(io.BytesIO(frame_data))
            return image
            
        except Exception as e:
            print(f"Error getting desktop frame: {e}")
            self.connected = False
            return None
    
    async def send_input_command(self, command_type, params):
        """Gửi lệnh điều khiển đến ứng dụng C#"""
        if not self.connected:
            if not await self.connect():
                return False
        
        try:
            command = {
                "action": "input",
                "type": command_type,
                "params": params
            }
            await self.websocket.send(json.dumps(command))
            return True
            
        except Exception as e:
            print(f"Error sending input command: {e}")
            self.connected = False
            return False
    
    async def mouse_click(self, x, y):
        """Gửi lệnh click chuột"""
        return await self.send_input_command("mouse_click", {"x": x, "y": y})
    
    async def mouse_move(self, x, y):
        """Gửi lệnh di chuyển chuột"""
        return await self.send_input_command("mouse_move", {"x": x, "y": y})
    
    async def type_text(self, text):
        """Gửi lệnh gõ văn bản"""
        return await self.send_input_command("type_text", {"text": text})
    
    async def key_press(self, key):
        """Gửi lệnh nhấn phím"""
        return await self.send_input_command("key_press", {"key": key})
    
    async def close(self):
        """Đóng kết nối"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False

# Global instance
desktop_bridge = SkemiDesktopBridge()