# Train/model_llava.py
import json
import math
import logging
import re
import base64
import os
from typing import Any, List, Tuple

# Try import ollama.chat; nếu không có thì dùng mock fallback
try:
    from ollama import chat
    _OLLAMA_AVAILABLE = True
except Exception:
    _OLLAMA_AVAILABLE = False
    logging.warning("ollama not available - model_llava will use mock responses")

# --- CẤU HÌNH VISION MODEL ---
MODEL_NAME = "llava:7b"
logging.basicConfig(level=logging.INFO)

OLLAMA_OPTIONS = {
    "temperature": 0.05,
    "seed": 42,
}


# -----------------------------------------------------------
# I. CHỨC NĂNG TÍNH TOÁN TỌA ĐỘ VÀ FALLBACK
# -----------------------------------------------------------
def assign_coords_recursive(node: dict, x: float, y: float, level: int = 0) -> dict:
    """Gán tọa độ cho node và đệ quy cho children (giữ nguyên logic của bạn)."""
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


def fallback_to_flat_nodes(input_list: List[str]) -> List[dict]:
    """Tạo node cấp 1 phẳng khi JSON parsing thất bại hoặc model không trả nodes."""
    if not input_list:
        return []
    tree = []
    x_center = 400
    y_start = 120
    node_texts = input_list if isinstance(input_list, list) else [str(input_list)]
    for i, s in enumerate(node_texts):
        if not str(s).strip():
            continue
        node = {"text": str(s).strip(), "children": [], "index": i}
        node['x_side'] = 1 if i % 2 == 0 else -1
        assign_coords_recursive(node, x_center, y_start, level=1)
        tree.append(node)
    return tree


