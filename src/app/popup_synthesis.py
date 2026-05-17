#!/usr/bin/env python3
"""
합성 경로 분석 팝업 (Synthesis Route Planner).
목표 분자 SMILES → 역합성 엔진으로 모든 합성 경로 탐색 →
플로차트 시각화 + 단계별 메커니즘 보기.
"""
import logging
import os
import sys
import traceback
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# Headless/capture audits must not load heavy local LLMs while collecting GUI evidence.
# [MAGIC] qwen2.5:14b uses about 9.7GB VRAM on this machine and repeatedly stalled
# popup_screenshot_matrix in M854 watchdog cycles.
_HEADLESS_MODE = (
    os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
    or os.environ.get("CHEMGRID_HEADLESS", "0") == "1"
)
_SKIP_OLLAMA_FALLBACK = (
    _HEADLESS_MODE
    or os.environ.get("CHEMGRID_SKIP_OLLAMA_FALLBACK", "0") == "1"
    or os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
)


def _is_capture_or_headless_mode() -> bool:
    """Runtime check for evidence harnesses that must not enter modal exec()."""
    return (
        _HEADLESS_MODE
        or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
        or os.environ.get("CHEMGRID_HEADLESS", "0") == "1"
        or os.environ.get("CHEMGRID_CAPTURE_MODE", "0") == "1"
    )


_ACTIVE_SYNTHESIS_VIEWERS = []

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSplitter,
    QProgressBar, QMessageBox, QSizePolicy, QGroupBox,
    QToolTip, QApplication, QTextEdit, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
)
from PyQt6.QtCore import (
    Qt, QObject, QThread, pyqtSignal, QRectF, QPointF, QSize, QTimer,
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QLinearGradient, QPixmap, QPalette, QImage,
)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from retrosynthesis_engine import (
    RetrosynthesisEngine, SynthesisRoute, SynthesisStep, RouteFeasibility,
)

from building_blocks import get_building_block_info, is_building_block
from mechanism_pdf_exporter import MechanismPDFExporter, export_synthesis_route_pdf

# Curved arrow imports for mechanism overlay
try:
    from mechanism_engine import MechanismEngine
    from popup_reaction import CurvedArrowRenderer
    MECHANISM_AVAILABLE = True
except ImportError:
    MECHANISM_AVAILABLE = False

# ═══════════════════════════════════════════════════════════
# Gemini API worker (runs in QThread to avoid GUI freeze)
# ═══════════════════════════════════════════════════════════

class _GeminiWorker(QObject):
    """Background worker for Gemini API calls — new SDK (google.genai) 우선, old SDK fallback."""
    finished = pyqtSignal(str, str)  # (result_text, error_msg)

    def __init__(self, genai_lib, api_key: str, prompt: str):
        super().__init__()
        self._genai_lib = genai_lib
        self._api_key = api_key
        self._prompt = prompt

    def run(self):
        try:
            # 1차: 새 SDK (google.genai) 시도
            result_text = None
            models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
            try:
                import google.genai as _new_genai
                client = _new_genai.Client(api_key=self._api_key)
                for model_name in models_to_try:
                    try:
                        resp = client.models.generate_content(
                            model=model_name, contents=self._prompt
                        )
                        result_text = resp.text
                        if result_text:
                            break
                    except Exception:
                        continue
            except ImportError as e:
                logger.warning(f"[SynthesisWorker] Gemini 신형 SDK 임포트 실패: {e}")

            # 2차: Old SDK fallback
            if not result_text and self._genai_lib:
                self._genai_lib.configure(api_key=self._api_key)
                for model_name in models_to_try:
                    try:
                        model = self._genai_lib.GenerativeModel(model_name)
                        response = model.generate_content(self._prompt)
                        try:
                            result_text = response.text
                        except ValueError:
                            block_reason = ""
                            try:
                                if response.prompt_feedback and response.prompt_feedback.block_reason:
                                    block_reason = f" (사유: {response.prompt_feedback.block_reason.name})"
                            except Exception as e:
                                logger.warning(f"[SynthesisWorker] prompt_feedback 읽기 실패: {e}")
                            self.finished.emit("", f"응답이 안전 필터에 의해 차단되었습니다{block_reason}")
                            return
                        if result_text:
                            break
                    except Exception:
                        continue

            if not result_text:
                self.finished.emit("", "Gemini API 호출 실패 — 모든 모델에서 응답 없음")
                return
            self.finished.emit(result_text, "")
        except Exception as e:
            self.finished.emit("", f"{type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════
# 색상 테마
# ═══════════════════════════════════════════════════════════
_COLORS = {
    "bg": QColor(24, 26, 32),
    "panel": QColor(32, 34, 42),
    "card": QColor(42, 44, 54),
    "card_hover": QColor(52, 56, 68),
    "accent": QColor(66, 165, 245),      # 파란색 계열
    "accent2": QColor(255, 167, 38),     # 주황색
    "success": QColor(102, 187, 106),    # 초록
    "warning": QColor(255, 183, 77),     # 경고
    "text": QColor(224, 224, 224),
    "text_dim": QColor(158, 158, 158),
    "building_block": QColor(76, 175, 80),  # 빌딩블록 초록
    "target": QColor(244, 67, 54),          # 타겟 빨강
    "intermediate": QColor(66, 165, 245),   # 중간체 파랑
    "arrow": QColor(255, 167, 38),          # 화살표 주황
}


# ═══════════════════════════════════════════════════════════
# [M849] Ollama fallback QThread (GUI freeze 방지)
# ═══════════════════════════════════════════════════════════
class _OllamaFallbackThread(QThread):
    """Ollama 텍스트 경로 제안 비동기 QThread.

    M849 FIX: 이전 _on_routes_found()의 동기 Ollama 호출(5s) -> GUI 동결 원인.
    학술: Coley 2019 ACS Cent. Sci. 5:1572 (ASKCOS), Schwaller 2020 Chem. Sci. 11:3316
    """
    finished = pyqtSignal(str)   # 응답 텍스트 (실패 시 빈 문자열)

    def __init__(self, smiles: str, parent=None):
        super().__init__(parent)
        self._smiles = smiles

    def run(self):
        hint = ""
        if _SKIP_OLLAMA_FALLBACK:
            logger.warning(
                "[M854] Ollama synthesis fallback skipped in headless/capture mode "
                "(QT_QPA_PLATFORM=%s, CHEMGRID_CAPTURE_MODE=%s)",
                os.environ.get("QT_QPA_PLATFORM", ""),
                os.environ.get("CHEMGRID_CAPTURE_MODE", "0"),
            )
            self.finished.emit("")
            return
        try:
            import requests as _req
            nl = chr(10)
            _prompt = (
                "SMILES: " + self._smiles + nl +
                "이 분자의 간단한 유기합성 경로를 3단계 이내로 한국어로 제시하라. "
                "단계별: (1)출발물질 (2)시약/조건 (3)생성물. 가능하면 SMILES 포함."
            )
            _resp = _req.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen2.5-coder:1.5b", "prompt": _prompt, "stream": False},
                timeout=5,   # [MAGIC:5] Ollama 최대 대기(초) — GUI freeze 방지 M849
            )
            if _resp.ok:
                hint = _resp.json().get("response", "")
        except Exception as _oe:
            import logging as _log
            _log.getLogger(__name__).warning(
                "[M849][_OllamaFallbackThread] Ollama 경로 제안 실패: %s", _oe)
        self.finished.emit(hint)


# ═══════════════════════════════════════════════════════════
# [M923 FIX] 엔진 상태 백그라운드 체크 스레드
# 격분 #15: _update_engine_status_label이 GUI 스레드에서
# ASKCOS is_available() 최대 ~16s 네트워크 요청 → 합성경로탭 완전 차단.
# 수정: 네트워크 체크를 QThread로 분리, GUI 즉시 "확인 중..." 표시 후 비동기 갱신.
# ═══════════════════════════════════════════════════════════
class _EngineStatusThread(QThread):
    """ASKCOS/IBM RXN 온라인 여부 백그라운드 확인.

    Rule M: 실패 시 logger.warning + "오프라인" 표시 (silent failure 금지).
    학술: Coley 2019 ACS Cent. Sci. 5:1572 (ASKCOS), Schwaller 2020 Chem Sci 11:3316 (IBM RXN).
    """
    status_ready = pyqtSignal(str, bool, bool)
    # (status_text, askcos_online, ibm_rxn_online)

    def run(self):
        lines = []
        askcos_online = False
        ibm_rxn_online = False
        try:
            from retrosynthesis_engine import RetrosynthesisEngine
            engine = RetrosynthesisEngine()
            engine._get_askcos_client()   # lazy init + is_available() 호출
            engine._get_ibm_rxn_client()  # [M852] IBM RXN lazy init
            askcos_online = engine._use_askcos and getattr(engine, '_askcos_online', False)
            ibm_rxn_online = getattr(engine, '_ibm_rxn_online', False)
            local_count = len(getattr(engine, '_transforms', []))
            if askcos_online:
                lines.append("ASKCOS: 온라인 (Coley 2019, 1M+ 템플릿)")
            else:
                askcos_client = getattr(engine, '_askcos_client', None)
                askcos_err = ""
                if askcos_client is not None and hasattr(askcos_client, "get_last_error"):
                    try:
                        askcos_err = str(askcos_client.get_last_error())[:80]
                    except Exception as _err:
                        logger.warning("[M923] ASKCOS last_error read failed: %s", _err)
                if askcos_err:
                    lines.append(
                        f"ASKCOS: 오프라인 ({askcos_err}) → 로컬 SMARTS {local_count}종")
                else:
                    lines.append(
                        f"ASKCOS: 오프라인 → 로컬 SMARTS {local_count}종 (RDKit)")
            if ibm_rxn_online:
                lines.append("IBM RXN: 온라인 (Schwaller 2020)")
            else:
                lines.append("IBM RXN: 오프라인 (API 키 미설정)")
        except Exception as _e:
            logger.warning("[M923] _EngineStatusThread 엔진 상태 확인 실패: %s", _e)
            lines.append("ASKCOS: 상태 미확인")
            lines.append("IBM RXN: 상태 미확인")
        lines.append("학술: Coley 2019 ACS Cent.Sci. 5:1572")
        self.status_ready.emit(" | ".join(lines), askcos_online, ibm_rxn_online)


