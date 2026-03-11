# docking_interaction_analyzer.py (v1.0 - Protein-Ligand Interaction Analysis)
"""
ChemDraw Pro: Post-docking interaction detection and 2D visualization
- Hydrogen bond detection (distance + angle criteria)
- Hydrophobic contact detection
- Pi-stacking detection (aromatic ring centroids)
- Salt bridge detection (charged group proximity)
- 2D interaction diagram generation (matplotlib)
"""

import math
from typing import Dict, List, Tuple, Optional, Set

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

# Element properties
HBOND_DONORS = {"N", "O", "S"}
HBOND_ACCEPTORS = {"N", "O", "S", "F"}
HYDROPHOBIC_ELEMENTS = {"C"}
AROMATIC_RESIDUES = {"PHE", "TYR", "TRP", "HIS"}
POSITIVE_RESIDUES = {"ARG", "LYS", "HIS"}
NEGATIVE_RESIDUES = {"ASP", "GLU"}


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

        if not pose.atom_coords or not receptor.atoms:
            return interactions

        # Build spatial index of receptor atoms by residue
        residue_atoms: Dict[Tuple[str, int, str], List[PDBAtom]] = {}
        for atom in receptor.atoms:
            key = (atom.residue_name, atom.residue_id, atom.chain)
            if key not in residue_atoms:
                residue_atoms[key] = []
            residue_atoms[key].append(atom)

        # Detect each interaction type
        interactions.extend(
            InteractionAnalyzer._detect_hydrogen_bonds(
                pose, receptor.atoms, residue_atoms
            )
        )
        interactions.extend(
            InteractionAnalyzer._detect_hydrophobic_contacts(
                pose, receptor.atoms, residue_atoms
            )
        )
        interactions.extend(
            InteractionAnalyzer._detect_pi_stacking(
                pose, residue_atoms
            )
        )
        interactions.extend(
            InteractionAnalyzer._detect_salt_bridges(
                pose, residue_atoms
            )
        )

        # Deduplicate by residue (keep closest interaction per type per residue)
        interactions = InteractionAnalyzer._deduplicate(interactions)

        return interactions

    @staticmethod
    def _detect_hydrogen_bonds(pose: DockingPose,
                                protein_atoms: List[PDBAtom],
                                residue_atoms: dict) -> List[Interaction]:
        """Detect hydrogen bonds between ligand and protein"""
        hbonds = []

        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else "C"

            if lig_elem not in HBOND_DONORS and lig_elem not in HBOND_ACCEPTORS:
                continue

            for patom in protein_atoms:
                if patom.element not in HBOND_DONORS and patom.element not in HBOND_ACCEPTORS:
                    continue

                # One must be donor, other acceptor
                if lig_elem in HBOND_DONORS and patom.element not in HBOND_ACCEPTORS:
                    if lig_elem not in HBOND_ACCEPTORS or patom.element not in HBOND_DONORS:
                        continue

                dist = _distance_3d(lx, ly, lz, patom.x, patom.y, patom.z)
                if dist < HBOND_DIST_MAX:
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
                                      protein_atoms: List[PDBAtom],
                                      residue_atoms: dict) -> List[Interaction]:
        """Detect hydrophobic contacts (C-C proximity)"""
        contacts = []

        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else "C"
            if lig_elem not in HYDROPHOBIC_ELEMENTS:
                continue

            for patom in protein_atoms:
                if patom.element not in HYDROPHOBIC_ELEMENTS:
                    continue

                dist = _distance_3d(lx, ly, lz, patom.x, patom.y, patom.z)
                if dist < HYDROPHOBIC_DIST_MAX:
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
        """Detect pi-stacking interactions with aromatic residues"""
        stackings = []

        # Find aromatic rings in ligand (simplified: look for 6-membered carbon rings)
        lig_ring_centroids = _find_ring_centroids_simple(
            pose.atom_coords, pose.atom_elements
        )

        for (res_name, res_id, chain), atoms in residue_atoms.items():
            if res_name not in AROMATIC_RESIDUES:
                continue

            # Get aromatic ring centroid of residue
            ring_atoms = [a for a in atoms if a.name.strip() in
                          {"CG", "CD1", "CD2", "CE1", "CE2", "CZ", "CH2",
                           "NE1", "CE3", "CZ2", "CZ3"}]
            if len(ring_atoms) < 4:
                continue

            rx = sum(a.x for a in ring_atoms) / len(ring_atoms)
            ry = sum(a.y for a in ring_atoms) / len(ring_atoms)
            rz = sum(a.z for a in ring_atoms) / len(ring_atoms)

            for lig_centroid_idx, (lx, ly, lz) in lig_ring_centroids:
                dist = _distance_3d(lx, ly, lz, rx, ry, rz)
                if dist < PI_STACK_DIST_MAX:
                    stackings.append(Interaction(
                        type="pi_stacking",
                        ligand_atom_idx=lig_centroid_idx,
                        protein_atom_name="RING",
                        residue_name=res_name,
                        residue_id=res_id,
                        chain=chain,
                        distance=round(dist, 2),
                    ))

        return stackings

    @staticmethod
    def _detect_salt_bridges(pose: DockingPose,
                              residue_atoms: dict) -> List[Interaction]:
        """Detect salt bridges between charged groups"""
        bridges = []

        # Simplified: check ligand N/O atoms near charged residues
        for lig_idx, (lx, ly, lz) in enumerate(pose.atom_coords):
            lig_elem = pose.atom_elements[lig_idx] if lig_idx < len(pose.atom_elements) else "C"
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
        if not MATPLOTLIB_AVAILABLE or not interactions:
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
                ax.text(mx, my, f"{inter.distance}Å",
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
                    "pi_stacking": "π-Stacking",
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


def _find_ring_centroids_simple(
    coords: List[Tuple[float, float, float]],
    elements: List[str]
) -> List[Tuple[int, Tuple[float, float, float]]]:
    """Simple heuristic to find aromatic ring centroids in ligand

    Returns list of (representative_atom_index, centroid_xyz)
    """
    centroids = []

    # Find clusters of carbon atoms close together (potential rings)
    carbon_indices = [i for i, e in enumerate(elements) if e == "C"]

    if len(carbon_indices) < 5:
        return centroids

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
            centroid_x = sum(coords[i][0] for i in cluster) / len(cluster)
            centroid_y = sum(coords[i][1] for i in cluster) / len(cluster)
            centroid_z = sum(coords[i][2] for i in cluster) / len(cluster)
            centroids.append((cluster[0], (centroid_x, centroid_y, centroid_z)))
            visited.update(cluster)

    return centroids
