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
    QListWidgetItem, QFileDialog, QApplication, QSizePolicy
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

# [VINA-WIRE] AutoDock Vina 백엔드 import
VINA_BACKEND_AVAILABLE = False
try:
    from docking_interface import (
        VinaDockingThread, DockingConfig,
        PDBParser as VinaPDBParser, PDBDownloader,
        LigandPreparer, ReceptorPreparer,
        DOCKING_AVAILABLE as _VINA_DOCKING_OK,
    )
    from docking_data import (
        ReceptorData, LigandData, DockingResult, DockingPose,
    )
    VINA_BACKEND_AVAILABLE = _VINA_DOCKING_OK
except ImportError:
    logger.info("docking_interface not available — using empirical scoring only")

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

        # ★ 거대 분자 가드: 중원자 200개 초과 시 2D fallback (헤모글로빈 등 프리즈 방지)
        n_heavy = mol.GetNumHeavyAtoms()
        if n_heavy > 200:
            logger.warning(
                f"거대 분자 감지 (heavy atoms={n_heavy}): 3D 임베딩 건너뛰고 2D 사용")
            AllChem.Compute2DCoords(mol)
            mol = Chem.AddHs(mol)
            try:
                AllChem.Compute2DCoords(mol)
            except Exception:
                pass
            conf = mol.GetConformer()
            atom_positions = {}
            atom_symbols = {}
            for atom in mol.GetAtoms():
                i = atom.GetIdx()
                pos = conf.GetAtomPosition(i)
                atom_positions[i] = (round(float(pos.x), 3),
                                      round(float(pos.y), 3), 0.0)
                atom_symbols[i] = atom.GetSymbol()
            bonds = {}
            for bond in mol.GetBonds():
                i1, i2 = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                bt = bond.GetBondTypeAsDouble()
                bonds[(i1, i2)] = int(round(bt)) if bt and abs(bt - 1.5) >= 0.01 else 1.5
            atom_positions = estimate_z_vsepr(atom_positions, bonds, atom_symbols)
            bonds = _detect_coordination_bonds(atom_symbols, bonds)
            return atom_positions, atom_symbols, bonds

        mol = Chem.AddHs(mol)  # 명시적 수소 추가

        # ★ 중간 크기 분자 (50-200): 반복 횟수 축소
        max_iter_1 = 500 if n_heavy > 50 else 1000
        max_iter_2 = 1000 if n_heavy > 50 else 2000

        # ★ 다단계 3D 임베딩 전략 (복잡한 분자 대응)
        result = -1

        # 전략 1: ETKDGv3 (가장 정확)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        params.maxIterations = max_iter_1
        result = AllChem.EmbedMolecule(mol, params)

        # 전략 2: ETKDG (레거시, 더 관대)
        if result != 0:
            result = AllChem.EmbedMolecule(mol, AllChem.ETKDG())

        # 전략 3: useRandomCoords=True (강제 임베딩 — 복잡 분자에 효과적)
        if result != 0:
            params2 = AllChem.ETKDGv3()
            params2.useRandomCoords = True
            params2.randomSeed = 42
            params2.maxIterations = max_iter_2
            result = AllChem.EmbedMolecule(mol, params2)

        # 전략 4: 기본 랜덤 좌표 (최후의 수단)
        if result != 0:
            result = AllChem.EmbedMolecule(mol, randomSeed=42, useRandomCoords=True)

        # 전략 5: 2D 좌표 생성 후 Z축 VSEPR 추정 (진정한 최후 수단)
        if result != 0:
            try:
                AllChem.Compute2DCoords(mol)
                conf = mol.GetConformer()
                # 2D 좌표를 기반으로 VSEPR Z 추정
                atom_positions = {}
                atom_symbols = {}
                for atom in mol.GetAtoms():
                    i = atom.GetIdx()
                    pos = conf.GetAtomPosition(i)
                    atom_positions[i] = (round(float(pos.x), 3),
                                          round(float(pos.y), 3),
                                          0.0)  # 일단 flat
                    atom_symbols[i] = atom.GetSymbol()

                bonds = {}
                for bond in mol.GetBonds():
                    i1 = bond.GetBeginAtomIdx()
                    i2 = bond.GetEndAtomIdx()
                    bt = bond.GetBondTypeAsDouble()
                    if bt and abs(bt - 1.5) < 0.01:
                        order = 1.5
                    else:
                        order = int(round(bt)) if bt else 1
                    bonds[(i1, i2)] = order

                # Z축 VSEPR 추정
                atom_positions = estimate_z_vsepr(atom_positions, bonds, atom_symbols)
                bonds = _detect_coordination_bonds(atom_symbols, bonds)
                return atom_positions, atom_symbols, bonds
            except Exception:
                return None

        # 최적화
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

        # Kekulize: 방향족 결합을 교대 단일/이중으로 변환 (벤젠 = 1,2,1,2,1,2)
        # 이렇게 하면 3D에서 실제 Kekulé 구조로 그려짐
        try:
            Chem.Kekulize(mol, clearAromaticFlags=False)
        except Exception:
            pass  # Kekulize 실패 시 원본 유지

        bonds: Dict[Tuple, int] = {}
        for bond in mol.GetBonds():
            i1 = bond.GetBeginAtomIdx()
            i2 = bond.GetEndAtomIdx()
            bt = bond.GetBondTypeAsDouble()
            bond_type = bond.GetBondType()
            # [COORD-BOND] RDKit DATIVE bond type → directly mark as 0.5
            if hasattr(Chem.BondType, 'DATIVE') and bond_type == Chem.BondType.DATIVE:
                order = 0.5
            # Kekulize 후에도 AROMATIC으로 남은 결합 (실패 시)
            elif bond_type == Chem.BondType.AROMATIC:
                order = 1.5
            else:
                order = int(round(bt)) if bt else 1
            bonds[(i1, i2)] = order

        # ★ 메탈로센 샌드위치 구조 후처리 (ferrocene 등)
        atom_positions, atom_symbols, bonds = _fix_metallocene_geometry(
            atom_positions, atom_symbols, bonds)

        # ★ 범용 배위결합 감지 (포르피린 Fe-N, 시스플라틴 Pt-N, 카르보닐 Co-CO 등)
        bonds = _detect_coordination_bonds(atom_symbols, bonds)

        # ★ 3D 좌표 유효성 검증: 모든 원자가 같은 z=0이면 임베딩 실패
        z_vals = [p[2] for p in atom_positions.values()]
        if len(z_vals) > 3 and max(z_vals) - min(z_vals) < 0.01:
            # 평면 좌표 → VSEPR Z 추정으로 보강
            atom_positions = estimate_z_vsepr(atom_positions, bonds, atom_symbols)

        return atom_positions, atom_symbols, bonds
    except Exception as e:
        logger.warning(f"generate_3d_full_from_smiles failed: {e}")
        return None


def _fix_metallocene_geometry(
    atom_positions: Dict[int, Tuple[float, float, float]],
    atom_symbols: Dict[int, str],
    bonds: Dict[Tuple, Any],
) -> Tuple[Dict, Dict, Dict]:
    """메탈로센(ferrocene 등) 샌드위치 구조 후처리.

    RDKit은 이온성 금속 복합체([Fe+2].[cH-]1cccc1.[cH-]1cccc1)를 임베딩할 때
    Fe-C 결합을 생성하지 않고, 두 Cp 고리를 동일 좌표에 겹쳐놓는다.
    이 함수는:
      1. 결합이 없는 전이금속 원자를 탐지
      2. 5원 고리(Cp)를 찾아 금속 위/아래에 배치
      3. 가상 Fe-C 결합(dashed, order=0.5)을 추가
    """
    import numpy as np

    TRANSITION_METALS = {
        'Fe', 'Cr', 'Co', 'Ni', 'Ru', 'Os', 'Mn', 'V', 'Ti', 'Zr', 'Hf',
        'Mo', 'W', 'Rh', 'Ir', 'Pd', 'Pt',
    }

    # 1) 결합이 없는 전이금속 원자 탐색
    bonded_atoms: set = set()
    for (k1, k2) in bonds.keys():
        bonded_atoms.add(k1)
        bonded_atoms.add(k2)

    metal_indices = [
        idx for idx, sym in atom_symbols.items()
        if sym in TRANSITION_METALS and idx not in bonded_atoms
    ]
    if not metal_indices:
        return atom_positions, atom_symbols, bonds

    # 2) 인접 리스트 구축 (비금속 원자 전용)
    adjacency: Dict[int, list] = {}
    for (k1, k2) in bonds.keys():
        adjacency.setdefault(k1, []).append(k2)
        adjacency.setdefault(k2, []).append(k1)

    # 3) 연결 성분(connected component) 기반 Cp 고리 탐색
    #    메탈로센에서 금속은 결합이 없으므로, 비금속 원자의 연결 성분 = 각 Cp 고리
    heavy_atoms = {idx for idx, sym in atom_symbols.items()
                   if sym not in TRANSITION_METALS and sym != 'H' and idx in bonded_atoms}
    visited_cc: set = set()
    cp_rings: list = []

    for seed in heavy_atoms:
        if seed in visited_cc:
            continue
        # DFS로 연결 성분 수집
        component: list = []
        stack = [seed]
        while stack:
            node = stack.pop()
            if node in visited_cc:
                continue
            visited_cc.add(node)
            if atom_symbols.get(node) in TRANSITION_METALS or atom_symbols.get(node) == 'H':
                continue
            component.append(node)
            for nb in adjacency.get(node, []):
                if nb not in visited_cc and nb in heavy_atoms:
                    stack.append(nb)
        # 5원 연결 성분 = Cp 고리 (사이클로펜타디에닐)
        if len(component) == 5:
            cp_rings.append(component)

    if not cp_rings or not metal_indices:
        return atom_positions, atom_symbols, bonds

    # 4) 각 금속에 대해 최대 2개 Cp 고리를 배정하여 샌드위치 구조 생성
    new_positions = dict(atom_positions)
    new_bonds = dict(bonds)
    used_rings: set = set()

    for m_idx in metal_indices:
        # 미사용 Cp 고리 중 최대 2개
        available = [r for r in cp_rings if frozenset(r) not in used_rings]
        rings_for_metal = available[:2]
        if not rings_for_metal:
            continue

        # 금속 원점 (0,0,0)
        m_pos = np.array(atom_positions.get(m_idx, (0.0, 0.0, 0.0)))

        # Cp 고리 반지름 ≈ 1.21 Å, Fe-Cp 거리 ≈ 1.66 Å
        CP_RADIUS = 1.21
        FE_CP_DIST = 1.66

        for ring_idx, ring in enumerate(rings_for_metal):
            used_rings.add(frozenset(ring))
            z_sign = 1.0 if ring_idx == 0 else -1.0

            # 정오각형 배치 + z 오프셋
            n = len(ring)
            for i, atom_idx in enumerate(ring):
                angle = 2.0 * math.pi * i / n
                # 두번째 고리는 36도(π/5) 회전 (eclipsed → staggered)
                if ring_idx == 1:
                    angle += math.pi / n
                x = m_pos[0] + CP_RADIUS * math.cos(angle)
                y = m_pos[1] + CP_RADIUS * math.sin(angle)
                z = m_pos[2] + z_sign * FE_CP_DIST
                new_positions[atom_idx] = (round(x, 3), round(y, 3), round(z, 3))

                # 해당 원자에 붙은 H도 이동
                for nb in adjacency.get(atom_idx, []):
                    if atom_symbols.get(nb) == 'H':
                        hx = m_pos[0] + (CP_RADIUS + 1.08) * math.cos(angle)
                        hy = m_pos[1] + (CP_RADIUS + 1.08) * math.sin(angle)
                        hz = m_pos[2] + z_sign * (FE_CP_DIST + 0.05)
                        new_positions[nb] = (round(hx, 3), round(hy, 3), round(hz, 3))

                # 가상 금속-탄소 결합 추가 (order=0.5 → dashed로 렌더링)
                new_bonds[(m_idx, atom_idx)] = 0.5

    return new_positions, atom_symbols, new_bonds


# ============================================================
# Generic Coordination Bond Detection (all transition metal complexes)
# ============================================================

# Comprehensive transition metals: Sc-Zn (3d), Y-Cd (4d), Hf-Hg (5d)
TRANSITION_METALS_ALL = frozenset({
    'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
    'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
    'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg',
})

# Ligand donor atoms: atoms that commonly donate lone pairs to metals
LIGAND_DONORS = frozenset({'N', 'O', 'P', 'S', 'As', 'Se'})


def _detect_coordination_bonds(
    atom_symbols: Dict[int, str],
    bonds: Dict[Tuple, Any],
) -> Dict[Tuple, Any]:
    """Generic coordination bond detection for ALL transition metal complexes.

    Scans all existing bonds. If a bond connects a transition metal to a
    ligand donor atom (N, O, P, S, As, Se) AND the bond order is single (1),
    it is re-classified as a dative/coordination bond (order=0.5).

    Also handles metal-C bonds that are single (e.g., metal carbonyls M-CO):
    if a carbon is bonded to a metal with order 1 AND that carbon also has
    a triple or double bond to O/N (like C≡O or C=N), treat M-C as dative.

    Bonds already marked as 0.5 (from metallocene logic) are left unchanged.

    Args:
        atom_symbols: {atom_idx: element_symbol}
        bonds: {(i,j): bond_order} — modified in-place and returned

    Returns:
        Updated bonds dict with coordination bonds marked as order 0.5.
    """
    new_bonds = dict(bonds)

    # Build adjacency for carbonyl/isocyanide detection
    adjacency: Dict[int, list] = {}
    for (k1, k2), order in bonds.items():
        adjacency.setdefault(k1, []).append((k2, order))
        adjacency.setdefault(k2, []).append((k1, order))

    for (k1, k2), order in bonds.items():
        # Skip bonds already marked as dative (0.5) or non-single bonds
        if isinstance(order, (int, float)) and abs(order - 0.5) < 0.01:
            continue

        # Only process single bonds (order == 1)
        if not (isinstance(order, (int, float)) and abs(order - 1.0) < 0.01):
            continue

        sym1 = atom_symbols.get(k1, '')
        sym2 = atom_symbols.get(k2, '')

        metal_idx = None
        ligand_idx = None

        # Case 1: metal -> donor atom (N, O, P, S, As, Se)
        if sym1 in TRANSITION_METALS_ALL and sym2 in LIGAND_DONORS:
            metal_idx, ligand_idx = k1, k2
        elif sym2 in TRANSITION_METALS_ALL and sym1 in LIGAND_DONORS:
            metal_idx, ligand_idx = k2, k1

        # Case 2: metal -> C (carbonyl M-CO, isocyanide M-CN)
        elif sym1 in TRANSITION_METALS_ALL and sym2 == 'C':
            # Check if this carbon has a multiple bond to O or N
            if _is_carbonyl_or_isocyanide_carbon(k2, adjacency, atom_symbols):
                metal_idx, ligand_idx = k1, k2
        elif sym2 in TRANSITION_METALS_ALL and sym1 == 'C':
            if _is_carbonyl_or_isocyanide_carbon(k1, adjacency, atom_symbols):
                metal_idx, ligand_idx = k2, k1

        if metal_idx is not None:
            new_bonds[(k1, k2)] = 0.5

    return new_bonds


