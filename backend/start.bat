@echo off
cd /d "%~dp0"

echo === Stop old process on port 8000 ===
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
    timeout /t 1 /nobreak >nul
)

echo === Start backend ===
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
