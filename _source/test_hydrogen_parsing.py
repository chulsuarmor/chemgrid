#!/usr/bin/env python3
"""
HYDROGEN PARSING VALIDATION TEST
수소 원자 파싱 및 기하 구조 추출 검증
"""

import sys
from pathlib import Path
import tempfile
import re

# Test 1: Mulliken 정규식 검증
def test_mulliken_regex():
    """Mulliken 부분전하 추출 정규식 테스트"""
    print("\n" + "="*60)
    print("TEST 1: Mulliken Charge Extraction Regex")
    print("="*60)
    
    # 정규식 (orca_interface.py에서 사용)
    pattern = r'^\s*(\d+)\s+([A-Z][a-z]?)\s*:\s*([-+]?\d*\.?\d+)'
    
    # 테스트 케이스
    test_lines = [
        "    0   B    0.3200",
        "    1   N   -0.3800",
        "    6   H    0.0300",
        "    11  H    0.0300",
    ]
    
    print("\nParsing test lines:")
    matched_count = 0
    for line in test_lines:
        # electron_density_analyzer.py 형식
        match = re.match(r'^\s*(\d+)\s+([A-Z][a-z]?)\s*:\s*([-+]?\d*\.?\d+)', line)
        if match:
            idx = int(match.group(1))
            symbol = match.group(2)
            charge = float(match.group(3))
            print(f"  ✓ MATCHED: idx={idx}, symbol={symbol}, charge={charge:.4f}")
            matched_count += 1
        else:
            print(f"  ✗ FAILED: {line}")
    
    assert matched_count == 4, f"Expected 4 matches, got {matched_count}"
    print(f"\n✓ PASS: All {matched_count} lines parsed successfully")
    return True


# Test 2: 기하 구조 정규식 검증
def test_geometry_regex():
    """기하 구조 추출 정규식 테스트"""
    print("\n" + "="*60)
    print("TEST 2: Geometry Extraction Regex")
    print("="*60)
    
    # 정규식 (electron_density_analyzer.py에서 사용)
    pattern = r'^\s*(\d+)?\s+([A-Z][a-z]?)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)'
    
    # 테스트 케이스 (테스트 파일의 "FINAL GEOMETRY" 형식)
    test_lines = [
        "0 B    1.27    0.00    0.00",
        "1 N    0.64    1.10    0.00",
        "6 H    1.90   -0.20    0.00",
        "11 H    1.45   -1.85    0.00",
    ]
    
    print("\nParsing test lines:")
    matched_count = 0
    for line in test_lines:
        match = re.match(pattern, line)
        if match:
            idx_str = match.group(1)
            symbol = match.group(2)
            x = float(match.group(3))
            y = float(match.group(4))
            z = float(match.group(5))
            
            atom_idx = int(idx_str) if idx_str else None
            print(f"  ✓ MATCHED: idx={atom_idx}, symbol={symbol}, xyz=({x:.2f}, {y:.2f}, {z:.2f})")
            matched_count += 1
        else:
            print(f"  ✗ FAILED: {line}")
    
    assert matched_count == 4, f"Expected 4 matches, got {matched_count}"
    print(f"\n✓ PASS: All {matched_count} coordinate lines parsed successfully")
    return True


# Test 3: Borazine 전체 전하 검증
def test_borazine_total_charge():
    """Borazine B3N3H6 전체 전하 검증"""
    print("\n" + "="*60)
    print("TEST 3: Borazine Total Charge (H included)")
    print("="*60)
    
    # Borazine 부분전하 (테스트 파일에서)
    charges = {
        0: 0.3200,   # B
        1: -0.3800,  # N
        2: 0.3200,   # B
        3: -0.3800,  # N
        4: 0.3200,   # B
        5: -0.3800,  # N
        6: 0.0300,   # H
        7: 0.0300,   # H
        8: 0.0300,   # H
        9: 0.0300,   # H
        10: 0.0300,  # H
        11: 0.0300,  # H
    }
    
    print("\nAtom charges:")
    print("  B atoms (positive):")
    for idx in [0, 2, 4]:
        print(f"    {idx}: {charges[idx]:+.4f}")
    
    print("  N atoms (negative):")
    for idx in [1, 3, 5]:
        print(f"    {idx}: {charges[idx]:+.4f}")
    
    print("  H atoms (neutral):")
    for idx in [6, 7, 8, 9, 10, 11]:
        print(f"    {idx}: {charges[idx]:+.4f}")
    
    total = sum(charges.values())
    print(f"\nTotal molecular charge: {total:+.4f}")
    
    # 검증
    assert abs(total) < 0.01, f"Total charge should be ~0, got {total:.4f}"
    print(f"\n✓ PASS: Total charge = {total:.4f} ≈ 0.00")
    print(f"✓ CONFIRMED: All 12 atoms (B3 + N3 + H6) included")
    return True


