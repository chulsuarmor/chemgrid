# drug_screening.py (v1.0 - Drug Screening Pipeline)
"""
ChemGrid: Drug Screening Pipeline
- pLDDT confidence filtering from AlphaFold predictions
- Hit compound ranking by binding affinity
- QED (Quantitative Estimate of Drug-likeness) scoring via RDKit
- Multi-criteria compound prioritization
"""

import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen, Lipinski, QED as RDKit_QED
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# Local imports with graceful fallback
try:
    from alphafold_interface import ProteinStructure, filter_by_plddt
    ALPHAFOLD_AVAILABLE = True
except ImportError:
    ALPHAFOLD_AVAILABLE = False

try:
    from admet_predictor import predict_admet, ADMETProfile
    ADMET_AVAILABLE = True
except ImportError:
    ADMET_AVAILABLE = False


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class CompoundEntry:
    """A single compound in the screening library."""
    smiles: str = ""
    name: str = ""
    mol_id: str = ""
    source: str = ""  # "library", "user", "virtual"

@dataclass
class DockingScore:
    """Docking result for a compound."""
    smiles: str
    binding_affinity: float = 0.0   # kcal/mol (more negative = better)
    pose_rmsd: float = 0.0
    n_interactions: int = 0
    interaction_types: List[str] = field(default_factory=list)

@dataclass
class QEDResult:
    """QED scoring result."""
    qed_score: float = 0.0       # 0-1, higher = more drug-like
    mw: float = 0.0
    logp: float = 0.0
    hba: int = 0
    hbd: int = 0
    tpsa: float = 0.0
    n_rotatable: int = 0
    n_aromatic_rings: int = 0
    n_alerts: int = 0            # Structural alerts count

@dataclass
class ScreeningHit:
    """A screened compound with all scoring metrics."""
    compound: CompoundEntry = field(default_factory=CompoundEntry)
    qed: Optional[QEDResult] = None
    docking: Optional[DockingScore] = None
    admet: Optional[ADMETProfile] = None
    # Composite scores
    composite_score: float = 0.0   # 0-1, weighted combination
    rank: int = 0
    tier: str = ""                  # "A" (top), "B" (promising), "C" (weak)
    flags: List[str] = field(default_factory=list)

@dataclass
class ScreeningResult:
    """Complete screening campaign result."""
    n_compounds: int = 0
    n_hits: int = 0
    hits: List[ScreeningHit] = field(default_factory=list)
    target_pdb_id: str = ""
    target_plddt_reliable: bool = False
    filters_applied: List[str] = field(default_factory=list)
    error: str = ""


# ============================================================================
# QED SCORING
# ============================================================================

def calculate_qed(smiles: str) -> Optional[QEDResult]:
    """
    Calculate QED (Quantitative Estimate of Drug-likeness) using RDKit.

    QED is a composite score (0-1) that integrates multiple molecular
    descriptors into a single measure of drug-likeness.

    Based on: Bickerton et al., Nature Chemistry 4, 90-98 (2012)
    """
    if not RDKIT_AVAILABLE:
        return None

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    result = QEDResult()

    try:
        result.qed_score = RDKit_QED.qed(mol)
    except Exception:
        # Fallback: manual QED approximation
        result.qed_score = _approximate_qed(mol)

    result.mw = Descriptors.MolWt(mol)
    result.logp = Crippen.MolLogP(mol)
    result.hba = Lipinski.NumHAcceptors(mol)
    result.hbd = Lipinski.NumHDonors(mol)
    result.tpsa = Descriptors.TPSA(mol)
    result.n_rotatable = Lipinski.NumRotatableBonds(mol)
    result.n_aromatic_rings = Lipinski.NumAromaticRings(mol)

    # Count structural alerts (PAINS-like)
    result.n_alerts = _count_structural_alerts(mol)

    return result


def _approximate_qed(mol) -> float:
    """
    Approximate QED when RDKit.Chem.QED fails.
    Simple desirability function approach.
    """
    mw = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    hbd = Lipinski.NumHDonors(mol)
    hba = Lipinski.NumHAcceptors(mol)
    tpsa = Descriptors.TPSA(mol)
    rot = Lipinski.NumRotatableBonds(mol)

    # Gaussian desirability for each property
    def desirability(val, mean, sigma):
        return math.exp(-0.5 * ((val - mean) / sigma) ** 2)

    d_mw = desirability(mw, 330, 120)
    d_logp = desirability(logp, 2.5, 1.5)
    d_hbd = desirability(hbd, 1.5, 1.5)
    d_hba = desirability(hba, 4.0, 2.5)
    d_tpsa = desirability(tpsa, 75, 40)
    d_rot = desirability(rot, 4.0, 3.0)

    # Geometric mean
    product = d_mw * d_logp * d_hbd * d_hba * d_tpsa * d_rot
    if product <= 0:
        return 0.0
    return product ** (1.0 / 6.0)


