@echo off
setlocal EnableExtensions
rem BI-Wizard logs: docker compose logs -f --tail=200 [service names]
rem Example: scripts\logs-local.bat backend superset    (stop with Ctrl+C)
rem Services: postgres, db-bootstrap, migrate, backend, frontend, superset-init, superset
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [FAIL] .env not found. Copy .env.example to .env and fill in the values.
    set "RC=1"
    goto :done
)

docker compose logs -f --tail=200 %*
if errorlevel 1 set "RC=1"

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
