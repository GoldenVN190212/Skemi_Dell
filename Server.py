# Server.py
import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ollama import chat  # Gemma 3:1b

app = FastAPI()

# Cho phép frontend fetch từ các nguồn khác (port 5500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Folder lưu file upload
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount CSS và JS
if os.path.exists("Css"):
    app.mount("/Css", StaticFiles(directory="Css"), name="Css")
if os.path.exists("Js"):
    app.mount("/Js", StaticFiles(directory="Js"), name="Js")

# Serve HTML chính
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Chatbot.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Chatbot.html không tồn tại"}, status_code=404)

# ----- Queue xử lý AI -----
queue = asyncio.Queue()

# ----- Lưu chat tạm thời (RAM) theo session -----
# sessions: { session_id: {"messages": [...], "last_active": datetime } }
sessions = {}

SESSION_TIMEOUT = timedelta(minutes=120)  # 120 phút không hoạt động → xóa

class Question(BaseModel):
    session_id: str
    question: str

# Worker chạy liên tục
async def worker():
    while True:
        session_id, message, fut = await queue.get()
        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]
            messages.append({"role": "user", "content": message})
            
            response = chat(
                model="gemma3:1b",
                messages=[{"role": "system", "content": "Bạn là chatbot thân thiện, trả lời ngắn gọn."}] + messages
            )

            # Debug phản hồi thô
            print("🧠 Raw response:", response)

            # Xử lý phản hồi mới của Ollama
            answer = ""
            if isinstance(response, dict):
                if "message" in response and "content" in response["message"]:
                    answer = response["message"]["content"]
                elif "messages" in response and isinstance(response["messages"], list):
                    answer = response["messages"][-1].get("content", "")
            elif hasattr(response, "message"):
                answer = getattr(response.message, "content", "")
            elif hasattr(response, "text"):
                answer = response.text

            if not answer:
                answer = "Gemma không trả lời được."

            messages.append({"role": "assistant", "content": answer})

            # Cập nhật session
            sessions[session_id] = {"messages": messages, "last_active": datetime.utcnow()}

            fut.set_result(answer)
        except Exception as e:
            fut.set_result(f"Lỗi khi gọi model: {e}")
        finally:
            queue.task_done()

# Task tự động xóa session timeout
async def session_cleaner():
    while True:
        now = datetime.utcnow()
        to_delete = []
        for session_id, data in sessions.items():
            if now - data["last_active"] > SESSION_TIMEOUT:
                to_delete.append(session_id)
        for session_id in to_delete:
            print(f"🗑️ Xóa session {session_id} do timeout")
            del sessions[session_id]
        await asyncio.sleep(60)  # check mỗi 1 phút

# Start worker & cleaner khi server khởi động
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())
    asyncio.create_task(session_cleaner())

# API chat
@app.post("/ask")
async def ask_ai(data: Question):
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    await queue.put((data.session_id, data.question, fut))
    answer = await fut
    return {"answer": answer}

# API xóa session khi người dùng out
@app.post("/end_session")
async def end_session(data: dict):
    session_id = data.get("session_id")
    if session_id in sessions:
        del sessions[session_id]
        print(f"🗑️ Session {session_id} xóa do user out")
    return {"message": "Session đã xóa"}

# API upload file
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {"message": f"Upload thành công: {file.filename}"}
    except Exception as e:
        return {"message": f"Upload thất bại: {e}"}
