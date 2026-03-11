# popup_3d.py — Integrated 3D Molecular Analysis Popup (Phase 7)
"""
ChemGrid 통합 3D 분석 팝업
- OpenGL 3D 뷰어 (Ball-and-Stick / Space-filling)
- QPainter 2.5D 폴백
- RDKit 3D 좌표 생성 (ORCA > RDKit > VSEPR > 2D)
- ORCA .out 파싱 (geometry, frequencies, energies)
- PubChem API 연동 (IUPAC명, 물성)
- Gemini AI 분석 (선택적)
- 진동 모드 3D 화살표 애니메이션
- 결합 길이/각도 측정 도구
- matplotlib 스펙트럼 플롯
- 하단 탭: [📊 속성] [📈 스펙트럼] [🎵 진동모드] [📝 AI분석]

Phase 6-1A (2026-02-28): C2 fix, OpenGL/QPainter 리팩토링
Phase 7   (2026-02-28): 통합 분석 팝업 확장
"""

import os
import re
import math
import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
    QComboBox, QCheckBox, QFrame, QTabWidget, QTextEdit, QSplitter,
    QGroupBox, QFormLayout, QProgressBar, QScrollArea, QListWidget,
    QListWidgetItem, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QPointF, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import (
    QSurfaceFormat, QPainter, QColor, QPen, QBrush,
    QRadialGradient, QFont, QMouseEvent, QWheelEvent, QIcon
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
# C2 Fix: Invalid import removed

# --- Portable path ---
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

# --- dotenv 로드 (GOOGLE_API_KEY / GEMINI_API_KEY 지원) ---
# server.py와 동일하게 GOOGLE_API_KEY 우선 사용
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_candidates = [
        _SCRIPT_DIR.parent.parent / "agents" / "mcp_server" / ".env",
        _SCRIPT_DIR.parent / "mcp_server" / ".env",
        Path(os.getcwd()) / "agents" / "mcp_server" / ".env",
        Path(os.getcwd()) / ".env",
    ]
    for _ec in _env_candidates:
        if _ec.exists():
            _load_dotenv(_ec)
            break
    _DOTENV_LOADED = True
except ImportError:
    _DOTENV_LOADED = False  # python-dotenv 미설치 시 os.environ으로만 동작

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Optional dependency checks ---
OPENGL_AVAILABLE = False
try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    logger.warning("PyOpenGL not available, using QPainter 2.5D fallback")

RDKIT_AVAILABLE = False
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    logger.warning("RDKit not available")

MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    logger.warning("matplotlib not available")

REQUESTS_AVAILABLE = False
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    logger.warning("requests not available — PubChem disabled")

# pubchem_client: API 키 + 초당 1회 속도 제한 적용
try:
    import pubchem_client as _pc_client
    _PC_CLIENT_AVAILABLE = True
except ImportError:
    _PC_CLIENT_AVAILABLE = False
    _pc_client = None

GEMINI_AVAILABLE = False
try:
    # [BUG-07 수정] google.genai 우선 시도, 실패 시 google.generativeai 폴백
    # [FW-01 수정] FutureWarning 억제 — google.generativeai deprecated warning
    try:
        import google.genai as genai_lib
        GEMINI_AVAILABLE = True
    except ImportError:
        import warnings
        warnings.filterwarnings(
            "ignore", category=FutureWarning,
            module="google.generativeai"
        )
        import google.generativeai as genai_lib
        GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("google.generativeai not available — AI analysis disabled")


# ============================================================
# Section 1: CPK Color & Radius Data
# ============================================================

VDW_RADII = {
    "H": 1.20, "He": 1.40, "Li": 1.82, "Be": 1.53, "B": 1.92,
    "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "Ne": 1.54,
    "Na": 2.27, "Mg": 1.73, "Al": 1.84, "Si": 2.10, "P": 1.80,
    "S": 1.80, "Cl": 1.75, "Ar": 1.88, "K": 2.75, "Ca": 2.31,
    "Br": 1.85, "I": 1.98, "Xe": 2.16,
}

COVALENT_RADII = {
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84,
    "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58,
    "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07,
    "S": 1.05, "Cl": 1.02, "Ar": 1.06, "K": 2.03, "Ca": 1.76,
    "Br": 1.20, "I": 1.39, "Xe": 1.40,
}

CPK_COLORS = {
    "H":  (1.00, 1.00, 1.00), "He": (0.85, 1.00, 1.00),
    "Li": (0.80, 0.50, 1.00), "Be": (0.76, 1.00, 0.00),
    "B":  (1.00, 0.71, 0.71), "C":  (0.56, 0.56, 0.56),
    "N":  (0.19, 0.31, 0.97), "O":  (1.00, 0.05, 0.05),
    "F":  (0.56, 0.88, 0.31), "Ne": (0.70, 0.89, 0.96),
    "Na": (0.67, 0.36, 0.95), "Mg": (0.54, 1.00, 0.00),
    "Al": (0.75, 0.65, 0.65), "Si": (0.94, 0.78, 0.63),
    "P":  (1.00, 0.50, 0.00), "S":  (1.00, 1.00, 0.19),
    "Cl": (0.12, 0.94, 0.12), "Ar": (0.50, 0.82, 0.89),
    "K":  (0.56, 0.25, 0.83), "Ca": (0.24, 1.00, 0.00),
    "Br": (0.65, 0.16, 0.16), "I":  (0.58, 0.00, 0.58),
    "Xe": (0.26, 0.62, 0.69),
    # 전이금속 CPK 표준 색상 (JMOL/Avogadro 기준)
    "Sc": (0.90, 0.90, 0.90), "Ti": (0.75, 0.76, 0.78),
    "V":  (0.65, 0.65, 0.67), "Cr": (0.54, 0.60, 0.78),
    "Mn": (0.61, 0.48, 0.78), "Fe": (0.88, 0.40, 0.20),
    "Co": (0.94, 0.56, 0.63), "Ni": (0.31, 0.82, 0.31),
    "Cu": (0.78, 0.50, 0.20), "Zn": (0.49, 0.50, 0.69),
    "Pd": (0.00, 0.41, 0.52), "Pt": (0.82, 0.82, 0.88),
    "Au": (1.00, 0.82, 0.14), "Ag": (0.75, 0.75, 0.75),
    "Ru": (0.14, 0.56, 0.56), "Rh": (0.04, 0.49, 0.55),
    "Mo": (0.33, 0.71, 0.71), "W":  (0.13, 0.58, 0.84),
    "Re": (0.15, 0.49, 0.67), "Os": (0.15, 0.40, 0.59),
    "Ir": (0.09, 0.33, 0.53), "Hg": (0.72, 0.72, 0.82),
}

_DEFAULT_COLOR = (0.75, 0.00, 0.75)
_DEFAULT_VDW = 1.70
_DEFAULT_COV = 0.77


def get_cpk_color(symbol: str) -> Tuple[float, float, float]:
    return CPK_COLORS.get(symbol, _DEFAULT_COLOR)


def get_vdw_radius(symbol: str) -> float:
    return VDW_RADII.get(symbol, _DEFAULT_VDW)


def get_covalent_radius(symbol: str) -> float:
    return COVALENT_RADII.get(symbol, _DEFAULT_COV)


# ============================================================
# Section 2: 3D Coordinate Generation
# ============================================================

def generate_3d_coords_rdkit(smiles: str) -> Optional[Dict[int, Tuple[float, float, float]]]:
    """RDKit ETKDG + MMFF로 3D 좌표 생성 (수소 포함 인덱스)"""
    if not RDKIT_AVAILABLE or not smiles:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        result = AllChem.EmbedMolecule(mol, params)
        if result != 0:
            result = AllChem.EmbedMolecule(mol, randomSeed=42)
            if result != 0:
                return None
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        except Exception:
            pass
        conf = mol.GetConformer()
        coords = {}
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            coords[i] = (round(pos.x, 2), round(pos.y, 2), round(pos.z, 2))
        return coords
    except Exception as e:
        logger.warning(f"RDKit 3D generation failed: {e}")
        return None


def generate_3d_full_from_smiles(smiles: str) -> Optional[Tuple[Dict, Dict, Dict]]:
    """SMILES → 수소 포함 완전한 3D 분자 데이터 생성.

    Returns:
        (atom_positions, atom_symbols, bonds) 또는 None
        - atom_positions: {int_key: (x, y, z)}
        - atom_symbols:   {int_key: 'C'/'H'/...}
        - bonds:          {(i,j): bond_order(int)}
    """
    if not RDKIT_AVAILABLE or not smiles:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mol = Chem.AddHs(mol)  # 명시적 수소 추가
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        result = AllChem.EmbedMolecule(mol, params)
        if result != 0:
            # ETKDGv3 실패 시 레거시 방법 시도
            result = AllChem.EmbedMolecule(mol, AllChem.ETKDG())
            if result != 0:
                return None
        try:
            ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
            if ff:
                ff.Minimize(maxIts=500)
        except Exception:
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            except Exception:
                pass

        conf = mol.GetConformer()
        atom_positions: Dict[int, Tuple[float, float, float]] = {}
        atom_symbols: Dict[int, str] = {}
        for atom in mol.GetAtoms():
            i = atom.GetIdx()
            pos = conf.GetAtomPosition(i)
            atom_positions[i] = (round(float(pos.x), 3),
                                  round(float(pos.y), 3),
                                  round(float(pos.z), 3))
            atom_symbols[i] = atom.GetSymbol()

        bonds: Dict[Tuple, int] = {}
        for bond in mol.GetBonds():
            i1 = bond.GetBeginAtomIdx()
            i2 = bond.GetEndAtomIdx()
            bt = bond.GetBondTypeAsDouble()
            # [BUG-A FIX] aromatic bond: 1.5 보존 (int(round(1.5))=2 → 이중결합 오류 수정)
            if bt and abs(bt - 1.5) < 0.01:
                order = 1.5   # 방향족 비편재화 결합
            else:
                order = int(round(bt)) if bt else 1
            bonds[(i1, i2)] = order

        return atom_positions, atom_symbols, bonds
    except Exception as e:
        logger.warning(f"generate_3d_full_from_smiles failed: {e}")
        return None


def estimate_z_vsepr(atom_positions_2d: Dict, bonds: Dict, atom_symbols: Dict) -> Dict:
    """VSEPR 기반 Z축 추정"""
    result = {}
    adjacency = {}
    for (k1, k2) in bonds.keys():
        adjacency.setdefault(k1, []).append(k2)
        adjacency.setdefault(k2, []).append(k1)

    visited = set()

    def _assign_z(key, z_val):
        if key in visited:
            return
        visited.add(key)
        x, y, _ = atom_positions_2d.get(key, (0.0, 0.0, 0.0))
        result[key] = (round(x, 2), round(y, 2), round(z_val, 2))
        neighbors = adjacency.get(key, [])
        if len(neighbors) >= 3:
            for i, nkey in enumerate(neighbors):
                if nkey not in visited:
                    z_offset = 1.0 if (i % 2 == 0) else -1.0
                    _assign_z(nkey, z_val + z_offset * 0.8)
        else:
            for nkey in neighbors:
                if nkey not in visited:
                    _assign_z(nkey, z_val)

    if atom_positions_2d:
        _assign_z(next(iter(atom_positions_2d)), 0.0)
    for key in atom_positions_2d:
        if key not in result:
            x, y, _ = atom_positions_2d[key]
            result[key] = (round(x, 2), round(y, 2), 0.0)
    return result


# ============================================================
# Section 3: ORCA Output Parser
# ============================================================

class OrcaOutputParser:
    """
    ORCA .out 파일 파서.
    geometry, 에너지, 진동 주파수, 진동 모드 벡터 추출.
    """

    def __init__(self, filepath: str = None, text: str = None):
        self.filepath = filepath
        self.text = text or ""
        if filepath and not text:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    self.text = f.read()
            except Exception as e:
                logger.warning(f"ORCA file read failed: {e}")

        self.atoms: List[Tuple[str, float, float, float]] = []
        self.total_energy: Optional[float] = None       # Hartree
        self.frequencies: List[float] = []               # cm^-1
        self.ir_intensities: List[float] = []            # km/mol
        self.normal_modes: List[List[Tuple[float, float, float]]] = []
        self.dipole_moment: Optional[float] = None
        self.mulliken_charges: List[float] = []
        self.converged: bool = False

        if self.text:
            self._parse()

    def _parse(self):
        """Parse all sections from ORCA output"""
        self._parse_final_geometry()
        self._parse_energy()
        self._parse_frequencies()
        self._parse_dipole()
        self._parse_mulliken()
        self._parse_convergence()

    def _parse_final_geometry(self):
        """Extract final optimized geometry (CARTESIAN COORDINATES in Angstrom)"""
        # Look for the last "CARTESIAN COORDINATES (ANGSTROEM)" block
        pattern = r"CARTESIAN COORDINATES \(ANGSTROEM\)\s*\n-+\n(.*?)(?:\n\s*\n|\n-+)"
        matches = re.findall(pattern, self.text, re.DOTALL)
        if not matches:
            return
        block = matches[-1]  # last geometry = final
        for line in block.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    sym = parts[0]
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    self.atoms.append((sym, round(x, 2), round(y, 2), round(z, 2)))
                except ValueError:
                    continue

    def _parse_energy(self):
        """Extract total energy"""
        pattern = r"FINAL SINGLE POINT ENERGY\s+([-\d.]+)"
        matches = re.findall(pattern, self.text)
        if matches:
            try:
                self.total_energy = float(matches[-1])
            except ValueError:
                pass

    def _parse_frequencies(self):
        """Extract vibrational frequencies and IR intensities"""
        # Frequencies
        freq_pattern = r"^\s*(\d+):\s+([-\d.]+)\s+cm\*\*-1"
        for m in re.finditer(freq_pattern, self.text, re.MULTILINE):
            try:
                self.frequencies.append(float(m.group(2)))
            except ValueError:
                pass

        # IR intensities from the IR SPECTRUM block
        ir_pattern = r"^\s*(\d+):\s+[-\d.]+\s+([\d.]+)"
        ir_block_match = re.search(r"IR SPECTRUM\s*\n-+\n.*?\n-+\n(.*?)(?:\n\s*\n|\Z)",
                                   self.text, re.DOTALL)
        if ir_block_match:
            for line in ir_block_match.group(1).split("\n"):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        self.ir_intensities.append(float(parts[2]))
                    except (ValueError, IndexError):
                        pass

        # Normal modes (displacement vectors)
        self._parse_normal_modes()

    def _parse_normal_modes(self):
        """Extract normal mode displacement vectors"""
        # ORCA prints normal modes in blocks of up to 6 modes at a time
        mode_section = re.search(
            r"NORMAL MODES\s*\n-+\n(.*?)(?:\n-+\n|\Z)", self.text, re.DOTALL)
        if not mode_section:
            return

        n_atoms = len(self.atoms)
        if n_atoms == 0:
            return

        n_modes = len(self.frequencies)
        if n_modes == 0:
            return

        # Initialize mode vectors
        self.normal_modes = [[] for _ in range(n_modes)]

        block_text = mode_section.group(1)
        lines = block_text.strip().split("\n")

        # Parse column blocks
        i = 0
        while i < len(lines):
            # Find header line with mode indices
            header = lines[i].split()
            mode_indices = []
            for h in header:
                try:
                    mode_indices.append(int(h))
                except ValueError:
                    pass
            if not mode_indices:
                i += 1
                continue
            i += 1  # skip blank/header

            # Read 3*n_atoms rows of displacement data
            for row in range(3 * n_atoms):
                if i >= len(lines):
                    break
                parts = lines[i].split()
                i += 1
                if len(parts) < len(mode_indices) + 1:
                    continue
                for col_idx, mode_idx in enumerate(mode_indices):
                    if mode_idx < n_modes:
                        try:
                            val = float(parts[col_idx + 1])
                            atom_idx = row // 3
                            coord_idx = row % 3
                            # Ensure atom entry exists
                            while len(self.normal_modes[mode_idx]) <= atom_idx:
                                self.normal_modes[mode_idx].append([0.0, 0.0, 0.0])
                            self.normal_modes[mode_idx][atom_idx][coord_idx] = val
                        except (ValueError, IndexError):
                            pass

        # Convert inner lists to tuples
        for mi in range(len(self.normal_modes)):
            self.normal_modes[mi] = [tuple(v) for v in self.normal_modes[mi]]

    def _parse_dipole(self):
        """Extract dipole moment"""
        pattern = r"Magnitude \(Debye\)\s*:\s+([\d.]+)"
        m = re.search(pattern, self.text)
        if m:
            try:
                self.dipole_moment = float(m.group(1))
            except ValueError:
                pass

    def _parse_mulliken(self):
        """Extract Mulliken charges"""
        block = re.search(r"MULLIKEN ATOMIC CHARGES\s*\n-*\n(.*?)(?:Sum of|$)",
                          self.text, re.DOTALL)
        if block:
            for line in block.group(1).strip().split("\n"):
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        self.mulliken_charges.append(float(parts[1].strip()))
                    except ValueError:
                        pass

    def _parse_convergence(self):
        """Check if optimization converged"""
        self.converged = "****ORCA TERMINATED NORMALLY****" in self.text

    def get_atom_coords_dict(self) -> Dict[int, Tuple[float, float, float]]:
        """Return {index: (x,y,z)} dict"""
        return {i: (a[1], a[2], a[3]) for i, a in enumerate(self.atoms)}

    def get_atom_symbols_dict(self) -> Dict[int, str]:
        """Return {index: symbol} dict"""
        return {i: a[0] for i, a in enumerate(self.atoms)}


# ============================================================
# Section 4: PubChem API Client
# ============================================================

class PubChemClient:
    """PubChem REST API로 분자 정보 조회 (키 불필요)"""

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def lookup_by_smiles(self, smiles: str) -> Optional[Dict[str, Any]]:
        """SMILES로 PubChem 조회. 캐시 사용."""
        if not REQUESTS_AVAILABLE or not smiles:
            return None
        if smiles in self._cache:
            return self._cache[smiles]
        try:
            # Step 1: Get CID from SMILES
            url = f"{self.BASE_URL}/compound/smiles/{requests.utils.quote(smiles)}/property/" \
                  f"IUPACName,MolecularFormula,MolecularWeight,XLogP,TPSA,Complexity," \
                  f"HBondDonorCount,HBondAcceptorCount,RotatableBondCount,ExactMass/JSON"
            resp = (_pc_client._get(url, timeout=10) if _PC_CLIENT_AVAILABLE else requests.get(url, timeout=10))
            if resp is None or resp.status_code != 200:
                return None
            data = resp.json()
            props = data.get("PropertyTable", {}).get("Properties", [{}])[0]

            # Step 2: Get synonyms (common names, CAS)
            cid = props.get("CID", "")
            synonyms = []
            cas_number = ""
            if cid:
                syn_url = f"{self.BASE_URL}/compound/cid/{cid}/synonyms/JSON"
                syn_resp = (_pc_client._get(syn_url, timeout=10) if _PC_CLIENT_AVAILABLE else requests.get(syn_url, timeout=10))
                if syn_resp and syn_resp.status_code == 200:
                    syn_data = syn_resp.json()
                    syn_list = syn_data.get("InformationList", {}).get("Information", [{}])[0]
                    synonyms = syn_list.get("Synonym", [])[:10]  # Top 10
                    # Find CAS number (pattern: digits-digits-digits)
                    cas_re = re.compile(r"^\d{2,7}-\d{2}-\d$")
                    for s in synonyms:
                        if cas_re.match(s):
                            cas_number = s
                            break

            result = {
                "cid": cid,
                "iupac_name": props.get("IUPACName", ""),
                "formula": props.get("MolecularFormula", ""),
                "molecular_weight": props.get("MolecularWeight", 0),
                "exact_mass": props.get("ExactMass", 0),
                "xlogp": props.get("XLogP", None),
                "tpsa": props.get("TPSA", None),
                "complexity": props.get("Complexity", None),
                "hbd": props.get("HBondDonorCount", 0),
                "hba": props.get("HBondAcceptorCount", 0),
                "rotatable_bonds": props.get("RotatableBondCount", 0),
                "synonyms": synonyms,
                "cas_number": cas_number,
                "source": "PubChem DB",
            }
            self._cache[smiles] = result
            return result
        except Exception as e:
            logger.warning(f"PubChem lookup failed: {e}")
            return None


# ============================================================
# Section 5: Gemini AI Analyzer
# ============================================================

class GeminiAnalyzer:
    """
    Google Gemini AI를 사용한 분자 분석.
    ⚡ AI 보조 (참고용) — 신뢰도 ★★★☆☆
    """

    def __init__(self, api_key: str = None):
        # [BUG-07 수정] GOOGLE_API_KEY 우선 (server.py와 통일), GEMINI_API_KEY 폴백
        self.api_key = (api_key or
                        os.environ.get("GOOGLE_API_KEY") or
                        os.environ.get("GEMINI_API_KEY") or "")
        self.model = None
        self._configured = False

        if GEMINI_AVAILABLE and self.api_key:
            try:
                genai_lib.configure(api_key=self.api_key)
                # gemini-2.0-flash 우선, 폴백으로 1.5-flash
                try:
                    self.model = genai_lib.GenerativeModel("gemini-2.0-flash")
                except Exception:
                    self.model = genai_lib.GenerativeModel("gemini-1.5-flash")
                self._configured = True
                logger.info(f"Gemini configured (key={self.api_key[:8]}...)")
            except Exception as e:
                logger.warning(f"Gemini setup failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._configured and self.model is not None

    def analyze_molecule(self, smiles: str, properties: Dict = None,
                         orca_data: Dict = None) -> str:
        """Generate AI analysis note for molecule"""
        if not self.is_available:
            return "⚠️ Gemini API 키가 설정되지 않았습니다.\n환경변수 GEMINI_API_KEY를 설정하세요."

        prompt = self._build_prompt(smiles, properties, orca_data)
        try:
            response = self.model.generate_content(prompt)
            return f"⚡ AI 분석 (참고용 — Gemini)\n{'=' * 40}\n{response.text}"
        except Exception as e:
            return f"⚠️ AI 분석 실패: {e}"

    def _build_prompt(self, smiles: str, properties: Dict = None,
                      orca_data: Dict = None) -> str:
        parts = [
            "당신은 유기화학 전문가입니다. 다음 분자를 분석하세요.",
            f"SMILES: {smiles}",
        ]
        if properties:
            parts.append(f"분자식: {properties.get('formula', 'N/A')}")
            parts.append(f"IUPAC: {properties.get('iupac_name', 'N/A')}")
            parts.append(f"MW: {properties.get('molecular_weight', 'N/A')}")
        if orca_data:
            if orca_data.get("energy"):
                parts.append(f"DFT 에너지: {orca_data['energy']:.6f} Hartree")
            if orca_data.get("dipole"):
                parts.append(f"쌍극자 모멘트: {orca_data['dipole']:.3f} D")

        parts.extend([
            "",
            "다음 항목을 포함하여 간결하게 분석하세요 (한국어):",
            "1. 주요 작용기와 특성",
            "2. 반응성 예측 (친핵성/친전자성)",
            "3. 예상 스펙트럼 특징 (IR, NMR 핵심 피크)",
            "4. 실용적 응용/주의사항",
            "5. 흥미로운 화학적 사실",
        ])
        return "\n".join(parts)


# ============================================================
# Section 6: Molecule3DData
# ============================================================

class Molecule3DData:
    """3D 분자 좌표 + 메타데이터 컨테이너"""

    def __init__(self, atoms: Dict, bonds: Dict, theory_data: Dict = None,
                 orca_xyz: Dict = None, smiles: str = None,
                 orca_parser: OrcaOutputParser = None):
        self.atoms = atoms
        self.bonds = bonds
        self.theory_data = theory_data or {}
        self.orca_xyz = orca_xyz
        self.smiles = smiles
        self.orca_parser = orca_parser

        self.atom_positions: Dict = {}
        self.atom_symbols: Dict = {}
        self._coord_source = "Unknown"

        self._build_data()

    def _build_data(self):
        """좌표 우선순위: ORCA > RDKit > VSEPR > flat 2D"""
        base_2d = {}
        if self.theory_data and "map" in self.theory_data:
            t_map = self.theory_data["map"]
            for orig_pos, theory_pos in t_map.items():
                x = theory_pos.x() if hasattr(theory_pos, 'x') else theory_pos[0]
                y = theory_pos.y() if hasattr(theory_pos, 'y') else theory_pos[1]
                base_2d[orig_pos] = (round(x, 2), round(y, 2), 0.0)
                if orig_pos in self.atoms:
                    self.atom_symbols[orig_pos] = self.atoms[orig_pos].get("main", "C")
                else:
                    self.atom_symbols[orig_pos] = "C"
        else:
            for pos, data in self.atoms.items():
                base_2d[pos] = (round(pos[0], 2), round(pos[1], 2), 0.0)
                self.atom_symbols[pos] = data.get("main", "C")

        # Priority 1: ORCA parser
        if self.orca_parser and self.orca_parser.atoms:
            self.atom_positions = self.orca_parser.get_atom_coords_dict()
            self.atom_symbols = self.orca_parser.get_atom_symbols_dict()
            self._coord_source = "ORCA 최적화"
            return

        # Priority 2: ORCA xyz dict
        if self.orca_xyz and len(self.orca_xyz) > 0:
            self.atom_positions = dict(self.orca_xyz)
            self._coord_source = "ORCA xyz"
            return

        # Priority 3: RDKit 3D — 수소 포함 완전 데이터 재구성 (Lewis 구조 키 무시)
        # [BUG-H1 수정] Lewis 구조에 없는 수소도 RDKit에서 완전히 포함하여 표시
        if self.smiles and RDKIT_AVAILABLE:
            result = generate_3d_full_from_smiles(self.smiles)
            if result:
                rdkit_pos, rdkit_sym, rdkit_bonds = result
                self.atom_positions = rdkit_pos      # {int: (x,y,z)} — H 포함
                self.atom_symbols   = rdkit_sym      # {int: 'C'/'H'/...}
                self.bonds          = rdkit_bonds    # {(i,j): order} — RDKit 결합
                self._coord_source  = "RDKit ETKDG+MMFF (H포함)"
                return

        # Priority 4: VSEPR
        if base_2d and self.bonds:
            self.atom_positions = estimate_z_vsepr(base_2d, self.bonds, self.atom_symbols)
            self._coord_source = "VSEPR 추정"
            return

        # Priority 5: flat 2D → [BUG-10 수정] 픽셀 좌표를 Å로 변환
        # canvas grid_size=40px ≈ C-C bond(1.5Å) → 1px = 1.5/40 = 0.0375 Å
        PIXEL_TO_ANGSTROM = 1.5 / 40.0
        self.atom_positions = {}
        for key, (x, y, z) in base_2d.items():
            self.atom_positions[key] = (
                round(x * PIXEL_TO_ANGSTROM, 3),
                round(y * PIXEL_TO_ANGSTROM, 3),
                0.0,
            )
        self._coord_source = "2D (Z=0)"

    @property
    def num_atoms(self) -> int:
        return len(self.atom_positions)

    @property
    def num_bonds(self) -> int:
        return len(self.bonds)

    @property
    def coord_source(self) -> str:
        return self._coord_source

    def get_center(self) -> Tuple[float, float, float]:
        if not self.atom_positions:
            return (0.0, 0.0, 0.0)
        coords = list(self.atom_positions.values())
        n = len(coords)
        return (sum(c[0] for c in coords) / n,
                sum(c[1] for c in coords) / n,
                sum(c[2] for c in coords) / n)

    def get_bounding_size(self) -> float:
        if not self.atom_positions:
            return 1.0
        coords = list(self.atom_positions.values())
        xs, ys, zs = [c[0] for c in coords], [c[1] for c in coords], [c[2] for c in coords]
        return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)

    def get_bond_length(self, k1, k2) -> Optional[float]:
        """두 원자 간 결합 길이 (Å)"""
        if k1 in self.atom_positions and k2 in self.atom_positions:
            p1, p2 = self.atom_positions[k1], self.atom_positions[k2]
            dx, dy, dz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
            return round(math.sqrt(dx*dx + dy*dy + dz*dz), 2)
        return None

    def get_bond_angle(self, k1, k2, k3) -> Optional[float]:
        """세 원자의 결합 각도 (°), k2가 중심"""
        if all(k in self.atom_positions for k in (k1, k2, k3)):
            p1, p2, p3 = (self.atom_positions[k1], self.atom_positions[k2],
                          self.atom_positions[k3])
            v1 = (p1[0]-p2[0], p1[1]-p2[1], p1[2]-p2[2])
            v2 = (p3[0]-p2[0], p3[1]-p2[1], p3[2]-p2[2])
            dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
            m1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
            m2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
            if m1 < 1e-8 or m2 < 1e-8:
                return None
            cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
            return round(math.degrees(math.acos(cos_a)), 1)
        return None

    # ============================================================
    # 파일 내보내기 메서드 — Orca/Avogadro 호환
    # ============================================================

    def export_xyz(self) -> str:
        """XYZ 형식 내보내기 — ORCA/Avogadro/VMD 호환
        형식: N줄 원자수 / 주석줄 / 원소 X Y Z
        """
        lines = [
            str(len(self.atom_positions)),
            f"ChemGrid 3D Export | source={self._coord_source} | smiles={self.smiles or 'N/A'}"
        ]
        for key, pos in self.atom_positions.items():
            sym = self.atom_symbols.get(key, "C")
            x, y, z = pos
            lines.append(f"{sym:<4s}  {x:14.6f}  {y:14.6f}  {z:14.6f}")
        return "\n".join(lines) + "\n"

    def export_orca_inp(self, charge: int = 0, multiplicity: int = 1,
                        method: str = "B3LYP", basis: str = "def2-SVP") -> str:
        """ORCA 입력 파일(.inp) 생성 — DFT 최적화 + 진동수 계산 템플릿
        설명_오비탈.txt 기준: ! B3LYP def2-SVP (+ Freq for orbital analysis)
        """
        smiles_str = self.smiles or "unknown"
        lines = [
            f"# ChemGrid → ORCA 입력 파일",
            f"# SMILES: {smiles_str}",
            f"# 좌표 출처: {self._coord_source}",
            f"# 생성: ChemGrid 3D Export",
            f"",
            f"! {method} {basis} Opt Freq",
            f"! CPCM(Water)",
            f"",
            f"%maxcore 4096",
            f"%pal",
            f"  nprocs 4",
            f"end",
            f"",
            f"# 오비탈 분석 (HOMO/LUMO .cube 파일 생성)",
            f"%plots",
            f"  dim1 50",
            f"  dim2 50",
            f"  dim3 50",
            f"  MO(\"molecule_HOMO.cube\", homo, 0)    # HOMO",
            f"  MO(\"molecule_LUMO.cube\", lumo, 0)    # LUMO",
            f"end",
            f"",
            f"* xyz {charge} {multiplicity}",
        ]
        for key, pos in self.atom_positions.items():
            sym = self.atom_symbols.get(key, "C")
            x, y, z = pos
            lines.append(f"  {sym:<4s}  {x:14.6f}  {y:14.6f}  {z:14.6f}")
        lines.append("*")
        lines.append("")
        return "\n".join(lines)

    def export_gjf(self, charge: int = 0, multiplicity: int = 1,
                   method: str = "B3LYP", basis: str = "6-31G*") -> str:
        """Gaussian 입력 파일(.gjf) 생성 — GaussView 호환"""
        smiles_str = self.smiles or "unknown"
        lines = [
            f"%chk=molecule.chk",
            f"%nprocshared=4",
            f"%mem=4GB",
            f"#{method}/{basis} Opt Freq",
            f"",
            f"ChemGrid 3D Export | SMILES: {smiles_str}",
            f"",
            f"{charge} {multiplicity}",
        ]
        for key, pos in self.atom_positions.items():
            sym = self.atom_symbols.get(key, "C")
            x, y, z = pos
            lines.append(f" {sym:<4s}  {x:14.6f}  {y:14.6f}  {z:14.6f}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def export_mol(self) -> str:
        """MDL MOL V2000 형식 내보내기 — Avogadro/ChemDraw 호환
        RDKit 설치 시 V3000으로 자동 업그레이드.
        """
        if RDKIT_AVAILABLE and self.smiles:
            try:
                from rdkit import Chem
                from rdkit.Chem import AllChem
                mol = Chem.MolFromSmiles(self.smiles)
                if mol:
                    mol = Chem.AddHs(mol)
                    params = AllChem.ETKDGv3()
                    params.randomSeed = 42
                    if AllChem.EmbedMolecule(mol, params) == 0:
                        try:
                            AllChem.MMFFOptimizeMolecule(mol)
                        except Exception:
                            pass
                        return Chem.MolToMolBlock(mol)
            except Exception as e:
                logger.warning(f"RDKit MOL export failed: {e}")

        # 수동 V2000 생성 (RDKit 없거나 실패 시)
        keys = list(self.atom_positions.keys())
        key_idx = {k: i + 1 for i, k in enumerate(keys)}
        n_atoms = len(keys)
        n_bonds = len(self.bonds)
        lines = [
            "\n     ChemGrid         3D\n",
            f"{n_atoms:3d}{n_bonds:3d}  0  0  0  0  0  0  0  0999 V2000"
        ]
        for key in keys:
            pos = self.atom_positions[key]
            sym = self.atom_symbols.get(key, "C")
            x, y, z = pos
            lines.append(f"   {x:8.4f}   {y:8.4f}   {z:8.4f} {sym:<3s}  0  0  0  0  0  0  0  0  0  0  0  0")
        for (k1, k2), order in self.bonds.items():
            i1, i2 = key_idx.get(k1, 1), key_idx.get(k2, 1)
            bo = min(int(order) if isinstance(order, int) else 1, 3)
            lines.append(f"{i1:3d}{i2:3d}{bo:3d}  0  0  0  0")
        lines.append("M  END")
        return "\n".join(lines)


# ============================================================
# Section 7: OpenGL Renderers
# ============================================================

class GLQuadricManager:
    def __init__(self):
        self._sq = None
        self._cq = None

    def sphere(self):
        if self._sq is None:
            self._sq = gluNewQuadric()
            gluQuadricNormals(self._sq, GLU_SMOOTH)
        return self._sq

    def cylinder(self):
        if self._cq is None:
            self._cq = gluNewQuadric()
            gluQuadricNormals(self._cq, GLU_SMOOTH)
        return self._cq

    def cleanup(self):
        if self._sq:
            gluDeleteQuadric(self._sq)
            self._sq = None
        if self._cq:
            gluDeleteQuadric(self._cq)
            self._cq = None


def _set_material(r, g, b, a=1.0):
    """Material 설정 — CPK 색상 강조를 위해 ambient/specular 증가.
    [BUG-C1 수정] glColor4f 명시 호출로 GL_COLOR_MATERIAL과 동기화.
    GL_COLOR_MATERIAL 활성화 시 glColor가 ambient+diffuse를 override하므로
    glColor4f를 먼저 호출하여 CPK 색상이 정확히 반영되도록 함.
    """
    glColor4f(r, g, b, a)  # GL_COLOR_MATERIAL → ambient+diffuse 즉시 반영
    glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [r*0.35, g*0.35, b*0.35, a])
    glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [r, g, b, a])
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.7, 0.7, 0.7, a])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 70.0)


