@echo off
echo ============================================
echo  ChemGrid - Start Script v2
echo ============================================

set CONDA_PYTHON=C:\ProgramData\anaconda3\envs\chemgrid\python.exe

echo [1/1] ChemGrid running...
cd /d c:\chemgrid\src\app
%CONDA_PYTHON% draw.py 2>c:\chemgrid\launch_error.log
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] ChemGrid failed!
    type c:\chemgrid\launch_error.log
)
pause
