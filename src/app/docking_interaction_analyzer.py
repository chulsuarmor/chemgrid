# docking_interaction_analyzer.py (v2.0 - Protein-Ligand Interaction Analysis)
"""
ChemDraw Pro: Post-docking interaction detection and 2D visualization
- Hydrogen bond detection (explicit donor-acceptor pairs + distance criteria)
- Hydrophobic contact detection
- Pi-stacking detection (aromatic ring centroids + normal vector angle validation)
- Salt bridge detection (charged group proximity)
- Halogen bond detection (C-X···Y, X=F/Cl/Br/I)
- Spatial hashing (5A grid) for O(n) proximity filtering
- 2D interaction diagram generation (matplotlib)

v2.0 changes:
  - BUG-DOCK-003: Refactored H-bond with explicit donor-acceptor pair validation
  - BUG-DOCK-005: Added spatial hashing (5A grid) for O(n) proximity filtering
  - BUG-DOCK-006: Added pi-stacking ring normal vector angle validation
  - Added halogen bond detection
"""

import logging
import math
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from docking_data import (
    PDBAtom, ReceptorData, DockingPose, Interaction, LigandData
)


# ============================================================================
# INTERACTION DETECTION CONSTANTS
# ============================================================================

# Hydrogen bond criteria
HBOND_DIST_MAX = 3.5          # Angstroms (donor-acceptor distance)
HBOND_ANGLE_MIN = 120.0       # degrees

# Hydrophobic contact criteria
HYDROPHOBIC_DIST_MAX = 4.0    # Angstroms

# Pi-stacking criteria
PI_STACK_DIST_MAX = 5.5       # Angstroms (centroid-centroid)
PI_STACK_ANGLE_MAX = 30.0     # degrees from parallel (face-to-face)
PI_STACK_ANGLE_T_MIN = 60.0   # degrees (T-shaped)

# Salt bridge criteria
SALT_BRIDGE_DIST_MAX = 4.0    # Angstroms

# Halogen bond criteria
HALOGEN_BOND_DIST_MAX = 3.5   # Angstroms (X···acceptor distance)
HALOGEN_BOND_ANGLE_MIN = 120.0  # degrees (C-X···acceptor angle, valid range 120-180)
HALOGEN_BOND_ANGLE_MAX = 180.0  # degrees (upper bound, ideally ~165)

# Spatial hashing grid size (Angstroms) — must be >= largest interaction cutoff
SPATIAL_GRID_SIZE = 5.5

# Element properties
HBOND_DONORS = {"N", "O", "S"}
HBOND_ACCEPTORS = {"N", "O", "S", "F"}
HYDROPHOBIC_ELEMENTS = {"C"}
HALOGEN_ELEMENTS = {"F", "Cl", "Br", "I"}
HALOGEN_ACCEPTORS = {"N", "O", "S"}
AROMATIC_RESIDUES = {"PHE", "TYR", "TRP", "HIS"}
POSITIVE_RESIDUES = {"ARG", "LYS", "HIS"}
NEGATIVE_RESIDUES = {"ASP", "GLU"}


# ============================================================================
# SPATIAL HASH GRID (BUG-DOCK-005 fix)
# ============================================================================

