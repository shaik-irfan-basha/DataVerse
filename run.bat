@echo off
setlocal
title DataVerse - AI Data Studio
color 0B
cls

echo =====================================================================
echo                 DATAVERSE - AI DATA STUDIO
echo =====================================================================
echo.

cd /d "%~dp0"
set DATAVERSE_ALLOW_SERVER_ENV_KEY=true

:: Check if Python is installed on PATH
python --version >nul 2>&1
if errorlevel 1 goto :no_python

:: Dispatch based on first command-line argument
if /i "%~1"=="--desktop" goto :launch_desktop
if /i "%~1"=="-d" goto :launch_desktop
if /i "%~1"=="--legacy" goto :launch_legacy
if /i "%~1"=="--legacy-desktop" goto :launch_legacy
if /i "%~1"=="--browser" goto :launch_browser
if /i "%~1"=="--web" goto :launch_browser
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
if /i "%~1"=="--check" goto :check_only
if not "%~1"=="" goto :unknown_arg

:: Default mode (no arguments): Launch Web Studio in browser
goto :launch_browser

:launch_desktop
echo [*] Launching DataVerse Desktop Studio [WebView2]...
python desktop_app.py %*
exit /b %errorlevel%

:launch_legacy
echo [*] Launching DataVerse Desktop [CustomTkinter Fallback]...
python main.py
exit /b %errorlevel%

:launch_browser
:: Check if port 8000 is already active
python -c "import socket, sys; s = socket.socket(); res = s.connect_ex(('127.0.0.1', 8000)); s.close(); sys.exit(0 if res == 0 else 1)" >nul 2>&1
if %errorlevel% equ 0 goto :server_already_active

echo [*] Starting DataVerse Neon Studio on http://127.0.0.1:8000 ...
echo [*] Launching your web browser automatically...
echo.

:: Launch browser in background after 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000/"

:: Start Uvicorn server
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%

:server_already_active
echo [OK] DataVerse server is already active on http://127.0.0.1:8000/
echo [OK] Opening in your default browser...
start http://127.0.0.1:8000/
ping -n 3 127.0.0.1 >nul
exit /b 0

:check_only
echo [OK] Environment check passed.
echo [OK] Working directory: %CD%
python --version
exit /b 0

:no_python
echo [ERROR] Python was not found on your system PATH.
echo Please install Python 3.10+ from python.org and add it to PATH.
echo.
pause
exit /b 1

:show_help
echo DataVerse Launcher Usage:
echo   run.bat                 Launch Web Studio in default browser (default)
echo   run.bat --desktop       Launch native Desktop Studio (WebView2)
echo   run.bat --legacy        Launch CustomTkinter desktop fallback
echo   run.bat --check         Check environment without launching
echo   run.bat --help          Show this help message
echo.
exit /b 0

:unknown_arg
echo [WARNING] Unrecognized argument: %~1
echo.
goto :show_help
