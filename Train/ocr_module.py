# Train/ocr_module.py
import easyocr
import logging

logging.basicConfig(level=logging.INFO)

# Khởi tạo Reader một lần để không tốn thời gian load lại model
# 'vi' là tiếng Việt, 'en' là tiếng Anh
try:
    # SỬA LẠI: Chuyển sang dùng CPU (gpu=False) để tránh lỗi cài đặt CUDA/PyTorch
    reader = easyocr.Reader(['vi', 'en'], gpu=False) 
    logging.info("EasyOCR model loaded successfully (CPU mode).")
except Exception as e:
    logging.error(f"Failed to load EasyOCR: {e}")
    reader = None

def extract_text_from_image(image_path):
    """
    Sử dụng EasyOCR để trích xuất văn bản từ ảnh.
    Trả về LIST các dòng văn bản.
    """
    if not reader:
        return []
        
    try:
        # detail=0 trả về LIST các chuỗi (strings)
        result = reader.readtext(image_path, detail=0, paragraph=False) 
        
        # Làm sạch các dòng trống nếu có
        cleaned_lines = [line.strip() for line in result if line.strip()]
        
        return cleaned_lines
    except Exception as e:
        logging.error(f"OCR Error: {e}")
        return []