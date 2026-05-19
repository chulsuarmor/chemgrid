# NEW_MINIMAL_REPLACEMENT_WITH_NO_PROVENANCE
# Select the newest ChemGrid Lite executable for test_feedback_chemgrid.bat.

$ErrorActionPreference = "SilentlyContinue"

$candidates = Get-ChildItem -Path "C:\chemgrid\dist*\ChemGrid_Lite\ChemGrid.exe" -File |
    Sort-Object -Property LastWriteTimeUtc -Descending

if ($candidates -and $candidates.Count -gt 0) {
    Write-Output $candidates[0].FullName
}

exit 0
