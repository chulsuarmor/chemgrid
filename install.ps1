# ChemGrid Installer (Windows PowerShell 5.1+)
# Worker D-M1153-002-W_INSTALL_FIX_URGENT / M1426 / 2026-05-18
#
# Usage (student PC - no admin required):
#   irm https://github.com/chulsuarmor/chemgrid/releases/latest/download/install.ps1 | iex
#
# Or specific version:
#   irm https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.ps1 | iex
#
# IMPORTANT: If you see encoding errors, download directly:
#   $u='https://github.com/chulsuarmor/chemgrid/releases/latest/download/ChemGrid.exe'
#   Invoke-WebRequest $u -OutFile "$env:USERPROFILE\Desktop\ChemGrid.exe"
#
# Rule I  : No API keys in source. Magic numbers commented.
# Rule M  : No silent failure. All steps report status.
# Rule JJ : No cmd window. PowerShell only, no cmd.exe calls.
# M1426   : ASCII-only rewrite. Korean removed. PS 5.1 compatible.
#            Removed: ?? / ?. / && operators (PS7-only).
#            Removed: all Korean characters.

# UTF-8 output for PS 5.1 cp949 consoles
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Non-interactive run (irm | iex) -- safe to ignore
}

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ----------------------------------------------------------------------------
# Configuration (Rule I: magic numbers annotated)
# ----------------------------------------------------------------------------
$Repo           = 'chulsuarmor/chemgrid'
$ExeAsset       = 'ChemGrid.exe'
$ZipAsset       = 'ChemGrid_Lite.zip'
$InstallDir     = "$env:LOCALAPPDATA\ChemGrid"  # Per-user folder, no admin needed
$ShortcutName   = 'ChemGrid.lnk'
$MinExeSizeMB   = 100   # Minimum expected exe size MB (actual ~1.17 GB)
$MinZipSizeMB   = 50    # Minimum expected zip size MB (actual ~290 MB)

# ----------------------------------------------------------------------------
# Helper functions -- ASCII output only (Rule M: user feedback required)
# ----------------------------------------------------------------------------
function Write-Step { param([string]$msg) Write-Host "[$msg]" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  --  $msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$msg) Write-Host "  !!  $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  ChemGrid Installer" -ForegroundColor Cyan
Write-Host "  Python is NOT required." -ForegroundColor Cyan
Write-Host "  ChemGrid.exe is fully portable." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------------------
# Step 1: Environment check (Rule N: type/environment guard)
# ----------------------------------------------------------------------------
Write-Step "Step 1/9: Environment check"
$psVer = $PSVersionTable.PSVersion.Major
if ($psVer -lt 5) {
    Write-Err "PowerShell 5.0+ required (current: $psVer). Run on Windows 10/11."
    exit 1
}
Write-OK "PowerShell $psVer detected"

# Force TLS 1.2 for GitHub HTTPS (required on older Windows)
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Write-OK "TLS 1.2 enabled"
} catch {
    Write-Warn "TLS 1.2 setup failed (continuing): $($_.Exception.Message)"
}

# ----------------------------------------------------------------------------
# Step 2: Fetch latest release info from GitHub API
# ----------------------------------------------------------------------------
Write-Step "Step 2/9: Fetching release info"
$apiUrl  = "https://api.github.com/repos/$Repo/releases/latest"
$release = $null
try {
    $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ 'User-Agent' = 'ChemGrid-Installer/1.1' }
} catch {
    Write-Err "GitHub API request failed: $($_.Exception.Message)"
    Write-Warn "Manual download: https://github.com/$Repo/releases"
    Write-Warn "Direct exe link: https://github.com/$Repo/releases/latest/download/ChemGrid.exe"
    exit 1
}

# Rule N: type guard -- validate release structure
if (-not $release) {
    Write-Err "Empty response from GitHub API."
    Write-Warn "Direct exe link: https://github.com/$Repo/releases/latest/download/ChemGrid.exe"
    exit 1
}
if (-not $release.assets) {
    Write-Err "No assets found in release. Contact: https://github.com/$Repo/issues"
    exit 1
}
$tag = $release.tag_name
Write-OK "Release: $tag"

