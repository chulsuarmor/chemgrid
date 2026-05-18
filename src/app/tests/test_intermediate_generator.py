#!/usr/bin/env python3
"""
test_intermediate_generator.py — RWMol 기반 중간체 생성기 테스트
================================================================
Wolff-Kishner, Aldol, Fischer 에스터화 3개 반응의 중간체를 생성하고
모든 SMILES가 RDKit 유효한지 검증한다.
"""

import sys
import os

# Add src/app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rdkit import Chem
from intermediate_generator import generate_intermediates


def _validate_smiles(smi: str) -> bool:
    """SMILES가 RDKit으로 파싱 + 산화 가능한지 확인."""
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return False
    try:
        Chem.SanitizeMol(mol)
        return True
    except Exception:
        return False


def test_wolff_kishner():
    """Wolff-Kishner: CC(=O)c1ccccc1 + NH2NH2 → CCc1ccccc1"""
    print("=" * 60)
    print("TEST 1: Wolff-Kishner Reduction")
    print("  Reactant: acetophenone CC(=O)c1ccccc1")
    print("  Product:  ethylbenzene  CCc1ccccc1")
    print("=" * 60)

    results = generate_intermediates(
        reactant_smi="CC(=O)c1ccccc1",
        product_smi="CCc1ccccc1",
        conditions="NH2NH2, KOH, 200°C, ethylene glycol",
    )

    assert len(results) >= 4, f"Expected >=4 intermediates, got {len(results)}"

    all_valid = True
    for i, r in enumerate(results):
        valid = _validate_smiles(r['smiles'])
        status = "PASS" if valid else "FAIL"
        if not valid:
            all_valid = False
        print(f"  [{status}] Step {i}: {r['label']}")
        print(f"         SMILES: {r['smiles']}")
        print(f"         {r['annotation']}")
        if r['is_transition_state']:
            print(f"         [TRANSITION STATE]")
        if r['charges']:
            print(f"         Charges: {r['charges']}")
        if r['radicals']:
            print(f"         Radicals: {r['radicals']}")
        print()

    assert all_valid, "Some SMILES failed validation!"

    # Check that we have real intermediates (not just reactant/product)
    intermediates = [r for r in results if r['is_intermediate']]
    assert len(intermediates) >= 2, \
        f"Expected >=2 real intermediates, got {len(intermediates)}"

    # Check hydrazone is present
    hydrazone_found = any("히드라존" in r['label'] and "음이온" not in r['label']
                          for r in results)
    assert hydrazone_found, "Hydrazone intermediate not found!"

    print("  >>> Wolff-Kishner: ALL PASSED <<<\n")
    return True


def test_aldol():
    """Aldol condensation: CC(=O)C → CC(=O)/C=C/C (via NaOH)"""
    print("=" * 60)
    print("TEST 2: Aldol Condensation")
    print("  Reactant: acetone      CC(=O)C")
    print("  Product:  mesityl oxide CC(=O)/C=C\\C")
    print("=" * 60)

    results = generate_intermediates(
        reactant_smi="CC(=O)C",
        product_smi="CC(/C=C/C)=O",
        conditions="NaOH, H2O",
    )

    assert len(results) >= 3, f"Expected >=3 steps, got {len(results)}"

    all_valid = True
    for i, r in enumerate(results):
        valid = _validate_smiles(r['smiles'])
        status = "PASS" if valid else "FAIL"
        if not valid:
            all_valid = False
        print(f"  [{status}] Step {i}: {r['label']}")
        print(f"         SMILES: {r['smiles']}")
        print(f"         {r['annotation']}")
        print()

    assert all_valid, "Some SMILES failed validation!"

    # Check enolate
    enolate_found = any("에놀레이트" in r['label'] for r in results)
    assert enolate_found, "Enolate intermediate not found!"

    print("  >>> Aldol: ALL PASSED <<<\n")
    return True


def test_fischer():
    """Fischer esterification: CC(=O)O + CCO → CCOC(C)=O + H2O"""
    print("=" * 60)
    print("TEST 3: Fischer Esterification")
    print("  Reactant: acetic acid CH3COOH + ethanol EtOH")
    print("  Product:  ethyl acetate CCOC(C)=O")
    print("=" * 60)

    results = generate_intermediates(
        reactant_smi="CC(=O)O.CCO",
        product_smi="CCOC(C)=O",
        conditions="H2SO4, reflux",
    )

    assert len(results) >= 3, f"Expected >=3 steps, got {len(results)}"

    all_valid = True
    for i, r in enumerate(results):
        valid = _validate_smiles(r['smiles'])
        status = "PASS" if valid else "FAIL"
        if not valid:
            all_valid = False
        print(f"  [{status}] Step {i}: {r['label']}")
        print(f"         SMILES: {r['smiles']}")
        print(f"         {r['annotation']}")
        print()

    assert all_valid, "Some SMILES failed validation!"
    print("  >>> Fischer: ALL PASSED <<<\n")
    return True


def test_e2():
    """E2 elimination: CCBr + NaOH → C=C"""
    print("=" * 60)
    print("TEST 4: E2 Elimination")
    print("  Reactant: bromoethane CCBr")
    print("  Product:  ethylene    C=C")
    print("=" * 60)

    results = generate_intermediates(
        reactant_smi="CCBr",
        product_smi="C=C",
        conditions="KOEt, ethanol",
    )

    all_valid = True
    for i, r in enumerate(results):
        valid = _validate_smiles(r['smiles'])
        status = "PASS" if valid else "FAIL"
        if not valid:
            all_valid = False
        print(f"  [{status}] Step {i}: {r['label']}")
        print(f"         SMILES: {r['smiles']}")
        print(f"         {r['annotation']}")
        if r['is_transition_state']:
            print(f"         [TRANSITION STATE]")
        print()

    assert all_valid, "Some SMILES failed validation!"

    # E2 should have a transition state
    ts_found = any(r['is_transition_state'] for r in results)
    assert ts_found, "E2 transition state not found!"

    print("  >>> E2: ALL PASSED <<<\n")
    return True


def test_radical():
    """Radical NBS: Cc1ccccc1 → BrCc1ccccc1"""
    print("=" * 60)
    print("TEST 5: Radical Benzylic Bromination (NBS)")
    print("  Reactant: toluene     Cc1ccccc1")
    print("  Product:  benzyl Br   BrCc1ccccc1")
    print("=" * 60)

    results = generate_intermediates(
        reactant_smi="Cc1ccccc1",
        product_smi="BrCc1ccccc1",
        conditions="NBS, hv",
    )

    all_valid = True
    for i, r in enumerate(results):
        valid = _validate_smiles(r['smiles'])
        status = "PASS" if valid else "FAIL"
        if not valid:
            all_valid = False
        print(f"  [{status}] Step {i}: {r['label']}")
        print(f"         SMILES: {r['smiles']}")
        print(f"         {r['annotation']}")
        if r['radicals']:
            print(f"         Radicals: {r['radicals']}")
        print()

    assert all_valid, "Some SMILES failed validation!"

    radical_found = any(r['radicals'] for r in results)
    assert radical_found, "Radical intermediate not found!"

    print("  >>> Radical NBS: ALL PASSED <<<\n")
    return True


if __name__ == "__main__":
    passed = 0
    failed = 0

    for test_fn in [test_wolff_kishner, test_aldol, test_fischer, test_e2, test_radical]:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  !!! FAILED: {e}\n")
            failed += 1
        except Exception as e:
            print(f"  !!! ERROR: {e}\n")
            failed += 1

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
