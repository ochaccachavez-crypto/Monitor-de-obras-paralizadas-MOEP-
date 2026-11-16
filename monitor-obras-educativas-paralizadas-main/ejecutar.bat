@echo off
rem Ejecuta TODO el proyecto (descargas, tablas, proyecto PDF e inventario). Doble clic o: ejecutar.bat --fuentes escale,enla  |  ejecutar.bat --sin-descarga
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creando el entorno virtual e instalando las librerias, solo la primera vez...
    py -3 -m venv .venv
)
rem Revisa en cada corrida que esten todas las librerias (si ya estan, tarda unos segundos)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
".venv\Scripts\python.exe" src\pipeline_completo.py %*
echo.
echo Terminado. El dashboard se abre solo en el navegador: resultados\dashboard.html
pause