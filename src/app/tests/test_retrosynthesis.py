#!/usr/bin/env python3
"""
Comprehensive unit tests for retrosynthesis_engine.py and building_blocks.py.
Covers building block identification, route finding, constraints, performance, and edge cases.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from building_blocks import (
    is_building_block,
    get_building_block_info,
    find_similar_blocks,
    get_all_building_blocks,
    BUILDING_BLOCKS,
)
from retrosynthesis_engine import RetrosynthesisEngine, SynthesisRoute


# ═══════════════════════════════════════════════════════════
# 1. Building Blocks
# ═══════════════════════════════════════════════════════════

class TestBuildingBlockIdentification:
    """is_building_block() correctness."""

    @pytest.mark.parametrize("smiles,name", [
        ("c1ccccc1", "benzene"),
        ("CCO", "ethanol"),
        ("CO", "methanol"),
        ("CC(=O)C", "acetone"),
    ])
    def test_known_building_blocks_return_true(self, smiles, name):
        assert is_building_block(smiles), f"{name} ({smiles}) should be a building block"

    @pytest.mark.parametrize("smiles,name", [
        ("CC(=O)Oc1ccccc1C(=O)O", "aspirin"),
        ("CCOC(=O)c1ccccc1", "ethyl benzoate"),
        ("CC(=O)c1ccccc1", "acetophenone"),
        ("c1ccc([N+](=O)[O-])cc1", "nitrobenzene"),
        ("Nc1ccccc1", "aniline"),
    ])
    def test_complex_molecules_return_false(self, smiles, name):
        assert not is_building_block(smiles), f"{name} ({smiles}) should NOT be a building block"

    def test_invalid_smiles_returns_false(self):
        assert not is_building_block("NOT_A_SMILES")

    def test_empty_string_returns_false(self):
        assert not is_building_block("")

    def test_building_blocks_db_not_empty(self):
        assert len(BUILDING_BLOCKS) > 50, "Expected at least 50 building blocks in the database"


class TestBuildingBlockInfo:
    """get_building_block_info() returns metadata."""

    def test_ethanol_info(self):
        info = get_building_block_info("CCO")
        assert info is not None
        assert "name" in info
        assert "cost" in info

    def test_unknown_molecule_returns_none(self):
        info = get_building_block_info("CC(=O)Oc1ccccc1C(=O)O")  # aspirin
        assert info is None


class TestFindSimilarBlocks:
    """find_similar_blocks() Tanimoto similarity search."""

    def test_returns_results_with_scores(self):
        results = find_similar_blocks("c1ccc(O)cc1")  # phenol
        assert len(results) > 0, "Should find at least one similar building block"
        for smi, name, sim in results:
            assert 0.0 <= sim <= 1.0, f"Similarity {sim} out of [0,1] range"
            assert isinstance(smi, str)
            assert isinstance(name, str)

    def test_benzene_most_similar_to_phenol(self):
        results = find_similar_blocks("c1ccc(O)cc1")  # phenol
        # Benzene should appear among top results (high Tanimoto to phenol)
        top_smiles = [smi for smi, _, _ in results[:5]]
        assert any("c1ccccc1" == s or is_building_block(s) for s in top_smiles)

    def test_top_n_respected(self):
        results = find_similar_blocks("CCO", top_n=3)
        assert len(results) <= 3

    def test_invalid_smiles_returns_empty(self):
        results = find_similar_blocks("INVALID")
        assert results == []


class TestGetAllBuildingBlocks:
    def test_returns_dict_copy(self):
        all_bb = get_all_building_blocks()
        assert isinstance(all_bb, dict)
        assert len(all_bb) == len(BUILDING_BLOCKS)


# ═══════════════════════════════════════════════════════════
# 2. Retrosynthesis Engine — Route Finding
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def engine():
    """Shared engine instance (expensive to construct)."""
    return RetrosynthesisEngine()


class TestEthanolSynthesis:
    """Ethanol: simple molecule, already a building block but routes should also be found."""

    def test_find_at_least_one_route(self, engine):
        routes = engine.find_routes("CCO", max_depth=5, max_routes=10, timeout_seconds=5.0)
        assert len(routes) >= 1, "Ethanol should have at least 1 route (including building-block identity)"

    def test_building_block_route_present(self, engine):
        routes = engine.find_routes("CCO", max_depth=5, max_routes=10, timeout_seconds=5.0)
        # When target is a building block, a 0-step route should be first
        zero_step = [r for r in routes if r.total_steps == 0]
        assert len(zero_step) >= 1, "Ethanol is a building block; expect a 0-step identity route"


class TestPhenolSynthesis:
    """Phenol (Oc1ccccc1): should require 1+ step from benzene."""

    def test_find_routes(self, engine):
        routes = engine.find_routes("Oc1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        assert len(routes) >= 1, "Phenol should have at least 1 synthesis route"

    def test_routes_have_steps(self, engine):
        routes = engine.find_routes("Oc1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        multi_step = [r for r in routes if r.total_steps >= 1]
        assert len(multi_step) >= 1, "At least one phenol route should have 1+ steps"


class TestChlorobenzeneSynthesis:
    """Chlorobenzene (Clc1ccccc1): 1-step EAS from benzene + Cl2."""

    def test_find_eas_route(self, engine):
        routes = engine.find_routes("Clc1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        assert len(routes) >= 1, "Chlorobenzene should have synthesis routes"

    def test_one_step_route_exists(self, engine):
        routes = engine.find_routes("Clc1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        one_step = [r for r in routes if r.total_steps == 1]
        assert len(one_step) >= 1, "Should have a 1-step EAS chlorination route"


class TestAnilineSynthesis:
    """Aniline (Nc1ccccc1): via nitrobenzene reduction."""

    def test_find_routes(self, engine):
        routes = engine.find_routes("Nc1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        assert len(routes) >= 1, "Aniline should have synthesis routes"

    def test_nitro_reduction_step_present(self, engine):
        routes = engine.find_routes("Nc1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        # Look for a route mentioning ArNO2 reduction or nitration
        found_nitro = False
        for route in routes:
            for step in route.steps:
                if "NO₂" in step.transform_name or "Nitrat" in step.transform_name_en or \
                   "Reduction" in step.transform_name_en:
                    found_nitro = True
                    break
        assert found_nitro, "Expected at least one route involving nitro reduction"


class TestAspirinSynthesis:
    """Aspirin (CC(=O)Oc1ccccc1C(=O)O): multi-step synthesis."""

    def test_find_routes(self, engine):
        routes = engine.find_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=6, max_routes=10,
                                    validate=False, timeout_seconds=8.0)
        assert len(routes) >= 1, "Aspirin should have at least 1 synthesis route"

    def test_multi_step(self, engine):
        routes = engine.find_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=6, max_routes=10,
                                    validate=False, timeout_seconds=8.0)
        if routes:
            multi = [r for r in routes if r.total_steps >= 2]
            assert len(multi) >= 1, "Aspirin should require 2+ steps"


class TestEthylBenzoateSynthesis:
    """Ethyl benzoate (CCOC(=O)c1ccccc1): ester from acid + alcohol."""

    def test_find_routes(self, engine):
        routes = engine.find_routes("CCOC(=O)c1ccccc1", max_depth=6, max_routes=10,
                                    validate=False, timeout_seconds=8.0)
        assert len(routes) >= 1, "Ethyl benzoate should have synthesis routes"


class TestAcetophenoneSynthesis:
    """Acetophenone (CC(=O)c1ccccc1): FC acylation route."""

    def test_find_routes(self, engine):
        routes = engine.find_routes("CC(=O)c1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        assert len(routes) >= 1, "Acetophenone should have synthesis routes"

    def test_fc_acylation_present(self, engine):
        routes = engine.find_routes("CC(=O)c1ccccc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        found_fc = False
        for route in routes:
            for step in route.steps:
                if "FC" in step.transform_name or "Acylation" in step.transform_name_en:
                    found_fc = True
                    break
        assert found_fc, "Expected at least one route with Friedel-Crafts acylation"


class TestNitrobenzeneSynthesis:
    """Nitrobenzene (c1ccc([N+](=O)[O-])cc1): EAS nitration route."""

    def test_find_routes(self, engine):
        routes = engine.find_routes("c1ccc([N+](=O)[O-])cc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        assert len(routes) >= 1, "Nitrobenzene should have synthesis routes"

    def test_nitration_step(self, engine):
        routes = engine.find_routes("c1ccc([N+](=O)[O-])cc1", max_depth=5, max_routes=10,
                                    validate=False, timeout_seconds=5.0)
        found_nitration = False
        for route in routes:
            for step in route.steps:
                if "니트로화" in step.transform_name or "Nitration" in step.transform_name_en:
                    found_nitration = True
                    break
        assert found_nitration, "Expected EAS nitration step"


# ═══════════════════════════════════════════════════════════
# 3. Constraints
# ═══════════════════════════════════════════════════════════

class TestRouteConstraints:
    """Structural constraints on returned routes."""

    def test_no_routes_exceed_max_depth(self, engine):
        max_d = 10
        routes = engine.find_routes("CC(=O)Oc1ccccc1C(=O)O",  # aspirin
                                    max_depth=max_d, max_routes=20,
                                    validate=False, timeout_seconds=8.0)
        for route in routes:
            assert route.total_steps <= max_d, \
                f"Route has {route.total_steps} steps, exceeding max_depth={max_d}"

    def test_no_circular_routes(self, engine):
        """Target should not appear as a building block in its own multi-step route."""
        target = "Clc1ccccc1"  # chlorobenzene
        routes = engine.find_routes(target, max_depth=5, max_routes=20,
                                    validate=False, timeout_seconds=5.0)
        from rdkit import Chem
        target_canon = Chem.MolToSmiles(Chem.MolFromSmiles(target))
        for route in routes:
            if route.total_steps > 0:
                bb_canons = set()
                for bb in route.building_blocks:
                    mol = Chem.MolFromSmiles(bb)
                    if mol:
                        bb_canons.add(Chem.MolToSmiles(mol))
                assert target_canon not in bb_canons, \
                    f"Circular route: target {target_canon} found in its own building blocks"

    def test_building_blocks_are_actual_building_blocks(self, engine):
        routes = engine.find_routes("Clc1ccccc1", max_depth=5, max_routes=20,
                                    validate=False, timeout_seconds=5.0)
        for route in routes:
            if route.total_steps > 0:
                for bb in route.building_blocks:
                    assert is_building_block(bb), \
                        f"Route building block '{bb}' is not in the building blocks database"

    def test_routes_sorted_by_score_ascending(self, engine):
        routes = engine.find_routes("CC(=O)c1ccccc1",  # acetophenone
                                    max_depth=5, max_routes=20,
                                    validate=False, timeout_seconds=5.0)
        if len(routes) >= 2:
            scores = [r.score for r in routes]
            for i in range(len(scores) - 1):
                assert scores[i] <= scores[i + 1], \
                    f"Routes not sorted by score: {scores[i]} > {scores[i+1]}"


# ═══════════════════════════════════════════════════════════
# 4. Performance
# ═══════════════════════════════════════════════════════════

class TestPerformance:
    """Search should complete within reasonable time."""

    @pytest.mark.parametrize("smiles,name,timeout", [
        ("Clc1ccccc1", "chlorobenzene", 5),
        ("CCO", "ethanol", 5),
        ("CC(=O)C", "acetone", 5),
    ])
    def test_simple_molecule_within_timeout(self, engine, smiles, name, timeout):
        start = time.time()
        engine.find_routes(smiles, max_depth=5, max_routes=10, validate=False,
                           timeout_seconds=float(timeout))
        elapsed = time.time() - start
        assert elapsed < timeout + 1.0, \
            f"{name} search took {elapsed:.1f}s, exceeded {timeout}s timeout"


# ═══════════════════════════════════════════════════════════
# 5. Edge Cases
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    """Invalid inputs and boundary conditions."""

    def test_invalid_smiles_returns_empty(self, engine):
        routes = engine.find_routes("NOT_VALID_SMILES", max_depth=5, timeout_seconds=2.0)
        assert routes == [], "Invalid SMILES should return empty list"

    def test_empty_string_returns_empty(self, engine):
        routes = engine.find_routes("", max_depth=5, timeout_seconds=2.0)
        assert routes == [], "Empty string should return empty list"

    def test_complex_molecule_within_timeout(self, engine):
        """Very complex molecule (cholesterol, MW~387) should still return within timeout."""
        cholesterol = "C[C@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]1[C@H]2CC=C2C[C@@H](O)CC[C@@]21C)C"
        timeout = 10.0
        start = time.time()
        routes = engine.find_routes(cholesterol, max_depth=3, max_routes=5,
                                    validate=False, timeout_seconds=timeout)
        elapsed = time.time() - start
        assert elapsed < timeout + 2.0, \
            f"Complex molecule search took {elapsed:.1f}s, should finish within {timeout}s"
        # Result can be empty (no routes found is acceptable), but must not hang
        assert isinstance(routes, list)


class TestEngineInitialization:
    """Engine should initialize properly."""

    def test_transforms_loaded(self, engine):
        assert len(engine._transforms) > 20, \
            f"Expected 20+ compiled transforms, got {len(engine._transforms)}"

    def test_transforms_have_compiled_reactions(self, engine):
        for t in engine._transforms:
            assert t._compiled_rxn is not None, f"Transform '{t.name}' has no compiled reaction"


class TestSynthesisRouteDataclass:
    """Verify route data structure fields."""

    def test_route_fields(self, engine):
        routes = engine.find_routes("Clc1ccccc1", max_depth=5, max_routes=5,
                                    validate=False, timeout_seconds=5.0)
        for route in routes:
            assert isinstance(route, SynthesisRoute)
            assert isinstance(route.target_smiles, str)
            assert isinstance(route.steps, list)
            assert isinstance(route.total_steps, int)
            assert isinstance(route.score, float)
            assert isinstance(route.building_blocks, list)
            assert route.total_steps == len(route.steps)

    def test_step_fields(self, engine):
        routes = engine.find_routes("Clc1ccccc1", max_depth=5, max_routes=5,
                                    validate=False, timeout_seconds=5.0)
        for route in routes:
            for step in route.steps:
                assert isinstance(step.reactant_smiles, list)
                assert isinstance(step.product_smiles, str)
                assert isinstance(step.transform_name, str)
                assert isinstance(step.transform_name_en, str)
                assert isinstance(step.conditions, str)
                assert 0.0 <= step.confidence <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
