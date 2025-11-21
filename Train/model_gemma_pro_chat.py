import ollama
from typing import List, Dict, Any, Union

# System Prompt được sửa lại cho đúng yêu cầu
SYSTEM_PROMPT = (
    "Bạn là một trợ lý AI cao cấp và chuyên nghiệp, có khả năng phân tích phức tạp. "
    "Luôn luôn trả lời bằng đúng ngôn ngữ mà người dùng sử dụng trong tin nhắn gần nhất. "
    "Nếu người dùng dùng tiếng Anh, bạn trả lời tiếng Anh. Nếu dùng tiếng Việt, trả lời tiếng Việt. "
    "Tuyệt đối không sử dụng bất kỳ định dạng Markdown nào (như *, **, #, [], v.v.). "
    "Chỉ sử dụng văn bản thuần túy."
)

MODEL_NAME = "gemma3:4b-it-q8_0"

def call_gemma_pro_chat(messages: List[Dict[str, str]]) -> Union[str, Any]:
    """
    Thực hiện cuộc gọi chat với mô hình gemma (phiên bản Pro) thông qua Ollama.
    """

    # 1. Thêm System Prompt vào đầu messages
    contextual_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=contextual_messages,
            options={
                "temperature": 0.3,  # giữ nguyên logic ban đầu
            }
        )

        # Trả về output thuần túy (Server.py sẽ trích content)
        return response.get('message', {}).get('content', "Lỗi: Không nhận được phản hồi từ model Pro.")
        
    except Exception as e:
        return f"Lỗi khi gọi model {MODEL_NAME}: {str(e)}"
