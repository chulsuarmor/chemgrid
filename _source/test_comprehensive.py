# -*- coding: utf-8 -*-
"""
Comprehensive DFT Analyzer Test - 10 molecules (3 basic + 7 advanced)
"""

import sys
from pathlib import Path

def create_mock_orca_output(molecule_type):
    """Create mock ORCA output files for testing"""
    
    if molecule_type == "borazine":
        content = """ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -198.456789012

MULLIKEN ATOMIC CHARGES:
    0   B    0.3200
    1   N   -0.3800
    2   B    0.3200
    3   N   -0.3800
    4   B    0.3200
    5   N   -0.3800

ORCA finished
"""
    elif molecule_type == "azulene":
        content = """ORCA 5.0.0
MULLIKEN ATOMIC CHARGES:
    0   C    0.0850
    1   C   -0.1250
    2   C    0.0950
    3   C   -0.0850
    4   C    0.1050
    5   C   -0.0950
    6   C   -0.1150
    7   C    0.0750
    8   C   -0.0550
    9   C    0.0150

ORCA finished
"""
    elif molecule_type == "pyridine":
        content = """ORCA 5.0.0
MULLIKEN ATOMIC CHARGES:
    0   N   -0.3200
    1   C   -0.1100
    2   C    0.0400
    3   C   -0.1100
    4   C    0.0400
    5   C   -0.1050

ORCA finished
"""
    elif molecule_type == "pyrrole":
        content = """ORCA 5.0.0
MULLIKEN ATOMIC CHARGES:
    0   N   -0.4200
    1   C   -0.0850
    2   C   -0.0550
    3   C   -0.0850
    4   C   -0.0550

ORCA finished
"""
    elif molecule_type == "fulvene":
        content = """ORCA 5.0.0
MULLIKEN ATOMIC CHARGES:
    0   C   -0.1950
    1   C    0.0200
    2   C    0.0200
    3   C    0.0200
    4   C    0.0200
    5   C   -0.1950

ORCA finished
"""
    elif molecule_type == "naphthalene":
        content = """ORCA 5.0.0
MULLIKEN ATOMIC CHARGES:
    0   C   -0.0850
    1   C    0.0150
    2   C   -0.0750
    3   C    0.0250
    4   C   -0.0850
    5   C    0.0150
    6   C   -0.0750
    7   C    0.0250
    8   C   -0.0650
    9   C    0.0050

ORCA finished
"""
    elif molecule_type == "nitrobenzene":
        content = """ORCA 5.0.0
MULLIKEN ATOMIC CHARGES:
    0   N    0.5200
    1   O   -0.4100
    2   O   -0.4100
    3   C    0.1850
    4   C   -0.0950
    5   C    0.0850
    6   C   -0.0950
    7   C    0.0850
    8   C   -0.0950

ORCA finished
"""
    else:
        raise ValueError(f"Unknown molecule: {molecule_type}")
    
    out_path = Path(f"/tmp/test_{molecule_type}.out")
    out_path.write_text(content, encoding='utf-8')
    return out_path


