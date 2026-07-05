@echo off
setlocal
echo ========================================
echo  Starting Skemi embedded feature services
echo ========================================
echo  Arena (gamification) : http://localhost:5000
echo  Skemi CLI (workspace): http://localhost:3000
echo ----------------------------------------
echo  These power the "Arena" and "Skemi CLI" sections
echo  inside the main app at http://localhost:8010
echo ========================================

REM --- Arena / gamification (Express on :5000) ---
start "Skemi Arena (:5000)" cmd /c "cd /d ""D:\gamification\backend"" && node server.js"

REM --- Skemi CLI Web workspace (Express + socket.io on :3000) ---
start "Skemi CLI Web (:3000)" cmd /c "cd /d ""D:\Skemi CLI Web"" && node server.js"

echo.
echo Both feature services launching in their own windows.
echo Close those windows to stop them.
echo.
endlocal
