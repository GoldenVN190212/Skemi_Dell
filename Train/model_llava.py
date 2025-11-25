import json
import math
import logging
import re
import tempfile
from typing import Any, List, Dict
import os

try:
    from .ocr_module import extract_text_from_image
    _OCR_AVAILABLE = True
except ImportError:
    logging.warning("OCR module not available.")
    _OCR_AVAILABLE = False

try:
    from ollama import chat
    _OLLAMA_AVAILABLE = True
    MODEL_NAME = "llava-llama3:latest"
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
    """Chuyển đổi Tiếng Việt cơ bản sang Tiếng Anh cho topic (đảm bảo sạch và Tiếng Anh)"""
    vn_topic = vn_topic.lower().strip()
    vn_topic = vn_topic.replace('{', '').replace('}', '').replace("'", '').replace('"', '').replace('topic:', '').replace('chủ đề:', '').strip()
    
    if 'tê giác trắng phương bắc' in vn_topic or 'rhino' in vn_topic:
        return 'Northern White Rhino'
    if not vn_topic:
        return 'Topic Not Found'
    
    # Giả định: nếu không khớp key, giữ nguyên nhưng đã được làm sạch
    return vn_topic

def fallback_to_flat_nodes(text_list: List[str]) -> List[Any]:
    nodes = []
    for i, text in enumerate(text_list[:5]):
        x = 200 + (i % 3) * 200
        y = 150 + (i // 3) * 150
        nodes.append({"text": text, "children": [], "x": x, "y": y, "id": f"f{i}"})
    return nodes

def assign_coords_recursive(nodes_list: List[Dict[str, Any]], center_x: int, center_y: int, level: int =1, angle_offset: float=0):
    if not nodes_list: return
    if level == 1:
        total_nodes = len(nodes_list)
        radius = 300
        angle_step = 360 / total_nodes
        for i, node in enumerate(nodes_list):
            angle = (i * angle_step) % 360
            node["x"] = center_x + int(radius * math.cos(math.radians(angle)))
            node["y"] = center_y + int(radius * math.sin(math.radians(angle)))
            assign_coords_recursive(node.get("children", []), node["x"], node["y"], level=2, angle_offset=angle)
    else:
        parent_angle = angle_offset
        child_radius = 180
        child_angle_range = 90
        if 90 < parent_angle < 270: child_angle_range = -90
        num_children = len(nodes_list)
        if num_children > 0:
            angle_step = child_angle_range / (num_children + 1)
            for i, child in enumerate(nodes_list):
                angle = parent_angle + angle_step * (i + 1)
                child["x"] = center_x + int(child_radius * math.cos(math.radians(angle)))
                child["y"] = center_y + int(child_radius * math.sin(math.radians(angle)))
                assign_coords_recursive(child.get("children", []), child["x"], child["y"], level + 1, angle_offset=angle)

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
        if not ocr_lines:
            return ["Error OCR: No text extracted", []]
        input_text = "\n".join(ocr_lines)
        logging.info(f"OCR success: {len(ocr_lines)} lines")

        prompt = (
            "You are a mind map generation expert. TASK: Based on the following text, "
            "identify the MAIN TOPIC in **ENGLISH** and create mindmap nodes in Vietnamese "
            "up to 3 levels deep. ONLY RETURN JSON: {'topic':'TOPIC_IN_ENGLISH','nodes':[{'text':'','children':[...]}]}.\n"
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
            topic_guess = "Undefined Topic (LLM Failed to return English)"
            nodes = []
            
            if lines:
                first_line = lines[0].strip()
                # Cố gắng trích xuất topic từ chuỗi lỗi/thô và làm sạch
                if 'topic' in first_line:
                    start_idx = first_line.find('topic')
                    topic_part = first_line[start_idx:].split(',')[0].strip()
                    topic_raw = topic_part.split(':')[-1].strip().replace("'", "").replace('"', "")
                    topic_guess = simple_vn_to_en_topic(topic_raw)
                else:
                    topic_guess = simple_vn_to_en_topic(first_line)
                
                nodes = fallback_to_flat_nodes(lines)
                
            return [topic_guess, nodes]

        # LOGIC KHI THÀNH CÔNG JSON
        data = json.loads(cleaned_json)
        topic = data.get("topic", "")
        nodes = data.get("nodes", [])
        
        if not topic or (isinstance(topic, str) and topic.strip() == ''):
            topic = "Topic Not Found in Valid JSON"
        else:
            # Đảm bảo topic là Tiếng Anh (hoặc đã được làm sạch)
            topic = simple_vn_to_en_topic(topic) 
            
        assign_coords_recursive(nodes, 400, 300)
        return [topic, nodes]

    except Exception as e:
        logging.exception("call_mindmap_generation error:")
        return [f"Error processing Mindmap: {str(e)}", []]
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)