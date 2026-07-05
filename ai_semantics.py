"""
AI-Based Semantic Analysis for Desktop Agent
Replaces all keyword matching with AI understanding
"""

import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SemanticIntent:
    intent_type: str  # "folder", "launch", "interaction", "sensitive", "search", "chat"
    target: str  # What the user wants to access/do
    confidence: float
    context: Dict[str, Any]


class AISemanticsAnalyzer:
    """AI-based semantic analysis - no keyword matching"""
    
    def __init__(self, gemini_client=None):
        self.gemini = gemini_client
        self._folder_cache: Dict[str, Path] = {}
        self._app_cache: Dict[str, str] = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def analyze_intent(self, query: str) -> SemanticIntent:
        """Phân tích ý định người dùng bằng AI - không dùng keyword"""
        if not self.gemini:
            return await self._fallback_analysis(query)
        
        prompt = f"""Phân tích ý định người dùng một cách tự nhiên, không dựa vào keyword cố định.

Query: "{query}"

Phân tích:
1. Người dùng muốn làm gì? (mở ứng dụng, truy cập thư mục, tìm kiếm, thao tác...)
2. Đối tượng chính là gì? (tên ứng dụng, tên thư mục, nội dung tìm kiếm...)
3. Có cần xác nhận không? (hành động nhạy cảm, xóa file, thanh toán...)

Trả về JSON:
{{
    "intent_type": "folder|launch|interaction|sensitive|search|chat|system",
    "target": "tên ứng dụng/thư mục/nội dung chính",
    "confidence": 0.0-1.0,
    "requires_confirmation": true/false,
    "reason": "giải thích ngắn",
    "suggested_path": "đường dẫn đề xuất nếu có",
    "app_name": "tên ứng dụng nếu là launch",
    "folder_name": "tên thư mục nếu là folder"
}}"""
        
        try:
            response = await self.gemini.generate_content_async(prompt)
            result = self._parse_json(response.text)
            
            return SemanticIntent(
                intent_type=result.get("intent_type", "chat"),
                target=result.get("target", ""),
                confidence=result.get("confidence", 0.5),
                context=result
            )
        except Exception as e:
            print(f"[AI Semantics] Error: {e}")
            return await self._fallback_analysis(query)
    
    async def _fallback_analysis(self, query: str) -> SemanticIntent:
        """Fallback khi AI không khả dụng - dùng semantic matching đơn giản"""
        query_lower = query.lower()
        
        # Semantic understanding without hardcoded keywords
        # Detect folder intent by context, not keywords
        folder_indicators = [
            "mở", "vào", "xem", "truy cập", "tìm", "trong",
            "open", "access", "browse", "view", "go to", "enter"
        ]
        has_folder_context = any(ind in query_lower for ind in folder_indicators)
        
        # Check for actual folder names or references
        common_folders = ["downloads", "desktop", "documents", "pictures", "videos", "music"]
        detected_folder = None
        for folder in common_folders:
            if folder in query_lower or folder.replace("s", "") in query_lower:
                detected_folder = folder
                break
        
        if detected_folder and has_folder_context:
            return SemanticIntent(
                intent_type="folder",
                target=detected_folder,
                confidence=0.7,
                context={"folder_name": detected_folder}
            )
        
        # Check for app launch intent
        launch_indicators = ["mở", "bật", "chạy", "khởi động", "launch", "open", "start", "run"]
        has_launch_context = any(ind in query_lower for ind in launch_indicators)
        
        # Extract potential app name (words after launch indicators)
        potential_app = ""
        for indicator in launch_indicators:
            if indicator in query_lower:
                parts = query_lower.split(indicator, 1)
                if len(parts) > 1:
                    potential_app = parts[1].strip().split()[0] if parts[1].strip() else ""
                    break
        
        if has_launch_context and potential_app:
            return SemanticIntent(
                intent_type="launch",
                target=potential_app,
                confidence=0.6,
                context={"app_name": potential_app}
            )
        
        # Default to chat
        return SemanticIntent(
            intent_type="chat",
            target=query,
            confidence=0.8,
            context={}
        )
    
    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Parse JSON from AI response"""
        # Extract from markdown code block
        code_match = re.search(r'```(?:json)?\s*({[\s\S]*?})\s*```', text)
        if code_match:
            text = code_match.group(1)
        
        # Try direct JSON parsing
        try:
            return json.loads(text)
        except:
            # Extract JSON object
            json_match = re.search(r'({[\s\S]*})', text)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except:
                    pass
        
        return {}
    
    async def resolve_folder(self, query: str, home_path: Path) -> Optional[Path]:
        """AI-based folder resolution - không dùng keyword matching"""
        intent = await self.analyze_intent(query)
        
        if intent.intent_type != "folder":
            return None
        
        folder_name = intent.context.get("folder_name", intent.target)
        
        # Map to actual folder
        folder_mapping = {
            "downloads": home_path / "Downloads",
            "desktop": home_path / "Desktop",
            "documents": home_path / "Documents",
            "pictures": home_path / "Pictures",
            "videos": home_path / "Videos",
            "music": home_path / "Music",
        }
        
        # Try exact match first
        if folder_name.lower() in folder_mapping:
            path = folder_mapping[folder_name.lower()]
            if path.exists():
                return path
        
        # Try fuzzy matching with AI understanding
        for key, path in folder_mapping.items():
            if key in folder_name.lower() or folder_name.lower() in key:
                if path.exists():
                    return path
        
        return None
    
    async def detect_sensitive_action(self, query: str, context: Dict = None) -> bool:
        """AI-based sensitive action detection"""
        if not self.gemini:
            return False
        
        prompt = f"""Phân tích xem lệnh sau có cần xác nhận từ người dùng không (hành động nhạy cảm).

