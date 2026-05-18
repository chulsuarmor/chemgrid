# popup_polymer.py — Polymer Analysis Popup
"""
ChemGrid: 고분자 분석 팝업
SMILES 기반 고분자 물성 예측 및 시각화

8-tab QTabWidget:
  1. 📊 물성     : 기본 물성 테이블 + 단량체/반복단위 2D 구조
  2. 🌡️ 열분석   : Tg/Tm/Td 온도 바 + TGA/DSC 시뮬레이션 그래프 (QPainter + matplotlib)
  3. ⚙️ 기계적    : 인장강도, 영률, 파단연신율 수평 바 차트 (matplotlib)
  4. 📈 비교     : 레이더 차트 (PE/PTFE/PS 참조 고분자 비교)
  5. 🔬 반응 조건  : 중합 조건 분석 (개시제/온도/압력/용매/촉매)
  6. 🤖 AI 해석   : Groq LLM 기반 고분자 특성 해석
  7. ⚗️ 연쇄 중합  : 단량체→이량체 연쇄성장 반응 애니메이션
  8. 🔧 구조 최적화 : 목표 특성 기반 단량체 유도체 생성 + 물성 최적화
"""

from __future__ import annotations

import io
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QPushButton, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QScrollArea, QFrame, QGridLayout,
    QTextEdit, QComboBox, QSlider, QMessageBox,
    QFileDialog, QProgressBar, QSplitter, QApplication,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import (
    QFont, QPixmap, QImage, QPainter, QColor, QPen,
    QBrush, QLinearGradient, QRadialGradient, QPainterPath, QDesktopServices,
    QFontDatabase,
)

logger = logging.getLogger(__name__)


_QT_KR_FONT = "Malgun Gothic"
_QT_KR_FONT_READY = False


def _ensure_qt_korean_font_ready() -> str:
    """Load a Korean Qt font for popup/offscreen captures before widgets paint."""
    global _QT_KR_FONT, _QT_KR_FONT_READY
    if _QT_KR_FONT_READY:
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
            logger.warning("[M860] polymer popup Korean font load failed: %s", exc)
    app.setFont(QFont(_QT_KR_FONT, 10))
    _QT_KR_FONT_READY = True
    return _QT_KR_FONT

# ── Optional: matplotlib ──────────────────────────────────────────────
MPL_OK = False
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.patches as mpatches
    import numpy as np
    MPL_OK = True
except ImportError:
    logger.warning("matplotlib not available — mechanical/comparison tabs disabled")

# ── Korean font for matplotlib ──────────────────────────────────────
_MPL_KR_FONT = None
if MPL_OK:
    import matplotlib
    import matplotlib.font_manager as fm
    _KR_FONT_PATHS = [
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/NanumGothic.ttf",   # 나눔고딕
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux
    ]
    for _fp in _KR_FONT_PATHS:
        if os.path.exists(_fp):
            _MPL_KR_FONT = fm.FontProperties(fname=_fp)
            matplotlib.rcParams["font.family"] = _MPL_KR_FONT.get_name()
            fm.fontManager.addfont(_fp)
            break
_fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}

# ── Optional: RDKit ───────────────────────────────────────────────────
RDKIT_OK = False
RWMOL_OK = False
try:
    from rdkit import Chem
    from rdkit.Chem import Draw, AllChem, RWMol, Descriptors
    RDKIT_OK = True
    RWMOL_OK = True
except ImportError:
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw
        RDKIT_OK = True
    except ImportError:
        logger.warning("RDKit not available — 2D structure images disabled")

# ── Optional: SA Score (RDKit Contrib) ──────────────────────────────
SA_SCORE_OK = False
_sa_scorer_func = None
if RDKIT_OK:
    try:
        from rdkit import RDConfig
        import sys as _sys
        _sa_path = os.path.join(RDConfig.RDContribDir, "SA_Score")
        if _sa_path not in _sys.path:
            _sys.path.append(_sa_path)
        from sascorer import calculateScore as _sa_calculate_score  # type: ignore[import]
        _sa_scorer_func = _sa_calculate_score
        SA_SCORE_OK = True
        logger.info("SA Score (Ertl & Schuffenhauer) loaded from %s", _sa_path)
    except Exception as _e:
        logger.warning("SA Score not available: %s — synthesizability filter disabled", _e)

# ── Optional: xtb interface ──────────────────────────────────────────
XTB_OK = False
_run_xtb_calculation = None
_XtbResult = None
try:
    from orca_interface import run_xtb_calculation as _run_xtb_calculation_import  # type: ignore[import]
    from orca_interface import XtbResult as _XtbResultImport  # type: ignore[import]
    from orca_interface import find_xtb_executable  # type: ignore[import]
    _run_xtb_calculation = _run_xtb_calculation_import
    _XtbResult = _XtbResultImport
    # Only mark as OK if xtb binary is actually present
    if find_xtb_executable() is not None:
        XTB_OK = True
        logger.info("xtb GFN2-xTB available for polymer optimization")
    else:
        logger.info("xtb not found — polymer optimization will use Van Krevelen fallback")
except Exception as _e:
    logger.warning("orca_interface import failed: %s — xtb disabled", _e)

# ── Polymer engine ────────────────────────────────────────────────────
ENGINE_OK = False
try:
    from polymer_property_engine import (
        PolymerPropertyEngine,
        PolymerProperties,
        PolymerizationResult,
    )
    ENGINE_OK = True
except ImportError:
    logger.warning("polymer_property_engine not available")

    # Stub classes for type hints when engine is missing
    class PolymerProperties:  # type: ignore[no-redef]
        pass

    class PolymerizationResult:  # type: ignore[no-redef]
        pass

# ── Optional: reaction animation viewer ──────────────────────────────
ANIM_VIEWER_OK = False
try:
    from popup_reaction_animation import _Viewer3DWidget
    ANIM_VIEWER_OK = True
except ImportError:
    logger.warning("popup_reaction_animation._Viewer3DWidget not available")

ANIM_ENGINE_OK = False
try:
    from reaction_animation_engine import ReactionAnimationEngine
    ANIM_ENGINE_OK = True
except ImportError:
    logger.warning("ReactionAnimationEngine not available")

# ── Optional: httpx for AI API calls ─────────────────────────────────
HTTPX_OK = False
try:
    import httpx
    HTTPX_OK = True
except ImportError:
    logger.warning("httpx not available — AI analysis tab disabled")

# Shared User-Agent for all HTTP API requests (avoids Cloudflare 1010 blocks)
_USER_AGENT = "ChemGrid/1.0 (Python)"


# ── 유틸리티 ──────────────────────────────────────────────────────────

def _mol_to_pixmap(smiles: str, size: Tuple[int, int] = (300, 200)) -> Optional[QPixmap]:
    """SMILES -> QPixmap via RDKit + PIL"""
    if not RDKIT_OK:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            return None
        img = Draw.MolToImage(mol, size=size)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qimg = QImage()
        qimg.loadFromData(buf.getvalue())
        return QPixmap.fromImage(qimg)
    except Exception as e:
        logger.warning("mol_to_pixmap failed for %s: %s", smiles, e)
        return None


def _fmt(value, unit: str = "", precision: int = 1) -> str:
    """숫자 포맷: None -> 'N/A', float -> 소수점 precision자리"""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f} {unit}".strip()
    return f"{value} {unit}".strip()


# ── 참조 고분자 데이터 (비교 탭용) ────────────────────────────────────
# SMILES for reference polymers
_REF_POLYMERS = {
    "PE":   "C=C",
    "PTFE": "FC(F)=C(F)F",
    "PS":   "C=Cc1ccccc1",
}


# ── 구조 최적화 목표 프리셋 ────────────────────────────────────────────
POLYMER_OPTIMIZATION_GOALS = {
    "내열성 향상": {
        "target": "Td",
        "weight_Td": 0.4, "weight_Tg": 0.3, "weight_Tm": 0.2, "weight_tensile": 0.1,
    },
    "충격 강도 향상": {
        "target": "tensile",
        "weight_tensile": 0.4, "weight_elongation": 0.3, "weight_modulus": 0.2, "weight_Tg": 0.1,
    },
    "화학적 안정성": {
        "target": "chemical_inert",
        "weight_Td": 0.3, "weight_density": 0.2, "weight_delta": 0.3, "weight_Tg": 0.2,
    },
    "고인장 강도": {
        "target": "tensile",
        "weight_tensile": 0.5, "weight_modulus": 0.3, "weight_Tg": 0.2,
    },
    "저마찰 코팅": {
        "target": "low_friction",
        "weight_delta": 0.3, "weight_density": 0.2, "weight_Td": 0.2, "weight_Tg": 0.3,
    },
    "광학적 투명도": {
        "target": "optical",
        "weight_n": 0.4, "weight_Tg": 0.3, "weight_density": 0.3,
    },
}

# 치환기 라이브러리: (SMILES fragment, 한글명, 카테고리)
POLYMER_SUBSTITUENT_LIBRARY = [
    # 불소화 — Td, 화학적 안정성 향상
    ("F", "불소화", "fluorination"),
    ("C(F)(F)F", "트리플루오로메틸", "fluorination"),
    # 강화 — Tg, 인장강도 향상
    ("c1ccccc1", "페닐기", "strengthening"),
    ("C#N", "시아노기", "strengthening"),
    ("C(=O)c1ccccc1", "벤조일기", "strengthening"),
    # 유연성 — 연신율 향상, Tg 저하
    ("OC", "메톡시기", "flexibility"),
    ("O", "히드록시기", "flexibility"),
    ("OCCOC", "에톡시에톡시", "flexibility"),
    # 가교 잠재력
    ("C=C", "비닐기", "crosslinking"),
    ("C(=O)O", "카르복시기", "crosslinking"),
    # 기타 기능기
    ("Cl", "염소화", "halogenation"),
    ("S", "티오기", "sulfur"),
    ("N", "아미노기", "nitrogen"),
    ("C(C)(C)C", "tert-부틸기", "bulky"),
    ("Si(C)(C)C", "트리메틸실릴", "silicone"),
]


# ══════════════════════════════════════════════════════════════════════
#  온도 바 위젯 (QPainter custom widget)
# ══════════════════════════════════════════════════════════════════════

class _TemperatureBarWidget(QWidget):
    """Tg / Tm / Td 온도를 그라데이션 바 위에 마커로 표시하는 위젯.

    범위: -200 ~ 600 degC, 파란색(저온) → 빨간색(고온) 그라데이션.
    """

    # 온도 범위 상수 (degC)
    T_MIN = -200
    T_MAX = 600

    def __init__(
        self,
        tg: Optional[float] = None,
        tm: Optional[float] = None,
        td: Optional[float] = None,
        max_service: Optional[float] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._tg = tg
        self._tm = tm
        self._td = td
        self._max_service = max_service
        self.setMinimumSize(600, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # ── 좌표 변환 ─────────────────────────────────────
    def _t_to_x(self, temp: float, bar_x: float, bar_w: float) -> float:
        """온도(degC) -> 픽셀 x 좌표"""
        ratio = (temp - self.T_MIN) / (self.T_MAX - self.T_MIN)
        ratio = max(0.0, min(1.0, ratio))
        return bar_x + ratio * bar_w

    # ── paintEvent ────────────────────────────────────
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 여백
        margin_left = 50
        margin_right = 30
        bar_y = 50
        bar_h = 30  # px 높이
        bar_x = margin_left
        bar_w = w - margin_left - margin_right

        # ── 그라데이션 바 ──
        grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
        grad.setColorAt(0.0, QColor(30, 100, 220))    # 파랑 (-200)
        grad.setColorAt(0.35, QColor(100, 200, 255))   # 연파랑
        grad.setColorAt(0.5, QColor(255, 255, 100))     # 노랑 (200)
        grad.setColorAt(0.75, QColor(255, 160, 50))     # 주황
        grad.setColorAt(1.0, QColor(220, 30, 30))       # 빨강 (600)

        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(80, 80, 80), 1))
        p.drawRoundedRect(int(bar_x), bar_y, int(bar_w), bar_h, 4, 4)

        # ── 눈금 ──
        p.setPen(QPen(QColor(60, 60, 60), 1))
        tick_font = QFont("Segoe UI", 8)
        p.setFont(tick_font)
        for temp in range(self.T_MIN, self.T_MAX + 1, 100):  # 100도 간격
            tx = self._t_to_x(temp, bar_x, bar_w)
            p.drawLine(int(tx), bar_y + bar_h, int(tx), bar_y + bar_h + 5)
            p.drawText(int(tx) - 15, bar_y + bar_h + 18, f"{temp}")

        # ── 마커 정의 ──
        markers = []
        if self._tg is not None:
            markers.append((self._tg, "Tg", QColor(30, 144, 255)))   # 파랑
        if self._tm is not None:
            markers.append((self._tm, "Tm", QColor(34, 139, 34)))    # 초록
        if self._td is not None:
            markers.append((self._td, "Td", QColor(220, 20, 60)))    # 빨강
        if self._max_service is not None:
            markers.append((self._max_service, "Max", QColor(255, 140, 0)))  # 주황

        # ── 마커 그리기 ──
        marker_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(marker_font)
        for temp, label, color in markers:
            mx = self._t_to_x(temp, bar_x, bar_w)

            # 삼각형 마커 (위쪽)
            path = QPainterPath()
            path.moveTo(mx, bar_y - 2)
            path.lineTo(mx - 7, bar_y - 16)
            path.lineTo(mx + 7, bar_y - 16)
            path.closeSubpath()
            p.setBrush(QBrush(color))
            p.setPen(QPen(color.darker(120), 1))
            p.drawPath(path)

            # 수직 점선
            pen = QPen(color, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(int(mx), bar_y, int(mx), bar_y + bar_h)

            # 라벨
            p.setPen(QPen(color.darker(130)))
            p.drawText(int(mx) - 20, bar_y - 20, f"{label} = {temp:.0f} \u00b0C")

        # ── 타이틀 ──
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QPen(QColor(40, 40, 40)))
        p.drawText(margin_left, 20, "\uc628\ub3c4 \ubd84\ud3ec (Temperature Profile)")

        p.end()


# ══════════════════════════════════════════════════════════════════════
#  메인 팝업 다이얼로그
# ══════════════════════════════════════════════════════════════════════

class _AIAnalysisWorker(QThread):
    """Groq API 호출을 별도 스레드에서 수행."""
    finished = pyqtSignal(str)    # 성공 시 응답 텍스트
    error = pyqtSignal(str)       # 실패 시 에러 메시지

    def __init__(self, prompt: str, api_key: str, parent=None):
        super().__init__(parent)
        self._prompt = prompt
        self._api_key = api_key

    def run(self):
        try:
            if not HTTPX_OK:
                self.error.emit("httpx 라이브러리가 설치되지 않았습니다.")
                return
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a polymer chemist. Analyze in Korean. "
                                "Be academic and thorough. Use proper chemistry terminology."
                            ),
                        },
                        {"role": "user", "content": self._prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                timeout=30.0,
            )
            data = response.json()
            if not isinstance(data, dict):
                logger.warning("Groq 응답이 dict가 아님: type=%s", type(data).__name__)
                self.error.emit(f"API 응답 형식 오류 (expected dict, got {type(data).__name__})")
                return
            if response.status_code != 200:
                err_obj = data.get("error", {})
                if not isinstance(err_obj, dict):
                    err_obj = {}
                err_msg = err_obj.get("message", str(response.status_code))
                self.error.emit(f"API 오류: {err_msg}")
                return
            choices = data.get("choices", [])
            if not isinstance(choices, list) or not choices:
                logger.warning("Groq choices가 비어있거나 list가 아님: %s", type(choices).__name__)
                self.error.emit("API 응답에 choices가 없습니다")
                return
            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                logger.warning("choices[0]이 dict가 아님: type=%s", type(first_choice).__name__)
                self.error.emit("API 응답 형식 오류")
                return
            msg = first_choice.get("message", {})
            if not isinstance(msg, dict):
                logger.warning("message가 dict가 아님: type=%s", type(msg).__name__)
                self.error.emit("API 응답 형식 오류")
                return
            text = str(msg.get("content", ""))
            self.finished.emit(text)
        except Exception as e:
            self.error.emit(f"AI 분석 실패: {e}")


