#!/usr/bin/env python3
"""
Validate the off-by-one fix by testing with Pyridine mock output
"""
import sys
from pathlib import Path

# Test the fix
print("="*70)
print("VALIDATING OFF-BY-ONE FIX: append() 우선, 조건 체크 나중")
print("="*70)

# Import after path setup
from test_dft_analyzer import create_mock_orca_output
from electron_density_analyzer import MullikenChargeExtractor, GeometryExtractor

# Create pyridine test data
print("\n[TEST] Creating Pyridine (C5H5N) mock output...")
out_path = create_mock_orca_output("pyridine")

print(f"✓ Mock file created at: {out_path}\n")

# Extract charges
print("[TEST] Extracting Mulliken charges...")
charges = MullikenChargeExtractor.extract_from_out_file(out_path)

print(f"\nExtracted {len(charges)} charges:")
for atom_idx in sorted(charges.keys()):
    print(f"  Atom {atom_idx}: {charges[atom_idx]:+.4f}")

# Expected: 11 atoms
expected_atoms = 11
if len(charges) == expected_atoms:
    print(f"\n✅ SUCCESS: Extracted all {expected_atoms} atoms!")
    
    # Verify charge sum
    total_charge = sum(charges.values())
    print(f"\nTotal charge: {total_charge:.4f}")
    if abs(total_charge) < 0.001:
        print("✅ SUCCESS: Total charge ≈ 0.0 (charge conservation OK)")
    else:
        print(f"⚠️  WARNING: Total charge = {total_charge:.4f} (expected ≈ 0.0)")
else:
    print(f"\n❌ FAIL: Expected {expected_atoms} atoms, got {len(charges)}")
    missing = expected_atoms - len(charges)
    if missing > 0:
        print(f"   Missing {missing} atom(s) - OFF-BY-ONE ERROR STILL EXISTS!")

# Extract geometry
print("\n[TEST] Extracting geometry...")
geometry = GeometryExtractor.extract_final_geometry(out_path)
print(f"Extracted {len(geometry)} atomic coordinates:")
for atom_idx in sorted(geometry.keys()):
    x, y, z = geometry[atom_idx]
    print(f"  Atom {atom_idx}: ({x:6.2f}, {y:6.2f}, {z:6.2f})")

if len(geometry) == expected_atoms:
    print(f"\n✅ SUCCESS: Extracted all {expected_atoms} coordinates!")
else:
    print(f"\n⚠️  Got {len(geometry)} coordinates, expected {expected_atoms}")

# Cleanup
out_path.unlink()

# Run full test with test_dft_analyzer
print("\n" + "="*70)
print("RUNNING FULL TEST: TEST 6 - Pyridine")
print("="*70 + "\n")

try:
    from test_dft_analyzer import test_pyridine
    test_pyridine()
    print("\n" + "="*70)
    print("RESULT: All tests passed! ✅")
    print("="*70)
except AssertionError as e:
    print(f"\n❌ Test failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
