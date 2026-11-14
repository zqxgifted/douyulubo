@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 正在启动 斗鱼录播工具箱 GUI...
python gui\app.py
if errorlevel 1 (
  echo.
  echo 启动失败。请确认已安装 Python 3.9+ 且包含 tkinter，以及 Node.js 18+。
  pause
)
