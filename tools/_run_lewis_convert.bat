@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
echo Environment Activated: chemgrid
echo Running Conversion...
python _convert_lewis.py
echo Running Verification...
python _verify_lewis.py
echo Done.
