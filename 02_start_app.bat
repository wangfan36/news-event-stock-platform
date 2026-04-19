@echo off
setlocal
cd /d "%~dp0"

set APP_HOST=127.0.0.1
set APP_PORT=8000

if exist ".venv\Scripts\python.exe" (
  set PYTHON_EXE=.venv\Scripts\python.exe
) else (
  set PYTHON_EXE=python
)

echo Starting app at http://%APP_HOST%:%APP_PORT%/
start "news-stock-platform" cmd /k "cd /d %~dp0 && %PYTHON_EXE% -m iching_alpha.webapp"
timeout /t 3 /nobreak >nul
start "" http://%APP_HOST%:%APP_PORT%/
