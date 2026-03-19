# alphafold_interface.py (v1.0 - ColabFold API Integration)
"""
ChemGrid: AlphaFold/ColabFold Protein Structure Prediction Interface
- FASTA sequence validation
- ColabFold API call with timeout and retry
- PDB file parsing and structure extraction
- Graceful fallback when API is unavailable
"""

import os
import re
import json
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import urllib.request
    import urllib.error
    URLLIB_AVAILABLE = True
except ImportError:
    URLLIB_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PDBAtom:
    """Single atom from a PDB file."""
    serial: int
    name: str
    res_name: str
    chain_id: str
    res_seq: int
    x: float
    y: float
    z: float
    occupancy: float = 1.0
    temp_factor: float = 0.0  # B-factor / pLDDT in AlphaFold
    element: str = ""

@dataclass
class PDBResidue:
    """A residue (amino acid) from a PDB structure."""
    name: str
    seq_num: int
    chain_id: str
    atoms: List[PDBAtom] = field(default_factory=list)
    plddt: float = 0.0  # per-residue confidence

@dataclass
class ProteinStructure:
    """Parsed protein structure from PDB."""
    sequence: str = ""
    residues: List[PDBResidue] = field(default_factory=list)
    atoms: List[PDBAtom] = field(default_factory=list)
    plddt_scores: List[float] = field(default_factory=list)
    mean_plddt: float = 0.0
    pdb_text: str = ""
    source: str = ""  # "colabfold", "rcsb", "cache", "fallback"
    error: str = ""

@dataclass
class PredictionResult:
    """Result of a structure prediction request."""
    success: bool = False
    structure: Optional[ProteinStructure] = None
    error: str = ""
    elapsed_seconds: float = 0.0
    method: str = ""  # "colabfold_api", "rcsb_lookup", "cache"


# ============================================================================
# SEQUENCE VALIDATION
# ============================================================================

# Standard amino acid one-letter codes
VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")
# Extended codes (including ambiguous)
EXTENDED_AA = VALID_AA | set("BJOUXZ")

def validate_fasta_sequence(sequence: str) -> Tuple[bool, str, str]:
    """
    Validate a FASTA protein sequence.

    Args:
        sequence: Raw sequence string (may include FASTA header)

    Returns:
        (is_valid, cleaned_sequence, error_message)
    """
    if not sequence or not sequence.strip():
        return False, "", "Empty sequence provided"

    lines = sequence.strip().splitlines()
    header = ""
    seq_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            header = line
        else:
            seq_lines.append(line.upper())

    clean_seq = "".join(seq_lines)
    # Remove whitespace and digits
    clean_seq = re.sub(r"[\s\d]", "", clean_seq)

    if not clean_seq:
        return False, "", "No amino acid sequence found after parsing"

    if len(clean_seq) < 10:
        return False, clean_seq, f"Sequence too short ({len(clean_seq)} residues, minimum 10)"

    if len(clean_seq) > 2500:
        return False, clean_seq, f"Sequence too long ({len(clean_seq)} residues, maximum 2500 for ColabFold)"

    invalid_chars = set(clean_seq) - EXTENDED_AA
    if invalid_chars:
        return False, clean_seq, f"Invalid characters in sequence: {sorted(invalid_chars)}"

    return True, clean_seq, ""


# ============================================================================
# PDB PARSER
# ============================================================================

