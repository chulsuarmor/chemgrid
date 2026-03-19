# popup_reaction.py (v2.0 - Textbook-Style Organic Reaction Mechanism Popup)
"""
ChemGrid: 유기합성반응 분석 팝업 — 교과서 스타일
- 흰 배경 + 검은 화살표 (유기화학 전공서 스타일)
- Atom-mapped 곡선 화살표 (실제 원자 좌표 기반)
- 반응식 레이아웃: Reactants → [Intermediate] → Products
- 시약/조건 라벨 (화살표 위/아래)
"""

import math
import logging
from typing import List, Optional, Dict, Tuple

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QTextEdit, QSlider, QFrame, QScrollArea,
    QApplication, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal, QSizeF
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath,
    QLinearGradient, QRadialGradient, QPaintEvent, QFontMetrics
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
# TEXTBOOK COLORS
# ============================================================================
COLOR_BG = QColor(255, 255, 255)          # 흰 배경
COLOR_BOND = QColor(0, 0, 0)             # 검은 결합선
COLOR_ARROW = QColor(200, 30, 30)        # 빨간 곡선 화살표 (교과서 스타일)
COLOR_ARROW_RADICAL = QColor(200, 30, 30)  # 빨간 피셔훅
COLOR_LABEL = QColor(0, 0, 0)            # 검은 라벨
COLOR_CHARGE = QColor(200, 0, 0)         # 빨간 전하 표기
COLOR_REAGENT = QColor(0, 80, 180)       # 파란 시약 텍스트
COLOR_TRANSITION = QColor(100, 100, 100)  # 회색 전이상태 괄호
COLOR_ENERGY_LINE = QColor(0, 100, 200)   # 파란 에너지선
COLOR_ENERGY_PT = QColor(200, 50, 50)     # 빨간 에너지점

# CPK colors for heteroatoms
HETEROATOM_COLORS = {
    "O": QColor(200, 0, 0),
    "N": QColor(0, 0, 200),
    "S": QColor(180, 160, 0),
    "P": QColor(200, 120, 0),
    "F": QColor(0, 160, 0),
    "Cl": QColor(0, 160, 0),
    "Br": QColor(140, 40, 40),
    "I": QColor(120, 0, 160),
}


# ============================================================================
# TEXTBOOK MOLECULE RENDERER (QPainter-based, skeletal formula)
# ============================================================================

