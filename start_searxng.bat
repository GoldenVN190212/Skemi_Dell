@echo off
REM ============================================================
REM  Skemi — start a local SearXNG (free, private web-search) so
REM  Deep Research gets REAL fresh results. Needs Docker Desktop.
REM ============================================================
echo [Skemi] Starting local SearXNG on http://127.0.0.1:8888 ...

REM Remove any previous container so this is idempotent.
docker rm -f skemi-searxng >nul 2>&1

docker run -d ^
  --name skemi-searxng ^
  --restart unless-stopped ^
  -p 8888:8080 ^
  -v "%~dp0Skemi_SearXNG:/etc/searxng" ^
  searxng/searxng:latest

if %errorlevel% neq 0 (
  echo.
  echo [Skemi] Could not start SearXNG. Is Docker Desktop running?
  echo         Open Docker Desktop, wait until it says "Engine running", then run this again.
  pause
  exit /b 1
)

echo.
echo [Skemi] SearXNG container started. Give it ~10-15 seconds to boot.
echo [Skemi] Test it:  http://127.0.0.1:8888/search?q=test^&format=json
echo [Skemi] Then (re)start Skemi:  python Server.py
echo.
pause
