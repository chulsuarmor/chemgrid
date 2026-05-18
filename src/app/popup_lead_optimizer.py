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

import csv
import io
import math
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── PyQt6 ────────────────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QComboBox, QSpinBox, QSlider, QCheckBox, QMessageBox,
        QGroupBox, QFormLayout, QProgressBar, QTextEdit, QTableWidget,
        QTableWidgetItem, QWidget, QHeaderView, QSizePolicy, QStackedWidget,
        QScrollArea, QApplication, QProgressDialog,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl, QTimer
    from PyQt6.QtGui import (
        QFont, QFontDatabase, QColor, QBrush, QPixmap, QImage, QPainter,
        QDesktopServices,
    )
    PYQT_OK = True
except ImportError:
    PYQT_OK = False

# ── Korean Qt font (G3 pattern from popup_polymer.py — M1390) ────────────
_QT_KR_FONT = "Malgun Gothic"
_QT_KR_FONT_READY = False


def _ensure_qt_korean_font_ready() -> str:
    """Load a Korean Qt font for popup/offscreen captures before widgets paint."""
    global _QT_KR_FONT, _QT_KR_FONT_READY
    if _QT_KR_FONT_READY:
        return _QT_KR_FONT
    if not PYQT_OK:
        return _QT_KR_FONT
    app = QApplication.instance()
    if app is None:
        return _QT_KR_FONT
    for font_path in (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"):
        try:
            if os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        _QT_KR_FONT = families[0]
                        break
        except Exception as exc:
            logger.warning("[M1390] lead optimizer Korean font load failed: %s", exc)
    app.setFont(QFont(_QT_KR_FONT, 10))
    _QT_KR_FONT_READY = True
    return _QT_KR_FONT


# ── lead_optimizer (core engine) ─────────────────────────────────────────
try:
    from lead_optimizer import (
        MoleculeVariantGenerator, translate_goal, call_llm,
        score_variant, calculate_sa_score, inject_api_keys,
        save_api_key, get_api_key, VariantResult, ModificationStrategy,
        LeadOptimizationResult, PRESET_GOALS, GOAL_RECEPTOR_MAP,
        RDKIT_OK, GROQ_OK, GEMINI_OK, export_lead_optimizer_report,
    )
except ImportError:
    RDKIT_OK = GROQ_OK = GEMINI_OK = False
    PRESET_GOALS = {}
    GOAL_RECEPTOR_MAP = {}

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

    def export_lead_optimizer_report(*args, **kwargs):  # type: ignore[no-redef]
        return False, "lead_optimizer report export is unavailable"

# ── docking_data ─────────────────────────────────────────────────────────
try:
    from docking_data import (
        RECEPTOR_DATABASE,
        get_receptor_metadata,
        get_receptor_dropdown_options,
    )
except ImportError:
    RECEPTOR_DATABASE = {}

    def get_receptor_metadata(pdb_id):  # type: ignore[no-redef]
        return None

    def get_receptor_dropdown_options():  # type: ignore[no-redef]
        return []

try:
    from docking_interface import (
        get_docking_engine_disclosure,
        build_selected_receptor_external_context,
    )
except ImportError:
    def get_docking_engine_disclosure():  # type: ignore[no-redef]
        return {
            "engine": "RDKit descriptor heuristic",
            "basis": "SIMULATION_HEURISTIC_NOT_VINA",
            "simulation_mode": True,
            "is_real_vina_available": False,
            "detail": (
                "AutoDock Vina is unavailable; lead optimization scores are "
                "RDKit descriptor heuristic estimates, not confirmed Vina runs."
            ),
        }

    def build_selected_receptor_external_context(receptor_id, alphafold_payload=None):  # type: ignore[no-redef]
        return {"receptor": {"selected_pdb_id": receptor_id, "external_links": {}}}


LEAD_ENGINE_DISCLOSURE_TEXT = (
    # M1345: Rule GG + Rule Q bilingual — Korean prefix mandatory.
    "[시뮬레이션 모드 / SIMULATION_MODE]\n"
    "엔진 기반: 리드 최적화는 RDKit 기술자 + ChemGrid 휴리스틱 점수를 사용합니다.\n"
    "이 kcal/mol 형식 점수는 스크리닝 추정값이며 실제 AutoDock Vina 도킹 결과가 아닙니다.\n"
    "/ Engine basis: lead optimization uses RDKit descriptors plus ChemGrid "
    "heuristic scoring. These kcal/mol-style scores are screening estimates "
    "and AutoDock Vina has not been run unless a Vina log/pose artifact is attached."
)

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
except ImportError as e:
    logger.debug("Optional import unavailable: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# STYLE CONSTANTS
# ════════════════════════════════════════════════════════════════════════════

_DARK_BG = "#ffffff"          # white background (matches molecule images)
_DARK_SURFACE = "#f5f5f5"    # light gray surface for inputs/panels
_ACCENT = "#1565C0"          # blue accent for buttons/headers
_TEXT = "#333333"            # dark text for readability
_TEXT_DIM = "#666666"        # dimmed text
_TIER_A = "#2e7d32"         # green for tier A
_TIER_B = "#e65100"         # orange for tier B
_TIER_C = "#c62828"         # red for tier C
_KOREAN_UI_FONT = "Malgun Gothic"
_KOREAN_UI_FONT_PATHS = (
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
)
_KOREAN_UI_FONT_REGISTERED = False


def _ensure_korean_ui_font() -> str:
    """Register a Korean-capable Qt font for offscreen qtest captures."""
    global _KOREAN_UI_FONT_REGISTERED
    if not PYQT_OK or _KOREAN_UI_FONT_REGISTERED:
        return _KOREAN_UI_FONT
    _KOREAN_UI_FONT_REGISTERED = True
    for font_path in _KOREAN_UI_FONT_PATHS:
        if not os.path.isfile(font_path):
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    return families[0]
        except Exception as exc:
            logger.warning("Korean UI font registration failed for %s: %s", font_path, exc)
    return _KOREAN_UI_FONT

DARK_STYLESHEET = f"""
QDialog, QWidget {{
    background-color: {_DARK_BG};
    color: {_TEXT};
    font-family: '{_KOREAN_UI_FONT}';
}}
QGroupBox {{
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: {_TEXT};
    font-family: '{_KOREAN_UI_FONT}';
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QLabel {{
    color: {_TEXT};
    font-family: '{_KOREAN_UI_FONT}';
}}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QSlider {{
    background-color: {_DARK_SURFACE};
    color: {_TEXT};
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: '{_KOREAN_UI_FONT}';
}}
QComboBox QAbstractItemView {{
    background-color: {_DARK_SURFACE};
    color: {_TEXT};
    selection-background-color: #bbdefb;
}}
QTableWidget {{
    background-color: {_DARK_SURFACE};
    color: {_TEXT};
    gridline-color: #d0d0d0;
    border: 1px solid #cccccc;
    selection-background-color: #bbdefb;
}}
QTableWidget::item {{
    padding: 4px;
}}
QHeaderView::section {{
    background-color: {_ACCENT};
    color: #ffffff;
    padding: 6px;
    border: none;
    font-weight: bold;
}}
QProgressBar {{
    background-color: {_DARK_SURFACE};
    border: 1px solid #cccccc;
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
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    font-family: '{_KOREAN_UI_FONT}';
}}
QPushButton:hover {{
    background-color: #1976D2;
}}
QPushButton:disabled {{
    background-color: #e0e0e0;
    color: #999999;
}}
QCheckBox {{
    color: {_TEXT};
    spacing: 6px;
    font-family: '{_KOREAN_UI_FONT}';
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

def _smiles_to_pixmap(smiles: str, width: int = 260, height: int = 200,
                      dark_bg: bool = True) -> Optional["QPixmap"]:
    """Render SMILES to QPixmap via RDKit. Returns None on failure.

    Args:
        dark_bg: If True, use dark theme background (#1a1a2e) instead of white.
    """
    if not _RDKIT_DRAW_OK or not PYQT_OK:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        # Configure draw options for dark theme
        drawer = Draw.MolDraw2DCairo(width, height)
        opts = drawer.drawOptions()
        if dark_bg:
            # 밝은 배경으로 가독성 향상
            opts.setBackgroundColour((1.0, 1.0, 1.0, 1.0))
            opts.setAnnotationColour((0.0, 0.0, 0.0, 1.0))
        drawer.SetDrawOptions(opts)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        png_data = drawer.GetDrawingText()

        qimg = QImage()
        qimg.loadFromData(png_data)
        if qimg.isNull():
            # Fallback: PIL Image → QPixmap (no dark bg in this path)
            img = Draw.MolToImage(mol, size=(width, height))
            if img is None:
                return None
            data = img.convert("RGBA").tobytes("raw", "RGBA")
            qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
    except Exception as e:
        logger.debug("Dark-bg molecule image failed, trying simple: %s", e)
        # Final fallback: try simple MolToImage without dark bg
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            img = Draw.MolToImage(mol, size=(width, height))
            if img is None:
                return None
            data = img.convert("RGBA").tobytes("raw", "RGBA")
            qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            return QPixmap.fromImage(qimg)
        except Exception as e:
            logger.warning("Molecule image generation completely failed: %s", e)
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
    except Exception as e:
        logger.debug("Docking score estimation failed: %s", e)
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
            engine_disclosure = get_docking_engine_disclosure()
            result.engine_disclosure = engine_disclosure
            result.engine_basis = str(
                engine_disclosure.get("detail", LEAD_ENGINE_DISCLOSURE_TEXT)
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
                try:
                    v.engine_basis = result.engine_basis
                except Exception as e:
                    logger.warning("Failed to attach engine basis to variant: %s", e)

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
                    except Exception as e:
                        logger.warning("Operation failed: %s", e)

                # ADMET
                if ADMET_OK:
                    try:
                        admet_profile = predict_admet(v.smiles)
                        if admet_profile and admet_profile.lipinski:
                            v.admet_pass = admet_profile.lipinski.passes
                            v.admet_violations = admet_profile.lipinski.violations
                        if admet_profile and admet_profile.bbb:
                            v.bbb_score = admet_profile.bbb.score
                    except Exception as e:
                        logger.warning("ADMET prediction failed: %s", e)

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
    route_data = pyqtSignal(object)  # SynthesisRoute list for experiment summary
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
            # Emit raw route data for experiment summary
            self.route_data.emit(routes)
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


class AIAnalysisSummaryWorker(QThread):
    """Calls LLM to generate a pharmacological analysis summary."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, base_smiles: str, deriv_smiles: str, parent=None):
        super().__init__(parent)
        self.base_smiles = base_smiles
        self.deriv_smiles = deriv_smiles

    def run(self):
        try:
            prompt = (
                f"분자 {self.base_smiles}에서 유도체 {self.deriv_smiles}로의 "
                f"구조 변경을 분석하고, 예상되는 약리학적 개선 효과를 2-3문장으로 요약하세요."
            )
            text = call_llm(prompt)
            if text:
                self.finished.emit(text)
            else:
                self.finished.emit(
                    "AI 분석을 수행할 수 없습니다. (API 키가 설정되지 않았거나 LLM 호출 실패)")
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
        _ensure_qt_korean_font_ready()  # M1390: Korean font for offscreen captures
        self._canvas = canvas
        self._initial_smiles = smiles
        self._strategy: Optional[ModificationStrategy] = None
        self._result: Optional[LeadOptimizationResult] = None
        self._worker: Optional[PipelineWorker] = None
        self._retro_worker: Optional[RetrosynthesisWorker] = None
        self._ai_worker: Optional[AIAnalysisSummaryWorker] = None
        self._selected_variant: Optional[VariantResult] = None
        self._cached_routes = None  # retrosynthesis routes for experiment export
        # [M1288] QProgressDialog + timeout timer references
        self._progress_dlg: Optional["QProgressDialog"] = None  # type: ignore[assignment]
        self._timeout_timer: Optional["QTimer"] = None  # type: ignore[assignment]
        self._pipeline_start_ts: float = 0.0

        ui_font_family = _ensure_korean_ui_font()
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont(ui_font_family, 10))
        self.setWindowTitle("리드 최적화 파이프라인")
        self.resize(1400, 900)
        self.setFont(QFont(ui_font_family, 10))
        self.setStyleSheet(DARK_STYLESHEET)

        self._init_ui()
        self._populate_initial()

    # ================================================================ UI BUILD
    def _init_ui(self):
        root = QVBoxLayout(self)

        # Title
        title = QLabel("리드 최적화 파이프라인")
        title.setFont(QFont(_KOREAN_UI_FONT, 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: #1565C0; padding: 8px;")
        root.addWidget(title)

        # ── [M1288] Rule GG SIMULATION_MODE banner — 휴리스틱 점수 사용 시 표시 ──
        # #FFF176 background + #FFC107 border (Rule GG 노랑 배너)
        self._sim_banner = QLabel(
            # M1345: Rule Q bilingual prefix — Korean "[시뮬레이션 모드" mandatory per Rule GG.
            "[시뮬레이션 모드 / SIMULATION_MODE] 휴리스틱 점수 사용 중 / Heuristic scoring active. "
            "Install Vina + AlphaFold for real binding analysis."
        )
        self._sim_banner.setWordWrap(True)
        self._sim_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sim_banner.setStyleSheet(
            "background:#FFF176; color:#7B3F00; border:2px solid #FFC107; "
            "border-radius:4px; padding:6px 10px; font-weight:bold;"
        )
        self._sim_banner.setVisible(False)  # shown only when _simple_binding_score is active
        root.addWidget(self._sim_banner)

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
            f"background-color: {_DARK_SURFACE}; border: 1px solid #cccccc; border-radius: 6px;"
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
        receptor_options = get_receptor_dropdown_options()
        if receptor_options:
            for opt in receptor_options:
                pdb_id = str(opt.get("pdb_id", "") or "")
                label = str(opt.get("label", "") or pdb_id)
                if pdb_id:
                    self.combo_receptor.addItem(label, pdb_id)
        else:
            for pdb_id, meta in RECEPTOR_DATABASE.items():
                label = f"{meta.name} ({pdb_id})"
                if self.combo_receptor.findText(label) == -1:
                    self.combo_receptor.addItem(label, pdb_id)
        self.combo_receptor.currentIndexChanged.connect(self._on_receptor_changed)
        rec_layout.addWidget(self.combo_receptor)

        self.lbl_auto_receptor = QLabel("")
        self.lbl_auto_receptor.setStyleSheet("color: #2e7d32; font-size: 11px; padding: 2px 4px;")
        self.lbl_auto_receptor.setWordWrap(True)
        rec_layout.addWidget(self.lbl_auto_receptor)

        layout.addWidget(grp_receptor)

        # ── Bottom row ──
        bottom = QHBoxLayout()
        self.btn_ai_settings = QPushButton("⚙ AI 설정")
        self.btn_ai_settings.clicked.connect(self._on_open_ai_settings)
        bottom.addWidget(self.btn_ai_settings)

        bottom.addStretch()

        self.btn_next_0 = QPushButton("다음 >")
        self.btn_next_0.setStyleSheet("QPushButton { background-color: #1565C0; color: #ffffff; padding: 10px 30px; }")
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
        self.lbl_strategy_title.setFont(QFont(_KOREAN_UI_FONT, 14, QFont.Weight.Bold))
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
        self.btn_start_gen.setStyleSheet("QPushButton { background-color: #1565C0; color: #ffffff; padding: 10px 30px; }")
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
        lbl_title.setFont(QFont(_KOREAN_UI_FONT, 14, QFont.Weight.Bold))
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
        lbl_title.setFont(QFont(_KOREAN_UI_FONT, 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.lbl_docking_engine_basis = QLabel(LEAD_ENGINE_DISCLOSURE_TEXT)
        self.lbl_docking_engine_basis.setWordWrap(True)
        # M1345: Rule GG CT04 standard colors #FFF176 bg + #FFC107 border (was #fff3cd).
        self.lbl_docking_engine_basis.setStyleSheet(
            "background: #FFF176; color: #7B3F00; padding: 8px; "
            "border: 2px solid #FFC107; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(self.lbl_docking_engine_basis)

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
        self.btn_dock_stop.setStyleSheet("QPushButton { background-color: #c62828; color: #ffffff; }")
        self.btn_dock_stop.clicked.connect(self._on_early_stop)
        layout.addWidget(self.btn_dock_stop)

        self.stack.addWidget(page)

    # ─────────────────────── Page 4: ADMET ─────────────────────────────────
    def _build_page_admet(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl_title = QLabel("ADMET 스크리닝")
        lbl_title.setFont(QFont(_KOREAN_UI_FONT, 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.progress_admet = QProgressBar()
        layout.addWidget(self.progress_admet)

        self.lbl_admet_lipinski = QLabel("Lipinski 통과: -")
        self.lbl_admet_lipinski.setFont(QFont(_KOREAN_UI_FONT, 12))
        layout.addWidget(self.lbl_admet_lipinski)

        self.lbl_admet_bbb = QLabel("BBB 양성: -")
        self.lbl_admet_bbb.setFont(QFont(_KOREAN_UI_FONT, 12))
        layout.addWidget(self.lbl_admet_bbb)

        self.lbl_admet_qed = QLabel("평균 QED: -")
        self.lbl_admet_qed.setFont(QFont(_KOREAN_UI_FONT, 12))
        layout.addWidget(self.lbl_admet_qed)

        layout.addStretch()
        self.stack.addWidget(page)

    # ─────────────────────── Page 5: Results ───────────────────────────────
    def _build_page_results(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl_title = QLabel("결과")
        lbl_title.setFont(QFont(_KOREAN_UI_FONT, 14, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        # [M505] 방법론 명시 배너 — 경험적 가중합 휴리스틱 표기 (Rule O 학술품질, FP-15 P-MOCK-DISGUISED 재발방지)
        # Hopkins 2007 LE (Lead Efficiency Index, J. Med. Chem.) 기반 가중합 구조이나 ML 모델 미사용
        methodology_label = QLabel(
            "랭킹 방법: 경험적 가중합 (도킹 30% + QED 20% + ADMET 20% + SA 15% + 점수변화 15%)\n"
            "    ML 모델 미사용 — RDKit 기반 휴리스틱 추정값 (실험적 결합 친화도 아님)\n"
            f"    {LEAD_ENGINE_DISCLOSURE_TEXT}"
        )
        methodology_label.setWordWrap(True)
        # M1345: Rule GG CT04 standard colors #FFF176 bg + #FFC107 border (was #fff3cd).
        methodology_label.setStyleSheet(
            "background: #FFF176; color: #7B3F00; "
            "padding: 8px; border: 2px solid #FFC107; "
            "font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(methodology_label)

        self.lbl_result_summary = QLabel("")
        layout.addWidget(self.lbl_result_summary)

        self.tbl_results = QTableWidget()
        self.tbl_results.setColumnCount(9)
        # [M505] 헤더에 (휴리스틱) 표기 — 학생 학습 오염 방지 (Rule O, FP-08 P-SCOPE 재발방지)
        self.tbl_results.setHorizontalHeaderLabels([
            "순위", "구조", "SMILES", "변형", "결합에너지",
            "점수변화", "QED", "SA", "종합 (휴리스틱)",
        ])
        self.tbl_results.horizontalHeader().setToolTip(
            "경험적 가중합 점수 — ML 모델 미사용, RDKit 기반 추정값"
        )
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

        self.btn_drylab_results = QPushButton("\U0001F4C4 DryLab 보고서")
        self.btn_drylab_results.setStyleSheet(
            "QPushButton { background: #2c3e50; color: white; padding: 6px 14px; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background: #34495e; }"
        )
        self.btn_drylab_results.clicked.connect(self._on_export_drylab_report)
        bottom.addWidget(self.btn_drylab_results)

        self.btn_csv_export = QPushButton("CSV 내보내기")
        self.btn_csv_export.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; padding: 6px 14px; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background: #1976D2; }"
        )
        self.btn_csv_export.setToolTip("유도체 목록을 CSV 파일로 내보냅니다")
        self.btn_csv_export.clicked.connect(self._on_export_csv)
        bottom.addWidget(self.btn_csv_export)

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
        lbl_title.setFont(QFont(_KOREAN_UI_FONT, 14, QFont.Weight.Bold))
        scroll_layout.addWidget(lbl_title)

        # Structure image
        self.lbl_detail_structure = QLabel("구조")
        self.lbl_detail_structure.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_detail_structure.setFixedHeight(300)
        self.lbl_detail_structure.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; border: 1px solid #cccccc; border-radius: 6px;"
        )
        scroll_layout.addWidget(self.lbl_detail_structure)

        # Structural comparison: Base → Derivative
        grp_comparison = QGroupBox("기준 분자 → 유도체 변환 경로")
        comp_layout = QVBoxLayout(grp_comparison)

        # Side-by-side images: base molecule and derivative
        img_row = QHBoxLayout()
        self.lbl_base_mol_img = QLabel("기준 분자")
        self.lbl_base_mol_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_base_mol_img.setFixedSize(200, 160)
        self.lbl_base_mol_img.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #cccccc; border-radius: 4px;"
        )
        img_row.addWidget(self.lbl_base_mol_img)

        arrow_lbl = QLabel("  →  ")
        arrow_lbl.setFont(QFont(_KOREAN_UI_FONT, 24, QFont.Weight.Bold))
        arrow_lbl.setStyleSheet("color: #1565C0;")
        arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_row.addWidget(arrow_lbl)

        self.lbl_deriv_mol_img = QLabel("유도체")
        self.lbl_deriv_mol_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_deriv_mol_img.setFixedSize(200, 160)
        self.lbl_deriv_mol_img.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #cccccc; border-radius: 4px;"
        )
        img_row.addWidget(self.lbl_deriv_mol_img)
        img_row.addStretch()
        comp_layout.addLayout(img_row)

        # Text description of structural changes
        self.lbl_struct_diff = QLabel("-")
        self.lbl_struct_diff.setWordWrap(True)
        self.lbl_struct_diff.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; padding: 8px; border-radius: 4px; font-size: 12px;"
        )
        comp_layout.addWidget(self.lbl_struct_diff)

        scroll_layout.addWidget(grp_comparison)

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
        scores_form.addRow("휴리스틱 도킹 점수:", self.lbl_d_docking)
        self.lbl_d_engine_basis = QLabel(LEAD_ENGINE_DISCLOSURE_TEXT)
        self.lbl_d_engine_basis.setWordWrap(True)
        scores_form.addRow("Engine basis:", self.lbl_d_engine_basis)
        self.lbl_d_delta = QLabel("-")
        scores_form.addRow("점수 변화:", self.lbl_d_delta)
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

        # ── AI Summary (Groq/Gemini LLM) ────────────────────────────
        grp_ai_summary = QGroupBox("AI 약리학적 분석 요약")
        ai_summary_layout = QVBoxLayout(grp_ai_summary)
        self.lbl_ai_summary = QLabel("AI 분석 대기 중...")
        self.lbl_ai_summary.setWordWrap(True)
        self.lbl_ai_summary.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; padding: 10px; border-radius: 4px; "
            f"font-size: 12px; line-height: 1.4; color: #b0c4de;"
        )
        ai_summary_layout.addWidget(self.lbl_ai_summary)
        scroll_layout.addWidget(grp_ai_summary)

        # ── 종합 분석 (Comprehensive Analysis) ──────────────────────
        grp_comprehensive = QGroupBox("종합 분석")
        comp_analysis_layout = QVBoxLayout(grp_comprehensive)
        self.lbl_comprehensive = QLabel("-")
        self.lbl_comprehensive.setWordWrap(True)
        self.lbl_comprehensive.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_comprehensive.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; padding: 12px; border-radius: 4px; "
            f"font-size: 12px; line-height: 1.5;"
        )
        comp_analysis_layout.addWidget(self.lbl_comprehensive)

        # Experiment summary (populated after retrosynthesis)
        self.lbl_experiment_summary = QLabel("")
        self.lbl_experiment_summary.setWordWrap(True)
        self.lbl_experiment_summary.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_experiment_summary.setStyleSheet(
            f"background-color: {_DARK_SURFACE}; padding: 12px; border-radius: 4px; "
            f"font-size: 12px; line-height: 1.5;"
        )
        self.lbl_experiment_summary.setVisible(False)
        comp_analysis_layout.addWidget(self.lbl_experiment_summary)

        # Experiment report export button
        self.btn_experiment_report = QPushButton("상세 실험 보고서 PDF 내보내기")
        self.btn_experiment_report.setStyleSheet(
            "QPushButton { background: #1b5e20; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #2e7d32; }"
        )
        self.btn_experiment_report.setToolTip(
            "역합성 경로 기반 실험 보고서를 PDF로 내보냅니다")
        self.btn_experiment_report.clicked.connect(self._on_export_experiment_report)
        self.btn_experiment_report.setEnabled(False)
        comp_analysis_layout.addWidget(self.btn_experiment_report)

        scroll_layout.addWidget(grp_comprehensive)

        # Web 3D protein structure viewer button
        self.btn_web_protein_3d = QPushButton("\U0001F310 단백질 3D 구조 보기 (웹)")
        self.btn_web_protein_3d.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #1976D2; }"
        )
        self.btn_web_protein_3d.setToolTip("선택된 수용체의 3D 구조를 RCSB PDB 웹사이트에서 봅니다")
        self.btn_web_protein_3d.clicked.connect(self._on_open_web_protein_3d)
        scroll_layout.addWidget(self.btn_web_protein_3d)

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

        # [M1034 格忿#31] 유도체 → 도킹 팝업 직접 연결 버튼
        # 사용자: "그린 분자 + 수용체 도킹 시뮬레이션 링크"
        # Rule M: 선택된 유도체 SMILES 없을 시 logger.warning + 사용자 안내 (silent failure 금지)
        # Rule S: QPushButton.clicked — Qt6 공식 시그널
        self.btn_dock_receptor = QPushButton("도킹 시뮬레이션 실행")
        self.btn_dock_receptor.setStyleSheet(
            "QPushButton { background: #1b5e20; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #2e7d32; }"
        )
        self.btn_dock_receptor.setToolTip(
            "선택된 유도체 분자를 도킹 시뮬레이션 팝업으로 전달합니다.\n"
            "수용체를 선택하고 도킹 실행 버튼을 누르세요.\n"
            "(M1034 格忿#31 — 그린 분자 → 수용체 도킹 연결)"
        )
        self.btn_dock_receptor.clicked.connect(self._on_dock_with_receptor)
        btn_row.addWidget(self.btn_dock_receptor)

        self.btn_lead_report = QPushButton("Lead optimizer report PDF")
        self.btn_lead_report.setStyleSheet(
            "QPushButton { background: #0d47a1; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #1565C0; }"
        )
        self.btn_lead_report.setToolTip(
            "Export a lead-optimization report with heuristic-score disclosure and claim sidecar."
        )
        self.btn_lead_report.clicked.connect(self._on_export_lead_report)
        btn_row.addWidget(self.btn_lead_report)

        self.btn_drylab_report = QPushButton("\U0001F4C4 DryLab 보고서 내보내기")
        self.btn_drylab_report.setStyleSheet(
            "QPushButton { background: #2c3e50; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #34495e; }"
        )
        self.btn_drylab_report.setToolTip("전체 파이프라인 결과를 학술 보고서 PDF로 내보냅니다")
        self.btn_drylab_report.clicked.connect(self._on_export_drylab_report)
        btn_row.addWidget(self.btn_drylab_report)

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

    def _selected_receptor_id(self) -> str:
        idx = self.combo_receptor.currentIndex()
        if idx > 0:
            combo_receptor = str(self.combo_receptor.itemData(idx) or "").strip().upper()
            if combo_receptor:
                return combo_receptor
        pipeline_receptor = str(getattr(self, "_receptor_pdb", "") or "").strip().upper()
        if pipeline_receptor:
            return pipeline_receptor
        strategy = getattr(self, "_strategy", None)
        return str(getattr(strategy, "target_protein", "") or "").strip().upper()

    def _selected_receptor_context(self) -> Dict:
        receptor_pdb = self._selected_receptor_id()
        if not receptor_pdb:
            return {}
        meta = get_receptor_metadata(receptor_pdb)
        alphafold_uniprot_id = str(getattr(meta, "uniprot_id", "") or "") if meta else ""
        payload = {"uniprot_id": alphafold_uniprot_id} if alphafold_uniprot_id else None
        context = build_selected_receptor_external_context(receptor_pdb, payload)
        receptor_ctx = context.get("receptor", {}) if isinstance(context, dict) else {}
        if not isinstance(receptor_ctx, dict):
            receptor_ctx = {}
        external_links = receptor_ctx.get("external_links", {})
        if not isinstance(external_links, dict):
            external_links = {}
        return {
            "pdb_id": receptor_pdb,
            "name": getattr(meta, "name", receptor_pdb) if meta else receptor_pdb,
            "gene": getattr(meta, "gene", "") if meta else "",
            "organism": getattr(meta, "organism", "") if meta else "",
            "uniprot_id": alphafold_uniprot_id,
            "function": getattr(meta, "function", "") if meta else "",
            "disease_relevance": getattr(meta, "disease_relevance", "") if meta else "",
            "binding_site_residues": getattr(meta, "binding_site_residues", []) if meta else [],
            "pocket_character": getattr(meta, "pocket_character", "") if meta else "",
            "external_links": external_links,
            "alphafold_match": context.get("alphafold_match", {}) if isinstance(context, dict) else {},
            "engine_disclosure": context.get("engine_disclosure", {}) if isinstance(context, dict) else {},
        }

    def _sync_receptor_combo_to_pipeline_selection(self, receptor_pdb: str) -> bool:
        """Reflect an auto-selected receptor in the combo before downstream export."""
        receptor_pdb = str(receptor_pdb or "").strip().upper()
        if not receptor_pdb:
            return False
        for i in range(self.combo_receptor.count()):
            if str(self.combo_receptor.itemData(i) or "").strip().upper() == receptor_pdb:
                if self.combo_receptor.currentIndex() != i:
                    self.combo_receptor.setCurrentIndex(i)
                return True
        logger.warning("Lead optimizer selected receptor %s is not in combo options", receptor_pdb)
        return False

    def _on_receptor_changed(self, _index: int = 0):
        receptor_info = self._selected_receptor_context()
        if not receptor_info:
            self.lbl_auto_receptor.setText("")
            return
        links = receptor_info.get("external_links", {})
        link_names = ", ".join(sorted(links.keys())) if isinstance(links, dict) else ""
        uid = receptor_info.get("uniprot_id", "") or "no UniProt mapping"
        self.lbl_auto_receptor.setText(
            f"Selected receptor: {receptor_info.get('name', '')} "
            f"({receptor_info.get('pdb_id', '')}); UniProt {uid}. "
            f"External page routes require separate browser/CDP evidence: {link_names}."
        )

    def _on_goal_changed(self, text: str):
        self.edit_custom_goal.setVisible(text == "사용자 정의...")

        # ── Goal → Receptor 자동 매핑 ──
        receptors = GOAL_RECEPTOR_MAP.get(text, [])
        if receptors:
            pdb_id = receptors[0]
            for i in range(self.combo_receptor.count()):
                if self.combo_receptor.itemData(i) == pdb_id:
                    self.combo_receptor.setCurrentIndex(i)
                    # 수용체 이름 추출
                    meta = RECEPTOR_DATABASE.get(pdb_id)
                    receptor_name = meta.name if meta else pdb_id
                    self.lbl_auto_receptor.setText(
                        f"이 목표에 적합한 수용체가 자동 선택되었습니다: {receptor_name} ({pdb_id})"
                    )
                    break
            else:
                # PDB ID가 combo에 없는 경우 (alt ID 등)
                self.lbl_auto_receptor.setText("")
        else:
            self.lbl_auto_receptor.setText("")

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
        receptor_pdb = self._selected_receptor_id()

        # Translate goal → strategy
        self._strategy = translate_goal(goal_text, smiles)
        if self._strategy is None:
            QMessageBox.warning(self, "경고", "전략을 생성할 수 없습니다.")
            return

        if not receptor_pdb and self._strategy.target_protein:
            receptor_pdb = self._strategy.target_protein

        self._goal_text = goal_text
        self._receptor_pdb = receptor_pdb
        self._sync_receptor_combo_to_pipeline_selection(receptor_pdb)

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

        # [M1288] Rule GG: show SIMULATION_MODE banner (heuristic scoring is always active)
        if hasattr(self, "_sim_banner"):
            self._sim_banner.setVisible(True)
        logger.warning(
            "Lead optimizer: using _simple_binding_score heuristic (not real Vina). "
            "Rule GG SIMULATION_MODE banner shown."
        )

        # [M1288] QProgressDialog — indeterminate mode (max=0), cancelable (Rule S: canceled signal)
        if PYQT_OK:
            import time as _time
            self._pipeline_start_ts = _time.time()
            self._progress_dlg = QProgressDialog(
                "리드 최적화 분석 중 / Lead optimization analysis running...",
                "취소 / Cancel",
                0,
                0,  # max=0 → indeterminate (marquee) mode
                self,
            )
            self._progress_dlg.setWindowTitle("분석 중 / Analysing")
            self._progress_dlg.setMinimumDuration(0)   # show immediately
            self._progress_dlg.setAutoClose(False)
            self._progress_dlg.setAutoReset(False)
            # Rule S: canceled is the correct PyQt6 signal (verified above)
            self._progress_dlg.canceled.connect(self._on_pipeline_cancel_requested)
            self._progress_dlg.show()

            # [M1288] 120s timeout handler (Rule M: no silent failure on long runs)
            _PIPELINE_TIMEOUT_MS = 120_000  # 120 seconds (magic number: pipeline SLA)
            self._timeout_timer = QTimer(self)
            self._timeout_timer.setSingleShot(True)
            self._timeout_timer.timeout.connect(self._on_pipeline_timeout)
            self._timeout_timer.start(_PIPELINE_TIMEOUT_MS)

    def _on_pipeline_cancel_requested(self):
        """User clicked Cancel in QProgressDialog — stop worker gracefully."""
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            logger.warning("Lead optimizer pipeline cancelled by user.")
        self._close_progress_dlg()

    def _on_pipeline_timeout(self):
        """[M1288] 120s timeout: warn user and show partial results without crashing."""
        import time as _time
        elapsed = _time.time() - self._pipeline_start_ts
        logger.warning(
            "Lead optimizer pipeline timeout after %.1fs (threshold=120s). "
            "Requesting worker stop for partial results.", elapsed
        )
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
        self._close_progress_dlg()
        # Rule M: user feedback — statusBar or fallback QMessageBox warning toast
        msg = (
            f"파이프라인이 120초를 초과했습니다. 부분 결과를 표시합니다.\n"
            f"Pipeline exceeded 120s. Showing partial results. "
            f"(Elapsed: {elapsed:.0f}s)"
        )
        try:
            parent_mw = self.parent()
            if parent_mw is not None and hasattr(parent_mw, "statusBar"):
                parent_mw.statusBar().showMessage(msg, 5000)  # 5s display
                return
        except Exception as _e:
            logger.debug("statusBar toast failed: %s", _e)
        # Fallback: non-blocking informational dialog
        QMessageBox.information(self, "시간 초과 / Timeout", msg)

    def _close_progress_dlg(self):
        """Close QProgressDialog and stop timeout timer safely."""
        if self._timeout_timer is not None:
            try:
                self._timeout_timer.stop()
            except Exception as _e:
                logger.debug("Timeout timer stop failed: %s", _e)
            self._timeout_timer = None
        if self._progress_dlg is not None:
            try:
                self._progress_dlg.close()
                self._progress_dlg.deleteLater()
            except Exception as _e:
                logger.debug("Progress dialog close failed: %s", _e)
            self._progress_dlg = None

    # ================================================================ PIPELINE CALLBACKS
    def _on_stage_changed(self, stage: str):
        stage_map = {
            "generating": (2, "유도체 생성 중..."),
            "docking": (3, "도킹 스코어링 중..."),
            "admet": (4, "ADMET 스크리닝 중..."),
            "ranking": (4, "종합 랭킹 계산 중..."),
        }
        # Rule N: isinstance guard for stage_map
        if not isinstance(stage_map, dict): stage_map = {}
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
        self._close_progress_dlg()  # [M1288] close QProgressDialog on success
        self._result = result
        engine_basis = getattr(result, "engine_basis", LEAD_ENGINE_DISCLOSURE_TEXT)
        if hasattr(self, "lbl_docking_engine_basis"):
            self.lbl_docking_engine_basis.setText(engine_basis)
        try:
            self.txt_dock_log.append(f"[engine] {engine_basis}")
        except Exception as exc:
            logger.debug("Lead engine disclosure log append failed: %s", exc)
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
        self._close_progress_dlg()  # [M1288] close QProgressDialog on error
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
            # Rule N: isinstance guard for tier_colors
            if not isinstance(tier_colors, dict): tier_colors = {}
            tier_item.setForeground(QBrush(QColor(tier_colors.get(v.tier, _TEXT_DIM))))
            tier_item.setFont(QFont(_KOREAN_UI_FONT, 11, QFont.Weight.Bold))
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
        # Structure (white background — matches popup theme)
        pm = _smiles_to_pixmap(v.smiles, 400, 280, dark_bg=False)
        if pm:
            self.lbl_detail_structure.setPixmap(pm)
        else:
            self.lbl_detail_structure.setText(v.smiles)

        # Base → Derivative structural comparison
        self._populate_struct_comparison(v)

        self.lbl_d_smiles.setText(v.smiles)
        self.lbl_d_mod_type.setText(v.modification_type)
        self.lbl_d_mod_detail.setText(v.modification_detail)
        self.lbl_d_docking.setText(f"{v.docking_score:.2f} kcal/mol-style")
        self.lbl_d_delta.setText(f"{v.docking_delta:+.2f} kcal/mol-style")
        engine_basis = getattr(v, "engine_basis", "")
        if not engine_basis and self._result is not None:
            engine_basis = getattr(self._result, "engine_basis", "")
        if hasattr(self, "lbl_d_engine_basis"):
            self.lbl_d_engine_basis.setText(engine_basis or LEAD_ENGINE_DISCLOSURE_TEXT)

        delta_color = _TIER_A if v.docking_delta < 0 else _TIER_C
        self.lbl_d_delta.setStyleSheet(f"color: {delta_color};")

        self.lbl_d_qed.setText(f"{v.qed_score:.3f}")
        self.lbl_d_sa.setText(f"{v.sa_score:.1f} (1=쉬움, 10=어려움)")
        self.lbl_d_composite.setText(f"{v.composite_rank:.3f}")

        tier_colors = {"A": _TIER_A, "B": _TIER_B, "C": _TIER_C}
        self.lbl_d_tier.setText(v.tier)
        # Rule N: isinstance guard for tier_colors
        if not isinstance(tier_colors, dict): tier_colors = {}
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

        # Populate comprehensive analysis
        self._populate_comprehensive_analysis(v)

        # Start AI summary in background
        self._start_ai_analysis(v)

        # Reset experiment summary and retro output
        self.lbl_experiment_summary.setVisible(False)
        self.lbl_experiment_summary.setText("")
        self.btn_experiment_report.setEnabled(False)
        self._cached_routes = None
        self.txt_retro.setVisible(False)
        self.txt_retro.clear()

    def _populate_struct_comparison(self, v):
        """Populate the Base → Derivative structural comparison section."""
        base_smi = self._initial_smiles
        deriv_smi = v.smiles

        # Base molecule image
        if base_smi:
            base_pm = _smiles_to_pixmap(base_smi, 180, 140, dark_bg=False)
            if base_pm:
                self.lbl_base_mol_img.setPixmap(
                    base_pm.scaled(180, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
            else:
                self.lbl_base_mol_img.setText(f"기준: {base_smi[:30]}...")
        else:
            self.lbl_base_mol_img.setText("기준 분자 없음")

        # Derivative molecule image
        deriv_pm = _smiles_to_pixmap(deriv_smi, 180, 140, dark_bg=False)
        if deriv_pm:
            self.lbl_deriv_mol_img.setPixmap(
                deriv_pm.scaled(180, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_deriv_mol_img.setText(f"유도체: {deriv_smi[:30]}...")

        # Structural difference analysis
        diff_lines = []
        diff_lines.append(f"변형 유형: {v.modification_type}")
        diff_lines.append(f"변형 상세: {v.modification_detail}")

        # Try RDKit-based structural comparison
        if _RDKIT_DRAW_OK and base_smi:
            try:
                base_mol = Chem.MolFromSmiles(base_smi)
                deriv_mol = Chem.MolFromSmiles(deriv_smi)
                if base_mol is None:
                    logger.warning("Invalid base SMILES for structural comparison: %s", base_smi)
                if deriv_mol is None:
                    logger.warning("Invalid derivative SMILES for structural comparison: %s", deriv_smi)
                if base_mol and deriv_mol:
                    # Atom/bond count difference
                    base_atoms = base_mol.GetNumHeavyAtoms()
                    deriv_atoms = deriv_mol.GetNumHeavyAtoms()
                    atom_diff = deriv_atoms - base_atoms
                    base_bonds = base_mol.GetNumBonds()
                    deriv_bonds = deriv_mol.GetNumBonds()
                    bond_diff = deriv_bonds - base_bonds

                    diff_lines.append(f"원자 수 변화: {base_atoms} → {deriv_atoms} ({atom_diff:+d})")
                    diff_lines.append(f"결합 수 변화: {base_bonds} → {deriv_bonds} ({bond_diff:+d})")

                    # MW change
                    base_mw = Descriptors.ExactMolWt(base_mol)
                    deriv_mw = Descriptors.ExactMolWt(deriv_mol)
                    diff_lines.append(f"분자량 변화: {base_mw:.1f} → {deriv_mw:.1f} ({deriv_mw - base_mw:+.1f} Da)")

                    # LogP change
                    base_logp = Crippen.MolLogP(base_mol)
                    deriv_logp = Crippen.MolLogP(deriv_mol)
                    diff_lines.append(f"LogP 변화: {base_logp:.2f} → {deriv_logp:.2f} ({deriv_logp - base_logp:+.2f})")
            except Exception as exc:
                diff_lines.append(f"(구조 비교 중 오류: {exc})")

        self.lbl_struct_diff.setText("\n".join(diff_lines))

    # ──────────────────────────────────────────────────────────────────────
    # Comprehensive Analysis
    # ──────────────────────────────────────────────────────────────────────

    def _populate_comprehensive_analysis(self, v):
        """Build rich HTML content for the comprehensive analysis section."""
        base_smi = self._initial_smiles or ""
        deriv_smi = v.smiles
        html_parts = []

        # ── 1. 예상 개선 효과 (Expected Improvement) ──
        html_parts.append(
            f'<p style="color:#4fc3f7; font-weight:bold; font-size:13px; '
            f'margin-bottom:4px;">1. 예상 개선 효과</p>'
        )
        # Heuristic docking score change %
        base_dock = 0.0
        if self._result and self._result.base_docking_score != 0:
            base_dock = self._result.base_docking_score
        if base_dock != 0:
            delta_pct = abs(v.docking_delta / base_dock) * 100
            improve_dir = "감소" if v.docking_delta < 0 else "증가"
            html_parts.append(
                f'<p>기준 분자 대비 휴리스틱 도킹 점수 <b>{delta_pct:.1f}%</b> {improve_dir}</p>'
                '<p style="font-size:11px;color:#9fb3c8;">탐색용 점수 변화이며 실제 결합 세기 해석에 사용할 수 없습니다.</p>'
            )
        else:
            html_parts.append(
                f'<p>기준 분자 대비 휴리스틱 점수 변화: <b>{v.docking_delta:+.2f}</b> kcal/mol-style</p>'
                '<p style="font-size:11px;color:#9fb3c8;">탐색용 점수 변화이며 실제 Vina 결과가 아닙니다.</p>'
            )

        # QED tier
        qed = v.qed_score
        if qed >= 0.7:
            qed_tier = "A"
            qed_color = _TIER_A
        elif qed >= 0.4:
            qed_tier = "B"
            qed_color = _TIER_B
        else:
            qed_tier = "C"
            qed_color = _TIER_C
        html_parts.append(
            f'<p>QED 약물성 지수: <b>{qed:.3f}</b> '
            f'(<span style="color:{qed_color};">{qed_tier}등급</span>)</p>'
        )

        # ADMET prediction
        lipinski_str = '<span style="color:#4caf50;">PASS</span>' if v.admet_pass \
            else '<span style="color:#f44336;">FAIL</span>'
        bbb_str = "Yes" if v.bbb_score > 0.5 else "No"
        bbb_color = _TIER_A if v.bbb_score > 0.5 else _TIER_C
        html_parts.append(
            f'<p>ADMET 예측: Lipinski {lipinski_str}, '
            f'BBB <span style="color:{bbb_color};">{bbb_str}</span></p>'
        )

        # ── 2. 구조적 변화 분석 (Structural Changes) ──
        html_parts.append(
            f'<p style="color:#4fc3f7; font-weight:bold; font-size:13px; '
            f'margin-top:10px; margin-bottom:4px;">2. 구조적 변화 분석</p>'
        )
        # Modification type translation
        mod_type_kr = {
            "r_group": "R-그룹 치환",
            "bioisostere": "생물학적 등가체 교환",
            "chain": "사슬 연장/단축",
            "ring": "고리 변형",
            "stereo": "입체 이성질체 변경",
        }
        # Rule N: isinstance guard for mod_type_kr
        if not isinstance(mod_type_kr, dict):
            mod_type_kr = {}
        html_parts.append(
            f'<p>변형 유형: <b>{mod_type_kr.get(v.modification_type, v.modification_type)}</b></p>'
        )

        # Functional group detection via RDKit
        func_groups_added = []
        delta_mw_str = "-"
        delta_logp_str = "-"
        if _RDKIT_DRAW_OK and base_smi:
            try:
                base_mol = Chem.MolFromSmiles(base_smi)
                deriv_mol = Chem.MolFromSmiles(deriv_smi)
                if base_mol is None:
                    logger.warning("Invalid base SMILES for functional group detection: %s", base_smi)
                if deriv_mol is None:
                    logger.warning("Invalid derivative SMILES for functional group detection: %s", deriv_smi)
                if base_mol and deriv_mol:
                    # Detect functional groups
                    fg_patterns = {
                        "하이드록실(-OH)": "[OX2H]",
                        "아미노(-NH2)": "[NX3;H2]",
                        "카르복실(-COOH)": "[CX3](=O)[OX2H1]",
                        "할로겐(-F/-Cl/-Br)": "[F,Cl,Br,I]",
                        "나이트로(-NO2)": "[NX3](=O)=O",
                        "시아노(-CN)": "[CX2]#[NX1]",
                        "술폰아마이드(-SO2NH)": "[SX4](=O)(=O)[NX3]",
                        "에스테르(-COO-)": "[CX3](=O)[OX2][#6]",
                        "아마이드(-CONH-)": "[CX3](=O)[NX3]",
                        "트리플루오로메틸(-CF3)": "[CX4](F)(F)F",
                        "메톡시(-OCH3)": "[OX2][CH3]",
                    }
                    for fg_name, smarts in fg_patterns.items():
                        pat = Chem.MolFromSmarts(smarts)
                        if pat is None:
                            continue
                        base_count = len(base_mol.GetSubstructMatches(pat))
                        deriv_count = len(deriv_mol.GetSubstructMatches(pat))
                        if deriv_count > base_count:
                            func_groups_added.append(fg_name)

                    # MW change
                    base_mw = Descriptors.ExactMolWt(base_mol)
                    deriv_mw = Descriptors.ExactMolWt(deriv_mol)
                    d_mw = deriv_mw - base_mw
                    delta_mw_str = f"{d_mw:+.1f} g/mol"

                    # LogP change
                    base_logp = Crippen.MolLogP(base_mol)
                    deriv_logp = Crippen.MolLogP(deriv_mol)
                    d_logp = deriv_logp - base_logp
                    polarity = "소수성 증가" if d_logp > 0 else "친수성 증가" if d_logp < 0 else "변화 없음"
                    delta_logp_str = f"{d_logp:+.2f} ({polarity})"
            except Exception as e:
                logger.warning("Operation failed: %s", e)

        if func_groups_added:
            html_parts.append(
                f'<p>추가된 작용기: <b>{", ".join(func_groups_added)}</b></p>'
            )
        else:
            html_parts.append('<p>추가된 작용기: (감지 없음 또는 RDKit 미사용)</p>')
        html_parts.append(f'<p>분자량 변화: <b>{delta_mw_str}</b></p>')
        html_parts.append(f'<p>LogP 변화: <b>{delta_logp_str}</b></p>')

        # ── 3. 합성 난이도 (Synthesis Difficulty) ──
        html_parts.append(
            f'<p style="color:#4fc3f7; font-weight:bold; font-size:13px; '
            f'margin-top:10px; margin-bottom:4px;">3. 합성 난이도</p>'
        )
        sa = v.sa_score
        if sa < 3:
            sa_label = "쉬움"
            sa_color = _TIER_A
        elif sa <= 5:
            sa_label = "보통"
            sa_color = _TIER_B
        else:
            sa_label = "어려움"
            sa_color = _TIER_C

        html_parts.append(
            f'<p>합성 접근성 점수: <b>{sa:.1f}</b>/10 '
            f'(<span style="color:{sa_color}; font-weight:bold;">{sa_label}</span>)</p>'
        )
        # Estimated synthesis steps (heuristic from SA score)
        est_steps = max(1, min(10, round(sa * 1.2)))
        html_parts.append(f'<p>예상 합성 단계: <b>{est_steps}단계</b></p>')

        # Commercially available reagents heuristic
        commercially_available = sa < 4.0
        avail_str = ("Yes" if commercially_available else "No")
        avail_color = _TIER_A if commercially_available else _TIER_C
        html_parts.append(
            f'<p>시중 구매 가능 시약 기반: '
            f'<span style="color:{avail_color};"><b>{avail_str}</b></span></p>'
        )

        # ── 4. 실험 방법 요약 (M1282: placeholder→SIMULATION_MODE banner, Rule GG) ──
        # Rule GG: fallback/미연결 상태를 노랑 배너로 명시 — 학생 학습 오염 차단.
        # retrosynthesis_engine.run_retrosynthesis() 연결 시 RetrosynthesisWorker가
        # _on_route_data_received()를 통해 이 섹션을 실제 경로 데이터로 대체함.
        # 외부 엔진 미연결 시 [SIMULATION_MODE] 배너 표시 (Rule M: silent failure 금지).
        html_parts.append(
            f'<p style="color:#4fc3f7; font-weight:bold; font-size:13px; '
            f'margin-top:10px; margin-bottom:4px;">4. 실험 방법 요약</p>'
        )
        html_parts.append(
            # M1345: Rule Q "[시뮬레이션 모드" Korean prefix + bilingual body.
            '<p style="background:#FFF176; color:#333; padding:4px 8px; '
            'border-left:4px solid #F9A825; margin:4px 0;">'
            '[시뮬레이션 모드 / SIMULATION_MODE] 합성 경로 분석 엔진 미연결 / '
            'Synthesis route engine not connected — '
            '"합성 경로 분석" 버튼 실행 후 자동 생성됩니다. '
            '(Rule GG: 학생 학습 오염 차단 — 외부 엔진 연결 필요)'
            '</p>'
        )

        self.lbl_comprehensive.setText("".join(html_parts))

    def _start_ai_analysis(self, v):
        """Launch background AI analysis summary."""
        base_smi = self._initial_smiles or ""
        if not base_smi:
            self.lbl_ai_summary.setText("기준 분자 SMILES가 없어 AI 분석을 수행할 수 없습니다.")
            return
        # M1282: Rule GG yellow banner when GEMINI_API_KEY and GROQ_API_KEY absent.
        # Rule M: silent failure 금지 — API 키 부재 시 명시적 SIMULATION_MODE 표시.
        _has_gemini = bool(GEMINI_OK and get_api_key("GEMINI_API_KEY"))
        _has_groq = bool(GROQ_OK and get_api_key("GROQ_API_KEY"))
        if not _has_gemini and not _has_groq:
            logger.warning(
                "[popup_lead_optimizer] GEMINI_API_KEY and GROQ_API_KEY absent — "
                "AI 분석 SIMULATION_MODE (Rule GG). .env에 키 등록 필요."
            )
            self.lbl_ai_summary.setText(
                # M1345: Rule Q bilingual prefix — "[시뮬레이션 모드" Korean mandatory.
                "[시뮬레이션 모드 / SIMULATION_MODE] AI 분석 키 미설정 / AI analysis key not set — "
                "GEMINI_API_KEY 또는 GROQ_API_KEY를 .env 파일에 등록하면 실제 LLM 분석이 활성화됩니다. "
                "(Rule GG: 학생 학습 오염 차단)"
            )
            return
        self.lbl_ai_summary.setText("AI 분석 중...")
        self._ai_worker = AIAnalysisSummaryWorker(base_smi, v.smiles, self)
        self._ai_worker.finished.connect(self._on_ai_summary_done)
        self._ai_worker.error.connect(self._on_ai_summary_error)
        self._ai_worker.start()

    def _on_ai_summary_done(self, text: str):
        self.lbl_ai_summary.setText(text)

    def _on_ai_summary_error(self, msg: str):
        self.lbl_ai_summary.setText(f"AI 분석 오류: {msg}")

    def _on_route_data_received(self, routes):
        """Handle retrosynthesis route data for experiment summary."""
        self._cached_routes = routes
        if not routes:
            return
        # Build experiment summary HTML from best route
        route = routes[0]
        html_parts = [
            '<p style="color:#4fc3f7; font-weight:bold; font-size:13px; '
            'margin-bottom:4px;">실험 방법 요약</p>'
        ]
        for step in route.steps:
            reactant_names = ", ".join(
                step.reactant_smiles if hasattr(step, 'reactant_smiles') else
                (step.reactants if hasattr(step, 'reactants') else [])
            )
            product = (step.product_smiles if hasattr(step, 'product_smiles')
                       else getattr(step, 'product', '?'))
            conditions = getattr(step, 'conditions', '')
            transform = (step.transform_name if hasattr(step, 'transform_name')
                         else getattr(step, 'reaction_name', ''))
            cond_str = f" (조건: {conditions})" if conditions else ""
            html_parts.append(
                f'<p>Step {step.step_number}: {reactant_names} &rarr; {product}{cond_str}'
                f'<br/><i style="color:#999;">[{transform}]</i></p>'
            )
        self.lbl_experiment_summary.setText("".join(html_parts))
        self.lbl_experiment_summary.setVisible(True)
        self.btn_experiment_report.setEnabled(True)

        # Also update comprehensive analysis section 4
        # M1282: match updated SIMULATION_MODE banner text (Rule GG, not old placeholder).
        current_html = self.lbl_comprehensive.text()
        # M1345: marker updated to match bilingual prefix (Rule Q).
        _simmode_marker = "합성 경로 분석 엔진 미연결"
        if _simmode_marker in current_html:
            summary_html = "".join(html_parts[1:])  # skip the title
            # Replace the entire SIMULATION_MODE banner paragraph with real route data
            import re as _re
            current_html = _re.sub(
                r'<p[^>]*>\[시뮬레이션 모드 / SIMULATION_MODE\][^<]*합성 경로 분석 엔진 미연결[^<]*</p>',
                summary_html,
                current_html,
            )
            self.lbl_comprehensive.setText(current_html)

    def _on_export_experiment_report(self):
        """Export experiment report PDF using cached retrosynthesis routes."""
        if not self._cached_routes:
            QMessageBox.information(self, "알림",
                                   "먼저 '합성 경로 분석'을 실행하세요.")
            return
        try:
            from experiment_report_exporter import ExperimentReportExporter
            route = self._cached_routes[0]
            variant_smi = self._selected_variant.smiles if self._selected_variant else ""
            variant_name = (self._selected_variant.modification_detail
                            if self._selected_variant else variant_smi)

            # Get AI summary text if available
            ai_text = self.lbl_ai_summary.text()
            if "AI 분석 중" in ai_text or "AI 분석 대기" in ai_text:
                ai_text = ""

            exporter = ExperimentReportExporter(
                route=route,
                target_name=variant_name,
                target_smiles=variant_smi,
                ai_analysis_text=ai_text,
            )

            # Use QFileDialog for save path
            from PyQt6.QtWidgets import QFileDialog
            safe_name = variant_smi[:20].replace("/", "_").replace("\\", "_")
            default_name = f"experiment_report_{safe_name}.pdf"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "실험 보고서 저장", default_name,
                "PDF 파일 (*.pdf);;모든 파일 (*)"
            )
            if not file_path:
                return

            success, msg = exporter.export(file_path)
            if success:
                QMessageBox.information(
                    self, "완료",
                    f"실험 보고서가 저장되었습니다:\n{file_path}"
                )
            else:
                QMessageBox.warning(self, "오류", f"보고서 생성 실패: {msg}")
        except ImportError:
            QMessageBox.warning(
                self, "오류",
                "experiment_report_exporter 모듈을 불러올 수 없습니다."
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "오류",
                f"실험 보고서 내보내기 실패:\n{exc}"
            )

    def _on_open_web_protein_3d(self):
        """Open RCSB or AlphaFold web 3D viewer for the selected receptor."""
        receptor_info = self._selected_receptor_context()
        receptor_pdb = str(receptor_info.get("pdb_id", "") or "")
        if not receptor_pdb:
            QMessageBox.information(self, "알림", "표적 수용체를 먼저 선택하세요.")
            return

        links = receptor_info.get("external_links", {})
        if not isinstance(links, dict):
            links = {}
        url = (
            links.get("pdbe_entry")
            or links.get("rcsb_3d_view")
            or f"https://www.rcsb.org/3d-view/{receptor_pdb}"
        )
        logger.info(
            "Opening selected receptor external route: pdb=%s url=%s all_links=%s",
            receptor_pdb, url, links,
        )

        QDesktopServices.openUrl(QUrl(url))

    def _on_retrosynthesis(self):
        if self._selected_variant is None:
            return
        variant_smiles = self._selected_variant.smiles
        variant_name = self._selected_variant.modification_type or variant_smiles

        # Try opening the full SynthesisPopup dialog first
        try:
            from popup_synthesis import SynthesisPopup
            dlg = SynthesisPopup(
                target_smiles=variant_smiles,
                target_name=variant_name,
                parent=self,
            )
            dlg.exec()
            return
        except ImportError:
            logger.warning("popup_synthesis not available, falling back to inline retrosynthesis")
        except Exception as exc:
            logger.warning("SynthesisPopup failed: %s — falling back to inline", exc)

        # Fallback: inline retrosynthesis via worker thread
        self.txt_retro.setVisible(True)
        self.txt_retro.setText("합성 경로 분석 중...")
        self.btn_retro.setEnabled(False)

        self._retro_worker = RetrosynthesisWorker(variant_smiles, self)
        self._retro_worker.finished.connect(self._on_retro_done)
        self._retro_worker.route_data.connect(self._on_route_data_received)
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
                except Exception as e:
                    logger.warning("Operation failed: %s", e)
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
            except Exception as e:
                logger.warning("UI update failed: %s", e)

    def _on_dock_with_receptor(self):
        """[M1034 格忿#31] 선택된 유도체 SMILES를 DockingPopup에 전달하여 도킹 시뮬레이션 실행.

        Rule M: SMILES 없을 시 silent return 금지 — logger.warning + 사용자 안내 필수.
        Rule L: Chem.MolFromSmiles() + None 체크 (RDKIT_AVAILABLE 분기).
        Rule N: isinstance 타입 가드 적용.
        """
        # N코드: 타입 가드 — _selected_variant None 체크
        if self._selected_variant is None:
            logger.warning(
                "[LeadOptimizer._on_dock_with_receptor] _selected_variant 없음 (M1034 Rule M)"
            )
            QMessageBox.warning(
                self, "알림",
                "도킹할 유도체가 선택되지 않았습니다.\n결과 목록에서 유도체를 먼저 선택하세요."
            )
            return

        smiles = getattr(self._selected_variant, 'smiles', '') or ''
        # N코드: isinstance 타입 가드
        if not isinstance(smiles, str) or not smiles.strip():
            logger.warning(
                "[LeadOptimizer._on_dock_with_receptor] SMILES 없음: %r (M1034 Rule M)",
                smiles,
            )
            QMessageBox.warning(
                self, "알림",
                "선택된 유도체의 SMILES가 없습니다. 결과를 다시 생성하세요."
            )
            return

        # L코드: RDKit SMILES 유효성 검증
        try:
            from rdkit import Chem as _Chem
            mol = _Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning(
                    "[LeadOptimizer._on_dock_with_receptor] SMILES RDKit 파싱 실패: %s (Rule L)",
                    smiles,
                )
                QMessageBox.warning(
                    self, "SMILES 오류",
                    f"유도체 SMILES가 유효하지 않습니다.\nSMILES: {smiles}\n"
                    "PubChem에서 검증된 SMILES를 사용하세요."
                )
                return
        except ImportError:
            # RDKit 미설치 시 경고만 기록하고 진행
            logger.warning(
                "[LeadOptimizer._on_dock_with_receptor] RDKit 미설치 — SMILES 검증 건너뜀 (Rule L)"
            )

        # DockingPopup 열기 — initial_smiles 주입 (M1034 格忿#31 핵심)
        try:
            from popup_docking import DockingPopup
            canvas = getattr(self, '_canvas', None)
            popup = DockingPopup(canvas=canvas, parent=self, initial_smiles=smiles)
            logger.info(
                "[LeadOptimizer._on_dock_with_receptor] DockingPopup 열기: smiles=%s (M1034)",
                smiles[:60],
            )
            # Rule F: 오프스크린/캡처 모드 분기
            import os
            if (
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
                or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            ):
                popup.setModal(False)
                popup.show()
            else:
                popup.exec()
        except Exception as exc:
            logger.warning(
                "[LeadOptimizer._on_dock_with_receptor] DockingPopup 열기 실패: %s (M1034 Rule M)",
                exc,
            )
            QMessageBox.critical(
                self, "도킹 팝업 오류",
                f"도킹 시뮬레이션 팝업을 열 수 없습니다.\n{exc}"
            )

    def _on_export_csv(self):
        """유도체 목록을 CSV 파일로 내보내기."""
        if self._result is None:
            QMessageBox.warning(self, "알림", "파이프라인 결과가 없습니다.")
            return
        variants = self._result.ranked_variants
        if not variants:
            QMessageBox.warning(self, "알림", "내보낼 유도체 데이터가 없습니다.")
            return
        try:
            from PyQt6.QtWidgets import QFileDialog
            default_name = f"lead_variants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "CSV 내보내기", default_name,
                "CSV 파일 (*.csv);;모든 파일 (*)")
            if not file_path:
                return
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "순위", "SMILES", "변형 설명", "휴리스틱 도킹 점수 (kcal/mol-style)",
                    "휴리스틱 점수 변화 (kcal/mol-style)", "QED", "SA Score", "티어",
                ])
                for i, v in enumerate(variants):
                    # N코드: 외부 데이터 타입 가드
                    smiles = v.smiles if hasattr(v, 'smiles') and isinstance(v.smiles, str) else ""
                    desc = v.modification_detail if hasattr(v, 'modification_detail') and isinstance(v.modification_detail, str) else ""
                    dock = v.docking_score if hasattr(v, 'docking_score') and isinstance(v.docking_score, (int, float)) else 0
                    improve = v.docking_delta if hasattr(v, 'docking_delta') and isinstance(v.docking_delta, (int, float)) else 0
                    qed = v.qed_score if hasattr(v, 'qed_score') and isinstance(v.qed_score, (int, float)) else 0
                    sa = v.sa_score if hasattr(v, 'sa_score') and isinstance(v.sa_score, (int, float)) else 0
                    tier = v.tier if hasattr(v, 'tier') and isinstance(v.tier, str) else ""
                    writer.writerow([
                        i + 1, smiles, desc,
                        f"{dock:.3f}", f"{improve:+.2f}",
                        f"{qed:.3f}", f"{sa:.2f}", tier,
                    ])
            QMessageBox.information(
                self, "CSV 내보내기 완료",
                f"{len(variants)}개 유도체를 CSV로 내보냈습니다.\n{file_path}")
            logger.info("CSV export complete: %s (%d variants)", file_path, len(variants))
        except Exception as exc:
            logger.warning("CSV export failed: %s", exc)
            QMessageBox.critical(self, "CSV 내보내기 실패", str(exc))

    def _on_export_lead_report(self):
        """Export lead-optimization report PDF plus claim-validation sidecar.

        Academic citations for lead-optimization methodology:
        - Free & Wilson (1964): additive substituent contributions model.
          Free, S.M.; Wilson, J.W. J. Med. Chem. 1964, 7, 395-399.
        - Griffen et al. (2011): matched molecular pair analysis for SAR.
          Griffen, E. et al. J. Med. Chem. 2011, 54, 7739-7750.
        - Sun et al. (2012): scaffold hopping and lead diversification.
          Sun, H. et al. J. Chem. Inf. Model. 2012, 52, 1757-1768.
        """
        if self._result is None:
            # M1038: cp949 mojibake fix (Rule Q) — was garbled hex eb9aae e2949d eb9aaf ec94a0
            QMessageBox.warning(self, "알림", "파이프라인 결과가 없습니다.")
            return
        receptor_info = self._selected_receptor_context()
        from PyQt6.QtWidgets import QFileDialog
        safe_name = (getattr(self, "_initial_name", "") or "lead_optimizer")
        safe_name = str(safe_name).replace(" ", "_").replace("/", "_").replace("\\", "_")
        default_name = f"Lead_Optimizer_Report_{safe_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Lead optimizer report save", default_name,
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not file_path:
            return
        success, msg = export_lead_optimizer_report(
            self._result,
            file_path,
            receptor_info=receptor_info,
            selected_variant=self._selected_variant,
            ligand_name=safe_name,
        )
        if success:
            # M1038: cp949 mojibake fix (Rule Q) — was garbled hex eabea8 eca6ba
            QMessageBox.information(self, "완료", f"Lead optimizer report saved:\n{msg}")
        else:
            # M1038: cp949 mojibake fix (Rule Q) — was garbled hex e385bb ecaa9f
            QMessageBox.warning(self, "오류", f"Lead optimizer report failed:\n{msg}")

    def _on_export_drylab_report(self):
        """Export DryLab comprehensive research report PDF."""
        if self._result is None:
            QMessageBox.warning(self, "알림", "파이프라인 결과가 없습니다.")
            return

        try:
            from drylab_report_exporter import DryLabData, export_drylab_report
        except ImportError as exc:
            QMessageBox.critical(self, "오류", f"DryLab 모듈 로드 실패: {exc}")
            return

        # Collect data from pipeline results
        base_smi = self._initial_smiles or ""
        mol_name = self._initial_name if hasattr(self, '_initial_name') else base_smi

        receptor_info = self._selected_receptor_context()
        alphafold_uniprot_id = str(receptor_info.get("uniprot_id", "") or "")

        # Build docking results list from ranked variants
        docking_results = []
        result_engine_basis = getattr(self._result, "engine_basis", LEAD_ENGINE_DISCLOSURE_TEXT)
        for v in self._result.ranked_variants:
            docking_results.append({
                "smiles": v.smiles,
                "name": getattr(v, "modification_detail", getattr(v, "modification_type", "")),
                "score": v.docking_score,
                "delta": v.docking_delta,
                "method": "RDKit descriptor heuristic; AutoDock Vina was not run for this evidence",
                "engine_basis": getattr(v, "engine_basis", result_engine_basis),
            })

        # ── Data Bridge 1: synthesis_routes from _cached_routes ──
        synthesis_routes = self._cached_routes if self._cached_routes else []

        # ── Data Bridge 2: admet_profile from predict_admet() ──
        admet_profile = {}
        if ADMET_OK and base_smi:
            try:
                _admet = predict_admet(base_smi)
                if _admet:
                    admet_profile = {
                        "Lipinski PASS": getattr(getattr(_admet, 'lipinski', None), 'passes', 'N/A'),
                        "Lipinski Violations": getattr(getattr(_admet, 'lipinski', None), 'violations', 'N/A'),
                        "BBB Score": getattr(getattr(_admet, 'bbb', None), 'score', 'N/A'),
                        "GI Absorption": getattr(_admet, 'gi_absorption', 'N/A'),
                        "Evidence Basis": getattr(
                            _admet,
                            'evidence_basis',
                            'RDKit descriptors and rule heuristics; not ML/clinical validation',
                        ),
                        "ML/Clinical Validation": bool(
                            getattr(_admet, 'has_ml_clinical_validation', False)
                        ),
                    }
            except Exception as e:
                logger.warning("ADMET prediction failed: %s", e)

        # ── Data Bridge 3: mol_data from RDKit descriptors ──
        mol_data = {}
        if _RDKIT_DRAW_OK and base_smi:
            try:
                _mol = Chem.MolFromSmiles(base_smi)
                if _mol is None:
                    logger.warning("Invalid base SMILES for mol_data bridge: %s", base_smi)
                if _mol:
                    mol_data = {
                        "formula": rdMolDescriptors.CalcMolFormula(_mol),
                        "mw": Descriptors.ExactMolWt(_mol),
                        "logp": Crippen.MolLogP(_mol),
                        "tpsa": Descriptors.TPSA(_mol),
                        "hbd": Descriptors.NumHDonors(_mol),
                        "hba": Descriptors.NumHAcceptors(_mol),
                        "rotatable_bonds": Descriptors.NumRotatableBonds(_mol),
                        "heavy_atoms": _mol.GetNumHeavyAtoms(),
                        "rings": Descriptors.RingCount(_mol),
                    }
            except Exception as e:
                logger.warning("Descriptor calculation failed: %s", e)

        # ── Data Bridge 4: ai_analysis_text from AI summary label ──
        ai_analysis_text = ""
        try:
            _ai_text = self.lbl_ai_summary.text()
            if _ai_text and "AI 분석 중" not in _ai_text and "AI 분석 대기" not in _ai_text:
                ai_analysis_text = _ai_text
        except Exception as e:
            logger.warning("Operation failed: %s", e)

        # ── Data Bridge 5: spectra from predict_all() ──
        spectra = {}
        try:
            from predict_spectra import predict_all as _predict_all
            _spec = _predict_all(base_smi)
            if _spec:
                if _spec.ir_peaks:
                    spectra["ir_peaks"] = [
                        {"wavenumber": p.wavenumber, "intensity": f"{100 - p.transmittance:.0f}%",
                         "assignment": p.assignment} for p in _spec.ir_peaks[:12]]
                if _spec.h1_nmr_peaks:
                    spectra["nmr_h_peaks"] = [
                        {"shift": p.shift, "integration": p.integration,
                         "assignment": p.assignment} for p in _spec.h1_nmr_peaks]
                if getattr(_spec, 'c13_peaks', None):
                    spectra["nmr_c13_peaks"] = [
                        {"shift": p.shift, "assignment": p.assignment}
                        for p in _spec.c13_peaks]
                if getattr(_spec, 'uvvis_peaks', None):
                    spectra["uvvis_peaks"] = [
                        {"wavelength": p.wavelength, "epsilon": p.epsilon,
                         "transition": p.transition_type, "assignment": p.assignment}
                        for p in _spec.uvvis_peaks]
        except Exception as e:
            logger.warning("Operation failed: %s", e)

        data = DryLabData(
            smiles=base_smi,
            name=mol_name,
            mol_data=mol_data,
            spectra=spectra,
            docking_results=docking_results,
            receptor_info=receptor_info,
            derivatives=self._result.ranked_variants,
            synthesis_routes=synthesis_routes,
            admet_profile=admet_profile,
            screenshots={},
            base_docking_score=self._result.base_docking_score,
            goal=self._result.goal,
            ai_analysis_text=ai_analysis_text,
            engine_basis=result_engine_basis,
            external_links=receptor_info.get("external_links", {}) if isinstance(receptor_info, dict) else {},
            alphafold_uniprot_id=alphafold_uniprot_id,
            external_route_evidence_status=(
                receptor_info.get("external_route_evidence", {}).get(
                    "external_route_evidence_status",
                    "APP_LINK_ONLY_BROWSER_CDP_REQUIRED",
                )
                if isinstance(receptor_info.get("external_route_evidence", {}), dict)
                else "APP_LINK_ONLY_BROWSER_CDP_REQUIRED"
            ),
            has_browser_cdp_external_capture=False,
            has_loaded_webgl_structure_proof=False,
            has_nonblank_alphafold_pdbe_image=False,
            alphafold_entry_status="LINK_ONLY_ACCESS_MAY_BE_BLOCKED",
            pdbe_alphafold_route_status="LINK_ONLY_ROUTE_MAY_BE_BLOCKED",
        )

        # Ask for save location (M683: PDF + DOCX + HWPX 동시 생성)
        from PyQt6.QtWidgets import QFileDialog
        default_name = f"DryLab_Report_{mol_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "DryLab 보고서 저장", default_name,
            "PDF + Word + 한글(HWPX) (*.pdf);;PDF Files (*.pdf);;Word Files (*.docx);;한글 파일 (*.hwpx);;All Files (*)")
        if not file_path:
            return

        # [M1036 D889 F6-6] QProgressDialog — 30s 내 진행바 피드백 (Rule M 사용자 피드백 의무)
        from PyQt6.QtWidgets import QProgressDialog  # Rule S: wasCanceled/setValue/setLabelText 확인됨
        _progress = QProgressDialog("DryLab 보고서 생성 중…", "취소", 0, 14, self)
        _progress.setWindowTitle("DryLab 내보내기")
        _progress.setWindowModality(Qt.WindowModality.WindowModal)
        _progress.setMinimumDuration(500)  # MAGIC: 0.5s — 빠른 export 시 팝업 안 띄움
        _progress.setValue(0)
        _progress.show()
        QApplication.processEvents()

        def _on_drylab_progress(stage_label: str, step: int, total: int) -> None:
            """Stage progress callback for QProgressDialog."""
            if _progress.wasCanceled():
                return
            _progress.setLabelText(f"DryLab 보고서 생성 중… ({step}/{total})\n{stage_label}")
            _progress.setValue(step)
            QApplication.processEvents()

        try:
            success, msg = export_drylab_report(data, file_path,
                                                progress_callback=_on_drylab_progress)
        finally:
            _progress.setValue(14)
            _progress.close()

        if success:
            # M683: msg 형태 "pdf|docx|hwpx" 파싱
            _paths = msg.split("|") if "|" in msg else [msg]
            _pdf_path = next((p for p in _paths if p.lower().endswith(".pdf")), file_path)
            _docx_path = next((p for p in _paths if p.lower().endswith(".docx")), None)
            _hwpx_path = next((p for p in _paths if p.lower().endswith(".hwpx")), None)
            _msg_text = str(msg or "")
            if _msg_text.startswith("WARN:"):
                _export_status = "WARN"
            elif _msg_text.startswith("FAIL:") or not all(
                p for p in (_pdf_path, _hwpx_path)
            ):
                _export_status = "FAIL"
            else:
                _export_status = "PASS"
            _warning_summary = ""
            if _export_status == "WARN":
                _warning_summary = str(msg).split("|", 1)[0]
                if _warning_summary.startswith("WARN:"):
                    _warning_summary = _warning_summary[5:].strip()
            _output_summary = f"PDF: {_pdf_path}"
            if _docx_path:
                _output_summary += f"\nWord (.docx): {_docx_path}"
            if _hwpx_path:
                _output_summary += f"\n한글 (.hwpx): {_hwpx_path}"
            # ── DryLab AI Reviewer: 자동 품질 검증 ──
            if _export_status == "FAIL":
                QMessageBox.critical(
                    self,
                    "DryLab export validation failed",
                    "DryLab export did not produce the required PDF/HWPX outputs.\n"
                    f"{_output_summary}\n\n"
                    "Status: FAIL (not PASS). Check the export evidence sidecar."
                )
                return
            review_passed = True
            try:
                from drylab_report_reviewer import review_drylab_report
                review = review_drylab_report(_pdf_path)
                if review.passed:
                    if _export_status == "WARN":
                        detail = (
                            f"DryLab 보고서가 생성되었지만 내보내기 경고가 있습니다.\n"
                            f"{_output_summary}\n\n"
                            f"내보내기 상태: WARN\n"
                            f"검토 점수: {review.score:.1f}/100\n"
                            "검토 점수는 문서 품질 점수이며 WARN 상태를 PASS로 바꾸지 않습니다."
                        )
                        if _warning_summary:
                            detail += f"\n\n경고 요약:\n{_warning_summary}"
                    else:
                        detail = (
                            f"DryLab 보고서가 저장되었습니다.\n{_output_summary}\n\n"
                            f"AI 검증 결과: PASS ({review.score:.1f}/100)"
                        )
                    if review.suggestions:
                        detail += "\n\n개선 제안:\n" + "\n".join(
                            f"  - {s}" for s in review.suggestions[:5]
                        )
                    if _export_status == "WARN":
                        QMessageBox.warning(self, "경고 포함 완료", detail)
                    else:
                        QMessageBox.information(self, "완료", detail)
                else:
                    review_passed = False
                    detail = (
                        f"DryLab 보고서가 저장되었으나 품질 검증에 "
                        f"실패했습니다.\n\n"
                        f"점수: {review.score:.1f}/100 (기준: 70점)\n\n"
                        f"이슈:\n" + "\n".join(
                            f"  - {iss}" for iss in review.issues[:10]
                        )
                    )
                    if review.suggestions:
                        detail += "\n\n개선 제안:\n" + "\n".join(
                            f"  - {s}" for s in review.suggestions[:5]
                        )
                    detail += "\n\n보고서를 다시 생성하시겠습니까?"
                    retry = QMessageBox.question(
                        self, "품질 검증 실패", detail,
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.No,
                    )
                    if retry == QMessageBox.StandardButton.Yes:
                        # 사용자가 재생성을 원하면 재귀 호출
                        self._on_export_drylab_report()
                        return
            except ImportError:
                logger.warning("drylab_report_reviewer 모듈 없음 — 검증 생략")
            except Exception as rev_exc:
                logger.warning("DryLab 검증 오류: %s", rev_exc)

            # PASS이거나 검증 스킵 시 파일 열기
            if review_passed:
                try:
                    from PyQt6.QtGui import QDesktopServices
                    from PyQt6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
                except Exception as e:
                    logger.warning("Module import failed: %s", e)
        else:
            QMessageBox.critical(self, "오류", f"보고서 생성 실패:\n{msg}")
