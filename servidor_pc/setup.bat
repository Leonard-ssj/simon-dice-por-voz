@echo off
:: ============================================================
:: setup.bat -- Crea el entorno virtual e instala dependencias
:: Ejecutar UNA SOLA VEZ despues de clonar el repositorio.
::
:: Uso:
::   cd servidor_pc
::   setup.bat
:: ============================================================

echo.
echo  Simon Dice por Voz -- Setup del servidor PC
echo  ============================================

:: Verificar que Python este instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python no encontrado.
    echo  Instalar Python 3.10+ desde https://python.org
    echo  Marcar "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

echo.
echo  [1/3] Creando entorno virtual en .venv ...
python -m venv .venv
if errorlevel 1 (
    echo  [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)
echo  OK

echo.
echo  [2/3] Instalando dependencias (puede tardar 2-5 min la primera vez) ...
.venv\Scripts\pip install --upgrade pip --quiet
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo la instalacion de dependencias.
    echo  Verificar conexion a internet e intentar de nuevo.
    pause
    exit /b 1
)
echo  OK

echo.
echo  [3/3] Verificando instalacion ...
.venv\Scripts\python -c "import whisper, serial, websockets, numpy; print('  Todos los modulos OK')"
if errorlevel 1 (
    echo  [ADVERTENCIA] Algunos modulos no se importaron correctamente.
    echo  Revisar errores arriba.
)

echo.
echo  ============================================
echo  Setup completado.
echo.
echo  Para correr el servidor:
echo    .venv\Scripts\python servidor.py
echo.
echo  O usar el script de inicio:
echo    iniciar.bat
echo  ============================================
echo.
pause
