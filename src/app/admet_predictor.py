# admet_predictor.py (v1.0 - ADMET Property Prediction)
"""
ChemGrid: ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) Predictor
- Lipinski Rule of Five evaluation
- BBB (Blood-Brain Barrier) permeability estimation
- Metabolic stability heuristics
- Comprehensive ADMET profile from SMILES input
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski, Crippen, rdMolDescriptors, QED
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class LipinskiResult:
    """Lipinski's Rule of Five evaluation."""
    mw: float = 0.0            # Molecular Weight
    logp: float = 0.0          # Calculated LogP (Wildman-Crippen)
    hbd: int = 0               # Hydrogen Bond Donors
    hba: int = 0               # Hydrogen Bond Acceptors
    violations: int = 0
    violation_details: List[str] = field(default_factory=list)
    passes: bool = False       # True if <= 1 violation

@dataclass
class BBBResult:
    """Blood-Brain Barrier permeability estimation."""
    score: float = 0.0         # 0-1 probability estimate
    classification: str = ""   # "BBB+", "BBB-", "uncertain"
    tpsa: float = 0.0          # Topological Polar Surface Area
    logp: float = 0.0
    mw: float = 0.0
    hbd: int = 0
    factors: Dict[str, str] = field(default_factory=dict)

@dataclass
class MetabolicStabilityResult:
    """Metabolic stability heuristics."""
    classification: str = ""   # "high", "moderate", "low"
    score: float = 0.0         # 0-1 stability score
    n_rotatable_bonds: int = 0
    n_aromatic_rings: int = 0
    mw: float = 0.0
    clogp: float = 0.0
    alerts: List[str] = field(default_factory=list)
    metabolic_soft_spots: List[str] = field(default_factory=list)

@dataclass
class ADMETProfile:
    """Complete ADMET prediction profile."""
    smiles: str = ""
    mol_name: str = ""
    is_organic: bool = True           # False if non-organic elements detected
    lipinski: Optional[LipinskiResult] = None
    bbb: Optional[BBBResult] = None
    metabolic_stability: Optional[MetabolicStabilityResult] = None
    # Additional descriptors
    tpsa: float = 0.0
    n_rotatable_bonds: int = 0
    n_aromatic_rings: int = 0
    n_heavy_atoms: int = 0
    molar_refractivity: float = 0.0
    # Drug-likeness
    qed_score: float = 0.0           # RDKit QED (Quantitative Estimate of Drug-likeness), 0-1
    drug_likeness_score: float = 0.0  # 0-1 composite score
    oral_bioavailability: str = ""    # "likely", "moderate", "unlikely"
    # Summary
    overall_assessment: str = ""
    warnings: List[str] = field(default_factory=list)
    error: str = ""


# ============================================================================
# LIPINSKI RULE OF FIVE
# ============================================================================

def evaluate_lipinski(mol) -> Optional[LipinskiResult]:
    """
    Evaluate Lipinski's Rule of Five for oral bioavailability.

    Criteria:
      - MW <= 500 Da
      - LogP <= 5
      - HBD (NH, OH) <= 5
      - HBA (N, O atoms) <= 10

    A compound is "drug-like" if it violates at most 1 rule.
    """
    if mol is None:
        logger.warning("evaluate_lipinski: mol is None — cannot evaluate")
        return None

    result = LipinskiResult()

    result.mw = Descriptors.MolWt(mol)
    result.logp = Crippen.MolLogP(mol)
    result.hbd = Lipinski.NumHDonors(mol)
    result.hba = Lipinski.NumHAcceptors(mol)

    violations = []
    if result.mw > 500:
        violations.append(f"MW={result.mw:.1f} > 500")
    if result.logp > 5:
        violations.append(f"LogP={result.logp:.2f} > 5")
    if result.hbd > 5:
        violations.append(f"HBD={result.hbd} > 5")
    if result.hba > 10:
        violations.append(f"HBA={result.hba} > 10")

    result.violations = len(violations)
    result.violation_details = violations
    result.passes = len(violations) <= 1

    return result


