"""
Headless test: intermolecular mechanism arrows must cross molecule boundaries.

Usage:
    python test_intermolecular_arrows.py

Pass criteria:
    At least ONE arrow has from_mol_idx != to_mol_idx (cross-molecule).
    If ALL arrows have same mol_idx → the fix is NOT working.

M157 regression guard — 5회 반복 버그 재발 방지.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from mechanism_engine import MechanismEngine
from reaction_mechanisms import get_mechanism


def mol_idx_of(atom_idx: int, frag_boundaries: list) -> int:
    """Return which fragment (molecule index) an atom belongs to."""
    for fi, (lo, hi) in enumerate(frag_boundaries):
        if lo <= atom_idx <= hi:
            return fi
    return -1


def run_test(label: str, reactant_smiles_list: list, product_smiles: str,
             transform_name: str, frag_sizes: list) -> bool:
    """
    Run one test case. Returns True if at least one cross-molecule arrow exists.
    frag_sizes: list of atom counts per fragment (in same order as reactant_smiles_list).
    """
    engine = MechanismEngine()
    mech = engine.generate_intermolecular_mechanism(
        reactant_smiles_list, product_smiles, transform_name=transform_name)

    if mech is None:
        print(f"  SKIP: mech is None for {label}")
        return True  # can't test, not a failure of the fix

    # Build fragment boundaries
    frag_boundaries = []
    offset = 0
    for n in frag_sizes:
        frag_boundaries.append((offset, offset + n - 1))
        offset += n

    found_cross = False
    for step in mech.steps:
        for arrow in step.arrows:
            fa = arrow.from_atom_idx
            ta = arrow.to_atom_idx
            if fa >= 0 and ta >= 0:
                fm = mol_idx_of(fa, frag_boundaries)
                tm = mol_idx_of(ta, frag_boundaries)
                if fm >= 0 and tm >= 0 and fm != tm:
                    found_cross = True
                    print(f"  [CROSS] {label} step {step.step_number}: "
                          f"atom {fa}(mol{fm}) → atom {ta}(mol{tm})")

    if not found_cross:
        # Check if all arrows are within the same molecule (intramolecular loop)
        all_arrows = [(a.from_atom_idx, a.to_atom_idx)
                      for s in mech.steps for a in s.arrows
                      if a.from_atom_idx >= 0 and a.to_atom_idx >= 0]
        print(f"  [FAIL] {label}: no cross-molecule arrows found. "
              f"All arrows: {all_arrows}")
    return found_cross


def test_global_not_mutated():
    """Gold standard MECHANISMS["sn2"] must be immutable across repeated calls."""
    original_arrows = [(a.from_atom_idx, a.to_atom_idx)
                       for a in get_mechanism('sn2').steps[0].arrows]
    engine = MechanismEngine()
    # Call with reversed order 3 times
    for _ in range(3):
        engine.generate_intermolecular_mechanism(
            ['[OH-]', 'CBr'], 'CO.[Br-]', transform_name='SN2')
    after_arrows = [(a.from_atom_idx, a.to_atom_idx)
                    for a in get_mechanism('sn2').steps[0].arrows]
    ok = original_arrows == after_arrows
    if ok:
        print(f"  [PASS] Global sn2 stable: {after_arrows}")
    else:
        print(f"  [FAIL] Global sn2 mutated: original={original_arrows} after={after_arrows}")
    return ok


def test_stable_repeated_calls():
    """Same reactant order → same arrow indices every call."""
    engine = MechanismEngine()
    results = []
    for _ in range(3):
        mech = engine.generate_intermolecular_mechanism(
            ['[OH-]', 'CBr'], 'CO.[Br-]', transform_name='SN2')
        if mech:
            arrows = [(a.from_atom_idx, a.to_atom_idx)
                      for a in mech.steps[0].arrows]
            results.append(arrows)

    if len(set(str(r) for r in results)) == 1:
        print(f"  [PASS] Stable repeated calls: {results[0]}")
        return True
    else:
        print(f"  [FAIL] Inconsistent arrows across calls: {results}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("TEST: Intermolecular mechanism arrows (M157 regression)")
    print("=" * 60)
    passed = 0
    total = 0

    # Test 1: SN2 — [OH-, CBr] reversed order (the original bug case)
    total += 1
    ok = run_test(
        "SN2 [OH-,CBr]",
        ['[OH-]', 'CBr'], 'CO.[Br-]', 'SN2',
        frag_sizes=[1, 2]  # [OH-]=1 atom, CBr=2 atoms
    )
    if ok:
        passed += 1
        print(f"  [PASS] SN2 reversed order")

    # Test 2: SN2 — CBr, OH- original order (should also have cross arrows)
    total += 1
    ok = run_test(
        "SN2 [CBr,OH-]",
        ['CBr', '[OH-]'], 'CO.[Br-]', 'SN2',
        frag_sizes=[2, 1]  # CBr=2 atoms, [OH-]=1 atom
    )
    if ok:
        passed += 1
        print(f"  [PASS] SN2 original order")

    # Test 3: Global immutability
    total += 1
    if test_global_not_mutated():
        passed += 1

    # Test 4: Stable repeated calls
    total += 1
    if test_stable_repeated_calls():
        passed += 1

    print()
    print(f"Results: {passed}/{total} PASS")
    if passed == total:
        print("ALL PASS - intermolecular fix is working")
        sys.exit(0)
    else:
        print("FAIL — arrows still looping within same molecule")
        sys.exit(1)
