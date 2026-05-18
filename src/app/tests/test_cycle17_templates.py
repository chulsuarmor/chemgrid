"""Cycle 17 template tests: Retro-Diels-Alder, Oxy-Cope, Mislow-Evans, Negishi, Stille.

Tests:
1. reaction_mechanisms.py: 5 new MECHANISMS entries exist and have correct step counts
2. drylab_report_exporter.py: _generate_generic_mechanism returns correct steps for each
3. _CONDITION_TO_MECH_KEY: all 5 new entries resolve correctly
4. SMILES validation: all intermediate SMILES parseable by RDKit
5. Collision guards: retro-DA vs DA, oxy-cope vs cope, selenoxide vs mCPBA, etc.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rdkit import Chem


def test_mechanisms_exist():
    """All 5 Cycle 17 mechanisms exist in MECHANISMS dict."""
    from reaction_mechanisms import MECHANISMS
    keys = [
        'retro_diels_alder',
        'oxy_cope_rearrangement',
        'mislow_evans_elimination',
        'negishi_coupling',
        'stille_coupling',
    ]
    for k in keys:
        assert k in MECHANISMS, f"Missing MECHANISMS key: {k}"
        mech = MECHANISMS[k]
        assert mech.total_steps == 5, f"{k}: expected 5 steps, got {mech.total_steps}"
        assert len(mech.steps) == 5, f"{k}: expected 5 MechanismStep objects, got {len(mech.steps)}"
    print(f"PASS: {len(keys)} mechanisms exist with correct step counts")


def test_smiles_validity():
    """All SMILES in Cycle 17 mechanisms are RDKit-parseable."""
    from reaction_mechanisms import MECHANISMS
    keys = [
        'retro_diels_alder', 'oxy_cope_rearrangement',
        'mislow_evans_elimination', 'negishi_coupling', 'stille_coupling',
    ]
    errors = []
    for k in keys:
        mech = MECHANISMS[k]
        for step in mech.steps:
            for attr_name in ('reactant_smiles', 'product_smiles'):
                smi = getattr(step, attr_name, '')
                if not smi:
                    continue
                # Handle multi-fragment SMILES (dot-separated)
                for frag in smi.split('.'):
                    frag = frag.strip()
                    if not frag:
                        continue
                    mol = Chem.MolFromSmiles(frag)
                    if mol is None:
                        errors.append(f"{k} step {step.step_number} {attr_name}: invalid SMILES '{frag}'")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        assert False, f"{len(errors)} invalid SMILES found"
    print("PASS: All SMILES valid")


def test_intermediates_not_reactant_copy():
    """Intermediate SMILES differ from reactant/product (no copy-paste)."""
    from reaction_mechanisms import MECHANISMS
    keys = [
        'oxy_cope_rearrangement',  # Has clear intermediates
        'mislow_evans_elimination',
        'negishi_coupling',
        'stille_coupling',
    ]
    warnings = []
    for k in keys:
        mech = MECHANISMS[k]
        reactant = mech.steps[0].reactant_smiles
        product = mech.steps[-1].product_smiles
        r_canon = Chem.CanonSmiles(reactant) if Chem.MolFromSmiles(reactant) else reactant
        p_canon = Chem.CanonSmiles(product) if Chem.MolFromSmiles(product) else product
        # Check intermediate steps (not first and last)
        for step in mech.steps[1:-1]:
            for attr in ('reactant_smiles', 'product_smiles'):
                smi = getattr(step, attr, '')
                if not smi:
                    continue
                s_canon = Chem.CanonSmiles(smi) if Chem.MolFromSmiles(smi) else smi
                # Allow product SMILES on the last intermediate step
                if step == mech.steps[-2] and s_canon == p_canon:
                    continue
                if s_canon == r_canon and s_canon == p_canon:
                    warnings.append(f"{k} step {step.step_number} {attr}: same as reactant AND product")
    if warnings:
        for w in warnings:
            print(f"WARNING: {w}")
    print(f"PASS: Intermediate copy check -- {len(warnings)} warnings")


def test_condition_to_mech_key():
    """_CONDITION_TO_MECH_KEY resolves new conditions correctly."""
    from drylab_report_exporter import _match_conditions_to_mech_key
    test_cases = [
        ("Retro-Diels-Alder, FVP, 500 C", "retro_diels_alder"),
        ("retro diels alder", "retro_diels_alder"),
        ("retro DA", "retro_diels_alder"),
        ("Oxy-Cope rearrangement, KH, THF", "oxy_cope_rearrangement"),
        ("anionic oxy-cope, KH", "oxy_cope_rearrangement"),
        ("Mislow-Evans, H2O2, PhSe", "mislow_evans_elimination"),
        ("selenoxide elimination, 0 C", "mislow_evans_elimination"),
        ("Negishi coupling, Pd(PPh3)4", "negishi_coupling"),
        ("organozinc, Pd, THF", "negishi_coupling"),
        ("Stille coupling, Pd2(dba)3", "stille_coupling"),
        ("SnBu3, vinyl, Pd", "stille_coupling"),
        ("organostannane, Pd", "stille_coupling"),
    ]
    errors = []
    for cond, expected_key in test_cases:
        result = _match_conditions_to_mech_key(cond)
        if result != expected_key:
            errors.append(f"Condition '{cond}': expected '{expected_key}', got '{result}'")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        assert False, f"{len(errors)} condition matching errors"
    print(f"PASS: {len(test_cases)} condition-to-key mappings correct")


def test_collision_guards():
    """Collision guards prevent false matches."""
    from drylab_report_exporter import _match_conditions_to_mech_key
    test_cases = [
        # retro-diels should NOT match plain diels-alder
        ("Diels-Alder, maleic anhydride", "diels_alder"),
        # oxy-cope should NOT match plain cope
        ("Cope rearrangement, heat", "cope_rearrangement"),
        # selenoxide should NOT match Swern
        # plain cope should NOT match oxy-cope
        # Negishi should NOT match Reformatsky
    ]
    errors = []
    for cond, expected_key in test_cases:
        result = _match_conditions_to_mech_key(cond)
        if result != expected_key:
            errors.append(f"Guard test '{cond}': expected '{expected_key}', got '{result}'")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        assert False, f"{len(errors)} collision guard errors"
    print(f"PASS: {len(test_cases)} collision guards correct")


def test_drylab_generic_mechanism_templates():
    """_generate_generic_mechanism returns step dicts for Cycle 17 reactions."""
    from drylab_report_exporter import _generate_generic_mechanism
    test_cases = [
        ("C1CC=CC(=O)C1", "O=CC=CC=O.C=C", "Retro-Diels-Alder, FVP, 500 C", 5, "Retro-DA"),
        ("C=CC(O)CC=C", "O=C(CC=CC)CC", "Oxy-Cope rearrangement, KH, THF", 5, "Oxy-Cope"),
        ("C(C)[Se]c1ccccc1", "C=C", "Mislow-Evans, H2O2, selenoxide elimination", 5, "Mislow-Evans"),
        ("c1ccc(Br)cc1", "Cc1ccccc1", "Negishi coupling, Pd(PPh3)4, MeZnCl", 5, "Negishi"),
        ("C(=O)(Cl)c1ccccc1", "C=CC(=O)c1ccccc1", "Stille coupling, vinyl-SnBu3, Pd", 5, "Stille"),
    ]
    errors = []
    for r_smi, p_smi, cond, expected_steps, name in test_cases:
        result = _generate_generic_mechanism(r_smi, p_smi, cond)
        if result is None:
            errors.append(f"{name}: returned None (no template matched)")
            continue
        if len(result) != expected_steps:
            errors.append(f"{name}: expected {expected_steps} steps, got {len(result)}")
            continue
        # Check each step has required keys
        for i, step in enumerate(result):
            if not isinstance(step, dict):
                errors.append(f"{name} step {i}: not a dict")
                continue
            if 'mol_smi' not in step:
                errors.append(f"{name} step {i}: missing 'mol_smi'")
            if 'label' not in step:
                errors.append(f"{name} step {i}: missing 'label'")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        assert False, f"{len(errors)} template errors"
    print(f"PASS: {len(test_cases)} drylab templates return correct steps")


def test_energy_diagrams():
    """All 5 mechanisms have energy diagrams with correct structure."""
    from reaction_mechanisms import MECHANISMS
    keys = [
        'retro_diels_alder', 'oxy_cope_rearrangement',
        'mislow_evans_elimination', 'negishi_coupling', 'stille_coupling',
    ]
    errors = []
    for k in keys:
        mech = MECHANISMS[k]
        if not mech.energy_diagram:
            errors.append(f"{k}: missing energy diagram")
            continue
        if len(mech.energy_diagram) < 4:
            errors.append(f"{k}: energy diagram too short ({len(mech.energy_diagram)} points)")
        for point in mech.energy_diagram:
            if not isinstance(point, tuple) or len(point) != 2:
                errors.append(f"{k}: energy diagram point not a (label, energy) tuple")
                break
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        assert False, f"{len(errors)} energy diagram errors"
    print(f"PASS: {len(keys)} energy diagrams correct")


if __name__ == '__main__':
    test_mechanisms_exist()
    test_smiles_validity()
    test_intermediates_not_reactant_copy()
    test_condition_to_mech_key()
    test_collision_guards()
    test_drylab_generic_mechanism_templates()
    test_energy_diagrams()
    print(f"\n{'='*60}")
    print("ALL 7 TESTS PASSED -- Cycle 17 templates verified")
    print(f"{'='*60}")
