@echo off
:: Herramienta Pericles — Instalador
:: Doble clic para instalar. Solo necesitas hacer esto una vez.

echo.
echo  ============================================
echo    Herramienta Pericles - Instalador
echo  ============================================
echo.
echo  Este proceso instalara todo lo necesario para
echo  ejecutar la aplicacion. Puede tardar unos minutos
echo  dependiendo de tu conexion a internet.
echo.
echo  No cierres esta ventana hasta que termine.
echo.
pause

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"

echo.
if %ERRORLEVEL% EQU 0 (
    echo  Instalacion completada correctamente.
    echo  Ahora puedes abrir la aplicacion con pericles.bat
) else (
    echo  Hubo un problema durante la instalacion.
    echo  Revisa los mensajes anteriores para mas detalles.
)
echo.
pause
