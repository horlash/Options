@echo off
title Options Scanner (PRODUCTION)
echo ==============================================
echo   Options Scanner - Production Launch
echo ==============================================
echo.

cd /d "%~dp0"

:: 1. Activate Environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found!
    echo Please run 'setup_windows.bat' first.
    pause
    exit /b 1
)

:: 2. Set Production Variables
set FLASK_APP=backend.app:app
set FLASK_ENV=production
set FLASK_DEBUG=0
set PYTHONUNBUFFERED=1

:: 3. Launch with Waitress (Production Server)
echo Starting Waitress Server on Port 5001...
echo Access at: http://localhost:5001
echo.

python -m waitress --port=5001 backend.app:app

pause
