#!/usr/bin/env python3
"""Quick test for Azulene H parsing fix"""

from pathlib import Path
import re

# Test mock Azulene data
azulene_mock = """
ORCA 5.0.0
SCF CONVERGENCE:
THE OPTIMIZATION HAS CONVERGED

FINAL SINGLE POINT ENERGY    -384.234567890

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
   10   H    0.0320
   11   H    0.0310
   12   H    0.0300
   13   H    0.0315
   14   H    0.0305
   15   H    0.0310
   16   H    0.0320
   17   H    0.0315

LÖWDIN ATOMIC CHARGES:
    0   C    0.0650

"""

print("="*60)
print("TESTING MULLIKEN CHARGE EXTRACTION")
print("Expected: 18 atoms (C0-C9, H10-H17)")
print("="*60)

lines = azulene_mock.split('\n')
charges = {}

# Find Mulliken section
mulliken_start = None
for i, line in enumerate(lines):
    if "MULLIKEN ATOMIC CHARGES" in line:
        mulliken_start = i + 1
        break

if mulliken_start is not None:
    print(f"\nFound MULLIKEN section at line {mulliken_start}")
    
    # OLD WAY (BROKEN): while symbol changes
    print("\n[OLD WAY - BROKEN]:")
    prev_symbol = None
    count_old = 0
    for line in lines[mulliken_start:mulliken_start + 50]:
        if not line.strip():
            print("  → Empty line, STOPPING (but H not parsed yet!)")
            break
        
        parts = line.split()
        if len(parts) >= 3:
            symbol = parts[1]
            if prev_symbol is not None and symbol != prev_symbol:
                print(f"  → Symbol changed from {prev_symbol} to {symbol}, STOPPING (WRONG!)")
                break
            prev_symbol = symbol
            charge = float(parts[2])
            count_old += 1
            print(f"  ✓ Atom {parts[0]:2s} ({symbol}): {charge:.4f}")
    
    print(f"\nOLD WAY Result: Parsed {count_old} atoms ❌ (should be 18)")
    
    # NEW WAY (FIXED): while empty line or separator
    print("\n[NEW WAY - FIXED]:")
    charges = {}
    for line in lines[mulliken_start:mulliken_start + 50]:
        # Empty line signals end
        if not line.strip():
            print("  → Empty line, STOPPING (correctly!)")
            break
        
        # Colon is optional
        match = re.match(
            r'^\s*(\d+)\s+([A-Z][a-z]?)\s*:?\s*([-+]?\d*\.?\d+)',
            line
        )
        
        if match:
            atom_idx = int(match.group(1))
            symbol = match.group(2)
            charge = float(match.group(3))
            charges[atom_idx] = round(charge, 4)
            print(f"  ✓ Atom {atom_idx:2d} ({symbol}): {charge:.4f}")
    
    print(f"\nNEW WAY Result: Parsed {len(charges)} atoms ✅")
    print(f"Expected: 18, Got: {len(charges)}")
    
    # Validate
    if len(charges) == 18:
        total = sum(charges.values())
        print(f"\n✅ SUCCESS!")
        print(f"   - All 18 atoms parsed (C10 + H8)")
        print(f"   - Total charge: {total:.4f}")
    else:
        print(f"\n❌ FAILED!")
        print(f"   - Expected 18 atoms, got {len(charges)}")

print("\n" + "="*60)
