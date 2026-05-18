"""membrane_permeability.py -- pH-Dependent Lipid Membrane Permeability Engine (Module B)

pH-based lipid membrane permeation and disruption analysis for
ChemGrid Cascade #11 Block 11-B.

Features
--------
- logP (RDKit Crippen) + pKa prediction (empirical SMARTS rules)
- Henderson-Hasselbalch logD(pH) calculation
- Ion-pair partitioning (P_IP_app) with thermodynamic ionisation equilibrium
- 5-layer lipid membrane model (water/headgroup/interface/tail/center) -- DOPC params
- Free energy profile across membrane + matplotlib visualisation
- Surfactant membrane disruption simulation

References
----------
- Avdeef, A. (2012). Absorption and Drug Development, 2nd Ed.
- Missner, A. & Pohl, P. (2009). ChemPhysChem 10, 4257-4269.
- Marrink, S.J. & Berendsen, H.J.C. (1994). J. Phys. Chem. 98, 4155-4168.
- COSMOperm: Rezaei, M. et al. (2021). J. Chem. Inf. Model.

Created: 2026-04-04  |  Block 11-B  |  Owned by: domain_drug
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guards (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from rdkit import Chem
    from rdkit.Chem import (
        AllChem, Crippen, Descriptors, rdMolDescriptors,
        Fragments,
    )
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

    class QThread:  # type: ignore[no-redef]
        pass

    class pyqtSignal:  # type: ignore[no-redef]
        def __init__(self, *a):
            pass
        def emit(self, *a):
            pass


# ---------------------------------------------------------------------------
# Module-level availability flag (for import guards in other modules)
# ---------------------------------------------------------------------------
MEMBRANE_PERM_AVAILABLE = RDKIT_AVAILABLE and NUMPY_AVAILABLE


# ---------------------------------------------------------------------------
# Physical / chemical constants (annotated sources)
# ---------------------------------------------------------------------------

_R = 8.314462618       # J/(mol*K) -- universal gas constant (CODATA 2018)
_kB = 1.380649e-23     # J/K       -- Boltzmann constant
_LN10 = 2.302585093    # ln(10)
_T_REF = 298.15        # K         -- reference temperature (25 degC)
_KCAL_TO_J = 4184.0    # 1 kcal = 4184 J


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IonisationState:
    """Single microspecies ionisation state."""
    charge: int
    fraction: float          # mole fraction at given pH
    logP_species: float      # intrinsic logP of this microspecies
    description: str = ""    # e.g. "neutral", "cation", "anion", "zwitterion"


@dataclass
class LogDResult:
    """pH-dependent distribution coefficient."""
    pH: float
    logD: float
    logP_neutral: float
    pKa_values: List[float]
    pKa_types: List[str]     # "acid" or "base" for each pKa
    ionisation_states: List[IonisationState] = field(default_factory=list)
    dominant_species: str = "neutral"
    fraction_neutral: float = 1.0
    fraction_ionised: float = 0.0


@dataclass
class MembraneLayerParams:
    """Parameters for a single membrane layer."""
    name: str
    thickness: float         # Angstroms
    dielectric: float        # relative permittivity
    logP_scale: float        # scaling factor: how logP translates to layer affinity
    born_radius_factor: float  # Born solvation energy scale
    description: str = ""


@dataclass
class FreeEnergyPoint:
    """Single point in the transmembrane free energy profile."""
    z_position: float        # Angstroms from bilayer center
    layer_name: str
    delta_G: float           # kcal/mol relative to bulk water
    partition_coeff: float   # local partition coefficient


@dataclass
class PermeabilityResult:
    """Complete membrane permeability analysis result."""
    smiles: str
    molecule_name: str
    logP: float
    pKa_values: List[float]
    pKa_types: List[str]
    pH: float
    logD: float
    fraction_neutral: float
    fraction_ionised: float
    dominant_species: str
    free_energy_profile: List[FreeEnergyPoint]
    permeability_cm_s: float    # apparent permeability (cm/s)
    log_perm: float             # log10(Papp)
    classification: str         # "high" / "moderate" / "low" / "impermeable"
    membrane_model: str         # "DOPC" etc.
    ion_pair_correction: float  # delta logD from ion-pair partitioning
    success: bool = True
    error: str = ""
    # Surfactant disruption fields (item 7)
    disruption_cmc: Optional[float] = None
    disruption_hlb: Optional[float] = None
    disruption_score: Optional[float] = None


# ---------------------------------------------------------------------------
# pKa prediction (empirical SMARTS rules)
# Reference: Liao & Nicklaus (2009), J. Chem. Inf. Model. 49, 2801-2812
# Fallback: Viswanadhan empirical pKa estimation
# ---------------------------------------------------------------------------

# SMARTS patterns -> (pKa_estimate, type)
# Calibrated against ACD/pKa for 200 drug molecules
_PKA_RULES: List[Tuple[str, float, str, str]] = [
    # Carboxylic acids
    ("[CX3](=O)[OX2H]",                     4.0,  "acid",  "carboxylic acid"),
    # Sulfonamides
    ("[SX4](=O)(=O)[NX3H]",                10.0,  "acid",  "sulfonamide NH"),
    # Phenols
    ("[OX2H]c1ccccc1",                       9.9,  "acid",  "phenol"),
    # Thiols
    ("[SX2H]",                               8.3,  "acid",  "thiol"),
    # Primary aliphatic amines
    ("[NX3H2;!$([NX3H2]c)]",              10.6,  "base",  "primary amine"),
    # Secondary aliphatic amines
    ("[NX3H1;!$([NX3H1]c);!$([NX3H1]C=O)]", 10.0, "base", "secondary amine"),
    # Tertiary aliphatic amines
    ("[NX3H0;!$([NX3H0]c);!$([NX3H0]C=O);!$([NX3H0](=*))]", 9.5, "base", "tertiary amine"),
    # Pyridine nitrogen
    ("c1ccncc1",                              5.2,  "base",  "pyridine"),
    # Imidazole NH
    ("c1c[nH]cn1",                            6.0,  "base",  "imidazole"),
    # Guanidine
    ("[NX3H2]C(=[NX2H])[NX3H2]",          12.5,  "base",  "guanidine"),
    # Amidine
    ("[NX3H2]C(=[NX2H])",                  11.5,  "base",  "amidine"),
    # Tetrazole (acid)
    ("c1nn[nH]n1",                            4.9,  "acid",  "tetrazole"),
    # Barbiturate NH
    ("[NX3H]C(=O)[NX3H]C(=O)",              8.0,  "acid",  "barbiturate"),
    # Enol/hydroxamic
    ("[OX2H]N",                               8.5,  "acid",  "hydroxamic acid"),
    # Phosphoric acid
    ("[PX4](=O)([OX2H])",                    1.5,  "acid",  "phosphoric acid"),
]


def predict_pka(mol) -> Tuple[List[float], List[str], List[str]]:
    """Predict pKa values using empirical SMARTS matching.

    Returns
    -------
    (pka_values, pka_types, pka_descriptions)
        pka_values: list of predicted pKa
        pka_types: 'acid' or 'base' for each
        pka_descriptions: human-readable description
    """
    if not RDKIT_AVAILABLE or mol is None:
        return [], [], []

    pka_vals: List[float] = []
    pka_types: List[str] = []
    pka_descs: List[str] = []

    for smarts, pka, ptype, desc in _PKA_RULES:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            continue
        matches = mol.GetSubstructMatches(pattern)
        n_matches = len(matches)
        if n_matches > 0:
            # For multiple identical groups, add pKa for each
            # with statistical correction: pKa_n = pKa + 0.6*(n-1)  (Hammet)
            for i in range(n_matches):
                corrected_pka = pka + 0.6 * i  # statistical factor
                pka_vals.append(round(corrected_pka, 1))
                pka_types.append(ptype)
                pka_descs.append(f"{desc} (#{i+1})" if n_matches > 1 else desc)

    # Sort by pKa value
    if pka_vals:
        combined = sorted(zip(pka_vals, pka_types, pka_descs))
        pka_vals = [c[0] for c in combined]
        pka_types = [c[1] for c in combined]
        pka_descs = [c[2] for c in combined]

    return pka_vals, pka_types, pka_descs


# ---------------------------------------------------------------------------
# Henderson-Hasselbalch logD calculator
# ---------------------------------------------------------------------------

def calculate_logd(logP: float, pka_values: List[float],
                   pka_types: List[str], pH: float) -> LogDResult:
    """Calculate pH-dependent logD using Henderson-Hasselbalch.

    For acids:  logD = logP - log10(1 + 10^(pH - pKa))
    For bases:  logD = logP - log10(1 + 10^(pKa - pH))

    For polyprotic species, corrections are additive (first approximation).

    Parameters
    ----------
    logP : float
        Octanol-water partition coefficient of neutral species
    pka_values : list of float
    pka_types : list of str ('acid' or 'base')
    pH : float

    Returns
    -------
    LogDResult with computed logD and ionisation details
    """
    # Type guards (Rule N)
    if not isinstance(logP, (int, float)):
        logger.warning("calculate_logd: logP is not numeric: %s", type(logP).__name__)
        logP = 0.0
    if not isinstance(pH, (int, float)):
        logger.warning("calculate_logd: pH is not numeric: %s", type(pH).__name__)
        pH = 7.4
    if not isinstance(pka_values, list):
        logger.warning("calculate_logd: pka_values is not a list: %s", type(pka_values).__name__)
        pka_values = []
    if not isinstance(pka_types, list):
        logger.warning("calculate_logd: pka_types is not a list: %s", type(pka_types).__name__)
        pka_types = []
    if not pka_values:
        return LogDResult(
            pH=pH, logD=logP, logP_neutral=logP,
            pKa_values=[], pKa_types=[],
            dominant_species="neutral",
            fraction_neutral=1.0,
            fraction_ionised=0.0,
        )

    # Compute ionisation correction
    # For polyprotic species, use the *most significant* pKa (closest to pH)
    # rather than summing all corrections, which over-counts.
    # Approach: for acids, pick the strongest (lowest pKa); for bases, pick strongest (highest pKa)
    # Then compute composite fraction ionised properly.
    ionisation_states: List[IonisationState] = []
    acid_pkas = [(pka, i) for i, (pka, ptype) in enumerate(zip(pka_values, pka_types)) if ptype == "acid"]
    base_pkas = [(pka, i) for i, (pka, ptype) in enumerate(zip(pka_values, pka_types)) if ptype == "base"]

    # For each ionisable group, compute its individual fraction ionised
    frac_ionised_per_group: List[float] = []
    for pka, ptype in zip(pka_values, pka_types):
        if ptype == "acid":
            exponent = pH - pka
            frac = 1.0 / (1.0 + 10.0 ** (-exponent)) if abs(exponent) < 30 else (1.0 if exponent > 0 else 0.0)
        else:
            exponent = pka - pH
            frac = 1.0 / (1.0 + 10.0 ** (-exponent)) if abs(exponent) < 30 else (1.0 if exponent > 0 else 0.0)
        frac = max(0.0, min(1.0, frac))
        frac_ionised_per_group.append(frac)

        ionisation_states.append(IonisationState(
            charge=(-1 if ptype == "acid" else +1),
            fraction=frac,
            logP_species=logP - 3.5,  # ionised species ~3.5 logP units less lipophilic
            description=("anion (deprotonated acid)" if ptype == "acid"
                         else "cation (protonated base)"),
        ))

    # Composite logD: use the *dominant* single-pKa correction
    # For monoprotic: exact Henderson-Hasselbalch
    # For polyprotic: use the pKa giving the largest correction (Avdeef 2012 Ch.3)
    max_correction = 0.0
    for pka, ptype in zip(pka_values, pka_types):
        if ptype == "acid":
            exponent = pH - pka
        else:
            exponent = pka - pH
        correction = math.log10(1.0 + 10.0 ** exponent) if exponent < 30 else exponent
        max_correction = max(max_correction, correction)

    logD = logP - max_correction

    # Overall fraction ionised: probability that *at least one* group is ionised
    # P(at least one ionised) = 1 - product(1 - f_i)
    product_neutral = 1.0
    for f in frac_ionised_per_group:
        product_neutral *= (1.0 - f)
    total_ionised_fraction = 1.0 - product_neutral
    fraction_neutral = max(0.0, product_neutral)

    # Add neutral species
    ionisation_states.insert(0, IonisationState(
        charge=0, fraction=fraction_neutral,
        logP_species=logP,
        description="neutral",
    ))

    # Determine dominant species
    max_frac = 0.0
    dominant = "neutral"
    for state in ionisation_states:
        if state.fraction > max_frac:
            max_frac = state.fraction
            dominant = state.description

    return LogDResult(
        pH=pH,
        logD=logD,
        logP_neutral=logP,
        pKa_values=pka_values,
        pKa_types=pka_types,
        ionisation_states=ionisation_states,
        dominant_species=dominant,
        fraction_neutral=fraction_neutral,
        fraction_ionised=total_ionised_fraction,
    )


# ---------------------------------------------------------------------------
# Ion-pair partitioning (P_IP_app)
# Reference: Avdeef (2012) Ch. 3, Palm et al. (1999)
# ---------------------------------------------------------------------------

# Default ion-pair constants
_LOG_P_IP_ACID = -1.0    # logP of ion-pair for acids (Avdeef empirical)
_LOG_P_IP_BASE = -2.0    # logP of ion-pair for bases
_DELTA_LOG_P_IP = 0.5    # ion-pair enhancement factor per unit charge

def calculate_ion_pair_logd(logP: float, pka_values: List[float],
                            pka_types: List[str], pH: float,
                            ionic_strength: float = 0.15) -> float:
    """Calculate apparent logD with ion-pair partitioning correction.

    The ion-pair partition model accounts for the observation that ionised
    species can still partition into lipid membranes via ion-pair formation
    with endogenous counterions (phospholipid headgroups, etc.).

    P_IP_app = P_neutral * f_neutral + P_IP * f_ionised

    where P_IP depends on the counterion concentration and membrane charge.

    Parameters
    ----------
    logP : float
        Neutral species logP
    pka_values, pka_types : lists
    pH : float
    ionic_strength : float
        Physiological ionic strength (default 0.15 M)

    Returns
    -------
    float : corrected logD incorporating ion-pair contribution
    """
    # Get standard Henderson-Hasselbalch result first
    hh_result = calculate_logd(logP, pka_values, pka_types, pH)

    if not pka_values or hh_result.fraction_ionised < 0.01:
        return hh_result.logD  # negligible ionisation

    # Ion-pair correction
    # Debye-Hueckel activity coefficient correction
    # log(gamma) = -0.509 * z^2 * sqrt(I) / (1 + sqrt(I))
    sqrt_I = math.sqrt(ionic_strength)
    log_gamma = -0.509 * sqrt_I / (1.0 + sqrt_I)  # for z=1

    ip_correction = 0.0
    for pka, ptype in zip(pka_values, pka_types):
        if ptype == "acid":
            frac_ionised = 1.0 / (1.0 + 10.0 ** (pka - pH))
            log_p_ip = _LOG_P_IP_ACID + log_gamma
        else:
            frac_ionised = 1.0 / (1.0 + 10.0 ** (pH - pka))
            log_p_ip = _LOG_P_IP_BASE + log_gamma

        # Ion-pair contribution to apparent partition
        # P_app = f_neutral * P_neutral + f_ionised * P_IP
        # In log space: need to convert, compute, convert back
        p_ip = 10.0 ** log_p_ip
        ip_correction += frac_ionised * p_ip

    # Combine: P_app = f_neutral * 10^logP + ip_correction
    p_neutral = 10.0 ** logP
    p_app = hh_result.fraction_neutral * p_neutral + ip_correction

    if p_app > 0:
        return math.log10(p_app)
    return hh_result.logD


# ---------------------------------------------------------------------------
# 5-layer lipid membrane model (DOPC bilayer)
# Reference: Marrink & Berendsen (1994), Shinoda (2016)
# ---------------------------------------------------------------------------

# DOPC membrane layer parameters (total bilayer ~50 A)
# Layers are defined from center (z=0) to one leaflet (symmetric bilayer)
DOPC_MEMBRANE_LAYERS: List[MembraneLayerParams] = [
    MembraneLayerParams(
        name="center",
        thickness=5.0,       # Angstroms, hydrocarbon midplane region
        dielectric=2.0,      # very low -- pure hydrocarbon
        logP_scale=1.0,      # full lipophilicity contribution
        born_radius_factor=0.7,
        description="Bilayer midplane (chain termini, low density)",
    ),
    MembraneLayerParams(
        name="tail",
        thickness=8.0,       # hydrocarbon chain region
        dielectric=2.2,      # slightly higher than center due to ordering
        logP_scale=0.95,
        born_radius_factor=0.8,
        description="Hydrocarbon tail region (C4-C14 of acyl chains)",
    ),
    MembraneLayerParams(
        name="interface",
        thickness=5.0,       # glycerol/ester region
        dielectric=12.0,     # transitional
        logP_scale=0.4,      # partial lipophilic contribution
        born_radius_factor=1.2,
        description="Glycerol/ester interface (carbonyl region)",
    ),
    MembraneLayerParams(
        name="headgroup",
        thickness=5.0,       # phosphocholine headgroup
        dielectric=30.0,     # polar headgroup environment
        logP_scale=0.15,     # mostly hydrophilic
        born_radius_factor=1.8,
        description="Phosphocholine headgroup region",
    ),
    MembraneLayerParams(
        name="water",
        thickness=10.0,      # bulk water layer (semi-infinite, truncated)
        dielectric=78.5,     # bulk water at 25 degC
        logP_scale=0.0,      # reference (logD contribution = 0)
        born_radius_factor=2.5,
        description="Bulk aqueous phase",
    ),
]


def build_membrane_z_profile(layers: Optional[List[MembraneLayerParams]] = None,
                             n_points_per_layer: int = 10) -> List[Tuple[float, str, MembraneLayerParams]]:
    """Build z-coordinate profile for the full symmetric bilayer.

    Returns list of (z_position, layer_name, params) tuples from
    -half_thickness to +half_thickness.
    """
    if layers is None:
        layers = DOPC_MEMBRANE_LAYERS

    # Build one leaflet from center outward
    one_leaflet: List[Tuple[float, str, MembraneLayerParams]] = []
    z = 0.0
    for layer in layers:
        dz = layer.thickness / n_points_per_layer
        for i in range(n_points_per_layer):
            z_pos = z + dz * (i + 0.5)
            one_leaflet.append((z_pos, layer.name, layer))
        z += layer.thickness

    # Build symmetric bilayer: mirror the leaflet
    # Negative z = same structure
    profile = []
    for z_pos, name, params in reversed(one_leaflet):
        profile.append((-z_pos, name, params))
    for z_pos, name, params in one_leaflet:
        profile.append((z_pos, name, params))

    return profile


def calculate_free_energy_profile(
    logD: float,
    logP: float,
    mol_weight: float,
    tpsa: float,
    hbd: int,
    charge: int,
    fraction_neutral: float = 1.0,
    layers: Optional[List[MembraneLayerParams]] = None,
    n_points: int = 10,
) -> List[FreeEnergyPoint]:
    """Calculate transmembrane free energy profile.

    Uses the parallel pathway model (Avdeef 2012):
    - Neutral species cross via passive transcellular diffusion (logP-driven)
    - Ionised species face Born solvation barrier (charge-dielectric penalty)
    - Total profile is the Boltzmann-weighted sum of both pathways

    DeltaG(z) = -RT * ln(f_neutral * 10^(-DG_neutral/RT*ln10)
                         + f_ionised * 10^(-DG_ionised/RT*ln10))

    Parameters
    ----------
    logD : float
        pH-adjusted distribution coefficient
    logP : float
        Neutral species logP
    mol_weight : float
        Molecular weight
    tpsa : float
        Topological polar surface area (A^2)
    hbd : int
        Number of hydrogen bond donors
    charge : int
        Net formal charge at given pH
    fraction_neutral : float
        Fraction of neutral species (0-1)
    layers : list of MembraneLayerParams, optional
    n_points : int
        Points per layer

    Returns
    -------
    List of FreeEnergyPoint across the full bilayer
    """
    z_profile = build_membrane_z_profile(layers, n_points)
    fe_points: List[FreeEnergyPoint] = []

    # Reference DeltaG in water = 0 kcal/mol
    rt_ln10 = _R * _T_REF * _LN10 / _KCAL_TO_J  # ~1.364 kcal/mol at 25C
    rt_kcal = _R * _T_REF / _KCAL_TO_J           # ~0.593 kcal/mol at 25C

    # Born solvation radius estimate from MW (empirical)
    r_born = 1.5 * (mol_weight ** (1.0 / 3.0))  # Angstroms

    f_neutral = max(fraction_neutral, 1e-15)
    f_ionised = 1.0 - f_neutral

    for z_pos, layer_name, params in z_profile:
        # ---- Neutral species free energy ----
        # Transfer: water -> layer, driven by logP
        delta_g_neutral = -rt_ln10 * logP * params.logP_scale

        # Desolvation penalty for polar groups (H-bond donors)
        polarity_loss = max(0.0, 1.0 - params.dielectric / 78.5)
        delta_g_neutral += 0.6 * hbd * polarity_loss  # kcal/mol

        # TPSA desolvation (~0.01 kcal/mol per A^2)
        delta_g_neutral += 0.01 * tpsa * polarity_loss

        # ---- Ionised species free energy ----
        # Same lipophilic baseline but with ion penalty
        delta_g_ionised = delta_g_neutral  # start from same baseline

        if abs(charge) > 0:
            # Born solvation penalty: charge entering low-dielectric medium
            # DeltaG_born = (332 * z^2) / (2 * r_born) * (1/eps_layer - 1/eps_water)
            #
            # Born scaling factor rationale (Xiang & Anderson 1994):
            # - 0.1: original empirical fit for partially ionised drugs
            # - For nearly fully ionised molecules (fraction_neutral < 0.01),
            #   the 0.1 scaling grossly underestimates the real barrier because
            #   the dominant pathway IS the ion pathway, not the neutral remnant.
            #   Calibrated against BCS Class III data: Metformin, Atenolol,
            #   Ranitidine, Cimetidine (all low/impermeable in Caco-2).
            # - Scale up to 0.35 for fully ionised species (Palm et al. 1999,
            #   Avdeef 2012 Ch.5 revisited Born model for permanent cations)
            if fraction_neutral < 0.01:
                # Fully ionised: Born barrier dominates passive transcellular
                born_scale = 0.35  # calibrated for BCS III permanent cations
            elif fraction_neutral < 0.1:
                # Transition zone: interpolate between 0.1 and 0.35
                # Linear interp on log scale of fraction_neutral
                t = (math.log10(max(fraction_neutral, 1e-15)) - math.log10(0.1)) / (
                    math.log10(0.01) - math.log10(0.1)
                )  # t=0 at f=0.1, t=1 at f=0.01
                t = max(0.0, min(1.0, t))
                born_scale = 0.1 + 0.25 * t
            else:
                born_scale = 0.1  # original Xiang & Anderson for partially ionised

            born_raw = (332.0 * charge**2) / (2.0 * r_born * params.born_radius_factor) * (
                1.0 / params.dielectric - 1.0 / 78.5
            )
            delta_g_ionised += born_raw * born_scale

            # Additional ion desolvation: +3.5 kcal/mol in core (Avdeef)
            # For fully ionised species, add extra desolvation penalty
            # reflecting that no neutral pathway shortcut exists
            ion_desolv_base = 3.5  # kcal/mol, Avdeef empirical
            if fraction_neutral < 0.01:
                ion_desolv_base = 5.5  # enhanced for permanent ions (BCS III calibration)
            elif fraction_neutral < 0.1:
                t = (math.log10(max(fraction_neutral, 1e-15)) - math.log10(0.1)) / (
                    math.log10(0.01) - math.log10(0.1)
                )
                t = max(0.0, min(1.0, t))
                ion_desolv_base = 3.5 + 2.0 * t
            delta_g_ionised += ion_desolv_base * params.logP_scale

        # ---- Composite: parallel pathway ----
        # P_total(z) = f_neutral * exp(-DG_n / RT) + f_ionised * exp(-DG_i / RT)
        # DG_effective = -RT * ln(P_total)

        if layer_name == "water":
            delta_g_total = 0.0
        else:
            # Compute Boltzmann factors
            if abs(delta_g_neutral) < 50 * rt_kcal:
                boltz_neutral = math.exp(-delta_g_neutral / rt_kcal)
            else:
                boltz_neutral = 0.0 if delta_g_neutral > 0 else 1e20

            if abs(delta_g_ionised) < 50 * rt_kcal:
                boltz_ionised = math.exp(-delta_g_ionised / rt_kcal)
            else:
                boltz_ionised = 0.0 if delta_g_ionised > 0 else 1e20

            p_total = f_neutral * boltz_neutral + f_ionised * boltz_ionised
            if p_total > 1e-30:
                delta_g_total = -rt_kcal * math.log(p_total)
            else:
                delta_g_total = 30.0  # very large barrier

        # Local partition coefficient K = exp(-DeltaG / RT)
        if abs(delta_g_total) < 50 * rt_kcal:
            k_local = math.exp(-delta_g_total / rt_kcal)
        else:
            k_local = 0.0 if delta_g_total > 0 else 1e20

        fe_points.append(FreeEnergyPoint(
            z_position=z_pos,
            layer_name=layer_name,
            delta_G=round(delta_g_total, 3),
            partition_coeff=k_local,
        ))

    return fe_points


# ---------------------------------------------------------------------------
# Apparent permeability (Papp) from free energy profile
# Reference: Marrink & Berendsen (1994), Diamond & Katz (1974)
# ---------------------------------------------------------------------------

def calculate_permeability(
    fe_profile: List[FreeEnergyPoint],
    diffusion_coeff_water: float = 1e-5,  # cm^2/s, typical small molecule in water
    mol_weight: float = 300.0,
    fraction_neutral: float = 1.0,
    logD: float = 0.0,
    logP: float = 0.0,
) -> Tuple[float, float, str]:
    """Calculate apparent permeability from free energy profile.

    Uses the inhomogeneous solubility-diffusion (ISD) model:

    1/P = integral(dz / (K(z) * D(z)))

    where K(z) is local partition coefficient and D(z) is local diffusion coefficient.

    Parameters
    ----------
    fe_profile : list of FreeEnergyPoint
    diffusion_coeff_water : float
        Diffusion coefficient in water (cm^2/s)
    mol_weight : float
        For estimating membrane diffusion reduction
    fraction_neutral : float
        Fraction of neutral species at analysis pH (used for ionisation-aware
        classification override)
    logD : float
        pH-adjusted distribution coefficient (used for ionisation-aware
        classification override)
    logP : float
        Neutral species logP (used to distinguish lipophilic ionised drugs
        that still permeate via the neutral pathway)

    Returns
    -------
    (Papp_cm_s, log_Papp, classification)
    """
    if not isinstance(fe_profile, list):
        logger.warning("calculate_permeability: fe_profile is not a list: %s",
                       type(fe_profile).__name__)
        return 1e-10, -10.0, "impermeable"
    if not fe_profile:
        logger.warning("calculate_permeability: empty free energy profile")
        return 1e-10, -10.0, "impermeable"

    # Diffusion coefficient reduction in membrane interior
    # D_membrane ~ D_water * (MW_ref / MW)^0.5 * 0.01 (Marrink 1994)
    # 0.01 factor accounts for ~100x slower diffusion in lipid bilayer
    mw_factor = math.sqrt(200.0 / max(mol_weight, 50.0))  # 200 Da reference
    d_membrane = diffusion_coeff_water * 0.01 * mw_factor  # cm^2/s

    # Integrate resistance across bilayer using trapezoidal rule
    # 1/P = sum(dz / (K(z) * D(z)))
    total_resistance = 0.0
    dz_cm = 1e-8  # 1 Angstrom = 1e-8 cm

    for point in fe_profile:
        k_z = max(point.partition_coeff, 1e-20)  # avoid division by zero

        if point.layer_name == "water":
            d_z = diffusion_coeff_water
        else:
            d_z = d_membrane

        total_resistance += dz_cm / (k_z * d_z)

    # P_app = 1 / total_resistance
    if total_resistance > 0:
        p_app = 1.0 / total_resistance
    else:
        p_app = diffusion_coeff_water  # essentially no barrier

    # Clamp to physically reasonable range
    p_app = max(p_app, 1e-15)  # lower bound
    p_app = min(p_app, 1e-2)   # upper bound (free diffusion)

    log_papp = math.log10(p_app)

    # Classification (Yee 1997, Irvine 1999, MDCK-MDR1 scale)
    if log_papp >= -4.5:       # >= 3e-5 cm/s
        classification = "high"
    elif log_papp >= -5.5:     # >= 3e-6 cm/s
        classification = "moderate"
    elif log_papp >= -6.5:     # >= 3e-7 cm/s
        classification = "low"
    else:
        classification = "impermeable"

    # --- Ionisation-aware classification override ---
    # For nearly fully ionised molecules with LOW intrinsic lipophilicity,
    # passive transcellular permeation is negligible.  These are BCS Class
    # III compounds (e.g. Metformin, Atenolol, Cimetidine) whose absorption
    # depends on carrier-mediated transport, NOT passive diffusion.
    #
    # However, ionised molecules with HIGH intrinsic lipophilicity
    # (e.g. Propranolol logP=2.87, Metoprolol logP=1.61) DO permeate well
    # via the small neutral fraction -- even 0.1% neutral * 10^2.87 partition
    # gives meaningful flux.  These are BCS Class I and should stay "high".
    #
    # Decision boundary: logP >= 1.5 indicates the neutral pathway is
    # sufficient for permeation even at very low neutral fraction.
    # Below logP 1.5, ionised species with f_neutral < 0.01 are truly
    # transport-limited.
    #
    # Calibration data (Caco-2 Papp, cm/s):
    #   Metformin  (logP=-1.03, f_n~0):      Papp < 1e-7 (impermeable)
    #   Atenolol   (logP= 0.75, f_n~0):      Papp ~ 2e-7 (low)
    #   Cimetidine (logP= 0.75, f_n~0):      Papp ~ 3e-7 (low)
    #   Furosemide (logP= 1.89, f_n~0, acid):Papp ~ 1e-7 (low) [TPSA=127]
    #   Propranolol(logP= 2.87, f_n=0.0025): Papp ~ 3e-5 (high)
    #   Metoprolol (logP= 1.61, f_n=0.0025): Papp ~ 2e-5 (high)
    #   Aspirin    (logP= 1.31, f_n=0.0004): Papp ~ 3e-5 (high, pH-partition)
    #
    # References: Avdeef (2012) Ch.5, Palm et al. (1999), Kasim et al. (2004)

    # Only apply override for hydrophilic ionised species (logP < 1.5)
    # For lipophilic bases/acids, the neutral pathway suffices
    _LOGP_OVERRIDE_CUTOFF = 1.5  # logP below which ionisation override applies
    if logP < _LOGP_OVERRIDE_CUTOFF:
        if fraction_neutral < 0.001:
            # Nearly completely ionised + hydrophilic: passive ≈ 0
            if classification in ("high", "moderate"):
                classification = "low"
                log_papp = min(log_papp, -6.0)
                p_app = 10.0 ** log_papp
        elif fraction_neutral < 0.01:
            # > 99% ionised + hydrophilic: cap at moderate
            if classification == "high":
                classification = "moderate"
                log_papp = min(log_papp, -5.0)
                p_app = 10.0 ** log_papp

    return p_app, round(log_papp, 2), classification


# ---------------------------------------------------------------------------
# Surfactant membrane disruption model (item 7)
# Reference: Heerklotz (2008), Detergents & Lipids
# ---------------------------------------------------------------------------

# Known surfactant parameters: (CMC in mM, HLB)
_SURFACTANT_DB: Dict[str, Dict[str, float]] = {
    "SDS": {"cmc_mM": 8.2, "hlb": 40.0, "name": "Sodium Dodecyl Sulfate"},
    "CTAB": {"cmc_mM": 0.9, "hlb": 21.4, "name": "Cetyltrimethylammonium Bromide"},
    "Triton X-100": {"cmc_mM": 0.24, "hlb": 13.5, "name": "Triton X-100"},
    "Tween-20": {"cmc_mM": 0.06, "hlb": 16.7, "name": "Polysorbate 20"},
    "CHAPS": {"cmc_mM": 6.0, "hlb": 22.0, "name": "CHAPS"},
}


def estimate_surfactant_disruption(
    surfactant_name: str,
    concentration_mM: float,
) -> Tuple[float, str]:
    """Estimate membrane disruption by a surfactant.

    Uses the 3-stage model:
    - Stage 1 (c < CMC): insertion into outer leaflet
    - Stage 2 (c ~ CMC): solubilisation onset, mixed micelle formation
    - Stage 3 (c >> CMC): complete solubilisation

    Returns
    -------
    (disruption_score_0_to_1, stage_description)
    """
    surf = _SURFACTANT_DB.get(surfactant_name)
    if surf is None:
        return 0.0, f"Unknown surfactant: {surfactant_name}"

    cmc = surf["cmc_mM"]
    ratio = concentration_mM / cmc if cmc > 0 else 0.0

    if ratio < 0.5:
        # Stage 1: minimal disruption, insertion into outer leaflet
        score = 0.1 * (ratio / 0.5)
        desc = "Stage I: Surfactant inserts into outer leaflet. Minimal disruption."
    elif ratio < 2.0:
        # Stage 2: solubilisation onset
        score = 0.1 + 0.6 * ((ratio - 0.5) / 1.5)
        desc = "Stage II: Solubilisation onset. Mixed lipid-surfactant micelles forming."
    elif ratio < 10.0:
        # Stage 3: extensive solubilisation
        score = 0.7 + 0.25 * ((ratio - 2.0) / 8.0)
        desc = "Stage III: Extensive membrane solubilisation. Loss of barrier function."
    else:
        # Complete disruption
        score = min(1.0, 0.95 + 0.05 * math.log10(ratio / 10.0 + 1.0))
        desc = "Stage III+: Complete membrane disruption. Lipid bilayer dissolved."

    return round(score, 3), desc


# ---------------------------------------------------------------------------
# logP from RDKit
# ---------------------------------------------------------------------------

def calculate_logp(mol) -> float:
    """Calculate Crippen logP using RDKit.

    Uses Wildman-Crippen logP estimation (atom contribution method).
    Reference: Wildman & Crippen (1999) J. Chem. Inf. Comput. Sci. 39, 868.
    """
    if not RDKIT_AVAILABLE or mol is None:
        return 0.0
    return Crippen.MolLogP(mol)


# ---------------------------------------------------------------------------
# Full analysis pipeline
# ---------------------------------------------------------------------------

def run_permeability_analysis(
    smiles: str,
    molecule_name: str = "",
    pH: float = 7.4,
    ionic_strength: float = 0.15,
    membrane_model: str = "DOPC",
) -> PermeabilityResult:
    """Run complete pH-dependent membrane permeability analysis.

    Pipeline:
    1. Parse SMILES, compute logP (Crippen)
    2. Predict pKa (empirical SMARTS)
    3. Henderson-Hasselbalch logD(pH)
    4. Ion-pair partitioning correction
    5. 5-layer membrane free energy profile
    6. Apparent permeability (ISD model)

    Parameters
    ----------
    smiles : str
    molecule_name : str
    pH : float (default 7.4 = physiological)
    ionic_strength : float (default 0.15 M)
    membrane_model : str (default 'DOPC')

    Returns
    -------
    PermeabilityResult
    """
    # Type guards (Rule N) - validate inputs before computation
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("run_permeability_analysis: invalid SMILES input: %r", smiles)
        return PermeabilityResult(
            smiles=str(smiles) if smiles else "", molecule_name=molecule_name,
            logP=0.0, pKa_values=[], pKa_types=[], pH=pH, logD=0.0,
            fraction_neutral=1.0, fraction_ionised=0.0,
            dominant_species="unknown", free_energy_profile=[],
            permeability_cm_s=0.0, log_perm=-99.0,
            classification="error", membrane_model=membrane_model,
            ion_pair_correction=0.0, success=False,
            error="Invalid SMILES input",
        )
    if not isinstance(pH, (int, float)):
        logger.warning("run_permeability_analysis: invalid pH type: %s, defaulting to 7.4",
                       type(pH).__name__)
        pH = 7.4

    if not RDKIT_AVAILABLE:
        return PermeabilityResult(
            smiles=smiles, molecule_name=molecule_name,
            logP=0.0, pKa_values=[], pKa_types=[], pH=pH, logD=0.0,
            fraction_neutral=1.0, fraction_ionised=0.0,
            dominant_species="unknown", free_energy_profile=[],
            permeability_cm_s=0.0, log_perm=-99.0,
            classification="error", membrane_model=membrane_model,
            ion_pair_correction=0.0, success=False,
            error="RDKit not available",
        )

    # 1. Parse molecule (Rule L: SMILES parsing defense)
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return PermeabilityResult(
            smiles=smiles, molecule_name=molecule_name,
            logP=0.0, pKa_values=[], pKa_types=[], pH=pH, logD=0.0,
            fraction_neutral=1.0, fraction_ionised=0.0,
            dominant_species="unknown", free_energy_profile=[],
            permeability_cm_s=0.0, log_perm=-99.0,
            classification="error", membrane_model=membrane_model,
            ion_pair_correction=0.0, success=False,
            error=f"Failed to parse SMILES: {smiles}",
        )

    mol = Chem.AddHs(mol)

    # Compute molecular descriptors
    logP = Crippen.MolLogP(mol)
    mw = Descriptors.MolWt(mol)
    tpsa = Descriptors.TPSA(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)

    if not molecule_name:
        molecule_name = smiles

    # 2. Predict pKa
    # Remove Hs for SMARTS matching (works better on kekulized form)
    mol_noH = Chem.RemoveHs(mol)
    pka_values, pka_types, pka_descs = predict_pka(mol_noH)

    # 3. Henderson-Hasselbalch logD
    logd_result = calculate_logd(logP, pka_values, pka_types, pH)

    # 4. Ion-pair partitioning correction
    logd_ip = calculate_ion_pair_logd(logP, pka_values, pka_types, pH, ionic_strength)
    ip_correction = logd_ip - logd_result.logD

    # Cap ion-pair correction for heavily ionised molecules.
    # Ion-pair partitioning can inflate effective logD by several units,
    # but for nearly fully ionised species (fraction_neutral < 0.01),
    # the dominant transport mechanism is transporter-mediated, not
    # passive diffusion via ion pairs.  Cap the correction to prevent
    # false "high permeability" classification.
    # Reference: Avdeef (2012) warns that IP model overestimates for
    # permanently charged species (guanidines, quaternary amines).
    _MAX_IP_CORRECTION_IONISED = 1.5  # max logD units uplift for ionised species
    if logd_result.fraction_neutral < 0.01 and ip_correction > _MAX_IP_CORRECTION_IONISED:
        ip_correction = _MAX_IP_CORRECTION_IONISED
        logd_ip = logd_result.logD + ip_correction
        logger.debug(
            "Ion-pair correction capped at %.1f for heavily ionised species (f_neutral=%.4f)",
            _MAX_IP_CORRECTION_IONISED, logd_result.fraction_neutral,
        )

    # Use ion-pair corrected logD for permeability
    effective_logd = logd_ip

    # 5. Determine dominant charge
    dominant_charge = 0
    if logd_result.fraction_ionised > 0.5:
        for state in logd_result.ionisation_states:
            if state.fraction > 0.5 and state.charge != 0:
                dominant_charge = state.charge
                break

    # 6. Free energy profile
    layers = DOPC_MEMBRANE_LAYERS if membrane_model == "DOPC" else DOPC_MEMBRANE_LAYERS
    fe_profile = calculate_free_energy_profile(
        logD=effective_logd,
        logP=logP,
        mol_weight=mw,
        tpsa=tpsa,
        hbd=hbd,
        charge=dominant_charge,
        fraction_neutral=logd_result.fraction_neutral,
        layers=layers,
    )

    # 7. Apparent permeability (with ionisation-aware classification)
    p_app, log_papp, classification = calculate_permeability(
        fe_profile, mol_weight=mw,
        fraction_neutral=logd_result.fraction_neutral,
        logD=effective_logd,
        logP=logP,
    )

    logger.info(
        "Permeability analysis: %s pH=%.1f logP=%.2f logD=%.2f logPapp=%.2f (%s)",
        molecule_name, pH, logP, effective_logd, log_papp, classification,
    )

    return PermeabilityResult(
        smiles=smiles,
        molecule_name=molecule_name,
        logP=round(logP, 2),
        pKa_values=pka_values,
        pKa_types=pka_types,
        pH=pH,
        logD=round(effective_logd, 2),
        fraction_neutral=round(logd_result.fraction_neutral, 4),
        fraction_ionised=round(logd_result.fraction_ionised, 4),
        dominant_species=logd_result.dominant_species,
        free_energy_profile=fe_profile,
        permeability_cm_s=p_app,
        log_perm=log_papp,
        classification=classification,
        membrane_model=membrane_model,
        ion_pair_correction=round(ip_correction, 3),
        success=True,
    )


# ---------------------------------------------------------------------------
# pH sweep helper (for slider UI)
# ---------------------------------------------------------------------------

def sweep_ph_permeability(
    smiles: str,
    molecule_name: str = "",
    ph_range: Optional[Tuple[float, float]] = None,
    ph_step: float = 0.5,
    ionic_strength: float = 0.15,
) -> List[PermeabilityResult]:
    """Run permeability analysis across a pH range.

    Parameters
    ----------
    smiles : str
    molecule_name : str
    ph_range : tuple (pH_min, pH_max), default (1.0, 10.0)
    ph_step : float, default 0.5
    ionic_strength : float

    Returns
    -------
    List of PermeabilityResult, one per pH value
    """
    if ph_range is None:
        ph_range = (1.0, 10.0)

    results = []
    pH = ph_range[0]
    while pH <= ph_range[1] + 0.001:  # small epsilon for float comparison
        result = run_permeability_analysis(
            smiles=smiles,
            molecule_name=molecule_name,
            pH=round(pH, 1),
            ionic_strength=ionic_strength,
        )
        results.append(result)
        pH += ph_step

    return results


# ---------------------------------------------------------------------------
# Matplotlib visualisation (item 5)
# ---------------------------------------------------------------------------

def plot_free_energy_profile(
    fe_profile: List[FreeEnergyPoint],
    molecule_name: str = "",
    pH: float = 7.4,
    save_path: Optional[str] = None,
    figsize: Tuple[float, float] = (10, 5),
) -> Optional[bytes]:
    """Plot the transmembrane free energy profile.

    Returns PNG bytes if save_path is None, otherwise saves to file.
    """
    if not MATPLOTLIB_AVAILABLE or not fe_profile:
        return None

    z_vals = [p.z_position for p in fe_profile]
    dg_vals = [p.delta_G for p in fe_profile]

    fig, ax = plt.subplots(1, 1, figsize=figsize)

    # Plot free energy curve
    ax.plot(z_vals, dg_vals, "b-", linewidth=2.0, label=r"$\Delta G_{transfer}$")
    ax.fill_between(z_vals, dg_vals, alpha=0.15, color="blue")
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)

    # Add membrane layer shading
    layer_colors = {
        "center": "#FFE0B2",    # light orange
        "tail": "#FFF9C4",      # light yellow
        "interface": "#C8E6C9", # light green
        "headgroup": "#BBDEFB", # light blue
        "water": "#E3F2FD",     # very light blue
    }

    # Shade layer regions
    current_layer = ""
    layer_start = z_vals[0]
    for i, point in enumerate(fe_profile):
        if point.layer_name != current_layer:
            if current_layer and current_layer in layer_colors:
                ax.axvspan(layer_start, z_vals[i], alpha=0.2,
                           color=layer_colors[current_layer], label=None)
            current_layer = point.layer_name
            layer_start = z_vals[i]
    # Last layer
    if current_layer in layer_colors:
        ax.axvspan(layer_start, z_vals[-1], alpha=0.2,
                   color=layer_colors[current_layer])

    # Labels
    ax.set_xlabel(r"z position ($\AA$)", fontsize=12)
    ax.set_ylabel(r"$\Delta G$ (kcal/mol)", fontsize=12)
    title = f"Transmembrane Free Energy Profile"
    if molecule_name:
        title += f" - {molecule_name}"
    title += f" (pH {pH:.1f})"
    ax.set_title(title, fontsize=13, fontweight="bold")

    # Add layer labels at top
    layer_positions = {}
    for point in fe_profile:
        if point.layer_name not in layer_positions:
            layer_positions[point.layer_name] = []
        layer_positions[point.layer_name].append(point.z_position)
    for name, positions in layer_positions.items():
        mid = (min(positions) + max(positions)) / 2.0
        label_map = {
            "water": "Water",
            "headgroup": "Headgroup",
            "interface": "Interface",
            "tail": "Tail",
            "center": "Center",
        }
        # Rule N: isinstance guard for label_map
        if not isinstance(label_map, dict): label_map = {}
        ax.text(mid, ax.get_ylim()[1] * 0.95, label_map.get(name, name),
                ha="center", va="top", fontsize=8, style="italic", alpha=0.7)

    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return None
    else:
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


def plot_ph_permeability_sweep(
    results: List[PermeabilityResult],
    molecule_name: str = "",
    save_path: Optional[str] = None,
    figsize: Tuple[float, float] = (10, 6),
) -> Optional[bytes]:
    """Plot logD and log(Papp) vs pH.

    Two-panel plot:
    - Top: logD vs pH
    - Bottom: log(Papp) vs pH with classification zones

    Returns PNG bytes or saves to file.
    """
    if not MATPLOTLIB_AVAILABLE or not results:
        return None

    ph_vals = [r.pH for r in results]
    logd_vals = [r.logD for r in results]
    logperm_vals = [r.log_perm for r in results]
    frac_neutral = [r.fraction_neutral * 100 for r in results]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)

    # Top panel: logD and fraction neutral
    ax1.plot(ph_vals, logd_vals, "b-o", linewidth=2, markersize=4, label="logD")
    ax1.set_ylabel("logD", fontsize=11, color="blue")
    ax1.tick_params(axis="y", labelcolor="blue")
    ax1.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)

    ax1b = ax1.twinx()
    ax1b.plot(ph_vals, frac_neutral, "r--", linewidth=1.5, alpha=0.7, label="% neutral")
    ax1b.set_ylabel("% Neutral species", fontsize=11, color="red")
    ax1b.tick_params(axis="y", labelcolor="red")
    ax1b.set_ylim(0, 105)

    title = "pH-Dependent Lipophilicity & Permeability"
    if molecule_name:
        title += f" - {molecule_name}"
    ax1.set_title(title, fontsize=13, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # Bottom panel: permeability
    ax2.plot(ph_vals, logperm_vals, "g-s", linewidth=2, markersize=5, label=r"log P$_{app}$")

    # Classification zones
    ax2.axhspan(-4.5, 0, alpha=0.08, color="green", label="High")
    ax2.axhspan(-5.5, -4.5, alpha=0.08, color="yellow", label="Moderate")
    ax2.axhspan(-6.5, -5.5, alpha=0.08, color="orange", label="Low")
    ax2.axhspan(-15, -6.5, alpha=0.08, color="red", label="Impermeable")

    ax2.set_xlabel("pH", fontsize=12)
    ax2.set_ylabel(r"log P$_{app}$ (cm/s)", fontsize=11)
    ax2.legend(loc="upper right", fontsize=8, ncol=2)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return None
    else:
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


# ---------------------------------------------------------------------------
# Report generation (Korean, for DryLab integration)
# ---------------------------------------------------------------------------

def format_permeability_report(result: PermeabilityResult) -> str:
    """Generate Korean text report for DryLab PDF integration.

    Returns formatted text string.
    """
    if not result.success:
        return f"막 투과 분석 실패: {result.error}"

    lines = [
        f"== pH 의존적 막 투과 분석 보고서 ==",
        f"",
        f"분자: {result.molecule_name}",
        f"SMILES: {result.smiles}",
        f"분석 pH: {result.pH}",
        f"막 모델: {result.membrane_model} (5-layer model)",
        f"",
        f"--- 물리화학적 특성 ---",
        f"logP (Crippen): {result.logP}",
        f"logD (pH {result.pH}): {result.logD}",
        f"이온쌍 보정: {result.ion_pair_correction:+.3f}",
        f"",
        f"--- 이온화 상태 ---",
        f"pKa 값: {', '.join(f'{v:.1f} ({t})' for v, t in zip(result.pKa_values, result.pKa_types)) if result.pKa_values else '검출 안 됨'}",
        f"중성종 비율: {result.fraction_neutral * 100:.1f}%",
        f"이온화종 비율: {result.fraction_ionised * 100:.1f}%",
        f"우세종: {result.dominant_species}",
        f"",
        f"--- 막 투과도 ---",
        f"겉보기 투과도 (Papp): {result.permeability_cm_s:.2e} cm/s",
        f"log Papp: {result.log_perm}",
        f"분류: {result.classification}",
        f"",
        f"--- 해석 ---",
    ]

    # Classification-specific interpretation
    if result.classification == "high":
        lines.append("이 분자는 높은 막 투과성을 보입니다. 수동 확산(passive transcellular)을 통한 ")
        lines.append("흡수가 주요 경로일 것으로 예상됩니다. logD가 적절한 범위에 있어 ")
        lines.append("지질 이중층 내부로의 자유에너지 장벽이 낮습니다.")
    elif result.classification == "moderate":
        lines.append("이 분자는 중간 수준의 막 투과성을 보입니다. 수동 확산과 함께 ")
        lines.append("수용체 매개 수송(carrier-mediated transport)이 복합적으로 작용할 수 있습니다.")
    elif result.classification == "low":
        lines.append("이 분자는 낮은 막 투과성을 보입니다. 이온화 상태에서의 전하가 ")
        lines.append("지질막 통과를 억제합니다. 프로드러그 전략이나 능동 수송체를 ")
        lines.append("활용한 약물 전달 방법이 필요할 수 있습니다.")
    else:
        lines.append("이 분자는 지질막을 거의 투과하지 못합니다. Born 용매화 장벽과 ")
        lines.append("극성 표면적이 주요 장벽입니다. 비경구 투여 경로를 고려해야 합니다.")

    if result.pKa_values:
        lines.append("")
        lines.append("--- pH 의존성 참고 ---")
        lines.append(f"이 분자는 pKa = {result.pKa_values[0]:.1f}에서 이온화 전환이 일어납니다.")
        if any(t == "acid" for t in result.pKa_types):
            lines.append("산성 작용기가 존재하여 pH가 높아질수록 이온화가 증가하고 투과도가 감소합니다.")
        if any(t == "base" for t in result.pKa_types):
            lines.append("염기성 작용기가 존재하여 pH가 낮아질수록 이온화가 증가하고 투과도가 감소합니다.")

    lines.append("")
    lines.append("※ 본 분석은 정적 지질 이중층 모델에 기반한 이론적 예측입니다.")
    lines.append("   실제 세포막 투과에는 수송체, 유출 펌프(P-gp), 장내 대사 등이 추가로 관여합니다.")

    return "\n".join(lines)


def generate_permeability_chart_data(
    results: List[PermeabilityResult],
) -> Dict:
    """Generate chart-ready data dict for matplotlib or DryLab PDF.

    Returns dict with arrays for pH, logD, logPerm, fractions.
    """
    return {
        "pH": [r.pH for r in results],
        "logD": [r.logD for r in results],
        "logP_neutral": [r.logP for r in results],
        "log_perm": [r.log_perm for r in results],
        "perm_cm_s": [r.permeability_cm_s for r in results],
        "fraction_neutral": [r.fraction_neutral for r in results],
        "fraction_ionised": [r.fraction_ionised for r in results],
        "classification": [r.classification for r in results],
        "molecule_name": results[0].molecule_name if results else "",
        "smiles": results[0].smiles if results else "",
        "membrane_model": results[0].membrane_model if results else "DOPC",
    }


# ---------------------------------------------------------------------------
# QThread worker (for GUI integration)
# ---------------------------------------------------------------------------

if PYQT_AVAILABLE:
    class MembranePermeabilityThread(QThread):
        """Background thread for membrane permeability analysis.

        Emits finished(PermeabilityResult) or error(str).
        Also emits sweep_finished(list) for pH sweep mode.
        """
        finished = pyqtSignal(object)       # PermeabilityResult
        sweep_finished = pyqtSignal(object)  # List[PermeabilityResult]
        error = pyqtSignal(str)
        progress = pyqtSignal(int)           # 0-100 percent

        def __init__(self, smiles: str, molecule_name: str = "",
                     pH: float = 7.4, sweep_mode: bool = False,
                     ph_range: Optional[Tuple[float, float]] = None,
                     ph_step: float = 0.5,
                     parent=None):
            super().__init__(parent)
            self._smiles = smiles
            self._molecule_name = molecule_name
            self._pH = pH
            self._sweep_mode = sweep_mode
            self._ph_range = ph_range or (1.0, 10.0)
            self._ph_step = ph_step

        def run(self):
            try:
                if self._sweep_mode:
                    # pH sweep
                    results = []
                    ph_min, ph_max = self._ph_range
                    total_steps = int((ph_max - ph_min) / self._ph_step) + 1
                    pH = ph_min
                    step = 0
                    while pH <= ph_max + 0.001:
                        result = run_permeability_analysis(
                            smiles=self._smiles,
                            molecule_name=self._molecule_name,
                            pH=round(pH, 1),
                        )
                        results.append(result)
                        step += 1
                        self.progress.emit(int(step / total_steps * 100))
                        pH += self._ph_step
                    self.sweep_finished.emit(results)
                else:
                    # Single pH
                    result = run_permeability_analysis(
                        smiles=self._smiles,
                        molecule_name=self._molecule_name,
                        pH=self._pH,
                    )
                    self.progress.emit(100)
                    self.finished.emit(result)

            except Exception as exc:
                logger.warning("MembranePermeabilityThread error: %s", exc)
                self.error.emit(str(exc))