class SpatialHash:
    """Grid-based spatial index for O(n) proximity queries.

    Divides 3D space into cubic cells of `cell_size` Angstroms.
    For each query point, only atoms in the 27 neighboring cells are checked.
    """

    def __init__(self, cell_size: float = SPATIAL_GRID_SIZE):
        self.cell_size = cell_size
        self._grid: Dict[Tuple[int, int, int], List[PDBAtom]] = defaultdict(list)

    def _cell_key(self, x: float, y: float, z: float) -> Tuple[int, int, int]:
        return (
            int(math.floor(x / self.cell_size)),
            int(math.floor(y / self.cell_size)),
            int(math.floor(z / self.cell_size)),
        )

    def insert(self, atom: PDBAtom) -> None:
        key = self._cell_key(atom.x, atom.y, atom.z)
        self._grid[key].append(atom)

    def build_from_atoms(self, atoms: List[PDBAtom]) -> None:
        """Bulk-insert all protein atoms."""
        self._grid.clear()
        for atom in atoms:
            self.insert(atom)

    def query_nearby(self, x: float, y: float, z: float,
                     radius: float) -> List[PDBAtom]:
        """Return all atoms within `radius` of (x, y, z).

        Checks the 27 neighboring cells (3x3x3 block).
        Final distance check ensures exact cutoff.
        """
        cx, cy, cz = self._cell_key(x, y, z)
        r2 = radius * radius
        result = []
        # How many cells to check in each direction
        n_cells = max(1, int(math.ceil(radius / self.cell_size)))
        for dx in range(-n_cells, n_cells + 1):
            for dy in range(-n_cells, n_cells + 1):
                for dz in range(-n_cells, n_cells + 1):
                    key = (cx + dx, cy + dy, cz + dz)
                    for atom in self._grid.get(key, ()):
                        d2 = (atom.x - x)**2 + (atom.y - y)**2 + (atom.z - z)**2
                        if d2 <= r2:
                            result.append(atom)
        return result


# ============================================================================
# INTERACTION ANALYZER
# ============================================================================

