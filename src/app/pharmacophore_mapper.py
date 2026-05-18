# pharmacophore_mapper.py (v1.0 - Pharmacophore Feature Identification)
"""
ChemGrid: Pharmacophore Feature Mapper
- Identifies pharmacophore features from molecular structure:
  H-bond donors, H-bond acceptors, hydrophobic centers,
  aromatic rings, positive/negative ionizable groups
- Maps features to 3D coordinates
- Generates pharmacophore fingerprints for similarity
"""

import logging
import math
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import (
        AllChem, Descriptors, rdMolDescriptors,
        rdMolTransforms, Lipinski,
    )
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    from rdkit.Chem.Pharm2D import Gobbi_Pharm2D, Generate
    PHARM2D_AVAILABLE = True
except ImportError:
    PHARM2D_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PharmacophoreFeature:
    """A single pharmacophore feature."""
    feature_type: str       # "HBD", "HBA", "Hydrophobic", "Aromatic", "PosIon", "NegIon"
    atom_indices: List[int] = field(default_factory=list)
    position_3d: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # centroid
    position_2d: Tuple[float, float] = (0.0, 0.0)
    smarts_match: str = ""
    description: str = ""
    strength: float = 1.0   # relative importance 0-1

@dataclass
class PharmacophoreMap:
    """Complete pharmacophore map for a molecule."""
    smiles: str = ""
    mol_name: str = ""
    features: List[PharmacophoreFeature] = field(default_factory=list)
    n_hbd: int = 0
    n_hba: int = 0
    n_hydrophobic: int = 0
    n_aromatic: int = 0
    n_pos_ionizable: int = 0
    n_neg_ionizable: int = 0
    total_features: int = 0
    has_3d: bool = False
    error: str = ""


# ============================================================================
# SMARTS DEFINITIONS FOR PHARMACOPHORE FEATURES
# ============================================================================

# H-bond Donors: NH, OH, occasionally SH
_HBD_SMARTS = [
    ("[NH2]", "Primary amine NH2", 1.0),
    ("[NH1]", "Secondary amine NH", 0.9),
    ("[nH]", "Aromatic NH", 0.85),
    ("[OH]", "Hydroxyl OH", 1.0),
    ("[OH2]", "Water", 0.5),
    ("[SH]", "Thiol SH", 0.6),
]

# H-bond Acceptors: O, N (with lone pairs)
_HBA_SMARTS = [
    ("[#8;!$([#8]~[#7])]", "Oxygen acceptor", 1.0),
    ("[#7;!$([#7]~[#8]);!$([nH]);!$([NH2+]);!$([NH3+])]", "Nitrogen acceptor", 0.9),
    ("[F]", "Fluorine (weak acceptor)", 0.3),
]

# Hydrophobic centers
_HYDROPHOBIC_SMARTS = [
    ("[CH3]", "Methyl group", 0.7),
    ("[CH2;!$([CH2]~[#7,#8,#16])]", "Methylene (non-polar)", 0.6),
    ("[CH;!$([CH]~[#7,#8,#16])]", "Methine (non-polar)", 0.5),
    ("[c;!$([c]~[#7,#8,#16])]", "Aromatic carbon (hydrophobic)", 0.8),
    ("[Cl,Br,I]", "Halogen (hydrophobic)", 0.7),
    ("[S;X2;!$([S]~[#8])]", "Thioether", 0.5),
    ("C(F)(F)F", "Trifluoromethyl", 0.9),
]

# Positive ionizable
_POS_ION_SMARTS = [
    ("[NH3+]", "Protonated primary amine", 1.0),
    ("[NH2+]", "Protonated secondary amine", 1.0),
    ("[NH+]", "Protonated tertiary amine", 0.9),
    ("[n+]", "Protonated aromatic N", 0.85),
    ("[NX3;!$([NX3]~[#8]);!$([NX3]~[#16])]([CH3])([CH3])", "Tertiary amine (basic)", 0.8),
    ("[NH2;!$([NH2]~[#8])]", "Primary amine (ionizable at pH 7.4)", 0.7),
    ("[C;$(C(=N)(N)N)]", "Guanidinium (ionizable)", 0.95),
    ("[C;$(C(=N)N)]", "Amidine (ionizable)", 0.8),
]

# Negative ionizable
_NEG_ION_SMARTS = [
    ("[O-]", "Oxide anion", 1.0),
    ("[S-]", "Thiolate", 0.9),
    ("C(=O)[OH]", "Carboxylic acid (ionizable at pH 7.4)", 0.95),
    ("S(=O)(=O)[OH]", "Sulfonic acid", 0.95),
    ("P(=O)([OH])([OH])", "Phosphoric acid", 0.9),
    ("[#6]S(=O)(=O)[NH]", "Sulfonamide (weakly acidic)", 0.5),
    ("c1[nH]c2ccccc2c1", "Indole NH (weakly acidic)", 0.3),
]


