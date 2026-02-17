@echo off
echo ========================================
echo LEAP Options Scanner - Publish to GitHub
echo ========================================
echo.
echo This script will help you push your local repository to GitHub.
echo.
echo 1. Create a new repository on GitHub (https://github.com/new).
echo    - Do NOT initialize with README, license, or gitignore.
echo.
set /p REMOTENAME="Enter the remote repository URL (e.g., https://github.com/username/repo.git): "
echo.
echo Adding remote 'origin'...
git remote add origin %REMOTENAME%
if %errorlevel% neq 0 (
   echo Remote 'origin' might already exist. Setting URL...
   git remote set-url origin %REMOTENAME%
)

echo.
echo Pushing to GitHub...
git branch -M main
git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo Successfully published to GitHub!
) else (
    echo Failed to push. Please check your credentials and URL.
)
pause
