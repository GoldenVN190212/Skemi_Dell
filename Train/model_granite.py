# Train/model_granite.py (Đã cập nhật để loại bỏ Mock Response)

from ollama import chat 
import json
import math
import logging

MODEL_NAME = "granite3.2-vision:2b-q8_0" # Cần đảm bảo model này có sẵn và đang chạy
logging.basicConfig(level=logging.INFO)

OLLAMA_OPTIONS = {
    "temperature": 0.1, 
    "seed": 42
}

def assign_coords_recursive(node, x, y, level=0):
    """Hàm đệ quy để gán tọa độ cho cấu trúc cây JSON."""
    
    if level == 1:
        x_pos = 400 + (1 if node.get('x_side', 1) == 1 else -1) * (180 + (node.get('index', 0) // 2) * 60)
        y_pos = 120 + node.get('index', 0) * 100
        node['x'] = x_pos
        node['y'] = y_pos
    elif level > 1:
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

def call_granite_block(input_data):
    """
    input_data: list subtopics (text) HOẶC str (file path)
    """
    # 1. Nếu là TEXT → Yêu cầu tạo cấu trúc mindmap nodes (Tree) + Gán tọa độ
    if isinstance(input_data, list):
        text_input = "\n".join(input_data)
        
        json_prompt = f"""
Bạn là AI chuyên nghiệp tạo cấu trúc Mindmap JSON.
Nhiệm vụ: Phân tích danh sách các chủ đề sau: {text_input}
BẮT BUỘC tạo một cấu trúc JSON phân cấp (tối đa 3 cấp) dựa trên mối quan hệ logic của các chủ đề này.
Định dạng JSON phải là một *mảng* chứa các node cấp 1 (là con của node gốc - Topic), mỗi node phải có trường 'text' và 'children' (là một mảng các node con).
TRẢ LỜI CHỈ BẰNG MẢNG JSON, không thêm bất kỳ lời giải thích hay ký tự nào ngoài JSON.
"""
        try:
            messages = [
                {"role": "system", "content": json_prompt},
                {"role": "user", "content": "Tạo cấu trúc mindmap từ danh sách trên."}
            ]
            
            resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
            content = resp.message.content
            
            content = content.strip().strip("```json").strip("```")

            json_tree = json.loads(content)
            final_nodes = json_tree 
        
            # Gán tọa độ cho các node cấp 1 và con cháu
            for i, child in enumerate(final_nodes):
                child['index'] = i
                child['x_side'] = 1 if i % 2 == 0 else -1 
                assign_coords_recursive(child, 400, 60, level=1)
                
            return final_nodes

        except Exception as e:
            logging.error(f"Lỗi khi tạo JSON Mindmap: {e}. Fallback về list phẳng có tọa độ.")
            
            # FALLBACK: Logic tạo node cấp 1 phẳng (Có tọa độ)
            tree = []
            x_center = 400
            y_start = 120
            
            node_texts = input_data[1:] if len(input_data) > 1 else input_data
            
            for i, s in enumerate(node_texts):
                node = {"text": s, "children": [], "index": i}
                node['x_side'] = 1 if i % 2 == 0 else -1 
                
                assign_coords_recursive(node, x_center, y_start, level=1)
                tree.append(node)
                
            return tree


    # 2. Nếu là FILE PATH → gọi Vision Model, trả về list text (OCR/HWR)
    elif isinstance(input_data, str):
        try:
            detailed_prompt = """
BẠN LÀ CHUYÊN GIA OCR/HWR. Bạn là AI phân tích hình ảnh/tài liệu. 
1. Nhiệm vụ: Đọc toàn bộ chữ viết tay hoặc văn bản/công thức.
2. Trích xuất: Dòng đầu tiên là CHỦ ĐỀ CHÍNH, sau đó là TỐI THIỂU 7 ý chính (subtopics) dưới dạng gạch đầu dòng.
3. Trả lời CHỈ bằng danh sách gạch đầu dòng ngắn gọn (mỗi dòng một ý), không giải thích thêm.
"""
            messages = [
                {"role": "system", "content": detailed_prompt},
                {"role": "user", "content": "Phân tích nội dung file. Chú ý đến chữ viết tay hoặc công thức Toán học.", "images": [input_data]}
            ]
            
            # 🟢 KÍCH HOẠT LỜI GỌI THỰC TẾ
            resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
            content = resp.message.content
            
            content = content.strip().strip("-").strip("*")
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            lines = [l.strip('- ').strip('* ') for l in lines if l.strip()] 

            logging.info(f"Granite Parsed Lines: {lines}") 
            return lines
        except Exception as e:
            logging.error(f"Lỗi Granite Block (File path): {e}")
            return []
            
    return []