def parse_pdb_text(pdb_text: str) -> ProteinStructure:
    """
    Parse PDB format text into a ProteinStructure.

    Handles standard PDB ATOM/HETATM records.
    For AlphaFold predictions, B-factor column contains pLDDT scores.
    """
    structure = ProteinStructure(pdb_text=pdb_text)
    residue_map: Dict[Tuple[str, int], PDBResidue] = {}
    atoms = []

    for line in pdb_text.splitlines():
        record = line[:6].strip()
        if record not in ("ATOM", "HETATM"):
            continue

        try:
            atom = PDBAtom(
                serial=int(line[6:11].strip()) if line[6:11].strip() else 0,
                name=line[12:16].strip(),
                res_name=line[17:20].strip(),
                chain_id=line[21:22].strip() if len(line) > 21 else "A",
                res_seq=int(line[22:26].strip()) if line[22:26].strip() else 0,
                x=float(line[30:38].strip()) if line[30:38].strip() else 0.0,
                y=float(line[38:46].strip()) if line[38:46].strip() else 0.0,
                z=float(line[46:54].strip()) if line[46:54].strip() else 0.0,
                occupancy=float(line[54:60].strip()) if len(line) > 59 and line[54:60].strip() else 1.0,
                temp_factor=float(line[60:66].strip()) if len(line) > 65 and line[60:66].strip() else 0.0,
                element=line[76:78].strip() if len(line) > 77 else "",
            )
        except (ValueError, IndexError):
            continue

        atoms.append(atom)

        res_key = (atom.chain_id, atom.res_seq)
        if res_key not in residue_map:
            residue_map[res_key] = PDBResidue(
                name=atom.res_name,
                seq_num=atom.res_seq,
                chain_id=atom.chain_id,
            )
        residue_map[res_key].atoms.append(atom)

    structure.atoms = atoms

    # Sort residues by chain then sequence number
    sorted_keys = sorted(residue_map.keys(), key=lambda k: (k[0], k[1]))
    for key in sorted_keys:
        res = residue_map[key]
        # pLDDT from B-factor of CA atom (or first atom)
        ca_atoms = [a for a in res.atoms if a.name == "CA"]
        if ca_atoms:
            res.plddt = ca_atoms[0].temp_factor
        elif res.atoms:
            res.plddt = res.atoms[0].temp_factor
        structure.residues.append(res)

    # Compute pLDDT statistics
    plddt_scores = [r.plddt for r in structure.residues if r.plddt > 0]
    structure.plddt_scores = plddt_scores
    structure.mean_plddt = sum(plddt_scores) / len(plddt_scores) if plddt_scores else 0.0

    # Reconstruct 1-letter sequence
    aa3to1 = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
        "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
        "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
        "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    }
    structure.sequence = "".join(
        aa3to1.get(r.name, "X") for r in structure.residues
    )

    return structure


# ============================================================================
# COLABFOLD API CLIENT
# ============================================================================

COLABFOLD_API_URL = "https://api.colabfold.com"
COLABFOLD_SUBMIT_URL = f"{COLABFOLD_API_URL}/batch"
COLABFOLD_TICKET_URL = f"{COLABFOLD_API_URL}/result"

# Cache directory for predictions
_CACHE_DIR = Path(tempfile.gettempdir()) / "chemgrid_alphafold_cache"


def _get_cache_path(sequence: str) -> Path:
    """Get cache file path for a sequence (hash-based)."""
    import hashlib
    seq_hash = hashlib.md5(sequence.encode()).hexdigest()[:16]
    return _CACHE_DIR / f"af_{seq_hash}.pdb"


def _load_from_cache(sequence: str) -> Optional[ProteinStructure]:
    """Try loading a cached prediction."""
    cache_path = _get_cache_path(sequence)
    if cache_path.exists():
        try:
            pdb_text = cache_path.read_text(encoding="utf-8")
            structure = parse_pdb_text(pdb_text)
            structure.source = "cache"
            return structure
        except Exception:
            pass
    return None


