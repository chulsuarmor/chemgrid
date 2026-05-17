# canvas.py — MoleculeCanvas 분리 모듈
# Agent 02 (캔버스/그리기) 전담
# 최종 업데이트: 2026-03-01
#
# 변경 이력:
#   - MoleculeCanvas를 draw.py에서 분리
#   - [M1] 조준선 3중 렌더링 버그 수정 → 최상위 Z-INDEX 1회만 호출
#   - [M2] paintEvent 내부 디버그 print() 전부 제거
#   - [C3] self.canvas.repaint → self.update() 수정
#   - [C5] 하드코딩 절대 경로 → __file__ 기반 상대 경로
#   - [U5] draw_bond() 고리 이중결합 짧은 선 안쪽 방향 보정 (BFS 고리 감지)
#   - [Phase 6-3] Theory 모드 분자 선택 UX: 점선 테두리 + IUPAC명 + 바닥 클릭 해제
#   - [Phase 6-3 v4 명령1] +/- 기호 → atoms["charge"] 별도 필드 분리
#   - [Phase 6-3 v4 명령3] 반응 화살표 도구 (Arrow) — 4방향 스냅, 고스트, 모든 레이어 표시
#   - [Phase 6-3 v4 명령4] 텍스트 상자 도구 (Text) — 아래첨자 변환, T모드 전용 표시
#   - [Phase 6-3 v4 명령5] 비공유전자쌍 user_lp 플래그 추가
# =========================================================================

import logging
import math
import copy
import os
try:
    import pubchem_client as _pc_client
    _PC_CLIENT_AVAILABLE = True
except ImportError:
    _PC_CLIENT_AVAILABLE = False
    _pc_client = None
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QFontMetrics,
    QPolygonF, QPainterPath,
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QSizeF,
    pyqtProperty, pyqtSignal, QPropertyAnimation, QEasingCurve,
    QThread,
)

logger = logging.getLogger(__name__)

from chem_data import ELEMENT_DATA, VISUAL_SETTINGS
from analyzer import ChemicalAnalyzer
from renderer import CloudRenderer
from layer_logic import LewisRenderer, TheoryRenderer, ElectronDistributionRenderer, _resolve_atom_font_family
from coord_utils import get_ring_center_for_bond

# [M609 Rule Q] canvas.py 캔버스 전역 폰트 패밀리
# LewisRenderer._get_font_family() 와 동일한 해결 체인 사용
# 이 변수는 QApplication 생성 이후 첫 접근 시 lazy 해결됨
_CANVAS_FONT_FAMILY: str = ""  # 빈문자열 = lazy init 미완료 (Rule I)


def _get_canvas_font() -> str:
    """
    [M609 Rule Q] canvas.py 전역 폰트 lazy 해결.
    QApplication 생성 이후 첫 호출 시 해결되어 모듈 변수에 캐시.
    """
    global _CANVAS_FONT_FAMILY
    if not _CANVAS_FONT_FAMILY:
        _CANVAS_FONT_FAMILY = _resolve_atom_font_family()
    return _CANVAS_FONT_FAMILY


# ========== 포터블 경로 ==========
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

# ========== [Phase Integration] 옵셔널 임포트 ==========
try:
    from phase_integration import PhaseIntegrationManager, attach_phase_integration
    PHASE_INTEGRATION_AVAILABLE = True
except ImportError:
    PHASE_INTEGRATION_AVAILABLE = False

try:
    from popup_3d import Molecule3DData, Molecule3DPopup
    PHASE_C_AVAILABLE = True
except ImportError:
    PHASE_C_AVAILABLE = False

try:
    from orca_interface import OrcaCalculationResult
    ORCA_AVAILABLE = True
except ImportError:
    ORCA_AVAILABLE = False


# ==========================================
# 유틸리티
# ==========================================
class CanvasMode:
    MAIN = "Drawing"    # 메인 그리기 화면
    LEWIS = "Lewis"     # 루이스 구조 레이어
    THEORY = "Theory"   # 이론적 구조 레이어


def get_coord_key(point):
    """0.01 단위 정밀도: 붙여넣기 시 미세 소수점 오차로 인한 분자 찌그러짐 방지"""
    return (round(point.x(), 2), round(point.y(), 2))


# ==========================================
# [P0-5 FIX] PubChem IUPAC명 비동기 조회 워커
# ==========================================
class _IUPACNameWorker(QThread):
    """백그라운드에서 SMILES→IUPAC명/관용명 조회 (UI 블로킹 방지).

    PubChem REST API 호출이 네트워크 지연/타임아웃 시 메인 스레드를
    차단하지 않도록 QThread에서 실행한다.
    IUPACName이 없는 대형 분자(헤모글로빈 등)는 Title(관용명)을 폴백으로 사용.
    """
    finished = pyqtSignal(str)  # resolved name (IUPAC 또는 관용명, 빈 문자열=실패)

    def __init__(self, smiles: str, parent: 'QWidget | None' = None) -> None:
        super().__init__(parent)
        self._smiles: str = smiles

    def run(self) -> None:
        """워커 스레드에서 실행: PubChem IUPAC+Title 조회 (timeout=5s)."""
        try:
            if _PC_CLIENT_AVAILABLE and _pc_client is not None:
                name = _pc_client.get_iupac_name_by_smiles(self._smiles)
                if name:
                    self.finished.emit(name)
                    return
            # pubchem_client 미사용 폴백: requests 직접 사용
            # IUPACName + Title 동시 요청 — 대형 분자는 IUPAC 없이 Title만 존재
            import requests
            import urllib.parse
            encoded = urllib.parse.quote(self._smiles, safe="")
            url = (
                f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/"
                f"compound/smiles/{encoded}/property/IUPACName,Title/JSON"
            )
            try:
                resp = requests.get(url, timeout=5)  # [MAGIC: 5s] PubChem IUPAC lookup
            except Exception as _ssl_e:
                _ssl_msg = str(_ssl_e)
                if "SSL" in type(_ssl_e).__name__ or "ssl" in _ssl_msg.lower() or "UNEXPECTED_EOF" in _ssl_msg:
                    logger.warning("[M1363] canvas PubChem SSL 오류 → verify=False 재시도: %s", _ssl_msg[:80])
                    try:
                        resp = requests.get(url, timeout=5, verify=False)
                    except Exception:
                        self.finished.emit("")
                        return
                else:
                    logger.warning("[M1363] canvas PubChem 오류: %s", _ssl_msg[:80])
                    self.finished.emit("")
                    return
            if resp is not None and resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, dict):
                    logger.warning("PubChem 응답이 dict가 아님: type=%s", type(data).__name__)
                    self.finished.emit("")
                    return
                prop_table = data.get("PropertyTable", {})
                if not isinstance(prop_table, dict):
                    logger.warning("PropertyTable이 dict가 아님: type=%s", type(prop_table).__name__)
                    self.finished.emit("")
                    return
                props = prop_table.get("Properties", [])
                if not isinstance(props, list):
                    logger.warning("Properties가 list가 아님: type=%s", type(props).__name__)
                    self.finished.emit("")
                    return
                if props:
                    p0 = props[0]
                    if isinstance(p0, dict):
                        iupac = p0.get("IUPACName", "")
                        title = p0.get("Title", "")
                        # IUPAC 우선, 없으면 Title(관용명) 폴백
                        if iupac:
                            self.finished.emit(iupac)
                            return
                        if title:
                            self.finished.emit(title)
                            return
                    else:
                        logger.warning("Properties[0]이 dict가 아님: type=%s", type(p0).__name__)
            self.finished.emit("")
        except Exception as e:
            logger.warning("PubChem IUPAC/Title name lookup failed (async): %s", e)
            self.finished.emit("")


