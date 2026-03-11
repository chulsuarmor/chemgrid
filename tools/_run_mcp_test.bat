@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
python _run_mcp_test.py > test_output.txt 2>&1
type test_output.txt
if exist server_log.txt type server_log.txt
