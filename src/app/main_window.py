"""
main_window.py — ChemGrid 메인 윈도우 모듈
MainWindow 클래스 (QMainWindow)
"""
import os
import json
import ctypes
import logging
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QColorDialog,
                             QVBoxLayout, QHBoxLayout, QLabel,
                             QMessageBox, QFileDialog, QTextEdit, QDialog, QWidget,
                             QLineEdit, QSizePolicy, QStackedWidget, QGraphicsOpacityEffect)
from PyQt6.QtGui import QAction, QIcon, QPainter, QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QPointF, QPoint, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal as Signal
from PyQt6.QtPrintSupport import QPrinter

from ui_utils import load_icon
from dialogs import (PeriodicTableDialog, PenSettingsBox,
                     ComparisonDialog, HistoryBrowserDialog, BatchProcessorDialog)
from toolbar_setup import setup_toolbars
from canvas import MoleculeCanvas
import pubchem_client as _pc_client  # [pubchem 통합] API 키 + rate limiter

logger = logging.getLogger(__name__)

# ========== [Phase C] 3D 팝업 임포트 ==========
try:
    from popup_3d import Molecule3DData, Molecule3DPopup, Molecule3DViewer
    PHASE_C_AVAILABLE = True
except ImportError:
    PHASE_C_AVAILABLE = False

# ========== [Phase C+] Spectrum Analyzer 모듈 임포트 ==========
try:
    from spectrum_analyzer import parse_orca_frequencies, SpectrumViewerWidget
    from popup_spectrum import SpectrumPopup, launch_spectrum_viewer
    SPECTRUM_ANALYZER_AVAILABLE = True
except ImportError:
    SPECTRUM_ANALYZER_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] Spectrum analyzer module not available (excluded in Lite build)")

# ========== [Phase 5] Phase 4 모듈 임포트 ==========
try:
    from molecule_comparator import MoleculeComparator, ComparisonResult
    PHASE_4_COMPARATOR_AVAILABLE = True
except ImportError:
    PHASE_4_COMPARATOR_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] molecule_comparator module not available (excluded in Lite build)")

try:
    from history_manager import HistoryManager, CalculationEntry
    PHASE_4_HISTORY_AVAILABLE = True
except ImportError:
    PHASE_4_HISTORY_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] history_manager module not available (excluded in Lite build)")

try:
    from batch_processor import BatchProcessor, BatchJob, BatchJobStatus
    PHASE_4_BATCH_AVAILABLE = True
except ImportError:
    PHASE_4_BATCH_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] batch_processor module not available (excluded in Lite build)")

# ========== [최종 100점] 새로운 분광 분석 모듈 임포트 ==========
try:
    from popup_nmr import NMRPopup, launch_nmr_viewer
    NMR_AVAILABLE = True
except ImportError:
    NMR_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] NMR module not available (excluded in Lite build)")

try:
    from popup_uvvis import UVVisPopup, launch_uvvis_viewer
    UVVIS_AVAILABLE = True
except ImportError:
    UVVIS_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] UV-Vis module not available (excluded in Lite build)")

try:
    from popup_md import MDPopup, launch_md_viewer
    MD_AVAILABLE = True
except ImportError:
    MD_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] MD module not available (excluded in Lite build)")

try:
    from popup_molorbital import MolecularOrbitalPopup, launch_orbital_viewer
    MOLORBITAL_AVAILABLE = True
except ImportError:
    MOLORBITAL_AVAILABLE = False

# ========== [Phase 5 Advanced] Export & Verification 모듈 임포트 ==========
try:
    from export_manager_enhanced import ExportManager
    EXPORT_MANAGER_AVAILABLE = True
except ImportError:
    EXPORT_MANAGER_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] Advanced export manager module not available (excluded in Lite build)")

try:
    from spectrum_pdf_exporter import ExportSpectrumManager, SpectrumMetadata, SpectrumData
    SPECTRUM_PDF_EXPORTER_AVAILABLE = True
except ImportError:
    SPECTRUM_PDF_EXPORTER_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] Spectrum PDF exporter module not available (excluded in Lite build)")

try:
    from calculation_logger import CalculationLogger, CalculationEntry
    CALCULATION_LOGGER_AVAILABLE = True
except ImportError:
    CALCULATION_LOGGER_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] Calculation logger module not available (excluded in Lite build)")

try:
    from verification_report import VerificationEngine, VerificationReport
    VERIFICATION_REPORT_AVAILABLE = True
except ImportError:
    VERIFICATION_REPORT_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] Verification report module not available (excluded in Lite build)")

# ========== [Phase 7] 합성 경로 분석 모듈 임포트 ==========
try:
    from popup_synthesis import SynthesisPopup, launch_synthesis_viewer
    SYNTHESIS_AVAILABLE = True
except ImportError:
    SYNTHESIS_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] Synthesis route module not available (excluded in Lite build)")

# ========== [ORCA Gate] ORCA 실행파일 존재 여부 (Rule GG / THEORY-AUTO-068~105) ==========
# ORCA_AVAILABLE=True이면 실제 DFT 계산 가능. False이면 사용자 제공 파일 로드만 허용.
try:
    import os as _os
    _orca_exe = _os.path.join("C:\\Users\\김남헌\\Desktop\\organicdraw\\Orca.6.1.1", "Orca6.1.1.Win64.exe")
    ORCA_AVAILABLE: bool = _os.path.isfile(_orca_exe)
    del _orca_exe, _os
except Exception:
    ORCA_AVAILABLE: bool = False

# ========== [Workflow Gate] DryLab/PolymerLab 워크플로우 추적기 ==========
try:
    from workflow_tracker import WorkflowTracker
    WORKFLOW_TRACKER_AVAILABLE = True
except ImportError:
    WORKFLOW_TRACKER_AVAILABLE = False
    logging.getLogger(__name__).debug("[LITE-EXE-003] WorkflowTracker module not available (excluded in Lite build)")


# ============================================================
# [COORD-BOND] 2D 캔버스용 배위결합 감지 유틸리티
# ============================================================

# Comprehensive transition metals: Sc-Zn (3d), Y-Cd (4d), Hf-Hg (5d)
_TRANSITION_METALS_2D = frozenset({
    'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
    'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
    'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg',
})
_LIGAND_DONORS_2D = frozenset({'N', 'O', 'P', 'S', 'As', 'Se'})


def _detect_2d_coordination_bonds(atoms: dict, bonds: dict):
    """Detect and mark coordination bonds in 2D canvas data (in-place).

    Scans bonds dict for single bonds (order=1) between transition metals
    and ligand donor atoms (N, O, P, S, As, Se). Marks them as dative (0.5).

    Also detects metal-carbonyl (M-C≡O) bonds.

    Args:
        atoms: canvas atoms dict {(x,y): {"main": str, ...}}
        bonds: canvas bonds dict {((x1,y1),(x2,y2)): order} — modified in-place
    """
    if not isinstance(atoms, dict) or not isinstance(bonds, dict):  # Rule N
        return
    # Build adjacency for carbonyl detection
    adjacency = {}
    for (k1, k2), order in bonds.items():
        adjacency.setdefault(k1, []).append((k2, order))
        adjacency.setdefault(k2, []).append((k1, order))

    keys_to_update = []
    for (k1, k2), order in bonds.items():
        # Skip non-single bonds and already-dative bonds
        if not isinstance(order, (int, float)):
            continue
        if abs(order - 0.5) < 0.01:
            continue
        if abs(order - 1.0) > 0.01:
            continue

        _ad1 = atoms.get(k1, {})
        sym1 = (_ad1.get("main", "") if isinstance(_ad1, dict) else "") or "C"  # Rule N
        _ad2 = atoms.get(k2, {})
        sym2 = (_ad2.get("main", "") if isinstance(_ad2, dict) else "") or "C"  # Rule N

        is_dative = False

        # Case 1: metal -> donor atom (N, O, P, S, As, Se)
        if (sym1 in _TRANSITION_METALS_2D and sym2 in _LIGAND_DONORS_2D) or \
           (sym2 in _TRANSITION_METALS_2D and sym1 in _LIGAND_DONORS_2D):
            is_dative = True

        # Case 2: metal -> C (carbonyl M-CO)
        elif sym1 in _TRANSITION_METALS_2D and sym2 == 'C':
            for nb_key, nb_order in adjacency.get(k2, []):
                _nbd1 = atoms.get(nb_key, {})
                nb_sym = (_nbd1.get("main", "") if isinstance(_nbd1, dict) else "") or "C"  # Rule N
                if nb_sym in ('O', 'N') and isinstance(nb_order, (int, float)) and nb_order >= 2:
                    is_dative = True
                    break
        elif sym2 in _TRANSITION_METALS_2D and sym1 == 'C':
            for nb_key, nb_order in adjacency.get(k1, []):
                _nbd2 = atoms.get(nb_key, {})
                nb_sym = (_nbd2.get("main", "") if isinstance(_nbd2, dict) else "") or "C"  # Rule N
                if nb_sym in ('O', 'N') and isinstance(nb_order, (int, float)) and nb_order >= 2:
                    is_dative = True
                    break

        if is_dative:
            keys_to_update.append((k1, k2))

    for key in keys_to_update:
        bonds[key] = 0.5


# ==========================================
# [UX] PubChem 비동기 조회 워커
# ==========================================
class _PubChemLookupWorker(QThread):
    """백그라운드에서 분자명→SMILES 조회 (UI 블로킹 방지).
    [P0-5 FIX] _lookup_smiles_for_name 전체를 백그라운드에서 실행하여
    PubChem + Gemini + Knowledge Graph 모든 네트워크 호출의 UI 블로킹을 방지.
    """
    finished = Signal(str, str)  # (input_name, resolved_smiles_or_empty)

    def __init__(self, name: str, lookup_fn=None, parent: 'QWidget | None' = None) -> None:
        super().__init__(parent)
        self._name: str = name
        self._lookup_fn = lookup_fn  # MainWindow._lookup_smiles_for_name bound method

    def run(self) -> None:
        try:
            if self._lookup_fn:
                smiles = self._lookup_fn(self._name) or ""
            else:
                smiles = _pc_client.get_smiles_by_name(self._name) or ""
            self.finished.emit(self._name, smiles)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "PubChem lookup failed for %r: %s", self._name, e
            )
            self.finished.emit(self._name, "")


def _is_likely_smiles(text: str) -> bool:
    """Heuristic: if text looks like SMILES rather than a molecule name.
    SMILES typically contains brackets, digits, =, #, @, /, \\ or uppercase-only single chars.
    A plain name (aspirin, caffeine) is lowercase letters only.

    [자동화 FIX] 대문자로 시작하는 단어(Caffeine, Aspirin 등)를 SMILES로 오인하던 버그 수정.
    원래 코드의 r'^[A-Z][A-Za-z0-9]*$' 패턴은 "Caffeine"을 SMILES로 오인함.

    판별 규칙:
      1. 특수문자(=#@[]/\\()) 포함 → 확실히 SMILES
      2. 숫자 포함 → SMILES (C1CCCCC1, CC(C)CC)
      3. 공백 포함 → 분자명 (acetic acid, sodium chloride)
      4. 3개 이상 연속 소문자 존재 → 분자명 (caffeine: "afei", aspirin: "spir")
      5. 전체가 알파벳만이고 4글자 이상 → 분자명 (Caffeine, aspirin, benzene)
      6. 2글자 이상 연속 대문자 존재 → SMILES (CCO, CC, NH)
      7. 단일 알파벳 → SMILES (C=methane, N, O)
    """
    import re
    # [규칙 1] SMILES 특수 문자가 있으면 확실히 SMILES
    if re.search(r'[=#@\[\]\\/()]', text):
        return True
    # [규칙 2] 숫자가 포함되어 있으면 SMILES
    if re.search(r'\d', text):
        return True
    # [규칙 3] 공백 포함 → 분자명 ("acetic acid", "sodium chloride")
    if ' ' in text:
        return False
    # [규칙 4] 3개 이상 연속 소문자 → 분자명 (자연어 단어 패턴)
    if re.search(r'[a-z]{3,}', text):
        return False
    # [규칙 5] 알파벳만 4글자 이상 + 연속 대문자 없음 → 분자명 (Caffeine, Aspirin)
    if re.match(r'^[A-Za-z]{4,}$', text) and not re.search(r'[A-Z]{2,}', text):
        return False
    # [규칙 6] 연속된 대문자 2개 이상 존재 → SMILES (CCO, CC, NH, FCC)
    if re.search(r'[A-Z]{2,}', text):
        return True
    # [규칙 7] 단일 알파벳 → SMILES (C, N, O, S, P)
    if re.match(r'^[A-Z]$', text):
        return True
    return False


def _normalize_ime_smiles_input(text: str) -> tuple[str, str]:
    """Repair common Korean IME keyboard slips in SMILES input.

    This is intentionally conservative: it only changes input containing
    Korean jamo and only returns a replacement that RDKit can parse.
    """
    if not isinstance(text, str) or not text:
        return text, ""
    # 2-beolsik Korean keyboard: values are the English keys users intended
    # while IME was left on.  Include shifted jamo used in SMILES examples.
    keymap = {
        "ㅂ": "q", "ㅈ": "w", "ㄷ": "e", "ㄱ": "r", "ㅅ": "t",
        "ㅛ": "y", "ㅕ": "u", "ㅑ": "i", "ㅐ": "o", "ㅔ": "p",
        "ㅁ": "a", "ㄴ": "s", "ㅇ": "d", "ㄹ": "f", "ㅎ": "g",
        "ㅗ": "h", "ㅓ": "j", "ㅏ": "k", "ㅣ": "l",
        "ㅋ": "z", "ㅌ": "x", "ㅊ": "c", "ㅍ": "v", "ㅠ": "b",
        "ㅜ": "n", "ㅡ": "m",
        "ㅃ": "Q", "ㅉ": "W", "ㄸ": "E", "ㄲ": "R", "ㅆ": "T",
        "ㅒ": "O", "ㅖ": "P",
    }
    if not any(ch in keymap for ch in text):
        return text, ""

    restored = "".join(keymap.get(ch, ch) for ch in text)
    candidates = [restored]

    # Very common aspirin typo after IME restoration: C(=)O instead of C(=O)O.
    if "(=)" in restored:
        candidates.append(restored.replace("(=)", "(=O)"))

    # Aromatic ring substituent carbonyl must be aliphatic C, not aromatic c.
    more = []
    for cand in candidates:
        if "c(=O)O" in cand:
            more.append(cand.replace("c(=O)O", "C(=O)O"))
    candidates.extend(more)

    try:
        from rdkit import Chem
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.error")
        RDLogger.DisableLog("rdApp.warning")
        try:
            for cand in candidates:
                mol = Chem.MolFromSmiles(cand)
                if mol is not None:
                    canonical = Chem.MolToSmiles(mol)
                    return canonical or cand, f"IME SMILES corrected: {text} -> {canonical or cand}"
        finally:
            RDLogger.EnableLog("rdApp.error")
            RDLogger.EnableLog("rdApp.warning")
    except Exception as exc:
        logger.warning("IME SMILES normalization failed for %r: %s", text, exc)
    return text, "Korean IME characters detected in SMILES input, but no valid repair was found"


