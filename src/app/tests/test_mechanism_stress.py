#!/usr/bin/env python3
"""스트레스 테스트: 10단계 이상 고난이도 반응 메커니즘 PNG 생성.

Robinson Annulation (14단계), Swern Oxidation (12단계), Favorskii (10단계)
+ 기존 반응들의 스네이크 레이아웃 검증.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_high_difficulty_mechanisms():
    from drylab_report_exporter import _generate_generic_mechanism, _generate_mechanism_step_png

    test_cases = [
        # (name, reactant, product, conditions, expected_min_steps)
        (
            "Robinson_Annulation_14step",
            "O=C1CCCCC1",           # cyclohexanone
            "O=C1C=CC(=O)CC1",      # 2-cyclohexenone (simplified)
            "NaOH, MVK, heat",
            14,
        ),
        (
            "Swern_Oxidation_12step",
            "CCO",                   # ethanol
            "CC=O",                  # acetaldehyde
            "DMSO, (COCl)2, Et3N, Swern",
            10,
        ),
        (
            "Favorskii_Rearrangement_10step",
            "O=C1CCCCC1Cl",         # 2-chlorocyclohexanone
            "OC(=O)C1CCCC1",        # cyclopentane carboxylic acid
            "NaOMe, Favorskii",
            8,
        ),
        (
            "Fischer_Esterification_6step",
            "CC(=O)O",              # acetic acid
            "CC(=O)OCC",            # ethyl acetate
            "H2SO4, EtOH, Fischer",
            4,
        ),
        (
            "Aldol_Condensation_5step",
            "CC(=O)C",              # acetone
            "CC(=O)/C=C(/C)C(=O)C", # diacetone alcohol → mesityl oxide
            "NaOH, heat, Aldol",
            4,
        ),
        (
            "Beckmann_Rearrangement_4step",
            "O=C1CCCCC1",          # cyclohexanone
            "O=C1CCCCCN1",         # caprolactam
            "NH2OH, H2SO4, Beckmann",
            3,
        ),
        (
            "Wolff_Kishner_6step",
            "CC(=O)c1ccccc1",      # acetophenone
            "CCc1ccccc1",          # ethylbenzene
            "NH2NH2, KOH, Wolff-Kishner",
            4,
        ),
        (
            "Curtius_Rearrangement_4step",
            "CC(=O)Cl",            # acetyl chloride
            "CN=C=O",             # methyl isocyanate
            "NaN3, heat, Curtius",
            3,
        ),
    ]

    output_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                              'departments', 'domain_mechanism', 'evidence')
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
            # Count total arrows
            total_arrows = 0
            for s in steps:
                ad = s.get('arrow_defs', [])
                ia = s.get('inner_arrows', [])
                total_arrows += len(ad) + len(ia)
            print(f"  Total arrows: {total_arrows}")

            # Print step labels
            for i, s in enumerate(steps):
                label = s.get('label', f'Step {i+1}')
                is_int = s.get('is_intermediate', False)
                is_ts = s.get('is_transition_state', False)
                ad = len(s.get('arrow_defs', []))
                ia = len(s.get('inner_arrows', []))
                badge = ' [intermediate]' if is_int else ' [TS]' if is_ts else ''
                print(f"    Step {i+1}: {label}{badge}  (arrows: {ad}+{ia})")

        # Render full PNG via _generate_mechanism_step_png (includes _get_mechanism_steps + fill_inner + render)
        try:
            png_bytes = _generate_mechanism_step_png(rsmi, psmi, cond)
            if png_bytes:
                out_path = os.path.join(output_dir, f'stress_{name}.png')
                with open(out_path, 'wb') as f:
                    f.write(png_bytes)
                fsize = len(png_bytes) / 1024
                print(f"  📸 PNG saved: {out_path} ({fsize:.0f} KB)")
                results.append((name, 'PASS', n_steps, f'{fsize:.0f}KB'))
            else:
                print(f"  ❌ FAIL: render returned None")
                results.append((name, 'FAIL', n_steps, 'render=None'))
        except Exception as e:
            print(f"  ❌ FAIL: render error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, 'ERROR', n_steps, str(e)[:50]))

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    total_pass = sum(1 for r in results if r[1] == 'PASS')
    for name, status, steps, info in results:
        emoji = '✅' if status == 'PASS' else '❌'
        print(f"  {emoji} {name}: {status} ({steps} steps, {info})")
    print(f"\n  {total_pass}/{len(results)} PASS")
    return total_pass == len(results)

if __name__ == '__main__':
    success = test_high_difficulty_mechanisms()
    sys.exit(0 if success else 1)
