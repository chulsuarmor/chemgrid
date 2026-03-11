@echo off
setlocal
echo.
echo ============================================================
echo ChemGrid Agent 10: Integrated Verification
echo ============================================================
echo.

echo [1/3] Verifying Critical Fixes (C1-C5, M1-M2)...
py verify_integrated_fixes.py
if %errorlevel% neq 0 (
    echo [ERROR] Critical fix verification failed!
    exit /b 1
)

echo.
echo [2/3] Verifying v3.2 Rendering Logic...
py visual_verify_v32.py
if %errorlevel% neq 0 (
    echo [ERROR] Rendering verification failed!
    exit /b 1
)

echo.
echo [3/3] Running YOLO Export Automation (10 Molecules -> 30 PDFs)...
py _yolo_export_automation.py
if %errorlevel% neq 0 (
    echo [ERROR] Export automation failed!
    exit /b 1
)

echo.
echo ============================================================
echo SUCCESS: All verification steps passed!
echo Output files are in: %CD%\yolo_outputs
echo ============================================================

endlocal
pause
