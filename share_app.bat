@echo off
echo ========================================
echo Options Scanner - Share App
echo ========================================
echo.
echo Checking for ngrok...
where ngrok >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Ngrok is not found in your PATH.
    echo Please install ngrok from https://ngrok.com/download
    echo and ensure it is available in your command line.
    echo.
    pause
    exit /b
)

echo.
echo Starting Ngrok tunnel to port 5000...
echo.
echo Copy the "Forwarding" URL (https://...) to share with others.
echo Users will need to login with the credentials you set.
echo.
if exist "ngrok.exe" (
    .\ngrok.exe http 5000
) else (
    ngrok http 5000
)
