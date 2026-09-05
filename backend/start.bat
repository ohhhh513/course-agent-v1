@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === 清理旧进程 ===
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
    timeout /t 1 /nobreak >nul
)

echo === 启动后端 ===
python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
