@echo off
REM ChemDraw.exe 빌드 및 검증 배치 파일
setlocal enabledelayexpansion

cd /d "C:\Users\김남헌\Desktop\organicdraw"

echo.
echo ========================================
echo ChemDraw.exe 빌드 및 검증
echo ========================================
echo.

REM 1. 파일 존재 확인
echo [1] 파일 존재 확인 중...
if exist logo.png (
  echo   [OK] logo.png 존재
) else (
  echo   [ERR] logo.png 없음
)

if exist build_exe.py (
  echo   [OK] build_exe.py 존재
) else (
  echo   [ERR] build_exe.py 없음
)

if exist draw.py (
  echo   [OK] draw.py 존재
) else (
  echo   [ERR] draw.py 없음
)

if exist ChemDraw.exe (
  echo   [OK] ChemDraw.exe 이미 존재
  goto :END
)

if exist dist\ChemDraw.exe (
  echo   [INFO] dist\ChemDraw.exe 존재 - 복사 중...
  copy dist\ChemDraw.exe ChemDraw.exe
  if !errorlevel! equ 0 (
    echo   [OK] 복사 완료
    goto :VERIFY
  )
)

REM 2. Python/PyInstaller로 빌드
echo.
echo [2] PyInstaller로 빌드 중...
python build_exe.py

if !errorlevel! equ 0 (
  echo   [OK] 빌드 성공
  if exist dist\ChemDraw.exe (
    copy dist\ChemDraw.exe ChemDraw.exe
    echo   [OK] dist\ChemDraw.exe 복사 완료
  )
) else (
  echo   [ERR] 빌드 실패
  goto :END
)

REM 3. 최종 검증
:VERIFY
echo.
echo [3] 최종 검증 중...
if exist ChemDraw.exe (
  for %%A in (ChemDraw.exe) do (
    set "filesize=%%~zA"
    echo   [OK] ChemDraw.exe 존재 - 크기: !filesize! bytes
  )
  echo.
  echo ========================================
  echo 빌드 완료! ChemDraw.exe가 준비되었습니다.
  echo ========================================
  echo.
) else (
  echo   [ERR] ChemDraw.exe 생성 실패
)

:END
pause
