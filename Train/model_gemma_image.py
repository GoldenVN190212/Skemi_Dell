# model_gemma3.py
from ollama import chat
import json

# -----------------------------
# 1) CHATBOT — trả về TEXT
# -----------------------------
def call_gemma_image(message):
    messages = [
        {"role": "system", "content": "Bạn là AI hỗ trợ trả lời câu hỏi."},
        {"role": "user", "content": message}
    ]
    resp = chat(model="gemma3:4b", messages=messages)
    return resp.message.content  # <<== quan trọng: chỉ trả text


# -----------------------------
# 2) FILE ANALYSIS — trả JSON (mindmap)
# -----------------------------
def call_gemma3_block(text):
    """
    Phân tích text từ file → JSON
    """
    messages = [
        {"role": "system", "content": "Bạn là AI phân tích tài liệu học tập."},
        {"role": "user", "content": f"Phân tích nội dung sau. Hãy trả về JSON có dạng:\n"
                                    "{ \"topic\": ..., \"detail\": [...], \"summary\": [...] }\n\n{text}"}
    ]

    resp = chat(model="gemma3:4b", messages=messages)

    # Parse JSON an toàn
    try:
        data = json.loads(resp.message.content)
        return {
            "topic": data.get("topic", "Chưa xác định"),
            "detail": data.get("detail", []),
            "summary": data.get("summary", [])
        }
    except:
        return {
            "topic": "Chưa xác định",
            "detail": [],
            "summary": []
        }
