@echo off
setlocal
title BARIA
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch-app.ps1"
if errorlevel 1 (
    echo.
    echo No se ha podido iniciar BARIA. Revisa el mensaje anterior.
    pause
    exit /b 1
)
exit /b 0
