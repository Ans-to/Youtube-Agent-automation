@echo off
setlocal
cd /d "%~dp0"
title Offline Agent HQ

if not exist "config.json" (
  if exist "config.example.json" (
    copy /Y "config.example.json" "config.json" >nul
    echo Created config.json from config.example.json.
  ) else (
    echo ERROR: config.example.json is missing.
    pause
    exit /b 1
  )
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'" >nul 2>nul
  if %errorlevel%==0 (
    py -3 dashboard.py
    goto :end
  )
)

where python >nul 2>nul
if %errorlevel%==0 (
  python -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'" >nul 2>nul
  if %errorlevel%==0 (
    python dashboard.py
    goto :end
  )
)

echo ERROR: Python 3.10 or newer was not found.
echo Run setup_windows.ps1 or install Python from https://www.python.org/downloads/windows/
pause
exit /b 1

:end
if not %errorlevel%==0 (
  echo Agent HQ exited with an error.
  pause
)
endlocal