# ============================================================================
# STRUCTURAL ALERTS (PAINS-like)
# ============================================================================

_PAINS_SMARTS = [
    ("[#7]1~[#6](~[#16])~[#7]~[#6]~[#6]1", "rhodanine"),
    ("[#6]1(=[#8])~[#6](~[#7])~[#16]~[#6](~[#7])~[#7]1", "thiadiazine"),
    ("c1cc([N+](=O)[O-])cc([N+](=O)[O-])c1", "dinitrophenyl"),
    ("[#6](=[#8])([#6])[#8][#6](=[#8])[#6]", "acid_anhydride"),
    ("[CH]=[CH][C](=O)", "michael_acceptor_1"),
    ("[#6](=[#8])[#6](=[#8])", "1_2_diketone"),
]


def _count_structural_alerts(mol) -> int:
    """Count the number of PAINS-like structural alerts."""
    count = 0
    for smarts, _name in _PAINS_SMARTS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and mol.HasSubstructMatch(pattern):
            count += 1
    return count


# ============================================================================
# pLDDT CONFIDENCE FILTER
# ============================================================================

def filter_target_by_confidence(
    structure: "ProteinStructure",
    min_plddt: float = 70.0,
) -> Dict:
    """
    Assess whether an AlphaFold-predicted target structure is reliable
    enough for virtual screening.

    Args:
        structure: ProteinStructure from alphafold_interface
        min_plddt: Minimum pLDDT threshold

    Returns:
        Dict with reliability assessment
    """
    if not ALPHAFOLD_AVAILABLE:
        return {
            "reliable": False,
            "error": "alphafold_interface not available",
        }

    confidence = filter_by_plddt(structure, min_plddt=min_plddt)

    recommendation = ""
    if confidence["reliable"]:
        recommendation = "Structure suitable for docking-based virtual screening"
    elif confidence["confidence_ratio"] >= 0.5:
        recommendation = ("Partial confidence - limit docking to high-confidence "
                          "binding site residues only")
    else:
        recommendation = ("Low confidence structure - use experimental structure "
                          "or wait for better prediction")

    return {
        **confidence,
        "recommendation": recommendation,
    }


# ============================================================================
# HIT COMPOUND RANKING
# ============================================================================

def rank_by_binding_affinity(
    docking_scores: List[DockingScore],
    affinity_cutoff: float = -6.0,
) -> List[DockingScore]:
    """
    Filter and rank compounds by binding affinity from docking.

    Args:
        docking_scores: List of docking results
        affinity_cutoff: Minimum binding affinity (kcal/mol, more negative = stronger)

    Returns:
        Sorted list (best affinity first), filtered by cutoff
    """
    filtered = [d for d in docking_scores if d.binding_affinity <= affinity_cutoff]
    filtered.sort(key=lambda x: x.binding_affinity)
    return filtered


# ============================================================================
# COMPOSITE SCORING & SCREENING PIPELINE
# ============================================================================

def score_compound(
    smiles: str,
    name: str = "",
    docking_score: Optional[DockingScore] = None,
    weights: Optional[Dict[str, float]] = None,
) -> ScreeningHit:
    """
    Score a single compound using multi-criteria evaluation.

    Weights (default):
      - qed: 0.30 (drug-likeness)
      - affinity: 0.35 (binding strength)
      - admet: 0.25 (ADMET properties)
      - alerts: 0.10 (penalty for structural alerts)
    """
    if weights is None:
        weights = {
            "qed": 0.30,
            "affinity": 0.35,
            "admet": 0.25,
            "alerts": 0.10,
        }

    hit = ScreeningHit()
    hit.compound = CompoundEntry(smiles=smiles, name=name)
    hit.docking = docking_score
    flags = []

    # QED scoring
    qed_result = calculate_qed(smiles)
    hit.qed = qed_result
    qed_norm = qed_result.qed_score if qed_result else 0.0

    # ADMET scoring
    admet_norm = 0.5  # default if unavailable
    if ADMET_AVAILABLE:
        admet_profile = predict_admet(smiles, mol_name=name)
        hit.admet = admet_profile
        if not admet_profile.error:
            admet_norm = admet_profile.drug_likeness_score
            if admet_profile.oral_bioavailability == "unlikely":
                flags.append("poor_oral_bioavailability")
            if admet_profile.metabolic_stability and \
               admet_profile.metabolic_stability.classification == "low":
                flags.append("low_metabolic_stability")

    # Binding affinity normalization (map kcal/mol to 0-1)
    # Typical range: -12 (excellent) to 0 (no binding)
    affinity_norm = 0.0
    if docking_score and docking_score.binding_affinity < 0:
        # Normalize: -12 -> 1.0, -6 -> 0.5, 0 -> 0.0
        affinity_norm = min(1.0, max(0.0, -docking_score.binding_affinity / 12.0))

    # Structural alerts penalty
    alert_penalty = 0.0
    if qed_result and qed_result.n_alerts > 0:
        alert_penalty = min(1.0, qed_result.n_alerts * 0.3)
        if qed_result.n_alerts >= 2:
            flags.append("multiple_PAINS_alerts")

    # Composite score
    composite = (
        weights["qed"] * qed_norm
        + weights["affinity"] * affinity_norm
        + weights["admet"] * admet_norm
        - weights["alerts"] * alert_penalty
    )
    composite = max(0.0, min(1.0, composite))
    hit.composite_score = composite

    # Tier assignment
    if composite >= 0.7:
        hit.tier = "A"
    elif composite >= 0.4:
        hit.tier = "B"
    else:
        hit.tier = "C"

    hit.flags = flags
    return hit


