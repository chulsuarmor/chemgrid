@echo off
chcp 65001 >nul
echo ============================================================
echo  ChemGrid — 안내형 반자동 테스터 (guided_test.py)
echo ============================================================
echo.
echo  [동작 방식]
echo  1. ChemGrid가 자동으로 실행됩니다
echo  2. 터미널에 단계별 안내가 출력됩니다
echo  3. 안내에 따라 ChemGrid 창에서 행동하면
echo     앱 로그를 자동으로 감지해서 다음 단계로 넘어갑니다
echo.
echo  종료하려면 Ctrl+C 를 누르세요.
echo ============================================================
echo.

C:\ProgramData\anaconda3\envs\chemgrid\python.exe c:\chemgrid\tools\guided_test.py

echo.
echo 테스트 종료.
pause
