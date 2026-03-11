#!/usr/bin/env python
"""Run a single test for debugging"""
import sys
sys.path.insert(0, r'C:\Users\김남헌\Desktop\organicdraw\_source')

# Import and run the test
from test_dft_analyzer import test_pyridine

try:
    test_pyridine()
    print("\n✅ TEST PASSED!")
except AssertionError as e:
    print(f"\n❌ TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
