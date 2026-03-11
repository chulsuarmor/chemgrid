# docking_data.py (v1.0 - Molecular Docking Data Structures)
"""
ChemDraw Pro: Data structures for molecular docking simulation
- Receptor (protein) data from PDB files
- Ligand data from canvas SMILES
- Docking configuration and results
- Protein-ligand interaction types
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional


@dataclass
class PDBAtom:
    """Single atom from a PDB file"""
    serial: int
    name: str           # atom name (e.g., "CA", "CB", "N")
    residue_name: str   # residue name (e.g., "ALA", "GLY")
    chain: str          # chain identifier
    residue_id: int     # residue sequence number
    x: float
    y: float
    z: float
    element: str        # element symbol
    occupancy: float = 1.0
    b_factor: float = 0.0
    is_hetatm: bool = False


@dataclass
class Residue:
    """Protein residue (amino acid)"""
    name: str           # 3-letter code (e.g., "ALA")
    chain: str
    residue_id: int
    atoms: List[PDBAtom] = field(default_factory=list)

    @property
    def ca_position(self) -> Optional[Tuple[float, float, float]]:
        """Get C-alpha position for backbone tracing"""
        for atom in self.atoms:
            if atom.name.strip() == "CA":
                return (atom.x, atom.y, atom.z)
        return None


@dataclass
class ReceptorData:
    """Parsed protein receptor structure"""
    pdb_id: Optional[str] = None
    filepath: Optional[Path] = None
    name: str = ""
    atoms: List[PDBAtom] = field(default_factory=list)
    residues: Dict[str, List[Residue]] = field(default_factory=dict)  # chain -> residues
    prepared_pdbqt: Optional[Path] = None

    @property
    def atom_count(self) -> int:
        return len(self.atoms)

    @property
    def residue_count(self) -> int:
        return sum(len(res) for res in self.residues.values())

    @property
    def chains(self) -> List[str]:
        return list(self.residues.keys())

    def get_center(self) -> Tuple[float, float, float]:
        """Calculate centroid of all atoms"""
        if not self.atoms:
            return (0.0, 0.0, 0.0)
        xs = [a.x for a in self.atoms]
        ys = [a.y for a in self.atoms]
        zs = [a.z for a in self.atoms]
        n = len(self.atoms)
        return (sum(xs)/n, sum(ys)/n, sum(zs)/n)

    def get_bounding_box(self) -> Tuple[Tuple[float,float,float], Tuple[float,float,float]]:
        """Get min/max corners of bounding box"""
        if not self.atoms:
            return ((0,0,0), (0,0,0))
        xs = [a.x for a in self.atoms]
        ys = [a.y for a in self.atoms]
        zs = [a.z for a in self.atoms]
        return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


@dataclass
class LigandData:
    """Ligand molecule data prepared for docking"""
    smiles: str = ""
    name: str = ""
    atoms: List[Tuple[str, float, float, float]] = field(default_factory=list)  # (element, x, y, z)
    prepared_pdbqt: Optional[Path] = None

    @property
    def atom_count(self) -> int:
        return len(self.atoms)


@dataclass
class DockingConfig:
    """Docking search parameters"""
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    size_x: float = 20.0  # Angstroms
    size_y: float = 20.0
    size_z: float = 20.0
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: float = 3.0  # kcal/mol

    @property
    def center(self) -> Tuple[float, float, float]:
        return (self.center_x, self.center_y, self.center_z)

    @property
    def size(self) -> Tuple[float, float, float]:
        return (self.size_x, self.size_y, self.size_z)


@dataclass
class DockingPose:
    """Single docking pose result"""
    pose_id: int
    affinity_kcal: float   # binding energy in kcal/mol (negative = favorable)
    rmsd_lb: float = 0.0   # RMSD lower bound
    rmsd_ub: float = 0.0   # RMSD upper bound
    atom_coords: List[Tuple[float, float, float]] = field(default_factory=list)
    atom_elements: List[str] = field(default_factory=list)


@dataclass
class Interaction:
    """Protein-ligand interaction"""
    type: str               # "hydrogen_bond", "hydrophobic", "pi_stacking", "salt_bridge", "halogen_bond"
    ligand_atom_idx: int    # index in ligand atom list
    protein_atom_name: str  # protein atom name
    residue_name: str       # e.g., "ALA"
    residue_id: int
    chain: str
    distance: float         # Angstroms
    angle: Optional[float] = None  # degrees (for directional interactions)

    @property
    def residue_label(self) -> str:
        """e.g., 'ALA-123:A'"""
        return f"{self.residue_name}-{self.residue_id}:{self.chain}"

    @property
    def type_label(self) -> str:
        labels = {
            "hydrogen_bond": "H-Bond",
            "hydrophobic": "Hydrophobic",
            "pi_stacking": "π-Stacking",
            "salt_bridge": "Salt Bridge",
            "halogen_bond": "Halogen Bond",
        }
        return labels.get(self.type, self.type)


@dataclass
class DockingResult:
    """Complete docking calculation result"""
    converged: bool = False
    poses: List[DockingPose] = field(default_factory=list)
    receptor: Optional[ReceptorData] = None
    ligand: Optional[LigandData] = None
    config: Optional[DockingConfig] = None
    interactions: Dict[int, List[Interaction]] = field(default_factory=dict)  # pose_id -> interactions
    computation_time: float = 0.0  # seconds
    vina_log: str = ""
    error_message: str = ""

    @property
    def best_affinity(self) -> float:
        """Get best (most negative) binding affinity"""
        if not self.poses:
            return 0.0
        return min(p.affinity_kcal for p in self.poses)

    @property
    def num_poses(self) -> int:
        return len(self.poses)
