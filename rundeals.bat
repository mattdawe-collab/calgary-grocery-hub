@echo off
title Calgary Grocery Hub - Weekly Run
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

echo Running Calgary Grocery Hub public publication chain...
python tools\run_publication_chain.py
if errorlevel 1 (
    echo ERROR: publication chain failed.
    pause
    exit /b 1
)

echo Complete. Opening Current Flyer Report...
start current_flyers.csv
pause
