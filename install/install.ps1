# ChemGrid legacy installer wrapper
#
# Canonical installer contract:
#   Pinned v1.0.0-lite-rc1 onefile ChemGrid.exe via the repository root installer.
#   The root installer verifies SHA256
#   981898c1b88e3d512aae820eb7be812c27b4dd7dc217a3bd59522ba37d8f5a22.
#   This wrapper does not follow releases/latest or rc8.
#
# Usage:
#   powershell.exe -ExecutionPolicy Bypass -File install/install.ps1 [-NoLaunch] [-DryRun]

param(
    [switch]$Help,
    [switch]$NoLaunch,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Write-Step { param([string]$msg) Write-Host "[$msg]" -ForegroundColor Cyan }
function Write-Err  { param([string]$msg) Write-Host "  !!  $msg" -ForegroundColor Red }

if ($Help) {
    Write-Host "Usage: powershell.exe -ExecutionPolicy Bypass -File install/install.ps1 [-NoLaunch] [-DryRun]"
    Write-Host "Delegates to the repository root installer pinned to v1.0.0-lite-rc1 ChemGrid.exe."
    Write-Host "Does not follow releases/latest or rc8."
    exit 0
}

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