class TextbookMoleculeRenderer:
    """교과서 스타일 골격식 분자 렌더링 — RDKit 2D 좌표 기반"""

    @staticmethod
    def render(painter: QPainter, mol, rect: QRectF,
               show_atom_indices: bool = False,
               highlight_atoms: List[int] = None,
               is_product: bool = False) -> Dict[int, QPointF]:
        """분자를 골격식으로 렌더링하고 각 원자의 화면 좌표를 반환

        멀티 프래그먼트 SMILES (A.B 형태)는 각 프래그먼트를 분리 렌더링하고
        사이에 '+' 기호를 표시합니다.

        Returns:
            Dict[int, QPointF] — {atom_idx: pixel_position}
        """
        atom_positions = {}
        if mol is None:
            return atom_positions

        # ── 프래그먼트 분리 ──
        frags = Chem.GetMolFrags(mol, asMols=False)
        n_frags = len(frags)

        AllChem.Compute2DCoords(mol)
        conf = mol.GetConformer()

        # Collect coordinates
        coords = []
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            coords.append((pos.x, pos.y, mol.GetAtomWithIdx(i)))

        if not coords:
            return atom_positions

        # ── 프래그먼트별 좌표 분리 & 재배치 ──
        if n_frags > 1:
            # 각 프래그먼트의 bounding box 계산 후 가로로 재배치
            frag_data = []  # [(atom_indices, x_min, x_max, y_min, y_max, cx, cy)]
            for frag_atoms in frags:
                fxs = [coords[a][0] for a in frag_atoms]
                fys = [coords[a][1] for a in frag_atoms]
                frag_data.append({
                    'atoms': frag_atoms,
                    'xmin': min(fxs), 'xmax': max(fxs),
                    'ymin': min(fys), 'ymax': max(fys),
                    'cx': (min(fxs) + max(fxs)) / 2,
                    'cy': (min(fys) + max(fys)) / 2,
                })

            # 프래그먼트 간 간격 (RDKit 좌표 공간)
            gap = 2.5  # RDKit 단위로 프래그먼트 사이 간격
            plus_gap = 0.8  # '+' 기호용 추가 공간

            # 모든 프래그먼트를 가로 일렬로 재배치
            current_x = 0.0
            for fi, fd in enumerate(frag_data):
                fw = (fd['xmax'] - fd['xmin']) or 1.0
                fh = (fd['ymax'] - fd['ymin']) or 1.0
                # 프래그먼트 중심을 현재 x 위치로 이동
                shift_x = current_x + fw / 2 - fd['cx']
                # Y 중심은 0으로 맞춤
                shift_y = -fd['cy']
                for a in fd['atoms']:
                    old_x, old_y, atom_obj = coords[a]
                    coords[a] = (old_x + shift_x, old_y + shift_y, atom_obj)
                current_x += fw + gap + plus_gap

        # Calculate transform to fit rect
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]

        if len(xs) < 2:
            cx, cy = xs[0], ys[0]
            scale = 30.0
        else:
            cx = (min(xs) + max(xs)) / 2
            cy = (min(ys) + max(ys)) / 2
            rx = (max(xs) - min(xs)) or 1
            ry = (max(ys) - min(ys)) or 1
            margin = 22
            scale = min((rect.width() - margin * 2) / rx,
                        (rect.height() - margin * 2) / ry) * 0.78

        def tx(x, y):
            return QPointF(
                rect.x() + rect.width() / 2 + (x - cx) * scale,
                rect.y() + rect.height() / 2 - (y - cy) * scale
            )

        # Store atom positions
        for i, (x, y, atom) in enumerate(coords):
            atom_positions[i] = tx(x, y)

        # ── 프래그먼트 사이 '+' 기호 그리기 ──
        if n_frags > 1:
            painter.save()
            painter.setPen(COLOR_BOND)
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            for fi in range(n_frags - 1):
                # fi번째 프래그먼트의 오른쪽 끝과 fi+1번째의 왼쪽 끝 사이
                frag_r = frags[fi]
                frag_next = frags[fi + 1]
                # 오른쪽 끝 원자의 x 최대값
                rx_max = max(atom_positions[a].x() for a in frag_r)
                rx_y = sum(atom_positions[a].y() for a in frag_r) / len(frag_r)
                # 왼쪽 끝 원자의 x 최소값
                lx_min = min(atom_positions[a].x() for a in frag_next)
                lx_y = sum(atom_positions[a].y() for a in frag_next) / len(frag_next)
                plus_x = (rx_max + lx_min) / 2
                plus_y = (rx_y + lx_y) / 2
                painter.drawText(QRectF(plus_x - 8, plus_y - 8, 16, 16),
                                 Qt.AlignmentFlag.AlignCenter, "+")
            painter.restore()

        # ── Kekulize: 방향족 → 교대 이중결합 (케쿨레 구조) ──
        # 반응 메커니즘에서는 어떤 π결합이 끊어지는지 보여야 하므로
        # 비편재화 원(circle) 대신 명시적 이중결합으로 표현
        kekulized_orders = {}  # (min_i, max_j) -> bond_order
        try:
            mol_kek = Chem.RWMol(mol)
            Chem.Kekulize(mol_kek, clearAromaticFlags=False)
            for bond in mol_kek.GetBonds():
                bi = bond.GetBeginAtomIdx()
                bj = bond.GetEndAtomIdx()
                key = (min(bi, bj), max(bi, bj))
                kekulized_orders[key] = bond.GetBondTypeAsDouble()
        except Exception:
            pass  # Kekulize 실패 시 원래 bond order 사용

        # ── Product delocalization: aromatic rings use circle instead of kekulé ──
        aromatic_rings = []
        if is_product and RDKIT_AVAILABLE:
            ring_info = mol.GetRingInfo()
            for ring in ring_info.AtomRings():
                if len(ring) >= 5 and all(
                    mol.GetAtomWithIdx(a).GetIsAromatic() for a in ring
                ):
                    aromatic_rings.append(ring)
            if aromatic_rings:
                # Clear kekulized orders so aromatic bonds draw as single lines
                # (circle will indicate delocalization)
                for ring in aromatic_rings:
                    for k in range(len(ring)):
                        a1 = ring[k]
                        a2 = ring[(k + 1) % len(ring)]
                        key = (min(a1, a2), max(a1, a2))
                        kekulized_orders[key] = 1.0  # Force single bond

        # ── Draw bonds ──
        pen_bond = QPen(COLOR_BOND, 2.0)
        pen_bond.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_thin = QPen(COLOR_BOND, 1.2)
        pen_thin.setCapStyle(Qt.PenCapStyle.RoundCap)

        for bond in mol.GetBonds():
            i = bond.GetBeginAtomIdx()
            j = bond.GetEndAtomIdx()
            p1 = atom_positions[i]
            p2 = atom_positions[j]

            # Shorten bonds to heteroatoms
            sym_i = coords[i][2].GetSymbol()
            sym_j = coords[j][2].GetSymbol()
            charge_i = coords[i][2].GetFormalCharge()
            charge_j = coords[j][2].GetFormalCharge()
            p1_draw, p2_draw = p1, p2
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1:
                continue

            show_label_i = (sym_i != "C") or (charge_i != 0)
            show_label_j = (sym_j != "C") or (charge_j != 0)
            if show_label_i:
                p1_draw = QPointF(p1.x() + dx / length * 10,
                                  p1.y() + dy / length * 10)
            if show_label_j:
                p2_draw = QPointF(p2.x() - dx / length * 10,
                                  p2.y() - dy / length * 10)

            bond_pair = (min(i, j), max(i, j))
            # 케쿨레 구조 우선 사용 (방향족 → 교대 이중결합)
            order = kekulized_orders.get(bond_pair, bond.GetBondTypeAsDouble())

            if order >= 3:
                # Triple bond: 중심선 + 양쪽 보조선
                gap = 4.5
                nx, ny = -dy / length * gap, dx / length * gap
                painter.setPen(pen_bond)
                painter.drawLine(p1_draw, p2_draw)
                painter.setPen(pen_thin)
                painter.drawLine(
                    QPointF(p1_draw.x() + nx, p1_draw.y() + ny),
                    QPointF(p2_draw.x() + nx, p2_draw.y() + ny))
                painter.drawLine(
                    QPointF(p1_draw.x() - nx, p1_draw.y() - ny),
                    QPointF(p2_draw.x() - nx, p2_draw.y() - ny))
            elif order >= 2.0:
                # Double bond: 주선 + 오프셋 보조선 (indented)
                # 보조선을 약간 짧게 해서 이중결합 확실히 구분
                gap = 4.5  # 3.0→4.5 확대 (단일결합과 명확히 구분)
                nx, ny = -dy / length * gap, dx / length * gap
                # 보조선 indent: 양쪽 끝 15% 안쪽으로
                indent = 0.15
                q1 = QPointF(p1_draw.x() + dx * indent + nx,
                             p1_draw.y() + dy * indent + ny)
                q2 = QPointF(p2_draw.x() - dx * indent + nx,
                             p2_draw.y() - dy * indent + ny)
                painter.setPen(pen_bond)
                painter.drawLine(p1_draw, p2_draw)
                painter.setPen(pen_thin)
                painter.drawLine(q1, q2)
            else:
                # Single bond
                painter.setPen(pen_bond)
                painter.drawLine(p1_draw, p2_draw)

        # (방향족 원 제거 — 케쿨레 이중결합으로 대체)
        # Product molecules: draw inscribed circle for aromatic rings
        if is_product and aromatic_rings:
            painter.save()
            pen_circle = QPen(COLOR_BOND, 1.2)
            painter.setPen(pen_circle)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for ring in aromatic_rings:
                # Calculate ring center and radius
                cx = sum(atom_positions[a].x() for a in ring) / len(ring)
                cy = sum(atom_positions[a].y() for a in ring) / len(ring)
                # Inscribed circle radius = ~60% of avg distance to center
                avg_r = sum(
                    math.sqrt((atom_positions[a].x() - cx) ** 2 +
                              (atom_positions[a].y() - cy) ** 2)
                    for a in ring
                ) / len(ring)
                circle_r = avg_r * 0.55
                painter.drawEllipse(QPointF(cx, cy), circle_r, circle_r)
            painter.restore()

        # Draw atoms (skeletal: only show heteroatoms and their H's)
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i, (x, y, atom) in enumerate(coords):
            sym = atom.GetSymbol()
            charge = atom.GetFormalCharge()
            num_h = atom.GetTotalNumHs()
            pt = atom_positions[i]

            # Skip carbon unless it has charge or is terminal
            is_terminal = (atom.GetDegree() <= 1 and sym == "C")
            if sym == "C" and charge == 0 and not is_terminal:
                if highlight_atoms and i in highlight_atoms:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor(255, 200, 200, 100)))
                    painter.drawEllipse(pt, 8, 8)
                continue

            # Background clear for heteroatom labels
            label = sym
            # 헤테로원자 + 말단 탄소에 수소 표시 (CH₃, NH₂ 등)
            if num_h > 0 and (sym != "C" or is_terminal):
                if num_h == 1:
                    label += "H"
                else:
                    label += f"H{_subscript(num_h)}"

            # Charge text
            charge_text = ""
            if charge > 0:
                charge_text = "+" if charge == 1 else f"{charge}+"
            elif charge < 0:
                charge_text = "−" if charge == -1 else f"{abs(charge)}−"

            full_label = label + charge_text

            # Clear background
            tw = fm.horizontalAdvance(full_label) + 4
            th = fm.height() + 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(COLOR_BG))
            painter.drawRect(QRectF(pt.x() - tw / 2, pt.y() - th / 2, tw, th))

            # Draw label
            color = HETEROATOM_COLORS.get(sym, COLOR_BOND)
            painter.setPen(color)
            painter.drawText(
                QRectF(pt.x() - tw / 2, pt.y() - th / 2, tw, th),
                Qt.AlignmentFlag.AlignCenter, full_label
            )

            # Lone pair dots (:) for heteroatoms with lone pairs
            if sym in ("O", "N", "S", "F", "Cl", "Br", "I"):
                try:
                    # Estimate lone pair positions (opposite to bonds)
                    n_lp = 0
                    if sym == "O":
                        n_lp = 2 if atom.GetDegree() <= 2 else 1
                    elif sym == "N":
                        n_lp = 1 if atom.GetDegree() <= 3 else 0
                    elif sym in ("F", "Cl", "Br", "I"):
                        n_lp = 3
                    elif sym == "S":
                        n_lp = 2 if atom.GetDegree() <= 2 else 1

                    if n_lp > 0:
                        # Find average bond direction
                        bond_dirs = []
                        for nb in atom.GetNeighbors():
                            nb_pt = atom_positions.get(nb.GetIdx())
                            if nb_pt:
                                bdx = nb_pt.x() - pt.x()
                                bdy = nb_pt.y() - pt.y()
                                bl = math.sqrt(bdx * bdx + bdy * bdy)
                                if bl > 0:
                                    bond_dirs.append((bdx / bl, bdy / bl))

                        if bond_dirs:
                            avg_bx = sum(d[0] for d in bond_dirs) / len(bond_dirs)
                            avg_by = sum(d[1] for d in bond_dirs) / len(bond_dirs)
                            al = math.sqrt(avg_bx * avg_bx + avg_by * avg_by)
                            if al > 0.1:
                                avg_bx /= al
                                avg_by /= al
                            else:
                                avg_bx, avg_by = 0, -1
                        else:
                            avg_bx, avg_by = 0, -1

                        # Draw dots opposite to bonds
                        dot_dist = 12
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(color))
                        dot_r = 1.5

                        # Primary lone pair (opposite bonds)
                        lp_x = pt.x() - avg_bx * dot_dist
                        lp_y = pt.y() - avg_by * dot_dist
                        # Two dots side by side
                        perp_x = -avg_by * 2.5
                        perp_y = avg_bx * 2.5
                        painter.drawEllipse(QPointF(lp_x + perp_x, lp_y + perp_y), dot_r, dot_r)
                        painter.drawEllipse(QPointF(lp_x - perp_x, lp_y - perp_y), dot_r, dot_r)

                        # Second lone pair (perpendicular) if n_lp >= 2
                        if n_lp >= 2 and len(bond_dirs) == 1:
                            perp2_x = -avg_by * dot_dist
                            perp2_y = avg_bx * dot_dist
                            pp_x = pt.x() + perp2_x
                            pp_y = pt.y() + perp2_y
                            painter.drawEllipse(
                                QPointF(pp_x - avg_bx * 2.5, pp_y - avg_by * 2.5), dot_r, dot_r)
                            painter.drawEllipse(
                                QPointF(pp_x + avg_bx * 2.5, pp_y + avg_by * 2.5), dot_r, dot_r)
                except Exception:
                    pass

            # Highlight
            if highlight_atoms and i in highlight_atoms:
                painter.setPen(QPen(QColor(255, 0, 0, 120), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pt, 12, 12)

        # Atom index labels (debug mode)
        if show_atom_indices:
            painter.setFont(QFont("Arial", 6))
            painter.setPen(QColor(150, 150, 150))
            for i, pt in atom_positions.items():
                painter.drawText(QPointF(pt.x() + 8, pt.y() - 8), str(i))

        return atom_positions


def _subscript(n: int) -> str:
    """Unicode subscript digits"""
    subs = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    return str(n).translate(subs)


# ============================================================================
# CURVED ARROW RENDERER (Textbook Style — Black)
# ============================================================================

class CurvedArrowRenderer:
    """교과서 스타일 곡선 화살표 렌더링

    v2.1 개선:
    - 2-control-point cubic Bezier로 더 자연스러운 S-curve 지원
    - 론페어 출발 시 전자쌍 도트(·:) 렌더링
    - 화살촉 크기/형태를 거리 비례로 적응 조절
    - 짧은 화살표(<30px) 전용 경로: 직선에 가까운 미니 커브
    """

    @staticmethod
    def _calc_control_points(start: QPointF, end: QPointF, curvature: float):
        """시작/끝 좌표와 곡률로 제어점 계산.

        Returns:
            (ctrl, length, dx, dy) — quadratic 제어점 및 메타데이터
        """
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return None, length, dx, dy

        # 곡률: 최소/최대 제한으로 항상 잘 보이는 U자 곡선
        # 짧은 화살표는 bulge를 줄여서 겹침 방지
        if length < 30:
            min_bulge = 8
            max_bulge = 20
        else:
            min_bulge = 18  # 결합선에서 충분히 떨어짐
            max_bulge = 55  # 분자 밖으로 너무 안 나감

        bulge = max(min_bulge, min(abs(curvature) * length, max_bulge))
        sign = 1 if curvature >= 0 else -1
        perp_x = -dy / length * sign * bulge
        perp_y = dx / length * sign * bulge
        ctrl = QPointF(mid.x() + perp_x, mid.y() + perp_y)
        return ctrl, length, dx, dy

    @staticmethod
    def draw_full_arrow(painter: QPainter, start: QPointF, end: QPointF,
                        curvature: float = 0.3, color: QColor = COLOR_ARROW,
                        width: float = 2.0, show_lone_pair: bool = False):
        """2전자 이동 곡선 화살표 (실선, 꽉 찬 화살촉)

        Args:
            show_lone_pair: True이면 시작점에 전자쌍 도트(··) 표시
        """
        painter.save()

        ctrl, length, dx, dy = CurvedArrowRenderer._calc_control_points(
            start, end, curvature)
        if ctrl is None:
            painter.restore()
            return

        # Draw curve — quadratic Bezier
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(ctrl, end)
        painter.drawPath(path)

        # Filled arrowhead — 거리 비례 적응 크기
        arrow_size = max(7, min(12, length * 0.12))
        tx = end.x() - ctrl.x()
        ty = end.y() - ctrl.y()
        tlen = math.sqrt(tx * tx + ty * ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen

        # 교과서 표준: 약간 넓은 삼각형 (0.5 비율)
        half_w = arrow_size * 0.5
        px1 = end.x() - arrow_size * tx + half_w * ty
        py1 = end.y() - arrow_size * ty - half_w * tx
        px2 = end.x() - arrow_size * tx - half_w * ty
        py2 = end.y() - arrow_size * ty + half_w * tx

        arrow_path = QPainterPath()
        arrow_path.moveTo(end)
        arrow_path.lineTo(QPointF(px1, py1))
        arrow_path.lineTo(QPointF(px2, py2))
        arrow_path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(arrow_path)

        # Lone pair dots at tail (선택적)
        if show_lone_pair and length > 15:
            CurvedArrowRenderer._draw_lone_pair_dots(
                painter, start, ctrl, color, width)

        painter.restore()

    @staticmethod
    def draw_half_arrow(painter: QPainter, start: QPointF, end: QPointF,
                        curvature: float = 0.3, color: QColor = COLOR_ARROW,
                        width: float = 1.5, show_lone_pair: bool = False):
        """1전자 이동 피셔훅 화살표 (반쪽 화살촉)

        Args:
            show_lone_pair: True이면 시작점에 단일 전자 도트(·) 표시
        """
        painter.save()

        ctrl, length, dx, dy = CurvedArrowRenderer._calc_control_points(
            start, end, curvature)
        if ctrl is None:
            painter.restore()
            return

        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(ctrl, end)
        painter.drawPath(path)

        # Single barb (fishhook) — 거리 비례 적응 크기
        arrow_size = max(7, min(11, length * 0.11))
        tx = end.x() - ctrl.x()
        ty = end.y() - ctrl.y()
        tlen = math.sqrt(tx * tx + ty * ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen

        bx = end.x() - arrow_size * tx + arrow_size * 0.6 * ty
        by = end.y() - arrow_size * ty - arrow_size * 0.6 * tx

        pen2 = QPen(color, width + 0.3)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawLine(end, QPointF(bx, by))

        # Single electron dot at tail (선택적)
        if show_lone_pair and length > 15:
            CurvedArrowRenderer._draw_single_electron_dot(
                painter, start, ctrl, color)

        painter.restore()

    @staticmethod
    def _draw_lone_pair_dots(painter: QPainter, start: QPointF,
                             ctrl: QPointF, color: QColor, width: float):
        """시작점 뒤에 전자쌍 도트(··) 렌더링 — 론페어 출발 화살표용"""
        # 커브 시작 방향의 반대쪽에 도트 배치
        dx_to_ctrl = ctrl.x() - start.x()
        dy_to_ctrl = ctrl.y() - start.y()
        d = math.sqrt(dx_to_ctrl ** 2 + dy_to_ctrl ** 2)
        if d < 0.1:
            return
        # 커브 방향과 수직으로 도트 배치
        nx = -dy_to_ctrl / d  # 수직 벡터
        ny = dx_to_ctrl / d
        dot_offset = 4.0
        dot_r = max(1.8, width * 0.7)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        # 두 개의 도트
        for sign in (-1, 1):
            cx = start.x() + nx * sign * dot_offset
            cy = start.y() + ny * sign * dot_offset
            painter.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

    @staticmethod
    def _draw_single_electron_dot(painter: QPainter, start: QPointF,
                                  ctrl: QPointF, color: QColor):
        """시작점 뒤에 단일 전자 도트(·) — 라디칼/피셔훅용"""
        dx_to_ctrl = ctrl.x() - start.x()
        dy_to_ctrl = ctrl.y() - start.y()
        d = math.sqrt(dx_to_ctrl ** 2 + dy_to_ctrl ** 2)
        if d < 0.1:
            return
        # 커브 진행 반대 방향으로 3px 뒤에 도트
        bx = start.x() - dx_to_ctrl / d * 3
        by = start.y() - dy_to_ctrl / d * 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(bx, by), 2.0, 2.0)

    @staticmethod
    def draw_step_number(painter: QPainter, start: QPointF, end: QPointF,
                         ctrl: QPointF, step_num: int, color: QColor = COLOR_ARROW):
        """화살표 근처에 단계 번호(①②③...) 표시

        Args:
            ctrl: 베지어 제어점 (커브 정점 부근에 번호 배치)
            step_num: 1-based 단계 번호
        """
        painter.save()

        # 제어점(커브 정점) 방향으로 약간 오프셋하여 화살표와 겹침 방지
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        offset_x = ctrl.x() - mid.x()
        offset_y = ctrl.y() - mid.y()
        od = math.sqrt(offset_x * offset_x + offset_y * offset_y)
        if od > 0.1:
            offset_x = offset_x / od * 14  # 커브 바깥쪽으로 14px
            offset_y = offset_y / od * 14
        else:
            offset_y = -14  # 기본: 위쪽

        # 번호 위치: 제어점에서 커브 바깥 방향
        nx = ctrl.x() + offset_x
        ny = ctrl.y() + offset_y

        # 원형 배경
        radius = 8
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(nx, ny), radius, radius)

        # 테두리
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(nx, ny), radius, radius)

        # 번호 텍스트
        font = QFont("Arial", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(color)
        text_rect = QRectF(nx - radius, ny - radius, radius * 2, radius * 2)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(step_num))

        painter.restore()

    @staticmethod
    def draw_reaction_arrow(painter: QPainter, x1: float, x2: float, y: float,
                            reagents_above: str = "", conditions_below: str = "",
                            double_headed: bool = False):
        """반응 화살표 (직선, 시약/조건 라벨 포함)"""
        painter.save()

        # Main arrow line
        pen = QPen(COLOR_BOND, 1.5)
        painter.setPen(pen)
        mid_y = y

        # Arrow shaft
        painter.drawLine(QPointF(x1, mid_y), QPointF(x2 - 8, mid_y))

        # Arrowhead
        arrow_size = 8
        arrow_path = QPainterPath()
        arrow_path.moveTo(QPointF(x2, mid_y))
        arrow_path.lineTo(QPointF(x2 - arrow_size, mid_y - 4))
        arrow_path.lineTo(QPointF(x2 - arrow_size, mid_y + 4))
        arrow_path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(COLOR_BOND))
        painter.drawPath(arrow_path)

        if double_headed:
            # Reverse arrowhead
            arrow_path2 = QPainterPath()
            arrow_path2.moveTo(QPointF(x1, mid_y))
            arrow_path2.lineTo(QPointF(x1 + arrow_size, mid_y - 4))
            arrow_path2.lineTo(QPointF(x1 + arrow_size, mid_y + 4))
            arrow_path2.closeSubpath()
            painter.drawPath(arrow_path2)

        # Reagent above arrow
        if reagents_above:
            painter.setPen(COLOR_REAGENT)
            painter.setFont(QFont("Arial", 9))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, mid_y - 22, 160, 18),
                Qt.AlignmentFlag.AlignCenter, reagents_above)

        # Conditions below arrow
        if conditions_below:
            painter.setPen(COLOR_LABEL)
            painter.setFont(QFont("Arial", 8))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, mid_y + 5, 160, 16),
                Qt.AlignmentFlag.AlignCenter, conditions_below)

        painter.restore()


