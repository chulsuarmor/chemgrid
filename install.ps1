$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$HelpArgs = @('/?', '-?', '--help', '/help', '-h')
$DryRunArgs = @('/dryrun', '--dry-run', '-dryrun')
$NoLaunchArgs = @('/nolaunch', '--no-launch', '-nolaunch', '-NoLaunch')
if ($args | Where-Object { $HelpArgs -contains $_ }) {
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File install.ps1"
    Write-Host "Downloads the pinned ChemGrid v1.0.0-lite-rc1 onefile EXE to Desktop and starts it unless -NoLaunch is set."
    exit 0
}
$DryRun = [bool]($args | Where-Object { $DryRunArgs -contains $_ })
$NoLaunch = [bool]($args | Where-Object { $NoLaunchArgs -contains $_ })

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Warning "TLS 1.2 setup failed, continuing: $($_.Exception.Message)"
}

$Url = 'https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid.exe'
$ExpectedSha256 = '62e501f5537e169dc8d8bcade90ded1e8ad8f28ab6872ec21a38f7124b6ecd3c'
$Desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($Desktop)) {
    $Desktop = Join-Path $env:USERPROFILE 'Downloads'
}
New-Item -ItemType Directory -Force -Path $Desktop | Out-Null

$Output = Join-Path $Desktop 'ChemGrid.exe'
$TempOutput = Join-Path $env:TEMP ("ChemGrid_{0}.exe" -f ([guid]::NewGuid().ToString('N')))
if ($DryRun) {
    Write-Host "DRYRUN: would download $Url"
    Write-Host "DRYRUN: would verify SHA256 $ExpectedSha256"
    if ($NoLaunch) {
        Write-Host "DRYRUN: would write $Output without starting ChemGrid"
    } else {
        Write-Host "DRYRUN: would write $Output and start ChemGrid"
    }
    exit 0
}

Write-Host "Downloading ChemGrid v1.0.0-lite-rc1 to $TempOutput"
Invoke-WebRequest -Uri $Url -OutFile $TempOutput -UseBasicParsing

if (-not (Test-Path $TempOutput)) {
    throw "Download failed: $TempOutput"
}

$Size = (Get-Item $TempOutput).Length
$MinSize = 100MB
if ($Size -lt $MinSize) {
    throw "Downloaded file is too small: $Size bytes"
}

$ActualSha256 = (Get-FileHash -Algorithm SHA256 $TempOutput).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "Downloaded ChemGrid.exe SHA256 mismatch. Expected $ExpectedSha256 but got $ActualSha256"
}

try {
    Copy-Item -Force -Path $TempOutput -Destination $Output
} catch {
    $Output = Join-Path $Desktop 'ChemGrid_image_fixed_rc1.exe'
    Write-Warning "Could not replace Desktop\\ChemGrid.exe, writing alternate file: $Output"
    Copy-Item -Force -Path $TempOutput -Destination $Output
}

try {
    Unblock-File -Path $Output
} catch {
    Write-Warning "Unblock-File failed, continuing: $($_.Exception.Message)"
} finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $TempOutput
}

if ($NoLaunch) {
    Write-Host "ChemGrid downloaded and verified: $Output"
} else {
    Write-Host "Starting ChemGrid..."
    Start-Process -FilePath $Output
}
