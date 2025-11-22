@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM === CheapSkater Windows Launcher ===
set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f "tokens=1-3 delims=/: " %%a in ("%TIME%") do set "h=%%a" & set "m=%%b" & set "s=%%c"
set "h=%h: =0%"
set "timestamp=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%h%%m%%s:~0,2%"
set "LOG_FILE=%LOG_DIR%\launcher_%timestamp%.log"

echo.
echo [CheapSkater launcher (no-preflight) starting]
echo [Logs will go to %LOG_FILE%]
echo.

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

REM --- Create minimal ZIP list so discovery step is skipped ---
if not exist "catalog\wa_or_stores.yml" (
    echo Seeding catalog\wa_or_stores.yml...
    powershell -NoProfile -Command ^
      "$p='catalog/wa_or_stores.yml';" ^
      "[IO.Directory]::CreateDirectory((Split-Path $p))|Out-Null;" ^
      "$y=@('zips:','- 98101','- 97201') -join [Environment]::NewLine;" ^
      "Set-Content -LiteralPath $p -Value $y -Encoding UTF8" >>"%LOG_FILE%" 2>&1
)

REM --- Disable selector preflight sanity-check ---
set "CHEAPSKATER_SKIP_PREFLIGHT=1"
set "CHEAPSKATER_HEADLESS=0"
set "CHEAPSKATER_STEALTH=1"
set "CHEAPSKATER_WAIT_MULTIPLIER=0.85"
set "CHEAPSKATER_CATEGORY_DELAY_MIN_MS=900"
set "CHEAPSKATER_CATEGORY_DELAY_MAX_MS=1900"
set "CHEAPSKATER_ZIP_DELAY_MIN_MS=3000"
set "CHEAPSKATER_ZIP_DELAY_MAX_MS=7000"
set "CHEAPSKATER_MOUSE_JITTER=1"
set "CHEAPSKATER_SLOW_MO_MS=0"
set "CHEAPSKATER_USER_DATA_DIR=none"
set "CHEAPSKATER_BROWSER_ZIP_LIMIT=0"
set "CHEAPSKATER_CHROMIUM_ARGS=--disable-blink-features=AutomationControlled --disable-dev-shm-usage --lang=en-US --no-default-browser-check --window-size=1440,960"
set "LOG_LEVEL=INFO"

REM --- Optional ZIP override ---
set "EXTRA_ARGS=--concurrency 1"
if not "%~1"=="" (
    set "EXTRA_ARGS=%EXTRA_ARGS% --zip %~1"
)
REM --- Optional proxy: set CHEAPSKATER_PROXY before launch, e.g.
REM set "CHEAPSKATER_PROXY=http://user:pass@host:port"

set "DASHBOARD_LOG=%LOG_DIR%\dashboard_%timestamp%.log"
echo Launching dashboard server ^(logs -> %DASHBOARD_LOG%^)... 
start "CheapSkater Dashboard" cmd /c ""%CD%\.venv\Scripts\python.exe" -m uvicorn app.dashboard:app --host 0.0.0.0 --port 8000 >> "%DASHBOARD_LOG%" 2>&1"
timeout /t 3 >nul
if /i not "%CHEAPSKATER_SKIP_DASHBOARD_OPEN%"=="1" (
    start "" "http://localhost:8000" >nul 2>&1
)

REM --- Start scraper (Ctrl+C to stop) ---
echo Launching scraper (full run, no probe) %EXTRA_ARGS% ...
python -m app.main %EXTRA_ARGS% >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Scraper run failed! Check %LOG_FILE%
    pause
    exit /b 1
)

echo.
echo ================================
echo ✅  CheapSkater finished OK
echo ================================
echo Logs: %LOG_FILE%
pause
exit /b 0
