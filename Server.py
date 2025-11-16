import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ollama import chat  # bạn phải có package ollama

app = FastAPI()

# ----------------- CORS -----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Static Files -----------------
if os.path.exists("Css"):
    app.mount("/Css", StaticFiles(directory="Css"), name="Css")
if os.path.exists("Js"):
    app.mount("/Js", StaticFiles(directory="Js"), name="Js")

# ----------------- HTML -----------------
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Chatbot.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Chatbot.html không tồn tại"}, status_code=404)

# ----------------- Session -----------------
sessions = {}
SESSION_TIMEOUT = timedelta(minutes=120)
MAX_MESSAGES = 50
RECENT_MESSAGES = 10

class Question(BaseModel):
    session_id: str
    question: str

# ----------------- Queue -----------------
queue = asyncio.Queue()

# ----------------- Model -----------------
GEMMA_MODEL = "gemma3:1b"
GEMMA_TIMEOUT = 5.0  # giây

# ----------------- Helper -----------------
async def call_gemma(messages):
    def blocking_call():
        return chat(model=GEMMA_MODEL, messages=messages)
    resp = await asyncio.to_thread(blocking_call)
    if isinstance(resp, dict):
        return resp.get("message", {}).get("content", "") or str(resp)
    elif hasattr(resp, "message"):
        return getattr(resp.message, "content", "")
    else:
        return str(resp)

# ----------------- Worker -----------------
async def worker():
    while True:
        session_id, message, fut = await queue.get()
        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]

            messages.append({"role": "user", "content": message})
            if len(messages) > MAX_MESSAGES:
                messages = messages[-MAX_MESSAGES:]

            recent_messages = messages[-RECENT_MESSAGES:]
            system_base = {"role": "system", "content": "Bạn là chatbot thân thiện, trả lời bằng tiếng Việt."}
            gemma_messages = [system_base] + recent_messages

            try:
                collected = await asyncio.wait_for(call_gemma(gemma_messages), timeout=GEMMA_TIMEOUT)
            except:
                collected = "[Lỗi: không thể kết nối tới Gemma hoặc timeout]"

            messages.append({"role": "assistant", "content": collected})
            if len(messages) > MAX_MESSAGES:
                messages = messages[-MAX_MESSAGES:]
            sessions[session_id] = {"messages": messages, "last_active": datetime.utcnow()}

            fut.set_result(collected)
        except Exception as e:
            fut.set_result(f"Lỗi worker: {e}")
        finally:
            queue.task_done()

# ----------------- Session cleaner -----------------
async def session_cleaner():
    while True:
        now = datetime.utcnow()
        to_delete = [sid for sid, data in sessions.items() if now - data["last_active"] > SESSION_TIMEOUT]
        for sid in to_delete:
            del sessions[sid]
        await asyncio.sleep(60)

# ----------------- Startup -----------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())
    asyncio.create_task(session_cleaner())

# ----------------- API -----------------
@app.post("/ask")
async def ask_ai(data: Question):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    await queue.put((data.session_id, data.question, fut))
    collected = await fut
    return JSONResponse({"answer": collected})

@app.post("/end_session")
async def end_session(data: dict):
    sid = data.get("session_id")
    if sid in sessions:
        del sessions[sid]
    return {"message": "Session đã xóa"}
