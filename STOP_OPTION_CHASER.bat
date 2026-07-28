@echo off
setlocal EnableExtensions

set "OC_PORT=8765"

echo Stopping Option Chaser on port %OC_PORT%...

for /f "delims=" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %OC_PORT% -State Listen -ErrorAction SilentlyContinue).OwningProcess"') do (
    taskkill /PID %%P /F >nul 2>nul
)

echo Stop command completed.
timeout /t 2 /nobreak >nul
exit /b 0
