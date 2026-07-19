@echo off
setlocal enabledelayedexpansion
title WuHuaGachaAnalysis

echo ========================================
echo    WuHuaGachaAnalysis
echo ========================================
echo.

:: 查找 Python
set PYTHON=
for %%p in (python python3 py) do (
    %%p --version >nul 2>&1
    if !errorlevel! equ 0 set PYTHON=%%p
)
if "%PYTHON%"=="" set PYTHON=python

%PYTHON% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python
    echo 请安装 Python 3.11: https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo Python: 
%PYTHON% --version

:: 进入脚本所在目录
cd /d "%~dp0"

:: 创建虚拟环境
if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] 创建虚拟环境...
    %PYTHON% -m venv .venv
    if !errorlevel! neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: 激活
call .venv\Scripts\activate.bat

:: 安装依赖
echo [2/3] 安装依赖...
pip install -r requirements.txt -q 2>nul
if !errorlevel! neq 0 (
    echo 重试安装...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [错误] 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
)

:: 首次运行自动下载 PaddleOCR 模型
echo [3/3] 启动（首次需下载 OCR 模型，约 1 分钟）...
%PYTHON% -m src.main

if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出 (code: %errorlevel%)
    pause
)
