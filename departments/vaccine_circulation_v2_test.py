#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vaccine Circulation v2: Inorganic/Coordination Compound Stress Test
====================================================================
50 molecules across 6 categories:
  1. Coordination compounds (15)
  2. Organometallics (10)
  3. Inorganic (10)
  4. Impossible/wrong structures (5)
  5. Reactive species (5)
  6. Edge cases (5)

Tests per molecule:
  A. SMILES parsing (RDKit Chem.MolFromSmiles)
  B. IR spectrum generation (predict_spectra.predict_ir)
  C. ADMET prediction (admet_predictor.predict_admet)
     - Should WARN or REJECT for non-organic/non-drug-like
  D. 3D coordinate generation (AllChem.EmbedMolecule)
  E. Non-drug-like detection (system should identify these)
"""

import sys
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

# Add src/app to path
APP_DIR = Path(__file__).resolve().parent.parent / "src" / "app"
sys.path.insert(0, str(APP_DIR))

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

from predict_spectra import predict_ir
from admet_predictor import predict_admet

# ============================================================================
# MOLECULE DEFINITIONS (50 total)
# ============================================================================

@dataclass
class TestMolecule:
    name: str
    smiles: str
    category: str
    notes: str = ""
    expected_parse: bool = True
    expected_3d: bool = True
    is_drug_like: bool = False  # Should ADMET flag this as non-drug-like?
    has_metal: bool = False
    known_issues: str = ""


MOLECULES: List[TestMolecule] = [
    # ── Category 1: Coordination Compounds (15) ──────────────────────
    TestMolecule(
        "[Co(NH3)6]3+", "[Co+3]([NH3])([NH3])([NH3])([NH3])([NH3])[NH3]",
        "coordination", has_metal=True,
        notes="Octahedral Co(III) hexaammine, classic Werner complex",
        known_issues="RDKit may reject high-valence metal; ADMET meaningless"
    ),
    TestMolecule(
        "[Fe(CN)6]4-", "[Fe-4]([C-]#N)([C-]#N)([C-]#N)([C-]#N)([C-]#N)[C-]#N",
        "coordination", has_metal=True,
        notes="Ferrocyanide, low-spin d6 octahedral",
        expected_parse=False,
        known_issues="Complex charge states; RDKit likely rejects"
    ),
    TestMolecule(
        "[Ni(CO)4]", "[Ni](=C=O)(=C=O)(=C=O)=C=O",
        "coordination", has_metal=True,
        notes="Tetrahedral Ni(0) carbonyl, extremely toxic",
        known_issues="Ni-CO bonding not representable in valence SMILES"
    ),
    TestMolecule(
        "[Cr(H2O)6]3+", "[Cr+3]([OH2])([OH2])([OH2])([OH2])([OH2])[OH2]",
        "coordination", has_metal=True,
        notes="Hexaaquachromium(III), violet octahedral complex",
        known_issues="High-valence metal; ADMET meaningless"
    ),
    TestMolecule(
        "[Cu(NH3)4]2+", "[Cu+2]([NH3])([NH3])([NH3])[NH3]",
        "coordination", has_metal=True,
        notes="Tetraamminecopper(II), deep blue square planar",
        known_issues="Square planar vs tetrahedral ambiguity"
    ),
    TestMolecule(
        "trans-[PtCl2(NH3)2] (transplatin)", "[NH3][Pt](Cl)(Cl)[NH3]",
        "coordination", has_metal=True,
        notes="Trans isomer of cisplatin - inactive against cancer",
        known_issues="Cis/trans distinction critical; SMILES doesn't encode geometry"
    ),
    TestMolecule(
        "[Fe(oxalate)3]3-", "[Fe+3]([O-]C(=O)C(=O)[O-])([O-]C(=O)C(=O)[O-])[O-]C(=O)C(=O)[O-]",
        "coordination", has_metal=True,
        notes="Tris(oxalato)ferrate(III), chiral D3 symmetry",
        known_issues="Complex multidentate ligand encoding"
    ),
    TestMolecule(
        "[Mn(acac)3]", "[Mn+3]",
        "coordination", has_metal=True,
        notes="Tris(acetylacetonato)manganese(III); simplified as bare ion",
        expected_3d=False,
        known_issues="Bare metal ion, no organic ligands in SMILES"
    ),
    TestMolecule(
        "[Ru(bpy)3]2+", "[Ru+2].c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1",
        "coordination", has_metal=True,
        notes="Ruthenium tris-bipyridyl, photochemistry workhorse",
        known_issues="Disconnected fragments; ADMET meaningless for coordination compound"
    ),
    TestMolecule(
        "[Ir(ppy)3]", "[Ir+3].c1ccc(-c2ccccn2)cc1.c1ccc(-c2ccccn2)cc1.c1ccc(-c2ccccn2)cc1",
        "coordination", has_metal=True,
        notes="Fac-tris(2-phenylpyridine)iridium(III), OLED emitter",
        known_issues="Disconnected fragments; cyclometalated not encoded"
    ),
    TestMolecule(
        "Heme (Fe-protoporphyrin IX simplified)",
        "[Fe+2]1([NH3])([NH3])N2C(=CC3=CC4=CC(=CC5=CC(=CC1=C2C=C3)N5)N4)",
        "coordination", has_metal=True,
        notes="Simplified porphyrin core with Fe",
        expected_parse=False,
        known_issues="Porphyrin macrocycle encoding very difficult in SMILES"
    ),
    TestMolecule(
        "Chlorophyll core (Mg-porphyrin simplified)",
        "[Mg+2]1(N2=CC=CC2=CC2=CC(=CC3=CC(=CC1)N3)N2)",
        "coordination", has_metal=True,
        notes="Simplified Mg-porphyrin chlorophyll core",
        expected_parse=False,
        known_issues="Macrocyclic metal complex; SMILES likely invalid"
    ),
    TestMolecule(
        "Vitamin B12 core (Co-corrin simplified)",
        "[Co+3]",
        "coordination", has_metal=True,
        notes="Just Co3+ ion; actual B12 far too complex for SMILES",
        expected_3d=False,
        known_issues="Single atom; no meaningful chemistry tests possible"
    ),
    TestMolecule(
        "Cisplatin", "[NH3][Pt]([NH3])(Cl)Cl",
        "coordination", has_metal=True,
        notes="cis-diamminedichloroplatinum(II), anticancer drug",
        known_issues="Square planar Pt(II); ADMET trained on organic drugs only"
    ),
    TestMolecule(
        "Ferrocene", "[Fe+2].[cH-]1cccc1.[cH-]1cccc1",
        "coordination", has_metal=True,
        notes="Bis(cyclopentadienyl)iron(II), sandwich complex",
        known_issues="Eta-5 bonding not representable; ADMET meaningless"
    ),

    # ── Category 2: Organometallics (10) ──────────────────────────────
    TestMolecule(
        "Grignard reagent (CH3MgBr)", "[CH3][Mg]Br",
        "organometallic", has_metal=True,
        notes="Methylmagnesium bromide, key synthetic reagent",
        known_issues="Ionic/covalent hybrid; exists as equilibrium mixture in solution"
    ),
    TestMolecule(
        "n-Butyllithium", "[CH2][CH2][CH2][CH3].[Li]",
        "organometallic", has_metal=True,
        notes="Strong base/nucleophile; actually aggregated in solution",
        known_issues="True structure is hexameric/tetrameric cluster, not monomeric"
    ),
    TestMolecule(
        "Gilman reagent (dimethylcuprate)", "[CH3][Cu][CH3]",
        "organometallic", has_metal=True,
        notes="Lithium dimethylcuprate (simplified, no Li counter-ion)",
        known_issues="Cu-C bonding unusual for RDKit"
    ),
    TestMolecule(
        "Zeise's salt anion", "[Pt-](Cl)(Cl)(Cl)(C=C)",
        "organometallic", has_metal=True,
        notes="First organometallic compound (1827); ethylene-Pt complex",
        expected_parse=False,
        known_issues="Pi-bonded ethylene to Pt not encodable in standard SMILES"
    ),
    TestMolecule(
        "Titanocene dichloride", "[Ti](Cl)(Cl).[cH-]1cccc1.[cH-]1cccc1",
        "organometallic", has_metal=True,
        notes="Cp2TiCl2, metallocene with anticancer activity",
        known_issues="Eta-5 Cp bonding not representable"
    ),
    TestMolecule(
        "Wilkinson's catalyst simplified", "[Rh](Cl)([PH3])([PH3])[PH3]",
        "organometallic", has_metal=True,
        notes="RhCl(PPh3)3 simplified with PH3 instead of PPh3",
        known_issues="Simplified ligands; real catalyst has bulky PPh3"
    ),
    TestMolecule(
        "Grubbs catalyst core (simplified)", "[Ru](Cl)(Cl)(=C)([PH3])",
        "organometallic", has_metal=True,
        notes="Simplified 1st gen Grubbs carbene catalyst",
        known_issues="Ru=C carbene bond atypical; may not parse"
    ),
    TestMolecule(
        "Pd(PPh3)4 simplified", "[Pd]([PH3])([PH3])([PH3])[PH3]",
        "organometallic", has_metal=True,
        notes="Tetrakis(triphenylphosphine)palladium(0) simplified",
        known_issues="Pd(0) with 4 ligands; 18-electron complex"
    ),
    TestMolecule(
        "NiCl2(dppe) simplified", "[Ni](Cl)(Cl)([PH3])[PH3]",
        "organometallic", has_metal=True,
        notes="NiCl2 with bidentate phosphine (simplified)",
        known_issues="Square planar Ni(II) phosphine complex"
    ),
    TestMolecule(
        "Zirconocene dichloride", "[Zr](Cl)(Cl).[cH-]1cccc1.[cH-]1cccc1",
        "organometallic", has_metal=True,
        notes="Cp2ZrCl2, olefin polymerization catalyst",
        known_issues="Eta-5 Cp bonding not representable"
    ),

    # ── Category 3: Inorganic (10) ────────────────────────────────────
    TestMolecule(
        "Sulfur hexafluoride (SF6)", "FS(F)(F)(F)(F)F",
        "inorganic",
        notes="Octahedral hypervalent sulfur, extremely stable",
        known_issues="Hypervalent S; RDKit handling of expanded octets"
    ),
    TestMolecule(
        "Xenon tetrafluoride (XeF4)", "F[Xe](F)(F)F",
        "inorganic",
        notes="Square planar noble gas compound, d2sp3 hybridized",
        known_issues="Noble gas compound; extreme chemistry"
    ),
    TestMolecule(
        "Phosphorus pentachloride (PCl5)", "ClP(Cl)(Cl)(Cl)Cl",
        "inorganic",
        notes="Trigonal bipyramidal, hypervalent phosphorus",
        known_issues="Hypervalent P; expanded octet"
    ),
    TestMolecule(
        "Iodine heptafluoride (IF7)", "FI(F)(F)(F)(F)(F)F",
        "inorganic",
        notes="Pentagonal bipyramidal, highest coordination for main group",
        expected_parse=False,
        known_issues="I with 7 bonds; extreme hypervalence"
    ),
    TestMolecule(
        "Bromine trifluoride (BrF3)", "FBr(F)F",
        "inorganic",
        notes="T-shaped, powerful fluorinating agent",
        known_issues="Hypervalent Br; toxic and extremely reactive"
    ),
    TestMolecule(
        "Diborane (B2H6)", "[BH2]([H])[BH2]",
        "inorganic",
        notes="3-center-2-electron bonds; banana bonds",
        known_issues="Non-classical bonding; SMILES cannot represent 3c2e bonds"
    ),
    TestMolecule(
        "Aluminum chloride dimer (Al2Cl6)", "Cl[Al](Cl)(Cl)[Al](Cl)(Cl)Cl",
        "inorganic",
        notes="Bridged dimer with 2 Cl bridges",
        known_issues="Al-Cl-Al bridging; Lewis acid"
    ),
    TestMolecule(
        "Phosphorus pentoxide unit (P4O10 fragment)", "O=P(O)(O)OP(=O)(O)O",
        "inorganic",
        notes="Diphosphoric acid fragment of P4O10 cage",
        known_issues="Highly polar inorganic; no drug relevance"
    ),
    TestMolecule(
        "Silicon dioxide unit (SiO2)", "O=[Si]=O",
        "inorganic",
        notes="Linear representation; real SiO2 is network solid",
        known_issues="Network solid cannot be represented by single SMILES"
    ),
    TestMolecule(
        "Sodium nitroprusside (Na2[Fe(CN)5NO])", "[Fe+2]([C-]#N)([C-]#N)([C-]#N)([C-]#N)([C-]#N)[N+]=O",
        "inorganic", has_metal=True,
        notes="Nitroprusside: NO bound to Fe, vasodilator",
        known_issues="Complex charge states and unusual NO+ ligand"
    ),

    # ── Category 4: Impossible/Wrong Structures (5) ───────────────────
    TestMolecule(
        "Pentavalent carbon", "C(C)(C)(C)(C)C",
        "impossible",
        notes="Carbon with 5 bonds = IMPOSSIBLE",
        expected_parse=False,
        expected_3d=False,
        known_issues="MUST be rejected; any system accepting this is fundamentally broken"
    ),
    TestMolecule(
        "Heptavalent nitrogen", "[N](=O)(=O)(=O)(O)(O)O",
        "impossible",
        notes="Nitrogen with 7 bonds = IMPOSSIBLE",
        expected_parse=False,
        expected_3d=False,
        known_issues="Max N valence is 5 (already unusual); 7 is chemically impossible"
    ),
    TestMolecule(
        "Square planar carbon (forced)", "C1=CC=C1",
        "impossible",
        notes="Cyclobutadiene: 4pi antiaromatic, extremely unstable",
        expected_parse=True,  # RDKit will parse it
        known_issues="RDKit parses but is antiaromatic; should be flagged as unstable"
    ),
    TestMolecule(
        "Noble gas compound that shouldn't exist (NeF2)", "F[Ne]F",
        "impossible",
        notes="Neon difluoride does NOT exist; Ne has no chemistry",
        expected_parse=False,
        known_issues="Ne has full electron shell; cannot form compounds at all"
    ),
    TestMolecule(
        "Bond between two noble gases (He-Ar)", "[He][Ar]",
        "impossible",
        notes="No covalent bond possible between two noble gases",
        expected_parse=False,
        expected_3d=False,
        known_issues="Completely impossible; atoms with full shells cannot bond"
    ),

    # ── Category 5: Reactive Species (5) ──────────────────────────────
    TestMolecule(
        "Superoxide O2-", "[O-][O]",
        "reactive_species",
        notes="Superoxide radical anion, biological oxidant",
        known_issues="Radical + charged; not a drug; ADMET meaningless"
    ),
    TestMolecule(
        "Ozone (O3)", "[O-][O+]=O",
        "reactive_species",
        notes="Ozone; SMILES uses charge-separated form",
        known_issues="Reactive allotrope; not drug-like"
    ),
    TestMolecule(
        "Nitric oxide radical (NO)", "[N]=O",
        "reactive_species",
        notes="Signaling molecule, radical species",
        known_issues="Radical notation approximate; biological role but not a drug per se"
    ),
    TestMolecule(
        "Methyl radical", "[CH3]",
        "reactive_species",
        notes="Carbon radical; extremely short-lived",
        known_issues="Radical; ADMET/Lipinski completely meaningless"
    ),
    TestMolecule(
        "Phenyl cation", "c1cc[c+]cc1",
        "reactive_species",
        notes="Phenyl cation; extremely unstable antiaromatic species",
        known_issues="Antiaromatic cation; fleeting intermediate"
    ),

    # ── Category 6: Edge Cases (5) ────────────────────────────────────
    TestMolecule(
        "Buckminsterfullerene C60",
        "c12c3c4c5c1c1c6c7c8c2c2c9c%10c3c3c%11c4c4c%12c%13c5c5c1c1c6c6c%14c7c7c%15c8c2c2c9c8c9c%10c3c3c%11c%10c4c4c%12c%11c%12c%13c5c5c1c1c6c%14c6c7c%15c2c2c8c7c9c3c%10c3c4c%11c%12c5c1c6c2c7c3",
        "edge_case",
        expected_parse=False,
        expected_3d=False,
        notes="60-carbon fullerene; icosahedral symmetry",
        known_issues="SMILES encoding of C60 is notoriously unreliable"
    ),
    TestMolecule(
        "Carbon nanotube segment (polyphenylene)",
        "c1cc2cc3cc4cc5cc6cc7cc8cc1cc1cc(cc9cc%10cc%11cc%12cc2cc3cc4c4cc5cc5cc6cc6cc7cc8cc1c1cc9cc9cc%10cc%10cc%11cc%12c4c5c6c1c9%10)c",
        "edge_case",
        expected_parse=False,
        notes="Approximate nanotube segment via fused aromatics",
        known_issues="Extremely complex topology; almost certainly fails SMILES parsing"
    ),
    TestMolecule(
        "Graphene sheet fragment (coronene)",
        "c1cc2ccc3cc4ccc5cc6ccc1c1c2c3c4c5c61",
        "edge_case",
        notes="Coronene (7 fused benzene rings); graphene fragment",
        known_issues="Large fused aromatic system; 3D will be flat"
    ),
    TestMolecule(
        "Diamond lattice unit (adamantane extended)",
        "C1C2CC3CC1CC(C2)C3",
        "edge_case",
        notes="Adamantane as diamond lattice unit cell analog",
        known_issues="Simple molecule but represents sp3 carbon network"
    ),
    TestMolecule(
        "Polyacetylene chain (20 units)",
        "C=C" * 20,
        "edge_case",
        notes="40 carbons in conjugated polyene chain; conducting polymer",
        known_issues="Very long conjugation; UV-Vis should show extreme red shift"
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
    has_metal: bool = False
    is_drug_like: bool = False
    # Test results
    parse_ok: Optional[bool] = None
    parse_detail: str = ""
    ir_ok: Optional[bool] = None
    ir_detail: str = ""
    ir_peak_count: int = 0
    admet_ok: Optional[bool] = None
    admet_detail: str = ""
    admet_warned_non_drug: bool = False  # Did system flag as non-drug-like?
    coord3d_ok: Optional[bool] = None
    coord3d_detail: str = ""
    correctly_identified_non_drug: bool = False
    # Silent failures
    silent_failures: List[str] = field(default_factory=list)
    # Metadata
    expected_parse: bool = True
    expected_3d: bool = True
    notes: str = ""
    known_issues: str = ""


def _check_metal_atoms(mol) -> List[str]:
    """Return list of metal symbols found in molecule."""
    metals = []
    if mol is None:
        return metals
    metal_symbols = {
        "Li", "Be", "Na", "Mg", "Al", "K", "Ca", "Sc", "Ti", "V", "Cr",
        "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "Rb", "Sr", "Y",
        "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
        "Sb", "Cs", "Ba", "La", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt",
        "Au", "Hg", "Tl", "Pb", "Bi"
    }
    for atom in mol.GetAtoms():
        if atom.GetSymbol() in metal_symbols:
            metals.append(atom.GetSymbol())
    return list(set(metals))


def _check_formal_charges(mol) -> int:
    """Return total absolute formal charge."""
    if mol is None:
        return 0
    return sum(abs(a.GetFormalCharge()) for a in mol.GetAtoms())


def _check_radicals(mol) -> int:
    """Return number of radical electrons."""
    if mol is None:
        return 0
    return sum(a.GetNumRadicalElectrons() for a in mol.GetAtoms())


def _check_disconnected(mol) -> int:
    """Return number of disconnected fragments."""
    if mol is None:
        return 0
    return len(Chem.GetMolFrags(mol))


def run_single_test(mol_def: TestMolecule) -> TestResult:
    """Run all tests on a single molecule."""
    result = TestResult(
        molecule_name=mol_def.name,
        category=mol_def.category,
        smiles=mol_def.smiles,
        has_metal=mol_def.has_metal,
        is_drug_like=mol_def.is_drug_like,
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
                formula = rdMolDescriptors.CalcMolFormula(rdkit_mol)
            except Exception:
                formula = "?"
            metals = _check_metal_atoms(rdkit_mol)
            charges = _check_formal_charges(rdkit_mol)
            radicals = _check_radicals(rdkit_mol)
            frags = _check_disconnected(rdkit_mol)

            detail_parts = [f"atoms={n_atoms}", f"bonds={n_bonds}", f"formula={formula}"]
            if metals:
                detail_parts.append(f"metals={metals}")
            if charges > 0:
                detail_parts.append(f"total_charge={charges}")
            if radicals > 0:
                detail_parts.append(f"radicals={radicals}")
            if frags > 1:
                detail_parts.append(f"fragments={frags}")
            result.parse_detail = ", ".join(detail_parts)

            # Silent failure: parsed but shouldn't have
            if not mol_def.expected_parse:
                result.silent_failures.append(
                    f"SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! ({mol_def.notes})"
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
                f"{p.wavenumber:.0f}cm-1({p.assignment})" for p in ir_peaks[:5]
            )
            result.ir_detail = f"{len(ir_peaks)} peaks: {peak_summary}"

            # Silent failure: metal compound getting organic IR
            if mol_def.has_metal and rdkit_mol is not None:
                metal_atoms = _check_metal_atoms(rdkit_mol)
                organic_only = all("C-H" in p.assignment or "fingerprint" in p.assignment
                                   for p in ir_peaks)
                if organic_only and metal_atoms:
                    result.silent_failures.append(
                        f"SILENT FAIL: Metal complex ({metal_atoms}) got only organic IR peaks; "
                        f"no metal-ligand stretches"
                    )
        else:
            result.ir_ok = False
            result.ir_detail = "No IR peaks returned"
    except Exception as e:
        result.ir_ok = False
        result.ir_detail = f"Exception: {e}"

    # ── Test C: ADMET Prediction ──
    try:
        admet = predict_admet(mol_def.smiles, mol_name=mol_def.name)
        if admet.error:
            result.admet_ok = False
            result.admet_detail = f"Error: {admet.error}"
            # This is actually CORRECT behavior for non-drug-like molecules
            if mol_def.category in ("coordination", "organometallic", "inorganic",
                                     "impossible", "reactive_species"):
                result.correctly_identified_non_drug = True
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
            if admet.warnings:
                detail_parts.append(f"warnings={len(admet.warnings)}")
                result.admet_warned_non_drug = any(
                    "non-drug" in w.lower() or "metal" in w.lower() or
                    "inorganic" in w.lower() or "not applicable" in w.lower()
                    for w in admet.warnings
                )
            result.admet_detail = "; ".join(detail_parts)

            # Silent failures for non-drug-like molecules getting ADMET
            if mol_def.has_metal:
                result.silent_failures.append(
                    "SILENT FAIL: Metal-containing compound received normal ADMET profile "
                    "(ADMET is meaningless for metal complexes)"
                )
            if mol_def.category == "inorganic" and not mol_def.has_metal:
                result.silent_failures.append(
                    "SILENT FAIL: Inorganic compound received ADMET profile "
                    "(ADMET models not trained on inorganics)"
                )
            if mol_def.category == "impossible":
                result.silent_failures.append(
                    "SILENT FAIL: Impossible/wrong molecule received ADMET profile without error"
                )
            if mol_def.category == "reactive_species":
                if lip and lip.passes:
                    result.silent_failures.append(
                        "SILENT FAIL: Reactive species passed Lipinski "
                        "(reactive species are not viable drugs)"
                    )
                else:
                    result.silent_failures.append(
                        "SILENT FAIL: Reactive species received ADMET profile "
                        "(reactive intermediates are not drug candidates)"
                    )

    except Exception as e:
        result.admet_ok = False
        result.admet_detail = f"Exception: {str(e)[:120]}"

    # ── Test D: 3D Coordinate Generation ──
    if rdkit_mol is not None:
        try:
            mol_3d = Chem.AddHs(rdkit_mol)
            embed_result = AllChem.EmbedMolecule(mol_3d, AllChem.ETKDG())
            if embed_result == 0:
                try:
                    opt = AllChem.MMFFOptimizeMolecule(mol_3d, maxIters=200)
                    if opt in (0, 1):
                        result.coord3d_ok = True
                        result.coord3d_detail = f"Embedded + MMFF optimized (status={opt})"
                    else:
                        try:
                            AllChem.UFFOptimizeMolecule(mol_3d, maxIters=200)
                            result.coord3d_ok = True
                            result.coord3d_detail = "Embedded + UFF optimized (MMFF failed)"
                        except Exception:
                            result.coord3d_ok = True
                            result.coord3d_detail = "Embedded but optimization failed"
                except Exception:
                    try:
                        AllChem.UFFOptimizeMolecule(mol_3d, maxIters=200)
                        result.coord3d_ok = True
                        result.coord3d_detail = "Embedded + UFF optimized"
                    except Exception:
                        result.coord3d_ok = True
                        result.coord3d_detail = "Embedded, optimization skipped"
            else:
                result.coord3d_ok = False
                result.coord3d_detail = f"EmbedMolecule returned {embed_result}"
                if mol_def.expected_3d:
                    result.coord3d_detail += " (UNEXPECTED)"
        except Exception as e:
            result.coord3d_ok = False
            result.coord3d_detail = f"Exception: {str(e)[:100]}"
    else:
        result.coord3d_ok = False
        result.coord3d_detail = "Skipped (SMILES parse failed)"

    # ── Test E: Non-drug-like identification ──
    # Check if system correctly flags non-drug-like molecules
    if rdkit_mol is not None and not mol_def.is_drug_like:
        metals = _check_metal_atoms(rdkit_mol)
        charges = _check_formal_charges(rdkit_mol)
        radicals = _check_radicals(rdkit_mol)
        frags = _check_disconnected(rdkit_mol)

        reasons = []
        if metals:
            reasons.append(f"contains metals ({metals})")
        if charges > 2:
            reasons.append(f"high formal charges (total={charges})")
        if radicals > 0:
            reasons.append(f"contains radicals ({radicals}e)")
        if frags > 2:
            reasons.append(f"too many fragments ({frags})")

        if reasons and result.admet_ok and not result.admet_warned_non_drug:
            result.silent_failures.append(
                f"SILENT FAIL: Non-drug-like molecule ({', '.join(reasons)}) "
                f"was NOT flagged by ADMET system"
            )
            result.correctly_identified_non_drug = False
        elif reasons and (not result.admet_ok or result.admet_warned_non_drug):
            result.correctly_identified_non_drug = True

    return result


def run_all_tests() -> List[TestResult]:
    """Run vaccine circulation v2 on all 50 molecules."""
    results = []
    print(f"\n{'='*80}")
    print(f" VACCINE CIRCULATION V2: INORGANIC/COORDINATION STRESS TEST")
    print(f" {len(MOLECULES)} molecules x 4 test types + non-drug detection")
    print(f" Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    for i, mol_def in enumerate(MOLECULES, 1):
        print(f"[{i:2d}/50] Testing: {mol_def.name} ({mol_def.category})")
        t0 = time.time()
        result = run_single_test(mol_def)
        elapsed = time.time() - t0

        statuses = []
        for label, ok in [("Parse", result.parse_ok), ("IR", result.ir_ok),
                          ("ADMET", result.admet_ok), ("3D", result.coord3d_ok)]:
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
            for sf in result.silent_failures[:3]:
                print(f"        >> {sf}")
            if sf_count > 3:
                print(f"        >> ... and {sf_count - 3} more")

        results.append(result)

    return results


def generate_report(results: List[TestResult]) -> str:
    """Generate comprehensive markdown report."""
    lines = []
    lines.append("# Vaccine Circulation V2 Results: Inorganic/Coordination Stress Test")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total molecules tested:** {len(results)}")
    lines.append(f"**Python:** {sys.version.split()[0]}")
    lines.append("")

    # Overall statistics
    total_tests = sum(4 for _ in results)  # 4 tests per molecule
    pass_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.admet_ok, r.coord3d_ok]
        if ok is True
    )
    fail_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.admet_ok, r.coord3d_ok]
        if ok is False
    )
    skip_count = total_tests - pass_count - fail_count
    silent_total = sum(len(r.silent_failures) for r in results)
    correctly_flagged = sum(1 for r in results if r.correctly_identified_non_drug)

    lines.append("## Summary")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total individual tests | {total_tests} |")
    lines.append(f"| PASS | {pass_count} |")
    lines.append(f"| FAIL (explicit) | {fail_count} |")
    lines.append(f"| SKIP | {skip_count} |")
    lines.append(f"| **SILENT FAILURES** | **{silent_total}** |")
    lines.append(f"| Correctly identified non-drug-like | {correctly_flagged}/{len(results)} |")
    lines.append("")

    # Per-test-type stats
    lines.append("## Pass Rate by Test Type")
    lines.append("| Test | Pass | Fail | Skip | Rate |")
    lines.append("|------|------|------|------|------|")
    for test_name, accessor in [
        ("SMILES Parse", lambda r: r.parse_ok),
        ("IR Spectrum", lambda r: r.ir_ok),
        ("ADMET", lambda r: r.admet_ok),
        ("3D Coords", lambda r: r.coord3d_ok),
    ]:
        p = sum(1 for r in results if accessor(r) is True)
        f = sum(1 for r in results if accessor(r) is False)
        s = len(results) - p - f
        rate = f"{p/(p+f)*100:.0f}%" if (p+f) > 0 else "N/A"
        lines.append(f"| {test_name} | {p} | {f} | {s} | {rate} |")
    lines.append("")

    # Per-category stats
    lines.append("## Pass Rate by Category")
    categories = {}
    for r in results:
        if r.category not in categories:
            categories[r.category] = {"pass": 0, "fail": 0, "silent": 0, "total": 0, "non_drug_flagged": 0}
        cat = categories[r.category]
        for ok in [r.parse_ok, r.ir_ok, r.admet_ok, r.coord3d_ok]:
            cat["total"] += 1
            if ok is True:
                cat["pass"] += 1
            elif ok is False:
                cat["fail"] += 1
        cat["silent"] += len(r.silent_failures)
        if r.correctly_identified_non_drug:
            cat["non_drug_flagged"] += 1

    lines.append("| Category | Tests | Pass | Fail | Silent Fails | Correctly Flagged |")
    lines.append("|----------|-------|------|------|-------------|-------------------|")
    for cat_name in ["coordination", "organometallic", "inorganic", "impossible",
                     "reactive_species", "edge_case"]:
        if cat_name in categories:
            c = categories[cat_name]
            n_mols = sum(1 for r in results if r.category == cat_name)
            lines.append(
                f"| {cat_name} | {c['total']} | {c['pass']} | {c['fail']} "
                f"| {c['silent']} | {c['non_drug_flagged']}/{n_mols} |"
            )
    lines.append("")

    # ── SILENT FAILURES ──
    lines.append("## SILENT FAILURES (Critical for Audit Teams)")
    lines.append("")
    lines.append("> These are cases where the system produced a result WITHOUT an error,")
    lines.append("> but the result is chemically wrong, meaningless, or misleading.")
    lines.append("> Inorganic/metal compounds should NEVER get standard organic ADMET profiles.")
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

    # ── Detailed Results ──
    lines.append("## Detailed Results (All 50 Molecules)")
    lines.append("")

    for cat_name, cat_label in [
        ("coordination", "Coordination Compounds"),
        ("organometallic", "Organometallics"),
        ("inorganic", "Inorganic"),
        ("impossible", "Impossible/Wrong Structures"),
        ("reactive_species", "Reactive Species"),
        ("edge_case", "Edge Cases"),
    ]:
        cat_results = [r for r in results if r.category == cat_name]
        if not cat_results:
            continue

        lines.append(f"### {cat_label}")
        lines.append("")

        for r in cat_results:
            status_parse = "PASS" if r.parse_ok else ("FAIL" if r.parse_ok is False else "SKIP")
            status_ir = "PASS" if r.ir_ok else ("FAIL" if r.ir_ok is False else "SKIP")
            status_admet = "PASS" if r.admet_ok else ("FAIL" if r.admet_ok is False else "SKIP")
            status_3d = "PASS" if r.coord3d_ok else ("FAIL" if r.coord3d_ok is False else "SKIP")

            lines.append(f"**{r.molecule_name}**")
            lines.append(f"- SMILES: `{r.smiles}`")
            lines.append(f"- Parse: [{status_parse}] {r.parse_detail}")
            lines.append(f"- IR: [{status_ir}] {r.ir_detail}")
            lines.append(f"- ADMET: [{status_admet}] {r.admet_detail}")
            lines.append(f"- 3D: [{status_3d}] {r.coord3d_detail}")
            ndf = "YES" if r.correctly_identified_non_drug else "NO"
            lines.append(f"- Non-drug-like correctly identified: **{ndf}**")
            if r.silent_failures:
                lines.append(f"- **SILENT FAILURES ({len(r.silent_failures)}):**")
                for sf in r.silent_failures:
                    lines.append(f"  - {sf}")
            if r.known_issues:
                lines.append(f"- Known issues: {r.known_issues}")
            lines.append("")

    # ── Audit Recommendations ──
    lines.append("## Audit Recommendations")
    lines.append("")
    lines.append("### Critical Fixes Needed")
    lines.append("1. **ADMET must detect metal atoms** and refuse to produce a standard organic ADMET profile. "
                 "Add a pre-check: if molecule contains transition metals, return a warning instead of Lipinski/BBB scores.")
    lines.append("2. **ADMET must detect radicals** and formal charges > |2| as indicators of reactive/unstable species.")
    lines.append("3. **ADMET must detect disconnected fragments** (>2) as suspicious input.")
    lines.append("4. **IR predictor needs metal-ligand modes**: M-N, M-O, M-Cl stretches (200-600 cm-1 region).")
    lines.append("5. **Impossible structures that pass RDKit parsing** (cyclopropyne, cyclobutadiene) need "
                 "post-parse chemical feasibility validation.")
    lines.append("")
    lines.append(f"**Total silent failures found: {silent_total}**")
    lines.append("")
    if silent_total > 20:
        lines.append("**VERDICT: CRITICAL number of silent failures. System has NO inorganic/metal validation.**")
    elif silent_total > 10:
        lines.append("**VERDICT: HIGH number of silent failures. Significant gaps in non-organic molecule handling.**")
    else:
        lines.append("**VERDICT: MODERATE. Some validation exists but needs improvement.**")

    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("Starting Vaccine Circulation V2: Inorganic/Coordination Stress Test...")
    results = run_all_tests()

    print(f"\n{'='*80}")
    print(f" GENERATING REPORT")
    print(f"{'='*80}\n")

    report = generate_report(results)

    output_path = Path(__file__).resolve().parent / "vaccine_circulation_v2_results.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Report written to: {output_path}")

    # Print summary
    silent_total = sum(len(r.silent_failures) for r in results)
    correctly_flagged = sum(1 for r in results if r.correctly_identified_non_drug)
    print(f"\n{'='*80}")
    print(f" FINAL SUMMARY")
    print(f"{'='*80}")
    print(f" Total molecules: {len(results)}")
    print(f" Silent failures: {silent_total}")
    print(f" Correctly identified non-drug-like: {correctly_flagged}/{len(results)}")

    pass_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.admet_ok, r.coord3d_ok]
        if ok is True
    )
    fail_count = sum(
        1 for r in results
        for ok in [r.parse_ok, r.ir_ok, r.admet_ok, r.coord3d_ok]
        if ok is False
    )
    total = pass_count + fail_count
    if total > 0:
        print(f" Pass: {pass_count}/{total} ({pass_count/total*100:.0f}%)")
        print(f" Fail: {fail_count}/{total} ({fail_count/total*100:.0f}%)")
    print(f"{'='*80}")
