@echo off
setlocal enabledelayedexpansion

title HimShiksha API - Push Updates to GitHub
echo ========================================================
echo       HIMSHIKSHA API - GITHUB ONE-CLICK UPDATE TOOL
echo ========================================================
echo.

cd /d "%~dp0"
echo [1/5] Working Directory: %CD%
echo.

echo [2/5] Checking Git Status...
git status
echo.

echo --------------------------------------------------------
set /p CONFIRM="Do you want to stage, commit, and push these changes to GitHub? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo [INFO] Update cancelled by user.
    goto :END
)

echo.
set /p COMMIT_MSG="Enter commit description (Press ENTER for default: 'Update HimShiksha API routes and services'): "
if "%COMMIT_MSG%"=="" (
    set COMMIT_MSG=Update HimShiksha API routes and services (%date% %time%)
)

echo.
echo [3/5] Staging modified and new API files...
git add main.py requirements.txt routes/ services/ utils/ schemas/ Procfile render.yaml .gitignore
git status --short

echo.
echo [4/5] Committing changes...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo [NOTE] No new changes to commit or commit failed.
)

echo.
echo [5/5] Pushing to GitHub (branch: main)...
echo If prompted, authenticate with your GitHub browser login or Personal Access Token.
git push origin main

if errorlevel 0 (
    echo.
    echo ========================================================
    echo   SUCCESS: Changes successfully pushed to GitHub!
    echo   Render will automatically detect and deploy the update.
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   ERROR: Git push encountered an issue.
    echo   Please verify your GitHub credentials or internet.
    echo ========================================================
)

:END
echo.
pause
