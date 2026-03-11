# popup_reaction.py (v1.0 - Organic Synthesis Reaction Popup)
"""
ChemGrid: 유기합성반응 분석 팝업
- 두 분자의 가능한 반응 경로 목록 표시
- 반응 메커니즘 단계별 시각화 (곡선 화살표, 전자 이동)
- QPainter 기반 2D 분자 구조 + 화살표 렌더링
"""

import math
import logging
from typing import List, Optional, Dict, Tuple

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QTextEdit, QSlider, QFrame, QScrollArea,
    QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath,
    QLinearGradient, QRadialGradient, QPaintEvent
)

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from reaction_predictor import ReactionPredictor, ReactionPathway, FunctionalGroup
from reaction_mechanisms import (
    get_mechanism, MechanismData, MechanismStep, ArrowData
)


# ============================================================================
# CPK COLORS (for 2D molecule rendering)
# ============================================================================
CPK_COLORS = {
    "C": QColor(80, 80, 80), "H": QColor(200, 200, 200),
    "O": QColor(230, 50, 50), "N": QColor(50, 80, 230),
    "S": QColor(220, 200, 50), "P": QColor(255, 165, 0),
    "F": QColor(50, 200, 50), "Cl": QColor(50, 200, 50),
    "Br": QColor(165, 42, 42), "I": QColor(148, 0, 211),
}


# ============================================================================
# CURVED ARROW RENDERER
# ============================================================================

