@echo off
rem ============================================================================
rem  T33 - Launch the training studio in the DEFAULT form (perception gate OFF)
rem
rem  This is the control condition for the side-by-side check:
rem      this .bat            ->  gate OFF  ->  read-only panel shows "not started"
rem      通电训练_感知门控开.bat  ->  gate ON   ->  devlevel.json appears, panel shows data
rem
rem  It explicitly CLEARS EGO_GATE_PERCEPTION so that running it right after the
rem  powered one still gives a clean OFF run (a stale variable in the same shell
rem  would otherwise silently keep the gate on).
rem ============================================================================

chcp 65001 >nul
title TRAINING STUDIO - PERCEPTION GATE OFF (default)
cd /d "%~dp0.."

set "EGO_GATE_PERCEPTION="
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo   ============================================================
echo    PERCEPTION GATE : OFF  (default form)
echo   ------------------------------------------------------------
echo    EGO_GATE_PERCEPTION is cleared explicitly.
echo    This is the behaviour the project had before T33.
echo   ============================================================
echo.

if exist "启动训练台.exe" (
    start "" "启动训练台.exe"
) else (
    set "PY=C:\Users\22082\AppData\Local\Programs\Python\Python312\python.exe"
    if not exist "%PY%" set "PY=python"
    "%PY%" engine\training_studio.py
)
