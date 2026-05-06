@echo off
:: Push updated CSVs to GitHub after scraper run
:: This triggers Railway auto-deploy if connected

cd /d "%~dp0"

echo.
echo ============================================
echo   Pushing updated data to GitHub...
echo ============================================

:: Stage the data files
git add current_flyers.csv historical_archive.csv

:: Check if there are actually changes to commit
git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo No changes to push — data is already up to date.
    exit /b 0
)

:: Get current date for commit message
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set DATESTAMP=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%

:: Commit and push
git commit -m "Update deal data %DATESTAMP%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Git commit failed!
    exit /b 1
)

git push origin main
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Git push failed!
    exit /b 1
)

echo.
echo ✅ Data pushed to GitHub.
echo.

:: Railway is hooked up to GitHub auto-deploy via railway.toml; the git push
:: above already triggers a redeploy. The manual `railway up` block below is
:: optional belt-and-suspenders. We skip it cleanly if:
::   - Railway CLI isn't on PATH (e.g. Task Scheduler context), OR
::   - Required source dirs (api\, dashboard\dist\) are missing, OR
::   - We can't write to the temp dir.
:: This avoids silent zero-payload deploys and avoids breaking the pipeline
:: when the CLI isn't authenticated for the scheduled-task user.

where railway >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Railway CLI not on PATH - skipping manual deploy. GitHub auto-deploy will handle it.]
    exit /b 0
)

if not exist "%~dp0api" (
    echo [api\ directory missing - skipping manual Railway deploy.]
    exit /b 0
)
if not exist "%~dp0dashboard\dist" (
    echo [dashboard\dist\ missing - skipping manual Railway deploy. Run "npm run build" in dashboard\.]
    exit /b 0
)

echo ============================================
echo   Deploying to Railway ^(manual^)...
echo ============================================

:: Use %TEMP% (per-user, always writable) instead of hard-coded C:\temp
set DEPLOY_DIR=%TEMP%\railway-deploy
if exist "%DEPLOY_DIR%" rmdir /s /q "%DEPLOY_DIR%"
mkdir "%DEPLOY_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: could not create %DEPLOY_DIR%
    exit /b 1
)

:: Copy required files
xcopy /s /i /q "%~dp0api" "%DEPLOY_DIR%\api"
xcopy /s /i /q "%~dp0dashboard\dist" "%DEPLOY_DIR%\dashboard\dist"
copy /y "%~dp0current_flyers.csv" "%DEPLOY_DIR%\"
copy /y "%~dp0historical_archive.csv" "%DEPLOY_DIR%\"
copy /y "%~dp0requirements.txt" "%DEPLOY_DIR%\"
copy /y "%~dp0railway.toml" "%DEPLOY_DIR%\"
copy /y "%~dp0Procfile" "%DEPLOY_DIR%\"
if exist "%~dp0.dockerignore" copy /y "%~dp0.dockerignore" "%DEPLOY_DIR%\"

:: Deploy to Railway from local copy
pushd "%DEPLOY_DIR%"
railway up --detach
if %ERRORLEVEL% NEQ 0 (
    popd
    echo ERROR: Railway deploy failed! GitHub auto-deploy will still pick up the push.
    exit /b 1
)
popd

echo.
echo ✅ Data deployed to Railway!
