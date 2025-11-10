@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f %%a in ('echo prompt $E^| cmd') do set "ESC=%%a"
set "GREEN=!ESC![32m"
set "CYAN=!ESC![36m"
set "YELLOW=!ESC![33m"
set "RED=!ESC![31m"
set "RESET=!ESC![0m"

set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\launcher.log"

call :log "CheapSkater launcher starting"

where python >nul 2>nul
if errorlevel 1 (
    call :log "Python not found. Download from https://www.python.org/downloads/"
    echo Python 3.11+ is required. Download from https://www.python.org/downloads/
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    call :log "Python 3.11+ is required"
    echo Python 3.11+ is required. Download from https://www.python.org/downloads/
    exit /b 1
)

if not exist .venv (
    call :log "Creating virtual environment"
    python -m venv .venv >>"%LOG_FILE%" 2>&1
    if errorlevel 1 (
        call :log "Failed to create virtual environment"
        exit /b 1
    )
)

call "%~dp0.venv\Scripts\activate" >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "Failed to activate virtual environment"
    exit /b 1
)

call :run_cmd "Upgrading pip" "python -m pip install --upgrade pip"
if exist requirements.txt (
    call :run_cmd "Installing requirements" "python -m pip install -r requirements.txt"
)

call :run_cmd "Installing Playwright chromium" "python -m playwright install chromium"

if not exist catalog\building_materials.lowes.yml (
    call :run_cmd "Running category discovery" "python -m app.main --discover-categories"
)

if not exist catalog\wa_or_stores.yml (
    call :run_cmd "Running store discovery" "python -m app.main --discover-stores"
)

set "PROBE_FILE=%TEMP%\cheapskater_probe.json"
call :log "Running probe check"
python -m app.main --probe >"%PROBE_FILE%" 2>>"%LOG_FILE%"
if errorlevel 1 (
    call :log "Probe command failed"
    type "%PROBE_FILE%"
    del "%PROBE_FILE%" >nul 2>nul
    exit /b 1
)
python -c "import json, sys; json.load(open(sys.argv[1], encoding='utf-8'))" "%PROBE_FILE%"
if errorlevel 1 (
    call :log "Probe output is not valid JSON"
    type "%PROBE_FILE%"
    del "%PROBE_FILE%" >nul 2>nul
    exit /b 1
)
del "%PROBE_FILE%" >nul 2>nul

set "PY_BIN=%~dp0.venv\Scripts\python.exe"
if not exist "%PY_BIN%" set "PY_BIN=python"

call :start_process SCRAPER_PID "Running scraper" "%LOG_DIR%\scraper.log" "-m|app.main|--once"
call :start_process DASHBOARD_PID "Starting dashboard" "%LOG_DIR%\dashboard.log" "-m|uvicorn|app.dashboard:app|--host|0.0.0.0|--port|8000"

timeout /t 2 >nul
start "CheapSkater Dashboard" http://localhost:8000

:menu
    echo.
    echo !GREEN![R]!RESET! Re-run scrape   !CYAN![L]!RESET! View logs   !YELLOW![T]!RESET! Run tests   !RED![Q]!RESET! Quit
    set "CHOICE="
    set /p "CHOICE=Select option [R/L/T/Q]: "
    if /I "!CHOICE!"=="R" (
        call :start_process SCRAPER_PID "Re-running scraper" "%LOG_DIR%\scraper.log" "-m|app.main|--once"
        goto menu
    )
    if /I "!CHOICE!"=="L" (
        start "CheapSkater Logs" notepad.exe "%LOG_FILE%"
        goto menu
    )
    if /I "!CHOICE!"=="T" (
        call :run_cmd "Running full pipeline test" "\"%PY_BIN%\" test_full_pipeline.py"
        goto menu
    )
    if /I "!CHOICE!"=="Q" goto quit
    echo Invalid option.
    goto menu

:quit
call :cleanup_process "SCRAPER" !SCRAPER_PID!
call :cleanup_process "DASHBOARD" !DASHBOARD_PID!
call :log "Launcher exiting"
exit /b 0

:run_cmd
set "DESC=%~1"
set "CMD=%~2"
call :log "%DESC%"
>>"%LOG_FILE%" echo [%DATE% %TIME%] CMD: %CMD%
cmd /c %CMD% >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "%DESC% failed"
    exit /b 1
)
exit /b 0

:start_process
set "VAR=%~1"
set "DESC=%~2"
set "LOGPATH=%~3"
set "ARGSTRING=%~4"
call :log "%DESC%"
set "%VAR%="
set "SAFE_LOG=%LOGPATH:'='''%"
set "SAFE_ARGS=%ARGSTRING:'='''%"
>>"%LOG_FILE%" echo [%DATE% %TIME%] Starting %DESC% with args: %ARGSTRING%
for /f "usebackq tokens=* delims=" %%P in (`powershell -NoProfile -Command "$log = '%SAFE_LOG%'; if (-not (Test-Path $log)) { New-Item -ItemType File -Path $log -Force | Out-Null }; $exe = '%PY_BIN%'; $args = '%SAFE_ARGS%'.Split('|'); $proc = Start-Process -FilePath $exe -ArgumentList $args -RedirectStandardOutput $log -RedirectStandardError $log -PassThru; $proc.Id"`) do (
    set "%VAR%=%%P"
)
if not defined %VAR% (
    call :log "%DESC% failed to start"
    exit /b 1
)
exit /b 0

:cleanup_process
set "NAME=%~1"
set "PID=%~2"
if "%PID%"=="" exit /b 0
call :log "Stopping %NAME% (pid=%PID%)"
powershell -NoProfile -Command "if (Get-Process -Id %PID% -ErrorAction SilentlyContinue) { Stop-Process -Id %PID% -Force }" >nul 2>&1
exit /b 0

:log
set "MESSAGE=%~1"
echo [%DATE% %TIME%] %MESSAGE%
>>"%LOG_FILE%" echo [%DATE% %TIME%] %MESSAGE%
exit /b 0
