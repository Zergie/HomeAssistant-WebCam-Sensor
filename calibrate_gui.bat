@echo off
setlocal
cd /d "%~dp0"

rem Load an unquoted RTSP_URL=value from .env if it is not already set.
if not defined RTSP_URL if exist ".env" (
    for /f "usebackq tokens=1,* delims== eol=#" %%A in (".env") do (
        if /i "%%A"=="RTSP_URL" set "RTSP_URL=%%B"
    )
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "calibrate_gui.py" %*
) else (
    python "calibrate_gui.py" %*
)

if errorlevel 1 (
    echo.
    echo Calibration could not start. See the error above.
    pause
    exit /b 1
)
