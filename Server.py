# Server.py
import os
import asyncio
import tempfile
import json
import logging
from datetime import datetime, timedelta
from typing import Tuple, List, Any

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ----------------- MODEL WRAPPERS -----------------
from Train.model_gemma_small_chat import call_gemma__small_chat
from Train.model_gemma_pro_chat import call_gemma_pro_chat  
from Train.model_gemma_image import call_gemma_image
from Train.model_granite import call_granite_block

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

# ----------------- HOMEPAGE -----------------
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Home.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Home.html không tồn tại"}, status_code=404)

# ----------------- CHATBOT / SESSION -----------------
sessions = {}
SESSION_TIMEOUT = timedelta(minutes=120)
MAX_MESSAGES = 50
RECENT_MESSAGES = 10

class Question(BaseModel):
    session_id: str
    question: str

queue = asyncio.Queue()

def choose_chat_model(question: str):
    q = question.lower()
    complex_keywords = [
        "fix", "error", "bug", "code",
        "tối ưu", "phân tích", "so sánh",
        "tại sao", "vì sao", "giải thích",
        "firebase", "database", "server"
    ]
    if len(question) > 120 or any(k in q for k in complex_keywords):
        return "gemma3:4bPro"
    return "gemma1b"


async def call_chatbot(messages, model_name):
    """
    Gọi model và trả về kết quả CHỈ TEXT (không gắn tag model)
    """
    system_msg = {"role": "system", "content": "Bạn là chatbot. Trả lời cùng ngôn ngữ với câu hỏi người dùng."}
    full_messages = [system_msg] + messages

    def blocking_call():
        try:
            if model_name == "gemma1b":
                return call_gemma__small_chat(full_messages)
            else:
                return call_gemma_pro_chat(full_messages)
        except Exception as e:
            logging.exception("Error inside blocking_call")
            return f"[Lỗi model: {e}]"

    resp = await asyncio.to_thread(blocking_call)

    # Chuẩn hóa text
    if isinstance(resp, dict):
        content = resp.get("message", {}).get("content") or resp.get("content") or str(resp)
    elif hasattr(resp, "message"):
        content = resp.message.content
    else:
        content = str(resp)

    # XÓA model tag nếu model tự chèn
    content = content.replace(f"({model_name})", "").strip()

    # Không thêm tag model nữa
    return content


async def worker():
    while True:
        session_id, new_message, fut = await queue.get()
        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]

            messages.append({"role": "user", "content": new_message})
            messages = messages[-MAX_MESSAGES:]

            selected_model = choose_chat_model(new_message)

            try:
                reply_text = await call_chatbot(messages[-RECENT_MESSAGES:], selected_model)
            except Exception as e:
                logging.exception("Error calling chatbot model:")
                reply_text = "[Lỗi gọi model]"

            # Append lại vào session
            messages.append({"role": "assistant", "content": reply_text})
            messages = messages[-MAX_MESSAGES:]

            sessions[session_id] = {
                "messages": messages,
                "last_active": datetime.utcnow()
            }

            fut.set_result({"model": selected_model, "answer": reply_text})

        except Exception as e:
            fut.set_result({"model": "error", "answer": str(e)})
        finally:
            queue.task_done()


async def session_cleaner():
    while True:
        now = datetime.utcnow()
        expired = [sid for sid, data in sessions.items() if now - data["last_active"] > SESSION_TIMEOUT]
        for sid in expired:
            del sessions[sid]
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())
    asyncio.create_task(session_cleaner())


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


# ----------------- HELPERS MINDMAP -----------------
def _parse_gemma3_response(resp: Any) -> Tuple[str, List[str], List[str]]:
    topic = "Chưa xác định"
    detail = []
    summary = []

    try:
        if resp is None:
            return topic, detail, summary

        if isinstance(resp, (list, tuple)) and len(resp) >= 1:
            if len(resp) == 3:
                topic, detail, summary = resp
                return topic or "Chưa xác định", detail or [], summary or []

        if isinstance(resp, dict):
            topic = resp.get("topic", topic)
            detail = resp.get("detail", resp.get("subtopics_detail", [])) or []
            summary = resp.get("summary", resp.get("subtopics_summary", [])) or []
            return topic, detail, summary

        if isinstance(resp, str):
            try:
                j = json.loads(resp)
                return _parse_gemma3_response(j)
            except:
                lines = [l.strip() for l in resp.splitlines() if l.strip()]
                if lines:
                    topic = lines[0]
                    subs = [ln.lstrip("-• ").strip() for ln in lines[1:] if ln]
                    mid = max(1, len(subs)//2)
                    detail = subs
                    summary = subs[:max(1, len(subs)//3)]
                    return topic, detail, summary
    except Exception:
        logging.exception("Error parsing gemma3 response")

    return topic, detail, summary


# ----------------- MINDMAP ENDPOINT -----------------
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

        gemma_resp = await asyncio.to_thread(call_gemma_image, tmp_path)
        topic, subtopics_detail, subtopics_summary = _parse_gemma3_response(gemma_resp)

        if not isinstance(subtopics_detail, list):
            subtopics_detail = list(subtopics_detail) if subtopics_detail else []
        if not isinstance(subtopics_summary, list):
            subtopics_summary = list(subtopics_summary) if subtopics_summary else []

        granite_detail_task = asyncio.to_thread(call_granite_block, subtopics_detail)
        granite_summary_task = asyncio.to_thread(call_granite_block, subtopics_summary)

        granite_detail_res, granite_summary_res = await asyncio.gather(
            granite_detail_task, granite_summary_task
        )

        resp = {
            "topic": topic,
            "detail": subtopics_detail,
            "summary": subtopics_summary,
        }
        if granite_detail_res: resp["granite_detail"] = granite_detail_res
        if granite_summary_res: resp["granite_summary"] = granite_summary_res
        return JSONResponse(resp)

    except Exception as e:
        logging.exception("Error in /generate_mindmap")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ----------------- RUN -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Server:app", host="0.0.0.0", port=8000, reload=True)