# ----------------------------------------------------------------------------
# Step 3: Select download asset
#   Primary:  ChemGrid.exe (portable, no extraction needed)
#   Fallback: ChemGrid_Lite.zip
# ----------------------------------------------------------------------------
Write-Step "Step 3/9: Selecting download asset"
$useExeDirect = $true

$exeAssetObj = $null
foreach ($a in $release.assets) {
    if ($a.name -eq $ExeAsset) {
        $exeAssetObj = $a
        break
    }
}

if (-not $exeAssetObj) {
    Write-Warn "$ExeAsset not found in release. Switching to ZIP mode."
    $useExeDirect = $false
}

if ($useExeDirect) {
    $downloadUrl = $exeAssetObj.browser_download_url
    $assetSizeMB = [math]::Round($exeAssetObj.size / 1MB, 1)
    $minSizeMB   = $MinExeSizeMB
    Write-OK "Asset: $ExeAsset ($assetSizeMB MB)"
} else {
    $zipAssetObj = $null
    foreach ($a in $release.assets) {
        if ($a.name -eq $ZipAsset) {
            $zipAssetObj = $a
            break
        }
    }
    # Fallback: any portable zip pattern (M1418)
    if (-not $zipAssetObj) {
        foreach ($a in $release.assets) {
            if ($a.name -match 'ChemGrid.*\.zip') {
                $zipAssetObj = $a
                break
            }
        }
    }
    if (-not $zipAssetObj) {
        Write-Err "No downloadable asset found. Available assets:"
        foreach ($a in $release.assets) { Write-Host "    - $($a.name)" }
        Write-Warn "Direct link: https://github.com/$Repo/releases/latest/download/ChemGrid.exe"
        exit 1
    }
    $downloadUrl = $zipAssetObj.browser_download_url
    $assetSizeMB = [math]::Round($zipAssetObj.size / 1MB, 1)
    $minSizeMB   = $MinZipSizeMB
    Write-OK "Asset: $($zipAssetObj.name) ($assetSizeMB MB, ZIP)"
}

# Rule N: size sanity check
if ($assetSizeMB -lt $minSizeMB) {
    Write-Err "Asset size abnormal (${assetSizeMB}MB < minimum ${minSizeMB}MB). Release may be corrupted."
    exit 1
}

# ----------------------------------------------------------------------------
# Step 4: Check existing installation (Rule M: no silent overwrite)
# ----------------------------------------------------------------------------
Write-Step "Step 4/9: Checking existing installation"
if (Test-Path $InstallDir) {
    $ts        = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backupDir = "${InstallDir}_backup_$ts"
    Write-Warn "Existing installation found: $InstallDir"
    Write-Warn "Backing up to: $backupDir"
    try {
        Move-Item $InstallDir $backupDir -Force
        Write-OK "Backup complete"
    } catch {
        Write-Err "Backup failed: $($_.Exception.Message)"
        exit 1
    }
} else {
    Write-OK "Fresh installation"
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# ----------------------------------------------------------------------------
# Step 5: Download
# ----------------------------------------------------------------------------
Write-Step "Step 5/9: Downloading ($assetSizeMB MB) -- please wait..."

if ($useExeDirect) {
    $destFile = Join-Path $InstallDir $ExeAsset
} else {
    $destFile = Join-Path $env:TEMP "chemgrid_$tag.zip"
}

try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $destFile -UseBasicParsing
    $actualSizeMB = [math]::Round((Get-Item $destFile).Length / 1MB, 1)
    Write-OK "Download complete (${actualSizeMB} MB)"
} catch {
    Write-Err "Download failed: $($_.Exception.Message)"
    Write-Warn "Browser download: https://github.com/$Repo/releases/download/$tag/$ExeAsset"
    Write-Warn "Or open: https://github.com/$Repo/releases/latest"
    exit 1
}

