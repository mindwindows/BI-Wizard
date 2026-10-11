@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem .env 검증: .env.example 에 있는 변수 이름이 .env 에 모두 있는지, 값이 비어 있지 않은지 확인한다.
rem 이름만 출력하고 값은 절대 출력하지 않는다.
rem APP_BASE_PATH, SUPERSET_APP_ROOT 는 루트 배포일 때 빈 값이 정상이므로 빈 값 검사에서 제외한다.
cd /d "%~dp0.."
set "RC=0"
set /a MISSING=0
set /a EMPTY=0

if not exist ".env.example" (
    echo [오류] .env.example 이 없습니다.
    set "RC=1"
    goto :done
)
if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example 을 .env 로 복사한 뒤 값을 채우세요.
    set "RC=1"
    goto :done
)

for /f "usebackq tokens=1 delims==" %%N in (`findstr /b /r /c:"[A-Za-z_][A-Za-z0-9_]*=" ".env.example"`) do call :checkname %%N

echo.
if %MISSING% GTR 0 set "RC=1"
if %EMPTY% GTR 0 set "RC=1"
if "%RC%"=="0" (
    echo .env 검증 통과: 모든 변수 이름이 있고 값이 채워져 있습니다.
) else (
    echo .env 검증 실패: 누락 %MISSING% 개, 빈 값 %EMPTY% 개. 위 이름을 .env 에서 채우세요.
)
goto :done

:checkname
findstr /b /c:"%~1=" ".env" >nul 2>&1
if errorlevel 1 (
    echo [누락] %~1
    set /a MISSING+=1
    exit /b 0
)
if /i "%~1"=="APP_BASE_PATH" exit /b 0
if /i "%~1"=="SUPERSET_APP_ROOT" exit /b 0
findstr /b /r /c:"%~1=$" ".env" >nul 2>&1
if not errorlevel 1 (
    echo [빈 값] %~1
    set /a EMPTY+=1
)
exit /b 0

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
