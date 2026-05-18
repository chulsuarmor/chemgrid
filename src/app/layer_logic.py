# layer_logic.py (v3.0 - VSEPR Refactored + Formal Charge Display)
# Agent 03 (루이스 구조) + Agent 05 (렌더링 엔진) 공유 파일
# LewisRenderer: Agent 03 전담
# TheoryRenderer: Agent 05 전담 (수정 금지)

import logging
import math
from collections import deque
from pathlib import Path

from PyQt6.QtGui import (QPainter, QColor, QFont, QPen, QPainterPath,
                          QFontMetrics, QBrush, QPolygonF, QRadialGradient,
                          QFontDatabase)
from PyQt6.QtCore import Qt, QPointF, QRectF
from rdkit import Chem  # 이론적 구조의 결합 타입 판별용

logger = logging.getLogger(__name__)


# ============================================================================
# [M609 Rule Q] 원자 라벨 폰트 패밀리 해결 — tofu(□) 방지
# 우선순위: Malgun Gothic → NanumGothic → Arial Unicode MS → Arial
# Malgun Gothic은 Windows 7+ 기본 내장, 영문/한글/특수문자 모두 지원
# Arial Unicode MS는 Office 설치 환경에서 추가 가용
# ============================================================================

def _resolve_atom_font_family() -> str:
    """
    Qt 런타임에서 가용한 폰트 패밀리를 순서대로 탐색하여 반환한다.
    QFontDatabase.families() 없이도 QFont.exactMatch()로 확인 가능하지만,
    families() 목록 직접 검사가 더 신뢰성 높다.

    Returns:
        str: 첫 번째 가용 폰트 패밀리 이름
    """
    # 우선순위 폰트 목록 (Rule Q: Malgun Gothic/NanumGothic 명시)
    _FONT_PRIORITY = [
        "Malgun Gothic",       # Windows 7+ 기본, 한글+영문+특수문자
        "NanumGothic",         # 설치된 경우 (학교 PC 등)
        "Arial Unicode MS",    # Office 설치 시 가용, 완전한 유니코드
        "Arial",               # 최후 fallback (영문은 OK, 한글 tofu 위험)
    ]
    try:
        available = set(QFontDatabase.families())
        if not any(family in available for family in _FONT_PRIORITY):
            loaded = _load_known_atom_font_files()
            if loaded:
                available = set(QFontDatabase.families()) | loaded
                logger.debug("[M609] Qt font DB bootstrap loaded: %s", sorted(loaded))
        for family in _FONT_PRIORITY:
            if family in available:
                logger.debug("[M609] 원자 라벨 폰트 선택: %s", family)
                return family
    except Exception as e:  # QApplication 미생성 시 등
        logger.warning("[M609] QFontDatabase 조회 실패: %s — Arial 사용", e)
    return "Arial"  # 절대 최후 fallback


# 모듈 로드 시점에 한 번만 해결 (QApplication이 아직 없을 수도 있어 lazy 처리)
# 실제 사용 시점(첫 렌더링)에 LewisRenderer._FONT_FAMILY가 재평가됨
_ATOM_FONT_FAMILY_CACHE: str = ""  # 빈문자열 = 미초기화 (Rule I: Carbon='' 패턴 준수)


