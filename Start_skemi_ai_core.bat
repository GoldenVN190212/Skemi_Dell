@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo Starting Skemi AI core
echo ========================================
echo Root: %cd%
echo Core API: http://127.0.0.1:8011
echo Press Ctrl+C to stop.
echo.

python ChatBackend.py

endlocal
