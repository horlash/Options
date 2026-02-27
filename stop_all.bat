@echo off
echo ========================================
echo Options Scanner - Stopping All Services
echo ========================================

echo.
echo Stopping Backend (Python)...
taskkill /F /IM python.exe /T 2>nul
if %errorlevel% neq 0 echo (Python was not running)

echo.
echo Stopping Sharing (Ngrok)...
taskkill /F /IM ngrok.exe /T 2>nul
if %errorlevel% neq 0 echo (Ngrok was not running)

echo.
echo ========================================
echo All services stopped.
echo ========================================
pause
