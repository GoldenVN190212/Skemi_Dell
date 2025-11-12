# Server.py
import os
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

# Lớp dữ liệu câu hỏi
class Question(BaseModel):
    question: str

# API trả lời câu hỏi
@app.post("/ask")
async def ask_ai(data: Question):
    try:
        response = chat(
            model="gemma3:1b",
            messages=[
                {"role": "system", "content": "Bạn là một chatbot thân thiện, trả lời ngắn gọn."},
                {"role": "user", "content": data.question}
            ]
        )
        answer = getattr(response, "text", None) or "Gemma không trả lời được."
        return JSONResponse(content={"answer": answer})
    except Exception as e:
        return JSONResponse(content={"answer": f"Lỗi khi gọi model: {e}"})

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
