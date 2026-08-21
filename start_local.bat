@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run scripts\setup.ps1 first.
  pause
  exit /b 1
)

start "News Alpha" cmd /k ""%CD%\.venv\Scripts\python.exe" -m news_alpha.webapp"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000/
