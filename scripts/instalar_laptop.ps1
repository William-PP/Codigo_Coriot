<#
.SYNOPSIS
  Instala el entorno de la laptop de competencia (CORIOT GAMES 2026).
.DESCRIPTION
  Verifica Python 3.12, crea el entorno virtual, instala dependencias
  (offline si existe wheels/, si no por internet) y verifica el modelo YOLO.
.PARAMETER VenvPath
  Ruta del entorno virtual a crear. Por defecto: .venv en la raiz del repo.
.PARAMETER WheelsDir
  Carpeta con ruedas (wheels) para instalacion offline. Por defecto: kit\wheels.
#>
param(
    [string]$VenvPath = "",
    [string]$WheelsDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $VenvPath) { $VenvPath = Join-Path $RepoRoot ".venv" }
if (-not $WheelsDir) { $WheelsDir = Join-Path $RepoRoot "kit\wheels" }

function Write-Ok($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }

# 1. Python 3.12
$py = $null
try {
    $py = (Get-Command py -ErrorAction SilentlyContinue)
} catch {}
$pythonExe = $null
if ($py) {
    try {
        $ver = & py -3.12 --version 2>&1
        if ($ver -match "3\.12") { $pythonExe = "py -3.12" }
    } catch {}
}
if (-not $pythonExe) {
    # Buscar python 3.12 en PATH
    $cands = @("python3.12", "python")
    foreach ($c in $cands) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) {
            $ver = & $c --version 2>&1
            if ($ver -match "3\.12") { $pythonExe = $c; break }
        }
    }
}
if (-not $pythonExe) {
    Write-Fail "No se encontró Python 3.12."
    Write-Host "Descárgalo de https://www.python.org/downloads/release/python-31210/"
    Write-Host "o con winget: winget install Python.Python.3.12"
    exit 1
}
Write-Ok "Python 3.12 encontrado ($pythonExe)."

# 2. Crear entorno virtual
if (Test-Path $VenvPath) {
    Write-Warn "El entorno $VenvPath ya existe; se reutiliza."
} else {
    Write-Host "Creando entorno virtual en $VenvPath ..."
    if ($pythonExe -eq "py -3.12") {
        & py -3.12 -m venv $VenvPath
    } else {
        & $pythonExe -m venv $VenvPath
    }
    if ($LASTEXITCODE -ne 0) { Write-Fail "No se pudo crear el entorno virtual."; exit 1 }
    Write-Ok "Entorno virtual creado."
}

$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Write-Fail "No existe $venvPython"; exit 1 }

# 3. Instalar dependencias
$lock = Join-Path $RepoRoot "requirements-lock.txt"
$req = Join-Path $RepoRoot "Requirements.txt"
$useLock = Test-Path $lock

if (Test-Path $WheelsDir) {
    Write-Host "Instalando desde wheels (offline): $WheelsDir"
    if ($useLock) {
        & $venvPython -m pip install --no-index --find-links $WheelsDir -r $lock
    } else {
        & $venvPython -m pip install --no-index --find-links $WheelsDir -r $req
    }
} else {
    Write-Warn "No hay carpeta wheels ($WheelsDir). Se instala por internet."
    if ($useLock) {
        & $venvPython -m pip install -r $lock
    } else {
        & $venvPython -m pip install -r $req
    }
}
if ($LASTEXITCODE -ne 0) { Write-Fail "Falló la instalación de dependencias."; exit 1 }
Write-Ok "Dependencias instaladas."

# 4. Verificar pesos del modelo
$pesos = Join-Path $RepoRoot "modelo\pesos\yolo11n.pt"
if (-not (Test-Path $pesos)) {
    Write-Fail "No se encontró el modelo base en $pesos"
    Write-Host "Copia yolo11n.pt (y rescate.pt si existe) a modelo\pesos\ antes de competir."
    exit 1
}
Write-Ok "Pesos del modelo presentes ($pesos)."

# 5. Verificación del entorno
Write-Host "Ejecutando modelo/verificar_entorno.py ..."
& $venvPython (Join-Path $RepoRoot "modelo\verificar_entorno.py")
if ($LASTEXITCODE -ne 0) { Write-Warn "verificar_entorno.py terminó con código $LASTEXITCODE." } else { Write-Ok "Entorno verificado." }

$entrenar = Join-Path $RepoRoot "modelo\entrenar.py"
if (-not (Test-Path $entrenar)) {
    Write-Fail "No se encontró el script de entrenamiento en $entrenar"
    exit 1
}
Write-Ok "Script de entrenamiento presente ($entrenar)."

Write-Host ""
Write-Ok "Instalación completada. Clona el repo y ejecuta scripts/instalar_laptop.ps1"
Write-Ok "Activa con: $VenvPath\Scripts\Activate.ps1"