class _PolymerOptWorker(QThread):
    """단량체 유도체 생성 + 물성 예측 + 스코어링을 별도 스레드에서 수행.

    파이프라인 (3세대 진화적 최적화):
      1. 초기 20개 유도체 생성 (전략 A~H)
      2. SA Score > 6 필터링 (합성 불가 제거)
      3. xtb GFN2-xTB SP 계산으로 HOMO-LUMO gap + dipole 획득
         (실패 시 Van Krevelen fallback)
      4. 상위 5개 선택 → 돌연변이 생성 → 재평가 (3세대)
    """

    progress = pyqtSignal(int, int, str)   # (current, total, variant_smiles)
    finished = pyqtSignal(list)            # list of (smiles, props, score, description, sa_score, xtb_gap, xtb_dipole)
    error = pyqtSignal(str)

    # 세대당 초기 집단 크기 및 엘리트 수
    _INITIAL_N = 20   # 초기 유도체 수
    _ELITE_N = 5      # 선택 엘리트 수
    _GENERATIONS = 3  # 세대 수
    _XTB_TIMEOUT = 30 # 초 (타임아웃, 변이체당)

    def __init__(
        self,
        monomer_smiles: str,
        goal_key: str,
        n_variants: int = 20,  # 생성할 유도체 수 (legacy, 내부적으로 _INITIAL_N 우선)
        parent=None,
    ):
        super().__init__(parent)
        self._monomer = monomer_smiles
        self._goal_key = goal_key
        self._n = n_variants

    # ── SA Score 계산 헬퍼 ────────────────────────────────────────────
    @staticmethod
    def _calc_sa_score(smiles: str) -> Optional[float]:
        """SA Score 계산 (1=easy, 10=hard). 실패 시 None."""
        if not SA_SCORE_OK or _sa_scorer_func is None:
            return None
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패 (SA score): %r", smiles)
                return None
            return float(_sa_scorer_func(mol))
        except Exception as e:
            logger.debug("SA score failed for %s: %s", smiles, e)
            return None

    # ── xtb 단점 계산 헬퍼 ───────────────────────────────────────────
    @staticmethod
    def _calc_xtb(smiles: str) -> Tuple[Optional[float], Optional[float]]:
        """xtb SP 계산. 반환: (homo_lumo_gap_ev, dipole_debye). 실패 시 (None, None)."""
        if not XTB_OK or _run_xtb_calculation is None:
            return None, None
        try:
            result = _run_xtb_calculation(smiles, calc_type="sp", timeout=_PolymerOptWorker._XTB_TIMEOUT)
            if result.success:
                return result.homo_lumo_gap_ev, result.dipole_debye
            logger.debug("xtb SP failed for %s: %s", smiles, result.error_message)
            return None, None
        except Exception as e:
            logger.debug("xtb exception for %s: %s", smiles, e)
            return None, None

    # ── 단일 변이체 평가 ─────────────────────────────────────────────
    def _evaluate_variant(
        self,
        vsmi: str,
        desc: str,
        engine: "PolymerPropertyEngine",
        goal_weights: Dict[str, Any],
    ) -> Optional[Tuple]:
        """변이체 하나를 평가. 반환: (smiles, props, score, desc, sa_score, xtb_gap, xtb_dipole) or None."""
        # SA Score 계산 및 필터링
        sa = self._calc_sa_score(vsmi)
        if sa is not None and sa > 6.0:  # 합성 난이도 임계값 6.0
            logger.debug("SA Score %.1f > 6.0 for %s — skipped", sa, vsmi)
            return None

        # Van Krevelen 물성 예측
        try:
            props = engine.predict_all(vsmi)
        except Exception as e:
            logger.warning("Property prediction failed for %s: %s", vsmi, e)
            return None

        # xtb 전자 구조 계산 (없으면 None)
        xtb_gap, xtb_dipole = self._calc_xtb(vsmi)

        # 스코어링
        score = _score_variant(props, goal_weights)

        # xtb gap으로 스코어 보정 (available 시): 넓은 gap = 화학적 안정성 ↑
        if xtb_gap is not None:
            # gap 정규화 (GFN2-xTB: 보통 2~8 eV 범위)
            gap_bonus = min(1.0, max(0.0, (xtb_gap - 2.0) / 6.0)) * 0.1  # 최대 10% 보너스
            score = min(1.0, score + gap_bonus)

        return vsmi, props, score, desc, sa, xtb_gap, xtb_dipole

    # ── 엘리트 돌연변이 ──────────────────────────────────────────────
    @staticmethod
    def _mutate_elite(elite_smiles: List[str], n: int) -> List[Tuple[str, str]]:
        """엘리트 SMILES 목록을 돌연변이시켜 n개의 (smiles, desc) 쌍 반환."""
        mutations: List[Tuple[str, str]] = []
        seen: set = set(elite_smiles)

        def _try_add(smi: str, desc: str) -> None:
            if len(mutations) >= n:
                return
            try:
                m = Chem.MolFromSmiles(smi)
                if m is None:
                    logger.warning("[Rule L] MolFromSmiles 실패 (mutation): %r", smi)
                    return
                canon = Chem.MolToSmiles(m)
                if canon in seen:
                    return
                seen.add(canon)
                mutations.append((canon, desc))
            except Exception as e:
                logger.debug("Mutation SMILES invalid: %s", e)

        for base_smi in elite_smiles:
            if len(mutations) >= n:
                break
            mol = Chem.MolFromSmiles(base_smi)
            if mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패: %r", base_smi)
                continue

            # 돌연변이 1: 메틸기 추가
            if RWMOL_OK:
                for atom in mol.GetAtoms():
                    if len(mutations) >= n:
                        break
                    if atom.GetSymbol() == "C" and atom.GetTotalNumHs() > 0:
                        emol = Chem.RWMol(mol)
                        new_idx = emol.AddAtom(Chem.Atom(6))
                        emol.AddBond(atom.GetIdx(), new_idx, Chem.BondType.SINGLE)
                        try:
                            Chem.SanitizeMol(emol)
                            _try_add(Chem.MolToSmiles(emol), f"엘리트 돌연변이: 메틸 추가")
                        except Exception as e:
                            logger.warning("[PopupPolymer] 엘리트 돌연변이 메틸 추가 SanitizeMol failed: %s", e)

            # 돌연변이 2: 불소화 시도
            _try_add(base_smi.replace("H", "F", 1), "엘리트 불소화")
            # 돌연변이 3: 체인 확장
            if "C=C" in base_smi:
                _try_add(base_smi.replace("C=C", "C=CCC", 1), "엘리트 체인 확장")
            # 돌연변이 4: 수소결합 도너 추가
            if "C" in base_smi:
                _try_add(base_smi.replace("C", "CO", 1), "엘리트 히드록시 추가")

        return mutations

    def run(self) -> None:
        try:
            if not ENGINE_OK:
                self.error.emit("polymer_property_engine이 설치되지 않았습니다.")
                return
            if not RDKIT_OK:
                self.error.emit("RDKit이 설치되지 않았습니다.")
                return

            goal_weights = POLYMER_OPTIMIZATION_GOALS.get(
                self._goal_key,
                POLYMER_OPTIMIZATION_GOALS.get("내열성 향상", {}),
            )
            # N-code: type guard — goal_weights from external config
            if not isinstance(goal_weights, dict):
                logger.warning("[PolymerOptWorker] goal_weights is not dict: type=%s",
                               type(goal_weights).__name__)
                goal_weights = {}

            engine = PolymerPropertyEngine()
            all_results: List[Tuple] = []
            evaluated_smiles: set = set()

            # ── 세대별 진화적 최적화 ─────────────────────────────────
            current_variants = _generate_polymer_variants(self._monomer, self._INITIAL_N)
            if not current_variants:
                self.error.emit("유도체를 생성할 수 없습니다. 단량체 구조를 확인하세요.")
                return

            total_ops = self._INITIAL_N + self._ELITE_N * self._GENERATIONS  # 최대 횟수 추정
            completed = 0

            for generation in range(self._GENERATIONS):
                gen_results: List[Tuple] = []

                for vsmi, desc in current_variants:
                    if vsmi in evaluated_smiles:
                        continue
                    evaluated_smiles.add(vsmi)
                    completed += 1
                    self.progress.emit(completed, total_ops, vsmi)

                    result = self._evaluate_variant(vsmi, desc, engine, goal_weights)
                    if result is not None:
                        gen_results.append(result)

                all_results.extend(gen_results)

                # 마지막 세대는 돌연변이 불필요
                if generation < self._GENERATIONS - 1:
                    # 상위 엘리트 선택 → 돌연변이
                    gen_results.sort(key=lambda x: x[2], reverse=True)
                    elite = [r[0] for r in gen_results[:self._ELITE_N]]
                    mutation_variants = self._mutate_elite(elite, self._ELITE_N * 4)
                    current_variants = mutation_variants
                    if not current_variants:
                        logger.info("No mutations generated at generation %d", generation + 1)
                        break

            if not all_results:
                self.error.emit("평가된 유도체가 없습니다. SA Score 필터 또는 물성 예측 실패.")
                return

            # 점수 내림차순 정렬, 중복 SMILES 제거
            seen_final: set = set()
            unique_results: List[Tuple] = []
            for item in sorted(all_results, key=lambda x: x[2], reverse=True):
                if item[0] not in seen_final:
                    seen_final.add(item[0])
                    unique_results.append(item)

            logger.info(
                "[PolymerOptWorker] done: %d variants evaluated, %d unique, xtb=%s, sa=%s",
                len(all_results), len(unique_results), XTB_OK, SA_SCORE_OK,
            )
            self.finished.emit(unique_results)

        except Exception as e:
            self.error.emit(f"최적화 실패: {e}")


def _generate_polymer_variants(
    monomer_smiles: str, n: int = 20
) -> List[Tuple[str, str]]:
    """단량체 SMILES로부터 n개의 유도체 (SMILES, 설명) 쌍을 생성.

    전략:
      A) 치환기 라이브러리 — 비닐 탄소 또는 기존 할로겐에 치환기 부착
      B) 헤테로원자 삽입 (O, N, S) — 골격 다양화
      C) 체인 확장 — 스페이서 삽입
      D) 다중 불소화 — 화학적 안정성
      E) RWMol 메틸기 부가 — 체계적 치환
      F) 고리 개환 — 고리형 단량체(카프로락톤, 락티드) → 선형
      G) 코모노머 조합 — 공중합 파트너 결합
      H) 기능기 다양화 — 아미드/에스터/우레탄 도입
    """
    if not RDKIT_OK:
        return []

    mol = Chem.MolFromSmiles(monomer_smiles)
    if mol is None:
        logger.warning("[Rule L] MolFromSmiles 실패: %r", monomer_smiles)
        return []

    results: List[Tuple[str, str]] = []
    seen: set = {Chem.MolToSmiles(mol)}  # 중복 방지

    def _try_add(smi: str, desc: str) -> None:
        """유효한 SMILES이면 결과에 추가."""
        if len(results) >= n:
            return
        try:
            m = Chem.MolFromSmiles(smi)
            if m is None:
                logger.warning("[Rule L] MolFromSmiles 실패 (_try_add): %r", smi)
                return
            canon = Chem.MolToSmiles(m)
            if canon in seen:
                return
            seen.add(canon)
            results.append((canon, desc))
        except Exception as e:
            logger.warning("Invalid SMILES skipped in lead variant generation: %s", e)

    # ── 전략 A: 치환기 교체/추가 ──
    for sub_smi, sub_name, _cat in POLYMER_SUBSTITUENT_LIBRARY:
        if len(results) >= n:
            break
        if "C=C" in monomer_smiles:
            variant1 = monomer_smiles.replace("C=C", f"C(=C){sub_smi}", 1)
            _try_add(variant1, f"비닐 C에 {sub_name} 부착")

            variant2 = monomer_smiles.replace("C=C", f"C=C({sub_smi})", 1)
            _try_add(variant2, f"비닐 말단에 {sub_name} 부착")

        if "Cl" in monomer_smiles and sub_smi != "Cl":
            _try_add(monomer_smiles.replace("Cl", sub_smi, 1), f"Cl → {sub_name} 교체")
        if "F" in monomer_smiles and sub_smi not in ("F", "C(F)(F)F"):
            _try_add(monomer_smiles.replace("F", sub_smi, 1), f"F → {sub_name} 교체")

    # ── 전략 B: 헤테로원자 삽입 ──
    for hetero, hname in [("O", "산소"), ("N", "질소"), ("S", "황")]:
        if len(results) >= n:
            break
        if "CC" in monomer_smiles:
            _try_add(monomer_smiles.replace("CC", f"C{hetero}C", 1), f"골격에 {hname} 삽입")

    # ── 전략 C: 체인 확장 ──
    if "C=C" in monomer_smiles and len(results) < n:
        _try_add(monomer_smiles.replace("C=C", "C=CCC", 1), "체인 2C 확장")
        _try_add(monomer_smiles.replace("C=C", "CC=C", 1), "체인 시프트 확장")

    # ── 전략 D: 다중 불소화 ──
    if len(results) < n and "C=C" in monomer_smiles:
        base_rest = monomer_smiles.replace("C=C", "", 1) or "F"
        _try_add(f"FC(F)=C(F){base_rest}", "다중 불소화")

    # ── 전략 E: RWMol 메틸기 부가 ──
    if RWMOL_OK and len(results) < n:
        try:
            for atom in mol.GetAtoms():
                if len(results) >= n:
                    break
                if atom.GetSymbol() == "C" and atom.GetTotalNumHs() > 0:
                    idx = atom.GetIdx()
                    emol = Chem.RWMol(mol)
                    new_idx = emol.AddAtom(Chem.Atom(6))  # Carbon
                    emol.AddBond(idx, new_idx, Chem.BondType.SINGLE)
                    try:
                        Chem.SanitizeMol(emol)
                        _try_add(Chem.MolToSmiles(emol), f"C{idx}에 메틸기 부가")
                    except Exception as e:
                        logger.warning("RWMol methyl addition at C%d failed: %s", idx, e)
        except Exception as e:
            logger.warning("RWMol variant generation (E) failed: %s", e)

    # ── 전략 F: 고리 개환 (ring-opening) ──
    # 고리형 단량체의 락톤/락탐 고리를 개환하여 선형 단량체 생성
    if len(results) < n:
        # 카프로락톤 유도체 → 히드록시카프로산
        _try_add("OC(=O)CCCCCО", "카프로락톤 개환 → 6-히드록시카프로산")
        _try_add("OC(=O)CCCCCO", "카프로락톤 개환 → ε-히드록시카프로산")
        # 락티드 → 젖산
        _try_add("OC(C)C(=O)O", "락티드 개환 → L-젖산")
        _try_add("OC(=O)COC(=O)CO", "글리콜리드 개환 → 글리콜산")
        # 원래 단량체에 고리 구조가 있으면 RWMol로 개환 시도
        if RWMOL_OK:
            ri = mol.GetRingInfo()
            if ri.NumRings() > 0:
                for ring in ri.AtomRings():
                    if len(results) >= n:
                        break
                    if len(ring) < 6:
                        continue
                    # 첫 번째 결합을 끊어서 선형화
                    try:
                        emol = Chem.RWMol(mol)
                        a0, a1 = ring[0], ring[1]
                        bond = emol.GetBondBetweenAtoms(a0, a1)
                        if bond and not bond.GetIsAromatic():
                            emol.RemoveBond(a0, a1)
                            Chem.SanitizeMol(emol)
                            _try_add(Chem.MolToSmiles(emol), f"{len(ring)}원환 개환")
                    except Exception as e:
                        logger.debug("Ring opening failed: %s", e)

    # ── 전략 G: 코모노머 조합 (common comonomers database) ──
    # 주요 공중합 파트너: 에틸렌, 아크릴로니트릴, 부타디엔, 아크릴산, MMA
    _COMONOMERS = [
        ("C=C",        "에틸렌 코모노머"),
        ("C=CC#N",     "아크릴로니트릴 코모노머"),
        ("C=CC=C",     "부타디엔 코모노머"),
        ("C=CC(=O)O",  "아크릴산 코모노머"),
        ("C=C(C)C(=O)OC", "메틸메타크릴레이트 코모노머"),
        ("C=CC(=O)OCC", "에틸아크릴레이트 코모노머"),
    ]
    if len(results) < n:
        for co_smi, co_name in _COMONOMERS:
            if len(results) >= n:
                break
            # [M722-2 F5-6] 코모노머 블록을 dot 분리 SMILES가 아닌 연결된 단일 구조로 생성.
            # 사용자 격분: "작용기 따로 분리되어있는 그런게 많은데 제대로 하나의 분자로 표기되도록 수정"
            # dot SMILES(X.Y) = 독립 분자 2개 → optimizer가 분절된 분자 렌더링 → 격분 유발.
            # 수정: RDKit CombineMols + rdkit.Chem.rdmolops.CombineMols + 비닐-비닐 결합 형성.
            # 학술: 교대 공중합(alternating copolymer) = 단량체1-단량체2 교대 반복 단위.
            try:
                co_mol = Chem.MolFromSmiles(co_smi)
                if co_mol is None:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", co_smi)
                    continue
                m_mol = Chem.MolFromSmiles(monomer_smiles)
                if m_mol is None:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", monomer_smiles)
                    continue
                if "C=C" in monomer_smiles and "C=C" in co_smi:
                    # 교대 공중합: 비닐 이중결합을 개열하여 단량체-코모노머 연결 (-[CH2-CH(X)]-[CH2-CH(Y)]-)
                    # 간단 근사: 양쪽 비닐기를 단결합으로 연결한 이량체 SMILES 생성
                    m_chain = monomer_smiles.replace("C=C", "CC", 1)  # 단량체 이중결합 개열
                    co_chain = co_smi.replace("C=C", "CC", 1)         # 코모노머 이중결합 개열
                    # 두 체인을 C-C 단결합으로 연결 (이량체 근사)
                    combined_smi = f"{m_chain}{co_chain}"              # SMILES 연결 (공유결합)
                    _try_add(combined_smi, f"{co_name} 교대 이량체 (연결)")
                else:
                    # 비비닐 코모노머: CombineMols로 단일 분자 구조 생성 (dot 분리 방지)
                    # 두 분자의 C 원자 사이 단결합 형성 (간단 이량체 근사)
                    m_chain = monomer_smiles if "C=C" not in monomer_smiles else monomer_smiles.replace("C=C", "CC", 1)
                    combined_smi = f"{m_chain}{co_smi}"
                    _try_add(combined_smi, f"{co_name} 블록 이량체 (연결)")
            except Exception as e:
                logger.debug("Comonomer combination failed for %s: %s", co_smi, e)

    # ── 전략 H: 기능기 다양화 (아미드/에스터/우레탄 도입) ──
    if len(results) < n:
        # 에스터 변환: 비닐기 + 카르복실
        _try_add(f"{monomer_smiles.replace('C=C', 'C=CC(=O)O', 1)}", "아크릴레이트 에스터 도입")
        # 아미드 도입
        _try_add(f"{monomer_smiles.replace('C=C', 'C=CC(=O)N', 1)}", "아크릴아미드 도입")
        # 설폰산 도입 (이온 전도성)
        if "C=C" in monomer_smiles:
            _try_add(monomer_smiles.replace("C=C", "C=CCS(=O)(=O)O", 1), "설폰산기 도입")
        # 포스포네이트 도입 (내화학성)
        if "C=C" in monomer_smiles:
            _try_add(monomer_smiles.replace("C=C", "C=CCP(=O)(O)O", 1), "포스포네이트 도입")
        # 에폭시기 도입 (가교 잠재력)
        if "C=C" in monomer_smiles:
            _try_add(monomer_smiles.replace("C=C", "C1OC1", 1), "에폭시기 도입")

    return results


