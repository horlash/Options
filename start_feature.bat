@echo off
echo ========================================
echo FEATURE BRANCH - Trading UI Testing
echo ========================================
echo.

REM Set port to 5002 for feature branch testing
set PORT=5002

REM Initialize database if needed
echo Initializing database...
python -c "from backend.database.models import init_db; init_db()"

echo.
echo Starting Feature Server on http://localhost:5002
echo (Prod remains on http://localhost:5000)
echo.
echo Press Ctrl+C to stop the server
echo.
python -m backend.app