def _is_carbonyl_or_isocyanide_carbon(
    c_idx: int,
    adjacency: Dict[int, list],
    atom_symbols: Dict[int, str],
) -> bool:
    """Check if a carbon atom is part of a CO or CN ligand (carbonyl/isocyanide).

    Returns True if the carbon has a double or triple bond to O or N.
    """
    for neighbor_idx, bond_order in adjacency.get(c_idx, []):
        sym = atom_symbols.get(neighbor_idx, '')
        if sym in ('O', 'N') and isinstance(bond_order, (int, float)) and bond_order >= 2:
            return True
    return False


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

        self._use_new_sdk = False
        if GEMINI_AVAILABLE and self.api_key:
            # 1차: 새 SDK (google.genai) — Client 패턴
            try:
                import google.genai as _new_genai
                self._client = _new_genai.Client(api_key=self.api_key)
                self._model_name = "gemini-2.5-flash"
                self._use_new_sdk = True
                self._configured = True
                logger.info(f"Gemini (new SDK) configured (key={self.api_key[:8]}...)")
            except Exception:
                # 2차: 구 SDK (google.generativeai) — GenerativeModel 패턴
                try:
                    import google.generativeai as _old_genai
                    _old_genai.configure(api_key=self.api_key)
                    try:
                        self.model = _old_genai.GenerativeModel("gemini-2.5-flash")
                    except Exception:
                        self.model = _old_genai.GenerativeModel("gemini-2.0-flash")
                    self._configured = True
                    logger.info(f"Gemini (old SDK) configured (key={self.api_key[:8]}...)")
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
            if self._use_new_sdk:
                resp = self._client.models.generate_content(
                    model=self._model_name, contents=prompt
                )
                return f"⚡ AI 분석 (참고용 — Gemini)\n{'=' * 40}\n{resp.text}"
            else:
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
            # [FIX-3D-006] 배위결합(0.5) → MOL block에서 1로 표현
            bo = max(1, min(int(round(order)) if isinstance(order, (int, float)) else 1, 3))
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

        # [FIX] 진동 변위를 적용한 원자 좌표 맵 구축 (결합도 함께 늘어나도록)
        displaced_positions = {}
        keys = list(mol_data.atom_positions.keys())
        for idx, (pos_key, coords) in enumerate(mol_data.atom_positions.items()):
            cx, cy, cz = coords
            if vib_vectors and idx < len(vib_vectors) and abs(vib_scale) > 0.001:
                vx, vy, vz = vib_vectors[idx]
                cx += vx * vib_scale
                cy += vy * vib_scale
                cz += vz * vib_scale
            displaced_positions[pos_key] = (cx, cy, cz)

        # Bonds (π 오비탈 모드에서도 결합선은 유지 — 분자 골격 파악용)
        # [FIX-3D-005] 진동 시 결합 길이 변화에 따른 색상 코딩
        _has_vib = vib_vectors is not None and abs(vib_scale) > 0.001
        _set_material(0.60, 0.60, 0.60)
        for (k1, k2), order in mol_data.bonds.items():
            if k1 in mol_data.atom_positions and k2 in mol_data.atom_positions:
                # [FIX] 진동 시 결합도 함께 늘어나도록 displaced 좌표 사용
                p1, p2 = displaced_positions[k1], displaced_positions[k2]
                # [FIX] order를 float/int 그대로 보존 (1.5 방향족 검출 위해)
                bo = order
                bond_r = self.BOND_RADIUS * (0.5 if small_atoms else 1.0)

                # [FIX-3D-005] 진동 중 결합 신축 색상 코딩
                if _has_vib:
                    eq1 = mol_data.atom_positions[k1]
                    eq2 = mol_data.atom_positions[k2]
                    eq_len = math.sqrt(sum((a-b)**2 for a, b in zip(eq1, eq2)))
                    disp_len = math.sqrt(sum((a-b)**2 for a, b in zip(p1, p2)))
                    if eq_len > 0.01:
                        strain = (disp_len - eq_len) / eq_len  # >0 stretched, <0 compressed
                        strain_clamped = max(-0.15, min(0.15, strain))
                        strain_t = strain_clamped / 0.15  # -1.0 to +1.0
                        if strain_t > 0.02:
                            # 신장(stretched): 회색→빨강 그라데이션
                            t = strain_t
                            _set_material(0.60 + 0.40*t, 0.60 - 0.40*t, 0.60 - 0.40*t)
                        elif strain_t < -0.02:
                            # 압축(compressed): 회색→파랑 그라데이션
                            t = -strain_t
                            _set_material(0.60 - 0.40*t, 0.60 - 0.20*t, 0.60 + 0.40*t)
                        else:
                            _set_material(0.60, 0.60, 0.60)

                if isinstance(bo, (float, int)) and abs(bo - 0.5) < 0.01:
                    # [FIX-3D-006] 배위 결합 (메탈로센 Fe-C 등): 점선 실린더
                    self._dashed_bond(cq, p1, p2, bond_r * 0.6, 8)
                elif isinstance(bo, (float, int)) and abs(bo - 1.5) < 0.01:
                    # [FIX] 방향족 비편재화 결합: 중앙 + 얇은 오프셋 (2중결합 느낌)
                    _draw_cylinder(cq, p1, p2, bond_r, 10)
                    self._aromatic_bond_overlay(cq, p1, p2, bond_r * 0.45)
                elif bo == 1 or (isinstance(bo, float) and bo < 1.4):
                    _draw_cylinder(cq, p1, p2, bond_r, 10)
                else:
                    self._multi_bond(cq, p1, p2, min(int(round(bo)), 3))

                # [FIX-3D-005] 진동 후 결합 색상 리셋
                if _has_vib:
                    _set_material(0.60, 0.60, 0.60)

        # Atoms — displaced_positions 재사용 (결합과 동일한 좌표)
        for idx, (pos, _) in enumerate(mol_data.atom_positions.items()):
            sym = mol_data.atom_symbols.get(pos, "C")
            r, g, b = get_cpk_color(sym)
            _set_material(r, g, b)
            rad = get_covalent_radius(sym) * atom_scale

            cx, cy, cz = displaced_positions[pos]

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

    def _aromatic_bond_overlay(self, cq, p1, p2, thin_r):
        """방향족 결합 시각화: 명확한 이중결합 표현 (Kekulé 스타일).
        메인 실린더 옆에 확실히 보이는 보조 실린더를 추가하여
        단일결합과 방향족 결합을 시각적으로 구별.
        오프셋을 크게, 색상을 다르게 하여 확실히 보이도록."""
        offset_dist = max(0.15, thin_r * 2.5)  # 이전 0.08 → 0.15 이상
        ox, oy, oz = self._perpendicular_offset(p1, p2, offset_dist)
        # 오프셋된 보조 실린더 (이중결합 시각 효과)
        np1 = (p1[0] + ox, p1[1] + oy, p1[2] + oz)
        np2 = (p2[0] + ox, p2[1] + oy, p2[2] + oz)
        # 밝은 회색으로 보조 결합 — 메인보다 얇지만 확실히 보이게
        _set_material(0.75, 0.75, 0.75)
        _draw_cylinder(cq, np1, np2, thin_r * 0.8, 8)
        # 원래 색상 복원
        _set_material(0.60, 0.60, 0.60)

    def _dashed_bond(self, cq, p1, p2, radius, n_segments=8):
        """배위 결합 시각화: 점선 실린더 (메탈로센 Fe-C 등)."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        _set_material(0.50, 0.50, 0.70)  # 약간 푸르스름한 회색
        for i in range(n_segments):
            if i % 2 == 0:  # 짝수 세그먼트만 그림 (점선 효과)
                t0 = i / n_segments
                t1 = (i + 1) / n_segments
                sp = (p1[0] + dx * t0, p1[1] + dy * t0, p1[2] + dz * t0)
                ep = (p1[0] + dx * t1, p1[1] + dy * t1, p1[2] + dz * t1)
                _draw_cylinder(cq, sp, ep, radius, 6)
        _set_material(0.60, 0.60, 0.60)

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

    def render_stereo_bonds(self, mol_data: Molecule3DData):
        """입체 결합 (웨지/대쉬) 시각화.
        SMILES에서 @/@@ 정보를 추출하여 키랄 중심 주변 결합을 강조."""
        if not RDKIT_AVAILABLE or not mol_data.smiles:
            return
        try:
            mol = Chem.MolFromSmiles(mol_data.smiles)
            if mol is None:
                return
            mol = Chem.AddHs(mol)

            # 키랄 중심 찾기
            chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
            if not chiral_centers:
                return

            sq, cq = self.qm.sphere(), self.qm.cylinder()

            for atom_idx, chirality in chiral_centers:
                atom = mol.GetAtomWithIdx(atom_idx)
                if atom_idx not in mol_data.atom_positions:
                    continue

                center_pos = mol_data.atom_positions[atom_idx]
                neighbors = [n.GetIdx() for n in atom.GetNeighbors()]

                # 키랄 중심의 결합들을 웨지/대쉬로 표현
                for i, n_idx in enumerate(neighbors):
                    if n_idx not in mol_data.atom_positions:
                        continue
                    n_pos = mol_data.atom_positions[n_idx]

                    # Z 좌표 차이로 위/아래 결정
                    dz = n_pos[2] - center_pos[2]

                    if abs(dz) > 0.1:
                        if dz > 0:
                            # 위로 = wedge (실선 삼각형) — 파란 계열
                            self._draw_wedge_bond(cq, center_pos, n_pos, (0.2, 0.5, 1.0))
                        else:
                            # 아래로 = dash (점선) — 빨간 계열
                            self._draw_dash_bond(cq, center_pos, n_pos, (1.0, 0.3, 0.3))

        except Exception:
            pass

    def _draw_wedge_bond(self, cq, p1, p2, color):
        """웨지 결합: 시작점은 가늘고 끝점은 두꺼운 원뿔형"""
        _set_material(*color)
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
        # 원뿔: 시작 반지름 0.04, 끝 반지름 0.18
        gluCylinder(cq, 0.04, 0.18, length, 12, 1)
        glPopMatrix()

    def _draw_dash_bond(self, cq, p1, p2, color):
        """대쉬 결합: 점선으로 표현 (여러 개의 짧은 실린더)"""
        _set_material(*color)
        n_dashes = 6
        dx = (p2[0]-p1[0]) / (2*n_dashes)
        dy = (p2[1]-p1[1]) / (2*n_dashes)
        dz = (p2[2]-p1[2]) / (2*n_dashes)
        for i in range(n_dashes):
            t1 = 2*i
            t2 = 2*i + 1
            sp = (p1[0]+dx*t1, p1[1]+dy*t1, p1[2]+dz*t1)
            ep = (p1[0]+dx*t2, p1[1]+dy*t2, p1[2]+dz*t2)
            _draw_cylinder(cq, sp, ep, self.BOND_RADIUS * 0.8, 8)

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
        """Pi 오비탈 렌더링: 원자별 p-orbital 로브 + 공액계 연결 시각화.

        [FIX-PI-LOBE] 납작 디스크 → 적절한 물방울형 p-orbital 로브 (위/아래)
        [FIX-PI-PERP] 각 sp2 원자의 로컬 법선 벡터 사용 (전역 SVD 대신)
        — 비평면 분자에서도 각 sp2 원자의 p-orbital이 올바른 방향을 가리킴
        """
        if not OPENGL_AVAILABLE:
            return
        try:
            # 분자 평면 법선 벡터 계산 (SVD) — 밴드 렌더링 및 폴백용
            global_normal = self._calc_molecular_plane_normal(mol_data)

            # RDKit으로 sp2/방향족 원자 + 고리 정보 감지
            sp2_keys, ring_groups, ring_atom_keys = self._detect_sp2_and_rings(mol_data)

            # 인접 리스트 구축 (로컬 법선 계산용)
            adjacency = {}  # {key: [neighbor_key, ...]}
            for k1, k2 in mol_data.bonds.keys():
                adjacency.setdefault(k1, []).append(k2)
                adjacency.setdefault(k2, []).append(k1)

            sq = self.qm.sphere()

            # ── 모든 sp2 원자에 p-orbital 로브 렌더링 (위/아래 물방울) ──
            all_sp2_set = set(sp2_keys)
            for key in sp2_keys:
                pos = mol_data.atom_positions.get(key)
                if pos:
                    # [FIX-PI-PERP] 로컬 법선: 이웃 원자 좌표로부터 sp2 평면 법선 계산
                    local_n = self._calc_local_normal(
                        key, mol_data.atom_positions, adjacency, global_normal)
                    self._draw_p_orbital_lobes(sq, pos, local_n)

            # ── 공액 시스템 연결 밴드 (방향족 고리) ──
            for ring_positions in ring_groups:
                # 고리 자체의 법선 계산 (고리 원자들의 외적)
                ring_normal = self._calc_ring_normal(ring_positions, global_normal)
                self._draw_ring_pi_cloud(sq, ring_positions, ring_normal)

            # ── 비고리 sp2 연결 밴드 ──
            non_ring_sp2 = [k for k in sp2_keys if k not in ring_atom_keys]
            if non_ring_sp2:
                sp2_systems = self._group_connected_sp2(non_ring_sp2, mol_data)
                for system_keys in sp2_systems:
                    if len(system_keys) >= 2:
                        system_positions = []
                        for key in system_keys:
                            pos = mol_data.atom_positions.get(key)
                            if pos:
                                system_positions.append(pos)
                        if len(system_positions) >= 2:
                            sys_normal = self._calc_ring_normal(
                                system_positions, global_normal)
                            self._draw_ring_pi_cloud(sq, system_positions, sys_normal)

        except Exception:
            pass  # RDKit 없거나 OpenGL 오류 시 조용히 실패

    def _calc_local_normal(self, atom_key, atom_positions, adjacency, fallback_normal):
        """[FIX-PI-PERP] sp2 원자의 로컬 평면 법선 벡터를 계산합니다.

        3개 이상의 이웃이 있으면 이웃 벡터들의 외적으로 법선 계산.
        2개 이웃이면 두 결합 벡터의 외적 사용.
        이웃 부족 시 전역 법선(SVD) 폴백.

        Returns:
            (nx, ny, nz): 단위 법선 벡터
        """
        import math
        pos = atom_positions.get(atom_key)
        if pos is None:
            return fallback_normal

        neighbors = adjacency.get(atom_key, [])
        # 이웃 좌표의 상대 벡터 수집
        vecs = []
        for nb in neighbors:
            nb_pos = atom_positions.get(nb)
            if nb_pos is not None:
                dx = nb_pos[0] - pos[0]
                dy = nb_pos[1] - pos[1]
                dz = nb_pos[2] - pos[2]
                mag = math.sqrt(dx*dx + dy*dy + dz*dz)
                if mag > 1e-6:
                    vecs.append((dx, dy, dz))

        if len(vecs) >= 2:
            # 첫 두 결합 벡터의 외적 = 평면 법선
            v1 = vecs[0]
            v2 = vecs[1]
            nx = v1[1]*v2[2] - v1[2]*v2[1]
            ny = v1[2]*v2[0] - v1[0]*v2[2]
            nz = v1[0]*v2[1] - v1[1]*v2[0]
            mag = math.sqrt(nx*nx + ny*ny + nz*nz)
            if mag > 1e-6:
                # 3개 이상 이웃이면 추가 외적들과 평균하여 안정성 향상
                if len(vecs) >= 3:
                    # 여러 쌍의 외적 평균
                    total_nx, total_ny, total_nz = nx/mag, ny/mag, nz/mag
                    count = 1
                    for i in range(len(vecs)):
                        for j in range(i+1, len(vecs)):
                            if i == 0 and j == 1:
                                continue  # 이미 계산됨
                            vi, vj = vecs[i], vecs[j]
                            cx = vi[1]*vj[2] - vi[2]*vj[1]
                            cy = vi[2]*vj[0] - vi[0]*vj[2]
                            cz = vi[0]*vj[1] - vi[1]*vj[0]
                            cm = math.sqrt(cx*cx + cy*cy + cz*cz)
                            if cm > 1e-6:
                                # 부호 일관성: 첫 법선과 같은 방향이 되도록
                                dot = (cx/cm)*total_nx + (cy/cm)*total_ny + (cz/cm)*total_nz
                                sign = 1.0 if dot >= 0 else -1.0
                                total_nx += sign * cx / cm
                                total_ny += sign * cy / cm
                                total_nz += sign * cz / cm
                                count += 1
                    fm = math.sqrt(total_nx**2 + total_ny**2 + total_nz**2)
                    if fm > 1e-6:
                        return (total_nx/fm, total_ny/fm, total_nz/fm)
                return (nx/mag, ny/mag, nz/mag)

        return fallback_normal

    def _calc_ring_normal(self, positions, fallback_normal):
        """고리/시스템 원자 좌표 리스트로부터 평면 법선을 계산합니다.

        Newell's method: 다각형의 면적 벡터를 법선으로 사용.
        """
        import math
        if len(positions) < 3:
            return fallback_normal
        # Newell's method
        nx, ny, nz = 0.0, 0.0, 0.0
        n = len(positions)
        for i in range(n):
            p1 = positions[i]
            p2 = positions[(i + 1) % n]
            nx += (p1[1] - p2[1]) * (p1[2] + p2[2])
            ny += (p1[2] - p2[2]) * (p1[0] + p2[0])
            nz += (p1[0] - p2[0]) * (p1[1] + p2[1])
        mag = math.sqrt(nx*nx + ny*ny + nz*nz)
        if mag > 1e-6:
            return (nx/mag, ny/mag, nz/mag)
        return fallback_normal

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
        """RDKit으로 sp2 원자 키 목록과 방향족 고리 좌표 그룹을 반환합니다.

        Returns:
            (sp2_keys, ring_groups, ring_atom_keys)
            - sp2_keys: List[key] — 모든 sp2/sp 원자
            - ring_groups: List[List[(x,y,z)]] — 방향족 고리별 좌표
            - ring_atom_keys: Set[key] — 방향족 고리에 속하는 원자 키
        """
        sp2_keys = []
        ring_groups = []
        ring_atom_keys = set()
        try:
            from rdkit import Chem
            smiles = getattr(mol_data, 'smiles', '') or ''
            if not smiles:
                return sp2_keys, ring_groups, ring_atom_keys
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return sp2_keys, ring_groups, ring_atom_keys

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
                            key = atom_keys[i]
                            ring_atom_keys.add(key)
                            pos = mol_data.atom_positions.get(key)
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
        return sp2_keys, ring_groups, ring_atom_keys

    def _group_connected_sp2(self, sp2_keys, mol_data):
        """sp2 원자들을 결합 연결성 기반으로 그룹화합니다.

        Returns: List[List[key]] — 각 리스트가 연결된 sp2 시스템의 키 목록
        """
        sp2_set = set(sp2_keys)
        # 인접 리스트 구성 (sp2 원자끼리 결합이 있는 경우)
        adj = {k: [] for k in sp2_keys}
        for k1, k2 in mol_data.bonds.keys():
            if k1 in sp2_set and k2 in sp2_set:
                adj[k1].append(k2)
                adj[k2].append(k1)

        # BFS로 연결 컴포넌트 추출
        visited = set()
        systems = []
        for start in sp2_keys:
            if start in visited:
                continue
            component = []
            queue = [start]
            visited.add(start)
            while queue:
                node = queue.pop(0)
                component.append(node)
                for nb in adj.get(node, []):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            systems.append(component)
        return systems

    def _draw_p_orbital_lobes(self, sq, pos, normal):
        """sp2 원자의 p 오비탈 두 로브를 반투명 타원체로 그립니다.

        ORCA/Avogadro 기준: p 오비탈 로브는 결합 평면에 수직,
        각 로브 크기 = C-C 결합 길이(1.54Å)의 약 45% ≈ 0.70Å.
        gluSphere + glScalef로 물방울형 로브 생성.
        """
        import math
        nx, ny, nz = normal
        x, y, z = pos
        lobe_size = 0.55    # 로브 반지름 (Å)
        lobe_dist = 0.42    # 원자에서 로브 중심까지 거리 (Å)

        # 법선→Z축 회전각 계산
        # [BUG-O1 수정] Z × N = (0,0,1) × (nx,ny,nz) = (-ny, nx, 0)
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

    def _draw_ring_pi_cloud(self, sq, positions, normal):
        """방향족 고리/공액계의 π 전자구름을 위아래 납작 디스크로 그립니다.

        ORCA 기준: 방향족 π MO (HOMO/HOMO-1)는 고리 평면 위아래
        약 0.6~0.8Å에 최대 전자밀도 → 납작한 원판 형태로 시각화.
        gluSphere + glScalef로 디스크 형태 생성.
        """
        import math
        if not positions or len(positions) < 2:
            return

        # 무게중심
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)
        cz = sum(p[2] for p in positions) / len(positions)

        # 반지름
        ring_radius = sum(
            math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2)
            for p in positions
        ) / len(positions)

        nx, ny, nz = normal
        cloud_offset = 0.65   # 면에서 π cloud 중심까지 (Å)
        disk_flat = 0.28      # 납작 정도 (Z 스케일)

        dot_val = max(-1.0, min(1.0, nz))
        angle_deg = math.degrees(math.acos(dot_val))
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

            # 납작한 원판: 반지름에 맞게 XY 확장, Z 축소
            disk_scale = ring_radius * 1.10
            glScalef(disk_scale, disk_scale, disk_flat)

            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            # [FIX-ORBITAL-COLOR] π cloud 색상 직접 설정
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

    # ── Monte Carlo 점밀도 캐시 (lobe_key → List[(x,y,z)]) ──
    _mc_lobe_cache: Dict = {}

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
    # ESP Surface (McMurry-style electrostatic potential map)
    # ------------------------------------------------------------------
    def render_esp_surface(self, mol_data: 'Molecule3DData'):
        """Render an electrostatic potential (ESP) surface using VDW spheres
        colored by Gasteiger partial charges.

        McMurry textbook convention:
          RED   = delta-minus (electron-rich, negative charge)
          GREEN = neutral
          BLUE  = delta-plus  (electron-poor, positive charge)

        Uses RDKit Gasteiger charges when SMILES is available, falls back
        to electronegativity-based heuristic otherwise.
        """
        if not OPENGL_AVAILABLE:
            return

        try:
            sq = self.qm.sphere()
            charges = self._compute_gasteiger_charges(mol_data)

            # Determine max absolute charge for normalization
            abs_charges = [abs(c) for c in charges.values() if math.isfinite(c)]
            max_abs = max(abs_charges) if abs_charges else 0.5
            if max_abs < 1e-6:
                max_abs = 0.5

            # Sort atoms back-to-front for proper transparency blending
            # Use camera-space Z (approximate: just use z coordinate)
            sorted_keys = sorted(
                mol_data.atom_positions.keys(),
                key=lambda k: mol_data.atom_positions[k][2]
            )

            # Enable transparency
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)

            for key in sorted_keys:
                pos = mol_data.atom_positions.get(key)
                if pos is None:
                    continue
                sym = mol_data.atom_symbols.get(key, "C")
                charge = charges.get(key, 0.0)
                if not math.isfinite(charge):
                    charge = 0.0

                # Normalize charge to [-1, +1]
                norm = max(-1.0, min(1.0, charge / max_abs))

                # ESP color mapping: negative→RED, zero→GREEN, positive→BLUE
                r, g, b = self._esp_charge_to_color(norm)
                alpha = 0.75

                # Set material with ESP color
                glColor4f(r, g, b, alpha)
                glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT,
                             [r * 0.30, g * 0.30, b * 0.30, alpha])
                glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE,
                             [r, g, b, alpha])
                glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,
                             [0.4, 0.4, 0.4, alpha])
                glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 40.0)

                # Draw VDW sphere
                vdw_r = get_vdw_radius(sym)
                cx, cy, cz = pos
                glPushMatrix()
                glTranslatef(cx, cy, cz)
                gluSphere(sq, vdw_r, 32, 24)
                glPopMatrix()

            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)

        except Exception as e:
            logger.warning("AdvancedOrbitalRenderer.render_esp_surface error: %s", e)

    @staticmethod
    def _esp_charge_to_color(norm: float):
        """Map normalized charge [-1, +1] to RGB color.

        -1 (negative, electron-rich) → RED   (1.0, 0.0, 0.0)
         0 (neutral)                 → GREEN (0.0, 0.85, 0.0)
        +1 (positive, electron-poor) → BLUE  (0.0, 0.0, 1.0)

        Smooth interpolation between these anchors.
        """
        if norm < 0:
            # RED → GREEN as norm goes from -1 → 0
            t = norm + 1.0  # 0..1
            r = 1.0 - t
            g = 0.85 * t
            b = 0.0
        else:
            # GREEN → BLUE as norm goes from 0 → +1
            t = norm  # 0..1
            r = 0.0
            g = 0.85 * (1.0 - t)
            b = t
        return (r, g, b)

    def _compute_gasteiger_charges(self, mol_data: 'Molecule3DData') -> Dict:
        """Compute per-atom partial charges using RDKit Gasteiger method.

        Falls back to Pauling electronegativity heuristic if RDKit is
        unavailable or SMILES is missing.
        Returns: dict mapping atom_key → float charge value.
        """
        charges: Dict = {}
        smiles = getattr(mol_data, 'smiles', '') or ''

        if smiles:
            try:
                from rdkit import Chem
                from rdkit.Chem import AllChem

                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:
                    mol = Chem.AddHs(mol)
                    AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                    AllChem.ComputeGasteigerCharges(mol)

                    # Map RDKit atom indices to mol_data keys
                    # Build symbol-position matching
                    rdkit_charges = []
                    for atom in mol.GetAtoms():
                        q = float(atom.GetProp('_GasteigerCharge'))
                        sym = atom.GetSymbol()
                        rdkit_charges.append((sym, q))

                    # Match by symbol order: group by symbol
                    from collections import defaultdict
                    sym_queue = defaultdict(list)
                    for sym, q in rdkit_charges:
                        sym_queue[sym].append(q)

                    sym_idx = defaultdict(int)
                    for key in mol_data.atom_positions:
                        sym = mol_data.atom_symbols.get(key, "C")
                        idx = sym_idx[sym]
                        if idx < len(sym_queue.get(sym, [])):
                            charges[key] = sym_queue[sym][idx]
                            sym_idx[sym] = idx + 1
                        else:
                            charges[key] = 0.0

                    return charges
            except Exception as e:
                logger.debug("Gasteiger charge computation failed, using fallback: %s", e)

        # Fallback: electronegativity-based heuristic
        EN = {
            'H': 2.20, 'C': 2.55, 'N': 3.04, 'O': 3.44, 'F': 3.98,
            'P': 2.19, 'S': 2.58, 'Cl': 3.16, 'Br': 2.96, 'I': 2.66,
            'B': 2.04, 'Si': 1.90, 'Se': 2.55, 'Li': 0.98, 'Na': 0.93,
            'K': 0.82, 'Mg': 1.31, 'Ca': 1.00, 'Fe': 1.83, 'Zn': 1.65,
        }
        ref_en = 2.55  # carbon reference
        for key in mol_data.atom_positions:
            sym = mol_data.atom_symbols.get(key, "C")
            en = EN.get(sym, 2.55)
            # Higher EN → more negative (electron-attracting)
            charges[key] = -(en - ref_en) * 0.35
        return charges

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
    # [FIX-HYB-001] 혼성궤도 유형별 색상 구분 (한눈에 식별 가능)
    COLOR_SP  = (1.00, 0.40, 0.80, 0.60)   # sp: 분홍 — 선형
    COLOR_SP2 = (0.25, 0.50, 1.00, 0.60)   # sp2: 파랑 — 삼각평면
    COLOR_SP3 = (0.20, 0.80, 0.40, 0.60)   # sp3: 초록 — 사면체

    def _render_hybrid(self, sq, pos, info):
        # [FIX-ORB-H] H 원자는 1s 오비탈 — 로브 렌더링 생략 (페놀 sp3 오류 방지)
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
        # [FIX-HYB-001] 혼성궤도 유형 라벨을 원자 근처에 텍스트로 표시
        self._draw_hyb_indicator(sq, pos, hyb)

    def _sp(self, sq, pos, ndirs):
        """sp: 2 σ 로브 + 2 π 오비탈 쌍 — [FIX-HYB-001] sp 색상(분홍) 적용"""
        dirs = list(ndirs[:2])
        ideal = [(0,0,1),(0,0,-1)]
        while len(dirs) < 2:
            dirs.append(ideal[len(dirs)])
        # σ 로브에 sp 고유 색상 사용
        sp_pos = (self.COLOR_SP[0], self.COLOR_SP[1], self.COLOR_SP[2], 0.60)
        sp_neg = (self.COLOR_SP[0]*0.6, self.COLOR_SP[1]*0.6, self.COLOR_SP[2]*0.6, 0.55)
        self._lobe(sq, pos, dirs[0], 2.5, 0.45, sp_pos)
        self._lobe(sq, pos, dirs[1], 2.5, 0.45, sp_neg)
        # π 오비탈: σ축에 수직인 두 방향
        p1 = self._perp(dirs[0])
        p2 = self._cross3(dirs[0], p1)
        for pv in (p1, p2):
            for s in (+1, -1):
                self._lobe(sq, pos, (pv[0]*s, pv[1]*s, pv[2]*s), 2.0, 0.42, self.COLOR_PI)

    def _sp2(self, sq, pos, ndirs):
        """sp2: 3 σ 로브 + 1 π 오비탈 (면 수직) — [FIX-HYB-001] sp2 색상(파랑) 적용"""
        dirs = list(ndirs[:3])
        ideal = [(1,0,0),(-0.5,0.866,0),(-0.5,-0.866,0)]
        while len(dirs) < 3:
            dirs.append(ideal[len(dirs)])
        # σ 로브에 sp2 고유 색상 사용
        sp2_col = (self.COLOR_SP2[0], self.COLOR_SP2[1], self.COLOR_SP2[2], 0.60)
        for i, d in enumerate(dirs[:3]):
            self._lobe(sq, pos, d, 2.2, 0.48, sp2_col)
        # π 오비탈: 분자면 법선
        if len(dirs) >= 2:
            pn = self._cross3(dirs[0], dirs[1])
            pl = math.sqrt(sum(x*x for x in pn))
            if pl > 1e-6:
                pn = tuple(x/pl for x in pn)
                self._lobe(sq, pos, pn, 2.0, 0.52, self.COLOR_SIGMA_NEG)
                self._lobe(sq, pos, tuple(-x for x in pn), 2.0, 0.52, self.COLOR_SIGMA_POS)

    def _sp3(self, sq, pos, ndirs):
        """sp3: 4 σ 로브 (사면체) — [FIX-HYB-001] sp3 색상(초록) 적용"""
        dirs = list(ndirs[:4])
        ideal = [(0.577,0.577,0.577),(0.577,-0.577,-0.577),
                 (-0.577,0.577,-0.577),(-0.577,-0.577,0.577)]
        while len(dirs) < 4:
            dirs.append(ideal[len(dirs)])
        # σ 로브에 sp3 고유 색상 사용
        sp3_col = (self.COLOR_SP3[0], self.COLOR_SP3[1], self.COLOR_SP3[2], 0.60)
        for i, d in enumerate(dirs[:4]):
            self._lobe(sq, pos, d, 2.0, 0.50, sp3_col)

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
    def _generate_mc_lobe_points(self, pos, direction, scale_z, radius, n_points=600, seed=42):
        """Monte Carlo rejection sampling으로 오비탈 로브 점밀도 생성.

        Prolate spheroid 형상의 |ψ|² 비례 점 분포.
        파동함수 근사: ψ(r,θ) ∝ r·cos(θ)·exp(-ζr)
        여기서 θ = 로브 방향(direction)과의 각도.

        Args:
            pos: 원자 중심 좌표 (x, y, z)
            direction: 로브 방향 단위벡터 (nx, ny, nz)
            scale_z: Z 방향 늘림 배율
            radius: 기본 반지름 (Å)
            n_points: 생성할 점 수
            seed: 난수 시드

        Returns: List[(x, y, z)] — 월드 좌표 점 목록
        """
        import random
        rng = random.Random(seed)

        nx, ny, nz = direction
        # 로브 중심 = 원자 위치 + 방향 × (radius × scale_z × 0.5)
        cx = pos[0] + nx * radius * scale_z * 0.5
        cy = pos[1] + ny * radius * scale_z * 0.5
        cz = pos[2] + nz * radius * scale_z * 0.5

        # 로브 반경: 가로(xy) = radius * 0.55, 세로(z) = radius * scale_z
        r_xy = radius * 0.55
        r_z = radius * scale_z * 0.5

        zeta = 2.2  # Slater exponent 근사
        r_max = max(r_xy, r_z) * 1.1  # 샘플링 범위

        # direction 기준 로컬 좌표계 구성
        if abs(nx) < 0.9:
            perp1 = (-nz, 0.0, nx)
        else:
            perp1 = (0.0, nz, -ny)
        len_p1 = math.sqrt(perp1[0]**2 + perp1[1]**2 + perp1[2]**2)
        if len_p1 < 1e-6:
            perp1 = (1.0, 0.0, 0.0)
            len_p1 = 1.0
        perp1 = (perp1[0]/len_p1, perp1[1]/len_p1, perp1[2]/len_p1)
        # perp2 = direction x perp1
        perp2 = (ny*perp1[2] - nz*perp1[1],
                 nz*perp1[0] - nx*perp1[2],
                 nx*perp1[1] - ny*perp1[0])

        points = []
        attempts = 0
        max_attempts = n_points * 10

        while len(points) < n_points and attempts < max_attempts:
            attempts += 1
            # 로컬 좌표 (direction = z축) 에서 균일 샘플링
            lx = rng.uniform(-r_max, r_max)
            ly = rng.uniform(-r_max, r_max)
            lz = rng.uniform(-r_max, r_max)

            # 타원체 내부 체크 (prolate spheroid)
            ellip = (lx/r_xy)**2 + (ly/r_xy)**2 + (lz/r_z)**2
            if ellip > 1.0:
                continue

            # 로컬 반경 및 방향 각도
            r_local = math.sqrt(lx*lx + ly*ly + lz*lz)
            if r_local < 1e-6:
                continue
            cos_theta = abs(lz) / r_local  # 로브 축 방향과의 cos(θ)

            # |ψ|² ∝ r²·cos²(θ)·exp(-2ζr)
            psi_sq = (r_local**2) * (cos_theta**2) * math.exp(-2 * zeta * r_local)
            # 최대값: r=1/zeta, cos_theta=1
            r_opt = 1.0 / zeta
            max_psi_sq = (r_opt**2) * math.exp(-2.0) * 1.1  # 약간 여유

            if max_psi_sq < 1e-12:
                continue
            if rng.random() < psi_sq / max_psi_sq:
                # 로컬 → 월드 좌표 변환
                wx = cx + lx*perp1[0] + ly*perp2[0] + lz*nx
                wy = cy + lx*perp1[1] + ly*perp2[1] + lz*ny
                wz = cz + lx*perp1[2] + ly*perp2[2] + lz*nz
                points.append((wx, wy, wz))

        return points

    def _lobe(self, sq, pos, direction, scale_z: float, radius: float, color: tuple):
        """단일 오비탈 로브를 Monte Carlo 점밀도로 그립니다.

        [MC-DOT-REPLACE] gluSphere prolate spheroid → MC 점밀도 방식.
        |ψ|² 비례 rejection sampling으로 점을 생성하여 GL_POINTS로 렌더링.
        교과서 스타일의 전자 구름 밀도 표현.

        Args:
            scale_z: Z 방향 늘림 배율 (p 오비탈: 2.2, d 로브: 1.4 등)
            radius:  구 기본 반지름 (Å)
        """
        r, g, b, a = color

        # 캐시 키: 위치 + 방향 + 크기 파라미터
        cache_key = (f"{pos[0]:.2f}_{pos[1]:.2f}_{pos[2]:.2f}_"
                     f"{direction[0]:.3f}_{direction[1]:.3f}_{direction[2]:.3f}_"
                     f"{scale_z:.2f}_{radius:.2f}")

        if cache_key not in AdvancedOrbitalRenderer._mc_lobe_cache:
            seed_val = hash(cache_key) & 0xFFFFFF
            # 점 수: scale_z에 비례 (큰 로브 = 더 많은 점)
            n_pts = int(400 * max(1.0, scale_z / 1.5))
            AdvancedOrbitalRenderer._mc_lobe_cache[cache_key] = \
                self._generate_mc_lobe_points(
                    pos, direction, scale_z, radius,
                    n_points=n_pts, seed=seed_val
                )

        points = AdvancedOrbitalRenderer._mc_lobe_cache[cache_key]
        if not points:
            return

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        glDisable(GL_LIGHTING)
        glPointSize(2.5)

        glBegin(GL_POINTS)
        for wx, wy, wz in points:
            glColor4f(r, g, b, a)
            glVertex3f(wx, wy, wz)
        glEnd()

        glEnable(GL_LIGHTING)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)

    def _torus(self, sq, pos, major_r: float, minor_r: float):
        """dz² 오비탈의 도넛(ring) — parametric torus mesh.

        [FIX-FROG-EGG-003] 12개 소구 → 매끄러운 토러스 메시 (GL_TRIANGLE_STRIP).
        Major ring: 36 segments, minor tube: 18 segments for smooth appearance.
        """
        x, y, z = pos
        r, g, b, a = self.COLOR_EG
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        # Full material setup for smooth Phong shading
        glColor4f(r, g, b, a)
        glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [r*0.30, g*0.30, b*0.30, a])
        glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [r, g, b, a])
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.5, 0.5, 0.6, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 50.0)

        n_major = 36  # segments around the ring
        n_minor = 18  # segments around the tube cross-section

        glPushMatrix()
        glTranslatef(x, y, z)

        for i in range(n_major):
            theta0 = 2.0 * math.pi * i / n_major
            theta1 = 2.0 * math.pi * (i + 1) / n_major
            cos_t0, sin_t0 = math.cos(theta0), math.sin(theta0)
            cos_t1, sin_t1 = math.cos(theta1), math.sin(theta1)

            glBegin(GL_TRIANGLE_STRIP)
            for j in range(n_minor + 1):
                phi = 2.0 * math.pi * j / n_minor
                cos_p, sin_p = math.cos(phi), math.sin(phi)

                # Ring 0 (theta0)
                nx0 = cos_t0 * cos_p
                ny0 = sin_t0 * cos_p
                nz0 = sin_p
                vx0 = (major_r + minor_r * cos_p) * cos_t0
                vy0 = (major_r + minor_r * cos_p) * sin_t0
                vz0 = minor_r * sin_p
                glNormal3f(nx0, ny0, nz0)
                glVertex3f(vx0, vy0, vz0)

                # Ring 1 (theta1)
                nx1 = cos_t1 * cos_p
                ny1 = sin_t1 * cos_p
                nz1 = sin_p
                vx1 = (major_r + minor_r * cos_p) * cos_t1
                vy1 = (major_r + minor_r * cos_p) * sin_t1
                vz1 = minor_r * sin_p
                glNormal3f(nx1, ny1, nz1)
                glVertex3f(vx1, vy1, vz1)
            glEnd()

        glPopMatrix()
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)

    def _draw_hyb_indicator(self, sq, pos, hyb):
        """[FIX-HYB-001] 혼성궤도 유형을 색상 구체로 원자 옆에 표시.

        sp=분홍, sp2=파랑, sp3=초록, sp3d/sp3d2=노랑
        원자 약간 위에 작은 구체를 그려 혼성화 유형을 직관적으로 식별.
        """
        hyb_colors = {
            'sp':    self.COLOR_SP,
            'sp2':   self.COLOR_SP2,
            'sp3':   self.COLOR_SP3,
            'sp3d':  (1.00, 0.80, 0.10, 0.70),
            'sp3d2': (1.00, 0.60, 0.00, 0.70),
        }
        color = hyb_colors.get(hyb, self.COLOR_SP3)
        r, g, b, a = color
        x, y, z = pos

        # 원자 위 약간 위에 작은 색상 구체 (혼성 표시기)
        indicator_offset = 0.60  # 원자 위 0.6 Angstrom
        indicator_r = 0.15       # 표시기 반지름

        glPushMatrix()
        glTranslatef(x, y + indicator_offset, z)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        glColor4f(r, g, b, a)
        glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [r, g, b, a])
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 40.0)
        gluSphere(sq, indicator_r, 10, 8)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glPopMatrix()

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
        # 진동 애니메이션 상태
        self.vib_vectors = None
        self.vib_scale = 0.0
        self._vib_active = False
        self._vib_phase = 0.0
        self._vib_amplitude = 1.5
        self._vib_timer = QTimer(self)
        self._vib_timer.timeout.connect(self._vib_tick)
        self._vib_highlight_indices = set()  # [VIB-SPEC] 하이라이트 원자 인덱스
        # 단백질/도킹 시각화 상태
        self._protein_ca = []
        self._binding_site = None
        self._binding_site_radius = 8.0
        self._dock_pose_coords = None
        self._dock_pose_elements = None
        self._dock_approach_offset = None
        self._dock_approach_step = 0
        self._update_transform()

    def set_mol_data(self, md):
        self.mol_data = md
        self._update_transform()
        self.update()

    def start_vibration(self, vectors, amplitude=1.5):
        """진동 모드 애니메이션 시작"""
        self.vib_vectors = vectors
        self._vib_amplitude = amplitude
        self._vib_phase = 0.0
        self._vib_active = True
        self._vib_timer.start(30)  # ~33 fps

    def stop_vibration(self):
        """진동 모드 애니메이션 정지"""
        self._vib_active = False
        self._vib_timer.stop()
        self.vib_vectors = None
        self.vib_scale = 0.0
        self._update_transform()
        self.update()

    def _vib_tick(self):
        """진동 애니메이션 프레임 업데이트"""
        self._vib_phase += 0.1
        self.vib_scale = math.sin(self._vib_phase) * self._vib_amplitude
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
        # 원자 인덱스 맵 구축 (진동 벡터는 인덱스 기반)
        atom_keys = list(self.mol_data.atom_positions.keys())
        for idx, key in enumerate(atom_keys):
            x, y, z = self.mol_data.atom_positions[key]
            # 진동 변위 적용
            if self.vib_vectors and self.vib_scale != 0.0 and idx < len(self.vib_vectors):
                vx, vy, vz = self.vib_vectors[idx]
                x += vx * self.vib_scale
                y += vy * self.vib_scale
                z += vz * self.vib_scale
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
        # Bonds — [FIX-3D-005] 진동 시 결합 신축 색상 코딩
        _qp_has_vib = self.vib_vectors is not None and self._vib_active and abs(self.vib_scale) > 0.001
        for (k1, k2), order in self.mol_data.bonds.items():
            if k1 in spos and k2 in spos:
                s1, s2 = spos[k1], spos[k2]
                avg = (s1[2] + s2[2]) / 2
                g = int(100 * avg)
                bw = max(1, int(2.5 * avg))
                bond_color = QColor(g, g, g)
                if _qp_has_vib and k1 in self.mol_data.atom_positions and k2 in self.mol_data.atom_positions:
                    eq1 = self.mol_data.atom_positions[k1]
                    eq2 = self.mol_data.atom_positions[k2]
                    eq_len = math.sqrt(sum((a-b)**2 for a, b in zip(eq1, eq2)))
                    if eq_len > 0.01:
                        # 실제 displaced 좌표 계산
                        ak = list(self.mol_data.atom_positions.keys())
                        i1 = ak.index(k1) if k1 in ak else -1
                        i2 = ak.index(k2) if k2 in ak else -1
                        if i1 >= 0 and i2 >= 0 and i1 < len(self.vib_vectors) and i2 < len(self.vib_vectors):
                            d1 = self.mol_data.atom_positions[k1]
                            d2 = self.mol_data.atom_positions[k2]
                            v1 = self.vib_vectors[i1]
                            v2 = self.vib_vectors[i2]
                            dp1 = tuple(d + v * self.vib_scale for d, v in zip(d1, v1))
                            dp2 = tuple(d + v * self.vib_scale for d, v in zip(d2, v2))
                            disp_len = math.sqrt(sum((a-b)**2 for a, b in zip(dp1, dp2)))
                            strain = (disp_len - eq_len) / eq_len
                            strain_t = max(-1.0, min(1.0, strain / 0.15))
                            if strain_t > 0.02:
                                t = strain_t
                                bond_color = QColor(int(g + (255-g)*t), int(g*(1-t*0.6)), int(g*(1-t*0.6)))
                            elif strain_t < -0.02:
                                t = -strain_t
                                bond_color = QColor(int(g*(1-t*0.6)), int(g*(1-t*0.3)), int(g + (255-g)*t))
                p.setPen(QPen(bond_color, bw))
                x1, y1, x2, y2 = int(s1[0]), int(s1[1]), int(s2[0]), int(s2[1])
                bo = order
                if isinstance(bo, (float, int)) and abs(bo - 0.5) < 0.01:
                    # 배위결합: 점선
                    pen = QPen(bond_color, max(1, bw - 1))
                    pen.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen)
                    p.drawLine(x1, y1, x2, y2)
                elif isinstance(bo, (float, int)) and (bo >= 1.8 or abs(bo - 1.5) < 0.01):
                    # 이중결합 또는 방향족: 병렬 이중선
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx*dx + dy*dy) if (dx*dx + dy*dy) > 0 else 1
                    off = max(2, bw)  # 오프셋 거리
                    nx, ny = dx/length * off, dy/length * off
                    p.setPen(QPen(bond_color, bw))
                    p.drawLine(int(x1 + nx), int(y1 + ny), int(x2 + nx), int(y2 + ny))
                    p.drawLine(int(x1 - nx), int(y1 - ny), int(x2 - nx), int(y2 - ny))
                elif isinstance(bo, (float, int)) and bo >= 2.8:
                    # 삼중결합: 3선
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx*dx + dy*dy) if (dx*dx + dy*dy) > 0 else 1
                    off = max(2, bw + 1)
                    nx, ny = dx/length * off, dy/length * off
                    p.setPen(QPen(bond_color, bw))
                    p.drawLine(x1, y1, x2, y2)  # 중심선
                    p.drawLine(int(x1 + nx), int(y1 + ny), int(x2 + nx), int(y2 + ny))
                    p.drawLine(int(x1 - nx), int(y1 - ny), int(x2 - nx), int(y2 - ny))
                else:
                    # 단일결합
                    p.drawLine(x1, y1, x2, y2)
        # Atoms — [VIB-SPEC] 진동 하이라이트 인덱스 확인
        _qp_atom_keys = list(self.mol_data.atom_positions.keys())
        _qp_highlight = self._vib_highlight_indices if hasattr(self, '_vib_highlight_indices') else set()
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
            # [VIB-SPEC] 하이라이트: 진동 관련 원자에 발광 링 표시
            _atom_idx = _qp_atom_keys.index(key) if key in _qp_atom_keys else -1
            is_highlighted = _atom_idx in _qp_highlight and len(_qp_highlight) > 0
            if is_highlighted:
                # Draw glow ring
                glow_pen = QPen(QColor(255, 165, 0, 160), max(2, int(rad * 0.25)))
                p.setPen(glow_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(sx, sy), rad + 4, rad + 4)
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
        # 진동 변위 화살표 표시
        if self.vib_vectors and self._vib_active:
            atom_keys = list(self.mol_data.atom_positions.keys())
            arrow_pen = QPen(QColor(0, 255, 100, 200), 2)
            p.setPen(arrow_pen)
            p.setBrush(QBrush(QColor(0, 255, 100, 200)))
            for idx, key in enumerate(atom_keys):
                if key not in spos or idx >= len(self.vib_vectors):
                    continue
                vx, vy, vz = self.vib_vectors[idx]
                mag = math.sqrt(vx*vx + vy*vy + vz*vz)
                if mag < 0.01:
                    continue
                sx, sy, df = spos[key]
                # 변위벡터를 회전 적용 (카메라 좌표계)
                cry2, sry2 = math.cos(math.radians(self.rotation_y)), math.sin(math.radians(self.rotation_y))
                crx2, srx2 = math.cos(math.radians(self.rotation_x)), math.sin(math.radians(self.rotation_x))
                dvx = vx*cry2 + vz*sry2
                dvz = -vx*sry2 + vz*cry2
                dvy = vy*crx2 - dvz*srx2
                arrow_scale = scale * 3.0  # 화살표 크기 증폭
                ex = sx + dvx * arrow_scale
                ey = sy + dvy * arrow_scale
                p.drawLine(int(sx), int(sy), int(ex), int(ey))
                # 화살표 머리
                p.drawEllipse(QPointF(ex, ey), 3, 3)
        # 단백질/도킹 시각화 오버레이
        if self._protein_ca:
            self._paint_protein(p, w, h)
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

    # ── 단백질 도킹 시각화 (QPainter 2.5D) ──────────────────────────
    def set_protein_data(self, ca_atoms, binding_site=None):
        """단백질 Cα 백본 데이터 설정"""
        self._protein_ca = ca_atoms
        self._binding_site = binding_site
        self._binding_site_radius = 8.0
        self._dock_approach_offset = None
        self._dock_approach_timer = QTimer(self)
        self._dock_approach_timer.timeout.connect(self._dock_approach_tick)
        self.update()

    def set_docking_pose(self, atom_coords, atom_elements,
                         binding_center=None, binding_radius=8.0):
        """도킹 포즈 좌표 설정"""
        self._dock_pose_coords = atom_coords
        self._dock_pose_elements = atom_elements
        if binding_center:
            self._binding_site = binding_center
        self._binding_site_radius = binding_radius
        self.update()

    def start_dock_approach(self, start_offset=(40.0, 0.0, 0.0)):
        """리간드 접근 애니메이션"""
        self._dock_approach_offset = list(start_offset)
        self._dock_approach_step = 0
        if not hasattr(self, '_dock_approach_timer'):
            self._dock_approach_timer = QTimer(self)
            self._dock_approach_timer.timeout.connect(self._dock_approach_tick)
        self._dock_approach_timer.start(30)

    def _dock_approach_tick(self):
        """접근 애니메이션 프레임"""
        if self._dock_approach_offset is None:
            self._dock_approach_timer.stop()
            return
        self._dock_approach_step += 1
        decay = max(0.0, 1.0 - self._dock_approach_step / 60.0)
        self._dock_approach_offset = [
            self._dock_approach_offset[0] * 0.93,
            self._dock_approach_offset[1] * 0.93,
            self._dock_approach_offset[2] * 0.93,
        ]
        if decay <= 0.02:
            self._dock_approach_offset = None
            self._dock_approach_timer.stop()
        self.update()

    def _paint_protein(self, p, w, h):
        """단백질 Cα 백본 + 도킹 포즈 그리기"""
        if not hasattr(self, '_protein_ca') or not self._protein_ca:
            return
        ca = self._protein_ca
        # 단백질 중심 계산
        xs = [a[1] for a in ca]; ys = [a[2] for a in ca]; zs = [a[3] for a in ca]
        pcx, pcy, pcz = sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs)
        # 단백질 크기
        rng = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs), 1.0)
        pscale = min(w, h) / (rng + 10.0) * 0.3 * self.zoom_scale
        ox, oy = w/2 + self.pan_x, h/2 + self.pan_y
        cry, sry = math.cos(math.radians(self.rotation_y)), math.sin(math.radians(self.rotation_y))
        crx, srx = math.cos(math.radians(self.rotation_x)), math.sin(math.radians(self.rotation_x))

        def project(x, y, z):
            dx, dy, dz = x-pcx, y-pcy, z-pcz
            rx = dx*cry + dz*sry
            rz_tmp = -dx*sry + dz*cry
            ry = dy*crx - rz_tmp*srx
            return ox + rx*pscale, oy + ry*pscale

        # 백본 라인
        prev = None
        chain_colors = {"A": QColor(80,160,255,120), "B": QColor(80,255,160,120)}
        for res, x, y, z, chain in ca:
            sx, sy = project(x, y, z)
            color = chain_colors.get(chain, QColor(150,150,200,100))
            if prev and prev[2] == chain:
                p.setPen(QPen(color, 1))
                p.drawLine(int(prev[0]), int(prev[1]), int(sx), int(sy))
            prev = (sx, sy, chain)

        # 결합 부위 원
        if hasattr(self, '_binding_site') and self._binding_site:
            bx, by = project(*self._binding_site)
            r = self._binding_site_radius * pscale * 0.5
            p.setPen(QPen(QColor(255,255,0,80), 2, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(255,255,0,20)))
            p.drawEllipse(QPointF(bx, by), r, r)

        # 도킹 포즈 원자
        if hasattr(self, '_dock_pose_coords') and self._dock_pose_coords:
            off = self._dock_approach_offset or [0, 0, 0]
            elem_colors = {
                "C": QColor(0,255,100), "O": QColor(255,60,60),
                "N": QColor(60,60,255), "H": QColor(200,200,200),
                "S": QColor(255,255,50), "F": QColor(0,255,200),
                "Cl": QColor(0,200,0), "Br": QColor(180,60,0),
            }
            for i, (x, y, z) in enumerate(self._dock_pose_coords):
                sx, sy = project(x + off[0], y + off[1], z + off[2])
                elem = self._dock_pose_elements[i] if i < len(self._dock_pose_elements) else "C"
                color = elem_colors.get(elem, QColor(100,255,100))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(color))
                p.drawEllipse(QPointF(sx, sy), 4, 4)


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
        self._vib_highlight_indices = set()  # [VIB-SPEC] 하이라이트 원자 인덱스

        # [PROTEIN-3D] 단백질 렌더링 데이터
        self._protein_ca = None      # List[(res, x, y, z, chain)] — Cα backbone
        self._protein_center = None  # (cx, cy, cz)
        self._protein_visible = False
        self._dock_approach_phase = -1.0  # <0 = no animation, 0~1 = approach
        self._dock_approach_timer = QTimer(self)
        self._dock_approach_timer.timeout.connect(self._dock_approach_tick)
        self._ligand_offset = (0.0, 0.0, 0.0)  # approach 시 리간드 이동 오프셋
        self._binding_site_center = None  # 결합 부위 중심
        self._binding_site_radius = 8.0  # 결합 부위 반경 (Å)
        self._interaction_lines = []  # [(x1,y1,z1,x2,y2,z2,type)] 상호작용 선

        # [DOCK-POSE] 도킹 포즈 좌표 (Vina 결과 실제 좌표)
        self._docking_pose_atoms = None  # List[(element, x, y, z)]
        self._cached_ligand_bonds = None  # 캐싱된 리간드 결합 리스트
        self._ligand_bonds_dirty = True   # 리간드 결합 재계산 필요 플래그

        # [PERF] 단백질 잔기 렌더링용 캐싱 quadric
        self._protein_quadric = None

        # [RIBBON] 단백질 리본 렌더링
        self._ribbon_mode = False  # False=backbone lines, True=ribbon
        self._secondary_structure = None  # List[str] — 'H'(helix), 'E'(sheet), 'C'(coil)

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

    def set_protein_data(self, ca_atoms, binding_site=None):
        """[PROTEIN-3D] 단백질 Cα 백본 데이터 설정
        ca_atoms: List[(residue_name, x, y, z, chain)]
        binding_site: (cx, cy, cz) — 결합 부위 중심
        """
        self._protein_ca = ca_atoms
        if ca_atoms:
            xs = [a[1] for a in ca_atoms]
            ys = [a[2] for a in ca_atoms]
            zs = [a[3] for a in ca_atoms]
            self._protein_center = (
                sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
            # 단백질+리간드 모두 볼 수 있도록 view scale 조정
            max_range = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))
            self._view_scale = 15.0 / (max_range + 1.0)
            self._center = self._protein_center
        self._binding_site_center = binding_site
        self._protein_visible = True
        self.update()

    def set_docking_pose(self, atom_coords, atom_elements, binding_center=None, binding_radius=8.0):
        """[DOCK-POSE] 실제 Vina 도킹 포즈 좌표로 리간드 배치

        Args:
            atom_coords: List[(x, y, z)] — Vina 결과 좌표 (Å)
            atom_elements: List[str] — 원소 기호
            binding_center: (cx, cy, cz) — DockingConfig.center (검색 박스 중심)
            binding_radius: float — 노란 존 반경 (Å)
        """
        if atom_coords and atom_elements:
            self._docking_pose_atoms = [
                (elem, x, y, z)
                for elem, (x, y, z) in zip(atom_elements, atom_coords)
            ]
            self._ligand_bonds_dirty = True  # 결합 재계산 필요
        else:
            self._docking_pose_atoms = None
            self._cached_ligand_bonds = None

        if binding_center:
            self._binding_site_center = binding_center
            self._binding_site_radius = binding_radius
            # 결합 부위 중심으로 뷰 포커스 (단백질 전체 중심 대신)
            self._center = binding_center
            # 결합 부위 주변만 보이도록 적절한 줌 레벨 설정
            self._view_scale = 15.0 / (binding_radius * 4.0 + 1.0)
        self.update()

    def set_protein_visible(self, visible: bool):
        self._protein_visible = visible
        self.update()

    def start_dock_approach(self, start_offset=(40.0, 0.0, 0.0)):
        """[PROTEIN-3D] 리간드 접근 애니메이션 시작 — 결합부위 근처에서 출발"""
        # 결합 반경의 3~4배에서 시작하여 결합 부위로 접근
        self._dock_start_dist = self._binding_site_radius * 3.5 if self._binding_site_radius > 0 else 25.0
        self._ligand_offset = (self._dock_start_dist, self._dock_start_dist * 0.3, 0.0)
        self._dock_approach_phase = 0.0
        self._dock_approach_timer.start(33)  # ~30 fps

    def _dock_approach_tick(self):
        """도킹 접근 애니메이션 프레임 — 리간드가 결합부위로 접근"""
        self._dock_approach_phase += 0.012  # 약간 더 느리게 (관찰 시간 확보)
        if self._dock_approach_phase >= 1.0:
            self._dock_approach_phase = -1.0  # 완료
            self._ligand_offset = (0.0, 0.0, 0.0)
            self._dock_approach_timer.stop()
        else:
            # ease-in: 처음엔 빠르다가 결합부위 근처에서 감속
            t = self._dock_approach_phase
            # 3단계: 0~0.3 빠른 접근, 0.3~0.7 감속, 0.7~1.0 미세 조정
            if t < 0.3:
                ease = (t / 0.3) * 0.6  # 0→0.6
            elif t < 0.7:
                ease = 0.6 + ((t - 0.3) / 0.4) * 0.3  # 0.6→0.9
            else:
                ease = 0.9 + ((t - 0.7) / 0.3) * 0.1  # 0.9→1.0
            start_dist = getattr(self, '_dock_start_dist', 25.0)
            ox = start_dist * (1.0 - ease)
            oy = start_dist * 0.3 * (1.0 - ease)  # 약간 위에서 접근
            oz = 0.0
            self._ligand_offset = (ox, oy, oz)
        self.update()

    def _draw_protein(self):
        """[PROTEIN-3D] OpenGL 단백질 Cα 백본 렌더링
        [PERF] 거대 분자 크기 가드 — Cα 수에 따라 렌더링 수준 자동 조절"""
        if not self._protein_ca or not OPENGL_AVAILABLE:
            return
        n_ca = len(self._protein_ca)
        try:
            if n_ca > 5000:
                # 거대 구조 — 렌더링 건너뜀, 경고 1회 표시
                if not getattr(self, '_macro_warn_shown', False):
                    logger.warning(f"거대 구조 ({n_ca} Cα): 렌더링 건너뜀. PyMOL/ChimeraX 권장.")
                    self._macro_warn_shown = True
                return
            if n_ca > 1000:
                # 대형 단백질 — 단순 backbone line만
                self._draw_protein_backbone_simple()
                return
            if n_ca > 300:
                # 중형 단백질 — ribbon 전용 (ball-and-stick 금지)
                self._draw_protein_ribbon_only()
                return
            self._draw_protein_impl()
        except Exception as e:
            logger.error(f"Protein render error: {e}")
            self._protein_visible = False  # 재크래시 방지

    def _draw_protein_backbone_simple(self):
        """[PERF] 대형 단백질용 초경량 backbone — GL_LINE_STRIP만 사용"""
        glDisable(GL_LIGHTING)
        glLineWidth(1.5)
        chains = {}
        for res, x, y, z, ch in self._protein_ca:
            chains.setdefault(ch, []).append((x, y, z))
        chain_colors = {
            'A': (0.3, 0.6, 0.9), 'B': (0.9, 0.5, 0.3),
            'C': (0.4, 0.8, 0.4), 'D': (0.8, 0.4, 0.8),
            'E': (0.9, 0.9, 0.3), 'F': (0.3, 0.8, 0.8),
        }
        default_color = (0.5, 0.5, 0.6)
        for ch, coords in chains.items():
            color = chain_colors.get(ch, default_color)
            glColor3f(*color)
            glBegin(GL_LINE_STRIP)
            for x, y, z in coords:
                glVertex3f(x, y, z)
            glEnd()
        glEnable(GL_LIGHTING)
        glLineWidth(1.0)

    def _draw_protein_ribbon_only(self):
        """[PERF] 중형 단백질용 ribbon 전용 렌더링 (sticks 없음)"""
        chain_colors = {
            'A': (0.3, 0.6, 0.9), 'B': (0.9, 0.5, 0.3),
            'C': (0.4, 0.8, 0.4), 'D': (0.8, 0.4, 0.8),
            'E': (0.9, 0.9, 0.3), 'F': (0.3, 0.8, 0.8),
        }
        default_color = (0.5, 0.5, 0.6)
        if self._ribbon_mode and self._secondary_structure:
            self._draw_ribbon(chain_colors, default_color)
        else:
            # ribbon 데이터 미준비 시 backbone fallback
            self._draw_backbone_lines(chain_colors, default_color)

    def toggle_ribbon_mode(self):
        """Backbone ↔ Ribbon 모드 전환"""
        self._ribbon_mode = not self._ribbon_mode
        if self._ribbon_mode and self._protein_ca and self._secondary_structure is None:
            self._detect_secondary_structure()
        self.update()

    def _detect_secondary_structure(self):
        """간이 DSSP: Cα 거리 + 패턴 기반 2차 구조 추정

        α-helix: Cα(i)→Cα(i+3) ≈ 5.0-5.5Å, 연속 4+ 잔기
        β-sheet: Cα(i)→Cα(i+2) ≈ 6.5-7.0Å, 연속 3+ 잔기
        """
        if not self._protein_ca:
            return

        # 체인별로 분리
        chains = {}
        for idx, (res, x, y, z, ch) in enumerate(self._protein_ca):
            chains.setdefault(ch, []).append((idx, x, y, z))

        ss = ['C'] * len(self._protein_ca)  # default: coil

        for ch, atoms in chains.items():
            n = len(atoms)
            if n < 4:
                continue

            # 1차: α-helix 검출 — Cα(i)→Cα(i+3) 거리
            helix_flags = [False] * n
            for i in range(n - 3):
                _, x0, y0, z0 = atoms[i]
                _, x3, y3, z3 = atoms[i + 3]
                d13 = math.sqrt((x3-x0)**2 + (y3-y0)**2 + (z3-z0)**2)
                if 4.8 <= d13 <= 5.8:
                    helix_flags[i] = True
                    helix_flags[i+1] = True
                    helix_flags[i+2] = True
                    helix_flags[i+3] = True

            # 연속 4+ 잔기 필터
            run_start = -1
            for i in range(n):
                if helix_flags[i]:
                    if run_start < 0:
                        run_start = i
                else:
                    if run_start >= 0 and (i - run_start) >= 4:
                        for j in range(run_start, i):
                            gi = atoms[j][0]
                            if gi < len(ss):
                                ss[gi] = 'H'
                    run_start = -1
            if run_start >= 0 and (n - run_start) >= 4:
                for j in range(run_start, n):
                    gi = atoms[j][0]
                    if gi < len(ss):
                        ss[gi] = 'H'

            # 2차: β-sheet 검출 — Cα(i)→Cα(i+2) 거리 (helix가 아닌 곳에서만)
            sheet_flags = [False] * n
            for i in range(n - 2):
                gi_check = atoms[i][0]
                if gi_check < len(ss) and ss[gi_check] == 'H':
                    continue
                _, x0, y0, z0 = atoms[i]
                _, x2, y2, z2 = atoms[i + 2]
                d12 = math.sqrt((x2-x0)**2 + (y2-y0)**2 + (z2-z0)**2)
                if 6.2 <= d12 <= 7.2:
                    sheet_flags[i] = True
                    sheet_flags[i+1] = True
                    sheet_flags[i+2] = True

            run_start = -1
            for i in range(n):
                if sheet_flags[i]:
                    if run_start < 0:
                        run_start = i
                else:
                    if run_start >= 0 and (i - run_start) >= 3:
                        for j in range(run_start, i):
                            gi = atoms[j][0]
                            if gi < len(ss) and ss[gi] != 'H':
                                ss[gi] = 'E'
                    run_start = -1
            if run_start >= 0 and (n - run_start) >= 3:
                for j in range(run_start, n):
                    gi = atoms[j][0]
                    if gi < len(ss) and ss[gi] != 'H':
                        ss[gi] = 'E'

        self._secondary_structure = ss

    def _draw_protein_impl(self):
        """실제 단백질 렌더링 구현"""
        chain_colors = {
            'A': (0.3, 0.6, 0.9), 'B': (0.9, 0.5, 0.3),
            'C': (0.4, 0.8, 0.4), 'D': (0.8, 0.4, 0.8),
            'E': (0.9, 0.9, 0.3), 'F': (0.3, 0.8, 0.8),
        }
        default_color = (0.5, 0.5, 0.6)

        if self._ribbon_mode and self._secondary_structure:
            self._draw_ribbon(chain_colors, default_color)
        else:
            self._draw_backbone_lines(chain_colors, default_color)

        # [PERF] 캐싱된 quadric 사용 — 매 프레임 생성/삭제 방지
        if self._protein_quadric is None:
            self._protein_quadric = gluNewQuadric()
        pq = self._protein_quadric

        # 결합 부위 표시 (반투명 구)
        # [FIX] 깊이 쓰기 비활성 + 뒷면 제거로 과도한 알파 축적 방지
        if self._binding_site_center:
            bx, by, bz = self._binding_site_center
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)       # 깊이 버퍼 쓰기 비활성 (투명체 렌더링)
            glEnable(GL_CULL_FACE)      # 뒷면 컬링 활성
            glCullFace(GL_BACK)         # 뒷면만 제거 → 앞면만 렌더
            glDisable(GL_LIGHTING)      # 조명 끄고 순수 색상
            glColor4f(1.0, 0.85, 0.3, 0.10)  # 밝고 투명한 노란색
            glPushMatrix()
            glTranslatef(bx, by, bz)
            gluSphere(pq, self._binding_site_radius, 24, 24)
            glPopMatrix()
            glDisable(GL_CULL_FACE)
            glDepthMask(GL_TRUE)
            glEnable(GL_LIGHTING)
            glDisable(GL_BLEND)

        # 결합 부위 주변 잔기 (sticks)
        if self._binding_site_center:
            bx, by, bz = self._binding_site_center
            glEnable(GL_LIGHTING)
            for res, x, y, z, ch in self._protein_ca:
                dist = math.sqrt((x-bx)**2 + (y-by)**2 + (z-bz)**2)
                if dist < 12.0:
                    color = chain_colors.get(ch, default_color)
                    glColor3f(*[c * 1.3 for c in color])
                    glPushMatrix()
                    glTranslatef(x, y, z)
                    gluSphere(pq, 0.5, 8, 8)
                    glPopMatrix()

        glEnable(GL_LIGHTING)
        glLineWidth(1.0)

    def _draw_backbone_lines(self, chain_colors, default_color):
        """Cα backbone as GL_LINE_STRIP (기존 모드)"""
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        chains = {}
        for res, x, y, z, ch in self._protein_ca:
            chains.setdefault(ch, []).append((x, y, z, res))
        for ch, atoms in chains.items():
            color = chain_colors.get(ch, default_color)
            glColor3f(*color)
            glBegin(GL_LINE_STRIP)
            for x, y, z, _ in atoms:
                glVertex3f(x, y, z)
            glEnd()

    def _draw_ribbon(self, chain_colors, default_color):
        """[RIBBON] 2차 구조 기반 리본 렌더링

        α-helix: 빨강 원통 (반경 1.5Å)
        β-sheet: 노랑 평면 리본 (너비 2.5Å)
        Coil: 얇은 튜브 (반경 0.3Å)
        """
        ss = self._secondary_structure
        if not ss:
            self._draw_backbone_lines(chain_colors, default_color)
            return

        glEnable(GL_LIGHTING)
        cq = gluNewQuadric()

        # 체인별 처리
        chains = {}
        for idx, (res, x, y, z, ch) in enumerate(self._protein_ca):
            chains.setdefault(ch, []).append((idx, x, y, z, res))

        for ch, atoms in chains.items():
            n = len(atoms)
            base_color = chain_colors.get(ch, default_color)

            for i in range(n - 1):
                idx0, x0, y0, z0, _ = atoms[i]
                idx1, x1, y1, z1, _ = atoms[i + 1]
                struct = ss[idx0]

                dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
                length = math.sqrt(dx*dx + dy*dy + dz*dz)
                if length < 0.01:
                    continue

                # 2차 구조별 색상 + 반경
                if struct == 'H':
                    # α-helix: 빨강 계열 튜브
                    r, g, b = 0.85, 0.25, 0.25
                    radius = 1.2
                elif struct == 'E':
                    # β-sheet: 노랑 계열 넓적한 튜브
                    r, g, b = 0.9, 0.8, 0.2
                    radius = 0.8
                else:
                    # Coil: 체인 색상 얇은 튜브
                    r, g, b = base_color
                    radius = 0.25

                _set_material(r, g, b)

                glPushMatrix()
                glTranslatef(x0, y0, z0)

                # 방향 벡터 → 회전 (Z축 기준)
                ax = -dy
                ay = dx
                az = 0.0
                al = math.sqrt(ax*ax + ay*ay + az*az)
                angle = math.degrees(math.acos(max(-1.0, min(1.0, dz / length))))
                if al > 1e-6:
                    glRotatef(angle, ax / al, ay / al, az / al)
                elif dz < 0:
                    glRotatef(180, 1, 0, 0)

                if struct == 'E':
                    # β-sheet: 납작한 직육면체로 근사
                    w = 2.0  # 너비
                    h = 0.4  # 두께
                    glScalef(w, h, 1.0)
                    gluCylinder(cq, 0.5, 0.5, length, 4, 1)
                    glScalef(1.0/w, 1.0/h, 1.0)
                else:
                    # 원통 (helix/coil)
                    slices = 12 if struct == 'H' else 6
                    gluCylinder(cq, radius, radius, length, slices, 1)

                glPopMatrix()

        gluDeleteQuadric(cq)

    def _precompute_ligand_bonds(self, atoms):
        """리간드 결합을 공간 해시로 1회 계산 후 캐싱 — O(n) average"""
        from collections import defaultdict
        cell_size = 3.5  # Å — max bond length ~2.8Å * 1.25
        grid = defaultdict(list)

        for i, (elem, x, y, z) in enumerate(atoms):
            cx, cy, cz = int(x / cell_size), int(y / cell_size), int(z / cell_size)
            grid[(cx, cy, cz)].append(i)

        bonds = []
        for i, (ei, xi, yi, zi) in enumerate(atoms):
            ci = (int(xi / cell_size), int(yi / cell_size), int(zi / cell_size))
            ri = get_covalent_radius(ei)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for j in grid.get((ci[0]+dx, ci[1]+dy, ci[2]+dz), []):
                            if j <= i:
                                continue
                            ej, xj, yj, zj = atoms[j]
                            rj = get_covalent_radius(ej)
                            dist = math.sqrt((xj-xi)**2 + (yj-yi)**2 + (zj-zi)**2)
                            if 0.4 < dist < (ri + rj) * 1.3:
                                bonds.append((i, j, dist))
        return bonds

    def _draw_docking_ligand(self):
        """[DOCK-POSE] Vina 실제 도킹 포즈 좌표로 리간드 ball-and-stick 렌더링
        [PERF] 결합 탐색을 공간 해시로 사전 계산하여 O(n) 평균 복잡도 달성"""
        if not self._docking_pose_atoms or not OPENGL_AVAILABLE:
            return
        try:
            glEnable(GL_LIGHTING)
            sq = gluNewQuadric()
            cq = gluNewQuadric()

            atoms = self._docking_pose_atoms  # [(element, x, y, z), ...]

            # 원자 렌더링
            for elem, x, y, z in atoms:
                r, g, b = get_cpk_color(elem)
                _set_material(r, g, b)
                rad = get_covalent_radius(elem) * 0.35
                glPushMatrix()
                glTranslatef(x, y, z)
                gluSphere(sq, rad, 16, 12)
                glPopMatrix()

            # [PERF] 결합 사전 계산 — 리간드 데이터 변경 시에만 재계산
            if self._ligand_bonds_dirty or self._cached_ligand_bonds is None:
                self._cached_ligand_bonds = self._precompute_ligand_bonds(atoms)
                self._ligand_bonds_dirty = False

            # 캐싱된 결합 렌더링
            _set_material(0.6, 0.6, 0.6)
            for i, j, dist in self._cached_ligand_bonds:
                ei, xi, yi, zi = atoms[i]
                ej, xj, yj, zj = atoms[j]
                dx, dy, dz = xj - xi, yj - yi, zj - zi
                glPushMatrix()
                glTranslatef(xi, yi, zi)
                length = dist
                if length > 1e-6:
                    ax = -dy
                    ay = dx
                    az = 0.0
                    al = math.sqrt(ax * ax + ay * ay + az * az)
                    angle = math.degrees(math.acos(max(-1.0, min(1.0, dz / length))))
                    if al > 1e-6:
                        glRotatef(angle, ax / al, ay / al, az / al)
                    elif dz < 0:
                        glRotatef(180, 1, 0, 0)
                    gluCylinder(cq, 0.06, 0.06, length, 8, 1)
                glPopMatrix()

            gluDeleteQuadric(sq)
            gluDeleteQuadric(cq)
        except Exception as e:
            logger.error(f"Docking ligand render error: {e}")

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

        # [PROTEIN-3D] 단백질 백본 먼저 렌더링 (배경)
        if self._protein_visible and self._protein_ca:
            self._draw_protein()

        # [DOCK-POSE] 도킹 포즈 좌표가 있으면 Vina 실제 좌표로 리간드 렌더링
        if self._docking_pose_atoms and self._protein_visible:
            if self._dock_approach_phase >= 0:
                glPushMatrix()
                ox, oy, oz = self._ligand_offset
                glTranslatef(ox, oy, oz)
            self._draw_docking_ligand()
            if self._dock_approach_phase >= 0:
                glPopMatrix()
        elif self.mol_data:
            # 일반 분자 렌더링 (도킹 아닐 때)
            need_pop = False
            if self._protein_visible and self._binding_site_center:
                # [FIX-DOCK-POS] 도킹 모드: 리간드를 결합부위 중심으로 이동
                # RDKit 3D 좌표는 원점 근처 → 단백질 PDB 좌표계의 결합부위로 변환
                glPushMatrix()
                bx, by, bz = self._binding_site_center
                # mol_data 무게중심 계산
                positions = list(self.mol_data.atom_positions.values())
                if positions:
                    mcx = sum(p[0] for p in positions) / len(positions)
                    mcy = sum(p[1] for p in positions) / len(positions)
                    mcz = sum(p[2] for p in positions) / len(positions)
                else:
                    mcx = mcy = mcz = 0.0
                # 리간드 무게중심 → 결합부위 중심으로 이동
                glTranslatef(bx - mcx, by - mcy, bz - mcz)
                # 추가: 접근 애니메이션 오프셋
                if self._dock_approach_phase >= 0:
                    ox, oy, oz = self._ligand_offset
                    glTranslatef(ox, oy, oz)
                need_pop = True
            elif self._dock_approach_phase >= 0:
                glPushMatrix()
                ox, oy, oz = self._ligand_offset
                glTranslatef(ox, oy, oz)
                need_pop = True

            vv = self.vib_vectors if self._vib_active else None
            vs = self.vib_scale if self._vib_active else 0.0
            small = (self.orbital_mode != 'none')
            if self.render_mode == "ball_and_stick":
                self._bs.render(self.mol_data, vv, vs, small_atoms=small)
                # ★ 입체 결합 (웨지/대쉬) 시각화
                self._bs.render_stereo_bonds(self.mol_data)
            else:
                self._sf.render(self.mol_data, vv, vs)
            # 오비탈 렌더링 (모드에 따라 분기)
            if self.orbital_mode == 'pi':
                self._pi.render(self.mol_data)
            elif self.orbital_mode == 'all':
                self._adv.render_esp_surface(self.mol_data)
            elif self.orbital_mode in ('hybrid', 'd_orbital', 'f_orbital'):
                self._adv.render(self.mol_data, orbital_mode=self.orbital_mode)

            if need_pop:
                glPopMatrix()

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
        # [PERF] 캐싱된 단백질 quadric 정리
        if self._protein_quadric:
            try:
                gluDeleteQuadric(self._protein_quadric)
            except Exception:
                pass
            self._protein_quadric = None


# ============================================================
# Section 10: Tab Panels
# ============================================================

class PropertiesPanel(QWidget):
    """📊 속성 탭 — RDKit 계산값 + PubChem DB"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        # [FIX-SCROLL-001] QScrollArea로 감싸 창 높이 부족 시 스크롤 가능
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner_widget = QWidget()
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
        inner_widget.setLayout(layout)
        scroll_area.setWidget(inner_widget)
        outer_layout.addWidget(scroll_area)
        self.setLayout(outer_layout)

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

        # ── matplotlib 캔버스 (리사이즈 반응형) ──
        self.figure = Figure(dpi=100)
        self.figure.patch.set_facecolor("#1e1e1e")
        self.figure.set_tight_layout(True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.setMinimumHeight(180)
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

    def resizeEvent(self, event):
        """Reapply tight_layout when the panel is resized so the graph fills the width."""
        super().resizeEvent(event)
        try:
            if hasattr(self, 'figure') and self.figure and self.figure.axes:
                self.figure.tight_layout()
                self.canvas.draw_idle()
        except Exception:
            pass

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
                # AI 피크 분석용 데이터 저장 (IRPeak.wavenumber, .transmittance)
                if spec.ir_peaks:
                    self.frequencies = [p.wavenumber for p in spec.ir_peaks]
                    self.intensities = [100.0 - p.transmittance for p in spec.ir_peaks]  # 흡수 강도로 변환
            elif _t == "RAMAN":
                new_fig = _make_raman_figure(spec.raman_peaks)
                if spec.raman_peaks:
                    self.frequencies = [p.shift for p in spec.raman_peaks]
                    self.intensities = [p.intensity for p in spec.raman_peaks]
            elif _t in ("NMRH", "1HNMR", "NMR", "NMR_H"):
                new_fig = _make_nmr_h1_figure(spec.h1_nmr_peaks, spec.formula, smiles=smiles)
            elif _t in ("NMRC13", "13CNMR", "NMR_C13", "C13"):
                new_fig = _make_nmr_c13_figure(spec.c13_peaks, spec.formula, smiles=smiles)
            elif _t in ("UVVIS", "UV"):
                new_fig = _make_uvvis_figure(spec.uvvis_peaks)
            else:
                new_fig = _make_ir_figure(spec.ir_peaks)
                if spec.ir_peaks:
                    self.frequencies = [p.wavenumber for p in spec.ir_peaks]
                    self.intensities = [100.0 - p.transmittance for p in spec.ir_peaks]
            # AI 분석 캐시 초기화 (새 스펙트럼이니 재분석 필요)
            self.ai_analysis_data = None
            self.ai_annotations = []
            self.ai_overlay_visible = False
            if hasattr(self, 'btn_ai_overlay'):
                self.btn_ai_overlay.setChecked(False)
            # FigureCanvas에 새 figure 연결 — resize to fill full tab width
            canvas_w = self.canvas.width()
            canvas_h = self.canvas.height()
            if canvas_w > 100 and canvas_h > 50:
                dpi = new_fig.get_dpi()
                new_fig.set_size_inches(canvas_w / dpi, canvas_h / dpi)
            new_fig.set_tight_layout(True)
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
    def _resolve_smiles(self) -> str:
        """SMILES를 다중 소스에서 확보: _smiles_cache > 부모 popup > mol_data."""
        smiles = getattr(self, '_smiles_cache', '') or ''
        if smiles:
            return smiles
        # 부모 Molecule3DPopup에서 SMILES 탐색
        popup = self.parent()
        while popup and not isinstance(popup, Molecule3DPopup):
            popup = popup.parent() if hasattr(popup, 'parent') else None
        if popup:
            md = getattr(popup, 'mol_data', None)
            if md and getattr(md, 'smiles', ''):
                smiles = md.smiles
                self._smiles_cache = smiles
                return smiles
            cs = getattr(popup, '_current_smiles', '')
            if cs:
                self._smiles_cache = cs
                return cs
        return ''

    def _export_pdf(self):
        """모든 스펙트럼을 고품질 PDF로 일괄 출력 (SpectrumPDFExporter 사용).
        6종 스펙트럼: IR, Raman, 1H NMR, 13C NMR, UV-Vis, Mass Spectrum.
        """
        if not MATPLOTLIB_AVAILABLE:
            self.info_label.setText("⚠️ matplotlib 미설치")
            return
        smiles = self._resolve_smiles()
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
        _default_name = f"{_safe_smiles}_all_spectra_{_ts}.pdf"

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

        # PDF 저장 — 6종 스펙트럼 일괄 출력
        self.info_label.setText("🔄 PDF 생성 중 (6종 스펙트럼 일괄 출력)...")
        QApplication.processEvents()

        # [STEP 1] 스펙트럼 데이터 수집 (6종: IR, Raman, 1H NMR, 13C NMR, UV-Vis, MS)
        spectra_data = {}
        if smiles and RDKIT_AVAILABLE:
            import numpy as _np
            # 6종 스펙트럼 생성 (MS 포함)
            for st, key in [("IR", "IR"), ("Raman", "Raman"),
                             ("NMR_H", "NMR_1H"), ("NMR_C13", "NMR_13C"),
                             ("UV-Vis", "UV-Vis"), ("MS", "Mass")]:
                try:
                    fq, it = predict_spectrum_from_smiles(smiles, st)
                    if not fq:
                        logger.debug("predict_spectrum_from_smiles returned empty for %s", st)
                        continue
                    if st == "IR":
                        x = _np.linspace(400, 4000, 1000)
                        y = _np.ones_like(x) * 100
                        gamma = 20.0
                        max_it = max(it) if it else 1.0
                        for f, intensity in zip(fq, it):
                            y -= intensity / max_it * 80 * (gamma**2 / ((x - f)**2 + gamma**2))
                        spectra_data[key] = {"x": x, "y": y,
                            "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                            "notes": "SMILES 기반 예측 IR 스펙트럼", "smiles": smiles}
                    elif st in ("NMR_H", "NMR_C13"):
                        xmin, xmax = (-1, 12) if st == "NMR_H" else (-5, 225)
                        x = _np.linspace(xmin, xmax, 2000)
                        y = _np.zeros_like(x)
                        for f, intensity in zip(fq, it):
                            g = 0.05 if st == "NMR_H" else 0.8
                            y += intensity * (g**2 / ((x - f)**2 + g**2))
                        y_max = y.max()
                        if y_max > 0:
                            y /= y_max
                        spectra_data[key] = {"x": x, "y": y,
                            "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                            "notes": "SMILES 기반 예측 NMR", "smiles": smiles}
                    elif st == "UV-Vis":
                        x = _np.linspace(180, 800, 1500)
                        y = _np.zeros_like(x)
                        sigma = 20.0
                        for f, intensity in zip(fq, it):
                            y += intensity * _np.exp(-((x - f)**2) / (2 * sigma**2))
                        y_max = y.max()
                        if y_max > 0:
                            y /= y_max
                        spectra_data["UV-Vis"] = {"x": x, "y": y,
                            "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 5))],
                            "notes": "SMILES 기반 예측 UV-Vis", "smiles": smiles,
                            "concentration": 1e-4, "path_length": 1.0}
                    elif st == "MS":
                        # Mass spectrum: m/z as x, relative intensity as y
                        x = _np.array(fq)
                        y = _np.array(it)
                        if y.max() > 0:
                            y = y / y.max() * 100
                        spectra_data["Mass"] = {"x": x, "y": y,
                            "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                            "notes": "SMILES 기반 예측 Mass Spectrum (EI-MS)", "smiles": smiles}
                    else:
                        # Raman fallback
                        x = _np.linspace(400, 4000, 1000)
                        y = _np.zeros_like(x)
                        gamma = 20.0
                        for f, intensity in zip(fq, it):
                            y += intensity * (gamma**2 / ((x - f)**2 + gamma**2))
                        y_max = y.max()
                        if y_max > 0:
                            y /= y_max
                        spectra_data[key] = {"x": x, "y": y,
                            "peaks": [(fq[i], it[i]) for i in range(min(len(fq), 10))],
                            "notes": "SMILES 기반 예측", "smiles": smiles}
                except Exception as _spec_err:
                    logger.warning("Spectrum %s generation failed: %s", st, _spec_err)
        else:
            logger.warning("PDF export: no SMILES (%r) or RDKIT unavailable (%s)",
                           smiles[:20] if smiles else '', RDKIT_AVAILABLE)

        # [STEP 2] SpectrumPDFExporter로 고품질 PDF 생성 시도
        pdf_generated = False
        if spectra_data:
            try:
                import sys as _sys
                _exporter_path = str(_SCRIPT_DIR.parent.parent / "agents" / "09_data_export")
                if _exporter_path not in _sys.path:
                    _sys.path.insert(0, _exporter_path)
                from spectrum_pdf_exporter import SpectrumPDFExporter

                # RDKit에서 분자식 가져오기
                _formula = "N/A"
                try:
                    _mol = Chem.MolFromSmiles(smiles)
                    if _mol:
                        _formula = rdMolDescriptors.CalcMolFormula(Chem.AddHs(_mol))
                except Exception:
                    pass

                exporter = SpectrumPDFExporter(output_dir=str(Path(filepath).parent))
                mol_name = smiles[:20] if smiles else "Unknown"
                pdf_path = exporter.create_report(
                    molecule_name=mol_name,
                    spectra_data=spectra_data,
                    filename=Path(filepath).name,
                    metadata={"smiles": smiles, "formula": _formula,
                              "iupac_name": "", "common_name": mol_name}
                )
                if pdf_path:
                    self.info_label.setText(
                        f"✅ PDF 저장 완료 ({len(spectra_data)}종 스펙트럼): {Path(pdf_path).name}")
                    pdf_generated = True
                else:
                    logger.warning("SpectrumPDFExporter.create_report returned None")
            except ImportError as _ie:
                logger.warning("SpectrumPDFExporter import failed: %s", _ie)
            except Exception as _e:
                logger.warning("SpectrumPDFExporter failed: %s", _e)

        # [STEP 3] 고품질 PDF 실패 시 — matplotlib PdfPages 멀티페이지 fallback
        if not pdf_generated and spectra_data:
            try:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as _plt
                from matplotlib.backends.backend_pdf import PdfPages as _PdfPages

                with _PdfPages(filepath) as _pdf:
                    for _key, _sdata in spectra_data.items():
                        _fig, _ax = _plt.subplots(figsize=(11, 7))
                        _x = _sdata.get("x", [])
                        _y = _sdata.get("y", [])
                        if hasattr(_x, '__len__') and len(_x) > 0:
                            if _key == "Mass":
                                _ax.stem(_x, _y, linefmt='b-', markerfmt='bx', basefmt='k-')
                            else:
                                _ax.plot(_x, _y, linewidth=1.2)
                            _ax.set_title(f"{_key} Spectrum — {smiles[:30]}", fontsize=14)
                            _ax.grid(True, linestyle='--', alpha=0.4)
                            if _key == "IR":
                                _ax.invert_xaxis()
                                _ax.set_xlabel("Wavenumber (cm\u207b\u00b9)")
                                _ax.set_ylabel("Transmittance (%)")
                            elif "NMR" in _key:
                                _ax.invert_xaxis()
                                _ax.set_xlabel("Chemical Shift (ppm)")
                                _ax.set_ylabel("Intensity")
                            elif _key == "UV-Vis":
                                _ax.set_xlabel("Wavelength (nm)")
                                _ax.set_ylabel("Absorbance (a.u.)")
                            elif _key == "Mass":
                                _ax.set_xlabel("m/z")
                                _ax.set_ylabel("Relative Intensity (%)")
                            else:
                                _ax.set_xlabel("Wavenumber (cm\u207b\u00b9)")
                                _ax.set_ylabel("Intensity (a.u.)")
                        _pdf.savefig(_fig, bbox_inches='tight')
                        _plt.close(_fig)
                self.info_label.setText(
                    f"✅ PDF 저장 ({len(spectra_data)}종, 기본모드): {Path(filepath).name}")
                pdf_generated = True
            except Exception as _fb_err:
                logger.warning("PdfPages fallback failed: %s", _fb_err)

        # [STEP 4] 모든 방법 실패 시 — 현재 figure 단일 저장
        if not pdf_generated:
            try:
                if self.ax is not None:
                    self.figure.savefig(filepath, dpi=200, bbox_inches='tight',
                                       facecolor='#1e1e1e', edgecolor='none')
                    self.info_label.setText(
                        f"⚠️ 단일 스펙트럼만 저장됨 (SMILES 없음): {Path(filepath).name}")
                else:
                    self.info_label.setText("⚠️ 스펙트럼 데이터 없음. 분자를 먼저 로드하세요.")
            except Exception as _e:
                self.info_label.setText(f"❌ PDF 저장 실패: {str(_e)[:60]}")

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
    """🎵 진동모드 탭 — 모드 선택 + 3D 애니메이션 제어 + 분광학 해설"""

    mode_selected = pyqtSignal(int)      # mode index
    animation_toggled = pyqtSignal(bool)  # play/stop
    internal_vib_calculated = pyqtSignal(object)  # VibrationResult
    zoom_to_atoms_requested = pyqtSignal(list)  # [atom_indices] — 3D 뷰어 줌 요청

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smiles = ""  # 현재 분자 SMILES (내부 엔진용)
        self._vib_result = None
        self._init_ui()

    # Signal: ORCA 파일 로드 요청 (부모에서 연결)
    orca_load_requested = pyqtSignal()

    # ── 특성 주파수 범위 (교육 참조용) ──
    CHARACTERISTIC_FREQUENCIES = {
        "O-H stretch":       (3200, 3600, "O-H 신축 진동 (stretching)"),
        "N-H stretch":       (3300, 3500, "N-H 신축 진동 (stretching)"),
        "C-H stretch (sp3)": (2850, 3000, "C-H 신축 진동 (sp3, stretching)"),
        "C-H stretch (sp2)": (3000, 3100, "C-H 신축 진동 (sp2, stretching)"),
        "C-H stretch (sp)":  (3300, 3320, "C-H 신축 진동 (sp, stretching)"),
        "C=O stretch":       (1650, 1750, "C=O 신축 진동 (stretching)"),
        "C=C stretch":       (1600, 1680, "C=C 신축 진동 (stretching)"),
        "C-O stretch":       (1000, 1300, "C-O 신축 진동 (stretching)"),
        "C-N stretch":       (1000, 1250, "C-N 신축 진동 (stretching)"),
        "Ring breathing":    (990, 1100,  "고리 호흡 진동 (ring breathing)"),
        "C-H bending":       (1350, 1470, "C-H 굽힘 진동 (bending)"),
        "O-H bending":       (1200, 1400, "O-H 굽힘 진동 (bending)"),
        "N-H bending":       (1550, 1650, "N-H 굽힘 진동 (bending)"),
        "C-F stretch":       (1000, 1400, "C-F 신축 진동 (stretching)"),
        "C-Cl stretch":      (600, 800,   "C-Cl 신축 진동 (stretching)"),
        "C-Br stretch":      (500, 680,   "C-Br 신축 진동 (stretching)"),
        "C=N stretch":       (1600, 1690, "C=N 신축 진동 (stretching)"),
        "C#N stretch":       (2200, 2260, "C#N 신축 진동 (nitrile stretching)"),
        "C#C stretch":       (2100, 2260, "C#C 신축 진동 (alkyne stretching)"),
        "S=O stretch":       (1030, 1370, "S=O 신축 진동 (stretching)"),
    }

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # [VIB-UX] ORCA 데이터 없을 때 안내 위젯
        self.no_data_widget = QWidget()
        nd_layout = QVBoxLayout()
        nd_layout.setContentsMargins(12, 20, 12, 20)
        nd_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nd_icon = QLabel("🎵")
        nd_icon.setStyleSheet("font-size: 36pt;")
        nd_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nd_layout.addWidget(nd_icon)

        nd_title = QLabel("진동 모드 데이터 없음")
        nd_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #ddd;")
        nd_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nd_layout.addWidget(nd_title)

        nd_desc = QLabel(
            "진동 모드 애니메이션을 보려면:\n"
            "1. 내부 엔진으로 간이 계산 (경험적 힘 상수 기반)\n"
            "2. ORCA 양자화학 계산 결과(.out) 로드"
        )
        nd_desc.setStyleSheet("color: #999; font-size: 9pt;")
        nd_desc.setWordWrap(True)
        nd_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nd_layout.addWidget(nd_desc)

        nd_layout.addSpacing(10)

        # 내부 엔진 계산 버튼 (NEW)
        self.btn_internal_calc = QPushButton("⚡ 내부 엔진으로 계산")
        self.btn_internal_calc.setStyleSheet("""
            QPushButton {
                background: #e65100; color: white; border: none;
                padding: 8px 20px; border-radius: 4px; font-size: 10pt;
            }
            QPushButton:hover { background: #ff6d00; }
        """)
        self.btn_internal_calc.clicked.connect(self._run_internal_engine)
        nd_layout.addWidget(self.btn_internal_calc, alignment=Qt.AlignmentFlag.AlignCenter)

        nd_layout.addSpacing(6)

        btn_load_orca = QPushButton("📂 ORCA 파일 로드")
        btn_load_orca.setStyleSheet("""
            QPushButton {
                background: #2d5aa0; color: white; border: none;
                padding: 8px 20px; border-radius: 4px; font-size: 10pt;
            }
            QPushButton:hover { background: #3a6ec0; }
        """)
        btn_load_orca.clicked.connect(self.orca_load_requested.emit)
        nd_layout.addWidget(btn_load_orca, alignment=Qt.AlignmentFlag.AlignCenter)

        self.no_data_widget.setLayout(nd_layout)
        layout.addWidget(self.no_data_widget)

        # [VIB-UX] 모드 데이터 있을 때 표시되는 위젯
        self.data_widget = QWidget()
        data_layout = QVBoxLayout()
        data_layout.setContentsMargins(0, 0, 0, 0)

        # Mode list (upper half)
        data_layout.addWidget(QLabel("진동 모드 선택:"))
        self.mode_list = QListWidget()
        self.mode_list.currentRowChanged.connect(self._on_mode_changed)
        data_layout.addWidget(self.mode_list, stretch=3)

        # Animation controls
        ctrl = QHBoxLayout()
        self.btn_play = QPushButton("▶ 재생")
        self.btn_play.setCheckable(True)
        self.btn_play.clicked.connect(self._toggle_animation)
        ctrl.addWidget(self.btn_play)

        ctrl.addWidget(QLabel("진폭:"))
        self.amp_slider = QSlider(Qt.Orientation.Horizontal)
        self.amp_slider.setMinimum(10)
        self.amp_slider.setMaximum(500)
        self.amp_slider.setValue(200)  # [FIX-VIB-001] 기본 진폭 2x (더 선명한 애니메이션)
        ctrl.addWidget(self.amp_slider)
        data_layout.addLayout(ctrl)

        # ── [VIB-SPEC] 분광학 상세 정보 패널 ──
        self.detail_group = QGroupBox("분광학 상세 정보")
        self.detail_group.setStyleSheet(
            "QGroupBox { border: 1px solid #555; border-radius: 4px; "
            "margin-top: 6px; padding-top: 14px; color: #ccc; font-size: 9pt; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }")
        detail_inner = QVBoxLayout()
        detail_inner.setContentsMargins(6, 4, 6, 4)
        detail_inner.setSpacing(3)

        # Mode type + frequency
        self.lbl_mode_type = QLabel("")
        self.lbl_mode_type.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ffa726;")
        self.lbl_mode_type.setWordWrap(True)
        detail_inner.addWidget(self.lbl_mode_type)

        self.lbl_frequency = QLabel("")
        self.lbl_frequency.setStyleSheet("font-size: 9pt; color: #81d4fa;")
        detail_inner.addWidget(self.lbl_frequency)

        # IR/Raman activity
        self.lbl_ir_activity = QLabel("")
        self.lbl_ir_activity.setStyleSheet("font-size: 9pt; color: #ddd;")
        self.lbl_ir_activity.setWordWrap(True)
        detail_inner.addWidget(self.lbl_ir_activity)

        self.lbl_raman_activity = QLabel("")
        self.lbl_raman_activity.setStyleSheet("font-size: 9pt; color: #ddd;")
        self.lbl_raman_activity.setWordWrap(True)
        detail_inner.addWidget(self.lbl_raman_activity)

        # Explanation
        self.lbl_explanation = QLabel("")
        self.lbl_explanation.setStyleSheet(
            "font-size: 8pt; color: #aaa; padding: 4px; "
            "background: #2a2a2a; border-radius: 3px;")
        self.lbl_explanation.setWordWrap(True)
        detail_inner.addWidget(self.lbl_explanation)

        # Zoom-to button removed (P1: unreliable camera positioning)

        self.detail_group.setLayout(detail_inner)
        data_layout.addWidget(self.detail_group, stretch=2)

        # Info
        self.info_label = QLabel("ORCA 데이터에서 진동 모드를 로드하세요")
        self.info_label.setStyleSheet("color: #888; font-size: 9pt;")
        data_layout.addWidget(self.info_label)

        self.data_widget.setLayout(data_layout)
        self.data_widget.setVisible(False)  # 초기에는 숨김
        layout.addWidget(self.data_widget)

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
        # [VIB-UX] 데이터 로드 시 no_data 숨기고 data 표시
        self.no_data_widget.setVisible(False)
        self.data_widget.setVisible(True)

    def _on_mode_changed(self, row):
        if row >= 0:
            self.mode_selected.emit(row)
            self._update_detail_panel(row)

    def _update_detail_panel(self, row):
        """선택된 진동 모드의 분광학 상세 정보 업데이트"""
        if not self._vib_result or row < 0 or row >= len(self._vib_result.modes):
            # No internal engine data — show basic info from ORCA mode list
            self.lbl_mode_type.setText(f"Mode {row + 1}")
            self.lbl_frequency.setText("")
            self.lbl_ir_activity.setText("")
            self.lbl_raman_activity.setText("")
            self.lbl_explanation.setText("내부 엔진으로 계산하면 분광학 상세 정보를 표시합니다.")
            return

        mode = self._vib_result.modes[row]

        # Mode type description
        type_icons = {"stretch": "↔", "bend": "∠", "torsion": "⟳"}
        type_kr = {"stretch": "신축 진동 (stretching)", "bend": "굽힘 진동 (bending)",
                   "torsion": "비틀림 진동 (torsion)"}
        icon = type_icons.get(mode.mode_type, "")
        mtype_kr = type_kr.get(mode.mode_type, "진동")
        self.lbl_mode_type.setText(f"{icon} {mode.description}")

        # Frequency + wavelength
        freq_text = f"{mode.frequency_cm:.1f} cm\u207b\u00b9"
        if mode.wavelength_um > 0:
            freq_text += f"  (\u03bb = {mode.wavelength_um:.2f} \u03bcm)"
        if mode.freq_range_label:
            freq_text += f"  [{mode.freq_range_label}]"
        self.lbl_frequency.setText(freq_text)

        # IR activity
        ir_check = "\u2713" if mode.ir_active else "\u2717"
        ir_color = "#4caf50" if mode.ir_active else "#f44336"
        ir_text = (f"<span style='color:{ir_color};font-weight:bold;'>IR {ir_check}</span> "
                   f"<span style='color:#bbb;'>({mode.ir_explanation})</span>")
        self.lbl_ir_activity.setText(ir_text)

        # Raman activity
        raman_check = "\u2713" if mode.raman_active else "\u2717"
        raman_color = "#4caf50" if mode.raman_active else "#f44336"
        raman_text = (f"<span style='color:{raman_color};font-weight:bold;'>Raman {raman_check}</span> "
                      f"<span style='color:#bbb;'>({mode.raman_explanation})</span>")
        self.lbl_raman_activity.setText(raman_text)

        # Full spectroscopy note
        if mode.spectroscopy_note:
            self.lbl_explanation.setText(mode.spectroscopy_note)
        else:
            self.lbl_explanation.setText(f"{mode.description} - {mtype_kr}")

    def _zoom_to_vibrating_atoms(self):
        """현재 선택된 모드의 진동 원자 영역으로 3D 뷰 줌"""
        row = self.mode_list.currentRow()
        if row < 0 or not self._vib_result or row >= len(self._vib_result.modes):
            return
        mode = self._vib_result.modes[row]
        atom_indices = list(mode.bond_indices)
        if atom_indices:
            self.zoom_to_atoms_requested.emit(atom_indices)

    def _toggle_animation(self, checked):
        self.btn_play.setText("⏸ 정지" if checked else "▶ 재생")
        self.animation_toggled.emit(checked)

    def set_smiles(self, smiles: str):
        """내부 엔진 계산용 SMILES 설정"""
        self._smiles = smiles

    def _run_internal_engine(self):
        """내부 진동 엔진으로 계산 실행"""
        if not self._smiles:
            self.info_label.setText("분자 데이터가 없습니다")
            return

        self.btn_internal_calc.setText("계산 중...")
        self.btn_internal_calc.setEnabled(False)
        QApplication.processEvents()

        try:
            from vibration_engine import InternalVibrationEngine
            engine = InternalVibrationEngine()
            result = engine.calculate(smiles=self._smiles)

            if result.success and result.modes:
                self._vib_result = result
                freqs = [m.frequency_cm for m in result.modes]
                intensities = [m.ir_intensity for m in result.modes]

                # 모드 목록 로드 (설명 + 모드 유형 아이콘 + IR/Raman 활성 포함)
                self.mode_list.clear()
                type_icons = {"stretch": "↔", "bend": "∠", "torsion": "⟳"}
                n_stretch = sum(1 for m in result.modes if getattr(m, 'mode_type', 'stretch') == 'stretch')
                n_bend = sum(1 for m in result.modes if getattr(m, 'mode_type', '') == 'bend')
                n_torsion = sum(1 for m in result.modes if getattr(m, 'mode_type', '') == 'torsion')
                for i, mode in enumerate(result.modes):
                    mtype = getattr(mode, 'mode_type', 'stretch')
                    icon = type_icons.get(mtype, "·")
                    inten_bar = "█" * int(mode.ir_intensity * 5)
                    # IR/Raman activity tags
                    spec_tags = []
                    if getattr(mode, 'ir_active', True):
                        spec_tags.append("IR")
                    if getattr(mode, 'raman_active', True):
                        spec_tags.append("Ra")
                    spec_str = "/".join(spec_tags) if spec_tags else ""
                    item = QListWidgetItem(
                        f"{icon} Mode {i+1}: {mode.frequency_cm:.0f} cm⁻¹  {inten_bar}  [{spec_str}]  {mode.description}")
                    self.mode_list.addItem(item)

                self.info_label.setText(
                    f"내부 엔진: {len(result.modes)}개 모드 "
                    f"(↔{n_stretch} ∠{n_bend} ⟳{n_torsion})")
                self.no_data_widget.setVisible(False)
                self.data_widget.setVisible(True)

                # 부모에게 결과 전달
                self.internal_vib_calculated.emit(result)

                # [FIX-VIB-001] 첫 번째 모드 자동 선택 → 즉시 애니메이션 시작
                if self.mode_list.count() > 0:
                    self.mode_list.setCurrentRow(0)
            else:
                err = result.error_message or "계산 실패"
                self.info_label.setText(f"오류: {err}")
        except Exception as e:
            self.info_label.setText(f"엔진 오류: {e}")
        finally:
            self.btn_internal_calc.setText("⚡ 내부 엔진으로 계산")
            self.btn_internal_calc.setEnabled(True)

    def get_displacement_vectors(self, mode_idx: int):
        """선택된 모드의 변위벡터 반환"""
        if self._vib_result and 0 <= mode_idx < len(self._vib_result.modes):
            return self._vib_result.modes[mode_idx].displacement_vectors
        return None


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
            elif section_key == "application":
                # [AI-FIX] 응용 및 주의 — Lipinski Rule of Five + 구조 경고
                mw = Descriptors.MolWt(mol)
                logp = Descriptors.MolLogP(mol)
                n_donors = Descriptors.NumHDonors(mol)
                n_accept = Descriptors.NumHAcceptors(mol)
                n_rot = Descriptors.NumRotatableBonds(mol)
                tpsa = Descriptors.TPSA(mol)
                lines = []
                # Lipinski 약물유사성
                lipinski_pass = (mw <= 500 and logp <= 5 and n_donors <= 5 and n_accept <= 10)
                lipinski_score = sum([mw <= 500, logp <= 5, n_donors <= 5, n_accept <= 10])
                lines.append(f"• Lipinski Rule of Five: {lipinski_score}/4 통과 {'✅' if lipinski_pass else '⚠️'}")
                if lipinski_pass:
                    lines.append("  → 경구 투여 약물 후보로 적합한 물리화학적 특성")
                else:
                    violations = []
                    if mw > 500: violations.append(f"MW {mw:.0f}>500")
                    if logp > 5: violations.append(f"LogP {logp:.1f}>5")
                    if n_donors > 5: violations.append(f"HBD {n_donors}>5")
                    if n_accept > 10: violations.append(f"HBA {n_accept}>10")
                    lines.append(f"  → 위반: {', '.join(violations)}")
                # TPSA (혈뇌장벽)
                lines.append(f"• TPSA: {tpsa:.1f} Å² — {'BBB 투과 가능 (CNS 약물 후보)' if tpsa < 90 else '경구 흡수 가능' if tpsa < 140 else '낮은 경구 흡수 예상'}")
                # 회전 가능 결합
                if n_rot > 10:
                    lines.append(f"• ⚠️ 회전 가능 결합 {n_rot}개 — 유연성 과다, 결합 엔트로피 불리")
                # 구조 경고 (PAINS-like)
                alerts = []
                if mol.HasSubstructMatch(Chem.MolFromSmarts("[N+](=O)[O-]")):
                    alerts.append("니트로기 (독성/돌연변이 유발 위험)")
                if mol.HasSubstructMatch(Chem.MolFromSmarts("[F,Cl,Br,I]")):
                    alerts.append("할로겐 함유 (대사 안정성 주의)")
                if mol.HasSubstructMatch(Chem.MolFromSmarts("c1ccc2c(c1)ccc1ccccc12")):
                    alerts.append("다환 방향족 (발암 가능성)")
                if mol.HasSubstructMatch(Chem.MolFromSmarts("[SX2]")):
                    alerts.append("티오에테르 (산화적 대사 주의)")
                if alerts:
                    lines.append("• ⚠️ 구조 경고:")
                    for a in alerts:
                        lines.append(f"  - {a}")
                else:
                    lines.append("• ✅ 주요 구조 경고 없음")
                # 용도 추정
                n_ar = rdMolDescriptors.CalcNumAromaticRings(mol)
                if n_ar >= 2 and mw > 250:
                    lines.append("• 💊 방향족 다환 구조 → 키나아제 억제제/항암제 스캐폴드 가능성")
                elif any(a.GetAtomicNum() == 7 for a in mol.GetAtoms()) and n_donors >= 2:
                    lines.append("• 💊 질소 함유 + H-bond 공여 → CNS/신경계 약물 스캐폴드 가능성")
                elif logp < 0:
                    lines.append("• 💧 높은 친수성 → 수용성 약물/프로드럭 후보")
                return "\n".join(lines)
            elif section_key == "facts":
                # [AI-FIX] 화학적 사실 — SMILES 패턴 매칭으로 알려진 화합물군 식별
                mw = Descriptors.MolWt(mol)
                lines = []
                # 알려진 구조 패턴 매칭
                known_patterns = [
                    ("c1ccccc1C(=O)O", "벤조산 유도체", "벤조산은 식품 방부제(E210)로 사용되며, 아스피린의 모체 구조입니다."),
                    ("c1ccccc1O", "페놀 유도체", "페놀 구조는 항산화/항균 활성의 핵심이며, 타이레놀(아세트아미노펜)에도 포함됩니다."),
                    ("CC(=O)O", "아세트산 유도체", "아세트산은 식초의 주성분(3-5%)이며, 생체 내 아세틸-CoA의 전구체입니다."),
                    ("CCO", "알코올 유도체", "에탄올(C₂H₅OH)은 가장 널리 소비되는 알코올이며, 효모 발효의 주산물입니다."),
                    ("c1ccncc1", "피리딘 유도체", "피리딘 고리는 비타민 B3(나이아신), 항결핵제 이소니아지드의 핵심 구조입니다."),
                    ("C1CCCCC1", "사이클로헥세인 유도체", "의자/보트 배좌가 대표적이며, 당(Sugar)의 기본 골격입니다."),
                    ("c1ccc2[nH]ccc2c1", "인돌 유도체", "인돌은 세로토닌, 트립토판, 멜라토닌의 핵심 골격으로, 신경전달에 중요합니다."),
                    ("c1ccc(-c2ccccc2)cc1", "비페닐 구조", "비페닐은 LCD 액정, 열매체, 의약품 스캐폴드로 널리 활용됩니다."),
                ]
                matched = False
                for smarts, name, fact in known_patterns:
                    pat = Chem.MolFromSmarts(smarts)
                    if pat and mol.HasSubstructMatch(pat):
                        lines.append(f"• 🔍 {name} 계열 화합물")
                        lines.append(f"  {fact}")
                        matched = True
                        break
                # 원소 조성 기반 사실
                atom_nums = set(a.GetAtomicNum() for a in mol.GetAtoms())
                if 16 in atom_nums:  # S
                    lines.append("• 🧪 황(S) 함유 — 시스테인/메티오닌의 핵심 원소, 이황화결합 형성")
                if 15 in atom_nums:  # P
                    lines.append("• 🧪 인(P) 함유 — DNA/ATP의 필수 원소, 유기인 화합물은 농약/신경작용제")
                if 9 in atom_nums:  # F
                    lines.append("• 🧪 불소(F) 함유 — C-F 결합은 가장 강한 단일결합 중 하나 (485 kJ/mol)")
                # 분자량 기반 정보
                n_heavy = mol.GetNumHeavyAtoms()
                n_rings = rdMolDescriptors.CalcNumRings(mol)
                lines.append(f"• 📊 중원자 {n_heavy}개, 고리 {n_rings}개, 분자량 {mw:.1f} g/mol")
                if n_rings >= 4:
                    lines.append("• 🔬 다환 구조 — 스테로이드/테르페노이드 골격과 유사")
                elif n_heavy <= 5:
                    lines.append("• 🔬 소분자 — 용매/시약/대사 중간체로 흔히 사용")
                if not matched and not lines:
                    lines.append(f"• 분자식 기반 분석 (SMILES: {smiles})")
                    lines.append("  Gemini API를 설정하면 더 상세한 화학적 사실을 확인할 수 있습니다.")
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
        # ── 신경계 (7종) ──
        ("GABA-A (α1β2γ2)",    "6X3S", "GABA 수용체 — 벤조디아제핀 결합 부위"),
        ("Dopamine D2",         "6CM4", "도파민 D2 수용체 — 항정신병/파킨슨"),
        ("Serotonin 5-HT2A",   "6WHA", "세로토닌 수용체 — 항우울제/항정신병"),
        ("Mu-Opioid (μOR)",    "5C1M", "뮤-오피오이드 수용체 — 진통제 표적"),
        ("Acetylcholinesterase", "4EY7", "아세틸콜린에스터라아제 — 알츠하이머"),
        ("NMDA (NR2B)",         "5UN1", "NMDA 수용체 — 신경퇴행성 질환"),
        ("CB1 (카나비노이드)",   "5TGZ", "카나비노이드 수용체1 — 통증/식욕"),
        # ── 항암 (8종) ──
        ("EGFR (항암)",         "1IVO", "표피성장인자 수용체 — 항암제 표적"),
        ("CDK2 (세포주기)",     "1FIN", "사이클린의존 키나아제2 — 항암 표적"),
        ("BRAF V600E",          "4RZV", "BRAF 돌연변이 키나아제 — 흑색종 항암"),
        ("Tubulin (미세소관)",   "1SA0", "튜불린 — 항암제(탁솔/빈카) 표적"),
        ("ALK (폐암)",          "2XP2", "역형성림프종 키나아제 — 크리조티닙 표적"),
        ("PI3Kα (유방암)",      "4JPS", "PI3 키나아제 알파 — 알펠리십 표적"),
        ("mTOR (면역억제)",     "4DRH", "라파마이신 표적 — 에버롤리무스"),
        ("VEGFR2 (혈관신생)",   "3WZE", "혈관내피성장인자 수용체 — 항암 표적"),
        # ── 대사/내분비 (6종) ──
        ("COX-2 (NSAIDs)",      "5IKT", "프로스타글란딘 합성효소 — 소염진통제"),
        ("HMG-CoA Reductase",   "1HWK", "콜레스테롤 합성효소 — 스타틴 표적"),
        ("DPP-4 (당뇨)",        "2ONC", "디펩티딜펩티다아제4 — 글립틴 표적"),
        ("PPARγ (대사증후군)",   "2PRG", "핵수용체 — 티아졸리딘디온(TZD) 표적"),
        ("GLP-1R (비만/당뇨)",  "5VAI", "글루카곤유사펩타이드1 수용체 — 세마글루타이드"),
        ("Glucokinase (혈당)",  "3IDH", "글루코키나아제 — 당뇨 활성제"),
        # ── 심혈관/호흡기 (3종) ──
        ("ACE2 (COVID-19)",     "6M0J", "SARS-CoV-2 스파이크 단백질 수용체"),
        ("Thrombin (혈액응고)",  "3U69", "혈액응고 효소 — 항응고제 표적"),
        ("Beta-2 (천식)",       "3NY8", "β2 아드레날린 수용체 — 기관지 확장"),
        # ── 감염/면역 (7종) ──
        ("HIV Protease",        "3OXC", "HIV 단백질분해효소 — 항바이러스"),
        ("DNA Gyrase",          "5BTC", "DNA 자이레이스 — 항생제(퀴놀론) 표적"),
        ("Neuraminidase (독감)", "3TI6", "뉴라미니다아제 — 타미플루 표적"),
        ("SARS-CoV-2 Mpro",    "6LU7", "코로나 주요 단백질분해효소 — 팍스로비드"),
        ("Reverse Transcriptase","3HVT", "HIV 역전사효소 — NRTI/NNRTI 표적"),
        ("JAK2 (면역)",         "3FUP", "야누스 키나아제2 — 룩소리티닙 표적"),
        ("TNF-α (자가면역)",    "2AZ5", "종양괴사인자 알파 — 아달리무맙 표적"),
        # ── 비뇨/성기능 (2종) ──
        ("PDE5 (발기부전)",     "1UDT", "포스포디에스터라아제5 — 실데나필 표적"),
        ("SGLT2 (당뇨/심부전)", "7VSI", "나트륨-포도당 공동수송체2 — 다파글리플로진"),
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
        self._vina_result = None              # [VINA-WIRE] Vina 도킹 결과 보관
        self._vina_thread = None              # [VINA-WIRE] Vina 스레드 참조
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

        # [PROTEIN-3D] 3D 도킹 시각화 버튼
        self.btn_dock_3d = QPushButton("🎬 3D 도킹 시각화")
        self.btn_dock_3d.setEnabled(False)
        self.btn_dock_3d.setStyleSheet(
            "QPushButton { background:#1565C0; color:#90CAF9; border:1px solid #1976D2; "
            "border-radius:3px; padding:5px 14px; font-size:10pt; font-weight:bold; }"
            "QPushButton:hover { background:#1976D2; }"
            "QPushButton:disabled { background:#333; color:#666; }")
        self.btn_dock_3d.setToolTip(
            "도킹 결과를 3D 뷰어에서 시각화합니다.\n"
            "단백질 백본 + 리간드 접근 애니메이션을 표시합니다.")
        self.btn_dock_3d.clicked.connect(self._show_dock_3d)
        dock_btn_row.addWidget(self.btn_dock_3d)
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
        """도킹 실행: Vina 우선, 미설치 시 경험적 근사 폴백"""
        if not self._smiles:
            self.dock_result.setPlainText("⚠️ 리간드(분자) SMILES 없음 — 분자를 먼저 로드하세요")
            return
        if not self._receptor_atoms:
            self.dock_result.setPlainText("⚠️ 수용체 미로드 — [📥 수용체 로드] 먼저 실행하세요")
            return

        self.btn_dock.setEnabled(False)
        self.dock_result.setPlainText("🔄 도킹 시뮬레이션 중...")
        QApplication.processEvents()

        # [VINA-WIRE] 실제 Vina 사용 가능하면 시도
        if VINA_BACKEND_AVAILABLE and self._current_pdb_id:
            try:
                self._run_vina_real()
                return  # Vina 비동기 실행 → 완료 시 콜백에서 결과 표시
            except Exception as e:
                logger.warning(f"Vina failed, falling back to empirical: {e}")
                self.dock_result.setPlainText("🔄 Vina 실패 → 경험적 근사치 계산 중...")
                QApplication.processEvents()

        # 경험적 근사 폴백
        try:
            energy = self._empirical_docking_score()
            self._docking_energy = energy
            self._show_docking_result(energy, method="경험적 근사")
        except Exception as e:
            self.dock_result.setPlainText(f"⚠️ 도킹 오류: {e}")
        finally:
            self.btn_dock.setEnabled(True)

    def _run_vina_real(self):
        """[VINA-WIRE] 실제 AutoDock Vina 실행 (비동기)"""
        import tempfile
        work_dir = Path(tempfile.mkdtemp(prefix="chemgrid_vina_"))

        # 1) 리간드 준비
        ligand = LigandPreparer.smiles_to_3d(self._smiles)
        if ligand is None:
            raise RuntimeError("리간드 3D 좌표 생성 실패")
        lig_pdbqt = LigandPreparer.prepare_pdbqt(ligand, work_dir)
        if lig_pdbqt is None:
            raise RuntimeError("리간드 PDBQT 변환 실패")

        # 2) 수용체 PDB 다운로드 및 준비
        receptor = ReceptorData(pdb_id=self._current_pdb_id)
        # PDB 파일이 이미 있으면 재사용
        pdb_cache = work_dir / f"{self._current_pdb_id}.pdb"
        if not pdb_cache.exists():
            import requests as _req
            url = f"https://files.rcsb.org/download/{self._current_pdb_id}.pdb"
            resp = _req.get(url, timeout=30)
            resp.raise_for_status()
            pdb_cache.write_text(resp.text, encoding='utf-8')

        receptor.filepath = pdb_cache
        parser = VinaPDBParser()
        receptor = parser.parse(str(pdb_cache))

        rec_pdbqt = ReceptorPreparer.prepare_pdbqt(receptor, work_dir)
        if rec_pdbqt is None:
            raise RuntimeError("수용체 PDBQT 변환 실패")

        # 3) 결합 부위 자동 탐지
        center, size = ReceptorPreparer.detect_binding_site(receptor)

        config = DockingConfig(
            center_x=center[0], center_y=center[1], center_z=center[2],
            size_x=size[0], size_y=size[1], size_z=size[2],
            exhaustiveness=8,
            num_modes=5,
        )

        # 4) Vina 비동기 실행
        self.dock_result.setPlainText(
            f"🔄 AutoDock Vina 도킹 중...\n"
            f"수용체: {self._current_pdb_id}\n"
            f"결합 부위: ({center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f})\n"
            f"박스 크기: {size[0]:.0f}×{size[1]:.0f}×{size[2]:.0f} Å"
        )
        QApplication.processEvents()

        self._vina_thread = VinaDockingThread(
            receptor_pdbqt=rec_pdbqt,
            ligand_pdbqt=lig_pdbqt,
            config=config,
            work_dir=work_dir,
            receptor=receptor,
            ligand=ligand,
            parent=self,
        )
        self._vina_thread.progress.connect(
            lambda msg: self.dock_result.setPlainText(f"🔄 {msg}"))
        self._vina_thread.result.connect(self._on_vina_result)
        self._vina_thread.error.connect(self._on_vina_error)
        self._vina_thread.start()

    def _on_vina_result(self, dock_result):
        """[VINA-WIRE] Vina 도킹 완료 콜백"""
        self.btn_dock.setEnabled(True)
        if dock_result.poses:
            best = dock_result.poses[0]
            self._docking_energy = best.affinity_kcal
            self._vina_result = dock_result  # 3D 시각화용 보관
            self._show_docking_result(best.affinity_kcal, method="AutoDock Vina")
            # 추가 포즈 정보
            if len(dock_result.poses) > 1:
                extra = "\n\n📊 상위 포즈 결합 에너지:\n"
                for i, pose in enumerate(dock_result.poses[:5]):
                    extra += f"  Pose {i+1}: {pose.affinity_kcal:.2f} kcal/mol\n"
                self.dock_result.append(extra)
        else:
            self.dock_result.setPlainText("⚠️ Vina 도킹 완료되었으나 포즈가 생성되지 않았습니다.")

    def _on_vina_error(self, error_msg):
        """[VINA-WIRE] Vina 오류 → 경험적 근사 폴백"""
        logger.warning(f"Vina error: {error_msg}")
        self.dock_result.setPlainText(f"⚠️ Vina 오류: {error_msg}\n\n🔄 경험적 근사치로 대체 계산 중...")
        QApplication.processEvents()
        try:
            energy = self._empirical_docking_score()
            self._docking_energy = energy
            self._show_docking_result(energy, method="경험적 근사 (Vina 실패)")
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
            "3NY8": {"hb_w": -0.7, "hydro_w": -0.7, "baseline": -4.8},   # Beta-2
            "3OXC": {"hb_w": -0.9, "hydro_w": -0.5, "baseline": -5.0},   # HIV Protease
            "4EY7": {"hb_w": -0.8, "hydro_w": -0.6, "baseline": -5.5},   # AChE
            "6CM4": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -5.0},   # Dopamine D2 (소수성 포켓)
            "6WHA": {"hb_w": -0.8, "hydro_w": -0.7, "baseline": -4.8},   # 5-HT2A
            "5C1M": {"hb_w": -0.9, "hydro_w": -0.6, "baseline": -5.2},   # Mu-Opioid (극성)
            "1HWK": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -6.0},   # HMG-CoA (스타틴)
            "1UDT": {"hb_w": -0.6, "hydro_w": -0.9, "baseline": -5.5},   # PDE5 (소수성)
            "1FIN": {"hb_w": -0.8, "hydro_w": -0.7, "baseline": -5.0},   # CDK2
            "4RZV": {"hb_w": -0.6, "hydro_w": -0.9, "baseline": -5.8},   # BRAF (소수성)
            "1SA0": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -5.3},   # Tubulin
            "5BTC": {"hb_w": -0.9, "hydro_w": -0.5, "baseline": -4.5},   # DNA Gyrase (극성)
            "3TI6": {"hb_w": -1.0, "hydro_w": -0.4, "baseline": -5.0},   # Neuraminidase (극성)
            "2ONC": {"hb_w": -0.8, "hydro_w": -0.6, "baseline": -4.8},   # DPP-4
            "2PRG": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -5.5},   # PPARγ
            # 추가 수용체 보정 인자
            "5UN1": {"hb_w": -0.9, "hydro_w": -0.5, "baseline": -4.5},   # NMDA (극성)
            "5TGZ": {"hb_w": -0.5, "hydro_w": -1.0, "baseline": -5.5},   # CB1 (소수성)
            "2XP2": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -5.5},   # ALK
            "4JPS": {"hb_w": -0.7, "hydro_w": -0.7, "baseline": -5.3},   # PI3Kα
            "4DRH": {"hb_w": -0.8, "hydro_w": -0.6, "baseline": -5.0},   # mTOR
            "3WZE": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -5.5},   # VEGFR2
            "5VAI": {"hb_w": -1.0, "hydro_w": -0.4, "baseline": -4.5},   # GLP-1R (극성)
            "3IDH": {"hb_w": -0.9, "hydro_w": -0.5, "baseline": -4.8},   # Glucokinase
            "6LU7": {"hb_w": -0.9, "hydro_w": -0.6, "baseline": -5.0},   # SARS Mpro
            "3HVT": {"hb_w": -0.7, "hydro_w": -0.7, "baseline": -5.2},   # RT
            "3FUP": {"hb_w": -0.7, "hydro_w": -0.8, "baseline": -5.5},   # JAK2
            "2AZ5": {"hb_w": -0.8, "hydro_w": -0.6, "baseline": -4.8},   # TNF-α
            "7VSI": {"hb_w": -0.9, "hydro_w": -0.5, "baseline": -4.5},   # SGLT2
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

    def _show_docking_result(self, energy: float, method: str = "경험적 근사"):
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
            f"계산 방법:  {method}",
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
            "6CM4": [("Haloperidol", -9.2), ("Risperidone", -10.8)],
            "6WHA": [("Ketanserin", -9.5)],
            "5C1M": [("Morphine", -9.0), ("Fentanyl", -11.5)],
            "1HWK": [("Atorvastatin", -11.0), ("Rosuvastatin", -10.5)],
            "1UDT": [("Sildenafil", -10.2), ("Tadalafil", -10.8)],
            "3TI6": [("Oseltamivir", -9.8), ("Zanamivir", -10.1)],
        }
        refs = preset_drug_map.get(self._current_pdb_id, [])
        if refs:
            lines.append("참조 약물 비교:")
            for drug, ref_e in refs:
                diff = energy - ref_e
                sign = "↑ 강함" if diff < 0 else "↓ 약함"
                lines.append(f"  vs {drug}: {diff:+.1f} kcal/mol ({sign})")

        lines.append("─────────────────────────────────")
        if "Vina" in method:
            lines.append("✅ AutoDock Vina 실제 도킹 결과")
        else:
            lines.append("📊 경험적 스코어링 함수 기반 결과 (AutoDock Vina 연동 시 정밀도 향상)")

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

        # [PROTEIN-3D] 3D 시각화 버튼 활성화
        self.btn_dock_3d.setEnabled(True)

    def _show_dock_3d(self):
        """[PROTEIN-3D] 도킹 결과를 3D 뷰어에 표시 — 단백질 백본 + 리간드 실제 도킹 포즈"""
        if not self._receptor_atoms:
            return
        try:
            # Molecule3DPopup의 viewer에 접근 (부모 탐색)
            popup = self.parent()
            while popup and not isinstance(popup, Molecule3DPopup):
                popup = popup.parent()
            if popup is None or not hasattr(popup, 'viewer'):
                self.dock_result.append("\n⚠️ 3D 뷰어를 찾을 수 없습니다.")
                return
            viewer = popup.viewer
            if not viewer or not hasattr(viewer, 'set_protein_data'):
                self.dock_result.append("\n⚠️ 3D 뷰어가 도킹 시각화를 지원하지 않습니다.")
                return

            # 결합 부위 중심: DockingConfig.center 우선, 없으면 Cα 무게중심 폴백
            binding_center = None
            binding_radius = 8.0
            if self._vina_result and self._vina_result.config:
                cfg = self._vina_result.config
                binding_center = cfg.center
                # 검색 박스 크기의 절반 → 노란 존 반경
                binding_radius = min(cfg.size_x, cfg.size_y, cfg.size_z) / 2.0

            if binding_center is None or binding_center == (0.0, 0.0, 0.0):
                xs = [a[1] for a in self._receptor_atoms]
                ys = [a[2] for a in self._receptor_atoms]
                zs = [a[3] for a in self._receptor_atoms]
                binding_center = (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))

            # 뷰어에 단백질 데이터 전달
            viewer.set_protein_data(self._receptor_atoms, binding_site=binding_center)
            viewer._binding_site_radius = binding_radius

            # [DOCK-POSE] 최적 도킹 포즈의 실제 좌표를 뷰어에 전달
            if self._vina_result and self._vina_result.poses:
                best_pose = self._vina_result.poses[0]
                if best_pose.atom_coords and best_pose.atom_elements:
                    viewer.set_docking_pose(
                        best_pose.atom_coords,
                        best_pose.atom_elements,
                        binding_center=binding_center,
                        binding_radius=binding_radius,
                    )

            # 리간드 접근 애니메이션 시작
            viewer.start_dock_approach(start_offset=(40.0, 0.0, 0.0))

            self.dock_result.append(
                "\n🎬 3D 도킹 시각화 시작 — 뷰어에서 단백질+리간드 확인")
        except Exception as e:
            logger.error(f"3D 도킹 시각화 오류: {e}")
            self.dock_result.append(f"\n⚠️ 3D 시각화 오류: {e}")

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


