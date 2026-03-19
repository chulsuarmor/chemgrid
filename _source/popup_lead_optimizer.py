# popup_lead_optimizer.py — Lead Optimization Pipeline Wizard
"""
ChemGrid: 리드 최적화 파이프라인 위저드
7-page QStackedWidget wizard:
  1. Setup (기준 분자, 최적화 목표, 표적 수용체)
  2. Strategy Confirmation (전략 확인)
  3. Variant Generation (유도체 생성)
  4. Batch Docking (도킹 진행)
  5. ADMET Screening (ADMET 스크리닝)
  6. Results (결과 랭킹 테이블)
  7. Winner Detail (상세 분석)
"""

import math
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── PyQt6 ────────────────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QComboBox, QSpinBox, QSlider, QCheckBox, QMessageBox,
        QGroupBox, QFormLayout, QProgressBar, QTextEdit, QTableWidget,
        QTableWidgetItem, QWidget, QHeaderView, QSizePolicy, QStackedWidget,
        QScrollArea, QApplication,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
    from PyQt6.QtGui import QFont, QColor, QBrush, QPixmap, QImage, QPainter
    PYQT_OK = True
except ImportError:
    PYQT_OK = False

# ── lead_optimizer (core engine) ─────────────────────────────────────────
try:
    from lead_optimizer import (
        MoleculeVariantGenerator, translate_goal, call_llm,
        score_variant, calculate_sa_score, inject_api_keys,
        save_api_key, get_api_key, VariantResult, ModificationStrategy,
        LeadOptimizationResult, PRESET_GOALS, RDKIT_OK, GROQ_OK, GEMINI_OK,
    )
except ImportError:
    RDKIT_OK = GROQ_OK = GEMINI_OK = False
    PRESET_GOALS = {}

    class VariantResult:  # type: ignore[no-redef]
        pass

    class ModificationStrategy:  # type: ignore[no-redef]
        pass

    class LeadOptimizationResult:  # type: ignore[no-redef]
        pass

    class MoleculeVariantGenerator:  # type: ignore[no-redef]
        pass

    def translate_goal(g, s):  # type: ignore[no-redef]
        return None

    def call_llm(p, s=""):  # type: ignore[no-redef]
        return ""

    def score_variant(v, b):  # type: ignore[no-redef]
        return 0.0

    def calculate_sa_score(s):  # type: ignore[no-redef]
        return 5.0

    def inject_api_keys():  # type: ignore[no-redef]
        pass

    def save_api_key(k, v):  # type: ignore[no-redef]
        pass

    def get_api_key(k):  # type: ignore[no-redef]
        return ""

# ── docking_data ─────────────────────────────────────────────────────────
try:
    from docking_data import RECEPTOR_DATABASE, get_receptor_metadata
except ImportError:
    RECEPTOR_DATABASE = {}

    def get_receptor_metadata(pdb_id):  # type: ignore[no-redef]
        return None

# ── optional: ADMET / QED / RDKit ────────────────────────────────────────
try:
    from admet_predictor import predict_admet
    ADMET_OK = True
except ImportError:
    ADMET_OK = False

    def predict_admet(smiles, mol_name=""):  # type: ignore[no-redef]
        return None

try:
    from drug_screening import calculate_qed
    QED_OK = True
except ImportError:
    QED_OK = False

    def calculate_qed(smiles):  # type: ignore[no-redef]
        return None

# RDKit for 2D depiction
_RDKIT_DRAW_OK = False
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Draw, Crippen, rdMolDescriptors
    _RDKIT_DRAW_OK = True
except ImportError:
    pass


# ════════════════════════════════════════════════════════════════════════════
# STYLE CONSTANTS
# ════════════════════════════════════════════════════════════════════════════

_DARK_BG = "#1a1a2e"
_DARK_SURFACE = "#16213e"
_ACCENT = "#0f3460"
_TEXT = "#e0e0e0"
_TEXT_DIM = "#999999"
_TIER_A = "#4caf50"
_TIER_B = "#ff9800"
_TIER_C = "#f44336"

DARK_STYLESHEET = f"""
QDialog, QWidget {{
    background-color: {_DARK_BG};
    color: {_TEXT};
}}
QGroupBox {{
    border: 1px solid #2a2a4e;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: {_TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QLabel {{
    color: {_TEXT};
}}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QSlider {{
    background-color: {_DARK_SURFACE};
    color: {_TEXT};
    border: 1px solid #2a2a4e;
    border-radius: 4px;
    padding: 4px 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {_DARK_SURFACE};
    color: {_TEXT};
    selection-background-color: {_ACCENT};
}}
QTableWidget {{
    background-color: {_DARK_SURFACE};
    color: {_TEXT};
    gridline-color: #2a2a4e;
    border: 1px solid #2a2a4e;
    selection-background-color: {_ACCENT};
}}
QTableWidget::item {{
    padding: 4px;
}}
QHeaderView::section {{
    background-color: {_ACCENT};
    color: {_TEXT};
    padding: 6px;
    border: none;
    font-weight: bold;
}}
QProgressBar {{
    background-color: {_DARK_SURFACE};
    border: 1px solid #2a2a4e;
    border-radius: 4px;
    text-align: center;
    color: {_TEXT};
}}
QProgressBar::chunk {{
    background-color: #e94560;
    border-radius: 3px;
}}
QPushButton {{
    background-color: {_ACCENT};
    color: {_TEXT};
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #1a4a7a;
}}
QPushButton:disabled {{
    background-color: #333;
    color: #666;
}}
QCheckBox {{
    color: {_TEXT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
}}
QScrollArea {{
    border: none;
}}
"""


# ════════════════════════════════════════════════════════════════════════════
# UTILITY: mol → QPixmap
# ════════════════════════════════════════════════════════════════════════════

def _smiles_to_pixmap(smiles: str, width: int = 260, height: int = 200) -> Optional["QPixmap"]:
    """Render SMILES to QPixmap via RDKit. Returns None on failure."""
    if not _RDKIT_DRAW_OK or not PYQT_OK:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        # Use MolToQPixmap if available, else fall back to MolToImage
        try:
            from rdkit.Chem.Draw import MolToQPixmap
            return MolToQPixmap(mol, size=(width, height))
        except (ImportError, AttributeError):
            pass
        # Fallback: PIL Image → QPixmap
        img = Draw.MolToImage(mol, size=(width, height))
        if img is None:
            return None
        data = img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


def _smiles_to_small_pixmap(smiles: str, size: int = 64) -> Optional["QPixmap"]:
    """Small thumbnail for table cells."""
    return _smiles_to_pixmap(smiles, size, size)


