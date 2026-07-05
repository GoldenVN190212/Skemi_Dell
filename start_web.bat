@echo off
echo ========================================
echo    Starting Skemi Web Server
echo ========================================
echo.
echo Opening http://localhost:8080 in browser...
echo Press Ctrl+C to stop the server.
echo.
start http://localhost:8080/index.html
python -m http.server 8080
pause
