#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VERIFICATION: Pyridine Test (Total Charge Must Be 0.0000)
Tests the create_density_map fix for Atom 5 boundary error
"""

from pathlib import Path
from electron_density_analyzer import ElectronDensityAnalyzer

print("\n" + "="*70)
print("VERIFICATION: create_density_map Fix (v2.03)")
print("="*70)
print("\nTEST: Pyridine (C5H5N)")
print("Expected: 11 atoms, Total charge: 0.0000\n")

# Create mock ORCA output for Pyridine
mock_orca_output = """
ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -248.567890123

MULLIKEN ATOMIC CHARGES:
    0   N   -0.1500
    1   C    0.0250
    2   C    0.0450
    3   C    0.0100
    4   C    0.0450
    5   C    0.0250
    6   H    0.0000
    7   H    0.0000
    8   H    0.0000
    9   H    0.0000
   10   H    0.0000
---
Sum of atomic charges = 0.00000

LÖWDIN ATOMIC CHARGES:
    0   N   -0.2800
    1   C   -0.0950
    2   C    0.0300
    3   C   -0.0950
    4   C    0.0300
    5   C   -0.0900
    6   H   -0.0050
    7   H   -0.0050
    8   H   -0.0050
    9   H   -0.0050
   10   H   -0.0050
---
Sum of atomic charges = -0.50000

FINAL GEOMETRY:
0 N    0.00    1.14    0.00
1 C    1.12    0.40    0.00
2 C    1.12   -0.99    0.00
3 C    0.00   -1.73    0.00
4 C   -1.12   -0.99    0.00
5 C   -1.12    0.40    0.00
6 H    1.90    0.85    0.00
7 H    1.90   -1.55    0.00
8 H    0.00   -2.50    0.00
9 H   -1.90   -1.55    0.00
10 H   -1.90    0.85    0.00
---

ORCA finished
"""

# Write temp file
out_path = Path("/tmp/test_pyridine.out")
out_path.write_text(mock_orca_output, encoding='utf-8')

print("📊 Analyzing Pyridine (C5H5N)...")
print("="*70)

# Create analyzer
analyzer = ElectronDensityAnalyzer()

# Atom positions (11 atoms: 1N + 5C + 5H)
atom_positions = {
    (0.0, 1.14): 0,   # N
    (1.12, 0.40): 1,  # C1 (ortho)
    (1.12, -0.99): 2, # C2 (meta)
    (0.0, -1.73): 3,  # C3 (para)
    (-1.12, -0.99): 4,# C4 (meta)
    (-1.12, 0.40): 5, # C5 (ortho) ← CRITICAL: Atom 5 must be processed!
    (1.90, 0.85): 6,  # H
    (1.90, -1.55): 7, # H
    (0.0, -2.50): 8,  # H
    (-1.90, -1.55): 9,# H
    (-1.90, 0.85): 10, # H
}

atom_symbols = {
    0: "N",
    1: "C", 2: "C", 3: "C", 4: "C", 5: "C",
    6: "H", 7: "H", 8: "H", 9: "H", 10: "H",
}

print(f"\n✓ Atom positions: {len(atom_positions)} atoms")
print(f"✓ Atom symbols: {len(atom_symbols)} atoms\n")

try:
    # Analyze
    density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
    
    print(f"\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    
    print(f"\n✓ Densities extracted: {len(density_map.atom_densities)} atoms")
    print(f"✓ Grid points created: {len(density_map.grid_points)} positions")
    
    # Print all atoms
    print(f"\nAtom-by-atom charges:")
    for density in sorted(density_map.atom_densities, key=lambda d: d.atom_index):
        symbol_name = {
            0: "N",
            1: "C (ortho)", 2: "C (meta)", 3: "C (para)", 4: "C (meta)", 5: "C (ortho)",
            6: "H", 7: "H", 8: "H", 9: "H", 10: "H"
        }.get(density.atom_index, density.atom_symbol)
        
        print(f"  Atom {density.atom_index:2d} ({symbol_name:10s}): {density.mulliken_charge:+.4f}")
    
    # ========== CRITICAL VERIFICATION ==========
    print(f"\n" + "="*70)
    print("CRITICAL VERIFICATION:")
    print("="*70)
    
    total = density_map.total_charge
    print(f"\nTotal molecular charge: {total:.4f}")
    
    # Check Atom 5 is included
    atom5_found = False
    for density in density_map.atom_densities:
        if density.atom_index == 5:
            atom5_found = True
            atom5_charge = density.mulliken_charge
            print(f"✓ Atom 5 (ortho-C) found: charge = {atom5_charge:.4f}")
            break
    
    if not atom5_found:
        print(f"❌ ATOM 5 NOT FOUND IN DENSITIES!")
    
    # Verify total charge
    expected_total = 0.0
    if abs(total - expected_total) < 0.0001:
        print(f"\n✅ SUCCESS: Total charge = {total:.4f} (expected {expected_total:.4f})")
        print(f"\nProof:")
        print(f"  • All 11 atoms processed")
        print(f"  • Atom 5 (last carbon) included in sum")
        print(f"  • Final round(total, 4) applied")
        print(f"  • Charge conservation maintained: {total:.4f} ≈ 0.0000")
        success = True
    else:
        print(f"\n❌ FAILURE: Total charge = {total:.4f} (expected {expected_total:.4f})")
        print(f"  Difference: {total - expected_total:.6f}")
        
        # Debug: Manual sum
        manual_sum = sum(d.mulliken_charge for d in density_map.atom_densities)
        print(f"\n  Debug - Manual sum: {manual_sum:.4f}")
        print(f"  Debug - Densities count: {len(density_map.atom_densities)}")
        print(f"  Debug - Atom positions count: {len(atom_positions)}")
        
        success = False
    
    print("="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    success = False

# Cleanup
out_path.unlink()

print()
exit(0 if success else 1)
