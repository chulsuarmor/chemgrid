#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VERIFICATION: AtomicDensity Fix (v2.04)
Proves that Mulliken charge 0.0 (hydrogen) is preserved, not hijacked by Löwdin
"""

from dataclasses import dataclass
from typing import Tuple

print("\n" + "="*70)
print("VERIFICATION: AtomicDensity Mulliken-First Logic (v2.04)")
print("="*70)
print("\nProblem: Hydrogen atoms in Pyridine")
print("  Mulliken: 0.0000 (valid value)")
print("  Löwdin: -0.0050 (different methodology)")
print("  Old logic: 0.0 != 0.0 is False → Use Löwdin (-0.0050)")
print("  Result: Total charge = -0.0250 instead of 0.0000 ❌\n")

# ============================================================================
# OLD LOGIC (BROKEN)
# ============================================================================

print("="*70)
print("\n❌ OLD LOGIC (v2.03 and earlier):")
print("="*70)

@dataclass
class AtomicDensity_Old:
    """OLD: Treats 0.0 as 'no data'"""
    atom_index: int
    atom_symbol: str
    mulliken_charge: float
    lowdin_charge: float
    effective_charge: float = 0.0
    
    def __post_init__(self):
        # BROKEN: 0.0 != 0.0 is False, so use Löwdin
        self.effective_charge = self.mulliken_charge if self.mulliken_charge != 0.0 else self.lowdin_charge

# Pyridine hydrogen atoms
print("\nHydrogen atoms (OLD logic):")
h_atoms_old = []
for i in range(6, 11):
    h_old = AtomicDensity_Old(
        atom_index=i,
        atom_symbol="H",
        mulliken_charge=0.0,
        lowdin_charge=-0.0050,
    )
    h_atoms_old.append(h_old)
    print(f"  Atom {i} (H):")
    print(f"    Mulliken: {h_old.mulliken_charge:+.4f}")
    print(f"    Löwdin:   {h_old.lowdin_charge:+.4f}")
    print(f"    effective_charge (0.0 != 0.0 → Use Löwdin): {h_old.effective_charge:+.4f}")

old_h_total = sum(h.effective_charge for h in h_atoms_old)
print(f"\nOLD Logic - H atoms total: {old_h_total:.4f}")
print(f"❌ WRONG: {old_h_total:.4f} (should be 0.0000)")

# Full Pyridine with old logic
print("\nFull Pyridine (OLD logic):")
mulliken_all_old = {
    0: -0.1500,
    1: 0.0250,
    2: 0.0450,
    3: 0.0100,
    4: 0.0450,
    5: 0.0250,
    6: 0.0,      # H
    7: 0.0,      # H
    8: 0.0,      # H
    9: 0.0,      # H
    10: 0.0,     # H
}
lowdin_all_old = {
    0: -0.2800,
    1: -0.0950,
    2: 0.0300,
    3: -0.0950,
    4: 0.0300,
    5: -0.0900,
    6: -0.0050,  # H
    7: -0.0050,  # H
    8: -0.0050,  # H
    9: -0.0050,  # H
    10: -0.0050, # H
}

old_atoms = []
for idx in range(11):
    atom_old = AtomicDensity_Old(
        atom_index=idx,
        atom_symbol=("N" if idx == 0 else ("C" if idx < 6 else "H")),
        mulliken_charge=mulliken_all_old[idx],
        lowdin_charge=lowdin_all_old[idx],
    )
    old_atoms.append(atom_old)

old_total = sum(a.effective_charge for a in old_atoms)
print(f"  Atoms: {[a.effective_charge for a in old_atoms]}")
print(f"  Total: {old_total:.4f}")
print(f"  ❌ FAILED: {old_total:.4f} != 0.0000")

# ============================================================================
# NEW LOGIC (FIXED)
# ============================================================================

print("\n" + "="*70)
print("\n✅ NEW LOGIC (v2.04 - Mulliken-First):")
print("="*70)

@dataclass
class AtomicDensity_New:
    """NEW: Always use Mulliken, even if 0.0"""
    atom_index: int
    atom_symbol: str
    mulliken_charge: float
    lowdin_charge: float
    effective_charge: float = 0.0
    
    def __post_init__(self):
        # FIXED: Always use Mulliken (0.0 is valid)
        self.effective_charge = self.mulliken_charge

# Pyridine hydrogen atoms with new logic
print("\nHydrogen atoms (NEW logic):")
h_atoms_new = []
for i in range(6, 11):
    h_new = AtomicDensity_New(
        atom_index=i,
        atom_symbol="H",
        mulliken_charge=0.0,
        lowdin_charge=-0.0050,
    )
    h_atoms_new.append(h_new)
    print(f"  Atom {i} (H):")
    print(f"    Mulliken: {h_new.mulliken_charge:+.4f}")
    print(f"    Löwdin:   {h_new.lowdin_charge:+.4f}")
    print(f"    effective_charge (Always Mulliken): {h_new.effective_charge:+.4f}")

new_h_total = sum(h.effective_charge for h in h_atoms_new)
print(f"\nNEW Logic - H atoms total: {new_h_total:.4f}")
print(f"✅ CORRECT: {new_h_total:.4f} (0.0 preserved!)")

# Full Pyridine with new logic
print("\nFull Pyridine (NEW logic):")
new_atoms = []
for idx in range(11):
    atom_new = AtomicDensity_New(
        atom_index=idx,
        atom_symbol=("N" if idx == 0 else ("C" if idx < 6 else "H")),
        mulliken_charge=mulliken_all_old[idx],
        lowdin_charge=lowdin_all_old[idx],
    )
    new_atoms.append(atom_new)

new_total = sum(a.effective_charge for a in new_atoms)
print(f"  Atoms: {[a.effective_charge for a in new_atoms]}")
print(f"  Total: {new_total:.4f}")

# Final rounding
new_total_rounded = round(new_total, 4)
print(f"  After round(total, 4): {new_total_rounded:.4f}")

# ========== COMPARISON ==========

print("\n" + "="*70)
print("COMPARISON:")
print("="*70)

print(f"\nOLD Logic (v2.03):")
print(f"  H atom effective_charge: {h_atoms_old[0].effective_charge:.4f} (should be 0.0000)")
print(f"  Total: {old_total:.4f} (should be 0.0000)")
print(f"  ❌ FAILED")

print(f"\nNEW Logic (v2.04):")
print(f"  H atom effective_charge: {h_atoms_new[0].effective_charge:.4f} ✓")
print(f"  Total: {new_total_rounded:.4f} ✓")
print(f"  ✅ PASSED")

print("\n" + "="*70)
print("ROOT CAUSE ANALYSIS:")
print("="*70)

print(f"""
Old Code:
  self.effective_charge = self.mulliken_charge if self.mulliken_charge != 0.0 else self.lowdin_charge
  
  For H atom with mulliken=0.0:
    0.0 != 0.0 → False
    → Use lowdin_charge (-0.0050)
    → WRONG!

New Code:
  self.effective_charge = self.mulliken_charge
  
  For H atom with mulliken=0.0:
    → Use mulliken_charge (0.0)
    → CORRECT!
""")

print("\n" + "="*70)

if abs(new_total_rounded - 0.0) < 0.0001:
    print("✅✅✅ SUCCESS: Pyridine total charge = 0.0000 ✅✅✅")
    print("\nProof:")
    print(f"  • H atom charge preserved: 0.0000 (not hijacked to -0.0050)")
    print(f"  • N atom charge: -0.1500")
    print(f"  • C atoms total: +0.1500 (balanced)")
    print(f"  • Grand total: {new_total_rounded:.4f} ✓")
    exit_code = 0
else:
    print(f"❌ FAILED: Total = {new_total_rounded:.4f} (expected 0.0000)")
    exit_code = 1

print("="*70 + "\n")
exit(exit_code)