# ============================================================================
# REACTION SCHEME WIDGET (Reactants → Products layout)
# ============================================================================

class ReactionSchemeWidget(QWidget):
    """전체 반응 단계를 한 줄 가로로 나열하는 교과서 스타일 반응식 위젯

    Layout:
        [Reactant] ──→ [Intermediate₁] ──→ [Intermediate₂] ──→ [Product]
                   시약              시약              시약
    """

    step_clicked = pyqtSignal(int)  # step index clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mechanism: Optional[MechanismData] = None
        self._current_step: int = 0
        self._molecules = []  # List of (smiles, mol, label)
        self._step_arrows = []  # arrows per step
        self.setMinimumHeight(250)
        self.setMinimumWidth(600)

    def set_mechanism(self, mechanism: MechanismData, current_step: int = 0):
        """전체 메커니즘을 설정 — 모든 단계의 분자를 가로로 나열"""
        self._mechanism = mechanism
        self._current_step = current_step
        self._molecules = []
        self._step_arrows = []

        if not mechanism or not mechanism.steps:
            self.update()
            return

        # Extract unique molecules chain:
        # step1.reactant → step1.product → step2.product → ...
        seen_smiles = []
        for si, step in enumerate(mechanism.steps):
            if si == 0 and step.reactant_smiles:
                seen_smiles.append(step.reactant_smiles)
            if step.product_smiles and step.product_smiles != (seen_smiles[-1] if seen_smiles else ""):
                seen_smiles.append(step.product_smiles)
            self._step_arrows.append(step.arrows if step.arrows else [])

        # Build mol objects
        for smi in seen_smiles:
            mol = None
            if RDKIT_AVAILABLE and smi:
                try:
                    mol = Chem.MolFromSmiles(smi)
                except Exception:
                    pass
            self._molecules.append((smi, mol))

        self.update()

    def set_step(self, step: MechanismStep, mechanism: MechanismData = None):
        """호환성: 기존 코드에서 step 단위 호출 시"""
        if mechanism:
            idx = 0
            for i, s in enumerate(mechanism.steps):
                if s.step_number == step.step_number:
                    idx = i
                    break
            self.set_mechanism(mechanism, idx)
        else:
            self._mechanism = None
            self._molecules = []
            self.update()

    def set_current_step(self, idx: int):
        self._current_step = idx
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, COLOR_BG)

        if not self._mechanism or not self._molecules:
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 11))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "반응 경로를 선택하세요")
            painter.end()
            return

        mech = self._mechanism
        n_mols = len(self._molecules)

        # ── Title bar ──
        painter.setPen(COLOR_BOND)
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        title = f"{mech.title}"
        if self._current_step < len(mech.steps):
            st = mech.steps[self._current_step]
            title += f"  ·  Step {st.step_number}: {st.title}"
        painter.drawText(QRectF(10, 4, w - 20, 20), Qt.AlignmentFlag.AlignLeft, title)

        painter.setPen(QPen(QColor(200, 200, 200), 0.5))
        painter.drawLine(QPointF(10, 26), QPointF(w - 10, 26))

        # ── ㄹ-shape (serpentine) layout calculation ──
        arrow_space = 60  # px for reaction arrow between molecules
        margin_x = 12
        avail_w = w - 2 * margin_x

        # Calculate how many molecules fit per row — 더 넓은 카드
        min_mol_w = 140  # 최소 분자 카드 너비 (겹침 방지)
        items_per_slot = min_mol_w + arrow_space
        mols_per_row = max(2, int((avail_w + arrow_space) / items_per_slot))
        if n_mols <= mols_per_row:
            mols_per_row = n_mols

        n_rows = max(1, math.ceil(n_mols / mols_per_row))
        row_height = max(150, (h - 60) / n_rows)
        mol_w = max(120, (avail_w - arrow_space * (min(mols_per_row, n_mols) - 1)) / min(mols_per_row, n_mols))

        all_positions = []  # atom_positions per molecule
        mol_rects = []      # QRectF per molecule

        # ─── Pre-compute unstable intermediate flags ───
        # 연속된 불안정 중간체들을 하나의 대괄호 그룹으로 묶기 위해 미리 판별
        unstable_flags = []  # True/False per molecule index
        ts_flags = []        # True/False per molecule index
        for mi, (smi, mol_item) in enumerate(self._molecules):
            is_ts = False
            is_unstable = False

            if mi < len(mech.steps) and mech.steps[min(mi, len(mech.steps)-1)].is_transition_state:
                is_ts = True

            if 0 < mi < n_mols - 1:
                if smi and RDKIT_AVAILABLE:
                    try:
                        check_mol = Chem.MolFromSmiles(smi)
                        if check_mol:
                            has_formal_charge = any(
                                a.GetFormalCharge() != 0
                                for a in check_mol.GetAtoms()
                            )
                            has_radical = any(
                                a.GetNumRadicalElectrons() > 0
                                for a in check_mol.GetAtoms()
                            )
                            is_unstable = has_formal_charge or has_radical
                    except Exception:
                        pass

            unstable_flags.append(is_unstable or is_ts)
            ts_flags.append(is_ts)

        # ─── Group consecutive unstable intermediates ───
        # 연속된 불안정 중간체를 하나의 그룹으로 묶음
        # 예: [False, True, True, True, False] → 그룹 (1, 3)
        bracket_groups = []  # [(start_mi, end_mi), ...]
        i = 0
        while i < len(unstable_flags):
            if unstable_flags[i]:
                start = i
                while i < len(unstable_flags) and unstable_flags[i]:
                    i += 1
                bracket_groups.append((start, i - 1))
            else:
                i += 1

        for mi, (smi, mol) in enumerate(self._molecules):
            row = mi // mols_per_row
            col = mi % mols_per_row

            # ㄹ-shape: even rows L→R, odd rows R→L
            if row % 2 == 0:
                x_start = margin_x + col * (mol_w + arrow_space)
            else:
                x_start = margin_x + (mols_per_row - 1 - col) * (mol_w + arrow_space)

            y_start = 28 + row * row_height
            mol_rect = QRectF(x_start, y_start, mol_w, row_height - 20)
            mol_rects.append(mol_rect)

            # Highlight current step molecules
            is_current_reactant = (mi == self._current_step)
            is_current_product = (mi == self._current_step + 1)
            if is_current_reactant or is_current_product:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(220, 235, 255, 60)))
                painter.drawRoundedRect(mol_rect.adjusted(-2, -2, 2, 2), 4, 4)

            # Transition state / intermediate brackets
            # 대괄호 그룹 방식: 그룹의 첫 번째 분자에 [, 마지막 분자에 ] 그림
            for g_start, g_end in bracket_groups:
                if mi == g_start:
                    # 그룹 시작: 왼쪽 대괄호 [ 그리기
                    bracket_pen = QPen(COLOR_TRANSITION, 1.5)
                    painter.setPen(bracket_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    bx1 = mol_rect.left() - 4
                    by1 = mol_rect.top() + 2
                    by2 = mol_rect.bottom() - 8
                    bw = 5
                    painter.drawLine(QPointF(bx1 + bw, by1), QPointF(bx1, by1))
                    painter.drawLine(QPointF(bx1, by1), QPointF(bx1, by2))
                    painter.drawLine(QPointF(bx1, by2), QPointF(bx1 + bw, by2))

                if mi == g_end:
                    # 그룹 끝: 오른쪽 대괄호 ] 그리기
                    bracket_pen = QPen(COLOR_TRANSITION, 1.5)
                    painter.setPen(bracket_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    bx2 = mol_rect.right() + 4
                    by1 = mol_rect.top() + 2
                    by2 = mol_rect.bottom() - 8
                    bw = 5
                    painter.drawLine(QPointF(bx2 - bw, by1), QPointF(bx2, by1))
                    painter.drawLine(QPointF(bx2, by1), QPointF(bx2, by2))
                    painter.drawLine(QPointF(bx2, by2), QPointF(bx2 - bw, by2))

            if mi < len(ts_flags) and ts_flags[mi]:
                # ‡ symbol for transition state
                painter.setFont(QFont("Arial", 10))
                painter.setPen(COLOR_TRANSITION)
                ts_x = mol_rect.right() + 6
                ts_y = mol_rect.top() + 14
                painter.drawText(QPointF(ts_x, ts_y), "\u2021")

            # Render molecule
            if mol:
                positions = TextbookMoleculeRenderer.render(painter, mol, mol_rect, is_product=(mi == n_mols - 1))
            else:
                positions = {}
                painter.setPen(COLOR_BOND)
                painter.setFont(QFont("Consolas", 8))
                painter.drawText(mol_rect, Qt.AlignmentFlag.AlignCenter,
                                 smi[:30] if smi else "?")
            all_positions.append(positions)

        # ── Draw reaction arrows between molecules ──
        for mi in range(n_mols - 1):
            row_curr = mi // mols_per_row
            row_next = (mi + 1) // mols_per_row

            r1 = mol_rects[mi]
            r2 = mol_rects[mi + 1]

            # Get reagents/conditions for this step
            step_idx = min(mi, len(mech.steps) - 1)
            reagents = ""
            conditions = ""
            if step_idx < len(mech.steps):
                s = mech.steps[step_idx]
                reagents = getattr(s, 'reaction_smirks', '') or ''
                # Use mechanism-level reagents for step 0, step title for others
                if mi == 0:
                    reagents = getattr(mech, 'reagents_above', '') or ''
                    conditions = getattr(mech, 'conditions_below', '') or ''
                else:
                    reagents = ""
                    conditions = s.title[:25] if s.title else ""

            if row_curr == row_next:
                # Same row: horizontal arrow
                if row_curr % 2 == 0:
                    ax1 = r1.right() + 4
                    ax2 = r2.left() - 4
                else:
                    ax1 = r1.left() - 4
                    ax2 = r2.right() + 4
                    ax1, ax2 = min(ax1, ax2), max(ax1, ax2)
                ay = r1.top() + r1.height() / 2
                CurvedArrowRenderer.draw_reaction_arrow(
                    painter, ax1, ax2, ay,
                    reagents_above=reagents,
                    conditions_below=conditions)
            else:
                # Different row: vertical connector (ㄹ turn)
                # Draw down-arrow at row end
                if row_curr % 2 == 0:
                    cx = r1.right() + arrow_space / 2
                else:
                    cx = r1.left() - arrow_space / 2
                cy1 = r1.top() + r1.height() / 2
                cy2 = r2.top() + r2.height() / 2

                pen_arr = QPen(COLOR_BOND, 1.5)
                painter.setPen(pen_arr)
                painter.drawLine(QPointF(cx, cy1 + 5), QPointF(cx, cy2 - 8))
                # Arrowhead down
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(COLOR_BOND))
                ap = QPainterPath()
                ap.moveTo(QPointF(cx, cy2 - 3))
                ap.lineTo(QPointF(cx - 4, cy2 - 10))
                ap.lineTo(QPointF(cx + 4, cy2 - 10))
                ap.closeSubpath()
                painter.drawPath(ap)

                # Conditions label on vertical
                if conditions:
                    painter.setPen(COLOR_LABEL)
                    painter.setFont(QFont("Arial", 7))
                    painter.drawText(QPointF(cx + 5, (cy1 + cy2) / 2), conditions[:20])

        # ── Draw mechanism arrows on current step's reactant ──
        if self._current_step < len(self._step_arrows) and self._current_step < len(all_positions):
            arrows = self._step_arrows[self._current_step]
            positions = all_positions[self._current_step]
            mol_rect = mol_rects[self._current_step] if self._current_step < len(mol_rects) else QRectF()
            self._draw_mechanism_arrows(painter, arrows, positions, mol_rect)

        # ── Description at bottom ──
        if self._current_step < len(mech.steps):
            step = mech.steps[self._current_step]
            desc = step.description.replace("\n", " ")
            desc_y = h - 35
            painter.setPen(QColor(80, 80, 80))
            painter.setFont(QFont("Arial", 8))
            max_chars = max(1, (w - 20) // 5)
            if len(desc) > max_chars:
                desc = desc[:max_chars - 3] + "..."
            painter.drawText(QRectF(10, desc_y, w - 20, 16),
                             Qt.AlignmentFlag.AlignLeft, desc)

            if step.energy_label:
                painter.setPen(QColor(180, 80, 0))
                painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                painter.drawText(QRectF(w - 200, desc_y + 14, 190, 14),
                                 Qt.AlignmentFlag.AlignRight, step.energy_label)

        painter.end()

    def _draw_mechanism_arrows(self, painter: QPainter, arrows: List[ArrowData],
                               atom_positions: Dict[int, QPointF], mol_rect: QRectF):
        """메커니즘 화살표 그리기 — 프래그먼트 인식 스마트 배치

        전략:
        1. from_atom_idx/to_atom_idx가 유효하면 그대로 사용
        2. 멀티 프래그먼트 SMILES에서는 프래그먼트 간 화살표 우선
        3. from_type/to_type + 원자 속성 기반 자동 배치
        """
        if not arrows or not atom_positions:
            return

        # Reorder arrows to form electron flow chain (Nu→C→LG)
        arrows = self._order_arrow_chain(arrows)

        # Get molecule info if available
        mol = None
        frag_map = {}  # atom_idx → fragment_idx
        frag_atoms = []  # list of sets of atom indices per fragment
        step_idx = self._current_step
        if (self._mechanism and step_idx < len(self._mechanism.steps)
                and RDKIT_AVAILABLE):
            smi = self._mechanism.steps[step_idx].reactant_smiles
            if smi:
                try:
                    mol = Chem.MolFromSmiles(smi)
                    if mol:
                        frags = Chem.GetMolFrags(mol, asMols=False)
                        for fi, fatoms in enumerate(frags):
                            frag_atoms.append(set(fatoms))
                            for a in fatoms:
                                frag_map[a] = fi
                except Exception:
                    pass

        # Pre-classify atoms for smart placement (per-fragment)
        heteroatoms = []
        charged_neg = []
        charged_pos = []
        carbons = []
        pi_bond_atoms = []

        if mol:
            for atom in mol.GetAtoms():
                idx = atom.GetIdx()
                if idx not in atom_positions:
                    continue
                sym = atom.GetSymbol()
                charge = atom.GetFormalCharge()

                if sym in ("O", "N", "S", "F", "Cl", "Br", "I"):
                    heteroatoms.append(idx)
                if charge < 0:
                    charged_neg.append(idx)
                if charge > 0:
                    charged_pos.append(idx)
                if sym == "C":
                    carbons.append(idx)

            for bond in mol.GetBonds():
                if bond.GetBondTypeAsDouble() >= 2.0:
                    pi_bond_atoms.append(bond.GetBeginAtomIdx())
                    pi_bond_atoms.append(bond.GetEndAtomIdx())

        all_idxs = sorted(atom_positions.keys())

        for i, arrow in enumerate(arrows):
            from_idx = getattr(arrow, 'from_atom_idx', -1)
            to_idx = getattr(arrow, 'to_atom_idx', -1)

            # ── Smart auto-detect if indices not specified ──
            if from_idx < 0 or from_idx not in atom_positions:
                from_idx = self._auto_find_atom(
                    arrow.from_type, heteroatoms, charged_neg, charged_pos,
                    carbons, pi_bond_atoms, all_idxs, i, used_as="from",
                    frag_map=frag_map, frag_atoms=frag_atoms)

            if to_idx < 0 or to_idx not in atom_positions:
                # 다른 프래그먼트 원자 우선
                from_frag = frag_map.get(from_idx, -1)
                to_idx = self._auto_find_atom(
                    arrow.to_type, heteroatoms, charged_neg, charged_pos,
                    carbons, pi_bond_atoms, all_idxs, i, used_as="to",
                    exclude=from_idx, prefer_other_frag=from_frag,
                    frag_map=frag_map, frag_atoms=frag_atoms)

            if from_idx not in atom_positions or to_idx not in atom_positions:
                continue

            if from_idx == to_idx:
                continue

            start = QPointF(atom_positions[from_idx])
            end = QPointF(atom_positions[to_idx])

            # ── from_type에 따른 시작점 결정 ──
            # "bond" / "pi_bond": 결합의 중점에서 시작 (결합이 끊어지는 것)
            # "lone_pair": 론페어 위치에서 시작
            # "negative_charge": 음전하 위치에서 시작

            if arrow.from_type in ("bond", "pi_bond"):
                # 결합 끊김 화살표: 반드시 결합 중점에서 시작해야 함
                # (교과서 관례: 결합 위의 전자쌍이 이동하는 것을 명확히 표현)
                if mol:
                    atom_obj = mol.GetAtomWithIdx(from_idx)
                    best_mid = None
                    best_dist_to_target = float('inf')
                    # 1순위: from_idx와 직접 결합된 원자 중 to_idx 방향 결합
                    for nb in atom_obj.GetNeighbors():
                        nb_idx = nb.GetIdx()
                        if nb_idx in atom_positions:
                            nb_pt = atom_positions[nb_idx]
                            mid = QPointF((start.x() + nb_pt.x()) / 2,
                                          (start.y() + nb_pt.y()) / 2)
                            if nb_idx == to_idx:
                                best_mid = mid
                                break
                            d = math.sqrt((mid.x() - end.x()) ** 2
                                          + (mid.y() - end.y()) ** 2)
                            if d < best_dist_to_target:
                                best_dist_to_target = d
                                best_mid = mid
                    if best_mid:
                        start = best_mid
                    else:
                        # mol에서 이웃을 못 찾은 경우 — from/to 중점 폴백
                        start = QPointF((start.x() + end.x()) / 2,
                                        (start.y() + end.y()) / 2)
                else:
                    # RDKit 없이도 결합 중점에서 시작 (from↔to 중점 근사)
                    start = QPointF((start.x() + end.x()) / 2,
                                    (start.y() + end.y()) / 2)

            elif arrow.from_type == "lone_pair" and mol:
                atom_obj = mol.GetAtomWithIdx(from_idx)
                nb_pts = [atom_positions.get(nb.GetIdx()) for nb in atom_obj.GetNeighbors()
                          if nb.GetIdx() in atom_positions]
                if nb_pts:
                    avg_bx = sum(p.x() - start.x() for p in nb_pts) / len(nb_pts)
                    avg_by = sum(p.y() - start.y() for p in nb_pts) / len(nb_pts)
                    bl = math.sqrt(avg_bx * avg_bx + avg_by * avg_by)
                    if bl > 0.1:
                        start = QPointF(start.x() - avg_bx / bl * 12,
                                        start.y() - avg_by / bl * 12)
                else:
                    # 프래그먼트에 원자 1개 (단일 이온)
                    dx_tmp = end.x() - start.x()
                    dy_tmp = end.y() - start.y()
                    d_tmp = math.sqrt(dx_tmp * dx_tmp + dy_tmp * dy_tmp)
                    if d_tmp > 0:
                        # 타겟 반대 방향에 론페어
                        start = QPointF(start.x() - dx_tmp / d_tmp * 10,
                                        start.y() - dy_tmp / d_tmp * 10)

            elif arrow.from_type == "negative_charge":
                start = QPointF(start.x(), start.y() - 8)

            # ── to_type == "bond"이면 끝점도 결합 중점으로 이동 ──
            if arrow.to_type in ("bond",) and mol:
                to_atom_obj = mol.GetAtomWithIdx(to_idx)
                best_mid = None
                best_dist_from_start = float('inf')
                for nb in to_atom_obj.GetNeighbors():
                    nb_idx = nb.GetIdx()
                    if nb_idx in atom_positions:
                        nb_pt = atom_positions[nb_idx]
                        mid = QPointF((end.x() + nb_pt.x()) / 2,
                                      (end.y() + nb_pt.y()) / 2)
                        if nb_idx == from_idx:
                            best_mid = mid
                            break
                        d = math.sqrt((mid.x() - start.x()) ** 2 + (mid.y() - start.y()) ** 2)
                        if d < best_dist_from_start:
                            best_dist_from_start = d
                            best_mid = mid
                if best_mid:
                    end = best_mid

            dx = end.x() - start.x()
            dy = end.y() - start.y()
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 3:
                continue

            # 끝점: 원자 라벨과 겹치지 않게 축소 (결합 중점이면 덜 축소)
            shrink = 5 if arrow.to_type in ("bond",) else 8
            end = QPointF(end.x() - dx / dist * shrink, end.y() - dy / dist * shrink)
            # 시작점도 약간 축소 (from_type이 bond이면 이미 중점이므로 축소 불필요)
            if arrow.from_type not in ("bond", "pi_bond"):
                s_dx = end.x() - start.x()
                s_dy = end.y() - start.y()
                s_dist = math.sqrt(s_dx * s_dx + s_dy * s_dy)
                if s_dist > 15:
                    start = QPointF(start.x() + s_dx / s_dist * 4,
                                    start.y() + s_dy / s_dist * 4)

            curv = arrow.curvature if hasattr(arrow, 'curvature') else 0.25
            # 같은 프래그먼트 내 화살표는 곡률 더 높게
            from_frag = frag_map.get(from_idx, -1)
            to_frag = frag_map.get(to_idx, -1)
            if from_frag == to_frag and from_frag >= 0:
                curv = max(curv, 0.35)
            # 방향 번갈아
            if i % 2 == 1:
                curv = -curv

            # 화살표 색상: 데이터에 #000000(기본값)이면 교과서 빨간색 사용
            raw_color = getattr(arrow, 'color', '#000000')
            if raw_color in ('#000000', '#000', 'black', ''):
                color = COLOR_ARROW  # 빨간 교과서 스타일
            else:
                color = QColor(raw_color)

            # 론페어/음전하 출발 화살표에 전자쌍 도트 표시
            is_lone_pair_origin = arrow.from_type in (
                "lone_pair", "negative_charge")

            if arrow.arrow_type == "full":
                CurvedArrowRenderer.draw_full_arrow(
                    painter, start, end, curvature=curv, color=color,
                    show_lone_pair=is_lone_pair_origin)
            else:
                CurvedArrowRenderer.draw_half_arrow(
                    painter, start, end, curvature=curv, color=color,
                    show_lone_pair=is_lone_pair_origin)

            # 단계 번호 표시 (여러 화살표일 때 전자 흐름 순서 명확화)
            if len(arrows) > 1:
                ctrl_for_num, _, _, _ = CurvedArrowRenderer._calc_control_points(
                    start, end, curv)
                if ctrl_for_num is not None:
                    CurvedArrowRenderer.draw_step_number(
                        painter, start, end, ctrl_for_num,
                        step_num=i + 1, color=color)

    def _order_arrow_chain(self, arrows: List[ArrowData]) -> List[ArrowData]:
        """전자 흐름 체인 순서로 화살표 정렬: tail→head 연결"""
        if len(arrows) <= 1:
            return list(arrows)

        # Build adjacency: arrow whose to_atom connects to another arrow's from_atom
        ordered = []
        remaining = list(arrows)

        # Find chain start: arrow whose from_atom is NOT any other arrow's to_atom
        to_atoms = {getattr(a, 'to_atom_idx', -1) for a in remaining}
        starts = [a for a in remaining if getattr(a, 'from_atom_idx', -1) not in to_atoms]

        if starts:
            current = starts[0]
        else:
            current = remaining[0]

        ordered.append(current)
        remaining.remove(current)

        # Chain forward: current.to → next.from
        while remaining:
            cur_to = getattr(current, 'to_atom_idx', -1)
            found = None
            for a in remaining:
                if getattr(a, 'from_atom_idx', -1) == cur_to:
                    found = a
                    break
            if found:
                ordered.append(found)
                remaining.remove(found)
                current = found
            else:
                # No chain connection, just append remaining
                ordered.extend(remaining)
                break

        return ordered

    @staticmethod
    def _auto_find_atom(type_hint: str, heteroatoms, charged_neg, charged_pos,
                        carbons, pi_bond_atoms, all_idxs, arrow_idx,
                        used_as="from", exclude=-1,
                        prefer_other_frag=-1, frag_map=None, frag_atoms=None):
        """from_type/to_type + 프래그먼트 인식 원자 자동 선택

        prefer_other_frag: 이 프래그먼트가 아닌 다른 프래그먼트의 원자 우선 선택
        """
        if frag_map is None:
            frag_map = {}
        if frag_atoms is None:
            frag_atoms = []

        candidates = []

        if used_as == "from":
            if type_hint == "lone_pair":
                candidates = heteroatoms
            elif type_hint == "negative_charge":
                candidates = charged_neg if charged_neg else heteroatoms
            elif type_hint == "pi_bond":
                candidates = pi_bond_atoms
            elif type_hint == "bond":
                candidates = pi_bond_atoms if pi_bond_atoms else carbons
            else:
                candidates = heteroatoms if heteroatoms else all_idxs
        else:
            # Arrow ends at electron-poor target
            if type_hint == "atom":
                candidates = carbons if carbons else all_idxs
            elif type_hint == "bond":
                candidates = pi_bond_atoms if pi_bond_atoms else carbons
            elif type_hint == "antibonding":
                candidates = carbons
            else:
                candidates = carbons if carbons else all_idxs

        # Filter out excluded
        candidates = [c for c in candidates if c != exclude]

        if not candidates:
            candidates = [c for c in all_idxs if c != exclude]

        if not candidates:
            return -1

        # ── 프래그먼트 우선 로직 ──
        # prefer_other_frag >= 0이면 해당 프래그먼트가 아닌 원자를 우선
        if prefer_other_frag >= 0 and frag_map:
            other_frag_candidates = [c for c in candidates
                                     if frag_map.get(c, -1) != prefer_other_frag]
            if other_frag_candidates:
                candidates = other_frag_candidates

        # Pick based on arrow index to spread arrows across different atoms
        return candidates[arrow_idx % len(candidates)]


# ============================================================================
# ENERGY DIAGRAM WIDGET (Textbook Style)
# ============================================================================

class EnergyDiagramWidget(QWidget):
    """반응 에너지 다이어그램 — 교과서 스타일 곡선 + 활성화 에너지 표시"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []
        self.setMinimumHeight(120)
        self.setMaximumHeight(200)

    def set_data(self, energy_diagram: List[Tuple[str, float]]):
        self._data = energy_diagram
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, COLOR_BG)

        if not self._data:
            painter.end()
            return

        energies = [e for _, e in self._data]
        e_min, e_max = min(energies), max(energies)
        e_range = (e_max - e_min) or 1

        margin_x, margin_y = 60, 28
        plot_w = w - 2 * margin_x
        plot_h = h - 2 * margin_y

        n = len(self._data)
        points = []
        for i, (label, energy) in enumerate(self._data):
            x = margin_x + plot_w * i / max(n - 1, 1)
            y = margin_y + plot_h * (1 - (energy - e_min) / e_range)
            points.append((x, y, label, energy))

        # ── 곡선 에너지 경로 (스플라인) ──
        if len(points) >= 2:
            # Catmull-Rom 스플라인으로 부드러운 곡선
            curve_path = QPainterPath()
            curve_path.moveTo(QPointF(points[0][0], points[0][1]))

            if len(points) == 2:
                curve_path.lineTo(QPointF(points[1][0], points[1][1]))
            else:
                for i in range(len(points) - 1):
                    p0 = points[max(0, i - 1)]
                    p1 = points[i]
                    p2 = points[min(len(points) - 1, i + 1)]
                    p3 = points[min(len(points) - 1, i + 2)]

                    # Control points from Catmull-Rom → Cubic Bezier
                    cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
                    cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
                    cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
                    cp2y = p2[1] - (p3[1] - p1[1]) / 6.0

                    curve_path.cubicTo(
                        QPointF(cp1x, cp1y),
                        QPointF(cp2x, cp2y),
                        QPointF(p2[0], p2[1])
                    )

            # 곡선 아래 영역 채우기 (연한 파란색)
            fill_path = QPainterPath(curve_path)
            fill_path.lineTo(QPointF(points[-1][0], margin_y + plot_h))
            fill_path.lineTo(QPointF(points[0][0], margin_y + plot_h))
            fill_path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(200, 220, 255, 40)))
            painter.drawPath(fill_path)

            # 곡선 그리기
            pen = QPen(COLOR_ENERGY_LINE, 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(curve_path)

        # ── 활성화 에너지 표시 (Ea 화살표) ──
        if len(points) >= 3:
            # 반응물 = 첫 번째 점, 첫 번째 전이 상태 = 가장 높은 점
            reactant_e = points[0][3]
            product_e = points[-1][3]
            # 가장 높은 에너지 점 찾기 (전이 상태)
            ts_idx = max(range(len(points)), key=lambda k: points[k][3])
            ts_e = points[ts_idx][3]

            if ts_e > reactant_e:
                # Ea 화살표: 반응물 높이 → 전이 상태 높이
                ea_x = points[ts_idx][0] + 20
                ea_y_top = points[ts_idx][1]
                ea_y_bot = margin_y + plot_h * (1 - (reactant_e - e_min) / e_range)

                # 점선 수평선 (반응물 에너지 수준)
                pen_dash = QPen(QColor(180, 180, 180), 0.8, Qt.PenStyle.DashLine)
                painter.setPen(pen_dash)
                painter.drawLine(QPointF(points[0][0], ea_y_bot),
                                 QPointF(ea_x + 5, ea_y_bot))

                # Ea 양방향 화살표
                painter.setPen(QPen(QColor(200, 50, 50), 1.2))
                painter.drawLine(QPointF(ea_x, ea_y_bot - 2), QPointF(ea_x, ea_y_top + 2))
                # 위쪽 화살촉
                painter.drawLine(QPointF(ea_x, ea_y_top + 2),
                                 QPointF(ea_x - 3, ea_y_top + 7))
                painter.drawLine(QPointF(ea_x, ea_y_top + 2),
                                 QPointF(ea_x + 3, ea_y_top + 7))
                # 아래쪽 화살촉
                painter.drawLine(QPointF(ea_x, ea_y_bot - 2),
                                 QPointF(ea_x - 3, ea_y_bot - 7))
                painter.drawLine(QPointF(ea_x, ea_y_bot - 2),
                                 QPointF(ea_x + 3, ea_y_bot - 7))

                # Ea 라벨
                ea_val = ts_e - reactant_e
                painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
                painter.setPen(QColor(200, 50, 50))
                ea_label_y = (ea_y_top + ea_y_bot) / 2
                painter.drawText(QRectF(ea_x + 4, ea_label_y - 7, 60, 14),
                                 Qt.AlignmentFlag.AlignLeft,
                                 f"Ea={ea_val:.0f}")

            # ΔH 표시 (반응물 vs 생성물)
            delta_h = product_e - reactant_e
            if abs(delta_h) > 0.5:
                dh_x = points[-1][0] + 15
                dh_y_r = margin_y + plot_h * (1 - (reactant_e - e_min) / e_range)
                dh_y_p = points[-1][1]

                # ΔH 화살표
                painter.setPen(QPen(QColor(50, 120, 50), 1.0))
                painter.drawLine(QPointF(dh_x, dh_y_r), QPointF(dh_x, dh_y_p))
                if delta_h < 0:
                    painter.drawLine(QPointF(dh_x, dh_y_p),
                                     QPointF(dh_x - 3, dh_y_p + 5))
                    painter.drawLine(QPointF(dh_x, dh_y_p),
                                     QPointF(dh_x + 3, dh_y_p + 5))
                else:
                    painter.drawLine(QPointF(dh_x, dh_y_p),
                                     QPointF(dh_x - 3, dh_y_p - 5))
                    painter.drawLine(QPointF(dh_x, dh_y_p),
                                     QPointF(dh_x + 3, dh_y_p - 5))

                painter.setFont(QFont("Arial", 7))
                painter.setPen(QColor(50, 120, 50))
                sign = "+" if delta_h > 0 else ""
                dh_label_y = (dh_y_r + dh_y_p) / 2
                painter.drawText(QRectF(dh_x + 3, dh_label_y - 7, 60, 14),
                                 Qt.AlignmentFlag.AlignLeft,
                                 f"ΔH={sign}{delta_h:.0f}")

        # ── 점 및 라벨 ──
        font = QFont("Arial", 7)
        painter.setFont(font)
        for i, (x, y, label, energy) in enumerate(points):
            # 점
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(COLOR_ENERGY_PT))
            painter.drawEllipse(QPointF(x, y), 3.5, 3.5)

            # 라벨 (위쪽에 표시)
            painter.setPen(COLOR_LABEL)
            label_lines = label.split("\n")
            ly = y - 12
            for line in label_lines:
                painter.drawText(QRectF(x - 50, ly, 100, 11),
                                 Qt.AlignmentFlag.AlignCenter, line)
                ly -= 11

        # Y축 라벨
        painter.setPen(QColor(120, 120, 120))
        painter.setFont(QFont("Arial", 7))
        painter.save()
        painter.translate(14, h / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-35, -8, 70, 16),
                         Qt.AlignmentFlag.AlignCenter, "에너지 (E)")
        painter.restore()

        # X축 라벨
        painter.drawText(QRectF(w / 2 - 40, h - 14, 80, 14),
                         Qt.AlignmentFlag.AlignCenter, "반응 좌표")

        # Y축 선
        painter.setPen(QPen(QColor(180, 180, 180), 0.5))
        painter.drawLine(QPointF(margin_x - 5, margin_y),
                         QPointF(margin_x - 5, margin_y + plot_h))
        # X축 선
        painter.drawLine(QPointF(margin_x - 5, margin_y + plot_h),
                         QPointF(margin_x + plot_w + 5, margin_y + plot_h))

        painter.end()


# ============================================================================
# MOLECULE CARD WIDGET (Textbook style, white bg)
# ============================================================================

class MoleculeCardWidget(QWidget):
    """분자 카드 — 흰 배경 교과서 스타일"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smiles = ""
        self._name = ""
        self._mol = None
        self._border_color = QColor(0, 0, 0)
        self.setMinimumSize(180, 130)
        self.setMaximumHeight(160)

    def set_molecule(self, smiles: str, name: str = "", border_color: QColor = None):
        self._smiles = smiles
        self._name = name
        self._border_color = border_color or QColor(0, 0, 0)
        if RDKIT_AVAILABLE and smiles:
            self._mol = Chem.MolFromSmiles(smiles)
        else:
            self._mol = None
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, COLOR_BG)

        # Border
        painter.setPen(QPen(self._border_color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 4, 4)

        if self._mol:
            mol_rect = QRectF(5, 5, w - 10, h - 30)
            TextbookMoleculeRenderer.render(painter, self._mol, mol_rect)
        else:
            painter.setPen(QColor(100, 100, 100))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(QRectF(5, 5, w - 10, h - 30),
                             Qt.AlignmentFlag.AlignCenter,
                             self._smiles or "분자 없음")

        # Name label
        if self._name:
            painter.setPen(COLOR_LABEL)
            painter.setFont(QFont("Arial", 8))
            painter.drawText(QRectF(5, h - 22, w - 10, 18),
                             Qt.AlignmentFlag.AlignCenter, self._name)

        painter.end()


# ============================================================================
# MAIN REACTION POPUP
# ============================================================================

class ReactionPopup(QDialog):
    """유기합성반응 분석 팝업 — 교과서 스타일"""

    def __init__(self, smiles_list: List[str], names: List[str] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("유기합성반응 분석")
        self.setMinimumSize(1000, 750)
        self.resize(1100, 800)
        self.setStyleSheet("""
            QDialog { background: #FFFFFF; color: #222; }
            QGroupBox {
                border: 1px solid #ccc; border-radius: 4px;
                margin-top: 8px; padding-top: 14px; color: #333;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }
            QListWidget {
                background: #FAFAFA; color: #222; border: 1px solid #ccc;
                font-size: 10pt;
            }
            QListWidget::item:selected { background: #D0E4FF; color: #000; }
            QListWidget::item:hover { background: #EEF4FF; }
            QTextEdit {
                background: #FAFAFA; color: #333; border: 1px solid #ccc;
                font-size: 9pt;
            }
            QPushButton {
                background: #F0F0F0; color: #222; border: 1px solid #bbb;
                padding: 4px 12px; border-radius: 3px;
            }
            QPushButton:hover { background: #E0E0E0; }
            QPushButton:disabled { color: #aaa; }
            QLabel { color: #333; }
            QComboBox {
                background: #FAFAFA; border: 1px solid #ccc;
                padding: 3px 8px; color: #222;
            }
        """)

        self._smiles = smiles_list[:4]
        self._names = names or [f"분자 {chr(65 + i)}" for i in range(len(self._smiles))]
        self._predictor = ReactionPredictor()
        self._pathways: List[ReactionPathway] = []
        self._current_mechanism: Optional[MechanismData] = None
        self._current_step_idx = 0

        self._init_ui()
        self._run_prediction()

    def _init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(6, 6, 6, 6)

        # ═══ 왼쪽: 반응 경로 목록 (좁게) ═══
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(4, 4, 4, 4)

        # 입력 분자 카드 (작게)
        header = QLabel("반응물")
        header.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        left_layout.addWidget(header)

        COLORS = [QColor("#E53935"), QColor("#1565C0"),
                  QColor("#2E7D32"), QColor("#F57F17")]
        self._mol_widgets = []
        for i, smiles in enumerate(self._smiles):
            mw = MoleculeCardWidget()
            color = COLORS[i % len(COLORS)]
            mw.set_molecule(smiles, self._names[i], border_color=color)
            mw.setMaximumHeight(80)
            self._mol_widgets.append(mw)
            left_layout.addWidget(mw)

        # 반응 경로 목록
        rp_header = QLabel("반응 경로")
        rp_header.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        left_layout.addWidget(rp_header)

        self.reaction_list = QListWidget()
        self.reaction_list.currentRowChanged.connect(self._on_reaction_selected)
        left_layout.addWidget(self.reaction_list)

        self.reaction_info = QTextEdit()
        self.reaction_info.setReadOnly(True)
        self.reaction_info.setMaximumHeight(100)
        self.reaction_info.setPlaceholderText("반응을 선택하세요")
        left_layout.addWidget(self.reaction_info)

        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(240)

        # ═══ 오른쪽: 메커니즘 시각화 (넓게) ═══
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(4, 4, 4, 4)

        # Step navigation bar
        nav_bar = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 이전")
        self.btn_prev.clicked.connect(self._prev_step)
        self.btn_prev.setEnabled(False)
        self.btn_prev.setMaximumWidth(80)
        nav_bar.addWidget(self.btn_prev)

        self.step_label = QLabel("반응을 선택하세요")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        nav_bar.addWidget(self.step_label)

        self.btn_next = QPushButton("다음 ▶")
        self.btn_next.clicked.connect(self._next_step)
        self.btn_next.setEnabled(False)
        self.btn_next.setMaximumWidth(80)
        nav_bar.addWidget(self.btn_next)

        right_layout.addLayout(nav_bar)

        # Reaction scheme (textbook style, horizontal layout)
        self.scheme_widget = ReactionSchemeWidget()
        self.scheme_widget.setMinimumHeight(300)
        right_layout.addWidget(self.scheme_widget, stretch=3)

        # Energy diagram
        self.energy_widget = EnergyDiagramWidget()
        right_layout.addWidget(self.energy_widget, stretch=1)

        # Overall description
        self.overall_desc = QLabel("")
        self.overall_desc.setWordWrap(True)
        self.overall_desc.setStyleSheet(
            "color: #555; font-size: 9pt; padding: 4px; "
            "border-top: 1px solid #ddd;")
        right_layout.addWidget(self.overall_desc)

        right_panel.setLayout(right_layout)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, stretch=1)

        self.setLayout(main_layout)

    def _run_prediction(self):
        """반응 예측 실행"""
        if len(self._smiles) < 2:
            self.reaction_list.addItem("2개 이상의 분자가 필요합니다")
            return

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
            self.reaction_list.addItem("감지된 반응 경로가 없습니다")
            self.reaction_list.addItem("  작용기를 포함한 분자를 그려보세요")
            return

        for pw in self._pathways:
            conf_pct = int(pw.confidence * 100)
            item = QListWidgetItem(f"[{pw.category}] {pw.name}  ({conf_pct}%)")
            self.reaction_list.addItem(item)

    def _on_reaction_selected(self, row):
        """반응 경로 선택"""
        if row < 0 or row >= len(self._pathways):
            return

        pw = self._pathways[row]

        summary = self._predictor.get_reaction_summary(pw)
        self.reaction_info.setPlainText(summary)

        mech = get_mechanism(pw.mechanism_type)

        # Gold standard 없으면 → 범용 엔진으로 자동 생성 시도
        if mech is None and pw.product_smiles:
            try:
                from mechanism_engine import MechanismEngine
                engine = MechanismEngine()
                reactant_combined = ".".join(s for s in self._smiles if s)
                mech = engine.generate_mechanism(
                    reactant_smiles=reactant_combined,
                    product_smiles=pw.product_smiles,
                    mechanism_type_hint=pw.mechanism_type,
                )
                if mech:
                    logger.info(f"범용 엔진으로 메커니즘 자동 생성: {pw.mechanism_type}")
            except Exception as e:
                logger.warning(f"범용 메커니즘 엔진 오류: {e}")

        if mech:
            self._current_mechanism = mech
            self._current_step_idx = 0
            # 전체 메커니즘을 한 번에 전달 (가로 레이아웃)
            self.scheme_widget.set_mechanism(mech, 0)
            self._update_nav()
            self.energy_widget.set_data(mech.energy_diagram)
            self.overall_desc.setText(mech.overall_description)
        else:
            self._current_mechanism = None
            self.step_label.setText(f"메커니즘 데이터 없음 ({pw.mechanism_type})")
            self.scheme_widget.set_mechanism(None)
            self.energy_widget.set_data([])
            self.overall_desc.setText(pw.description)

    def _update_nav(self):
        """Step 네비게이션 업데이트"""
        if not self._current_mechanism:
            return
        mech = self._current_mechanism
        idx = self._current_step_idx
        total = mech.total_steps

        self.step_label.setText(f"Step {idx + 1} / {total}  —  {mech.title}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < total - 1)

    def _update_mechanism_display(self):
        if not self._current_mechanism:
            return
        idx = self._current_step_idx
        self.scheme_widget.set_current_step(idx)
        self._update_nav()

    def _prev_step(self):
        if self._current_step_idx > 0:
            self._current_step_idx -= 1
            self._update_mechanism_display()

    def _next_step(self):
        if (self._current_mechanism and
                self._current_step_idx < self._current_mechanism.total_steps - 1):
            self._current_step_idx += 1
            self._update_mechanism_display()
