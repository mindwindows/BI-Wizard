@echo off
setlocal EnableExtensions
rem BI-Wizard health check. Uses the same paths as the browser, through the frontend nginx.
rem   ${APP_BASE_PATH}/                 portal page
rem   ${APP_BASE_PATH}/api/health       FastAPI
rem   ${APP_BASE_PATH}/api/health/db    PostgreSQL connection
rem   ${SUPERSET_APP_ROOT}/health       Superset
rem The same URLs are used whatever APP_PROXY_STRIP_PREFIX is (browser-side paths).
rem Only the three names below are read from .env. Secret lines are never read.
cd /d "%~dp0.."
set "RC=0"
set "FAILED=0"

if not exist ".env" (
    echo [FAIL] .env not found. Copy .env.example to .env and fill in the values.
    set "RC=1"
    goto :done
)

set "FRONTEND_PORT="
set "APP_BASE_PATH="
set "SUPERSET_APP_ROOT="
for /f "usebackq delims=" %%L in (`findstr /b /c:"FRONTEND_PORT=" /c:"APP_BASE_PATH=" /c:"SUPERSET_APP_ROOT=" ".env"`) do set "%%L"
rem Strip surrounding double quotes (only for variables that are defined).
if defined FRONTEND_PORT set "FRONTEND_PORT=%FRONTEND_PORT:"=%"
if defined APP_BASE_PATH set "APP_BASE_PATH=%APP_BASE_PATH:"=%"
if defined SUPERSET_APP_ROOT set "SUPERSET_APP_ROOT=%SUPERSET_APP_ROOT:"=%"

if not defined FRONTEND_PORT (
    echo [FAIL] FRONTEND_PORT is missing in .env.
    set "RC=1"
    goto :done
)

set "ORIGIN=http://localhost:%FRONTEND_PORT%"
echo Target: %ORIGIN%%APP_BASE_PATH%/
echo.

call :check "portal page" "%ORIGIN%%APP_BASE_PATH%/"
call :check "API /health" "%ORIGIN%%APP_BASE_PATH%/api/health"
call :check "API /health/db PostgreSQL" "%ORIGIN%%APP_BASE_PATH%/api/health/db"
call :check "Superset /health" "%ORIGIN%%SUPERSET_APP_ROOT%/health"

echo.
docker compose ps

if "%FAILED%"=="1" (
    echo.
    echo [FAIL] Some checks failed. Run scripts\logs-local.bat to see the logs.
    set "RC=1"
) else (
    echo.
    echo [OK] All checks passed.
)
goto :done

:check
curl.exe -fsS -m 10 -o NUL "%~2" >NUL 2>&1
if errorlevel 1 (
    echo [FAIL] %~1  %~2
    set "FAILED=1"
) else (
    echo [OK] %~1
)
exit /b 0

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