def _draw_cylinder(quad, p1, p2, radius, slices=10):
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2-x1, y2-y1, z2-z1
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length < 1e-6:
        return
    glPushMatrix()
    glTranslatef(x1, y1, z1)
    nx, ny, nz = dx/length, dy/length, dz/length
    if abs(nz) > 0.9999:
        if nz < 0:
            glRotatef(180.0, 1.0, 0.0, 0.0)
    else:
        angle = math.degrees(math.acos(max(-1.0, min(1.0, nz))))
        ax, ay = -ny, nx
        al = math.sqrt(ax*ax + ay*ay)
        if al > 1e-8:
            glRotatef(angle, ax/al, ay/al, 0.0)
    gluCylinder(quad, radius, radius, length, slices, 1)
    glPopMatrix()


def _draw_arrow(quad, origin, direction, length, radius=0.06, color=(1, 0, 0)):
    """진동 모드용 화살표 그리기"""
    _set_material(*color)
    tip = (origin[0]+direction[0]*length,
           origin[1]+direction[1]*length,
           origin[2]+direction[2]*length)
    _draw_cylinder(quad, origin, tip, radius, 6)
    # Arrowhead (cone)
    glPushMatrix()
    glTranslatef(*tip)
    dx, dy, dz = direction
    dl = math.sqrt(dx*dx + dy*dy + dz*dz)
    if dl > 1e-6:
        nx, ny, nz = dx/dl, dy/dl, dz/dl
        if abs(nz) > 0.9999:
            if nz < 0:
                glRotatef(180.0, 1.0, 0.0, 0.0)
        else:
            ang = math.degrees(math.acos(max(-1.0, min(1.0, nz))))
            ax, ay = -ny, nx
            al = math.sqrt(ax*ax + ay*ay)
            if al > 1e-8:
                glRotatef(ang, ax/al, ay/al, 0.0)
    cone = gluNewQuadric()
    gluCylinder(cone, radius*2.5, 0.0, length*0.15, 8, 1)
    gluDeleteQuadric(cone)
    glPopMatrix()


class BallAndStickRenderer:
    # [FIX-BALL-SIZE] 원자 크기 축소: 1.35 → 0.45 (원자 겹침 방지, 표준 BnS 비율)
    # 표준 ball-and-stick: 원자 반지름 ≈ covalent_r × 0.45
    # C-C bond = 1.54Å, cov_r(C) = 0.76Å → ball_r = 0.34Å < 0.77Å (half-bond) → 원자 비겹침
    ATOM_SCALE = 0.45       # [FIX] 기존 1.35 → 0.45 (C=그레이, H=흰색 구분 명확)
    BOND_RADIUS = 0.10      # 결합 두께 (원자 비율에 맞게 소폭 축소)

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData, vib_vectors=None, vib_scale=0.0,
               small_atoms: bool = False):
        """Ball-and-stick 렌더링.

        Args:
            small_atoms: True이면 π 오비탈 모드 — 원자를 점 크기(covalent×0.12)로 축소.
                         원소 색상은 CPK 그대로 유지하여 원소 구분 가능.
        """
        sq, cq = self.qm.sphere(), self.qm.cylinder()
        atom_scale = 0.12 if small_atoms else self.ATOM_SCALE

        # Bonds (π 오비탈 모드에서도 결합선은 유지 — 분자 골격 파악용)
        _set_material(0.60, 0.60, 0.60)
        for (k1, k2), order in mol_data.bonds.items():
            if k1 in mol_data.atom_positions and k2 in mol_data.atom_positions:
                p1, p2 = mol_data.atom_positions[k1], mol_data.atom_positions[k2]
                bo = order if isinstance(order, int) else 1
                bond_r = self.BOND_RADIUS * (0.5 if small_atoms else 1.0)
                if bo == 1:
                    _draw_cylinder(cq, p1, p2, bond_r, 10)
                elif isinstance(bo, float) and abs(bo - 1.5) < 0.01:
                    # [BUG-A FIX] 방향족 비편재화 결합: 단일 실린더 + 얇은 오프셋 (dashed aromatic)
                    _draw_cylinder(cq, p1, p2, bond_r, 10)  # 단일 결합 표현
                    self._aromatic_bond_overlay(cq, p1, p2, bond_r * 0.5)  # 점선 오버레이
                else:
                    self._multi_bond(cq, p1, p2, min(int(round(bo)), 3))

        # Atoms
        keys = list(mol_data.atom_positions.keys())
        for idx, (pos, coords) in enumerate(mol_data.atom_positions.items()):
            sym = mol_data.atom_symbols.get(pos, "C")
            r, g, b = get_cpk_color(sym)
            _set_material(r, g, b)
            rad = get_covalent_radius(sym) * atom_scale

            # Apply vibration displacement
            cx, cy, cz = coords
            if vib_vectors and idx < len(vib_vectors) and abs(vib_scale) > 0.001:
                vx, vy, vz = vib_vectors[idx]
                cx += vx * vib_scale
                cy += vy * vib_scale
                cz += vz * vib_scale

            glPushMatrix()
            glTranslatef(cx, cy, cz)
            gluSphere(sq, rad, 20, 16)
            glPopMatrix()

            # Vibration arrows
            if vib_vectors and idx < len(vib_vectors) and abs(vib_scale) > 0.01:
                vx, vy, vz = vib_vectors[idx]
                mag = math.sqrt(vx*vx + vy*vy + vz*vz)
                if mag > 0.01:
                    _draw_arrow(cq, (cx, cy, cz), (vx/mag, vy/mag, vz/mag),
                                mag * abs(vib_scale) * 0.5, 0.04, (0.2, 1.0, 0.2))

    def _perpendicular_offset(self, p1, p2, dist):
        """두 점 사이 결합의 수직 오프셋 벡터 계산"""
        dx, dy, dz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
        l = math.sqrt(dx*dx + dy*dy + dz*dz)
        if l < 1e-6:
            return (0, 0, 0)
        bx, by, bz = dx/l, dy/l, dz/l
        # 수직 벡터 계산 (cross product with arbitrary axis)
        if abs(bx) < 0.9:
            px, py, pz = 0.0, bz, -by
        else:
            px, py, pz = -bz, 0.0, bx
        pl = math.sqrt(px*px + py*py + pz*pz)
        if pl < 1e-8:
            return (0, 0, 0)
        return (px/pl * dist, py/pl * dist, pz/pl * dist)

    def _multi_bond(self, cq, p1, p2, count):
        """v4: 이중결합 2개 평행, 삼중결합 3개 평행 실린더"""
        _set_material(0.60, 0.60, 0.60)
        if count == 2:
            # 이중결합: 2개 대칭 오프셋 실린더
            ox, oy, oz = self._perpendicular_offset(p1, p2, 0.12)
            np1a = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
            np2a = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
            np1b = (p1[0]-ox, p1[1]-oy, p1[2]-oz)
            np2b = (p2[0]-ox, p2[1]-oy, p2[2]-oz)
            _draw_cylinder(cq, np1a, np2a, self.BOND_RADIUS * 0.75, 10)
            _draw_cylinder(cq, np1b, np2b, self.BOND_RADIUS * 0.75, 10)
        elif count >= 3:
            # 삼중결합: 중앙 1개 + 양쪽 오프셋 2개
            _draw_cylinder(cq, p1, p2, self.BOND_RADIUS * 0.7, 10)
            ox, oy, oz = self._perpendicular_offset(p1, p2, 0.15)
            np1a = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
            np2a = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
            np1b = (p1[0]-ox, p1[1]-oy, p1[2]-oz)
            np2b = (p2[0]-ox, p2[1]-oy, p2[2]-oz)
            _draw_cylinder(cq, np1a, np2a, self.BOND_RADIUS * 0.6, 10)
            _draw_cylinder(cq, np1b, np2b, self.BOND_RADIUS * 0.6, 10)

    def cleanup(self):
        self.qm.cleanup()


class SpaceFillingRenderer:
    # [BUG-SF1 수정] SCALE=0.5→1.0: VDW 반경 자체가 실제 원자 크기이므로 축소 불필요
    # space-filling은 원자들이 겹쳐야 분자 형태가 보임
    SCALE = 1.0

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData, vib_vectors=None, vib_scale=0.0):
        sq = self.qm.sphere()
        for idx, (pos, coords) in enumerate(mol_data.atom_positions.items()):
            sym = mol_data.atom_symbols.get(pos, "C")
            r, g, b = get_cpk_color(sym)
            _set_material(r, g, b)
            rad = get_vdw_radius(sym) * self.SCALE
            cx, cy, cz = coords
            if vib_vectors and idx < len(vib_vectors) and abs(vib_scale) > 0.001:
                vx, vy, vz = vib_vectors[idx]
                cx += vx * vib_scale
                cy += vy * vib_scale
                cz += vz * vib_scale
            glPushMatrix()
            glTranslatef(cx, cy, cz)
            gluSphere(sq, rad, 32, 24)
            glPopMatrix()

    def cleanup(self):
        self.qm.cleanup()


# ============================================================================
# [CHEM-6] Pi 오비탈 렌더러 — sp2/sp 전자구름 및 방향족 π cloud
# ============================================================================

class PiOrbitalRenderer:
    """[CHEM-6] sp2/sp π 오비탈 및 방향족 전자구름 3D 렌더러.

    ORCA/Avogadro 스타일 근사:
    - sp2/sp 탄소 p 오비탈: 분자 평면에 수직 방향 두 로브 (반투명 타원체)
    - 방향족 고리: 고리 평면 위아래 π 전자구름 (반투명 납작 디스크)
    - 전자구름 모드: 원자 반지름을 점 크기(ORBITAL_ATOM_SCALE)로 극소화

    이론적 근거:
    - sp2 p 오비탈 파동함수: ψ ∝ r·cos(θ)·exp(-ζr) (Slater-type 근사)
      → 결합 평면 수직 방향 두 로브, 각 로브 크기 ~ C-C 결합 길이의 45%
    - 방향족 π 시스템: 고리 평면 위아래 도넛형 전자 분포
      → ORCA/Avogadro에서 isovalue 0.04 au 기준 시각화와 일치
    - 원자 색상: CPK 표준 유지 (원소 구분)
    - 반투명도: 오비탈 로브 α=0.45, 방향족 π cloud α=0.35
    """
    ORBITAL_ATOM_SCALE = 0.15   # 전자구름 모드 원자 크기 (covalent radius × 15%)
    LOBE_COLOR_POS = (0.25, 0.50, 1.00, 0.45)    # 양의 위상: 파란색 반투명
    LOBE_COLOR_NEG = (1.00, 0.35, 0.25, 0.45)    # 음의 위상: 빨간색 반투명
    RING_CLOUD_COLOR = (0.25, 0.50, 1.00, 0.35)  # 방향족 π cloud: 파란색 35%

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData):
        """Pi 오비탈 및 전자구름을 렌더링합니다."""
        if not OPENGL_AVAILABLE:
            return
        try:
            # 분자 평면 법선 벡터 계산 (SVD)
            normal = self._calc_molecular_plane_normal(mol_data)

            # RDKit으로 sp2/방향족 원자 + 고리 정보 감지
            sp2_keys, ring_groups = self._detect_sp2_and_rings(mol_data)

            sq = self.qm.sphere()

            # ── sp2/sp 원자의 p 오비탈 로브 렌더링 ──────────────
            for key in sp2_keys:
                pos = mol_data.atom_positions.get(key)
                if pos is None:
                    continue
                self._draw_p_orbital_lobes(sq, pos, normal)

            # ── 방향족 고리 π cloud 렌더링 ─────────────────────
            for ring_positions in ring_groups:
                self._draw_ring_pi_cloud(sq, ring_positions, normal)

        except Exception:
            pass  # RDKit 없거나 OpenGL 오류 시 조용히 실패

    def _calc_molecular_plane_normal(self, mol_data: Molecule3DData):
        """원자 좌표로부터 분자 평면 법선 벡터를 계산합니다 (SVD 기반)."""
        try:
            import numpy as np
            positions = list(mol_data.atom_positions.values())
            if len(positions) < 3:
                return (0.0, 0.0, 1.0)
            pts = np.array(positions, dtype=float)
            centroid = pts.mean(axis=0)
            _, _, Vt = np.linalg.svd(pts - centroid)
            normal = Vt[-1]  # 최소 분산 방향 = 법선
            norm_len = float(np.linalg.norm(normal))
            if norm_len < 1e-6:
                return (0.0, 0.0, 1.0)
            n = normal / norm_len
            return (float(n[0]), float(n[1]), float(n[2]))
        except Exception:
            return (0.0, 0.0, 1.0)

    def _detect_sp2_and_rings(self, mol_data: Molecule3DData):
        """RDKit으로 sp2 원자 키 목록과 방향족 고리 좌표 그룹을 반환합니다."""
        sp2_keys = []
        ring_groups = []
        try:
            from rdkit import Chem
            smiles = getattr(mol_data, 'smiles', '') or ''
            if not smiles:
                return sp2_keys, ring_groups
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return sp2_keys, ring_groups

            atom_keys = list(mol_data.atom_positions.keys())

            # sp2 원자 감지
            HybSP2 = Chem.rdchem.HybridizationType.SP2
            HybSP = Chem.rdchem.HybridizationType.SP
            for atom in mol.GetAtoms():
                idx = atom.GetIdx()
                if idx < len(atom_keys):
                    hyb = atom.GetHybridization()
                    if hyb in (HybSP2, HybSP):
                        sp2_keys.append(atom_keys[idx])

            # 방향족 고리 감지
            ring_info = mol.GetRingInfo()
            for ring in ring_info.AtomRings():
                if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                    ring_pos = []
                    for i in ring:
                        if i < len(atom_keys):
                            pos = mol_data.atom_positions.get(atom_keys[i])
                            if pos is not None:
                                ring_pos.append(pos)
                    if len(ring_pos) >= 3:
                        ring_groups.append(ring_pos)
        except ImportError:
            # RDKit 없으면 결합 수로 sp2 추정 (이중결합 갖는 원자)
            for key, pos in mol_data.atom_positions.items():
                bond_count = sum(1 for (k1, k2) in mol_data.bonds
                                 if key == k1 or key == k2)
                sym = mol_data.atom_symbols.get(key, 'C')
                if sym == 'C' and bond_count == 3:
                    sp2_keys.append(key)
        except Exception:
            pass
        return sp2_keys, ring_groups

    def _draw_p_orbital_lobes(self, sq, pos, normal):
        """sp2 원자의 p 오비탈 두 로브를 반투명 타원체로 그립니다.

        ORCA/Avogadro 기준: p 오비탈 로브는 결합 평면에 수직,
        각 로브 크기 = C-C 결합 길이(1.54Å)의 약 45% ≈ 0.70Å.
        """
        import math
        nx, ny, nz = normal
        x, y, z = pos
        lobe_size = 0.55    # 로브 반지름 (Å)
        lobe_dist = 0.42    # 원자에서 로브 중심까지 거리 (Å)

        # 법선→Z축 회전각 계산
        # [BUG-O1 수정] Z × N = (0,0,1) × (nx,ny,nz) = (-ny, nx, 0)
        # 이전 코드 rx,ry = ny,-nx 는 부호가 뒤집혀 오비탈 방향이 틀렸음
        dot = max(-1.0, min(1.0, nz))
        angle_deg = math.degrees(math.acos(dot))
        rx, ry = -ny, nx   # 올바른 회전축: Z × N

        for sign, color in ((+1, self.LOBE_COLOR_POS), (-1, self.LOBE_COLOR_NEG)):
            cx = x + sign * nx * lobe_dist
            cy = y + sign * ny * lobe_dist
            cz = z + sign * nz * lobe_dist

            glPushMatrix()
            glTranslatef(cx, cy, cz)

            # 법선 방향으로 정렬 (Z→normal)
            if angle_deg > 0.5:
                rl = math.sqrt(rx*rx + ry*ry)
                if rl > 1e-6:
                    glRotatef(angle_deg, rx/rl, ry/rl, 0.0)

            # [FIX-ORB-SHAPE] Z 1.40배로 줄임 → 더 둥근 구름 형태 (isovalue 0.04 근사)
            # ORCA 기준 p 오비탈 이미지는 2:1 비율 → scale_z=1.40, XY=0.78
            glScalef(0.78, 0.78, 1.40)

            r, g, b, a = color
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            # [FIX-ORBITAL-COLOR] GL_COLOR_MATERIAL 활성화 시 glMaterialfv(AMBIENT_AND_DIFFUSE) 무시됨
            # → glColor4f로 직접 설정해야 오비탈 색상이 적용됨
            glColor4f(r, g, b, a)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.3, 0.4, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 35.0)
            gluSphere(sq, lobe_size, 20, 14)
            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)
            glPopMatrix()

    def _draw_ring_pi_cloud(self, sq, ring_positions, normal):
        """방향족 고리의 π 전자구름을 위아래 납작 디스크로 그립니다.

        ORCA 기준: 방향족 π MO (HOMO/HOMO-1)는 고리 평면 위아래
        약 0.6~0.8Å에 최대 전자밀도 → 납작한 원판 형태로 시각화.
        """
        import math
        if not ring_positions:
            return

        # 고리 무게중심
        cx = sum(p[0] for p in ring_positions) / len(ring_positions)
        cy = sum(p[1] for p in ring_positions) / len(ring_positions)
        cz = sum(p[2] for p in ring_positions) / len(ring_positions)

        # 고리 반지름
        ring_radius = sum(
            math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2)
            for p in ring_positions
        ) / len(ring_positions)

        nx, ny, nz = normal
        cloud_offset = 0.65   # 고리 면에서 π cloud 중심까지 (Å)
        disk_flat = 0.28      # 납작 정도 (Z 스케일)

        dot = max(-1.0, min(1.0, nz))
        angle_deg = math.degrees(math.acos(dot))
        # [BUG-O1 수정] 올바른 회전축: Z × N = (-ny, nx, 0)
        rx, ry = -ny, nx

        r, g, b, a = self.RING_CLOUD_COLOR

        for sign in (+1, -1):
            dcx = cx + sign * nx * cloud_offset
            dcy = cy + sign * ny * cloud_offset
            dcz = cz + sign * nz * cloud_offset

            glPushMatrix()
            glTranslatef(dcx, dcy, dcz)

            if angle_deg > 0.5:
                rl = math.sqrt(rx*rx + ry*ry)
                if rl > 1e-6:
                    glRotatef(angle_deg, rx/rl, ry/rl, 0.0)

            # 납작한 원판: 고리 반지름에 맞게 XY 확장, Z 축소
            disk_scale = ring_radius * 1.10
            glScalef(disk_scale, disk_scale, disk_flat)

            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            # [FIX-ORBITAL-COLOR] π ring cloud 색상 직접 설정
            glColor4f(r, g, b, a)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.15, 0.20, 0.50, 0.60])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 18.0)
            gluSphere(sq, 1.0, 28, 18)  # radius=1 후 glScalef로 형태 결정
            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)
            glPopMatrix()

    def cleanup(self):
        self.qm.cleanup()


