@echo off
echo ========================================================
echo ChemGrid Mission Dispatch System
echo ========================================================
echo.

echo [1/3] Executing Patch Fixes directly (Bypassing Dispatcher)...
"C:\Users\김남헌\AppData\Local\Python\bin\python.exe" agents/08_spectroscopy/ir_raman/_patch_fix.py
"C:\Users\김남헌\AppData\Local\Python\bin\python.exe" agents/08_spectroscopy/uvvis/_patch_fix.py
"C:\Users\김남헌\AppData\Local\Python\bin\python.exe" agents/08_spectroscopy/nmr/_patch_fix.py
"C:\Users\김남헌\AppData\Local\Python\bin\python.exe" agents/09_data_export/_patch_fix.py
echo Patches applied.
echo.

echo [2/3] Generating PDF Report for Verification...
"C:\Users\김남헌\AppData\Local\Python\bin\python.exe" agents/09_data_export/spectrum_pdf_exporter.py
if %errorlevel% neq 0 (
    echo [ERROR] PDF Generation failed.
    pause
    exit /b %errorlevel%
)
echo.

echo [3/3] Verifying PDF Content (Agent 10)...
"C:\Users\김남헌\AppData\Local\Python\bin\python.exe" agents/10_testing_build/verify_pdf.py
if %errorlevel% neq 0 (
    echo [FAILURE] PDF Verification Failed! Please check the logs.
) else (
    echo [SUCCESS] PDF Verification Passed!
)

echo.
echo Mission Complete.
pause
