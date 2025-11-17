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

# ----------------- MODEL WRAPPERS (bạn phải có các file này) -----------------
# call_gemma_block: legacy gemma
# call_gemma3_block: gemma3:4b wrapper
# call_granite_block: granite wrapper (có thể trả subtopics hoặc base64 image)
from Train.model_gemma import call_gemma_block
from Train.model_gemma3 import call_gemma3_block
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

# Mount static if exists
if os.path.exists("Css"):
    app.mount("/Css", StaticFiles(directory="Css"), name="Css")
if os.path.exists("Js"):
    app.mount("/Js", StaticFiles(directory="Js"), name="Js")

# ----------------- SIMPLE HOMEPAGE -----------------
@app.get("/")
async def index():
    html_path = os.path.join(os.getcwd(), "Home.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Home.html không tồn tại"}, status_code=404)

# ----------------- CHATBOT / SESSION (unchanged) -----------------
sessions = {}
SESSION_TIMEOUT = timedelta(minutes=120)
MAX_MESSAGES = 50
RECENT_MESSAGES = 10

class Question(BaseModel):
    session_id: str
    question: str

queue = asyncio.Queue()

def choose_model(question: str):
    q = question.lower()
    complex_keywords = [
        "fix", "error", "bug", "code",
        "tối ưu", "phân tích", "so sánh",
        "tại sao", "vì sao", "giải thích",
        "firebase", "database", "server"
    ]
    if len(question) > 120 or any(k in q for k in complex_keywords):
        return "llama"
    return "gemma"

async def call_model(messages, model_name):
    def blocking_call():
        if model_name == "gemma":
            return call_gemma_block(messages)
        else:
            return call_gemma3_block(messages)
    resp = await asyncio.to_thread(blocking_call)
    if isinstance(resp, dict):
        # try to be flexible
        return resp.get("message", {}).get("content", "") or resp.get("content") or str(resp)
    elif hasattr(resp, "message"):
        return resp.message.content
    else:
        return str(resp)

async def worker():
    while True:
        session_id, new_message, fut = await queue.get()
        try:
            session = sessions.get(session_id, {"messages": [], "last_active": datetime.utcnow()})
            messages = session["messages"]

            messages.append({"role": "user", "content": new_message})
            messages = messages[-MAX_MESSAGES:]

            system_base = {"role": "system", "content": "Bạn là chatbot trả lời bằng tiếng Việt."}
            context_msgs = [system_base] + messages[-RECENT_MESSAGES:]

            selected = choose_model(new_message)

            try:
                reply = await call_model(context_msgs, selected)
            except Exception as e:
                logging.exception("Error calling model:")
                reply = "[Lỗi gọi model]"

            messages.append({"role": "assistant", "content": reply})
            messages = messages[-MAX_MESSAGES:]

            sessions[session_id] = {"messages": messages, "last_active": datetime.utcnow()}
            fut.set_result({"model": selected, "answer": reply})
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

