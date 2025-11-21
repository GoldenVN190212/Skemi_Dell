# Server.py
import os
import asyncio
import tempfile
import logging
import math
from datetime import datetime, timedelta
from typing import List, Any

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ----------------- MODULES -----------------
from Train.model_gemma_pro_chat import call_gemma_pro_chat
from Train.model_gemma_small_chat import call_gemma__small_chat
from Train.model_granite import call_granite_block 
from Train.ocr_module import extract_text_from_image 

# ----------------- APP INIT -----------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("Css"):
    app.mount("/Css", StaticFiles(directory="Css"), name="Css")
if os.path.exists("Js"):
    app.mount("/Js", StaticFiles(directory="Js"), name="Js")

# ----------------- HELPER: TỌA ĐỘ MINDMAP -----------------
def assign_coords_recursive(node, x, y, level=0):
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

# ----------------- HELPER: TRÍCH XUẤT NỘI DUNG -----------------
def extract_reply_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    try:
        return response.message.content
    except AttributeError:
        pass
    try:
        return response.content
    except AttributeError:
        pass
    try:
        return str(response)
    except:
        return "Lỗi trích xuất nội dung từ model."

# ----------------- HOMEPAGE -----------------
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Home.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Home.html không tồn tại"}, status_code=404)

# ----------------- SESSION & CHAT -----------------
class Question(BaseModel):
    session_id: str
    question: str

sessions = {}
SESSION_TIMEOUT = timedelta(minutes=120)

def assess_complexity(question: str) -> str:
    """Quyết định sử dụng model Small hay Pro"""
    q_lower = question.lower().strip()
    
    low_complexity_keywords = [
        "chào", "hello", "bạn là ai", "ai tạo ra bạn", "tên bạn",
        "hôm nay là ngày mấy", "ngày hôm nay", "ngày mấy"
    ]
    if any(word in q_lower for word in low_complexity_keywords):
        return "small"
    if len(q_lower.split()) < 3 and not any(k in q_lower for k in ["giải", "tóm tắt", "phân tích"]):
        return "small"
    return "pro"

@app.post("/ask")
async def ask_ai(data: Question):
    session = sessions.get(data.session_id, {"messages": []})
    messages = session["messages"]
    
    new_user_question = data.question
    messages.append({"role": "user", "content": new_user_question})
    
    # Đánh giá độ phức tạp
    model_tier = assess_complexity(new_user_question)
    logging.info(f"Question: '{new_user_question}' -> Using Model: {model_tier}")

    # Chọn model phù hợp
    if model_tier == "small":
        model_response = await asyncio.to_thread(call_gemma__small_chat, messages)
        model_used = "gemmaSmall"
    else:
        model_response = await asyncio.to_thread(call_gemma_pro_chat, messages)
        model_used = "gemmaPro"

    # Trích xuất content thuần
    reply_text = extract_reply_content(model_response)
    
    # Lưu session
    messages.append({"role": "assistant", "content": reply_text})
    sessions[data.session_id] = {"messages": messages}
    
    return JSONResponse({"model": model_used, "answer": reply_text})

@app.post("/end_session")
async def end_session(data: dict):
    sid = data.get("session_id")
    if sid in sessions:
        del sessions[sid]
    return {"message": "Session xóa"}

# ----------------- MINDMAP -----------------
@app.post("/generate_mindmap")
async def generate_mindmap(file: UploadFile = File(...)):
    tmp_path = None
    try:
        suffix = "." + file.filename.split(".")[-1] if "." in file.filename else ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_path = tmp.name
        contents = await file.read()
        tmp.write(contents)
        tmp.close()

        logging.info(f"--- BẮT ĐẦU XỬ LÝ FILE: {file.filename} ---")

        # Giai đoạn 1: OCR / HWR (call_granite_block với file path trả về list text)
        extracted_lines = await asyncio.to_thread(call_granite_block, tmp_path)
        logging.info(f"Extracted Lines (GĐ1): {extracted_lines[:5]}...")

        if not extracted_lines or len("".join(extracted_lines).strip()) < 5:
            return JSONResponse({
                "topic": "Không thể đọc nội dung",
                "detail": ["Hình ảnh quá mờ hoặc không có chữ viết rõ ràng."],
                "summary": [],
                "mindmap_nodes": [] 
            })

        topic = extracted_lines[0] if extracted_lines else "Nội dung Mindmap"

        # Giai đoạn 2: Structuring nodes (call_granite_block với list text trả về List[Node] có tọa độ)
        mindmap_nodes_structured = await asyncio.to_thread(call_granite_block, extracted_lines)
        
        # Nếu mô hình trả về cấu trúc phân cấp thành công
        if isinstance(mindmap_nodes_structured, list) and mindmap_nodes_structured and isinstance(mindmap_nodes_structured[0], dict):
            
            topic = extracted_lines[0] if extracted_lines else "Nội dung Mindmap"
            
            final_nodes = mindmap_nodes_structured
            
            detail_list = [n['text'] for n in final_nodes if 'text' in n]
            summary_list = [n['text'] for n in final_nodes[:4] if 'text' in n] 
        else:
            final_nodes = mindmap_nodes_structured 
            detail_list = extracted_lines
            summary_list = extracted_lines[:4]

        # Trả về kết quả
        return JSONResponse({
            "topic": topic,
            "mindmap_nodes": final_nodes, 
            "detail": detail_list,       
            "summary": summary_list      
        })

    except Exception as e:
        logging.exception("Lỗi Server:")
        return JSONResponse({"error": f"Lỗi xử lý Mindmap: {str(e)}"}, status_code=500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# ----------------- RUN -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Server:app", host="127.0.0.1", port=8000, reload=True)