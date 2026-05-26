@echo off
chcp 65001 >nul 2>&1
:: ChemGrid install.bat  --  Windows cmd wrapper for canonical PowerShell installer
:: Worker D-M1153-002-W_INSTALL_BAT / M1427 / 2026-05-18
:: Rule I: no API keys in source
:: Rule M: no silent failure -- every step echoes result
:: Rule K3: wrapper only -- canonical logic lives in install.ps1
::
:: Usage: double-click this .bat file from any folder.

setlocal

if /I "%~1"=="/?" goto :help
if /I "%~1"=="-?" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/dryrun" goto :dryrun
if /I "%~1"=="--dry-run" goto :dryrun

:: ----------------------------------------------------------------------------
echo.
echo ======================================
echo   ChemGrid Installer (rc1 onefile EXE wrapper)
echo ======================================
echo.

where powershell.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] powershell.exe not found. ChemGrid rc1 installer requires PowerShell 5+.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if %errorlevel% neq 0 pause
endlocal
exit /b %errorlevel%

:help
echo Usage: install.bat [/dryrun]
endlocal
exit /b 0

:dryrun
echo [DRYRUN] Would run PowerShell installer: %~dp0install.ps1
endlocal
exit /b 0
