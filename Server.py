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
MAX_MESSAGES_PER_SESSION = 50
RECENT_MESSAGES_TO_SEND = 10

class Question(BaseModel):
    session_id: str
    question: str

# ----------------- Queue & Worker -----------------
queue = asyncio.Queue()

# ========== MODEL CONFIG ==========
GEMMA_MODEL = "gemma3:1b"
LLAMA_MODEL = "llama3.2:11b"
GEMMA_TIMEOUT = 3.0
LLAMA_TIMEOUT = 12.0
OVERALL_TIMEOUT = 15.0
PREWARM_MODELS = True

# helper gọi model blocking trong thread
async def call_model_threadsafe(model_name: str, messages, max_tokens=512, temperature=0.2):
    def blocking_call():
        return chat(model=model_name, messages=messages, max_tokens=max_tokens, temperature=temperature)
    try:
        resp = await asyncio.to_thread(blocking_call)
        if isinstance(resp, dict):
            return resp.get("message", {}).get("content", "") or str(resp)
        elif hasattr(resp, "message"):
            return getattr(resp.message, "content", "")
        else:
            return str(resp)
    except Exception as e:
        raise

async def call_model_with_timeout(model_name: str, messages, max_tokens=512, temperature=0.2, timeout=None):
    try:
        if timeout:
            return await asyncio.wait_for(
                call_model_threadsafe(model_name, messages, max_tokens, temperature),
                timeout=timeout
            )
        else:
            return await call_model_threadsafe(model_name, messages, max_tokens, temperature)
    except asyncio.TimeoutError:
        raise
    except Exception as e:
        raise

# ----------------- Worker -----------------
async def worker():
    while True:
        session_id, message, fut = await queue.get()
        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]
            messages.append({"role": "user", "content": message})
            if len(messages) > MAX_MESSAGES_PER_SESSION:
                messages = messages[-MAX_MESSAGES_PER_SESSION:]
            recent_messages = messages[-RECENT_MESSAGES_TO_SEND:]

            # 1) Tóm tắt nhanh bằng Gemma
            summary_text = None
            try:
                summary_prompt = [{"role": "system", "content": "Tóm tắt ngắn gọn yêu cầu user bằng tiếng Việt, 1-2 câu."}]
                summary_prompt += recent_messages
                summary_text = await call_model_with_timeout(
                    GEMMA_MODEL, summary_prompt, max_tokens=128, temperature=0.0, timeout=GEMMA_TIMEOUT
                )
                summary_text = summary_text.strip() or recent_messages[-1]["content"]
            except Exception:
                summary_text = recent_messages[-1]["content"] if recent_messages else message

            # 2) Chuẩn bị message cho LLaMA & Gemma
            system_base = {"role": "system", "content": "Bạn là chatbot thân thiện, trả lời chi tiết bằng tiếng Việt."}
            llama_user = {"role": "user", "content": f"Tóm tắt: {summary_text}\n\nBối cảnh gần đây:\n" +
                                                 "\n".join([f"{m['role']}: {m['content']}" for m in recent_messages])}
            llama_messages = [system_base, llama_user]
            gemma_messages = [system_base, {"role": "user", "content": summary_text}] + recent_messages

            # 3) Gọi song song
            gemma_task = asyncio.create_task(call_model_with_timeout(
                GEMMA_MODEL, gemma_messages, max_tokens=300, temperature=0.0, timeout=GEMMA_TIMEOUT
            ))
            llama_task = asyncio.create_task(call_model_with_timeout(
                LLAMA_MODEL, llama_messages, max_tokens=512, temperature=0.1, timeout=LLAMA_TIMEOUT
            ))

            gemma_result = None
            llama_result = None

            try:
                gemma_result = await asyncio.wait_for(gemma_task, timeout=GEMMA_TIMEOUT)
            except: gemma_result = None

            try:
                remaining = max(0.0, OVERALL_TIMEOUT - GEMMA_TIMEOUT)
                llama_result = await asyncio.wait_for(llama_task, timeout=remaining)
            except: llama_result = None

            # 4) Quyết định kết quả trả về
            if llama_result:
                collected = llama_result
            elif gemma_result:
                collected = gemma_result
            else:
                collected = "[Lỗi: không thể kết nối tới mô hình AI hoặc đã timeout]"

            # 5) Cập nhật session
            messages.append({"role": "assistant", "content": collected})
            if len(messages) > MAX_MESSAGES_PER_SESSION:
                messages = messages[-MAX_MESSAGES_PER_SESSION:]
            sessions[session_id] = {"messages": messages, "last_active": datetime.utcnow()}

            fut.set_result(collected)

        except Exception as e:
            print("🛑 Lỗi worker:", e)
            try: fut.set_result(f"Lỗi tổng quát: {e}")
            except: pass
        finally:
            queue.task_done()

# ----------------- Session cleaner -----------------
async def session_cleaner():
    while True:
        now = datetime.utcnow()
        to_delete = [sid for sid, data in sessions.items() if now - data["last_active"] > SESSION_TIMEOUT]
        for sid in to_delete:
            print(f"🗑️ Xóa session {sid} do timeout")
            del sessions[sid]
        await asyncio.sleep(60)

# ----------------- Startup -----------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())
    asyncio.create_task(session_cleaner())

    if PREWARM_MODELS:
        async def prewarm():
            try:
                print("⚡ Prewarming models...")
                await call_model_with_timeout(GEMMA_MODEL, [{"role":"system","content":"Prewarm"}], max_tokens=16, temperature=0.0, timeout=5.0)
                await call_model_with_timeout(LLAMA_MODEL, [{"role":"system","content":"Prewarm"}], max_tokens=16, temperature=0.0, timeout=10.0)
                print("⚡ Prewarm done")
            except Exception as e:
                print("⚠️ Prewarm error:", e)
        asyncio.create_task(prewarm())

# ----------------- API hỏi AI -----------------
@app.post("/ask")
async def ask_ai(data: Question):
    loop = asyncio.get_running_loop()
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