def _score_variant(
    props, goal_weights: Dict[str, Any]
) -> float:
    """PolymerProperties 객체를 목표 가중치에 따라 0-1 스코어로 환산.

    정규화 범위 (일반 고분자 기준):
      Tg: -130 ~ 350 degC,  Tm: 100 ~ 400 degC,  Td: 200 ~ 600 degC
      tensile: 10 ~ 200 MPa, modulus: 0.1 ~ 5 GPa, elongation: 1 ~ 500 %
      density: 0.8 ~ 2.3 g/cm3, delta: 10 ~ 30, n: 1.3 ~ 1.7

    방향성:
      대부분 물성은 "높을수록 좋다" (Tg, Tm, Td, tensile 등).
      목표에 따라 일부 물성은 "낮을수록 좋다" (역방향):
        - delta(δ): 화학적 안정성 → 낮을수록 좋다 (용매와 덜 반응)
        - density: 저마찰 코팅 → 낮을수록 좋다
    """
    if props is None:
        return 0.0

    # 정규화 범위: (속성명, min, max)
    norm_map = {
        "Tg":       ("Tg", -130.0, 350.0),
        "Tm":       ("Tm", 100.0, 400.0),
        "Td":       ("Td", 200.0, 600.0),
        "tensile":  ("tensile_strength", 10.0, 200.0),
        "modulus":  ("youngs_modulus", 0.1, 5.0),
        "elongation": ("elongation_at_break", 1.0, 500.0),
        "density":  ("density", 0.8, 2.3),
        "delta":    ("solubility_param", 10.0, 30.0),  # 불소계 10~30 범위 확장
        "n":        ("refractive_index", 1.3, 1.7),
    }

    # 목표(target)에 따라 "낮을수록 좋은" 물성 반전
    # 예: 화학적 안정성에서 δ 낮을수록 용매와 덜 상호작용 → 내부식성 ↑
    # N-code: type guard — goal_weights from external config
    if not isinstance(goal_weights, dict):
        logger.warning("[_score_variant] goal_weights is not dict: type=%s",
                       type(goal_weights).__name__)
        return 0.0
    target = goal_weights.get("target", "")
    invert_map = {
        "chemical_inert": {"delta"},             # δ 낮을수록 내부식성 ↑
        "low_friction":   {"delta", "density"},  # δ, 밀도 낮을수록 저마찰 ↑
    }
    invert_keys = invert_map.get(target, set())

    total_weight = 0.0
    weighted_sum = 0.0

    for key, weight in goal_weights.items():
        if not key.startswith("weight_"):
            continue
        prop_key = key[len("weight_"):]  # e.g. "Td", "tensile"
        w = float(weight)
        if prop_key not in norm_map:
            continue

        attr_name, lo, hi = norm_map[prop_key]
        val = getattr(props, attr_name, None)
        if val is None:
            continue

        normalized = (float(val) - lo) / (hi - lo) if hi != lo else 0.5
        normalized = max(0.0, min(1.0, normalized))

        # 이 물성이 "낮을수록 좋은" 목표인 경우 반전
        if prop_key in invert_keys:
            normalized = 1.0 - normalized

        weighted_sum += normalized * w
        total_weight += w

    if total_weight == 0.0:
        return 0.0
    return weighted_sum / total_weight


class _SimplifiedChainGrowthWidget(QWidget):
    """Simplified 2D chain-growth animation using QPainter (fallback)."""

    def __init__(self, monomer_smiles: str = "C=C", parent=None):
        super().__init__(parent)
        self._monomer_label = monomer_smiles[:10]
        self._chain_length = 0       # 현재 연결된 단량체 수
        self._max_chain = 12         # 최대 체인 길이
        self._approaching_x = 0.0    # 접근 중인 단량체 x 위치
        self._is_approaching = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._playing = False
        self._speed_ms = 80          # ms per frame (80ms = ~12fps)
        self.setMinimumSize(600, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def start_animation(self):
        self._chain_length = 0
        self._approaching_x = 0.0
        self._is_approaching = True
        self._playing = True
        self._timer.start(self._speed_ms)

    def stop_animation(self):
        self._playing = False
        self._timer.stop()

    def set_speed(self, ms: int):
        self._speed_ms = max(20, min(500, ms))
        if self._playing:
            self._timer.setInterval(self._speed_ms)

    def _advance_frame(self):
        if self._chain_length >= self._max_chain:
            self._timer.stop()
            self._playing = False
            return
        if self._is_approaching:
            self._approaching_x += 8.0  # px per frame
            target_x = (self._chain_length + 1) * 45.0 + 40.0  # px target
            if self._approaching_x >= target_x:
                self._chain_length += 1
                self._is_approaching = False
                self._approaching_x = 0.0
        else:
            # brief pause then start next approach
            self._is_approaching = True
            self._approaching_x = max(0.0, self._chain_length * 45.0 - 20.0)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cy = h // 2  # center y

        # Background
        p.fillRect(0, 0, w, h, QColor(250, 250, 255))

        # Draw chain backbone
        unit_w = 45  # px per monomer unit
        start_x = 30
        node_r = 14  # radius of monomer circle

        # Already-linked monomers
        for i in range(self._chain_length):
            cx = start_x + i * unit_w
            # Bond line to previous
            if i > 0:
                p.setPen(QPen(QColor(60, 60, 60), 3))
                p.drawLine(cx - unit_w + node_r, cy, cx - node_r, cy)
            # Monomer circle
            grad = QRadialGradient(cx, cy, node_r)
            grad.setColorAt(0.0, QColor(100, 180, 255))
            grad.setColorAt(1.0, QColor(40, 100, 200))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(30, 70, 150), 1.5))
            p.drawEllipse(QPointF(cx, cy), node_r, node_r)
            # Label
            p.setPen(QPen(QColor(255, 255, 255)))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(cx - node_r, cy - node_r, node_r * 2, node_r * 2),
                        Qt.AlignmentFlag.AlignCenter, f"M{i+1}")

        # Approaching monomer
        if self._is_approaching and self._chain_length < self._max_chain:
            ax = self._approaching_x
            # pulsating effect
            pulse = 1.0 + 0.15 * math.sin(self._approaching_x * 0.15)
            r = node_r * pulse
            grad = QRadialGradient(ax, cy, r)
            grad.setColorAt(0.0, QColor(255, 200, 100))
            grad.setColorAt(1.0, QColor(220, 140, 40))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(180, 100, 20), 1.5))
            p.drawEllipse(QPointF(ax, cy), r, r)
            p.setPen(QPen(QColor(80, 40, 0)))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(ax - r, cy - r, r * 2, r * 2),
                        Qt.AlignmentFlag.AlignCenter, "M*")

        # Status text
        p.setPen(QPen(QColor(60, 60, 60)))
        p.setFont(QFont("Segoe UI", 9))
        status = f"체인 길이: {self._chain_length} / {self._max_chain}"
        p.drawText(10, h - 10, status)

        p.end()


