@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\check_local_app.py
) else (
  python scripts\check_local_app.py
)

echo.
pause
