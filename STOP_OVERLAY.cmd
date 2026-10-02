@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-Telemetry.ps1"
if errorlevel 1 (
  echo.
  echo Stop failed. The process was left untouched.
  pause
) else (
  timeout /t 2 /nobreak >nul
)
endlocal