# ════════════════════════════════════════════════════════════════════════════
# SIMPLIFIED DOCKING SCORER (no Vina required)
# ════════════════════════════════════════════════════════════════════════════

def _simple_binding_score(smiles: str, receptor_pdb: str = "") -> float:
    """Heuristic binding score (kcal/mol, negative = better).

    Uses molecular descriptors that correlate with binding:
    - MW similarity to drug-like range
    - LogP in optimal range (1-4)
    - H-bond donors/acceptors matching
    - Aromatic rings for pi-stacking
    """
    if not _RDKIT_DRAW_OK:
        return -5.0  # fallback
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return -3.0
        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        n_aromatic = rdMolDescriptors.CalcNumAromaticRings(mol)
        n_rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol)
        tpsa = Descriptors.TPSA(mol)

        # Base score: drug-like molecules score around -6 to -8
        score = -4.0

        # MW bonus (optimal 300-500 Da)
        if 300 <= mw <= 500:
            score -= 1.5
        elif 200 <= mw <= 600:
            score -= 0.8

        # LogP bonus (optimal 1-4)
        if 1.0 <= logp <= 4.0:
            score -= 1.2
        elif 0 <= logp <= 5.0:
            score -= 0.5

        # H-bond capacity
        hb_score = min(hbd, 5) * 0.2 + min(hba, 10) * 0.1
        score -= hb_score

        # Aromatic rings (pi-stacking potential)
        score -= min(n_aromatic, 4) * 0.3

        # Flexibility penalty (too flexible = entropy cost)
        if n_rotatable > 10:
            score += (n_rotatable - 10) * 0.15

        # TPSA bonus for pocket matching
        if 40 <= tpsa <= 140:
            score -= 0.5

        # Receptor-specific adjustments
        meta = get_receptor_metadata(receptor_pdb) if receptor_pdb else None
        if meta:
            pocket_vol = meta.pocket_volume_A3
            if pocket_vol > 0:
                # Larger pockets accommodate larger molecules
                if mw > 400 and pocket_vol > 400:
                    score -= 0.5
                elif mw < 300 and pocket_vol < 350:
                    score -= 0.3

        # Clamp to realistic range
        score = max(-12.0, min(-1.0, score))

        # Add small noise for differentiation
        import hashlib
        h = int(hashlib.md5(smiles.encode()).hexdigest()[:8], 16)
        noise = (h % 100 - 50) / 100.0  # -0.5 to +0.5
        score += noise * 0.4

        return round(score, 2)
    except Exception:
        return -5.0


# ════════════════════════════════════════════════════════════════════════════
# PIPELINE WORKER THREAD
# ════════════════════════════════════════════════════════════════════════════

class PipelineWorker(QThread):
    """Runs the full lead optimization pipeline in a background thread."""

    stage_changed = pyqtSignal(str)          # "generating", "docking", "admet", "ranking"
    progress = pyqtSignal(int, int, str)     # current, total, message
    variant_ready = pyqtSignal(object)       # single VariantResult (for live table updates)
    finished = pyqtSignal(object)            # LeadOptimizationResult
    error = pyqtSignal(str)

    def __init__(
        self,
        smiles: str,
        goal: str,
        strategy: "ModificationStrategy",
        receptor_pdb: str,
        n_variants: int,
        enabled_strategies: List[str],
        parent=None,
    ):
        super().__init__(parent)
        self.smiles = smiles
        self.goal = goal
        self.strategy = strategy
        self.receptor_pdb = receptor_pdb
        self.n_variants = n_variants
        self.enabled_strategies = enabled_strategies
        self._stop_flag = False

    def request_stop(self):
        self._stop_flag = True

    # ------------------------------------------------------------------ run
    def run(self):
        try:
            result = LeadOptimizationResult(
                base_smiles=self.smiles,
                goal=self.goal,
                receptor_pdb_id=self.receptor_pdb,
                total_variants=0,
                ranked_variants=[],
            )

            # ── Stage 1: Generate variants ────────────────────────────
            self.stage_changed.emit("generating")
            gen = MoleculeVariantGenerator()
            # Override strategy's strategies list with user selections
            strat_copy = ModificationStrategy(
                name=self.strategy.name,
                name_kr=self.strategy.name_kr,
                description=self.strategy.description,
                strategies=list(self.enabled_strategies),
                preferred_substituents=list(self.strategy.preferred_substituents),
                target_protein=self.receptor_pdb or self.strategy.target_protein,
                rationale=self.strategy.rationale,
            )
            variants = gen.generate_all(self.smiles, self.n_variants, strat_copy)
            if not variants:
                self.error.emit("유도체를 생성할 수 없습니다. SMILES를 확인해 주세요.")
                return
            result.total_variants = len(variants)
            result.stages_completed.append("generating")

            for i, v in enumerate(variants):
                if self._stop_flag:
                    break
                self.progress.emit(i + 1, len(variants), f"유도체 생성: {v.smiles[:40]}")
                self.variant_ready.emit(v)

            if self._stop_flag:
                result.ranked_variants = variants
                self.finished.emit(result)
                return

            # ── Stage 2: Docking / scoring ────────────────────────────
            self.stage_changed.emit("docking")
            base_score = _simple_binding_score(self.smiles, self.receptor_pdb)
            result.base_docking_score = base_score

            for i, v in enumerate(variants):
                if self._stop_flag:
                    break
                self.progress.emit(i + 1, len(variants), f"도킹 스코어링: {v.smiles[:40]}")
                v.docking_score = _simple_binding_score(v.smiles, self.receptor_pdb)

            result.stages_completed.append("docking")

            if self._stop_flag:
                result.ranked_variants = variants
                self.finished.emit(result)
                return

            # ── Stage 3: ADMET + QED ──────────────────────────────────
            self.stage_changed.emit("admet")
            for i, v in enumerate(variants):
                if self._stop_flag:
                    break
                self.progress.emit(i + 1, len(variants), f"ADMET 스크리닝: {v.smiles[:40]}")

                # QED
                if QED_OK:
                    try:
                        qed_result = calculate_qed(v.smiles)
                        if qed_result is not None:
                            v.qed_score = qed_result.qed_score
                    except Exception:
                        pass

                # ADMET
                if ADMET_OK:
                    try:
                        admet_profile = predict_admet(v.smiles)
                        if admet_profile and admet_profile.lipinski:
                            v.admet_pass = admet_profile.lipinski.passes
                            v.admet_violations = admet_profile.lipinski.violations
                        if admet_profile and admet_profile.bbb:
                            v.bbb_score = admet_profile.bbb.score
                    except Exception:
                        pass

            result.stages_completed.append("admet")

            if self._stop_flag:
                result.ranked_variants = variants
                self.finished.emit(result)
                return

            # ── Stage 4: SA Score ─────────────────────────────────────
            self.stage_changed.emit("ranking")
            for i, v in enumerate(variants):
                if self._stop_flag:
                    break
                self.progress.emit(i + 1, len(variants), f"합성 가능성 평가: {v.smiles[:40]}")
                v.sa_score = calculate_sa_score(v.smiles)

            # ── Stage 5: Composite ranking ────────────────────────────
            for v in variants:
                score_variant(v, base_score)

            variants.sort(key=lambda v: v.composite_rank, reverse=True)
            result.ranked_variants = variants
            result.stages_completed.append("ranking")

            self.finished.emit(result)

        except Exception as exc:
            self.error.emit(str(exc))


