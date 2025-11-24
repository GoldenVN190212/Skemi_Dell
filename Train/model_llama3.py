# Train/model_llama3.py
import json
import math
import logging
import re
import base64
from typing import Any, List, Dict

# Nhập EasyOCR - SỬA LẠI DÙNG RELATIVE IMPORT
try:
    from .ocr_module import extract_text_from_image
    # Lưu file ảnh tạm thời để OCR có thể đọc được (vì EasyOCR dùng path)
    import os
    import tempfile
    
    _OCR_AVAILABLE = True
except ImportError:
    logging.warning("ocr_module not available. Cannot perform OCR fallback.")
    _OCR_AVAILABLE = False


# Try import ollama.chat for Text-Only Model
try:
    from ollama import chat
    _OLLAMA_AVAILABLE = True
    MODEL_NAME = "llama3:8b" 
    
except Exception:
    _OLLAMA_AVAILABLE = False
    logging.warning("ollama not available - mindmap generation will use mock responses")

# --- CẤU HÌNH OLLAMA ---
OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "seed": 42,
    "num_ctx": 4096 
}

logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------
# Các hàm HỖ TRỢ (assign_coords_recursive, _clean_and_extract_json, ...)
# -----------------------------------------------------------

# 1. Hàm làm sạch và trích xuất JSON từ phản hồi của LLM
def _clean_and_extract_json(raw_text: str) -> str | None:
    """Removes non-JSON text and extracts the JSON object."""
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        json_str = match.group(0)
        json_str = json_str.strip()
        
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            json_str = json_str.strip('`').strip()
            if json_str.startswith("json"):
                 json_str = json_str[4:].strip()
            
            try:
                json.loads(json_str)
                return json_str
            except:
                logging.error("Failed to decode cleaned JSON.")
                return None
    return None

# 2. Hàm tạo node phẳng khi LLM/OCR thất bại
def fallback_to_flat_nodes(text_list: List[str]) -> List[Any]:
    """Creates a flat list of mindmap nodes from a list of strings."""
    if not text_list:
        return []
    
    main_nodes = []
    for i, text in enumerate(text_list[:5]):
        main_nodes.append({
            "text": text,
            "children": [],
            "x": 0,
            "y": 0,
        })
    return main_nodes

# 3. Hàm gán tọa độ đệ quy (ĐÃ SỬA ĐỔI THUẬT TOÁN)
def assign_coords_recursive(nodes_list: List[Dict[str, Any]], center_x: int, center_y: int, level: int = 1, angle_offset: float = 0):
    """Recursively assigns (x, y) coordinates to mindmap nodes with better spacing."""
    if not nodes_list:
        return

    # ----------------- CẤP CHÍNH (LEVEL 1) -----------------
    if level == 1:
        total_nodes = len(nodes_list)
        radius = 300  # Khoảng cách lớn hơn từ tâm cho các node chính
        angle_step = 360 / total_nodes
        
        for i, node in enumerate(nodes_list):
            angle = (i * angle_step) % 360
            
            # Gán tọa độ
            node["x"] = center_x + int(radius * math.cos(math.radians(angle)))
            node["y"] = center_y + int(radius * math.sin(math.radians(angle)))
            
            # Đệ quy: truyền tọa độ mới làm tâm, và góc của node cha làm góc tham chiếu
            assign_coords_recursive(node.get("children", []), node["x"], node["y"], level=2, angle_offset=angle)
        
    # ----------------- CẤP CON (LEVEL >= 2) -----------------
    else:
        # nodes_list là danh sách con của một node cha
        parent_angle = angle_offset
        child_radius = 180 
        child_angle_range = 90 # Góc phân tán mặc định
        
        # Nếu node cha nằm ở nửa bên trái màn hình (góc 90 đến 270), đảo chiều góc phân tán
        # Điều này giúp các nhánh luôn hướng ra ngoài
        if 90 < parent_angle < 270:
            child_angle_range = -90 

        num_children = len(nodes_list)
        if num_children > 0:
            # Tính toán góc bắt đầu và bước nhảy
            # Sử dụng (num_children + 1) để tạo khoảng cách đầu và cuối
            angle_step = child_angle_range / (num_children + 1)
            
            for i, child in enumerate(nodes_list):
                # Góc mới là góc cha + góc phân tán
                angle = parent_angle + angle_step * (i + 1)
                
                # Gán tọa độ
                child["x"] = center_x + int(child_radius * math.cos(math.radians(angle)))
                child["y"] = center_y + int(child_radius * math.sin(math.radians(angle)))
                
                # Đệ quy cho cấp con tiếp theo
                assign_coords_recursive(child.get("children", []), child["x"], child["y"], level + 1, angle_offset=angle)


