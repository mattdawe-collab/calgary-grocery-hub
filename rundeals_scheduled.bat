@echo off
REM ============================================================
REM  Calgary Grocery Hub - Scheduled Weekly Run (non-interactive)
REM  Triggered by Windows Task Scheduler. Logs to logs\scheduled_*.log
REM ============================================================

cd /d "%~dp0"

REM Build timestamp for log filename. Prefer PowerShell over deprecated WMIC.
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set STAMP=%%I

if not exist logs mkdir logs
set LOG=logs\scheduled_%STAMP%.log

REM Force UTF-8 stdout for Python (avoids cp1252 emoji crash)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

call :run_chain > "%LOG%" 2>&1
set RESULT=%ERRORLEVEL%
exit /b %RESULT%

:run_chain
  echo ==========================================================
  echo  Calgary Grocery Hub - Scheduled run %STAMP%
  echo ==========================================================

  echo.
  echo Running public publication chain...
  python tools\run_publication_chain.py
  set CHAIN_RESULT=%ERRORLEVEL%

  echo.
  echo.
  echo ==========================================================
  if "%CHAIN_RESULT%"=="0" (
    echo  Scheduled run COMPLETE %STAMP%
  ) else (
    echo  Scheduled run FAILED %STAMP% - see ERRORs above
  )
  echo ==========================================================
exit /b %CHAIN_RESULT%
