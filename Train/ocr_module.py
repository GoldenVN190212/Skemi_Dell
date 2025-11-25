import easyocr
import logging

logging.basicConfig(level=logging.INFO)
try:
    # Tải EasyOCR (giả định đã được cài đặt)
    reader = easyocr.Reader(['vi','en'], gpu=False)
    logging.info("EasyOCR loaded (CPU mode).")
except Exception as e:
    logging.error(f"OCR init error: {e}")
    reader = None

def extract_text_from_image(image_path):
    if not reader:
        return []
    try:
        # Sử dụng paragraph=False để giữ các dòng riêng biệt
        lines = reader.readtext(image_path, detail=0, paragraph=False) 
        return [l.strip() for l in lines if l.strip()]
    except Exception as e:
        logging.error(f"OCR Error: {e}")
        return []