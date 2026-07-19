@echo off
chcp 65001 >nul
title WuHuaGachaAnalysis

echo ========================================
echo    WuHuaGachaAnalysis 物华弥新抽卡分析器
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查/创建虚拟环境
if not exist ".venv" (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 安装依赖
echo [2/3] 安装依赖...
pip install -r requirements.txt -i https://mirror.baidu.com/pypi/simple -q

:: 启动应用
echo [3/3] 启动应用...
python -m src.main

pause
