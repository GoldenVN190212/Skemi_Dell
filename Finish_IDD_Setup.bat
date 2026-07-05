@echo off
REM ==========================================================================
REM  Skemi — one-click finisher for the virtual display (IDD).
REM  Double-click this file. It will:
REM    1) ask for admin ONCE (the UAC prompt — click Yes),
REM    2) remove ALL leftover/duplicate USB virtual-display adapters,
REM    3) install ONE clean virtual display and turn it on,
REM    4) run the self-test (--idd) to confirm hidden-app capture works.
REM  Safe + reversible: the Skemi "Gỡ màn hình ảo" button undoes step 2-3.
REM ==========================================================================
setlocal
cd /d "%~dp0"

REM --- self-elevate (one UAC) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights ^(approve the UAC prompt^)...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "IDD=%~dp0Skemi_Virtual_Display\usbmmidd_v2"
if not exist "%IDD%\deviceinstaller64.exe" (
    echo [ERROR] Khong tim thay driver tai: %IDD%
    pause & exit /b 1
)
cd /d "%IDD%"

echo.
echo [1/3] Don sach cac adapter man hinh ao trung lap...
deviceinstaller64.exe enableidd 0
for /L %%i in (1,1,24) do deviceinstaller64.exe stop usbmmidd  >nul 2>&1
for /L %%i in (1,1,24) do deviceinstaller64.exe remove usbmmidd >nul 2>&1

echo [2/3] Cai 1 man hinh ao sach + bat len...
deviceinstaller64.exe install usbmmIdd.inf usbmmidd
if %errorlevel% neq 0 (
    echo [ERROR] Cai driver that bai ^(ma loi %errorlevel%^). Co the can bat
    echo         test-signing hoac driver bi chan. Chua bat duoc man hinh ao.
    pause & exit /b 1
)
deviceinstaller64.exe enableidd 1

echo [3/3] Kiem tra (capture app an tren man hinh ao that)...
echo        Cho Windows nhan dien man hinh ao moi (~5s)...
timeout /t 5 /nobreak >nul
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel%==0 (
    python skemi_selftest.py --idd
) else (
    echo [INFO] Khong tim thay python tren PATH. Mo Skemi va chay:
    echo        python skemi_selftest.py --idd
)

echo.
echo ==== Xong. Neu thay "RESULT: ... 0 failed" la man hinh ao da hoat dong. ====
pause
endlocal
