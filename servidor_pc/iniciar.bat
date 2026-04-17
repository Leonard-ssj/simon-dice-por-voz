@echo off
:: ============================================================
:: iniciar.bat -- Activa el venv y corre el servidor
::
:: Uso:
::   cd servidor_pc
::   iniciar.bat
:: ============================================================

:: Verificar que el venv exista
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] Entorno virtual no encontrado.
    echo  Ejecutar primero: setup.bat
    echo.
    pause
    exit /b 1
)

echo.
echo  Activando entorno virtual...
call .venv\Scripts\activate.bat

echo  Iniciando servidor Simon Dice...
echo.
python servidor.py

:: Si el servidor termina con error, mostrar pausa para ver el mensaje
if errorlevel 1 (
    echo.
    echo  El servidor termino con error. Revisar mensajes arriba.
    pause
)
