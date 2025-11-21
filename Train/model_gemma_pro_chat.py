import ollama
from typing import List, Dict
import re

MODEL_NAME = "gemma3:4b-it-q8_0"

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI chuyên nghiệp, luôn trả lời bằng đúng ngôn ngữ của người dùng. "
    "Không sử dụng bất kỳ định dạng Markdown nào (như *, **, #, [], v.v.). "
    "Chỉ trả về văn bản thuần."
)

def call_gemma_pro_chat(messages: List[Dict[str, str]]):
    """
    Gọi model Pro, trả về văn bản thuần, không Markdown.
    """
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    try:
        response = ollama.chat(model=MODEL_NAME, messages=full_messages, options={"temperature":0.3})
        text = response.get("message", {}).get("content", "")
        # Loại bỏ Markdown còn sót
        text = re.sub(r'[*_~`#]', '', text)
        return text.strip()
    except Exception as e:
        return f"Lỗi gọi model Pro: {str(e)}"
