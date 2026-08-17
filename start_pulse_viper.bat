@echo off
title PulseViper Trading Engine Launcher
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "ROOT=%~dp0"
set "PYEXE=%ROOT%venv\Scripts\python.exe"
set "LAUNCHER=%ROOT%launcher.py"

echo.
echo ============================================================
echo   PulseViper Trading Engine
echo ============================================================
echo.

REM Ensure log directory exists
if not exist "logs" mkdir logs

REM ----- Validate Python interpreter and launcher script -----
if not exist "%PYEXE%" (
    echo [ERROR] Python interpreter not found at:
    echo         %PYEXE%
    echo.
    echo Please create the virtual environment first:
    echo     py -3 -m venv venv
    echo     venv\Scripts\activate
    echo     python -m pip install --upgrade pip
    echo     pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%LAUNCHER%" (
    echo [ERROR] Launcher script not found at:
    echo         %LAUNCHER%
    echo.
    pause
    exit /b 1
)

REM ----- Forward all arguments from this .bat to launcher.py -----
set "ARGS=%*"

echo [INFO] Using Python : %PYEXE%
echo [INFO] Launcher     : %LAUNCHER%
if defined ARGS (
    echo [INFO] Arguments    : %ARGS%
)
echo.
echo [INFO] Starting PulseViper launcher engine...
echo.

"%PYEXE%" "%LAUNCHER%" %ARGS%
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo [DONE] PulseViper finished cleanly.
) else (
    echo [WARN] PulseViper exited with code %EXITCODE%.
    echo        Check logs in: %ROOT%logs\
)

echo.
pause
exit /b %EXITCODE%
