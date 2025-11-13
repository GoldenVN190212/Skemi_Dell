import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ollama import chat

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

# ----------------- HTML chính -----------------
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Chatbot.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Chatbot.html không tồn tại"}, status_code=404)

# ----------------- Session -----------------
sessions = {}
SESSION_TIMEOUT = timedelta(minutes=120)

class Question(BaseModel):
    session_id: str
    question: str

# ----------------- Worker -----------------
queue = asyncio.Queue()

async def worker():
    while True:
        session_id, message, fut = await queue.get()
        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]
            messages.append({"role": "user", "content": message})

            # Lấy 5 messages gần nhất
            recent_messages = messages[-5:]

            # Tóm tắt ngắn gọn bằng phi3:mini
            try:
                summary = await asyncio.to_thread(lambda: chat(
                    model="phi3:mini",
                    messages=[{"role": "system", "content": "Tóm tắt ngắn gọn yêu cầu của user."}] + recent_messages
                ))
                if isinstance(summary, dict):
                    summary_text = summary.get("message", {}).get("content", "")
                elif hasattr(summary, "message"):
                    summary_text = getattr(summary.message, "content", "")
                else:
                    summary_text = str(summary)
                if not summary_text:
                    summary_text = "Yêu cầu không tóm tắt được."
            except Exception as e:
                print("🛑 Lỗi tóm tắt:", e)
                summary_text = "Yêu cầu không tóm tắt được."

            # Gọi Mistral trả về toàn bộ luôn
            try:
                ai_response = chat(
                    model="mistral:instruct",
                    messages=[{"role": "system", "content": "Bạn là chatbot thân thiện, trả lời chi tiết bằng tiếng Việt dựa trên tóm tắt."},
                              {"role": "user", "content": summary_text}] + recent_messages
                )
                if isinstance(ai_response, dict):
                    collected = ai_response.get("message", {}).get("content", "")
                elif hasattr(ai_response, "message"):
                    collected = getattr(ai_response.message, "content", "")
                else:
                    collected = str(ai_response)
            except Exception as e:
                collected = f"[Lỗi AI: {e}]"

            # Cập nhật session
            messages.append({"role": "assistant", "content": collected})
            sessions[session_id] = {"messages": messages, "last_active": datetime.utcnow()}

            fut.set_result(collected)

        except Exception as e:
            print("🛑 Lỗi worker:", e)
            fut.set_result(f"Lỗi tổng quát: {e}")
        finally:
            queue.task_done()

# ----------------- Session cleaner -----------------
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
        await asyncio.sleep(60)

# ----------------- Startup -----------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())
    asyncio.create_task(session_cleaner())

# ----------------- API hỏi AI -----------------
@app.post("/ask")
async def ask_ai(data: Question):
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    await queue.put((data.session_id, data.question, fut))
    collected = await fut
    return JSONResponse({"answer": collected})

# ----------------- API xóa session -----------------
@app.post("/end_session")
async def end_session(data: dict):
    session_id = data.get("session_id")
    if session_id in sessions:
        del sessions[session_id]
        print(f"🗑️ Session {session_id} xóa do user out")
    return {"message": "Session đã xóa"}
