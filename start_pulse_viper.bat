@echo off
title PulseViper Trading Engine Launcher
cd /d "%~dp0"
echo 🐍 PulseViper: Initializing environment...
if not exist venv\Scripts\activate.bat (
    echo ❌ Python virtual environment (venv) not found.
    echo Please create the virtual environment or run requirements installation first.
    pause
    exit /b 1
)
call venv\Scripts\activate
echo 🛠️ Running pre-flight checks and launching engine...
python launcher.py
pause
