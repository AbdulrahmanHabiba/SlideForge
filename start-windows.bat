@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.11 or newer from python.org
    pause
    exit /b 1
)
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
echo.
echo SlideForge running at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
python run.py
pause
