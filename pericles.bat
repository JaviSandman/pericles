@echo off
:: Herramienta Pericles — Lanzador
:: Doble clic para abrir la aplicacion en el navegador.

setlocal enabledelayedexpansion

set ROOT=%~dp0
set PYTHON=%ROOT%.venv\Scripts\python.exe
set APP=%ROOT%app\Presentacion.py
set URL=http://localhost:8501

cls
echo.
echo  ============================================
echo    Herramienta Pericles
echo  ============================================
echo.
echo  Pericles es una aplicacion de analisis electoral.
echo  Funciona como una pagina web que se ejecuta en tu
echo  propio ordenador, sin necesidad de conexion a internet.
echo.
echo  Al pulsar continuar ocurrira lo siguiente:
echo    1. Se arranca el servidor de la aplicacion (en segundo plano)
echo    2. Se abre tu navegador con la direccion local:
echo       http://localhost:8501
echo.
echo  IMPORTANTE: Esta ventana debe permanecer abierta
echo              mientras uses la aplicacion. Puedes
echo              minimizarla, pero no cerrarla.
echo.

:: ── Verificar instalacion ─────────────────────────────────────────────────
if not exist "%PYTHON%" (
    echo  ERROR: No se encontro el entorno virtual.
    echo         Ejecuta primero instalar.bat y vuelve a intentarlo.
    echo.
    pause
    exit /b 1
)

:: ── Detectar navegadores instalados ──────────────────────────────────────
set COUNT=0

set _EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe
if not exist "%_EDGE%" set _EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe
if exist "%_EDGE%" (
    set /a COUNT+=1
    set NAME1=Microsoft Edge
    set EXE1=%_EDGE%
)

set _CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if not exist "%_CHROME%" set _CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%_CHROME%" (
    set /a COUNT+=1
    set NAME%COUNT%=Google Chrome
    set EXE%COUNT%=%_CHROME%
)

set _FF=%ProgramFiles%\Mozilla Firefox\firefox.exe
if not exist "%_FF%" set _FF=%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe
if exist "%_FF%" (
    set /a COUNT+=1
    set NAME%COUNT%=Mozilla Firefox
    set EXE%COUNT%=%_FF%
)

:: ── Seleccion de navegador ────────────────────────────────────────────────
set CHOSEN_EXE=

if %COUNT% EQU 0 goto :no_browser

if %COUNT% EQU 1 (
    echo  Navegador detectado: !NAME1!
    echo.
    set CHOSEN_EXE=!EXE1!
    goto :confirm
)

echo  Se han detectado varios navegadores instalados.
echo  Con cual quieres abrir la aplicacion?
echo.
if %COUNT% GEQ 1 echo    [1] !NAME1!
if %COUNT% GEQ 2 echo    [2] !NAME2!
if %COUNT% GEQ 3 echo    [3] !NAME3!
echo.
set /p SEL="  Tu eleccion (1-%COUNT%): "

if "%SEL%"=="1" set CHOSEN_EXE=!EXE1!
if "%SEL%"=="2" if %COUNT% GEQ 2 set CHOSEN_EXE=!EXE2!
if "%SEL%"=="3" if %COUNT% GEQ 3 set CHOSEN_EXE=!EXE3!

if "!CHOSEN_EXE!"=="" (
    echo.
    echo  Opcion no valida. Se usara el navegador predeterminado.
)
goto :confirm

:no_browser
echo  No se detecto ningun navegador conocido.
echo  Abre manualmente %URL% cuando la app este lista.
echo.

:confirm
echo  Pulsa una tecla para iniciar Pericles...
pause > nul

:: ── Arrancar Streamlit en ventana secundaria ──────────────────────────────
start "Pericles (no cerrar)" /min "%PYTHON%" -m streamlit run "%APP%" --server.headless true --browser.gatherUsageStats false

:: Esperar a que Streamlit este listo
echo.
echo  Arrancando servidor, espera unos segundos...
timeout /t 5 /nobreak > nul

:: ── Abrir navegador ───────────────────────────────────────────────────────
if "!CHOSEN_EXE!"=="" (
    start "" "%URL%"
) else (
    start "" "!CHOSEN_EXE!" "%URL%"
)

:: ── Mensaje final ─────────────────────────────────────────────────────────
cls
echo.
echo  ============================================
echo    Pericles esta en marcha
echo  ============================================
echo.
echo  Si el navegador no se abrio, copia y pega
echo  esta direccion en tu navegador:
echo.
echo    %URL%
echo.
echo  Para cerrar la aplicacion, pulsa Ctrl+C aqui
echo  o cierra la ventana "Pericles (no cerrar)".
echo.
pause

endlocal
