@echo off
chcp 65001 >nul 2>&1
title BuddyDesk

REM Find Python
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto :found
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto :found
)
echo [ERROR] Python 3.10+ not found. Install from https://python.org
echo Make sure to check "Add Python to PATH".
pause
exit /b 1

:found
REM Check version
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required.
    %PY% --version
    pause
    exit /b 1
)

REM Install dependencies on first run
if not exist ".deps_installed" (
    echo [1/2] Installing dependencies...
    %PY% -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        %PY% -m pip install -r requirements.txt --quiet --user
    )
    echo. > .deps_installed
)

REM Launch
echo [2/2] Launching BuddyDesk...
cd /d "%~dp0"
%PY% main.py
if errorlevel 1 (
    echo.
    echo BuddyDesk exited with an error.
    pause
)
