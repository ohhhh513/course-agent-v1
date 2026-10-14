@echo off
chcp 65001 >nul
title Course Agent · 批量上传
echo.
echo  =========================================
echo   Course Agent 开发批量上传（交互模式）
echo  =========================================
echo  请先启动后端 start.bat，再按提示操作。
echo.

cd /d "%~dp0\.."

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未找到 python
  pause
  exit /b 1
)

echo  [1/2] 课程初始化（章/KP/资源）
python dev_tools\init_course.py --config dev_tools\course_structure_ds.json
echo.

echo  [2/2] 题库导入（若需要）
set /p DOQ=是否现在导入题库？(y/n): 
if /i "%DOQ%"=="y" (
  python dev_tools\import_questions.py --file dev_tools/questions_after_class_import.json
)

echo.
echo  完成。浏览器打开 http://127.0.0.1:8000 用教师账号查看课程。
pause
