@echo off
cd /d "%~dp0"
echo 🧠 Grocery Brain Starting...
python get_deals.py
echo.
echo 📊 Generating Weekly Reports...
set PYTHONIOENCODING=utf-8
python weekly_report_generator.py
echo.
call push_to_github.bat
pause
