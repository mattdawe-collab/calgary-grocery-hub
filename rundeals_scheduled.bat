@echo off
REM ============================================================
REM  Calgary Grocery Hub - Scheduled Weekly Run (non-interactive)
REM  Triggered by Windows Task Scheduler. Logs to logs\scheduled_*.log
REM ============================================================

cd /d "%~dp0"

REM Build timestamp for log filename
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set STAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%%DT:~10,2%%DT:~12,2%

if not exist logs mkdir logs
set LOG=logs\scheduled_%STAMP%.log

REM Force UTF-8 stdout for Python (avoids cp1252 emoji crash)
set PYTHONIOENCODING=utf-8

(
  echo ==========================================================
  echo  Calgary Grocery Hub - Scheduled run %STAMP%
  echo ==========================================================

  echo.
  echo [1/4] Scraping flyers ^(get_deals.py^)...
  python get_deals.py
  if errorlevel 1 (
    echo ERROR: get_deals.py failed with errorlevel %errorlevel%
    goto :health
  )

  echo.
  echo [2/4] Generating social media reports ^(weekly_report_generator.py^)...
  python weekly_report_generator.py
  if errorlevel 1 (
    echo ERROR: weekly_report_generator.py failed with errorlevel %errorlevel%
    goto :health
  )

  echo.
  echo [3/4] Committing, pushing to GitHub, deploying to Railway...
  call push_to_github.bat
  if errorlevel 1 (
    echo ERROR: push_to_github.bat failed with errorlevel %errorlevel%
    goto :health
  )

  :health
  echo.
  echo [4/4] Dashboard health check ^(after 60s grace for Railway redeploy^)...
  timeout /t 60 /nobreak > nul

  call :check_url "Railway dashboard" "https://calgarygroceryhub.up.railway.app"

  echo.
  echo ==========================================================
  echo  Scheduled run COMPLETE %STAMP%
  echo ==========================================================
) > "%LOG%" 2>&1

exit /b %errorlevel%

:check_url
REM %~1 = label, %~2 = url. PowerShell call captures status code.
set "URL_LABEL=%~1"
set "URL_TARGET=%~2"
for /f "delims=" %%S in ('powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%URL_TARGET%' -UseBasicParsing -TimeoutSec 20 -MaximumRedirection 5; $r.StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'DOWN' } }"') do set HTTP_STATUS=%%S
echo   - %URL_LABEL%: HTTP %HTTP_STATUS% ^(%URL_TARGET%^)
if "%HTTP_STATUS%"=="200" (
  echo     OK
) else (
  echo     ALERT: dashboard not returning 200 - investigate
)
exit /b 0
