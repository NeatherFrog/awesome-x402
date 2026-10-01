@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3 launch.py %*
goto finished
:python_fallback
where python >nul 2>nul
if errorlevel 1 goto python_missing
python launch.py %*
goto finished
:python_missing
echo Python 3.11 or newer is required. Install it from https://www.python.org/downloads/
echo Enable "Add python.exe to PATH" during installation, then start this file again.
pause
exit /b 1
:finished
set "TRADING_EXIT_CODE=%ERRORLEVEL%"
if not "%TRADING_EXIT_CODE%"=="0" pause
exit /b %TRADING_EXIT_CODE%