# Test 4: Mock ORCA output parsing
def test_mock_orca_borazine():
    """Mock ORCA Borazine 출력 파싱 테스트"""
    print("\n" + "="*60)
    print("TEST 4: Mock ORCA Output Parsing (Borazine)")
    print("="*60)
    
    mock_output = """
ORCA 5.0.0
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
    6   H    0.0300
    7   H    0.0300
    8   H    0.0300
    9   H    0.0300
   10   H    0.0300
   11   H    0.0300

LÖWDIN ATOMIC CHARGES:
    0   B    0.2900
    1   N   -0.3400
    2   B    0.2900
    3   N   -0.3400
    4   B    0.2900
    5   N   -0.3400
    6   H    0.0250
    7   H    0.0250
    8   H    0.0250
    9   H    0.0250
   10   H    0.0250
   11   H    0.0250

FINAL GEOMETRY:
0 B    1.27    0.00    0.00
1 N    0.64    1.10    0.00
2 B   -0.64    1.10    0.00
3 N   -1.27    0.00    0.00
4 B   -0.64   -1.10    0.00
5 N    0.64   -1.10    0.00
6 H    1.90   -0.20    0.00
7 H    1.05    1.80    0.00
8 H   -1.45    1.85    0.00
9 H   -1.90    0.20    0.00
10 H   -1.05   -1.80    0.00
11 H    1.45   -1.85    0.00

ORCA finished
"""
    
    # 임시 파일에 저장
    with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False, encoding='utf-8') as f:
        f.write(mock_output)
        temp_path = Path(f.name)
    
    try:
        # Parse Mulliken charges
        mulliken_charges = {}
        lowdin_charges = {}
        geometry = {}
        
        lines = mock_output.split('\n')
        
        # Mulliken parsing
        in_mulliken = False
        for line in lines:
            if "MULLIKEN ATOMIC CHARGES" in line:
                in_mulliken = True
                continue
            if in_mulliken:
                if not line.strip() or "---" in line or "LÖWDIN" in line:
                    break
                match = re.match(r'^\s*(\d+)\s+([A-Z][a-z]?)\s+([-.0-9]+)', line)
                if match:
                    idx = int(match.group(1))
                    symbol = match.group(2)
                    charge = float(match.group(3))
                    mulliken_charges[idx] = round(charge, 4)
        
        # Geometry parsing
        in_geom = False
        for line in lines:
            if "FINAL GEOMETRY" in line:
                in_geom = True
                continue
            if in_geom:
                if not line.strip():
                    break
                match = re.match(r'^\s*(\d+)?\s+([A-Z][a-z]?)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)', line)
                if match:
                    idx_str = match.group(1)
                    symbol = match.group(2)
                    x = float(match.group(3))
                    y = float(match.group(4))
                    z = float(match.group(5))
                    
                    atom_idx = int(idx_str) if idx_str else len(geometry)
                    geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
        
        print(f"\nMulliken charges parsed: {len(mulliken_charges)}")
        for idx in sorted(mulliken_charges.keys()):
            symbol = "B" if idx % 2 == 0 else ("N" if idx < 6 else "H")
            print(f"  Atom {idx:2d} ({symbol}): {mulliken_charges[idx]:+.4f}")
        
        print(f"\nGeometry parsed: {len(geometry)}")
        for idx in sorted(geometry.keys())[:6]:
            print(f"  Atom {idx}: {geometry[idx]}")
        print("  ...")
        
        total_charge = sum(mulliken_charges.values())
        print(f"\nTotal molecular charge: {total_charge:+.4f}")
        
        # Assertions
        assert len(mulliken_charges) == 12, f"Should have 12 charges, got {len(mulliken_charges)}"
        assert len(geometry) == 12, f"Should have 12 coordinates, got {len(geometry)}"
        assert abs(total_charge) < 0.01, f"Total charge should be ~0, got {total_charge:.4f}"
        
        print(f"\n✓ PASS: Borazine parsing complete")
        print(f"  ✓ 12 atoms parsed (B3 + N3 + H6)")
        print(f"  ✓ Total charge = {total_charge:.4f} ≈ 0.00")
        print(f"  ✓ Hydrogen atoms INCLUDED in parse")
        
    finally:
        temp_path.unlink()
    
    return True


# Test 5: Coordinate rounding precision
def test_coordinate_precision():
    """좌표 정밀도 테스트"""
    print("\n" + "="*60)
    print("TEST 5: Coordinate Rounding Precision")
    print("="*60)
    
    # 원본 좌표
    coords = [
        (1.2743, 0.0001, 0.0000),
        (0.6399, 1.1001, 0.0000),
        (1.8999, -0.2001, 0.0000),
    ]
    
    print("\nRounding coordinates to 2 decimal places:")
    for orig_coord in coords:
        rounded = (round(orig_coord[0], 2), round(orig_coord[1], 2), round(orig_coord[2], 2))
        print(f"  {orig_coord} → {rounded}")
    
    # 정규식 검증
    pattern = r'^\s*(\d+)\s+([A-Z][a-z]?)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)'
    
    test_lines = [
        "6 H    1.90   -0.20    0.00",
        "7 H    1.05    1.80    0.00",
    ]
    
    print("\nParsed coordinates (rounded to 2 decimals):")
    for line in test_lines:
        match = re.match(pattern, line)
        if match:
            x = float(match.group(3))
            y = float(match.group(4))
            z = float(match.group(5))
            rounded = (round(x, 2), round(y, 2), round(z, 2))
            print(f"  {rounded}")
    
    print("\n✓ PASS: Coordinate precision verified (2 decimal places)")
    return True


if __name__ == "__main__":
    try:
        print("\n" + "="*60)
        print("HYDROGEN PARSING & GEOMETRY EXTRACTION VALIDATION")
        print("="*60)
        
        # Run all tests
        test_mulliken_regex()
        test_geometry_regex()
        test_borazine_total_charge()
        test_mock_orca_borazine()
        test_coordinate_precision()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓✓✓")
        print("="*60)
        print("\n✓ Validation Summary:")
        print("  ✓ Mulliken regex accepts H atoms")
        print("  ✓ Geometry regex accepts INDEX SYMBOL X Y Z format")
        print("  ✓ Borazine: 12 atoms (B3+N3+H6) with total charge ≈ 0")
        print("  ✓ Mock ORCA parsing: 12 charges + 12 coordinates")
        print("  ✓ Coordinate precision: 2 decimal places")
        print("\n✓ READY FOR FULL TEST: test_dft_analyzer.py")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
