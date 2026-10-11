@echo off
setlocal EnableExtensions
rem .env check: every variable name in .env.example must exist in .env with a non-empty value.
rem Only names are printed. Values are never printed.
rem APP_BASE_PATH is the only variable allowed to be empty (root deployment).
cd /d "%~dp0.."
set "RC=0"
set /a MISSING=0
set /a EMPTY=0

if not exist ".env.example" (
    echo [FAIL] .env.example not found.
    set "RC=1"
    goto :done
)
if not exist ".env" (
    echo [FAIL] .env not found. Copy .env.example to .env and fill in the values.
    set "RC=1"
    goto :done
)

for /f "usebackq tokens=1 delims==" %%N in (`findstr /b /r /c:"[A-Za-z_][A-Za-z0-9_]*=" ".env.example"`) do call :checkname %%N

echo.
if %MISSING% GTR 0 set "RC=1"
if %EMPTY% GTR 0 set "RC=1"
if "%RC%"=="0" (
    echo [OK] .env check passed: all variable names exist and have values.
) else (
    echo [FAIL] .env check failed: %MISSING% missing, %EMPTY% empty. Fix the names listed above in .env.
)
goto :done

:checkname
findstr /b /c:"%~1=" ".env" >nul 2>&1
if errorlevel 1 (
    echo [MISSING] %~1
    set /a MISSING+=1
    exit /b 0
)
if /i "%~1"=="APP_BASE_PATH" exit /b 0
findstr /b /r /c:"%~1=$" ".env" >nul 2>&1
if not errorlevel 1 (
    echo [EMPTY] %~1
    set /a EMPTY+=1
)
exit /b 0

:done
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
