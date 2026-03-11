#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Standalone test for state-based ORCA parser (v2.00)
Tests the complete rewrite of _parse_out_file()
"""

import sys
import os
from pathlib import Path
import tempfile

# Test 1: Cyclopentadienyl anion
def test_cyclopentadienyl_anion():
    print("\n" + "="*70)
    print("TEST 1: Cyclopentadienyl Anion (C5H5-)")
    print("="*70)
    
    mock_content = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -193.123456789

MULLIKEN ATOMIC CHARGES:
    0   C   -0.2000
    1   C   -0.1950
    2   C   -0.2050
    3   C   -0.1950
    4   C   -0.2050

LÖWDIN ATOMIC CHARGES:
    0   C   -0.1800
    1   C   -0.1750
    2   C   -0.1850
    3   C   -0.1750
    4   C   -0.1850

FINAL STRUCTURE (ANGSTROMS AND DEGREES):
0 C    0.00    1.00    0.00
1 C    1.00    0.50    0.00
2 C    0.75   -0.75    0.00
3 C   -0.75   -0.75    0.00
4 C   -1.00    0.50    0.00

ORCA finished
"""
    
    # Write mock file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
        f.write(mock_content)
        temp_path = Path(f.name)
    
    try:
        # Import and test
        from orca_interface import _parse_out_file
        result = _parse_out_file(temp_path)
        
        print(f"\nResults:")
        print(f"  Converged: {result.converged}")
        print(f"  Energy: {result.energy:.6f}")
        print(f"  Geometry atoms: {len(result.geometry)}")
        print(f"  Mulliken charges: {len(result.charges_mulliken)}")
        
        # Calculate total charge
        total_charge = sum(result.charges_mulliken.values())
        print(f"\n  Mulliken charges:")
        for idx in sorted(result.charges_mulliken.keys()):
            print(f"    Atom {idx}: {result.charges_mulliken[idx]:+.4f}")
        print(f"\n  Total molecular charge: {total_charge:+.4f}")
        print(f"  Expected: -1.0000")
        
        # Validate
        assert result.converged, "Should be converged"
        assert len(result.geometry) == 5, f"Should have 5 atoms, got {len(result.geometry)}"
        assert len(result.charges_mulliken) == 5, f"Should have 5 charges, got {len(result.charges_mulliken)}"
        assert abs(total_charge - (-1.0)) < 0.05, f"Total charge {total_charge} should be ~-1"
        
        print(f"\n✓ PASS: Cyclopentadienyl anion parsed correctly")
        return True
        
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        temp_path.unlink()


# Test 2: Tropylium cation
def test_tropylium_cation():
    print("\n" + "="*70)
    print("TEST 2: Tropylium Cation (C7H7+)")
    print("="*70)
    
    mock_content = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -267.987654321

MULLIKEN ATOMIC CHARGES:
    0   C    0.1430
    1   C    0.1430
    2   C    0.1430
    3   C    0.1430
    4   C    0.1430
    5   C    0.1430
    6   C    0.1430

LÖWDIN ATOMIC CHARGES:
    0   C    0.1300
    1   C    0.1300
    2   C    0.1300
    3   C    0.1300
    4   C    0.1300
    5   C    0.1300
    6   C    0.1300

FINAL GEOMETRY:
0 C    1.00    0.00    0.00
1 C    0.50    0.87    0.00
2 C   -0.50    0.87    0.00
3 C   -1.00    0.00    0.00
4 C   -0.50   -0.87    0.00
5 C    0.50   -0.87    0.00
6 C    0.00    0.00    0.00

