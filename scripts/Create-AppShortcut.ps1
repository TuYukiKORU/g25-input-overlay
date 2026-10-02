[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$iconPath = Join-Path $projectRoot 'frontend\static\icons\app.ico'
if (-not (Test-Path -LiteralPath $iconPath)) { throw 'App icon missing. Run Build-AppIcon.ps1 first.' }
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path $projectRoot 'F1 Telemetry.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $projectRoot 'START_OVERLAY.cmd'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = 'Start F1 telemetry and open lap analysis'
$shortcut.Save()
Write-Host "App shortcut created: $shortcutPath"