# ----------------------------------------------------------------------------
# Step 6: Extract ZIP (only if not exe-direct mode)
# ----------------------------------------------------------------------------
if (-not $useExeDirect) {
    Write-Step "Step 6/9: Extracting ZIP"

    # ZIP path-traversal guard (Rule N)
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zipReader = [System.IO.Compression.ZipFile]::OpenRead($destFile)
        $safe = $true
        foreach ($entry in $zipReader.Entries) {
            $norm = $entry.FullName -replace '/', '\'
            if ($norm -match '\.\.[/\\]' -or $norm -match '^[A-Za-z]:[/\\]') {
                Write-Err "ZIP path-traversal detected: $($entry.FullName)"
                $safe = $false
                break
            }
        }
        $zipReader.Dispose()
        if (-not $safe) {
            Remove-Item $destFile -Force -ErrorAction SilentlyContinue
            exit 1
        }
        Write-OK "ZIP integrity verified"
    } catch {
        Write-Warn "ZIP pre-check failed (continuing): $($_.Exception.Message)"
    }

    try {
        Expand-Archive -Path $destFile -DestinationPath $InstallDir -Force
        Remove-Item $destFile -Force -ErrorAction SilentlyContinue
        Write-OK "Extraction complete"
    } catch {
        Write-Err "Extraction failed: $($_.Exception.Message)"
        exit 1
    }

    # Locate exe inside extracted folder
    $exeCandidates = @(
        (Join-Path $InstallDir $ExeAsset),
        (Join-Path $InstallDir "ChemGrid_Lite\$ExeAsset"),
        (Join-Path $InstallDir "ChemGrid\$ExeAsset")
    )
    $foundExe = $null
    foreach ($c in $exeCandidates) {
        if (Test-Path $c) { $foundExe = $c; break }
    }
    if (-not $foundExe) {
        Write-Err "$ExeAsset not found after extraction. Check: $InstallDir"
        exit 1
    }
    $destFile   = $foundExe
    $InstallDir = Split-Path $destFile -Parent
    Write-OK "Executable location: $InstallDir"
} else {
    Write-Step "Step 6/9: Skipped (exe-direct mode)"
    Write-OK "No extraction needed"
}

# ----------------------------------------------------------------------------
# Step 7: Verify executable (Rule M: no phantom deliverable)
# ----------------------------------------------------------------------------
Write-Step "Step 7/9: Verifying executable"
$exePath = if ($useExeDirect) { Join-Path $InstallDir $ExeAsset } else { $destFile }

if (-not (Test-Path $exePath)) {
    Write-Err "$ExeAsset not found at: $exePath"
    exit 1
}
$exeSizeMB = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
if ($exeSizeMB -lt $MinExeSizeMB) {
    Write-Err "Executable size abnormal (${exeSizeMB}MB). Possible corruption."
    exit 1
}
Write-OK "$ExeAsset verified ($exeSizeMB MB)"
Write-OK "Python NOT required -- all dependencies bundled in ChemGrid.exe"

# ----------------------------------------------------------------------------
# Step 8: .env setup (Rule I: no API keys in source -- .env.example only)
# ----------------------------------------------------------------------------
Write-Step "Step 8/9: API key setup (optional)"
$envExampleAsset = $null
foreach ($a in $release.assets) {
    if ($a.name -eq 'default.env.example') { $envExampleAsset = $a; break }
}
$envExample = Join-Path $InstallDir '.env.example'
$envFile    = Join-Path $InstallDir '.env'

if ($envExampleAsset -and (-not (Test-Path $envExample))) {
    try {
        Invoke-WebRequest -Uri $envExampleAsset.browser_download_url -OutFile $envExample -UseBasicParsing
        Write-OK ".env.example downloaded"
    } catch {
        Write-Warn ".env.example download failed (non-critical): $($_.Exception.Message)"
    }
}