ORCA finished
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
        f.write(mock_content)
        temp_path = Path(f.name)
    
    try:
        from orca_interface import _parse_out_file
        result = _parse_out_file(temp_path)
        
        print(f"\nResults:")
        print(f"  Converged: {result.converged}")
        print(f"  Energy: {result.energy:.6f}")
        print(f"  Geometry atoms: {len(result.geometry)}")
        print(f"  Mulliken charges: {len(result.charges_mulliken)}")
        
        # Calculate total charge
        total_charge = sum(result.charges_mulliken.values())
        print(f"\n  Mulliken charges:")
        for idx in sorted(result.charges_mulliken.keys()):
            print(f"    Atom {idx}: {result.charges_mulliken[idx]:+.4f}")
        print(f"\n  Total molecular charge: {total_charge:+.4f}")
        print(f"  Expected: +1.0000")
        
        # Validate
        assert result.converged, "Should be converged"
        assert len(result.geometry) == 7, f"Should have 7 atoms, got {len(result.geometry)}"
        assert len(result.charges_mulliken) == 7, f"Should have 7 charges, got {len(result.charges_mulliken)}"
        assert abs(total_charge - 1.0) < 0.05, f"Total charge {total_charge} should be ~+1"
        
        print(f"\n✓ PASS: Tropylium cation parsed correctly")
        return True
        
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        temp_path.unlink()


# Test 3: Benzene
def test_benzene():
    print("\n" + "="*70)
    print("TEST 3: Benzene (C6H6)")
    print("="*70)
    
    mock_content = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -230.654321098

MULLIKEN ATOMIC CHARGES:
    0   C   -0.0100
    1   C   -0.0100
    2   C   -0.0100
    3   C   -0.0100
    4   C   -0.0100
    5   C   -0.0100

LÖWDIN ATOMIC CHARGES:
    0   C   -0.0080
    1   C   -0.0080
    2   C   -0.0080
    3   C   -0.0080
    4   C   -0.0080
    5   C   -0.0080

FINAL GEOMETRY:
0 C    1.40    0.00    0.00
1 C    0.70    1.21    0.00
2 C   -0.70    1.21    0.00
3 C   -1.40    0.00    0.00
4 C   -0.70   -1.21    0.00
5 C    0.70   -1.21    0.00

ORCA finished
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
        f.write(mock_content)
        temp_path = Path(f.name)
    
    try:
        from orca_interface import _parse_out_file
        result = _parse_out_file(temp_path)
        
        print(f"\nResults:")
        print(f"  Converged: {result.converged}")
        print(f"  Energy: {result.energy:.6f}")
        print(f"  Geometry atoms: {len(result.geometry)}")
        print(f"  Mulliken charges: {len(result.charges_mulliken)}")
        
        # Calculate total charge
        total_charge = sum(result.charges_mulliken.values())
        print(f"\n  Mulliken charges:")
        for idx in sorted(result.charges_mulliken.keys()):
            print(f"    Atom {idx}: {result.charges_mulliken[idx]:+.4f}")
        print(f"\n  Total molecular charge: {total_charge:+.4f}")
        print(f"  Expected: 0.0000")
        
        # Validate
        assert result.converged, "Should be converged"
        assert len(result.geometry) == 6, f"Should have 6 atoms, got {len(result.geometry)}"
        assert len(result.charges_mulliken) == 6, f"Should have 6 charges, got {len(result.charges_mulliken)}"
        assert abs(total_charge) < 0.1, f"Total charge {total_charge} should be ~0"
        
        print(f"\n✓ PASS: Benzene parsed correctly")
        return True
        
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    print("\n" + "="*70)
    print("ORCA PARSER v2.00 - STATE-BASED PARSER VALIDATION")
    print("="*70)
    
    results = []
    results.append(("Cyclopentadienyl anion", test_cyclopentadienyl_anion()))
    results.append(("Tropylium cation", test_tropylium_cation()))
    results.append(("Benzene", test_benzene()))
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED!")
        print("\nParser improvements:")
        print("  ✓ State-based parsing (no more lines.index() errors)")
        print("  ✓ Sequential line scanning (no skipped data)")
        print("  ✓ Regex with optional atom index")
        print("  ✓ Correct charge aggregation")
        sys.exit(0)
    else:
        print("\n✗ SOME TESTS FAILED")
        sys.exit(1)
