import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ----------------- IMPORT MODEL FILES -----------------
from Train.model_gemma import call_gemma_block
from Train.model_llama import call_llama_block

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


# ----------------- QUEUE -----------------
queue = asyncio.Queue()


# ----------------- ROUTER -----------------
def choose_model(question: str):
    q = question.lower()

    complex_keywords = [
        "fix", "error", "bug", "code",
        "tối ưu", "phân tích", "so sánh",
        "tại sao", "vì sao", "giải thích",
        "firebase", "database", "server"
    ]

    # Dài quá = phức tạp
    if len(question) > 120:
        return "llama"

    # Có keyword = phức tạp
    if any(k in q for k in complex_keywords):
        return "llama"

    # Mặc định dùng Gemma
    return "gemma"


# ----------------- CALL MODEL (ASYNC WRAPPER) -----------------
async def call_model(messages, model_name):
    def blocking_call():
        if model_name == "gemma":
            return call_gemma_block(messages)
        else:
            return call_llama_block(messages)

    resp = await asyncio.to_thread(blocking_call)

    if isinstance(resp, dict):
        return resp.get("message", {}).get("content", "")
    elif hasattr(resp, "message"):
        return resp.message.content
    else:
        return str(resp)


# ----------------- WORKER -----------------
async def worker():
    while True:
        session_id, new_message, fut = await queue.get()

        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]

            # Append user message
            messages.append({"role": "user", "content": new_message})
            messages = messages[-MAX_MESSAGES:]

            # Build context
            system_base = {"role": "system", "content": "Bạn là chatbot trả lời bằng tiếng Việt."}
            context_msgs = [system_base] + messages[-RECENT_MESSAGES:]

            # CHỌN MODEL
            selected = choose_model(new_message)

            # GỌI MODEL
            try:
                reply = await call_model(context_msgs, selected)
            except:
                reply = "[Lỗi gọi model]"

            # Append answer
            messages.append({"role": "assistant", "content": reply})
            messages = messages[-MAX_MESSAGES:]

            # Save session
            sessions[session_id] = {"messages": messages, "last_active": datetime.utcnow()}

            fut.set_result({"model": selected, "answer": reply})

        except Exception as e:
            fut.set_result({"model": "error", "answer": str(e)})

        finally:
            queue.task_done()


# ----------------- SESSION CLEANER -----------------
async def session_cleaner():
    while True:
        now = datetime.utcnow()
        expired = [sid for sid, data in sessions.items()
                   if now - data["last_active"] > SESSION_TIMEOUT]

        for sid in expired:
            del sessions[sid]

        await asyncio.sleep(60)


# ----------------- STARTUP -----------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())
    asyncio.create_task(session_cleaner())


# ----------------- API -----------------
@app.post("/ask")
async def ask_ai(data: Question):
    fut = asyncio.get_running_loop().create_future()
    await queue.put((data.session_id, data.question, fut))
    result = await fut
    return JSONResponse(result)


@app.post("/end_session")
async def end_session(data: dict):
    sid = data.get("session_id")
    if sid in sessions:
        del sessions[sid]
    return {"message": "Session đã xóa"}
