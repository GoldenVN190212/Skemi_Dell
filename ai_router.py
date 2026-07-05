"""
AI Router & Search Integration for Skemi
Import SmartSearchEngine from Skemma-main (1)
"""

import sys
import os

# Add Skemma-main (1) to path for importing
SKEMMA_PATH = r"D:\Skemma-main (1)\Skemma-main\Skemma-main (1) (1)"
if SKEMMA_PATH not in sys.path:
    sys.path.insert(0, SKEMMA_PATH)

# Import search engine
try:
    from search_engine import SmartSearchEngine
    SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"[AI Router] Search engine not available: {e}")
    SmartSearchEngine = None
    SEARCH_AVAILABLE = False

import json
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class IntentResult:
    action: str  # "search", "computer", "chat", "mixed"
    confidence: float  # 0.0 - 1.0
    reason: str
    search_keywords: Optional[str] = None
    computer_action: Optional[str] = None


class AIRouter:
    """Router phân tích ý định người dùng và điều hướng đến đúng module"""
    
    def __init__(self, gemini_client=None):
        self.gemini = gemini_client
        self.search_engine = SmartSearchEngine() if SEARCH_AVAILABLE and SmartSearchEngine else None
        
    async def analyze_intent(self, command: str) -> IntentResult:
        """
        Phân tích ý định người dùng sử dụng AI model
        Returns IntentResult với action và confidence
        """
        if not self.gemini:
            # Fallback: rule-based intent detection
            return self._rule_based_intent(command)
        
        prompt = f"""Phân tích ý định người dùng sau. Chỉ trả về JSON:

Command: "{command}"

Phân loại:
- "search": Nếu người dùng muốn tìm kiếm thông tin, research, tra cứu, hỏi về sự kiện mới, dữ liệu thực tế
- "computer": Nếu người dùng muốn thao tác máy tính, mở app, click, gõ, điều khiển desktop
- "chat": Nếu người dùng chỉ trò chuyện, hỏi ý kiến, không cần dữ liệu thực tế
- "mixed": Nếu cả search và computer đều cần

JSON format:
{{
    "action": "search|computer|chat|mixed",
    "confidence": 0.0-1.0,
    "reason": "giải thích ngắn gọn 1 câu",
    "search_keywords": "từ khóa tìm kiếm nếu cần, ngược lại null",
    "computer_action": "hành động máy tính nếu cần, ngược lại null"
}}"""

        try:
            response = await self.gemini.generate_content_async(prompt)
            result = self._parse_json_response(response.text)
            
            return IntentResult(
                action=result.get("action", "chat"),
                confidence=result.get("confidence", 0.5),
                reason=result.get("reason", ""),
                search_keywords=result.get("search_keywords"),
                computer_action=result.get("computer_action")
            )
        except Exception as e:
            print(f"[AI Router] Intent analysis error: {e}")
            return self._rule_based_intent(command)
    
    def _rule_based_intent(self, command: str) -> IntentResult:
        """Fallback khi AI model không khả dụng"""
        command_lower = command.lower()
        
        # Search keywords
        search_triggers = [
            "tìm", "search", "research", "tra cứu", "thông tin", "dữ liệu",
            "tin tức", "sự kiện", "mới nhất", "latest", "tìm hiểu", "điều tra",
            "cập nhật", "báo cáo", "thống kê", "số liệu", "giá", "thời tiết",
            "lịch sử", "wiki", "wikipedia", "là gì", "là ai", "ở đâu", "khi nào"
        ]
        
        # Computer keywords
        computer_triggers = [
            "mở", "click", "gõ", "nhập", "tải", "download", "cài", "install",
            "chạy", "run", "execute", "bật", "tắt", "đóng", "xóa", "tạo",
            "file", "folder", "desktop", "app", "application", "trang web",
            "chrome", "edge", "firefox", "vscode", "notepad", "word", "excel"
        ]
        
        search_score = sum(1 for t in search_triggers if t in command_lower)
        computer_score = sum(1 for t in computer_triggers if t in command_lower)
        
        # Calculate confidence
        total_keywords = len(search_triggers) + len(computer_triggers)
        if search_score > 0 and computer_score > 0:
            confidence = min(0.95, 0.6 + (search_score + computer_score) * 0.05)
            action = "mixed"
        elif search_score > 0:
            confidence = min(0.95, 0.7 + search_score * 0.05)
            action = "search"
        elif computer_score > 0:
            confidence = min(0.95, 0.7 + computer_score * 0.05)
            action = "computer"
        else:
            confidence = 0.8
            action = "chat"
        
        return IntentResult(
            action=action,
            confidence=confidence,
            reason=f"Rule-based: {search_score} search keywords, {computer_score} computer keywords",
            search_keywords=command if action in ["search", "mixed"] else None,
            computer_action=command if action in ["computer", "mixed"] else None
        )
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON từ AI response"""
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*({[\s\S]*?})\s*```', text)
        if json_match:
            text = json_match.group(1)
        
        # Try to find JSON directly
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object
            json_match = re.search(r'({[\s\S]*?})', text)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except:
                    pass
            return {"action": "chat", "confidence": 0.5, "reason": "Parse error"}
    
    async def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Thực hiện search sử dụng SmartSearchEngine từ Skemma"""
        if not self.search_engine:
            return {
                "success": False,
                "error": "Search engine not available",
                "results": []
            }
        
        try:
            # Use SmartSearchEngine
            results = await self.search_engine.search(query, max_results=max_results)
            
            # Format results
            formatted = []
            for r in results:
                formatted.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                    "source": r.get("source", "web")
                })
            
            return {
                "success": True,
                "query": query,
                "results": formatted,
                "count": len(formatted)
            }
        except Exception as e:
            print(f"[AI Router] Search error: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    async def summarize_search_results(self, query: str, results: list) -> str:
        """Dùng AI tóm tắt kết quả search"""
        if not self.gemini or not results:
            return ""
        
        # Build context from results
        context = "\n\n".join([
            f"[{i+1}] {r.get('title', '')}\n{r.get('snippet', '')}\nURL: {r.get('url', '')}"
            for i, r in enumerate(results[:5])
        ])
        
        prompt = f"""Tóm tắt thông tin chính từ các kết quả tìm kiếm sau để trả lời câu hỏi: "{query}"

KẾT QUẢ TÌM KIẾM:
{context}

Hãy tóm tắt ngắn gọn (3-5 câu) những thông tin quan trọng nhất. Trích dẫn nguồn [1], [2], ... khi cần."""

        try:
            response = await self.gemini.generate_content_async(prompt)
            return response.text
        except Exception as e:
            print(f"[AI Router] Summarize error: {e}")
            return ""


# Singleton instance
_router_instance = None

def get_router(gemini_client=None):
    """Get or create AI Router singleton"""
    global _router_instance
    if _router_instance is None:
        _router_instance = AIRouter(gemini_client)
    return _router_instance
