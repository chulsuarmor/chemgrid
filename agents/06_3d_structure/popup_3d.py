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
# C2 Fix: `from PyQt6.QtOpenGL import GL` 제거 — PyQt6에 없음

# --- Portable path ---
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

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

GEMINI_AVAILABLE = False
try:
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
    "B":  (1.00, 0.71, 0.71), "C":  (0.20, 0.20, 0.20),
    "N":  (0.19, 0.31, 0.97), "O":  (1.00, 0.05, 0.05),
    "F":  (0.56, 0.88, 0.31), "Ne": (0.70, 0.89, 0.96),
    "Na": (0.67, 0.36, 0.95), "Mg": (0.54, 1.00, 0.00),
    "Al": (0.75, 0.65, 0.65), "Si": (0.94, 0.78, 0.63),
    "P":  (1.00, 0.50, 0.00), "S":  (1.00, 1.00, 0.19),
    "Cl": (0.12, 0.94, 0.12), "Ar": (0.50, 0.82, 0.89),
    "K":  (0.56, 0.25, 0.83), "Ca": (0.24, 1.00, 0.00),
    "Br": (0.65, 0.16, 0.16), "I":  (0.58, 0.00, 0.58),
    "Xe": (0.26, 0.62, 0.69),
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
    """RDKit ETKDG + MMFF로 3D 좌표 생성"""
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
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            props = data.get("PropertyTable", {}).get("Properties", [{}])[0]

            # Step 2: Get synonyms (common names, CAS)
            cid = props.get("CID", "")
            synonyms = []
            cas_number = ""
            if cid:
                syn_url = f"{self.BASE_URL}/compound/cid/{cid}/synonyms/JSON"
                syn_resp = requests.get(syn_url, timeout=10)
                if syn_resp.status_code == 200:
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
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = None
        self._configured = False

        if GEMINI_AVAILABLE and self.api_key:
            try:
                genai_lib.configure(api_key=self.api_key)
                self.model = genai_lib.GenerativeModel("gemini-1.5-flash")
                self._configured = True
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

        # Priority 3: RDKit 3D
        if self.smiles and RDKIT_AVAILABLE:
            rdkit_coords = generate_3d_coords_rdkit(self.smiles)
            if rdkit_coords:
                keys = list(base_2d.keys())
                for i, key in enumerate(keys):
                    self.atom_positions[key] = rdkit_coords.get(i, base_2d[key])
                self._coord_source = "RDKit ETKDG+MMFF"
                return

        # Priority 4: VSEPR
        if base_2d and self.bonds:
            self.atom_positions = estimate_z_vsepr(base_2d, self.bonds, self.atom_symbols)
            self._coord_source = "VSEPR 추정"
            return

        # Priority 5: flat 2D
        self.atom_positions = dict(base_2d)
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
    """Material 설정 — CPK 색상 강조를 위해 ambient/specular 증가"""
    glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [r*0.4, g*0.4, b*0.4, a])
    glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [r, g, b, a])
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.6, 0.6, 0.6, a])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 60.0)


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
    ATOM_SCALE = 0.85       # v4: 0.35→0.85 (약 2.4배 확대, 원소 구분 용이)
    BOND_RADIUS = 0.08      # 결합 두께 약간 줄여 원자와 대비

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData, vib_vectors=None, vib_scale=0.0):
        sq, cq = self.qm.sphere(), self.qm.cylinder()

        # Bonds
        _set_material(0.60, 0.60, 0.60)
        for (k1, k2), order in mol_data.bonds.items():
            if k1 in mol_data.atom_positions and k2 in mol_data.atom_positions:
                p1, p2 = mol_data.atom_positions[k1], mol_data.atom_positions[k2]
                bo = order if isinstance(order, int) else 1
                if bo == 1:
                    _draw_cylinder(cq, p1, p2, self.BOND_RADIUS, 10)
                else:
                    self._multi_bond(cq, p1, p2, min(bo, 3))

        # Atoms
        keys = list(mol_data.atom_positions.keys())
        for idx, (pos, coords) in enumerate(mol_data.atom_positions.items()):
            sym = mol_data.atom_symbols.get(pos, "C")
            r, g, b = get_cpk_color(sym)
            _set_material(r, g, b)
            rad = get_covalent_radius(sym) * self.ATOM_SCALE

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
    SCALE = 0.5

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
            if self.render_mode == "ball_and_stick":
                self._bs.render(self.mol_data, vv, vs)
            else:
                self._sf.render(self.mol_data, vv, vs)

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

    def cleanup(self):
        self._bs.cleanup()
        self._sf.cleanup()


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

    def update_pubchem(self, data: Dict):
        """PubChem 결과 업데이트 — v4: 독립적 try/except 오류 핸들링"""
        while self.pub_form.rowCount() > 0:
            self.pub_form.removeRow(0)

        if not data:
            self.pub_form.addRow("상태:", QLabel("오프라인 — PubChem 조회 불가"))
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


