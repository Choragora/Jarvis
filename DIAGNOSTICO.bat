@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m jarvis.preflight
".venv\Scripts\python.exe" -m jarvis diagnostics
pause
