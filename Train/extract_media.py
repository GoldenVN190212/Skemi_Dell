# --- Trong file chứa process_audio (ví dụ: extract_media.py) ---

import whisper
import logging
import os

# Tải mô hình Whisper chỉ một lần khi khởi động (model "base" hoặc "small" là đủ và nhanh)
# Nếu bạn muốn hiệu suất tốt nhất, dùng "medium" (nhưng chậm hơn)
try:
    # Tải mô hình cơ sở
    WHISPER_MODEL = whisper.load_model("base") 
    logging.info("Whisper model 'base' loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load Whisper model: {e}")
    WHISPER_MODEL = None


def process_audio(file_path: str) -> str:
    """
    Sử dụng OpenAI Whisper để chuyển đổi audio thành text.
    """
    if not WHISPER_MODEL:
        return "[Error: Whisper model not loaded. Check installation.]"
    
    try:
        logging.info(f"Starting Whisper S-t-T for file: {os.path.basename(file_path)}")
        
        # Gọi hàm transcribe của Whisper
        # `fp16=False` giúp chạy trên CPU ổn định hơn
        result = WHISPER_MODEL.transcribe(file_path, fp16=False) 
        
        transcribed_text = result.get("text", "").strip()
        
        if not transcribed_text:
            return "[Error: Whisper returned empty text or model failed to detect speech.]"

        # Trả về text đã trích xuất
        return transcribed_text
        
    except Exception as e:
        logging.error(f"Error during Whisper transcription: {e}")
        return f"[Error: S-t-T failed - {str(e)}]"