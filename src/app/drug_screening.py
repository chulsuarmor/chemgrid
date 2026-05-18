# drug_screening.py (v1.0 - Drug Screening Pipeline)
"""
ChemGrid: Drug Screening Pipeline
- pLDDT confidence filtering from AlphaFold predictions
- Hit compound ranking by binding affinity
- QED (Quantitative Estimate of Drug-likeness) scoring via RDKit
- Multi-criteria compound prioritization
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

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
# LogD pH CORRECTION (P1 fix — Mannhold 2009 JCIM + Henderson-Hasselbalch)
# ============================================================================

def calculate_logd(smiles: str, pH: float = 7.4) -> Optional[float]:
    """
    Estimate LogD at a given pH using LogP + Henderson-Hasselbalch correction.

    LogD = LogP - log10(1 + 10^(pKa - pH))  for acids (single ionizable group)
    LogD = LogP - log10(1 + 10^(pH - pKa))  for bases

    Note: This is a SIMPLIFIED single-group model.
    For multi-protic molecules use software such as ChemAxon MarvinSketch.

    References:
        Mannhold R. et al. J Chem Inf Model 2009, 49(3):747-776 (LogD review)
        Avdeef A. Absorption and Drug Development, 2003.
    """
    if not RDKIT_AVAILABLE:
        logger.warning("calculate_logd: RDKit not available for SMILES=%s", smiles)
        return None
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("calculate_logd: invalid SMILES (type=%s)", type(smiles).__name__)
        return None
    if not isinstance(pH, (int, float)):
        logger.warning("calculate_logd: pH must be numeric, got %s", type(pH).__name__)
        pH = 7.4  # default physiological pH

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("calculate_logd: MolFromSmiles failed for SMILES=%s", smiles)
        return None

    logp = Crippen.MolLogP(mol)  # Wildman-Crippen LogP (non-ionized form)

    # Heuristic pKa estimation from SMARTS functional groups
    # Acid: carboxylic acid pKa ~4.5, phenol pKa ~10.0
    # Base: amine (aliphatic) pKa ~10.5, amine (aromatic) pKa ~4.5
    pka_acid = None
    pka_base = None

    cooh_smarts = Chem.MolFromSmarts("[CX3](=O)[OX2H1]")    # Carboxylic acid
    phenol_smarts = Chem.MolFromSmarts("[cX3]1[cH]1[OX2H1]") # Phenol (simplified)
    ali_amine_smarts = Chem.MolFromSmarts("[NX3;H1,H2;!$(N-C=O)]")  # Aliphatic amine
    aro_amine_smarts = Chem.MolFromSmarts("[nX2,nX3]")       # Aromatic N (pyridine-like)

    if cooh_smarts is not None and mol.HasSubstructMatch(cooh_smarts):
        pka_acid = 4.5   # [MAGIC:4.5] carboxylic acid mean pKa (Avdeef 2003)
    elif phenol_smarts is not None and mol.HasSubstructMatch(phenol_smarts):
        pka_acid = 10.0  # [MAGIC:10.0] phenol mean pKa

    if ali_amine_smarts is not None and mol.HasSubstructMatch(ali_amine_smarts):
        pka_base = 10.5  # [MAGIC:10.5] aliphatic amine mean pKa
    elif aro_amine_smarts is not None and mol.HasSubstructMatch(aro_amine_smarts):
        pka_base = 4.5   # [MAGIC:4.5] aromatic N mean pKa

    logd = logp

    if pka_acid is not None:
        # Acid ionization reduces lipophilicity at pH > pKa
        logd -= math.log10(1.0 + 10.0 ** (pH - pka_acid))

    if pka_base is not None:
        # Base ionization reduces lipophilicity at pH < pKa
        logd -= math.log10(1.0 + 10.0 ** (pka_base - pH))

    logger.debug("calculate_logd: SMILES=%s LogP=%.2f LogD(pH%.1f)=%.2f", smiles, logp, pH, logd)
    return round(logd, 3)


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
        logger.warning("calculate_qed: RDKit not available, cannot compute QED for SMILES=%s", smiles)
        return None

    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("calculate_qed: invalid SMILES input (type=%s, value=%r)", type(smiles).__name__, smiles)
        return None

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("calculate_qed: failed to parse SMILES=%s", smiles)
        return None

    result = QEDResult()

    try:
        result.qed_score = RDKit_QED.qed(mol)
    except Exception as e:
        logger.warning("calculate_qed: RDKit QED failed for %s: %s, using approximation", smiles, e)
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
        logger.warning("filter_target_by_confidence: alphafold_interface not available")
        return {
            "reliable": False,
            "error": "alphafold_interface not available",
        }

    if structure is None:
        logger.warning("filter_target_by_confidence: structure is None")
        return {
            "reliable": False,
            "error": "No structure provided",
        }

    if not isinstance(min_plddt, (int, float)):
        logger.warning("filter_target_by_confidence: invalid min_plddt type=%s, using default 70.0", type(min_plddt).__name__)
        min_plddt = 70.0

    confidence = filter_by_plddt(structure, min_plddt=min_plddt)
    # Rule N: external function may return non-dict
    if not isinstance(confidence, dict):
        logger.warning("filter_by_plddt returned non-dict: type=%s", type(confidence).__name__)
        return {"reliable": False, "error": "filter_by_plddt returned invalid type"}

    recommendation = ""
    if confidence.get("reliable"):
        recommendation = "Structure suitable for docking-based virtual screening"
    elif confidence.get("confidence_ratio", 0.0) >= 0.5:
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
    if not isinstance(docking_scores, list):
        logger.warning("rank_by_binding_affinity: docking_scores is not a list (type=%s)", type(docking_scores).__name__)
        return []

    if not docking_scores:
        logger.warning("rank_by_binding_affinity: empty docking_scores list")
        return []

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
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("score_compound: invalid SMILES (type=%s, value=%r)", type(smiles).__name__, smiles)
        hit = ScreeningHit()
        hit.compound = CompoundEntry(smiles=str(smiles) if smiles else "", name=name)
        hit.flags = ["invalid_smiles"]
        hit.tier = "C"
        return hit

    if weights is None:
        weights = {
            "qed": 0.30,
            "affinity": 0.35,
            "admet": 0.25,
            "alerts": 0.10,
        }

    if not isinstance(weights, dict):
        logger.warning("score_compound: weights is not a dict (type=%s), using defaults", type(weights).__name__)
        weights = {"qed": 0.30, "affinity": 0.35, "admet": 0.25, "alerts": 0.10}

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

    if not isinstance(compounds, list):
        logger.warning("run_screening: compounds is not a list (type=%s)", type(compounds).__name__)
        result.error = "Invalid compounds input"
        return result

    result.n_compounds = len(compounds)
    result.filters_applied = []

    if not compounds:
        logger.warning("run_screening: empty compounds list")
        result.error = "No compounds provided"
        return result

    if not RDKIT_AVAILABLE:
        logger.warning("run_screening: RDKit not available — cannot run screening")
        result.error = "RDKit not available - cannot run screening"
        return result

    if docking_scores is not None and not isinstance(docking_scores, dict):
        logger.warning("run_screening: docking_scores is not a dict (type=%s), ignoring", type(docking_scores).__name__)
        docking_scores = {}

    if docking_scores is None:
        docking_scores = {}

    # Step 1: Target confidence check
    if target_structure and ALPHAFOLD_AVAILABLE:
        confidence = filter_target_by_confidence(target_structure)
        # Rule N: isinstance guard on external function return
        if not isinstance(confidence, dict):
            logger.warning("filter_target_by_confidence returned non-dict: type=%s", type(confidence).__name__)
            confidence = {}
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
        # Rule N: isinstance guard for docking_scores
        if not isinstance(docking_scores, dict): docking_scores = {}
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
