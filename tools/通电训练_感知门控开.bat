@echo off
rem D-027: real training is accepted. Open the studio; user still clicks Start.
rem ASCII only. The exe reads current external source. Explicit gate OFF remains
rem available by launching the exe with EGO_GATE_PERCEPTION=0.
setlocal
set "EGO_GATE_PERCEPTION=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=C:\Users\22082\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -c "import os,sys,subprocess; r=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])),os.pardir)); os.environ['EGO_ROOT']=r; e=os.path.join(r,'\u542f\u52a8\u8bad\u7ec3\u53f0.exe'); subprocess.Popen([e],cwd=r) if os.path.exists(e) else subprocess.Popen([sys.executable,os.path.join(r,'engine','training_studio.py')],cwd=r)" "%~f0"
exit /b 0
