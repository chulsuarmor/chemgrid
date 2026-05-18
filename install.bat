@echo off
chcp 65001 >nul 2>&1
:: ChemGrid install.bat  --  Windows cmd (no PowerShell dependency)
:: Worker D-M1153-002-W_INSTALL_BAT / M1427 / 2026-05-18
:: Rule I: no API keys in source
:: Rule M: no silent failure -- every step echoes result
:: Rule K3: surgical -- cmd only, PowerShell 0 lines
::
:: Usage (cmd window):
::   curl -L -o "%USERPROFILE%\Desktop\ChemGrid.exe" ^
::     https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid.exe ^
::     && start "" "%USERPROFILE%\Desktop\ChemGrid.exe"
::
:: Or double-click this .bat file from any folder.

setlocal EnableDelayedExpansion

:: ----------------------------------------------------------------------------
:: Config (Rule I: magic number comments)
:: ----------------------------------------------------------------------------
set "REPO=chulsuarmor/chemgrid"
set "TAG=v1.0.0-lite-rc2"
set "EXE_NAME=ChemGrid.exe"
:: Destination: Desktop (no admin required)
set "DEST=%USERPROFILE%\Desktop\%EXE_NAME%"
set "DL_URL=https://github.com/%REPO%/releases/download/%TAG%/%EXE_NAME%"
:: Minimum file size check: 100 MB = 104857600 bytes (actual ~1.17 GB)
set /a MIN_BYTES=104857600

:: ----------------------------------------------------------------------------
echo.
echo ======================================
echo   ChemGrid Installer (cmd edition)
echo ======================================
echo.

:: ----------------------------------------------------------------------------
:: 1) curl.exe presence check (built-in since Windows 10 v1803)
:: ----------------------------------------------------------------------------
where curl.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] curl.exe not found.
    echo        Windows 10 v1803+ has curl built in.
    echo        If on older Windows, download curl from https://curl.se/windows/
    echo        and place curl.exe in a folder on your PATH.
    echo.
    pause
    exit /b 1
)
echo [OK] curl.exe found.

:: ----------------------------------------------------------------------------
:: 2) Download ChemGrid.exe to Desktop
:: ----------------------------------------------------------------------------
echo.
echo [STEP] Downloading %EXE_NAME% to Desktop...
echo        Source : %DL_URL%
echo        Target : %DEST%
echo        (This may take several minutes -- file is ~1.17 GB)
echo.

curl -L --retry 3 --retry-delay 2 --progress-bar -o "%DEST%" "%DL_URL%"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Download failed. Possible causes:
    echo        - No internet connection
    echo        - GitHub release not yet published
    echo        - Disk full (need ~1.5 GB free on %USERPROFILE%\Desktop)
    echo.
    echo        Manual download URL:
    echo        %DL_URL%
    echo.
    pause
    exit /b 1
)
echo.
echo [OK] Download complete.

:: ----------------------------------------------------------------------------
:: 3) File size sanity check (Rule M: no silent failure)
:: ----------------------------------------------------------------------------
echo [STEP] Verifying file size...
for %%F in ("%DEST%") do set /a FILE_SIZE=%%~zF
:: Note: set /a is 32-bit integer; large sizes wrap -- use string compare instead
for %%F in ("%DEST%") do set "FILE_SIZE_STR=%%~zF"

:: Simple length-based check: a valid 1.17 GB exe has 10 digits; < 9 digits = likely corrupt
set "LEN_OK=0"
if "%FILE_SIZE_STR%" geq "104857600" set "LEN_OK=1"
:: geq string comparison works for same-length numbers; check digit count fallback
set "_tmp=%FILE_SIZE_STR%"
if "!_tmp:~9,1!" neq "" set "LEN_OK=1"

if "%LEN_OK%"=="0" (
    echo [ERROR] Downloaded file appears too small: %FILE_SIZE_STR% bytes
    echo        Expected at least 100 MB. The file may be corrupt or the
    echo        release asset may be missing. Check:
    echo        https://github.com/%REPO%/releases/tag/%TAG%
    del /f /q "%DEST%" >nul 2>&1
    echo.
    pause
    exit /b 1
)
echo [OK] File size OK: %FILE_SIZE_STR% bytes

:: ----------------------------------------------------------------------------
:: 4) Launch ChemGrid.exe
:: ----------------------------------------------------------------------------
echo.
echo [STEP] Launching %EXE_NAME%...
start "" "%DEST%"
if %errorlevel% neq 0 (
    echo [WARN] Could not auto-launch. Please double-click:
    echo        %DEST%
) else (
    echo [OK] ChemGrid started.
)

:: ----------------------------------------------------------------------------
:: 5) Done
:: ----------------------------------------------------------------------------
echo.
echo ======================================
echo   Installation complete!
echo ======================================
echo.
echo   Executable : %DEST%
echo   To relaunch: double-click ChemGrid.exe on your Desktop
echo.
echo   For AI features (optional), create a .env file next to
echo   ChemGrid.exe with your API key:
echo     GROQ_API_KEY=your_key_here
echo   Free key: https://console.groq.com/keys
echo.
echo   Issues: https://github.com/%REPO%/issues
echo.
pause
endlocal