# ============================================================================
# [CHEM-8] 고차원 오비탈 렌더러 — sp3d2/d/f 오비탈 및 전이금속 착물
# ============================================================================

class AdvancedOrbitalRenderer:
    """[CHEM-8] 고차원 오비탈 3D 렌더러.

    지원 오비탈 유형:
    - sp (선형 2 σ로브 + 2 π) — 아세틸렌, CO₂
    - sp2 (삼각평면 3 σ + 1 π) — 에틸렌, 벤젠
    - sp3 (사면체 4 σ) — 메탄, 물
    - sp3d (삼각쌍뿔 5) — PCl₅, SF₄
    - sp3d2 (정팔면체 6) — SF₆, 전이금속 착물 [Fe(CN)₆]³⁻ 등
    - d 오비탈 (Oh: t₂g/eg, Td: e/t₂) — Fe²⁺, Co²⁺, Ni²⁺, Cr³⁺
    - f 오비탈 (8 cubic lobes) — La~Lu, Th~Lr

    이론적 근거:
    - ORCA/Avogadro 기준: GTO 기저 기반 isosurface isovalue=0.04 au
    - σ 로브 크기 ≈ C-C 결합 길이(1.54 Å)의 45~55%
    - d 오비탈 t₂g(dxy/dxz/dyz): 축 사이 방향, eg(dx²-y²/dz²): 축 방향
    - Crystal Field Splitting: Oh → Δo 에너지 차이로 t₂g/eg 색상 구분
    - 전이금속 착물 ORCA 입력: ! B3LYP def2-TZVP NBO
    - QM/MM(ORCA): 단백질 결합 시뮬레이션 지원 (CHEM-10 장기 계획)
    """

    # 전이금속 d-block 원소 (3d ~ 5d)
    TRANSITION_METALS = {
        'Sc','Ti','V','Cr','Mn','Fe','Co','Ni','Cu','Zn',
        'Y','Zr','Nb','Mo','Tc','Ru','Rh','Pd','Ag','Cd',
        'La','Hf','Ta','W','Re','Os','Ir','Pt','Au','Hg',
    }
    # f-block (란타나이드 + 악티나이드)
    F_BLOCK = {
        'Ce','Pr','Nd','Pm','Sm','Eu','Gd','Tb','Dy','Ho','Er','Tm','Yb','Lu',
        'Th','Pa','U','Np','Pu','Am','Cm','Bk','Cf','Es','Fm','Md','No','Lr',
    }

    # 오비탈 로브 색상 (ORCA/Avogadro 표준 — 위상에 따라 파란/빨간)
    # [FIX-ORB-ALPHA] alpha 0.45 → 0.65 (더 선명한 오비탈 가시성)
    COLOR_SIGMA_POS = (0.25, 0.50, 1.00, 0.65)   # σ +위상: 파랑
    COLOR_SIGMA_NEG = (1.00, 0.35, 0.25, 0.65)   # σ -위상: 빨강
    COLOR_PI        = (0.25, 0.50, 1.00, 0.55)   # π 로브: 연파랑
    COLOR_T2G       = (0.20, 0.80, 0.40, 0.60)   # t₂g: 초록 (낮은 에너지)
    COLOR_EG        = (1.00, 0.80, 0.10, 0.60)   # eg: 노랑 (높은 에너지)
    COLOR_F_A       = (0.60, 0.20, 0.80, 0.55)   # f +: 보라
    COLOR_F_B       = (0.80, 0.60, 0.20, 0.55)   # f -: 황갈색

    def __init__(self):
        self.qm = GLQuadricManager()
        # ORCA NBO 점유수 캐시 (원자키 → {오비탈유형: 점유수})
        self._nbo_occupations: Dict = {}

    def set_nbo_data(self, nbo_data: Dict):
        """ORCA NBO(Natural Bond Orbital) 점유수 데이터 주입.
        Format: {atom_index: {'dxy': 1.85, 'dxz': 1.90, ...}}
        """
        self._nbo_occupations = nbo_data or {}

    def render(self, mol_data: Molecule3DData, orbital_mode: str = 'hybrid'):
        """오비탈 렌더링 메인 진입점.

        orbital_mode:
          'hybrid'   — sp/sp2/sp3/sp3d/sp3d2 혼성 오비탈
          'd_orbital' — 전이금속 d 오비탈 (crystal field)
          'f_orbital' — 란타나이드/악티나이드 f 오비탈
          'all'       — 모든 유형 동시 표시
        """
        if not OPENGL_AVAILABLE:
            return
        try:
            sq = self.qm.sphere()
            atom_info = self._analyze_atoms(mol_data)
            for key, info in atom_info.items():
                pos = mol_data.atom_positions.get(key)
                if pos is None:
                    continue
                sym = info['sym']
                if sym in self.F_BLOCK and orbital_mode in ('f_orbital', 'all'):
                    self._render_f(sq, pos)
                if sym in self.TRANSITION_METALS and orbital_mode in ('d_orbital', 'all'):
                    self._render_d(sq, pos, info)
                if orbital_mode in ('hybrid', 'all'):
                    self._render_hybrid(sq, pos, info)
        except Exception as e:
            logger.warning("AdvancedOrbitalRenderer.render error: %s", e)

    # ------------------------------------------------------------------
    # 분석
    # ------------------------------------------------------------------
    def _analyze_atoms(self, mol_data: Molecule3DData) -> Dict:
        """RDKit 혼성화 + 실제 결합 방향 분석."""
        adj: Dict = {}
        for (k1, k2), order in mol_data.bonds.items():
            adj.setdefault(k1, []).append((k2, int(order) if isinstance(order, int) else 1))
            adj.setdefault(k2, []).append((k1, int(order) if isinstance(order, int) else 1))

        # RDKit 혼성화
        rdkit_hyb: Dict = {}
        try:
            from rdkit import Chem
            smiles = getattr(mol_data, 'smiles', '') or ''
            if smiles:
                rmol = Chem.MolFromSmiles(smiles)
                if rmol:
                    HYB = Chem.rdchem.HybridizationType
                    HYB_MAP = {HYB.SP:'sp', HYB.SP2:'sp2', HYB.SP3:'sp3',
                               HYB.SP3D:'sp3d', HYB.SP3D2:'sp3d2'}
                    atom_keys = list(mol_data.atom_positions.keys())
                    for atom in rmol.GetAtoms():
                        idx = atom.GetIdx()
                        if idx < len(atom_keys):
                            h = HYB_MAP.get(atom.GetHybridization())
                            if h:
                                rdkit_hyb[atom_keys[idx]] = h
        except Exception:
            pass

        result: Dict = {}
        for key, pos in mol_data.atom_positions.items():
            sym = mol_data.atom_symbols.get(key, 'C')
            neighbors = adj.get(key, [])
            ndirs = []
            for (nkey, order) in neighbors:
                npos = mol_data.atom_positions.get(nkey)
                if npos:
                    dx, dy, dz = npos[0]-pos[0], npos[1]-pos[1], npos[2]-pos[2]
                    l = math.sqrt(dx*dx + dy*dy + dz*dz)
                    if l > 1e-6:
                        ndirs.append((dx/l, dy/l, dz/l, order))

            hyb = rdkit_hyb.get(key)
            if not hyb:
                n = len(ndirs)
                if sym in self.TRANSITION_METALS:
                    hyb = {6:'sp3d2', 5:'sp3d', 4:'sp3', 3:'sp2', 2:'sp'}.get(n, 'sp3')
                else:
                    hyb = {2:'sp', 3:'sp2'}.get(n, 'sp3')

            result[key] = {'sym': sym, 'hyb': hyb, 'ndirs': ndirs, 'pos': pos}
        return result

    # ------------------------------------------------------------------
    # 혼성 오비탈 렌더링
    # ------------------------------------------------------------------
    def _render_hybrid(self, sq, pos, info):
        # [FIX-ORB-H] H 원자는 1s 오비탈 — 로브 렌더링 생략 (페놀 sp3 오류 방지)
        # H는 이웃 원자가 1개이므로 ndirs 1개 → sp3으로 오분류 → 4 로브 오표시 방지
        if info['sym'] == 'H':
            return
        hyb = info['hyb']
        ndirs = [(d[0], d[1], d[2]) for d in info['ndirs']]
        {
            'sp':    self._sp,
            'sp2':   self._sp2,
            'sp3':   self._sp3,
            'sp3d':  self._sp3d,
            'sp3d2': self._sp3d2,
        }.get(hyb, self._sp3)(sq, pos, ndirs)

    def _sp(self, sq, pos, ndirs):
        """sp: 2 σ 로브 + 2 π 오비탈 쌍"""
        dirs = list(ndirs[:2])
        ideal = [(0,0,1),(0,0,-1)]
        while len(dirs) < 2:
            dirs.append(ideal[len(dirs)])
        self._lobe(sq, pos, dirs[0], 2.5, 0.45, self.COLOR_SIGMA_POS)
        self._lobe(sq, pos, dirs[1], 2.5, 0.45, self.COLOR_SIGMA_NEG)
        # π 오비탈: σ축에 수직인 두 방향
        p1 = self._perp(dirs[0])
        p2 = self._cross3(dirs[0], p1)
        for pv in (p1, p2):
            for s in (+1, -1):
                self._lobe(sq, pos, (pv[0]*s, pv[1]*s, pv[2]*s), 2.0, 0.42, self.COLOR_PI)

    def _sp2(self, sq, pos, ndirs):
        """sp2: 3 σ 로브 + 1 π 오비탈 (면 수직)"""
        dirs = list(ndirs[:3])
        ideal = [(1,0,0),(-0.5,0.866,0),(-0.5,-0.866,0)]
        while len(dirs) < 3:
            dirs.append(ideal[len(dirs)])
        for i, d in enumerate(dirs[:3]):
            c = self.COLOR_SIGMA_POS if i%2==0 else self.COLOR_SIGMA_NEG
            self._lobe(sq, pos, d, 2.2, 0.48, c)
        # π 오비탈: 분자면 법선
        if len(dirs) >= 2:
            pn = self._cross3(dirs[0], dirs[1])
            pl = math.sqrt(sum(x*x for x in pn))
            if pl > 1e-6:
                pn = tuple(x/pl for x in pn)
                self._lobe(sq, pos, pn, 2.0, 0.52, self.COLOR_SIGMA_NEG)
                self._lobe(sq, pos, tuple(-x for x in pn), 2.0, 0.52, self.COLOR_SIGMA_POS)

    def _sp3(self, sq, pos, ndirs):
        """sp3: 4 σ 로브 (사면체)"""
        dirs = list(ndirs[:4])
        ideal = [(0.577,0.577,0.577),(0.577,-0.577,-0.577),
                 (-0.577,0.577,-0.577),(-0.577,-0.577,0.577)]
        while len(dirs) < 4:
            dirs.append(ideal[len(dirs)])
        for i, d in enumerate(dirs[:4]):
            c = self.COLOR_SIGMA_POS if i%2==0 else self.COLOR_SIGMA_NEG
            self._lobe(sq, pos, d, 2.0, 0.50, c)

    def _sp3d(self, sq, pos, ndirs):
        """sp3d: 5 로브 — 삼각쌍뿔 (3 적도 + 2 축)"""
        dirs = list(ndirs[:5])
        eq_ideal = [(1,0,0),(-0.5,0.866,0),(-0.5,-0.866,0)]
        ax_ideal = [(0,0,1),(0,0,-1)]
        eq = dirs[:3] if len(dirs)>=3 else dirs[:len(dirs)] + eq_ideal[len(dirs):]
        while len(eq)<3: eq.append(eq_ideal[len(eq)])
        ax = dirs[3:5] if len(dirs)>=5 else dirs[3:len(dirs)] + ax_ideal[len(dirs)-3:]
        while len(ax)<2: ax.append(ax_ideal[len(ax)])
        for i,d in enumerate(eq):
            c = self.COLOR_SIGMA_POS if i%2==0 else self.COLOR_SIGMA_NEG
            self._lobe(sq, pos, d, 2.0, 0.50, c)
        for i,d in enumerate(ax):
            c = self.COLOR_SIGMA_NEG if i==0 else self.COLOR_SIGMA_POS
            self._lobe(sq, pos, d, 2.4, 0.45, c)  # 축 결합: 더 긴 로브

    def _sp3d2(self, sq, pos, ndirs):
        """sp3d2: 6 로브 — 정팔면체 (±x, ±y, ±z)"""
        dirs = list(ndirs[:6])
        ideal = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
        while len(dirs)<6: dirs.append(ideal[len(dirs)])
        for i,d in enumerate(dirs[:6]):
            c = self.COLOR_SIGMA_POS if i%2==0 else self.COLOR_SIGMA_NEG
            self._lobe(sq, pos, d, 2.0, 0.48, c)

    # ------------------------------------------------------------------
    # d 오비탈 렌더링 (전이금속)
    # ------------------------------------------------------------------
    def _render_d(self, sq, pos, info):
        """전이금속 d 오비탈: Oh(정팔면체) vs Td(사면체) Crystal Field."""
        n = len(info['ndirs'])
        if n >= 6:
            # 정팔면체 Oh: t₂g (3개, 낮은 에너지) + eg (2개, 높은 에너지)
            # t₂g: dxy, dxz, dyz — 축 사이 방향 (4 로브)
            for lobes in [
                [(0.707,0.707,0),(-0.707,0.707,0),(-0.707,-0.707,0),(0.707,-0.707,0)],  # dxy
                [(0.707,0,0.707),(-0.707,0,0.707),(-0.707,0,-0.707),(0.707,0,-0.707)],  # dxz
                [(0,0.707,0.707),(0,-0.707,0.707),(0,-0.707,-0.707),(0,0.707,-0.707)],  # dyz
            ]:
                for d in lobes:
                    self._lobe(sq, pos, d, 1.4, 0.38, self.COLOR_T2G)
            # eg: dx²-y² (4 로브, 축 방향) + dz² (2 로브 + torus)
            for d in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0)]:   # dx²-y²
                self._lobe(sq, pos, d, 1.6, 0.40, self.COLOR_EG)
            for d in [(0,0,1),(0,0,-1)]:                     # dz² 로브
                self._lobe(sq, pos, d, 1.8, 0.42, self.COLOR_EG)
            self._torus(sq, pos, 0.52, 0.17)                 # dz² 도넛
        elif n == 4:
            # 사면체 Td: e (dz², dx²-y²) + t₂ (dxy, dxz, dyz)
            for d in [(0,0,1),(0,0,-1)]:
                self._lobe(sq, pos, d, 1.5, 0.38, self.COLOR_EG)
            for d in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0)]:
                self._lobe(sq, pos, d, 1.3, 0.36, self.COLOR_EG)
            for lobes in [[(0.707,0.707,0),(-0.707,0.707,0),(-0.707,-0.707,0),(0.707,-0.707,0)],
                          [(0.707,0,0.707),(-0.707,0,0.707),(-0.707,0,-0.707),(0.707,0,-0.707)],
                          [(0,0.707,0.707),(0,-0.707,0.707),(0,-0.707,-0.707),(0,0.707,-0.707)]]:
                for d in lobes:
                    self._lobe(sq, pos, d, 1.4, 0.36, self.COLOR_T2G)
        elif n == 4 and False:  # 평면사각형 D4h (future: detect square planar)
            pass  # placeholder for Pt²⁺, Pd²⁺ etc.
        else:
            # 배위수 불명: 5 d 오비탈 단순 표시
            for d in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
                self._lobe(sq, pos, d, 1.3, 0.36, self.COLOR_T2G)

    # ------------------------------------------------------------------
    # f 오비탈 렌더링 (란타나이드/악티나이드)
    # ------------------------------------------------------------------
    def _render_f(self, sq, pos):
        """f 오비탈: 8 cubic lobes (±x±y±z 방향) — 간략화 표현.
        실제 f 오비탈은 7가지 유형(fz3, fxz2, fyz2, fxyz, fz(x2-y2), fx(x2-3y2), fy(3x2-y2))이며,
        ORCA에서 NBO 분석으로 각 유형별 점유수 확인 가능.
        """
        cubic_dirs = [
            (0.577, 0.577, 0.577), (0.577, 0.577,-0.577),
            (0.577,-0.577, 0.577), (0.577,-0.577,-0.577),
            (-0.577, 0.577, 0.577),(-0.577, 0.577,-0.577),
            (-0.577,-0.577, 0.577),(-0.577,-0.577,-0.577),
        ]
        for i, d in enumerate(cubic_dirs):
            c = self.COLOR_F_A if i%2==0 else self.COLOR_F_B
            self._lobe(sq, pos, d, 1.2, 0.32, c)

    # ------------------------------------------------------------------
    # OpenGL 기본 드로잉 유틸리티
    # ------------------------------------------------------------------
    def _lobe(self, sq, pos, direction, scale_z: float, radius: float, color: tuple):
        """단일 오비탈 로브를 prolate spheroid로 그립니다.

        Args:
            scale_z: Z 방향 늘림 배율 (p 오비탈: 2.2, d 로브: 1.4 등)
            radius:  구 기본 반지름 (Å)
        """
        nx, ny, nz = direction
        x, y, z = pos
        # 로브 중심 = 원자 위치 + 방향 × (radius × scale_z × 0.5)
        cx = x + nx * radius * scale_z * 0.5
        cy = y + ny * radius * scale_z * 0.5
        cz = z + nz * radius * scale_z * 0.5

        dot = max(-1.0, min(1.0, nz))
        angle_deg = math.degrees(math.acos(dot))
        # [BUG-O1 수정] Z × N = (-ny, nx, 0) — AdvancedOrbitalRenderer._lobe
        rx, ry = -ny, nx
        r, g, b, a = color

        glPushMatrix()
        glTranslatef(cx, cy, cz)
        if angle_deg > 0.5:
            al = math.sqrt(rx*rx + ry*ry)
            if al > 1e-6:
                glRotatef(angle_deg, rx/al, ry/al, 0.0)
        glScalef(0.55, 0.55, scale_z)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        # [FIX-ORBITAL-COLOR] AdvancedOrbitalRenderer._lobe 색상 직접 설정
        glColor4f(r, g, b, a)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.3, 0.4, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
        gluSphere(sq, radius, 18, 12)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glPopMatrix()

    def _torus(self, sq, pos, major_r: float, minor_r: float):
        """dz² 오비탈의 도넛(ring) — 소구 12개로 근사."""
        x, y, z = pos
        r, g, b, a = self.COLOR_EG
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        # [FIX-ORBITAL-COLOR] _torus dz² 색상 직접 설정
        glColor4f(r, g, b, a)
        for i in range(12):
            angle = 2 * math.pi * i / 12
            tx = x + major_r * math.cos(angle)
            ty = y + major_r * math.sin(angle)
            glPushMatrix()
            glTranslatef(tx, ty, z)
            gluSphere(sq, minor_r, 8, 6)
            glPopMatrix()
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)

    @staticmethod
    def _perp(v):
        """벡터에 수직인 단위 벡터 (Gram-Schmidt)."""
        vx, vy, vz = v
        px, py, pz = (0.0, 1.0, 0.0) if abs(vx) > 0.9 else (1.0, 0.0, 0.0)
        dot = px*vx + py*vy + pz*vz
        px -= dot*vx; py -= dot*vy; pz -= dot*vz
        l = math.sqrt(px*px + py*py + pz*pz)
        return (px/l, py/l, pz/l)

    @staticmethod
    def _cross3(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

    def cleanup(self):
        self.qm.cleanup()


# ============================================================
# Section 8: QPainter 2.5D Fallback
# ============================================================

class FallbackRenderer2D(QWidget):
    """QPainter 2.5D 분자 뷰어 (PyOpenGL 없을 때)"""

    def __init__(self, mol_data: Molecule3DData, parent=None):
        super().__init__(parent)
        self.mol_data = mol_data
        self.setMinimumSize(400, 400)
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._mouse_last = None
        self._right_last = None
        self.render_mode = "ball_and_stick"
        self._transformed = []
        self._update_transform()

    def set_mol_data(self, md):
        self.mol_data = md
        self._update_transform()
        self.update()

    def _update_transform(self):
        if not self.mol_data or not self.mol_data.atom_positions:
            self._transformed = []
            return
        cx, cy, cz = self.mol_data.get_center()
        crx, srx = math.cos(math.radians(self.rotation_x)), math.sin(math.radians(self.rotation_x))
        cry, sry = math.cos(math.radians(self.rotation_y)), math.sin(math.radians(self.rotation_y))
        self._transformed = []
        for key, (x, y, z) in self.mol_data.atom_positions.items():
            dx, dy, dz = x-cx, y-cy, z-cz
            rx = dx*cry + dz*sry
            rz = -dx*sry + dz*cry
            ry = dy*crx - rz*srx
            rz2 = dy*srx + rz*crx
            self._transformed.append((key, rx, ry, rz2))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(30, 30, 30))
        if not self._transformed:
            p.setPen(QColor(180, 180, 180))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No molecule data")
            p.end()
            return
        w, h = self.width(), self.height()
        ox, oy = w/2 + self.pan_x, h/2 + self.pan_y
        bs = self.mol_data.get_bounding_size()
        scale = min(w, h) / (bs + 4.0) * 0.35 * self.zoom_scale
        sorted_a = sorted(self._transformed, key=lambda t: t[3])
        zvals = [t[3] for t in sorted_a]
        zmin, zmax = min(zvals), max(zvals)
        zr = (zmax - zmin) if zmax > zmin else 1.0
        spos = {}
        for key, rx, ry, rz in self._transformed:
            sx, sy = ox + rx*scale, oy + ry*scale
            df = 0.7 + 0.6 * ((rz - zmin) / zr)
            spos[key] = (sx, sy, df)
        # Bonds
        for (k1, k2), order in self.mol_data.bonds.items():
            if k1 in spos and k2 in spos:
                s1, s2 = spos[k1], spos[k2]
                avg = (s1[2] + s2[2]) / 2
                g = int(100 * avg)
                bw = max(1, int(2.5 * avg))
                p.setPen(QPen(QColor(g, g, g), bw))
                p.drawLine(int(s1[0]), int(s1[1]), int(s2[0]), int(s2[1]))
        # Atoms
        for key, rx, ry, rz in sorted_a:
            sym = self.mol_data.atom_symbols.get(key, "C")
            sx, sy, df = spos[key]
            if self.render_mode == "space_filling":
                rad = get_vdw_radius(sym) * scale * 0.4 * df
            else:
                rad = get_covalent_radius(sym) * scale * 0.5 * df
            rad = max(3, rad)
            r, g, b = get_cpk_color(sym)
            bc = QColor(int(r*255), int(g*255), int(b*255))
            grad = QRadialGradient(sx - rad*0.3, sy - rad*0.3, rad*1.2)
            grad.setColorAt(0.0, bc.lighter(180))
            grad.setColorAt(0.5, bc)
            grad.setColorAt(1.0, bc.darker(200))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(sx, sy), rad, rad)
            if self.render_mode == "ball_and_stick" and sym not in ("C", "H") and rad > 8:
                p.setPen(QColor(255, 255, 255))
                p.setFont(QFont("Arial", max(7, int(rad*0.6))))
                p.drawText(int(sx-rad*0.4), int(sy+rad*0.2), sym)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._mouse_last = (e.position().x(), e.position().y())
        elif e.button() == Qt.MouseButton.RightButton:
            self._right_last = (e.position().x(), e.position().y())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._mouse_last = None
        elif e.button() == Qt.MouseButton.RightButton:
            self._right_last = None

    def mouseMoveEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if self._mouse_last:
            self.rotation_y += (x - self._mouse_last[0]) * 0.5
            self.rotation_x += (y - self._mouse_last[1]) * 0.5
            self._mouse_last = (x, y)
            self._update_transform()
            self.update()
        if self._right_last:
            self.pan_x += x - self._right_last[0]
            self.pan_y += y - self._right_last[1]
            self._right_last = (x, y)
            self.update()

    def wheelEvent(self, e):
        self.zoom_scale *= 1.1 if e.angleDelta().y() > 0 else (1/1.1)
        self.zoom_scale = max(0.1, min(10.0, self.zoom_scale))
        self.update()

    def reset_view(self):
        self.rotation_x = self.rotation_y = self.pan_x = self.pan_y = 0.0
        self.zoom_scale = 1.0
        self._update_transform()
        self.update()


# ============================================================
# Section 9: OpenGL 3D Viewer
# ============================================================

