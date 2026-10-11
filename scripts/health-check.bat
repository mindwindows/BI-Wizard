@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem BI-Wizard Health Check: 브라우저와 같은 경로로 frontend nginx 를 거쳐 확인한다.
rem   ${APP_BASE_PATH}/                 포털 정적 페이지
rem   ${APP_BASE_PATH}/api/health       FastAPI 상태
rem   ${APP_BASE_PATH}/api/health/db    PostgreSQL 연결
rem   ${SUPERSET_APP_ROOT}/health       Superset
rem APP_PROXY_STRIP_PREFIX 값과 상관없이 같은 주소(브라우저 쪽 경로)를 쓴다.
rem .env 에서는 아래 세 이름의 줄만 읽는다. Secret 줄은 읽지 않는다.
cd /d "%~dp0.."
set "RC=0"
set "FAILED=0"

if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example 을 .env 로 복사한 뒤 값을 채우세요.
    set "RC=1"
    goto :done
)

set "FRONTEND_PORT="
set "APP_BASE_PATH="
set "SUPERSET_APP_ROOT="
for /f "usebackq delims=" %%L in (`findstr /b /c:"FRONTEND_PORT=" /c:"APP_BASE_PATH=" /c:"SUPERSET_APP_ROOT=" ".env"`) do set "%%L"
rem 값이 따옴표로 감싸여 있으면 따옴표를 뗀다(정의된 변수만 처리한다).
if defined FRONTEND_PORT set "FRONTEND_PORT=%FRONTEND_PORT:"=%"
if defined APP_BASE_PATH set "APP_BASE_PATH=%APP_BASE_PATH:"=%"
if defined SUPERSET_APP_ROOT set "SUPERSET_APP_ROOT=%SUPERSET_APP_ROOT:"=%"

if not defined FRONTEND_PORT (
    echo [오류] .env 에 FRONTEND_PORT 가 없습니다.
    set "RC=1"
    goto :done
)

set "ORIGIN=http://localhost:%FRONTEND_PORT%"
echo 확인 대상: %ORIGIN%%APP_BASE_PATH%/
echo.

call :check "포털 정적 페이지" "%ORIGIN%%APP_BASE_PATH%/"
call :check "API /health" "%ORIGIN%%APP_BASE_PATH%/api/health"
call :check "API /health/db PostgreSQL 연결" "%ORIGIN%%APP_BASE_PATH%/api/health/db"
call :check "Superset /health" "%ORIGIN%%SUPERSET_APP_ROOT%/health"

echo.
docker compose ps

if "%FAILED%"=="1" (
    echo.
    echo 실패한 항목이 있습니다. scripts\logs-local.bat 으로 로그를 확인하세요.
    set "RC=1"
) else (
    echo.
    echo 모든 확인이 정상입니다.
)
goto :done

:check
curl.exe -fsS -m 10 -o NUL "%~2" >NUL 2>&1
if errorlevel 1 (
    echo [실패] %~1  %~2
    set "FAILED=1"
) else (
    echo [정상] %~1
)
exit /b 0

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
