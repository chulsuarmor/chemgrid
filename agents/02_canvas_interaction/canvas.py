# canvas.py — MoleculeCanvas 분리 모듈
# Agent 02 (캔버스/그리기) 전담
# 최종 업데이트: 2026-03-01
#
# 변경 이력:
#   - MoleculeCanvas를 draw.py에서 분리
#   - [M1] 조준선 3중 렌더링 버그 수정 → 최상위 Z-INDEX 1회만 호출
#   - [M2] paintEvent 내부 디버그 print() 전부 제거
#   - [C3] self.canvas.repaint() → self.update() 수정
#   - [C5] 하드코딩 절대 경로 → __file__ 기반 상대 경로
#   - [U5] draw_bond() 고리 이중결합 짧은 선 안쪽 방향 보정 (BFS 고리 감지)
#   - [Phase 6-3] Theory 모드 분자 선택 UX: 점선 테두리 + IUPAC명 + 바닥 클릭 해제
#   - [Phase 6-3 v4 명령1] +/- 기호 → atoms["charge"] 별도 필드 분리
#   - [Phase 6-3 v4 명령3] 반응 화살표 도구 (Arrow) — 4방향 스냅, 고스트, 모든 레이어 표시
#   - [Phase 6-3 v4 명령4] 텍스트 상자 도구 (Text) — 아래첨자 변환, T모드 전용 표시
#   - [Phase 6-3 v4 명령5] 비공유전자쌍 user_lp 플래그 추가
# =========================================================================

import math
import copy
import os
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QFontMetrics,
    QPolygonF, QPainterPath,
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QSizeF,
    pyqtProperty, pyqtSignal, QPropertyAnimation, QEasingCurve,
)

