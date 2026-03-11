@echo off
chcp 65001 > nul
title ChemGrid AI 입력 자동화 테스트
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   ChemGrid AI 텍스트 입력 + 전자구름 검증 테스트      ║
echo ║   tools/ai_input_tester.py                           ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo [1] 전체 테스트 (ChemGrid 자동 실행)
echo [2] 이미 실행 중인 ChemGrid 사용 (--no-launch)
echo [3] 텍스트 입력 테스트만 (--only-text)
echo [Q] 종료
echo.
set /p choice="선택 (1/2/3/Q): "

if /i "%choice%"=="1" goto full
if /i "%choice%"=="2" goto nolaunsh
if /i "%choice%"=="3" goto textonly
if /i "%choice%"=="q" goto end
if /i "%choice%"=="Q" goto end

:full
echo.
echo [실행] 전체 테스트 시작...
cd /d c:\chemgrid
python tools\ai_input_tester.py
goto done

:nolaunsh
echo.
echo [실행] 기존 창 사용 모드...
cd /d c:\chemgrid
python tools\ai_input_tester.py --no-launch
goto done

:textonly
echo.
echo [실행] 텍스트 입력 테스트만...
cd /d c:\chemgrid
python tools\ai_input_tester.py --no-launch --only-text
goto done

:done
echo.
echo 테스트 완료. 보고서: tools\ai_input_report.html
echo.
pause
goto end

:end
exit
