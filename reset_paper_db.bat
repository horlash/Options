@echo off
echo ============================================
echo   Paper Trading DEV DB Reset
echo   Container: paper_trading_dev_db (port 5433)
echo   Clearing ALL trades for ALL users
echo ============================================
echo.

docker exec paper_trading_dev_db psql -U paper_user -d paper_trading -c "DELETE FROM state_transitions; DELETE FROM paper_trades;"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to connect to dev database. Is Docker running?
    echo Make sure the paper_trading_dev_db container is up.
    echo Try: docker-compose -f docker-compose.dev.yml up -d
    pause
    exit /b 1
)

echo.
echo [SUCCESS] All trades and state transitions cleared from DEV DB.
echo.

docker exec paper_trading_dev_db psql -U paper_user -d paper_trading -c "SELECT COUNT(*) AS remaining_trades FROM paper_trades; SELECT COUNT(*) AS remaining_transitions FROM state_transitions;"

echo.
echo ============================================
echo   DEV DB Reset Complete
echo ============================================
pause
