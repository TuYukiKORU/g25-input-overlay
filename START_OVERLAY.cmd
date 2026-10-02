@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-Telemetry.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. See .runtime\server.err.log for details.
  pause
)
endlocal