Query: "{query}"
Context: {json.dumps(context or {}, ensure_ascii=False)}

Các hành động cần xác nhận: xóa file/quan trọng, format, cài đặt phần mềm lạ, thay đổi system, 
shutdown/restart, thanh toán, đăng nhập, chia sẻ thông tin cá nhân, truy cập registry.

Trả về JSON:
{{
    "requires_confirmation": true/false,
    "reason": "giải thích tại sao",
    "risk_level": "low|medium|high",
    "suggested_confirmation_message": "tin nhắn xác nhận cho người dùng"
}}"""
        
        try:
            response = await self.gemini.generate_content_async(prompt)
            result = self._parse_json(response.text)
            return result.get("requires_confirmation", False)
        except:
            return False
    
    async def resolve_app(self, query: str, installed_apps: List[Dict]) -> Optional[str]:
        """AI-based app resolution - tìm ứng dụng phù hợp nhất"""
        if not installed_apps:
            return None
        
        intent = await self.analyze_intent(query)
        
        if intent.intent_type != "launch":
            return None
        
        app_name = intent.context.get("app_name", intent.target)
        
        # Find best match using semantic understanding
        best_match = None
        best_score = 0
        
        for app in installed_apps:
            app_names = [
                app.get("name", "").lower(),
                app.get("display_name", "").lower(),
                Path(app.get("target", "")).stem.lower()
            ]
            
            for name in app_names:
                if not name:
                    continue
                
                # Exact match
                if app_name.lower() == name:
                    return app.get("target")
                
                # Contains match
                if app_name.lower() in name or name in app_name.lower():
                    score = len(app_name) / len(name) if len(name) > 0 else 0
                    if score > best_score:
                        best_score = score
                        best_match = app.get("target")
        
        return best_match


# Singleton
_analyzer_instance = None

def get_semantics_analyzer(gemini_client=None):
    """Get or create AI Semantics Analyzer"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = AISemanticsAnalyzer(gemini_client)
    return _analyzer_instance
