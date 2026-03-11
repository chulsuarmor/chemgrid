#!/usr/bin/env python3
"""
Quick ChemDraw.exe build and verification
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def main():
    workspace = Path(r"C:\Users\김남헌\Desktop\organicdraw")
    os.chdir(workspace)
    
    print("\n" + "="*70)
    print("ChemDraw.exe Build and Verification")
    print("="*70 + "\n")
    
    # Check files
    logo_png = workspace / "logo.png"
    build_py = workspace / "build_exe.py"
    draw_py = workspace / "draw.py"
    exe_path = workspace / "ChemDraw.exe"
    dist_exe = workspace / "dist" / "ChemDraw.exe"
    
    print("[1] Checking prerequisites...")
    files_ok = True
    
    if logo_png.exists():
        print(f"  [OK] logo.png ({logo_png.stat().st_size:,} bytes)")
    else:
        print(f"  [FAIL] logo.png missing")
        files_ok = False
    
    if build_py.exists():
        print(f"  [OK] build_exe.py ({build_py.stat().st_size:,} bytes)")
    else:
        print(f"  [FAIL] build_exe.py missing")
        files_ok = False
    
    if draw_py.exists():
        print(f"  [OK] draw.py ({draw_py.stat().st_size:,} bytes)")
    else:
        print(f"  [FAIL] draw.py missing")
        files_ok = False
    
    # Check if ChemDraw.exe already exists
    if exe_path.exists():
        size = exe_path.stat().st_size
        print(f"\n[OK] ChemDraw.exe already exists ({size:,} bytes)")
        print(f"  Location: {exe_path}")
        return True
    
    # Check if dist/ChemDraw.exe exists
    if dist_exe.exists():
        print(f"\n[2] Found dist/ChemDraw.exe ({dist_exe.stat().st_size:,} bytes)")
        print(f"  Copying to {exe_path}...")
        try:
            shutil.copy(dist_exe, exe_path)
            print(f"  [OK] Copy successful")
            return True
        except Exception as e:
            print(f"  [FAIL] Copy failed: {e}")
    
    # Try to run build_exe.py
    if not files_ok:
        print("\n[FAIL] Missing prerequisites. Cannot build.")
        return False
    
    print("\n[3] Building with PyInstaller...")
    try:
        result = subprocess.run(
            [sys.executable, "build_exe.py"],
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )
        
        if result.returncode == 0:
            print("[OK] Build successful")
            
            # Try to copy from dist
            if dist_exe.exists():
                print("[4] Copying from dist...")
                shutil.copy(dist_exe, exe_path)
                print("[OK] Copy successful")
        else:
            print(f"[FAIL] Build failed")
            print(f"  stdout: {result.stdout[:200]}")
            print(f"  stderr: {result.stderr[:200]}")
            return False
    
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False
    
    # Final check
    print("\n[5] Final verification...")
    if exe_path.exists():
        size = exe_path.stat().st_size
        print(f"[OK] ChemDraw.exe created ({size:,} bytes)")
        print(f"  Location: {exe_path}")
        return True
    else:
        print(f"[FAIL] ChemDraw.exe not found")
        return False

if __name__ == "__main__":
    try:
        success = main()
        print("\n" + "="*70)
        if success:
            print("SUCCESS: Ready to deploy!")
        else:
            print("FAILED: Check errors above")
        print("="*70 + "\n")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
