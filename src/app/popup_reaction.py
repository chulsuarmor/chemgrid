# popup_reaction.py (v2.0 - Textbook-Style Organic Reaction Mechanism Popup)
"""
ChemGrid: 유기합성반응 분석 팝업 — 교과서 스타일
- 흰 배경 + 검은 화살표 (유기화학 전공서 스타일)
- Atom-mapped 곡선 화살표 (실제 원자 좌표 기반)
- 반응식 레이아웃: Reactants → [Intermediate] → Products
- 시약/조건 라벨 (화살표 위/아래)
"""

import math
import os
import logging
from typing import List, Optional, Dict, Tuple

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QTextEdit, QSlider, QFrame, QScrollArea,
    QApplication, QSizePolicy, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QThread, pyqtSignal, QSizeF

# [M816 D-M804-B12] Headless guard pattern (skill synthesis_timeout.md §8 AI-TIMEOUT-HEADLESS-001)
# audit/test 환경에서 QT_QPA_PLATFORM=offscreen 시 외부 AI 호출 자동 skip
_HEADLESS_MODE = os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath,
    QLinearGradient, QRadialGradient, QPaintEvent, QFontMetrics,
    QFontDatabase
)

logger = logging.getLogger(__name__)


def _ensure_korean_font_loaded() -> str:
    """Load a real Korean font for Qt offscreen captures before any QPainter text."""
    for font_path in (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"):
        try:
            if os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        return families[0]
        except Exception as exc:
            logger.warning("[M854] Korean font load failed: %s (%s)", font_path, exc)
    return "Malgun Gothic"


_KOREAN_FONT_FAMILY = "Malgun Gothic"
_KOREAN_FONT_READY = False


def _ensure_korean_font_ready() -> str:
    """Make Korean text render in direct widget grabs as well as full popups."""
    global _KOREAN_FONT_FAMILY, _KOREAN_FONT_READY
    if _KOREAN_FONT_READY:
        return _KOREAN_FONT_FAMILY
    if QApplication.instance() is None:
        return _KOREAN_FONT_FAMILY
    _KOREAN_FONT_FAMILY = _ensure_korean_font_loaded()
    QApplication.instance().setFont(QFont(_KOREAN_FONT_FAMILY, 10))
    _KOREAN_FONT_READY = True
    return _KOREAN_FONT_FAMILY

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from reaction_predictor import ReactionPredictor, ReactionPathway, FunctionalGroup
from reaction_mechanisms import (
    get_mechanism, MechanismData, MechanismStep, ArrowData,
    compute_mechanism_energies, resolve_atom_map_indices,
)

# ============================================================================
# TEXTBOOK COLORS
# ============================================================================
COLOR_BG = QColor(255, 255, 255)          # 흰 배경
COLOR_BOND = QColor(0, 0, 0)             # 검은 결합선
COLOR_ARROW = QColor(0, 0, 0)            # 검은 곡선 화살표 (유기화학 교과서 표준)
COLOR_ARROW_RADICAL = QColor(0, 0, 0)    # 검은 피셔훅
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
               is_product: bool = False,
               mechanism_mode: bool = False,
               mechanism_type: str = "ionic") -> Dict[int, QPointF]:  # DEFECT-2: mechanism_type으로 페리사이클릭 분류 비활성
        """분자를 골격식으로 렌더링하고 각 원자의 화면 좌표를 반환

        멀티 프래그먼트 SMILES (A.B 형태)는 각 프래그먼트를 분리 렌더링하고
        사이에 '+' 기호를 표시합니다.

        mechanism_mode=True이면 프래그먼트 간 간격 확대 + 분류 라벨 + 배경 틴팅

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

        # ── 프래그먼트 분류 (mechanism_mode) ──
        frag_classifications = []
        if n_frags > 1 and mechanism_mode:
            frag_classifications = TextbookMoleculeRenderer._classify_fragments(
                mol, frags, mechanism_type=mechanism_type)  # DEFECT-2: 페리사이클릭 시 분류 비활성

        # ── 프래그먼트별 좌표 분리 & 재배치 ──
        frag_data = []
        if n_frags > 1:
            # 각 프래그먼트의 bounding box 계산 후 가로로 재배치
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
            # mechanism_mode: 7.0 단위 (~85px) 넓은 간격으로 프래그먼트 시각적 분리
            # non-mechanism: 5.0 단위 — 프래그먼트가 겹치지 않도록 충분한 간격
            if mechanism_mode and mechanism_type == "br2_anti_addition":
                # Br2 addition uses tiny fragments; the generic 7.2-unit gap
                # shrinks arrows and hides backside attack details.
                gap = 4.4
                plus_gap = 1.0
            else:
                gap = 7.2 if mechanism_mode else 5.0  # RDKit units; enough separation without shrinking the alkene panel
                plus_gap = 2.0 if mechanism_mode else 1.5  # '+' 기호용 추가 공간

            # Mechanism mode: keep chemically meaningful fragment order.
            if mechanism_mode and frag_classifications:
                if mechanism_type in {
                    "electrophilic_addition",
                    "br2_anti_addition",
                    "acid_hydration",
                    "norbornene_addition",
                    "oxymercuration_reduction",
                }:
                    # M859: electrophilic addition must read left-to-right as
                    # alkene substrate -> electrophile/acid -> nucleophile.
                    order_map = {'substrate': 0, 'reagent': 1, 'nucleophile': 2, 'leaving_group': 3}
                else:
                    # Substitution/elimination convention: nucleophile/base
                    # approaches the substrate, then leaving group exits.
                    order_map = {'nucleophile': 0, 'reagent': 1, 'substrate': 2, 'leaving_group': 3}
                indexed = list(enumerate(frag_classifications))
                # Rule N: isinstance guard for order_map
                if not isinstance(order_map, dict): order_map = {}
                indexed.sort(key=lambda x: order_map.get(x[1], 2))
                reorder = [idx for idx, _ in indexed]
                frags = [frags[r] for r in reorder]
                frag_data = [frag_data[r] for r in reorder]
                frag_classifications = [frag_classifications[r] for r in reorder]
                # Remap coords ordering doesn't change (atom indices are absolute)

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
            # 원자 수에 따라 마진/스케일 적응 — 많은 원자일수록 여유 필요
            n_atoms = len(xs)
            # 기본 마진 30px, 원자 10개 초과 시 추가 마진 (라벨 겹침 방지)
            margin = 30 + max(0, (n_atoms - 10)) * 2  # px
            # 스케일 팩터: 작은 분자 0.82, 큰 분자 0.68 (원자 수 비례 감소)
            if mechanism_mode and mechanism_type == "br2_anti_addition":
                scale_factor = 1.00
            else:
                scale_factor = max(0.68, 0.82 - max(0, n_atoms - 8) * 0.01)
            scale = min((rect.width() - margin * 2) / rx,
                        (rect.height() - margin * 2) / ry) * scale_factor

        def tx(x, y):
            return QPointF(
                rect.x() + rect.width() / 2 + (x - cx) * scale,
                rect.y() + rect.height() / 2 - (y - cy) * scale
            )

        # Store atom positions
        for i, (x, y, atom) in enumerate(coords):
            atom_positions[i] = tx(x, y)

        # ── 프래그먼트 배경 틴팅 + 라벨 (mechanism_mode) ──
        # Fragment bounding boxes in pixel space for later arrow routing
        frag_pixel_bboxes = []  # [(xmin, ymin, xmax, ymax)] per fragment
        if n_frags > 1 and frag_data:
            # Compute pixel-space bounding boxes for each fragment
            for fi, fd in enumerate(frag_data):
                frag_atom_pts = [atom_positions[a] for a in fd['atoms']
                                 if a in atom_positions]
                if frag_atom_pts:
                    fxmin = min(p.x() for p in frag_atom_pts) - 12
                    fxmax = max(p.x() for p in frag_atom_pts) + 12
                    fymin = min(p.y() for p in frag_atom_pts) - 16
                    fymax = max(p.y() for p in frag_atom_pts) + 16
                    frag_pixel_bboxes.append((fxmin, fymin, fxmax, fymax))
                else:
                    frag_pixel_bboxes.append((0, 0, 0, 0))

        if n_frags > 1 and mechanism_mode and frag_classifications:
            # Background tinting per fragment classification
            _FRAG_TINTS = {
                'nucleophile': QColor(232, 240, 254, 50),     # light blue #e8f0fe
                'substrate': QColor(255, 255, 255, 0),        # transparent (white)
                'leaving_group': QColor(253, 232, 232, 50),   # light red #fde8e8
                'reagent': QColor(240, 248, 230, 50),         # light green
            }
            _FRAG_LABELS = {
                'nucleophile': '친핵체',
                'substrate': '기질',
                'leaving_group': '이탈기',
                'reagent': '시약',
            }
            _FRAG_BORDER_COLORS = {
                'nucleophile': QColor(100, 140, 220, 80),
                'substrate': QColor(180, 180, 180, 60),
                'leaving_group': QColor(220, 100, 100, 80),
                'reagent': QColor(140, 180, 100, 60),
            }

            painter.save()
            for fi in range(n_frags):
                if fi >= len(frag_pixel_bboxes) or fi >= len(frag_classifications):
                    continue
                cls = frag_classifications[fi]
                bx1, by1, bx2, by2 = frag_pixel_bboxes[fi]
                box_rect = QRectF(bx1 - 4, by1 - 4, bx2 - bx1 + 8, by2 - by1 + 8)

                # Background tint with rounded corners
                tint = _FRAG_TINTS.get(cls, QColor(0, 0, 0, 0))
                if tint.alpha() > 0:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(tint))
                    painter.drawRoundedRect(box_rect, 6, 6)

                # Subtle border
                border_color = _FRAG_BORDER_COLORS.get(cls, QColor(180, 180, 180, 60))
                painter.setPen(QPen(border_color, 1.0, Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(box_rect, 6, 6)

                # Fragment label below
                label = _FRAG_LABELS.get(cls, '')
                if label:
                    painter.setFont(QFont("Malgun Gothic", 7))
                    painter.setPen(QColor(120, 120, 120))
                    label_rect = QRectF(bx1 - 4, by2 + 4, bx2 - bx1 + 8, 14)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
                if mechanism_type in {"electrophilic_addition", "br2_anti_addition"} and cls == "substrate":
                    painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
                    painter.setPen(QColor(80, 80, 80))
                    painter.drawText(
                        QRectF(bx1 - 12, by1 - 18, bx2 - bx1 + 24, 14),
                        Qt.AlignmentFlag.AlignCenter,
                        "C=C pi")
            painter.restore()

        # ── 프래그먼트 사이 '+' 기호 또는 점선 분리선 그리기 ──
        if n_frags > 1:
            painter.save()
            painter.setPen(COLOR_BOND)
            painter.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
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

                hbr_pair = False
                if mechanism_mode and mechanism_type == "electrophilic_addition":
                    try:
                        def _single_atom_info(frag_atoms):
                            if len(frag_atoms) != 1:
                                return None
                            idx = list(frag_atoms)[0]
                            atom = mol.GetAtomWithIdx(idx)
                            return idx, atom.GetSymbol(), atom.GetFormalCharge()

                        left_info = _single_atom_info(frag_r)
                        right_info = _single_atom_info(frag_next)
                        infos = [info for info in (left_info, right_info) if info is not None]
                        hbr_pair = (
                            len(infos) == 2
                            and any(info[1] == "H" and info[2] > 0 for info in infos)
                            and any(info[1] == "Br" and info[2] < 0 for info in infos)
                        )
                    except Exception as pair_exc:
                        logger.warning("[M860] HBr polar pair detection fallback: %s", pair_exc)

                if hbr_pair:
                    # M860: HBr acid addition must look like a polarized H-Br
                    # reagent, not two unrelated ions separated by plus signs.
                    h_idx = br_idx = None
                    for idx in list(frag_r) + list(frag_next):
                        atom = mol.GetAtomWithIdx(idx)
                        if atom.GetSymbol() == "H":
                            h_idx = idx
                        elif atom.GetSymbol() == "Br":
                            br_idx = idx
                    if h_idx in atom_positions and br_idx in atom_positions:
                        hp = atom_positions[h_idx]
                        bp = atom_positions[br_idx]
                        painter.setPen(QPen(QColor(90, 90, 90), 1.4, Qt.PenStyle.DashLine))
                        painter.drawLine(hp, bp)
                        mid_x = (hp.x() + bp.x()) / 2
                        mid_y = min(hp.y(), bp.y()) - 22
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
                        painter.drawRoundedRect(QRectF(mid_x - 38, mid_y - 8, 76, 16), 3, 3)
                        painter.setPen(QColor(80, 80, 80))
                        painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
                        painter.drawText(QRectF(mid_x - 38, mid_y - 8, 76, 16),
                                         Qt.AlignmentFlag.AlignCenter, "Hδ+—Brδ−")
                        solv_y = max(hp.y(), bp.y()) + 34
                        if solv_y < rect.bottom() - 18:
                            painter.setPen(Qt.PenStyle.NoPen)
                            painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
                            painter.drawRoundedRect(QRectF(mid_x - 44, solv_y - 12, 88, 24), 3, 3)
                            painter.setPen(QPen(QColor(90, 90, 90), 1.0))
                            painter.drawLine(QPointF(mid_x - 18, solv_y), QPointF(mid_x, solv_y + 4))
                            painter.drawLine(QPointF(mid_x, solv_y + 4), QPointF(mid_x + 18, solv_y))
                            painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
                            painter.setPen(QColor(180, 30, 30))
                            painter.drawText(QRectF(mid_x - 8, solv_y - 5, 16, 14),
                                             Qt.AlignmentFlag.AlignCenter, "O")
                            painter.setPen(QColor(80, 80, 80))
                            painter.drawText(QRectF(mid_x - 38, solv_y - 10, 18, 14),
                                             Qt.AlignmentFlag.AlignCenter, "H")
                            painter.drawText(QRectF(mid_x + 20, solv_y - 10, 18, 14),
                                             Qt.AlignmentFlag.AlignCenter, "H")
                            painter.setFont(QFont("Malgun Gothic", 6))
                            painter.drawText(QRectF(mid_x - 44, solv_y + 8, 88, 10),
                                             Qt.AlignmentFlag.AlignCenter, "H2O/ROH solvent")
                elif mechanism_mode:
                    # Draw dotted vertical separator line between fragments
                    sep_pen = QPen(QColor(180, 180, 180, 120), 1.0, Qt.PenStyle.DotLine)
                    painter.setPen(sep_pen)
                    sep_top = min(rect.top() + 5, plus_y - 40)
                    sep_bot = max(rect.bottom() - 5, plus_y + 40)
                    painter.drawLine(QPointF(plus_x, sep_top), QPointF(plus_x, sep_bot))
                    # Also draw '+' symbol at midpoint for clarity
                    painter.setPen(QColor(140, 140, 140))
                    painter.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
                    painter.drawText(QRectF(plus_x - 10, plus_y - 10, 20, 20),
                                     Qt.AlignmentFlag.AlignCenter, "+")
                else:
                    # Standard '+' symbol between fragments
                    painter.setPen(COLOR_BOND)
                    painter.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
                    painter.drawText(QRectF(plus_x - 10, plus_y - 10, 20, 20),
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
        except Exception as e:
            logger.warning("Kekulize failed, using original bond order: %s", e)

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
            # Rule N: isinstance guard for kekulized_orders
            if not isinstance(kekulized_orders, dict): kekulized_orders = {}
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
        font = QFont("Malgun Gothic", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i, (x, y, atom) in enumerate(coords):
            sym = atom.GetSymbol()
            charge = atom.GetFormalCharge()
            num_h = atom.GetTotalNumHs()
            pt = atom_positions[i]

            # Skip carbon unless it has charge or is terminal
            is_terminal = (atom.GetDegree() <= 1 and sym == "C")
            hide_mechanism_terminal_carbon = (
                mechanism_mode and sym == "C" and charge == 0
                and is_terminal and atom.GetDegree() == 1
            )
            if hide_mechanism_terminal_carbon:
                continue
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
                charge_text = "⁻" if charge == -1 else f"{abs(charge)}⁻"  # U+207B SUPERSCRIPT MINUS — 학술 표기, Arial offscreen 글리프 호환 (DEFECT-1)

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
                            # Rule N: isinstance guard for atom_positions
                            if not isinstance(atom_positions, dict): atom_positions = {}
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
                        dot_r = 2.0  # M473 DEFECT-V5: 1.5 → 2.0 (교과서 론페어 도트 크기)

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
                except Exception as e:
                    logger.debug("Bond drawing error: %s", e)

            # Highlight
            if highlight_atoms and i in highlight_atoms:
                painter.setPen(QPen(QColor(255, 0, 0, 120), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pt, 12, 12)

        # Atom index labels (debug mode)
        if show_atom_indices:
            painter.setFont(QFont("Malgun Gothic", 6))
            painter.setPen(QColor(150, 150, 150))
            for i, pt in atom_positions.items():
                painter.drawText(QPointF(pt.x() + 8, pt.y() - 8), str(i))

        return atom_positions

    @staticmethod
    def _classify_fragments(mol, frags, mechanism_type: str = "ionic"):
        """Classify fragments as nucleophile/substrate/leaving_group/reagent.

        Classification heuristics:
        - Small anion (charge < 0, <=3 atoms) → nucleophile
        - Small halide fragment (<=2 atoms) → leaving_group
        - Largest fragment → substrate
        - Neutral lone-pair donor (O/N/S with charge<=0, small) → nucleophile
        - Everything else → reagent

        DEFECT-2 fix: 페리사이클릭/협동 메커니즘(Diels-Alder, Cope, Claisen 등)은
        친핵체/이탈기 분류가 의미없으므로 빈 목록 반환 (분류 라벨 비활성).
        """
        # Pericyclic/concerted: no nucleophile/leaving_group classification applicable
        _PERICYCLIC_TYPES = {
            "pericyclic", "concerted", "diels_alder", "cycloaddition_2_2",
            "cope_rearrangement", "claisen_rearrangement", "ene_reaction",
            "sigmatropic",
        }
        if mechanism_type in _PERICYCLIC_TYPES:
            logger.debug(
                "_classify_fragments: 페리사이클릭 메커니즘(%s) — SN/E 분류 비활성",
                mechanism_type
            )
            return []  # 분류 라벨 표시 없음 (배경 틴팅도 비활성)

        classifications = []
        max_atoms = max(len(f) for f in frags) if frags else 1

        for fi, frag_atoms in enumerate(frags):
            total_charge = sum(
                mol.GetAtomWithIdx(a).GetFormalCharge() for a in frag_atoms
            )
            has_lone_pair_donor = any(
                mol.GetAtomWithIdx(a).GetSymbol() in ('O', 'N', 'S')
                and mol.GetAtomWithIdx(a).GetFormalCharge() <= 0
                for a in frag_atoms
            )
            has_halide = any(
                mol.GetAtomWithIdx(a).GetSymbol() in ('F', 'Cl', 'Br', 'I')
                for a in frag_atoms
            )
            n_atoms = len(frag_atoms)

            if total_charge < 0 and n_atoms <= 3:
                classifications.append('nucleophile')
            elif has_halide and n_atoms <= 2:
                classifications.append('leaving_group')
            elif n_atoms == max_atoms:
                classifications.append('substrate')
            elif has_lone_pair_donor and n_atoms <= 4 and total_charge <= 0:
                classifications.append('nucleophile')
            else:
                classifications.append('reagent')

        return classifications


def _subscript(n: int) -> str:
    """Unicode subscript digits"""
    subs = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    return str(n).translate(subs)


# ============================================================================
# CURVED ARROW RENDERER (Textbook Style — Black)
# ============================================================================

class CurvedArrowRenderer:
    """교과서 스타일 곡선 화살표 렌더링

    v3.0 개선:
    - 100px 이상 화살표: cubic Bezier (2 제어점) S-curve
    - 100px 미만: quadratic Bezier (1 제어점) 유지
    - 적응형 bulge: 0.25 * length (cap 120) — 긴 화살표도 자연스러운 곡선
    - 화살표 겹침 방지: arrow_index 기반 교대 곡률 + ±3px 오프셋
    - 화살촉 비례 크기: max(8, min(0.12*length, 16))
    - Anti-aliasing 강제 + 2.0px 펜 기본값
    - 론페어 출발 시 전자쌍 도트(·:) 렌더링
    """

    @staticmethod
    def _calc_control_points(start: QPointF, end: QPointF, curvature: float,
                             arrow_index: int = 0):
        """시작/끝 좌표와 곡률로 제어점 계산.

        Args:
            arrow_index: 겹침 방지용 화살표 순번 (±3px 오프셋 적용)

        Returns:
            For length >= 100: (ctrl1, ctrl2, length, dx, dy) — cubic 제어점 2개
            For length < 100:  (ctrl, None, length, dx, dy) — quadratic 제어점 1개
        """
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return None, None, length, dx, dy

        # 적응형 bulge: 짧은 화살표는 작게, 긴 화살표는 0.25*length (max 120px)
        if length < 30:
            min_bulge = 8
            max_bulge = 20  # 아주 짧은 화살표용
        else:
            min_bulge = 18  # 결합선에서 충분히 떨어짐
            max_bulge = 120  # 긴 화살표: 더 풍성한 곡선 (감사팀 #1 반영)

        raw_bulge = abs(curvature) * length
        # 0.25 * length 스케일링 (기존 curvature*length 대비 더 자연스러운 비율)
        adaptive_bulge = min(0.25 * length, max_bulge)  # 0.25배 스케일
        bulge = max(min_bulge, min(raw_bulge, adaptive_bulge))

        sign = 1 if curvature >= 0 else -1

        # 겹침 방지: arrow_index 기반 ±3px 추가 오프셋
        overlap_offset = arrow_index * 3.0  # px per arrow index

        total_bulge = bulge + overlap_offset
        perp_x = -dy / length * sign * total_bulge
        perp_y = dx / length * sign * total_bulge

        if length >= 100:
            # Cubic Bezier: 1/3, 2/3 지점에 제어점 배치
            # 부드러운 호(arc) 형태: 중앙에서 최대 bulge, 양 끝에서 점진적 감소
            # ctrl1(1/3 지점)과 ctrl2(2/3 지점)에 동일 방향 수직 오프셋 적용
            # → 시작/끝점과 합쳐져 자연스러운 호 형태 생성
            p1 = QPointF(start.x() + dx / 3, start.y() + dy / 3)
            p2 = QPointF(start.x() + dx * 2 / 3, start.y() + dy * 2 / 3)
            ctrl1 = QPointF(p1.x() + perp_x * 1.1, p1.y() + perp_y * 1.1)
            ctrl2 = QPointF(p2.x() + perp_x * 1.1, p2.y() + perp_y * 1.1)
            return ctrl1, ctrl2, length, dx, dy
        else:
            # Quadratic Bezier: 중점에 단일 제어점
            mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
            ctrl = QPointF(mid.x() + perp_x, mid.y() + perp_y)
            return ctrl, None, length, dx, dy

    @staticmethod
    def draw_full_arrow(painter: QPainter, start: QPointF, end: QPointF,
                        curvature: float = 0.3, color: QColor = COLOR_ARROW,
                        width: float = 2.2, show_lone_pair: bool = False,
                        arrow_index: int = 0):
        """2전자 이동 곡선 화살표 (실선, 꽉 찬 화살촉)
        # width 기본값 2.0 → 2.2 (M473 DEFECT-V3): 결합선 2.0px 대비 약간 두껍게

        Args:
            show_lone_pair: True이면 시작점에 전자쌍 도트(··) 표시
            arrow_index: 겹침 방지용 화살표 순번
        """
        painter.save()
        # Anti-aliasing 강제
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        ctrl1, ctrl2, length, dx, dy = CurvedArrowRenderer._calc_control_points(
            start, end, curvature, arrow_index)
        if ctrl1 is None:
            painter.restore()
            return

        # ── 화살촉-원자 간격: 끝점을 접선 방향으로 4px 후퇴 (감사팀 #2) ──
        _ARROW_GAP = 4.0  # px: 화살촉 끝 → 원자 중심 간 여백
        last_ctrl = ctrl2 if ctrl2 is not None else ctrl1
        tx = end.x() - last_ctrl.x()
        ty = end.y() - last_ctrl.y()
        tlen = math.sqrt(tx * tx + ty * ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen
        # 화살촉 끝점을 원자에서 4px 떨어뜨림
        tip = QPointF(end.x() - _ARROW_GAP * tx, end.y() - _ARROW_GAP * ty)

        # Draw curve — width 펜 (교과서 가독성)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        if ctrl2 is not None:
            # Cubic Bezier (긴 화살표 >= 100px): 부드러운 호
            path.cubicTo(ctrl1, ctrl2, tip)
        else:
            # Quadratic Bezier (짧은 화살표 < 100px)
            path.quadTo(ctrl1, tip)
        painter.drawPath(path)

        # Filled arrowhead — 비례 크기: max(10, min(0.15*length, 18)) (M473 DEFECT-V1)
        # Magic: 10px min = 2.2px 선 기준 4.5배 비율 (PDF 표준: 화살촉 >= 선두께 4-5배)
        # Magic: 18px max = 큰 패널에서 원자 라벨 가리지 않는 상한
        arrow_size = max(10, min(0.15 * length, 18))  # M473 DEFECT-V1

        # 교과서 표준: McMurry 삼각형 (0.42 비율) — 기존 0.35 → 0.42 (M473 DEFECT-V1)
        # Magic: 0.42 = 화살촉 너비/길이 비율 (교과서 PDF 비교: 이등변삼각형 적정 비율)
        half_w = arrow_size * 0.42  # M473 DEFECT-V1
        px1 = tip.x() - arrow_size * tx + half_w * ty
        py1 = tip.y() - arrow_size * ty - half_w * tx
        px2 = tip.x() - arrow_size * tx - half_w * ty
        py2 = tip.y() - arrow_size * ty + half_w * tx

        arrow_path = QPainterPath()
        arrow_path.moveTo(tip)
        arrow_path.lineTo(QPointF(px1, py1))
        arrow_path.lineTo(QPointF(px2, py2))
        arrow_path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(arrow_path)

        # Lone pair dots at tail (선택적)
        if show_lone_pair and length > 15:
            CurvedArrowRenderer._draw_lone_pair_dots(
                painter, start, ctrl1, color, width)

        painter.restore()

    @staticmethod
    def draw_half_arrow(painter: QPainter, start: QPointF, end: QPointF,
                        curvature: float = 0.3, color: QColor = COLOR_ARROW,
                        width: float = 1.8, show_lone_pair: bool = False,
                        arrow_index: int = 0):
        """1전자 이동 피셔훅 화살표 (반쪽 화살촉)
        # width 기본값 1.5 → 1.8 (M473 DEFECT-V3): fishhook 가시성 향상

        Args:
            show_lone_pair: True이면 시작점에 단일 전자 도트(·) 표시
            arrow_index: 겹침 방지용 화살표 순번
        """
        painter.save()
        # Anti-aliasing 강제
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        ctrl1, ctrl2, length, dx, dy = CurvedArrowRenderer._calc_control_points(
            start, end, curvature, arrow_index)
        if ctrl1 is None:
            painter.restore()
            return

        # ── 화살촉-원자 간격: 끝점을 접선 방향으로 4px 후퇴 (감사팀 #2) ──
        _ARROW_GAP = 4.0  # px: 화살촉 끝 → 원자 중심 간 여백
        last_ctrl = ctrl2 if ctrl2 is not None else ctrl1
        tx = end.x() - last_ctrl.x()
        ty = end.y() - last_ctrl.y()
        tlen = math.sqrt(tx * tx + ty * ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen
        tip = QPointF(end.x() - _ARROW_GAP * tx, end.y() - _ARROW_GAP * ty)

        # width 펜 (교과서 가독성)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        if ctrl2 is not None:
            path.cubicTo(ctrl1, ctrl2, tip)
        else:
            path.quadTo(ctrl1, tip)
        painter.drawPath(path)

        # Single barb (fishhook) — 비례 크기 (M473 DEFECT-V1/V2)
        # Magic: 10px min = 1.8px 선 기준 5.5배 비율 (PDF 표준)
        # Magic: 18px max = 상한 (full arrow와 동일 상한 유지)
        arrow_size = max(10, min(0.15 * length, 18))  # M473 DEFECT-V2

        # 피셔훅: 한쪽만 — 폭 0.40 (기존 0.27 → 0.40, M473 DEFECT-V2)
        # Magic: 0.40 = 라디칼 fishhook 식별 가능 최소 비율 (교과서 기준)
        barb_width = arrow_size * 0.40  # M473 DEFECT-V2
        bx = tip.x() - arrow_size * tx + barb_width * ty
        by = tip.y() - arrow_size * ty - barb_width * tx

        pen2 = QPen(color, 2.0 + 0.3)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawLine(tip, QPointF(bx, by))

        # Single electron dot at tail (선택적)
        if show_lone_pair and length > 15:
            CurvedArrowRenderer._draw_single_electron_dot(
                painter, start, ctrl1, color)

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
        dot_r = max(2.0, width * 0.8)  # M473 DEFECT-V5: min 1.8 → 2.0, ratio 0.7 → 0.8

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
        font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
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
        # Anti-aliasing 강제 — M757: draw_reaction_arrow만 누락되어 있던 RenderHint 추가
        # Kimi K2 감사: SmoothPixmapTransform은 QPainterPath에 무효, Antialiasing만 유효
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

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
            painter.setFont(QFont("Malgun Gothic", 9))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, mid_y - 22, 160, 18),
                Qt.AlignmentFlag.AlignCenter, reagents_above)

        # Conditions below arrow
        if conditions_below:
            painter.setPen(COLOR_LABEL)
            painter.setFont(QFont("Malgun Gothic", 8))
            mid_x = (x1 + x2) / 2
            bg_rect = QRectF(mid_x - 85, mid_y + 11, 170, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
            painter.drawRect(bg_rect)
            painter.setPen(COLOR_LABEL)
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, conditions_below)

        painter.restore()

    @staticmethod
    def draw_retrosynthetic_arrow(painter: QPainter, x1: float, x2: float,
                                  y: float, reagents_above: str = "",
                                  conditions_below: str = "",
                                  color: QColor = COLOR_BOND, width: float = 1.5):
        """역합성 화살표 (=>>): 열린 삼각형 화살촉 + 이중 샤프트

        교과서 역합성 분석(Corey retrosynthetic analysis)에서 사용하는
        열린(open-headed) 화살표. 생성물에서 출발물질 방향을 나타냄.

        Args:
            x1: 시작 x좌표 (생성물 쪽)
            x2: 끝 x좌표 (출발물질 쪽)
            y: 화살표 y좌표
            reagents_above: 화살표 위 시약 텍스트
            conditions_below: 화살표 아래 조건 텍스트
            color: 화살표 색상 (기본: 검정)
            width: 선 두께
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        mid_y = y
        arrow_size = 10  # px: 열린 화살촉 크기
        half_gap = 2.0   # px: 이중선 간격의 절반

        # ── 이중 샤프트 (retrosynthetic 표준: 두 줄 평행선) ──
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 상단 라인
        painter.drawLine(QPointF(x1, mid_y - half_gap),
                         QPointF(x2 - arrow_size, mid_y - half_gap))
        # 하단 라인
        painter.drawLine(QPointF(x1, mid_y + half_gap),
                         QPointF(x2 - arrow_size, mid_y + half_gap))

        # ── 열린 삼각형 화살촉 (채우지 않음) ──
        head_half_h = 5.0  # px: 화살촉 세로 반폭
        head_pen = QPen(color, width + 0.3)
        head_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        head_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(head_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        head_path = QPainterPath()
        head_path.moveTo(QPointF(x2 - arrow_size, mid_y - head_half_h))
        head_path.lineTo(QPointF(x2, mid_y))
        head_path.lineTo(QPointF(x2 - arrow_size, mid_y + head_half_h))
        painter.drawPath(head_path)

        # ── 시약/조건 라벨 ──
        if reagents_above:
            painter.setPen(COLOR_REAGENT)
            painter.setFont(QFont("Malgun Gothic", 9))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, mid_y - 24, 160, 18),
                Qt.AlignmentFlag.AlignCenter, reagents_above)

        if conditions_below:
            painter.setPen(COLOR_LABEL)
            painter.setFont(QFont("Malgun Gothic", 8))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, mid_y + 7, 160, 16),
                Qt.AlignmentFlag.AlignCenter, conditions_below)

        painter.restore()

    @staticmethod
    def draw_equilibrium_arrows(painter: QPainter, x1: float, x2: float,
                                y: float, reagents_above: str = "",
                                conditions_below: str = "",
                                color: QColor = COLOR_BOND, width: float = 1.3):
        """가역 반응 평형 화살표: 상하 두 개의 반쪽 화살표 (harpoon 스타일)

        교과서 가역 반응 표기: 위 화살표(정반응, 오른쪽), 아래 화살표(역반응, 왼쪽).
        각 화살표는 반쪽 화살촉(harpoon barb)으로 표현.

        Args:
            x1: 왼쪽 x좌표
            x2: 오른쪽 x좌표
            y: 중심 y좌표
            reagents_above: 화살표 위 텍스트
            conditions_below: 화살표 아래 텍스트
            color: 화살표 색상
            width: 선 두께
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        gap = 3.0           # px: 두 화살표 사이 수직 간격
        barb_size = 6.0     # px: 반쪽 화살촉 길이
        barb_half_w = 3.0   # px: 화살촉 세로 폭

        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # ── 상단: 정반응 (→, 오른쪽) ──
        y_top = y - gap
        painter.drawLine(QPointF(x1, y_top), QPointF(x2 - barb_size, y_top))
        # 반쪽 화살촉 (위쪽 barb만)
        painter.drawLine(QPointF(x2, y_top),
                         QPointF(x2 - barb_size, y_top - barb_half_w))
        painter.drawLine(QPointF(x2, y_top),
                         QPointF(x2 - barb_size, y_top))

        # ── 하단: 역반응 (←, 왼쪽) ──
        y_bot = y + gap
        painter.drawLine(QPointF(x1 + barb_size, y_bot), QPointF(x2, y_bot))
        # 반쪽 화살촉 (아래쪽 barb만)
        painter.drawLine(QPointF(x1, y_bot),
                         QPointF(x1 + barb_size, y_bot + barb_half_w))
        painter.drawLine(QPointF(x1, y_bot),
                         QPointF(x1 + barb_size, y_bot))

        # ── 시약/조건 라벨 ──
        if reagents_above:
            painter.setPen(COLOR_REAGENT)
            painter.setFont(QFont("Malgun Gothic", 9))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, y - gap - 20, 160, 18),
                Qt.AlignmentFlag.AlignCenter, reagents_above)

        if conditions_below:
            painter.setPen(COLOR_LABEL)
            painter.setFont(QFont("Malgun Gothic", 8))
            mid_x = (x1 + x2) / 2
            painter.drawText(
                QRectF(mid_x - 80, y + gap + 5, 160, 16),
                Qt.AlignmentFlag.AlignCenter, conditions_below)

        painter.restore()

    @staticmethod
    def draw_curved_retrosynthetic_arrow(painter: QPainter, start: QPointF,
                                         end: QPointF, curvature: float = 0.3,
                                         color: QColor = COLOR_BOND,
                                         width: float = 2.0,
                                         arrow_index: int = 0):
        """곡선 역합성 화살표 (열린 화살촉 + Bezier 곡선)

        역합성 분석에서 결합 끊기(disconnect)를 표시할 때 사용.
        draw_full_arrow와 동일한 곡선 경로에 열린(open) 화살촉 적용.

        Args:
            start: 시작점 (생성물 원자)
            end: 끝점 (출발물질 원자)
            curvature: 곡률
            color: 색상
            width: 선 두께
            arrow_index: 겹침 방지용 순번
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        ctrl1, ctrl2, length, dx, dy = CurvedArrowRenderer._calc_control_points(
            start, end, curvature, arrow_index)
        if ctrl1 is None:
            painter.restore()
            return

        # 화살촉-원자 간격
        _ARROW_GAP = 4.0  # px
        last_ctrl = ctrl2 if ctrl2 is not None else ctrl1
        tx = end.x() - last_ctrl.x()
        ty = end.y() - last_ctrl.y()
        tlen = math.sqrt(tx * tx + ty * ty)
        if tlen > 0:
            tx /= tlen
            ty /= tlen
        tip = QPointF(end.x() - _ARROW_GAP * tx, end.y() - _ARROW_GAP * ty)

        # 곡선 경로
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(start)
        if ctrl2 is not None:
            path.cubicTo(ctrl1, ctrl2, tip)
        else:
            path.quadTo(ctrl1, tip)
        painter.drawPath(path)

        # 열린 삼각형 화살촉 (채우지 않음) — 역합성 화살표 (draw_curved_retrosynthetic_arrow)
        # Magic: 10px min, 18px max = M473 DEFECT-V1 기준 (draw_full_arrow와 동일 상한)
        arrow_size = max(10, min(0.15 * length, 18))  # M473 DEFECT-V1
        half_w = arrow_size * 0.42  # M473 DEFECT-V1

        px1 = tip.x() - arrow_size * tx + half_w * ty
        py1 = tip.y() - arrow_size * ty - half_w * tx
        px2 = tip.x() - arrow_size * tx - half_w * ty
        py2 = tip.y() - arrow_size * ty + half_w * tx

        head_pen = QPen(color, width + 0.3)
        head_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        head_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(head_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        head_path = QPainterPath()
        head_path.moveTo(QPointF(px1, py1))
        head_path.lineTo(tip)
        head_path.lineTo(QPointF(px2, py2))
        painter.drawPath(head_path)

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
        # N-guard: mechanism must be MechanismData or None
        if mechanism is not None and not isinstance(mechanism, MechanismData):
            logger.warning("set_mechanism: mechanism is not MechanismData (got %s)",
                           type(mechanism).__name__)
            mechanism = None
        # N-guard: current_step must be int
        if not isinstance(current_step, int):
            logger.warning("set_mechanism: current_step is not int (got %s)",
                           type(current_step).__name__)
            current_step = 0
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
                    if mol is None:
                        logger.warning("Invalid SMILES in mechanism step: %s", smi)
                except Exception as e:
                    logger.warning("SMILES parse error for '%s': %s", smi, e)
            self._molecules.append((smi, mol))

        self.update()

    def set_step(self, step: MechanismStep, mechanism: MechanismData = None):
        """호환성: 기존 코드에서 step 단위 호출 시"""
        # N-guard: step must be MechanismStep
        if not isinstance(step, MechanismStep):
            logger.warning("set_step: step is not MechanismStep (got %s)",
                           type(step).__name__)
            return
        if mechanism is not None and not isinstance(mechanism, MechanismData):
            logger.warning("set_step: mechanism is not MechanismData (got %s)",
                           type(mechanism).__name__)
            mechanism = None
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
        _ensure_korean_font_ready()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, COLOR_BG)

        if not self._mechanism or not self._molecules:
            # M450: 메커니즘이 None인 경우 — 두 가지 상황 구분 (Rule M 사용자 피드백 의무)
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Malgun Gothic", 11))
            if self._mechanism is None:
                # 아직 아무 반응도 선택되지 않은 초기 상태는 없어야 함 (M450-AUTO-SELECT)
                # → 혹시 발생 시: "메커니즘 로딩 중..." 표시
                painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                                 "좌측에서 반응을 클릭하면 메커니즘이 표시됩니다")
            else:
                # 메커니즘은 있지만 분자 SMILES 파싱 실패
                painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                                 f"분자 구조 파싱 실패 — {self._mechanism.title}")
            painter.end()
            return

        mech = self._mechanism
        n_mols = len(self._molecules)

        # ── Title bar ──
        painter.setPen(COLOR_BOND)
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        title = f"{mech.title}"
        if self._current_step < len(mech.steps):
            st = mech.steps[self._current_step]
            title += f"  ·  Step {st.step_number}: {st.title}"
        painter.drawText(QRectF(10, 4, w - 20, 20), Qt.AlignmentFlag.AlignLeft, title)

        painter.setPen(QPen(QColor(200, 200, 200), 0.5))
        painter.drawLine(QPointF(10, 26), QPointF(w - 10, 26))

        dedicated_drawers = {
            "sn2": self._draw_sn2_pdf_standard_scheme,
            "br2_anti_addition": self._draw_br2_pdf_standard_scheme,
        }
        dedicated_drawer = dedicated_drawers.get(getattr(mech, "mechanism_type", ""))
        if dedicated_drawer is not None:
            dedicated_drawer(painter, QRectF(10, 30, w - 20, h - 70), self._current_step)
            if self._current_step < len(mech.steps):
                step = mech.steps[self._current_step]
                desc = step.description.replace("\n", " ")
                if getattr(mech, "mechanism_type", "") == "sn2":
                    desc = (
                        "SN2: 친핵체가 후면에서 탄소를 공격하고 C-Br 결합 전자는 Br-로 이동합니다. "
                        "전이상태와 Walden 반전을 표시합니다."
                    )
                desc_y = h - 35
                painter.setPen(QColor(80, 80, 80))
                painter.setFont(QFont("Malgun Gothic", 8))
                max_chars = max(1, (w - 20) // 5)
                if len(desc) > max_chars:
                    desc = desc[:max_chars - 3] + "..."
                painter.drawText(QRectF(10, desc_y, w - 20, 16),
                                 Qt.AlignmentFlag.AlignLeft, desc)
                if step.energy_label:
                    painter.setPen(QColor(180, 80, 0))
                    painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
                    painter.drawText(QRectF(w - 200, desc_y + 14, 190, 14),
                                     Qt.AlignmentFlag.AlignRight, step.energy_label)
            painter.end()
            return

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
        if RDKIT_AVAILABLE and 0 <= self._current_step < len(self._molecules):
            try:
                current_smi = self._molecules[self._current_step][0]
                current_mol = Chem.MolFromSmiles(current_smi) if current_smi else None
                frag_count = len(Chem.GetMolFrags(current_mol)) if current_mol is not None else 0
                if frag_count >= 3 and n_mols >= 3:
                    # M859: multi-fragment acid/electrophile steps need a wider
                    # reactant panel; otherwise C=C, H+/Br- and arrows overlap.
                    mols_per_row = 1
            except Exception as layout_exc:
                logger.warning("[M859] mechanism fragment layout fallback: %s", layout_exc)

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
                        if check_mol is None:
                            logger.warning("Invalid SMILES for stability check: %s", smi)
                        else:
                            has_formal_charge = any(
                                a.GetFormalCharge() != 0
                                for a in check_mol.GetAtoms()
                            )
                            has_radical = any(
                                a.GetNumRadicalElectrons() > 0
                                for a in check_mol.GetAtoms()
                            )
                            is_unstable = has_formal_charge or has_radical
                    except Exception as e:
                        logger.warning("Stability check error: %s", e)

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
                painter.setFont(QFont("Malgun Gothic", 10))
                painter.setPen(COLOR_TRANSITION)
                ts_x = mol_rect.right() + 6
                ts_y = mol_rect.top() + 14
                painter.drawText(QPointF(ts_x, ts_y), "\u2021")

            # Render molecule
            # Enable mechanism_mode when this molecule is the current step's
            # reactant and has mechanism arrows (multi-fragment separation)
            has_mech_arrows = (
                mi == self._current_step
                and mi < len(self._step_arrows)
                and len(self._step_arrows[mi]) > 0
            )
            if mol:
                # DEFECT-2: mechanism_type 전달 — 페리사이클릭 시 분류 라벨 비활성
                _mtype = (
                    self._mechanism.mechanism_type
                    if self._mechanism is not None and isinstance(self._mechanism.mechanism_type, str)
                    else "ionic"
                )
                positions = TextbookMoleculeRenderer.render(
                    painter, mol, mol_rect,
                    is_product=(mi == n_mols - 1),
                    mechanism_mode=has_mech_arrows,
                    mechanism_type=_mtype)
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
                # Use MechanismStep.reagents (Rule M: no silent return on missing attr)
                reagents = getattr(s, 'reagents', '') or ''
                if (
                    getattr(mech, 'mechanism_type', '') == "electrophilic_addition"
                    and reagents == "HBr"
                ):
                    conditions = "polar protic, 0°C→rt"
                else:
                    condition_parts = []
                    for attr in ('solvent', 'temperature', 'leaving_group'):
                        val = getattr(s, attr, '') or ''
                        if val:
                            condition_parts.append(val)
                    conditions = " | ".join(condition_parts) if condition_parts else (s.title[:25] if s.title else "")
                if len(conditions) > 24:
                    conditions = conditions[:22] + "..."
                if not reagents:
                    logger.debug("Step %d has no reagents label", step_idx)

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
                if mols_per_row == 1:
                    cx = r1.x() + r1.width() / 2
                elif row_curr % 2 == 0:
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
                    painter.setFont(QFont("Malgun Gothic", 7))
                    # DEFECT-3: 30자 + 말줄임표 (기존 20자 잘림 해소)
                    short_cond = conditions[:30] + ("…" if len(conditions) > 30 else "")
                    painter.drawText(QPointF(cx + 5, (cy1 + cy2) / 2), short_cond)

        # ── Draw mechanism arrows: previous steps grayed, current step full color ──
        # Previous steps (< current): light gray semi-transparent arrows
        gray_color = QColor(180, 180, 180, 100)  # semi-transparent gray for past steps
        current_mech_type = (
            self._mechanism.mechanism_type
            if self._mechanism is not None and isinstance(self._mechanism.mechanism_type, str)
            else ""
        )
        # Bromination step 2 is an SN2-like backside attack.  Showing the previous
        # pi attack on top of it makes the decisive backside arrow unreadable.
        if current_mech_type != "br2_anti_addition":
            for si in range(self._current_step):
                if si < len(self._step_arrows) and si < len(all_positions):
                    prev_arrows = self._step_arrows[si]
                    prev_positions = all_positions[si]
                    prev_mol_rect = mol_rects[si] if si < len(mol_rects) else QRectF()
                    self._draw_mechanism_arrows(
                        painter, prev_arrows, prev_positions, prev_mol_rect,
                        color_override=gray_color, step_idx_override=si)

        # Current step: full color arrows (as existing behavior)
        if self._current_step < len(self._step_arrows) and self._current_step < len(all_positions):
            arrows = self._step_arrows[self._current_step]
            positions = all_positions[self._current_step]
            mol_rect = mol_rects[self._current_step] if self._current_step < len(mol_rects) else QRectF()
            self._draw_mechanism_arrows(painter, arrows, positions, mol_rect)
        # Future steps (> current): no arrows drawn

        # ── Description at bottom ──
        if self._current_step < len(mech.steps):
            step = mech.steps[self._current_step]
            desc = step.description.replace("\n", " ")
            desc_y = h - 35
            painter.setPen(QColor(80, 80, 80))
            painter.setFont(QFont("Malgun Gothic", 8))
            max_chars = max(1, (w - 20) // 5)
            if len(desc) > max_chars:
                desc = desc[:max_chars - 3] + "..."
            painter.drawText(QRectF(10, desc_y, w - 20, 16),
                             Qt.AlignmentFlag.AlignLeft, desc)

            if step.energy_label:
                painter.setPen(QColor(180, 80, 0))
                painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
                painter.drawText(QRectF(w - 200, desc_y + 14, 190, 14),
                                 Qt.AlignmentFlag.AlignRight, step.energy_label)

        painter.end()

    def _draw_sn2_dedicated_scheme(self, painter: QPainter, rect: QRectF, step_idx: int) -> None:
        """Dedicated grid-snapped SN2 layout with backside attack and leaving arrow."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = QColor(0, 0, 0)
        atom_red = QColor(160, 0, 0)
        atom_blue = QColor(0, 80, 180)
        label = QColor(35, 35, 35)
        panel = rect.adjusted(12, 8, -12, -10)
        top = panel.top()
        y = top + panel.height() * 0.42
        base_y = top + panel.height() * 0.71
        left = panel.left() + 80
        center = panel.left() + panel.width() * 0.43
        right = panel.right() - 180

        def snap(p: QPointF) -> QPointF:
            grid = 12.0
            return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)

        def text_box(x: float, yy: float, text: str, width: float = 220.0) -> None:
            box = QRectF(x, yy, width, 16.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 242)))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(label)
            painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
            painter.drawText(box.adjusted(4, 0, -3, 0), Qt.AlignmentFlag.AlignLeft, text)

        def atom_text(x: float, yy: float, text: str, color: QColor = ink,
                      size: int = 11) -> None:
            painter.setPen(color)
            painter.setFont(QFont("Malgun Gothic", size, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 34, yy - 12, 68, 24),
                             Qt.AlignmentFlag.AlignCenter, text)

        def reaction_arrow(xa: float, xb: float, yy: float, title: str = "") -> None:
            painter.setPen(QPen(ink, 1.6))
            painter.drawLine(QPointF(xa, yy), QPointF(xb, yy))
            head = QPainterPath()
            head.moveTo(QPointF(xb, yy))
            head.lineTo(QPointF(xb - 10, yy - 5))
            head.lineTo(QPointF(xb - 10, yy + 5))
            head.closeSubpath()
            painter.fillPath(head, QBrush(ink))
            if title:
                painter.setPen(atom_blue)
                painter.setFont(QFont("Malgun Gothic", 8))
                painter.drawText(QRectF((xa + xb) / 2 - 72, yy - 25, 144, 18),
                                 Qt.AlignmentFlag.AlignCenter, title)

        def draw_reactant() -> tuple[QPointF, QPointF, QPointF]:
            nu = QPointF(left + 35, y)
            c = QPointF(center - 56, y)
            br = QPointF(center + 58, y)
            atom_text(nu.x(), nu.y(), ":OH-", atom_blue)
            painter.setPen(QPen(QColor(120, 120, 120), 1.0, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(nu.x() + 42, y), QPointF(c.x() - 34, y))
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(QPointF(c.x() + 26, y), QPointF(br.x() - 24, y))
            atom_text(c.x(), c.y(), "CH3")
            atom_text(br.x(), br.y(), "Br", atom_red)
            text_box(nu.x() - 44, y + 24, "nucleophile", 96)
            text_box(c.x() - 48, y + 24, "δ+ carbon", 102)
            text_box(br.x() - 42, y + 24, "leaving group", 116)
            return nu, c, br

        def draw_transition_state(cx: float) -> None:
            c = QPointF(cx, y)
            o = QPointF(cx - 92, y)
            br = QPointF(cx + 92, y)
            painter.setPen(QPen(QColor(120, 120, 120), 1.6, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(o.x() + 28, y), QPointF(c.x() - 28, y))
            painter.drawLine(QPointF(c.x() + 28, y), QPointF(br.x() - 28, y))
            painter.setPen(QPen(ink, 1.4))
            painter.drawLine(QPointF(cx - 124, y - 40), QPointF(cx - 124, y + 40))
            painter.drawLine(QPointF(cx + 124, y - 40), QPointF(cx + 124, y + 40))
            atom_text(o.x(), y, "HO", atom_blue)
            atom_text(c.x(), y, "C", ink)
            atom_text(br.x(), y, "Br", atom_red)
            text_box(cx - 102, y - 62, "five-coordinate transition state", 214)
            text_box(cx - 72, y + 48, "Walden inversion", 144)

        def draw_products(cx: float) -> None:
            c = QPointF(cx, y)
            o = QPointF(cx - 68, y)
            br = QPointF(cx + 122, y)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(QPointF(o.x() + 28, y), QPointF(c.x() - 28, y))
            atom_text(o.x(), y, "HO", atom_blue)
            atom_text(c.x(), y, "CH3")
            painter.setFont(QFont("Malgun Gothic", 17, QFont.Weight.Bold))
            painter.setPen(ink)
            painter.drawText(QRectF(cx + 50, y - 13, 24, 26), Qt.AlignmentFlag.AlignCenter, "+")
            atom_text(br.x(), y, "Br-", atom_red)

        if step_idx <= 0:
            nu, c, br = draw_reactant()
            ts_x = center + 300
            reaction_arrow(center + 104, ts_x - 140, y, "concerted")
            draw_transition_state(ts_x)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF(nu.x() + 30, y - 30)),
                snap(QPointF(c.x() - 22, y - 12)),
                curvature=0.32, color=ink, width=2.5, arrow_index=0)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF((c.x() + br.x()) / 2, y - 28)),
                snap(QPointF(br.x() + 48, y - 30)),
                curvature=-0.22, color=ink, width=2.5, arrow_index=1)
            text_box(left - 24, base_y - 10, "1 lone pair attacks the backside of carbon", 276)
            text_box(left - 24, base_y + 9, "2 C-Br sigma bond electrons leave to Br-", 262)
            text_box(left - 24, base_y + 28, "3 attack and leaving occur in one step", 244)
        else:
            draw_transition_state(center - 30)
            reaction_arrow(center + 120, right - 145, y, "inversion complete")
            draw_products(right - 18)
            text_box(left - 24, base_y - 10, "Product: C-O bond formed, Br- separated", 268)
            text_box(left - 24, base_y + 9, "Stereochemistry: backside attack gives inversion", 294)

        painter.restore()

    def _draw_br2_dedicated_scheme(self, painter: QPainter, rect: QRectF, step_idx: int) -> None:
        """Dedicated non-overlapping textbook layout for alkene bromination.

        The generic RDKit fragment layout is too compact for C=C + Br2, so this
        path draws the full electron-flow sequence in fixed lanes.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = QColor(0, 0, 0)
        atom_red = QColor(160, 0, 0)
        label = QColor(35, 35, 35)
        blue = QColor(0, 80, 180)
        panel = rect.adjusted(10, 6, -10, -8)
        top = panel.top()
        mid_y = top + panel.height() * 0.42
        base_y = top + panel.height() * 0.70
        x0 = panel.left() + 38
        x1 = panel.left() + panel.width() * 0.36
        x2 = panel.left() + panel.width() * 0.63
        x3 = panel.right() - 66

        def text_box(x: float, y: float, text: str, w: float = 170.0) -> None:
            box = QRectF(x, y, w, 16.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 242)))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(label)
            painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
            painter.drawText(box.adjusted(4, 0, -3, 0), Qt.AlignmentFlag.AlignLeft, text)

        def atom_text(x: float, y: float, text: str, color: QColor = ink) -> None:
            painter.setPen(color)
            painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 26, y - 10, 52, 20), Qt.AlignmentFlag.AlignCenter, text)

        def reaction_arrow(xa: float, xb: float, y: float, title: str = "") -> None:
            painter.setPen(QPen(ink, 1.6))
            painter.drawLine(QPointF(xa, y), QPointF(xb, y))
            path = QPainterPath()
            path.moveTo(QPointF(xb, y))
            path.lineTo(QPointF(xb - 10, y - 5))
            path.lineTo(QPointF(xb - 10, y + 5))
            path.closeSubpath()
            painter.fillPath(path, QBrush(ink))
            if title:
                painter.setPen(blue)
                painter.setFont(QFont("Malgun Gothic", 8))
                painter.drawText(QRectF((xa + xb) / 2 - 55, y - 24, 110, 18),
                                 Qt.AlignmentFlag.AlignCenter, title)

        def draw_ethene(cx: float, cy: float) -> tuple[QPointF, QPointF, QPointF]:
            left = QPointF(cx - 42, cy)
            right = QPointF(cx + 42, cy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(QPointF(left.x(), left.y() - 4), QPointF(right.x(), right.y() - 4))
            painter.drawLine(QPointF(left.x(), left.y() + 4), QPointF(right.x(), right.y() + 4))
            atom_text(left.x() - 28, cy, "H2C")
            atom_text(right.x() + 28, cy, "CH2")
            return left, right, QPointF((left.x() + right.x()) / 2, cy)

        def draw_br2(cx: float, cy: float) -> tuple[QPointF, QPointF, QPointF]:
            b1 = QPointF(cx - 32, cy)
            b2 = QPointF(cx + 32, cy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(b1, b2)
            atom_text(b1.x() - 8, cy, "Br", atom_red)
            atom_text(b2.x() + 8, cy, "Br", atom_red)
            return b1, b2, QPointF(cx, cy)

        def draw_bromonium(cx: float, cy: float) -> tuple[QPointF, QPointF, QPointF]:
            c1 = QPointF(cx - 40, cy + 18)
            c2 = QPointF(cx + 40, cy + 18)
            br = QPointF(cx, cy - 32)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(c1, c2)
            painter.drawLine(c1, br)
            painter.drawLine(c2, br)
            atom_text(c1.x() - 24, c1.y(), "CH2")
            atom_text(c2.x() + 24, c2.y(), "CH2")
            atom_text(br.x(), br.y() - 2, "Br+", atom_red)
            return c1, c2, br

        def draw_product(cx: float, cy: float) -> None:
            c1 = QPointF(cx - 48, cy)
            c2 = QPointF(cx + 48, cy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(c1, c2)
            painter.drawLine(c1, QPointF(c1.x() - 42, c1.y() - 24))
            painter.drawLine(c2, QPointF(c2.x() + 42, c2.y() + 24))
            atom_text(c1.x() - 58, c1.y() - 26, "Br", atom_red)
            atom_text(c2.x() + 58, c2.y() + 26, "Br", atom_red)
            atom_text(c1.x() - 8, c1.y(), "CH2")
            atom_text(c2.x() + 8, c2.y(), "CH2")

        painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
        painter.setPen(label)
        if step_idx <= 0:
            c_left, c_right, c_mid = draw_ethene(x0 + 70, mid_y)
            painter.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
            painter.drawText(QRectF(x0 + 150, mid_y - 12, 24, 24), Qt.AlignmentFlag.AlignCenter, "+")
            b1, b2, b_mid = draw_br2(x0 + 250, mid_y)
            reaction_arrow(x0 + 330, x1 - 70, mid_y, "Br2, CH2Cl2")
            draw_bromonium(x1 + 40, mid_y)
            atom_text(x1 + 142, mid_y, "Br-", atom_red)
            painter.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
            painter.drawText(QRectF(x1 + 94, mid_y - 12, 24, 24), Qt.AlignmentFlag.AlignCenter, "+")
            reaction_arrow(x1 + 175, x2 - 56, mid_y)
            draw_product(x3 - 40, mid_y)

            CurvedArrowRenderer.draw_full_arrow(
                painter, QPointF(c_mid.x(), c_mid.y() - 34), QPointF(b1.x() - 12, b1.y() - 18),
                curvature=0.20, color=ink, width=2.4, arrow_index=0)
            CurvedArrowRenderer.draw_full_arrow(
                painter, QPointF(b_mid.x(), b_mid.y() - 38), QPointF(b2.x() + 52, b2.y() - 38),
                curvature=-0.18, color=ink, width=2.4, arrow_index=1)
            CurvedArrowRenderer.draw_full_arrow(
                painter, QPointF(c_right.x() - 8, c_right.y() + 34), QPointF(b1.x() - 8, b1.y() + 22),
                curvature=-0.18, color=ink, width=2.2, arrow_index=2)
            text_box(x0 + 10, base_y - 10, "1 pi bond attacks Br(+)", 188)
            text_box(x0 + 10, base_y + 9, "2 Br-Br bond electrons leave to Br(-)", 252)
            text_box(x0 + 10, base_y + 28, "3 second C closes bromonium ion", 230)
            text_box(x1 - 12, top + 8, "TS: C-Br forming while Br-Br breaks", 250)
        else:
            c1, c2, brp = draw_bromonium(x0 + 160, mid_y)
            atom_text(x0 + 320, mid_y, "Br-", atom_red)
            painter.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
            painter.drawText(QRectF(x0 + 250, mid_y - 12, 24, 24), Qt.AlignmentFlag.AlignCenter, "+")
            reaction_arrow(x0 + 370, x2 - 56, mid_y, "anti backside attack")
            draw_product(x3 - 40, mid_y)
            CurvedArrowRenderer.draw_full_arrow(
                painter, QPointF(x0 + 318, mid_y - 28), QPointF(c2.x() + 10, c2.y() - 2),
                curvature=0.28, color=ink, width=2.4, arrow_index=0)
            CurvedArrowRenderer.draw_full_arrow(
                painter, QPointF((c2.x() + brp.x()) / 2, (c2.y() + brp.y()) / 2 - 22),
                QPointF(brp.x() - 34, brp.y() - 24),
                curvature=-0.20, color=ink, width=2.4, arrow_index=1)
            text_box(x0 + 12, base_y - 10, "1 Br(-) attacks the backside face", 230)
            text_box(x0 + 12, base_y + 9, "2 C-Br(+) bond opens to neutral Br", 234)
            text_box(x0 + 12, base_y + 28, "Anti addition gives trans-1,2-dibromide", 262)

        painter.restore()

    def _draw_sn2_pdf_standard_scheme(self, painter: QPainter, rect: QRectF, step_idx: int) -> None:
        """PDF-standard SN2: backside attack, sigma-bond departure, TS, inversion."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = QColor(0, 0, 0)
        grey = QColor(120, 120, 120)
        panel = rect.adjusted(18, 10, -18, -12)
        y = panel.top() + panel.height() * 0.39
        note_y = panel.top() + panel.height() * 0.70
        x_left = panel.left() + panel.width() * 0.18
        x_mid = panel.left() + panel.width() * 0.50
        x_right = panel.left() + panel.width() * 0.78

        def snap(p: QPointF) -> QPointF:
            grid = 12.0
            return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)

        def atom(x: float, yy: float, text: str, size: int = 12) -> None:
            painter.setPen(ink)
            painter.setFont(QFont("Malgun Gothic", size, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 42, yy - 14, 84, 28), Qt.AlignmentFlag.AlignCenter, text)

        def label_box(x: float, yy: float, text: str, w: float = 260.0) -> None:
            box = QRectF(x, yy, w, 20.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 242)))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QColor(35, 35, 35))
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            painter.drawText(box.adjusted(5, 0, -4, 0), Qt.AlignmentFlag.AlignLeft, text)

        def reaction_arrow(xa: float, xb: float, yy: float, title: str = "") -> None:
            painter.setPen(QPen(ink, 1.8))
            painter.drawLine(QPointF(xa, yy), QPointF(xb, yy))
            head = QPainterPath()
            head.moveTo(QPointF(xb, yy))
            head.lineTo(QPointF(xb - 12, yy - 6))
            head.lineTo(QPointF(xb - 12, yy + 6))
            head.closeSubpath()
            painter.fillPath(head, QBrush(ink))
            if title:
                label_box((xa + xb) / 2 - 52, yy - 34, title, 104)

        def wedge(start: QPointF, end: QPointF, width: float = 15.0) -> None:
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length = max(1.0, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            path = QPainterPath()
            path.moveTo(start)
            path.lineTo(QPointF(end.x() + nx * width / 2, end.y() + ny * width / 2))
            path.lineTo(QPointF(end.x() - nx * width / 2, end.y() - ny * width / 2))
            path.closeSubpath()
            painter.fillPath(path, QBrush(ink))

        def dash_bond(start: QPointF, end: QPointF, pieces: int = 5) -> None:
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length = max(1.0, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            painter.setPen(QPen(ink, 1.3))
            for i in range(pieces):
                t = (i + 1) / (pieces + 1)
                half = 2.0 + i * 1.2
                cx, cy = start.x() + dx * t, start.y() + dy * t
                painter.drawLine(QPointF(cx - nx * half, cy - ny * half),
                                 QPointF(cx + nx * half, cy + ny * half))

        def draw_substrate(cx: float, yy: float, inverted: bool = False) -> tuple[QPointF, QPointF]:
            c = QPointF(cx, yy)
            br = QPointF(cx + 88, yy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(QPointF(c.x() + 26, yy), QPointF(br.x() - 26, yy))
            atom(c.x(), c.y(), "C")
            atom(br.x(), br.y(), "Br")
            painter.setPen(QPen(ink, 1.5))
            up = "CH3" if inverted else "H"
            down = "H" if inverted else "CH3"
            painter.drawLine(c, QPointF(c.x(), c.y() - 44))
            painter.drawLine(c, QPointF(c.x(), c.y() + 44))
            atom(c.x(), c.y() - 56, up, 10)
            atom(c.x(), c.y() + 56, down, 10)
            if inverted:
                dash_bond(c, QPointF(c.x() + 42, c.y() - 30))
                wedge(c, QPointF(c.x() + 42, c.y() + 30))
            else:
                wedge(c, QPointF(c.x() - 42, c.y() - 30))
                dash_bond(c, QPointF(c.x() - 42, c.y() + 30))
            return c, br

        def draw_ts(cx: float, yy: float) -> None:
            c = QPointF(cx, yy)
            o = QPointF(cx - 96, yy)
            br = QPointF(cx + 96, yy)
            painter.setPen(QPen(grey, 1.7, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(o.x() + 30, yy), QPointF(c.x() - 26, yy))
            painter.drawLine(QPointF(c.x() + 26, yy), QPointF(br.x() - 30, yy))
            painter.setPen(QPen(ink, 1.5))
            painter.drawLine(QPointF(cx - 130, yy - 60), QPointF(cx - 130, yy + 60))
            painter.drawLine(QPointF(cx + 130, yy - 60), QPointF(cx + 130, yy + 60))
            atom(o.x(), yy, "HO")
            atom(c.x(), yy, "C")
            atom(br.x(), yy, "Br")
            painter.setPen(QPen(ink, 1.5))
            painter.drawLine(c, QPointF(c.x(), c.y() - 44))
            painter.drawLine(c, QPointF(c.x(), c.y() + 44))
            atom(c.x(), c.y() - 56, "H", 10)
            atom(c.x(), c.y() + 56, "CH3", 10)
            label_box(cx - 118, yy - 86, "partial Nu-C and C-Br bonds", 236)
            label_box(cx - 72, yy + 66, "Walden inversion", 150)

        def draw_product(cx: float, yy: float) -> None:
            c = QPointF(cx, yy)
            o = QPointF(cx - 80, yy)
            br = QPointF(cx + 118, yy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(QPointF(o.x() + 28, yy), QPointF(c.x() - 26, yy))
            atom(o.x(), yy, "HO")
            atom(c.x(), yy, "C")
            painter.setPen(QPen(ink, 1.5))
            painter.drawLine(c, QPointF(c.x(), c.y() - 44))
            painter.drawLine(c, QPointF(c.x(), c.y() + 44))
            atom(c.x(), c.y() - 56, "CH3", 10)
            atom(c.x(), c.y() + 56, "H", 10)
            dash_bond(c, QPointF(c.x() + 44, c.y() - 28))
            wedge(c, QPointF(c.x() + 44, c.y() + 30))
            painter.setFont(QFont("Malgun Gothic", 17, QFont.Weight.Bold))
            painter.setPen(ink)
            painter.drawText(QRectF(cx + 54, yy - 13, 24, 26), Qt.AlignmentFlag.AlignCenter, "+")
            atom(br.x(), yy, "Br-")

        if step_idx <= 0:
            nu = QPointF(x_left - 120, y)
            atom(nu.x(), nu.y(), ":OH-")
            c, br = draw_substrate(x_left, y, inverted=False)
            reaction_arrow(x_left + 126, x_mid - 150, y, "concerted")
            draw_ts(x_mid, y)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF(nu.x() + 34, y - 34)),
                snap(QPointF(c.x() - 24, y - 12)),
                curvature=0.32, color=ink, width=2.5, arrow_index=0,
                show_lone_pair=True)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF((c.x() + br.x()) / 2, y - 30)),
                snap(QPointF(br.x() + 52, y - 30)),
                curvature=-0.22, color=ink, width=2.5, arrow_index=1)
            label_box(panel.left() + 8, note_y - 10, "1 Nu lone pair attacks backside carbon", 292)
            label_box(panel.left() + 8, note_y + 14, "2 C-Br sigma electrons leave to Br-", 286)
            label_box(panel.left() + 8, note_y + 38, "3 one transition state, no carbocation", 286)
        else:
            draw_ts(x_left + 70, y)
            reaction_arrow(x_left + 240, x_right - 172, y, "inversion")
            draw_product(x_right, y)
            label_box(panel.left() + 8, note_y + 2, "Product shows Walden inversion and separated Br-", 342)

        painter.restore()

    def _draw_br2_pdf_standard_scheme(self, painter: QPainter, rect: QRectF, step_idx: int) -> None:
        """PDF-standard alkene bromination: bromonium formation then anti opening."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = QColor(0, 0, 0)
        grey = QColor(120, 120, 120)
        panel = rect.adjusted(18, 10, -18, -12)
        y = panel.top() + panel.height() * 0.40
        note_y = panel.top() + panel.height() * 0.70
        x_left = panel.left() + panel.width() * 0.18
        x_mid = panel.left() + panel.width() * 0.50
        x_right = panel.left() + panel.width() * 0.80

        def snap(p: QPointF) -> QPointF:
            grid = 12.0
            return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)

        def atom(x: float, yy: float, text: str, size: int = 12) -> None:
            painter.setPen(ink)
            painter.setFont(QFont("Malgun Gothic", size, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 42, yy - 14, 84, 28), Qt.AlignmentFlag.AlignCenter, text)

        def label_box(x: float, yy: float, text: str, w: float = 260.0) -> None:
            box = QRectF(x, yy, w, 20.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 242)))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QColor(35, 35, 35))
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            painter.drawText(box.adjusted(5, 0, -4, 0), Qt.AlignmentFlag.AlignLeft, text)

        def reaction_arrow(xa: float, xb: float, yy: float, title: str = "") -> None:
            painter.setPen(QPen(ink, 1.8))
            painter.drawLine(QPointF(xa, yy), QPointF(xb, yy))
            path = QPainterPath()
            path.moveTo(QPointF(xb, yy))
            path.lineTo(QPointF(xb - 12, yy - 6))
            path.lineTo(QPointF(xb - 12, yy + 6))
            path.closeSubpath()
            painter.fillPath(path, QBrush(ink))
            if title:
                label_box((xa + xb) / 2 - 64, yy - 34, title, 128)

        def lone_pairs(p: QPointF) -> None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(ink))
            for dx, dy in [(-12, -15), (-6, -15), (6, 15), (12, 15)]:
                painter.drawEllipse(QPointF(p.x() + dx, p.y() + dy), 2.0, 2.0)

        def wedge(start: QPointF, end: QPointF, width: float = 15.0) -> None:
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length = max(1.0, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            path = QPainterPath()
            path.moveTo(start)
            path.lineTo(QPointF(end.x() + nx * width / 2, end.y() + ny * width / 2))
            path.lineTo(QPointF(end.x() - nx * width / 2, end.y() - ny * width / 2))
            path.closeSubpath()
            painter.fillPath(path, QBrush(ink))

        def dash_bond(start: QPointF, end: QPointF, pieces: int = 5) -> None:
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length = max(1.0, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            painter.setPen(QPen(ink, 1.3))
            for i in range(pieces):
                t = (i + 1) / (pieces + 1)
                half = 2.0 + i * 1.2
                cx, cy = start.x() + dx * t, start.y() + dy * t
                painter.drawLine(QPointF(cx - nx * half, cy - ny * half),
                                 QPointF(cx + nx * half, cy + ny * half))

        def draw_ethene(cx: float, yy: float) -> tuple[QPointF, QPointF, QPointF]:
            c1 = QPointF(cx - 44, yy)
            c2 = QPointF(cx + 44, yy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(QPointF(c1.x(), yy - 5), QPointF(c2.x(), yy - 5))
            painter.drawLine(QPointF(c1.x(), yy + 5), QPointF(c2.x(), yy + 5))
            atom(c1.x() - 28, yy, "H2C")
            atom(c2.x() + 28, yy, "CH2")
            return c1, c2, QPointF(cx, yy)

        def draw_br2(cx: float, yy: float) -> tuple[QPointF, QPointF, QPointF]:
            b1 = QPointF(cx - 34, yy)
            b2 = QPointF(cx + 34, yy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(b1, b2)
            atom(b1.x() - 8, yy, "Br")
            atom(b2.x() + 8, yy, "Br")
            lone_pairs(b1)
            lone_pairs(b2)
            atom(b1.x() - 3, yy - 36, "delta+", 8)
            atom(b2.x() + 5, yy + 36, "delta-", 8)
            return b1, b2, QPointF(cx, yy)

        def draw_bromonium(cx: float, yy: float) -> tuple[QPointF, QPointF, QPointF]:
            c1 = QPointF(cx - 48, yy + 24)
            c2 = QPointF(cx + 48, yy + 24)
            br = QPointF(cx, yy - 34)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(c1, c2)
            painter.drawLine(c1, br)
            painter.drawLine(c2, br)
            atom(c1.x() - 26, c1.y(), "CH2", 10)
            atom(c2.x() + 26, c2.y(), "CH2", 10)
            atom(br.x(), br.y() - 2, "Br+")
            return c1, c2, br

        def draw_product(cx: float, yy: float) -> None:
            c1 = QPointF(cx - 52, yy)
            c2 = QPointF(cx + 52, yy)
            painter.setPen(QPen(ink, 2.0))
            painter.drawLine(c1, c2)
            wedge(c1, QPointF(c1.x() - 46, c1.y() - 30))
            dash_bond(c2, QPointF(c2.x() + 46, c2.y() + 30))
            atom(c1.x() - 62, c1.y() - 32, "Br")
            atom(c2.x() + 62, c2.y() + 32, "Br")
            atom(c1.x() - 7, c1.y(), "CH2", 10)
            atom(c2.x() + 7, c2.y(), "CH2", 10)
            label_box(cx - 92, yy + 62, "trans / anti addition", 184)

        if step_idx <= 0:
            c1, c2, c_mid = draw_ethene(x_left - 40, y)
            painter.setFont(QFont("Malgun Gothic", 17, QFont.Weight.Bold))
            painter.setPen(ink)
            painter.drawText(QRectF(x_left + 66, y - 13, 24, 26), Qt.AlignmentFlag.AlignCenter, "+")
            b1, b2, b_mid = draw_br2(x_left + 188, y - 44)
            reaction_arrow(x_left + 260, x_mid - 96, y)
            draw_bromonium(x_mid + 18, y)
            painter.setFont(QFont("Malgun Gothic", 17, QFont.Weight.Bold))
            painter.drawText(QRectF(x_mid + 126, y + 4, 24, 26), Qt.AlignmentFlag.AlignCenter, "+")
            atom(x_mid + 190, y + 18, "Br-")
            lone_pairs(QPointF(x_mid + 190, y + 18))
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF(c_mid.x(), c_mid.y() - 38)),
                snap(QPointF(b1.x() - 18, b1.y() + 22)),
                curvature=0.24, color=ink, width=2.5, arrow_index=0)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF(b_mid.x(), b_mid.y() - 32)),
                snap(QPointF(b2.x() + 58, b2.y() - 32)),
                curvature=-0.22, color=ink, width=2.5, arrow_index=1)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF(c2.x() - 10, c2.y() + 38)),
                snap(QPointF(b1.x() - 10, b1.y() + 34)),
                curvature=-0.22, color=ink, width=2.4, arrow_index=2)
            label_box(panel.left() + 8, note_y - 14, "1 pi bond attacks Br(delta+)", 252)
            label_box(panel.left() + 8, note_y + 10, "2 Br-Br sigma electrons leave to Br-", 300)
            label_box(panel.left() + 8, note_y + 34, "3 second alkene carbon closes bromonium ion", 342)
            label_box(x_mid - 70, y - 86, "bromonium ion intermediate only", 260)
        else:
            c1, c2, brp = draw_bromonium(x_left + 38, y)
            atom(x_left + 196, y + 20, "Br-")
            lone_pairs(QPointF(x_left + 196, y + 20))
            reaction_arrow(x_left + 252, x_right - 128, y, "anti opening")
            draw_product(x_right, y)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF(x_left + 190, y - 18)),
                snap(QPointF(c2.x() + 8, c2.y() - 4)),
                curvature=0.35, color=ink, width=2.5, arrow_index=0,
                show_lone_pair=True)
            CurvedArrowRenderer.draw_full_arrow(
                painter, snap(QPointF((c2.x() + brp.x()) / 2, (c2.y() + brp.y()) / 2 - 26)),
                snap(QPointF(brp.x() - 34, brp.y() - 32)),
                curvature=-0.28, color=ink, width=2.5, arrow_index=1)
            label_box(panel.left() + 8, note_y - 2, "1 Br- attacks the backside face", 270)
            label_box(panel.left() + 8, note_y + 22, "2 C-Br bridge bond opens to neutral Br", 314)
            label_box(panel.left() + 8, note_y + 46, "3 product is trans anti-1,2-dibromide", 316)

        painter.restore()

    def _draw_mechanism_arrows(self, painter: QPainter, arrows: List[ArrowData],
                               atom_positions: Dict[int, QPointF], mol_rect: QRectF,
                               color_override: Optional[QColor] = None,
                               step_idx_override: int = -1):
        """메커니즘 화살표 그리기 — Hybrid Grid 프래그먼트 인식 스마트 배치

        전략:
        1. from_atom_idx/to_atom_idx가 유효하면 그대로 사용
        2. 멀티 프래그먼트 SMILES에서는 프래그먼트 간 화살표 우선
        3. from_type/to_type + 원자 속성 기반 자동 배치
        4. Inter-fragment arrows: thicker, brighter red, curve UP, route via bbox edges
        5. Intra-fragment arrows: normal, darker red, alternate curvature

        Args:
            color_override: 이전 단계 회색 표시 등에 사용. None이면 기본 색상 사용.
        """
        if not arrows or not atom_positions:
            return
        # N-guard: validate external data types
        if not isinstance(atom_positions, dict):
            logger.warning("_draw_mechanism_arrows: atom_positions is not dict (got %s)", type(atom_positions).__name__)
            return
        if not isinstance(arrows, list):
            logger.warning("_draw_mechanism_arrows: arrows is not list (got %s)", type(arrows).__name__)
            return

        # Reorder arrows to form electron flow chain (Nu→C→LG)
        arrows = self._order_arrow_chain(arrows)

        # Get molecule info if available
        mol = None
        frag_map = {}  # atom_idx → fragment_idx
        frag_atoms = []  # list of sets of atom indices per fragment
        frag_pixel_bboxes = []  # [(xmin, ymin, xmax, ymax)] per fragment
        step_idx = step_idx_override if step_idx_override >= 0 else self._current_step
        if (self._mechanism and step_idx < len(self._mechanism.steps)
                and RDKIT_AVAILABLE):
            smi = self._mechanism.steps[step_idx].reactant_smiles
            if smi:
                try:
                    mol = Chem.MolFromSmiles(smi)
                    if mol is not None:  # Rule L: None guard
                        frags = Chem.GetMolFrags(mol, asMols=False)
                        for fi, fatoms in enumerate(frags):
                            frag_atoms.append(set(fatoms))
                            for a in fatoms:
                                frag_map[a] = fi
                            # Compute pixel bounding box for this fragment
                            frag_pts = [atom_positions[a] for a in fatoms
                                        if a in atom_positions]
                            if frag_pts:
                                fxmin = min(p.x() for p in frag_pts) - 12
                                fxmax = max(p.x() for p in frag_pts) + 12
                                fymin = min(p.y() for p in frag_pts) - 16
                                fymax = max(p.y() for p in frag_pts) + 16
                                frag_pixel_bboxes.append((fxmin, fymin, fxmax, fymax))
                            else:
                                frag_pixel_bboxes.append((0, 0, 0, 0))
                    else:
                        logger.warning("[Rule L] MolFromSmiles 실패: %r", smi)
                except Exception as e:
                    logger.debug("Fragment bbox calculation error: %s", e)

        is_multi_frag = len(frag_atoms) > 1

        # Bug 3 Fix (M894): atom_map_num 기반 idx 보정 — SMILES 재정렬 후에도 정확한 원자 지정
        # mol이 파싱된 직후, atom_positions 구성 전에 보정 적용
        if mol is not None and RDKIT_AVAILABLE:
            try:
                arrows = resolve_atom_map_indices(arrows, mol)
            except Exception as _e:
                logger.warning("resolve_atom_map_indices 실패 (기존 idx 유지): %s", _e)

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

        mechanism_type_for_overlay = (
            self._mechanism.mechanism_type
            if self._mechanism is not None and isinstance(self._mechanism.mechanism_type, str)
            else ""
        )
        if mechanism_type_for_overlay == "br2_anti_addition" and mol:
            if step_idx == 0 and self._draw_br2_textbook_step1_overlay(
                    painter, atom_positions, mol, color_override=color_override):
                return
            if step_idx == 1 and self._draw_br2_textbook_step2_overlay(
                    painter, atom_positions, mol, color_override=color_override):
                return

        # Bug 2 Fix (M894): from_atom_idx==-1 외부 심볼 가상 좌표 계산
        # Nu/LG 라벨이 "-1"인 화살표의 시작점을 atom_positions bbox 외부로 설정
        _external_positions: Dict[int, QPointF] = {}  # 가상 외부 좌표 캐시
        if atom_positions:
            _bbox_xmin = min(p.x() for p in atom_positions.values())
            _bbox_xmax = max(p.x() for p in atom_positions.values())
            _bbox_ymin = min(p.y() for p in atom_positions.values())
            _bbox_ymax = max(p.y() for p in atom_positions.values())
            _bbox_cx = (_bbox_xmin + _bbox_xmax) / 2
            _bbox_cy = (_bbox_ymin + _bbox_ymax) / 2
            _ext_margin = 50  # Magic: 50px 외부 여백 — 라벨이 분자 바깥에 위치 (M894)
            # Nu 심볼 → 왼쪽 외부 (Nu가 분자에 접근하는 방향)
            _external_positions[-10] = QPointF(_bbox_xmin - _ext_margin, _bbox_cy)
            # LG 심볼 → 오른쪽 외부 (LG가 분자에서 떠나는 방향)
            _external_positions[-11] = QPointF(_bbox_xmax + _ext_margin, _bbox_cy)
            # 상단 외부 (양성자 이탈 등)
            _external_positions[-12] = QPointF(_bbox_cx, _bbox_ymin - _ext_margin)
        else:
            _bbox_xmin = _bbox_xmax = _bbox_ymin = _bbox_ymax = _bbox_cx = _bbox_cy = 0

        for i, arrow in enumerate(arrows):
            from_idx = getattr(arrow, 'from_atom_idx', -1)
            to_idx = getattr(arrow, 'to_atom_idx', -1)

            # Bug 2 Fix (M894): from_atom_idx==-1 Nu/LG 시작점 처리
            # from_label에서 LG 여부 판단 → 외부 좌표 할당
            if from_idx < 0:
                from_label_lower = getattr(arrow, 'from_label', '').lower()
                if any(kw in from_label_lower for kw in ("이탈기", "lg", "leaving")):
                    # LG: 분자 오른쪽 외부
                    from_idx = -11
                elif any(kw in from_label_lower for kw in ("친핵", "nu", "nucleoph", "oh", "cn", "유입")):
                    # Nu: 분자 왼쪽 외부
                    from_idx = -10
                else:
                    # 기타 외부 원자 (양성자 등)
                    from_idx = -12
                # 외부 좌표를 atom_positions에 임시 등록
                if from_idx not in atom_positions and from_idx in _external_positions:
                    atom_positions[from_idx] = _external_positions[from_idx]
                    logger.debug("Bug2Fix: 외부 Nu/LG 가상 좌표 등록 from_idx=%d label='%s'",
                                 from_idx, from_label_lower)

            # ── Smart auto-detect if indices not specified ──
            if from_idx < -12 or (from_idx >= 0 and from_idx not in atom_positions):
                from_idx = self._auto_find_atom(
                    arrow.from_type, heteroatoms, charged_neg, charged_pos,
                    carbons, pi_bond_atoms, all_idxs, i, used_as="from",
                    frag_map=frag_map, frag_atoms=frag_atoms)

            if to_idx < 0 or to_idx not in atom_positions:
                # 다른 프래그먼트 원자 우선
                # Rule N: isinstance guard for frag_map
                if not isinstance(frag_map, dict): frag_map = {}
                from_frag = frag_map.get(from_idx, -1) if from_idx >= 0 else -1
                to_idx = self._auto_find_atom(
                    arrow.to_type, heteroatoms, charged_neg, charged_pos,
                    carbons, pi_bond_atoms, all_idxs, i, used_as="to",
                    exclude=from_idx if from_idx >= 0 else -1,
                    prefer_other_frag=from_frag,
                    frag_map=frag_map, frag_atoms=frag_atoms)

            if from_idx not in atom_positions or to_idx not in atom_positions:
                continue

            if from_idx == to_idx:
                continue

            start = QPointF(atom_positions[from_idx])
            end = QPointF(atom_positions[to_idx])

            # ── sigma bond: arrow starts at bond midpoint, not atom center ──
            # M632 ARROW-AUTO-001: R-MgBr C-Mg bond arrow was starting at C atom.
            # Fix: when from_type=="bond", find the bonded neighbor of from_idx
            # (not to_idx) and set start = midpoint(from_idx, neighbor).
            if arrow.from_type == "bond" and mol:
                try:
                    from_atom = mol.GetAtomWithIdx(from_idx)
                    for nbr in from_atom.GetNeighbors():
                        nbr_idx = nbr.GetIdx()
                        if nbr_idx != to_idx and nbr_idx in atom_positions:
                            nbr_pos = atom_positions[nbr_idx]
                            from_pos = atom_positions[from_idx]
                            start = QPointF(
                                (from_pos.x() + nbr_pos.x()) / 2,
                                (from_pos.y() + nbr_pos.y()) / 2,
                            )
                            break
                except Exception as e:
                    logger.warning("[reaction] arrow start calc fallback: %s", e)

            # ── Determine if inter-fragment or intra-fragment ──
            # Rule N: isinstance guard for frag_map
            if not isinstance(frag_map, dict): frag_map = {}
            from_frag = frag_map.get(from_idx, -1)
            to_frag = frag_map.get(to_idx, -1)
            is_inter_frag = (from_frag != to_frag and from_frag >= 0
                             and to_frag >= 0 and is_multi_frag)
            mechanism_type = (
                self._mechanism.mechanism_type
                if self._mechanism is not None and isinstance(self._mechanism.mechanism_type, str)
                else ""
            )
            is_br2_small_bond_arrow = (
                mechanism_type == "br2_anti_addition"
                and arrow.from_type in ("bond", "bond_center")
                and from_frag == to_frag
                and from_frag >= 0
            )

            # ── Intramolecular attack guard: 분자 내 공격 화살표는 원자 수 >= 5 필요 ──
            # CH₃-Br 같은 단순 분자에서는 분자 내 고리형 전이상태 불가
            # (최소 5원자 사슬이어야 환형 TS 가능 — Baldwin 규칙)
            if not is_inter_frag and from_frag >= 0 and from_frag < len(frag_atoms):
                frag_size = len(frag_atoms[from_frag])
                if frag_size < 5 and not is_br2_small_bond_arrow:
                    logger.debug(
                        "Skipping intramolecular arrow on small fragment "
                        "(size=%d < 5): from_idx=%d to_idx=%d",
                        frag_size, from_idx, to_idx)
                    continue

            # ── Inter-fragment arrow routing ──
            # 원자 위치 사용 (atom_positions에 있으면), bbox는 최후 수단
            if is_inter_frag:
                # M859: intermolecular mechanisms still need textbook electron
                # origins.  Pi/sigma arrows must start from the bond midpoint,
                # not from an atom center or from the step connector line.
                if arrow.from_type in ("bond", "pi_bond", "bond_center") and mol:
                    try:
                        from_atom = mol.GetAtomWithIdx(from_idx)
                        best_mid = None
                        best_dist = float("inf")
                        for nbr in from_atom.GetNeighbors():
                            nbr_idx = nbr.GetIdx()
                            if nbr_idx in atom_positions:
                                nbr_pos = atom_positions[nbr_idx]
                                from_pos = atom_positions[from_idx]
                                mid = QPointF(
                                    (from_pos.x() + nbr_pos.x()) / 2,
                                    (from_pos.y() + nbr_pos.y()) / 2,
                                )
                                d = math.sqrt((mid.x() - end.x()) ** 2 + (mid.y() - end.y()) ** 2)
                                if d < best_dist:
                                    best_dist = d
                                    best_mid = mid
                        if best_mid is not None:
                            start = best_mid
                    except Exception as e:
                        logger.warning("[M859] inter-fragment bond midpoint fallback: %s", e)
                elif arrow.from_type in ("lone_pair", "negative_charge"):
                    dx_tmp = end.x() - start.x()
                    dy_tmp = end.y() - start.y()
                    d_tmp = math.sqrt(dx_tmp * dx_tmp + dy_tmp * dy_tmp)
                    if d_tmp > 0:
                        start = QPointF(start.x() - dx_tmp / d_tmp * 10,
                                        start.y() - dy_tmp / d_tmp * 10)

                # 기본: atom_positions 그대로 사용. bbox 폴백은 atom이 없을 때만.
                if from_idx not in atom_positions or to_idx not in atom_positions:
                    if frag_pixel_bboxes:
                        src_bbox = frag_pixel_bboxes[from_frag] if from_frag < len(frag_pixel_bboxes) else None
                        tgt_bbox = frag_pixel_bboxes[to_frag] if to_frag < len(frag_pixel_bboxes) else None
                        if src_bbox and tgt_bbox:
                            src_cx = (src_bbox[0] + src_bbox[2]) / 2
                            tgt_cx = (tgt_bbox[0] + tgt_bbox[2]) / 2
                            if src_cx < tgt_cx:
                                start = QPointF(src_bbox[2], (src_bbox[1] + src_bbox[3]) / 2)
                                end = QPointF(tgt_bbox[0], (tgt_bbox[1] + tgt_bbox[3]) / 2)
                            else:
                                start = QPointF(src_bbox[0], (src_bbox[1] + src_bbox[3]) / 2)
                                end = QPointF(tgt_bbox[2], (tgt_bbox[1] + tgt_bbox[3]) / 2)
            else:
                # ── from_type에 따른 시작점 결정 ──
                # "bond" / "pi_bond": 결합의 중점에서 시작 (결합이 끊어지는 것)
                # "lone_pair": 론페어 위치에서 시작
                # "negative_charge": 음전하 위치에서 시작

                if arrow.from_type in ("bond", "pi_bond", "bond_center"):
                    if mol:
                        atom_obj = mol.GetAtomWithIdx(from_idx)
                        best_mid = None
                        best_dist_to_target = float('inf')
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
                            start = QPointF((start.x() + end.x()) / 2,
                                            (start.y() + end.y()) / 2)
                    else:
                        start = QPointF((start.x() + end.x()) / 2,
                                        (start.y() + end.y()) / 2)

                elif arrow.from_type == "lone_pair" and mol:
                    atom_obj = mol.GetAtomWithIdx(from_idx)
                    # Rule N: isinstance guard for atom_positions
                    if not isinstance(atom_positions, dict): atom_positions = {}
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
                        dx_tmp = end.x() - start.x()
                        dy_tmp = end.y() - start.y()
                        d_tmp = math.sqrt(dx_tmp * dx_tmp + dy_tmp * dy_tmp)
                        if d_tmp > 0:
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

            if is_br2_small_bond_arrow:
                # Make Br-Br sigma cleavage and bromonium ring-opening arrows
                # visible instead of hiding them on top of the black bond line.
                dx_tmp = end.x() - start.x()
                dy_tmp = end.y() - start.y()
                d_tmp = math.sqrt(dx_tmp * dx_tmp + dy_tmp * dy_tmp)
                if d_tmp > 0:
                    perp_x = -dy_tmp / d_tmp
                    perp_y = dx_tmp / d_tmp
                    offset = 20.0
                    start = QPointF(start.x() + perp_x * offset,
                                    start.y() + perp_y * offset)
                    end = QPointF(end.x() + perp_x * (offset + 10.0),
                                  end.y() + perp_y * (offset + 10.0))

            dx = end.x() - start.x()
            dy = end.y() - start.y()
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 3:
                continue

            # 끝점: 원자 라벨과 겹치지 않게 축소
            if is_inter_frag:
                # Inter-fragment: minimal shrink since we route from bbox edge
                shrink = 3
            else:
                shrink = 5 if arrow.to_type in ("bond",) else 8
            end = QPointF(end.x() - dx / dist * shrink, end.y() - dy / dist * shrink)

            # 시작점도 약간 축소
            if not is_inter_frag and arrow.from_type not in ("bond", "pi_bond", "bond_center"):
                s_dx = end.x() - start.x()
                s_dy = end.y() - start.y()
                s_dist = math.sqrt(s_dx * s_dx + s_dy * s_dy)
                if s_dist > 15:
                    start = QPointF(start.x() + s_dx / s_dist * 4,
                                    start.y() + s_dy / s_dist * 4)

            # ── Curvature and visual style based on inter/intra-fragment ──
            if is_inter_frag:
                # Inter-fragment: curved above fragments, thicker and readable.
                curv = 0.42 if (i % 2 == 0) else -0.42
                color = COLOR_ARROW
                width = 3.0  # inter-fragment는 굵게 (프래그먼트 간 화살표 강조)
            else:
                curv = arrow.curvature if hasattr(arrow, 'curvature') else 0.25
                # 같은 프래그먼트 내 화살표는 곡률 더 높게
                if from_frag == to_frag and from_frag >= 0:
                    curv = max(curv, 0.35)
                # 교과서 표준 곡률 방향: 화살표가 분자 중심에서 바깥으로 휘도록
                # cross product (arrow dir × center-to-start dir) 부호로 결정
                arrow_dx = end.x() - start.x()
                arrow_dy = end.y() - start.y()
                # 분자 렌더링 영역 중심
                mol_cx = mol_rect.x() + mol_rect.width() / 2
                mol_cy = mol_rect.y() + mol_rect.height() / 2
                # 화살표 중점에서 분자 중심 방향 벡터
                mid_x = (start.x() + end.x()) / 2
                mid_y = (start.y() + end.y()) / 2
                to_center_dx = mol_cx - mid_x
                to_center_dy = mol_cy - mid_y
                # cross product: 양이면 중심이 화살표 왼쪽 → 오른쪽(+)으로 볼록
                cross = arrow_dx * to_center_dy - arrow_dy * to_center_dx
                if abs(cross) > 1e-3:
                    # 분자 중심 반대쪽으로 볼록 (바깥으로 휨)
                    curv = abs(curv) if cross < 0 else -abs(curv)
                else:
                    # 중심과 일직선 — 위→아래면 음, 아래→위면 양 (기본)
                    curv = abs(curv) if start.y() > end.y() else -abs(curv)
                # 같은 두 원자 사이 여러 화살표 → 겹침 방지 교대
                if i > 0 and i < len(arrows):
                    prev = arrows[i - 1]
                    if (getattr(prev, 'from_atom_idx', -2) == from_idx and
                            getattr(prev, 'to_atom_idx', -2) == to_idx):
                        curv = -curv  # 동일 시작/끝 화살표만 교대
                color = COLOR_ARROW
                width = 2.2  # M473 DEFECT-V3: 2.0 → 2.2 (결합선 2.0px 대비 약간 두껍게)

            # color_override가 있으면 (이전 단계 회색 표시 등) 색상 덮어쓰기
            if is_br2_small_bond_arrow:
                curv = 0.65 if (i % 2 == 0) else -0.65
                width = 3.0

            if color_override is not None:
                color = color_override

            # 론페어/음전하 출발 화살표에 전자쌍 도트 표시
            is_lone_pair_origin = arrow.from_type in (
                "lone_pair", "negative_charge")

            if arrow.arrow_type == "full":
                CurvedArrowRenderer.draw_full_arrow(
                    painter, start, end, curvature=curv, color=color,
                    width=width, show_lone_pair=is_lone_pair_origin,
                    arrow_index=i)
            elif arrow.arrow_type == "retrosynthetic":
                CurvedArrowRenderer.draw_curved_retrosynthetic_arrow(
                    painter, start, end, curvature=curv, color=color,
                    width=width, arrow_index=i)
            else:
                CurvedArrowRenderer.draw_half_arrow(
                    painter, start, end, curvature=curv, color=color,
                    width=width, show_lone_pair=is_lone_pair_origin,
                    arrow_index=i)

            # 단계 번호 표시 (여러 화살표일 때 전자 흐름 순서 명확화)
            if len(arrows) > 1:
                ctrl_for_num, _, _, _, _ = CurvedArrowRenderer._calc_control_points(
                    start, end, curv, arrow_index=i)
                if ctrl_for_num is not None:
                    CurvedArrowRenderer.draw_step_number(
                        painter, start, end, ctrl_for_num,
                        step_num=i + 1, color=color)

    def _draw_br2_textbook_step1_overlay(self, painter: QPainter,
                                         atom_positions: Dict[int, QPointF],
                                         mol,
                                         color_override: Optional[QColor] = None) -> bool:
        """Draw alkene bromination step 1 with explicit inter-molecular arrows.

        Required textbook order:
        1. alkene pi bond attacks Br(delta+)
        2. Br-Br sigma bond cleaves to Br-
        3. the second alkene carbon closes the bromonium bridge.
        """
        try:
            alkene_bond = None
            br_bond = None
            for bond in mol.GetBonds():
                a = bond.GetBeginAtomIdx()
                b = bond.GetEndAtomIdx()
                if a not in atom_positions or b not in atom_positions:
                    continue
                sa = mol.GetAtomWithIdx(a).GetSymbol()
                sb = mol.GetAtomWithIdx(b).GetSymbol()
                if sa == "C" and sb == "C" and bond.GetBondTypeAsDouble() >= 1.8:
                    alkene_bond = (a, b)
                elif sa == "Br" and sb == "Br":
                    br_bond = (a, b)

            if alkene_bond is None or br_bond is None:
                return False

            c1, c2 = alkene_bond
            br1, br2 = br_bond
            p_c1 = atom_positions[c1]
            p_c2 = atom_positions[c2]
            p_br1 = atom_positions[br1]
            p_br2 = atom_positions[br2]
            c_mid = QPointF((p_c1.x() + p_c2.x()) / 2, (p_c1.y() + p_c2.y()) / 2)
            br_mid = QPointF((p_br1.x() + p_br2.x()) / 2, (p_br1.y() + p_br2.y()) / 2)

            def _dist(p: QPointF, q: QPointF) -> float:
                return math.hypot(p.x() - q.x(), p.y() - q.y())

            electrophile = br1 if _dist(p_br1, c_mid) <= _dist(p_br2, c_mid) else br2
            leaving = br2 if electrophile == br1 else br1
            p_e = atom_positions[electrophile]
            p_l = atom_positions[leaving]
            bridge_c = c2 if _dist(p_c1, p_e) <= _dist(p_c2, p_e) else c1
            p_bridge = atom_positions[bridge_c]

            ink = QColor(color_override) if color_override is not None else QColor(0, 0, 0)
            label_ink = QColor(color_override) if color_override is not None else QColor(35, 35, 35)

            def snap_point(p: QPointF) -> QPointF:
                # 12 px textbook grid snap: keeps arrows anchored to bond centers
                # instead of arbitrary decorative offsets.
                grid = 12.0
                return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)

            def draw_label_box(x: float, y: float, text: str, w: float = 126.0) -> None:
                x = max(6.0, x)
                rect = QRectF(x, y, w, 15.0)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 238)))
                painter.drawRoundedRect(rect, 3, 3)
                painter.setPen(label_ink)
                painter.drawText(rect.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignLeft, text)

            lane_gap = 34.0
            pi_start = snap_point(QPointF(c_mid.x() - 10, c_mid.y() - lane_gap))
            pi_end = snap_point(QPointF(p_e.x() - 18 if p_e.x() >= c_mid.x() else p_e.x() + 18,
                                        p_e.y() - lane_gap))
            CurvedArrowRenderer.draw_full_arrow(
                painter, pi_start, pi_end, curvature=0.28,
                color=ink, width=2.4, arrow_index=0)

            cleave_start = snap_point(QPointF(br_mid.x(), br_mid.y() - lane_gap - 10))
            cleave_dir = 1 if p_l.x() >= p_e.x() else -1
            cleave_end = snap_point(QPointF(p_l.x() + cleave_dir * 54, p_l.y() - lane_gap - 10))
            CurvedArrowRenderer.draw_full_arrow(
                painter, cleave_start, cleave_end, curvature=-0.24,
                color=ink, width=2.4, arrow_index=1)

            bridge_start = snap_point(QPointF(p_bridge.x() - 10, p_bridge.y() + lane_gap))
            bridge_end = snap_point(QPointF(p_e.x() - 10 if p_e.x() >= p_bridge.x() else p_e.x() + 10,
                                            p_e.y() + lane_gap - 4))
            CurvedArrowRenderer.draw_full_arrow(
                painter, bridge_start, bridge_end, curvature=-0.22,
                color=ink, width=2.2, arrow_index=2)

            painter.save()
            painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
            legend_x = max(8.0, min(p_c1.x(), p_c2.x(), p_e.x(), p_l.x()) - 10.0)
            legend_y = max(6.0, min(p_c1.y(), p_c2.y(), p_e.y(), p_l.y()) - 78.0)
            draw_label_box(legend_x, legend_y, "1 pi bond -> Br(+)", 148.0)
            draw_label_box(legend_x, legend_y + 17.0, "2 Br-Br -> Br(-)", 148.0)
            draw_label_box(legend_x, legend_y + 34.0, "3 bromonium closure", 162.0)
            painter.setFont(QFont("Malgun Gothic", 7))
            draw_label_box(legend_x, legend_y + 51.0,
                           "TS: C-Br forming / Br-Br breaking", 226.0)
            painter.restore()
            return True
        except Exception as exc:
            logger.warning("[br2_anti_addition] textbook step1 overlay failed: %s", exc)
            return False

    def _draw_br2_textbook_step2_overlay(self, painter: QPainter,
                                         atom_positions: Dict[int, QPointF],
                                         mol,
                                         color_override: Optional[QColor] = None) -> bool:
        """Draw bromonium ring opening as Br- backside attack plus C-Br cleavage."""
        try:
            br_plus = None
            br_minus = None
            for atom in mol.GetAtoms():
                idx = atom.GetIdx()
                if idx not in atom_positions or atom.GetSymbol() != "Br":
                    continue
                if atom.GetFormalCharge() > 0:
                    br_plus = idx
                elif atom.GetFormalCharge() < 0:
                    br_minus = idx

            if br_plus is None:
                for atom in mol.GetAtoms():
                    idx = atom.GetIdx()
                    if idx in atom_positions and atom.GetSymbol() == "Br":
                        carbon_neighbors = [n.GetIdx() for n in atom.GetNeighbors()
                                            if n.GetSymbol() == "C"]
                        if len(carbon_neighbors) >= 2:
                            br_plus = idx
                            break
            if br_minus is None:
                for atom in mol.GetAtoms():
                    idx = atom.GetIdx()
                    if idx in atom_positions and atom.GetSymbol() == "Br" and atom.GetDegree() == 0:
                        br_minus = idx
                        break
            if br_plus is None or br_minus is None:
                return False

            carbon_neighbors = [n.GetIdx() for n in mol.GetAtomWithIdx(br_plus).GetNeighbors()
                                if n.GetSymbol() == "C" and n.GetIdx() in atom_positions]
            if not carbon_neighbors:
                return False

            p_nuc = atom_positions[br_minus]
            p_brp = atom_positions[br_plus]

            def _dist_idx(idx: int) -> float:
                p = atom_positions[idx]
                return math.hypot(p.x() - p_nuc.x(), p.y() - p_nuc.y())

            target_c = min(carbon_neighbors, key=_dist_idx)
            p_target = atom_positions[target_c]
            bond_mid = QPointF((p_target.x() + p_brp.x()) / 2,
                               (p_target.y() + p_brp.y()) / 2)

            ink = QColor(color_override) if color_override is not None else QColor(0, 0, 0)
            label_ink = QColor(color_override) if color_override is not None else QColor(35, 35, 35)

            def snap_point(p: QPointF) -> QPointF:
                grid = 12.0
                return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)

            def draw_label_box(x: float, y: float, text: str, w: float = 150.0) -> None:
                x = max(6.0, x)
                rect = QRectF(x, y, w, 15.0)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 238)))
                painter.drawRoundedRect(rect, 3, 3)
                painter.setPen(label_ink)
                painter.drawText(rect.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignLeft, text)

            # Backside attack: start behind Br- and approach the carbon opposite
            # the bridging Br+.  The snapped points make the 180-degree SN2
            # relation legible instead of decorative.
            attack_start = snap_point(QPointF(p_nuc.x(), p_nuc.y() - 32))
            attack_end = snap_point(QPointF(p_target.x(), p_target.y() + 14))
            CurvedArrowRenderer.draw_full_arrow(
                painter, attack_start, attack_end, curvature=0.40,
                color=ink, width=2.4, arrow_index=0)

            open_start = snap_point(QPointF(bond_mid.x() - 10, bond_mid.y() - 28))
            open_end = snap_point(QPointF(p_brp.x() - 24, p_brp.y() - 38))
            CurvedArrowRenderer.draw_full_arrow(
                painter, open_start, open_end, curvature=-0.28,
                color=ink, width=2.4, arrow_index=1)

            painter.save()
            painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
            legend_x = max(8.0, min(p_nuc.x(), p_brp.x(), p_target.x()) - 18.0)
            legend_y = max(6.0, min(p_nuc.y(), p_brp.y(), p_target.y()) - 68.0)
            draw_label_box(legend_x, legend_y, "1 Br(-) backside attack", 180.0)
            draw_label_box(legend_x, legend_y + 17.0, "2 C-Br(+) bond opens", 174.0)
            painter.setFont(QFont("Malgun Gothic", 7))
            draw_label_box(legend_x, legend_y + 34.0,
                           "anti SN2-like ring opening", 190.0)
            painter.restore()
            return True
        except Exception as exc:
            logger.warning("[br2_anti_addition] textbook step2 overlay failed: %s", exc)
            return False

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
        # N-guard: validate external data types
        if frag_map is None or not isinstance(frag_map, dict):
            frag_map = {}
        if frag_atoms is None or not isinstance(frag_atoms, list):
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
        # Rule N: isinstance guard for frag_map
        if not isinstance(frag_map, dict):
            frag_map = {}
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

    # Rule GG SIMULATION_MODE 배너 색상 (HAL-001 P0 fix — M1458)
    _SIMULATION_BANNER_COLOR = QColor(0xFF, 0xCC, 0x00)  # #FFCC00 노랑

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []
        self._is_heuristic: bool = True  # HAL-001: True=경험적 추정, False=xtb/DFT 계산값
        self.setMinimumHeight(120)
        self.setMaximumHeight(200)

    def set_data(self, energy_diagram: List[Tuple[str, float]], is_heuristic: bool = True):
        """에너지 다이어그램 데이터 설정.

        Args:
            energy_diagram: [(라벨, 상대에너지 kcal/mol)] 목록
            is_heuristic: True=경험적 추정값(배너 표시), False=xTB/DFT 계산값
        """
        # N-guard: energy_diagram must be a list of tuples
        if not isinstance(energy_diagram, list):
            logger.warning("EnergyDiagramWidget.set_data: energy_diagram is not list (got %s)",
                           type(energy_diagram).__name__)
            self._data = []
            self._is_heuristic = True
            self.update()
            return
        self._data = energy_diagram
        self._is_heuristic = bool(is_heuristic)  # Rule N 타입 가드
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

                # Ea 라벨 — HAL-001: ≈ 기호로 경험적 추정임을 명시
                ea_val = ts_e - reactant_e
                painter.setFont(QFont("Malgun Gothic", 7, QFont.Weight.Bold))
                painter.setPen(QColor(200, 50, 50))
                ea_label_y = (ea_y_top + ea_y_bot) / 2
                ea_suffix = " (경험적)" if self._is_heuristic else ""
                painter.drawText(QRectF(ea_x + 4, ea_label_y - 7, 80, 14),
                                 Qt.AlignmentFlag.AlignLeft,
                                 f"Ea≈{ea_val:.0f}{ea_suffix}")  # ≈ = U+2248

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

                painter.setFont(QFont("Malgun Gothic", 7))
                painter.setPen(QColor(50, 120, 50))
                sign = "+" if delta_h > 0 else ""
                dh_label_y = (dh_y_r + dh_y_p) / 2
                # HAL-001: ≈ 기호로 경험적 추정임을 명시
                painter.drawText(QRectF(dh_x + 3, dh_label_y - 7, 60, 14),
                                 Qt.AlignmentFlag.AlignLeft,
                                 f"ΔH≈{sign}{delta_h:.0f}")  # ≈ = U+2248

        # ── 점 및 라벨 ──
        font = QFont("Malgun Gothic", 7)
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

        # Y축 라벨 — HAL-001 M1458: 추정/계산 구분 표시
        painter.setPen(QColor(120, 120, 120))
        painter.setFont(QFont("Malgun Gothic", 7))
        painter.save()
        painter.translate(14, h / 2)
        painter.rotate(-90)
        # 경험적 추정: "(추정, kcal/mol)", xtb/DFT 계산: "(GFN2-xTB, kcal/mol)"
        y_label = "에너지 (추정, kcal/mol)" if self._is_heuristic else "에너지 (GFN2-xTB, kcal/mol)"
        painter.drawText(QRectF(-60, -8, 120, 16),
                         Qt.AlignmentFlag.AlignCenter, y_label)
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

        # ── Rule GG SIMULATION_MODE 배너 (HAL-001 P0 fix — M1458) ──
        # xtb 미설치 / 경험적 추정값 사용 시 노랑 배너 표시.
        # xtb 설치 → compute_mechanism_energies 성공 → set_data(is_heuristic=False) → 배너 사라짐.
        if self._is_heuristic and self._data:
            _BANNER_H = 26  # px — 매직넘버: 두 줄 텍스트(font 6pt) 최소 높이
            banner_rect = QRectF(0, h - _BANNER_H, w, _BANNER_H)
            # 노랑 반투명 배경 (#FFCC00, alpha=200 — Rule GG)
            banner_color = QColor(self._SIMULATION_BANNER_COLOR)
            banner_color.setAlpha(200)  # alpha=200: 배경 보임 유지
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(banner_color))
            painter.drawRect(banner_rect)
            # 배너 텍스트 (2줄) — 어두운 갈색으로 노랑 위 가독성 확보
            painter.setPen(QColor(60, 40, 0))
            painter.setFont(QFont("Malgun Gothic", 6))
            painter.drawText(
                QRectF(4, h - _BANNER_H, w - 8, _BANNER_H / 2),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "활성화 에너지는 화살표 수 비례 경험적 추정값입니다.",
            )
            painter.drawText(
                QRectF(4, h - _BANNER_H / 2, w - 8, _BANNER_H / 2),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "xtb 설치 시 GFN2-xTB 계산값으로 개선됩니다.",
            )

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
        # N-guard: smiles must be str
        if not isinstance(smiles, str):
            logger.warning("MoleculeCardWidget.set_molecule: smiles is not str (got %s)",
                           type(smiles).__name__)
            smiles = str(smiles) if smiles is not None else ""
        self._smiles = smiles
        self._name = name if isinstance(name, str) else str(name) if name else ""
        self._border_color = border_color or QColor(0, 0, 0)
        if RDKIT_AVAILABLE and smiles:
            self._mol = Chem.MolFromSmiles(smiles)
            if self._mol is None:
                logger.warning("Invalid SMILES for molecule widget: %s", smiles)
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
            painter.setFont(QFont("Malgun Gothic", 9))
            painter.drawText(QRectF(5, 5, w - 10, h - 30),
                             Qt.AlignmentFlag.AlignCenter,
                             self._smiles or "분자 없음")

        # Name label
        if self._name:
            painter.setPen(COLOR_LABEL)
            painter.setFont(QFont("Malgun Gothic", 8))
            painter.drawText(QRectF(5, h - 22, w - 10, 18),
                             Qt.AlignmentFlag.AlignCenter, self._name)

        painter.end()