class SpectrumPanel(QWidget):
    """📈 스펙트럼 탭 — IR 스펙트럼 (ORCA 데이터 기반) + AI 피크 분석 오버레이"""

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

        if not MATPLOTLIB_AVAILABLE:
            layout.addWidget(QLabel("matplotlib 미설치 — 스펙트럼 표시 불가"))
            self.setLayout(layout)
            return

        self.figure = Figure(figsize=(8, 3), dpi=100)
        self.figure.patch.set_facecolor("#1e1e1e")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas)

        self.info_label = QLabel("ORCA .out 파일 로드 시 IR 스펙트럼이 표시됩니다")
        self.info_label.setStyleSheet("color: #888;")
        layout.addWidget(self.info_label)

        # 🤖 AI 피크 분석 토글 버튼 (그래프 아래)
        self.btn_ai_overlay = QPushButton("🤖 AI 피크 분석")
        self.btn_ai_overlay.setCheckable(True)
        self.btn_ai_overlay.setChecked(False)
        self.btn_ai_overlay.setStyleSheet("""
            QPushButton {
                background-color: #37474F;
                color: #B0BEC5;
                border: 1px solid #546E7A;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #1565C0;
                color: white;
                border: 1px solid #42A5F5;
            }
            QPushButton:hover {
                background-color: #455A64;
            }
        """)
        self.btn_ai_overlay.clicked.connect(self._toggle_ai_overlay)
        layout.addWidget(self.btn_ai_overlay)

        self.setLayout(layout)

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

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("⚡ AI 분석 노트 (Gemini — 참고용)"))
        hdr.addStretch()
        self.btn_analyze = QPushButton("🔍 분석 요청")
        self.btn_analyze.clicked.connect(self._request_analysis)
        hdr.addWidget(self.btn_analyze)
        layout.addLayout(hdr)

        # Reliability notice
        notice = QLabel("⚠️ AI 생성 결과는 참고용입니다. 정확성을 항상 검증하세요. (신뢰도 ★★★☆☆)")
        notice.setStyleSheet("color: #f0ad4e; font-size: 8pt; padding: 4px;")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        # Result text
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background-color: #252525; color: #ddd; font-size: 10pt;")
        layout.addWidget(self.result_text)

        # API key input
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("API Key:"))
        self.key_input = QLabel(
            "환경변수 GEMINI_API_KEY 설정됨" if os.environ.get("GEMINI_API_KEY")
            else "미설정 (환경변수 GEMINI_API_KEY 필요)")
        self.key_input.setStyleSheet("color: #888; font-size: 8pt;")
        key_layout.addWidget(self.key_input)
        layout.addLayout(key_layout)

        self.setLayout(layout)

        # Data holders
        self._smiles = ""
        self._properties = {}
        self._orca_data = {}

    def set_data(self, smiles: str, properties: Dict = None, orca_data: Dict = None):
        self._smiles = smiles
        self._properties = properties or {}
        self._orca_data = orca_data or {}

    def _request_analysis(self):
        if not self._smiles:
            self.result_text.setPlainText("⚠️ SMILES가 없어 분석할 수 없습니다.")
            return

        self.btn_analyze.setEnabled(False)
        self.result_text.setPlainText("🔄 AI 분석 중... (Gemini API 호출)")
        QApplication.processEvents()

        # Run in thread to avoid UI freeze
        def _run():
            result = self._analyzer.analyze_molecule(
                self._smiles, self._properties, self._orca_data)
            return result

        # Simple threaded approach
        try:
            result = _run()
            self.result_text.setPlainText(result)
        except Exception as e:
            self.result_text.setPlainText(f"⚠️ 오류: {e}")
        finally:
            self.btn_analyze.setEnabled(True)


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
        self.mol_data = mol_data
        self.orca_parser = mol_data.orca_parser if mol_data else None
        self.viewer = None
        self.pubchem = PubChemClient()
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        self.setWindowTitle("ChemGrid — 통합 3D 분자 분석")
        self.setGeometry(80, 80, 1000, 820)
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

        self.tabs.addTab(self.tab_props, "📊 속성")
        self.tabs.addTab(self.tab_spectrum, "📈 스펙트럼")
        self.tabs.addTab(self.tab_vibration, "🎵 진동모드")
        self.tabs.addTab(self.tab_ai, "📝 AI분석")

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
                self.tab_props.update_pubchem(pub_data)
            except Exception:
                self.tab_props.update_pubchem(None)
        else:
            self.tab_props.update_pubchem(None)

        # ORCA data
        if self.orca_parser:
            self._apply_orca_data(self.orca_parser)

        # AI tab
        orca_info = {}
        if self.orca_parser:
            orca_info["energy"] = self.orca_parser.total_energy
            orca_info["dipole"] = self.orca_parser.dipole_moment
        self.tab_ai.set_data(smiles, {}, orca_info)

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
        """진동 모드 선택 시 뷰어에 벡터 표시"""
        if (self.orca_parser and mode_idx < len(self.orca_parser.normal_modes)
                and isinstance(self.viewer, Molecule3DViewer)):
            vectors = self.orca_parser.normal_modes[mode_idx]
            amp = self.tab_vibration.amp_slider.value() / 100.0
            if self.tab_vibration.btn_play.isChecked():
                self.viewer.start_vibration(vectors, amp)

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

    def closeEvent(self, event):
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.stop_vibration()
            self.viewer.cleanup()
        super().closeEvent(event)
