import ollama
from datetime import datetime
import re

MODEL_NAME = "gemma3:1b"

def call_gemma__small_chat(messages):
    """
    Gọi model nhỏ, trả lời thuần văn bản, không có Markdown.
    """
    # System prompt ép model trả lời thuần text
    system_prompt = {
        "role": "system",
        "content": (
            "Bạn là trợ lý AI Skemi. "
            "Luôn trả lời bằng đúng ngôn ngữ người dùng. "
            "Tuyệt đối không sử dụng Markdown hoặc ký tự đặc biệt như *, **, #, [], v.v. "
            "Chỉ trả về văn bản thuần."
        )
    }

    full_messages = [system_prompt] + messages

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=full_messages,
            options={'temperature': 0.5}
        )

        text = getattr(response.message, "content", str(response))
        # Loại bỏ Markdown nếu còn sót
        text = re.sub(r'[*_~`#]', '', text)
        return text.strip()

    except Exception as e:
        print(f"Lỗi gọi model SMALL: {e}")
        return "Xin lỗi, tôi không thể trả lời lúc này."