# ═══════════════════════════════════════════════════════════
# 백그라운드 역합성 스레드
# ═══════════════════════════════════════════════════════════
class RetrosynthesisThread(QThread):
    """백그라운드에서 합성 경로 탐색"""
    progress = pyqtSignal(str)       # 상태 메시지
    route_found = pyqtSignal(object) # SynthesisRoute 하나씩 전달
    finished_all = pyqtSignal(list)  # 전체 결과 리스트
    error = pyqtSignal(str)

    def __init__(self, target_smiles: str, max_depth=6, max_routes=30,
                 validate=True, timeout=15.0,
                 starting_material: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._target = target_smiles
        self._max_depth = max_depth
        self._max_routes = max_routes
        self._validate = validate
        self._timeout = timeout
        self._starting_material = starting_material

    def run(self):
        try:
            self.progress.emit("역합성 엔진 초기화 중...")
            engine = RetrosynthesisEngine()
            # [M677 FIX] 사용자 LV.14 item 15+17 — chemgrid lite 합성경로탭 복구.
            # 사용자 명령: "원본 chemgrid 참조해서 제대로 복구시켜놔 물론 lite인거 감안해서 외부엔진 위주로"
            # ASKCOS 서버 온라인 여부 확인 후 사용자 피드백 (Rule M, Rule NN)
            # 학술 인용:
            #   Coley, C.W. et al. (2019) ACS Cent. Sci. 5(9): 1572-1583.  (ASKCOS 1M+ templates)
            #   Schwaller, P. et al. (2020) Chem. Sci. 11: 3316.            (IBM RXN fallback)
            engine._get_askcos_client()  # lazy init 강제 수행
            # [M852] IBM RXN lazy init
            engine._get_ibm_rxn_client()

            # [M852] 외부 엔진 상태 알림 (ASKCOS + IBM RXN)
            engines_online = []
            if engine._use_askcos and engine._askcos_online:
                engines_online.append("ASKCOS (Coley 2019)")
            if engine._ibm_rxn_online:
                engines_online.append("IBM RXN (Schwaller 2020)")

            if engines_online:
                self.progress.emit(
                    f"외부 엔진 온라인: {', '.join(engines_online)}")
            elif engine._use_askcos and not engine._askcos_online:
                self.progress.emit(
                    "ASKCOS/IBM RXN 오프라인 → 로컬 SMARTS 템플릿 + RDKit 엔진 (fallback)")
            else:
                self.progress.emit("로컬 SMARTS + RDKit 엔진 사용 중 (외부 엔진 비활성)")

            if self._starting_material:
                self.progress.emit("모분자 -> 유도체 변환 경로 탐색 중...")
            else:
                self.progress.emit(f"경로 탐색 중... (최대 깊이: {self._max_depth})")
            routes = engine.find_routes(
                self._target,
                max_depth=self._max_depth,
                max_routes=self._max_routes,
                validate=self._validate,
                timeout_seconds=self._timeout,
                starting_material=self._starting_material,
            )
            # [M677 FIX] Rule M — 0건이라도 silent 금지: 어떤 엔진이 시도됐는지 명시
            if routes:
                self.progress.emit(
                    f"완료: {len(routes)}개 경로 발견 "
                    f"(ASKCOS={engine._askcos_online}, 로컬={len(engine._transforms)} 템플릿)")
            else:
                logger.warning(
                    "[M677] RetrosynthesisThread: 경로 0건 — "
                    "ASKCOS=%s, target=%r, depth=%d",
                    engine._askcos_online, self._target, self._max_depth,
                )
                self.progress.emit(
                    "경로 0건 — ASKCOS/로컬 템플릿 모두 미매칭. "
                    "Gemini AI 분석을 이용해 보세요.")
            self.finished_all.emit(routes)
        except Exception as e:
            self.error.emit(f"오류: {e}\n{traceback.format_exc()}")


# ═══════════════════════════════════════════════════════════
# 경로 플로차트 위젯
# ═══════════════════════════════════════════════════════════
class RouteFlowchartWidget(QWidget):
    """합성 경로를 가로 교과서 스타일로 시각화 (골격식 분자 + 반응 화살표)

    Layout:
        [시작물질] ──→ [중간체₁] ──→ [중간체₂] ──→ [타겟]
                  조건         조건          조건

    ㄹ자 꺾기: 한 줄에 다 안 들어가면 다음 줄로 (교과서 스타일)
    """

    step_clicked = pyqtSignal(int)  # 단계 인덱스 클릭

    # --- CPK heteroatom colors ---
    _HETERO = {
        "O": QColor(220, 20, 20), "N": QColor(30, 30, 200),
        "S": QColor(180, 160, 0), "P": QColor(200, 120, 0),
        "F": QColor(0, 160, 0), "Cl": QColor(0, 160, 0),
        "Br": QColor(140, 40, 40), "I": QColor(120, 0, 160),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._route: Optional[SynthesisRoute] = None
        self._no_routes_msg: str = ""   # [Rule M] 경로 0건 실패 메시지 (빈=대기 안내)
        self._hover_step = -1
        self._node_rects: List[QRectF] = []   # 클릭 영역
        self._atom_positions: Dict[int, Dict[int, QPointF]] = {}  # node_idx → {atom_idx: QPointF}
        self._mechanism_cache: Dict[str, object] = {}  # cache key → MechanismData
        self._mechanism_engine = None
        self.setMouseTracking(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(280)

    def set_route(self, route: Optional[SynthesisRoute]):
        self._route = route
        self._no_routes_msg = ""  # [Rule M] 실패 메시지 초기화 (set_no_routes_message가 설정한 값 클리어)
        self._node_rects.clear()
        self._atom_positions.clear()
        self._mechanism_cache.clear()
        self._recalc_size()
        self.update()

    def set_no_routes_message(self, message: str):
        """[Rule M] 경로 0건 시 플로차트 영역에 명시적 실패 메시지 표시.
        Silent return(빈 흰 화면) 금지 — 사용자가 이유를 알 수 있어야 함."""
        self._route = None
        self._no_routes_msg = message
        self._node_rects.clear()
        self._atom_positions.clear()
        self._mechanism_cache.clear()
        self.setMinimumHeight(280)
        self.update()

    # ── 크기 계산 ──
    def _recalc_size(self):
        if self._route is None or not self._route.steps:
            self.setMinimumHeight(280)
            return
        n_nodes = len(self._route.steps) + 1  # +1 for starting materials
        mols_per_row = max(2, self.width() // 220)
        n_rows = max(1, (n_nodes + mols_per_row - 1) // mols_per_row)
        row_h = 240
        self.setMinimumHeight(max(280, 30 + n_rows * row_h))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_size()

    # ── 골격식 분자 렌더링 (QPainter) ──
    @staticmethod
    def _render_skeletal(painter: QPainter, smiles_list: List[str],
                         rect: QRectF, hetero_colors: dict,
                         breaking_bonds: Optional[List[tuple]] = None,
                         forming_bonds: Optional[List[tuple]] = None
                         ) -> Dict[int, QPointF]:
        """RDKit 2D 좌표로 골격식을 직접 QPainter에 그림.
        다중 프래그먼트일 경우 각각 분리 렌더링 후 '+' 표시.

        [FIX-E] breaking_bonds, forming_bonds: (atom_i, atom_j) 리스트.
        해당 결합은 점선으로 렌더링됨. 유지되는 결합은 실선.

        Returns:
            Dict[int, QPointF]: atom_idx → 화면좌표 매핑 (화살표 렌더링용)
        """
        if not RDKIT_AVAILABLE:
            return {}

        # 다중 프래그먼트: 영역 분할 + 사이에 '+' 표시
        valid_smiles = [s for s in smiles_list if s]
        if len(valid_smiles) > 1:
            merged_positions: Dict[int, QPointF] = {}
            n_frags = len(valid_smiles)
            plus_w = 20  # '+' 기호 공간
            frag_w = (rect.width() - plus_w * (n_frags - 1)) / n_frags
            atom_offset = 0
            for fi, frag_smi in enumerate(valid_smiles):
                fx = rect.left() + fi * (frag_w + plus_w)
                frag_rect = QRectF(fx, rect.top(), frag_w, rect.height())
                # [FIX-E] Offset breaking/forming bonds for this fragment
                # Determine fragment atom count for upper bound
                try:
                    _frag_mol = Chem.MolFromSmiles(frag_smi) if RDKIT_AVAILABLE else None
                    if _frag_mol is None and RDKIT_AVAILABLE:
                        logger.warning("[Rule L] MolFromSmiles 실패: %r", frag_smi)
                    _frag_n = Chem.RemoveHs(_frag_mol).GetNumAtoms() if _frag_mol else 999
                except Exception:
                    _frag_n = 999
                frag_breaking = None
                frag_forming = None
                if breaking_bonds:
                    frag_breaking = [(a - atom_offset, b - atom_offset)
                                     for (a, b) in breaking_bonds
                                     if a >= atom_offset and b >= atom_offset
                                     and a < atom_offset + _frag_n
                                     and b < atom_offset + _frag_n]
                if forming_bonds:
                    frag_forming = [(a - atom_offset, b - atom_offset)
                                    for (a, b) in forming_bonds
                                    if a >= atom_offset and b >= atom_offset
                                    and a < atom_offset + _frag_n
                                    and b < atom_offset + _frag_n]
                frag_positions = RouteFlowchartWidget._render_skeletal(
                    painter, [frag_smi], frag_rect, hetero_colors,
                    breaking_bonds=frag_breaking, forming_bonds=frag_forming)
                # Offset atom indices for multi-fragment merging
                for idx, pt in frag_positions.items():
                    merged_positions[idx + atom_offset] = pt
                # Count atoms in this fragment for offset
                try:
                    mol = Chem.MolFromSmiles(frag_smi)
                    if mol:
                        mol = Chem.RemoveHs(mol)
                        atom_offset += mol.GetNumAtoms()
                    else:
                        logger.warning("[Rule L] MolFromSmiles 실패 (frag offset): %r", frag_smi)
                except Exception as e:
                    logger.warning(f"[MoleculeWidget] 프래그먼트 원자 오프셋 계산 실패: {e}")
                # '+' 기호
                if fi < n_frags - 1:
                    plus_x = fx + frag_w
                    painter.setPen(QPen(QColor(80, 80, 80)))
                    painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
                    painter.drawText(
                        QRectF(plus_x, rect.top(), plus_w, rect.height()),
                        Qt.AlignmentFlag.AlignCenter, "+")
            return merged_positions

        combined = ".".join(s for s in valid_smiles if s)
        try:
            mol = Chem.MolFromSmiles(combined)
            if mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패 (combined): %r", combined[:60])
                return {}
            mol = Chem.RemoveHs(mol)
            AllChem.Compute2DCoords(mol)
            # Kekulize: 방향족 결합 → 교차 단일/이중결합
            try:
                Chem.Kekulize(mol, clearAromaticFlags=False)
            except Exception as e:
                logger.warning(f"[MoleculeWidget] Kekulize 실패(방향족 원으로 표시됨): {e}")
        except Exception:
            return {}

        conf = mol.GetConformer()
        n = mol.GetNumAtoms()
        if n == 0:
            return {}

        # 좌표 수집
        xs, ys = [], []
        for i in range(n):
            pos = conf.GetAtomPosition(i)
            xs.append(pos.x)
            ys.append(-pos.y)  # Y 반전

        # 스케일 계산 — 분자를 rect 안에 맞추기 (여백 18px)
        margin = 18
        draw_rect = rect.adjusted(margin, margin + 4, -margin, -margin - 16)
        if draw_rect.width() < 20 or draw_rect.height() < 20:
            return {}

        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        mol_w = x_max - x_min if x_max > x_min else 1.0
        mol_h = y_max - y_min if y_max > y_min else 1.0

        sx = draw_rect.width() / mol_w
        sy = draw_rect.height() / mol_h
        scale = min(sx, sy, 32.0)  # 최대 배율 제한
        # 최소 배율: 분자가 너무 작지 않게
        scale = max(scale, 12.0)

        cx_mol = (x_min + x_max) / 2.0
        cy_mol = (y_min + y_max) / 2.0
        cx_draw = draw_rect.center().x()
        cy_draw = draw_rect.center().y()

        # 화면 좌표
        screen = {}
        for i in range(n):
            px = cx_draw + (xs[i] - cx_mol) * scale
            py = cy_draw + (ys[i] - cy_mol) * scale
            screen[i] = QPointF(px, py)

        # [FIX-E] 결합 그리기 — 유지 결합=실선, 끊어지거나 형성되는 결합=점선
        # breaking/forming bonds를 set으로 변환 (빠른 조회)
        _dotted_bonds = set()
        if breaking_bonds:
            for pair in breaking_bonds:
                _dotted_bonds.add((min(pair[0], pair[1]), max(pair[0], pair[1])))
        if forming_bonds:
            for pair in forming_bonds:
                _dotted_bonds.add((min(pair[0], pair[1]), max(pair[0], pair[1])))

        bond_pen_solid = QPen(QColor(40, 40, 40), max(1.4, scale * 0.07))
        bond_pen_solid.setCapStyle(Qt.PenCapStyle.RoundCap)
        bond_pen_dotted = QPen(QColor(80, 80, 80), max(1.4, scale * 0.07))
        bond_pen_dotted.setCapStyle(Qt.PenCapStyle.RoundCap)
        bond_pen_dotted.setStyle(Qt.PenStyle.DashLine)

        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            p1, p2 = screen[i], screen[j]
            bt = bond.GetBondTypeAsDouble()

            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = (dx * dx + dy * dy) ** 0.5
            if length < 0.1:
                continue

            # [FIX-E] 해당 결합이 끊어지거나 형성되면 점선 펜 사용
            bond_key = (min(i, j), max(i, j))
            bond_pen = bond_pen_dotted if bond_key in _dotted_bonds else bond_pen_solid

            if bt >= 2.8:
                # 삼중결합
                nx, ny = -dy / length, dx / length
                off = max(2.5, scale * 0.1)
                painter.setPen(bond_pen)
                painter.drawLine(p1, p2)
                painter.drawLine(
                    QPointF(p1.x() + nx * off, p1.y() + ny * off),
                    QPointF(p2.x() + nx * off, p2.y() + ny * off))
                painter.drawLine(
                    QPointF(p1.x() - nx * off, p1.y() - ny * off),
                    QPointF(p2.x() - nx * off, p2.y() - ny * off))
            elif bt >= 1.8:
                # 이중결합
                nx, ny = -dy / length, dx / length
                off = max(1.8, scale * 0.08)
                painter.setPen(bond_pen)
                painter.drawLine(
                    QPointF(p1.x() + nx * off, p1.y() + ny * off),
                    QPointF(p2.x() + nx * off, p2.y() + ny * off))
                painter.drawLine(
                    QPointF(p1.x() - nx * off, p1.y() - ny * off),
                    QPointF(p2.x() - nx * off, p2.y() - ny * off))
            else:
                painter.setPen(bond_pen)
                painter.drawLine(p1, p2)

        # 원자 라벨 (탄소는 생략, 헤테로원자만 표시)
        font_size = max(8, min(13, int(scale * 0.5)))
        atom_font = QFont("Arial", font_size, QFont.Weight.Bold)
        painter.setFont(atom_font)
        fm = QFontMetrics(atom_font)

        for i in range(n):
            atom = mol.GetAtomWithIdx(i)
            sym = atom.GetSymbol()
            if sym == "C" and atom.GetFormalCharge() == 0:
                continue  # 탄소 생략 (골격식)

            label = sym
            fc = atom.GetFormalCharge()
            if fc > 0:
                label += "+"
            elif fc < 0:
                label += "-"

            # H 표시
            n_h = atom.GetTotalNumHs()
            if n_h == 1:
                label += "H"
            elif n_h > 1:
                label += f"H{n_h}"

            # 배경 지우기 (결합선 위에 라벨이 깔끔하게)
            tw = fm.horizontalAdvance(label) + 4
            th = fm.height() + 2
            bg_rect = QRectF(screen[i].x() - tw / 2, screen[i].y() - th / 2, tw, th)
            painter.fillRect(bg_rect, QColor(255, 255, 255))

            # 색상
            color = hetero_colors.get(sym, QColor(40, 40, 40))
            painter.setPen(QPen(color))
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, label)

        return screen

    # ── 메인 paintEvent ──
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 흰 배경
        p.fillRect(0, 0, w, h, QColor(255, 255, 255))

        if self._route is None or not self._route.steps:
            # [Rule M] no_routes_msg가 있으면 실패 메시지 표시, 없으면 대기 안내
            no_msg = getattr(self, '_no_routes_msg', '')
            if no_msg:
                # 실패 메시지: 주황색 경고 스타일
                p.fillRect(0, 0, w, h, QColor(32, 28, 20))
                p.setPen(QPen(QColor(255, 183, 77)))  # 경고 주황
                p.setFont(QFont("Segoe UI", 11))
                p.drawText(
                    QRectF(20, 0, w - 40, h),
                    Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                    no_msg,
                )
            else:
                p.setPen(QPen(QColor(160, 160, 160)))
                p.setFont(QFont("Segoe UI", 12))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                           "경로를 선택해주세요")
            p.end()
            return

        route = self._route
        steps = route.steps

        # ── 천연물 추��� 경로 특별 렌더링 ──
        if getattr(route, '_is_extraction', False):
            self._paint_extraction_route(p, w, h, route)
            p.end()
            return

        # ── 노드 목록 구성 ──
        # node = (ntype, smiles_list, step_idx_or_None)
        all_nodes = []
        # 시작 물질
        all_nodes.append(("bb", steps[0].reactant_smiles, -1))
        for si, step in enumerate(steps):
            is_target = (si == len(steps) - 1)
            ntype = "target" if is_target else "inter"
            all_nodes.append((ntype, [step.product_smiles], si))

        n_nodes = len(all_nodes)

        # ── 레이아웃: 가로 나열, ㄹ자 꺾기 ──
        arrow_w = 70  # 화살표 공간
        margin_x = 16
        margin_y = 28
        avail_w = w - 2 * margin_x

        min_mol_w = 150
        slot_w = min_mol_w + arrow_w
        mols_per_row = max(2, int((avail_w + arrow_w) / slot_w))
        if n_nodes <= mols_per_row:
            mols_per_row = n_nodes

        mol_w = max(130, (avail_w - arrow_w * (min(mols_per_row, n_nodes) - 1))
                    / min(mols_per_row, n_nodes))
        n_rows = max(1, (n_nodes + mols_per_row - 1) // mols_per_row)
        row_h = max(200, (h - margin_y - 10) / n_rows)

        self._node_rects.clear()

        for mi, (ntype, smiles_list, step_idx) in enumerate(all_nodes):
            row = mi // mols_per_row
            col = mi % mols_per_row

            # ㄹ자: 짝수 행 L→R, 홀수 행 R→L
            if row % 2 == 0:
                x_start = margin_x + col * (mol_w + arrow_w)
            else:
                x_start = margin_x + (mols_per_row - 1 - col) * (mol_w + arrow_w)

            y_start = margin_y + row * row_h
            mol_rect = QRectF(x_start, y_start, mol_w, row_h - 30)
            self._node_rects.append(mol_rect)

            # ── 노드 배경 (hover 하이라이트) ──
            is_hovered = (mi == self._hover_step)
            if is_hovered:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(220, 235, 255, 80)))
                p.drawRoundedRect(mol_rect.adjusted(-2, -2, 2, 2), 6, 6)

            # ── 노드 테두리 (타입별 색상) ──
            if ntype == "bb":
                border_color = QColor(76, 175, 80)  # 초록
            elif ntype == "target":
                border_color = QColor(244, 67, 54)  # 빨강
            else:
                border_color = QColor(66, 165, 245)  # 파랑

            pen = QPen(border_color, 2.0)
            pen.setStyle(Qt.PenStyle.DashLine if ntype == "inter" else Qt.PenStyle.SolidLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(mol_rect.adjusted(1, 1, -1, -1), 6, 6)

            # ── 골격식 분자 렌더링 ──
            # [FIX-E] 결합 변화 정보를 가져와서 점선 렌더링에 전달
            breaking = None
            forming = None
            if MECHANISM_AVAILABLE and step_idx >= 0 and step_idx < len(steps):
                cur_step = steps[step_idx]
                cache_key = f"{'.'.join(cur_step.reactant_smiles)}>>>{cur_step.product_smiles}"
                mech_data = self._mechanism_cache.get(cache_key)
                if mech_data is not None:
                    breaking = []
                    forming = []
                    for ms in mech_data.steps:
                        for arr in ms.arrows:
                            if arr.from_atom_idx >= 0 and arr.to_atom_idx >= 0:
                                pair = (arr.from_atom_idx, arr.to_atom_idx)
                                if arr.to_type in ("atom", "antibonding"):
                                    forming.append(pair)
                                if arr.from_type == "bond":
                                    breaking.append(pair)
            atom_pos = self._render_skeletal(p, smiles_list, mol_rect, self._HETERO,
                                             breaking_bonds=breaking,
                                             forming_bonds=forming)
            self._atom_positions[mi] = atom_pos

            # ── 라벨 (시작물질 / 중간체 / 타겟) ──
            label_y = mol_rect.bottom() + 2
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))

            if ntype == "bb":
                p.setPen(QPen(QColor(76, 175, 80)))
                bb_names = []
                for smi in smiles_list:
                    info = get_building_block_info(smi)
                    bb_names.append(info['name_en'] if info else smi[:18])
                lbl = " + ".join(bb_names)
            elif ntype == "target":
                p.setPen(QPen(QColor(244, 67, 54)))
                lbl = "Target"
            else:
                p.setPen(QPen(QColor(100, 100, 100)))
                lbl = f"Step {step_idx + 1}"

            lbl_rect = QRectF(mol_rect.left(), label_y, mol_rect.width(), 18)
            p.drawText(lbl_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, lbl)

            # ── 가로 반응 화살표 (노드 → 다음 노드) ──
            if mi < n_nodes - 1:
                next_row = (mi + 1) // mols_per_row
                next_col = (mi + 1) % mols_per_row

                step_data = steps[mi] if mi < len(steps) else None

                if next_row == row:
                    # 같은 줄: 가로 화살표
                    if row % 2 == 0:
                        ax1 = mol_rect.right() + 6
                        ax2 = ax1 + arrow_w - 12
                    else:
                        ax1 = mol_rect.left() - 6
                        ax2 = ax1 - arrow_w + 12
                    ay = mol_rect.center().y()

                    # 화살표 선
                    p.setPen(QPen(QColor(60, 60, 60), 2.0))
                    p.drawLine(QPointF(ax1, ay), QPointF(ax2, ay))

                    # 화살표 머리
                    head = 10  # Rule O/M473: visible route arrowhead minimum is 10 px.
                    direction = 1 if ax2 > ax1 else -1
                    arrow_path = QPainterPath()
                    arrow_path.moveTo(ax2, ay)
                    arrow_path.lineTo(ax2 - direction * head, ay - head)
                    arrow_path.lineTo(ax2 - direction * head, ay + head)
                    arrow_path.closeSubpath()
                    p.fillPath(arrow_path, QBrush(QColor(60, 60, 60)))

                    # 조건 라벨 (화살표 위)
                    if step_data:
                        p.setPen(QPen(QColor(0, 100, 200)))
                        p.setFont(QFont("Segoe UI", 7))
                        cond_rect = QRectF(min(ax1, ax2) - 10, ay - 28,
                                           abs(ax2 - ax1) + 20, 24)
                        cond_text = step_data.transform_name
                        if step_data.conditions:
                            cond_text += f"\n{step_data.conditions}"
                        p.drawText(cond_rect,
                                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                                   cond_text)

                        # 추가 반응물
                        if len(step_data.reactant_smiles) > 1:
                            extra = step_data.reactant_smiles[1:]
                            extra_names = []
                            for smi in extra:
                                info = get_building_block_info(smi)
                                extra_names.append(info['name_en'] if info else smi[:12])
                            p.setPen(QPen(QColor(150, 150, 150)))
                            p.setFont(QFont("Segoe UI", 7))
                            extra_rect = QRectF(min(ax1, ax2) - 10, ay + 4,
                                                abs(ax2 - ax1) + 20, 16)
                            p.drawText(extra_rect,
                                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                       f"+ {', '.join(extra_names)}")

                else:
                    # 다른 줄: 꺾이는 화살표 (아래로)
                    if row % 2 == 0:
                        sx = mol_rect.right() - 10
                    else:
                        sx = mol_rect.left() + 10

                    sy1 = mol_rect.bottom() + 18
                    sy2 = margin_y + next_row * row_h - 4

                    p.setPen(QPen(QColor(60, 60, 60), 2.0, Qt.PenStyle.DashLine))
                    p.drawLine(QPointF(sx, sy1), QPointF(sx, sy2))

                    head = 10  # Rule O/M473: visible route arrowhead minimum is 10 px.
                    arrow_path = QPainterPath()
                    arrow_path.moveTo(sx, sy2)
                    arrow_path.lineTo(sx - head, sy2 - head)
                    arrow_path.lineTo(sx + head, sy2 - head)
                    arrow_path.closeSubpath()
                    p.fillPath(arrow_path, QBrush(QColor(60, 60, 60)))

                    if step_data:
                        p.setPen(QPen(QColor(0, 100, 200)))
                        p.setFont(QFont("Segoe UI", 7))
                        cond_rect = QRectF(sx + 10, (sy1 + sy2) / 2 - 10, 120, 20)
                        p.drawText(cond_rect,
                                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                   step_data.transform_name)

        # ── 굽은 화살표 오버레이 (전자 이동 메커니즘) ──
        if MECHANISM_AVAILABLE:
            self._draw_mechanism_arrows(p, steps)

        p.end()

    # ── 메커니즘 굽은 화살표 렌더링 ──
    def _draw_mechanism_arrows(self, painter: QPainter, steps: list):
        """각 합성 단계에 대해 전자 이동 굽은 화살표를 오버레이.

        [P0-4 FIX] 모든 메커니즘 단계의 화살표를 표시 (기존: 1단계만).
        - 멀티 프래그먼트 SMILES에서 분자 간(intermolecular) 화살표도 지원
        - 메커니즘 단계별 색상 구분 (1단계=빨강, 2단��=파랑, 3단계=보라)
        - 전이 상태 표시 (‡ 기호) 추가
        """
        if not self._route or not steps:
            return

        if self._mechanism_engine is None:
            try:
                self._mechanism_engine = MechanismEngine()
            except Exception as e:
                logger.warning("MechanismEngine init failed: %s", e)
                return

        # 메커니즘 단계별 색상 팔레트 (교과서 스타일)
        _MECH_STEP_COLORS = [
            QColor(200, 30, 30, 200),    # Step 1: 빨강 (친핵체 공격)
            QColor(30, 80, 200, 200),    # Step 2: 파랑 (이탈기 이탈)
            QColor(140, 30, 180, 200),   # Step 3: 보라 (재배열)
            QColor(200, 120, 0, 200),    # Step 4: 주황
            QColor(0, 140, 100, 200),    # Step 5: 청록
        ]

        for si, step in enumerate(steps):
            # node index: 0=시작물질, 1..N=각 step 생성물
            # 반응물 노드 인덱스 = si (step의 반응물), 생성물 = si+1
            reactant_node_idx = si
            reactant_positions = self._atom_positions.get(reactant_node_idx, {})
            if not reactant_positions:
                continue

            # 메커니즘 생성 (캐시)
            # [INTERMOLECULAR FIX] generate_intermolecular_mechanism 사용:
            # - reactant_smiles 목록 순서를 유지하여 combined SMILES 생성
            # - 금 표준 템플릿 원자 인덱스를 실제 combined mol 인덱스로 재매핑
            # - 결과: from_atom_idx/to_atom_idx 가 merged_positions 딕셔너리와 정확히 일치
            cache_key = f"{'.'.join(step.reactant_smiles)}>>>{step.product_smiles}"
            if cache_key not in self._mechanism_cache:
                try:
                    mech = self._mechanism_engine.generate_intermolecular_mechanism(
                        step.reactant_smiles,
                        step.product_smiles,
                        transform_name=getattr(step, 'transform_name', '') or '',
                        conditions=getattr(step, 'conditions', '') or '')
                    self._mechanism_cache[cache_key] = mech
                except Exception as e:
                    logger.warning(
                        "Intermolecular mechanism generation failed for step %d: %s", si, e)
                    self._mechanism_cache[cache_key] = None

            mech = self._mechanism_cache.get(cache_key)
            if mech is None:
                # [Rule M] silent failure 방지: 메커니즘 없음을 화면에 표시
                node_rect = self._node_rects[reactant_node_idx] if \
                    reactant_node_idx < len(self._node_rects) else None
                if node_rect is not None:
                    painter.save()
                    painter.setPen(QPen(QColor(160, 100, 0, 180), 1))
                    painter.setFont(QFont("Arial", 7))
                    painter.drawText(
                        QRectF(node_rect.left(), node_rect.bottom() - 18,
                               node_rect.width(), 18),
                        Qt.AlignmentFlag.AlignCenter,
                        "(메커니즘 정보 없음)")
                    painter.restore()
                logger.warning(
                    "_draw_mechanism_arrows: no mechanism for step %d cache_key=%r",
                    si, cache_key[:60])
                continue

            # [P0-4 FIX] 모든 메커니즘 단계의 화살표를 렌더링
            for mech_step_idx, mech_step in enumerate(mech.steps):
                # 단계별 색상 선택
                arrow_color = _MECH_STEP_COLORS[
                    mech_step_idx % len(_MECH_STEP_COLORS)]

                # 전이 상태 표시 (‡ 기호)
                if mech_step.is_transition_state and reactant_positions:
                    # 반응물 영역 중앙 상단에 ‡ 기호 표시
                    node_rect = self._node_rects[reactant_node_idx] if \
                        reactant_node_idx < len(self._node_rects) else None
                    if node_rect is not None:
                        painter.setPen(QPen(QColor(180, 80, 0), 1.5))
                        painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
                        ts_x = node_rect.right() - 20
                        ts_y = node_rect.top() + 16
                        painter.drawText(QPointF(ts_x, ts_y), "\u2021")

                # 분자 경계 계산: 각 fragment의 원자 인덱스 범위 파악
                # (분자간 화살표인지 분자내 화살표인지 판별에 사용)
                frag_boundaries: list = []  # [(start_idx, end_idx), ...]
                try:
                    from rdkit import Chem as _Chem
                    _offset = 0
                    for _smi in step.reactant_smiles:
                        if not _smi:
                            continue
                        _m = _Chem.MolFromSmiles(_smi)
                        if _m:
                            _m = _Chem.RemoveHs(_m)
                        else:
                            logger.warning("[Rule L] MolFromSmiles 실패 (frag boundary): %r", _smi)
                            continue
                        _n = _m.GetNumAtoms()
                        frag_boundaries.append((_offset, _offset + _n - 1))
                        _offset += _n
                except Exception as e:
                    logger.warning(f"[MechanismStepWidget] 프래그먼트 경계 계산 실패(curvature 조정 없이 진행): {e}")

                def _frag_of(idx: int) -> int:
                    """atom_idx 가 몇 번째 fragment 소속인지 반환 (-1=모름)"""
                    for fi, (lo, hi) in enumerate(frag_boundaries):
                        if lo <= idx <= hi:
                            return fi
                    return -1

                for arrow_idx, arrow in enumerate(mech_step.arrows):
                    from_idx = arrow.from_atom_idx
                    to_idx = arrow.to_atom_idx

                    # [INTERMOLECULAR FIX] 분자간(intermolecular) 화살표 처리:
                    # - from_idx, to_idx 가 모두 >= 0: merged_positions 에서 직접 조회
                    #   (이미 올바른 오프셋 포함. generate_intermolecular_mechanism 이 재매핑 완료)
                    # - from_idx=-1: 외부 소스 → 타겟 원자 근처에 화살표 시작점 배치
                    # - to_idx=-1: 외부 타겟 → 소스 원자 근처에 화살표 끝점 배치
                    start_pt = None
                    end_pt = None

                    if from_idx >= 0:
                        start_pt = reactant_positions.get(from_idx)
                    elif from_idx == -1 and reactant_positions:
                        # 외부 소스: 타겟 원자 근처에서 화살표 시작
                        if to_idx >= 0 and to_idx in reactant_positions:
                            target = reactant_positions[to_idx]
                            start_pt = QPointF(target.x() - 22, target.y() - 14)
                        else:
                            all_pts = list(reactant_positions.values())
                            if all_pts:
                                avg_y = sum(p.y() for p in all_pts) / len(all_pts)
                                min_x = min(p.x() for p in all_pts)
                                start_pt = QPointF(min_x - 18, avg_y)

                    if to_idx >= 0:
                        end_pt = reactant_positions.get(to_idx)
                    elif to_idx == -1 and reactant_positions:
                        # 외부 타겟: 소스 원자 근처로 화살표 끝
                        if from_idx >= 0 and from_idx in reactant_positions:
                            source = reactant_positions[from_idx]
                            end_pt = QPointF(source.x() + 22, source.y() + 14)
                        else:
                            all_pts = list(reactant_positions.values())
                            if all_pts:
                                avg_y = sum(p.y() for p in all_pts) / len(all_pts)
                                max_x = max(p.x() for p in all_pts)
                                end_pt = QPointF(max_x + 18, avg_y)

                    if start_pt is None or end_pt is None:
                        logger.debug(
                            "Mechanism arrow skip: from_idx=%d to_idx=%d "
                            "start=%s end=%s reactant_positions keys=%s",
                            from_idx, to_idx, start_pt, end_pt,
                            sorted(reactant_positions.keys())[:10])
                        continue

                    # 화살표 너비: 첫 단계는 굵게, 이후 단계는 얇게
                    width = 2.0 if mech_step_idx == 0 else 1.5

                    # 분자간 화살표 여부 판별 → curvature 증가 (더 뚜렷한 호 형태)
                    curvature = arrow.curvature
                    if (from_idx >= 0 and to_idx >= 0
                            and frag_boundaries
                            and _frag_of(from_idx) != _frag_of(to_idx)
                            and _frag_of(from_idx) >= 0
                            and _frag_of(to_idx) >= 0):
                        # 서로 다른 분자 간 화살표: 반원형으로 올려 분명히 구분
                        curvature = max(curvature, 0.55)

                    if arrow.arrow_type == "full":
                        CurvedArrowRenderer.draw_full_arrow(
                            painter, start_pt, end_pt,
                            curvature=curvature,
                            color=arrow_color, width=width,
                            arrow_index=arrow_idx)
                    else:
                        CurvedArrowRenderer.draw_half_arrow(
                            painter, start_pt, end_pt,
                            curvature=curvature,
                            color=arrow_color, width=width,
                            arrow_index=arrow_idx)

    # ── 천연물 추출 경로 렌더링 ──
    def _paint_extraction_route(self, p: QPainter, w: int, h: int, route):
        """천연물 추출 경로를 교과서 스타일로 시각화.
        합성 화살표 대신 추출/정제 과정을 보여줌."""
        nat_info = getattr(route, '_natural_product_info', None)
        if nat_info is None:
            return

        margin = 30
        # 상단: 천연물 추출 안내 배너
        banner_h = 50
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(76, 175, 80, 30)))
        p.drawRoundedRect(QRectF(margin, 10, w - 2 * margin, banner_h), 8, 8)

        p.setPen(QPen(QColor(76, 175, 80)))
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        p.drawText(QRectF(margin + 10, 10, w - 2 * margin - 20, banner_h),
                   Qt.AlignmentFlag.AlignVCenter,
                   f"이 물질은 천연유래물질입니다. 추출 및 정제를 권장합니다.")

        # 본문 영역
        y_start = banner_h + 30
        section_w = w - 2 * margin
        line_h = 22

        def draw_section(y: float, title: str, content: str, color: QColor) -> float:
            """섹션 하나를 그리고 다음 y 좌표를 반환."""
            # 섹션 배경
            content_lines = content.split('. ')
            n_lines = max(1, len(content_lines))
            box_h = 30 + n_lines * line_h + 10
            p.setPen(QPen(color, 1.5))
            p.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 15)))
            p.drawRoundedRect(QRectF(margin, y, section_w, box_h), 6, 6)

            # 제목
            p.setPen(QPen(color))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            p.drawText(QRectF(margin + 12, y + 6, section_w - 24, 22),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

            # 내용
            p.setPen(QPen(QColor(60, 60, 60)))
            p.setFont(QFont("Segoe UI", 9))
            cy = y + 30
            for line in content_lines:
                line = line.strip()
                if line:
                    p.drawText(QRectF(margin + 16, cy, section_w - 32, line_h),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               line)
                    cy += line_h
            return y + box_h + 12

        # 1. 물질 정보
        y = draw_section(y_start,
                         f"[물질] {nat_info.name_kr} ({nat_info.name})",
                         f"유래: {nat_info.source}",
                         QColor(33, 150, 243))

        # 2. 추출 방법
        y = draw_section(y, "[추출 방법]", nat_info.extraction, QColor(76, 175, 80))

        # 3. 정제 방법
        y = draw_section(y, "[정제 방법]", nat_info.purification, QColor(156, 39, 176))

        # 4. 보관 조건 (있으면)
        if nat_info.storage:
            y = draw_section(y, "[보관 조건]", nat_info.storage, QColor(255, 152, 0))

        # 5. 참고사항 (있으면)
        if nat_info.note:
            y = draw_section(y, "[참고사항]", nat_info.note, QColor(96, 125, 139))

        # 타겟 분자 골격식 (우하단)
        mol_rect = QRectF(w - 220, y_start, 190, 150)
        p.setPen(QPen(QColor(200, 200, 200), 1.0, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(mol_rect.adjusted(-2, -2, 2, 2), 6, 6)
        self._render_skeletal(p, [route.target_smiles], mol_rect, self._HETERO)

        # 분자 라벨
        p.setPen(QPen(QColor(100, 100, 100)))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(mol_rect.left(), mol_rect.bottom() + 2, mol_rect.width(), 16),
                   Qt.AlignmentFlag.AlignHCenter, nat_info.name_kr)

    # ── 마우스 이벤트 ──
    def mouseMoveEvent(self, event):
        if self._route is None:
            return
        old_hover = self._hover_step
        self._hover_step = -1
        pos = QPointF(event.pos())
        for i, rect in enumerate(self._node_rects):
            if rect.contains(pos):
                self._hover_step = i
                break
        if old_hover != self._hover_step:
            self.update()

    def mousePressEvent(self, event):
        if self._route is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = QPointF(event.pos())
        for i, rect in enumerate(self._node_rects):
            if rect.contains(pos):
                # i=0은 시작물질, i=1~N은 step 0~N-1
                step_idx = i - 1
                if step_idx >= 0:
                    self.step_clicked.emit(step_idx)
                break


# ═══════════════════════════════════════════════════════════
# 경로 카드 위젯 (왼쪽 목록용)
# ═══════════════════════════════════════════════════════════
class RouteCardWidget(QFrame):
    """합성 경로 하나를 표시하는 카드"""
    clicked = pyqtSignal(int)  # route index

    def __init__(self, route: SynthesisRoute, index: int, parent=None):
        super().__init__(parent)
        self._route = route
        self._index = index
        self._selected = False
        self.setFixedHeight(90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        # 천연물 추출 경로 감지
        is_extraction = getattr(self._route, '_is_extraction', False)

        # 헤더: Route N ★
        header = QHBoxLayout()
        if is_extraction:
            lbl_title = QLabel("천연물 추출")
            lbl_title.setStyleSheet("color: #66BB6A;")
        else:
            lbl_title = QLabel(f"경로 {self._index + 1}")
            lbl_title.setStyleSheet("color: #E0E0E0;")
        lbl_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header.addWidget(lbl_title)

        # [M1355_W184] 점수 뱃지 + 품질 라벨 + 출처 태그
        # score: 낮을수록 좋음 (0=직접가용, <30=우수, <60=양호, <100=보통, >=100=복잡)
        score = self._route.score
        if is_extraction:
            score_text = "추출 권장"
            lbl_score = QLabel(score_text)
            lbl_score.setStyleSheet("color: #66BB6A; padding: 2px 6px; background: rgba(102,187,106,30); border-radius: 4px;")
        else:
            if score == 0:
                score_text = "직접 가용"
                _score_color = "#66BB6A"
                _score_bg = "rgba(102,187,106,30)"
            elif score < 30:
                score_text = f"우수 ({score:.0f})"   # [MAGIC:30] 우수 임계값
                _score_color = "#42A5F5"
                _score_bg = "rgba(66,165,245,30)"
            elif score < 60:
                score_text = f"양호 ({score:.0f})"   # [MAGIC:60] 양호 임계값
                _score_color = "#FFA726"
                _score_bg = "rgba(255,167,38,30)"
            elif score < 100:
                score_text = f"보통 ({score:.0f})"   # [MAGIC:100] 보통 임계값
                _score_color = "#FF7043"
                _score_bg = "rgba(255,112,67,30)"
            else:
                score_text = f"복잡 ({score:.0f})"
                _score_color = "#EF5350"
                _score_bg = "rgba(239,83,80,30)"
            lbl_score = QLabel(score_text)
            lbl_score.setStyleSheet(
                f"color: {_score_color}; padding: 2px 6px; "
                f"background: {_score_bg}; border-radius: 4px;"
            )
        lbl_score.setFont(QFont("Segoe UI", 8))
        header.addWidget(lbl_score)

        # [M1355_W184] 출처 태그 (ASKCOS / IBM RXN / 로컬)
        if not is_extraction:
            _src = ""
            if getattr(self._route, '_askcos_source', False):
                _ex = getattr(self._route, '_askcos_examples', 0)
                _src = f"ASKCOS ({_ex}건)" if _ex else "ASKCOS"
            elif getattr(self._route, '_ibm_rxn_source', False):
                _src = "IBM RXN"
            if _src:
                lbl_src = QLabel(_src)
                lbl_src.setFont(QFont("Segoe UI", 7))
                lbl_src.setStyleSheet("color: #78909C; padding: 1px 4px; border-radius: 3px;")
                header.addWidget(lbl_src)

        header.addStretch()
        layout.addLayout(header)

        if is_extraction:
            # 천연물 추출 카드: 유래 생물 표시
            nat_info = getattr(self._route, '_natural_product_info', None)
            source_text = nat_info.source if nat_info else "천연유래"
            lbl_source = QLabel(f"원료: {source_text}")
            lbl_source.setFont(QFont("Segoe UI", 9))
            lbl_source.setStyleSheet("color: #A5D6A7;")
            lbl_source.setWordWrap(True)
            layout.addWidget(lbl_source)

            lbl_note = QLabel("합성보다 추출이 효율적")
            lbl_note.setFont(QFont("Segoe UI", 8))
            lbl_note.setStyleSheet("color: #81C784;")
            layout.addWidget(lbl_note)
        else:
            # 단계 수 + 시작물질
            steps_text = f"{self._route.total_steps}단계"
            lbl_steps = QLabel(steps_text)
            lbl_steps.setFont(QFont("Segoe UI", 9))
            lbl_steps.setStyleSheet("color: #B0BEC5;")
            layout.addWidget(lbl_steps)

            # 빌딩블록 목록
            bb_names = []
            for bb in self._route.building_blocks[:4]:
                info = get_building_block_info(bb)
                if info:
                    bb_names.append(info['name_en'])
                else:
                    bb_names.append(bb[:12])
            bb_text = ", ".join(bb_names)
            if len(self._route.building_blocks) > 4:
                bb_text += f" +{len(self._route.building_blocks) - 4}"
            lbl_bb = QLabel(bb_text)
            lbl_bb.setFont(QFont("Segoe UI", 8))
            lbl_bb.setStyleSheet("color: #81C784;")
            lbl_bb.setWordWrap(True)
            layout.addWidget(lbl_bb)

        self._update_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        is_extraction = getattr(self._route, '_is_extraction', False)
        if self._selected:
            if is_extraction:
                self.setStyleSheet("""
                    RouteCardWidget {
                        background: rgba(76, 175, 80, 40);
                        border: 2px solid #66BB6A;
                        border-radius: 8px;
                    }
                """)
            else:
                self.setStyleSheet("""
                    RouteCardWidget {
                        background: rgba(66, 165, 245, 40);
                        border: 2px solid #42A5F5;
                        border-radius: 8px;
                    }
                """)
        else:
            if is_extraction:
                self.setStyleSheet("""
                    RouteCardWidget {
                        background: rgba(76, 175, 80, 20);
                        border: 1px solid #4CAF50;
                        border-radius: 8px;
                    }
                    RouteCardWidget:hover {
                        background: rgba(76, 175, 80, 40);
                        border: 1px solid #66BB6A;
                    }
                """)
            else:
                self.setStyleSheet("""
                    RouteCardWidget {
                        background: rgba(42, 44, 54, 200);
                        border: 1px solid #555;
                        border-radius: 8px;
                    }
                    RouteCardWidget:hover {
                        background: rgba(52, 56, 68, 200);
                        border: 1px solid #42A5F5;
                    }
                """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)


# ═══════════════════════════════════════════════════════════
# 단계 상세 패널
# ═══════════════════════════════════════════════════════════
class StepDetailPanel(QFrame):
    """선택된 단계의 상세 정보"""
    mechanism_requested = pyqtSignal(object)  # SynthesisStep
    gemini_requested = pyqtSignal(object)     # SynthesisStep or None (route-level)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(32,34,42,230); border-radius: 8px;")
        self._step: Optional[SynthesisStep] = None
        self._has_route = False  # True when any route data is available
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self._lbl_title = QLabel("단계를 선택해주세요")
        self._lbl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._lbl_title.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(self._lbl_title)

        self._lbl_reaction = QLabel("")
        self._lbl_reaction.setFont(QFont("Consolas", 9))
        self._lbl_reaction.setStyleSheet("color: #90CAF9;")
        self._lbl_reaction.setWordWrap(True)
        layout.addWidget(self._lbl_reaction)

        self._lbl_conditions = QLabel("")
        self._lbl_conditions.setFont(QFont("Segoe UI", 9))
        self._lbl_conditions.setStyleSheet("color: #FFA726;")
        layout.addWidget(self._lbl_conditions)

        self._lbl_confidence = QLabel("")
        self._lbl_confidence.setFont(QFont("Segoe UI", 9))
        self._lbl_confidence.setStyleSheet("color: #81C784;")
        layout.addWidget(self._lbl_confidence)

        # 메커니즘 보기 버튼
        self._btn_mechanism = QPushButton("🔬 메커니즘 보기 (굽은 화살표)")
        self._btn_mechanism.setFixedHeight(36)
        self._btn_mechanism.setStyleSheet("""
            QPushButton {
                background-color: #E65100; color: white; border-radius: 8px;
                font-weight: bold; font-size: 10pt;
            }
            QPushButton:hover { background-color: #F57C00; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._btn_mechanism.setEnabled(False)
        self._btn_mechanism.clicked.connect(self._on_mechanism_click)
        layout.addWidget(self._btn_mechanism)

        # Gemini AI 분석 버튼 — enabled whenever route data is available
        self._btn_gemini = QPushButton("🤖 Gemini AI 분석")
        self._btn_gemini.setFixedHeight(36)
        self._btn_gemini.setStyleSheet("""
            QPushButton {
                background-color: #1565C0; color: white; border-radius: 8px;
                font-weight: bold; font-size: 10pt;
            }
            QPushButton:hover { background-color: #1E88E5; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._btn_gemini.setEnabled(False)
        self._btn_gemini.clicked.connect(self._on_gemini_click)
        layout.addWidget(self._btn_gemini)
        self._btn_gemini.setToolTip("단계를 선택하면 단계 분석, 미선택 시 전체 경로 분석")

    def set_has_route(self, has_route: bool):
        """Call when a route is selected/deselected to enable route-level AI analysis."""
        self._has_route = has_route
        self._update_gemini_button()

    def _update_gemini_button(self):
        """Enable Gemini button if a step is selected OR route data is available."""
        enabled = self._step is not None or self._has_route
        self._btn_gemini.setEnabled(enabled)
        if self._step:
            self._btn_gemini.setText("🤖 Gemini AI 분석 (이 단계)")
        elif self._has_route:
            self._btn_gemini.setText("🤖 Gemini AI 분석 (전체 경로)")
        else:
            self._btn_gemini.setText("🤖 Gemini AI 분석")

    def set_step(self, step: Optional[SynthesisStep],
                 mechanism_data=None):
        """단계 정보를 설정합니다.

        Args:
            step: SynthesisStep 객체 또는 None
            mechanism_data: MechanismData 객체 (있으면 중간체/전이상태 정보 표시)
        """
        self._step = step
        if step is None:
            self._lbl_title.setText(
                "단계를 선택해주세요" if self._has_route
                else "경로를 먼저 탐색해주세요")
            self._lbl_reaction.setText("")
            self._lbl_conditions.setText("")
            self._lbl_confidence.setText("")
            self._btn_mechanism.setEnabled(False)
            self._update_gemini_button()
            return

        self._lbl_title.setText(f"Step {step.step_number}: {step.transform_name}")

        # 반응식 + 반응 조건 상세 표시
        r_str = " + ".join(step.reactant_smiles)
        reaction_text = f"{r_str}\n\u2192 {step.product_smiles}"

        # 메커니즘 정보가 있으면 중간체/전이상태 정보 추가
        if mechanism_data is not None:
            n_mech_steps = len(mechanism_data.steps)
            intermediates = []
            for ms in mechanism_data.steps:
                if ms.is_transition_state:
                    intermediates.append(f"  [\u2021 {ms.title}]")
                elif ms.product_smiles and ms.product_smiles != step.product_smiles:
                    intermediates.append(f"  \u2192 {ms.title}")
            if intermediates:
                reaction_text += "\n" + "\n".join(intermediates[:3])  # 최대 3개 표시
            reaction_text += f"\n({n_mech_steps}단계 메커니즘)"

        self._lbl_reaction.setText(reaction_text)

        # 반응 조건 상세 표시
        conditions_parts = []
        if step.conditions:
            conditions_parts.append(f"조건: {step.conditions}")
        if hasattr(step, 'transform_name_en') and step.transform_name_en:
            conditions_parts.append(f"({step.transform_name_en})")
        self._lbl_conditions.setText(" ".join(conditions_parts))

        conf_pct = step.confidence * 100
        self._lbl_confidence.setText(f"신뢰도: {conf_pct:.0f}%")
        self._btn_mechanism.setEnabled(True)
        self._update_gemini_button()

    def _on_mechanism_click(self):
        if self._step:
            self.mechanism_requested.emit(self._step)

    def _on_gemini_click(self):
        """Gemini AI로 현재 단계 또는 전체 경로 분석을 요청합니다."""
        # Emit step (may be None for route-level analysis)
        self.gemini_requested.emit(self._step)


# ═══════════════════════════════════════════════════════════
# 경로 실행 가능성 비교 테이블 위젯
# ═══════════════════════════════════════════════════════════
class FeasibilityComparisonWidget(QFrame):
    """합성 경로들의 실행 가능성을 비교하는 테이블 위젯.

    학생이 어떤 경로가 자신의 실험실에서 실현 가능한지 한눈에 비교할 수 있도록
    ★/☆ 별점 + 점수 + 실험실 등급을 표시합니다.
    """

    route_selected = pyqtSignal(int)  # 경로 인덱스 선택 시그널

    def __init__(self, parent=None):
        super().__init__(parent)
        self._feasibility_data: List[RouteFeasibility] = []
        self._routes: List[SynthesisRoute] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 헤더
        header_layout = QHBoxLayout()
        lbl_title = QLabel("경로 비교 (실행 가능성 순위)")
        lbl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #E0E0E0;")
        header_layout.addWidget(lbl_title)

        # 범례
        legend = QLabel("★=우수 ☆=부족 | 추천도 높을수록 실현 가능")
        legend.setFont(QFont("Segoe UI", 8))
        legend.setStyleSheet("color: #9E9E9E;")
        header_layout.addStretch()
        header_layout.addWidget(legend)
        layout.addLayout(header_layout)

        # 테이블
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "경로", "단계 수", "온도", "시약 접근성", "안전성", "추천도", "실험실 등급", "예상 수율"
        ])
        self._table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background: #2A2C36; color: #90CAF9; "
            "border: 1px solid #444; padding: 4px; font-weight: bold; font-size: 9pt; }"
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("""
            QTableWidget {
                background: #1E2028; color: #E0E0E0; border: 1px solid #444;
                border-radius: 6px; gridline-color: #333;
                font-size: 9pt;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background: rgba(66, 165, 245, 50);
            }
            QTableWidget::item:alternate {
                background: #252830;
            }
        """)

        # 열 크기 설정
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 55)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 60)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 80)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 70)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(6, 100)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(7, 70)

        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

        # 선택된 경로 상세 (하단)
        self._detail_label = QLabel("")
        self._detail_label.setFont(QFont("Segoe UI", 9))
        self._detail_label.setStyleSheet("color: #B0BEC5; padding: 4px;")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)

    def update_data(self, routes: List[SynthesisRoute],
                    feasibility_data: List[RouteFeasibility]):
        """경로 데이터와 실행 가능성 점수를 업데이트합니다."""
        self._routes = routes
        self._feasibility_data = feasibility_data
        self._populate_table()

    def _populate_table(self):
        """테이블에 데이터를 채웁니다."""
        self._table.setRowCount(0)
        if not self._feasibility_data:
            return

        # 추천도(overall_score) 내림차순으로 정렬된 인덱스
        sorted_indices = sorted(
            range(len(self._feasibility_data)),
            key=lambda i: self._feasibility_data[i].overall_score,
            reverse=True
        )

        self._table.setRowCount(len(sorted_indices))

        for row, idx in enumerate(sorted_indices):
            f = self._feasibility_data[idx]
            route = self._routes[idx]

            # 경로 번호 (원래 인덱스 + 1)
            item_route = QTableWidgetItem(f"경로 {idx + 1}")
            item_route.setData(Qt.ItemDataRole.UserRole, idx)  # 원래 인덱스 저장
            item_route.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, item_route)

            # 단계 수
            step_text = f"{route.total_steps}단계" if route.total_steps > 0 else "직접 가용"
            item_steps = QTableWidgetItem(step_text)
            item_steps.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, item_steps)

            # 온도 (별점)
            temp_text = self._score_to_temp_label(f.temperature_score)
            item_temp = QTableWidgetItem(temp_text)
            item_temp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, item_temp)

            # 시약 접근성 (별점)
            reagent_stars = self._score_to_stars(f.reagent_availability)
            item_reagent = QTableWidgetItem(reagent_stars)
            item_reagent.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, item_reagent)

            # 안전성 (별점)
            safety_stars = self._score_to_stars(f.safety_score)
            item_safety = QTableWidgetItem(safety_stars)
            item_safety.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 4, item_safety)

            # 추천도 (숫자/100)
            score_text = f"{f.overall_score:.0f}/100"
            item_score = QTableWidgetItem(score_text)
            item_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 색상 코딩
            if f.overall_score >= 80:
                item_score.setForeground(QColor(102, 187, 106))  # 초록
            elif f.overall_score >= 60:
                item_score.setForeground(QColor(255, 183, 77))   # 주황
            elif f.overall_score >= 40:
                item_score.setForeground(QColor(255, 152, 0))    # 진주황
            else:
                item_score.setForeground(QColor(244, 67, 54))    # 빨강
            item_score.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self._table.setItem(row, 5, item_score)

            # 실험실 등급
            item_lab = QTableWidgetItem(f.lab_level)
            item_lab.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 등급별 색상
            lab_colors = {
                "고등학교": QColor(102, 187, 106),
                "대학교": QColor(66, 165, 245),
                "연구소": QColor(255, 183, 77),
                "산업체": QColor(244, 67, 54),
            }
            item_lab.setForeground(lab_colors.get(f.lab_level, QColor(200, 200, 200)))
            self._table.setItem(row, 6, item_lab)

            # 예상 수율
            yield_map = {"high": "높음", "medium": "보통", "low": "낮음"}
            item_yield = QTableWidgetItem(yield_map.get(f.estimated_yield, f.estimated_yield))
            item_yield.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 7, item_yield)

        # 첫 번째 행 자동 선택
        if self._table.rowCount() > 0:
            self._table.selectRow(0)

    @staticmethod
    def _score_to_stars(score: float) -> str:
        """점수(0-100)를 ★/☆ 5점 별점으로 변환합니다."""
        n_full = int(score / 20)
        n_full = max(0, min(5, n_full))
        return "★" * n_full + "☆" * (5 - n_full)

    @staticmethod
    def _score_to_temp_label(score: float) -> str:
        """온도 점수를 사람이 읽기 쉬운 라벨로 변환합니다."""
        if score >= 90:
            return "상온"
        elif score >= 70:
            return "0~80°C"
        elif score >= 50:
            return "환류"
        elif score >= 30:
            return "극한 온도"
        else:
            return ">300°C"

    def _on_cell_clicked(self, row: int, _col: int):
        """테이블 행 클릭 → 경로 선택 시그널 발신 + 상세 표시"""
        item = self._table.item(row, 0)
        if item is None:
            return
        route_idx = item.data(Qt.ItemDataRole.UserRole)
        if route_idx is None:
            return

        # 상세 라벨 업데이트
        if route_idx < len(self._feasibility_data):
            f = self._feasibility_data[route_idx]
            self._detail_label.setText(f.summary)

        self.route_selected.emit(route_idx)

    def show_no_routes_message(self, target_smiles: str = ""):
        """[Rule M] 경로 0건 시 사용자에게 명시적 실패 메시지를 테이블에 표시.
        Silent failure(setRowCount(0) 후 아무것도 없음) 금지."""
        self._table.setRowCount(1)
        # span all 8 columns with a single explanatory cell
        msg = (
            "경로 없음 — 이 분자는 SMARTS/ASKCOS DB에 없습니다. "
            "이론적 합성 가능하나 시판 시약 정보 필요. Gemini AI 분석을 이용하세요."
        )
        item = QTableWidgetItem(msg)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item.setForeground(QColor(255, 183, 77))  # 경고 주황색
        item.setFont(QFont("Segoe UI", 9))
        self._table.setItem(0, 0, item)
        # 나머지 열 빈 셀로 채워 레이아웃 유지
        for col in range(1, 8):
            self._table.setItem(0, col, QTableWidgetItem(""))
        self._detail_label.setText(
            f"합성 경로 탐색 실패: {target_smiles[:60]}")
        logger.warning(
            "[FeasibilityComparisonWidget] 경로 0건 안내 표시: smiles=%r", target_smiles)


