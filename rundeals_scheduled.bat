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

REM Failure flag - set to 1 by any failing stage so we can surface to Task Scheduler
set FAILED=0

(
  echo ==========================================================
  echo  Calgary Grocery Hub - Scheduled run %STAMP%
  echo ==========================================================

  echo.
  echo [1/4] Scraping flyers ^(get_deals.py^)...
  python get_deals.py
  if errorlevel 1 (
    echo ERROR: get_deals.py failed with errorlevel %errorlevel%
    set FAILED=1
    goto :health
  )

  echo.
  echo [2/4] Generating social media reports ^(weekly_report_generator.py^)...
  python weekly_report_generator.py
  if errorlevel 1 (
    echo ERROR: weekly_report_generator.py failed with errorlevel %errorlevel% - skipping push so we don't deploy stale data
    set FAILED=1
    goto :health
  )

  echo.
  echo [3/4] Committing, pushing to GitHub, deploying to Railway...
  call push_to_github.bat
  if errorlevel 1 (
    echo ERROR: push_to_github.bat failed with errorlevel %errorlevel%
    set FAILED=1
    goto :health
  )

  :health
  echo.
  echo [4/4] Dashboard health check ^(after 60s grace for Railway redeploy^)...
  timeout /t 60 /nobreak > nul

  call :check_url "Railway dashboard" "https://calgarygroceryhub.up.railway.app"
  if errorlevel 1 set FAILED=1

  echo.
  echo ==========================================================
  if "%FAILED%"=="1" (
    echo  Scheduled run FAILED %STAMP% - see ERRORs above
  ) else (
    echo  Scheduled run COMPLETE %STAMP%
  )
  echo ==========================================================
) > "%LOG%" 2>&1

REM Surface real exit code so Task Scheduler "Last Run Result" reflects truth
if "%FAILED%"=="1" exit /b 1
exit /b 0

:check_url
REM %~1 = label, %~2 = url. Returns errorlevel 1 if URL doesn't return 200.
set "URL_LABEL=%~1"
set "URL_TARGET=%~2"
for /f "delims=" %%S in ('powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%URL_TARGET%' -UseBasicParsing -TimeoutSec 20 -MaximumRedirection 5; $r.StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'DOWN' } }"') do set HTTP_STATUS=%%S
echo   - %URL_LABEL%: HTTP %HTTP_STATUS% ^(%URL_TARGET%^)
if "%HTTP_STATUS%"=="200" (
  echo     OK
  exit /b 0
)
echo     ALERT: dashboard not returning 200 - investigate
exit /b 1
