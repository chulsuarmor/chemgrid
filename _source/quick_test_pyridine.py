#!/usr/bin/env python3
"""Quick test for Pyridine parsing with all 3 sections."""

import sys
from pathlib import Path

# Add source directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Test the parsing directly
def create_pyridine_mock():
    """Create Pyridine mock ORCA output with all 11 atoms"""
    content = """
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
    out_path = Path("/tmp/test_pyridine.out")
    out_path.write_text(content, encoding='utf-8')
    return out_path

try:
    print("=" * 70)
    print("TEST: Pyridine (C5H5N) - 3-Section Synchronization")
    print("=" * 70)
    print()
    
    # Create mock data
    out_path = create_pyridine_mock()
    print(f"✓ Created mock ORCA output: {out_path}")
    print()
    
    # Test 1: Direct parsing with orca_interface
    print("Step 1: Testing orca_interface._parse_out_file()")
    print("-" * 70)
    from orca_interface import _parse_out_file
    
    result = _parse_out_file(out_path)
    
    print(f"\n[Mulliken]  Extracted {len(result.charges_mulliken)} atomic charges")
    print(f"  Atom indices: {sorted(result.charges_mulliken.keys())}")
    print(f"  Sample: {list(result.charges_mulliken.items())[:3]}")
    
    print(f"\n[Löwdin]    Extracted {len(result.charges_lowdin)} Löwdin charges")
    print(f"  Atom indices: {sorted(result.charges_lowdin.keys())}")
    print(f"  Sample: {list(result.charges_lowdin.items())[:3]}")
    
    print(f"\n[Geometry]  Extracted {len(result.geometry)} atomic coordinates")
    print(f"  Atom indices: {sorted(result.geometry.keys())}")
    print(f"  Sample: {list(result.geometry.items())[:3]}")
    
    # Validation
    print("\n" + "=" * 70)
    print("VALIDATION")
    print("=" * 70)
    
    mulliken_count = len(result.charges_mulliken)
    lowdin_count = len(result.charges_lowdin)
    geometry_count = len(result.geometry)
    
    print(f"\n[Mulliken] {mulliken_count} atoms {'✅' if mulliken_count == 11 else '❌'}")
    print(f"[Löwdin]   {lowdin_count} atoms {'✅' if lowdin_count == 11 else '❌'}")
    print(f"[Geometry] {geometry_count} atoms {'✅' if geometry_count == 11 else '❌'}")
    
    if mulliken_count == lowdin_count == geometry_count == 11:
        print("\n✓ SUCCESS: All 3 sections have 11 atoms synchronized! ✓")
        sys.exit(0)
    else:
        print("\n✗ FAILURE: Atom counts do not match!")
        sys.exit(1)
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        Path("/tmp/test_pyridine.out").unlink()
    except:
        pass
