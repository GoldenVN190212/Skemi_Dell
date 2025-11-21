# Train/model_gemma_small_chat.py
import ollama
from datetime import datetime

MODEL_NAME = "gemma3:1b" 

def call_gemma__small_chat(messages):
    """
    Gọi model nhẹ cho các tác vụ đơn giản.
    Được sửa để:
    - Model trả lời đúng NGÔN NGỮ mà người dùng sử dụng.
    - Không sử dụng Markdown.
    """
    last_user_message = messages[-1]['content'].lower().strip()
    
    # --- LOGIC CÂU TRẢ LỜI CỨNG ---
    
    # 1. Logic Custom Persona (Skemi)
    persona_keywords = ["bạn là ai", "tên bạn", "ai tạo ra bạn", "được phát triển bởi ai"]
    if any(k in last_user_message for k in persona_keywords):
        return "Tôi là Skemi, được huấn luyện bởi nhà phát triển Golden_VN."

    # 2. Logic Custom Date/Time
    date_keywords = ["hôm nay là ngày mấy", "ngày hôm nay", "ngày mấy"]
    if any(k in last_user_message for k in date_keywords):
        now = datetime.now()
        day_of_week = now.strftime("%A")
        
        day_mapping = {
            "Monday": "Thứ Hai", "Tuesday": "Thứ Ba", "Wednesday": "Thứ Tư",
            "Thursday": "Thứ Năm", "Friday": "Thứ Sáu", "Saturday": "Thứ Bảy",
            "Sunday": "Chủ Nhật"
        }
        day_vi = day_mapping.get(day_of_week, day_of_week)
        
        return f"Hôm nay là {day_vi}, ngày {now.day} tháng {now.month} năm {now.year}. Bạn cần giúp gì nữa không?"
    
    # 3. Logic Custom Holiday (Ngày Lễ)
    holiday_keywords = ["hôm nay là ngày lễ gì", "ngày lễ hôm nay"]
    if any(k in last_user_message for k in holiday_keywords):
        now = datetime.now()
        
        if now.month == 11 and now.day == 20:
            return f"Hôm nay, ngày {now.day} tháng {now.month} năm {now.year}, là Ngày Nhà giáo Việt Nam."
        
        return "Hôm nay không có ngày lễ lớn nào được ghi nhận."
        
    # --- END LOGIC CỨNG ---

    # -----------------------------------------------------
    # SYSTEM PROMPT — Đã sửa theo đúng yêu cầu 
    # -----------------------------------------------------
    system_prompt = {
        "role": "system", 
        "content": (
            "Bạn là trợ lý AI Skemi. "
            "Luôn luôn trả lời bằng đúng ngôn ngữ người dùng đang sử dụng. "
            "Nếu người dùng hỏi tiếng Việt thì trả lời tiếng Việt. "
            "Nếu người dùng hỏi tiếng Anh thì trả lời tiếng Anh. "
            "Không sử dụng bất kỳ định dạng Markdown nào như *, **, #, [], v.v. "
            "Chỉ trả lời bằng văn bản thuần túy."
        )
    }
    
    full_messages = [system_prompt] + messages

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=full_messages,
            options={'temperature': 0.5}
        )

        if hasattr(response, 'message') and hasattr(response.message, 'content'):
            return response.message.content
        
        return str(response)

    except Exception as e:
        print(f"Lỗi gọi model SMALL ({MODEL_NAME}): {e}")
        return "Chào bạn! Tôi là trợ lý AI."
