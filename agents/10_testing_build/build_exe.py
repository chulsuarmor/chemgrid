# build_exe.py (v1.0 - ChemDraw Executable Builder)
"""
Build ChemDraw Pro as standalone executable using PyInstaller
Creates ChemDraw.exe with all dependencies bundled
"""

import subprocess
import sys
import os
from pathlib import Path

def build_chemdraw_exe():
    """Build ChemDraw.exe using PyInstaller"""
    
    # Get project root
    project_root = Path(__file__).parent
    logo_path = project_root / "logo.png"
    draw_script = project_root / "draw.py"
    
    # Check prerequisites
    print("[BUILD] Checking prerequisites...")
    
    if not draw_script.exists():
        print(f"❌ Error: draw.py not found at {draw_script}")
        return False
    
    print(f"✓ draw.py found: {draw_script}")
    
    # Check PyInstaller
    try:
        result = subprocess.run(
            ["pyinstaller", "--version"],
            capture_output=True,
            text=True
        )
        print(f"✓ PyInstaller found: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ Error: PyInstaller not installed")
        print("   Install with: pip install pyinstaller")
        return False
    
    # Convert PNG to ICO if logo exists
    icon_path = None
    if logo_path.exists():
        print("\n[BUILD] Converting logo.png to .ico...")
        try:
            from PIL import Image
            img = Image.open(logo_path)
            icon_path = project_root / "logo.ico"
            img.save(icon_path, format="ICO", sizes=[(256, 256)])
            print(f"✓ Icon created: {icon_path}")
        except ImportError:
            print("⚠ Warning: Pillow not installed, skipping icon conversion")
            print("   Install with: pip install Pillow")
        except Exception as e:
            print(f"⚠ Warning: Could not convert icon: {e}")
    
    # PyInstaller command
    print("\n[BUILD] Running PyInstaller...")
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--name", "ChemDraw",
        "--distpath", str(project_root / "dist"),
        "--buildpath", str(project_root / "build"),
        "--specpath", str(project_root),
    ]
    
    # Add icon if available
    if icon_path and icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    
    # Add hidden imports for dependencies
    hidden_imports = [
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtSvg",
        "matplotlib",
        "numpy",
        "scipy",
        "networkx",
        "reportlab",
    ]
    
    for hidden_import in hidden_imports:
        cmd.extend(["--hidden-import", hidden_import])
    
    # Add the main script
    cmd.append(str(draw_script))
    
    print(f"Command: {' '.join(cmd[:5])}...")
    
    try:
        result = subprocess.run(cmd, cwd=str(project_root))
        
        if result.returncode == 0:
            exe_path = project_root / "dist" / "ChemDraw.exe"
            if exe_path.exists():
                print(f"\n✓ Build successful!")
                print(f"✓ Executable: {exe_path}")
                print(f"✓ File size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
                return True
            else:
                print("❌ Build completed but exe not found")
                return False
        else:
            print(f"❌ Build failed with return code {result.returncode}")
            return False
    
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False


def create_batch_launcher():
    """Create launcher batch script for development"""
    project_root = Path(__file__).parent
    batch_file = project_root / "ChemDraw_Dev.bat"
    
    batch_content = """@echo off
REM ChemDraw Pro Development Launcher
REM Double-click to run ChemDraw with conda environment

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Check if conda is installed
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Conda not found. Please install Anaconda or Miniconda.
    pause
    exit /b 1
)

REM Activate chemdraw environment
call conda activate chemdraw
if %errorlevel% neq 0 (
    echo Error: Could not activate chemdraw environment
    echo Creating new environment...
    call conda create -n chemdraw python=3.10 -y
    call conda activate chemdraw
)

REM Run ChemDraw
echo Launching ChemDraw Pro...
python draw.py

if %errorlevel% neq 0 (
    echo Error: ChemDraw exited with error code %errorlevel%
    pause
)
"""
    
    with open(batch_file, 'w') as f:
        f.write(batch_content)
    
    print(f"✓ Batch launcher created: {batch_file}")


def create_uninstaller():
    """Create uninstaller for ChemDraw"""
    project_root = Path(__file__).parent
    uninstall_script = project_root / "uninstall.bat"
    
    uninstall_content = """@echo off
REM ChemDraw Pro Uninstaller

setlocal enabledelayexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo Uninstalling ChemDraw Pro...
echo.

REM Remove build artifacts
if exist "build" (
    echo Removing build directory...
    rmdir /s /q "build"
)

if exist "dist" (
    echo Removing dist directory...
    rmdir /s /q "dist"
)

REM Remove spec file
if exist "ChemDraw.spec" (
    echo Removing ChemDraw.spec...
    del /f /q "ChemDraw.spec"
)

echo.
echo Uninstall complete.
pause
"""
    
    with open(uninstall_script, 'w') as f:
        f.write(uninstall_content)
    
    print(f"✓ Uninstaller created: {uninstall_script}")


if __name__ == "__main__":
    print("=" * 70)
    print("ChemDraw Pro Executable Builder")
    print("=" * 70)
    print()
    
    # Check if PyInstaller should be installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # Build executable
    success = build_chemdraw_exe()
    
    if success:
        print("\n[POST-BUILD] Creating additional files...")
        create_batch_launcher()
        create_uninstaller()
        
        print("\n" + "=" * 70)
        print("BUILD COMPLETE!")
        print("=" * 70)
        print("\nYou can now:")
        print("  1. Run ChemDraw.exe from dist/ folder")
        print("  2. Or use ChemDraw_Dev.bat for development (conda environment)")
        print("  3. Double-click ChemDraw.exe to launch the application")
    else:
        print("\n" + "=" * 70)
        print("BUILD FAILED - Please fix errors above")
        print("=" * 70)
        sys.exit(1)