# ============================================================================
# BBB PERMEABILITY
# ============================================================================

def estimate_bbb_permeability(mol) -> Optional[BBBResult]:
    """
    Estimate Blood-Brain Barrier permeability using physicochemical descriptors.

    Based on simplified Clark/Pardridge model:
      - TPSA < 90 A^2 favors BBB penetration
      - LogP 1-3 optimal
      - MW < 450
      - HBD <= 3
      - No strong P-gp substrate features

    Returns a score 0-1 and classification.
    """
    if mol is None:
        logger.warning("estimate_bbb_permeability: mol is None — cannot estimate")
        return None

    result = BBBResult()

    result.tpsa = Descriptors.TPSA(mol)
    result.logp = Crippen.MolLogP(mol)
    result.mw = Descriptors.MolWt(mol)
    result.hbd = Lipinski.NumHDonors(mol)

    score = 1.0
    factors = {}

    # TPSA factor (most important for BBB)
    if result.tpsa <= 60:
        factors["TPSA"] = f"{result.tpsa:.1f} A^2 (favorable)"
    elif result.tpsa <= 90:
        score -= 0.15
        factors["TPSA"] = f"{result.tpsa:.1f} A^2 (borderline)"
    else:
        penalty = min(0.5, (result.tpsa - 90) / 100)
        score -= penalty
        factors["TPSA"] = f"{result.tpsa:.1f} A^2 (unfavorable, >90)"

    # LogP factor
    if 1.0 <= result.logp <= 3.0:
        factors["LogP"] = f"{result.logp:.2f} (optimal 1-3)"
    elif 0.0 <= result.logp <= 5.0:
        score -= 0.1
        factors["LogP"] = f"{result.logp:.2f} (acceptable)"
    else:
        score -= 0.25
        factors["LogP"] = f"{result.logp:.2f} (suboptimal)"

    # MW factor
    if result.mw <= 400:
        factors["MW"] = f"{result.mw:.1f} (favorable)"
    elif result.mw <= 500:
        score -= 0.1
        factors["MW"] = f"{result.mw:.1f} (borderline)"
    else:
        score -= 0.3
        factors["MW"] = f"{result.mw:.1f} (unfavorable, >500)"

    # HBD factor
    if result.hbd <= 1:
        factors["HBD"] = f"{result.hbd} (favorable)"
    elif result.hbd <= 3:
        score -= 0.1
        factors["HBD"] = f"{result.hbd} (acceptable)"
    else:
        score -= 0.25
        factors["HBD"] = f"{result.hbd} (unfavorable, >3)"

    score = max(0.0, min(1.0, score))
    result.score = score
    result.factors = factors

    if score >= 0.7:
        result.classification = "BBB+"
    elif score >= 0.4:
        result.classification = "uncertain"
    else:
        result.classification = "BBB-"

    return result


# ============================================================================
# METABOLIC STABILITY
# ============================================================================

# SMARTS patterns for metabolic soft spots
_METABOLIC_ALERTS = [
    ("ester_hydrolysis", "[C;!R](=O)[O;!R][C,c]", "Ester bond (hydrolysis risk)"),
    ("amide_hydrolysis", "[C;!R](=O)[NH][C,c]", "Primary/secondary amide (hydrolysis)"),
    ("benzylic_oxidation", "[cH1]~[CH2]", "Benzylic position (CYP oxidation)"),
    ("allylic_oxidation", "[CH2]~[CH]=[CH]", "Allylic position (oxidation)"),
    ("n_dealkylation", "[NH1,NH2][CH3]", "N-methyl (N-dealkylation)"),
    ("o_dealkylation", "[OH0][CH3]", "O-methyl (O-dealkylation by CYP)"),
    ("sulfide_oxidation", "[#16X2]", "Thioether (S-oxidation)"),
    ("epoxidation", "c1ccccc1", "Aromatic ring (epoxidation risk)"),
    ("glucuronidation", "[OH]c", "Phenol (glucuronidation)"),
    ("nitro_reduction", "[N+](=O)[O-]", "Nitro group (reduction)"),
]