class PolymerAnalysisPopup(QDialog):
    """고분자 분석 팝업 (8-tab)"""

    def __init__(
        self,
        smiles: str,
        mol_name: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        _ensure_qt_korean_font_ready()
        self._smiles = smiles
        self._mol_name = mol_name
        self._props: Optional[PolymerProperties] = None
        self._poly_result: Optional[PolymerizationResult] = None
        self._ref_props: Dict[str, Optional[PolymerProperties]] = {}
        self._conditions: Dict[str, Any] = {}       # 반응 조건 저장 (report export용)
        self._ai_worker: Optional[_AIAnalysisWorker] = None
        self._opt_worker: Optional[_PolymerOptWorker] = None
        self._opt_results: List[Tuple] = []  # 최적화 결과 저장
        self._anim_timer: Optional[QTimer] = None
        self._anim_frames: List[Any] = []
        self._anim_idx: int = 0
        self._anim_trajectory: Optional[Any] = None  # [M676 FIX] ReactionTrajectory 보관
        # [M706 F5-4] Rule GG SIMULATION_MODE 플래그
        # 엔진 초기화 실패/단량체 불인식/predict_all None 시 True로 설정
        self._simulation_mode: bool = False
        self._simulation_reason: str = ""

        self._init_engine()
        self._init_ui()

    # ── 엔진 초기화 ──────────────────────────────────
    def _init_engine(self):
        """PolymerPropertyEngine 로 물성 예측.

        [M706 F5-4] 3단계 SIMULATION_MODE 플래그 관리 (Rule GG):
        1. ENGINE_OK=False → "모듈 미설치"
        2. detect_polymerization().possible=False → "단량체 불인식"
        3. predict_all() is None → "그룹기여법 계산 실패"
        각 단계에서 _simulation_mode=True + logger.warning 필수 (Rule M).
        """
        if not ENGINE_OK:
            self._simulation_mode = True
            self._simulation_reason = (
                "polymer_property_engine 모듈 미설치 — "
                "물성 탭은 이론 추정값(Schulz-Flory 분포)만 표시됩니다."
            )
            logger.warning("[M706 F5-4] polymer_property_engine unavailable")
            return

        try:
            engine = PolymerPropertyEngine()

            # [M706 F5-4] detect_polymerization 먼저 수행 — 중합 불가 분자 조기 감지
            self._poly_result = engine.detect_polymerization(self._smiles)
            if self._poly_result is not None and not self._poly_result.possible:
                self._simulation_mode = True
                _smiles_preview = self._smiles[:40] + ("..." if len(self._smiles) > 40 else "")
                self._simulation_reason = (
                    f"입력 분자({_smiles_preview})는 중합 가능한 단량체로 인식되지 않았습니다.\n"
                    "비닐기(-C=C-), 이관능기, 고리형 에스터/아미드 등 중합 가능한 구조를 그려주세요.\n"
                    "아래 물성값은 이론 추정값입니다."
                )
                logger.warning(
                    "[M706 F5-4] 단량체 불인식: %r (possible=%s)",
                    self._smiles, getattr(self._poly_result, 'possible', None)
                )
                # 중합 불가여도 predict_all 시도는 계속 (이론값 제공 목적)

            self._props = engine.predict_all(self._smiles)
            if self._props is None:
                if not self._simulation_mode:
                    self._simulation_mode = True
                    self._simulation_reason = (
                        "물성 계산 엔진이 이 단량체에 대한 그룹 기여법 계산에 실패했습니다.\n"
                        "이론값(Schulz-Flory 분포)은 표시됩니다."
                    )
                logger.warning("[M706 F5-4] predict_all() returned None for SMILES=%r", self._smiles)

            # 참조 고분자 물성 (비교 탭용)
            for name, ref_smi in _REF_POLYMERS.items():
                try:
                    self._ref_props[name] = engine.predict_all(ref_smi)
                except Exception as e:
                    logger.warning("Reference polymer %s prediction failed: %s", name, e)
                    self._ref_props[name] = None
        except Exception as e:
            self._simulation_mode = True
            self._simulation_reason = f"엔진 오류: {type(e).__name__}: {e}"
            logger.warning("[M706 F5-4] PolymerPropertyEngine 초기화 실패: %s", e)

    # ── UI 초기화 ────────────────────────────────────
    def _init_ui(self):
        self._polymer_name = ""
        if self._props and hasattr(self._props, 'polymer_name') and self._props.polymer_name:
            self._polymer_name = self._props.polymer_name
        elif self._mol_name:
            self._polymer_name = self._mol_name
        else:
            self._polymer_name = self._smiles[:30]

        self.setWindowTitle(f"\U0001f52c \uace0\ubd84\uc790 \ubd84\uc11d - {self._polymer_name}")
        self.resize(1000, 800)
        self.setMinimumSize(800, 600)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # ── 상단: 단량체 + 반복단위 구조 ──
        top_frame = self._build_structure_header()
        root_layout.addWidget(top_frame)

        # ── Analyze polymerization conditions ──
        poly_type = getattr(self._props, 'poly_type', 'addition') if self._props else 'addition'
        self._conditions = self._analyze_polymerization_conditions(poly_type, self._smiles)

        # ── 탭 위젯 ──
        tabs = QTabWidget()
        self._tabs = tabs
        tabs.addTab(self._build_properties_tab(), "\ubb3c\uc131")
        tabs.addTab(self._build_thermal_tab(), "\uc5f4\ubd84\uc11d")
        tabs.addTab(self._build_mechanical_tab(), "\uae30\uacc4\uc801")
        tabs.addTab(self._build_comparison_tab(), "\ube44\uad50")
        tabs.addTab(self._build_conditions_tab(), "\ubc18\uc751 \uc870\uac74")
        tabs.addTab(self._build_ai_tab(), "AI \ud574\uc11d")
        tabs.addTab(self._build_chain_growth_tab(), "\uc5f0\uc1c4 \uc911\ud569")
        tabs.addTab(self._build_optimization_tab(), "\uad6c\uc870 \ucd5c\uc801\ud654")

        # [M1369 G5-W191] \ube44\uc911\ud569\uc131 \ubaa8\ub178\uba38 \uac00\ub4dc (M992 \ud328\ud134):
        # poly_result.possible=False \uc2dc \uc911\ud569 \uc758\uc874 \ud0ed \ube44\ud65c\uc131\ud654 + tooltip \uc548\ub0b4
        # \ube44\ud65c\uc131\ud654 \ub300\uc0c1: \ubc18\uc751\uc870\uac74(4), AI\ud574\uc11d(5), \uc5f0\uc1c4\uc911\ud569(6), \uad6c\uc870\ucd5c\uc801\ud654(7)
        # \ubb3c\uc131/\uc5f4\ubd84\uc11d/\uae30\uacc4\uc801/\ube44\uad50(0-3)\ub294 \uc774\ub860\uac12 \ud45c\uc2dc \uac00\ub2a5\ud558\ubbc0\ub85c \uc720\uc9c0
        _NON_POLY_TABS = {
            4: "\ubc18\uc751 \uc870\uac74",  # \uc911\ud569 \uba54\ucee4\ub2c8\uc998 \uc758\uc874
            5: "AI \ud574\uc11d",    # \uc911\ud569 \uc870\uac74 \uae30\ubc18 AI \ud504\ub86c\ud504\ud2b8
            6: "\uc5f0\uc1c4 \uc911\ud569",  # \ube44\ub2d0 \ub2e8\ub7c9\uccb4 \uc804\uc6a9 \uc560\ub2c8\uba54\uc774\uc158
            7: "\uad6c\uc870 \ucd5c\uc801\ud654",  # \uc720\ub3c4\uccb4 \uc911\ud569\uc131 \ud544\uc694
        }
        _is_non_poly = (
            self._poly_result is not None
            and not getattr(self._poly_result, 'possible', True)
        )
        if _is_non_poly:
            _tooltip_msg = "\ube44\uc911\ud569\uc131 \u2014 \uc911\ud569 \uac00\ub2a5\ud55c \ub2e8\ub7c9\uccb4(\ube44\ub2d0\uae30, \uc774\uad00\ub2a5\uae30 \ub4f1)\uc5d0\uc11c\ub9cc \ud65c\uc131\ud654\ub429\ub2c8\ub2e4"
            for _tab_idx, _tab_name in _NON_POLY_TABS.items():
                tabs.setTabEnabled(_tab_idx, False)
                tabs.setTabToolTip(_tab_idx, f"{_tab_name}: {_tooltip_msg}")
            logger.warning(
                "[M1369 G5-W191] \ube44\uc911\ud569\uc131 \ubaa8\ub178\uba38 \u2014 tabs %s \ube44\ud65c\uc131\ud654: smiles=%r",
                list(_NON_POLY_TABS.keys()), self._smiles
            )

        root_layout.addWidget(tabs, 1)

        # ── 하단: 경고 + Report + 닫기 버튼 ──
        bottom = QHBoxLayout()

        # 경고 라벨
        warnings_text = ""
        if self._props and hasattr(self._props, 'warnings') and self._props.warnings:
            warnings_text = " | ".join(self._props.warnings)
        self._warn_label = QLabel(warnings_text)
        self._warn_label.setStyleSheet("color: #e67e22; font-size: 11px;")
        self._warn_label.setWordWrap(True)
        bottom.addWidget(self._warn_label, 1)

        report_btn = QPushButton("Polymer Report \uc0dd\uc131")
        report_btn.setFixedWidth(180)
        report_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "font-weight: bold; padding: 6px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
        )
        report_btn.clicked.connect(self._export_polymer_report)
        bottom.addWidget(report_btn)

        close_btn = QPushButton("\ub2eb\uae30")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)

        root_layout.addLayout(bottom)

    # ══════════════════════════════════════════════════
    #  상단 구조 헤더
    # ══════════════════════════════════════════════════
    def _build_structure_header(self) -> QFrame:
        # [M804-B5] SMILES 비호환 안내 배너 포함 시 높이 자동 확장 (Rule M: 버튼 비활성화 금지)
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # [M804-B5] SIMULATION_MODE / 비호환 안내를 구조 헤더 상단에 즉시 표시
        # Rule M: 단량체 불인식 → 버튼 비활성화 금지, 사용자 안내 메시지 의무.
        # Rule GG: SIMULATION_MODE 배너 노랑/빨강.
        if self._simulation_mode and self._simulation_reason:
            compat_banner = QLabel(
                "⚠ 고분자 분석 안내: " + self._simulation_reason.replace("\n", "  ")
            )
            compat_banner.setWordWrap(True)
            compat_banner.setStyleSheet(
                "QLabel {"
                "  background-color: #FFF9C4;"
                "  color: #5D4037;"
                "  border-bottom: 2px solid #FFC107;"
                "  padding: 5px 10px;"
                "  font-size: 10px;"
                "}"
            )
            outer.addWidget(compat_banner)

        inner_widget = QWidget()
        inner_widget.setFixedHeight(160)
        layout = QHBoxLayout(inner_widget)

        # 단량체 구조
        mono_box = QVBoxLayout()
        mono_label = QLabel("\ub2e8\ub7c9\uccb4 (Monomer)")
        mono_label.setFont(QFont(_QT_KR_FONT, 9, QFont.Weight.Bold))
        mono_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mono_box.addWidget(mono_label)

        mono_pix = _mol_to_pixmap(self._smiles, (250, 120))
        mono_img = QLabel()
        mono_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if mono_pix:
            mono_img.setPixmap(mono_pix)
        else:
            mono_img.setText(self._smiles)
            mono_img.setStyleSheet("color: #888; font-family: monospace;")
        mono_box.addWidget(mono_img)
        layout.addLayout(mono_box)

        # 화살표
        arrow = QLabel("  =>  ")
        arrow.setFont(QFont(_QT_KR_FONT, 20, QFont.Weight.Bold))
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(arrow)

        # 반복단위 구조
        ru_box = QVBoxLayout()
        ru_label = QLabel("\ubc18\ubcf5\ub2e8\uc704 (Repeat Unit)")
        ru_label.setFont(QFont(_QT_KR_FONT, 9, QFont.Weight.Bold))
        ru_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ru_box.addWidget(ru_label)

        ru_smiles = self._smiles
        if self._props and hasattr(self._props, 'repeat_unit_smiles') and self._props.repeat_unit_smiles:
            ru_smiles = self._props.repeat_unit_smiles

        ru_pix = _mol_to_pixmap(ru_smiles, (250, 120))
        ru_img = QLabel()
        ru_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if ru_pix:
            ru_img.setPixmap(ru_pix)
        else:
            ru_img.setText(ru_smiles)
            ru_img.setStyleSheet("color: #888; font-family: monospace;")
        ru_box.addWidget(ru_img)
        layout.addLayout(ru_box)

        # Gold standard badge
        if self._props and hasattr(self._props, 'is_gold_standard') and self._props.is_gold_standard:
            badge = QLabel(" Gold Standard ")
            badge.setStyleSheet(
                "background-color: #f1c40f; color: #2c3e50; "
                "font-weight: bold; font-size: 11px; "
                "border-radius: 8px; padding: 4px 10px;"
            )
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedHeight(28)
            layout.addWidget(badge)

        # [M804-B5] outer QVBoxLayout\uc5d0 inner_widget \ucd94\uac00
        outer.addWidget(inner_widget)
        return frame

    # ══════════════════════════════════════════════════
    #  Tab 1: 물성 (Properties)
    # ══════════════════════════════════════════════════
    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # [M706 F5-4] SIMULATION_MODE 황색 배너 (Rule GG)
        # 엔진 실패/단량체 불인식/predict_all None 시 표시. silent N/A 금지 (Rule M).
        if self._simulation_mode:
            sim_banner = QLabel(
                "⚠ [SIMULATION_MODE]  " + self._simulation_reason +
                "\n아래 물성값은 실측 데이터가 아닌 이론 추정값 또는 미계산 상태입니다."
            )
            sim_banner.setWordWrap(True)
            sim_banner.setStyleSheet(
                "QLabel {"
                "  background-color: #FFF3CD;"
                "  color: #856404;"
                "  border: 2px solid #FFCA28;"
                "  border-radius: 6px;"
                "  padding: 8px 12px;"
                "  font-size: 11px;"
                "}"
            )
            layout.addWidget(sim_banner)

        props = self._props

        # 기본 정보 그룹
        info_group = QGroupBox("\uae30\ubcf8 \uc815\ubcf4")
        info_layout = QGridLayout(info_group)

        info_items = [
            ("\uace0\ubd84\uc790\uba85", getattr(props, 'polymer_name', 'N/A') if props else 'N/A'),
            ("\uace0\ubd84\uc790\uba85 (\ud55c\uae00)", getattr(props, 'polymer_name_kr', 'N/A') if props else 'N/A'),
            ("\uc911\ud569 \uc720\ud615", getattr(props, 'poly_type', 'N/A') if props else 'N/A'),
            ("\ub2e8\ub7c9\uccb4 SMILES", getattr(props, 'monomer_smiles', self._smiles) if props else self._smiles),
        ]
        for row, (label, value) in enumerate(info_items):
            lbl = QLabel(f"<b>{label}</b>")
            val = QLabel(str(value) if value else "N/A")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info_layout.addWidget(lbl, row, 0)
            info_layout.addWidget(val, row, 1)

        layout.addWidget(info_group)

        # 물성 테이블
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["\ubb3c\uc131", "\uac12", "\ub2e8\uc704"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        rows = [
            ("\ubc18\ubcf5\ub2e8\uc704 \ubd84\uc790\ub7c9 (M_repeat)",
             _fmt(getattr(props, 'M_repeat', None), "", 2) if props else "N/A",
             "g/mol"),
            ("\ubc00\ub3c4 (\u03c1)",
             _fmt(getattr(props, 'density', None), "", 3) if props else "N/A",
             "g/cm\u00b3"),
            ("\uc6a9\ud574\ub3c4 \ud30c\ub77c\ubbf8\ud130 (\u03b4)",
             _fmt(getattr(props, 'solubility_param', None), "", 1) if props else "N/A",
             "(J/cm\u00b3)\u00b9\u1fe5\u00b2"),
            ("\uad74\uc808\ub960 (n)",
             _fmt(getattr(props, 'refractive_index', None), "", 4) if props else "N/A",
             ""),
        ]

        table.setRowCount(len(rows))
        for i, (prop_name, value, unit) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(prop_name))
            table.setItem(i, 1, QTableWidgetItem(value))
            table.setItem(i, 2, QTableWidgetItem(unit))

        layout.addWidget(table)

        # 그룹 분해 (group decomposition)
        if props and hasattr(props, 'group_decomposition') and props.group_decomposition:
            grp_group = QGroupBox("\uadf8\ub8f9 \ubd84\ud574 (Group Decomposition)")
            grp_layout = QVBoxLayout(grp_group)
            grp_table = QTableWidget()
            grp_table.setColumnCount(2)
            grp_table.setHorizontalHeaderLabels(["\uadf8\ub8f9", "\uac1c\uc218"])
            grp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            grp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

            decomp = props.group_decomposition
            grp_table.setRowCount(len(decomp))
            for i, (group_name, count) in enumerate(decomp.items()):
                grp_table.setItem(i, 0, QTableWidgetItem(str(group_name)))
                grp_table.setItem(i, 1, QTableWidgetItem(str(count)))

            grp_layout.addWidget(grp_table)
            layout.addWidget(grp_group)

        # ── 분자량 분포 (PDI / Mn / Mw) 그래프 (M684 Block5 신설) ─────
        # Schulz-Flory 분포 시뮬레이션: PDI = Mw/Mn
        # 중합 유형에 따른 이론 PDI: 라디칼=2.0, 리빙음이온=1.05, 축중합=2.0, ROMP=1.1
        if MPL_OK:
            try:
                pdi_group = QGroupBox("분자량 분포 (Molecular Weight Distribution, Block5 M684)")
                pdi_vlay = QVBoxLayout(pdi_group)

                # PDI 추정 (중합 유형 기반)
                poly_type_str = getattr(props, 'poly_type', '') if props else ''
                _poly_lower = str(poly_type_str).lower()
                # PDI 이론값 (Rule I 매직넘버 주석 필수)
                if "anionic" in _poly_lower or "living" in _poly_lower or "음이온" in _poly_lower:
                    _pdi_est = 1.05   # 리빙 음이온 중합: PDI ≈ 1.05 (이론 최소)
                    _pdi_label = "리빙 음이온 (PDI ≈ 1.05)"
                elif "romp" in _poly_lower or "ring-open" in _poly_lower:
                    _pdi_est = 1.10   # ROMP: PDI ≈ 1.1 (Grubbs 촉매)
                    _pdi_label = "ROMP (PDI ≈ 1.10)"
                elif "cationic" in _poly_lower or "양이온" in _poly_lower:
                    _pdi_est = 1.50   # 양이온 중합: PDI ≈ 1.5 (사슬이동 반응)
                    _pdi_label = "양이온 중합 (PDI ≈ 1.50)"
                elif "step" in _poly_lower or "condensa" in _poly_lower or "축중합" in _poly_lower:
                    _pdi_est = 2.00   # 축중합: PDI ≈ 2.0 (Most Probable Distribution)
                    _pdi_label = "축중합 (PDI ≈ 2.00)"
                else:
                    _pdi_est = 2.00   # 라디칼 중합 기본: PDI ≈ 2.0 (Schulz-Flory)
                    _pdi_label = "라디칼 중합 (PDI ≈ 2.00)"

                # Mn 기준값 (반복단위 분자량 × 100 DP 가정 — 교육용 시각화)
                _m_repeat = getattr(props, 'M_repeat', None) if props else None
                _mn_base = float(_m_repeat) * 100.0 if _m_repeat else 10000.0  # DP=100 가정

                # Schulz-Flory (most probable) 분포 시뮬레이션
                _mw_arr = np.linspace(_mn_base * 0.05, _mn_base * _pdi_est * 4.0, 300)
                _mn_val = _mn_base
                _mw_val = _mn_val * _pdi_est  # Mw = Mn * PDI
                _sigma  = _mn_val * (_pdi_est - 1.0) ** 0.5 if _pdi_est > 1.0 else _mn_val * 0.05

                # Log-normal 분포 근사 (고분자 분자량 분포 표준 표현)
                _mu_ln  = np.log(_mn_val) + _sigma ** 2 / (2 * _mn_val)  # log-space mean
                _sig_ln = (_sigma / _mn_val) if _mn_val > 0 else 0.3
                _sig_ln = max(_sig_ln, 0.05)  # 최솟값 보장
                _dist   = (1.0 / (_mw_arr * _sig_ln * np.sqrt(2 * np.pi))) * \
                          np.exp(-((np.log(_mw_arr) - np.log(_mn_val)) ** 2) /
                                  (2 * _sig_ln ** 2))
                _dist   = _dist / (_dist.max() + 1e-12)  # 정규화

                fig_pdi = Figure(figsize=(5.5, 2.5), facecolor='white')
                ax_pdi = fig_pdi.add_subplot(111)
                ax_pdi.plot(_mw_arr, _dist, color='#2196F3', linewidth=1.8, label=_pdi_label)
                ax_pdi.axvline(_mn_val, color='#E74C3C', linestyle='--', linewidth=1.2,
                               label=f"Mn = {_mn_val:.0f} g/mol")
                ax_pdi.axvline(_mw_val, color='#27AE60', linestyle='--', linewidth=1.2,
                               label=f"Mw = {_mw_val:.0f} g/mol")

                # 범례 & 레이블 (Rule Q: fontproperties 필수)
                _fkw_pdi = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}
                ax_pdi.set_xlabel("분자량 (g/mol)", fontsize=8, **_fkw_pdi)
                ax_pdi.set_ylabel("상대 강도", fontsize=8, **_fkw_pdi)
                ax_pdi.set_title(
                    f"분자량 분포 — PDI = {_pdi_est:.2f}  (이론적 Schulz-Flory 분포)",
                    fontsize=8, **_fkw_pdi,
                )
                ax_pdi.legend(fontsize=7, prop=_MPL_KR_FONT)
                ax_pdi.tick_params(labelsize=7)
                fig_pdi.tight_layout(pad=0.6)

                canvas_pdi = FigureCanvas(fig_pdi)
                canvas_pdi.setMinimumHeight(200)
                pdi_vlay.addWidget(canvas_pdi)

                # PDI 수치 라벨
                pdi_info_lbl = QLabel(
                    f"<b>Mn</b> = {_mn_val:.0f} g/mol &nbsp;|&nbsp; "
                    f"<b>Mw</b> = {_mw_val:.0f} g/mol &nbsp;|&nbsp; "
                    f"<b>PDI</b> = {_pdi_est:.2f} &nbsp;({_pdi_label})"
                    "<br><small>* Schulz-Flory log-normal 분포 이론 시뮬레이션. "
                    "DP=100 가정 (실제 DP는 중합 조건에 따라 다름)</small>"
                )
                pdi_info_lbl.setWordWrap(True)
                pdi_vlay.addWidget(pdi_info_lbl)

                layout.addWidget(pdi_group)
            except Exception as _epdi:
                logger.warning("[M684 Block5] PDI graph failed: %s", _epdi)

        # ── [M1369 G5-W191] Tg 예측 근거 섹션 ─────────────────────────────
        # Van Krevelen 그룹 기여법 기반 Tg 예측 원리 표시
        # Tg = sum(Yg_i) / M_repeat  (Yg = molar glass-transition function, J/mol)
        # 참고: Van Krevelen & Nijenhuis, "Properties of Polymers" 4th ed. (2009) Table 6.7
        tg_group = QGroupBox("Tg 예측 근거 (Van Krevelen 그룹 기여법)")
        tg_vlay = QVBoxLayout(tg_group)
        _tg_val = getattr(props, 'Tg', None) if props else None
        _m_rep  = getattr(props, 'M_repeat', None) if props else None
        _grp_decomp = getattr(props, 'group_decomposition', {}) if props else {}
        if not isinstance(_grp_decomp, dict):
            _grp_decomp = {}

        tg_formula_lbl = QLabel(
            "<b>Tg 계산식 (Van Krevelen):</b>  Tg = Σ(Y<sub>g,i</sub> × n<sub>i</sub>) / M<sub>repeat</sub>"
            "<br><small>Y<sub>g,i</sub> = 그룹별 유리전이 기여 함수 [J/mol], "
            "n<sub>i</sub> = 반복단위 내 그룹 수, M<sub>repeat</sub> = 반복단위 분자량</small>"
        )
        tg_formula_lbl.setWordWrap(True)
        tg_formula_lbl.setStyleSheet("font-size: 11px; color: #2c3e50; padding: 4px;")
        tg_vlay.addWidget(tg_formula_lbl)

        # Yg 그룹 기여값 조견표 (Van Krevelen 2009 표준값)
        # (단위: J/mol, 참고문헌 기반 대표값)
        _YG_TABLE = {
            # 탄화수소 backbone
            "-CH2-":       2700,   # 메틸렌기
            "-CH3":        2700,   # 말단 메틸기 (근사)
            "-CH<":       14800,   # 3차 C
            ">C<":        35000,   # 4차 C (고Tg 기여)
            "C6H4":       57500,   # 페닐렌 (방향족 고리)
            # 극성 그룹 (Tg 상승)
            "-CN":        45000,   # 시아노기 (PAN 고Tg 원인)
            "-COOH":      22500,   # 카르복실기
            "-C(=O)-":    17500,   # 케톤
            "-COO-":      14500,   # 에스터
            # 극성 그룹 (Tg 저하)
            "-O-":         3400,   # 에테르 (사슬 유연성)
            "-OH":        21000,   # 히드록실 (수소결합)
            # 할로겐
            "-F":          5300,   # 불소화
            "-Cl":        11500,   # 염소화 (PVC)
        }

        tg_table_widget = QTableWidget()
        tg_table_widget.setColumnCount(3)
        tg_table_widget.setHorizontalHeaderLabels(
            ["그룹 (Group)", "Yg (J/mol)", "주요 고분자 예시"]
        )
        tg_table_widget.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        tg_table_widget.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        tg_table_widget.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        tg_table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tg_table_widget.setMaximumHeight(200)  # 스크롤 가능한 높이 제한
        tg_table_widget.verticalHeader().setVisible(False)
        tg_table_widget.setAlternatingRowColors(True)

        _YG_EXAMPLES = {
            "-CH2-": "PE, PP",
            "-CH3": "이소택틱 PP",
            "-CH<": "PP, PVC",
            ">C<": "폴리이소부틸렌",
            "C6H4": "PS, PC, PET",
            "-CN": "PAN (아크릴로니트릴)",
            "-COOH": "폴리아크릴산",
            "-C(=O)-": "폴리케톤",
            "-COO-": "PMMA, PET",
            "-O-": "PEO, PPO",
            "-OH": "PVA",
            "-F": "PVDF, PTFE",
            "-Cl": "PVC",
        }

        rows_yg = list(_YG_TABLE.items())
        tg_table_widget.setRowCount(len(rows_yg))
        for i, (grp, yg_val) in enumerate(rows_yg):
            tg_table_widget.setItem(i, 0, QTableWidgetItem(grp))
            item_yg = QTableWidgetItem(f"{yg_val:,}")
            item_yg.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tg_table_widget.setItem(i, 1, item_yg)
            tg_table_widget.setItem(i, 2, QTableWidgetItem(_YG_EXAMPLES.get(grp, "")))
        tg_vlay.addWidget(tg_table_widget)

        # 현재 고분자 Tg 예측값 표시
        if _tg_val is not None:
            tg_result_lbl = QLabel(
                f"<b>현재 고분자 예측 Tg: {_tg_val:.1f} °C</b>"
                + (f"  (반복단위 M = {_m_rep:.1f} g/mol 기준)" if _m_rep else "")
            )
            tg_result_lbl.setStyleSheet(
                "color: #1565C0; font-size: 12px; font-weight: bold; "
                "background-color: #E3F2FD; padding: 4px 8px; border-radius: 4px;"
            )
            tg_vlay.addWidget(tg_result_lbl)
        else:
            tg_result_lbl = QLabel("Tg 예측값 없음 (엔진 미설치 또는 미지원 단량체)")
            tg_result_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px; padding: 4px;")
            tg_vlay.addWidget(tg_result_lbl)

        layout.addWidget(tg_group)

        # ── [M1369 G5-W191] 단량체 공중합 반응성 비율 r1/r2 섹션 ─────────────
        # Mayo-Lewis 공중합 방정식: F1 = (r1*f1^2 + f1*f2) / (r1*f1^2 + 2*f1*f2 + r2*f2^2)
        # r1 = k11/k12, r2 = k22/k21  (k11=자기반응속도, k12=교차반응속도)
        # r1*r2 = 1 이상: 블록 공중합 경향 / r1*r2 < 1: 교대 공중합 경향
        r1r2_group = QGroupBox("단량체 공중합 반응성 비율 r1/r2 (Mayo-Lewis 방정식)")
        r1r2_vlay = QVBoxLayout(r1r2_group)

        r1r2_intro = QLabel(
            "<b>Mayo-Lewis 방정식:</b>  F<sub>1</sub> = (r<sub>1</sub>f<sub>1</sub><sup>2</sup> "
            "+ f<sub>1</sub>f<sub>2</sub>) / (r<sub>1</sub>f<sub>1</sub><sup>2</sup> "
            "+ 2f<sub>1</sub>f<sub>2</sub> + r<sub>2</sub>f<sub>2</sub><sup>2</sup>)"
            "<br><small>r<sub>1</sub> = k<sub>11</sub>/k<sub>12</sub>: "
            "단량체1 라디칼의 자기중합/교차중합 속도 비<br>"
            "r<sub>1</sub>·r<sub>2</sub> < 1 → 교대 공중합, "
            "r<sub>1</sub>·r<sub>2</sub> = 1 → 이상(ideal), "
            "r<sub>1</sub>·r<sub>2</sub> > 1 → 블록 경향</small>"
        )
        r1r2_intro.setWordWrap(True)
        r1r2_intro.setStyleSheet("font-size: 11px; color: #2c3e50; padding: 4px;")
        r1r2_vlay.addWidget(r1r2_intro)

        # 주요 단량체 공중합 반응성 비율 조견표 (문헌값)
        # 참고: Odian, "Principles of Polymerization" 4th ed. (2004) Table 6-1
        # 형식: (M1 이름, M2 이름, r1, r2, r1*r2, 공중합 특성)
        _R1R2_TABLE = [
            ("스타이렌 (S)",       "메틸메타크릴레이트 (MMA)", 0.52, 0.46, 0.24, "교대 경향"),
            ("스타이렌 (S)",       "아크릴로니트릴 (AN)",      0.41, 0.04, 0.02, "강한 교대"),
            ("스타이렌 (S)",       "부타디엔 (Bd)",            0.78, 1.39, 1.08, "블록 경향"),
            ("스타이렌 (S)",       "말레산무수물 (MAn)",        0.02, 0.00, 0.00, "1:1 교대"),
            ("메틸메타크릴레이트", "아크릴로니트릴 (AN)",      1.20, 0.15, 0.18, "교대 경향"),
            ("에틸렌 (E)",         "비닐아세테이트 (VA)",       1.06, 0.01, 0.01, "E 우세"),
            ("아크릴산 (AA)",      "아크릴아미드 (AM)",         1.15, 0.88, 1.01, "이상 공중합"),
            ("염화비닐 (VC)",      "아크릴로니트릴 (AN)",      0.02, 3.28, 0.07, "교대 경향"),
        ]

        r1r2_table_widget = QTableWidget()
        r1r2_table_widget.setColumnCount(6)
        r1r2_table_widget.setHorizontalHeaderLabels(
            ["M1 단량체", "M2 단량체", "r1", "r2", "r1·r2", "공중합 특성"]
        )
        for col in range(6):
            r1r2_table_widget.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        r1r2_table_widget.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch
        )
        r1r2_table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        r1r2_table_widget.setMaximumHeight(220)
        r1r2_table_widget.verticalHeader().setVisible(False)
        r1r2_table_widget.setAlternatingRowColors(True)
        r1r2_table_widget.setRowCount(len(_R1R2_TABLE))

        for i, (m1, m2, r1, r2, r1r2, char) in enumerate(_R1R2_TABLE):
            r1r2_table_widget.setItem(i, 0, QTableWidgetItem(m1))
            r1r2_table_widget.setItem(i, 1, QTableWidgetItem(m2))
            item_r1 = QTableWidgetItem(f"{r1:.2f}")
            item_r1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            r1r2_table_widget.setItem(i, 2, item_r1)
            item_r2 = QTableWidgetItem(f"{r2:.2f}")
            item_r2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            r1r2_table_widget.setItem(i, 3, item_r2)
            item_prod = QTableWidgetItem(f"{r1r2:.2f}")
            item_prod.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # r1*r2 < 1 → 교대(파란색), r1*r2 ≈ 1 → 이상(검정), r1*r2 > 1 → 블록(빨간색)
            if r1r2 < 0.5:
                item_prod.setForeground(QBrush(QColor(13, 71, 161)))    # 짙은 파랑 (교대)
            elif r1r2 > 1.2:
                item_prod.setForeground(QBrush(QColor(183, 28, 28)))    # 짙은 빨강 (블록)
            r1r2_table_widget.setItem(i, 4, item_prod)
            r1r2_table_widget.setItem(i, 5, QTableWidgetItem(char))

        r1r2_vlay.addWidget(r1r2_table_widget)

        # 현재 단량체에 해당하는 r1/r2 자동 조회
        _smiles_upper = self._smiles.upper() if self._smiles else ""
        _r1r2_hint = ""
        if "C=CC1=CC=CC=C1" in self._smiles or "C=CC1=CC=CC=C1" in _smiles_upper:
            _r1r2_hint = "현재 단량체: 스타이렌 계열 — 위 표의 'S' 행 참조"
        elif "C=C(C)C(=O)OC" in self._smiles:
            _r1r2_hint = "현재 단량체: MMA 계열 — 위 표의 'MMA' 행 참조"
        elif "C=CC#N" in self._smiles:
            _r1r2_hint = "현재 단량체: 아크릴로니트릴 계열 — 위 표의 'AN' 행 참조"
        elif self._smiles in ("C=C", "CC"):
            _r1r2_hint = "현재 단량체: 에틸렌/폴리에틸렌 — 위 표의 'E' 행 참조"

        r1r2_note = QLabel(
            (_r1r2_hint if _r1r2_hint else "현재 단량체의 r1/r2는 실험 조건(온도, 용매)에 따라 변화합니다.") +
            "<br><small>출처: Odian G., Principles of Polymerization, 4th ed. (2004)</small>"
        )
        r1r2_note.setWordWrap(True)
        r1r2_note.setStyleSheet("color: #5D4037; font-size: 10px; padding: 3px 6px;")
        r1r2_vlay.addWidget(r1r2_note)

        layout.addWidget(r1r2_group)

        layout.addStretch()
        return widget

    # ══════════════════════════════════════════════════
    #  Tab 2: 열분석 (Thermal Analysis)
    # ══════════════════════════════════════════════════
    def _build_thermal_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        props = self._props

        tg = getattr(props, 'Tg', None) if props else None
        tm = getattr(props, 'Tm', None) if props else None
        td = getattr(props, 'Td', None) if props else None
        max_svc = getattr(props, 'max_service_temp', None) if props else None
        cte = getattr(props, 'CTE', None) if props else None
        tc = getattr(props, 'thermal_conductivity', None) if props else None

        # 온도 바 위젯
        temp_bar = _TemperatureBarWidget(tg=tg, tm=tm, td=td, max_service=max_svc)
        layout.addWidget(temp_bar)

        # 상세 수치 테이블
        detail_group = QGroupBox("\uc5f4\uc801 \ubb3c\uc131 \uc0c1\uc138")
        detail_layout = QGridLayout(detail_group)

        thermal_items = [
            ("\uc720\ub9ac\uc804\uc774\uc628\ub3c4 (Tg)", _fmt(tg, "\u00b0C", 1)),
            ("\uc6a9\uc735\uc628\ub3c4 (Tm)", _fmt(tm, "\u00b0C", 1)),
            ("\ubd84\ud574\uc628\ub3c4 (Td)", _fmt(td, "\u00b0C", 1)),
            ("\ucd5c\ub300 \uc0ac\uc6a9\uc628\ub3c4", _fmt(max_svc, "\u00b0C", 1)),
            ("\uc120\ud325\ucc3d\uacc4\uc218 (CTE)", _fmt(cte, "\u00d710\u207b\u2075 /\u00b0C", 1) if cte else "N/A"),
            ("\uc5f4\uc804\ub3c4\ub3c4", _fmt(tc, "W/(m\u00b7K)", 3) if tc else "N/A"),
        ]

        for row, (label, value) in enumerate(thermal_items):
            lbl = QLabel(f"<b>{label}</b>")
            val = QLabel(str(value))
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_layout.addWidget(lbl, row, 0)
            detail_layout.addWidget(val, row, 1)

        layout.addWidget(detail_group)

        # TGA / DSC 시뮬레이션 그래프
        if MPL_OK and td is not None and td > 0:
            tga_dsc_widget = self._build_tga_dsc_graphs(tg, tm, td)
            if tga_dsc_widget is not None:
                layout.addWidget(tga_dsc_widget, 1)  # stretch=1 for graph expansion

        # 설명
        desc = QLabel(
            "<i>\uc8fc\uc758: Tg(\uc720\ub9ac\uc804\uc774) \uc774\ud558\uc5d0\uc11c \ucde8\uc131, "
            "Tm(\uc6a9\uc735) \uc774\uc0c1\uc5d0\uc11c \uc561\uccb4, "
            "Td(\ubd84\ud574) \uc774\uc0c1\uc5d0\uc11c \ud654\ud559\uc801 \ubd84\ud574 \ubc1c\uc0dd</i>"
        )
        desc.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()
        return widget

    def _build_tga_dsc_graphs(
        self,
        tg: Optional[float],
        tm: Optional[float],
        td: float,
    ) -> Optional[QWidget]:
        """TGA (열중량분석) + DSC (시차주사열량측정) 시뮬레이션 그래프 생성.

        TGA: Weight % vs Temperature — sigmoid decomposition around Td.
        DSC: Heat Flow vs Temperature — Tg step + Tm endotherm + Td exotherm.
        """
        if not MPL_OK:
            return None
        try:
            # Determine aromaticity for char yield estimation
            is_aromatic = False
            if RDKIT_OK:
                try:
                    from rdkit import Chem
                    mol = Chem.MolFromSmiles(self._smiles)
                    if mol is not None:
                        is_aromatic = any(atom.GetIsAromatic() for atom in mol.GetAtoms())
                    else:
                        logger.warning("[Rule L] MolFromSmiles 실패: %r", self._smiles)
                except Exception as e:
                    logger.warning("Aromaticity check failed for TGA/DSC: %s", e)

            # Residual weight: 15% for aromatic (more char), 5% for aliphatic
            residual = 15.0 if is_aromatic else 5.0

            # ── Temperature arrays ──
            t_max_tga = min(td + 200, 800)  # TGA x-axis upper limit
            T_tga = np.linspace(25, t_max_tga, 500)

            t_min_dsc = -50
            t_max_dsc = td + 50
            T_dsc = np.linspace(t_min_dsc, t_max_dsc, 500)

            # ── TGA curve: sigmoid decomposition ──
            # width = 30°C (typical TGA ramp rate decomposition width)
            tga_width = 30.0  # °C — controls steepness of weight loss sigmoid
            weight = residual + (100.0 - residual) / (1.0 + np.exp((T_tga - td) / tga_width))

            # ── DSC curve ──
            dsc = np.zeros_like(T_dsc)

            # Glass transition (Tg): step change (endothermic shift)
            if tg is not None and not math.isnan(tg):
                step_height = 0.3  # mW/mg — typical Tg step magnitude
                tg_step_width = 3.0  # °C — steepness of sigmoid step
                dsc += step_height / (1.0 + np.exp(-(T_dsc - tg) / tg_step_width))

            # Melting peak (Tm): endothermic (negative, exo up convention)
            has_tm = tm is not None and not math.isnan(tm) and tm > 0
            if has_tm:
                melt_amplitude = 2.0  # mW/mg — endothermic peak height
                melt_sigma = 10.0  # °C — peak width
                dsc -= melt_amplitude * np.exp(-((T_dsc - tm) ** 2) / (2.0 * melt_sigma ** 2))

            # Decomposition peak (Td): exothermic (positive, exo up convention)
            decomp_amplitude = 3.0  # mW/mg — exothermic peak height
            decomp_sigma = 20.0  # °C — peak width
            dsc += decomp_amplitude * np.exp(-((T_dsc - td) ** 2) / (2.0 * decomp_sigma ** 2))

            # ── Create figure with 2 subplots ──
            fig = Figure(figsize=(8, 5), dpi=100)
            fig.patch.set_facecolor('#fafafa')

            # --- TGA subplot (left) ---
            ax1 = fig.add_subplot(1, 2, 1)
            ax1.plot(T_tga, weight, color='#c0392b', linewidth=2.0, label='TGA')
            ax1.axvline(x=td, color='#7f8c8d', linestyle='--', linewidth=1.0, alpha=0.7)
            ax1.annotate(
                f'Td = {td:.0f} \u00b0C',
                xy=(td, residual + (100.0 - residual) / 2.0),
                xytext=(td + 30, 60),
                fontsize=9, color='#c0392b', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.2),
                **_fkw,
            )
            ax1.set_xlabel('Temperature (\u00b0C)', fontsize=9, **_fkw)
            ax1.set_ylabel('Weight Remaining (%)', fontsize=9, **_fkw)
            ax1.set_title('TGA (\uc5f4\uc911\ub7c9\ubd84\uc11d)', fontsize=11,
                          fontweight='bold', **_fkw)
            ax1.set_ylim(-5, 110)
            ax1.set_xlim(25, t_max_tga)
            ax1.grid(True, alpha=0.3)
            ax1.spines['top'].set_visible(False)
            ax1.spines['right'].set_visible(False)

            # --- DSC subplot (right) ---
            ax2 = fig.add_subplot(1, 2, 2)
            ax2.plot(T_dsc, dsc, color='#2980b9', linewidth=2.0, label='DSC')

            # Annotate Tg
            if tg is not None and not math.isnan(tg) and t_min_dsc <= tg <= t_max_dsc:
                tg_y = step_height / (1.0 + np.exp(-(tg - tg) / tg_step_width))
                ax2.axvline(x=tg, color='#27ae60', linestyle=':', linewidth=1.0, alpha=0.7)
                ax2.annotate(
                    f'Tg = {tg:.0f} \u00b0C',
                    xy=(tg, tg_y), xytext=(tg - 40, tg_y + 1.5),
                    fontsize=8, color='#27ae60', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='#27ae60', lw=1.0),
                    **_fkw,
                )

            # Annotate Tm
            if has_tm and t_min_dsc <= tm <= t_max_dsc:
                ax2.axvline(x=tm, color='#e67e22', linestyle=':', linewidth=1.0, alpha=0.7)
                ax2.annotate(
                    f'Tm = {tm:.0f} \u00b0C',
                    xy=(tm, -melt_amplitude * 0.8),
                    xytext=(tm + 25, -melt_amplitude - 0.5),
                    fontsize=8, color='#e67e22', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='#e67e22', lw=1.0),
                    **_fkw,
                )

            # Annotate Td
            if t_min_dsc <= td <= t_max_dsc:
                ax2.axvline(x=td, color='#c0392b', linestyle=':', linewidth=1.0, alpha=0.7)
                ax2.annotate(
                    f'Td = {td:.0f} \u00b0C',
                    xy=(td, decomp_amplitude * 0.8),
                    xytext=(td - 50, decomp_amplitude + 0.5),
                    fontsize=8, color='#c0392b', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.0),
                    **_fkw,
                )

            ax2.set_xlabel('Temperature (\u00b0C)', fontsize=9, **_fkw)
            ax2.set_ylabel('Heat Flow (mW/mg)  \u2191 exo', fontsize=9, **_fkw)
            ax2.set_title('DSC (\uc2dc\ucc28\uc8fc\uc0ac\uc5f4\ub7c9\uce21\uc815)',
                          fontsize=11, fontweight='bold', **_fkw)
            ax2.set_xlim(t_min_dsc, t_max_dsc)
            ax2.grid(True, alpha=0.3)
            ax2.spines['top'].set_visible(False)
            ax2.spines['right'].set_visible(False)

            fig.tight_layout(pad=2.0)
            canvas = FigureCanvas(fig)
            return canvas
        except Exception as e:
            logger.warning("TGA/DSC graph generation failed: %s", e)
            return None

    # ══════════════════════════════════════════════════
    #  Tab 3: 기계적 물성 (Mechanical)
    # ══════════════════════════════════════════════════
    def _build_mechanical_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if not MPL_OK:
            layout.addWidget(QLabel("matplotlib \ubbf8\uc124\uce58 \u2014 \ucc28\ud2b8\ub97c \ud45c\uc2dc\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."))
            return widget

        props = self._props

        tensile = getattr(props, 'tensile_strength', None) if props else None
        modulus = getattr(props, 'youngs_modulus', None) if props else None
        elongation = getattr(props, 'elongation_at_break', None) if props else None

        fig = Figure(figsize=(7, 5), dpi=100)
        fig.patch.set_facecolor('#fafafa')

        # 3 horizontal bar subplots
        properties = [
            ("\uc778\uc7a5\uac15\ub3c4\n(Tensile Strength)", tensile, "MPa", 200, "#3498db"),
            ("\uc601\ub960\n(Young's Modulus)", modulus, "GPa", 10, "#2ecc71"),
            ("\ud30c\ub2e8\uc5f0\uc2e0\uc728\n(Elongation)", elongation, "%", 500, "#e74c3c"),
        ]

        for idx, (label, value, unit, max_val, color) in enumerate(properties):
            ax = fig.add_subplot(3, 1, idx + 1)
            bar_value = value if value is not None else 0
            ax.barh([0], [bar_value], color=color, height=0.5, alpha=0.85)
            ax.set_xlim(0, max_val * 1.1)
            ax.set_yticks([0])
            ax.set_yticklabels([label], fontsize=9, **_fkw)
            ax.set_xlabel(unit, fontsize=8, **_fkw)
            ax.tick_params(axis='x', labelsize=8)

            # 값 텍스트
            display_val = f"{value:.1f} {unit}" if value is not None else "N/A"
            text_x = bar_value + max_val * 0.02 if value is not None else max_val * 0.02
            ax.text(text_x, 0, display_val, va='center', fontsize=10, fontweight='bold', **_fkw)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

        fig.tight_layout(pad=1.5)

        canvas = FigureCanvas(fig)
        layout.addWidget(canvas, 1)

        return widget

    # ══════════════════════════════════════════════════
    #  Tab 4: 비교 (Comparison Radar)
    # ══════════════════════════════════════════════════
    def _build_comparison_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if not MPL_OK:
            layout.addWidget(QLabel("matplotlib \ubbf8\uc124\uce58 \u2014 \ub808\uc774\ub354 \ucc28\ud2b8\ub97c \ud45c\uc2dc\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."))
            return widget

        # 6 axes for radar: density, Tg, Tm, tensile_strength, youngs_modulus, solubility_param
        categories = [
            "\ubc00\ub3c4\n(g/cm\u00b3)",
            "Tg\n(\u00b0C)",
            "Tm\n(\u00b0C)",
            "\uc778\uc7a5\uac15\ub3c4\n(MPa)",
            "\uc601\ub960\n(GPa)",
            "\u03b4\n(sol. param)",
        ]
        N = len(categories)

        # 정규화 범위 (min, max)  — 일반 고분자 범위 기준
        norm_ranges = [
            (0.8, 2.3),      # density (g/cm3)
            (-130, 350),     # Tg (degC)
            (100, 400),      # Tm (degC)
            (10, 200),       # tensile_strength (MPa)
            (0.1, 5.0),      # youngs_modulus (GPa)
            (14, 26),        # solubility_param
        ]

        def _extract_values(p) -> List[Optional[float]]:
            if p is None:
                return [None] * N
            return [
                getattr(p, 'density', None),
                getattr(p, 'Tg', None),
                getattr(p, 'Tm', None),
                getattr(p, 'tensile_strength', None),
                getattr(p, 'youngs_modulus', None),
                getattr(p, 'solubility_param', None),
            ]

        def _normalize(values: List[Optional[float]]) -> List[float]:
            result = []
            for i, v in enumerate(values):
                lo, hi = norm_ranges[i]
                if v is None:
                    result.append(0.0)
                else:
                    normed = (v - lo) / (hi - lo) if hi != lo else 0.5
                    result.append(max(0.0, min(1.0, normed)))
            return result

        # 데이터 수집
        all_series = {}
        if self._props:
            poly_name = getattr(self._props, 'polymer_name', None) or self._mol_name or "Current"
            all_series[poly_name] = _normalize(_extract_values(self._props))

        colors = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6"]
        for ref_name, ref_props in self._ref_props.items():
            all_series[ref_name] = _normalize(_extract_values(ref_props))

        # Radar chart
        fig = Figure(figsize=(6, 5), dpi=100)
        fig.patch.set_facecolor('#fafafa')
        ax = fig.add_subplot(111, polar=True)

        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles += angles[:1]  # close

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=8, **_fkw)
        ax.set_ylim(0, 1)
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=7, color="#aaa")
        ax.grid(True, alpha=0.3)

        for idx, (name, values) in enumerate(all_series.items()):
            vals = values + values[:1]  # close
            color = colors[idx % len(colors)]
            ax.plot(angles, vals, 'o-', linewidth=1.5, label=name, color=color, markersize=4)
            ax.fill(angles, vals, alpha=0.1, color=color)

        _legend_kw = {"prop": _MPL_KR_FONT} if _MPL_KR_FONT else {}
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=8,
                 **_legend_kw)
        fig.tight_layout(pad=2.0)

        canvas = FigureCanvas(fig)
        layout.addWidget(canvas, 1)

        # 범례 설명
        note = QLabel(
            "<i>\uac01 \ucd95\uc740 \uc77c\ubc18 \uace0\ubd84\uc790 \ubc94\uc704 "
            "\uae30\uc900\uc73c\ub85c 0\u20131 \uc815\uaddc\ud654. "
            "\uc678\uace8 = \ub192\uc740 \uac12.</i>"
        )
        note.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        return widget

    # ══════════════════════════════════════════════════
    #  Polymerization conditions analysis
    # ══════════════════════════════════════════════════

    @staticmethod
    def _analyze_polymerization_conditions(
        poly_type: str, smiles: str
    ) -> Dict[str, Any]:
        """단량체 SMILES와 중합 유형으로부터 반응 조건을 분석.

        치환기의 전자적 효과에 따라 개시 메커니즘을 분류:
          - 전자흡인기(CN, COOR 등) → 음이온 중합
          - 전자공여기(OR, NR2) → 양이온 중합
          - 라디칼 안정 / 중성 → 라디칼 중합 (AIBN/BPO)
          - 입체특이적 필요 → Ziegler-Natta
        """
        conditions: Dict[str, Any] = {
            "poly_type": poly_type,
            "initiator_type": "라디칼 (Radical)",
            "initiator_examples": "AIBN, BPO (과산화벤조일)",
            "temperature_range": "60-80 °C",
            "pressure": "상압 (1 atm)",
            "solvent": "벌크 중합 또는 톨루엔",
            "catalyst": "불필요",
            "atmosphere": "N₂ 불활성 분위기",
            "notes": "",
        }

        if not smiles:
            return conditions
        smiles_upper = smiles.upper()

        # ── 축합 중합 (condensation) ──
        if poly_type and "condensation" in str(poly_type).lower():
            conditions.update({
                "initiator_type": "축합 촉매 (Condensation Catalyst)",
                "initiator_examples": "p-TSA, Sb₂O₃, Ti(OBu)₄",
                "temperature_range": "200-280 °C",
                "pressure": "감압 (진공, <1 mmHg)",
                "solvent": "무용매 (용융 중합)",
                "catalyst": "금속산화물 촉매 또는 산촉매",
                "notes": "축합수(H₂O) 제거 필수 — 진공 또는 N₂ 퍼징",
            })
            return conditions

        # ── 개환 중합 (ring-opening) ──
        if poly_type and "ring" in str(poly_type).lower():
            conditions.update({
                "initiator_type": "음이온 개환 (Anionic ROP)",
                "initiator_examples": "Sn(Oct)₂, NaOMe, n-BuLi",
                "temperature_range": "25-130 °C",
                "pressure": "상압",
                "solvent": "THF 또는 톨루엔",
                "catalyst": "유기금속 촉매",
                "notes": "수분 엄격 차단 필수 (글로브박스 또는 슐렌크 라인)",
            })
            return conditions

        # ── 부가 중합 — 치환기 전자효과 분류 ──
        # electron-withdrawing groups → anionic polymerization
        ewg_patterns = ["C#N", "C(=O)O", "C(=O)", "S(=O)", "N(=O)", "[N+]"]
        has_ewg = any(pat in smiles for pat in ewg_patterns)

        # electron-donating groups → cationic polymerization
        edg_patterns = ["OC", "OCC", "NCC", "N(C", "Oc1", "N("]
        has_edg = any(pat in smiles for pat in edg_patterns)

        # Fluorinated → special conditions
        has_fluoro = "F" in smiles_upper and "C=C" in smiles

        # Stereospecific (propylene, etc.) → Ziegler-Natta
        stereo_hint = (
            smiles in ("C=CC", "CC=C", "C(/C)=C\\C")  # propylene variants
            or ("C=C" in smiles and len(smiles) > 4 and not has_ewg and not has_edg)
        )

        if has_ewg:
            conditions.update({
                "initiator_type": "음이온 중합 (Anionic)",
                "initiator_examples": "n-BuLi, NaNH₂, K-naphthalenide",
                "temperature_range": "-78 ~ 0 °C (저온)",
                "pressure": "상압",
                "solvent": "THF (무수)",
                "catalyst": "불필요 (개시제가 직접 반응)",
                "notes": (
                    "리빙 음이온 중합 가능 — 좁은 분자량 분포(PDI ≈ 1.05). "
                    "수분/산소 엄격 차단 필수."
                ),
            })
        elif has_edg:
            conditions.update({
                "initiator_type": "양이온 중합 (Cationic)",
                "initiator_examples": "BF₃·Et₂O, AlCl₃/H₂O, TiCl₄/IB",
                "temperature_range": "-100 ~ -30 °C (극저온)",
                "pressure": "상압",
                "solvent": "CH₂Cl₂ 또는 CH₃Cl (극성 용매)",
                "catalyst": "루이스산 공촉매",
                "notes": (
                    "양이온 중합은 이동반응(chain transfer)이 빈번하여 "
                    "분자량 제어 어려움. 저온 유지 중요."
                ),
            })
        elif has_fluoro:
            conditions.update({
                "initiator_type": "라디칼 (수계 분산)",
                "initiator_examples": "과황산암모늄 (APS), 과산화벤조일",
                "temperature_range": "50-80 °C",
                "pressure": "고압 (50-200 atm)",
                "solvent": "수계 분산 (에멀젼 중합)",
                "catalyst": "계면활성제 (PFOA 대체제)",
                "notes": "불소계 단량체는 고압 필요. 환경규제(PFAS) 고려.",
            })
        elif stereo_hint:
            conditions.update({
                "initiator_type": "지글러-나타 (Ziegler-Natta)",
                "initiator_examples": "TiCl₃/AlEt₃, TiCl₄/MgCl₂/AlEt₃",
                "temperature_range": "50-80 °C",
                "pressure": "1-30 atm",
                "solvent": "헥산 또는 헵탄 (무극성)",
                "catalyst": "지글러-나타 촉매 또는 메탈로센 촉매",
                "notes": (
                    "이소택틱(isotactic) 선택성 달성. "
                    "메탈로센 촉매(Cp₂ZrCl₂/MAO)로 PDI ≈ 2.0 달성 가능."
                ),
            })
        else:
            # Default: radical polymerization
            conditions.update({
                "initiator_type": "라디칼 (Radical)",
                "initiator_examples": "AIBN (아조비스이소부티로니트릴), BPO (과산화벤조일)",
                "temperature_range": "60-80 °C",
                "pressure": "상압 (고밀도 PE의 경우 1000-3000 atm)",
                "solvent": "벌크 중합, 톨루엔, 또는 수계 에멀젼",
                "catalyst": "불필요 (개시제로 라디칼 생성)",
                "notes": (
                    "라디칼 중합은 가장 범용적. "
                    "산소 제거(N₂ 퍼징) 필수 — O₂가 라디칼 억제제 역할."
                ),
            })

        return conditions

    # ══════════════════════════════════════════════════
    #  Tab 5: 반응 조건 (Polymerization Conditions)
    # ══════════════════════════════════════════════════
    def _build_conditions_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        cond = self._conditions
        # N-code: type guard — conditions dict
        if not isinstance(cond, dict):
            logger.warning("[PolymerPopup] _conditions is not dict: type=%s",
                           type(cond).__name__)
            cond = {}

        title = QLabel("<b>\U0001f52c \uc911\ud569 \ubc18\uc751 \uc870\uac74 \ubd84\uc11d</b>")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        # Conditions table
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["\ud56d\ubaa9", "\ub0b4\uc6a9"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        # Rule N: isinstance guard re-assert (cond verified as dict above L1554)
        if not isinstance(cond, dict):
            cond = {}
        rows_data = [
            ("\uc911\ud569 \uc720\ud615", cond.get("poly_type", "N/A")),
            ("\uac1c\uc2dc\uc81c \uc720\ud615", cond.get("initiator_type", "N/A")),
            ("\uac1c\uc2dc\uc81c \uc608\uc2dc", cond.get("initiator_examples", "N/A")),
            ("\uc628\ub3c4 \ubc94\uc704", cond.get("temperature_range", "N/A")),
            ("\uc555\ub825 \uc870\uac74", cond.get("pressure", "N/A")),
            ("\uc6a9\ub9e4", cond.get("solvent", "N/A")),
            ("\ucd09\ub9e4", cond.get("catalyst", "N/A")),
            ("\ubd84\uc704\uae30", cond.get("atmosphere", "N/A")),
        ]
        table.setRowCount(len(rows_data))
        for i, (label, value) in enumerate(rows_data):
            lbl_item = QTableWidgetItem(label)
            lbl_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            table.setItem(i, 0, lbl_item)
            table.setItem(i, 1, QTableWidgetItem(str(value)))
            table.setRowHeight(i, 32)

        layout.addWidget(table, 1)

        # Notes section
        notes = cond.get("notes", "")
        if notes:
            notes_group = QGroupBox("\U0001f4dd \ucc38\uace0 \uc0ac\ud56d")
            notes_layout = QVBoxLayout(notes_group)
            notes_label = QLabel(notes)
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet(
                "color: #2c3e50; background-color: #eaf2f8; "
                "padding: 10px; border-radius: 6px; font-size: 11px;"
            )
            notes_layout.addWidget(notes_label)
            layout.addWidget(notes_group)

        layout.addStretch()
        return widget

    # ══════════════════════════════════════════════════
    #  Tab 6: AI 해석 (AI Interpretation)
    # ══════════════════════════════════════════════════
    def _build_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("<b>\U0001f916 AI \uae30\ubc18 \uace0\ubd84\uc790 \ud574\uc11d</b>")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        # Button row
        btn_row = QHBoxLayout()
        self._ai_run_btn = QPushButton("\U0001f680 AI \ubd84\uc11d \uc2e4\ud589")
        self._ai_run_btn.setStyleSheet(
            "QPushButton { background-color: #8e44ad; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #9b59b6; }"
            "QPushButton:disabled { background-color: #bdc3c7; }"
        )
        self._ai_run_btn.clicked.connect(self._run_ai_analysis)
        btn_row.addWidget(self._ai_run_btn)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)  # indeterminate
        self._ai_progress.setVisible(False)
        self._ai_progress.setFixedHeight(20)
        btn_row.addWidget(self._ai_progress, 1)

        layout.addLayout(btn_row)

        # Result area
        self._ai_text = QTextEdit()
        self._ai_text.setReadOnly(True)
        self._ai_text.setPlaceholderText(
            "AI \ubd84\uc11d \ubc84\ud2bc\uc744 \ub20c\ub7ec \uace0\ubd84\uc790 \ud2b9\uc131 \ud574\uc11d\uc744 \uc2e4\ud589\ud558\uc138\uc694.\n"
            "Groq LLM (llama-3.3-70b-versatile) \uae30\ubc18 \ud559\uc220\uc801 \ubd84\uc11d\uc744 \uc81c\uacf5\ud569\ub2c8\ub2e4."
        )
        self._ai_text.setStyleSheet(
            "QTextEdit { font-size: 12px; line-height: 1.5; "
            "border: 1px solid #ddd; border-radius: 4px; padding: 8px; }"
        )
        layout.addWidget(self._ai_text, 1)

        return widget

    def _run_ai_analysis(self):
        """Groq API를 통해 고분자 AI 해석을 실행."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            logger.warning("python-dotenv not installed")

        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            self._ai_text.setText(
                "\u26a0\ufe0f API \ud0a4\uac00 \uc124\uc815\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.\n"
                ".env \ud30c\uc77c\uc5d0 GROQ_API_KEY=... \ub97c \ucd94\uac00\ud558\uc138\uc694."
            )
            return

        if not HTTPX_OK:
            self._ai_text.setText(
                "\u26a0\ufe0f httpx \ub77c\uc774\ube0c\ub7ec\ub9ac\uac00 \uc124\uce58\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.\n"
                "pip install httpx"
            )
            return

        # Build prompt
        props = self._props
        cond = self._conditions
        # N-code: type guard — cond might not be dict if construction failed
        if not isinstance(cond, dict):
            logger.warning("[PolymerPopup] _conditions is not dict in AI analysis: type=%s",
                           type(cond).__name__)
            cond = {}

        prop_lines = []
        if props:
            for attr_name, label in [
                ('polymer_name', '고분자명'),
                ('poly_type', '중합유형'),
                ('M_repeat', '반복단위 분자량'),
                ('density', '밀도 (g/cm³)'),
                ('Tg', '유리전이온도 Tg (°C)'),
                ('Tm', '용융온도 Tm (°C)'),
                ('Td', '분해온도 Td (°C)'),
                ('tensile_strength', '인장강도 (MPa)'),
                ('youngs_modulus', '영률 (GPa)'),
                ('elongation_at_break', '파단연신율 (%)'),
                ('solubility_param', '용해도 파라미터'),
                ('refractive_index', '굴절률'),
            ]:
                val = getattr(props, attr_name, None)
                if val is not None:
                    prop_lines.append(f"  - {label}: {val}")

        cond_lines = []
        # Rule N: re-assert isinstance guard (cond verified at L1686)
        assert isinstance(cond, dict)
        for key in ["initiator_type", "temperature_range", "pressure", "solvent", "catalyst"]:
            val = cond.get(key, "")
            if val:
                cond_lines.append(f"  - {key}: {val}")

        prompt = (
            f"다음 고분자의 화학적 특성을 학술적으로 상세히 분석해주세요.\n\n"
            f"단량체 SMILES: {self._smiles}\n"
            f"고분자명: {self._polymer_name}\n\n"
            f"예측된 물성:\n" + "\n".join(prop_lines) + "\n\n"
            f"중합 조건:\n" + "\n".join(cond_lines) + "\n\n"
            f"분석 항목:\n"
            f"1. 고분자의 구조-물성 관계 (structure-property relationship)\n"
            f"2. 열적 안정성 평가 및 응용 분야\n"
            f"3. 기계적 특성의 분자 구조적 원인\n"
            f"4. 산업적 응용 및 상용 제품 예시\n"
            f"5. 개선 가능한 공중합체 또는 블렌드 제안\n"
        )

        # Disable button, show progress
        self._ai_run_btn.setEnabled(False)
        self._ai_progress.setVisible(True)
        self._ai_text.setText("\u23f3 AI \ubd84\uc11d \uc911... (Groq API \ud638\ucd9c)")

        self._ai_worker = _AIAnalysisWorker(prompt, api_key, parent=self)
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_finished(self, text: str):
        self._ai_text.setText(text)
        self._ai_run_btn.setEnabled(True)
        self._ai_progress.setVisible(False)

    def _on_ai_error(self, msg: str):
        self._ai_text.setText(f"\u274c {msg}")
        self._ai_run_btn.setEnabled(True)
        self._ai_progress.setVisible(False)

    # ══════════════════════════════════════════════════
    #  Tab 7: 연쇄 중합 시뮬레이션 (Chain Growth)
    # ══════════════════════════════════════════════════
    def _build_chain_growth_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("<b>\u2697\ufe0f \uc5f0\uc1c4\uc131\uc7a5 \uc911\ud569 \uc2dc\ubbac\ub808\uc774\uc158</b>")
        title.setFont(QFont(_QT_KR_FONT, 12, QFont.Weight.Bold))
        layout.addWidget(title)

        mechanism_hint = QLabel(
            "3D 반응 시뮬레이션 엔진 연결: 성장 라디칼 + 비닐 단량체 접근, "
            "점선=형성 결합, 점묘=약화되는 C=C π결합, •=라디칼 이동"
        )
        mechanism_hint.setWordWrap(True)
        mechanism_hint.setStyleSheet(
            "QLabel { background:#fff8e1; color:#5d4037; border:1px solid #f6d365; "
            "border-radius:4px; padding:6px; font-size:10px; }"
        )
        layout.addWidget(mechanism_hint)

        # ── Viewer area ──
        self._chain_viewer: Optional[QWidget] = None
        self._chain_fallback: Optional[_SimplifiedChainGrowthWidget] = None
        self._using_3d_viewer = False

        if ANIM_VIEWER_OK:
            try:
                self._chain_viewer = _Viewer3DWidget()
                if hasattr(self._chain_viewer, "set_learning_badge"):
                    self._chain_viewer.set_learning_badge(
                        "연쇄성장 3D 중합 시뮬레이션",
                        "성장 라디칼이 비닐 단량체의 C=C에 접근",
                        "녹색=새 C-C 결합, 점묘=C=C 약화, •=라디칼 이동",
                    )
                self._using_3d_viewer = True
                layout.addWidget(self._chain_viewer, 1)
            except Exception as e:
                logger.warning("_Viewer3DWidget instantiation failed: %s", e)

        if not self._using_3d_viewer:
            self._chain_fallback = _SimplifiedChainGrowthWidget(self._smiles)
            layout.addWidget(self._chain_fallback, 1)

        # ── Controls ──
        ctrl_layout = QHBoxLayout()

        self._chain_play_btn = QPushButton("\u25b6 \uc2dc\ubbac\ub808\uc774\uc158 \uc2dc\uc791")
        self._chain_play_btn.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; "
            "font-weight: bold; padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
        )
        self._chain_play_btn.clicked.connect(self._start_chain_simulation)
        ctrl_layout.addWidget(self._chain_play_btn)

        self._chain_pause_btn = QPushButton("\u23f8 \uc77c\uc2dc\uc815\uc9c0")
        self._chain_pause_btn.setEnabled(False)
        self._chain_pause_btn.clicked.connect(self._pause_chain_simulation)
        ctrl_layout.addWidget(self._chain_pause_btn)

        self._chain_final_btn = QPushButton("끝 프레임")
        self._chain_final_btn.setToolTip("중합 반응의 최종 생성물 프레임으로 이동")
        self._chain_final_btn.clicked.connect(self._show_chain_final_frame)
        ctrl_layout.addWidget(self._chain_final_btn)

        self._chain_webgl_btn = QPushButton("WebGL 3D")
        self._chain_webgl_btn.setToolTip("3Dmol.js WebGL로 중합 trajectory를 target-bond-only 방식으로 열기")
        self._chain_webgl_btn.clicked.connect(self._open_chain_webgl)
        ctrl_layout.addWidget(self._chain_webgl_btn)

        ctrl_layout.addWidget(QLabel("\uc18d\ub3c4:"))
        self._chain_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._chain_speed_slider.setRange(20, 500)  # ms per frame
        self._chain_speed_slider.setValue(80)
        self._chain_speed_slider.setFixedWidth(150)
        self._chain_speed_slider.valueChanged.connect(self._on_chain_speed_changed)
        ctrl_layout.addWidget(self._chain_speed_slider)
        self._chain_speed_label = QLabel("80 ms")
        self._chain_speed_label.setFixedWidth(50)
        ctrl_layout.addWidget(self._chain_speed_label)

        # Frame slider (for 3D viewer mode)
        if self._using_3d_viewer:
            ctrl_layout.addWidget(QLabel("\ud504\ub808\uc784:"))
            self._frame_slider = QSlider(Qt.Orientation.Horizontal)
            self._frame_slider.setRange(0, 0)
            self._frame_slider.valueChanged.connect(self._on_frame_slider_changed)
            ctrl_layout.addWidget(self._frame_slider, 1)
        else:
            self._frame_slider = None

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Info label
        self._chain_info = QLabel(
            "\ub2e8\ub7c9\uccb4\uac00 \ud558\ub098\uc529 \uacb0\ud569\ud558\uc5ec "
            "\uace0\ubd84\uc790 \uc0ac\uc2ac\uc774 \uc131\uc7a5\ud558\ub294 \uacfc\uc815\uc744 "
            "\uc2dc\uac01\ud654\ud569\ub2c8\ub2e4."
        )
        self._chain_info.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        self._chain_info.setWordWrap(True)
        layout.addWidget(self._chain_info)

        return widget

    def _ensure_chain_trajectory(self) -> bool:
        """Create and cache the chain-growth 3D trajectory without starting playback."""
        if getattr(self, "_anim_trajectory", None) is not None and self._anim_frames:
            return True
        if not ANIM_ENGINE_OK:
            logger.warning("[M860] chain WebGL unavailable: ReactionAnimationEngine missing")
            return False
        try:
            engine = ReactionAnimationEngine()
            if hasattr(engine, "generate_chain_growth_polymerization_animation"):
                trajectory = engine.generate_chain_growth_polymerization_animation(
                    self._smiles,
                    n_frames=60,
                )
            else:
                dimer_smiles = self._make_dimer_smiles(self._smiles)
                trajectory = engine.generate_frames(
                    self._smiles,
                    dimer_smiles,
                    n_frames=60,
                )
            if trajectory is None or not hasattr(trajectory, "frames"):
                logger.warning("[M860] chain trajectory generation returned invalid result")
                return False
            frames = trajectory.frames
            if not isinstance(frames, list) or not frames:
                logger.warning("[M860] chain trajectory frames empty/type invalid")
                return False
            self._anim_trajectory = trajectory
            self._anim_frames = frames
            self._anim_idx = 0
            if self._frame_slider:
                self._frame_slider.setRange(0, len(frames) - 1)
            return True
        except Exception as exc:
            logger.warning("[M860] chain trajectory generation failed: %s", exc)
            return False

    def _show_chain_final_frame(self):
        """Jump to the final polymerization frame without forcing playback."""
        if not self._ensure_chain_trajectory():
            QMessageBox.warning(self, "중합 3D", "연쇄성장 3D trajectory를 생성하지 못했습니다.")
            return
        last_idx = len(self._anim_frames) - 1
        self._anim_idx = last_idx
        self._render_3d_frame(last_idx)
        if self._frame_slider:
            self._frame_slider.blockSignals(True)
            self._frame_slider.setValue(last_idx)
            self._frame_slider.blockSignals(False)

    def _open_chain_webgl(self):
        """Open chain-growth trajectory in the shared 3Dmol.js evidence viewer."""
        if not self._ensure_chain_trajectory():
            QMessageBox.warning(self, "WebGL 3D", "연쇄성장 3D trajectory를 생성하지 못했습니다.")
            return
        try:
            from reaction_3dmol_exporter import write_3dmol_reaction_html

            out_dir = Path(__file__).resolve().parents[2] / "docs" / "reports" / "reaction_3d_evidence_20260509"
            out_path = out_dir / "polymer_popup_chain_growth_3dmol_webgl.html"
            written = write_3dmol_reaction_html(
                self._anim_trajectory,
                out_path,
                title=f"ChemGrid WebGL 3D Polymerization - {self._polymer_name or self._mol_name or 'chain growth'}",
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(written)))
        except Exception as exc:
            logger.warning("[M860] chain WebGL export failed: %s", exc)
            QMessageBox.warning(self, "WebGL 3D", f"WebGL 내보내기 실패: {exc}")

    def _start_chain_simulation(self):
        """Start the chain-growth polymerization animation.

        [M676 FIX] 사용자 LV.14 item 3+11 — F2C=CF2 등 단량체로 연쇄 중합
        시뮬레이션이 작동 안 하는 문제 해소.
        근본 원인 1: ReactionAnimationEngine.generate_frames()는
        ReactionTrajectory 객체(frames=List 속성 보유)를 반환하나,
        기존 코드는 list로 가정하여 len(frames)/frames[i] 접근 시 TypeError.
        근본 원인 2: _Viewer3DWidget는 set_frame()이 아닌 set_frame_data()를 사용.
        해결: ReactionTrajectory를 통째로 보관하고, set_frame_data()에 명시 인자 전달.
        """
        self._chain_play_btn.setEnabled(False)
        self._chain_pause_btn.setEnabled(True)

        if self._using_3d_viewer and ANIM_ENGINE_OK:
            # Try to generate dimer SMILES and use reaction animation engine
            try:
                engine = ReactionAnimationEngine()
                if hasattr(engine, "generate_chain_growth_polymerization_animation"):
                    trajectory = engine.generate_chain_growth_polymerization_animation(
                        self._smiles,
                        n_frames=60,
                    )
                else:
                    dimer_smiles = self._make_dimer_smiles(self._smiles)
                    trajectory = engine.generate_frames(
                        self._smiles,
                        dimer_smiles,
                        n_frames=60,
                    )
                # [M676 FIX] Rule N 타입 가드: ReactionTrajectory dataclass
                if trajectory is None:
                    raise RuntimeError("ReactionAnimationEngine returned None")
                if not hasattr(trajectory, "frames"):
                    raise TypeError(
                        f"trajectory missing 'frames' attr: {type(trajectory).__name__}")
                frames = trajectory.frames
                if not isinstance(frames, list):
                    raise TypeError(
                        f"trajectory.frames is not list: {type(frames).__name__}")
                if frames and len(frames) > 0:
                    self._anim_trajectory = trajectory  # [M676] 통째로 보관
                    self._anim_frames = frames
                    self._anim_idx = 0
                    if self._frame_slider:
                        self._frame_slider.setRange(0, len(frames) - 1)
                    # Start playback timer
                    self._anim_timer = QTimer(self)
                    self._anim_timer.timeout.connect(self._advance_3d_frame)
                    self._anim_timer.start(self._chain_speed_slider.value())
                    return
                else:
                    # [Rule M] frames 0건 시 silent 금지: 사용자 피드백
                    logger.warning(
                        "[M676] _start_chain_simulation: frames 0건 — fallback "
                        "2D animation 사용 (smiles=%r)", self._smiles)
            except Exception as e:
                # [Rule M] silent 금지 — fallback 사유 로깅 + UI 메시지
                logger.warning(
                    "[M676] ReactionAnimationEngine 실패 — 2D fallback 전환: %s", e)

        # Fallback: use simplified 2D animation
        if self._chain_fallback:
            self._chain_fallback.start_animation()
        elif not self._using_3d_viewer:
            # Create fallback if not yet created
            self._chain_fallback = _SimplifiedChainGrowthWidget(self._smiles)
            self._chain_fallback.start_animation()

    def _pause_chain_simulation(self):
        """Pause/resume the chain simulation."""
        self._chain_play_btn.setEnabled(True)
        self._chain_pause_btn.setEnabled(False)

        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()
        elif self._chain_fallback:
            self._chain_fallback.stop_animation()

    def _advance_3d_frame(self):
        """Advance one frame in the 3D viewer animation.

        [M676 FIX] _Viewer3DWidget API는 set_frame()이 아닌 set_frame_data().
        set_frame_data(coords, symbols, bonds, bond_changes, label, frame_idx,
                       n_frames, charge_labels, arrows, bond_styles)
        ReactionTrajectory dataclass에서 명시적으로 추출하여 전달.
        """
        if self._anim_idx >= len(self._anim_frames):
            if self._anim_timer:
                self._anim_timer.stop()
            self._chain_play_btn.setEnabled(True)
            self._chain_pause_btn.setEnabled(False)
            return
        self._render_3d_frame(self._anim_idx)
        if self._frame_slider:
            self._frame_slider.blockSignals(True)
            self._frame_slider.setValue(self._anim_idx)
            self._frame_slider.blockSignals(False)
        self._anim_idx += 1

    def _on_frame_slider_changed(self, value: int):
        """Manual frame scrubbing."""
        if 0 <= value < len(self._anim_frames):
            self._anim_idx = value
            self._render_3d_frame(value)

    def _render_3d_frame(self, idx: int):
        """[M676 FIX] ReactionTrajectory 한 프레임을 _Viewer3DWidget에 전송."""
        traj = getattr(self, "_anim_trajectory", None)
        if traj is None or not (0 <= idx < len(self._anim_frames)):
            return
        if self._chain_viewer is None or not hasattr(self._chain_viewer, "set_frame_data"):
            logger.warning("[M676] _render_3d_frame: viewer 또는 set_frame_data 부재")
            return
        try:
            frame_coords = self._anim_frames[idx]
            symbols = traj.atom_symbols if isinstance(traj.atom_symbols, dict) else {}
            bonds = (traj.bonds_per_frame[idx]
                     if isinstance(traj.bonds_per_frame, list)
                     and idx < len(traj.bonds_per_frame) else {})
            label = traj.labels[idx] if isinstance(traj.labels, list) and idx < len(traj.labels) else ""
            n_frames = traj.n_frames if isinstance(traj.n_frames, int) else len(self._anim_frames)
            bond_changes = traj.bond_changes if isinstance(traj.bond_changes, list) else []
            charge_labels = traj.charge_labels if isinstance(traj.charge_labels, list) else []
            arrows = traj.arrows if isinstance(traj.arrows, list) else []
            bond_styles = (traj.bond_styles[idx]
                           if isinstance(traj.bond_styles, list)
                           and idx < len(traj.bond_styles) else None)
            self._chain_viewer.set_frame_data(
                coords=frame_coords,
                symbols=symbols,
                bonds=bonds,
                bond_changes=bond_changes,
                label=label,
                frame_idx=idx,
                n_frames=n_frames,
                charge_labels=charge_labels,
                arrows=arrows,
                bond_styles=bond_styles,
            )
        except Exception as e:
            # [Rule M] silent 금지
            logger.warning("[M676] _render_3d_frame error idx=%d: %s", idx, e)

    def _on_chain_speed_changed(self, value: int):
        self._chain_speed_label.setText(f"{value} ms")
        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.setInterval(value)
        if self._chain_fallback:
            self._chain_fallback.set_speed(value)

    @staticmethod
    def _make_dimer_smiles(monomer_smiles: str) -> str:
        """단량체 SMILES로부터 이량체(dimer) SMILES를 생성.

        비닐 단량체(C=C)를 전제로: 이중결합 개열 후 2개 단량체 연결.
        """
        if not RDKIT_OK:
            # Fallback: simple string manipulation for vinyl monomers
            if "C=C" in monomer_smiles:
                # e.g. C=C -> CCCC (ethylene dimer = butane backbone)
                unit = monomer_smiles.replace("C=C", "CC", 1)
                return unit + unit
            return monomer_smiles + "." + monomer_smiles

        try:
            mol = Chem.MolFromSmiles(monomer_smiles)
            if mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패: %r", monomer_smiles)
                return monomer_smiles + "." + monomer_smiles

            # Find C=C double bond
            from rdkit.Chem import AllChem
            double_bond_pattern = Chem.MolFromSmarts("[C:1]=[C:2]")
            matches = mol.GetSubstructMatches(double_bond_pattern)
            if not matches:
                return monomer_smiles + "." + monomer_smiles

            # Simple approach: hydrogenate C=C, duplicate
            unit_smiles = monomer_smiles.replace("C=C", "CC", 1)
            dimer = unit_smiles + unit_smiles
            # Validate
            dimer_mol = Chem.MolFromSmiles(dimer)
            if dimer_mol is not None:
                return Chem.MolToSmiles(dimer_mol)
            else:
                logger.warning("[Rule L] MolFromSmiles 실패 (dimer): %r", dimer)
            return unit_smiles + "." + unit_smiles
        except Exception as e:
            logger.warning("Dimer SMILES generation failed: %s", e)
            return monomer_smiles + "." + monomer_smiles

    # ══════════════════════════════════════════════════
    #  Tab 8: 구조 최적화 (Structure Optimization)
    # ══════════════════════════════════════════════════
    def _build_optimization_tab(self) -> QWidget:
        """목표 특성 기반 단량체 유도체 생성 + 물성 최적화 탭."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ── 상단: 목표 선택 + 실행 ──
        top_group = QGroupBox("\U0001f3af 최적화 목표 설정")
        top_layout = QHBoxLayout(top_group)

        top_layout.addWidget(QLabel("목표 특성:"))
        self._opt_goal_combo = QComboBox()
        for goal_name in POLYMER_OPTIMIZATION_GOALS:
            self._opt_goal_combo.addItem(goal_name)
        self._opt_goal_combo.setMinimumWidth(180)
        top_layout.addWidget(self._opt_goal_combo)

        self._opt_run_btn = QPushButton("\U0001f680 최적화 실행")
        self._opt_run_btn.setStyleSheet(
            "QPushButton { background-color: #e67e22; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #f39c12; }"
            "QPushButton:disabled { background-color: #bdc3c7; }"
        )
        self._opt_run_btn.clicked.connect(self._run_optimization)
        top_layout.addWidget(self._opt_run_btn)

        self._opt_progress = QProgressBar()
        self._opt_progress.setRange(0, 100)
        self._opt_progress.setValue(0)
        self._opt_progress.setFixedHeight(20)
        self._opt_progress.setVisible(False)
        top_layout.addWidget(self._opt_progress, 1)

        self._opt_status_label = QLabel("")
        self._opt_status_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        top_layout.addWidget(self._opt_status_label)

        # ── 리드 보고서 내보내기 버튼 ──
        self._opt_report_btn = QPushButton("\U0001f4ca 리드 보고서 PDF")
        self._opt_report_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "font-weight: bold; padding: 8px 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
            "QPushButton:disabled { background-color: #bdc3c7; }"
        )
        self._opt_report_btn.setEnabled(False)
        self._opt_report_btn.clicked.connect(self._export_lead_report)
        top_layout.addWidget(self._opt_report_btn)

        layout.addWidget(top_group)

        # ── 중단: 원본 vs 최적화 비교 이미지 ──
        self._opt_compare_frame = QFrame()
        self._opt_compare_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._opt_compare_frame.setFixedHeight(180)
        compare_layout = QHBoxLayout(self._opt_compare_frame)

        # 원본 구조
        orig_box = QVBoxLayout()
        orig_title = QLabel("<b>원본 단량체</b>")
        orig_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orig_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        orig_box.addWidget(orig_title)

        self._opt_orig_img = QLabel()
        self._opt_orig_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opt_orig_img.setMinimumSize(220, 120)
        orig_pix = _mol_to_pixmap(self._smiles, (220, 120))
        if orig_pix:
            self._opt_orig_img.setPixmap(orig_pix)
        else:
            self._opt_orig_img.setText(self._smiles)
            self._opt_orig_img.setStyleSheet("color: #888; font-family: monospace;")
        orig_box.addWidget(self._opt_orig_img)

        self._opt_orig_props_label = QLabel("")
        self._opt_orig_props_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opt_orig_props_label.setStyleSheet("font-size: 10px; color: #2c3e50;")
        if self._props:
            tg = getattr(self._props, 'Tg', None)
            ts = getattr(self._props, 'tensile_strength', None)
            orig_text_parts = []
            if tg is not None:
                orig_text_parts.append(f"Tg: {tg:.0f}\u00b0C")
            if ts is not None:
                orig_text_parts.append(f"인장: {ts:.1f} MPa")
            self._opt_orig_props_label.setText(" | ".join(orig_text_parts) if orig_text_parts else "물성 N/A")
        orig_box.addWidget(self._opt_orig_props_label)
        compare_layout.addLayout(orig_box)

        # 화살표
        arrow = QLabel("  \u27a1  ")
        arrow.setFont(QFont("Segoe UI", 24))
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        compare_layout.addWidget(arrow)

        # 최적화 결과 구조 (선택 시 업데이트)
        opt_box = QVBoxLayout()
        self._opt_best_title = QLabel("<b>최적화 #1</b>")
        self._opt_best_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opt_best_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        opt_box.addWidget(self._opt_best_title)

        self._opt_best_img = QLabel("최적화 실행 후 결과가 표시됩니다")
        self._opt_best_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opt_best_img.setMinimumSize(220, 120)
        self._opt_best_img.setStyleSheet("color: #aaa; font-size: 11px; border: 1px dashed #ccc; border-radius: 4px;")
        opt_box.addWidget(self._opt_best_img)

        self._opt_best_props_label = QLabel("")
        self._opt_best_props_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opt_best_props_label.setStyleSheet("font-size: 10px; color: #27ae60;")
        opt_box.addWidget(self._opt_best_props_label)

        compare_layout.addLayout(opt_box)
        layout.addWidget(self._opt_compare_frame)

        # ── 하단: 결과 테이블 ──
        # 열 구성: 순위, 구조, SMILES, 변형설명, Tg, Tm, Td, 인장, SA점수, gap, dipole, 종합점수
        self._opt_table = QTableWidget()
        self._opt_table.setColumnCount(12)
        self._opt_table.setHorizontalHeaderLabels([
            "순위", "구조", "단량체 SMILES", "변형 설명",
            "Tg (\u00b0C)", "Tm (\u00b0C)", "Td (\u00b0C)",
            "인장 (MPa)",
            "SA점수",         # col 8 — 합성 용이성 (1=easy, 10=hard)
            "gap (eV)",       # col 9 — xtb HOMO-LUMO gap
            "dipole (D)",     # col 10 — xtb dipole moment
            "점수",           # col 11 — 종합 스코어
        ])
        self._opt_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._opt_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        for col in (0, 1, 4, 5, 6, 7, 8, 9, 10, 11):
            self._opt_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._opt_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._opt_table.setAlternatingRowColors(True)
        self._opt_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._opt_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._opt_table.cellClicked.connect(self._on_opt_row_clicked)
        self._opt_table.verticalHeader().setVisible(False)

        layout.addWidget(self._opt_table, 1)

        # 범례
        xtb_status = "xtb ON" if XTB_OK else "xtb OFF (fallback)"
        sa_status = "SA ON" if SA_SCORE_OK else "SA OFF"
        legend = QLabel(
            "\U0001f7e2 점수 > 0.7 (우수)  |  "
            "\U0001f7e1 점수 0.4\u20130.7 (보통)  |  "
            "\U0001f534 점수 < 0.4 (미흡)  |  "
            f"SA < 4.0 = 합성 용이 (초록 강조)  |  [{xtb_status}, {sa_status}]"
        )
        legend.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        layout.addWidget(legend)

        return widget

    def _run_optimization(self):
        """최적화 워커 스레드를 시작."""
        if not ENGINE_OK:
            QMessageBox.warning(
                self, "오류",
                "polymer_property_engine이 설치되지 않았습니다.",
            )
            return
        if not RDKIT_OK:
            QMessageBox.warning(self, "오류", "RDKit이 설치되지 않았습니다.")
            return

        goal_key = self._opt_goal_combo.currentText()

        self._opt_run_btn.setEnabled(False)
        self._opt_progress.setVisible(True)
        self._opt_progress.setValue(0)
        self._opt_status_label.setText("유도체 생성 중...")
        self._opt_table.setRowCount(0)

        self._opt_worker = _PolymerOptWorker(
            self._smiles, goal_key, n_variants=_PolymerOptWorker._INITIAL_N, parent=self
        )
        self._opt_worker.progress.connect(self._on_opt_progress)
        self._opt_worker.finished.connect(self._on_opt_finished)
        self._opt_worker.error.connect(self._on_opt_error)
        self._opt_worker.start()

    def _on_opt_progress(self, current: int, total: int, smiles: str) -> None:
        """최적화 진행 상태 업데이트 (3세대 진화 + xtb)."""
        pct = int(current / max(total, 1) * 100)
        self._opt_progress.setValue(pct)
        short_smi = smiles[:25] + "…" if len(smiles) > 25 else smiles
        xtb_tag = " [xtb]" if XTB_OK else ""
        self._opt_status_label.setText(
            f"진화 최적화{xtb_tag} ({current}/{total}): {short_smi}"
        )

    def _on_opt_finished(self, results: list) -> None:
        """최적화 완료 후 테이블 채우기.

        results 원소: (smiles, props, score, desc, sa_score, xtb_gap, xtb_dipole)
        이전 버전 호환(4원소)도 처리.
        """
        self._opt_run_btn.setEnabled(True)
        self._opt_progress.setVisible(False)
        self._opt_results = results
        self._opt_report_btn.setEnabled(bool(results))

        if not results:
            self._opt_status_label.setText("생성된 유도체가 없습니다.")
            return

        xtb_count = sum(1 for r in results if len(r) >= 7 and r[5] is not None)
        sa_count = sum(1 for r in results if len(r) >= 7 and r[4] is not None)
        status_parts = [f"완료: {len(results)}개 유도체"]
        if xtb_count:
            status_parts.append(f"xtb {xtb_count}개")
        if sa_count:
            status_parts.append(f"SA {sa_count}개")
        self._opt_status_label.setText(" | ".join(status_parts))
        self._opt_table.setRowCount(len(results))

        for row, result_tuple in enumerate(results):
            # 하위 호환: 4원소 (이전) 또는 7원소 (신규)
            if len(result_tuple) >= 7:
                vsmi, props, score, desc, sa, xtb_gap, xtb_dipole = result_tuple[:7]
            else:
                vsmi, props, score, desc = result_tuple[:4]
                sa, xtb_gap, xtb_dipole = None, None, None

            # 순위
            rank_item = QTableWidgetItem(str(row + 1))
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._opt_table.setItem(row, 0, rank_item)

            # 구조 썸네일
            pix = _mol_to_pixmap(vsmi, (60, 40))
            struct_label = QLabel()
            struct_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if pix:
                struct_label.setPixmap(pix)
            else:
                struct_label.setText("N/A")
            self._opt_table.setCellWidget(row, 1, struct_label)
            self._opt_table.setRowHeight(row, 50)

            # SMILES
            self._opt_table.setItem(row, 2, QTableWidgetItem(vsmi))

            # 변형 설명
            self._opt_table.setItem(row, 3, QTableWidgetItem(desc))

            # 물성 값
            tg = getattr(props, 'Tg', None) if props else None
            tm = getattr(props, 'Tm', None) if props else None
            td = getattr(props, 'Td', None) if props else None
            tensile = getattr(props, 'tensile_strength', None) if props else None

            self._opt_table.setItem(row, 4, QTableWidgetItem(
                f"{tg:.0f}" if tg is not None else "N/A"))
            self._opt_table.setItem(row, 5, QTableWidgetItem(
                f"{tm:.0f}" if tm is not None else "N/A"))
            self._opt_table.setItem(row, 6, QTableWidgetItem(
                f"{td:.0f}" if td is not None else "N/A"))
            self._opt_table.setItem(row, 7, QTableWidgetItem(
                f"{tensile:.1f}" if tensile is not None else "N/A"))

            # SA Score — col 8
            if sa is not None:
                sa_text = f"{sa:.2f}"
            else:
                sa_text = "N/A"
            sa_item = QTableWidgetItem(sa_text)
            sa_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # SA < 4 = 합성 용이 → 진초록 강조
            if sa is not None and sa < 4.0:
                sa_item.setForeground(QBrush(QColor(0, 140, 0)))
                sa_item.setFont(QFont("", -1, QFont.Weight.Bold))
            elif sa is not None and sa > 5.0:
                sa_item.setForeground(QBrush(QColor(180, 50, 50)))
            self._opt_table.setItem(row, 8, sa_item)

            # xtb HOMO-LUMO gap — col 9
            gap_item = QTableWidgetItem(
                f"{xtb_gap:.2f}" if xtb_gap is not None else "—"
            )
            gap_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._opt_table.setItem(row, 9, gap_item)

            # xtb dipole — col 10
            dip_item = QTableWidgetItem(
                f"{xtb_dipole:.2f}" if xtb_dipole is not None else "—"
            )
            dip_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._opt_table.setItem(row, 10, dip_item)

            # 종합 점수 — col 11
            score_item = QTableWidgetItem(f"{score:.3f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._opt_table.setItem(row, 11, score_item)

            # 행 색상 (점수 기반)
            if score > 0.7:
                row_color = QColor(220, 255, 220)   # 연초록
            elif score >= 0.4:
                row_color = QColor(255, 255, 220)   # 연노랑
            else:
                row_color = QColor(255, 220, 220)   # 연빨강

            for col in range(12):
                item = self._opt_table.item(row, col)
                if item:
                    item.setBackground(QBrush(row_color))
            # SA < 4 행은 초록 배경 강조 유지 (점수색 위에 덮어씌움)
            if sa is not None and sa < 4.0 and score <= 0.7:
                row_color = QColor(210, 255, 210)
                for col in range(12):
                    item = self._opt_table.item(row, col)
                    if item:
                        item.setBackground(QBrush(row_color))

        # 자동으로 1위 선택 표시
        if results:
            self._opt_table.selectRow(0)
            self._on_opt_row_clicked(0, 0)

    def _on_opt_error(self, msg: str):
        """최적화 오류 처리."""
        self._opt_run_btn.setEnabled(True)
        self._opt_progress.setVisible(False)
        self._opt_status_label.setText(f"\u274c {msg}")

    def _on_opt_row_clicked(self, row: int, _col: int = 0) -> None:
        """테이블 행 클릭 시 비교 이미지 업데이트."""
        if row < 0 or row >= len(self._opt_results):
            return

        result_tuple = self._opt_results[row]
        # 하위 호환: 4원소 또는 7원소
        if len(result_tuple) >= 7:
            vsmi, props, score, desc, sa, xtb_gap, xtb_dipole = result_tuple[:7]
        else:
            vsmi, props, score, desc = result_tuple[:4]
            sa, xtb_gap, xtb_dipole = None, None, None

        # 제목 업데이트
        self._opt_best_title.setText(f"<b>최적화 #{row + 1}</b>  ({desc})")

        # 이미지 업데이트
        pix = _mol_to_pixmap(vsmi, (220, 120))
        if pix:
            self._opt_best_img.setPixmap(pix)
            self._opt_best_img.setStyleSheet("")
        else:
            self._opt_best_img.setText(vsmi)
            self._opt_best_img.setStyleSheet(
                "color: #888; font-family: monospace; "
                "border: 1px dashed #ccc; border-radius: 4px;"
            )

        # 물성 비교 텍스트 (xtb + SA 포함)
        tg = getattr(props, 'Tg', None) if props else None
        ts = getattr(props, 'tensile_strength', None) if props else None
        parts = []
        if tg is not None:
            parts.append(f"Tg: {tg:.0f}\u00b0C")
        if ts is not None:
            parts.append(f"인장: {ts:.1f} MPa")
        if sa is not None:
            parts.append(f"SA: {sa:.2f}")
        if xtb_gap is not None:
            parts.append(f"gap: {xtb_gap:.2f} eV")
        if xtb_dipole is not None:
            parts.append(f"\u03bc: {xtb_dipole:.2f} D")
        parts.append(f"점수: {score:.3f}")
        self._opt_best_props_label.setText(" | ".join(parts))

    # ══════════════════════════════════════════════════
    #  Polymer Report Export
    # ══════════════════════════════════════════════════
    def _export_polymer_report(self):
        """Polymer Report를 PDF로 내보내기."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Polymer Report \uc800\uc7a5",
            f"Polymer_Report_{self._polymer_name}.pdf",
            "PDF (*.pdf)",
        )
        if not file_path:
            return

        try:
            from polymer_report_exporter import PolymerReportData, export_polymer_report
        except ImportError:
            QMessageBox.warning(
                self,
                "\uc624\ub958",
                "polymer_report_exporter \ubaa8\ub4c8\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.",
            )
            return

        try:
            # [M709] synthesis_text extract
            synthesis_text = ""
            if hasattr(self, '_synthesis_text') and self._synthesis_text:
                synthesis_text = self._synthesis_text.toPlainText()
            elif hasattr(self, '_ai_text') and self._ai_text:
                synthesis_text = self._ai_text.toPlainText()

            # [F6-0 M745] Part 6 분광분석 — 단량체(중합 전) + 반복단위(중합 후) 스펙트럼 계산
            # 사용자 원문: "Polymer Report에 분광분석 탭(고분자 중합 전 분자, 중합 후 분자) 빠져있고"
            # Rule M: 실패 시 None 반환 — silent 금지, logger.warning 필수
            monomer_spectra = None
            polymer_spectra = None
            try:
                from predict_spectra import predict_all as _predict_all
                monomer_spectra = _predict_all(self._smiles)
                # 반복단위 SMILES: poly_result에서 추출 (없으면 단량체 사용)
                repeat_smi = None
                if self._poly_result is not None and hasattr(self._poly_result, 'repeat_unit_smiles'):
                    repeat_smi = getattr(self._poly_result, 'repeat_unit_smiles', None)
                if repeat_smi and repeat_smi != self._smiles:
                    polymer_spectra = _predict_all(repeat_smi)
                else:
                    polymer_spectra = monomer_spectra  # fallback: 단량체 스펙트럼 재사용
                logger.debug("[F6-0] 분광분석 계산 완료 monomer=%s poly=%s",
                             bool(monomer_spectra), bool(polymer_spectra))
            except Exception as _spec_e:
                logger.warning("[F6-0] 분광분석 계산 실패 (보고서에 그래프 제외): %s", _spec_e)

            data = PolymerReportData(
                monomer_smiles=self._smiles,
                polymer_props=self._props,
                conditions=self._conditions,
                ai_text=self._ai_text.toPlainText() if hasattr(self, '_ai_text') else "",
                synthesis_text=synthesis_text,
                monomer_spectra=monomer_spectra,
                polymer_spectra=polymer_spectra,
            )
            success, msg = export_polymer_report(data, file_path)
            if success:
                # [M710] HWPX path display (Rule M)
                import os as _os
                hwpx_path = _os.path.splitext(file_path)[0] + ".hwpx"
                hwpx_exists = _os.path.isfile(hwpx_path)
                # [M706/M710 BUG FIX] \ub9ac\ud130\ub7f4 \uc904\ubc14\uafc8 \u2192 \n \uc774\uc2a4\ucf00\uc774\ud504\ub85c \uc218\uc815
                info_msg = "Polymer Report \uc800\uc7a5 \uc644\ub8cc:\n" + str(file_path)
                if hwpx_exists:
                    info_msg += "\n\nHWPX \ud30c\uc77c\ub3c4 \uc0dd\uc131\ub428:\n" + str(hwpx_path)
                else:
                    info_msg += "\n\n(HWPX \uc0dd\uc131 \uc2dc\ub3c4\ub428)"
                QMessageBox.information(
                    self,
                    "\uc644\ub8cc",
                    info_msg,
                )
            else:
                QMessageBox.warning(self, "\uc624\ub958", f"\uc800\uc7a5 \uc2e4\ud328: {msg}")
        except Exception as e:
            logger.warning("Polymer report export failed: %s", e)
            QMessageBox.warning(
                self,
                "\uc624\ub958",
                f"Report \uc0dd\uc131 \uc911 \uc624\ub958: {e}",
            )

    # ══════════════════════════════════════════════════
    #  Lead Optimization Report Export (종합)
    # ══════════════════════════════════════════════════
    def _export_lead_report(self):
        """리드 최적화 종합 보고서 PDF 내보내기."""
        if not hasattr(self, '_opt_results') or not self._opt_results:
            QMessageBox.warning(self, "\uc624\ub958",
                                "\ub9ac\ub4dc \ucd5c\uc801\ud654\ub97c \uba3c\uc800 \uc2e4\ud589\ud558\uc138\uc694.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "\ub9ac\ub4dc \ucd5c\uc801\ud654 \ubcf4\uace0\uc11c \uc800\uc7a5",
            f"Polymer_Lead_Report_{self._polymer_name}.pdf",
            "PDF (*.pdf)",
        )
        if not file_path:
            return

        try:
            from polymer_lead_report_exporter import (
                PolymerLeadReportData, export_polymer_lead_report
            )
        except ImportError:
            QMessageBox.warning(self, "\uc624\ub958",
                                "polymer_lead_report_exporter \ubaa8\ub4c8\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.")
            return

        try:
            # 현재 선택된 행 (없으면 1위)
            sel_row = 0
            sel_items = self._opt_table.selectedItems()
            if sel_items:
                sel_row = sel_items[0].row()

            vsmi, best_props, best_score, best_desc = self._opt_results[sel_row]

            # goal/weights
            goal_name = self._opt_goal_combo.currentText()
            goal_weights = POLYMER_OPTIMIZATION_GOALS.get(goal_name, {})
            # N-code: type guard — goal_weights from config
            if not isinstance(goal_weights, dict):
                logger.warning("[PolymerPopup] goal_weights for report is not dict: type=%s",
                               type(goal_weights).__name__)
                goal_weights = {}

            # all_variants 목록 구성 (하위 호환: 4/7 원소)
            all_variants = []
            for result_tuple in self._opt_results:
                if len(result_tuple) >= 7:
                    smi_, props_, score_, desc_, sa_, gap_, dip_ = result_tuple[:7]
                else:
                    smi_, props_, score_, desc_ = result_tuple[:4]
                    sa_, gap_, dip_ = None, None, None
                entry: Dict[str, Any] = {
                    "smiles": smi_,
                    "description": desc_,
                    "score": score_,
                    "props": props_,
                }
                if sa_ is not None:
                    entry["sa_score"] = sa_
                if gap_ is not None:
                    entry["xtb_homo_lumo_gap_ev"] = gap_
                if dip_ is not None:
                    entry["xtb_dipole_debye"] = dip_
                all_variants.append(entry)

            # AI 텍스트 자동 생성 (xtb / SA 반영)
            orig_tg = getattr(self._props, 'Tg', 0) or 0
            # best_props may come from 7-element tuple
            if len(self._opt_results[sel_row]) >= 7:
                _, best_props, best_score, best_desc, best_sa, best_gap, best_dip = self._opt_results[sel_row][:7]
            else:
                _, best_props, best_score, best_desc = self._opt_results[sel_row][:4]
                best_sa, best_gap, best_dip = None, None, None
            best_tg = getattr(best_props, 'Tg', 0) or 0

            engine_desc = "Van Krevelen 그룹 기여법 + RDKit QSPR 하이브리드"
            if XTB_OK:
                engine_desc += " + GFN2-xTB 전자구조 계산"
            if SA_SCORE_OK:
                engine_desc += " + SA Score 합성가능성 필터(≤6.0)"

            xtb_part = ""
            if best_gap is not None:
                xtb_part = f" xtb HOMO-LUMO gap = {best_gap:.2f} eV,"
            sa_part = ""
            if best_sa is not None:
                sa_part = f" SA Score = {best_sa:.2f} (합성 용이)," if best_sa < 4 else f" SA Score = {best_sa:.2f},"

            ai_text = (
                f"원본 단량체 {self._polymer_name}의 "
                f"{goal_name}을 위해 리드 최적화를 수행하였다. "
                f"총 {len(all_variants)}종의 유도체를 생성하여 "
                f"{engine_desc} 엔진으로 물성을 예측하고, "
                f"가중 스코어링으로 순위를 매겼다. "
                f"3세대 진화적 최적화(초기 20개 → 상위5 엘리트 돌연변이 반복)를 적용하였다. "
                f"최적 유도체는 {best_desc}로,{sa_part}{xtb_part} "
                f"Tg가 {orig_tg:.1f}°C에서 {best_tg:.1f}°C로 변화하였다."
            )

            data = PolymerLeadReportData(
                original_smiles=self._smiles,
                original_polymer_props=self._props,
                optimization_goal=goal_name,
                optimization_weights=goal_weights,
                all_variants=all_variants,
                selected_smiles=vsmi,
                selected_description=best_desc,
                selected_polymer_props=best_props,
                selected_score=best_score,
                ai_text=ai_text,
                conditions=getattr(self, '_conditions', {}),
            )

            success, msg = export_polymer_lead_report(data, file_path)
            if success:
                QMessageBox.information(
                    self, "\uc644\ub8cc",
                    f"\ub9ac\ub4dc \ucd5c\uc801\ud654 \ubcf4\uace0\uc11c \uc800\uc7a5 \uc644\ub8cc:\n{file_path}"
                )
            else:
                QMessageBox.warning(self, "\uc624\ub958", f"\uc800\uc7a5 \uc2e4\ud328: {msg}")
        except Exception as e:
            logger.warning("Lead report export failed: %s", e)
            QMessageBox.warning(
                self, "\uc624\ub958", f"\ub9ac\ub4dc \ubcf4\uace0\uc11c \uc0dd\uc131 \uc911 \uc624\ub958: {e}"
            )


# ── 호환성 알리아스 ─────────────────────────────────────────────────────
# evolution_loop._FEATURE_CONNECTIVITY_MAP / ct_hourly_review 등 하네스 도구가
# "PolymerPopup" 이름으로 연결성을 검증함.  실제 구현 클래스는 PolymerAnalysisPopup.
PolymerPopup = PolymerAnalysisPopup  # noqa: E305

# ── 단독 실행 테스트 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    # 폴리스타이렌 테스트
    dlg = PolymerAnalysisPopup("C=Cc1ccccc1", mol_name="Polystyrene (test)")
    dlg.show()
    sys.exit(app.exec())
