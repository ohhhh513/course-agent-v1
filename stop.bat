@echo off
title Course-Agent Stopper

REM ============================================================
REM  Course Agent - One-click Stop
REM ============================================================

set "PORT=8000"

echo.
echo  ================================================
echo   Course Agent - Stopping port %PORT%
echo  ================================================
echo.

set "FOUND=0"
for /f "tokens=5" %%P in ('netstat -ano -p TCP ^| findstr ":%PORT%" ^| findstr LISTENING 2^>nul') do (
    set "FOUND=1"
    echo  Found PID=%%P on port %PORT% - killing...
    taskkill /F /PID %%P >nul 2>nul
)

if "%FOUND%"=="0" (
    echo  Port %PORT% is free - nothing to stop.
)

taskkill /FI "WINDOWTITLE eq CourseAgent-Backend*" /F >nul 2>nul

echo.
echo  Done.
echo.
