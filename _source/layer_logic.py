# layer_logic.py (v3.0 - VSEPR Refactored + Formal Charge Display)
# Agent 03 (루이스 구조) + Agent 05 (렌더링 엔진) 공유 파일
# LewisRenderer: Agent 03 전담
# TheoryRenderer: Agent 05 전담 (수정 금지)

import logging
import math
from collections import deque

from PyQt6.QtGui import (QPainter, QColor, QFont, QPen, QPainterPath,
                          QFontMetrics, QBrush)
from PyQt6.QtCore import Qt, QPointF, QRectF
from rdkit import Chem  # 이론적 구조의 결합 타입 판별용

logger = logging.getLogger(__name__)


# ============================================================================
# 고리 감지 유틸리티 — 이중결합 짧은 선 방향 결정용
# ============================================================================

def _find_ring_containing_bond(k1, k2, adj):
    """
    k1-k2 결합을 포함하는 최소 고리의 원자 리스트를 반환.
    BFS로 k1→k2를 직접 연결하지 않고 우회하는 최단 경로를 탐색.

    Args:
        k1, k2: 결합 양 끝 원자의 좌표 튜플
        adj: {pos_tuple: [(neighbor_pos, bond_info), ...]} 인접 리스트

    Returns:
        list[tuple]: 고리를 구성하는 원자 좌표 리스트 (k1, ..., k2 순서)
        None: 고리가 아닌 경우
    """
    visited = {k1}
    queue = deque([(k1, [k1])])

    while queue:
        current, path = queue.popleft()

        for neighbor, _ in adj.get(current, []):
            # k1→k2 직접 결합은 제외 (우회 경로만 탐색)
            if current == k1 and neighbor == k2:
                continue

            if neighbor == k2:
                # 고리 발견! (k1 → ... → k2)
                return path + [k2]

            if neighbor not in visited and len(path) < 8:
                # 최대 8원자 고리까지 탐색 (성능 보장)
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return None  # 고리 아님


def _get_ring_center_direction(k1, k2, analysis):
    """
    이중결합(k1-k2)이 고리에 속하는 경우, 결합 중점에서 고리 중심을 향하는
    단위 벡터를 반환. 고리가 아니면 None.

    Args:
        k1, k2: 결합 양 끝 원자의 좌표 튜플
        analysis: 분석 딕셔너리 (adj, theory_data 포함)

    Returns:
        QPointF: 고리 중심 방향 단위 벡터
        None: 고리가 아닌 경우
    """
    adj = analysis.get("adj", {})
    t_map = analysis.get("theory_data", {}).get("map", {})

    ring_atoms = _find_ring_containing_bond(k1, k2, adj)
    if not ring_atoms:
        return None

    # 고리 중심점 계산
    ring_positions = []
    for atom_key in ring_atoms:
        pos = t_map.get(atom_key, QPointF(*atom_key))
        ring_positions.append(pos)

    center_x = sum(p.x() for p in ring_positions) / len(ring_positions)
    center_y = sum(p.y() for p in ring_positions) / len(ring_positions)
    ring_center = QPointF(round(center_x, 2), round(center_y, 2))

    # 결합 중점
    p1 = t_map.get(k1, QPointF(*k1))
    p2 = t_map.get(k2, QPointF(*k2))
    bond_mid = QPointF(round((p1.x() + p2.x()) / 2, 2),
                       round((p1.y() + p2.y()) / 2, 2))

    # 결합 중점 → 고리 중심 벡터
    to_center = ring_center - bond_mid
    dist = math.hypot(to_center.x(), to_center.y())
    if dist < 0.001:
        return None

    return to_center / dist  # 단위 벡터


# ============================================================================
# LewisRenderer — 루이스 구조 레이어 (Agent 03 전담)
# ============================================================================

