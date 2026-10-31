@echo off
chcp 65001 >nul
title training dashboard
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONDONTWRITEBYTECODE=1

set "PY=C:\Users\22082\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo   ============================================================
echo    Training dashboard is starting.
echo    A browser window will open at http://127.0.0.1:8791
echo    Keep this window open. Press Ctrl+C to stop.
echo   ============================================================
echo.

start "" http://127.0.0.1:8791
"%PY%" engine\dashboard.py --port 8791
if errorlevel 9009 (
  echo.
  echo   [ERROR] python not found. Install Python 3.12 and check "Add to PATH".
  echo.
  pause
)
