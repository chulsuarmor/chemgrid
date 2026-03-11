#!/usr/bin/env python3
"""Quick syntax validation of modified files"""

import py_compile
import sys
from pathlib import Path

files_to_check = [
    r"C:\Users\김남헌\Desktop\organicdraw\_source\orca_interface.py",
    r"C:\Users\김남헌\Desktop\organicdraw\_source\test_parser_standalone.py",
    r"C:\Users\김남헌\Desktop\organicdraw\_source\test_additional_molecules.py",
]

results = []

for filepath in files_to_check:
    try:
        py_compile.compile(filepath, doraise=True)
        results.append((Path(filepath).name, True, "OK"))
    except Exception as e:
        results.append((Path(filepath).name, False, str(e)))

# Write results
output = Path(r"C:\Users\김남헌\Desktop\organicdraw\_source\syntax_validation_results.txt")
with open(output, 'w', encoding='utf-8') as f:
    f.write("SYNTAX VALIDATION RESULTS\n")
    f.write("="*70 + "\n\n")
    
    for filename, passed, msg in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        f.write(f"{status}: {filename}\n")
        if msg and msg != "OK":
            f.write(f"  Error: {msg}\n")
    
    f.write("\n" + "="*70 + "\n")
    passed_count = sum(1 for _, p, _ in results if p)
    f.write(f"Summary: {passed_count}/{len(results)} files passed\n")

print(f"Results written to {output}")
