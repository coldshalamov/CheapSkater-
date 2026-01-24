@echo off
REM Test SendGrid Integration Script
REM Usage: test-sendgrid.bat [SENDGRID_API_KEY] [SENDGRID_FROM]
REM
REM If API key is not provided, it will use the SENDGRID_API_KEY environment variable

setlocal enabledelayedexpansion

echo.
echo ========================================
echo SendGrid Integration Test Launcher
echo ========================================
echo.

REM Set API key if provided as argument
if not "%1"=="" (
    set SENDGRID_API_KEY=%1
    echo Using provided API key
) else (
    if "!SENDGRID_API_KEY!"=="" (
        echo ERROR: No SendGrid API key provided!
        echo.
        echo Usage:
        echo   test-sendgrid.bat ^<API_KEY^> [SENDER_EMAIL]
        echo.
        echo Or set environment variable:
        echo   set SENDGRID_API_KEY=SG.your_key_here
        echo   test-sendgrid.bat
        echo.
        exit /b 1
    ) else (
        echo Using SENDGRID_API_KEY environment variable
    )
)

REM Set sender email if provided
if not "%2"=="" (
    set SENDGRID_FROM=%2
) else (
    set SENDGRID_FROM=deals@gloorbot.com
)

if not exist "cheapskater.db" (
    echo WARNING: cheapskater.db not found in current directory
    echo The script may fail if the database doesn't exist
    echo.
    pause
)

echo.
echo Configuration:
echo   API Key: %SENDGRID_API_KEY:~0,10%... (hidden)
echo   From: %SENDGRID_FROM%
echo   To: rob@redhatfunding.com
echo.
echo Running test script...
echo.

python scripts/test_sendgrid_flow.py

pause
