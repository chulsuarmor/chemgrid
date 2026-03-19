#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Additional molecule tests for ORCA parser v2.00

Tests 7 additional aromatic molecules:
1. Fulvene (C₅H₄=C=CH₂)
2. Borazine (B₃N₃H₆)
3. Naphthalene (C₁₀H₈)
4. Pyrrole (C₄H₅N)
5. Pyridine (C₅H₅N)
6. Azulene (C₁₀H₈)
7. Tropylium cation (C₇H₇⁺)

Expected charges and validations included.
"""

import sys
import tempfile
from pathlib import Path

LOG_FILE = Path(r"C:\Users\김남헌\Desktop\organicdraw\_source\additional_molecules_test.log")

def log(msg):
    """Write to log file"""
    print(msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

# Mock ORCA outputs for additional molecules

FULVENE_OUTPUT = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -193.562341234

MULLIKEN ATOMIC CHARGES:
    0   C   -0.1500
    1   C   -0.1400
    2   C   -0.1450
    3   C   -0.1400
    4   C   -0.1200
    5   C    0.2950

LÖWDIN ATOMIC CHARGES:
    0   C   -0.1200
    1   C   -0.1100
    2   C   -0.1150
    3   C   -0.1100
    4   C   -0.0900
    5   C    0.2450

FINAL STRUCTURE:
0 C    0.00    1.00    0.00
1 C    1.00    0.50    0.00
2 C    0.75   -0.75    0.00
3 C   -0.75   -0.75    0.00
4 C   -1.00    0.50    0.00
5 C    0.00    0.00    0.00

ORCA finished
"""

BORAZINE_OUTPUT = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -187.234567890

MULLIKEN ATOMIC CHARGES:
    0   B    0.2100
    1   N   -0.2100
    2   B    0.2100
    3   N   -0.2100
    4   B    0.2100
    5   N   -0.2100

LÖWDIN ATOMIC CHARGES:
    0   B    0.1900
    1   N   -0.1900
    2   B    0.1900
    3   N   -0.1900
    4   B    0.1900
    5   N   -0.1900

FINAL STRUCTURE:
0 B    1.40    0.00    0.00
1 N    0.70    1.21    0.00
2 B   -0.70    1.21    0.00
3 N   -1.40    0.00    0.00
4 B   -0.70   -1.21    0.00
5 N    0.70   -1.21    0.00

ORCA finished
"""

NAPHTHALENE_OUTPUT = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -384.876543210

MULLIKEN ATOMIC CHARGES:
    0   C   -0.0080
    1   C   -0.0120
    2   C   -0.0100
    3   C   -0.0090
    4   C   -0.0100
    5   C   -0.0110
    6   C   -0.0100
    7   C   -0.0120
    8   C   -0.0090
    9   C   -0.0090

LÖWDIN ATOMIC CHARGES:
    0   C   -0.0060
    1   C   -0.0090
    2   C   -0.0080
    3   C   -0.0070
    4   C   -0.0080
    5   C   -0.0085
    6   C   -0.0080
    7   C   -0.0090
    8   C   -0.0070
    9   C   -0.0070

FINAL STRUCTURE:
0 C    1.40    0.00    0.00
1 C    0.70    1.21    0.00
2 C   -0.70    1.21    0.00
3 C   -1.40    0.00    0.00
4 C   -0.70   -1.21    0.00
5 C    0.70   -1.21    0.00
6 C    2.10    1.21    0.00
7 C    2.80    0.00    0.00
8 C    2.10   -1.21    0.00
9 C    0.70   -2.42    0.00

ORCA finished
"""

PYRROLE_OUTPUT = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -210.567234567

MULLIKEN ATOMIC CHARGES:
    0   N   -0.3200
    1   C   -0.0850
    2   C   -0.0900
    3   C   -0.0850
    4   C   -0.0800

LÖWDIN ATOMIC CHARGES:
    0   N   -0.2800
    1   C   -0.0650
    2   C   -0.0700
    3   C   -0.0650
    4   C   -0.0600