class _PubChemThread(QThread):
    """PubChem API 비동기 조회 (UI 블로킹 방지)"""
    result_ready = pyqtSignal(object)  # dict or None

    def __init__(self, client, smiles: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._smiles = smiles

    def run(self):
        try:
            data = self._client.lookup_by_smiles(self._smiles)
            self.result_ready.emit(data)
        except Exception:
            self.result_ready.emit(None)


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
        # 화면 크기에 맞게 반응형 크기 설정
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                popup_w = min(1100, avail.width() - 80)
                popup_h = min(760, avail.height() - 80)  # 860 → 760 기본 축소
                popup_x = max(40, (avail.width() - popup_w) // 2)
                popup_y = max(40, (avail.height() - popup_h) // 2)
            else:
                popup_x, popup_y, popup_w, popup_h = 120, 80, 1100, 760
        except Exception:
            popup_x, popup_y, popup_w, popup_h = 120, 80, 1100, 760
        self.setGeometry(popup_x, popup_y, popup_w, popup_h)
        self.setMinimumSize(700, 500)  # 자유 리사이즈 허용, 최소 크기만 제한
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

        # === Top control bar (스크롤 가능) ===
        ctrl_widget = QWidget()
        ctrl = QHBoxLayout(ctrl_widget)
        ctrl.setContentsMargins(0, 0, 0, 0)
        ctrl.setSpacing(6)
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

        # [RIBBON] 단백질 리본 모드 토글
        self.btn_ribbon = QPushButton("🎗 Ribbon")
        self.btn_ribbon.setCheckable(True)
        self.btn_ribbon.setToolTip(
            "단백질 2차 구조 리본 렌더링\n"
            "α-helix (빨강 튜브) / β-sheet (노랑 리본) / Coil (얇은 관)")
        self.btn_ribbon.clicked.connect(self._toggle_ribbon)
        ctrl.addWidget(self.btn_ribbon)

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

        # [FIX] 컨트롤 바를 QScrollArea로 감싸 창이 좁아도 버튼이 잘리지 않도록
        from PyQt6.QtWidgets import QScrollArea
        ctrl_scroll = QScrollArea()
        ctrl_scroll.setWidget(ctrl_widget)
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ctrl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        ctrl_scroll.setFixedHeight(42)
        ctrl_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        main_layout.addWidget(ctrl_scroll)

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

        # 알파폴드/합성 탭
        self.tab_alphafold = self._create_alphafold_synthesis_tab()
        self.tabs.addTab(self.tab_alphafold, "🧪 신약설계")

        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 1)  # 3D viewer stretches
        splitter.setStretchFactor(1, 1)  # tab panel stretches equally
        splitter.setSizes([380, 340])  # 3D 뷰어와 탭 패널 균등 배분 (스펙트럼 그래프 크기 확보)

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
        self.tab_vibration.orca_load_requested.connect(self._load_orca_file)
        self.tab_vibration.internal_vib_calculated.connect(self._on_internal_vib)
        self.tab_vibration.zoom_to_atoms_requested.connect(self._zoom_viewer_to_atoms)

        # 내부 엔진용 SMILES 전달
        if self.mol_data.smiles:
            self.tab_vibration.set_smiles(self.mol_data.smiles)

    def _load_data(self):
        """초기 데이터 로드 (RDKit, PubChem, ORCA)"""
        smiles = self.mol_data.smiles or ""
        self._current_smiles = smiles  # 신약설계 탭에서 사용

        # Properties tab — RDKit
        self.tab_props.update_rdkit(smiles)
        self.tab_props.update_measurements(self.mol_data)

        # Properties tab — PubChem (threaded — UI 블로킹 방지)
        if smiles and REQUESTS_AVAILABLE:
            self._pubchem_thread = _PubChemThread(self.pubchem, smiles)
            self._pubchem_thread.result_ready.connect(
                lambda data: self.tab_props.update_pubchem(data, smiles))
            self._pubchem_thread.start()
        else:
            self.tab_props.update_pubchem(None, smiles)

        # [FIX-PDF-SMILES] SMILES를 SpectrumPanel에 항상 전달 (PDF 일괄 출력에 필요)
        if smiles:
            self.tab_spectrum._smiles_cache = smiles

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

    def _toggle_ribbon(self):
        """[RIBBON] Backbone ↔ Ribbon 전환"""
        if self.viewer:
            self.viewer.toggle_ribbon_mode()
            self.btn_ribbon.setChecked(self.viewer._ribbon_mode)

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
        """진동 모드 선택 시 뷰어에 벡터 즉시 표시 (play 버튼 불필요) + 하이라이트"""
        vectors = None
        # ORCA 파서 데이터
        if (self.orca_parser and mode_idx < len(self.orca_parser.normal_modes)):
            vectors = self.orca_parser.normal_modes[mode_idx]
        # 내부 엔진 데이터
        elif self.tab_vibration._vib_result:
            vectors_raw = self.tab_vibration.get_displacement_vectors(mode_idx)
            if vectors_raw:
                vectors = [list(v) for v in vectors_raw]

        # [VIB-SPEC] 진동 원자 하이라이트 설정
        if (self.viewer and self.tab_vibration._vib_result
                and mode_idx < len(self.tab_vibration._vib_result.modes)):
            mode = self.tab_vibration._vib_result.modes[mode_idx]
            self.viewer._vib_highlight_indices = set(mode.bond_indices)
        elif self.viewer:
            self.viewer._vib_highlight_indices = set()

        if vectors and self.viewer and hasattr(self.viewer, 'start_vibration'):
            amp = self.tab_vibration.amp_slider.value() / 100.0
            self.viewer.start_vibration(vectors, amp)
            self.tab_vibration.btn_play.setChecked(True)
            self.tab_vibration.btn_play.setText("⏸ 정지")

    def _on_vib_toggle(self, play):
        """진동 애니메이션 재생/정지"""
        if not self.viewer or not hasattr(self.viewer, 'start_vibration'):
            return
        if play:
            row = self.tab_vibration.mode_list.currentRow()
            # [FIX-VIB-002] 모드 미선택 시 첫 번째 모드 자동 선택
            if row < 0 and self.tab_vibration.mode_list.count() > 0:
                self.tab_vibration.mode_list.setCurrentRow(0)
                row = 0
            vectors = None
            if (self.orca_parser and row >= 0
                    and row < len(self.orca_parser.normal_modes)):
                vectors = self.orca_parser.normal_modes[row]
            elif self.tab_vibration._vib_result:
                vectors_raw = self.tab_vibration.get_displacement_vectors(row)
                if vectors_raw:
                    vectors = [list(v) for v in vectors_raw]
            if vectors:
                amp = self.tab_vibration.amp_slider.value() / 100.0
                self.viewer.start_vibration(vectors, amp)
            else:
                logger.warning("Vibration toggle: no displacement vectors for mode %d", row)
        else:
            self.viewer.stop_vibration()

    def _on_internal_vib(self, result):
        """내부 진동 엔진 결과 처리"""
        # 결과는 이미 VibrationPanel에서 모드 목록에 표시됨
        # 여기서는 스펙트럼 탭에도 IR 스펙트럼을 표시
        if result.modes:
            freqs = [m.frequency_cm for m in result.modes]
            intensities = [m.ir_intensity * 100 for m in result.modes]
            try:
                self.tab_spectrum.plot_simple_ir(freqs, intensities)
            except Exception:
                pass  # SpectrumPanel에 plot_simple_ir가 없을 수 있음

    def _zoom_viewer_to_atoms(self, atom_indices: list):
        """진동 원자 영역으로 3D 뷰어 줌 & 하이라이트

        atom_indices: 진동에 관여하는 원자의 인덱스 리스트
        """
        if not self.viewer or not self.mol_data or not self.mol_data.atom_positions:
            return

        atom_keys = list(self.mol_data.atom_positions.keys())
        if not atom_keys:
            return

        # 1. Highlight: set highlighted atom indices on viewer
        self.viewer._vib_highlight_indices = set(atom_indices)

        # 2. Compute center of vibrating atoms
        positions = []
        for idx in atom_indices:
            if 0 <= idx < len(atom_keys):
                key = atom_keys[idx]
                if key in self.mol_data.atom_positions:
                    positions.append(self.mol_data.atom_positions[key])

        if not positions:
            return

        # Center of the vibrating region
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)
        cz = sum(p[2] for p in positions) / len(positions)

        # 3. Zoom in: increase zoom_scale and adjust pan to center on the region
        mol_cx, mol_cy, mol_cz = self.mol_data.get_center()
        dx = cx - mol_cx
        dy = cy - mol_cy

        w = self.viewer.width()
        h = self.viewer.height()
        bs = self.mol_data.get_bounding_size()
        current_scale = min(w, h) / (bs + 4.0) * 0.35 * self.viewer.zoom_scale

        # Zoom in to 2x if not already zoomed
        target_zoom = max(self.viewer.zoom_scale * 1.5, 2.0)
        if target_zoom > 5.0:
            target_zoom = 5.0

        self.viewer.zoom_scale = target_zoom
        self.viewer.pan_x = -dx * current_scale
        self.viewer.pan_y = -dy * current_scale

        # Update zoom slider if available
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.setValue(int(target_zoom * 100))

        self.viewer.update()

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

    # ── AlphaFold / 신약설계 탭 메서드 (Molecule3DPopup 소속) ──

    def _create_alphafold_synthesis_tab(self):
        """💊 신약설계 탭 — 학생 친화적 원클릭 UI.

        학생이 해야 하는 것: 목표 선택 → 버튼 클릭. 끝.
        나머지(표적 단백질, AlphaFold, 도킹, ADMET, 합성)는 시스템이 자동 처리.
        """
        from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                      QPushButton, QLabel, QComboBox,
                                      QGroupBox, QTextEdit, QProgressBar)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── 헤더 ──
        header = QLabel("💊 이 분자를 더 좋게 만들고 싶다면?")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #4a9eff;")
        layout.addWidget(header)

        subtitle = QLabel("아래에서 원하는 방향을 선택하고 '시작' 버튼을 누르세요.\n"
                          "나머지는 AI가 자동으로 처리합니다.")
        subtitle.setStyleSheet("color: #aaa; font-size: 11px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── 목표 선택 (학생용 자연어) ──
        goal_group = QGroupBox("어떤 효과를 원하시나요?")
        goal_group.setStyleSheet("QGroupBox { font-weight: bold; color: #ff9800; }")
        goal_layout = QVBoxLayout(goal_group)

        self._drug_goal_combo = QComboBox()
        self._drug_goal_combo.setStyleSheet("padding: 6px; font-size: 12px;")
        self._drug_goal_combo.addItems([
            "🎯 항암 효과를 추가하고 싶어",
            "🧠 뇌까지 약이 도달하게 하고 싶어 (BBB 투과)",
            "⏱️ 약효가 더 오래 지속되게 하고 싶어",
            "💧 물에 더 잘 녹게 하고 싶어",
            "🛡️ 부작용을 줄이고 싶어 (선택성 향상)",
            "⚡ 약이 더 빨리 분해되지 않게 하고 싶어 (대사 안정성)",
            "✏️ 직접 입력할래...",
        ])
        goal_layout.addWidget(self._drug_goal_combo)

        # 직접 입력 필드 (기본 숨김)
        from PyQt6.QtWidgets import QLineEdit
        self._drug_custom_goal = QLineEdit()
        self._drug_custom_goal.setPlaceholderText("예: 통증을 줄이면서 위장에 안전한 약을 만들고 싶어")
        self._drug_custom_goal.setStyleSheet("padding: 6px;")
        self._drug_custom_goal.hide()
        goal_layout.addWidget(self._drug_custom_goal)

        self._drug_goal_combo.currentIndexChanged.connect(
            lambda i: self._drug_custom_goal.setVisible(i == 6)
        )
        layout.addWidget(goal_group)

        # ── 실행 버튼 ──
        btn_row = QHBoxLayout()
        self._btn_drug_start = QPushButton("🚀 자동 분석 시작!")
        self._btn_drug_start.setStyleSheet(
            "QPushButton { background: #e65100; color: white; padding: 14px 24px; "
            "border-radius: 8px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #f57c00; }"
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        self._btn_drug_start.clicked.connect(self._run_drug_design)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_drug_start)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── 진행 상태 ──
        self._drug_progress = QProgressBar()
        self._drug_progress.setStyleSheet(
            "QProgressBar { border: 1px solid #555; border-radius: 4px; text-align: center; }"
            "QProgressBar::chunk { background: #4caf50; }"
        )
        self._drug_progress.hide()
        layout.addWidget(self._drug_progress)

        self._drug_status = QLabel("")
        self._drug_status.setStyleSheet("color: #aaa; font-size: 11px;")
        self._drug_status.setWordWrap(True)
        layout.addWidget(self._drug_status)

        # ── 결과 영역 ──
        self._drug_result = QTextEdit()
        self._drug_result.setReadOnly(True)
        self._drug_result.setStyleSheet(
            "background: #1a1a2e; color: #e0e0e0; border: 1px solid #333; "
            "border-radius: 4px; font-size: 11px; padding: 6px;"
        )
        self._drug_result.setMaximumHeight(200)
        self._drug_result.hide()
        layout.addWidget(self._drug_result)

        # ── 상세 분석 버튼 (결과 나온 후 표시) ──
        self._btn_drug_detail = QPushButton("📊 상세 분석 환경 열기 (리드 최적화)")
        self._btn_drug_detail.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; padding: 8px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1976d2; }"
        )
        self._btn_drug_detail.clicked.connect(self._open_lead_optimizer)
        self._btn_drug_detail.hide()
        layout.addWidget(self._btn_drug_detail)

        layout.addStretch()
        return widget

    def _run_drug_design(self):
        """원클릭 신약 설계 — 목표 → 유도체 생성 → 간이 스코어링."""
        from PyQt6.QtCore import QThread, pyqtSignal

        goal_idx = self._drug_goal_combo.currentIndex()
        goal_map = {
            0: "항암 효과 추가",
            1: "BBB 투과 개선",
            2: "지속 시간 개선",
            3: "수용성 개선",
            4: "선택성 향상",
            5: "대사 안정성 향상",
        }
        if goal_idx == 6:
            goal = self._drug_custom_goal.text().strip() or "범용 최적화"
        else:
            goal = goal_map.get(goal_idx, "범용 최적화")

        smiles = getattr(self, '_current_smiles', '') or ''
        if not smiles:
            self._drug_status.setText("⚠️ 먼저 분자를 입력해주세요!")
            return

        self._btn_drug_start.setEnabled(False)
        self._drug_progress.show()
        self._drug_progress.setRange(0, 0)  # indeterminate
        self._drug_status.setText(f"🔄 '{goal}' 방향으로 유도체 탐색 중...")
        self._drug_result.hide()
        self._btn_drug_detail.hide()

        class QuickDesignWorker(QThread):
            finished = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self, smi, goal_text, parent=None):
                super().__init__(parent)
                self._smi = smi
                self._goal = goal_text

            def run(self):
                try:
                    import sys
                    sys.path.insert(0, 'src/app')
                    from lead_optimizer import (
                        MoleculeVariantGenerator, translate_goal,
                        score_variant, calculate_sa_score
                    )
                    from admet_predictor import predict_admet

                    strategy = translate_goal(self._goal, self._smi)
                    gen = MoleculeVariantGenerator()
                    variants = gen.generate_all(self._smi, n_target=15, strategy=strategy)

                    if not variants:
                        self.finished.emit("유도체를 생성하지 못했습니다. 다른 분자를 시도해보세요.")
                        return

                    # Score each variant
                    for v in variants:
                        try:
                            p = predict_admet(v.smiles)
                            v.admet_pass = p.lipinski.passes
                            v.admet_violations = p.lipinski.violations
                            v.qed_score = p.drug_likeness_score
                            v.bbb_score = p.bbb.score
                        except Exception:
                            v.qed_score = 0.5
                        v.sa_score = calculate_sa_score(v.smiles)
                        v.docking_score = -6.0  # placeholder
                        score_variant(v, -5.0)

                    # Sort by rank
                    variants.sort(key=lambda x: x.composite_rank, reverse=True)

                    # Build result text
                    lines = [f"✅ {len(variants)}개 유도체 발견! (목표: {self._goal})\n"]
                    lines.append(f"전략: {strategy.name_kr}")
                    if strategy.rationale:
                        lines.append(f"근거: {strategy.rationale[:80]}\n")

                    lines.append("━━━ TOP 5 후보 ━━━")
                    for i, v in enumerate(variants[:5]):
                        tier_emoji = {"A": "🟢", "B": "🟡", "C": "🔴"}.get(v.tier, "⚪")
                        bbb = f"BBB={'통과' if v.bbb_score > 0.5 else '미통과'}" if v.bbb_score else ""
                        lines.append(
                            f"\n{i+1}위 {tier_emoji} [{v.tier}등급] 점수: {v.composite_rank:.2f}"
                        )
                        lines.append(f"   변형: {v.modification_detail}")
                        lines.append(f"   SMILES: {v.smiles[:50]}")
                        lines.append(f"   약물성(QED): {v.qed_score:.2f} | "
                                     f"합성난이도: {v.sa_score:.1f}/10 | {bbb}")

                    lines.append("\n💡 '상세 분석 환경'에서 도킹 시뮬레이션, 합성 경로,")
                    lines.append("   ADMET 분석을 더 자세히 확인할 수 있습니다.")

                    self.finished.emit("\n".join(lines))
                except Exception as e:
                    self.error.emit(str(e))

        def _on_done(text):
            self._drug_progress.hide()
            self._drug_progress.setRange(0, 100)
            self._btn_drug_start.setEnabled(True)
            self._drug_result.setPlainText(text)
            self._drug_result.show()
            self._btn_drug_detail.show()
            self._drug_status.setText("✅ 분석 완료!")

        def _on_error(msg):
            self._drug_progress.hide()
            self._btn_drug_start.setEnabled(True)
            self._drug_status.setText(f"⚠️ 오류: {msg}")

        self._quick_worker = QuickDesignWorker(smiles, goal)
        self._quick_worker.finished.connect(_on_done)
        self._quick_worker.error.connect(_on_error)
        self._quick_worker.start()

    def _open_alphafold(self):
        """AlphaFold 팝업 열기."""
        try:
            from popup_alphafold import AlphaFoldPopup
            popup = AlphaFoldPopup(parent=self)
            popup.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "AlphaFold", f"AlphaFold 열기 실패: {e}")

    def _open_synthesis(self):
        """합성경로 팝업 열기."""
        try:
            from popup_synthesis import SynthesisPopup
            smiles = getattr(self, '_current_smiles', '') or ''
            if not smiles:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "합성경로", "분자 SMILES가 없습니다. 먼저 분자를 로드하세요.")
                return
            popup = SynthesisPopup(target_smiles=smiles, parent=self)
            popup.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "합성경로", f"합성경로 열기 실패: {e}")

    def _open_lead_optimizer(self):
        """리드 최적화 팝업 열기."""
        try:
            from popup_lead_optimizer import LeadOptimizerPopup
            smiles = getattr(self, '_current_smiles', '') or ''
            popup = LeadOptimizerPopup(smiles=smiles, parent=self)
            popup.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "리드 최적화", f"리드 최적화 열기 실패: {e}")

    def _open_admet(self):
        """ADMET 팝업 열기."""
        try:
            from popup_admet import ADMETPopup
            smiles = getattr(self, '_current_smiles', '') or ''
            popup = ADMETPopup(smiles=smiles, parent=self)
            popup.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ADMET", f"ADMET 열기 실패: {e}")

    def closeEvent(self, event):
        if self.viewer and hasattr(self.viewer, 'stop_vibration'):
            self.viewer.stop_vibration()
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.cleanup()
        super().closeEvent(event)
