#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VERIFICATION SCRIPT: Strict Column Check Fix
Test that coordinate hijacking is FIXED with len(parts) == 3 validation
"""

from pathlib import Path
from electron_density_analyzer import ElectronDensityAnalyzer, MullikenChargeExtractor

# ============================================================================
# TEST 1: Cyclopentadienyl Anion (Total Charge Must Be -1.0000)
# ============================================================================

print("\n" + "="*70)
print("VERIFICATION: Strict Column Check (v2.02)")
print("="*70)
print("\nTEST 1: Cyclopentadienyl Anion (C5H5-)")
print("Expected total charge: -1.0000 (must be preserved!)\n")

# Create mock ORCA output with potential coordinate hijacking
mock_orca_output = """
ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -193.123456789

MULLIKEN ATOMIC CHARGES:
    0   C   -0.2000
    1   C   -0.1950
    2   C   -0.2050
    3   C   -0.1950
    4   C   -0.2050
---
Sum of atomic charges = -1.00000

LÖWDIN ATOMIC CHARGES:
    0   C   -0.1800
    1   C   -0.1750
    2   C   -0.1850
    3   C   -0.1750
    4   C   -0.1850
---
Sum of atomic charges = -0.90000

FINAL GEOMETRY:
0 C    0.00    1.00    0.00
1 C    1.00    0.50    0.00
2 C    0.75   -0.75    0.00
3 C   -0.75   -0.75    0.00
4 C   -1.00    0.50    0.00
---

ORCA finished
"""

# Write temp file
out_path = Path("/tmp/test_cyclopentadienyl.out")
out_path.write_text(mock_orca_output, encoding='utf-8')

# Extract Mulliken charges
print("📊 Extracting Mulliken charges...")
extractor = MullikenChargeExtractor()
mulliken_charges = extractor.extract_from_out_file(out_path)

print(f"\n✅ Mulliken charges extracted:")
print(f"   Data: {mulliken_charges}")
print(f"   Count: {len(mulliken_charges)}")

total_charge = sum(mulliken_charges.values())
print(f"\n🔍 CHARGE VALIDATION:")
print(f"   Total charge: {total_charge:.4f}")

# ✅ CRITICAL VERIFICATION
if abs(total_charge - (-1.0)) < 0.0001:
    print(f"\n✅ SUCCESS: Total charge = -1.0000 (PRESERVED!)")
    print(f"   Coordinate hijacking is FIXED!")
    success = True
else:
    print(f"\n❌ FAILURE: Total charge = {total_charge:.4f} (should be -1.0000)")
    print(f"   Coordinates were hijacked as charges!")
    success = False

# Verify charge values are NOT coordinates
print(f"\n🔬 DATA INTEGRITY CHECK:")
expected_charges = [-0.2, -0.195, -0.205, -0.195, -0.205]
actual_charges = [mulliken_charges.get(i, 0.0) for i in range(5)]
print(f"   Expected: {expected_charges}")
print(f"   Actual:   {actual_charges}")

# These are the geometry X,Y,Z coordinates that COULD have been hijacked
hijack_coords = [0.00, 1.00, 0.75, -0.75, -1.00]  # X coordinates
print(f"\n⚠️  HIJACKING ATTACK VECTORS (X-coordinates):")
print(f"   {hijack_coords}")
print(f"   Are any of these in actual_charges? {any(coord in [round(c, 2) for c in actual_charges] for coord in hijack_coords)}")

if not any(coord in [round(c, 2) for c in actual_charges] for coord in hijack_coords):
    print(f"   ✅ NO HIJACKING DETECTED!")
else:
    print(f"   ❌ HIJACKING DETECTED!")
    success = False

# ============================================================================
# TEST 2: Full Analysis with ElectronDensityAnalyzer
# ============================================================================

print("\n" + "="*70)
print("TEST 2: Full Analysis Pipeline (ElectronDensityAnalyzer)")
print("="*70)

atom_positions = {
    (0.0, 1.0): 0,
    (1.0, 0.5): 1,
    (0.75, -0.75): 2,
    (-0.75, -0.75): 3,
    (-1.0, 0.5): 4,
}

atom_symbols = {0: "C", 1: "C", 2: "C", 3: "C", 4: "C"}

analyzer = ElectronDensityAnalyzer()
try:
    density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
    
    print(f"\n✅ Analysis complete:")
    print(f"   Atoms: {density_map.num_atoms}")
    print(f"   Total charge: {density_map.total_charge:.4f}")
    
    if abs(density_map.total_charge - (-1.0)) < 0.0001:
        print(f"\n✅ FINAL VERIFICATION: Total charge = -1.0000")
        print(f"   All data integrity checks PASSED!")
    else:
        print(f"\n❌ FINAL VERIFICATION: Total charge = {density_map.total_charge:.4f}")
        success = False
        
except Exception as e:
    print(f"\n❌ Analysis failed: {e}")
    success = False

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*70)
if success:
    print("✅✅✅ ALL TESTS PASSED: STRICT COLUMN CHECK WORKS! ✅✅✅")
    print("\nProof:")
    print(f"  1. Mulliken charges correctly extracted: {list(mulliken_charges.values())}")
    print(f"  2. Total charge preserved: {sum(mulliken_charges.values()):.4f} == -1.0000")
    print(f"  3. Coordinate hijacking prevented: len(parts) == 3 check")
    print(f"  4. Geometry data (5 columns) correctly rejected from Mulliken")
else:
    print("❌ TEST FAILED")
print("="*70)

# Cleanup
out_path.unlink()

exit(0 if success else 1)