# ════════════════════════════════════════════════════════════════════════════
# RETROSYNTHESIS WORKER
# ════════════════════════════════════════════════════════════════════════════

class RetrosynthesisWorker(QThread):
    """Runs retrosynthesis in background."""
    finished = pyqtSignal(str)   # formatted text result
    error = pyqtSignal(str)

    def __init__(self, smiles: str, parent=None):
        super().__init__(parent)
        self.smiles = smiles

    def run(self):
        try:
            from retrosynthesis_engine import RetrosynthesisEngine
            engine = RetrosynthesisEngine()
            routes = engine.find_routes(self.smiles, max_depth=6, max_routes=5, timeout_seconds=15.0)
            if not routes:
                self.finished.emit("합성 경로를 찾을 수 없습니다.")
                return
            lines = []
            for ri, route in enumerate(routes):
                lines.append(f"═══ 경로 {ri + 1} (점수: {route.score:.2f}, {route.total_steps}단계) ═══")
                for si, step in enumerate(route.steps):
                    lines.append(f"  [{si + 1}] {step.reaction_name}")
                    lines.append(f"      반응물: {', '.join(step.reactants)}")
                    lines.append(f"      생성물: {step.product}")
                    if hasattr(step, "conditions") and step.conditions:
                        lines.append(f"      조건: {step.conditions}")
                lines.append("")
            self.finished.emit("\n".join(lines))
        except ImportError:
            self.finished.emit("역합성 엔진(retrosynthesis_engine)을 사용할 수 없습니다.")
        except Exception as exc:
            self.error.emit(str(exc))


# ════════════════════════════════════════════════════════════════════════════
# API SETTINGS DIALOG
# ════════════════════════════════════════════════════════════════════════════