# ============================================================================
# OLLAMA REACTION HINT WORKER (M818 / D-M804-B12-FIX)
# ============================================================================
# 사용자 격분 #20 "반응분석까지 쳐 막아놨노" — 22초 GUI freeze fix.
#   - 이전(M769): popup_reaction._run_prediction() 안에서 requests.post timeout=20s 동기 호출.
#   - 신규(M818): QThread + urllib.request.urlopen(timeout=3.0) 비동기 worker.
#   - skill synthesis_timeout.md §10 GUI-THREAD-BLOCKING-REQUEST-001 + 신규 §11 AI-TIMEOUT-HEADLESS-002 적용.
#   - Rule MM/PP: Ollama 자동 라우팅 의무 유지 (호출 자체는 살림).
#   - Rule M: silent failure 금지 — hint_failed 시 사용자 안내 fallback.
# ============================================================================

class _OllamaReactionHintWorker(QThread):
    """반응 경로가 0건일 때 소형 Ollama 모델에 비동기로 힌트 조회.

    - GUI 메인스레드 절대 freeze 금지 (3s timeout, 별도 QThread).
    - HTTP 200 시 hint_ready emit, 실패 시 hint_failed emit.
    """

    hint_ready = pyqtSignal(str)
    hint_failed = pyqtSignal(str)

    # M818: 단축 timeout — 메인스레드 freeze 차단 의무 (skill §10 5s 이하 권고 더 강화)
    _OLLAMA_URL = "http://localhost:11434/api/generate"
    _OLLAMA_MODEL = "qwen2.5-coder:1.5b"
    _OLLAMA_TIMEOUT_SEC = 3.0  # 매직넘버 주석 (Rule I): 3s = GUI 응답성 한계 + Ollama 미가동 시 즉시 fallback

    def __init__(self, smiles_pair, parent=None):
        super().__init__(parent)
        # N-guard: 외부 데이터 isinstance() 체크 (Rule N)
        if not isinstance(smiles_pair, (list, tuple)):
            logger.warning("[M818] _OllamaReactionHintWorker: smiles_pair not list/tuple (got %s)",
                           type(smiles_pair).__name__)
            smiles_pair = []
        self._smiles_pair = list(smiles_pair)[:2]

    def run(self):
        """별도 스레드 실행 — 메인 GUI 영향 0."""
        import urllib.request
        import urllib.error
        import json as _json

        try:
            # 입력 가드 (Rule M silent failure 금지)
            if not self._smiles_pair or len(self._smiles_pair) < 2:
                self.hint_failed.emit("smiles_pair empty")
                return

            smi_a, smi_b = self._smiles_pair[0], self._smiles_pair[1]
            prompt = (
                f"두 분자 SMILES: {smi_a}, {smi_b}. "
                "유기화학 학생용으로 가능한 반응 유형 1~3개를 한국어 1줄씩 안내. "
                "확실하지 않으면 '작용기를 포함한 분자를 그려보세요'라고 답하라."
            )
            payload = {
                "model": self._OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 200},  # 짧게 (Ollama 응답 속도 우선)
            }
            data = _json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._OLLAMA_URL, data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self._OLLAMA_TIMEOUT_SEC) as r:
                if r.status != 200:
                    self.hint_failed.emit(f"HTTP {r.status}")
                    return
                body = _json.loads(r.read().decode("utf-8", errors="replace"))

            # N-guard: dict 검증 (Rule N)
            if not isinstance(body, dict):
                self.hint_failed.emit("non-dict response")
                return
            response_text = body.get("response", "")
            if not isinstance(response_text, str) or not response_text.strip():
                self.hint_failed.emit("empty response")
                return
            self.hint_ready.emit(response_text.strip())
        except urllib.error.URLError as e:
            # M818: Ollama 미가동/네트워크 차단 — silent return 금지 (Rule M)
            logger.warning("[M818] Ollama hint worker URLError: %s", e)
            self.hint_failed.emit(f"URLError: {e}")
        except Exception as e:  # noqa: BLE001 — Rule M: 모든 예외 사용자 피드백
            logger.warning("[M818] Ollama hint worker failed: %s", e)
            self.hint_failed.emit(f"{type(e).__name__}: {e}")


