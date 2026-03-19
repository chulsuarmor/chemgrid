#!/usr/bin/env python3
"""
합성 경로 분석 팝업 (Synthesis Route Planner).
목표 분자 SMILES → 역합성 엔진으로 모든 합성 경로 탐색 →
플로차트 시각화 + 단계별 메커니즘 보기.
"""
import os
import sys
import traceback
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSplitter,
    QProgressBar, QMessageBox, QSizePolicy, QGroupBox,
    QToolTip, QApplication, QTextEdit,
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

from retrosynthesis_engine import RetrosynthesisEngine, SynthesisRoute, SynthesisStep
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
            except ImportError:
                pass

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
                            except Exception:
                                pass
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
# 백그라운드 역합성 스레드
# ═══════════════════════════════════════════════════════════
class RetrosynthesisThread(QThread):
    """백그라운드에서 합성 경로 탐색"""
    progress = pyqtSignal(str)       # 상태 메시지
    route_found = pyqtSignal(object) # SynthesisRoute 하나씩 전달
    finished_all = pyqtSignal(list)  # 전체 결과 리스트
    error = pyqtSignal(str)

    def __init__(self, target_smiles: str, max_depth=6, max_routes=30,
                 validate=True, timeout=15.0, parent=None):
        super().__init__(parent)
        self._target = target_smiles
        self._max_depth = max_depth
        self._max_routes = max_routes
        self._validate = validate
        self._timeout = timeout

    def run(self):
        try:
            self.progress.emit("역합성 엔진 초기화 중...")
            engine = RetrosynthesisEngine()
            self.progress.emit(f"경로 탐색 중... (최대 깊이: {self._max_depth})")
            routes = engine.find_routes(
                self._target,
                max_depth=self._max_depth,
                max_routes=self._max_routes,
                validate=self._validate,
                timeout_seconds=self._timeout,
            )
            self.progress.emit(f"완료: {len(routes)}개 경로 발견")
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
        self._node_rects.clear()
        self._atom_positions.clear()
        self._mechanism_cache.clear()
        self._recalc_size()
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
                         rect: QRectF, hetero_colors: dict) -> Dict[int, QPointF]:
        """RDKit 2D 좌표로 골격식을 직접 QPainter에 그림.
        다중 프래그먼트일 경우 각각 분리 렌더링 후 '+' 표시.

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
                frag_positions = RouteFlowchartWidget._render_skeletal(
                    painter, [frag_smi], frag_rect, hetero_colors)
                # Offset atom indices for multi-fragment merging
                for idx, pt in frag_positions.items():
                    merged_positions[idx + atom_offset] = pt
                # Count atoms in this fragment for offset
                try:
                    mol = Chem.MolFromSmiles(frag_smi)
                    if mol:
                        mol = Chem.RemoveHs(mol)
                        atom_offset += mol.GetNumAtoms()
                except Exception:
                    pass
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
                return {}
            mol = Chem.RemoveHs(mol)
            AllChem.Compute2DCoords(mol)
            # Kekulize: 방향족 결합 → 교차 단일/이중결합
            try:
                Chem.Kekulize(mol, clearAromaticFlags=False)
            except Exception:
                pass
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

        # 결합 그리기
        bond_pen = QPen(QColor(40, 40, 40), max(1.4, scale * 0.07))
        bond_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            p1, p2 = screen[i], screen[j]
            bt = bond.GetBondTypeAsDouble()

            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = (dx * dx + dy * dy) ** 0.5
            if length < 0.1:
                continue

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
            p.setPen(QPen(QColor(160, 160, 160)))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "경로를 선택해주세요")
            p.end()
            return

        route = self._route
        steps = route.steps

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
            atom_pos = self._render_skeletal(p, smiles_list, mol_rect, self._HETERO)
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
                    head = 7
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

                    head = 7
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
        """각 합성 단계에 대해 전자 이동 굽은 화살표를 오버레이"""
        if not self._route or not steps:
            return

        if self._mechanism_engine is None:
            try:
                self._mechanism_engine = MechanismEngine()
            except Exception:
                return

        for si, step in enumerate(steps):
            # node index: 0=시작물질, 1..N=각 step 생성물
            # 반응물 노드 인덱스 = si (step의 반응물), 생성물 = si+1
            reactant_node_idx = si
            reactant_positions = self._atom_positions.get(reactant_node_idx, {})
            if not reactant_positions:
                continue

            # 메커니즘 생성 (캐시)
            cache_key = f"{'.'.join(step.reactant_smiles)}>>>{step.product_smiles}"
            if cache_key not in self._mechanism_cache:
                try:
                    r_smi = ".".join(step.reactant_smiles)
                    mech = self._mechanism_engine.generate_mechanism(
                        r_smi, step.product_smiles)
                    self._mechanism_cache[cache_key] = mech
                except Exception:
                    self._mechanism_cache[cache_key] = None

            mech = self._mechanism_cache.get(cache_key)
            if mech is None:
                continue

            # 화살표 그리기: 첫 번째 메커니즘 단계의 화살표만 사용
            for mech_step in mech.steps[:1]:
                for arrow in mech_step.arrows:
                    from_idx = arrow.from_atom_idx
                    to_idx = arrow.to_atom_idx
                    if from_idx < 0 or to_idx < 0:
                        continue
                    start_pt = reactant_positions.get(from_idx)
                    end_pt = reactant_positions.get(to_idx)
                    if start_pt is None or end_pt is None:
                        continue

                    arrow_color = QColor(200, 30, 30, 180)  # 빨간색 반투명
                    if arrow.arrow_type == "full":
                        CurvedArrowRenderer.draw_full_arrow(
                            painter, start_pt, end_pt,
                            curvature=arrow.curvature,
                            color=arrow_color, width=1.8)
                    else:
                        CurvedArrowRenderer.draw_half_arrow(
                            painter, start_pt, end_pt,
                            curvature=arrow.curvature,
                            color=arrow_color, width=1.5)

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

        # 헤더: Route N ★
        header = QHBoxLayout()
        lbl_title = QLabel(f"경로 {self._index + 1}")
        lbl_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #E0E0E0;")
        header.addWidget(lbl_title)

        # 점수 뱃지
        score = self._route.score
        score_text = f"점수: {score:.0f}" if score != 0 else "직접 가용"
        lbl_score = QLabel(score_text)
        lbl_score.setFont(QFont("Segoe UI", 8))
        lbl_score.setStyleSheet("color: #FFA726; padding: 2px 6px; background: rgba(255,167,38,30); border-radius: 4px;")
        header.addWidget(lbl_score)
        header.addStretch()
        layout.addLayout(header)

        # 단계 수 + 시작물질
        steps_text = f"📐 {self._route.total_steps}단계"
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
        bb_text = "🧪 " + ", ".join(bb_names)
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
        if self._selected:
            self.setStyleSheet("""
                RouteCardWidget {
                    background: rgba(66, 165, 245, 40);
                    border: 2px solid #42A5F5;
                    border-radius: 8px;
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

    def set_step(self, step: Optional[SynthesisStep]):
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
        r_str = " + ".join(step.reactant_smiles)
        self._lbl_reaction.setText(f"{r_str}\n→ {step.product_smiles}")
        self._lbl_conditions.setText(f"조건: {step.conditions}" if step.conditions else "")
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
# 메인 합성 팝업
# ═══════════════════════════════════════════════════════════
class SynthesisPopup(QDialog):
    """합성 경로 분석 팝업 다이얼로그"""

    def __init__(self, target_smiles: str, target_name: str = "",
                 parent=None):
        super().__init__(parent)
        self._target_smi = target_smiles
        self._target_name = target_name or target_smiles
        self._routes: List[SynthesisRoute] = []
        self._selected_route_idx = -1
        self._selected_step_idx = -1
        self._thread: Optional[RetrosynthesisThread] = None
        self._route_cards: List[RouteCardWidget] = []

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

        # ═══ 우측 패널 (플로차트 + 상세) ═══
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setStyleSheet("""
            QSplitter::handle { background: #333; height: 3px; }
        """)

        # 플로차트 스크롤
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
        right_splitter.addWidget(flowchart_scroll)

        # 하단: 단계 상세
        self._step_detail = StepDetailPanel()
        self._step_detail.mechanism_requested.connect(self._open_mechanism)
        self._step_detail.gemini_requested.connect(self._on_gemini_analyze)
        self._step_detail.setFixedHeight(180)
        right_splitter.addWidget(self._step_detail)

        right_splitter.setSizes([500, 180])
        main_layout.addWidget(right_splitter, 1)

    def _render_target_image(self):
        """타겟 분자 2D 이미지 렌더링"""
        if not RDKIT_AVAILABLE:
            self._target_img_label.setText("RDKit 미설치")
            return
        try:
            mol = Chem.MolFromSmiles(self._target_smi)
            if mol is None:
                self._target_img_label.setText("유효하지 않은 SMILES")
                return
            img = Draw.MolToImage(mol, size=(220, 140))
            data = img.convert("RGBA").tobytes("raw", "RGBA")
            qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            pm = QPixmap.fromImage(qimg)
            self._target_img_label.setPixmap(pm)
        except Exception as e:
            self._target_img_label.setText(f"렌더링 실패: {e}")

    def _start_search(self):
        """백그라운드 역합성 검색 시작"""
        # 복잡한 분자 감지 → 파라미터 조정
        try:
            mol = Chem.MolFromSmiles(self._target_smi) if RDKIT_AVAILABLE else None
            n_heavy = mol.GetNumHeavyAtoms() if mol else 0
        except Exception:
            n_heavy = 0

        is_complex = n_heavy > 20
        timeout = 45.0 if is_complex else 20.0
        max_depth = 5 if is_complex else 6
        validate = not is_complex  # 복잡 분자는 mechanism 검증 건너뜀

        self._thread = RetrosynthesisThread(
            self._target_smi,
            max_depth=max_depth,
            max_routes=30,
            validate=validate,
            timeout=timeout,
            parent=self,
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_all.connect(self._on_routes_found)
        self._thread.error.connect(self._on_error)
        self._thread.start()

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

        if not routes:
            self._lbl_status.setText("경로를 찾지 못했습니다")
            self._lbl_status.setStyleSheet("color: #FFA726;")
            return

        self._lbl_status.setText(f"✅ {len(routes)}개 경로 발견")
        self._lbl_status.setStyleSheet("color: #66BB6A;")

        # 카드 생성
        # 기존 stretch 제거
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

        # 첫 번째 경로 자동 선택
        if routes:
            self._on_route_selected(0)

    def _on_route_selected(self, idx: int):
        """경로 카드 클릭 → 플로차트 갱신"""
        if idx < 0 or idx >= len(self._routes):
            return

        # 이전 선택 해제
        for card in self._route_cards:
            card.set_selected(False)

        self._selected_route_idx = idx
        self._route_cards[idx].set_selected(True)
        self._flowchart.set_route(self._routes[idx])
        self._step_detail.set_has_route(True)   # route available → Gemini enabled
        self._step_detail.set_step(None)         # 단계 선택 초기화
        self._btn_export_pdf.setEnabled(True)    # PDF 내보내기 활성화

    def _on_step_clicked(self, step_idx: int):
        """플로차트에서 단계 클릭"""
        route = self._routes[self._selected_route_idx]
        if 0 <= step_idx < len(route.steps):
            self._step_detail.set_step(route.steps[step_idx])
            self._btn_reaction_anim.setEnabled(True)
            self._selected_step_idx = step_idx

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
            popup.exec()
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
                except Exception:
                    pass  # 파일 열기 실패해도 무시
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
        except Exception:
            pass

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
            except Exception:
                pass

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
                            parent=None):
    """외부에서 합성 경로 분석 팝업을 열 때 사용"""
    popup = SynthesisPopup(target_smiles, target_name, parent=parent)
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
