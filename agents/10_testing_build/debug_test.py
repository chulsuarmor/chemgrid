#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import traceback

print("Python version:", sys.version)
print("Working directory:", os.getcwd())

try:
    print("\nAttempting to import test_dft_analyzer...")
    import test_dft_analyzer
    print("✓ Import successful")
    
    print("\nRunning tests...")
    test_dft_analyzer.test_cyclopentadienyl_anion()
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
