# Server.py
import os
import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langdetect import detect

# ----------------- MODULES -----------------
from Train.model_gemma_pro_chat import call_gemma_pro_chat
from Train.model_gemma_small_chat import call_gemma__small_chat
from Train.model_llava import call_mindmap_generation 

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

# Ensure tmp_files exists (some endpoints might still use it)
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

    messages = [{"role": "system", "content": system_prompt}] + messages

    logging.info(f"[{data.session_id}] Ngôn ngữ: {language} | Model: {model_tier}")

    if model_tier == "small":
        model_response = await asyncio.to_thread(call_gemma__small_chat, messages)
        model_used = "gemmaSmall"
    else:
        model_response = await asyncio.to_thread(call_gemma_pro_chat, messages)
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

# ----------------- MINDMAP -----------------
@app.post("/generate_mindmap")
async def generate_mindmap(file: UploadFile = File(...)):
    try:
        # Read bytes directly from UploadFile (no temp file)
        file_bytes = await file.read()

        # Call LLaVA model - we expect [topic, nodes]
        result = await asyncio.to_thread(call_mindmap_generation, file_bytes)

        if not isinstance(result, list) or len(result) != 2:
            raise Exception(f"Vision Model trả về định dạng không hợp lệ: {result}")

        topic, final_nodes = result

        # If model returned an error-like topic
        if isinstance(topic, str) and topic.startswith("Lỗi"):
            return JSONResponse({
                "topic": topic,
                "detail": ["Không thể phân tích hình ảnh. Vui lòng thử ảnh rõ hơn."],
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

        # Extract text for detail/summary
        def extract_all_text(node):
            items = [node.get("text", "")]
            for child in node.get("children", []):
                items.extend(extract_all_text(child))
            return items

        detail_list = []
        summary_list = []
        for node in final_nodes:
            detail_list.extend(extract_all_text(node))
            summary_list.append(node.get("text", ""))

        return JSONResponse({
            "topic": topic,
            "mindmap_nodes": final_nodes,
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
