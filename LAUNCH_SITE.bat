@echo off
setlocal
title CheapSkater Dashboard Launcher

echo.
echo ==========================================
echo    🚀 CheapSkater Dashboard Launcher
echo ==========================================
echo.

:: Check for virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\
    echo Please run launch.bat first to initialize the environment.
    echo.
    pause
    exit /b 1
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Set environment variables if needed
set "CHEAPSKATER_DB_PATH=orwa_lowes.sqlite"

:: Start the site in the browser
echo [INFO] Opening browser to http://localhost:9000...
start "" "http://localhost:9000"

:: Start the Dashboard Server
echo [INFO] Starting Dashboard server on port 9000...
echo [HINT] Press Ctrl+C to stop the server.
echo.

python -m uvicorn app.dashboard:app --host 0.0.0.0 --port 9000 --reload

echo.
echo [INFO] Dashboard stopped.
pause
