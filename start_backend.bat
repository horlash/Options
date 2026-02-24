@echo off
echo ========================================
echo LEAP Options Scanner - Starting...
echo ========================================
echo.

REM Activate virtual environment
REM call .venv\Scripts\activate.bat

REM Initialize database if needed
echo Initializing database...
python -c "from backend.database.models import init_db; init_db()"

echo.
echo Starting Secured Server on http://localhost:5050
echo (Frontend is served automatically)
echo.
echo Press Ctrl+C to stop the server
echo.
python -c "from backend.app import app; app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)"
