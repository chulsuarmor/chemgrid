#!/usr/bin/env python
# -*- coding: utf-8 -*-
import subprocess
import sys

result = subprocess.run([
    sys.executable, 
    r"C:\Users\김남헌\Desktop\organicdraw\_source\test_parser_standalone.py"
], capture_output=True, text=True)

# Write output to file
with open(r"C:\Users\김남헌\Desktop\organicdraw\_source\test_output.log", 'w', encoding='utf-8') as f:
    f.write("=== STDOUT ===\n")
    f.write(result.stdout)
    f.write("\n=== STDERR ===\n")
    f.write(result.stderr)
    f.write(f"\n=== EXIT CODE: {result.returncode} ===\n")

print("Test output written to test_output.log")
print(f"Exit code: {result.returncode}")
