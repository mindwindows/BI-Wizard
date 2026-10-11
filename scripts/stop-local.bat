@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem BI-Wizard 로컬 종료: docker compose down
rem 볼륨 삭제 옵션은 쓰지 않는다. 데이터(PostgreSQL 볼륨)는 유지된다.
cd /d "%~dp0.."
set "RC=0"

if not exist ".env" (
    echo [오류] .env 파일이 없어 docker compose 설정을 읽을 수 없습니다. .env 를 만든 뒤 다시 실행하세요.
    set "RC=1"
    goto :done
)

docker compose down
if errorlevel 1 (
    echo [오류] docker compose down 이 실패했습니다.
    set "RC=1"
    goto :done
)
echo 종료했습니다. 데이터 볼륨은 그대로 남아 있습니다.

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
