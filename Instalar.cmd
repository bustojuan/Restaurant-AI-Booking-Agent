@echo off
setlocal
title BARIA - Instalacion
cd /d "%~dp0"
echo.
echo BARIA - Instalacion inicial
echo Se requiere conexion a Internet, Node.js 24 LTS y uv.
echo Este proceso puede tardar varios minutos.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 (
    echo.
    echo No se ha completado la instalacion. Revisa el mensaje anterior.
    echo Consulta INSTALLATION.md para instalar los requisitos.
    pause
    exit /b 1
)
echo.
echo Instalacion completada. Abre "Iniciar BARIA.cmd" para usar la aplicacion.
pause
exit /b 0
