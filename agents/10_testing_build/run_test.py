#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.getcwd())

# Run test_azulene only
from test_dft_analyzer import test_azulene, create_mock_orca_output
from pathlib import Path

try:
    test_azulene()
    print("\n✅ TEST PASSED!")
except AssertionError as e:
    print(f"\n❌ TEST FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
