@echo off
chcp 65001 >nul
title LangGraph 可视化编排平台

echo ============================================
echo   LangGraph 可视化编排平台
echo ============================================
echo.

:: Activate virtual environment
call "%~dp0..\venv\Scripts\activate.bat"

:: Check if venv exists
if not exist "%~dp0..\venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在，请先运行 setup.bat
    pause
    exit /b 1
)

echo [信息] 启动服务...
echo [信息] API 文档: http://localhost:8765/docs
echo [信息] 可视化界面: http://localhost:8765
echo.

python "%~dp0..\main.py"

pause
