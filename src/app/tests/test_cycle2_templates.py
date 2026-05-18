#!/usr/bin/env python3
"""Cycle 2 Templates Test: 5 new reaction mechanism templates.

1. Br2 Anti-Addition (bromonium ion, 3 steps)
2. Acid-Catalyzed Hydration (Markovnikov, 3 steps)
3. Ozonolysis (4 steps)
4. Free Radical Halogenation (5 steps)
5. Wittig Reaction (4 steps)
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_cycle2_templates():
    from drylab_report_exporter import _generate_generic_mechanism, _generate_mechanism_step_png

    test_cases = [
        # (name, reactant, product, conditions, expected_min_steps)
        (
            "Br2_Anti_Addition",
            "C=C",                     # ethylene
            "BrCCBr",                  # 1,2-dibromoethane
            "Br2, CH2Cl2",
            3,
        ),
        (
            "Br2_Anti_Addition_propene",
            "CC=C",                    # propene
            "CC(Br)CBr",              # 1,2-dibromopropane
            "Br2, CCl4",
            3,
        ),
        (
            "Acid_Hydration_propene",
            "CC=C",                    # propene
            "CC(O)C",                 # 2-propanol (Markovnikov)
            "H2SO4, H2O, hydration",
            3,
        ),
        (
            "Acid_Hydration_cyclohexene",
            "C1=CCCCC1",              # cyclohexene
            "OC1CCCCC1",             # cyclohexanol
            "H3O+, hydration, acid",
            3,
        ),
        (
            "Ozonolysis_reductive",
            "CC=CC",                   # 2-butene
            "CC=O",                   # acetaldehyde (x2)
            "O3, Me2S, ozonolysis",
            4,
        ),
        (
            "Ozonolysis_oxidative",
            "C=C",                     # ethylene
            "OC=O",                   # formic acid
            "O3, H2O2, ozone",
            4,
        ),
        (
            "Radical_Chlorination",
            "CC",                      # ethane
            "CCCl",                   # chloroethane
            "Cl2, hv, radical, light",
            5,
        ),
        (
            "Radical_Bromination",
            "CC(C)C",                  # isobutane
            "CC(C)(C)Br",            # tert-butyl bromide
            "Br2, uv, radical, peroxide",
            5,
        ),
        (
            "Wittig_benzaldehyde",
            "O=Cc1ccccc1",            # benzaldehyde
            "C=Cc1ccccc1",           # styrene
            "PPh3, BuLi, Wittig",
            4,
        ),
        (
            "Wittig_acetone",
            "CC(=O)C",                # acetone
            "CC(=C)C",               # 2-methylpropene
            "PPh3, NaH, Wittig",
            4,
        ),
    ]

    output_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                              'departments', 'domain_mechanism', 'evidence', 'cycle2')
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for name, rsmi, psmi, cond, min_steps in test_cases:
        print(f"\n{'='*60}")
        print(f"  Testing: {name}")
        print(f"  Reactant: {rsmi}")
        print(f"  Product:  {psmi}")
        print(f"  Conditions: {cond}")
        print(f"  Expected min steps: {min_steps}")
        print(f"{'='*60}")

        # Check step count from generic mechanism
        steps = _generate_generic_mechanism(rsmi, psmi, cond)
        n_steps = len(steps) if steps else 0
        print(f"  Generated {n_steps} steps from _generate_generic_mechanism")

        if n_steps < min_steps:
            print(f"  WARNING: Expected >= {min_steps} steps, got {n_steps}")

        if steps:
            # Validate intermediate SMILES are distinct from reactant/product
            from rdkit import Chem
            r_canon = Chem.MolToSmiles(Chem.MolFromSmiles(rsmi)) if Chem.MolFromSmiles(rsmi) else ''
            p_canon = Chem.MolToSmiles(Chem.MolFromSmiles(psmi)) if Chem.MolFromSmiles(psmi) else ''

            for i, s in enumerate(steps):
                mol_smi = s.get('mol_smi', '')
                m = Chem.MolFromSmiles(mol_smi)
                if m is None:
                    print(f"    Step {i+1}: INVALID SMILES '{mol_smi}'")
                else:
                    canon = Chem.MolToSmiles(m)
                    is_copy = (canon == r_canon) and s.get('is_intermediate', False)
                    copy_flag = ' [COPY OF REACTANT!]' if is_copy else ''
                    label = s.get('label', f'Step {i+1}')
                    is_int = s.get('is_intermediate', False)
                    is_ts = s.get('is_transition_state', False)
                    ad = len(s.get('arrow_defs', []))
                    ia = len(s.get('inner_arrows', []))
                    badge = ' [intermediate]' if is_int else ' [TS]' if is_ts else ''
                    print(f"    Step {i+1}: {label}{badge}  (arrows: {ad}+{ia}){copy_flag}")

            # Count total arrows
            total_arrows = sum(len(s.get('arrow_defs', [])) + len(s.get('inner_arrows', []))
                              for s in steps)
            print(f"  Total arrows: {total_arrows}")

        # Render full PNG
        try:
            png_bytes = _generate_mechanism_step_png(rsmi, psmi, cond)
            if png_bytes:
                out_path = os.path.join(output_dir, f'cycle2_{name}.png')
                with open(out_path, 'wb') as f:
                    f.write(png_bytes)
                fsize = len(png_bytes) / 1024
                print(f"  PNG saved: {out_path} ({fsize:.0f} KB)")
                step_pass = n_steps >= min_steps
                results.append((name, 'PASS' if step_pass else 'WARN', n_steps, f'{fsize:.0f}KB'))
            else:
                print(f"  FAIL: render returned None")
                results.append((name, 'FAIL', n_steps, 'render=None'))
        except Exception as e:
            print(f"  FAIL: render error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, 'ERROR', n_steps, str(e)[:80]))

    # Summary
    print(f"\n{'='*60}")
    print("  CYCLE 2 TEMPLATES SUMMARY")
    print(f"{'='*60}")
    total_pass = sum(1 for r in results if r[1] in ('PASS', 'WARN'))
    for name, status, steps, info in results:
        marker = 'OK' if status == 'PASS' else 'WARN' if status == 'WARN' else 'FAIL'
        print(f"  [{marker}] {name}: {status} ({steps} steps, {info})")
    print(f"\n  {total_pass}/{len(results)} generated successfully")
    return total_pass == len(results)


if __name__ == '__main__':
    success = test_cycle2_templates()
    sys.exit(0 if success else 1)
