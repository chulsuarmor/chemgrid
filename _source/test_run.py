#!/usr/bin/env python3
import sys

# Import and run just TEST 6 (Pyridine)
from test_dft_analyzer import test_pyridine, test_borazine, test_azulene

try:
    print("\n[SUBAGENT] Starting TEST 6: Pyridine\n")
    test_pyridine()
except Exception as e:
    print(f"\n[ERROR] {e}\n")
    import traceback
    traceback.print_exc()

try:
    print("\n[SUBAGENT] Starting TEST 4: Borazine\n")
    test_borazine()
except Exception as e:
    print(f"\n[ERROR] {e}\n")
    import traceback
    traceback.print_exc()

try:
    print("\n[SUBAGENT] Starting TEST 5: Azulene\n")
    test_azulene()
except Exception as e:
    print(f"\n[ERROR] {e}\n")
    import traceback
    traceback.print_exc()