def run_screening(
    compounds: List[CompoundEntry],
    docking_scores: Optional[Dict[str, DockingScore]] = None,
    target_structure: Optional["ProteinStructure"] = None,
    qed_cutoff: float = 0.3,
    affinity_cutoff: float = -5.0,
    max_hits: int = 100,
) -> ScreeningResult:
    """
    Run a full virtual screening pipeline.

    Pipeline:
    1. Target validation (pLDDT if AlphaFold)
    2. QED pre-filter (remove non-drug-like)
    3. Score all passing compounds
    4. Rank by composite score
    5. Return top hits

    Args:
        compounds: List of compounds to screen
        docking_scores: Optional mapping smiles -> DockingScore
        target_structure: Optional AlphaFold target for pLDDT check
        qed_cutoff: Minimum QED score to pass pre-filter
        affinity_cutoff: Minimum binding affinity (kcal/mol)
        max_hits: Maximum number of hits to return

    Returns:
        ScreeningResult
    """
    result = ScreeningResult()
    result.n_compounds = len(compounds)
    result.filters_applied = []

    if not RDKIT_AVAILABLE:
        result.error = "RDKit not available - cannot run screening"
        return result

    if docking_scores is None:
        docking_scores = {}

    # Step 1: Target confidence check
    if target_structure and ALPHAFOLD_AVAILABLE:
        confidence = filter_target_by_confidence(target_structure)
        result.target_plddt_reliable = confidence.get("reliable", False)
        result.filters_applied.append(
            f"pLDDT check: {'PASS' if result.target_plddt_reliable else 'WARNING'}"
        )

    # Step 2: QED pre-filter
    passing = []
    for entry in compounds:
        qed_result = calculate_qed(entry.smiles)
        if qed_result and qed_result.qed_score >= qed_cutoff:
            passing.append((entry, qed_result))

    result.filters_applied.append(
        f"QED pre-filter (>={qed_cutoff}): {len(passing)}/{len(compounds)} passed"
    )

    # Step 3: Score compounds
    hits = []
    for entry, _qed in passing:
        dock = docking_scores.get(entry.smiles, None)

        # Apply affinity filter if docking data exists
        if dock and dock.binding_affinity > affinity_cutoff:
            continue

        hit = score_compound(
            smiles=entry.smiles,
            name=entry.name,
            docking_score=dock,
        )
        hits.append(hit)

    # Step 4: Rank
    hits.sort(key=lambda h: h.composite_score, reverse=True)

    for i, hit in enumerate(hits):
        hit.rank = i + 1

    # Step 5: Limit results
    result.hits = hits[:max_hits]
    result.n_hits = len(result.hits)

    if docking_scores:
        result.filters_applied.append(
            f"Affinity filter (<={affinity_cutoff} kcal/mol)"
        )
    result.filters_applied.append(f"Top {max_hits} hits returned")

    return result


# ============================================================================
# UTILITY: SCREENING RESULT TO DICT
# ============================================================================

def screening_result_to_dict(result: ScreeningResult) -> Dict:
    """Convert ScreeningResult to a serializable dict."""
    hits_list = []
    for hit in result.hits:
        h = {
            "rank": hit.rank,
            "smiles": hit.compound.smiles,
            "name": hit.compound.name,
            "composite_score": round(hit.composite_score, 3),
            "tier": hit.tier,
            "flags": hit.flags,
        }
        if hit.qed:
            h["qed"] = round(hit.qed.qed_score, 3)
        if hit.docking:
            h["binding_affinity"] = round(hit.docking.binding_affinity, 2)
        if hit.admet:
            h["oral_bioavailability"] = hit.admet.oral_bioavailability
            h["drug_likeness"] = round(hit.admet.drug_likeness_score, 3)
        hits_list.append(h)

    return {
        "n_compounds": result.n_compounds,
        "n_hits": result.n_hits,
        "target_plddt_reliable": result.target_plddt_reliable,
        "filters_applied": result.filters_applied,
        "hits": hits_list,
        "error": result.error,
    }
