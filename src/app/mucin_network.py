"""mucin_network.py -- Mucin Glycoprotein Network Analyzer (Module C)

Coarse-grained mucin gel network modelling, Ogston sieving,
and mucolytic agent simulation for ChemGrid Cascade #11 Block 11-C.

Features
--------
- Coarse-grained mucin network graph (NetworkX)
- pH-dependent network density (acid condensation / alkaline swelling)
- Mucolytic S-S bond cleavage simulation (N-acetylcysteine / DTT)
- Ogston sieving model: particle size vs mesh size -> penetration probability
- PEGylation (nanoparticle surface coating) stealth effect
- Electrostatic interaction mapping (sialic acid charges vs drug charge)

Scientific References
---------------------
- Ogston, A.G. (1958). Trans. Faraday Soc. 54, 1754-1757.
- Lieleg, O. & Ribbeck, K. (2011). Trends Cell Biol. 21(9), 543-551.
- Cone, R.A. (2009). Adv. Drug Deliv. Rev. 61(2), 75-85.
- Lai, S.K., Wang, Y.-Y. & Hanes, J. (2009). Adv. Drug Deliv. Rev. 61(2), 158-171.
- Bansil, R. & Turner, B.S. (2006). Curr. Opin. Colloid Interface Sci. 11(2-3), 164-170.

Created: 2026-04-04  |  Block 11-C  |  Owned by: domain_drug
"""

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guards (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors, Crippen
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
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
MUCIN_NETWORK_AVAILABLE = NETWORKX_AVAILABLE and NUMPY_AVAILABLE


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

_R = 8.314462618       # J/(mol*K) -- universal gas constant (CODATA 2018)
_T_BODY = 310.15       # K  (37 C)
_kB = 1.380649e-23     # J/K -- Boltzmann constant
_AVOGADRO = 6.02214076e23  # mol^-1

# Mucin gel reference parameters (Cone 2009, Lieleg & Ribbeck 2011)
_MUCIN_MW = 2.5e6      # Da -- average MUC5AC molecular weight
_MUCIN_LENGTH_NM = 500  # nm -- contour length of single mucin monomer
_MESH_SIZE_PHYSIOLOGICAL_NM = 340  # nm -- Lai et al. (2009) fresh cervicovaginal mucus
_MESH_SIZE_CF_NM = 140  # nm -- cystic fibrosis mucus (dehydrated, dense)
_SIALIC_ACID_CHARGE = -1  # net charge per sialic acid residue at pH 7.4
_SS_BOND_ENERGY_KJ = 251  # kJ/mol -- typical disulfide bond dissociation energy


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MucinNetworkParams:
    """Parameters for mucin gel network construction."""
    n_nodes: int = 80           # number of mucin junction nodes
    n_disulfide_bonds: int = 50  # number of S-S crosslinks
    n_entanglements: int = 30   # physical entanglements (non-covalent)
    mesh_size_nm: float = _MESH_SIZE_PHYSIOLOGICAL_NM  # average mesh pore size
    mucin_concentration_mg_ml: float = 20.0  # mg/mL (typical 10-50 mg/mL)
    sialic_acid_per_chain: int = 120  # average SA residues per mucin monomer
    pH: float = 7.4
    temperature_K: float = _T_BODY


@dataclass
class MucinNode:
    """Single node in the mucin network (junction point or chain terminus)."""
    node_id: int
    x: float  # nm
    y: float  # nm
    z: float  # nm
    charge: float  # net charge (from sialic acid residues)
    is_crosslink: bool = False  # True if this node is a disulfide crosslink


@dataclass
class MucinEdge:
    """Edge (connection) in the mucin network."""
    source: int
    target: int
    bond_type: str  # "disulfide", "entanglement", or "backbone"
    length_nm: float = 0.0
    is_intact: bool = True  # False after cleavage


@dataclass
class OgstonResult:
    """Result of Ogston sieving analysis for a specific particle."""
    particle_name: str
    particle_radius_nm: float
    mesh_size_nm: float
    fiber_radius_nm: float  # mucin fiber radius (~3-4 nm)
    volume_fraction: float  # phi = mucin volume fraction
    penetration_probability: float  # 0 to 1
    diffusion_ratio: float  # D_mucus / D_water
    classification: str  # "freely permeable", "partially sieved", "trapped"
    notes: str = ""


@dataclass
class MucolyticResult:
    """Result of mucolytic agent simulation."""
    agent_name: str
    agent_smiles: str
    concentration_mM: float
    ss_bonds_before: int
    ss_bonds_after: int
    fraction_cleaved: float
    mesh_size_before_nm: float
    mesh_size_after_nm: float
    viscosity_ratio: float  # mu_after / mu_before (< 1 = less viscous)
    network_fragments: int  # connected components after cleavage
    mechanism: str  # description of mucolytic mechanism


@dataclass
class PEGylationResult:
    """Result of PEGylation stealth effect analysis."""
    peg_mw: float  # PEG molecular weight (Da)
    peg_density: float  # chains per nm^2
    brush_height_nm: float  # PEG brush height (Alexander-de Gennes)
    steric_repulsion_kT: float  # repulsive energy in kT units
    charge_shielding: float  # fraction of surface charge masked (0-1)
    penetration_enhancement: float  # fold-increase in Ogston P vs bare
    classification: str  # "mucoinert", "partially shielded", "mucoadhesive"


@dataclass
class ElectrostaticMapResult:
    """Result of electrostatic interaction mapping."""
    drug_smiles: str
    drug_charge_pH74: float
    mucin_local_charge_density: float  # charge/nm^3
    interaction_energy_kT: float
    interaction_type: str  # "repulsive", "attractive", "neutral"
    binding_probability: float  # probability of mucoadhesive trapping
    notes: str = ""


@dataclass
class MucinAnalysisResult:
    """Complete mucin network analysis result."""
    success: bool
    error: str = ""
    params: Optional[MucinNetworkParams] = None
    network_stats: Dict = field(default_factory=dict)
    ogston_results: List[OgstonResult] = field(default_factory=list)
    mucolytic_result: Optional[MucolyticResult] = None
    pegylation_result: Optional[PEGylationResult] = None
    electrostatic_result: Optional[ElectrostaticMapResult] = None
    node_positions: List[Tuple[float, float, float]] = field(default_factory=list)
    edges: List[Tuple[int, int, str, bool]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mucin network construction (Coarse-Grained)
# ---------------------------------------------------------------------------

def build_mucin_network(
    params: MucinNetworkParams,
    seed: int = 42,
) -> Tuple:
    """Build a coarse-grained mucin gel network using NetworkX.

    The network consists of:
    - Backbone chains (linear segments between junction nodes)
    - Disulfide crosslinks (covalent S-S bonds between chains)
    - Physical entanglements (transient, non-covalent contacts)

    Parameters
    ----------
    params : MucinNetworkParams
    seed : int -- random seed for reproducibility

    Returns
    -------
    (nx.Graph, list_of_MucinNode, list_of_MucinEdge)
    """
    if not NETWORKX_AVAILABLE or not NUMPY_AVAILABLE:
        logger.warning("NetworkX or NumPy unavailable; returning empty network")
        return None, [], []

    rng = np.random.default_rng(seed)

    # ----- Generate node positions in a 3D cube (side = f(concentration)) -----
    # Box side length scales inversely with concentration^(1/3)
    # At 20 mg/mL with 80 nodes, box ~ 1000 nm
    conc = max(params.mucin_concentration_mg_ml, 1.0)
    box_side_nm = 1000.0 * (20.0 / conc) ** (1.0 / 3.0)  # reference: 1000 nm at 20 mg/mL

    nodes: List[MucinNode] = []
    for i in range(params.n_nodes):
        x = rng.uniform(0, box_side_nm)
        y = rng.uniform(0, box_side_nm)
        z = rng.uniform(0, box_side_nm)

        # Assign charge: each node represents a mucin junction with sialic acid
        # Average charge = sialic_acid_per_chain / n_nodes * _SIALIC_ACID_CHARGE
        # pH-dependent: pKa of sialic acid ~ 2.6 (Schauer, 1982)
        # At pH > 4, fully deprotonated (charge = -1 per SA)
        pka_sialic = 2.6  # pKa of N-acetylneuraminic acid (Neu5Ac)
        fraction_ionised = 1.0 / (1.0 + 10.0 ** (pka_sialic - params.pH))
        sa_per_node = params.sialic_acid_per_chain / max(params.n_nodes, 1)
        charge = sa_per_node * _SIALIC_ACID_CHARGE * fraction_ionised

        nodes.append(MucinNode(
            node_id=i, x=x, y=y, z=z,
            charge=round(charge, 2),
            is_crosslink=False,
        ))

    # ----- Build NetworkX graph -----
    G = nx.Graph()
    for nd in nodes:
        G.add_node(nd.node_id, pos=(nd.x, nd.y, nd.z), charge=nd.charge)

    edges: List[MucinEdge] = []

    # 1. Backbone chains -- connect sequential nodes (simulating linear mucin chains)
    # Divide nodes into chains of ~10 nodes each
    chain_length = max(8, params.n_nodes // 8)  # ~10 nodes per chain
    for start in range(0, params.n_nodes, chain_length):
        for j in range(start, min(start + chain_length - 1, params.n_nodes - 1)):
            src, tgt = j, j + 1
            dist = _node_distance(nodes[src], nodes[tgt])
            e = MucinEdge(source=src, target=tgt, bond_type="backbone",
                          length_nm=round(dist, 1), is_intact=True)
            edges.append(e)
            G.add_edge(src, tgt, bond_type="backbone", length=dist, intact=True)

    # 2. Disulfide crosslinks -- random inter-chain bridges
    all_node_ids = list(range(params.n_nodes))
    ss_count = 0
    attempts = 0
    max_attempts = params.n_disulfide_bonds * 10  # avoid infinite loop
    while ss_count < params.n_disulfide_bonds and attempts < max_attempts:
        attempts += 1
        a, b = rng.choice(all_node_ids, size=2, replace=False)
        if G.has_edge(a, b):
            continue
        dist = _node_distance(nodes[a], nodes[b])
        # S-S bonds form between nearby chains (< half box)
        if dist > box_side_nm * 0.5:
            continue
        e = MucinEdge(source=a, target=b, bond_type="disulfide",
                      length_nm=round(dist, 1), is_intact=True)
        edges.append(e)
        G.add_edge(a, b, bond_type="disulfide", length=dist, intact=True)
        nodes[a].is_crosslink = True
        nodes[b].is_crosslink = True
        ss_count += 1

    # 3. Physical entanglements
    ent_count = 0
    attempts = 0
    while ent_count < params.n_entanglements and attempts < params.n_entanglements * 10:
        attempts += 1
        a, b = rng.choice(all_node_ids, size=2, replace=False)
        if G.has_edge(a, b):
            continue
        dist = _node_distance(nodes[a], nodes[b])
        if dist > box_side_nm * 0.4:
            continue
        e = MucinEdge(source=a, target=b, bond_type="entanglement",
                      length_nm=round(dist, 1), is_intact=True)
        edges.append(e)
        G.add_edge(a, b, bond_type="entanglement", length=dist, intact=True)
        ent_count += 1

    logger.info("Mucin network built: %d nodes, %d edges (%d SS, %d ent, rest backbone)",
                G.number_of_nodes(), G.number_of_edges(),
                ss_count, ent_count)

    return G, nodes, edges


def _node_distance(a: MucinNode, b: MucinNode) -> float:
    """Euclidean distance between two nodes in nm."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


# ---------------------------------------------------------------------------
# pH-dependent network density (item 2)
# Reference: Bansil & Turner (2006), Celli et al. (2007)
# ---------------------------------------------------------------------------

def calculate_ph_dependent_mesh_size(
    base_mesh_nm: float,
    pH: float,
) -> Tuple[float, str]:
    """Calculate pH-dependent mucin gel mesh size.

    Mucin undergoes sol-gel transition at low pH:
    - pH < 2: tight gel (gastric mucin, condensed)
    - pH 2-4: transitional (gel-sol boundary)
    - pH 4-6: loose gel
    - pH 6-8: expanded sol/gel (physiological)
    - pH > 8: highly swollen, weak gel

    The transition is driven by:
    1. Protonation of sialic acid (pKa ~ 2.6) reduces charge repulsion
    2. Hydrophobic collapse of protein backbone at low pH
    3. Hydrogen bonding between sugar residues

    Parameters
    ----------
    base_mesh_nm : float -- mesh size at pH 7.4 (reference)
    pH : float

    Returns
    -------
    (adjusted_mesh_nm, description)
    """
    # Scaling function based on Bansil & Turner (2006) rheology data
    # At pH 2: mesh ~ 0.15x reference (condensed gel)
    # At pH 4: mesh ~ 0.5x reference (partial gel)
    # At pH 6: mesh ~ 0.85x reference (loose)
    # At pH 7.4: mesh ~ 1.0x reference (physiological)
    # At pH 9: mesh ~ 1.3x reference (swollen)

    if pH < 2.0:
        # Fully condensed gastric gel
        scale = 0.10 + 0.05 * pH  # 0.10 at pH 0, 0.20 at pH 2
        desc = "Condensed gastric gel: mucin undergoes hydrophobic collapse and hydrogen bonding"
    elif pH < 4.0:
        # Sol-gel transition zone
        scale = 0.20 + 0.15 * (pH - 2.0)  # 0.20 at pH 2, 0.50 at pH 4
        desc = "Sol-gel transition: sialic acid partially protonated, intermediate density"
    elif pH < 6.0:
        # Loose gel
        scale = 0.50 + 0.175 * (pH - 4.0)  # 0.50 at pH 4, 0.85 at pH 6
        desc = "Loose gel: charge repulsion partially restored, network expanding"
    elif pH < 8.0:
        # Physiological range
        scale = 0.85 + 0.075 * (pH - 6.0)  # 0.85 at pH 6, 1.0 at pH 8
        desc = "Physiological gel: sialic acid fully ionised, moderate charge repulsion"
    else:
        # Alkaline swelling
        scale = 1.0 + 0.15 * (pH - 8.0)  # 1.0 at pH 8, 1.3 at pH 10
        desc = "Alkaline-swollen: enhanced electrostatic repulsion, weakened hydrophobic interactions"

    scale = max(0.05, min(scale, 2.0))  # clamp to physical range
    adjusted = base_mesh_nm * scale

    return round(adjusted, 1), desc


# ---------------------------------------------------------------------------
# Ogston sieving model (item 4)
# Reference: Ogston (1958), Lieleg & Ribbeck (2011)
# ---------------------------------------------------------------------------

def ogston_sieving(
    particle_radius_nm: float,
    mesh_size_nm: float,
    fiber_radius_nm: float = 3.5,  # mucin fiber radius, Lai et al. (2009)
    mucin_conc_mg_ml: float = 20.0,
) -> OgstonResult:
    """Calculate Ogston sieving probability for a particle in mucin gel.

    The Ogston model treats the gel as a random fiber network.
    Penetration probability depends on the ratio of particle size
    to mesh (pore) size.

    P = exp(-pi * phi * ((r_p + r_f) / r_f)^2)

    where phi = volume fraction of fibers,
          r_p = particle radius,
          r_f = fiber radius.

    Diffusion ratio (D_gel/D_water) is estimated using the
    Amsden (1998) obstruction-scaling model:
    D_gel/D_water = exp(-pi * (r_p / (mesh_size + r_p))^2)

    Parameters
    ----------
    particle_radius_nm : float
    mesh_size_nm : float
    fiber_radius_nm : float (default 3.5 nm for mucin glycoprotein fiber)
    mucin_conc_mg_ml : float

    Returns
    -------
    OgstonResult
    """
    if particle_radius_nm <= 0 or mesh_size_nm <= 0 or fiber_radius_nm <= 0:
        return OgstonResult(
            particle_name="", particle_radius_nm=particle_radius_nm,
            mesh_size_nm=mesh_size_nm, fiber_radius_nm=fiber_radius_nm,
            volume_fraction=0.0, penetration_probability=0.0,
            diffusion_ratio=0.0, classification="error",
            notes="Invalid parameters (non-positive values)",
        )

    # Volume fraction: phi ~ (conc_mg_ml / 1000) * (v_specific / rho)
    # For mucin: partial specific volume ~ 0.72 mL/g (typical glycoprotein)
    v_specific = 0.72  # mL/g -- partial specific volume of mucin
    phi = (mucin_conc_mg_ml / 1000.0) * v_specific  # dimensionless
    phi = max(phi, 1e-6)

    # Ogston penetration probability
    ratio = (particle_radius_nm + fiber_radius_nm) / fiber_radius_nm
    P_ogston = math.exp(-math.pi * phi * ratio ** 2)
    P_ogston = max(0.0, min(1.0, P_ogston))

    # Amsden (1998) diffusion ratio
    D_ratio = math.exp(-math.pi * (particle_radius_nm / (mesh_size_nm + particle_radius_nm)) ** 2)
    D_ratio = max(0.0, min(1.0, D_ratio))

    # Classification
    if P_ogston > 0.5:
        classification = "freely permeable"
    elif P_ogston > 0.1:
        classification = "partially sieved"
    elif P_ogston > 0.01:
        classification = "mostly trapped"
    else:
        classification = "completely trapped"

    # Size ratio note for educational context
    size_ratio = particle_radius_nm / mesh_size_nm
    if size_ratio < 0.1:
        notes = "Particle much smaller than mesh pores: minimal steric hindrance"
    elif size_ratio < 0.5:
        notes = "Particle comparable to mesh size: significant sieving effect"
    elif size_ratio < 1.0:
        notes = "Particle approaches mesh size: strong steric exclusion"
    else:
        notes = "Particle larger than mesh pores: complete steric trapping"

    return OgstonResult(
        particle_name="",
        particle_radius_nm=round(particle_radius_nm, 1),
        mesh_size_nm=round(mesh_size_nm, 1),
        fiber_radius_nm=round(fiber_radius_nm, 1),
        volume_fraction=round(phi, 6),
        penetration_probability=round(P_ogston, 4),
        diffusion_ratio=round(D_ratio, 4),
        classification=classification,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Mucolytic agent simulation (item 3)
# Reference: Suk et al. (2009), Sheffner (1963)
# ---------------------------------------------------------------------------

# Mucolytic agents database
_MUCOLYTIC_DB: Dict[str, Dict] = {
    "N-acetylcysteine": {
        "smiles": "CC(=O)NC(CS)C(=O)O",
        "mechanism": "Thiol group (-SH) reduces disulfide bonds (S-S -> 2 SH) via thiol-disulfide exchange",
        "max_cleavage_fraction": 0.85,  # at saturating concentration
        "half_max_conc_mM": 5.0,  # EC50 for S-S cleavage
        "abbrev": "NAC",
    },
    "DTT": {
        "smiles": "OC(CS)C(S)CO",
        "mechanism": "Dithiol reducing agent: cyclic oxidation forms stable 6-membered ring, driving S-S reduction to completion",
        "max_cleavage_fraction": 0.95,
        "half_max_conc_mM": 2.0,
        "abbrev": "DTT",
    },
    "TCEP": {
        "smiles": "O=P(CCO)(CCO)CCO",
        "mechanism": "Phosphine-based reductant: irreversible S-S reduction without forming mixed disulfides",
        "max_cleavage_fraction": 0.98,
        "half_max_conc_mM": 1.0,
        "abbrev": "TCEP",
    },
    "Erdosteine": {
        "smiles": "O=C1CSCC1NC(=O)CS",
        "mechanism": "Prodrug: metabolised to active thiol (Met-I) that cleaves mucin S-S bonds + antioxidant",
        "max_cleavage_fraction": 0.70,
        "half_max_conc_mM": 8.0,
        "abbrev": "ERD",
    },
}


def simulate_mucolytic_cleavage(
    agent_name: str,
    concentration_mM: float,
    n_disulfide_bonds: int = 50,
    mesh_size_nm: float = _MESH_SIZE_PHYSIOLOGICAL_NM,
) -> MucolyticResult:
    """Simulate S-S bond cleavage by a mucolytic agent.

    Uses a Hill-type dose-response model:
    fraction_cleaved = f_max * [C]^n / ([C]^n + EC50^n)
    where n = 1.5 (cooperativity from gel accessibility)

    The mesh size expands as crosslinks are removed:
    mesh_after = mesh_before / sqrt(1 - fraction_cleaved)
    (from scaling theory: mesh ~ phi^(-0.5) and crosslink density ~ phi)

    Viscosity decreases with mesh expansion (Rubinstein-Colby scaling):
    mu_ratio = (mesh_before / mesh_after)^3

    Parameters
    ----------
    agent_name : str -- key in _MUCOLYTIC_DB
    concentration_mM : float
    n_disulfide_bonds : int
    mesh_size_nm : float

    Returns
    -------
    MucolyticResult
    """
    agent = _MUCOLYTIC_DB.get(agent_name)
    if agent is None:
        return MucolyticResult(
            agent_name=agent_name, agent_smiles="",
            concentration_mM=concentration_mM,
            ss_bonds_before=n_disulfide_bonds, ss_bonds_after=n_disulfide_bonds,
            fraction_cleaved=0.0,
            mesh_size_before_nm=mesh_size_nm, mesh_size_after_nm=mesh_size_nm,
            viscosity_ratio=1.0, network_fragments=1,
            mechanism=f"Unknown mucolytic agent: {agent_name}",
        )

    # N코드: 타입 가드 — agent가 dict인지, 필수 키 존재 확인
    if not isinstance(agent, dict):
        logger.warning("Mucolytic agent DB entry is not dict: type=%s", type(agent).__name__)
        return MucolyticResult(
            agent_name=agent_name, agent_smiles="",
            concentration_mM=concentration_mM,
            ss_bonds_before=n_disulfide_bonds, ss_bonds_after=n_disulfide_bonds,
            fraction_cleaved=0.0,
            mesh_size_before_nm=mesh_size_nm, mesh_size_after_nm=mesh_size_nm,
            viscosity_ratio=1.0, network_fragments=1,
            mechanism=f"Invalid mucolytic agent entry type: {type(agent).__name__}",
        )

    # Hill equation for dose-response
    f_max = agent.get("max_cleavage_fraction", 0.0)
    ec50 = agent.get("half_max_conc_mM", 10.0)
    if not isinstance(f_max, (int, float)):
        f_max = 0.0
    if not isinstance(ec50, (int, float)) or ec50 <= 0:
        ec50 = 10.0
    hill_n = 1.5  # cooperativity coefficient (empirical)

    if concentration_mM <= 0:
        frac_cleaved = 0.0
    else:
        frac_cleaved = f_max * (concentration_mM ** hill_n) / (
            concentration_mM ** hill_n + ec50 ** hill_n
        )
    frac_cleaved = min(frac_cleaved, f_max)

    ss_after = max(0, round(n_disulfide_bonds * (1.0 - frac_cleaved)))

    # Mesh expansion (scaling theory)
    # mesh ~ 1/sqrt(crosslink_density)
    remaining_fraction = 1.0 - frac_cleaved
    if remaining_fraction < 0.01:
        remaining_fraction = 0.01  # avoid division by zero; near-complete dissolution
    mesh_after = mesh_size_nm / math.sqrt(remaining_fraction)

    # Viscosity ratio (Rubinstein-Colby entangled gel scaling)
    # eta ~ xi^(-3) where xi = mesh size
    viscosity_ratio = (mesh_size_nm / mesh_after) ** 3

    # Estimate network fragments using percolation theory
    # At percolation threshold (~0.5 of bonds removed), network fragments
    # Simplified: fragments ~ 1 + (n_nodes_approx * frac_cleaved / 5)
    n_approx_nodes = 80
    if frac_cleaved > 0.5:
        # Above percolation threshold: many disconnected fragments
        fragments = max(2, round(n_approx_nodes * (frac_cleaved - 0.3) / 2.0))
    elif frac_cleaved > 0.2:
        fragments = max(1, round(frac_cleaved * 5))
    else:
        fragments = 1

    return MucolyticResult(
        agent_name=agent_name,
        agent_smiles=agent["smiles"],
        concentration_mM=round(concentration_mM, 2),
        ss_bonds_before=n_disulfide_bonds,
        ss_bonds_after=ss_after,
        fraction_cleaved=round(frac_cleaved, 4),
        mesh_size_before_nm=round(mesh_size_nm, 1),
        mesh_size_after_nm=round(mesh_after, 1),
        viscosity_ratio=round(viscosity_ratio, 4),
        network_fragments=fragments,
        mechanism=agent["mechanism"],
    )


# ---------------------------------------------------------------------------
# PEGylation stealth effect (item 5)
# Reference: Lai, Wang & Hanes (2009), Suk et al. (2011)
# ---------------------------------------------------------------------------

def calculate_pegylation_effect(
    peg_mw: float = 5000.0,  # Da -- PEG molecular weight
    peg_density: float = 0.5,  # chains/nm^2 on nanoparticle surface
    particle_radius_nm: float = 100.0,
    mucin_charge_density: float = -0.01,  # charge/nm^3 (negative from sialic acid)
) -> PEGylationResult:
    """Model PEGylation stealth effect on nanoparticle mucin penetration.

    PEG forms a polymer brush on the particle surface that:
    1. Sterically repels mucin fibers (Alexander-de Gennes brush theory)
    2. Shields surface charges (reduces electrostatic mucoadhesion)
    3. Reduces hydrophobic interactions

    Brush height (Alexander-de Gennes):
    h = N * a * (sigma * a^2)^(1/3)
    where N = PEG degree of polymerisation, a = monomer size (0.35 nm),
    sigma = grafting density (chains/nm^2)

    Parameters
    ----------
    peg_mw : float -- PEG molecular weight (Da)
    peg_density : float -- grafting density (chains/nm^2)
    particle_radius_nm : float
    mucin_charge_density : float -- charge/nm^3

    Returns
    -------
    PEGylationResult
    """
    # PEG monomer MW = 44 Da (ethylene oxide unit)
    monomer_mw = 44.0  # Da per EO unit
    N = peg_mw / monomer_mw  # degree of polymerisation
    a = 0.35  # nm -- Kuhn segment length for PEG

    # Flory radius (unperturbed coil)
    Rf = a * N ** 0.6  # good solvent scaling (Flory exponent = 3/5)

    # Alexander-de Gennes brush height
    sigma = peg_density  # chains/nm^2
    if sigma > 0 and a > 0:
        # Brush regime: sigma > 1/Rf^2
        if sigma * Rf ** 2 > 1:
            # Dense brush
            h = N * a * (sigma * a ** 2) ** (1.0 / 3.0)
        else:
            # Mushroom regime: h ~ Rf
            h = Rf
    else:
        h = 0.0

    # Steric repulsion (de Gennes model)
    # F/A ~ kT * sigma^(3/2) * [2h/D - 1] per unit area
    # Approximate repulsion energy when mucin fiber (r_f~3.5 nm) approaches
    r_fiber = 3.5  # nm -- mucin fiber radius
    if h > r_fiber:
        compression = 2 * h / r_fiber  # overlap parameter
        repulsion_kT = sigma ** 1.5 * (compression - 1) * 10  # scaled
    else:
        repulsion_kT = 0.1  # minimal repulsion

    repulsion_kT = max(0.0, min(repulsion_kT, 100.0))

    # Charge shielding: PEG layer masks surface charge
    # Shielding ~ 1 - exp(-h / Debye_length)
    # At physiological ionic strength (0.15 M), Debye length ~ 0.8 nm
    debye_length = 0.8  # nm at 0.15 M NaCl
    charge_shielding = 1.0 - math.exp(-h / debye_length) if h > 0 else 0.0

    # Penetration enhancement
    # Dense PEG brush: 10-100x enhancement vs bare particle (Lai et al. 2009)
    # Modelled as exponential of brush quality
    if h > 5.0 and sigma > 0.1:
        # Dense, tall brush: excellent mucus penetration
        enhancement = min(100.0, 1.0 + 99.0 * (1 - math.exp(-sigma * h / 10.0)))
    elif h > 2.0:
        enhancement = min(20.0, 1.0 + 19.0 * (1 - math.exp(-sigma * h / 20.0)))
    else:
        enhancement = 1.0 + h * 0.5  # minimal effect

    # Classification
    if enhancement > 10.0 and charge_shielding > 0.9:
        classification = "mucoinert"
    elif enhancement > 3.0 or charge_shielding > 0.5:
        classification = "partially shielded"
    else:
        classification = "mucoadhesive"

    return PEGylationResult(
        peg_mw=round(peg_mw, 0),
        peg_density=round(peg_density, 3),
        brush_height_nm=round(h, 2),
        steric_repulsion_kT=round(repulsion_kT, 2),
        charge_shielding=round(charge_shielding, 4),
        penetration_enhancement=round(enhancement, 2),
        classification=classification,
    )


# ---------------------------------------------------------------------------
# Electrostatic interaction mapping (item 6)
# Reference: Lieleg et al. (2010), Cone (2009)
# ---------------------------------------------------------------------------

def calculate_electrostatic_interaction(
    drug_smiles: str,
    pH: float = 7.4,
    mucin_charge_density: float = -0.005,  # charge/nm^3 (from sialic acid)
    temperature_K: float = _T_BODY,
) -> ElectrostaticMapResult:
    """Calculate electrostatic interaction between drug and mucin gel.

    Mucin gel has net negative charge from sialic acid residues.
    Drug charge at given pH determines interaction type:
    - Cationic drugs: attracted, trapped (mucoadhesive)
    - Anionic drugs: repelled, pass through (mucorepulsive)
    - Neutral drugs: no electrostatic interaction (diffusion-limited)

    Uses Debye-Hueckel screened Coulomb interaction:
    U(r) = (q_drug * q_mucin) / (4*pi*eps0*eps_r*r) * exp(-r/lambda_D)

    Parameters
    ----------
    drug_smiles : str
    pH : float
    mucin_charge_density : float
    temperature_K : float

    Returns
    -------
    ElectrostaticMapResult
    """
    if not RDKIT_AVAILABLE:
        return ElectrostaticMapResult(
            drug_smiles=drug_smiles, drug_charge_pH74=0.0,
            mucin_local_charge_density=mucin_charge_density,
            interaction_energy_kT=0.0, interaction_type="unknown",
            binding_probability=0.0,
            notes="RDKit not available",
        )

    mol = Chem.MolFromSmiles(drug_smiles)
    if mol is None:
        return ElectrostaticMapResult(
            drug_smiles=drug_smiles, drug_charge_pH74=0.0,
            mucin_local_charge_density=mucin_charge_density,
            interaction_energy_kT=0.0, interaction_type="unknown",
            binding_probability=0.0,
            notes=f"Failed to parse SMILES: {drug_smiles}",
        )

    # Estimate drug charge at given pH
    # Use formal charge as baseline, then apply pKa-based ionisation
    formal_charge = sum(a.GetFormalCharge() for a in mol.GetAtoms())

    # Simple heuristic: count ionisable groups
    # Amines (basic, pKa ~ 9-11): protonated at pH < pKa => +1
    # Carboxylic acids (pKa ~ 4-5): deprotonated at pH > pKa => -1
    n_basic_N = len(mol.GetSubstructMatches(Chem.MolFromSmarts("[NX3;H2,H1;!$(NC=O)]"))) if Chem.MolFromSmarts("[NX3;H2,H1;!$(NC=O)]") else 0
    n_acid_COOH = len(mol.GetSubstructMatches(Chem.MolFromSmarts("[CX3](=O)[OX2H1]"))) if Chem.MolFromSmarts("[CX3](=O)[OX2H1]") else 0

    # Henderson-Hasselbalch for net charge
    charge_from_bases = 0.0
    for _ in range(n_basic_N):
        pka_base = 10.0  # average amine pKa
        frac_protonated = 1.0 / (1.0 + 10.0 ** (pH - pka_base))
        charge_from_bases += frac_protonated  # each protonated amine = +1

    charge_from_acids = 0.0
    for _ in range(n_acid_COOH):
        pka_acid = 4.5  # average carboxylic acid pKa
        frac_ionised = 1.0 / (1.0 + 10.0 ** (pka_acid - pH))
        charge_from_acids -= frac_ionised  # each deprotonated acid = -1

    net_charge = formal_charge + charge_from_bases + charge_from_acids

    # Debye-Hueckel screened interaction energy (kT units)
    # At physiological ionic strength: lambda_D ~ 0.8 nm
    lambda_D = 0.8  # nm -- Debye length at 0.15 M NaCl
    # Interaction distance: average contact distance ~ 2 nm
    r_contact = 2.0  # nm
    # Simplified U/kT = (q_drug * rho_mucin * V_eff) / (eps * kT)
    # V_eff = effective interaction volume ~ (4/3) * pi * lambda_D^3
    V_eff = (4.0 / 3.0) * math.pi * lambda_D ** 3  # nm^3
    # Bjerrum length at 37C, water: l_B ~ 0.71 nm
    l_B = 0.71  # nm -- Bjerrum length in water at 310 K

    # Interaction energy in kT units
    U_kT = net_charge * mucin_charge_density * V_eff * l_B * 1000  # scaled for observable effect
    U_kT = max(-50.0, min(50.0, U_kT))  # clamp

    # Classify interaction
    if U_kT < -1.0:
        interaction_type = "attractive"
        # Cationic drug attracted to anionic mucin
        binding_prob = 1.0 - math.exp(U_kT)  # higher |U| -> higher binding
        binding_prob = min(0.99, max(0.0, binding_prob))
    elif U_kT > 1.0:
        interaction_type = "repulsive"
        binding_prob = math.exp(-U_kT)  # repulsion reduces binding
        binding_prob = min(0.5, max(0.0, binding_prob))
    else:
        interaction_type = "neutral"
        binding_prob = 0.1  # weak non-specific interaction only

    # Educational notes
    if interaction_type == "attractive":
        notes = ("Cationic drug attracted to anionic mucin glycoproteins. "
                 "Risk of mucoadhesive trapping reducing bioavailability.")
    elif interaction_type == "repulsive":
        notes = ("Anionic drug repelled by like-charged mucin. "
                 "Charge repulsion facilitates mucus penetration.")
    else:
        notes = ("Near-neutral drug at this pH. Mucus penetration governed "
                 "primarily by size (Ogston sieving) and hydrophobicity.")

    return ElectrostaticMapResult(
        drug_smiles=drug_smiles,
        drug_charge_pH74=round(net_charge, 2),
        mucin_local_charge_density=mucin_charge_density,
        interaction_energy_kT=round(U_kT, 3),
        interaction_type=interaction_type,
        binding_probability=round(binding_prob, 4),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Molecule hydrodynamic radius estimation
# ---------------------------------------------------------------------------

def estimate_hydrodynamic_radius_nm(smiles: str) -> Tuple[float, str]:
    """Estimate hydrodynamic radius of a molecule from SMILES.

    Uses the empirical correlation:
    r_h (nm) ~ 0.066 * MW^(1/3)  for small molecules (MW < 1000 Da)
    This is calibrated against DLS measurements of drug molecules.

    For larger species (proteins, nanoparticles), use known values.

    Returns
    -------
    (radius_nm, method_description)
    """
    if not RDKIT_AVAILABLE:
        return 0.5, "default (RDKit unavailable)"

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return 0.5, "default (SMILES parse failed)"

    mw = Descriptors.MolWt(mol)

    # Empirical: r_h ~ 0.066 * MW^(1/3) nm for drug-like molecules
    # Calibration: aspirin (180 Da) -> ~0.37 nm, insulin (5808 Da) -> ~1.2 nm
    r_h = 0.066 * mw ** (1.0 / 3.0)  # nm

    method = f"Empirical MW^(1/3) correlation (MW={mw:.1f} Da)"
    return round(r_h, 2), method


# ---------------------------------------------------------------------------
# Chart generation (matplotlib)
# ---------------------------------------------------------------------------

def generate_ogston_chart(
    results: List[OgstonResult],
    output_path: str = "",
) -> Optional[bytes]:
    """Generate Ogston sieving probability chart.

    Bar chart: penetration probability + diffusion ratio for multiple particles.

    Returns PNG bytes if no output_path, or writes to file.
    """
    if not MATPLOTLIB_AVAILABLE or not results:
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")

    names = [r.particle_name or f"r={r.particle_radius_nm}nm" for r in results]
    P_vals = [r.penetration_probability for r in results]
    D_vals = [r.diffusion_ratio for r in results]

    x = range(len(results))

    # Penetration probability
    bars1 = ax1.bar(x, P_vals, color="#4ecdc4", edgecolor="#1a1a2e", linewidth=0.5)
    ax1.set_xlabel("Particle", color="white", fontsize=10)
    ax1.set_ylabel("Penetration Probability", color="white", fontsize=10)
    ax1.set_title("Ogston Sieving: Penetration", color="white", fontsize=12)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(names, rotation=45, ha="right", color="white", fontsize=8)
    ax1.set_ylim(0, 1.05)
    ax1.set_facecolor("#16213e")
    ax1.tick_params(colors="white")
    for bar_val, bar_obj in zip(P_vals, bars1):
        ax1.text(bar_obj.get_x() + bar_obj.get_width() / 2, bar_val + 0.02,
                 f"{bar_val:.3f}", ha="center", va="bottom", color="white", fontsize=8)

    # Diffusion ratio
    bars2 = ax2.bar(x, D_vals, color="#f39c12", edgecolor="#1a1a2e", linewidth=0.5)
    ax2.set_xlabel("Particle", color="white", fontsize=10)
    ax2.set_ylabel("D_mucus / D_water", color="white", fontsize=10)
    ax2.set_title("Diffusion Retardation", color="white", fontsize=12)
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(names, rotation=45, ha="right", color="white", fontsize=8)
    ax2.set_ylim(0, 1.05)
    ax2.set_facecolor("#16213e")
    ax2.tick_params(colors="white")
    for bar_val, bar_obj in zip(D_vals, bars2):
        ax2.text(bar_obj.get_x() + bar_obj.get_width() / 2, bar_val + 0.02,
                 f"{bar_val:.3f}", ha="center", va="bottom", color="white", fontsize=8)

    fig.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        return None
    else:
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()


def generate_mucolytic_chart(
    agent_name: str,
    concentrations_mM: List[float],
    n_ss: int = 50,
    mesh_nm: float = _MESH_SIZE_PHYSIOLOGICAL_NM,
    output_path: str = "",
) -> Optional[bytes]:
    """Generate mucolytic dose-response chart.

    2-panel: left = fraction cleaved + mesh size vs concentration
             right = viscosity ratio vs concentration

    Returns PNG bytes if no output_path.
    """
    if not MATPLOTLIB_AVAILABLE or not concentrations_mM:
        return None

    results = [simulate_mucolytic_cleavage(agent_name, c, n_ss, mesh_nm) for c in concentrations_mM]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")

    concs = [r.concentration_mM for r in results]
    fracs = [r.fraction_cleaved for r in results]
    meshes = [r.mesh_size_after_nm for r in results]
    viscs = [r.viscosity_ratio for r in results]

    # Left: cleavage fraction + mesh size
    color1 = "#e74c3c"
    ax1.plot(concs, fracs, "o-", color=color1, label="Fraction cleaved", linewidth=2)
    ax1.set_xlabel("Concentration (mM)", color="white", fontsize=10)
    ax1.set_ylabel("Fraction S-S Cleaved", color=color1, fontsize=10)
    ax1.set_facecolor("#16213e")
    ax1.tick_params(colors="white")
    ax1.set_ylim(0, 1.05)

    ax1b = ax1.twinx()
    color2 = "#3498db"
    ax1b.plot(concs, meshes, "s--", color=color2, label="Mesh size (nm)", linewidth=2)
    ax1b.set_ylabel("Mesh Size (nm)", color=color2, fontsize=10)
    ax1b.tick_params(axis="y", labelcolor=color2)

    ax1.set_title(f"{agent_name}: Dose-Response", color="white", fontsize=12)

    # Right: viscosity ratio
    ax2.plot(concs, viscs, "D-", color="#2ecc71", linewidth=2)
    ax2.set_xlabel("Concentration (mM)", color="white", fontsize=10)
    ax2.set_ylabel("Viscosity Ratio (after/before)", color="white", fontsize=10)
    ax2.set_title("Mucus Viscosity Change", color="white", fontsize=12)
    ax2.set_facecolor("#16213e")
    ax2.tick_params(colors="white")
    ax2.set_ylim(0, 1.05)
    ax2.axhline(y=0.5, color="#e74c3c", linestyle=":", alpha=0.5, label="50% reduction")
    ax2.legend(facecolor="#16213e", edgecolor="white", labelcolor="white")

    fig.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        return None
    else:
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()


# ---------------------------------------------------------------------------
# Network 3D data export (for OpenGL renderer)
# ---------------------------------------------------------------------------

def get_network_3d_data(
    nodes: List[MucinNode],
    edges: List[MucinEdge],
) -> Dict:
    """Export network as 3D-renderable data dict for OpenGL/popup_3d.

    Returns dict with:
    - 'nodes': list of {id, x, y, z, charge, is_crosslink}
    - 'edges': list of {source, target, bond_type, intact, length}
    - 'bounds': {min_x, max_x, min_y, max_y, min_z, max_z}
    """
    node_list = []
    for nd in nodes:
        node_list.append({
            "id": nd.node_id,
            "x": nd.x,
            "y": nd.y,
            "z": nd.z,
            "charge": nd.charge,
            "is_crosslink": nd.is_crosslink,
        })

    edge_list = []
    for e in edges:
        edge_list.append({
            "source": e.source,
            "target": e.target,
            "bond_type": e.bond_type,
            "intact": e.is_intact,
            "length": e.length_nm,
        })

    if nodes:
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        zs = [n.z for n in nodes]
        bounds = {
            "min_x": min(xs), "max_x": max(xs),
            "min_y": min(ys), "max_y": max(ys),
            "min_z": min(zs), "max_z": max(zs),
        }
    else:
        bounds = {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0, "min_z": 0, "max_z": 0}

    return {"nodes": node_list, "edges": edge_list, "bounds": bounds}


# ---------------------------------------------------------------------------
# Full analysis pipeline
# ---------------------------------------------------------------------------

def run_mucin_analysis(
    drug_smiles: str,
    drug_name: str = "",
    pH: float = 7.4,
    mucin_conc_mg_ml: float = 20.0,
    mucolytic_agent: Optional[str] = None,
    mucolytic_conc_mM: float = 10.0,
    peg_mw: float = 0.0,
    peg_density: float = 0.0,
    particle_radius_nm: float = 0.0,
) -> MucinAnalysisResult:
    """Run complete mucin network analysis for a drug molecule.

    Pipeline:
    1. Build mucin network at given pH and concentration
    2. Calculate pH-dependent mesh size
    3. Estimate drug hydrodynamic radius
    4. Ogston sieving analysis
    5. Electrostatic interaction mapping
    6. (Optional) Mucolytic cleavage simulation
    7. (Optional) PEGylation stealth analysis

    Parameters
    ----------
    drug_smiles : str
    drug_name : str
    pH : float
    mucin_conc_mg_ml : float
    mucolytic_agent : str or None
    mucolytic_conc_mM : float
    peg_mw : float (0 = no PEGylation)
    peg_density : float (chains/nm^2)
    particle_radius_nm : float (0 = estimate from SMILES)

    Returns
    -------
    MucinAnalysisResult
    """
    if not MUCIN_NETWORK_AVAILABLE:
        return MucinAnalysisResult(
            success=False,
            error="NetworkX or NumPy not available",
        )

    try:
        # 1. Build network
        params = MucinNetworkParams(
            pH=pH,
            mucin_concentration_mg_ml=mucin_conc_mg_ml,
        )
        mesh_base = _MESH_SIZE_PHYSIOLOGICAL_NM * (20.0 / max(mucin_conc_mg_ml, 1.0)) ** 0.5
        mesh_ph, mesh_desc = calculate_ph_dependent_mesh_size(mesh_base, pH)
        params.mesh_size_nm = mesh_ph

        G, nodes, edges = build_mucin_network(params)

        # Network statistics
        n_ss = sum(1 for e in edges if e.bond_type == "disulfide")
        n_ent = sum(1 for e in edges if e.bond_type == "entanglement")
        n_bb = sum(1 for e in edges if e.bond_type == "backbone")
        n_components = nx.number_connected_components(G) if G is not None else 0

        network_stats = {
            "n_nodes": len(nodes),
            "n_edges": len(edges),
            "n_disulfide": n_ss,
            "n_entanglement": n_ent,
            "n_backbone": n_bb,
            "n_connected_components": n_components,
            "mesh_size_nm": mesh_ph,
            "mesh_description": mesh_desc,
            "box_side_nm": round(1000.0 * (20.0 / max(mucin_conc_mg_ml, 1.0)) ** (1.0 / 3.0), 1),
            "mucin_conc_mg_ml": mucin_conc_mg_ml,
            "pH": pH,
        }

        # 2. Estimate drug size
        if particle_radius_nm <= 0:
            r_h, r_method = estimate_hydrodynamic_radius_nm(drug_smiles)
        else:
            r_h = particle_radius_nm
            r_method = "user-specified"

        # 3. Ogston sieving
        ogston_drug = ogston_sieving(
            particle_radius_nm=r_h,
            mesh_size_nm=mesh_ph,
            mucin_conc_mg_ml=mucin_conc_mg_ml,
        )
        ogston_drug.particle_name = drug_name or drug_smiles[:30]

        # Also compute for reference particles
        reference_particles = [
            ("IgG antibody", 5.0),       # ~5 nm radius
            ("AAV vector", 12.5),         # ~25 nm diameter
            ("100nm nanoparticle", 50.0),
            ("500nm microparticle", 250.0),
        ]
        ogston_results = [ogston_drug]
        for name, r_nm in reference_particles:
            res = ogston_sieving(r_nm, mesh_ph, mucin_conc_mg_ml=mucin_conc_mg_ml)
            res.particle_name = name
            ogston_results.append(res)

        # 4. Electrostatic interaction
        electro = calculate_electrostatic_interaction(drug_smiles, pH)

        # 5. Mucolytic (optional)
        mucolytic_result = None
        if mucolytic_agent and mucolytic_agent in _MUCOLYTIC_DB:
            mucolytic_result = simulate_mucolytic_cleavage(
                mucolytic_agent, mucolytic_conc_mM,
                n_disulfide_bonds=n_ss,
                mesh_size_nm=mesh_ph,
            )

        # 6. PEGylation (optional)
        peg_result = None
        if peg_mw > 0 and peg_density > 0:
            peg_result = calculate_pegylation_effect(
                peg_mw=peg_mw,
                peg_density=peg_density,
                particle_radius_nm=r_h,
            )

        # Node positions for 3D rendering
        node_positions = [(n.x, n.y, n.z) for n in nodes]
        edge_tuples = [(e.source, e.target, e.bond_type, e.is_intact) for e in edges]

        return MucinAnalysisResult(
            success=True,
            params=params,
            network_stats=network_stats,
            ogston_results=ogston_results,
            mucolytic_result=mucolytic_result,
            pegylation_result=peg_result,
            electrostatic_result=electro,
            node_positions=node_positions,
            edges=edge_tuples,
        )

    except Exception as exc:
        logger.warning("Mucin analysis failed: %s", exc, exc_info=True)
        return MucinAnalysisResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Report generation (Korean text for DryLab PDF)
# ---------------------------------------------------------------------------

def format_mucin_report(result: MucinAnalysisResult) -> str:
    """Format mucin analysis result as Korean text for DryLab PDF.

    Returns
    -------
    str -- formatted report text
    """
    if not result.success:
        return f"점막 분석 실패: {result.error}"

    lines = []
    lines.append("=== 점막(Mucin) 네트워크 분석 결과 ===\n")

    # Network stats — N코드: 외부 데이터 타입 가드
    ns = result.network_stats
    if not isinstance(ns, dict):
        logger.warning("network_stats is not dict: type=%s", type(ns).__name__)
        ns = {}
    lines.append(f"pH: {ns.get('pH', 7.4)}")
    lines.append(f"뮤신 농도: {ns.get('mucin_conc_mg_ml', 20)} mg/mL")
    lines.append(f"메쉬 크기: {ns.get('mesh_size_nm', 0)} nm")
    lines.append(f"네트워크 상태: {ns.get('mesh_description', '')}")
    lines.append(f"이황화 결합: {ns.get('n_disulfide', 0)}개")
    lines.append(f"물리적 엉킴: {ns.get('n_entanglement', 0)}개")
    lines.append(f"연결 성분: {ns.get('n_connected_components', 0)}개\n")

    # Ogston results — N코드: list 타입 가드
    if result.ogston_results and isinstance(result.ogston_results, list):
        lines.append("--- Ogston 체거름(Sieving) 분석 ---")
        for og in result.ogston_results:
            lines.append(
                f"  {og.particle_name}: r={og.particle_radius_nm}nm, "
                f"P={og.penetration_probability:.4f}, "
                f"D/D0={og.diffusion_ratio:.4f}, "
                f"분류={og.classification}"
            )
        lines.append("")

    # Electrostatic
    if result.electrostatic_result:
        er = result.electrostatic_result
        lines.append("--- 정전기적 상호작용 ---")
        lines.append(f"  약물 순전하(pH {ns.get('pH', 7.4)}): {er.drug_charge_pH74:+.2f}")
        lines.append(f"  상호작용 에너지: {er.interaction_energy_kT:.3f} kT")
        lines.append(f"  상호작용 유형: {er.interaction_type}")
        lines.append(f"  결합 확률: {er.binding_probability:.4f}")
        lines.append(f"  해석: {er.notes}\n")

    # Mucolytic
    if result.mucolytic_result:
        mr = result.mucolytic_result
        lines.append("--- 거담제(Mucolytic) 시뮬레이션 ---")
        lines.append(f"  거담제: {mr.agent_name} ({mr.concentration_mM} mM)")
        lines.append(f"  작용 기전: {mr.mechanism}")
        lines.append(f"  S-S 절단율: {mr.fraction_cleaved*100:.1f}%")
        lines.append(f"  메쉬 크기 변화: {mr.mesh_size_before_nm} -> {mr.mesh_size_after_nm} nm")
        lines.append(f"  점도 변화: {mr.viscosity_ratio:.4f}x (1.0=무변화, 0=완전 액화)")
        lines.append(f"  네트워크 조각: {mr.network_fragments}개\n")

    # PEGylation
    if result.pegylation_result:
        pr = result.pegylation_result
        lines.append("--- PEGylation 스텔스 효과 ---")
        lines.append(f"  PEG MW: {pr.peg_mw:.0f} Da")
        lines.append(f"  그래프팅 밀도: {pr.peg_density:.3f} chains/nm^2")
        lines.append(f"  브러시 높이: {pr.brush_height_nm:.2f} nm")
        lines.append(f"  전하 차폐: {pr.charge_shielding*100:.1f}%")
        lines.append(f"  투과 향상: {pr.penetration_enhancement:.1f}x")
        lines.append(f"  분류: {pr.classification}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chart data for matplotlib (DryLab/GUI integration)
# ---------------------------------------------------------------------------

def generate_mucin_chart_data(result: MucinAnalysisResult) -> Dict:
    """Generate chart-ready data dict for DryLab PDF or GUI plots.

    Returns
    -------
    dict with keys: 'ogston_bars', 'mucolytic_curve', 'electrostatic_map'
    """
    data: Dict = {}

    if result.ogston_results:
        data["ogston_bars"] = {
            "names": [r.particle_name for r in result.ogston_results],
            "penetration": [r.penetration_probability for r in result.ogston_results],
            "diffusion": [r.diffusion_ratio for r in result.ogston_results],
            "classification": [r.classification for r in result.ogston_results],
        }

    if result.mucolytic_result:
        mr = result.mucolytic_result
        data["mucolytic_summary"] = {
            "agent": mr.agent_name,
            "concentration_mM": mr.concentration_mM,
            "fraction_cleaved": mr.fraction_cleaved,
            "mesh_before": mr.mesh_size_before_nm,
            "mesh_after": mr.mesh_size_after_nm,
            "viscosity_ratio": mr.viscosity_ratio,
        }

    if result.electrostatic_result:
        er = result.electrostatic_result
        data["electrostatic"] = {
            "drug_charge": er.drug_charge_pH74,
            "interaction_kT": er.interaction_energy_kT,
            "type": er.interaction_type,
            "binding_prob": er.binding_probability,
        }

    return data


# ---------------------------------------------------------------------------
# QThread worker (for non-blocking GUI integration)
# ---------------------------------------------------------------------------

class MucinAnalysisThread(QThread):
    """Background thread for mucin network analysis.

    Signals
    -------
    finished : MucinAnalysisResult
    progress : str (status message)
    error : str
    """
    finished = pyqtSignal(object)  # MucinAnalysisResult
    progress = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        drug_smiles: str,
        drug_name: str = "",
        pH: float = 7.4,
        mucin_conc_mg_ml: float = 20.0,
        mucolytic_agent: Optional[str] = None,
        mucolytic_conc_mM: float = 10.0,
        peg_mw: float = 0.0,
        peg_density: float = 0.0,
        particle_radius_nm: float = 0.0,
        parent=None,
    ):
        super().__init__(parent)
        self._smiles = drug_smiles
        self._name = drug_name
        self._pH = pH
        self._conc = mucin_conc_mg_ml
        self._mucolytic = mucolytic_agent
        self._mucolytic_conc = mucolytic_conc_mM
        self._peg_mw = peg_mw
        self._peg_density = peg_density
        self._particle_r = particle_radius_nm

    def run(self):
        """Execute analysis pipeline in background thread."""
        try:
            self.progress.emit("Building mucin network...")
            result = run_mucin_analysis(
                drug_smiles=self._smiles,
                drug_name=self._name,
                pH=self._pH,
                mucin_conc_mg_ml=self._conc,
                mucolytic_agent=self._mucolytic,
                mucolytic_conc_mM=self._mucolytic_conc,
                peg_mw=self._peg_mw,
                peg_density=self._peg_density,
                particle_radius_nm=self._particle_r,
            )
            self.progress.emit("Analysis complete.")
            self.finished.emit(result)
        except Exception as exc:
            logger.warning("MucinAnalysisThread failed: %s", exc, exc_info=True)
            self.error.emit(str(exc))
