@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Codigo Rescate - Laptop

rem 1. Preferir el entorno virtual del proyecto.
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

rem 2. Si no hay venv, buscar un Python funcional con el lanzador py.
if not defined PY (
    py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
)
if not defined PY (
    py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
)
if not defined PY (
    py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo [ERROR] No se encontro un Python funcional.
    echo Instala Python 3.12 desde https://www.python.org/downloads/
    echo y despues ejecuta: scripts\instalar_laptop.ps1
    echo.
    pause
    exit /b 1
)

rem 3. Comprobar dependencias sin importar ultralytics (evita cargar torch).
%PY% -c "import importlib.util as u; assert all(u.find_spec(m) for m in ('tkinter','cv2','paho.mqtt.client','ultralytics'))" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Faltan dependencias para la GUI.
    echo Instaladas con: scripts\instalar_laptop.ps1
    echo.
    pause
    exit /b 1
)

rem 4. Arrancar la GUI y dejar el error visible si algo falla.
%PY% app_gui.py
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" (
    echo.
    echo [ERROR] La GUI termino con codigo %CODIGO%.
    pause
)
endlocal
