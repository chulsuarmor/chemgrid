@echo off
echo ========================================
echo ChemGrid 빌드 스크립트
echo ========================================

cd /d "%~dp0"

echo.
echo [1/3] 기존 빌드 파일 정리...
if exist build rmdir /s /q build
if exist dist\ChemGrid.exe del /f /q dist\ChemGrid.exe

echo.
echo [2/3] PyInstaller로 ChemGrid.exe 생성...
pyinstaller ChemGrid.spec --clean

echo.
echo [3/3] 빌드 결과 확인...
if exist dist\ChemGrid.exe (
    echo.
    echo ========================================
    echo 빌드 성공!
    echo ========================================
    echo 실행 파일: dist\ChemGrid.exe
    echo.
    dir dist\ChemGrid.exe
) else (
    echo.
    echo ========================================
    echo 빌드 실패!
    echo ========================================
    echo PyInstaller가 설치되지 않았거나 오류가 발생했습니다.
    echo 다음 명령어로 설치: pip install pyinstaller
)

echo.
pause
