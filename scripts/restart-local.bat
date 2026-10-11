@echo off
setlocal EnableExtensions
rem BI-Wizard local restart: down, then up -d --build
rem Also use this after editing .env (for example APP_PROXY_STRIP_PREFIX). No volume-removal option is used.
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [FAIL] .env not found. Copy .env.example to .env and fill in the empty secret values.
    set "RC=1"
    goto :done
)

docker compose down
if errorlevel 1 (
    echo [FAIL] docker compose down failed.
    set "RC=1"
    goto :done
)

docker compose up -d --build
if errorlevel 1 (
    echo [FAIL] docker compose up failed. Run scripts\logs-local.bat to see the logs.
    set "RC=1"
    goto :done
)

docker compose ps
echo.
echo [OK] Restart requested. Next: scripts\health-check.bat

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
