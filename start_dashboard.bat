@echo off
setlocal
title Calgary Grocery Hub - Dashboard

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "API_PORT=8000"
if not "%~1"=="" set "API_PORT=%~1"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================
echo   Calgary Grocery Hub - Dashboard
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%\dashboard\dist\index.html" (
    echo React production build is missing. Building dashboard...
    where npm >nul 2>&1
    if errorlevel 1 (
        echo ERROR: npm was not found in PATH. Install Node.js, then run:
        echo   cd /d "%PROJECT_DIR%\dashboard"
        echo   npm install
        echo   npm run build
        pause
        exit /b 1
    )
    pushd "%PROJECT_DIR%\dashboard"
    if not exist node_modules (
        npm install
        if errorlevel 1 (
            popd
            echo ERROR: npm install failed.
            pause
            exit /b 1
        )
    )
    npm run build
    if errorlevel 1 (
        popd
        echo ERROR: dashboard build failed.
        pause
        exit /b 1
    )
    popd
)

echo Starting FastAPI server on port %API_PORT%...
start "Calgary Grocery Hub API" /D "%PROJECT_DIR%" cmd /k "set PYTHONUTF8=1&& set PYTHONIOENCODING=utf-8&& python -m uvicorn api.main:app --host 0.0.0.0 --port %API_PORT%"

timeout /t 3 /nobreak >nul

echo.
echo Local dashboard:
echo   http://localhost:%API_PORT%
echo.
echo API:
echo   http://localhost:%API_PORT%/api/insights
echo.
echo Press any key in this window to stop the API server.
pause >nul

taskkill /fi "windowtitle eq Calgary Grocery Hub API*" /f >nul 2>&1
echo Server stopped.
endlocal
