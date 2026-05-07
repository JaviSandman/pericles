#Requires -Version 5.1
<#
.SYNOPSIS
    Instala Herramienta Pericles en el equipo local.
.DESCRIPTION
    1. Verifica que Python 3.10+ está instalado.
    2. Crea un entorno virtual (.venv) dentro de esta carpeta.
    3. Instala las dependencias (requirements.txt).
    4. Verifica que los datos están disponibles en data/.
    Ejecución: clic derecho → "Ejecutar con PowerShell"
               o desde terminal: .\instalar.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
Write-Host ">> Verificando Python..." -ForegroundColor Yellow
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonCmd = $cmd
                Write-Host "   Encontrado: $ver" -ForegroundColor Green
                break
            }
        }
    } catch {}
}
if (-not $pythonCmd) {
    Write-Host "ERROR: Se necesita Python 3.10 o superior." -ForegroundColor Red
    Write-Host "       Descárgalo desde https://www.python.org/downloads/" -ForegroundColor Red
    Read-Host "Pulsa Enter para salir"
    exit 1
}

# ── 2. Crear entorno virtual ─────────────────────────────────────────────────
if (Test-Path (Join-Path $VENV "Scripts\python.exe")) {
    Write-Host ">> Entorno virtual ya existe, omitiendo creación." -ForegroundColor Green
} else {
    Write-Host ">> Creando entorno virtual..." -ForegroundColor Yellow
    & $pythonCmd -m venv $VENV
    Write-Host "   OK" -ForegroundColor Green
}

$pip    = Join-Path $VENV "Scripts\pip.exe"
$python = Join-Path $VENV "Scripts\python.exe"

# ── 3. Instalar dependencias ─────────────────────────────────────────────────
Write-Host ">> Instalando dependencias (puede tardar unos minutos)..." -ForegroundColor Yellow
Write-Host "   Veras los paquetes descargados a continuacion:" -ForegroundColor DarkGray
Write-Host ""
& $pip install --upgrade pip
Write-Host ""
& $pip install -r $REQ
Write-Host ""
Write-Host "   OK" -ForegroundColor Green

# ── 4. Verificar datos ───────────────────────────────────────────────────────
$parquets = Get-ChildItem $DATA -Filter "*.parquet" -ErrorAction SilentlyContinue
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
Write-Host "   Instalación completada." -ForegroundColor Green
Write-Host "   Ejecuta 'pericles.bat' para abrir la app." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Pulsa Enter para salir"
