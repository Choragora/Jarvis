@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  pause
  exit /b 1
)
echo Browser isolado preparado para inspecao de websites.
pause
