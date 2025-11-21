
# Train/model_llama3_8b.py (Cập nhật)

from ollama import chat 
import json
import math
import logging

MODEL_NAME = "granite3.2-vision:2b-q8_0 "
logging.basicConfig(level=logging.INFO)

# Tham số cố định cho việc gọi AI để tăng tính ổn định
OLLAMA_OPTIONS = {
    "temperature": 0.1, # Rất thấp để đảm bảo cú pháp JSON và kết quả trích xuất ổn định
    "seed": 42
}

def assign_coords_recursive(node, x, y, level=0):
    """Hàm đệ quy để gán tọa độ cho cấu trúc cây JSON."""
    
    # Giữ nguyên logic tính toán tọa độ phức tạp của bạn
    if level == 1:
        # Giả định phân tán cho node cấp 1
        x_pos = 400 + (1 if node.get('x_side', 1) == 1 else -1) * (150 + (node.get('index', 0) // 2) * 50)
        y_pos = 120 + node.get('index', 0) * 80
        node['x'] = x_pos
        node['y'] = y_pos
    elif level > 1:
        # Tính toán góc và khoảng cách tương đối so với cha
        distance = 150 / (level - 1) 
        angle = (node.get('index', 0) * 60) + (180 if level % 2 == 0 else 0)
        
        node['x'] = x + distance * math.cos(math.radians(angle))
        node['y'] = y + distance * math.sin(math.radians(angle))
    
    # Gán tọa độ cho node con
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
    # 1. Nếu là TEXT → Yêu cầu Llama3 8B tạo cấu trúc mindmap nodes (Tree)
    if isinstance(input_data, list):
        text_input = "\n".join(input_data)
        
        json_prompt = f"""
Bạn là AI chuyên nghiệp tạo cấu trúc Mindmap JSON.
Nhiệm vụ: Phân tích danh sách các chủ đề sau: {text_input}
BẮT BUỘC tạo một cấu trúc JSON phân cấp (tối đa 3 cấp) dựa trên mối quan hệ logic của các chủ đề này.
Mỗi node phải có trường 'text' và 'children' (là một mảng các node con).
Sử dụng chủ đề đầu tiên làm node gốc (root node).
TRẢ LỜI CHỈ BẰNG JSON, không thêm bất kỳ lời giải thích hay ký tự nào ngoài JSON.
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
            
            if json_tree and json_tree.get('children'):
                # Gán tọa độ cho node cấp 1 và con cháu
                for i, child in enumerate(json_tree['children']):
                    child['index'] = i
                    child['x_side'] = 1 if i % 2 == 0 else -1 
                    assign_coords_recursive(child, 400, 60, level=1)
                
                return json_tree.get('children')
            
        except Exception as e:
            logging.error(f"Lỗi khi Llama3 8B tạo JSON/Tree: {e}. Fallback về list phẳng.")
            pass 

        # FALLBACK: Logic tạo node cấp 1 phẳng (Nếu JSON bị lỗi)
        tree = []
        x_center = 400
        y_start = 120
        for i, s in enumerate(input_data):
            x_pos = x_center + (1 if i%2==0 else -1) * 150
            y_pos = y_start + i * 70
            tree.append({"text": s, "x": x_pos, "y": y_pos, "children": []})
        return tree

    # 2. Nếu là FILE PATH → gọi Llama3 8B trực tiếp, trả về list text (Tăng cường HWR)
    elif isinstance(input_data, str):
        try:
            detailed_prompt = """
BẠN LÀ CHUYÊN GIA OCR/HWR. Bạn là AI phân tích hình ảnh. 
1. Nhiệm vụ: TẬP TRUNG vào việc đọc chữ viết tay hoặc văn bản trong hình ảnh. 
2. Trích xuất TỐI THIỂU 7 ý chính (subtopics) từ các phép tính/dòng chữ.
3. Trả lời CHỈ bằng danh sách gạch đầu dòng ngắn gọn (mỗi dòng một ý), không giải thích thêm.
"""
            messages = [
                {"role": "system", "content": detailed_prompt},
                {"role": "user", "content": "Phân tích nội dung file. Chú ý đến chữ viết tay.", "images": [input_data]}
            ]
            resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
            content = resp.message.content
            
            # Tăng cường parsing để xử lý các ký tự thừa
            content = content.strip().strip("-").strip("*")
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            lines = [l.strip('- ').strip('* ') for l in lines if l.strip()] # Làm sạch thêm

            logging.info(f"Llama3 8B Parsed Lines: {lines}") 
            return lines
        except Exception as e:
            logging.error("Lỗi Llama3 8B (File path):", e)
            return []

def call_granite_block(subtopics):
    """
    Nhận subtopics → vẽ mindmap hoặc trả về subtopics
    Hiện tại giả lập trả nguyên mảng subtopics
    """
    # TODO: thực hiện gọi Granite3.2-Vision:2b-q8_0 nếu cần image
    return subtopics