class _APISettingsDialog(QDialog):
    """Small dialog for configuring LLM API keys."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 설정")
        self.resize(500, 320)
        self.setStyleSheet(DARK_STYLESHEET)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Groq
        grp_groq = QGroupBox("Groq API (Llama 3.1)")
        gl = QHBoxLayout(grp_groq)
        self.edit_groq = QLineEdit()
        self.edit_groq.setPlaceholderText("gsk_...")
        self.edit_groq.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_groq.setText(get_api_key("GROQ_API_KEY"))
        gl.addWidget(self.edit_groq)
        self.btn_show_groq = QPushButton("표시")
        self.btn_show_groq.setFixedWidth(50)
        self.btn_show_groq.clicked.connect(self._toggle_groq_visibility)
        gl.addWidget(self.btn_show_groq)
        layout.addWidget(grp_groq)

        lbl_groq_link = QLabel('<a href="https://console.groq.com" style="color:#4fc3f7;">console.groq.com</a>')
        lbl_groq_link.setOpenExternalLinks(True)
        layout.addWidget(lbl_groq_link)

        # Gemini
        grp_gemini = QGroupBox("Gemini API")
        gml = QHBoxLayout(grp_gemini)
        self.edit_gemini = QLineEdit()
        self.edit_gemini.setPlaceholderText("AIza...")
        self.edit_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_gemini.setText(get_api_key("GEMINI_API_KEY"))
        gml.addWidget(self.edit_gemini)
        self.btn_show_gemini = QPushButton("표시")
        self.btn_show_gemini.setFixedWidth(50)
        self.btn_show_gemini.clicked.connect(self._toggle_gemini_visibility)
        gml.addWidget(self.btn_show_gemini)
        layout.addWidget(grp_gemini)

        lbl_gemini_link = QLabel('<a href="https://aistudio.google.com" style="color:#4fc3f7;">aistudio.google.com</a>')
        lbl_gemini_link.setOpenExternalLinks(True)
        layout.addWidget(lbl_gemini_link)

        layout.addSpacing(12)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_test = QPushButton("연결 테스트")
        self.btn_test.clicked.connect(self._on_test)
        btn_row.addWidget(self.btn_test)

        self.btn_save = QPushButton("저장")
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #4caf50; }"
        )
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_save)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def _toggle_groq_visibility(self):
        if self.edit_groq.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_groq.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_show_groq.setText("숨김")
        else:
            self.edit_groq.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_show_groq.setText("표시")

    def _toggle_gemini_visibility(self):
        if self.edit_gemini.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_gemini.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_show_gemini.setText("숨김")
        else:
            self.edit_gemini.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_show_gemini.setText("표시")

    def _on_test(self):
        self.lbl_status.setText("테스트 중...")
        self.lbl_status.repaint()
        # Quick test: just try calling LLM with a trivial prompt
        groq_key = self.edit_groq.text().strip()
        gemini_key = self.edit_gemini.text().strip()

        results = []
        if groq_key:
            os.environ["GROQ_API_KEY"] = groq_key
            try:
                resp = call_llm("Say OK", "Reply with exactly: OK")
                if resp:
                    results.append("Groq: 연결 성공")
                else:
                    results.append("Groq: 응답 없음")
            except Exception as e:
                results.append(f"Groq: 실패 ({e})")
        else:
            results.append("Groq: 키 미입력")

        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            try:
                resp = call_llm("Say OK", "Reply with exactly: OK")
                if resp:
                    results.append("Gemini: 연결 성공")
                else:
                    results.append("Gemini: 응답 없음")
            except Exception as e:
                results.append(f"Gemini: 실패 ({e})")
        else:
            results.append("Gemini: 키 미입력")

        self.lbl_status.setText(" | ".join(results))

    def _on_save(self):
        groq_key = self.edit_groq.text().strip()
        gemini_key = self.edit_gemini.text().strip()
        if groq_key:
            save_api_key("GROQ_API_KEY", groq_key)
        if gemini_key:
            save_api_key("GEMINI_API_KEY", gemini_key)
        self.lbl_status.setText("저장 완료")
        inject_api_keys()


# ════════════════════════════════════════════════════════════════════════════
# MAIN WIZARD DIALOG
# ════════════════════════════════════════════════════════════════════════════

class LeadOptimizerPopup(QDialog):
    """7-page wizard for the Lead Optimization Pipeline."""

    # Signal emitted when user clicks "캔버스에 그리기"
    draw_on_canvas = pyqtSignal(str)  # SMILES

    def __init__(self, smiles: str = "", canvas=None, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._initial_smiles = smiles
        self._strategy: Optional[ModificationStrategy] = None
        self._result: Optional[LeadOptimizationResult] = None
        self._worker: Optional[PipelineWorker] = None
        self._retro_worker: Optional[RetrosynthesisWorker] = None
        self._selected_variant: Optional[VariantResult] = None

        self.setWindowTitle("리드 최적화 파이프라인")
        self.resize(1400, 900)
        self.setStyleSheet(DARK_STYLESHEET)

        self._init_ui()
        self._populate_initial()

    # ================================================================ UI BUILD
    def _init_ui(self):
        root = QVBoxLayout(self)

        # Title
        title = QLabel("리드 최적화 파이프라인")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: #e94560; padding: 8px;")
        root.addWidget(title)

        # Stacked widget (7 pages)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self._build_page_setup()          # 0
        self._build_page_strategy()       # 1
        self._build_page_generation()     # 2
        self._build_page_docking()        # 3
        self._build_page_admet()          # 4
        self._build_page_results()        # 5
        self._build_page_detail()         # 6

    # ─────────────────────────── Page 0: Setup ─────────────────────────────
    def _build_page_setup(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # ── 기준 분자 ──
        grp_mol = QGroupBox("기준 분자")
        mol_layout = QVBoxLayout(grp_mol)

        row_smi = QHBoxLayout()
        self.edit_smiles = QLineEdit()
        self.edit_smiles.setPlaceholderText("SMILES를 입력하거나 캔버스에서 가져오세요")
        self.edit_smiles.setReadOnly(True)
        self.edit_smiles.textChanged.connect(self._on_smiles_changed)
        row_smi.addWidget(self.edit_smiles, stretch=1)

        self.btn_from_canvas = QPushButton("캔버스에서 가져오기")
        self.btn_from_canvas.clicked.connect(self._on_fetch_from_canvas)
        row_smi.addWidget(self.btn_from_canvas)

        self.btn_manual_input = QPushButton("직접 입력")
        self.btn_manual_input.setCheckable(True)
        self.btn_manual_input.clicked.connect(self._on_toggle_manual)
        row_smi.addWidget(self.btn_manual_input)

        mol_layout.addLayout(row_smi)

        # 2D preview
        self.lbl_mol_preview = QLabel("구조 미리보기")
        self.lbl_mol_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_mol_preview.setFixedHeight(220)
        self.lbl_mol_preview.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; border: 1px solid #2a2a4e; border-radius: 6px;"
        )
        mol_layout.addWidget(self.lbl_mol_preview)
        layout.addWidget(grp_mol)

        # ── 최적화 목표 ──
        grp_goal = QGroupBox("최적화 목표")
        goal_layout = QVBoxLayout(grp_goal)

        self.combo_goal = QComboBox()
        goal_items = list(PRESET_GOALS.keys()) + ["사용자 정의..."]
        self.combo_goal.addItems(goal_items)
        self.combo_goal.currentTextChanged.connect(self._on_goal_changed)
        goal_layout.addWidget(self.combo_goal)

        self.edit_custom_goal = QLineEdit()
        self.edit_custom_goal.setPlaceholderText("예: 폐암 선택적 억제, LogP 2~4 유지")
        self.edit_custom_goal.setVisible(False)
        goal_layout.addWidget(self.edit_custom_goal)
        layout.addWidget(grp_goal)

        # ── 표적 수용체 ──
        grp_receptor = QGroupBox("표적 수용체")
        rec_layout = QVBoxLayout(grp_receptor)

        self.combo_receptor = QComboBox()
        self.combo_receptor.addItem("(자동 선택)")
        for pdb_id, meta in RECEPTOR_DATABASE.items():
            # Avoid duplicates from alt IDs
            label = f"{meta.name} ({pdb_id})"
            if self.combo_receptor.findText(label) == -1:
                self.combo_receptor.addItem(label, pdb_id)
        rec_layout.addWidget(self.combo_receptor)
        layout.addWidget(grp_receptor)

        # ── Bottom row ──
        bottom = QHBoxLayout()
        self.btn_ai_settings = QPushButton("⚙ AI 설정")
        self.btn_ai_settings.clicked.connect(self._on_open_ai_settings)
        bottom.addWidget(self.btn_ai_settings)

        bottom.addStretch()

        self.btn_next_0 = QPushButton("다음 >")
        self.btn_next_0.setStyleSheet("QPushButton { background-color: #e94560; padding: 10px 30px; }")
        self.btn_next_0.clicked.connect(self._on_next_from_setup)
        bottom.addWidget(self.btn_next_0)
        layout.addLayout(bottom)

        layout.addStretch()
        self.stack.addWidget(page)

    # ─────────────────────── Page 1: Strategy ──────────────────────────────
    def _build_page_strategy(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.lbl_strategy_title = QLabel("전략")
        self.lbl_strategy_title.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(self.lbl_strategy_title)

        self.lbl_strategy_desc = QLabel("")
        self.lbl_strategy_desc.setWordWrap(True)
        self.lbl_strategy_desc.setStyleSheet(f"color: {_TEXT_DIM}; padding: 8px;")
        layout.addWidget(self.lbl_strategy_desc)

        self.lbl_strategy_rationale = QLabel("")
        self.lbl_strategy_rationale.setWordWrap(True)
        self.lbl_strategy_rationale.setStyleSheet("padding: 8px; font-style: italic;")
        layout.addWidget(self.lbl_strategy_rationale)

        # ── 변형 전략 체크박스 ──
        grp_strat = QGroupBox("변형 전략")
        strat_layout = QVBoxLayout(grp_strat)
        self.chk_r_group = QCheckBox("R기 치환 (R-group replacement)")
        self.chk_bioisostere = QCheckBox("등가체 교환 (Bioisostere)")
        self.chk_chain = QCheckBox("사슬 변형 (Chain modification)")
        self.chk_ring = QCheckBox("고리 변형 (Ring modification)")
        for chk in (self.chk_r_group, self.chk_bioisostere, self.chk_chain, self.chk_ring):
            strat_layout.addWidget(chk)
        layout.addWidget(grp_strat)

        # ── 유도체 수 ──
        grp_count = QGroupBox("유도체 수")
        count_layout = QHBoxLayout(grp_count)
        self.slider_count = QSlider(Qt.Orientation.Horizontal)
        self.slider_count.setRange(10, 200)
        self.slider_count.setValue(50)
        self.slider_count.setTickInterval(10)
        self.spin_count = QSpinBox()
        self.spin_count.setRange(10, 200)
        self.spin_count.setValue(50)
        self.slider_count.valueChanged.connect(self.spin_count.setValue)
        self.spin_count.valueChanged.connect(self.slider_count.setValue)
        count_layout.addWidget(self.slider_count, stretch=1)
        count_layout.addWidget(self.spin_count)
        layout.addWidget(grp_count)

        # ── AI 상태 ──
        grp_ai = QGroupBox("AI 상태")
        ai_layout = QVBoxLayout(grp_ai)
        self.lbl_ai_status = QLabel("")
        ai_layout.addWidget(self.lbl_ai_status)
        layout.addWidget(grp_ai)

        # Navigation
        bottom = QHBoxLayout()
        self.btn_prev_1 = QPushButton("< 이전")
        self.btn_prev_1.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        bottom.addWidget(self.btn_prev_1)
        bottom.addStretch()
        self.btn_start_gen = QPushButton("생성 시작 >")
        self.btn_start_gen.setStyleSheet("QPushButton { background-color: #e94560; padding: 10px 30px; }")
        self.btn_start_gen.clicked.connect(self._on_start_pipeline)
        bottom.addWidget(self.btn_start_gen)
        layout.addLayout(bottom)

        layout.addStretch()
        self.stack.addWidget(page)

    # ─────────────────────── Page 2: Generation ────────────────────────────
    def _build_page_generation(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl_title = QLabel("유도체 생성")
        lbl_title.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.progress_gen = QProgressBar()
        layout.addWidget(self.progress_gen)

        self.lbl_gen_status = QLabel("0 / 0 유도체 생성됨")
        layout.addWidget(self.lbl_gen_status)

        self.tbl_gen = QTableWidget()
        self.tbl_gen.setColumnCount(4)
        self.tbl_gen.setHorizontalHeaderLabels(["#", "SMILES", "변형 유형", "상세"])
        self.tbl_gen.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_gen.horizontalHeader().setStretchLastSection(True)
        self.tbl_gen.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_gen.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.tbl_gen, stretch=1)

        self.stack.addWidget(page)

    # ─────────────────────── Page 3: Docking ───────────────────────────────
    def _build_page_docking(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl_title = QLabel("도킹 진행")
        lbl_title.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.progress_dock = QProgressBar()
        layout.addWidget(self.progress_dock)

        self.lbl_dock_time = QLabel("예상 시간: 계산 중...")
        layout.addWidget(self.lbl_dock_time)

        self.txt_dock_log = QTextEdit()
        self.txt_dock_log.setReadOnly(True)
        self.txt_dock_log.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        layout.addWidget(self.txt_dock_log, stretch=1)

        self.btn_dock_stop = QPushButton("조기 중단")
        self.btn_dock_stop.setStyleSheet("QPushButton { background-color: #f44336; }")
        self.btn_dock_stop.clicked.connect(self._on_early_stop)
        layout.addWidget(self.btn_dock_stop)

        self.stack.addWidget(page)

    # ─────────────────────── Page 4: ADMET ─────────────────────────────────
    def _build_page_admet(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl_title = QLabel("ADMET 스크리닝")
        lbl_title.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.progress_admet = QProgressBar()
        layout.addWidget(self.progress_admet)

        self.lbl_admet_lipinski = QLabel("Lipinski 통과: -")
        self.lbl_admet_lipinski.setFont(QFont("", 12))
        layout.addWidget(self.lbl_admet_lipinski)

        self.lbl_admet_bbb = QLabel("BBB 양성: -")
        self.lbl_admet_bbb.setFont(QFont("", 12))
        layout.addWidget(self.lbl_admet_bbb)

        self.lbl_admet_qed = QLabel("평균 QED: -")
        self.lbl_admet_qed.setFont(QFont("", 12))
        layout.addWidget(self.lbl_admet_qed)

        layout.addStretch()
        self.stack.addWidget(page)

    # ─────────────────────── Page 5: Results ───────────────────────────────
    def _build_page_results(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl_title = QLabel("결과")
        lbl_title.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.lbl_result_summary = QLabel("")
        layout.addWidget(self.lbl_result_summary)

        self.tbl_results = QTableWidget()
        self.tbl_results.setColumnCount(9)
        self.tbl_results.setHorizontalHeaderLabels([
            "순위", "구조", "SMILES", "변형", "결합에너지",
            "개선도", "QED", "SA", "티어",
        ])
        self.tbl_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_results.horizontalHeader().setStretchLastSection(True)
        self.tbl_results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_results.setSortingEnabled(True)
        self.tbl_results.doubleClicked.connect(self._on_result_row_clicked)
        layout.addWidget(self.tbl_results, stretch=1)

        # Navigation
        bottom = QHBoxLayout()
        self.btn_back_to_setup = QPushButton("< 처음으로")
        self.btn_back_to_setup.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        bottom.addWidget(self.btn_back_to_setup)
        bottom.addStretch()
        layout.addLayout(bottom)

        self.stack.addWidget(page)

    # ─────────────────────── Page 6: Detail ────────────────────────────────
    def _build_page_detail(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        lbl_title = QLabel("상세 분석")
        lbl_title.setFont(QFont("", 14, QFont.Weight.Bold))
        scroll_layout.addWidget(lbl_title)

        # Structure image
        self.lbl_detail_structure = QLabel("구조")
        self.lbl_detail_structure.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_detail_structure.setFixedHeight(300)
        self.lbl_detail_structure.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; border: 1px solid #2a2a4e; border-radius: 6px;"
        )
        scroll_layout.addWidget(self.lbl_detail_structure)

        # Scores grid
        grp_scores = QGroupBox("점수")
        scores_form = QFormLayout(grp_scores)
        self.lbl_d_smiles = QLabel("-")
        self.lbl_d_smiles.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        scores_form.addRow("SMILES:", self.lbl_d_smiles)
        self.lbl_d_mod_type = QLabel("-")
        scores_form.addRow("변형 유형:", self.lbl_d_mod_type)
        self.lbl_d_mod_detail = QLabel("-")
        self.lbl_d_mod_detail.setWordWrap(True)
        scores_form.addRow("변형 상세:", self.lbl_d_mod_detail)
        self.lbl_d_docking = QLabel("-")
        scores_form.addRow("결합 에너지:", self.lbl_d_docking)
        self.lbl_d_delta = QLabel("-")
        scores_form.addRow("개선도:", self.lbl_d_delta)
        self.lbl_d_qed = QLabel("-")
        scores_form.addRow("QED:", self.lbl_d_qed)
        self.lbl_d_sa = QLabel("-")
        scores_form.addRow("SA Score:", self.lbl_d_sa)
        self.lbl_d_composite = QLabel("-")
        scores_form.addRow("종합 점수:", self.lbl_d_composite)
        self.lbl_d_tier = QLabel("-")
        scores_form.addRow("티어:", self.lbl_d_tier)
        scroll_layout.addWidget(grp_scores)

        # ADMET detail
        grp_admet_d = QGroupBox("ADMET 상세")
        admet_d_layout = QVBoxLayout(grp_admet_d)
        self.lbl_d_admet_pass = QLabel("-")
        admet_d_layout.addWidget(self.lbl_d_admet_pass)
        self.lbl_d_admet_violations = QLabel("-")
        admet_d_layout.addWidget(self.lbl_d_admet_violations)
        self.lbl_d_bbb = QLabel("-")
        admet_d_layout.addWidget(self.lbl_d_bbb)
        scroll_layout.addWidget(grp_admet_d)

        # Docking interaction summary
        grp_dock_d = QGroupBox("도킹 상호작용 요약")
        dock_d_layout = QVBoxLayout(grp_dock_d)
        self.lbl_d_dock_summary = QLabel("간이 스코어링 모드 — 상세 상호작용은 전체 도킹 팝업에서 확인하세요.")
        self.lbl_d_dock_summary.setWordWrap(True)
        dock_d_layout.addWidget(self.lbl_d_dock_summary)
        scroll_layout.addWidget(grp_dock_d)

        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_retro = QPushButton("합성 경로 분석")
        self.btn_retro.clicked.connect(self._on_retrosynthesis)
        btn_row.addWidget(self.btn_retro)

        self.btn_draw_canvas = QPushButton("캔버스에 그리기")
        self.btn_draw_canvas.clicked.connect(self._on_draw_to_canvas)
        btn_row.addWidget(self.btn_draw_canvas)

        self.btn_back_results = QPushButton("< 결과 목록")
        self.btn_back_results.clicked.connect(lambda: self.stack.setCurrentIndex(5))
        btn_row.addWidget(self.btn_back_results)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Retrosynthesis output
        self.txt_retro = QTextEdit()
        self.txt_retro.setReadOnly(True)
        self.txt_retro.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        self.txt_retro.setMaximumHeight(250)
        self.txt_retro.setVisible(False)
        layout.addWidget(self.txt_retro)

        self.stack.addWidget(page)

    # ================================================================ POPULATE
    def _populate_initial(self):
        if self._initial_smiles:
            self.edit_smiles.setText(self._initial_smiles)

    # ================================================================ SLOTS: Page 0
    def _on_smiles_changed(self, text: str):
        text = text.strip()
        if text:
            pm = _smiles_to_pixmap(text, 300, 200)
            if pm:
                self.lbl_mol_preview.setPixmap(pm)
            else:
                self.lbl_mol_preview.setText("구조 미리보기 (SMILES 확인 필요)")
        else:
            self.lbl_mol_preview.setText("구조 미리보기")

    def _on_fetch_from_canvas(self):
        smiles = ""
        parent = self.parent()
        if self._canvas and hasattr(self._canvas, "get_smiles"):
            smiles = self._canvas.get_smiles()
        elif parent and hasattr(parent, "get_smiles"):
            smiles = parent.get_smiles()
        elif parent and hasattr(parent, "canvas") and hasattr(parent.canvas, "get_smiles"):
            smiles = parent.canvas.get_smiles()

        if smiles:
            self.edit_smiles.setReadOnly(False)
            self.edit_smiles.setText(smiles)
            self.edit_smiles.setReadOnly(True)
            self.btn_manual_input.setChecked(False)
        else:
            QMessageBox.information(self, "알림", "캔버스에 분자가 없습니다.")

    def _on_toggle_manual(self, checked: bool):
        self.edit_smiles.setReadOnly(not checked)
        if checked:
            self.edit_smiles.setFocus()

    def _on_goal_changed(self, text: str):
        self.edit_custom_goal.setVisible(text == "사용자 정의...")

    def _on_open_ai_settings(self):
        dlg = _APISettingsDialog(self)
        dlg.exec()

    def _on_next_from_setup(self):
        smiles = self.edit_smiles.text().strip()
        if not smiles:
            QMessageBox.warning(self, "경고", "SMILES를 입력해 주세요.")
            return

        if not RDKIT_OK:
            QMessageBox.warning(self, "경고", "RDKit가 설치되어 있지 않습니다. 유도체 생성이 불가능합니다.")
            return

        # Validate SMILES
        if _RDKIT_DRAW_OK:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                QMessageBox.warning(self, "경고", "유효하지 않은 SMILES입니다.")
                return

        # Determine goal
        goal_text = self.combo_goal.currentText()
        if goal_text == "사용자 정의...":
            goal_text = self.edit_custom_goal.text().strip()
            if not goal_text:
                QMessageBox.warning(self, "경고", "사용자 정의 목표를 입력해 주세요.")
                return

        # Determine receptor
        receptor_pdb = ""
        idx = self.combo_receptor.currentIndex()
        if idx > 0:
            receptor_pdb = self.combo_receptor.itemData(idx) or ""

        # Translate goal → strategy
        self._strategy = translate_goal(goal_text, smiles)
        if self._strategy is None:
            QMessageBox.warning(self, "경고", "전략을 생성할 수 없습니다.")
            return

        if not receptor_pdb and self._strategy.target_protein:
            receptor_pdb = self._strategy.target_protein

        self._goal_text = goal_text
        self._receptor_pdb = receptor_pdb

        # Populate strategy page
        self.lbl_strategy_title.setText(f"전략: {self._strategy.name_kr}")
        self.lbl_strategy_desc.setText(self._strategy.description)
        self.lbl_strategy_rationale.setText(f"근거: {self._strategy.rationale}")

        # Set checkboxes
        strats = self._strategy.strategies
        self.chk_r_group.setChecked("r_group" in strats)
        self.chk_bioisostere.setChecked("bioisostere" in strats)
        self.chk_chain.setChecked("chain" in strats)
        self.chk_ring.setChecked("ring" in strats)

        # AI status
        ai_parts = []
        if GROQ_OK and get_api_key("GROQ_API_KEY"):
            ai_parts.append("Groq (Llama 3.1) 연결됨")
        if GEMINI_OK and get_api_key("GEMINI_API_KEY"):
            ai_parts.append("Gemini 연결됨")
        if not ai_parts:
            ai_parts.append("프리셋 모드 (LLM 미연결)")
        self.lbl_ai_status.setText(" | ".join(ai_parts))

        self.stack.setCurrentIndex(1)

    # ================================================================ SLOTS: Page 1
    def _on_start_pipeline(self):
        smiles = self.edit_smiles.text().strip()
        if not smiles or self._strategy is None:
            return

        # Gather enabled strategies
        enabled = []
        if self.chk_r_group.isChecked():
            enabled.append("r_group")
        if self.chk_bioisostere.isChecked():
            enabled.append("bioisostere")
        if self.chk_chain.isChecked():
            enabled.append("chain")
        if self.chk_ring.isChecked():
            enabled.append("ring")

        if not enabled:
            QMessageBox.warning(self, "경고", "최소 하나의 변형 전략을 선택해 주세요.")
            return

        n_variants = self.spin_count.value()

        # Reset pages
        self.tbl_gen.setRowCount(0)
        self.progress_gen.setValue(0)
        self.progress_dock.setValue(0)
        self.progress_admet.setValue(0)
        self.txt_dock_log.clear()
        self.lbl_gen_status.setText("0 / 0 유도체 생성됨")

        # Move to generation page
        self.stack.setCurrentIndex(2)

        # Start worker
        self._worker = PipelineWorker(
            smiles=smiles,
            goal=self._goal_text,
            strategy=self._strategy,
            receptor_pdb=self._receptor_pdb,
            n_variants=n_variants,
            enabled_strategies=enabled,
            parent=self,
        )
        self._worker.stage_changed.connect(self._on_stage_changed)
        self._worker.progress.connect(self._on_pipeline_progress)
        self._worker.variant_ready.connect(self._on_variant_ready)
        self._worker.finished.connect(self._on_pipeline_finished)
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

        self.btn_start_gen.setEnabled(False)

    # ================================================================ PIPELINE CALLBACKS
    def _on_stage_changed(self, stage: str):
        stage_map = {
            "generating": (2, "유도체 생성 중..."),
            "docking": (3, "도킹 스코어링 중..."),
            "admet": (4, "ADMET 스크리닝 중..."),
            "ranking": (4, "종합 랭킹 계산 중..."),
        }
        page_idx, msg = stage_map.get(stage, (2, stage))
        self.stack.setCurrentIndex(page_idx)

        if stage == "docking":
            self.txt_dock_log.append(f"[{stage}] {msg}")
        elif stage == "admet":
            pass
        elif stage == "ranking":
            self.txt_dock_log.append("[ranking] 종합 점수 계산 시작")

    def _on_pipeline_progress(self, current: int, total: int, message: str):
        page_idx = self.stack.currentIndex()

        pct = int(current / max(1, total) * 100) if total > 0 else 0

        if page_idx == 2:  # generation
            self.progress_gen.setValue(pct)
            self.lbl_gen_status.setText(f"{current} / {total} 유도체 생성됨")
        elif page_idx == 3:  # docking
            self.progress_dock.setValue(pct)
            self.lbl_dock_time.setText(f"진행: {current}/{total}")
            if current % 10 == 0 or current == total:
                self.txt_dock_log.append(f"  [{current}/{total}] {message}")
        elif page_idx == 4:  # admet
            self.progress_admet.setValue(pct)

    def _on_variant_ready(self, variant):
        """Add a variant to the generation table (live update)."""
        row = self.tbl_gen.rowCount()
        self.tbl_gen.setRowCount(row + 1)
        self.tbl_gen.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        smi_display = variant.smiles if len(variant.smiles) <= 60 else variant.smiles[:57] + "..."
        self.tbl_gen.setItem(row, 1, QTableWidgetItem(smi_display))
        self.tbl_gen.setItem(row, 2, QTableWidgetItem(variant.modification_type))
        self.tbl_gen.setItem(row, 3, QTableWidgetItem(variant.modification_detail))

    def _on_pipeline_finished(self, result):
        self._result = result
        self.btn_start_gen.setEnabled(True)

        if not result.ranked_variants:
            QMessageBox.warning(self, "알림", "생성된 유도체가 없습니다.")
            self.stack.setCurrentIndex(0)
            return

        # Update ADMET summary on page 4
        variants = result.ranked_variants
        n_lipinski = sum(1 for v in variants if v.admet_pass)
        n_bbb = sum(1 for v in variants if v.bbb_score > 0.5)
        avg_qed = sum(v.qed_score for v in variants) / max(1, len(variants))
        self.lbl_admet_lipinski.setText(f"Lipinski 통과: {n_lipinski}개 / {len(variants)}개")
        self.lbl_admet_bbb.setText(f"BBB 양성: {n_bbb}개")
        self.lbl_admet_qed.setText(f"평균 QED: {avg_qed:.3f}")

        # Populate results table (page 5)
        self._populate_results_table(variants)

        # Move to results
        self.stack.setCurrentIndex(5)

    def _on_pipeline_error(self, msg: str):
        self.btn_start_gen.setEnabled(True)
        QMessageBox.critical(self, "파이프라인 오류", msg)
        self.stack.setCurrentIndex(0)

    def _on_early_stop(self):
        if self._worker:
            self._worker.request_stop()
            self.txt_dock_log.append("[!] 조기 중단 요청됨 — 부분 결과를 사용합니다.")

    # ================================================================ RESULTS TABLE
    def _populate_results_table(self, variants: List):
        self.tbl_results.setSortingEnabled(False)
        self.tbl_results.setRowCount(len(variants))

        n_a = sum(1 for v in variants if v.tier == "A")
        n_b = sum(1 for v in variants if v.tier == "B")
        n_c = sum(1 for v in variants if v.tier == "C")
        self.lbl_result_summary.setText(
            f"총 {len(variants)}개 유도체 | "
            f'<span style="color:{_TIER_A}">A: {n_a}</span>  '
            f'<span style="color:{_TIER_B}">B: {n_b}</span>  '
            f'<span style="color:{_TIER_C}">C: {n_c}</span>'
        )

        for row, v in enumerate(variants):
            # 순위
            rank_item = QTableWidgetItem()
            rank_item.setData(Qt.ItemDataRole.DisplayRole, str(row + 1))
            rank_item.setData(Qt.ItemDataRole.UserRole, float(row + 1))
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_results.setItem(row, 0, rank_item)

            # 구조 (thumbnail)
            pm = _smiles_to_small_pixmap(v.smiles, 48)
            struct_item = QTableWidgetItem()
            if pm:
                struct_item.setData(Qt.ItemDataRole.DecorationRole, pm)
            else:
                struct_item.setText("—")
            self.tbl_results.setItem(row, 1, struct_item)
            self.tbl_results.setRowHeight(row, 54)

            # SMILES
            smi_text = v.smiles if len(v.smiles) <= 50 else v.smiles[:47] + "..."
            smi_item = QTableWidgetItem(smi_text)
            smi_item.setToolTip(v.smiles)
            self.tbl_results.setItem(row, 2, smi_item)

            # 변형
            self.tbl_results.setItem(row, 3, QTableWidgetItem(v.modification_type))

            # 결합에너지
            dock_item = QTableWidgetItem(f"{v.docking_score:.2f}")
            dock_item.setData(Qt.ItemDataRole.UserRole, float(v.docking_score))
            dock_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_results.setItem(row, 4, dock_item)

            # 개선도
            delta_item = QTableWidgetItem(f"{v.docking_delta:+.2f}")
            delta_item.setData(Qt.ItemDataRole.UserRole, float(v.docking_delta))
            delta_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if v.docking_delta < 0:
                delta_item.setForeground(QBrush(QColor(_TIER_A)))
            self.tbl_results.setItem(row, 5, delta_item)

            # QED
            qed_item = QTableWidgetItem(f"{v.qed_score:.3f}")
            qed_item.setData(Qt.ItemDataRole.UserRole, float(v.qed_score))
            qed_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_results.setItem(row, 6, qed_item)

            # SA
            sa_item = QTableWidgetItem(f"{v.sa_score:.1f}")
            sa_item.setData(Qt.ItemDataRole.UserRole, float(v.sa_score))
            sa_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_results.setItem(row, 7, sa_item)

            # 티어
            tier_colors = {"A": _TIER_A, "B": _TIER_B, "C": _TIER_C}
            tier_item = QTableWidgetItem(v.tier)
            tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tier_item.setForeground(QBrush(QColor(tier_colors.get(v.tier, _TEXT_DIM))))
            tier_item.setFont(QFont("", 11, QFont.Weight.Bold))
            self.tbl_results.setItem(row, 8, tier_item)

        self.tbl_results.setSortingEnabled(True)
        self.tbl_results.resizeColumnsToContents()
        # Make structure column wider
        self.tbl_results.setColumnWidth(1, 56)

    # ================================================================ DETAIL PAGE
    def _on_result_row_clicked(self, index):
        row = index.row()
        if self._result is None:
            return
        variants = self._result.ranked_variants
        if row < 0 or row >= len(variants):
            return

        v = variants[row]
        self._selected_variant = v
        self._show_detail(v)
        self.stack.setCurrentIndex(6)

    def _show_detail(self, v):
        # Structure
        pm = _smiles_to_pixmap(v.smiles, 400, 280)
        if pm:
            self.lbl_detail_structure.setPixmap(pm)
        else:
            self.lbl_detail_structure.setText(v.smiles)

        self.lbl_d_smiles.setText(v.smiles)
        self.lbl_d_mod_type.setText(v.modification_type)
        self.lbl_d_mod_detail.setText(v.modification_detail)
        self.lbl_d_docking.setText(f"{v.docking_score:.2f} kcal/mol")
        self.lbl_d_delta.setText(f"{v.docking_delta:+.2f} kcal/mol")

        delta_color = _TIER_A if v.docking_delta < 0 else _TIER_C
        self.lbl_d_delta.setStyleSheet(f"color: {delta_color};")

        self.lbl_d_qed.setText(f"{v.qed_score:.3f}")
        self.lbl_d_sa.setText(f"{v.sa_score:.1f} (1=쉬움, 10=어려움)")
        self.lbl_d_composite.setText(f"{v.composite_rank:.3f}")

        tier_colors = {"A": _TIER_A, "B": _TIER_B, "C": _TIER_C}
        self.lbl_d_tier.setText(v.tier)
        self.lbl_d_tier.setStyleSheet(f"color: {tier_colors.get(v.tier, _TEXT)}; font-weight: bold; font-size: 16px;")

        # ADMET detail
        admet_str = "통과" if v.admet_pass else "미통과"
        self.lbl_d_admet_pass.setText(f"Lipinski: {admet_str}")
        self.lbl_d_admet_violations.setText(f"Lipinski 위반: {v.admet_violations}건")
        bbb_str = f"BBB 투과 확률: {v.bbb_score:.2f}"
        if v.bbb_score > 0.7:
            bbb_str += " (높음)"
        elif v.bbb_score > 0.4:
            bbb_str += " (중간)"
        else:
            bbb_str += " (낮음)"
        self.lbl_d_bbb.setText(bbb_str)

        # Hide retro output
        self.txt_retro.setVisible(False)
        self.txt_retro.clear()

    def _on_retrosynthesis(self):
        if self._selected_variant is None:
            return
        smiles = self._selected_variant.smiles
        self.txt_retro.setVisible(True)
        self.txt_retro.setText("합성 경로 분석 중...")
        self.btn_retro.setEnabled(False)

        self._retro_worker = RetrosynthesisWorker(smiles, self)
        self._retro_worker.finished.connect(self._on_retro_done)
        self._retro_worker.error.connect(self._on_retro_error)
        self._retro_worker.start()

    def _on_retro_done(self, text: str):
        self.txt_retro.setText(text)
        self.btn_retro.setEnabled(True)

    def _on_retro_error(self, msg: str):
        self.txt_retro.setText(f"오류: {msg}")
        self.btn_retro.setEnabled(True)

    def _on_draw_to_canvas(self):
        if self._selected_variant is None:
            return
        smiles = self._selected_variant.smiles

        # Walk up parent chain to find MainWindow with _draw_smiles_on_canvas
        sent = False
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, '_draw_smiles_on_canvas'):
                try:
                    widget._draw_smiles_on_canvas(smiles, "Lead Opt Variant")
                    sent = True
                except Exception:
                    pass
                break
            widget = widget.parent() if hasattr(widget, 'parent') and callable(widget.parent) else None

        if not sent:
            # Emit signal as fallback for external handling
            self.draw_on_canvas.emit(smiles)

        if sent:
            QMessageBox.information(self, "알림", f"캔버스에 분자를 그렸습니다.\n{smiles}")
        else:
            QMessageBox.warning(self, "알림",
                                f"캔버스에 직접 그리기를 할 수 없습니다.\nSMILES를 클립보드에 복사합니다.\n{smiles}")
            try:
                QApplication.clipboard().setText(smiles)
            except Exception:
                pass
