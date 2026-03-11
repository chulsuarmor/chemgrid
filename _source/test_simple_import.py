#!/usr/bin/env python
import sys
import os

os.chdir(r'C:\Users\김남헌\Desktop\organicdraw\_source')
sys.path.insert(0, r'C:\Users\김남헌\Desktop\organicdraw\_source')

try:
    print("Step 1: Import test_dft_analyzer")
    from test_dft_analyzer import test_cyclopentadienyl_anion
    print("SUCCESS")
    
    print("\nStep 2: Run test 1")
    test_cyclopentadienyl_anion()
    print("Test 1 completed")
    
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
