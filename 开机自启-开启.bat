@echo off
chcp 65001 >nul
title 狗狗管理平台 · 开启开机自启
cd /d "%~dp0"

set "VENV="
if exist "%~dp0py_path.txt" for /f "usebackq delims=" %%i in ("%~dp0py_path.txt") do set "VENV=%%i"
if not defined VENV set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set PY=%VENV%\python.exe

if not exist "%PY%" (
  echo [×] 找不到 Python 环境，请先运行「安装.bat」。
  pause
  exit /b 1
)

"%PY%" install_autostart.py on

echo.
echo 说明：登录 Windows 后 15 秒，服务会自动在后台启动。
echo       浏览器打开 http://127.0.0.1:5800 即可使用，无需再点任何东西。
echo.
pause
exit /b 0
