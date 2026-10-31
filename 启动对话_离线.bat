@echo off
chcp 65001 >nul
title self-development dialogue
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONDONTWRITEBYTECODE=1

set "PY=C:\Users\22082\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" launcher.py --offline %*
if errorlevel 9009 (
  echo.
  echo   [ERROR] python not found.
  echo.
  pause
)