@echo off
chcp 65001 >nul
title 狗狗管理平台 · 安装
cd /d "%~dp0"

echo.
echo ============================================================
echo   狗狗管理平台 环境安装
echo ============================================================
echo.

rem ========== 1. 找 Python 解释器 ==========
set "PYROOT="
if exist "C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
  set "PYROOT=C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
)
if not defined PYROOT (
  where py >nul 2>&1 && set "PYROOT=py -3"
)
if not defined PYROOT (
  where python >nul 2>&1 && set "PYROOT=python"
)
if not defined PYROOT (
  echo [错误] 没找到 Python。
  echo        请先安装 Python 3.10+（勾选 Add to PATH），或修改本文件里的 PYROOT。
  pause
  exit /b 1
)
echo [i] 使用 Python：%PYROOT%
echo.

rem ========== 2. 建虚拟环境（默认放在系统 venv 目录） ==========
set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default"
if not exist "%VENV%\Scripts\python.exe" (
  echo [1/3] 创建虚拟环境...
  %PYROOT% -m venv "%VENV%"
  if errorlevel 1 (
    echo [×] 创建虚拟环境失败。
    pause
    exit /b 1
  )
) else (
  echo [1/3] 虚拟环境已存在，跳过
)

set "PY=%VENV%\Scripts\python.exe"

rem ========== 3. 装依赖（清华源，失败自动换阿里源） ==========
echo [2/3] 升级 pip...
"%PY%" -m pip install -q --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 "%PY%" -m pip install -q --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/

echo [3/3] 安装依赖（flask / requests / beautifulsoup4 / lxml / Pillow / waitress）...
"%PY%" -m pip install -q -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo     清华源失败，换阿里源重试...
  "%PY%" -m pip install -q -r "%~dp0requirements.txt" -i https://mirrors.aliyun.com/pypi/simple/
)

rem ========== 4. 记录 Python 路径（其它脚本都读这个文件） ==========
echo %VENV%\Scripts>"%~dp0py_path.txt"

echo.
echo ============================================================
echo   [√] 安装完成
echo ============================================================
echo.
echo   下一步：双击「启动服务.bat」即可打开平台。
echo   想开机自动运行：双击「开机自启-开启.bat」。
echo.
pause
