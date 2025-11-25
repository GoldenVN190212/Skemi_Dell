import ollama
from typing import List, Dict
import re
import logging

logging.basicConfig(level=logging.INFO)

MODEL_NAME = "gemma3:4b-it-q8_0"

SYSTEM_PROMPT_FORMAT = (
    "Bạn là trợ lý AI chuyên nghiệp và hữu ích. Hãy trả lời một cách tự nhiên và thân thiện, "
    "cung cấp câu trả lời chính xác và chi tiết cho các câu hỏi phức tạp. "
    "TUYỆT ĐỐI không sử dụng bất kỳ định dạng Markdown hoặc ký tự đặc biệt nào (như *, **, #, [], v.v.). "
    "Chỉ trả về văn bản thuần. Yêu cầu về ngôn ngữ ĐẦU RA (Việt/Anh) phải được TUÂN THỦ NGHIÊM NGẶT từ các hướng dẫn trước đó."
)

def call_gemma_pro_chat(messages: List[Dict[str, str]]):
    
    lang_system_prompt = next((m for m in messages if m['role'] == 'system'), None)
    
    full_messages = []
    
    # 1. Thêm System Prompt về Format/Tone
    full_messages.append({"role": "system", "content": SYSTEM_PROMPT_FORMAT})
    
    # 2. Thêm System Prompt về Ngôn ngữ (Ưu tiên cao)
    if lang_system_prompt:
        full_messages.append(lang_system_prompt)
        
    # 3. Thêm các tin nhắn lịch sử và tin nhắn User hiện tại
    full_messages.extend([m for m in messages if m['role'] != 'system'])

    try:
        logging.info(f"Calling Ollama Pro: {MODEL_NAME} with {len(full_messages)} messages.")

        response = ollama.chat(
            model=MODEL_NAME, 
            messages=full_messages, 
            options={"temperature": 0.3}
        )
        
        text = response.get("message", {}).get("content", "")
        text = re.sub(r'[*_~`#]', '', text)
        return text.strip()
        
    except Exception as e:
        logging.error(f"Lỗi gọi model Pro ({MODEL_NAME}): {e}")
        return f"Xin lỗi, mô hình Pro hiện đang gặp lỗi: {str(e)}"