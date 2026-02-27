@echo off
echo Starting Options Scanner V2 (Sandbox) on Port 5001...
echo.

cd /d "%~dp0"

:: Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Please run setup first if needed.
)

:: Set environment variables
set FLASK_APP=backend/app.py
set FLASK_ENV=development
set PORT=5001

:: Start Flask
echo Starting Flask Server...
python -m flask run --port=5001 --host=0.0.0.0
pause
