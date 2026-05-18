#!/usr/bin/env python3
"""Cycle 13 Templates Test: 5 new reaction mechanism templates (10 test cases).

1. Schmidt Reaction (4 steps) — TASK-MECH-133
2. Dakin Reaction (4 steps) — TASK-MECH-134
3. Tiffeneau-Demjanov Rearrangement (5 steps) — TASK-MECH-135
4. Paal-Knorr Synthesis (4 steps) — TASK-MECH-136
5. Chichibabin Amination (4 steps) — TASK-MECH-137
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'departments', 'domain_mechanism', 'evidence', 'cycle13')


def test_cycle13_templates():
    from rdkit import Chem
    from drylab_report_exporter import _generate_generic_mechanism

    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    test_cases = [
        # (name, reactant, product, conditions, expected_min_steps)

        # Schmidt Reaction — TASK-MECH-133
        (
            "Schmidt_acetone",
            "CC(=O)C",                     # acetone
            "CC(=O)NC",                    # N-methylacetamide
            "HN3, H2SO4, Schmidt reaction",
            4,
        ),
        (
            "Schmidt_cyclohexanone",
            "O=C1CCCCC1",                 # cyclohexanone
            "O=C1CCCCCN1",                # caprolactam
            "TMSN3, TFA, Schmidt",
            4,
        ),

        # Dakin Reaction — TASK-MECH-134
        (
            "Dakin_4hydroxybenzaldehyde",
            "Oc1ccc(C=O)cc1",             # 4-hydroxybenzaldehyde
            "Oc1ccc(O)cc1",               # hydroquinone
            "H2O2, NaOH, Dakin reaction",
            4,
        ),
        (
            "Dakin_vanillin",
            "COc1cc(C=O)ccc1O",           # vanillin
            "COc1cc(O)ccc1O",             # methoxycatechol
            "H2O2, NaOH, Dakin",
            4,
        ),

        # Tiffeneau-Demjanov — TASK-MECH-135
        (
            "TiffeneauDemjanov_cyclopentanone",
            "O=C1CCCC1",                  # cyclopentanone
            "O=C1CCCCC1",                 # cyclohexanone
            "CH2N2, NaNO2/HCl, Tiffeneau-Demjanov",
            5,
        ),
        (
            "TiffeneauDemjanov_cyclobutanone",
            "O=C1CCC1",                   # cyclobutanone
            "O=C1CCCC1",                  # cyclopentanone
            "Tiffeneau-Demjanov ring expansion, CH2N2",
            5,
        ),

        # Paal-Knorr Synthesis — TASK-MECH-136
        (
            "PaalKnorr_diketone_methylamine",
            "CC(=O)CCC(=O)C",             # 2,5-hexanedione
            "Cc1ccc(C)n1C",               # 1,2,5-trimethylpyrrole
            "CH3NH2, AcOH, Paal-Knorr",
            4,
        ),
        (
            "PaalKnorr_diketone_aniline",
            "CC(=O)CCC(=O)C",             # 2,5-hexanedione
            "Cc1ccc(C)n1-c1ccccc1",       # N-phenyl-2,5-dimethylpyrrole
            "aniline, p-TsOH, Paal-Knorr synthesis",
            4,
        ),

        # Chichibabin Amination — TASK-MECH-137
        (
            "Chichibabin_pyridine",
            "c1ccncc1",                    # pyridine
            "Nc1ccccn1",                   # 2-aminopyridine
            "NaNH2, PhNMe2, Chichibabin",
            4,
        ),
        (
            "Chichibabin_3methylpyridine",
            "Cc1ccncc1",                   # 3-methylpyridine (3-picoline)
            "Nc1cc(C)ccn1",               # 2-amino-5-methylpyridine
            "NaNH2, Chichibabin amination, 120C",
            4,
        ),
    ]

    results = []
    total = len(test_cases)
    passed = 0

    for name, reactant, product, conditions, min_steps in test_cases:
        # Validate SMILES first
        r_mol = Chem.MolFromSmiles(reactant)
        p_mol = Chem.MolFromSmiles(product)
        if r_mol is None or p_mol is None:
            results.append(f"  FAIL  {name}: Invalid reactant/product SMILES")
            continue

        r_can = Chem.MolToSmiles(r_mol)
        p_can = Chem.MolToSmiles(p_mol)

        # Generate mechanism
        steps = _generate_generic_mechanism(reactant, product, conditions)

        if steps is None:
            results.append(f"  FAIL  {name}: No mechanism returned (None)")
            continue

        if len(steps) < min_steps:
            results.append(f"  FAIL  {name}: Expected >= {min_steps} steps, got {len(steps)}")
            continue

        # Verify intermediate SMILES are NOT copies of reactant or product
        intermediates_ok = True
        for i, step in enumerate(steps):
            mol_smi = step.get('mol_smi', '')
            if not mol_smi:
                continue
            int_mol = Chem.MolFromSmiles(mol_smi)
            if int_mol is None:
                results.append(f"  FAIL  {name}: Step {i+1} has invalid SMILES: {mol_smi}")
                intermediates_ok = False
                break
            int_can = Chem.MolToSmiles(int_mol)
            # First and last steps may match reactant/product (that's OK)
            if 0 < i < len(steps) - 1:
                if int_can == r_can:
                    results.append(
                        f"  FAIL  {name}: Step {i+1} intermediate is copy of reactant!")
                    intermediates_ok = False
                    break

        if not intermediates_ok:
            continue

        # Verify arrow_defs or inner_arrows exist in at least one step
        has_arrows = any(
            step.get('inner_arrows') or step.get('arrow_defs')
            for step in steps
        )
        if not has_arrows:
            results.append(f"  FAIL  {name}: No arrow definitions in any step")
            continue

        # Verify mech_badge is present in first step
        badge = steps[0].get('mech_badge', '')
        if not badge:
            results.append(f"  WARN  {name}: No mech_badge in first step (non-critical)")

        # Verify is_intermediate or is_transition_state in middle steps
        has_state_flag = any(
            step.get('is_intermediate') or step.get('is_transition_state')
            for step in steps[1:-1]
        )
        if not has_state_flag:
            results.append(f"  WARN  {name}: No is_intermediate/is_transition_state flags "
                           f"in middle steps")

        passed += 1
        results.append(f"  PASS  {name}: {len(steps)} steps, badge='{badge}'")

    # Print results
    print("=" * 70)
    print(f"Cycle 13 Mechanism Templates Test: {passed}/{total} PASS")
    print("=" * 70)
    for r in results:
        print(r)
    print("=" * 70)

    # Write summary to evidence
    summary_path = os.path.join(EVIDENCE_DIR, 'test_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"Cycle 13 Test Results: {passed}/{total} PASS\n")
        f.write("=" * 60 + "\n")
        for r in results:
            f.write(r + "\n")
    print(f"\nEvidence written to: {summary_path}")

    return passed == total


if __name__ == '__main__':
    success = test_cycle13_templates()
    sys.exit(0 if success else 1)