def estimate_metabolic_stability(mol) -> Optional[MetabolicStabilityResult]:
    """
    Estimate metabolic stability using structural alerts and descriptors.

    Heuristic scoring based on:
      - Number of metabolic soft spots (SMARTS alerts)
      - Rotatable bonds (flexibility correlates with metabolism)
      - LogP (highly lipophilic = faster metabolism)
      - MW (larger = more sites of metabolism)
    """
    if mol is None:
        logger.warning("estimate_metabolic_stability: mol is None — cannot estimate")
        return None

    result = MetabolicStabilityResult()

    result.n_rotatable_bonds = Lipinski.NumRotatableBonds(mol)
    result.n_aromatic_rings = Lipinski.NumAromaticRings(mol)
    result.mw = Descriptors.MolWt(mol)
    result.clogp = Crippen.MolLogP(mol)

    # Check metabolic alerts
    alerts = []
    soft_spots = []
    for name, smarts, description in _METABOLIC_ALERTS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None:
            matches = mol.GetSubstructMatches(pattern)
            if matches:
                alerts.append(f"{description} ({len(matches)}x)")
                soft_spots.append(name)

    result.alerts = alerts
    result.metabolic_soft_spots = soft_spots

    # Scoring
    score = 1.0

    # Penalty for metabolic soft spots
    n_alerts = len(alerts)
    if n_alerts >= 4:
        score -= 0.4
    elif n_alerts >= 2:
        score -= 0.2
    elif n_alerts >= 1:
        score -= 0.1

    # Penalty for high lipophilicity (CYP substrate likelihood)
    if result.clogp > 4.0:
        score -= 0.2
    elif result.clogp > 3.0:
        score -= 0.1

    # Penalty for high flexibility
    if result.n_rotatable_bonds > 10:
        score -= 0.15
    elif result.n_rotatable_bonds > 7:
        score -= 0.05

    # Penalty for large MW
    if result.mw > 600:
        score -= 0.15
    elif result.mw > 500:
        score -= 0.05

    score = max(0.0, min(1.0, score))
    result.score = score

    if score >= 0.7:
        result.classification = "high"
    elif score >= 0.4:
        result.classification = "moderate"
    else:
        result.classification = "low"

    return result


# ============================================================================
# VEBER RULES (Oral Bioavailability)
# ============================================================================

def evaluate_veber_rules(mol) -> Optional[Dict]:
    """
    Evaluate Veber's rules for oral bioavailability.

    Criteria:
      - Rotatable bonds <= 10
      - TPSA <= 140 A^2
    """
    if mol is None:
        logger.warning("evaluate_veber_rules: mol is None — cannot evaluate")
        return None

    rot_bonds = Lipinski.NumRotatableBonds(mol)
    tpsa = Descriptors.TPSA(mol)

    violations = []
    if rot_bonds > 10:
        violations.append(f"Rotatable bonds={rot_bonds} > 10")
    if tpsa > 140:
        violations.append(f"TPSA={tpsa:.1f} > 140")

    return {
        "rotatable_bonds": rot_bonds,
        "tpsa": tpsa,
        "violations": len(violations),
        "violation_details": violations,
        "passes": len(violations) == 0,
    }


# ============================================================================
# GHOSE FILTER
# ============================================================================

def evaluate_ghose_filter(mol) -> Optional[Dict]:
    """
    Evaluate Ghose filter for drug-likeness.

    Criteria:
      - 160 <= MW <= 480
      - -0.4 <= LogP <= 5.6
      - 40 <= Molar Refractivity <= 130
      - 20 <= Total Atom Count <= 70
    """
    if mol is None:
        logger.warning("evaluate_ghose_filter: mol is None — cannot evaluate")
        return None

    mw = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    mr = Crippen.MolMR(mol)
    n_atoms = mol.GetNumAtoms()

    violations = []
    if not (160 <= mw <= 480):
        violations.append(f"MW={mw:.1f} not in [160, 480]")
    if not (-0.4 <= logp <= 5.6):
        violations.append(f"LogP={logp:.2f} not in [-0.4, 5.6]")
    if not (40 <= mr <= 130):
        violations.append(f"MR={mr:.1f} not in [40, 130]")
    if not (20 <= n_atoms <= 70):
        violations.append(f"Atoms={n_atoms} not in [20, 70]")

    return {
        "mw": mw,
        "logp": logp,
        "molar_refractivity": mr,
        "n_atoms": n_atoms,
        "violations": len(violations),
        "violation_details": violations,
        "passes": len(violations) == 0,
    }


