@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo Starting Skemi canonical server
echo ========================================
echo Root: %cd%
echo Frontend + API: http://localhost:8010
echo (Mo bang localhost de dang nhap Google/Facebook hoat dong — Firebase chi
echo  cho phep "localhost", khong cho phep "127.0.0.1".)
echo Press Ctrl+C to stop.
echo.
start http://localhost:8010/

python -m uvicorn Server:app --host 127.0.0.1 --port 8010 --reload

echo.
echo Server stopped.
pause

endlocal