from chem_data import ELEMENT_DATA, VISUAL_SETTINGS
from analyzer import ChemicalAnalyzer
from renderer import CloudRenderer
from layer_logic import LewisRenderer, TheoryRenderer
from coord_utils import get_ring_center_for_bond

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
# MoleculeCanvas — 핵심 캔버스 엔진
# ==========================================
class MoleculeCanvas(QWidget):
    # [Phase 6-3] Theory 모드 분자 선택/해제 시그널
    molecule_selected = pyqtSignal(bool)  # True=선택됨, False=해제됨

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.grid_size, self.snap_distance = 40, 25
        self.atom_radius, self.lone_pair_gap, self.radical_gap = 12, 10, 12
        self.scale_factor, self.pan_offset = 1.0, QPointF(0, 0)
        self.atoms, self.bonds, self.strokes = {}, {}, []
        self.undo_stack, self.redo_stack = [], []
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

        # ========== [Phase 6-3] Theory 모드 분자 선택 상태 ==========
        self.selected_molecule_keys = set()    # 선택된 분자의 모든 원자 키 집합
        self.selected_molecule_name = ""       # IUPAC명 또는 관용명
        self.selected_molecule_bbox = None     # QRectF 바운딩 박스
        self._name_fetch_pending = False       # PubChem 조회 중복 방지 플래그

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
            self.arrows = copy.deepcopy(st.get("ar", []))
            self.text_boxes = copy.deepcopy(st.get("tb", []))
            self.update()

    def redo(self):
        if self.redo_stack:
            st = self.redo_stack.pop()
            self.undo_stack.append(copy.deepcopy(st))
            self.atoms = copy.deepcopy(st["a"])
            self.bonds = copy.deepcopy(st["b"])
            self.strokes = copy.deepcopy(st["s"])
            self.arrows = copy.deepcopy(st.get("ar", []))
            self.text_boxes = copy.deepcopy(st.get("tb", []))
            self.update()

    # ------------------------------------------------------------------
    # 그리드 스냅
    # ------------------------------------------------------------------
    def get_closest_pt(self, l_pos):
        rh = self.grid_size * 0.866
        r = round(l_pos.y() / rh)
        off = self.grid_size / 2 if r % 2 != 0 else 0
        c = round((l_pos.x() - off) / self.grid_size)
        pt = QPointF(c * self.grid_size + off, r * rh)
        if math.hypot(pt.x() - l_pos.x(), pt.y() - l_pos.y()) < self.snap_distance:
            return pt
        return None

    def get_bond_gap(self, pt_key, vec):
        """결합선이 원소 기호나 치환기로부터 얼마나 떨어져야 하는지 계산"""
        if pt_key not in self.atoms:
            return 0
        at = self.atoms[pt_key]
        if at["main"]:
            font = QFont("Arial", 12, QFont.Weight.Bold)
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

            # 고리 감지 (DFS)
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
            self.drag_origin = l_pos
            self.selection_rect = QRectF(l_pos, QSizeF(0, 0))
            self.selected_atoms.clear()
            self.selected_bonds.clear()
            self.update()
            return

        if event.button() in [Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton] or self.mode == "Hand":
            self.drag_origin = event.position()
            return

        # [Phase 6-3] Theory 모드: 좌클릭으로 분자 선택/해제
        if self.view_state == "Theory" and event.button() == Qt.MouseButton.LeftButton:
            clicked_atom = self._find_atom_at_theory(l_pos)
            if clicked_atom is not None:
                self._select_molecule_at(clicked_atom)
            else:
                # 빈 영역(바닥) 클릭 → 선택 해제
                if self.selected_molecule_keys:
                    self._deselect_molecule()
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
                t_map = (
                    self.analysis_results.get("theory_data", {}).get("map", {})
                    if self.analysis_results
                    else {}
                )
                self.selected_atoms = set()
                for k in self.atoms:
                    pt = t_map.get(k, QPointF(*k))
                    if self.selection_rect.contains(pt):
                        self.selected_atoms.add(k)
                self.selected_bonds = set()
                for k in self.bonds:
                    p1 = t_map.get(k[0], QPointF(*k[0]))
                    p2 = t_map.get(k[1], QPointF(*k[1]))
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

        self.analysis_results = self.analyzer.analyze(self.atoms, self.bonds)
        self.on_molecule_updated()
        self.update()

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
        """Hook 2: 분자 수정 감지 → Phase B-D 업데이트 트리거"""
        if self.phase_manager:
            try:
                self.phase_manager.on_molecule_updated(self.atoms, self.bonds, self.analysis_results)
            except Exception:
                pass

    def on_theory_layer_interaction(self):
        """Hook 3: Theory layer 상호작용 → 3D 팝업 트리거"""
        if self.phase_manager and self.analysis_results:
            try:
                theory_data = self.analysis_results.get("theory_data", {})
                self.phase_manager.on_theory_layer_interaction(self.atoms, self.bonds, theory_data)
            except Exception:
                pass

    def on_orca_calculation_complete(self, orca_result):
        """Hook 4: ORCA 계산 완료 → ESP 시각화 + DFT 전자 밀도 분석"""
        self._analyze_dft_electron_density(orca_result)
        if self.phase_manager:
            try:
                self.phase_manager.on_orca_calculation_complete(orca_result)
            except Exception:
                pass

    def _analyze_dft_electron_density(self, orca_result):
        """ORCA DFT 결과에서 전자 밀도 분석 (포터블 경로 사용)"""
        try:
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
                return

            atom_positions = {}
            atom_symbols = {}
            for coord_key, atom_data in self.atoms.items():
                atom_idx = len(atom_positions)
                atom_symbol = atom_data.get("main", "C")
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

            # [C3 수정] self.canvas.repaint() → self.update()
            self.update()

        except ImportError:
            pass
        except Exception:
            pass

    def cleanup(self):
        """Hook 5: 종료 시 QThread·팝업 정리"""
        if self.phase_manager:
            try:
                self.phase_manager.cleanup()
            except Exception:
                pass

    def get_smiles(self):
        """현재 캔버스의 분자를 SMILES로 변환"""
        try:
            if not self.atoms:
                return "C"
            from rdkit import Chem

            editmol = Chem.RWMol(Chem.Mol())
            coord_to_idx = {}
            for coord_key, atom_data in self.atoms.items():
                element = atom_data.get("main", "C")
                if not element:
                    element = "C"
                atom = Chem.Atom(element)
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
            return smiles if smiles else "C"
        except Exception:
            return "C"

    # ------------------------------------------------------------------
    # [Phase 6-3] Theory 모드 분자 선택/해제 시스템
    # ------------------------------------------------------------------
    def _find_atom_at_theory(self, l_pos):
        """Theory 레이어 좌표 기준으로 l_pos 근처의 원자 키를 탐색.
        theory_data["map"]의 매핑된 좌표를 사용하며, 없으면 원본 좌표 사용.
        Returns: atom_key tuple 또는 None"""
        if not self.analysis_results:
            return None
        t_map = self.analysis_results.get("theory_data", {}).get("map", {})
        hit_radius = 18 / self.scale_factor  # 클릭 허용 반경 (px, 논리 좌표)

        best_key = None
        best_dist = hit_radius
        for k in self.atoms:
            pt = t_map.get(k, QPointF(*k))
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
        if self.analysis_results:
            t_map = self.analysis_results.get("theory_data", {}).get("map", {})

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
        """선택된 분자의 IUPAC명/관용명을 PubChem에서 조회.
        네트워크 실패 시 SMILES를 폴백으로 표시."""
        self.selected_molecule_name = ""
        if not self.selected_molecule_keys:
            return

        smiles = self._get_molecule_smiles()
        if not smiles or smiles == "C":
            return

        # PubChem REST API 동기 호출 (timeout=5s)
        try:
            import requests
            import urllib.parse
            encoded = urllib.parse.quote(smiles, safe="")
            url = (
                f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/"
                f"compound/smiles/{encoded}/property/IUPACName/JSON"
            )
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                props = data.get("PropertyTable", {}).get("Properties", [])
                if props:
                    name = props[0].get("IUPACName", "")
                    if name:
                        self.selected_molecule_name = name
                        self.update()
                        return
        except Exception:
            pass

        # 폴백: SMILES 자체를 표시
        self.selected_molecule_name = smiles
        self.update()

    def _get_molecule_smiles(self):
        """선택된 분자 원자/결합만으로 SMILES 생성."""
        try:
            from rdkit import Chem

            mol_keys = self.selected_molecule_keys
            if not mol_keys:
                return ""

            editmol = Chem.RWMol(Chem.Mol())
            coord_to_idx = {}
            for coord_key in mol_keys:
                atom_data = self.atoms.get(coord_key, {})
                element = atom_data.get("main", "C")
                if not element:
                    element = "C"
                atom = Chem.Atom(element)
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
        except Exception:
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
            for r in range(int(vr.top() / (40 * 0.866)) - 1, int(vr.bottom() / (40 * 0.866)) + 2):
                off = 20 if r % 2 != 0 else 0
                for c in range(int(vr.left() / 40) - 1, int(vr.right() / 40) + 2):
                    p.drawEllipse(QPointF(c * 40 + off, r * 40 * 0.866), 1.5, 1.5)
            p.restore()

        # ===================== LAYER 2: 애니메이션 배경 (이전 뷰) =====================
        if self.view_state != "Drawing" and is_animating:
            p.save()
            p.translate(self.pan_offset)
            p.scale(self.scale_factor, self.scale_factor)
            max_r = math.hypot(self.width(), self.height()) * 0.8
            progress = min(self._reveal_radius / max_r, 1.0) if max_r > 0 else 1.0
            p.setOpacity(1.0 - progress * 0.3)

            # DFT density
            if self.dft_density_map and self.show_dft_density:
                try:
                    from renderer import DFTDensityRenderer
                    atom_charges = {
                        pos: d.effective_charge
                        for pos, d in zip(
                            [(round(d.position[0], 2), round(d.position[1], 2)) for d in self.dft_density_map.atom_densities],
                            self.dft_density_map.atom_densities,
                        )
                    }
                    DFTDensityRenderer.draw_dft_density_clouds(p, atom_charges, {})
                except Exception:
                    pass

            if hasattr(self, "analysis_results") and self.show_clouds:
                CloudRenderer.draw_clouds(p, self.analysis_results, use_theory_coords=False)
            for k, v in self.bonds.items():
                self.draw_bond(p, QPointF(*k[0]), QPointF(*k[1]), v, False)
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

            # DFT density
            if self.dft_density_map and self.show_dft_density:
                try:
                    from renderer import DFTDensityRenderer
                    atom_charges = {
                        pos: d.effective_charge
                        for pos, d in zip(
                            [(round(d.position[0], 2), round(d.position[1], 2)) for d in self.dft_density_map.atom_densities],
                            self.dft_density_map.atom_densities,
                        )
                    }
                    DFTDensityRenderer.draw_dft_density_clouds(p, atom_charges, {})
                except Exception:
                    pass

            # 전자구름
            if self.analysis_results and self.show_clouds:
                use_theory = self.view_state in ["Lewis", "Theory"]
                CloudRenderer.draw_clouds(p, self.analysis_results, use_theory_coords=use_theory)

            # 구조 렌더링
            if self.view_state == "Lewis" and self.analysis_results:
                LewisRenderer.render(p, self.atoms, self.bonds, self.analysis_results, self.selected_atoms, self.selected_bonds)
            elif self.view_state == "Theory" and self.analysis_results:
                TheoryRenderer.render(p, self.atoms, self.bonds, self.analysis_results, self.selected_atoms, self.selected_bonds)

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
            if self.view_state == "Theory" and self.selected_molecule_bbox:
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
                    font = QFont("Arial", 10)
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
            if hasattr(self, "analysis_results") and self.show_clouds:
                CloudRenderer.draw_clouds(p, self.analysis_results, use_theory_coords=False)

            # 2. 결합선
            for k, v in self.bonds.items():
                self.draw_bond(p, QPointF(*k[0]), QPointF(*k[1]), v, k in self.selected_bonds)

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
                        self.draw_bond(p, anchor + QPointF(*rel_b[0]), anchor + QPointF(*rel_b[1]), g_mode, False)

                elif closest and self.mode in ["LonePair", "Radical", "Positive", "Negative", "H"]:
                    k = get_coord_key(closest)
                    dx, dy = l_pos.x() - closest.x(), l_pos.y() - closest.y()
                    ang_deg = round((math.degrees(math.atan2(dy, dx)) % 360) / 60) * 60
                    ang = math.radians(ang_deg)
                    gp = QPointF(closest.x() + math.cos(ang) * 22, closest.y() + math.sin(ang) * 22)

                    if self.mode == "H":
                        p.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                        target_pos = (
                            closest
                            if (self.atoms.get(k, {"main": ""})["main"] == "" and math.hypot(dx, dy) < 12)
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
                        p.setFont(QFont("Arial", 14, QFont.Weight.Bold))
                        sym = "+" if self.mode == "Positive" else "-"
                        p.drawText(QRectF(gp.x() - 10, gp.y() - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, sym)

                elif closest and self.mode not in ["Wedge", "Dash", "Bond", "Select", "Hand", "Eraser", "Pen", "Arrow", "Text"]:
                    p.setFont(QFont("Arial", 12, QFont.Weight.Bold))
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

            # 펜 스트로크
            for s in self.strokes + [{"pts": self.temp_stroke, "clr": self.pen_color, "w": self.pen_width}]:
                if len(s["pts"]) >= 2:
                    p.setPen(QPen(s["clr"], s["w"] / self.scale_factor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    for i in range(len(s["pts"]) - 1):
                        p.drawLine(s["pts"][i], s["pts"][i + 1])

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

        # ===================== [v4 명령4] 텍스트 상자 — Text 모드일 때만 렌더링 =====================
        if self.mode == "Text" and self.text_boxes:
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
            CloudRenderer.draw_crosshairs_v32(p, self.analysis_results)
            p.restore()

    # ------------------------------------------------------------------
    # 결합 그리기
    # ------------------------------------------------------------------
    def draw_bond(self, p, p1, p2, data, sel):
        p.setPen(QPen(Qt.GlobalColor.blue if sel else Qt.GlobalColor.black, 2))
        v, bt_mode = 1, "Bond"
        if isinstance(data, int):
            v = data
        elif isinstance(data, tuple):
            p1, p2, bt_mode = data

        vec = p2 - p1
        l = math.hypot(vec.x(), vec.y())
        if l == 0:
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
                elem1 = self.atoms.get(k1, {}).get("main", "C")
                elem2 = self.atoms.get(k2, {}).get("main", "C")
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

    # ------------------------------------------------------------------
    # 원소 기호 그리기
    # ------------------------------------------------------------------
    def draw_atom_group(self, p, pt, data, sel):
        p.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        main = data["main"]
        fm = QFontMetrics(p.font())

        if main:
            tw = fm.horizontalAdvance(main)
            text_rect = QRectF(pt.x() - tw / 2, pt.y() - fm.height() / 2, tw, fm.height())
            p.setPen(Qt.GlobalColor.blue if sel else Qt.GlobalColor.black)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, main)

        for d, sym in data["attach"].items():
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
            elif sym == "+":
                p.save()
                p.setPen(QPen(p.pen().color(), 2.2))
                p.drawLine(QPointF(sx - 5, sy), QPointF(sx + 5, sy))
                p.drawLine(QPointF(sx, sy - 5), QPointF(sx, sy + 5))
                p.restore()
            elif sym == "-":
                p.save()
                p.setPen(QPen(p.pen().color(), 2.5))
                p.drawLine(QPointF(sx - 5, sy), QPointF(sx + 5, sy))
                p.restore()
            else:
                sw = fm.horizontalAdvance(sym)
                p.drawText(
                    QRectF(sx - sw / 2, sy - fm.height() / 2, sw, fm.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    sym,
                )

        # [v4 명령1] charge 필드 렌더링 — 원소 기호 우상단에 작은 위첨자로 표시
        charge_sym = data.get("charge", "")
        if charge_sym:
            p.save()
            charge_font = QFont("Arial", 9, QFont.Weight.Bold)
            p.setFont(charge_font)
            cfm = QFontMetrics(charge_font)
            label = main if main else "C"
            label_w = fm.horizontalAdvance(label)
            # 우상단 위첨자 위치
            cx = pt.x() + label_w / 2 + 1
            cy = pt.y() - fm.height() / 2 + cfm.ascent() - 2
            p.setPen(QColor(200, 0, 0) if charge_sym == "+" else QColor(0, 0, 200))
            p.drawText(QPointF(cx, cy), charge_sym)
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
        """화살표 1개를 그린다: 직선 + 삼각형 화살촉"""
        p.save()
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(start, end)

        # 화살촉 (삼각형)
        vec = end - start
        length = math.hypot(vec.x(), vec.y())
        if length > 0:
            ux, uy = vec.x() / length, vec.y() / length
            # 화살촉 크기
            head_len = min(12, length * 0.3)
            head_w = head_len * 0.4
            # 화살촉 꼭짓점 3개
            tip = end
            base = QPointF(end.x() - ux * head_len, end.y() - uy * head_len)
            left = QPointF(base.x() + uy * head_w, base.y() - ux * head_w)
            right = QPointF(base.x() - uy * head_w, base.y() + ux * head_w)
            p.setBrush(pen.color())
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([tip, left, right]))
        p.restore()

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
        """언더바+숫자를 유니코드 아래첨자로 변환: CH_3 → CH₃"""
        import re
        SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
        return re.sub(r'_(\d+)', lambda m: m.group(1).translate(SUBSCRIPT), text)

    def _draw_text_boxes(self, p):
        """Text 모드일 때 모든 텍스트 상자를 렌더링.
        - 빨간 점선 테두리
        - 텍스트 (아래첨자 변환 적용)
        - 편집 중인 상자는 커서(|) 표시"""
        for i, tb in enumerate(self.text_boxes):
            pos = tb["pos"]
            text = self._render_subscript(tb["text"]) if tb["text"] else ""
            font_size = tb.get("font_size", 12)
            is_editing = (i == self.text_editing_idx)

            font = QFont("Arial", font_size)
            p.setFont(font)
            fm = QFontMetrics(font)

            # 텍스트 크기 계산 (최소 폭 보장)
            display = text + "|" if is_editing else text
            tw = max(fm.horizontalAdvance(display if display else "T"), 30)
            th = fm.height() + 6
            box_rect = QRectF(pos.x() - 4, pos.y() - th / 2, tw + 8, th)

            # 빨간 점선 테두리
            p.save()
            border_pen = QPen(QColor(220, 50, 50), 1.0 / self.scale_factor, Qt.PenStyle.DashLine)
            p.setPen(border_pen)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawRect(box_rect)
            p.restore()

            # 텍스트 내용
            p.setPen(Qt.GlobalColor.black)
            p.drawText(
                QPointF(pos.x(), pos.y() + fm.ascent() / 2 - 1),
                display,
            )
