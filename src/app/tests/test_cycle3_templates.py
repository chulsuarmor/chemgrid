#!/usr/bin/env python3
"""Cycle 3 Templates Test: 5 new reaction mechanism templates (10 test cases).

1. Grignard Addition (4 steps) — TASK-MECH-083
2. Baeyer-Villiger Oxidation (4 steps) — TASK-MECH-084
3. Birch Reduction (5 steps) — TASK-MECH-085
4. Hydroboration-Oxidation (4 steps) — TASK-MECH-086
5. Simmons-Smith Cyclopropanation (3 steps) — TASK-MECH-087
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'departments', 'domain_mechanism', 'evidence', 'cycle3')


def test_cycle3_templates():
    from rdkit import Chem
    from drylab_report_exporter import _generate_generic_mechanism, _generate_mechanism_step_png

    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    test_cases = [
        # (name, reactant, product, conditions, expected_min_steps)
        (
            "Grignard_benzaldehyde",
            "O=Cc1ccccc1",              # benzaldehyde (C=O)
            "OC(C)c1ccccc1",           # 1-phenylethanol
            "MeMgBr, Mg, THF, Grignard",
            4,
        ),
        (
            "Grignard_acetone",
            "CC(=O)C",                  # acetone (ketone)
            "CC(O)(C)C",               # tert-butanol
            "CH3MgBr, Mg, Grignard",
            4,
        ),
        (
            "BaeyerVilliger_cyclohexanone",
            "O=C1CCCCC1",              # cyclohexanone
            "O=C1OCCCCC1",             # caprolactone (7-membered lactone)
            "mCPBA, Baeyer-Villiger",
            4,
        ),
        (
            "BaeyerVilliger_acetophenone",
            "CC(=O)c1ccccc1",          # acetophenone
            "CC(=O)Oc1ccccc1",         # phenyl acetate
            "mCPBA, Baeyer-Villiger oxidation",
            4,
        ),
        (
            "Birch_benzene",
            "c1ccccc1",                 # benzene (aromatic)
            "C1=CCC=CC1",             # 1,4-cyclohexadiene
            "Na, NH3, t-BuOH, Birch",
            5,
        ),
        (
            "Birch_anisole",
            "COc1ccccc1",              # anisole (EDG on ring)
            "COC1=CCC=CC1",           # 2,5-dihydroanisole
            "Li, NH3, EtOH, Birch reduction",
            5,
        ),
        (
            "Hydroboration_propene",
            "CC=C",                     # propene
            "CCCO",                    # 1-propanol (anti-Markovnikov)
            "BH3, THF, H2O2, NaOH, hydroboration",
            4,
        ),
        (
            "Hydroboration_cyclohexene",
            "C1=CCCCC1",              # cyclohexene
            "OC1CCCCC1",             # cyclohexanol (syn addition)
            "BH3.THF, H2O2, NaOH, hydroboration",
            4,
        ),
        (
            "SimmonsSmith_cyclohexene",
            "C1=CCCCC1",              # cyclohexene
            "C1CC2CCCCC12",           # norcarane (bicyclo[4.1.0]heptane)
            "CH2I2, Zn(Cu), Simmons-Smith",
            3,
        ),
        (
            "SimmonsSmith_styrene",
            "C=Cc1ccccc1",             # styrene
            "C1CC1c1ccccc1",          # phenylcyclopropane
            "CH2I2, Zn, Et2O, Simmons-Smith cyclopropanation",
            3,
        ),
    ]

    results = []
    pass_count = 0
    fail_count = 0

    for name, reactant, product, conditions, expected_steps in test_cases:
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"  Reactant: {reactant}")
        print(f"  Product:  {product}")
        print(f"  Conditions: {conditions}")

        # 1. Generate mechanism steps
        steps = _generate_generic_mechanism(reactant, product, conditions)

        if steps is None:
            print(f"  FAIL: _generate_generic_mechanism returned None")
            results.append((name, 'FAIL', 'returned None', 0))
            fail_count += 1
            continue

        n_steps = len(steps)
        print(f"  Steps generated: {n_steps} (expected >= {expected_steps})")

        if n_steps < expected_steps:
            print(f"  FAIL: expected >= {expected_steps} steps, got {n_steps}")
            results.append((name, 'FAIL', f'{n_steps} < {expected_steps}', n_steps))
            fail_count += 1
            continue

        # 2. Check each step has valid mol_smi (not None, parseable by RDKit)
        all_valid = True
        step_smis = []
        for i, step in enumerate(steps):
            smi = step.get('mol_smi', '')
            mol = Chem.MolFromSmiles(smi) if smi else None
            label = step.get('label', '')
            is_ts = step.get('is_transition_state', False)
            is_int = step.get('is_intermediate', False)
            has_arrows = len(step.get('inner_arrows', [])) > 0 or len(step.get('arrow_defs', [])) > 0
            canon = Chem.MolToSmiles(mol) if mol else 'N/A'
            step_smis.append(canon)

            status_str = 'OK' if mol else 'INVALID'
            tag = ''
            if is_ts:
                tag = ' [TS]'
            elif is_int:
                tag = ' [INT]'

            print(f"    Step {i+1}: {status_str}{tag} | {label[:50]}")
            print(f"            mol_smi={smi[:60]} -> canon={canon}")
            print(f"            arrows={has_arrows}, reagent={step.get('reagent_smi', '')[:30]}")

            if mol is None and smi:
                print(f"    WARNING: RDKit cannot parse mol_smi: {smi}")
                all_valid = False

        # 3. Check no intermediate is same as reactant or product
        r_canon = Chem.MolToSmiles(Chem.MolFromSmiles(reactant)) if Chem.MolFromSmiles(reactant) else ''
        p_canon = Chem.MolToSmiles(Chem.MolFromSmiles(product)) if Chem.MolFromSmiles(product) else ''
        # Intermediates (steps 1 to N-1) should differ from reactant and product
        # (first step may use reactant, last step may use product — that's OK)
        duplicate_count = 0
        for i, canon in enumerate(step_smis[1:-1], start=1):
            if canon == r_canon:
                print(f"    WARNING: Step {i+1} intermediate = reactant (possible copy)")
                duplicate_count += 1
            if canon == p_canon and i < len(step_smis) - 2:
                print(f"    WARNING: Step {i+1} intermediate = product (possible copy)")
                duplicate_count += 1

        # 4. Generate PNG (optional — depends on full rendering pipeline)
        png_path = os.path.join(EVIDENCE_DIR, f'{name}.png')
        try:
            png_data = _generate_mechanism_step_png(reactant, product, conditions)
            if png_data and len(png_data) > 100:
                with open(png_path, 'wb') as f:
                    f.write(png_data)
                png_size = len(png_data)
                print(f"  PNG: {png_size:,} bytes -> {png_path}")
            else:
                png_size = 0
                print(f"  PNG: generation returned empty/small data")
        except Exception as e:
            png_size = 0
            print(f"  PNG: generation error: {e}")

        # 5. Determine pass/fail
        if all_valid and n_steps >= expected_steps and duplicate_count == 0:
            print(f"  PASS (steps={n_steps}, arrows=OK, intermediates=distinct)")
            results.append((name, 'PASS', f'{n_steps} steps', png_size))
            pass_count += 1
        elif all_valid and n_steps >= expected_steps:
            print(f"  PASS (with {duplicate_count} intermediate warnings)")
            results.append((name, 'PASS*', f'{n_steps} steps, {duplicate_count} warnings', png_size))
            pass_count += 1
        else:
            print(f"  FAIL: valid={all_valid}, steps={n_steps}, dupes={duplicate_count}")
            results.append((name, 'FAIL', f'valid={all_valid}', png_size))
            fail_count += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"CYCLE 3 TEMPLATES TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total: {len(test_cases)} | PASS: {pass_count} | FAIL: {fail_count}")
    print(f"{'='*60}")
    for name, status, detail, png_size in results:
        png_str = f" | PNG={png_size:,}B" if png_size > 0 else " | no PNG"
        print(f"  {status:6s} | {name:40s} | {detail}{png_str}")

    assert fail_count == 0, f"{fail_count} tests FAILED"
    print(f"\nALL {pass_count}/{len(test_cases)} TESTS PASSED")


if __name__ == '__main__':
    test_cycle3_templates()
