@echo off
:: Direct run (no sync)
set CONDA_PYTHON=C:\ProgramData\anaconda3\envs\chemgrid\python.exe
cd /d c:\chemgrid\src\app
%CONDA_PYTHON% draw.py 2>c:\chemgrid\launch_error.log
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed! Error log:
    type c:\chemgrid\launch_error.log
)
pause
