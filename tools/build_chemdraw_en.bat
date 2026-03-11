@echo off
setlocal enabledelayexpansion

cd /d "C:\Users\김남헌\Desktop\organicdraw"

echo.
echo ========================================
echo Building ChemDraw.exe
echo ========================================
echo.

echo [1] Checking files...
if exist logo.png (
  echo   OK: logo.png exists
)

if exist build_exe.py (
  echo   OK: build_exe.py exists
)

if exist ChemDraw.exe (
  echo   OK: ChemDraw.exe already exists
  for %%A in (ChemDraw.exe) do set "size=%%~zA"
  echo   Size: !size! bytes
  goto :DONE
)

if exist dist\ChemDraw.exe (
  echo   OK: dist\ChemDraw.exe found
  copy dist\ChemDraw.exe ChemDraw.exe
  goto :DONE
)

echo [2] Building with PyInstaller...
python build_exe.py

:DONE
echo.
echo ========================================
echo Verification
echo ========================================
echo.
if exist ChemDraw.exe (
  for %%A in (ChemDraw.exe) do set "size=%%~zA"
  echo SUCCESS: ChemDraw.exe created
  echo Size: !size! bytes
  echo Location: C:\Users\김남헌\Desktop\organicdraw\ChemDraw.exe
)

pause
