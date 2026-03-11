#!/usr/bin/env python
"""Minimal test for pyridine extraction"""
import sys
import tempfile
from pathlib import Path

# Mock ORCA output for pyridine
MOCK_OUTPUT = """ORCA 5.0.0
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

ORCA finished
"""

def main():
    # Write temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
        f.write(MOCK_OUTPUT)
        out_path = Path(f.name)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        print("=" * 70)
        print("TEST: Pyridine (C5H5N) - Mulliken charge extraction")
        print("=" * 70)
        print(f"\nTest file: {out_path}\n")
        
        atom_positions = {
            (0.0, 1.14): 0,   # N
            (1.12, 0.40): 1,  # ortho-C
            (1.12, -0.99): 2, # meta-C
            (0.0, -1.73): 3,  # para-C
            (-1.12, -0.99): 4,# meta-C
            (-1.12, 0.40): 5, # ortho-C
            (1.90, 0.85): 6,  # H on C1
            (1.90, -1.55): 7, # H on C2
            (0.0, -2.50): 8,  # H on C3
            (-1.90, -1.55): 9,# H on C4
            (-1.90, 0.85): 10, # H on C5
        }
        
        atom_symbols = {0: "N", 1: "C", 2: "C", 3: "C", 4: "C", 5: "C",
                        6: "H", 7: "H", 8: "H", 9: "H", 10: "H"}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        # Detailed output
        print(f"\n[EXTRACTION RESULTS]")
        print(f"  Total atoms extracted: {len(density_map.atom_densities)}")
        print(f"  Expected atoms: 11")
        
        if len(density_map.atom_densities) == 11:
            print(f"  ✅ Atom count CORRECT")
        else:
            print(f"  ❌ Atom count MISMATCH")
            print(f"     Expected: 11, Got: {len(density_map.atom_densities)}")
        
        # Show charges
        print(f"\n[MULLIKEN CHARGES]")
        charges = []
        for density in density_map.atom_densities:
            charges.append(density.mulliken_charge)
            atom_label = {0: "N", 1: "C1", 2: "C2", 3: "C3", 4: "C4", 5: "C5"}.get(
                density.atom_index, f"H{density.atom_index-5}")
            print(f"  {density.atom_index:2d} {atom_label:3s}: {density.mulliken_charge:+.4f}")
        
        total_charge = density_map.total_charge
        print(f"\n[CHARGE CONSERVATION]")
        print(f"  Total molecular charge: {total_charge:.4f}")
        print(f"  Expected: 0.0000")
        if abs(total_charge) < 0.001:
            print(f"  ✅ Charge conservation: OK")
        else:
            print(f"  ❌ Charge conservation: FAILED")
        
        # Final result
        print(f"\n" + "=" * 70)
        if len(density_map.atom_densities) == 11 and abs(total_charge) < 0.001:
            print(f"✅ TEST PASSED: Pyridine extracted with 11 atoms, charge = 0.0000")
        else:
            print(f"❌ TEST FAILED:")
            if len(density_map.atom_densities) != 11:
                print(f"   - Atom count: {len(density_map.atom_densities)} (expected 11)")
            if abs(total_charge) >= 0.001:
                print(f"   - Total charge: {total_charge:.4f} (expected 0.0000)")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        out_path.unlink()

if __name__ == "__main__":
    main()