# ==========================================
# MoleculeCanvas — 핵심 캔버스 엔진
# ==========================================
class MoleculeCanvas(QWidget):
    # [Phase 6-3] Theory 모드 분자 선택/해제 시그널
    molecule_selected = pyqtSignal(bool)  # True=선택됨, False=해제됨
    # [NEW] 분자 변경 시그널 — 상태바 MW/MF 업데이트용
    molecule_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.grid_size, self.snap_distance = 40, 25
        self.atom_radius, self.lone_pair_gap, self.radical_gap = 12, 10, 12
        self.scale_factor, self.pan_offset = 1.0, QPointF(0, 0)
        self.atoms, self.bonds, self.strokes = {}, {}, []
        self.undo_stack, self.redo_stack = [], []

        # ========== [v4 명령3] 반응 화살표 도구 (save_state 전에 초기화 필수) ==========
        self.arrows = []              # [(QPointF_start, QPointF_end), ...]
        self.arrow_drawing = False
        self.arrow_start = None
        self.arrow_ghost_end = None

        # ========== [v4 명령4] 텍스트 상자 도구 (save_state 전에 초기화 필수) ==========
        self.text_boxes = []
        self.text_editing_idx = None
        self.text_font_size = 12

        self.save_state()
        self.mode = "Bond"
        self.pen_color, self.pen_width = QColor(255, 0, 0), 2
        self.selected_atoms, self.selected_bonds = set(), set()
        self.selected_items = []
        self.clipboard, self.is_pasting = None, False
        self.current_start = self.current_end = self.selection_rect = self.drag_origin = None
        self.temp_stroke = []
        self.last_mouse_pos = QPointF(0, 0)

        # 분석 엔진 장착
        self.analyzer = ChemicalAnalyzer()
        self.analysis_results = None
        self.view_state = "Drawing"
        self.show_clouds = True

        self.lasso_mode = False
        self.lasso_points = []
        self.lasso_step = 5

        self._reveal_radius = 0
        self.reveal_center = QPointF(0, 0)

        # ========== [Phase Integration] Canvas 초기화 ==========
        self.phase_manager = None
        if PHASE_INTEGRATION_AVAILABLE:
            self.phase_manager = attach_phase_integration(self)

        # ========== DFT Electron Density Storage ==========
        self.dft_density_map = None
        self.show_dft_density = True

        # ========== ORCA Population Data (ElectronDist 레이어 전용) ==========
        # [M895 D888-W9] 사용자: "전자분포 레이어는 거의 무조건 ORCA 기반 표시"
        # __init__ 초기화 의무 — getattr fallback 없이 항상 접근 가능
        # ORCA 미설치 시: None → Gasteiger fallback (Rule GG 배너 표시)
        # ORCA 설치 시: dict {atom_idx: {"mulliken_charge": float, ...}}
        # Mulliken R.S. (1955) J.Chem.Phys 23:1833
        self.orca_population_data = None  # [M895] Rule I: 명시 초기화 (None = ORCA 없음)

        # ========== [Phase 6-3] Theory 모드 분자 선택 상태 ==========
        self.selected_molecule_keys = set()    # 선택된 분자의 모든 원자 키 집합
        self.selected_molecule_name = ""       # IUPAC명 또는 관용명
        self.selected_molecule_bbox = None     # QRectF 바운딩 박스
        self._name_fetch_pending = False       # PubChem 조회 중복 방지 플래그
        self._iupac_worker: '_IUPACNameWorker | None' = None  # [P0-5] 비동기 IUPAC 조회 워커
        # ── [BUG-03 Fix] SMILES 파이프라인 태그: 그리기/텍스트 입력 완료 시 저장
        # 모든 하위 파이프라인(이론적 구조, 3D, 분석)은 get_smiles() 대신 이 값 우선 사용
        self._last_drawn_smiles: str = ""       # 가장 최근에 확정된 SMILES
        self._last_drawn_mol_name: str = ""     # 분자명 (텍스트 입력 시 저장)

        # ========== [v4 명령3] 반응 화살표 도구 ==========
        self.arrows = []              # [(QPointF_start, QPointF_end), ...]
        self.arrow_drawing = False     # 화살표 드래그 중 플래그
        self.arrow_start = None        # 드래그 시작점
        self.arrow_ghost_end = None    # 고스트 끝점 (4방향 스냅)

        # ========== [v4 명령4] 텍스트 상자 도구 ==========
        self.text_boxes = []           # [{"pos": QPointF, "text": str, "font_size": int}, ...]
        self.text_editing_idx = None   # 현재 편집 중인 텍스트 박스 인덱스 (None=비활성)
        self.text_font_size = 12       # 기본 텍스트 크기

    # ------------------------------------------------------------------
    # 애니메이션 제어 속성
    # ------------------------------------------------------------------
    @pyqtProperty(float)
    def reveal_radius(self):
        return self._reveal_radius

    @reveal_radius.setter
    def reveal_radius(self, v):
        self._reveal_radius = v
        self.update()

    def start_reveal_animation(self, center_pt):
        """버튼 위치에서 원형으로 확장되는 부드러운 애니메이션"""
        self.reveal_center = QPointF(center_pt)
        self.anim = QPropertyAnimation(self, b"reveal_radius")
        self.anim.setDuration(1000)
        self.anim.setStartValue(0)
        max_r = math.hypot(self.width(), self.height()) * 1.0
        self.anim.setEndValue(max_r)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self._on_animation_finished)
        self.anim.start()

    def _on_animation_finished(self):
        self.update()

    # ------------------------------------------------------------------
    # 좌표 변환
    # ------------------------------------------------------------------
    def to_logical(self, pos):
        return (pos - self.pan_offset) / self.scale_factor

    def to_screen(self, pos):
        return (pos * self.scale_factor) + self.pan_offset

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------
    def save_state(self):
        self.undo_stack.append({
            "a": copy.deepcopy(self.atoms),
            "b": copy.deepcopy(self.bonds),
            "s": copy.deepcopy(self.strokes),
            "ar": copy.deepcopy(self.arrows),
            "tb": copy.deepcopy(self.text_boxes),
        })
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            st = self.undo_stack[-1]
            self.atoms = copy.deepcopy(st["a"])
            self.bonds = copy.deepcopy(st["b"])
            self.strokes = copy.deepcopy(st["s"])
            _ar_u = st.get("ar", []) if isinstance(st, dict) else []
            self.arrows = copy.deepcopy(_ar_u if isinstance(_ar_u, list) else [])
            _tb_u = st.get("tb", []) if isinstance(st, dict) else []
            self.text_boxes = copy.deepcopy(_tb_u if isinstance(_tb_u, list) else [])
            # [P0-FIX] Re-run analysis after undo to keep analysis_results in sync
            self.analysis_results = self.analyzer.analyze(self.atoms, self.bonds, smiles=getattr(self, '_last_drawn_smiles', None))
            self.on_molecule_updated()
            self.update()

    def redo(self):
        if self.redo_stack:
            st = self.redo_stack.pop()
            self.undo_stack.append(copy.deepcopy(st))
            self.atoms = copy.deepcopy(st["a"])
            self.bonds = copy.deepcopy(st["b"])
            self.strokes = copy.deepcopy(st["s"])
            _ar_r = st.get("ar", []) if isinstance(st, dict) else []
            self.arrows = copy.deepcopy(_ar_r if isinstance(_ar_r, list) else [])
            _tb_r = st.get("tb", []) if isinstance(st, dict) else []
            self.text_boxes = copy.deepcopy(_tb_r if isinstance(_tb_r, list) else [])
            # [P0-FIX] Re-run analysis after redo to keep analysis_results in sync
            self.analysis_results = self.analyzer.analyze(self.atoms, self.bonds, smiles=getattr(self, '_last_drawn_smiles', None))
            self.on_molecule_updated()
            self.update()

    # ------------------------------------------------------------------
    # [D_M804_B3 #04 (2026-05-05)] 루이스-골격구조 전환 시 분자 깨짐 방지
    # ------------------------------------------------------------------
    def refresh_analysis_for_view_switch(self, target_mode: str) -> bool:
        """
        뷰 전환(Drawing/Lewis/Theory) 시 analysis_results 재생성.

        사용자 격분 #04: "Lewis = 진짜 루이스 구조식, 골격구조식 아님. 변환 시 분자 깨짐"
        원인 분석: 사용자가 atoms/bonds를 편집한 후 commit_state 호출 전 view 전환하면
        analysis_results가 stale 상태 → h_count/lp_count 누락 → 빈 lewis 렌더링.

        해결: view 전환 진입 시 atoms/bonds 존재하면 analyze() 강제 재실행.
        Rule L: MolFromSmiles + None 체크 (SMILES 무결성 확인).
        Rule M: 실패 시 logger.warning + status (silent failure 금지).
        Rule N: isinstance() 가드.

        Args:
            target_mode: "Drawing"/"Lewis"/"Theory"/"ElectronDist"

        Returns:
            bool: 분석 갱신 성공 여부 (False=경고 표시 필요)
        """
        # 원자 없으면 갱신 불필요
        if not self.atoms or not isinstance(self.atoms, dict):
            return True
        # bonds 없는 단일 원자도 분석 가능 — 단 빈 dict는 통과
        if not isinstance(self.bonds, dict):
            self.bonds = {}

        try:
            _smiles_pre = getattr(self, '_last_drawn_smiles', '') or ''

            # Rule L: SMILES 사전 검증 — 깨진 SMILES면 None 폴백
            if _smiles_pre:
                try:
                    from rdkit import Chem
                    _verify_mol = Chem.MolFromSmiles(_smiles_pre)
                    if _verify_mol is None:
                        logger.warning(
                            "[D_M804_B3] SMILES 검증 실패 — 폴백 사용: %r", _smiles_pre[:60]
                        )
                        _smiles_pre = ''  # 깨진 SMILES → analyze가 atoms/bonds로 재구성
                except Exception as _ev:
                    logger.warning("[D_M804_B3] RDKit 검증 예외: %s", _ev)
                    _smiles_pre = ''

            # 분석 실행 — 실패 시 silent하게 stale 결과 유지하지 않음
            new_analysis = self.analyzer.analyze(
                self.atoms, self.bonds,
                smiles=_smiles_pre if _smiles_pre else None
            )
            if new_analysis is None or not isinstance(new_analysis, dict):
                logger.warning(
                    "[D_M804_B3] analyze() 빈 결과 — 기존 analysis_results 유지 (mode=%s)",
                    target_mode
                )
                return False

            self.analysis_results = new_analysis
            # smiles 키 보존 (Lewis renderer 의존)
            if _smiles_pre and self.analysis_results.get("smiles", "") == "":
                self.analysis_results["smiles"] = _smiles_pre
            logger.debug(
                "[D_M804_B3] view 전환 analysis 갱신 OK mode=%s atoms=%d bonds=%d",
                target_mode, len(self.atoms), len(self.bonds)
            )
            return True
        except Exception as _ex:
            # Rule M: silent failure 금지 — 격분 사례에서 silent 폴백 금지
            logger.warning(
                "[D_M804_B3] view 전환 analysis 갱신 실패 (mode=%s): %s",
                target_mode, _ex
            )
            return False

    # ------------------------------------------------------------------
    # 그리드 스냅
    # ------------------------------------------------------------------
    def _draw_2d_electron_clouds(self, painter, use_theory_coords: bool = True) -> bool:
        """Draw the 2D ESP/electron-cloud layer when the UI toggle is enabled."""
        if not self.show_clouds:
            return False
        if not isinstance(self.analysis_results, dict):
            logger.warning(
                "[W-2D-ELECTRON-CLOUD] show_clouds ON but analysis_results is %s",
                type(self.analysis_results).__name__,
            )
            return False

        charges = self.analysis_results.get("charges")
        if not isinstance(charges, dict) or not charges:
            logger.warning(
                "[W-2D-ELECTRON-CLOUD] show_clouds ON but charges missing/empty"
            )
            return False

        theory_data = self.analysis_results.get("theory_data")
        effective_theory_coords = use_theory_coords and isinstance(theory_data, dict)
        if use_theory_coords and not effective_theory_coords:
            logger.warning(
                "[W-2D-ELECTRON-CLOUD] theory_data missing; drawing clouds in canvas coordinates"
            )

        CloudRenderer.draw_esp_isosurface(
            painter,
            self.analysis_results,
            use_theory_coords=effective_theory_coords,
        )
        return True

    def _theory_cloud_uses_fallback_source(self) -> bool:
        """Return True when the Theory cloud lacks ORCA/xTB/ESP-grid provenance."""
        if not isinstance(self.analysis_results, dict):
            return False

        source_keys = (
            "electron_cloud_source",
            "charge_source",
            "charge_method",
            "esp_source",
            "density_source",
        )
        for key in source_keys:
            source = self.analysis_results.get(key)
            if not isinstance(source, str):
                continue
            normalized = source.strip().lower()
            if not normalized:
                continue
            fallback_tokens = ("gasteiger", "heuristic", "custom", "simulation", "fallback")
            if any(token in normalized for token in fallback_tokens):
                return True
            real_tokens = ("orca", "xtb", "esp grid", "dft mep", "dft_mep")
            if any(token in normalized for token in real_tokens):
                return False

        # The current 2D Theory cloud consumes analyzer["charges"], which are
        # Gasteiger/custom heuristic values unless a future provenance rework
        # marks a real ORCA/xTB/ESP-grid source explicitly.
        return True

    def _draw_theory_cloud_fallback_banner(self, painter) -> None:
        """Draw a screen-fixed disclosure for heuristic Theory cloud data."""
        painter.save()
        try:
            painter.setClipping(False)
            painter.resetTransform()
            try:
                dev_w = float(painter.device().width())  # type: ignore[union-attr]
            except Exception as exc:
                logger.warning(
                    "[W-2D-ELECTRON-CLOUD] banner device width fallback: %s", exc
                )
                dev_w = 800.0

            banner_x = 10.0  # [MAGIC:10px] fixed screen margin.
            banner_y = 34.0  # [MAGIC:34px] below the existing Theory label.
            banner_w = max(260.0, min(dev_w - 20.0, 680.0))
            banner_h = 44.0  # [MAGIC:44px] two compact disclosure lines.
            rect = QRectF(banner_x, banner_y, banner_w, banner_h)

            painter.setOpacity(0.94)
            painter.setPen(QPen(QColor(155, 96, 0), 1.2))
            painter.setBrush(QBrush(QColor(255, 242, 170, 232)))
            painter.drawRoundedRect(rect, 5.0, 5.0)

            font = QFont(_get_canvas_font(), 8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(92, 58, 0))
            line1 = "SIMULATION_MODE: 2D Theory cloud uses Gasteiger/custom heuristic charges"
            line2 = "Not ORCA/xTB/ESP grid; learning visualization only"
            text_x = banner_x + 8.0  # [MAGIC:8px] inner text padding.
            painter.drawText(QPointF(text_x, banner_y + 17.0), line1)
            painter.drawText(QPointF(text_x, banner_y + 35.0), line2)
        finally:
            painter.restore()

    def get_closest_pt(self, l_pos, strict=True):
        rh = self.grid_size * 0.866
        r = round(l_pos.y() / rh)
        off = self.grid_size / 2 if r % 2 != 0 else 0
        c = round((l_pos.x() - off) / self.grid_size)
        pt = QPointF(c * self.grid_size + off, r * rh)
        if strict and math.hypot(pt.x() - l_pos.x(), pt.y() - l_pos.y()) >= self.snap_distance:
            return None
        return pt

    def get_bond_gap(self, pt_key, vec):
        """결합선이 원소 기호나 치환기로부터 얼마나 떨어져야 하는지 계산"""
        if pt_key not in self.atoms:
            return 0
        at = self.atoms[pt_key]
        if at["main"]:
            font = QFont(_get_canvas_font(), 12, QFont.Weight.Bold)  # [M609]
            fm = QFontMetrics(font)
            text_width = fm.horizontalAdvance(at["main"])
            text_height = fm.height()
            base_gap = max(text_width, text_height) / 2
            return base_gap + 8
        if -1 in at["attach"]:
            return self.atom_radius
        d = round((math.degrees(math.atan2(vec.y(), vec.x())) % 360) / 60) % 6
        if d in at["attach"]:
            return self.radical_gap
        return 0

    # ------------------------------------------------------------------
    # 수동 정리 (180° 직선화)
    # ------------------------------------------------------------------
    def manual_clean_up(self):
        """고리 보호 및 확장 옥텟(S, P 등) 보정 예외 적용"""
        self.save_state()
        for _pass in range(2):
            neighbors = {}
            for k, val in self.bonds.items():
                p1, p2 = k
                if p1 not in neighbors:
                    neighbors[p1] = []
                if p2 not in neighbors:
                    neighbors[p2] = []
                neighbors[p1].append((p2, val))
                neighbors[p2].append((p1, val))

            # 고리 감지 (DFS) — Rule N: 타입 가드
            assert isinstance(neighbors, dict)
            ring_atoms = set()

            def is_ring(curr, target, visited, parent):
                visited.add(curr)
                for n_data in neighbors.get(curr, []):
                    n = n_data[0]
                    if n == parent:
                        continue
                    if n == target:
                        return True
                    if n not in visited and is_ring(n, target, visited, curr):
                        return True
                return False

            for atom_key in neighbors.keys():
                if len(neighbors[atom_key]) >= 2 and is_ring(atom_key, atom_key, set(), None):
                    ring_atoms.add(atom_key)

            for center, adj in neighbors.items():
                if center in ring_atoms or len(adj) != 2:
                    continue
                orders = [v if isinstance(v, int) else 1 for _, v in adj]
                if (orders.count(2) >= 2 or orders.count(3) >= 1) and len(adj) >= 2:
                    p1_key, p2_key = adj[0][0], adj[1][0]
                    c_pt, p1_pt = QPointF(*center), QPointF(*p1_key)
                    ang1 = math.atan2(p1_pt.y() - c_pt.y(), p1_pt.x() - c_pt.x())
                    new_p2_pt = c_pt + QPointF(
                        math.cos(ang1 + math.pi) * self.grid_size,
                        math.sin(ang1 + math.pi) * self.grid_size,
                    )
                    new_key = get_coord_key(new_p2_pt)
                    if p2_key in self.atoms:
                        self.atoms[new_key] = self.atoms.pop(p2_key)
                    for bk in list(self.bonds.keys()):
                        if p2_key in bk:
                            other = bk[0] if bk[1] == p2_key else bk[1]
                            v = self.bonds.pop(bk)
                            self.bonds[tuple(sorted((other, new_key)))] = v
        self.update()

    # ------------------------------------------------------------------
    # 마우스 이벤트
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        self.last_mouse_pos = event.position()
        l_pos = self.to_logical(self.last_mouse_pos)
        closest = self.get_closest_pt(l_pos)

        if self.mode == "Pen":
            self.window().pen_ui.hide()

        if self.is_pasting and self.clipboard and event.button() == Qt.MouseButton.LeftButton:
            self.finalize_paste(l_pos)
            return

        if self.mode == "Select" and event.button() == Qt.MouseButton.LeftButton:
            # [Phase 6-3 FIX] Theory 모드: 단일 분자 선택 (이전 블록의 early return으로 인해 실행 불가였던 버그 수정)
            if self.view_state == "Theory":
                clicked_atom = self._find_atom_at_theory(l_pos)
                if clicked_atom is not None:
                    self._select_molecule_at(clicked_atom)
                else:
                    # 빈 영역(바닥) 클릭 → 선택 해제
                    if self.selected_molecule_keys:
                        self._deselect_molecule()
            elif self.view_state != "Theory":
                # Theory 모드가 아니면 선택 해제
                if self.selected_molecule_keys:
                    self._deselect_molecule()

            self.drag_origin = l_pos
            self.selection_rect = QRectF(l_pos, QSizeF(0, 0))
            self.selected_atoms.clear()
            self.selected_bonds.clear()
            self.update()
            return

        if event.button() in [Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton] or self.mode == "Hand":
            self.drag_origin = event.position()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.save_state()
            if self.mode in ["Bond", "Wedge", "Dash"]:
                for k, v in list(self.bonds.items()):
                    mid = (QPointF(*k[0]) + QPointF(*k[1])) / 2
                    if math.hypot(mid.x() - l_pos.x(), mid.y() - l_pos.y()) < 15 / self.scale_factor:
                        if self.mode == "Bond":
                            order = v if isinstance(v, int) else 1
                            self.bonds[k] = (order % 3) + 1
                        elif self.mode == "Wedge":
                            self.bonds[k] = (QPointF(*k[0]), QPointF(*k[1]), "Wedge")
                        elif self.mode == "Dash":
                            self.bonds[k] = (QPointF(*k[0]), QPointF(*k[1]), "Dash")
                        self.update()
                        return
                if closest:
                    self.current_start = self.current_end = closest

            elif self.mode in ["LonePair", "Radical", "Positive", "Negative", "H"] and closest:
                k = get_coord_key(closest)
                dx, dy = l_pos.x() - closest.x(), l_pos.y() - closest.y()
                if k not in self.atoms:
                    self.atoms[k] = {"main": "", "attach": {}}

                # [v4 명령1] Positive/Negative → charge 필드에 저장 (main 보존)
                if self.mode in ["Positive", "Negative"]:
                    charge_sym = "+" if self.mode == "Positive" else "-"
                    self.atoms[k]["charge"] = charge_sym
                elif self.mode == "H" and self.atoms[k]["main"] == "" and math.hypot(dx, dy) < 12:
                    self.atoms[k]["main"] = "H"
                else:
                    d = round((math.degrees(math.atan2(dy, dx)) % 360) / 60) % 6
                    sym_map = {"LonePair": "..", "Radical": "·", "H": "H"}
                    self.atoms[k]["attach"][d] = sym_map[self.mode]
                    # [v4 명령5] LonePair → user_lp 플래그 추가 (사용자가 그린 비공유전자쌍 구분)
                    if self.mode == "LonePair":
                        if "user_lp" not in self.atoms[k]:
                            self.atoms[k]["user_lp"] = set()
                        self.atoms[k]["user_lp"].add(d)

            # [v4 명령3] Arrow 모드: 화살표 드래그 시작
            elif self.mode == "Arrow":
                self.arrow_start = l_pos
                self.arrow_drawing = True
                self.arrow_ghost_end = l_pos

            # [v4 명령4] Text 모드: 텍스트 상자 생성 또는 기존 선택
            elif self.mode == "Text":
                self._handle_text_click(l_pos)

            elif self.mode == "Eraser":
                self.erase(l_pos)

            elif self.mode == "Pen":
                self.temp_stroke = [l_pos]

            elif closest:
                k = get_coord_key(closest)
                self.atoms[k] = {"main": self.mode, "attach": {}}
        self.update()

    def mouseMoveEvent(self, event):
        curr_pos = event.position()
        l_pos = self.to_logical(curr_pos)

        if self.mode == "Eraser" and event.buttons() & Qt.MouseButton.LeftButton:
            self.erase(l_pos)

        if (
            (event.buttons() & Qt.MouseButton.RightButton)
            or (event.buttons() & Qt.MouseButton.MiddleButton)
            or (event.buttons() & Qt.MouseButton.LeftButton and self.mode == "Hand")
        ):
            self.pan_offset += curr_pos - self.last_mouse_pos

        elif event.buttons() & Qt.MouseButton.LeftButton and self.mode == "Select" and self.drag_origin:
            self.selection_rect = QRectF(self.drag_origin, l_pos).normalized()

            if self.view_state in ["Lewis", "Theory"]:
                _td_sel = self.analysis_results.get("theory_data", {}) if isinstance(self.analysis_results, dict) else {}
                t_map = _td_sel.get("map", {}) if isinstance(_td_sel, dict) else {}
                if not isinstance(t_map, dict):
                    t_map = {}
                self.selected_atoms = set()
                for k in self.atoms:
                    # [FIX-SELECT] Theory 좌표 + 원본 좌표 양쪽 모두 체크
                    # 좌표 변환 미세 불일치로 인한 선택 누락 방지
                    _rk = (round(k[0], 2), round(k[1], 2))
                    pt_theory = t_map.get(_rk) or t_map.get(k)
                    pt_orig = QPointF(*k)
                    # Theory 좌표 또는 원본 좌표 중 하나라도 rect 안이면 선택
                    hit = False
                    if pt_theory and self.selection_rect.contains(pt_theory):
                        hit = True
                    if not hit and self.selection_rect.contains(pt_orig):
                        hit = True
                    if hit:
                        self.selected_atoms.add(k)
                self.selected_bonds = set()
                assert isinstance(t_map, dict)  # Rule N: 타입 가드
                for k in self.bonds:
                    _rk0 = (round(k[0][0], 2), round(k[0][1], 2))
                    _rk1 = (round(k[1][0], 2), round(k[1][1], 2))
                    p1 = t_map.get(_rk0) or t_map.get(k[0]) or QPointF(*k[0])
                    p2 = t_map.get(_rk1) or t_map.get(k[1]) or QPointF(*k[1])
                    mid = (p1 + p2) / 2
                    if self.selection_rect.contains(mid):
                        self.selected_bonds.add(k)
                self.selected_items = [
                    {"type": "atom", "key": k, "data": self.atoms[k]} for k in self.selected_atoms
                ] + [
                    {"type": "bond", "key": k, "data": self.bonds[k]} for k in self.selected_bonds
                ]
            else:
                self.selected_atoms = {
                    k for k in self.atoms if self.selection_rect.contains(QPointF(*k))
                }
                self.selected_bonds = set()
                for k in self.bonds:
                    mid = (QPointF(*k[0]) + QPointF(*k[1])) / 2
                    if self.selection_rect.contains(mid):
                        self.selected_bonds.add(k)
                self.selected_items = [
                    {"type": "atom", "key": k, "data": self.atoms[k]} for k in self.selected_atoms
                ] + [
                    {"type": "bond", "key": k, "data": self.bonds[k]} for k in self.selected_bonds
                ]

        elif self.mode == "Pen" and self.temp_stroke:
            self.temp_stroke.append(l_pos)

        elif self.mode in ["Bond", "Wedge", "Dash"] and self.current_start:
            t = self.get_closest_pt(l_pos)
            self.current_end = t if t else l_pos

        # [v4 명령3] Arrow 모드: 고스트 — 동서남북 4방향 스냅
        elif self.mode == "Arrow" and self.arrow_drawing and self.arrow_start:
            dx = l_pos.x() - self.arrow_start.x()
            dy = l_pos.y() - self.arrow_start.y()
            if abs(dx) >= abs(dy):
                self.arrow_ghost_end = QPointF(l_pos.x(), self.arrow_start.y())
            else:
                self.arrow_ghost_end = QPointF(self.arrow_start.x(), l_pos.y())

        self.last_mouse_pos = curr_pos
        self.update()

    def mouseReleaseEvent(self, event):
        # Lasso 선택
        if self.lasso_mode and self.lasso_points:
            polygon = QPolygonF(self.lasso_points)
            self.selected_atoms = {
                k
                for k in self.atoms
                if polygon.containsPoint(QPointF(*k), Qt.FillRule.WindingFill)
            }
            self.selected_bonds = set()
            for k in self.bonds:
                mid = (QPointF(*k[0]) + QPointF(*k[1])) / 2
                if polygon.containsPoint(mid, Qt.FillRule.WindingFill):
                    self.selected_bonds.add(k)
            self.lasso_points = []
            self.lasso_mode = False
            self.update()
            return

        if self.selection_rect:
            # [FIX 3D-2] Theory 모드: 단순 클릭 vs 드래그 선택 분리 처리
            # 핵심 버그: 단순 클릭 시 selection_rect = QRectF(l_pos, QSizeF(0,0)) 가 생성됨
            #           → PyQt6 객체는 항상 truthy → 이 블록이 실행됨
            #           → selected_atoms는 mousePressEvent에서 .clear()된 상태 → False
            #           → _deselect_molecule() 즉시 호출 → btn_3d 즉시 비활성화!
            # 수정: 면적 임계값으로 실제 드래그인지 판별, 단순 클릭은 mousePressEvent에서 이미 처리됨
            if self.view_state == "Theory":
                is_drag_select = (
                    self.selection_rect.width() > 5 or self.selection_rect.height() > 5
                )
                if is_drag_select:
                    # 드래그 선택: selected_atoms 기반으로 처리
                    if self.selected_atoms:
                        # [FIX] 드래그로 일부만 잡혀도 BFS 확장하여 연결된 전체 분자 선택
                        # 좌표 미세 불일치로 일부 원자만 rect 안에 들어오는 경우 대응
                        from collections import deque
                        adj = {}
                        for (a, b) in self.bonds:
                            adj.setdefault(a, set()).add(b)
                            adj.setdefault(b, set()).add(a)
                        expanded = set()
                        for seed in self.selected_atoms:
                            if seed in expanded:
                                continue
                            queue = deque([seed])
                            while queue:
                                curr = queue.popleft()
                                if curr in expanded:
                                    continue
                                expanded.add(curr)
                                # Rule N: isinstance guard for adj
                                if not isinstance(adj, dict): adj = {}
                                for nb in adj.get(curr, set()):
                                    if nb not in expanded:
                                        queue.append(nb)
                        self.selected_molecule_keys = expanded
                        self._compute_molecule_bbox()
                        self._fetch_molecule_name()
                        self.molecule_selected.emit(True)
                        logger.debug("드래그 선택: %d개 직접 → BFS 확장 %d개 원자", len(self.selected_atoms), len(expanded))
                    else:
                        # 빈 영역 드래그 → 선택 해제
                        if self.selected_molecule_keys:
                            self._deselect_molecule()
                # else: 단순 클릭(면적<5px) → mousePressEvent에서 이미 선택/해제 처리됨 → 아무것도 하지 않음
            self.selection_rect = self.drag_origin = None

        elif self.mode in ["Bond", "Wedge", "Dash"] and self.current_start and self.current_end:
            snap_end = self.get_closest_pt(self.current_end)
            if snap_end and self.current_start != snap_end:
                k1 = get_coord_key(self.current_start)
                k2 = get_coord_key(snap_end)
                for b_key in list(self.bonds.keys()):
                    if (k1 in b_key) and (k2 in b_key):
                        self.bonds.pop(b_key)
                        break
                if self.mode == "Bond":
                    k = tuple(sorted((k1, k2)))
                    self.bonds[k] = 1
                else:
                    k = (k1, k2)
                    self.bonds[k] = (self.current_start, snap_end, self.mode)
            self.current_start = self.current_end = None

        elif self.mode == "Pen" and self.temp_stroke:
            self.strokes.append({"pts": self.temp_stroke, "clr": self.pen_color, "w": self.pen_width})
            self.temp_stroke = []

        # [v4 명령3] Arrow 모드: 드래그 종료 → 화살표 확정
        elif self.mode == "Arrow" and self.arrow_drawing and self.arrow_start and self.arrow_ghost_end:
            dist = math.hypot(
                self.arrow_ghost_end.x() - self.arrow_start.x(),
                self.arrow_ghost_end.y() - self.arrow_start.y(),
            )
            if dist > 10:  # 최소 길이 필터 (너무 짧은 화살표 방지)
                self.arrows.append((QPointF(self.arrow_start), QPointF(self.arrow_ghost_end)))
            self.arrow_drawing = False
            self.arrow_start = None
            self.arrow_ghost_end = None

        # ★ [FIX] 수동 그리기 후 _last_drawn_smiles 자동 갱신
        # 텍스트 입력은 main_window에서 설정하지만, 수동 그리기는 여기서 설정해야
        # Theory 모드 전환 시 분자 인식/선택이 작동함
        if self.atoms and self.bonds:
            try:
                _auto_smiles = self.get_smiles()
                if _auto_smiles and _auto_smiles not in ('C', ''):
                    self._last_drawn_smiles = _auto_smiles
                    logger.debug("수동 그리기 SMILES 자동 저장: %s", _auto_smiles[:60])
            except Exception as _e:
                logger.warning("수동 그리기 SMILES 추출 실패: %s", _e)

        self.analysis_results = self.analyzer.analyze(self.atoms, self.bonds, smiles=getattr(self, '_last_drawn_smiles', None))
        self.on_molecule_updated()
        self.save_current_smiles() # [Tutor] 상태 저장
        self.update()

    # ------------------------------------------------------------------
    # [Tutor Integration] 상태 내보내기
    # ------------------------------------------------------------------
    def save_current_smiles(self):
        """현재 캔버스의 상태(SMILES)를 파일로 저장하여 외부 프로세스(Tutor)가 읽을 수 있게 함."""
        try:
            smiles = self.get_smiles()
            # C:\chemgrid\current_state.json
            path = os.path.join("c:/chemgrid", "current_state.json")
            import json
            with open(path, "w") as f:
                json.dump({"smiles": smiles, "atom_count": len(self.atoms)}, f)
        except Exception as e:
            logger.warning("Failed to save state: %s", e)

    # ------------------------------------------------------------------
    # 키보드
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        # [v4 명령4] Text 모드 + 편집 중: 키 입력을 텍스트 상자에 전달
        if self.mode == "Text" and self.text_editing_idx is not None:
            idx = self.text_editing_idx
            if 0 <= idx < len(self.text_boxes):
                if event.key() == Qt.Key.Key_Backspace:
                    if self.text_boxes[idx]["text"]:
                        self.text_boxes[idx]["text"] = self.text_boxes[idx]["text"][:-1]
                elif event.key() == Qt.Key.Key_Return:
                    self.text_editing_idx = None  # Enter → 편집 종료
                elif event.key() == Qt.Key.Key_Escape:
                    self.text_editing_idx = None  # Esc → 편집 종료
                elif event.text() and not ctrl:
                    self.text_boxes[idx]["text"] += event.text()
                self.update()
                return

        if ctrl and event.key() == Qt.Key.Key_C:
            self.copy_selection()
        elif ctrl and event.key() == Qt.Key.Key_V:
            self.is_pasting = True
        elif ctrl and event.key() == Qt.Key.Key_X:
            self.copy_selection()
            self.delete_selection()
        elif ctrl and event.key() == Qt.Key.Key_Z:
            self.undo()
        elif ctrl and event.key() == Qt.Key.Key_Y:
            self.redo()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selection()
        # [UC-R01] 결합 타입 빠른 전환 단축키: B=Bond, W=Wedge, D=Dash
        elif not ctrl and event.key() == Qt.Key.Key_B:
            self.mode = "Bond"
            self._notify_mode_change()
        elif not ctrl and event.key() == Qt.Key.Key_W:
            self.mode = "Wedge"
            self._notify_mode_change()
        elif not ctrl and event.key() == Qt.Key.Key_D:
            self.mode = "Dash"
            self._notify_mode_change()
        self.update()

    # ------------------------------------------------------------------
    # 선택 / 복사 / 붙여넣기
    # ------------------------------------------------------------------
    def delete_selection(self):
        if self.selected_atoms or self.selected_bonds:
            self.save_state()
            for k in list(self.selected_atoms):
                self.atoms.pop(k, None)
            for k in list(self.selected_bonds):
                self.bonds.pop(k, None)
            self.selected_atoms.clear()
            self.selected_bonds.clear()

    def copy_selection(self):
        """선택 영역의 좌측 상단 실제 원자를 기준점으로 설정"""
        if not (self.selected_atoms or self.selected_bonds):
            logger.warning("복사 실패: 선택된 원자/결합이 없음")
            return
        pts = [QPointF(*k) for k in self.selected_atoms]
        if not pts:
            for bk in self.selected_bonds:
                pts.extend([QPointF(*bk[0]), QPointF(*bk[1])])
        anchor_node = sorted(pts, key=lambda p: (p.y(), p.x()))[0]
        ref = anchor_node
        self.clipboard = {"a": [], "b": []}
        for k in self.selected_atoms:
            pt = QPointF(*k)
            self.clipboard["a"].append(((pt.x() - ref.x(), pt.y() - ref.y()), self.atoms[k]))
        for k in self.selected_bonds:
            bt = self.bonds[k]
            p1, p2 = (bt[0], bt[1]) if isinstance(bt, tuple) else (QPointF(*k[0]), QPointF(*k[1]))
            self.clipboard["b"].append((
                ((p1.x() - ref.x(), p1.y() - ref.y()), (p2.x() - ref.x(), p2.y() - ref.y())),
                bt,
            ))

    def finalize_paste(self, l_pos):
        """웨지/대쉬의 방향 정보와 그리드 스냅을 동기화하여 붙여넣기"""
        if not self.clipboard:
            logger.warning("붙여넣기 실패: 클립보드가 비어있음")
            return
        self.save_state()
        snap_anchor = self.get_closest_pt(l_pos) or l_pos
        for rel, data in self.clipboard["a"]:
            new_pos = snap_anchor + QPointF(*rel)
            self.atoms[get_coord_key(new_pos)] = copy.deepcopy(data)
        for rel_b, bt in self.clipboard["b"]:
            p1_n = snap_anchor + QPointF(*rel_b[0])
            p2_n = snap_anchor + QPointF(*rel_b[1])
            new_bt = copy.deepcopy(bt)
            if isinstance(new_bt, tuple):
                new_bt = (p1_n, p2_n, new_bt[2])
            self.bonds[(get_coord_key(p1_n), get_coord_key(p2_n))] = new_bt
        self.is_pasting = False
        self.update()

    # ------------------------------------------------------------------
    # 줌 / 팬
    # ------------------------------------------------------------------
    def wheelEvent(self, event):
        zoom = 1.15 if event.angleDelta().y() > 0 else 0.85
        l_pos = self.to_logical(event.position())
        self.scale_factor = max(0.1, min(self.scale_factor * zoom, 10.0))
        self.pan_offset = event.position() - l_pos * self.scale_factor
        self.update()

    # ------------------------------------------------------------------
    # Phase Integration 훅
    # ------------------------------------------------------------------
    def on_molecule_updated(self):
        """Hook 2: 분자 수정 감지 → Phase B-D 업데이트 트리거 + 상태바 갱신"""
        if self.phase_manager:
            try:
                self.phase_manager.on_molecule_updated(self.atoms, self.bonds, self.analysis_results)
            except Exception as e:
                logger.warning("Phase integration molecule update failed: %s", e)
        # [NEW] 분자 변경 시그널 발송 → MainWindow 상태바 MW/MF 갱신
        self.molecule_changed.emit()

    def on_theory_layer_interaction(self):
        """Hook 3: Theory layer 상호작용 → 3D 팝업 트리거"""
        if self.phase_manager and self.analysis_results and isinstance(self.analysis_results, dict):
            try:
                theory_data = self.analysis_results.get("theory_data", {})
                if not isinstance(theory_data, dict):
                    theory_data = {}
                self.phase_manager.on_theory_layer_interaction(self.atoms, self.bonds, theory_data)
            except Exception as e:
                logger.warning("Phase integration theory interaction failed: %s", e)

    def _notify_mode_change(self):
        """[UC-R01] 키보드 단축키로 모드 변경 시 부모 MainWindow의 툴바 상태를 동기화"""
        win = self.window()
        if win and hasattr(win, 'tb'):
            for action in win.tb.actions():
                if action.text() == self.mode and action.isCheckable():
                    action.setChecked(True)
                    break

    def on_orca_calculation_complete(self, orca_result):
        """Hook 4: ORCA 계산 완료 → ESP 시각화 + DFT 전자 밀도 분석"""
        self._analyze_dft_electron_density(orca_result)
        if self.phase_manager:
            try:
                self.phase_manager.on_orca_calculation_complete(orca_result)
            except Exception as e:
                logger.warning("Phase integration ORCA calculation handler failed: %s", e)

    def _analyze_dft_electron_density(self, orca_result):
        """ORCA DFT 결과에서 전자 밀도 분석.

        [CHEM-4] mulliken_charges 직접 연동 우선 (OrcaOutputParser 결과 딕셔너리 활용).
        ElectronDensityAnalyzer 파일 파싱은 Fallback으로만 사용.
        """
        try:
            # ── [CHEM-4 우선순위 1] orca_result 딕셔너리에서 mulliken_charges 직접 추출 ──
            mulliken_charges = None
            if isinstance(orca_result, dict):
                mulliken_charges = orca_result.get("mulliken_charges")

            if mulliken_charges is not None:
                # atom 정렬: y좌표 오름차순 → x좌표 오름차순 (캔버스 그리기 순서 일치)
                atom_list = sorted(
                    self.atoms.items(),
                    key=lambda kv: (round(kv[0][1], 0), round(kv[0][0], 0))
                )
                direct_map = {}

                if isinstance(mulliken_charges, dict):
                    # {atom_idx: charge} 형식
                    for i, (coord_key, _) in enumerate(atom_list):
                        if i in mulliken_charges:
                            direct_map[coord_key] = mulliken_charges[i]
                elif isinstance(mulliken_charges, (list, tuple)):
                    # [charge0, charge1, ...] 형식
                    for i, (coord_key, _) in enumerate(atom_list):
                        if i < len(mulliken_charges):
                            direct_map[coord_key] = float(mulliken_charges[i])

                if direct_map:
                    self.dft_density_map = direct_map
                    self.update()
                    return  # 직접 연동 성공 → 파일 파싱 불필요

            # ── [CHEM-4 Fallback] ElectronDensityAnalyzer를 이용한 파일 파싱 ──
            from electron_density_analyzer import ElectronDensityAnalyzer

            # [C5 수정] 하드코딩 절대 경로 제거 → __file__ 기반 상대 경로
            orca_out_candidates = [
                _SCRIPT_DIR / "orca_calcs" / "input.out",
                _SCRIPT_DIR / "input.out",
            ]

            orca_out_path = None
            for candidate in orca_out_candidates:
                if candidate.exists():
                    orca_out_path = candidate
                    break

            if not orca_out_path:
                logger.debug("ORCA output file unavailable for density fallback: %s", [str(c) for c in orca_out_candidates])
                return

            atom_positions = {}
            atom_symbols = {}
            for coord_key, atom_data in self.atoms.items():
                if not isinstance(atom_data, dict):
                    continue
                atom_idx = len(atom_positions)
                atom_symbol = atom_data.get("main", "")  # Rule I: Carbon = empty string
                atom_positions[coord_key] = atom_idx
                atom_symbols[atom_idx] = atom_symbol

            analyzer = ElectronDensityAnalyzer()
            density_map = analyzer.analyze_orca_output(
                out_path=orca_out_path,
                atom_positions=atom_positions,
                atom_symbols=atom_symbols,
                detect_resonance=True,
            )
            self.dft_density_map = density_map

            # [C3 수정] self.canvas.repaint -> self.update()
            self.update()

        except ImportError as e:
            logger.debug("DFT density analyzer not available: %s", e)
        except Exception as e:
            logger.warning("DFT electron density analysis failed: %s", e)

    def cleanup(self):
        """Hook 5: 종료 시 QThread·팝업 정리"""
        if self.phase_manager:
            try:
                self.phase_manager.cleanup()
            except Exception as e:
                logger.warning("Phase integration cleanup failed: %s", e)

    def get_smiles(self):
        """현재 캔버스의 분자를 SMILES로 변환"""
        try:
            if not self.atoms:
                return "C"
            from rdkit import Chem

            editmol = Chem.RWMol(Chem.Mol())
            coord_to_idx = {}
            
            # [Fix] 결합 차수 계산 (고립된 빈 원자 무시용)
            degrees = {}
            for (k1, k2) in self.bonds.keys():
                degrees[k1] = degrees.get(k1, 0) + 1
                degrees[k2] = degrees.get(k2, 0) + 1

            for coord_key, atom_data in self.atoms.items():
                if not isinstance(atom_data, dict):
                    continue
                element = atom_data.get("main", "")

                # [FIX] 결합이 없는 고립 원자 제외 (Lewis 표시용 잡음 원자 방지)
                # - 원소 없고 결합 없음 → 빈 마커 (charge/lone pair 도구)
                # - 원소 있어도 결합 없음 → analyzer가 추가한 lewis 잡음 원자일 가능성
                if degrees.get(coord_key, 0) == 0:
                    # 단, 단일 원자 분자는 유효 (H⁺, Na⁺, Cl⁻ 등)
                    if not element:
                        continue
                    # charge가 있는 이온은 유효한 단일 원자
                    if not atom_data.get("charge") and not atom_data.get("formal_charge"):
                        continue

                if not element:
                    element = "C"

                atom = Chem.Atom(element)

                # [Fix] 전하 정보 반영
                charge = atom_data.get("charge", "")
                if charge == "+": atom.SetFormalCharge(1)
                elif charge == "-": atom.SetFormalCharge(-1)

                # [M723-4 FIX] F5-1 item4: attach["H"] → explicit H 반영
                # 사용자가 H 모드로 원소 옆에 수소를 붙이면 attach[d]="H"로 저장.
                # 이것을 SMILES에 반영하지 않으면 우측 말단 O에 H가 누락됨.
                # attach에 "H" 개수만큼 explicit H 설정 (Chem.AddHs 대신 명시적 설정).
                attach = atom_data.get("attach", {})
                if isinstance(attach, dict):
                    explicit_h = sum(1 for sym in attach.values() if sym == "H")
                    if explicit_h > 0:
                        atom.SetNumExplicitHs(explicit_h)  # Rule L: SetNumExplicitHs 후 SanitizeMol로 검증

                idx = editmol.AddAtom(atom)
                coord_to_idx[coord_key] = idx

            for (k1, k2), bond_data in self.bonds.items():
                if k1 in coord_to_idx and k2 in coord_to_idx:
                    idx1, idx2 = coord_to_idx[k1], coord_to_idx[k2]
                    bond_type = Chem.BondType.SINGLE
                    if isinstance(bond_data, int):
                        if bond_data == 2:
                            bond_type = Chem.BondType.DOUBLE
                        elif bond_data == 3:
                            bond_type = Chem.BondType.TRIPLE
                    elif isinstance(bond_data, float):
                        # [FIX-RECOG] 방향족 결합 (1.5) 지원
                        if abs(bond_data - 1.5) < 0.01:
                            bond_type = Chem.BondType.AROMATIC
                        elif bond_data >= 2.5:
                            bond_type = Chem.BondType.TRIPLE
                        elif bond_data >= 1.5:
                            bond_type = Chem.BondType.DOUBLE
                    elif isinstance(bond_data, tuple):
                        # Wedge/Dash 입체결합 → 단일결합으로 처리
                        bond_type = Chem.BondType.SINGLE
                    editmol.AddBond(idx1, idx2, bond_type)

            mol = editmol.GetMol()
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                # [FIX-RECOG] Sanitize 실패 시 부분 Sanitize 시도
                # (방향족 Kekulization 실패 등에서도 SMILES 추출 가능)
                logger.warning("SanitizeMol failed, attempting partial sanitize: %s", e)
                try:
                    Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL ^
                                     Chem.SanitizeFlags.SANITIZE_PROPERTIES ^
                                     Chem.SanitizeFlags.SANITIZE_KEKULIZE)
                except Exception as e:
                    logger.warning("Partial SanitizeMol fallback also failed: %s", e)
            smiles = Chem.MolToSmiles(mol)
            return smiles if smiles else "C"
        except Exception as e:
            logger.warning("SMILES 변환 실패: %s", e)
            return "C"

    # ------------------------------------------------------------------
    # [Phase 6-3] Theory 모드 분자 선택/해제 시스템
    # ------------------------------------------------------------------
    def _find_atom_at_theory(self, l_pos):
        """Theory 레이어 좌표 기준으로 l_pos 근처의 원자 키를 탐색.
        theory_data["map"]의 매핑된 좌표를 사용하며, 없으면 원본 좌표 사용.
        [FIX-SELECT] 라운딩 키 + 원본 키 양쪽으로 t_map 조회
        Returns: atom_key tuple 또는 None"""
        t_map = {}
        if self.analysis_results and isinstance(self.analysis_results, dict):
            _td_hit = self.analysis_results.get("theory_data", {})
            t_map = _td_hit.get("map", {}) if isinstance(_td_hit, dict) else {}
            if not isinstance(t_map, dict):
                t_map = {}
        hit_radius = 28 / self.scale_factor

        best_key = None
        best_dist = hit_radius
        for k in self.atoms:
            # [FIX-SELECT] 라운딩 키로 먼저 조회, 실패 시 원본 키, 최종 fallback은 원본 좌표
            _rk = (round(k[0], 2), round(k[1], 2))
            pt = t_map.get(_rk) or t_map.get(k) or QPointF(*k)
            px, py = pt.x(), pt.y()
            dist = math.hypot(px - l_pos.x(), py - l_pos.y())
            if dist < best_dist:
                best_dist = dist
                best_key = k
        return best_key

    def _select_molecule_at(self, atom_key):
        """atom_key가 속한 전체 분자를 BFS로 탐색하여 선택.
        bonds 딕셔너리의 인접 관계를 사용."""
        from collections import deque

        # 결합 기반 인접 리스트 구축
        adj = {}
        for (a, b) in self.bonds:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)

        # BFS로 연결된 모든 원자 탐색
        visited = set()
        queue = deque([atom_key])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            # Rule N: isinstance guard for adj
            if not isinstance(adj, dict): adj = {}
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        # 결합이 없는 고립 원자도 포함
        if not visited:
            visited.add(atom_key)

        self.selected_molecule_keys = visited
        self._compute_molecule_bbox()
        self._fetch_molecule_name()
        self.molecule_selected.emit(True)
        self.update()

    def _deselect_molecule(self):
        """분자 선택 해제 — 바닥 클릭 시 호출"""
        self.selected_molecule_keys = set()
        self.selected_molecule_name = ""
        self.selected_molecule_bbox = None
        self._name_fetch_pending = False
        self.molecule_selected.emit(False)
        self.update()

    def _compute_molecule_bbox(self):
        """선택된 분자의 바운딩 박스(QRectF) 계산.
        Theory 레이어에서는 theory_data["map"]의 좌표 사용."""
        if not self.selected_molecule_keys:
            self.selected_molecule_bbox = None
            return

        t_map = {}
        if self.analysis_results and isinstance(self.analysis_results, dict):
            _td_sm = self.analysis_results.get("theory_data", {})
            t_map = _td_sm.get("map", {}) if isinstance(_td_sm, dict) else {}
            if not isinstance(t_map, dict):
                t_map = {}

        xs, ys = [], []
        for key in self.selected_molecule_keys:
            if key in t_map:
                pos = t_map[key]
                xs.append(pos.x())
                ys.append(pos.y())
            else:
                xs.append(float(key[0]))
                ys.append(float(key[1]))

        if not xs:
            self.selected_molecule_bbox = None
            return

        PADDING = 25  # 테두리와 원자 사이 여백(px)
        self.selected_molecule_bbox = QRectF(
            min(xs) - PADDING, min(ys) - PADDING,
            max(xs) - min(xs) + 2 * PADDING,
            max(ys) - min(ys) + 2 * PADDING,
        )

    def _fetch_molecule_name(self):
        """선택된 분자의 IUPAC명/관용명을 PubChem에서 비동기 조회.

        [P0-5 FIX] QThread 워커를 사용하여 UI 블로킹 방지.
        네트워크 실패/타임아웃 시 SMILES를 폴백으로 즉시 표시.
        """
        self.selected_molecule_name = ""
        if not self.selected_molecule_keys:
            logger.warning("분자명 조회 실패: 선택된 분자 키가 없음")
            return

        smiles = self._get_molecule_smiles()
        if not smiles or smiles == "C":
            logger.warning("분자명 조회 건너뜀: SMILES가 비어있거나 단일 탄소 (smiles=%r)", smiles)
            return

        # 즉시 SMILES를 임시 표시 (네트워크 응답 대기 중 사용자에게 피드백)
        self.selected_molecule_name = smiles
        self._name_fetch_pending = True
        self.update()

        # 이전 워커가 실행 중이면 시그널 연결 해제 후 참조 해제
        if self._iupac_worker is not None and self._iupac_worker.isRunning():
            try:
                self._iupac_worker.finished.disconnect(self._on_iupac_name_resolved)
            except (TypeError, RuntimeError) as e:
                logger.warning("[Canvas] iupac_worker signal disconnect failed: %s", e)
            self._iupac_worker = None

        # 비동기 워커 시작
        self._iupac_worker = _IUPACNameWorker(smiles, parent=self)
        self._iupac_worker.finished.connect(self._on_iupac_name_resolved)
        self._iupac_worker.start()

    def _on_iupac_name_resolved(self, iupac_name: str) -> None:
        """[P0-5 FIX] 비동기 PubChem IUPAC 조회 완료 콜백.

        UI 스레드에서 실행됨 (Qt signal-slot 메커니즘).
        """
        self._name_fetch_pending = False
        if iupac_name:
            self.selected_molecule_name = iupac_name
        # iupac_name이 빈 문자열이면 기존 SMILES 폴백 유지
        self.update()

    def _get_molecule_smiles(self):
        """선택된 분자 원자/결합만으로 SMILES 생성.
        [Fix v3] 형식전하(+/-) 반영 → 3D 팝업에서 올바른 SMILES 생성
        """
        try:
            from rdkit import Chem

            mol_keys = self.selected_molecule_keys
            if not mol_keys:
                return ""

            editmol = Chem.RWMol(Chem.Mol())
            coord_to_idx = {}
            for coord_key in mol_keys:
                atom_data = self.atoms.get(coord_key, {})
                if not isinstance(atom_data, dict):
                    atom_data = {}
                element = atom_data.get("main", "C")
                if not element:
                    element = "C"
                atom = Chem.Atom(element)
                # [Fix v3] 형식전하 반영 — get_smiles()와 동일한 로직
                charge = atom_data.get("charge", "")
                if charge == "+":
                    atom.SetFormalCharge(1)
                elif charge == "-":
                    atom.SetFormalCharge(-1)
                idx = editmol.AddAtom(atom)
                coord_to_idx[coord_key] = idx

            for (k1, k2), bond_data in self.bonds.items():
                if k1 in coord_to_idx and k2 in coord_to_idx:
                    idx1, idx2 = coord_to_idx[k1], coord_to_idx[k2]
                    bond_type = Chem.BondType.SINGLE
                    if isinstance(bond_data, int):
                        if bond_data == 2:
                            bond_type = Chem.BondType.DOUBLE
                        elif bond_data == 3:
                            bond_type = Chem.BondType.TRIPLE
                    editmol.AddBond(idx1, idx2, bond_type)

            mol = editmol.GetMol()
            Chem.SanitizeMol(mol)
            smiles = Chem.MolToSmiles(mol)
            return smiles if smiles else ""
        except Exception as e:
            logger.warning("_get_molecule_smiles failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # paintEvent — 5-레이어 렌더링
    # [M1 수정] 조준선은 최상위 Z-INDEX에서 1회만 호출
    # [M2 수정] 모든 디버그 print() 제거
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.white)

        is_animating = hasattr(self, "anim") and self.anim.state() == QPropertyAnimation.State.Running
        vr = QRectF(self.to_logical(QPointF(0, 0)), self.to_logical(QPointF(self.width(), self.height())))

        # ===================== LAYER 1: 그리드 점 (Drawing 모드) =====================
        if self.view_state == "Drawing" or is_animating:
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(225, 225, 225))
            vr = QRectF(self.to_logical(QPointF(0, 0)), self.to_logical(QPointF(self.width(), self.height())))
            # [UC-R02] grid_size 동적 참조 (하드코딩 40 제거)
            gs = self.grid_size
            rh = gs * 0.866
            for r in range(int(vr.top() / rh) - 1, int(vr.bottom() / rh) + 2):
                off = gs / 2 if r % 2 != 0 else 0
                for c in range(int(vr.left() / gs) - 1, int(vr.right() / gs) + 2):
                    p.drawEllipse(QPointF(c * gs + off, r * rh), 1.5, 1.5)
            p.restore()

        # ===================== LAYER 2: 애니메이션 배경 (이전 뷰) =====================
        if self.view_state != "Drawing" and is_animating:
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)
            max_r = math.hypot(self.width(), self.height()) * 0.8
            progress = min(self._reveal_radius / max_r, 1.0) if max_r > 0 else 1.0
            p.setOpacity(1.0 - progress * 0.3)

            # F07/F25: Theory is a clean structure layer. Electron-density/ESP
            # visuals belong to ElectronDist or dedicated popups, not Theory.

            # [CHEM-PI-2D] Pi 오비탈 로브 (배경 레이어) — UF-2: 2D 레이어 전체 제거
            # [UF-2 2026-04-21] 유저 요청으로 비활성화. 3D popup π탭에서만 표시.
            # if hasattr(self, "analysis_results") and self.show_clouds:
            #     CloudRenderer.draw_pi_orbital_lobes_2d(p, self.analysis_results, use_theory_coords=True)

            for k, v in self.bonds.items():
                self.draw_bond(p, QPointF(*k[0]), QPointF(*k[1]), v, False, force_single=False) # force_single Disabled
            for k, v in self.atoms.items():
                self.draw_atom_group(p, QPointF(*k), v, False)
            if hasattr(self, "analysis_results"):
                CloudRenderer.draw_stereo_labels(p, self.analysis_results)
            p.restore()

        # ===================== LAYER 3: 원형 확장 (Lewis/Theory) =====================
        if self.view_state != "Drawing":
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)

            # 원형 클리핑
            path = QPainterPath()
            l_reveal_center = self.to_logical(self.reveal_center)
            l_radius = self._reveal_radius / self.scale_factor
            path.addEllipse(l_reveal_center, l_radius, l_radius)
            p.setClipPath(path)
            p.fillRect(vr, Qt.GlobalColor.white)

            _clouds_drawn = False
            if self.view_state in ("Theory", "ElectronDist"):
                _clouds_drawn = self._draw_2d_electron_clouds(p, use_theory_coords=True)

            # W-2D-ELECTRON-CLOUD: show_clouds controls the shared 2D ESP
            # cloud layer for Theory and ElectronDist. Lewis and Drawing stay
            # structural-only.

            # [CHEM-PI-2D] Pi 오비탈 로브 — 2D 레이어에서 제거 (3D popup에서만 표시)
            # [UF-2 2026-04-21] 유저 요청: Lewis/Theory 레이어 p-orbital 로브 제거.
            # 콘쥬게이션 표현(ESP cloud)은 유지. 개별 p-orbital 로브는 3D popup π-orbital 탭 전용.
            # if self.analysis_results and self.show_clouds:
            #     CloudRenderer.draw_pi_orbital_lobes_2d(p, self.analysis_results, use_theory_coords=True)

            # 구조 렌더링
            # [M722-3 F5-3/F5-7 방어 가드] LewisRenderer.render()는 Lewis 모드에서만 호출.
            # Theory 모드에서 LewisRenderer가 호출되면 _render_vsepr_extensions(LP dots)도 실행됨.
            # → Theory 모드에서 LP 비공유전자쌍이 나타나는 원인 차단.
            # M663에서 TheoryRenderer STAGE 3-B LP 제거 완료, 여기서는 Lewis 모드 한정 보장.
            if self.view_state == "Lewis" and self.analysis_results:
                LewisRenderer.render(p, self.atoms, self.bonds, self.analysis_results, self.selected_atoms, self.selected_bonds)
                # [M645_W26] Lewis 레이어에 입체구조 배너 표시
                # stereo_data 있으면 "(R)/(S) + wedge/dash 포함" 표시 — Lewis≠Stereo 시각 구분
                _stereo_check = (
                    self.analysis_results.get("stereo", {})
                    if isinstance(self.analysis_results, dict) else {}
                )
                if _stereo_check:
                    p.setClipping(False)
                    p.save()
                    _slbl_font = QFont(_get_canvas_font(), 9)  # [MAGIC:9pt] 배너 서브 크기
                    _slbl_font.setBold(True)
                    p.setFont(_slbl_font)
                    _stereo_n = len(_stereo_check)
                    # 녹색 배너: 입체중심 개수 표시 (IUPAC CIP nomenclature 1956)
                    p.setPen(QColor(0, 150, 80, 210))  # [MAGIC:210 alpha] 분자 미가림
                    _slbl_fm = QFontMetrics(_slbl_font)
                    _slbl_text = f"[입체구조 — 키랄 중심 {_stereo_n}개 (wedge/dash)]"
                    p.drawText(12, _slbl_fm.ascent() + 8, _slbl_text)  # [MAGIC:12,8px] 좌상단 여백
                    p.restore()
            elif self.view_state == "ElectronDist":
                # [M645_W23] 전자분포 레이어:
                #   STAGE 1 — 회색 점선 분자 골격 (사용자: "회색 점선으로 분자 형태 보여주던가")
                #   STAGE 2 — 원자 charge 색상 원
                #   STAGE 3 — 부분전하 숫자 (ORCA Mulliken / Gasteiger fallback)
                # Rule M: analysis_results 없어도 빈 dict 전달 (silent return 금지)
                _electron_analysis = dict(self.analysis_results) if isinstance(self.analysis_results, dict) else {}
                # [M645_W23] Gasteiger fallback을 위해 SMILES 주입
                # _compute_gasteiger_fallback()은 analysis["smiles"]를 참조
                if not isinstance(_electron_analysis.get("smiles"), str) or not _electron_analysis.get("smiles"):
                    _smiles_for_gasteiger = getattr(self, "_last_drawn_smiles", "")
                    if _smiles_for_gasteiger:
                        _electron_analysis["smiles"] = _smiles_for_gasteiger
                _orca_pop = getattr(self, 'orca_population_data', None)
                ElectronDistributionRenderer.render(
                    p, self.atoms, self.bonds,
                    _electron_analysis,
                    orca_population_data=_orca_pop,
                    selected_atoms=self.selected_atoms,
                    selected_bonds=self.selected_bonds,
                )
                # [M645_W23] ElectronDist 모드 구별 배너
                p.setClipping(False)
                p.save()
                _ed_font = QFont(_get_canvas_font(), 10)
                _ed_font.setBold(True)
                p.setFont(_ed_font)
                _orca_ok = isinstance(_orca_pop, dict) and len(_orca_pop) > 0
                _ed_color = QColor(33, 150, 243, 220) if _orca_ok else QColor(255, 152, 0, 220)
                p.setPen(_ed_color)
                _ed_label = "[전자분포 레이어 — Mulliken]" if _orca_ok else "[전자분포 레이어 — Gasteiger]"
                _ed_fm = QFontMetrics(_ed_font)
                p.drawText(12, _ed_fm.ascent() + 52, _ed_label)  # [MAGIC:52px] Theory 배너 아래 배치
                p.restore()
            elif self.view_state == "Theory":
                # [LITE-EXE-001 FIX] Theory 모드 byte-identical mislabel 방지 (M645_W10, FP-08 재발)
                # FP-08 P-SCOPE: "이론적 구조" 버튼 존재 → Theory 기능 작동 오인
                # 실제로 theory_data 없으면 TheoryRenderer.render() silent return → Lewis와 pixel-identical
                # 해결: Theory 모드에서 항상 구별되는 상단 배너 라벨 표시
                # Rule M: silent failure 금지 — 사용자에게 현재 레이어 상태 항상 피드백
                if self.analysis_results:
                    _t_data_check = (
                        self.analysis_results.get("theory_data")
                        if isinstance(self.analysis_results, dict)
                        else None
                    )
                    TheoryRenderer.render(p, self.atoms, self.bonds, self.analysis_results, self.selected_atoms, self.selected_bonds)
                    if not _t_data_check:
                        logger.warning(
                            "[LITE-EXE-001] Theory 모드 theory_data 없음 (analysis 불완전) "
                            "— byte-identical 방지 라벨 표시 (M645_W10)"
                        )
                else:
                    logger.warning(
                        "[LITE-EXE-001] Theory 모드 analysis_results=None "
                        "— byte-identical 방지 라벨 표시 (M645_W10)"
                    )
                # [LITE-EXE-001] Theory 모드 구별 배너: theory_data 유무와 무관하게 항상 표시
                # Lewis 레이어와 시각적으로 명확히 구분되도록 상단 좌측에 모드 표시
                p.setClipping(False)
                p.save()
                _lbl_font = QFont(_get_canvas_font(), 10)  # [MAGIC:10pt] 배너 가독성
                _lbl_font.setBold(True)
                p.setFont(_lbl_font)
                _t_data_ok = (
                    bool(self.analysis_results and isinstance(self.analysis_results, dict)
                         and self.analysis_results.get("theory_data"))
                )
                # theory_data 있으면 정상(파란색), 없으면 주황색 경고
                _banner_color = QColor(33, 150, 243, 220) if _t_data_ok else QColor(255, 152, 0, 220)
                # [MAGIC:220 alpha] 배너 반투명 — 분자 구조를 가리지 않도록
                p.setPen(_banner_color)
                _banner_label = (
                    "[이론적 구조 레이어]"
                    if _t_data_ok
                    else "[이론적 구조 — 분석 대기 중]"
                )
                _lbl_fm = QFontMetrics(_lbl_font)
                _lbl_margin = 12  # [MAGIC:12px] 좌측 여백
                _lbl_ty = _lbl_fm.ascent() + 8  # [MAGIC:8px] 상단 여백
                p.drawText(_lbl_margin, _lbl_ty, _banner_label)
                p.restore()
                if _clouds_drawn and self._theory_cloud_uses_fallback_source():
                    self._draw_theory_cloud_fallback_banner(p)

            # 선택 범위 사각형
            if self.selection_rect:
                p.setPen(QPen(Qt.GlobalColor.blue, 1 / self.scale_factor, Qt.PenStyle.DashLine))
                p.setBrush(QColor(0, 0, 255, 15))
                p.drawRect(self.selection_rect)

            # 원형 테두리 효과
            if is_animating and l_radius > 10:
                p.setClipping(False)
                max_r_anim = math.hypot(self.width(), self.height()) * 0.8
                progress = min(self._reveal_radius / max_r_anim, 1.0) if max_r_anim > 0 else 1.0
                alpha = int(255 * (1.0 - progress * 0.7))
                shadow_pen = QPen(QColor(33, 150, 243, alpha // 3), 6.0 / self.scale_factor)
                p.setPen(shadow_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(l_reveal_center, l_radius + 2 / self.scale_factor, l_radius + 2 / self.scale_factor)
                main_pen = QPen(QColor(33, 150, 243, alpha), 2.5 / self.scale_factor)
                p.setPen(main_pen)
                p.drawEllipse(l_reveal_center, l_radius, l_radius)

            # ===== [Phase 6-3] Theory 모드: 선택 분자 점선 테두리 + IUPAC명 =====
            if self.view_state in ["Theory", "Lewis", "Drawing"] and self.selected_molecule_bbox:
                p.setClipping(False)
                p.save()
                # 점선 테두리 (Material Blue, 둥근 모서리)
                dash_pen = QPen(QColor(33, 150, 243), 2.0 / self.scale_factor, Qt.PenStyle.DashLine)
                dash_pen.setDashPattern([8, 4])
                p.setPen(dash_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(self.selected_molecule_bbox, 8, 8)

                # IUPAC명/관용명 텍스트 (바운딩 박스 하단 중앙)
                if self.selected_molecule_name:
                    font = QFont(_get_canvas_font(), 10)  # [M609]
                    p.setFont(font)
                    p.setPen(Qt.GlobalColor.black)
                    fm = QFontMetrics(font)
                    text_width = fm.horizontalAdvance(self.selected_molecule_name)
                    bbox = self.selected_molecule_bbox
                    text_x = bbox.center().x() - text_width / 2
                    text_y = bbox.bottom() + 5 + fm.ascent()
                    p.drawText(int(round(text_x, 0)), int(round(text_y, 0)), self.selected_molecule_name)
                p.restore()

            # [M1 수정] 조준선 호출 제거 — 최상위 Z-INDEX에서 1회만 호출
            p.restore()

        # ===================== LAYER 4: Drawing 모드 분자 =====================
        if self.view_state == "Drawing":
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)

            # 1. 전자구름
            # Drawing mode uses the same ESP palette as Theory, but in drawing
            # coordinates.  The global show_clouds toggle says "전자구름 끄기"
            # by default, so hiding this layer while the toggle is ON breaks the
            # visible UI contract.
            # ESP is intentionally not rendered in Drawing mode.
            # Rule I / learner-flow guard: electrostatic potential belongs to
            # Theory/ElectronDist evidence. Rendering it here used Drawing-space
            # coordinates and made the same molecule show conflicting cloud
            # colors across 2D layers.

            # [P0-6 FIX] Pi 오비탈 로브는 Drawing 모드에서 제거
            # sp3 혼성 원자에서는 비편재화 전자가 없어 p-오비탈 표시가 부적절.
            # Theory/Lewis 레이어에서만 표시. (원래 코드: draw_pi_orbital_lobes_2d 호출 제거)

            # 2. 결합선
            for k, v in self.bonds.items():
                # 방향족 고리 내부 결합은 단일 결합(single bond)으로 강제 렌더링 -> Disabled
                self.draw_bond(p, QPointF(*k[0]), QPointF(*k[1]), v, k in self.selected_bonds, force_single=False)

            # 3. 원소 기호
            for k, v in self.atoms.items():
                self.draw_atom_group(p, QPointF(*k), v, k in self.selected_atoms)

            # 4. 입체 라벨
            if hasattr(self, "analysis_results"):
                CloudRenderer.draw_stereo_labels(p, self.analysis_results)

            # [M1 수정] 조준선 호출 제거 — 최상위 Z-INDEX에서 1회만 호출
            p.restore()

        # ===================== LAYER 5: 최상단 오버레이 (Drawing 전용) =====================
        if self.view_state == "Drawing":
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)

            l_pos = self.to_logical(self.last_mouse_pos)
            closest = self.get_closest_pt(l_pos)

            # 고스트 드로잉
            if closest or self.is_pasting:
                ghost_color = QColor(0, 120, 255)
                p.setOpacity(0.5)
                p.setPen(QPen(ghost_color, 1.5 / self.scale_factor))
                p.setBrush(Qt.BrushStyle.NoBrush)

                if self.is_pasting and self.clipboard:
                    anchor = self.get_closest_pt(l_pos) or l_pos
                    for rel, data in self.clipboard["a"]:
                        self.draw_atom_group(p, anchor + QPointF(*rel), data, False)
                    for rel_b, bt in self.clipboard["b"]:
                        g_mode = bt[2] if isinstance(bt, tuple) else bt
                        self.draw_bond(p, anchor + QPointF(*rel_b[0]), anchor + QPointF(*rel_b[1]), g_mode, False, force_single=False)

                elif closest and self.mode in ["LonePair", "Radical", "Positive", "Negative", "H"]:
                    k = get_coord_key(closest)
                    dx, dy = l_pos.x() - closest.x(), l_pos.y() - closest.y()
                    ang_deg = round((math.degrees(math.atan2(dy, dx)) % 360) / 60) * 60
                    ang = math.radians(ang_deg)
                    gp = QPointF(closest.x() + math.cos(ang) * 22, closest.y() + math.sin(ang) * 22)

                    if self.mode == "H":
                        p.setFont(QFont(_get_canvas_font(), 12, QFont.Weight.Bold))  # [M609]
                        target_pos = (
                            closest
                            if (isinstance(self.atoms.get(k), dict) and self.atoms.get(k, {}).get("main", "") == "" and math.hypot(dx, dy) < 12)
                            else gp
                        )
                        p.drawText(QRectF(target_pos.x() - 10, target_pos.y() - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, "H")
                    elif self.mode == "LonePair":
                        p.save()
                        p.translate(gp)
                        p.rotate(ang_deg + 90)
                        p.setBrush(ghost_color)
                        p.drawEllipse(QPointF(-3.5, 0), 2.0, 2.0)
                        p.drawEllipse(QPointF(3.5, 0), 2.0, 2.0)
                        p.restore()
                    elif self.mode == "Radical":
                        p.setBrush(ghost_color)
                        p.drawEllipse(gp, 2.5, 2.5)
                    else:
                        p.setFont(QFont(_get_canvas_font(), 14, QFont.Weight.Bold))  # [M609]
                        sym = "+" if self.mode == "Positive" else "-"
                        p.drawText(QRectF(gp.x() - 10, gp.y() - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, sym)

                elif closest and self.mode not in ["Wedge", "Dash", "Bond", "Select", "Hand", "Eraser", "Pen", "Arrow", "Text"]:
                    p.setFont(QFont(_get_canvas_font(), 12, QFont.Weight.Bold))  # [M609]
                    fm = QFontMetrics(p.font())
                    tw = fm.horizontalAdvance(self.mode)
                    p.drawText(
                        QRectF(closest.x() - tw / 2, closest.y() - fm.height() / 2, tw, fm.height()),
                        Qt.AlignmentFlag.AlignCenter,
                        self.mode,
                    )

                p.setOpacity(1.0)

            # 결합 드래그 미리보기
            if self.mode in ["Bond", "Wedge", "Dash"] and self.current_start:
                p.setPen(QPen(Qt.GlobalColor.red, 1.5 / self.scale_factor, Qt.PenStyle.DashLine))
                p.drawLine(self.current_start, self.current_end)

            # [UF-4 2026-04-21] 펜 스트로크 → 모든 레이어 공통 오버레이로 이동됨
            # (아래 "펜 스트로크 오버레이" 섹션에서 렌더링)

            # 선택 사각형
            if self.selection_rect:
                p.setPen(QPen(Qt.GlobalColor.blue, 1 / self.scale_factor, Qt.PenStyle.DashLine))
                p.setBrush(QColor(0, 0, 255, 15))
                p.drawRect(self.selection_rect)

            # 지우개 커서
            if self.mode == "Eraser":
                er_pos = self.to_logical(self.last_mouse_pos)
                r_box = 10 / self.scale_factor
                p.save()
                p.setPen(QPen(Qt.GlobalColor.black, 1.2))
                p.setBrush(QColor(255, 255, 255, 220))
                p.drawRect(QRectF(er_pos.x() - r_box, er_pos.y() - r_box, r_box * 2, r_box * 2))
                p.restore()

            p.restore()

        # ===================== [v4 명령3] 반응 화살표 — 모든 뷰 모드에서 렌더링 =====================
        if self.arrows or (self.arrow_drawing and self.arrow_start and self.arrow_ghost_end):
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)

            # 확정된 화살표 (검은색, 실선, 화살촉)
            for (a_start, a_end) in self.arrows:
                self._draw_arrow(p, a_start, a_end,
                                 QPen(Qt.GlobalColor.black, 2.0 / self.scale_factor),
                                 Qt.PenStyle.SolidLine)

            # 드래그 중 고스트 (파란색, 점선, 화살촉)
            if self.arrow_drawing and self.arrow_start and self.arrow_ghost_end:
                self._draw_arrow(p, self.arrow_start, self.arrow_ghost_end,
                                 QPen(QColor(0, 120, 255), 1.5 / self.scale_factor, Qt.PenStyle.DashLine),
                                 Qt.PenStyle.DashLine)
            p.restore()

        # ===================== [UF-4 2026-04-21] 펜 스트로크 오버레이 — 모든 레이어 공통 최상위 렌더링 =====================
        # 이전: Drawing 전용 LAYER 5 블록 안에 있어서 Lewis/Theory 레이어 전환 시 사라짐
        # 수정: 반응 화살표(모든 레이어)와 동일한 패턴으로 항상 렌더링
        if self.strokes or self.temp_stroke:
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)
            for s in self.strokes + [{"pts": self.temp_stroke, "clr": self.pen_color, "w": self.pen_width}]:
                if len(s["pts"]) >= 2:
                    p.setPen(QPen(s["clr"], s["w"] / self.scale_factor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    for i in range(len(s["pts"]) - 1):
                        p.drawLine(s["pts"][i], s["pts"][i + 1])
            p.restore()

        # ===================== [v4 명령4 수정] 텍스트 상자 — 텍스트는 항상 보이고 테두리만 조건부 =====================
        if self.text_boxes:
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)
            self._draw_text_boxes(p)
            p.restore()

        # ===================== 최상위 Z-INDEX: 조준선(⊕) — 1회 렌더링 =====================
        # [M1 수정] paintEvent 끝에서 단 1회만 호출하여 3중 렌더링 버그 해결
        if hasattr(self, "analysis_results") and self.analysis_results:
            p.save()
            p.setClipping(False)
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)
            # [BUG-FIX] draw_crosshairs_v32 비활성화
            # 순수 녹색(#00FF00) 과녁 마커가 Theory 레이어 위에 항상 표시되는 버그
            # 전자 밀도 상위 탄소에 QPen(QColor(0,255,0,255)) 조준선을 그리던 기능
            # 화학 교육용 UI에서 혼란을 주므로 기본 OFF (필요 시 설정에서 토글)
            # CloudRenderer.draw_crosshairs_v32(p, self.analysis_results)
            p.restore()

    # ------------------------------------------------------------------
    # 방향족 고리 감지 (bonds dict 기반)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 결합 그리기
    # ------------------------------------------------------------------
    def draw_bond(self, p, p1, p2, data, sel, force_single=False):
        p.setPen(QPen(Qt.GlobalColor.blue if sel else Qt.GlobalColor.black, 2))
        v, bt_mode = 1, "Bond"
        if isinstance(data, float) and abs(data - 0.5) < 0.01:
            # [COORD-BOND] Dative/coordination bond (order=0.5) → dashed arrow
            bt_mode = "Dative"
            v = 0.5
        elif isinstance(data, float) and abs(data - 1.5) < 0.01:
            # [AROMATIC-FIX] 방향족 결합 → 단일선만 그리기 (고리 원이 방향족 표기 보완)
            bt_mode = "Bond"
            v = 1
        elif isinstance(data, int):
            v = data
        elif isinstance(data, tuple):
            p1, p2, bt_mode = data
        
        # [Aromatic] 방향족 고리 내부면 단일 결합으로 강제
        if force_single and bt_mode == "Bond":
            v = 1

        vec = p2 - p1
        l = math.hypot(vec.x(), vec.y())
        if l == 0:
            logger.warning("결합 그리기 건너뜀: 길이 0 (p1=%s, p2=%s)", p1, p2)
            return

        unit = vec / l
        k1, k2 = get_coord_key(p1), get_coord_key(p2)
        nx, ny = -unit.y(), unit.x()

        # [U5] 고리 내 이중결합 → 짧은 선이 고리 안쪽을 향하도록 보정
        ring_center = get_ring_center_for_bond(k1, k2, self.bonds)
        if ring_center is not None:
            # 고리 결합: 결합 중점 → 고리 중심 방향으로 nx,ny 정렬
            mid = (p1 + p2) / 2
            to_cx = ring_center.x() - mid.x()
            to_cy = ring_center.y() - mid.y()
            dot = nx * to_cx + ny * to_cy
            if dot < 0:
                nx, ny = -nx, -ny
        else:
            # 비고리 결합: 기존 neighbors 평균 기반 방향 결정
            neighbors = []
            for bk in self.bonds:
                if k1 in [bk[0], bk[1]] or k2 in [bk[0], bk[1]]:
                    for pk in [bk[0], bk[1]]:
                        if pk != k1 and pk != k2:
                            neighbors.append(QPointF(*pk))
            if neighbors:
                ax = sum(pt.x() for pt in neighbors) / len(neighbors)
                ay = sum(pt.y() for pt in neighbors) / len(neighbors)
                if (ax - p1.x()) * nx + (ay - p1.y()) * ny < 0:
                    nx, ny = -nx, -ny

        g1, g2 = self.get_bond_gap(k1, unit), self.get_bond_gap(k2, -unit)
        s, e = p1 + unit * g1, p2 - unit * g2

        if bt_mode == "Bond":
            if v == 1:
                p.drawLine(s, e)
            elif v >= 2:
                _ad1_c = self.atoms.get(k1, {})
                elem1 = _ad1_c.get("main", "C") if isinstance(_ad1_c, dict) else "C"
                _ad2_c = self.atoms.get(k2, {})
                elem2 = _ad2_c.get("main", "C") if isinstance(_ad2_c, dict) else "C"
                is_cc_bond = elem1 in ["C", ""] and elem2 in ["C", ""]
                off = 7
                p.drawLine(s, e)
                if is_cc_bond:
                    p.drawLine(
                        QPointF(s.x() + nx * off + unit.x() * 3, s.y() + ny * off + unit.y() * 3),
                        QPointF(e.x() + nx * off - unit.x() * 3, e.y() + ny * off - unit.y() * 3),
                    )
                else:
                    p.drawLine(
                        QPointF(s.x() + nx * off, s.y() + ny * off),
                        QPointF(e.x() + nx * off, e.y() + ny * off),
                    )
                if v == 3:
                    if is_cc_bond:
                        p.drawLine(
                            QPointF(s.x() - nx * off + unit.x() * 3, s.y() - ny * off + unit.y() * 3),
                            QPointF(e.x() - nx * off - unit.x() * 3, e.y() - ny * off - unit.y() * 3),
                        )
                    else:
                        p.drawLine(
                            QPointF(s.x() - nx * off, s.y() - ny * off),
                            QPointF(e.x() - nx * off, e.y() - ny * off),
                        )

        elif bt_mode == "Wedge":
            poly = QPolygonF([s, e + QPointF(nx * 5, ny * 5), e - QPointF(nx * 5, ny * 5)])
            p.setBrush(p.pen().color())
            p.drawPolygon(poly)
            p.setBrush(Qt.BrushStyle.NoBrush)

        elif bt_mode == "Dash":
            for i in range(8):
                f, w = i / 7.0, i * 0.8
                ps = s + (e - s) * f
                p.drawLine(ps + QPointF(nx * w, ny * w), ps - QPointF(nx * w, ny * w))

        elif bt_mode == "Dative":
            # [COORD-BOND] Dative/coordination bond: dashed line + arrowhead
            # Rendered as dashed line from ligand → metal with arrow tip
            p.save()
            dative_color = QColor(80, 80, 160) if not sel else Qt.GlobalColor.blue
            dash_pen = QPen(dative_color, 2)
            dash_pen.setStyle(Qt.PenStyle.DashLine)
            dash_pen.setDashPattern([6, 3])
            p.setPen(dash_pen)
            p.drawLine(s, e)
            # Arrowhead at endpoint (toward the metal)
            arrow_len = 8
            arrow_w = 4
            ax = -unit.x() * arrow_len
            ay = -unit.y() * arrow_len
            arrow_p1 = e + QPointF(ax + ny * arrow_w, ay - nx * arrow_w)
            arrow_p2 = e + QPointF(ax - ny * arrow_w, ay + nx * arrow_w)
            solid_pen = QPen(dative_color, 2)
            p.setPen(solid_pen)
            p.setBrush(dative_color)
            p.drawPolygon(QPolygonF([e, arrow_p1, arrow_p2]))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.restore()

    # ------------------------------------------------------------------
    # 원소 기호 그리기
    # ------------------------------------------------------------------
    def draw_atom_group(self, p, pt, data, sel):
        if not isinstance(data, dict):
            return
        p.setFont(QFont(_get_canvas_font(), 12, QFont.Weight.Bold))  # [M609]
        main = data.get("main", "")
        fm = QFontMetrics(p.font())

        # [Fix v3] 그리기 레이어: 원자 색상 항상 검은색 (전하 여부와 무관)
        # 탄소는 그리기 레이어에서 숨김 유지 (charge가 있어도 C 기호 미표시)
        charge_sym_pre = data.get("charge", "")
        display_main = main  # 빈 탄소는 항상 숨김
        if display_main:
            tw = fm.horizontalAdvance(display_main)
            text_rect = QRectF(pt.x() - tw / 2, pt.y() - fm.height() / 2, tw, fm.height())
            _acolor = Qt.GlobalColor.blue if sel else Qt.GlobalColor.black
            p.setPen(_acolor)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_main)

        for d, sym in data["attach"].items():
            # [FIX] +/- 기호는 attach에서 그리지 않음 — charge 필드에서 위첨자로 통합 렌더링
            if sym in ("+", "-"):
                continue
            ang = math.radians(d * 60) if d != -1 else 0
            dist = 22 if main else 8
            sx = pt.x() + (math.cos(ang) * dist if d != -1 else 0)
            sy = pt.y() + (math.sin(ang) * dist if d != -1 else 0)

            if sym == "..":
                p.save()
                p.translate(sx, sy)
                if d != -1:
                    p.rotate(d * 60 + 90)
                p.setBrush(p.pen().color())
                p.drawEllipse(QPointF(-3.5, 0), 2.0, 2.0)
                p.drawEllipse(QPointF(3.5, 0), 2.0, 2.0)
                p.restore()
            elif sym == "·":
                p.save()
                p.translate(sx, sy)
                p.setBrush(p.pen().color())
                p.drawEllipse(QPointF(0, 0), 2.5, 2.5)
                p.restore()
            else:
                sw = fm.horizontalAdvance(sym)
                p.drawText(
                    QRectF(sx - sw / 2, sy - fm.height() / 2, sw, fm.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    sym,
                )

        # [v6 Fix] charge 필드 + attach 내 +/- → 통합 위첨자 렌더링
        # attach의 +/-와 charge 필드 중 하나라도 있으면 위첨자로 표시
        charge_sym = data.get("charge", "")
        if not charge_sym:
            # charge 필드 없으면 attach에서 +/- 체크
            _attach_c = data.get("attach", {})
            if not isinstance(_attach_c, dict):
                _attach_c = {}
            for _d, _s in _attach_c.items():
                if _s in ("+", "-"):
                    charge_sym = _s
                    break
        if charge_sym:
            p.save()
            # [v6.1] 교과서 위첨자 스타일 — 원소 기호 완전히 오른쪽 바깥에 표시
            charge_font = QFont(_get_canvas_font(), 10, QFont.Weight.Bold)  # [M609]
            p.setFont(charge_font)
            # 원소 기호의 실제 텍스트 경계 바깥으로 확실히 빼기
            label_w = fm.horizontalAdvance(main) if main else 0
            # [v8.4] 원소 기호 우측 끝 + 여유 간격 (탄소 기호 없어도 최소 10px)
            gap = max(label_w / 2, 10) + 6
            # 위첨자 텍스트로 직접 표시 (⁺ / ⁻ 유니코드 위첨자)
            sup_text = "⁺" if charge_sym == "+" else "⁻"  # Rule Q: direct charge superscripts
            sup_color = Qt.GlobalColor.red if charge_sym == "+" else Qt.GlobalColor.blue
            p.setPen(sup_color)
            p.drawText(QPointF(pt.x() + gap, pt.y() - fm.height() * 0.35), sup_text)
            p.restore()

    # ------------------------------------------------------------------
    # 지우개
    # ------------------------------------------------------------------
    def erase(self, l_pos):
        r = 15 / self.scale_factor
        for k in list(self.atoms.keys()):
            if (l_pos.x() - r < k[0] < l_pos.x() + r) and (l_pos.y() - r < k[1] < l_pos.y() + r):
                self.atoms.pop(k)
        for k in list(self.bonds.keys()):
            mid_x = (k[0][0] + k[1][0]) / 2
            mid_y = (k[0][1] + k[1][1]) / 2
            if (l_pos.x() - r < mid_x < l_pos.x() + r) and (l_pos.y() - r < mid_y < l_pos.y() + r):
                self.bonds.pop(k)
        self.strokes = [
            s
            for s in self.strokes
            if not any(math.hypot(pt.x() - l_pos.x(), pt.y() - l_pos.y()) < 10 / self.scale_factor for pt in s["pts"])
        ]
        # 화살표 지우기
        self.arrows = [
            (a_s, a_e) for (a_s, a_e) in self.arrows
            if math.hypot((a_s.x() + a_e.x()) / 2 - l_pos.x(),
                          (a_s.y() + a_e.y()) / 2 - l_pos.y()) > r
        ]
        # 텍스트 상자 지우기
        self.text_boxes = [
            tb for tb in self.text_boxes
            if math.hypot(tb["pos"].x() - l_pos.x(), tb["pos"].y() - l_pos.y()) > r
        ]

    # ------------------------------------------------------------------
    # [v4 명령3] 반응 화살표 — 화살표 렌더링 헬퍼
    # ------------------------------------------------------------------
    def _draw_arrow(self, p, start, end, pen, style):
        """화살표 1개를 그린다: 직선 + 삼각형 화살촉 (벡터 보정)"""
        try:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # 직선 그리기
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(start, end)

            # 화살촉 (삼각형) 계산
            vec = end - start
            length = math.hypot(vec.x(), vec.y())
            if length > 5.0:  # 너무 짧으면 그리지 않음
                ux, uy = vec.x() / length, vec.y() / length
                head_len = max(15.0, 14.0 / self.scale_factor)  # [Rule O] 최소 15px 보장 (M844)
                head_w = 6.0 / self.scale_factor
                
                tip = end
                base_pt = QPointF(end.x() - ux * head_len, end.y() - uy * head_len)
                left = QPointF(base_pt.x() + uy * head_w, base_pt.y() - ux * head_w)
                right = QPointF(base_pt.x() - uy * head_w, base_pt.y() + ux * head_w)
                
                # 화살촉은 테두리 없이 채우기만 수행 (검은색/파란색)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(pen.color())
                p.drawPolygon(QPolygonF([tip, left, right]))
            p.restore()
        except Exception as e:
            logger.warning("_draw_arrow Error: %s", e)
            try:
                p.restore()
            except Exception as e:
                logger.warning("Arrow painter restore failed: %s", e)

    # ------------------------------------------------------------------
    # [v4 명령4] 텍스트 상자 — 헬퍼 메서드
    # ------------------------------------------------------------------
    def _handle_text_click(self, l_pos):
        """Text 모드에서 클릭: 기존 텍스트 상자 선택 또는 새로 생성"""
        hit_radius = 30 / self.scale_factor
        # 기존 텍스트 상자 중 가장 가까운 것 탐색
        for i, tb in enumerate(self.text_boxes):
            dist = math.hypot(tb["pos"].x() - l_pos.x(), tb["pos"].y() - l_pos.y())
            if dist < hit_radius:
                self.text_editing_idx = i
                self.update()
                return
        # 새 텍스트 상자 생성
        self.save_state()
        self.text_boxes.append({
            "pos": QPointF(l_pos),
            "text": "",
            "font_size": self.text_font_size,
        })
        self.text_editing_idx = len(self.text_boxes) - 1
        self.update()

    def _render_subscript(self, text):
        """언더바+숫자 → 아래첨자, ^+숫자/+-  → 위첨자 변환
        CH_3 → CH₃  /  CO^2- → CO²⁻  /  H^+ → H⁺  (M843 #3 fix)
        """
        import re
        # [M843 #3] ^ 위첨자: ^n → 유니코드 위첨자. 숫자/+/- 지원
        SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
        SUPERSCRIPT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
        result = re.sub(r'\^([0-9+\-]+)', lambda m: m.group(1).translate(SUPERSCRIPT), text)
        result = re.sub(r'_(\d+)', lambda m: m.group(1).translate(SUBSCRIPT), result)
        return result

    def _draw_text_boxes(self, p):
        """모든 텍스트 상자를 렌더링.
        - 빨간 점선 테두리 (Text 도구 선택 시에만)
        - 텍스트 (아래첨자 변환 적용)
        - 편집 중인 상자는 커서(|) 표시"""
        for i, tb in enumerate(self.text_boxes):
            pos = tb["pos"]
            text = self._render_subscript(tb["text"]) if tb["text"] else ""
            # Rule N: isinstance guard for tb
            if not isinstance(tb, dict): tb = {}
            font_size = tb.get("font_size", 12)
            # [P0-1 FIX] QFont::setPointSize <= 0 방지 (크래시 유발)
            font_size = max(int(font_size) if isinstance(font_size, (int, float)) else 12, 1)
            is_editing = (i == self.text_editing_idx) and (self.mode == "Text")

            font = QFont(_get_canvas_font(), font_size)  # [M609]
            p.setFont(font)
            fm = QFontMetrics(font)

            # 텍스트 크기 계산 (최소 폭 보장)
            display = text + "|" if is_editing else text
            tw = max(fm.horizontalAdvance(display if display else "T"), 30)
            th = fm.height() + 6
            box_rect = QRectF(pos.x() - 4, pos.y() - th / 2, tw + 8, th)

            # Text 모드일 때만 테두리 및 배경 표시
            if self.mode == "Text":
                p.save()
                border_pen = QPen(QColor(220, 50, 50), 1.0 / self.scale_factor, Qt.PenStyle.DashLine)
                p.setPen(border_pen)
                p.setBrush(QColor(255, 255, 255, 200))
                p.drawRect(box_rect)
                p.restore()

            # 텍스트 내용 (모드 상관없이 항상 표시)
            p.setPen(Qt.GlobalColor.black)
            p.drawText(
                QPointF(pos.x(), pos.y() + fm.ascent() / 2 - 1),
                display,
            )
