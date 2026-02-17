@echo off
echo 🚀 STARTING DEV SERVER (Port 5000)...
cd /d "%~dp0"
call .venv\Scripts\activate
python backend\app.py
pause
