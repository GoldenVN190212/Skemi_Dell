# Train/model_granite.py 

from ollama import chat 
import json
import math
import logging

MODEL_NAME = "granite3.2-vision:2b-q8_0" 
logging.basicConfig(level=logging.INFO)

OLLAMA_OPTIONS = {
    "temperature": 0.1, 
    "seed": 42
}

def assign_coords_recursive(node, x, y, level=0):
    """Hàm đệ quy để gán tọa độ cho cấu trúc cây JSON."""
    
    if level == 1:
        # Cấp 1: Phân tán sang hai bên
        x_pos = 400 + (1 if node.get('x_side', 1) == 1 else -1) * (180 + (node.get('index', 0) // 2) * 60)
        y_pos = 120 + node.get('index', 0) * 100
        node['x'] = x_pos
        node['y'] = y_pos
    elif level > 1:
        # Cấp 2 trở đi: Hình tròn xung quanh node cha
        distance = 150 / (level - 0.5)
        angle = (node.get('index', 0) * 45) + (180 if level % 2 == 0 else 0)
        
        node['x'] = x + distance * math.cos(math.radians(angle))
        node['y'] = y + distance * math.sin(math.radians(angle))
    
    if node.get('children'):
        for i, child in enumerate(node['children']):
            child['index'] = i
            child['x_side'] = node.get('x_side', 1)
            assign_coords_recursive(child, node['x'], node['y'], level + 1)
    
    return node

def fallback_to_flat_nodes(input_list):
    """Logic Fallback tạo node cấp 1 phẳng khi JSON parsing thất bại."""
    if not input_list: return []
    
    tree = []
    x_center = 400
    y_start = 120
    
    # Dòng đầu tiên là Topic
    node_texts = input_list[1:] if len(input_list) > 1 else input_list
    
    for i, s in enumerate(node_texts):
        node = {"text": s, "children": [], "index": i}
        node['x_side'] = 1 if i % 2 == 0 else -1 
        
        assign_coords_recursive(node, x_center, y_start, level=1)
        tree.append(node)
        
    return tree

def call_granite_block(input_data):
    """
    input_data: str (file path) HOẶC List (dữ liệu đã được trích xuất từ file path)
    """
    # Xử lý trường hợp Server.py gọi lại với list thô khi bước 1 thất bại (Fallback 1)
    if isinstance(input_data, list):
        return fallback_to_flat_nodes(input_data)
        
    # Xử lý trường hợp là FILE PATH (Bước chính)
    elif isinstance(input_data, str):
        
        json_prompt = """
BẠN LÀ CHUYÊN GIA PHÂN TÍCH VÀ CẤU TRÚC DỮ LIỆU.
Nhiệm vụ:
1. Trích xuất toàn bộ văn bản/công thức/ý chính từ hình ảnh.
2. Từ nội dung trích xuất, xác định CHỦ ĐỀ CHÍNH.
3. Tạo cấu trúc Mindmap JSON phân cấp (tối đa 3 cấp) dựa trên mối quan hệ logic.

Yêu cầu định dạng JSON BẮT BUỘC:
{{
    "topic": "Chủ đề chính được trích xuất từ hình ảnh",
    "nodes": [
        {{ "text": "Ý chính cấp 1 thứ nhất", "children": [...] }},
        {{ "text": "Ý chính cấp 1 thứ hai", "children": [...] }}
        // ...
    ]
}}
TRẢ LỜI CHỈ BẰNG OBJECT JSON, không thêm bất kỳ lời giải thích hay ký tự nào ngoài JSON.
"""
        try:
            messages = [
                {"role": "system", "content": json_prompt},
                {"role": "user", "content": "Phân tích nội dung file. Chú ý đến chữ viết tay hoặc công thức.", "images": [input_data]}
            ]
            
            resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
            content = resp.message.content
            
            # Làm sạch JSON
            content = content.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "", 1)
            if content.endswith("```"):
                content = content.rstrip("`")
            
            json_data = json.loads(content)
            
            topic = json_data.get("topic", "Chủ đề không xác định")
            final_nodes = json_data.get("nodes", [])

            # Gán tọa độ cho các node cấp 1 và con cháu
            for i, child in enumerate(final_nodes):
                child['index'] = i
                child['x_side'] = 1 if i % 2 == 0 else -1 
                assign_coords_recursive(child, 400, 60, level=1)
            
            # Trả về DẠNG ĐẶC BIỆT: [topic_str, list_of_nodes]
            return [topic, final_nodes]

        except Exception as e:
            logging.error(f"Lỗi Granite Block (File path) - Lỗi JSON/Kỹ thuật: {e}")
            # Fallback 2: Trả về dữ liệu thô báo lỗi cho Server.py xử lý
            return ["Lỗi phân tích nội dung từ Vision Model", []] 
            
    return ["Lỗi Input Type", []]