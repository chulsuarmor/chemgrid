#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cycle 14 Template Tests - 5 Phase 3 advanced reactions.

Reactions tested:
  1. Neber Rearrangement (TASK-MECH-138)
  2. Lossen Rearrangement (TASK-MECH-139)
  3. Hofmann-Loffler-Freytag (TASK-MECH-140)
  4. Sommelet-Hauser Rearrangement (TASK-MECH-141)
  5. Stevens Rearrangement (TASK-MECH-142)

Each reaction: 2 tests (gold standard MECHANISMS dict + drylab template trigger).
Total: 10 tests.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rdkit import Chem

passed = 0
failed = 0
errors = []


def check(test_name, condition, msg=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print("  [PASS] %s" % test_name)
    else:
        failed += 1
        err = "  [FAIL] %s: %s" % (test_name, msg)
        print(err)
        errors.append(err)


def validate_smiles(smi):
    """Check if SMILES is RDKit-parseable."""
    return Chem.MolFromSmiles(smi) is not None


# ===============================================================
# Test 1-2: Neber Rearrangement
# ===============================================================
print("\n=== Neber Rearrangement ===")

from reaction_mechanisms import MECHANISMS
mech = MECHANISMS.get('neber_rearrangement')
check("Neber_gold_exists", mech is not None, "neber_rearrangement not in MECHANISMS")
if mech:
    all_valid = True
    for step in mech.steps:
        if step.reactant_smiles and not validate_smiles(step.reactant_smiles):
            all_valid = False
            print("    Invalid reactant: %s" % step.reactant_smiles)
        if step.product_smiles and not validate_smiles(step.product_smiles):
            all_valid = False
            print("    Invalid product: %s" % step.product_smiles)
    check("Neber_gold_smiles_valid", all_valid,
          "One or more SMILES in Neber gold standard are invalid")

from drylab_report_exporter import _generate_generic_mechanism
result = _generate_generic_mechanism(
    'CC(=NOS(=O)(=O)c1ccc(C)cc1)C', 'CC(=O)C(C)N',
    'Neber rearrangement, KOEt/EtOH')
check("Neber_drylab_trigger",
      result is not None and len(result) >= 4,
      "Neber drylab template returned %d steps (expected >=4)" % (len(result) if result else 0))


# ===============================================================
# Test 3-4: Lossen Rearrangement
# ===============================================================
print("\n=== Lossen Rearrangement ===")

mech = MECHANISMS.get('lossen_rearrangement')
check("Lossen_gold_exists", mech is not None, "lossen_rearrangement not in MECHANISMS")
if mech:
    all_valid = all(
        validate_smiles(s.reactant_smiles) and validate_smiles(s.product_smiles)
        for s in mech.steps if s.reactant_smiles and s.product_smiles
    )
    check("Lossen_gold_smiles_valid", all_valid,
          "One or more SMILES in Lossen gold standard are invalid")

result = _generate_generic_mechanism('CC(=O)NO', 'CN',
                                      'Lossen rearrangement, Ac2O, Et3N')
check("Lossen_drylab_trigger",
      result is not None and len(result) >= 4,
      "Lossen drylab template returned %d steps (expected >=4)" % (len(result) if result else 0))


# ===============================================================
# Test 5-6: Hofmann-Loffler-Freytag
# ===============================================================
print("\n=== Hofmann-Loffler-Freytag ===")

mech = MECHANISMS.get('hofmann_loffler_freytag')
check("HLF_gold_exists", mech is not None, "hofmann_loffler_freytag not in MECHANISMS")
if mech:
    all_valid = all(
        validate_smiles(s.reactant_smiles) and validate_smiles(s.product_smiles)
        for s in mech.steps if s.reactant_smiles and s.product_smiles
    )
    check("HLF_gold_smiles_valid", all_valid,
          "One or more SMILES in HLF gold standard are invalid")

result = _generate_generic_mechanism(
    'ClN(CCCC)C', 'CN1CCC(C)C1',
    'Hofmann-Loffler-Freytag, hv, NaOH')
check("HLF_drylab_trigger",
      result is not None and len(result) >= 5,
      "HLF drylab template returned %d steps (expected >=5)" % (len(result) if result else 0))


# ===============================================================
# Test 7-8: Sommelet-Hauser Rearrangement
# ===============================================================
print("\n=== Sommelet-Hauser Rearrangement ===")

mech = MECHANISMS.get('sommelet_hauser')
check("SomHaus_gold_exists", mech is not None, "sommelet_hauser not in MECHANISMS")
if mech:
    all_valid = all(
        validate_smiles(s.reactant_smiles) and validate_smiles(s.product_smiles)
        for s in mech.steps if s.reactant_smiles and s.product_smiles
    )
    check("SomHaus_gold_smiles_valid", all_valid,
          "One or more SMILES in Sommelet-Hauser gold standard are invalid")

result = _generate_generic_mechanism(
    'C[N+](C)(C)Cc1ccccc1', 'CN(C)Cc1ccccc1C',
    'Sommelet-Hauser rearrangement, NaNH2, NH3(l)')
check("SomHaus_drylab_trigger",
      result is not None and len(result) >= 4,
      "Sommelet-Hauser drylab template returned %d steps (expected >=4)" % (len(result) if result else 0))


# ===============================================================
# Test 9-10: Stevens Rearrangement
# ===============================================================
print("\n=== Stevens Rearrangement ===")

mech = MECHANISMS.get('stevens_rearrangement')
check("Stevens_gold_exists", mech is not None, "stevens_rearrangement not in MECHANISMS")
if mech:
    all_valid = all(
        validate_smiles(s.reactant_smiles) and validate_smiles(s.product_smiles)
        for s in mech.steps if s.reactant_smiles and s.product_smiles
    )
    check("Stevens_gold_smiles_valid", all_valid,
          "One or more SMILES in Stevens gold standard are invalid")

result = _generate_generic_mechanism(
    'C[N+](C)(CC)Cc1ccccc1', 'CN(C)C(Cc1ccccc1)C',
    'Stevens rearrangement, NaNH2')
check("Stevens_drylab_trigger",
      result is not None and len(result) >= 3,
      "Stevens drylab template returned %d steps (expected >=3)" % (len(result) if result else 0))


# ===============================================================
# Summary
# ===============================================================
print("\n" + "=" * 60)
print("TOTAL: %d tests -- %d PASS, %d FAIL" % (passed + failed, passed, failed))
if errors:
    print("\nFailed tests:")
    for e in errors:
        print(e)
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