# ----------------- HELPERS FOR MINDMAP -----------------
def _parse_gemma3_response(resp: Any) -> Tuple[str, List[str], List[str]]:
    """
    Normalize the output from call_gemma3_block into (topic, detail_list, summary_list).
    Supports:
      - returning tuple/list: (topic, detail, summary)
      - returning dict with keys
      - returning JSON string
      - returning single string -> treat as topic only
    """
    topic = "Chủ đề chưa xác định"
    detail = []
    summary = []

    try:
        if resp is None:
            return topic, detail, summary

        # If resp already tuple/list of 3
        if isinstance(resp, (list, tuple)) and len(resp) >= 1:
            if len(resp) == 3:
                topic = resp[0] or topic
                detail = resp[1] or []
                summary = resp[2] or []
                return topic, detail, summary
            # fallback: 1st entry topic, second maybe detail
            if len(resp) == 2:
                topic = resp[0] or topic
                detail = resp[1] or []
                return topic, detail, summary

        # If dict
        if isinstance(resp, dict):
            topic = resp.get("topic", topic)
            detail = resp.get("detail", resp.get("subtopics_detail", resp.get("subtopics", []))) or []
            summary = resp.get("summary", resp.get("subtopics_summary", [])) or []
            return topic, detail, summary

        # If string, try parse JSON inside
        if isinstance(resp, str):
            s = resp.strip()
            # try JSON
            try:
                j = json.loads(s)
                return _parse_gemma3_response(j)
            except Exception:
                # If not JSON, try simple heuristic splitting
                # If response contains lines like "Topic: ...", "Detail: ...", "Summary: ..."
                lines = [l.strip() for l in s.splitlines() if l.strip()]
                if lines:
                    # first non-empty line as topic
                    topic = lines[0]
                    # try find lines starting with '-' or numbers for subtopics
                    subs = [ln.lstrip("-• ").strip() for ln in lines[1:] if ln and len(ln) < 200]
                    if subs:
                        # split subs roughly in half between detail and summary
                        mid = max(1, len(subs)//2)
                        detail = subs
                        summary = subs[:max(1, len(subs)//3)]
                    return topic, detail, summary

    except Exception:
        logging.exception("Error parsing gemma3 response")

    return topic, detail, summary

# ----------------- MINDMAP ENDPOINT (fixed) -----------------
@app.post("/generate_mindmap")
async def generate_mindmap(file: UploadFile = File(...)):
    """
    Endpoint expects multipart/form-data with key 'file'.
    It will:
     - save temp file
     - call_gemma3_block(temp_path) in thread -> return topic, detail, summary
     - call_granite_block for detail and summary in parallel (in threads)
     - return JSON with topic, detail, summary and optionally images if granite returns them
    """
    tmp_path = None
    try:
        # Save uploaded file to a temp file
        suffix = ""
        if file.filename and "." in file.filename:
            suffix = "." + file.filename.split(".")[-1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_path = tmp.name
        contents = await file.read()
        tmp.write(contents)
        tmp.close()
        logging.info("Saved uploaded file to %s", tmp_path)

        # Call gemma3 in a thread
        gemma_resp = await asyncio.to_thread(call_gemma3_block, tmp_path)
        logging.info("Gemma3 raw response: %s", type(gemma_resp))

        # Normalize gemma3 response
        topic, subtopics_detail, subtopics_summary = _parse_gemma3_response(gemma_resp)
        logging.info("Parsed topic=%s, detail_count=%d, summary_count=%d",
                     topic, len(subtopics_detail), len(subtopics_summary))

        # Ensure lists
        if not isinstance(subtopics_detail, list):
            subtopics_detail = list(subtopics_detail) if subtopics_detail else []
        if not isinstance(subtopics_summary, list):
            subtopics_summary = list(subtopics_summary) if subtopics_summary else []

        # Call granite in parallel (each in a thread)
        granite_detail_task = asyncio.to_thread(call_granite_block, subtopics_detail)
        granite_summary_task = asyncio.to_thread(call_granite_block, subtopics_summary)
        granite_detail_res, granite_summary_res = await asyncio.gather(granite_detail_task, granite_summary_task)

        logging.info("Granite results types: %s , %s", type(granite_detail_res), type(granite_summary_res))

        # Build response
        resp = {
            "topic": topic,
            "detail": subtopics_detail,
            "summary": subtopics_summary,
        }

        # If granite returns images or base64, include them
        if granite_detail_res:
            resp["granite_detail"] = granite_detail_res
        if granite_summary_res:
            resp["granite_summary"] = granite_summary_res

        return JSONResponse(resp)

    except Exception as e:
        logging.exception("Error in /generate_mindmap")
        return JSONResponse({"error": str(e)}, status_code=500)

    finally:
        # cleanup temp file
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            logging.exception("Failed to remove temp file")

# -----------------------------------------------------------------------
# If you want to run via 'python Server.py' for quick dev:
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Server:app", host="0.0.0.0", port=8000, reload=True)
