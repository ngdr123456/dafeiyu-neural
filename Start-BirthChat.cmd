@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0runtime\pythonw.exe" (
  start "" "%~dp0runtime\pythonw.exe" -I "%~dp0start_birth_chat.pyw" %*
  exit /b
)
if exist "%~dp0dist\BirthChat-Windows\Start-BirthChat.cmd" (
  call "%~dp0dist\BirthChat-Windows\Start-BirthChat.cmd" %*
  exit /b
)
echo Bundled runtime missing. Use dist\BirthChat-Windows\Start-BirthChat.cmd
echo Or run a Python 3.12+ installation with Tk: python -m birth.windows_chat
pause
exit /b 1
