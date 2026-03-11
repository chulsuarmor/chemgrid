#!/usr/bin/env python3
"""
Diagnose the off-by-one error in charge extraction
"""
import sys
from pathlib import Path
from test_dft_analyzer import create_mock_orca_output
from electron_density_analyzer import MullikenChargeExtractor

# Create pyridine mock output
print("[DIAGNOSE] Creating mock Pyridine output...")
out_path = create_mock_orca_output("pyridine")
print(f"Mock file created at: {out_path}\n")

# Read and display the content
print("[DIAGNOSE] File content (first 50 lines):")
with open(out_path, 'r') as f:
    lines = f.readlines()
    for i, line in enumerate(lines[:50]):
        print(f"{i:3d}: {line.rstrip()}")

print(f"\nTotal lines in file: {len(lines)}\n")

# Extract charges using MullikenChargeExtractor
print("[DIAGNOSE] Extracting Mulliken charges...")
charges = MullikenChargeExtractor.extract_from_out_file(out_path)

print(f"Extracted {len(charges)} charges:")
for atom_idx in sorted(charges.keys()):
    print(f"  Atom {atom_idx}: {charges[atom_idx]}")

print(f"\nExpected: 11 atoms (N + 5C + 5H)")
print(f"Got: {len(charges)} atoms")

if len(charges) == 11:
    print("\n✓ SUCCESS: All 11 atoms extracted!")
else:
    print(f"\n✗ FAIL: Missing {11 - len(charges)} atoms!")
    print("\nDEBUG: Let's check the MULLIKEN section in detail:")
    
    # Find MULLIKEN section
    for i, line in enumerate(lines):
        if "MULLIKEN ATOMIC CHARGES" in line:
            print(f"\nMULLIKEN section starts at line {i}:")
            for j in range(i, min(i+20, len(lines))):
                print(f"{j:3d}: {lines[j].rstrip()}")
            break

# Cleanup
out_path.unlink()