class InteractionAnalyzer:
    """Analyze protein-ligand interactions from docking poses"""

    @staticmethod
    def analyze_pose(receptor: ReceptorData, pose: DockingPose,
                     ligand: Optional[LigandData] = None) -> List[Interaction]:
        """Detect all interactions for a single docking pose"""
        interactions = []

        # Type guard: ensure pose and receptor are valid types (Rule N)
        if not isinstance(pose, DockingPose):
            logger.warning("analyze_pose: invalid pose type: %s", type(pose).__name__)
            return interactions
        if not isinstance(receptor, ReceptorData):
            logger.warning("analyze_pose: invalid receptor type: %s", type(receptor).__name__)
            return interactions

        if not pose.atom_coords or not receptor.atoms:
            logger.warning("analyze_pose: empty atom_coords (%s) or receptor.atoms (%s)",
                           len(pose.atom_coords) if pose.atom_coords else 0,
                           len(receptor.atoms) if receptor.atoms else 0)
            return interactions

        # Build spatial hash for O(n) proximity queries (BUG-DOCK-005)
        spatial = SpatialHash(SPATIAL_GRID_SIZE)
        spatial.build_from_atoms(receptor.atoms)

        # Build residue lookup (still needed for pi-stacking and salt bridges)
        residue_atoms: Dict[Tuple[str, int, str], List[PDBAtom]] = {}
        for atom in receptor.atoms:
            key = (atom.residue_name, atom.residue_id, atom.chain)
            if key not in residue_atoms:
                residue_atoms[key] = []
            residue_atoms[key].append(atom)

        # Detect each interaction type
        interactions.extend(
            InteractionAnalyzer._detect_hydrogen_bonds(pose, spatial)
        )
        interactions.extend(
            InteractionAnalyzer._detect_hydrophobic_contacts(pose, spatial)
        )
        interactions.extend(
            InteractionAnalyzer._detect_pi_stacking(pose, residue_atoms)
        )
        interactions.extend(
            InteractionAnalyzer._detect_salt_bridges(pose, residue_atoms)
        )
        interactions.extend(
            InteractionAnalyzer._detect_halogen_bonds(pose, spatial)
        )

        # Deduplicate by residue (keep closest interaction per type per residue)
        interactions = InteractionAnalyzer._deduplicate(interactions)

        return interactions

    @staticmethod
    def _detect_hydrogen_bonds(pose: DockingPose,
                                spatial: SpatialHash) -> List[Interaction]:
        """Detect hydrogen bonds using explicit donor-acceptor pair validation.

        BUG-DOCK-003 fix: Instead of complex nested conditions, we explicitly
        check that one atom is a donor and the other is an acceptor.
        Valid H-bond pairs:
          - Ligand donor (N, O, S) --- Protein acceptor (N, O, S, F)
          - Ligand acceptor (N, O, S, F) --- Protein donor (N, O, S)
        """
        hbonds = []

        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else ''
            # Carbon = '' (empty string) in ChemGrid convention
            if lig_elem in ('', 'C', 'H'):
                continue

            lig_is_donor = lig_elem in HBOND_DONORS
            lig_is_acceptor = lig_elem in HBOND_ACCEPTORS

            if not lig_is_donor and not lig_is_acceptor:
                continue

            # Spatial hash query: only check nearby protein atoms
            nearby = spatial.query_nearby(lx, ly, lz, HBOND_DIST_MAX)

            for patom in nearby:
                p_elem = patom.element
                if not p_elem or p_elem in ('C', 'H'):
                    continue

                p_is_donor = p_elem in HBOND_DONORS
                p_is_acceptor = p_elem in HBOND_ACCEPTORS

                # Explicit donor-acceptor pair check (BUG-DOCK-003)
                valid_pair = False
                if lig_is_donor and p_is_acceptor:
                    valid_pair = True
                if lig_is_acceptor and p_is_donor:
                    valid_pair = True
                if not valid_pair:
                    continue

                dist = _distance_3d(lx, ly, lz, patom.x, patom.y, patom.z)
                if dist < HBOND_DIST_MAX and dist > 0.5:  # avoid self-overlap artifacts
                    hbonds.append(Interaction(
                        type="hydrogen_bond",
                        ligand_atom_idx=lig_idx,
                        protein_atom_name=patom.name,
                        residue_name=patom.residue_name,
                        residue_id=patom.residue_id,
                        chain=patom.chain,
                        distance=round(dist, 2),
                    ))

        return hbonds

    @staticmethod
    def _detect_hydrophobic_contacts(pose: DockingPose,
                                      spatial: SpatialHash) -> List[Interaction]:
        """Detect hydrophobic contacts (C-C proximity) using spatial hash."""
        contacts = []

        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else ''
            # Carbon = '' (empty string) OR 'C' in ChemGrid
            if lig_elem not in HYDROPHOBIC_ELEMENTS and lig_elem != '':
                continue

            nearby = spatial.query_nearby(lx, ly, lz, HYDROPHOBIC_DIST_MAX)

            for patom in nearby:
                if patom.element not in HYDROPHOBIC_ELEMENTS:
                    continue

                dist = _distance_3d(lx, ly, lz, patom.x, patom.y, patom.z)
                if dist < HYDROPHOBIC_DIST_MAX and dist > 0.5:
                    contacts.append(Interaction(
                        type="hydrophobic",
                        ligand_atom_idx=lig_idx,
                        protein_atom_name=patom.name,
                        residue_name=patom.residue_name,
                        residue_id=patom.residue_id,
                        chain=patom.chain,
                        distance=round(dist, 2),
                    ))

        return contacts

    @staticmethod
    def _detect_pi_stacking(pose: DockingPose,
                             residue_atoms: dict) -> List[Interaction]:
        """Detect pi-stacking with ring normal vector angle validation.

        BUG-DOCK-006 fix: In addition to centroid distance, we compute
        ring normal vectors and validate the angle:
          - Face-to-face (parallel): angle < 30 degrees
          - T-shaped (edge-to-face): angle > 60 degrees
        Interactions between 30-60 degrees are rejected (unlikely pi-stacking).
        """
        stackings = []

        # Find aromatic rings in ligand with normal vectors
        lig_rings = _find_ring_centroids_with_normals(
            pose.atom_coords, pose.atom_elements
        )

        for (res_name, res_id, chain), atoms in residue_atoms.items():
            if res_name not in AROMATIC_RESIDUES:
                continue

            # Get aromatic ring atoms of residue
            ring_atoms = [a for a in atoms if a.name.strip() in
                          {"CG", "CD1", "CD2", "CE1", "CE2", "CZ", "CH2",
                           "NE1", "CE3", "CZ2", "CZ3"}]
            if len(ring_atoms) < 4:
                continue

            # Protein ring centroid
            rx = sum(a.x for a in ring_atoms) / len(ring_atoms)
            ry = sum(a.y for a in ring_atoms) / len(ring_atoms)
            rz = sum(a.z for a in ring_atoms) / len(ring_atoms)

            # Protein ring normal vector
            p_normal = _compute_ring_normal(
                [(a.x, a.y, a.z) for a in ring_atoms]
            )

            for lig_centroid_idx, (lx, ly, lz), lig_normal in lig_rings:
                dist = _distance_3d(lx, ly, lz, rx, ry, rz)
                if dist >= PI_STACK_DIST_MAX:
                    continue

                # Angle validation (BUG-DOCK-006)
                if p_normal is not None and lig_normal is not None:
                    angle = _angle_between_normals(lig_normal, p_normal)
                    # Accept face-to-face (< 30 deg) or T-shaped (> 60 deg)
                    if PI_STACK_ANGLE_MAX < angle < PI_STACK_ANGLE_T_MIN:
                        continue  # Reject ambiguous angles

                    stacking_type = "pi_stacking"
                else:
                    # No normal vector available — accept based on distance only
                    stacking_type = "pi_stacking"
                    angle = None

                stackings.append(Interaction(
                    type=stacking_type,
                    ligand_atom_idx=lig_centroid_idx,
                    protein_atom_name="RING",
                    residue_name=res_name,
                    residue_id=res_id,
                    chain=chain,
                    distance=round(dist, 2),
                    angle=round(angle, 1) if angle is not None else None,
                ))

        return stackings

    @staticmethod
    def _detect_salt_bridges(pose: DockingPose,
                              residue_atoms: dict) -> List[Interaction]:
        """Detect salt bridges between charged groups"""
        bridges = []

        # Simplified: check ligand N/O atoms near charged residues
        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else ''
            if lig_elem not in {"N", "O"}:
                continue

            for (res_name, res_id, chain), atoms in residue_atoms.items():
                if res_name not in POSITIVE_RESIDUES and res_name not in NEGATIVE_RESIDUES:
                    continue

                # Check charged atoms in residue
                charged_atom_names = set()
                if res_name == "ARG":
                    charged_atom_names = {"NH1", "NH2", "NE"}
                elif res_name == "LYS":
                    charged_atom_names = {"NZ"}
                elif res_name == "ASP":
                    charged_atom_names = {"OD1", "OD2"}
                elif res_name == "GLU":
                    charged_atom_names = {"OE1", "OE2"}
                elif res_name == "HIS":
                    charged_atom_names = {"ND1", "NE2"}

                for patom in atoms:
                    if patom.name.strip() not in charged_atom_names:
                        continue

                    dist = _distance_3d(lx, ly, lz, patom.x, patom.y, patom.z)
                    if dist < SALT_BRIDGE_DIST_MAX:
                        bridges.append(Interaction(
                            type="salt_bridge",
                            ligand_atom_idx=lig_idx,
                            protein_atom_name=patom.name,
                            residue_name=res_name,
                            residue_id=res_id,
                            chain=chain,
                            distance=round(dist, 2),
                        ))

        return bridges

    @staticmethod
    def _detect_halogen_bonds(pose: DockingPose,
                               spatial: SpatialHash) -> List[Interaction]:
        """Detect halogen bonds (C-X···Y where X is halogen, Y is acceptor).

        Halogen bonds are common in drug molecules containing F, Cl, Br, I.
        The C-X···Y angle should be approximately linear (120-180 degrees).

        TASK-DOCK-006: Added C-X···O/N angle validation.
        A halogen bond requires:
          1. Distance X···acceptor < 3.5 A
          2. C-X···acceptor angle in range [120, 180] degrees
        The carbon bonded to the halogen is found by searching for the
        nearest carbon neighbor in the ligand coordinates.
        """
        halbonds = []

        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else ''
            if lig_elem not in HALOGEN_ELEMENTS:
                continue

            # Find the bonded carbon (C-X): nearest carbon/'' atom to this halogen
            # Carbon is stored as '' (empty string) or 'C' in ChemGrid convention
            bonded_carbon_coord = _find_bonded_carbon(
                lig_idx, pose.atom_coords, pose.atom_elements
            )

            nearby = spatial.query_nearby(lx, ly, lz, HALOGEN_BOND_DIST_MAX)

            for patom in nearby:
                if patom.element not in HALOGEN_ACCEPTORS:
                    continue

                dist = _distance_3d(lx, ly, lz, patom.x, patom.y, patom.z)
                if not (0.5 < dist < HALOGEN_BOND_DIST_MAX):
                    continue

                # Angle validation: C-X···Acceptor (TASK-DOCK-006)
                angle = None
                if bonded_carbon_coord is not None:
                    try:
                        angle = _angle_three_points(
                            bonded_carbon_coord,   # C (vertex start)
                            (lx, ly, lz),          # X (halogen, vertex)
                            (patom.x, patom.y, patom.z),  # Acceptor (vertex end)
                        )
                    except Exception as e:
                        logger.warning("Halogen bond angle calculation failed for "
                                       "lig_idx=%d, patom=%s: %s", lig_idx, patom.name, e)
                        angle = None

                    # Reject if angle is outside valid halogen bond range
                    if angle is not None and not (HALOGEN_BOND_ANGLE_MIN <= angle <= HALOGEN_BOND_ANGLE_MAX):
                        continue
                # If no bonded carbon found, accept based on distance only
                # (graceful fallback — better to report a possible interaction
                # than to silently discard it when geometry is unavailable)

                halbonds.append(Interaction(
                    type="halogen_bond",
                    ligand_atom_idx=lig_idx,
                    protein_atom_name=patom.name,
                    residue_name=patom.residue_name,
                    residue_id=patom.residue_id,
                    chain=patom.chain,
                    distance=round(dist, 2),
                    angle=round(angle, 1) if angle is not None else None,
                ))

        return halbonds

    @staticmethod
    def _deduplicate(interactions: List[Interaction]) -> List[Interaction]:
        """Keep only the closest interaction per type per residue"""
        best: Dict[Tuple[str, str, int, str], Interaction] = {}
        for inter in interactions:
            key = (inter.type, inter.residue_name, inter.residue_id, inter.chain)
            if key not in best or inter.distance < best[key].distance:
                best[key] = inter
        return list(best.values())

    @staticmethod
    def generate_2d_interaction_map(interactions: List[Interaction],
                                     ligand_name: str = "Ligand") -> Optional['Figure']:
        """Generate 2D circular interaction diagram using matplotlib"""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("generate_2d_interaction_map: matplotlib not available")
            return None
        if not isinstance(interactions, list):
            logger.warning("generate_2d_interaction_map: invalid interactions type: %s",
                           type(interactions).__name__)
            return None
        if not interactions:
            logger.warning("generate_2d_interaction_map: empty interactions list")
            return None

        fig, ax = plt.subplots(1, 1, figsize=(10, 10))
        ax.set_xlim(-2.5, 2.5)
        ax.set_ylim(-2.5, 2.5)
        ax.set_aspect('equal')
        ax.axis('off')
        fig.patch.set_facecolor('white')

        # Draw ligand at center
        ligand_circle = plt.Circle((0, 0), 0.5, color='#4CAF50', alpha=0.8, zorder=5)
        ax.add_patch(ligand_circle)
        ax.text(0, 0, ligand_name, ha='center', va='center',
                fontsize=9, fontweight='bold', color='white', zorder=6)

        # Interaction type colors and styles
        TYPE_COLORS = {
            "hydrogen_bond": "#2196F3",     # Blue
            "hydrophobic": "#FF9800",       # Orange
            "pi_stacking": "#9C27B0",       # Purple
            "salt_bridge": "#F44336",        # Red
            "halogen_bond": "#00BCD4",       # Cyan
        }
        TYPE_LINESTYLES = {
            "hydrogen_bond": "--",
            "hydrophobic": "-",
            "pi_stacking": ":",
            "salt_bridge": "-.",
            "halogen_bond": "--",
        }

        # Place residues in a circle
        unique_residues = list(set(
            (i.residue_name, i.residue_id, i.chain) for i in interactions
        ))
        n = len(unique_residues)
        if n == 0:
            return fig

        for idx, (res_name, res_id, chain) in enumerate(unique_residues):
            angle = 2 * math.pi * idx / n - math.pi / 2
            rx = 1.8 * math.cos(angle)
            ry = 1.8 * math.sin(angle)

            # Get interactions for this residue
            res_interactions = [
                i for i in interactions
                if i.residue_name == res_name and i.residue_id == res_id and i.chain == chain
            ]

            # Residue background color based on primary interaction
            if res_interactions:
                primary_type = res_interactions[0].type
                bg_color = TYPE_COLORS.get(primary_type, "#9E9E9E")
            else:
                bg_color = "#9E9E9E"

            # Draw residue circle
            res_circle = plt.Circle((rx, ry), 0.35, color=bg_color, alpha=0.3, zorder=3)
            ax.add_patch(res_circle)
            res_circle_border = plt.Circle((rx, ry), 0.35, fill=False,
                                           edgecolor=bg_color, linewidth=2, zorder=4)
            ax.add_patch(res_circle_border)

            # Residue label
            label = f"{res_name}\n{res_id}"
            ax.text(rx, ry, label, ha='center', va='center',
                    fontsize=8, fontweight='bold', zorder=5)

            # Draw interaction lines
            for inter in res_interactions:
                color = TYPE_COLORS.get(inter.type, "#9E9E9E")
                ls = TYPE_LINESTYLES.get(inter.type, "-")

                ax.plot([0, rx], [0, ry], color=color, linestyle=ls,
                        linewidth=1.5, alpha=0.7, zorder=2)

                # Distance label at midpoint
                mx, my = rx/2, ry/2
                ax.text(mx, my, f"{inter.distance}\u00c5",
                        fontsize=7, ha='center', va='center',
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                  edgecolor=color, alpha=0.9),
                        zorder=4)

        # Legend
        legend_patches = []
        seen_types = set(i.type for i in interactions)
        for itype, color in TYPE_COLORS.items():
            if itype in seen_types:
                label = {
                    "hydrogen_bond": "H-Bond",
                    "hydrophobic": "Hydrophobic",
                    "pi_stacking": "\u03c0-Stacking",
                    "salt_bridge": "Salt Bridge",
                    "halogen_bond": "Halogen Bond",
                }.get(itype, itype)
                legend_patches.append(mpatches.Patch(color=color, label=label, alpha=0.7))

        if legend_patches:
            ax.legend(handles=legend_patches, loc='upper right',
                      fontsize=9, framealpha=0.9)

        ax.set_title("Protein-Ligand Interaction Diagram", fontsize=14, fontweight='bold', pad=20)

        plt.tight_layout()
        return fig


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _distance_3d(x1, y1, z1, x2, y2, z2) -> float:
    """Euclidean distance between two 3D points"""
    return math.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)


