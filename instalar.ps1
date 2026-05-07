#Requires -Version 5.1
<#
.SYNOPSIS
    Instala Herramienta Pericles en el equipo local.
.DESCRIPTION
    1. Verifica Python 3.10+ e instala con winget si no esta presente.
    2. Crea un entorno virtual (.venv) dentro de esta carpeta.
    3. Instala las dependencias (requirements.txt).
    4. Verifica que los datos esten disponibles en data/.
    Ejecución: clic derecho → "Ejecutar con PowerShell"
               o desde terminal: .\instalar.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ROOT   = $PSScriptRoot
$VENV   = Join-Path $ROOT ".venv"
$DATA   = Join-Path $ROOT "data"
$REQ    = Join-Path $ROOT "requirements.txt"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Herramienta Pericles — Instalador"        -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
# ── 0. Verificar Windows 10+ ───────────────────────────────────────────────────
Write-Host ">> Verificando sistema operativo..." -ForegroundColor Yellow
$osVersion = [Environment]::OSVersion.Version
if ($osVersion.Major -lt 10) {
    Write-Host "" 
    Write-Host "  ERROR: Esta aplicacion requiere Windows 10 o superior." -ForegroundColor Red
    Write-Host "         Tu sistema es Windows $($osVersion.Major).$($osVersion.Minor)." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Windows 7 y Windows 8 no son compatibles porque:" -ForegroundColor Yellow
    Write-Host "    - Python 3.10+ no esta disponible para esos sistemas." -ForegroundColor Yellow
    Write-Host "    - Carecen de soporte de seguridad actualizado." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Pulsa Enter para salir"
    exit 1
}
Write-Host "   OK: Windows $($osVersion.Major).$($osVersion.Minor)" -ForegroundColor Green
# ── 1. Verificar Python ──────────────────────────────────────────────────────
function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) {
                    return $cmd
                }
            }
        } catch {}
    }
    return $null
}

Write-Host ">> Verificando Python..." -ForegroundColor Yellow
$pythonCmd = Find-Python

if (-not $pythonCmd) {
    Write-Host "   Python 3.10+ no encontrado. Instalando con winget..." -ForegroundColor Yellow
    winget install Python.Python.3.13 --silent --accept-source-agreements --accept-package-agreements
    # Refrescar PATH para que python sea visible en esta sesion
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $pythonCmd = Find-Python
    if (-not $pythonCmd) {
        Write-Host ""
        Write-Host ">> Paso adicional necesario:" -ForegroundColor Cyan
        Write-Host "   Cierra esta ventana y vuelve a ejecutar instalar.bat." -ForegroundColor Yellow
        Write-Host "   Si el problema persiste, instala Python manualmente:" -ForegroundColor DarkGray
        Write-Host "   https://www.python.org/downloads/ (marca 'Add to PATH')" -ForegroundColor DarkGray
        Read-Host "Pulsa Enter para salir"
        exit 1
    }
}

$verFound = & $pythonCmd --version 2>&1
Write-Host "   Encontrado: $verFound" -ForegroundColor Green

# ── 2. Crear entorno virtual ─────────────────────────────────────────────────
if (Test-Path (Join-Path $VENV "Scripts\python.exe")) {
    Write-Host ">> Entorno virtual ya existe, omitiendo creacion." -ForegroundColor Green
} else {
    Write-Host ">> Creando entorno virtual..." -ForegroundColor Yellow
    & $pythonCmd -m venv $VENV
    Write-Host "   OK" -ForegroundColor Green
}

$pip    = Join-Path $VENV "Scripts\pip.exe"

# ── 3. Instalar dependencias ─────────────────────────────────────────────────
Write-Host ">> Instalando dependencias (puede tardar unos minutos)..." -ForegroundColor Yellow
Write-Host "   Veras los paquetes descargados a continuacion:" -ForegroundColor DarkGray
Write-Host ""
& $pip install -r $REQ
Write-Host ""
Write-Host "   OK" -ForegroundColor Green

# ── 4. Verificar datos ───────────────────────────────────────────────────────
$parquets = @(Get-ChildItem $DATA -Filter "*.parquet" -ErrorAction SilentlyContinue)
if ($parquets.Count -lt 5) {
    Write-Host ""
    Write-Host "ADVERTENCIA: No se encuentran los archivos de datos en la carpeta data/." -ForegroundColor Red
    Write-Host "             Asegurate de haber descomprimido el ZIP completo" -ForegroundColor Red
    Write-Host "             y de que la carpeta data/ contiene archivos .parquet." -ForegroundColor Red
} else {
    Write-Host ">> Datos verificados ($($parquets.Count) archivos)." -ForegroundColor Green
}

# ── Fin ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Instalacion completada." -ForegroundColor Green
Write-Host "   Ejecuta 'pericles.bat' para abrir la app." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Pulsa Enter para salir"