# ============================================================================
# MAIN REACTION POPUP
# ============================================================================

class ReactionPopup(QDialog):
    """유기합성반응 분석 팝업 — 교과서 스타일"""

    def __init__(self, smiles_list: List[str], names: List[str] = None,
                 parent=None):
        super().__init__(parent)
        global _KOREAN_FONT_FAMILY
        _KOREAN_FONT_FAMILY = _ensure_korean_font_loaded()
        self.setWindowTitle("유기합성반응 분석")
        self.setMinimumSize(1000, 750)
        self.resize(1100, 800)
        self.setStyleSheet("""
            QDialog { background: #FFFFFF; color: #222; font-family: "Malgun Gothic"; }
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
            QLabel { color: #333; font-family: "Malgun Gothic"; }
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

        # Auto-play timer: advances mechanism steps every 2000ms
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(2000)  # 2초 간격 자동 재생
        self._auto_timer.timeout.connect(self._autoplay_tick)
        self._is_autoplaying = False

        # 검색 필터: 리스트 행 → 실제 _pathways 인덱스 매핑
        self._filtered_indices: List[int] = []

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
        header.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
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
        rp_header.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        left_layout.addWidget(rp_header)

        # 검색 필터 입력창
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("반응 검색 (예: SN2, Diels, 치환...)")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setStyleSheet(
            "QLineEdit { background: #FAFAFA; color: #222; "
            "border: 1px solid #ccc; padding: 4px 8px; "
            "border-radius: 3px; font-size: 9pt; }"
            "QLineEdit:focus { border-color: #1565C0; }")
        self._search_edit.textChanged.connect(self._on_search_changed)
        left_layout.addWidget(self._search_edit)

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
        self.step_label.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        nav_bar.addWidget(self.step_label)

        self.btn_next = QPushButton("다음 ▶")
        self.btn_next.clicked.connect(self._next_step)
        self.btn_next.setEnabled(False)
        self.btn_next.setMaximumWidth(80)
        nav_bar.addWidget(self.btn_next)

        self._btn_autoplay = QPushButton("▶ 자동")
        self._btn_autoplay.clicked.connect(self._toggle_autoplay)
        self._btn_autoplay.setEnabled(False)
        self._btn_autoplay.setMaximumWidth(80)
        nav_bar.addWidget(self._btn_autoplay)

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
                # N-guard: predict() must return a list
                if not isinstance(pathways, list):
                    logger.warning("_run_prediction: predict() returned non-list (got %s)",
                                   type(pathways).__name__)
                    continue
                for pw in pathways:
                    key = (pw.mechanism_type, pw.name)
                    if key not in seen:
                        seen.add(key)
                        all_pathways.append(pw)

        self._pathways = sorted(all_pathways, key=lambda p: p.confidence, reverse=True)

        if not self._pathways:
            # [M816 D-M804-B12] 사용자 격분 #20 "반응분석까지 쳐 막아놨노" — 22초 GUI freeze fix.
            #   - 이전(M769): requests.post timeout=20s 동기 호출 → Ollama 미가동 시 메인스레드 22초 hang.
            #   - skill synthesis_timeout.md §8 AI-TIMEOUT-HEADLESS-001 + §7 RETROSYN-TIMEOUT-001 패턴 적용.
            #   - DeepSeek R1 audit_theory dispatch (D-M804-B12) 권고 C: HEADLESS guard + 3s timeout + QThread async.
            # Rule PP: Ollama 자동 라우팅 의무 유지 (호출 자체는 살림).
            # Rule M: silent failure 금지 — UI에 "분석 중..." 즉시 표시 후 worker 완료 시 갱신.
            self.reaction_list.addItem("감지된 반응 경로가 없습니다")
            self._filtered_indices = []

            if _HEADLESS_MODE:
                # offscreen/CI 모드: 외부 AI 호출 skip → 즉시 반환 (audit/test 가속)
                logger.warning("[M816 D-M804-B12] HEADLESS_MODE — Ollama 반응 힌트 skip")
                self.reaction_list.addItem("  작용기를 포함한 분자를 그려보세요")
                return

            # GUI 모드: 비동기 worker — 메인 스레드 절대 freeze 금지
            self.reaction_list.addItem("  AI 반응 힌트 조회 중... (Ollama)")
            self._ollama_hint_worker = _OllamaReactionHintWorker(
                self._smiles[:2], parent=self
            )
            self._ollama_hint_worker.hint_ready.connect(self._on_ollama_hint_ready)
            self._ollama_hint_worker.hint_failed.connect(self._on_ollama_hint_failed)
            self._ollama_hint_worker.finished.connect(self._ollama_hint_worker.deleteLater)
            self._ollama_hint_worker.start()
            return

        # 전체 경로 표시 (검색 필터 초기 상태 = 전체)
        self._populate_reaction_list()

    def _populate_reaction_list(self, filter_text: str = ""):
        """반응 목록을 필터 텍스트에 맞게 채우기.

        filter_text가 빈 문자열이면 전체 표시.
        검색어는 공백으로 분리하여 AND 조건 매칭 (카테고리, 이름, mechanism_type).
        """
        self.reaction_list.blockSignals(True)
        self.reaction_list.clear()
        self._filtered_indices = []

        keywords = filter_text.strip().lower().split() if filter_text.strip() else []

        for i, pw in enumerate(self._pathways):
            # 검색 대상 텍스트: 카테고리 + 이름 + mechanism_type
            searchable = f"{pw.category} {pw.name} {pw.mechanism_type}".lower()

            # 모든 키워드가 검색 대상에 포함되어야 매칭 (AND 조건)
            if keywords and not all(kw in searchable for kw in keywords):
                continue

            conf_pct = int(pw.confidence * 100)
            item = QListWidgetItem(f"[{pw.category}] {pw.name}  ({conf_pct}%)")
            self.reaction_list.addItem(item)
            self._filtered_indices.append(i)

        self.reaction_list.blockSignals(False)

        # 결과 카운트 표시
        total = len(self._pathways)
        shown = len(self._filtered_indices)
        if keywords:
            self._search_edit.setToolTip(
                f"{shown}/{total}개 반응 표시 중")
        else:
            self._search_edit.setToolTip(f"전체 {total}개 반응")

        # M450: 리스트에 항목이 있으면 첫 번째 항목 자동 선택 → _on_reaction_selected 트리거
        # blockSignals 해제 후 setCurrentRow(0) 호출 — 빈 우측 패널 방지 (Rule M silent failure 금지)
        if self._filtered_indices:
            logger.info(
                "M450-AUTO-SELECT: reaction_list 첫 항목 자동 선택 (%d개 중 1번)",
                len(self._filtered_indices),
            )
            self.reaction_list.setCurrentRow(0)

    def _on_search_changed(self, text: str):
        """검색 입력 변경 시 반응 목록 필터링."""
        if not self._pathways:
            return
        self._populate_reaction_list(text)

    # ------------------------------------------------------------------
    # Ollama 비동기 힌트 슬롯 (M818 / D-M804-B12-FIX)
    # ------------------------------------------------------------------
    def _remove_ollama_placeholder(self):
        """'AI 반응 힌트 조회 중...' placeholder 라인 제거."""
        try:
            for i in range(self.reaction_list.count() - 1, -1, -1):
                item = self.reaction_list.item(i)
                if item is None:
                    continue
                text = item.text() or ""
                if "AI 반응 힌트 조회 중" in text:
                    self.reaction_list.takeItem(i)
        except Exception as e:  # noqa: BLE001 — Rule M
            logger.warning("[M818] _remove_ollama_placeholder failed: %s", e)

    def _on_ollama_hint_ready(self, hint: str):
        """Ollama 힌트 응답 수신 — 메인스레드에서 호출됨."""
        # N-guard: hint must be str (Rule N)
        if not isinstance(hint, str):
            logger.warning("[M818] _on_ollama_hint_ready: hint not str (got %s)",
                           type(hint).__name__)
            self._on_ollama_hint_failed("non-str hint")
            return

        self._remove_ollama_placeholder()

        # 헤더
        header_item = QListWidgetItem("[AI 반응 힌트]")
        # 헤더 아이템 굵게 표시
        f = header_item.font()
        f.setBold(True)
        header_item.setFont(f)
        self.reaction_list.addItem(header_item)

        # 비공백 라인 6개까지만, 80자 truncate (Rule M 사용자 피드백)
        max_lines = 6  # 매직넘버 주석 (Rule I): UX — 너무 많은 라인은 가독성 저하
        max_chars = 80  # 매직넘버 주석 (Rule I): QListWidgetItem 가독 폭
        added = 0
        for line in hint.splitlines():
            if added >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            if len(line) > max_chars:
                line = line[: max_chars - 1] + "…"
            self.reaction_list.addItem(QListWidgetItem(f"  {line}"))
            added += 1

        if added == 0:
            # 응답이 모두 공백이었던 경우 — Rule M fallback
            self.reaction_list.addItem(
                QListWidgetItem("  작용기를 포함한 분자를 그려보세요"))

    def _on_ollama_hint_failed(self, err: str):
        """Ollama 호출 실패 — silent 금지, 사용자 안내 (Rule M)."""
        # N-guard
        if not isinstance(err, str):
            err = str(err)
        logger.warning("[M818] Ollama reaction hint failed: %s", err)

        self._remove_ollama_placeholder()
        # 사용자 안내 (학습 가이드) — silent return 금지 의무 (Rule M)
        self.reaction_list.addItem(
            QListWidgetItem("  작용기를 포함한 분자를 그려보세요"))

    def _on_reaction_selected(self, row):
        """반응 경로 선택 (필터링된 인덱스 매핑 사용)"""
        if row < 0 or row >= len(self._filtered_indices):
            return

        real_idx = self._filtered_indices[row]
        if real_idx < 0 or real_idx >= len(self._pathways):
            logger.warning(f"반응 목록 인덱스 범위 초과: row={row}, real_idx={real_idx}")
            return

        pw = self._pathways[real_idx]

        summary = self._predictor.get_reaction_summary(pw)
        self.reaction_info.setPlainText(summary)

        mech = get_mechanism(pw.mechanism_type)

        # M450: Gold standard 없으면 → 범용 엔진으로 자동 생성 시도
        # product_smiles 유무와 무관하게 fallback 시도 (Rule M silent failure 금지)
        if mech is None:
            logger.warning(
                "M450-FALLBACK: get_mechanism('%s') returned None → MechanismEngine fallback 시도",
                pw.mechanism_type,
            )
            try:
                from mechanism_engine import MechanismEngine
                engine = MechanismEngine()
                reactant_combined = ".".join(s for s in self._smiles if s)
                # product_smiles가 빈 문자열이면 reactant_combined를 임시 대입 (엔진이 mechanism_type_hint 기반으로 생성)
                product_smi = pw.product_smiles if pw.product_smiles else reactant_combined
                mech = engine.generate_mechanism(
                    reactant_smiles=reactant_combined,
                    product_smiles=product_smi,
                    mechanism_type_hint=pw.mechanism_type,
                )
                if mech:
                    logger.info("M450-FALLBACK: 범용 엔진 자동 생성 성공 → %s", pw.mechanism_type)
                else:
                    logger.warning(
                        "M450-FALLBACK: MechanismEngine도 None 반환 — mechanism_type=%s",
                        pw.mechanism_type,
                    )
            except Exception as e:
                logger.warning("M450-FALLBACK: 범용 메커니즘 엔진 오류 (mechanism_type=%s): %s",
                               pw.mechanism_type, e)

        if mech:
            self._current_mechanism = mech
            self._current_step_idx = 0
            # 전체 메커니즘을 한 번에 전달 (가로 레이아웃)
            self.scheme_widget.set_mechanism(mech, 0)
            self._update_nav()

            # xTB GFN2-xTB 에너지 프로파일 on-demand 계산
            # 실패 시 기존 하드코딩 energy_diagram 유지 (graceful fallback)
            xtb_diagram = None
            try:
                xtb_diagram = compute_mechanism_energies(mech)
            except Exception as e:
                logger.warning("xTB energy computation failed for '%s': %s",
                               mech.mechanism_type, e)

            if xtb_diagram is not None:
                # HAL-001 M1446: xtb 계산값 → is_heuristic=False (배너 숨김)
                self.energy_widget.set_data(xtb_diagram, is_heuristic=False)
                logger.info("에너지 다이어그램: xTB GFN2-xTB 계산값 사용 (%s)",
                            mech.mechanism_type)
            else:
                # HAL-001 M1446: 경험적 추정값 → is_heuristic=True (배너 표시)
                self.energy_widget.set_data(mech.energy_diagram, is_heuristic=True)
                logger.info("에너지 다이어그램: 하드코딩 추정값 사용 (%s)",
                            mech.mechanism_type)

            self.overall_desc.setText(mech.overall_description)
        else:
            # M450: gold standard + fallback 엔진 모두 실패 → 명확한 사용자 피드백 (Rule M)
            self._current_mechanism = None
            self.step_label.setText(
                f"메커니즘 데이터 없음 — {pw.name} ({pw.mechanism_type})"
            )
            logger.warning(
                "M450: 메커니즘 모두 실패 — mechanism_type=%s name=%s",
                pw.mechanism_type, pw.name,
            )
            # scheme_widget에 None 대신 mechanism_type 힌트를 담은 placeholder MechanismData 표시
            # → paintEvent에서 "반응 경로를 선택하세요" 대신 반응명 표시
            self.scheme_widget.set_mechanism(None)
            self.energy_widget.set_data([])
            self.overall_desc.setText(
                f"{pw.description}\n\n"
                f"[메커니즘 데이터 없음] {pw.name}에 대한 단계별 메커니즘이 아직 등록되지 않았습니다."
            )

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
        # Auto-play button: enable when mechanism has more than 1 step
        self._btn_autoplay.setEnabled(total > 1)

    def _update_mechanism_display(self):
        if not self._current_mechanism:
            return
        idx = self._current_step_idx
        self.scheme_widget.set_current_step(idx)
        self._update_nav()

    def _prev_step(self):
        # 수동 네비게이션 시 자동 재생 중지
        if self._is_autoplaying:
            self._stop_autoplay()
        if self._current_step_idx > 0:
            self._current_step_idx -= 1
            self._update_mechanism_display()

    def _next_step(self):
        # 수동 네비게이션 시 자동 재생 중지
        if self._is_autoplaying:
            self._stop_autoplay()
        if (self._current_mechanism and
                self._current_step_idx < self._current_mechanism.total_steps - 1):
            self._current_step_idx += 1
            self._update_mechanism_display()

    def _toggle_autoplay(self):
        """자동 재생 토글: ▶ 자동 ↔ ⏸ 정지"""
        if self._is_autoplaying:
            self._stop_autoplay()
        else:
            self._start_autoplay()

    def _start_autoplay(self):
        """자동 재생 시작"""
        if not self._current_mechanism:
            return
        # 이미 마지막 단계면 처음으로 되돌린 후 시작
        if self._current_step_idx >= self._current_mechanism.total_steps - 1:
            self._current_step_idx = 0
            self._update_mechanism_display()
        self._is_autoplaying = True
        self._btn_autoplay.setText("⏸ 정지")
        self._auto_timer.start()

    def _stop_autoplay(self):
        """자동 재생 정지"""
        self._auto_timer.stop()
        self._is_autoplaying = False
        self._btn_autoplay.setText("▶ 자동")

    def _autoplay_tick(self):
        """자동 재생 타이머 콜백: 다음 단계로 이동, 마지막이면 정지"""
        if not self._current_mechanism:
            self._stop_autoplay()
            return
        if self._current_step_idx < self._current_mechanism.total_steps - 1:
            self._current_step_idx += 1
            self._update_mechanism_display()
        # 마지막 단계 도달 시 자동 재생 정지
        if self._current_step_idx >= self._current_mechanism.total_steps - 1:
            self._stop_autoplay()
