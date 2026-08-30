@echo off
chcp 65001 >nul
REM ============================================
REM 五大联赛预测系统 · Windows 每日自动更新
REM 用法: 双击运行一次即可注册每日 09:30 自动任务
REM 日志: logs\auto_update.log
REM ============================================

set BASE=%~dp0..
set TASK_NAME=Top5PredictorDailyUpdate

REM 修改这里为你的 Python 路径（必须支持运行 auto_update.py）
set PYTHON=C:\Users\ASUS\.workbuddy\binaries\python\versions\3.13.12\python.exe

echo [1/3] 检查 Python...
if not exist "%PYTHON%" (
  echo     ❌ 未找到 Python: %PYTHON%
  echo     请编辑本脚本，将 PYTHON 变量改为你的 python.exe 路径
  pause
  exit /b 1
)

echo [2/3] 注册计划任务 %TASK_NAME% ...
schtasks /Create /F /TN "%TASK_NAME%" ^
  /SC DAILY /ST 09:30 ^
  /TR "cmd /c \"%PYTHON%\" \"%BASE%\scripts\auto_update.py\" --days 7 >> \"%BASE%\logs\auto_update.log\" 2>&1"

if errorlevel 1 (
  echo     ❌ 计划任务注册失败，请检查权限（可能需要管理员身份运行）
  pause
  exit /b 1
)

echo [3/3] 首次运行验证...
if not exist "%BASE%\logs" mkdir "%BASE%\logs"
"%PYTHON%" "%BASE%\scripts\auto_update.py" --days 7 >> "%BASE%\logs\auto_update.log" 2>&1

echo.
echo ✅ 已完成！每日 09:30 将自动: 拉取真实赛程 → 计算预测 → 更新看板
echo    查看任务: schtasks /Query /TN "%TASK_NAME%"
echo    查看日志: %BASE%\logs\auto_update.log
echo    提示: 在系统环境变量中设置 FOOTBALL_DATA_KEY 后即可拉取真实赛程
pause
