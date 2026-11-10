<#
.SYNOPSIS
  Verificación completa de la laptop de competencia.
#>
param(
    [string]$VenvPath = ""
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $VenvPath) { $VenvPath = Join-Path $RepoRoot ".venv" }
$venvPython = Join-Path $VenvPath "Scripts\python.exe"

$ok = 0
$fail = 0

function Check($name, $script) {
    try {
        $result = & $script
        if ($LASTEXITCODE -eq 0 -and $result) {
            Write-Host "[OK]   $name" -ForegroundColor Green
            $script:ok++
        } else {
            Write-Host "[FAIL] $name" -ForegroundColor Red
            $script:fail++
        }
    } catch {
        Write-Host "[FAIL] $name ($($_.Exception.Message))" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "=== Verificación de la laptop de competencia ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host "Venv: $VenvPath"
Write-Host ""

# 1. Python
if (Test-Path $venvPython) {
    $ver = & $venvPython --version 2>&1
    if ($ver -match "3\.12") {
        Write-Host "[OK]   Python $ver" -ForegroundColor Green; $ok++
    } else {
        Write-Host "[FAIL] Python $ver (se esperaba 3.12)" -ForegroundColor Red; $fail++
    }
} else {
    Write-Host "[FAIL] No existe $venvPython" -ForegroundColor Red; $fail++
}

# 2. Librerías
if (Test-Path $venvPython) {
    & $venvPython -c "import ultralytics, cv2, paho.mqtt; print('ultralytics', ultralytics.__version__, 'opencv', cv2.__version__)" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK]   Librerías (ultralytics, opencv, paho-mqtt)" -ForegroundColor Green; $ok++
    } else {
        Write-Host "[FAIL] Faltan librerías" -ForegroundColor Red; $fail++
    }
}

# 3. Pesos del modelo
$pesos = Join-Path $RepoRoot "modelo\pesos\yolo11n.pt"
if (Test-Path $pesos) {
    Write-Host "[OK]   Pesos del modelo base ($pesos)" -ForegroundColor Green; $ok++
} else {
    Write-Host "[FAIL] No existe $pesos (yolo11n.pt obligatorio)" -ForegroundColor Red; $fail++
}
$entrenar = Join-Path $RepoRoot "modelo\entrenar.py"
if (Test-Path $entrenar) {
    Write-Host "[OK]   Script de entrenamiento ($entrenar)" -ForegroundColor Green; $ok++
} else {
    Write-Host "[FAIL] No existe $entrenar" -ForegroundColor Red; $fail++
}
$rescate = Join-Path $RepoRoot "modelo\pesos\rescate.pt"
if (Test-Path $rescate) {
    Write-Host "[OK]   Modelo de competencia ($rescate)" -ForegroundColor Green; $ok++
} else {
    Write-Host "[WARN] Modelo de competencia pendiente: $rescate (se genera el dia de la competencia)" -ForegroundColor Yellow
}

# 4. Broker local
$tcp = New-Object System.Net.Sockets.TcpClient
$ar = $tcp.BeginConnect("127.0.0.1", 1883, $null, $null)
if ($ar.AsyncWaitHandle.WaitOne(2000) -and $tcp.Connected) {
    Write-Host "[OK]   Broker local 127.0.0.1:1883 responde" -ForegroundColor Green; $ok++
    $tcp.Close()
} else {
    Write-Host "[WARN] Broker local 127.0.0.1:1883 no responde (arranca Mosquitto)" -ForegroundColor Yellow
}
$tcp.Dispose()

# 5. Tests
if (Test-Path $venvPython) {
    Push-Location $RepoRoot
    & $venvPython -m unittest discover -s tests -v 2>&1 | Out-Null
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -eq 0) {
        Write-Host "[OK]   Tests (python -m unittest discover -s tests)" -ForegroundColor Green; $ok++
    } else {
        Write-Host "[FAIL] Tests fallaron (código $code)" -ForegroundColor Red; $fail++
    }
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "RESULTADO: TODO VERDE ($ok puntos OK)" -ForegroundColor Green
} else {
    Write-Host "RESULTADO: $fail FALLOS, $ok OK" -ForegroundColor Red
}