class LewisRenderer:
    """
    루이스 구조 렌더러 v3.0
    - VSEPR 기반 빈 공간 탐색 알고리즘으로 H/LP 정확 배치
    - 형식전하(+/-) 렌더링 지원
    - 디버그 print 제거 → logging 사용
    """

    # --- 공통 상수 ---
    _FONT_FAMILY = "Arial"
    _FONT_SIZE_MAIN = 14       # 원자 기호
    _FONT_SIZE_H = 12          # 수소 기호
    _FONT_SIZE_CHARGE = 10     # 형식전하 기호
    _BOND_WIDTH = 2.2          # 결합선 두께
    _BOND_WIDTH_SELECTED = 2.8 # 선택 시 결합선 두께
    _GAP_MARGIN = 8            # 기호-결합선 여백 (px)
    _MIN_ANGLE_GAP = 30.0      # 최소 배치 각도 간격 (°)

    @staticmethod
    def get_bond_gap(pt_key, atoms_data):
        """
        결합선이 원소 기호로부터 떨어져야 하는 거리(px) 계산.
        기호 텍스트 크기의 절반 + 여백.
        """
        if pt_key not in atoms_data:
            return 0

        atom = atoms_data[pt_key]
        symbol = atom.get("main", "C")

        # 빈 문자열("") → 탄소로 간주
        if not symbol or symbol.strip() == "":
            symbol = "C"

        font = QFont(LewisRenderer._FONT_FAMILY,
                      LewisRenderer._FONT_SIZE_MAIN, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(symbol)
        text_height = fm.height()

        base_gap = max(text_width, text_height) / 2
        return base_gap + LewisRenderer._GAP_MARGIN

    @staticmethod
    def render(painter, atoms, bonds, analysis,
               selected_atoms=None, selected_bonds=None):
        """
        루이스 구조 메인 렌더 파이프라인
        Z-order: 결합선 → 원자기호 → H/LP → 형식전하
        """
        if not analysis:
            return

        logger.debug("LewisRenderer v3.0 activated")
        t_map = analysis.get("theory_data", {}).get("map", {})
        atoms_data = analysis.get("atoms", {})

        if selected_atoms is None:
            selected_atoms = set()
        if selected_bonds is None:
            selected_bonds = set()

        painter.save()

        # === STAGE 1: 결합선 렌더링 ===
        LewisRenderer._render_bonds(painter, analysis, t_map,
                                     atoms_data, selected_bonds)

        # === STAGE 2: 원자 기호 렌더링 ===
        LewisRenderer._render_atom_symbols(painter, analysis, t_map,
                                            selected_atoms)

        # === STAGE 3: 수소 + 비공유전자쌍 (VSEPR 배치) ===
        LewisRenderer._render_vsepr_extensions(painter, analysis, t_map)

        # === STAGE 4: 형식전하 표시 ===
        LewisRenderer._render_formal_charges(painter, analysis, t_map)

        painter.restore()
        logger.debug("LewisRenderer complete")

    # ------------------------------------------------------------------
    # STAGE 1: 결합선
    # ------------------------------------------------------------------
    @staticmethod
    def _render_bonds(painter, analysis, t_map, atoms_data, selected_bonds):
        """결합선 렌더링 (단일/이중/삼중, C=C 짧은 선 지원)"""
        for (k1, k2), v in analysis.get("bonds", {}).items():
            is_selected = ((k1, k2) in selected_bonds
                           or (k2, k1) in selected_bonds)
            color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            width = (LewisRenderer._BOND_WIDTH_SELECTED if is_selected
                     else LewisRenderer._BOND_WIDTH)
            painter.setPen(QPen(color, width))

            p1_orig = t_map.get(k1, QPointF(*k1))
            p2_orig = t_map.get(k2, QPointF(*k2))

            vec = p2_orig - p1_orig
            length = math.hypot(vec.x(), vec.y())
            if length == 0:
                continue

            unit = vec / length
            gap1 = LewisRenderer.get_bond_gap(k1, atoms_data)
            gap2 = LewisRenderer.get_bond_gap(k2, atoms_data)

            p1 = p1_orig + unit * gap1
            p2 = p2_orig - unit * gap2

            order = v if isinstance(v, int) else (2 if "DOUBLE" in str(v) else 1)

            # C=C 판별 (짧은 보조선 적용)
            elem1 = atoms_data.get(k1, {}).get("main", "C")
            elem2 = atoms_data.get(k2, {}).get("main", "C")
            is_cc = (elem1 in ("C", "") and elem2 in ("C", ""))

            # 단일 결합
            painter.drawLine(p1, p2)

            # 이중/삼중 결합 보조선
            if order >= 2:
                perp = QPointF(-vec.y(), vec.x()) / length * 4.5

                # 🔴 고리 내부 방향 감지: perp를 고리 중심 쪽으로 정렬
                ring_dir = _get_ring_center_direction(k1, k2, analysis)
                if ring_dir is not None:
                    dot = perp.x() * ring_dir.x() + perp.y() * ring_dir.y()
                    if dot < 0:
                        perp = QPointF(-perp.x(), -perp.y())

                if is_cc:
                    p1s = p1_orig + unit * (gap1 + 3)
                    p2s = p2_orig - unit * (gap2 + 3)
                    painter.drawLine(p1s + perp, p2s + perp)
                else:
                    painter.drawLine(p1 + perp, p2 + perp)

                if order == 3:
                    if is_cc:
                        p1s = p1_orig + unit * (gap1 + 3)
                        p2s = p2_orig - unit * (gap2 + 3)
                        painter.drawLine(p1s - perp, p2s - perp)
                    else:
                        painter.drawLine(p1 - perp, p2 - perp)

        logger.debug("Bonds rendered")

    # ------------------------------------------------------------------
    # STAGE 2: 원자 기호
    # ------------------------------------------------------------------
    @staticmethod
    def _get_charged_ring_atoms(analysis):
        """
        π 공명 시스템(방향족 고리)에 전하가 있을 때, 고리 전체 원자에 동일 색상 부여.
        
        규칙:
        - 전하가 있는 원자가 방향족 고리에 속하면 BFS로 연결된 모든 방향족 원자에 전하 색상 전파
        - 음이온 고리 → 적색계열 QColor(180, 0, 50)
        - 양이온 고리 → 청색계열 QColor(0, 80, 200)
        - 방향족이 아닌 원자는 해당 원자만 색상 변경
        
        Returns:
            dict {atom_key: QColor}: 색상 매핑 (전하 없는 원자는 포함 안됨)
        """
        result = {}
        atoms_data = analysis.get("atoms", {})
        aromatic_atoms = analysis.get("aromatic", set())
        adj = analysis.get("adj", {})

        # 전하 있는 원자 수집
        charged = {}
        for pt_key, atom_data in atoms_data.items():
            fc = atom_data.get("formal_charge", 0)
            if fc == 0:
                _cf = atom_data.get("charge", "")
                if _cf == "+": fc = 1
                elif _cf == "-": fc = -1
            if fc != 0:
                charged[pt_key] = fc

        for charged_key, charge_val in charged.items():
            color = QColor(0, 80, 200) if charge_val > 0 else QColor(180, 0, 50)

            if charged_key in aromatic_atoms:
                # BFS: 연결된 방향족 원자 전체 탐색
                visited = set()
                queue = deque([charged_key])
                while queue:
                    current = queue.popleft()
                    if current in visited:
                        continue
                    visited.add(current)
                    if current in aromatic_atoms:
                        result[current] = color
                        for neighbor, _ in adj.get(current, []):
                            if neighbor not in visited and neighbor in aromatic_atoms:
                                queue.append(neighbor)
            else:
                # 비방향족: 해당 원자만
                result[charged_key] = color

        return result

    @staticmethod
    def _render_atom_symbols(painter, analysis, t_map, selected_atoms):
        """
        원자 기호 렌더링 (모든 원소 표시, 선택 시 파란색 하이라이트)
        [Fix v3] π 고리에 전하가 있으면 고리 전체 동일 색상 (비편재화)
        """
        # π 비편재화 색상 맵 사전 계산
        charged_color_map = LewisRenderer._get_charged_ring_atoms(analysis)

        for pt_key, atom_data in analysis["atoms"].items():
            symbol = atom_data.get("main", "C")
            if not symbol or symbol.strip() == "":
                symbol = "C"

            center = t_map.get(pt_key, QPointF(*pt_key))
            is_selected = pt_key in selected_atoms

            # [Fix v3] 전하 비편재화 색상 우선 적용
            if is_selected:
                atom_color = Qt.GlobalColor.blue
            elif pt_key in charged_color_map:
                atom_color = charged_color_map[pt_key]
            else:
                atom_color = Qt.GlobalColor.black

            painter.setFont(QFont(LewisRenderer._FONT_FAMILY,
                                   LewisRenderer._FONT_SIZE_MAIN,
                                   QFont.Weight.Bold))
            painter.setPen(atom_color)
            fm = QFontMetrics(painter.font())
            tw = fm.horizontalAdvance(symbol)
            th = fm.height()

            text_rect = QRectF(center.x() - tw / 2, center.y() - th / 2,
                               tw, th)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, symbol)

            if is_selected:
                painter.setPen(QPen(Qt.GlobalColor.blue, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(center.x() - tw / 2 - 3,
                                        center.y() - th / 2 - 2,
                                        tw + 6, th + 4))

        logger.debug("Atom symbols rendered")

    # ------------------------------------------------------------------
    # STAGE 3: VSEPR 기반 수소 + 비공유전자쌍 배치
    # ------------------------------------------------------------------
    @staticmethod
    def _render_vsepr_extensions(painter, analysis, t_map):
        """모든 원자에 대해 VSEPR 기반 H/LP 배치"""
        atoms_data = analysis.get("atoms", {})
        aromatic_set = analysis.get("aromatic", set())
        for pt_key, atom_data in atoms_data.items():
            h_count = atom_data.get("h_count", 0)
            lp_count = atom_data.get("lp_count", 0)

            # [Fix v3.2] 방향족 탄소 이온: LP 표시 안함
            # 음이온(C⁻) 탄소의 '외견상 비공유전자쌍'은 실제로 방향족 π 시스템에 비편재화됨.
            # LP 두 점 표시는 화학적으로 잘못된 표현 → lp_count=0 처리
            symbol = atom_data.get("main", "C") or "C"
            user_charge = atom_data.get("charge", "")
            formal_charge = atom_data.get("formal_charge", 0)
            if symbol == "C" and pt_key in aromatic_set and (user_charge or formal_charge != 0):
                lp_count = 0  # 방향족 이온 탄소: π 전자는 LP가 아닌 비편재화 전자

            if h_count + lp_count == 0:
                continue
            LewisRenderer._draw_vsepr_extensions(
                painter, pt_key, atom_data, analysis, t_map,
                lp_count_override=lp_count)

    @staticmethod
    def _draw_vsepr_extensions(painter, pos_tuple, data, analysis, t_map,
                                lp_count_override=None):
        """
        VSEPR 기반 수소 및 비공유전자쌍 배치 v3.0

        개선사항 (v2.0 → v3.0):
        - 기존 결합 사이의 빈 각도 구간(gap)을 탐색하여 정확 배치
        - 기존 결합과 겹치지 않도록 보장
        - 전하 유무와 관계없이 RDKit h_count를 신뢰
        [Fix v3 수소 도구] attach dict에 사용자가 직접 배치한 H 수를 h_count에서 차감
        → 수소 도구로 붙인 H와 VSEPR 자동 H가 중복 표시되는 문제 해결
        [Fix v3.2] lp_count_override: 방향족 이온 탄소의 LP 수를 외부에서 강제 지정
        """
        center = t_map.get(pos_tuple, QPointF(*pos_tuple))
        adj_info = analysis.get("adj", {}).get(pos_tuple, [])

        # [STEP 1] 기존 결합 방향 각도 수집
        occupied_angles = []
        for neighbor_pos, _ in adj_info:
            neighbor_center = t_map.get(neighbor_pos, QPointF(*neighbor_pos))
            vec = neighbor_center - center
            mag = math.hypot(vec.x(), vec.y())
            if mag > 0:
                angle = math.degrees(math.atan2(vec.y(), vec.x()))
                occupied_angles.append(angle)

        # [STEP 2] 수소와 비공유전자쌍 개수
        # [Fix v3] 사용자가 attach로 이미 배치한 H 수 차감 (중복 렌더링 방지)
        user_placed_h = sum(1 for sym in data.get("attach", {}).values() if sym == "H")
        h_count = max(0, data.get("h_count", 0) - user_placed_h)
        # [Fix v3.2] lp_count_override 우선 적용 (방향족 이온 탄소: LP=0)
        lp_count = lp_count_override if lp_count_override is not None else data.get("lp_count", 0)
        total_extensions = h_count + lp_count
        if total_extensions == 0:
            return

        total_groups = len(occupied_angles) + total_extensions

        # [STEP 3] 빈 공간 탐색 후 최적 각도 계산
        placement_angles = LewisRenderer._find_available_angles(
            occupied_angles, total_extensions, total_groups)

        # [STEP 4] 기호 크기 기반 동적 gap 계산
        symbol = data.get("main", "C")
        if not symbol or symbol.strip() == "":
            symbol = "C"
        font = QFont(LewisRenderer._FONT_FAMILY,
                      LewisRenderer._FONT_SIZE_MAIN, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        sym_half = max(fm.horizontalAdvance(symbol), fm.height()) / 2
        base_gap = sym_half + LewisRenderer._GAP_MARGIN

        # [STEP 5] 수소 우선 배치, 이후 비공유전자쌍
        for i, angle_deg in enumerate(placement_angles):
            rad = math.radians(angle_deg)
            direction = QPointF(math.cos(rad), math.sin(rad))

            if i < h_count:
                LewisRenderer._draw_h_bond(painter, center, direction,
                                            gap=base_gap)
            else:
                LewisRenderer._draw_lone_pair(painter, center, direction,
                                               gap=base_gap + 4)

    @staticmethod
    def _find_available_angles(occupied_angles, num_to_place, total_groups):
        """
        기존 결합 각도 사이의 빈 공간에 확장 요소(H, LP)를 최적 배치.

        알고리즘:
        1. 기존 결합 각도를 [0°, 360°) 범위로 정규화 후 정렬
        2. 인접 결합 사이의 빈 각도 구간(gap) 크기 계산
        3. 가장 큰 gap부터 확장 요소 배분 (gap 내 균등 분할)
        4. 최소 각도 간격(30°) 보장

        Args:
            occupied_angles: 기존 결합 방향 각도 리스트 (°)
            num_to_place: 배치할 확장 요소 수 (H + LP)
            total_groups: 전체 그룹 수 (기존 결합 + 확장 요소)

        Returns:
            배치할 각도 리스트 (°)
        """
        if num_to_place == 0:
            return []

        if not occupied_angles:
            # 결합이 없으면 위쪽(-90°)부터 균등 배치
            step = 360.0 / max(total_groups, 1)
            return [-90 + i * step for i in range(num_to_place)]

        # [1] 정규화 및 정렬
        normed = sorted([(a % 360) for a in occupied_angles])
        n_occ = len(normed)

        # [2] 인접 결합 사이 gap 계산
        gaps = []
        for i in range(n_occ):
            a_start = normed[i]
            a_end = normed[(i + 1) % n_occ]
            gap_size = (a_end - a_start) % 360
            if gap_size == 0:
                gap_size = 360.0  # 결합 1개 → 나머지 360° 전부 빈 공간
            gaps.append((gap_size, a_start))

        # [3] gap 크기순 정렬 (큰 것 우선)
        gaps.sort(key=lambda g: g[0], reverse=True)

        # [4] 이상적 간격 (VSEPR 기하)
        ideal_spacing = 360.0 / max(total_groups, 1)

        # [5] 각 gap에 배치할 개수 분배
        result = []
        remaining = num_to_place

        for gap_size, start_a in gaps:
            if remaining <= 0:
                break

            # 이 gap에 넣을 수 있는 최대 개수
            fit = max(1, round(gap_size / ideal_spacing))
            to_place = min(fit, remaining)

            # gap 내 균등 분할
            for j in range(to_place):
                angle = start_a + gap_size * (j + 1) / (to_place + 1)
                result.append(angle % 360)

            remaining -= to_place

        # [6] Fallback: 남은 요소가 있으면 가장 큰 gap 중앙에 배치
        if remaining > 0 and gaps:
            gap_size, start_a = gaps[0]
            placed_in_gap = len(result)
            for j in range(remaining):
                angle = start_a + gap_size * (placed_in_gap + j + 1) / (placed_in_gap + remaining + 1)
                result.append(angle % 360)

        return result[:num_to_place]

    # ------------------------------------------------------------------
    # STAGE 4: 형식전하 표시
    # ------------------------------------------------------------------
    @staticmethod
    def _render_formal_charges(painter, analysis, t_map):
        """
        형식전하(+/-) 렌더링 — 원자 기호 우상단에 ChemGrid 스타일로 표시.
        예: N⁺, O⁻
        """
        atoms_data = analysis.get("atoms", {})
        for pt_key, atom_data in atoms_data.items():
            formal_charge = atom_data.get("formal_charge", 0)
            # [Fix v2] charge 필드 fallback (lewis_data 주입 전 상태에서도 동작)
            if formal_charge == 0:
                _cf3 = atom_data.get("charge", "")
                if _cf3 == "+": formal_charge = 1
                elif _cf3 == "-": formal_charge = -1
            if formal_charge == 0:
                continue

            center = t_map.get(pt_key, QPointF(*pt_key))

            # 원자 기호 크기 계산 (우상단 오프셋용)
            symbol = atom_data.get("main", "C")
            if not symbol or symbol.strip() == "":
                symbol = "C"

            main_font = QFont(LewisRenderer._FONT_FAMILY,
                               LewisRenderer._FONT_SIZE_MAIN,
                               QFont.Weight.Bold)
            main_fm = QFontMetrics(main_font)
            sym_w = main_fm.horizontalAdvance(symbol)
            sym_h = main_fm.height()

            # [Fix v2] 전하 기호는 검은색 위첨자 (원자색이 이미 전하 상태 표시)
            charge_text = "+" if formal_charge > 0 else "−"  # U+2212

            # 우상단 오프셋
            charge_font = QFont(LewisRenderer._FONT_FAMILY,
                                 LewisRenderer._FONT_SIZE_CHARGE,
                                 QFont.Weight.Bold)
            painter.setFont(charge_font)
            painter.setPen(Qt.GlobalColor.black)  # [Fix v2] 검은색
            cfm = QFontMetrics(charge_font)
            cw = cfm.horizontalAdvance(charge_text)
            ch = cfm.height()

            # 원자 기호의 우상단에 배치
            cx = center.x() + sym_w / 2 + 1
            cy = center.y() - sym_h / 2 - 1

            charge_rect = QRectF(cx, cy, cw, ch)
            painter.drawText(charge_rect, Qt.AlignmentFlag.AlignCenter,
                             charge_text)

        logger.debug("Formal charges rendered")

    # ------------------------------------------------------------------
    # 개별 요소 렌더링
    # ------------------------------------------------------------------
    @staticmethod
    def _draw_lone_pair(painter, center, direction, gap=22):
        """
        비공유 전자쌍(..) 렌더링 — ChemGrid 스타일 두 점.

        Args:
            center: 원자 중심 좌표
            direction: 방향 단위 벡터
            gap: 원자 중심으로부터의 거리 (px)
        """
        painter.save()

        pos = center + direction * gap

        # 수직 방향 벡터 (두 점을 좌우로 배치)
        perp = QPointF(-direction.y(), direction.x()) * 3.5

        painter.setBrush(Qt.GlobalColor.black)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(pos + perp, 2.5, 2.5)
        painter.drawEllipse(pos - perp, 2.5, 2.5)

        painter.restore()

    @staticmethod
    def _draw_h_bond(painter, center, direction, gap=18):
        """
        수소 결합선 + H 기호 렌더링 — ChemGrid 스타일.

        Args:
            center: 원자 중심 좌표
            direction: 방향 단위 벡터
            gap: 결합선 시작 거리 (px, 기호 가장자리)
        """
        # 결합선 시작/끝점
        start = center + direction * gap
        end = center + direction * (gap + 20)

        # 결합선
        painter.setPen(QPen(Qt.GlobalColor.black, 2.0))
        painter.drawLine(start, end)

        # H 기호 위치
        h_pos = end + direction * 10

        painter.setFont(QFont(LewisRenderer._FONT_FAMILY,
                               LewisRenderer._FONT_SIZE_H,
                               QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.black)
        fm = QFontMetrics(painter.font())
        tw = fm.horizontalAdvance("H")
        th = fm.height()

        text_rect = QRectF(h_pos.x() - tw / 2, h_pos.y() - th / 2, tw, th)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "H")


# ============================================================================
# TheoryRenderer — 이론적 구조 레이어 (Agent 05 전담, 수정 금지)
# ============================================================================

class TheoryRenderer:
    @staticmethod
    def get_bond_gap(pt_key, atoms_data):
        """
        결합선이 원소 기호로부터 얼마나 떨어져야 하는지 계산
        Theory 레이어에서는 비탄소 원소만 표시
        """
        if pt_key not in atoms_data:
            return 0
        
        atom = atoms_data[pt_key]
        symbol = atom.get("main", "C")
        
        # 원소 기호가 있고 C가 아닌 경우 (Theory는 비탄소만 표시)
        if symbol and symbol.strip() and symbol != "C":
            font = QFont("Arial", 14, QFont.Weight.Bold)
            fm = QFontMetrics(font)
            text_width = fm.horizontalAdvance(symbol)
            text_height = fm.height()
            
            # 텍스트 크기의 절반 + 넉넉한 여백 (수소처럼 명확한 간격)
            base_gap = max(text_width, text_height) / 2
            return base_gap + 8  # 여백을 더 크게
        
        return 0
    
    @staticmethod
    def render(painter, atoms, bonds, analysis, selected_atoms=None, selected_bonds=None):
        """
        [Step 4 개선] 이론적 구조 레이어: MMFF94 최적 좌표 + 원소 표기 + 입체 표현
        - 선택 표시: 파란색 하이라이트
        """
        t_data = analysis.get("theory_data")
        if not t_data: return

        painter.save()
        painter.setOpacity(1.0)
        
        coords = t_data["coords"]
        t_map = t_data.get("map", {})
        atoms_data = analysis.get("atoms", {})
        
        # [신규] 선택 표시를 위한 기본값 설정
        if selected_atoms is None:
            selected_atoms = set()
        if selected_bonds is None:
            selected_bonds = set()
        
        # === STAGE 1: 결합선 렌더링 (웨지/대쉬 포함, 간격 적용) ===
        for (k1, k2), v in bonds.items():
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = (k1, k2) in selected_bonds or (k2, k1) in selected_bonds
            line_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            # [TASK 1] 선 두께 정규화: Drawing 레이어와 동일하게 2.2
            line_width = 2.8 if is_selected else 2.2
            painter.setPen(QPen(line_color, line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            # 이론적 좌표 사용
            p1_orig = t_map.get(k1, QPointF(*k1))
            p2_orig = t_map.get(k2, QPointF(*k2))
            
            # 방향 벡터 계산
            vec = p2_orig - p1_orig
            length = math.hypot(vec.x(), vec.y())
            if length == 0:
                continue
            
            unit = vec / length
            
            # 각 원소에서의 간격 계산
            gap1 = TheoryRenderer.get_bond_gap(k1, atoms_data)
            gap2 = TheoryRenderer.get_bond_gap(k2, atoms_data)
            
            # 간격을 적용한 시작점과 끝점
            p1 = p1_orig + unit * gap1
            p2 = p2_orig - unit * gap2
            
            # 결합 타입 판별
            if isinstance(v, tuple) and len(v) >= 3:
                # 웨지/대쉬 입체 결합
                bond_mode = v[2]
                if bond_mode == "Wedge":
                    # 웨지 (채워진 삼각형)
                    perp = QPointF(-vec.y(), vec.x()) / length * 5
                    painter.setBrush(painter.pen().color())
                    from PyQt6.QtGui import QPolygonF
                    poly = QPolygonF([p1, p2 + perp, p2 - perp])
                    painter.drawPolygon(poly)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                elif bond_mode == "Dash":
                    # 대쉬 (계단식 바코드)
                    perp = QPointF(-vec.y(), vec.x()) / length
                    for i in range(8):
                        f = i / 7.0
                        w = i * 0.8
                        ps = p1 + (p2 - p1) * f
                        painter.drawLine(ps + perp * w, ps - perp * w)
                else:
                    painter.drawLine(p1, p2)
            else:
                # 일반 결합
                order = v if isinstance(v, int) else 1

                # [TASK 1] 지능형 Offset: C=C만 짧은 선 적용
                elem1 = atoms_data.get(k1, {}).get("main", "C")
                elem2 = atoms_data.get(k2, {}).get("main", "C")
                is_cc_bond = (elem1 in ["C", ""] and elem2 in ["C", ""])

                painter.drawLine(p1, p2)

                # 다중 결합
                if order >= 2:
                    perp = QPointF(-vec.y(), vec.x()) / length * 4.5

                    # 🔴 고리 내부 방향 감지: perp를 고리 중심 쪽으로 정렬
                    ring_dir = _get_ring_center_direction(k1, k2, analysis)
                    if ring_dir is not None:
                        dot = perp.x() * ring_dir.x() + perp.y() * ring_dir.y()
                        if dot < 0:
                            perp = QPointF(-perp.x(), -perp.y())

                    if is_cc_bond:
                        # C=C: 한쪽 선을 짧게
                        p1_short = p1_orig + unit * (gap1 + 3)
                        p2_short = p2_orig - unit * (gap2 + 3)
                        painter.drawLine(p1_short + perp, p2_short + perp)
                    else:
                        # N=O, C=N: 평행선 (간격 적용)
                        painter.drawLine(p1 + perp, p2 + perp)

                    if order == 3:
                        if is_cc_bond:
                            p1_short = p1_orig + unit * (gap1 + 3)
                            p2_short = p2_orig - unit * (gap2 + 3)
                            painter.drawLine(p1_short - perp, p2_short - perp)
                        else:
                            painter.drawLine(p1 - perp, p2 - perp)
        
        # === STAGE 2: 원소 기호 렌더링 (비탄소만, 테두리 없이, 선택 표시 포함) ===
        for pt_key, atom_data in analysis.get("atoms", {}).items():
            symbol = atom_data.get("main", "C")
            if not symbol or symbol.strip() == "" or symbol == "C":
                continue  # 탄소는 생략
            
            center = t_map.get(pt_key, QPointF(*pt_key))
            
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = pt_key in selected_atoms
            atom_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            
            # 기호 그리기 (선택 시 파란색, 미선택 시 검은색)
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.setPen(atom_color)
            fm = QFontMetrics(painter.font())
            text_w = fm.horizontalAdvance(symbol)
            text_h = fm.height()
            
            text_rect = QRectF(center.x() - text_w/2, center.y() - text_h/2, text_w, text_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, symbol)
            
            # [신규] 선택된 원자에 파란색 테두리 추가
            if is_selected:
                painter.setPen(QPen(Qt.GlobalColor.blue, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(center.x() - text_w/2 - 3, center.y() - text_h/2 - 2, text_w + 6, text_h + 4))

        # === STAGE 3: 전하/라디칼/비공유전자쌍 기호 표시 (원자색 변경 없이 기호만) ===
        # [Fix v3] 탄소 기호 미표시 유지, 전하/라디칼/LP만 골격 옆에 검은색으로 표시
        charge_font = QFont("Arial", 10, QFont.Weight.Bold)
        lp_font = QFont("Arial", 8, QFont.Weight.Bold)

        for pt_key, atom_data in analysis.get("atoms", {}).items():
            center = t_map.get(pt_key, QPointF(*pt_key))

            # --- 3-A: 형식전하 (+/-) 기호 표시 ---
            formal_charge = atom_data.get("formal_charge", 0)
            if formal_charge == 0:
                _cf = atom_data.get("charge", "")
                if _cf == "+":
                    formal_charge = 1
                elif _cf == "-":
                    formal_charge = -1

            if formal_charge != 0:
                charge_text = "+" if formal_charge > 0 else "−"
                painter.setFont(charge_font)
                painter.setPen(Qt.GlobalColor.black)
                cfm = QFontMetrics(charge_font)
                # 원자 오른쪽 위에 표시 (탄소는 기호 없으므로 소폭 오프셋)
                symbol = atom_data.get("main", "C") or "C"
                main_fm = QFontMetrics(QFont("Arial", 14, QFont.Weight.Bold))
                sym_w = main_fm.horizontalAdvance(symbol) if symbol != "C" else 6
                cx = center.x() + sym_w / 2 + 2
                cy = center.y() - 10
                painter.drawText(QPointF(cx, cy), charge_text)

            # --- 3-B: 비공유전자쌍 (..) 표시 (음이온 원자 주변) ---
            # [Fix v3.2] 방향족 탄소 이온: LP 표시 안함 (π 비편재화)
            lp_count = atom_data.get("lp_count", 0)
            _sym_t = atom_data.get("main", "C") or "C"
            _uc_t = atom_data.get("charge", "")
            _fc_t = atom_data.get("formal_charge", 0)
            if (_sym_t == "C" and pt_key in analysis.get("aromatic", set())
                    and (_uc_t or _fc_t != 0)):
                lp_count = 0
            if lp_count > 0:
                # 기존 결합 방향 수집 (배치 위치 계산용)
                adj_info = analysis.get("adj", {}).get(pt_key, [])
                occupied_angles = []
                for neighbor_pos, _ in adj_info:
                    nb_center = t_map.get(neighbor_pos, QPointF(*neighbor_pos))
                    vec = nb_center - center
                    mag = math.hypot(vec.x(), vec.y())
                    if mag > 0:
                        angle = math.degrees(math.atan2(vec.y(), vec.x()))
                        occupied_angles.append(angle)

                # 가장 빈 방향 찾기 (결합 반대 방향 우선)
                if occupied_angles:
                    avg_angle = sum(occupied_angles) / len(occupied_angles)
                    lp_angle = (avg_angle + 180) % 360
                else:
                    lp_angle = 270  # 기본: 위쪽

                rad = math.radians(lp_angle)
                lp_dist = 20
                lp_pos = QPointF(center.x() + math.cos(rad) * lp_dist,
                                 center.y() + math.sin(rad) * lp_dist)

                perp = QPointF(-math.sin(rad), math.cos(rad)) * 3.5
                painter.setBrush(Qt.GlobalColor.black)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(lp_pos + perp, 2.0, 2.0)
                painter.drawEllipse(lp_pos - perp, 2.0, 2.0)

            # --- 3-C: 라디칼 도트 (·) 표시 ---
            attach = atom_data.get("attach", {})
            for d, sym in attach.items():
                if sym != "·":
                    continue
                ang = math.radians(d * 60) if d != -1 else 0
                dist = 22
                rx = center.x() + math.cos(ang) * dist
                ry = center.y() + math.sin(ang) * dist
                painter.setBrush(Qt.GlobalColor.black)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(rx, ry), 2.5, 2.5)

        painter.restore()


# ============================================================================
# TransitionEffect — 원형 확장 클리핑 (공유)
# ============================================================================

class TransitionEffect:
    @staticmethod
    def apply_circular_reveal(painter, radius, center_pt):
        path = QPainterPath()
        path.addEllipse(center_pt, radius, radius)
        painter.setClipPath(path)
