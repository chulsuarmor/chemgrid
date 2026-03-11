@echo off
echo ========================================================
echo [YOLO Mode] Starting ChemGrid Export Automation...
echo ========================================================
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
python _yolo_export_automation.py > _yolo_execution.log 2>&1
echo.
echo [Automation Completed]
echo Checking verification...
python _verify_pdf_content.py >> _yolo_execution.log 2>&1
type _yolo_execution.log
