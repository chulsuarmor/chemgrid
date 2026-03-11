import os
import sys
from pathlib import Path
import importlib.util

def check_library(name):
    if importlib.util.find_spec(name) is None:
        print(f"[ERROR] Library '{name}' not found.")
        return False
    print(f"[OK] Library '{name}' found.")
    return True

def atomic_mkdir(path_str):
    try:
        p = Path(path_str)
        p.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Directory created/verified: {p.absolute()}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to create directory {path_str}: {e}")
        return False

def main():
    print("=== Robust Environment Setup for Lewis Structure Export ===")
    
    # 1. Directory Setup
    dirs = [
        "_source/lewis_structures",
        "_source/lewis_structures/pdf",
        "_source/lewis_structures/verification"
    ]
    
    all_dirs_ok = True
    for d in dirs:
        if not atomic_mkdir(d):
            all_dirs_ok = False
            
    if not all_dirs_ok:
        print("\n[FATAL] Directory setup failed. Check permissions or disk space.")
        sys.exit(1)
        
    # 2. Dependency Check
    required_libs = ['rdkit', 'reportlab'] # reportlab for PDF generation often used instead of cairo if cairo is tricky on windows
    # Note: Checking for cairo specifically if needed, but reportlab is a common alternative or complement
    
    libs_ok = True
    for lib in required_libs:
        if not check_library(lib):
            libs_ok = False
            
    if not libs_ok:
        print("\n[WARNING] Some dependencies are missing. Please install them using pip or conda.")
        print("Recommended: conda install -c conda-forge rdkit reportlab")
    else:
        print("\n[OK] All core dependencies verified.")
        
    # 3. Create a specialized README for resumption
    readme_path = Path("_source/lewis_structures/README_RESUME.txt")
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write("""
=== Lewis Structure Export Project Resumption Guide ===

1. Objectives:
   - Convert .chem files to Lewis Structures
   - Export to PDF
   - Verify PDF content

2. Directory Structure:
   - /pdf: Stores generated PDFs
   - /verification: Stores validation reports

3. Next Steps:
   - Run python _convert_lewis.py (Needs implementation)
   - Run python _verify_lewis.py (Needs implementation)

Refer to memory/lewis_structure_plan.md for full details.
""")
    print(f"\n[OK] Resumption guide created at {readme_path}")
    print("\n=== Setup Complete ===")

if __name__ == "__main__":
    main()