# ============================================================================
# CHEMICAL PLAUSIBILITY PRE-FILTER
# ============================================================================

# Elements commonly found in organic drug molecules
_ORGANIC_ELEMENTS = {'C', 'H', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I', 'B', 'Si', 'Se'}


def _validate_molecule_type(mol) -> Tuple[bool, List[str]]:
    """
    Check if molecule is suitable for ADMET analysis.

    Screens out:
      1. Metal complexes / non-organic elements
      2. Radical species (reactive intermediates)
      3. Highly charged ionic species
      4. Disconnected fragments (salts, mixtures)
      5. Impossible ring strain (triple bond in 3-4 membered ring)
      6. Anti-aromatic 4-membered fully-conjugated rings

    Returns:
        (is_valid, warnings) where is_valid=True means no issues found.
    """
    if mol is None:
        logger.warning("_validate_molecule_type: mol is None — skipping validation")
        return False, ["mol 객체가 None — 분자 검증 불가"]

    warnings: List[str] = []

    # 1. Metal / non-organic element detection
    for atom in mol.GetAtoms():
        sym = atom.GetSymbol()
        if sym not in _ORGANIC_ELEMENTS:
            warnings.append(
                f"\u26a0\ufe0f 금속/비유기 원소 감지 ({sym}) \u2014 ADMET 예측값이 부정확할 수 있습니다"
            )
            break  # one warning is enough

    # 2. Radical detection
    for atom in mol.GetAtoms():
        if atom.GetNumRadicalElectrons() > 0:
            warnings.append(
                "\u26a0\ufe0f 라디칼 종 \u2014 반응성 중간체이므로 약물 후보가 될 수 없습니다"
            )
            break

    # 3. High total absolute formal charge
    total_charge = sum(abs(atom.GetFormalCharge()) for atom in mol.GetAtoms())
    if total_charge > 2:
        warnings.append(
            f"\u26a0\ufe0f 높은 전하 ({total_charge}) \u2014 이온성 종이므로 경구 투여 약물로 부적합"
        )

    # 4. Disconnected fragments (salts, mixtures)
    from rdkit.Chem import GetMolFrags
    frags = GetMolFrags(mol)
    if len(frags) > 1:
        warnings.append(
            f"\u26a0\ufe0f 분자가 {len(frags)}개 조각으로 분리됨 \u2014 단일 분자가 아닙니다"
        )

    # 5. Impossible ring strain: triple bond in 3- or 4-membered ring
    ring_info = mol.GetRingInfo()
    for ring in ring_info.BondRings():
        if len(ring) <= 4:
            for bond_idx in ring:
                bond = mol.GetBondWithIdx(bond_idx)
                if bond.GetBondType() == Chem.BondType.TRIPLE:
                    warnings.append(
                        "\u26a0\ufe0f 소형 고리에 삼중결합 \u2014 화학적으로 불가능한 구조"
                    )
                    break
            else:
                continue
            break  # already found one, no need to keep scanning

    # 6. Anti-aromatic check: 4-membered fully sp2-conjugated ring
    for ring_atoms in ring_info.AtomRings():
        if len(ring_atoms) == 4:
            all_sp2 = all(
                mol.GetAtomWithIdx(i).GetHybridization() == Chem.HybridizationType.SP2
                for i in ring_atoms
            )
            if all_sp2:
                warnings.append(
                    "\u26a0\ufe0f 4원 반방향족 고리 감지 \u2014 극도로 불안정한 구조"
                )
                break  # one warning is enough

    is_valid = len(warnings) == 0
    return is_valid, warnings


# ============================================================================
# UNIFIED ADMET PROFILE
# ============================================================================

def predict_admet(smiles: str, mol_name: str = "") -> ADMETProfile:
    """
    Generate a comprehensive ADMET profile from a SMILES string.

    Args:
        smiles: Valid SMILES string
        mol_name: Optional molecule name

    Returns:
        ADMETProfile with all predictions
    """
    # N: Type guard — smiles must be str
    if not isinstance(smiles, str):
        logger.warning("predict_admet: smiles is not str — type=%s, value=%s", type(smiles).__name__, smiles)
        smiles = str(smiles) if smiles is not None else ""
    if not isinstance(mol_name, str):
        logger.warning("predict_admet: mol_name is not str — type=%s", type(mol_name).__name__)
        mol_name = str(mol_name) if mol_name is not None else ""

    profile = ADMETProfile(smiles=smiles, mol_name=mol_name)

    if not smiles or not smiles.strip():
        profile.error = "빈 SMILES 문자열 — ADMET 예측 불가"
        logger.warning("predict_admet: empty SMILES string provided")
        return profile

    if not RDKIT_AVAILABLE:
        profile.error = "RDKit not available - cannot compute ADMET properties"
        logger.warning("predict_admet: RDKit unavailable")
        return profile

    # L: SMILES parsing defense — MolFromSmiles + None check
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        profile.error = f"잘못된 SMILES 구조: {smiles}"
        logger.warning("predict_admet: invalid SMILES — %s", smiles)
        return profile

    # --- Chemical plausibility pre-filter ---
    is_valid, validation_warnings = _validate_molecule_type(mol)
    if validation_warnings:
        profile.warnings.extend(validation_warnings)
    # Mark non-organic if metal/non-organic element detected
    for atom in mol.GetAtoms():
        if atom.GetSymbol() not in _ORGANIC_ELEMENTS:
            profile.is_organic = False
            break

    # Add hydrogens for accurate descriptor calculation
    mol_h = Chem.AddHs(mol)

    # Core predictions (None-safe: sub-functions return None on failure)
    profile.lipinski = evaluate_lipinski(mol)
    profile.bbb = estimate_bbb_permeability(mol)
    profile.metabolic_stability = estimate_metabolic_stability(mol)

    # Additional descriptors
    profile.tpsa = Descriptors.TPSA(mol)
    profile.n_rotatable_bonds = Lipinski.NumRotatableBonds(mol)
    profile.n_aromatic_rings = Lipinski.NumAromaticRings(mol)
    profile.n_heavy_atoms = mol.GetNumHeavyAtoms()
    profile.molar_refractivity = Crippen.MolMR(mol)

    # QED (Quantitative Estimate of Drug-likeness) — Bickerton et al. 2012
    try:
        profile.qed_score = QED.qed(mol)
    except Exception as e:
        logger.warning("QED calculation failed for %s: %s", smiles, e)
        profile.qed_score = 0.0

    # Drug-likeness composite score (0-1)
    dl_score = 0.0
    dl_factors = 0

    # N: None guard — lipinski can be None
    if profile.lipinski is not None and profile.lipinski.passes:
        dl_score += 0.3
    dl_factors += 0.3

    veber = evaluate_veber_rules(mol)
    # N: None guard — veber can be None
    if veber is not None and veber["passes"]:
        dl_score += 0.2
    dl_factors += 0.2

    ghose = evaluate_ghose_filter(mol)
    # N: None guard — ghose can be None
    if ghose is not None and ghose["passes"]:
        dl_score += 0.2
    dl_factors += 0.2

    # Metabolic stability contribution (None guard)
    if profile.metabolic_stability is not None:
        if profile.metabolic_stability.classification == "high":
            dl_score += 0.15
        elif profile.metabolic_stability.classification == "moderate":
            dl_score += 0.08
    dl_factors += 0.15

    # BBB is a bonus, not required (None guard)
    if profile.bbb is not None and profile.bbb.classification == "BBB+":
        dl_score += 0.15
    dl_factors += 0.15

    profile.drug_likeness_score = dl_score / dl_factors if dl_factors > 0 else 0.0

    # Oral bioavailability assessment (None guards)
    lipinski_passes = profile.lipinski.passes if profile.lipinski is not None else False
    lipinski_violations = profile.lipinski.violations if profile.lipinski is not None else 999
    veber_passes = veber["passes"] if (veber is not None and isinstance(veber, dict)) else False

    if lipinski_passes and veber_passes:
        profile.oral_bioavailability = "likely"
    elif lipinski_violations <= 2:
        profile.oral_bioavailability = "moderate"
    else:
        profile.oral_bioavailability = "unlikely"

    # Warnings (append to any pre-filter warnings already in profile.warnings)
    if lipinski_violations > 1:
        profile.warnings.append(f"Lipinski violations ({lipinski_violations}): poor oral absorption expected")
    if profile.tpsa > 140:
        profile.warnings.append(f"High TPSA ({profile.tpsa:.1f}): poor membrane permeability")
    if profile.metabolic_stability is not None:
        if profile.metabolic_stability.classification == "low":
            profile.warnings.append("Low metabolic stability: rapid clearance expected")
        if len(profile.metabolic_stability.alerts) > 3:
            profile.warnings.append(f"Multiple metabolic soft spots ({len(profile.metabolic_stability.alerts)})")
    if profile.n_heavy_atoms > 50:
        profile.warnings.append("Large molecule: may have absorption issues")

    # Overall assessment
    if profile.drug_likeness_score >= 0.7:
        profile.overall_assessment = "Good drug-like properties"
    elif profile.drug_likeness_score >= 0.4:
        profile.overall_assessment = "Moderate drug-like properties - optimization recommended"
    else:
        profile.overall_assessment = "Poor drug-like properties - significant optimization needed"

    return profile


def admet_to_dict(profile: ADMETProfile) -> Dict:
    """Convert an ADMETProfile to a plain dictionary for serialization."""
    # N: Type guard — profile must be ADMETProfile
    if not isinstance(profile, ADMETProfile):
        logger.warning("admet_to_dict: profile is not ADMETProfile — type=%s", type(profile).__name__)
        return {"error": f"잘못된 프로파일 타입: {type(profile).__name__}"}

    d = {
        "smiles": profile.smiles,
        "mol_name": profile.mol_name,
        "is_organic": profile.is_organic,
        "error": profile.error,
        "qed_score": round(profile.qed_score, 3),
        "drug_likeness_score": round(profile.drug_likeness_score, 3),
        "oral_bioavailability": profile.oral_bioavailability,
        "overall_assessment": profile.overall_assessment,
        "warnings": profile.warnings,
        "descriptors": {
            "tpsa": round(profile.tpsa, 2),
            "n_rotatable_bonds": profile.n_rotatable_bonds,
            "n_aromatic_rings": profile.n_aromatic_rings,
            "n_heavy_atoms": profile.n_heavy_atoms,
            "molar_refractivity": round(profile.molar_refractivity, 2),
        },
    }

    if profile.lipinski:
        d["lipinski"] = {
            "mw": round(profile.lipinski.mw, 2),
            "logp": round(profile.lipinski.logp, 2),
            "hbd": profile.lipinski.hbd,
            "hba": profile.lipinski.hba,
            "violations": profile.lipinski.violations,
            "violation_details": profile.lipinski.violation_details,
            "passes": profile.lipinski.passes,
        }

    if profile.bbb:
        d["bbb"] = {
            "score": round(profile.bbb.score, 3),
            "classification": profile.bbb.classification,
            "tpsa": round(profile.bbb.tpsa, 2),
            "factors": profile.bbb.factors,
        }

    if profile.metabolic_stability:
        d["metabolic_stability"] = {
            "classification": profile.metabolic_stability.classification,
            "score": round(profile.metabolic_stability.score, 3),
            "n_rotatable_bonds": profile.metabolic_stability.n_rotatable_bonds,
            "n_aromatic_rings": profile.metabolic_stability.n_aromatic_rings,
            "alerts": profile.metabolic_stability.alerts,
            "metabolic_soft_spots": profile.metabolic_stability.metabolic_soft_spots,
        }

    return d
