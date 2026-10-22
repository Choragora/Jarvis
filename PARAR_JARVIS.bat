@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -m jarvis stop
if errorlevel 1 pause
