$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Warning "TLS 1.2 setup failed, continuing: $($_.Exception.Message)"
}

$Url = 'https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid.exe'
$Desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($Desktop)) {
    $Desktop = Join-Path $env:USERPROFILE 'Downloads'
}
New-Item -ItemType Directory -Force -Path $Desktop | Out-Null

$Output = Join-Path $Desktop 'ChemGrid.exe'
Write-Host "Downloading ChemGrid v1.0.0-lite-rc1 to $Output"
Invoke-WebRequest -Uri $Url -OutFile $Output -UseBasicParsing

if (-not (Test-Path $Output)) {
    throw "Download failed: $Output"
}

$Size = (Get-Item $Output).Length
$MinSize = 100MB
if ($Size -lt $MinSize) {
    throw "Downloaded file is too small: $Size bytes"
}

try {
    Unblock-File -Path $Output
} catch {
    Write-Warning "Unblock-File failed, continuing: $($_.Exception.Message)"
}

Write-Host "Starting ChemGrid..."
Start-Process -FilePath $Output