# ============================================================================
# FEATURE DETECTION
# ============================================================================

def _find_features_by_smarts(
    mol,
    smarts_list: List[Tuple[str, str, float]],
    feature_type: str,
    conf=None,
) -> List[PharmacophoreFeature]:
    """
    Find pharmacophore features using SMARTS patterns.

    Args:
        mol: RDKit molecule (with or without 3D coords)
        smarts_list: List of (SMARTS, description, strength)
        feature_type: Feature type label
        conf: Optional RDKit conformer for 3D coordinates

    Returns:
        List of PharmacophoreFeature
    """
    features = []
    seen_atoms: Set[int] = set()  # Avoid duplicating features on same atoms

    for smarts, description, strength in smarts_list:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            continue

        matches = mol.GetSubstructMatches(pattern)
        for match in matches:
            # Skip if primary atom already assigned to same feature type
            if match[0] in seen_atoms:
                continue
            seen_atoms.add(match[0])

            feat = PharmacophoreFeature(
                feature_type=feature_type,
                atom_indices=list(match),
                smarts_match=smarts,
                description=description,
                strength=strength,
            )

            # 3D coordinates (centroid of matched atoms)
            if conf is not None:
                coords = []
                for idx in match:
                    pos = conf.GetAtomPosition(idx)
                    coords.append((pos.x, pos.y, pos.z))
                if coords:
                    cx = sum(c[0] for c in coords) / len(coords)
                    cy = sum(c[1] for c in coords) / len(coords)
                    cz = sum(c[2] for c in coords) / len(coords)
                    feat.position_3d = (round(cx, 3), round(cy, 3), round(cz, 3))
                    feat.has_3d = True

            # 2D coordinates
            try:
                conf2d = mol.GetConformer(0) if conf is None else conf
                if conf2d is not None and len(match) > 0:
                    pos = conf2d.GetAtomPosition(match[0])
                    feat.position_2d = (round(pos.x, 3), round(pos.y, 3))
            except Exception as e:
                logger.debug("2D position extraction error: %s", e)

            features.append(feat)

    return features


def _find_aromatic_features(mol, conf=None) -> List[PharmacophoreFeature]:
    """
    Find aromatic ring features (ring centroids).
    """
    features = []
    ring_info = mol.GetRingInfo()

    for ring_atoms in ring_info.AtomRings():
        # Check if aromatic
        is_aromatic = all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring_atoms)
        if not is_aromatic:
            continue

        feat = PharmacophoreFeature(
            feature_type="Aromatic",
            atom_indices=list(ring_atoms),
            description=f"Aromatic ring ({len(ring_atoms)}-membered)",
            strength=1.0 if len(ring_atoms) == 6 else 0.8,
        )

        # Compute ring centroid in 3D
        if conf is not None:
            coords = []
            for idx in ring_atoms:
                pos = conf.GetAtomPosition(idx)
                coords.append((pos.x, pos.y, pos.z))
            if coords:
                cx = sum(c[0] for c in coords) / len(coords)
                cy = sum(c[1] for c in coords) / len(coords)
                cz = sum(c[2] for c in coords) / len(coords)
                feat.position_3d = (round(cx, 3), round(cy, 3), round(cz, 3))

        features.append(feat)

    return features


# ============================================================================
# MAIN PHARMACOPHORE MAPPING
# ============================================================================

def map_pharmacophore(
    smiles: str,
    mol_name: str = "",
    generate_3d: bool = True,
) -> PharmacophoreMap:
    """
    Identify all pharmacophore features for a molecule.

    Args:
        smiles: SMILES string
        mol_name: Optional molecule name
        generate_3d: Whether to generate 3D coordinates

    Returns:
        PharmacophoreMap with all identified features
    """
    result = PharmacophoreMap(smiles=smiles, mol_name=mol_name)

    if not RDKIT_AVAILABLE:
        result.error = "RDKit not available"
        return result

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        result.error = f"Invalid SMILES: {smiles}"
        return result

    mol = Chem.AddHs(mol)

    # Generate 3D coordinates
    conf = None
    if generate_3d:
        try:
            status = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
            if status == 0:
                AllChem.MMFFOptimizeMoleculeConfs(mol)
                conf = mol.GetConformer(0)
                result.has_3d = True
        except Exception:
            # Fallback: 2D only
            try:
                AllChem.Compute2DCoords(mol)
                conf = mol.GetConformer(0)
            except Exception as e:
                logger.debug("2D coord fallback computation error: %s", e)

    if conf is None:
        try:
            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer(0)
        except Exception as e:
            logger.debug("2D coord computation error: %s", e)

    # Detect features
    all_features = []

    # H-bond donors
    hbd_features = _find_features_by_smarts(mol, _HBD_SMARTS, "HBD", conf)
    all_features.extend(hbd_features)
    result.n_hbd = len(hbd_features)

    # H-bond acceptors
    hba_features = _find_features_by_smarts(mol, _HBA_SMARTS, "HBA", conf)
    all_features.extend(hba_features)
    result.n_hba = len(hba_features)

    # Hydrophobic centers
    hydro_features = _find_features_by_smarts(mol, _HYDROPHOBIC_SMARTS, "Hydrophobic", conf)
    all_features.extend(hydro_features)
    result.n_hydrophobic = len(hydro_features)

    # Aromatic rings
    arom_features = _find_aromatic_features(mol, conf)
    all_features.extend(arom_features)
    result.n_aromatic = len(arom_features)

    # Positive ionizable
    pos_features = _find_features_by_smarts(mol, _POS_ION_SMARTS, "PosIon", conf)
    all_features.extend(pos_features)
    result.n_pos_ionizable = len(pos_features)

    # Negative ionizable
    neg_features = _find_features_by_smarts(mol, _NEG_ION_SMARTS, "NegIon", conf)
    all_features.extend(neg_features)
    result.n_neg_ionizable = len(neg_features)

    result.features = all_features
    result.total_features = len(all_features)

    return result


