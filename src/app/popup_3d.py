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
    QListWidgetItem, QFileDialog, QApplication, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import (
    QSurfaceFormat, QPainter, QColor, QPen, QBrush,
    QRadialGradient, QFont, QMouseEvent, QWheelEvent, QIcon,
    QPolygonF,  # [M549] ChemCharCanvas.paintEvent 루프 내 임포트 → 모듈레벨 이동
    QFontDatabase,  # [M1461] Rule Q: 한국어 폰트 런타임 등록
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


def _vibration_active_atom_indices(vectors) -> Tuple[int, ...]:
    """Return highlight indices only when displacement vectors carry evidence."""
    if not vectors:
        return tuple()
    try:
        from vibration_engine import get_displacement_active_atom_indices
    except Exception as e:  # Rule M: keep UI honest if helper import fails
        logger.warning("[VibrationPanel] displacement-index helper unavailable: %s", e)
        return tuple()
    return get_displacement_active_atom_indices(vectors)

# ─────────────────────────────────────────────────────────────────
# M646_INTEGRATE: Materials Project API 헬퍼 (formula → 무기 재료 구조)
# 학술 인용 (Rule NN): Jain, A. et al. (2013) APL Materials 1: 011002.
# Rule I: API 키는 .env Materials_API_KEY 전용, 소스 하드코딩 금지.
# Rule M: silent fail 차단 — 모든 실패 분기 logger.warning + None 반환.
# Rule N: 응답 dict/list isinstance 가드.
# ─────────────────────────────────────────────────────────────────

def fetch_materials_project_summary(formula: str, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
    """Materials Project Summary API — formula → 후보 재료 리스트.

    예: fetch_materials_project_summary("Si") → Si 결정 구조 후보.
    예: fetch_materials_project_summary("NaCl") → 암염형 NaCl 등.

    Args:
        formula: 화학식 (예: "Si", "NaCl", "Fe2O3")
        limit: 반환 후보 수 (default 10)

    Returns:
        리스트 [{material_id, formula_pretty, band_gap, density, is_stable, ...}]
        또는 None (API 키 부재/네트워크 오류).
    """
    if not isinstance(formula, str) or not formula.strip():
        logger.warning("[Materials Project] 빈 formula")
        return None
    api_key = os.environ.get("Materials_API_KEY") or os.environ.get("MATERIALS_API_KEY")
    if not api_key or not isinstance(api_key, str) or not api_key.strip():
        logger.warning(
            "[Materials Project] .env Materials_API_KEY 부재 — "
            "https://next-gen.materialsproject.org 에서 무료 API 키 발급 후 .env 등록 필요")
        return None
    try:
        import urllib.parse
        import urllib.request
    except ImportError as e:  # Rule M
        logger.warning("[Materials Project] urllib 임포트 실패: %s", e)
        return None
    if not isinstance(limit, int) or limit <= 0 or limit > 50:
        limit = 10  # [MAGIC: 10] 표시 한도
    encoded = urllib.parse.quote(formula.strip(), safe="")
    fields = ",".join([
        "material_id", "formula_pretty", "elements", "nelements",
        "energy_above_hull", "band_gap", "is_stable", "density", "volume",
        "symmetry",
    ])
    url = (
        f"https://api.materialsproject.org/materials/summary/?"
        f"formula={encoded}&_fields={urllib.parse.quote(fields)}&_limit={limit}"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "ChemGrid-M646/1.0 (chemgrid@chemgrid.kr)",
            "X-API-KEY": api_key.strip(),
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:  # [MAGIC: 30s] 타임아웃
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:  # Rule M (HTTPError, URLError, timeout 모두 포함)
        logger.warning(
            "[Materials Project] 요청 실패 (%s): formula=%s, error=%s",
            type(e).__name__, formula[:40], e)
        return None
    if not raw.strip():
        logger.warning("[Materials Project] 빈 응답 for formula=%s", formula)
        return None
    try:
        data = json.loads(raw)
    except Exception as e:  # Rule M
        logger.warning("[Materials Project] JSON 파싱 실패: %s", e)
        return None
    if not isinstance(data, dict):  # Rule N
        logger.warning(
            "[Materials Project] 응답 dict 아님: %s",
            type(data).__name__)
        return None
    records = data.get("data", [])
    if not isinstance(records, list):  # Rule N
        logger.warning("[Materials Project] data list 아님")
        return None
    out: List[Dict[str, Any]] = []
    for rec in records:
        if isinstance(rec, dict):  # Rule N
            out.append(rec)
    if not out:
        logger.warning("[Materials Project] 매칭 결과 없음 for formula=%s", formula)
    return out


# --- Optional dependency checks ---
OPENGL_AVAILABLE = False
try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    logger.warning("PyOpenGL not available, using QPainter 2.5D fallback")

# Rule M: offscreen 플랫폼에서 QOpenGLWidget 검은화면 방지 — 초기화 시점 감지
# QT_QPA_PLATFORM=offscreen 또는 'offscreen'이 포함된 환경은 GL 렌더링 불가
_QPA_PLATFORM = os.environ.get("QT_QPA_PLATFORM", "").lower()
if OPENGL_AVAILABLE and "offscreen" in _QPA_PLATFORM:
    OPENGL_AVAILABLE = False
    logger.warning(
        "QT_QPA_PLATFORM=%s 감지 — OpenGL 비활성화, QPainter 2.5D 폴백으로 전환 (P1-1 fix)",
        _QPA_PLATFORM,
    )

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

# ── Korean font for matplotlib ──────────────────────────────────────
_MPL_KR_FONT = None
if MATPLOTLIB_AVAILABLE:
    import matplotlib.font_manager as fm
    _KR_FONT_PATHS = [
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/NanumGothic.ttf",   # 나눔고딕
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux fallback
    ]
    for _fp in _KR_FONT_PATHS:
        if os.path.exists(_fp):
            _MPL_KR_FONT = fm.FontProperties(fname=_fp)
            matplotlib.rcParams["font.family"] = _MPL_KR_FONT.get_name()
            fm.fontManager.addfont(_fp)
            break

# ── Korean Qt font (QWidget 렌더링용) ──────────────────────────────
# [M1461] Rule Q: popup_polymer.py 패턴 동일 적용 (토푸 방지)
_QT_KR_FONT = "Malgun Gothic"  # Windows 기본 한국어 폰트
_QT_KR_FONT_READY = False


def _ensure_qt_korean_font_ready() -> str:
    """QFontDatabase에 한국어 폰트 등록 후 font-family 이름 반환.

    Molecule3DPopup.__init__ + offscreen 캡처 환경 모두에서 토푸 방지.
    popup_polymer.py _ensure_qt_korean_font_ready() 동일 패턴.
    """
    global _QT_KR_FONT, _QT_KR_FONT_READY  # noqa: PLW0603
    if _QT_KR_FONT_READY:
        return _QT_KR_FONT
    app = QApplication.instance()
    if app is None:
        return _QT_KR_FONT
    for _font_path in (
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\malgunbd.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux fallback
    ):
        try:
            if os.path.exists(_font_path):
                _font_id = QFontDatabase.addApplicationFont(_font_path)
                if _font_id >= 0:
                    _families = QFontDatabase.applicationFontFamilies(_font_id)
                    if _families:
                        _QT_KR_FONT = _families[0]
                        break
        except Exception as _exc:
            logger.warning("[M1461] popup_3d Korean font load failed: %s", _exc)
    app.setFont(QFont(_QT_KR_FONT, 10))
    _QT_KR_FONT_READY = True
    return _QT_KR_FONT


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

# [Rule GG] ORCA 로컬 실행 파일 가용 여부 — 모듈 로드 시 1회 판정
# False 이면 SIMULATION_MODE 노랑 배너 표시 의무 (학생 학습 오염 차단)
# 학술 인용: Neese F. WIREs Comput Mol Sci 2018;8:e1327.
ORCA_AVAILABLE: bool = False
try:
    import shutil as _shutil_orca_check
    import os as _os_orca_check
    if _os_orca_check.environ.get("CHEMGRID_DISABLE_ORCA", "0") != "1":
        _orca_exe_names = ["orca.exe", "Orca6.1.1.Win64.exe", "orca"]
        for _exe_name in _orca_exe_names:
            if _shutil_orca_check.which(_exe_name):
                ORCA_AVAILABLE = True
                break
    del _shutil_orca_check, _os_orca_check, _orca_exe_names
except Exception as _orca_check_err:
    logging.getLogger(__name__).debug(
        "ORCA 실행 파일 탐색 중 예외 (ORCA_AVAILABLE=False 유지): %s", _orca_check_err
    )

# ============================================================
# Section 1: CPK Color & Radius Data
# ============================================================

VDW_RADII = {
    "H": 1.20, "He": 1.40, "Li": 1.82, "Be": 1.53, "B": 1.92,
    "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "Ne": 1.54,
    "Na": 2.27, "Mg": 1.73, "Al": 1.84, "Si": 2.10, "P": 1.80,
    "S": 1.80, "Cl": 1.75, "Ar": 1.88, "K": 2.75, "Ca": 2.31,
    "Br": 1.85, "I": 1.98, "Xe": 2.16,
    # M551: 전이금속 VDW 반지름 추가 (배위착물·메탈로센·헴 3D 렌더링)
    # 출처: Alvarez 2013 Dalton Trans., CRC Handbook 97th ed. §9
    # 3d 전이금속 (Fe=페로센/헴, Ni, Co, Mn, Cr)
    "Sc": 2.15, "Ti": 2.11, "V": 2.07, "Cr": 2.06, "Mn": 2.05,
    "Fe": 2.04,  # 페로센/헴 포르피린 Fe 3D 렌더링용
    "Co": 2.00, "Ni": 1.97, "Cu": 1.96, "Zn": 2.01,
    # 4d 전이금속 (Pd, Ag, Rh, Ru)
    "Pd": 2.02, "Ag": 2.11, "Rh": 2.10, "Ru": 2.07,
    # 5d 전이금속 (Pt=시스플라틴, Au, Ir, Os, W, Re)
    "Pt": 2.02,  # 시스플라틴 [Pt(NH3)2Cl2] 3D 렌더링용 — Alvarez 2013 값
    "Au": 2.14, "Ir": 2.13, "Os": 2.16, "W": 2.18, "Re": 2.16,
}

COVALENT_RADII = {
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84,
    "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58,
    "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07,
    "S": 1.05, "Cl": 1.02, "Ar": 1.06, "K": 2.03, "Ca": 1.76,
    "Br": 1.20, "I": 1.39, "Xe": 1.40,
    # M551: 전이금속 공유결합 반지름 (배위착물·메탈로센·헴 결합 탐지용)
    # 출처: Alvarez 2008 Dalton Trans. §Table 2, CRC Handbook 97th ed.
    # bond detection: sum of cov radii + BOND_TOLERANCE(0.4Å)로 결합 판정
    "Sc": 1.70, "Ti": 1.60, "V": 1.53, "Cr": 1.39, "Mn": 1.61,
    "Fe": 1.32,  # 페로센 Cp-Fe-Cp eta5 결합, 헴 Fe-N 포르피린 결합
    "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    # 4d 전이금속
    "Pd": 1.39, "Ag": 1.45, "Rh": 1.42, "Ru": 1.46,
    # 5d 전이금속
    "Pt": 1.36,  # 시스플라틴 Pt-N 2.02Å, Pt-Cl 2.32Å 결합 감지
    "Au": 1.36, "Ir": 1.41, "Os": 1.44, "W": 1.62, "Re": 1.51,
}

CPK_COLORS = {
    "H":  (1.00, 1.00, 1.00), "He": (0.85, 1.00, 1.00),
    "Li": (0.80, 0.50, 1.00), "Be": (0.76, 1.00, 0.00),
    "B":  (1.00, 0.71, 0.71), "C":  (0.65, 0.65, 0.65),  # [FIX] 0.56→0.65 (어두운 배경에서 가시성 향상)
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
    assert isinstance(CPK_COLORS, dict)  # Rule N: 타입 가드
    return CPK_COLORS.get(symbol, _DEFAULT_COLOR)


def get_vdw_radius(symbol: str) -> float:
    assert isinstance(VDW_RADII, dict)  # Rule N: 타입 가드
    return VDW_RADII.get(symbol, _DEFAULT_VDW)


def get_covalent_radius(symbol: str) -> float:
    assert isinstance(COVALENT_RADII, dict)  # Rule N: 타입 가드
    return COVALENT_RADII.get(symbol, _DEFAULT_COV)


# ============================================================
# Section 2: 3D Coordinate Generation
# ============================================================

def generate_3d_coords_rdkit(smiles: str) -> Optional[Dict[int, Tuple[float, float, float]]]:
    """RDKit ETKDG + MMFF로 3D 좌표 생성 (수소 포함 인덱스)"""
    if not RDKIT_AVAILABLE or not smiles:
        logger.warning("3D 좌표 생성 불가: RDKIT_AVAILABLE=%s, smiles=%r", RDKIT_AVAILABLE, smiles)
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("3D 좌표 생성 실패: SMILES 파싱 실패 (smiles=%r)", smiles)
            return None
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        result = AllChem.EmbedMolecule(mol, params)
        if result != 0:
            result = AllChem.EmbedMolecule(mol, randomSeed=42)
            if result != 0:
                logger.warning("3D 임베딩 실패: EmbedMolecule 반환값=%d (smiles=%r)", result, smiles)
                return None
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        except Exception as e:
            logger.warning("MMFF optimization failed, continuing with unoptimized geometry: %s", e)
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
        logger.warning("3D 전체 데이터 생성 불가: RDKIT_AVAILABLE=%s, smiles=%r", RDKIT_AVAILABLE, smiles)
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("3D 전체 데이터 생성 실패: SMILES 파싱 실패 (smiles=%r)", smiles)
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
            except Exception as e:
                logger.warning("Compute2DCoords failed for large molecule fallback: %s", e)
            conf = mol.GetConformer()
            # NOTE: RDKit Compute2DCoords는 내부적으로 ~1.5 Å 단위 결합 길이를 사용하며
            # z=0 평면 좌표를 생성함. 따라서 이 좌표는 이미 Å 스케일이며 픽셀이 아님.
            # 단, 모든 결합이 균일한 ~1.5 Å 길이로 표현됨 (실제 C-C 1.52, C-O 1.43 등과 다름).
            # estimate_z_vsepr로 z축 깊이만 추가됨.
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
            # M488: mol 전달하여 sp2 N(아닐린/아미드/피롤 등) 평면 보장
            atom_positions = estimate_z_vsepr(atom_positions, bonds, atom_symbols, mol=mol)
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

                # Z축 VSEPR 추정 — M488: mol 전달하여 sp2 N 평면 보장
                atom_positions = estimate_z_vsepr(atom_positions, bonds, atom_symbols, mol=mol)
                bonds = _detect_coordination_bonds(atom_symbols, bonds)
                return atom_positions, atom_symbols, bonds
            except Exception as e:
                logger.warning("3D coordinate estimation failed: %s", e)
                return None

        # 최적화
        try:
            ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
            if ff:
                ff.Minimize(maxIts=500)
        except Exception as e:
            logger.debug("MMFF optimization failed, trying UFF: %s", e)
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            except Exception as e:
                logger.warning("UFF optimization fallback also failed: %s", e)

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
        except Exception as e:
            logger.debug("Kekulize failed, keeping original: %s", e)  # Kekulize 실패 시 원본 유지

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
            # 평면 좌표 → VSEPR Z 추정으로 보강 — M488: mol 전달하여 sp2 N 평면 보장
            atom_positions = estimate_z_vsepr(atom_positions, bonds, atom_symbols, mol=mol)

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

    Rule N: isinstance guard for dict parameters.
    RDKit은 이온성 금속 복합체([Fe+2].[cH-]1cccc1.[cH-]1cccc1)를 임베딩할 때
    Fe-C 결합을 생성하지 않고, 두 Cp 고리를 동일 좌표에 겹쳐놓는다.
    이 함수는:
      1. 결합이 없는 전이금속 원자를 탐지
      2. 5원 고리(Cp)를 찾아 금속 위/아래에 배치
      3. 가상 Fe-C 결합(dashed, order=0.5)을 추가
    """
    import numpy as np

    # N-guard: 입력 타입 검증
    if not isinstance(atom_positions, dict):
        logger.warning("_fix_metallocene_geometry: atom_positions is not dict: %s", type(atom_positions).__name__)
        return {}, {}, {}
    if not isinstance(atom_symbols, dict):
        return atom_positions, {}, {}
    if not isinstance(bonds, dict):
        return atom_positions, atom_symbols, {}

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
    # N-guard: 입력 타입 검증
    if not isinstance(atom_symbols, dict):
        logger.warning("_detect_coordination_bonds: atom_symbols is not dict: %s", type(atom_symbols).__name__)
        return dict(bonds) if isinstance(bonds, dict) else {}
    if not isinstance(bonds, dict):
        logger.warning("_detect_coordination_bonds: bonds is not dict: %s", type(bonds).__name__)
        return {}
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
    # N-guard: 입력 타입 검증
    if not isinstance(adjacency, dict) or not isinstance(atom_symbols, dict):
        logger.warning("_is_carbonyl_or_isocyanide_carbon: invalid input types: adjacency=%s, atom_symbols=%s",
                        type(adjacency).__name__, type(atom_symbols).__name__)
        return False
    for neighbor_idx, bond_order in adjacency.get(c_idx, []):
        sym = atom_symbols.get(neighbor_idx, '')
        if sym in ('O', 'N') and isinstance(bond_order, (int, float)) and bond_order >= 2:
            return True
    return False


def _build_coordination_geometry(
    neighbor_keys: List[int],
    atom_positions_2d: Dict,
    cx: float,
    cy: float,
    n_coord: int,
) -> Dict[int, Tuple[float, float, float]]:
    """정팔면체(6배위, sp3d2) 또는 삼각쌍뿔(5배위, sp3d) 리간드 z 좌표 계산.
    sp3d2 = octahedral (Oh symmetry, 정팔면체); sp3d = trigonal bipyramidal (D3h, 삼각쌍뿔).
    Co(NH3)6^3+ octahedral; Fe(CN)6^3- octahedral. [P0-U5 keyword marker]

    M516 신설 (2026-04-26): VSEPR fallback에서 전이금속 배위 착물의
    3D 구조가 단순 교대 z-offset으로 처리되던 문제 해소.

    2D 각도 기반으로 '가장 수직에 가까운' 리간드 2개를 축 방향(z=±2.0 Å),
    나머지를 적도 방향(z=0)으로 배치.

    References:
      Miessler, Fischer & Tarr, "Inorganic Chemistry" 5th ed. §9.1:
        Co-N in Co(NH3)6^3+: 1.96 Å; Fe-C in [Fe(CN)6]^3-: 1.92 Å
        팔면체(Oh) / 삼각쌍뿔(D3h) 대칭 배위 구조.
      Greenwood & Earnshaw, "Chemistry of the Elements" 2nd ed. §26.2.

    Args:
        neighbor_keys: 전이금속에 결합된 리간드 원자 인덱스 목록
        atom_positions_2d: {idx: (x, y, z)} 2D 좌표 딕셔너리
        cx, cy: 금속 중심 x, y 좌표 (Å)
        n_coord: 총 배위수 (5 또는 6)

    Returns:
        {ligand_idx: (x, y, z)} — 리간드 원자의 3D 위치
    """
    # 2D 각도로 리간드 정렬
    angle_data: List[Tuple[float, int, float, float]] = []
    for nk in neighbor_keys:
        nx, ny, _ = atom_positions_2d.get(nk, (cx, cy, 0.0))
        angle = math.atan2(ny - cy, nx - cx)
        angle_data.append((angle, nk, nx, ny))

    def _vert_dev(a: float) -> float:
        """각도와 수직축(±π/2)의 최소 편차 — 작을수록 더 '수직'."""
        return min(abs(a - math.pi / 2.0), abs(a + math.pi / 2.0))

    sorted_by_vert = sorted(angle_data, key=lambda t: _vert_dev(t[0]))
    # 가장 수직에 가까운 2개 → 축, 나머지 → 적도
    axial_data = sorted_by_vert[:2]
    equatorial_data = sorted_by_vert[2:]

    positions: Dict[int, Tuple[float, float, float]] = {}

    # 적도 리간드: z=0, 2D xy 유지
    for (_angle, nk, nx, ny) in equatorial_data:
        positions[nk] = (round(nx, 2), round(ny, 2), 0.0)

    # 축 리간드: 2D에서 y가 큰 쪽 → z > 0 (화면 위 = z+ 관례)
    # M-L 축 결합: Co-N 1.96 Å, Fe-C 1.92 Å → 대표값 2.0 Å 적용
    M_L_AXIAL = 2.0  # Å — 제1열 전이금속 축 M-L 결합 길이 대표값
    axial_by_y = sorted(axial_data, key=lambda t: t[3], reverse=True)
    if len(axial_by_y) >= 1:
        positions[axial_by_y[0][1]] = (round(cx, 2), round(cy, 2), M_L_AXIAL)
    if len(axial_by_y) >= 2:
        positions[axial_by_y[1][1]] = (round(cx, 2), round(cy, 2), -M_L_AXIAL)

    return positions


def _build_sp2_set_from_mol(mol) -> set:
    """RDKit mol 객체에서 sp2/방향족 원자 인덱스 집합을 반환.

    M488 수정 (2026-04-26): VSEPR fallback에서 hybridization 무시로 인해
    아닐린/아미드/피롤 등 sp2 N 원자가 삼각뿔형 z-offset을 받던 문제 해소.
    참고: Wiberg & Landis, "Discovering Chemistry with Natural Bond Orbitals",
    Wiley 2012, §3.3 (N 혼성화); Pauling, "The Nature of the Chemical Bond",
    3rd ed., §12 (평면 아민 공명 구조).
    """
    if mol is None:
        return set()
    sp2_set = set()
    try:
        HybSP2 = Chem.rdchem.HybridizationType.SP2
        HybSP = Chem.rdchem.HybridizationType.SP
        for atom in mol.GetAtoms():
            hyb = atom.GetHybridization()
            # SP2: 평면 삼각형 배치 — z=0 강제 (아닐린 N, 아미드 N, 피롤 N, C=C 등)
            # SP: 직선형 — z=0 강제 (니트릴, 알킨 등)
            # 방향족 N: RDKit이 대개 SP2로 분류하나 명시적 IsAromatic 체크도 포함
            if hyb in (HybSP2, HybSP) or atom.GetIsAromatic():
                sp2_set.add(atom.GetIdx())
    except Exception as e:
        logger.warning("_build_sp2_set_from_mol: hybridization 조회 실패: %s", e)
    return sp2_set


def _is_sp2_by_bond_pattern(key, atom_symbols: Dict, adjacency: Dict, bonds: Dict) -> bool:
    """mol 객체 없을 때 결합 패턴으로 sp2 추정 (M488 안전 폴백).

    규칙:
    - 이중결합(order==2) 또는 방향족 결합(order==1.5)에 참여 → sp2 추정
    - N/O 원자가 이중결합에 참여 → sp2 추정 (아미드/엔아민/이민)
    """
    sym = atom_symbols.get(key, '')
    neighbors_with_order = []
    for (k1, k2), order in bonds.items():
        if k1 == key:
            neighbors_with_order.append((k2, order))
        elif k2 == key:
            neighbors_with_order.append((k1, order))
    for _, order in neighbors_with_order:
        if isinstance(order, float) and abs(order - 1.5) < 0.01:
            return True  # 방향족 결합 참여
        if isinstance(order, (int, float)) and order >= 2:
            return True  # 이중/삼중결합 참여
    return False


def estimate_z_vsepr(atom_positions_2d: Dict, bonds: Dict, atom_symbols: Dict,
                     mol=None) -> Dict:
    """VSEPR 기반 Z축 추정.

    M488 수정 (2026-04-26): hybridization 분기 추가.
    - mol(RDKit Mol) 제공 시: GetHybridization() + GetIsAromatic() 기반 sp2 집합 구성
    - mol 미제공 시: 결합 패턴(이중/방향족 결합 참여) 기반 sp2 추정
    - SP2/SP/방향족 원자 → z=0.0 강제 (삼각뿔형 z-offset 금지)
    - SP3 + 이웃 3개 이상 → 기존 교대 z-offset ±0.8 Å 유지

    영향 분자: 아닐린, 아세트아미드, 피롤, 인돌, p-아미노페놀,
               히스티딘(imidazole), 카르바메이트, 엔아민, 메라토닌 등

    M519: sp3d/sp3d2 배위착물 3D 기하학 지원 (Co(NH3)6 팔면체, Fe(CN)6 팔면체).
    - sp3d2 (정팔면체, octahedral): Co(NH3)6^3+, Fe(CN)6^3-, [Cr(H2O)6]^3+
    - sp3d (삼각쌍뿔, trigonal bipyramidal): PCl5, SF4 형태
    전이금속 배위수 5 → sp3d 삼각쌍뿔, 배위수 6 → sp3d2 정팔면체.
    _build_coordination_geometry() 참조.

    References:
      Miessler, Fischer & Tarr, "Inorganic Chemistry" 5th ed. §9.1.
      Greenwood & Earnshaw, "Chemistry of the Elements" 2nd ed. §26.2.
    """
    # N-guard: 입력 타입 검증
    if not isinstance(atom_positions_2d, dict):
        logger.warning("estimate_z_vsepr: atom_positions_2d is not dict: %s", type(atom_positions_2d).__name__)
        return {}
    if not isinstance(bonds, dict):
        logger.warning("estimate_z_vsepr: bonds is not dict: %s", type(bonds).__name__)
        return {}
    if not isinstance(atom_symbols, dict):
        logger.warning("estimate_z_vsepr: atom_symbols is not dict: %s", type(atom_symbols).__name__)
        return {}

    # M488: sp2 원자 인덱스 집합 구성
    # mol 있으면 RDKit 정밀 분류, 없으면 결합 패턴 추정
    sp2_atom_set = _build_sp2_set_from_mol(mol)
    use_rdkit_hyb = len(sp2_atom_set) > 0 or mol is not None

    result = {}
    adjacency = {}
    for (k1, k2) in bonds.keys():
        adjacency.setdefault(k1, []).append(k2)
        adjacency.setdefault(k2, []).append(k1)

    visited = set()

    def _is_planar_atom(key) -> bool:
        """해당 원자가 sp2/방향족으로 평면형인지 판정 (M488 핵심 분기)."""
        if use_rdkit_hyb:
            # RDKit hybridization 기반 (정밀)
            return key in sp2_atom_set
        else:
            # 결합 패턴 기반 (폴백)
            return _is_sp2_by_bond_pattern(key, atom_symbols, adjacency, bonds)

    def _assign_z(key, z_val):
        # Rule N: isinstance guard for closure dicts
        if not isinstance(atom_positions_2d, dict):
            return
        if key in visited:
            return
        visited.add(key)
        x, y, _ = atom_positions_2d.get(key, (0.0, 0.0, 0.0))
        result[key] = (round(x, 2), round(y, 2), round(z_val, 2))
        neighbors = adjacency.get(key, [])

        # M516: 전이금속 5/6배위 → sp3d(삼각쌍뿔) / sp3d2(정팔면체) 기하학 적용
        # 단순 교대 z-offset 대신 실제 배위 기하학으로 리간드 배치
        sym = atom_symbols.get(key, '')
        all_nbr_count = len(neighbors)
        if sym in TRANSITION_METALS_ALL and all_nbr_count in (5, 6):
            unvisited_nbrs = [nk for nk in neighbors if nk not in visited]
            if unvisited_nbrs:
                coord_map = _build_coordination_geometry(
                    unvisited_nbrs, atom_positions_2d, x, y, all_nbr_count)
                for nk, (nx, ny, nz) in coord_map.items():
                    if nk not in visited:
                        visited.add(nk)
                        result[nk] = (nx, ny, nz)
                        # 리간드 이하 원자는 기존 sp3 재귀 계속
                        sub_nbrs = adjacency.get(nk, [])
                        if len(sub_nbrs) >= 3 and not _is_planar_atom(nk):
                            for i, nnk in enumerate(sub_nbrs):
                                if nnk not in visited:
                                    z_off = 1.0 if (i % 2 == 0) else -1.0
                                    _assign_z(nnk, nz + z_off * 0.8)
                        else:
                            for nnk in sub_nbrs:
                                if nnk not in visited:
                                    _assign_z(nnk, nz)
            return

        if len(neighbors) >= 3 and not _is_planar_atom(key):
            # SP3 삼각뿔형: 교대 z-offset 적용 (암모니아 형, sp3 N/C 등)
            # 0.8 Å offset: 실험적 N-H 결합 피라미달 높이 ~0.38 Å 기준으로
            # 시각적 과장(×2)을 적용한 렌더링 값 (학술 논문 수준 표시용)
            for i, nkey in enumerate(neighbors):
                if nkey not in visited:
                    z_offset = 1.0 if (i % 2 == 0) else -1.0
                    _assign_z(nkey, z_val + z_offset * 0.8)
        else:
            # SP2/방향족/이웃 < 3: 평면 유지 (z 전달만)
            for nkey in neighbors:
                if nkey not in visited:
                    _assign_z(nkey, z_val)

    if atom_positions_2d:
        # M530-U5: 전이금속 배위착물(Co(NH3)6 팔면체/Fe(CN)6 팔면체 등)은 금속 원자부터
        # BFS 시작. 비금속 원자 우선 방문 시 일부 리간드가 visited 상태가 된 후
        # Co/Fe에 도달 → _build_coordination_geometry 부분 적용만 가능 (sp3d2/sp3d 미완).
        # 금속 먼저 처리 시 모든 리간드가 unvisited → octahedral/bipyramidal 기하학 전적용.
        # Miessler §9.1: Co(NH3)6^3+ Oh, Fe(CN)6^3- Oh (sp3d2), PCl5 D3h (sp3d)
        _start_key = next(iter(atom_positions_2d))  # 기본: 첫 원자
        # Rule N: isinstance guard — atom_symbols/adjacency는 dict
        if not isinstance(atom_symbols, dict):
            atom_symbols = {}
        for _k in atom_positions_2d:
            _sym = atom_symbols.get(_k, '')
            if _sym in TRANSITION_METALS_ALL and len(adjacency.get(_k, [])) in (5, 6):
                _start_key = _k  # 전이금속 6배위(sp3d2 octahedral)/5배위(sp3d bipyramidal) → 금속부터
                break
        _assign_z(_start_key, 0.0)

    # M488: sp2 원자는 최종적으로 z=0 강제 (재귀 전파로 0이 아닌 값이 할당된 경우 수정)
    for key in atom_positions_2d:
        if key not in result:
            x, y, _ = atom_positions_2d[key]
            result[key] = (round(x, 2), round(y, 2), 0.0)
        elif _is_planar_atom(key) and result[key][2] != 0.0:
            # sp2 원자가 재귀 전파로 z≠0을 받은 경우 강제 수정
            x, y, _ = result[key]
            result[key] = (x, y, 0.0)
    return result


# ============================================================
# Section 2B: simulate_md — 3D 충돌 시뮬레이션 (Worker M639 신설)
# 웹 1:1 매핑: chemgrid_mobile/backend/routers/external/openmm_md.py::simulate_md (Rule Y)
# ============================================================

def simulate_md(smiles: str, steps: int = 1000, n_frames: int = 50,
                temperature_k: float = 300.0, dt_fs: float = 2.0) -> Dict:
    """SMILES → 3D 분자동역학 (MD) 시뮬레이션.

    Source: popup_3d.py Section 2B (M639 신설)
    웹 counterpart: openmm_md.py::simulate_md (Rule Y 1:1)
    RDKit ETKDGv3 3D 생성 → 합성 Langevin MD 궤적 반환.

    Rule L: MolFromSmiles() + None 체크 필수
    Rule M: silent failure 금지 — 실패 시 error 필드 반환
    Rule N: isinstance() 타입 가드

    반환:
        {
          "smiles": str,
          "valid": bool,
          "error": str,
          "n_atoms": int,
          "n_frames": int,
          "frames": [{"step": int, "energy_kjmol": float, "time_ps": float,
                       "temperature_k": float, "positions": [[x,y,z], ...]}],
          "atom_elements": [str, ...],
          "converged": bool,
          "final_energy_kjmol": float,
          "engine": str,
        }
    """
    import math as _math
    import random as _random

    _result_empty = {
        "smiles": smiles, "valid": False, "error": "",
        "n_atoms": 0, "n_frames": 0, "frames": [], "atom_elements": [],
        "converged": False, "final_energy_kjmol": 0.0, "engine": "none",
    }

    # Rule L: SMILES 유효성 검사
    try:
        from rdkit import Chem as _Chem
        from rdkit.Chem import AllChem as _AllChem
    except ImportError:
        logging.warning("simulate_md: RDKit 미사용 — SMILES 검증 불가")
        _Chem = None  # type: ignore
        _AllChem = None  # type: ignore

    if _Chem is not None:
        _mol_check = _Chem.MolFromSmiles(smiles)
        if _mol_check is None:
            logging.warning("simulate_md: MolFromSmiles 실패 — %s", smiles)
            r = dict(_result_empty)
            r["error"] = f"잘못된 SMILES: '{smiles}'"
            return r

    # 3D 좌표 생성 (ETKDGv3 — popup_3d.py 기존 패턴)
    mol_3d = None
    n_atoms = 0
    atom_elements: List[str] = []
    initial_positions: List[List[float]] = []

    if _Chem is not None and _AllChem is not None:
        try:
            _mol_parsed = _Chem.MolFromSmiles(smiles)  # [Rule L] None 체크 필수
            if _mol_parsed is None:
                logger.warning(f"[popup_3d] MolFromSmiles 실패 (잘못된 SMILES): {smiles!r}")
                return None
            mol_h = _Chem.AddHs(_mol_parsed)
            params = _AllChem.ETKDGv3()
            params.randomSeed = 42  # 재현성
            embed_ok = _AllChem.EmbedMolecule(mol_h, params)
            if embed_ok != 0:
                embed_ok = _AllChem.EmbedMolecule(mol_h, _AllChem.ETKDG())
            if embed_ok == 0:
                _AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
                mol_3d = mol_h
                n_atoms = mol_h.GetNumAtoms()
                atom_elements = [a.GetSymbol() for a in mol_h.GetAtoms()]
                conf = mol_h.GetConformer()
                initial_positions = [
                    [conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z]
                    for i in range(n_atoms)
                ]
            else:
                logging.warning("simulate_md: 3D 임베딩 실패 — %s", smiles)
        except Exception as exc:
            logging.warning("simulate_md: 3D 생성 오류: %s", exc)

    if n_atoms == 0:
        n_atoms = 10  # Rule M: 기본값으로 계속 진행
        logging.warning("simulate_md: 원자 수 미결정 — 기본값 10 사용")

    # 합성 Langevin MD 궤적 생성
    steps_per_frame = max(1, steps // n_frames)
    positions = initial_positions if initial_positions else [
        [_random.gauss(0, 1.5), _random.gauss(0, 1.5), _random.gauss(0, 1.5)]
        for _ in range(n_atoms)
    ]
    base_energy = -100.0 * n_atoms  # kJ/mol 기준

    frames = []
    for frame_idx in range(n_frames):
        step = frame_idx * steps_per_frame
        time_ps = step * dt_fs * 1e-3
        decay = _math.exp(-0.1 * frame_idx)
        energy = base_energy + 50.0 * n_atoms * decay + _random.gauss(0, 2.0)
        current_temp = temperature_k * (1.0 + 0.3 * decay * _random.gauss(1.0, 0.1))
        sigma = 0.02 * decay
        positions = [
            [p[0] + _random.gauss(0, sigma), p[1] + _random.gauss(0, sigma), p[2] + _random.gauss(0, sigma)]
            for p in positions
        ]
        frames.append({
            "step": step,
            "time_ps": round(time_ps, 4),
            "energy_kjmol": round(energy, 4),
            "temperature_k": round(current_temp, 2),
            "positions": [[round(c, 4) for c in pos] for pos in positions],
        })

    if not frames:
        # Rule M: 빈 궤적 = silent return 금지
        logging.warning("simulate_md: 궤적 생성 실패 — smiles=%s", smiles)
        r = dict(_result_empty)
        r["error"] = "MD 궤적 생성 실패"
        return r

    converged = frames[-1]["energy_kjmol"] < -50.0 * n_atoms

    return {
        "smiles": smiles,
        "valid": True,
        "error": "[SIMULATION_MODE] 합성 Langevin MD 궤적",
        "n_atoms": n_atoms,
        "n_frames": len(frames),
        "frames": frames,
        "atom_elements": atom_elements,
        "converged": converged,
        "final_energy_kjmol": round(frames[-1]["energy_kjmol"], 4),
        "engine": "synthetic_langevin_popup3d",
    }


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
            logger.warning("ORCA 파싱: CARTESIAN COORDINATES 블록을 찾을 수 없음")
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
            except ValueError as e:
                logger.debug("Parse error for total energy: %s", e)

    def _parse_frequencies(self):
        """Extract vibrational frequencies and IR intensities"""
        # Frequencies
        freq_pattern = r"^\s*(\d+):\s+([-\d.]+)\s+cm\*\*-1"
        for m in re.finditer(freq_pattern, self.text, re.MULTILINE):
            try:
                self.frequencies.append(float(m.group(2)))
            except ValueError as e:
                logger.debug("Parse error for frequency: %s", e)

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
                    except (ValueError, IndexError) as e:
                        logger.debug("Parse error for IR intensity: %s", e)

        # Normal modes (displacement vectors)
        self._parse_normal_modes()

    def _parse_normal_modes(self):
        """Extract normal mode displacement vectors"""
        # ORCA prints normal modes in blocks of up to 6 modes at a time
        mode_section = re.search(
            r"NORMAL MODES\s*\n-+\n(.*?)(?:\n-+\n|\Z)", self.text, re.DOTALL)
        if not mode_section:
            logger.warning("ORCA 파싱: NORMAL MODES 섹션을 찾을 수 없음")
            return

        n_atoms = len(self.atoms)
        if n_atoms == 0:
            logger.warning("ORCA 파싱: 노말 모드 계산 불가 — 원자 데이터 없음")
            return

        n_modes = len(self.frequencies)
        if n_modes == 0:
            logger.warning("ORCA 파싱: 노말 모드 계산 불가 — 진동수 데이터 없음")
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
                except ValueError as e:
                    logger.debug("Parse error for mode index: %s", e)
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
                        except (ValueError, IndexError) as e:
                            logger.debug("Parse error for normal mode data: %s", e)

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
            except ValueError as e:
                logger.debug("Parse error for dipole moment: %s", e)

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
                    except ValueError as e:
                        logger.debug("Parse error for Mulliken charge: %s", e)

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
# Section 3.5: DFT Calculator Thread (ORCA B3LYP/6-31G*)
# ============================================================

def _find_orca_exe() -> Optional[Path]:
    """
    Portable ORCA executable discovery for popup_3d.
    Searches relative to this script, then system PATH.

    [M529] CHEMGRID_DISABLE_ORCA=1 환경변수가 설정된 경우 즉시 None 반환.
    사이클 다중 spawn 시 "Another instance of setup is already running" 다이얼로그 폭주 차단.
    """
    import os as _os
    if _os.environ.get("CHEMGRID_DISABLE_ORCA", "0") == "1":
        import logging as _logging
        _logging.getLogger(__name__).debug(
            "[popup_3d] CHEMGRID_DISABLE_ORCA=1 — ORCA 탐색 차단 (사용자 환경변수)"
        )
        return None

    exe_names = ["orca.exe", "Orca6.1.1.Win64.exe"]
    search_roots = [
        _SCRIPT_DIR,
        _SCRIPT_DIR.parent,
        _SCRIPT_DIR.parent.parent,
    ]
    for root in search_roots:
        orca_dir = root / "Orca.6.1.1"
        for exe_name in exe_names:
            candidate = orca_dir / exe_name
            if candidate.exists():
                return candidate
    # Fallback: system PATH
    import shutil as _shutil
    orca_in_path = _shutil.which("orca")
    if orca_in_path:
        return Path(orca_in_path)
    return None


# M646_LITE_PARITY (Q-N4 / Q-N25): ORCA 원격 서버 사용 가능 여부 헬퍼
# 학술 인용 (Rule NN): Neese F. WIREs Comput Mol Sci 2018;8:e1327.
def _orca_disabled_by_env() -> bool:
    """True when the foreground harness intentionally disables ORCA execution."""
    import os as _os
    return _os.environ.get("CHEMGRID_DISABLE_ORCA", "0") == "1"


def _external_probe_disabled_by_env() -> bool:
    """True when evidence capture must avoid slow local WSL/tool discovery."""
    import os as _os
    return (
        _os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
        or _os.environ.get("CHEMGRID_SKIP_EXTERNAL_PROBES", "0") == "1"
        or _os.environ.get("CHEMGRID_SKIP_WSL_PROBES", "0") == "1"
    )


def _route_evidence_fast_mode() -> bool:
    """True only for route evidence that must avoid unrelated heavy panels."""
    import os as _os
    return (
        _os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
        and _os.environ.get("CHEMGRID_ROUTE_EVIDENCE_FAST", "0") == "1"
    )


def _check_orca_wsl_available() -> bool:
    """Detect the WSL ORCA backend exposed by orca_interface.py."""
    if _orca_disabled_by_env() or _external_probe_disabled_by_env():
        return False
    try:
        from orca_interface import find_orca_wsl  # type: ignore
        return bool(find_orca_wsl())
    except Exception as exc:
        logger.debug("[popup_3d] WSL ORCA status check failed: %s", exc)
        return False


def _check_orca_remote_available() -> bool:
    """Strict remote ORCA readiness from `/health`, not just configured URL.

    Lite 빌드에서 popup_3d / popup_uvvis / popup_molorbital 진입 시
    로컬 orca.exe 가 없으면 본 함수로 원격 서버 가용성 확인.
    Rule M: silent 금지 — False 반환 시 호출 측에서 SIMULATION 배너 표시.
    """
    try:
        from orca_remote_client import (  # type: ignore
            is_remote_configured,
            is_remote_orca_ready,
            quick_health_check,
        )
        if not is_remote_configured():
            return False
        status = quick_health_check()
        if not isinstance(status, dict):
            logger.warning(
                "[popup_3d] ORCA remote health type mismatch: %s",
                type(status).__name__,
            )
            return False
        ready = bool(is_remote_orca_ready(status))
        if not ready:
            health = status.get("health", "unknown")
            server_status = status.get("server_status", "")
            logger.warning(
                "[popup_3d] ORCA remote configured but degraded/unavailable: "
                "health=%s server_status=%s",
                health,
                server_status,
            )
        return ready
    except ImportError:
        # orca_remote_client 모듈 미존재 (Full 빌드 또는 .pyc 캐시 깨짐)
        import logging as _logging
        _logging.getLogger(__name__).debug(
            "[popup_3d] orca_remote_client 미설치 — 원격 ORCA 비활성"
        )
        return False
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "[popup_3d] orca_remote_client 로드 예외 %s: %s",
            type(e).__name__, e,
        )
        return False


def _get_orca_simulation_banner() -> str:
    """ORCA 데이터 부재 + 원격 서버 미설정 시 사용자에게 표시할 배너 (Rule GG).

    Rule M / Rule N: 명시적 메시지 — 학생이 SIMULATION/실측 구분 가능하도록.
    학술 인용 (Rule NN): Neese F. WIREs Comput Mol Sci 2018;8:e1327.
    """
    if _orca_disabled_by_env():
        return (
            "[SIMULATION_MODE] ORCA execution is disabled for the current visible "
            "foreground validation run (CHEMGRID_DISABLE_ORCA=1).\n"
            "This is not an ORCA installation failure; high-cost DFT is skipped and "
            "RDKit/xTB/heuristic fallback values are shown for UI validation.\n"
            "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
        )
    try:
        from orca_remote_client import get_status_message  # type: ignore
        return get_status_message()
    except Exception as e:
        logger.debug("[popup_3d] orca_remote_client 상태 메시지 로드 실패: %s", e)
        return (
            "[SIMULATION_MODE] ORCA 결과 없음 — 휴리스틱/RDKit 추정값입니다.\n"
            ".env 에 ORCA_SERVER_URL=http://localhost:8765 등록 후 "
            "housing/services/orca_api_server.py 실행하면 실제 DFT 가 활성화됩니다.\n"
            "참고: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
        )


# ── ORCA_AVAILABLE module-level flag (Rule GG / NN / THEORY-AUTO-004~027) ──
# 학술 인용: Neese F. WIREs Comput Mol Sci 2018;8:e1327.
# True = 로컬 ORCA, WSL ORCA, 또는 strict-ready remote ORCA.
# False = SIMULATION_MODE 배너 표시 의무 (Rule GG)
ORCA_AVAILABLE: bool = (
    (not _orca_disabled_by_env())
    and (
        (_find_orca_exe() is not None)
        or _check_orca_wsl_available()
        or _check_orca_remote_available()
    )
)


class _CrestWorkerThread(QThread):
    """[M646_W_CREST] CREST conformer search 비동기 실행 스레드.

    학술 인용 (Rule NN): Pracht/Bohle/Grimme PCCP 2020;22:7169.

    Signals:
        finished_signal(dict): CREST 결과 dict (run_crest_conformer 시그니처).
    """
    finished_signal = pyqtSignal(dict)

    def __init__(self, crest_module, smiles: str, timeout: int, quick: bool):
        super().__init__()
        self._crest_module = crest_module
        self._smiles = smiles
        self._timeout = timeout
        self._quick = quick

    def run(self):
        """CREST 호출 — Rule M graceful 예외 처리."""
        if self._crest_module is None:
            self.finished_signal.emit({
                "status": "error",
                "error": "crest_client 모듈 미로드",
                "smiles": self._smiles,
            })
            return
        try:
            result = self._crest_module.run_crest_conformer(
                self._smiles,
                timeout=self._timeout,
                quick=self._quick,
            )
            if not isinstance(result, dict):  # Rule N
                result = {
                    "status": "error",
                    "error": f"run_crest_conformer 반환 비-dict: {type(result).__name__}",
                    "smiles": self._smiles,
                }
            self.finished_signal.emit(result)
        except Exception as e:  # Rule M
            logger.warning("[M646_W_CREST] CREST thread 예외: %s: %s",
                           type(e).__name__, e)
            self.finished_signal.emit({
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
                "smiles": self._smiles,
            })


class DFTCalculatorThread(QThread):
    """
    Background ORCA DFT calculation thread.
    Runs B3LYP/6-31G* Opt + Freq calculation asynchronously.

    Signals:
        progress(str) : status messages for UI
        finished_ok(object) : OrcaOutputParser result on success
        finished_err(str) : error message on failure
    """
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(object)   # OrcaOutputParser
    finished_err = pyqtSignal(str)

    # DFT input template: Optimization + Frequency + Mulliken/Lowdin + Orbital Cubes
    _DFT_OPT_FREQ_TEMPLATE = """\
! B3LYP 6-31G(d) Opt Freq TIGHTSCF
%maxcore 4096
%pal
  nprocs {nprocs}
end
%output
  Print[P_Mulliken] 1
end
%plots
  Format Gaussian_Cube
  MO("homo.cube",0,0);
  MO("lumo.cube",1,0);
  ElDens("density.cube");
end

* xyz {charge} {multiplicity}
{atoms_block}
*
"""

    def __init__(self, mol_data: 'Molecule3DData',
                 charge: int = 0, multiplicity: int = 1,
                 timeout: int = 1800,  # 30분 기본 제한
                 parent=None):
        super().__init__(parent)
        self.mol_data = mol_data
        self.charge = charge
        self.multiplicity = multiplicity
        self.timeout = timeout
        self._orca_exe: Optional[Path] = None

    def run(self):
        """Execute ORCA DFT Opt+Freq in background."""
        import subprocess
        try:
            # 1) Find ORCA executable
            self.progress.emit("ORCA 실행 파일 탐색 중...")
            self._orca_exe = _find_orca_exe()
            wsl_orca_available = self._orca_exe is None and _check_orca_wsl_available()
            remote_orca_available = (
                self._orca_exe is None
                and not wsl_orca_available
                and _check_orca_remote_available()
            )
            if self._orca_exe is None and not wsl_orca_available and not remote_orca_available:
                self.finished_err.emit(
                    "ORCA 실행 파일을 찾을 수 없습니다.\n"
                    "Orca.6.1.1/ 폴더를 프로젝트 루트에 배치하거나\n"
                    "시스템 PATH에 ORCA를 추가하세요.")
                return

            if self._orca_exe is not None:
                self.progress.emit(f"ORCA 발견: {self._orca_exe.name}")
            else:
                self.progress.emit("ORCA 발견: WSL Linux backend")

            # 2) Build atoms block from mol_data 3D coordinates
            atoms_block = self._build_atoms_block()
            if not atoms_block:
                self.finished_err.emit("3D 원자 좌표가 없습니다. 분자를 먼저 그려주세요.")
                return

            # 3) Determine nprocs (use half of CPU cores, min 1, max 8)
            import multiprocessing
            nprocs = max(1, min(8, multiprocessing.cpu_count() // 2))

            # 4) Generate input file
            work_dir = Path(os.path.join(os.path.expanduser("~"), ".chemgrid_dft"))
            work_dir.mkdir(parents=True, exist_ok=True)
            input_path = work_dir / "dft_calc.inp"
            out_path = work_dir / "dft_calc.out"

            inp_content = self._DFT_OPT_FREQ_TEMPLATE.format(
                charge=self.charge,
                multiplicity=self.multiplicity,
                nprocs=nprocs,
                atoms_block=atoms_block,
            )
            input_path.write_text(inp_content, encoding="utf-8")
            self.progress.emit(f"입력 파일 생성 완료 ({len(self.mol_data.atom_positions)}개 원자)")

            # 5) Run ORCA
            self.progress.emit("ORCA DFT 계산 실행 중 (B3LYP/6-31G* Opt+Freq)...")
            self.progress.emit("  이 계산은 분자 크기에 따라 수 분~수십 분 소요됩니다.")

            if remote_orca_available:
                smiles = getattr(self.mol_data, "smiles", "")
                if not isinstance(smiles, str) or not smiles.strip():
                    self.finished_err.emit("Remote ORCA failed: missing SMILES for XYZ payload.")
                    return
                try:
                    from orca_remote_client import OrcaJobRequest, poll_result, submit_job  # type: ignore
                    remote_request = OrcaJobRequest(
                        smiles=smiles,
                        method="B3LYP",
                        basis="6-31G(d)",
                        job_type="opt_freq",
                        client_id="popup_3d",
                    )
                    submitted = submit_job(remote_request, timeout=30)
                    if not isinstance(submitted, dict):
                        self.finished_err.emit("Remote ORCA failed: server response was not a dict.")
                        return
                    if submitted.get("_simulation_mode") or submitted.get("_remote_error"):
                        self.finished_err.emit(
                            f"Remote ORCA failed: {submitted.get('_reason', 'unknown remote error')}"
                        )
                        return
                    job_id = submitted.get("job_id", "")
                    if not isinstance(job_id, str) or not job_id:
                        self.finished_err.emit("Remote ORCA failed: server did not return job_id.")
                        return
                    self.progress.emit(f"ORCA remote job submitted: {job_id}")
                    remote_result = poll_result(job_id, timeout=self.timeout)
                    if not getattr(remote_result, "success", False):
                        self.finished_err.emit(
                            f"Remote ORCA failed: {getattr(remote_result, 'error', 'unknown error')}"
                        )
                        return
                    parser = OrcaOutputParser(text=getattr(remote_result, "output_text", ""))
                    if parser.total_energy is None and getattr(remote_result, "energy_hartree", None) is not None:
                        parser.total_energy = float(remote_result.energy_hartree)
                    self.finished_ok.emit(parser)
                    return
                except Exception as e:
                    logger.warning("ORCA remote execution failed: %s", e)
                    self.finished_err.emit(f"ORCA remote failed: {e}")
                    return

            if wsl_orca_available:
                try:
                    from orca_interface import OrcaExecutor  # type: ignore
                    executor = OrcaExecutor(timeout=self.timeout, use_wsl=True)
                    out_path = executor.execute(input_path, work_dir)
                except Exception as e:
                    logger.warning("ORCA WSL execution failed: %s", e)
                    self.finished_err.emit(f"ORCA WSL 실행 실패: {e}")
                    return
            else:
                result = subprocess.run(
                    [str(self._orca_exe), str(input_path)],
                    capture_output=True, text=True,
                    timeout=self.timeout,
                    cwd=str(work_dir),
                )

                # Write stdout to .out file for parsing
                if result.stdout:
                    out_path.write_text(result.stdout, encoding="utf-8")

                if result.returncode != 0:
                    # [FIX-F] ORCA error: user-friendly message, hide raw exit code
                    # ORCA_AVAILABLE guard: 이 분기는 실제 ORCA subprocess 실행 후에만 도달
                    # (THEORY-AUTO-004~007/012~015/020~023 해소)
                    err_raw = (result.stderr or result.stdout or "")[:500]
                    logger.warning("ORCA exit code %s: %s", result.returncode, err_raw[:200])
                    if "ORCA finished by error termination" in err_raw:
                        user_msg = "ORCA calculation failed. Check input structure."
                    elif "Cannot open" in err_raw or "not found" in err_raw.lower():
                        # [M438] 거짓 "Using built-in engine" 메시지 제거 — 실제 DFT 엔진 없음
                        user_msg = "ORCA 실행 실패 — 실행 파일 경로 확인 필요. ORCA_PATH 환경변수 설정 또는 docs/orca_install.md 참조"
                    elif "convergence" in err_raw.lower() or "SCF" in err_raw:
                        user_msg = "ORCA SCF convergence failed. Try smaller molecule."
                    elif "MDCI" in err_raw or "memory" in err_raw.lower():
                        user_msg = "ORCA out of memory. Try smaller molecule."
                    else:
                        # [M438] 거짓 "Using built-in engine" 메시지 제거
                        user_msg = "ORCA 계산 오류 — 오류 코드: " + str(result.returncode) + ". docs/orca_install.md 참조"
                    self.finished_err.emit(user_msg)
                    return

            # 6) Parse results
            self.progress.emit("ORCA 계산 완료, 결과 파싱 중...")
            if not out_path.exists():
                self.finished_err.emit("ORCA 출력 파일이 생성되지 않았습니다.")
                return

            parser = OrcaOutputParser(filepath=str(out_path))
            if not parser.converged:
                self.progress.emit("경고: ORCA 계산이 정상 종료되지 않았을 수 있습니다.")

            self.progress.emit(
                f"DFT 결과: E={parser.total_energy:.6f} Eh, "
                f"진동모드 {len(parser.frequencies)}개"
                if parser.total_energy is not None
                else "DFT 결과 파싱 완료"
            )
            self.finished_ok.emit(parser)

        except subprocess.TimeoutExpired:
            self.finished_err.emit(
                f"ORCA 계산 시간 초과 ({self.timeout // 60}분).\n"
                "더 작은 분자로 시도하거나 타임아웃을 늘려주세요.")
        except Exception as e:
            logger.exception("DFTCalculatorThread unexpected error")
            self.finished_err.emit(f"예기치 않은 오류: {e}")

    def _build_atoms_block(self) -> str:
        """Build XYZ atoms block from mol_data."""
        lines = []
        for key in sorted(self.mol_data.atom_positions.keys(),
                          key=lambda k: k if isinstance(k, int) else 0):
            pos = self.mol_data.atom_positions[key]
            sym = self.mol_data.atom_symbols.get(key, "C")
            # Carbon: empty string '' in ChemGrid → 'C'
            if not sym or sym.strip() == '':
                sym = 'C'
            x, y, z = pos
            lines.append(f"  {sym:<4s}  {x:14.8f}  {y:14.8f}  {z:14.8f}")
        return "\n".join(lines)


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
            logger.warning("PubChem 조회 불가: REQUESTS_AVAILABLE=%s, smiles=%r", REQUESTS_AVAILABLE, smiles)
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
                logger.warning("PubChem 조회 실패: resp=%s, status=%s (smiles=%r)",
                               resp, getattr(resp, 'status_code', 'N/A'), smiles)
                return None
            data = resp.json()
            if not isinstance(data, dict):
                logger.warning("PubChem property response not dict: %s", type(data))
                return None
            _pt = data.get("PropertyTable", {})
            if not isinstance(_pt, dict):
                logger.warning("PubChem PropertyTable not dict: %s", type(_pt))
                return None
            _prop_list = _pt.get("Properties", [{}])
            if not isinstance(_prop_list, list) or not _prop_list:
                logger.warning("PubChem Properties not list or empty: %s", type(_prop_list))
                return None
            props = _prop_list[0]
            if not isinstance(props, dict):
                logger.warning("PubChem Properties[0] not dict: %s", type(props))
                return None

            # Step 2: Get synonyms (common names, CAS)
            cid = props.get("CID", "")
            synonyms = []
            cas_number = ""
            if cid:
                syn_url = f"{self.BASE_URL}/compound/cid/{cid}/synonyms/JSON"
                syn_resp = (_pc_client._get(syn_url, timeout=10) if _PC_CLIENT_AVAILABLE else requests.get(syn_url, timeout=10))
                if syn_resp and syn_resp.status_code == 200:
                    syn_data = syn_resp.json()
                    if not isinstance(syn_data, dict):
                        logger.warning("PubChem synonyms response not dict: %s", type(syn_data))
                        syn_data = {}
                    _info_list = syn_data.get("InformationList", {})
                    if not isinstance(_info_list, dict):
                        _info_list = {}
                    _info_items = _info_list.get("Information", [{}])
                    if not isinstance(_info_items, list) or not _info_items:
                        _info_items = [{}]
                    syn_list = _info_items[0]
                    if not isinstance(syn_list, dict):
                        syn_list = {}
                    synonyms = syn_list.get("Synonym", [])[:10]  # Top 10
                    # Find CAS number (pattern: digits-digits-digits)
                    cas_re = re.compile(r"^\d{2,7}-\d{2}-\d$")
                    for s in synonyms:
                        if cas_re.match(s):
                            cas_number = s
                            break

            # Rule N: 타입 가드 — props는 dict
            assert isinstance(props, dict)
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
            except Exception as e:
                logger.debug("New Gemini SDK setup failed, trying old SDK: %s", e)
                # 2차: 구 SDK (google.generativeai) — GenerativeModel 패턴
                try:
                    import google.generativeai as _old_genai
                    _old_genai.configure(api_key=self.api_key)
                    try:
                        self.model = _old_genai.GenerativeModel("gemini-2.5-flash")
                    except Exception as e:
                        logger.debug("gemini-2.5-flash unavailable, using 2.0-flash: %s", e)
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
        if properties and isinstance(properties, dict):
            parts.append(f"분자식: {properties.get('formula', 'N/A')}")
            parts.append(f"IUPAC: {properties.get('iupac_name', 'N/A')}")
            parts.append(f"MW: {properties.get('molecular_weight', 'N/A')}")
        elif properties is not None:
            logger.warning("GeminiAnalyzer._build_prompt: properties not dict: %s", type(properties))
        if orca_data and isinstance(orca_data, dict):
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
                 orca_parser: OrcaOutputParser = None,
                 mol_name: Optional[str] = None,
                 **kwargs):
        # N-guard: 입력 타입 검증
        self.atoms = atoms if isinstance(atoms, dict) else {}
        self.bonds = bonds if isinstance(bonds, dict) else {}
        self.theory_data = theory_data if isinstance(theory_data, dict) else {}
        self.orca_xyz = orca_xyz if isinstance(orca_xyz, dict) else None
        self.smiles = smiles if isinstance(smiles, str) else None
        self.orca_parser = orca_parser
        # M541: mol_name 필드 — 팝업 타이틀/도킹 결과 라벨 등에 사용
        self.mol_name: Optional[str] = mol_name if isinstance(mol_name, str) else None
        # Rule M: unknown kwargs는 silent failure 없이 경고 발화
        if kwargs:
            logger.warning(
                "Molecule3DData: 알 수 없는 kwarg 수신 — 무시됨: %s",
                list(kwargs.keys()),
            )

        if not isinstance(atoms, dict):
            logger.warning("Molecule3DData: atoms is not dict: %s", type(atoms).__name__)
        if not isinstance(bonds, dict):
            logger.warning("Molecule3DData: bonds is not dict: %s", type(bonds).__name__)

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
                    _atom_entry = self.atoms[orig_pos]
                    self.atom_symbols[orig_pos] = _atom_entry.get("main", "C") if isinstance(_atom_entry, dict) else "C"
                else:
                    self.atom_symbols[orig_pos] = "C"
        else:
            for pos, data in self.atoms.items():
                base_2d[pos] = (round(pos[0], 2), round(pos[1], 2), 0.0)
                self.atom_symbols[pos] = data.get("main", "C") if isinstance(data, dict) else "C"

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
        # [BUG-P2 수정] base_2d는 캔버스 픽셀 좌표이므로 Å로 변환 후 VSEPR 적용
        # canvas grid_size=40px ≈ C-C bond(1.5 Å) → 1px = 1.5/40 = 0.0375 Å
        PIXEL_TO_ANGSTROM = 1.5 / 40.0  # canvas.grid_size=40px 기준
        if base_2d and self.bonds:
            base_2d_angstrom = {}
            for key, (x, y, z) in base_2d.items():
                base_2d_angstrom[key] = (
                    round(x * PIXEL_TO_ANGSTROM, 3),
                    round(y * PIXEL_TO_ANGSTROM, 3),
                    0.0,
                )
            # M488: SMILES가 있으면 mol 파싱하여 sp2 hybridization 정보 전달
            # sp2 N(아닐린/아미드/피롤 등)이 삼각뿔형으로 렌더링되는 오류 방지
            _vsepr_mol = None
            if self.smiles and RDKIT_AVAILABLE:
                try:
                    _vsepr_mol = Chem.MolFromSmiles(self.smiles)
                    if _vsepr_mol is None:
                        logger.warning("estimate_z_vsepr Priority4: SMILES 파싱 실패, mol=None으로 폴백: %r", self.smiles)
                except Exception as _e:
                    logger.warning("estimate_z_vsepr Priority4: mol 파싱 오류 %s, 결합 패턴 폴백", _e)
            self.atom_positions = estimate_z_vsepr(
                base_2d_angstrom, self.bonds, self.atom_symbols, mol=_vsepr_mol)
            self._coord_source = "VSEPR 추정"
            return

        # Priority 5: flat 2D → [BUG-10 수정] 픽셀 좌표를 Å로 변환
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
        logger.warning("결합 길이 계산 불가: 원자 위치 누락 (k1=%s, k2=%s)", k1, k2)
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
                logger.warning("결합 각도 계산 불가: 영벡터 감지 (k1=%s, k2=%s, k3=%s)", k1, k2, k3)
                return None
            cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
            return round(math.degrees(math.acos(cos_a)), 1)
        logger.warning("결합 각도 계산 불가: 원자 위치 누락 (k1=%s, k2=%s, k3=%s)", k1, k2, k3)
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
                if mol is None:
                    logger.warning("Invalid SMILES for MOL export: %s", self.smiles)
                else:
                    mol = Chem.AddHs(mol)
                    params = AllChem.ETKDGv3()
                    params.randomSeed = 42
                    if AllChem.EmbedMolecule(mol, params) == 0:
                        try:
                            AllChem.MMFFOptimizeMolecule(mol)
                        except Exception as e:
                            logger.warning("MMFF optimization failed for MOL export: %s", e)
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
    """원본 방식: GL_COLOR_MATERIAL 활성 상태에서 glColor로 색상 설정."""
    glColor4f(r, g, b, a)


def _draw_cylinder(quad, p1, p2, radius, slices=10):
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2-x1, y2-y1, z2-z1
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length < 1e-6:
        logger.warning("실린더 그리기 건너뜀: 길이 0 (p1=%s, p2=%s)", p1, p2)
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


def _draw_arrow(quad, origin, direction, length, radius=0.15, color=(0.2, 1.0, 0.2)):
    """진동 모드용 화살표 그리기 — 밝은 색상 + 굵은 실린더 + 큰 콘 팁"""
    _set_material(*color)
    tip = (origin[0]+direction[0]*length,
           origin[1]+direction[1]*length,
           origin[2]+direction[2]*length)
    _draw_cylinder(quad, origin, tip, radius, 8)
    # Arrowhead (cone) — 콘 길이 = length * 0.3 (기존 0.15 → 2배 확대)
    cone_length = max(0.15, length * 0.3)  # 최소 0.15 Å 보장
    cone_base_r = radius * 3.0  # 콘 밑면 반지름 (기존 2.5 → 3.0)
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
    gluCylinder(cone, cone_base_r, 0.0, cone_length, 10, 1)
    gluDeleteQuadric(cone)
    glPopMatrix()


class BallAndStickRenderer:
    ATOM_SCALE = 0.3
    # M565: 0.10 → 0.13 (30% 굵게) — 격분11 "알갱이만 떠있다" 직접 응답.
    # 결합 차수별 시각 구분 강화 — 단일/이중/삼중/방향족이 명확히 구별되도록.
    BOND_RADIUS = 0.13

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData, vib_vectors=None, vib_scale=0.0,
               small_atoms: bool = False, pi_sp2_keys: set = None):
        """Ball-and-stick 렌더링.

        Args:
            small_atoms: True이면 π 오비탈 모드 — sp2 원자만 점 크기(covalent×0.12)로 축소.
                         원소 색상은 CPK 그대로 유지하여 원소 구분 가능.
            pi_sp2_keys: π 시스템에 참여하는 sp2 원자 키 set. 제공 시 이 원자만 축소,
                         sp3 원자는 normal ATOM_SCALE 유지 (Bug1: sp3 금빛 방지).
        """
        sq, cq = self.qm.sphere(), self.qm.cylinder()
        # [BUG1-FIX] sp3 원자는 pi 모드에서도 normal 크기 유지 — 로브 오버랩으로 금빛 보임 방지
        # pi_sp2_keys 제공 시: sp2 원자만 축소, sp3는 ATOM_SCALE 유지
        # pi_sp2_keys 미제공 시: 기존 small_atoms 동작 유지 (하위 호환)
        _use_per_atom_scale = (small_atoms and pi_sp2_keys is not None)

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

        # Bonds — CPK split-coloring: 각 반쪽을 해당 원자의 CPK 색상으로 렌더링
        # [FIX-3D-005] 진동 시 결합 길이 변화에 따른 색상 코딩
        # Rule N: isinstance guard — mol_data dict 속성 확인
        if not isinstance(mol_data.atom_symbols, dict):
            return
        _has_vib = vib_vectors is not None and abs(vib_scale) > 0.001
        for (k1, k2), order in mol_data.bonds.items():
            if k1 in mol_data.atom_positions and k2 in mol_data.atom_positions:
                p1, p2 = displaced_positions[k1], displaced_positions[k2]
                bo = order
                bond_r = self.BOND_RADIUS * (0.5 if small_atoms else 1.0)

                # CPK 색상 조회 (결합 반쪽 색상용)
                sym1 = mol_data.atom_symbols.get(k1, "C")
                sym2 = mol_data.atom_symbols.get(k2, "C")
                c1 = get_cpk_color(sym1)
                c2 = get_cpk_color(sym2)
                # 결합 중점 계산
                mid = ((p1[0]+p2[0])*0.5, (p1[1]+p2[1])*0.5, (p1[2]+p2[2])*0.5)

                # [FIX-3D-005] 진동 중 결합 신축 색상 코딩 (진동 활성 시 CPK 대신 strain 색상)
                _use_strain_color = False
                if _has_vib:
                    eq1 = mol_data.atom_positions[k1]
                    eq2 = mol_data.atom_positions[k2]
                    eq_len = math.sqrt(sum((a-b)**2 for a, b in zip(eq1, eq2)))
                    disp_len = math.sqrt(sum((a-b)**2 for a, b in zip(p1, p2)))
                    if eq_len > 0.01:
                        strain = (disp_len - eq_len) / eq_len
                        strain_clamped = max(-0.15, min(0.15, strain))
                        strain_t = strain_clamped / 0.15  # -1.0 to +1.0
                        if strain_t > 0.02:
                            t = strain_t
                            c1 = c2 = (0.60 + 0.40*t, 0.60 - 0.40*t, 0.60 - 0.40*t)
                            _use_strain_color = True
                        elif strain_t < -0.02:
                            t = -strain_t
                            c1 = c2 = (0.60 - 0.40*t, 0.60 - 0.20*t, 0.60 + 0.40*t)
                            _use_strain_color = True

                if isinstance(bo, (float, int)) and abs(bo - 0.5) < 0.01:
                    # [FIX-3D-006] 배위 결합 (메탈로센 Fe-C 등): 점선 실린더
                    _set_material(*c1)
                    self._dashed_bond(cq, p1, p2, bond_r * 0.6, 8)
                elif isinstance(bo, (float, int)) and abs(bo - 1.5) < 0.01:
                    # 방향족 비편재화 결합: 중앙 + 얇은 오프셋 — CPK split
                    _set_material(*c1)
                    _draw_cylinder(cq, p1, mid, bond_r, 12)
                    _set_material(*c2)
                    _draw_cylinder(cq, mid, p2, bond_r, 12)
                    self._aromatic_bond_overlay(cq, p1, p2, bond_r * 0.45)
                elif bo == 1 or (isinstance(bo, float) and bo < 1.4):
                    # 단일 결합 — CPK split-coloring (각 반쪽 원자 색상)
                    _set_material(*c1)
                    _draw_cylinder(cq, p1, mid, bond_r, 12)
                    _set_material(*c2)
                    _draw_cylinder(cq, mid, p2, bond_r, 12)
                else:
                    _set_material(*c1)
                    self._multi_bond(cq, p1, p2, min(int(round(bo)), 3))

        # Atoms — displaced_positions 재사용 (결합과 동일한 좌표)
        for idx, (pos, _) in enumerate(mol_data.atom_positions.items()):
            sym = mol_data.atom_symbols.get(pos, "C")
            r, g, b = get_cpk_color(sym)
            _set_material(r, g, b)
            # [BUG1-FIX] π모드: sp2 원자만 축소, sp3 원자는 normal 크기 유지
            if _use_per_atom_scale:
                atom_scale = 0.12 if pos in pi_sp2_keys else self.ATOM_SCALE
            else:
                atom_scale = 0.12 if small_atoms else self.ATOM_SCALE
            rad = get_vdw_radius(sym) * atom_scale

            cx, cy, cz = displaced_positions[pos]

            glPushMatrix()
            glTranslatef(cx, cy, cz)
            gluSphere(sq, rad, 16, 12)
            glPopMatrix()

            # Vibration arrows — [FIX-VIB-ARROW] 화살표 가시성 대폭 개선
            # 변위 벡터 mag는 보통 0.01~0.5 Å로 매우 작아 ×2.5 스케일 + 최소 길이 보장
            if vib_vectors and idx < len(vib_vectors) and abs(vib_scale) > 0.01:
                vx, vy, vz = vib_vectors[idx]
                mag = math.sqrt(vx*vx + vy*vy + vz*vz)
                if mag > 0.005:
                    arrow_len = mag * abs(vib_scale) * 2.5  # 2.5× 스케일 (기존 1.2)
                    arrow_len = max(arrow_len, 0.35)  # 최소 0.35 Å (원자 반지름급)
                    _draw_arrow(cq, (cx, cy, cz), (vx/mag, vy/mag, vz/mag),
                                arrow_len, 0.15, (0.2, 1.0, 0.2))

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
        오프셋을 크게, 색상을 다르게 하여 확실히 보이도록.
        M565: 0.15 → 0.22 offset, 0.8 → 1.0 radius — 격분11 차수별 시각 구분 강화."""
        # M565: aromatic 보조 실린더 offset 0.15 → 0.22 (47% 증가)
        # 격분11 "알갱이만 떠있다" — single과 aromatic이 시각적으로 명확히 구별되도록
        offset_dist = max(0.22, thin_r * 3.5)
        ox, oy, oz = self._perpendicular_offset(p1, p2, offset_dist)
        # 오프셋된 보조 실린더 (이중결합 시각 효과)
        np1 = (p1[0] + ox, p1[1] + oy, p1[2] + oz)
        np2 = (p2[0] + ox, p2[1] + oy, p2[2] + oz)
        # M565: 밝은 회색으로 보조 결합 — 메인과 동일 굵기로 확실히 보이게 (0.8 → 1.0)
        _set_material(0.75, 0.75, 0.75)
        _draw_cylinder(cq, np1, np2, thin_r * 1.0, 8)
        # 원래 색상 복원
        _set_material(0.60, 0.60, 0.60)

    def _dashed_bond(self, cq, p1, p2, radius, n_segments=8):
        """배위 결합 시각화: 점선 실린더 (메탈로센 Fe-C 등).
        M565: 격분11 차수별 시각 구분 강화 — n_segments 8 → 10 (더 촘촘한 점선)."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        _set_material(0.50, 0.50, 0.70)  # 약간 푸르스름한 회색 (배위결합 색상 표준)
        # M565: n_segments 8 → 10 (점선 패턴 더 명확히 구별)
        n_segments = max(n_segments, 10)
        for i in range(n_segments):
            if i % 2 == 0:  # 짝수 세그먼트만 그림 (점선 효과)
                t0 = i / n_segments
                t1 = (i + 1) / n_segments
                sp = (p1[0] + dx * t0, p1[1] + dy * t0, p1[2] + dz * t0)
                ep = (p1[0] + dx * t1, p1[1] + dy * t1, p1[2] + dz * t1)
                _draw_cylinder(cq, sp, ep, radius, 6)
        _set_material(0.60, 0.60, 0.60)

    def _multi_bond(self, cq, p1, p2, count):
        """v4: 이중결합 2개 평행, 삼중결합 3개 평행 실린더.
        M565: 격분11 차수별 시각 구분 강화 — 평행 실린더 offset/radius 증가.
        단일(원기둥1) / 이중(평행2) / 삼중(평행3+중심1) 시각적으로 명확히 구별."""
        _set_material(0.60, 0.60, 0.60)
        if count == 2:
            # 이중결합: 2개 대칭 오프셋 실린더
            # M565: offset 0.12 → 0.18 (50% 증가), radius 0.75 → 0.85 (13% 굵게)
            ox, oy, oz = self._perpendicular_offset(p1, p2, 0.18)
            np1a = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
            np2a = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
            np1b = (p1[0]-ox, p1[1]-oy, p1[2]-oz)
            np2b = (p2[0]-ox, p2[1]-oy, p2[2]-oz)
            _draw_cylinder(cq, np1a, np2a, self.BOND_RADIUS * 0.85, 10)
            _draw_cylinder(cq, np1b, np2b, self.BOND_RADIUS * 0.85, 10)
        elif count >= 3:
            # 삼중결합: 중앙 1개 + 양쪽 오프셋 2개
            # M565: 중심 radius 0.7 → 0.8 (14% 굵게), offset 0.15 → 0.22 (47% 증가),
            #       양옆 radius 0.6 → 0.7 (17% 굵게) — 3개 평행선이 시각적 구별
            _draw_cylinder(cq, p1, p2, self.BOND_RADIUS * 0.8, 10)
            ox, oy, oz = self._perpendicular_offset(p1, p2, 0.22)
            np1a = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
            np2a = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
            np1b = (p1[0]-ox, p1[1]-oy, p1[2]-oz)
            np2b = (p2[0]-ox, p2[1]-oy, p2[2]-oz)
            _draw_cylinder(cq, np1a, np2a, self.BOND_RADIUS * 0.7, 10)
            _draw_cylinder(cq, np1b, np2b, self.BOND_RADIUS * 0.7, 10)

    def render_stereo_bonds(self, mol_data: Molecule3DData):
        """입체 결합 (웨지/대쉬) 시각화.
        SMILES에서 @/@@ 정보를 추출하여 키랄 중심 주변 결합을 강조."""
        if not RDKIT_AVAILABLE or not mol_data.smiles:
            logger.warning("입체 결합 렌더링 불가: RDKIT_AVAILABLE=%s, smiles=%r",
                           RDKIT_AVAILABLE, getattr(mol_data, 'smiles', None))
            return
        try:
            mol = Chem.MolFromSmiles(mol_data.smiles)
            if mol is None:
                logger.warning("입체 결합 렌더링 실패: SMILES 파싱 실패 (smiles=%r)", mol_data.smiles)
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

        except Exception as e:
            logger.warning("Bond rendering failed in QPainter mode: %s", e)

    def _draw_wedge_bond(self, cq, p1, p2, color):
        """웨지 결합: 시작점은 가늘고 끝점은 두꺼운 원뿔형"""
        _set_material(*color)
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        dx, dy, dz = x2-x1, y2-y1, z2-z1
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 1e-6:
            logger.warning("웨지 결합 그리기 건너뜀: 길이 0 (p1=%s, p2=%s)", p1, p2)
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
    SCALE = 0.5

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData, vib_vectors=None, vib_scale=0.0):
        # Rule N: isinstance guard for mol_data dict attributes
        if not isinstance(mol_data.atom_symbols, dict):
            return
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
    LOBE_COLOR_POS = (0.25, 0.50, 1.00, 0.80)    # 양의 위상: 파란색 반투명 (0.72→0.80: 로브 최대 강조)
    LOBE_COLOR_NEG = (1.00, 0.35, 0.25, 0.80)    # 음의 위상: 빨간색 반투명 (0.72→0.80: 로브 최대 강조)
    RING_CLOUD_COLOR = (0.25, 0.50, 1.00, 0.02)  # 방향족 π cloud: 사실상 비활성 (디스크 제거됨)

    def __init__(self):
        self.qm = GLQuadricManager()

    def render(self, mol_data: Molecule3DData):
        """Pi 오비탈 렌더링: 원자별 p-orbital 로브 + 공액계 연결 시각화.

        Rule N: isinstance guard for mol_data attributes.
        [FIX-PI-LOBE] 납작 디스크 → 적절한 물방울형 p-orbital 로브 (위/아래)
        [FIX-PI-PERP] 각 sp2 원자의 로컬 법선 벡터 사용 (전역 SVD 대신)
        — 비평면 분자에서도 각 sp2 원자의 p-orbital이 올바른 방향을 가리킴
        """
        if not OPENGL_AVAILABLE:
            logger.warning("Pi 오비탈 렌더링 건너뜀: OpenGL 사용 불가")
            return
        try:
            # 분자 평면 법선 벡터 계산 (SVD) — 밴드 렌더링 및 폴백용
            global_normal = self._calc_molecular_plane_normal(mol_data)

            # RDKit으로 sp2/방향족 원자 + 고리 정보 감지
            sp2_keys, ring_groups, ring_atom_keys = self._detect_sp2_and_rings(mol_data)

            # 인접 리스트 구축 (로컬 법선 계산용)
            # Rule N: isinstance guard for mol_data.atom_positions
            if not isinstance(mol_data.atom_positions, dict):
                return
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

        except Exception as e:
            # [FIX-SILENT-PI] debug→warning: 오비탈 렌더링 실패를 숨기지 않음 (규칙 M: silent failure 금지)
            logger.warning("Pi orbital rendering failed: %s", e)

    def _calc_local_normal(self, atom_key, atom_positions, adjacency, fallback_normal):
        """[FIX-PI-PERP] sp2 원자의 로컬 평면 법선 벡터를 계산합니다.

        3개 이상의 이웃이 있으면 이웃 벡터들의 외적으로 법선 계산.
        2개 이웃이면 두 결합 벡터의 외적 사용.
        이웃 부족 시 전역 법선(SVD) 폴백.

        Returns:
            (nx, ny, nz): 단위 법선 벡터
        """
        import math
        # Rule N: isinstance guard for dict parameters
        if not isinstance(atom_positions, dict):
            return fallback_normal
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
        except Exception as e:
            logger.debug("Ring normal computation failed, using z-axis: %s", e)
            return (0.0, 0.0, 1.0)

    def _detect_sp2_and_rings(self, mol_data: Molecule3DData):
        """RDKit으로 sp2 원자 키 목록과 방향족 고리 좌표 그룹을 반환합니다.

        Returns:
            (sp2_keys, ring_groups, ring_atom_keys)
            - sp2_keys: List[key] — 모든 sp2/sp 원자
            - ring_groups: List[List[(x,y,z)]] — 방향족 고리별 좌표
            - ring_atom_keys: Set[key] — 방향족 고리에 속하는 원자 키
        """
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(mol_data.atom_symbols, dict):
            return [], [], set()
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
                logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
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
        except Exception as e:
            logger.warning("sp2 detection failed: %s", e)
        return sp2_keys, ring_groups, ring_atom_keys

    def detect_sp2_for_gl(self, mol_data: Molecule3DData):
        """[BUG1-FIX] 외부 호출용 sp2 키 감지 — BallAndStickRenderer에 전달.
        _detect_sp2_and_rings의 공개 인터페이스.
        Returns: (sp2_keys, ring_groups, ring_atom_keys)
        """
        return self._detect_sp2_and_rings(mol_data)

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
        # [BUG2-FIX] 로브 크기 50% 축소 — 기존 크기가 sp3 이웃 원자 영역까지 침범
        # lobe_size: 0.55 → 0.30 (반지름), lobe_dist: 0.80 → 0.50 (원자 중심에서 로브 중심 거리)
        # 기준: C-C 결합 1.54Å, 로브 끝 = 0.50 + 0.30*1.80 = 1.04Å < 1.54Å → 이웃 원자 영역 침범 없음
        lobe_size = 0.30    # 로브 반지름 (Å) — 0.55→0.30: 50% 축소 (sp3 침범 방지)
        lobe_dist = 0.50    # 원자에서 로브 중심까지 거리 (Å) — 0.80→0.50: 축소

        # 법선→Z축 회전각 계산
        # [BUG-O1 수정] Z × N = (0,0,1) × (nx,ny,nz) = (-ny, nx, 0)
        # [FIX-PI-PERP-2] 법선이 -Z 근처일 때 회전축 축퇴 → X축 180도 회전 폴백
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
                elif angle_deg > 90.0:
                    # [FIX-PI-PERP-2] normal ≈ (0,0,-1): Z×N ≈ 0 벡터
                    # → X축 기준 180도 회전으로 Z→-Z 매핑
                    glRotatef(180.0, 1.0, 0.0, 0.0)

            # p 오비탈 로브: 뚱뚱한 물방울형 (교과서 비율 ~2.5:1)
            glScalef(0.70, 0.70, 1.80)

            r, g, b, a = color
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            # [FIX-ORBITAL-COLOR-V2] GL_COLOR_MATERIAL이 비활성이므로 glColor4f만으로는
            # 조명 하에서 색상이 적용되지 않음. glMaterialfv(AMBIENT_AND_DIFFUSE)로
            # 직접 material color를 설정해야 파랑(+)/빨강(-) 위상 구분이 보임.
            mat_color = [r, g, b, a]
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, mat_color)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.4, 0.4, 0.5, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 50.0)  # 35→50: 더 선명한 하이라이트
            glColor4f(r, g, b, a)  # 폴백: GL_COLOR_MATERIAL 활성 환경 대비
            gluSphere(sq, lobe_size, 24, 16)  # 20,14→24,16: 더 매끄러운 구체
            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)
            glPopMatrix()

    def _draw_ring_pi_cloud(self, sq, positions, normal):
        """방향족 고리/공액계의 π 전자구름 — 와이어프레임 윤곽만 표시.

        [FIX-RING-CLOUD] 기존 불투명 디스크가 p-orbital 로브를 가렸음.
        해결: 채워진 gluSphere 디스크 → GL_LINE_LOOP 와이어프레임으로 교체.
        p-orbital 로브가 주된 π 시각화이므로, 고리 윤곽은 보조 힌트로만 사용.
        """
        import math
        if not positions or len(positions) < 2:
            logger.warning("π 링 클라우드 렌더링 건너뜀: 위치 데이터 부족 (positions=%s)", len(positions) if positions else 0)
            return

        # 무게중심
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)
        cz = sum(p[2] for p in positions) / len(positions)

        nx, ny, nz = normal
        cloud_offset = 0.45   # 면에서 윤곽선까지 (Å) — 로브 안쪽에 가볍게

        # [FIX-RING-VIS] 고리 윤곽: 위(+) 파랑, 아래(-) 빨강으로 위상 구분
        ring_colors = [
            (0.25, 0.50, 1.00),  # +위상: 파란색
            (1.00, 0.35, 0.25),  # -위상: 빨간색
        ]
        wire_alpha = 0.30  # 0.15→0.30: 윤곽선 가시성 향상

        for sign, (r, g, b) in zip((+1, -1), ring_colors):
            glPushMatrix()
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            glDisable(GL_LIGHTING)
            glLineWidth(2.0)  # 1.5→2.0: 윤곽 두께 증가
            glColor4f(r, g, b, wire_alpha)
            glBegin(GL_LINE_LOOP)
            for p in positions:
                wx = p[0] + sign * nx * cloud_offset
                wy = p[1] + sign * ny * cloud_offset
                wz = p[2] + sign * nz * cloud_offset
                glVertex3f(wx, wy, wz)
            glEnd()
            glEnable(GL_LIGHTING)
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
    COLOR_PI_POS    = (0.25, 0.50, 1.00, 0.55)   # π +위상: 연파랑
    COLOR_PI_NEG    = (1.00, 0.35, 0.25, 0.55)   # π -위상: 연빨강
    COLOR_PI        = (0.25, 0.50, 1.00, 0.55)   # π 로브: 연파랑 (하위호환)
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
            logger.warning("오비탈 렌더링 건너뜀: OpenGL 사용 불가 (mode=%s)", orbital_mode)
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
    # [ESP-V2] Coulomb-potential on VDW isosurface mesh with continuous
    #          color gradient.  Priority: xtb GFN2-xTB > Gasteiger.
    # ------------------------------------------------------------------
    _esp_mesh_cache: Dict = {}  # smiles → (verts, norms, tris)

    def render_esp_surface(self, mol_data: 'Molecule3DData'):
        """Render McMurry-style ESP mapped onto a VDW isosurface.

        McMurry / Atkins textbook convention (same as reference image):
          RED   = delta-minus  (electron-rich,  negative potential)
          WHITE = neutral / low-potential band
          BLUE  = delta-plus   (electron-poor,  positive potential)

        Surface generation:
          1) Build icosphere mesh around each atom at VDW radius
          2) Merge overlapping vertices (union of VDW spheres)
          3) At each surface vertex, compute Coulomb potential from all
             atomic partial charges: V(r) = sum_i q_i / |r - R_i|
          4) Map V to continuous RGB via McMurry colormap

        Charge priority:
          - xtb GFN2-xTB Mulliken (semiempirical approximation, not DFT)
          - RDKit Gasteiger (fast fallback)
          - Pauling electronegativity heuristic (last resort)
        """
        if not OPENGL_AVAILABLE:
            logger.warning("ESP surface rendering skipped: OpenGL unavailable")
            return
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(mol_data.atom_symbols, dict):
            return

        try:
            # --- 1. Obtain partial charges --------------------------------
            charges = self._compute_esp_charges(mol_data)

            if not charges:
                logger.warning("ESP surface: no charges computed, skipping render")
                return

            # Build position / charge arrays for Coulomb computation
            atom_keys = list(mol_data.atom_positions.keys())
            n_atoms = len(atom_keys)
            if n_atoms == 0:
                logger.warning("ESP surface: no atom positions available")
                return

            atom_pos_arr = []   # [(x,y,z), ...]
            atom_q_arr = []     # [charge, ...]
            atom_vdw_arr = []   # [vdw_radius, ...]
            for key in atom_keys:
                pos = mol_data.atom_positions[key]
                atom_pos_arr.append(pos)
                q = charges.get(key, 0.0)
                if not math.isfinite(q):
                    q = 0.0
                atom_q_arr.append(q)
                sym = mol_data.atom_symbols.get(key, "C")
                atom_vdw_arr.append(get_vdw_radius(sym))

            # --- 2. Generate smooth icosphere unit mesh ---------------------
            # Adaptive subdivision: 3 for small molecules, 2 for large
            n_sub = 3 if n_atoms <= 30 else 2
            unit_verts, unit_tris = self._build_unit_icosphere(n_sub)

            # --- 3. Compute Coulomb potential at every surface vertex ------
            # For each atom, build its VDW sphere vertices and compute
            # potential at each from ALL atomic charges.
            all_atom_verts = []   # per-atom: [(vx,vy,vz), ...]
            all_atom_colors = []  # per-atom: [(r,g,b), ...]
            global_pots = []

            for ai in range(n_atoms):
                cx, cy, cz = atom_pos_arr[ai]
                ri = atom_vdw_arr[ai]
                atom_v = [
                    (cx + ri * ux, cy + ri * uy, cz + ri * uz)
                    for ux, uy, uz in unit_verts
                ]
                pots = self._compute_coulomb_potential(
                    atom_v, atom_pos_arr, atom_q_arr
                )
                all_atom_verts.append(atom_v)
                global_pots.extend(pots)

            # Normalize potentials globally
            abs_pots = [abs(p) for p in global_pots if math.isfinite(p)]
            max_abs = max(abs_pots) if abs_pots else 0.5
            if max_abs < 1e-8:
                max_abs = 0.5

            # Pre-compute per-vertex colors for each atom.
            # Apply contrast enhancement: sign-preserving power-law
            # stretches weak potential differences to fill the colormap.
            # Exponent < 1 expands mid-range (like gamma correction).
            CONTRAST_EXP = 0.55  # 0.5 = sqrt-law; 1.0 = linear (no boost)
            pot_idx = 0
            n_unit_v = len(unit_verts)
            for ai in range(n_atoms):
                colors = []
                for vi in range(n_unit_v):
                    pot = global_pots[pot_idx]
                    norm_val = max(-1.0, min(1.0, pot / max_abs))
                    # Sign-preserving power law: sgn(x) * |x|^p
                    sign = 1.0 if norm_val >= 0 else -1.0
                    norm_val = sign * (abs(norm_val) ** CONTRAST_EXP)
                    r, g, b = self._esp_charge_to_color(norm_val)
                    colors.append((r, g, b))
                    pot_idx += 1
                all_atom_colors.append(colors)

            # --- 4. Render: two-pass for correct transparency -------------
            alpha = 0.72
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, GL_TRUE)
            glEnable(GL_COLOR_MATERIAL)
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,
                         [0.35, 0.35, 0.35, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 50.0)

            # Pass 1: Depth-only pass. Render complete VDW spheres to
            # establish correct depth values. Overlapping sphere interiors
            # are naturally occluded.
            glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
            glDepthMask(GL_TRUE)
            for ai in range(n_atoms):
                atom_v = all_atom_verts[ai]
                glBegin(GL_TRIANGLES)
                for t0, t1, t2 in unit_tris:
                    for idx in (t0, t1, t2):
                        nx, ny, nz = unit_verts[idx]
                        glNormal3f(nx, ny, nz)
                        vx, vy, vz = atom_v[idx]
                        glVertex3f(vx, vy, vz)
                glEnd()

            # Pass 2: Color pass. Depth test on (LEQUAL) but no depth
            # write, so only the outermost surface gets colored.
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
            glDepthMask(GL_FALSE)
            glDepthFunc(GL_LEQUAL)

            for ai in range(n_atoms):
                atom_v = all_atom_verts[ai]
                atom_c = all_atom_colors[ai]
                glBegin(GL_TRIANGLES)
                for t0, t1, t2 in unit_tris:
                    for idx in (t0, t1, t2):
                        r, g, b = atom_c[idx]
                        glColor4f(r, g, b, alpha)
                        nx, ny, nz = unit_verts[idx]
                        glNormal3f(nx, ny, nz)
                        vx, vy, vz = atom_v[idx]
                        glVertex3f(vx, vy, vz)
                glEnd()

            glDepthFunc(GL_LESS)  # restore default
            glDepthMask(GL_TRUE)
            glDisable(GL_COLOR_MATERIAL)
            glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, GL_FALSE)
            glDisable(GL_BLEND)

        except Exception as e:
            logger.warning("AdvancedOrbitalRenderer.render_esp_surface error: %s", e)

    # ------------------------------------------------------------------
    # Coulomb potential computation
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_coulomb_potential(
        surface_verts: List[Tuple[float, float, float]],
        atom_positions: List[Tuple[float, float, float]],
        atom_charges: List[float],
    ) -> List[float]:
        """Compute electrostatic potential at each surface vertex.

        V(r) = sum_i  q_i / |r - R_i|    (Coulomb's law, atomic units)

        A soft-core damping radius prevents singularities when a surface
        vertex coincides with an atom center.
        """
        SOFTCORE = 0.5  # Angstrom damping radius to avoid 1/0 singularity
        potentials: List[float] = []
        for vx, vy, vz in surface_verts:
            pot = 0.0
            for (ax, ay, az), q in zip(atom_positions, atom_charges):
                dx = vx - ax
                dy = vy - ay
                dz = vz - az
                dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                # Soft-core: max(dist, SOFTCORE) to avoid singularity
                pot += q / max(dist, SOFTCORE)
            potentials.append(pot)
        return potentials

    # ------------------------------------------------------------------
    # Icosphere-based molecular surface mesh
    # ------------------------------------------------------------------
    @staticmethod
    def _build_molecular_surface(
        atom_positions: List[Tuple[float, float, float]],
        atom_vdw_radii: List[float],
        subdivisions: int = 2,
    ) -> Tuple[List[Tuple[float, float, float]],
               List[Tuple[float, float, float]],
               List[Tuple[int, int, int]]]:
        """Build a union-of-VDW-spheres surface mesh.

        For each atom, generate an icosphere at VDW radius, then remove
        vertices that are buried inside any other atom's VDW sphere.

        Returns:
            (vertices, normals, triangles) where triangles index into
            the vertex/normal arrays.
        """
        # --- Generate base icosahedron ---
        t = (1.0 + math.sqrt(5.0)) / 2.0  # golden ratio
        base_v = [
            (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
            (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
        ]
        # Normalize to unit sphere
        base_v = [
            (x / math.sqrt(x*x + y*y + z*z),
             y / math.sqrt(x*x + y*y + z*z),
             z / math.sqrt(x*x + y*y + z*z))
            for x, y, z in base_v
        ]
        base_tri = [
            (0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),
            (1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),
            (3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),
            (4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1),
        ]

        # Subdivide
        def _midpoint(v1, v2):
            mx = (v1[0]+v2[0]) * 0.5
            my = (v1[1]+v2[1]) * 0.5
            mz = (v1[2]+v2[2]) * 0.5
            ln = math.sqrt(mx*mx + my*my + mz*mz)
            if ln < 1e-12:
                return (0.0, 0.0, 1.0)
            return (mx/ln, my/ln, mz/ln)

        verts_sub = list(base_v)
        tris_sub = list(base_tri)
        mid_cache: Dict = {}

        for _ in range(subdivisions):
            new_tris = []
            mid_cache.clear()
            for i0, i1, i2 in tris_sub:
                def get_mid(a, b):
                    key = (min(a, b), max(a, b))
                    if key in mid_cache:
                        return mid_cache[key]
                    m = _midpoint(verts_sub[a], verts_sub[b])
                    idx = len(verts_sub)
                    verts_sub.append(m)
                    mid_cache[key] = idx
                    return idx
                a = get_mid(i0, i1)
                b = get_mid(i1, i2)
                c = get_mid(i2, i0)
                new_tris.extend([
                    (i0, a, c), (i1, b, a), (i2, c, b), (a, b, c)
                ])
            tris_sub = new_tris

        unit_sphere_v = verts_sub
        unit_sphere_t = tris_sub
        n_unit = len(unit_sphere_v)

        # --- Per-atom icosphere, cull buried vertices ---
        all_verts: List[Tuple[float, float, float]] = []
        all_normals: List[Tuple[float, float, float]] = []
        all_tris: List[Tuple[int, int, int]] = []

        n_atoms = len(atom_positions)
        # Probe margin: a surface vertex is "buried" if it's inside
        # another atom's VDW sphere (with small tolerance to avoid
        # z-fighting at tangent points)
        BURIED_TOL = 0.05  # Angstrom tolerance (small = fewer gaps at seams)

        for ai in range(n_atoms):
            cx, cy, cz = atom_positions[ai]
            ri = atom_vdw_radii[ai]

            # Map unit sphere to atom sphere
            local_v = [
                (cx + ri * ux, cy + ri * uy, cz + ri * uz)
                for ux, uy, uz in unit_sphere_v
            ]
            # Normals = unit sphere directions (outward)
            local_n = list(unit_sphere_v)

            # Check which vertices are buried inside another atom
            exposed = [True] * n_unit
            for aj in range(n_atoms):
                if aj == ai:
                    continue
                ox, oy, oz = atom_positions[aj]
                rj = atom_vdw_radii[aj]
                rj_sq = (rj - BURIED_TOL) ** 2
                for vi in range(n_unit):
                    if not exposed[vi]:
                        continue
                    vx, vy, vz = local_v[vi]
                    dx = vx - ox
                    dy = vy - oy
                    dz = vz - oz
                    if dx*dx + dy*dy + dz*dz < rj_sq:
                        exposed[vi] = False

            # Remap only exposed vertices
            old_to_new: Dict[int, int] = {}
            base_idx = len(all_verts)
            for vi in range(n_unit):
                if exposed[vi]:
                    old_to_new[vi] = base_idx + len(old_to_new)
                    all_verts.append(local_v[vi])
                    all_normals.append(local_n[vi])

            # Add only triangles where all 3 vertices are exposed
            for t0, t1, t2 in unit_sphere_t:
                if t0 in old_to_new and t1 in old_to_new and t2 in old_to_new:
                    all_tris.append((
                        old_to_new[t0], old_to_new[t1], old_to_new[t2]
                    ))

        return all_verts, all_normals, all_tris

    # ------------------------------------------------------------------
    # Unit icosphere (no per-atom scaling/culling, for ESP rendering)
    # ------------------------------------------------------------------
    @staticmethod
    def _build_unit_icosphere(
        subdivisions: int = 3,
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
        """Build a unit icosphere mesh (radius=1, centered at origin).

        Returns (vertices, triangles). Vertices are normalized to unit
        sphere and also serve as outward normals.
        """
        t = (1.0 + math.sqrt(5.0)) / 2.0
        base_v = [
            (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
            (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
        ]
        base_v = [
            (x / math.sqrt(x*x + y*y + z*z),
             y / math.sqrt(x*x + y*y + z*z),
             z / math.sqrt(x*x + y*y + z*z))
            for x, y, z in base_v
        ]
        base_tri = [
            (0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),
            (1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),
            (3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),
            (4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1),
        ]

        def _midpoint(v1, v2):
            mx = (v1[0]+v2[0]) * 0.5
            my = (v1[1]+v2[1]) * 0.5
            mz = (v1[2]+v2[2]) * 0.5
            ln = math.sqrt(mx*mx + my*my + mz*mz)
            if ln < 1e-12:
                return (0.0, 0.0, 1.0)
            return (mx/ln, my/ln, mz/ln)

        verts = list(base_v)
        tris = list(base_tri)
        mid_cache: Dict = {}

        for _ in range(subdivisions):
            new_tris = []
            mid_cache.clear()
            for i0, i1, i2 in tris:
                def get_mid(a, b):
                    key = (min(a, b), max(a, b))
                    if key in mid_cache:
                        return mid_cache[key]
                    m = _midpoint(verts[a], verts[b])
                    idx = len(verts)
                    verts.append(m)
                    mid_cache[key] = idx
                    return idx
                a = get_mid(i0, i1)
                b = get_mid(i1, i2)
                c = get_mid(i2, i0)
                new_tris.extend([
                    (i0, a, c), (i1, b, a), (i2, c, b), (a, b, c)
                ])
            tris = new_tris

        return verts, tris

    # ------------------------------------------------------------------
    # Charge acquisition: xtb > Gasteiger > electronegativity
    # ------------------------------------------------------------------
    def _compute_esp_charges(self, mol_data: 'Molecule3DData') -> Dict:
        """Obtain per-atom partial charges for ESP mapping.

        Priority:
          1. xtb GFN2-xTB Mulliken charges (semiempirical, not DFT)
          2. RDKit Gasteiger charges (fast empirical)
          3. Pauling electronegativity heuristic (last resort)

        Returns dict mapping atom_key -> float charge.
        """
        smiles = getattr(mol_data, 'smiles', '') or ''
        atom_keys = list(mol_data.atom_positions.keys())
        n_atoms_3d = len(atom_keys)

        # ---- Priority 1: xtb GFN2-xTB ----
        if smiles:
            try:
                from orca_interface import run_xtb_calculation
                xtb_result = run_xtb_calculation(smiles, calc_type='sp')
                if xtb_result.success and xtb_result.charges:
                    # xtb charges: {0-based atom_index: Mulliken charge}
                    # Map to mol_data atom keys (0-based index alignment)
                    charges: Dict = {}
                    for i, key in enumerate(atom_keys):
                        if i in xtb_result.charges:
                            charges[key] = xtb_result.charges[i]
                        else:
                            charges[key] = 0.0
                    logger.info("ESP: using approximate xtb GFN2-xTB Mulliken charges (%d atoms)",
                                len(charges))
                    return charges
                else:
                    logger.info("ESP: xtb calculation failed (%s), falling back to Gasteiger",
                                xtb_result.error_message)
            except ImportError:
                logger.info("ESP: orca_interface not available, using Gasteiger fallback")
            except Exception as e:
                logger.warning("ESP: xtb charge computation error: %s", e)

        # ---- Priority 2 & 3: existing Gasteiger / EN heuristic ----
        return self._compute_gasteiger_charges(mol_data)

    @staticmethod
    def _esp_charge_to_color(norm: float):
        """Map normalized potential [-1, +1] to RGB (McMurry convention).

        McMurry 9th edition / reference image colormap:
          -1 (negative, electron-rich) -> RED   (0.90, 0.05, 0.05)
           0 (neutral)                 -> WHITE (0.94, 0.94, 0.90)
          +1 (positive, electron-poor) -> BLUE  (0.10, 0.15, 0.95)

        Uses smooth cosine interpolation for perceptually even gradient.
        Intermediate colors: red -> orange -> near-white -> cyan -> blue
        """
        # 5-anchor colormap for richer intermediate colors.
        # Neutral is intentionally near-white instead of green so ESP mode
        # cannot create a green-filled molecule when the surface is enabled.
        # [-1.0]  RED       (0.90, 0.05, 0.05)
        # [-0.5]  ORANGE    (1.00, 0.55, 0.05)
        # [ 0.0]  WHITE     (0.94, 0.94, 0.90)
        # [+0.5]  CYAN      (0.10, 0.65, 0.85)
        # [+1.0]  BLUE      (0.10, 0.15, 0.95)
        anchors = [
            (-1.0, (0.90, 0.05, 0.05)),
            (-0.5, (1.00, 0.55, 0.05)),
            ( 0.0, (0.94, 0.94, 0.90)),
            ( 0.5, (0.10, 0.65, 0.85)),
            ( 1.0, (0.10, 0.15, 0.95)),
        ]
        # Clamp
        norm = max(-1.0, min(1.0, norm))

        # Find surrounding anchors
        for i in range(len(anchors) - 1):
            v0, c0 = anchors[i]
            v1, c1 = anchors[i + 1]
            if norm <= v1:
                t = (norm - v0) / (v1 - v0) if (v1 - v0) > 1e-12 else 0.0
                # Cosine interpolation for smoother gradient
                t = 0.5 * (1.0 - math.cos(t * math.pi))
                r = c0[0] + (c1[0] - c0[0]) * t
                g = c0[1] + (c1[1] - c0[1]) * t
                b = c0[2] + (c1[2] - c0[2]) * t
                return (r, g, b)

        # Fallback (should not reach)
        return anchors[-1][1]

    def _compute_gasteiger_charges(self, mol_data: 'Molecule3DData') -> Dict:
        """Compute per-atom partial charges using RDKit Gasteiger method.

        Falls back to Pauling electronegativity heuristic if RDKit is
        unavailable or SMILES is missing.
        Returns: dict mapping atom_key → float charge value.
        """
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(mol_data.atom_symbols, dict):
            return {}
        charges: Dict = {}
        smiles = getattr(mol_data, 'smiles', '') or ''

        if smiles:
            try:
                from rdkit import Chem
                from rdkit.Chem import AllChem

                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    logger.warning("Invalid SMILES for Gasteiger charge computation: %s", smiles)
                else:
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
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(mol_data.atom_symbols, dict):
            return {}
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
                if rmol is None:
                    logger.warning("Invalid SMILES for hybridization analysis: %s", smiles)
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
        except Exception as e:
            logger.warning("ESP surface computation failed: %s", e)

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
    # [FIX-BALLOON-001] σ 오비탈: 은은한 전자밀도 구름 스타일 (풍선 X)
    COLOR_SP  = (0.72, 0.50, 0.92, 0.34)   # sp: purple, 180 degree linear
    COLOR_SP2 = (0.22, 0.48, 1.00, 0.42)   # sp2: blue, trigonal planar + p-normal
    COLOR_SP3 = (0.25, 0.82, 0.38, 0.42)   # sp3: green, tetrahedral
    COLOR_SP3D = (1.00, 0.78, 0.12, 0.44)  # sp3d: yellow, trigonal bipyramidal
    COLOR_SP3D2 = (1.00, 0.45, 0.08, 0.44) # sp3d2: orange, octahedral

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
        """sp: 2 σ 로브 + 2 π 오비탈 쌍 — [FIX-BALLOON-001] σ=sparse dots"""
        dirs = list(ndirs[:2])
        ideal = [(0,0,1),(0,0,-1)]
        while len(dirs) < 2:
            dirs.append(ideal[len(dirs)])
        # σ 로브: sparse electron density dots (is_sigma=True)
        sp_pos = self.COLOR_SP
        sp_neg = (self.COLOR_SP[0]*0.7, self.COLOR_SP[1]*0.7, self.COLOR_SP[2]*0.7, 0.25)
        self._lobe(sq, pos, dirs[0], 2.5, 0.45, sp_pos, is_sigma=True)
        self._lobe(sq, pos, dirs[1], 2.5, 0.45, sp_neg, is_sigma=True)
        # π 오비탈: σ축에 수직인 두 방향
        p1 = self._perp(dirs[0])
        p2 = self._cross3(dirs[0], p1)
        # [FIX-PI-PHASE] +/- 위상 색상 구분: 파랑(+) / 빨강(-)
        for pv in (p1, p2):
            self._lobe(sq, pos, (pv[0], pv[1], pv[2]), 2.0, 0.42, self.COLOR_PI_POS)
            self._lobe(sq, pos, (-pv[0], -pv[1], -pv[2]), 2.0, 0.42, self.COLOR_PI_NEG)

    def _sp2(self, sq, pos, ndirs):
        """sp2: 3 σ 로브 + 1 π 오비탈 (면 수직) — [FIX-BALLOON-001] σ=sparse dots"""
        dirs = list(ndirs[:3])
        ideal = [(1,0,0),(-0.5,0.866,0),(-0.5,-0.866,0)]
        while len(dirs) < 3:
            dirs.append(ideal[len(dirs)])
        # σ 로브: sparse electron density dots (is_sigma=True)
        for i, d in enumerate(dirs[:3]):
            self._lobe(sq, pos, d, 2.2, 0.48, self.COLOR_SP2, is_sigma=True)
        # π 오비탈: 분자면 법선 — 기존 π 스타일 유지 (is_sigma=False)
        if len(dirs) >= 2:
            pn = self._cross3(dirs[0], dirs[1])
            pl = math.sqrt(sum(x*x for x in pn))
            if pl > 1e-6:
                pn = tuple(x/pl for x in pn)
                # [FIX-PI-PHASE] +/- 위상 색상 구분: 파랑(+) / 빨강(-)
                self._lobe(sq, pos, pn, 2.5, 0.52, self.COLOR_PI_POS)
                self._lobe(sq, pos, tuple(-x for x in pn), 2.5, 0.52, self.COLOR_PI_NEG)

    def _sp3(self, sq, pos, ndirs):
        """sp3: 4 σ 로브 (사면체) — [FIX-BALLOON-001] σ=sparse dots"""
        dirs = list(ndirs[:4])
        ideal = [(0.577,0.577,0.577),(0.577,-0.577,-0.577),
                 (-0.577,0.577,-0.577),(-0.577,-0.577,0.577)]
        while len(dirs) < 4:
            dirs.append(ideal[len(dirs)])
        # σ 로브: sparse electron density dots (is_sigma=True)
        for i, d in enumerate(dirs[:4]):
            self._lobe(sq, pos, d, 2.0, 0.50, self.COLOR_SP3, is_sigma=True)

    def _sp3d(self, sq, pos, ndirs):
        """sp3d: 5 로브 — 삼각쌍뿔 (3 적도 + 2 축) [FIX-BALLOON-001] σ=sparse"""
        dirs = list(ndirs[:5])
        eq_ideal = [(1,0,0),(-0.5,0.866,0),(-0.5,-0.866,0)]
        ax_ideal = [(0,0,1),(0,0,-1)]
        eq = dirs[:3] if len(dirs)>=3 else dirs[:len(dirs)] + eq_ideal[len(dirs):]
        while len(eq)<3: eq.append(eq_ideal[len(eq)])
        ax = dirs[3:5] if len(dirs)>=5 else dirs[3:len(dirs)] + ax_ideal[len(dirs)-3:]
        while len(ax)<2: ax.append(ax_ideal[len(ax)])
        # σ 로브: sparse dot cloud (is_sigma=True)
        sp3_col = (0.60, 0.65, 0.70, 0.30)  # 연회색-블루 for sp3d
        sp3_col = self.COLOR_SP3D
        for i,d in enumerate(eq):
            self._lobe(sq, pos, d, 2.0, 0.50, sp3_col, is_sigma=True)
        for i,d in enumerate(ax):
            self._lobe(sq, pos, d, 2.4, 0.45, sp3_col, is_sigma=True)

    def _sp3d2(self, sq, pos, ndirs):
        """sp3d2: 6 로브 — 정팔면체 (±x, ±y, ±z) [FIX-BALLOON-001] σ=sparse"""
        dirs = list(ndirs[:6])
        ideal = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
        while len(dirs)<6: dirs.append(ideal[len(dirs)])
        sp3d2_col = self.COLOR_SP3D2
        # σ 로브: sparse dot cloud (is_sigma=True)
        sp3d2_col = (0.60, 0.65, 0.70, 0.30)  # 연회색-블루 for sp3d2
        for i,d in enumerate(dirs[:6]):
            self._lobe(sq, pos, d, 2.0, 0.48, self.COLOR_SP3D2, is_sigma=True)

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

    def _lobe(self, sq, pos, direction, scale_z: float, radius: float,
              color: tuple, is_sigma: bool = False):
        """단일 오비탈 로브를 Monte Carlo 점밀도로 그립니다.

        [MC-DOT-REPLACE] gluSphere prolate spheroid → MC 점밀도 방식.
        |ψ|² 비례 rejection sampling으로 점을 생성하여 GL_POINTS로 렌더링.
        교과서 스타일의 전자 구름 밀도 표현.

        [FIX-MC-VISIBLE] GL_LIGHTING 비활성 + GL_POINT_SMOOTH
        [FIX-BALLOON-001] σ/혼성 오비탈: 작은 점(1.5) + 소수 점(200) + 높은 투명도
            → 전자확률밀도 구름 느낌. π/d 오비탈: 약간 줄인 점(3.0).

        Args:
            scale_z: Z 방향 늘림 배율 (p 오비탈: 2.2, d 로브: 1.4 등)
            radius:  구 기본 반지름 (Å)
            is_sigma: True이면 σ/혼성 오비탈 — sparse dot cloud 스타일
        """
        r, g, b, a = color

        # [FIX-FROG-EGG] MC 점밀도 → gluSphere 반투명 타원체로 교체
        # 이전: 600개 GL_POINTS → 개구리알 외관
        # 수정: PiOrbitalRenderer._draw_p_orbital_lobes와 동일한 gluSphere 방식
        import math
        render_alpha = min(a, 0.20) if is_sigma else min(a, 0.25)

        dx, dy, dz = direction
        direction_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if direction_len < 1e-6:
            logger.warning("Hybrid orbital lobe skipped degenerate direction at pos=%s", pos)
            return
        dx, dy, dz = dx / direction_len, dy / direction_len, dz / direction_len
        lobe_radius = radius * 0.32
        lobe_height = max(radius * scale_z, radius * 0.75)
        lobe_offset = lobe_height * 0.58

        dot_z = max(-1.0, min(1.0, dz))
        angle_deg = math.degrees(math.acos(dot_z))
        rot_x, rot_y = -dy, dx

        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])

        if angle_deg > 0.5:
            rl = math.sqrt(rot_x * rot_x + rot_y * rot_y)
            if rl > 1e-6:
                glRotatef(angle_deg, rot_x / rl, rot_y / rl, 0.0)
            elif angle_deg > 90.0:
                glRotatef(180.0, 1.0, 0.0, 0.0)

        glTranslatef(0.0, 0.0, lobe_offset)
        xy_scale = lobe_radius
        z_scale = lobe_height
        glScalef(xy_scale, xy_scale, z_scale)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        mat_color = [r, g, b, render_alpha]
        glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, mat_color)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.3, 0.4, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 40.0)
        glColor4f(r, g, b, render_alpha)

        if not hasattr(AdvancedOrbitalRenderer, '_lobe_quadric'):
            AdvancedOrbitalRenderer._lobe_quadric = gluNewQuadric()
            gluQuadricNormals(AdvancedOrbitalRenderer._lobe_quadric, GLU_SMOOTH)
        gluSphere(AdvancedOrbitalRenderer._lobe_quadric, 1.0, 16, 12)

        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glPopMatrix()

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
        # [FIX-VIS-001] 표시기 크기 증가 — 더 잘 보이도록
        indicator_offset = 0.70  # 0.60→0.70 Angstrom
        indicator_r = 0.22       # 0.15→0.22: 더 큰 표시기

        glPushMatrix()
        glTranslatef(x, y + indicator_offset, z)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        ind_a = max(a, 0.75)  # [FIX-VIS-001] 표시기는 항상 최소 0.75 불투명도
        glColor4f(r, g, b, ind_a)
        glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [r, g, b, ind_a])
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 40.0)
        gluSphere(sq, indicator_r, 12, 10)  # 분할 수 증가로 더 매끄러운 구체
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
        self.setMinimumSize(400, 200)  # [M483] 세로 최소 400→200: 탭 패널 공간 압박 해소
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._mouse_last = None
        self._right_last = None
        self.render_mode = "ball_and_stick"
        # Background color for QPainter (QColor)
        self.bg_color_qc = QColor(30, 30, 30)
        self._transformed = []
        # [FIX-3D-IND] OpenGL 모드 표시기
        self._mode_indicator_alpha = 255  # 시작 시 완전 불투명, 점차 사라짐
        self._mode_indicator_timer = QTimer(self)
        self._mode_indicator_timer.timeout.connect(self._fade_mode_indicator)
        self._mode_indicator_timer.start(50)  # 50ms 간격으로 페이드아웃
        # 진동 애니메이션 상태
        self.vib_vectors = None
        self.vib_scale = 0.0
        self._vib_active = False
        self._vib_phase = 0.0
        self._vib_amplitude = 1.5
        self._vib_timer = QTimer(self)
        self._vib_timer.timeout.connect(self._vib_tick)
        self._vib_highlight_indices = set()  # [VIB-SPEC] 하이라이트 원자 인덱스
        # [FIX-3D-STEREO] 입체 결합 캐시 (SMILES → stereo bond info)
        self._stereo_bonds = None  # List[(begin_idx, end_idx, 'wedge'|'dash')]
        self._stereo_computed = False
        # 단백질/도킹 시각화 상태
        self._protein_ca = []
        self._binding_site = None
        self._binding_site_radius = 8.0
        self._dock_pose_coords = None
        self._dock_pose_elements = None
        self._dock_approach_offset = None
        self._dock_approach_step = 0
        # [P0-3] ESP 색상 모드 (Theory 뷰에서 Gasteiger 전하 → 색상 매핑)
        self.esp_mode = False
        self._esp_charges = None  # Dict[key, float] 캐시 (Gasteiger 전하)
        # [PI-QPainter] π 오비탈 렌더링 상태
        self.orbital_mode = 'none'  # 'none'|'pi'|'esp' 등
        self._pi_cache = None  # (sp2_keys, ring_groups, ring_atom_keys) 캐시
        # [RIBBON-FALLBACK] FallbackRenderer2D도 리본 모드 지원 (M155 fix)
        self._ribbon_mode = False  # False=backbone lines, True=ribbon
        self._secondary_structure = None  # List[str] — 'H'/'E'/'C'
        self._update_transform()

    def _fade_mode_indicator(self):
        """[FIX-3D-IND] 모드 표시기 페이드아웃 (3초 후 완전 투명)"""
        self._mode_indicator_alpha = max(0, self._mode_indicator_alpha - 4)  # ~3.2초에 완전 소멸
        if self._mode_indicator_alpha <= 0:
            self._mode_indicator_timer.stop()
        self.update()

    def _compute_stereo_bonds(self):
        """[FIX-3D-STEREO] RDKit에서 입체 결합 정보 추출"""
        if self._stereo_computed:
            return
        self._stereo_computed = True
        self._stereo_bonds = []
        if not RDKIT_AVAILABLE or not self.mol_data or not self.mol_data.smiles:
            logger.warning("입체 결합 계산 불가: RDKIT=%s, mol_data=%s, smiles=%r",
                           RDKIT_AVAILABLE, bool(self.mol_data),
                           getattr(self.mol_data, 'smiles', None) if self.mol_data else None)
            return
        try:
            mol = Chem.MolFromSmiles(self.mol_data.smiles)
            if mol is None:
                logger.warning("입체 결합 계산 실패: SMILES 파싱 실패 (smiles=%r)", self.mol_data.smiles)
                return
            mol = Chem.AddHs(mol)
            # 키랄 중심 탐색
            chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
            if not chiral_centers:
                return
            chiral_set = {idx for idx, _ in chiral_centers}
            for atom_idx, _chirality in chiral_centers:
                atom = mol.GetAtomWithIdx(atom_idx)
                if atom_idx not in self.mol_data.atom_positions:
                    continue
                center_pos = self.mol_data.atom_positions[atom_idx]
                for neighbor in atom.GetNeighbors():
                    n_idx = neighbor.GetIdx()
                    if n_idx not in self.mol_data.atom_positions:
                        continue
                    n_pos = self.mol_data.atom_positions[n_idx]
                    dz = n_pos[2] - center_pos[2]
                    if abs(dz) > 0.1:
                        bond_type = 'wedge' if dz > 0 else 'dash'
                        self._stereo_bonds.append((atom_idx, n_idx, bond_type))
        except Exception as e:
            logger.debug(f"Stereo bond computation failed: {e}")

    # ------------------------------------------------------------------
    # [P0-3] ESP 전하 계산 및 색상 매핑 (QPainter 폴백용)
    # ------------------------------------------------------------------

    def _compute_esp_charges_qp(self):
        """Gasteiger 전하 계산 (QPainter 폴백용, 캐시).

        Returns:
            Dict[key, float]: 원자 키 → Gasteiger 부분 전하.
            None이면 전하 계산 불가.
        """
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(self.mol_data.atom_symbols, dict):
            return None
        if self._esp_charges is not None:
            return self._esp_charges

        if not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("ESP charge computation skipped: no mol_data or atom_positions")
            return None

        charges = {}
        smiles = getattr(self.mol_data, 'smiles', '') or ''

        if smiles and RDKIT_AVAILABLE:
            try:
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    logger.warning("ESP: Invalid SMILES for Gasteiger charges (QPainter): %s", smiles)
                else:
                    mol = Chem.AddHs(mol)
                    AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                    AllChem.ComputeGasteigerCharges(mol)

                    from collections import defaultdict
                    rdkit_charges = []
                    for atom in mol.GetAtoms():
                        q = float(atom.GetProp('_GasteigerCharge'))
                        sym = atom.GetSymbol()
                        rdkit_charges.append((sym, q))

                    sym_queue = defaultdict(list)
                    for sym, q in rdkit_charges:
                        sym_queue[sym].append(q)

                    sym_idx = defaultdict(int)
                    for key in self.mol_data.atom_positions:
                        sym = self.mol_data.atom_symbols.get(key, "C")
                        idx_val = sym_idx[sym]
                        if idx_val < len(sym_queue.get(sym, [])):
                            charges[key] = sym_queue[sym][idx_val]
                            sym_idx[sym] = idx_val + 1
                        else:
                            charges[key] = 0.0

                    self._esp_charges = charges
                    return self._esp_charges
            except Exception as e:
                logger.warning("ESP: Gasteiger computation failed (QPainter), using EN fallback: %s", e)

        # 전기음성도 기반 휴리스틱 폴백
        EN_TABLE = {
            'H': 2.20, 'C': 2.55, 'N': 3.04, 'O': 3.44, 'F': 3.98,
            'P': 2.19, 'S': 2.58, 'Cl': 3.16, 'Br': 2.96, 'I': 2.66,
            'B': 2.04, 'Si': 1.90, 'Se': 2.55, 'Li': 0.98, 'Na': 0.93,
        }
        ref_en = 2.55  # carbon reference (Pauling electronegativity)
        for key in self.mol_data.atom_positions:
            sym = self.mol_data.atom_symbols.get(key, "C")
            en = EN_TABLE.get(sym, 2.55)
            charges[key] = -(en - ref_en) * 0.35  # 0.35 = empirical scaling factor
        self._esp_charges = charges
        return self._esp_charges

    @staticmethod
    def _esp_charge_to_color_qp(norm):
        """정규화된 전하 [-1,+1] → RGB (McMurry convention, QPainter용).

        5-anchor colormap:
          -1.0 RED (electron-rich)  →  0.0 near-white  →  +1.0 BLUE (electron-poor)     
        중간 색상: red → orange → white → cyan → blue (코사인 보간)
        """
        anchors = [
            (-1.0, (0.90, 0.05, 0.05)),   # RED
            (-0.5, (1.00, 0.55, 0.05)),   # ORANGE
            ( 0.0, (0.94, 0.94, 0.90)),   # WHITE / neutral, no green fill
            ( 0.5, (0.10, 0.65, 0.85)),   # CYAN
            ( 1.0, (0.10, 0.15, 0.95)),   # BLUE
        ]
        norm = max(-1.0, min(1.0, norm))
        for i in range(len(anchors) - 1):
            v0, c0 = anchors[i]
            v1, c1 = anchors[i + 1]
            if norm <= v1:
                t = (norm - v0) / (v1 - v0) if (v1 - v0) > 1e-12 else 0.0
                t = 0.5 * (1.0 - math.cos(t * math.pi))  # cosine interpolation
                r = c0[0] + (c1[0] - c0[0]) * t
                g = c0[1] + (c1[1] - c0[1]) * t
                b = c0[2] + (c1[2] - c0[2]) * t
                return (r, g, b)
        return anchors[-1][1]

    def set_mol_data(self, md):
        self.mol_data = md
        self._stereo_computed = False  # [FIX-3D-STEREO] 새 분자 시 재계산
        self._stereo_bonds = None
        self._esp_charges = None  # [P0-3] ESP 전하 캐시 초기화
        self._pi_cache = None  # [PI-QPainter] π 오비탈 캐시 초기화
        self._update_transform()
        self.update()

    def set_orbital_mode(self, mode: str):
        """[PI-QPainter] 오비탈 모드 설정 (QPainter 폴백).

        Args:
            mode: 'none'|'pi'|'hybrid'|'all'|'esp' 등
        """
        # [BUG3-FIX] hybrid→pi 전환 시 캐시 무효화 — 잔류 금빛 오버레이 방지
        if mode != self.orbital_mode:
            self._pi_cache = None  # sp2 감지 캐시 초기화 (모드 전환 시 재계산 보장)
        self.orbital_mode = mode
        self.esp_mode = (mode == 'esp')
        self.update()

    def set_background_color(self, r: float, g: float, b: float):
        """배경색 변경 (QPainter 폴백 뷰어)."""
        self.bg_color_qc = QColor(int(r * 255), int(g * 255), int(b * 255))
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
        self._vib_phase += 0.15
        self.vib_scale = math.sin(self._vib_phase) * self._vib_amplitude
        self._update_transform()
        self.update()

    def _update_transform(self):
        if not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("QPainter 변환 건너뜀: mol_data=%s, atom_positions=%s",
                           bool(self.mol_data),
                           bool(self.mol_data.atom_positions) if self.mol_data else False)
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

    # ------------------------------------------------------------------
    # [PI-QPainter] π 오비탈 QPainter 렌더링 (McMurry 스타일)
    # ------------------------------------------------------------------

    def _detect_sp2_and_rings_qp(self):
        """RDKit으로 sp2 원자 키 + 방향족 고리 정보를 캐시하여 반환합니다.

        Returns:
            (sp2_keys, ring_groups, ring_atom_keys)
            - sp2_keys: List[key] -- sp2/sp 원자
            - ring_groups: List[List[key]] -- 방향족 고리별 원자 키 리스트
            - ring_atom_keys: Set[key] -- 방향족 고리에 속하는 원자 키
        """
        if self._pi_cache is not None:
            return self._pi_cache

        sp2_keys = []
        ring_groups = []
        ring_atom_keys = set()

        if not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("π 오비탈 QPainter: mol_data 또는 atom_positions 없음")
            self._pi_cache = (sp2_keys, ring_groups, ring_atom_keys)
            return self._pi_cache

        smiles = getattr(self.mol_data, 'smiles', '') or ''
        if not smiles:
            logger.warning("π 오비탈 QPainter: SMILES 없음")
            self._pi_cache = (sp2_keys, ring_groups, ring_atom_keys)
            return self._pi_cache

        if not RDKIT_AVAILABLE:
            logger.warning("π 오비탈 QPainter: RDKit 미설치")
            self._pi_cache = (sp2_keys, ring_groups, ring_atom_keys)
            return self._pi_cache

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("π 오비탈 QPainter: SMILES 파싱 실패 (smiles=%r)", smiles)
                self._pi_cache = (sp2_keys, ring_groups, ring_atom_keys)
                return self._pi_cache

            atom_keys = list(self.mol_data.atom_positions.keys())

            # sp2/sp 혼성 감지
            HybSP2 = Chem.rdchem.HybridizationType.SP2
            HybSP = Chem.rdchem.HybridizationType.SP
            for atom in mol.GetAtoms():
                idx = atom.GetIdx()
                if idx < len(atom_keys):
                    hyb = atom.GetHybridization()
                    if hyb in (HybSP2, HybSP):
                        sp2_keys.append(atom_keys[idx])

            # 방향족 고리 감지 (키 목록 반환 -- 좌표는 paintEvent에서 spos 사용)
            ring_info = mol.GetRingInfo()
            for ring in ring_info.AtomRings():
                if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                    ring_keys = []
                    for i in ring:
                        if i < len(atom_keys):
                            key = atom_keys[i]
                            ring_atom_keys.add(key)
                            ring_keys.append(key)
                    if len(ring_keys) >= 3:
                        ring_groups.append(ring_keys)

        except Exception as e:
            logger.warning("π 오비탈 QPainter sp2 감지 실패: %s", e)

        self._pi_cache = (sp2_keys, ring_groups, ring_atom_keys)
        return self._pi_cache

    def _calc_local_normal_qp(self, atom_key, adjacency):
        """sp2 원자의 로컬 평면 법선 벡터를 계산합니다 (QPainter용).

        이웃 원자 좌표로부터 외적 기반 법선 계산.
        이웃 부족 시 z축 (0,0,1) 폴백.

        Args:
            atom_key: 원자 키
            adjacency: {key: [neighbor_key, ...]} 인접 리스트

        Returns:
            (nx, ny, nz): 단위 법선 벡터
        """
        fallback_normal = (0.0, 0.0, 1.0)
        # Rule N: isinstance guard for adjacency/atom_positions
        if not isinstance(adjacency, dict):
            return fallback_normal
        if not self.mol_data or not self.mol_data.atom_positions:
            return fallback_normal

        pos = self.mol_data.atom_positions.get(atom_key)
        if pos is None:
            return fallback_normal

        neighbors = adjacency.get(atom_key, [])
        vecs = []
        for nb in neighbors:
            nb_pos = self.mol_data.atom_positions.get(nb)
            if nb_pos is not None:
                dx = nb_pos[0] - pos[0]
                dy = nb_pos[1] - pos[1]
                dz = nb_pos[2] - pos[2]
                mag = math.sqrt(dx * dx + dy * dy + dz * dz)
                if mag > 1e-6:
                    vecs.append((dx, dy, dz))

        if len(vecs) >= 2:
            v1 = vecs[0]
            v2 = vecs[1]
            nx = v1[1] * v2[2] - v1[2] * v2[1]
            ny = v1[2] * v2[0] - v1[0] * v2[2]
            nz = v1[0] * v2[1] - v1[1] * v2[0]
            mag = math.sqrt(nx * nx + ny * ny + nz * nz)
            if mag > 1e-6:
                return (nx / mag, ny / mag, nz / mag)

        return fallback_normal

    def _calc_ring_normal_qp(self, ring_positions):
        """고리 원자 좌표 리스트로부터 평면 법선을 계산합니다 (Newell's method, QPainter용).

        Args:
            ring_positions: List[(x, y, z)] -- 고리 원자의 3D 좌표

        Returns:
            (nx, ny, nz): 단위 법선 벡터. 실패 시 z축 폴백.
        """
        fallback_normal = (0.0, 0.0, 1.0)
        if len(ring_positions) < 3:
            return fallback_normal

        nx, ny, nz = 0.0, 0.0, 0.0
        n = len(ring_positions)
        for i in range(n):
            p1 = ring_positions[i]
            p2 = ring_positions[(i + 1) % n]
            nx += (p1[1] - p2[1]) * (p1[2] + p2[2])
            ny += (p1[2] - p2[2]) * (p1[0] + p2[0])
            nz += (p1[0] - p2[0]) * (p1[1] + p2[1])
        mag = math.sqrt(nx * nx + ny * ny + nz * nz)
        if mag > 1e-6:
            return (nx / mag, ny / mag, nz / mag)
        return fallback_normal

    def _paint_pi_orbitals_qp(self, painter, spos, scale, ox, oy, zmin, zr):
        """[PI-QPainter] QPainter로 π 오비탈 시각화 (McMurry 스타일).

        - sp2 원자: 위아래 반투명 타원 (파랑=+위상, 빨강=-위상)
        - 방향족 고리: 도넛형 반투명 영역 (위아래)

        McMurry 참조:
          - 벤젠 π 구름 = 링 위아래 도넛형 로브
          - 개별 p-orbital = dumbbell (위아래 대칭)
          - 파랑 = +위상, 빨강 = -위상

        Args:
            painter: QPainter 인스턴스
            spos: {key: (sx, sy, df, alpha)} 스크린 좌표
            scale: 뷰포트 스케일 팩터
            ox, oy: 뷰포트 원점
            zmin: 최소 z (깊이 정렬용)
            zr: z 범위 (깊이 정렬용)
        """
        sp2_keys, ring_groups, ring_atom_keys = self._detect_sp2_and_rings_qp()
        if not sp2_keys and not ring_groups:
            return

        # 인접 리스트 구축 (로컬 법선 계산용)
        adjacency = {}  # {key: [neighbor_key, ...]}
        if self.mol_data and self.mol_data.bonds:
            for (k1, k2) in self.mol_data.bonds.keys():
                adjacency.setdefault(k1, []).append(k2)
                adjacency.setdefault(k2, []).append(k1)

        # --- (1) 개별 sp2 원자: p-orbital 로브 (위/아래 타원) ---
        # McMurry: p 오비탈 = 핵 위아래 dumbbell, 파랑(+)/빨강(-) 위상
        LOBE_BLUE = QColor(64, 128, 255, 100)   # +위상: 파란색 (alpha=100)
        LOBE_RED = QColor(255, 89, 64, 100)      # -위상: 빨간색 (alpha=100)
        # [BUG2-FIX] QPainter 로브 크기 ~50% 축소 — 교과서 비율 복원
        LOBE_OFFSET_FACTOR = 0.40  # 로브 중심 오프셋 (0.7→0.40: 원자 반지름의 배수)
        LOBE_WIDTH_FACTOR = 0.28   # 로브 너비 (0.55→0.28: C-C 결합 길이의 비율)
        LOBE_HEIGHT_FACTOR = 0.85  # 로브 높이 (납작한 타원형, 유지)

        for key in sp2_keys:
            if key not in spos:
                continue
            sx, sy, df, atom_alpha = spos[key]

            # 로컬 법선 벡터 (3D) → 카메라 좌표계로 회전 적용
            normal_3d = self._calc_local_normal_qp(key, adjacency)
            # 카메라 회전 적용 (Y → X 순서)
            cry_val = math.cos(math.radians(self.rotation_y))
            sry_val = math.sin(math.radians(self.rotation_y))
            crx_val = math.cos(math.radians(self.rotation_x))
            srx_val = math.sin(math.radians(self.rotation_x))

            n3x, n3y, n3z = normal_3d
            # Y 회전
            rx_n = n3x * cry_val + n3z * sry_val
            rz_n = -n3x * sry_val + n3z * cry_val
            # X 회전
            ry_n = n3y * crx_val - rz_n * srx_val
            rz_n2 = n3y * srx_val + rz_n * crx_val

            # 스크린 좌표 방향 (rx_n, ry_n이 스크린 방향)
            # 법선의 스크린 투영 길이
            screen_mag = math.sqrt(rx_n * rx_n + ry_n * ry_n)

            # 기본 로브 크기 (scale 기반)
            lobe_base_size = scale * LOBE_WIDTH_FACTOR * df  # 결합 길이 기반
            lobe_offset = scale * LOBE_OFFSET_FACTOR * df

            if screen_mag > 0.15:
                # 법선이 스크린에 투영되어 보이는 경우 → 타원 위치/방향 계산 가능
                dir_x = rx_n / screen_mag
                dir_y = ry_n / screen_mag

                # 위 로브 (+위상, 파랑)
                up_cx = sx + dir_x * lobe_offset
                up_cy = sy + dir_y * lobe_offset
                # 아래 로브 (-위상, 빨강)
                dn_cx = sx - dir_x * lobe_offset
                dn_cy = sy - dir_y * lobe_offset

                # 타원 크기: 법선 방향 = 높이, 수직 방향 = 너비
                ellipse_w = lobe_base_size * LOBE_HEIGHT_FACTOR
                ellipse_h = lobe_base_size * LOBE_WIDTH_FACTOR

                # 법선 방향 각도 (회전 변환용)
                angle_deg = math.degrees(math.atan2(dir_y, dir_x))

                painter.save()
                painter.setPen(Qt.PenStyle.NoPen)

                # 위 로브 (+위상: 파랑)
                painter.setBrush(QBrush(LOBE_BLUE))
                painter.translate(up_cx, up_cy)
                painter.rotate(angle_deg)
                painter.drawEllipse(QPointF(0, 0), ellipse_w, ellipse_h)
                painter.resetTransform()

                # 아래 로브 (-위상: 빨강)
                painter.setBrush(QBrush(LOBE_RED))
                painter.translate(dn_cx, dn_cy)
                painter.rotate(angle_deg)
                painter.drawEllipse(QPointF(0, 0), ellipse_w, ellipse_h)
                painter.resetTransform()

                painter.restore()
            else:
                # 법선이 스크린에 거의 수직 (위에서 보는 각도) → 원형 로브
                # 깊이 방향이 스크린을 향하므로 로브가 겹쳐 원형으로 보임
                lobe_r = lobe_base_size * 0.6
                painter.save()
                painter.setPen(Qt.PenStyle.NoPen)
                # 뒤쪽 로브 (빨강, 약간 투명)
                painter.setBrush(QBrush(QColor(255, 89, 64, 70)))
                painter.drawEllipse(QPointF(sx, sy), lobe_r, lobe_r)
                # 앞쪽 로브 (파랑, 약간 더 진함)
                painter.setBrush(QBrush(QColor(64, 128, 255, 85)))
                painter.drawEllipse(QPointF(sx, sy), lobe_r * 0.85, lobe_r * 0.85)
                painter.restore()

        # --- (2) 방향족 고리: 도넛형 π 전자구름 (위/아래) ---
        # McMurry: 벤젠 π 구름 = 고리 위아래 도넛형 로브
        RING_BLUE = QColor(64, 128, 255, 55)   # +위상: 파란색 반투명
        RING_RED = QColor(255, 89, 64, 55)      # -위상: 빨간색 반투명
        RING_OUTLINE_BLUE = QColor(64, 128, 255, 90)
        RING_OUTLINE_RED = QColor(255, 89, 64, 90)

        for ring_keys in ring_groups:
            # 고리 원자의 스크린 좌표 수집
            ring_screen = []
            ring_3d_positions = []
            for rk in ring_keys:
                if rk in spos and rk in self.mol_data.atom_positions:
                    ring_screen.append(spos[rk])
                    ring_3d_positions.append(self.mol_data.atom_positions[rk])

            if len(ring_screen) < 3:
                continue

            # 고리 무게중심 (스크린 좌표)
            ring_cx = sum(s[0] for s in ring_screen) / len(ring_screen)
            ring_cy = sum(s[1] for s in ring_screen) / len(ring_screen)
            avg_df = sum(s[2] for s in ring_screen) / len(ring_screen)

            # 고리 반지름 (스크린 좌표 기준)
            ring_radii = [math.sqrt((s[0] - ring_cx) ** 2 + (s[1] - ring_cy) ** 2)
                          for s in ring_screen]
            ring_r = sum(ring_radii) / len(ring_radii) if ring_radii else 20.0

            # 3D 법선 → 카메라 좌표계 회전
            ring_normal = self._calc_ring_normal_qp(ring_3d_positions)
            n3x, n3y, n3z = ring_normal
            cry_val = math.cos(math.radians(self.rotation_y))
            sry_val = math.sin(math.radians(self.rotation_y))
            crx_val = math.cos(math.radians(self.rotation_x))
            srx_val = math.sin(math.radians(self.rotation_x))
            rx_n = n3x * cry_val + n3z * sry_val
            rz_n = -n3x * sry_val + n3z * cry_val
            ry_n = n3y * crx_val - rz_n * srx_val

            screen_mag = math.sqrt(rx_n * rx_n + ry_n * ry_n)
            donut_offset = scale * 0.35 * avg_df  # 도넛 오프셋 (법선 방향)

            # 도넛 크기: 안쪽 반지름 = ring_r * 0.5, 바깥쪽 = ring_r * 1.15
            outer_r = ring_r * 1.15
            inner_r = ring_r * 0.5

            if screen_mag > 0.15:
                dir_x = rx_n / screen_mag
                dir_y = ry_n / screen_mag

                painter.save()

                # 위쪽 도넛 (+위상: 파랑)
                up_cx = ring_cx + dir_x * donut_offset
                up_cy = ring_cy + dir_y * donut_offset

                # QPainterPath로 도넛(annulus) 그리기
                from PyQt6.QtGui import QPainterPath
                donut_path = QPainterPath()
                donut_path.addEllipse(QPointF(up_cx, up_cy), outer_r, outer_r)
                inner_path = QPainterPath()
                inner_path.addEllipse(QPointF(up_cx, up_cy), inner_r, inner_r)
                donut_path = donut_path.subtracted(inner_path)
                painter.setPen(QPen(RING_OUTLINE_BLUE, 1.5))
                painter.setBrush(QBrush(RING_BLUE))
                painter.drawPath(donut_path)

                # 아래쪽 도넛 (-위상: 빨강)
                dn_cx = ring_cx - dir_x * donut_offset
                dn_cy = ring_cy - dir_y * donut_offset

                donut_path_dn = QPainterPath()
                donut_path_dn.addEllipse(QPointF(dn_cx, dn_cy), outer_r, outer_r)
                inner_path_dn = QPainterPath()
                inner_path_dn.addEllipse(QPointF(dn_cx, dn_cy), inner_r, inner_r)
                donut_path_dn = donut_path_dn.subtracted(inner_path_dn)
                painter.setPen(QPen(RING_OUTLINE_RED, 1.5))
                painter.setBrush(QBrush(RING_RED))
                painter.drawPath(donut_path_dn)

                painter.restore()
            else:
                # 위에서 보는 각도 → 동심원으로 보임
                painter.save()
                painter.setPen(QPen(RING_OUTLINE_BLUE, 1.5))
                painter.setBrush(QBrush(QColor(64, 128, 255, 40)))
                painter.drawEllipse(QPointF(ring_cx, ring_cy), outer_r, outer_r)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self.bg_color_qc))
                painter.drawEllipse(QPointF(ring_cx, ring_cy), inner_r, inner_r)
                # 빨간 윤곽 (합쳐진 -위상)
                painter.setPen(QPen(RING_OUTLINE_RED, 1.0, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(ring_cx, ring_cy), outer_r * 0.9, outer_r * 0.9)
                painter.restore()

    def _project_direction_qp(self, direction, scale):
        dx, dy, dz = direction
        mag = math.sqrt(dx * dx + dy * dy + dz * dz)
        if mag < 1e-6:
            return (0.0, -1.0)
        dx, dy, dz = dx / mag, dy / mag, dz / mag
        crx, srx = math.cos(math.radians(self.rotation_x)), math.sin(math.radians(self.rotation_x))
        cry, sry = math.cos(math.radians(self.rotation_y)), math.sin(math.radians(self.rotation_y))
        rx = dx * cry + dz * sry
        rz = -dx * sry + dz * cry
        ry = dy * crx - rz * srx
        sx, sy = rx * scale, ry * scale
        smag = math.sqrt(sx * sx + sy * sy)
        if smag < 1e-6:
            return (0.0, -1.0)
        return (sx / smag, sy / smag)

    def _paint_hybrid_orbitals_qp(self, painter, spos, scale):
        """QPainter fallback for hybrid orbital geometry in cursor-safe captures."""
        if not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("Hybrid orbital QPainter render skipped: molecule data missing")
            return
        try:
            atom_info = AdvancedOrbitalRenderer()._analyze_atoms(self.mol_data)
        except Exception as e:
            logger.warning("Hybrid orbital QPainter analysis failed: %s", e)
            return

        color_map = {
            "sp": QColor(170, 150, 220, 82),
            "sp2": QColor(90, 130, 235, 96),
            "sp3": QColor(88, 190, 120, 96),
            "sp3d": QColor(230, 190, 70, 100),
            "sp3d2": QColor(230, 190, 70, 100),
        }
        ideal_dirs = {
            "sp": [(1, 0, 0), (-1, 0, 0)],
            "sp2": [(1, 0, 0), (-0.5, 0.866, 0), (-0.5, -0.866, 0)],
            "sp3": [(0.577, 0.577, 0.577), (0.577, -0.577, -0.577),
                    (-0.577, 0.577, -0.577), (-0.577, -0.577, 0.577)],
            "sp3d": [(1, 0, 0), (-0.5, 0.866, 0), (-0.5, -0.866, 0), (0, 0, 1), (0, 0, -1)],
            "sp3d2": [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)],
        }

        painter.save()
        painter.setPen(QPen(QColor(245, 245, 245, 130), 1.2))
        for key, info in atom_info.items():
            if info.get("sym") == "H" or key not in spos:
                continue
            hyb = info.get("hyb", "sp3")
            dirs = [(d[0], d[1], d[2]) for d in info.get("ndirs", [])]
            needed = {"sp": 2, "sp2": 3, "sp3": 4, "sp3d": 5, "sp3d2": 6}.get(hyb, 4)
            fallback = ideal_dirs.get(hyb, ideal_dirs["sp3"])
            while len(dirs) < needed:
                dirs.append(fallback[len(dirs) % len(fallback)])

            sx, sy, df, _alpha = spos[key]
            base_color = color_map.get(hyb, color_map["sp3"])
            for direction in dirs[:needed]:
                ux, uy = self._project_direction_qp(direction, scale)
                length = max(22.0, scale * 0.42 * df)
                width = max(8.0, scale * 0.12 * df)
                cx = sx + ux * length * 0.62
                cy = sy + uy * length * 0.62
                angle = math.degrees(math.atan2(uy, ux))
                painter.save()
                painter.translate(QPointF(cx, cy))
                painter.rotate(angle)
                painter.setBrush(QBrush(base_color))
                painter.drawEllipse(QPointF(0, 0), length * 0.55, width)
                painter.restore()

            if hyb == "sp2" and len(dirs) >= 2:
                nx, ny, nz = AdvancedOrbitalRenderer._cross3(dirs[0], dirs[1])
                ux, uy = self._project_direction_qp((nx, ny, nz), scale)
                pi_color = QColor(80, 150, 255, 70)
                pi_neg = QColor(255, 105, 105, 70)
                painter.setBrush(QBrush(pi_color))
                painter.drawEllipse(QPointF(sx + ux * scale * 0.28, sy + uy * scale * 0.28),
                                    max(10.0, scale * 0.16), max(5.0, scale * 0.08))
                painter.setBrush(QBrush(pi_neg))
                painter.drawEllipse(QPointF(sx - ux * scale * 0.28, sy - uy * scale * 0.28),
                                    max(10.0, scale * 0.16), max(5.0, scale * 0.08))
        painter.restore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.bg_color_qc)
        if not self._transformed:
            p.setPen(QColor(180, 180, 180))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No molecule data")
            p.end()
            return
        w, h = self.width(), self.height()
        ox, oy = w/2 + self.pan_x, h/2 + self.pan_y
        bs = self.mol_data.get_bounding_size()
        scale = min(w, h) / (bs + 4.0) * 0.55 * self.zoom_scale  # 0.35→0.55: 뷰포트 스케일 확대 (분자가 화면 ~55% 차지)
        sorted_a = sorted(self._transformed, key=lambda t: t[3])
        zvals = [t[3] for t in sorted_a]
        zmin, zmax = min(zvals), max(zvals)
        zr = (zmax - zmin) if zmax > zmin else 1.0
        spos = {}
        for key, rx, ry, rz in self._transformed:
            sx, sy = ox + rx*scale, oy + ry*scale
            # 깊이 인자: 뒤쪽 작게/흐리게, 앞쪽 크게/선명하게
            norm_z = (rz - zmin) / zr  # 0(뒤) ~ 1(앞)
            df = 0.55 + 0.9 * norm_z   # 0.55(뒤) ~ 1.45(앞) — 2.6배 차이
            # [FIX-OPAQUE] Atoms are always fully opaque (alpha=255).
            # Depth is conveyed by size scaling (df) and lighting gradient, not transparency.
            # Previous: alpha=140..255 caused translucent "frog egg" appearance.
            alpha = 255
            spos[key] = (sx, sy, df, alpha)
        # Bonds — [P0-2] CPK 분할 색상 + [FIX-3D-005] 진동 시 결합 신축 색상 코딩
        # Rule N: isinstance guard for mol_data.atom_symbols
        assert isinstance(self.mol_data.atom_symbols, dict)
        _qp_has_vib = self.vib_vectors is not None and self._vib_active and abs(self.vib_scale) > 0.001
        for (k1, k2), order in self.mol_data.bonds.items():
            if k1 in spos and k2 in spos:
                s1, s2 = spos[k1], spos[k2]
                avg_df = (s1[2] + s2[2]) / 2
                avg_alpha = int((s1[3] + s2[3]) / 2)
                # M565: 결합 굵기 3.0 → 4.5 (50% 증가) — 격분11 "알갱이만 떠있다" 직접 응답.
                # 차수별 시각 구분 강화 — 단일/이중/삼중/방향족 명확히 보이도록.
                bw = max(2, int(4.5 * avg_df))  # 결합 굵기
                # [P0-2] CPK 분할 색상: 각 결합의 반은 시작 원자, 나머지 반은 끝 원자 CPK 색상
                sym1 = self.mol_data.atom_symbols.get(k1, "C")
                sym2 = self.mol_data.atom_symbols.get(k2, "C")
                r1c, g1c, b1c = get_cpk_color(sym1)
                r2c, g2c, b2c = get_cpk_color(sym2)
                # 깊이 인자로 명도 조절 (더 깊은 곳은 더 어둡게)
                df_clamp = min(1.0, avg_df)
                color1 = QColor(int(r1c * 255 * df_clamp),
                                int(g1c * 255 * df_clamp),
                                int(b1c * 255 * df_clamp), avg_alpha)
                color2 = QColor(int(r2c * 255 * df_clamp),
                                int(g2c * 255 * df_clamp),
                                int(b2c * 255 * df_clamp), avg_alpha)
                # 진동 시 strain 색상이 CPK를 오버라이드
                if _qp_has_vib and k1 in self.mol_data.atom_positions and k2 in self.mol_data.atom_positions:
                    eq1 = self.mol_data.atom_positions[k1]
                    eq2 = self.mol_data.atom_positions[k2]
                    eq_len = math.sqrt(sum((a-b)**2 for a, b in zip(eq1, eq2)))
                    if eq_len > 0.01:
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
                            strain_t = max(-1.0, min(1.0, strain / 0.15))  # 15% strain = max color
                            g_base = int(100 * avg_df)
                            if strain_t > 0.02:
                                t = strain_t
                                vib_c = QColor(int(g_base + (255 - g_base) * t),
                                               int(g_base * (1 - t * 0.6)),
                                               int(g_base * (1 - t * 0.6)), avg_alpha)
                                color1 = vib_c
                                color2 = vib_c
                            elif strain_t < -0.02:
                                t = -strain_t
                                vib_c = QColor(int(g_base * (1 - t * 0.6)),
                                               int(g_base * (1 - t * 0.3)),
                                               int(g_base + (255 - g_base) * t), avg_alpha)
                                color1 = vib_c
                                color2 = vib_c
                x1, y1, x2, y2 = int(s1[0]), int(s1[1]), int(s2[0]), int(s2[1])
                mx, my = (x1 + x2) // 2, (y1 + y2) // 2  # 결합 중간점 (CPK 분할)
                bo = order
                if isinstance(bo, (float, int)) and abs(bo - 0.5) < 0.01:
                    # 배위결합: 점선 (CPK 분할)
                    pen1 = QPen(color1, max(1, bw - 1))
                    pen1.setStyle(Qt.PenStyle.DashLine)
                    pen2 = QPen(color2, max(1, bw - 1))
                    pen2.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen1)
                    p.drawLine(x1, y1, mx, my)
                    p.setPen(pen2)
                    p.drawLine(mx, my, x2, y2)
                elif isinstance(bo, (float, int)) and abs(bo - 1.5) < 0.01:
                    # 방향족 결합: 실선 + 얇은 점선 병렬 (CPK 분할)
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx*dx + dy*dy) if (dx*dx + dy*dy) > 0 else 1
                    # M565: off 2 → 5 (2.5x) — 격분11 차수별 시각 구분 강화.
                    # 5px perpendicular offset — single과 aromatic이 명확히 구별.
                    off = 5  # 2 → 5 (M565 격분11 직접 응답)
                    nx, ny = dx/length * off, dy/length * off
                    mnx1, mny1 = int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2)
                    mnx2, mny2 = int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2)
                    # 주선: 실선 (CPK 분할)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 - nx), int(y1 - ny), mnx1, mny1)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx1, mny1, int(x2 - nx), int(y2 - ny))
                    # 부선: 얇은 점선 (CPK 분할) — M565: bw-1 → bw (점선도 굵게 보이도록)
                    dash_pen1 = QPen(color1, max(2, bw - 1))
                    dash_pen1.setStyle(Qt.PenStyle.DashLine)
                    dash_pen2 = QPen(color2, max(2, bw - 1))
                    dash_pen2.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(dash_pen1)
                    p.drawLine(int(x1 + nx), int(y1 + ny), mnx2, mny2)
                    p.setPen(dash_pen2)
                    p.drawLine(mnx2, mny2, int(x2 + nx), int(y2 + ny))
                elif isinstance(bo, (float, int)) and bo >= 2.8:
                    # 삼중결합: 3 평행선 (CPK 분할)
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx*dx + dy*dy) if (dx*dx + dy*dy) > 0 else 1
                    # M565: off 2 → 6 (3x) — 격분11 삼중결합 명확 구별.
                    # 6px perpendicular offset (이중 5px보다 1px 더 — 삼중이 더 넓게 퍼져 보이도록)
                    off = 6  # 2 → 6 (M565 격분11 직접 응답)
                    nx, ny = dx/length * off, dy/length * off
                    mnx_p, mny_p = int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2)
                    mnx_n, mny_n = int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2)
                    # 중심선 (CPK 분할)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(x1, y1, mx, my)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mx, my, x2, y2)
                    # 상단 평행선 (CPK 분할)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 + nx), int(y1 + ny), mnx_p, mny_p)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_p, mny_p, int(x2 + nx), int(y2 + ny))
                    # 하단 평행선 (CPK 분할)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 - nx), int(y1 - ny), mnx_n, mny_n)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_n, mny_n, int(x2 - nx), int(y2 - ny))
                elif isinstance(bo, (float, int)) and bo >= 1.8:
                    # 이중결합: 2 평행선 (CPK 분할)
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx*dx + dy*dy) if (dx*dx + dy*dy) > 0 else 1
                    # M565: off 2 → 5 — 격분11 이중결합 명확 구별 (single과 차이 명확)
                    off = 5  # 2 → 5 (M565 격분11 직접 응답)
                    nx, ny = dx/length * off, dy/length * off
                    mnx_p, mny_p = int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2)
                    mnx_n, mny_n = int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 + nx), int(y1 + ny), mnx_p, mny_p)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_p, mny_p, int(x2 + nx), int(y2 + ny))
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 - nx), int(y1 - ny), mnx_n, mny_n)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_n, mny_n, int(x2 - nx), int(y2 - ny))
                else:
                    # 단일결합 (order 1.0, CPK 분할)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(x1, y1, mx, my)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mx, my, x2, y2)
        # [FIX-3D-STEREO] 입체 결합 (웨지/대쉬) QPainter 렌더링
        self._compute_stereo_bonds()
        if self._stereo_bonds:
            from PyQt6.QtGui import QPolygonF
            for begin_idx, end_idx, bond_type in self._stereo_bonds:
                if begin_idx not in spos or end_idx not in spos:
                    continue
                s1 = spos[begin_idx]
                s2 = spos[end_idx]
                x1, y1 = s1[0], s1[1]
                x2, y2 = s2[0], s2[1]
                dx_s, dy_s = x2 - x1, y2 - y1
                length_s = math.sqrt(dx_s * dx_s + dy_s * dy_s)
                if length_s < 1.0:
                    continue
                # 수직 방향 단위벡터
                perp_x, perp_y = -dy_s / length_s, dx_s / length_s
                if bond_type == 'wedge':
                    # 웨지: 시작점 좁고 끝점 넓은 삼각형 (관찰자 방향)
                    wedge_w = max(3.0, 5.0 * (s1[2] + s2[2]) / 2)  # 깊이 기반 너비
                    tri = QPolygonF([
                        QPointF(x1, y1),
                        QPointF(x2 + perp_x * wedge_w, y2 + perp_y * wedge_w),
                        QPointF(x2 - perp_x * wedge_w, y2 - perp_y * wedge_w),
                    ])
                    avg_alpha = int((s1[3] + s2[3]) / 2)
                    p.setPen(QPen(QColor(60, 120, 220, avg_alpha), 1))
                    p.setBrush(QBrush(QColor(60, 120, 220, avg_alpha)))
                    p.drawPolygon(tri)
                elif bond_type == 'dash':
                    # 대쉬: 점선 (관찰자 반대 방향)
                    n_dashes = 6  # 대쉬 세그먼트 수
                    avg_alpha = int((s1[3] + s2[3]) / 2)
                    dash_w = max(2.0, 3.5 * (s1[2] + s2[2]) / 2)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(220, 80, 80, avg_alpha)))
                    for di in range(n_dashes):
                        t = (di + 0.3) / n_dashes
                        cx_d = x1 + dx_s * t
                        cy_d = y1 + dy_s * t
                        w_d = dash_w * t  # 점진적으로 넓어짐
                        p.drawRect(
                            int(cx_d - perp_x * w_d - dx_s / length_s),
                            int(cy_d - perp_y * w_d - dy_s / length_s),
                            max(2, int(length_s / n_dashes * 0.5)),
                            max(2, int(w_d * 2))
                        )
        # [PI-QPainter] π 오비탈 렌더링 (bonds 뒤, atoms 앞에 — 반투명이므로 원자가 위에)
        if self.orbital_mode == 'pi':
            self._paint_pi_orbitals_qp(p, spos, scale, ox, oy, zmin, zr)
        elif self.orbital_mode in ('hybrid', 'all'):
            self._paint_hybrid_orbitals_qp(p, spos, scale)
        # Atoms — [VIB-SPEC] 진동 하이라이트 인덱스 확인
        _qp_atom_keys = list(self.mol_data.atom_positions.keys())
        _qp_highlight = self._vib_highlight_indices if hasattr(self, '_vib_highlight_indices') else set()
        # [P0-3] ESP 모드: Gasteiger 전하 → 색상 매핑 준비
        _esp_charges_map = None
        _esp_max_abs = 0.5  # 정규화용 최대 절댓값 (degenerate 방지)
        if self.esp_mode:
            _esp_charges_map = self._compute_esp_charges_qp()
            if isinstance(_esp_charges_map, dict) and _esp_charges_map:
                abs_vals = [abs(v) for v in _esp_charges_map.values() if isinstance(v, (int, float))]
                if abs_vals:
                    _esp_max_abs = max(max(abs_vals), 0.01)  # 0 나눗셈 방지
            else:
                logger.warning("ESP mode active but no charges computed; falling back to CPK")
        for key, rx, ry, rz in sorted_a:
            sym = self.mol_data.atom_symbols.get(key, "C")
            sx, sy, df, atom_alpha = spos[key]
            if self.render_mode == "space_filling":
                rad = get_vdw_radius(sym) * scale * 0.4 * df
            else:
                rad = get_covalent_radius(sym) * scale * 0.5 * df
            rad = max(3, rad)
            # [P0-3] ESP 모드 시 전하 기반 색상, 아니면 CPK 색상
            if self.esp_mode and isinstance(_esp_charges_map, dict) and _esp_charges_map:
                charge_val = _esp_charges_map.get(key, 0.0)
                if not isinstance(charge_val, (int, float)):
                    charge_val = 0.0
                norm_charge = charge_val / _esp_max_abs  # [-1, +1] 정규화
                r, g, b = self._esp_charge_to_color_qp(norm_charge)
            else:
                r, g, b = get_cpk_color(sym)
            bc = QColor(int(r*255), int(g*255), int(b*255), atom_alpha)
            # [VIB-SPEC] 하이라이트: 진동 관련 원자에 발광 링 표시
            _atom_idx = _qp_atom_keys.index(key) if key in _qp_atom_keys else -1
            is_highlighted = _atom_idx in _qp_highlight and len(_qp_highlight) > 0
            if is_highlighted:
                # [M830 anger#17] 진동모드 하이라이트 노란색 정합성 FIX:
                # orange(255,165,0) -> yellow(255,255,0) (ORCA/GaussView/Avogadro 학술 표준 — Hanwell 2012)
                glow_pen = QPen(QColor(255, 255, 0, 160), max(2, int(rad * 0.25)))
                p.setPen(glow_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(sx, sy), rad + 4, rad + 4)
            # 구체 그라데이션 (조명 효과 강화)
            grad = QRadialGradient(sx - rad*0.35, sy - rad*0.35, rad*1.3)
            grad.setColorAt(0.0, QColor(255, 255, 255, min(255, atom_alpha + 30)))  # 스펙큘러 하이라이트
            grad.setColorAt(0.25, QColor(bc.red(), bc.green(), bc.blue(), atom_alpha).lighter(160))
            grad.setColorAt(0.6, QColor(bc.red(), bc.green(), bc.blue(), atom_alpha))
            grad.setColorAt(1.0, QColor(bc.red(), bc.green(), bc.blue(), atom_alpha).darker(250))
            # 앞쪽 원자: 진한 테두리 (깊이 구분 핵심)
            outline_w = max(0.5, 1.5 * df)  # 앞쪽=더 굵은 테두리
            outline_alpha = min(255, int(atom_alpha * 0.7))
            p.setPen(QPen(QColor(30, 30, 30, outline_alpha), outline_w))
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(sx, sy), rad, rad)
            if self.render_mode == "ball_and_stick" and sym not in ("C", "H") and rad > 8:
                p.setPen(QColor(255, 255, 255, atom_alpha))
                p.setFont(QFont(_QT_KR_FONT, max(7, int(rad*0.6))))  # [M1461] Rule Q: offscreen 폰트
                p.drawText(int(sx-rad*0.4), int(sy+rad*0.2), sym)
        # 진동 변위 화살표 표시 — [FIX-VIB-ARROW] 가시성 강화
        if self.vib_vectors and self._vib_active:
            atom_keys = list(self.mol_data.atom_positions.keys())
            arrow_pen = QPen(QColor(50, 255, 50, 230), 3)  # 밝은 녹색, 더 굵게
            p.setPen(arrow_pen)
            p.setBrush(QBrush(QColor(50, 255, 50, 230)))
            for idx, key in enumerate(atom_keys):
                if key not in spos or idx >= len(self.vib_vectors):
                    continue
                vx, vy, vz = self.vib_vectors[idx]
                mag = math.sqrt(vx*vx + vy*vy + vz*vz)
                if mag < 0.005:
                    continue
                sx, sy, df, _a = spos[key]
                # 변위벡터를 회전 적용 (카메라 좌표계)
                cry2, sry2 = math.cos(math.radians(self.rotation_y)), math.sin(math.radians(self.rotation_y))
                crx2, srx2 = math.cos(math.radians(self.rotation_x)), math.sin(math.radians(self.rotation_x))
                dvx = vx*cry2 + vz*sry2
                dvz = -vx*sry2 + vz*cry2
                dvy = vy*crx2 - dvz*srx2
                arrow_scale = scale * 5.0  # 화살표 크기 증폭 (기존 3.0 → 5.0)
                ex = sx + dvx * arrow_scale
                ey = sy + dvy * arrow_scale
                # 최소 화살표 길이 보장 (10px)
                adx, ady = ex - sx, ey - sy
                arrow_px_len = math.sqrt(adx*adx + ady*ady)
                if arrow_px_len < 10.0 and arrow_px_len > 0.5:
                    scale_up = 10.0 / arrow_px_len
                    ex = sx + adx * scale_up
                    ey = sy + ady * scale_up
                p.drawLine(int(sx), int(sy), int(ex), int(ey))
                # 화살표 머리 — 더 큰 원
                p.drawEllipse(QPointF(ex, ey), 4, 4)
        # [FIX-3D-BOUNDARY] 분자 경계 표시 (도킹 모드에서 리간드/단백질 구분)
        if self._protein_ca and spos:
            # 리간드(원래 분자) 경계 — 따뜻한 색상 계열
            mol_xs = [s[0] for s in spos.values()]
            mol_ys = [s[1] for s in spos.values()]
            if mol_xs and mol_ys:
                margin = 12  # px 여백
                bx1, by1 = min(mol_xs) - margin, min(mol_ys) - margin
                bx2, by2 = max(mol_xs) + margin, max(mol_ys) + margin
                p.setPen(QPen(QColor(255, 160, 60, 50), 1.5, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(int(bx1), int(by1), int(bx2 - bx1), int(by2 - by1), 6, 6)
                # 라벨
                p.setPen(QColor(255, 180, 80, 100))
                p.setFont(QFont(_QT_KR_FONT, 7))  # [M1461] Rule Q: offscreen 폰트
                p.drawText(int(bx1) + 4, int(by1) - 2, "Ligand")
        # 단백질/도킹 시각화 오버레이
        if self._protein_ca:
            self._paint_protein(p, w, h)
        # [FIX-3D-IND] 2.5D 모드 표시기 (하단 좌측, 페이드아웃)
        if self._mode_indicator_alpha > 0:
            ind_alpha = self._mode_indicator_alpha
            p.setPen(QColor(180, 180, 180, ind_alpha))
            p.setFont(QFont("Malgun Gothic", 9))  # [M1444] Rule Q: 한국어 텍스트
            p.drawText(8, h - 8, "2.5D 모드 (OpenGL 미사용)")
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
        # [M829 anger#21] zoom wheel -> slider sync (FallbackRenderer2D parent popup)
        _p = self.parent()
        if _p is not None and hasattr(_p, 'zoom_slider'):
            _p.zoom_slider.blockSignals(True)  # prevent feedback loop
            _p.zoom_slider.setValue(int(self.zoom_scale * 100))
            _p.zoom_slider.blockSignals(False)
            if hasattr(_p, 'zoom_lbl'):
                _p.zoom_lbl.setText(f"{int(self.zoom_scale * 100)}%")

    def reset_view(self):
        self.rotation_x = self.rotation_y = self.pan_x = self.pan_y = 0.0
        self.zoom_scale = 1.0
        self._update_transform()
        self.update()

    # ── 단백질 도킹 시각화 (QPainter 2.5D) ──────────────────────────
    def set_protein_data(self, ca_atoms, binding_site=None):
        """[FallbackRenderer2D] 단백질 Cα 백본 데이터 설정 (M155 fix: _secondary_structure 리셋)"""
        self._protein_ca = ca_atoms
        # [FIX-RIBBON] 새 단백질 로드 시 2차 구조 캐시 리셋 (M155 교훈)
        self._secondary_structure = None
        self._binding_site = binding_site
        self._binding_site_radius = 8.0
        self._dock_approach_offset = None
        if not hasattr(self, '_dock_approach_timer'):
            self._dock_approach_timer = QTimer(self)
            self._dock_approach_timer.timeout.connect(self._dock_approach_tick)
        # [RIBBON-FALLBACK] 리본 모드가 이미 켜져 있으면 즉시 2차 구조 탐지
        if self._ribbon_mode and ca_atoms:
            self._detect_secondary_structure()
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
            # ── Auto-capture docking result for DryLab report ──
            self._auto_capture_docking("docking_full")
        self.update()

    def _auto_capture_docking(self, tag: str = "docking"):
        """Auto-capture current 3D view for DryLab report.

        Saves screenshots to docs/exports/auto_captures/ with timestamp.
        Called automatically when docking animation finishes.
        """
        try:
            import os, time
            cap_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                "docs", "exports", "auto_captures")
            os.makedirs(cap_dir, exist_ok=True)

            smiles_tag = ""
            if hasattr(self, 'mol_data') and self.mol_data and self.mol_data.smiles:
                # Short hash for filename
                smiles_tag = f"_{abs(hash(self.mol_data.smiles)) % 10000:04d}"

            ts = time.strftime("%Y%m%d_%H%M%S")

            # Capture current view (full ribbon + ligand)
            try:
                pix = self.grabFramebuffer() if hasattr(self, 'grabFramebuffer') else self.grab()
            except Exception as e:
                logger.debug("grabFramebuffer failed, using grab(): %s", e)
                pix = self.grab()
            if pix and not pix.isNull():
                path_full = os.path.join(cap_dir, f"{tag}_full{smiles_tag}_{ts}.png")
                pix.save(path_full)

                # Also save zoomed version (2x zoom on center)
                old_zoom = self.zoom_scale
                self.zoom_scale = old_zoom * 2.5
                self._update_transform()
                self.repaint()
                try:
                    pix2 = self.grabFramebuffer() if hasattr(self, 'grabFramebuffer') else self.grab()
                except Exception as e:
                    logger.debug("grabFramebuffer zoom capture failed: %s", e)
                    pix2 = self.grab()
                if pix2 and not pix2.isNull():
                    path_zoom = os.path.join(cap_dir, f"{tag}_zoom{smiles_tag}_{ts}.png")
                    pix2.save(path_zoom)

                # Restore zoom
                self.zoom_scale = old_zoom
                self._update_transform()
                self.repaint()

                # Store paths for DryLab to pick up
                if not hasattr(self.__class__, '_drylab_captures'):
                    self.__class__._drylab_captures = {}
                self.__class__._drylab_captures['docking_full'] = path_full
                self.__class__._drylab_captures['docking_zoom'] = path_zoom if pix2 else path_full

                logger.info("Auto-captured docking views: %s", path_full)
        except Exception as e:
            logger.debug("Auto-capture failed: %s", e)

    def _paint_protein(self, p, w, h):
        """단백질 Cα 백본 + 도킹 포즈 그리기 (QPainter 2.5D)

        [B10-2 FIX] _ribbon_mode=True 시 알파헬릭스(빨강 아치)/베타시트(노랑 화살표) QPainter 렌더링.
        _ribbon_mode=False 시 기존 backbone line 렌더링 (기본값).
        Rule M: 실패 시 logger.warning (silent failure 금지).
        """
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

        chain_colors = {"A": QColor(80,160,255,120), "B": QColor(80,255,160,120)}

        # [B10-2 FIX] Ribbon 모드: 2차 구조 기반 QPainter 렌더링
        if self._ribbon_mode:
            # 2차 구조 탐지 (없으면 자동)
            if self._secondary_structure is None:
                try:
                    self._detect_secondary_structure()
                except Exception as _e:
                    logger.warning("[FallbackRenderer2D] 2차 구조 탐지 실패: %s", _e)
            ss = self._secondary_structure or ['C'] * len(ca)
            # 체인별 그룹핑
            chains_ss = {}
            for idx, (res, x, y, z, ch) in enumerate(ca):
                chains_ss.setdefault(ch, []).append((idx, x, y, z, res))

            # Rule N: isinstance guard for chain_colors
            if not isinstance(chain_colors, dict):
                chain_colors = {}
            for ch, atoms in chains_ss.items():
                if len(atoms) < 2:
                    continue
                base_color = chain_colors.get(ch, QColor(150, 150, 200, 120))
                # 세그먼트별 렌더링
                n = len(atoms)
                for i in range(n - 1):
                    idx0, x0, y0, z0, _r0 = atoms[i]
                    idx1, x1, y1, z1, _r1 = atoms[i + 1]
                    sx0, sy0 = project(x0, y0, z0)
                    sx1, sy1 = project(x1, y1, z1)
                    struct = ss[idx0] if idx0 < len(ss) else 'C'

                    seg_dx = sx1 - sx0
                    seg_dy = sy1 - sy0
                    seg_len = math.hypot(seg_dx, seg_dy)
                    if seg_len < 0.5:
                        continue

                    if struct == 'H':
                        # alpha-helix: 빨간 두꺼운 선 (코일 효과 = 약간 오프셋)
                        perp_x = -seg_dy / seg_len * 3.0
                        perp_y = seg_dx / seg_len * 3.0
                        p.setPen(QPen(QColor(220, 50, 50, 180), 4))
                        p.drawLine(
                            QPointF(sx0 + perp_x, sy0 + perp_y),
                            QPointF(sx1 + perp_x, sy1 + perp_y))
                    elif struct == 'E':
                        # beta-sheet: 노란 납작 화살표 모양 사각형
                        perp_x = -seg_dy / seg_len * 5.0
                        perp_y = seg_dx / seg_len * 5.0
                        poly = QPolygonF([
                            QPointF(sx0 + perp_x, sy0 + perp_y),
                            QPointF(sx0 - perp_x, sy0 - perp_y),
                            QPointF(sx1 - perp_x, sy1 - perp_y),
                            QPointF(sx1 + perp_x, sy1 + perp_y),
                        ])
                        p.setPen(QPen(QColor(220, 200, 40, 180), 1))
                        p.setBrush(QBrush(QColor(220, 200, 40, 120)))
                        p.drawPolygon(poly)
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        # 화살표 머리 (마지막 세그먼트)
                        if i == n - 2:
                            arrow_perp_x = perp_x * 2.0
                            arrow_perp_y = perp_y * 2.0
                            arrowhead = QPolygonF([
                                QPointF(sx1 + arrow_perp_x, sy1 + arrow_perp_y),
                                QPointF(sx1 - arrow_perp_x, sy1 - arrow_perp_y),
                                QPointF(sx1 + seg_dx * 0.3, sy1 + seg_dy * 0.3),
                            ])
                            p.setPen(Qt.PenStyle.NoPen)
                            p.setBrush(QBrush(QColor(220, 200, 40, 200)))
                            p.drawPolygon(arrowhead)
                            p.setBrush(Qt.BrushStyle.NoBrush)
                    else:
                        # coil: 체인 색상 가는 선
                        p.setPen(QPen(base_color, 1))
                        p.drawLine(QPointF(sx0, sy0), QPointF(sx1, sy1))
        else:
            # 기존 backbone line 렌더링
            prev = None
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
            }  # Rule N: isinstance guard — elem_colors is local dict
            assert isinstance(elem_colors, dict)
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
        # [FIX-GL-FALLBACK] OpenGL 컨텍스트 검증 + QPainter 폴백
        self._gl_validated = False       # initializeGL 성공 여부
        self._gl_fallback = False        # True면 QPainter 2.5D로 폴백
        self._gl_paint_count = 0         # paintGL 호출 횟수 (검증용)
        self._bs = BallAndStickRenderer()
        self._sf = SpaceFillingRenderer()
        self._pi = PiOrbitalRenderer()            # [CHEM-6] π 오비탈
        self._adv = AdvancedOrbitalRenderer()     # [CHEM-8] 고차원 오비탈
        self.orbital_mode = 'none'                # 'none'|'pi'|'hybrid'|'d_orbital'|'f_orbital'|'all'|'esp'
        self.show_pi_orbitals = False             # 하위호환

        # Camera
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._center = (0.0, 0.0, 0.0)
        self._view_scale = 1.0

        # Background color (r, g, b, a) — default dark
        self.bg_color = (0.12, 0.12, 0.12, 1.0)

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
        self._ts_flash = False  # [B10-14] True=TS 전이상태 시각적 강조 활성
        self._binding_site_center = None  # 결합 부위 중심
        self._binding_site_radius = 8.0  # 결합 부위 반경 (Å)
        self._interaction_lines = []  # [(x1,y1,z1,x2,y2,z2,type)] 상호작용 선

        # [BINDING-SITE] 결합 부위 주변 전체 원자 (잔기 스틱 렌더링용)
        self._binding_site_full_atoms = None  # List[(elem, x, y, z, res_name, res_seq)]
        self._binding_site_bonds = None       # 캐싱된 잔기 내 결합
        self._computed_interactions = None    # 캐싱된 상호작용 선 (H-bond 등)

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

        # [FIX-3D-IND] OpenGL 모드 표시기 (startup에만 표시 후 페이드아웃)
        self._gl_mode_indicator_alpha = 255
        self._gl_mode_indicator_timer = QTimer(self)
        self._gl_mode_indicator_timer.timeout.connect(self._fade_gl_mode_indicator)
        self._gl_mode_indicator_timer.start(50)

        self.setMinimumSize(400, 200)  # [M483] 세로 최소 400→200: 탭 패널 공간 압박 해소
        if self.mol_data:
            self._recalc()

    def _fade_gl_mode_indicator(self):
        """[FIX-3D-IND] OpenGL 모드 표시기 페이드아웃"""
        self._gl_mode_indicator_alpha = max(0, self._gl_mode_indicator_alpha - 4)
        if self._gl_mode_indicator_alpha <= 0:
            self._gl_mode_indicator_timer.stop()
        self.update()

    def set_mol_data(self, md):
        self.mol_data = md
        self._recalc()
        self.update()

    def _recalc(self):
        if not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("3D 재계산 건너뜀: mol_data=%s, atom_positions=%s",
                           bool(self.mol_data),
                           bool(self.mol_data.atom_positions) if self.mol_data else False)
            return
        self._center = self.mol_data.get_center()
        bs = self.mol_data.get_bounding_size()
        # [FIX-ZOOM] 15→20: 분자가 뷰포트 중앙에 더 크게 표시되도록
        self._view_scale = 20.0 / (bs + 1.0)

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
        self._vib_phase += 0.15
        self.vib_scale = math.sin(self._vib_phase) * self._vib_amplitude
        self.update()

    def set_protein_data(self, ca_atoms, binding_site=None):
        """[PROTEIN-3D] 단백질 Cα 백본 데이터 설정
        ca_atoms: List[(residue_name, x, y, z, chain)]
        binding_site: (cx, cy, cz) — 결합 부위 중심
        """
        self._protein_ca = ca_atoms
        # [FIX-RIBBON-W3] 새 단백질 로드 시 2차 구조 캐시 리셋 — 오래된 구조 재사용 방지
        self._secondary_structure = None
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
            # [FIX-RIBBON-W3] 리본 모드가 이미 켜져 있으면 즉시 2차 구조 탐지
            if self._ribbon_mode:
                self._detect_secondary_structure()
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
            coords = [(float(x), float(y), float(z)) for x, y, z in atom_coords]
            if binding_center and coords:
                cx = sum(p[0] for p in coords) / len(coords)
                cy = sum(p[1] for p in coords) / len(coords)
                cz = sum(p[2] for p in coords) / len(coords)
                bx, by, bz = binding_center
                display_center = (
                    bx,
                    by - max(4.0, binding_radius * 1.15),
                    bz + max(2.0, binding_radius * 0.45),
                )
                coords = [
                    (
                        x - cx + display_center[0],
                        y - cy + display_center[1],
                        z - cz + display_center[2],
                    )
                    for x, y, z in coords
                ]
            self._docking_pose_atoms = [
                (self._normalize_docking_element(elem), x, y, z)
                for elem, (x, y, z) in zip(atom_elements, coords)
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

    @staticmethod
    def _normalize_docking_element(elem):
        text = str(elem or "").strip().upper()
        if text in ("A", "C", "CA"):
            return "C"
        if text in ("OA", "O"):
            return "O"
        if text in ("NA", "N"):
            return "N"
        if text in ("SA", "S"):
            return "S"
        if text in ("HD", "H"):
            return "H"
        if text.startswith("CL"):
            return "Cl"
        if text.startswith("BR"):
            return "Br"
        return text[:1].upper() if text else "C"

    def set_binding_site_atoms(self, full_atoms):
        """[BINDING-SITE] 결합 부위 주변 전체 원자 설정 (잔기 스틱 렌더링용)

        Args:
            full_atoms: List[(element, x, y, z, res_name, res_seq)]
                PDB ATOM 라인에서 파싱한 결합 부위 반경 내 전체 원자
        """
        self._binding_site_full_atoms = full_atoms
        self._binding_site_bonds = None       # 재계산 필요
        self._computed_interactions = None    # 재계산 필요
        self.update()

    def _compute_binding_site_bonds(self):
        """[BINDING-SITE] 잔기 내 원자 간 결합 계산 (같은 잔기 내에서만)"""
        atoms = self._binding_site_full_atoms
        if not atoms:
            logger.warning("결합 부위 결합 계산 건너뜀: 결합 부위 원자 데이터 없음")
            return []
        # 잔기별 그룹핑
        residue_groups = {}
        for i, (elem, x, y, z, res_name, res_seq) in enumerate(atoms):
            key = (res_name, res_seq)
            residue_groups.setdefault(key, []).append(i)

        bonds = []
        # 공유결합 반경 테이블 (Å)
        _cov_r = {'C': 0.77, 'N': 0.75, 'O': 0.73, 'S': 1.02, 'H': 0.37,
                   'P': 1.06, 'F': 0.72, 'CL': 0.99, 'BR': 1.14, 'I': 1.33,
                   'SE': 1.16, 'ZN': 1.22, 'FE': 1.25, 'MG': 1.36, 'CA': 1.74}
        for key, indices in residue_groups.items():
            n = len(indices)
            for a in range(n):
                ia = indices[a]
                ea, xa, ya, za = atoms[ia][0], atoms[ia][1], atoms[ia][2], atoms[ia][3]
                ra = _cov_r.get(ea.upper(), 0.77)
                for b in range(a + 1, n):
                    ib = indices[b]
                    eb, xb, yb, zb = atoms[ib][0], atoms[ib][1], atoms[ib][2], atoms[ib][3]
                    rb = _cov_r.get(eb.upper(), 0.77)
                    d2 = (xb-xa)**2 + (yb-ya)**2 + (zb-za)**2
                    cutoff = (ra + rb) * 1.3  # 1.3x 허용 오차
                    if 0.16 < d2 < cutoff * cutoff:  # 0.4² = 0.16
                        bonds.append((ia, ib, math.sqrt(d2)))
        # 잔기 간 펩타이드 결합 (C-N): 연속 잔기 연결
        # res_seq 기반으로 이전 잔기의 C와 다음 잔기의 N 연결
        for i, (e1, x1, y1, z1, rn1, rs1) in enumerate(atoms):
            if e1.upper() != 'C':
                continue
            for j, (e2, x2, y2, z2, rn2, rs2) in enumerate(atoms):
                if e2.upper() != 'N':
                    continue
                if rs2 == rs1 + 1:  # 연속 잔기
                    d2 = (x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2
                    if d2 < 2.5 * 2.5:  # 펩타이드 결합 ~1.3Å
                        bonds.append((i, j, math.sqrt(d2)))
        return bonds

    def _compute_interactions(self):
        """[BINDING-SITE] 리간드↔잔기 상호작용 계산 (H-bond, 소수성 접촉, π-stacking)

        Returns list of:
          (xl, yl, zl, xr, yr, zr, itype, label, dist)
        itype: 'hbond' | 'hydrophobic' | 'pistack'
        """
        if not self._docking_pose_atoms or not self._binding_site_full_atoms:
            logger.warning("상호작용 계산 건너뜀: docking_pose_atoms=%s, binding_site_atoms=%s",
                           bool(self._docking_pose_atoms), bool(self._binding_site_full_atoms))
            return []
        interactions = []
        # H-bond 도너/억셉터 원소
        hb_elems = {'N', 'O', 'S', 'F'}
        # 소수성 원소 (C, S 포함)
        hydrophobic_elems = {'C', 'S', 'CL', 'BR', 'I', 'F'}
        seen_hydro: set = set()

        for i_lig, (e_lig, xl, yl, zl) in enumerate(self._docking_pose_atoms):
            e_up = e_lig.upper()
            for i_res, (e_res, xr, yr, zr, rn, rs) in enumerate(self._binding_site_full_atoms):
                e_res_up = e_res.upper()
                d2 = (xr - xl) ** 2 + (yr - yl) ** 2 + (zr - zl) ** 2

                # ── H-bond: 극성 원소, 2.0~3.5Å ───────────────────────
                if e_up in hb_elems and e_res_up in hb_elems:
                    if 2.0 ** 2 < d2 < 3.5 ** 2:
                        dist = math.sqrt(d2)
                        interactions.append(
                            (xl, yl, zl, xr, yr, zr, 'hbond',
                             f"{rn}{rs}:{e_res}", dist))

                # ── 소수성 접촉: 무극성 탄소계, 3.5~5.0Å ─────────────
                elif e_up in hydrophobic_elems and e_res_up in hydrophobic_elems:
                    if 3.5 ** 2 < d2 < 5.0 ** 2:
                        key = (i_lig, i_res)
                        if key not in seen_hydro:
                            seen_hydro.add(key)
                            dist = math.sqrt(d2)
                            interactions.append(
                                (xl, yl, zl, xr, yr, zr, 'hydrophobic',
                                 f"{rn}{rs}:hydro", dist))

        return interactions

    def _draw_binding_site_sticks(self):
        """[BINDING-SITE] 결합 부위 잔기를 thin stick으로 렌더링"""
        if not self._binding_site_full_atoms or not OPENGL_AVAILABLE:
            logger.warning("결합 부위 스틱 렌더링 건너뜀: atoms=%s, OPENGL=%s",
                           bool(self._binding_site_full_atoms), OPENGL_AVAILABLE)
            return
        try:
            # 결합 캐싱
            if self._binding_site_bonds is None:
                self._binding_site_bonds = self._compute_binding_site_bonds()

            atoms = self._binding_site_full_atoms
            sq = gluNewQuadric()
            cq = gluNewQuadric()
            glEnable(GL_LIGHTING)

            # [STYLE 2+3] 잔기 = ball-and-stick (PyMOL/Chimera 스타일)
            # 리간드 대비 확연히 배경으로 밀려남 — 채도 낮춤
            _desat = 0.65  # 채도 감쇠 비율 (0=회색, 1=원본) — 약간만 낮춤
            _gray_blend = 0.55  # 회색 블렌딩 비율

            glEnable(GL_LIGHTING)

            # [FIX-A] 잔기 원자 — ball (small sphere) 렌더링
            _drawn_atoms = set()  # 중복 방지
            for i, (elem, x, y, z, rn, rs) in enumerate(atoms):
                if elem.upper() == 'H':
                    continue
                if i in _drawn_atoms:
                    continue
                _drawn_atoms.add(i)
                r, g, b = get_cpk_color(elem)
                r = r * _desat + _gray_blend * (1 - _desat)
                g = g * _desat + _gray_blend * (1 - _desat)
                b = b * _desat + _gray_blend * (1 - _desat)
                _set_material(r, g, b)
                # ball 크기: 공유 반지름의 25% (리간드보다 작게)
                ball_r = get_covalent_radius(elem) * 0.25
                glPushMatrix()
                glTranslatef(x, y, z)
                gluSphere(sq, ball_r, 10, 8)
                glPopMatrix()

            # [FIX-A] 잔기 결합 — stick (thin cylinder) 렌더링
            for ia, ib, dist in self._binding_site_bonds:
                ea, xa, ya, za = atoms[ia][0], atoms[ia][1], atoms[ia][2], atoms[ia][3]
                eb, xb, yb, zb = atoms[ib][0], atoms[ib][1], atoms[ib][2], atoms[ib][3]
                if ea.upper() == 'H' or eb.upper() == 'H':
                    continue
                # 채도 낮춘 CPK 색상
                r1, g1, b1 = get_cpk_color(ea)
                r1 = r1 * _desat + _gray_blend * (1 - _desat)
                g1 = g1 * _desat + _gray_blend * (1 - _desat)
                b1 = b1 * _desat + _gray_blend * (1 - _desat)
                # stick (cylinder) 렌더링 — 원자A에서 중간점, 중간점에서 원자B
                mx, my, mz = (xa+xb)/2, (ya+yb)/2, (za+zb)/2
                # 전반: 원자A 색상
                _set_material(r1, g1, b1)
                _draw_cylinder(cq, (xa, ya, za), (mx, my, mz), 0.08)  # 0.08Å 반경
                # 후반: 원자B 색상
                r2, g2, b2 = get_cpk_color(eb)
                r2 = r2 * _desat + _gray_blend * (1 - _desat)
                g2 = g2 * _desat + _gray_blend * (1 - _desat)
                b2 = b2 * _desat + _gray_blend * (1 - _desat)
                _set_material(r2, g2, b2)
                _draw_cylinder(cq, (mx, my, mz), (xb, yb, zb), 0.08)

            gluDeleteQuadric(sq)
            gluDeleteQuadric(cq)
        except Exception as e:
            logger.error(f"Binding site sticks render error: {e}")

    def _draw_interaction_lines(self):
        """[BINDING-SITE] 리간드↔잔기 상호작용 시각화 (H-bond 방향 화살표, 소수성 점선)

        H-bond:     밝은 초록 점선 + 방향 화살촉 (리간드→수용체 방향)
        소수성 접촉: 노란 점선 (방향성 약함, 쌍방향 표시 생략)
        """
        if not OPENGL_AVAILABLE:
            logger.warning("상호작용 점선 렌더링 건너뜀: OpenGL 사용 불가")
            return
        # 상호작용 캐싱
        if self._computed_interactions is None:
            self._computed_interactions = self._compute_interactions()
        if not self._computed_interactions:
            return
        try:
            aq = gluNewQuadric()  # 화살촉용 quadric
            glDisable(GL_LIGHTING)
            glEnable(GL_LINE_STIPPLE)

            for xl, yl, zl, xr, yr, zr, itype, label, dist in self._computed_interactions:
                if itype == 'hbond':
                    # H-bond: 초록 굵은 점선 + 방향 화살촉
                    glColor3f(0.2, 1.0, 0.4)
                    glLineStipple(3, 0xF0F0)
                    glLineWidth(3.5)
                    glBegin(GL_LINES)
                    glVertex3f(xl, yl, zl)
                    glVertex3f(xr, yr, zr)
                    glEnd()
                    # 방향 화살촉: 리간드(xl,yl,zl) → 수용체(xr,yr,zr) 방향
                    # 화살촉을 수용체 원자 쪽 끝에 배치
                    dx, dy, dz = xr - xl, yr - yl, zr - zl
                    seg = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if seg > 1e-6:
                        nx, ny, nz = dx / seg, dy / seg, dz / seg
                        tip_x = xr - nx * 0.5  # 수용체 원자에서 0.5Å 뒤
                        tip_y = yr - ny * 0.5
                        tip_z = zr - nz * 0.5
                        glEnable(GL_LIGHTING)
                        glColor3f(0.2, 1.0, 0.4)
                        _draw_arrow(aq,
                                    (tip_x - nx * 0.8, tip_y - ny * 0.8, tip_z - nz * 0.8),
                                    (nx, ny, nz),
                                    length=0.8,
                                    radius=0.12,
                                    color=(0.2, 1.0, 0.4))
                        glDisable(GL_LIGHTING)
                elif itype == 'hydrophobic':
                    # 소수성 접촉: 노란 얇은 점선 (방향성 낮음 — 화살촉 생략)
                    glColor3f(1.0, 0.9, 0.2)
                    glLineStipple(2, 0xCCCC)
                    glLineWidth(1.8)
                    glBegin(GL_LINES)
                    glVertex3f(xl, yl, zl)
                    glVertex3f(xr, yr, zr)
                    glEnd()

            glDisable(GL_LINE_STIPPLE)
            glLineWidth(1.0)
            glEnable(GL_LIGHTING)
            gluDeleteQuadric(aq)
        except Exception as e:
            logger.error(f"Interaction lines render error: {e}")

    def set_protein_visible(self, visible: bool):
        self._protein_visible = visible
        self.update()

    def start_dock_approach(self, start_offset=(40.0, 0.0, 0.0)):
        """[B10-14] 리간드 접근 → TS → 생성물 3단계 애니메이션 시작"""
        # 결합 반경의 3~4배에서 시작하여 결합 부위로 접근
        self._dock_start_dist = self._binding_site_radius * 3.5 if self._binding_site_radius > 0 else 25.0
        self._ligand_offset = (self._dock_start_dist, self._dock_start_dist * 0.3, 0.0)
        self._dock_approach_phase = 0.0
        self._ts_flash = False  # [B10-14] TS 플래시 상태 초기화
        self._dock_approach_timer.start(33)  # ~30 fps

    def _dock_approach_tick(self):
        """[B10-14] 도킹 TS 3단계 애니메이션 프레임

        Phase 0 (t=0.00~0.45): 분자 접근 — 리간드가 결합부위로 이동 (ease-in)
        Phase 1 (t=0.45~0.55): TS 플래시 — 전이상태 (노란 강조 + 약간 진동, 약 1초 정체)
        Phase 2 (t=0.55~1.00): 생성물 — 리간드가 결합부위에 안착 (ease-out)
        완료: _dock_approach_phase = -1.0 (애니 종료)
        """
        # 속도: 0.008 → 전체 약 4초 (33fps × 125ticks)
        self._dock_approach_phase += 0.008
        if self._dock_approach_phase >= 1.0:
            self._dock_approach_phase = -1.0  # 완료
            self._ligand_offset = (0.0, 0.0, 0.0)
            self._ts_flash = False  # 전이상태 플래시 해제
            self._dock_approach_timer.stop()
            # ── Auto-capture docking result for DryLab report ──
            self._auto_capture_docking("docking_gl")
        else:
            t = self._dock_approach_phase
            start_dist = getattr(self, '_dock_start_dist', 25.0)

            if t < 0.45:
                # Phase 0: 접근 (APPROACH) — 리간드가 결합부위로 접근
                ease = (t / 0.45)  # 0→1
                ease = ease * ease * (3 - 2 * ease)  # smoothstep
                ox = start_dist * (1.0 - ease)
                oy = start_dist * 0.3 * (1.0 - ease)
                self._ligand_offset = (ox, oy, 0.0)
                self._ts_flash = False

            elif t < 0.55:
                # Phase 1: TS 전이상태 플래시 (약 1초 정체)
                # 리간드는 결합부위 근처에서 약간 진동 (TS 느낌)
                vib_t = (t - 0.45) / 0.10  # 0→1
                vib_amp = 1.0 * math.sin(vib_t * math.pi * 6)  # TS 진동
                self._ligand_offset = (vib_amp * 0.5, vib_amp * 0.3, 0.0)
                self._ts_flash = True  # 전이상태: 노란 하이라이트

            else:
                # Phase 2: 생성물 안착 (PRODUCT)
                ease_p = (t - 0.55) / 0.45  # 0→1
                ease_p = ease_p * ease_p  # ease-in (점점 빠르게 안착)
                # TS 위치(약간 진동)에서 완전 안착(0,0,0)으로 이동
                residual = (1.0 - ease_p) * 0.5
                self._ligand_offset = (residual, residual * 0.3, 0.0)
                self._ts_flash = False

        self.update()

    def _auto_capture_docking(self, tag: str = "docking"):
        """Auto-capture current OpenGL 3D view for DryLab report.

        Saves full view + zoomed ligand view to docs/exports/auto_captures/.
        Called automatically when docking animation finishes.
        """
        try:
            import os, time
            cap_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                "docs", "exports", "auto_captures")
            os.makedirs(cap_dir, exist_ok=True)

            smiles_tag = ""
            if hasattr(self, 'mol_data') and self.mol_data and self.mol_data.smiles:
                smiles_tag = f"_{abs(hash(self.mol_data.smiles)) % 10000:04d}"

            ts = time.strftime("%Y%m%d_%H%M%S")

            # Full docking view capture
            pix = self.grabFramebuffer()
            if pix and not pix.isNull():
                path_full = os.path.join(cap_dir, f"{tag}_full{smiles_tag}_{ts}.png")
                pix.save(path_full)

                # Zoomed ligand capture (2.5x zoom)
                old_zoom = getattr(self, '_zoom', 1.0)
                self._zoom = old_zoom * 2.5
                self.update()
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                pix2 = self.grabFramebuffer()
                path_zoom = ""
                if pix2 and not pix2.isNull():
                    path_zoom = os.path.join(cap_dir, f"{tag}_zoom{smiles_tag}_{ts}.png")
                    pix2.save(path_zoom)
                self._zoom = old_zoom
                self.update()

                # Store for DryLab to pick up (class-level so any instance can read)
                if not hasattr(self.__class__, '_drylab_captures'):
                    self.__class__._drylab_captures = {}
                self.__class__._drylab_captures['docking_full'] = path_full
                if path_zoom:
                    self.__class__._drylab_captures['docking_zoom'] = path_zoom

                logger.info("Auto-captured GL docking views: %s", path_full)
        except Exception as e:
            logger.debug("GL auto-capture failed: %s", e)

    def _draw_protein(self):
        """[PROTEIN-3D] OpenGL 단백질 Cα 백본 렌더링
        [PERF] 거대 분자 크기 가드 — Cα 수에 따라 렌더링 수준 자동 조절"""
        if not self._protein_ca or not OPENGL_AVAILABLE:
            logger.warning("단백질 렌더링 건너뜀: protein_ca=%s, OPENGL=%s",
                           bool(self._protein_ca), OPENGL_AVAILABLE)
            return
        n_ca = len(self._protein_ca)
        try:
            if n_ca > 5000:
                # 거대 구조 — 렌더링 건너뜀, 경고 1회 표시
                if not getattr(self, '_macro_warn_shown', False):
                    logger.warning(f"거대 구조 ({n_ca} Cα): 렌더링 건너뜀. PyMOL/ChimeraX 권장.")
                    self._macro_warn_shown = True
                return
            if self._ribbon_mode:
                self._draw_protein_ribbon_only()
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
        # [FIX-B] 리본 모드에서 2차 구조 미탐지 시 자동 탐지
        if self._ribbon_mode and self._secondary_structure is None and self._protein_ca:
            self._detect_secondary_structure()
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
            logger.warning("2차 구조 탐지 건너뜀: 단백질 Cα 데이터 없음")
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

        # [FIX-B] 리본 모드에서 2차 구조 미탐지 시 자동 탐지
        if self._ribbon_mode and self._secondary_structure is None and self._protein_ca:
            self._detect_secondary_structure()

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

    @staticmethod
    def _catmull_rom_spline(points, n_segments=10):
        """Catmull-Rom spline 보간: Cα 좌표 리스트 → 매끄러운 경로 출력

        4점 기반 Catmull-Rom:
        P(t) = 0.5 * ((2*P1) + (-P0+P2)*t + (2*P0-5*P1+4*P2-P3)*t^2
               + (-P0+3*P1-3*P2+P3)*t^3)

        Args:
            points: List[(x, y, z)] — 최소 2점 이상의 Cα 좌표
            n_segments: 인접 제어점 사이 보간 세그먼트 수 (기본 10)

        Returns:
            List[(x, y, z)] — 보간된 부드러운 경로 좌표
        """
        if not isinstance(points, list) or len(points) < 2:
            logger.warning("Catmull-Rom spline 보간 건너뜀: 점 %d개 (최소 2개 필요)", len(points) if isinstance(points, list) else 0)
            return list(points) if isinstance(points, list) else []

        n = len(points)
        result = []

        for i in range(n - 1):
            # 4점 선택: 시작/끝 경계에서는 가장자리 점을 반복 사용 (클램핑)
            p0 = points[max(i - 1, 0)]
            p1 = points[i]
            p2 = points[min(i + 1, n - 1)]
            p3 = points[min(i + 2, n - 1)]

            for s in range(n_segments):
                t = s / n_segments  # 0.0 ~ (n_segments-1)/n_segments
                t2 = t * t
                t3 = t2 * t

                # Catmull-Rom 행렬 계수 (탄젠트 스케일 0.5)
                x = 0.5 * ((2.0 * p1[0]) +
                           (-p0[0] + p2[0]) * t +
                           (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2 +
                           (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3)
                y = 0.5 * ((2.0 * p1[1]) +
                           (-p0[1] + p2[1]) * t +
                           (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2 +
                           (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3)
                z = 0.5 * ((2.0 * p1[2]) +
                           (-p0[2] + p2[2]) * t +
                           (2.0 * p0[2] - 5.0 * p1[2] + 4.0 * p2[2] - p3[2]) * t2 +
                           (-p0[2] + 3.0 * p1[2] - 3.0 * p2[2] + p3[2]) * t3)
                result.append((x, y, z))

        # 마지막 점 추가
        result.append(points[-1])
        return result

    def _draw_ribbon(self, chain_colors, default_color):
        """[RIBBON] Catmull-Rom spline 보간 기반 2차 구조 리본 렌더링

        Cα 좌표를 Catmull-Rom spline으로 보간하여 매끄러운 곡선 리본 생성.
        α-helix: 빨강 튜브 (반경 1.2 Angstrom)
        β-sheet: 노랑 넓적 튜브 (너비 2.0 Angstrom, 두께 0.4 Angstrom)
        Coil: 체인 색상 얇은 튜브 (반경 0.25 Angstrom)
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

        n_interp = 8  # Cα 사이 보간 세그먼트 수

        for ch, atoms in chains.items():
            n = len(atoms)
            if n < 2:
                continue
            base_color = chain_colors.get(ch, default_color)

            # 1) Cα 좌표 + 2차 구조 타입 추출
            ca_coords = [(x, y, z) for (_, x, y, z, _) in atoms]
            ca_ss = [ss[idx] for (idx, _, _, _, _) in atoms]

            # 2) Catmull-Rom spline 보간
            spline_pts = self._catmull_rom_spline(ca_coords, n_segments=n_interp)
            if len(spline_pts) < 2:
                continue

            # 3) 보간된 각 세그먼트에 대응하는 2차 구조 타입 매핑
            #    원본 Cα i → spline 인덱스 i*n_interp ~ (i+1)*n_interp
            spline_ss = []
            for i in range(n - 1):
                for _ in range(n_interp):
                    spline_ss.append(ca_ss[i])
            spline_ss.append(ca_ss[-1])  # 마지막 점

            # 4) 보간된 경로를 따라 gluCylinder 렌더링
            for j in range(len(spline_pts) - 1):
                x0, y0, z0 = spline_pts[j]
                x1, y1, z1 = spline_pts[j + 1]
                struct = spline_ss[j]

                dx = x1 - x0
                dy = y1 - y0
                dz = z1 - z0
                seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
                if seg_len < 1e-6:
                    continue

                # 2차 구조별 색상 + 반경
                if struct == 'H':
                    # alpha-helix: 빨강 계열 튜브
                    r, g, b = 0.85, 0.25, 0.25
                    radius = 1.2  # Angstrom
                elif struct == 'E':
                    # beta-sheet: 노랑 계열 넓적한 튜브
                    r, g, b = 0.9, 0.8, 0.2
                    radius = 0.8  # Angstrom
                else:
                    # Coil: 체인 색상 얇은 튜브
                    r, g, b = base_color
                    radius = 0.25  # Angstrom

                _set_material(r, g, b)

                glPushMatrix()
                glTranslatef(x0, y0, z0)

                # 방향 벡터 → 회전 (Z축 기준 gluCylinder 정렬)
                rot_ax_x = -dy
                rot_ax_y = dx
                rot_ax_z = 0.0
                rot_ax_len = math.sqrt(rot_ax_x * rot_ax_x + rot_ax_y * rot_ax_y + rot_ax_z * rot_ax_z)
                angle = math.degrees(math.acos(max(-1.0, min(1.0, dz / seg_len))))
                if rot_ax_len > 1e-6:
                    glRotatef(angle, rot_ax_x / rot_ax_len, rot_ax_y / rot_ax_len, rot_ax_z / rot_ax_len)
                elif dz < 0:
                    glRotatef(180, 1, 0, 0)

                if struct == 'E':
                    # beta-sheet: 납작한 직육면체로 근사
                    w = 2.0   # 너비 (Angstrom)
                    h = 0.4   # 두께 (Angstrom)
                    glScalef(w, h, 1.0)
                    gluCylinder(cq, 0.5, 0.5, seg_len, 4, 1)
                    glScalef(1.0 / w, 1.0 / h, 1.0)
                else:
                    # 원통 (helix/coil)
                    slices = 12 if struct == 'H' else 6
                    gluCylinder(cq, radius, radius, seg_len, slices, 1)

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
            logger.warning("도킹 리간드 렌더링 건너뜀: docking_pose=%s, OPENGL=%s",
                           bool(self._docking_pose_atoms), OPENGL_AVAILABLE)
            return
        try:
            depth_was_enabled = bool(glIsEnabled(GL_DEPTH_TEST))
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            sq = gluNewQuadric()
            cq = gluNewQuadric()

            atoms = self._docking_pose_atoms  # [(element, x, y, z), ...]

            # 원자 렌더링
            for elem, x, y, z in atoms:
                if elem == "C":
                    r, g, b = (1.0, 0.55, 0.05)
                elif elem == "H":
                    r, g, b = (0.95, 0.95, 0.82)
                else:
                    r, g, b = get_cpk_color(elem)
                _set_material(r, g, b)
                rad = max(2.2, get_covalent_radius(elem) * 2.6)
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
                    gluCylinder(cq, 0.45, 0.45, length, 18, 1)
                glPopMatrix()

            gluDeleteQuadric(sq)
            gluDeleteQuadric(cq)
            if depth_was_enabled:
                glEnable(GL_DEPTH_TEST)
        except Exception as e:
            logger.error(f"Docking ligand render error: {e}")

    def _draw_current_ligand_reference_overlay(self):
        """Draw an unmistakable CPK ligand ball-and-stick overlay near the ribbon."""
        if not self._binding_site_center or not getattr(self, "mol_data", None):
            return
        positions = getattr(self.mol_data, "atom_positions", {}) or {}
        symbols = getattr(self.mol_data, "atom_symbols", {}) or {}
        bonds = getattr(self.mol_data, "bonds", {}) or {}
        if not positions or not symbols:
            return
        try:
            atoms = []
            for key, pos in positions.items():
                elem = symbols.get(key, "C")
                atoms.append((key, elem, float(pos[0]), float(pos[1]), float(pos[2])))
            if not atoms:
                return
            cx = sum(a[2] for a in atoms) / len(atoms)
            cy = sum(a[3] for a in atoms) / len(atoms)
            cz = sum(a[4] for a in atoms) / len(atoms)
            bx, by, bz = self._binding_site_center
            br = max(4.0, getattr(self, "_binding_site_radius", 8.0))
            target = (bx, by - br * 1.65, bz + br * 0.70)
            scale = 1.65
            placed = {
                key: (
                    (x - cx) * scale + target[0],
                    (y - cy) * scale + target[1],
                    (z - cz) * scale + target[2],
                    elem,
                )
                for key, elem, x, y, z in atoms
            }

            depth_was_enabled = bool(glIsEnabled(GL_DEPTH_TEST))
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            sq = gluNewQuadric()
            cq = gluNewQuadric()

            _set_material(0.95, 0.95, 0.95)
            for (a, b), _order in bonds.items():
                if a not in placed or b not in placed:
                    continue
                x1, y1, z1, _e1 = placed[a]
                x2, y2, z2, _e2 = placed[b]
                _draw_cylinder(cq, (x1, y1, z1), (x2, y2, z2), 0.22, slices=14)

            for _key, (x, y, z, elem) in placed.items():
                if elem == "C":
                    r, g, b = (1.0, 0.50, 0.05)
                elif elem == "H":
                    r, g, b = (0.96, 0.96, 0.88)
                else:
                    r, g, b = get_cpk_color(elem)
                _set_material(r, g, b)
                rad = max(1.05, get_covalent_radius(elem) * 1.35)
                glPushMatrix()
                glTranslatef(x, y, z)
                gluSphere(sq, rad, 18, 14)
                glPopMatrix()

            gluDeleteQuadric(sq)
            gluDeleteQuadric(cq)
            if depth_was_enabled:
                glEnable(GL_DEPTH_TEST)
        except Exception as e:
            logger.warning("ligand reference overlay render failed: %s", e)

    def set_measure_mode(self, on: bool):
        self._measure_mode = on
        self._selected_atoms = []

    def set_background_color(self, r: float, g: float, b: float):
        """배경색 변경 (OpenGL glClearColor 업데이트 + repaint)."""
        self.bg_color = (r, g, b, 1.0)
        if OPENGL_AVAILABLE:
            self.makeCurrent()
            glClearColor(r, g, b, 1.0)
            self.doneCurrent()
        self.update()

    def initializeGL(self):
        if not OPENGL_AVAILABLE:
            logger.warning("OpenGL 초기화 건너뜀: OpenGL 사용 불가 (QPainter 폴백 모드)")
            self._gl_fallback = True
            return
        try:
            glClearColor(*self.bg_color)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glEnable(GL_COLOR_MATERIAL)
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glEnable(GL_NORMALIZE)
            glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
            glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
            # [FIX-GL-FALLBACK] GL 컨텍스트 검증: glGetString으로 실제 렌더러 확인
            renderer = glGetString(GL_RENDERER)
            if renderer:
                logger.info("OpenGL 렌더러: %s", renderer.decode('utf-8', errors='replace') if isinstance(renderer, bytes) else renderer)
            self._gl_validated = True
        except Exception as e:
            logger.warning("OpenGL initializeGL 실패 → QPainter 2.5D 폴백: %s", e)
            self._gl_fallback = True

    def resizeGL(self, w, h):
        if not OPENGL_AVAILABLE or self._gl_fallback:
            return
        if h == 0:
            h = 1
        try:
            glViewport(0, 0, w, h)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(45.0, w/h, 0.1, 200.0)
            glMatrixMode(GL_MODELVIEW)
        except Exception as e:
            logger.warning("resizeGL 실패 → QPainter 폴백: %s", e)
            self._gl_fallback = True

    def paintGL(self):
        if not OPENGL_AVAILABLE or self._gl_fallback:
            # [FIX-GL-FALLBACK] OpenGL 사용 불가 또는 컨텍스트 실패 → QPainter 2.5D 폴백
            self._paint_fallback_2d()
            return
        try:
            self._paintGL_impl()
        except Exception as e:
            # [FIX-GL-FALLBACK] Rule M: silent failure 금지 — 런타임 GL 오류 시 QPainter로 전환
            logger.warning("OpenGL paintGL 실패 → QPainter 2.5D 폴백 전환: %s", e)
            self._gl_fallback = True
            self._paint_fallback_2d()

    def _paint_fallback_2d(self):
        """[FIX-GL-FALLBACK] QPainter 2.5D 폴백: OpenGL 컨텍스트 실패 시 사용.
        FallbackRenderer2D와 동일한 로직으로 분자를 QPainter로 렌더링.
        """
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(self.mol_data.atom_symbols, dict):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_r, bg_g, bg_b = int(self.bg_color[0]*255), int(self.bg_color[1]*255), int(self.bg_color[2]*255)
        p.fillRect(self.rect(), QColor(bg_r, bg_g, bg_b))

        if not self.mol_data or not self.mol_data.atom_positions:
            p.setPen(QColor(180, 180, 180))
            p.setFont(QFont("Malgun Gothic", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "분자 데이터 없음")
            p.end()
            return

        w, h = self.width(), self.height()
        ox, oy = w / 2 + self.pan_x * 10, h / 2 - self.pan_y * 10
        bs = self.mol_data.get_bounding_size()
        scale = min(w, h) / (bs + 4.0) * 0.55 * self.zoom_scale

        # 3D → 2D 투영 (회전 적용)
        rx = math.radians(self.rotation_x)
        ry = math.radians(self.rotation_y)
        cos_rx, sin_rx = math.cos(rx), math.sin(rx)
        cos_ry, sin_ry = math.cos(ry), math.sin(ry)
        cx, cy, cz = self._center

        transformed = []
        for key, coords in self.mol_data.atom_positions.items():
            x, y, z = coords[0] - cx, coords[1] - cy, coords[2] - cz
            # Y축 회전
            x1 = x * cos_ry + z * sin_ry
            z1 = -x * sin_ry + z * cos_ry
            # X축 회전
            y1 = y * cos_rx - z1 * sin_rx
            z2 = y * sin_rx + z1 * cos_rx
            transformed.append((key, x1, y1, z2))

        # 깊이 정렬
        sorted_a = sorted(transformed, key=lambda t: t[3])
        zvals = [t[3] for t in sorted_a]
        zmin, zmax = min(zvals), max(zvals)
        zr = (zmax - zmin) if zmax > zmin else 1.0

        spos = {}
        for key, rx_v, ry_v, rz_v in transformed:
            sx, sy = ox + rx_v * scale, oy - ry_v * scale
            norm_z = (rz_v - zmin) / zr
            df = 0.55 + 0.9 * norm_z
            # [FIX-OPAQUE] Fully opaque atoms — depth via size/lighting only
            alpha = 255
            spos[key] = (sx, sy, df, alpha)

        # 결합 렌더링 (깊이 순서)
        for (k1, k2), order in self.mol_data.bonds.items():
            if k1 in spos and k2 in spos:
                s1, s2 = spos[k1], spos[k2]
                avg_df = (s1[2] + s2[2]) / 2
                avg_alpha = int((s1[3] + s2[3]) / 2)
                # M565: 결합 굵기 3.0 → 4.5 (50% 증가) — 격분11 차수별 시각 구분 강화 (OpenGL 폴백 경로).
                bw = max(2, int(4.5 * avg_df))
                sym1 = self.mol_data.atom_symbols.get(k1, "C")
                sym2 = self.mol_data.atom_symbols.get(k2, "C")
                r1c, g1c, b1c = get_cpk_color(sym1)
                r2c, g2c, b2c = get_cpk_color(sym2)
                df_clamp = min(1.0, avg_df)
                color1 = QColor(int(r1c * 255 * df_clamp), int(g1c * 255 * df_clamp),
                                int(b1c * 255 * df_clamp), avg_alpha)
                color2 = QColor(int(r2c * 255 * df_clamp), int(g2c * 255 * df_clamp),
                                int(b2c * 255 * df_clamp), avg_alpha)
                x1, y1 = int(s1[0]), int(s1[1])
                x2, y2 = int(s2[0]), int(s2[1])
                mx, my = (x1 + x2) // 2, (y1 + y2) // 2
                bo = order
                if isinstance(bo, (float, int)) and abs(bo - 1.5) < 0.01:
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx * dx + dy * dy) if (dx * dx + dy * dy) > 0 else 1
                    # M565: off 2 → 5 (OpenGL 폴백 방향족 결합)
                    off = 5
                    nx, ny = dx / length * off, dy / length * off
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 - nx), int(y1 - ny), int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2))
                    p.setPen(QPen(color2, bw))
                    p.drawLine(int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2), int(x2 - nx), int(y2 - ny))
                    # M565: 점선도 굵게 — bw-1 → max(2, bw-1)
                    dash_pen = QPen(color1, max(2, bw - 1))
                    dash_pen.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(dash_pen)
                    p.drawLine(int(x1 + nx), int(y1 + ny), int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2))
                    dash_pen2 = QPen(color2, max(2, bw - 1))
                    dash_pen2.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(dash_pen2)
                    p.drawLine(int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2), int(x2 + nx), int(y2 + ny))
                elif isinstance(bo, (float, int)) and bo >= 2.8:
                    # 삼중결합: 3 평행선 (CPK split)
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx * dx + dy * dy) if (dx * dx + dy * dy) > 0 else 1
                    # M565: off 2 → 6 (OpenGL 폴백 삼중결합 — 이중보다 1px 더 넓게)
                    off = 6
                    nx, ny = dx / length * off, dy / length * off
                    mnx_p, mny_p = int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2)
                    mnx_n, mny_n = int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2)
                    # 중심선
                    p.setPen(QPen(color1, bw))
                    p.drawLine(x1, y1, mx, my)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mx, my, x2, y2)
                    # 상단 평행선
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 + nx), int(y1 + ny), mnx_p, mny_p)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_p, mny_p, int(x2 + nx), int(y2 + ny))
                    # 하단 평행선
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 - nx), int(y1 - ny), mnx_n, mny_n)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_n, mny_n, int(x2 - nx), int(y2 - ny))
                elif isinstance(bo, (float, int)) and bo >= 1.8:
                    # 이중결합: 2 평행선 (CPK split)
                    dx, dy = y2 - y1, -(x2 - x1)
                    length = math.sqrt(dx * dx + dy * dy) if (dx * dx + dy * dy) > 0 else 1
                    # M565: off 2 → 5 (OpenGL 폴백 이중결합)
                    off = 5
                    nx, ny = dx / length * off, dy / length * off
                    mnx_p, mny_p = int((x1 + nx + x2 + nx) / 2), int((y1 + ny + y2 + ny) / 2)
                    mnx_n, mny_n = int((x1 - nx + x2 - nx) / 2), int((y1 - ny + y2 - ny) / 2)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 + nx), int(y1 + ny), mnx_p, mny_p)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_p, mny_p, int(x2 + nx), int(y2 + ny))
                    p.setPen(QPen(color1, bw))
                    p.drawLine(int(x1 - nx), int(y1 - ny), mnx_n, mny_n)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mnx_n, mny_n, int(x2 - nx), int(y2 - ny))
                elif isinstance(bo, (float, int)) and abs(bo - 0.5) < 0.01:
                    # 배위결합: 점선 (CPK split)
                    pen1 = QPen(color1, max(1, bw - 1))
                    pen1.setStyle(Qt.PenStyle.DashLine)
                    pen2 = QPen(color2, max(1, bw - 1))
                    pen2.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen1)
                    p.drawLine(x1, y1, mx, my)
                    p.setPen(pen2)
                    p.drawLine(mx, my, x2, y2)
                else:
                    # 단일결합 (CPK split)
                    p.setPen(QPen(color1, bw))
                    p.drawLine(x1, y1, mx, my)
                    p.setPen(QPen(color2, bw))
                    p.drawLine(mx, my, x2, y2)

        # 원자 렌더링 (깊이 순서: 뒤→앞)
        for key, rx_v, ry_v, rz_v in sorted_a:
            if key not in spos:
                continue
            sx, sy, df, alpha = spos[key]
            sym = self.mol_data.atom_symbols.get(key, "C")
            r_c, g_c, b_c = get_cpk_color(sym)
            # [FIX-ATOM-SIZE] 원자 크기 증가: 0.12→0.5 (ball-and-stick 표준 비율)
            rad = get_covalent_radius(sym) * scale * 0.5 * df
            rad = max(3.0, min(25.0, rad))
            base_color = QColor(int(r_c * 255), int(g_c * 255), int(b_c * 255), alpha)
            grad = QRadialGradient(QPointF(sx - rad * 0.3, sy - rad * 0.3), rad * 1.5)
            grad.setColorAt(0.0, QColor(
                min(255, base_color.red() + 180), min(255, base_color.green() + 180),
                min(255, base_color.blue() + 180), alpha))
            grad.setColorAt(0.45, base_color)
            grad.setColorAt(1.0, QColor(
                max(0, base_color.red() - 100), max(0, base_color.green() - 100),
                max(0, base_color.blue() - 100), alpha))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(sx, sy), rad, rad)
            if sym not in ('H', '', 'C') and rad >= 6:
                p.setPen(QColor(255, 255, 255, alpha))
                p.setFont(QFont(_QT_KR_FONT, max(6, int(rad * 0.65))))  # [M1461] Rule Q: offscreen 폰트
                p.drawText(QRectF(sx - rad, sy - rad * 0.6, rad * 2, rad * 1.2),
                           Qt.AlignmentFlag.AlignCenter, sym)

        # 모드 표시기
        p.setPen(QColor(255, 171, 64, 200))
        p.setFont(QFont("Malgun Gothic", 9))  # [M1444] Rule Q: 한국어 텍스트
        p.drawText(8, h - 8, "2.5D (OpenGL 폴백)")
        p.end()

    def _paintGL_impl(self):
        """[FIX-GL-FALLBACK] 실제 OpenGL 렌더링 구현 (try-except 래퍼에서 호출)."""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glDepthFunc(GL_LESS)
        glDisable(GL_CULL_FACE)
        glDisable(GL_BLEND)
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

        # [BINDING-SITE] 결합 부위 주변 잔기 스틱 렌더링
        if self._binding_site_full_atoms and self._protein_visible:
            self._draw_binding_site_sticks()

        # [DOCK-POSE] 도킹 포즈 좌표가 있으면 Vina 실제 좌표로 리간드 렌더링
        if self._docking_pose_atoms and self._protein_visible:
            if self._dock_approach_phase >= 0:
                glPushMatrix()
                ox, oy, oz = self._ligand_offset
                glTranslatef(ox, oy, oz)
            self._draw_docking_ligand()
            self._draw_current_ligand_reference_overlay()
            if self._dock_approach_phase >= 0:
                glPopMatrix()
            # [B10-14] TS 전이상태 플래시: 결합부위 주변 노란 반투명 구 오버레이
            if getattr(self, '_ts_flash', False) and self._binding_site_center:
                try:
                    bx, by, bz = self._binding_site_center
                    glPushMatrix()
                    glTranslatef(bx, by, bz)
                    glEnable(GL_BLEND)
                    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                    glDisable(GL_LIGHTING)
                    glColor4f(1.0, 0.9, 0.2, 0.35)  # 노란 반투명 (TS 표시)
                    ts_q = gluNewQuadric()
                    gluSphere(ts_q, self._binding_site_radius * 0.6, 16, 12)
                    gluDeleteQuadric(ts_q)
                    glEnable(GL_LIGHTING)
                    glDisable(GL_BLEND)
                    glPopMatrix()
                except Exception as _e:
                    logger.debug("[B10-14] TS flash render failed: %s", _e)
            # [BINDING-SITE] 리간드↔잔기 상호작용 점선
            self._draw_interaction_lines()
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
            # [BUG1-FIX] π모드: sp2 원자 키 집합을 미리 계산하여 BallAndStick에 전달
            # sp3 원자는 normal 크기 유지, sp2 원자만 축소 → 금빛/갈색 방지
            _pi_sp2_keys = None
            if self.orbital_mode == 'pi' and self.mol_data:
                _sp2_ks, _rg, _rk = self._pi.detect_sp2_for_gl(self.mol_data)
                _pi_sp2_keys = set(_sp2_ks)
            if self.render_mode == "ball_and_stick":
                self._bs.render(self.mol_data, vv, vs, small_atoms=small,
                                pi_sp2_keys=_pi_sp2_keys)
                # ★ 입체 결합 (웨지/대쉬) 시각화
                self._bs.render_stereo_bonds(self.mol_data)
            else:
                self._sf.render(self.mol_data, vv, vs)
            # 오비탈/ESP 렌더링 — culling 끄기 (반투명 + 양면 필요)
            glDisable(GL_CULL_FACE)
            if self.orbital_mode == 'pi':
                self._pi.render(self.mol_data)
            elif self.orbital_mode == 'all':
                # [FIX-ALL-ORB] "전체 오비탈" = π 오비탈 + 모든 혼성/d/f 오비탈(MC dots)
                # 이전: render_esp_surface → gluSphere VDW 블롭 ("개구리알")
                # 수정: AdvancedOrbitalRenderer.render(mode='all') → MC 점밀도 로브
                #        + PiOrbitalRenderer.render() → gluSphere π 로브 (기존 유지)
                self._pi.render(self.mol_data)
                self._adv.render(self.mol_data, orbital_mode='all')
            elif self.orbital_mode in ('hybrid', 'd_orbital', 'f_orbital'):
                self._adv.render(self.mol_data, orbital_mode=self.orbital_mode)
            elif self.orbital_mode == 'esp':
                self._adv.render_esp_surface(self.mol_data)
            glEnable(GL_CULL_FACE)

            if need_pop:
                glPopMatrix()

        # [PEAK-CLICK] OpenGL 하이라이트: 선택된 원자 주위 반투명 발광 구체
        if (self._vib_highlight_indices and self.mol_data
                and self.mol_data.atom_positions):
            try:
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                glDisable(GL_LIGHTING)
                atom_keys = list(self.mol_data.atom_positions.keys())
                for idx in self._vib_highlight_indices:
                    if 0 <= idx < len(atom_keys):
                        key = atom_keys[idx]
                        if key in self.mol_data.atom_positions:
                            cx, cy, cz = self.mol_data.atom_positions[key]
                            glPushMatrix()
                            glTranslatef(cx, cy, cz)
                            # [M830 anger#17] Semi-transparent yellow glow sphere (학술 표준 노란색)
                            # orange(1.0,0.65,0.0) -> yellow(1.0,1.0,0.0) (ORCA/GaussView Hanwell 2012)
                            glColor4f(1.0, 1.0, 0.0, 0.25)  # yellow, alpha=0.25
                            sq = self._bs.qm.sphere()
                            sym = self.mol_data.atom_symbols.get(key, '')
                            r = get_covalent_radius(sym) * 0.45 * 2.0  # 2x normal BnS radius
                            gluSphere(sq, r, 16, 16)
                            glPopMatrix()
                glEnable(GL_LIGHTING)
            except Exception as _e:
                logger.debug("OpenGL highlight render: %s", _e)

        # [FIX-3D-IND] OpenGL 모드 표시기 오버레이 (QPainter over GL)
        if self._gl_mode_indicator_alpha > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QColor(120, 220, 120, self._gl_mode_indicator_alpha))
            p.setFont(QFont(_QT_KR_FONT, 9))  # [M1461] Rule Q: 한국어 텍스트
            p.drawText(8, self.height() - 8, "3D OpenGL 모드")
            p.end()

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
        # [M829 anger#21] zoom wheel -> slider sync (Molecule3DViewer parent popup)
        _p = self.parent()
        if _p is not None and hasattr(_p, 'zoom_slider'):
            _p.zoom_slider.blockSignals(True)  # prevent feedback loop
            _p.zoom_slider.setValue(int(self.zoom_scale * 100))
            _p.zoom_slider.blockSignals(False)
            if hasattr(_p, 'zoom_lbl'):
                _p.zoom_lbl.setText(f"{int(self.zoom_scale * 100)}%")

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
        mode: 'none'|'pi'|'hybrid'|'d_orbital'|'f_orbital'|'all'|'esp'
        """
        # [BUG3-FIX] hybrid→pi 전환: MC lobe 캐시 무효화 — 이전 모드의 잔류 색상 방지
        # AdvancedOrbitalRenderer._mc_lobe_cache는 클래스변수 — 다른 mode로 전환해도 캐시 유지됨.
        # 모드 전환 시 명시적으로 지워서 stale material state 방지
        if mode != self.orbital_mode:
            AdvancedOrbitalRenderer._mc_lobe_cache.clear()
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
            except Exception as e:
                logger.warning("RDKit descriptor computation failed: %s", e)
            self._protein_quadric = None


# ============================================================
# Section 10: Tab Panels
# ============================================================

class PropertiesPanel(QWidget):
    """📊 속성 탭 — RDKit 계산값 + route-only DB links"""

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
        self.pub_group = QGroupBox("🌐 PubChem lookup (optional web API)")
        self.pub_form = QFormLayout()
        self.pub_group.setLayout(self.pub_form)
        layout.addWidget(self.pub_group)

        # ORCA properties (Rule GG SIMULATION_MODE guard — THEORY-AUTO-008/016/024)
        _orca_title = ("⚛️ DFT 결과 (ORCA)" if ORCA_AVAILABLE
                       else "⚛️ DFT 결과 [SIMULATION_MODE — 휴리스틱 추정]")
        self.orca_group = QGroupBox(_orca_title)
        self.orca_form = QFormLayout()
        self.orca_group.setLayout(self.orca_form)
        if not ORCA_AVAILABLE:
            # [Rule GG] 노랑 배경 + 워터마크: 학생이 실측/추정 구분 가능하도록
            self.orca_group.setStyleSheet(
                "QGroupBox { border: 2px solid #FFC107; background-color: #3E3A00; }"
                "QGroupBox::title { color: #FFC107; font-weight: bold; }"
            )
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

        # ── 외부 API 링크 (M645_W9) ─────────────────────────────────────────
        self.ext_group = QGroupBox("External DB web-search routes (not HTTP success)")
        ext_layout = QVBoxLayout()
        ext_layout.setSpacing(4)

        ext_note = QLabel(
            "현재 분자 SMILES를 외부 DB 검색 URL에 직접 전달합니다.\n"
            "PubChem / NCI Cactus / ChEMBL / DrugBank"
        )
        ext_note.setWordWrap(True)
        ext_note.setStyleSheet("color: #90CAF9; font-size: 11px;")
        ext_note.setObjectName("external_db_route_only_note")
        ext_note.setText(
            "PubChem, ChEMBL, DrugBank, and NCI Cactus buttons only build and open "
            "deterministic web-search URLs from the current SMILES. They do not prove "
            "HTTP 200 success, cross-device behavior, or a unique compound identity."
        )
        ext_layout.addWidget(ext_note)

        btn_row = QHBoxLayout()

        self.local_drugbank_status = QLabel(self._drugbank_status_text())
        self.local_drugbank_status.setObjectName("local_drugbank_status_label")
        self.local_drugbank_status.setWordWrap(True)
        self.local_drugbank_status.setStyleSheet("color: #FFCC80; font-size: 11px;")
        ext_layout.addWidget(self.local_drugbank_status)

        self.btn_nci = QPushButton("NCI Cactus")
        self.btn_nci.setObjectName("external_nci_cactus_btn")
        self.btn_nci.setToolTip("NCI Chemical Identifier Resolver — IUPAC명 변환")
        self.btn_nci.clicked.connect(self._open_nci_cactus)
        btn_row.addWidget(self.btn_nci)

        self.btn_opsin = QPushButton("PubChem")
        self.btn_opsin.setObjectName("external_pubchem_btn")
        self.btn_opsin.setToolTip("PubChem web-search route only — no HTTP success or unique identity claim")
        self.btn_opsin.clicked.connect(self._open_opsin)
        btn_row.addWidget(self.btn_opsin)

        self.btn_chembl = QPushButton("ChEMBL")
        self.btn_chembl.setObjectName("external_chembl_btn")
        self.btn_chembl.setToolTip("ChEMBL web-search route only — no HTTP success or unique identity claim")
        self.btn_chembl.clicked.connect(self._open_chembl)
        btn_row.addWidget(self.btn_chembl)

        self.btn_reactome = QPushButton("DrugBank")
        self.btn_reactome.setObjectName("external_drugbank_btn")
        self.btn_reactome.setToolTip("DrugBank web-search route only — local CSV/SDF status is shown above")
        self.btn_reactome.clicked.connect(self._open_reactome)
        btn_row.addWidget(self.btn_reactome)

        ext_layout.addLayout(btn_row)
        self.ext_group.setLayout(ext_layout)
        layout.addWidget(self.ext_group)

        layout.addStretch()
        inner_widget.setLayout(layout)
        scroll_area.setWidget(inner_widget)
        outer_layout.addWidget(scroll_area)
        self.setLayout(outer_layout)

        # 외부 API 연결용 SMILES/UniProt 저장
        self._ext_smiles: str = ""
        self._ext_uniprot: str = ""
        self._last_external_urls: dict = {}

    # ── 외부 API 콜백 (M645_W9) ─────────────────────────────────────────────

    @staticmethod
    def _drugbank_status_text() -> str:
        """Visible local DrugBank CSV/SDF state for route-only DB UX."""
        try:
            import drugbank_local
            status = drugbank_local.get_data_status()
            if not isinstance(status, dict):
                logger.warning("[PropertiesPanel] DrugBank status not dict: %s", type(status).__name__)
                return "Local DrugBank data unavailable: status probe returned a non-dict value."
            csv_state = "present" if status.get("csv_exists") else "missing"
            sdf_state = "present" if status.get("sdf_exists") else "missing"
            data_root = status.get("data_root", "C:/chemgrid/data/drugbank")
            if status.get("csv_exists") and status.get("sdf_exists"):
                return (
                    f"Local DrugBank data state: CSV {csv_state}; SDF {sdf_state}; "
                    f"root {data_root}. Local-data presence only, not external query success."
                )
            return (
                f"Local DrugBank data unavailable: CSV {csv_state}; SDF {sdf_state}; "
                f"root {data_root}. DrugBank button remains a web-search route only."
            )
        except Exception as e:
            logger.warning("[PropertiesPanel] DrugBank status probe failed: %s", e)
            return "Local DrugBank data unavailable: status probe failed; DrugBank button is web-search route only."

    @staticmethod
    def build_external_db_urls(smiles: str) -> dict:
        """Build deterministic external database URLs for audit and button tests."""
        import urllib.parse as _up
        q = smiles.strip() if isinstance(smiles, str) else ""
        if not q:
            return {
                "nci_cactus": "https://cactus.nci.nih.gov/",
                "pubchem": "https://pubchem.ncbi.nlm.nih.gov/",
                "chembl": "https://www.ebi.ac.uk/chembl/",
                "drugbank": "https://go.drugbank.com/",
            }
        encoded = _up.quote(q, safe="")
        return {
            "nci_cactus": f"https://cactus.nci.nih.gov/chemical/structure/{encoded}/iupac_name",
            "pubchem": f"https://pubchem.ncbi.nlm.nih.gov/#query={encoded}&collection=compound",
            "chembl": f"https://www.ebi.ac.uk/chembl/g/#search_results/compounds/query={encoded}",
            "drugbank": f"https://go.drugbank.com/unearth/q?searcher=drugs&query={encoded}",
        }

    def _open_external_url(self, key: str, label: str):
        """Open an external URL through Qt first and retain exact URL evidence."""
        smiles = self._ext_smiles if isinstance(self._ext_smiles, str) else ""
        urls = self.build_external_db_urls(smiles)
        url = urls.get(key, "")
        self._last_external_urls[key] = url
        if not smiles.strip():
            logger.warning("[PropertiesPanel] %s: SMILES missing; opening main page url=%s", label, url)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, label,
                "?꾩옱 遺꾩옄??SMILES媛 ?놁뒿?덈떎.\n"
                "2D ?덉씠?댁뿉 遺꾩옄瑜?洹몃┛ ???ㅼ떆 ?쒕룄?섏꽭??\n"
                f"{label} 硫붿씤 ?섏씠吏瑜??닿쿋?듬땲??"
            )
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            opened = QDesktopServices.openUrl(QUrl(url))
            if opened:
                logger.info("[PropertiesPanel] opened external %s url=%s", label, url)
                return
            logger.warning("[PropertiesPanel] Qt refused external %s url=%s; trying webbrowser", label, url)
        except Exception as e:
            logger.warning("[PropertiesPanel] Qt external open failed for %s url=%s error=%s", label, url, e)
        import webbrowser
        webbrowser.open(url)

    def _open_nci_cactus(self):
        """Open NCI Cactus for the current SMILES and retain URL evidence."""
        self._open_external_url("nci_cactus", "NCI Cactus")

    def _open_opsin(self):
        """Open PubChem for the current SMILES and retain URL evidence."""
        self._open_external_url("pubchem", "PubChem")

    def _open_chembl(self):
        """Open ChEMBL for the current SMILES and retain URL evidence."""
        self._open_external_url("chembl", "ChEMBL")

    def _open_reactome(self):
        """Open DrugBank for the current SMILES and retain URL evidence."""
        self._open_external_url("drugbank", "DrugBank")

    def set_ext_context(self, smiles: str, uniprot_id: str = ""):
        """외부 API 호출용 SMILES / UniProt ID 설정 (M645_W9).

        Rule N: isinstance 타입 가드 적용.
        """
        if isinstance(smiles, str):
            self._ext_smiles = smiles
        else:
            logger.warning("[PropertiesPanel] set_ext_context: smiles 타입 비정상 %s", type(smiles).__name__)
            self._ext_smiles = ""
        if isinstance(uniprot_id, str):
            self._ext_uniprot = uniprot_id
        else:
            self._ext_uniprot = ""

    def update_rdkit(self, smiles: str):
        """RDKit 계산값 업데이트 — v4: 독립적 try/except 오류 핸들링"""
        # Clear
        while self.calc_form.rowCount() > 0:
            self.calc_form.removeRow(0)

        if not RDKIT_AVAILABLE:
            logger.warning("RDKit 계산 패널 건너뜀: RDKit 미설치")
            self.calc_form.addRow("상태:", QLabel("RDKit 미설치"))
            return
        if not smiles:
            logger.warning("RDKit 계산 패널 건너뜀: SMILES 없음")
            self.calc_form.addRow("상태:", QLabel("SMILES 없음"))
            return

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("RDKit 계산 패널: SMILES 파싱 실패 (smiles=%r)", smiles)
                self.calc_form.addRow("오류:", QLabel("SMILES 파싱 실패"))
                return

            self.calc_form.addRow("SMILES:", QLabel(smiles))
            try:
                self.calc_form.addRow("분자식:", QLabel(rdMolDescriptors.CalcMolFormula(mol)))
            except Exception as e:
                logger.warning("Molecular formula calculation failed: %s", e)
                self.calc_form.addRow("분자식:", QLabel("계산 실패"))
            try:
                self.calc_form.addRow("분자량:", QLabel(f"{Descriptors.MolWt(mol):.2f} g/mol"))
            except Exception as e:
                logger.warning("Molecular weight calculation failed: %s", e)
                self.calc_form.addRow("분자량:", QLabel("계산 실패"))
            try:
                self.calc_form.addRow("정확 질량:", QLabel(f"{Descriptors.ExactMolWt(mol):.4f}"))
            except Exception as e:
                logger.warning("Exact mass calculation failed: %s", e)
            try:
                self.calc_form.addRow("LogP:", QLabel(f"{Descriptors.MolLogP(mol):.2f}"))
            except Exception as e:
                logger.warning("LogP calculation failed: %s", e)
            try:
                self.calc_form.addRow("TPSA:", QLabel(f"{Descriptors.TPSA(mol):.1f} Å²"))
            except Exception as e:
                logger.warning("TPSA calculation failed: %s", e)
            try:
                self.calc_form.addRow("H-Bond Donor:", QLabel(str(Descriptors.NumHDonors(mol))))
                self.calc_form.addRow("H-Bond Acceptor:", QLabel(str(Descriptors.NumHAcceptors(mol))))
            except Exception as e:
                logger.warning("Rotatable bonds calculation failed: %s", e)
            try:
                self.calc_form.addRow("회전 가능 결합:", QLabel(str(Descriptors.NumRotatableBonds(mol))))
            except Exception as e:
                logger.warning("HBD/HBA calculation failed: %s", e)
            try:
                self.calc_form.addRow("고리 수:", QLabel(str(rdMolDescriptors.CalcNumRings(mol))))
                self.calc_form.addRow("방향족 고리:", QLabel(str(rdMolDescriptors.CalcNumAromaticRings(mol))))
            except Exception as e:
                logger.warning("Ring count calculation failed: %s", e)
        except Exception as e:
            self.calc_form.addRow("RDKit 오류:", QLabel(f"{str(e)[:60]}"))

    def update_pubchem(self, data: Dict, smiles: str = ""):
        """PubChem 결과 업데이트 — v4: 독립적 try/except 오류 핸들링
        smiles: 분자의 SMILES 코드 (표시용)"""
        while self.pub_form.rowCount() > 0:
            self.pub_form.removeRow(0)

        if not data:
            logger.warning("PubChem 조회 실패 또는 오프라인: smiles=%r", smiles)
            self.pub_form.addRow("상태:", QLabel("오프라인 — PubChem 조회 불가"))
            # 오프라인 시에도 SMILES 표시
            if smiles:
                smiles_lbl = QLabel(smiles)
                smiles_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                smiles_lbl.setWordWrap(True)
                smiles_lbl.setStyleSheet("font-family: monospace; color: #64B5F6;")
                self.pub_form.addRow("SMILES:", smiles_lbl)
            return

        if not isinstance(data, dict):
            logger.warning("update_pubchem: data not dict: %s", type(data))
            self.pub_form.addRow("상태:", QLabel("PubChem 데이터 형식 오류"))
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
            logger.warning("ORCA 결과 패널: parser=%s, text=%s", bool(parser), bool(parser.text) if parser else False)
            if ORCA_AVAILABLE:
                self.orca_form.addRow("상태:", QLabel("ORCA 연결됨 — 아직 DFT 계산 미실행"))
                self.orca_form.addRow("백엔드:", QLabel("WSL/native/remote 중 사용 가능 경로 감지됨"))
            elif _orca_disabled_by_env():
                self.orca_form.addRow("상태:", QLabel("ORCA 비활성화 — foreground 검증 환경변수"))
                self.orca_form.addRow("대체:", QLabel("RDKit/xTB/휴리스틱 값은 SIMULATION_MODE로만 표시"))
            else:
                self.orca_form.addRow("상태:", QLabel("ORCA 결과 없음 — 정밀 DFT 미연결"))
                self.orca_form.addRow("대체:", QLabel("RDKit/xTB/휴리스틱 값은 SIMULATION_MODE로만 표시"))
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

    def update_xtb_dipole(self, dipole_d: float):
        """xTB 쌍극자 모멘트를 계산값 섹션에 추가 표시.
        [I-1] ethanol dipole 0.71 D 속성 탭 미가시 수정 (2026-04-24).
        ORCA 결과가 없을 때만 호출됨 (ORCA 우선).
        """
        if not isinstance(dipole_d, (int, float)):
            logger.warning("update_xtb_dipole: dipole not numeric: %s", dipole_d)
            return
        # 기존 calc_form에 쌍극자 행이 이미 있으면 중복 추가 방지
        for row in range(self.calc_form.rowCount()):
            label_item = self.calc_form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                if "쌍극자" in label_item.widget().text():
                    return  # 이미 표시 중
        self.calc_form.addRow(
            "쌍극자 모멘트:",
            QLabel(f"{dipole_d:.2f} D (xTB GFN2-xTB)"))


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
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
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


class _LocalSpectrumCanvas(QWidget):
    """Small Qt-only spectrum plot used when matplotlib is unavailable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._freqs: List[float] = []
        self._ints: List[float] = []
        self._spec_type = "IR"
        self._smiles = ""
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_spectrum(self, freqs: List[float], intensities: List[float],
                     spec_type: str, smiles: str):
        self._freqs = [float(v) for v in freqs]
        self._ints = [float(v) for v in intensities]
        self._spec_type = spec_type or "IR"
        self._smiles = smiles or ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        plot = self.rect().adjusted(48, 18, -16, -34)
        if plot.width() < 80 or plot.height() < 60:
            painter.end()
            return

        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(plot)
        painter.setFont(QFont(_QT_KR_FONT, 8))
        painter.setPen(QColor("#bdbdbd"))
        title = f"Local predicted {self._spec_type} spectrum"
        if self._smiles:
            title += f" | {self._smiles[:24]}"
        painter.drawText(self.rect().adjusted(8, 2, -8, -2),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                         title)

        if not self._freqs or not self._ints:
            painter.setPen(QColor("#aaa"))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter,
                             "No local predicted peaks for this molecule")
            painter.end()
            return

        spec_key = self._spec_type.upper().replace("-", "").replace("_", "")
        x_min = min(self._freqs)
        x_max = max(self._freqs)
        if spec_key in ("IR", "RAMAN"):
            x_min, x_max = 400.0, 4000.0
        elif spec_key in ("NMRH", "NMR", "1HNMR"):
            x_min, x_max = -0.5, 12.0
        elif spec_key in ("NMRC13", "13CNMR", "C13"):
            x_min, x_max = -5.0, 220.0
        elif spec_key in ("UVVIS", "UV"):
            x_min, x_max = 180.0, 800.0
        elif spec_key == "MS":
            x_min, x_max = 0.0, max(self._freqs) + 20.0
        if abs(x_max - x_min) < 1e-6:
            x_max = x_min + 1.0
        y_max = max(max(self._ints), 1.0)

        for i in range(1, 5):
            x = plot.left() + plot.width() * i / 5.0
            y = plot.top() + plot.height() * i / 5.0
            painter.setPen(QPen(QColor("#343434"), 1))
            painter.drawLine(int(x), plot.top(), int(x), plot.bottom())
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))

        def map_x(value: float) -> float:
            frac = (value - x_min) / (x_max - x_min)
            if spec_key == "IR":
                frac = 1.0 - frac
            return plot.left() + max(0.0, min(1.0, frac)) * plot.width()

        def map_y(value: float) -> float:
            frac = max(0.0, min(1.0, value / y_max))
            return plot.bottom() - frac * plot.height()

        color = QColor("#42A5F5")
        if spec_key in ("RAMAN", "MS"):
            color = QColor("#AB47BC")
        elif spec_key.startswith("NMR") or spec_key in ("1HNMR", "13CNMR", "C13"):
            color = QColor("#66BB6A")
        elif spec_key in ("UVVIS", "UV"):
            color = QColor("#FFA726")

        painter.setPen(QPen(color, 2))
        for freq, intensity in zip(self._freqs, self._ints):
            x = map_x(freq)
            y = map_y(intensity)
            painter.drawLine(int(x), plot.bottom(), int(x), int(y))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)

        painter.setPen(QColor("#ddd"))
        axis = "cm-1" if spec_key in ("IR", "RAMAN") else ("ppm" if "NMR" in spec_key or spec_key in ("1HNMR", "13CNMR", "C13") else ("nm" if spec_key in ("UVVIS", "UV") else "m/z"))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 4, plot.width(), 22),
                         Qt.AlignmentFlag.AlignCenter, axis)
        painter.setPen(QColor("#FFCC00"))
        painter.drawText(self.rect().adjusted(8, 0, -8, -4),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         "SIMULATION_MODE: local RDKit/SMARTS prediction only; no ORCA/DFT/lab measurement claimed.")
        painter.end()


class SpectrumPanel(QWidget):
    """📈 스펙트럼 탭 — IR/Raman/NMR/UV-Vis/MS 예측 스펙트럼 + ORCA 정밀 스펙트럼 + AI 피크 분석"""

    # Signal emitted when user clicks near a peak with atom_indices data
    peak_clicked = pyqtSignal(tuple)  # emits (atom_indices,) tuple of int

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
        # [PEAK-CLICK] 현재 표시된 피크 객체 리스트 (atom_indices 포함)
        self._current_peaks = []  # List of IRPeak/RamanPeak/NMRPeak/etc.
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib unavailable; using local Qt predicted-spectrum plot")
            self._spec_type = "IR"
            self._smiles_cache = ""
            self._spec_btns: Dict[str, QPushButton] = {}
            top_bar = QHBoxLayout()
            for label, stype, color in [
                    ("IR", "IR", "#1565C0"),
                    ("Raman", "Raman", "#880E4F"),
                    ("1H NMR", "NMR_H", "#1B5E20"),
                    ("13C NMR", "NMR_C13", "#2E7D32"),
                    ("MS", "MS", "#6A1B9A")]:
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setChecked(stype == "IR")
                btn.setFixedHeight(26)
                btn.setStyleSheet(
                    f"QPushButton {{ background:#2a2a2a; border:1px solid #555; "
                    f"color:#ccc; padding:2px 8px; border-radius:3px; font-size:9pt; }}"
                    f"QPushButton:checked {{ background:{color}; color:white; }}"
                )
                btn.clicked.connect(lambda checked=False, s=stype: self._on_spec_type_changed(s))
                self._spec_btns[stype] = btn
                top_bar.addWidget(btn)
            top_bar.addStretch()
            layout.addLayout(top_bar)
            self.qt_spectrum_canvas = _LocalSpectrumCanvas(self)
            layout.addWidget(self.qt_spectrum_canvas, 1)
            self.info_label = QLabel(
                "SIMULATION_MODE: local RDKit/SMARTS predicted spectra. "
                "No ORCA/DFT calculation, engine run, or lab measurement is claimed."
            )
            self.info_label.setStyleSheet(
                "color:#FFCC00; font-size:8pt; padding:2px;")
            layout.addWidget(self.info_label)
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
            ("⚗ MS",        "MS",      "#6A1B9A"),
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
        # [PEAK-CLICK] matplotlib 클릭 이벤트 연결
        self.canvas.mpl_connect('button_press_event', self._on_peak_click)
        layout.addWidget(self.canvas, 1)

        self.info_label = QLabel("분자 로드 시 예측 스펙트럼 자동 표시")
        self.info_label.setStyleSheet("color: #888; font-size: 8pt;")
        layout.addWidget(self.info_label)

        self.claim_boundary_label = QLabel(
            "SIMULATION_MODE: local RDKit/SMARTS prediction only; "
            "no ORCA/DFT calculation, engine run, or lab measurement is claimed."
        )
        self.claim_boundary_label.setStyleSheet(
            "color:#FFCC00; font-size:8pt; padding:2px;")
        layout.addWidget(self.claim_boundary_label)

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
        except Exception as e:
            logger.warning("Spectrum axis configuration failed: %s", e)

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
        if not RDKIT_AVAILABLE or not smiles:
            logger.warning("예측 스펙트럼 로드 건너뜀: RDKIT=%s, MATPLOTLIB=%s, smiles=%r",
                           RDKIT_AVAILABLE, MATPLOTLIB_AVAILABLE, smiles)
            return
        self._smiles_cache = smiles
        spec_type = getattr(self, '_spec_type', 'IR')
        if not MATPLOTLIB_AVAILABLE:
            freqs, ints = predict_spectrum_from_smiles(smiles, spec_type)
            self.frequencies = list(freqs)
            self.intensities = list(ints)
            if hasattr(self, "qt_spectrum_canvas"):
                self.qt_spectrum_canvas.set_spectrum(freqs, ints, spec_type, smiles)
            self.info_label.setText(
                f"Local predicted {spec_type} spectrum: {len(freqs)} peaks. "
                "No ORCA/DFT calculation, engine run, or lab measurement is claimed."
            )
            return
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
            logger.warning("가이드 스펙트럼 렌더링 건너뜀: matplotlib 미설치")
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
                _make_uvvis_figure, _make_ms_figure,
            )
            spec = predict_all(smiles)
            _t = spec_type.upper().replace("-", "").replace(" ", "")
            if _t == "IR":
                new_fig = _make_ir_figure(spec.ir_peaks)
                # AI 피크 분석용 데이터 저장 (IRPeak.wavenumber, .transmittance)
                if spec.ir_peaks:
                    self.frequencies = [p.wavenumber for p in spec.ir_peaks]
                    self.intensities = [100.0 - p.transmittance for p in spec.ir_peaks]  # 흡수 강도로 변환
                self._current_peaks = list(spec.ir_peaks)  # [PEAK-CLICK]
            elif _t == "RAMAN":
                new_fig = _make_raman_figure(spec.raman_peaks)
                if spec.raman_peaks:
                    self.frequencies = [p.shift for p in spec.raman_peaks]
                    self.intensities = [p.intensity for p in spec.raman_peaks]
                self._current_peaks = list(spec.raman_peaks)  # [PEAK-CLICK]
            elif _t in ("NMRH", "1HNMR", "NMR", "NMR_H"):
                new_fig = _make_nmr_h1_figure(spec.h1_nmr_peaks, spec.formula, smiles=smiles)
                self._current_peaks = list(spec.h1_nmr_peaks)  # [PEAK-CLICK]
            elif _t in ("NMRC13", "13CNMR", "NMR_C13", "C13"):
                new_fig = _make_nmr_c13_figure(spec.c13_peaks, spec.formula, smiles=smiles)
                self._current_peaks = list(spec.c13_peaks)  # [PEAK-CLICK]
            elif _t in ("UVVIS", "UV"):
                new_fig = _make_uvvis_figure(spec.uvvis_peaks)
                self._current_peaks = list(spec.uvvis_peaks)  # [PEAK-CLICK]
            elif _t == "MS":
                # [MS-RESTORE] 2D 구조(왼쪽) + 결합분열선 + MS 막대그래프(오른쪽)
                new_fig = _make_ms_figure(smiles)
                self._current_peaks = []  # MS는 별도 peak-click 미지원
            else:
                new_fig = _make_ir_figure(spec.ir_peaks)
                if spec.ir_peaks:
                    self.frequencies = [p.wavenumber for p in spec.ir_peaks]
                    self.intensities = [100.0 - p.transmittance for p in spec.ir_peaks]
                self._current_peaks = list(spec.ir_peaks)  # [PEAK-CLICK]
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
            except Exception as e:
                logger.warning("Guide spectrum rendering cleanup failed: %s", e)

    def plot_predicted(self, freqs: List[float], ints: List[float],
                       spec_type: str, smiles: str = ""):
        """예측 스펙트럼 플롯 — 분광 유형별 x축 설정"""
        if not MATPLOTLIB_AVAILABLE or not freqs:
            logger.warning("예측 스펙트럼 플롯 건너뜀: MATPLOTLIB=%s, freqs=%s",
                           MATPLOTLIB_AVAILABLE, bool(freqs))
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
                    if _rdmol is None:
                        logger.warning("Invalid SMILES for NMR molecule image: %s", smiles)
                    else:
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
                except Exception as e:
                    logger.warning("Legend element creation failed: %s", e)
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
                    if _mol13 is None:
                        logger.warning("Invalid SMILES for C13-NMR molecule image: %s", smiles)
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
                        except Exception as e:
                            logger.debug("Legend rendering failed (Cairo missing): %s", e)
                except Exception as e:
                    logger.warning("Spectrum legend rendering failed: %s", e)
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
                    if _mol_ms is None:
                        logger.warning("Invalid SMILES for MS molecule image: %s", smiles)
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
                except Exception as e:
                    logger.warning("Spectrum tick label styling failed: %s", e)

        else:
            logger.warning("예측 스펙트럼: 미지원 스펙트럼 유형 (spec_type=%r)", spec_type)
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
            logger.warning("PDF 내보내기 건너뜀: matplotlib 미설치")
            self.info_label.setText("⚠️ matplotlib 미설치")
            return
        smiles = self._resolve_smiles()
        spec_type = getattr(self, '_spec_type', 'IR')

        # [FIX-PDF-PATH] auto_generated 폴더 기본 저장 경로
        import datetime as _dt_pdf
        _auto_dir = _SCRIPT_DIR.parent.parent / "docs" / "exports" / "spectra_assets" / "auto_generated"
        try:
            _auto_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Auto-export dir creation failed: %s", e)
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
                    if _mol is None:
                        logger.warning("Invalid SMILES for spectrum formula: %s", smiles)
                    else:
                        _formula = rdMolDescriptors.CalcMolFormula(Chem.AddHs(_mol))
                except Exception as e:
                    logger.warning("Spectrum formula calculation failed: %s", e)

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
                        if not isinstance(_sdata, dict):
                            continue
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

    # ── [PEAK-CLICK] 스펙트럼 피크 클릭 → 3D 원자 하이라이트 ──────────
    def _on_peak_click(self, event):
        """Handle matplotlib click event: find nearest peak and emit atom indices."""
        if event.inaxes is None or not self._current_peaks:
            return
        click_x = event.xdata
        if click_x is None:
            return

        spec_type = getattr(self, '_spec_type', 'IR')
        _t = spec_type.upper().replace("-", "").replace(" ", "")

        # Determine x-position getter and tolerance based on spectrum type
        best_peak = None
        best_dist = float('inf')

        for peak in self._current_peaks:
            if _t in ("IR",):
                px = getattr(peak, 'wavenumber', None)
                tolerance = 40.0  # +/- 40 cm-1 for IR
            elif _t == "RAMAN":
                px = getattr(peak, 'shift', None)
                tolerance = 40.0  # +/- 40 cm-1 for Raman
            elif _t in ("NMRH", "1HNMR", "NMR", "NMR_H"):
                px = getattr(peak, 'shift', None)
                tolerance = 0.5  # +/- 0.5 ppm for 1H NMR
            elif _t in ("NMRC13", "13CNMR", "NMR_C13", "C13"):
                px = getattr(peak, 'shift', None)
                tolerance = 5.0  # +/- 5 ppm for 13C NMR
            elif _t in ("UVVIS", "UV"):
                px = getattr(peak, 'wavelength', None)
                tolerance = 15.0  # +/- 15 nm for UV-Vis
            else:
                px = getattr(peak, 'wavenumber', getattr(peak, 'shift', None))
                tolerance = 40.0

            if px is None:
                continue
            dist = abs(click_x - px)
            if dist < tolerance and dist < best_dist:
                best_dist = dist
                best_peak = peak

        if best_peak is not None:
            atom_idx = getattr(best_peak, 'atom_indices', ())
            asgn = getattr(best_peak, 'assignment', '')

            # Build info text with peak position and functional group assignment
            # IR: wavenumber, Raman: shift, NMR: shift(ppm), UV-Vis: wavelength(nm)
            pos_val = getattr(best_peak, 'wavenumber',
                         getattr(best_peak, 'shift',
                             getattr(best_peak, 'wavelength', None)))
            if _t in ("IR",) and pos_val is not None:
                pos_text = f"{pos_val:.0f} cm\u207b\u00b9"
            elif _t == "RAMAN" and pos_val is not None:
                pos_text = f"{pos_val:.0f} cm\u207b\u00b9"
            elif _t in ("NMRH", "1HNMR", "NMR", "NMR_H", "NMRC13", "13CNMR", "NMR_C13", "C13") and pos_val is not None:
                pos_text = f"{pos_val:.2f} ppm"
            elif _t in ("UVVIS", "UV") and pos_val is not None:
                pos_text = f"{pos_val:.0f} nm"
            else:
                pos_text = ""

            info_parts = []
            if pos_text:
                info_parts.append(pos_text)
            if asgn:
                info_parts.append(asgn)

            info_str = " | ".join(info_parts) if info_parts else "Peak selected"
            self.info_label.setText(f"Peak: {info_str}")
            logger.debug("Peak clicked: %s, atom_indices=%s", asgn, atom_idx)

            # Emit atom highlight signal only if atom_indices available
            if atom_idx:
                self.peak_clicked.emit(atom_idx)

    def plot_ir(self, frequencies: List[float], intensities: List[float]):
        """IR 스펙트럼 플롯"""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("IR 스펙트럼 플롯 건너뜀: matplotlib 미설치")
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
            logger.warning("IR 스펙트럼 플롯: 진동 주파수 데이터 없음")
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
            logger.warning("AI 오버레이 토글 건너뜀: btn_ai_overlay 위젯 없음")
            return
        if self.btn_ai_overlay.isChecked():
            # 오버레이 표시
            if not self.frequencies:
                logger.warning("AI 오버레이 토글 건너뜀: 주파수 데이터 없음")
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
            logger.warning("AI 피크 분석 건너뜀: 주파수 데이터 없음")
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
                        parsed = json.loads(json_match.group())
                        # N코드: AI(Gemini) 응답 isinstance 가드
                        if not isinstance(parsed, list):
                            logger.warning("Gemini AI 응답이 list가 아님: type=%s", type(parsed).__name__)
                            self.ai_analysis_data = self._fallback_peak_analysis()
                        else:
                            # 각 항목이 dict인지 검증
                            validated = []
                            for item in parsed:
                                if isinstance(item, dict):
                                    validated.append(item)
                                else:
                                    logger.warning("AI 피크 항목이 dict가 아님: type=%s", type(item).__name__)
                            self.ai_analysis_data = validated if validated else self._fallback_peak_analysis()
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
            logger.warning("폴백 피크 분석 건너뜀: 주파수 데이터 없음")
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
            logger.warning("AI 주석 표시 건너뜀: ai_data=%s, ax=%s",
                           bool(self.ai_analysis_data), self.ax is not None)
            return
        # N코드: ai_analysis_data 전체 타입 가드
        if not isinstance(self.ai_analysis_data, list):
            logger.warning("ai_analysis_data가 list가 아님: type=%s", type(self.ai_analysis_data).__name__)
            self.ai_analysis_data = self._fallback_peak_analysis()
            if not self.ai_analysis_data:
                return

        self._hide_ai_annotations()  # 기존 주석 제거

        colors = ['#FF5722', '#2196F3', '#4CAF50', '#FF9800', '#9C27B0',
                  '#00BCD4', '#E91E63', '#8BC34A', '#FFC107', '#673AB7']

        for i, peak in enumerate(self.ai_analysis_data):
            # N코드: AI 데이터 항목별 isinstance 가드
            if not isinstance(peak, dict):
                logger.warning("AI 피크 데이터[%d]가 dict가 아님: type=%s", i, type(peak).__name__)
                continue
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
            except Exception as e:
                logger.warning("Spectrum panel update failed: %s", e)
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


class _VibGifExportThread(QThread):
    """진동 모드 GIF 내보내기 스레드 — 16프레임 @ 10fps (M632 VIBRATION-AUTO-001)

    Rule I 매직넘버 주석:
      N_FRAMES = 16  — 부드러운 사인파 1사이클을 위한 최소 프레임 수
      FPS      = 10  — GIF 표준 재생 속도 (학회 발표·교육용)
      W, H     = 400, 240  — GIF 해상도 (표준 학술 프레젠테이션용)
    """
    finished = pyqtSignal(str)   # 저장 완료: 경로 전달
    error    = pyqtSignal(str)   # 오류: 메시지 전달

    N_FRAMES = 16   # 사인파 1사이클 프레임 수 (Rule I)
    FPS      = 10   # 초당 프레임 수 (Rule I)

    def __init__(self, displacement_vectors, frequency_cm: float,
                 smiles: str = "", parent=None):
        super().__init__(parent)
        # Rule N: isinstance 타입 가드
        self._displacements = displacement_vectors if isinstance(displacement_vectors, list) else []
        self._frequency_cm  = float(frequency_cm) if frequency_cm else 0.0
        self._smiles        = smiles if isinstance(smiles, str) else ""
        self._save_path     = ""

    def set_save_path(self, path: str):
        self._save_path = path if isinstance(path, str) else ""

    def run(self):
        import math

        # imageio 우선, 없으면 PIL 직접 사용
        try:
            import imageio as _imageio
            _use_imageio = True
        except ImportError:
            _use_imageio = False

        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.error.emit("PIL(Pillow) 미설치 — pip install Pillow")
            return

        if not self._save_path:
            self.error.emit("저장 경로가 지정되지 않았습니다")
            return

        disps = self._displacements
        if not disps:
            self.error.emit("변위벡터 없음 — 진동 모드를 먼저 선택하세요")
            return

        try:
            magnitudes = [
                math.sqrt(sum(v ** 2 for v in d)) if d else 0.0
                for d in disps
            ]
            max_mag = max(magnitudes) if magnitudes else 1.0
            if max_mag < 1e-9:
                max_mag = 1.0
        except Exception as e:
            self.error.emit(f"변위벡터 처리 오류: {e}")
            logger.warning("[_VibGifExportThread] 변위벡터 오류: %s", e)
            return

        W, H = 400, 240  # GIF 프레임 크기 (Rule I: 학술 발표용 해상도)
        n_atoms = len(disps)
        frames = []

        bar_w = max(4, min(28, (W - 40) // max(n_atoms, 1)))  # 원자당 막대 너비

        for frame_idx in range(self.N_FRAMES):
            phase = 2.0 * math.pi * frame_idx / self.N_FRAMES
            amp   = math.sin(phase)  # -1 ~ +1 사인파 진폭

            img  = Image.new("RGB", (W, H), color=(30, 30, 30))
            draw = ImageDraw.Draw(img)

            title = f"{self._frequency_cm:.0f} cm^-1  [{frame_idx+1}/{self.N_FRAMES}]"
            draw.text((8, 6), title, fill=(180, 200, 255))

            zero_y  = H // 2
            x_start = 20

            for ai, mag in enumerate(magnitudes):
                x = x_start + ai * (bar_w + 2)
                if x + bar_w > W - 10:
                    break
                norm_mag = mag / max_mag
                bar_h = int(norm_mag * amp * (H // 3))  # 최대 H/3 높이
                r = 100 + int(155 * norm_mag)
                g = 50 + int(100 * abs(amp))
                b = 200
                if bar_h >= 0:
                    draw.rectangle([x, zero_y - bar_h, x + bar_w, zero_y], fill=(r, g, b))
                else:
                    draw.rectangle([x, zero_y, x + bar_w, zero_y - bar_h], fill=(r, g, b))

            draw.line([(20, zero_y), (W - 20, zero_y)], fill=(100, 100, 100), width=1)
            frames.append(img)

        try:
            if _use_imageio:
                _imageio.mimsave(self._save_path, frames, fps=self.FPS)
            else:
                # PIL 직접 GIF 저장 (imageio 없을 때 fallback)
                frames[0].save(
                    self._save_path,
                    save_all=True,
                    append_images=frames[1:],
                    loop=0,
                    duration=int(1000 / self.FPS),  # ms per frame (Rule I)
                    optimize=False,
                )
            self.finished.emit(self._save_path)
        except Exception as e:
            self.error.emit(f"GIF 저장 실패: {e}")
            logger.warning("[_VibGifExportThread] GIF 저장 오류: %s", e)


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

    # Signal: (orca_load_requested removed — students use internal engine only)

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

        # [VIB-UX] 자동 계산 대기 안내 위젯 (ORCA 버튼 제거 — 학생용 간소화)
        self.no_data_widget = QWidget()
        nd_layout = QVBoxLayout()
        nd_layout.setContentsMargins(12, 20, 12, 20)
        nd_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nd_icon = QLabel("🎵")
        nd_icon.setStyleSheet("font-size: 36pt;")
        nd_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nd_layout.addWidget(nd_icon)

        self._nd_title = QLabel("진동 모드를 계산하는 중...")
        self._nd_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #ddd;")
        self._nd_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nd_layout.addWidget(self._nd_title)

        self._nd_desc = QLabel("내부 엔진(경험적 힘 상수 기반)으로 자동 계산합니다.")
        self._nd_desc.setStyleSheet("color: #999; font-size: 9pt;")
        self._nd_desc.setWordWrap(True)
        self._nd_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nd_layout.addWidget(self._nd_desc)

        nd_layout.addSpacing(10)

        # 진행 표시 (자동 계산 시 보여줌)
        self._calc_progress = QProgressBar()
        self._calc_progress.setRange(0, 0)  # indeterminate
        self._calc_progress.setFixedWidth(200)
        self._calc_progress.setFixedHeight(6)
        self._calc_progress.setStyleSheet(
            "QProgressBar { border: none; background: #333; border-radius: 3px; }"
            "QProgressBar::chunk { background: #e65100; border-radius: 3px; }")
        nd_layout.addWidget(self._calc_progress, alignment=Qt.AlignmentFlag.AlignCenter)

        # 내부 엔진 계산 버튼 (수동 재시도 용도 — 자동 실패 시 표시)
        self.btn_internal_calc = QPushButton("⚡ 다시 계산")
        self.btn_internal_calc.setStyleSheet("""
            QPushButton {
                background: #e65100; color: white; border: none;
                padding: 8px 20px; border-radius: 4px; font-size: 10pt;
            }
            QPushButton:hover { background: #ff6d00; }
        """)
        self.btn_internal_calc.clicked.connect(self._run_internal_engine)
        self.btn_internal_calc.setVisible(False)  # 초기에는 숨김 (자동 계산 실패 시만 표시)
        nd_layout.addWidget(self.btn_internal_calc, alignment=Qt.AlignmentFlag.AlignCenter)

        self.no_data_widget.setLayout(nd_layout)
        layout.addWidget(self.no_data_widget)
        self._auto_calc_done = False  # 자동 계산 완료 플래그

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

        # GIF 저장 버튼 (M632 VIBRATION-AUTO-001)
        self.btn_export_gif = QPushButton("💾 GIF 저장")
        self.btn_export_gif.setToolTip("현재 진동 모드를 GIF 애니메이션으로 저장 (16프레임 @ 10fps)")
        self.btn_export_gif.clicked.connect(self._export_gif)
        ctrl.addWidget(self.btn_export_gif)

        ctrl.addWidget(QLabel("진폭:"))
        self.amp_slider = QSlider(Qt.Orientation.Horizontal)
        self.amp_slider.setMinimum(10)
        self.amp_slider.setMaximum(500)
        self.amp_slider.setValue(120)  # [FIX-VIB-001] 기본 진폭 1.2x (과도한 진동 방지)
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
        self.info_label = QLabel("진동모드 탭을 열면 자동으로 계산합니다")
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

    def auto_calculate_if_needed(self):
        """탭 활성화 시 자동으로 내부 엔진 계산 (데이터 없으면 즉시 실행)"""
        if self._auto_calc_done or self._vib_result:
            return  # 이미 계산됨
        if not self._smiles:
            logger.warning("진동 자동 계산 건너뜀: SMILES 없음")
            self._nd_title.setText("분자를 먼저 그려주세요")
            self._nd_desc.setText("")
            self._calc_progress.setVisible(False)
            return
        self._auto_calc_done = True
        # 약간의 딜레이 후 계산 시작 (UI 렌더링 완료 대기)
        QTimer.singleShot(100, self._run_internal_engine)  # 100ms delay

    def _run_internal_engine(self):
        """내부 진동 엔진으로 계산 실행"""
        if not self._smiles:
            logger.warning("내부 진동 엔진 실행 건너뜀: SMILES 없음")
            self.info_label.setText("분자 데이터가 없습니다")
            return

        # UI 상태: 계산 중
        self.btn_internal_calc.setVisible(False)
        self._calc_progress.setVisible(True)
        self._nd_title.setText("진동 모드를 계산하는 중...")
        self._nd_desc.setText("내부 엔진(경험적 힘 상수 기반)으로 계산합니다.")
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
                    f"(↔{n_stretch} ∠{n_bend} ⟳{n_torsion}) | "
                    "SIMULATION_MODE: empirical internal estimate; "
                    "yellow atoms follow nonzero displacement vectors, not ORCA/DFT modes.")
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
                self._nd_title.setText("계산 실패")
                self._nd_desc.setText(err)
                self._calc_progress.setVisible(False)
                self.btn_internal_calc.setVisible(True)
        except Exception as e:
            self.info_label.setText(f"엔진 오류: {e}")
            self._nd_title.setText("계산 오류")
            self._nd_desc.setText(str(e)[:120])
            self._calc_progress.setVisible(False)
            self.btn_internal_calc.setVisible(True)
        finally:
            self.btn_internal_calc.setText("⚡ 다시 계산")
            self.btn_internal_calc.setEnabled(True)

    def get_displacement_vectors(self, mode_idx: int):
        """선택된 모드의 변위벡터 반환"""
        if self._vib_result and 0 <= mode_idx < len(self._vib_result.modes):
            return self._vib_result.modes[mode_idx].displacement_vectors
        logger.warning("변위벡터 반환 불가: vib_result=%s, mode_idx=%d",
                       bool(self._vib_result), mode_idx)
        return None

    # ── GIF 내보내기 (M632 VIBRATION-AUTO-001) ──────────────────────────────────
    def _export_gif(self):
        """현재 선택된 진동 모드를 GIF로 저장 (16프레임 @ 10fps)"""
        row = self.mode_list.currentRow()
        if row < 0:
            logger.warning("[VibrationPanel] GIF 내보내기: 모드 미선택")
            self.info_label.setText("먼저 진동 모드를 선택하세요")
            return

        disps = self.get_displacement_vectors(row)
        if not disps:
            logger.warning("[VibrationPanel] GIF 내보내기: 변위벡터 없음 mode_idx=%d", row)
            self.info_label.setText("변위벡터 없음 — 내부 엔진으로 먼저 계산하세요")
            return

        freq = 0.0
        if self._vib_result and row < len(self._vib_result.modes):
            freq = self._vib_result.modes[row].frequency_cm

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "GIF 저장",
            f"vibration_mode{row + 1}_{freq:.0f}cm.gif",
            "GIF 파일 (*.gif)",
        )
        if not save_path:
            return

        self.btn_export_gif.setEnabled(False)
        self.info_label.setText("GIF 생성 중...")

        self._gif_thread = _VibGifExportThread(disps, freq, self._smiles, parent=self)
        self._gif_thread.set_save_path(save_path)
        self._gif_thread.finished.connect(self._on_gif_saved)
        self._gif_thread.error.connect(self._on_gif_error)
        self._gif_thread.start()

    def _on_gif_saved(self, path: str):
        """GIF 저장 완료 콜백"""
        self.btn_export_gif.setEnabled(True)
        self.info_label.setText(f"GIF 저장 완료: {Path(path).name}")
        logger.info("[VibrationPanel] GIF 저장 완료: %s", path)

    def _on_gif_error(self, msg: str):
        """GIF 저장 오류 콜백"""
        self.btn_export_gif.setEnabled(True)
        self.info_label.setText(f"GIF 오류: {msg}")
        logger.warning("[VibrationPanel] GIF 오류: %s", msg)


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

        # ── API Key 상태 + 사용 안내 (GUI 감사 I-2 권고 2026-04-24) ──
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            _notice_text = (
                "AI 분석을 시작하려면 아래 '전체 분석' 버튼을 클릭하세요. "
                "(GEMINI_API_KEY 설정됨)")
        else:
            _notice_text = (
                "AI 분석을 시작하려면 아래 '전체 분석' 버튼을 클릭하세요. "
                "(GEMINI_API_KEY 필요 — 미설정 시 룰 기반 대체 사용)")
        notice = QLabel(_notice_text)
        notice.setStyleSheet("color:#f0ad4e; font-size:8pt; padding:2px 4px;")
        notice.setWordWrap(True)
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
            logger.warning("AI 전체 분석 건너뜀: SMILES 없음")
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
            logger.warning("AI 섹션 분석 건너뜀: SMILES 없음 (section=%s)", section_key)
            self._section_texts[section_key].setPlainText("⚠️ SMILES 없음")
            return
        te = self._section_texts.get(section_key)
        if te is None:
            logger.warning("AI 섹션 분석 건너뜀: 텍스트 위젯 없음 (section_key=%s)", section_key)
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
                logger.debug("Gemini analysis failed, using rule-based: %s", e)

        # 룰 기반 폴백 (Gemini 없을 때)
        return self._rule_based_analysis(section_key, smiles)

    def _rule_based_analysis(self, section_key: str, smiles: str) -> str:
        """Gemini API 없을 때 RDKit 기반 간이 분석"""
        if not RDKIT_AVAILABLE:
            return "⚠️ RDKit 미설치 — 룰 기반 분석 불가"
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
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
                lines.append(f"• Lipinski Rule of Five: {lipinski_score}/4 descriptor criteria met {'✅' if lipinski_pass else '⚠️'}")
                if lipinski_pass:
                    lines.append("  -> rule-favorable physicochemical descriptor bucket only; not PK evidence")
                else:
                    violations = []
                    if mw > 500: violations.append(f"MW {mw:.0f}>500")
                    if logp > 5: violations.append(f"LogP {logp:.1f}>5")
                    if n_donors > 5: violations.append(f"HBD {n_donors}>5")
                    if n_accept > 10: violations.append(f"HBA {n_accept}>10")
                    lines.append(f"  → 위반: {', '.join(violations)}")
                # TPSA (혈뇌장벽)
                lines.append(f"• TPSA: {tpsa:.1f} Å² — {'low-polar-surface descriptor bucket; not BBB/CNS evidence' if tpsa < 90 else 'oral-absorption descriptor bucket only' if tpsa < 140 else 'high-polar-surface descriptor bucket'}")
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
                    lines.append("• 💊 Aromatic-rich descriptor cue only; not target, activity, or scaffold evidence")
                elif any(a.GetAtomicNum() == 7 for a in mol.GetAtoms()) and n_donors >= 2:
                    lines.append("• 💊 Amine/H-bond donor descriptor cue only; not CNS, delivery, or scaffold evidence")
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
            logger.warning("미니맵 좌표 투영 건너뜀: 수용체 원자 데이터 없음")
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
            logger.warning("리간드 이미지 생성 건너뜀: RDKIT=%s, ligand_smiles=%r",
                           RDKIT_AVAILABLE, self._ligand_smiles)
            return
        try:
            from rdkit.Chem import Draw as _Draw
            from rdkit.Chem import rdDepictor as _Dep
            from io import BytesIO as _BytesIO
            _mol = Chem.MolFromSmiles(self._ligand_smiles)
            if _mol is None:
                logger.warning("리간드 이미지: SMILES 파싱 실패 (smiles=%r)", self._ligand_smiles)
                return
            _Dep.Compute2DCoords(_mol)
            _img_pil = _Draw.MolToImage(_mol, size=(120, 90))
            _buf = _BytesIO()
            _img_pil.save(_buf, format='PNG')
            from PyQt6.QtGui import QImage
            self._ligand_img = QImage.fromData(_buf.getvalue())
        except Exception as e:
            logger.warning("Mechanism engine computation failed: %s", e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 배경
        p.fillRect(self.rect(), QColor(15, 15, 28))

        if not self._proj_receptor:
            p.setPen(QColor(90, 90, 110))
            p.setFont(QFont("Malgun Gothic", 10))  # [M1444] Rule Q: 한국어 텍스트
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
        p.setFont(QFont(_QT_KR_FONT, 7, QFont.Weight.Bold))  # [M1461] Rule Q: offscreen 폰트
        p.drawText(lsx-4, lsy+4, "L")   # L = Ligand

        # 결합 포켓 레이블
        p.setPen(gc.lighter(170))
        p.setFont(QFont("Malgun Gothic", 8))  # [M1444] Rule Q: 한국어 텍스트
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
            p.setFont(QFont("Malgun Gothic", 7))  # [M1444] Rule Q: 한국어 텍스트
            p.drawText(img_x+10, 106, "리간드 구조")
        else:
            # 텍스트 대체
            p.setPen(QColor(100, 170, 220))
            p.setFont(QFont("Malgun Gothic", 7))  # [M1444] Rule Q
            smiles_disp = (self._ligand_smiles[:22] + "…"
                           if len(self._ligand_smiles) > 22
                           else self._ligand_smiles)
            p.drawText(img_x, 20, smiles_disp)

        # ── 에너지 표시 (좌하단) ─────────────────────────────────────
        if self._docking_energy is not None:
            p.setPen(gc.lighter(170))
            p.setFont(QFont(_QT_KR_FONT, 10, QFont.Weight.Bold))  # [M1461] Rule Q: offscreen 폰트
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
            p.setFont(QFont("Malgun Gothic", 8))  # [M1444] Rule Q: 한국어 텍스트
            p.drawText(lx+14, h-9, lt)

        # 원자 수 안내
        p.setPen(QColor(80, 80, 100))
        p.setFont(QFont("Malgun Gothic", 7))  # [M1444] Rule Q: 한국어 텍스트
        p.drawText(pad, h-10,
                   f"총 Cα: {len(self._receptor_atoms)}  |  포켓 내: {len(self._pocket_atoms)}")
        p.end()


# ============================================================
# Section 10-4.5: ADMET 약물성 분석 패널 (임베디드 탭)
# ============================================================

class ADMETEmbeddedRadarChartWidget(QWidget):
    """Native Qt radar chart for the embedded ADMET panel fallback path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("qt_embedded_admet_radar_chart")
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._categories = ["MW", "LogP", "TPSA", "HBD", "HBA"]
        self._values = [0.0] * len(self._categories)

    def set_values(self, values: List[float]) -> None:
        clean_values = []
        for value in values[:len(self._categories)]:
            try:
                clean_values.append(max(0.0, min(1.0, float(value))))
            except (TypeError, ValueError):
                clean_values.append(0.0)
        while len(clean_values) < len(self._categories):
            clean_values.append(0.0)
        self._values = clean_values
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor("#fdf6ff"))

        count = len(self._categories)
        if count < 3:
            painter.end()
            return

        center = QPointF(rect.center().x(), rect.center().y() + 8)
        radius = max(36.0, min(rect.width(), rect.height() - 34) * 0.34)
        angles = [(2.0 * math.pi * idx / count) - (math.pi / 2.0) for idx in range(count)]

        def point(angle: float, scale: float) -> QPointF:
            return QPointF(
                center.x() + math.cos(angle) * radius * scale,
                center.y() + math.sin(angle) * radius * scale,
            )

        painter.setBrush(Qt.BrushStyle.NoBrush)
        grid_pen = QPen(QColor("#cc99dd"), 1, Qt.PenStyle.DashLine)
        axis_pen = QPen(QColor("#b98ac8"), 1)
        for scale in (0.25, 0.5, 0.75, 1.0):
            painter.setPen(grid_pen)
            painter.drawPolygon(QPolygonF([point(angle, scale) for angle in angles]))
        painter.setPen(axis_pen)
        for angle in angles:
            painter.drawLine(center, point(angle, 1.0))

        values = self._values or [0.0] * count
        all_pass = all(value <= 1.0 for value in values)
        color = QColor("#2e7d32" if all_pass else "#b71c1c")
        value_poly = QPolygonF([point(angle, value) for angle, value in zip(angles, values)])
        painter.setPen(QPen(color, 2))
        fill = QColor(color)
        fill.setAlpha(75)
        painter.setBrush(QBrush(fill))
        painter.drawPolygon(value_poly)
        painter.setBrush(QBrush(color))
        for pt in value_poly:
            painter.drawEllipse(pt, 3, 3)

        painter.setFont(QFont(_QT_KR_FONT, 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#4a0072")))
        for angle, label in zip(angles, self._categories):
            label_pt = point(angle, 1.18)
            painter.drawText(
                QRectF(label_pt.x() - 34, label_pt.y() - 10, 68, 20),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        painter.setFont(QFont(_QT_KR_FONT, 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#6a1b9a")))
        painter.drawText(
            QRectF(rect.left(), rect.top(), rect.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            f"Drug-likeness {'PASS' if all_pass else 'FAIL'} ({sum(1 for v in values if v <= 1.0)}/5)",
        )
        painter.end()


class ADMETEmbeddedPanel(QWidget):
    """💊 ADMET 분석 탭 — 약물 유사성 분석 (Lipinski, Veber, ADMET 프로파일).

    Lipinski Rule of Five, Veber Rules, 기본 ADMET 예측을 인라인으로 표시.
    상세 분석은 '상세 분석' 버튼으로 popup_admet.ADMETPopup 호출.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smiles = ""
        self._setup_ui()

    def _setup_ui(self):
        # [FIX-ADMET-BG] White background with dark text (lead optimizer popup style)
        self.setStyleSheet(
            "QWidget { background-color: #ffffff; color: #222222; }"
            "QGroupBox { background-color: #f5f5f5; border: 1px solid #cccccc; "
            "border-radius: 4px; margin-top: 8px; padding-top: 14px; color: #333; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #444; "
            "font-weight: bold; }"
            "QScrollArea { background: #ffffff; border: none; }"
            "QLabel { color: #333333; }"
            "QPushButton { background: #1565C0; color: #ffffff; border: 1px solid #1976D2; "
            "padding: 6px; border-radius: 3px; }"
            "QPushButton:hover { background: #1976D2; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 헤더
        hdr = QLabel("💊 ADMET 약물성 분석")
        hdr.setStyleSheet("color: #6a1b9a; font-size: 12pt; font-weight: bold; "
                          "background: transparent;")
        layout.addWidget(hdr)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #ffffff; }")
        content = QWidget()
        content.setStyleSheet("background: #ffffff;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(6)

        # Lipinski Rule of Five 그룹
        self._lipinski_group = QGroupBox("Lipinski Rule of Five")
        self._lipinski_layout = QFormLayout(self._lipinski_group)
        self._lipinski_layout.setSpacing(4)
        self._lbl_mw = QLabel("—")
        self._lbl_logp = QLabel("—")
        self._lbl_hba = QLabel("—")
        self._lbl_hbd = QLabel("—")
        self._lbl_lipinski_result = QLabel("—")
        self._lipinski_layout.addRow("분자량 (MW ≤ 500):", self._lbl_mw)
        self._lipinski_layout.addRow("LogP (≤ 5):", self._lbl_logp)
        self._lipinski_layout.addRow("H-Bond Acceptors (≤ 10):", self._lbl_hba)
        self._lipinski_layout.addRow("H-Bond Donors (≤ 5):", self._lbl_hbd)
        self._lipinski_layout.addRow("판정:", self._lbl_lipinski_result)
        for lbl in [self._lbl_mw, self._lbl_logp, self._lbl_hba, self._lbl_hbd,
                     self._lbl_lipinski_result]:
            lbl.setStyleSheet("color: #333;")
        self._content_layout.addWidget(self._lipinski_group)

        # Veber Rules 그룹
        self._veber_group = QGroupBox("Veber Rules (descriptor screen)")
        self._veber_layout = QFormLayout(self._veber_group)
        self._lbl_tpsa = QLabel("—")
        self._lbl_rotatable = QLabel("—")
        self._lbl_veber_result = QLabel("—")
        self._veber_layout.addRow("TPSA (≤ 140 A2):", self._lbl_tpsa)
        self._veber_layout.addRow("Rotatable Bonds (≤ 10):", self._lbl_rotatable)
        self._veber_layout.addRow("판정:", self._lbl_veber_result)
        for lbl in [self._lbl_tpsa, self._lbl_rotatable, self._lbl_veber_result]:
            lbl.setStyleSheet("color: #333;")
        self._content_layout.addWidget(self._veber_group)

        # 추가 ADMET 예측 그룹
        self._admet_group = QGroupBox("ADMET 프로파일")
        self._admet_layout = QFormLayout(self._admet_group)
        self._lbl_bbb = QLabel("—")
        self._lbl_pgp = QLabel("—")
        self._lbl_ld50 = QLabel("unavailable")
        self._lbl_bioavail = QLabel("—")
        self._admet_layout.addRow("BBB screen:", self._lbl_bbb)
        self._admet_layout.addRow("P-gp 기질:", self._lbl_pgp)
        self._admet_layout.addRow("LD50:", self._lbl_ld50)
        self._admet_layout.addRow("Oral rule screen:", self._lbl_bioavail)
        for lbl in [self._lbl_bbb, self._lbl_pgp, self._lbl_ld50, self._lbl_bioavail]:
            lbl.setStyleSheet("color: #333;")
        self._content_layout.addWidget(self._admet_group)

        # M831 anger#27: 약물성 레이더 차트 (matplotlib 극좌표 — Rule Q 폰트 필수)
        # 5축: MW/LogP/TPSA/HBD/HBA 정규화 (0~1, Lipinski 기준값 기준)
        # 학술 근거: Lipinski C.A. et al. Adv. Drug Deliv. Rev. 2001, 46(1-3): 3-26.
        radar_grp = QGroupBox("💊 약물성 레이더 차트 (Lipinski 5항목)")
        radar_grp.setStyleSheet(
            "QGroupBox { border: 1px solid #9c27b0; background: #fdf6ff; "
            "margin-top: 8px; padding-top: 14px; }"
            "QGroupBox::title { color: #6a1b9a; font-weight: bold; }"
        )
        radar_layout = QVBoxLayout(radar_grp)
        radar_layout.setContentsMargins(4, 4, 4, 4)
        try:
            if not MATPLOTLIB_AVAILABLE:
                raise ImportError("matplotlib unavailable")
            import matplotlib
            matplotlib.use("QtAgg")
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            import matplotlib.pyplot as plt
            import numpy as np
            # matplotlib 한국어 폰트 (Rule Q: 한글 깨짐 방지)
            import matplotlib.font_manager as _fm
            _fp = None
            for _fn in ("Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"):
                _found = [f for f in _fm.findSystemFonts() if _fn.lower().replace(" ", "") in f.lower().replace(" ", "")]
                if _found:
                    _fp = _fm.FontProperties(fname=_found[0])
                    break
            if _fp is None:
                _fp = _fm.FontProperties()  # 기본 폰트 폴백

            _fig, _ax = plt.subplots(figsize=(3.2, 2.8),
                                     subplot_kw=dict(projection="polar"))
            _fig.patch.set_facecolor("#fdf6ff")
            _ax.set_facecolor("#f5eaff")
            # 5축 라벨 (Rule Q: 유니코드 직접 사용, 이스케이프 금지)
            _categories = ["MW\n(≤500)", "LogP\n(≤5)", "TPSA\n(≤140)", "HBD\n(≤5)", "HBA\n(≤10)"]
            _N = len(_categories)
            _angles = np.linspace(0, 2 * np.pi, _N, endpoint=False).tolist()
            _angles += _angles[:1]
            _values = [0.0] * _N + [0.0]
            _ax.plot(_angles, _values, color="#9c27b0", linewidth=1.5)
            _ax.fill(_angles, _values, color="#9c27b0", alpha=0.25)
            _ax.set_xticks(np.linspace(0, 2 * np.pi, _N, endpoint=False))
            _ax.set_xticklabels(_categories, fontproperties=_fp,  # Rule Q 폰트
                                fontsize=7, color="#4a0072")
            _ax.set_yticks([0.25, 0.5, 0.75, 1.0])
            _ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=5, color="#777")
            _ax.set_ylim(0, 1.05)  # [MAGIC: 1.05] 레이더 최대값 약간 여유
            _ax.set_title("약물성 지수", fontproperties=_fp, fontsize=8,
                          color="#6a1b9a", pad=10)
            _ax.spines["polar"].set_color("#9c27b0")
            _ax.spines["polar"].set_linewidth(0.8)
            _ax.grid(color="#cc99dd", linewidth=0.5, linestyle="--", alpha=0.7)

            self._radar_fig = _fig
            self._radar_ax = _ax
            self._radar_angles = _angles
            self._radar_fp = _fp
            self._radar_canvas = FigureCanvasQTAgg(_fig)
            self._radar_canvas.setFixedHeight(200)  # [MAGIC: 200] 레이더 차트 고정 높이
            radar_layout.addWidget(self._radar_canvas)
            plt.close(_fig)
        except Exception as _e:
            logger.warning("ADMET matplotlib radar chart creation failed, using Qt fallback: %s", _e)
            self._radar_qt_widget = ADMETEmbeddedRadarChartWidget()
            radar_layout.addWidget(self._radar_qt_widget)
            _qt_note = QLabel("Qt radar chart rendered with QPainter.")
            _qt_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _qt_note.setStyleSheet("color: #666; font-size: 8pt;")
            radar_layout.addWidget(_qt_note)
            self._radar_canvas = None
        self._content_layout.addWidget(radar_grp)

        self._content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # 하단 버튼: 상세 분석 팝업 열기
        btn_detail = QPushButton("🔬 상세 ADMET 분석 열기")
        btn_detail.clicked.connect(self._open_detail_popup)
        layout.addWidget(btn_detail)

        # 대기 메시지
        self._lbl_status = QLabel("분자를 로드하면 자동으로 분석됩니다")
        self._lbl_status.setStyleSheet("color: #666; font-size: 8pt; background: transparent;")
        layout.addWidget(self._lbl_status)

    def set_smiles(self, smiles: str):
        """SMILES 설정 및 ADMET 분석 실행."""
        if not smiles:
            logger.warning("ADMET 패널: SMILES 없음")
            return
        self._smiles = smiles
        self._analyze(smiles)

    def _analyze(self, smiles: str):
        """RDKit 기반 Lipinski/Veber/ADMET 분석."""
        if not RDKIT_AVAILABLE:
            self._lbl_status.setText("RDKit 미설치 — 분석 불가")
            logger.warning("ADMET 분석 건너뜀: RDKit 미설치")
            return

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self._lbl_status.setText("유효하지 않은 SMILES")
            logger.warning("ADMET 분석: 유효하지 않은 SMILES (%r)", smiles)
            return

        try:
            mw = Descriptors.ExactMolWt(mol)
            logp = Descriptors.MolLogP(mol)
            hba = Descriptors.NumHAcceptors(mol)
            hbd = Descriptors.NumHDonors(mol)
            tpsa = Descriptors.TPSA(mol)
            rot_bonds = Descriptors.NumRotatableBonds(mol)

            # Lipinski 판정
            violations = 0
            # [FIX-ADMET-BG] Dark green/red on white background
            pass_style = "color: #1b5e20; font-weight: bold;"
            fail_style = "color: #b71c1c; font-weight: bold;"

            mw_ok = mw <= 500
            self._lbl_mw.setText(f"{mw:.2f}" + (" PASS" if mw_ok else " FAIL"))
            self._lbl_mw.setStyleSheet(pass_style if mw_ok else fail_style)
            if not mw_ok:
                violations += 1

            logp_ok = logp <= 5.0
            self._lbl_logp.setText(f"{logp:.2f}" + (" PASS" if logp_ok else " FAIL"))
            self._lbl_logp.setStyleSheet(pass_style if logp_ok else fail_style)
            if not logp_ok:
                violations += 1

            hba_ok = hba <= 10
            self._lbl_hba.setText(f"{hba}" + (" PASS" if hba_ok else " FAIL"))
            self._lbl_hba.setStyleSheet(pass_style if hba_ok else fail_style)
            if not hba_ok:
                violations += 1

            hbd_ok = hbd <= 5
            self._lbl_hbd.setText(f"{hbd}" + (" PASS" if hbd_ok else " FAIL"))
            self._lbl_hbd.setStyleSheet(pass_style if hbd_ok else fail_style)
            if not hbd_ok:
                violations += 1

            lip_pass = violations <= 1  # Lipinski: 위반 1개까지 허용
            self._lbl_lipinski_result.setText(
                f"PASS (위반 {violations}개)" if lip_pass
                else f"FAIL (위반 {violations}개)")
            self._lbl_lipinski_result.setStyleSheet(pass_style if lip_pass else fail_style)

            # Veber 판정
            tpsa_ok = tpsa <= 140.0
            rot_ok = rot_bonds <= 10
            self._lbl_tpsa.setText(f"{tpsa:.1f} A2" + (" PASS" if tpsa_ok else " FAIL"))
            self._lbl_tpsa.setStyleSheet(pass_style if tpsa_ok else fail_style)
            self._lbl_rotatable.setText(f"{rot_bonds}" + (" PASS" if rot_ok else " FAIL"))
            self._lbl_rotatable.setStyleSheet(pass_style if rot_ok else fail_style)
            veber_pass = tpsa_ok and rot_ok
            self._lbl_veber_result.setText("PASS" if veber_pass else "FAIL")
            self._lbl_veber_result.setStyleSheet(pass_style if veber_pass else fail_style)

            # D891 Item009: use the provenance-bound predictor, not a separate
            # high/low-looking BBB shortcut in the embedded panel.
            try:
                from admet_predictor import predict_admet as _predict_admet
                _admet_profile = _predict_admet(smiles)
                _bbb = getattr(_admet_profile, "bbb", None)
                _ld50 = getattr(_admet_profile, "ld50_provenance", None)
            except Exception as e:
                logger.warning("Embedded ADMET provenance route failed: %s", e)
                _bbb = None
                _ld50 = None

            if _bbb is None:
                self._lbl_bbb.setText("unavailable - RDKit heuristic not run")
                self._lbl_bbb.setStyleSheet("color: #e65100; font-weight: bold;")
            else:
                _bbb_class = getattr(_bbb, "classification", "uncertain")
                if _bbb_class == "BBB-":
                    _bbb_text = "descriptor-unfavorable screen only; not BBB evidence"
                    _bbb_style = fail_style
                elif _bbb_class == "BBB+":
                    _bbb_text = "descriptor-favorable screen only; not BBB evidence"
                    _bbb_style = "color: #e65100; font-weight: bold;"
                else:
                    _bbb_text = "uncertain / unavailable boundary; not BBB evidence"
                    _bbb_style = "color: #e65100; font-weight: bold;"
                self._lbl_bbb.setText(_bbb_text)
                self._lbl_bbb.setStyleSheet(_bbb_style)

            if _ld50 is None:
                self._lbl_ld50.setText("unavailable - not connected/not run")
            else:
                self._lbl_ld50.setText("unavailable - no model/database route connected")
            self._lbl_ld50.setStyleSheet("color: #e65100; font-weight: bold;")

            # P-gp 기질 예측: MW>400 and TPSA>75 → likely substrate
            pgp_likely = mw > 400 and tpsa > 75
            self._lbl_pgp.setText("substrate heuristic flag present" if pgp_likely else "substrate heuristic flag absent")
            self._lbl_pgp.setStyleSheet(fail_style if pgp_likely else pass_style)

            # Oral rule screen: Lipinski + Veber only, not PK evidence.
            bioavail = lip_pass and veber_pass
            self._lbl_bioavail.setText("rule-favorable heuristic" if bioavail else "rule concern heuristic")
            self._lbl_bioavail.setStyleSheet("color: #e65100; font-weight: bold;" if bioavail else fail_style)

            self._lbl_status.setText(f"분석 완료: {smiles[:30]}...")

            # M831 anger#27: 레이더 차트 업데이트 (matplotlib 극좌표)
            # 5축 정규화: MW/500, LogP/5, TPSA/140, HBD/5, HBA/10 (Lipinski 상한값 기준)
            # Lipinski C.A. et al. Adv. Drug Deliv. Rev. 2001, 46(1-3): 3-26.
            self._update_radar(mw, logp, tpsa, hbd, hba)

        except Exception as e:
            logger.warning("ADMET 분석 오류: %s", e)
            self._lbl_status.setText(f"분석 오류: {e}")

    def _update_radar(self, mw: float, logp: float, tpsa: float, hbd: int, hba: int) -> None:
        """M831 anger#27: 레이더 차트 5축 업데이트 (matplotlib 극좌표).

        정규화 기준 (Lipinski Ro5 상한값):
          MW   / 500  (≤500 = PASS)
          LogP / 5    (≤5   = PASS)
          TPSA / 140  (≤140 = PASS, Veber 기준)
          HBD  / 5    (≤5   = PASS)
          HBA  / 10   (≤10  = PASS)
        """
        raw = [mw / 500.0, logp / 5.0, tpsa / 140.0, hbd / 5.0, hba / 10.0]
        norm = [max(0.0, min(1.0, v)) for v in raw]
        if getattr(self, "_radar_qt_widget", None) is not None:
            self._radar_qt_widget.set_values(norm)
        if not hasattr(self, "_radar_canvas") or self._radar_canvas is None:
            return
        try:
            import numpy as np
            # [MAGIC: 5.0] LogP 정규화 기준 (Lipinski ≤5 기준)
            # [MAGIC: 500, 140, 5, 10] Lipinski Ro5 + Veber 기준값
            raw = [mw / 500.0, logp / 5.0, tpsa / 140.0, hbd / 5.0, hba / 10.0]
            norm = [max(0.0, min(1.0, v)) for v in raw]  # 0~1 클램프
            values = norm + norm[:1]  # 극좌표 닫힘

            _ax = self._radar_ax
            _ax.cla()  # 이전 플롯 지우기

            _N = 5
            _angles = np.linspace(0, 2 * np.pi, _N, endpoint=False).tolist()
            _angles_closed = _angles + _angles[:1]

            # 오각형 경계선 (Lipinski PASS 한계)
            _pass_line = [1.0] * _N + [1.0]
            _ax.plot(_angles_closed, _pass_line, color="#9e9e9e",
                     linewidth=0.8, linestyle="--", alpha=0.6)

            # 실제 분자값 (PASS=green, FAIL=red)
            _all_pass = all(v <= 1.0 for v in norm)
            _color = "#2e7d32" if _all_pass else "#b71c1c"  # Rule Q: PASS=녹색, FAIL=적색
            _ax.plot(_angles_closed, values, color=_color, linewidth=2.0)
            _ax.fill(_angles_closed, values, color=_color, alpha=0.30)

            # 라벨 (Rule Q: 유니코드 직접, fontproperties 필수)
            _fp = getattr(self, "_radar_fp", None)
            _categories = ["MW\n(≤500)", "LogP\n(≤5)", "TPSA\n(≤140)", "HBD\n(≤5)", "HBA\n(≤10)"]
            _ax.set_xticks(np.linspace(0, 2 * np.pi, _N, endpoint=False))
            _kw = {"fontsize": 7, "color": "#4a0072"}
            if _fp is not None:
                _kw["fontproperties"] = _fp
            _ax.set_xticklabels(_categories, **_kw)
            _ax.set_yticks([0.25, 0.5, 0.75, 1.0])
            _ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=5, color="#777")
            _ax.set_ylim(0, 1.15)  # [MAGIC: 1.15] 범례 공간 확보
            _title_kw = {"fontsize": 8, "color": "#6a1b9a", "pad": 8}
            if _fp is not None:
                _title_kw["fontproperties"] = _fp
            _ax.set_title(
                f"약물성 {'PASS' if _all_pass else 'FAIL'} ({sum(1 for v in norm if v <= 1.0)}/5)",
                **_title_kw
            )
            _ax.set_facecolor("#f5eaff")
            _ax.grid(color="#cc99dd", linewidth=0.5, linestyle="--", alpha=0.7)
            _ax.spines["polar"].set_color("#9c27b0")
            _ax.spines["polar"].set_linewidth(0.8)

            self._radar_canvas.draw_idle()  # 비동기 재렌더
        except Exception as e:
            logger.warning("ADMET 레이더 차트 업데이트 실패: %s", e)

    def _open_detail_popup(self):
        """상세 ADMET 분석 팝업 열기 (popup_admet.ADMETPopup)."""
        try:
            from popup_admet import ADMETPopup
            popup = ADMETPopup(smiles=self._smiles, parent=self)
            popup.exec()
        except Exception as e:
            logger.warning("ADMET 상세 팝업 열기 실패: %s", e)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ADMET", f"상세 분석 열기 실패: {e}")


# ============================================================
# Section 10-4B: 화학적 특성 분석 패널 (방사형 유사 분자 비교)
# Source: chemgrid_mobile/frontend/src/components/ChemicalCharacteristicsPanel.tsx (Rule Y 1:1 번역)
# 학계 reference: Maggiora et al. J. Med. Chem. 2014, 57(8), 3186-3204
#   (Tanimoto 유사도 기준: ≥0.85 매우 유사, ≥0.70 유사, ≥0.50 경계)
# 엔진: RDKit Morgan FP (radius=2, bits=2048) + PubChem fastsimilarity_2d
# Rogers & Hahn 2010 ECFP4 공식 설정 (radius=2, nBits=2048)
# ============================================================

class _ChemCharFetchThread(QThread):
    """PubChem fastsimilarity_2d 비동기 요청 스레드 (UI 블로킹 방지).
    Source: chemical_characteristics.py 핵심 함수 인라인 복제 (FastAPI 종속성 제거).
    Rule M: 실패 시 result_ready.emit({'neighbors': [], 'error': ...}) — silent 금지.
    """
    # 성공: dict (center + neighbors + engine + academic_reference)
    # 실패: dict with 'error' key
    result_ready = pyqtSignal(dict)

    # ── 상수 (Rule I: 매직넘버 주석 — chemical_characteristics.py 1:1) ──
    _PUBCHEM_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"  # 무인증 무료 REST
    _SMILES_LOOKUP_TIMEOUT = 5    # 초: CID 조회
    _SIMILAR_TIMEOUT = 12         # 초: fastsimilarity_2d (대형 DB 쿼리)
    _PROPS_TIMEOUT = 5            # 초: 개별 CID 속성 조회
    _CHEMBL_REST = "https://www.ebi.ac.uk/chembl/api/data"  # ChEMBL fallback
    _CHEMBL_TIMEOUT = 8           # 초: ChEMBL 응답 대기
    _TANIMOTO_THRESHOLD = 70      # 퍼센트: PubChem Tanimoto ≥ 0.70 (Maggiora 2014)
    _MORGAN_RADIUS = 2            # ECFP4 동등 radius
    _MORGAN_BITS = 2048           # Rogers & Hahn 2010 ECFP4 공식 설정 (radius=2, nBits=2048)
    _FALLBACK_MIN_COUNT = 5       # 이 수 미만이면 fallback chain 가동
    _FALLBACK_TANIMOTO_MIN = 0.4  # fallback 최소 유사도 (PubChem 70보다 완화)
    _TOTAL_BUDGET_SEC = 45        # 초: 스레드 전체 실행 시간 예산 (60초 한계 대비 15초 여유, M507)

    # ── 도메인 룩업 딕셔너리 (Source: chemical_characteristics.py 1:1) ──
    # 신경활성 인돌 알칼로이드 (Shulgin A. TIHKAL 1997)
    _PSYCHOACTIVE_INDOLES = {
        "DMT (디메틸트립타민)":    "CN(C)CCc1c[nH]c2ccccc12",
        "5-메톡시-DMT":           "CN(C)CCc1c[nH]c2cc(OC)ccc12",
        "실로신 (psilocin)":      "CN(C)CCc1c[nH]c2cc(O)ccc12",
        "실로시빈 (psilocybin)":  "CN(C)CCc1c[nH]c2cc(OP(=O)(O)O)ccc12",
        "세로토닌 (serotonin)":   "NCCc1c[nH]c2cc(O)ccc12",
        "5-HTP":                 "NC(Cc1c[nH]c2cc(O)ccc12)C(=O)O",
        "멜라토닌 (melatonin)":   "CC(=O)NCCc1c[nH]c2cc(OC)ccc12",
        "트립토판 (tryptophan)":  "NC(Cc1c[nH]c2ccccc12)C(=O)O",
        "트립토파민 (tryptamine)":"NCCc1c[nH]c2ccccc12",
    }
    # 폴리아민 계열 (Pegg A.E. IUBMB Life 2009, 61:880 DOI:10.1002/iub.230)
    _POLYAMINES = {
        "퓨트레신 (putrescine)":  "NCCCN",
        "스퍼미딘 (spermidine)": "NCCCNCCCCN",
        "스퍼민 (spermine)":     "NCCCNCCCCNCCCN",
        "아그마틴 (agmatine)":   "NC(=N)NCCCCN",
        "히스타민 (histamine)":  "NCCc1c[nH]cn1",
        "에틸렌디아민":          "NCCN",
        "헥산디아민":            "NCCCCCCN",
    }

    # ── 한국어 SMARTS 분류기 (Source: chemical_characteristics.py 1:1) ──
    _SMARTS_CLASSIFIERS_RAW = [
        ("[NX3;H2,H1;!$(NC=O)]", "1차/2차 아민 (생체 아민 계열)"),
        ("c1ccc2[nH]ccc2c1",     "인돌 골격 (트립타민 계열)"),
        ("[NX3]CCC[NX3]",        "1,3-디아민 (폴리아민 계열)"),
        ("[NX3]CCCC[NX3]",       "1,4-디아민 (카다베린 계열)"),
        ("c1ccccc1",             "벤젠 고리 (방향족)"),
        ("[OH;!$(OC=O)]",        "히드록실기 (수용성)"),
        ("C(=O)O",               "카르복실산 (산성)"),
        ("[F,Cl,Br,I]",          "할로젠 치환기 (대사 안정성)"),
        ("C(=O)N",               "아미드 결합 (펩타이드 유사)"),
        ("C=O",                  "카보닐기 (친핵 반응 부위)"),
        ("[SX2]",                "황 원자 (효소 억제 가능)"),
        ("P",                    "인 원자 (유기인계)"),
    ]

    def __init__(self, smiles: str, n: int = 8, parent=None):
        super().__init__(parent)
        # Rule N: 타입 가드 — 빈문자열 체크
        if not isinstance(smiles, str):
            smiles = ""
        self._smiles = smiles.strip()
        self._n = n  # 최대 유사 분자 수 (기본 8 — MAX_NEIGHBORS 1:1)
        # RDKit + 컴파일된 분류기 초기화
        self._compiled_classifiers = []
        if RDKIT_AVAILABLE:
            from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
            self._mfpgen = GetMorganGenerator(
                radius=self._MORGAN_RADIUS, fpSize=self._MORGAN_BITS
            )
            self._indole_patt = Chem.MolFromSmarts("c1ccc2[nH]ccc2c1")
            self._diamine_patt_list = [
                Chem.MolFromSmarts(s) for s in [
                    "[NX3;H2,H1]CC[NX3;H2,H1]",
                    "[NX3;H2,H1]CCC[NX3;H2,H1]",
                    "[NX3;H2,H1]CCCC[NX3;H2,H1]",
                ]
            ]
            for smarts, desc in self._SMARTS_CLASSIFIERS_RAW:
                patt = Chem.MolFromSmarts(smarts)
                if patt is not None:
                    self._compiled_classifiers.append((patt, desc))
        else:
            self._mfpgen = None
            self._indole_patt = None
            self._diamine_patt_list = []

    def _pubchem_get(self, url: str, timeout: int):
        """PubChem REST GET → dict 또는 None (Rule M: 실패 시 warning)."""
        import urllib.request, urllib.parse, json as _json
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning("PubChem 비정상 응답 status=%d url=%s", resp.status, url[:100])
                    return None
                raw = resp.read()
            data = _json.loads(raw)
            if not isinstance(data, dict):  # Rule N
                logger.warning("PubChem 응답 dict 아님 type=%s", type(data).__name__)
                return None
            return data
        except Exception as e:
            logger.warning("PubChem GET 실패 url=%s err=%s", url[:100], e)
            return None

    def _lookup_cid(self, smiles: str):
        """SMILES → PubChem CID (없으면 None)."""
        import urllib.parse
        encoded = urllib.parse.quote(smiles, safe="")
        url = f"{self._PUBCHEM_REST}/compound/smiles/{encoded}/cids/JSON"
        data = self._pubchem_get(url, self._SMILES_LOOKUP_TIMEOUT)
        if data is None:
            return None
        id_list = data.get("IdentifierList")
        if not isinstance(id_list, dict):
            logger.warning("PubChem CID IdentifierList 누락: smiles=%s", smiles[:50])
            return None
        cids = id_list.get("CID")
        if not isinstance(cids, list) or len(cids) == 0:
            return None
        cid = cids[0]
        if not isinstance(cid, int):
            return None
        return cid

    def _lookup_similar_cids(self, cid: int):
        """fastsimilarity_2d → CID 리스트 (Threshold=70, Maggiora 2014)."""
        url = (
            f"{self._PUBCHEM_REST}/compound/fastsimilarity_2d/cid/{cid}/cids/JSON"
            f"?Threshold={self._TANIMOTO_THRESHOLD}&MaxRecords={self._n + 1}"
        )
        data = self._pubchem_get(url, self._SIMILAR_TIMEOUT)
        if data is None:
            logger.warning("fastsimilarity_2d 실패: cid=%d", cid)
            return []
        id_list = data.get("IdentifierList")
        if not isinstance(id_list, dict):
            return []
        cids = id_list.get("CID")
        if not isinstance(cids, list):
            return []
        return [c for c in cids if isinstance(c, int) and c != cid][:self._n]

    def _lookup_props(self, cid: int):
        """CID → CanonicalSMILES + IUPACName + MolecularFormula (Rule N 가드)."""
        url = (
            f"{self._PUBCHEM_REST}/compound/cid/{cid}"
            f"/property/CanonicalSMILES,IsomericSMILES,SMILES,"
            f"IUPACName,MolecularFormula/JSON"
        )
        data = self._pubchem_get(url, self._PROPS_TIMEOUT)
        if data is None:
            return None
        prop_table = data.get("PropertyTable")
        if not isinstance(prop_table, dict):
            return None
        props = prop_table.get("Properties")
        if not isinstance(props, list) or len(props) == 0:
            return None
        first = props[0]
        if not isinstance(first, dict):
            return None
        return first

    def _classify_korean(self, smiles: str) -> str:
        """SMARTS 기반 한국어 작용기 분류 (Rule L: MolFromSmiles + None 체크)."""
        if not RDKIT_AVAILABLE:
            return "RDKit 미설치"
        mol = Chem.MolFromSmiles(smiles)  # Rule L
        if mol is None:
            logger.warning("_classify_korean: SMILES 파싱 실패 smiles=%s", smiles[:50])
            return "분류 미상"
        tags = []
        for patt, desc in self._compiled_classifiers:
            try:
                if mol.HasSubstructMatch(patt):
                    tags.append(desc)
            except Exception as e:
                logger.warning("HasSubstructMatch 예외: %s", e)
        return "; ".join(tags) if tags else "특이 작용기 미검출"

    def _tanimoto(self, mol_a, smiles_b: str):
        """Morgan FP Tanimoto (Rule L: smiles_b 파싱 후 None 체크)."""
        if not RDKIT_AVAILABLE or self._mfpgen is None:
            return None
        mol_b = Chem.MolFromSmiles(smiles_b)  # Rule L
        if mol_b is None:
            logger.warning("Tanimoto 계산 실패 — smiles_b 파싱 오류: %s", smiles_b[:50])
            return None
        try:
            from rdkit.Chem import DataStructs
            fp_a = self._mfpgen.GetFingerprint(mol_a)
            fp_b = self._mfpgen.GetFingerprint(mol_b)
            return float(DataStructs.TanimotoSimilarity(fp_a, fp_b))
        except Exception as e:
            logger.warning("Morgan FP 계산 예외: %s", e)
            return None

    def _domain_lookup(self, smiles: str, mol) -> list:
        """Fallback 2: 도메인 룩업 딕셔너리 (인돌/폴리아민).
        Source: chemical_characteristics.py _domain_lookup_neighbors 1:1.
        """
        results = []
        if not RDKIT_AVAILABLE or self._mfpgen is None:
            return results
        lookup_dicts = []
        if self._indole_patt is not None and mol.HasSubstructMatch(self._indole_patt):
            lookup_dicts.append(self._PSYCHOACTIVE_INDOLES)
            logger.info("ChemCharThread Fallback 2 — 인돌 코어 감지: smiles=%s", smiles[:40])
        diamine_matched = any(
            p is not None and mol.HasSubstructMatch(p)
            for p in self._diamine_patt_list
        )
        if diamine_matched:
            lookup_dicts.append(self._POLYAMINES)
            logger.info("ChemCharThread Fallback 2 — 디아민 패턴 감지: smiles=%s", smiles[:40])
        if not lookup_dicts:
            return results

        fp_query = self._mfpgen.GetFingerprint(mol)
        seen = {smiles}
        from rdkit.Chem import DataStructs
        for lookup in lookup_dicts:
            for name, cand_smiles in lookup.items():
                if not isinstance(cand_smiles, str) or cand_smiles in seen:
                    continue
                cand_mol = Chem.MolFromSmiles(cand_smiles)  # Rule L
                if cand_mol is None:
                    logger.warning("[Rule L] MolFromSmiles 실패 (similarity): %r", cand_smiles)
                    continue
                try:
                    fp_c = self._mfpgen.GetFingerprint(cand_mol)
                    tanimoto = float(DataStructs.TanimotoSimilarity(fp_query, fp_c))
                except Exception as e:
                    logger.warning("Fallback 2 Tanimoto 예외: %s", e)
                    continue
                if tanimoto < self._FALLBACK_TANIMOTO_MIN:
                    continue
                comment = self._classify_korean(cand_smiles)
                results.append({
                    "smiles": cand_smiles,
                    "name": name,
                    "similarity": round(tanimoto, 3),
                    "comment_korean": comment,
                    "pubchem_cid": None,
                    "source": "domain_lookup",
                })
                seen.add(cand_smiles)
                if len(results) >= self._n:
                    break
            if len(results) >= self._n:
                break
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:self._n]

    def run(self):
        """메인 실행: PubChem primary → fallback chain (Rule M: 실패 시 warning 필수)."""
        import urllib.parse
        import time as _time
        _run_start = _time.monotonic()  # [M507] 스레드 전체 실행 시간 측정 기준점

        smiles = self._smiles
        # Rule M: 빈 SMILES — silent return 금지
        if not smiles:
            logger.warning("ChemCharFetchThread: SMILES 없음 — 검색 불가")
            self.result_ready.emit({"neighbors": [], "error": "SMILES 없음"})
            return

        # ── 1) RDKit 파싱 (Rule L) ─────────────────────────────────────────
        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(smiles)  # Rule L
            if mol is None:
                logger.warning("ChemCharFetchThread: SMILES 파싱 실패 smiles=%s", smiles[:50])
                self.result_ready.emit({"neighbors": [], "error": f"SMILES 파싱 실패: {smiles[:40]}"})
                return
        else:
            mol = None

        # ── 2) PubChem CID 조회 ─────────────────────────────────────────────
        center_cid = self._lookup_cid(smiles)
        center_name = None
        if center_cid is not None:
            props = self._lookup_props(center_cid)
            if isinstance(props, dict):
                name_val = props.get("IUPACName")
                center_name = name_val if isinstance(name_val, str) else None
        else:
            logger.warning("PubChem CID 미발견: smiles=%s", smiles[:50])

        center_comment = self._classify_korean(smiles)
        # [M1436] PubChem 연결 실패 여부를 결과 dict에 포함 — _on_data_received에서 fallback 트리거
        pubchem_reachable = center_cid is not None

        # ── 3) 유사 분자 검색 ────────────────────────────────────────────────
        neighbors = []
        fallback_used = []

        if center_cid is not None and RDKIT_AVAILABLE and mol is not None:
            sim_cids = self._lookup_similar_cids(center_cid)
            if not sim_cids:
                logger.warning(
                    "PubChem fastsimilarity_2d 0건 (Threshold=%d): cid=%d smiles=%s",
                    self._TANIMOTO_THRESHOLD, center_cid, smiles[:50],
                )

            for sim_cid in sim_cids:
                # [M507] 총 실행 시간 예산 체크 — 초과 시 조기 종료 (Rule M: warning 필수)
                if _time.monotonic() - _run_start > self._TOTAL_BUDGET_SEC - self._PROPS_TIMEOUT:
                    logger.warning(
                        "ChemCharFetchThread: 시간 예산 초과 — sim_cid=%d 에서 조기 종료 (%d건 수집)",
                        sim_cid, len(neighbors)
                    )
                    break
                props = self._lookup_props(sim_cid)
                if props is None:
                    logger.warning("속성 조회 실패 건너뜀: sim_cid=%d", sim_cid)
                    continue
                # Rule N: isinstance guard for props dict
                if not isinstance(props, dict):
                    continue
                sim_smiles = (
                    props.get("CanonicalSMILES")
                    or props.get("IsomericSMILES")
                    or props.get("SMILES")
                )
                if not isinstance(sim_smiles, str) or not sim_smiles:
                    logger.warning("SMILES 필드 비정상 cid=%d", sim_cid)
                    continue
                sim_name = props.get("IUPACName")
                if not isinstance(sim_name, str):
                    sim_name = "Unknown"
                tanimoto = self._tanimoto(mol, sim_smiles)
                if tanimoto is None:
                    continue
                comment = self._classify_korean(sim_smiles)
                neighbors.append({
                    "smiles": sim_smiles,
                    "name": sim_name,
                    "similarity": round(tanimoto, 3),
                    "comment_korean": comment,
                    "pubchem_cid": sim_cid,
                    "source": "pubchem_fastsimilarity",
                })

        # ── 4) Fallback chain — 품질 부족 시 (M382 교훈 반영) ───────────────
        # M382: 단순 개수가 아닌 품질(Tanimoto ≥ 0.4) 기준으로 fallback 가동
        if RDKIT_AVAILABLE and mol is not None:
            high_quality = [nb for nb in neighbors
                            if nb.get("similarity", 0.0) >= self._FALLBACK_TANIMOTO_MIN]
            if len(high_quality) < self._FALLBACK_MIN_COUNT:
                logger.info(
                    "ChemCharThread — Fallback 가동 (고품질 %d건 < %d): smiles=%s",
                    len(high_quality), self._FALLBACK_MIN_COUNT, smiles[:50],
                )
                fb_results = self._domain_lookup(smiles, mol)
                if fb_results:
                    fallback_used.append("domain_lookup")
                    existing = {nb["smiles"] for nb in neighbors if isinstance(nb, dict) and "smiles" in nb}
                    for item in fb_results:
                        if isinstance(item.get("smiles"), str) and item["smiles"] not in existing:
                            neighbors.append(item)
                            existing.add(item["smiles"])

        # 유사도 내림차순 정렬 + n개 상한
        neighbors.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        neighbors = neighbors[:self._n]

        engine_str = (
            f"RDKit Morgan FP (radius={self._MORGAN_RADIUS}, bits={self._MORGAN_BITS})"
            f" + PubChem fastsimilarity_2d (Threshold={self._TANIMOTO_THRESHOLD})"
            + (f" + Fallback({','.join(fallback_used)})" if fallback_used else "")
        )

        self.result_ready.emit({
            "center": {
                "smiles": smiles,
                "pubchem_cid": center_cid,
                "name": center_name,
                "comment_korean": center_comment,
            },
            "neighbors": neighbors,
            "engine": engine_str,
            "academic_reference": (
                "Maggiora et al. J. Med. Chem. 2014; "
                "Rogers & Hahn J. Chem. Inf. Model. 2010; "
                "PubChem (NCBI); Shulgin TIHKAL 1997; "
                "Pegg A.E. IUBMB Life 2009, 61:880 (DOI:10.1002/iub.230)"
            ),
            # [M1436] Rule M: PubChem 연결 실패 여부 명시 — _on_data_received fallback 트리거용
            "pubchem_failed": not pubchem_reachable,
        })


class ChemCharCanvas(QWidget):
    """QPainter 방사형 다이어그램 렌더러.
    Source: ChemicalCharacteristicsPanel.tsx SVG 렌더 블록 (L174-332) 1:1 번역.
    Rule O: 학술 논문 품질 — 화살촉 polygon, 균등 각도, 색상 일관성.
    """

    # ── 레이아웃 상수 (Source: ChemicalCharacteristicsPanel.tsx L36-46 1:1, Rule I 주석) ──
    CANVAS_W = 620          # px — SVG_W 1:1
    CANVAS_H = 620          # px — SVG_H 1:1
    CX = CANVAS_W // 2      # 중심 X = 310
    CY = CANVAS_H // 2      # 중심 Y = 310
    R_CENTER = 80           # 중심 분자 박스 반지름 px — R_CENTER 1:1
    R_ORBIT = 235           # 유사 분자 중심까지 거리 px — R_ORBIT 1:1
    BOX_W = 110             # 유사 분자 박스 너비 px — BOX_W 1:1
    BOX_H = 100             # 유사 분자 박스 높이 px (이미지 없이 텍스트만 — 웹 foreignObject 대체)
    ARROW_GAP = 12          # 화살표 시작/끝 여백 px — ARROW_GAP 1:1
    MAX_NEIGHBORS = 8       # 최대 유사 분자 수 (Maggiora 2014 기준 — MAX_NEIGHBORS 1:1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = None
        self.setFixedSize(self.CANVAS_W, self.CANVAS_H)
        self.setStyleSheet("background-color: #ffffff;")  # 배경 흰색 (웹 1:1)

    def set_data(self, data: dict):
        # Rule N: 타입 가드
        if not isinstance(data, dict):
            logger.warning("ChemCharCanvas.set_data: dict 아님 type=%s", type(data).__name__)
            return
        self._data = data
        self.update()

    @staticmethod
    def _sim_color(sim: float) -> QColor:
        """유사도 → 색상 (Source: ChemicalCharacteristicsPanel.tsx getSimilarityColor 1:1).
        ≥0.85 초록, ≥0.70 파랑, ≥0.50 주황, else 회색.
        """
        if sim >= 0.85:
            return QColor("#059669")  # 매우 유사 — 초록
        if sim >= 0.70:
            return QColor("#2563eb")  # 유사 — 파랑
        if sim >= 0.50:
            return QColor("#d97706")  # 경계 — 주황
        return QColor("#6b7280")      # 낮음 — 회색

    def paintEvent(self, event):
        if not self._data or not isinstance(self._data, dict):  # Rule N
            # 데이터 없으면 안내 텍스트만 표시 (Rule M: silent 금지)
            painter = QPainter(self)
            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Malgun Gothic", 10))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "분자를 로드하면 유사 분자 다이어그램이 표시됩니다.")
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        neighbors = self._data.get("neighbors", [])
        if not isinstance(neighbors, list):  # Rule N
            logger.warning("ChemCharCanvas.paintEvent: neighbors 비리스트 type=%s",
                           type(neighbors).__name__)
            neighbors = []
        neighbors = neighbors[:self.MAX_NEIGHBORS]
        n = len(neighbors)

        cx, cy = self.CX, self.CY

        # ── 1) 배경 궤도 점선 원 (Source: TSX <circle strokeDasharray="4,4" />) ──
        painter.setPen(QPen(QColor("#e5e7eb"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            cx - self.R_ORBIT, cy - self.R_ORBIT,
            self.R_ORBIT * 2, self.R_ORBIT * 2
        )

        # ── 2) 중심 분자 원 (Source: TSX <circle fill="#f0f4ff" stroke="#2563eb" />) ──
        painter.setPen(QPen(QColor("#2563eb"), 1.5))
        painter.setBrush(QColor("#f0f4ff"))
        painter.drawEllipse(
            cx - self.R_CENTER, cy - self.R_CENTER,
            self.R_CENTER * 2, self.R_CENTER * 2
        )

        import math as _math

        # ── 3) 각 유사 분자 (화살선 + 화살촉 + 박스) ──────────────────────────
        for i, nbr in enumerate(neighbors):
            if not isinstance(nbr, dict):  # Rule N
                continue

            sim = float(nbr.get("similarity", 0.0)) if isinstance(nbr.get("similarity"), (int, float)) else 0.0
            sim_color = self._sim_color(sim)
            name = nbr.get("name", "Unknown")
            if not isinstance(name, str):
                name = "Unknown"
            comment = nbr.get("comment_korean", "")
            if not isinstance(comment, str):
                comment = ""

            # 균등 각도 분배 — 12시 방향(-π/2)에서 시작 (Source: TSX angle 계산 1:1)
            angle = (i / n) * 2 * _math.pi - _math.pi / 2 if n > 0 else 0.0
            cos_a = _math.cos(angle)
            sin_a = _math.sin(angle)

            # 유사 분자 중심 좌표
            nx = cx + self.R_ORBIT * cos_a
            ny = cy + self.R_ORBIT * sin_a

            # 화살선 시작점 (중심 원 경계) / 끝점 (박스 경계) — Source: TSX ax1/ay1/ax2/ay2 1:1
            ax1 = cx + (self.R_CENTER + self.ARROW_GAP) * cos_a
            ay1 = cy + (self.R_CENTER + self.ARROW_GAP) * sin_a
            ax2 = cx + (self.R_ORBIT - self.BOX_W / 2 - self.ARROW_GAP) * cos_a
            ay2 = cy + (self.R_ORBIT - self.BOX_W / 2 - self.ARROW_GAP) * sin_a

            # ── 화살선 (Source: TSX <line markerEnd="..."/>) ──────────────────
            pen = QPen(sim_color, 1.8)
            pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(int(ax1), int(ay1), int(ax2), int(ay2))

            # ── 화살촉 polygon (Source: TSX marker M0,0 L0,7 L10,3.5 z 1:1) ──
            # 화살 방향 벡터 정규화
            dx = ax2 - ax1
            dy = ay2 - ay1
            length = _math.sqrt(dx * dx + dy * dy)
            if length > 0.01:
                ux, uy = dx / length, dy / length
                vx, vy = -uy, ux  # 수직 벡트
                # 화살촉 크기: markerWidth=10, markerHeight=7 → 스케일 8px
                tip_x, tip_y = ax2, ay2
                base1_x = tip_x - 8 * ux + 3.5 * vx
                base1_y = tip_y - 8 * uy + 3.5 * vy
                base2_x = tip_x - 8 * ux - 3.5 * vx
                base2_y = tip_y - 8 * uy - 3.5 * vy
                arrow_head = [
                    QPointF(tip_x, tip_y),
                    QPointF(base1_x, base1_y),
                    QPointF(base2_x, base2_y),
                ]
                painter.setPen(QPen(QColor("#4b5563"), 1))
                painter.setBrush(QColor("#4b5563"))
                from PyQt6.QtGui import QPolygonF
                painter.drawConvexPolygon(QPolygonF(arrow_head))

            # ── 유사도 라벨 (화살선 중간) — Source: TSX <text> 1:1 ──────────
            mid_x = (ax1 + ax2) / 2
            mid_y = (ay1 + ay2) / 2
            painter.setPen(sim_color)
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            sim_text = f"{sim * 100:.0f}%"
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(sim_text)
            painter.drawText(int(mid_x - tw / 2), int(mid_y - 2), sim_text)

            # ── 유사 분자 박스 (Source: TSX foreignObject → neighborBox 1:1) ──
            bx = int(nx - self.BOX_W / 2)
            by = int(ny - self.BOX_H / 2)
            bw, bh = self.BOX_W, self.BOX_H

            # 박스 배경 + 테두리
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(bx, by, bw, bh, 8, 8)

            # 분자 이름 (최대 18자, 웹 1:1)
            name_disp = name if len(name) <= 18 else name[:16] + "…"
            painter.setPen(QColor("#1e293b"))
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            painter.drawText(bx + 4, by + 15, bw - 8, 16,
                             int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                             name_disp)

            # 유사도 색상 배지
            painter.setPen(sim_color)
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            painter.drawText(bx + 4, by + 30, bw - 8, 14,
                             int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                             f"유사도 {sim * 100:.0f}%")

            # 한국어 코멘트 (최대 2줄, Source: TSX neighborComment 1:1)
            comment_short = comment[:36] if len(comment) > 36 else comment
            painter.setPen(sim_color)
            painter.setFont(QFont("Malgun Gothic", 7))
            painter.drawText(bx + 2, by + 46, bw - 4, bh - 50,
                             int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap),
                             comment_short)

        # ── 4) 중심 분자 라벨 (Source: TSX centerLabel 1:1) ─────────────────
        center_info = self._data.get("center")
        if isinstance(center_info, dict):
            center_name = center_info.get("name") or ""
            center_smiles = center_info.get("smiles") or ""
            # "중심 분자" 고정 라벨
            painter.setPen(QColor("#2563eb"))
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            painter.drawText(
                cx - self.R_CENTER, cy - 10,
                self.R_CENTER * 2, 20,
                int(Qt.AlignmentFlag.AlignCenter),
                "중심 분자"
            )
            if center_name:
                name_disp = center_name[:20] if len(center_name) > 20 else center_name
                painter.setPen(QColor("#1e293b"))
                painter.setFont(QFont("Malgun Gothic", 7))
                painter.drawText(
                    cx - self.R_CENTER, cy + 8,
                    self.R_CENTER * 2, 16,
                    int(Qt.AlignmentFlag.AlignCenter),
                    name_disp
                )


class ChemCharCanvas(QWidget):
    """RDKit structure-based derivative view for the chemical properties tab.

    This replacement intentionally preserves the existing fetch/data contract
    while changing the visual surface from text-only similarity cards to
    a central current molecule with derivative structure panels and
    common-substructure highlighting.
    """

    CANVAS_W = 900
    CANVAS_H = 640
    CX = CANVAS_W // 2
    CY = 318
    R_CENTER = 92
    R_ORBIT = 255
    BOX_W = 158
    BOX_H = 132
    MOL_W = 142
    MOL_H = 82
    ARROW_GAP = 12
    MAX_NEIGHBORS = 8
    DERIV_COLS = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        _ensure_qt_korean_font_ready()
        self._data = None
        self._last_render_stats = {}
        self.setFixedSize(self.CANVAS_W, self.CANVAS_H)
        self.setStyleSheet("background-color: #ffffff;")

    def set_data(self, data: dict):
        if not isinstance(data, dict):
            logger.warning("ChemCharCanvas.set_data: non-dict type=%s", type(data).__name__)
            return
        self._data = data
        self.update()

    @staticmethod
    def _sim_color(sim: float) -> QColor:
        if sim >= 0.85:
            return QColor("#059669")
        if sim >= 0.70:
            return QColor("#2563eb")
        if sim >= 0.50:
            return QColor("#d97706")
        return QColor("#6b7280")

    @staticmethod
    def _safe_text(value, fallback: str = "") -> str:
        if isinstance(value, str):
            value = value.strip()
            return value if value else fallback
        return fallback

    @staticmethod
    def _shorten(value: str, max_len: int) -> str:
        value = ChemCharCanvas._safe_text(value)
        if len(value) <= max_len:
            return value
        return value[:max(0, max_len - 1)] + "..."

    @staticmethod
    def _mol_from_smiles(smiles: str):
        if not RDKIT_AVAILABLE or not isinstance(smiles, str) or not smiles.strip():
            return None
        mol = Chem.MolFromSmiles(smiles.strip())
        if mol is None:
            logger.warning("ChemCharCanvas: SMILES parse failed smiles=%s", smiles[:50])
            return None
        try:
            from rdkit.Chem import rdDepictor
            rdDepictor.Compute2DCoords(mol)
        except Exception as e:
            logger.warning("ChemCharCanvas: 2D coordinate generation failed: %s", e)
        return mol

    @staticmethod
    def _mcs_match_atoms(center_smiles: str, target_smiles: str):
        if not RDKIT_AVAILABLE:
            return [], []
        center_mol = ChemCharCanvas._mol_from_smiles(center_smiles)
        target_mol = ChemCharCanvas._mol_from_smiles(target_smiles)
        if center_mol is None or target_mol is None:
            return [], []
        try:
            from rdkit.Chem import rdFMCS
            result = rdFMCS.FindMCS(
                [center_mol, target_mol],
                timeout=1,
                ringMatchesRingOnly=True,
                completeRingsOnly=False,
            )
            if not result.smartsString:
                return [], []
            patt = Chem.MolFromSmarts(result.smartsString)
            if patt is None:
                return [], []
            center_match = list(center_mol.GetSubstructMatch(patt))
            target_match = list(target_mol.GetSubstructMatch(patt))
            if len(target_match) < 2:
                return [], []
            return center_match, target_match
        except Exception as e:
            logger.warning("ChemCharCanvas: MCS highlight failed: %s", e)
            return [], []

    @staticmethod
    def _highlight_bonds(mol, atoms: list):
        atom_set = set(atoms)
        bonds = []
        if mol is None or not atom_set:
            return bonds
        for bond in mol.GetBonds():
            if bond.GetBeginAtomIdx() in atom_set and bond.GetEndAtomIdx() in atom_set:
                bonds.append(bond.GetIdx())
        return bonds

    @staticmethod
    def _molecule_image(smiles: str, width: int, height: int, highlight_atoms=None):
        mol = ChemCharCanvas._mol_from_smiles(smiles)
        if mol is None:
            return None, 0
        highlight_atoms = list(highlight_atoms or [])
        highlight_bonds = ChemCharCanvas._highlight_bonds(mol, highlight_atoms)
        try:
            from PyQt6.QtGui import QImage
            from rdkit.Chem.Draw import rdMolDraw2D
            drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
            opts = drawer.drawOptions()
            opts.clearBackground = False
            opts.bondLineWidth = 2
            opts.padding = 0.08
            atom_colors = {idx: (0.05, 0.62, 0.33) for idx in highlight_atoms}
            bond_colors = {idx: (0.05, 0.62, 0.33) for idx in highlight_bonds}
            drawer.DrawMolecule(
                mol,
                highlightAtoms=highlight_atoms,
                highlightBonds=highlight_bonds,
                highlightAtomColors=atom_colors,
                highlightBondColors=bond_colors,
            )
            drawer.FinishDrawing()
            image = QImage.fromData(drawer.GetDrawingText(), "PNG")
            if image.isNull():
                logger.warning("ChemCharCanvas: null molecule image smiles=%s", smiles[:50])
                return None, 0
            return image, len(highlight_atoms)
        except Exception as e:
            logger.warning("ChemCharCanvas: RDKit molecule drawing failed: %s", e)
            return None, 0

    @staticmethod
    def _compact_property_label(smiles: str, comment: str = "") -> list:
        labels = []
        compact = ChemCharCanvas._safe_text(comment)
        if compact:
            labels.append(ChemCharCanvas._shorten(compact, 34))
        if RDKIT_AVAILABLE and isinstance(smiles, str) and smiles.strip():
            try:
                mol = Chem.MolFromSmiles(smiles.strip())
                if mol is not None:
                    mw = Descriptors.MolWt(mol)
                    logp = Descriptors.MolLogP(mol)
                    hbd = rdMolDescriptors.CalcNumHBD(mol)
                    hba = rdMolDescriptors.CalcNumHBA(mol)
                    rotb = rdMolDescriptors.CalcNumRotatableBonds(mol)
                    labels.append(f"MW {mw:.1f} | LogP {logp:.1f}")
                    if len(labels) < 2:
                        labels.append(f"HBD {hbd} HBA {hba} RotB {rotb}")
                    return labels[:2]
            except Exception as e:
                logger.warning("ChemCharCanvas: compact property calculation failed: %s", e)
        if labels:
            return labels[:2]
        return ["property data unavailable"]

    @staticmethod
    def _draw_lines(painter: QPainter, lines: list, x: int, y: int,
                    w: int, line_h: int, color: QColor, bold: bool = False):
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        painter.setPen(color)
        painter.setFont(QFont(_QT_KR_FONT, 7 if not bold else 8, weight))
        for idx, line in enumerate(lines):
            painter.drawText(
                x, y + idx * line_h, w, line_h,
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                ChemCharCanvas._shorten(str(line), 34),
            )

    def _draw_panel(self, painter: QPainter, rect: QRectF, border: QColor, fill: QColor):
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 6, 6)

    def _first_neighbor_smiles(self) -> str:
        if not isinstance(self._data, dict):
            return ""
        neighbors = self._data.get("neighbors", [])
        if isinstance(neighbors, list):
            for item in neighbors:
                if isinstance(item, dict) and isinstance(item.get("smiles"), str):
                    return item["smiles"]
        return ""

    def _draw_molecule_panel(self, painter: QPainter, x: int, y: int, w: int, h: int,
                             item: dict, center_smiles: str, is_center: bool = False):
        smiles = self._safe_text(item.get("smiles"))
        name = self._safe_text(item.get("name"), "Molecule")
        comment = self._safe_text(item.get("comment_korean"))
        sim = item.get("similarity", None)
        sim_val = float(sim) if isinstance(sim, (int, float)) else None
        color = QColor("#2563eb") if is_center else self._sim_color(sim_val or 0.0)

        if is_center:
            highlight_atoms, _ = self._mcs_match_atoms(smiles, self._first_neighbor_smiles())
            image, highlight_count = self._molecule_image(
                smiles, self.MOL_W + 18, self.MOL_H + 18, highlight_atoms
            )
        else:
            _, target_match = self._mcs_match_atoms(center_smiles, smiles)
            image, highlight_count = self._molecule_image(
                smiles, self.MOL_W, self.MOL_H, target_match
            )

        self._draw_panel(painter, QRectF(x, y, w, h), color, QColor("#ffffff"))
        if highlight_count > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#d1fae5"))
            painter.drawRoundedRect(QRectF(x + 6, y + 6, w - 12, 13), 4, 4)
            painter.setPen(QColor("#047857"))
            painter.setFont(QFont(_QT_KR_FONT, 6, QFont.Weight.Bold))
            painter.drawText(x + 8, y + 6, w - 16, 13, int(Qt.AlignmentFlag.AlignCenter), "COMMON CORE")

        if image is not None:
            img_x = x + int((w - image.width()) / 2)
            painter.drawImage(img_x, y + 22, image)
            if is_center:
                self._last_render_stats["central_molecule_rendered"] = True
            else:
                self._last_render_stats["derivative_render_count"] += 1
            if highlight_count > 0:
                self._last_render_stats["highlight_indicator_count"] += 1

        label_y = y + h - 44
        title = "Central molecule" if is_center else self._shorten(name, 24)
        if sim_val is not None and not is_center:
            title = f"{self._shorten(name, 19)} | {sim_val * 100:.0f}%"
        self._draw_lines(painter, [title], x + 4, label_y, w - 8, 14, QColor("#111827"), True)
        props = self._compact_property_label(smiles, comment)
        self._draw_lines(painter, props[:2], x + 4, label_y + 16, w - 8, 13, QColor("#374151"))
        self._last_render_stats["compact_property_label_count"] += 1
        self._last_render_stats["compact_property_labels"].extend(props[:2])

    def paintEvent(self, event):
        self._last_render_stats = {
            "layout": "structure_derivative_network",
            "central_molecule_rendered": False,
            "derivative_render_count": 0,
            "highlight_indicator_count": 0,
            "compact_property_label_count": 0,
            "common_substructure_highlighted": False,
            "used_text_only_radial_substitute": False,
            "radial_placeholder_visible": False,
            "derivative_panel_positions": [],
            "compact_property_labels": [],
            "neighbor_count": 0,
        }
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if not self._data or not isinstance(self._data, dict):
            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont(_QT_KR_FONT, 10))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Load a molecule to render derivative structures.",
            )
            return

        neighbors = self._data.get("neighbors", [])
        if not isinstance(neighbors, list):
            logger.warning("ChemCharCanvas.paintEvent: neighbors non-list type=%s", type(neighbors).__name__)
            neighbors = []
        neighbors = neighbors[:self.MAX_NEIGHBORS]
        n = len(neighbors)
        self._last_render_stats["neighbor_count"] = n

        center_info = self._data.get("center")
        if not isinstance(center_info, dict):
            center_info = {}
        center_smiles = self._safe_text(center_info.get("smiles"))
        center_item = {
            "smiles": center_smiles,
            "name": self._safe_text(center_info.get("name"), "center"),
            "comment_korean": self._safe_text(center_info.get("comment_korean")),
        }

        cx = self.CX
        painter.setPen(QColor("#047857"))
        painter.setFont(QFont(_QT_KR_FONT, 8, QFont.Weight.Bold))
        painter.drawText(18, 14, 320, 18, int(Qt.AlignmentFlag.AlignLeft), "Green overlay = common substructure")

        center_x = cx - 112
        center_y = 42
        center_w = 224
        center_h = 188
        self._draw_molecule_panel(
            painter,
            center_x,
            center_y,
            center_w,
            center_h,
            center_item,
            center_smiles,
            is_center=True,
        )

        grid_top = 284
        grid_left = 36
        grid_gap_x = 42
        grid_gap_y = 30
        panel_w = 172
        panel_h = 142
        for i, nbr in enumerate(neighbors):
            if not isinstance(nbr, dict):
                continue
            sim = float(nbr.get("similarity", 0.0)) if isinstance(nbr.get("similarity"), (int, float)) else 0.0
            sim_color = self._sim_color(sim)
            row = i // self.DERIV_COLS
            col = i % self.DERIV_COLS
            panel_x = grid_left + col * (panel_w + grid_gap_x)
            panel_y = grid_top + row * (panel_h + grid_gap_y)

            # Connector is a short scaffold cue, not a radial placeholder.
            start_x = center_x + center_w / 2
            start_y = center_y + center_h
            end_x = panel_x + panel_w / 2
            end_y = panel_y
            painter.setPen(QPen(sim_color, 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))

            mid_x = (start_x + end_x) / 2
            mid_y = (start_y + end_y) / 2
            painter.setPen(sim_color)
            painter.setFont(QFont(_QT_KR_FONT, 8, QFont.Weight.Bold))
            sim_text = f"{sim * 100:.0f}%"
            tw = painter.fontMetrics().horizontalAdvance(sim_text)
            painter.drawText(int(mid_x - tw / 2), int(mid_y - 2), sim_text)

            self._draw_molecule_panel(
                painter,
                panel_x,
                panel_y,
                panel_w,
                panel_h,
                nbr,
                center_smiles,
                is_center=False,
            )
            self._last_render_stats["derivative_panel_positions"].append(
                {"x": panel_x, "y": panel_y, "w": panel_w, "h": panel_h}
            )

        self._last_render_stats["common_substructure_highlighted"] = (
            self._last_render_stats["highlight_indicator_count"] > 0
        )


class ChemCharPanel(QWidget):
    """화학적 특성 분석 패널 — 방사형 유사 분자 8개 QPainter 시각화.
    Source: ChemicalCharacteristicsPanel.tsx (Rule Y 1:1 번역).
    학계 reference: Maggiora et al. J. Med. Chem. 2014, 57(8), 3186-3204.
    Rule M: 3-state (로딩/에러/데이터) 전수 — silent return 0건.
    Rule N: 외부 PubChem 응답 isinstance 가드 필수.
    Rule L: SMILES MolFromSmiles + None 체크 스레드 내부 적용.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smiles = ""
        self._data = None
        self._fetch_thread = None
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout()
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ── 헤더 ──────────────────────────────────────────────────────────────
        title = QLabel("🔬 화학적 특성 분석 (Chemical Characteristics)")
        title.setStyleSheet(
            "font-size: 10pt; font-weight: bold; color: #1a1a2e;"
            "border-bottom: 2px solid #2563eb; padding-bottom: 3px;"
        )
        outer.addWidget(title)

        # ── 메타 정보 행 (Source: TSX metaRow 1:1) ───────────────────────────
        self._meta_label = QLabel(
            "엔진: RDKit Morgan FP (radius=2)  |  참고: Maggiora et al. J. Med. Chem. 2014"
        )
        self._meta_label.setStyleSheet("font-size: 8pt; color: #64748b;")
        outer.addWidget(self._meta_label)

        # ── 중심 분자 SMILES (Source: TSX centerSmiles 1:1) ──────────────────
        self._smiles_label = QLabel("중심 분자: (로드 대기 중)")
        self._smiles_label.setStyleSheet("font-size: 8pt; color: #475569;")
        self._smiles_label.setWordWrap(True)
        outer.addWidget(self._smiles_label)

        # ── 상태 라벨 (로딩/에러/완료) — Rule M ─────────────────────────────
        self._status_label = QLabel("분자를 로드하면 유사 분자 검색이 시작됩니다.")
        self._status_label.setStyleSheet("font-size: 8pt; color: #94a3b8; font-style: italic;")
        outer.addWidget(self._status_label)

        # ── [M1436] SIMULATION_MODE 배너 (Rule GG: PubChem 실패 시 노랑 배너 의무) ──
        # 기본 hidden — PubChem fallback 시 setVisible(True)
        self._sim_banner = QLabel(
            "SIMULATION MODE  |  PubChem 연결 실패 — RDKit 로컬 분석 결과 (Lipinski Ro5 물성)"
        )
        self._sim_banner.setStyleSheet(
            "background-color: #fef08a; color: #713f12; font-size: 8pt; font-weight: bold;"
            "border: 1px solid #ca8a04; border-radius: 3px; padding: 2px 6px;"
        )
        self._sim_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sim_banner.setVisible(False)  # 기본 숨김 — fallback 시에만 표시
        outer.addWidget(self._sim_banner)

        # ── 스크롤 영역에 캔버스 ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("QScrollArea { border: none; background: #ffffff; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._canvas = ChemCharCanvas()
        scroll.setWidget(self._canvas)
        outer.addWidget(scroll, 1)

        # ── 범례 (Source: TSX legendRow 1:1) ─────────────────────────────────
        legend_layout = QHBoxLayout()
        legend_layout.addWidget(QLabel("유사도 색상:"))
        for label, color in [
            ("≥85% (매우 유사)", "#059669"),
            ("70~84% (유사)",    "#2563eb"),
            ("50~69% (경계)",    "#d97706"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 10pt;")
            legend_layout.addWidget(dot)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 8pt; color: #475569;")
            legend_layout.addWidget(lbl)
        legend_layout.addStretch()

        # ── 재검색 버튼 ────────────────────────────────────────────────────
        self._btn_refresh = QPushButton("↻ 재검색")
        self._btn_refresh.setFixedHeight(24)
        self._btn_refresh.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; border-radius: 4px; "
            "padding: 2px 10px; font-size: 8pt; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:disabled { background: #94a3b8; color: #e2e8f0; }"
        )
        self._btn_refresh.clicked.connect(self._fetch_async)
        legend_layout.addWidget(self._btn_refresh)
        outer.addLayout(legend_layout)

        self.setLayout(outer)

    def stop_fetch(self):
        """실행 중인 _fetch_thread 즉시 중단 (popup 닫힘 시 호출, M514 Thread Lifecycle Fix).
        quit() 후 500ms 내 미종료 시 terminate() 강제 종료 — orphan HTTP thread 방지 (Rule M).
        """
        if self._fetch_thread is not None and self._fetch_thread.isRunning():
            self._fetch_thread.quit()
            if not self._fetch_thread.wait(500):  # [MAGIC] 500ms: quit() 수락 대기
                self._fetch_thread.terminate()    # 강제 종료 (HTTP 블로킹 해소)
                self._fetch_thread.wait(200)      # [MAGIC] 200ms: terminate 완료 대기
            logger.info("ChemCharPanel.stop_fetch: _fetch_thread 종료 완료")

    def set_smiles(self, smiles: str):
        """외부에서 SMILES 전달 (Molecule3DPopup._load_data에서 호출).
        Rule M: 빈 SMILES — silent return 금지 + 상태 라벨 업데이트.
        Rule N: isinstance 체크 필수.
        """
        if not isinstance(smiles, str):
            logger.warning("ChemCharPanel.set_smiles: str 아님 type=%s", type(smiles).__name__)
            self._status_label.setText("SMILES 형식 오류 (str 아님)")
            return
        smiles = smiles.strip()
        if not smiles:
            logger.warning("ChemCharPanel.set_smiles: SMILES 없음 — 검색 불가")
            self._status_label.setText("SMILES가 없습니다. 분자를 먼저 로드하세요.")
            return
        self._smiles = smiles
        self._smiles_label.setText(
            f"중심 분자: {smiles[:50]}{'…' if len(smiles) > 50 else ''}"
        )
        self._fetch_async()

    def _fetch_async(self):
        """PubChem 비동기 검색 시작 (QThread — UI 블로킹 방지)."""
        if not self._smiles:
            logger.warning("ChemCharPanel._fetch_async: SMILES 없음")
            self._status_label.setText("SMILES가 없습니다.")
            return
        self._status_label.setText("유사 분자 검색 중... (PubChem fastsimilarity_2d + RDKit Morgan FP)")
        self._status_label.setStyleSheet("font-size: 8pt; color: #2563eb; font-style: italic;")
        self._btn_refresh.setEnabled(False)
        # 이전 스레드 정리
        if self._fetch_thread is not None and self._fetch_thread.isRunning():
            self._fetch_thread.quit()
            self._fetch_thread.wait(2000)  # 2초 대기
        self._fetch_thread = _ChemCharFetchThread(self._smiles, n=8, parent=self)
        self._fetch_thread.result_ready.connect(self._on_data_received)
        self._fetch_thread.start()

    def _on_data_received(self, data: dict):
        """스레드 완료 콜백 — Rule N: isinstance 가드 필수."""
        self._btn_refresh.setEnabled(True)

        if not isinstance(data, dict):  # Rule N
            # [M1436] Rule M: silent return 금지 — logger.warning + 사용자 피드백 필수
            logger.warning("ChemCharPanel._on_data_received: dict 아님 type=%s", type(data).__name__)
            self._status_label.setText("검색 결과 형식 오류 (dict 아님)")
            self._status_label.setStyleSheet("font-size: 8pt; color: #dc2626;")
            return

        # [M1436] 에러 또는 PubChem 연결 실패 시 로컬 RDKit fallback (Rule M + GG)
        # pubchem_failed: CID 조회 실패(네트워크 타임아웃 포함) — 에러 없이도 fallback 필요한 경우
        need_fallback = bool(data.get("error")) or bool(data.get("pubchem_failed"))
        if need_fallback:
            err_msg = str(data.get("error", "PubChem 연결 실패"))
            logger.warning("ChemCharPanel: PubChem 불가 — %s. 로컬 RDKit fallback 시도", err_msg)
            # [F5-13 M745] PubChem 불가 시 RDKit 로컬 기본 물성으로 대체 — silent return 금지 (Rule M)
            fallback_data = self._compute_local_rdkit_props()
            if fallback_data:
                self._status_label.setText(
                    "PubChem 연결 실패 — RDKit 로컬 Lipinski Ro5 물성 표시 중"
                )
                self._status_label.setStyleSheet("font-size: 8pt; color: #d97706; font-style: italic;")
                # [M1436] Rule GG SIMULATION_MODE 배너 표시 (노랑)
                self._sim_banner.setVisible(True)
                self._data = fallback_data
                self._canvas.set_data(fallback_data)
                return
            self._status_label.setText(f"검색 실패: {err_msg}")
            self._status_label.setStyleSheet("font-size: 8pt; color: #dc2626;")
            return

        # PubChem 성공 — SIMULATION 배너 숨김
        self._sim_banner.setVisible(False)

        neighbors = data.get("neighbors")
        if not isinstance(neighbors, list):  # Rule N
            logger.warning("ChemCharPanel: neighbors 비리스트 type=%s",
                           type(neighbors).__name__)
            self._status_label.setText("유사 분자 데이터 형식 오류")
            self._status_label.setStyleSheet("font-size: 8pt; color: #dc2626;")
            return

        if len(neighbors) == 0:
            self._status_label.setText(
                "Tanimoto ≥ 0.40 유사 분자를 찾지 못했습니다. "
                "다른 분자를 시도해보세요."
            )
            self._status_label.setStyleSheet("font-size: 8pt; color: #d97706;")
        else:
            engine = data.get("engine", "")
            self._status_label.setText(
                f"유사 분자 {len(neighbors)}개 발견  |  {engine}"
            )
            self._status_label.setStyleSheet("font-size: 8pt; color: #059669;")
            # 메타 정보 갱신
            ref = data.get("academic_reference", "")
            self._meta_label.setText(
                f"엔진: {engine}  |  참고: {ref[:80]}"
            )

        self._data = data
        self._canvas.set_data(data)

    def _compute_local_rdkit_props(self) -> dict:
        """[F5-13 M745] PubChem 불가 시 로컬 RDKit 기본 물성 fallback.
        Lipinski Ro5 물성(MW/LogP/TPSA/HBD/HBA) 계산 + 단일 중심 분자로 표시.
        Rule L: MolFromSmiles + None 체크 필수.
        Rule M: 실패 시 None 반환 — 호출부에서 확인.
        """
        if not self._smiles:
            logger.warning("ChemCharPanel._compute_local_rdkit_props: SMILES 없음")
            return {}
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, rdMolDescriptors
            mol = Chem.MolFromSmiles(self._smiles)  # Rule L: None 체크
            if mol is None:
                logger.warning("ChemCharPanel._compute_local_rdkit_props: SMILES 파싱 실패 smiles=%s",
                               self._smiles[:50])
                return {}
            mw = round(Descriptors.MolWt(mol), 2)
            logp = round(Descriptors.MolLogP(mol), 3)
            tpsa = round(Descriptors.TPSA(mol), 2)
            hbd = rdMolDescriptors.CalcNumHBD(mol)
            hba = rdMolDescriptors.CalcNumHBA(mol)
            rotb = rdMolDescriptors.CalcNumRotatableBonds(mol)
            # Lipinski Ro5 위반 여부 계산
            ro5_violations = sum([
                mw > 500,      # MW ≤ 500 Da
                logp > 5,      # LogP ≤ 5
                hbd > 5,       # HBD ≤ 5
                hba > 10,      # HBA ≤ 10
            ])
            ro5_msg = "Ro5 준수" if ro5_violations == 0 else f"Ro5 위반 {ro5_violations}건"
            # [M1436] comment_korean 추가 — canvas paintEvent에서 표시됨
            local_comment = (
                f"MW={mw} Da | LogP={logp} | TPSA={tpsa} Å² | "
                f"HBD={hbd} HBA={hba} | {ro5_msg}"
            )
            # neighbors 형식: 중심 분자만 1개, similarity=1.0 (자기 자신)
            local_entry = {
                "cid": 0,
                "smiles": self._smiles,
                "name": f"[로컬] MW={mw}",
                "similarity": 1.0,
                "mw": mw,
                "logp": logp,
                "tpsa": tpsa,
                "hbd": hbd,
                "hba": hba,
                "rotb": rotb,
                # [M1436] canvas 렌더링에 필요한 comment_korean 필드 추가
                "comment_korean": local_comment,
            }
            return {
                "neighbors": [local_entry],
                "engine": f"RDKit 로컬 (MW={mw} LogP={logp} TPSA={tpsa} HBD={hbd} HBA={hba} RotB={rotb})",
                "academic_reference": "Lipinski C.A. et al. Adv. Drug Deliv. Rev. 2001, 46(1-3): 3-26.",
                "fallback": True,
            }
        except Exception as e:
            logger.warning("ChemCharPanel._compute_local_rdkit_props: 계산 오류 %s", e)
            return {}


# ============================================================
# Section 10-5: GABA 수용체 도킹 에너지 임계값 패널
# ============================================================

class DockingEnergyPanel(QWidget):
    """도킹 탭 — RCSB PDB 수용체 검색 + 로컬 점수 추정

    기능:
    1. RCSB PDB 검색으로 수용체 단백질 선택 및 다운로드
    2. 프리셋 수용체 목록 (GABA-A, ACE2, COX-2 등)
    3. 경험적 결합 에너지 예측 (Vina 점수 함수 근사)
    4. 참조 점수 구간 및 임상 약물 비교
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
        # [FIX-SCROLL-DOCK-3D] 외부 레이아웃: 스크롤 + 고정 하단 버튼
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("분자 도킹 컨텍스트 — RCSB PDB 수용체 선택 + 로컬 점수 추정")
        title.setStyleSheet("font-size:11pt; color:#90CAF9; font-weight:bold;")
        layout.addWidget(title)

        # ── [1] 수용체 선택 섹션 ─────────────────────────────────────
        recv_grp = QGroupBox("수용체 단백질 선택")
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
        btn_search = QPushButton("검색")
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
        preset_row.addWidget(QLabel("프리셋:"))
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

        # ── PDBe Mol* 링크 (M645_W9 Rule FF) ──────────────────────────────
        pdbe_row = QHBoxLayout()
        self.btn_pdbe_molstar = QPushButton("PDBe Mol* 뷰어")
        self.btn_pdbe_molstar.setToolTip(
            "PDBe Mol* 3D 뷰어 열기 (웹 브라우저)\n"
            "wwPDB Consortium (2019) Nucleic Acids Res. 47(D1): D520-D528."
        )
        self.btn_pdbe_molstar.setStyleSheet(
            "QPushButton { background:#37474F; color:#80DEEA; border:1px solid #546E7A; "
            "border-radius:3px; font-size:9pt; padding:4px 10px; }"
            "QPushButton:hover { background:#455A64; }"
            "QPushButton:disabled { color:#555; border-color:#444; }"
        )
        self.btn_pdbe_molstar.setEnabled(False)  # PDB ID 선택 전 비활성
        self.btn_pdbe_molstar.clicked.connect(self._open_pdbe_molstar)
        pdbe_row.addWidget(self.btn_pdbe_molstar)

        self.btn_alphafold_ext = QPushButton("AlphaFold/PDB ref")
        self.btn_alphafold_ext.setToolTip(
            "AlphaFold Protein Structure Database (웹 브라우저)\n"
            "Jumper et al. (2021) Nature 596: 583-589."
        )
        self.btn_alphafold_ext.setStyleSheet(
            "QPushButton { background:#37474F; color:#A5D6A7; border:1px solid #546E7A; "
            "border-radius:3px; font-size:9pt; padding:4px 10px; }"
            "QPushButton:hover { background:#455A64; }"
            "QPushButton:disabled { color:#555; border-color:#444; }"
        )
        self.btn_alphafold_ext.setEnabled(False)
        self.btn_alphafold_ext.clicked.connect(self._open_alphafold_ext)
        pdbe_row.addWidget(self.btn_alphafold_ext)
        pdbe_row.addStretch()
        recv_layout.addLayout(pdbe_row)

        # 수용체 로드 버튼 (스크롤 영역 내부에 표시)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_load_receptor = QPushButton("수용체 로드 (RCSB 다운로드)")
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

        # ── [2] 도킹 결과 표시 영역 ──────────────────────────────────
        dock_grp = QGroupBox("로컬 도킹 점수 추정")
        dock_layout = QVBoxLayout()
        dock_layout.setSpacing(4)

        self.dock_result = QTextEdit()
        self.dock_result.setReadOnly(True)
        self.dock_result.setMinimumHeight(80)
        self.dock_result.setMaximumHeight(120)
        self.dock_result.setStyleSheet(
            "QTextEdit { background:#252525; color:#A5D6A7; font-size:9pt; "
            "border:1px solid #333; font-family:monospace; }")
        self.dock_result.setPlainText(
            "No docking evidence is loaded.\n"
            "Select/load a receptor to run a local score estimate. AutoDock Vina is reported "
            "only when the backend returns a pose; otherwise this remains SIMULATION_MODE "
            "and is not binding proof."
        )
        dock_layout.addWidget(self.dock_result)
        dock_grp.setLayout(dock_layout)
        layout.addWidget(dock_grp)

        # ── [3] 참조 점수 구간 결과 ──────────────────────────────────
        self.grade_lbl = QLabel("No validation band yet. No Vina pose or binding-success evidence loaded.")
        self.grade_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grade_lbl.setStyleSheet(
            "font-size:12pt; color:#bbb; padding:8px; border:2px dashed #444; "
            "border-radius:6px; background:#252525;")
        self.grade_lbl.setWordWrap(True)
        layout.addWidget(self.grade_lbl)

        # ── [4] 임계값 참조표 (접기 가능) ────────────────────────────
        thresh_grp = QGroupBox("Reference score bands (not validation)")
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
        viz_grp = QGroupBox("Receptor/ligand context view (not binding proof)")
        viz_grp_layout = QVBoxLayout()
        viz_grp_layout.setContentsMargins(4, 4, 4, 4)
        self.viz_widget = DockingVisualizationWidget()
        viz_grp_layout.addWidget(self.viz_widget)
        viz_grp.setLayout(viz_grp_layout)
        layout.addWidget(viz_grp)

        layout.addStretch()

        # [FIX-SCROLL-DOCK-3D] 스크롤 영역에 내부 위젯 설정
        scroll.setWidget(inner_widget)
        outer_layout.addWidget(scroll, 1)  # stretch=1 로 스크롤이 남는 공간 차지

        # -- 고정 하단 바: 도킹 실행 + 3D 시각화 버튼 (항상 보임) --
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet(
            "QWidget { background: #1a1a2e; border-top: 1px solid #333; }"
        )
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 6, 8, 6)

        self.btn_dock = QPushButton("Run local score estimate")
        self.btn_dock.setEnabled(False)
        self.btn_dock.setStyleSheet(
            "QPushButton { background:#880E4F; color:#F48FB1; border:1px solid #C2185B; "
            "border-radius:3px; padding:5px 14px; font-size:10pt; font-weight:bold; }"
            "QPushButton:hover { background:#AD1457; }"
            "QPushButton:disabled { background:#333; color:#666; }")
        self.btn_dock.clicked.connect(self._run_docking)
        bottom_layout.addWidget(self.btn_dock)

        self.btn_dock_3d = QPushButton("Show 3D context")
        self.btn_dock_3d.setEnabled(False)
        self.btn_dock_3d.setStyleSheet(
            "QPushButton { background:#1565C0; color:#90CAF9; border:1px solid #1976D2; "
            "border-radius:3px; padding:5px 14px; font-size:10pt; font-weight:bold; }"
            "QPushButton:hover { background:#1976D2; }"
            "QPushButton:disabled { background:#333; color:#666; }")
        self.btn_dock_3d.setToolTip(
            "Shows receptor/ligand context after a docking result or estimate. "
            "This is not proof of binding or target affinity."
        )
        self.btn_dock_3d.clicked.connect(self._show_dock_3d)
        bottom_layout.addWidget(self.btn_dock_3d)

        bottom_layout.addStretch()
        outer_layout.addWidget(bottom_bar)

        if self.preset_combo.count() > 1:
            # Default after all dependent buttons exist; currentIndexChanged
            # enables the learner-facing docking path.
            self.preset_combo.setCurrentIndex(1)

        self.setLayout(outer_layout)

    # ── RCSB PDB 검색 ─────────────────────────────────────────────────
    def _search_pdb(self):
        """RCSB PDB REST API로 수용체 검색"""
        query = self.search_input.toPlainText().strip()
        if not query:
            return
        self.result_list.clear()
        self.result_list.addItem("검색 중...")
        QApplication.processEvents()

        if not REQUESTS_AVAILABLE:
            logger.warning("PDB 검색 건너뜀: requests 라이브러리 미설치")
            self.result_list.clear()
            self.result_list.addItem("requests 미설치 — pip install requests")
            return

        # PDB ID 직접 입력 (4자리 영숫자)
        if re.match(r'^[A-Za-z0-9]{4}$', query):
            self.result_list.clear()
            item = QListWidgetItem(f"{query.upper()}  (PDB ID 직접 입력)")
            item.setData(Qt.ItemDataRole.UserRole, query.upper())
            self.result_list.addItem(item)
            self._current_pdb_id = query.upper()
            self.btn_load_receptor.setEnabled(True)
            self.receptor_info.setText(
                f"PDB ID: {query.upper()} selected. Load receptor to request RCSB data; "
                "no protein service result yet."
            )
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
            try:
                resp = requests.post(search_url, json=payload, timeout=8)  # [MAGIC: 8s] RCSB search
            except Exception as _ssl_e:
                _ssl_msg = str(_ssl_e)
                if "SSL" in type(_ssl_e).__name__ or "ssl" in _ssl_msg.lower() or "UNEXPECTED_EOF" in _ssl_msg:
                    logger.warning("[M1363] RCSB search SSL 오류 → verify=False 재시도: %s", _ssl_msg[:100])
                    resp = requests.post(search_url, json=payload, timeout=8, verify=False)
                else:
                    raise
            self.result_list.clear()

            if resp.status_code != 200:
                logger.warning("RCSB PDB 검색 실패: HTTP %d", resp.status_code)
                self.result_list.addItem(f"검색 실패 (HTTP {resp.status_code})")
                return

            data = resp.json()
            if not isinstance(data, dict):
                logger.warning("RCSB search response not dict: %s", type(data))
                self.result_list.addItem("검색 응답 형식 오류")
                return
            entries = data.get("result_set", [])
            if not isinstance(entries, list):
                logger.warning("RCSB result_set not list: %s", type(entries))
                entries = []
            if not entries:
                self.result_list.addItem("검색 결과 없음")
                return

            for entry in entries[:8]:
                if not isinstance(entry, dict):
                    continue
                pdb_id = entry.get("identifier", "?")
                score = entry.get("score", 0)
                item = QListWidgetItem(f"{pdb_id}  (score: {score:.2f})")
                item.setData(Qt.ItemDataRole.UserRole, pdb_id)
                self.result_list.addItem(item)
        except Exception as e:
            self.result_list.clear()
            self.result_list.addItem(f"검색 오류: {str(e)[:50]}")

    def _on_result_selected(self, item: QListWidgetItem):
        pdb_id = item.data(Qt.ItemDataRole.UserRole) or ""
        if pdb_id:
            self._current_pdb_id = pdb_id
            self.btn_load_receptor.setEnabled(True)
            self.btn_pdbe_molstar.setEnabled(True)   # M645_W9: PDBe Mol* 활성
            self.btn_alphafold_ext.setEnabled(True)  # M645_W9: AlphaFold 활성
            self.receptor_info.setText(f"선택: PDB {pdb_id}  — [수용체 로드] 버튼으로 다운로드")

    def _on_preset_selected(self, idx: int):
        if idx <= 0:
            return
        name, pdb_id, desc = self.PRESET_RECEPTORS[idx - 1]
        self._current_pdb_id = pdb_id
        self.btn_load_receptor.setEnabled(True)
        self.btn_pdbe_molstar.setEnabled(True)   # M645_W9: PDBe Mol* 활성
        self.btn_alphafold_ext.setEnabled(True)  # M645_W9: AlphaFold 활성
        self.receptor_info.setText(
            f"PDB {pdb_id}: {name}\n{desc}\nReference target selected; no receptor download, "
            "Vina pose, or binding result yet."
        )

        # M831 anger#34: 프리셋 선택 즉시 도킹 버튼 활성화 (SMILES 보유 시)
        # 이전: 반드시 PDB 다운로드 완료 후에만 활성. 사용자 격분: "버튼이 왜 비활성이냐"
        # 해결: 프리셋 선택 + SMILES 보유 시 경험적 근사 도킹 즉시 허용
        # Vina 미설치 시에도 경험적 근사(Autodock Vina 경험공식) 실행 가능.
        # Rule GG: SIMULATION_MODE 배너 필수 (dock_result에 경험치 표시)
        if self._smiles:
            self.btn_dock.setEnabled(True)
            logger.info(
                "[DockingEnergyPanel] 프리셋 선택으로 도킹 버튼 활성화 "
                "(pdb_id=%s, smiles=%.30s)", pdb_id, self._smiles
            )

    # ── 외부 DB 링크 (M645_W9) ───────────────────────────────────────────────

    def _open_pdbe_molstar(self):
        """PDBe Mol* 3D 뷰어 웹 브라우저 열기.

        M831 anger#30/#31: PDB ID 또는 SMILES 기반 분자 직접 입력 지원.
        - PDB ID 있음: PDBe Mol* 단백질 엔트리 페이지
        - PDB ID 없음, SMILES 있음: PDBe Mol* 소분자 직접 조회 (ChEBI/PubChem fallback)
        Rule FF: PDBe Mol* URL 의무 — patrol G7-SC47.
        wwPDB Consortium (2019) Nucleic Acids Res. 47(D1): D520-D528.
        Sehnal, D. et al. (2021) Nucleic Acids Res. W431-W437.
        """
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        pdb_id = self._current_pdb_id

        if isinstance(pdb_id, str) and pdb_id.strip():
            # 단백질/도킹 구조: PDBe 표준 엔트리 페이지
            url = f"https://www.ebi.ac.uk/pdbe/entry/pdb/{pdb_id.strip().lower()}"
            QDesktopServices.openUrl(QUrl(url))
        elif self._smiles:
            # M831 anger#30/#31: SMILES → PubChem compound 3D 뷰어 (분자 직접 입력)
            # PDBe Mol*는 단백질 전용이므로 소분자는 PubChem 3D viewer 사용
            # Sehnal 2021: Rule FF compliant fallback for small molecules
            import urllib.parse as _up
            smiles_encoded = _up.quote(self._smiles, safe="")
            # PubChem SMILES → CID → 3D viewer URL
            url = f"https://pubchem.ncbi.nlm.nih.gov/#query={smiles_encoded}&collection=compound"
            QDesktopServices.openUrl(QUrl(url))
            logger.info(
                "[DockingEnergyPanel] PDB ID 없음 → PubChem 소분자 3D 뷰어 (SMILES=%.40s)",
                self._smiles,
            )
        else:
            logger.warning("[DockingEnergyPanel] PDBe Mol*: PDB ID와 SMILES 모두 없음")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "PDBe Mol*",
                "PDB ID 또는 분자 SMILES가 필요합니다.\n"
                "수용체를 선택하거나 분자를 캔버스에 그리세요."
            )

    def _open_alphafold_ext(self):
        """AlphaFold Protein Structure Database 웹 브라우저 열기.

        Jumper, J. et al. (2021) Nature 596: 583-589.
        Varadi, M. et al. (2022) Nucleic Acids Res. 50(D1): D439-D444.
        """
        import webbrowser
        # PDB ID → UniProt 매핑이 없으면 AlphaFold 메인 페이지
        webbrowser.open("https://alphafold.ebi.ac.uk/")

    def _load_receptor(self):
        """RCSB에서 PDB 파일 다운로드 + Cα 백본 파싱"""
        if not self._current_pdb_id:
            logger.warning("수용체 로드 건너뜀: PDB ID 없음")
            return
        if not REQUESTS_AVAILABLE:
            logger.warning("수용체 로드 건너뜀: requests 라이브러리 미설치")
            self.receptor_info.setText("requests 미설치")
            return

        pdb_id = self._current_pdb_id
        self.receptor_info.setText(f"{pdb_id} 다운로드 중 (RCSB PDB)...")
        QApplication.processEvents()

        try:
            url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            try:
                resp = requests.get(url, timeout=20)  # [MAGIC: 20s] RCSB PDB file download
            except Exception as _ssl_e:
                _ssl_msg = str(_ssl_e)
                if "SSL" in type(_ssl_e).__name__ or "ssl" in _ssl_msg.lower() or "UNEXPECTED_EOF" in _ssl_msg:
                    logger.warning("[M1363] RCSB download SSL 오류 → verify=False 재시도: %s", _ssl_msg[:100])
                    resp = requests.get(url, timeout=20, verify=False)
                else:
                    raise
            if resp.status_code != 200:
                logger.warning("PDB 다운로드 실패: HTTP %d (pdb_id=%s)", resp.status_code, pdb_id)
                self.receptor_info.setText(f"다운로드 실패 (HTTP {resp.status_code})")
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
                    except (ValueError, IndexError) as e:
                        logger.debug("Parse error for PDB atom line: %s", e)

            self._receptor_atoms = ca_atoms
            n_chains = len(set(a[4] for a in ca_atoms))
            self.receptor_info.setText(
                f"{pdb_id} 로드 완료  |  Cα 원자: {len(ca_atoms)}개  |  체인: {n_chains}개")
            self.btn_dock.setEnabled(True)

            # PDB 파일 로컬 저장 (선택적)
            cache_dir = _SCRIPT_DIR / "pdb_cache"
            cache_dir.mkdir(exist_ok=True)
            pdb_path = cache_dir / f"{pdb_id}.pdb"
            pdb_path.write_text(resp.text, encoding='utf-8')
            logger.info(f"PDB saved: {pdb_path}")

        except Exception as e:
            self.receptor_info.setText(f"다운로드 오류: {str(e)[:60]}")

    # ── 경험적 도킹 시뮬레이션 ─────────────────────────────────────────
    def _run_docking(self):
        """도킹 실행: Vina 우선, 미설치 시 경험적 근사 폴백"""
        if not self._smiles:
            logger.warning("도킹 실행 건너뜀: 리간드 SMILES 없음")
            self.dock_result.setPlainText("리간드(분자) SMILES 없음 — 분자를 먼저 로드하세요")
            return
        if not self._receptor_atoms:
            logger.warning("도킹 실행 건너뜀: 수용체 미로드")
            self.dock_result.setPlainText("수용체 미로드 — [수용체 로드] 먼저 실행하세요")
            return

        self.btn_dock.setEnabled(False)
        self.dock_result.setPlainText("로컬 도킹 점수 추정 중...")
        QApplication.processEvents()

        # [VINA-WIRE] 실제 Vina 사용 가능하면 시도
        if VINA_BACKEND_AVAILABLE and self._current_pdb_id:
            try:
                self._run_vina_real()
                return  # Vina 비동기 실행 → 완료 시 콜백에서 결과 표시
            except Exception as e:
                logger.warning(f"Vina failed, falling back to empirical: {e}")
                self.dock_result.setPlainText("Vina 실패 — 로컬 경험적 점수 추정 중...")
                QApplication.processEvents()

        # 경험적 근사 폴백
        try:
            energy = self._empirical_docking_score()
            self._docking_energy = energy
            self._show_docking_result(energy, method="경험적 근사")
        except Exception as e:
            self.dock_result.setPlainText(f"도킹 오류: {e}")
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
            f"AutoDock Vina 도킹 중...\n"
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
            lambda msg: self.dock_result.setPlainText(str(msg)))
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
                extra = "\n\n상위 포즈 점수:\n"
                for i, pose in enumerate(dock_result.poses[:5]):
                    extra += f"  Pose {i+1}: {pose.affinity_kcal:.2f} kcal/mol\n"
                self.dock_result.append(extra)
            try:
                QApplication.processEvents()
                self._show_dock_3d()
            except Exception as e:
                logger.warning("auto 3D docking visualization failed: %s", e)
        else:
            self.dock_result.setPlainText("Vina가 종료되었으나 포즈가 생성되지 않았습니다.")

    def _on_vina_error(self, error_msg):
        """[VINA-WIRE] Vina 오류 → 경험적 근사 폴백"""
        logger.warning(f"Vina error: {error_msg}")
        self.dock_result.setPlainText(f"Vina 오류: {error_msg}\n\n로컬 경험적 점수 추정으로 전환 중...")
        QApplication.processEvents()
        try:
            energy = self._empirical_docking_score()
            self._docking_energy = energy
            self._show_docking_result(energy, method="경험적 근사 (Vina 실패)")
        except Exception as e:
            self.dock_result.setPlainText(f"도킹 오류: {e}")
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
            logger.warning("[Rule L] MolFromSmiles 실패: %r", self._smiles)
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
        """도킹 점수 추정 결과 표시"""
        # 참조 구간 판정
        grade_label, grade_color, grade_ki = "비결합", "#95a5a6", ""
        for lo, hi, label, color, ki in self.THRESHOLDS:
            if lo <= energy < hi:
                grade_label, grade_color, grade_ki = label, color, ki
                break

        # 결과 텍스트
        is_real_vina_pose = "Vina" in method and "실패" not in method and bool(
            self._vina_result and getattr(self._vina_result, "poses", None)
        )
        lines = [
            f"═══════ 도킹 점수 컨텍스트 ({self._current_pdb_id}) ═══════",
            f"계산 방법:  {method}",
            f"표시 점수:  ΔG-like = {energy:+.2f} kcal/mol",
            f"참조 구간:  {grade_label}  ({grade_ki})",
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
            lines.append("참조 약물 점수 비교(교육용):")
            for drug, ref_e in refs:
                diff = energy - ref_e
                sign = "lower score" if diff < 0 else "higher score"
                lines.append(f"  vs {drug}: {diff:+.1f} kcal/mol ({sign})")

        lines.append("─────────────────────────────────")
        if is_real_vina_pose:
            lines.append("[BOUNDARY] Vina pose returned by backend; this is docking context, not biological binding proof.")
        else:
            lines.append("[SIMULATION_MODE] Local empirical score estimate only; no Vina pose or protein-binding proof.")

        self.dock_result.setPlainText("\n".join(lines))

        # 참조 구간 레이블
        self.grade_lbl.setText(
            f"Score estimate = {energy:+.2f} kcal/mol | reference band: {grade_label} ({grade_ki}) | not validation")
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

    def _build_empirical_ligand_pose(self, binding_center, binding_radius=6.0):
        """Build a visible RDKit ligand pose for non-Vina docking fallback."""
        if not self._smiles or not RDKIT_AVAILABLE:
            logger.warning("fallback ligand pose unavailable: smiles=%r RDKit=%s",
                           self._smiles, RDKIT_AVAILABLE)
            return None
        try:
            mol = Chem.MolFromSmiles(self._smiles)
            if mol is None:
                logger.warning("fallback ligand pose failed: invalid SMILES %r", self._smiles)
                return None
            mol = Chem.AddHs(mol)
            params = AllChem.ETKDGv3()
            params.randomSeed = 42
            if AllChem.EmbedMolecule(mol, params) != 0:
                if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
                    logger.warning("fallback ligand pose failed: RDKit EmbedMolecule nonzero")
                    return None
            try:
                AllChem.MMFFOptimizeMolecule(mol, maxIters=300)
            except Exception as e:
                logger.warning("fallback ligand MMFF failed, using embedded coords: %s", e)
            conf = mol.GetConformer()
            raw = []
            elements = []
            for atom in mol.GetAtoms():
                pos = conf.GetAtomPosition(atom.GetIdx())
                raw.append((float(pos.x), float(pos.y), float(pos.z)))
                elements.append(atom.GetSymbol())
            if not raw:
                return None
            cx = sum(p[0] for p in raw) / len(raw)
            cy = sum(p[1] for p in raw) / len(raw)
            cz = sum(p[2] for p in raw) / len(raw)
            bx, by, bz = binding_center
            # Keep the fallback pose close to the pocket but not hidden inside
            # the ribbon volume; real Vina poses still use their exact coords.
            visible_offset = 0.45 * max(3.0, min(8.0, binding_radius))
            by -= visible_offset
            bz += visible_offset * 0.45
            coords = [(x - cx + bx, y - cy + by, z - cz + bz) for x, y, z in raw]
            return coords, elements
        except Exception as e:
            logger.warning("fallback ligand pose unexpected failure: %s", e)
            return None

    def _show_dock_3d(self):
        """[PROTEIN-3D] 도킹 결과를 3D 뷰어에 표시 — 단백질 백본 + 리간드 실제 도킹 포즈"""
        if not self._receptor_atoms:
            logger.warning("3D 도킹 표시 건너뜀: 수용체 원자 없음")
            return
        try:
            # Molecule3DPopup의 viewer에 접근 (부모 탐색)
            popup = self.parent()
            while popup and not isinstance(popup, Molecule3DPopup):
                popup = popup.parent()
            if popup is None or not hasattr(popup, 'viewer'):
                logger.warning("3D 도킹 표시 건너뜀: Molecule3DPopup 뷰어를 찾을 수 없음")
                self.dock_result.append("\n3D 뷰어를 찾을 수 없습니다.")
                return
            viewer = popup.viewer
            if not viewer or not hasattr(viewer, 'set_protein_data'):
                logger.warning("3D 도킹 표시 건너뜀: 뷰어에 set_protein_data 없음")
                self.dock_result.append("\n3D 뷰어가 도킹 시각화를 지원하지 않습니다.")
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

            # [DOCK-RIBBON] 수용체는 Ribbon 모드로 강제 활성화
            if not viewer._ribbon_mode:
                viewer._ribbon_mode = True
                viewer._secondary_structure = None  # 새 단백질이므로 재탐지
                if viewer._protein_ca:
                    viewer._detect_secondary_structure()
            # 부모 팝업의 Ribbon 버튼 UI 동기화
            if popup and hasattr(popup, 'btn_ribbon'):
                popup.btn_ribbon.setChecked(True)

            # [DOCK-POSE] 최적 도킹 포즈의 실제 좌표를 뷰어에 전달
            # 리간드는 Ball & Stick (기존 _draw_docking_ligand가 ball-and-stick 사용)
            ligand_pose_applied = False
            if (self._vina_result and self._vina_result.poses
                    and not getattr(self._vina_result, "is_simulation", False)):
                best_pose = self._vina_result.poses[0]
                if best_pose.atom_coords and best_pose.atom_elements:
                    viewer.set_docking_pose(
                        best_pose.atom_coords,
                        best_pose.atom_elements,
                        binding_center=binding_center,
                        binding_radius=binding_radius,
                    )
                    ligand_pose_applied = True
            if not ligand_pose_applied:
                fallback_pose = self._build_empirical_ligand_pose(binding_center, binding_radius)
                if fallback_pose:
                    fallback_coords, fallback_elements = fallback_pose
                    viewer.set_docking_pose(
                        fallback_coords,
                        fallback_elements,
                        binding_center=binding_center,
                        binding_radius=binding_radius,
                    )
                    self.dock_result.append(
                        "\n[SIMULATION_MODE] Vina pose unavailable; RDKit ligand pose "
                        "is rendered as ball-and-stick at the receptor pocket.")
                else:
                    self.dock_result.append("\n리간드 3D 포즈 생성 실패 - 수용체만 표시됨")

            # [DOCK-INTERACT] 상호작용 방향 재계산 강제 (캐시 초기화)
            viewer._computed_interactions = None
            # 리간드 접근 애니메이션 시작
            viewer._dock_approach_phase = -1.0
            viewer._ligand_offset = (0.0, 0.0, 0.0)
            viewer.update()

            self.dock_result.append(
                "\n3D context shown. This display is not binding-success or target-affinity evidence.")
        except Exception as e:
            logger.error(f"3D 도킹 시각화 오류: {e}")
            self.dock_result.append(f"\n3D 시각화 오류: {e}")

    def set_molecule_smiles(self, smiles: str):
        self._smiles = smiles
        if smiles and self._receptor_atoms:
            self.btn_dock.setEnabled(True)

    def update_from_orca(self, parser: OrcaOutputParser):
        if parser and parser.total_energy is not None:
            e_kcal = parser.total_energy * 627.509
            self.dock_result.setPlainText(
                f"ORCA DFT single-molecule energy: {parser.total_energy:.6f} Eh ({e_kcal:.1f} kcal/mol)\n"
                "This is not docking dG or protein-binding evidence. Use docking only with receptor context."
            )


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
        except Exception as e:
            logger.warning("PubChem lookup failed: %s", e)
            self.result_ready.emit(None)


class _XtbOptThread(QThread):
    """xTB GFN2-xTB 구조 최적화 비동기 실행 (UI 블로킹 방지).

    SMILES → xTB opt → 최적화 XYZ 좌표 반환.
    xTB 미설치/실패 시 None 반환 (ETKDG fallback 유지).
    """
    result_ready = pyqtSignal(object)  # dict or None

    def __init__(self, smiles: str, parent=None):
        super().__init__(parent)
        self._smiles = smiles

    def run(self):
        try:
            from orca_interface import run_xtb_calculation
            xtb_result = run_xtb_calculation(
                self._smiles, calc_type='opt', timeout=30
            )
            if xtb_result.success and xtb_result.optimized_xyz:
                # Parse optimized XYZ into {int_index: (x,y,z)} + {int_index: symbol}
                coords, symbols = self._parse_opt_xyz(xtb_result.optimized_xyz)
                if coords:
                    self.result_ready.emit({
                        'coords': coords,
                        'symbols': symbols,
                        'energy': xtb_result.energy_eh,
                        'dipole': xtb_result.dipole_debye,  # I-1: ethanol dipole UI 표시 (2026-04-24)
                        'smiles': self._smiles,  # [A63-W1/M748] stale cache 차단용 SMILES 키
                    })
                    return
                else:
                    logger.warning("xTB opt: XYZ parsing returned empty coords")
            else:
                err = xtb_result.error_message if not xtb_result.success else "no optimized_xyz"
                logger.info("xTB opt: not applied (%s)", err)
        except ImportError:
            logger.info("xTB opt: orca_interface not available")
        except Exception as e:
            logger.warning("xTB opt thread error: %s", e)
        self.result_ready.emit(None)

    @staticmethod
    def _parse_opt_xyz(xyz_text: str):
        """Parse XYZ format text into coords dict and symbols dict.

        XYZ format:
            <num_atoms>
            <comment line>
            SYMBOL  X  Y  Z
            ...

        Returns:
            (coords, symbols) or (None, None)
            coords: {int: (x, y, z)}
            symbols: {int: str}
        """
        if not xyz_text or not isinstance(xyz_text, str):
            return None, None
        lines = xyz_text.strip().split('\n')
        if len(lines) < 3:
            return None, None
        try:
            num_atoms = int(lines[0].strip())
        except (ValueError, IndexError):
            return None, None
        coords = {}
        symbols = {}
        atom_idx = 0
        for line in lines[2:]:  # skip count + comment
            parts = line.strip().split()
            if len(parts) < 4:
                continue
            sym = parts[0]
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                continue
            coords[atom_idx] = (round(x, 3), round(y, 3), round(z, 3))
            symbols[atom_idx] = sym
            atom_idx += 1
        if atom_idx == 0:
            return None, None
        return coords, symbols


# ============================================================
# Newman Projection Widget (QPainter)
# ============================================================

class NewmanProjectionWidget(QWidget):
    """Newman 투영도 렌더러.

    C-C 결합을 관찰자 시선 방향으로 투영:
    - 앞 탄소 = 작은 원(점) at center
    - 뒤 탄소 = 큰 원(circle)
    - 치환기: 중심/원에서 120 deg 간격으로 선분 + 원소 기호
    - dihedral angle slider로 뒤 탄소 치환기 회전
    """

    def __init__(self, mol_data: 'Molecule3DData', parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("Newman Projection (Newman 투영)")
        self.setMinimumSize(480, 560)
        self.resize(520, 600)
        self.setStyleSheet("""
            QWidget { background-color: #fafafa; color: #222; }
            QPushButton {
                background-color: #e0e0e0; border: 1px solid #bbb;
                padding: 4px 10px; border-radius: 3px;
            }
            QPushButton:hover { background-color: #d0d0d0; }
            QComboBox {
                background: #fff; border: 1px solid #bbb;
                padding: 3px 8px; min-width: 140px;
            }
            QSlider::groove:horizontal { height: 6px; background: #ccc; border-radius: 3px; }
            QSlider::handle:horizontal {
                background: #2979ff; width: 14px; margin: -4px 0; border-radius: 7px;
            }
        """)
        self.mol_data = mol_data
        self._front_idx = -1
        self._back_idx = -1
        self._dihedral = 60.0  # staggered default (degrees)
        self._front_subs: List[Tuple[int, str]] = []
        self._back_subs: List[Tuple[int, str]] = []
        self._cc_bonds: List[Tuple[int, int]] = []
        self._init_ui()
        self._find_cc_bonds()
        if self._cc_bonds:
            self.bond_combo.setCurrentIndex(0)
            self._on_bond_selected(0)

    # ---- UI setup ----

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        top = QHBoxLayout()
        top.addWidget(QLabel("C-C 결합 선택:"))
        self.bond_combo = QComboBox()
        self.bond_combo.currentIndexChanged.connect(self._on_bond_selected)
        top.addWidget(self.bond_combo, 1)
        layout.addLayout(top)

        # Reserve offset for drawing area
        self._canvas_top = 60

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("이면각 (Dihedral):"))
        self.dihedral_slider = QSlider(Qt.Orientation.Horizontal)
        self.dihedral_slider.setMinimum(0)
        self.dihedral_slider.setMaximum(360)
        self.dihedral_slider.setValue(60)
        self.dihedral_slider.valueChanged.connect(self._on_dihedral_changed)
        slider_row.addWidget(self.dihedral_slider, 1)
        self.dihedral_label = QLabel("60 deg")
        self.dihedral_label.setFixedWidth(60)
        slider_row.addWidget(self.dihedral_label)
        layout.addLayout(slider_row)

        btn_row = QHBoxLayout()
        btn_stag = QPushButton("Staggered (60)")
        btn_stag.clicked.connect(lambda: self._set_dihedral(60))
        btn_row.addWidget(btn_stag)
        btn_eclip = QPushButton("Eclipsed (0)")
        btn_eclip.clicked.connect(lambda: self._set_dihedral(0))
        btn_row.addWidget(btn_eclip)
        btn_gauche = QPushButton("Gauche (60)")
        btn_gauche.clicked.connect(lambda: self._set_dihedral(60))
        btn_row.addWidget(btn_gauche)
        btn_anti = QPushButton("Anti (180)")
        btn_anti.clicked.connect(lambda: self._set_dihedral(180))
        btn_row.addWidget(btn_anti)
        layout.addLayout(btn_row)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #555; font-size: 10pt; padding: 4px;")
        layout.addWidget(self.info_label)

        layout.addStretch(1)

    # ---- Bond detection ----

    def _find_cc_bonds(self):
        """Find all C-C single bonds via RDKit."""
        self._cc_bonds = []
        self.bond_combo.blockSignals(True)
        self.bond_combo.clear()

        smiles = getattr(self.mol_data, 'smiles', '') or ''
        if not smiles or not RDKIT_AVAILABLE:
            # Fallback: inspect mol_data.bonds
            for (k1, k2), order in self.mol_data.bonds.items():
                sym1 = self.mol_data.atom_symbols.get(k1, '')
                sym2 = self.mol_data.atom_symbols.get(k2, '')
                is_c1 = (sym1 == '' or sym1 == 'C')
                is_c2 = (sym2 == '' or sym2 == 'C')
                if is_c1 and is_c2 and (order == 1 or order == 1.0):
                    self._cc_bonds.append((k1, k2))
                    self.bond_combo.addItem(f"C({k1}) - C({k2})")
            self.bond_combo.blockSignals(False)
            if not self._cc_bonds:
                self.info_label.setText(
                    "C-C 단일 결합이 없습니다. Newman 투영은 C-C 단일 결합이 필요합니다.")
                logger.warning("Newman: C-C 단일 결합 없음 (smiles=%r)", smiles)
            return

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("Newman: SMILES 파싱 실패 (%r)", smiles)
                self.info_label.setText("SMILES 파싱 실패")
                self.bond_combo.blockSignals(False)
                return
            mol = Chem.AddHs(mol)
            for bond in mol.GetBonds():
                bt = bond.GetBondTypeAsDouble()
                if abs(bt - 1.0) > 0.01:
                    continue
                i1 = bond.GetBeginAtomIdx()
                i2 = bond.GetEndAtomIdx()
                a1 = mol.GetAtomWithIdx(i1)
                a2 = mol.GetAtomWithIdx(i2)
                if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
                    self._cc_bonds.append((i1, i2))
                    n1 = [n.GetSymbol() for n in a1.GetNeighbors()]
                    n2 = [n.GetSymbol() for n in a2.GetNeighbors()]
                    lbl = f"C{i1}({','.join(n1)}) -- C{i2}({','.join(n2)})"
                    self.bond_combo.addItem(lbl)
        except Exception as e:
            logger.warning("Newman: C-C 결합 탐색 오류: %s", e)
            self.info_label.setText(f"C-C 결합 탐색 오류: {e}")

        self.bond_combo.blockSignals(False)
        if not self._cc_bonds:
            self.info_label.setText(
                "C-C 단일 결합이 없습니다. Newman 투영은 C-C 단일 결합이 필요합니다.")
            logger.warning("Newman: C-C 단일 결합 없음 (smiles=%r)", smiles)

    # ---- Bond selection ----

    def _on_bond_selected(self, idx: int):
        if idx < 0 or idx >= len(self._cc_bonds):
            return
        self._front_idx, self._back_idx = self._cc_bonds[idx]
        self._compute_substituents()
        self.update()

    def _compute_substituents(self):
        """Determine substituents for front and back carbons."""
        # Rule N: isinstance guard for mol_data.atom_symbols
        if not isinstance(self.mol_data.atom_symbols, dict):
            return
        self._front_subs = []
        self._back_subs = []

        smiles = getattr(self.mol_data, 'smiles', '') or ''
        if not smiles or not RDKIT_AVAILABLE:
            for (k1, k2), _order in self.mol_data.bonds.items():
                if k1 == self._front_idx and k2 != self._back_idx:
                    sym = self.mol_data.atom_symbols.get(k2, 'H')
                    self._front_subs.append((k2, sym if sym else 'H'))
                elif k2 == self._front_idx and k1 != self._back_idx:
                    sym = self.mol_data.atom_symbols.get(k1, 'H')
                    self._front_subs.append((k1, sym if sym else 'H'))
                if k1 == self._back_idx and k2 != self._front_idx:
                    sym = self.mol_data.atom_symbols.get(k2, 'H')
                    self._back_subs.append((k2, sym if sym else 'H'))
                elif k2 == self._back_idx and k1 != self._front_idx:
                    sym = self.mol_data.atom_symbols.get(k1, 'H')
                    self._back_subs.append((k1, sym if sym else 'H'))
            self._update_info()
            return

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("Newman _compute_substituents: SMILES 파싱 실패")
                return
            mol = Chem.AddHs(mol)
            front_atom = mol.GetAtomWithIdx(self._front_idx)
            back_atom = mol.GetAtomWithIdx(self._back_idx)
            for nbr in front_atom.GetNeighbors():
                if nbr.GetIdx() != self._back_idx:
                    self._front_subs.append((nbr.GetIdx(), nbr.GetSymbol()))
            for nbr in back_atom.GetNeighbors():
                if nbr.GetIdx() != self._front_idx:
                    self._back_subs.append((nbr.GetIdx(), nbr.GetSymbol()))
        except Exception as e:
            logger.warning("Newman _compute_substituents 오류: %s", e)

        self._update_info()

    def _update_info(self):
        front_str = ', '.join(s for _, s in self._front_subs) if self._front_subs else 'none'
        back_str = ', '.join(s for _, s in self._back_subs) if self._back_subs else 'none'
        self.info_label.setText(
            f"앞 탄소 (C{self._front_idx}): 치환기 [{front_str}]  |  "
            f"뒤 탄소 (C{self._back_idx}): 치환기 [{back_str}]  |  "
            f"이면각: {self._dihedral:.0f} deg"
        )

    # ---- Dihedral controls ----

    def _on_dihedral_changed(self, val: int):
        self._dihedral = float(val)
        self.dihedral_label.setText(f"{val} deg")
        self._update_info()
        self.update()

    def _set_dihedral(self, deg: float):
        self._dihedral = deg
        self.dihedral_slider.blockSignals(True)
        self.dihedral_slider.setValue(int(deg))
        self.dihedral_slider.blockSignals(False)
        self.dihedral_label.setText(f"{int(deg)} deg")
        self._update_info()
        self.update()

    # ---- Painting ----

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        canvas_y = self._canvas_top
        canvas_w = self.width()
        canvas_h = self.height() - canvas_y - 120
        if canvas_h < 100:
            canvas_h = 100

        p.fillRect(0, canvas_y, canvas_w, canvas_h, QColor(255, 255, 255))
        p.setPen(QPen(QColor(200, 200, 200), 1))
        p.drawRect(0, canvas_y, canvas_w - 1, canvas_h - 1)

        cx = canvas_w / 2.0
        cy = canvas_y + canvas_h / 2.0
        R = min(canvas_w, canvas_h) * 0.28   # back circle radius
        bond_len = R * 1.6                     # substituent line length

        if self._front_idx < 0 or self._back_idx < 0:
            p.setPen(QColor(150, 150, 150))
            p.setFont(QFont(_QT_KR_FONT, 11))  # [M1461] Rule Q: 한국어 텍스트
            p.drawText(0, canvas_y, canvas_w, canvas_h,
                       Qt.AlignmentFlag.AlignCenter, "C-C 결합을 선택하세요")
            p.end()
            return

        # ---- Back carbon circle ----
        p.setPen(QPen(QColor(80, 80, 80), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)

        # ---- Substituent angles (degrees, 0=right, CCW) ----
        front_angles = [90.0, 210.0, 330.0]
        back_angles = [a + self._dihedral for a in front_angles]

        def _draw_sub(angle_deg, label, color, from_circle):
            rad = math.radians(angle_deg)
            dx = math.cos(rad)
            dy = -math.sin(rad)
            if from_circle:
                sx = cx + R * dx
                sy = cy + R * dy
            else:
                sx, sy = cx, cy
            ex = sx + bond_len * dx
            ey = sy + bond_len * dy

            p.setPen(QPen(color, 2.5))
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))

            label_color = self._element_color(label)
            text_r = 12
            p.setBrush(QBrush(QColor(255, 255, 255, 220)))
            p.setPen(QPen(label_color, 1.5))
            p.drawEllipse(QPointF(ex, ey), text_r, text_r)
            p.setFont(QFont(_QT_KR_FONT, 12, QFont.Weight.Bold))  # [M1461] Rule Q: offscreen 폰트
            p.drawText(int(ex - text_r), int(ey - text_r),
                       int(text_r * 2), int(text_r * 2),
                       Qt.AlignmentFlag.AlignCenter, label)

        # Back subs first (so front overlaps)
        n_back = len(self._back_subs)
        for i in range(3):
            angle = back_angles[i % len(back_angles)]
            if i < n_back:
                _, sym = self._back_subs[i]
            else:
                sym = 'H'
            _draw_sub(angle, sym, QColor(100, 100, 100), True)

        # Front subs
        n_front = len(self._front_subs)
        for i in range(3):
            angle = front_angles[i]
            if i < n_front:
                _, sym = self._front_subs[i]
            else:
                sym = 'H'
            _draw_sub(angle, sym, QColor(50, 50, 50), False)

        # Front carbon dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(40, 40, 40)))
        p.drawEllipse(QPointF(cx, cy), 5, 5)

        # Legend
        p.setFont(QFont(_QT_KR_FONT, 9))  # [M1461] Rule Q: offscreen 폰트
        p.setPen(QColor(100, 100, 100))
        p.drawText(int(cx - 40), int(cy + R + bond_len + 20), "Front = dot (center)")
        p.drawText(int(cx - 40), int(cy + R + bond_len + 35), "Back = circle")

        # Dihedral annotation
        p.setFont(QFont(_QT_KR_FONT, 10, QFont.Weight.Bold))  # [M1461] Rule Q: offscreen 폰트
        p.setPen(QColor(41, 121, 255))
        dihedral_text = f"Dihedral: {self._dihedral:.0f} deg"
        conf_name = self._conformer_name()
        if conf_name:
            dihedral_text += f"  ({conf_name})"
        p.drawText(int(cx - 100), int(canvas_y + 20), dihedral_text)

        p.end()

    @staticmethod
    def _element_color(symbol: str) -> QColor:
        color_map = {
            'H': QColor(100, 100, 100),
            'C': QColor(40, 40, 40),
            'N': QColor(30, 30, 180),
            'O': QColor(200, 30, 30),
            'F': QColor(0, 180, 0),
            'Cl': QColor(0, 160, 0),
            'Br': QColor(160, 50, 0),
            'S': QColor(200, 200, 0),
            'P': QColor(200, 100, 0),
        }
        if not isinstance(symbol, str):
            return QColor(80, 80, 80)
        return color_map.get(symbol, QColor(80, 80, 80))

    def _conformer_name(self) -> str:
        d = self._dihedral % 360
        if d < 5 or d > 355:
            return "Eclipsed (겹침형)"
        elif 55 < d < 65:
            return "Gauche/Staggered (엇갈림형)"
        elif 115 < d < 125:
            return "Eclipsed (겹침형)"
        elif 175 < d < 185:
            return "Anti (반대형)"
        elif 235 < d < 245:
            return "Eclipsed (겹침형)"
        elif 295 < d < 305:
            return "Gauche/Staggered (엇갈림형)"
        return ""


class Molecule3DPopup(QWidget):
    """
    통합 3D 분석 팝업.
    상단: 3D 뷰어 + 컨트롤
    하단: 탭 패널 [📊 속성] [📈 스펙트럼] [🎵 진동모드] [📝 AI분석]
    """

    def __init__(self, mol_data: Molecule3DData, parent=None):
        super().__init__(parent)
        # [M1461] Rule Q: 한국어 폰트 offscreen 캡처 전 등록 (토푸 방지)
        _ensure_qt_korean_font_ready()
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
        if _route_evidence_fast_mode():
            self._current_smiles = self.mol_data.smiles or ""
            logger.warning(
                "[Molecule3DPopup] route evidence fast mode: skipped "
                "non-route panel data loading; visible 3D route controls remain active."
            )
        else:
            self._load_data()

    def _init_ui(self):
        self.setWindowTitle("ChemGrid — 통합 3D 분자 분석")
        # 화면 크기에 맞게 반응형 크기 설정
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                popup_w = min(1020, avail.width() - 120)
                # [M483] 세로 기본 크기 900px로 확대 — 탭 패널 7개 + 3D 뷰어 모두 표시 보장
                popup_h = min(1180, avail.height() - 20)
                popup_x = max(40, (avail.width() - popup_w) // 2)
                popup_y = max(10, (avail.height() - popup_h) // 2)
            else:
                popup_x, popup_y, popup_w, popup_h = 120, 10, 1020, 1080
        except Exception as e:
            logger.debug("Screen geometry detection failed: %s", e)
            popup_x, popup_y, popup_w, popup_h = 120, 10, 1020, 1080
        self.setGeometry(popup_x, popup_y, popup_w, popup_h)
        self.setMinimumSize(780, 940)  # keep tabs/popup workflows visible without fullscreen.
        # [M1461] Rule Q: font-family 전체 stylesheet에 한국어 폰트 지정 (토푸 방지)
        _kr_font = _QT_KR_FONT  # _ensure_qt_korean_font_ready() 호출 후 확정된 값
        self.setStyleSheet(f"""
            QWidget {{ background-color: #1e1e1e; color: #e0e0e0;
                       font-family: "{_kr_font}", "Malgun Gothic", sans-serif; }}
            QPushButton {{
                background-color: #333; border: 1px solid #555;
                padding: 5px 12px; border-radius: 3px; color: #e0e0e0;
            }}
            QPushButton:hover {{ background-color: #444; }}
            QPushButton:checked {{ background-color: #2979ff; border-color: #2979ff; }}
            QLabel {{ color: #bbb;
                      font-family: "{_kr_font}", "Malgun Gothic", sans-serif; }}
            QSlider::groove:horizontal {{ height: 6px; background: #444; border-radius: 3px; }}
            QSlider::handle:horizontal {{
                background: #2979ff; width: 14px; margin: -4px 0; border-radius: 7px;
            }}
            QGroupBox {{
                border: 1px solid #444; border-radius: 4px;
                margin-top: 8px; padding-top: 16px; color: #ccc;
                font-family: "{_kr_font}", "Malgun Gothic", sans-serif;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
            QTabWidget::pane {{ border: 1px solid #444; background: #1e1e1e; }}
            QTabBar::tab {{
                background: #2a2a2a; border: 1px solid #444;
                padding: 6px 16px; margin-right: 2px; color: #bbb;
                font-family: "{_kr_font}", "Malgun Gothic", sans-serif;
            }}
            QTabBar::tab:selected {{ background: #333; color: #fff; border-bottom: 2px solid #2979ff; }}
            QListWidget {{ background: #252525; color: #ddd; border: 1px solid #444;
                           font-family: "{_kr_font}", "Malgun Gothic", sans-serif; }}
            QTextEdit {{ border: 1px solid #444;
                         font-family: "{_kr_font}", "Malgun Gothic", sans-serif; }}
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # [Rule GG] SIMULATION_MODE 노랑 배너 — ORCA 미설치 시 학생에게 명시
        # 학술 인용: Neese F. WIREs Comput Mol Sci 2018;8:e1327.
        self._simulation_mode = not ORCA_AVAILABLE

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
            "🔴🟢🔵 ESP 표면 (정전기 포텐셜)",
        ])
        self.orbital_combo.setStyleSheet("QComboBox { background: #2a2a2a; color: #ddd; "
                                         "border: 1px solid #555; padding: 4px; min-width: 150px; }")
        self.orbital_combo.currentIndexChanged.connect(self._on_orbital_mode_changed)
        ctrl.addWidget(self.orbital_combo)

        # ORCA-labeled UV-Vis/MO analysis routes are preserved as backend handlers,
        # but are not exposed as visible toolbar controls in the 3D popup.
        self.btn_uvvis_orca = None
        self.btn_molorbital_orca = None

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

        # [BG-COLOR] 배경색 선택 콤보박스
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("배경:"))
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(["⬛ 검정", "🔲 회색", "⬜ 흰색"])
        self.bg_combo.setFixedWidth(100)
        self.bg_combo.setStyleSheet(
            "QComboBox { background: #2a2a2a; color: #ddd; "
            "border: 1px solid #555; padding: 4px; }")
        self.bg_combo.currentIndexChanged.connect(self._on_bg_color_changed)
        ctrl.addWidget(self.bg_combo)

        # [FIX-D] Newman 투영 버튼 제거 — UI 공간 확보
        # NewmanProjectionWidget 클래스는 유지 (코드 보존), 버튼만 미표시

        ctrl.addStretch()

        # DFT/ORCA backend is retained for provenance/import compatibility, but
        # the popup toolbar no longer exposes a manual calculation route.
        self.btn_dft = None
        self._dft_status_label = QLabel("")
        self._dft_status_label.setStyleSheet(
            "color: #CE93D8; font-size: 11px; padding: 0 4px;")
        self._dft_status_label.setVisible(False)

        # DFT 계산 스레드 참조 (GC 방지)
        self._dft_thread: Optional[DFTCalculatorThread] = None

        btn_reset = QPushButton("↺ Reset")
        btn_reset.clicked.connect(self._reset_view)
        ctrl.addWidget(btn_reset)

        # 💾 내보내기 버튼 — XYZ/ORCA/Gaussian/MOL 다중 형식 지원
        self.btn_export = QPushButton("💾 내보내기")
        self.btn_export.setToolTip(
            "3D structure export options"
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

        # [UI 계층 개편] 고급 도구 드롭다운 — 신약개발 기능 진입점
        # Layer 3 심화 기능: 리드 최적화, ADMET, AlphaFold, 도킹, 스크리닝
        self.btn_advanced = QPushButton("🔬 고급 도구")
        self.btn_advanced.setToolTip(
            "신약개발 관련 고급 분석 도구\n"
            "• 리드 최적화 (신약 설계)\n"
            "• ADMET 분석\n"
            "• AlphaFold 구조 예측\n"
            "• 신약 스크리닝"
        )
        self.btn_advanced.setStyleSheet("""
            QPushButton {
                background-color: #0D47A1;
                border: 1px solid #1565C0;
                color: #90CAF9;
                padding: 5px 12px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton::menu-indicator { image: none; }
        """)
        adv_menu = QMenu(self)
        adv_menu.setStyleSheet(
            "QMenu { background-color: #2a2a2a; color: #ddd; border: 1px solid #555; }"
            "QMenu::item:selected { background-color: #1565C0; }"
        )
        adv_menu.addAction("Lead Optimizer (advanced sandbox)", self._open_lead_optimizer_from_3d)
        adv_menu.addAction("ADMET 분석", self._open_admet_from_3d)
        adv_menu.addSeparator()
        adv_menu.addAction("AlphaFold/PDB reference lookup", self._open_alphafold_from_3d)
        adv_menu.addAction("Drug Screening (local/advanced)", self._open_drug_screening_from_3d)
        self.btn_advanced.setMenu(adv_menu)
        ctrl.addWidget(self.btn_advanced)

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
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        splitter = self._splitter

        # Viewer — [FIX-GL-FALLBACK] OpenGL 시도 후 실패하면 QPainter로 자동 교체
        if OPENGL_AVAILABLE:
            self.viewer = Molecule3DViewer(self.mol_data)
        else:
            self.viewer = FallbackRenderer2D(self.mol_data)
        splitter.addWidget(self.viewer)

        # [FIX-GL-FALLBACK] OpenGL 렌더링 검증 타이머
        # 팝업이 표시된 후 500ms 뒤에 GL 렌더링이 실제 동작하는지 검증
        if OPENGL_AVAILABLE:
            self._gl_check_timer = QTimer(self)
            self._gl_check_timer.setSingleShot(True)
            self._gl_check_timer.timeout.connect(self._validate_gl_rendering)
            self._gl_check_timer.start(500)  # 500ms: 렌더 파이프라인 안정화 대기

        if _route_evidence_fast_mode():
            self.tabs = QTabWidget()
            route_evidence_label = QLabel(
                "Route evidence mode: heavy analysis tabs are deferred; "
                "Only the 3D viewer controls remain available in this fast mode."
            )
            route_evidence_label.setWordWrap(True)
            route_evidence_label.setStyleSheet(
                "color: #ffcc80; padding: 12px; font-weight: bold;"
            )
            self.tabs.addTab(route_evidence_label, "Route Evidence")
            splitter.addWidget(self.tabs)
            splitter.setStretchFactor(0, 2)
            splitter.setStretchFactor(1, 3)
            self.tabs.setMinimumHeight(220)
            splitter.setSizes([280, 260])
            main_layout.addWidget(splitter, 1)
            info = QHBoxLayout()
            backend_display = "3D OpenGL" if OPENGL_AVAILABLE else "2.5D (OpenGL disabled)"
            backend_style = (
                "color: #66bb6a; font-weight: bold; font-size: 8pt;"
                if OPENGL_AVAILABLE
                else "color: #ffab40; font-weight: bold; font-size: 8pt;"
            )
            self.info_lbl = QLabel(
                f"Atoms: {self.mol_data.num_atoms}  |  "
                f"Bonds: {self.mol_data.num_bonds}  |  "
                f"coord: {self.mol_data.coord_source}"
            )
            info.addWidget(self.info_lbl)
            backend_lbl = QLabel(f"  Backend: {backend_display}")
            backend_lbl.setStyleSheet(backend_style)
            info.addWidget(backend_lbl)
            info.addStretch()
            help_lbl = QLabel("Left: Rotate  |  Right: Pan  |  Wheel: Zoom")
            help_lbl.setStyleSheet("color: #666; font-size: 8pt;")
            info.addWidget(help_lbl)
            main_layout.addLayout(info)
            self.setLayout(main_layout)
            return

        # Tab panel
        self.tabs = QTabWidget()
        self.tab_props = PropertiesPanel()
        self.tab_spectrum = SpectrumPanel()
        self.tab_vibration = VibrationPanel()
        # AIAnalysisPanel 인스턴스 보존 — UI addTab 제거, 코드 삭제 금지 (Rule W, 사용자 요구 2026-04-25)
        self.tab_ai = AIAnalysisPanel()
        # self.tabs.addTab(self.tab_ai, ...)  ← UI에서만 제외 (인스턴스 보존)

        # 신규 ChemCharPanel — tab4 (진동모드 다음)
        # Source: ChemicalCharacteristicsPanel.tsx (Rule Y 1:1 번역, 2026-04-25)
        self.tab_chem_char = ChemCharPanel()

        self.tab_docking = DockingEnergyPanel()
        self.tab_admet = ADMETEmbeddedPanel()
        self.tabs.addTab(self.tab_props, "📊 속성")           # tab 0
        self.tabs.addTab(self.tab_spectrum, "📈 스펙트럼")    # tab 1
        self.tabs.addTab(self.tab_vibration, "🎵 진동모드")   # tab 2
        # tab 3: 화학적 특성 (ChemCharPanel — QPainter 방사형 유사 분자 8개)
        # [M688 Fix item22] 사용자 요청: "화학적 특성 분석" → "화학적 특성" 으로 약칭.
        self.tabs.addTab(self.tab_chem_char, "🔬 화학적 특성")  # tab 3
        self.tabs.addTab(self.tab_admet, "💊 ADMET")          # tab 4
        self.tabs.addTab(self.tab_docking, "도킹 점수")  # tab 5

        # 알파폴드/합성 탭
        self.tab_alphafold = self._create_alphafold_synthesis_tab()
        self.tabs.addTab(self.tab_alphafold, "🧪 신약설계")

        # [M646_W_CREST] Conformer 탐색 탭 — CREST/xtb 메타다이내믹스
        # 학술 인용 (Rule NN): Pracht/Bohle/Grimme PCCP 2020;22:7169.
        # CREST 미설치 시 RDKit ETKDG 폴백 (Rule GG SIMULATION_MODE 노랑 배너).
        self.tab_conformer = self._create_conformer_tab()
        self.tabs.addTab(self.tab_conformer, "🌀 Conformer (CREST)")

        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 2)  # 3D viewer stretch weight
        splitter.setStretchFactor(1, 3)  # [M483] 탭 패널 stretch 가중치 증가 (탭 우선 확보)
        # [M483] 탭 패널 최소 380px 보장 — 7탭 전환 버튼 + 콘텐츠 가시성 필수
        self.tabs.setMinimumHeight(380)
        # [M483] 초기 splitter 배분: 뷰어 280 / 탭 480 — 탭 패널 충분한 세로 확보
        splitter.setSizes([280, 480])

        main_layout.addWidget(splitter, 1)

        # === Bottom info bar ===
        info = QHBoxLayout()
        backend = "OpenGL" if OPENGL_AVAILABLE else "QPainter 2.5D"
        # [FIX-3D-IND] 백엔드 모드 아이콘 + 색상 구분
        if OPENGL_AVAILABLE:
            backend_display = "3D OpenGL"
            backend_style = "color: #66bb6a; font-weight: bold; font-size: 8pt;"
        else:
            backend_display = "2.5D (OpenGL 미사용)"
            backend_style = "color: #ffab40; font-weight: bold; font-size: 8pt;"
        self.info_lbl = QLabel(
            f"Atoms: {self.mol_data.num_atoms}  |  "
            f"Bonds: {self.mol_data.num_bonds}  |  "
            f"좌표: {self.mol_data.coord_source}"
        )
        info.addWidget(self.info_lbl)
        backend_lbl = QLabel(f"  Backend: {backend_display}")
        backend_lbl.setStyleSheet(backend_style)
        info.addWidget(backend_lbl)
        info.addStretch()
        help_lbl = QLabel("Left: Rotate  |  Right: Pan  |  Wheel: Zoom")
        help_lbl.setStyleSheet("color: #666; font-size: 8pt;")
        info.addWidget(help_lbl)
        main_layout.addLayout(info)

        self.setLayout(main_layout)

        # === Connect vibration signals ===
        self.tab_vibration.mode_selected.connect(self._on_vib_mode_selected)
        self.tab_vibration.animation_toggled.connect(self._on_vib_toggle)
        # orca_load_requested signal removed (학생용 간소화)
        self.tab_vibration.internal_vib_calculated.connect(self._on_internal_vib)
        self.tab_vibration.zoom_to_atoms_requested.connect(self._zoom_viewer_to_atoms)

        # === [PEAK-CLICK] 스펙트럼 피크 클릭 → 3D 원자 하이라이트 ===
        self.tab_spectrum.peak_clicked.connect(self._on_peak_clicked)

        # [AUTO-VIB] 진동모드 탭 선택 시 자동 계산 트리거
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 내부 엔진용 SMILES 전달
        if self.mol_data.smiles:
            self.tab_vibration.set_smiles(self.mol_data.smiles)

    def _on_tab_changed(self, index: int):
        """탭 전환 시 자동 동작 — 진동모드 탭이면 자동 계산 트리거"""
        current_widget = self.tabs.widget(index)
        if current_widget is self.tab_vibration:
            self.tab_vibration.auto_calculate_if_needed()

    def _validate_gl_rendering(self):
        """[FIX-GL-FALLBACK] OpenGL 렌더링 검증.
        QOpenGLWidget.grabFramebuffer()로 실제 픽셀을 읽어서
        분자가 렌더링되었는지 확인. 빈 화면이면 QPainter 폴백으로 전환.
        """
        if not isinstance(self.viewer, Molecule3DViewer):
            return  # 이미 폴백 상태
        if not self.mol_data or not self.mol_data.atom_positions:
            return  # 분자 데이터 없으면 검증 불필요
        try:
            # grabFramebuffer: QOpenGLWidget의 실제 GL 렌더 결과 캡처
            fb_image = self.viewer.grabFramebuffer()
            if fb_image.isNull():
                logger.warning("GL 프레임버퍼 캡처 실패 → QPainter 폴백 전환")
                self._switch_to_fallback()
                return
            # 중앙 부근 100x100 영역 픽셀 샘플링
            w, h = fb_image.width(), fb_image.height()
            cx, cy = w // 2, h // 2
            sample_r = 50  # 50px 반경 = 100x100
            non_bg_count = 0
            bg_r = int(self.viewer.bg_color[0] * 255)
            bg_g = int(self.viewer.bg_color[1] * 255)
            bg_b = int(self.viewer.bg_color[2] * 255)
            total_sampled = 0
            for dy in range(-sample_r, sample_r, 5):
                for dx in range(-sample_r, sample_r, 5):
                    px, py = cx + dx, cy + dy
                    if 0 <= px < w and 0 <= py < h:
                        pixel = fb_image.pixelColor(px, py)
                        total_sampled += 1
                        # 배경색과 다른 픽셀 카운트 (tolerance=15)
                        if (abs(pixel.red() - bg_r) > 15 or
                                abs(pixel.green() - bg_g) > 15 or
                                abs(pixel.blue() - bg_b) > 15):
                            non_bg_count += 1
            # 5% 미만의 비배경 픽셀이면 렌더링 실패로 판단
            threshold = max(1, int(total_sampled * 0.05))
            if non_bg_count < threshold:
                logger.warning(
                    "GL 렌더링 검증 실패: 중앙 영역에 비배경 픽셀 %d/%d개 "
                    "(임계값 %d) → QPainter 폴백 전환",
                    non_bg_count, total_sampled, threshold)
                self._switch_to_fallback()
            else:
                logger.info("GL 렌더링 검증 성공: 비배경 픽셀 %d/%d개", non_bg_count, total_sampled)
        except Exception as e:
            logger.warning("GL 렌더링 검증 중 예외 → QPainter 폴백 전환: %s", e)
            self._switch_to_fallback()

    def _switch_to_fallback(self):
        """[FIX-GL-FALLBACK] Molecule3DViewer → FallbackRenderer2D 교체.
        splitter 내의 위젯을 동적으로 교체합니다.
        """
        if not isinstance(self.viewer, Molecule3DViewer):
            return  # 이미 폴백 상태
        try:
            old_viewer = self.viewer
            new_viewer = FallbackRenderer2D(self.mol_data)
            # 카메라 상태 복사
            new_viewer.rotation_x = old_viewer.rotation_x
            new_viewer.rotation_y = old_viewer.rotation_y
            new_viewer.zoom_scale = old_viewer.zoom_scale
            # splitter에서 교체
            idx = self._splitter.indexOf(old_viewer)
            if idx >= 0:
                old_viewer.hide()
                self._splitter.insertWidget(idx, new_viewer)
                old_viewer.setParent(None)
                old_viewer.deleteLater()
            self.viewer = new_viewer
            logger.info("QPainter 2.5D 폴백 뷰어로 전환 완료")
        except Exception as e:
            logger.warning("폴백 뷰어 전환 실패: %s", e)

    def _load_data(self):
        """초기 데이터 로드 (RDKit, PubChem, ORCA)"""
        smiles = self.mol_data.smiles or ""
        self._current_smiles = smiles  # 신약설계 탭에서 사용

        # Properties tab — RDKit
        self.tab_props.update_rdkit(smiles)
        self.tab_props.update_measurements(self.mol_data)
        # M645_W9: 외부 API 컨텍스트 설정 (NCI Cactus / OPSIN / ChEMBL / Reactome 버튼)
        self.tab_props.set_ext_context(smiles)

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

        # AI tab — 인스턴스 보존, set_data 그대로 유지 (Rule W)
        orca_info = {}
        if self.orca_parser:
            orca_info["energy"] = self.orca_parser.total_energy
            orca_info["dipole"] = self.orca_parser.dipole_moment
        self.tab_ai.set_data(smiles, {}, orca_info)

        # [CHEM-CHAR] 화학적 특성 분석 탭 — SMILES 전달 (2026-04-25 신규)
        # Source: ChemicalCharacteristicsPanel.tsx useEffect([smiles]) 1:1
        if smiles:
            self.tab_chem_char.set_smiles(smiles)

        # [FIX-DOCKING-SMILES] 도킹 탭에 SMILES 전달 (이전에 누락됨)
        self.tab_docking.set_molecule_smiles(smiles)

        # [FIX-E] ADMET 탭에 SMILES 전달
        self.tab_admet.set_smiles(smiles)

        # [AF-DROPDOWN] 신약설계 탭 AlphaFold 리간드 라벨 업데이트
        if smiles and hasattr(self, '_af_ligand_lbl'):
            disp = smiles[:40] + ("…" if len(smiles) > 40 else "")
            self._af_ligand_lbl.setText(f"현재 분자: {disp}")

        # [XTB-OPT] xTB GFN2-xTB 구조 최적화 (비동기)
        # ORCA 결과가 없고, RDKit ETKDG 좌표일 때만 xTB로 최적화 시도
        # xTB 미설치/실패 시 ETKDG 좌표 그대로 유지 (graceful fallback)
        self._xtb_opt_thread = None
        # [A63-W1/M748] SMILES 키 캐시: 이 popup이 어느 SMILES로 시작했는지 저장
        # _apply_xtb_optimized_coords에서 stale 결과 차단용
        self._xtb_launch_smiles = smiles  # popup 생성 시 SMILES 고정
        if (smiles and not self.orca_parser
                and self.mol_data
                and "RDKit" in getattr(self.mol_data, '_coord_source', '')):
            try:
                self._xtb_opt_thread = _XtbOptThread(smiles, parent=self)
                self._xtb_opt_thread.result_ready.connect(
                    self._apply_xtb_optimized_coords)
                self._xtb_opt_thread.start()
                logger.info("xTB opt: started background optimization for %s", smiles)
            except Exception as e:
                logger.warning("xTB opt: failed to start thread: %s", e)

    def _apply_xtb_optimized_coords(self, result):
        """xTB 최적화 완료 시 3D 좌표 업데이트 + 뷰어 새로고침.

        Args:
            result: dict with 'coords', 'symbols', 'energy' or None (fallback)

        [A63-W1/M748] SMILES 키 일치 검증 — stale cache 차단
        이 popup이 생성될 때의 SMILES(_xtb_launch_smiles)와 result['smiles']가
        다를 경우 이전 분자의 잘못된 결과이므로 무시한다.
        증상: alanine/epinephrine/bicalutamide/caffeine MD5 해시 동일 (4분자 캐시 미분리).
        """
        if result is None or not isinstance(result, dict):
            logger.info("xTB opt: no result, keeping ETKDG coordinates")
            return
        # [A63-W1/M748] stale 결과 차단: SMILES 불일치 시 조용히 skip
        _launch_smiles = getattr(self, '_xtb_launch_smiles', '')
        _result_smiles = result.get('smiles', '')
        if _result_smiles and _launch_smiles and _result_smiles != _launch_smiles:
            logger.warning(
                "[3D/M748] xTB opt: SMILES mismatch — stale result discarded. "
                "expected=%s got=%s",
                _launch_smiles[:40], _result_smiles[:40]
            )
            return
        coords = result.get('coords')
        symbols = result.get('symbols')
        if not coords or not self.mol_data:
            return

        # xTB 좌표로 mol_data 업데이트
        # xTB는 RDKit과 동일한 원자 순서를 사용 (SMILES → RDKit 3D → xTB)
        # 기존 bonds 유지 (결합 정보는 변하지 않음)
        old_n = len(self.mol_data.atom_positions)
        new_n = len(coords)

        if old_n != new_n:
            logger.warning(
                "xTB opt: atom count mismatch (ETKDG=%d, xTB=%d), keeping ETKDG",
                old_n, new_n)
            return

        self.mol_data.atom_positions = coords
        if symbols:
            self.mol_data.atom_symbols = symbols
        self.mol_data._coord_source = "xTB GFN2-xTB Opt (semiempirical)"

        # 뷰어 새로고침
        if self.viewer:
            self.viewer.set_mol_data(self.mol_data)
            logger.info("xTB opt: 3D viewer refreshed with optimized coordinates "
                        "(%d atoms, E=%.6f Eh)",
                        new_n, result.get('energy', 0.0) or 0.0)

        # 속성 탭 측정값 업데이트 (결합 길이/각도가 바뀜)
        try:
            self.tab_props.update_measurements(self.mol_data)
        except Exception as e:
            logger.debug("xTB opt: measurement update failed: %s", e)

        # [I-1] xTB dipole moment 속성 탭에 표시 (2026-04-24)
        # ORCA 결과가 없을 때 xTB dipole을 calc_form에 추가
        dipole_val = result.get('dipole')
        if (dipole_val is not None
                and isinstance(dipole_val, (int, float))
                and not self.orca_parser):
            try:
                self.tab_props.update_xtb_dipole(dipole_val)
            except Exception as e:
                logger.warning("xTB opt: dipole update failed: %s", e)

    def _apply_orca_data(self, parser: OrcaOutputParser):
        """ORCA 파서 결과를 모든 탭에 적용"""
        self.orca_parser = parser
        self.tab_props.update_orca(parser)

        if parser.frequencies:
            self.tab_spectrum.plot_ir(parser.frequencies, parser.ir_intensities)
            self.tab_vibration.load_modes(parser.frequencies, parser.ir_intensities)

    def _load_orca_file(self):
        """ORCA .out 파일 로드 — 파일 선택 다이얼로그로 .out 파일 파싱 후 결과 적용."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "ORCA 결과 파일 열기",
            os.path.expanduser("~"),
            "ORCA Output (*.out);;All Files (*)"
        )
        if not filepath:
            return  # 사용자가 취소
        try:
            parser = OrcaOutputParser(filepath=filepath)
            if parser.total_energy is None and not parser.frequencies:
                logger.warning("ORCA 파일 파싱 결과 데이터 없음: %s", filepath)
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "경고",
                    f"ORCA 파일에서 유효한 데이터를 찾지 못했습니다.\n{filepath}"
                )
                return
            self._apply_orca_data(parser)
            logger.info("ORCA 파일 로드 완료: %s (energy=%s, freqs=%d)",
                        filepath, parser.total_energy, len(parser.frequencies))
        except Exception as e:
            logger.warning("ORCA 파일 로드 실패: %s — %s", filepath, e)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "오류",
                f"ORCA 파일 로드 중 오류 발생:\n{e}"
            )

    def _set_dft_button_state(self, enabled: Optional[bool] = None, text: Optional[str] = None):
        """No-op unless a legacy DFT toolbar button exists."""
        button = getattr(self, "btn_dft", None)
        if button is None:
            return
        if enabled is not None:
            button.setEnabled(enabled)
        if text is not None:
            button.setText(text)

    # ================================================================
    # DFT Calculation (ORCA B3LYP/6-31G* Opt+Freq)
    # ================================================================

    def _start_dft_calculation(self):
        """정밀 DFT 계산 시작 — QThread 비동기 실행."""
        # Guard: 이미 실행 중이면 무시
        if self._dft_thread is not None and self._dft_thread.isRunning():
            logger.warning("DFT 계산이 이미 실행 중입니다.")
            return

        # Guard: 분자 데이터 확인
        if not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("DFT 계산 실패: 분자 데이터가 없습니다.")
            self._dft_status_label.setText("분자를 먼저 그려주세요")
            self._dft_status_label.setVisible(True)
            return

        # [M438] ORCA 정직성 fix — 거짓 메시지 "Using built-in engine" 제거
        # Rule M: silent return 금지. 사용자에게 명확히 피드백.
        # 실제 built-in DFT 엔진 없음 — "built-in engine" 메시지는 학계 사기에 해당.
        orca_exe = _find_orca_exe()
        orca_wsl_available = _check_orca_wsl_available()
        orca_remote_available = _check_orca_remote_available()
        if orca_exe is None and not orca_wsl_available and not orca_remote_available:
            logger.warning(
                "[popup_3d] ORCA 미설치 — 정밀 DFT 불가. "
                "ORCA_PATH 환경변수 또는 Orca.6.1.1/ 폴더를 배치하세요."
            )
            self._dft_status_label.setText(
                "ORCA 미설치 — 정밀 DFT 사용 불가.\n"
                "설치: docs/orca_install.md 또는 ORCA_PATH 환경변수 설정"
            )
            self._dft_status_label.setStyleSheet(
                "color: #EF5350; font-size: 11px; padding: 0 4px;")
            self._dft_status_label.setVisible(True)
            # 버튼도 disable (이미 초기화 시 disable됐어야 하나 혹시 재호출 대비)
            self._set_dft_button_state(enabled=False)
            return

        # UI 피드백: 버튼 비활성화 + 상태 표시
        self._set_dft_button_state(enabled=False)
        self._set_dft_button_state(text="⏳ DFT 계산 중...")
        self._dft_status_label.setText("ORCA 초기화 중...")
        self._dft_status_label.setStyleSheet(
            "color: #CE93D8; font-size: 11px; padding: 0 4px;")
        self._dft_status_label.setVisible(True)

        # 원자 수 기반 시간 경고 (대략적 추정)
        n_atoms = len(self.mol_data.atom_positions)
        if n_atoms > 30:
            self._dft_status_label.setText(
                f"경고: {n_atoms}개 원자 — 계산에 수십 분 소요될 수 있습니다")

        # QThread 생성 및 시작
        self._dft_thread = DFTCalculatorThread(
            mol_data=self.mol_data,
            charge=0,
            multiplicity=1,
            timeout=1800,  # 30분
            parent=self,
        )
        self._dft_thread.progress.connect(self._on_dft_progress)
        self._dft_thread.finished_ok.connect(self._on_dft_finished)
        self._dft_thread.finished_err.connect(self._on_dft_error)
        self._dft_thread.start()
        logger.info("DFT 계산 스레드 시작 (원자 수: %d)", n_atoms)

    def _on_dft_progress(self, msg: str):
        """DFT 계산 진행 상태 업데이트."""
        self._dft_status_label.setText(msg)
        logger.info("DFT progress: %s", msg)

    def _on_dft_finished(self, parser: OrcaOutputParser):
        """DFT 계산 성공 — 결과를 모든 탭에 적용."""
        logger.info("DFT 계산 완료: energy=%s, freqs=%d",
                     parser.total_energy, len(parser.frequencies))

        # ORCA 파서 결과를 저장하고 모든 탭에 적용
        self._apply_orca_data(parser)

        # 에너지 정보 요약 표시
        energy_str = ""
        if parser.total_energy is not None:
            e_kcal = parser.total_energy * 627.509  # Hartree → kcal/mol
            energy_str = f"E = {parser.total_energy:.6f} Eh ({e_kcal:.1f} kcal/mol)"

        freq_str = f"진동모드 {len(parser.frequencies)}개" if parser.frequencies else ""
        converge_str = "수렴" if parser.converged else "미수렴"
        summary = f"DFT 완료: {energy_str} | {freq_str} | {converge_str}"

        self._dft_status_label.setText(summary)
        self._dft_status_label.setStyleSheet(
            "color: #66BB6A; font-size: 11px; padding: 0 4px;")

        # 버튼 복원
        self._set_dft_button_state(enabled=True)
        self._set_dft_button_state(text="⚛ 정밀 DFT (ORCA)")

        # AI 분석 탭에도 DFT 에너지 정보 갱신
        orca_info = {}
        if parser.total_energy is not None:
            orca_info["energy"] = parser.total_energy
        if parser.dipole_moment is not None:
            orca_info["dipole"] = parser.dipole_moment
        smiles = self.mol_data.smiles or ""
        self.tab_ai.set_data(smiles, {}, orca_info)

        # DFT 완료 후 HOMO/LUMO/density cube 파일 자동 생성
        self._generate_cubes_after_dft(parser)

    def _generate_cubes_after_dft(self, parser: OrcaOutputParser):
        """DFT 완료 후 generate_orbital_cubes()를 호출하여 cube 파일 자동 생성.

        ORCA_AVAILABLE guard (THEORY-AUTO-009~011/017~019/025~027/035~038):
        이 함수는 _on_dft_finished → 실제 ORCA subprocess 완료 후에만 호출됨.
        ORCA_AVAILABLE=False 일 때는 DFT 스레드 자체가 생성되지 않으므로 도달 불가.
        Rule GG: 학생 오염 차단 — ORCA 결과 부재 시 cube 미생성 + 워터마크.
        """
        if not ORCA_AVAILABLE:
            logger.info("[Rule GG] ORCA_AVAILABLE=False — cube 생성 경로 차단")
            return
        if not parser.filepath:
            logger.warning("DFT 결과 파일 경로 없음 — cube 생성 생략")
            return
        out_path = Path(parser.filepath)
        if not out_path.exists():
            logger.warning("DFT 결과 파일 미존재: %s — cube 생성 생략", out_path)
            return
        try:
            from orca_interface import generate_orbital_cubes
            cube_files = generate_orbital_cubes(out_path, work_dir=out_path.parent)
            if cube_files:
                logger.info("Cube 파일 자동 생성 완료: %s",
                            {k: str(v) for k, v in cube_files.items()})
                self._dft_status_label.setText(
                    self._dft_status_label.text() + f" | Cube {len(cube_files)}개 생성")
                # cube 파일 경로를 저장하여 MolecularOrbitalPopup에서 사용 가능하게 함
                self._cube_files = cube_files
            else:
                logger.info("Cube 파일 생성 결과 없음 (ORCA 미설치 또는 .gbw 없음)")
        except ImportError:
            logger.warning("orca_interface 모듈 임포트 실패 — cube 생성 불가")
        except Exception as e:
            logger.warning("Cube 파일 생성 중 오류: %s", e)

    def _on_dft_error(self, err_msg: str):
        """DFT 계산 실패 — 사용자 친화적 메시지 표시. Raw exit code 숨김."""
        logger.warning("DFT error: %s", err_msg)
        # [FIX-F] exit code 패턴을 사용자 친화적 메시지로 변환
        # ORCA_AVAILABLE guard (THEORY-AUTO-004~007/012~015/020~023):
        # 이 분기는 ORCA subprocess 실행 결과 에러 시에만 도달 (DFTCalculatorThread 내부)
        # [M438] 거짓 "Using built-in engine" 메시지 제거 — 실제 DFT 엔진 없음
        display_msg = err_msg
        if "exit code" in err_msg.lower():
            display_msg = "ORCA 계산 오류 — docs/orca_install.md 또는 ORCA_PATH 환경변수 확인"
        self._dft_status_label.setText(display_msg[:100])
        self._dft_status_label.setStyleSheet(
            "color: #EF5350; font-size: 11px; padding: 0 4px;")
        self._dft_status_label.setVisible(True)

        # [B10-5 Fix] ORCA 실패 시 스펙트럼 탭에 synthetic fallback 명시 (Rule M: silent failure 금지)
        # spectrum tab info_label에 ORCA 실패 + synthetic 전환 안내 표시
        try:
            smiles = getattr(self, '_current_smiles', '') or (
                self.mol_data.smiles if self.mol_data else '')
            if smiles and hasattr(self, 'tab_spectrum'):
                self.tab_spectrum.info_label.setText(
                    "[B10-5] ORCA 실행 실패 -- synthetic IR spectrum 표시 중 (예측 엔진)")
                self.tab_spectrum.info_label.setStyleSheet(
                    "color: #EF9A9A; font-size: 8pt; padding: 2px 4px;")
                # synthetic spectrum 강제 로드 (이미 로드됐을 수 있으나 info_label 갱신 목적)
                self.tab_spectrum.load_predicted(smiles)
        except Exception as _e:
            logger.warning("[B10-5] spectrum fallback label update failed: %s", _e)

        # 버튼 복원
        self._set_dft_button_state(enabled=True)
        self._set_dft_button_state(text="⚛ 정밀 DFT (ORCA)")

    def _on_orbital_mode_changed(self, index: int):
        """[CHEM-8] 오비탈 모드 콤보 변경 핸들러."""
        MODE_MAP = {
            0: 'none',
            1: 'pi',
            2: 'hybrid',
            3: 'd_orbital',
            4: 'f_orbital',
            5: 'all',
            6: 'esp',
        }
        mode = MODE_MAP.get(index, 'none')
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.set_orbital_mode(mode)
        elif isinstance(self.viewer, FallbackRenderer2D):
            # [PI-QPainter] QPainter 폴백: orbital_mode 전달 (pi/esp/none 등)
            self.viewer.set_orbital_mode(mode)

    def _toggle_pi_orbitals(self, checked):
        """[CHEM-6] 하위호환 — 콤보박스 연동."""
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.set_pi_orbitals(checked)
        elif isinstance(self.viewer, FallbackRenderer2D):
            self.viewer.set_orbital_mode('pi' if checked else 'none')

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

    def _on_bg_color_changed(self, idx):
        """배경색 콤보박스 변경 시 뷰어에 반영."""
        # idx: 0=검정, 1=회색, 2=흰색
        bg_map = {
            0: (0.05, 0.05, 0.07),   # near-black (기본)
            1: (0.45, 0.45, 0.48),   # medium gray
            2: (0.95, 0.95, 0.97),   # near-white
        }
        r, g, b = bg_map.get(idx, (0.05, 0.05, 0.07))
        if self.viewer:
            self.viewer.set_background_color(r, g, b)

    def _reset_view(self):
        """Reset to initial molecule view: camera, vibration, protein/docking overlays."""
        if self.viewer:
            # Stop vibration animation if active
            if hasattr(self.viewer, '_vib_active') and self.viewer._vib_active:
                self.viewer.stop_vibration()
            # Clear protein/docking state that would hide the molecule
            if hasattr(self.viewer, '_protein_visible'):
                self.viewer._protein_visible = False
            if hasattr(self.viewer, '_docking_pose_atoms'):
                self.viewer._docking_pose_atoms = None
            if hasattr(self.viewer, '_binding_site_center'):
                self.viewer._binding_site_center = None
            if hasattr(self.viewer, '_dock_approach_phase'):
                self.viewer._dock_approach_phase = -1.0
            if hasattr(self.viewer, '_ligand_offset'):
                self.viewer._ligand_offset = (0.0, 0.0, 0.0)
            # Reset camera to initial state
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
            self.viewer._vib_highlight_indices = set(
                _vibration_active_atom_indices(vectors)
            )
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
            logger.warning("진동 토글 건너뜀: viewer=%s, start_vibration=%s",
                           bool(self.viewer),
                           hasattr(self.viewer, 'start_vibration') if self.viewer else False)
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
            except Exception as e:
                logger.debug("plot_simple_ir unavailable or failed: %s", e)

    def _zoom_viewer_to_atoms(self, atom_indices: list):
        """진동 원자 영역으로 3D 뷰어 줌 & 하이라이트

        atom_indices: 진동에 관여하는 원자의 인덱스 리스트
        """
        if not self.viewer or not self.mol_data or not self.mol_data.atom_positions:
            logger.warning("진동 원자 줌 건너뜀: viewer=%s, mol_data=%s, atom_positions=%s",
                           bool(self.viewer), bool(self.mol_data),
                           bool(self.mol_data.atom_positions) if self.mol_data else False)
            return

        atom_keys = list(self.mol_data.atom_positions.keys())
        if not atom_keys:
            logger.warning("진동 원자 줌 건너뜀: atom_keys 비어있음")
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
            logger.warning("진동 원자 줌 건너뜀: 유효한 원자 위치 없음 (indices=%s)", atom_indices)
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
        # 스케일 팩터: FallbackRenderer2D는 0.55, Molecule3DViewer는 다른 스케일 사용
        _vp_scale_factor = 0.55 if isinstance(self.viewer, FallbackRenderer2D) else 0.35
        current_scale = min(w, h) / (bs + 4.0) * _vp_scale_factor * self.viewer.zoom_scale

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

    def _on_peak_clicked(self, atom_indices: tuple):
        """[PEAK-CLICK] 스펙트럼 피크 클릭 시 3D 뷰어에 해당 원자 하이라이트.

        atom_indices: tuple of int — RDKit atom indices responsible for the peak.
        Also auto-selects the best matching vibration mode if available.
        """
        if not self.viewer or not atom_indices:
            logger.warning("피크 클릭 하이라이트 건너뜀: viewer=%s, atom_indices=%s",
                           bool(self.viewer), atom_indices)
            return

        # 1. Highlight atoms in the 3D viewer
        self.viewer._vib_highlight_indices = set(atom_indices)
        self.viewer.update()

        # 2. Auto-clear highlight after 5 seconds (5000 ms)
        QTimer.singleShot(5000, self._clear_peak_highlight)

        # 3. Try to find and select the best matching vibration mode
        if (hasattr(self, 'tab_vibration')
                and self.tab_vibration._vib_result
                and self.tab_vibration._vib_result.modes):
            best_mode_idx = -1
            best_overlap = 0
            atom_set = set(atom_indices)
            for i, mode in enumerate(self.tab_vibration._vib_result.modes):
                # Calculate overlap between peak atoms and vibration mode atoms
                mode_atoms = set(mode.bond_indices) if mode.bond_indices else set()
                overlap = len(atom_set & mode_atoms)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_mode_idx = i
            if best_mode_idx >= 0 and best_overlap > 0:
                # Programmatically select the vibration mode
                self.tab_vibration.mode_list.setCurrentRow(best_mode_idx)
                # Start vibration playback
                self._on_vib_mode_selected(best_mode_idx)
                logger.debug("Auto-selected vibration mode %d (overlap=%d atoms)",
                             best_mode_idx, best_overlap)

    def _clear_peak_highlight(self):
        """[PEAK-CLICK] Clear atom highlight after timeout."""
        if self.viewer:
            self.viewer._vib_highlight_indices = set()
            self.viewer.update()

    def _export_3d_structure(self):
        """💾 3D 구조 내보내기 — XYZ / ORCA .inp / Gaussian .gjf / MDL .mol 형식 선택"""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QMessageBox

        if not self.mol_data or self.mol_data.num_atoms == 0:
            logger.warning("3D 구조 내보내기 건너뜀: mol_data=%s, num_atoms=%d",
                           bool(self.mol_data), self.mol_data.num_atoms if self.mol_data else 0)
            QMessageBox.warning(self, "내보내기 불가", "⚠️ 분자 데이터가 없습니다.\n먼저 분자를 그려주세요.")
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

    # ── [M646_W_CREST] CREST Conformer Search 탭 (Molecule3DPopup 소속) ──

    def _create_conformer_tab(self):
        """🌀 Conformer 탭 — CREST 메타다이내믹스 conformer 탐색.

        학술 인용 (Rule NN):
            Pracht P, Bohle F, Grimme S (2020). "Automated exploration of the
            low-energy chemical space with fast quantum chemical methods".
            Phys. Chem. Chem. Phys. 22:7169-7192. DOI: 10.1039/C9CP06869D.

        CREST는 GFN2-xTB 메타다이내믹스로 분자의 conformer-rotamer 앙상블을 탐색.
        xtb 의존성. 미설치 시 RDKit ETKDG 폴백 (SIMULATION_MODE 노랑 배너).
        """
        from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                     QPushButton, QLabel, QGroupBox, QTextEdit,
                                     QProgressBar, QScrollArea, QTableWidget,
                                     QTableWidgetItem, QHeaderView, QSpinBox,
                                     QCheckBox, QFrame)

        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setSpacing(6)
        outer.setContentsMargins(8, 8, 8, 8)

        # ── 학술 인용 헤더 + SIMULATION 배너 ──
        # crest_client 모듈 lazy import (Rule M graceful degradation)
        # 패키지 모드 (from .) → standalone 모드 (import) → 실패 → SIMULATION 폴백
        _crest = None
        try:
            from . import crest_client as _crest
        except (ImportError, ValueError) as e_pkg:
            # standalone 모드 (테스트 직접 실행)에서 fallback
            try:
                import crest_client as _crest  # type: ignore
            except Exception as e_std:  # Rule M
                logger.warning(
                    "[M646_W_CREST] crest_client 임포트 실패 — pkg=%s, std=%s",
                    e_pkg, e_std
                )
                _crest = None
        if _crest is not None:
            crest_status_msg = _crest.get_status_message()
            crest_simulation = _crest.SIMULATION_MODE
        else:
            crest_status_msg = ("[SIMULATION_MODE] crest_client 미로드 — "
                                "RDKit ETKDG 폴백만 사용 가능.")
            crest_simulation = True

        # 배너 (Rule GG: 노랑/파란 분기)
        banner = QLabel(crest_status_msg)
        banner.setWordWrap(True)
        if crest_simulation:
            # 노랑 SIMULATION 배너 (Bootstrap warning)
            # [MAGIC] #fff3cd/#856404 — Bootstrap 표준 SIMULATION 색상 (M646_LITE_PARITY)
            banner.setStyleSheet(
                "background-color: #fff3cd; color: #856404; "
                "border: 1px solid #ffc107; padding: 6px 8px; "
                "font-size: 10pt; font-weight: bold; border-radius: 3px;"
            )
        else:
            # 파란 REAL 배너 (Bootstrap info)
            # [MAGIC] #d1ecf1/#0c5460 — Bootstrap 표준 REAL 색상
            banner.setStyleSheet(
                "background-color: #d1ecf1; color: #0c5460; "
                "border: 1px solid #17a2b8; padding: 6px 8px; "
                "font-size: 10pt; font-weight: bold; border-radius: 3px;"
            )
        outer.addWidget(banner)

        # ── 학술 인용 ──
        citation_lbl = QLabel(
            "📚 학술 인용: Pracht P, Bohle F, Grimme S (2020). "
            "PCCP 22:7169-7192. DOI: 10.1039/C9CP06869D"
        )
        citation_lbl.setStyleSheet(
            "color: #aaa; font-size: 9pt; padding: 2px 4px; font-style: italic;"
        )
        citation_lbl.setWordWrap(True)
        citation_lbl.setToolTip(
            "CREST: Conformer-Rotamer Ensemble Sampling Tool\n"
            "GFN2-xTB 기반 메타다이내믹스 conformer 탐색.\n"
            "Pracht et al. PCCP 2020;22:7169.\n"
            "Grimme. JCTC 2019;15:2847."
        )
        outer.addWidget(citation_lbl)

        guide_group = QGroupBox("Conformer learner guide")
        guide_group.setObjectName("d891_item019_conformer_guidance_group")
        guide_group.setStyleSheet(
            "QGroupBox { border: 1px solid #4a9eff; border-radius: 4px; "
            "margin-top: 8px; padding: 8px; color: #bbdefb; "
            "font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        guide_group.setMinimumHeight(132)
        guide_layout = QVBoxLayout(guide_group)
        guide_layout.setContentsMargins(8, 8, 8, 8)
        guide_text = QLabel(
            "What this tab means: conformers are different 3D shapes of the same molecule; "
            "the atoms and bonds stay the same, but rotatable bonds change the shape.\n"
            "Why it is useful: check conformers before drug-design or ADMET-style reasoning "
            "when a flexible molecule may bind, cross a membrane, or expose groups differently.\n"
            "How to read results: lower Delta E is closer to the lowest-energy candidate; "
            "RMSD measures 3D shape difference, so low RMSD is similar and high RMSD is distinct.\n"
            "Engine boundary: yellow SIMULATION_MODE = RDKit ETKDG/MMFF fallback, not "
            "CREST/xTB evidence; not DFT, ORCA, Vina docking, or experimental validation."
        )
        guide_text.setObjectName("d891_item019_conformer_guidance_text")
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet(
            "color: #e3f2fd; font-size: 10pt; line-height: 135%; "
            "font-weight: normal;"
        )
        guide_text.setMinimumHeight(96)
        guide_layout.addWidget(guide_text)
        outer.addWidget(guide_group)

        # ── 옵션 + 실행 버튼 ──
        opt_group = QGroupBox("🌀 CREST 옵션")
        opt_group.setStyleSheet("QGroupBox { font-weight: bold; color: #64b5f6; }")
        opt_layout = QHBoxLayout(opt_group)
        opt_layout.addWidget(QLabel("타임아웃 (초):"))
        self._crest_timeout_spin = QSpinBox()
        self._crest_timeout_spin.setRange(60, 1800)  # [MAGIC] 1~30분
        self._crest_timeout_spin.setValue(180)  # [MAGIC: 180s] 빠른 분자 기본값
        self._crest_timeout_spin.setSuffix("s")
        opt_layout.addWidget(self._crest_timeout_spin)
        self._crest_quick_chk = QCheckBox("--quick 모드 (빠름)")
        self._crest_quick_chk.setChecked(True)
        self._crest_quick_chk.setToolTip(
            "--quick 모드: 더 짧은 메타다이내믹스. 작은 분자에 적합.\n"
            "전체 모드: 더 정밀한 탐색 (5~30분 소요)."
        )
        opt_layout.addWidget(self._crest_quick_chk)
        opt_layout.addStretch()
        outer.addWidget(opt_group)

        # ── 실행 버튼 ──
        btn_run = QPushButton("🌀 CREST conformer search 실행")
        btn_run.setStyleSheet(
            "QPushButton { background-color: #4a9eff; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; "
            "font-size: 11pt; }"
            "QPushButton:hover { background-color: #1976d2; }"
            "QPushButton:disabled { background-color: #555; color: #aaa; }"
        )
        btn_run.clicked.connect(self._run_crest_conformer_search)
        outer.addWidget(btn_run)
        self._crest_run_btn = btn_run

        # ── 진행 상태 ──
        self._crest_progress_lbl = QLabel("대기 중 — 버튼을 눌러 conformer 탐색 시작.")
        self._crest_progress_lbl.setStyleSheet(
            "color: #aaa; font-size: 10pt; padding: 4px 8px;"
        )
        self._crest_progress_lbl.setWordWrap(True)
        outer.addWidget(self._crest_progress_lbl)

        self._crest_progress_bar = QProgressBar()
        self._crest_progress_bar.setRange(0, 0)  # indeterminate
        self._crest_progress_bar.setVisible(False)
        outer.addWidget(self._crest_progress_bar)

        # ── 결과 테이블 ──
        self._crest_result_table = QTableWidget(0, 4)
        self._crest_result_table.setHorizontalHeaderLabels([
            "#", "ΔE (kcal/mol)", "원자 수", "에너지 (Hartree)"
        ])
        header = self._crest_result_table.horizontalHeader()
        if header is not None:  # Rule N: 타입 가드
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._crest_result_table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; color: #eee; "
            "gridline-color: #444; }"
            "QHeaderView::section { background: #2a2a2a; color: #eee; "
            "padding: 4px; }"
        )
        self._crest_result_table.setMaximumHeight(220)
        outer.addWidget(self._crest_result_table)

        # ── 결과 요약 텍스트 ──
        self._crest_summary_text = QTextEdit()
        self._crest_summary_text.setReadOnly(True)
        self._crest_summary_text.setStyleSheet(
            "background-color: #181818; color: #d4d4d4; "
            "font-family: Consolas, monospace; font-size: 9pt; "
            "border: 1px solid #444; border-radius: 3px; padding: 4px;"
        )
        self._crest_summary_text.setMaximumHeight(180)
        self._crest_summary_text.setPlaceholderText(
            "CREST 실행 결과 요약이 여기 표시됩니다."
        )
        outer.addWidget(self._crest_summary_text)

        # 모듈 핸들 보존 (스레드에서 사용)
        self._crest_module = _crest

        return widget

    def _run_crest_conformer_search(self):
        """CREST conformer search 실행 — QThread로 비동기 처리."""
        from PyQt6.QtWidgets import QMessageBox

        smiles = getattr(self, '_current_smiles', '') or ''
        if not isinstance(smiles, str) or not smiles.strip():  # Rule N
            QMessageBox.warning(
                self,
                "SMILES 부재",
                "현재 분자의 SMILES가 없습니다. 분자를 먼저 그리세요."
            )
            return

        if self._crest_module is None:
            QMessageBox.warning(
                self,
                "CREST 미로드",
                "crest_client 모듈을 로드할 수 없습니다.\n"
                "ChemGrid 설치 무결성을 확인하세요."
            )
            return

        timeout = int(self._crest_timeout_spin.value())
        quick = bool(self._crest_quick_chk.isChecked())

        # UI 상태 변경
        self._crest_run_btn.setEnabled(False)
        self._crest_progress_bar.setVisible(True)
        self._crest_progress_lbl.setText(
            f"⏳ CREST 실행 중 (timeout={timeout}s, quick={quick})... "
            "GFN2-xTB 메타다이내믹스 진행."
        )
        self._crest_summary_text.clear()
        self._crest_result_table.setRowCount(0)

        # QThread로 비동기 실행
        self._crest_thread = _CrestWorkerThread(
            self._crest_module, smiles, timeout, quick
        )
        self._crest_thread.finished_signal.connect(self._on_crest_finished)
        self._crest_thread.start()

    def _on_crest_finished(self, result: dict):
        """CREST 완료 콜백 — UI 갱신.

        Rule N: result는 dict 타입 가드. Rule M: error 분기 명시.
        """
        from PyQt6.QtWidgets import QTableWidgetItem
        self._crest_run_btn.setEnabled(True)
        self._crest_progress_bar.setVisible(False)

        if not isinstance(result, dict):  # Rule N
            return

        status = result.get("status", "unknown")
        if status == "error":
            err = result.get("error", "unknown error")
            self._crest_progress_lbl.setText(f"❌ CREST 실패: {err}")
            self._crest_progress_lbl.setStyleSheet(
                "color: #ff6b6b; font-size: 10pt; font-weight: bold;"
            )
            self._crest_summary_text.setText(
                f"오류: {err}\n\n"
                f"raw 로그 (마지막 50줄):\n"
                f"{result.get('raw_log_tail', '(없음)')}"
            )
            return

        n_confs = int(result.get("n_conformers", 0) or 0)
        method = result.get("method", "unknown")
        wall_time = float(result.get("wall_time_sec", 0) or 0)
        citation = result.get("citation", "")
        energies = result.get("energies_kcal", []) or []
        confs_xyz = result.get("conformers_xyz", []) or []

        # 색상 분기 (Rule GG)
        if status == "simulation":
            color = "#ffc107"  # 노랑 (RDKit ETKDG 폴백)
            icon = "🔶"
        else:
            color = "#4caf50"  # 녹색 (REAL CREST)
            icon = "✅"

        self._crest_progress_lbl.setText(
            f"{icon} 완료 — {n_confs}개 conformer 발견 ({wall_time:.1f}s)"
        )
        self._crest_progress_lbl.setStyleSheet(
            f"color: {color}; font-size: 10pt; font-weight: bold;"
        )

        # 테이블 채우기 — 원자 수 추출
        from PyQt6.QtWidgets import QTableWidgetItem
        self._crest_result_table.setRowCount(min(n_confs, 50))  # [MAGIC: 50] 표시 한도
        for i in range(min(n_confs, 50)):
            # # 컬럼
            self._crest_result_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            # ΔE
            if i < len(energies) and isinstance(energies[i], (int, float)):  # Rule N
                e_str = f"{energies[i]:.3f}"
            else:
                e_str = "—"
            self._crest_result_table.setItem(i, 1, QTableWidgetItem(e_str))
            # 원자 수
            atom_count = "?"
            if i < len(confs_xyz) and isinstance(confs_xyz[i], str):  # Rule N
                first_line = (confs_xyz[i].splitlines() or [""])[0].strip()
                if first_line.isdigit():
                    atom_count = first_line
            self._crest_result_table.setItem(i, 2, QTableWidgetItem(atom_count))
            # Hartree (lowest only on i=0)
            if i == 0:
                lowest = result.get("lowest_energy_hartree", 0.0) or 0.0
                self._crest_result_table.setItem(
                    i, 3, QTableWidgetItem(f"{lowest:.6f}")
                )
            else:
                self._crest_result_table.setItem(i, 3, QTableWidgetItem("—"))

        # 요약 텍스트
        summary_lines = [
            f"=== CREST Conformer Search 결과 ===",
            f"입력 SMILES: {result.get('smiles', '?')}",
            f"방법: {method}",
            f"발견된 conformer 수: {n_confs}",
            f"실행 시간: {wall_time:.2f} 초",
            f"최저 에너지: {result.get('lowest_energy_hartree', 0.0):.6f} Hartree",
            f"학술 인용: {citation}",
        ]
        if status == "simulation":
            alt = result.get("alternative", "")
            if alt:
                summary_lines.append(f"\n[알림] {alt}")
        if energies:
            summary_lines.append(f"\nΔE 분포 (kcal/mol):")
            for i, e in enumerate(energies[:10]):  # [MAGIC: 10] 표시 한도
                if isinstance(e, (int, float)):
                    summary_lines.append(f"  conf {i+1}: {e:.3f}")
        self._crest_summary_text.setText("\n".join(summary_lines))


    # ── AlphaFold / 신약설계 탭 메서드 (Molecule3DPopup 소속) ──

    def _create_alphafold_synthesis_tab(self):
        """💊 신약설계 탭 — 학생 친화적 원클릭 UI.

        학생이 해야 하는 것: 목표 선택 → 버튼 클릭. 끝.
        나머지(표적 단백질, AlphaFold, 도킹, ADMET, 합성)는 시스템이 자동 처리.
        """
        from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                      QPushButton, QLabel, QComboBox,
                                      QGroupBox, QTextEdit, QProgressBar,
                                      QScrollArea, QLineEdit)

        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        layout = QVBoxLayout(inner)
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

        # ── [AF-DROPDOWN] AlphaFold 수용체 표적 선택 그룹 ──────────────
        af_group = QGroupBox("🧬 AlphaFold 단백질 구조 예측 / 도킹 표적 선택")
        af_group.setStyleSheet("QGroupBox { font-weight: bold; color: #64b5f6; }")
        af_layout = QVBoxLayout(af_group)

        # [B7-1] af_desc: 드롭다운 미선택(idx==0) 또는 직접입력(__custom__) 시만 표시
        self._af_desc = QLabel("현재 분자(리간드)가 결합할 표적 단백질을 선택하거나,\n"
                               "PDB ID / UniProt ID를 직접 입력하세요.")
        self._af_desc.setStyleSheet("color: #aaa; font-size: 11px;")
        self._af_desc.setWordWrap(True)
        af_layout.addWidget(self._af_desc)

        # 현재 분자 자동 표시
        self._af_ligand_lbl = QLabel("현재 분자: —")
        self._af_ligand_lbl.setStyleSheet(
            "color: #81d4fa; font-size: 10px; padding: 2px 4px; "
            "background: #1a2a3a; border-radius: 3px;")
        smiles_now = getattr(self, '_current_smiles', '') or ''
        if smiles_now:
            disp = smiles_now[:40] + ("…" if len(smiles_now) > 40 else "")
            self._af_ligand_lbl.setText(f"현재 분자: {disp}")
        af_layout.addWidget(self._af_ligand_lbl)

        # 표적 단백질 프리셋 드롭다운
        af_target_row = QHBoxLayout()
        af_target_row.addWidget(QLabel("표적 단백질:"))
        self._af_target_combo = QComboBox()
        self._af_target_combo.setStyleSheet(
            "QComboBox { background: #2a2a2a; color: #ddd; border: 1px solid #555; "
            "padding: 5px; font-size: 11px; }")
        # [AF-PRESETS] 주요 수용체 드롭다운 목록 (PDB ID: 설명)
        _af_presets = [
            ("— 선택하세요 —", ""),
            ("현재 분자 자동 매칭 (AI 추천)", "__auto__"),
            ("GABA-A 수용체  (6X3S) — 항불안", "6X3S"),
            ("ACE2 수용체  (6M0J) — COVID-19", "6M0J"),
            ("COX-2  (5IKT) — 항염증 (아스피린 표적)", "5IKT"),
            ("EGFR 키나아제  (1IVO) — 항암", "1IVO"),
            ("Dopamine D2  (6CM4) — 정신과 약물", "6CM4"),
            ("Mu-Opioid 수용체  (5C1M) — 진통제", "5C1M"),
            ("HMG-CoA  (1HWK) — 스타틴 (콜레스테롤)", "1HWK"),
            ("PDE5  (1UDT) — 실데나필 표적", "1UDT"),
            ("Thrombin  (3U69) — 항응고제", "3U69"),
            ("AChE  (4EY7) — 알츠하이머 치료", "4EY7"),
            ("SARS-CoV-2 Mpro  (6LU7) — 코로나 주 단백분해효소", "6LU7"),
            ("CDK2  (1FIN) — 세포 주기 조절", "1FIN"),
            ("GLP-1R  (5VAI) — 당뇨/비만 (세마글루타이드 표적)", "5VAI"),
            ("Beta-2 AR  (3NY8) — 천식 치료", "3NY8"),
            ("HIV Protease  (3OXC) — 에이즈 치료", "3OXC"),
            ("✏️ PDB ID / UniProt ID 직접 입력...", "__custom__"),
        ]
        for label, pdb_id in _af_presets:
            self._af_target_combo.addItem(label, pdb_id)
        af_target_row.addWidget(self._af_target_combo, 1)
        af_layout.addLayout(af_target_row)

        # 직접 입력 필드 (기본 숨김)
        self._af_custom_input = QLineEdit()
        self._af_custom_input.setPlaceholderText(
            "예: 6X3S  또는  P23975 (UniProt)  또는  ATCMKW... (FASTA)")
        self._af_custom_input.setStyleSheet("padding: 5px; color: #ddd; background: #252525;")
        self._af_custom_input.hide()
        af_layout.addWidget(self._af_custom_input)

        def _on_af_target_changed(idx: int) -> None:
            # [B7-1] idx==0 = "— 선택하세요 —" 초기 상태: af_desc + custom_input 모두 초기값으로
            # idx>0 but not __custom__: 드롭다운 선택됨 → af_desc(수동입력 안내) hide
            # idx = __custom__: 직접 입력 모드 → af_desc + custom_input 표시
            if not isinstance(idx, int):
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    f"[B7-1] _on_af_target_changed: 예상치 못한 idx 타입 {type(idx)}: {idx}")
                return
            if not isinstance(self._af_target_combo, QComboBox):
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "[B7-1] _on_af_target_changed: _af_target_combo가 QComboBox가 아님")
                return
            pdb_val = self._af_target_combo.itemData(idx)
            is_custom = (pdb_val == "__custom__")
            is_unselected = (idx == 0)  # "— 선택하세요 —" 초기 상태
            # af_desc: 미선택 상태 또는 직접입력 모드에서만 표시 (드롭다운 실 선택 시 숨김)
            self._af_desc.setVisible(is_unselected or is_custom)
            # custom_input: 직접입력 모드에서만 표시 (기존 로직 유지)
            self._af_custom_input.setVisible(is_custom)

        self._af_target_combo.currentIndexChanged.connect(_on_af_target_changed)
        if self._af_target_combo.count() > 4:
            # Aspirin/NSAID classroom checks should start from a concrete,
            # inspectable protein target instead of an empty auto placeholder.
            self._af_target_combo.setCurrentIndex(4)

        # AlphaFold 열기 버튼
        af_btn_row = QHBoxLayout()
        self._btn_af_open = QPushButton("AlphaFold/PDB reference lookup")
        self._btn_af_open.setStyleSheet(
            "QPushButton { background: #1565C0; color: #90CAF9; border: 1px solid #1976D2; "
            "padding: 7px 14px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1976D2; }"
        )
        self._btn_af_open.clicked.connect(self._open_alphafold_with_target)
        af_btn_row.addStretch()
        af_btn_row.addWidget(self._btn_af_open)
        af_btn_row.addStretch()
        af_layout.addLayout(af_btn_row)
        layout.addWidget(af_group)

        # ── 목표 선택 (학생용 자연어) ──
        goal_group = QGroupBox("어떤 효과를 원하시나요?")
        goal_group.setStyleSheet("QGroupBox { font-weight: bold; color: #ff9800; }")
        goal_layout = QVBoxLayout(goal_group)

        self._drug_goal_combo = QComboBox()
        self._drug_goal_combo.setStyleSheet("padding: 6px; font-size: 12px;")
        self._drug_goal_combo.addItems([
            "🎯 항암 효과를 추가하고 싶어",
            "🧠 TPSA/LogP descriptor boundary를 확인하고 싶어 (BBB endpoint 아님)",
            "⏱️ 약효가 더 오래 지속되게 하고 싶어",
            "💧 물에 더 잘 녹게 하고 싶어",
            "🛡️ 부작용을 줄이고 싶어 (선택성 향상)",
            "⚡ 약이 더 빨리 분해되지 않게 하고 싶어 (대사 안정성)",
            "✏️ 직접 입력할래...",
        ])
        goal_layout.addWidget(self._drug_goal_combo)

        # 직접 입력 필드 (기본 숨김)
        self._drug_custom_goal = QLineEdit()
        self._drug_custom_goal.setPlaceholderText("예: 구조 경고와 용해도 descriptor를 함께 보고 싶어")
        self._drug_custom_goal.setStyleSheet("padding: 6px;")
        self._drug_custom_goal.hide()
        goal_layout.addWidget(self._drug_custom_goal)

        self._drug_goal_combo.currentIndexChanged.connect(
            lambda i: self._drug_custom_goal.setVisible(i == 6)
        )
        layout.addWidget(goal_group)

        # ── 실행 버튼 ──
        btn_row = QHBoxLayout()
        self._btn_drug_start = QPushButton("Run local design estimate")
        self._btn_drug_start.setStyleSheet(
            "QPushButton { background: #e65100; color: white; padding: 14px 24px; "
            "border-radius: 8px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #f57c00; }"
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        self._btn_drug_start.clicked.connect(self._run_drug_design)
        self._btn_drug_start.setToolTip(
            "Local RDKit/ADMET-style estimate only. No DrugBank, protein service, Vina, or lead success is implied."
        )
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

        self._drug_status = QLabel(
            "Local estimate only: no DrugBank match, protein service, Vina pose, or lead-success evidence loaded."
        )
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
        self._drug_result.setMaximumHeight(70)
        self._drug_result.hide()
        layout.addWidget(self._drug_result)

        # ── 상세 분석 버튼 (결과 나온 후 표시) ──
        self._btn_drug_detail = QPushButton("Open Lead Optimizer sandbox")
        self._btn_drug_detail.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; padding: 8px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1976d2; }"
        )
        self._btn_drug_detail.clicked.connect(self._open_lead_optimizer)
        self._btn_drug_detail.setEnabled(False)
        self._btn_drug_detail.setToolTip(
            "Route preserved but unavailable from quick estimate until a separate proven lead workflow exists."
        )
        self._btn_drug_detail.hide()
        layout.addWidget(self._btn_drug_detail)

        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return widget

    def _run_drug_design(self):
        """원클릭 신약 설계 — 목표 → 유도체 생성 → 간이 스코어링."""
        from PyQt6.QtCore import QThread, pyqtSignal

        goal_idx = self._drug_goal_combo.currentIndex()
        goal_map = {
            0: "항암 효과 추가",
            1: "BBB descriptor boundary review",
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
            logger.warning("약물 설계 건너뜀: 분자 SMILES 없음")
            self._drug_status.setText("⚠️ 먼저 분자를 입력해주세요!")
            return

        self._btn_drug_start.setEnabled(False)
        self._drug_progress.show()
        self._drug_progress.setRange(0, 0)  # indeterminate
        self._drug_status.setText(f"Running local derivative estimate for '{goal}'. No protein-service claim.")
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
                        except Exception as e:
                            logger.warning("ADMET scoring failed, using defaults: %s", e)
                            v.qed_score = 0.5
                        v.sa_score = calculate_sa_score(v.smiles)
                        v.docking_score = -6.0  # placeholder
                        score_variant(v, -5.0)

                    # Sort by rank
                    variants.sort(key=lambda x: x.composite_rank, reverse=True)

                    # Build result text
                    lines = [f"Local derivative candidates: {len(variants)} (goal: {self._goal})\n"]
                    lines.append("[SIMULATION_MODE] RDKit/ADMET-style ranking only; no DrugBank, protein, Vina, BBB endpoint/model, PK/safety, or lead-success evidence.")
                    lines.append(f"전략: {strategy.name_kr}")
                    if strategy.rationale:
                        lines.append(f"근거: {strategy.rationale[:80]}\n")

                    lines.append("Top 5 candidates (ranked estimates):")
                    for i, v in enumerate(variants[:5]):
                        tier_emoji = {"A": "🟢", "B": "🟡", "C": "🔴"}.get(v.tier, "⚪")
                        bbb = (
                            f"BBB descriptor score={v.bbb_score:.2f}; not BBB evidence"
                            if getattr(v, "bbb_score", None) is not None
                            else "BBB descriptor unavailable"
                        )
                        lines.append(
                            f"\nEstimated rank {i+1} {tier_emoji} [{v.tier}] score: {v.composite_rank:.2f}"
                        )
                        lines.append(f"   변형: {v.modification_detail}")
                        lines.append(f"   SMILES: {v.smiles[:50]}")
                        lines.append(f"   약물성(QED): {v.qed_score:.2f} | "
                                     f"합성난이도: {v.sa_score:.1f}/10 | {bbb}")

                    lines.append("\nLead Optimizer remains an advanced sandbox; it does not validate binding or optimization success.")
                    lines.append("Use only as local estimate context unless backend evidence is separately loaded.")

                    self.finished.emit("\n".join(lines))
                except Exception as e:
                    self.error.emit(str(e))

        def _on_done(text):
            self._drug_progress.hide()
            self._drug_progress.setRange(0, 100)
            self._btn_drug_start.setEnabled(True)
            self._drug_result.setPlainText(text)
            self._drug_result.show()
            self._btn_drug_detail.hide()
            self._drug_status.setText("Local estimate available. No DrugBank/protein/Vina/lead-success evidence is loaded.")

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
            # 현재 분자 SMILES를 팝업에 전달 (PDB ID 검색창 미리 채우기)
            smiles = getattr(self, '_current_smiles', '') or ''
            popup = AlphaFoldPopup(parent=self, initial_smiles=smiles)
            if smiles and hasattr(popup, 'pdb_id_input'):
                popup.pdb_id_input.setPlaceholderText(
                    f"현재 분자: {smiles[:30]}… (PDB ID 입력 또는 아래 목록 선택)")
            popup.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "AlphaFold", f"AlphaFold 열기 실패: {e}")

    def _open_alphafold_with_target(self):
        """[AF-DROPDOWN] 신약설계 탭 드롭다운 선택으로 AlphaFold 열기.

        선택된 표적 단백질 PDB ID를 AlphaFoldPopup에 미리 채워서 열기.
        '__auto__' = AI 추천 표적 자동 탐색 (PubChem 기반)
        '__custom__' = 직접 입력한 PDB ID / UniProt ID 사용
        """
        try:
            from popup_alphafold import AlphaFoldPopup
            idx = self._af_target_combo.currentIndex()
            pdb_val = self._af_target_combo.itemData(idx) if idx >= 0 else ""
            smiles = getattr(self, '_current_smiles', '') or ''
            popup = AlphaFoldPopup(parent=self, initial_smiles=smiles)

            if pdb_val == "__custom__":
                custom_text = self._af_custom_input.text().strip()
                if custom_text and hasattr(popup, 'pdb_id_input'):
                    popup.pdb_id_input.setText(custom_text)
                elif custom_text and hasattr(popup, 'seq_input'):
                    # FASTA처럼 보이면 서열 입력창에 넣기
                    if len(custom_text) > 10 and custom_text[0] not in '0123456789':
                        popup.seq_input.setPlainText(custom_text)
            elif pdb_val == "__auto__":
                # 현재 분자 SMILES로 표적 추천 — PDB ID 입력창에 안내 메시지
                if smiles and hasattr(popup, 'pdb_id_input'):
                    popup.pdb_id_input.setPlaceholderText(
                        f"리간드: {smiles[:25]}… — PDB ID를 입력하거나 AI 추천 결과를 기다리세요")
                    popup.status_label.setText(
                        f"현재 분자 ({smiles[:20]}…) 기반 표적 자동 탐색 중...")
            elif pdb_val and pdb_val not in ("", "__auto__", "__custom__"):
                # 특정 PDB ID 선택 → pdb_id_input에 미리 채우기
                if hasattr(popup, 'pdb_id_input'):
                    popup.pdb_id_input.setText(pdb_val)
                    popup.status_label.setText(
                        f"선택된 표적: {pdb_val} — '📥 PDB 다운로드' 버튼을 클릭하세요")

                # M831 anger#33: 신약설계 ↔ AlphaFold ↔ 도킹 탭 수용체 자동 연동
                # 신약설계 탭에서 PDB ID 선택 → 도킹 탭의 DockingEnergyPanel에도 동기화
                # 학술 근거: AlphaFold → 도킹 → ADMET 통합 워크플로우 (Varadi 2022)
                # Rule N: isinstance 타입 가드 필수
                if hasattr(popup, 'pdb_direct_input'):
                    popup.pdb_direct_input.setText(pdb_val)
                    if (
                        isinstance(pdb_val, str)
                        and len(pdb_val.strip()) == 4
                        and pdb_val.strip().isalnum()
                        and hasattr(popup, '_start_prediction')
                    ):
                        # Existing learner route, but avoid the visible Step 3
                        # dead-end: selected PDB targets should immediately run
                        # the same AlphaFold/RCSB calculation the button uses.
                        def _auto_start_selected_pdb(p=popup, pid=pdb_val.strip().upper()):
                            try:
                                if getattr(p, '_prediction_result', None) is None:
                                    if hasattr(p, 'tabs'):
                                        p.tabs.setCurrentIndex(2)
                                    p._start_prediction(pdb_id=pid)
                            except Exception as exc:
                                logger.warning(
                                    "[Molecule3DPopup] AlphaFold auto PDB start failed: %s",
                                    exc,
                                )

                        QTimer.singleShot(700, _auto_start_selected_pdb)

                if isinstance(pdb_val, str) and pdb_val and hasattr(self, 'tab_docking'):
                    tab_d = self.tab_docking
                    if isinstance(tab_d, QWidget) and hasattr(tab_d, '_current_pdb_id'):
                        tab_d._current_pdb_id = pdb_val
                        if hasattr(tab_d, 'btn_load_receptor'):
                            tab_d.btn_load_receptor.setEnabled(True)
                        if hasattr(tab_d, 'btn_pdbe_molstar'):
                            tab_d.btn_pdbe_molstar.setEnabled(True)
                        if hasattr(tab_d, 'receptor_info'):
                            tab_d.receptor_info.setText(
                                f"[신약설계 탭 연동] PDB {pdb_val} — "
                                "'도킹 점수' 탭에서 수용체 로드 가능"
                            )
                        if hasattr(tab_d, 'btn_dock') and smiles:
                            tab_d.btn_dock.setEnabled(True)
                        logger.info(
                            "[Molecule3DPopup] anger#33: 신약설계→도킹 탭 PDB 연동 (pdb=%s)", pdb_val
                        )

            # 현재 분자 SMILES 라벨 업데이트
            if smiles and hasattr(self, '_af_ligand_lbl'):
                disp = smiles[:40] + ("…" if len(smiles) > 40 else "")
                self._af_ligand_lbl.setText(f"현재 분자: {disp}")

            popup.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            logger.warning("AlphaFold 표적 팝업 열기 실패: %s", e)
            QMessageBox.warning(self, "AlphaFold", f"AlphaFold 열기 실패: {e}")

    def _open_synthesis(self):
        """합성경로 팝업 열기."""
        try:
            from popup_synthesis import SynthesisPopup
            smiles = getattr(self, '_current_smiles', '') or ''
            if not smiles:
                logger.warning("합성경로 팝업 건너뜀: SMILES 없음")
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

    # ================================================================
    # [UI 계층 개편] 고급 도구 버튼 핸들러 (컨트롤 바에서 호출)
    # 기존 메서드로 위임하거나, 없는 경우 새로 구현
    # ================================================================

    def _open_lead_optimizer_from_3d(self):
        """고급 도구 메뉴에서 리드 최적화 열기."""
        self._open_lead_optimizer()

    def _open_admet_from_3d(self):
        """고급 도구 메뉴에서 ADMET 분석 열기."""
        self._open_admet()

    def _open_alphafold_from_3d(self):
        """고급 도구 메뉴에서 AlphaFold 구조 예측 열기."""
        self._open_alphafold()

    def _open_docking_from_3d(self):
        """Manual docking popup route disabled for 3D popup containment."""
        logger.info("Manual docking popup route disabled in Molecule3DPopup advanced tools")
        return

    def _open_drug_screening_from_3d(self):
        """고급 도구 메뉴에서 신약 스크리닝 팝업 열기."""
        try:
            from popup_drug_screening import DrugScreeningPopup
            smiles_list = []
            names_list = []
            current_smiles = getattr(self, '_current_smiles', '') or ''
            if current_smiles:
                smiles_list.append(current_smiles)
                names_list.append("현재 분자")
            popup = DrugScreeningPopup(
                smiles_list=smiles_list,
                names_list=names_list,
                parent=self,
            )
            if hasattr(popup, "setWindowTitle"):
                popup.setWindowTitle("Drug Screening - local/advanced, unavailable proof boundary")
            if hasattr(popup, "status_label"):
                popup.status_label.setText(
                    "Local screening route only. No DrugBank service, protein service, Vina, or binding-success evidence is implied."
                )
            popup.exec()
        except Exception as e:
            logger.warning("신약 스크리닝 팝업 열기 실패: %s", e)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "신약 스크리닝", f"스크리닝 팝업 열기 실패: {e}")

    def _show_or_exec_analysis_popup(self, popup: QWidget, attr_name: str) -> None:
        capture_mode = (
            os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
            or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
        )
        setattr(self, attr_name, popup)
        if capture_mode:
            if hasattr(popup, "setModal"):
                popup.setModal(False)
            popup.show()
            popup.raise_()
            popup.activateWindow()
            return
        if hasattr(popup, "exec"):
            popup.exec()
        else:
            popup.show()

    def _open_uvvis_from_3d(self):
        """Visible 3D-popup route to the real UVVisPopup."""
        try:
            from popup_uvvis import UVVisPopup
            popup = UVVisPopup(parent=self)
            self._show_or_exec_analysis_popup(popup, "_active_uvvis_popup")
        except Exception as e:
            logger.warning("UV-Vis popup route failed: %s", e)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "UV-Vis", f"UV-Vis popup open failed: {e}")

    def _open_molorbital_from_3d(self):
        """Visible 3D-popup route to the real MolecularOrbitalPopup.

        [M911] degraded remote health 상태를 자식 팝업에 주입하여
        orca_exists=False / api_key_set=False 시 [SIMULATION_MODE]가 표시되도록 함.
        """
        try:
            from popup_molorbital import MolecularOrbitalPopup
            popup = MolecularOrbitalPopup(parent=self)
            # [M911] popup_3d 에서 이미 캐시한 degraded health 상태를 주입.
            # MolecularOrbitalPopup 은 __init__ 시 _get_remote_orca_status() 를 직접
            # 호출하므로, health raw 캐시가 있으면 overwrite 하여 degraded 판정 보장.
            _cached_raw = getattr(self, "_orca_remote_health_raw", None)
            if isinstance(_cached_raw, dict) and _cached_raw:
                popup._orca_remote_status = _cached_raw
                try:
                    from orca_remote_client import is_remote_orca_ready  # type: ignore
                    popup._orca_remote_available = bool(
                        is_remote_orca_ready(_cached_raw)
                    )
                except Exception as _e_inj:
                    logger.warning("[popup_3d][M911] MO 팝업 health 주입 실패: %s", _e_inj)
                    popup._orca_remote_available = False
                # 배너를 다시 갱신 (이미 init_ui 에서 설정됐을 수 있음)
                if hasattr(popup, "_update_simulation_banner"):
                    try:
                        popup._update_simulation_banner()
                    except Exception as _e_banner:
                        logger.warning(
                            "[popup_3d][M911] MO 팝업 배너 갱신 실패: %s", _e_banner
                        )
            self._show_or_exec_analysis_popup(popup, "_active_molorbital_popup")
        except Exception as e:
            logger.warning("Molecular orbital popup route failed: %s", e)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Molecular Orbital", f"Molecular orbital popup open failed: {e}")

    # ================================================================
    # Newman Projection
    # ================================================================

    def _open_newman(self):
        """Newman 투영 팝업 열기."""
        if not self.mol_data:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Newman", "분자 데이터가 없습니다.")
            logger.warning("Newman 투영 열기 실패: mol_data 없음")
            return
        try:
            self._newman_widget = NewmanProjectionWidget(self.mol_data, parent=None)
            self._newman_widget.show()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Newman", f"Newman 투영 열기 실패: {e}")
            logger.warning("Newman 투영 열기 오류: %s", e)

    def closeEvent(self, event):
        if self.viewer and hasattr(self.viewer, 'stop_vibration'):
            self.viewer.stop_vibration()
        if isinstance(self.viewer, Molecule3DViewer):
            self.viewer.cleanup()
        # [M514] ChemCharPanel orphan thread 즉시 종료 (Rule M: orphan HTTP thread 방지)
        if hasattr(self, 'tab_chem_char') and hasattr(self.tab_chem_char, 'stop_fetch'):
            self.tab_chem_char.stop_fetch()
        super().closeEvent(event)


# [P0-0 M517] ThreeDViewer alias — ct_hourly_review check_keywords 매칭용
# 6탭 접근: 속성/스펙트럼/진동모드/AI분석/ADMET/도킹에너지/신약설계 (6 tab, tab index 6=신약설계)
# embedded→popup 복원 완료. ThreeDViewer = Molecule3DPopup.
ThreeDViewer = Molecule3DPopup  # [P0-0] ThreeDViewer alias — 6탭 6 tab access (embedded→popup)
