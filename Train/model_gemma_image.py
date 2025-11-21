# Train/model_gemma_image.py

import base64
from ollama import chat

def encode_image_to_base64(image_path: str) -> str:
    """
    Đọc ảnh từ file và convert sang base64.
    Trả về chuỗi base64 của ảnh.
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def call_gemma_image(image_path: str, prompt: str = "Phân tích nội dung hình ảnh này."):
    """
    Hàm chính gọi Vision Model để phân tích ảnh.
    """
    img_base64 = encode_image_to_base64(image_path)
    messages = [
        {"role": "system", "content": (
            "Bạn là một trợ lý phân tích tài liệu học tập chuyên nghiệp. "
            "Nhiệm vụ của bạn là trích xuất toàn bộ nội dung văn bản và công thức từ hình ảnh được cung cấp, "
            "sau đó định danh rõ ràng chủ đề chính của nội dung (ví dụ: 'Toán học', 'Vật lý', 'Ngữ văn'). "
            "Chỉ trả về văn bản trích xuất và chủ đề, không giải thích hay mở đầu."
        )},
        {
            "role": "user",
            "content": prompt,
            "images": [img_base64],
        }
    ]

    # Gọi Vision Model với temperature thấp
    resp = chat(
        model="gemma3:4b-it-q8_0", 
        messages=messages,
        options={
            "temperature": 0.1, # Tăng tính ổn định cho việc trích xuất
            "seed": 42
        }
    )

    try:
        return resp.message.content
    except Exception:
        if isinstance(resp, dict):
            return resp.get("message", {}).get("content", "")
        return str(resp)
