@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
cd /d c:\chemgrid\agents\10_testing_build\integrated
python draw.py 2>c:\chemgrid\_chemgrid_stderr.log 1>c:\chemgrid\_chemgrid_stdout.log
