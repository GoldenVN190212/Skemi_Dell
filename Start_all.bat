@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo   SKEMI — full stack launcher
echo ================================================================
echo   Main app (FastAPI)      : http://localhost:8010
echo   Arena (gamification)    : http://localhost:5000   (section: Arena)
echo   Skemi CLI (workspace)   : http://localhost:3000   (section: Skemi CLI)
echo ----------------------------------------------------------------
echo   Optional services (start separately if you need them):
echo     - Ollama LLM        : Start_skemi_ai_core.bat  (AI chat/agent)
echo     - SearXNG meta-search: Start_search_stack.bat   (best search quality)
echo ================================================================

REM --- Embedded feature services (own windows) ---
start "Skemi Arena (:5000)"   cmd /c "cd /d ""D:\gamification\backend"" && node server.js"
start "Skemi CLI Web (:3000)" cmd /c "cd /d ""D:\Skemi CLI Web"" && node server.js"

REM --- Main app (this window) ---
start "" http://localhost:8010/
python -m uvicorn Server:app --host 127.0.0.1 --port 8010 --reload

echo.
echo Main server stopped. Close the Arena/CLI windows to stop those too.
pause
endlocal