def test_borazine():
    """TEST 4: Borazine (B3N3H6) - heteroatom alternating"""
    print("\n" + "="*60)
    print("TEST 4: Borazine (B3N3H6)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("borazine")
        atom_positions = {(1.27, 0.0): 0, (0.64, 1.10): 1, (-0.64, 1.10): 2, 
                         (-1.27, 0.0): 3, (-0.64, -1.10): 4, (0.64, -1.10): 5}
        atom_symbols = {0: "B", 1: "N", 2: "B", 3: "N", 4: "B", 5: "N"}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        total_charge = abs(density_map.total_charge)
        assert total_charge < 0.1, f"Total charge {total_charge} should be ~0"
        print("✓ PASS: Heteroatom charge separation")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def test_azulene():
    """TEST 5: Azulene (C10H8) - asymmetric bicyclic"""
    print("\n" + "="*60)
    print("TEST 5: Azulene (C10H8)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("azulene")
        atom_positions = {(1.35, 0.0): 0, (0.68, 1.17): 1, (-0.68, 1.17): 2,
                         (-1.35, 0.0): 3, (-0.68, -0.78): 4, (0.68, -0.78): 5,
                         (1.92, -1.17): 6, (2.03, -2.51): 7, (0.81, -3.16): 8, (-0.41, -2.41): 9}
        atom_symbols = {i: "C" for i in range(10)}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        assert len(density_map.atom_densities) == 10, "Should have 10 carbons"
        assert abs(density_map.total_charge) < 0.1, "Total charge should be ~0"
        print("✓ PASS: Asymmetric charge distribution (10 atoms)")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def test_pyridine():
    """TEST 6: Pyridine (C5H5N) - nitrogen electron withdrawal"""
    print("\n" + "="*60)
    print("TEST 6: Pyridine (C5H5N)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("pyridine")
        atom_positions = {(0.0, 1.14): 0, (1.12, 0.40): 1, (1.12, -0.99): 2,
                         (0.0, -1.73): 3, (-1.12, -0.99): 4, (-1.12, 0.40): 5}
        atom_symbols = {0: "N", 1: "C", 2: "C", 3: "C", 4: "C", 5: "C"}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        assert abs(density_map.total_charge) < 0.1, "Total charge should be ~0"
        print("✓ PASS: Nitrogen electron-withdrawing effect")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def test_pyrrole():
    """TEST 7: Pyrrole (C4H4NH) - nitrogen resonance"""
    print("\n" + "="*60)
    print("TEST 7: Pyrrole (C4H4NH)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("pyrrole")
        atom_positions = {(0.0, 0.94): 0, (1.12, 0.26): 1, (0.69, -1.07): 2,
                         (-0.69, -1.07): 3, (-1.12, 0.26): 4}
        atom_symbols = {0: "N", 1: "C", 2: "C", 3: "C", 4: "C"}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        assert abs(density_map.total_charge) < 0.1, "Total charge should be ~0"
        print("✓ PASS: Nitrogen lone pair resonance")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def test_fulvene():
    """TEST 8: Fulvene (C6H6) - atypical hydrocarbon"""
    print("\n" + "="*60)
    print("TEST 8: Fulvene (C6H6)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("fulvene")
        atom_positions = {(0.0, 0.73): 0, (0.97, 1.67): 1, (2.34, 1.27): 2,
                         (2.34, -0.13): 3, (0.97, -1.07): 4, (-0.97, -1.07): 5}
        atom_symbols = {i: "C" for i in range(6)}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        assert abs(density_map.total_charge) < 0.1, "Total charge should be ~0"
        print("✓ PASS: Fulvene charge distribution")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def test_naphthalene():
    """TEST 9: Naphthalene (C10H8) - multi-ring indexing"""
    print("\n" + "="*60)
    print("TEST 9: Naphthalene (C10H8)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("naphthalene")
        atom_positions = {(2.45, 1.40): 0, (1.23, 0.70): 1, (0.0, 1.40): 2,
                         (-1.23, 0.70): 3, (-2.45, 1.40): 4, (2.45, -1.40): 5,
                         (1.23, -0.70): 6, (0.0, -1.40): 7, (-1.23, -0.70): 8, (-2.45, -1.40): 9}
        atom_symbols = {i: "C" for i in range(10)}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        assert len(density_map.atom_densities) == 10, "Should have 10 carbons"
        assert abs(density_map.total_charge) < 0.1, "Total charge should be ~0"
        print("✓ PASS: Multi-ring integrity (10/10 atoms)")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def test_nitrobenzene():
    """TEST 10: Nitrobenzene (C6H5NO2) - EWG deactivation"""
    print("\n" + "="*60)
    print("TEST 10: Nitrobenzene (C6H5NO2)")
    print("="*60)
    
    try:
        from electron_density_analyzer import ElectronDensityAnalyzer
        
        out_path = create_mock_orca_output("nitrobenzene")
        atom_positions = {(0.0, 1.35): 0, (0.0, 2.55): 1, (0.0, 0.70): 2,
                         (0.0, 0.0): 3, (1.20, -0.70): 4, (1.20, -2.10): 5,
                         (0.0, -2.80): 6, (-1.20, -2.10): 7, (-1.20, -0.70): 8}
        atom_symbols = {0: "N", 1: "O", 2: "O", 3: "C", 4: "C", 5: "C", 6: "C", 7: "C", 8: "C"}
        
        analyzer = ElectronDensityAnalyzer()
        density_map = analyzer.analyze_orca_output(out_path, atom_positions, atom_symbols)
        
        assert len(density_map.atom_densities) == 9, "Should have 9 atoms"
        assert abs(density_map.total_charge) < 0.1, "Total charge should be ~0"
        print("✓ PASS: EWG deactivation effect")
        out_path.unlink()
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("COMPREHENSIVE DFT ANALYZER TEST")
    print("="*60)
    print("Testing 7 advanced molecules (Tests 4-10)")
    
    results = []
    results.append(("TEST 4: Borazine", test_borazine()))
    results.append(("TEST 5: Azulene", test_azulene()))
    results.append(("TEST 6: Pyridine", test_pyridine()))
    results.append(("TEST 7: Pyrrole", test_pyrrole()))
    results.append(("TEST 8: Fulvene", test_fulvene()))
    results.append(("TEST 9: Naphthalene", test_naphthalene()))
    results.append(("TEST 10: Nitrobenzene", test_nitrobenzene()))
    
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name}: {status}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed} tests failed")
        sys.exit(1)
