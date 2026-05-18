"""Cycle 18 template verification -Kumada, Tebbe, Petasis, Buchwald-Hartwig, Chan-Lam.

Tests:
1. All 5 keys exist in MECHANISMS dict
2. Each MechanismData has correct step count and valid SMILES
3. Intermediates differ from reactant/product (no copy-paste)
4. _CONDITION_TO_MECH_KEY entries resolve correctly
5. _generate_generic_mechanism blocks fire for each reaction
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rdkit import Chem

# ── Part 1: reaction_mechanisms.py ──────────────────────────
from reaction_mechanisms import MECHANISMS, MechanismData, get_mechanism

CYCLE18_KEYS = [
    'kumada_coupling',
    'tebbe_olefination',
    'petasis_reaction',
    'buchwald_hartwig',
    'chan_lam_coupling',
]

passed = 0
failed = 0
total = 0

def check(desc, condition):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  PASS: {desc}")
    else:
        failed += 1
        print(f"  FAIL: {desc}")

print("=" * 60)
print("Part 1: MECHANISMS dict -5 new keys")
print("=" * 60)

for key in CYCLE18_KEYS:
    mech = get_mechanism(key)
    check(f"{key} exists in MECHANISMS", mech is not None)
    if mech is None:
        continue
    check(f"{key} is MechanismData", isinstance(mech, MechanismData))
    check(f"{key} has 5 steps", mech.total_steps == 5 and len(mech.steps) == 5)
    check(f"{key} has energy_diagram", len(mech.energy_diagram) >= 5)

    # Validate all SMILES
    for i, step in enumerate(mech.steps):
        for smi_name in ('reactant_smiles', 'product_smiles'):
            smi = getattr(step, smi_name)
            mol = Chem.MolFromSmiles(smi)
            check(f"{key} step {i+1} {smi_name} RDKit-valid ({smi})", mol is not None)

    # Check intermediates differ from first reactant / last product
    first_r_mol = Chem.MolFromSmiles(mech.steps[0].reactant_smiles)
    first_r = Chem.MolToSmiles(first_r_mol) if first_r_mol else mech.steps[0].reactant_smiles
    for i, step in enumerate(mech.steps):
        if 1 <= i <= len(mech.steps) - 2:  # intermediate steps
            r_mol = Chem.MolFromSmiles(step.reactant_smiles)
            p_mol = Chem.MolFromSmiles(step.product_smiles)
            r_can = Chem.MolToSmiles(r_mol) if r_mol else step.reactant_smiles
            p_can = Chem.MolToSmiles(p_mol) if p_mol else step.product_smiles
            # At least one of reactant/product should differ from overall reactant
            differs = (r_can != first_r) or (p_can != first_r)
            check(f"{key} step {i+1} intermediate != reactant copy", differs)

print()
print("=" * 60)
print("Part 2: _CONDITION_TO_MECH_KEY resolution")
print("=" * 60)

# Import the condition matcher
try:
    from drylab_report_exporter import _match_conditions_to_mech_key
    _has_matcher = True
except ImportError:
    _has_matcher = False
    print("  SKIP: _match_conditions_to_mech_key not importable")

if _has_matcher:
    test_conditions = [
        ("Kumada coupling, NiCl2(dppf), THF", "kumada_coupling"),
        ("Tebbe olefination, Cp2TiCH2, pyridine", "tebbe_olefination"),
        ("Petasis reaction, ArB(OH)2, morpholine, glyoxylic acid", "petasis_reaction"),
        ("Buchwald-Hartwig amination, Pd2(dba)3, SPhos, NaOtBu", "buchwald_hartwig"),
        ("Chan-Lam coupling, Cu(OAc)2, Et3N, air", "chan_lam_coupling"),
    ]
    for cond, expected_key in test_conditions:
        result = _match_conditions_to_mech_key(cond)
        check(f"'{cond[:40]}...' → {expected_key}", result == expected_key)

print()
print("=" * 60)
print("Part 3: _generate_generic_mechanism template blocks")
print("=" * 60)

try:
    from drylab_report_exporter import _generate_generic_mechanism
    _has_gen = True
except ImportError:
    _has_gen = False
    print("  SKIP: _generate_generic_mechanism not importable")

if _has_gen:
    gen_tests = [
        ("Kumada", "Clc1ccccc1", "Cc1ccccc1", "Kumada coupling, NiCl2(dppf), THF"),
        ("Tebbe", "O=Cc1ccccc1", "C=Cc1ccccc1", "Tebbe olefination, Cp2TiCH2, pyridine"),
        ("Petasis", "O=CC(=O)O", "OC(=O)C(c1ccccc1)NCC", "Petasis reaction, ArB(OH)2, morpholine"),
        ("Buchwald-Hartwig", "Brc1ccccc1", "c1ccc(NC2CCCCC2)cc1", "Buchwald-Hartwig, Pd2(dba)3, SPhos"),
        ("Chan-Lam", "OB(O)c1ccccc1", "c1ccc(NC2CCCCC2)cc1", "Chan-Lam coupling, Cu(OAc)2, Et3N"),
    ]
    for name, rsmi, psmi, cond in gen_tests:
        steps = _generate_generic_mechanism(rsmi, psmi, cond)
        check(f"{name}: _generate_generic_mechanism returns steps", steps is not None)
        if steps:
            check(f"{name}: returns 5 steps", len(steps) == 5)
            # Check mech_badge on first step
            first = steps[0]
            has_badge = first.get('annotation', '') != '' or first.get('mech_badge', '') != ''
            check(f"{name}: first step has annotation/badge", has_badge)

print()
print("=" * 60)
print(f"TOTAL: {passed}/{total} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("ALL TESTS PASSED!")