FINAL STRUCTURE:
0 N    0.00    0.50    0.00
1 C    1.00    0.10    0.00
2 C    1.00   -1.10    0.00
3 C    0.00   -1.50    0.00
4 C   -1.00   -1.10    0.00

ORCA finished
"""

PYRIDINE_OUTPUT = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -247.234567890

MULLIKEN ATOMIC CHARGES:
    0   N   -0.3100
    1   C   -0.0750
    2   C   -0.0900
    3   C   -0.0750
    4   C   -0.0900
    5   C   -0.0750

LÖWDIN ATOMIC CHARGES:
    0   N   -0.2700
    1   C   -0.0550
    2   C   -0.0700
    3   C   -0.0550
    4   C   -0.0700
    5   C   -0.0550

FINAL STRUCTURE:
0 N    0.00    0.00    0.00
1 C    1.20    0.70    0.00
2 C    1.20    2.10    0.00
3 C    0.00    2.80    0.00
4 C   -1.20    2.10    0.00
5 C   -1.20    0.70    0.00

ORCA finished
"""

AZULENE_OUTPUT = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -384.123456789

MULLIKEN ATOMIC CHARGES:
    0   C   -0.0450
    1   C   -0.0500
    2   C   -0.0480
    3   C   -0.0470
    4   C   -0.0490
    5   C   -0.0520
    6   C   -0.0480
    7   C   -0.0460
    8   C   -0.0470
    9   C   -0.0430

LÖWDIN ATOMIC CHARGES:
    0   C   -0.0350
    1   C   -0.0390
    2   C   -0.0370
    3   C   -0.0360
    4   C   -0.0380
    5   C   -0.0410
    6   C   -0.0370
    7   C   -0.0350
    8   C   -0.0360
    9   C   -0.0330

FINAL STRUCTURE:
0 C    0.00    1.40    0.00
1 C    1.21    0.70    0.00
2 C    1.21   -0.70    0.00
3 C    0.00   -1.40    0.00
4 C   -1.21   -0.70    0.00
5 C   -1.21    0.70    0.00
6 C    0.00   -0.00    0.00
7 C    2.42    1.40    0.00
8 C    2.42   -1.40    0.00
9 C    1.21   -2.10    0.00

ORCA finished
"""

TROPYLIUM_CATION_OUTPUT = """ORCA 5.0.0
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

FINAL STRUCTURE:
0 C    1.00    0.00    0.00
1 C    0.50    0.87    0.00
2 C   -0.50    0.87    0.00
3 C   -1.00    0.00    0.00
4 C   -0.50   -0.87    0.00
5 C    0.50   -0.87    0.00
6 C    0.00    0.00    0.00

