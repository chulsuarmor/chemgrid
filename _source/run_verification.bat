@echo off
echo.
echo ============================================================
echo Verification: Atom 5 Boundary Fix (create_density_map v2.03)
echo ============================================================
echo.

python "C:\Users\김남헌\Desktop\organicdraw\_source\verify_atom5_fix.py"
set result=%errorlevel%

if %result% equ 0 (
    echo.
    echo ============================================================
    echo SUCCESS: All checks passed!
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo FAILED: Some checks did not pass
    echo ============================================================
)

pause
exit /b %result%
