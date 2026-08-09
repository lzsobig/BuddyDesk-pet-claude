@echo off
chcp 65001 >nul 2>&1
title BuddyDesk
setlocal

REM Always resolve files relative to this script, not the caller's cwd.
cd /d "%~dp0"

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
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        set "PY=%%~P"
        goto :found
    )
)
echo [ERROR] Python 3.10+ not found. Install from https://python.org
echo Make sure to check "Add Python to PATH".
pause
exit /b 1

:found
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required.
    %PY% --version
    pause
    exit /b 1
)

REM Install dependencies on first run; only mark success after pip succeeds.
if not exist ".deps_installed" (
    echo [1/2] Installing dependencies...
    %PY% -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [WARN] System install failed; retrying for current user...
        %PY% -m pip install -r requirements.txt --quiet --user
    )
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. No success marker was written.
        pause
        exit /b 1
    )
    echo. > ".deps_installed"
)

REM Launch
 echo [2/2] Launching BuddyDesk...
%PY% main.py
if errorlevel 1 (
    echo.
    echo BuddyDesk exited with an error.
    pause
)
endlocal
