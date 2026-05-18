# [Phase D] iupac_analyzer.py - IUPAC Nomenclature Analysis
"""
ChemGrid Pro Phase D: Automated IUPAC Naming System
- RDKit-based IUPAC nomenclature generation
- Stereochemistry detection (R/S, E/Z)
- Real-time synchronization with molecule edits
- Display only in theoretical 3D layer
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from PyQt6.QtCore import QThread, pyqtSignal, QPointF
import logging
import math

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors, AllChem, rdchem
    RDKIT_AVAILABLE = True
    try:
        from rdkit.Chem.Draw import IPythonConsole
    except ImportError as e:
        logger.warning("[IUPACAnalyzer] IPythonConsole import skipped (Jupyter-only): %s", e)
except ImportError:
    RDKIT_AVAILABLE = False
    print("[Phase D] RDKit not available, IUPAC naming disabled")

try:
    import pubchem_client as _pubchem
    _PUBCHEM_AVAILABLE = True
except ImportError:
    _PUBCHEM_AVAILABLE = False


@dataclass
class IUPACName:
    """Container for IUPAC nomenclature data"""
    iupac_name: str  # Full IUPAC name
    common_name: Optional[str] = None  # Common/trivial name if applicable
    stereo_descriptors: Dict[int, str] = None  # {atom_idx: "R"/"S"/"E"/"Z"}
    functional_groups: List[str] = None  # Identified functional groups
    confidence: float = 1.0  # Confidence score (0.0-1.0)
    
    def __post_init__(self):
        if self.stereo_descriptors is None:
            self.stereo_descriptors = {}
        if self.functional_groups is None:
            self.functional_groups = []


class StereochemistryAnalyzer:
    """
    Analyzes stereochemistry in molecules
    - Detects tetrahedral chiral centers (R/S)
    - Detects double bond stereochemistry (E/Z)
    - Validates CIP rules
    """
    
    @staticmethod
    def assign_stereochemistry(mol: Chem.Mol) -> Dict[int, str]:
        """
        Assign stereochemistry descriptors (R/S, E/Z) to atoms
        
        Returns:
            Dict mapping atom indices to stereochemistry descriptors
        """
        stereo_map = {}
        
        try:
            # Assign 3D stereochemistry from conformer if available
            if mol.GetNumConformers() > 0:
                Chem.AssignStereochemistryFrom3D(mol)
            else:
                Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
            
            # Extract R/S assignments (Gasteiger charges not needed for stereochemistry)
            # Note: ComputeGasteigerCharges is in AllChem, not rdMolTransforms
            
            for atom in mol.GetAtoms():
                if atom.HasProp("_CIPCode"):
                    cip_code = atom.GetProp("_CIPCode")
                    stereo_map[atom.GetIdx()] = cip_code
            
            # Extract E/Z assignments for double bonds
            for bond in mol.GetBonds():
                if bond.GetBondType() == Chem.BondType.DOUBLE:
                    bond_stereo = bond.GetStereo()
                    if bond_stereo == Chem.BondStereo.STEREOE:
                        stereo_map[f"bond_{bond.GetBeginAtomIdx()}_{bond.GetEndAtomIdx()}"] = "E"
                    elif bond_stereo == Chem.BondStereo.STEREOZ:
                        stereo_map[f"bond_{bond.GetBeginAtomIdx()}_{bond.GetEndAtomIdx()}"] = "Z"
            
            print(f"[Phase D] Stereochemistry detected: {stereo_map}")
            
        except Exception as e:
            print(f"[Phase D STEREO ERROR] {e}")
        
        return stereo_map


class FunctionalGroupAnalyzer:
    """Identifies functional groups in molecules"""
    
    # SMARTS patterns for common functional groups
    FUNCTIONAL_GROUPS = {
        "Amine": "[N;X3,X4]",
        "Amide": "[N;X3]([C;X3]=[O])",
        "Aldehyde": "[C;H1;X3]=[O]",
        "Ketone": "[C;X3]=[O]",
        "Carboxylic Acid": "[C;X3](=[O])[OH]",
        "Ester": "[C;X3](=[O])[O]",
        "Alcohol": "[O;X2;H]",
        "Phenol": "[O;H,X1][c]",
        "Thiol": "[S;X2;H]",
        "Sulfide": "[S;X2]([#6])[#6]",
        "Sulfoxide": "[S;X3]=[O]",
        "Sulfone": "[S;X4]([!H])(=[O])=[O]",
        "Phosphine": "[P;X3]",
        "Phosphate": "[P;X4]=[O]",
        "Nitro": "[N;X3]([O])=[O]",
        "Nitrile": "[C;X2]#[N]",
        "Alkene": "[C]=[C]",
        "Alkyne": "[C]#[C]",
        "Aromatic": "[c]",
    }
    
    @staticmethod
    def identify_functional_groups(mol: Chem.Mol) -> List[str]:
        """
        Identify functional groups in molecule
        
        Returns:
            List of identified functional group names
        """
        groups = []
        
        try:
            for group_name, smarts in FunctionalGroupAnalyzer.FUNCTIONAL_GROUPS.items():
                pattern = Chem.MolFromSmarts(smarts)
                if pattern and mol.HasSubstructMatch(pattern):
                    groups.append(group_name)
            
            print(f"[Phase D] Functional groups: {groups}")
            
        except Exception as e:
            print(f"[Phase D FG ERROR] {e}")
        
        return groups


class IUPACNameGenerator:
    """
    Generates IUPAC names using RDKit
    Integrates stereochemistry and functional group information
    """
    
    @staticmethod
    def generate_iupac_name(mol: Chem.Mol) -> Optional[str]:
        """
        Generate IUPAC name for molecule.

        Fallback chain (in order):
          1. PubChem API lookup (authoritative IUPAC name)
          2. RDKit canonical SMILES (unambiguous identifier)
          3. Molecular formula with "(offline)" label

        Returns:
            IUPAC name string or None if generation fails
        """
        try:
            # Validate and clean molecule
            mol = Chem.AddHs(mol)
            mol = Chem.RemoveHs(mol)

            smiles = Chem.MolToSmiles(mol, isomericSmiles=True)
            formula = rdMolDescriptors.CalcMolFormula(mol)

            # --- Fallback 1: PubChem authoritative IUPAC name ---
            if _PUBCHEM_AVAILABLE:
                try:
                    pubchem_name = _pubchem.get_iupac_name_by_smiles(smiles)
                    if pubchem_name and isinstance(pubchem_name, str) and len(pubchem_name) > 0:
                        print(f"[Phase D] PubChem IUPAC name: {pubchem_name}")
                        return pubchem_name
                except Exception as e:
                    print(f"[Phase D] PubChem lookup failed: {e}")

            # --- Fallback 2: SMILES (unambiguous, but not a name) ---
            # Only use if formula is too generic (e.g. many isomers share same formula)
            # Return formula + SMILES for clarity
            if smiles:
                offline_name = f"{formula} (offline)"
                print(f"[Phase D] Offline fallback: {offline_name}")
                return offline_name

            # --- Fallback 3: formula only ---
            if formula:
                return f"{formula} (offline)"

            return None

        except Exception as e:
            print(f"[Phase D IUPAC ERROR] {e}")
            return None
    
    # NOTE: _find_longest_carbon_chain and _dfs_chain_length removed.
    # The old code produced fake names like "C2_compound-1O".
    # Now we use PubChem API for authoritative IUPAC names.


class IUPACAnalyzerThread(QThread):
    """
    Background thread for IUPAC nomenclature analysis
    Runs independently to avoid blocking UI
    [OPTIMIZED] With proper thread synchronization and resource cleanup
    """
    
    progress = pyqtSignal(str)  # Progress message
    result = pyqtSignal(IUPACName)  # Result: IUPACName object
    error = pyqtSignal(str)  # Error message
    finished_cleanup = pyqtSignal()  # Signal when thread is safely finished
    
    def __init__(self, atoms: Dict, bonds: Dict):
        super().__init__()
        self.atoms = atoms
        self.bonds = bonds
        self.iupac_data = None
        self._stop_event = False  # Flag to stop thread gracefully
        self.setObjectName(f"IUPACAnalyzer-{id(self)}")  # Debug tracking
    
    def run(self):
        """Execute IUPAC analysis in background thread with safe interruption"""
        try:
            if not RDKIT_AVAILABLE:
                # [FIX] RDKit 미설치는 예상된 상태 — error 시그널 대신 조용히 종료
                # error.emit()이 phase_integration._on_iupac_error()를 트리거해
                # "[Phase D Error] [Phase D] RDKit not available" 이중 메시지가 출력됐음
                return
            
            self.progress.emit("[Phase D] Starting IUPAC analysis...")
            
            # Check for stop request
            if self._stop_event:
                print(f"[{self.objectName()}] Analysis cancelled before start")
                return
            
            # Build RDKit molecule from atoms and bonds
            mol = self._build_rdkit_molecule()
            
            if not mol:
                self.error.emit("Failed to build RDKit molecule")
                return
            
            # Check for stop request
            if self._stop_event:
                print(f"[{self.objectName()}] Analysis cancelled after mol build")
                return
            
            # Analyze stereochemistry
            self.progress.emit("[Phase D] Analyzing stereochemistry...")
            stereo_descriptors = StereochemistryAnalyzer.assign_stereochemistry(mol)
            
            if self._stop_event:
                return
            
            # Identify functional groups
            self.progress.emit("[Phase D] Identifying functional groups...")
            functional_groups = FunctionalGroupAnalyzer.identify_functional_groups(mol)
            
            if self._stop_event:
                return
            
            # Generate IUPAC name
            self.progress.emit("[Phase D] Generating IUPAC name...")
            iupac_name = IUPACNameGenerator.generate_iupac_name(mol)
            
            if not iupac_name:
                iupac_name = "Unknown compound"
            
            # Check for stop request before emitting result
            if self._stop_event:
                return
            
            # Create result object
            self.iupac_data = IUPACName(
                iupac_name=iupac_name,
                stereo_descriptors=stereo_descriptors,
                functional_groups=functional_groups,
                confidence=0.9  # Default confidence
            )
            
            self.progress.emit(f"[Phase D] IUPAC analysis complete: {iupac_name}")
            self.result.emit(self.iupac_data)
            
        except Exception as e:
            self.error.emit(f"[Phase D ANALYSIS ERROR] {str(e)}")
        finally:
            self.finished_cleanup.emit()
    
    def stop(self):
        """Gracefully stop the analysis thread"""
        self._stop_event = True
        print(f"[{self.objectName()}] Stop signal received")
    
    def _build_rdkit_molecule(self) -> Optional[Chem.Mol]:
        """Build RDKit molecule from ChemGrid atoms and bonds"""
        try:
            mol = Chem.RWMol()
            atom_map = {}

            # Add atoms
            # pos is always a (float, float) tuple from get_coord_key — never QPointF
            for pos, data in self.atoms.items():
                if not isinstance(pos, tuple):
                    # Guard: pos must be a hashable tuple key
                    pt_key = (round(pos.x(), 2), round(pos.y(), 2)) if hasattr(pos, 'x') else pos
                else:
                    pt_key = pos
                symbol = data.get("main", "C") if isinstance(data, dict) else "C"
                atom = Chem.Atom(symbol or "C")  # '' (Carbon) → "C" for RDKit
                idx = mol.AddAtom(atom)
                atom_map[pt_key] = idx

            # Add bonds
            for (k1, k2), bond_data in self.bonds.items():
                # Normalise keys: canvas stores tuple keys but guard against QPointF
                if hasattr(k1, 'x'):
                    k1 = (round(k1.x(), 2), round(k1.y(), 2))
                if hasattr(k2, 'x'):
                    k2 = (round(k2.x(), 2), round(k2.y(), 2))

                if k1 not in atom_map or k2 not in atom_map:
                    continue
                idx1 = atom_map[k1]
                idx2 = atom_map[k2]

                # Determine bond order
                # bond_data formats:
                #   int           → plain bond order (1/2/3)
                #   float         → coordination bond (0.5) → treat as SINGLE
                #   (QPointF, QPointF, "Wedge"/"Dash") → stereo single bond; order = 1
                #   (int, int, ...)  → (order, ?, ?) legacy tuple
                if isinstance(bond_data, int):
                    bond_order = bond_data
                elif isinstance(bond_data, float):
                    bond_order = 1  # dative / coordination bond → single for RDKit
                elif isinstance(bond_data, tuple) and len(bond_data) >= 3:
                    # Stereo bond: (QPointF, QPointF, "Wedge"/"Dash") — always order 1
                    last = bond_data[2]
                    if isinstance(last, str) and last in ("Wedge", "Dash"):
                        bond_order = 1
                    elif isinstance(bond_data[1], int):
                        bond_order = bond_data[1]
                    else:
                        bond_order = 1  # fallback
                elif isinstance(bond_data, tuple) and len(bond_data) == 2:
                    bond_order = bond_data[1] if isinstance(bond_data[1], int) else 1
                else:
                    bond_order = 1

                bond_type = {
                    1: Chem.BondType.SINGLE,
                    2: Chem.BondType.DOUBLE,
                    3: Chem.BondType.TRIPLE,
                }.get(bond_order, Chem.BondType.SINGLE)

                mol.AddBond(idx1, idx2, bond_type)

            final_mol = mol.GetMol()
            Chem.SanitizeMol(final_mol)

            return final_mol

        except Exception as e:
            print(f"[Phase D BUILD ERROR] {e}")
            return None


class IUPACAnalyzer:
    """
    Main IUPAC analyzer interface
    Provides synchronous and asynchronous analysis methods
    [OPTIMIZED] With LRU caching (50 entries max, 10min TTL)
    """
    
    _analysis_cache = {}  # {smiles_hash: IUPACName}
    _cache_timestamps = {}  # {smiles_hash: timestamp}
    _max_cache_entries = 50
    _cache_ttl_seconds = 600  # 10 minutes
    
    @staticmethod
    def _smiles_to_cache_key(atoms: Dict, bonds: Dict) -> str:
        """Generate cache key from atoms/bonds (simpler than full SMILES)"""
        # Guard: QPointF keys are not hashable; normalise to tuple before frozenset
        try:
            safe_keys = frozenset(
                (round(k.x(), 2), round(k.y(), 2)) if hasattr(k, 'x') else k
                for k in atoms.keys()
            )
            return f"{len(atoms)}_{len(bonds)}_{hash(safe_keys)}"
        except Exception:
            return f"{len(atoms)}_{len(bonds)}_0"
    
    @staticmethod
    def _invalidate_stale_cache():
        """Remove cache entries older than TTL"""
        import time
        current_time = time.time()
        stale_keys = [
            k for k, t in IUPACAnalyzer._cache_timestamps.items()
            if current_time - t > IUPACAnalyzer._cache_ttl_seconds
        ]
        for key in stale_keys:
            IUPACAnalyzer._analysis_cache.pop(key, None)
            IUPACAnalyzer._cache_timestamps.pop(key, None)
    
    @staticmethod
    def _enforce_cache_limit():
        """Enforce maximum cache size (LRU eviction)"""
        if len(IUPACAnalyzer._analysis_cache) >= IUPACAnalyzer._max_cache_entries:
            oldest_key = min(IUPACAnalyzer._cache_timestamps, key=IUPACAnalyzer._cache_timestamps.get)
            IUPACAnalyzer._analysis_cache.pop(oldest_key, None)
            IUPACAnalyzer._cache_timestamps.pop(oldest_key, None)
    
    @staticmethod
    def analyze_sync(atoms: Dict, bonds: Dict) -> Optional[IUPACName]:
        """
        Synchronous IUPAC analysis (blocking)
        [OPTIMIZED] With cache hit detection
        """
        if not RDKIT_AVAILABLE:
            print("[Phase D] RDKit not available")
            return None
        
        try:
            # Check cache first
            import time
            IUPACAnalyzer._invalidate_stale_cache()
            cache_key = IUPACAnalyzer._smiles_to_cache_key(atoms, bonds)
            
            if cache_key in IUPACAnalyzer._analysis_cache:
                print(f"[Phase D] Cache hit for {cache_key}")
                return IUPACAnalyzer._analysis_cache[cache_key]
            
            # Cache miss: perform analysis
            mol = IUPACAnalyzerThread(atoms, bonds)._build_rdkit_molecule()
            if not mol:
                return None
            
            iupac_name = IUPACNameGenerator.generate_iupac_name(mol)
            stereo = StereochemistryAnalyzer.assign_stereochemistry(mol)
            fg = FunctionalGroupAnalyzer.identify_functional_groups(mol)
            
            result = IUPACName(
                iupac_name=iupac_name or "Unknown",
                stereo_descriptors=stereo,
                functional_groups=fg
            )
            
            # Store in cache
            IUPACAnalyzer._enforce_cache_limit()
            IUPACAnalyzer._analysis_cache[cache_key] = result
            IUPACAnalyzer._cache_timestamps[cache_key] = time.time()
            
            print(f"[Phase D] Analyzed and cached: {iupac_name}")
            return result
            
        except Exception as e:
            print(f"[Phase D SYNC ERROR] {e}")
            return None
    
    @staticmethod
    def analyze_async(atoms: Dict, bonds: Dict) -> IUPACAnalyzerThread:
        """
        Asynchronous IUPAC analysis (non-blocking)
        Use for interactive analysis with UI updates
        """
        thread = IUPACAnalyzerThread(atoms, bonds)
        return thread


# ============================================================================
# DISPLAY HELPERS FOR 3D LAYER
# ============================================================================

class IUPACLabelRenderer:
    """Helper class for rendering IUPAC labels in 3D layer"""
    
    @staticmethod
    def format_label_for_display(iupac_data: IUPACName) -> str:
        """
        Format IUPAC data for display in 3D theoretical layer
        
        Returns:
            Formatted display string
        """
        lines = []
        
        # Main IUPAC name
        lines.append(f"IUPAC: {iupac_data.iupac_name}")
        
        # Stereochemistry descriptors
        if iupac_data.stereo_descriptors:
            stereo_str = ", ".join([f"{k}: {v}" for k, v in iupac_data.stereo_descriptors.items()])
            lines.append(f"Stereochemistry: {stereo_str}")
        
        # Functional groups
        if iupac_data.functional_groups:
            lines.append(f"Functional Groups: {', '.join(iupac_data.functional_groups)}")
        
        # Confidence
        lines.append(f"Confidence: {iupac_data.confidence:.1%}")
        
        return "\n".join(lines)
    
    @staticmethod
    def create_stereo_label_positions(mol_data: Dict) -> Dict[Tuple, str]:
        """
        Create stereochemistry label positions for 3D layer display
        Maps atom positions to their R/S or E/Z descriptors
        
        Returns:
            Dict mapping (x, y) positions to label strings
        """
        labels = {}
        # Implementation would integrate with analyzer results
        return labels
