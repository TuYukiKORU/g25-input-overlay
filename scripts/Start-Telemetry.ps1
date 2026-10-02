[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot ".runtime"
$pidFile = Join-Path $runtimeDir "server.pid"
$stdoutLog = Join-Path $runtimeDir "server.out.log"
$stderrLog = Join-Path $runtimeDir "server.err.log"

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

function Get-ManagedServerProcess {
    param([int]$ProcessId)
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process -or $process.ProcessName -notmatch "^pythonw?$") {
        return $null
    }
    if ((Get-PortOwner TCP 5000) -eq $ProcessId -and
        (Get-PortOwner UDP 20777) -eq $ProcessId) {
        return $process
    }
    return $null
}

function Get-PythonExecutable {
    $candidates = @()
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        $candidates += $venvPython
    }
    $commands = Get-Command python.exe -All -ErrorAction SilentlyContinue
    $candidates += @($commands | ForEach-Object { $_.Source })
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        $works = $false
        try {
            & $candidate -c "import sys" *> $null
            $works = $LASTEXITCODE -eq 0
        } catch {
            $works = $false
        }
        if ($works) {
            return $candidate
        }
    }
    throw "A working Python installation was not found. Recreate .venv or install Python."
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

if (Test-Path -LiteralPath $pidFile) {
    $savedPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$savedPid)) {
        $running = Get-ManagedServerProcess -ProcessId $savedPid
        if ($running) {
            Write-Host "Telemetry server is already running (PID $savedPid)." -ForegroundColor Green
            Write-Host "Analysis: http://127.0.0.1:5000/analysis"
            if (-not $NoBrowser) {
                Start-Process "http://127.0.0.1:5000/analysis"
            }
            exit 0
        }
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$tcpOwner = Get-PortOwner TCP 5000
$udpOwner = Get-PortOwner UDP 20777
if ($tcpOwner -or $udpOwner) {
    $owners = @($tcpOwner, $udpOwner) | Where-Object { $_ } | Sort-Object -Unique
    throw "Port 5000 or UDP 20777 is already used by another process (PID: $($owners -join ', '))."
}

$pythonExe = Get-PythonExecutable
$localDependencies = Join-Path $projectRoot ".runtime-deps"
if (Test-Path -LiteralPath $localDependencies) {
    $env:PYTHONPATH = if ($env:PYTHONPATH) {
        "$localDependencies$([IO.Path]::PathSeparator)$env:PYTHONPATH"
    } else {
        $localDependencies
    }
}
Push-Location $projectRoot
try {
    $flaskAvailable = $false
    try {
        & $pythonExe -c "import flask" *> $null
        $flaskAvailable = $LASTEXITCODE -eq 0
    } catch {
        $flaskAvailable = $false
    }
    if (-not $flaskAvailable) {
        throw "Flask is not installed for $pythonExe. Run: `"$pythonExe`" -m pip install -r requirements.txt"
    }

    $server = Start-Process -FilePath $pythonExe -ArgumentList "backend\app.py" `
        -WorkingDirectory $projectRoot -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru

    $ready = $false
    $actualPid = 0
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        $httpOwner = Get-PortOwner TCP 5000
        $udpOwner = Get-PortOwner UDP 20777
        if ($httpOwner -gt 0 -and $httpOwner -eq $udpOwner) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:5000/health" -TimeoutSec 1
                if ($response.StatusCode -eq 200) {
                    $actualPid = $httpOwner
                    $ready = $true
                    break
                }
            } catch {
                # The sockets can be ready just before Flask accepts requests.
            }
        }
    }

    if (-not $ready) {
        $httpOwner = Get-PortOwner TCP 5000
        if ($httpOwner -gt 0) {
            Stop-Process -Id $httpOwner -Force -ErrorAction SilentlyContinue
        }
        if (-not $server.HasExited -and $server.Id -ne $httpOwner) {
            Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        $errorTail = if (Test-Path -LiteralPath $stderrLog) {
            (Get-Content -LiteralPath $stderrLog -Tail 12) -join [Environment]::NewLine
        } else { "No error log was created." }
        throw "Telemetry server did not start.`n$errorTail"
    }

    Set-Content -LiteralPath $pidFile -Value $actualPid -Encoding ascii
    Write-Host "Telemetry server started (PID $actualPid)." -ForegroundColor Green
    Write-Host "Analysis: http://127.0.0.1:5000/analysis"
    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:5000/analysis"
    }
} finally {
    Pop-Location
}