# ============================================================================
# PHARMACOPHORE SIMILARITY
# ============================================================================

def pharmacophore_distance(map1: PharmacophoreMap, map2: PharmacophoreMap) -> float:
    """
    Calculate pharmacophore distance between two molecules.

    Uses feature count vector Euclidean distance as a simple metric.
    Returns 0.0 for identical profiles, higher values for more different.
    """
    v1 = [map1.n_hbd, map1.n_hba, map1.n_hydrophobic,
          map1.n_aromatic, map1.n_pos_ionizable, map1.n_neg_ionizable]
    v2 = [map2.n_hbd, map2.n_hba, map2.n_hydrophobic,
          map2.n_aromatic, map2.n_pos_ionizable, map2.n_neg_ionizable]

    dist_sq = sum((a - b) ** 2 for a, b in zip(v1, v2))
    return math.sqrt(dist_sq)


def pharmacophore_similarity(map1: PharmacophoreMap, map2: PharmacophoreMap) -> float:
    """
    Calculate pharmacophore similarity (0-1) using Tanimoto on feature counts.

    Returns 1.0 for identical profiles, 0.0 for completely different.
    """
    v1 = [map1.n_hbd, map1.n_hba, map1.n_hydrophobic,
          map1.n_aromatic, map1.n_pos_ionizable, map1.n_neg_ionizable]
    v2 = [map2.n_hbd, map2.n_hba, map2.n_hydrophobic,
          map2.n_aromatic, map2.n_pos_ionizable, map2.n_neg_ionizable]

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1)
    norm2 = sum(b * b for b in v2)

    denom = norm1 + norm2 - dot
    if denom <= 0:
        return 1.0 if norm1 == 0 and norm2 == 0 else 0.0

    return dot / denom


# ============================================================================
# 3D PHARMACOPHORE OVERLAY
# ============================================================================

def get_feature_coordinates(pmap: PharmacophoreMap) -> Dict[str, List[Tuple[float, float, float]]]:
    """
    Extract 3D coordinates grouped by feature type.

    Returns:
        Dict mapping feature_type -> list of (x, y, z) coordinates
    """
    coords: Dict[str, List[Tuple[float, float, float]]] = {}

    for feat in pmap.features:
        ftype = feat.feature_type
        if ftype not in coords:
            coords[ftype] = []
        if feat.position_3d != (0.0, 0.0, 0.0) or pmap.has_3d:
            coords[ftype].append(feat.position_3d)

    return coords


# ============================================================================
# UTILITY: TO DICT
# ============================================================================

def pharmacophore_map_to_dict(pmap: PharmacophoreMap) -> Dict:
    """Convert PharmacophoreMap to a serializable dict."""
    features_list = []
    for feat in pmap.features:
        features_list.append({
            "type": feat.feature_type,
            "atom_indices": feat.atom_indices,
            "position_3d": list(feat.position_3d),
            "position_2d": list(feat.position_2d),
            "description": feat.description,
            "strength": round(feat.strength, 2),
        })

    return {
        "smiles": pmap.smiles,
        "mol_name": pmap.mol_name,
        "has_3d": pmap.has_3d,
        "total_features": pmap.total_features,
        "counts": {
            "HBD": pmap.n_hbd,
            "HBA": pmap.n_hba,
            "Hydrophobic": pmap.n_hydrophobic,
            "Aromatic": pmap.n_aromatic,
            "PosIon": pmap.n_pos_ionizable,
            "NegIon": pmap.n_neg_ionizable,
        },
        "features": features_list,
        "error": pmap.error,
    }
