@echo off
set "TARGET=%~dp0啟動 Option Chaser.bat"
set "SHORTCUT=%USERPROFILE%\Desktop\啟動 Option Chaser.lnk"
powershell -NoProfile -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell; " ^
  "$Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); " ^
  "$Shortcut.TargetPath = '%TARGET%'; " ^
  "$Shortcut.WorkingDirectory = '%~dp0'; " ^
  "$Shortcut.Save()"
if exist "%SHORTCUT%" (
  echo 已在桌面建立捷徑：啟動 Option Chaser
) else (
  echo 建立捷徑失敗，請手動將「啟動 Option Chaser.bat」拖曳到桌面建立捷徑。
)
pause
