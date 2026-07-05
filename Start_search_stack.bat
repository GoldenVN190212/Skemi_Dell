@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo Starting Skemi self-hosted search stack
echo ========================================
echo Root: %cd%
echo SearXNG: http://127.0.0.1:8888
echo HAProxy:  http://127.0.0.1:8119
echo.

docker compose up -d
if errorlevel 1 (
  echo Failed to start the search stack.
  pause
  exit /b 1
)

echo.
docker compose ps
echo.
echo Search stack started.
pause

endlocal
