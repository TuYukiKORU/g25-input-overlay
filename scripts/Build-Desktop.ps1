[CmdletBinding()]
param([string]$Python = "python", [string]$Version = "0.3.2-udp-preview")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $buildPython = Join-Path $projectRoot ".build-venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $buildPython)) {
        & $Python -m venv .build-venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
    }
    & $buildPython -m pip install -r requirements-desktop.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install desktop build dependencies." }
    if (-not (Test-Path -LiteralPath ".build-assets\test-laps\manifest.json")) {
        & $buildPython scripts/prepare_test_laps.py
        if ($LASTEXITCODE -ne 0) { throw "Could not prepare real test laps." }
    }
    & $buildPython scripts/build_metadata.py --version $Version
    if ($LASTEXITCODE -ne 0) { throw "Could not create the build fingerprint." }
    & $buildPython scripts/build_manuals.py --version $Version
    if ($LASTEXITCODE -ne 0) { throw "Could not build the user manuals." }
    & $buildPython -m PyInstaller --noconfirm F1Telemetry.spec
    if ($LASTEXITCODE -ne 0) { throw "The desktop build failed." }
    & $buildPython scripts/package_desktop.py --version $Version
    if ($LASTEXITCODE -ne 0) { throw "Could not package the release." }
} finally { Pop-Location }
