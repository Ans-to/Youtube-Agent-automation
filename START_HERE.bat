@echo off
setlocal
cd /d "%~dp0"
title Offline Agent HQ - One-click setup
echo.
echo ============================================================
echo  OFFLINE AGENT HQ - ONE-CLICK WINDOWS SETUP
echo ============================================================
echo This installs missing free prerequisites, checks the project,
echo installs the video renderer, and then opens the dashboard.
echo Internet is needed for initial installs and optional model setup.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_all_windows.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not finish. Read the error above.
  pause
  exit /b 1
)
endlocal
