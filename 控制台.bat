@echo off
chcp 65001 >nul
set "_root=%~dp0"
cd /d "%_root%"

set "PATH=%_root%toolkit;%_root%toolkit\Scripts;%_root%toolkit\Git\mingw64\bin;%_root%toolkit\adb;%PATH%"

title 物华弥新抽卡分析器 - 控制台
echo ========================================
echo   物华弥新抽卡分析器 - 调试控制台
echo ========================================
echo.
echo   可用命令:
echo     python -V         查看Python版本
echo     pip list          查看已安装包
echo     git log           查看更新日志
echo     adb devices       查看已连接设备
echo     python -m src.main  启动主程序
echo.
echo ========================================
echo.

cmd /K