class Molecule3DViewer(QOpenGLWidget):
    """OpenGL 3D 뷰어. 진동 모드 애니메이션, 측정 도구 포함."""

    atom_clicked = pyqtSignal(object)  # key of clicked atom

    def __init__(self, mol_data: Molecule3DData = None, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)

        self.mol_data = mol_data
        self.render_mode = "ball_and_stick"
        self._bs = BallAndStickRenderer()
        self._sf = SpaceFillingRenderer()
        self._pi = PiOrbitalRenderer()            # [CHEM-6] π 오비탈
        self._adv = AdvancedOrbitalRenderer()     # [CHEM-8] 고차원 오비탈
        self.orbital_mode = 'none'                # 'none'|'pi'|'hybrid'|'d_orbital'|'f_orbital'|'all'
        self.show_pi_orbitals = False             # 하위호환

        # Camera
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._center = (0.0, 0.0, 0.0)
        self._view_scale = 1.0

        # Mouse
        self._ml = None
        self._mr = None

        # Vibration animation
        self.vib_vectors = None   # List[(dx,dy,dz)] per atom
        self.vib_scale = 0.0      # current phase
        self._vib_timer = QTimer(self)
        self._vib_timer.timeout.connect(self._vib_tick)
        self._vib_phase = 0.0
        self._vib_amplitude = 1.5
        self._vib_active = False

        # Measurement
        self._selected_atoms = []  # list of keys for measurement
        self._measure_mode = False

        self.setMinimumSize(400, 400)
        if self.mol_data:
            self._recalc()

    def set_mol_data(self, md):
        self.mol_data = md
        self._recalc()
        self.update()

    def _recalc(self):
        if not self.mol_data or not self.mol_data.atom_positions:
            return
        self._center = self.mol_data.get_center()
        bs = self.mol_data.get_bounding_size()
        self._view_scale = 15.0 / (bs + 1.0)

    def start_vibration(self, vectors, amplitude=1.5):
        """Start vibration mode animation"""
        self.vib_vectors = vectors
        self._vib_amplitude = amplitude
        self._vib_phase = 0.0
        self._vib_active = True
        self._vib_timer.start(30)  # ~33 fps

    def stop_vibration(self):
        self._vib_active = False
        self._vib_timer.stop()
        self.vib_vectors = None
        self.vib_scale = 0.0
        self.update()

    def _vib_tick(self):
        self._vib_phase += 0.1
        self.vib_scale = math.sin(self._vib_phase) * self._vib_amplitude
        self.update()

    def set_measure_mode(self, on: bool):
        self._measure_mode = on
        self._selected_atoms = []

    def initializeGL(self):
        if not OPENGL_AVAILABLE:
            return
        glClearColor(0.12, 0.12, 0.12, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_NORMALIZE)
        glLightfv(GL_LIGHT0, GL_POSITION, [2.0, 3.0, 3.0, 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.15, 0.15, 0.15, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.85, 0.85, 0.85, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT1, GL_POSITION, [-2.0, -1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.3, 0.3, 0.35, 1.0])

    def resizeGL(self, w, h):
        if not OPENGL_AVAILABLE:
            return
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w/h, 0.1, 200.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        if not OPENGL_AVAILABLE:
            return
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.pan_x, self.pan_y, -50.0)
        s = self._view_scale * self.zoom_scale
        glScalef(s, s, s)
        glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
        glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
        cx, cy, cz = self._center
        glTranslatef(-cx, -cy, -cz)

        if self.mol_data:
            vv = self.vib_vectors if self._vib_active else None
            vs = self.vib_scale if self._vib_active else 0.0
            small = (self.orbital_mode != 'none')
            if self.render_mode == "ball_and_stick":
                self._bs.render(self.mol_data, vv, vs, small_atoms=small)
            else:
                self._sf.render(self.mol_data, vv, vs)
            # 오비탈 렌더링 (모드에 따라 분기)
            if self.orbital_mode == 'pi':
                self._pi.render(self.mol_data)
            elif self.orbital_mode in ('hybrid', 'd_orbital', 'f_orbital', 'all'):
                self._adv.render(self.mol_data, orbital_mode=self.orbital_mode)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._ml = (e.position().x(), e.position().y())
        elif e.button() == Qt.MouseButton.RightButton:
            self._mr = (e.position().x(), e.position().y())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._ml = None
        elif e.button() == Qt.MouseButton.RightButton:
            self._mr = None

    def mouseMoveEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if self._ml:
            self.rotation_y += (x - self._ml[0]) * 0.5
            self.rotation_x += (y - self._ml[1]) * 0.5
            self._ml = (x, y)
            self.update()
        if self._mr:
            self.pan_x += (x - self._mr[0]) * 0.05
            self.pan_y -= (y - self._mr[1]) * 0.05
            self._mr = (x, y)
            self.update()

    def wheelEvent(self, e):
        self.zoom_scale *= 1.1 if e.angleDelta().y() > 0 else (1/1.1)
        self.zoom_scale = max(0.1, min(10.0, self.zoom_scale))
        self.update()

    def reset_view(self):
        self.rotation_x = self.rotation_y = 0.0
        self.zoom_scale = 1.0
        self.pan_x = self.pan_y = 0.0
        self._recalc()
        self.update()

    def set_pi_orbitals(self, on: bool):
        """[CHEM-6] 하위호환 π 오비탈 토글."""
        self.set_orbital_mode('pi' if on else 'none')

    def set_orbital_mode(self, mode: str):
        """[CHEM-8] 오비탈 표시 모드 설정.
        mode: 'none'|'pi'|'hybrid'|'d_orbital'|'f_orbital'|'all'
        """
        self.orbital_mode = mode
        self.show_pi_orbitals = (mode == 'pi')
        self.update()

    def cleanup(self):
        self._bs.cleanup()
        self._sf.cleanup()
        self._pi.cleanup()
        self._adv.cleanup()


# ============================================================
# Section 10: Tab Panels
# ============================================================

