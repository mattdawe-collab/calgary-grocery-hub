@echo off
title Calgary Grocery Hub - Dashboard

echo ============================================
echo   Calgary Grocery Hub - Starting Dashboard
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH!
    echo Please install Python or check your PATH settings.
    pause
    exit /b 1
)

:: Start FastAPI backend (serves both API + React production build)
echo Starting server on port 8000...
start "API Server" cmd /k "cd /d \"\\NASD66196\Python Projects\Weekly Deals\" && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

:: Give the API a moment to start
timeout /t 3 /nobreak >nul

:: Check if the server is actually running
netstat -an | findstr ":8000" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Server may not have started. Check the "API Server" window for errors.
    echo.
)

echo.
echo   Local:  http://localhost:8000
echo.

:: Ask if user wants to expose externally
set /p TUNNEL="Expose externally via ngrok? (y/n): "
if /i "%TUNNEL%"=="y" (
    echo Starting ngrok tunnel...
    start "ngrok Tunnel" cmd /k "ngrok http --url paris-prevertebral-unsusceptibly.ngrok-free.dev 8000"
    timeout /t 5 /nobreak >nul
    echo.
    echo   Public: https://paris-prevertebral-unsusceptibly.ngrok-free.dev
)

echo.
echo ============================================
echo   Dashboard is running!
echo   Press any key to stop all services...
echo ============================================
pause >nul

:: Kill all services
taskkill /fi "windowtitle eq API Server*" /f >nul 2>&1
taskkill /fi "windowtitle eq ngrok Tunnel*" /f >nul 2>&1
echo Servers stopped.