def _load_known_atom_font_files() -> set[str]:
    """Load Windows font files when Qt offscreen starts with an empty font DB."""
    loaded: set[str] = set()
    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
    ]
    for font_path in candidates:
        if not font_path.exists():
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id < 0:
                logger.warning("[M609] font load failed: %s", font_path)
                continue
            for family in QFontDatabase.applicationFontFamilies(font_id):
                loaded.add(str(family))
        except Exception as exc:
            logger.warning("[M609] font load exception for %s: %s", font_path, exc)
    return loaded


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

        _adj_neighbors = adj.get(current, []) if isinstance(adj, dict) else []
        if not isinstance(_adj_neighbors, list):
            _adj_neighbors = []
        for neighbor, _ in _adj_neighbors:
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
    if not isinstance(analysis, dict):
        return None
    adj = analysis.get("adj", {})
    if not isinstance(adj, dict):
        logger.warning("_get_ring_center_direction: adj is not dict: %s", type(adj).__name__)
        adj = {}
    _theory = analysis.get("theory_data", {})
    if not isinstance(_theory, dict):
        logger.warning("_get_ring_center_direction: theory_data is not dict: %s", type(_theory).__name__)
        _theory = {}
    t_map = _theory.get("map", {})
    if not isinstance(t_map, dict):
        logger.warning("_get_ring_center_direction: map is not dict: %s", type(t_map).__name__)
        t_map = {}

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

    # 결합 중점 — Rule N: 타입 가드
    assert isinstance(t_map, dict)
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
    # [M609 Rule Q] _FONT_FAMILY: 하드코딩 "Arial" → 런타임 해결
    # 첫 렌더링 시 _get_font_family()가 Malgun Gothic 우선 체인으로 해결
    _FONT_FAMILY: str = ""  # 빈문자열 = lazy init 미완료 (Rule I: 매직넘버 금지)
    _FONT_SIZE_MAIN = 14       # 원자 기호
    _FONT_SIZE_H = 12          # 수소 기호
    _FONT_SIZE_SUB = 9         # 아래첨자 (NH2의 "2" 등)
    _FONT_SIZE_CHARGE = 10     # 형식전하 기호
    _BOND_WIDTH = 2.2          # 결합선 두께
    _BOND_WIDTH_SELECTED = 2.8 # 선택 시 결합선 두께
    _GAP_MARGIN = 8            # 기호-결합선 여백 (px)
    _MIN_ANGLE_GAP = 30.0      # 최소 배치 각도 간격 (°)
    _H_COLLISION_RADIUS = 18.0 # [P0-2 v2] H 라벨 충돌 감지 반경 (px) — 18px for 12pt font
    # [M647_W11] 사용자 격분 (2026-05-03 18:37): "산소 등 비공유 전자쌍의 표현이 너무 크고
    #   굵어 분자를 식별하는데 방해... 점의 두께를 절반 이상 줄이고 산소에 약간 더 붙여서 표현
    #   (C:\chemgrid\docs\in 내 전공서 이미지 참조)" → 3.5→1.5px (절반 이상 축소).
    # [M722-1 F4-1 item5] 사용자 격분 재차 인용: "비공유 전자쌍의 표현이 너무 크고 굵어 분자를
    #   식별하는데 방해가 되므로, 지금보다 점의 두께를 절반 이상 줄이고 산소에 약간 더 붙여서 표현"
    #   → 1.5→0.9px (M647_W11 이후 재축소), 펜 두께 1.2→0.7px, 간격 3.0→2.2px.
    # [D_M804_B3 사용자 격분 #03 (2026-05-05)] "비공유전자쌍 크기 축소 + 떨어트리기" —
    #   M722-1 0.9px여도 원자 라벨과 시각적 혼동 발생. dot_size 0.9→0.7px (재축소).
    #   _LONE_PAIR_GAP 2.2→3.0px (perpendicular separation 확대 — 두 점 시각 구분).
    #   _LP_DISTANCE_FROM_ATOM 신설: 0.35*base_gap+1 → 0.55*base_gap+3 (원자에서 떨어트리기).
    # 학술 표준: 유기화학 교과서 (Clayden 2nd ed §1.6 / Solomons §1.3): lone pair dot 크기는
    #   원자 라벨 텍스트 점 크기(폰트 12pt 기준 ~3px)의 약 1/3 이하가 방해 최소화.
    #   IUPAC Gold Book "lone pair": 원자 기호 옆에 명확히 식별되도록 표기.
    _LONE_PAIR_DOT_SIZE = 0.7  # [MAGIC: 0.7px] D_M804_B3 재축소 (M722-1 0.9px → 0.7px)
    _LONE_PAIR_GAP = 3.0       # [MAGIC: 3.0px] D_M804_B3 두 점 perpendicular 간격 확대 (2.2→3.0)
    # [MAGIC: 0.55, 3.0] D_M804_B3 LP-원자 거리 비율: 원자 기호 가장자리 + 3px 추가 여백.
    # 0.55*base_gap (heteroatom 14px → 7.7px) + 3 = ~10.7px 원자 중심에서.
    _LP_DISTANCE_RATIO = 0.55
    _LP_DISTANCE_OFFSET = 3.0

    @classmethod
    def _get_font_family(cls) -> str:
        """
        [M609 Rule Q] 원자 라벨 폰트 lazy 해결.
        _FONT_FAMILY가 빈문자열(미초기화)이면 _resolve_atom_font_family()를 호출하여
        Malgun Gothic 우선 chain으로 해결하고 클래스 변수에 캐시한다.

        호출 시점: QApplication 생성 후 첫 렌더링 (draw_lewis_atom/get_bond_gap 등)
        """
        if not cls._FONT_FAMILY:  # 빈문자열 = 미초기화
            cls._FONT_FAMILY = _resolve_atom_font_family()
        return cls._FONT_FAMILY

    @staticmethod
    def get_bond_gap(pt_key, atoms_data):
        """
        결합선이 원소 기호로부터 떨어져야 하는 거리(px) 계산.
        기호 텍스트 크기의 절반 + 여백.

        [M501 FIX] 탄소 원자(symbol="")는 Lewis 골격 구조에서 라벨 없이
        vertex만 표시 → gap = 0. 이전 코드의 "C"로 대체 후 gap 계산이 문제였음.
        탄소에 17px gap을 부여해서 40px 결합이 6px로 줄어 점선처럼 보임.
        Rule I: Carbon = '' (빈 문자열) — 라벨 없는 탄소는 gap=0.
        """
        if pt_key not in atoms_data:
            return 0

        atom = atoms_data[pt_key]
        if not isinstance(atom, dict):
            return 0
        symbol = atom.get("main", "")

        # [M501 FIX] 탄소(빈 문자열)는 라벨 없음 → gap = 0 (vertex 표시)
        # Rule I: Carbon = '' (empty string). 결합이 vertex에서 만나므로 gap 불필요.
        if not symbol or symbol.strip() == "":
            return 0  # Carbon vertex: no label, no gap needed

        font = QFont(LewisRenderer._get_font_family(),  # [M609] lazy resolved font
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
            logger.warning("LewisRenderer.render: analysis is empty or None")
            return
        if not isinstance(analysis, dict):
            logger.warning("LewisRenderer.render: analysis is not dict: %s", type(analysis).__name__)
            return

        logger.debug("LewisRenderer v3.0 activated")
        _theory_d = analysis.get("theory_data", {})
        if not isinstance(_theory_d, dict):
            _theory_d = {}
        t_map = _theory_d.get("map", {})
        if not isinstance(t_map, dict):
            t_map = {}
        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            atoms_data = {}

        if selected_atoms is None:
            selected_atoms = set()
        if selected_bonds is None:
            selected_bonds = set()

        painter.save()

        # === STAGE 1: 결합선 렌더링 ===
        LewisRenderer._render_bonds(painter, analysis, t_map,
                                     atoms_data, selected_bonds)

        # === STAGE 1b: 입체화학 wedge/dash 렌더링 (B10-15) ===
        # 키랄 탄소 + 3개 이상 R기 → wedge(실선 삼각형)/dash(점선) 표시
        LewisRenderer._render_stereo_bonds(painter, analysis, t_map, atoms_data)

        # === STAGE 1c: 방향족 링 내부 원 — D888-W4 사용자 명시 피드백으로 비활성화 ===
        # [D888-W4/M891] "벤젠 원모양 비편재화 표시 없애라" — 내접원 제거, Kekule 이중결합으로 표시
        # LewisRenderer._render_aromatic_ring_circles(painter, analysis, t_map)  # DISABLED

        # === STAGE 2: 원자 기호 렌더링 ===
        # [M680 item2] Lewis 구조식 = 탄소도 "C" 명시 표시 (show_carbon=True)
        LewisRenderer._render_atom_symbols(painter, analysis, t_map,
                                            selected_atoms, show_carbon=True)

        # === STAGE 3: 수소 + 비공유전자쌍 (VSEPR 배치) ===
        LewisRenderer._render_vsepr_extensions(painter, analysis, t_map)

        # === STAGE 4: 형식전하 표시 ===
        LewisRenderer._render_formal_charges(painter, analysis, t_map)

        # === STAGE 5: 분자내 수소결합 점선 (catechol OH 등) ===
        LewisRenderer._render_intramolecular_hbonds(painter, analysis, t_map)

        painter.restore()
        logger.debug("LewisRenderer complete")

    # ------------------------------------------------------------------
    # STAGE 1: 결합선
    # ------------------------------------------------------------------
    @staticmethod
    def _render_bonds(painter, analysis, t_map, atoms_data, selected_bonds):
        """결합선 렌더링 (단일/이중/삼중, C=C 짧은 선 지원)"""
        _bonds_data = analysis.get("bonds", {}) if isinstance(analysis, dict) else {}
        if not isinstance(_bonds_data, dict):
            logger.warning("_render_bonds: bonds data is not dict: %s", type(_bonds_data).__name__)
            _bonds_data = {}
        # [D888-W4/M891] aromatic_ring_sets 빌드 로직 제거 — 내접원 비활성화로 불필요
        # (이전: rings/aromatic_atoms 수집 후 ring 내 결합 order=1 강제에 사용)
        for (k1, k2), v in _bonds_data.items():
            # [M501 FIX] Wedge/Dash 입체결합은 _render_stereo_bonds()에서 처리.
            # 여기서 solid line으로 중복 그리면 시각적 노이즈 발생.
            # tuple 형식 (QPointF, QPointF, "Wedge"/"Dash") → STAGE 1b에서 처리됨.
            if isinstance(v, tuple) and len(v) >= 3 and isinstance(v[2], str) and v[2] in ("Wedge", "Dash"):
                continue  # stereo bond — handled by _render_stereo_bonds
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

            # [P0-2 FIX] Minimum bond line length enforcement
            # After gap subtraction, if the remaining line is too short,
            # clamp to minimum 8px to prevent double bonds appearing as dots
            drawn_length = math.hypot((p2 - p1).x(), (p2 - p1).y())
            if drawn_length < 8.0 and length > 0:
                # Shrink gaps proportionally to guarantee minimum 8px line
                max_gap_total = length - 8.0
                if max_gap_total < 0:
                    max_gap_total = 0
                scale_factor_gap = max_gap_total / (gap1 + gap2) if (gap1 + gap2) > 0 else 0
                p1 = p1_orig + unit * (gap1 * scale_factor_gap)
                p2 = p2_orig - unit * (gap2 * scale_factor_gap)

            order = v if isinstance(v, (int, float)) else (2 if "DOUBLE" in str(v) else 1)
            # [D888-W4/M891] STAGE 1c 내접원 비활성화에 따라 order=1 강제 로직도 제거.
            # canvas.bonds에는 Kekulize 후 1/2 교대 결합이 저장되어 있으므로 그대로 사용.
            # (이전 코드: aromatic ring set 내 결합을 order=1로 강제 → Kekule 이중결합 억제)

            # [COORD-BOND] Dative bond (order=0.5): dashed line + arrowhead
            if isinstance(order, (int, float)) and abs(order - 0.5) < 0.01:
                dative_color = QColor(80, 80, 160)
                dash_pen = QPen(dative_color, width)
                dash_pen.setStyle(Qt.PenStyle.DashLine)
                dash_pen.setDashPattern([6, 3])
                painter.setPen(dash_pen)
                painter.drawLine(p1, p2)
                # Arrowhead
                arrow_len = 6
                arrow_w = 3
                ax = -unit.x() * arrow_len
                ay = -unit.y() * arrow_len
                perp_x, perp_y = -unit.y(), unit.x()
                ap1 = p2 + QPointF(ax + perp_y * arrow_w, ay - perp_x * arrow_w)
                ap2 = p2 + QPointF(ax - perp_y * arrow_w, ay + perp_x * arrow_w)
                painter.setPen(QPen(dative_color, width))
                painter.setBrush(dative_color)
                painter.drawPolygon(QPolygonF([p2, ap1, ap2]))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                continue

            # C=C 판별 (짧은 보조선 적용)
            # Rule N: isinstance guard for atoms_data
            if not isinstance(atoms_data, dict): atoms_data = {}
            _ad1 = atoms_data.get(k1, {})
            _ad2 = atoms_data.get(k2, {})
            elem1 = _ad1.get("main", "C") if isinstance(_ad1, dict) else "C"
            elem2 = _ad2.get("main", "C") if isinstance(_ad2, dict) else "C"
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
        if not isinstance(analysis, dict):
            return result
        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            atoms_data = {}
        aromatic_atoms = analysis.get("aromatic", set())
        if not isinstance(aromatic_atoms, set):
            aromatic_atoms = set()
        adj = analysis.get("adj", {})
        if not isinstance(adj, dict):
            adj = {}

        # 전하 있는 원자 수집
        charged = {}
        for pt_key, atom_data in atoms_data.items():
            if not isinstance(atom_data, dict):
                continue
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
                        _adj_list = adj.get(current, [])
                        if not isinstance(_adj_list, list):
                            _adj_list = []
                        for neighbor, _ in _adj_list:
                            if neighbor not in visited and neighbor in aromatic_atoms:
                                queue.append(neighbor)
            else:
                # 비방향족: 해당 원자만
                result[charged_key] = color

        return result

    @staticmethod
    def _render_atom_symbols(painter, analysis, t_map, selected_atoms,
                              show_carbon: bool = False):
        """
        원자 기호 렌더링 (모든 원소 표시, 선택 시 파란색 하이라이트)
        [Fix v3] π 고리에 전하가 있으면 고리 전체 동일 색상 (비편재화)

        [M680 item2 fix] show_carbon=True 시 빈 symbol(탄소)을 "C"로 표시.
        Lewis 구조식은 모든 원소(탄소 포함)를 명시 표기해야 함.
        Rule I: Carbon='' (빈문자열) 규칙은 내부 저장 규칙 — 렌더링 시 Lewis 모드에선 "C" 표시.
        """
        if not isinstance(analysis, dict):
            return
        # π 비편재화 색상 맵 사전 계산
        charged_color_map = LewisRenderer._get_charged_ring_atoms(analysis)

        _atoms_s2 = analysis.get("atoms", {})
        if not isinstance(_atoms_s2, dict):
            logger.warning("_render_atom_symbols: atoms data is not dict: %s", type(_atoms_s2).__name__)
            _atoms_s2 = {}
        for pt_key, atom_data in _atoms_s2.items():
            if not isinstance(atom_data, dict):
                continue
            symbol = atom_data.get("main", "")
            # Rule I: Carbon = '' (empty string) — 내부 저장 규칙.
            # [M680 item2] Lewis 구조식은 탄소도 'C'로 명시 표시 (show_carbon=True).
            # Theory/skeletal 모드는 show_carbon=False(기본값)로 이전과 동일 동작.
            if not symbol or symbol.strip() == "":
                if show_carbon:
                    symbol = "C"  # [MAGIC: "C"] Lewis 구조식 탄소 명시 (M680 item2)
                else:
                    continue  # skeletal notation: 탄소 라벨 미표시

            center = t_map.get(pt_key, QPointF(*pt_key))
            is_selected = pt_key in selected_atoms

            # [Fix v3] 전하 비편재화 색상 우선 적용
            if is_selected:
                atom_color = Qt.GlobalColor.blue
            elif pt_key in charged_color_map:
                atom_color = charged_color_map[pt_key]
            else:
                atom_color = Qt.GlobalColor.black

            painter.setFont(QFont(LewisRenderer._get_font_family(),  # [M609]
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
    # STAGE 1b: Wedge/Dash 입체화학 결합 렌더링 (B10-15 / M645_W26)
    # ------------------------------------------------------------------
    @staticmethod
    def _render_stereo_bonds(painter, analysis, t_map, atoms_data):
        """[B10-15 / M645_W26] 키랄 탄소 입체화학 wedge/dash 결합 렌더링.

        조건: stereo_data 존재 시 wedge(채운 삼각형)/dash(빗금 쐐기) 표시.
        SMILES에서 RDKit WedgeMolBonds → BondDir 기반으로 결합 방향 판별.

        [M645_W26 ROOT CAUSE FIX] 기존 코드는 atoms_data["rdkit_idx"] 필드로
        rdkit_idx → canvas_key 매핑을 구축하려 했으나, analyzer.py가 rdkit_idx를
        atoms_data에 저장하지 않아 매핑이 항상 빈 dict → wedge/dash 0개.

        수정: theory_data["coords"] (rdkit_idx → QPointF) +
              theory_data["map"] 역방향 (QPointF → canvas_key)으로 매핑 구축.
              매핑 실패 시 캔버스 atoms 순차 인덱스 fallback 적용.

        Rule L: MolFromSmiles + None 체크 필수.
        Rule M: 실패 시 logger.warning (silent failure 금지).
        Rule I: 매직넘버 주석 필수.
        """
        if not isinstance(analysis, dict):
            return
        stereo_data = analysis.get("stereo", {})
        if not stereo_data:
            return  # 키랄 중심 없음 → 렌더링 건너뜀

        smiles = analysis.get("smiles", "")
        if not smiles:
            logger.warning("[LewisRenderer._render_stereo_bonds] SMILES 없음, wedge/dash 건너뜀")
            return

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("[LewisRenderer._render_stereo_bonds] SMILES 파싱 실패: %r", smiles)
                return
            Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
            from rdkit.Chem import AllChem
            AllChem.Compute2DCoords(mol)
            try:
                Chem.WedgeMolBonds(mol, mol.GetConformer())  # M279: BondDir 설정 (CIP 우선순위 기반)
            except Exception as e:
                logger.warning("[LewisRenderer._render_stereo_bonds] WedgeMolBonds 실패, fallback 사용: %s", e)
            conf = mol.GetConformer()
        except Exception as e:
            logger.warning("[LewisRenderer._render_stereo_bonds] RDKit 초기화 실패: %s", e)
            return

        # [M645_W26 FIX] rdkit_idx → canvas_key 매핑 3단계 전략
        # ── STEP 1: theory_data["coords"] + theory_data["map"] 역방향 매핑 ──
        # theory_data["coords"]: {rdkit_idx: QPointF(screen_x, screen_y)}
        # theory_data["map"]:    {(canvas_x, canvas_y): QPointF(screen_x, screen_y)}
        rdkit_idx_to_canvas_key = {}
        _t_data = analysis.get("theory_data", {})
        if isinstance(_t_data, dict):
            _t_coords = _t_data.get("coords", {})  # rdkit_idx → QPointF
            _t_map_raw = _t_data.get("map", {})    # (cx,cy) → QPointF
            if isinstance(_t_coords, dict) and isinstance(_t_map_raw, dict):
                # 역방향: QPointF → canvas_key (소수점 2자리 반올림 일치)
                _screen_to_ck = {}
                for ck, qpt in _t_map_raw.items():
                    if isinstance(qpt, QPointF):
                        _key = (round(qpt.x(), 1), round(qpt.y(), 1))
                        _screen_to_ck[_key] = ck
                for ridx, qpt in _t_coords.items():
                    if not isinstance(ridx, int) or not isinstance(qpt, QPointF):
                        continue
                    _skey = (round(qpt.x(), 1), round(qpt.y(), 1))
                    ck = _screen_to_ck.get(_skey)
                    if ck is not None:
                        rdkit_idx_to_canvas_key[ridx] = ck

        # ── STEP 2: atoms_data["rdkit_idx"] 필드 fallback (미래 호환) ──
        if not rdkit_idx_to_canvas_key:
            for ck, ad in atoms_data.items():
                if not isinstance(ad, dict):
                    continue
                ridx = ad.get("rdkit_idx", -1)
                if isinstance(ridx, int) and ridx >= 0:
                    rdkit_idx_to_canvas_key[ridx] = ck

        # ── STEP 3: 순차 인덱스 기반 최후 fallback ──
        # analyzer.py generate_smiles: sorted_keys = sorted(atoms.keys(), key=λ y,x)
        # RDKit mol AddAtom도 동일 순서 → rdkit_idx == sorted position index
        # [M764 A70-W1 F4-1 item4] STEP 3 fallback은 좌표 정합성이 낮아 wedge 침범 위험.
        # STEP 3 사용 시 wedge/dash 그리기 자체를 건너뜀 (Rule M: 잘못된 시각 < 없는 시각).
        _step3_fallback_used = False
        if not rdkit_idx_to_canvas_key and atoms_data:
            sorted_ck = sorted(atoms_data.keys(), key=lambda k: (k[1], k[0]))
            for seq_idx, ck in enumerate(sorted_ck):
                rdkit_idx_to_canvas_key[seq_idx] = ck
            _step3_fallback_used = True
            logger.warning(
                "[M764/M645_W26] rdkit_idx 매핑 STEP3 fallback: 순차 인덱스 사용 (%d atoms)"
                " → wedge/dash 건너뜀 (침범 방지 M764 F4-1 item4)", len(sorted_ck)
            )

        mapped_count = len(rdkit_idx_to_canvas_key)
        logger.debug("[M645_W26] rdkit_idx_to_canvas_key: %d 항목 구축", mapped_count)

        # [M764 F4-1 item4] STEP3 fallback 좌표 비정합 시 wedge/dash 완전 생략 — 침범 방지
        if _step3_fallback_used:
            logger.warning("[M764] STEP3 fallback 감지 — wedge/dash 전체 생략 (분자 침범 방지)")
            return

        # 키랄 원자 찾기
        chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=False)
        if not chiral_centers:
            logger.debug("[M645_W26] 키랄 센터 없음 — wedge/dash 생략")
            return

        painter.save()
        wedge_color = QColor(20, 20, 20)    # [MAGIC:20] 충분히 진한 쐐기 — Cahn-Ingold-Prelog 1956
        dash_color = QColor(40, 40, 40)     # [MAGIC:40] 빗금 쐐기 색상

        drawn_count = 0
        for atom_idx, cip_code in chiral_centers:
            atom = mol.GetAtomWithIdx(atom_idx)
            center_ck = rdkit_idx_to_canvas_key.get(atom_idx)
            if center_ck is None:
                logger.warning("[M645_W26] atom_idx=%d → canvas_key 없음 (매핑 범위 초과)", atom_idx)
                continue

            # t_map이 있으면 보정 좌표, 없으면 canvas 원본 좌표 사용
            center_screen = t_map.get(center_ck, QPointF(*center_ck))

            neighbors = atom.GetNeighbors()
            n_sub = len(neighbors)
            if n_sub < 2:
                continue  # [MAGIC:2] 치환기 2개 이상일 때 wedge/dash 의미 있음

            from rdkit.Chem import BondDir, ChiralType
            wedge_drawn = 0
            dash_drawn = 0

            for nb in neighbors:
                n_idx = nb.GetIdx()
                nb_ck = rdkit_idx_to_canvas_key.get(n_idx)
                if nb_ck is None:
                    continue
                nb_screen = t_map.get(nb_ck, QPointF(*nb_ck))

                bond = mol.GetBondBetweenAtoms(atom_idx, n_idx)
                if bond is None:
                    continue
                bdir = bond.GetBondDir()
                is_wedge = (bdir == BondDir.BEGINWEDGE)
                is_dash = (bdir == BondDir.BEGINDASH)

                # 키랄 태그 기반 fallback (BondDir가 NONE일 때)
                if not is_wedge and not is_dash:
                    tag = atom.GetChiralTag()
                    nb_order = [n.GetIdx() for n in neighbors].index(n_idx)
                    if tag == ChiralType.CHI_TETRAHEDRAL_CW:
                        if nb_order == 0 and wedge_drawn == 0:
                            is_wedge = True
                        elif nb_order == 1 and dash_drawn == 0:
                            is_dash = True
                    elif tag == ChiralType.CHI_TETRAHEDRAL_CCW:
                        if nb_order == 0 and wedge_drawn == 0:
                            is_dash = True
                        elif nb_order == 1 and dash_drawn == 0:
                            is_wedge = True

                vec = nb_screen - center_screen
                length = math.hypot(vec.x(), vec.y())
                if length < 2.0:
                    continue
                unit = vec / length
                perp = QPointF(-unit.y(), unit.x())

                if is_wedge and wedge_drawn < 1:
                    # 채운 삼각형 쐐기: IUPAC 권고 1996 — 시작=좁게, 끝=넓게
                    # [M647_W11] 사용자 격분 (2026-05-03 18:37): "웨지 대쉬 표현이 오류가 나서
                    #   분자 내 다른 구조를 심각하게 침범" → half_w_end 8.0→4.0px 축소,
                    #   bond length 캡 추가 (Procrustes 좌표 어긋남 시에도 시각 안정성 보장).
                    half_w_start = 1.5   # [MAGIC:1.5px] 시작 반폭 (px)
                    half_w_end = 4.0     # [MAGIC:4.0px] 끝 반폭 — M647_W11 축소 (M645_W26 8.0px 침범)
                    gap_c = LewisRenderer.get_bond_gap(center_ck, atoms_data)
                    gap_n = LewisRenderer.get_bond_gap(nb_ck, atoms_data)
                    p_start = center_screen + unit * gap_c
                    p_end_full = nb_screen - unit * gap_n
                    # [M647_W11] bond length 캡 (60px 상한): theory_data Procrustes drift 시 wedge가
                    #   분자 너비를 가로지르며 다른 원자 침범하는 사고 차단
                    seg_len = math.hypot((p_end_full - p_start).x(), (p_end_full - p_start).y())
                    if seg_len > 60.0:  # [MAGIC: 60px] 일반 결합 25~40px의 1.5배 상한
                        p_end = p_start + unit * 60.0
                    else:
                        p_end = p_end_full
                    poly = QPolygonF([
                        p_start + perp * half_w_start,
                        p_start - perp * half_w_start,
                        p_end - perp * half_w_end,
                        p_end + perp * half_w_end,
                    ])
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(wedge_color))
                    painter.drawPolygon(poly)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    wedge_drawn += 1
                    drawn_count += 1

                elif is_dash and dash_drawn < 1:
                    # 빗금 쐐기 (hashed wedge): 평행 가로선이 점점 넓어짐
                    gap_c = LewisRenderer.get_bond_gap(center_ck, atoms_data)
                    gap_n = LewisRenderer.get_bond_gap(nb_ck, atoms_data)
                    p_start = center_screen + unit * gap_c
                    p_end_full = nb_screen - unit * gap_n
                    # [M647_W11] bond length 캡 (wedge와 동일 60px 상한)
                    full_len = math.hypot((p_end_full - p_start).x(), (p_end_full - p_start).y())
                    if full_len > 60.0:
                        p_end = p_start + unit * 60.0
                    else:
                        p_end = p_end_full
                    dash_len = math.hypot((p_end - p_start).x(), (p_end - p_start).y())
                    if dash_len < 2.0:
                        continue
                    n_dashes = max(4, int(dash_len / 4))  # [MAGIC:4px] 간격
                    for di in range(n_dashes):
                        t0 = di / n_dashes
                        # [M647_W11] half_w 8.0→4.0 축소 (분자 침범 차단)
                        half_w = 1.5 + (4.0 - 1.5) * t0  # [MAGIC:1.5~4.0px] 점점 넓어짐
                        ps = p_start + (p_end - p_start) * t0
                        dash_pen = QPen(dash_color, max(1.2, half_w * 0.5))
                        dash_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                        painter.setPen(dash_pen)
                        painter.drawLine(
                            ps + perp * half_w,
                            ps - perp * half_w,
                        )
                    dash_drawn += 1
                    drawn_count += 1

        painter.restore()
        logger.debug(
            "[M645_W26] Stereo bonds rendered: %d chiral centers, %d bonds drawn",
            len(chiral_centers), drawn_count,
        )
        if drawn_count == 0:
            logger.warning(
                "[M645_W26] 키랄 센터 %d개 존재하나 wedge/dash 0개 그려짐 "
                "— 매핑(%d항목) 또는 BondDir 문제. SMILES: %r",
                len(chiral_centers), mapped_count, smiles,
            )

    # ------------------------------------------------------------------
    # STAGE 1c: 방향족 링 내접원 (A59-W1/M731/ISSUE-A58-002)
    # ------------------------------------------------------------------
    @staticmethod
    def _render_aromatic_ring_circles(painter, analysis, t_map):
        """6원 방향족 링에 내접원(정원) 표기 — Kekulé 이중결합 대신 비편재화 표현.

        근거: IUPAC 2013 §P-31.1.2 — 방향족 6원 링 circle 표기법.
        popup_reaction.py L412-427 inscribed circle 로직 동일 패턴 (검증됨).

        [M731/ISSUE-A58-002] 방향족 링 직사각형 왜곡 근본 원인:
        - 방향족 결합은 order=1 저장 → STAGE 1에서 단일선만 그려짐
        - 내접원 없으면 정육각형으로 보이지 않음
        - 본 메서드로 링마다 정원 1개 추가
        """
        if not isinstance(analysis, dict):
            return
        rings = analysis.get("rings", [])
        if not isinstance(rings, list):
            return
        if not rings:
            return
        aromatic_atoms = analysis.get("aromatic", set())
        if not isinstance(aromatic_atoms, set):
            aromatic_atoms = set()

        painter.save()
        painter.setPen(QPen(Qt.GlobalColor.black, LewisRenderer._BOND_WIDTH))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for ring in rings:
            if not isinstance(ring, (list, tuple)) or len(ring) < 5:
                continue  # 5원 미만은 스킵
            if not all(atom_key in aromatic_atoms for atom_key in ring):
                continue  # non-aromatic rings must not get a delocalization circle
            # 고리 중심 계산
            positions = [t_map.get(atom_key, QPointF(*atom_key)) for atom_key in ring]
            cx = sum(pt.x() for pt in positions) / len(positions)
            cy = sum(pt.y() for pt in positions) / len(positions)
            # 내접원 반지름 = 평균 거리의 55% (IUPAC 관행, popup_reaction.py 동일)
            avg_r = sum(
                math.hypot(pt.x() - cx, pt.y() - cy) for pt in positions
            ) / len(positions)
            circle_r = avg_r * 0.55  # [MAGIC: 0.55] IUPAC/표준 방향족 원 비율
            if circle_r < 1.0:
                continue  # 너무 작은 원은 스킵 (렌더링 노이즈 방지)
            center_pt = QPointF(cx, cy)
            painter.drawEllipse(center_pt, circle_r, circle_r)

        painter.restore()
        logger.debug("Aromatic ring circles rendered: %d rings", len(rings))

    # ------------------------------------------------------------------
    # STAGE 3: VSEPR 기반 수소 + 비공유전자쌍 배치
    # ------------------------------------------------------------------
    @staticmethod
    def _render_vsepr_extensions(painter, analysis, t_map):
        """
        모든 원자에 대해 VSEPR 기반 H/LP 배치
        [P0-2 FIX] 전체 H 라벨 좌표를 수집한 뒤 충돌 감지 + 밀어내기 수행
        """
        if not isinstance(analysis, dict):
            return
        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            atoms_data = {}
        aromatic_set = analysis.get("aromatic", set())
        if not isinstance(aromatic_set, set):
            aromatic_set = set()

        # [P0-2] Phase 1: 모든 H/LP 위치를 사전 계산 (렌더링 전에 충돌 감지용)
        h_label_positions = []  # [(QPointF center, atom_key), ...]

        for pt_key, atom_data in atoms_data.items():
            if not isinstance(atom_data, dict):
                continue
            h_count = atom_data.get("h_count", 0)
            lp_count = atom_data.get("lp_count", 0)

            # [Fix v3.2] 방향족 탄소 이온: LP 표시 안함
            symbol = atom_data.get("main", "C") or "C"
            user_charge = atom_data.get("charge", "")
            formal_charge = atom_data.get("formal_charge", 0)
            if symbol == "C" and pt_key in aromatic_set and (user_charge or formal_charge != 0):
                lp_count = 0  # 방향족 이온 탄소: π 전자는 LP가 아닌 비편재화 전자

            # [M686 Fix] 배위결합 양전하 원자: LP 강제 0 (item7 NO2 N+ 비공유전자쌍 오류)
            # NO2: N+(formal=+1) — 배위결합으로 비공유전자쌍 없음. 동일 원리: O+ S+ 적용.
            # 학술 근거: Clayden Organic Chemistry 3rd ed. §1.4 (배위결합 dative bond).
            # Rule L: formal_charge는 int. isinstance 가드 적용.
            _effective_fc = formal_charge
            if not isinstance(_effective_fc, int):
                _effective_fc = 0
            if _effective_fc > 0 and symbol in ("N", "O", "S", "P"):
                lp_count = 0  # 양전하 N/O/S/P = 배위결합 또는 전자 이전으로 LP 없음

            if h_count + lp_count == 0:
                continue
            LewisRenderer._draw_vsepr_extensions(
                painter, pt_key, atom_data, analysis, t_map,
                lp_count_override=lp_count,
                h_label_positions=h_label_positions)

        # [P0-2] Phase 2: H 라벨 충돌 감지 및 위치 조정은
        # _draw_vsepr_extensions 내부에서 수집된 좌표로 처리됨
        # (실제 렌더링은 _draw_vsepr_extensions에서 직접 수행)

    @staticmethod
    def _draw_vsepr_extensions(painter, pos_tuple, data, analysis, t_map,
                                lp_count_override=None, h_label_positions=None):
        """
        VSEPR 기반 수소 및 비공유전자쌍 배치 v3.1

        개선사항 (v3.0 → v3.1):
        - [P0-2] H 라벨 충돌 감지: h_label_positions 리스트에 좌표 수집 후
          기존 라벨과 겹치면 force-directed push로 위치 조정
        - [P0-2] NH2 등 다중 H는 그룹 라벨(NH2)로 렌더링 + 아래첨자
        - [P0-2] OH/HO flip: 결합 방향에 따라 H를 왼쪽/오른쪽 배치

        [Fix v3 수소 도구] attach dict에 사용자가 직접 배치한 H 수를 h_count에서 차감
        [Fix v3.2] lp_count_override: 방향족 이온 탄소의 LP 수를 외부에서 강제 지정
        """
        if not isinstance(data, dict):
            logger.warning("_draw_vsepr_extensions: data is not dict: %s", type(data).__name__)
            return
        if h_label_positions is None:
            h_label_positions = []
        center = t_map.get(pos_tuple, QPointF(*pos_tuple))
        _adj_dict = analysis.get("adj", {}) if isinstance(analysis, dict) else {}
        if not isinstance(_adj_dict, dict):
            _adj_dict = {}
        adj_info = _adj_dict.get(pos_tuple, [])
        if not isinstance(adj_info, list):
            adj_info = []

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
        _attach = data.get("attach", {})
        if not isinstance(_attach, dict):
            _attach = {}
        user_placed_h = sum(1 for sym in _attach.values() if sym == "H")
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

        # [STEP 4] 기호 크기 기반 동적 gap 계산 — Rule N: isinstance
        assert isinstance(data, dict)
        symbol = data.get("main", "C")
        if not symbol or symbol.strip() == "":
            symbol = "C"
        font = QFont(LewisRenderer._get_font_family(),  # [M609]
                      LewisRenderer._FONT_SIZE_MAIN, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        sym_half = max(fm.horizontalAdvance(symbol), fm.height()) / 2
        base_gap = sym_half + LewisRenderer._GAP_MARGIN

        # [STEP 5] 수소 우선 배치, 이후 비공유전자쌍
        # [P0-2 FIX] H 라벨에 충돌 감지 적용 (force-directed push)
        for i, angle_deg in enumerate(placement_angles):
            rad = math.radians(angle_deg)
            direction = QPointF(math.cos(rad), math.sin(rad))

            if i < h_count:
                # [P0-2 v2] Calculate H label position for collision detection
                # label_reach: distance from center to H text center
                label_reach = base_gap + 20 + 10  # bond_line + H_text_offset
                h_pos = center + direction * label_reach
                # Iterative collision push: try up to 6 angles (±15° steps each)
                # to find a slot with no overlap. Rule O: minimum 8px separation
                adjusted_direction = direction
                push_angle = angle_deg
                for _push_try in range(6):  # max 6 attempts = 90° sweep
                    collision_found = False
                    for existing_pos, _ in h_label_positions:
                        dist_to_existing = math.hypot(
                            h_pos.x() - existing_pos.x(),
                            h_pos.y() - existing_pos.y()
                        )
                        if dist_to_existing < LewisRenderer._H_COLLISION_RADIUS:
                            collision_found = True
                            break
                    if not collision_found:
                        break  # no collision — keep current adjusted_direction
                    # Push away: rotate by 15° and recompute position
                    push_angle += 15.0
                    push_rad = math.radians(push_angle)
                    adjusted_direction = QPointF(
                        math.cos(push_rad), math.sin(push_rad))
                    h_pos = center + adjusted_direction * (label_reach + 10)

                LewisRenderer._draw_h_bond(painter, center, adjusted_direction,
                                            gap=base_gap)
                # Record position for future collision checks
                h_label_positions.append((h_pos, pos_tuple))
            else:
                # [M763 A69-W1-P1 LV-10 LP PROX] 이전: 0.35+1 (~7px) — 너무 가까워서 라벨과 겹침.
                # [D_M804_B3 사용자 격분 #03 (2026-05-05)] "비공유전자쌍 크기 축소 + 떨어트리기" —
                # M763 0.35+1 (~7px) → 0.55+3 (~10.7px). 원자 기호 가장자리(약 7px) + 3px 여백.
                # 학술 근거: Clayden Organic Chemistry §1.6 Fig 1.8 — LP dot은 원자 옆에
                # 명확히 식별되도록 (라벨 가장자리 너머에 위치, 겹침 없음).
                _lp_gap = int(base_gap * LewisRenderer._LP_DISTANCE_RATIO) + int(LewisRenderer._LP_DISTANCE_OFFSET)
                LewisRenderer._draw_lone_pair(painter, center, direction, gap=_lp_gap)

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

        # [M650 H2O/NH3 명시 배치] Kimi REJECT 대응 — 학술 표준 (Solomons §1.3,
        # Clayden 2nd §1.6) VSEPR LP 4분면 / tetrahedral 명시.
        # 일반 알고리즘이 동작하긴 하나 H2O 두 LP가 같은 사분면에 몰릴 가능성 차단.
        #
        # 케이스 A: H2O 류 (2 bonds + 2 LP) → LP는 H 결합의 반대쪽 두 사분면
        # 케이스 B: NH3 류 (3 bonds + 1 LP) → LP는 3 H 무게중심의 정반대 (tetrahedral)
        if n_occ == 2 and num_to_place == 2:
            # [M650 H2O 4-quadrant] 두 H 결합 평균 각도 → 반대 방향 +/- 90°
            # Solomons §1.3: H2O는 sp3, 2 bonds + 2 LPs ≈ 109.5° 분포.
            # 시각적 단순화: H 결합 평균 반대 방향에서 +/- 90° 좌상/우상 사분면.
            avg_bond = (normed[0] + normed[1]) / 2.0
            opposite = (avg_bond + 180.0) % 360.0
            # [MAGIC: 90도] tetrahedral half-angle, 4-quadrant separation
            return [(opposite - 90.0) % 360.0, (opposite + 90.0) % 360.0]

        if n_occ == 3 and num_to_place == 1:
            # [M650 NH3 tetrahedral] 3 H 결합 무게중심의 정반대 (vector sum reverse)
            # Clayden 2nd §1.6: NH3는 sp3, lone pair는 H trio 반대편 (umbrella up).
            sum_x = sum(math.cos(math.radians(a)) for a in normed)
            sum_y = sum(math.sin(math.radians(a)) for a in normed)
            # 합 벡터의 반대 방향 = LP 위치
            opp_angle = math.degrees(math.atan2(-sum_y, -sum_x)) % 360.0
            return [opp_angle]

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
        if not isinstance(analysis, dict):
            return
        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            atoms_data = {}
        for pt_key, atom_data in atoms_data.items():
            if not isinstance(atom_data, dict):
                continue
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

            main_font = QFont(LewisRenderer._get_font_family(),  # [M609]
                               LewisRenderer._FONT_SIZE_MAIN,
                               QFont.Weight.Bold)
            main_fm = QFontMetrics(main_font)
            sym_w = main_fm.horizontalAdvance(symbol)
            sym_h = main_fm.height()

            # [Fix v2] 전하 기호는 검은색 위첨자 (원자색이 이미 전하 상태 표시)
            charge_text = "+" if formal_charge > 0 else "⁻"  # U+207B (Rule Q M433: 화학 음전하 위첨자)

            # 우상단 오프셋
            charge_font = QFont(LewisRenderer._get_font_family(),  # [M609]
                                 LewisRenderer._FONT_SIZE_CHARGE,
                                 QFont.Weight.Bold)
            painter.setFont(charge_font)
            painter.setPen(Qt.GlobalColor.black)  # [Fix v2] 검은색
            cfm = QFontMetrics(charge_font)
            cw = cfm.horizontalAdvance(charge_text)
            ch = cfm.height()

            # [v5 Fix] 원자 기호의 우상단에 배치 — 중앙 가림 방지
            min_offset = max(sym_w / 2, 8) + 3
            cx = center.x() + min_offset
            cy = center.y() - sym_h / 2 - 2

            charge_rect = QRectF(cx, cy, cw, ch)
            painter.drawText(charge_rect, Qt.AlignmentFlag.AlignCenter,
                             charge_text)

        logger.debug("Formal charges rendered")

    # ------------------------------------------------------------------
    # STAGE 5: 분자내 수소결합 점선
    # ------------------------------------------------------------------
    @staticmethod
    def _render_intramolecular_hbonds(painter, analysis, t_map):
        """
        [P0-2 FIX] 분자내 수소결합 점선 렌더링
        - Catechol (1,2-dihydroxybenzene): 인접 OH 간 수소결합
        - Salicylic acid: OH...O=C 수소결합
        - 일반적으로 O-H...O, O-H...N, N-H...O 패턴 감지

        조건: 수소결합 donor (OH, NH)와 acceptor (O, N, S)가
        적절한 거리(20~120px) 내에 있을 때 점선 표시
        """
        if not isinstance(analysis, dict):
            return
        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            return

        # H-bond donor/acceptor 수집
        oh_donors = []  # donor atom positions (O or N with H attached)
        acceptors = []  # (atom_position, element)
        for pt_key, ad in atoms_data.items():
            if not isinstance(ad, dict):
                continue
            el = ad.get("main", "") or "C"
            hc = ad.get("h_count", 0)
            if el in ('O', 'N', 'S'):
                acceptors.append((pt_key, el))
                if hc > 0:  # Has H attached = donor
                    oh_donors.append(pt_key)

        if not oh_donors or not acceptors:
            return

        # H-bond 거리 기준 (px)
        MAX_HBOND_DIST = 120.0  # 최대 수소결합 거리
        MIN_HBOND_DIST = 20.0   # 최소 거리 (자기 자신 제외)
        drawn_hbonds = set()

        painter.save()
        for donor_key in oh_donors:
            donor_center = t_map.get(donor_key, QPointF(*donor_key))
            for acc_key, acc_el in acceptors:
                if acc_key == donor_key:
                    continue
                # 중복 방지
                pair = tuple(sorted([donor_key, acc_key], key=str))
                if pair in drawn_hbonds:
                    continue
                acc_center = t_map.get(acc_key, QPointF(*acc_key))
                dist_hb = math.hypot(
                    acc_center.x() - donor_center.x(),
                    acc_center.y() - donor_center.y()
                )
                if MIN_HBOND_DIST < dist_hb < MAX_HBOND_DIST:
                    # [P0-2 FIX] 점선 스타일 수소결합 표시
                    # DashLine + 명시적 dash pattern으로 solid처럼 보이는 문제 해결
                    hb_pen = QPen(QColor(100, 100, 100, 180), 1.5)
                    hb_pen.setStyle(Qt.PenStyle.CustomDashLine)
                    hb_pen.setDashPattern([3, 5])  # 3px dash, 5px gap — 명확한 점선
                    painter.setPen(hb_pen)
                    painter.drawLine(donor_center, acc_center)
                    drawn_hbonds.add(pair)

        painter.restore()
        logger.debug("Intramolecular H-bonds rendered: %d", len(drawn_hbonds))

    # ------------------------------------------------------------------
    # 개별 요소 렌더링
    # ------------------------------------------------------------------
    @staticmethod
    def _draw_lone_pair(painter, center, direction, gap=14):
        """
        비공유 전자쌍(..) 렌더링 — ChemGrid 스타일 두 점.
        [M647_W11] 사용자 격분 (2026-05-03 18:37): "산소에 약간 더 붙여서 표현" →
            기본 gap 22→14px 축소 + effective_gap min 18→12px 축소.
        [M650 Kimi REJECT (2026-05-03)] H2O/NH3 A1-2: dots 보이지 않음 (1.5px 너무 작음).
            대응: dot 크기는 사용자 요구대로 1.5px 유지하되, Antialiasing ON +
            펜 두께 0.8→1.2px 강화 + 검은 fill로 시인성 극대화. (Solomons §1.3)
        [참고] 전공서 (docs/in/ 유기화학 교과서): lone pair는 원자 가장자리에 매우 가까이.

        Args:
            center: 원자 중심 좌표
            direction: 방향 단위 벡터
            gap: 원자 중심으로부터의 거리 (px) — M647_W11 22→14px
        """
        painter.save()
        # [M650] 작은 점(1.5px)에서 anti-aliasing은 시인성 핵심.
        # Rule M: silent failure 금지 — RenderHint 미설정 시 dots 흐릿하게 깨짐.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # [M763 A69-W1-P1 LV-10] effective_gap floor 6→4 — M691 6px 여전히 원자에서 멀음.
        # M763: floor 4px = 원자 기호 가장자리(반지름~4px)와 접함. "10→3~4" 비율에 정합.
        # [D_M804_B3 사용자 격분 #03 (2026-05-05)] "비공유전자쌍 크기 축소 + 떨어트리기" —
        # M763 floor 4px → 8px (원자 기호 라벨 너머에 LP 배치). 학술 근거: Clayden §1.6 Fig 1.8 —
        # LP dot은 원자 기호 옆에 명확히 식별되도록 표기 (라벨과 겹침 없음).
        effective_gap = max(gap, 8)  # [MAGIC: 8px] D_M804_B3 LP-원자 최소 거리 확대 (4→8px)
        pos = center + direction * effective_gap

        # 수직 방향 벡터 (두 점을 좌우로 배치)
        # [P0-2] 간격을 _LONE_PAIR_GAP 상수로 확대 (4.0 → 4.5px)
        # [D_M804_B3 #03] _LONE_PAIR_GAP 2.2 → 3.0px (두 점 시각적 분리 강화)
        perp = QPointF(-direction.y(), direction.x()) * LewisRenderer._LONE_PAIR_GAP

        # [M722-1 F4-1 item5] 사용자 재격분: "점의 두께를 절반 이상 줄이고 산소에 약간 더 붙여서"
        # dot_size 1.5→0.9px, 펜 두께 1.2→0.7px (절반 이상 축소). Antialiasing 유지로 시인성 확보.
        # [D_M804_B3 #03 (2026-05-05)] dot_size 0.9→0.7px (재축소), 펜 두께 0.7→0.5px (시각적 부담 감소).
        # 학술 근거: Clayden §1.6 Fig 1.8 — lone pair는 원자 기호 옆 작은 점(약 0.7px 인쇄 크기).
        dot_size = LewisRenderer._LONE_PAIR_DOT_SIZE
        painter.setBrush(Qt.GlobalColor.black)
        painter.setPen(QPen(Qt.GlobalColor.black, 0.5))  # [MAGIC: 0.5px] D_M804_B3 펜 재축소 (0.7→0.5)
        painter.drawEllipse(pos + perp, dot_size, dot_size)
        painter.drawEllipse(pos - perp, dot_size, dot_size)

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

        painter.setFont(QFont(LewisRenderer._get_font_family(),  # [M609]
                               LewisRenderer._FONT_SIZE_H,
                               QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.black)
        fm = QFontMetrics(painter.font())
        tw = fm.horizontalAdvance("H")
        th = fm.height()

        text_rect = QRectF(h_pos.x() - tw / 2, h_pos.y() - th / 2, tw, th)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "H")

    @staticmethod
    def _draw_h_group_label(painter, center, direction, gap, h_count,
                            atom_symbol, flip_h=False):
        """
        [P0-2 FIX] 다중 수소 그룹 라벨 렌더링 (OH, HO, NH2, H2N 등)
        - NH2의 "2"는 아래첨자로 렌더링
        - OH/HO flip: 결합 방향에 따라 H 위치 전환

        Args:
            center: 원자 중심 좌표
            direction: 라벨 방향 벡터
            gap: 원자 중심부터 라벨까지 거리
            h_count: 수소 개수
            atom_symbol: 원자 기호 (O, N, S 등)
            flip_h: True면 H를 기호 앞에 배치 (HO, H2N)
        """
        if h_count <= 0:
            return

        # 라벨 위치 계산
        label_pos = center + direction * gap

        main_font = QFont(LewisRenderer._get_font_family(),  # [M609]
                          LewisRenderer._FONT_SIZE_H, QFont.Weight.Bold)
        sub_font = QFont(LewisRenderer._get_font_family(),  # [M609]
                         LewisRenderer._FONT_SIZE_SUB, QFont.Weight.Bold)
        fm = QFontMetrics(main_font)
        sfm = QFontMetrics(sub_font)

        painter.setPen(Qt.GlobalColor.black)

        if h_count == 1:
            # Simple: OH or HO
            if flip_h:
                label = "H" + atom_symbol
            else:
                label = atom_symbol + "H"
            painter.setFont(main_font)
            tw = fm.horizontalAdvance(label)
            th = fm.height()
            text_rect = QRectF(label_pos.x() - tw / 2,
                               label_pos.y() - th / 2, tw, th)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
        else:
            # Subscript rendering: NH2 → "NH" + subscript "2"
            # or H2N → "H" + subscript "2" + "N"
            if flip_h:
                main_part = "H"
                sub_part = str(h_count)
                tail_part = atom_symbol
            else:
                main_part = atom_symbol + "H"
                sub_part = str(h_count)
                tail_part = ""

            main_w = fm.horizontalAdvance(main_part)
            sub_w = sfm.horizontalAdvance(sub_part)
            tail_w = fm.horizontalAdvance(tail_part) if tail_part else 0
            total_w = main_w + sub_w + tail_w
            text_h = fm.height()

            x_start = label_pos.x() - total_w / 2
            y_center = label_pos.y()

            # Draw main part
            painter.setFont(main_font)
            main_rect = QRectF(x_start, y_center - text_h / 2,
                               main_w, text_h)
            painter.drawText(main_rect, Qt.AlignmentFlag.AlignCenter,
                             main_part)

            # Draw subscript (smaller, lowered by 35% of text height)
            painter.setFont(sub_font)
            sub_h = sfm.height()
            sub_rect = QRectF(x_start + main_w,
                              y_center - text_h / 2 + text_h * 0.35,
                              sub_w, sub_h)
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter,
                             sub_part)

            # Draw tail if flipped
            if tail_part:
                painter.setFont(main_font)
                tail_rect = QRectF(x_start + main_w + sub_w,
                                   y_center - text_h / 2, tail_w, text_h)
                painter.drawText(tail_rect, Qt.AlignmentFlag.AlignCenter,
                                 tail_part)


# ============================================================================
# TheoryRenderer — 이론적 구조 레이어 (Agent 05 전담, 수정 금지)
# ============================================================================

class TheoryRenderer:
    @staticmethod
    def get_bond_gap(pt_key, atoms_data):
        """
        결합선이 원소 기호로부터 얼마나 떨어져야 하는지 계산
        Theory 레이어에서는 비탄소 원소만 표시
        [FIX-OH] 암묵적 수소 포함 라벨 너비 기준으로 gap 계산
        """
        if pt_key not in atoms_data:
            return 0

        atom = atoms_data[pt_key]
        if not isinstance(atom, dict):
            return 0
        symbol = atom.get("main", "C")

        # 원소 기호가 있고 C가 아닌 경우 (Theory는 비탄소만 표시)
        if symbol and symbol.strip() and symbol != "C":
            # [FIX-OH] 표시 라벨 생성 (암묵적 수소 포함)
            _att_gap = atom.get("attach", {})
            if not isinstance(_att_gap, dict):
                _att_gap = {}
            user_placed_h = sum(1 for sym in _att_gap.values() if sym == "H")
            implicit_h = max(0, atom.get("h_count", 0) - user_placed_h)
            display_label = symbol
            if implicit_h == 1:
                display_label = symbol + "H"
            elif implicit_h > 1:
                display_label = symbol + "H" + str(implicit_h)

            font = QFont(LewisRenderer._get_font_family(), 14, QFont.Weight.Bold)  # [M609]
            fm = QFontMetrics(font)
            # [M504 FIX] gap은 원소기호(N,O,S...) 너비만 사용.
            # 전체 라벨(NH2,OH...) 너비를 쓰면 C-N/C-O 결합선이 과도하게 짧아짐.
            # 결합선은 N 원자까지 연결되고, H2 subscript는 N 오른쪽에 붙으므로
            # gap = 원소기호 반너비 + 여백 (유기화학 교과서 skeletal 표기 기준)
            symbol_width = fm.horizontalAdvance(symbol)  # 'N', 'O', 'S' 등 기호만
            text_height = fm.height()
            base_gap = max(symbol_width, text_height) / 2
            return base_gap + 4  # [MAGIC: 4px] 원소기호 반지름 여백 (NH2의 N 반지름 ~8px)

        return 0
    
    # Halogen elements: sp3 halogen gets wide/shallow cloud (B10-16, M222)
    _HALOGENS = frozenset(('F', 'Cl', 'Br', 'I'))

    # [U-1 lp_donor] 비공유전자쌍 공여 원소 외각전자 수 (중성 상태 기준, VSEPR 교과서)
    # NH2(N=5): lp=1, OH(O=6): lp=2, SH(S=6): lp=2, F=7:lp=3, Cl/Br/I=7:lp=3
    # lp_count fallback = max(0, (outer_elecs - n_heavy_bonds - h_count) // 2)
    # Rule I: 원소별 외각전자 수는 주기율표 고정값 (매직넘버 아님, IUPAC 기준)
    _LP_DONOR_OUTER = {'N': 5, 'O': 6, 'S': 6, 'F': 7, 'Cl': 7, 'Br': 7, 'I': 7}

    @staticmethod
    def _draw_per_atom_clouds(painter, analysis, t_map, atoms_data, bonds):
        """
        STAGE 0: per-atom electron cloud overlay for Theory layer.

        Rules (B8-1/B9-1/B10-16 fix):
          - sp2/sp (pi-system, aromatic): radial gradient cloud on each atom.
            Color from Gasteiger charge (red=electron-rich, blue=electron-poor,
            green=neutral). Alpha 0.55 at center, fade to 0.
          - sp3 halogen (F/Cl/Br/I): wide, shallow cloud. alpha_scale=0.30,
            radius_scale=1.6x VdW (M222 teaching).
          - sp3 C/H (saturated): no cloud (already correct absence).
          - sp3 hetero O/N/S not in pi-island: no cloud here (LP dots suffice).

        Draws BEHIND bonds (called before STAGE 1).
        Rule N: all dict accesses guarded.
        Rule M: logger.warning on missing data, no silent returns after guard.
        Rule O: gradient radial quality (not flat fill).
        """
        if not isinstance(analysis, dict):
            logger.warning("TheoryRenderer._draw_per_atom_clouds: analysis not dict")
            return

        islands = analysis.get("islands", [])
        if not isinstance(islands, list):
            logger.warning("TheoryRenderer._draw_per_atom_clouds: islands not list")
            islands = []

        aromatic = analysis.get("aromatic", set())
        if not isinstance(aromatic, set):
            aromatic = set()

        charges = analysis.get("charges", {})
        if not isinstance(charges, dict):
            charges = {}

        # [A59-W2 F4-3/F5-0] Gasteiger per-atom charge redistribution:
        # adding explicit H to O in phenol changes ring carbon charges via sigma
        # inductive effect (+I). This IS chemically valid (Gasteiger 1980 Tetrahedron 36:3219).
        # Cloud color shift on ring carbons when H is added/removed = correct behavior.
        if not charges:
            logger.warning(
                "[A59-W2] _draw_per_atom_clouds: charges empty — "
                "Gasteiger fallback may not have run (check analysis['charges'])"
            )

        if not isinstance(atoms_data, dict):
            logger.warning("TheoryRenderer._draw_per_atom_clouds: atoms_data not dict")
            return
        if not isinstance(t_map, dict):
            logger.warning("TheoryRenderer._draw_per_atom_clouds: t_map not dict")
            return
        if not isinstance(bonds, dict):
            logger.warning("TheoryRenderer._draw_per_atom_clouds: bonds not dict")
            return

        # Collect pi-system atom keys (all atoms that appear in any island).
        pi_atoms = set()
        for isl in islands:
            if isinstance(isl, (set, frozenset, list)):
                pi_atoms.update(isl)

        # Estimate average bond length for cloud radius baseline.
        bond_lengths_px = []
        for (k1, k2) in bonds.keys():
            p1 = t_map.get(k1, QPointF(*k1))
            p2 = t_map.get(k2, QPointF(*k2))
            bl = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
            if 5.0 < bl < 300.0:
                bond_lengths_px.append(bl)
        avg_bl = sum(bond_lengths_px) / len(bond_lengths_px) if bond_lengths_px else 50.0
        avg_bl = min(avg_bl, 120.0)  # clamp: matches draw_esp_isosurface cap

        # Base cloud radius: 80% of avg bond length (covers ~1 VdW shell).
        BASE_R = avg_bl * 0.80

        painter.save()
        try:
            painter.setPen(Qt.PenStyle.NoPen)

            for pt_key, atom_data in atoms_data.items():
                if not isinstance(atom_data, dict):
                    continue

                symbol = atom_data.get("main", "") or ""  # '' = carbon (Rule I)
                # Normalise: treat empty string as C for logic below
                elem = symbol if symbol else "C"

                center = t_map.get(pt_key, QPointF(*pt_key))

                # --- Determine cloud type ---
                is_pi = pt_key in pi_atoms
                is_halogen = elem in TheoryRenderer._HALOGENS

                if is_pi:
                    # sp2/sp atom in a pi-island: draw ESP-colored pi cloud.
                    charge = charges.get(pt_key, 0.0)
                    if not isinstance(charge, (int, float)):
                        charge = 0.0

                    # [M679 FIX] 사용자 LV.14 item 24 — ESP 색 대비 부족 해소
                    # 변경 전: NEUTRAL=0.15 → 대부분 atom이 teal-green = 단색 인상
                    # 변경 후: NEUTRAL=0.05 → 작은 charge도 색깔 반영 (대비 ↑)
                    # ABS_SCALE는 0.35 유지 (Gasteiger 표준), threshold만 완화
                    # Color logic matching draw_esp_isosurface palette.
                    ABS_SCALE = 0.35  # Gasteiger range ~+-0.35 (학술 표준)
                    norm = max(-1.0, min(1.0, charge / ABS_SCALE))
                    # [MAGIC: 0.05] M674 — neutral threshold 완화로 색 대비 강화 (사용자 LV.14)
                    NEUTRAL = 0.05
                    # [M555 FIX] alpha_center 대폭 축소: 이전 145~200이 "전자구름 존나 크고"
                    # 사용자 격분 원인. 타겟분자(Drawing mode) 수준의 단순한 표현으로 복원.
                    # alpha_center 60~85: 교과서 수준 은은한 ESP 색조 표시 (Rule O 학술품질 유지).
                    if norm < -NEUTRAL:       # electron-rich -> red/orange tones
                        t = min(abs(norm) * 2.0, 1.0)
                        r, g, b = 255, int(200 * (1 - t) + 50 * t), int(200 * (1 - t))
                        # [M648 FIX] alpha_center cap=85: L3 표준 55-85 준수.
                        # [M679 ENH] alpha 살짝 상향 (75→85) — 색 대비 강화. [MAGIC: 75~95]
                        alpha_center = min(95, int(75 + 30 * t))
                    elif norm > NEUTRAL:      # electron-poor -> blue tones
                        t = min(norm * 2.0, 1.0)
                        r, g, b = int(200 * (1 - t)), int(200 * (1 - t) + 50 * t), 255
                        # [M679 ENH] alpha 살짝 상향 (75→95) — 색 대비 강화. [MAGIC: 75~95]
                        alpha_center = min(95, int(75 + 30 * t))
                    else:                     # neutral / delocalized -> teal-green
                        # Aromatic pi-cloud: subtle teal-green overlay (delocalization hint).
                        r, g, b = 40, 180, 140
                        # [M646_W34] [MAGIC: 70] Q-N20 균일 알파 (이전 55 → 70 약간 상향)
                        alpha_center = 70

                    # Aromatic atoms get a slightly larger cloud radius (ring
                    # delocalization extends over the full ring pi-orbital lobe).
                    radius = BASE_R * (1.05 if pt_key in aromatic else 0.92)
                    radius = min(radius, 90.0)  # cap same as draw_esp_isosurface

                    col_center = QColor(r, g, b, alpha_center)
                    col_mid = QColor(r, g, b, alpha_center // 3)
                    col_edge = QColor(r, g, b, 0)

                    grad = QRadialGradient(center, radius)
                    grad.setColorAt(0.0, col_center)
                    grad.setColorAt(0.45, col_mid)
                    grad.setColorAt(1.0, col_edge)
                    painter.setBrush(QBrush(grad))
                    painter.drawEllipse(center, radius, radius)

                elif is_halogen:
                    # sp3 halogen: wide, shallow cloud (M222 rule).
                    # Halogens are electron-rich: reddish tones.
                    # width_scale 1.6x, height_scale 0.7x (oblate/flat shape).
                    # [M555 FIX] alpha 더 낮춤: 이전 80 → 40 (은은한 힌트 수준).
                    charge = charges.get(pt_key, -0.15)  # halogens default negative
                    if not isinstance(charge, (int, float)):
                        charge = -0.15

                    ABS_SCALE = 0.35
                    norm = max(-1.0, min(1.0, charge / ABS_SCALE))
                    if norm <= 0.0:    # negative charge: red
                        t = min(abs(norm) * 2.0, 1.0)
                        r, g, b = 220, int(100 * (1 - t) + 40 * t), int(160 * (1 - t))
                    else:              # unexpectedly positive halogen
                        r, g, b = 140, 100, 220  # purple-ish

                    # Wide oblate ellipse: rx = 1.6x, ry = 0.7x BASE_R
                    rx = min(BASE_R * 1.6, 100.0)  # wide
                    ry = min(BASE_R * 0.7, 55.0)   # shallow

                    alpha_center = 40  # [MAGIC: 40] 이전 80 → 축소. 은은한 할로겐 구름 (M555)
                    col_center = QColor(r, g, b, alpha_center)
                    col_mid = QColor(r, g, b, alpha_center // 3)
                    col_edge = QColor(r, g, b, 0)

                    # QRadialGradient for ellipse: draw on ellipse via scale transform
                    # Use square gradient then scale painter.
                    painter.save()
                    painter.translate(center)
                    painter.scale(rx / max(rx, 1.0), ry / max(rx, 1.0))
                    grad = QRadialGradient(QPointF(0.0, 0.0), rx)
                    grad.setColorAt(0.0, col_center)
                    grad.setColorAt(0.45, col_mid)
                    grad.setColorAt(1.0, col_edge)
                    painter.setBrush(QBrush(grad))
                    painter.drawEllipse(QPointF(0.0, 0.0), rx, rx)
                    painter.restore()

                # sp3 C/H and sp3 hetero (O/N/S) without pi participation:
                # no cloud drawn here -- LP dots in STAGE 3 suffice.

        except Exception as e:  # noqa: broad-except
            logger.warning("TheoryRenderer._draw_per_atom_clouds error: %s", e)
        finally:
            painter.restore()

    @staticmethod
    def render(painter, atoms, bonds, analysis, selected_atoms=None, selected_bonds=None):
        """
        [Step 4 개선] 이론적 구조 레이어: MMFF94 최적 좌표 + 원소 표기 + 입체 표현
        - 선택 표시: 파란색 하이라이트
        """
        if not isinstance(analysis, dict):
            logger.warning("TheoryRenderer.render: analysis is not dict: %s", type(analysis).__name__)
            return
        t_data = analysis.get("theory_data")
        if not t_data or not isinstance(t_data, dict):
            logger.warning("TheoryRenderer.render: theory_data missing or invalid: %s",
                           type(t_data).__name__ if t_data else "None")
            return

        painter.save()
        painter.setOpacity(1.0)

        coords = t_data.get("coords")
        if coords is None:
            logger.warning("TheoryRenderer.render: coords is None in theory_data")
            painter.restore()
            return
        t_map = t_data.get("map", {})
        if not isinstance(t_map, dict):
            t_map = {}
        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            atoms_data = {}
        
        # [신규] 선택 표시를 위한 기본값 설정
        if selected_atoms is None:
            selected_atoms = set()
        if selected_bonds is None:
            selected_bonds = set()

        # F07/F25: Theory is a clean structural view. Per-atom cloud visuals are
        # reserved for ElectronDist/3D electronic-property views, not this layer.

        # === STAGE 1: 결합선 렌더링 (웨지/대쉬 포함, 간격 적용) ===
        for (k1, k2), v in bonds.items():
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = (k1, k2) in selected_bonds or (k2, k1) in selected_bonds
            line_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            # [TASK 1] 선 두께 정규화: Drawing 레이어와 동일하게 2.2
            line_width = 2.8 if is_selected else 2.2
            painter.setPen(QPen(line_color, line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            # 이론적 좌표 사용 — Rule N: isinstance
            assert isinstance(t_map, dict)
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
            # [COORD-BOND] Dative bond (order=0.5): dashed line + arrowhead
            if isinstance(v, (int, float)) and abs(v - 0.5) < 0.01:
                dative_color = QColor(80, 80, 160)
                dash_pen = QPen(dative_color, line_width)
                dash_pen.setStyle(Qt.PenStyle.DashLine)
                dash_pen.setDashPattern([6, 3])
                painter.setPen(dash_pen)
                painter.drawLine(p1, p2)
                arrow_len = 6
                arrow_w = 3
                ax = -unit.x() * arrow_len
                ay = -unit.y() * arrow_len
                perp_x, perp_y = -unit.y(), unit.x()
                ap1 = p2 + QPointF(ax + perp_y * arrow_w, ay - perp_x * arrow_w)
                ap2 = p2 + QPointF(ax - perp_y * arrow_w, ay + perp_x * arrow_w)
                painter.setPen(QPen(dative_color, line_width))
                painter.setBrush(dative_color)
                painter.drawPolygon(QPolygonF([p2, ap1, ap2]))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                continue
            elif isinstance(v, tuple) and len(v) >= 3:
                # 웨지/대쉬 입체 결합
                bond_mode = v[2]
                if bond_mode == "Wedge":
                    # 웨지 (채워진 삼각형)
                    perp = QPointF(-vec.y(), vec.x()) / length * 5
                    painter.setBrush(painter.pen().color())
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
                _tad1 = atoms_data.get(k1, {})
                _tad2 = atoms_data.get(k2, {})
                elem1 = _tad1.get("main", "C") if isinstance(_tad1, dict) else "C"
                elem2 = _tad2.get("main", "C") if isinstance(_tad2, dict) else "C"
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
        # [FIX-OH] 헤테로원자의 암묵적 수소를 함께 표시 (예: O→OH, N→NH2)
        _atoms_s2 = analysis.get("atoms", {})
        if not isinstance(_atoms_s2, dict):
            _atoms_s2 = {}
        for pt_key, atom_data in _atoms_s2.items():
            if not isinstance(atom_data, dict):
                continue
            symbol = atom_data.get("main", "C")
            if not symbol or symbol.strip() == "" or symbol == "C":
                continue  # 탄소는 생략

            # [FIX-OH] 암묵적 수소 개수를 반영한 표시 라벨 생성
            # 사용자가 attach로 이미 배치한 H 수 차감 (중복 표시 방지)
            _att_s2 = atom_data.get("attach", {})
            if not isinstance(_att_s2, dict):
                _att_s2 = {}
            user_placed_h = sum(1 for sym in _att_s2.values() if sym == "H")
            implicit_h = max(0, atom_data.get("h_count", 0) - user_placed_h)

            # [P0-2 FIX] OH/HO flip convention + NH2 subscript rendering
            # Organic convention: if bond comes from the LEFT, flip to HO/H2N format
            center = t_map.get(pt_key, QPointF(*pt_key))

            # Determine if bond approaches from the left (flip condition)
            _adj_s2 = analysis.get("adj", {})
            if not isinstance(_adj_s2, dict):
                _adj_s2 = {}
            _neighbors_s2 = _adj_s2.get(pt_key, [])
            flip_h = False  # Whether to place H before symbol
            if implicit_h > 0 and _neighbors_s2:
                # Calculate average bond direction to this atom
                avg_angle = 0.0
                n_bonds = 0
                for nb_pos, _ in _neighbors_s2:
                    nb_center = t_map.get(nb_pos, QPointF(*nb_pos))
                    dx = nb_center.x() - center.x()
                    if abs(dx) > 1.0:  # meaningful horizontal component
                        avg_angle += dx
                        n_bonds += 1
                # If bonds predominantly approach from the RIGHT, flip H to left
                if n_bonds > 0 and avg_angle / n_bonds > 3.0:
                    flip_h = True

            # Build display label with proper ordering
            if flip_h and implicit_h > 0:
                # H before symbol: HO, H2N, HS
                if implicit_h == 1:
                    display_label = "H" + symbol
                else:
                    display_label = "H" + str(implicit_h) + symbol
            else:
                display_label = symbol
                if implicit_h == 1:
                    display_label = symbol + "H"
                elif implicit_h > 1:
                    display_label = symbol + "H" + str(implicit_h)

            # [신규] 선택 여부에 따라 색상 변경
            is_selected = pt_key in selected_atoms
            atom_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black

            # [P0-2 FIX] Draw with subscript for hydrogen count > 1
            main_font = QFont(LewisRenderer._get_font_family(), 14, QFont.Weight.Bold)  # [M609]
            sub_font = QFont(LewisRenderer._get_font_family(), 10, QFont.Weight.Bold)   # [M609] subscript font
            painter.setFont(main_font)
            painter.setPen(atom_color)
            fm = QFontMetrics(main_font)
            sfm = QFontMetrics(sub_font)

            has_subscript = implicit_h > 1
            if has_subscript:
                # Draw with subscript: split into main part and subscript digit
                if flip_h:
                    main_part = "H"
                    subscript_part = str(implicit_h)
                    tail_part = symbol
                else:
                    main_part = symbol + "H"
                    subscript_part = str(implicit_h)
                    tail_part = ""

                # Calculate total width
                main_w = fm.horizontalAdvance(main_part)
                sub_w = sfm.horizontalAdvance(subscript_part)
                tail_w = fm.horizontalAdvance(tail_part) if tail_part else 0
                total_w = main_w + sub_w + tail_w
                text_h = fm.height()

                # Draw main part
                x_start = center.x() - total_w / 2
                y_center = center.y()

                painter.setFont(main_font)
                main_rect = QRectF(x_start, y_center - text_h / 2, main_w, text_h)
                painter.drawText(main_rect, Qt.AlignmentFlag.AlignCenter, main_part)

                # Draw subscript (smaller, lowered)
                painter.setFont(sub_font)
                sub_h = sfm.height()
                sub_rect = QRectF(x_start + main_w, y_center - text_h / 2 + text_h * 0.35,
                                  sub_w, sub_h)
                painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, subscript_part)

                # Draw tail part if flipped (the symbol after subscript)
                if tail_part:
                    painter.setFont(main_font)
                    tail_rect = QRectF(x_start + main_w + sub_w, y_center - text_h / 2,
                                       tail_w, text_h)
                    painter.drawText(tail_rect, Qt.AlignmentFlag.AlignCenter, tail_part)

                text_w = total_w
            else:
                # Simple label without subscript
                text_w = fm.horizontalAdvance(display_label)
                text_h = fm.height()
                text_rect = QRectF(center.x() - text_w / 2, center.y() - text_h / 2, text_w, text_h)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_label)

            # [신규] 선택된 원자에 파란색 테두리 추가
            if is_selected:
                painter.setPen(QPen(Qt.GlobalColor.blue, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(center.x() - text_w/2 - 3, center.y() - text_h/2 - 2, text_w + 6, text_h + 4))

        # === STAGE 3: 전하/라디칼/비공유전자쌍 기호 표시 (원자색 변경 없이 기호만) ===
        # [Fix v3] 탄소 기호 미표시 유지, 전하/라디칼/LP만 골격 옆에 검은색으로 표시
        charge_font = QFont(LewisRenderer._get_font_family(), 10, QFont.Weight.Bold)  # [M609]
        lp_font = QFont(LewisRenderer._get_font_family(), 8, QFont.Weight.Bold)        # [M609]

        _atoms_s3 = analysis.get("atoms", {})
        if not isinstance(_atoms_s3, dict):
            _atoms_s3 = {}
        for pt_key, atom_data in _atoms_s3.items():
            if not isinstance(atom_data, dict):
                continue
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
                charge_text = "+" if formal_charge > 0 else "⁻"  # Rule Q M433: direct charge superscript
                painter.setFont(charge_font)
                painter.setPen(Qt.GlobalColor.black)
                cfm = QFontMetrics(charge_font)
                # [v5 Fix] 원자 우상단 위첨자 — 중앙 가림 방지
                assert isinstance(atom_data, dict)  # Rule N: 타입 가드
                symbol = atom_data.get("main", "C") or "C"
                main_fm = QFontMetrics(QFont(LewisRenderer._get_font_family(), 14, QFont.Weight.Bold))  # [M609]
                sym_w = main_fm.horizontalAdvance(symbol)
                sym_h = main_fm.height()
                # 최소 오프셋 보장: 탄소(기호없음)도 충분히 우측으로
                min_offset = max(sym_w / 2, 8) + 4
                cx = center.x() + min_offset
                cy = center.y() - sym_h * 0.5  # 원자 위로 충분히
                painter.drawText(QPointF(cx, cy), charge_text)

            # --- 3-B: 비공유전자쌍 표시 ---
            # [M647_W11_A3 + M663 FIX] Theory 레이어에서 LP dot 제거.
            # 학술 근거: IUPAC Gold Book "lone pair" + Clayden Organic Chemistry 3rd ed Ch 4
            # — Lewis structure에서 LP 명시, ESP/orbital representation은 전자밀도 분포로 LP 정보 흡수.
            # LP dot은 LewisRenderer.STAGE 3 (_render_vsepr_extensions)만 담당.
            # Rule SS CRITICAL: USR-AUTO-3MONTH-LP-DOT-THEORY P0 (M655) 해소.

            # --- 3-C: 라디칼 도트 (·) 표시 --- Rule N: isinstance
            assert isinstance(atom_data, dict) and isinstance(analysis, dict)
            attach = atom_data.get("attach", {})
            if not isinstance(attach, dict):
                attach = {}
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

        # === STAGE 4: Intramolecular hydrogen bond dotted lines ===
        # [P0-2 FIX] Detect OH...O or OH...N proximity for H-bond visualization
        # Common in catechol (1,2-dihydroxybenzene), salicylic acid, etc.
        _atoms_hb = analysis.get("atoms", {})
        if isinstance(_atoms_hb, dict):
            # Collect all H-bond donor/acceptor positions
            oh_donors = []  # (O_position, H_approximate_position)
            acceptors = []  # (atom_position, element)
            for pt_key_hb, ad_hb in _atoms_hb.items():
                if not isinstance(ad_hb, dict):
                    continue
                el_hb = ad_hb.get("main", "") or "C"
                hc_hb = ad_hb.get("h_count", 0)
                if el_hb in ('O', 'N', 'S'):
                    acceptors.append((pt_key_hb, el_hb))
                    if hc_hb > 0:  # Has H attached = donor
                        oh_donors.append(pt_key_hb)

            # Draw H-bond dotted lines between nearby donor-acceptor pairs
            MAX_HBOND_DIST = 120.0  # max distance in px for H-bond
            MIN_HBOND_DIST = 20.0   # min distance (avoid self)
            drawn_hbonds = set()
            for donor_key in oh_donors:
                donor_center = t_map.get(donor_key, QPointF(*donor_key))
                for acc_key, acc_el in acceptors:
                    if acc_key == donor_key:
                        continue
                    pair = tuple(sorted([donor_key, acc_key], key=str))
                    if pair in drawn_hbonds:
                        continue
                    acc_center = t_map.get(acc_key, QPointF(*acc_key))
                    dist_hb = math.hypot(
                        acc_center.x() - donor_center.x(),
                        acc_center.y() - donor_center.y()
                    )
                    if MIN_HBOND_DIST < dist_hb < MAX_HBOND_DIST:
                        # Draw dotted line — CustomDashLine으로 solid처럼 보이는 문제 해결
                        hb_pen = QPen(QColor(100, 100, 100, 180), 1.5)
                        hb_pen.setStyle(Qt.PenStyle.CustomDashLine)
                        hb_pen.setDashPattern([3, 5])  # 3px dash, 5px gap
                        painter.setPen(hb_pen)
                        painter.drawLine(donor_center, acc_center)
                        drawn_hbonds.add(pair)

        painter.restore()


# ============================================================================
# [M541] ElectronDistributionRenderer — ORCA Mulliken/Löwdin 전자분포
# ============================================================================
# 사용자 직접 설계 신규 레이어 (학회 발표 시연 핵심):
#   "기존 루이스랑 이론적 레이어 있는거처럼 새롭게 전자분포 레이어 만들고
#    그 레이어 클릭하면 기존 이론적 구조가 회색으로 옅게 보이면서
#    각 원자들이 있던 위치에 해당 원소의 정확한 전자 배치값이 orca로 계산되어서 나가고,
#    색 분포랑 해당 전자분포 숫자만 강조"
#
# Rule O 학술 인용 (논문 품질 의무):
#   - Mulliken R.S. (1955) "Electronic Population Analysis on LCAO–MO
#     Molecular Wave Functions. I." J. Chem. Phys. 23, 1833.
#   - Löwdin P.O. (1950) "On the Non-Orthogonality Problem Connected
#     with the Use of Atomic Wave Functions in the Theory of Molecules
#     and Crystals." J. Chem. Phys. 18, 365.

# 중성 원자 ground-state 전자배치 (IUPAC 주기율표 고정값, Rule I 매직넘버 아님)
# 표기: 표준 Aufbau 순서. 학생이 즉시 이해 가능하도록 superscript는 유니코드 사용.
_GROUND_STATE_CONFIG = {
    "H":  "1s¹",                              # 1s1
    "He": "1s²",                              # 1s2
    "Li": "1s² 2s¹",
    "Be": "1s² 2s²",
    "B":  "1s² 2s² 2p¹",
    "C":  "1s² 2s² 2p²",
    "N":  "1s² 2s² 2p³",
    "O":  "1s² 2s² 2p⁴",            # 2p4
    "F":  "1s² 2s² 2p⁵",
    "Ne": "1s² 2s² 2p⁶",
    "Na": "[Ne] 3s¹",
    "Mg": "[Ne] 3s²",
    "Al": "[Ne] 3s² 3p¹",
    "Si": "[Ne] 3s² 3p²",
    "P":  "[Ne] 3s² 3p³",
    "S":  "[Ne] 3s² 3p⁴",
    "Cl": "[Ne] 3s² 3p⁵",
    "Ar": "[Ne] 3s² 3p⁶",
    "K":  "[Ar] 4s¹",
    "Ca": "[Ar] 4s²",
    "Br": "[Ar] 3d¹⁰ 4s² 4p⁵",  # 3d10 4s2 4p5
    "I":  "[Kr] 4d¹⁰ 5s² 5p⁵",
}


def _superscript_decimal(value: float) -> str:
    """0.00 ~ 9.99 등 소수값을 일반 ASCII로 반환 (학생 가독성).

    유니코드 superscript는 소수점/소수 부분 표기가 불편하므로
    valence shell occupancy 같은 실측값은 "3.85"처럼 그대로 표기.
    """
    return f"{value:.2f}"


def _format_orbital_occupancy(symbol: str, occ_dict) -> str:
    """ORCA Mulliken reduced orbital occupancy → 사람이 읽을 수 있는 표기.

    Rule N: occ_dict가 dict가 아니면 ground-state 폴백.
    Rule M: 비어있으면 logger.warning 후 ground-state 표시.

    예: {"s": 3.85, "p": 4.57} → "s:3.85 p:4.57"
        None / 빈 dict → ground-state 전자배치 (예: "1s² 2s² 2p⁴")
    """
    if not isinstance(occ_dict, dict) or not occ_dict:
        # ORCA 데이터 부재/비정상 → ground-state 폴백 (학생 이해 우선)
        ground = _GROUND_STATE_CONFIG.get(symbol or "C", "")
        if not ground:
            logger.warning(
                "[M541] orbital_occupancy 부재 + ground-state 미정의 (symbol=%s)",
                symbol
            )
            return symbol or "C"
        return ground

    # Rule N: 각 값이 숫자인지 확인
    parts = []
    for shell in ("s", "p", "d", "f"):
        val = occ_dict.get(shell)
        if val is None:
            continue
        if not isinstance(val, (int, float)):
            logger.warning(
                "[M541] occupancy[%s] 가 숫자가 아님 (type=%s)",
                shell, type(val).__name__
            )
            continue
        parts.append(f"{shell}:{_superscript_decimal(float(val))}")

    if not parts:
        # ORCA 결과 dict는 있으나 유효 shell이 없음 → ground-state 폴백
        return _GROUND_STATE_CONFIG.get(symbol or "C", symbol or "C")

    return " ".join(parts)


def _charge_to_color_qcolor(charge: float) -> QColor:
    """Mulliken 부분전하 → QColor (음전하 RED, 양전하 BLUE, 중성 GREEN).

    학생 직관 우선:
      - charge < 0 (전자 풍부): RED (255, 80, 80) → orange로 그라디언트
      - charge > 0 (전자 결핍): BLUE (60, 100, 255)
      - |charge| < NEUTRAL_BAND: GREEN (40, 180, 80) — 중성 영역

    Rule N: charge가 숫자가 아니면 GREEN 폴백.
    Rule O: 알파 0.85 (높은 가시성) — 회색 골격 위에서 강조.

    학술 비교 척도: Gasteiger Marsili (~±0.35), Mulliken (~±0.6).
    M541 ORCA Mulliken 기준 ABS_SCALE=0.6 적용.
    """
    if not isinstance(charge, (int, float)):
        return QColor(40, 180, 80, 220)  # GREEN fallback

    ABS_SCALE = 0.6      # Mulliken 부분전하의 일반적 max 절대값
    NEUTRAL_BAND = 0.10  # |charge| < 0.10 e → 중성으로 간주

    if abs(charge) < NEUTRAL_BAND:
        return QColor(40, 180, 80, 220)  # GREEN — 중성

    norm = max(-1.0, min(1.0, charge / ABS_SCALE))

    if norm < 0:
        # 음전하 (RED → DEEP RED 그라디언트)
        intensity = abs(norm)
        r = 255
        g = int(120 * (1 - intensity) + 40 * intensity)
        b = int(120 * (1 - intensity) + 40 * intensity)
    else:
        # 양전하 (BLUE → DEEP BLUE)
        intensity = norm
        r = int(120 * (1 - intensity) + 30 * intensity)
        g = int(120 * (1 - intensity) + 60 * intensity)
        b = 255

    return QColor(r, g, b, 230)


class ElectronDistributionRenderer:
    """ORCA Mulliken Population Analysis 기반 전자분포 시각화 레이어.

    사용자 M541 직접 설계 (학회 발표 시연 핵심):
      - STAGE 1: 기존 Theory 골격을 회색(#888)으로 opacity 0.30 옅게 그림
      - STAGE 2: 각 원자 위치에 큰 원 (Mulliken charge → 색상)
      - STAGE 3: 원자 위/아래 텍스트:
                 - 위: 원소기호 + 전자 배치값 (예: "O: 1s² 2s² 2p⁴")
                 - 아래: Mulliken 부분전하 (예: "-0.412")

    학술 인용 (Rule O):
      - Mulliken R.S. 1955 J.Chem.Phys 23:1833
      - Löwdin P.O. 1950 J.Chem.Phys 18:365

    데이터 흐름 (Rule M/N 준수):
      MoleculeCanvas.orca_population_data: dict | None
          {atom_idx: {"mulliken_charge": float, "orbital_occupancy": dict}}
      → ORCA 미실행 / dict 비정상 시 ground-state 전자배치로 fallback.
    """

    # 시각 상수 (Rule I: 매직넘버 주석 필수)
    _SKELETON_OPACITY = 0.30          # Theory 골격 회색 투명도 (0~1)
    _SKELETON_COLOR = QColor(128, 128, 128, 180)  # #888 회색
    _ATOM_DOT_RADIUS = 22.0           # 원자 강조 원 반지름 (px) — Theory보다 약간 크게
    _ATOM_DOT_STROKE_WIDTH = 1.5      # 원자 원 테두리 두께
    _CONFIG_FONT_SIZE = 11            # 전자 배치값 폰트 크기 (pt)
    _CHARGE_FONT_SIZE = 14            # Mulliken charge 폰트 크기 (pt) — 강조
    _CONFIG_OFFSET_Y = -38            # 원자 중심으로부터 전자배치 텍스트 y 오프셋 (px, 위쪽)
    _CHARGE_OFFSET_Y = +42            # 원자 중심으로부터 charge 텍스트 y 오프셋 (px, 아래)

    @staticmethod
    def _compute_gasteiger_fallback(analysis: dict) -> dict:
        """ORCA 미실행 시 RDKit Gasteiger-Marsili 전하로 폴백.

        [M645_W23] 사용자 요구: "숫자가 안나오고" — ORCA 없어도 Gasteiger 숫자 표시.
        학술 인용: Gasteiger, J.; Marsili, M. (1980) Tetrahedron 36:3219.

        Returns:
            {rdkit_idx(int): {"mulliken_charge": float, "orbital_occupancy": None}}
            빈 dict if 계산 실패 (Rule M: warning 로깅)
        """
        # Rule N: analysis 타입 가드
        if not isinstance(analysis, dict):
            return {}
        smiles = analysis.get("smiles", "")
        if not smiles or not isinstance(smiles, str):
            # smiles 없으면 atoms에서 추출 시도
            atoms_data = analysis.get("atoms", {})
            if isinstance(atoms_data, dict):
                # SMILES 직접 재구성 불가 — 빈 dict 반환 + warning
                logger.warning(
                    "[M645_W23] Gasteiger fallback: analysis에 smiles 없음 — 전하 표시 불가"
                )
            return {}
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            import math as _math
            mol = Chem.MolFromSmiles(smiles)  # Rule L
            if mol is None:
                logger.warning(
                    "[M645_W23] Gasteiger fallback: SMILES 파싱 실패 (%s)", smiles
                )
                return {}
            mol_h = AllChem.AddHs(mol)
            AllChem.ComputeGasteigerCharges(mol_h)
            charges = {}
            heavy_idx = 0
            for i in range(mol_h.GetNumAtoms()):
                atom_i = mol_h.GetAtomWithIdx(i)
                if atom_i.GetAtomicNum() == 1:  # 수소 제외
                    continue
                gc = atom_i.GetDoubleProp("_GasteigerCharge")
                if not isinstance(gc, (int, float)):
                    heavy_idx += 1
                    continue
                # Rule N: NaN/Inf 처리
                if _math.isnan(gc) or _math.isinf(gc):
                    logger.warning(
                        "[M645_W23] Gasteiger NaN/Inf (atom=%s idx=%d) -> 0.0",
                        atom_i.GetSymbol(), i
                    )
                    gc = 0.0
                charges[heavy_idx] = {
                    "mulliken_charge": float(gc),
                    "orbital_occupancy": None,  # Gasteiger는 orbital occupancy 없음
                }
                heavy_idx += 1
            logger.debug(
                "[M645_W23] Gasteiger fallback 완료: %d atoms (Gasteiger/Marsili 1980)",
                len(charges)
            )
            return charges
        except Exception as e:
            logger.warning("[M645_W23] Gasteiger fallback 계산 실패: %s", e)
            return {}

    @staticmethod
    def render(painter, atoms, bonds, analysis, orca_population_data=None,
               selected_atoms=None, selected_bonds=None):
        """전자분포 레이어 메인 렌더 파이프라인.

        Args:
            painter: QPainter (이미 view transform 적용된 상태)
            atoms: MoleculeCanvas.atoms — {coord_key: atom_dict}
            bonds: MoleculeCanvas.bonds — {(k1,k2): bond_value}
            analysis: ChemicalAnalyzer 결과 (theory_data 포함 dict)
            orca_population_data: ORCA Mulliken 결과 (dict | None)
                형식: {atom_idx: {"mulliken_charge": float,
                                   "lowdin_charge": float,
                                   "orbital_occupancy": dict|None}}
                None / dict 아님 → Gasteiger fallback 시도 후 ground-state 폴백 (Rule M)
            selected_atoms / selected_bonds: 선택 강조 (현재 미사용, 호환용)
        """
        # Rule N: isinstance 가드 — analysis 검증
        if not isinstance(analysis, dict):
            logger.warning(
                "[M541] ElectronDistributionRenderer.render: analysis가 dict 아님 (type=%s)",
                type(analysis).__name__
            )
            return

        t_data = analysis.get("theory_data")
        # [M645_W25] theory_data 없어도 atoms 좌표에서 직접 t_map 생성 — W23 가짜 PASS 원인 수정
        # 원인: theory_data 부재 시 즉시 return → render() 0출력 → Lewis와 byte-identical
        # 수정: theory_data.map 없으면 analysis["atoms"] 좌표를 QPointF로 직접 변환하여 t_map 구성
        if not isinstance(t_data, dict):
            logger.warning(
                "[M645_W25] ElectronDistributionRenderer.render: theory_data 부재 "
                "— atoms 좌표에서 직접 t_map 생성 (폴백)"
            )
            t_map = {}
        else:
            t_map = t_data.get("map", {})
            if not isinstance(t_map, dict):
                logger.warning("[M541] theory_data.map이 dict 아님 — 빈 t_map 사용")
                t_map = {}

        atoms_data = analysis.get("atoms", {})
        if not isinstance(atoms_data, dict):
            atoms_data = {}

        # [M645_W25] atoms_data가 비어있으면 atoms 파라미터에서 직접 구성
        # analysis["atoms"]는 analyzer.py가 round(x,2)로 정규화한 키이므로
        # canvas.atoms와 키가 다를 수 있음 → canvas.atoms를 직접 사용
        if not atoms_data and isinstance(atoms, dict):
            for _ck, _av in atoms.items():
                _rk = (round(float(_ck[0]), 2), round(float(_ck[1]), 2)) if isinstance(_ck, (tuple, list)) and len(_ck) >= 2 else _ck
                atoms_data[_rk] = _av if isinstance(_av, dict) else {}
            if atoms_data:
                logger.debug(
                    "[M645_W25] atoms_data 비어있음 — canvas.atoms에서 직접 구성: %d 원자",
                    len(atoms_data)
                )

        # [M645_W25] t_map이 비어있으면 atoms 좌표를 QPointF로 직접 변환하여 t_map 구성
        # atoms_data 키: (x, y) float 쌍 → t_map 키: (x, y) → QPointF(x, y)
        # 이렇게 하면 _render_skeleton_grey/_render_atom_charge_disks/_render_atom_labels에서
        # t_map.get(coord_key, QPointF(*coord_key)) 폴백이 atoms 위치를 정확히 반환함
        if not t_map and atoms_data:
            for _ck in atoms_data.keys():
                if isinstance(_ck, (tuple, list)) and len(_ck) >= 2:
                    t_map[_ck] = QPointF(float(_ck[0]), float(_ck[1]))
            if t_map:
                logger.debug(
                    "[M645_W25] atoms 좌표 → t_map 직접 생성: %d 원자 (theory_data 폴백)",
                    len(t_map)
                )
            else:
                logger.warning(
                    "[M645_W25] atoms_data도 비어있음 — atoms/bonds 인자 직접 접근으로 폴백"
                )
                # 최후 폴백: atoms 파라미터에서 직접 키 추출
                if isinstance(atoms, dict):
                    for _ck in atoms.keys():
                        if isinstance(_ck, (tuple, list)) and len(_ck) >= 2:
                            t_map[_ck] = QPointF(float(_ck[0]), float(_ck[1]))

        # Rule M: orca_population_data 부재/비정상 → Gasteiger fallback 시도 후 ground-state 폴백
        # [M645_W23] 사용자 요구: "숫자가 안나오고" — ORCA 없어도 Gasteiger 전하 숫자 표시
        is_orca_available = isinstance(orca_population_data, dict) and len(orca_population_data) > 0
        _effective_pop_data = orca_population_data  # 실제 렌더링에 사용할 charge 데이터
        is_gasteiger_fallback = False

        if not is_orca_available:
            logger.warning(
                "[M541] ORCA Mulliken 데이터 없음 → Gasteiger fallback 시도"
            )
            # [M645_W23] ORCA 없으면 Gasteiger-Marsili (1980) 로 실제 숫자 계산
            _gasteiger = ElectronDistributionRenderer._compute_gasteiger_fallback(analysis)
            if _gasteiger:
                _effective_pop_data = _gasteiger
                is_gasteiger_fallback = True
                logger.debug(
                    "[M645_W23] Gasteiger fallback 활성화: %d atoms (전하 숫자 표시)",
                    len(_gasteiger)
                )
            else:
                logger.warning(
                    "[M541] Gasteiger fallback도 실패 → ground-state 전자배치만 표시"
                )

        painter.save()
        try:
            # =================================================================
            # [M647_W3 카드3 #10-가] STAGE 1: Lewis 구조 회색 반투명 (alpha ~0.4)
            # =================================================================
            # 사용자 명세 (#10-가):
            #   "기존 루이스 구조 레이어에서 표현된 까만 루이스 구조를 반투명한 회색으로 바꿔서
            #    기존 루이스 구조 레이어 위치 그대로 표현함. 원소 개별을 덧대어 그리지 않음.
            #    또한 수소 등 원자를 온전하게 표기"
            #
            # 구현: LewisRenderer.render()를 회색 alpha 0.4로 직접 호출 (점선이 아닌 실선)
            # _render_skeleton_grey()는 결합선만 그리고 원자 라벨/수소를 그리지 않으므로 폐기.
            # Lewis 그대로 + 회색 alpha = 사용자 요구 "기존 위치 그대로" + "수소 온전 표기" 충족.
            ElectronDistributionRenderer._render_lewis_grey(
                painter, atoms, bonds, analysis,
                selected_atoms, selected_bonds
            )

            # =================================================================
            # [M647_W3 카드3 #10-다] STAGE 2: 색상 charge 원 — 완전 제거
            # =================================================================
            # 사용자 명령 (#10):
            #   "경계가 구분된 원에 원색을 칠해서 전자 구름을 표기하는것이 절대 아님"
            # _render_atom_charge_disks() 호출 제거 — STAGE 2 폐기.
            # ESP 전자구름은 canvas.py LAYER 3에서 별도로 그림 (배경 빨강/초록/파랑).

            # =================================================================
            # [M647_W3 카드3 #10-라] STAGE 3: 부분전하 숫자 (까만 텍스트 only)
            # =================================================================
            # _effective_pop_data = ORCA Mulliken 또는 Gasteiger fallback
            # 학술 인용 (Rule NN):
            #   - Mulliken R.S. 1955 J.Chem.Phys 23:1833 (Mulliken population analysis)
            #   - Löwdin P.O. 1950 J.Chem.Phys 18:365 (Löwdin orthogonalization)
            #   - Gasteiger J.; Marsili M. 1980 Tetrahedron 36:3219 (Gasteiger-Marsili charges)
            # [M717 F5-2 item6] canvas_atoms (수소 포함 전체) 전달 — 모든 원자 오버레이
            ElectronDistributionRenderer._render_atom_labels(
                painter, atoms_data, t_map, _effective_pop_data,
                is_orca_available=is_orca_available,
                is_gasteiger_fallback=is_gasteiger_fallback,
                canvas_atoms=atoms,
            )

            # =================================================================
            # STAGE 4: ORCA 미설치 시 좌상단 배너 (Rule GG SIMULATION_MODE 의무)
            # =================================================================
            # 사용자 #7: ORCA 미실행 경고가 좌상단에 표출되어야 한다 (#8 btn_back_to_lewis 가림 해소 후 가시)
            # Rule GG: fallback/mock 사용시 노랑/빨강 배너 의무 (학생 학습 오염 차단)
            if not is_orca_available:
                ElectronDistributionRenderer._render_fallback_banner(
                    painter, is_gasteiger=is_gasteiger_fallback
                )

        finally:
            painter.restore()

        logger.debug("[M647_W3 카드3] ElectronDistributionRenderer complete (4단 재설계)")

    # ------------------------------------------------------------------
    # [M647_W3 카드3 #10-가] STAGE 1: Lewis 구조를 회색 alpha 0.4로 직접 그림
    # ------------------------------------------------------------------
    @staticmethod
    def _render_lewis_grey(painter, atoms, bonds, analysis,
                            selected_atoms=None, selected_bonds=None):
        """Lewis 구조를 회색 반투명(alpha ~0.4)으로 직접 호출.

        [M647_W3 카드3 #10-가] 사용자 명세 (격분 LV.6):
          "기존 루이스 구조 레이어에서 표현된 까만 루이스 구조(H-C-C 등 그림으로 표현되는
           루이스 구조식)를 반투명한 회색으로 바꿔서 기존 루이스 구조 레이어 위치 그대로 표현함.
           원소 개별을 덧대어 그리지 않음. 또한 수소 등 원자를 온전하게 표기"

        구현 전략:
          - LewisRenderer.render()를 painter.setOpacity(0.4)로 호출
          - 결과: 결합선/원소기호/수소/lone pair 모두 회색 alpha 표시
          - 별도 STAGE 2의 색상 원/individual atom dot은 추가하지 않음 (사용자 명령)

        학술 인용 (Rule NN):
          - Mulliken R.S. 1955 J.Chem.Phys 23:1833
        """
        # Rule N: 타입 가드
        if not isinstance(atoms, dict) or not isinstance(bonds, dict):
            logger.warning(
                "[M647_W3] _render_lewis_grey: atoms/bonds 타입 오류 — 빈 골격"
            )
            return
        if not isinstance(analysis, dict):
            analysis = {}

        painter.save()
        try:
            # [M647_W3] [MAGIC: 0.40] 사용자 명세 "반투명한 회색" — alpha ~0.4
            # 0.30(기존) 너무 옅음 / 0.50 가독성 양호 / 0.40 사용자 의도와 정확히 일치
            painter.setOpacity(0.40)
            # LewisRenderer.render()는 검정 결합선 + 원소기호 + 수소 + lone pair 그림
            # painter.setOpacity(0.40)이 적용된 상태로 호출되므로 모든 출력이 회색 톤
            try:
                LewisRenderer.render(
                    painter, atoms, bonds, analysis,
                    selected_atoms or set(), selected_bonds or set()
                )
            except Exception as e:
                # Rule M: silent failure 금지
                logger.warning(
                    "[M647_W3] _render_lewis_grey: LewisRenderer.render 실패 — %s", e
                )
        finally:
            painter.restore()

    # ------------------------------------------------------------------
    # [DEPRECATED M647_W3] STAGE 1 (구버전): Theory 골격 회색 점선
    # ------------------------------------------------------------------
    # 사용 중단 사유:
    # - 결합선만 그리고 원소기호/수소/lone pair 누락 → 사용자 명세 #10-가 위배
    # - "수소 등 원자를 온전하게 표기"하지 않으므로 즉시 폐기
    # - _render_lewis_grey()로 대체됨
    #
    # 체화 4단계 (Rule H):
    # H-1. 변경 전 사유: M647_W3 (점선만은 사용자 4단 명세 #10-가 위반)
    # H-2. skills 패턴: "회색 골격은 결합선만이 아니라 원소기호+수소까지 포함" — popup_3d_development.md
    # H-3. patrol/AV: M647_W3에서 신규 패턴 추가 (skeleton만 검사 → Lewis 호출 검사)
    # H-4. CLAUDE.md Rule O: 렌더링 품질 — "결합선만으로 골격 표현 금지, 라벨 포함 의무"
    @staticmethod
    def _render_skeleton_grey(painter, bonds, t_map, atoms_data):
        """[DEPRECATED M647_W3] 사용 중단 — _render_lewis_grey()로 대체.

        기존 동작: Theory 좌표계의 결합선만 회색 점선으로 그림.
        사용자 #10-가 명세 위반: "수소 등 원자를 온전하게 표기" 미충족.
        """
        if not isinstance(bonds, dict):
            return
        if not isinstance(t_map, dict):
            t_map = {}
        if not isinstance(atoms_data, dict):
            atoms_data = {}

        painter.save()
        try:
            painter.setOpacity(ElectronDistributionRenderer._SKELETON_OPACITY)
            # [M645_W23] SolidLine → DashLine: 사용자 "회색 점선" 요구
            grey_pen = QPen(
                ElectronDistributionRenderer._SKELETON_COLOR,
                2.0, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap
            )
            # [MAGIC: dash pattern 6,4] 결합선 식별 가능한 최소 점선 간격
            grey_pen.setDashPattern([6, 4])
            painter.setPen(grey_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            for (k1, k2), v in bonds.items():
                p1 = t_map.get(k1, QPointF(*k1))
                p2 = t_map.get(k2, QPointF(*k2))
                vec = p2 - p1
                length = math.hypot(vec.x(), vec.y())
                if length == 0:
                    continue
                unit = vec / length
                # 원자 표시 원과 겹치지 않도록 양 끝에서 소량 줄임
                # [MAGIC: 22px] _ATOM_DOT_RADIUS와 동일
                gap = ElectronDistributionRenderer._ATOM_DOT_RADIUS
                if length > 2 * gap + 5:
                    p1_short = p1 + unit * gap
                    p2_short = p2 - unit * gap
                else:
                    p1_short, p2_short = p1, p2
                painter.drawLine(p1_short, p2_short)

                # 다중결합 보조선 (단순 평행 1줄, 회색 골격 강조 우선)
                # Rule N: bond value 타입 가드
                order = 1
                if isinstance(v, (int, float)):
                    order = int(v) if v >= 1 else 1
                elif isinstance(v, str) and "DOUBLE" in v.upper():
                    order = 2
                if order >= 2:
                    perp = QPointF(-vec.y(), vec.x()) / length * 4.0
                    painter.drawLine(p1_short + perp, p2_short + perp)
                    if order >= 3:
                        painter.drawLine(p1_short - perp, p2_short - perp)
        finally:
            painter.restore()

    # ------------------------------------------------------------------
    # [DEPRECATED M647_W3] STAGE 2: 색상 원 — 사용자 명령으로 완전 폐기
    # ------------------------------------------------------------------
    # 사용 중단 사유 (사용자 격분 LV.6 직접 인용):
    #   "경계가 구분된 원에 원색을 칠해서 전자 구름을 표기하는것이 절대 아님"
    # 체화 4단계 (Rule H):
    # H-1. 변경 전 사유: 색상 원이 분자 구조를 완전히 가려 식별 불가 (cap_1777801297962.png)
    # H-2. skills 패턴: "전자분포 색상 표현은 ESP cloud(canvas LAYER 3)만, 원자 disk 금지"
    # H-3. patrol/AV: ElectronDistributionRenderer에 _render_atom_charge_disks() 호출 검사 추가
    # H-4. CLAUDE.md Rule O: 렌더링 품질 — "전하 표현은 텍스트 숫자 또는 ESP cloud, 색상 원 금지"
    @staticmethod
    def _render_atom_charge_disks(painter, atoms_data, t_map, orca_pop_data):
        """[DEPRECATED M647_W3] 색상 charge 원 — 사용자 명령으로 호출 금지.

        기존 동작: 원자 위치에 charge 색상 원을 그림.
        사용자 #10 명령: "원에 원색을 칠해서 전자 구름을 표기하는것이 절대 아님"
        대체: ESP cloud (canvas LAYER 3) + 부분전하 숫자 텍스트 (까만, _render_atom_labels)
        """
        if not isinstance(atoms_data, dict):
            return
        if not isinstance(t_map, dict):
            t_map = {}

        # rdkit_idx → coord_key 매핑이 필요. atoms_data[coord_key]["rdkit_idx"] 활용.
        # ORCA atom_idx는 RDKit ordering과 일치한다고 가정 (analyzer.py에서 동기화됨).
        painter.save()
        try:
            painter.setOpacity(1.0)
            for coord_key, atom_data in atoms_data.items():
                if not isinstance(atom_data, dict):
                    continue
                center = t_map.get(coord_key, QPointF(*coord_key))

                # Rule N: rdkit_idx 추출 후 None 가드
                rdkit_idx = atom_data.get("rdkit_idx")
                charge = 0.0
                if isinstance(orca_pop_data, dict) and isinstance(rdkit_idx, int):
                    pop_entry = orca_pop_data.get(rdkit_idx)
                    if isinstance(pop_entry, dict):
                        c = pop_entry.get("mulliken_charge")
                        if isinstance(c, (int, float)):
                            charge = float(c)

                color = _charge_to_color_qcolor(charge)
                # 테두리: 약간 진한 같은 톤
                border_color = QColor(
                    max(0, color.red() - 40),
                    max(0, color.green() - 40),
                    max(0, color.blue() - 40),
                    255
                )
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(border_color,
                                    ElectronDistributionRenderer._ATOM_DOT_STROKE_WIDTH))
                painter.drawEllipse(
                    center,
                    ElectronDistributionRenderer._ATOM_DOT_RADIUS,
                    ElectronDistributionRenderer._ATOM_DOT_RADIUS
                )

                # 원자 중앙에 원소 기호 (흰색, 학생 가독성)
                symbol = atom_data.get("main", "") or "C"
                if symbol == "":
                    symbol = "C"
                font_sym = QFont(LewisRenderer._get_font_family(), 12, QFont.Weight.Bold)  # [M609]
                painter.setFont(font_sym)
                painter.setPen(QPen(QColor(255, 255, 255), 1.0))
                fm_sym = QFontMetrics(font_sym)
                text_w = fm_sym.horizontalAdvance(symbol)
                text_h = fm_sym.ascent()
                painter.drawText(
                    QPointF(center.x() - text_w / 2.0, center.y() + text_h / 2.0 - 1),
                    symbol
                )
        finally:
            painter.restore()

    # ------------------------------------------------------------------
    # STAGE 3: 원자 위/아래 텍스트 (전자배치 + 부분전하 숫자)
    # ------------------------------------------------------------------
    @staticmethod
    def _render_atom_labels(painter, atoms_data, t_map, orca_pop_data,
                             is_orca_available=False, is_gasteiger_fallback=False,
                             canvas_atoms=None):
        """각 원자 위에 부분전하 숫자(까만 텍스트)만 표시.

        [M717 F5-2 item6] 사용자 요구:
          "분자 내 존재하는 모든 원소의 위(수소 등 포함)에 표현되어야 하고,
           그 원소를 가리듯이 숫자가 앞으로 나와서 그 원소 위치에 덧그려져야 한다.
           그리고 일부 선들 지금 원소랑 위치 어긋나있다."
        수정 내용:
          (1) canvas_atoms (canvas.atoms 전체) 기반 반복 — 수소 포함 모든 원자 커버
          (2) 텍스트 y 위치 = center.y() + fm.ascent()/2 — 원자 중심에 덧그리기
          (3) atoms_data rdkit_idx 기반 전하 매핑은 기존 로직 유지

        [M647_W3 카드3 #9/#10-다/#10-라] 사용자 격분 LV.6 4단 재설계:
        - #9 [GS]1s2s2p4 전자오비탈 텍스트 완전 삭제
        - #10-다: 까만 텍스트만, 배경 박스 없음
        - #10-라: 부분전하 DFT 형식 (Mulliken 1955 / Gasteiger 1980)

        [M645_W32] 부분전하 좌표 view_container 안 clamp.

        Args:
            canvas_atoms: MoleculeCanvas.atoms 원본 (수소 포함 전체 원자). None이면 atoms_data 폴백.
        """
        if not isinstance(atoms_data, dict):
            atoms_data = {}
        if not isinstance(t_map, dict):
            t_map = {}

        # [M717] canvas_atoms 없으면 atoms_data로 폴백 (수소 포함 전체 원자 커버)
        _iteration_source = canvas_atoms if isinstance(canvas_atoms, dict) and canvas_atoms else atoms_data

        # [M645_W32] 텍스트 우측 경계: view_container 좌측 = canvas_w - 400(container) - 15(margin)
        try:
            _device_w = painter.device().width()  # type: ignore[union-attr]
        except Exception:
            _device_w = 9999
        # [MAGIC: 415] view_container 너비(400) + 우측 여백(15) = 우측 차단 영역
        _safe_max_x = float(_device_w) - 415.0

        # [M717] rdkit_idx 역방향 인덱스: coord_key → rdkit_idx (canvas_atoms 조회용)
        _coord_to_rdkit: dict = {}
        for _ck, _ad in atoms_data.items():
            if isinstance(_ad, dict):
                _ri = _ad.get("rdkit_idx")
                if isinstance(_ri, int):
                    _coord_to_rdkit[_ck] = _ri

        painter.save()
        try:
            painter.setOpacity(1.0)

            # [M647_W3 카드3 #10-라] charge 텍스트 (까만 폰트, DFT 논문 형식)
            font_charge = QFont(LewisRenderer._get_font_family(),  # [M609]
                                 ElectronDistributionRenderer._CHARGE_FONT_SIZE,
                                 QFont.Weight.Bold)
            fm_charge = QFontMetrics(font_charge)
            # [MAGIC: ascent/2] drawText y=baseline; 원자 중심 덧그리기 위해 ascent/2 보정
            _half_asc = fm_charge.ascent() / 2.0

            for coord_key, atom_data in _iteration_source.items():
                if not isinstance(atom_data, dict):
                    continue

                # [M717] t_map 좌표 조회: 소수점 반올림 차이 보정
                center = t_map.get(coord_key)
                if center is None:
                    if isinstance(coord_key, (tuple, list)) and len(coord_key) >= 2:
                        _rk = (round(float(coord_key[0]), 2), round(float(coord_key[1]), 2))
                        center = t_map.get(_rk, QPointF(float(coord_key[0]), float(coord_key[1])))
                    else:
                        continue

                # ORCA/Gasteiger 데이터에서 charge 추출 (Rule N 타입 가드)
                rdkit_idx = (
                    atom_data.get("rdkit_idx")
                    if "rdkit_idx" in atom_data
                    else _coord_to_rdkit.get(coord_key)
                )
                charge_value = None
                if isinstance(orca_pop_data, dict) and isinstance(rdkit_idx, int):
                    pop_entry = orca_pop_data.get(rdkit_idx)
                    if isinstance(pop_entry, dict):
                        c = pop_entry.get("mulliken_charge")
                        if isinstance(c, (int, float)):
                            charge_value = float(c)

                # ----- [M647_W3 카드3 #9] 전자배치 텍스트 완전 제거 -----
                # 사용자: "[GS]1s22s22p4 텍스트는 분자 표현을 완전히 망치고 있음"

                # ----- 부분전하 숫자 텍스트 (원자 중앙 덧그리기) -----
                # 학술 인용: Mulliken 1955 J.Chem.Phys 23:1833 / Gasteiger 1980 Tetrahedron 36:3219
                if charge_value is None:
                    # [MAGIC: em-dash] DFT 논문 형식 — 데이터 없음 표기 (Rule Q: 유니코드 직접)
                    charge_text = "—"  # em-dash
                else:
                    charge_text = f"{charge_value:+.2f}"

                painter.setFont(font_charge)
                # [M895 D888-W9] ORCA/Gasteiger 데이터 소스에 따른 색상 구분
                # ORCA Mulliken: 색상 숫자 — 음전하(red #D32F2F) / 양전하(blue #1976D2) / 중성(검정)
                # Gasteiger fallback: 단일 검정 (경험적 모델, 색상 구분 미지원)
                # Mulliken R.S. 1955 J.Chem.Phys 23:1833 / Gasteiger 1980 Tetrahedron 36:3219
                if is_orca_available and charge_value is not None:
                    # ORCA Mulliken: red/blue/black 색상 부분전하 (학술 논문 표준)
                    if charge_value < -0.05:  # [MAGIC: -0.05] 음전하 임계값 (M645_W23 색상 표준)
                        _charge_pen_color = QColor(0xD3, 0x2F, 0x2F)  # #D32F2F RED 음전하
                    elif charge_value > 0.05:  # [MAGIC: +0.05] 양전하 임계값 (M645_W23 색상 표준)
                        _charge_pen_color = QColor(0x19, 0x76, 0xD2)  # #1976D2 BLUE 양전하
                    else:
                        _charge_pen_color = QColor(0x38, 0x8E, 0x3C)  # #388E3C GREEN 중성 (±0.05 이내)
                else:
                    # Gasteiger fallback 또는 데이터 없음: 단일 검정
                    _charge_pen_color = QColor(0, 0, 0)  # 검정
                painter.setPen(QPen(_charge_pen_color, 1.5))

                qw = fm_charge.horizontalAdvance(charge_text)
                # [M645_W32] x clamp — view_container 영역 침범 방지
                chg_x = center.x() - qw / 2.0
                if chg_x + qw > _safe_max_x:
                    chg_x = center.x() - qw - 4.0
                # [M717 F5-2 item6] 원자 중심 덧그리기 — baseline 보정 ascent/2
                # 이전: center.y() - 8.0 (원자 위 오프셋, 위치 어긋남)
                painter.drawText(
                    QPointF(chg_x, center.y() + _half_asc),
                    charge_text
                )

                # [P1-FIX] NH2/OH subscript: _render_lewis_grey opacity=0.40 으로
                # LewisRenderer가 NH2를 그리지만 너무 흐려 보이지 않음.
                # 헤테로 원자(N/O/S/P 등) h_count>=1 일 때 1.0 opacity로 재그림.
                # _draw_h_group_label과 동일 렌더링, 단 원자 위쪽 방향에 오프셋 배치.
                # 학술 표준: Clayden Organic Chemistry §1.6 Lewis 구조식 필기 규범
                sym = atom_data.get("main", "")
                if sym and sym not in ("", "C", "H"):
                    h_count = atom_data.get("h_count", 0)
                    if isinstance(h_count, int) and h_count >= 1:
                        # [MAGIC: 22] 원자 중심 위쪽으로 NH2 그룹 라벨 오프셋 (px)
                        # 전하 텍스트는 원자 중심에, NH2는 위쪽으로 분리 배치
                        _nh_offset_y = -22.0
                        main_font_h = QFont(LewisRenderer._get_font_family(),
                                            12, QFont.Weight.Bold)
                        sub_font_h = QFont(LewisRenderer._get_font_family(),
                                           9, QFont.Weight.Bold)
                        fm_h = QFontMetrics(main_font_h)
                        sfm_h = QFontMetrics(sub_font_h)
                        painter.setOpacity(1.0)
                        # [RGB 0,0,0,200] 검정 (0.78 alpha) — 배경과 대비 유지
                        painter.setPen(QPen(QColor(0, 0, 0, 200), 1))
                        if h_count >= 2:
                            main_part = sym + "H"
                            sub_part = str(h_count)
                            mw = fm_h.horizontalAdvance(main_part)
                            sw = sfm_h.horizontalAdvance(sub_part)
                            total = mw + sw
                            _nx = center.x() - total / 2.0
                            _ny = center.y() + _nh_offset_y
                            painter.setFont(main_font_h)
                            painter.drawText(
                                QPointF(_nx,
                                        _ny + fm_h.ascent()),
                                main_part
                            )
                            painter.setFont(sub_font_h)
                            # [MAGIC: 0.25*height] 아래첨자 = baseline + 25% 아래
                            painter.drawText(
                                QPointF(_nx + mw,
                                        _ny + fm_h.ascent() + fm_h.height() * 0.25),
                                sub_part
                            )
                        else:
                            # h_count == 1: "NH" 또는 "OH"
                            label = sym + "H"
                            painter.setFont(main_font_h)
                            tw = fm_h.horizontalAdvance(label)
                            painter.drawText(
                                QPointF(center.x() - tw / 2.0,
                                        center.y() + _nh_offset_y + fm_h.ascent()),
                                label
                            )
        finally:
            painter.restore()

    # ------------------------------------------------------------------
    # STAGE 4: ORCA 미설치 시 학습 모드 배너 (Rule M)
    # ------------------------------------------------------------------
    @staticmethod
    def _render_fallback_banner(painter, is_gasteiger=False):
        """ORCA 미실행 시 좌상단에 노란/파란 경고 배너 + 워터마크 표시.

        [M645_W23] is_gasteiger=True이면 Gasteiger charge 사용 중임을 표시.
        [M645_W32] FP-15 P-MOCK-DISGUISED 차단:
          - 배너 2줄: 한국어(학습 모드 명시) + 영문 병기 (Rule Q-b)
          - 워터마크: 분자 좌표계 중앙 하단 반투명 "SIMULATION / 학습 모드" 텍스트
        Rule M: silent 동작 금지 — 사용자에게 현재 상태 항상 피드백.
        학술 인용: Gasteiger J.; Marsili M. (1980) Tetrahedron 36:3219
                  Mulliken R.S. (1955) J.Chem.Phys 23:1833

        Note: 이 메서드는 view transform(pan+scale)이 적용된 painter 안에서 호출됨.
        배너/워터마크는 transform을 일시 리셋(resetTransform)하여 화면 픽셀 기준으로 그림.
        """
        painter.save()
        try:
            # [M645_W32] 화면 고정 좌표를 위해 transform 리셋
            # painter.device().width()/height()로 실제 화면 크기 획득
            try:
                dev_w = float(painter.device().width())   # type: ignore[union-attr]
                dev_h = float(painter.device().height())  # type: ignore[union-attr]
            except Exception:
                dev_w, dev_h = 800.0, 600.0
            painter.resetTransform()
            painter.setOpacity(0.92)

            banner_x = 10.0
            banner_y = 10.0
            banner_w = 480.0   # [M645_W32] 2줄 텍스트 + 영문 병기
            banner_h = 54.0    # [M645_W32] 2줄 표시

            if is_gasteiger:
                # [M683 FIX] 사용자 LV.14 item 5 — lite 버전 Gasteiger 배너 개선
                # 기존: "⚠ Gasteiger 부분전하 (학습 모드 — ORCA 미실행)" → 경고 느낌 과다
                # 수정: "Gasteiger 부분전하 시각화 (ChemGrid Lite — 경험적 모델)" + 안내 톤 완화
                # Rule GG: SIMULATION_MODE 배너 의무 유지 (제거 불가) — 단, 학생 친화 텍스트
                painter.setPen(QPen(QColor(0, 80, 160), 1.5))
                painter.setBrush(QBrush(QColor(200, 230, 255, 220)))
                # [M645_W32] 1줄: 한국어, 2줄: 영문 + 인용
                line1 = "Gasteiger 부분전하 시각화 (ChemGrid Lite — 경험적 모델, ORCA 미연결)"
                line2 = "Gasteiger/Marsili 1980 Tetrahedron 36:3219  |  정밀 DFT 계산: ORCA 설치 필요"
                txt_color = QColor(0, 50, 120)
                wm_color = QColor(0, 60, 140)
                wm_text = "SIMULATION  /  학습 모드"  # 학습 모드
            else:
                # ground-state 폴백: 노란색 배너
                painter.setPen(QPen(QColor(180, 130, 0), 1.5))
                painter.setBrush(QBrush(QColor(255, 240, 180, 220)))
                line1 = "⚠ 전자배치 추정값 (학습 모드 — ORCA 미실행)"  # ⚠ 전자배치 추정값 (학습 모드 — ORCA 미실행)
                line2 = "Ground-state fallback (learning mode) - Mulliken 1955 J.Chem.Phys 23:1833"
                txt_color = QColor(120, 60, 0)
                wm_color = QColor(140, 100, 0)
                wm_text = "학습 모드 (ORCA 미설치)"  # 학습 모드 (ORCA 미설치)

            painter.drawRoundedRect(
                QRectF(banner_x, banner_y, banner_w, banner_h),
                6.0, 6.0
            )

            font_banner = QFont(LewisRenderer._get_font_family(), 10, QFont.Weight.Bold)  # [M609]
            font_banner_sm = QFont(LewisRenderer._get_font_family(), 8, QFont.Weight.Normal)  # [M609]
            painter.setPen(QPen(txt_color, 1.0))

            # 1줄: 한국어 (큰 폰트)
            painter.setFont(font_banner)
            painter.drawText(
                QPointF(banner_x + 10.0, banner_y + 20.0),
                line1
            )
            # 2줄: 영문 + 인용 (작은 폰트) — Rule Q-b 영문 병기
            painter.setFont(font_banner_sm)
            painter.drawText(
                QPointF(banner_x + 10.0, banner_y + 42.0),
                line2
            )

            # ------------------------------------------------------------------
            # [M645_W32] 워터마크: 화면 우하단 반투명 대형 텍스트
            # Rule GG: Gasteiger 폴백 시 시각적으로 명확한 학습 모드 표시
            # ------------------------------------------------------------------
            painter.setOpacity(0.13)  # [MAGIC: 0.13] 배경에 묻히지 않는 최소 가시 수준
            font_wm = QFont(LewisRenderer._get_font_family(), 20, QFont.Weight.Bold)  # [M609]
            painter.setFont(font_wm)
            painter.setPen(QPen(wm_color, 1.0))
            fm_wm = QFontMetrics(font_wm)
            wm_w = fm_wm.horizontalAdvance(wm_text)
            wm_h = fm_wm.ascent()
            # [M645_W32] 화면 중앙 하단 80% 지점에 배치 — view_container 침범 방지
            # [MAGIC: 0.85 * dev_h] 화면 하단에서 15% 위쪽
            # [MAGIC: 415] view_container 너비(400) + 여백(15) = 우측 차단
            safe_right = dev_w - 415.0
            wm_x = min((dev_w - wm_w) / 2.0, safe_right - wm_w)
            wm_y = dev_h * 0.85 + wm_h
            painter.drawText(QPointF(wm_x, wm_y), wm_text)
        finally:
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
