@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title Course-Agent Launcher

REM ============================================================
REM  Course Agent - One-click Start
REM ============================================================

set "PORT=8000"
REM Python 解释器优先级：自定义路径、项目 venv、已激活 Conda、常用 stucourse 路径、PATH 与 py 启动器。
REM 其他电脑可设置 COURSE_AGENT_PYTHON 指向自己的 python.exe，无需修改此脚本。
set "PROJECT=%~dp0"
set "BACKEND=%PROJECT%backend"

echo.
echo  ================================================
echo   Course Agent - Starting on port %PORT%
echo  ================================================
echo.

REM --- 1. Check prerequisites ---
echo  [1/5] Checking environment...

set "PYTHON="

REM 每个候选都检查 Python 版本，选中后再由依赖步骤检查或安装缺失包。
if defined COURSE_AGENT_PYTHON call :TryPython "%COURSE_AGENT_PYTHON%" "COURSE_AGENT_PYTHON"
if not defined PYTHON call :TryPython "%BACKEND%\.venv\Scripts\python.exe" "project venv"
if not defined PYTHON if defined CONDA_PREFIX call :TryPython "%CONDA_PREFIX%\python.exe" "active Conda environment"
if not defined PYTHON call :TryPython "E:\anaconda\envs\stucourse\python.exe" "stucourse Conda environment"

if not defined PYTHON (
    for /f "delims=" %%E in ('where python3.11 2^>nul') do if not defined PYTHON call :TryPython "%%E" "PATH python3.11"
)
if not defined PYTHON (
    for /f "delims=" %%E in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PYTHON call :TryPython "%%E" "py launcher Python 3.11"
)
if not defined PYTHON (
    for /f "delims=" %%E in ('where python 2^>nul') do if not defined PYTHON call :TryPython "%%E" "PATH Python"
)

if not defined PYTHON (
    echo  [ERROR] A Python 3.11 environment was not found.
    echo          Set COURSE_AGENT_PYTHON to the full path of python.exe and retry.
    echo          Checked the project venv, active Conda environment, and PATH.
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
REM openai 也在检查项里：缺了它智能答疑会静默退回演示模式（只检索、不调模型）
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
echo   Login    : admin / admin   （首次启动用管理员建教师与课程）
echo              （系统不再内置演示师生账号；演示库账号见 dev_tools 说明）
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
if errorlevel 1 exit /b 1
set "PYTHON=%~1"
echo        Using %~2
exit /b 0
