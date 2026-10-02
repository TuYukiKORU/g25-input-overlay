[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot ".runtime\server.pid"

function Get-PortOwner {
    param(
        [ValidateSet("TCP", "UDP")][string]$Protocol,
        [int]$Port
    )
    $lines = & netstat.exe -ano -p $Protocol 2>$null
    $pattern = if ($Protocol -eq "TCP") {
        "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    } else {
        "^\s*UDP\s+\S+:$Port\s+\S+\s+(\d+)\s*$"
    }
    foreach ($line in $lines) {
        if ($line -match $pattern) {
            return [int]$Matches[1]
        }
    }
    return 0
}

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "Telemetry server is not running (no PID file)." -ForegroundColor Yellow
    exit 0
}

$savedPid = 0
if (-not [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$savedPid)) {
    Remove-Item -LiteralPath $pidFile -Force
    throw "The PID file was invalid and has been removed."
}

$process = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Host "Telemetry server was already stopped. Stale PID file removed." -ForegroundColor Yellow
    exit 0
}

if ($process.ProcessName -notmatch "^pythonw?$" -or
    (Get-PortOwner TCP 5000) -ne $savedPid -or
    (Get-PortOwner UDP 20777) -ne $savedPid) {
    throw "PID $savedPid is not this project's telemetry server. Refusing to stop it."
}

Stop-Process -Id $savedPid
try {
    Wait-Process -Id $savedPid -Timeout 5 -ErrorAction Stop
} catch {
    Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Telemetry server stopped (PID $savedPid)." -ForegroundColor Green
