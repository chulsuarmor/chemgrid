# ChemGrid legacy installer wrapper
#
# Canonical installer contract:
#   Pinned rc1 onefile ChemGrid.exe via the repository root installer.
#   The root installer verifies the expected EXE SHA256 before launch.
#
# Usage:
#   powershell.exe -ExecutionPolicy Bypass -File install/install.ps1

param(
    [switch]$NoLaunch,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Write-Step { param([string]$msg) Write-Host "[$msg]" -ForegroundColor Cyan }
function Write-Err  { param([string]$msg) Write-Host "  !!  $msg" -ForegroundColor Red }

Write-Step "ChemGrid legacy installer wrapper"

$rootInstaller = Join-Path (Split-Path -Parent $PSScriptRoot) 'install.ps1'
if (-not (Test-Path $rootInstaller)) {
    Write-Err "Canonical installer not found: $rootInstaller"
    exit 1
}

$argsList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $rootInstaller)
if ($NoLaunch) {
    $argsList += '-NoLaunch'
}
if ($DryRun) {
    $argsList += '--dry-run'
}

& powershell.exe @argsList
exit $LASTEXITCODE