# Hàm Hỗ trợ: Lưu bytes thành file tạm thời để EasyOCR xử lý
def save_bytes_to_tempfile(file_bytes: bytes, suffix: str = ".png") -> str:
    """Saves bytes to a temporary file and returns the path."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(file_bytes)
    finally:
        temp_file.close()
    return temp_file.name


# -----------------------------------------------------------
# HÀM CHÍNH: call_mindmap_generation (Dùng Text-Only LLM)
# -----------------------------------------------------------
def call_mindmap_generation(input_data: bytes) -> List[Any]:
    """
    Chấp nhận: image/document bytes
    Trả về: [topic(str), nodes(list)]
    """
    if not _OCR_AVAILABLE:
        return ["Lỗi cấu hình: Thiếu EasyOCR Module", []]
    
    if not _OLLAMA_AVAILABLE:
        return ["Chủ đề Mock", fallback_to_flat_nodes(["Ý chính 1", "Ý chính 2", "Ý chính 3"])]

    # --- BƯỚC 1: TRÍCH XUẤT VĂN BẢN (OCR) ---
    temp_path = None
    try:
        temp_path = save_bytes_to_tempfile(input_data)
        ocr_result_lines = extract_text_from_image(temp_path)
        
        if not ocr_result_lines:
            return ["Lỗi OCR: Không trích xuất được văn bản", []]
        
        input_text = "\n".join(ocr_result_lines)
        logging.info(f"OCR thành công. Trích xuất {len(ocr_result_lines)} dòng.")

    except Exception as e:
        logging.exception("Lỗi xử lý OCR:")
        return [f"Lỗi xử lý OCR: {str(e)}", []]
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            
    # --- BƯỚC 2: LLM TẠO CẤU TRÚC MINDMAP (SỬ DỤNG PROMPT ĐÃ SỬA) ---
    prompt = (
        "Bạn là chuyên gia tạo sơ đồ tư duy. TÁC VỤ: Dựa trên văn bản sau, "
        "hãy xác định CHỦ ĐỀ CHÍNH (TOPIC) và tạo cấu trúc mindmap nodes (tối đa 3 cấp độ). "
        "Quy tắc bắt buộc:\n"
        "1. CHỦ ĐỀ CHÍNH (topic) PHẢI là một từ/cụm từ tổng quát bằng TIẾNG ANH (ví dụ: 'Football Player' thay vì 'CR7'; 'Mathematics' thay vì 'Math Equation').\n"
        "2. Các nodes con (text trong children) PHẢI là Tiếng Việt.\n"
        "3. PHẢI TRẢ VỀ 1 JSON OBJECT DUY NHẤT theo định dạng: "
        '{"topic":"TOPIC_IN_ENGLISH","nodes":[{"text":"Node Tiếng Việt","children":[...]}]}. '
        "CHỈ TRẢ VỀ JSON, KHÔNG GIẢI THÍCH.\n\n"
        "Văn bản:\n"
        f"--- {input_text} ---"
    )
    
    try:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Phân tích văn bản trên và trả về JSON cấu trúc Mindmap."}
        ]
        
        resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
        raw = getattr(resp, "message", {}).get("content", str(resp))
        
        cleaned_json = _clean_and_extract_json(raw)
        if not cleaned_json:
            logging.error(f"Lỗi Mindmap - Không tìm thấy JSON. Phản hồi thô: {raw}")
            lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()][:5]
            if lines:
                topic_guess = lines[0][:120] if lines else "Chủ đề không xác định"
                nodes = fallback_to_flat_nodes(lines[1:] or lines)
                if not nodes:
                    nodes = [{"text": topic_guess, "children": []}]
                return [topic_guess, nodes]
            return ["Lỗi phân tích nội dung từ LLM", []]

        data = json.loads(cleaned_json)
        topic = data.get("topic", "Chủ đề không xác định")
        nodes = data.get("nodes", [])

        # Gán tọa độ cho các node cấp 1 và con cháu
        # Sửa center Y từ 60 lên 300 để có không gian vẽ tốt hơn
        assign_coords_recursive(nodes, 400, 300, level=1) 

        return [topic, nodes]

    except Exception as e:
        logging.exception("call_mindmap_generation exception:")
        return [f"Lỗi xử lý LLM Mindmap: {str(e)}", []]