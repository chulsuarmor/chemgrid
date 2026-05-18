"""Cycle 15 template tests: Barton Reaction, Eschenmoser-Claisen, Ireland-Claisen,
Overman Rearrangement, Rupe Rearrangement.

Tests:
1. reaction_mechanisms.py: MECHANISMS dict entries exist, steps valid, SMILES parseable
2. drylab_report_exporter.py: _generate_generic_mechanism returns steps for each reaction
3. _CONDITION_TO_MECH_KEY: keyword mapping resolves correctly
4. No keyword collision with existing reactions
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rdkit import Chem

# ── Test 1: reaction_mechanisms.py entries ──
def test_mechanisms_exist():
    from reaction_mechanisms import MECHANISMS
    keys = [
        'barton_reaction', 'eschenmoser_claisen', 'ireland_claisen',
        'overman_rearrangement', 'rupe_rearrangement',
    ]
    for k in keys:
        assert k in MECHANISMS, f"Missing MECHANISMS['{k}']"
        md = MECHANISMS[k]
        assert md.total_steps >= 4, f"{k}: too few steps ({md.total_steps})"
        assert len(md.steps) >= 4, f"{k}: steps list shorter than total_steps"
    print("test_mechanisms_exist -- PASS (5/5)")


def test_mechanisms_smiles_valid():
    from reaction_mechanisms import MECHANISMS
    keys = [
        'barton_reaction', 'eschenmoser_claisen', 'ireland_claisen',
        'overman_rearrangement', 'rupe_rearrangement',
    ]
    fail_count = 0
    for k in keys:
        md = MECHANISMS[k]
        for step in md.steps:
            for attr in ('reactant_smiles', 'product_smiles'):
                smi = getattr(step, attr)
                mol = Chem.MolFromSmiles(smi)
                if mol is None:
                    print(f"  FAIL: {k} step {step.step_number} {attr} = '{smi}'")
                    fail_count += 1
    assert fail_count == 0, f"{fail_count} invalid SMILES found"
    print("test_mechanisms_smiles_valid -- PASS")


def test_mechanisms_intermediates_differ():
    """Intermediates must differ from reactant/product (canonical SMILES)."""
    from reaction_mechanisms import MECHANISMS
    keys = [
        'barton_reaction', 'eschenmoser_claisen', 'ireland_claisen',
        'overman_rearrangement', 'rupe_rearrangement',
    ]
    for k in keys:
        md = MECHANISMS[k]
        first_smi = Chem.MolToSmiles(Chem.MolFromSmiles(md.steps[0].reactant_smiles))
        last_smi = Chem.MolToSmiles(Chem.MolFromSmiles(md.steps[-1].product_smiles))
        # At least one intermediate should differ from both first reactant and last product
        has_unique = False
        for step in md.steps[1:-1]:
            r_can = Chem.MolToSmiles(Chem.MolFromSmiles(step.reactant_smiles))
            p_can = Chem.MolToSmiles(Chem.MolFromSmiles(step.product_smiles))
            if r_can != first_smi and r_can != last_smi:
                has_unique = True
                break
            if p_can != first_smi and p_can != last_smi:
                has_unique = True
                break
        assert has_unique, f"{k}: no unique intermediate (all steps copy reactant/product)"
    print("test_mechanisms_intermediates_differ -- PASS")


# ── Test 2: drylab_report_exporter template blocks ──
def test_drylab_templates():
    from drylab_report_exporter import _generate_generic_mechanism
    test_cases = [
        ("Barton reaction, hv, nitrite, delta-nitroso", "CCCCCON=O", "OCC(/C=N/O)CCC"),
        ("Eschenmoser-Claisen, dimethylacetamide dimethyl acetal, xylene, 140C", "C=CCO", "C=CCC(=O)N(C)C"),
        ("Ireland-Claisen, LDA, TMSCl, -78C", "C=CCOC(=O)CC", "C=CCC(C)C(=O)O"),
        ("Overman rearrangement, Cl3CCN, NaH, xylene", "C=CCO", "C=CCN"),
        ("Rupe rearrangement, H2SO4, propargylic alcohol", "CC(O)(C#C)C", "CC(=CC=O)C"),
    ]
    for cond, rsmi, psmi in test_cases:
        result = _generate_generic_mechanism(rsmi, psmi, cond)
        assert result is not None, f"No template for '{cond}'"
        assert len(result) >= 4, f"'{cond}': too few steps ({len(result)})"
        # All step mol_smi must be RDKit-parseable
        for i, step in enumerate(result):
            mol = Chem.MolFromSmiles(step['mol_smi'])
            assert mol is not None, f"'{cond}' step {i}: invalid mol_smi '{step['mol_smi']}'"
    print("test_drylab_templates -- PASS (5/5)")


# ── Test 3: _CONDITION_TO_MECH_KEY resolution ──
def test_condition_mapping():
    from drylab_report_exporter import _match_conditions_to_mech_key
    mappings = [
        ("Barton reaction, hv, nitrite", "barton_reaction"),
        ("Barton photolysis, UV", "barton_reaction"),
        ("Eschenmoser-Claisen, DMA acetal", "eschenmoser_claisen"),
        ("Eschenmoser Claisen rearrangement", "eschenmoser_claisen"),
        ("Ireland-Claisen, LDA, TMSCl", "ireland_claisen"),
        ("Ireland Claisen rearrangement", "ireland_claisen"),
        ("Overman rearrangement, PdCl2", "overman_rearrangement"),
        ("Rupe rearrangement, H2SO4", "rupe_rearrangement"),
    ]
    for cond, expected in mappings:
        result = _match_conditions_to_mech_key(cond)
        assert result == expected, f"'{cond}' -> '{result}' (expected '{expected}')"
    print("test_condition_mapping -- PASS (8/8)")


# ── Test 4: No collision with existing reactions ──
def test_no_collision():
    from drylab_report_exporter import _match_conditions_to_mech_key
    # These should NOT map to the new Cycle 15 reactions
    no_collision = [
        ("Barton decarboxylation, thiohydroxamic", "barton_decarboxylation"),
        ("Barton ester, radical", "barton_decarboxylation"),
        ("Eschenmoser-Tanabe fragmentation", "eschenmoser_tanabe"),
        ("Claisen rearrangement, allyl vinyl ether", "claisen_rearrangement"),
    ]
    for cond, expected in no_collision:
        result = _match_conditions_to_mech_key(cond)
        assert result == expected, f"Collision! '{cond}' -> '{result}' (expected '{expected}')"
    print("test_no_collision -- PASS (4/4)")


# ── Test 5: Barton reaction uses half-arrows (radical) ──
def test_barton_radical_arrows():
    from drylab_report_exporter import _generate_generic_mechanism
    result = _generate_generic_mechanism("CCCCCON=O", "OCC(/C=N/O)CCC",
                                          "Barton reaction, hv, nitrite")
    assert result is not None
    # At least one step should have half_arrows=True (radical)
    has_half = any(step.get('half_arrows', False) for step in result)
    assert has_half, "Barton reaction should have radical (half) arrows"
    print("test_barton_radical_arrows -- PASS")


# ── Test 6: Sigmatropic rearrangements have TS steps ──
def test_sigmatropic_ts():
    from drylab_report_exporter import _generate_generic_mechanism
    cases = [
        ("Eschenmoser-Claisen, xylene", "C=CCO", "C=CCC(=O)N(C)C"),
        ("Ireland-Claisen, LDA, TMSCl", "C=CCOC(=O)CC", "C=CCC(C)C(=O)O"),
        ("Overman rearrangement, Cl3CCN", "C=CCO", "C=CCN"),
    ]
    for cond, rsmi, psmi in cases:
        result = _generate_generic_mechanism(rsmi, psmi, cond)
        assert result is not None, f"No template for '{cond}'"
        has_ts = any(step.get('is_transition_state', False) for step in result)
        assert has_ts, f"'{cond}' should have a transition state step"
    print("test_sigmatropic_ts -- PASS (3/3)")


# ── Test 7: Rupe uses ionic (not radical) arrows ──
def test_rupe_ionic():
    from drylab_report_exporter import _generate_generic_mechanism
    result = _generate_generic_mechanism("CC(O)(C#C)C", "CC(=CC=O)C",
                                          "Rupe rearrangement, H2SO4")
    assert result is not None
    # Rupe is ionic, should NOT have half_arrows=True
    for step in result:
        assert not step.get('half_arrows', False), "Rupe should be ionic, not radical"
    print("test_rupe_ionic -- PASS")


# ── Test 8: Ireland-Claisen guard against generic Claisen ──
def test_ireland_vs_claisen():
    from drylab_report_exporter import _generate_generic_mechanism
    # Generic Claisen should NOT trigger Ireland-Claisen
    result = _generate_generic_mechanism("C=CCOC=C", "C=CCC(=O)C",
                                          "Claisen rearrangement")
    if result is not None:
        # Should not have Ireland badge
        for step in result:
            badge = step.get('mech_badge', '')
            assert 'Ireland' not in badge, "Generic Claisen should not produce Ireland badge"
    print("test_ireland_vs_claisen -- PASS")


# ── Test 9: Eschenmoser-Claisen vs Eschenmoser-Tanabe ──
def test_eschenmoser_collision():
    from drylab_report_exporter import _generate_generic_mechanism
    # Eschenmoser-Tanabe (fragmentation) should NOT trigger Eschenmoser-Claisen
    result = _generate_generic_mechanism("O=C1CCCCC1O1CC1", "C#CC(=O)CCCC",
                                          "Eschenmoser-Tanabe fragmentation")
    if result is not None:
        for step in result:
            badge = step.get('mech_badge', '')
            assert 'Eschenmoser-Claisen' not in badge, "E-T fragmentation should not produce E-C badge"
    print("test_eschenmoser_collision -- PASS")


# ── Test 10: Energy diagrams exist ──
def test_energy_diagrams():
    from reaction_mechanisms import MECHANISMS
    keys = [
        'barton_reaction', 'eschenmoser_claisen', 'ireland_claisen',
        'overman_rearrangement', 'rupe_rearrangement',
    ]
    for k in keys:
        md = MECHANISMS[k]
        assert len(md.energy_diagram) >= 4, f"{k}: energy diagram too short ({len(md.energy_diagram)})"
    print("test_energy_diagrams -- PASS (5/5)")


# ── Test 11: Step count validation ──
def test_step_counts():
    from reaction_mechanisms import MECHANISMS
    expected = {
        'barton_reaction': 5,
        'eschenmoser_claisen': 5,
        'ireland_claisen': 5,
        'overman_rearrangement': 5,
        'rupe_rearrangement': 5,
    }
    for k, exp in expected.items():
        md = MECHANISMS[k]
        assert md.total_steps == exp, f"{k}: expected {exp} steps, got {md.total_steps}"
        assert len(md.steps) == exp, f"{k}: steps list has {len(md.steps)}, expected {exp}"
    print("test_step_counts -- PASS (5/5)")


if __name__ == '__main__':
    test_mechanisms_exist()
    test_mechanisms_smiles_valid()
    test_mechanisms_intermediates_differ()
    test_drylab_templates()
    test_condition_mapping()
    test_no_collision()
    test_barton_radical_arrows()
    test_sigmatropic_ts()
    test_rupe_ionic()
    test_ireland_vs_claisen()
    test_eschenmoser_collision()
    test_energy_diagrams()
    test_step_counts()
    print("\n=== All 13 tests PASS ===")
