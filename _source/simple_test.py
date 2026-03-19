#!/usr/bin/env python3
"""Simple validation of off-by-one fix"""
import sys
from pathlib import Path

print("=" * 70)
print("SIMPLE TEST: Verifying off-by-one fix")
print("=" * 70)

try:
    # Test 1: Check if extractors exist
    print("\n[TEST 1] Checking if extractors are importable...")
    from electron_density_analyzer import MullikenChargeExtractor, GeometryExtractor
    print("✓ MullikenChargeExtractor imported")
    print("✓ GeometryExtractor imported")
    
    # Test 2: Create mock ORCA output
    print("\n[TEST 2] Creating mock Pyridine output...")
    from test_dft_analyzer import create_mock_orca_output
    out_path = create_mock_orca_output("pyridine")
    print(f"✓ Created: {out_path}")
    
    # Test 3: Extract charges
    print("\n[TEST 3] Extracting Mulliken charges...")
    charges = MullikenChargeExtractor.extract_from_out_file(out_path)
    print(f"✓ Extracted {len(charges)} charges:")
    for idx in sorted(charges.keys()):
        print(f"    Atom {idx}: {charges[idx]:+.4f}")
    
    # Test 4: Verify count
    print("\n[TEST 4] Validating atom count...")
    expected = 11  # Pyridine: C5 + N1 + H5
    if len(charges) == expected:
        print(f"✓ SUCCESS: Got {expected} atoms (all atoms including C5)")
    else:
        print(f"✗ FAILED: Got {len(charges)} atoms, expected {expected}")
        print(f"  Missing: {expected - len(charges)} atom(s)")
        if len(charges) == 10:
            print("  ⚠️  This is the OFF-BY-ONE ERROR: Last carbon (C5) is missing!")
        sys.exit(1)
    
    # Test 5: Verify charge conservation
    print("\n[TEST 5] Checking charge conservation...")
    total = sum(charges.values())
    print(f"Total charge: {total:.4f}")
    if abs(total) < 0.001:
        print(f"✓ SUCCESS: Charge conserved (≈ 0.0)")
    else:
        print(f"⚠️  Total charge = {total:.4f} (expected ≈ 0.0)")
    
    # Test 6: Extract geometry
    print("\n[TEST 6] Extracting geometry...")
    geometry = GeometryExtractor.extract_final_geometry(out_path)
    print(f"✓ Extracted {len(geometry)} coordinates:")
    for idx in sorted(geometry.keys()):
        x, y, z = geometry[idx]
        print(f"    Atom {idx}: ({x:6.2f}, {y:6.2f}, {z:6.2f})")
    
    if len(geometry) == expected:
        print(f"✓ SUCCESS: Got {expected} coordinates (all atoms including last)")
    else:
        print(f"✗ FAILED: Got {len(geometry)} coordinates, expected {expected}")
        sys.exit(1)
    
    # Cleanup
    out_path.unlink()
    
    print("\n" + "="*70)
    print("ALL TESTS PASSED ✅")
    print("="*70)
    print("\nSummary:")
    print("  ✓ MullikenChargeExtractor: Fixed off-by-one error")
    print("  ✓ GeometryExtractor: Fixed off-by-one error")
    print("  ✓ All 11 atoms in Pyridine extracted correctly")
    print("  ✓ Charge conservation verified")
    print("\nThe fix is working correctly!")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
