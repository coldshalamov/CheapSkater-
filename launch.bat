@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM === CheapSkater Windows Launcher (looping) ===
set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f "tokens=1-3 delims=/: " %%a in ("%TIME%") do set "h=%%a" & set "m=%%b" & set "s=%%c"
set "h=%h: =0%"
set "timestamp=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%h%%m%%s:~0,2%"
set "LOG_FILE=%LOG_DIR%\launcher_%timestamp%.log"

echo.
echo [CheapSkater launcher starting]
echo [Logs will go to %LOG_FILE%]
echo.

:run_scraper

REM --- Preserve cursor/probe so the queue resumes where it left off ---
REM (no deletion here)

REM --- Create venv if missing ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv .venv || (echo Venv creation failed! & pause & exit /b 1)
)

REM --- Activate venv ---
call ".venv\Scripts\activate.bat" || (echo Activation failed! & pause & exit /b 1)

REM --- Install deps ---
echo Upgrading pip...
python -m pip install -U pip >>"%LOG_FILE%" 2>&1
echo Installing requirements...
pip install -r requirements.txt >>"%LOG_FILE%" 2>&1
echo Installing Playwright Chromium...
python -m playwright install chromium >>"%LOG_FILE%" 2>&1

REM --- Disable selector preflight sanity-check ---
set "CHEAPSKATER_SKIP_PREFLIGHT=1"
set "CHEAPSKATER_HEADLESS=0"
set "CHEAPSKATER_STEALTH=1"
set "CHEAPSKATER_WAIT_MULTIPLIER=1.15"
set "CHEAPSKATER_CATEGORY_DELAY_MIN_MS=1800"
set "CHEAPSKATER_CATEGORY_DELAY_MAX_MS=4200"
set "CHEAPSKATER_ZIP_DELAY_MIN_MS=6000"
set "CHEAPSKATER_ZIP_DELAY_MAX_MS=14000"
set "CHEAPSKATER_MOUSE_JITTER=1"
set "CHEAPSKATER_SLOW_MO_MS=16"
set "CHEAPSKATER_BROWSER_ZIP_LIMIT=1"
set "LOG_LEVEL=INFO"
set "SCRAPER_ARGS=--concurrency 1"

REM --- Optional ZIP override ---
set "EXTRA_ARGS="
if not "%~1"=="" (
    set "EXTRA_ARGS=--zip %~1"
)

REM --- Dashboard (background) ---
set "DASHBOARD_LOG=%LOG_DIR%\dashboard_%timestamp%.log"
echo Launching dashboard server ^(logs -> %DASHBOARD_LOG%^)... 
start "CheapSkater Dashboard" cmd /c ""%CD%\.venv\Scripts\python.exe" -m uvicorn app.dashboard:app --host 0.0.0.0 --port 8000 >> "%DASHBOARD_LOG%" 2>&1"
timeout /t 3 >nul
start "" "http://localhost:8000" >nul 2>&1

REM --- Probe (no cache) ---
echo Running probe %EXTRA_ARGS% (no cache)...
python -m app.main --probe --probe-cache-minutes 0 %SCRAPER_ARGS% %EXTRA_ARGS% >>"%LOG_FILE%" 2>&1
set "PROBE_EXIT=%ERRORLEVEL%"
if not "%PROBE_EXIT%"=="0" (
    echo Probe failed (exit %PROBE_EXIT%). See %LOG_FILE% for details; continuing...
) else (
    echo Probe succeeded.
)

REM --- Scraper (loop forever) ---
echo Launching scraper (Ctrl+C to stop)...
python -m app.main %SCRAPER_ARGS% %EXTRA_ARGS% >>"%LOG_FILE%" 2>&1
set "SCRAPER_EXIT=%ERRORLEVEL%"
echo Scraper exited with code %SCRAPER_EXIT%. Restarting in 10 seconds...
timeout /t 10 >nul
goto :run_scraper
