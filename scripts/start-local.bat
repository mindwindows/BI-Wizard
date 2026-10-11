@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem BI-Wizard 로컬 시작: docker compose up -d --build
rem 저장소 루트로 이동한다(어느 위치에서 실행해도 같게 동작한다).
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example 을 .env 로 복사한 뒤 비어 있는 Secret 값을 채우세요.
    set "RC=1"
    goto :done
)

docker compose up -d --build
if errorlevel 1 (
    echo [오류] docker compose up 이 실패했습니다. scripts\logs-local.bat 으로 로그를 확인하세요.
    set "RC=1"
    goto :done
)

docker compose ps
echo.
echo 시작 요청을 마쳤습니다. 상태 확인: scripts\health-check.bat

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
