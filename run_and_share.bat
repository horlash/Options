@echo off
echo ========================================
echo LEAP Scanner - Launch ^& Share
echo ========================================

REM 1. Check Token Health (Auto-Heal)
python check_token_status.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ⚠️ TOKEN EXPIRING OR INVALID! Launching Re-Auth Tool...
    echo Please complete the login in the new window.
    start /wait cmd /c "python auto_schwab_auth.py && pause"
)

REM 2. Start Backend in a new window
echo Starting Backend Server...
start "LEAP Scanner Backend" cmd /k "call start_backend.bat"

REM 2. Wait a few seconds for backend to initialize
echo Waiting for server to start...
timeout /t 7 /nobreak

REM 3. Start Ngrok Share in a new window
echo Starting Ngrok Sharing...
start "LEAP Scanner Share" cmd /k "call share_app.bat"

echo.
echo ========================================
echo Services Launched!
echo 1. Backend: Running on http://localhost:5050 (Window 1)
echo 2. Sharing: Ngrok Tunnel active (Window 2)
echo ========================================
echo.
pause