# ═══════════════════════════════════════════════════════════
# 메인 합성 팝업
# ═══════════════════════════════════════════════════════════
class SynthesisPopup(QDialog):
    """합성 경로 분석 팝업 다이얼로그.

    Args:
        target_smiles: 목표 분자 SMILES
        target_name: 목표 분자 이름 (표시용)
        parent_smiles: 모분자 SMILES (Option B 활성화용).
                       None이면 표준 역합성 (시중 시약 → 목표) 전용.
                       문자열이면 출발물질 선택 토글 표시.
        parent_name: 모분자 이름 (표시용)
        parent: Qt parent widget
    """

    def __init__(self, target_smiles: str, target_name: str = "",
                 parent_smiles: Optional[str] = None, parent_name: str = "",
                 parent=None):
        super().__init__(parent)
        self._target_smi = target_smiles
        self._target_name = target_name or target_smiles
        self._parent_smi = parent_smiles  # 모분자 SMILES (Option B)
        self._parent_name = parent_name
        self._routes: List[SynthesisRoute] = []
        self._feasibility_data: List[RouteFeasibility] = []
        self._selected_route_idx = -1
        self._selected_step_idx = -1
        self._thread: Optional[RetrosynthesisThread] = None
        self._route_cards: List[RouteCardWidget] = []
        self._use_parent_as_starting = False  # True = Option B
        self._active_reaction_animation_popup = None
        self._engine_status_thread: Optional[_EngineStatusThread] = None  # [M923]

        self.setWindowTitle(f"합성 경로 분석 — {self._target_name}")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_COLORS['bg'].name()};
            }}
        """)

        self._init_ui()
        self._start_search()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ═══ 좌측 패널 (240px) ═══
        left_panel = QWidget()
        left_panel.setFixedWidth(260)
        left_panel.setStyleSheet(f"background: {_COLORS['panel'].name()}; border-radius: 10px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)

        # 타겟 분자 정보
        lbl_target_header = QLabel("🎯 타겟 분자")
        lbl_target_header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_target_header.setStyleSheet("color: #F44336;")
        left_layout.addWidget(lbl_target_header)

        # 타겟 2D 이미지
        self._target_img_label = QLabel()
        self._target_img_label.setFixedSize(230, 150)
        self._target_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._target_img_label.setStyleSheet("background: white; border-radius: 8px;")
        self._render_target_image()
        left_layout.addWidget(self._target_img_label)

        lbl_smi = QLabel(self._target_smi if len(self._target_smi) <= 40
                         else self._target_smi[:37] + "...")
        lbl_smi.setFont(QFont("Consolas", 8))
        lbl_smi.setStyleSheet("color: #90CAF9;")
        lbl_smi.setWordWrap(True)
        left_layout.addWidget(lbl_smi)

        # ── 합성 출발물질 선택 토글 (Option A/B) ──
        if self._parent_smi:
            from PyQt6.QtWidgets import QComboBox
            starting_group = QGroupBox("합성 출발물질 선택")
            starting_group.setStyleSheet("""
                QGroupBox {
                    color: #E0E0E0; border: 1px solid #555;
                    border-radius: 6px; margin-top: 6px; padding-top: 12px;
                    font-size: 9pt; font-weight: bold;
                }
                QGroupBox::title { subcontrol-position: top left; left: 8px; }
            """)
            sg_layout = QVBoxLayout(starting_group)
            sg_layout.setContentsMargins(6, 4, 6, 4)
            sg_layout.setSpacing(4)

            self._starting_combo = QComboBox()
            self._starting_combo.addItem("시중 시약 (표준 역합성)")
            parent_label = self._parent_name or self._parent_smi[:30]
            self._starting_combo.addItem(f"원래 구조체: {parent_label}")
            self._starting_combo.setStyleSheet("""
                QComboBox {
                    background: #333; color: #E0E0E0; border: 1px solid #555;
                    border-radius: 4px; padding: 4px 8px; font-size: 8pt;
                }
                QComboBox::drop-down { border: none; }
                QComboBox QAbstractItemView {
                    background: #2A2C36; color: #E0E0E0;
                    selection-background-color: #42A5F5;
                }
            """)
            self._starting_combo.currentIndexChanged.connect(self._on_starting_material_changed)
            sg_layout.addWidget(self._starting_combo)

            hint_lbl = QLabel("원래 구조체: 정제된 모분자에서\n유도체까지 최소 단계 합성")
            hint_lbl.setFont(QFont("Segoe UI", 7))
            hint_lbl.setStyleSheet("color: #9E9E9E;")
            hint_lbl.setWordWrap(True)
            sg_layout.addWidget(hint_lbl)

            left_layout.addWidget(starting_group)

        # 구분선
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #555;")
        left_layout.addWidget(sep)

        # 경로 목록 헤더
        lbl_routes = QLabel("📋 합성 경로 목록")
        lbl_routes.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_routes.setStyleSheet("color: #E0E0E0;")
        left_layout.addWidget(lbl_routes)

        # 진행 표시
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # 무한 진행
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setStyleSheet("""
            QProgressBar { background: #333; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #42A5F5; border-radius: 2px; }
        """)
        left_layout.addWidget(self._progress_bar)

        self._lbl_status = QLabel("검색 중...")
        self._lbl_status.setFont(QFont("Segoe UI", 8))
        self._lbl_status.setStyleSheet("color: #9E9E9E;")
        left_layout.addWidget(self._lbl_status)

        # [M723-5 FIX] F6-5 item21 엔진 연결 현황 표시 — Rule M: silent failure 금지
        # 사용자 직접 인용: "askcos나 orca 등등 연구실급으로 이론적 정합성이 높은
        #  외부 및 오픈소스 엔진들이 제대로 연결되지 않은 것 같은데, 전체적인 코드 연결
        #  및 실 연산 현황 전체 재점검해라"
        # 학술 인용: Coley 2019 ACS Cent. Sci. 5:1572 (ASKCOS 68 templates)
        self._lbl_engine_status = QLabel()
        self._lbl_engine_status.setFont(QFont("Segoe UI", 7))
        self._lbl_engine_status.setWordWrap(True)
        self._lbl_engine_status.setStyleSheet(
            "color: #78909C; background: #1A1C24; "
            "border-radius: 3px; padding: 3px 5px;"
        )
        # [M849] init시 즉시 호출 대신 100ms 후 비동기 실행 (GUI 즉시 표시 보장)
        # ASKCOS is_available() 네트워크 요청 최대 5s -> 팝업 오픈 지연 방지
        QTimer.singleShot(100, self._update_engine_status_label)  # [MAGIC:100] init 후 100ms 딜레이
        left_layout.addWidget(self._lbl_engine_status)

        # [M849 / Rule GG] SIMULATION_MODE 배너 — 외부엔진 미연결 시 노란 경고
        # "fallback/mock 사용시 노랑 배너 + 결과탭(휴리스틱) + 워터마크 의무"
        self._simulation_banner = QLabel()
        self._simulation_banner.setWordWrap(True)
        self._simulation_banner.setStyleSheet(
            "QLabel { background-color: #F57F17; color: #000; "
            "font-weight: bold; font-size: 9pt; "
            "border-radius: 4px; padding: 4px 6px; }"
        )
        self._simulation_banner.hide()
        left_layout.addWidget(self._simulation_banner)

        # 경로 카드 스크롤 영역
        self._routes_scroll = QScrollArea()
        self._routes_scroll.setWidgetResizable(True)
        self._routes_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 6px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #555; border-radius: 3px; min-height: 20px;
            }
        """)
        self._routes_container = QWidget()
        self._routes_layout = QVBoxLayout(self._routes_container)
        self._routes_layout.setContentsMargins(0, 0, 0, 0)
        self._routes_layout.setSpacing(4)
        self._routes_layout.addStretch()
        self._routes_scroll.setWidget(self._routes_container)
        left_layout.addWidget(self._routes_scroll, 1)

        # [FIX-D] 단계별 설명 패널 (왼쪽 패널 하단)
        lbl_steps_header = QLabel("단계별 설명")
        lbl_steps_header.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl_steps_header.setStyleSheet("color: #90CAF9;")
        left_layout.addWidget(lbl_steps_header)

        self._left_steps_text = QTextEdit()
        self._left_steps_text.setReadOnly(True)
        self._left_steps_text.setMaximumHeight(160)
        self._left_steps_text.setStyleSheet("""
            QTextEdit {
                background: #1E2028; color: #B0BEC5;
                border: 1px solid #444; border-radius: 6px;
                font-size: 8pt; padding: 4px;
            }
        """)
        self._left_steps_text.setPlaceholderText(
            "경로 선택 시 단계별 설명이 여기 표시됩니다.")
        left_layout.addWidget(self._left_steps_text)

        # PDF 내보내기 버튼
        self._btn_export_pdf = QPushButton("합성 경로 PDF 내보내기")
        self._btn_export_pdf.setFixedHeight(36)
        self._btn_export_pdf.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32; color: white; border-radius: 8px;
                font-weight: bold; font-size: 9pt;
            }
            QPushButton:hover { background-color: #388E3C; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._btn_export_pdf.setEnabled(False)
        self._btn_export_pdf.setToolTip("선택된 합성 경로를 PDF 파일로 내보냅니다")
        self._btn_export_pdf.clicked.connect(self._on_export_pdf)
        left_layout.addWidget(self._btn_export_pdf)

        # 3D 반응 애니메이션 버튼
        self._btn_reaction_anim = QPushButton("\U0001f3ac 3D 반응 애니메이션")
        self._btn_reaction_anim.setObjectName("synthesis_reaction_animation_btn")
        self._btn_reaction_anim.setAccessibleName("3D reaction animation")
        self._btn_reaction_anim.setFixedHeight(36)
        self._btn_reaction_anim.setStyleSheet("""
            QPushButton {
                background-color: #1565C0; color: white; border-radius: 8px;
                font-weight: bold; font-size: 9pt;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._btn_reaction_anim.setEnabled(False)
        self._btn_reaction_anim.setToolTip("선택된 합성 단계의 3D 반응 메커니즘 애니메이션을 봅니다")
        self._btn_reaction_anim.clicked.connect(self._on_reaction_animation)
        left_layout.addWidget(self._btn_reaction_anim)

        main_layout.addWidget(left_panel)

        # ═══ 우측 패널 (비교 테이블 탭 + 플로차트 + 상세) ═══
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setStyleSheet("""
            QSplitter::handle { background: #333; height: 3px; }
        """)

        # 탭 위젯: 경로 비교 테이블 + 플로차트
        self._right_tabs = QTabWidget()
        self._right_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444; border-radius: 6px;
                background: #1E2028;
            }
            QTabBar::tab {
                background: #2A2C36; color: #B0BEC5;
                padding: 6px 14px; border: 1px solid #444;
                border-bottom: none; border-top-left-radius: 6px;
                border-top-right-radius: 6px; margin-right: 2px;
                font-size: 9pt;
            }
            QTabBar::tab:selected {
                background: #1E2028; color: #42A5F5;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background: #353840;
            }
        """)

        # 탭 1: 경로 비교 테이블
        self._feasibility_widget = FeasibilityComparisonWidget()
        self._feasibility_widget.route_selected.connect(self._on_route_selected)
        self._right_tabs.addTab(self._feasibility_widget, "경로 비교 (실행 가능성)")

        # 탭 2: 플로차트 상세 뷰
        flowchart_scroll = QScrollArea()
        flowchart_scroll.setWidgetResizable(True)
        flowchart_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 8px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #555; border-radius: 4px; min-height: 30px;
            }
        """)
        self._flowchart = RouteFlowchartWidget()
        self._flowchart.step_clicked.connect(self._on_step_clicked)
        flowchart_scroll.setWidget(self._flowchart)
        self._right_tabs.addTab(flowchart_scroll, "플로차트 (반응 경로)")

        # 탭 3: 단계별 메커니즘 상세 (step descriptions + intermediates)
        self._steps_detail_text = QTextEdit()
        self._steps_detail_text.setReadOnly(True)
        self._steps_detail_text.setStyleSheet("""
            QTextEdit {
                background: #1E2028; color: #E0E0E0;
                border: none; font-size: 10pt;
                padding: 10px;
            }
        """)
        self._steps_detail_text.setPlaceholderText(
            "경로를 선택하면 단계별 반응 메커니즘과 조건이 표시됩니다.")
        self._right_tabs.addTab(self._steps_detail_text,
                                "단계별 메커니즘 상세")

        # 탭 4: M646_LITE_PARITY — Reactome 경로 분석 (router src/app 통합)
        # 학술 인용 (Rule NN — academic_integrity_check.py / FP-28 차단):
        #   Fabregat, A. et al. (2018) The Reactome Pathway Knowledgebase.
        #     Nucleic Acids Res. 46(D1): D649-D655.
        #   Jassal, B. et al. (2020) The reactome pathway knowledgebase.
        #     Nucleic Acids Res. 48(D1): D498-D503.
        # Rule Y: 1:1 router 이식 — ext_live._reactome_get_pathways() 동일 URL.
        self._build_tab_reactome()

        right_splitter.addWidget(self._right_tabs)

        # 하단: 단계 상세
        self._step_detail = StepDetailPanel()
        self._step_detail.mechanism_requested.connect(self._open_mechanism)
        self._step_detail.gemini_requested.connect(self._on_gemini_analyze)
        self._step_detail.setFixedHeight(180)
        right_splitter.addWidget(self._step_detail)

        right_splitter.setSizes([500, 180])
        main_layout.addWidget(right_splitter, 1)

    # ────────────────────────────────────────────────────────────────────
    # M646_LITE_PARITY: Reactome router src/app 통합 (Q-N25)
    # ────────────────────────────────────────────────────────────────────
    def _build_tab_reactome(self):
        """Reactome 생화학 경로 검색 탭 — UniProt → 경로 리스트.

        학술 인용 (Rule NN — academic_integrity_check.py / FP-28 차단):
          Fabregat, A. et al. (2018) NAR 46(D1): D649-D655.
          Jassal, B. et al. (2020) NAR 48(D1): D498-D503.

        Rule M: silent 금지. Rule N: 응답 list 가드.
        Rule Y: 1:1 router 이식 — ext_live._reactome_get_pathways() URL 동일.
        """
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # 학술 인용 (Rule NN: 항상 표시)
        lbl_citation = QLabel(
            "<i>참고: Fabregat et al. NAR 2018;46:D649 — Reactome pathway DB. "
            "Jassal et al. NAR 2020;48:D498 — Reactome 2020 update.</i>"
        )
        lbl_citation.setWordWrap(True)
        lbl_citation.setStyleSheet("color: #AAA; font-size: 9px; padding: 2px 8px;")
        vbox.addWidget(lbl_citation)

        # 안내문 (FP-15 — 외부 API 의존성 명시)
        lbl_info = QLabel(
            "<b>외부 API:</b> Reactome ContentService (reactome.org). "
            "UniProt ID 입력 → 해당 단백질이 참여하는 생화학 경로 리스트.<br>"
            "네트워크 미연결 시 SIMULATION_MODE 표시."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(
            "QLabel { padding: 8px; background-color: #2A2D36; color: #DDD; "
            "border: 1px solid #444; border-radius: 4px; font-size: 11px; }"
        )
        vbox.addWidget(lbl_info)

        # 검색 폼
        grp_search = QGroupBox("UniProt ID 검색")
        grp_search.setStyleSheet(
            "QGroupBox { color: #DDD; font-size: 10pt; }"
        )
        form_layout = QHBoxLayout(grp_search)
        form_layout.addWidget(QLabel("UniProt:"))
        self._reactome_uniprot_input = QLineEdit()
        self._reactome_uniprot_input.setPlaceholderText(
            "예: P00533 (EGFR), P00734 (Thrombin), P09874 (PARP1)"
        )
        self._reactome_uniprot_input.setStyleSheet(
            "QLineEdit { background: #1E2028; color: #E0E0E0; "
            "border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }"
        )
        form_layout.addWidget(self._reactome_uniprot_input)

        self._btn_reactome_search = QPushButton("Reactome 검색")
        self._btn_reactome_search.setStyleSheet(
            "QPushButton { background-color: #16a085; color: white; "
            "font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
        )
        self._btn_reactome_search.clicked.connect(self._on_reactome_search)
        form_layout.addWidget(self._btn_reactome_search)
        vbox.addWidget(grp_search)

        # 결과 표
        self._tbl_reactome = QTableWidget()
        self._tbl_reactome.setColumnCount(3)
        self._tbl_reactome.setHorizontalHeaderLabels([
            "Stable ID", "Display Name", "Species",
        ])
        self._tbl_reactome.horizontalHeader().setStretchLastSection(True)
        self._tbl_reactome.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._tbl_reactome.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._tbl_reactome.setStyleSheet(
            "QTableWidget { background: #1E2028; color: #E0E0E0; "
            "gridline-color: #444; }"
            "QHeaderView::section { background: #2A2D36; color: #FFF; "
            "padding: 4px; }"
        )
        # 학술 인용 툴팁 (Rule NN UI 명시)
        self._tbl_reactome.setToolTip(
            "Reactome pathway DB (Fabregat et al. NAR 2018;46:D649). "
            "더블클릭하면 Reactome 페이지를 엽니다."
        )
        self._tbl_reactome.doubleClicked.connect(
            self._on_reactome_row_doubleclick
        )
        vbox.addWidget(self._tbl_reactome, 1)

        # 상태 라벨 (Rule M: 명시적 피드백)
        self._lbl_reactome_status = QLabel("준비됨")
        self._lbl_reactome_status.setStyleSheet(
            "color: #AAA; font-size: 9px; padding: 4px 8px;"
        )
        vbox.addWidget(self._lbl_reactome_status)

        self._right_tabs.addTab(tab, "Reactome 경로")

    def _on_reactome_search(self):
        """Reactome ContentService API 호출 — Fabregat 2018 NAR 46:D649.

        Rule M: silent 금지. Rule N: 응답 list 가드.
        Rule Y: ext_live._reactome_get_pathways() 와 1:1 동일.
        """
        uid_raw = self._reactome_uniprot_input.text().strip()
        # UniProt 정규식 가드 (Rule N) — 6자리 영숫자
        import re as _re
        if not _re.match(r"^[OPQA-Z][0-9][A-Z0-9]{3}[0-9]$", uid_raw, _re.IGNORECASE):
            self._lbl_reactome_status.setText(
                "<span style='color:#e74c3c;'>UniProt ID 형식 오류 — 6자리 영숫자 (예: P00533)</span>"
            )
            QMessageBox.warning(
                self, "Reactome",
                f"UniProt ID 형식이 올바르지 않습니다: '{uid_raw}'\n예: P00533, P00734, P09874"
            )
            return

        self._lbl_reactome_status.setText(
            f"<i>Reactome 검색 중... ({uid_raw.upper()})</i>"
        )
        self._btn_reactome_search.setEnabled(False)
        try:
            results = self._reactome_query(uid_raw.upper())
        finally:
            self._btn_reactome_search.setEnabled(True)

        # Rule N: list 가드
        if not isinstance(results, list):  # Rule N
            logger.warning("[Reactome] 예상치 못한 응답 타입 %s", type(results).__name__)
            results = []

        # _simulation_mode 체크 (Rule GG)
        sim_flag = False
        sim_reason = ""
        if results and isinstance(results[0], dict):
            sim_flag = bool(results[0].get("_simulation_mode", False))
            sim_reason = str(results[0].get("_reason", ""))
        if sim_flag:
            self._lbl_reactome_status.setText(
                f"<span style='color:#e67e22;'>"
                f"<b>SIMULATION_MODE</b> — {sim_reason}</span>"
            )
            self._tbl_reactome.setRowCount(0)
            return

        # 결과 표 채우기 (외부 데이터 dict 가드 — Rule N)
        self._tbl_reactome.setRowCount(len(results))
        for i, item in enumerate(results):
            if not isinstance(item, dict):  # Rule N
                continue
            stable_id = str(item.get("stId") or item.get("stableId") or "?")
            display_name = str(item.get("displayName") or item.get("name") or "")
            species_obj = item.get("species", {})
            species = ""
            if isinstance(species_obj, dict):  # Rule N
                species = str(species_obj.get("displayName", "") or "")
            elif isinstance(species_obj, list) and species_obj:
                first = species_obj[0]
                if isinstance(first, dict):
                    species = str(first.get("displayName", "") or "")
                elif isinstance(first, str):
                    species = first

            self._tbl_reactome.setItem(i, 0, QTableWidgetItem(stable_id))
            self._tbl_reactome.setItem(i, 1, QTableWidgetItem(display_name))
            self._tbl_reactome.setItem(i, 2, QTableWidgetItem(species))

        if not results:
            self._lbl_reactome_status.setText(
                f"<span style='color:#7f8c8d;'>경로 0건 — UniProt {uid_raw.upper()} 매칭 없음</span>"
            )
        else:
            self._lbl_reactome_status.setText(
                f"<span style='color:#27ae60;'>"
                f"<b>{len(results)}건 경로</b> — Fabregat et al. NAR 2018;46:D649</span>"
            )

    def _reactome_query(self, uniprot_id: str) -> list:
        """Reactome ContentService API 직접 호출 — 1:1 ext_live 이식.

        Rule M / Rule N / Rule Y 준수.
        """
        try:
            import requests as _requests
        except ImportError as e:
            logger.warning("[Reactome] requests 미설치: %s", e)
            return [{
                "_simulation_mode": True,
                "_reason": "requests 라이브러리 없음 — 외부 API 호출 불가",
            }]

        if not isinstance(uniprot_id, str) or not uniprot_id.strip():  # Rule N
            return [{"_simulation_mode": True, "_reason": "UniProt ID 비어 있음"}]

        # M646_LITE_PARITY 검증: Reactome ContentService /mapping/UniProt/{id}/pathways
        # 이 endpoint 는 species=9606(Homo sapiens) 인자 함께 사용 시 안정적으로 작동.
        # raw probe (2026-04-28): /pathways/low/entity/{id}/allForms 는 HTTP 404 반환,
        #                         /mapping/UniProt/{id}/pathways?species=9606 은 200 OK + JSON list.
        # M712/REACTOME-SSL-001: https://reactome.org → SSL handshake 오류 발생 환경 존재.
        #   1차 HTTPS 시도 → SSLError 발생 시 HTTP fallback 자동 전환 (Rule M: silent 금지).
        # [MAGIC: 30s] Reactome API 응답 시간 max
        # [MAGIC: 9606] Homo sapiens NCBI taxonomy ID (Reactome 표준)
        _uid_upper = uniprot_id.strip().upper()
        _url_https = (
            f"https://reactome.org/ContentService/data/mapping/UniProt/"
            f"{_uid_upper}/pathways?species=9606"
        )
        _url_http = (
            f"http://reactome.org/ContentService/data/mapping/UniProt/"
            f"{_uid_upper}/pathways?species=9606"
        )
        url = _url_https  # 초기값 — 에러 메시지용
        resp = None
        for _attempt_url in (_url_https, _url_http):
            url = _attempt_url
            try:
                resp = _requests.get(  # type: ignore[union-attr]
                    _attempt_url,
                    headers={"User-Agent": "ChemGrid/M712",
                             "Accept": "application/json"},
                    timeout=30,
                    verify=(_attempt_url.startswith("https")),  # [M712] HTTP fallback 시 verify 불필요
                )
                break  # 성공 시 loop 탈출
            except _requests.exceptions.Timeout:  # type: ignore[union-attr]
                logger.warning("[Reactome] timeout @ %s", _attempt_url[:80])
                return [{"_simulation_mode": True, "_reason": "Reactome API timeout (30s)"}]
            except Exception as e:
                _is_ssl = "ssl" in type(e).__name__.lower() or "ssl" in str(e).lower()
                if _is_ssl and _attempt_url == _url_https:
                    # SSL 오류 → HTTP fallback 시도 (Rule M: 사용자에게 fallback 안내)
                    logger.warning(
                        "[Reactome] HTTPS SSL 오류 → HTTP fallback 시도: %s", e
                    )
                    continue
                logger.warning("[Reactome] 네트워크 오류 %s: %s", type(e).__name__, e)
                return [{"_simulation_mode": True,
                          "_reason": f"network: {type(e).__name__}: {e}"}]

        if resp is None:
            logger.warning("[Reactome] HTTPS+HTTP 모두 실패")
            return [{"_simulation_mode": True, "_reason": "Reactome HTTPS+HTTP 모두 실패"}]

        if not resp.ok:
            logger.warning("[Reactome] HTTP %d", resp.status_code)
            return [{"_simulation_mode": True,
                      "_reason": f"HTTP {resp.status_code}"}]
        try:
            data = resp.json()
        except Exception as e:
            logger.warning("[Reactome] JSON 파싱 실패: %s", e)
            return [{"_simulation_mode": True, "_reason": f"json: {e}"}]

        # Reactome 은 list 직접 반환
        if isinstance(data, list):  # Rule N
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):  # 가끔 단일 dict 반환
            return [data]
        return []

    def _on_reactome_row_doubleclick(self, idx):
        """Reactome 행 더블클릭 → 브라우저 외부 열기."""
        row = idx.row()
        if row < 0:
            return
        item = self._tbl_reactome.item(row, 0)  # Stable ID 열
        if item is None:
            return
        stable_id = item.text().strip()
        if not stable_id or stable_id == "?":
            return
        try:
            from PyQt6.QtCore import QUrl as _QUrl
            from PyQt6.QtGui import QDesktopServices as _QDS
            _QDS.openUrl(_QUrl(f"https://reactome.org/PathwayBrowser/#/{stable_id}"))
        except Exception as e:
            logger.warning("[Reactome] URL 열기 실패: %s", e)

    def _render_target_image(self):
        """타겟 분자 이미지 렌더링 — ChemGrid Theory 레이어 스타일 (ESP cloud + 결합각).

        [B5-1 FIX] RDKit flat 2D / QPainter 골격식 대신 TheoryRenderer 사용.
        ChemicalAnalyzer.analyze() -> TheoryRenderer.render() 경로로
        메인 캔버스 Theory 레이어와 동일한 시각화 제공.
        폴백: TheoryRenderer 실패 시 QPainter 골격식으로 복귀 (Rule M silent failure 금지).
        """
        if not RDKIT_AVAILABLE:
            self._target_img_label.setText("RDKit 미설치")
            return

        # [Rule L] SMILES 파싱 + None 체크 필수
        mol = Chem.MolFromSmiles(self._target_smi)
        if mol is None:
            logger.warning("[_render_target_image] Invalid SMILES: %s", self._target_smi)
            self._target_img_label.setText("유효하지 않은 SMILES")
            return

        W, H = 230, 150  # Magic: _target_img_label 고정 크기와 일치

        # 1차 시도: TheoryRenderer (ChemGrid Theory layer 스타일)
        try:
            from rdkit.Chem import AllChem
            from analyzer import ChemicalAnalyzer
            from layer_logic import TheoryRenderer

            # SMILES -> atoms/bonds (ChemGrid 좌표계)
            mol_2d = Chem.RemoveHs(mol)
            AllChem.Compute2DCoords(mol_2d)
            try:
                Chem.Kekulize(mol_2d, clearAromaticFlags=False)
            except Exception as _ke:
                logger.warning("[_render_target_image] Kekulize skip: %s", _ke)

            conf = mol_2d.GetConformer()
            SCALE = 28.0  # Magic: popup 패널 230x150 에 맞게 조정된 스케일
            cx_m = sum(conf.GetAtomPosition(i).x for i in range(mol_2d.GetNumAtoms())) / max(mol_2d.GetNumAtoms(), 1)
            cy_m = sum(conf.GetAtomPosition(i).y for i in range(mol_2d.GetNumAtoms())) / max(mol_2d.GetNumAtoms(), 1)

            atoms: dict = {}
            idx_to_key: dict = {}
            for i in range(mol_2d.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                atom = mol_2d.GetAtomWithIdx(i)
                sym = "" if atom.GetSymbol() == "C" else atom.GetSymbol()  # Rule I: Carbon = ''
                x = round(W / 2 + (pos.x - cx_m) * SCALE, 2)
                y = round(H / 2 - (pos.y - cy_m) * SCALE, 2)
                key = (x, y)
                offset = 0
                while key in atoms:
                    offset += 1
                    key = (round(x + offset * SCALE, 2), y)
                entry: dict = {"main": sym, "attach": {}}
                fc = atom.GetFormalCharge()
                if fc != 0:
                    entry["formal_charge"] = fc
                    entry["charge"] = "+" if fc > 0 else "-"
                atoms[key] = entry
                idx_to_key[i] = key

            bonds: dict = {}
            for bond in mol_2d.GetBonds():
                bi, bj = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                k1, k2 = idx_to_key.get(bi), idx_to_key.get(bj)
                if k1 is not None and k2 is not None:
                    bt = bond.GetBondTypeAsDouble()
                    bonds[(k1, k2)] = 2 if bt >= 1.75 else 1

            # ChemicalAnalyzer (theory_data coords 생성)
            analysis = ChemicalAnalyzer().analyze(atoms, bonds, self._target_smi)
            if not isinstance(analysis, dict):
                raise ValueError(f"analyze() returned {type(analysis).__name__}")

            # TheoryRenderer -> QPixmap
            pixmap = QPixmap(W, H)
            pixmap.fill(QColor(255, 255, 255))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            TheoryRenderer.render(painter, atoms, bonds, analysis, set(), set())
            painter.end()
            self._target_img_label.setPixmap(pixmap)
            return  # 성공 -- 조기 리턴

        except Exception as e:
            logger.warning(
                "[_render_target_image] TheoryRenderer failed, falling back to skeletal: %s", e
            )

        # 폴백: QPainter 골격식 렌더링 (Rule M: silent failure 금지, 폴백 제공)
        try:
            pixmap = QPixmap(W, H)
            pixmap.fill(QColor(255, 255, 255))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = QRectF(0, 0, W, H)
            RouteFlowchartWidget._render_skeletal(
                painter, [self._target_smi], rect,
                RouteFlowchartWidget._HETERO)
            painter.end()
            self._target_img_label.setPixmap(pixmap)
        except Exception as e2:
            logger.warning("[_render_target_image] Fallback skeletal also failed: %s", e2)
            self._target_img_label.setText(f"렌더링 실패: {e2}")

    def _on_starting_material_changed(self, index: int):
        """출발물질 선택 변경 시 재검색."""
        self._use_parent_as_starting = (index == 1)  # index 1 = 원래 구조체
        # 기존 결과 초기화 후 재검색
        self._routes.clear()
        self._selected_route_idx = -1
        self._selected_step_idx = -1
        # 경로 카드 정리
        for card in self._route_cards:
            card.deleteLater()
        self._route_cards.clear()
        self._flowchart.set_route(None)
        self._progress_bar.show()
        self._progress_bar.setRange(0, 0)
        self._lbl_status.setText("재검색 중...")
        self._lbl_status.setStyleSheet("color: #9E9E9E;")
        self._start_search()

    def _update_engine_status_label(self) -> None:
        """[M923 FIX] 엔진 연결 현황 라벨 갱신 — 즉시 "확인 중..." 표시 후 백그라운드 체크.

        격분 #15 근본 원인: 이전 구현이 GUI 스레드에서 ASKCOS is_available() 직접 호출 →
        최대 ~16s 네트워크 대기 → 합성경로탭 완전 차단.
        수정: _EngineStatusThread(QThread)로 네트워크 체크 분리, GUI 즉시 반응 보장.
        Rule M: silent failure 금지 (스레드 예외도 logger.warning).
        학술: Coley 2019 ACS Cent.Sci. 5:1572 (ASKCOS).
        """
        # 즉시 "확인 중..." 표시 — GUI freeze 없음
        if hasattr(self, '_lbl_engine_status'):
            self._lbl_engine_status.setText("외부 엔진 연결 상태 확인 중...")
        # SIMULATION_MODE 배너: 초기에는 "확인 중" 상태 (숨김)
        if hasattr(self, '_simulation_banner'):
            self._simulation_banner.hide()

        # 네트워크 체크는 백그라운드 스레드에서 수행
        self._engine_status_thread = _EngineStatusThread(parent=self)
        self._engine_status_thread.status_ready.connect(self._on_engine_status_ready)
        self._engine_status_thread.start()

    def _on_engine_status_ready(self, text: str, askcos_online: bool, ibm_rxn_online: bool) -> None:
        """[M923] _EngineStatusThread 완료 콜백 — GUI 스레드에서 라벨/배너 갱신.

        Rule M: silent failure 금지 — askcos_online=False시 SIMULATION_MODE 배너 표시.
        """
        if hasattr(self, '_lbl_engine_status'):
            self._lbl_engine_status.setText(text)

        # [M849 / Rule GG] SIMULATION_MODE 배너 제어
        if hasattr(self, '_simulation_banner'):
            if not askcos_online:
                self._simulation_banner.setText(
                    "SIMULATION_MODE — 외부 엔진(ASKCOS) 미연결.\n"
                    "로컬 SMARTS 휴리스틱 결과입니다 (학술 정합성 제한)."
                )
                self._simulation_banner.show()
            else:
                self._simulation_banner.hide()

    def _start_search(self):
        """백그라운드 역합성 검색 시작"""
        # 이전 스레드가 있으면 대기
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)

        # 출발물질 결정
        starting_mat = None
        if self._use_parent_as_starting and self._parent_smi:
            starting_mat = self._parent_smi

        # 복잡한 분자 감지 → 파라미터 조정
        try:
            mol = Chem.MolFromSmiles(self._target_smi) if RDKIT_AVAILABLE else None
            if mol is None and RDKIT_AVAILABLE:
                logger.warning("[Rule L] MolFromSmiles 실패: %r", self._target_smi)
            n_heavy = mol.GetNumHeavyAtoms() if mol else 0
        except Exception:
            n_heavy = 0

        is_complex = n_heavy > 20
        timeout = 45.0 if is_complex else 20.0
        max_depth = 10  # M632 SYNTHESIS-AUTO-001: max_depth 고정 10 (복잡도 무관)
        validate = not is_complex  # 복잡 분자는 mechanism 검증 건너뜀

        self._thread = RetrosynthesisThread(
            self._target_smi,
            max_depth=max_depth,
            max_routes=30,
            validate=validate,
            timeout=timeout,
            starting_material=starting_mat,
            parent=self,
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_all.connect(self._on_routes_found)
        self._thread.error.connect(self._on_error)
        self._thread.start()

        # [WATCHDOG] 최대 탐색 시간 + 5초 후 progress_bar 강제 숨김
        # Rule M: silent failure 방지 — 스레드가 어떤 이유로든 종료되지 않아도
        # 화면이 뺑뺑이(무한 progress_bar)로 멈추지 않도록 보장
        watchdog_ms = int((timeout + 5.0) * 1000)
        QTimer.singleShot(watchdog_ms, self._watchdog_hide_progress)

    def _watchdog_hide_progress(self):
        """[WATCHDOG] 타임아웃 후 progress_bar 강제 숨김 — 뺑뺑이 방지 (M613 Rule M)"""
        if self._progress_bar.isVisible():
            logger.warning(
                "[popup_synthesis] watchdog: 분석 타임아웃 — progress_bar 강제 숨김 "
                "(target=%r)", self._target_smi)
            self._progress_bar.hide()
            if not self._routes:
                # M613: "분석 타임아웃" 메시지 (웹 TimeoutError 배너 1:1 대응 Rule Y)
                self._lbl_status.setText("분석 타임아웃 — 경로를 찾지 못했습니다")
                self._lbl_status.setStyleSheet("color: #FFA726;")
                # routes=0 처리도 병행 (Rule M: silent failure 금지)
                self._feasibility_widget.show_no_routes_message(self._target_smi)
                self._flowchart.set_no_routes_message(
                    f"분석 타임아웃.\nSMILES: {self._target_smi[:60]}\n\n"
                    "분자가 복잡하거나 엔진이 응답하지 않을 수 있습니다.\n"
                    "Gemini AI 분석을 사용하거나 분자 구조를 단순화하여 다시 시도하세요."
                )

    def _on_progress(self, msg: str):
        self._lbl_status.setText(msg)

    def _on_error(self, msg: str):
        self._progress_bar.hide()
        self._lbl_status.setText("오류 발생")
        self._lbl_status.setStyleSheet("color: #F44336;")
        QMessageBox.warning(self, "역합성 오류", msg)

    def _on_routes_found(self, routes: list):
        """경로 검색 완료"""
        self._routes = routes
        self._progress_bar.hide()
        # [M849] Rule GG: 검색 완료 후 엔진 상태 + SIMULATION_MODE 배너 갱신
        self._update_engine_status_label()

        if not routes:
            # [M849 FIX / M751 F5-8] 합성경로 0건 — _OllamaFallbackThread 비동기 호출
            # 이전: GUI 메인 스레드에서 동기 Ollama 호출(5s) -> 화면 동결(격분 #12 원인)
            # 수정: _OllamaFallbackThread(QThread) -> GUI 즉시 반응 유지
            # 학술: Coley 2019 ACS Cent. Sci. 5:1572 (ASKCOS)
            # Rule M: silent 금지 -- 0건 상태 즉시 표시 + AI 힌트 비동기 로드
            logger.warning(
                "[M849] 합성경로 0건: target_smiles=%r -- "
                "ASKCOS/SMARTS 모두 미매칭, _OllamaFallbackThread 비동기 시도",
                self._target_smi,
            )
            # 즉시 UI 업데이트 (GUI freeze 없음)
            self._feasibility_widget.show_no_routes_message(self._target_smi)
            _nl = chr(10)  # [MAGIC:10] ASCII LF -- 문자열 내 개행 (f-string 회피)
            _no_route_msg_base = (
                "합성 경로를 찾지 못했습니다." + _nl
                + "SMILES: " + self._target_smi[:60] + _nl + _nl
                + "이론적으로 합성 가능하나 시판 시약 정보가 필요합니다." + _nl
                + "Gemini AI 분석을 사용하거나 직접 경로를 설계하세요." + _nl
                + "[AI 경로 제안 로드 중...]"
            )
            self._flowchart.set_no_routes_message(_no_route_msg_base)
            self._lbl_status.setText("경로 탐색 완료 -- AI 경로 제안 로드 중...")
            self._lbl_status.setStyleSheet("color: #42A5F5;")
            self._step_detail.set_has_route(False)

            # 비동기 Ollama 힌트 로드 (_OllamaFallbackThread, Rule MM: Ollama=무료)
            if _SKIP_OLLAMA_FALLBACK:
                logger.warning(
                    "[M854] HEADLESS/CAPTURE mode -- skip _OllamaFallbackThread "
                    "to prevent qwen2.5:14b VRAM stall"
                )
                self._on_ollama_hint_ready("")
                return
            self._ollama_thread = _OllamaFallbackThread(self._target_smi, parent=self)
            self._ollama_thread.finished.connect(self._on_ollama_hint_ready)
            self._ollama_thread.start()
            return

        # 천연물 경로 감지
        has_extraction = any(getattr(r, '_is_extraction', False) for r in routes)
        if has_extraction:
            n_synth = sum(1 for r in routes if not getattr(r, '_is_extraction', False))
            self._lbl_status.setText(
                f"천연물 ���출 권장 + {n_synth}개 합성 경로")
            self._lbl_status.setStyleSheet("color: #66BB6A;")
        else:
            self._lbl_status.setText(f"{len(routes)}개 경로 발견")
            self._lbl_status.setStyleSheet("color: #66BB6A;")

        # 실행 가능성 점수 계산 — Rule M: 실패해도 카드 생성/버튼 활성화는 반드시 실행
        try:
            from retrosynthesis_engine import RouteFeasibility, NaturalProductInfo
            engine = RetrosynthesisEngine()
            self._feasibility_data = []
            for route in routes:
                if getattr(route, '_is_extraction', False):
                    # 천연물 추출 경로: 특별 feasibility 생성
                    nat_info = getattr(route, '_natural_product_info', None)
                    name = nat_info.name_kr if nat_info else "천연물"
                    feasibility = RouteFeasibility(
                        overall_score=85.0,
                        temperature_score=90.0,
                        pressure_score=100.0,
                        reagent_availability=95.0,
                        step_count_score=80.0,
                        safety_score=85.0,
                        estimated_yield="high",
                        lab_level="대학교",
                        summary=f"{name} 천연물 추출+정제 경로 (합성보다 추출 권장)",
                    )
                else:
                    feasibility = engine.score_route_feasibility(route)
                self._feasibility_data.append(feasibility)

            # 비교 테이블 업데이트
            self._feasibility_widget.update_data(routes, self._feasibility_data)
        except Exception as _fe:
            logger.warning("[_on_routes_found] feasibility scoring/table update failed: %s", _fe)
            self._feasibility_data = []

        # 카드 생성
        # 기존 stretch 제��
        while self._routes_layout.count() > 0:
            item = self._routes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._route_cards.clear()
        for i, route in enumerate(routes):
            card = RouteCardWidget(route, i)
            card.clicked.connect(self._on_route_selected)
            self._routes_layout.addWidget(card)
            self._route_cards.append(card)
        self._routes_layout.addStretch()

        # 첫 번�� 경로 자동 선택
        if routes:
            self._on_route_selected(0)

    def _on_ollama_hint_ready(self, hint: str) -> None:
        """[M849] Ollama fallback 비동기 완료 callback.
        경로 0건 시 AI 경로 제안을 flowchart에 표시.
        Rule M: 빈 hint = fallback 메시지 표시 (silent failure 금지).
        """
        _nl = chr(10)  # [MAGIC:10] ASCII LF -- 문자열 내 개행 (f-string 회피)
        _no_route_msg = (
            "합성 경로를 찾지 못했습니다." + _nl
            + "SMILES: " + self._target_smi[:60] + _nl + _nl
        )
        if hint:
            _no_route_msg += "[AI 경로 제안]" + _nl + hint[:500]
        else:
            _no_route_msg += (
                "이론적으로 합성 가능하나 시판 시약 정보가 필요합니다." + _nl
                + "Gemini AI 분석을 사용하거나 직접 경로를 설계하세요."
            )
        self._flowchart.set_no_routes_message(_no_route_msg)
        self._lbl_status.setText("경로 탐색 완료 (AI 경로 제안)")
        self._lbl_status.setStyleSheet("color: #FFA726;")

    def _on_route_selected(self, idx: int):
        """경로 카드/비교 테이블 클릭 → 플로차트 갱신 + 단계별 상세 업데이트"""
        if idx < 0 or idx >= len(self._routes):
            return

        # 이전 선택 해제
        for card in self._route_cards:
            card.set_selected(False)

        self._selected_route_idx = idx
        if idx < len(self._route_cards):
            self._route_cards[idx].set_selected(True)
        self._flowchart.set_route(self._routes[idx])
        self._step_detail.set_has_route(True)   # route available → Gemini enabled
        self._step_detail.set_step(None)         # 단계 선택 초기화
        self._btn_export_pdf.setEnabled(True)    # PDF 내보내기 활성화

        # 단계별 메커니즘 상세 탭 업데이트
        self._update_steps_detail_text(self._routes[idx])

        # [FIX-D] 왼쪽 패널 단계별 설명 업데이트
        self._update_left_steps_summary(self._routes[idx])

        # [B5-3/B10-9 FIX] 첫 번째 단계 자동 선택 → 메커니즘 버튼 즉시 활성화
        # 경로 로드 후 단계를 별도로 클릭하지 않아도 mechanism 버튼이 켜지도록 함
        route = self._routes[idx]
        if route and route.steps:
            self._on_step_clicked(0)  # step_idx=0 → 첫 번째 단계 자동 선택

        # 비교 테이블에서 클릭한 경우: 플로차트 탭으로 자동 전환
        if self._right_tabs.currentIndex() == 0:
            self._right_tabs.setCurrentIndex(1)

    def _on_step_clicked(self, step_idx: int):
        """플로차트에서 단계 클릭 — 메커니즘 데이터와 함께 상세 패널 업데이트"""
        route = self._routes[self._selected_route_idx]
        if 0 <= step_idx < len(route.steps):
            step = route.steps[step_idx]
            # 메커니즘 데이터 조회 (캐시에서)
            mech_data = None
            if MECHANISM_AVAILABLE:
                cache_key = f"{'.'.join(step.reactant_smiles)}>>>{step.product_smiles}"
                mech_data = self._flowchart._mechanism_cache.get(cache_key)
            try:
                self._step_detail.set_step(step, mechanism_data=mech_data)
            except Exception as _e:
                logger.warning("[_on_step_clicked] set_step failed for step %d: %s", step_idx, _e)
            # Rule M: set_step 실패여도 버튼 활성화 보장 (silent failure 금지)
            self._btn_reaction_anim.setEnabled(True)
            self._selected_step_idx = step_idx

    def _update_left_steps_summary(self, route: SynthesisRoute):
        """[FIX-D] 왼쪽 패널에 단계별 요약을 표시합니다.

        각 합성 단계의 반응명, 반응물 -> 생성물, 조건을 간결하게 보여줌.
        """
        if not route or not route.steps:
            self._left_steps_text.setHtml(
                "<p style='color:#999;'>단계 정보 없음</p>")
            return

        # 천연물 추출 경로
        if getattr(route, '_is_extraction', False):
            nat_info = getattr(route, '_natural_product_info', None)
            if nat_info:
                self._left_steps_text.setHtml(
                    f"<p style='color:#66BB6A;'><b>천연물 추출 경로</b></p>"
                    f"<p style='color:#B0BEC5;'>1. 추출: {nat_info.source}</p>"
                    f"<p style='color:#B0BEC5;'>2. 정제: {nat_info.purification[:60]}...</p>"
                )
            return

        html_lines = []
        for si, step in enumerate(route.steps):
            # 반응물 이름 조회
            reactant_names = []
            for r_smi in step.reactant_smiles:
                info = get_building_block_info(r_smi)
                if info:
                    reactant_names.append(info['name_en'])
                else:
                    reactant_names.append(r_smi[:15] + ("..." if len(r_smi) > 15 else ""))
            r_str = " + ".join(reactant_names)

            # 생성물 이름
            p_info = get_building_block_info(step.product_smiles)
            p_name = p_info['name_en'] if p_info else (
                step.product_smiles[:15] + ("..." if len(step.product_smiles) > 15 else ""))

            # 색상: 첫 단계 강조
            color = "#90CAF9" if si == 0 else "#B0BEC5"
            cond_short = step.conditions[:30] + ("..." if len(step.conditions) > 30 else "") if step.conditions else ""

            html_lines.append(
                f"<p style='color:{color};margin:1px 0;'>"
                f"<b>Step {step.step_number}:</b> {step.transform_name}</p>"
                f"<p style='color:#9E9E9E;margin:0 0 4px 8px;font-size:7pt;'>"
                f"{r_str} &rarr; {p_name}"
            )
            if cond_short:
                html_lines.append(
                    f"<br><span style='color:#FFA726;'>{cond_short}</span>")
            html_lines.append("</p>")

        self._left_steps_text.setHtml("".join(html_lines))

    def _update_steps_detail_text(self, route: SynthesisRoute):
        """선택된 경로의 단계별 반응 메커니즘 상세를 텍스트로 표시.

        [P0-4 FIX] 각 단계에 대해:
        - 반응물/생성물 SMILES
        - 반응 조건 (시약, 온도, 용매, 촉매)
        - 메커니즘 유형 및 전자 이동 설명
        - 중간체/전이상태 정보
        """
        if not route or not route.steps:
            self._steps_detail_text.setHtml(
                "<p style='color:#999;'>경로 데이터가 없습니다.</p>")
            return

        # 천연물 추출 경로 처리
        if getattr(route, '_is_extraction', False):
            nat_info = getattr(route, '_natural_product_info', None)
            if nat_info:
                html = (
                    "<h2 style='color:#66BB6A;'>천연물 추출 경로</h2>"
                    f"<p><b>물질:</b> {nat_info.name_kr} ({nat_info.name})</p>"
                    f"<p><b>유래:</b> {nat_info.source}</p>"
                    f"<p><b>추출 방법:</b> {nat_info.extraction}</p>"
                    f"<p><b>정제 방법:</b> {nat_info.purification}</p>")
                if nat_info.storage:
                    html += f"<p><b>보관 조건:</b> {nat_info.storage}</p>"
                if nat_info.note:
                    html += f"<p><b>참고:</b> {nat_info.note}</p>"
                self._steps_detail_text.setHtml(html)
            return

        # MechanismEngine 초기화 (필요 시)
        mech_engine = None
        if MECHANISM_AVAILABLE:
            try:
                mech_engine = MechanismEngine()
            except Exception as e:
                logger.warning(
                    "MechanismEngine init for detail text: %s", e)

        # HTML 빌드
        html_parts = [
            "<style>",
            "  body { font-family: 'Segoe UI', Arial, sans-serif; }",
            "  h2 { color: #42A5F5; margin-top: 16px; border-bottom: 1px solid #444; "
            "       padding-bottom: 4px; }",
            "  h3 { color: #FFA726; margin-top: 10px; }",
            "  .reaction { color: #90CAF9; font-family: Consolas, monospace; "
            "              font-size: 10pt; margin: 4px 0; }",
            "  .conditions { color: #FFA726; font-size: 9pt; margin: 2px 0; }",
            "  .mech-info { color: #CE93D8; font-size: 9pt; margin: 2px 0; }",
            "  .step-desc { color: #B0BEC5; font-size: 9pt; margin: 4px 0 4px 16px; }",
            "  .ts-label { color: #FF7043; font-weight: bold; }",
            "  .inter-label { color: #4FC3F7; font-style: italic; }",
            "  .bb-name { color: #81C784; }",
            "</style>",
            f"<h2>합성 경로 ({route.total_steps}단계)</h2>",
        ]

        # 시작물질 표시
        if route.building_blocks:
            bb_names = []
            for bb_smi in route.building_blocks:
                info = get_building_block_info(bb_smi)
                if info:
                    bb_names.append(
                        f"<span class='bb-name'>{info['name_en']}</span> "
                        f"({bb_smi})")
                else:
                    bb_names.append(f"<span class='bb-name'>{bb_smi}</span>")
            html_parts.append(
                f"<p><b>시작물질:</b> {' + '.join(bb_names)}</p>")

        for si, step in enumerate(route.steps):
            r_str = " + ".join(step.reactant_smiles)
            html_parts.append(
                f"<h3>Step {step.step_number}: {step.transform_name}</h3>")

            # 반응식
            html_parts.append(
                f"<p class='reaction'>{r_str} &rarr; {step.product_smiles}</p>")

            # 반응 조건
            if step.conditions:
                html_parts.append(
                    f"<p class='conditions'>조건: {step.conditions}</p>")
            if hasattr(step, 'transform_name_en') and step.transform_name_en:
                html_parts.append(
                    f"<p class='conditions'>({step.transform_name_en})</p>")

            # 신뢰도
            conf_pct = step.confidence * 100
            color = "#66BB6A" if conf_pct >= 70 else "#FFA726" if conf_pct >= 40 else "#F44336"
            html_parts.append(
                f"<p style='color:{color};font-size:9pt;'>"
                f"신뢰도: {conf_pct:.0f}%</p>")

            # 메커니즘 상세 (있으면)
            mech_data = None
            if mech_engine is not None:
                cache_key = (f"{'.'.join(step.reactant_smiles)}"
                             f">>>{step.product_smiles}")
                # 플로차트 캐시에서 먼저 확인
                mech_data = self._flowchart._mechanism_cache.get(cache_key)
                if mech_data is None:
                    try:
                        # [INTERMOLECULAR FIX] 상세 패널도 재매핑된 메커니즘 사용
                        mech_data = mech_engine.generate_intermolecular_mechanism(
                            step.reactant_smiles,
                            step.product_smiles,
                            transform_name=getattr(step, 'transform_name',
                                                   '') or '',
                            conditions=getattr(step, 'conditions', '') or '')
                    except Exception as e:
                        logger.warning(
                            "Mechanism gen for detail text step %d: %s", si, e)

            if mech_data is not None:
                html_parts.append(
                    f"<p class='mech-info'><b>메커니즘:</b> "
                    f"{mech_data.title} ({mech_data.total_steps}단계)</p>")
                if mech_data.overall_description:
                    html_parts.append(
                        f"<p class='step-desc'>"
                        f"{mech_data.overall_description[:200]}</p>")
                for ms in mech_data.steps:
                    if ms.is_transition_state:
                        html_parts.append(
                            f"<p class='step-desc'>"
                            f"<span class='ts-label'>[&#8225; 전이상태]</span> "
                            f"{ms.title}: {ms.description[:120]}</p>")
                    else:
                        arrow_count = len(ms.arrows) if ms.arrows else 0
                        html_parts.append(
                            f"<p class='step-desc'>"
                            f"<b>Step {ms.step_number}:</b> {ms.title} "
                            f"({arrow_count}개 전자 이동)</p>")
                        if ms.description:
                            # 설명을 줄바꿈으로 분리하여 표시
                            desc_lines = ms.description.split('\n')
                            for dl in desc_lines[:3]:  # 최대 3줄
                                dl = dl.strip()
                                if dl:
                                    html_parts.append(
                                        f"<p class='step-desc'>"
                                        f"  &bull; {dl}</p>")
                        if ms.product_smiles:
                            smi_display = ms.product_smiles
                            if len(smi_display) > 60:
                                smi_display = smi_display[:57] + "..."
                            label_class = ("inter-label"
                                           if ms.product_smiles != step.product_smiles
                                           else "")
                            html_parts.append(
                                f"<p class='step-desc {label_class}'>"
                                f"  &rarr; {smi_display}</p>")
            else:
                html_parts.append(
                    "<p class='mech-info'>메커니즘 데이터 없음 "
                    "(메커니즘 보기 버튼으로 상세 확인)</p>")

            # 단계 구분선
            if si < len(route.steps) - 1:
                html_parts.append("<hr style='border-color:#333;'>")

        self._steps_detail_text.setHtml("\n".join(html_parts))

    def _open_mechanism(self, step: SynthesisStep):
        """메커니즘 보기 → ReactionPopup 오픈"""
        try:
            from popup_reaction import ReactionPopup
            reactant_smi = ".".join(step.reactant_smiles)
            product_smi = step.product_smiles
            all_smiles = step.reactant_smiles + [step.product_smiles]
            names = [f"반응물 {i+1}" for i in range(len(step.reactant_smiles))]
            names.append("생성물")
            popup = ReactionPopup(all_smiles, names, parent=self)
            popup.exec()
        except Exception as e:
            QMessageBox.warning(self, "메커니즘 오류",
                                f"메커니즘 팝업을 열 수 없습니다:\n{e}")

    def _show_or_exec_child_popup(self, popup: QWidget, attr_name: str) -> None:
        """Use non-modal show() in capture/offscreen mode; keep exec() for users."""
        setattr(self, attr_name, popup)
        if _is_capture_or_headless_mode():
            logger.warning(
                "[M854] SynthesisPopup capture/headless mode -- using show() "
                "instead of exec() for %s so QTest harness can continue",
                attr_name,
            )
            if hasattr(popup, "setModal"):
                popup.setModal(False)
            if hasattr(popup, "setWindowModality"):
                popup.setWindowModality(Qt.WindowModality.NonModal)
            try:
                popup.destroyed.connect(
                    lambda _obj=None, _attr=attr_name: setattr(self, _attr, None)
                )
            except Exception as e:
                logger.warning("[M854] child popup cleanup hook failed: %s", e)
            popup.show()
            popup.raise_()
            popup.activateWindow()
            return

        if hasattr(popup, "exec"):
            popup.exec()
        else:
            popup.show()

    def _on_reaction_animation(self):
        """선택된 합성 단계의 3D 반응 메커니즘 애니메이션."""
        if self._selected_route_idx < 0:
            QMessageBox.information(self, "애니메이션 불가",
                                   "먼저 합성 경로와 단계를 선택해주세요.")
            return
        route = self._routes[self._selected_route_idx]
        step_idx = getattr(self, '_selected_step_idx', -1)
        if step_idx < 0 or step_idx >= len(route.steps):
            QMessageBox.information(self, "애니메이션 불가",
                                   "플로차트에서 합성 단계를 클릭해주세요.")
            return
        step = route.steps[step_idx]
        try:
            from popup_reaction_animation import ReactionAnimationPopup
            reactant_smi = ".".join(step.reactant_smiles)
            product_smi = step.product_smiles
            reaction_name = step.transform_name or step.transform_name_en or ""
            popup = ReactionAnimationPopup(
                reactant_smiles=reactant_smi,
                product_smiles=product_smi,
                reaction_name=reaction_name,
                parent=self,
            )
            self._show_or_exec_child_popup(popup, "_active_reaction_animation_popup")
        except ImportError:
            QMessageBox.warning(self, "모듈 없음",
                                "popup_reaction_animation 모듈을 찾을 수 없습니다.")
        except Exception as e:
            QMessageBox.warning(self, "애니메이션 오류",
                                f"3D 반응 애니메이션을 열 수 없습니다:\n{e}")

    def _on_export_pdf(self):
        """선택된 합성 경로를 PDF로 내보내기."""
        if self._selected_route_idx < 0 or self._selected_route_idx >= len(self._routes):
            QMessageBox.information(self, "내보내기 불가",
                                   "먼저 합성 경로를 선택해주세요.")
            return

        route = self._routes[self._selected_route_idx]

        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, "합성 경로 PDF 저장",
            f"synthesis_route_{self._target_name}.pdf",
            "PDF 파일 (*.pdf);;모든 파일 (*.*)"
        )
        if not file_path:
            return  # 사용자 취소

        self._btn_export_pdf.setEnabled(False)
        self._btn_export_pdf.setText("PDF 생성 중...")

        try:
            success, result_msg = export_synthesis_route_pdf(route, file_path)
            if success:
                QMessageBox.information(
                    self, "PDF 내보내기 완료",
                    f"합성 경로가 PDF로 저장되었습니다.\n{result_msg}")
                # 파일 열기 시도
                try:
                    os.startfile(result_msg)
                except Exception as e:
                    logger.warning(f"[SynthesisPopup] PDF 파일 자동 열기 실패: {e}")
            else:
                QMessageBox.warning(self, "PDF 내보내기 실패", result_msg)
        except Exception as e:
            QMessageBox.warning(self, "PDF 내보내기 오류",
                                f"PDF 내보내기 중 오류 발생:\n{e}")
        finally:
            self._btn_export_pdf.setEnabled(True)
            self._btn_export_pdf.setText("합성 경로 PDF 내보내기")

    def _on_gemini_analyze(self, step):
        """Gemini AI로 합성 단계 또는 전체 경로 상세 분석."""
        # Gather route context
        route = None
        if 0 <= self._selected_route_idx < len(self._routes):
            route = self._routes[self._selected_route_idx]

        if step is None and route is None:
            QMessageBox.information(
                self, "분석 불가",
                "분석할 데이터가 없습니다.\n경로 탐색을 먼저 실행해주세요.")
            return

        # --- Gemini API availability check ---
        genai_lib = None
        api_key = ""
        import_error_msg = ""
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import google.generativeai as genai_lib
            api_key = (os.environ.get("GEMINI_API_KEY", "")
                       or os.environ.get("GOOGLE_API_KEY", ""))
        except ImportError:
            import_error_msg = (
                "google-generativeai 패키지가 설치되지 않았습니다.\n"
                "설치: pip install google-generativeai")
        except Exception as exc:
            import_error_msg = f"google.generativeai 로드 오류: {exc}"

        if genai_lib is None or not api_key:
            # Graceful fallback with informative message
            if step is not None:
                self._show_fallback_protocol(step)
            else:
                reason = import_error_msg or (
                    "Gemini API 키가 설정되지 않았습니다.\n"
                    "환경변수 GEMINI_API_KEY 또는 GOOGLE_API_KEY를 설정해주세요.")
                QMessageBox.information(
                    self, "Gemini API 미설정",
                    f"{reason}\n\n"
                    "개별 단계를 클릭하면 rule-based 기본 프로토콜을 볼 수 있습니다.")
            return

        # --- Build comprehensive prompt ---
        prompt = self._build_gemini_prompt(step, route)
        title = (f"🤖 Gemini 분석: {step.transform_name}"
                 if step else f"🤖 Gemini 전체 경로 분석: {self._target_name}")

        # --- Run API call in background thread to avoid GUI freeze ---
        self._btn_gemini_ref = self._step_detail._btn_gemini  # save ref for re-enable
        self._btn_gemini_ref.setEnabled(False)
        self._btn_gemini_ref.setText("🤖 AI 분석 중...")

        self._gemini_worker = _GeminiWorker(genai_lib, api_key, prompt)
        self._gemini_thread = QThread()
        self._gemini_worker.moveToThread(self._gemini_thread)

        # Store context for result handler
        self._gemini_ctx = {"step": step, "title": title}

        self._gemini_thread.started.connect(self._gemini_worker.run)
        self._gemini_worker.finished.connect(self._on_gemini_result)
        self._gemini_worker.finished.connect(self._gemini_thread.quit)
        self._gemini_worker.finished.connect(self._gemini_worker.deleteLater)
        self._gemini_thread.finished.connect(self._gemini_thread.deleteLater)
        self._gemini_thread.start()

    def _on_gemini_result(self, result_text: str, error_msg: str):
        """Handle Gemini API result back on the main thread."""
        # Re-enable button
        try:
            self._step_detail._update_gemini_button()
        except Exception as e:
            logger.warning(f"[SynthesisPopup] Gemini 버튼 상태 복원 실패: {e}")

        if error_msg:
            # Provide actionable error messages
            err_upper = error_msg.upper()
            if "API_KEY" in err_upper or "401" in error_msg or "403" in error_msg:
                hint = "API 키가 유효하지 않거나 만료되었을 수 있습니다."
            elif "QUOTA" in err_upper or "429" in error_msg or "RESOURCEEXHAUSTED" in err_upper:
                hint = "API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            elif "TIMEOUT" in err_upper or "DEADLINE" in err_upper:
                hint = "요청 시간이 초과되었습니다. 네트워크 연결을 확인해주세요."
            elif "SAFETY" in err_upper or "BLOCKED" in err_upper:
                hint = "안전 필터에 의해 응답이 차단되었습니다. 프롬프트를 조정해보세요."
            else:
                hint = "네트워크 연결을 확인하거나 잠시 후 다시 시도해주세요."
            QMessageBox.warning(
                self, "Gemini 오류",
                f"AI 분석 실패:\n{error_msg}\n\n{hint}")
            # If step available, offer fallback
            ctx_step = self._gemini_ctx.get("step")
            if ctx_step is not None:
                self._show_fallback_protocol(ctx_step)
            return

        # --- Show result dialog ---
        title = self._gemini_ctx.get("title", "Gemini 분석 결과")
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(650, 550)
        dlg.setStyleSheet("background: #1a1a2e; color: #e0e0e0;")
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "background: #16213e; color: #e0e0e0; font-size: 11pt; "
            "border: 1px solid #0f3460; border-radius: 6px; padding: 8px;")
        txt.setPlainText(result_text)
        lay.addWidget(txt)
        btn_close = QPushButton("닫기")
        btn_close.setStyleSheet(
            "background: #1565C0; color: white; padding: 8px 20px; "
            "border-radius: 6px; font-weight: bold;")
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        dlg.exec()

    def _build_gemini_prompt(self, step, route) -> str:
        """Build a comprehensive Gemini prompt from available molecular/route data."""
        parts = []

        # --- Header: target molecule context ---
        parts.append(f"타겟 분자: {self._target_name}")
        parts.append(f"타겟 SMILES: {self._target_smi}")

        # Molecular properties via RDKit if available
        if RDKIT_AVAILABLE:
            try:
                from rdkit.Chem import Descriptors
                mol = Chem.MolFromSmiles(self._target_smi)
                if mol:
                    mw = Descriptors.ExactMolWt(mol)
                    logp = Descriptors.MolLogP(mol)
                    hba = Descriptors.NumHAcceptors(mol)
                    hbd = Descriptors.NumHDonors(mol)
                    n_rings = mol.GetRingInfo().NumRings()
                    parts.append(
                        f"분자량: {mw:.2f} g/mol | LogP: {logp:.2f} | "
                        f"HBA: {hba} | HBD: {hbd} | 고리 수: {n_rings}")
                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", self._target_smi)
            except Exception as e:
                logger.warning(f"[SynthesisPopup] 분자 물성 계산 실패: {e}")

        parts.append("")

        if step is not None:
            # --- Step-level analysis ---
            reactants = " + ".join(step.reactant_smiles)
            parts.append(
                f"유기화학 합성 반응의 구체적인 실험 프로토콜을 작성해주세요.\n\n"
                f"반응명: {step.transform_name} ({step.transform_name_en})\n"
                f"반응물 SMILES: {reactants}\n"
                f"생성물 SMILES: {step.product_smiles}\n"
                f"기본 조건: {step.conditions}\n")

            # Include route context if available
            if route:
                parts.append(
                    f"(이 단계는 총 {route.total_steps}단계 합성 경로의 "
                    f"Step {step.step_number}입니다. "
                    f"경로 점수: {route.score:.2f})\n")

            parts.append(
                "다음 항목을 모두 한국어로 답변해주세요:\n\n"
                "## 1. 시약 및 용매\n"
                "- 각 시약의 당량(equiv.), 몰 비율, 농도\n"
                "- 용매 선택과 건조/탈기 필요 여부\n"
                "- 시약 등급 (Reagent Grade, Anhydrous 등)\n\n"
                "## 2. 반응 조건\n"
                "- 온도 (시작 → 최종, 승온 속도)\n"
                "- 반응 시간\n"
                "- 분위기 (N₂, Ar, 공기)\n"
                "- 압력 (상압/감압/가압)\n\n"
                "## 3. 촉매\n"
                "- 촉매 종류, 당량, 활성화 조건\n"
                "- 촉매 회수 가능 여부\n\n"
                "## 4. 예상 수율\n"
                "- 문헌 기반 수율 범위 (%)\n"
                "- 수율 영향 인자 (수분, 온도, 시간)\n\n"
                "## 5. 후처리 (Workup)\n"
                "- 반응 종료 방법 (quench)\n"
                "- 추출/세척/건조/농축 절차\n"
                "- 정제 방법 (칼럼, 재결정 등)\n\n"
                "## 6. 안전 주의사항\n"
                "- GHS 위험 등급, 유해 물질 취급 주의\n"
                "- 필요한 보호 장비\n\n"
                "## 7. 대체 합성법 (선택)\n"
                "- 더 효율적이거나 친환경적인 대안이 있다면 간략히 제안\n")
        else:
            # --- Route-level (overall) analysis ---
            parts.append(
                "아래 합성 경로 전체를 분석하고 종합 평가를 한국어로 작성해주세요.\n")

            if route:
                parts.append(f"총 단계 수: {route.total_steps}")
                parts.append(f"경로 점수: {route.score:.2f}")
                if route.building_blocks:
                    parts.append(f"빌딩블록: {', '.join(route.building_blocks)}")
                parts.append("")

                for s in route.steps:
                    r_str = " + ".join(s.reactant_smiles)
                    parts.append(
                        f"Step {s.step_number}: {s.transform_name} "
                        f"({s.transform_name_en})\n"
                        f"  반응물: {r_str}\n"
                        f"  생성물: {s.product_smiles}\n"
                        f"  조건: {s.conditions}\n"
                        f"  신뢰도: {s.confidence * 100:.0f}%\n")

            parts.append(
                "\n다음 항목을 모두 답변해주세요:\n\n"
                "## 1. 경로 종합 평가\n"
                "- 전체 경로의 실현 가능성, 효율성, 선형/수렴 여부\n"
                "- 예상 총 수율 (각 단계 수율 곱)\n\n"
                "## 2. 병목 단계 (Bottleneck)\n"
                "- 가장 어렵거나 수율이 낮을 것으로 예상되는 단계와 이유\n\n"
                "## 3. 시약 조달 용이성\n"
                "- 빌딩블록/시약의 상업적 이용 가능성\n"
                "- 비용이 높은 시약 식별\n\n"
                "## 4. 안전 및 환경\n"
                "- 경로 전체에서 주의해야 할 위험 물질\n"
                "- 폐기물 처리 고려사항\n\n"
                "## 5. 대안 경로 제안\n"
                "- 더 짧거나 효율적인 대안 경로가 있다면 간략히 제안\n")

        return "\n".join(parts)

    def _show_fallback_protocol(self, step: SynthesisStep):
        """Gemini API 미사용 시 rule-based 기본 프로토콜 생성"""
        reactants = " + ".join(step.reactant_smiles)
        product = step.product_smiles

        lines = [
            f"== {step.transform_name} ({step.transform_name_en}) ==",
            f"",
            f"[반응물] {reactants}",
            f"[생성물] {product}",
            f"[조건] {step.conditions}",
            f"",
            "--- 기본 실험 프로토콜 (rule-based) ---",
            "",
        ]

        # Condition parsing
        cond = step.conditions.lower()
        if "가열" in cond or "heat" in cond or "reflux" in cond.lower():
            lines.append("온도: 환류 또는 60-100 C (용매 끓는점에 따라 조절)")
        elif "-78" in cond:
            lines.append("온도: -78 C (드라이아이스/아세톤 배스)")
        elif "0" in cond:
            lines.append("온도: 0 C (아이스 배스)")
        else:
            lines.append("온도: 실온 (RT, ~25 C)")

        lines.append("반응 시간: 1-24시간 (TLC 모니터링 권장)")
        lines.append("")

        # Solvent/atmosphere hints
        if "thf" in cond:
            lines.append("용매: THF (건조, Ar 분위기)")
        elif "dmso" in cond:
            lines.append("용매: DMSO")
        elif "dcm" in cond or "ch2cl2" in cond or "ch₂cl₂" in cond:
            lines.append("용매: CH2Cl2 (건조)")
        elif "meoh" in cond:
            lines.append("용매: MeOH")
        elif "h2o" in cond or "h₂o" in cond:
            lines.append("용매: H2O")
        else:
            lines.append("용매: 반응 조건에 맞게 선택")

        # Catalyst hints
        if "pd" in cond:
            lines.append("촉매: Pd 촉매 (질소/아르곤 분위기 필수)")
        elif "fecl3" in cond or "febr3" in cond or "alcl3" in cond:
            lines.append("촉매: Lewis산 촉매 (무수 조건)")
        elif "h2so4" in cond or "h₂so₄" in cond:
            lines.append("촉매: H2SO4 (촉매량)")

        lines.extend([
            "",
            "예상 수율: 문헌 참조 필요",
            "",
            "주의: 이 프로토콜은 rule-based 추정입니다.",
            "Gemini API 키를 설정하면 AI 기반 상세 프로토콜을 받을 수 있습니다.",
            "(환경변수: GEMINI_API_KEY 또는 GOOGLE_API_KEY)",
        ])

        # Show in dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"기본 프로토콜: {step.transform_name}")
        dlg.resize(550, 420)
        dlg.setStyleSheet("background: #1a1a2e; color: #e0e0e0;")
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "background: #16213e; color: #e0e0e0; font-size: 11pt; "
            "border: 1px solid #0f3460; border-radius: 6px; padding: 8px;")
        txt.setPlainText("\n".join(lines))
        lay.addWidget(txt)
        btn_close = QPushButton("닫기")
        btn_close.setStyleSheet(
            "background: #1565C0; color: white; padding: 8px 20px; "
            "border-radius: 6px; font-weight: bold;")
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        dlg.exec()

    def closeEvent(self, event):
        """다이얼로그 닫기 시 스레드 정리"""
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════
# 편의 함수
# ═══════════════════════════════════════════════════════════
def launch_synthesis_viewer(target_smiles: str, target_name: str = "",
                            parent_smiles: Optional[str] = None,
                            parent_name: str = "",
                            parent=None):
    """외부에서 합성 경로 분석 팝업을 열 때 사용.

    Args:
        target_smiles: 목표 분자 SMILES
        target_name: 목표 분자 이름
        parent_smiles: 모분자 SMILES (Option B 활성화). None이면 표준 역합성만.
        parent_name: 모분자 이름
        parent: Qt parent widget
    """
    popup = SynthesisPopup(target_smiles, target_name,
                           parent_smiles=parent_smiles,
                           parent_name=parent_name,
                           parent=parent)
    if _is_capture_or_headless_mode():
        logger.warning(
            "[M854] launch_synthesis_viewer capture/headless mode -- using show() "
            "instead of exec() so QTest harness can continue"
        )
        popup.setModal(False)
        popup.setWindowModality(Qt.WindowModality.NonModal)
        _ACTIVE_SYNTHESIS_VIEWERS.append(popup)

        def _forget_popup(_obj=None):
            try:
                if popup in _ACTIVE_SYNTHESIS_VIEWERS:
                    _ACTIVE_SYNTHESIS_VIEWERS.remove(popup)
            except Exception as e:
                logger.warning("[M854] launch_synthesis_viewer cleanup failed: %s", e)

        try:
            popup.destroyed.connect(_forget_popup)
        except Exception as e:
            logger.warning("[M854] launch_synthesis_viewer cleanup hook failed: %s", e)
        popup.show()
        popup.raise_()
        popup.activateWindow()
        return popup
    popup.exec()
    return popup


# ═══════════════════════════════════════════════════════════
# CLI 테스트
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    app = QApplication.instance() or QApplication(sys.argv)

    # 테스트: 아스피린 합성 경로
    target = "CC(=O)Oc1ccccc1C(=O)O"
    popup = SynthesisPopup(target, "아스피린 (Aspirin)")
    popup.show()
    sys.exit(app.exec())
