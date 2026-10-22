@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "JARVIS_PY_EXE="

rem An explicit path and an existing environment do not need the py launcher.
if defined JARVIS_PYTHON call :probe "%JARVIS_PYTHON%"
if defined JARVIS_PY_EXE goto found
call :probe "%~dp0..\.venv\Scripts\python.exe"
if defined JARVIS_PY_EXE goto found

for /f "delims=" %%P in ('py -3.12 -X utf8 -c "import sys; print(sys.executable)" 2^>nul') do call :probe "%%P"
if defined JARVIS_PY_EXE goto found

call :probe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :probe "%ProgramFiles%\Python312\python.exe"
if defined JARVIS_PY_EXE goto found

for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Python\PythonCore\3.12\InstallPath" /v ExecutablePath 2^>nul') do if /i "%%A"=="REG_SZ" call :probe "%%B"
for /f "tokens=2,*" %%A in ('reg query "HKLM\Software\Python\PythonCore\3.12\InstallPath" /v ExecutablePath 2^>nul') do if /i "%%A"=="REG_SZ" call :probe "%%B"
if defined JARVIS_PY_EXE goto found

for /f "delims=" %%P in ('where python.exe 2^>nul') do call :probe "%%P"
if defined JARVIS_PY_EXE goto found
exit /b 1

:probe
if defined JARVIS_PY_EXE exit /b 0
if not exist "%~1" exit /b 1
rem Do not open the Microsoft Store placeholder while testing PATH candidates.
if /i "%~f1"=="%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" exit /b 1
"%~1" -I -c "import struct,sys; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "JARVIS_PY_EXE=%~f1"
exit /b 0

:found
rem Printing through SET preserves metacharacters in names such as A^&B.
set JARVIS_PY_EXE
exit /b 0
