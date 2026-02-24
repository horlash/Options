@echo off
echo ========================================
echo LEAP Scanner - Launch ^& Share
echo ========================================

REM 1. Start Backend in a new window
echo Starting Backend Server...
start "LEAP Scanner Backend" cmd /k "cd /d %~dp0 && call start_backend.bat"

REM 2. Wait for backend to be ready (health check loop)
echo Waiting for backend to be ready...
set RETRIES=0
:healthcheck
set /a RETRIES+=1
if %RETRIES% GTR 30 (
    echo [ERROR] Backend failed to start after 30 attempts. Aborting.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:5050/ | findstr "200 302" >nul
if %errorlevel% neq 0 (
    echo    Attempt %RETRIES%/30 - Backend not ready yet...
    goto healthcheck
)
echo ✓ Backend is ready!

REM 3. Start Ngrok with custom domain
echo Starting Ngrok Sharing...
cd /d %~dp0
if exist "ngrok.exe" (
    start "LEAP Scanner Share" cmd /k "cd /d %~dp0 && .\ngrok.exe http 5050 --domain=tradeoptions.ngrok.app"
) else (
    start "LEAP Scanner Share" cmd /k "ngrok http 5050 --domain=tradeoptions.ngrok.app"
)

echo.
echo ========================================
echo Services Launched!
echo 1. Backend:  http://localhost:5050
echo 2. Public:   https://tradeoptions.ngrok.app
echo ========================================
echo.
pause