if ((Test-Path $envExample) -and (-not (Test-Path $envFile))) {
    Copy-Item $envExample $envFile -Force
    Write-OK ".env created (no API keys -- AI features disabled)"
    Write-Warn "To enable AI: edit $envFile and add GROQ_API_KEY or GEMINI_API_KEY"
} elseif (Test-Path $envFile) {
    Write-OK ".env preserved (existing API keys retained)"
} else {
    Write-Warn ".env.example not found -- basic features work without it"
}

# ----------------------------------------------------------------------------
# Step 9: Desktop shortcut
# ----------------------------------------------------------------------------
Write-Step "Step 9/9: Creating desktop shortcut"
$shortcutCreated = $false
try {
    $desktopCandidates = @(
        [Environment]::GetFolderPath('Desktop'),
        "$env:USERPROFILE\Desktop",
        "$env:USERPROFILE\OneDrive\Desktop"
    )
    $desktop = $null
    foreach ($d in $desktopCandidates) {
        if ($d -and (Test-Path $d)) { $desktop = $d; break }
    }
    if ($desktop) {
        $shortcutPath = Join-Path $desktop $ShortcutName
        $wsh = New-Object -ComObject WScript.Shell
        $sc  = $wsh.CreateShortcut($shortcutPath)
        $sc.TargetPath       = $exePath
        $sc.WorkingDirectory = $InstallDir
        $sc.IconLocation     = $exePath
        $sc.Description      = 'ChemGrid - Chemistry Drawing + Spectral Analysis + AI Drug Design'
        $sc.Save()
        Write-OK "Desktop shortcut: $shortcutPath"
        $shortcutCreated = $true

        # Start menu registration (non-critical)
        try {
            $startMenu = [Environment]::GetFolderPath('Programs')
            if ($startMenu -and (Test-Path $startMenu)) {
                Copy-Item $shortcutPath (Join-Path $startMenu $ShortcutName) -Force -ErrorAction SilentlyContinue
                Write-OK "Start menu registered"
            }
        } catch {
            Write-Warn "Start menu registration skipped: $($_.Exception.Message)"
        }
    } else {
        Write-Warn "Desktop folder not found -- shortcut skipped"
    }
} catch {
    Write-Warn "Shortcut creation failed (non-critical): $($_.Exception.Message)"
}

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  ChemGrid Installation Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Install path : $InstallDir" -ForegroundColor White
Write-Host "  Executable   : $ExeAsset ($exeSizeMB MB)" -ForegroundColor White
Write-Host "  Python       : NOT required (all bundled)" -ForegroundColor White
if ($shortcutCreated) {
    Write-Host "  Shortcut     : Desktop + Start Menu" -ForegroundColor White
}
Write-Host ""
Write-Host "How to run:" -ForegroundColor Cyan
Write-Host "  1. Double-click ChemGrid on Desktop"
Write-Host "  2. Or run directly:"
Write-Host "     $exePath"
Write-Host ""
Write-Host "Optional AI features (GROQ / Gemini):" -ForegroundColor Cyan
Write-Host "  Edit: $envFile"
Write-Host "  Free key: https://console.groq.com/keys"
Write-Host ""
Write-Host "If this script fails (encoding issue on older Windows):" -ForegroundColor Yellow
Write-Host "  Open browser and download directly:" -ForegroundColor Yellow
Write-Host "  https://github.com/$Repo/releases/download/$tag/$ExeAsset" -ForegroundColor Yellow
Write-Host ""
Write-Host "Issues: https://github.com/$Repo/issues" -ForegroundColor Gray
Write-Host ""

# ----------------------------------------------------------------------------
# Auto-launch (suppress with -NoLaunch argument)
# ----------------------------------------------------------------------------
if (-not ($args -contains '-NoLaunch')) {
    Write-Step "Launching ChemGrid..."
    try {
        # Rule JJ: no cmd window -- Start-Process does not create a new console window
        Start-Process -FilePath $exePath -WorkingDirectory $InstallDir
        Write-OK "ChemGrid started"
    } catch {
        Write-Warn "Auto-launch failed. Run manually: $exePath"
    }
}
