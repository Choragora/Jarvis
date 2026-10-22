@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo JARVIS - Instalacao por utilizador, sem privilegios de administrador
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Instale Python 3.12 x64 de https://www.python.org/downloads/windows/ e volte a executar.
  goto falha
)
where node >nul 2>&1
if errorlevel 1 (
  echo Instale Node.js LTS de https://nodejs.org/ e volte a executar.
  goto falha
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto falha
".venv\Scripts\python.exe" -m pip install --require-hashes -r requirements-windows.txt
if errorlevel 1 goto falha
call npm ci --prefix tools\codex --ignore-scripts --no-audit --no-fund
if errorlevel 1 goto falha
".venv\Scripts\python.exe" -m jarvis.preflight
if errorlevel 1 goto falha
echo.
echo Instalacao concluida. Abra INICIAR_JARVIS.bat.
echo Na primeira utilizacao, prepare o modelo STT e ligue o ChatGPT nas definicoes.
pause
exit /b 0
:falha
echo.
echo A instalacao encontrou um problema. O erro esta acima. Consulte README.md.
pause
exit /b 1
