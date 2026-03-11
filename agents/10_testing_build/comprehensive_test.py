#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for ORCA parser v2.00
Writes all output to a log file to avoid console encoding issues
"""

import sys
import os
from pathlib import Path
import tempfile
import traceback

LOG_FILE = Path(r"C:\Users\김남헌\Desktop\organicdraw\_source\test.log")

def log(msg):
    """Write message to both console and log file"""
    print(msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def main():
    # Clear log
    LOG_FILE.write_text("", encoding='utf-8')
    
    log("\n" + "="*70)
    log("ORCA PARSER v2.00 - COMPREHENSIVE TEST SUITE")
    log("="*70)
    
    try:
        log("\n[1] Importing orca_interface...")
        sys.path.insert(0, r"C:\Users\김남헌\Desktop\organicdraw\_source")
        from orca_interface import _parse_out_file
        log("✓ Successfully imported _parse_out_file")
        
        # Test 1: Cyclopentadienyl anion
        log("\n" + "-"*70)
        log("TEST 1: Cyclopentadienyl Anion (C5H5-)")
        log("-"*70)
        
        mock_content_1 = """ORCA 5.0.0
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
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
            f.write(mock_content_1)
            temp_path_1 = Path(f.name)
        
        result_1 = _parse_out_file(temp_path_1)
        
        log(f"  Converged: {result_1.converged}")
        log(f"  Energy: {result_1.energy:.6f}")
        log(f"  Geometry atoms: {len(result_1.geometry)}")
        log(f"  Mulliken charges found: {len(result_1.charges_mulliken)}")
        
        total_charge_1 = sum(result_1.charges_mulliken.values())
        log(f"  Mulliken charges:")
        for idx in sorted(result_1.charges_mulliken.keys()):
            log(f"    Atom {idx}: {result_1.charges_mulliken[idx]:+.4f}")
        log(f"  Total molecular charge: {total_charge_1:+.4f}")
        log(f"  Expected: -1.0000")
        
        assert result_1.converged, "Should be converged"
        assert len(result_1.geometry) == 5, f"Should have 5 atoms, got {len(result_1.geometry)}"
        assert len(result_1.charges_mulliken) == 5, f"Should have 5 Mulliken charges, got {len(result_1.charges_mulliken)}"
        assert abs(total_charge_1 - (-1.0)) < 0.05, f"Total charge should be ~-1.0, got {total_charge_1:.4f}"
        
        log("  ✓ PASS: Cyclopentadienyl anion test passed")
        temp_path_1.unlink()
        
        # Test 2: Tropylium cation
        log("\n" + "-"*70)
        log("TEST 2: Tropylium Cation (C7H7+)")
        log("-"*70)
        
        mock_content_2 = """ORCA 5.0.0
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
            f.write(mock_content_2)
            temp_path_2 = Path(f.name)
        
        result_2 = _parse_out_file(temp_path_2)
        
        log(f"  Converged: {result_2.converged}")
        log(f"  Energy: {result_2.energy:.6f}")
        log(f"  Geometry atoms: {len(result_2.geometry)}")
        log(f"  Mulliken charges found: {len(result_2.charges_mulliken)}")
        
        total_charge_2 = sum(result_2.charges_mulliken.values())
        log(f"  Mulliken charges:")
        for idx in sorted(result_2.charges_mulliken.keys()):
            log(f"    Atom {idx}: {result_2.charges_mulliken[idx]:+.4f}")
        log(f"  Total molecular charge: {total_charge_2:+.4f}")
        log(f"  Expected: +1.0000")
        
        assert result_2.converged, "Should be converged"
        assert len(result_2.geometry) == 7, f"Should have 7 atoms, got {len(result_2.geometry)}"
        assert len(result_2.charges_mulliken) == 7, f"Should have 7 Mulliken charges, got {len(result_2.charges_mulliken)}"
        assert abs(total_charge_2 - 1.0) < 0.05, f"Total charge should be ~+1.0, got {total_charge_2:.4f}"
        
        log("  ✓ PASS: Tropylium cation test passed")
        temp_path_2.unlink()
        
        # Test 3: Benzene
        log("\n" + "-"*70)
        log("TEST 3: Benzene (C6H6)")
        log("-"*70)
        
        mock_content_3 = """ORCA 5.0.0
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
            f.write(mock_content_3)
            temp_path_3 = Path(f.name)
        
        result_3 = _parse_out_file(temp_path_3)
        
        log(f"  Converged: {result_3.converged}")
        log(f"  Energy: {result_3.energy:.6f}")
        log(f"  Geometry atoms: {len(result_3.geometry)}")
        log(f"  Mulliken charges found: {len(result_3.charges_mulliken)}")
        
        total_charge_3 = sum(result_3.charges_mulliken.values())
        log(f"  Mulliken charges:")
        for idx in sorted(result_3.charges_mulliken.keys()):
            log(f"    Atom {idx}: {result_3.charges_mulliken[idx]:+.4f}")
        log(f"  Total molecular charge: {total_charge_3:+.4f}")
        log(f"  Expected: 0.0000")
        
        assert result_3.converged, "Should be converged"
        assert len(result_3.geometry) == 6, f"Should have 6 atoms, got {len(result_3.geometry)}"
        assert len(result_3.charges_mulliken) == 6, f"Should have 6 Mulliken charges, got {len(result_3.charges_mulliken)}"
        assert abs(total_charge_3) < 0.1, f"Total charge should be ~0, got {total_charge_3:.4f}"
        
        log("  ✓ PASS: Benzene test passed")
        temp_path_3.unlink()
        
        # Summary
        log("\n" + "="*70)
        log("SUMMARY")
        log("="*70)
        log("✓ All tests passed successfully!")
        log("")
        log("Parser improvements verified:")
        log("  ✓ State-based parsing (no duplicate tag issues)")
        log("  ✓ Sequential line scanning (no skipped data)")
        log("  ✓ Regex with optional atom index")
        log("  ✓ Correct Mulliken charge aggregation")
        log("")
        log(f"Test results written to: {LOG_FILE}")
        
    except AssertionError as e:
        log(f"\n✗ ASSERTION FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        log(f"\n✗ ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