def _save_to_cache(sequence: str, pdb_text: str) -> None:
    """Save a prediction to cache."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _get_cache_path(sequence)
        cache_path.write_text(pdb_text, encoding="utf-8")
    except Exception:
        pass


def submit_colabfold_prediction(
    sequence: str,
    timeout_seconds: int = 600,
    poll_interval: int = 10,
) -> PredictionResult:
    """
    Submit a sequence to ColabFold API and wait for results.

    Args:
        sequence: Validated amino acid sequence (1-letter codes)
        timeout_seconds: Maximum wait time (default 10 minutes)
        poll_interval: Seconds between status checks

    Returns:
        PredictionResult with structure or error
    """
    if not URLLIB_AVAILABLE:
        return PredictionResult(
            success=False,
            error="urllib not available - cannot make API calls"
        )

    # Check cache first
    cached = _load_from_cache(sequence)
    if cached:
        return PredictionResult(
            success=True,
            structure=cached,
            method="cache",
        )

    start_time = time.time()

    # Step 1: Submit job
    try:
        payload = json.dumps({
            "query": sequence,
            "mode": "all",
        }).encode("utf-8")

        req = urllib.request.Request(
            COLABFOLD_SUBMIT_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            ticket_id = resp_data.get("id", "")

    except urllib.error.URLError as e:
        return PredictionResult(
            success=False,
            error=f"ColabFold API connection failed: {e}",
            elapsed_seconds=time.time() - start_time,
            method="colabfold_api",
        )
    except Exception as e:
        return PredictionResult(
            success=False,
            error=f"ColabFold submission error: {e}",
            elapsed_seconds=time.time() - start_time,
            method="colabfold_api",
        )

    if not ticket_id:
        return PredictionResult(
            success=False,
            error="No ticket ID returned from ColabFold API",
            elapsed_seconds=time.time() - start_time,
            method="colabfold_api",
        )

    # Step 2: Poll for results
    result_url = f"{COLABFOLD_TICKET_URL}/{ticket_id}"
    while (time.time() - start_time) < timeout_seconds:
        try:
            with urllib.request.urlopen(result_url, timeout=15) as resp:
                status_code = resp.getcode()
                if status_code == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    data = resp.read().decode("utf-8")

                    if "application/json" in content_type:
                        status_data = json.loads(data)
                        status = status_data.get("status", "")
                        if status == "FAILURE":
                            return PredictionResult(
                                success=False,
                                error=f"ColabFold prediction failed: {status_data.get('error', 'unknown')}",
                                elapsed_seconds=time.time() - start_time,
                                method="colabfold_api",
                            )
                        # Still running, continue polling
                    else:
                        # Got PDB text back
                        structure = parse_pdb_text(data)
                        structure.source = "colabfold"
                        _save_to_cache(sequence, data)
                        return PredictionResult(
                            success=True,
                            structure=structure,
                            elapsed_seconds=time.time() - start_time,
                            method="colabfold_api",
                        )
                elif status_code == 202:
                    pass  # Still processing
                else:
                    pass  # Unexpected status, keep polling

        except urllib.error.URLError:
            pass  # Transient network error, retry
        except Exception:
            pass

        time.sleep(poll_interval)

    return PredictionResult(
        success=False,
        error=f"ColabFold prediction timed out after {timeout_seconds}s",
        elapsed_seconds=time.time() - start_time,
        method="colabfold_api",
    )


# ============================================================================
# RCSB PDB LOOKUP (FALLBACK)
# ============================================================================

def fetch_pdb_from_rcsb(pdb_id: str) -> PredictionResult:
    """
    Fetch a known structure from RCSB PDB as fallback.

    Args:
        pdb_id: 4-character PDB ID (e.g., "1CRN")

    Returns:
        PredictionResult with structure or error
    """
    if not URLLIB_AVAILABLE:
        return PredictionResult(success=False, error="urllib not available")

    pdb_id = pdb_id.strip().upper()
    if not re.match(r"^[A-Z0-9]{4}$", pdb_id):
        return PredictionResult(success=False, error=f"Invalid PDB ID: {pdb_id}")

    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    start_time = time.time()

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            pdb_text = resp.read().decode("utf-8")
            structure = parse_pdb_text(pdb_text)
            structure.source = "rcsb"
            return PredictionResult(
                success=True,
                structure=structure,
                elapsed_seconds=time.time() - start_time,
                method="rcsb_lookup",
            )
    except urllib.error.HTTPError as e:
        return PredictionResult(
            success=False,
            error=f"RCSB PDB lookup failed for {pdb_id}: HTTP {e.code}",
            elapsed_seconds=time.time() - start_time,
            method="rcsb_lookup",
        )
    except Exception as e:
        return PredictionResult(
            success=False,
            error=f"RCSB PDB fetch error: {e}",
            elapsed_seconds=time.time() - start_time,
            method="rcsb_lookup",
        )


# ============================================================================
# UNIFIED PREDICTION INTERFACE
# ============================================================================

def predict_structure(
    sequence: str = "",
    pdb_id: str = "",
    timeout_seconds: int = 600,
) -> PredictionResult:
    """
    Unified interface for protein structure prediction/retrieval.

    Priority:
    1. Cache lookup (instant)
    2. RCSB PDB if pdb_id provided (fast)
    3. ColabFold API prediction (slow, may timeout)
    4. Fallback error

    Args:
        sequence: FASTA amino acid sequence
        pdb_id: Optional known PDB ID for RCSB lookup
        timeout_seconds: Max wait for ColabFold

    Returns:
        PredictionResult
    """
    # If PDB ID provided, use RCSB
    if pdb_id:
        result = fetch_pdb_from_rcsb(pdb_id)
        if result.success:
            return result

    # Validate sequence
    if not sequence:
        return PredictionResult(
            success=False,
            error="No sequence or PDB ID provided"
        )

    is_valid, clean_seq, error = validate_fasta_sequence(sequence)
    if not is_valid:
        return PredictionResult(success=False, error=f"Sequence validation failed: {error}")

    # Check cache
    cached = _load_from_cache(clean_seq)
    if cached:
        return PredictionResult(success=True, structure=cached, method="cache")

    # Try ColabFold
    result = submit_colabfold_prediction(clean_seq, timeout_seconds=timeout_seconds)
    return result


# ============================================================================
# CONFIDENCE FILTERING
# ============================================================================

def filter_by_plddt(
    structure: ProteinStructure,
    min_plddt: float = 70.0,
) -> Dict:
    """
    Analyze structure confidence and filter residues by pLDDT score.

    pLDDT interpretation (AlphaFold):
      > 90: Very high confidence
      70-90: High confidence (backbone reliable)
      50-70: Low confidence (caution)
      < 50: Very low confidence (likely disordered)

    Args:
        structure: Parsed protein structure
        min_plddt: Minimum pLDDT threshold

    Returns:
        Dict with confidence analysis
    """
    if not structure.residues:
        return {
            "total_residues": 0,
            "confident_residues": 0,
            "confidence_ratio": 0.0,
            "mean_plddt": 0.0,
            "categories": {},
            "reliable": False,
        }

    scores = [r.plddt for r in structure.residues]
    confident = [r for r in structure.residues if r.plddt >= min_plddt]

    categories = {
        "very_high": len([s for s in scores if s > 90]),
        "high": len([s for s in scores if 70 < s <= 90]),
        "low": len([s for s in scores if 50 < s <= 70]),
        "very_low": len([s for s in scores if s <= 50]),
    }

    total = len(structure.residues)
    conf_ratio = len(confident) / total if total > 0 else 0.0

    return {
        "total_residues": total,
        "confident_residues": len(confident),
        "confidence_ratio": conf_ratio,
        "mean_plddt": structure.mean_plddt,
        "categories": categories,
        "reliable": conf_ratio >= 0.7 and structure.mean_plddt >= 70.0,
        "confident_residue_indices": [r.seq_num for r in confident],
    }


# ============================================================================
# BINDING SITE EXTRACTION
# ============================================================================

def extract_binding_site(
    structure: ProteinStructure,
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    radius: float = 10.0,
) -> Dict:
    """
    Extract residues near a binding site center.

    Args:
        structure: Protein structure
        center: (x, y, z) center of binding pocket
        radius: Search radius in Angstroms

    Returns:
        Dict with binding site residues and atoms
    """
    if not NUMPY_AVAILABLE:
        # Fallback without numpy
        site_residues = set()
        site_atoms = []
        cx, cy, cz = center
        r2 = radius * radius
        for atom in structure.atoms:
            dx = atom.x - cx
            dy = atom.y - cy
            dz = atom.z - cz
            if dx * dx + dy * dy + dz * dz <= r2:
                site_atoms.append(atom)
                site_residues.add((atom.chain_id, atom.res_seq))
        return {
            "center": center,
            "radius": radius,
            "n_atoms": len(site_atoms),
            "n_residues": len(site_residues),
            "residue_keys": sorted(site_residues),
            "atoms": site_atoms,
        }

    center_arr = np.array(center)
    coords = np.array([[a.x, a.y, a.z] for a in structure.atoms])
    if len(coords) == 0:
        return {
            "center": center, "radius": radius,
            "n_atoms": 0, "n_residues": 0,
            "residue_keys": [], "atoms": [],
        }

    dists = np.linalg.norm(coords - center_arr, axis=1)
    mask = dists <= radius

    site_atoms = [a for a, m in zip(structure.atoms, mask) if m]
    site_residues = set((a.chain_id, a.res_seq) for a in site_atoms)

    return {
        "center": center,
        "radius": radius,
        "n_atoms": len(site_atoms),
        "n_residues": len(site_residues),
        "residue_keys": sorted(site_residues),
        "atoms": site_atoms,
    }
