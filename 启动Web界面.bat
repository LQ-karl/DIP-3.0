@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ===== DIP3.0 本地目录测算系统 - Web 界面启动器 =====
REM 定位脚本所在目录（项目根）
set "ROOT=%~dp0"
set "APP=%ROOT%web\app.py"

REM 使用 WorkBuddy 管理的 Python venv（含 streamlit）
set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

if not exist "%PY%" (
    echo [错误] 未找到 Python 虚拟环境：%PY%
    echo 请确认 WorkBuddy 已安装并在默认 venv 中安装了 streamlit。
    pause
    exit /b 1
)

if not exist "%APP%" (
    echo [错误] 未找到 Web 入口：%APP%
    pause
    exit /b 1
)

echo ============================================================
echo   DIP3.0 本地目录测算系统 - Web 界面启动
echo ============================================================
echo.
echo   正在启动 Web 服务...
echo   启动后请访问: http://localhost:8501
echo   按 Ctrl+C 停止服务
echo ------------------------------------------------------------

REM 延迟 3 秒后自动打开浏览器（等 streamlit 就绪）
start "" /min cmd /c "timeout /t 3 >nul && start http://localhost:8501"

"%PY%" -m streamlit run "%APP%" --server.port 8501 --server.headless true

endlocal
