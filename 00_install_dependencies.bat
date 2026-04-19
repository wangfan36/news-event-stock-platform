@echo off
setlocal
cd /d "%~dp0"

echo Creating local virtual environment...
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Done. Next run 01_check_environment.bat
pause
