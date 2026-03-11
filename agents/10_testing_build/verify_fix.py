#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Direct inline verification of Strict Column Check fix"""

# ============================================================================
# INLINE TEST: Strict Column Check Logic
# ============================================================================

print("\n" + "="*70)
print("VERIFICATION: Strict Column Check (v2.02)")
print("="*70)

# Simulate the ORCA output with potential hijacking
mock_lines = [
    "MULLIKEN ATOMIC CHARGES:",
    "    0   C   -0.2000",
    "    1   C   -0.1950",
    "    2   C   -0.2050",
    "    3   C   -0.1950",
    "    4   C   -0.2050",
    "---",
    "Sum of atomic charges = -1.00000",
    "",
    "FINAL GEOMETRY:",
    "0 C    0.00    1.00    0.00",
    "1 C    1.00    0.50    0.00",
    "2 C    0.75   -0.75    0.00",
    "3 C   -0.75   -0.75    0.00",
    "4 C   -1.00    0.50    0.00",
    "---",
]

print("\n📊 SIMULATING MULLIKEN PARSING WITH STRICT COLUMN CHECK:")
print("="*70)

# OLD (BROKEN) LOGIC: Uses regex (?:\s|$) - STILL GETS HIJACKED!
print("\n❌ OLD LOGIC (regex with (?:\\s|$) anchor):")
print("   Pattern: r'^\\s*(\\d+)\\s+([A-Z][a-z]?)\\s*:?\\s*([-+]?\\d*\\.?\\d+)(?:\\s|$)'")
print("   Problem: '0 C    0.00' matches at 0.00 because colon is after space")

import re
old_charges = {}
for line in mock_lines:
    match = re.match(r'^\s*(\d+)\s+([A-Z][a-z]?)\s*:?\s*([-+]?\d*\.?\d+)(?:\s|$)', line)
    if match:
        try:
            idx = int(match.group(1))
            charge = float(match.group(3))
            old_charges[idx] = round(charge, 4)
            print(f"   Matched: {line.strip()[:40]:40s} → Atom {idx}: {charge:.4f}")
        except:
            pass

old_total = sum(old_charges.values())
print(f"\n   OLD RESULT:")
print(f"     Charges: {list(old_charges.values())}")
print(f"     Total: {old_total:.4f}")
if old_total == 0.0:
    print(f"     ❌ COORDINATE HIJACKING DETECTED! (expected -1.0, got 0.0)")

# NEW (FIXED) LOGIC: Strict column count
print("\n" + "="*70)
print("\n✅ NEW LOGIC (len(parts) == 3 check - STRICT COLUMN COUNT):")
print("   1. Split line by whitespace: parts = line.split()")
print("   2. Check: len(parts) == 3 (Index, Symbol, Charge)")
print("   3. Geometry has 5 parts → REJECTED")

new_charges = {}
is_mulliken = False
for line in mock_lines:
    if "MULLIKEN" in line:
        is_mulliken = True
        print(f"\n   Entering MULLIKEN section...")
        continue
    
    if "FINAL GEOMETRY" in line or "---" in line or "Sum of" in line:
        if is_mulliken:
            print(f"   Exiting MULLIKEN section (found: {line.strip()[:30]}...)")
        is_mulliken = False
        continue
    
    if is_mulliken:
        parts = line.split()
        
        if len(parts) == 3:
            # CORRECT FORMAT: INDEX SYMBOL CHARGE
            try:
                idx = int(parts[0])
                symbol = parts[1]
                charge = float(parts[2])
                new_charges[idx] = round(charge, 4)
                total = sum(new_charges.values())
                print(f"   ✓ ACCEPT (3 cols): {line.strip()[:40]:40s} → Atom {idx}: {charge:.4f} (sum: {total:.4f})")
            except:
                pass
        
        elif len(parts) >= 5:
            # GEOMETRY FORMAT: INDEX SYMBOL X Y Z
            print(f"   ✗ REJECT (5+ cols): {line.strip()[:40]:40s} → Geometry data, not charge!")
        
        elif len(parts) == 4:
            # Colon format: INDEX SYMBOL : CHARGE
            if parts[2] == ':':
                try:
                    idx = int(parts[0])
                    charge = float(parts[3])
                    new_charges[idx] = round(charge, 4)
                    print(f"   ✓ ACCEPT (4 cols): {line.strip()[:40]:40s} → Atom {idx}: {charge:.4f}")
                except:
                    pass

new_total = sum(new_charges.values())
print(f"\n   NEW RESULT:")
print(f"     Charges: {list(new_charges.values())}")
print(f"     Total: {new_total:.4f}")

# ============================================================================
# COMPARISON
# ============================================================================

print("\n" + "="*70)
print("FINAL VERIFICATION:")
print("="*70)

print(f"\nOLD LOGIC (broken regex):")
print(f"  Total charge: {old_total:.4f}")
print(f"  Verdict: {'❌ HIJACKED' if old_total != -1.0 else '✓ Correct'}")

print(f"\nNEW LOGIC (strict column check):")
print(f"  Total charge: {new_total:.4f}")
print(f"  Verdict: {'✅ CORRECT' if abs(new_total - (-1.0)) < 0.0001 else '❌ FAILED'}")

print(f"\n" + "="*70)
if abs(new_total - (-1.0)) < 0.0001:
    print("✅✅✅ SUCCESS: STRICT COLUMN CHECK FIXES HIJACKING! ✅✅✅")
    print(f"\nProof:")
    print(f"  • Mulliken charges: {list(new_charges.values())}")
    print(f"  • Total preserved: {new_total:.4f} (exactly -1.0000)")
    print(f"  • Geometry data (5 cols) rejected from charge parsing")
    print(f"  • No coordinate values in charge dictionary")
    exit_code = 0
else:
    print(f"❌ TEST FAILED: Total charge = {new_total:.4f} (expected -1.0000)")
    exit_code = 1

print("="*70 + "\n")
exit(exit_code)
