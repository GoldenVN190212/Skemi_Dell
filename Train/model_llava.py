import json
import math # Giữ math nhưng không dùng trong logic tính tọa độ
import logging
import re
import tempfile
from typing import Any, List, Dict
import os

# (Giữ nguyên phần import module OCR và OLLAMA)
try:
    from .ocr_module import extract_text_from_image
    _OCR_AVAILABLE = True
except ImportError:
    logging.warning("OCR module not available.")
    _OCR_AVAILABLE = False

try:
    from ollama import chat
    _OLLAMA_AVAILABLE = True
    MODEL_NAME = "llava:13b"
    OLLAMA_OPTIONS = {"temperature":0.1, "seed":42, "num_ctx":4096}
except Exception:
    logging.warning("OLLAMA not available, using mock")
    _OLLAMA_AVAILABLE = False

logging.basicConfig(level=logging.INFO)

def _clean_and_extract_json(raw_text: str) -> str | None:
    # Tìm đoạn JSON từ { đến }
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        json_str = match.group(0).strip()
        try:
            json.loads(json_str)
            return json_str
        except:
            return None
    return None

def simple_vn_to_en_topic(vn_topic: str) -> str:
    """
    Hàm làm sạch chủ đề (giữ nguyên logic của bạn)
    """
    vn_topic = vn_topic.strip()
    vn_topic = re.sub(r'[\{\}\'"]', '', vn_topic).strip()
    
    # Xử lý các nhãn tiếng Việt còn sót lại (chỉ là ví dụ nhỏ)
    if 'biến đổi khí hậu' in vn_topic.lower():
        return 'Climate Change'
    if 'tê giác trắng phương bắc' in vn_topic.lower():
        return 'Northern White Rhino'
    if 'ô nhiễm nhựa thái bình dương' in vn_topic.lower():
        return 'Pacific Plastic Pollution'
    
    if not vn_topic:
        return 'Topic Not Found'
        
    return vn_topic 

def fallback_to_flat_nodes(text_list: List[str]) -> List[Any]:
    """
    SỬA: Loại bỏ việc gán tọa độ x, y thủ công.
    """
    nodes = []
    # Chỉ lấy các dòng có nội dung đáng kể
    clean_texts = [t for t in text_list if len(t.split()) > 2]
    for i, text in enumerate(clean_texts[:5]):
        # Đã loại bỏ x và y
        nodes.append({"text": text, "children": [], "id": f"f{i}"})
    return nodes

# --- PHẦN BỊ XÓA (Logic tính toán tọa độ) ---
# XÓA toàn bộ hàm assign_coords_recursive (vì Frontend đã dùng Vis.js để tự động layout)
# def assign_coords_recursive(nodes_list: List[Dict[str, Any]], center_x: int, center_y: int, level: int =1, angle_offset: float=0):
#     if not nodes_list: return
#     ...
# ---------------------------------------------


def save_bytes_to_tempfile(file_bytes: bytes, suffix: str = ".png") -> str:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(file_bytes)
    finally:
        temp_file.close()
    return temp_file.name


def call_mindmap_generation(input_data: bytes) -> List[Any]:
    if not _OCR_AVAILABLE:
        return ["Error: OCR Module is not available", []]
    if not _OLLAMA_AVAILABLE:
        return ["Mock Topic - English", fallback_to_flat_nodes(["Main Idea 1", "Main Idea 2"])]

    temp_path = None
    try:
        temp_path = save_bytes_to_tempfile(input_data)
        ocr_lines = extract_text_from_image(temp_path)
        
        # SỬA 1: Xử lý trường hợp ảnh không có chữ (Logic VLLM giữ nguyên)
        if not ocr_lines or not "".join(ocr_lines).strip():
            logging.warning("No significant text extracted by OCR. Using VLLM for image description.")
            
            # --- TẠO PROMPT MỚI CHO VLLM (Visual Language Model) ---
            vllm_prompt = (
                "You are a Mind Map Topic Identifier. "
                "TASK: Identify the MAIN TOPIC/SUBJECT of the uploaded IMAGE (no OCR text available). "
                "Respond ONLY with a JSON object: {'topic':'TOPIC_IN_ENGLISH','nodes':[]}. "
                "If the image is a person/logo/simple object, use the name as the topic. If it's a diagram, describe the subject."
                "Example 1: {'topic':'Cristiano Ronaldo Footballer','nodes':[]}. Example 2: {'topic':'Chatbot Digital Assistant','nodes':[]}"
            )
            
            messages_vllm = [
                {"role":"system","content": vllm_prompt},
                {"role":"user","content":[{"type":"text","text":"Analyze image for main topic."}, {"type":"image","path":temp_path}]}
            ]
            
            resp_vllm = chat(model=MODEL_NAME, messages=messages_vllm, options=OLLAMA_OPTIONS)
            raw_vllm = getattr(resp_vllm, "message", {}).get("content", str(resp_vllm))
            cleaned_json_vllm = _clean_and_extract_json(raw_vllm)
            
            if cleaned_json_vllm:
                data_vllm = json.loads(cleaned_json_vllm)
                topic = simple_vn_to_en_topic(data_vllm.get("topic", "Topic Not Found"))
                
                # Trả về ngay khi xác định được chủ đề ảnh, không có nodes
                return [topic, []] 
            
            return ["Topic Not Found (Image or OCR Empty)", []]


        input_text = "\n".join(ocr_lines)
        logging.info(f"OCR success: {len(ocr_lines)} lines")

        # SỬA 2: ÉP buộc đầu ra Tiếng Anh cho TOPIC và kèm theo YÊU CẦU JSON (Logic giữ nguyên)
        prompt = (
            "You are a mind map generation expert. TASK: Based on the following text, "
            "identify the MAIN TOPIC in **ENGLISH** and create mindmap nodes in Vietnamese "
            "up to 3 levels deep. ONLY RETURN JSON: {'topic':'TOPIC_IN_ENGLISH','nodes':[{'text':'','children':[...]}]}. "
            f"Text:\n--- {input_text} ---"
        )
        messages = [
            {"role":"system","content":prompt},
            {"role":"user","content":"Analyze text and return JSON mindmap."}
        ]
        
        resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
        raw = getattr(resp, "message", {}).get("content", str(resp))
        cleaned_json = _clean_and_extract_json(raw)
        
        if not cleaned_json:
            logging.warning(f"LLM failed to return valid JSON. Fallback initiated. Raw response: {raw[:100]}...")
            
            # FALLBACK LOGIC
            lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
            topic_guess = "Undefined Topic (JSON Error)"
            nodes = []
            
            if lines:
                first_line = lines[0].strip()
                topic_raw = first_line.replace('{','').replace('}','').split(',')[0].split(':')[-1].strip().replace("'", "").replace('"', "")
                topic_guess = simple_vn_to_en_topic(topic_raw) 
                nodes = fallback_to_flat_nodes(lines)
                
            return [topic_guess, nodes]

        # LOGIC KHI THÀNH CÔNG JSON
        data = json.loads(cleaned_json)
        topic = data.get("topic", "")
        nodes = data.get("nodes", [])
        
        if not topic or (isinstance(topic, str) and topic.strip() == ''):
            topic = "Topic Not Found (Empty Field)"
        else:
            topic = simple_vn_to_en_topic(topic) 
            
        # --- ĐÃ XÓA LỆNH GỌI TÍNH TỌA ĐỘ ---
        # assign_coords_recursive(nodes, 400, 300)
        # ------------------------------------
        return [topic, nodes]

    except Exception as e:
        logging.exception("call_mindmap_generation error:")
        return [f"Error processing Mindmap: {str(e)}", []]
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)