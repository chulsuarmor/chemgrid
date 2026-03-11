#!/usr/bin/env python3
"""Simple test to verify the fix by checking the code directly"""

# Test 1: Verify the fix was applied
print("=" * 60)
print("VERIFYING BUG FIX")
print("=" * 60)

import sys
from pathlib import Path

# Read electron_density_analyzer.py
analyzer_code = Path("electron_density_analyzer.py").read_text(encoding='utf-8', errors='ignore')

# Check if the old buggy code exists
if "mulliken_start = i + 3" in analyzer_code:
    print("\n✗ FAILED: Old buggy code 'i + 3' still present!")
    sys.exit(1)
elif "mulliken_start = i + 1" in analyzer_code:
    print("\n✓ PASSED: Code has been fixed! Using 'i + 1'")
else:
    print("\n? UNCLEAR: Could not find the line")
    sys.exit(1)

# Also check Löwdin
if "lowdin_start = i + 3" in analyzer_code:
    print("✗ FAILED: Old buggy Löwdin code 'i + 3' still present!")
    sys.exit(1)
elif "lowdin_start = i + 1" in analyzer_code:
    print("✓ PASSED: Löwdin code has been fixed! Using 'i + 1'")
else:
    print("? UNCLEAR: Could not find Löwdin line")
    sys.exit(1)

print("\n" + "=" * 60)
print("FIX VERIFICATION COMPLETE")
print("=" * 60)
print("\nSummary:")
print("  Mulliken parser: Fixed (i + 3 → i + 1)")
print("  Löwdin parser: Fixed (i + 3 → i + 1)")
print("\nNow running actual test...\n")

# Import test function
try:
    from test_dft_analyzer import (
        test_cyclopentadienyl_anion,
        test_tropylium_cation,
        test_benzene
    )
    
    test_cyclopentadienyl_anion()
    test_tropylium_cation()
    test_benzene()
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! ✓")
    print("=" * 60)
    
except AssertionError as e:
    print(f"\n✗ TEST FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