# -----------------------------------------------------------
# II. HỖ TRỢ: CHUYỂN ĐỔI ẢNH => BASE64
# -----------------------------------------------------------
def image_bytes_to_base64(data: Any) -> str:
    """
    Nhận bytes hoặc base64 string hoặc file path.
    Trả về base64 string (không kèm data uri prefix).
    """
    # Nếu đã là base64 dài (dạng string)
    if isinstance(data, str):
        # Heuristics: nếu chuỗi dài và chỉ chứa base64 chars đầu, coi là base64
        if len(data) > 200 and re.fullmatch(r'[A-Za-z0-9+/=\s]+', data[:200]):
            return data.replace("\n", "")
        # Nếu là đường dẫn file
        if os.path.exists(data):
            with open(data, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        # Không hợp lệ -> raise
        raise ValueError("Input string không phải base64 hợp lệ hoặc file không tồn tại")

    # Nếu là bytes / bytearray
    if isinstance(data, (bytes, bytearray)):
        return base64.b64encode(data).decode("utf-8")

    raise ValueError("Unsupported input type for image_bytes_to_base64")


# -----------------------------------------------------------
# III. HỖ TRỢ: LẤY JSON TỪ TEXT (LÀM SẠCH)
# -----------------------------------------------------------
def _clean_and_extract_json(text: str) -> str:
    """
    Làm sạch đầu ra model (loại bỏ ``` code fences, tìm block JSON {...}).
    Trả về chuỗi JSON (hoặc empty string nếu không tìm thấy).
    """
    if not text:
        return ""

    txt = text.strip()

    # Remove common code fences (```json ... ``` or ``` ... ```)
    # If content contains fences, remove surrounding fences first
    if txt.startswith("```") and txt.endswith("```"):
        # remove first and last line fence if exist
        # remove all top/bottom ``` lines
        txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\s*```$", "", txt, flags=re.IGNORECASE)
        txt = txt.strip()

    # Now search for the first {...} block that seems like JSON
    m = re.search(r"\{[\s\S]*\}", txt)
    if m:
        candidate = m.group(0)
        # Fix double-brace common mistakes {{ ... }}
        if candidate.startswith("{{") and candidate.endswith("}}"):
            candidate = candidate[1:-1].strip()
        return candidate.strip()

    # As fallback, try to see if the whole text looks like JSON
    try:
        json.loads(txt)
        return txt
    except Exception:
        return ""


# -----------------------------------------------------------
# IV. CALL OLLAMA / FALLBACK MOCK
# -----------------------------------------------------------
def _call_ollama(base64_image: str, prompt: str) -> str:
    """
    Gọi ollama.chat với messages phù hợp. Trả về raw text.
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Phân tích ảnh và trả về 1 JSON object duy nhất", "images": [base64_image]}
    ]
    # Ollama's chat returns an object with message.content commonly
    resp = chat(model=MODEL_NAME, messages=messages, options=OLLAMA_OPTIONS)
    # try common access patterns
    content = getattr(resp, "message", {}).get("content") if hasattr(resp, "message") else getattr(resp, "content", None)
    if content is None:
        # Last resort: string representation
        content = str(resp)
    return content


def _mock_response_for_image(base64_image: str) -> str:
    """
    Mock trả về JSON để test khi không có ollama.
    Bạn có thể tuỳ chỉnh mẫu này.
    """
    mock = {
        "topic": "Mẫu: Chủ đề từ ảnh",
        "nodes": [
            {"text": "Ý chính 1", "children": [{"text": "Chi tiết 1.1", "children": []}]},
            {"text": "Ý chính 2", "children": []},
            {"text": "Ý chính 3", "children": []}
        ]
    }
    return json.dumps(mock, ensure_ascii=False)


# -----------------------------------------------------------
# V. HÀM CHÍNH: call_mindmap_generation
# -----------------------------------------------------------
def call_mindmap_generation(input_data: Any) -> List[Any]:
    """
    Accepts:
      - bytes (image bytes from UploadFile.read())
      - base64 string
      - file path (optional)
    Returns:
      [topic(str), nodes(list)]
    """
    try:
        # Convert input to base64 string
        try:
            img_base64 = image_bytes_to_base64(input_data)
        except Exception as e:
            logging.exception("image_bytes_to_base64 failed:")
            return ["Lỗi Input Type", []]

        prompt = (
            "Bạn là chuyên gia phân tích tài liệu học thuật. "
            "TÁC VỤ: từ hình ảnh, trích xuất chủ đề chính (topic) và cấu trúc mindmap nodes. "
            "PHẢI TRẢ VỀ 1 JSON OBJECT DUY NHẤT theo định dạng: "
            '{"topic":"chu de","nodes":[{"text":"...","children":[...]}]}'
            " CHỈ TRẢ VỀ JSON, KHÔNG GIẢI THÍCH."
        )

        if _OLLAMA_AVAILABLE:
            raw = _call_ollama(img_base64, prompt)
        else:
            logging.info("ollama không khả dụng - sử dụng mock response cho model_llava")
            raw = _mock_response_for_image(img_base64)

        # Clean and extract JSON block
        cleaned_json = _clean_and_extract_json(raw)
        if not cleaned_json:
            logging.error(f"Lỗi LLaVA Mindmap - Không tìm thấy JSON object. Phản hồi thô: {raw}")
            # As a fallback, try to extract plain lines as nodes (very rough)
            # e.g., split raw by newlines and take first few non-empty lines
            lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
            if lines:
                topic_guess = lines[0][:120]
                nodes = fallback_to_flat_nodes(lines[1:5] or lines)
                return [topic_guess, nodes]
            return ["Lỗi phân tích nội dung từ Vision Model", []]

        # Parse JSON safely
        try:
            data = json.loads(cleaned_json)
        except Exception as e:
            logging.exception("JSON parse error in model_llava:")
            return ["Lỗi phân tích nội dung từ Vision Model", []]

        # Extract topic and nodes
        topic = data.get("topic", "Chủ đề không xác định")
        nodes = data.get("nodes", None)

        # If nodes is not provided or empty, attempt to build flat nodes from other fields
        if not nodes:
            # try other fields like 'points', 'items', or lines inside 'detail' if present
            # gather candidate texts
            candidates = []
            if isinstance(data.get("detail", None), list):
                candidates = data["detail"]
            elif isinstance(data.get("points", None), list):
                candidates = data["points"]
            elif isinstance(data.get("items", None), list):
                candidates = data["items"]
            else:
                # fallback: try to split any textual fields
                for k in ["summary", "text", "description"]:
                    if isinstance(data.get(k, None), (list, str)):
                        if isinstance(data[k], list):
                            candidates = data[k]
                        else:
                            candidates = [line for line in str(data[k]).splitlines() if line.strip()]
                        break

            if candidates:
                nodes = fallback_to_flat_nodes(candidates[:6])
            else:
                # final fallback: create a single root node from topic
                nodes = [{"text": topic, "children": []}]
                # assign coords
                for i, n in enumerate(nodes):
                    n['index'] = i
                    n['x_side'] = 1 if i % 2 == 0 else -1
                    assign_coords_recursive(n, 400, 120, level=1)

        # Ensure nodes is a list and each node has children key
        if not isinstance(nodes, list):
            nodes = []

        def normalize_node(n, idx=0):
            # Ensure keys exist
            text = n.get("text") if isinstance(n, dict) else str(n)
            node_obj = {
                "text": text,
                "children": []
            }
            # normalize children recursively if present
            if isinstance(n, dict) and isinstance(n.get("children", None), list):
                node_obj["children"] = [normalize_node(c, i) for i, c in enumerate(n.get("children", []))]
            node_obj["index"] = n.get("index", idx) if isinstance(n, dict) else idx
            node_obj["x_side"] = n.get("x_side", 1) if isinstance(n, dict) else (1 if idx % 2 == 0 else -1)
            return node_obj

        normalized_nodes = [normalize_node(n, i) for i, n in enumerate(nodes)]
        # Assign coordinates for all nodes
        for n in normalized_nodes:
            assign_coords_recursive(n, 400, 120, level=1)

        return [topic, normalized_nodes]

    except Exception as e:
        logging.exception("call_mindmap_generation exception:")
        return [f"Lỗi phân tích nội dung: {str(e)}", []]


# -----------------------------------------------------------
# VI. HỖ TRỢ TRÍCH XUẤT VĂN BẢN (nếu cần)
# -----------------------------------------------------------
def encode_image_to_base64(image_path: str) -> str:
    """Đọc ảnh từ file path và trả về base64 (giữ cho backward compatibility)."""
    if not os.path.exists(image_path):
        logging.error(f"File không tồn tại: {image_path}")
        return ""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_text_extraction(image_path: str, prompt: str = "Phân tích nội dung hình ảnh này.") -> str:
    """Gọi model để trích xuất text (dùng path legacy)."""
    img_base64 = encode_image_to_base64(image_path)
    if not img_base64:
        return "Lỗi: Không thể đọc file hình ảnh."

    extraction_options = OLLAMA_OPTIONS.copy()
    extraction_options['temperature'] = 0.1

    messages = [
        {"role": "system", "content": (
            "Bạn là một trợ lý phân tích tài liệu học tập chuyên nghiệp. "
            "Trích xuất toàn bộ văn bản và công thức từ hình ảnh, xác định chủ đề chính. "
            "Chỉ trả về văn bản và chủ đề, không giải thích hay mở đầu."
        )},
        {
            "role": "user",
            "content": prompt,
            "images": [img_base64],
        }
    ]

    try:
        if _OLLAMA_AVAILABLE:
            resp = chat(model=MODEL_NAME, messages=messages, options=extraction_options)
            return getattr(resp, "message", {}).get("content") or getattr(resp, "content", None) or str(resp)
        else:
            # fallback: return mock text
            return "Mock extracted text: 1) Ý chính A\n2) Ý chính B\n3) Công thức x = y"
    except Exception as e:
        logging.error(f"Lỗi LLaVA Text Extraction: {e}")
        return "Lỗi Server hoặc LLaVA không phản hồi."
