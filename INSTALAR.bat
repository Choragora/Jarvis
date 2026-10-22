@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
echo JARVIS - Instalacao por utilizador, sem privilegios de administrador
call :find_python
if /i "%~1"=="--check-python" goto check_python
if defined JARVIS_PYTHON goto python_ready
echo Nao foi encontrado um Python 3.12 x64 utilizavel.
where winget.exe >nul 2>&1
if errorlevel 1 goto python_manual
choice /c SN /n /m "Instalar Python 3.12 x64 para este utilizador pelo WinGet oficial? [S/N] "
if errorlevel 2 goto python_manual
winget install --id Python.Python.3.12 --exact --source winget --scope user --architecture x64 --accept-source-agreements --accept-package-agreements --disable-interactivity
if errorlevel 1 goto python_manual
call :find_python
if not defined JARVIS_PYTHON goto python_manual
:python_ready
echo Python encontrado:
set JARVIS_PYTHON
where node >nul 2>&1
if errorlevel 1 (
  echo Instale Node.js LTS de https://nodejs.org/ e volte a executar.
  goto falha
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -I -c "import struct,sys; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)"
  if errorlevel 1 (
    echo A pasta .venv existente usa outra versao ou arquitetura do Python.
    echo Preserve-a renomeando-a para .venv-anterior e execute este instalador novamente.
    goto falha
  )
)
if not exist ".venv\Scripts\python.exe" "%JARVIS_PYTHON%" -m venv .venv
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
:find_python
set "JARVIS_PY_DETECTED="
for /f "tokens=1,* delims==" %%A in ('call "%~dp0scripts\detect_python.bat"') do if "%%A"=="JARVIS_PY_EXE" set "JARVIS_PY_DETECTED=%%B"
set "JARVIS_PYTHON=%JARVIS_PY_DETECTED%"
exit /b 0
:check_python
if not defined JARVIS_PYTHON exit /b 1
set JARVIS_PYTHON
exit /b 0
:python_manual
echo.
echo Instale Python 3.12 x64 pelo instalador oficial:
echo https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
echo Pode escolher Install Now por utilizador. O launcher py e opcional.
echo Depois feche esta janela e execute INSTALAR.bat novamente.
goto falha
:falha
echo.
echo A instalacao encontrou um problema. O erro esta acima. Consulte README.md.
pause
exit /b 1