ORCA finished
"""

# Test molecules data
TEST_MOLECULES = [
    {
        'name': 'Fulvene',
        'formula': 'C₅H₄=C=CH₂',
        'output': FULVENE_OUTPUT,
        'expected_atoms': 6,
        'expected_total_charge': 0.0,
        'charge_tolerance': 0.05
    },
    {
        'name': 'Borazine',
        'formula': 'B₃N₃H₆',
        'output': BORAZINE_OUTPUT,
        'expected_atoms': 6,
        'expected_total_charge': 0.0,
        'charge_tolerance': 0.05
    },
    {
        'name': 'Naphthalene',
        'formula': 'C₁₀H₈',
        'output': NAPHTHALENE_OUTPUT,
        'expected_atoms': 10,
        'expected_total_charge': 0.0,
        'charge_tolerance': 0.1
    },
    {
        'name': 'Pyrrole',
        'formula': 'C₄H₅N',
        'output': PYRROLE_OUTPUT,
        'expected_atoms': 5,
        'expected_total_charge': 0.0,
        'charge_tolerance': 0.1
    },
    {
        'name': 'Pyridine',
        'formula': 'C₅H₅N',
        'output': PYRIDINE_OUTPUT,
        'expected_atoms': 6,
        'expected_total_charge': 0.0,
        'charge_tolerance': 0.1
    },
    {
        'name': 'Azulene',
        'formula': 'C₁₀H₈',
        'output': AZULENE_OUTPUT,
        'expected_atoms': 10,
        'expected_total_charge': 0.0,
        'charge_tolerance': 0.1
    },
    {
        'name': 'Tropylium cation',
        'formula': 'C₇H₇⁺',
        'output': TROPYLIUM_CATION_OUTPUT,
        'expected_atoms': 7,
        'expected_total_charge': 1.0,
        'charge_tolerance': 0.05
    }
]

def test_molecule(molecule_data):
    """Test a single molecule"""
    name = molecule_data['name']
    formula = molecule_data['formula']
    output = molecule_data['output']
    expected_atoms = molecule_data['expected_atoms']
    expected_charge = molecule_data['expected_total_charge']
    tolerance = molecule_data['charge_tolerance']
    
    log(f"\n{'='*70}")
    log(f"Testing: {name} ({formula})")
    log(f"{'='*70}")
    
    try:
        from orca_interface import _parse_out_file
        
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
            f.write(output)
            temp_path = Path(f.name)
        
        # Parse
        result = _parse_out_file(temp_path)
        
        log(f"  Converged: {result.converged}")
        log(f"  Energy: {result.energy:.6f}")
        log(f"  Geometry atoms: {len(result.geometry)} (expected: {expected_atoms})")
        log(f"  Mulliken charges: {len(result.charges_mulliken)}")
        
        # Calculate total charge
        total_charge = sum(result.charges_mulliken.values())
        log(f"\n  Mulliken charges breakdown:")
        for idx in sorted(result.charges_mulliken.keys()):
            charge = result.charges_mulliken[idx]
            symbol = "N/A"  # Could extract from output if needed
            log(f"    Atom {idx}: {charge:+.4f}")
        
        log(f"\n  Total molecular charge: {total_charge:+.4f}")
        log(f"  Expected: {expected_charge:+.4f} (±{tolerance:.4f})")
        
        # Validate
        assert result.converged, "Should be converged"
        assert len(result.geometry) == expected_atoms, f"Should have {expected_atoms} atoms, got {len(result.geometry)}"
        assert len(result.charges_mulliken) == expected_atoms, f"Should have {expected_atoms} charges, got {len(result.charges_mulliken)}"
        
        charge_diff = abs(total_charge - expected_charge)
        assert charge_diff <= tolerance, f"Total charge {total_charge:.4f} should be {expected_charge:+.4f} ±{tolerance}, diff={charge_diff:.4f}"
        
        log(f"\n  ✓ PASS: {name} parsed correctly")
        temp_path.unlink()
        return True
        
    except AssertionError as e:
        log(f"\n  ✗ FAIL: {e}")
        return False
    except Exception as e:
        log(f"\n  ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    # Clear log
    LOG_FILE.write_text("", encoding='utf-8')
    
    log("\n" + "="*70)
    log("ORCA PARSER v2.00 - ADDITIONAL MOLECULES TEST SUITE")
    log("="*70)
    log("\nTesting 7 additional aromatic molecules")
    
    results = []
    for molecule in TEST_MOLECULES:
        passed = test_molecule(molecule)
        results.append((molecule['name'], passed))
    
    # Summary
    log("\n" + "="*70)
    log("SUMMARY")
    log("="*70)
    
    passed_count = sum(1 for _, passed in results if passed)
    total = len(results)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        log(f"  {status}: {name}")
    
    log(f"\nTotal: {passed_count}/{total} tests passed")
    
    if passed_count == total:
        log("\n✓ ALL TESTS PASSED!")
        log("\nAll 7 additional molecules validated successfully:")
        for name, _ in results:
            log(f"  ✓ {name}")
        return 0
    else:
        log("\n✗ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
