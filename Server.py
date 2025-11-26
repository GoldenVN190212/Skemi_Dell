import os
import asyncio
import logging
import math
import hashlib 
from datetime import datetime, timedelta
from typing import Any, List, Dict 
import json 

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langdetect import detect

# ----------------- MODULES -----------------
try:
    # Cần đảm bảo các module này tồn tại hoặc được mock
    from Train.model_gemma_pro_chat import call_gemma_pro_chat
    from Train.model_gemma_small_chat import call_gemma__small_chat
    from Train.model_llava import call_mindmap_generation # Dùng phiên bản đã sửa
except ImportError as e:
    logging.error(f"Error importing AI modules: {e}. Using local mocks.")
    def call_gemma_pro_chat(messages):
        logging.info("Calling mock gemma pro...")
        last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), "Hello!")
        return f"Mock Pro: I am running in mock mode. You asked: {last_user_message}" 

    def call_gemma__small_chat(messages):
        logging.info("Calling mock gemma small...")
        last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), "Hello!")
        return f"Mock Small: I am running in mock mode. You asked: {last_user_message}"
    
    def call_mindmap_generation(input_data: Any) -> List[Any]:
        # SỬA MOCK: Đảm bảo nodes mock KHÔNG CÓ x, y 
        return ["Mock Topic - Document Analysis (English)", [{"text": "Mock Node Main", "children": [{"text": "Mock Child Node"}], "id": "m1"}]]


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

os.makedirs("tmp_files", exist_ok=True)

# ----------------- CACHE & SESSION GLOBAL -----------------
mindmap_cache: Dict[str, Any] = {} # Key: file_hash, Value: (topic, nodes, detail, summary)
sessions = {}
SESSION_TIMEOUT = timedelta(minutes=120)

# ----------------- HELPERS -----------------
def extract_reply_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "message", {}).get("content") or getattr(response, "content", None) or str(response)

def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        if lang not in ["vi", "en"]:
            return "en" 
        return lang
    except:
        return "en"

def assess_complexity(question: str) -> str:
    q_lower = question.lower().strip()
    low_complexity_keywords = [
        "chào", "hello", "xin chào", "hi", "hey",
        "bạn là ai", "ai tạo ra bạn", "tên bạn", "who are you", "what is your name",
        "hôm nay là ngày mấy", "ngày hôm nay", "ngày mấy", "today's date", "what time is it",
        "lộ vậy", "đùa tao à", "hả", "sao", "what", "fuck", "shit", "why you so small", 
        "làm ơn", "please", "thank you", "cảm ơn" 
    ]
    
    if any(word in q_lower for word in low_complexity_keywords) or len(q_lower.split()) <= 4:
        return "small"
    
    high_complexity_keywords = ["giải thích", "phân tích", "tóm tắt", "sự khác biệt", "vì sao", "how does", "what is the difference", "tóm gọn"]
    if any(word in q_lower for word in high_complexity_keywords):
        return "pro"
        
    if len(q_lower.split()) > 6:
        return "pro"

    return "small"


# ----------------- HOMEPAGE & CHAT (Giữ nguyên) -----------------
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Home.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Home.html không tồn tại"}, status_code=404)

class Question(BaseModel):
    session_id: str
    question: str

@app.post("/ask")
async def ask_ai(data: Question):
    now = datetime.utcnow()
    session = sessions.get(data.session_id)

    if not session or now - session["created_at"] > SESSION_TIMEOUT:
        session = {"messages": [], "created_at": now}

    messages = session["messages"]
    messages.append({"role": "user", "content": data.question})

    model_tier = assess_complexity(data.question)
    language = detect_language(data.question) 

    system_prompt = {
        "vi": "Bạn là trợ lý AI hữu ích, lịch sự và thân thiện. Luôn trả lời bằng tiếng Việt.",
        "en": "You are a helpful, polite, and friendly AI assistant. Always reply in English.",
    }.get(language, "You are a helpful, polite, and friendly AI assistant.")

    messages_with_system = [{"role": "system", "content": system_prompt}] + messages[-5:]

    logging.info(f"[{data.session_id}] Ngôn ngữ: {language} | Model: {model_tier}")

    if model_tier == "small":
        model_response = await asyncio.to_thread(call_gemma__small_chat, messages_with_system)
        model_used = "gemmaSmall"
    else:
        model_response = await asyncio.to_thread(call_gemma_pro_chat, messages_with_system)
        model_used = "gemmaPro"

    reply_text = extract_reply_content(model_response)
    
    messages.append({"role": "assistant", "content": reply_text})
    sessions[data.session_id] = {"messages": messages, "created_at": now}

    return JSONResponse({"model": model_used, "answer": reply_text})

@app.post("/end_session")
async def end_session(data: dict):
    sid = data.get("session_id")
    if sid in sessions:
        del sessions[sid]
    return {"message": "Session đã được xóa"}

# ----------------- MINDMAP (KÈM CACHE) -----------------
@app.post("/generate_mindmap")
async def generate_mindmap(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        
        # 1. Tính Hash SHA-256
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # 2. KIỂM TRA CACHE
        if file_hash in mindmap_cache:
            logging.info(f"Cache HIT for hash: {file_hash}")
            topic, final_nodes, detail_list, summary_list = mindmap_cache[file_hash]
            return JSONResponse({
                "topic": topic,
                "mindmap_nodes": final_nodes, # Nodes không có x, y
                "detail": detail_list,
                "summary": summary_list
            })

        # 3. KHÔNG CÓ CACHE -> GỌI MODEL
        logging.info(f"Cache MISS for hash: {file_hash}. Calling Mindmap generation...")
        result = await asyncio.to_thread(call_mindmap_generation, file_bytes) 

        if not isinstance(result, list) or len(result) != 2:
            raise Exception(f"Vision Model trả về định dạng không hợp lệ: {result}")

        topic, final_nodes = result # final_nodes ở đây là cấu trúc cây không có tọa độ

        if isinstance(topic, str) and topic.startswith(("Lỗi", "Error", "Cannot", "Undefined Topic")):
            # Xử lý lỗi từ mô hình vision/OCR/Fallback
            return JSONResponse({
                 "topic": topic,
                 "detail": [f"Không thể phân tích hoặc Mindmap bị lỗi: {topic}"],
                 "summary": [],
                 "mindmap_nodes": []
               })

        if not final_nodes:
            return JSONResponse({
                "topic": topic if topic else "Topic Not Found",
                "detail": ["Not enough content to create mindmap."],
                "summary": [],
                "mindmap_nodes": []
            })

        # Extract text for detail/summary
        def extract_all_text(node):
            items = [node.get("text", "")]
            for child in node.get("children", []):
                items.extend(extract_all_text(child))
            return [i for i in items if i.strip()]

        detail_list = []
        summary_list = []
        for node in final_nodes:
            detail_list.extend(extract_all_text(node))
            summary_list.append(node.get("text", ""))

        # 4. LƯU VÀO CACHE TRƯỚC KHI TRẢ VỀ
        mindmap_cache[file_hash] = (topic, final_nodes, detail_list, summary_list)
        logging.info(f"Cache SAVED for hash: {file_hash}")

        return JSONResponse({
            "topic": topic,
            "mindmap_nodes": final_nodes, # Trả về nodes dạng cây không tọa độ
            "detail": detail_list, 
            "summary": summary_list[:4]
        })

    except Exception as e:
        logging.exception("Lỗi Server Mindmap:")
        return JSONResponse({"error": f"Lỗi xử lý Mindmap: {str(e)}"}, status_code=500)

# ----------------- RUN -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Server:app", host="127.0.0.1", port=8000, reload=True)