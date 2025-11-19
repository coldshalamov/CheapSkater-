@echo off
setlocal EnableDelayedExpansion

REM Flatten the repository into flatten_repo.txt using PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flatten_repo.ps1" %*

if errorlevel 1 (
    echo Flattening failed. See output above for details.
    exit /b 1
)

echo Flattening complete.
exit /b 0
