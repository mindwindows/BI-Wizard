@echo off
setlocal EnableExtensions
rem BI-Wizard local stop: docker compose down
rem No volume-removal option is used. PostgreSQL data stays in the Docker volume.
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [FAIL] .env not found. docker compose cannot read its configuration without it.
    set "RC=1"
    goto :done
)

docker compose down
if errorlevel 1 (
    echo [FAIL] docker compose down failed.
    set "RC=1"
    goto :done
)
echo [OK] Stopped. The data volume is kept.

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
