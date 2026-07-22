@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist logs mkdir logs
set "LOGFILE=logs\launch-%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2%.log"
set "LOGFILE=%LOGFILE: =0%"

echo Option Chaser 啟動中... > "%LOGFILE%"

rem --- Step 1: 找 Python ---
rem 全程用 !errorlevel!（延遲展開，已於檔首 setlocal enabledelayedexpansion）：
rem %errorlevel% 在整個 if/else 括號區塊於解析當下就被展開成同一個值，內層
rem 對 python --version 的判斷會誤讀外層 py -3 的舊值——這是已知的 batch 陷阱，
rem 全部改用 !errorlevel! 才能讓每個判斷讀到「當下」剛執行完命令的真實結果。
set "PYCMD="
py -3 --version >nul 2>&1
if !errorlevel!==0 (
  set "PYCMD=py -3"
) else (
  python --version >nul 2>&1
  if !errorlevel!==0 (
    set "PYCMD=python"
  )
)
if "%PYCMD%"=="" (
  echo 找不到 Python。>> "%LOGFILE%"
  echo 找不到 Python。
  echo 請先安裝 Python 3.11 以上版本：https://www.python.org/downloads/
  pause
  exit /b 1
)
rem 找到指令不代表版本足夠——實際檢查 >= 3.11（spec §10.2「版本 <3.11...」）
%PYCMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo 已安裝的 Python 版本過舊。>> "%LOGFILE%"
  echo 已安裝的 Python 版本過舊。
  echo 請先安裝 Python 3.11 以上版本：https://www.python.org/downloads/
  pause
  exit /b 1
)
echo 使用 Python: %PYCMD% >> "%LOGFILE%"

rem --- Step 2: 建立 / 使用 .venv ---
set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo 首次啟動，正在安裝必要元件（約 2-3 分鐘，僅此一次）...... >> "%LOGFILE%"
  echo 首次啟動，正在安裝必要元件（約 2-3 分鐘，僅此一次）......
  %PYCMD% -m venv .venv >> "%LOGFILE%" 2>&1
  if not exist "%VENV_PY%" (
    echo 建立虛擬環境失敗，詳見 %LOGFILE%
    pause
    exit /b 1
  )
  "%VENV_PY%" -m pip install -e ".[gui]" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo 安裝必要元件失敗，詳見 %LOGFILE%
    pause
    exit /b 1
  )
)

rem --- Step 3: 依賴健檢 ---
"%VENV_PY%" -c "import streamlit, option_chaser, webapp" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo 元件檢查失敗，正在重新安裝......>> "%LOGFILE%"
  "%VENV_PY%" -m pip install -e ".[gui]" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo 元件安裝失敗，詳見 %LOGFILE%
    pause
    exit /b 1
  )
)

rem --- Step 4: Port 8501 檢查（身分驗證） ---
set "LOCK=logs\running.lock"
"%VENV_PY%" -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=2)" >nul 2>&1
if %errorlevel%==0 (
  if exist "%LOCK%" (
    set /p LOCKPID=<"%LOCK%"
    tasklist /fi "PID eq !LOCKPID!" 2>nul | find "!LOCKPID!" >nul
    if !errorlevel!==0 (
      echo Option Chaser 已在執行，為你開啟瀏覽器。
      start http://localhost:8501
      exit /b 0
    )
  )
  echo 連接埠 8501 上有其他 Streamlit 程式，請關閉後重試。
  pause
  exit /b 1
)

rem --- Step 5: 取得本行程 PID 寫入 lock，再啟動（非 headless，瀏覽器由
rem     Streamlit 原生自動開啟）。PID 取得法：設一個本次執行獨有的視窗標題，
rem     用 tasklist /v 依標題反查 PID——不依賴 wmic（Windows 11 起預設移除）或
rem     PowerShell，純 batch 內建指令，相容性最佳。 ---
set "UNIQUE_TITLE=OptionChaserLauncher_%RANDOM%%RANDOM%"
title %UNIQUE_TITLE%
set "SELFPID="
for /f "tokens=2 delims=," %%P in ('tasklist /v /fo csv /nh ^| findstr /i "%UNIQUE_TITLE%"') do set "SELFPID=%%~P"
if not "%SELFPID%"=="" echo %SELFPID%> "%LOCK%"

echo Option Chaser 啟動中，請稍候瀏覽器自動開啟......
"%VENV_PY%" -m streamlit run webapp\app.py --server.port 8501
del "%LOCK%" 2>nul
