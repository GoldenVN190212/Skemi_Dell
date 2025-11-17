from ollama import chat
import json

def call_gemma3_block(file_path):
    """
    Nhận file → trích xuất text → topic → subtopics chi tiết & tóm tắt
    """
    text = extract_text_from_file(file_path)

    messages = [
        {"role": "system", "content": "Bạn là AI phân tích tài liệu học tập."},
        {"role": "user", "content": f"Phân tích nội dung sau. Trả về JSON: topic, subtopics detail, subtopics summary:\n{text}"}
    ]

    resp = chat(model="gemma3:4b", messages=messages)

    # Gemma3 trả JSON
    try:
        data = json.loads(resp.message.content)
        topic = data.get("topic", "Chưa xác định")
        detail = data.get("detail", [])
        summary = data.get("summary", [])
    except:
        topic = "Chưa xác định"
        detail = []
        summary = []

    return topic, detail, summary

def extract_text_from_file(file_path):
    """
    TODO: trích xuất PDF/DOCX/PPTX/IMG
    Hiện tại trả text giả lập
    """
    return "Nội dung giả lập từ file"
