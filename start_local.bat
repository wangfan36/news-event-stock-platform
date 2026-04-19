@echo off
setlocal
cd /d "%~dp0"

echo Starting local app...
start "news-stock-platform" cmd /k "cd /d %~dp0 && python -m iching_alpha.webapp"
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000/
