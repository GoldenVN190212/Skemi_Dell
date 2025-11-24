import os
import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any, List

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langdetect import detect

# ----------------- MODULES -----------------
try:
    # Các hàm giả định cho mục đích demo/hoàn chỉnh code
    def call_gemma_pro_chat(messages):
        logging.info("Calling mock gemma pro...")
        last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), "Hello!")
        return f"Tôi là Gemma Pro, trả lời câu hỏi phức tạp của bạn: {last_user_message}"

    def call_gemma__small_chat(messages):
        logging.info("Calling mock gemma small...")
        last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), "Hello!")
        return f"Tôi là Gemma Small, trả lời câu hỏi đơn giản của bạn: {last_user_message}"

    # Import logic Mindmap từ file đã cung cấp
    # Đảm bảo thư mục Train/ có module model_llama3.py
    from Train.model_llama3 import call_mindmap_generation
except ImportError as e:
    logging.error(f"Error importing AI modules: {e}. Using local mocks.")
    def call_gemma_pro_chat(messages):
        return "Mock Pro response."
    def call_gemma__small_chat(messages):
        return "Mock Small response."
    def call_mindmap_generation(input_data: Any) -> List[Any]:
        return ["Mock Topic", [{"text": "Mock Node", "children": [], "x": 500, "y": 200}]]


# ----------------- APP INIT -----------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cấu hình Static Files
if os.path.exists("Css"):
    app.mount("/Css", StaticFiles(directory="Css"), name="Css")
if os.path.exists("Js"):
    app.mount("/Js", StaticFiles(directory="Js"), name="Js")

# Đảm bảo tmp_files tồn tại
os.makedirs("tmp_files", exist_ok=True)

# ----------------- HELPERS -----------------
def extract_reply_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "message", {}).get("content") or getattr(response, "content", None) or str(response)

def detect_language(text: str) -> str:
    try:
        return detect(text)
    except:
        return "vi"

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
    now = datetime.utcnow()
    session = sessions.get(data.session_id)

    if not session or now - session["created_at"] > SESSION_TIMEOUT:
        session = {"messages": [], "created_at": now}

    messages = session["messages"]
    messages.append({"role": "user", "content": data.question})

    model_tier = assess_complexity(data.question)
    language = detect_language(data.question)

    system_prompt = {
        "vi": "Bạn là trợ lý AI trả lời bằng tiếng Việt.",
        "en": "You are an AI assistant that replies in English."
    }.get(language, "You are an AI assistant.")

    # Lấy 5 tin nhắn gần nhất + system prompt để giữ context
    messages_with_system = [{"role": "system", "content": system_prompt}] + messages[-5:]

    logging.info(f"[{data.session_id}] Ngôn ngữ: {language} | Model: {model_tier}")

    if model_tier == "small":
        model_response = await asyncio.to_thread(call_gemma__small_chat, messages_with_system)
        model_used = "gemmaSmall"
    else:
        model_response = await asyncio.to_thread(call_gemma_pro_chat, messages_with_system)
        model_used = "gemmaPro"

    reply_text = extract_reply_content(model_response)
    
    # Chỉ lưu tin nhắn mới vào session
    messages.append({"role": "assistant", "content": reply_text})
    sessions[data.session_id] = {"messages": messages, "created_at": now}

    return JSONResponse({"model": model_used, "answer": reply_text})

@app.post("/end_session")
async def end_session(data: dict):
    sid = data.get("session_id")
    if sid in sessions:
        del sessions[sid]
    return {"message": "Session đã được xóa"}

# ----------------- MINDMAP -----------------
@app.post("/generate_mindmap")
async def generate_mindmap(file: UploadFile = File(...)):
    try:
        # Read bytes directly from UploadFile
        file_bytes = await file.read()
        file_name = file.filename # Lấy tên file để xử lý sau này (nếu cần file type)

        # Call LLaVA model - we expect [topic, nodes]
        # (Giả định call_mindmap_generation chưa dùng file_name, nếu cần dùng, phải sửa)
        result = await asyncio.to_thread(call_mindmap_generation, file_bytes) 

        if not isinstance(result, list) or len(result) != 2:
            raise Exception(f"Vision Model trả về định dạng không hợp lệ: {result}")

        topic, final_nodes = result

        # Handle Model Error/Fallback
        if isinstance(topic, str) and topic.startswith(("Lỗi", "Error")):
             return JSONResponse({
                 "topic": topic,
                 "detail": ["Không thể phân tích hình ảnh/tài liệu. Vui lòng thử lại."],
                 "summary": [],
                 "mindmap_nodes": []
             })

        # If no nodes returned
        if not final_nodes:
            return JSONResponse({
                "topic": topic if topic else "Không xác định",
                "detail": ["Không đủ nội dung để tạo mindmap."],
                "summary": [],
                "mindmap_nodes": []
            })

        # Extract text for detail/summary (Recurse to get all text)
        def extract_all_text(node):
            # Lấy text của node hiện tại
            items = [node.get("text", "")]
            # Lấy text của các node con
            for child in node.get("children", []):
                items.extend(extract_all_text(child))
            return [i for i in items if i.strip()] # Filter empty strings

        detail_list = []
        summary_list = []
        for node in final_nodes:
            detail_list.extend(extract_all_text(node))
            summary_list.append(node.get("text", "")) # Chỉ lấy text cấp 1 cho summary

        return JSONResponse({
            "topic": topic,
            "mindmap_nodes": final_nodes, # Nodes đã có tọa độ
            "detail": detail_list, # Toàn bộ text
            "summary": summary_list[:4] # 4 ý chính đầu tiên
        })

    except Exception as e:
        logging.exception("Lỗi Server Mindmap:")
        return JSONResponse({"error": f"Lỗi xử lý Mindmap: {str(e)}"}, status_code=500)

# ----------------- RUN -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Server:app", host="127.0.0.1", port=8000, reload=True)