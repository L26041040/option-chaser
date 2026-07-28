@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "OC_PORT=8765"
set "OC_URL=http://127.0.0.1:%OC_PORT%"
set "APP_PASSWORD=option-chaser-local"

title Option Chaser

echo ============================================================
echo Option Chaser - One Click Launcher
echo ============================================================
echo URL      : %OC_URL%
echo Password : %APP_PASSWORD%
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

python -m streamlit version >nul 2>nul
if errorlevel 1 (
    echo ERROR: Streamlit is not installed in the current Python environment.
    echo Run: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

for /f "delims=" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %OC_PORT% -State Listen -ErrorAction SilentlyContinue).OwningProcess"') do (
    taskkill /PID %%P /F >nul 2>nul
)

start "" powershell -NoProfile -WindowStyle Hidden -Command "$u='%OC_URL%'; for($i=0; $i -lt 120; $i++){ try { $r=Invoke-WebRequest -Uri ($u+'/_stcore/health') -UseBasicParsing -TimeoutSec 1; if($r.StatusCode -eq 200){ Start-Process $u; exit 0 } } catch {}; Start-Sleep -Milliseconds 500 }; exit 1"

echo Starting Option Chaser...
echo The browser will open automatically.
echo Close this window or press Ctrl+C to stop the site.
echo.

python -m streamlit run webapp/app.py --server.address=127.0.0.1 --server.port=%OC_PORT% --server.headless=true --browser.gatherUsageStats=false
set "OC_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%OC_EXIT_CODE%"=="0" (
    echo Option Chaser stopped with exit code %OC_EXIT_CODE%.
    pause
)

exit /b %OC_EXIT_CODE%