def _cross_product(a: Tuple[float, float, float],
                   b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Cross product of two 3D vectors."""
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    )


def _normalize(v: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    """Normalize a 3D vector. Returns None if zero-length."""
    length = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if length < 1e-10:
        return None
    return (v[0]/length, v[1]/length, v[2]/length)


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    """Dot product of two 3D vectors."""
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _compute_ring_normal(
    ring_coords: List[Tuple[float, float, float]]
) -> Optional[Tuple[float, float, float]]:
    """Compute the normal vector of a ring plane using Newell's method.

    More robust than using just 3 points — works for non-planar rings too.
    """
    if len(ring_coords) < 3:
        return None

    # Newell's method for polygon normal
    nx, ny, nz = 0.0, 0.0, 0.0
    n = len(ring_coords)
    for i in range(n):
        cur = ring_coords[i]
        nxt = ring_coords[(i + 1) % n]
        nx += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
        ny += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
        nz += (cur[0] - nxt[0]) * (cur[1] + nxt[1])

    return _normalize((nx, ny, nz))


def _find_bonded_carbon(
    halogen_idx: int,
    coords: List[Tuple[float, float, float]],
    elements: List[str],
    max_bond_dist: float = 2.2,
) -> Optional[Tuple[float, float, float]]:
    """Find the carbon atom bonded to a halogen in ligand coordinates.

    Searches for the nearest carbon (element '' or 'C' in ChemGrid convention)
    within max_bond_dist Angstroms of the halogen atom.

    Args:
        halogen_idx: Index of the halogen atom in coords/elements
        coords: List of (x, y, z) for all ligand atoms
        elements: List of element symbols for all ligand atoms
        max_bond_dist: Maximum C-X bond distance in Angstroms (default 2.2)

    Returns:
        (x, y, z) of the bonded carbon, or None if not found.
    """
    hx, hy, hz = coords[halogen_idx]
    best_dist = max_bond_dist
    best_coord = None

    for i, (cx, cy, cz) in enumerate(coords):
        if i == halogen_idx:
            continue
        elem = elements[i] if i < len(elements) else ''
        # Carbon = '' (empty string) or 'C' in ChemGrid convention
        if elem not in ('', 'C'):
            continue
        dist = _distance_3d(hx, hy, hz, cx, cy, cz)
        if dist < best_dist:
            best_dist = dist
            best_coord = (cx, cy, cz)

    return best_coord


def _angle_three_points(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
    c: Tuple[float, float, float],
) -> float:
    """Compute angle A-B-C in degrees (angle at vertex B).

    Used for C-X···Acceptor angle validation in halogen bonds.

    Args:
        a: First point (e.g., bonded carbon C)
        b: Vertex point (e.g., halogen X)
        c: Third point (e.g., acceptor O/N)

    Returns:
        Angle in degrees [0, 180].
    """
    # Vectors BA and BC
    ba = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    bc = (c[0] - b[0], c[1] - b[1], c[2] - b[2])

    dot_val = _dot(ba, bc)
    mag_ba = math.sqrt(ba[0]**2 + ba[1]**2 + ba[2]**2)
    mag_bc = math.sqrt(bc[0]**2 + bc[1]**2 + bc[2]**2)

    if mag_ba < 1e-10 or mag_bc < 1e-10:
        return 0.0

    cos_angle = dot_val / (mag_ba * mag_bc)
    # Clamp for numerical stability
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def _angle_between_normals(
    n1: Tuple[float, float, float],
    n2: Tuple[float, float, float]
) -> float:
    """Angle between two normal vectors in degrees (0-90 range).

    Since ring normals can point in either direction, we use the
    absolute value of the dot product to get angle in [0, 90].
    """
    d = abs(_dot(n1, n2))
    d = min(d, 1.0)  # clamp for numerical stability
    return math.degrees(math.acos(d))


def _find_ring_centroids_with_normals(
    coords: List[Tuple[float, float, float]],
    elements: List[str]
) -> List[Tuple[int, Tuple[float, float, float], Optional[Tuple[float, float, float]]]]:
    """Find aromatic ring centroids in ligand with normal vectors.

    Returns list of (representative_atom_index, centroid_xyz, normal_vector)
    """
    results = []

    # Find clusters of carbon atoms close together (potential rings)
    # Carbon = '' (empty string) or 'C' in ChemGrid
    carbon_indices = [i for i, e in enumerate(elements) if e in ('C', '')]

    if len(carbon_indices) < 5:
        return results

    # Simple approach: find groups of 5-6 carbons within 3A of each other
    visited: Set[int] = set()

    for ci in carbon_indices:
        if ci in visited:
            continue

        cluster = [ci]
        cx, cy, cz = coords[ci]

        for cj in carbon_indices:
            if cj == ci or cj in visited:
                continue
            dx, dy, dz = coords[cj]
            if _distance_3d(cx, cy, cz, dx, dy, dz) < 3.0:
                cluster.append(cj)

        if 5 <= len(cluster) <= 7:
            # This might be an aromatic ring
            ring_coords = [coords[i] for i in cluster]
            centroid_x = sum(c[0] for c in ring_coords) / len(ring_coords)
            centroid_y = sum(c[1] for c in ring_coords) / len(ring_coords)
            centroid_z = sum(c[2] for c in ring_coords) / len(ring_coords)

            normal = _compute_ring_normal(ring_coords)

            results.append((
                cluster[0],
                (centroid_x, centroid_y, centroid_z),
                normal,
            ))
            visited.update(cluster)

    return results


def extract_binding_site_residues(
    receptor: ReceptorData, pose: DockingPose,
    radius: float = 5.0
) -> List[Tuple[str, int, str, bool, bool]]:
    """Extract residues within `radius` Angstroms of any ligand atom.

    Returns list of (residue_name, residue_id, chain, is_hbond_donor, is_hbond_acceptor)
    for each unique residue near the ligand.

    is_hbond_donor: residue has atoms that can donate H-bonds (N-H, O-H)
    is_hbond_acceptor: residue has atoms that can accept H-bonds (O, N, S, F)
    """
    if not isinstance(pose, DockingPose):
        logger.warning("extract_binding_site_residues: invalid pose type: %s", type(pose).__name__)
        return []
    if not isinstance(receptor, ReceptorData):
        logger.warning("extract_binding_site_residues: invalid receptor type: %s", type(receptor).__name__)
        return []
    if not pose.atom_coords or not receptor.atoms:
        logger.warning("extract_binding_site_residues: empty coords or atoms")
        return []

    # Build spatial hash for efficient proximity queries
    spatial = SpatialHash(SPATIAL_GRID_SIZE)
    spatial.build_from_atoms(receptor.atoms)

    # Find all protein atoms within radius of any ligand atom
    nearby_residue_keys: Dict[Tuple[str, int, str], Dict[str, bool]] = {}

    for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
        nearby_atoms = spatial.query_nearby(lx, ly, lz, radius)
        for patom in nearby_atoms:
            key = (patom.residue_name, patom.residue_id, patom.chain)
            if key not in nearby_residue_keys:
                nearby_residue_keys[key] = {"donor": False, "acceptor": False}
            # Check H-bond capability
            elem = patom.element
            if elem in HBOND_DONORS:
                nearby_residue_keys[key]["donor"] = True
            if elem in HBOND_ACCEPTORS:
                nearby_residue_keys[key]["acceptor"] = True

    result = []
    for (res_name, res_id, chain), caps in nearby_residue_keys.items():
        result.append((res_name, res_id, chain, caps["donor"], caps["acceptor"]))

    # Sort by residue_id for consistent ordering
    result.sort(key=lambda x: (x[2], x[1]))
    return result


# Attach as static method on InteractionAnalyzer for backward compatibility
InteractionAnalyzer.extract_binding_site_residues = staticmethod(extract_binding_site_residues)


# Legacy compatibility alias
def _find_ring_centroids_simple(
    coords: List[Tuple[float, float, float]],
    elements: List[str]
) -> List[Tuple[int, Tuple[float, float, float]]]:
    """Legacy wrapper — returns (atom_idx, centroid) without normals."""
    return [
        (idx, centroid)
        for idx, centroid, _normal in _find_ring_centroids_with_normals(coords, elements)
    ]
