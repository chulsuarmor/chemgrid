#!/usr/bin/env python3
"""Cycle 5 Templates Test: 5 new reaction mechanism templates (10 test cases).

1. EAS Halogenation (4 steps) — TASK-MECH-093
2. EAS Nitration (4 steps) — TASK-MECH-094
3. EAS Sulfonation (4 steps) — TASK-MECH-095
4. HX Addition Markovnikov (3 steps) — TASK-MECH-096
5. SN1 Reaction (3 steps) — TASK-MECH-097
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'departments', 'domain_mechanism', 'evidence', 'cycle5')


def test_cycle5_templates():
    from rdkit import Chem
    from drylab_report_exporter import _generate_generic_mechanism, _generate_mechanism_step_png

    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    test_cases = [
        # (name, reactant, product, conditions, expected_min_steps)

        # EAS Halogenation — TASK-MECH-093
        (
            "EAS_Br_benzene",
            "c1ccccc1",                    # benzene
            "c1ccc(Br)cc1",               # bromobenzene
            "Br2, FeBr3",
            4,
        ),
        (
            "EAS_Cl_toluene",
            "Cc1ccccc1",                   # toluene
            "Cc1ccc(Cl)cc1",              # 4-chlorotoluene
            "Cl2, AlCl3",
            4,
        ),

        # EAS Nitration — TASK-MECH-094
        (
            "Nitration_benzene",
            "c1ccccc1",                    # benzene
            "c1ccc([N+](=O)[O-])cc1",    # nitrobenzene
            "HNO3, H2SO4, nitration",
            4,
        ),
        (
            "Nitration_toluene",
            "Cc1ccccc1",                   # toluene
            "Cc1ccc([N+](=O)[O-])cc1",   # 4-nitrotoluene
            "HNO3, H2SO4",
            4,
        ),

        # EAS Sulfonation — TASK-MECH-095
        (
            "Sulfonation_benzene",
            "c1ccccc1",                    # benzene
            "c1ccc(S(=O)(=O)O)cc1",       # benzenesulfonic acid
            "SO3, fuming H2SO4, sulfonation",
            4,
        ),
        (
            "Sulfonation_naphthalene",
            "c1ccc2ccccc2c1",             # naphthalene
            "c1ccc2cc(S(=O)(=O)O)ccc2c1", # 2-naphthalenesulfonic acid
            "oleum, SO3",
            4,
        ),

        # HX Addition Markovnikov — TASK-MECH-096
        (
            "HBr_propene",
            "CC=C",                        # propene
            "CC(Br)C",                    # 2-bromopropane (Markovnikov)
            "HBr",
            3,
        ),
        (
            "HCl_2methylpropene",
            "CC(=C)C",                    # 2-methylpropene (isobutylene)
            "CC(C)(Cl)C",                 # 2-chloro-2-methylpropane (tert-butyl chloride)
            "HCl",
            3,
        ),

        # SN1 Reaction — TASK-MECH-097
        (
            "SN1_tBuBr_water",
            "CC(C)(C)Br",                 # tert-butyl bromide
            "CC(C)(C)O",                  # tert-butanol
            "H2O, SN1",
            3,
        ),
        (
            "SN1_tBuCl_EtOH",
            "CC(C)(C)Cl",                 # tert-butyl chloride
            "CC(C)(C)OCC",               # tert-butyl ethyl ether
            "EtOH, SN1, solvolysis",
            3,
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

        # Test 4: Generate PNG evidence
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
    print(f"CYCLE 5 TEMPLATE TEST SUMMARY")
    print(f"{'='*60}")
    for name, status, detail in results:
        icon = 'OK' if status == 'PASS' else 'XX'
        print(f"  [{icon}] {name}: {status} ({detail})")
    print(f"\nTotal: {passed}/{len(test_cases)} PASS, {failed}/{len(test_cases)} FAIL")
    return passed == len(test_cases)


if __name__ == '__main__':
    success = test_cycle5_templates()
    sys.exit(0 if success else 1)
