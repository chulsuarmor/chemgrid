#!/usr/bin/env python
"""Quick debug script to test Mulliken extraction"""

from pathlib import Path
from electron_density_analyzer import MullikenChargeExtractor, ElectronDensityAnalyzer
import tempfile

# Create test mock data for Pyridine
mock_data = """
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

# Write to temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
    f.write(mock_data)
    temp_path = Path(f.name)

try:
    # Test MullikenChargeExtractor
    print("=" * 60)
    print("Testing MullikenChargeExtractor")
    print("=" * 60)
    
    extractor = MullikenChargeExtractor()
    charges = extractor.extract_from_out_file(temp_path)
    print(f"\nExtracted {len(charges)} Mulliken charges:")
    for idx in sorted(charges.keys()):
        print(f"  Atom {idx}: {charges[idx]:.4f}")
    
    total = sum(charges.values())
    print(f"\nTotal molecular charge: {total:.4f}")
    
    # Test full analyzer
    print("\n" + "=" * 60)
    print("Testing ElectronDensityAnalyzer")
    print("=" * 60)
    
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
    density_map = analyzer.analyze_orca_output(temp_path, atom_positions, atom_symbols)
    
    print(f"\nAnalyzer Results:")
    print(f"  Total atoms in density map: {len(density_map.atom_densities)}")
    print(f"  Total molecular charge: {density_map.total_charge:.4f}")
    print(f"\nAtom Details:")
    for density in density_map.atom_densities:
        print(f"  Atom {density.atom_index}({density.atom_symbol}): mulliken={density.mulliken_charge:.4f}")

finally:
    temp_path.unlink()
    print("\nDebug complete!")
