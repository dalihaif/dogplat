@echo off
chcp 65001 >nul
title 狗狗管理平台 · 关闭开机自启
cd /d "%~dp0"

set "VENV="
if exist "%~dp0py_path.txt" for /f "usebackq delims=" %%i in ("%~dp0py_path.txt") do set "VENV=%%i"
if not defined VENV set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set PY=%VENV%\python.exe

if not exist "%PY%" (
  echo [×] 找不到 Python 环境。
  pause
  exit /b 1
)

"%PY%" install_autostart.py off

echo.
echo 说明：只是不再随系统自动启动，当前正在运行的服务不受影响。
echo       想停当前服务，双击「停止服务.bat」。
echo.
pause
exit /b 0
