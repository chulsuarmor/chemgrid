#!/usr/bin/env python3
"""Cycle 4 Templates Test: 5 new reaction mechanism templates (10 test cases).

1. Pinacol Rearrangement (4 steps) — TASK-MECH-088
2. Hofmann Rearrangement (5 steps) — TASK-MECH-089
3. Appel Reaction (3 steps) — TASK-MECH-090
4. Jones Oxidation (3 steps) — TASK-MECH-091
5. Cope Rearrangement (2 steps) — TASK-MECH-092
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'departments', 'domain_mechanism', 'evidence', 'cycle4')


def test_cycle4_templates():
    from rdkit import Chem
    from drylab_report_exporter import _generate_generic_mechanism, _generate_mechanism_step_png

    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    test_cases = [
        # (name, reactant, product, conditions, expected_min_steps)
        (
            "Pinacol_standard",
            "CC(O)(C)C(C)(C)O",        # pinacol (2,3-dimethyl-2,3-butanediol)
            "CC(=O)C(C)(C)C",          # pinacolone (3,3-dimethyl-2-butanone)
            "H2SO4, heat, Pinacol rearrangement",
            4,
        ),
        (
            "Pinacol_acid_heat",
            "CC(O)(C)C(C)(C)O",        # pinacol
            "CC(=O)C(C)(C)C",          # pinacolone
            "H2SO4, delta",             # trigger without explicit keyword
            4,
        ),
        (
            "Hofmann_acetamide",
            "CC(=O)N",                  # acetamide
            "CN",                       # methylamine (one fewer C)
            "Br2, NaOH, Hofmann",
            5,
        ),
        (
            "Hofmann_benzamide",
            "O=C(N)c1ccccc1",          # benzamide
            "Nc1ccccc1",               # aniline
            "Br2, NaOH, Hofmann rearrangement",
            5,
        ),
        (
            "Appel_ethanol",
            "CCO",                      # ethanol
            "CCCl",                     # chloroethane
            "PPh3, CCl4, Appel",
            3,
        ),
        (
            "Appel_1propanol",
            "CCCO",                     # 1-propanol
            "CCCCl",                    # 1-chloropropane
            "PPh3, CCl4, Appel reaction",
            3,
        ),
        (
            "Jones_2propanol",
            "CC(O)C",                   # isopropanol (2-degree)
            "CC(=O)C",                 # acetone (ketone)
            "CrO3, H2SO4, Jones oxidation",
            3,
        ),
        (
            "Jones_1butanol",
            "CCCCO",                    # 1-butanol (1-degree)
            "CCCC(=O)O",              # butanoic acid (Jones gives carboxylic acid from 1° alcohol)
            "Jones, CrO3, H2SO4, acetone",
            3,
        ),
        (
            "Cope_15hexadiene",
            "C=CCC=CC",                # 1,5-hexadiene derivative
            "CC=CCC=C",               # rearranged product
            "heat, Cope rearrangement",
            2,
        ),
        (
            "Cope_oxy",
            "C=CCC(O)C=C",            # 3-hydroxy-1,5-hexadiene
            "O=CCCCCC",               # 6-heptenal (after tautomerization)
            "KH, 18-crown-6, oxy-cope",
            2,
        ),
    ]

    results = []
    passed = 0
    failed = 0

    for name, reactant, product, conditions, min_steps in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"  Reactant: {reactant}")
        print(f"  Product:  {product}")
        print(f"  Conditions: {conditions}")

        # Test 1: Template generates steps
        steps = _generate_generic_mechanism(reactant, product, conditions)
        if steps is None:
            print(f"  FAIL: returned None (no template matched)")
            results.append((name, 'FAIL', 'No template matched'))
            failed += 1
            continue

        n_steps = len(steps)
        if n_steps < min_steps:
            print(f"  FAIL: only {n_steps} steps (expected >= {min_steps})")
            results.append((name, 'FAIL', f'{n_steps} < {min_steps} steps'))
            failed += 1
            continue

        print(f"  Steps: {n_steps} (expected >= {min_steps}) OK")

        # Test 2: All mol_smi are valid SMILES
        all_valid = True
        for i, step in enumerate(steps):
            mol_smi = step.get('mol_smi', '')
            if mol_smi:
                mol = Chem.MolFromSmiles(mol_smi)
                if mol is None:
                    print(f"  FAIL: Step {i+1} mol_smi '{mol_smi}' is invalid SMILES")
                    all_valid = False
        if not all_valid:
            results.append((name, 'FAIL', 'Invalid SMILES in steps'))
            failed += 1
            continue

        # Test 3: No reactant copying (intermediate != reactant)
        r_canon = Chem.MolToSmiles(Chem.MolFromSmiles(reactant))
        p_canon = Chem.MolToSmiles(Chem.MolFromSmiles(product))
        copy_count = 0
        for i, step in enumerate(steps):
            if i == 0:
                continue  # first step can be reactant
            if i == n_steps - 1:
                continue  # last step can be product
            mol_smi = step.get('mol_smi', '')
            if mol_smi:
                mol = Chem.MolFromSmiles(mol_smi)
                if mol:
                    canon = Chem.MolToSmiles(mol)
                    if canon == r_canon:
                        print(f"  WARNING: Step {i+1} mol_smi is SAME as reactant!")
                        copy_count += 1

        if copy_count > 0 and n_steps > 2:
            print(f"  FAIL: {copy_count} intermediate(s) copied from reactant")
            results.append((name, 'FAIL', f'{copy_count} reactant copies'))
            failed += 1
            continue

        # Test 4: Generate PNG evidence (call with reactant/product/conditions)
        try:
            png_data = _generate_mechanism_step_png(reactant, product, conditions)
            if png_data and len(png_data) > 1000:
                png_path = os.path.join(EVIDENCE_DIR, f'{name}.png')
                with open(png_path, 'wb') as f:
                    f.write(png_data)
                print(f"  PNG: {len(png_data)} bytes -> {png_path}")
            else:
                print(f"  PNG: small/empty ({len(png_data) if png_data else 0} bytes)")
        except Exception as e:
            print(f"  PNG generation error: {e}")

        # Print step details
        for i, step in enumerate(steps):
            label = step.get('label', '')
            mol_smi = step.get('mol_smi', '')
            reagent = step.get('reagent_smi', '')
            arrows = len(step.get('inner_arrows', []))
            byp = step.get('byproduct_smi', '')
            is_ts = step.get('is_transition_state', False)
            is_int = step.get('is_intermediate', False)
            tag = '[TS]' if is_ts else ('[INT]' if is_int else '')
            print(f"    Step {i+1}: {label} {tag}")
            print(f"      mol_smi: {mol_smi}")
            if reagent:
                print(f"      reagent: {reagent}")
            if byp:
                print(f"      byproduct: {byp}")
            if arrows:
                print(f"      arrows: {arrows}")

        results.append((name, 'PASS', f'{n_steps} steps'))
        passed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"CYCLE 4 TEMPLATE TEST SUMMARY")
    print(f"{'='*60}")
    for name, status, detail in results:
        icon = 'OK' if status == 'PASS' else 'XX'
        print(f"  [{icon}] {name}: {status} ({detail})")
    print(f"\nTotal: {passed}/{len(test_cases)} PASS, {failed}/{len(test_cases)} FAIL")
    return passed == len(test_cases)


if __name__ == '__main__':
    success = test_cycle4_templates()
    sys.exit(0 if success else 1)