class CurvedArrowRenderer:
    """곡선 화살표 렌더링 (2전자 = 실선, 1전자 = 반쪽 피셔훅)"""

    @staticmethod
    def draw_full_arrow(painter: QPainter, start: QPointF, end: QPointF,
                        curvature: float = 0.3, color: QColor = QColor("#E53935"),
                        width: float = 2.5):
        """2전자 이동 곡선 화살표 (실선, 꽉 찬 화살촉)"""
        painter.save()

        # Control point for Bézier curve
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx*dx + dy*dy)
        if length < 1:
            painter.restore()
            return

        # Perpendicular offset for curvature
        perp_x = -dy / length * curvature * length
        perp_y = dx / length * curvature * length
        ctrl = QPointF(mid.x() + perp_x, mid.y() + perp_y)

        # Draw curve
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(ctrl, end)
        painter.drawPath(path)

        # Arrowhead (filled triangle)
        arrow_size = 10
        # Direction at endpoint (tangent of quadratic Bézier at t=1)
        tx = end.x() - ctrl.x()
        ty = end.y() - ctrl.y()
        tlen = math.sqrt(tx*tx + ty*ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen

        # Two points of arrowhead
        px1 = end.x() - arrow_size * tx + arrow_size * 0.4 * ty
        py1 = end.y() - arrow_size * ty - arrow_size * 0.4 * tx
        px2 = end.x() - arrow_size * tx - arrow_size * 0.4 * ty
        py2 = end.y() - arrow_size * ty + arrow_size * 0.4 * tx

        arrow_path = QPainterPath()
        arrow_path.moveTo(end)
        arrow_path.lineTo(QPointF(px1, py1))
        arrow_path.lineTo(QPointF(px2, py2))
        arrow_path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(arrow_path)

        painter.restore()

    @staticmethod
    def draw_half_arrow(painter: QPainter, start: QPointF, end: QPointF,
                        curvature: float = 0.3, color: QColor = QColor("#FF9800"),
                        width: float = 2.0):
        """1전자 이동 피셔훅 화살표 (단일 바브)"""
        painter.save()

        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx*dx + dy*dy)
        if length < 1:
            painter.restore()
            return

        perp_x = -dy / length * curvature * length
        perp_y = dx / length * curvature * length
        ctrl = QPointF(mid.x() + perp_x, mid.y() + perp_y)

        # Draw curve
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(ctrl, end)
        painter.drawPath(path)

        # Single barb (fishhook)
        arrow_size = 10
        tx = end.x() - ctrl.x()
        ty = end.y() - ctrl.y()
        tlen = math.sqrt(tx*tx + ty*ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen

        bx = end.x() - arrow_size * tx + arrow_size * 0.5 * ty
        by = end.y() - arrow_size * ty - arrow_size * 0.5 * tx

        pen2 = QPen(color, width + 0.5)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawLine(end, QPointF(bx, by))

        painter.restore()


# ============================================================================
# MOLECULE 2D WIDGET (simplified rendering from SMILES)
# ============================================================================

class Molecule2DWidget(QWidget):
    """RDKit SMILES → 2D 구조 렌더링 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smiles = ""
        self._name = ""
        self._coords = []   # [(x, y, symbol)]
        self._bonds = []     # [(i, j, order)]
        self._highlight_color = None
        self.setMinimumSize(180, 150)

    def set_molecule(self, smiles: str, name: str = "", highlight_color: QColor = None):
        self._smiles = smiles
        self._name = name
        self._highlight_color = highlight_color
        self._compute_2d()
        self.update()

    def _compute_2d(self):
        self._coords = []
        self._bonds = []
        if not RDKIT_AVAILABLE or not self._smiles:
            return
        mol = Chem.MolFromSmiles(self._smiles)
        if mol is None:
            return
        AllChem.Compute2DCoords(mol)
        conf = mol.GetConformer()
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            sym = mol.GetAtomWithIdx(i).GetSymbol()
            self._coords.append((pos.x, pos.y, sym))
        for bond in mol.GetBonds():
            self._bonds.append((
                bond.GetBeginAtomIdx(),
                bond.GetEndAtomIdx(),
                bond.GetBondTypeAsDouble()
            ))

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(30, 30, 30))

        # Highlight border
        if self._highlight_color:
            pen = QPen(self._highlight_color, 3, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(2, 2, w - 4, h - 4)

        if not self._coords:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             self._smiles or "분자 없음")
            return

        # Transform coords to fit widget
        xs = [c[0] for c in self._coords]
        ys = [c[1] for c in self._coords]
        if len(xs) < 2:
            cx, cy = xs[0] if xs else 0, ys[0] if ys else 0
            scale = 1.0
        else:
            cx = (min(xs) + max(xs)) / 2
            cy = (min(ys) + max(ys)) / 2
            rx = (max(xs) - min(xs)) or 1
            ry = (max(ys) - min(ys)) or 1
            scale = min((w - 60) / rx, (h - 60) / ry) * 0.8

        def tx(x, y):
            return QPointF(w/2 + (x - cx) * scale, h/2 - (y - cy) * scale)

        # Draw bonds
        for i, j, order in self._bonds:
            p1 = tx(self._coords[i][0], self._coords[i][1])
            p2 = tx(self._coords[j][0], self._coords[j][1])
            pen = QPen(QColor(180, 180, 180), 2)
            painter.setPen(pen)
            if order >= 2:
                # Double bond offset
                dx = p2.x() - p1.x()
                dy = p2.y() - p1.y()
                ln = math.sqrt(dx*dx + dy*dy) or 1
                ox, oy = -dy/ln * 2, dx/ln * 2
                painter.drawLine(QPointF(p1.x()+ox, p1.y()+oy),
                                 QPointF(p2.x()+ox, p2.y()+oy))
                painter.drawLine(QPointF(p1.x()-ox, p1.y()-oy),
                                 QPointF(p2.x()-ox, p2.y()-oy))
                if order >= 3:
                    painter.drawLine(p1, p2)
            else:
                painter.drawLine(p1, p2)

        # Draw atoms
        font = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font)
        for x, y, sym in self._coords:
            pt = tx(x, y)
            color = CPK_COLORS.get(sym, QColor(200, 200, 200))
            if sym != "C":  # Don't draw C labels (skeletal)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(30, 30, 30)))
                painter.drawEllipse(pt, 10, 10)
                painter.setPen(color)
                painter.drawText(QRectF(pt.x()-10, pt.y()-8, 20, 16),
                                 Qt.AlignmentFlag.AlignCenter, sym)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(pt, 3, 3)

        # Name label
        if self._name:
            painter.setPen(QColor(200, 200, 200))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(QRectF(5, h - 22, w - 10, 20),
                             Qt.AlignmentFlag.AlignCenter, self._name)


# ============================================================================
# MECHANISM STEP WIDGET
# ============================================================================

class MechanismStepWidget(QWidget):
    """단일 메커니즘 단계 시각화 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step: Optional[MechanismStep] = None
        self.setMinimumHeight(200)

    def set_step(self, step: MechanismStep):
        self._step = step
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(25, 25, 30))

        if not self._step:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "반응 경로를 선택하세요")
            return

        step = self._step

        # Title bar
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(40, 60, 80)))
        painter.drawRoundedRect(QRectF(10, 10, w - 20, 36), 6, 6)
        painter.setPen(QColor(200, 220, 255))
        painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        painter.drawText(QRectF(20, 10, w - 40, 36), Qt.AlignmentFlag.AlignVCenter,
                         f"Step {step.step_number}: {step.title}")

        # Draw arrows visualization area
        arrow_area = QRectF(20, 56, w - 40, h - 120)
        painter.setPen(QPen(QColor(60, 60, 70), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(arrow_area, 4, 4)

        # Draw schematic arrows
        if step.arrows:
            n_arrows = len(step.arrows)
            for i, arrow in enumerate(step.arrows):
                y_frac = (i + 0.5) / max(n_arrows, 1)
                ay = arrow_area.top() + arrow_area.height() * y_frac

                # Arrow start/end
                ax_start = arrow_area.left() + 40
                ax_end = arrow_area.right() - 40

                start_pt = QPointF(ax_start, ay)
                end_pt = QPointF(ax_end, ay)

                color = QColor(arrow.color)
                if arrow.arrow_type == "full":
                    CurvedArrowRenderer.draw_full_arrow(
                        painter, start_pt, end_pt,
                        curvature=arrow.curvature * (0.3 if i % 2 == 0 else -0.3),
                        color=color, width=2.5)
                else:
                    CurvedArrowRenderer.draw_half_arrow(
                        painter, start_pt, end_pt,
                        curvature=arrow.curvature * (0.3 if i % 2 == 0 else -0.3),
                        color=color, width=2.0)

                # Labels
                painter.setPen(color)
                painter.setFont(QFont("Arial", 8))
                painter.drawText(QRectF(ax_start - 35, ay - 10, 70, 20),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 arrow.from_label[:15])
                painter.drawText(QRectF(ax_end - 35, ay - 10, 70, 20),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 arrow.to_label[:15])

        # Draw labels
        if step.labels:
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            lbl_y = arrow_area.bottom() + 5
            lbl_x = 30
            for key, val in step.labels.items():
                painter.setPen(QColor(180, 200, 255))
                painter.drawText(QPointF(lbl_x, lbl_y + 14), f"{key}: {val}")
                lbl_x += 180
                if lbl_x > w - 50:
                    lbl_x = 30
                    lbl_y += 18

        # Description at bottom
        desc_y = h - 55
        painter.setPen(QColor(170, 170, 180))
        painter.setFont(QFont("Arial", 8))
        # Word wrap manually for 2 lines
        desc = step.description.replace("\n", " ")
        max_chars = (w - 40) // 6
        if len(desc) > max_chars:
            # Split at word boundary
            split = desc[:max_chars].rfind(" ")
            if split < 0:
                split = max_chars
            painter.drawText(QPointF(20, desc_y), desc[:split])
            painter.drawText(QPointF(20, desc_y + 14), desc[split:split+max_chars])
        else:
            painter.drawText(QPointF(20, desc_y), desc)

        # Energy label
        if step.energy_label:
            painter.setPen(QColor(255, 200, 100))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(QRectF(w - 200, h - 25, 190, 20),
                             Qt.AlignmentFlag.AlignRight, f"⚡ {step.energy_label}")

        painter.end()


# ============================================================================
# ENERGY DIAGRAM WIDGET
# ============================================================================

class EnergyDiagramWidget(QWidget):
    """반응 에너지 다이어그램"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []
        self.setMinimumHeight(120)
        self.setMaximumHeight(160)

    def set_data(self, energy_diagram: List[Tuple[str, float]]):
        self._data = energy_diagram
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(20, 20, 25))

        if not self._data:
            return

        # Calculate scale
        energies = [e for _, e in self._data]
        e_min, e_max = min(energies), max(energies)
        e_range = (e_max - e_min) or 1

        margin_x, margin_y = 50, 25
        plot_w = w - 2 * margin_x
        plot_h = h - 2 * margin_y

        n = len(self._data)
        points = []
        for i, (label, energy) in enumerate(self._data):
            x = margin_x + plot_w * i / max(n - 1, 1)
            y = margin_y + plot_h * (1 - (energy - e_min) / e_range)
            points.append((x, y, label, energy))

        # Draw path
        pen = QPen(QColor(100, 180, 255), 2)
        painter.setPen(pen)
        for i in range(len(points) - 1):
            painter.drawLine(QPointF(points[i][0], points[i][1]),
                             QPointF(points[i+1][0], points[i+1][1]))

        # Draw points and labels
        font = QFont("Arial", 7)
        painter.setFont(font)
        for x, y, label, energy in points:
            # Point
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 200, 100)))
            painter.drawEllipse(QPointF(x, y), 4, 4)

            # Label
            painter.setPen(QColor(180, 180, 200))
            label_lines = label.split("\n")
            ly = y - 12
            for line in label_lines:
                painter.drawText(QRectF(x - 50, ly, 100, 12),
                                 Qt.AlignmentFlag.AlignCenter, line)
                ly -= 11

        # Y-axis label
        painter.setPen(QColor(120, 120, 140))
        painter.setFont(QFont("Arial", 7))
        painter.save()
        painter.translate(12, h / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-40, -8, 80, 16), Qt.AlignmentFlag.AlignCenter, "에너지")
        painter.restore()

        painter.end()


# ============================================================================
# MAIN REACTION POPUP
# ============================================================================

class ReactionPopup(QDialog):
    """유기합성반응 분석 팝업"""

    def __init__(self, smiles_list: List[str], names: List[str] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔬 유기합성반응 분석")
        self.setMinimumSize(950, 720)
        self.resize(1000, 750)
        self.setStyleSheet("""
            QDialog { background: #1a1a1e; color: #ddd; }
            QGroupBox { border: 1px solid #444; border-radius: 4px;
                        margin-top: 8px; padding-top: 12px; color: #bbb; }
            QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }
            QListWidget { background: #252530; color: #ddd; border: 1px solid #444;
                          font-size: 10pt; }
            QListWidget::item:selected { background: #1565C0; }
            QTextEdit { background: #252530; color: #ccc; border: 1px solid #444;
                        font-size: 9pt; }
        """)

        self._smiles = smiles_list[:4]  # 최대 4개 분자
        self._names = names or [f"분자 {chr(65+i)}" for i in range(len(self._smiles))]
        self._predictor = ReactionPredictor()
        self._pathways: List[ReactionPathway] = []
        self._current_mechanism: Optional[MechanismData] = None
        self._current_step_idx = 0

        self._init_ui()
        self._run_prediction()

    def _init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ═══ 상단: 분자 + 반응 목록 ═══
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 왼쪽: 분자 카드 ──
        mol_panel = QWidget()
        mol_layout = QVBoxLayout()
        mol_layout.setContentsMargins(4, 4, 4, 4)

        mol_layout.addWidget(QLabel("📦 반응물"))

        COLORS = [QColor("#FF6B6B"), QColor("#4FC3F7"), QColor("#81C784"), QColor("#FFD54F")]
        self._mol_widgets = []
        for i, smiles in enumerate(self._smiles):
            mw = Molecule2DWidget()
            color = COLORS[i % len(COLORS)]
            mw.set_molecule(smiles, self._names[i], highlight_color=color)
            mw.setMaximumHeight(180)
            self._mol_widgets.append(mw)
            mol_layout.addWidget(mw)

        mol_layout.addStretch()
        mol_panel.setLayout(mol_layout)
        mol_panel.setMaximumWidth(250)

        # ── 오른쪽: 반응 경로 목록 ──
        reaction_panel = QWidget()
        reaction_layout = QVBoxLayout()
        reaction_layout.setContentsMargins(4, 4, 4, 4)

        reaction_layout.addWidget(QLabel("⚗ 가능한 반응 경로"))

        self.reaction_list = QListWidget()
        self.reaction_list.currentRowChanged.connect(self._on_reaction_selected)
        reaction_layout.addWidget(self.reaction_list)

        # 반응 상세 정보
        self.reaction_info = QTextEdit()
        self.reaction_info.setReadOnly(True)
        self.reaction_info.setMaximumHeight(120)
        self.reaction_info.setPlaceholderText("반응을 선택하면 상세 정보가 표시됩니다.")
        reaction_layout.addWidget(self.reaction_info)

        reaction_panel.setLayout(reaction_layout)

        top_splitter.addWidget(mol_panel)
        top_splitter.addWidget(reaction_panel)
        top_splitter.setSizes([250, 700])

        main_layout.addWidget(top_splitter)

        # ═══ 하단: 메커니즘 시각화 ═══
        mech_group = QGroupBox("📋 반응 메커니즘 (단계별)")
        mech_layout = QVBoxLayout()

        # Step navigation
        nav_bar = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 이전")
        self.btn_prev.clicked.connect(self._prev_step)
        self.btn_prev.setEnabled(False)
        nav_bar.addWidget(self.btn_prev)

        self.step_label = QLabel("반응을 선택하세요")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #90CAF9;")
        nav_bar.addWidget(self.step_label)

        self.btn_next = QPushButton("다음 ▶")
        self.btn_next.clicked.connect(self._next_step)
        self.btn_next.setEnabled(False)
        nav_bar.addWidget(self.btn_next)

        mech_layout.addLayout(nav_bar)

        # Mechanism visualization
        self.mech_widget = MechanismStepWidget()
        mech_layout.addWidget(self.mech_widget)

        # Energy diagram
        self.energy_widget = EnergyDiagramWidget()
        mech_layout.addWidget(self.energy_widget)

        # Description
        self.step_desc = QLabel("")
        self.step_desc.setWordWrap(True)
        self.step_desc.setStyleSheet("color: #aaa; font-size: 9pt; padding: 4px;")
        mech_layout.addWidget(self.step_desc)

        mech_group.setLayout(mech_layout)
        main_layout.addWidget(mech_group)

        self.setLayout(main_layout)

    def _run_prediction(self):
        """반응 예측 실행"""
        if len(self._smiles) < 2:
            self.reaction_list.addItem("⚠️ 2개 이상의 분자가 필요합니다")
            return

        # 모든 분자 쌍에 대해 예측
        all_pathways = []
        seen = set()
        for i in range(len(self._smiles)):
            for j in range(i + 1, len(self._smiles)):
                pathways = self._predictor.predict(self._smiles[i], self._smiles[j])
                for pw in pathways:
                    key = (pw.mechanism_type, pw.name)
                    if key not in seen:
                        seen.add(key)
                        all_pathways.append(pw)

        self._pathways = sorted(all_pathways, key=lambda p: p.confidence, reverse=True)

        if not self._pathways:
            self.reaction_list.addItem("⚠️ 감지된 반응 경로가 없습니다")
            self.reaction_list.addItem("  작용기를 포함한 분자를 그려보세요")
            self.reaction_list.addItem("  예: 알코올 + 할로겐화물, 카르복실산 + 아민")
            return

        for pw in self._pathways:
            stars = "★" * int(pw.confidence * 5)
            item = QListWidgetItem(f"{pw.category} | {pw.name}  {stars}")
            self.reaction_list.addItem(item)

    def _on_reaction_selected(self, row):
        """반응 경로 선택 시"""
        if row < 0 or row >= len(self._pathways):
            return

        pw = self._pathways[row]

        # 상세 정보 표시
        summary = self._predictor.get_reaction_summary(pw)
        self.reaction_info.setPlainText(summary)

        # 메커니즘 로드
        mech = get_mechanism(pw.mechanism_type)
        if mech:
            self._current_mechanism = mech
            self._current_step_idx = 0
            self._update_mechanism_display()
            self.energy_widget.set_data(mech.energy_diagram)
        else:
            self._current_mechanism = None
            self.step_label.setText(f"메커니즘 데이터 없음 ({pw.mechanism_type})")
            self.mech_widget.set_step(None)
            self.energy_widget.set_data([])
            self.step_desc.setText(pw.description)

    def _update_mechanism_display(self):
        """현재 메커니즘 단계 표시"""
        if not self._current_mechanism:
            return

        mech = self._current_mechanism
        idx = self._current_step_idx
        total = mech.total_steps

        self.step_label.setText(f"Step {idx + 1} / {total}  —  {mech.title}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < total - 1)

        if idx < len(mech.steps):
            step = mech.steps[idx]
            self.mech_widget.set_step(step)
            self.step_desc.setText(step.description)
            if step.notes:
                self.step_desc.setText(f"{step.description}\n\n💡 {step.notes}")

    def _prev_step(self):
        if self._current_step_idx > 0:
            self._current_step_idx -= 1
            self._update_mechanism_display()

    def _next_step(self):
        if self._current_mechanism and self._current_step_idx < self._current_mechanism.total_steps - 1:
            self._current_step_idx += 1
            self._update_mechanism_display()