class PropertiesPanel(QWidget):
    """📊 속성 탭 — RDKit 계산값 + PubChem DB"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Calculated properties
        self.calc_group = QGroupBox("🔬 계산값 (RDKit)")
        self.calc_form = QFormLayout()
        self.calc_group.setLayout(self.calc_form)
        layout.addWidget(self.calc_group)

        # PubChem properties
        self.pub_group = QGroupBox("🌐 PubChem DB")
        self.pub_form = QFormLayout()
        self.pub_group.setLayout(self.pub_form)
        layout.addWidget(self.pub_group)

        # ORCA properties
        self.orca_group = QGroupBox("⚛️ DFT 결과 (ORCA)")
        self.orca_form = QFormLayout()
        self.orca_group.setLayout(self.orca_form)
        layout.addWidget(self.orca_group)

        # Bond measurements
        self.meas_group = QGroupBox("📏 결합 측정")
        self.meas_layout = QVBoxLayout()
        self.meas_text = QTextEdit()
        self.meas_text.setReadOnly(True)
        self.meas_text.setMaximumHeight(120)
        self.meas_layout.addWidget(self.meas_text)
        self.meas_group.setLayout(self.meas_layout)
        layout.addWidget(self.meas_group)

        layout.addStretch()
        self.setLayout(layout)

    def update_rdkit(self, smiles: str):
        """RDKit 계산값 업데이트 — v4: 독립적 try/except 오류 핸들링"""
        # Clear
        while self.calc_form.rowCount() > 0:
            self.calc_form.removeRow(0)

        if not RDKIT_AVAILABLE:
            self.calc_form.addRow("상태:", QLabel("RDKit 미설치"))
            return
        if not smiles:
            self.calc_form.addRow("상태:", QLabel("SMILES 없음"))
            return

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                self.calc_form.addRow("오류:", QLabel("SMILES 파싱 실패"))
                return

            self.calc_form.addRow("SMILES:", QLabel(smiles))
            try:
                self.calc_form.addRow("분자식:", QLabel(rdMolDescriptors.CalcMolFormula(mol)))
            except Exception:
                self.calc_form.addRow("분자식:", QLabel("계산 실패"))
            try:
                self.calc_form.addRow("분자량:", QLabel(f"{Descriptors.MolWt(mol):.2f} g/mol"))
            except Exception:
                self.calc_form.addRow("분자량:", QLabel("계산 실패"))
            try:
                self.calc_form.addRow("정확 질량:", QLabel(f"{Descriptors.ExactMolWt(mol):.4f}"))
            except Exception:
                pass
            try:
                self.calc_form.addRow("LogP:", QLabel(f"{Descriptors.MolLogP(mol):.2f}"))
            except Exception:
                pass
            try:
                self.calc_form.addRow("TPSA:", QLabel(f"{Descriptors.TPSA(mol):.1f} Å²"))
            except Exception:
                pass
            try:
                self.calc_form.addRow("H-Bond Donor:", QLabel(str(Descriptors.NumHDonors(mol))))
                self.calc_form.addRow("H-Bond Acceptor:", QLabel(str(Descriptors.NumHAcceptors(mol))))
            except Exception:
                pass
            try:
                self.calc_form.addRow("회전 가능 결합:", QLabel(str(Descriptors.NumRotatableBonds(mol))))
            except Exception:
                pass
            try:
                self.calc_form.addRow("고리 수:", QLabel(str(rdMolDescriptors.CalcNumRings(mol))))
                self.calc_form.addRow("방향족 고리:", QLabel(str(rdMolDescriptors.CalcNumAromaticRings(mol))))
            except Exception:
                pass
        except Exception as e:
            self.calc_form.addRow("RDKit 오류:", QLabel(f"{str(e)[:60]}"))

    def update_pubchem(self, data: Dict, smiles: str = ""):
        """PubChem 결과 업데이트 — v4: 독립적 try/except 오류 핸들링
        smiles: 분자의 SMILES 코드 (표시용)"""
        while self.pub_form.rowCount() > 0:
            self.pub_form.removeRow(0)

        if not data:
            self.pub_form.addRow("상태:", QLabel("오프라인 — PubChem 조회 불가"))
            # 오프라인 시에도 SMILES 표시
            if smiles:
                smiles_lbl = QLabel(smiles)
                smiles_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                smiles_lbl.setWordWrap(True)
                smiles_lbl.setStyleSheet("font-family: monospace; color: #64B5F6;")
                self.pub_form.addRow("SMILES:", smiles_lbl)
            return

        try:
            self.pub_form.addRow("IUPAC:", QLabel(str(data.get("iupac_name", "N/A"))))
            if data.get("cas_number"):
                self.pub_form.addRow("CAS:", QLabel(data["cas_number"]))
            if data.get("synonyms"):
                syns = ", ".join(data["synonyms"][:5])
                lbl = QLabel(syns)
                lbl.setWordWrap(True)
                self.pub_form.addRow("관용명:", lbl)
            # [신규] SMILES 코드 표시 (클립보드 복사 가능)
            smiles_val = smiles or ""
            if smiles_val:
                smiles_lbl = QLabel(smiles_val)
                smiles_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                smiles_lbl.setWordWrap(True)
                smiles_lbl.setStyleSheet("font-family: monospace; color: #64B5F6;")
                self.pub_form.addRow("SMILES:", smiles_lbl)
            self.pub_form.addRow("CID:", QLabel(str(data.get("cid", "N/A"))))
            self.pub_form.addRow("출처:", QLabel("★★★★★ PubChem DB"))
        except Exception as e:
            self.pub_form.addRow("PubChem 오류:", QLabel(f"{str(e)[:60]}"))

    def update_orca(self, parser: OrcaOutputParser):
        """ORCA 결과 업데이트 — v4: 독립적 try/except 오류 핸들링"""
        while self.orca_form.rowCount() > 0:
            self.orca_form.removeRow(0)

        if not parser or not parser.text:
            self.orca_form.addRow("상태:", QLabel("ORCA 결과 없음 — 📂 버튼으로 .out 파일 로드"))
            return

        try:
            if parser.total_energy is not None:
                self.orca_form.addRow("에너지:", QLabel(f"{parser.total_energy:.8f} Hartree"))
                ev = parser.total_energy * 27.2114
                self.orca_form.addRow("", QLabel(f"({ev:.4f} eV)"))
            if parser.dipole_moment is not None:
                self.orca_form.addRow("쌍극자:", QLabel(f"{parser.dipole_moment:.4f} Debye"))
            self.orca_form.addRow("수렴:", QLabel("✅ 정상 종료" if parser.converged else "⚠️ 미수렴"))
            self.orca_form.addRow("원자 수:", QLabel(str(len(parser.atoms))))
            self.orca_form.addRow("진동 모드:", QLabel(str(len(parser.frequencies))))
        except Exception as e:
            self.orca_form.addRow("DFT 오류:", QLabel(f"{str(e)[:60]}"))

    def update_measurements(self, mol_data: Molecule3DData):
        """결합 길이/각도 자동 계산 — v4: 예외 안전"""
        try:
            lines = []
            for (k1, k2), order in mol_data.bonds.items():
                dist = mol_data.get_bond_length(k1, k2)
                if dist is not None:
                    s1 = mol_data.atom_symbols.get(k1, "?")
                    s2 = mol_data.atom_symbols.get(k2, "?")
                    bo_str = {1: "-", 2: "=", 3: "≡"}.get(order if isinstance(order, int) else 1, "-")
                    lines.append(f"{s1}{bo_str}{s2}: {dist:.2f} Å")
            self.meas_text.setPlainText("\n".join(lines[:30]))  # Top 30
        except Exception as e:
            self.meas_text.setPlainText(f"측정 오류: {e}")


# ============================================================
# [SPEC-1] SMILES 기반 예측 스펙트럼 생성기 (ORCA 불필요)
# ============================================================

def predict_spectrum_from_smiles(smiles: str, spec_type: str = "IR"):
    """SMILES에서 RDKit 작용기 분석 기반 예측 스펙트럼 생성.

    spec_type: 'IR' | 'Raman' | 'NMR' | 'UV-Vis' | 'MS'
    Returns: (frequencies_or_shifts, intensities) 또는 ([], [])
    """
    if not RDKIT_AVAILABLE or not smiles:
        return [], []
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return [], []

        freqs, ints = [], []

        if spec_type in ("IR", "Raman"):
            mol_h = Chem.AddHs(mol)
            # 원자 조성 및 혼성화 분석
            HYB = Chem.rdchem.HybridizationType
            n_C_sp3 = sum(1 for a in mol.GetAtoms()
                         if a.GetAtomicNum() == 6 and a.GetHybridization() == HYB.SP3)
            n_C_sp2 = sum(1 for a in mol.GetAtoms()
                         if a.GetAtomicNum() == 6 and a.GetHybridization() == HYB.SP2)
            n_C_sp = sum(1 for a in mol.GetAtoms()
                        if a.GetAtomicNum() == 6 and a.GetHybridization() == HYB.SP)
            n_O = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 8)
            n_N = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 7)
            n_S = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 16)
            n_H = sum(1 for a in mol_h.GetAtoms() if a.GetAtomicNum() == 1)
            n_OH = sum(1 for a in mol.GetAtoms()
                      if a.GetAtomicNum() == 8 and a.GetTotalNumHs() > 0)
            n_NH = sum(1 for a in mol.GetAtoms()
                      if a.GetAtomicNum() == 7 and a.GetTotalNumHs() > 0)
            # 방향족 고리
            n_ar_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
            # 이중결합 C=O 검출
            n_CO_double = sum(1 for b in mol.GetBonds()
                             if b.GetBondTypeAsDouble() == 2.0 and
                             {b.GetBeginAtom().GetAtomicNum(),
                              b.GetEndAtom().GetAtomicNum()} == {6, 8})
            n_CN_double = sum(1 for b in mol.GetBonds()
                             if b.GetBondTypeAsDouble() == 2.0 and
                             {b.GetBeginAtom().GetAtomicNum(),
                              b.GetEndAtom().GetAtomicNum()} == {6, 7})
            n_CC_double = sum(1 for b in mol.GetBonds()
                             if b.GetBondTypeAsDouble() == 2.0 and
                             b.GetBeginAtom().GetAtomicNum() == 6 and
                             b.GetEndAtom().GetAtomicNum() == 6)
            n_triple = sum(1 for b in mol.GetBonds()
                          if b.GetBondTypeAsDouble() == 3.0)

            # IR 규칙 테이블: (주파수, 강도, 조건)
            rules_ir = [
                (3400,  n_OH * 80,  n_OH > 0,   "O-H stretch (broad)"),
                (3320,  n_NH * 50,  n_NH > 0,   "N-H stretch"),
                (3060,  n_ar_rings * 30, n_ar_rings > 0, "Ar C-H stretch"),
                (2960,  n_C_sp3 * 25, n_C_sp3 > 0, "C-H sp3 asym"),
                (2870,  n_C_sp3 * 15, n_C_sp3 > 0, "C-H sp3 sym"),
                (3010,  n_C_sp2 * 12, n_C_sp2 > 0, "C-H sp2"),
                (2100,  n_triple * 40, n_triple > 0, "C≡C stretch"),
                (1725,  n_CO_double * 100, n_CO_double > 0, "C=O stretch"),
                (1650,  n_CC_double * 60, n_CC_double > 0, "C=C stretch"),
                (1620,  n_CN_double * 50, n_CN_double > 0, "C=N stretch"),
                (1600,  n_ar_rings * 40, n_ar_rings > 0, "Ar C=C"),
                (1480,  n_ar_rings * 30, n_ar_rings > 0, "Ar C=C (2nd)"),
                (1460,  n_C_sp3 * 20, n_C_sp3 > 0, "CH2/CH3 bend"),
                (1375,  n_C_sp3 * 10, n_C_sp3 > 0, "CH3 sym bend"),
                (1260,  n_O * 30,  n_O > 0,    "C-O stretch"),
                (1000,  n_C_sp2 * 15, n_C_sp2 > 0, "=C-H oop"),
                (700,   n_ar_rings * 35, n_ar_rings > 0, "Ar C-H oop"),
            ]
            # Raman 강도는 IR과 역 관계 (비극성 진동이 강)
            raman_factor = 0.4 if spec_type == "Raman" else 1.0
            raman_bonus = {2960: 2.0, 2870: 2.5, 2100: 3.0,
                          1650: 1.5, 700: 1.2}

            for freq, raw_inten, cond, _ in rules_ir:
                if cond and raw_inten > 0:
                    if spec_type == "Raman":
                        factor = raman_factor * raman_bonus.get(freq, 1.0)
                    else:
                        factor = 1.0
                    freqs.append(float(freq))
                    ints.append(float(raw_inten * factor))

        elif spec_type in ("NMR", "NMR_H"):
            # ¹H NMR 화학적 이동 예측 (간이 규칙 기반)
            mol_h = Chem.AddHs(mol)
            HYB = Chem.rdchem.HybridizationType
            for atom in mol_h.GetAtoms():
                if atom.GetAtomicNum() != 1:
                    continue
                heavy = [n for n in atom.GetNeighbors() if n.GetAtomicNum() != 1]
                if not heavy:
                    continue
                c = heavy[0]
                hyb = c.GetHybridization()
                an = c.GetAtomicNum()
                # 화학적 이동 추정 (Shoolery 규칙 근사)
                if an == 8:                          shift = 4.5  # OH (가변적)
                elif an == 7:                        shift = 8.0  # NH
                elif an == 6 and c.GetIsAromatic():  shift = 7.3  # Ar-H
                elif an == 6 and hyb == HYB.SP2:     shift = 5.8  # =C-H
                elif an == 6 and hyb == HYB.SP:      shift = 2.5  # ≡C-H
                elif an == 6:
                    # sp3 C — 주변 전기음성도 원자 영향 (Shoolery substituent constants)
                    hetero_nb = sum(1 for nb in c.GetNeighbors()
                                   if nb.GetAtomicNum() in (7, 8, 16, 17, 35))
                    shift = 0.9 + hetero_nb * 1.5  # ~0.9 (알킬) ~ 4.5 (O 인접)
                    shift = min(shift, 4.5)
                else:
                    shift = 1.0
                freqs.append(round(shift, 2))
                ints.append(1.0)

        elif spec_type == "NMR_C13":
            # ¹³C NMR 화학적 이동 예측 (간이 규칙)
            HYB = Chem.rdchem.HybridizationType
            for atom in mol.GetAtoms():
                an = atom.GetAtomicNum()
                if an != 6:
                    continue
                hyb = atom.GetHybridization()
                is_ar = atom.GetIsAromatic()
                neighbors_an = [n.GetAtomicNum() for n in atom.GetNeighbors()]
                # 13C 화학적 이동 추정
                if is_ar:
                    # 방향족 — 치환기 영향 고려
                    hetero_adj = sum(1 for n_an in neighbors_an if n_an in (7, 8))
                    shift = 128.0 + hetero_adj * 10  # 128~150 ppm
                elif HYB.SP2 == hyb:
                    # C=O 검출
                    double_o = any(
                        b.GetBondTypeAsDouble() == 2.0 and
                        (b.GetBeginAtom().GetAtomicNum() == 8 or
                         b.GetEndAtom().GetAtomicNum() == 8)
                        for b in atom.GetBonds()
                    )
                    if double_o:
                        # C=O 유형별 구분
                        o_adj = sum(1 for n_an in neighbors_an if n_an == 8)
                        shift = 170.0 if o_adj >= 2 else 200.0  # ester vs ketone/aldehyde
                    else:
                        shift = 125.0  # C=C
                elif HYB.SP == hyb:
                    shift = 80.0  # ≡C
                else:
                    # sp3 C — 전기음성도 치환기 영향
                    o_adj = sum(1 for n_an in neighbors_an if n_an == 8)
                    n_adj = sum(1 for n_an in neighbors_an if n_an == 7)
                    shift = 20.0 + o_adj * 40.0 + n_adj * 25.0
                    shift = min(shift, 85.0)
                # 랜덤 스프레드 (같은 ppm 겹침 방지)
                import random
                shift += random.uniform(-0.5, 0.5)
                freqs.append(round(shift, 1))
                ints.append(1.0)

        elif spec_type == "UV-Vis":
            # UV-Vis 흡수파장 예측: 공액 π 시스템 검출
            n_ar = rdMolDescriptors.CalcNumAromaticRings(mol)
            n_db = sum(1 for b in mol.GetBonds()
                      if b.GetBondTypeAsDouble() == 2.0 and
                      b.GetBeginAtom().GetAtomicNum() == 6 and
                      b.GetEndAtom().GetAtomicNum() == 6)
            n_azo = sum(1 for b in mol.GetBonds()
                       if b.GetBondTypeAsDouble() == 2.0 and
                       b.GetBeginAtom().GetAtomicNum() == 7 and
                       b.GetEndAtom().GetAtomicNum() == 7)
            n_nitro = sum(1 for a in mol.GetAtoms()
                         if a.GetAtomicNum() == 7 and
                         sum(1 for n in a.GetNeighbors() if n.GetAtomicNum() == 8) >= 2)
            n_carbonyl = sum(1 for b in mol.GetBonds()
                            if b.GetBondTypeAsDouble() == 2.0 and
                            {b.GetBeginAtom().GetAtomicNum(),
                             b.GetEndAtom().GetAtomicNum()} == {6, 8})

            # Woodward–Fieser 규칙 근사
            lam_base = 217  # 기본 단위 (nm)
            if n_ar >= 1:
                lam_base = 254
                freqs.append(float(lam_base))
                ints.append(15000.0)
                if n_ar >= 2:
                    freqs.append(float(lam_base + 30 * (n_ar - 1)))
                    ints.append(25000.0)
            if n_db >= 2 and n_ar == 0:
                shift = 217 + (n_db - 2) * 30
                freqs.append(float(shift))
                ints.append(float(n_db * 8000))
            if n_carbonyl > 0 and n_ar == 0:
                freqs.append(270.0)  # n→π* 전이
                ints.append(50.0)
            if n_azo > 0:
                freqs.append(340.0)
                ints.append(5000.0)
            if n_nitro > 0:
                freqs.append(380.0)
                ints.append(12000.0)
            if not freqs:
                freqs.append(200.0)
                ints.append(100.0)

        elif spec_type == "MS":
            # 질량 스펙트럼: M⁺ 및 주요 단편화 예측
            mw = Descriptors.ExactMolWt(mol)
            freqs.append(round(mw, 2))  # M⁺
            ints.append(100.0)
            # M-1 (수소 손실)
            freqs.append(round(mw - 1, 2))
            ints.append(20.0)
            # M-OH, M-CH3 등
            n_OH = sum(1 for a in mol.GetAtoms()
                      if a.GetAtomicNum() == 8 and a.GetTotalNumHs() > 0)
            if n_OH > 0:
                freqs.append(round(mw - 17, 2))  # M-OH
                ints.append(40.0)
            n_CH3 = sum(1 for a in mol.GetAtoms()
                       if a.GetAtomicNum() == 6 and a.GetTotalNumHs() >= 3)
            if n_CH3 > 0:
                freqs.append(round(mw - 15, 2))  # M-CH3
                ints.append(30.0)
            # m/z=77 (페닐 양이온)
            n_ar = rdMolDescriptors.CalcNumAromaticRings(mol)
            if n_ar > 0 and mw > 80:
                freqs.append(77.0)
                ints.append(35.0)

        return freqs, ints
    except Exception as e:
        logger.warning(f"predict_spectrum_from_smiles({spec_type}) failed: {e}")
        return [], []


class SpectrumPanel(QWidget):
    """📈 스펙트럼 탭 — IR/Raman/NMR/UV-Vis/MS 예측 스펙트럼 + ORCA 정밀 스펙트럼 + AI 피크 분석"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # AI 오버레이 상태 관리
        self.ai_annotations = []        # matplotlib annotation 객체 리스트
        self.ai_overlay_visible = False  # 오버레이 표시 여부
        self.ai_analysis_data = None     # AI 분석 결과 캐시
        # 스펙트럼 데이터 (plot_ir에서 저장)
        self.frequencies = []
        self.intensities = []
        self.plot_x = None    # Lorentzian 브로드닝 후 x 배열
        self.plot_y = None    # Lorentzian 브로드닝 후 y 배열
        self.ax = None        # matplotlib Axes 객체
        self._gemini = GeminiAnalyzer()  # AI 분석용
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        if not MATPLOTLIB_AVAILABLE:
            layout.addWidget(QLabel("matplotlib 미설치 — 스펙트럼 표시 불가"))
            self.setLayout(layout)
            return

        # ── [SPEC-2] 5가지 분광 유형 선택 버튼 + PDF 내보내기 ──────────
        self._spec_type = "IR"   # 현재 선택된 스펙트럼 유형
        self._smiles_cache = ""  # 예측용 SMILES 캐시

        top_bar = QHBoxLayout()
        top_bar.setSpacing(4)

        spec_buttons = [
            ("📡 IR",       "IR",      "#1565C0"),
            ("🔴 Raman",    "Raman",   "#880E4F"),
            ("⚛ ¹H NMR",   "NMR_H",   "#1B5E20"),
            ("¹³C NMR",    "NMR_C13", "#2E7D32"),
            ("🌈 UV-Vis",   "UV-Vis",  "#E65100"),
        ]
        self._spec_btns: Dict[str, QPushButton] = {}
        for label, stype, color in spec_buttons:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(stype == "IR")
            btn.setFixedHeight(26)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:#2a2a2a; border:1px solid #555;
                    color:#ccc; padding:2px 8px; border-radius:3px; font-size:9pt;
                }}
                QPushButton:checked {{
                    background:{color}; border-color:{color}; color:white;
                }}
                QPushButton:hover {{ background:#3a3a3a; }}
            """)
            btn.clicked.connect(lambda checked, t=stype: self._on_spec_type_changed(t))
            top_bar.addWidget(btn)
            self._spec_btns[stype] = btn

        top_bar.addStretch()

        # [SPEC-4] PDF 내보내기 버튼
        self.btn_pdf = QPushButton("📄 PDF 저장")
        self.btn_pdf.setFixedHeight(26)
        self.btn_pdf.setStyleSheet("""
            QPushButton {
                background:#1B5E20; border:1px solid #43A047;
                color:#A5D6A7; padding:2px 10px; border-radius:3px; font-size:9pt;
            }
            QPushButton:hover { background:#2E7D32; }
        """)
        self.btn_pdf.clicked.connect(self._export_pdf)
        top_bar.addWidget(self.btn_pdf)

        layout.addLayout(top_bar)

        # ── matplotlib 캔버스 ──
        self.figure = Figure(figsize=(8, 3), dpi=100)
        self.figure.patch.set_facecolor("#1e1e1e")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, 1)

        self.info_label = QLabel("분자 로드 시 예측 스펙트럼 표시 | ORCA .out 파일 로드 시 정밀 스펙트럼")
        self.info_label.setStyleSheet("color: #888; font-size: 8pt;")
        layout.addWidget(self.info_label)

        # ── 하단 버튼 바: AI 분석 + 진동모드 버튼 ──
        bot_bar = QHBoxLayout()
        bot_bar.setSpacing(4)
        self.btn_ai_overlay = QPushButton("🤖 AI 피크 분석")
        self.btn_ai_overlay.setCheckable(True)
        self.btn_ai_overlay.setChecked(False)
        self.btn_ai_overlay.setFixedHeight(26)
        self.btn_ai_overlay.setStyleSheet("""
            QPushButton {
                background-color:#37474F; color:#B0BEC5;
                border:1px solid #546E7A; border-radius:4px;
                padding:4px 10px; font-size:9pt;
            }
            QPushButton:checked {
                background-color:#1565C0; color:white; border:1px solid #42A5F5;
            }
            QPushButton:hover { background-color:#455A64; }
        """)
        self.btn_ai_overlay.clicked.connect(self._toggle_ai_overlay)
        bot_bar.addWidget(self.btn_ai_overlay)

        # [SPEC-3] 진동모드 연계 버튼 (스펙트럼 패널 내 배치)
        self.btn_vib_link = QPushButton("🎵 진동모드 표시")
        self.btn_vib_link.setCheckable(True)
        self.btn_vib_link.setFixedHeight(26)
        self.btn_vib_link.setStyleSheet("""
            QPushButton {
                background-color:#1A237E; color:#9FA8DA;
                border:1px solid #3F51B5; border-radius:4px;
                padding:4px 10px; font-size:9pt;
            }
            QPushButton:checked {
                background-color:#283593; color:white; border:1px solid #5C6BC0;
            }
            QPushButton:hover { background-color:#283593; }
        """)
        self.btn_vib_link.clicked.connect(self._toggle_vib_link)
        bot_bar.addWidget(self.btn_vib_link)
        bot_bar.addStretch()
        layout.addLayout(bot_bar)

        self.setLayout(layout)

    # ── [SPEC-2] 스펙트럼 유형 변경 핸들러 ──────────────────────────
    def _on_spec_type_changed(self, spec_type: str):
        """5가지 분광 유형 버튼 중 하나 선택 → 예측 스펙트럼 갱신"""
        self._spec_type = spec_type
        # 다른 버튼 해제
        for stype, btn in self._spec_btns.items():
            btn.setChecked(stype == spec_type)
        # ORCA 데이터가 있으면 IR만 ORCA 사용, 나머지는 예측
        if self._smiles_cache:
            self.load_predicted(self._smiles_cache)

    # ── [SPEC-1] SMILES 기반 예측 스펙트럼 로드 ─────────────────────
    def load_predicted(self, smiles: str):
        """SMILES 기반 예측 스펙트럼 로드 (ORCA 없을 때 호출).
        분광 유형은 현재 선택된 _spec_type 사용.
        """
        if not RDKIT_AVAILABLE or not MATPLOTLIB_AVAILABLE or not smiles:
            return
        self._smiles_cache = smiles
        spec_type = getattr(self, '_spec_type', 'IR')
        # [GUIDE.md v2] 새로운 전문 분광 그래프 렌더링으로 위임
        self._render_guide_spectrum(smiles, spec_type)
        return
        if freqs:
            self.plot_predicted(freqs, ints, spec_type, smiles)
        else:
            self.info_label.setText(f"⚠️ {spec_type} 예측 데이터 없음 (분자 구조 확인 필요)")

    def _render_guide_spectrum(self, smiles: str, spec_type: str):
        """[GUIDE.md v2] popup_predicted_spectrum의 새 그래프 함수로 스펙트럼 렌더링.
        흰 배경 + 전문 색상 + 작용기 annotation 적용.
        """
        if not MATPLOTLIB_AVAILABLE:
            return
        try:
            import sys as _sys, os as _os
            _src_dir = _os.path.dirname(_os.path.abspath(__file__))
            if _src_dir not in _sys.path:
                _sys.path.insert(0, _src_dir)
            from predict_spectra import predict_all
            from popup_predicted_spectrum import (
                _make_ir_figure, _make_raman_figure,
                _make_nmr_h1_figure, _make_nmr_c13_figure,
                _make_uvvis_figure,
            )
            spec = predict_all(smiles)
            _t = spec_type.upper().replace("-", "").replace(" ", "")
            if _t == "IR":
                new_fig = _make_ir_figure(spec.ir_peaks)
            elif _t == "RAMAN":
                new_fig = _make_raman_figure(spec.raman_peaks)
            elif _t in ("NMRH", "1HNMR", "NMR", "NMR_H"):
                new_fig = _make_nmr_h1_figure(spec.h1_nmr_peaks, spec.formula, smiles=smiles)
            elif _t in ("NMRC13", "13CNMR", "NMR_C13", "C13"):
                new_fig = _make_nmr_c13_figure(spec.c13_peaks, spec.formula, smiles=smiles)
            elif _t in ("UVVIS", "UV"):
                new_fig = _make_uvvis_figure(spec.uvvis_peaks)
            else:
                new_fig = _make_ir_figure(spec.ir_peaks)
            # FigureCanvas에 새 figure 연결 (canvas 교체)
            new_fig.set_canvas(self.canvas)
            self.canvas.figure = new_fig
            self.figure = new_fig
            self.ax = new_fig.axes[0] if new_fig.axes else None
            self.canvas.draw()
            self.info_label.setText(
                f"[GUIDE.md v2] 예측 {spec_type} 스펙트럼  |  분자: {smiles[:25]}")
        except Exception as _e:
            logger.warning(f"_render_guide_spectrum 실패: {_e} — fallback")
            # fallback: 단순 표시
            try:
                freqs, ints = predict_spectrum_from_smiles(smiles, spec_type)
                self.figure.clear()
                self.figure.patch.set_facecolor("white")
                self.ax = self.figure.add_subplot(111)
                self.ax.set_facecolor("white")
                if freqs:
                    x = np.linspace(400, 4000, 2000)
                    y = np.zeros_like(x)
                    for f, i_ in zip(freqs, ints):
                        y += i_ * (20**2 / ((x - f)**2 + 20**2))
                    y /= max(y.max(), 1.0)
                    self.ax.plot(x, y, color='#C0392B', lw=1.4)
                    self.ax.invert_xaxis()
                self.ax.set_facecolor("white")
                self.figure.patch.set_facecolor("white")
                self.figure.tight_layout()
                self.canvas.draw()
            except Exception:
                pass

    def plot_predicted(self, freqs: List[float], ints: List[float],
                       spec_type: str, smiles: str = ""):
        """예측 스펙트럼 플롯 — 분광 유형별 x축 설정"""
        if not MATPLOTLIB_AVAILABLE or not freqs:
            return

        # 데이터 저장
        self.frequencies = list(freqs)
        self.intensities = list(ints)
        self.ai_analysis_data = None
        self.ai_annotations = []
        self.ai_overlay_visible = False
        if hasattr(self, 'btn_ai_overlay'):
            self.btn_ai_overlay.setChecked(False)

        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#1e1e1e")

        if spec_type in ("IR", "Raman"):
            # Lorentzian 브로드닝
            x = np.linspace(400, 4000, 3000)
            y = np.zeros_like(x)
            gamma = 20.0
            for f, intensity in zip(freqs, ints):
                y += intensity * (gamma**2 / ((x - f)**2 + gamma**2))
            y_max = np.max(y) if np.max(y) > 0 else 1
            y_norm = y / y_max * 85.0

            if spec_type == "IR":
                # [IR-GUIDE] 전송투과율 스타일: 피크 하향, y축 반전
                y_plot = 100.0 - y_norm
                self.plot_x, self.plot_y = x, y_plot
                line_color = "#00bcd4"
                self.ax.plot(x, y_plot, color=line_color, linewidth=1.2)
                self.ax.fill_between(x, y_plot, 100, alpha=0.15, color=line_color)
                self.ax.set_ylim(108, -5)   # 반전: 100% 상단, 0% 하단
                ylabel = "Transmittance (%)"
                self.ax.axvline(x=1500, color='#888', linestyle=':', alpha=0.5, lw=0.8)
                self.ax.text(1480, 2, "← Fingerprint", ha='right', fontsize=7, color='#888')
            else:  # Raman: Intensity 스타일 (피크 상향)
                y_plot = y_norm
                self.plot_x, self.plot_y = x, y_plot
                line_color = "#e91e63"
                self.ax.plot(x, y_plot, color=line_color, linewidth=1.2)
                self.ax.fill_between(x, y_plot, alpha=0.15, color=line_color)
                self.ax.set_ylim(0, 100)
                ylabel = "Intensity (a.u.)"

            for f, intensity in zip(freqs, ints):
                if intensity > max(ints) * 0.1:
                    self.ax.axvline(x=f, color="#ff5722", alpha=0.3, linewidth=0.5)
            xlabel = "Wavenumber (cm⁻¹)"
            title = f"Predicted {spec_type} Spectrum"
            self.ax.invert_xaxis()
            self.ax.set_xlim(4000, 400)
            self.ax.set_ylabel(ylabel, color="white", fontsize=9)

        elif spec_type in ("NMR", "NMR_H"):
            # [NMR-H-GUIDE] ¹H NMR: Lorentzian + 구역 레이블 + 루이스 구조 삽입
            x = np.linspace(-1, 12, 2000)
            y = np.zeros_like(x)
            gamma = 0.05
            for f, intensity in zip(freqs, ints):
                y += intensity * (gamma**2 / ((x - f)**2 + gamma**2))
            y_max = np.max(y) if np.max(y) > 0 else 1
            y = y / y_max
            self.plot_x, self.plot_y = x, y * 100
            self.ax.plot(x, y, color="#4caf50", linewidth=1.2)
            self.ax.fill_between(x, y, alpha=0.15, color="#4caf50")
            # 구역 레이블
            for ppm, zone in [(0.9, "알킬"), (2.5, "α-CH"), (3.5, "CH-O"),
                               (5.5, "알켄"), (7.3, "방향족"), (9.5, "CHO/OH")]:
                self.ax.text(ppm, float(y_max) * 0.92, zone,
                             ha='center', fontsize=7, color='#888', rotation=70)
            # 루이스 구조 이미지 삽입 (우상단 빈 공간)
            if smiles and RDKIT_AVAILABLE:
                try:
                    from rdkit.Chem import Draw as _RDDraw
                    from io import BytesIO as _BytesIO
                    import PIL.Image as _PILImage
                    import numpy as _np_nmr
                    _rdmol = Chem.MolFromSmiles(smiles)
                    if _rdmol:
                        _img = _RDDraw.MolToImage(_rdmol, size=(150, 110))
                        # [FIX-NMR-BG] 흰색 배경 → 다크 배경으로 변환
                        _arr = _np_nmr.array(_img.convert('RGBA'))
                        # 흰색 픽셀(>240,>240,>240)을 투명으로
                        _white_mask = ((_arr[:,:,0]>235) & (_arr[:,:,1]>235) & (_arr[:,:,2]>235))
                        _arr[_white_mask, 3] = 0   # 알파=0 → 투명
                        # 검정 픽셀(<30,<30,<30)은 밝은 회색으로 (다크 배경에서 가시성)
                        _black_mask = ((_arr[:,:,0]<30) & (_arr[:,:,1]<30) & (_arr[:,:,2]<30) & (_arr[:,:,3]>100))
                        _arr[_black_mask, :3] = 200
                        _img_dark = _PILImage.fromarray(_arr, 'RGBA')
                        _buf = _BytesIO()
                        _img_dark.save(_buf, format='PNG')
                        _buf.seek(0)
                        _arr2 = _np_nmr.array(_PILImage.open(_buf))
                        from matplotlib.offsetbox import OffsetImage, AnnotationBbox
                        _ib = OffsetImage(_arr2, zoom=0.62, alpha=0.88)
                        _ab = AnnotationBbox(_ib, (0.87, 0.80),
                                             xycoords='axes fraction', frameon=False,
                                             bboxprops=dict(edgecolor='none', alpha=0))
                        self.ax.add_artist(_ab)
                except Exception:
                    pass
            xlabel = "Chemical Shift (ppm)"
            title = "Predicted ¹H NMR Spectrum"
            self.ax.invert_xaxis()
            self.ax.set_xlim(11, -1)
            self.ax.set_ylabel("Relative Intensity", color="white", fontsize=9)

        elif spec_type == "NMR_C13":
            # [NMR-C13-GUIDE] ¹³C NMR: 0~220 ppm 범위 + 구역 레이블 + 탄소번호 분자구조
            x = np.linspace(-5, 225, 2000)
            y = np.zeros_like(x)
            gamma = 0.8
            for f, intensity in zip(freqs, ints):
                y += intensity * (gamma**2 / ((x - f)**2 + gamma**2))
            y_max = np.max(y) if np.max(y) > 0 else 1
            y = y / y_max
            self.plot_x, self.plot_y = x, y * 100
            self.ax.plot(x, y, color="#26c6da", linewidth=1.2)
            self.ax.fill_between(x, y, alpha=0.15, color="#26c6da")
            # 구역 레이블
            for ppm, zone in [(20, "sp³ C"), (75, "C-O"), (128, "sp² C\n(방향족)"), (195, "C=O")]:
                self.ax.text(ppm, 0.88, zone,
                             ha='center', fontsize=7, color='#888')
            # 구역 구분선
            for pline in [55, 100, 170]:
                self.ax.axvline(x=pline, color='#444', linestyle=':', alpha=0.5, lw=0.7)
            # [NMR-C13-NUM] 피크에 탄소번호 주석 + 분자구조 이미지 삽입
            # 탄소 혼성화별 색상: sp3=파랑, sp2=초록, sp=빨강, C=O=주황
            if smiles and RDKIT_AVAILABLE:
                try:
                    from rdkit import Chem
                    from rdkit.Chem import Draw as _RDDraw, rdMolDescriptors as _rmd
                    from rdkit.Chem.Draw import rdMolDraw2D
                    from io import BytesIO as _BytesIO
                    import PIL.Image as _PILImage
                    import numpy as _np_c13
                    HYB = Chem.rdchem.HybridizationType
                    _mol13 = Chem.MolFromSmiles(smiles)
                    if _mol13:
                        carbon_atoms = [a for a in _mol13.GetAtoms() if a.GetAtomicNum() == 6]
                        c_idx_list = [a.GetIdx() for a in carbon_atoms]
                        # 탄소별 색상 결정
                        atom_colors = {}
                        bond_colors = {}
                        for i, atom in enumerate(_mol13.GetAtoms()):
                            if atom.GetAtomicNum() != 6:
                                continue
                            hyb = atom.GetHybridization()
                            # C=O 검출
                            has_co = any(
                                b.GetBondTypeAsDouble() == 2.0 and
                                (b.GetBeginAtom().GetAtomicNum() == 8 or
                                 b.GetEndAtom().GetAtomicNum() == 8)
                                for b in atom.GetBonds())
                            if has_co:
                                atom_colors[atom.GetIdx()] = (1.0, 0.5, 0.0)   # 주황
                            elif hyb == HYB.SP2:
                                atom_colors[atom.GetIdx()] = (0.1, 0.7, 0.2)   # 초록
                            elif hyb == HYB.SP:
                                atom_colors[atom.GetIdx()] = (0.9, 0.1, 0.1)   # 빨강
                            else:
                                atom_colors[atom.GetIdx()] = (0.2, 0.4, 1.0)   # 파랑(sp3)

                        # 탄소 번호 주석 추가 (피크 위에 C1, C2...)
                        c_peak_shift = {}  # 탄소 번호 → 피크 ppm (freqs와 1:1 매핑)
                        for ci, ppm_val in zip(range(len(c_idx_list)), freqs[:len(c_idx_list)]):
                            c_peak_shift[ci + 1] = ppm_val
                        for ci, ppm_val in c_peak_shift.items():
                            # y값 찾기
                            idx_x = int(_np_c13.argmin(_np_c13.abs(x - ppm_val)))
                            y_at = float(y[idx_x]) if idx_x < len(y) else 0.05
                            color_key = c_idx_list[ci - 1] if ci - 1 < len(c_idx_list) else 0
                            r, g, b = atom_colors.get(color_key, (0.6, 0.6, 0.6))
                            col_hex = "#{:02X}{:02X}{:02X}".format(int(r*255), int(g*255), int(b*255))
                            self.ax.annotate(
                                f"C{ci}",
                                xy=(ppm_val, y_at),
                                xytext=(ppm_val, y_at + 0.06 + (ci % 3) * 0.05),
                                fontsize=6, color=col_hex, ha='center', va='bottom',
                                arrowprops=dict(arrowstyle='-', color=col_hex, lw=0.7),
                            )

                        # 분자 구조 이미지 (탄소번호 + 색상, 우상단 배치)
                        try:
                            drawer = rdMolDraw2D.MolDraw2DCairo(200, 150)
                            drawer.drawOptions().addAtomIndices = False
                            # 탄소 원자 번호 표시
                            atom_notes = {}
                            for ci2, aidx in enumerate(c_idx_list):
                                r2, g2, b2 = atom_colors.get(aidx, (0.6, 0.6, 0.6))
                                atom_notes[aidx] = f"C{ci2+1}"
                            drawer.drawOptions().annotationFontScale = 0.7
                            drawer.DrawMolecule(
                                _mol13, highlightAtoms=c_idx_list,
                                highlightAtomColors=atom_colors,
                                highlightBonds=[],
                                highlightBondColors={},
                            )
                            drawer.FinishDrawing()
                            _buf13 = _BytesIO(drawer.GetDrawingText())
                            _img13 = _PILImage.open(_buf13)
                            _arr13 = _np_c13.array(_img13.convert('RGBA'))
                            _white = (_arr13[:,:,0]>235) & (_arr13[:,:,1]>235) & (_arr13[:,:,2]>235)
                            _arr13[_white, 3] = 0
                            _black = (_arr13[:,:,0]<30) & (_arr13[:,:,1]<30) & (_arr13[:,:,2]<30) & (_arr13[:,:,3]>100)
                            _arr13[_black, :3] = 200
                            _img13_final = _PILImage.fromarray(_arr13, 'RGBA')
                            from matplotlib.offsetbox import OffsetImage, AnnotationBbox
                            _ib13 = OffsetImage(_np_c13.array(_img13_final), zoom=0.65, alpha=0.90)
                            # 우상단 (200ppm 근방) 배치
                            _ab13 = AnnotationBbox(_ib13, (0.15, 0.80),
                                                   xycoords='axes fraction', frameon=False)
                            self.ax.add_artist(_ab13)
                            # 범례 (색상 설명)
                            from matplotlib.patches import Patch
                            legend_els = [
                                Patch(facecolor='#3366FF', label='sp³ C'),
                                Patch(facecolor='#1AB233', label='sp² C'),
                                Patch(facecolor='#FF8000', label='C=O'),
                                Patch(facecolor='#E61A1A', label='sp C'),
                            ]
                            self.ax.legend(handles=legend_els, loc='upper center',
                                           fontsize=6, ncol=4, framealpha=0.3,
                                           labelcolor='white', facecolor='#1e1e1e')
                        except Exception:
                            pass  # Cairo 없을 때 조용히 실패
                except Exception:
                    pass
            xlabel = "Chemical Shift (ppm)"
            title = "Predicted ¹³C NMR Spectrum"
            self.ax.invert_xaxis()
            self.ax.set_xlim(220, -5)
            self.ax.set_ylabel("Relative Intensity", color="white", fontsize=9)

        elif spec_type == "UV-Vis":
            # [UV-Vis-GUIDE] 이중 서브플롯: 좌=ε, 우=log ε (Woodward-Fieser 준거)
            self.figure.clear()
            ax1 = self.figure.add_subplot(1, 2, 1)  # ε
            ax2 = self.figure.add_subplot(1, 2, 2)  # log ε
            self.ax = ax1
            ax1.set_facecolor("#1e1e1e")
            ax2.set_facecolor("#1e1e1e")

            x = np.linspace(180, 800, 1500)
            y_abs = np.zeros_like(x)
            sigma = 20.0
            for f, intensity in zip(freqs, ints):
                y_abs += intensity * np.exp(-((x - f)**2) / (2 * sigma**2))
            y_max_uv = np.max(y_abs) if np.max(y_abs) > 0 else 1
            epsilon = y_abs / y_max_uv * 30000.0
            log_eps = np.log10(np.maximum(epsilon, 1.0))
            self.plot_x, self.plot_y = x, epsilon

            # 가시광 배경 밴드
            vis_bands = [(380, 450, 'violet'), (450, 495, 'blue'),
                         (495, 570, 'green'), (570, 590, 'yellow'),
                         (590, 620, 'orange'), (620, 750, 'red')]

            for ax_uv, y_data, color_uv, ylabel_uv, t_uv in [
                (ax1, epsilon, "#ff9800", "ε (M⁻¹ cm⁻¹)", "ε (Linear)"),
                (ax2, log_eps, "#ef5350", "log ε", "log ε"),
            ]:
                ax_uv.plot(x, y_data, color=color_uv, linewidth=1.4)
                y_min_v = np.min(y_data) if ax_uv is ax2 else 0
                ax_uv.fill_between(x, y_data, y_min_v, alpha=0.15, color=color_uv)
                for ws, we, wc in vis_bands:
                    ax_uv.axvspan(ws, we, color=wc, alpha=0.06)
                ax_uv.set_xlabel("Wavelength (nm)", color="white", fontsize=8)
                ax_uv.set_ylabel(ylabel_uv, color="white", fontsize=8)
                ax_uv.set_title(t_uv, color="white", fontsize=9)
                ax_uv.set_xlim(180, 800)
                ax_uv.tick_params(colors="white", labelsize=7)
                for sp in ax_uv.spines.values():
                    sp.set_color("#555")

            lam_max = float(x[int(np.argmax(y_abs))])
            self.figure.suptitle(
                f"Predicted UV-Vis Spectrum  (SMILES 기반 예측)  |  λmax ≈ {lam_max:.0f} nm",
                color="white", fontsize=10)
            self.figure.patch.set_facecolor("#1e1e1e")
            self.figure.tight_layout()
            self.canvas.draw()
            self.info_label.setText(
                f"예측 UV-Vis 스펙트럼  |  피크: {len(freqs)}개  |  λmax ≈ {lam_max:.0f} nm")
            return  # UV-Vis는 별도 서브플롯 → early return

        elif spec_type == "MS":
            # MS: 막대 스펙트럼 + 분열 위치 표시
            x_int = [round(f) for f in freqs]
            self.plot_x, self.plot_y = np.array(x_int), np.array(ints)
            self.ax.bar(x_int, ints, color="#9c27b0", width=0.8, alpha=0.85)
            xlabel = "m/z"
            title = "Predicted Mass Spectrum"
            # [MS-FIX] x축 0부터 M⁺+20까지 (전체 범위)
            mw_peak = max(x_int) if x_int else 100
            self.ax.set_xlim(0, mw_peak + 20)
            self.ax.set_ylabel("Relative Intensity (%)", color="white", fontsize=9)

            # [MS-FRAG] 주요 단편화 m/z 위치에 빨간 점선 표시
            frag_colors = {
                "M⁺":  "#ffffff",
                "M-1":  "#ff7043",
                "M-OH": "#ef5350",
                "M-CH₃": "#ffa726",
                "m/z=77\n(Ph⁺)": "#ab47bc",
            }
            frag_positions = {}
            for x_v, i_v in zip(x_int, ints):
                diff = mw_peak - x_v
                if diff == 0:    frag_positions[x_v] = ("M⁺",      "#ffffff")
                elif diff == 1:  frag_positions[x_v] = ("M-1",     "#ff7043")
                elif diff == 17: frag_positions[x_v] = ("M-OH",    "#ef5350")
                elif diff == 15: frag_positions[x_v] = ("M-CH₃",   "#ffa726")
                elif abs(x_v - 77) <= 1 and i_v > 5:
                    frag_positions[x_v] = ("m/z=77\n(Ph⁺)", "#ab47bc")

            for mz_val, (frag_lbl, fcol) in frag_positions.items():
                self.ax.axvline(x=mz_val, color=fcol, linestyle='--',
                                alpha=0.55, linewidth=1.0)
                # 피크 레이블 (최상단에 표시)
                self.ax.text(mz_val, 103, frag_lbl, color=fcol,
                             fontsize=7, ha='center', va='bottom', rotation=75)

            # [MS-MOLIMG] 분자 구조 이미지 삽입 (좌상단 — 피크가 적은 저질량 영역)
            if smiles and RDKIT_AVAILABLE:
                try:
                    from rdkit.Chem import Draw as _RDDraw_ms
                    from io import BytesIO as _BytesIO_ms
                    import PIL.Image as _PILImage_ms
                    import numpy as _np_ms
                    _mol_ms = Chem.MolFromSmiles(smiles)
                    if _mol_ms:
                        _img_ms = _RDDraw_ms.MolToImage(_mol_ms, size=(140, 100))
                        _arr_ms = _np_ms.array(_img_ms.convert('RGBA'))
                        _wm = (_arr_ms[:,:,0]>235) & (_arr_ms[:,:,1]>235) & (_arr_ms[:,:,2]>235)
                        _arr_ms[_wm, 3] = 0
                        _bm = (_arr_ms[:,:,0]<30) & (_arr_ms[:,:,1]<30) & (_arr_ms[:,:,2]<30) & (_arr_ms[:,:,3]>100)
                        _arr_ms[_bm, :3] = 200
                        _img_ms_d = _PILImage_ms.fromarray(_arr_ms, 'RGBA')
                        from matplotlib.offsetbox import OffsetImage, AnnotationBbox
                        _ib_ms = OffsetImage(_np_ms.array(_img_ms_d), zoom=0.58, alpha=0.88)
                        _ab_ms = AnnotationBbox(_ib_ms, (0.16, 0.78),
                                                xycoords='axes fraction', frameon=False)
                        self.ax.add_artist(_ab_ms)
                        # M⁺ 분자량 텍스트
                        self.ax.text(0.16, 0.56, f"M⁺ = {mw_peak} Da",
                                     transform=self.ax.transAxes,
                                     color='#ce93d8', fontsize=8, ha='center',
                                     bbox=dict(boxstyle='round,pad=0.3',
                                               facecolor='#1a1a1a', alpha=0.7))
                except Exception:
                    pass

        else:
            return

        self.ax.set_xlabel(xlabel, color="white", fontsize=9)
        self.ax.set_title(f"{title}  (SMILES 기반 예측)", color="white", fontsize=10)
        self.ax.tick_params(colors="white", labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color("#555")

        self.figure.tight_layout()
        self.canvas.draw()
        self.info_label.setText(
            f"예측 {spec_type} 스펙트럼  |  피크: {len(freqs)}개"
            f"{'  |  SMILES: ' + smiles[:25] if smiles else ''}")

    # ── PDF 일괄 내보내기 (SpectrumPDFExporter 연동) ────────────────
    def _export_pdf(self):
        """모든 스펙트럼을 고품질 PDF로 일괄 출력 (SpectrumPDFExporter 사용).
        대학장비 분석급 가시성: IR(전송투과율), NMR(적분+구역), UV-Vis(ε/logε)
        """
        if not MATPLOTLIB_AVAILABLE:
            self.info_label.setText("⚠️ matplotlib 미설치")
            return
        smiles = getattr(self, '_smiles_cache', '')
        spec_type = getattr(self, '_spec_type', 'IR')

        # [FIX-PDF-PATH] auto_generated 폴더 기본 저장 경로
        import datetime as _dt_pdf
        _auto_dir = _SCRIPT_DIR.parent.parent / "docs" / "exports" / "spectra_assets" / "auto_generated"
        try:
            _auto_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            _auto_dir = Path(os.getcwd())
        _ts = _dt_pdf.datetime.now().strftime("%Y%m%d_%H%M%S")
        _safe_smiles = re.sub(r'[\\/:*?"<>|]', '', (smiles or "mol")[:12])
        _default_name = f"{_safe_smiles}_{spec_type}_{_ts}.pdf"

        filepath, _ = QFileDialog.getSaveFileName(
            self, "스펙트럼 PDF 일괄 저장",
            str(_auto_dir / _default_name),
            "PDF Files (*.pdf);;PNG Files (*.png);;All Files (*)")
        if not filepath:
            return

        # PNG 저장 (간단 모드 - 현재 figure 그대로)
        if filepath.lower().endswith('.png'):
            try:
                if self.ax is not None:
                    self.figure.savefig(filepath, dpi=200, bbox_inches='tight',
                                       facecolor='#1e1e1e', edgecolor='none')
                    self.info_label.setText(f"✅ PNG 저장: {filepath}")
                else:
                    self.info_label.setText("⚠️ 먼저 스펙트럼을 로드하세요")
            except Exception as e:
                self.info_label.setText(f"❌ 저장 실패: {e}")
            return

        # PDF 저장 — SpectrumPDFExporter 일괄 출력 시도
        try:
            import sys as _sys
            _exporter_path = str(_SCRIPT_DIR.parent.parent / "agents" / "09_data_export")
            if _exporter_path not in _sys.path:
                _sys.path.insert(0, _exporter_path)
            from spectrum_pdf_exporter import SpectrumPDFExporter, generate_spectrum_graph
            import datetime as _dt

            self.info_label.setText("🔄 PDF 생성 중 (고품질 일괄 출력)...")
            QApplication.processEvents()

            # 현재 SMILES로 모든 스펙트럼 데이터 생성
            spectra_data = {}
            if smiles and RDKIT_AVAILABLE:
                for st, key in [("IR","IR"),("Raman","Raman"),
                                 ("NMR_H","NMR_1H"),("NMR_C13","NMR_13C"),("UV-Vis","UV-Vis")]:
                    try:
                        fq, it = predict_spectrum_from_smiles(smiles, st)
                        if fq:
                            if st == "IR":
                                import numpy as _np
                                x = _np.linspace(400, 4000, 1000)
                                y = _np.ones_like(x) * 100
                                gamma = 20.0
                                for f, intensity in zip(fq, it):
                                    y -= intensity / max(it) * 80 * (gamma**2 / ((x - f)**2 + gamma**2))
                                spectra_data[key] = {"x": x, "y": y,
                                    "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                                    "notes": "SMILES 기반 예측", "smiles": smiles}
                            elif st in ("NMR_H", "NMR_C13"):
                                import numpy as _np
                                xmin, xmax = (-1, 12) if st == "NMR_H" else (-5, 225)
                                x = _np.linspace(xmin, xmax, 2000)
                                y = _np.zeros_like(x)
                                for f, intensity in zip(fq, it):
                                    g = 0.05 if st == "NMR_H" else 0.8
                                    y += intensity * (g**2 / ((x - f)**2 + g**2))
                                y /= max(y.max(), 1.0)
                                spectra_data[key] = {"x": x, "y": y,
                                    "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                                    "notes": "SMILES 기반 예측", "smiles": smiles}
                            elif st == "UV-Vis":
                                import numpy as _np
                                x = _np.linspace(180, 800, 1500)
                                y = _np.zeros_like(x)
                                sigma = 20.0
                                for f, intensity in zip(fq, it):
                                    y += intensity * _np.exp(-((x - f)**2) / (2 * sigma**2))
                                y /= max(y.max(), 1.0)
                                spectra_data["UV-Vis"] = {"x": x, "y": y,
                                    "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 5))],
                                    "notes": "SMILES 기반 예측", "smiles": smiles,
                                    "concentration": 1e-4, "path_length": 1.0}
                            else:
                                import numpy as _np
                                x = _np.linspace(400, 4000, 1000)
                                y = _np.zeros_like(x)
                                gamma = 20.0
                                for f, intensity in zip(fq, it):
                                    y += intensity * (gamma**2 / ((x - f)**2 + gamma**2))
                                y /= max(y.max(), 1.0)
                                spectra_data[key] = {"x": x, "y": y,
                                    "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                                    "notes": "SMILES 기반 예측", "smiles": smiles}
                    except Exception:
                        pass

            if not spectra_data:
                # 현재 figure만 저장
                if self.ax is not None:
                    self.figure.savefig(filepath, dpi=200, bbox_inches='tight',
                                       facecolor='#1e1e1e', edgecolor='none')
                    self.info_label.setText(f"✅ 현재 스펙트럼 저장 (단일): {filepath}")
                else:
                    self.info_label.setText("⚠️ 스펙트럼 데이터 없음. 분자를 먼저 로드하세요.")
                return

            exporter = SpectrumPDFExporter(output_dir=str(Path(filepath).parent))
            mol_name = smiles[:20] if smiles else "Unknown"
            pdf_path = exporter.create_report(
                molecule_name=mol_name,
                spectra_data=spectra_data,
                filename=Path(filepath).name,
                metadata={"smiles": smiles, "formula": "N/A",
                          "iupac_name": "", "common_name": mol_name}
            )
            if pdf_path:
                self.info_label.setText(f"✅ 고품질 PDF 저장: {pdf_path}")
            else:
                self.info_label.setText("⚠️ PDF 생성 실패 — PNG로 재시도 권장")
        except ImportError:
            # SpectrumPDFExporter 없으면 현재 figure 저장
            try:
                if self.ax is not None:
                    self.figure.savefig(filepath, dpi=200, bbox_inches='tight',
                                       facecolor='#1e1e1e', edgecolor='none')
                    self.info_label.setText(f"✅ 저장 (기본 모드): {filepath}")
                else:
                    self.info_label.setText("⚠️ 스펙트럼을 먼저 로드하세요")
            except Exception as e2:
                self.info_label.setText(f"❌ 저장 실패: {e2}")
        except Exception as e:
            self.info_label.setText(f"❌ PDF 오류: {str(e)[:60]}")

    # ── [SPEC-3] 진동모드 연계 토글 ─────────────────────────────────
    def _toggle_vib_link(self, checked: bool):
        """스펙트럼 내 진동모드 표시 토글 — 부모 팝업의 탭으로 전환"""
        # 부모 Molecule3DPopup에 신호 전달 (부모 탭 전환)
        popup = self.parent()
        while popup and not isinstance(popup, Molecule3DPopup):
            popup = popup.parent() if hasattr(popup, 'parent') else None
        if popup and hasattr(popup, 'tabs'):
            if checked:
                # 진동모드 탭 활성화
                for i in range(popup.tabs.count()):
                    if "진동" in popup.tabs.tabText(i):
                        popup.tabs.setCurrentIndex(i)
                        break
            self.btn_vib_link.setText(
                "🎵 진동모드 보기 ✓" if checked else "🎵 진동모드 표시")

    def plot_ir(self, frequencies: List[float], intensities: List[float]):
        """IR 스펙트럼 플롯"""
        if not MATPLOTLIB_AVAILABLE:
            return

        # 데이터를 인스턴스 변수로 저장 (AI 오버레이에서 사용)
        self.frequencies = list(frequencies)
        self.intensities = list(intensities) if intensities else [1.0] * len(frequencies)
        # AI 분석 캐시 초기화 (새 데이터 로드 시)
        self.ai_analysis_data = None
        self.ai_annotations = []
        self.ai_overlay_visible = False
        if hasattr(self, 'btn_ai_overlay'):
            self.btn_ai_overlay.setChecked(False)

        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#1e1e1e")

        if not frequencies:
            self.ax.text(0.5, 0.5, "진동 주파수 데이터 없음", transform=self.ax.transAxes,
                         ha="center", color="white", fontsize=12)
            self.canvas.draw()
            return

        # Generate Lorentzian-broadened spectrum
        x = np.linspace(400, 4000, 3000)
        y = np.zeros_like(x)
        gamma = 15.0  # broadening (cm^-1)

        # Use intensities if available, else uniform
        ints = self.intensities if len(self.intensities) == len(frequencies) else [1.0] * len(frequencies)

        for freq, inten in zip(frequencies, ints):
            if freq > 0:  # skip imaginary frequencies
                y += inten * (gamma**2 / ((x - freq)**2 + gamma**2))

        # Normalize
        if np.max(y) > 0:
            y = y / np.max(y) * 100

        # 플롯 데이터 저장 (AI 오버레이에서 y값 조회에 사용)
        self.plot_x = x
        self.plot_y = y

        self.ax.plot(x, y, color="#00bcd4", linewidth=1.2)
        self.ax.fill_between(x, y, alpha=0.15, color="#00bcd4")

        # Mark peak positions
        for freq, inten in zip(frequencies, ints):
            if freq > 400 and inten > max(ints) * 0.1:
                self.ax.axvline(x=freq, color="#ff5722", alpha=0.3, linewidth=0.5)

        self.ax.set_xlabel("Wavenumber (cm⁻¹)", color="white", fontsize=9)
        self.ax.set_ylabel("Transmittance (%)", color="white", fontsize=9)
        self.ax.set_title("IR Spectrum (ORCA)", color="white", fontsize=10)
        self.ax.invert_xaxis()
        self.ax.tick_params(colors="white", labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color("#555")
        self.ax.set_xlim(4000, 400)
        self.ax.set_ylim(0, 110)

        self.figure.tight_layout()
        self.canvas.draw()
        self.info_label.setText(f"진동 모드: {len(frequencies)}개  |  범위: {min(frequencies):.0f}–{max(frequencies):.0f} cm⁻¹")

    # ------------------------------------------------------------------
    # AI 피크 분석 오버레이 메서드
    # ------------------------------------------------------------------

    def _toggle_ai_overlay(self):
        """AI 피크 분석 오버레이 토글"""
        if not hasattr(self, 'btn_ai_overlay'):
            return
        if self.btn_ai_overlay.isChecked():
            # 오버레이 표시
            if not self.frequencies:
                self.btn_ai_overlay.setChecked(False)
                return
            if self.ai_analysis_data is None:
                self._run_ai_peak_analysis()
            self._show_ai_annotations()
        else:
            # 오버레이 숨김
            self._hide_ai_annotations()

    def _run_ai_peak_analysis(self):
        """AI로 IR 스펙트럼 피크 분석 수행"""
        if not self.frequencies:
            return

        # 방법 1: Gemini API 사용 (GEMINI_AVAILABLE + API 키 존재 시)
        if self._gemini.is_available:
            try:
                freq_list = [f for f in self.frequencies if f > 0]
                intensity_list = self.intensities[:len(freq_list)] if self.intensities else []

                prompt = (
                    "다음 IR 스펙트럼 진동수 데이터를 분석해서, 각 주요 피크가 어떤 작용기의 진동에 해당하는지 알려주세요.\n"
                    f"진동수 (cm⁻¹): {freq_list[:20]}\n"
                    f"강도: {intensity_list[:20]}\n\n"
                    "**반드시 아래 JSON 형식으로만 응답하세요:**\n"
                    '[\n'
                    '  {"freq": 3400, "label": "O-H stretch", "group": "hydroxyl"},\n'
                    '  {"freq": 1720, "label": "C=O stretch", "group": "carbonyl"},\n'
                    '  ...\n'
                    ']\n'
                    "각 피크의 freq(cm⁻¹), label(한국어 또는 영어), group(작용기명)을 포함하세요.\n"
                    "상위 5~10개 중요 피크만 선택하세요."
                )

                response = self._gemini.model.generate_content(prompt)
                # JSON 파싱 시도
                try:
                    json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    if json_match:
                        self.ai_analysis_data = json.loads(json_match.group())
                    else:
                        self.ai_analysis_data = self._fallback_peak_analysis()
                except (json.JSONDecodeError, Exception):
                    self.ai_analysis_data = self._fallback_peak_analysis()
            except Exception as e:
                logger.warning(f"Gemini peak analysis failed: {e}")
                self.ai_analysis_data = self._fallback_peak_analysis()
        else:
            # 방법 2: 룰 기반 폴백 (API 불필요)
            self.ai_analysis_data = self._fallback_peak_analysis()

    def _fallback_peak_analysis(self) -> List[Dict]:
        """API 없이 룰 기반 IR 피크 분석 (화학 교과서 기반)"""
        if not self.frequencies:
            return []

        # 표준 IR 작용기 영역 테이블
        IR_REGIONS = [
            (3200, 3600, "O-H stretch", "하이드록실 (OH)"),
            (3300, 3500, "N-H stretch", "아민 (NH)"),
            (2850, 3000, "C-H stretch (sp3)", "알케인 C-H"),
            (3000, 3100, "C-H stretch (sp2)", "알켄/방향족 C-H"),
            (3300, 3320, "C≡C-H stretch", "알카인 C-H"),
            (2100, 2260, "C≡C / C≡N stretch", "삼중결합"),
            (1680, 1750, "C=O stretch", "카르보닐"),
            (1600, 1680, "C=C stretch", "알켄/방향족"),
            (1500, 1600, "방향족 C=C", "방향족 고리"),
            (1000, 1300, "C-O stretch", "에테르/알코올"),
            (500, 1000, "지문 영역", "분자 고유 진동"),
        ]

        results = []
        freq_list = [f for f in self.frequencies if f > 0]
        ints = self.intensities if len(self.intensities) == len(self.frequencies) else [1.0] * len(freq_list)
        # 양수 주파수에 대응하는 강도만 추출
        pos_ints = []
        for i, f in enumerate(self.frequencies):
            if f > 0:
                pos_ints.append(ints[i] if i < len(ints) else 1.0)

        for low, high, label, group in IR_REGIONS:
            best_freq = None
            best_intensity = 0
            for i, f in enumerate(freq_list):
                if low <= f <= high:
                    inten = pos_ints[i] if i < len(pos_ints) else 1.0
                    if inten > best_intensity:
                        best_intensity = inten
                        best_freq = f

            if best_freq is not None and best_intensity > 0.1:
                results.append({
                    "freq": round(best_freq, 1),
                    "label": label,
                    "group": group
                })

        return results

    def _show_ai_annotations(self):
        """matplotlib 그래프 위에 AI 분석 주석 표시"""
        if not self.ai_analysis_data or self.ax is None:
            return

        self._hide_ai_annotations()  # 기존 주석 제거

        colors = ['#FF5722', '#2196F3', '#4CAF50', '#FF9800', '#9C27B0',
                  '#00BCD4', '#E91E63', '#8BC34A', '#FFC107', '#673AB7']

        for i, peak in enumerate(self.ai_analysis_data):
            freq = peak.get("freq", 0)
            label = peak.get("label", "")
            group = peak.get("group", "")

            # 그래프의 y값 찾기
            y_val = self._get_spectrum_value_at(freq)

            color = colors[i % len(colors)]

            # 화살표 + 텍스트 주석 (겹침 방지를 위해 y 오프셋 교대)
            y_offset = 15 + (i % 3) * 8
            ann = self.ax.annotate(
                f"{label}\n({group})",
                xy=(freq, y_val),
                xytext=(freq, y_val + y_offset),
                fontsize=7,
                color=color,
                fontweight='bold',
                ha='center',
                va='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.15, edgecolor=color),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5)
            )
            self.ai_annotations.append(ann)

        # 범례 (우상단)
        ann_legend = self.ax.annotate(
            "⚡ AI 분석 (참고용)",
            xy=(0.98, 0.98), xycoords='axes fraction',
            fontsize=8, color='#FF9800',
            ha='right', va='top',
            bbox=dict(boxstyle='round', facecolor='#263238', alpha=0.8, edgecolor='#FF9800')
        )
        self.ai_annotations.append(ann_legend)

        self.canvas.draw()  # matplotlib canvas 갱신
        self.ai_overlay_visible = True

    def _hide_ai_annotations(self):
        """AI 분석 주석 모두 숨기기"""
        for ann in self.ai_annotations:
            try:
                ann.remove()
            except Exception:
                pass
        self.ai_annotations = []

        if hasattr(self, 'canvas') and self.canvas is not None:
            self.canvas.draw()
        self.ai_overlay_visible = False

    def _get_spectrum_value_at(self, freq: float) -> float:
        """주어진 진동수에서의 스펙트럼 y값 반환"""
        if self.plot_x is None or self.plot_y is None:
            return 50.0
        idx = int(np.argmin(np.abs(self.plot_x - freq)))
        if idx < len(self.plot_y):
            return float(self.plot_y[idx])
        return 50.0


class VibrationPanel(QWidget):
    """🎵 진동모드 탭 — 모드 선택 + 3D 애니메이션 제어"""

    mode_selected = pyqtSignal(int)      # mode index
    animation_toggled = pyqtSignal(bool)  # play/stop

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Mode list
        layout.addWidget(QLabel("진동 모드 선택:"))
        self.mode_list = QListWidget()
        self.mode_list.currentRowChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_list)

        # Animation controls
        ctrl = QHBoxLayout()
        self.btn_play = QPushButton("▶ 재생")
        self.btn_play.setCheckable(True)
        self.btn_play.clicked.connect(self._toggle_animation)
        ctrl.addWidget(self.btn_play)

        ctrl.addWidget(QLabel("진폭:"))
        self.amp_slider = QSlider(Qt.Orientation.Horizontal)
        self.amp_slider.setMinimum(10)
        self.amp_slider.setMaximum(300)
        self.amp_slider.setValue(100)
        ctrl.addWidget(self.amp_slider)
        layout.addLayout(ctrl)

        # Info
        self.info_label = QLabel("ORCA 데이터에서 진동 모드를 로드하세요")
        self.info_label.setStyleSheet("color: #888; font-size: 9pt;")
        layout.addWidget(self.info_label)

        self.setLayout(layout)

    def load_modes(self, frequencies: List[float], ir_intensities: List[float] = None):
        """진동 모드 목록 로드"""
        self.mode_list.clear()
        for i, freq in enumerate(frequencies):
            inten_str = ""
            if ir_intensities and i < len(ir_intensities):
                inten_str = f"  (I={ir_intensities[i]:.1f})"
            tag = "⚠️ " if freq < 0 else ""
            item = QListWidgetItem(f"{tag}Mode {i+1}: {freq:.1f} cm⁻¹{inten_str}")
            self.mode_list.addItem(item)
        self.info_label.setText(f"{len(frequencies)}개 진동 모드 로드됨")

    def _on_mode_changed(self, row):
        if row >= 0:
            self.mode_selected.emit(row)

    def _toggle_animation(self, checked):
        self.btn_play.setText("⏸ 정지" if checked else "▶ 재생")
        self.animation_toggled.emit(checked)


class AIAnalysisPanel(QWidget):
    """📝 AI 분석 탭 — Gemini 기반"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._analyzer = GeminiAnalyzer()

    # [AI-1] 섹션별 구조화된 AI 분석 패널
    _SECTIONS = [
        ("🔬 작용기 분석",  "functional_group",
         "주요 작용기와 화학적 특성을 분석해주세요. (예: 하이드록실기, 카르보닐기 등)"),
        ("⚡ 반응성 예측",  "reactivity",
         "친핵성/친전자성, 산/염기성, 산화환원 반응성을 예측해주세요."),
        ("📈 스펙트럼 특징", "spectrum",
         "IR, ¹H NMR, UV-Vis 핵심 피크를 예측해주세요. 예: IR 1720 cm⁻¹ C=O 등."),
        ("💊 응용 및 주의",  "application",
         "실용적 응용 분야, 독성/안전성 주의사항을 알려주세요."),
        ("🧪 화학적 사실",   "facts",
         "흥미로운 화학적 사실, 유사 화합물, 역사적 배경을 알려주세요."),
    ]

    def _init_ui(self):
        outer = QVBoxLayout()
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # ── 상단 버튼 바 ──────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("⚡ AI 분석 (Gemini — 참고용 ★★★☆☆)"))
        top_bar.addStretch()

        self.btn_analyze_all = QPushButton("🔍 전체 분석")
        self.btn_analyze_all.setFixedHeight(26)
        self.btn_analyze_all.setStyleSheet(
            "QPushButton { background:#1565C0; color:white; border:1px solid #42A5F5; "
            "border-radius:3px; padding:2px 10px; font-size:9pt; }"
            "QPushButton:hover { background:#1976D2; }"
            "QPushButton:disabled { background:#333; color:#666; }")
        self.btn_analyze_all.clicked.connect(self._analyze_all)
        top_bar.addWidget(self.btn_analyze_all)

        btn_clear = QPushButton("❌ 초기화")
        btn_clear.setFixedHeight(26)
        btn_clear.setStyleSheet(
            "QPushButton { background:#37474F; color:#B0BEC5; border:1px solid #546E7A; "
            "border-radius:3px; padding:2px 8px; font-size:9pt; }"
            "QPushButton:hover { background:#455A64; }")
        btn_clear.clicked.connect(self._clear_all)
        top_bar.addWidget(btn_clear)
        outer.addLayout(top_bar)

        # ── API Key 상태 ──
        notice = QLabel(
            "⚠️ 참고용 결과  |  API: " + (
                "✅ GEMINI_API_KEY 설정됨"
                if os.environ.get("GEMINI_API_KEY") else
                "❌ 미설정 (환경변수 GEMINI_API_KEY 필요 — 없으면 룰 기반 대체)"))
        notice.setStyleSheet("color:#f0ad4e; font-size:8pt; padding:2px 4px;")
        outer.addWidget(notice)

        # ── 섹션별 QGroupBox + QTextEdit ─────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#1e1e1e; }")
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(6)
        scroll_layout.setContentsMargins(2, 2, 2, 2)

        self._section_texts: Dict[str, QTextEdit] = {}

        for title, key, hint in self._SECTIONS:
            grp = QGroupBox(title)
            grp.setStyleSheet(
                "QGroupBox { border:1px solid #444; border-radius:4px; "
                "margin-top:8px; padding-top:14px; color:#90CAF9; font-size:9pt; }"
                "QGroupBox::title { subcontrol-origin:margin; left:8px; }")
            grp_layout = QVBoxLayout()
            grp_layout.setContentsMargins(6, 4, 6, 6)
            grp_layout.setSpacing(4)

            # 플레이스홀더 힌트
            placeholder = QLabel(f"💡 {hint}")
            placeholder.setStyleSheet("color:#555; font-size:8pt; font-style:italic;")
            placeholder.setWordWrap(True)
            grp_layout.addWidget(placeholder)

            te = QTextEdit()
            te.setReadOnly(True)
            te.setMinimumHeight(70)
            te.setMaximumHeight(100)
            te.setStyleSheet(
                "QTextEdit { background:#252525; color:#ddd; font-size:9pt; "
                "border:1px solid #333; border-radius:2px; }")
            grp_layout.addWidget(te)
            self._section_texts[key] = te

            # 개별 분석 버튼
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_sec = QPushButton(f"🔍 {title} 분석")
            btn_sec.setFixedHeight(22)
            btn_sec.setStyleSheet(
                "QPushButton { background:#263238; color:#80CBC4; border:1px solid #37474F; "
                "border-radius:2px; padding:1px 8px; font-size:8pt; }"
                "QPushButton:hover { background:#37474F; }")
            btn_sec.clicked.connect(lambda checked, k=key, t=title: self._analyze_section(k, t))
            btn_row.addWidget(btn_sec)
            grp_layout.addLayout(btn_row)
            grp.setLayout(grp_layout)
            scroll_layout.addWidget(grp)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        outer.addWidget(scroll, 1)

        self.setLayout(outer)

        # Data holders
        self._smiles = ""
        self._properties = {}
        self._orca_data = {}

    def set_data(self, smiles: str, properties: Dict = None, orca_data: Dict = None):
        self._smiles = smiles
        self._properties = properties or {}
        self._orca_data = orca_data or {}

    def _analyze_all(self):
        """5개 섹션 모두 순서대로 분석"""
        if not self._smiles:
            for key in self._section_texts:
                self._section_texts[key].setPlainText("⚠️ SMILES 없음 — 분자를 먼저 로드하세요")
            return
        self.btn_analyze_all.setEnabled(False)
        self.btn_analyze_all.setText("🔄 분석 중...")
        QApplication.processEvents()
        for _, key, title in [(s[0], s[1], s[0]) for s in self._SECTIONS]:
            self._analyze_section(key, title, silent=True)
        self.btn_analyze_all.setEnabled(True)
        self.btn_analyze_all.setText("🔍 전체 분석")

    def _clear_all(self):
        """모든 섹션 초기화"""
        for te in self._section_texts.values():
            te.setPlainText("")

    def _analyze_section(self, section_key: str, section_title: str, silent: bool = False):
        """특정 섹션 개별 분석"""
        if not self._smiles:
            self._section_texts[section_key].setPlainText("⚠️ SMILES 없음")
            return
        te = self._section_texts.get(section_key)
        if te is None:
            return
        te.setPlainText("🔄 분석 중...")
        if not silent:
            QApplication.processEvents()
        try:
            result = self._analyze_section_gemini(section_key)
            te.setPlainText(result)
        except Exception as e:
            te.setPlainText(f"⚠️ 오류: {e}")

    def _analyze_section_gemini(self, section_key: str) -> str:
        """섹션별 Gemini 프롬프트 + 룰 기반 폴백"""
        smiles = self._smiles
        mol_info = f"SMILES: {smiles}"
        if self._properties.get("formula"):
            mol_info += f"\n분자식: {self._properties['formula']}"
        if self._properties.get("iupac_name"):
            mol_info += f"\nIUPAC: {self._properties['iupac_name']}"

        section_prompts = {
            "functional_group": (
                f"{mol_info}\n\n이 분자의 주요 작용기를 분석하고 각 작용기의 화학적 특성을 설명해주세요. "
                "반드시 한국어로, 5문장 이내로 답하세요."),
            "reactivity": (
                f"{mol_info}\n\n이 분자의 반응성을 예측하세요. "
                "친핵성/친전자성, 산/염기성, 주요 반응 경로를 한국어로 5문장 이내로 설명하세요."),
            "spectrum": (
                f"{mol_info}\n\n이 분자의 예상 스펙트럼 특징을 분석하세요. "
                "IR 주요 피크(cm⁻¹), ¹H NMR 화학적 이동(ppm), UV-Vis 흡수파장(nm)을 "
                "한국어로 각 1~2문장씩 설명하세요."),
            "application": (
                f"{mol_info}\n\n이 분자의 실용적 응용 분야와 독성/안전성 주의사항을 "
                "한국어로 5문장 이내로 설명하세요."),
            "facts": (
                f"{mol_info}\n\n이 분자에 관한 흥미로운 화학적 사실, 자연에서의 존재, "
                "역사적 발견 배경을 한국어로 3~5문장으로 설명하세요."),
        }
        prompt = section_prompts.get(section_key, f"{mol_info}\n이 분자를 분석하세요.")

        if self._analyzer.is_available:
            try:
                response = self._analyzer.model.generate_content(prompt)
                return response.text
            except Exception as e:
                pass  # fall through to rule-based

        # 룰 기반 폴백 (Gemini 없을 때)
        return self._rule_based_analysis(section_key, smiles)

    def _rule_based_analysis(self, section_key: str, smiles: str) -> str:
        """Gemini API 없을 때 RDKit 기반 간이 분석"""
        if not RDKIT_AVAILABLE:
            return "⚠️ RDKit 미설치 — 룰 기반 분석 불가"
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return "⚠️ SMILES 파싱 실패"
            if section_key == "functional_group":
                groups = []
                if any(a.GetAtomicNum() == 8 and a.GetTotalNumHs() > 0 for a in mol.GetAtoms()):
                    groups.append("하이드록실기 (-OH): 수소결합 공여체, 친수성 향상")
                if any(a.GetAtomicNum() == 7 and a.GetTotalNumHs() > 0 for a in mol.GetAtoms()):
                    groups.append("아민기 (-NH-): 염기성, 수소결합 공여체")
                co_bonds = sum(1 for b in mol.GetBonds()
                               if b.GetBondTypeAsDouble() == 2.0 and
                               {b.GetBeginAtom().GetAtomicNum(),
                                b.GetEndAtom().GetAtomicNum()} == {6, 8})
                if co_bonds > 0:
                    groups.append("카르보닐기 (C=O): 친전자성 탄소, IR ~1720 cm⁻¹")
                cc_double = sum(1 for b in mol.GetBonds()
                                if b.GetBondTypeAsDouble() == 2.0 and
                                b.GetBeginAtom().GetAtomicNum() == 6 and
                                b.GetEndAtom().GetAtomicNum() == 6)
                if cc_double > 0:
                    groups.append("알켄 (C=C): π 결합, 친전자성 첨가반응 가능")
                n_ar = rdMolDescriptors.CalcNumAromaticRings(mol)
                if n_ar > 0:
                    groups.append(f"방향족 고리 {n_ar}개: 친전자성 방향족 치환반응 가능")
                if not groups:
                    groups.append("알케인/알킬: 비극성 CH₂/CH₃ 그룹, 반응성 낮음")
                return "\n".join(f"• {g}" for g in groups)
            elif section_key == "reactivity":
                mw = Descriptors.MolWt(mol)
                logp = Descriptors.MolLogP(mol)
                n_donors = Descriptors.NumHDonors(mol)
                n_accept = Descriptors.NumHAcceptors(mol)
                lines = [
                    f"• 분자량: {mw:.1f} g/mol, LogP: {logp:.2f}",
                    f"• H-Bond 공여체: {n_donors}, 수용체: {n_accept}",
                ]
                if logp > 5:
                    lines.append("• 친지성 강함 → 소수성 상호작용 중요")
                else:
                    lines.append("• 친수성 경향 → 수소결합 상호작용 주요")
                return "\n".join(lines)
            elif section_key == "spectrum":
                lines = ["• IR 예측 피크 (주요):"]
                if any(a.GetAtomicNum() == 8 and a.GetTotalNumHs() > 0 for a in mol.GetAtoms()):
                    lines.append("  O-H stretch: ~3300-3500 cm⁻¹ (넓음)")
                lines.append("  C-H stretch: ~2850-3000 cm⁻¹")
                n_ar = rdMolDescriptors.CalcNumAromaticRings(mol)
                if n_ar > 0:
                    lines.append(f"• UV-Vis: 방향족 π→π* ~254 nm 흡수 예상")
                return "\n".join(lines)
            else:
                return f"(분자: {smiles}) — Gemini API를 설정하면 상세 분석 가능합니다."
        except Exception as e:
            return f"⚠️ 분석 오류: {e}"

    def _request_analysis(self):
        """하위호환 메서드 — 전체 분석으로 라우팅"""
        self._analyze_all()


# ============================================================
# [DOCK-2] 도킹 결합 포켓 2D 시각화 위젯 (QPainter 기반)
# ============================================================

class DockingVisualizationWidget(QWidget):
    """[DOCK-2] 리간드-수용체 결합 포켓 2D 시각화.

    원리:
    - 수용체 Cα 백본 좌표를 XY 직교 투영으로 2D 표시
    - 리간드 중심 기준 15Å 이내 Cα 를 결합 포켓으로 강조
    - 결합 에너지 등급 색상으로 포켓 경계 표시
    - RDKit 2D 리간드 구조 이미지를 우상단에 삽입
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._receptor_atoms: List = []      # [(res, x, y, z, chain)]
        self._ligand_smiles: str = ""
        self._docking_energy: Optional[float] = None
        self._grade_color: str = "#95a5a6"
        self._pocket_atoms: List = []
        self._proj_receptor: List = []       # [(nx, ny)] 정규화 2D
        self._proj_pocket: List = []
        self._ligand_proj: Tuple = (0.5, 0.5)
        self._ligand_img = None              # QImage (리간드 2D)
        self.setMinimumHeight(200)
        self.setMinimumWidth(480)

    def update_docking(self, receptor_atoms: List, ligand_smiles: str,
                       energy: float, grade_color: str):
        """도킹 결과 반영 후 paintEvent 트리거"""
        self._receptor_atoms = receptor_atoms
        self._ligand_smiles = ligand_smiles
        self._docking_energy = energy
        self._grade_color = grade_color

        # 리간드 중심 ← 수용체 Cα 전체 무게중심으로 근사
        if receptor_atoms:
            cx = sum(a[1] for a in receptor_atoms) / len(receptor_atoms)
            cy = sum(a[2] for a in receptor_atoms) / len(receptor_atoms)
            cz = sum(a[3] for a in receptor_atoms) / len(receptor_atoms)
        else:
            cx = cy = cz = 0.0
        self._ligand_center = (cx, cy, cz)

        # 결합 포켓: 리간드 중심 15 Å 이내 Cα
        r2 = 15.0 ** 2
        self._pocket_atoms = [
            a for a in receptor_atoms
            if (a[1]-cx)**2 + (a[2]-cy)**2 + (a[3]-cz)**2 < r2
        ]

        self._project_coords()
        self._build_ligand_image()
        self.update()

    def _project_coords(self):
        """Cα → XY 직교 투영 + [0,1] 정규화"""
        if not self._receptor_atoms:
            self._proj_receptor = []
            self._proj_pocket = []
            return
        xs = [a[1] for a in self._receptor_atoms]
        ys = [a[2] for a in self._receptor_atoms]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        rng = max(xmax - xmin, ymax - ymin, 1.0)
        self._proj_receptor = [
            ((a[1]-xmin)/rng, (a[2]-ymin)/rng)
            for a in self._receptor_atoms
        ]
        self._proj_pocket = [
            ((a[1]-xmin)/rng, (a[2]-ymin)/rng)
            for a in self._pocket_atoms
        ]
        lx, ly = self._ligand_center[0], self._ligand_center[1]
        self._ligand_proj = (
            max(0.02, min(0.98, (lx-xmin)/rng)),
            max(0.02, min(0.98, (ly-ymin)/rng)),
        )

    def _build_ligand_image(self):
        """RDKit → 리간드 2D QImage 생성"""
        self._ligand_img = None
        if not RDKIT_AVAILABLE or not self._ligand_smiles:
            return
        try:
            from rdkit.Chem import Draw as _Draw
            from rdkit.Chem import rdDepictor as _Dep
            from io import BytesIO as _BytesIO
            _mol = Chem.MolFromSmiles(self._ligand_smiles)
            if _mol is None:
                return
            _Dep.Compute2DCoords(_mol)
            _img_pil = _Draw.MolToImage(_mol, size=(120, 90))
            _buf = _BytesIO()
            _img_pil.save(_buf, format='PNG')
            from PyQt6.QtGui import QImage
            self._ligand_img = QImage.fromData(_buf.getvalue())
        except Exception:
            pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 배경
        p.fillRect(self.rect(), QColor(15, 15, 28))

        if not self._proj_receptor:
            p.setPen(QColor(90, 90, 110))
            p.setFont(QFont("Arial", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "🧬  도킹 완료 후 결합 포켓 시각화가 표시됩니다")
            p.end()
            return

        pad = 22
        draw_w = w - pad * 2 - 140   # 우측 리간드 이미지 공간 확보
        draw_h = h - pad * 2 - 28    # 하단 범례 공간

        def scr(nx, ny):
            return (int(pad + nx * draw_w), int(pad + ny * draw_h))

        # ── 수용체 Cα 백본 — 작은 회색 점 ──────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(70, 70, 95, 180))
        for nx, ny in self._proj_receptor:
            sx, sy = scr(nx, ny)
            p.drawEllipse(sx-2, sy-2, 4, 4)

        # ── Cα 백본 연결선 (인접 원자 — 300개 제한) ─────────────────
        p.setPen(QPen(QColor(55, 55, 78, 120), 1))
        for i in range(min(len(self._proj_receptor)-1, 300)):
            sx1, sy1 = scr(*self._proj_receptor[i])
            sx2, sy2 = scr(*self._proj_receptor[i+1])
            dx, dy = sx2-sx1, sy2-sy1
            if dx*dx + dy*dy < (draw_w * 0.12)**2:   # 체인 끊김 방지
                p.drawLine(sx1, sy1, sx2, sy2)

        # ── 결합 포켓 Cα — 등급 색상 하이라이트 점 ──────────────────
        gc = QColor(self._grade_color)
        pocket_fill = QColor(gc)
        pocket_fill.setAlpha(100)
        p.setPen(QPen(gc.lighter(140), 1))
        p.setBrush(pocket_fill)
        for nx, ny in self._proj_pocket:
            sx, sy = scr(nx, ny)
            p.drawEllipse(sx-5, sy-5, 10, 10)

        # ── 결합 포켓 경계 원 (리간드 중심 주위) ─────────────────────
        lsx, lsy = scr(*self._ligand_proj)
        pocket_r = int(min(draw_w, draw_h) * 0.20)
        border_col = QColor(gc)
        border_col.setAlpha(160)
        p.setPen(QPen(border_col, 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(lsx-pocket_r, lsy-pocket_r, pocket_r*2, pocket_r*2)

        # 포켓 중심 마커 (리간드 위치)
        p.setPen(Qt.PenStyle.NoPen)
        center_col = QColor(gc)
        center_col.setAlpha(220)
        p.setBrush(center_col)
        p.drawEllipse(lsx-6, lsy-6, 12, 12)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        p.drawText(lsx-4, lsy+4, "L")   # L = Ligand

        # 결합 포켓 레이블
        p.setPen(gc.lighter(170))
        p.setFont(QFont("Arial", 8))
        p.drawText(lsx-pocket_r, lsy-pocket_r-12, "결합 포켓 (15Å)")

        # ── 리간드 2D 구조 이미지 (우상단) ───────────────────────────
        img_x = w - 138
        if self._ligand_img and not self._ligand_img.isNull():
            from PyQt6.QtGui import QPixmap
            from PyQt6.QtCore import QRect
            pm = QPixmap.fromImage(self._ligand_img)
            p.drawPixmap(QRect(img_x, 6, 128, 96), pm)
            p.setPen(QPen(QColor(100, 130, 160), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(img_x-1, 5, 130, 98)
            p.setPen(QColor(160, 200, 220))
            p.setFont(QFont("Arial", 7))
            p.drawText(img_x+10, 106, "리간드 구조")
        else:
            # 텍스트 대체
            p.setPen(QColor(100, 170, 220))
            p.setFont(QFont("Arial", 7))
            smiles_disp = (self._ligand_smiles[:22] + "…"
                           if len(self._ligand_smiles) > 22
                           else self._ligand_smiles)
            p.drawText(img_x, 20, smiles_disp)

        # ── 에너지 표시 (좌하단) ─────────────────────────────────────
        if self._docking_energy is not None:
            p.setPen(gc.lighter(170))
            p.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            p.drawText(pad, h-30, f"ΔG = {self._docking_energy:+.2f} kcal/mol")

        # ── 하단 범례 ────────────────────────────────────────────────
        legend_items = [
            (QColor(70, 70, 95),  "수용체 Cα"),
            (gc,                   f"결합 포켓 ({len(self._pocket_atoms)}개)"),
        ]
        lx_base = pad + 220
        for i, (lc, lt) in enumerate(legend_items):
            lx = lx_base + i * 130
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(lc)
            p.drawEllipse(lx, h-20, 10, 10)
            p.setPen(QColor(170, 170, 185))
            p.setFont(QFont("Arial", 8))
            p.drawText(lx+14, h-9, lt)

        # 원자 수 안내
        p.setPen(QColor(80, 80, 100))
        p.setFont(QFont("Arial", 7))
        p.drawText(pad, h-10,
                   f"총 Cα: {len(self._receptor_atoms)}  |  포켓 내: {len(self._pocket_atoms)}")
        p.end()


# ============================================================
# Section 10-5: GABA 수용체 도킹 에너지 임계값 패널
# ============================================================

class DockingEnergyPanel(QWidget):
    """🧬 도킹 탭 — RCSB PDB 수용체 검색 + 분자 도킹 시뮬레이션

    기능:
    1. RCSB PDB 검색으로 수용체 단백질 선택 및 다운로드
    2. 프리셋 수용체 목록 (GABA-A, ACE2, COX-2 등)
    3. 경험적 결합 에너지 예측 (Vina 점수 함수 근사)
    4. 결합 등급 평가 및 임상 약물 비교
    5. 3D 시각화 (리간드+수용체 Cα 백본)
    """

    # 프리셋 수용체 목록
    PRESET_RECEPTORS = [
        ("GABA-A (α1β2γ2)",   "6X3S", "GABA 수용체 — 벤조디아제핀 결합 부위"),
        ("ACE2 (COVID-19)",    "6M0J", "SARS-CoV-2 스파이크 단백질 수용체"),
        ("COX-2 (NSAIDs)",     "5IKT", "프로스타글란딘 합성효소 — 소염진통제"),
        ("Thrombin (혈액응고)", "3U69", "혈액응고 효소 — 항응고제 표적"),
        ("EGFR (항암)",        "1IVO", "표피성장인자 수용체 — 항암제 표적"),
        ("Beta-2 (천식)",      "3NY8", "β2 아드레날린 수용체 — 기관지 확장"),
        ("HIV Protease",       "3OXC", "HIV 단백질분해효소 — 항바이러스"),
        ("Acetylcholinesterase","4EY7", "아세틸콜린에스터라아제 — 알츠하이머"),
    ]

    # 결합 에너지 임계값
    THRESHOLDS = [
        (-99.0, -12.0, "매우 강한 결합", "#e74c3c", "Ki < 1 μM"),
        (-12.0,  -8.0, "강한 결합",     "#e67e22", "Ki 1–100 μM"),
        (-8.0,   -5.0, "중간 결합",     "#f1c40f", "Ki 0.1–10 mM"),
        (-5.0,   -2.0, "약한 결합",     "#27ae60", "Ki > 10 mM"),
        (-2.0,   99.0, "비결합",        "#95a5a6", "결합 에너지 부족"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smiles: str = ""
        self._current_pdb_id: str = ""
        self._receptor_atoms: List = []       # [(sym, x, y, z)] Cα 백본
        self._docking_energy: Optional[float] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("🧬 분자 도킹 — RCSB PDB 수용체 선택 + 결합 에너지 예측")
        title.setStyleSheet("font-size:11pt; color:#90CAF9; font-weight:bold;")
        layout.addWidget(title)

        # ── [1] 수용체 선택 섹션 ─────────────────────────────────────
        recv_grp = QGroupBox("🔍 수용체 단백질 선택")
        recv_layout = QVBoxLayout()
        recv_layout.setSpacing(4)

        # RCSB 검색 바
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("PDB ID 또는 단백질명:"))
        self.search_input = QTextEdit()
        self.search_input.setFixedHeight(30)
        self.search_input.setPlaceholderText("예: 6X3S  또는  GABA receptor")
        self.search_input.setStyleSheet(
            "background:#252525; color:#ddd; border:1px solid #555; "
            "font-size:10pt; padding:2px 4px;")
        search_row.addWidget(self.search_input)
        btn_search = QPushButton("🔍 검색")
        btn_search.setFixedHeight(30)
        btn_search.setFixedWidth(70)
        btn_search.setStyleSheet(
            "QPushButton { background:#1565C0; color:white; border:1px solid #42A5F5; "
            "border-radius:3px; font-size:9pt; }"
            "QPushButton:hover { background:#1976D2; }")
        btn_search.clicked.connect(self._search_pdb)
        search_row.addWidget(btn_search)
        recv_layout.addLayout(search_row)

        # 프리셋 콤보박스
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("📋 프리셋:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setStyleSheet(
            "QComboBox { background:#2a2a2a; color:#ddd; border:1px solid #555; "
            "padding:3px; font-size:9pt; }")
        self.preset_combo.addItem("— 수용체 선택 —")
        for name, pdb_id, desc in self.PRESET_RECEPTORS:
            self.preset_combo.addItem(f"{pdb_id}  {name}")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self.preset_combo, 1)
        recv_layout.addLayout(preset_row)

        # 검색 결과 목록
        recv_layout.addWidget(QLabel("검색 결과:"))
        self.result_list = QListWidget()
        self.result_list.setMaximumHeight(80)
        self.result_list.setStyleSheet(
            "QListWidget { background:#252525; color:#ddd; border:1px solid #444; "
            "font-size:9pt; } "
            "QListWidget::item:selected { background:#1565C0; }")
        self.result_list.itemClicked.connect(self._on_result_selected)
        recv_layout.addWidget(self.result_list)

        # 수용체 정보 표시
        self.receptor_info = QLabel("— 수용체를 선택하세요 —")
        self.receptor_info.setStyleSheet("color:#888; font-size:8pt; padding:2px;")
        self.receptor_info.setWordWrap(True)
        recv_layout.addWidget(self.receptor_info)

        # 수용체 로드 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_load_receptor = QPushButton("📥 수용체 로드 (RCSB 다운로드)")
        self.btn_load_receptor.setEnabled(False)
        self.btn_load_receptor.setStyleSheet(
            "QPushButton { background:#2E7D32; color:#A5D6A7; border:1px solid #43A047; "
            "border-radius:3px; padding:4px 12px; font-size:9pt; }"
            "QPushButton:hover { background:#388E3C; }"
            "QPushButton:disabled { background:#333; color:#666; }")
        self.btn_load_receptor.clicked.connect(self._load_receptor)
        btn_row.addWidget(self.btn_load_receptor)
        recv_layout.addLayout(btn_row)
        recv_grp.setLayout(recv_layout)
        layout.addWidget(recv_grp)

        # ── [2] 도킹 시뮬레이션 ──────────────────────────────────────
        dock_grp = QGroupBox("⚗ 도킹 시뮬레이션")
        dock_layout = QVBoxLayout()
        dock_layout.setSpacing(4)

        dock_btn_row = QHBoxLayout()
        self.btn_dock = QPushButton("🔬 도킹 시뮬레이션 실행")
        self.btn_dock.setEnabled(False)
        self.btn_dock.setStyleSheet(
            "QPushButton { background:#880E4F; color:#F48FB1; border:1px solid #C2185B; "
            "border-radius:3px; padding:5px 14px; font-size:10pt; font-weight:bold; }"
            "QPushButton:hover { background:#AD1457; }"
            "QPushButton:disabled { background:#333; color:#666; }")
        self.btn_dock.clicked.connect(self._run_docking)
        dock_btn_row.addWidget(self.btn_dock)
        dock_btn_row.addStretch()
        dock_layout.addLayout(dock_btn_row)

        self.dock_result = QTextEdit()
        self.dock_result.setReadOnly(True)
        self.dock_result.setMinimumHeight(80)
        self.dock_result.setMaximumHeight(120)
        self.dock_result.setStyleSheet(
            "QTextEdit { background:#252525; color:#A5D6A7; font-size:9pt; "
            "border:1px solid #333; font-family:monospace; }")
        self.dock_result.setPlainText(
            "수용체를 로드하고 [🔬 도킹 시뮬레이션 실행] 버튼을 클릭하세요.\n"
            "리간드(현재 분자)와 수용체의 결합 에너지를 예측합니다.")
        dock_layout.addWidget(self.dock_result)
        dock_grp.setLayout(dock_layout)
        layout.addWidget(dock_grp)

        # ── [3] 결합 등급 결과 ────────────────────────────────────────
        self.grade_lbl = QLabel("— 도킹 실행 후 결합 등급이 표시됩니다 —")
        self.grade_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grade_lbl.setStyleSheet(
            "font-size:12pt; color:#bbb; padding:8px; border:2px dashed #444; "
            "border-radius:6px; background:#252525;")
        self.grade_lbl.setWordWrap(True)
        layout.addWidget(self.grade_lbl)

        # ── [4] 임계값 참조표 (접기 가능) ────────────────────────────
        thresh_grp = QGroupBox("📊 결합 등급 기준표 (AutoDock Vina 기준)")
        thresh_layout = QVBoxLayout()
        for lo, hi, label, color, ki in self.THRESHOLDS:
            row = QHBoxLayout()
            badge = QLabel("  ")
            badge.setFixedSize(14, 14)
            badge.setStyleSheet(f"background:{color}; border-radius:2px;")
            row.addWidget(badge)
            lo_s = "-∞" if lo < -90 else f"{lo:.0f}"
            hi_s = "∞" if hi > 90 else f"{hi:.0f}"
            row.addWidget(QLabel(f"{lo_s}~{hi_s} kcal/mol"))
            lbl_w = QLabel(f"[{label}]")
            lbl_w.setStyleSheet(f"color:{color}; font-weight:bold; font-size:9pt;")
            lbl_w.setFixedWidth(85)
            row.addWidget(lbl_w)
            row.addWidget(QLabel(ki))
            row.addStretch()
            thresh_layout.addLayout(row)
        thresh_grp.setLayout(thresh_layout)
        layout.addWidget(thresh_grp)

        # ── [DOCK-2] 결합 포켓 2D 시각화 위젯 ────────────────────────
        viz_grp = QGroupBox("🗺 결합 포켓 시각화 (수용체 Cα + 리간드)")
        viz_grp_layout = QVBoxLayout()
        viz_grp_layout.setContentsMargins(4, 4, 4, 4)
        self.viz_widget = DockingVisualizationWidget()
        viz_grp_layout.addWidget(self.viz_widget)
        viz_grp.setLayout(viz_grp_layout)
        layout.addWidget(viz_grp)

        layout.addStretch()
        self.setLayout(layout)

    # ── RCSB PDB 검색 ─────────────────────────────────────────────────
    def _search_pdb(self):
        """RCSB PDB REST API로 수용체 검색"""
        query = self.search_input.toPlainText().strip()
        if not query:
            return
        self.result_list.clear()
        self.result_list.addItem("🔄 검색 중...")
        QApplication.processEvents()

        if not REQUESTS_AVAILABLE:
            self.result_list.clear()
            self.result_list.addItem("⚠️ requests 미설치 — pip install requests")
            return

        # PDB ID 직접 입력 (4자리 영숫자)
        if re.match(r'^[A-Za-z0-9]{4}$', query):
            self.result_list.clear()
            item = QListWidgetItem(f"📌 {query.upper()}  (PDB ID 직접 입력)")
            item.setData(Qt.ItemDataRole.UserRole, query.upper())
            self.result_list.addItem(item)
            self._current_pdb_id = query.upper()
            self.btn_load_receptor.setEnabled(True)
            self.receptor_info.setText(f"PDB ID: {query.upper()}  — RCSB에서 구조 다운로드 가능")
            return

        # RCSB Full-text 검색
        try:
            search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
            payload = {
                "query": {
                    "type": "terminal",
                    "service": "full_text",
                    "parameters": {"value": query}
                },
                "return_type": "entry",
                "request_options": {"results_slice": {"start": 0, "rows": 10},
                                    "sort": [{"sort_by": "score", "direction": "desc"}]}
            }
            resp = requests.post(search_url, json=payload, timeout=8)
            self.result_list.clear()

            if resp.status_code != 200:
                self.result_list.addItem(f"⚠️ 검색 실패 (HTTP {resp.status_code})")
                return

            data = resp.json()
            entries = data.get("result_set", [])
            if not entries:
                self.result_list.addItem("검색 결과 없음")
                return

            for entry in entries[:8]:
                pdb_id = entry.get("identifier", "?")
                score = entry.get("score", 0)
                item = QListWidgetItem(f"🔬 {pdb_id}  (score: {score:.2f})")
                item.setData(Qt.ItemDataRole.UserRole, pdb_id)
                self.result_list.addItem(item)
        except Exception as e:
            self.result_list.clear()
            self.result_list.addItem(f"⚠️ 검색 오류: {str(e)[:50]}")

    def _on_result_selected(self, item: QListWidgetItem):
        pdb_id = item.data(Qt.ItemDataRole.UserRole) or ""
        if pdb_id:
            self._current_pdb_id = pdb_id
            self.btn_load_receptor.setEnabled(True)
            self.receptor_info.setText(f"선택: PDB {pdb_id}  — [📥 수용체 로드] 버튼으로 다운로드")

    def _on_preset_selected(self, idx: int):
        if idx <= 0:
            return
        name, pdb_id, desc = self.PRESET_RECEPTORS[idx - 1]
        self._current_pdb_id = pdb_id
        self.btn_load_receptor.setEnabled(True)
        self.receptor_info.setText(f"PDB {pdb_id}: {name}\n{desc}")

    def _load_receptor(self):
        """RCSB에서 PDB 파일 다운로드 + Cα 백본 파싱"""
        if not self._current_pdb_id:
            return
        if not REQUESTS_AVAILABLE:
            self.receptor_info.setText("⚠️ requests 미설치")
            return

        pdb_id = self._current_pdb_id
        self.receptor_info.setText(f"🔄 {pdb_id} 다운로드 중 (RCSB PDB)...")
        QApplication.processEvents()

        try:
            url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                self.receptor_info.setText(f"⚠️ 다운로드 실패 (HTTP {resp.status_code})")
                return

            # Cα 백본 파싱
            ca_atoms = []
            for line in resp.text.split('\n'):
                if line.startswith('ATOM') and line[12:16].strip() == 'CA':
                    try:
                        x = float(line[30:38])
                        y = float(line[38:46])
                        z = float(line[46:54])
                        chain = line[21]
                        res = line[17:20].strip()
                        ca_atoms.append((res, x, y, z, chain))
                    except (ValueError, IndexError):
                        pass

            self._receptor_atoms = ca_atoms
            n_chains = len(set(a[4] for a in ca_atoms))
            self.receptor_info.setText(
                f"✅ {pdb_id} 로드 완료  |  Cα 원자: {len(ca_atoms)}개  |  체인: {n_chains}개")
            self.btn_dock.setEnabled(True)

            # PDB 파일 로컬 저장 (선택적)
            cache_dir = _SCRIPT_DIR / "pdb_cache"
            cache_dir.mkdir(exist_ok=True)
            pdb_path = cache_dir / f"{pdb_id}.pdb"
            pdb_path.write_text(resp.text, encoding='utf-8')
            logger.info(f"PDB saved: {pdb_path}")

        except Exception as e:
            self.receptor_info.setText(f"⚠️ 다운로드 오류: {str(e)[:60]}")

    # ── 경험적 도킹 시뮬레이션 ─────────────────────────────────────────
    def _run_docking(self):
        """경험적 결합 에너지 예측 (Vina 점수함수 근사, 실제 AutoDock 없이)"""
        if not self._smiles:
            self.dock_result.setPlainText("⚠️ 리간드(분자) SMILES 없음 — 분자를 먼저 로드하세요")
            return
        if not self._receptor_atoms:
            self.dock_result.setPlainText("⚠️ 수용체 미로드 — [📥 수용체 로드] 먼저 실행하세요")
            return

        self.btn_dock.setEnabled(False)
        self.dock_result.setPlainText("🔄 도킹 시뮬레이션 중...")
        QApplication.processEvents()

        try:
            energy = self._empirical_docking_score()
            self._docking_energy = energy
            self._show_docking_result(energy)
        except Exception as e:
            self.dock_result.setPlainText(f"⚠️ 도킹 오류: {e}")
        finally:
            self.btn_dock.setEnabled(True)

    def _empirical_docking_score(self) -> float:
        """Vina 점수함수 근사 계산 — RDKit 분자 특성 기반.

        근사식 (Vina simplified):
        ΔG ≈ w_hb*N_hb + w_hydro*logP + w_rot*N_rot + w_size*N_atoms + baseline
        """
        if not RDKIT_AVAILABLE:
            # 기본 추정 (-8.0 ± 2.0)
            return -8.0

        mol = Chem.MolFromSmiles(self._smiles)
        if mol is None:
            return -8.0

        # 분자 특성 계산
        n_hbd = Descriptors.NumHDonors(mol)      # H-bond donors
        n_hba = Descriptors.NumHAcceptors(mol)   # H-bond acceptors
        logp  = Descriptors.MolLogP(mol)          # lipophilicity
        n_rot = Descriptors.NumRotatableBonds(mol)# flexibility penalty
        mw    = Descriptors.MolWt(mol)
        n_ar  = rdMolDescriptors.CalcNumAromaticRings(mol)
        n_atoms = mol.GetNumHeavyAtoms()

        # 수용체별 보정 인자 (문헌 기반 가중치)
        pdb_factors = {
            "6X3S": {"hb_w": -0.9, "hydro_w": -0.5, "baseline": -4.5},   # GABA-A (극성 포켓)
            "6M0J": {"hb_w": -0.7, "hydro_w": -0.6, "baseline": -5.0},   # ACE2
            "5IKT": {"hb_w": -0.8, "hydro_w": -0.7, "baseline": -5.5},   # COX-2 (소수성)
            "3U69": {"hb_w": -1.0, "hydro_w": -0.4, "baseline": -4.0},   # Thrombin
            "1IVO": {"hb_w": -0.6, "hydro_w": -0.8, "baseline": -5.2},   # EGFR
        }
        f = pdb_factors.get(self._current_pdb_id,
                            {"hb_w": -0.8, "hydro_w": -0.6, "baseline": -4.5})

        score = (f["hb_w"] * (n_hbd + n_hba)
                 + f["hydro_w"] * max(0, logp)
                 - 0.15 * n_rot
                 - 0.05 * max(0, n_atoms - 20)
                 + 0.3 * n_ar
                 + f["baseline"])

        # 분자량 보정 (너무 작거나 큰 분자 페널티)
        if mw < 150:
            score *= 0.7
        elif mw > 500:
            score *= 0.85

        return round(score, 2)

    def _show_docking_result(self, energy: float):
        """도킹 결과 표시"""
        # 등급 판정
        grade_label, grade_color, grade_ki = "비결합", "#95a5a6", ""
        for lo, hi, label, color, ki in self.THRESHOLDS:
            if lo <= energy < hi:
                grade_label, grade_color, grade_ki = label, color, ki
                break

        # 결과 텍스트
        lines = [
            f"═══════ 도킹 결과 ({self._current_pdb_id}) ═══════",
            f"예측 결합 에너지:  ΔG = {energy:+.2f} kcal/mol",
            f"결합 등급:  {grade_label}  ({grade_ki})",
            f"─────────────────────────────────",
            f"리간드: {self._smiles[:40]}{'...' if len(self._smiles)>40 else ''}",
            f"수용체 Cα 원자 수: {len(self._receptor_atoms)}개",
            f"─────────────────────────────────",
        ]
        # 임상 약물 비교 (프리셋 수용체일 때)
        preset_drug_map = {
            "6X3S": [("Diazepam", -10.5), ("Zolpidem", -11.2)],
            "6M0J": [("Remdesivir", -9.8)],
            "5IKT": [("Celecoxib", -10.2), ("Ibuprofen", -7.8)],
        }
        refs = preset_drug_map.get(self._current_pdb_id, [])
        if refs:
            lines.append("참조 약물 비교:")
            for drug, ref_e in refs:
                diff = energy - ref_e
                sign = "↑ 강함" if diff < 0 else "↓ 약함"
                lines.append(f"  vs {drug}: {diff:+.1f} kcal/mol ({sign})")

        lines.append("─────────────────────────────────")
        lines.append("⚠️ 경험적 근사값 — 실제 도킹은 AutoDock Vina 권장")

        self.dock_result.setPlainText("\n".join(lines))

        # 결합 등급 레이블
        self.grade_lbl.setText(
            f"ΔG = {energy:+.2f} kcal/mol  →  {grade_label}  ({grade_ki})")
        self.grade_lbl.setStyleSheet(
            f"font-size:12pt; color:{grade_color}; padding:8px; "
            f"border:2px solid {grade_color}; border-radius:6px; "
            f"background:#1a1a1a; font-weight:bold;")

        # [DOCK-2] 결합 포켓 시각화 위젯 업데이트
        if hasattr(self, 'viz_widget'):
            self.viz_widget.update_docking(
                self._receptor_atoms, self._smiles, energy, grade_color)

    def set_molecule_smiles(self, smiles: str):
        self._smiles = smiles
        if smiles and self._receptor_atoms:
            self.btn_dock.setEnabled(True)

    def update_from_orca(self, parser: OrcaOutputParser):
        if parser and parser.total_energy is not None:
            e_kcal = parser.total_energy * 627.509
            self.dock_result.setPlainText(
                f"ORCA DFT 절대 에너지: {parser.total_energy:.6f} Eh ({e_kcal:.1f} kcal/mol)\n"
                "⚠️ 도킹 ΔG ≠ DFT 절대 에너지. 위 도킹 버튼을 사용하세요.")


# ============================================================
# Section 11: Main Integrated Popup
# ============================================================

class Molecule3DPopup(QWidget):
    """
    통합 3D 분석 팝업.
    상단: 3D 뷰어 + 컨트롤
    하단: 탭 패널 [📊 속성] [📈 스펙트럼] [🎵 진동모드] [📝 AI분석]
    """

    def __init__(self, mol_data: Molecule3DData, parent=None):
        super().__init__(parent)
        # ★ 독립 최상위 창으로 설정 — 이동/최소화/최대화/닫기 모두 가능
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.mol_data = mol_data
        self.orca_parser = mol_data.orca_parser if mol_data else None
        self.viewer = None
        self.pubchem = PubChemClient()
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        self.setWindowTitle("ChemGrid — 통합 3D 분자 분석")
        self.setGeometry(120, 80, 1100, 860)
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QPushButton {
                background-color: #333; border: 1px solid #555;
                padding: 5px 12px; border-radius: 3px; color: #e0e0e0;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:checked { background-color: #2979ff; border-color: #2979ff; }
            QLabel { color: #bbb; }
            QSlider::groove:horizontal { height: 6px; background: #444; border-radius: 3px; }
            QSlider::handle:horizontal {
                background: #2979ff; width: 14px; margin: -4px 0; border-radius: 7px;
            }
            QGroupBox {
                border: 1px solid #444; border-radius: 4px;
                margin-top: 8px; padding-top: 16px; color: #ccc;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            QTabWidget::pane { border: 1px solid #444; background: #1e1e1e; }
            QTabBar::tab {
                background: #2a2a2a; border: 1px solid #444;
                padding: 6px 16px; margin-right: 2px; color: #bbb;
            }
            QTabBar::tab:selected { background: #333; color: #fff; border-bottom: 2px solid #2979ff; }
            QListWidget { background: #252525; color: #ddd; border: 1px solid #444; }
            QTextEdit { border: 1px solid #444; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # === Top control bar ===
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        ctrl.addWidget(QLabel("Model:"))

        self.btn_bs = QPushButton("⚛ Ball && Stick")
        self.btn_bs.setCheckable(True)
        self.btn_bs.setChecked(True)
        self.btn_bs.clicked.connect(lambda: self._set_mode("ball_and_stick"))
        ctrl.addWidget(self.btn_bs)

        self.btn_sf = QPushButton("🔵 Space Filling")
        self.btn_sf.setCheckable(True)
        self.btn_sf.clicked.connect(lambda: self._set_mode("space_filling"))
        ctrl.addWidget(self.btn_sf)

        # [CHEM-8] 오비탈 모드 선택 콤보박스
        ctrl.addWidget(QLabel("오비탈:"))
        self.orbital_combo = QComboBox()
        self.orbital_combo.setToolTip(
            "[CHEM-6/8] 오비탈 표시 모드\n"
            "• π 오비탈: sp2/방향족 π cloud (CHEM-6)\n"
            "• 혼성 오비탈: sp/sp2/sp3/sp3d/sp3d2 (CHEM-8)\n"
            "• d 오비탈: 전이금속 t₂g/eg Crystal Field (CHEM-8)\n"
            "• f 오비탈: 란타나이드/악티나이드 cubic lobes (CHEM-8)\n"
            "• 전체: 모든 오비탈 동시 표시"
        )
        self.orbital_combo.addItems([
            "오비탈 없음",
            "🌀 π 오비탈 (sp2)",
            "⚗ 혼성 오비탈 (자동)",
            "⚛ d 오비탈 (전이금속)",
            "✦ f 오비탈 (란타나이드)",
            "🌐 전체 오비탈",
        ])
        self.orbital_combo.setStyleSheet("QComboBox { background: #2a2a2a; color: #ddd; "
                                         "border: 1px solid #555; padding: 4px; min-width: 150px; }")
        self.orbital_combo.currentIndexChanged.connect(self._on_orbital_mode_changed)
        ctrl.addWidget(self.orbital_combo)

        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.valueChanged.connect(self._on_zoom)
        ctrl.addWidget(self.zoom_slider)
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setFixedWidth(40)
        ctrl.addWidget(self.zoom_lbl)

        ctrl.addStretch()

        # ORCA file loader
        btn_orca = QPushButton("📂 ORCA 로드")
        btn_orca.clicked.connect(self._load_orca_file)
        ctrl.addWidget(btn_orca)

        btn_reset = QPushButton("↺ Reset")
        btn_reset.clicked.connect(self._reset_view)
        ctrl.addWidget(btn_reset)

        # 💾 내보내기 버튼 — XYZ/ORCA/Gaussian/MOL 다중 형식 지원
        self.btn_export = QPushButton("💾 내보내기")
        self.btn_export.setToolTip(
            "3D 구조를 파일로 저장\n"
            "• XYZ  — ORCA/Avogadro/VMD\n"
            "• ORCA .inp — DFT 계산 템플릿\n"
            "• Gaussian .gjf — GaussView\n"
            "• MDL .mol — Avogadro/ChemDraw"
        )
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #1B5E20;
                border: 1px solid #43A047;
                color: #A5D6A7;
                padding: 5px 12px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #2E7D32; }
        """)
        self.btn_export.clicked.connect(self._export_3d_structure)
        ctrl.addWidget(self.btn_export)

        main_layout.addLayout(ctrl)

        # === Splitter: Viewer (top) + Tabs (bottom) ===
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Viewer
        if OPENGL_AVAILABLE:
            self.viewer = Molecule3DViewer(self.mol_data)
        else:
            self.viewer = FallbackRenderer2D(self.mol_data)
        splitter.addWidget(self.viewer)

        # Tab panel
        self.tabs = QTabWidget()
        self.tab_props = PropertiesPanel()
        self.tab_spectrum = SpectrumPanel()
        self.tab_vibration = VibrationPanel()
        self.tab_ai = AIAnalysisPanel()

        self.tab_docking = DockingEnergyPanel()
        self.tabs.addTab(self.tab_props, "📊 속성")
        self.tabs.addTab(self.tab_spectrum, "📈 스펙트럼")
        self.tabs.addTab(self.tab_vibration, "🎵 진동모드")
        self.tabs.addTab(self.tab_ai, "📝 AI분석")
        self.tabs.addTab(self.tab_docking, "🧬 도킹 에너지")

        splitter.addWidget(self.tabs)
        splitter.setSizes([500, 300])  # initial split

        main_layout.addWidget(splitter, 1)

        # === Bottom info bar ===
        info = QHBoxLayout()
        backend = "OpenGL" if OPENGL_AVAILABLE else "QPainter 2.5D"
        self.info_lbl = QLabel(
            f"Atoms: {self.mol_data.num_atoms}  |  "
            f"Bonds: {self.mol_data.num_bonds}  |  "
            f"좌표: {self.mol_data.coord_source}  |  "
            f"Backend: {backend}"
        )
        info.addWidget(self.info_lbl)
        info.addStretch()
        help_lbl = QLabel("Left: Rotate  |  Right: Pan  |  Wheel: Zoom")
        help_lbl.setStyleSheet("color: #666; font-size: 8pt;")
        info.addWidget(help_lbl)
        main_layout.addLayout(info)

        self.setLayout(main_layout)

        # === Connect vibration signals ===
        self.tab_vibration.mode_selected.connect(self._on_vib_mode_selected)
        self.tab_vibration.animation_toggled.connect(self._on_vib_toggle)

    def _load_data(self):
        """초기 데이터 로드 (RDKit, PubChem, ORCA)"""
        smiles = self.mol_data.smiles or ""

        # Properties tab — RDKit
        self.tab_props.update_rdkit(smiles)
        self.tab_props.update_measurements(self.mol_data)

        # Properties tab — PubChem (threaded)
        if smiles and REQUESTS_AVAILABLE:
            def _fetch():
                data = self.pubchem.lookup_by_smiles(smiles)
                return data
            # Simple sync for now (could be threaded)
            try:
                pub_data = _fetch()
                self.tab_props.update_pubchem(pub_data, smiles)  # [신규] smiles 전달
            except Exception:
                self.tab_props.update_pubchem(None, smiles)
        else:
            self.tab_props.update_pubchem(None, smiles)

        # ORCA data
        if self.orca_parser:
            self._apply_orca_data(self.orca_parser)

        # [SPEC-1] ORCA 없을 때 SMILES 기반 예측 스펙트럼 자동 표시
        if not self.orca_parser and smiles:
            try:
                self.tab_spectrum.load_predicted(smiles)
            except Exception as _e:
                logger.debug(f"Predicted spectrum skipped: {_e}")

        # AI tab
        orca_info = {}
        if self.orca_parser:
            orca_info["energy"] = self.orca_parser.total_energy
            orca_info["dipole"] = self.orca_parser.dipole_moment
        self.tab_ai.set_data(smiles, {}, orca_info)

        # [FIX-DOCKING-SMILES] 도킹 탭에 SMILES 전달 (이전에 누락됨)
        self.tab_docking.set_molecule_smiles(smiles)

    def _apply_orca_data(self, parser: OrcaOutputParser):
        """ORCA 파서 결과를 모든 탭에 적용"""
        self.orca_parser = parser
        self.tab_props.update_orca(parser)

        if parser.frequencies:
            self.tab_spectrum.plot_ir(parser.frequencies, parser.ir_intensities)
            self.tab_vibration.load_modes(parser.frequencies, parser.ir_intensities)

    def _load_orca_file(self):
        """ORCA .out 파일 로드 다이얼로그"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "ORCA Output 파일 열기", "",
            "ORCA Output (*.out *.log);;All Files (*)")
        if not filepath:
            return

        parser = OrcaOutputParser(filepath=filepath)
        if parser.atoms:
            # Update molecule data with ORCA geometry
            self.mol_data = Molecule3DData(
                atoms=self.mol_data.atoms,
                bonds=self.mol_data.bonds,
                theory_data=self.mol_data.theory_data,
                smiles=self.mol_data.smiles,
                orca_parser=parser
            )
            self.viewer.set_mol_data(self.mol_data)
            self.info_lbl.setText(
                f"Atoms: {self.mol_data.num_atoms}  |  "
                f"Bonds: {self.mol_data.num_bonds}  |  "
                f"좌표: {self.mol_data.coord_source}  |  "
                f"ORCA: {'✅ 수렴' if parser.converged else '⚠️'}")
            self.tab_props.update_measurements(self.mol_data)

        self._apply_orca_data(parser)

    def _on_orbital_mode_changed(self, index: int):
        """[CHEM-8] 오비탈 모드 콤보 변경 핸들러."""
        MODE_MAP = {
            0: 'none',
            1: 'pi',
            2: 'hybrid',
            3: 'd_orbital',
            4: 'f_orbital',
            5: 'all',
        }
        mode = MODE_MAP.get(index, 'none')
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.set_orbital_mode(mode)

    def _toggle_pi_orbitals(self, checked):
        """[CHEM-6] 하위호환 — 콤보박스 연동."""
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.set_pi_orbitals(checked)

    def _set_mode(self, mode):
        if self.viewer:
            self.viewer.render_mode = mode
            self.viewer.update()
        self.btn_bs.setChecked(mode == "ball_and_stick")
        self.btn_sf.setChecked(mode == "space_filling")

    def _on_zoom(self, val):
        self.zoom_lbl.setText(f"{val}%")
        if self.viewer:
            self.viewer.zoom_scale = val / 100.0
            self.viewer.update()

    def _reset_view(self):
        if self.viewer:
            self.viewer.reset_view()
        self.zoom_slider.setValue(100)

    def _on_vib_mode_selected(self, mode_idx):
        """진동 모드 선택 시 뷰어에 벡터 즉시 표시 (play 버튼 불필요)"""
        if (self.orca_parser and mode_idx < len(self.orca_parser.normal_modes)
                and isinstance(self.viewer, Molecule3DViewer)):
            vectors = self.orca_parser.normal_modes[mode_idx]
            amp = self.tab_vibration.amp_slider.value() / 100.0
            # [FIX-VIB] 모드 선택 즉시 시작 — play 버튼 상태 무관
            self.viewer.start_vibration(vectors, amp)
            self.tab_vibration.btn_play.setChecked(True)
            self.tab_vibration.btn_play.setText("⏸ 정지")

    def _on_vib_toggle(self, play):
        """진동 애니메이션 재생/정지"""
        if not isinstance(self.viewer, Molecule3DViewer):
            return
        if play:
            row = self.tab_vibration.mode_list.currentRow()
            if (self.orca_parser and row >= 0
                    and row < len(self.orca_parser.normal_modes)):
                vectors = self.orca_parser.normal_modes[row]
                amp = self.tab_vibration.amp_slider.value() / 100.0
                self.viewer.start_vibration(vectors, amp)
        else:
            self.viewer.stop_vibration()

    def _export_3d_structure(self):
        """💾 3D 구조 내보내기 — XYZ / ORCA .inp / Gaussian .gjf / MDL .mol 형식 선택"""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QMessageBox

        if not self.mol_data or self.mol_data.num_atoms == 0:
            QMessageBox.warning(self, "내보내기 불가", "⚠️ 분자 데이터가 없습니다.\n먼저 분자를 그리거나 ORCA 파일을 로드하세요.")
            return

        # ── 형식 선택 다이얼로그 ──
        dialog = QDialog(self)
        dialog.setWindowTitle("💾 내보내기 형식 선택")
        dialog.setFixedSize(360, 260)
        dialog.setStyleSheet("""
            QDialog { background: #1e1e1e; color: #e0e0e0; }
            QLabel { color: #bbb; }
            QRadioButton { color: #ddd; padding: 6px; font-size: 11pt; }
            QRadioButton:checked { color: #A5D6A7; }
            QDialogButtonBox QPushButton {
                background: #2E7D32; color: #A5D6A7; border: 1px solid #43A047;
                padding: 5px 20px; border-radius: 3px;
            }
            QDialogButtonBox QPushButton:hover { background: #388E3C; }
        """)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(16, 16, 16, 12)
        d_layout.setSpacing(6)

        title_lbl = QLabel("저장할 파일 형식을 선택하세요:")
        title_lbl.setStyleSheet("font-size: 10pt; color: #90CAF9; margin-bottom: 6px;")
        d_layout.addWidget(title_lbl)

        formats = [
            ("xyz",  "📐 XYZ (.xyz)  — ORCA / Avogadro / VMD 호환"),
            ("orca", "⚛ ORCA 입력 (.inp)  — DFT 계산 템플릿 (설명_오비탈 기준)"),
            ("gjf",  "🔬 Gaussian 입력 (.gjf)  — GaussView 호환"),
            ("mol",  "🧪 MDL MOL (.mol)  — Avogadro / ChemDraw 호환"),
        ]
        radio_map: Dict[str, QRadioButton] = {}
        btn_group = QButtonGroup(dialog)
        for i, (fmt, label) in enumerate(formats):
            rb = QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            btn_group.addButton(rb)
            d_layout.addWidget(rb)
            radio_map[fmt] = rb

        # 좌표 출처 표시
        src_lbl = QLabel(f"좌표 출처: {self.mol_data.coord_source}  |  원자: {self.mol_data.num_atoms}개")
        src_lbl.setStyleSheet("color: #888; font-size: 8pt; margin-top: 6px;")
        d_layout.addWidget(src_lbl)

        d_layout.addStretch()
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        d_layout.addWidget(btn_box)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # 선택된 형식 파악
        selected_fmt = "xyz"
        for fmt, rb in radio_map.items():
            if rb.isChecked():
                selected_fmt = fmt
                break

        ext_filter = {
            "xyz":  "XYZ Files (*.xyz);;All Files (*)",
            "orca": "ORCA Input (*.inp);;All Files (*)",
            "gjf":  "Gaussian Input (*.gjf);;All Files (*)",
            "mol":  "MDL MOL (*.mol);;All Files (*)",
        }
        default_name = f"molecule.{selected_fmt}"
        smiles_part = (self.mol_data.smiles or "").replace("/", "").replace("\\", "")[:20]
        if smiles_part:
            default_name = f"{smiles_part}.{selected_fmt}"

        filepath, _ = QFileDialog.getSaveFileName(
            self, "💾 3D 구조 내보내기", default_name, ext_filter[selected_fmt])
        if not filepath:
            return

        try:
            if selected_fmt == "xyz":
                content = self.mol_data.export_xyz()
            elif selected_fmt == "orca":
                content = self.mol_data.export_orca_inp()
            elif selected_fmt == "gjf":
                content = self.mol_data.export_gjf()
            elif selected_fmt == "mol":
                content = self.mol_data.export_mol()
            else:
                content = self.mol_data.export_xyz()

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            # 성공 메시지 (상태바에도 반영)
            QMessageBox.information(
                self, "✅ 내보내기 완료",
                f"파일이 저장되었습니다:\n{filepath}\n\n"
                f"형식: {selected_fmt.upper()}  |  원자: {self.mol_data.num_atoms}개\n"
                f"좌표 출처: {self.mol_data.coord_source}"
            )
            self.info_lbl.setText(
                self.info_lbl.text() + f"  |  ✅ 저장: {Path(filepath).name}"
            )
            logger.info(f"3D structure exported: {filepath} ({selected_fmt})")

        except Exception as e:
            QMessageBox.critical(self, "❌ 내보내기 오류", f"파일 저장에 실패했습니다:\n{e}")
            logger.error(f"Export failed: {e}")

    def closeEvent(self, event):
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.stop_vibration()
            self.viewer.cleanup()
        super().closeEvent(event)
