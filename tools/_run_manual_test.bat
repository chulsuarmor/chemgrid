@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
start /B python agents/mcp_server/server.py > server_log_manual.txt 2>&1
start /B python agents/10_testing_build/integrated/draw.py
echo Waiting for server...
timeout /t 10
python _test_request.py
taskkill /F /IM python.exe
