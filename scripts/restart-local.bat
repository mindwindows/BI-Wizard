@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem BI-Wizard 로컬 재시작: down 후 up -d --build
rem .env 값(예: APP_PROXY_STRIP_PREFIX)을 바꾼 뒤 반영할 때도 쓴다. 볼륨 삭제 옵션은 쓰지 않는다.
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example 을 .env 로 복사한 뒤 비어 있는 Secret 값을 채우세요.
    set "RC=1"
    goto :done
)

docker compose down
if errorlevel 1 (
    echo [오류] docker compose down 이 실패했습니다.
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
echo 재시작 요청을 마쳤습니다. 상태 확인: scripts\health-check.bat

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
