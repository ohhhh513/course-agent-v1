@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title Course-Agent Launcher

REM ============================================================
REM  Course Agent - One-click Start
REM ============================================================

set "PORT=8000"
REM Local settings are optional and ignored by Git (.env.*).
REM Set COURSE_AGENT_CONDA_ENV or COURSE_AGENT_PYTHON in .env.start.bat.
set "PROJECT=%~dp0"
set "BACKEND=%PROJECT%backend"
if exist "%PROJECT%.env.start.bat" call "%PROJECT%.env.start.bat"

echo.
echo  ================================================
echo   Course Agent - Starting on port %PORT%
echo  ================================================
echo.

REM --- 1. Check prerequisites ---
echo  [1/5] Checking environment...

set "PYTHON="

REM Explicit settings must succeed; never silently use a different environment.
if defined COURSE_AGENT_PYTHON (
    call :TryPython "%COURSE_AGENT_PYTHON%" "COURSE_AGENT_PYTHON"
    if not defined PYTHON goto ENVIRONMENT_NOT_FOUND
    goto PYTHON_SELECTED
)
if defined COURSE_AGENT_CONDA_ENV (
    call :UseConda
    if not defined PYTHON goto ENVIRONMENT_NOT_FOUND
    goto PYTHON_SELECTED
)
if not defined PYTHON call :TryPython "%BACKEND%\.venv\Scripts\python.exe" "project venv"
if not defined PYTHON if defined CONDA_PREFIX call :TryPython "%CONDA_PREFIX%\python.exe" "active Conda environment"

if not defined PYTHON (
    for /f "delims=" %%E in ('where python3.11 2^>nul') do if not defined PYTHON call :TryPython "%%E" "PATH python3.11"
)
if not defined PYTHON (
    for /f "delims=" %%E in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PYTHON call :TryPython "%%E" "py launcher Python 3.11"
)
if not defined PYTHON (
    for /f "delims=" %%E in ('where python 2^>nul') do if not defined PYTHON call :TryPython "%%E" "PATH Python"
)

if not defined PYTHON goto ENVIRONMENT_NOT_FOUND

:PYTHON_SELECTED
echo        Executable: "%PYTHON%"
"%PYTHON%" -c "import sys; print('       Python', sys.version.split()[0])"

if not exist "%BACKEND%\requirements.txt" (
    echo  [ERROR] backend\requirements.txt not found.
    pause
    exit /b 1
)
echo        Environment OK.
REM Read-only diagnostic: do not install, kill processes, or start the server.
if /i "%~1"=="--check" exit /b 0

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
REM Include openai so a missing SDK does not silently disable model calls.
"%PYTHON%" -c "import fastapi, sqlalchemy, uvicorn, jose, passlib, openai" 2>nul
if errorlevel 1 (
    echo  First run - installing dependencies, please wait...
    cd /d "%BACKEND%"
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto DEPENDENCY_INSTALL_FAILED
    "%PYTHON%" -m pip install bcrypt==4.0.1
    if errorlevel 1 goto DEPENDENCY_INSTALL_FAILED
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
    <nul set /p "=       ... still starting %RETRY% of 45"
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
echo   Login    : admin / admin - create teachers and courses on first run.
echo              See dev_tools for demo accounts.
echo.
echo  ================================================
echo.

start "" "http://127.0.0.1:%PORT%/"
endlocal
exit /b 0

:DEPENDENCY_INSTALL_FAILED
echo  [ERROR] Failed to install dependencies into the selected Python environment.
echo          Check the pip output above, then install requirements in that environment.
pause
exit /b 1

:TryPython
if not exist "%~1" exit /b 1
"%~1" -c "import sys; sys.exit(0 if sys.version_info.major == 3 and sys.version_info.minor == 11 else 1)" >nul 2>nul
if errorlevel 1 (
    echo  [SKIP] %~2: Python 3.11 is required.
    "%~1" --version
    exit /b 1
)
set "PYTHON=%~1"
echo        Using %~2
exit /b 0

:UseConda
where conda.bat >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] conda.bat was not found. Run from Anaconda Prompt,
    echo          or set COURSE_AGENT_PYTHON to the environment's python.exe.
    exit /b 1
)
call conda.bat activate "%COURSE_AGENT_CONDA_ENV%"
if errorlevel 1 exit /b 1
call :TryPython "%CONDA_PREFIX%\python.exe" "Conda environment %COURSE_AGENT_CONDA_ENV%"
exit /b

:ENVIRONMENT_NOT_FOUND
echo  [ERROR] A Python 3.11 environment was not found or the selected environment is incompatible.
echo          Activate a Python 3.11 Conda environment, or create .env.start.bat with:
echo          set "COURSE_AGENT_CONDA_ENV=your-env-name"
echo          Alternatively set COURSE_AGENT_PYTHON to the full path of python.exe.
if /i "%~1"=="--check" exit /b 1
pause
exit /b 1
