@echo off
REM Chuyển vào thư mục dự án
cd /d D:\Skemi

REM Thông báo
echo 🔥 Khởi động server FastAPI (Gemma3:1b)...
echo Nhấn Ctrl+C để tắt server bất cứ lúc nào.

REM Chạy server uvicorn
python -m uvicorn Server:app --host 127.0.0.1 --port 8000

REM Khi server dừng
echo Server đã dừng. Nhấn bất kỳ phím nào để thoát...
pause
