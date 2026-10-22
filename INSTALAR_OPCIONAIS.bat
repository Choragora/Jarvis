@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install --require-hashes -r requirements-online.txt
if errorlevel 1 (
  pause
  exit /b 1
)
echo Adaptadores online instalados. Nenhum pedido pago foi feito.
echo Configure uma credencial e autorize custos nas definicoes antes de ativar.
pause
