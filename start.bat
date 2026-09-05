@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Course-Agent Launcher

REM ============================================================
REM  Course Agent - One-click Start
REM ============================================================

set "PORT=8000"
set "PYTHON=C:\Users\CQYDDD\.local\bin\python3.12.exe"
set "PROJECT=%~dp0"
set "BACKEND=%PROJECT%backend"

echo.
echo  ================================================
echo   Course Agent - Starting on port %PORT%
echo  ================================================
echo.

REM --- 1. Check prerequisites ---
echo  [1/5] Checking environment...

if not exist "%PYTHON%" (
    echo  [ERROR] Python not found at: %PYTHON%
    echo          Please edit PYTHON at the top of this file.
    pause
    exit /b 1
)

"%PYTHON%" -c "import sys; print('       Python', sys.version.split()[0])"

if not exist "%BACKEND%\requirements.txt" (
    echo  [ERROR] backend\requirements.txt not found.
    pause
    exit /b 1
)
echo        Environment OK.

REM --- 2. Kill anything on the port ---
echo.
echo  [2/5] Clearing port %PORT%...
set "KILLED=0"
for /f "tokens=5" %%P in ('netstat -ano -p TCP ^| findstr ":%PORT%" ^| findstr LISTENING 2^>nul') do (
    echo        Killing PID=%%P
    taskkill /F /PID %%P >nul 2>nul
    set "KILLED=1"
)
if !KILLED!==0 echo        No process was listening on port %PORT%.
ping -n 3 127.0.0.1 >nul

REM --- 3. Ensure dependencies ---
echo.
echo  [3/5] Checking dependencies...
"%PYTHON%" -c "import fastapi, sqlalchemy, uvicorn, jose, passlib" 2>nul
if errorlevel 1 (
    echo  First run - installing dependencies, please wait...
    cd /d "%BACKEND%"
    "%PYTHON%" -m pip install --break-system-packages -r requirements.txt
    "%PYTHON%" -m pip install --break-system-packages bcrypt==4.0.1
    if errorlevel 1 (
        echo  [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo  Dependencies installed.
) else (
    echo        Dependencies OK.
)

REM --- 4. Launch backend ---
echo.
echo  [4/5] Launching server on 127.0.0.1:%PORT%...

cd /d "%BACKEND%"
if not exist "app\data" mkdir "app\data"

start "CourseAgent-Backend" /MIN "%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

REM --- 5. Wait for health check ---
echo.
echo  [5/5] Waiting for server to be ready, up to 90 seconds...
set /a RETRY=0
:HEALTH
set /a RETRY+=1
if %RETRY% gtr 45 (
    echo.
    echo.
    echo  [FAIL] Server failed to start within 90 seconds.
    echo          Please check the CourseAgent-Backend console window for errors.
    pause
    exit /b 1
)
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%PORT%/health', timeout=2)" 2>nul
if errorlevel 1 (
    <nul set /p "=       ... still starting (%RETRY%/45)"
    ping -n 2 127.0.0.1 >nul
    goto HEALTH
)

echo.
echo.
echo  ================================================
echo   Server is READY!
echo  ================================================
echo.
echo   Frontend : http://127.0.0.1:%PORT%/
echo   API Docs : http://127.0.0.1:%PORT%/docs
echo   Login    : student / 123456
echo              teacher / 123456
echo.
echo  ================================================
echo.

start "" "http://127.0.0.1:%PORT%/"
endlocal
