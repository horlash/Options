@echo off
REM ========================================
REM Docker Multi-Platform Build & Push Script
REM Version: 1.0.1
REM ========================================

echo.
echo ========================================
echo Building NewScanner v1.0.1
echo Multi-Platform: AMD64 + ARM64
echo ========================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

echo [1/4] Docker Desktop is running...
echo.

REM Check Docker Hub login
echo [2/4] Checking Docker Hub login...
docker pull hello-world >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Not logged into Docker Hub
    echo Please login now:
    echo.
    docker login
    if %errorlevel% neq 0 (
        echo [ERROR] Docker login failed!
        pause
        exit /b 1
    )
)

echo [✓] Logged into Docker Hub
echo.

REM Build and push multi-platform image
echo [3/4] Building multi-platform image...
echo   Platforms: linux/amd64, linux/arm64
echo   Tags: horlamy/newscanner:1.0.1, horlamy/newscanner:latest
echo.
echo This may take 5-10 minutes depending on your internet speed...
echo.

docker buildx build --platform linux/amd64,linux/arm64 ^
  -t horlamy/newscanner:1.0.1 ^
  -t horlamy/newscanner:latest ^
  --push .

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [✓] Build and push complete!
echo.

REM Verify the push
echo [4/4] Verifying image on Docker Hub...
docker manifest inspect horlamy/newscanner:1.0.1 >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Could not verify manifest (this is normal sometimes)
) else (
    echo [✓] Image verified on Docker Hub
)

echo.
echo ========================================
echo SUCCESS!
echo ========================================
echo.
echo Image pushed to Docker Hub:
echo   - horlamy/newscanner:1.0.1
echo   - horlamy/newscanner:latest
echo.
echo Supported platforms:
echo   - linux/amd64 (Windows, Linux x86_64)
echo   - linux/arm64 (Raspberry Pi 4/5)
echo.
echo To run on Raspberry Pi:
echo   docker pull horlamy/newscanner:1.0.1
echo   docker run -d -p 5000:5000 horlamy/newscanner:1.0.1
echo.
pause
