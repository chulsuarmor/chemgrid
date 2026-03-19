#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vaccine Circulation Test (백신 공회전 테스트)
=============================================
ChemGrid 감사팀 검증용: 50개 복잡/까다로운/비정상 분자를 투입하여
시스템이 에러를 올바르게 감지하는지, 또는 조용히 실패(silent fail)하는지 검사.

Categories:
  1. Bridged/Cage (5)
  2. Metal complexes (5)
  3. Large drugs (10)
  4. Stereochemistry challenges (5)
  5. Reactive intermediates (5)
  6. Heterocyclic fused (5)
  7. Natural products (5)
  8. Intentionally wrong (5) - audit team MUST flag these
  9. Edge cases (5)

Tests per molecule:
  A. SMILES parsing (RDKit Chem.MolFromSmiles)
  B. IR spectrum generation (predict_spectra.predict_ir)
  C. 3D coordinate generation (AllChem.EmbedMolecule)
  D. Lead optimizer variant generation (MoleculeVariantGenerator)
  E. ADMET prediction (admet_predictor.predict_admet)
"""

import sys
import os
import traceback
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

# Add src/app to path
APP_DIR = Path(__file__).resolve().parent.parent / "src" / "app"
sys.path.insert(0, str(APP_DIR))

# Imports
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors

from predict_spectra import predict_ir
from admet_predictor import predict_admet
from lead_optimizer import MoleculeVariantGenerator

# ============================================================================
# MOLECULE DEFINITIONS (50 total)
# ============================================================================

@dataclass
class TestMolecule:
    name: str
    smiles: str
    category: str
    notes: str = ""
    expected_parse: bool = True  # Should SMILES parse succeed?
    expected_3d: bool = True     # Should 3D embedding succeed?
    known_issues: str = ""       # Known pitfalls for audit teams


MOLECULES: List[TestMolecule] = [
    # ── Category 1: Bridged/Cage Structures (5) ──────────────────────
    TestMolecule(
        "Cubane", "C12C3C4C1C5C3C4C25",
        "bridged_cage",
        notes="Platonic solid hydrocarbon, extreme angle strain ~90deg",
        known_issues="3D embedding may fail due to strain; IR should show no C=C"
    ),
    TestMolecule(
        "Norbornane (bicyclo[2.2.1]heptane)", "C1CC2CC1CC2",
        "bridged_cage",
        notes="Classic bridged bicyclic, rigid skeleton"
    ),
    TestMolecule(
        "2-Adamantanone", "O=C1C2CC3CC1CC(C2)C3",
        "bridged_cage",
        notes="Adamantane with ketone; strong C=O ~1715 cm-1 in IR"
    ),
    TestMolecule(
        "Bicyclo[2.2.2]octane", "C1CC2CCC1CC2",
        "bridged_cage",
        notes="Symmetric bridged bicyclic"
    ),
    TestMolecule(
        "Spiro[4.5]decan-6-one", "O=C1CCCCC12CCCC2",
        "bridged_cage",
        notes="Spirocyclic ketone, shared quaternary carbon"
    ),

    # ── Category 2: Metal Complexes (5) ──────────────────────────────
    TestMolecule(
        "Ferrocene", "[Fe+2].[cH-]1cccc1.[cH-]1cccc1",
        "metal_complex",
        notes="Sandwich complex; RDKit can parse but 3D embedding is unreliable",
        expected_3d=False,
        known_issues="Metal complexes: 3D often fails, ADMET meaningless for organometallics"
    ),
    TestMolecule(
        "Cisplatin", "[NH3][Pt]([NH3])(Cl)Cl",
        "metal_complex",
        notes="Square planar Pt(II), cis geometry crucial for activity",
        expected_3d=False,
        known_issues="RDKit 3D embedding unreliable for Pt; ADMET not designed for metals"
    ),
    TestMolecule(
        "Hemoglobin Fe-porphyrin core (simplified)", "[Fe+2]1(N2=CC3=CC4=CC(=CC5=CC(=CC1=C2C=C3)N5)N4)([NH3])[NH3]",
        "metal_complex",
        notes="Simplified iron porphyrin; may not parse correctly",
        expected_parse=False,
        expected_3d=False,
        known_issues="Complex coordination chemistry; SMILES may be invalid"
    ),
    TestMolecule(
        "Zinc phthalocyanine core", "[Zn+2].c1cc2nc1cc1ccc(nc1cc1ccc([nH]c1cc1ccc(nc1cc1ccc2[nH]1)c1)c1)c1",
        "metal_complex",
        notes="Large macrocyclic metal complex",
        expected_3d=False,
        known_issues="Very large ring system with metal; 3D embedding almost certainly fails"
    ),
    TestMolecule(
        "Ruthenium tris-bipyridyl", "[Ru+2].c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1",
        "metal_complex",
        notes="Photochemistry workhorse; disconnected fragments with metal ion",
        expected_3d=False,
        known_issues="RDKit handles as disconnected fragments; ADMET meaningless"
    ),

    # ── Category 3: Large Drugs (10) ─────────────────────────────────
    TestMolecule(
        "Taxol (paclitaxel) core",
        "CC1=C2C(C(=O)C3(C(CC4C(C3C(C(C2(C)C)(CC1OC(=O)C(C(C5=CC=CC=C5)NC(=O)C6=CC=CC=C6)O)O)OC(=O)C7=CC=CC=C7)(CO4)OC(=O)C)O)C)OC(=O)C",
        "large_drug",
        notes="MW ~853; major anticancer drug; should violate Lipinski heavily"
    ),
    TestMolecule(
        "Erythromycin A",
        "CCC1C(C(C(C(=O)C(CC(C(C(C(C(C(=O)O1)C)OC2CC(C(C(O2)C)O)(C)OC)C)OC3C(C(CC(O3)C)N(C)C)O)(C)O)C)C)O)(C)O",
        "large_drug",
        notes="Macrolide antibiotic; MW ~733; complex stereochemistry"
    ),
    TestMolecule(
        "Vancomycin core (simplified)",
        "CC1C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC1C(C(C2=CC(=C(C(=C2)Cl)OC3=CC=C(C=C3)C(C(=O)N)NC(=O)C4CC(=O)N4)O)Cl)O)CC5=CC=CC=C5)CC(=O)N)C(C)C)CC(=O)N)C(C)O",
        "large_drug",
        notes="Glycopeptide antibiotic, last-resort drug; extremely complex"
    ),
    TestMolecule(
        "Cyclosporin A fragment (linear)",
        "CC1C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)N1C)CC2=CC=CC=C2)C(C)C)CC(C)C)C(C)C)CC(=O)O",
        "large_drug",
        notes="Immunosuppressant cyclic peptide fragment"
    ),
    TestMolecule(
        "Doxorubicin",
        "CC1C(C(CC(O1)OC2CC(CC3=C2C(=C4C(=C3O)C(=O)C5=C(C4=O)C(=CC=C5)OC)O)(C(=O)CO)O)N)O",
        "large_drug",
        notes="Anthracycline anticancer; MW ~543; quinone system"
    ),
    TestMolecule(
        "Sorafenib",
        "CNC(=O)C1=CC(=C(C=C1)OC2=CC=C(C=C2)NC(=O)NC3=CC(=C(C=C3)Cl)C(F)(F)F)C",
        "large_drug",
        notes="Multi-kinase inhibitor; urea linkage; CF3 group"
    ),
    TestMolecule(
        "Imatinib",
        "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5",
        "large_drug",
        notes="BCR-ABL kinase inhibitor (Gleevec); piperazine ring"
    ),
    TestMolecule(
        "Osimertinib",
        "C=CC(=O)NC1=CC(=C(C=C1NC2=NC=CC(=N2)C3=CN(C=C3)C)OC)N(C)CCN(C)C",
        "large_drug",
        notes="3rd-gen EGFR inhibitor; acrylamide warhead (Michael acceptor)"
    ),
    TestMolecule(
        "Lenalidomide",
        "C1CC(=O)NC(=O)C1N2CC3=CC=CC=C3C2=O",
        "large_drug",
        notes="Thalidomide analog; immunomodulatory; MW ~259; glutarimide ring"
    ),
    TestMolecule(
        "Bortezomib",
        "CC(C)CC(NC(=O)C(CC1=CC=CC=C1)NC(=O)C2=NC=CN=C2)B(O)O",
        "large_drug",
        notes="Proteasome inhibitor; BORONIC ACID group; B atom may cause issues"
    ),

    # ── Category 4: Stereochemistry Challenges (5) ───────────────────
    TestMolecule(
        "(R)-Thalidomide vs (S)-Thalidomide (R-form)",
        "O=C1CC[C@H](N1C2=CC=CC=C2C(=O)O)C(=O)O",
        "stereochemistry",
        notes="The R-enantiomer is sedative; S causes birth defects. System must preserve chirality.",
        known_issues="If chirality is lost in processing, this is a CRITICAL silent failure"
    ),
    TestMolecule(
        "Meso-tartaric acid",
        "OC(=O)[C@H](O)[C@@H](O)C(=O)O",
        "stereochemistry",
        notes="Meso compound: has chiral centers but is achiral overall due to internal mirror plane",
        known_issues="System should recognize this as achiral despite having stereocenters"
    ),
    TestMolecule(
        "BINAP (axial chirality)",
        "C1=CC=C(C2=C1C3=CC=CC=C3C=C2P(C4=CC=CC=C4)C5=CC=CC=C5)C6=CC=CC7=CC=CC=C76",
        "stereochemistry",
        notes="Atropisomeric biaryl; axial chirality not defined in this SMILES",
        known_issues="Axial chirality cannot be encoded in standard SMILES; system may not flag this"
    ),
    TestMolecule(
        "cis-Decalin",
        "C1CCC2CCCCC2C1",
        "stereochemistry",
        notes="Ring junction stereochemistry; cis vs trans not specified here",
        known_issues="Without explicit stereo, 3D may generate either isomer randomly"
    ),
    TestMolecule(
        "(S)-Ibuprofen",
        "CC(C)Cc1ccc([C@H](C)C(=O)O)cc1",
        "stereochemistry",
        notes="Only S-enantiomer is pharmacologically active; R is inactive",
        known_issues="Lead optimizer must preserve stereochemistry in variants"
    ),

    # ── Category 5: Reactive Intermediates (5) ───────────────────────
    TestMolecule(
        "tert-Butyl carbocation",
        "CC(C)[CH2+]",
        "reactive_intermediate",
        notes="Tertiary carbocation; positive formal charge",
        expected_3d=True,
        known_issues="Charged species; ADMET makes no physical sense; should warn"
    ),
    TestMolecule(
        "Triphenylmethyl carbanion",
        "[CH-](c1ccccc1)(c1ccccc1)c1ccccc1",
        "reactive_intermediate",
        notes="Stabilized carbanion; negative formal charge",
        known_issues="Charged species; ADMET/drug properties meaningless"
    ),
    TestMolecule(
        "Phenyl radical (SMILES approx)",
        "[CH2]c1ccccc1",
        "reactive_intermediate",
        notes="Benzyl radical approximation; radical notation limited in SMILES",
        known_issues="Standard SMILES cannot represent radicals properly; silent misparse likely"
    ),
    TestMolecule(
        "Dichlorocarbene",
        "Cl[C]Cl",
        "reactive_intermediate",
        notes="Carbene: divalent carbon; extremely reactive",
        known_issues="RDKit may reject or misinterpret divalent carbon"
    ),
    TestMolecule(
        "Phenyl nitrene (approx)",
        "[N]c1ccccc1",
        "reactive_intermediate",
        notes="Nitrene: monovalent nitrogen; SMILES encoding is approximate",
        known_issues="Monovalent N unusual; RDKit may add implicit H or reject"
    ),

    # ── Category 6: Heterocyclic Fused (5) ───────────────────────────
    TestMolecule(
        "Acridine",
        "c1ccc2nc3ccccc3cc2c1",
        "heterocyclic_fused",
        notes="Tricyclic aromatic; DNA intercalator scaffold"
    ),
    TestMolecule(
        "Phenothiazine",
        "c1ccc2c(c1)Sc1ccccc1N2",
        "heterocyclic_fused",
        notes="Tricyclic with S and N; antipsychotic scaffold (chlorpromazine core)"
    ),
    TestMolecule(
        "Benzimidazole-fused pyridine (1H-imidazo[4,5-b]pyridine)",
        "c1cc2[nH]cnc2nc1",
        "heterocyclic_fused",
        notes="Fused bicyclic with bridgehead N; purine-like"
    ),
    TestMolecule(
        "Pteridine",
        "c1cnc2nccnc2n1",
        "heterocyclic_fused",
        notes="Bicyclic diazine fusion; folate/flavin core; 4 ring nitrogens"
    ),
    TestMolecule(
        "Free-base porphyrin",
        "c1cc2cc3ccc([nH]3)cc3ccc([nH]3)cc3ccc(n3)cc3ccc1n3",
        "heterocyclic_fused",
        notes="18-pi aromatic macrocycle; 4 pyrrole rings",
        expected_3d=False,
        known_issues="Large macrocycle; 3D embedding may fail or produce poor geometry"
    ),

    # ── Category 7: Natural Products (5) ─────────────────────────────
    TestMolecule(
        "Camphor",
        "CC1(C)C2CCC1(C)C(=O)C2",
        "natural_product",
        notes="Bicyclic monoterpene ketone; strong C=O stretch ~1745 cm-1 (strained)"
    ),
    TestMolecule(
        "(-)-Menthol",
        "C[C@@H]1CC[C@H]([C@@H](C1)O)C(C)C",
        "natural_product",
        notes="Monoterpenoid; 3 stereocenters; cooling agent"
    ),
    TestMolecule(
        "(R)-Limonene",
        "C=C(C)[C@@H]1CC=C(C)CC1",
        "natural_product",
        notes="Monocyclic terpene; citrus aroma; R-enantiomer is orange scent"
    ),
    TestMolecule(
        "Artemisinin core",
        "CC1CCC2C(C)C(OO3)OC3(O2)C1CC(C)=O",
        "natural_product",
        notes="Endoperoxide bridge (O-O); antimalarial; 2015 Nobel Prize",
        known_issues="Peroxide bond unusual; may affect IR predictions"
    ),
    TestMolecule(
        "Quinine",
        "COC1=CC2=C(C=CN=C2C=C1)[C@@H](O)[C@H]1CC2CCN1CC2C=C",
        "natural_product",
        notes="Cinchona alkaloid; antimalarial; quinoline + quinuclidine bicyclic"
    ),

    # ── Category 8: INTENTIONALLY WRONG (5) ──────────────────────────
    # These SHOULD be caught by a good audit system.
    TestMolecule(
        "WRONG: Pentavalent carbon",
        "C(C)(C)(C)(C)C",
        "intentionally_wrong",
        notes="Carbon with 5 bonds = impossible. MUST be rejected.",
        expected_parse=False,
        expected_3d=False,
        known_issues="If RDKit accepts this, it is a CRITICAL validation failure"
    ),
    TestMolecule(
        "WRONG: Cyclopropyne (impossible ring strain)",
        "C1#CC1",
        "intentionally_wrong",
        notes="Triple bond in 3-membered ring = impossible angle strain",
        expected_parse=True,  # RDKit may parse it despite being chemically absurd
        known_issues="RDKit may accept this; a GOOD audit catches that it is chemically impossible"
    ),
    TestMolecule(
        "WRONG: Anti-aromatic cyclobutadiene (forced)",
        "C1=CC=C1",
        "intentionally_wrong",
        notes="4pi anti-aromatic; extremely unstable; should be flagged",
        expected_parse=True,  # RDKit will parse it
        known_issues="Parses fine but is anti-aromatic and chemically unstable; good audit flags it"
    ),
    TestMolecule(
        "WRONG: Nitrogen with impossible charge state",
        "[N+5](=O)(=O)(=O)(=O)=O",
        "intentionally_wrong",
        notes="N with +5 formal charge and 5 double bonds to O = absurd",
        expected_parse=False,
        expected_3d=False,
        known_issues="Chemically impossible; must be rejected"
    ),
    TestMolecule(
        "WRONG: Disconnected aspirin (meant to be bonded)",
        "CC(=O)O.c1ccccc1C(=O)O",
        "intentionally_wrong",
        notes="Acetic acid + benzoic acid as separate fragments instead of aspirin ester",
        expected_parse=True,
        known_issues="Parses as 2 valid fragments; audit should catch it is NOT aspirin but disconnected pieces"
    ),

    # ── Category 9: Edge Cases (5) ───────────────────────────────────
    TestMolecule(
        "Triacontane (C30 linear alkane)",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "edge_case",
        notes="C30H62; very long chain; tests performance with large molecules"
    ),
    TestMolecule(
        "Buckminsterfullerene C60",
        "c12c3c4c5c1c1c6c7c8c2c2c9c%10c3c3c%11c4c4c%12c%13c5c5c1c1c6c6c%14c7c7c%15c8c2c2c9c8c9c%10c3c3c%11c%10c4c4c%12c%11c%12c%13c5c5c1c1c6c%14c6c7c%15c2c2c8c7c9c3c%10c3c4c%11c%12c5c1c6c2c7c3",
        "edge_case",
        notes="60-carbon fullerene; icosahedral symmetry; all sp2",
        expected_3d=False,
        known_issues="Extremely complex topology; 3D embedding almost always fails"
    ),
    TestMolecule(
        "1,2-Propadiene (allene)",
        "C=C=C",
        "edge_case",
        notes="Cumulated diene; orthogonal pi systems; sp-hybridized central C"
    ),
    TestMolecule(
        "1,2,3-Butatriene (cumulene)",
        "C=C=C=C",
        "edge_case",
        notes="Three cumulated double bonds; extended cumulene"
    ),
    TestMolecule(
        "1,3,5,7-Octatetrayne (polyyne)",
        "C#CC#CC#CC#C",
        "edge_case",
        notes="Four conjugated triple bonds; linear carbon chain; sp hybridized"
    ),
]

assert len(MOLECULES) == 50, f"Expected 50 molecules, got {len(MOLECULES)}"

# ============================================================================
# TEST RUNNER
# ============================================================================

@dataclass
class TestResult:
    molecule_name: str
    category: str
    smiles: str
    # Test results: None = not run, True = pass, False = fail
    parse_ok: Optional[bool] = None
    parse_detail: str = ""
    ir_ok: Optional[bool] = None
    ir_detail: str = ""
    ir_peak_count: int = 0
    coord3d_ok: Optional[bool] = None
    coord3d_detail: str = ""
    lead_ok: Optional[bool] = None
    lead_detail: str = ""
    lead_variant_count: int = 0
    admet_ok: Optional[bool] = None
    admet_detail: str = ""
    # Silent failure detection
    silent_failures: List[str] = field(default_factory=list)
    # Expected vs actual
    expected_parse: bool = True
    expected_3d: bool = True
    notes: str = ""
    known_issues: str = ""


def run_single_test(mol_def: TestMolecule) -> TestResult:
    """Run all 5 tests on a single molecule."""
    result = TestResult(
        molecule_name=mol_def.name,
        category=mol_def.category,
        smiles=mol_def.smiles,
        expected_parse=mol_def.expected_parse,
        expected_3d=mol_def.expected_3d,
        notes=mol_def.notes,
        known_issues=mol_def.known_issues,
    )

    # ── Test A: SMILES Parsing ──
    rdkit_mol = None
    try:
        rdkit_mol = Chem.MolFromSmiles(mol_def.smiles)
        if rdkit_mol is not None:
            result.parse_ok = True
            n_atoms = rdkit_mol.GetNumAtoms()
            n_bonds = rdkit_mol.GetNumBonds()
            try:
                formula = Descriptors.MolFormula(rdkit_mol)
            except Exception:
                formula = "?"
            result.parse_detail = f"atoms={n_atoms}, bonds={n_bonds}, formula={formula}"

            # Silent failure check: parsed but shouldn't have
            if not mol_def.expected_parse:
                result.silent_failures.append(
                    f"SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! "
                    f"({mol_def.notes})"
                )
        else:
            result.parse_ok = False
            result.parse_detail = "MolFromSmiles returned None"
            if mol_def.expected_parse:
                result.parse_detail += " (UNEXPECTED: should have parsed)"
    except Exception as e:
        result.parse_ok = False
        result.parse_detail = f"Exception: {e}"

    # ── Test B: IR Spectrum Generation ──
    try:
        ir_peaks = predict_ir(mol_def.smiles)
        if ir_peaks and len(ir_peaks) > 0:
            result.ir_ok = True
            result.ir_peak_count = len(ir_peaks)
            peak_summary = ", ".join(
                f"{p.wavenumber:.0f}cm-1({p.assignment})"
                for p in ir_peaks[:5]
            )
            result.ir_detail = f"{len(ir_peaks)} peaks: {peak_summary}"

            # Silent failure checks for IR
            if rdkit_mol is not None:
                # Check: molecule has C=O but no ~1700 peak?
                co_pat = Chem.MolFromSmarts("[CX3]=[OX1]")
                if co_pat and rdkit_mol.HasSubstructMatch(co_pat):
                    has_co_peak = any(1650 <= p.wavenumber <= 1800 for p in ir_peaks)
                    if not has_co_peak:
                        result.silent_failures.append(
                            "SILENT FAIL: Molecule has C=O but no IR peak in 1650-1800 cm-1 range"
                        )

                # Check: molecule has O-H but no ~3200-3600 peak?
                oh_pat = Chem.MolFromSmarts("[OX2H]")
                if oh_pat and rdkit_mol.HasSubstructMatch(oh_pat):
                    has_oh_peak = any(3000 <= p.wavenumber <= 3700 for p in ir_peaks)
                    if not has_oh_peak:
                        result.silent_failures.append(
                            "SILENT FAIL: Molecule has O-H but no IR peak in 3000-3700 cm-1 range"
                        )

                # Check: molecule has N-H but no ~3300-3500 peak?
                nh_pat = Chem.MolFromSmarts("[NH]")
                if nh_pat and rdkit_mol.HasSubstructMatch(nh_pat):
                    has_nh_peak = any(3200 <= p.wavenumber <= 3500 for p in ir_peaks)
                    if not has_nh_peak:
                        result.silent_failures.append(
                            "SILENT FAIL: Molecule has N-H but no IR peak in 3200-3500 cm-1 range"
                        )
        else:
            result.ir_ok = False
            result.ir_detail = "No IR peaks returned"
            if result.parse_ok:
                result.silent_failures.append(
                    "SILENT FAIL: SMILES parsed OK but IR returned 0 peaks"
                )
    except Exception as e:
        result.ir_ok = False
        result.ir_detail = f"Exception: {e}"

    # ── Test C: 3D Coordinate Generation ──
    if rdkit_mol is not None:
        try:
            mol_3d = Chem.AddHs(rdkit_mol)
            embed_result = AllChem.EmbedMolecule(mol_3d, AllChem.ETKDG())
            if embed_result == 0:
                # Try force field optimization
                try:
                    opt_result = AllChem.MMFFOptimizeMolecule(mol_3d, maxIters=200)
                    if opt_result == 0:
                        result.coord3d_ok = True
                        result.coord3d_detail = "Embedded + MMFF optimized"
                    elif opt_result == 1:
                        result.coord3d_ok = True
                        result.coord3d_detail = "Embedded + MMFF converged with issues"
                    else:
                        # Try UFF fallback
                        try:
                            AllChem.UFFOptimizeMolecule(mol_3d, maxIters=200)
                            result.coord3d_ok = True
                            result.coord3d_detail = "Embedded + UFF optimized (MMFF failed)"
                        except Exception:
                            result.coord3d_ok = True
                            result.coord3d_detail = "Embedded but optimization failed"
                except Exception:
                    result.coord3d_ok = True
                    result.coord3d_detail = "Embedded, optimization skipped"

                if not mol_def.expected_3d and result.coord3d_ok:
                    # Not necessarily a silent fail, just unexpected success
                    pass
            else:
                result.coord3d_ok = False
                result.coord3d_detail = f"EmbedMolecule returned {embed_result}"
                if mol_def.expected_3d:
                    result.coord3d_detail += " (UNEXPECTED: should have embedded)"
        except Exception as e:
            result.coord3d_ok = False
            result.coord3d_detail = f"Exception: {str(e)[:100]}"
    else:
        result.coord3d_ok = False
        result.coord3d_detail = "Skipped (SMILES parse failed)"

    # ── Test D: Lead Optimizer Variant Generation ──
    if rdkit_mol is not None:
        try:
            gen = MoleculeVariantGenerator()
            variants = gen.generate_r_group_variants(
                rdkit_mol,
                preferred=["F", "Cl", "O", "N"],
                max_count=5
            )
            if variants and len(variants) > 0:
                result.lead_ok = True
                result.lead_variant_count = len(variants)
                result.lead_detail = f"{len(variants)} variants generated"

                # Silent failure: check if variants actually differ from parent
                parent_smi = Chem.MolToSmiles(rdkit_mol)
                identical_count = sum(
                    1 for v in variants if v.smiles == parent_smi
                )
                if identical_count > 0:
                    result.silent_failures.append(
                        f"SILENT FAIL: {identical_count}/{len(variants)} variants identical to parent"
                    )

                # Silent failure: check if variants parse back
                invalid_variants = 0
                for v in variants:
                    check = Chem.MolFromSmiles(v.smiles)
                    if check is None:
                        invalid_variants += 1
                if invalid_variants > 0:
                    result.silent_failures.append(
                        f"SILENT FAIL: {invalid_variants}/{len(variants)} generated variants have invalid SMILES"
                    )
            else:
                result.lead_ok = False
                result.lead_detail = "0 variants generated"
                if result.parse_ok and rdkit_mol.GetNumAtoms() > 3:
                    result.lead_detail += " (molecule has atoms but no variants)"
        except Exception as e:
            result.lead_ok = False
            result.lead_detail = f"Exception: {str(e)[:120]}"
    else:
        result.lead_ok = False
        result.lead_detail = "Skipped (SMILES parse failed)"

    # ── Test E: ADMET Prediction ──
    try:
        admet = predict_admet(mol_def.smiles, mol_name=mol_def.name)
        if admet.error:
            result.admet_ok = False
            result.admet_detail = f"Error: {admet.error}"
        else:
            result.admet_ok = True
            lip = admet.lipinski
            detail_parts = []
            if lip:
                detail_parts.append(
                    f"Lipinski: MW={lip.mw:.0f} LogP={lip.logp:.1f} "
                    f"HBD={lip.hbd} HBA={lip.hba} violations={lip.violations}"
                )
            if admet.bbb:
                detail_parts.append(f"BBB={admet.bbb.classification}")
            if admet.metabolic_stability:
                detail_parts.append(f"MetStab={admet.metabolic_stability.classification}")
            result.admet_detail = "; ".join(detail_parts)

            # Silent failure: metal complex getting normal ADMET
            if mol_def.category == "metal_complex":
                result.silent_failures.append(
                    "SILENT FAIL: Metal complex received normal ADMET profile "
                    "(ADMET is meaningless for organometallics)"
                )

            # Silent failure: reactive intermediate getting drug-like score
            if mol_def.category == "reactive_intermediate":
                if lip and lip.passes:
                    result.silent_failures.append(
                        "SILENT FAIL: Reactive intermediate passed Lipinski "
                        "(reactive species are not viable drugs)"
                    )

            # Silent failure: intentionally wrong molecule getting ADMET
            if mol_def.category == "intentionally_wrong":
                result.silent_failures.append(
                    "SILENT FAIL: Intentionally wrong molecule received ADMET "
                    "profile without error"
                )

    except Exception as e:
        result.admet_ok = False
        result.admet_detail = f"Exception: {str(e)[:120]}"

    return result


def run_all_tests() -> List[TestResult]:
    """Run vaccine circulation test on all 50 molecules."""
    results = []
    print(f"\n{'='*80}")
    print(f" VACCINE CIRCULATION TEST (백신 공회전)")
    print(f" {len(MOLECULES)} complex molecules x 5 test types")
    print(f" Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    for i, mol_def in enumerate(MOLECULES, 1):
        print(f"[{i:2d}/50] Testing: {mol_def.name} ({mol_def.category})")
        t0 = time.time()
        result = run_single_test(mol_def)
        elapsed = time.time() - t0

        # Status summary
        statuses = []
        for label, ok in [("Parse", result.parse_ok), ("IR", result.ir_ok),
                          ("3D", result.coord3d_ok), ("Lead", result.lead_ok),
                          ("ADMET", result.admet_ok)]:
            if ok is True:
                statuses.append(f"{label}:OK")
            elif ok is False:
                statuses.append(f"{label}:FAIL")
            else:
                statuses.append(f"{label}:SKIP")

        sf_count = len(result.silent_failures)
        sf_flag = f" *** {sf_count} SILENT FAILURE(S) ***" if sf_count > 0 else ""
        print(f"        {' | '.join(statuses)} [{elapsed:.2f}s]{sf_flag}")

        if result.silent_failures:
            for sf in result.silent_failures:
                print(f"        >> {sf}")

        results.append(result)

    return results


def generate_report(results: List[TestResult]) -> str:
    """Generate markdown report."""
    lines = []
    lines.append("# Vaccine Circulation Test Results (백신 공회전 결과)")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total molecules tested:** {len(results)}")
    lines.append("")

    # Overall statistics
    total_tests = len(results) * 5
    pass_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.coord3d_ok, r.lead_ok, r.admet_ok]
        if ok is True
    )
    fail_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.coord3d_ok, r.lead_ok, r.admet_ok]
        if ok is False
    )
    skip_count = total_tests - pass_count - fail_count
    silent_total = sum(len(r.silent_failures) for r in results)

    lines.append("## Summary")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total individual tests | {total_tests} |")
    lines.append(f"| PASS | {pass_count} |")
    lines.append(f"| FAIL (explicit) | {fail_count} |")
    lines.append(f"| SKIP | {skip_count} |")
    lines.append(f"| **SILENT FAILURES** | **{silent_total}** |")
    lines.append("")

    # Per-test-type statistics
    lines.append("## Pass Rate by Test Type")
    lines.append("| Test | Pass | Fail | Skip | Rate |")
    lines.append("|------|------|------|------|------|")
    for test_name, accessor in [
        ("SMILES Parse", lambda r: r.parse_ok),
        ("IR Spectrum", lambda r: r.ir_ok),
        ("3D Coords", lambda r: r.coord3d_ok),
        ("Lead Variants", lambda r: r.lead_ok),
        ("ADMET", lambda r: r.admet_ok),
    ]:
        p = sum(1 for r in results if accessor(r) is True)
        f = sum(1 for r in results if accessor(r) is False)
        s = len(results) - p - f
        rate = f"{p/(p+f)*100:.0f}%" if (p+f) > 0 else "N/A"
        lines.append(f"| {test_name} | {p} | {f} | {s} | {rate} |")
    lines.append("")

    # Per-category statistics
    lines.append("## Pass Rate by Category")
    categories = {}
    for r in results:
        if r.category not in categories:
            categories[r.category] = {"pass": 0, "fail": 0, "silent": 0, "total": 0}
        cat = categories[r.category]
        for ok in [r.parse_ok, r.ir_ok, r.coord3d_ok, r.lead_ok, r.admet_ok]:
            cat["total"] += 1
            if ok is True:
                cat["pass"] += 1
            elif ok is False:
                cat["fail"] += 1
        cat["silent"] += len(r.silent_failures)

    lines.append("| Category | Tests | Pass | Fail | Silent Fails |")
    lines.append("|----------|-------|------|------|-------------|")
    for cat_name in [
        "bridged_cage", "metal_complex", "large_drug", "stereochemistry",
        "reactive_intermediate", "heterocyclic_fused", "natural_product",
        "intentionally_wrong", "edge_case"
    ]:
        if cat_name in categories:
            c = categories[cat_name]
            lines.append(
                f"| {cat_name} | {c['total']} | {c['pass']} | {c['fail']} | {c['silent']} |"
            )
    lines.append("")

    # ── CRITICAL: Silent Failures Detail ──
    lines.append("## SILENT FAILURES (Critical for Audit Teams)")
    lines.append("")
    lines.append("> These are cases where the system produced a result WITHOUT an error,")
    lines.append("> but the result is chemically wrong, meaningless, or misleading.")
    lines.append("> A good audit team MUST catch these.")
    lines.append("")

    sf_molecules = [r for r in results if r.silent_failures]
    if sf_molecules:
        for r in sf_molecules:
            lines.append(f"### {r.molecule_name} ({r.category})")
            lines.append(f"- **SMILES:** `{r.smiles}`")
            lines.append(f"- **Notes:** {r.notes}")
            for sf in r.silent_failures:
                lines.append(f"- {sf}")
            lines.append("")
    else:
        lines.append("*No silent failures detected.*")
        lines.append("")

    # ── Detailed Results Table ──
    lines.append("## Detailed Results (All 50 Molecules)")
    lines.append("")

    for cat_name, cat_label in [
        ("bridged_cage", "Bridged/Cage Structures"),
        ("metal_complex", "Metal Complexes"),
        ("large_drug", "Large Drugs"),
        ("stereochemistry", "Stereochemistry Challenges"),
        ("reactive_intermediate", "Reactive Intermediates"),
        ("heterocyclic_fused", "Heterocyclic Fused"),
        ("natural_product", "Natural Products"),
        ("intentionally_wrong", "Intentionally Wrong"),
        ("edge_case", "Edge Cases"),
    ]:
        cat_results = [r for r in results if r.category == cat_name]
        if not cat_results:
            continue

        lines.append(f"### {cat_label}")
        lines.append("")

        for r in cat_results:
            emoji_parse = "PASS" if r.parse_ok else ("FAIL" if r.parse_ok is False else "SKIP")
            emoji_ir = "PASS" if r.ir_ok else ("FAIL" if r.ir_ok is False else "SKIP")
            emoji_3d = "PASS" if r.coord3d_ok else ("FAIL" if r.coord3d_ok is False else "SKIP")
            emoji_lead = "PASS" if r.lead_ok else ("FAIL" if r.lead_ok is False else "SKIP")
            emoji_admet = "PASS" if r.admet_ok else ("FAIL" if r.admet_ok is False else "SKIP")

            lines.append(f"**{r.molecule_name}**")
            lines.append(f"- SMILES: `{r.smiles}`")
            lines.append(f"- Parse: [{emoji_parse}] {r.parse_detail}")
            lines.append(f"- IR: [{emoji_ir}] {r.ir_detail}")
            lines.append(f"- 3D: [{emoji_3d}] {r.coord3d_detail}")
            lines.append(f"- Lead: [{emoji_lead}] {r.lead_detail}")
            lines.append(f"- ADMET: [{emoji_admet}] {r.admet_detail}")
            if r.silent_failures:
                lines.append(f"- **SILENT FAILURES ({len(r.silent_failures)}):**")
                for sf in r.silent_failures:
                    lines.append(f"  - {sf}")
            if r.known_issues:
                lines.append(f"- Known issues: {r.known_issues}")
            lines.append("")

    # ── Audit Team Scoring Guide ──
    lines.append("## Audit Team Scoring Guide")
    lines.append("")
    lines.append("A good audit team should catch the following:")
    lines.append("1. **Intentionally wrong molecules that silently pass** - If the system accepts pentavalent carbon or cyclopropyne without complaint, the validation is broken.")
    lines.append("2. **Metal complexes getting meaningful ADMET scores** - ADMET models are trained on organic drug molecules; applying them to ferrocene or cisplatin is scientifically meaningless.")
    lines.append("3. **Reactive intermediates passing Lipinski** - Carbocations and radicals are not viable drug candidates.")
    lines.append("4. **Missing IR peaks for obvious functional groups** - If a ketone has no C=O stretch, the spectrum predictor has a bug.")
    lines.append("5. **Generated variants identical to parent** - Lead optimizer producing duplicates is wasteful at best, misleading at worst.")
    lines.append("6. **Disconnected fragments treated as valid molecules** - The 'wrong aspirin' test checks if the system distinguishes bonded vs disconnected structures.")
    lines.append("")
    lines.append(f"**Total silent failures found: {silent_total}**")
    lines.append("")
    if silent_total > 10:
        lines.append("**VERDICT: HIGH number of silent failures. Audit teams have SIGNIFICANT work to do.**")
    elif silent_total > 5:
        lines.append("**VERDICT: MODERATE number of silent failures. Audit teams should investigate each one.**")
    else:
        lines.append("**VERDICT: LOW number of silent failures. System is relatively robust.**")

    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("Starting Vaccine Circulation Test...")
    results = run_all_tests()

    print(f"\n{'='*80}")
    print(f" GENERATING REPORT")
    print(f"{'='*80}\n")

    report = generate_report(results)

    output_path = Path(__file__).resolve().parent / "vaccine_circulation_results.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Report written to: {output_path}")

    # Print summary
    silent_total = sum(len(r.silent_failures) for r in results)
    print(f"\n{'='*80}")
    print(f" FINAL SUMMARY")
    print(f"{'='*80}")
    print(f" Total molecules: {len(results)}")
    print(f" Silent failures: {silent_total}")

    pass_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.coord3d_ok, r.lead_ok, r.admet_ok]
        if ok is True
    )
    fail_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.coord3d_ok, r.lead_ok, r.admet_ok]
        if ok is False
    )
    total = pass_count + fail_count
    print(f" Pass: {pass_count}/{total} ({pass_count/total*100:.0f}%)" if total > 0 else " No tests ran")
    print(f" Fail: {fail_count}/{total} ({fail_count/total*100:.0f}%)" if total > 0 else "")
    print(f"{'='*80}")