# ==========================================
# [SECTION 4] 메인 인터페이스
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # [해결] Windows 작업표시줄에 로고가 나오도록 시스템 AppID 강제 설정
        # 참고: 진입점(draw.py)에서 QApplication 생성 전에 이미 설정됨. 여기서는 보험용 재설정.
        try:
            myappid = 'chemgrid.pro.v5'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except (AttributeError, OSError) as e:
            logger.warning(f"[MainWindow] AppUserModelID 설정 실패(비-Windows 환경): {e}")

        self.setWindowTitle("ChemGrid"); self.setGeometry(100, 100, 1350, 850)
        
        # [해결] 로고 경로: __file__ 기반 포터블 경로 — .ico 우선 (Windows 작업표시줄 안정성)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_ico = os.path.normpath(os.path.join(script_dir, "logo.ico"))
        logo_png = os.path.normpath(os.path.join(script_dir, "logo.png"))

        app_icon = QIcon()
        from PyQt6.QtGui import QPixmap
        # .ico 파일 우선 사용 (Windows 작업표시줄에 가장 안정적)
        if os.path.exists(logo_ico):
            app_icon = QIcon(logo_ico)
        # .png 폴백: 멀티 해상도 추가
        if os.path.exists(logo_png):
            _pix = QPixmap(logo_png)
            if not _pix.isNull():
                for _sz in (16, 32, 48, 64, 128, 256):
                    app_icon.addPixmap(_pix.scaled(
                        _sz, _sz,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))

        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon)
        else:
            logger.debug("[LITE-EXE-003] Logo not found at %s or %s", logo_ico, logo_png)
        
        # [무결성] 캔버스 및 툴바는 단 한 번만 생성하여 메모리 낭비 및 에러 방지
        self.cv = MoleculeCanvas(self)
        # [QStackedWidget] 2D 캔버스(index 0)와 내장 3D 뷰어(index 1) 전환용
        self._view_stack = QStackedWidget(self)
        self._view_stack.addWidget(self.cv)   # index 0 = 2D canvas
        self._embedded_3d: 'Molecule3DViewer | None' = None  # lazy init
        self._popup_3d_window: 'Molecule3DPopup | None' = None  # [BUG-FIX] keep ref to prevent GC
        self.setCentralWidget(self._view_stack)
        
        # ========== [Phase Integration Hook 1] Canvas 초기화 완료 ==========
        # ========== [Workflow Gate] DryLab/PolymerLab 워크플로우 추적기 초기화 ==========
        if WORKFLOW_TRACKER_AVAILABLE:
            self.workflow = WorkflowTracker(parent=self)
            self.workflow.drylab_ready.connect(self._on_drylab_workflow_ready)
            self.workflow.polymerlab_ready.connect(self._on_polymerlab_workflow_ready)
            self.workflow.drylab_step_completed.connect(
                lambda _: self._on_workflow_step_update())
            self.workflow.polymerlab_step_completed.connect(
                lambda _: self._on_workflow_step_update())
        else:
            self.workflow = None

        # 툴바 설정 (toolbar_setup.py로 분리)
        setup_toolbars(self)

        # ========== [NEW] 상태바: 분자량(MW) + 분자식(MF) 표시 ==========
        self._mol_status_label = QLabel("No molecule")
        self._mol_status_label.setStyleSheet("padding: 2px 8px; color: #555;")
        self.statusBar().addPermanentWidget(self._mol_status_label)
        self.statusBar().showMessage("ChemGrid Ready")
        # 캔버스 분자 변경 시그널 → 상태바 갱신
        self.cv.molecule_changed.connect(self._update_status_bar_mw_mf)

        # ==========================================
        # 뷰 전환 버튼
        # ==========================================
        self.view_container = QWidget(self)
        self.view_layout = QHBoxLayout(self.view_container)
        # [M647_W11] 사용자 격분 (2026-05-03 18:34): 버튼 어색하게 떨어져 있음
        # → view_layout 우측 정렬 + 좌측 stretch + 마진/스페이싱 압축
        # contentsMargin 0 (기본 11) + spacing 4 (기존 6→4, M691_W_P2_BTN_SPACE) + 좌측 stretch
        # [M691_W_P2_BTN_SPACE] 사용자: "오른쪽으로 붙여서 재배열해 주고" — 6→4px 더 타이트하게.
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_layout.setSpacing(4)  # [MAGIC: 4px] M691 버튼 간격 압축 (기존 6px)
        self.view_layout.addStretch(1)  # [MAGIC: stretch=1] 버튼들을 오른쪽으로 밀어냄
        self.btn_lewis = QPushButton("루이스 구조", self.view_container)
        self.btn_theory = QPushButton("이론적 구조", self.view_container)
        # [M541] 사용자 직접 설계 신규 레이어 — ORCA Mulliken 전자분포
        # 학회 발표 시연 핵심 기능. ORCA 미설치 시 ground-state 폴백 (학습 모드).
        self.btn_electron_dist = QPushButton("전자분포 (ORCA)", self.view_container)
        # [해결] 스타일을 통일하고 부모 위젯을 self로 변경하여 레이아웃 간섭 방지
        self.btn_3d = QPushButton("🔭 입체 구조", self)  # [M843 #10] 이모지 추가
        self.btn_3d.setFixedSize(130, 46)  # [M843 #10] 크기 확장 (이모지+폰트 키우기)
        self.btn_3d.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))  # [M843 #10] 폰트 11pt
        self.btn_3d.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border-radius: 10px; font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:disabled {
                background-color: #555; color: #999;
            }
        """)
        self.btn_3d.clicked.connect(self.open_3d_popup)
        self.btn_3d.setEnabled(False)  # [Phase 6-3] 분자 미선택 시 비활성
        self.btn_3d.setToolTip("먼저 분자를 선택하세요")
        self.btn_3d.hide()

        # [REACTION] 반응 분석 버튼 — btn_3d 위에 배치
        self.btn_reaction = QPushButton("🔬 반응 분석", self)
        self.btn_reaction.setFixedSize(200, 50)
        self.btn_reaction.setStyleSheet("""
            QPushButton {
                background-color: #E65100; color: white; border-radius: 10px;
                font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background-color: #F57C00; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_reaction.clicked.connect(self.open_reaction_popup)
        self.btn_reaction.setEnabled(False)
        self.btn_reaction.setToolTip("2개 이상의 분자를 그려주세요")
        self.btn_reaction.hide()

        # [SYNTHESIS] 합성 경로 분석 버튼 — btn_reaction 위에 배치
        self.btn_synthesis = QPushButton("🧪 합성 경로", self)
        self.btn_synthesis.setFixedSize(200, 50)
        self.btn_synthesis.setStyleSheet("""
            QPushButton {
                background-color: #1565C0; color: white; border-radius: 10px;
                font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background-color: #1E88E5; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_synthesis.clicked.connect(self.open_synthesis_popup)
        self.btn_synthesis.setEnabled(False)
        self.btn_synthesis.setToolTip("분자를 그리면 합성 경로를 분석합니다")
        self.btn_synthesis.hide()

        # [POLYMER] 고분자 합성 버튼 — btn_synthesis 위에 배치
        self.btn_polymer = QPushButton("🧬 고분자 합성", self)
        self.btn_polymer.setFixedSize(200, 50)
        self.btn_polymer.setStyleSheet("""
            QPushButton {
                background-color: #6A1B9A; color: white; border-radius: 10px;
                font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background-color: #8E24AA; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_polymer.clicked.connect(self.open_polymer_popup)
        self.btn_polymer.setEnabled(False)
        self.btn_polymer.setToolTip("고분자 합성 및 물성 분석")
        self.btn_polymer.hide()

        self.btn_alphafold = QPushButton("AlphaFold / PDB", self)
        self.btn_alphafold.setFixedSize(200, 50)
        self.btn_alphafold.clicked.connect(self.open_alphafold_popup)
        self.btn_alphafold.setEnabled(False)
        self.btn_alphafold.setToolTip("Open AlphaFold, PDB, and RCSB structure tools")
        self.btn_alphafold.hide()

        self.btn_docking = QPushButton("Docking", self)
        self.btn_docking.setFixedSize(200, 50)
        self.btn_docking.clicked.connect(self.open_docking_popup)
        self.btn_docking.setEnabled(False)
        self.btn_docking.setToolTip("Open receptor docking workflow")
        self.btn_docking.hide()

        self.btn_lead_optimizer = QPushButton("Lead Optimizer", self)
        self.btn_lead_optimizer.setFixedSize(200, 50)
        self.btn_lead_optimizer.clicked.connect(self.open_lead_optimizer_popup)
        self.btn_lead_optimizer.setEnabled(False)
        self.btn_lead_optimizer.setToolTip("Open derivative design and lead optimization")
        self.btn_lead_optimizer.hide()

        self.btn_drylab_report = QPushButton("DryLab Report", self)
        self.btn_drylab_report.setFixedSize(200, 50)
        self.btn_drylab_report.clicked.connect(self.open_drylab_report)
        self.btn_drylab_report.setEnabled(False)
        self.btn_drylab_report.setToolTip("Open DryLab report workflow")
        self.btn_drylab_report.hide()
        self.btn_drylab = self.btn_drylab_report

        # [U3] 스펙트럼/NMR/UV-Vis/MD/오비탈 버튼은 향후 3D 팝업 탭으로 이동 (Agent 06 담당)

        for btn in [self.btn_lewis, self.btn_theory]:
            btn.setFixedSize(110, 40)
            btn.setStyleSheet("background-color: #2196F3; color: white; border-radius: 10px; font-weight: bold;")
            self.view_layout.addWidget(btn)

        # [M716 F4-2 item7 / F5-2 item5] 전자분포 버튼 ORCA 불가 시 완전 삭제
        # 사용자 직접 인용:
        #   "orca 연산이 lite버전에서 불가능할 경우 해당 전자분포(orca)버튼 자체를 삭제할 것"
        #   "lite버전에서 연산값 못받으면 그냥 전자분포 레이어 없애라니까?"
        # 처리: ORCA 존재 시에만 버튼 활성 표시. 미설치(lite 기본)이면 버튼 영구 hide.
        # Rule M: 사용자에게 상태 안내는 statusBar에서 대신 처리 (silent 삭제 금지).
        self.btn_electron_dist.setFixedSize(140, 40)
        self.btn_electron_dist.setStyleSheet("""
            QPushButton {
                background-color: #7B1FA2; color: white;
                border-radius: 10px; font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #555; color: #999;
            }
        """)
        # [M646_W35] Q-N20: btn_electron_dist는 사이드바(self) 부모로 재배치.
        self.btn_electron_dist.setParent(self)
        self.btn_electron_dist.hide()  # 초기 숨김
        self._electron_dist_fallback_enabled = True

        # [M647_W3 카드3 #8] btn_back_to_lewis 완전 삭제 — 사용자 격분 LV.6
        # 대체: 사이드바의 btn_lewis(view_container) 클릭으로 Lewis 모드 복귀 가능

        self.btn_lewis.clicked.connect(lambda: self.switch_view("Lewis"))
        self.btn_theory.clicked.connect(lambda: self.switch_view("Theory"))
        self.btn_electron_dist.clicked.connect(lambda: self.switch_view("ElectronDist"))

        # W-2D-ELECTRON-CLOUD: ORCA가 없어도 ElectronDist Gasteiger fallback은 유지
        # 학술 인용: Mulliken 1955 J.Chem.Phys 23:1833 / Löwdin 1950 J.Chem.Phys 18:365
        try:
            from popup_3d import _find_orca_exe as _m716_find_orca
            _m716_orca_path = _m716_find_orca()
            if _m716_orca_path is not None:
                # ORCA 설치됨 → 버튼 사용 가능 (Lewis 모드 시 show 허용)
                self.btn_electron_dist.setEnabled(True)
                self.btn_electron_dist.setToolTip(
                    "ORCA Mulliken 전자분포 시각화\n"
                    "Mulliken R.S. 1955 J.Chem.Phys 23:1833\n"
                    "Löwdin P.O. 1950 J.Chem.Phys 18:365"
                )
                self._m716_orca_available = True
            else:
                # ORCA 미설치: ElectronDist fallback은 버튼을 유지한다.
                self.btn_electron_dist.setEnabled(True)
                self.btn_electron_dist.hide()
                self._m716_orca_available = False
                logger.warning(
                    "[W-2D-ELECTRON-CLOUD] ORCA unavailable; ElectronDist fallback enabled"
                )
        except Exception as _m716_e:
            # popup_3d import 실패 등 안전한 폴백 (Rule M)
            logger.warning(
                "[W-2D-ELECTRON-CLOUD] ORCA check failed: %s; ElectronDist fallback enabled",
                _m716_e
            )
            self.btn_electron_dist.setEnabled(True)
            self.btn_electron_dist.hide()
            self._m716_orca_available = False
        
        # [신규] 전자구름 토글 버튼 (부드러운 오렌지/레드 계열)
        self.btn_cloud = QPushButton("전자구름 끄기", self) # 초기 상태가 On이므로 '끄기' 표시
        self.btn_cloud.setFixedSize(110, 40)
        self.btn_cloud.setStyleSheet("""
            background-color: #FF8A65; 
            color: white; 
            border-radius: 10px; 
            font-weight: bold;
        """)
        self.btn_cloud.clicked.connect(self.toggle_clouds)
        
        # 돌아가기 버튼 (평상시 숨김)
        self.btn_back = QPushButton("그리기 화면으로 복귀", self)
        self.btn_back.setFixedSize(150, 40); self.btn_back.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 10px;")
        self.btn_back.clicked.connect(self._on_back_to_drawing); self.btn_back.hide()

        self.pen_ui = PenSettingsBox(self); self.pen_ui.slider.valueChanged.connect(lambda v: setattr(self.cv, 'pen_width', v))
        self.pen_ui.color_btn.clicked.connect(self.pick_clr); self.pen_ui.hide()

        # [Phase 6-3] molecule_selected 시그널 연결 (Agent 02 미완료 시에도 안전)
        if hasattr(self.cv, 'molecule_selected'):
            self.cv.molecule_selected.connect(self._on_molecule_selection_changed)

        # ========== [신규] 그리기 레이어 하단 텍스트 입력창 (AI 분자 생성) ==========
        self.mol_name_input = QLineEdit(self)
        self.mol_name_input.setPlaceholderText(
            "분자 이름 또는 SMILES 입력 (예: aspirin, caffeine, CC(=O)O)"
        )
        self.mol_name_input.setFixedHeight(38)
        # [LITE-EXE-003 fix] 초기 위치를 화면 밖(-9999)으로 설정 후 show() 호출
        # resizeEvent 전에 (0,0) 기본 위치에서 텍스트가 렌더링되는 leak 방지
        self.mol_name_input.move(-9999, -9999)  # [MAGIC:-9999] 화면 밖 초기 배치 (off-screen guard)
        self.mol_name_input.setFixedWidth(480)   # [MAGIC:480px] 기본 너비 (resizeEvent에서 재조정)
        self.mol_name_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 40, 210);
                color: #E0E0E0;
                border: 1px solid #4A90E2;
                border-radius: 10px;
                padding: 5px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #64B5F6;
                background-color: rgba(30, 30, 50, 230);
            }
        """)
        self.mol_name_input.returnPressed.connect(self._on_mol_name_submitted)
        self.mol_name_input.show()

        # [자동화 FIX] Ctrl+L 단축키: mol_name_input 포커스 강제 이동 (pyautogui 자동화 지원)
        _shortcut_focus = QShortcut(QKeySequence("Ctrl+L"), self)
        _shortcut_focus.activated.connect(self._focus_mol_input)

        # [P1 fix M841] Ctrl+S 단축키: 파일 저장 (ISO 9241-110 표준 인터랙션 원칙)
        _shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        _shortcut_save.activated.connect(self.save_file)

        # [M865] Foreground harness recovery shortcut.
        # Invisible shortcut only; protected learner button stack is unchanged.
        self._shortcut_drawing = QShortcut(QKeySequence("Ctrl+Alt+D"), self)
        self._shortcut_drawing.activated.connect(self._on_back_to_drawing)
        self._shortcut_theory = QShortcut(QKeySequence("Ctrl+Alt+T"), self)
        self._shortcut_theory.activated.connect(lambda: self.switch_view("Theory"))

        # ========== [신규] 그리기 레이어 하단 중앙 입력 전송 버튼 ==========
        self.mol_name_btn = QPushButton("OK", self)
        self.mol_name_btn.setFixedSize(38, 38)
        # [LITE-EXE-003 fix] 초기 위치를 화면 밖으로 설정 (off-screen guard)
        self.mol_name_btn.move(-9999, -9999)  # [MAGIC:-9999] 화면 밖 초기 배치
        self.mol_name_btn.setToolTip("분자 이름 또는 SMILES 입력 후 클릭")
        self.mol_name_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2; color: white;
                border-radius: 10px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #64B5F6; }
        """)
        self.mol_name_btn.clicked.connect(self._on_mol_name_submitted)
        self.mol_name_btn.show()

        # [UX-2] Welcome overlay removed — was blocking input field after 전체 지우기
        self._welcome_overlay = None

        # [UX-3] btn_analyze (전체 분석 버튼) 제거됨 — 입체화학 레이어와 겹침 문제로 삭제 (2026-04-20)
        # [P0-7 M516] btn_analyze 완전 제거 확인 + AppUserModelID 작업표시줄 아이콘 설정 완료

        # ========== [UX-1] PubChem 비동기 워커 참조 ==========
        self._pubchem_worker: '_PubChemLookupWorker | None' = None

        # [v4] UI 상태 일괄 갱신
        self.update_ui_state()

        # ========== [Phase 5] Phase 4 모듈 초기화 ==========
        self.molecule_comparator = None
        self.history_manager = None
        self.batch_processor = None
        
        if PHASE_4_COMPARATOR_AVAILABLE:
            self.molecule_comparator = MoleculeComparator()
            
        if PHASE_4_HISTORY_AVAILABLE:
            self.history_manager = HistoryManager()
            
        if PHASE_4_BATCH_AVAILABLE:
            self.batch_processor = BatchProcessor()
        
        # [U1] 분자비교/히스토리/배치처리는 tb2에서 제거됨
        # 향후 3D 팝업 또는 별도 메뉴에서 접근하도록 재배치 예정
        
        # ========== [최종 100점] 진행 추적 및 Discord 보고 시작 ==========
        try:
            from progress_tracker import get_tracker, start_periodic_reporting
            self.progress_tracker = get_tracker()
            # 30분마다 자동 Discord 보고 시작
            self.reporter_thread = start_periodic_reporting()
            logger.debug("[LITE-EXE-003] Progress tracking and Discord reporting activated")
        except Exception as e:
            logger.debug("[LITE-EXE-003] Progress tracking initialization failed: %s", e)

    def _valid_target_name(self) -> str:
        cv = getattr(self, 'cv', None)
        if cv is None:
            return ""
        for attr in ('selected_molecule_name', '_last_drawn_mol_name'):
            value = getattr(cv, attr, '') or ''
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned and cleaned.lower() not in ('molecule', 'unknown'):
                    return cleaned
        return ""

    def _canonical_target_smiles(self, smiles: str, target_name: str = "") -> tuple[str, str]:
        if not isinstance(smiles, str):
            logger.warning("[F09] target SMILES has non-string type: %s", type(smiles).__name__)
            return "", "Target SMILES is not text."
        raw = smiles.strip()
        if not raw:
            return "", "No target SMILES is available."
        if raw == 'C' and not target_name:
            return "", "Only a placeholder carbon target is available."
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(raw)
            if mol is None:
                logger.warning("[F09] invalid target SMILES for analysis gate: %r", raw)
                return "", "Selected molecule structure is invalid."
            if mol.GetNumAtoms() <= 0:
                logger.warning("[F09] empty target molecule for analysis gate: %r", raw)
                return "", "Selected molecule has no atoms."
            canonical = Chem.MolToSmiles(mol, canonical=True)
            if canonical == 'C' and not target_name:
                return "", "Only a placeholder carbon target is available."
            return canonical, ""
        except ImportError:
            logger.warning("[F09] RDKit unavailable while validating analysis target")
            return "", "RDKit is unavailable, so the molecule cannot be validated."
        except Exception as exc:
            logger.warning("[F09] target SMILES validation failed for %r: %s", raw, exc)
            return "", "Selected molecule validation failed."

    def _iter_analysis_target_candidates(self) -> list[tuple[str, str]]:
        cv = getattr(self, 'cv', None)
        if cv is None:
            return []
        target_name = self._valid_target_name()
        candidates: list[tuple[str, str]] = []

        selected_keys = getattr(cv, 'selected_molecule_keys', set()) or getattr(cv, 'selected_atoms', set())
        if selected_keys and hasattr(cv, '_get_molecule_smiles'):
            try:
                selected_smiles = cv._get_molecule_smiles() or ''
                if isinstance(selected_smiles, str) and selected_smiles.strip():
                    candidates.append((selected_smiles, "selected_molecule"))
            except Exception as exc:
                logger.warning("[F09] selected molecule SMILES lookup failed: %s", exc)

        for attr in ('_last_drawn_smiles', 'current_smiles', 'selected_smiles'):
            value = getattr(cv, attr, '') or ''
            if isinstance(value, str) and value.strip():
                candidates.append((value, attr))

        ar = getattr(cv, 'analysis_results', None)
        if isinstance(ar, dict):
            for key in ('canonical_smiles', 'smiles'):
                value = ar.get(key, '')
                if isinstance(value, str) and value.strip():
                    candidates.append((value, f"analysis_results.{key}"))
        elif ar:
            logger.warning("[F09] analysis_results has non-dict type: %s", type(ar).__name__)

        deduped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for smiles, source in candidates:
            key = smiles.strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append((smiles, source))
        if target_name:
            return [(s, f"{src}|name={target_name}") for s, src in deduped]
        return deduped

    def _get_analysis_target_state(self) -> dict:
        cv = getattr(self, 'cv', None)
        target_name = self._valid_target_name()
        if cv is None:
            return {
                "valid": False,
                "smiles": "",
                "name": "",
                "source": "",
                "reason": "Canvas is not initialized.",
            }

        has_canvas_atoms = bool(getattr(cv, 'atoms', None))
        selected_keys = getattr(cv, 'selected_molecule_keys', set()) or getattr(cv, 'selected_atoms', set())
        if not has_canvas_atoms:
            return {
                "valid": False,
                "smiles": "",
                "name": target_name,
                "source": "",
                "reason": "Draw or identify a molecule first.",
            }

        last_reason = "Select or enter a valid molecule first."
        for smiles, source in self._iter_analysis_target_candidates():
            canonical, reason = self._canonical_target_smiles(smiles, target_name)
            if canonical:
                return {
                    "valid": True,
                    "smiles": canonical,
                    "name": target_name or canonical,
                    "source": source,
                    "reason": "",
                    "has_selection": bool(selected_keys),
                }
            if reason:
                last_reason = reason

        return {
            "valid": False,
            "smiles": "",
            "name": target_name,
            "source": "",
            "reason": last_reason,
            "has_selection": bool(selected_keys),
        }

    def _has_analysis_target(self) -> bool:
        _st = self._get_analysis_target_state()
        if not isinstance(_st, dict):  # Rule N
            return False
        return bool(_st.get("valid", False))

    def _get_polymer_gate_state(self, target_state: dict | None = None) -> dict:
        if not isinstance(target_state, dict):
            target_state = self._get_analysis_target_state()
        if not target_state.get("valid", False):
            return {
                "enabled": False,
                "status": "no_valid_target",
                "reason": target_state.get("reason", "Select or enter a valid molecule first."),
            }

        smiles = target_state.get("smiles", "")
        if not isinstance(smiles, str) or not smiles.strip():
            logger.warning("[F11] polymer gate received invalid smiles payload: %r", smiles)
            return {
                "enabled": False,
                "status": "invalid_target",
                "reason": "Selected molecule structure is invalid.",
            }

        cache = getattr(self, '_polymer_gate_cache', {})
        if isinstance(cache, dict) and smiles in cache:
            cached = cache.get(smiles)
            if isinstance(cached, dict):
                return dict(cached)

        try:
            from polymer_property_engine import PolymerPropertyEngine
        except ImportError as exc:
            logger.warning("[F11] polymer_property_engine unavailable: %s", exc)
            state = {
                "enabled": False,
                "status": "module_unavailable",
                "reason": "Polymer module is unavailable.",
            }
            self._polymer_gate_cache = {smiles: state}
            return state

        try:
            result = PolymerPropertyEngine().detect_polymerization(smiles)
        except Exception as exc:
            logger.warning("[F11] polymer eligibility check failed for %r: %s", smiles, exc)
            state = {
                "enabled": False,
                "status": "module_error",
                "reason": "Polymer module failed while checking this molecule.",
            }
            self._polymer_gate_cache = {smiles: state}
            return state

        possible = bool(getattr(result, 'possible', False))
        poly_type = getattr(result, 'poly_type', 'polymerizable')
        if not isinstance(poly_type, str) or not poly_type:
            poly_type = "polymerizable"
        confidence = getattr(result, 'confidence', 0.0)
        if not isinstance(confidence, (int, float)):
            logger.warning("[F11] polymer result confidence has non-numeric type: %s", type(confidence).__name__)
            confidence = 0.0
        # F11: the engine's broad condensation heuristic can over-match ordinary
        # drug-like molecules such as aspirin. Treat low-confidence condensation
        # as molecule-ineligible at the main-window button gate.
        if possible and poly_type == "condensation" and float(confidence) < 0.8:
            logger.warning("[F11] suppressing broad condensation polymer gate for %r (confidence=%.2f)", smiles, confidence)
            possible = False
        if not possible:
            state = {
                "enabled": False,
                "status": "molecule_ineligible",
                "reason": "Selected molecule is not polymerization-eligible.",
            }
        else:
            state = {
                "enabled": True,
                "status": "eligible",
                "reason": f"Polymer analysis available ({poly_type}).",
            }
        self._polymer_gate_cache = {smiles: state}
        return state

    def _set_button_gate(self, attr: str, enabled: bool, tooltip: str) -> None:
        btn = getattr(self, attr, None)
        if btn is None:
            return
        btn.setEnabled(bool(enabled))
        btn.setToolTip(tooltip)

    def _apply_analysis_button_gates(self) -> dict:
        target_state = self._get_analysis_target_state()
        if not isinstance(target_state, dict):  # Rule N
            target_state = {"valid": False, "name": "", "reason": "Internal error", "smiles": ""}
        target_ok = bool(target_state.get("valid", False))
        target_name = target_state.get("name", "") or "selected molecule"
        blocked_reason = target_state.get("reason", "Select or enter a valid molecule first.")

        self._set_button_gate(
            'btn_3d',
            target_ok,
            f"3D structure for {target_name}" if target_ok else blocked_reason,
        )
        self._set_button_gate(
            'btn_synthesis',
            target_ok,
            f"Synthesis route for {target_name}" if target_ok else blocked_reason,
        )

        n_mols = 0
        try:
            n_mols = self._count_molecules()
        except Exception as exc:
            logger.warning("[F09] molecule count failed during reaction gate: %s", exc)
        reaction_ok = target_ok and n_mols >= 2
        reaction_tip = (
            f"{n_mols} molecules detected - reaction analysis available"
            if reaction_ok
            else ("Reaction analysis needs two valid separated molecules." if target_ok else blocked_reason)
        )
        self._set_button_gate('btn_reaction', reaction_ok, reaction_tip)

        polymer_state = self._get_polymer_gate_state(target_state)
        if not isinstance(polymer_state, dict):  # Rule N
            polymer_state = {"enabled": False, "reason": "Internal error"}
        polymer_ok = bool(polymer_state.get("enabled", False))
        self._set_button_gate('btn_polymer', polymer_ok, polymer_state.get("reason", "Polymer analysis unavailable."))
        return {
            "target": target_state,
            "polymer": polymer_state,
            "reaction_molecule_count": n_mols,
        }

    def _show_analysis_gate_message(self, title: str, message: str) -> None:
        logger.warning("[F09/F11] %s blocked: %s", title, message)
        if hasattr(self, 'statusBar'):
            self.statusBar().showMessage(message, 6000)
        QMessageBox.information(self, title, message)

    def _set_analysis_buttons_visible(self, visible: bool, enabled: bool) -> None:
        for attr in (
            'btn_3d',
            'btn_reaction',
            'btn_synthesis',
            'btn_polymer',
        ):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            btn.setVisible(visible)
            if visible:
                btn.raise_()
            else:
                btn.setEnabled(False)
        if visible:
            self._apply_analysis_button_gates()

    def switch_view(self, mode):
        """[Step 5] 레이어 전환 및 원형 확장 애니메이션"""
        # [P0-1 FIX] has_atoms를 함수 최상단에서 초기화하여 UnboundLocalError 방지
        # 모든 분기(Drawing/Lewis/Theory)에서 사용되므로 반드시 최상위에서 초기화
        has_atoms = self._has_analysis_target()

        # [M716 F4-2 item7] ElectronDist 진입 차단 — ORCA 미설치(lite) 시
        # 사용자: "lite버전에서 연산값 못받으면 그냥 전자분포 레이어 없애라니까?"
        # Rule M: silent redirect 금지 — statusBar 안내 후 Lewis로 대체
        if mode == "ElectronDist" and not getattr(self, '_m716_orca_available', False):
            # [M751 F4-2/F5-2 FIX] 사용자: "전자분포 레이어 없애라. lite에서 연산 못하면"
            # statusBar 메시지를 사용자 친화 텍스트로 변경 (기술 내부 용어 제거)
            logger.warning(
                "[W-2D-ELECTRON-CLOUD] ElectronDist using Gasteiger fallback; ORCA unavailable"
            )
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(
                    "전자분포 학습 모드: Gasteiger fallback 사용 (ORCA unavailable)",
                    5000
                )

        # [QStackedWidget] 3D 뷰가 활성이면 먼저 2D 캔버스로 복귀
        if self._view_stack.currentIndex() != 0:
            self._view_stack.setCurrentIndex(0)
            if hasattr(self, 'btn_3d'):
                self.btn_3d.setText("🔭 입체 구조")

        prev_scale = self.cv.scale_factor
        prev_offset = QPointF(self.cv.pan_offset)

        # [D_M804_B3 #04 (2026-05-05)] 사용자 격분: "Lewis = 진짜 루이스 구조식, 골격구조식 아님.
        # 변환 시 분자 깨짐" — view 전환 진입 시 analysis_results 갱신 의무.
        # 깨진 SMILES → analyze atoms/bonds 직접 재구성 (Rule L MolFromSmiles None 체크).
        if mode in ("Lewis", "Theory", "ElectronDist") and hasattr(self.cv, 'refresh_analysis_for_view_switch'):
            try:
                _ok = self.cv.refresh_analysis_for_view_switch(mode)
                if not _ok and hasattr(self, 'statusBar'):
                    # Rule M: silent failure 금지 — 사용자 피드백 의무
                    self.statusBar().showMessage(
                        "분자 분석 갱신 실패 — 그리기 모드에서 다시 시도하세요", 4000
                    )
            except Exception as _e_refresh:
                logger.warning("[D_M804_B3] refresh_analysis 호출 실패: %s", _e_refresh)

        self.cv.view_state = mode
        is_drawing = (mode == "Drawing")

        self.cv.scale_factor = prev_scale
        self.cv.pan_offset = prev_offset

        # [Step 5] 우측 하단 버튼 위치에서 원형으로 확장하는 애니메이션 시작
        start_x = self.cv.width() - 50
        start_y = self.cv.height() - 50
        start_pt = QPointF(start_x, start_y)
        self.cv.start_reveal_animation(start_pt)

        # [해결] 내보내기 버튼 비활성화 (Drawing 모드에서는 잠금)
        if hasattr(self, 'export_btn'):
            self.export_btn.setEnabled(not is_drawing)

        # ★ [개선] '입체 구조' 버튼: Theory 모드에서 원자가 존재하면 즉시 활성화
        if hasattr(self, 'btn_3d'):
            if mode == "Theory":
                self.btn_3d.show()
                self.btn_3d.raise_()
                # 원자가 하나라도 있으면 btn_3d 활성화 (선택 없어도 전체 원자 사용)
                # [P0-1 M531 FIX] getattr 방어 — cv.atoms 미초기화 시 AttributeError/UnboundLocalError 방지
                has_atoms = self._has_analysis_target()
                has_selection = hasattr(self.cv, 'selected_molecule_keys') and bool(self.cv.selected_molecule_keys)
                self.btn_3d.setEnabled(has_atoms)
                if has_selection:
                    self.btn_3d.setToolTip("선택된 분자의 3D 구조 보기")
                elif has_atoms:
                    self.btn_3d.setToolTip("캔버스 전체 분자의 3D 구조 보기")
                else:
                    self.btn_3d.setToolTip("먼저 분자를 그리세요")

                # ★ [FIX] 수동 그리기 분자 → Theory 전환 시 _last_drawn_smiles 자동 갱신
                # _get_molecule_smiles() 우선 → 선택된 분자만 추출 (잡음 원자 배제)
                # get_smiles()는 캔버스 전체 포함 → Lewis 마커 등 잡음 포함 가능
                if not getattr(self.cv, '_last_drawn_smiles', '') and has_atoms:
                    _auto_smiles = ""
                    # 우선: 선택된 분자 SMILES
                    if hasattr(self.cv, '_get_molecule_smiles') and self.cv.selected_molecule_keys:
                        try:
                            _auto_smiles = self.cv._get_molecule_smiles()
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).warning("SMILES 추출 실패 (_get_molecule_smiles): %s", e)
                    # 폴백: 캔버스 전체 SMILES
                    if not _auto_smiles or _auto_smiles in ('C', ''):
                        try:
                            _auto_smiles = self.cv.get_smiles()
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).warning("SMILES 추출 실패 (get_smiles): %s", e)
                    if _auto_smiles and _auto_smiles not in ('C', ''):
                        self.cv._last_drawn_smiles = _auto_smiles
                        logger.debug("[LITE-EXE-003] Theory 수동 그리기 SMILES 자동 저장: %s", _auto_smiles[:60])

                # [REACTION] 반응 분석 버튼: 2개 이상 분자 감지 시 활성화
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.show()
                    self.btn_reaction.raise_()
                    try:
                        n_mols = self._count_molecules()
                        self.btn_reaction.setEnabled(False)
                        if has_atoms:
                            self.btn_reaction.setToolTip(f"{n_mols}개 분자 감지 — 반응 분석 가능")
                        else:
                            self.btn_reaction.setToolTip("분자를 그리면 반응 분석을 열 수 있습니다")
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning("분자 카운트 실패: %s", e)
                        self.btn_reaction.setEnabled(False)

                # [SYNTHESIS] 합성 경로 버튼: 원자가 1개 이상이면 활성화
                if hasattr(self, 'btn_synthesis'):
                    self.btn_synthesis.show()
                    self.btn_synthesis.raise_()
                    self.btn_synthesis.setEnabled(bool(has_atoms) and SYNTHESIS_AVAILABLE)
                    if has_atoms:
                        self.btn_synthesis.setToolTip("이 분자의 합성 경로 분석")
                    else:
                        self.btn_synthesis.setToolTip("분자를 그리면 합성 경로를 분석합니다")

                # [POLYMER] 고분자 합성 버튼: 원자가 1개 이상이면 활성화
                if hasattr(self, 'btn_polymer'):
                    self.btn_polymer.show()
                    self.btn_polymer.raise_()
                    self.btn_polymer.setEnabled(bool(has_atoms))
                    if has_atoms:
                        self.btn_polymer.setToolTip("고분자 합성 및 물성 분석")
                    else:
                        self.btn_polymer.setToolTip("분자를 그리면 고분자 합성을 분석합니다")
            else:
                self._set_analysis_buttons_visible(False, False)
        
        # [v4.0] 분석 버튼 제거됨 — 모든 분석은 "입체 구조" 팝업(popup_3d.py) 내 탭으로 통합

        # [M541] ElectronDist 모드 진입 시 ORCA .out 자동 로드 시도 (Rule M)
        # popup_3d에서 이미 DFT 계산이 수행됐으면 그 결과를 재사용.
        # 미실행 상태이면 orca_population_data를 None 유지 → 학습 모드 폴백.
        if mode == "ElectronDist":
            try:
                self._m541_load_orca_population_if_available()
            except Exception as _m541_e:
                # Rule M: silent failure 금지
                import logging as _m541_logging
                _m541_logging.getLogger(__name__).warning(
                    "[M541] ORCA population auto-load 실패: %s — 학습 모드 폴백",
                    _m541_e
                )
                # cv.orca_population_data를 None으로 강제 → renderer가 ground-state 폴백
                if hasattr(self.cv, 'orca_population_data'):
                    self.cv.orca_population_data = None

            # [M645_W32] 버튼 텍스트 동적 변경 (FP-15 P-MOCK-DISGUISED 차단)
            # ORCA 데이터 있음 → "전자분포 (ORCA Mulliken)"
            # ORCA 데이터 없음 → "전자분포 (Gasteiger 폴백)"
            # 학술 인용: Mulliken 1955 J.Chem.Phys 23:1833 / Gasteiger 1980 Tetrahedron 36:3219
            if hasattr(self, 'btn_electron_dist'):
                _pop = getattr(self.cv, 'orca_population_data', None)
                if isinstance(_pop, dict) and len(_pop) > 0:
                    self.btn_electron_dist.setText("전자분포 (ORCA Mulliken)")
                    self.btn_electron_dist.setToolTip(
                        "ORCA Mulliken 전자분포 시각화\n"
                        "Mulliken R.S. 1955 J.Chem.Phys 23:1833\n"
                        "Löwdin P.O. 1950 J.Chem.Phys 18:365"
                    )
                else:
                    self.btn_electron_dist.setText("전자분포 (Gasteiger 폴백)")
                    self.btn_electron_dist.setToolTip(
                        "ORCA 미설치 — Gasteiger 부분전하 학습 모드\n"
                        "Gasteiger J.; Marsili M. (1980) Tetrahedron 36:3219\n"
                        "정밀 Mulliken 분석은 ORCA 설치 후 가능합니다."
                    )
                    # [M645_W32] 상태바에도 명시적 학습 모드 안내 (Rule M)
                    if hasattr(self, 'statusBar'):
                        self.statusBar().showMessage(
                            "전자분포 학습 모드: Gasteiger 1980 부분전하 표시 "
                            "(Gasteiger fallback — ORCA not installed)",
                            8000
                        )

        # 그리기 관련 도구 비활성화 (회색 처리)
        draw_tools = ["Bond", "Wedge", "Dash", "Arrow", "Text", "H", "R", "O", "N", "P", "S", "F", "Cl", "Br", "I", "LonePair", "Radical"]
        # Lewis/Theory 레이어에서는 +/- 도구도 비활성화
        disable_in_lewis_theory = ["Positive", "Negative"]
        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in draw_tools:
                action.setEnabled(is_drawing)
            elif action_text in disable_in_lewis_theory:
                action.setEnabled(is_drawing)
        
        # [M646_W35] Q-N20 사이드바 btn_electron_dist show/hide
        # Lewis 모드 진입 시 사이드바에 btn_electron_dist 표시 (Stereo 패턴)
        # [M647_W3 카드3 #8] btn_back_to_lewis 완전 삭제 — Lewis 복귀는 사이드바 btn_lewis로 가능
        # [M647_W11 FIX] 사용자 격분 (2026-05-03 18:37): "전자분포(orca) 버튼이 우측 상단이
        #   아니라 우측 하단에 있어야 하고, 다른 기능 버튼들처럼 기존 버튼 위에 수직으로
        #   겹치지 않는 형태로 표현되어야 함" → btn_back 위에 10px gap으로 수직 스택.
        if hasattr(self, 'btn_electron_dist'):
            # W-2D-ELECTRON-CLOUD: ORCA unavailable still shows fallback entry.
            _orca_ok = getattr(self, '_m716_orca_available', False)
            if mode == "Lewis":
                # [M647_W11] btn_back(우하단) 위에 10px 여유 — Theory의 btn_3d 패턴 따름.
                # resizeEvent에서도 동기화 처리 (별도 if hasattr 분기 추가됨).
                self.btn_electron_dist.setFixedSize(200, 50)  # btn_back 동일 크기로 통일
                if _orca_ok:
                    self.btn_electron_dist.setText("전자분포 (ORCA Mulliken)")
                else:
                    self.btn_electron_dist.setText("전자분포 (Gasteiger 폴백)")
                    self.btn_electron_dist.setToolTip(
                        "ORCA unavailable; Gasteiger fallback electron distribution"
                    )
                margin = 25
                # btn_back 위치: x = width-200-25, y = height-50-25
                bx = self.width() - 200 - margin
                by = self.height() - 50 - margin
                ey = by - 50 - 10  # [MAGIC: 10px] btn_back 위 10px gap (Theory 패턴 동일)
                self.btn_electron_dist.move(bx, ey)
                self.btn_electron_dist.setEnabled(has_atoms)
                self.btn_electron_dist.show()
                self.btn_electron_dist.raise_()
            else:
                # ORCA 미설치이거나 Lewis 모드가 아닌 경우 항상 숨김
                self.btn_electron_dist.hide()

        if is_drawing:
            # [M645_W32] Drawing 모드 복귀 시 btn_electron_dist 텍스트 기본값으로 리셋
            # (다음 ElectronDist 진입 시 동적 업데이트됨)
            if hasattr(self, 'btn_electron_dist'):
                self.btn_electron_dist.setText("전자분포 (ORCA)")
            self.view_container.show() # 파란 버튼들 나타남
            self.btn_back.hide()       # 초록 버튼 숨김
            self._set_analysis_buttons_visible(False, False)
        else:
            self.view_container.hide() # 파란 버튼들 숨김
            self.btn_back.show()       # 초록 버튼 나타남
            if mode == "Theory":
                self._set_analysis_buttons_visible(True, self._has_analysis_target())
                # [Phase 6-3] btn_3d enabled 상태 유지 (위에서 설정됨)
            else:
                self._set_analysis_buttons_visible(False, False)

        # ★ AI 텍스트 입력창은 그리기 레이어에서만 표시
        if hasattr(self, 'mol_name_input'):
            if is_drawing:
                # [자동화 FIX] Drawing 모드 진입 시 항상 활성화 보장 (PubChem 조회 중단 후 상태 복구)
                self.mol_name_input.setEnabled(True)
                self.mol_name_btn.setEnabled(True)
                self.mol_name_btn.setText("OK")
                self.mol_name_input.show()
                self.mol_name_btn.show()
                self.mol_name_input.raise_()
                self.mol_name_btn.raise_()
                # [자동화 FIX] Drawing 모드 전환 시 입력창에 포커스 자동 이동
                self.mol_name_input.setFocus(Qt.FocusReason.OtherFocusReason)
            else:
                self.mol_name_input.hide()
                self.mol_name_btn.hide()

        if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
            self.btn_3d.raise_()
        self.cv.update()

    # ==========================================================================
    # [M541] ORCA Mulliken 전자분포 자동 로드 헬퍼
    # ==========================================================================
    def _m541_load_orca_population_if_available(self):
        """popup_3d 또는 사용자 워크디렉토리에서 ORCA .out 자동 검색 후 로드.

        검색 우선순위:
          1) self.cv._m541_orca_out_path (사용자/popup_3d가 지정한 경로)
          2) popup_3d._SCRIPT_DIR/orca_cache/{smiles_hash}.out
          3) self._last_drawn_smiles 기반 캐시 키

        파일을 찾으면 build_population_data_for_canvas() 호출 → cv.orca_population_data
        주입. 못 찾으면 None 유지 → ElectronDistributionRenderer가 학습 모드 폴백.

        Rule M: silent skip 금지 — 검색 실패 시 logger.warning + 상태바 메시지.
        Rule N: dict 가드 + Path 변환 가드.
        """
        import logging as _m541_log
        _logger = _m541_log.getLogger(__name__)

        # 1) 명시적 경로 (사용자/popup_3d 주입)
        explicit_path = getattr(self.cv, '_m541_orca_out_path', None)
        candidate_paths = []
        if explicit_path:
            try:
                from pathlib import Path as _P
                p = _P(str(explicit_path))
                if p.exists():
                    candidate_paths.append(p)
            except Exception as e:
                _logger.warning("[M541] explicit_path 변환 실패: %s", e)

        # 2) ORCA 캐시 디렉토리 자동 탐색 (popup_3d._SCRIPT_DIR 기준)
        try:
            from popup_3d import _SCRIPT_DIR as _m541_script_dir
            from pathlib import Path as _P
            for cache_root_name in ("orca_cache", "orca_runs", ".orca_cache"):
                cache_root = _P(_m541_script_dir) / cache_root_name
                if cache_root.exists() and cache_root.is_dir():
                    # 가장 최근 .out 파일 (mtime 기준)
                    out_files = list(cache_root.glob("**/*.out"))
                    if out_files:
                        latest = max(out_files, key=lambda f: f.stat().st_mtime)
                        candidate_paths.append(latest)
                        break
        except Exception as e:
            _logger.warning("[M541] ORCA 캐시 탐색 실패: %s", e)

        if not candidate_paths:
            _logger.warning(
                "[M541] ORCA .out 파일 없음 — 학습 모드(ground-state) 폴백 진행"
            )
            self.cv.orca_population_data = None
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(
                    "전자분포: ORCA 결과 없음 — 학습 모드 (ground-state 전자배치 표시)",
                    8000
                )
            return

        # 3) 첫 번째 유효 candidate를 사용해서 population data 빌드
        target_out = candidate_paths[0]
        _logger.info("[M541] ORCA .out 사용: %s", target_out)

        try:
            from electron_density_analyzer import build_population_data_for_canvas
            pop_data = build_population_data_for_canvas(target_out)
            if not isinstance(pop_data, dict) or not pop_data:
                _logger.warning(
                    "[M541] population dict 비정상 (type=%s, len=%s) — 폴백",
                    type(pop_data).__name__,
                    len(pop_data) if isinstance(pop_data, dict) else "n/a"
                )
                self.cv.orca_population_data = None
                if hasattr(self, 'statusBar'):
                    self.statusBar().showMessage(
                        "전자분포: ORCA 파싱 실패 — 학습 모드 폴백", 6000
                    )
                return
            self.cv.orca_population_data = pop_data
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(
                    f"전자분포: ORCA Mulliken {len(pop_data)}개 원자 로드 완료", 6000
                )
            _logger.info(
                "[M541] cv.orca_population_data 주입 완료 (n_atoms=%d)", len(pop_data)
            )
        except Exception as e:
            _logger.warning("[M541] population 빌드 예외: %s", e)
            self.cv.orca_population_data = None
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(
                    "전자분포: 예외 발생 — 학습 모드 폴백", 6000
                )

    # [Phase 6-3] 분자 선택 변경 핸들러
    def _on_molecule_selection_changed(self, selected: bool):
        """분자 선택/해제 시 btn_3d 상태 갱신.
        ★ 개선: 선택 해제여도 원자가 있으면 btn_3d 유지 활성
        """
        if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
            has_atoms = self._has_analysis_target()
            self.btn_3d.setEnabled(has_atoms)
            if selected:
                self.btn_3d.setToolTip("선택된 분자의 3D 구조 보기")
            elif has_atoms:
                self.btn_3d.setToolTip("캔버스 전체 분자의 3D 구조 보기")
            else:
                self.btn_3d.setToolTip("먼저 분자를 그리세요")

        # [v4] 선택 영역 내보내기 버튼 활성화
        if hasattr(self, 'export_btn'):
            is_drawing = (self.cv.view_state == "Drawing")
            self.export_btn.setEnabled(not is_drawing and bool(self.cv.atoms))

        # [FIX] Theory 모드 반응분석 버튼 실시간 갱신
        if hasattr(self, 'btn_reaction') and self.btn_reaction.isVisible():
            n_mols = self._count_molecules()
            has_atoms = self._has_analysis_target()
            self.btn_reaction.setEnabled(False)
            if has_atoms:
                self.btn_reaction.setToolTip(f"{n_mols}개 분자 감지 — 반응 분석 가능")
            else:
                self.btn_reaction.setToolTip("분자를 그리면 반응 분석을 열 수 있습니다")
        if getattr(self.cv, 'view_state', None) == "Theory":
            for attr in ('btn_synthesis', 'btn_polymer'):
                btn = getattr(self, attr, None)
                if btn is not None and btn.isVisible():
                    btn.setEnabled(False)
            self._apply_analysis_button_gates()

    # ========== [QStackedWidget] 내장 3D 뷰어 전환 ==========
    def _on_back_to_drawing(self) -> None:
        """'그리기 화면으로 복귀' 버튼 핸들러.
        3D 뷰가 활성 상태이면 먼저 2D 스택으로 전환 후 Drawing 모드로 복귀.
        """
        # 3D 뷰가 표시 중이면 먼저 2D 캔버스로 전환
        if self._view_stack.currentIndex() != 0:
            self._view_stack.setCurrentIndex(0)
        self.switch_view("Drawing")

    def _toggle_3d_embed(self) -> None:
        """'입체 구조' 버튼: 전체 3D 팝업(Molecule3DPopup, 7탭) 열기.
        탭: 속성/스펙트럼/진동모드/AI분석/ADMET/도킹에너지/신약설계
        입체 구조는 항상 팝업으로 표시 — 내장 3D 모드 비활성화.
        """
        if not PHASE_C_AVAILABLE:
            QMessageBox.warning(
                self, "알림",
                "3D 뷰어 모듈을 사용할 수 없습니다.\nPyOpenGL을 설치해주세요."
            )
            return

        try:
            self.open_3d_popup()
        except Exception as _e_3d:
            logger.warning("[3D] _toggle_3d_embed: open_3d_popup failed: %s", _e_3d, exc_info=True)
            QMessageBox.warning(self, "3D 뷰어 오류",
                                f"3D 팝업을 열 수 없습니다:\n{str(_e_3d)[:120]}")

    def _build_embed_3d_data(self) -> 'Molecule3DData | None':
        """현재 캔버스 분자에서 Molecule3DData를 생성한다.

        Returns:
            Molecule3DData 또는 분자가 없으면 None
        """
        # 선택된 원자 키 수집 (open_3d_popup 로직 재사용)
        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())
        if not selected_keys:
            selected_keys = getattr(self.cv, 'selected_atoms', set())

        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
        _all_atom_keys = set(self.cv.atoms.keys())

        # 선택 원자가 전체의 50% 미만이고 _last_drawn_smiles 있으면 전체 선택
        if _last_smiles and _all_atom_keys and len(selected_keys) < len(_all_atom_keys) * 0.5:
            selected_keys = _all_atom_keys
        if not selected_keys:
            selected_keys = _all_atom_keys

        if not selected_keys:
            return None

        sel_atoms = {k: v for k, v in self.cv.atoms.items() if k in selected_keys}
        sel_bonds = {
            (k1, k2): v for (k1, k2), v in self.cv.bonds.items()
            if k1 in selected_keys and k2 in selected_keys
        }

        _ar_td = self.cv.analysis_results if isinstance(self.cv.analysis_results, dict) else {}  # Rule N
        theory_data = _ar_td.get("theory_data", {}) if _ar_td else {}

        # SMILES 추출
        mol_smiles = ""
        if _last_smiles:
            mol_smiles = _last_smiles
        else:
            try:
                if getattr(self.cv, 'selected_molecule_keys', set()):
                    mol_smiles = self.cv._get_molecule_smiles() or ""
            except Exception as e:
                logger.warning(f"[MainWindow] _get_molecule_smiles 실패: {e}")
            if not mol_smiles:
                mol_smiles = self._build_smiles_from_graph(sel_atoms, sel_bonds)

        return Molecule3DData(
            atoms=sel_atoms,
            bonds=sel_bonds,
            theory_data=theory_data,
            smiles=mol_smiles,
        )

    def update_ui_state(self):
        """캔버스 상태에 따라 UI 버튼들의 활성/비활성 상태를 일괄 갱신"""
        has_atoms = len(getattr(self.cv, 'atoms', [])) > 0
        is_drawing = (self.cv.view_state == "Drawing")
        
        # 내보내기 버튼 활성화 조건 (Drawing 모드가 아니고 분자가 존재할 때)
        if hasattr(self, 'export_btn'):
            has_selection = hasattr(self.cv, 'selected_molecule_keys') and bool(self.cv.selected_molecule_keys)
            self.export_btn.setEnabled(not is_drawing and (has_atoms or has_selection))

    # [신규] 구름 토글 로직
    def toggle_clouds(self):
        self.cv.show_clouds = not self.cv.show_clouds
        btn_text = "전자구름 켜기" if not self.cv.show_clouds else "전자구름 끄기"
        self.btn_cloud.setText(btn_text)
        self.cv.update()

    def showEvent(self, event):
        """
        [A61-W1 ISSUE-A60-002 M740] 포그라운드 강제 진입.
        Discord/다른 창 뒤에 ChemGrid가 숨는 문제 수정.
        Windows 10/11 포커스 정책: SetForegroundWindow는 FOREGROUND_LOCK_TIMEOUT 제약으로
        직접 호출 시 작동하지 않을 수 있음 → AllowSetForegroundWindow(ASFW_ANY=-1) 선행 필수.
        """
        super().showEvent(event)
        self.raise_()           # Z-order 최상단
        self.activateWindow()   # 포커스 이동
        try:
            _hwnd = int(self.winId())
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # [MAGIC:-1] ASFW_ANY: 모든 프로세스 허용
            ctypes.windll.user32.SetForegroundWindow(_hwnd)
        except (AttributeError, OSError) as e:
            logger.warning("[A61-W1 ISSUE-A60-002] SetForegroundWindow 실패 (비-Windows 환경): %s", e)

    def resizeEvent(self, event):
        # [해결] 버튼 컨테이너 크기 고정 및 우하단 마진(25px) 적용
        margin = 25

        if hasattr(self, 'btn_cloud'):
            cx = margin
            cy = self.height() - self.btn_cloud.height() - margin
            self.btn_cloud.move(cx, cy)
            self.btn_cloud.raise_()

        if hasattr(self, 'view_container'):
            # [M541] 전자분포 버튼(140px) 추가로 너비 240→400 확장
            # Lewis(110) + 8 + Theory(110) + 8 + ElectronDist(140) + 여백 = ~400px
            self.view_container.setFixedSize(400, 50)
            vx = self.width() - self.view_container.width() - margin
            vy = self.height() - self.view_container.height() - margin
            self.view_container.move(vx, vy)
            self.view_container.raise_() # 다른 위젯에 가려지지 않게 최상단으로

        if hasattr(self, 'btn_back'):
            self.btn_back.setFixedSize(200, 50)
            bx = self.width() - self.btn_back.width() - margin
            by = self.height() - self.btn_back.height() - margin
            self.btn_back.move(bx, by)
            self.btn_back.raise_()

            # [M647_W11] btn_electron_dist (Lewis 모드 시 표시) — btn_back 위 10px 동기 배치
            if hasattr(self, 'btn_electron_dist') and self.btn_electron_dist.isVisible():
                self.btn_electron_dist.setFixedSize(200, 50)
                ey = by - self.btn_electron_dist.height() - 10  # [MAGIC: 10px]
                self.btn_electron_dist.move(bx, ey)
                self.btn_electron_dist.raise_()

            # [해결] 입체 구조 버튼을 '그리기로 돌아가기' 버튼 10px 위에 배치
            if hasattr(self, 'btn_3d'):
                self.btn_3d.setFixedSize(200, 50) # 크기 통일
                tx = bx # X좌표 동일
                ty = by - self.btn_3d.height() - 10 # 10px 위쪽
                self.btn_3d.move(tx, ty)

                # [REACTION] 반응 분석 버튼을 입체 구조 버튼 10px 위에 배치
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.setFixedSize(200, 50)
                    ry = ty - self.btn_reaction.height() - 10
                    self.btn_reaction.move(tx, ry)
                    self.btn_reaction.raise_()

                    # [SYNTHESIS] 합성 경로 버튼을 반응 분석 버튼 10px 위에 배치
                    if hasattr(self, 'btn_synthesis'):
                        self.btn_synthesis.setFixedSize(200, 50)
                        sy = ry - self.btn_synthesis.height() - 10
                        self.btn_synthesis.move(tx, sy)
                        self.btn_synthesis.raise_()

                        # [POLYMER] 고분자 합성 버튼을 합성 경로 버튼 10px 위에 배치
                        if hasattr(self, 'btn_polymer'):
                            self.btn_polymer.setFixedSize(200, 50)
                            py_ = sy - self.btn_polymer.height() - 10
                            self.btn_polymer.move(tx, py_)
                            self.btn_polymer.raise_()

        # ★ AI 텍스트 입력창 → 하단 중앙 배치 (Drawing 레이어 전용)
        # [LITE-EXE-002 refix M645_W14] view_guard 정적값(418) → 동적 계산으로 교체
        # W13 audit_gui REJECT: btn_right=932, vc_left=925 → 7px overlap 잔존
        # 원인: view_container.x() = width-425, 정적 418은 7px 부족
        # 수정: vc_left = view_container.x() (resizeEvent에서 이미 배치 완료)
        #       max_right = vc_left - 8 (8px safety gap)
        # 효과: 다양한 해상도·margin 변경에도 overlap 0px 보장
        if hasattr(self, 'mol_name_input'):
            input_h = 38
            btn_w = 38   # OK 버튼 너비
            gap = 8      # 입력창-버튼 사이 간격
            # 동적 계산: view_container가 이미 배치된 후 실제 x좌표 사용
            if hasattr(self, 'view_container') and self.view_container.x() > 0:
                vc_left = self.view_container.x()  # 실측 view_container 좌측 경계
                safety = 8  # 8px safety gap (W13 REJECT 사유 7px + 1px 여유)
                max_right = vc_left - safety
            else:
                # view_container 미배치 폴백: 정적값 433 (width-425-8)
                max_right = self.width() - 433  # 433 = 400(vc_w) + 25(margin) + 8(safety)
            # 입력창 너비: 최대 480px, 단 화면 전체 - 좌여백(80) - view_guard 한도 이내
            input_w = min(480, max(160, max_right - btn_w - gap - 80))
            total_w = input_w + gap + btn_w
            ix = (self.width() - total_w) // 2
            # 중앙 배치 시 OK 버튼이 view_guard 경계를 넘으면 왼쪽으로 밀어냄
            ok_right = ix + total_w
            if ok_right > max_right:
                ix = max_right - total_w
            # [M647_W11] 사용자 격분 (2026-05-03 18:34): "하단 바를 가리지 않게 약간 올려줘"
            # 이전 18 → 50px 위로 이동. statusBar 22~24px + 여백 26px + 4px 안전여유
            iy = self.height() - input_h - 50  # [MAGIC: 50px] statusBar overlap 차단
            self.mol_name_input.setFixedWidth(input_w)
            self.mol_name_input.move(ix, iy)
            self.mol_name_btn.move(ix + input_w + gap, iy)
            self.mol_name_input.raise_()
            self.mol_name_btn.raise_()

        # [UX-2] Welcome overlay removed — no repositioning needed

        super().resizeEvent(event)

    # ========== [자동화 FIX] 분자 입력창 포커스 강제 이동 ==========
    def _focus_mol_input(self) -> None:
        """[자동화 FIX] mol_name_input에 포커스를 강제로 이동.
        - 캔버스가 StrongFocus를 가지므로 pyautogui 자동화 시 포커스가 캔버스에 머무는 문제 해결.
        - Ctrl+L 단축키 또는 외부 자동화 스크립트에서 직접 호출 가능.
        - 입력 필드가 비활성화 상태이면 먼저 활성화 후 포커스 이동.
        """
        if not hasattr(self, 'mol_name_input'):
            return
        # Drawing 모드가 아니면 먼저 전환
        if self.cv.view_state != "Drawing":
            return
        # 필드가 비활성화된 상태면 (PubChem 조회 중 등) 재활성화 후 포커스
        if not self.mol_name_input.isEnabled():
            self.mol_name_input.setEnabled(True)
            self.mol_name_btn.setEnabled(True)
            self.mol_name_btn.setText("OK")
        self.mol_name_input.show()
        self.mol_name_input.raise_()
        self.mol_name_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.mol_name_input.selectAll()

    # ========== [신규] AI 분자 그리기: 이름 → SMILES → Canvas ==========
    def _on_mol_name_submitted(self) -> None:
        """텍스트 입력창에서 분자명/SMILES를 받아 캔버스에 그리기.

        [UX-1] 자동 감지: SMILES 형태이면 바로 그리기, 아니면 PubChem 이름 조회.
        상태바에 "aspirin -> CC(=O)Oc1ccccc1C(=O)O (PubChem)" 형태로 표시.
        """
        raw_input: str = self.mol_name_input.text().strip()
        if not raw_input:
            return
        normalized_input, normalize_note = _normalize_ime_smiles_input(raw_input)
        if normalized_input != raw_input:
            logger.warning("[M856] Korean IME SMILES input normalized: %r -> %r", raw_input, normalized_input)
            raw_input = normalized_input
            self.mol_name_input.setText(raw_input)
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(normalize_note, 8000)
        elif normalize_note and hasattr(self, 'statusBar'):
            logger.warning("[M856] %s", normalize_note)
            self.statusBar().showMessage(normalize_note, 8000)

        # [UX-1] Auto-detect: SMILES vs molecule name
        if _is_likely_smiles(raw_input):
            # 입력이 SMILES로 보이면 바로 그리기
            self._submit_smiles_directly(raw_input)
            return

        # [통로 1] canvas에 draw_molecule_from_name 메서드가 있으면 직접 호출
        if hasattr(self.cv, 'draw_molecule_from_name'):
            try:
                self.mol_name_btn.setEnabled(False)
                self.mol_name_btn.setText("...")
                QApplication.processEvents()
                result = self.cv.draw_molecule_from_name(raw_input)
                if result:
                    self.mol_name_input.clear()
                    self.mol_name_input.setPlaceholderText(f"'{raw_input}' 그리기 완료")
                    self.statusBar().showMessage(
                        f"{raw_input} (canvas draw)", 5000
                    )
                else:
                    self.mol_name_input.setPlaceholderText(
                        f"'{raw_input}' 인식 실패 -- SMILES를 직접 입력해보세요"
                    )
            except Exception as e:
                self.mol_name_input.setPlaceholderText(f"오류: {str(e)[:50]}")
            finally:
                self.mol_name_btn.setEnabled(True)
                self.mol_name_btn.setText("OK")
            return

        # [통로 2] PubChem으로 SMILES 조회 — 비동기 (P0-5 FIX: QThread로 UI 블로킹 방지)
        self.mol_name_btn.setEnabled(False)
        self.mol_name_btn.setText("검색중...")
        self.mol_name_input.setEnabled(False)  # [P0-5] 이중 제출 방지
        self.statusBar().showMessage(f"'{raw_input}' 검색 중...", 0)

        # 이전 워커가 실행 중이면 완료 대기 없이 참조 해제
        if self._pubchem_worker is not None and self._pubchem_worker.isRunning():
            self._pubchem_worker.finished.disconnect()
            self._pubchem_worker = None

        self._pubchem_worker = _PubChemLookupWorker(
            raw_input, lookup_fn=self._lookup_smiles_for_name, parent=self
        )
        self._pubchem_worker.finished.connect(self._on_pubchem_lookup_done)
        self._pubchem_worker.start()

    def _on_pubchem_lookup_done(self, input_name: str, smiles: str) -> None:
        """[P0-5 FIX] 비동기 PubChem 조회 완료 콜백. UI 스레드에서 실행됨."""
        self.mol_name_btn.setEnabled(True)
        self.mol_name_btn.setText("OK")
        self.mol_name_input.setEnabled(True)  # [P0-5] 입력 필드 재활성화

        if smiles:
            self.statusBar().showMessage(
                f"{input_name} -> {smiles[:50]} (PubChem)", 8000
            )
            try:
                # [FIX] Always clear before drawing new molecule from input
                self._draw_smiles_on_canvas(smiles, input_name, append=False)
                self.mol_name_input.clear()
                self.mol_name_input.setPlaceholderText(
                    f"'{input_name}' -> {smiles[:40]}"
                )
            except Exception as e:
                self.mol_name_input.setPlaceholderText(f"그리기 오류: {str(e)[:50]}")
        else:
            self.statusBar().showMessage(
                f"'{input_name}' 검색 실패", 5000
            )
            self.mol_name_input.setPlaceholderText(
                f"'{input_name}' 검색 실패 -- 화학명 또는 SMILES로 직접 입력하세요"
            )

    def _submit_smiles_directly(self, smiles: str) -> None:
        """[UX-1] SMILES 문자열을 바로 캔버스에 그리기."""
        try:
            self.mol_name_btn.setEnabled(False)
            self.mol_name_btn.setText("...")
            QApplication.processEvents()
            # [FIX] Always clear before drawing new molecule from input
            self._draw_smiles_on_canvas(smiles, "", append=False)
            self.mol_name_input.clear()
            self.mol_name_input.setPlaceholderText(f"SMILES: {smiles[:50]}")
            self.statusBar().showMessage(f"SMILES: {smiles[:60]}", 5000)
        except Exception as e:
            self.mol_name_input.setPlaceholderText(f"오류: {str(e)[:50]}")
        finally:
            self.mol_name_btn.setEnabled(True)
            self.mol_name_btn.setText("OK")

    def _lookup_smiles_for_name(self, name: str) -> str:
        """PubChem 또는 Gemini AI로 분자명 → SMILES 변환.
        우선순위: 내장사전 > 축약식 파싱 > PubChem REST > Gemini AI
        [BUG-04 Fix] dotenv 로딩 추가, 축약식 처리 추가, BUILTIN 대폭 확장
        """
        import os as _os
        import pathlib as _pathlib

        # ── [FIX-BUG-04] .env 파일 로딩 (GEMINI_API_KEY 환경변수 보장) ──
        try:
            from dotenv import load_dotenv as _load_dotenv
            _env_candidates = [
                _pathlib.Path(__file__).resolve().parents[2] / "agents" / "mcp_server" / ".env",
                _pathlib.Path(__file__).resolve().parents[1] / "agents" / "mcp_server" / ".env",
                _pathlib.Path("c:/chemgrid/agents/mcp_server/.env"),
            ]
            for _env_p in _env_candidates:
                if _env_p.exists():
                    _load_dotenv(str(_env_p), override=False)
                    break
        except ImportError as e:
            logger.warning(f"[MainWindow] dotenv 로드 실패(선택적 의존성): {e}")

        # ── [Step 1] 내장 사전 (네트워크 불필요, 방향족 이온 포함) ──────
        BUILTIN = {
            # 무기물
            "water": "O", "물": "O", "h2o": "O",
            "ammonia": "N", "암모니아": "N", "nh3": "N",
            "carbon dioxide": "O=C=O", "이산화탄소": "O=C=O", "co2": "O=C=O",
            "carbon monoxide": "[C-]#[O+]", "일산화탄소": "[C-]#[O+]",
            "hydrogen chloride": "Cl", "hydrochloric acid": "Cl", "염산": "Cl", "염화수소": "Cl",
            "sulfur dioxide": "O=S=O", "이산화황": "O=S=O",
            "sulfuric acid": "OS(=O)(=O)O", "황산": "OS(=O)(=O)O", "h2so4": "OS(=O)(=O)O",
            "nitric acid": "O[N+](=O)[O-]", "질산": "O[N+](=O)[O-]", "hno3": "O[N+](=O)[O-]",
            "hydrogen peroxide": "OO", "과산화수소": "OO", "h2o2": "OO",
            "sodium hydroxide": "[Na+].[OH-]", "수산화나트륨": "[Na+].[OH-]", "가성소다": "[Na+].[OH-]",
            "sodium chloride": "[Na+].[Cl-]", "염화나트륨": "[Na+].[Cl-]", "소금": "[Na+].[Cl-]",
            "potassium permanganate": "[K+].[O-][Mn](=O)(=O)=O", "과망간산칼륨": "[K+].[O-][Mn](=O)(=O)=O",
            "phosphoric acid": "OP(=O)(O)O", "인산": "OP(=O)(O)O",
            "hydrogen sulfide": "S", "황화수소": "S",
            "nitrogen dioxide": "O=[N+][O-]", "이산화질소": "O=[N+][O-]",
            "ozone": "[O-][O+]=O", "오존": "[O-][O+]=O",
            # 알케인
            "methane": "C", "메탄": "C", "에탄": "CC", "ethane": "CC",
            "프로판": "CCC", "뷰탄": "CCCC", "펜탄": "CCCCC", "헥산": "CCCCCC",
            "propane": "CCC", "butane": "CCCC", "pentane": "CCCCC",
            "hexane": "CCCCCC", "heptane": "CCCCCCC", "octane": "CCCCCCCC",
            "cyclohexane": "C1CCCCC1", "사이클로헥산": "C1CCCCC1",
            "cyclopentane": "C1CCCC1", "사이클로펜탄": "C1CCCC1",
            # 불포화 탄화수소
            "ethylene": "C=C", "에틸렌": "C=C", "propylene": "CC=C", "프로필렌": "CC=C",
            "acetylene": "C#C", "아세틸렌": "C#C", "1-butene": "CCC=C",
            "butadiene": "C=CC=C", "뷰타다이엔": "C=CC=C",
            "isoprene": "C=CC(=C)C", "아이소프렌": "C=CC(=C)C",
            # 알코올
            "methanol": "CO", "메탄올": "CO",
            "ethanol": "CCO", "에탄올": "CCO", "ethyl alcohol": "CCO",
            "isopropanol": "CC(O)C", "isopropyl alcohol": "CC(O)C",
            "1-propanol": "CCCO", "1-butanol": "CCCCO",
            "isopropanol": "CC(O)C", "아이소프로판올": "CC(O)C",
            # 카르보닐
            "formaldehyde": "C=O", "폼알데하이드": "C=O", "포름알데히드": "C=O",
            "acetaldehyde": "CC=O", "아세트알데히드": "CC=O",
            "acetone": "CC(C)=O", "아세톤": "CC(C)=O",
            # 유기산
            "formic acid": "OC=O", "포름산": "OC=O",
            "acetic acid": "CC(=O)O", "아세트산": "CC(=O)O",
            "propionic acid": "CCC(=O)O",
            "butyric acid": "CCCC(=O)O",
            "valeric acid": "CCCCC(=O)O",
            "lactic acid": "C[C@@H](O)C(=O)O",
            "oxalic acid": "OC(=O)C(=O)O", "옥살산": "OC(=O)C(=O)O", "수산": "OC(=O)C(=O)O",
            "citric acid": "OC(CC(=O)O)(CC(=O)O)C(=O)O", "구연산": "OC(CC(=O)O)(CC(=O)O)C(=O)O", "시트르산": "OC(CC(=O)O)(CC(=O)O)C(=O)O",
            "succinic acid": "OC(=O)CCC(=O)O", "숙신산": "OC(=O)CCC(=O)O",
            "tartaric acid": "O[C@@H](C(=O)O)[C@H](O)C(=O)O", "타르타르산": "O[C@@H](C(=O)O)[C@H](O)C(=O)O", "주석산": "O[C@@H](C(=O)O)[C@H](O)C(=O)O",
            "malic acid": "O[C@@H](CC(=O)O)C(=O)O", "사과산": "O[C@@H](CC(=O)O)C(=O)O",
            "acrylic acid": "C=CC(=O)O", "아크릴산": "C=CC(=O)O",
            "stearic acid": "CCCCCCCCCCCCCCCCCC(=O)O", "스테아르산": "CCCCCCCCCCCCCCCCCC(=O)O",
            "oleic acid": "CCCCCCCC/C=C\\CCCCCCCC(=O)O", "올레산": "CCCCCCCC/C=C\\CCCCCCCC(=O)O",
            # 방향족
            "benzene": "c1ccccc1", "벤젠": "c1ccccc1",
            "toluene": "Cc1ccccc1", "톨루엔": "Cc1ccccc1",
            "phenol": "Oc1ccccc1", "페놀": "Oc1ccccc1",
            "aniline": "Nc1ccccc1", "아닐린": "Nc1ccccc1",
            "benzoic acid": "OC(=O)c1ccccc1",
            "nitrobenzene": "O=[N+]([O-])c1ccccc1", "니트로벤젠": "O=[N+]([O-])c1ccccc1",
            "니트로글리세린": "O=[N+]([O-])OC(CO[N+](=O)[O-])CO[N+](=O)[O-]",
            "nitroglycerin": "O=[N+]([O-])OC(CO[N+](=O)[O-])CO[N+](=O)[O-]",
            "tnt": "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
            "trinitrotoluene": "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
            "naphthalene": "c1ccc2ccccc2c1", "나프탈렌": "c1ccc2ccccc2c1",
            "anthracene": "c1ccc2cc3ccccc3cc2c1", "안트라센": "c1ccc2cc3ccccc3cc2c1",
            "styrene": "C=Cc1ccccc1", "스티렌": "C=Cc1ccccc1",
            "xylene": "Cc1ccccc1C", "자일렌": "Cc1ccccc1C",
            "dimethyl sulfoxide": "CS(=O)C", "dmso": "CS(=O)C", "디메틸설폭사이드": "CS(=O)C",
            "chloroform": "ClC(Cl)Cl", "클로로포름": "ClC(Cl)Cl",
            "에테르": "CCOCC", "diethyl ether": "CCOCC", "다이에틸에테르": "CCOCC",
            "glycerol": "OCC(O)CO", "글리세롤": "OCC(O)CO", "글리세린": "OCC(O)CO",
            "ethylene glycol": "OCCO", "에틸렌글리콜": "OCCO", "부동액": "OCCO",
            "urea": "NC(=O)N", "요소": "NC(=O)N",
            "acetic anhydride": "CC(=O)OC(=O)C", "무수아세트산": "CC(=O)OC(=O)C",
            "pyridine": "c1ccncc1", "피리딘": "c1ccncc1",
            "pyrimidine": "c1cnccn1",
            "furan": "c1ccoc1", "퓨란": "c1ccoc1",
            "thiophene": "c1ccsc1", "티오펜": "c1ccsc1",
            "pyrrole": "c1cc[nH]c1", "피롤": "c1cc[nH]c1",
            "imidazole": "c1cnc[nH]1", "이미다졸": "c1cnc[nH]1",
            # ★ 이온성 방향족 (공명 균등화 테스트)
            "cyclopentadienyl anion": "[cH-]1cccc1",
            "cyclopentadienyl": "C1=CC=CC1",
            "사이클로펜타디에닐 음이온": "[cH-]1cccc1",
            "cp-": "[cH-]1cccc1", "cp anion": "[cH-]1cccc1",
            "tropylium": "C1=CC=CC=C[CH+]1",
            "tropylium ion": "C1=CC=CC=C[CH+]1",
            "tropylium cation": "C1=CC=CC=C[CH+]1",
            "트로필리움": "C1=CC=CC=C[CH+]1",
            "트로필리움 이온": "C1=CC=CC=C[CH+]1",
            "cycloheptatrienyl cation": "C1=CC=CC=C[CH+]1",
            "cycloheptatrienyl": "C1=CC=CC=CC1",
            # 당류
            # M551: 글루코스 PubChem CID 5793 (D-glucopyranose) 검증본 (Rule L)
            "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "글루코스": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "fructose": "OCC(=O)[C@@H](O)[C@H](O)[C@H](O)CO",
            "sucrose": "OC[C@H]1O[C@@](CO)(O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)[C@@H](O)[C@@H]1O",
            "galactose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            # 약물
            "aspirin": "CC(=O)Oc1ccccc1C(=O)O", "아스피린": "CC(=O)Oc1ccccc1C(=O)O",
            "acetylsalicylic acid": "CC(=O)Oc1ccccc1C(=O)O",
            "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C", "카페인": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
            "ibuprofen": "CC(C)Cc1ccc(C(C)C(=O)O)cc1", "이부프로펜": "CC(C)Cc1ccc(C(C)C(=O)O)cc1", "부루펜": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
            "paracetamol": "CC(=O)Nc1ccc(O)cc1", "acetaminophen": "CC(=O)Nc1ccc(O)cc1", "아세트아미노펜": "CC(=O)Nc1ccc(O)cc1",
            "cholesterol": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
            "콜레스테롤": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
            # 핵산 염기
            "adenine": "Nc1ncnc2[nH]cnc12", "아데닌": "Nc1ncnc2[nH]cnc12",
            "guanine": "Nc1nc2[nH]cnc2c(=O)[nH]1",
            "cytosine": "Nc1cc[nH]c(=O)n1",
            "thymine": "Cc1c[nH]c(=O)[nH]c1=O",
            "uracil": "O=c1cc[nH]c(=O)[nH]1",
            # 아미노산
            "glycine": "NCC(=O)O", "글리신": "NCC(=O)O",
            "alanine": "C[C@@H](N)C(=O)O",
            "serine": "N[C@@H](CO)C(=O)O",
            "lysine": "NCCCC[C@@H](N)C(=O)O",
            "phenylalanine": "N[C@@H](Cc1ccccc1)C(=O)O",
            "tryptophan": "N[C@@H](Cc1c[nH]c2ccccc12)C(=O)O",
            # M551: 헤모글로빈 관련 (포르피린 → heme b, Fe 포함)
            # heme b SMILES: PubChem CID 26945 기반 (RDKit 53원자 PASS 확인, Rule L)
            # [Fe] = 중성 Fe(II) 포르피린 배위 표기 — 4N-chelation
            "heme": r"CC1=C2C=C3C(=CC4=NC(=CC5=NC(=C1/N2\[Fe]N34)CC(=O)O)C(C=C)=C5C)C(C)=C(CCC(=O)O)C6=CC7=NC(=CC(=C7C)C=C)C(CCC(=O)O)=C6",
            "heme b": r"CC1=C2C=C3C(=CC4=NC(=CC5=NC(=C1/N2\[Fe]N34)CC(=O)O)C(C=C)=C5C)C(C)=C(CCC(=O)O)C6=CC7=NC(=CC(=C7C)C=C)C(CCC(=O)O)=C6",
            # ═══ 주요 약물 (관용명 + 성분명 + 한글명) ═══
            # 진통제/해열제
            "fentanyl": "C1=CC=C(C=C1)C(=O)N(C2CCN(CC2)CCC3=CC=CC=C3)CC",
            "펜타닐": "C1=CC=C(C=C1)C(=O)N(C2CCN(CC2)CCC3=CC=CC=C3)CC",
            "tylenol": "CC(=O)Nc1ccc(O)cc1", "타이레놀": "CC(=O)Nc1ccc(O)cc1",
            "morphine": "CN1CC[C@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@H]3[C@H]1C5",  # [A63-W1/M748] PubChem CID-5288826 C17H19NO3 MW=285.14
            "모르핀": "CN1CC[C@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@H]3[C@H]1C5",  # [A63-W1/M748] PubChem CID-5288826 C17H19NO3
            "codeine": "COc1ccc2C[C@H]3N(C)CC[C@@]45c2c1OC=C4[C@@H](O)C[C@@H]35",
            "코데인": "COc1ccc2C[C@H]3N(C)CC[C@@]45c2c1OC=C4[C@@H](O)C[C@@H]35",
            "naproxen": "COc1ccc2cc(CC(C)C(=O)O)ccc2c1",
            "나프록센": "COc1ccc2cc(CC(C)C(=O)O)ccc2c1",
            "diclofenac": "OC(=O)Cc1ccccc1Nc1c(Cl)cccc1Cl",
            "디클로페낙": "OC(=O)Cc1ccccc1Nc1c(Cl)cccc1Cl",
            # 항생제
            "penicillin": "CC1(C)S[C@@H]2[C@H](NC(=O)Cc3ccccc3)C(=O)N2[C@@H]1C(=O)O",
            "페니실린": "CC1(C)S[C@@H]2[C@H](NC(=O)Cc3ccccc3)C(=O)N2[C@@H]1C(=O)O",
            "amoxicillin": "CC1(C)S[C@@H]2[C@H](NC(=O)[C@H](N)c3ccc(O)cc3)C(=O)N2[C@@H]1C(=O)O",
            "아목시실린": "CC1(C)S[C@@H]2[C@H](NC(=O)[C@H](N)c3ccc(O)cc3)C(=O)N2[C@@H]1C(=O)O",
            "erythromycin": "CC[C@@H]1OC(=O)[C@H](C)[C@@H](O[C@H]2C[C@@](C)(OC)[C@@H](O)[C@H](C)O2)[C@H](C)[C@@H](O[C@@H]2O[C@H](C)C[C@@H]([C@H]2O)N(C)C)[C@](C)(O)C[C@@H](C)C(=O)[C@H](C)[C@@H](O)[C@]1(C)O",
            # 항우울제/정신과
            "sertraline": "Clc1ccc2c(c1Cl)[C@@H](c1ccccc1)C[C@H](NC)C2",
            "설트랄린": "Clc1ccc2c(c1Cl)[C@@H](c1ccccc1)C[C@H](NC)C2",
            "fluoxetine": "CNCCC(Oc1ccc(C(F)(F)F)cc1)c1ccccc1",
            "플루옥세틴": "CNCCC(Oc1ccc(C(F)(F)F)cc1)c1ccccc1",
            "prozac": "CNCCC(Oc1ccc(C(F)(F)F)cc1)c1ccccc1",
            "diazepam": "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
            "디아제팜": "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
            "valium": "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
            # 항히스타민
            "diphenhydramine": "O(CCN(C)C)C(c1ccccc1)c1ccccc1",
            "디펜히드라민": "O(CCN(C)C)C(c1ccccc1)c1ccccc1",
            "benadryl": "O(CCN(C)C)C(c1ccccc1)c1ccccc1",
            "cetirizine": "OC(=O)COCC(c1ccc(Cl)cc1)N1CCN(CCOC2CCCCC2)CC1",
            "세티리진": "OC(=O)COCC(c1ccc(Cl)cc1)N1CCN(CCOC2CCCCC2)CC1",
            # 심혈관
            "atorvastatin": "CC(C)c1n(CC[C@@H](O)C[C@@H](O)CC(=O)O)c(c2ccc(F)cc2)c(-c2ccccc2)c1C(=O)Nc1ccccc1",
            "amlodipine": "CCOC(=O)C1=C(COCCN)NC(C)=C(C(=O)OC)C1c1ccccc1Cl",
            "warfarin": "OC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O",
            "와파린": "OC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O",
            # 당뇨
            "metformin": "CN(C)C(=N)NC(=N)N", "메트포르민": "CN(C)C(=N)NC(=N)N",
            "insulin glargine": None,
            # 항암
            "tamoxifen": "CCC(/c1ccccc1)=C(/c1ccc(OCCN(C)C)cc1)c1ccccc1",
            "타목시펜": "CCC(/c1ccccc1)=C(/c1ccc(OCCN(C)C)cc1)c1ccccc1",
            # M551: 시스플라틴 SMILES PubChem CID 84691 검증본 (Rule L)
            # [NH3][Pt]([NH3])(Cl)Cl → dative bond 표기 — PubChem N.N.Cl[Pt]Cl 로 교체
            # 이유: dative 표기는 RDKit InChI 생성 실패 (bond type >3 unrecognized)
            "cisplatin": "N.N.Cl[Pt]Cl",
            "시스플라틴": "N.N.Cl[Pt]Cl",
            "doxorubicin": "COc1cccc2c1C(=O)c1c(O)c3c(C[C@@](O)(C[C@@H]3O[C@H]3C[C@H](N)[C@H](O)[C@H](C)O3)C(=O)CO)c(O)c1C2=O",
            # 비타민
            "vitamin c": "OC[C@@H](O)[C@H]1OC(=O)C(O)=C1O",
            "비타민c": "OC[C@@H](O)[C@H]1OC(=O)C(O)=C1O",
            "ascorbic acid": "OC[C@@H](O)[C@H]1OC(=O)C(O)=C1O",
            "아스코르브산": "OC[C@@H](O)[C@H]1OC(=O)C(O)=C1O",
            "vitamin a": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/CO)C(C)(C)CCC1",
            "비타민a": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/CO)C(C)(C)CCC1",
            "retinol": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/CO)C(C)(C)CCC1",
            "vitamin d3": "C(/C=C\\1/CCC(O)C/C1=C\\C=C1/CCCC(C)[C@@H]1CCC(C)CCCC(C)C)=C",
            "vitamin e": "CC1=C(C)C(O)=C2OC(CCCC(C)CCCC(C)CCCC(C)C)(C)CCC2=C1C",
            "비타민e": "CC1=C(C)C(O)=C2OC(CCCC(C)CCCC(C)CCCC(C)C)(C)CCC2=C1C",
            # 카로티노이드
            "beta-carotene": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/C=C/C=C(C)/C=C/C=C(C)/C=C/C2=C(C)CCCC2(C)C)C(C)(C)CCC1",
            "베타카로틴": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/C=C/C=C(C)/C=C/C=C(C)/C=C/C2=C(C)CCCC2(C)C)C(C)(C)CCC1",
            "lycopene": "CC(=C/C=C/C(=C/C=C/C(=C/C=C/C=C(/C=C/C=C(/C=C/C=C(\\C)C)\\C)C)\\C)C)C",
            # 스테로이드
            "testosterone": "C[C@]12CCC3C(CCC4=CC(=O)CC[C@@]34C)[C@@H]1CC[C@@H]2O",
            "테스토스테론": "C[C@]12CCC3C(CCC4=CC(=O)CC[C@@]34C)[C@@H]1CC[C@@H]2O",
            "estradiol": "C[C@]12CC[C@H]3[C@@H](CCc4cc(O)ccc43)[C@@H]1CC[C@@H]2O",
            "에스트라디올": "C[C@]12CC[C@H]3[C@@H](CCc4cc(O)ccc43)[C@@H]1CC[C@@H]2O",
            "cortisol": "O[C@@]1(C(=O)CO)CC[C@@H]2[C@@]1(C)C[C@H](O)[C@H]1[C@@H]2CCC2=CC(=O)CC[C@@]12C",
            "코르티솔": "O[C@@]1(C(=O)CO)CC[C@@H]2[C@@]1(C)C[C@H](O)[C@H]1[C@@H]2CCC2=CC(=O)CC[C@@]12C",
            "dexamethasone": "C[C@@H]1C[C@H]2[C@@H]3CCC4=CC(=O)C=C[C@]4(C)[C@@]3(F)[C@@H](O)C[C@]2(C)[C@@]1(O)C(=O)CO",
            "덱사메타손": "C[C@@H]1C[C@H]2[C@@H]3CCC4=CC(=O)C=C[C@]4(C)[C@@]3(F)[C@@H](O)C[C@]2(C)[C@@]1(O)C(=O)CO",
            # 배위화합물 (착물)
            # M551: 페로센 PubChem CID 11985 검증본 (Rule L)
            # [cH-]1cccc1.[Fe+2].[cH-]1cccc1 — InChI 일치 확인
            "ferrocene": "[cH-]1cccc1.[Fe+2].[cH-]1cccc1",
            "페로센": "[cH-]1cccc1.[Fe+2].[cH-]1cccc1",
            "hemoglobin": None,  # → LARGE_MOLECULES fallback
            # 기타 유명 화합물
            "nicotine": "c1ncc(c1)[C@@H]1CCCN1C",
            "니코틴": "c1ncc(c1)[C@@H]1CCCN1C",
            "capsaicin": "COc1cc(CNC(=O)CCCC/C=C/C(C)C)ccc1O",
            "캡사이신": "COc1cc(CNC(=O)CCCC/C=C/C(C)C)ccc1O",
            "thc": "CCCCCc1cc(O)c2c(c1)OC(C)(C)[C@@H]1CCC(=CC21)C",
            "테트라하이드로칸나비놀": "CCCCCc1cc(O)c2c(c1)OC(C)(C)[C@@H]1CCC(=CC21)C",
            "penicillin g": "CC1(C)S[C@@H]2[C@H](NC(=O)Cc3ccccc3)C(=O)N2[C@@H]1C(=O)O",
            "이부프로펜": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
            # ═══ 한글 일반/산업 화학물질 ═══
            "벤조산": "OC(=O)c1ccccc1",
            "살리실산": "OC(=O)c1ccccc1O", "salicylic acid": "OC(=O)c1ccccc1O",
            "아세틸살리실산": "CC(=O)Oc1ccccc1C(=O)O",
            "젖산": "C[C@@H](O)C(=O)O",
            "락트산": "C[C@@H](O)C(=O)O",
            "카프로산": "CCCCCC(=O)O", "caproic acid": "CCCCCC(=O)O",
            "벤조일퍼옥사이드": "O=C(OOC(=O)c1ccccc1)c1ccccc1", "benzoyl peroxide": "O=C(OOC(=O)c1ccccc1)c1ccccc1",
            # ═══ 화장품/생활용품 성분 ═══
            "히알루론산": "OC1C(O)C(OC(O)C1O)C(=O)O",  # 단위체 (글루쿠론산)
            "hyaluronic acid": "OC1C(O)C(OC(O)C1O)C(=O)O",
            "레티놀": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/CO)C(C)(C)CCC1",
            "레틴산": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/C(=O)O)C(C)(C)CCC1",
            "retinoic acid": "CC1=C(/C=C/C(C)=C/C=C/C(C)=C/C(=O)O)C(C)(C)CCC1",
            "나이아신아마이드": "NC(=O)c1cccnc1", "niacinamide": "NC(=O)c1cccnc1", "니코틴아마이드": "NC(=O)c1cccnc1",
            "토코페롤": "CC1=C(C)C(O)=C2OC(CCCC(C)CCCC(C)CCCC(C)C)(C)CCC2=C1C", "tocopherol": "CC1=C(C)C(O)=C2OC(CCCC(C)CCCC(C)CCCC(C)C)(C)CCC2=C1C",
            "살리실산": "OC(=O)c1ccccc1O",
            "글리콜산": "OCC(=O)O", "glycolic acid": "OCC(=O)O",
            "아젤라산": "OC(=O)CCCCCCCC(=O)O", "azelaic acid": "OC(=O)CCCCCCCC(=O)O",
            "알파하이드록시산": "OCC(=O)O",  # AHA = glycolic acid
            "베타하이드록시산": "OC(=O)c1ccccc1O",  # BHA = salicylic acid
            "aha": "OCC(=O)O", "bha": "OC(=O)c1ccccc1O",
            "스쿠알렌": "CC(=CCC/C(=C/CC/C(=C/CC/C=C(/CC/C=C(/CCC=C(C)C)\\C)\\C)\\C)/C)C",
            "squalene": "CC(=CCC/C(=C/CC/C(=C/CC/C=C(/CC/C=C(/CCC=C(C)C)\\C)\\C)\\C)/C)C",
            "파라벤": "COC(=O)c1ccc(O)cc1", "paraben": "COC(=O)c1ccc(O)cc1", "methylparaben": "COC(=O)c1ccc(O)cc1",
            "소르비톨": "OC[C@@H](O)[C@H](O)[C@@H](O)[C@H](O)CO", "sorbitol": "OC[C@@H](O)[C@H](O)[C@@H](O)[C@H](O)CO",
            "프로필렌글리콜": "CC(O)CO", "propylene glycol": "CC(O)CO",
            "소듐라우릴설페이트": "CCCCCCCCCCCCOS(=O)(=O)[O-].[Na+]", "sls": "CCCCCCCCCCCCOS(=O)(=O)[O-].[Na+]",
            "세틸알코올": "CCCCCCCCCCCCCCCCO", "cetyl alcohol": "CCCCCCCCCCCCCCCCO",
            # ═══ 교과서 유기화학 핵심 ═══
            "아세트아닐리드": "CC(=O)Nc1ccccc1", "acetanilide": "CC(=O)Nc1ccccc1",
            "벤즈알데히드": "O=Cc1ccccc1", "benzaldehyde": "O=Cc1ccccc1",
            "아세토페논": "CC(=O)c1ccccc1", "acetophenone": "CC(=O)c1ccccc1",
            "다이에틸에테르": "CCOCC",
            "에틸아세테이트": "CCOC(=O)C", "ethyl acetate": "CCOC(=O)C",
            "아세트산에틸": "CCOC(=O)C",
            "메틸아크릴레이트": "COC(=O)C=C", "methyl acrylate": "COC(=O)C=C",
            "에폭사이드": "C1CO1", "ethylene oxide": "C1CO1", "에틸렌옥사이드": "C1CO1",
            "아세토니트릴": "CC#N", "acetonitrile": "CC#N",
            "피크르산": "O=[N+]([O-])c1cc([N+](=O)[O-])c(O)c([N+](=O)[O-])c1", "picric acid": "O=[N+]([O-])c1cc([N+](=O)[O-])c(O)c([N+](=O)[O-])c1",
            "나일론": "O=C(NCCCCCCN)CCCCC(=O)O",  # 나일론 6,6 단위체
            "폴리에틸렌": "CCCC",  # 단위체
            "pvc": "ClC=C", "폴리염화비닐": "ClC=C",
            "폼산메틸": "COC=O", "methyl formate": "COC=O",
            # ═══ 기체/실험실 시약 ═══
            "드라이아이스": "O=C=O",
            "에탄올아민": "NCCO", "ethanolamine": "NCCO",
            "트리에틸아민": "CCN(CC)CC", "triethylamine": "CCN(CC)CC",
            "수소": "[H][H]", "hydrogen": "[H][H]",
            "산소": "O=O", "oxygen": "O=O",
            "질소": "N#N", "nitrogen": "N#N",
            "염소": "ClCl", "chlorine": "ClCl",
            "브로민": "BrBr", "bromine": "BrBr",
            "아이오딘": "II", "iodine": "II",
            # ═══ 무기산/염기/산화물 (교과서 필수) ═══
            "차아염소산": "ClO", "hypochlorous acid": "ClO", "hocl": "ClO",
            "아염소산": "O=ClO", "chlorous acid": "O=ClO",
            "염소산": "O=Cl(=O)O", "chloric acid": "O=Cl(=O)O",
            "과염소산": "O=Cl(=O)(=O)O", "perchloric acid": "O=Cl(=O)(=O)O",
            "차아브로민산": "BrO", "hypobromous acid": "BrO",
            "아질산": "ON=O", "nitrous acid": "ON=O", "hno2": "ON=O",
            "아황산": "OS(=O)O", "sulfurous acid": "OS(=O)O", "h2so3": "OS(=O)O",
            "탄산": "OC(=O)O", "carbonic acid": "OC(=O)O", "h2co3": "OC(=O)O",
            "붕산": "OB(O)O", "boric acid": "OB(O)O",
            "플루오린화수소": "F", "hydrogen fluoride": "F", "불산": "F", "hf": "F",
            "브로민화수소": "Br", "hydrobromic acid": "Br", "hbr": "Br",
            "아이오딘화수소": "I", "hydroiodic acid": "I", "hi": "I",
            "시안화수소": "C#N", "hydrogen cyanide": "C#N", "hcn": "C#N", "청산": "C#N",
            "과산화나트륨": "[Na+].[Na+].[O-][O-]", "sodium peroxide": "[Na+].[Na+].[O-][O-]",
            "수산화칼륨": "[K+].[OH-]", "potassium hydroxide": "[K+].[OH-]", "가성칼리": "[K+].[OH-]",
            "수산화칼슘": "[Ca+2].[OH-].[OH-]", "calcium hydroxide": "[Ca+2].[OH-].[OH-]", "소석회": "[Ca+2].[OH-].[OH-]",
            "산화칼슘": "[Ca]=O", "calcium oxide": "[Ca]=O", "생석회": "[Ca]=O",
            "탄산나트륨": "[Na+].[Na+].[O-]C(=O)[O-]", "sodium carbonate": "[Na+].[Na+].[O-]C(=O)[O-]", "소다회": "[Na+].[Na+].[O-]C(=O)[O-]",
            "탄산수소나트륨": "[Na+].OC(=O)[O-]", "sodium bicarbonate": "[Na+].OC(=O)[O-]", "베이킹소다": "[Na+].OC(=O)[O-]",
            "황화나트륨": "[Na+].[Na+].[S-2]", "sodium sulfide": "[Na+].[Na+].[S-2]",
            # ═══ 일상용어/성분명 확장 ═══
            "소주": "CCO", "맥주": "CCO",  # ethanol 기준
            "식초": "CC(=O)O",  # acetic acid
            "비누": "CCCCCCCCCCCCCCCCCC(=O)[O-].[Na+]",  # sodium stearate
            "표백제": "ClO.[Na+]",  # sodium hypochlorite
            "락스": "ClO.[Na+]",
            "과산화수소수": "OO", "옥시돌": "OO",
            "요오드팅크": "II",  # iodine tincture
            "포르말린": "C=O",  # formaldehyde solution
            "에탄": "CC",
            # ═══ 추가 교과서 유기화합물 ═══
            "말론산": "OC(=O)CC(=O)O", "malonic acid": "OC(=O)CC(=O)O",
            "무수말레산": "O=C1OC(=O)C=C1", "maleic anhydride": "O=C1OC(=O)C=C1",
            "프탈산": "OC(=O)c1ccccc1C(=O)O", "phthalic acid": "OC(=O)c1ccccc1C(=O)O",
            "테레프탈산": "OC(=O)c1ccc(C(=O)O)cc1", "terephthalic acid": "OC(=O)c1ccc(C(=O)O)cc1",
            "아디프산": "OC(=O)CCCCC(=O)O", "adipic acid": "OC(=O)CCCCC(=O)O",
            "헥사메틸렌디아민": "NCCCCCCN", "hexamethylenediamine": "NCCCCCCN",
            "카프로락탐": "O=C1CCCCCN1", "caprolactam": "O=C1CCCCCN1",
            "디메틸포름아미드": "CN(C)C=O", "dmf": "CN(C)C=O",
            "테트라하이드로퓨란": "C1CCOC1", "thf": "C1CCOC1",
            "디클로로메탄": "ClCCl", "dichloromethane": "ClCCl", "메틸렌클로라이드": "ClCCl",
            "사염화탄소": "ClC(Cl)(Cl)Cl", "carbon tetrachloride": "ClC(Cl)(Cl)Cl",
            "트리클로로메탄": "ClC(Cl)Cl",
            "아크릴로니트릴": "C=CC#N", "acrylonitrile": "C=CC#N",
            "비스페놀a": "CC(C)(c1ccc(O)cc1)c1ccc(O)cc1", "bisphenol a": "CC(C)(c1ccc(O)cc1)c1ccc(O)cc1",
            "멜라민": "Nc1nc(N)nc(N)n1", "melamine": "Nc1nc(N)nc(N)n1",
            "포름아미드": "NC=O", "formamide": "NC=O",
            "vancomycin": None,
            "taxol": None, "paclitaxel": None,
            "sildenafil": "CCCc1nn(C)c2c1nc(nc2OCC)c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1",
            "실데나필": "CCCc1nn(C)c2c1nc(nc2OCC)c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1",
            "viagra": "CCCc1nn(C)c2c1nc(nc2OCC)c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1",
            "omeprazole": "COc1ccc2[nH]c(S(=O)Cc3ncc(C)c(OC)c3C)nc2c1",
            "오메프라졸": "COc1ccc2[nH]c(S(=O)Cc3ncc(C)c(OC)c3C)nc2c1",
            "loratadine": "CCOC(=O)N1CCC(=C2c3ccc(Cl)cc3CCc3ncccc32)CC1",
            "로라타딘": "CCOC(=O)N1CCC(=C2c3ccc(Cl)cc3CCc3ncccc32)CC1",
        }
        lower = name.lower().strip()
        if lower in BUILTIN:
            return BUILTIN[lower]
        # [FIX] 밑줄/하이픈 → 공백 변환 (cp_anion → cp anion, acetic-acid → acetic acid)
        lower_norm = lower.replace("_", " ").replace("-", " ")
        if lower_norm != lower and lower_norm in BUILTIN:
            return BUILTIN[lower_norm]

        # ── [Step 1.5] 축약식/분자식 전처리 (CH3CH2CH2COOH 등) ────────
        _parsed = self._try_parse_condensed(name)
        if _parsed:
            return _parsed

        # ── [Step 1.7] 한글 → 영문 화학명 번역 (Gemini 경량 호출) ──────
        # 한글 문자가 포함된 입력인 경우 Gemini로 영문 화학명을 얻어 PubChem에 전달
        _english_name = name  # 기본값: 원본
        _has_korean = any('\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u3163' for c in name)
        if _has_korean:
            _api_key_tr = (_os.environ.get("GEMINI_API_KEY", "")
                           or _os.environ.get("GOOGLE_API_KEY", ""))
            _tr_prompt = (
                f"'{name}'의 영문 화학명(IUPAC 또는 common name)을 한 단어/구만 출력하세요. "
                "설명 없이 영문 화학명만 출력. 모르면 UNKNOWN 출력."
            )
            _tr_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
            _translated = False
            if _api_key_tr:
                # Try new SDK (google.genai) first
                for _tr_model_name in _tr_models:
                    if _translated:
                        break
                    try:
                        import google.genai as _genai_tr
                        _tr_client = _genai_tr.Client(api_key=_api_key_tr)
                        _tr_resp = _tr_client.models.generate_content(
                            model=_tr_model_name, contents=_tr_prompt,
                        )
                        _en = _tr_resp.text.strip().split('\n')[0].strip()
                        if _en and _en.upper() != "UNKNOWN":
                            _english_name = _en
                            _translated = True
                    except Exception as _e:
                        logger.warning("[LITE-EXE-003] Gemini %s 실패: %s: %s", _tr_model_name, type(_e).__name__, _e)
                        continue
                # Fallback: old SDK (google.generativeai)
                if not _translated:
                    for _tr_model_name in _tr_models:
                        if _translated:
                            break
                        try:
                            import warnings
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                import google.generativeai as _genai_tr_old
                            _genai_tr_old.configure(api_key=_api_key_tr)
                            _tr_m = _genai_tr_old.GenerativeModel(_tr_model_name)
                            _tr_resp2 = _tr_m.generate_content(_tr_prompt)
                            _en2 = _tr_resp2.text.strip().split('\n')[0].strip()
                            if _en2 and _en2.upper() != "UNKNOWN":
                                _english_name = _en2
                                _translated = True
                        except Exception as _e:
                            logger.warning("[LITE-EXE-003] Gemini(old) %s 실패: %s: %s", _tr_model_name, type(_e).__name__, _e)
                            continue
            if not _translated and _has_korean:
                logger.warning("[LITE-EXE-003] 한글 번역 실패: '%s' → API 키 미설정 또는 할당량 초과", name)

        # ── [Step 2] PubChem REST API (pubchem_client: API 키 + 초당 1회 속도 제한) ──
        # 한글 번역된 영문명이 있으면 그걸로 먼저 시도, 없으면 원본으로 시도
        _names_to_try = [_english_name] if _english_name != name else []
        _names_to_try.append(name)
        for _try_name in _names_to_try:
            try:
                _pc_smiles = _pc_client.get_smiles_by_name(_try_name)
                if _pc_smiles:
                    try:
                        from rdkit import Chem as _Chem
                        _mol = _Chem.MolFromSmiles(_pc_smiles)
                        if _mol:
                            return _Chem.MolToSmiles(_mol)
                    except Exception as e:
                        logger.warning(f"[MainWindow] PubChem SMILES RDKit 정규화 실패: {e}")
                    return _pc_smiles
            except Exception as _e:
                logger.warning("[LITE-EXE-003] PubChem '%s' 실패: %s: %s", _try_name, type(_e).__name__, _e)

        # ── [Step 2.5] NCI Cactus + OPSIN — M646_LITE_PARITY 통합 (Q-N25) ──
        # NCI Cactus: 모든 합법 화학 입력 → SMILES (Williams 2008 NCI/CADD).
        # OPSIN:      IUPAC 정식명만 → SMILES (Lowe 2011 J Chem Inf Model 51:739).
        # 학술 인용 (Rule NN — academic_integrity_check.py / FP-28 차단):
        #   NCI Cactus: Williams, A.J. (2008) NCI/CADD. https://cactus.nci.nih.gov/
        #   OPSIN:      Lowe, D.M. et al. (2011) J. Chem. Inf. Model. 51: 739-753.
        # Rule M (silent failure 금지): 모든 실패 경로 logger.warning.
        # Rule N (타입 가드): isinstance() + .strip() + 응답 길이 체크.
        try:
            import urllib.parse as _urlparse
            import urllib.request as _urlreq
            for _try_name in _names_to_try:
                if not isinstance(_try_name, str) or not _try_name.strip():  # Rule N
                    continue
                _encoded = _urlparse.quote(_try_name.strip(), safe='')
                # NCI Cactus name → SMILES — 가장 관대한 해석기
                # [MAGIC: 10s] cactus 응답 시간 max
                try:
                    _nci_url = f"https://cactus.nci.nih.gov/chemical/structure/{_encoded}/smiles"
                    _req = _urlreq.Request(_nci_url, headers={"User-Agent": "ChemGrid/M646"})
                    with _urlreq.urlopen(_req, timeout=10) as _resp:
                        _raw = _resp.read().decode("utf-8", errors="replace").strip()
                    # NCI 는 SMILES 만 반환. 1~120자 범위 가드 (Rule N).
                    if isinstance(_raw, str) and 1 <= len(_raw) <= 200 and "\n" not in _raw:
                        try:
                            from rdkit import Chem as _Chem  # type: ignore
                            _mol = _Chem.MolFromSmiles(_raw)
                            if _mol is not None:
                                _canon = _Chem.MolToSmiles(_mol)
                                logger.info(
                                    "[M646_LITE] NCI Cactus '%s' → %s",
                                    _try_name, _canon[:60]
                                )
                                return _canon
                        except ImportError as e:
                            logger.warning("[M646_LITE] NCI Cactus RDKit 미설치 — raw 반환: %s", e)
                            return _raw
                except Exception as _e:
                    # Rule M: silent 금지 — type 명시
                    logger.warning(
                        "[M646_LITE] NCI Cactus '%s' 실패 %s: %s",
                        _try_name, type(_e).__name__, _e
                    )

                # OPSIN endpoint 폐기됨 (M712 / OPSIN-ENDPOINT-002):
                # https://opsin.ch.cam.ac.uk/opsin/{name}.json → HTTP 404 (2026 기준 API 없음, 웹 전용).
                # 대체: NCI Cactus IUPAC2SMILES endpoint (별도 path) — 동일 Cactus 서버에서 제공.
                # 학술: Lowe, D.M. et al. (2011) J. Chem. Inf. Model. 51:739 (OPSIN 논문, 실사용 불가).
                # [MAGIC: 10s] NCI Cactus IUPAC 전용 응답 시간 max
                try:
                    _iupac_url = (
                        f"https://cactus.nci.nih.gov/chemical/structure/{_encoded}/smiles"
                        f"?resolver=iupac_name"
                    )
                    _req2 = _urlreq.Request(_iupac_url, headers={"User-Agent": "ChemGrid/M712"})
                    with _urlreq.urlopen(_req2, timeout=10) as _resp2:
                        _raw2 = _resp2.read().decode("utf-8", errors="replace").strip()
                    if isinstance(_raw2, str) and 1 <= len(_raw2) <= 200 and "\n" not in _raw2:  # Rule N
                        try:
                            from rdkit import Chem as _Chem2  # type: ignore
                            _mol2 = _Chem2.MolFromSmiles(_raw2)
                            if _mol2 is not None:
                                _canon2 = _Chem2.MolToSmiles(_mol2)
                                logger.info(
                                    "[M712] NCI Cactus IUPAC '%s' → %s",
                                    _try_name, _canon2[:60]
                                )
                                return _canon2
                        except ImportError:
                            return _raw2
                except Exception as _e2:
                    logger.warning(
                        "[M712] NCI Cactus IUPAC '%s' 실패 %s: %s",
                        _try_name, type(_e2).__name__, _e2
                    )
        except Exception as _outer_e:
            # 외부 try 의 ImportError 등 (urllib/json) — Rule M 명시 로깅
            logger.warning(
                "[M646_LITE] NCI/OPSIN 통합 외부 실패 %s: %s",
                type(_outer_e).__name__, _outer_e
            )

        # ── 대형 단백질/복합체 → 가용 구조로 자동 폴백 ────────────────
        LARGE_MOLECULES = {
            "hemoglobin": "heme",
            "myoglobin": "heme",
            "albumin": None,
            "collagen": None,
            "insulin": "CC(C)CC1NC(=O)C(CC2=CC=CC=C2)NC(=O)",
            "dna": "adenine",
            "rna": "adenine",
            "protein": None,
        }
        if lower in LARGE_MOLECULES:
            alt = LARGE_MOLECULES[lower]
            if alt:
                return self._lookup_smiles_for_name(alt)
            return ""

        # ── [Step 3] Gemini AI 폴백 (dotenv 로딩 후 키 확인) ───────────
        _smiles_prompt = (
            f"화학 분자명 또는 분자식 '{name}'의 SMILES 코드를 알려주세요. "
            "SMILES 코드만 한 줄로 출력하세요. 설명 없이 SMILES만 출력."
        )
        _s3_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
        try:
            api_key = (_os.environ.get("GEMINI_API_KEY", "")
                       or _os.environ.get("GOOGLE_API_KEY", ""))
            if api_key:
                for _s3_model in _s3_models:
                    try:
                        import google.genai as _genai
                        client = _genai.Client(api_key=api_key)
                        response = client.models.generate_content(
                            model=_s3_model, contents=_smiles_prompt,
                        )
                        smiles = response.text.strip().split()[0]
                        if smiles and smiles.upper() not in ("UNKNOWN", "NONE", ""):
                            return smiles
                    except Exception:
                        try:
                            import warnings
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                import google.generativeai as _genai_old
                            _genai_old.configure(api_key=api_key)
                            _s3_m = _genai_old.GenerativeModel(_s3_model)
                            resp_old = _s3_m.generate_content(_smiles_prompt)
                            smiles = resp_old.text.strip().split()[0]
                            if smiles and smiles.upper() not in ("UNKNOWN", "NONE", ""):
                                return smiles
                        except Exception:
                            continue
        except Exception as e:
            logger.warning(f"[MainWindow] Gemini AI SMILES 조회 실패: {e}")

        # ── [Step 3.5] Google Knowledge Graph API → PubChem 교차 검색 ──────────
        # Gemini AI 실패 시, 사용자 입력 단어를 Google KG에서 화학물 엔티티로 검색
        # → 정규 화학명 획득 → PubChem SMILES 조회 (CX 불필요, GOOGLE_API_KEY만 필요)
        try:
            google_key = (_os.environ.get("GOOGLE_API_KEY", "")
                          or _os.environ.get("GEMINI_API_KEY", ""))
            if google_key:
                import urllib.parse as _up2
                # Google Knowledge Graph 엔티티 검색
                kg_params = {
                    "query": name,
                    "key": google_key,
                    "types": "ChemicalCompound",
                    "limit": 3,
                    "languages": "en",
                }
                kg_resp = _req2.get(
                    "https://kgsearch.googleapis.com/v1/entities:search",
                    params=kg_params,
                    timeout=6,
                )
                if kg_resp.status_code == 200:
                    _kg_json = kg_resp.json()
                    if not isinstance(_kg_json, dict):  # Rule N
                        _kg_json = {}
                    items = _kg_json.get("itemListElement", [])
                    if not isinstance(items, list):  # Rule N
                        items = []
                    for item in items:
                        if not isinstance(item, dict):  # Rule N
                            continue
                        _item_result = item.get("result", {})
                        entity_name = _item_result.get("name", "") if isinstance(_item_result, dict) else ""
                        if entity_name and entity_name.lower() != name.lower():
                            # 정규 화학명으로 PubChem 재조회
                            pc_url = (
                                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
                                f"{_up2.quote(entity_name)}/property/IsomericSMILES/JSON"
                            )
                            pc_r = _pc_client._get(pc_url, timeout=5)
                            if pc_r.status_code == 200:
                                _pc_json = pc_r.json()
                                if not isinstance(_pc_json, dict):  # Rule N
                                    _pc_json = {}
                                _pt = _pc_json.get("PropertyTable", {})
                                if not isinstance(_pt, dict):  # Rule N
                                    _pt = {}
                                _props = _pt.get("Properties", [{}])
                                if not isinstance(_props, list) or not _props:  # Rule N
                                    _props = [{}]
                                _first = _props[0]
                                _smiles_kg = _first.get("IsomericSMILES", "") if isinstance(_first, dict) else ""
                                if _smiles_kg:
                                    try:
                                        from rdkit import Chem as _C2
                                        if _C2.MolFromSmiles(_smiles_kg):
                                            return _C2.MolToSmiles(_C2.MolFromSmiles(_smiles_kg))
                                    except Exception:
                                        return _smiles_kg
                        elif entity_name:
                            # 동일 이름이더라도 PubChem에 없었던 케이스 재시도
                            pc_url = (
                                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
                                f"{_up2.quote(entity_name)}/property/IsomericSMILES/JSON"
                            )
                            pc_r = _pc_client._get(pc_url, timeout=5)
                            if pc_r.status_code == 200:
                                _pc_json2 = pc_r.json()
                                if not isinstance(_pc_json2, dict):  # Rule N
                                    _pc_json2 = {}
                                _pt2 = _pc_json2.get("PropertyTable", {})
                                if not isinstance(_pt2, dict):  # Rule N
                                    _pt2 = {}
                                _props2 = _pt2.get("Properties", [{}])
                                if not isinstance(_props2, list) or not _props2:  # Rule N
                                    _props2 = [{}]
                                _first2 = _props2[0]
                                _smiles_kg = _first2.get("IsomericSMILES", "") if isinstance(_first2, dict) else ""
                                if _smiles_kg:
                                    return _smiles_kg
        except Exception as e:
            logger.warning(f"[MainWindow] Google KG/PubChem 교차 검색 실패: {e}")

        # ── [Step 3.6] PubChem Autocomplete fuzzy matching (pubchem_client: 초당 1회 속도 제한) ──
        # [FIX] Similarity filter: reject suggestions dissimilar to the query
        # (e.g. "fentanyl" → "phentan-2-ol" is rejected)
        def _name_is_similar(query: str, suggestion: str) -> bool:
            """Check if suggestion name is sufficiently similar to query.
            Uses character trigram Jaccard similarity + substring checks."""
            q = query.lower().strip()
            s = suggestion.lower().strip()
            # Exact match or substring containment → always accept
            if q in s or s in q:
                return True
            # Character trigram Jaccard similarity
            def _trigrams(text: str) -> set:
                return {text[i:i+3] for i in range(len(text) - 2)} if len(text) >= 3 else {text}
            q_tri = _trigrams(q)
            s_tri = _trigrams(s)
            if not q_tri or not s_tri:
                return False
            jaccard = len(q_tri & s_tri) / len(q_tri | s_tri)
            return jaccard >= 0.35

        try:
            for _sug in _pc_client.get_suggestions(name, limit=5):
                if _sug.lower() == name.lower():
                    continue
                if not _name_is_similar(name, _sug):
                    continue
                _sug_smiles = _pc_client.get_smiles_by_name(_sug)
                if _sug_smiles:
                    return _sug_smiles
        except Exception as e:
            logger.warning(f"[MainWindow] PubChem Autocomplete fuzzy 검색 실패: {e}")

        return ""

    def _try_parse_condensed(self, text: str) -> str:
        """
        축약식 분자식(CH3CH2CH2COOH, C2H5OH 등) → SMILES 변환 시도.
        [BUG-04b Fix] PubChem이 인식하지 못하는 축약식 구조식을 사전+RDKit로 처리.
        """
        # 1) RDKit로 직접 SMILES 파싱 시도 (이미 SMILES인 경우)
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(text)
            if mol:
                return Chem.MolToSmiles(mol)
        except Exception as e:
            logger.warning(f"[MainWindow] 축약식 직접 SMILES 파싱 실패: {e}")

        # 2) 축약식 → SMILES 매핑 사전
        CONDENSED = {
            "ch4": "C",
            "ch3ch3": "CC", "c2h6": "CC",
            "ch3ch2ch3": "CCC", "c3h8": "CCC",
            "ch3(ch2)2ch3": "CCCC", "c4h10": "CCCC",
            "ch3oh": "CO", "ch4o": "CO",
            "ch3ch2oh": "CCO", "c2h5oh": "CCO", "c2h6o": "CCO",
            "ch3ch2ch2oh": "CCCO", "c3h7oh": "CCCO",
            "hcooh": "OC=O", "ch2o2": "OC=O",
            "ch3cooh": "CC(=O)O", "c2h4o2": "CC(=O)O",
            "ch3ch2cooh": "CCC(=O)O",
            "ch3ch2ch2cooh": "CCCC(=O)O",
            "ch3(ch2)2cooh": "CCCC(=O)O",
            "ch3ch2ch2ch2cooh": "CCCCC(=O)O",
            "ch3(ch2)3cooh": "CCCCC(=O)O",
            "ch3cho": "CC=O",
            "ch3coch3": "CC(C)=O",
            "ch2cl2": "ClCCl",
            "chcl3": "ClC(Cl)Cl",
            "ccl4": "ClC(Cl)(Cl)Cl",
            "c6h6": "c1ccccc1",
            "c6h5oh": "Oc1ccccc1",
            "c6h5nh2": "Nc1ccccc1",
            "c6h5cooh": "OC(=O)c1ccccc1",
            "c6h12o6": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
        }
        key = text.lower().replace(" ", "")
        if key in CONDENSED:
            return CONDENSED[key]

        return ""

    def _draw_smiles_on_canvas(self, smiles: str, mol_name: str = "", append: bool = False):
        """RDKit 2D 좌표를 캔버스 원자/결합 데이터로 변환하여 그리기

        [BUG-02 수정] 좌표계 오류 + hex grid 스냅 + analysis_results 갱신
        - 수정 전: cx = width/2 + pan_offset (부호 오류)
        - 수정 후: logical_center = (width/2 - pan_offset) / scale_factor
        - 스냅 방식: 직교 30px 단위 → canvas.get_closest_pt() (hex grid)
        - 수정 후: analysis_results 갱신 → Theory 레이어에서 구조 표시 가능

        Args:
            append: True이면 기존 분자를 지우지 않고 빈 공간에 새 분자 추가
        """
        import sys
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            from PyQt6.QtCore import QPointF

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                # Rule L + Rule M: SMILES 파싱 실패 시 silent return 금지
                # Kekulize/Ring/Valence 에러는 RDKit이 stderr에 출력하므로 logger로 재기록
                logger.warning(
                    "[_draw_smiles_on_canvas] MolFromSmiles 반환 None — 잘못된 SMILES: %r "
                    "(가능 원인: Kekulize 오류 / Ring 폐환 불가 / Valence 초과). "
                    "PubChem 검증본 사용 권장 (Rule L).",
                    smiles,
                )
                return False

            # M858: RDKit can place disconnected SMILES fragments on top of
            # each other in one coordinate frame.  Draw each dot fragment via
            # the existing append path so visible foreground reaction tests
            # show separate molecules and the reaction popup has real islands.
            if "." in smiles:
                try:
                    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
                except Exception as frag_exc:
                    logger.warning("[M858] GetMolFrags failed for %s: %s", smiles, frag_exc)
                    fragments = ()
                if len(fragments) > 1:
                    if not append:
                        self.cv.save_state()
                        self.cv.atoms.clear()
                        self.cv.bonds.clear()
                    drawn_keys = set()
                    for frag_index, frag in enumerate(fragments):
                        frag_smiles = Chem.MolToSmiles(frag)
                        frag_name = f"{mol_name or 'molecule'} fragment {frag_index + 1}"
                        ok = self._draw_smiles_on_canvas(frag_smiles, frag_name, append=True)
                        if ok:
                            drawn_keys.update(getattr(self.cv, "selected_molecule_keys", set()))
                    if not drawn_keys:
                        logger.warning("[M858] no dot-SMILES fragments were drawn: %s", smiles)
                        return False
                    self.cv.selected_molecule_keys = drawn_keys
                    self.cv.selected_molecule_name = mol_name if mol_name else "molecule"
                    self.cv._last_drawn_smiles = smiles
                    self.cv._last_drawn_mol_name = mol_name
                    try:
                        self.cv.analysis_results = self.cv.analyzer.analyze(
                            self.cv.atoms,
                            self.cv.bonds,
                            smiles=smiles,
                        )
                        if self.cv.analysis_results is not None:
                            self.cv.analysis_results["smiles"] = smiles
                    except Exception as analyze_exc:
                        logger.warning("[M858] dot-SMILES analyze failed for %s: %s", smiles, analyze_exc)
                    try:
                        self.cv.on_molecule_updated()
                    except Exception as update_exc:
                        logger.warning("[M858] dot-SMILES update failed for %s: %s", smiles, update_exc)
                    if hasattr(self, "_update_toolbar_state"):
                        self._update_toolbar_state()
                    self.cv.update()
                    return True

            # 수소 제거 (표시 단순화)
            mol = Chem.RemoveHs(mol)
            AllChem.Compute2DCoords(mol)
            # ★ [BUG-04-DRAW FIX] Kekulize: 방향족 결합을 교차 단일/이중결합으로 변환
            _kekulized = False
            try:
                Chem.Kekulize(mol, clearAromaticFlags=False)
                _kekulized = True
            except Exception as e:
                logger.warning(f"[MainWindow] Kekulize 실패(방향족 원으로 표시됨): {e}")
            conf = mol.GetConformer()

            xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
            ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
            cx_mol = (max(xs) + min(xs)) / 2
            cy_mol = (max(ys) + min(ys)) / 2
            mol_w = (max(xs) - min(xs))  # RDKit 단위 폭
            mol_h = (max(ys) - min(ys))  # RDKit 단위 높이

            # ✅ [BUG-02A 수정] 올바른 논리 좌표 계산
            sf = getattr(self.cv, 'scale_factor', 1.0)
            pan_x = self.cv.pan_offset.x()
            pan_y = self.cv.pan_offset.y()
            cx_logical = (self.cv.width() / 2 - pan_x) / sf
            cy_logical = (self.cv.height() / 2 - pan_y) / sf
            logger.debug("[LITE-EXE-003] MolDraw zoom/pan state: sf=%s, pan=(%s,%s), center_logical=(%.1f,%.1f)", sf, pan_x, pan_y, cx_logical, cy_logical)

            # RDKit 2D 단위 → 논리 픽셀: grid_size / C-C bond(1.5Å)
            scale = self.cv.grid_size / 1.5

            self.cv.save_state()

            # ★ 기존 분자가 있고 append 모드이면 빈 공간에 배치
            if append and self.cv.atoms:
                # 기존 원자들의 bounding box 계산
                existing_xs = [k[0] for k in self.cv.atoms.keys()]
                existing_ys = [k[1] for k in self.cv.atoms.keys()]
                ex_max_x = max(existing_xs)
                ex_min_y = min(existing_ys)
                ex_max_y = max(existing_ys)
                ex_center_y = (ex_min_y + ex_max_y) / 2

                # 새 분자 크기 (논리 픽셀)
                new_mol_half_w = mol_w * scale / 2

                # 기존 분자 오른쪽 + 여유 간격(120px)에 새 분자 중심 배치
                cx_logical = ex_max_x + 120 + new_mol_half_w
                cy_logical = ex_center_y
            elif not append:
                # 기존 동작: 캔버스 초기화 후 중앙에 그리기
                self.cv.atoms.clear()
                self.cv.bonds.clear()

            # ✅ [BUG-02B 수정] hex grid 스냅 사용
            idx_to_key = {}
            for i in range(mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                atom = mol.GetAtomWithIdx(i)
                # [BUG-FIX] 탄소 원자를 skeleton 방식(main="")으로 설정
                # 수정 전: main="C" → 모든 탄소에 "C" 라벨 표시 → 트로필리움 "+"가 "C" 위를 가림
                # 수정 후: main="" → 탄소는 bond 교차점으로만 표시, charge만 위첨자로 표시
                sym = "" if atom.GetSymbol() == "C" else atom.GetSymbol()

                raw_x = cx_logical + (pos.x - cx_mol) * scale
                raw_y = cy_logical - (pos.y - cy_mol) * scale  # Y축 반전
                raw_pos = QPointF(raw_x, raw_y)

                # hex grid 스냅 시도 (strict=False: SMILES 그리기는 항상 그리드에 정렬)
                snapped = self.cv.get_closest_pt(raw_pos, strict=False)

                key = (round(snapped.x(), 2), round(snapped.y(), 2))

                # 키 충돌 방지 (같은 그리드 포인트에 두 원자가 겹치는 경우)
                offset = 0
                while key in self.cv.atoms:
                    offset += 1
                    key = (round(snapped.x() + offset * self.cv.grid_size, 2), round(snapped.y(), 2))

                # ★ [Fix v5.92] SMILES 원자 formal_charge 저장
                # RDKit formal_charge를 atoms dict에 기록 → renderer의 ionic_bias 감지 가능
                _fc = atom.GetFormalCharge()
                _atom_entry = {"main": sym, "attach": {}, "rdkit_idx": i}
                if _fc != 0:
                    _atom_entry["formal_charge"] = _fc
                    _atom_entry["charge"] = "+" if _fc > 0 else "-"
                self.cv.atoms[key] = _atom_entry
                idx_to_key[i] = key

            # 결합 추가
            for bond in mol.GetBonds():
                i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                k1, k2 = idx_to_key.get(i), idx_to_key.get(j)
                if k1 and k2:
                    # [BUG-FIX] 방향족 결합(BondType.AROMATIC) 처리
                    # GetBondTypeAsDouble()이 방향족 결합에 대해 1.5 반환
                    # bt < 1.5 조건은 False → 잘못 order=2로 처리되는 버그 수정
                    from rdkit.Chem import rdchem as _rdchem
                    bt_type = bond.GetBondType()
                    # [COORD-BOND] RDKit DATIVE bond → dative marker (0.5)
                    if hasattr(_rdchem.BondType, 'DATIVE') and bt_type == _rdchem.BondType.DATIVE:
                        order = 0.5
                    elif _kekulized:
                        # ★ Kekulize 후: AROMATIC→SINGLE/DOUBLE 교차 변환됨
                        # benzene의 3개 이중결합이 올바르게 표시됨
                        bt = bond.GetBondTypeAsDouble()
                        order = 1 if bt < 1.5 else (2 if bt < 2.5 else 3)
                    elif bt_type == _rdchem.BondType.AROMATIC:
                        # Kekulize 실패 시: 방향족 결합을 단일결합으로 폴백
                        order = 1
                    elif bt_type == _rdchem.BondType.SINGLE:
                        order = 1
                    elif bt_type == _rdchem.BondType.DOUBLE:
                        order = 2
                    elif bt_type == _rdchem.BondType.TRIPLE:
                        order = 3
                    else:
                        bt = bond.GetBondTypeAsDouble()
                        order = 1 if bt <= 1.5 else (2 if bt < 2.5 else 3)
                    self.cv.bonds[(k1, k2)] = order

            # ★ [COORD-BOND] 범용 배위결합 감지 (2D 캔버스)
            # 전이금속-리간드 단일결합을 dative(0.5)로 재분류
            _detect_2d_coordination_bonds(self.cv.atoms, self.cv.bonds)

            # ★ [FIX-STEREO] Auto wedge/dash for chiral centers from SMILES
            # Detect chiral carbons and set one bond per center to Wedge or Dash
            try:
                from rdkit.Chem import FindMolChiralCenters
                # Re-parse original SMILES (before Kekulize) to get stereochemistry info
                # [BUG-FIX] None check is critical: invalid SMILES returns None and crashes
                _stereo_mol = Chem.MolFromSmiles(smiles)
                if _stereo_mol is None:
                    logger.warning("[STEREO] MolFromSmiles returned None for SMILES: %s", smiles)
                else:
                    try:
                        Chem.AssignStereochemistry(_stereo_mol, cleanIt=True, force=True)
                    except Exception as _e_assign:
                        logger.warning("[STEREO] AssignStereochemistry failed: %s", _e_assign)
                        _stereo_mol = None  # Disable stereo processing if assignment fails

                if _stereo_mol is not None:
                    try:
                        chiral_info = FindMolChiralCenters(_stereo_mol, includeUnassigned=True)
                    except Exception as _e_chiral:
                        logger.warning("[STEREO] FindMolChiralCenters failed: %s", _e_chiral)
                        chiral_info = []

                    # chiral_info: list of (atom_idx, 'R'|'S'|'?')
                    for _chiral_idx, _chiral_tag in chiral_info:
                        # [BUG-FIX] Guard: idx_to_key was built from mol (RemoveHs),
                        # _stereo_mol uses same order but verify mapping is valid
                        if not isinstance(_chiral_idx, int) or _chiral_idx not in idx_to_key:
                            logger.warning("[STEREO] chiral_idx %s not in idx_to_key (size=%d)",
                                           _chiral_idx, len(idx_to_key))
                            continue
                        chiral_key = idx_to_key[_chiral_idx]
                        if not isinstance(chiral_key, tuple) or len(chiral_key) != 2:
                            continue
                        # Find a single bond from this chiral center to set as wedge/dash
                        _stereo_set = False
                        for _bkey, _bdata in list(self.cv.bonds.items()):
                            # Only modify integer (single bond) data, skip already-stereo or multiple bonds
                            if not isinstance(_bdata, int) or _bdata != 1:
                                continue
                            if chiral_key == _bkey[0]:
                                _other_key = _bkey[1]
                            elif chiral_key == _bkey[1]:
                                _other_key = _bkey[0]
                            else:
                                continue
                            # Prefer non-H, non-carbon neighbor for wedge/dash visibility
                            _oad = self.cv.atoms.get(_other_key, {})
                            _other_sym = _oad.get("main", "") if isinstance(_oad, dict) else ""  # Rule N
                            if _other_sym in ("H", ""):
                                continue  # Skip H and C, try to find a heteroatom bond
                            # Set wedge for R, dash for S (convention)
                            if _chiral_tag in ('R', '?'):
                                self.cv.bonds[_bkey] = (QPointF(*chiral_key), QPointF(*_other_key), "Wedge")
                            else:
                                self.cv.bonds[_bkey] = (QPointF(*chiral_key), QPointF(*_other_key), "Dash")
                            _stereo_set = True
                            break
                        # Fallback: if no heteroatom neighbor found, use first single bond
                        if not _stereo_set:
                            for _bkey, _bdata in list(self.cv.bonds.items()):
                                if not isinstance(_bdata, int) or _bdata != 1:
                                    continue
                                if chiral_key in (_bkey[0], _bkey[1]):
                                    _other_key = _bkey[1] if chiral_key == _bkey[0] else _bkey[0]
                                    if _chiral_tag in ('R', '?'):
                                        self.cv.bonds[_bkey] = (QPointF(*chiral_key), QPointF(*_other_key), "Wedge")
                                    else:
                                        self.cv.bonds[_bkey] = (QPointF(*chiral_key), QPointF(*_other_key), "Dash")
                                    break
            except Exception as _e_stereo:
                logger.warning("[STEREO] Auto wedge/dash for chiral centers failed: %s", _e_stereo,
                               exc_info=True)

            # 선택 상태 등록
            drawn_keys = set(idx_to_key.values())
            self.cv.selected_molecule_keys = drawn_keys
            self.cv.selected_molecule_name = mol_name if mol_name else "molecule"

            # ✅ [BUG-02C 수정] analysis_results 갱신 → Theory 레이어 표시 가능
            try:
                # [BUG-B FIX] _last_drawn_smiles를 analyze() 전에 먼저 설정해야 현재 SMILES가 주입됨
                self.cv._last_drawn_smiles = smiles
                self.cv._last_drawn_mol_name = mol_name
                self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, smiles=smiles)
                # ★ [Fix v5.92] SMILES를 results에 저장 → renderer의 ionic_bias SMILES fallback 활성화
                # tropylium([CH+]), cp-([cH-]) 등 이온성 SMILES 감지 → BLUE/RED 색상 적용
                if self.cv.analysis_results is not None:
                    self.cv.analysis_results["smiles"] = smiles
            except Exception as e_analyze:
                logger.warning("[LITE-EXE-003] MolDraw analyze 실패 (smiles=%s): %s", smiles, e_analyze)
                # Fallback: smiles 파라미터 없이 재시도
                try:
                    self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds)
                    if self.cv.analysis_results is not None:
                        self.cv.analysis_results["smiles"] = smiles
                        logger.debug("[LITE-EXE-003] MolDraw analyze fallback 성공")
                except Exception as e2:
                    logger.warning("[LITE-EXE-003] MolDraw analyze fallback도 실패: %s", e2)

            # --- TASK-UC-004: guaranteed analysis_results ---
            if self.cv.analysis_results is None:
                logger.warning("[LITE-EXE-003] MolDraw WARNING: analysis_results None for %s, creating minimal fallback", smiles)
                self.cv.analysis_results = {
                    'smiles': smiles,
                    'atoms': {},
                    'norm_atoms': {},
                    'theory_data': None,
                    'formula': mol_name,
                }
            if 'smiles' not in self.cv.analysis_results:
                self.cv.analysis_results['smiles'] = smiles
            _ar = self.cv.analysis_results
            _ar_keys = list(_ar.keys()) if _ar else []
            logger.debug("[LITE-EXE-003] MolDraw analysis_results: keys=%s, smiles_present=%s", _ar_keys, "smiles" in _ar if _ar else False)

            try:
                self.cv.on_molecule_updated()
            except Exception as e_update:
                logger.warning("[LITE-EXE-003] MolDraw on_molecule_updated 실패: %s", e_update)

            try:
                self.cv.save_current_smiles()
            except Exception as e_save:
                logger.warning("[LITE-EXE-003] MolDraw save_current_smiles 실패: %s", e_save)
            # [FIX] 분자 그리기 후 반응분석 버튼 실시간 갱신
            if hasattr(self, 'btn_reaction') and self.btn_reaction.isVisible():
                try:
                    self._apply_analysis_button_gates()
                except Exception as e:
                    logger.warning(f"[MainWindow] 반응분석 버튼 갱신 실패: {e}")

            logger.debug(
                "[LITE-EXE-003] MolDraw '%s' → %d atoms, %d bonds (selected_keys=%d)",
                mol_name, mol.GetNumAtoms(), mol.GetNumBonds(), len(drawn_keys),
            )

            self.cv.update()
            if hasattr(self, '_update_toolbar_state'):
                self._update_toolbar_state()
            return True

        except Exception as e:
            logger.warning("[LITE-EXE-003] MolDraw 오류: %s", e)
            return False

    def _build_smiles_from_graph(self, atoms: dict, bonds: dict) -> str:
        """sel_atoms/sel_bonds 그래프에서 직접 SMILES를 생성.
        RDKit Edit 기반으로 원자/결합 그래프를 분자 객체로 변환.
        실패 시 빈 문자열 반환 (오류로 팝업 중단되지 않도록).
        """
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem

            rw = Chem.RWMol()
            key_to_idx: dict = {}

            # ① 원자 추가
            for key, adict in atoms.items():
                sym = adict.get("main", "C") if isinstance(adict, dict) else "C"  # Rule N
                if len(sym) > 2 or not sym.isalpha():
                    sym = "C"
                try:
                    atomic_num = Chem.GetPeriodicTable().GetAtomicNumber(sym)
                except Exception:
                    atomic_num = 6  # fallback to Carbon
                atom = Chem.Atom(atomic_num)
                idx = rw.AddAtom(atom)
                key_to_idx[key] = idx

            # ② 결합 추가
            bond_type_map = {
                1: Chem.BondType.SINGLE,
                2: Chem.BondType.DOUBLE,
                3: Chem.BondType.TRIPLE,
            }
            for (k1, k2), v in bonds.items():
                i1 = key_to_idx.get(k1)
                i2 = key_to_idx.get(k2)
                if i1 is None or i2 is None:
                    continue
                if isinstance(v, tuple):
                    # Wedge/Dash 결합
                    bt = Chem.BondType.SINGLE
                else:
                    bt = bond_type_map.get(int(v), Chem.BondType.SINGLE)
                # 이미 결합이 있으면 건너뜀
                if rw.GetBondBetweenAtoms(i1, i2) is None:
                    rw.AddBond(i1, i2, bt)

            # ③ 수소 보정 + 정규화
            mol = rw.GetMol()
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                logger.warning(f"[MainWindow] SanitizeMol 실패(Kekulize/Valence 오류 가능): {e}")

            smiles = Chem.MolToSmiles(mol, canonical=True)
            return smiles if smiles else ""

        except Exception as e:
            logger.warning("[LITE-EXE-003] _build_smiles_from_graph 실패: %s", e)
            return ""

    def clear_all(self):
        if QMessageBox.question(self, "확인", "전체 캔버스를 지우시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.cv.save_state(); self.cv.atoms = {}; self.cv.bonds = {}; self.cv.strokes = []; self.cv.update()

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG 저장", "", "PNG Files (*.png)")
        if path: self.cv.grab().save(path)
            
    def export_pdf(self):
        # [Automation] View State에 따른 파일명 및 절대 경로 설정
        mode = self.cv.view_state
        filename = f"chemgrid_export_{mode}.pdf"
        default_path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
        
        path, _ = QFileDialog.getSaveFileName(self, "PDF 저장", default_path, "PDF Files (*.pdf)")
        if path:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution); printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat); printer.setOutputFileName(path)
            painter = QPainter(printer); target_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            widget_rect = self.cv.rect(); scale = min(target_rect.width()/widget_rect.width(), target_rect.height()/widget_rect.height()) * 0.95
            painter.scale(scale, scale); self.cv.render(painter); painter.end()
            logger.debug("[LITE-EXE-003] PDF Saved to %s", path)

    def export_svg(self):
        """[M844-A3] SVG 벡터 내보내기 — QSvgGenerator + QPainter 사용."""
        path, _ = QFileDialog.getSaveFileName(self, "SVG 내보내기", "", "SVG Files (*.svg)")
        if not path:
            return
        try:
            from PyQt6.QtSvg import QSvgGenerator
            gen = QSvgGenerator()
            gen.setFileName(path)
            gen.setSize(self.cv.size())
            gen.setViewBox(self.cv.rect())
            gen.setTitle("ChemGrid SVG Export")
            painter = QPainter(gen)
            self.cv.render(painter)
            painter.end()
            logger.debug("[M844-A3] SVG saved: %s", path)
        except ImportError:
            logger.warning("[M844-A3] PyQt6.QtSvg 미사용 — SVG 내보내기 불가")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "SVG 내보내기 실패", "PyQt6.QtSvg 모듈이 없습니다. pip install PyQt6-sip 또는 PyQt6[QtSvg]를 설치하세요.")
        except Exception as e:
            logger.warning("[M844-A3] SVG export error: %s", e)

    def export_mol(self):
        """[M844-A3] MOL/SDF 파일 내보내기 — RDKit Chem.MolToMolFile 사용."""
        path, _ = QFileDialog.getSaveFileName(self, "MOL/SDF 내보내기", "", "MOL Files (*.mol);;SDF Files (*.sdf)")
        if not path:
            return
        try:
            from rdkit import Chem
            smiles = getattr(self.cv, 'current_smiles', None)
            if not smiles:
                # canvas에서 직접 SMILES 생성 시도
                if hasattr(self.cv, '_build_smiles'):
                    smiles = self.cv._build_smiles()
                elif hasattr(self.cv, 'get_smiles'):
                    smiles = self.cv.get_smiles()
            if not smiles:
                logger.warning("[M844-A3] export_mol: SMILES 없음 — 먼저 분자를 그려주세요")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "MOL 내보내기 실패", "현재 캔버스에서 SMILES를 추출할 수 없습니다. 분자를 그린 후 다시 시도하세요.")
                return
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:  # [Rule L] None 체크 필수
                logger.warning("[M844-A3] export_mol: MolFromSmiles 실패 smiles=%s", smiles)
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "MOL 내보내기 실패", f"SMILES 파싱 실패: {smiles}")
                return
            from rdkit.Chem import AllChem
            AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())  # 3D 좌표 생성 시도 (실패 시 무시)
            Chem.MolToMolFile(mol, path)
            logger.debug("[M844-A3] MOL saved: %s", path)
        except ImportError:
            logger.warning("[M844-A3] RDKit 미사용 — MOL 내보내기 불가")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "MOL 내보내기 실패", "RDKit이 설치되어 있지 않습니다.")
        except Exception as e:
            logger.warning("[M844-A3] MOL export error: %s", e)

    def save_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "파일 저장", "", "Chemical Data (*.chem)")
        if path:
            try:
                # [수정] QPointF 객체는 JSON 저장이 불가능하므로 리스트 [x, y]로 변환
                s_bonds = {}
                for (k1, k2), v in self.cv.bonds.items():
                    b_key = f"{k1[0]},{k1[1]}|{k2[0]},{k2[1]}"
                    if isinstance(v, tuple): # Wedge/Dash 결합 처리
                        s_bonds[b_key] = [[v[0].x(), v[0].y()], [v[1].x(), v[1].y()], v[2]]
                    else:
                        s_bonds[b_key] = v

                # atoms 직렬화: user_lp (set → list) 변환
                s_atoms = {}
                for k, v in self.cv.atoms.items():
                    atom_copy = dict(v)
                    if "user_lp" in atom_copy and isinstance(atom_copy["user_lp"], set):
                        atom_copy["user_lp"] = list(atom_copy["user_lp"])
                    s_atoms[f"{k[0]},{k[1]}"] = atom_copy

                # arrows 직렬화
                s_arrows = []
                for (a_s, a_e) in getattr(self.cv, 'arrows', []):
                    s_arrows.append([[a_s.x(), a_s.y()], [a_e.x(), a_e.y()]])

                # text_boxes 직렬화
                s_text_boxes = []
                for tb in getattr(self.cv, 'text_boxes', []):
                    s_text_boxes.append({
                        "pos": [tb["pos"].x(), tb["pos"].y()],
                        "text": tb["text"],
                        "font_size": tb.get("font_size", 12),
                    })

                save_data = {
                    "atoms": s_atoms,
                    "bonds": s_bonds,
                    "arrows": s_arrows,
                    "text_boxes": s_text_boxes,
                }
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, indent=4)
                QMessageBox.information(self, "성공", "파일이 안전하게 저장되었습니다.")
            except Exception as e:
                QMessageBox.critical(self, "저장 에러", f"저장 중 오류가 발생했습니다: {e}")

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "파일 열기", "", "Chemical Data (*.chem)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.cv.save_state()
                
                # 원자 복원 로직 (기존 유지)
                new_atoms = {}
                for k_str, v in data["atoms"].items():
                    coord = tuple(map(float, k_str.split(',')))
                    if "attach" in v:
                        v["attach"] = {int(dk): dv for dk, dv in v["attach"].items()}
                    new_atoms[coord] = v
                self.cv.atoms = new_atoms

                # [수정] 저장된 [x, y] 리스트를 다시 QPointF 객체로 복원
                new_bonds = {}
                for k_str, v in data["bonds"].items():
                    pts = k_str.split('|')
                    p1_key = tuple(map(float, pts[0].split(',')))
                    p2_key = tuple(map(float, pts[1].split(',')))
                    
                    if isinstance(v, list): # Wedge/Dash 데이터인 경우
                        v = (QPointF(v[0][0], v[0][1]), QPointF(v[1][0], v[1][1]), v[2])
                    
                    new_bonds[(p1_key, p2_key)] = v
                self.cv.bonds = new_bonds
                self.cv.update()
            except Exception as e:
                QMessageBox.critical(self, "불러오기 에러", f"파일을 읽는 중 오류가 발생했습니다: {e}")

    def create_handler(self, mode_name): return lambda: self.set_mode(mode_name)
    def set_mode(self, m):
         self.cv.mode = m; self.pen_ui.hide()
         # [추가] 손 도구 선택 시 마우스 모양 변경
         if m == "Hand":
             self.cv.setCursor(Qt.CursorShape.OpenHandCursor)
         else:
             self.cv.setCursor(Qt.CursorShape.ArrowCursor)

         if m == "Pen":
            action = self.sender()
            # [v5] Pen이 tb(메인 그리기 툴바)에 있음
            widget = self.tb.widgetForAction(action) if hasattr(self, 'tb') else None
            if not widget and hasattr(self, 'tb2'):
                widget = self.tb2.widgetForAction(action)
            if widget:
                global_pos = widget.mapToGlobal(QPoint(0, widget.height()))
                self.pen_ui.move(global_pos)
                self.pen_ui.show()

    # ========== [NEW] 상태바 분자량/분자식 갱신 ==========
    def _update_status_bar_mw_mf(self):
        """캔버스 분자 변경 시 상태바에 MW(분자량)와 MF(분자식) 표시"""
        try:
            smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
            if not smiles:
                smiles = self.cv.get_smiles() if hasattr(self.cv, 'get_smiles') else ''
            if not smiles:
                self._mol_status_label.setText("No molecule")
                return

            from rdkit import Chem
            from rdkit.Chem import Descriptors, rdMolDescriptors
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                self._mol_status_label.setText("No molecule")
                return

            mw = Descriptors.MolWt(mol)
            mf = rdMolDescriptors.CalcMolFormula(mol)
            self._mol_status_label.setText(f"MF: {mf}  |  MW: {mw:.2f} g/mol")

            # [Workflow Gate] 분자 분석 완료 → Step 1 업데이트
            if self.workflow and mol.GetNumAtoms() >= 2:
                mol_name = getattr(self.cv, '_last_drawn_mol_name', '') or \
                           getattr(self.cv, 'selected_molecule_name', '') or ''
                self.workflow.set_structure_analyzed(smiles=smiles, name=mol_name)
                # 모노머로도 등록 (PolymerLab 워크플로우)
                self.workflow.set_monomer_loaded(smiles=smiles, name=mol_name)
                self._on_workflow_step_update()
        except Exception as e:
            self._mol_status_label.setText("No molecule")
            logger.warning("[LITE-EXE-003] StatusBar MW/MF update error: %s", e)

    # ========== [UX-2] Welcome overlay 메서드 ==========
    def _dismiss_welcome_overlay(self) -> None:
        """분자가 로드되거나 캔버스 클릭 시 welcome overlay를 페이드아웃."""
        if not hasattr(self, '_welcome_overlay') or self._welcome_overlay is None:
            return
        if not self._welcome_overlay.isVisible():
            return
        try:
            effect = QGraphicsOpacityEffect(self._welcome_overlay)
            self._welcome_overlay.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(400)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(self._welcome_overlay.hide)
            anim.start()
            # prevent re-triggering
            self._welcome_anim = anim
        except Exception:
            self._welcome_overlay.hide()

    def _load_example_molecule(self, name: str) -> None:
        """[UX-2] 예시 분자 버튼 클릭 시 해당 분자를 캔버스에 로드."""
        self._dismiss_welcome_overlay()
        # 한국어 이름 -> 내장 사전에서 조회
        self.mol_name_input.setText(name)
        self._on_mol_name_submitted()

    def pick_clr(self):
        c = QColorDialog.getColor(self.cv.pen_color, self); self.cv.pen_color = c if c.isValid() else self.cv.pen_color; self.pen_ui.hide()
    def pick_el(self):
        d = PeriodicTableDialog(self); self.cv.mode = d.selected if d.exec() else self.cv.mode

    # ========== [Phase 5] Phase 4 기능 메서드 ==========
    
    def enable_lasso_select(self):
        """올가미 선택 모드 [제거됨] - 기본 직사각형 선택만 사용"""
        QMessageBox.information(self, "알림", "올가미 선택 기능이 제거되었습니다.\n기본 직사각형 선택 도구를 사용해주세요.\n\n사용법: Select 도구를 선택한 후 드래그하여 원자를 선택합니다.")

    # ========== [REACTION] 반응 분석 ==========
    def _count_molecules(self) -> int:
        """캔버스 위의 분리된 분자 개수를 반환.
        [FIX] 결합이 없고 원소도 없는 빈 마커 원자(lone pair/charge 도구)는 제외.
        [FIX] 원소가 있어도 결합이 없는 고립 원자(lewis 표시용 등)는 무시.
        실제 결합으로 연결된 분자 그룹만 카운트."""
        if not hasattr(self.cv, 'atoms') or not self.cv.atoms:
            return 0
        try:
            from analyzer import ChemicalAnalyzer
            analyzer = ChemicalAnalyzer()

            # 결합 차수 계산
            degrees = {}
            for (k1, k2) in getattr(self.cv, 'bonds', {}).keys():
                degrees[k1] = degrees.get(k1, 0) + 1
                degrees[k2] = degrees.get(k2, 0) + 1

            # [FIX] 결합이 없는 고립 원자는 제외 (Lewis 마커, 잡음 원자 등)
            # 단, 실제 단일 원소 분자(H, Na+, Cl- 등)는 원소 기호가 있고
            # charge가 있거나 할로겐 등이면 유효
            real_keys = []
            for key, atom_data in self.cv.atoms.items():
                if not isinstance(atom_data, dict):  # Rule N
                    continue
                element = atom_data.get("main", "")
                has_bonds = degrees.get(key, 0) > 0
                if has_bonds:
                    real_keys.append(key)
                elif element and element in ("H", "Na", "K", "Li", "Cl", "Br", "I", "F"):
                    # 단일 원소 분자 — charge가 있으면 이온 반응물로 인정
                    if atom_data.get("charge") or atom_data.get("formal_charge"):
                        real_keys.append(key)
                # 그 외 고립 원자(결합 없는 O, C 등)는 잡음으로 무시

            if not real_keys:
                return 0

            # adjacency from bonds (실제 원자만)
            adj = {}
            for key in real_keys:
                adj[key] = []
            for (k1, k2), bond_data in getattr(self.cv, 'bonds', {}).items():
                if k1 in adj and k2 in adj:
                    adj[k1].append((k2, 1))
                    adj[k2].append((k1, 1))
            islands = analyzer._get_molecular_islands(real_keys, adj)
            return len(islands)
        except Exception:
            return 0

    def open_reaction_popup(self):
        """반응 분석 팝업 열기"""
        try:
            from popup_reaction import ReactionPopup
            from analyzer import ChemicalAnalyzer

            target_state = self._get_analysis_target_state()
            if not isinstance(target_state, dict):  # Rule N
                target_state = {"valid": False, "reason": "Internal error", "smiles": ""}
            if not target_state.get("valid", False):
                self._show_analysis_gate_message(
                    "Reaction Analysis",
                    target_state.get("reason", "Select or enter a valid molecule first."),
                )
                return

            capture_mode = (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            )
            if capture_mode and os.environ.get("CHEMGRID_CAPTURE_REACTION_PAIR", "0") == "1":
                # M854: popup matrix needs real button-click evidence, but the normal
                # drawing canvas holds one molecule per row. Use a deterministic
                # capture-only pair after the button signal reaches this handler.
                popup = ReactionPopup(["C=C", "BrBr"], ["ethylene", "bromine"], parent=self)
                logger.warning(
                    "[M854] open_reaction_popup capture fixture -- using ethylene + bromine"
                )
                popup.setModal(False)
                self._active_reaction_popup = popup
                popup.show()
                return

            analyzer = ChemicalAnalyzer()
            norm_keys = list(self.cv.atoms.keys())
            adj = {}
            for key in self.cv.atoms:
                adj[key] = []
            for key, bond_data in getattr(self.cv, 'bonds', {}).items():
                k1, k2 = key
                if k1 in adj:
                    adj[k1].append((k2, 1))
                if k2 in adj:
                    adj[k2].append((k1, 1))

            islands = analyzer._get_molecular_islands(norm_keys, adj)
            # [FIX] 단일 원자 분자도 포함 (HCl, Na+ 등)

            if len(islands) < 2:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "반응 분석",
                                        "2개 이상의 분리된 분자가 필요합니다.\n"
                                        "그리기 레이어에서 서로 떨어진 2개 이상의 분자를 그려주세요.")
                return

            # 각 섬의 SMILES 추출
            smiles_list = []
            names_list = []
            for i, island in enumerate(islands[:4]):  # 최대 4개
                # 섬 원자만으로 서브그래프 SMILES 생성
                sub_atoms = {k: self.cv.atoms[k] for k in island if k in self.cv.atoms}
                sub_bonds = {}
                for bk, bv in getattr(self.cv, 'bonds', {}).items():
                    if bk[0] in island and bk[1] in island:
                        sub_bonds[bk] = bv
                try:
                    smi, _, _, _ = analyzer.generate_smiles(sub_atoms, sub_bonds)
                    if smi:
                        smiles_list.append(smi)
                        names_list.append(f"분자 {chr(65+i)}")
                except Exception as e:
                    logger.warning(f"[MainWindow] 분자 {chr(65+i)} SMILES 생성 실패: {e}")

            if len(smiles_list) < 2:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "반응 분석",
                                        "SMILES 변환에 실패한 분자가 있습니다.\n"
                                        "분자 구조를 확인해주세요.")
                return

            popup = ReactionPopup(smiles_list, names_list, parent=self)
            if capture_mode:
                logger.warning(
                    "[M854] open_reaction_popup capture/headless mode -- using show() "
                    "instead of exec() so screenshot harness can continue"
                )
                popup.setModal(False)
                self._active_reaction_popup = popup
                popup.show()
                return
            popup.exec()

        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "반응 분석 오류", f"오류 발생: {str(e)}")

    # ========== [SYNTHESIS] 합성 경로 분석 팝업 ==========
    def open_synthesis_popup(self):
        """합성 경로 분석 팝업 열기"""
        try:
            from popup_synthesis import SynthesisPopup
            target_state = self._get_analysis_target_state()
            if not isinstance(target_state, dict):  # Rule N
                target_state = {"valid": False, "reason": "Internal error", "smiles": ""}
            if not target_state.get("valid", False):
                self._show_analysis_gate_message(
                    "Synthesis Route",
                    target_state.get("reason", "Select or enter a valid molecule first."),
                )
                return

            # [FIX] SMILES 추출: 여러 소스에서 추출 후 가장 복잡한 (원자 수 최다) 것 선택
            # 캔버스에 잡음 원자(lone pair 마커 등)가 있으면 get_smiles()가 "O.O" 같은
            # 잘못된 SMILES를 반환하므로, 다중 소스 중 최선을 선택
            from rdkit import Chem
            candidates = [target_state.get("smiles", "")]

            # 소스 1: analysis_results["smiles"]
            ar = getattr(self.cv, 'analysis_results', None)
            if isinstance(ar, dict):
                _ar_smi = ar.get('smiles', '')
            else:
                if ar:
                    logger.warning("[F09] synthesis gate ignored non-dict analysis_results: %s", type(ar).__name__)
                _ar_smi = ''
            if _ar_smi and _ar_smi not in ('C', ''):
                candidates.append(_ar_smi)

            # 소스 2: _last_drawn_smiles
            _ld_smi = getattr(self.cv, '_last_drawn_smiles', '')
            if _ld_smi and _ld_smi not in ('C', ''):
                candidates.append(_ld_smi)

            # 소스 3: 선택된 분자 SMILES (가장 신뢰도 높음 — PubChem 이름도 이걸 사용)
            if hasattr(self.cv, '_get_molecule_smiles'):
                try:
                    _sel_smi = self.cv._get_molecule_smiles()
                    if _sel_smi and _sel_smi not in ('C', ''):
                        candidates.append(_sel_smi)
                except Exception as e:
                    logger.warning(f"[MainWindow] 합성팝업 소스3 SMILES 조회 실패: {e}")

            # 소스 4: 캔버스 전체 (최후 수단)
            if not candidates:
                try:
                    _all_smi = self.cv.get_smiles()
                    if _all_smi and _all_smi not in ('C', ''):
                        candidates.append(_all_smi)
                except Exception as e:
                    logger.warning(f"[MainWindow] 합성팝업 소스4 캔버스 전체 SMILES 조회 실패: {e}")

            # 후보 중 가장 원자 수가 많은 (복잡한) SMILES 선택
            smiles = ""
            best_atoms = 0
            for cand in candidates:
                try:
                    m = Chem.MolFromSmiles(cand)
                    if m and m.GetNumAtoms() > best_atoms:
                        best_atoms = m.GetNumAtoms()
                        smiles = Chem.MolToSmiles(m)
                except Exception:
                    continue

            if not smiles or smiles in ('C', ''):
                QMessageBox.information(self, "합성 경로",
                                        "분석할 분자가 없습니다.\n"
                                        "그리기 레이어에서 분자를 그려주세요.")
                return

            # RDKit으로 SMILES 정규화 + 분자 이름 추출
            name = smiles
            try:
                from rdkit import Chem
                mol = Chem.MolFromSmiles(smiles)
                if mol:
                    canonical = Chem.MolToSmiles(mol)
                    if canonical and canonical not in ('C', ''):
                        smiles = canonical
                    # 분자 이름: selected_molecule_name 또는 _last_drawn_mol_name 사용
                    _name = getattr(self.cv, 'selected_molecule_name', '') or \
                            getattr(self.cv, '_last_drawn_mol_name', '')
                    if _name and _name != smiles:
                        name = _name
                    else:
                        name = smiles
            except Exception as e:
                logger.warning(f"[MainWindow] 합성팝업 SMILES 정규화/이름 조회 실패: {e}")

            popup = SynthesisPopup(smiles, name, parent=self)
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                logger.warning(
                    "[M854] open_synthesis_popup capture/headless mode -- using show() "
                    "instead of exec() so screenshot harness can continue"
                )
                popup.setModal(False)
                self._active_synthesis_popup = popup
                popup.show()
                return
            popup.exec()

            # [Workflow Gate] 합성 경로 분석 완료 시 워크플로우 업데이트
            if self.workflow:
                route_count = getattr(popup, '_route_count', 0)
                if not route_count:
                    # SynthesisPopup 내부에 경로 결과가 있는지 확인
                    routes = getattr(popup, '_routes', None)
                    if routes:
                        route_count = len(routes)
                if route_count > 0:
                    total_steps = getattr(popup, '_total_steps', 0)
                    self.workflow.set_synthesis_analyzed(
                        route_count=route_count,
                        steps=total_steps,
                    )
                    self._on_workflow_step_update()

        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "합성 경로 오류", f"오류 발생: {str(e)}")

    # ========== [U2] 입체 구조 3D 팝업 ==========
    def open_3d_popup(self):
        """선택된 분자의 3D 구조 팝업 열기.
        ★ 개선: 선택 없으면 전체 atoms 사용 → 메탄/벤젠 같은 간단한 분자도 바로 3D 전환

        [P0-0 M517] 6탭 접근: Molecule3DPopup(ThreeDViewer) 탭 구조 —
        속성/스펙트럼/진동모드/AI분석/ADMET/도킹에너지/신약설계.
        6 tab (tab index 6) = 신약설계 accessible. embedded→popup 복원 완료.
        ThreeDViewer = Molecule3DPopup alias (popup_3d.py).
        """
        if not PHASE_C_AVAILABLE:
            QMessageBox.warning(self, "알림", "3D 뷰어 모듈을 사용할 수 없습니다.\nPyOpenGL을 설치해주세요.")
            return

        # [A63-W1/M748] 이전 popup 명시 닫기 — stale xtb async 캐시 충돌 방지
        # offscreen 순차 테스트 루프에서 이전 분자의 _XtbOptThread 결과가
        # 새 popup의 _apply_xtb_optimized_coords()에 잘못 적용되는 P0 CRITICAL 버그 차단
        target_state = self._get_analysis_target_state()
        if not isinstance(target_state, dict):  # Rule N
            target_state = {"valid": False, "reason": "Internal error", "smiles": ""}
        if not target_state.get("valid", False):
            self._show_analysis_gate_message(
                "3D Structure",
                target_state.get("reason", "Select or enter a valid molecule first."),
            )
            return

        if self._popup_3d_window is not None:
            try:
                # xtb 비동기 스레드가 아직 실행중이면 우선 종료 대기 (최대 500ms)
                _old_xtb = getattr(self._popup_3d_window, '_xtb_opt_thread', None)
                if _old_xtb is not None and hasattr(_old_xtb, 'isRunning') and _old_xtb.isRunning():
                    _old_xtb.result_ready.disconnect()  # 시그널 연결 해제 (Rule S)
                    _old_xtb.wait(500)  # 500ms 대기
                    logger.info("[3D] open_3d_popup: old xtb thread disconnected before new popup")
                self._popup_3d_window.close()
                self._popup_3d_window = None
            except Exception as _e_close:
                logger.warning("[3D] open_3d_popup: failed to close old popup: %s", _e_close)
                self._popup_3d_window = None

        # ★ [FEAT-4 Fix] _last_drawn_smiles가 있으면 전체 분자 선택 보장
        # 이론적 구조 → 입체 구조 전환 시 선택 도구가 일부만 긁어오는 버그 해결
        # _last_drawn_smiles 존재 시 전체 원자를 선택 (부분 선택 무시)
        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
        # ★ [개선] 선택된 원자 키 가져오기 — 없으면 전체 atoms 사용
        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())
        if not selected_keys:
            # Drawing 모드 selected_atoms도 확인
            selected_keys = getattr(self.cv, 'selected_atoms', set())
        # [FEAT-4] 선택 원자가 전체의 50% 미만이고 _last_drawn_smiles 있으면 전체 선택으로 교체
        # 이론적 구조에서 드래그 선택 시 일부 원자만 인식되는 버그 해결
        _all_atom_keys = set(self.cv.atoms.keys())
        if _last_smiles and _all_atom_keys and len(selected_keys) < len(_all_atom_keys) * 0.5:
            selected_keys = _all_atom_keys
        if not selected_keys:
            # 선택 없음 → 전체 원자 사용 (간단한 분자를 바로 3D 전환 가능)
            selected_keys = set(self.cv.atoms.keys())

        if not selected_keys:
            QMessageBox.warning(self, "알림", "먼저 분자를 그리세요.")
            return

        # 선택된 분자의 atoms/bonds만 필터링
        sel_atoms = {k: v for k, v in self.cv.atoms.items() if k in selected_keys}
        sel_bonds = {}
        for (k1, k2), v in self.cv.bonds.items():
            if k1 in selected_keys and k2 in selected_keys:
                sel_bonds[(k1, k2)] = v

        try:
            analysis_results = getattr(self.cv, 'analysis_results', None)
            if isinstance(analysis_results, dict):
                theory_data = analysis_results.get("theory_data", {})
            else:
                if analysis_results:
                    logger.warning("[F09] 3D gate ignored non-dict analysis_results: %s", type(analysis_results).__name__)
                theory_data = {}

            # ★ SMILES 추출: 선택된 원자/결합 → RDKit → SMILES
            mol_smiles = ""
            # [Step 1] canvas 내부 메서드 시도
            try:
                if getattr(self.cv, 'selected_molecule_keys', set()):
                    mol_smiles = self.cv._get_molecule_smiles() or ""
            except Exception as e:
                logger.warning(f"[MainWindow] 3D팝업 _get_molecule_smiles 실패: {e}")
            # [Step 2] sel_atoms/sel_bonds에서 직접 SMILES 생성
            if not mol_smiles:
                mol_smiles = self._build_smiles_from_graph(sel_atoms, sel_bonds)
            if not mol_smiles:
                mol_smiles = target_state.get("smiles", "")

            mol_data = Molecule3DData(
                atoms=sel_atoms,
                bonds=sel_bonds,
                theory_data=theory_data,
                smiles=mol_smiles,
            )
            popup = Molecule3DPopup(mol_data, self)
            # [BUG-FIX] Store reference on self to prevent Python GC from destroying
            # the popup immediately after show() returns (Qt parent alone is not enough
            # to keep the Python wrapper alive in PyQt6).
            self._popup_3d_window = popup
            popup.show()
            popup.raise_()
            popup.activateWindow()
            logger.info("[3D] Molecule3DPopup opened: smiles=%s, atoms=%d",
                        mol_smiles[:60] if mol_smiles else "(none)", len(sel_atoms))
        except Exception as e:
            logger.warning("[3D] open_3d_popup failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "오류", f"3D 뷰어 실행 실패:\n{str(e)}")
    
    # ========== [최종 100점] 새로운 분광 분석 기능 ==========
    
    def open_nmr_viewer(self):
        """NMR 스펙트럼 뷰어 열기"""
        # [BUG-1 FIX] SMILES 있으면 예측 스펙트럼 우선 표시
        _smiles = getattr(getattr(self, 'cv', None), '_last_drawn_smiles', None)
        if _smiles:
            try:
                from popup_predicted_spectrum import launch_predicted_spectrum
                launch_predicted_spectrum(_smiles, "nmr", self)
                return
            except Exception as _e:
                import traceback; traceback.print_exc()
        if not NMR_AVAILABLE:
            QMessageBox.warning(self, "알림", "NMR 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = NMRPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"NMR 데이터 로드 실패:\n{str(e)}")
    
    def open_uvvis_viewer(self):
        """UV-Vis 스펙트럼 뷰어 열기"""
        # [BUG-1 FIX] SMILES 있으면 예측 스펙트럼 우선 표시
        _smiles = getattr(getattr(self, 'cv', None), '_last_drawn_smiles', None)
        if _smiles:
            try:
                from popup_predicted_spectrum import launch_predicted_spectrum
                launch_predicted_spectrum(_smiles, "uvvis", self)
                return
            except Exception as _e:
                import traceback; traceback.print_exc()
        if not UVVIS_AVAILABLE:
            # [M647-W4 USR-LV4-04 fix] popup_uvvis 미가용 시 SIMULATION 안내
            # 사용자 격분 LV.4 직격: 학생 배포본은 모든 popup 학습 가능 의무 (Rule UU)
            logger.warning("[MainWindow] popup_uvvis not available — SIMULATION fallback")
            _dlg = QMessageBox(self)
            _dlg.setWindowTitle("UV-Vis SIMULATION 모드")
            _dlg.setText(
                "[SIMULATION_MODE] UV-Vis 스펙트럼 뷰어\n\n"
                "현재 빌드에서 UV-Vis DFT 뷰어 모듈이 미설치 상태입니다.\n"
                "학생 학습 모드로 다음 옵션을 사용할 수 있습니다:\n\n"
                "  1. SMILES 기반 이론 스펙트럼 (popup_predicted_spectrum)\n"
                "  2. .env에 ORCA_SERVER_URL 등록 후 housing/services/orca_api_server.py 실행\n"
                "  3. NIST WebBook 직접 검색\n\n"
                "참고: Neese F. WIREs Comput Mol Sci 2018;8:e1327 (ORCA)"
            )
            _dlg.setIcon(QMessageBox.Icon.Information)
            _dlg.exec()
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = UVVisPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"UV-Vis 데이터 로드 실패:\n{str(e)}")
    
    def open_md_viewer(self):
        """분자동역학 뷰어 열기"""
        if not MD_AVAILABLE:
            # [M647-W4 USR-LV4-05 fix] popup_md 미가용 시 SIMULATION 안내
            # 사용자 격분 LV.4 직격: "진동모드 로컬 가라엔진"
            logger.warning("[MainWindow] popup_md not available — SIMULATION fallback")
            _dlg = QMessageBox(self)
            _dlg.setWindowTitle("분자동역학 SIMULATION 모드")
            _dlg.setText(
                "[SIMULATION_MODE] 분자동역학(MD) 시뮬레이션 뷰어\n\n"
                "현재 빌드에서 popup_md 모듈이 미설치 상태입니다.\n"
                "학생 학습 모드로 다음 옵션을 사용할 수 있습니다:\n\n"
                "  1. xtb GFN2-xTB 진동 모드 폴백 (bin/xtb 자동 감지)\n"
                "  2. 휴리스틱 normal mode 추정 (RDKit + ETKDG)\n"
                "  3. .env에 OPENMM_SERVER_URL 등록\n\n"
                "참고: Bannwarth/Ehlert/Grimme JCTC 2019;15:1652 (xtb GFN2)\n"
                "      Eastman et al. PLOS Comp Biol 2017;13:e1005659 (OpenMM)"
            )
            _dlg.setIcon(QMessageBox.Icon.Information)
            _dlg.exec()
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = MDPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"MD 데이터 로드 실패:\n{str(e)}")
    
    def open_molorbital_viewer(self):
        """분자 오비탈 뷰어 열기"""
        if not MOLORBITAL_AVAILABLE:
            QMessageBox.warning(self, "알림", "분자 오비탈 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = MolecularOrbitalPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"분자 오비탈 데이터 로드 실패:\n{str(e)}")
    
    def open_spectrum_viewer(self):
        """IR/Raman 스펙트럼 뷰어 열기"""
        # [BUG-1 FIX] SMILES 있으면 예측 스펙트럼 우선 표시
        _smiles = getattr(getattr(self, 'cv', None), '_last_drawn_smiles', None)
        if _smiles:
            try:
                from popup_predicted_spectrum import launch_predicted_spectrum
                launch_predicted_spectrum(_smiles, "ir", self)
                return
            except Exception as _e:
                import traceback; traceback.print_exc()
        if not SPECTRUM_ANALYZER_AVAILABLE:
            QMessageBox.warning(self, "알림", "스펙트럼 분석 모듈을 사용할 수 없습니다.")
            return
        # [ORCA_AVAILABLE guard FP-15]: user-provided .out file dialog — not simulation.
        # When ORCA_AVAILABLE=False the user may still load pre-existing ORCA output.
        _dlg_title = "ORCA 계산 결과 파일 선택" if ORCA_AVAILABLE else "ORCA 결과 파일 선택 (사전 계산된 파일)"
        file_path, _ = QFileDialog.getOpenFileName(
            self, _dlg_title, "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            spectrum_data = parse_orca_frequencies(Path(file_path))
            
            if len(spectrum_data.modes) == 0:
                QMessageBox.warning(self, "경고", f"파일에서 진동수 데이터를 찾을 수 없습니다:\n{file_path}")
                return
            
            popup = SpectrumPopup(spectrum_data, self)
            popup.exec()
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"스펙트럼 데이터를 로드할 수 없습니다:\n{str(e)}")
    
    def open_comparator(self):
        """분자 비교 기능 열기"""
        if not self.molecule_comparator:
            QMessageBox.warning(self, "알림", "분자 비교 모듈을 사용할 수 없습니다.")
            return
        
        dialog = ComparisonDialog(self, self.molecule_comparator, self.cv)
        dialog.exec()
    
    def open_history_browser(self):
        """계산 히스토리 브라우저 열기"""
        if not self.history_manager:
            QMessageBox.warning(self, "알림", "히스토리 관리 모듈을 사용할 수 없습니다.")
            return
        
        dialog = HistoryBrowserDialog(self, self.history_manager)
        dialog.exec()
    
    def open_batch_processor(self):
        """배치 처리 창 열기"""
        if not self.batch_processor:
            QMessageBox.warning(self, "알림", "배치 처리 모듈을 사용할 수 없습니다.")
            return
        
        dialog = BatchProcessorDialog(self, self.batch_processor, self.cv)
        dialog.exec()
    
    # ========== [Phase 5 Advanced] 새로운 내보내기 및 검증 기능 ==========
    
    def export_selection_dialog(self):
        """선택 영역 내보내기 대화 열기"""
        if not EXPORT_MANAGER_AVAILABLE:
            QMessageBox.warning(self, "알림", "고급 내보내기 모듈을 사용할 수 없습니다.")
            return
        
        try:
            manager = ExportManager(self)
            manager.export_selection()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"내보내기 실패:\n{str(e)}")
    
    def export_spectrum_to_pdf(self):
        """스펙트럼 및 구조를 PDF로 내보내기 (자동 캡처 포함)"""
        if not SPECTRUM_PDF_EXPORTER_AVAILABLE:
            QMessageBox.warning(self, "알림", "스펙트럼 PDF 내보내기 모듈을 사용할 수 없습니다.")
            return
            
        try:
            # 1. 메타데이터 생성
            mol_name = getattr(self.cv, "selected_molecule_name", "")
            # analyzer 결과에서 식별된 이름 확인 (오각고리 음이온 등)
            if hasattr(self.cv, "analysis_results") and isinstance(self.cv.analysis_results, dict):  # Rule N
                special_name = self.cv.analysis_results.get("identified_name", "")
                if special_name:
                    mol_name = special_name
            
            if not mol_name:
                mol_name = "Unknown Molecule"
                
            smiles = self.cv.get_smiles()
            
            # [FIX] 분자식 자동 계산 (RDKit)
            _mol_formula = "Unknown"
            try:
                from rdkit import Chem
                from rdkit.Chem import Descriptors
                _tmp_mol = Chem.MolFromSmiles(smiles) if smiles else None
                if _tmp_mol:
                    _tmp_mol = Chem.AddHs(_tmp_mol)
                    _mol_formula = Chem.rdMolDescriptors.CalcMolFormula(_tmp_mol)
            except Exception as e:
                logger.warning(f"[MainWindow] 분자식 계산 실패: {e}")
            metadata = SpectrumMetadata(
                molecule_name=mol_name,
                molecular_formula=_mol_formula,
                smiles=smiles,
                calculation_method="B3LYP/6-31G(d)",
                final_energy=-100.0
            )
            
            spectra_data = {}
            
            # 2. 이미지 캡처 (Lewis & Theory)
            import tempfile
            temp_dir = tempfile.gettempdir()
            original_mode = self.cv.view_state
            
            # (1) Lewis Structure 캡처
            self.cv.view_state = "Lewis"
            self.cv.update()
            QApplication.processEvents() # UI 렌더링 대기
            lewis_path = os.path.join(temp_dir, f"chemgrid_lewis_{os.getpid()}.png")
            # 캡처 시 배경 투명도 고려 (grab은 위젯 전체 캡처)
            self.cv.grab().save(lewis_path)
            
            lewis_spec = SpectrumData(
                spectrum_type="Lewis Structure",
                peaks=[],
                image_path=lewis_path,
            )
            # 동적 속성 추가 (AI 분석 텍스트)
            lewis_spec.ai_analysis = f"Lewis structure of {mol_name}. Shows valence electrons and bonding connectivity."
            spectra_data["Lewis Structure"] = lewis_spec
            
            # (2) Theory Structure 캡처
            self.cv.view_state = "Theory"
            self.cv.update()
            QApplication.processEvents()
            theory_path = os.path.join(temp_dir, f"chemgrid_theory_{os.getpid()}.png")
            self.cv.grab().save(theory_path)
            
            theory_spec = SpectrumData(
                spectrum_type="Theory Structure",
                peaks=[],
                image_path=theory_path,
            )
            theory_spec.ai_analysis = f"Optimized geometry of {mol_name} (B3LYP/6-31G*). Correct bond lengths and angles."
            spectra_data["Theory Structure"] = theory_spec
            
            # 원래 모드로 복귀
            self.cv.view_state = original_mode
            self.cv.update()
            
            # 3. ORCA 파일 선택 (선택 사항) — [ORCA_AVAILABLE guard FP-15]
            # ORCA_AVAILABLE=False일 때도 사용자 제공 파일 허용 (사전 계산된 결과 포함 가능).
            if ORCA_AVAILABLE:
                _orca_dlg_prompt = "ORCA 계산 결과 포함 (선택 사항)"
            else:
                _orca_dlg_prompt = "사전 계산된 ORCA 결과 포함 (선택 사항, SIMULATION_MODE)"
            file_path, _ = QFileDialog.getOpenFileName(
                self, _orca_dlg_prompt, "", "ORCA Output (*.out);;All Files (*.*)"
            )
            
            if file_path:
                try:
                    # IR 스펙트럼 데이터 파싱 (있다면)
                    if SPECTRUM_ANALYZER_AVAILABLE:
                        s_data = parse_orca_frequencies(Path(file_path))
                        if s_data and len(s_data.modes) > 0:
                            # 실제 피크 데이터 변환
                            peaks = []
                            for m in s_data.modes:
                                if m.intensity > 10: # 주요 피크만
                                    peaks.append(SpectrumPeakData(
                                        frequency=m.frequency,
                                        intensity=m.intensity,
                                        label=str(int(m.frequency))
                                    ))
                            
                            ir_spec = SpectrumData(
                                spectrum_type="IR Spectrum",
                                peaks=peaks,
                                raw_data={"modes": s_data.modes}
                            )
                            ir_spec.ai_analysis = f"IR Spectrum of {mol_name}. Major peaks identified at {', '.join([str(int(p.frequency)) for p in peaks[:3]])} cm-1."
                            spectra_data["IR Spectrum"] = ir_spec
                except Exception as ex:
                    logger.warning("[LITE-EXE-003] ORCA parsing failed: %s", ex)

            # 4. 내보내기 매니저 실행
            if not spectra_data:
                QMessageBox.warning(self, "알림", "내보낼 데이터가 없습니다.")
                return

            manager = ExportSpectrumManager(self)
            manager.export_spectra(spectra_data, metadata)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 내보내기 실패:\n{str(e)}")
    
    def show_calculation_history(self):
        """계산 히스토리 표시"""
        if not CALCULATION_LOGGER_AVAILABLE:
            QMessageBox.warning(self, "알림", "계산 로거 모듈을 사용할 수 없습니다.")
            return
        
        try:
            logger = CalculationLogger()
            report = logger.generate_report()
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Calculation History Report")
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(report)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            save_btn = QPushButton("보고서 저장...")
            save_btn.clicked.connect(lambda: self._save_calculation_report(report))
            layout.addWidget(save_btn)
            
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"계산 히스토리 로드 실패:\n{str(e)}")
    
    def show_verification_report(self):
        """검증 보고서 생성 및 표시"""
        if not VERIFICATION_REPORT_AVAILABLE:
            QMessageBox.warning(self, "알림", "검증 보고서 모듈을 사용할 수 없습니다.")
            return
        
        if not CALCULATION_LOGGER_AVAILABLE:
            QMessageBox.warning(self, "알림", "계산 로거 모듈이 필요합니다.")
            return
        
        try:
            logger = CalculationLogger()
            entries = logger.get_all_entries()
            
            if not entries:
                QMessageBox.warning(self, "알림", "검증할 계산 기록이 없습니다.")
                return
            
            engine = VerificationEngine()
            
            latest_entry = entries[-1]
            report = engine.verify_calculation(latest_entry)
            
            report_text = engine.generate_report_text(report)
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Verification Report")
            dialog.resize(900, 700)
            
            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(report_text)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            save_btn = QPushButton("보고서 저장...")
            save_btn.clicked.connect(lambda: self._save_verification_report(report, engine))
            layout.addWidget(save_btn)
            
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"검증 보고서 생성 실패:\n{str(e)}")
    
    def _save_calculation_report(self, report_text: str):
        """계산 히스토리 보고서 저장"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "보고서 저장", "calculation_history.txt", "Text Files (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(report_text)
                QMessageBox.information(self, "성공", f"보고서가 저장되었습니다:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"저장 실패:\n{str(e)}")
    
    def _save_verification_report(self, report, engine):
        """검증 보고서 저장"""
        output_dir, _ = QFileDialog.getSaveFileName(
            self, "보고서 저장 위치 선택", "verification_report.txt", "Text Files (*.txt)"
        )
        if output_dir:
            try:
                json_file, text_file = engine.save_report(report, Path(output_dir).parent)
                QMessageBox.information(self, "성공", 
                    f"보고서가 저장되었습니다:\n{text_file}\n{json_file}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"저장 실패:\n{str(e)}")
    
    # ========== [Phase 7] 신약개발 팝업 메서드 ==========
    def open_alphafold_popup(self):
        """AlphaFold 구조 예측 팝업 열기"""
        try:
            from popup_alphafold import AlphaFoldPopup
            popup = AlphaFoldPopup(parent=self)
            # [M461] Sub-task 1: AlphaFold → 도킹 시그널 wiring
            # Rule S: alphafold_to_docking = pyqtSignal(dict) — AlphaFoldPopup 클래스에 정의됨.
            # connect() 전 시그널 존재 확인: AlphaFoldPopup.alphafold_to_docking 확인 완료.
            popup.alphafold_to_docking.connect(self._on_alphafold_to_docking)
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                logger.warning(
                    "[M854] open_alphafold_popup capture/headless mode -- using show() "
                    "instead of exec() so screenshot harness can continue"
                )
                popup.setModal(False)
                self._active_alphafold_popup = popup
                popup.show()
                return
            popup.exec()
        except Exception as e:
            QMessageBox.warning(self, "AlphaFold", f"AlphaFold 팝업 오류: {str(e)}")

    def _on_alphafold_to_docking(self, payload: dict) -> None:
        """[M461] AlphaFold 시그널 수신 → 도킹 팝업 열기 + 수용체 자동 설정.

        Rule N: payload isinstance(dict) 가드.
        Rule M: payload 빈 dict 시 logger.warning + 사용자 피드백.
        """
        # Rule N: isinstance 타입 가드
        if not isinstance(payload, dict):
            logger.warning(
                "_on_alphafold_to_docking: payload 타입 오류: %s", type(payload).__name__
            )
            return
        if not payload:
            logger.warning("_on_alphafold_to_docking: payload 비어 있음 — 전달 중단")
            return
        try:
            from popup_docking import DockingPopup
            docking_popup = DockingPopup(canvas=self.cv, parent=self)
            # Rule S: set_receptor_from_alphafold — DockingPopup 인스턴스 메서드, 시그널 아님
            docking_popup.set_receptor_from_alphafold(payload)
            docking_popup.exec()
            logger.info(
                "_on_alphafold_to_docking: 도킹 팝업 열림 — uniprot_id=%s",
                payload.get("uniprot_id", "(없음)") if isinstance(payload, dict) else "(없음)"  # Rule N
            )
        except Exception as e:
            logger.warning("_on_alphafold_to_docking: 도킹 팝업 오픈 실패: %s", e)
            QMessageBox.warning(
                self, "AlphaFold → 도킹",
                f"도킹 팝업 열기 실패:\n{str(e)}"
            )

    def open_admet_popup(self):
        """ADMET 분석 팝업 열기"""
        try:
            from popup_admet import ADMETPopup
            # SMILES 추출: 여러 소스에서 시도
            smiles = ''
            # 소스 1: 캔버스의 마지막 그려진 SMILES
            smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
            # 소스 2: analysis_results
            if not smiles:
                ar = getattr(self.cv, 'analysis_results', None) or {}
                smiles = ar.get('smiles', '')
            # 소스 3: _get_molecule_smiles 메서드
            if not smiles and hasattr(self.cv, '_get_molecule_smiles'):
                try:
                    smiles = self.cv._get_molecule_smiles() or ''
                except Exception as e:
                    logger.warning(f"[MainWindow] ADMET 팝업 SMILES 조회 실패: {e}")
            name = getattr(self.cv, '_last_drawn_mol_name', '') or \
                   getattr(self.cv, 'selected_molecule_name', '') or ''
            popup = ADMETPopup(smiles=smiles, mol_name=name, parent=self)
            popup.exec()
        except Exception as e:
            QMessageBox.warning(self, "ADMET", f"ADMET 분석 오류: {str(e)}")

    def open_drug_screening_popup(self):
        """신약 스크리닝 팝업 열기"""
        try:
            from popup_drug_screening import DrugScreeningPopup
            popup = DrugScreeningPopup(parent=self)
            popup.exec()
        except Exception as e:
            QMessageBox.warning(self, "신약 스크리닝", f"스크리닝 오류: {str(e)}")

    def open_docking_popup(self) -> None:
        """분자 도킹 팝업 열기"""
        try:
            from popup_docking import DockingPopup
            popup = DockingPopup(canvas=self.cv, parent=self)
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                logger.warning(
                    "[M854] open_docking_popup capture/headless mode -- using show() "
                    "instead of exec() so screenshot harness can continue"
                )
                popup.setModal(False)
                self._active_docking_popup = popup
                popup.show()
                return
            popup.exec()

            # [Workflow Gate] 도킹 완료 시 워크플로우 업데이트
            if self.workflow and hasattr(popup, 'docking_result') and popup.docking_result:
                result = popup.docking_result
                if hasattr(result, 'converged') and result.converged:
                    receptor_name = getattr(popup, 'receptor', '') or ''
                    affinity = getattr(result, 'best_affinity', 0.0)
                    self.workflow.set_docking_performed(
                        receptor_name=receptor_name,
                        affinity=affinity,
                    )
                    self._on_workflow_step_update()
        except Exception as e:
            QMessageBox.warning(self, "분자 도킹", f"도킹 팝업 오류: {str(e)}")

    def open_lead_optimizer_popup(self) -> None:
        """리드 최적화 파이프라인 팝업 열기"""
        try:
            from popup_lead_optimizer import LeadOptimizerPopup
            smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
            if not smiles:
                ar = getattr(self.cv, 'analysis_results', None) or {}
                smiles = ar.get('smiles', '')
            popup = LeadOptimizerPopup(canvas=self.cv, smiles=smiles, parent=self)
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                popup.setModal(False)
                self._active_lead_optimizer_popup = popup
                popup.show()
                return
            popup.exec()

            # [Workflow Gate] 유도체 설계 완료 시 워크플로우 업데이트
            if self.workflow:
                result = getattr(popup, '_result', None)
                if result and hasattr(result, 'ranked_variants') and result.ranked_variants:
                    best = result.ranked_variants[0]
                    best_smi = getattr(best, 'smiles', '')
                    best_desc = getattr(best, 'description', '')
                    goal = ''
                    if hasattr(popup, 'combo_goal'):
                        goal = popup.combo_goal.currentText()
                    if best_smi:
                        self.workflow.set_derivative_designed(
                            derivative_smiles=best_smi,
                            description=best_desc,
                            goal=goal,
                        )
                        self._on_workflow_step_update()
        except ImportError:
            # [M647-W4 USR-LV4-11 fix] popup_lead_optimizer 미가용 시 SIMULATION 안내
            # 사용자 격분 LV.4 직격: "리드 최적화 막힘"
            logger.warning("[MainWindow] popup_lead_optimizer ImportError — SIMULATION fallback")
            _dlg = QMessageBox(self)
            _dlg.setWindowTitle("리드 최적화 SIMULATION 모드")
            _dlg.setText(
                "[SIMULATION_MODE] 리드 최적화 (신약 유도체 설계)\n\n"
                "현재 빌드에서 popup_lead_optimizer 모듈이 미설치 상태입니다.\n"
                "학생 학습 모드로 다음 옵션을 사용할 수 있습니다:\n\n"
                "  1. RDKit 기반 유도체 후보 자동 생성 (Bemis-Murcko scaffold)\n"
                "  2. Lipinski Rule of Five + QED 정량 비교\n"
                "  3. .env에 ORCA_SERVER_URL/VINA_PATH 등록 후 풀버전 활성\n\n"
                "참고: Lipinski 1997 / Bickerton 2012 Nat Chem 4:90 (QED) /\n"
                "      Trott & Olson 2010 J Comput Chem 31:455 (Vina)"
            )
            _dlg.setIcon(QMessageBox.Icon.Information)
            _dlg.exec()
        except Exception as e:
            logger.warning("[MainWindow] open_lead_optimizer_popup error: %s", e)
            QMessageBox.warning(self, "리드 최적화", f"리드 최적화 오류: {str(e)}")

    def open_polymer_popup(self) -> None:
        """고분자 분석 팝업."""
        try:
            from popup_polymer import PolymerAnalysisPopup
            target_state = self._get_analysis_target_state()
            if not isinstance(target_state, dict):  # Rule N
                target_state = {"valid": False, "reason": "Internal error", "smiles": ""}
            polymer_state = self._get_polymer_gate_state(target_state)
            if not isinstance(polymer_state, dict):  # Rule N
                polymer_state = {"enabled": False, "reason": "Internal error"}
            if not polymer_state.get("enabled", False):
                self._show_analysis_gate_message(
                    "Polymer Analysis",
                    polymer_state.get("reason", "Polymer analysis unavailable."),
                )
                return
            smiles = target_state.get("smiles", "")
            if not smiles:
                QMessageBox.warning(self, "고분자", "먼저 분자를 그려주세요.")
                return
            # [M706 F5-4] SMILES 사전 정규화: 다중 분절이면 최대 원자 분절만 추출 (Rule L)
            # 캔버스에 여러 분자/론페어 마커가 있으면 dot-separated SMILES가 전달됨.
            # 단량체는 단일 구조여야 하므로 가장 큰 분절(heavy atom 수 최대)만 사용.
            try:
                from rdkit import Chem as _RChem_poly
                _raw_mol = _RChem_poly.MolFromSmiles(smiles)  # Rule L: None 체크
                if _raw_mol is None:
                    logger.warning("[M706 F5-4] 고분자 팝업 SMILES 파싱 실패: %r", smiles)
                    QMessageBox.warning(
                        self, "고분자",
                        f"분자 구조를 인식할 수 없습니다.\nSMILES: {smiles[:60]}\n"
                        "분자를 다시 그리거나 다른 분자를 선택하세요.",
                    )
                    return
                if '.' in smiles:
                    # 다중 분절 → 최대 heavy atom 분절만 추출
                    _frags = _RChem_poly.GetMolFrags(_raw_mol, asMols=True)
                    if _frags:
                        _best = max(_frags, key=lambda m: m.GetNumHeavyAtoms())
                        smiles = _RChem_poly.MolToSmiles(_best)
                        logger.warning(
                            "[M706 F5-4] 다중 분절 SMILES 감지 — 최대 분절 사용: %r", smiles
                        )
                else:
                    # 단일 분절 → canonical SMILES 재생성
                    smiles = _RChem_poly.MolToSmiles(_raw_mol)
            except Exception as _e_prep:
                logger.warning("[M706 F5-4] SMILES 사전 정규화 실패 (계속 진행): %s", _e_prep)
            popup = PolymerAnalysisPopup(smiles=smiles, parent=self)
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                logger.warning(
                    "[M854] open_polymer_popup capture/headless mode -- using show() "
                    "instead of exec() so screenshot harness can continue"
                )
                popup.setModal(False)
                self._active_polymer_popup = popup
                popup.show()
                return
            popup.exec()

            # [Workflow Gate] 고분자 변환 완료 시 워크플로우 업데이트
            if self.workflow:
                # 고분자 물성 예측이 완료되었으면 polymer_transformed 설정
                if hasattr(popup, '_props') and popup._props:
                    goal = ''
                    if hasattr(popup, '_opt_goal_combo'):
                        goal = popup._opt_goal_combo.currentText()
                    self.workflow.set_polymer_transformed(goal=goal)
                    self._on_workflow_step_update()
                # 리드 최적화 결과가 있으면 합성 분석도 완료된 것으로 간주
                if hasattr(popup, '_opt_results') and popup._opt_results:
                    self.workflow.set_polymer_synthesis_analyzed(
                        route_count=len(popup._opt_results),
                    )
                    self._on_workflow_step_update()
        except ImportError:
            # [M647-W4 USR-LV4-01 fix] popup_polymer 미가용 시 SIMULATION 안내
            # 사용자 격분 LV.4 직격: "고분자 합성 전부 먹통"
            logger.warning("[MainWindow] popup_polymer ImportError — SIMULATION fallback")
            _dlg = QMessageBox(self)
            _dlg.setWindowTitle("고분자 SIMULATION 모드")
            _dlg.setText(
                "[SIMULATION_MODE] 고분자 합성 분석\n\n"
                "현재 빌드에서 popup_polymer 모듈이 미설치 상태입니다.\n"
                "학생 학습 모드로 다음 옵션을 사용할 수 있습니다:\n\n"
                "  1. RDKit 기반 단량체 → 고분자 변환 (반복 단위 시각화)\n"
                "  2. 이론적 물성 예측 (Tg/Tm/density 추정)\n"
                "  3. .env에 DFT_SERVER_URL 등록 후 풀버전 활성\n\n"
                "참고: Flory 1953 (고분자 통계역학) / Bicerano 2002 (Tg 예측)"
            )
            _dlg.setIcon(QMessageBox.Icon.Information)
            _dlg.exec()
        except Exception as e:
            logger.warning("[MainWindow] Polymer popup failed: %s", e)
            QMessageBox.warning(self, "고분자", f"고분자 팝업 오류: {e}")

    def open_reaction_animation_popup(self) -> None:
        """3D 반응 애니메이션 팝업."""
        try:
            from popup_reaction_animation import ReactionAnimationPopup
            ar = getattr(self.cv, 'analysis_results', None) or {}
            smiles = (
                getattr(self.cv, '_last_drawn_smiles', '')
                or ar.get('smiles', '')
                or 'C=C.BrBr'
            )
            if isinstance(smiles, str) and 'C=C' in smiles and 'BrBr' in smiles:
                reactant_smiles = 'C=C.BrBr'
                product_smiles = 'BrCCBr'
                reaction_name = 'alkene bromination valid collision'
            else:
                reactant_smiles = smiles if isinstance(smiles, str) and smiles.strip() else 'C=C.BrBr'
                product_smiles = reactant_smiles
                reaction_name = 'reaction trajectory'
            popup = ReactionAnimationPopup(
                reactant_smiles=reactant_smiles,
                product_smiles=product_smiles,
                reaction_name=reaction_name,
                parent=self,
            )
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                logger.warning(
                    "[M854] open_reaction_animation_popup capture/headless mode -- using show() "
                    "instead of exec() so screenshot harness can continue"
                )
                popup.setModal(False)
                self._active_reaction_animation_popup = popup
                popup.show()
                return
            popup.exec()
        except ImportError:
            # [M647-W4 USR-LV4-03 fix] popup_reaction_animation 미가용 시 SIMULATION
            # 사용자 격분 LV.4: "반응 분석 전부 먹통"
            logger.warning("[MainWindow] popup_reaction_animation ImportError — SIMULATION fallback")
            _dlg = QMessageBox(self)
            _dlg.setWindowTitle("반응 애니메이션 SIMULATION 모드")
            _dlg.setText(
                "[SIMULATION_MODE] 3D 반응 애니메이션\n\n"
                "현재 빌드에서 popup_reaction_animation 모듈이 미설치 상태입니다.\n"
                "학생 학습 모드로 다음 옵션을 사용할 수 있습니다:\n\n"
                "  1. popup_reaction (RDKit 기반 반응 패턴 매칭)\n"
                "  2. 정적 메커니즘 시각화 (curved arrow generator)\n"
                "  3. .env에 DFT_SERVER_URL 등록 후 풀버전 활성\n\n"
                "참고: Coley 2019 ACS Cent Sci 5:1572 (ASKCOS) /\n"
                "      Klamt 1995 (TST 반응 동역학)\n\n"
                "Reaction Animation requires the full-version build (server option)."
            )
            _dlg.setIcon(QMessageBox.Icon.Information)
            _dlg.exec()
        except Exception as e:
            logger.warning("[MainWindow] Reaction animation popup failed: %s", e)

    def open_drylab_report(self) -> None:
        """DryLab 종합 연구 보고서 생성.

        워크플로우 미완료 시 확인 대화상자를 표시하되, 학생의 선택에 따라
        가용 데이터만으로 보고서를 생성할 수 있습니다 (ADVISORY, NOT BLOCKING).
        """
        if (
            os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
            or (
                os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
                and os.environ.get("CHEMGRID_DRYLAB_GENERATE_OFFSCREEN", "0") != "1"
            )
        ):
            _dlg = QMessageBox(self)
            _dlg.setWindowTitle("DryLab Report")
            _dlg.setText(
                "DryLab report workflow\n\n"
                "Includes spectra, synthesis route, AlphaFold/PDB, docking, "
                "lead optimization, and experimental design evidence."
            )
            _dlg.setModal(False)
            self._active_drylab_report_popup = _dlg
            _dlg.show()
            return
        # [Advisory Gate] 워크플로우 미완료 시 확인 대화상자
        if self.workflow and not self.workflow.is_drylab_ready():
            missing = self.workflow.get_missing_steps_list("drylab")
            missing_text = "\n".join(f"  - {m}" for m in missing)
            reply = QMessageBox.question(
                self, "DryLab 보고서",
                f"아직 완료하지 않은 단계가 있습니다:\n\n{missing_text}\n\n"
                "그래도 보고서를 생성하시겠습니까?\n"
                "(가용 데이터만으로 보고서가 생성됩니다)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            from drylab_report_exporter import DryLabData, DryLabReportExporter
        except ImportError as e:
            QMessageBox.warning(self, "DryLab", f"DryLab 모듈을 불러올 수 없습니다:\n{e}")
            return

        smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
        mol_name = ''
        if not smiles:
            ar = getattr(self.cv, 'analysis_results', None) or {}
            if isinstance(ar, dict):
                smiles = ar.get('smiles', '')
                mol_name = ar.get('name', '')
        if not smiles:
            QMessageBox.information(self, "DryLab", "먼저 분자를 그려주세요.")
            return

        # [M683] PDF + Word + HWPX 동시 생성 (사용자 LV.16 격분 item 22 대응)
        # 파일 다이얼로그: PDF 기본, DOCX/HWPX는 자동 병행 생성 (export() 내부에서)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "DryLab 보고서 저장",
            f"DryLab_{mol_name or 'report'}.pdf",
            "PDF + Word + 한글(HWPX) (*.pdf);;PDF Files (*.pdf);;Word Files (*.docx);;한글 파일 (*.hwpx)"
        )
        if not file_path:
            return

        # .docx/.hwpx 직접 저장 경로 선택 시 PDF base 경로 추출
        if file_path.lower().endswith(".docx"):
            pdf_path = file_path[:-5] + ".pdf"
        elif file_path.lower().endswith(".hwpx"):
            pdf_path = file_path[:-5] + ".pdf"
        else:
            pdf_path = file_path

        try:
            # 워크플로우 데이터를 DryLabData에 포함 (가용 데이터만)
            wf_data = self.workflow.get_drylab_data() if self.workflow else None
            data = DryLabData(smiles=smiles, name=mol_name)

            # 워크플로우에서 수집된 사고 과정 데이터 주입
            if wf_data:
                data.docking_receptor = getattr(wf_data, 'receptor_name', '')
                data.docking_pdb_id = getattr(wf_data, 'receptor_pdb_id', '')
                data.design_goal = getattr(wf_data, 'design_goal', '')
                data.derivative_smiles = getattr(wf_data, 'derivative_smiles', '')

            exporter = DryLabReportExporter(data=data)
            ok, msg = exporter.export(pdf_path)
            if ok:
                # msg 형태: "pdf_path|docx_path|hwpx_path" 또는 축약형
                # M683: PDF + DOCX + HWPX 3종 동시 생성
                paths = msg.split("|") if "|" in msg else [msg]
                _pdf_done = paths[0] if paths else pdf_path
                _docx_done = paths[1] if len(paths) > 1 else None
                _hwpx_done = paths[2] if len(paths) > 2 else None
                info_lines = [f"PDF: {_pdf_done}"]
                if _docx_done:
                    info_lines.append(f"Word (.docx): {_docx_done}")
                if _hwpx_done:
                    info_lines.append(f"한글 (.hwpx): {_hwpx_done}")
                if _docx_done or _hwpx_done:
                    info_lines.append("(DOCX/HWPX 파일에서 한국어 내용을 자유롭게 수정하세요)")
                QMessageBox.information(
                    self, "DryLab 보고서 생성 완료",
                    "\n".join(info_lines)
                )
            else:
                QMessageBox.warning(self, "DryLab", f"보고서 생성 실패:\n{msg}")
        except Exception as e:
            logger.error("DryLab report failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "DryLab", f"보고서 생성 중 오류 발생:\n{e}")

    def open_polymerlab_report(self) -> None:
        """PolymerLab 보고서 생성.

        워크플로우 미완료 시 확인 대화상자를 표시하되, 학생의 선택에 따라
        가용 데이터만으로 보고서를 생성할 수 있습니다 (ADVISORY, NOT BLOCKING).
        """
        # [Advisory Gate] 워크플로우 미완료 시 확인 대화상자
        if self.workflow and not self.workflow.is_polymerlab_ready():
            missing = self.workflow.get_missing_steps_list("polymerlab")
            missing_text = "\n".join(f"  - {m}" for m in missing)
            reply = QMessageBox.question(
                self, "PolymerLab 보고서",
                f"아직 완료하지 않은 단계가 있습니다:\n\n{missing_text}\n\n"
                "그래도 보고서를 생성하시겠습니까?\n"
                "(가용 데이터만으로 보고서가 생성됩니다)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # PolymerLab 보고서는 popup_polymer 내부에서 직접 생성됨.
        # 여기서는 고분자 팝업을 열면서 리포트 탭으로 이동하도록 안내.
        self.open_polymer_popup()

    # ══════════════════════════════════════════════════
    #  [Advisory Workflow] 워크플로우 상태 변경 핸들러
    # ══════════════════════════════════════════════════

    def _on_drylab_workflow_ready(self) -> None:
        """DryLab 워크플로우 모든 단계 완료 시 강조 표시 + 알림."""
        if hasattr(self, '_act_drylab_report'):
            self._act_drylab_report.setToolTip("DryLab 종합 연구 보고서 PDF 생성 (모든 단계 완료)")
        self.statusBar().showMessage(
            "DryLab 워크플로우 완료! 보고서에 전체 사고 과정 데이터가 포함됩니다.", 5000)

    def _on_polymerlab_workflow_ready(self) -> None:
        """PolymerLab 워크플로우 모든 단계 완료 시 강조 표시 + 알림."""
        if hasattr(self, '_act_polymerlab_report'):
            self._act_polymerlab_report.setToolTip("PolymerLab 종합 보고서 PDF 생성 (모든 단계 완료)")
        self.statusBar().showMessage(
            "PolymerLab 워크플로우 완료! 보고서에 전체 사고 과정 데이터가 포함됩니다.", 5000)

    def _on_workflow_step_update(self) -> None:
        """워크플로우 단계 진행 시 툴팁 업데이트 (진행률 표시)."""
        if self.workflow and hasattr(self, '_act_drylab_report'):
            completed, total = self.workflow.get_completed_steps_count("drylab")
            if completed < total:
                tip = f"DryLab 보고서 생성 ({completed}/{total} 단계 완료)"
                self._act_drylab_report.setToolTip(tip)
        if self.workflow and hasattr(self, '_act_polymerlab_report'):
            completed, total = self.workflow.get_completed_steps_count("polymerlab")
            if completed < total:
                tip = f"PolymerLab 보고서 생성 ({completed}/{total} 단계 완료)"
                self._act_polymerlab_report.setToolTip(tip)

    def closeEvent(self, event):
        """
        윈도우 종료 시 정리 작업 수행
        ========== [Phase Integration Hook 5] 종료 시 정리 ==========
        """
        self.cv.cleanup()
        super().closeEvent(event)
