@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem BI-Wizard 로그 보기: docker compose logs -f --tail=200 [서비스 이름...]
rem 예: scripts\logs-local.bat backend superset   (종료: Ctrl+C)
rem 서비스: postgres, db-bootstrap, migrate, backend, frontend, superset-init, superset
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example 을 .env 로 복사한 뒤 값을 채우세요.
    set "RC=1"
    goto :done
)

docker compose logs -f --tail=200 %*
if errorlevel 1 set "RC=1"

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
