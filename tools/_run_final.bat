@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
cd /d c:\chemgrid
python _final_user_test.py
echo Final test completed.
