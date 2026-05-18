# renderer.py — Refactored v4.2 (Phase 6-3 공명균등화 + LP 제외)
# 변경 이력:
#   v4.2: [#3B] 공명구조 전자구름 균등화 (고리 원자 전하 평균화),
#         [#4] 사용자 비공유전자쌍(user_lp/LP) 전자구름 제외
#   v4.1: [U7] ELEMENT_COLORS CPK 색상 테이블 + get_element_color() 추가,
#         draw_clouds() painter.save()/restore() 추가 (색상 누출 방지)
#   v4.0: draw_clouds() 분리, DFTDensityRenderer→CloudRenderer 통합,
#         디버그 print 전면 제거 → logging 교체, QPen import 누락 수정
import logging
import math
from PyQt6.QtGui import (
    QColor, QRadialGradient, QBrush, QFont, QFontMetrics, QPainterPath, QPen, QImage,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QThread, pyqtSignal
from chem_data import VISUAL_SETTINGS, ELEMENT_DATA
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# CPK 표준 원소 색상 (ChemGrid 호환, Drawing/Lewis/Theory 공용)  [U7 수정]
# ============================================================================
ELEMENT_COLORS: Dict[str, QColor] = {
    "C":  QColor(0, 0, 0),            # 검정
    "H":  QColor(100, 100, 100),      # 짙은 회색
    "O":  QColor(255, 0, 0),          # 빨강 (CPK 표준)
    "N":  QColor(0, 0, 255),          # 파랑 (CPK 표준)
    "S":  QColor(255, 200, 50),       # 노랑
    "P":  QColor(255, 128, 0),        # 주황
    "F":  QColor(144, 224, 80),       # 연두
    "Cl": QColor(0, 255, 0),          # 초록
    "Br": QColor(165, 42, 42),        # 갈색
    "I":  QColor(148, 0, 211),        # 보라
    "Si": QColor(240, 200, 160),      # 베이지
    "B":  QColor(255, 181, 181),      # 연분홍
    "Li": QColor(204, 128, 255),      # 연보라
    "Na": QColor(171, 92, 242),       # 보라
    "K":  QColor(143, 64, 212),       # 진보라
    "Ca": QColor(61, 255, 0),         # 연초록
    "Fe": QColor(180, 80, 210),        # 보라색 (Heme 포르피린 Fe 식별 강조, 감사#7)
    "Mg": QColor(138, 255, 0),        # 밝은 초록
    "Zn": QColor(125, 128, 176),      # 회청색
    "Cu": QColor(200, 128, 51),       # 구리색
}


def get_element_color(element: str, is_selected: bool = False) -> QColor:
    """
    원소 기호에 따른 표준 CPK 색상 반환.  [U7 수정]

    Args:
        element: 원소 기호 (예: "O", "N", "C")
        is_selected: True이면 선택 하이라이트 색상 반환

    Returns:
        QColor 인스턴스
    """
    if is_selected:
        return QColor(33, 150, 243)  # Material Blue 선택 하이라이트
    return QColor(ELEMENT_COLORS.get(element, QColor(0, 0, 0)))

# ============================================================================
# PHASE B: ELECTRONIC DENSITY STRUCTURES
# ============================================================================

@dataclass
class ElectronicDensity:
    """Electronic density data at atomic positions"""
    atom_index: int
    atom_symbol: str
    position: Tuple[float, float, float]
    density: float  # Electron density value (a.u.)
    mulliken_charge: float
    lowdin_charge: float


# ============================================================================
# ESP CALCULATOR THREAD
# ============================================================================

class ESPCalculatorThread(QThread):
    """
    Background ESP (Electrostatic Potential) calculation thread.
    Computes density gradient mapping for visualization.
    [OPTIMIZED] With graceful interruption and thread safety.
    """
    progress = pyqtSignal(str)
    result = pyqtSignal(dict)
    error = pyqtSignal(str)
    finished_cleanup = pyqtSignal()

    def __init__(self, densities: List[ElectronicDensity], atom_positions: Dict):
        super().__init__()
        self.densities = densities
        self.atom_positions = atom_positions
        self.esp_map = {}
        self._stop_event = False
        self.setObjectName(f"ESPCalculator-{id(self)}")

    def run(self):
        """Calculate ESP values for all atom positions with graceful interruption."""
        try:
            self.progress.emit("[Phase B] Starting ESP calculation...")

            if not self.densities:
                self.error.emit("No density data provided")
                return

            if self._stop_event:
                logger.debug("%s: ESP calculation cancelled before start", self.objectName())
                return

            total_positions = len(self.atom_positions)
            for idx, target_pos in enumerate(self.atom_positions.keys()):
                if self._stop_event:
                    logger.debug(
                        "%s: ESP calculation interrupted at %d/%d",
                        self.objectName(), idx, total_positions,
                    )
                    return

                esp_value = 0.0
                for density in self.densities:
                    dx = target_pos[0] - density.position[0]
                    dy = target_pos[1] - density.position[1]
                    distance = math.sqrt(dx * dx + dy * dy) + 0.1
                    contrib = density.density / (distance ** 2 + 0.01)
                    esp_value += contrib

                self.esp_map[target_pos] = round(esp_value, 4)

                if idx % max(1, total_positions // 10) == 0:
                    self.progress.emit(
                        f"[Phase B] Processing: {idx}/{total_positions} positions"
                    )

            if not self._stop_event:
                self.progress.emit(
                    f"[Phase B] ESP calculation complete: {len(self.esp_map)} points"
                )
                self.result.emit(self.esp_map)

        except Exception as e:
            self.error.emit(f"[Phase B ESP Error] {str(e)}")
        finally:
            self.finished_cleanup.emit()

    def stop(self):
        """Gracefully stop the ESP calculation."""
        self._stop_event = True
        logger.debug("%s: Stop signal received", self.objectName())


# ============================================================================
# CLOUD RENDERER  (DFTDensityRenderer 기능을 통합)
# ============================================================================

class CloudRenderer:
    """
    통합 전자구름 렌더러.

    구 DFTDensityRenderer + 구 CloudRenderer를 하나로 합침.
    - charge_to_color()         : Mulliken 전하 → RGB (동적 스케일링)
    - calculate_esp_color()     : ESP 밀도 → 5색 그라데이션
    - draw_dft_density_clouds() : DFT 기반 간이 렌더링
    - draw_charge_indicator()   : ±기호 인디케이터
    - draw_clouds()             : 메인 오케스트레이터 (v3.2)
    - draw_crosshairs_v32()     : 조준선 마커
    - draw_stereo_labels()      : R/S 라벨
    """

    # ── ESP 캐시 ──────────────────────────────────────────────
    _esp_cache: Dict = {}
    _density_cache = None
    _cache_timestamp = None
    _max_cache_size = 1000
    _cache_access_count: Dict = {}

    # ------------------------------------------------------------------
    # 캐시 관리
    # ------------------------------------------------------------------
    @staticmethod
    def set_density_data(densities: List[ElectronicDensity]):
        """Store electronic density data for ESP visualization."""
        import time
        CloudRenderer._density_cache = densities
        CloudRenderer._esp_cache = {}
        CloudRenderer._cache_timestamp = time.time()
        CloudRenderer._cache_access_count = {}

    @staticmethod
    def _invalidate_cache_if_stale(max_age_seconds: int = 300) -> bool:
        import time
        if CloudRenderer._cache_timestamp:
            age = time.time() - CloudRenderer._cache_timestamp
            if age > max_age_seconds:
                CloudRenderer._esp_cache = {}
                CloudRenderer._cache_access_count = {}
                return True
        return False

    @staticmethod
    def _evict_lru_if_needed():
        if len(CloudRenderer._esp_cache) >= CloudRenderer._max_cache_size:
            if CloudRenderer._cache_access_count:
                lru_key = min(
                    CloudRenderer._cache_access_count,
                    key=CloudRenderer._cache_access_count.get,
                )
                CloudRenderer._esp_cache.pop(lru_key, None)
                CloudRenderer._cache_access_count.pop(lru_key, None)

    # ------------------------------------------------------------------
    # 색상 유틸리티  (구 DFTDensityRenderer에서 통합)
    # ------------------------------------------------------------------
    @staticmethod
    def charge_to_color(
        charge: float,
        min_charge: float = -1.0,
        max_charge: float = 1.0,
    ) -> QColor:
        """
        Mulliken 부분전하 → RGB 색상 변환 (McMurry 교과서 ESP 표준).

        교과서 기준 (Organic Chemistry, McMurry / Clayden):
          - 음전하 (전자 풍부, δ-): RED  → 산소 비공유전자쌍, F, 음이온
          - 양전하 (전자 부족, δ+): BLUE → 산소와 결합한 H, 카보닐 C, 양이온
          - 중성 (δ≈0):           GREEN → 일반 sp3 C-H

        Args:
            charge: 현재 원자의 Mulliken 전하 (음수=전자풍부, 양수=전자부족)
            min_charge: 현재 분자 내 최소 전하
            max_charge: 현재 분자 내 최대 전하
        """
        # [FIX-ESP v5] 절대 전하 기반 정규화 — 분자 내 상대적 차이가 아닌
        # 화학적 의미 있는 절대 스케일 사용 (Gasteiger 전하 범위: 약 -0.5 ~ +0.5)
        # 이렇게 해야 ethane과 같은 저전하 분자에서 색이 과장되지 않음
        ABS_SCALE = 0.35  # Gasteiger 전하 ±0.35 → 완전 RED/BLUE
        normalized = max(-1.0, min(1.0, charge / ABS_SCALE))

        # [MAGIC: 0.05] Shared neutral threshold with ESP surface renderers.
        NEUTRAL_ZONE = 0.05

        if normalized < -NEUTRAL_ZONE:  # 전자 풍부 → RED (친핵부위)
            intensity = min(1.0, (abs(normalized) - NEUTRAL_ZONE) / (1.0 - NEUTRAL_ZONE))
            r = 255
            g = int(60 * (1 - intensity))
            b = int(60 * (1 - intensity))
            alpha = int(140 + 115 * intensity)
        elif normalized > NEUTRAL_ZONE:  # 전자 부족 → BLUE (친전자부위)
            intensity = min(1.0, (normalized - NEUTRAL_ZONE) / (1.0 - NEUTRAL_ZONE))
            r = int(60 * (1 - intensity))
            g = int(60 * (1 - intensity))
            b = 255
            alpha = int(140 + 115 * intensity)
        else:  # 중성 → GREEN (비반응성, 낮은 투명도)
            r, g, b = 50, 180, 50
            alpha = 60  # 매우 옅게 — sp3 C-H 영역은 거의 안보이게

        color = QColor(r, g, b)
        color.setAlpha(alpha)
        return color

    @staticmethod
    def calculate_esp_color(
        density: float,
        min_density: float,
        max_density: float,
    ) -> QColor:
        """[PHASE B] ESP color map: Blue (low) → Red (high)."""
        if max_density <= min_density:
            return QColor(100, 149, 237)

        normalized = max(0.0, min(1.0,
            (density - min_density) / (max_density - min_density)))

        if normalized < 0.5:
            ratio = normalized * 2
            r = int(0 * (1 - ratio) + 0 * ratio)
            g = int(149 * (1 - ratio) + 255 * ratio)
            b = int(237 * (1 - ratio) + 0 * ratio)
        else:
            ratio = (normalized - 0.5) * 2
            r = int(0 * (1 - ratio) + 255 * ratio)
            g = int(255 * (1 - ratio) + 100 * ratio)
            b = int(0 * (1 - ratio) + 0 * ratio)

        return QColor(r, g, b)

    # ------------------------------------------------------------------
    # DFT 간이 렌더링 (구 DFTDensityRenderer 메서드 그대로 통합)
    # ------------------------------------------------------------------
    @staticmethod
    def draw_dft_density_clouds(
        painter,
        atom_positions: Dict,
        density_data: Dict,
    ):
        """DFT 기반 전자구름 간이 렌더링."""
        if not atom_positions:
            return

        painter.save()
        for (x, y), charge in atom_positions.items():
            color = CloudRenderer.charge_to_color(charge)
            base_radius = 14.0
            radius = min(base_radius + abs(charge) * 8.0, 35.0)

            grad = QRadialGradient(QPointF(x, y), radius)
            center_color = QColor(color)
            edge_color = QColor(color)
            edge_color.setAlpha(0)
            grad.setColorAt(0, center_color)
            grad.setColorAt(0.7, color)
            grad.setColorAt(1, edge_color)

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.restore()

    @staticmethod
    def draw_charge_indicator(
        painter,
        position: QPointF,
        charge: float,
        size: int = 10,
    ):
        """Simplified charge indicator (+ or − symbol)."""
        if abs(charge) < 0.05:
            return
        symbol = "−" if charge < 0 else "+"
        color = CloudRenderer.charge_to_color(charge)
        painter.save()
        painter.setFont(QFont("Arial", size, QFont.Weight.Bold))
        painter.setPen(color)
        painter.drawText(position, symbol)
        painter.restore()

    # ==================================================================
    # draw_clouds  — 메인 오케스트레이터 (v3.2)
    # ==================================================================
    @staticmethod
    def draw_clouds(
        painter,
        results,
        use_theory_coords: bool = False,
        densities: Optional[List[ElectronicDensity]] = None,
    ):
        """
        [v3.2] 해석적 렌더링 엔진 오케스트레이터.

        use_theory_coords=True  → Theory 레이어용 (이론적 좌표)
        use_theory_coords=False → Drawing/Lewis 레이어용 (그리기 좌표)
        densities: Optional ORCA electronic density data
        """
        if not results or not isinstance(results, dict):  # Rule N
            return

        charges = results.get("charges", {})
        if not isinstance(charges, dict):  # Rule N
            charges = {}
        islands = results.get("islands", [])
        if not isinstance(islands, list):  # Rule N
            islands = []
        aromatic = results.get("aromatic", set())
        if not isinstance(aromatic, (set, list, frozenset)):  # Rule N
            aromatic = set()
        atoms = results.get("atoms", {})
        if not isinstance(atoms, dict):  # Rule N
            atoms = {}
        bonds = results.get("bonds", {})
        if not isinstance(bonds, dict):  # Rule N
            bonds = {}

        logger.debug(
            "draw_clouds called — atoms=%d, use_theory=%s",
            len(charges), use_theory_coords,
        )

        if not charges:
            return

        # ── ESP 연속 표면 자동 분기: 원자 40개 이하이면 numpy 기반 연속 맵 ──
        n_atoms = len(charges)
        if n_atoms <= 40 and NUMPY_AVAILABLE:
            CloudRenderer.draw_esp_surface(painter, results, use_theory_coords)
            return

        # 🔴 U7 수정: 전자구름 렌더링 전후 painter 상태 격리
        painter.save()
        try:
            # ── 1) 사전 계산 ─────────────────────────────────────
            atom_is_size = {}
            for isl in islands:
                for a in isl:
                    atom_is_size[a] = len(isl)

            contrast = CloudRenderer._calculate_local_contrast(
                charges, atoms, aromatic, atom_is_size,
            )
            bond_stats = CloudRenderer._calculate_bond_stats(bonds)
            density_stats = CloudRenderer._calculate_density_stats(densities)

            # ── 2) 렌더링 순서 결정 ──────────────────────────────
            render_order = CloudRenderer._build_render_order(
                charges, atoms, aromatic, atom_is_size,
            )

            # ── 2.5) 방향족 π 비편재화 halo (CHEM-7) ─────────────
            _td_halo = results.get("theory_data", {}) if use_theory_coords else {}
            if not isinstance(_td_halo, dict):  # Rule N
                _td_halo = {}
            _theory_map = _td_halo.get("map", {}) if _td_halo else {}
            CloudRenderer.draw_pi_cloud_halo(
                painter,
                rings=results.get("rings", []),
                aromatic_nodes=aromatic,
                charges=charges,
                use_theory_coords=use_theory_coords,
                theory_map=_theory_map,
            )

            # ── 3) 원자별 구름 렌더링 ────────────────────────────
            electron_rich_carbons = CloudRenderer._render_atom_clouds(
                painter, render_order, results, contrast,
                bond_stats, density_stats, atom_is_size,
                use_theory_coords, densities,
            )

            # ── 4) 조준선 데이터 저장 ────────────────────────────
            CloudRenderer._store_crosshair_data(results, electron_rich_carbons)
        finally:
            painter.restore()  # 🔴 U7: 반드시 복원 — 후속 렌더링에 색상 누출 방지

    # ==================================================================
    # ESP 등표면 렌더링 (참고: McMurry ESP 맵 스타일)
    # 분자 전체를 감싸는 반투명 표면에 RED↔GREEN↔BLUE 그라디언트
    # ==================================================================
    @staticmethod
    def draw_esp_isosurface(
        painter,
        results,
        use_theory_coords: bool = False,
    ):
        """분자 전체를 감싸는 ESP 등표면 시각화 (2D 투영).

        참고 이미지: McMurry/Clayden 교과서의 ESP 맵
        - 빨강 = 전자 풍부 (δ⁻, 친핵부위)
        - 초록 = 중성
        - 파랑 = 전자 부족 (δ⁺, 친전자부위)

        각 원자 위치에 큰 반투명 가우시안을 그리되, 반지름을 VdW 반지름 기준으로
        키워서 분자 표면처럼 겹치게 만듦.
        """
        if not results or not isinstance(results, dict):  # Rule N
            return
        charges = results.get("charges", {})
        if not isinstance(charges, dict):  # Rule N
            charges = {}
        atoms_data = results.get("atoms", {})
        if not isinstance(atoms_data, dict):  # Rule N
            atoms_data = {}
        if not charges:
            return

        painter.save()
        try:
            _td = results.get("theory_data", {})
            if not isinstance(_td, dict):  # Rule N
                _td = {}
            theory_map = _td.get("map", {}) if use_theory_coords else {}
            if not isinstance(theory_map, dict):  # Rule N
                theory_map = {}
            bonds = results.get("bonds", {})
            if not isinstance(bonds, dict):  # Rule N
                bonds = {}
            # [B9-2 / M222] analyzer가 계산한 ESP 스타일 맵 조회.
            # Rule N: dict 타입 가드 (구버전 analyzer/캐시 호환).
            esp_style_map = results.get("esp_style_per_atom", {})
            if not isinstance(esp_style_map, dict):
                esp_style_map = {}

            # [M679 FIX] 사용자 LV.14 item 24 — ESP 단색 버그 + 색 대비 부족 해소
            # 변경 전: c_range floor=0.05 → 작은 전하 분자도 0.05 normalize → 다 norm<|0.05| → 전체 green
            # 변경 후: 실제 charge range로 정규화 + 적응적 floor (range/2 vs 0.02 vs c_range)
            # 학술 표준: ESP 색상 대비는 분자별 charge 분포에 적응 (McMurry/Clayden 교과서 표준)
            all_charges = list(charges.values())
            min_c = min(all_charges) if all_charges else -0.1
            max_c = max(all_charges) if all_charges else 0.1
            # 실제 분자별 ESP range 사용 — 작은 전하 분자도 색상 대비 보장
            actual_range = max(abs(min_c), abs(max_c))
            # [MAGIC: 0.02] floor 0.05→0.02 — 비극성 분자도 norm 차이 대비 가능
            # 너무 작으면 div-by-zero 위험 → 0.02 = Gasteiger 최소 의미 단위
            c_range = max(actual_range, 0.02)

            # 평균 결합 길이로 VdW 반지름 스케일 결정
            # [FIX-CONTOUR v1] 좌표계 혼용 방지: theory_map에 양쪽 끝점이 모두
            # 있는 결합만 사용하여 bond length 계산. 한쪽만 있으면 혼합 좌표계가
            # 되어 비정상적으로 큰 길이가 나올 수 있음.
            bond_lengths: List[float] = []
            for (k1, k2) in bonds.keys():
                if theory_map:
                    k1_in = k1 in theory_map
                    k2_in = k2 in theory_map
                    # 양쪽 모두 theory_map에 있거나 양쪽 모두 없을 때만 사용
                    if k1_in != k2_in:
                        continue  # 혼합 좌표 → skip
                    p1 = theory_map.get(k1, QPointF(*k1))
                    p2 = theory_map.get(k2, QPointF(*k2))
                else:
                    p1 = QPointF(*k1)
                    p2 = QPointF(*k2)
                bl = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
                if 5 < bl < 300:  # [FIX-CONTOUR v1] 비정상 길이 필터 (5~300px)
                    bond_lengths.append(bl)
            avg_bl = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 50.0
            # [FIX-CONTOUR v1] avg_bl 클램프: 최대 120px (일반 격자 40px의 3배)
            avg_bl = min(avg_bl, 120.0)
            # VdW 표면 반지름: 평균 결합 길이의 75% (겹치게)
            base_vdw = avg_bl * 0.75
            # [FIX-CONTOUR v1] 최대 반지름 한도: 90px (화면을 넘지 않도록)
            MAX_ESP_RADIUS = 90.0

            # 렌더링: 큰 반투명 원 (VdW 스케일)
            painter.setPen(Qt.PenStyle.NoPen)
            for pt_key, charge in charges.items():
                atom_data = atoms_data.get(pt_key, {})
                at_main = atom_data.get("main", "") or "C"

                # [B9-2 / M222] analyzer ESP 스타일 조회 (sp3 halogen 규칙 우선 적용).
                # Rule N: dict 타입 가드. show_esp=False → 구름 숨김.
                _style = esp_style_map.get(pt_key, None)
                _has_style = isinstance(_style, dict)
                if _has_style:
                    if not _style.get("show_esp", True):
                        continue  # sp3 포화 탄화수소 등 숨김 원자
                    _alpha_scale = float(_style.get("alpha_scale", 1.0))
                    _radius_scale = float(_style.get("radius_scale", 1.0))
                else:
                    # 폴백: analyzer가 esp_style_per_atom 미제공 (구버전/캐시)
                    # → 기존 동작 유지 (sp3 포화 필터 + 전체 표시)
                    _alpha_scale = 1.0
                    _radius_scale = 1.0

                # [FIX-ESP v6] sp3 포화 탄화수소 필터 — draw_esp_isosurface에도 적용.
                # [B9-2 / M222] esp_style_map에서 이미 show_esp=True로 판정됐으면
                # 이 필터를 건너뜀 (benzene sp2 등 aromatic bond order=1 케이스 구제).
                # esp_style 미제공 원자에만 폴백 적용.
                if not _has_style:
                    _is_hetero = at_main not in ('', 'C', 'H')
                    _has_charge = atom_data.get("charge", "") in ("+", "-")
                    _has_mult_bond = False
                    for (k1, k2), bdata in bonds.items():
                        if k1 == pt_key or k2 == pt_key:
                            bo = bdata if isinstance(bdata, (int, float)) else 1
                            if bo >= 1.5:
                                _has_mult_bond = True
                                break
                    if not (_is_hetero or _has_charge or _has_mult_bond):
                        continue

                center = theory_map.get(pt_key, QPointF(*pt_key)) if theory_map else QPointF(*pt_key)

                # 원소별 VdW 반지름 스케일
                el_data = ELEMENT_DATA.get(at_main, {})
                vdw_scale = el_data.get("cloud_scale", 1.0)
                radius = base_vdw * vdw_scale

                # H는 더 작게
                if at_main == "H":
                    radius = base_vdw * 0.55

                # [B9-2 / M222] ESP 스타일 radius_scale 적용 (sp3 halogen: 1.3x 넓게)
                radius = radius * _radius_scale

                # [FIX-CONTOUR v1] 반지름 클램프 — 화면 초과 방지
                radius = min(radius, MAX_ESP_RADIUS)
                if radius < 1.0:
                    continue  # 너무 작은 원은 스킵

                # 전하→색상 (연속 그라디언트)
                norm = max(-1.0, min(1.0, charge / c_range))
                if norm < -0.05:  # RED (전자 풍부)
                    t = min(abs(norm) * 2, 1.0)
                    r, g, b = int(255), int(200 * (1 - t) + 50 * t), int(200 * (1 - t))
                elif norm > 0.05:  # BLUE (전자 부족)
                    t = min(norm * 2, 1.0)
                    r, g, b = int(200 * (1 - t)), int(200 * (1 - t) + 50 * t), int(255)
                else:  # GREEN (중성)
                    r, g, b = 180, 220, 180

                color = QColor(r, g, b)
                # [D-4ab B1-2] ESP 구름 alpha 하향: 140→90 중심, 70→50 중간
                # [B9-2 / M222] sp3 halogen은 추가로 alpha_scale 0.3 적용 → ~27 중심, ~15 중간.
                # 사유: epinephrine Lewis에서 catechol ring C와 결합선이 ESP 구름에 가려짐.
                # canvas.py paintEvent: ESP → LewisRenderer/TheoryRenderer 순서로 이미 z-order 올바름.
                # alpha 감소로 원자 기호/결합선 가독성 회복 (Rule O 렌더링 품질).
                _base_center_a = 90   # [D-4ab B1-2] 140→90
                _base_mid_a = 50      # [D-4ab B1-2] 70→50
                _center_a = max(0, min(255, int(_base_center_a * _alpha_scale)))
                _mid_a = max(0, min(255, int(_base_mid_a * _alpha_scale)))
                color.setAlpha(_center_a)
                mid_color = QColor(r, g, b, _mid_a)
                edge_color = QColor(r, g, b, 0)

                grad = QRadialGradient(center, radius)
                grad.setColorAt(0.0, color)
                grad.setColorAt(0.5, mid_color)
                grad.setColorAt(1.0, edge_color)
                painter.setBrush(QBrush(grad))
                # [FIX-CONTOUR v1] NoPen 재확인 — 상태 누출 방지
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(center, radius, radius)
        finally:
            painter.restore()

    # ==================================================================
    # ESP 연속 표면 맵 (numpy meshgrid 기반)
    # ==================================================================
    @staticmethod
    def draw_esp_surface(
        painter,
        results,
        use_theory_coords: bool = False,
    ):
        """연속 ESP 표면 맵: Gaussian 블렌딩으로 '개구리알' 대신 연속 색상.

        구현:
          1. 분자 바운딩 박스 + 패딩 계산
          2. numpy meshgrid로 모든 픽셀에서 ESP 값 = Σ(charge_i × exp(-dist²/2σ²))
          3. VdW 표면 마스크: max(exp(-dist²/2r_vdw²)) > 0.01인 픽셀만 렌더링
          4. ESP → 색상: 음(RED) → 중성(GREEN) → 양(BLUE)
          5. 성능: 해상도 1/3 다운샘플 → SmoothTransformation 업스케일
        """
        if not NUMPY_AVAILABLE or not results:
            # numpy 없으면 기존 블롭 폴백
            CloudRenderer.draw_esp_isosurface(painter, results, use_theory_coords)
            return

        charges = results.get("charges", {})
        if not isinstance(charges, dict):  # Rule N
            charges = {}
        atoms_data = results.get("atoms", {})
        if not isinstance(atoms_data, dict):  # Rule N
            atoms_data = {}
        bonds = results.get("bonds", {})
        if not isinstance(bonds, dict):  # Rule N
            bonds = {}
        if not charges:
            return

        _td2 = results.get("theory_data", {})
        if not isinstance(_td2, dict):  # Rule N
            _td2 = {}
        theory_map = _td2.get("map", {}) if use_theory_coords else {}
        if not isinstance(theory_map, dict):  # Rule N
            theory_map = {}

        # 원자 데이터 수집: position, charge, vdw radius
        atom_list = []  # [(x, y, charge, vdw_r)]
        for pt_key, charge in charges.items():
            _ad = atoms_data.get(pt_key, {})
            atom_data = _ad if isinstance(_ad, dict) else {}  # Rule N
            at_main = atom_data.get("main", "") or "C"

            # sp3 포화 탄화수소 필터
            _is_hetero = at_main not in ('', 'C', 'H')
            _has_charge = atom_data.get("charge", "") in ("+", "-")
            _has_mult_bond = False
            for (k1, k2), bdata in bonds.items():
                if k1 == pt_key or k2 == pt_key:
                    bo = bdata if isinstance(bdata, (int, float)) else 1
                    if bo >= 1.5:
                        _has_mult_bond = True
                        break
            if not (_is_hetero or _has_charge or _has_mult_bond):
                continue

            center = theory_map.get(pt_key, QPointF(*pt_key)) if theory_map else QPointF(*pt_key)

            el_data = ELEMENT_DATA.get(at_main, {})
            vdw_scale = el_data.get("cloud_scale", 1.0)
            if at_main == "H":
                vdw_scale = 0.55

            atom_list.append((center.x(), center.y(), charge, vdw_scale))

        if not atom_list:
            return

        # 평균 결합 길이로 스케일 결정
        # [FIX-CONTOUR v1] 좌표계 혼용 방지 + 비정상 길이 필터
        bond_lengths: List[float] = []
        for (k1, k2) in bonds.keys():
            if theory_map:
                k1_in = k1 in theory_map
                k2_in = k2 in theory_map
                if k1_in != k2_in:
                    continue  # 혼합 좌표 → skip
                p1 = theory_map.get(k1, QPointF(*k1))
                p2 = theory_map.get(k2, QPointF(*k2))
            else:
                p1 = QPointF(*k1)
                p2 = QPointF(*k2)
            bl = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
            if 5 < bl < 300:
                bond_lengths.append(bl)
        avg_bl = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 50.0
        avg_bl = min(avg_bl, 120.0)  # [FIX-CONTOUR v1] 클램프
        base_vdw = avg_bl * 0.75
        sigma = avg_bl * 0.45  # Gaussian spread

        # 바운딩 박스 + 패딩
        xs = [a[0] for a in atom_list]
        ys = [a[1] for a in atom_list]
        padding = base_vdw * 1.5
        x_min, x_max = min(xs) - padding, max(xs) + padding
        y_min, y_max = min(ys) - padding, max(ys) + padding
        full_w = x_max - x_min
        full_h = y_max - y_min

        if full_w < 1 or full_h < 1:
            return

        # 다운샘플 해상도 (성능)
        downsample = 3
        img_w = max(4, int(full_w / downsample))
        img_h = max(4, int(full_h / downsample))

        # numpy 배열
        gx = np.linspace(x_min, x_max, img_w)
        gy = np.linspace(y_min, y_max, img_h)
        GX, GY = np.meshgrid(gx, gy)

        # ESP 값 계산: Σ(charge_i × exp(-dist²/2σ²))
        esp = np.zeros((img_h, img_w), dtype=np.float64)
        # VdW 표면 마스크: max density
        surface_mask = np.zeros((img_h, img_w), dtype=np.float64)
        inv_2sigma2 = 1.0 / (2.0 * sigma * sigma)

        for ax, ay, charge, vdw_s in atom_list:
            r_vdw = base_vdw * vdw_s
            dx = GX - ax
            dy = GY - ay
            dist2 = dx * dx + dy * dy
            gauss = np.exp(-dist2 * inv_2sigma2)
            esp += charge * gauss
            # VdW 표면 밀도
            inv_2r2 = 1.0 / (2.0 * r_vdw * r_vdw) if r_vdw > 0 else inv_2sigma2
            surface_density = np.exp(-dist2 * inv_2r2)
            surface_mask = np.maximum(surface_mask, surface_density)

        # 마스크: 표면 바깥은 투명
        mask_threshold = 0.01
        visible = surface_mask > mask_threshold

        if not np.any(visible):
            return

        # 정규화
        abs_scale = 0.35
        esp_norm = np.clip(esp / abs_scale, -1.0, 1.0)

        # QImage RGBA 생성
        rgba = np.zeros((img_h, img_w, 4), dtype=np.uint8)

        # 음전하 (RED): esp_norm < -0.15
        # [MAGIC: 0.05] Shared neutral threshold with atom-cloud ESP renderers.
        neutral_zone = 0.05

        neg_mask = esp_norm < -neutral_zone
        pos_mask = esp_norm > neutral_zone
        mid_mask = ~neg_mask & ~pos_mask

        # RED region
        intensity = np.clip((np.abs(esp_norm) - neutral_zone) / (1.0 - neutral_zone), 0, 1)
        rgba[neg_mask, 0] = 255
        rgba[neg_mask, 1] = (60 * (1 - intensity[neg_mask])).astype(np.uint8)
        rgba[neg_mask, 2] = (60 * (1 - intensity[neg_mask])).astype(np.uint8)

        # BLUE region
        rgba[pos_mask, 0] = (60 * (1 - intensity[pos_mask])).astype(np.uint8)
        rgba[pos_mask, 1] = (60 * (1 - intensity[pos_mask])).astype(np.uint8)
        rgba[pos_mask, 2] = 255

        # GREEN region
        rgba[mid_mask, 0] = 50
        rgba[mid_mask, 1] = 180
        rgba[mid_mask, 2] = 50

        # Alpha: 표면 마스크 비례 + 전하 강도
        base_alpha = np.clip(surface_mask * 3.0, 0, 1)  # 표면에서 강하게
        charge_alpha = np.where(mid_mask, 0.3, 0.55 + 0.45 * intensity)
        alpha = base_alpha * charge_alpha * 255
        alpha[~visible] = 0
        rgba[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)

        # QImage 생성 + 업스케일
        qimg = QImage(rgba.data, img_w, img_h, img_w * 4,
                       QImage.Format.Format_RGBA8888)
        # numpy 데이터가 GC되지 않도록 복사
        qimg = qimg.copy()

        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
            target_rect = QRectF(x_min, y_min, full_w, full_h)
            painter.drawImage(target_rect, qimg)
        finally:
            painter.restore()

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 로컬 대비 계산
    # ------------------------------------------------------------------
    @staticmethod
    def _calculate_local_contrast(
        charges: Dict,
        atoms: Dict,
        aromatic: set,
        atom_is_size: Dict,
    ) -> dict:
        """
        고리 탄소 기준 로컬 대비 파라미터를 반환.

        Returns:
            dict with keys: min_charge, max_charge, charge_range,
                            ring_avg_charge, ring_carbon_charges
        """
        if not isinstance(atoms, dict):  # Rule N
            atoms = {}
        ring_carbon_charges: List[float] = []
        for pt_key, charge in charges.items():
            _ad_rc = atoms.get(pt_key, {})
            at_main = _ad_rc.get("main", "C") if isinstance(_ad_rc, dict) else "C"  # Rule N
            is_ring = (pt_key in aromatic or atom_is_size.get(pt_key, 0) >= 2)
            # [BUG-3 FIX] carbon은 main=''로 저장됨 → at_main=="" ≠ "C" → 항상 False
            # 모든 탄소(main='', 'C' 모두) 포함해야 ring_carbon_charges 정상 수집
            if at_main in ('', 'C') and is_ring:
                ring_carbon_charges.append(charge)

        if ring_carbon_charges:
            ring_min = min(ring_carbon_charges)
            ring_max = max(ring_carbon_charges)
            ring_avg = sum(ring_carbon_charges) / len(ring_carbon_charges)
            charge_range = max(abs(ring_min), abs(ring_max), 0.01)

            logger.debug(
                "Local contrast — ring C: min=%+.3f max=%+.3f avg=%+.3f range=%.3f",
                ring_min, ring_max, ring_avg, charge_range,
            )
            return {
                "min_charge": ring_min,
                "max_charge": ring_max,
                "charge_range": charge_range,
                "ring_avg_charge": ring_avg,
                "ring_carbon_charges": ring_carbon_charges,
            }

        return {
            "min_charge": -0.5,
            "max_charge": 0.5,
            "charge_range": 0.5,
            "ring_avg_charge": 0.0,
            "ring_carbon_charges": [],
        }

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 결합 길이 통계
    # ------------------------------------------------------------------
    @staticmethod
    def _calculate_bond_stats(bonds: Dict) -> dict:
        bond_lengths: List[float] = []
        if bonds:
            for (k1, k2), _ in bonds.items():
                dist = math.sqrt((k1[0] - k2[0]) ** 2 + (k1[1] - k2[1]) ** 2)
                if 1 < dist < 300:  # [FIX-CONTOUR v1] 비정상 길이 필터
                    bond_lengths.append(dist)
        avg = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 40.0
        avg = min(avg, 120.0)  # [FIX-CONTOUR v1] 클램프
        return {
            "avg_bond_length": avg,
            "max_cloud_radius": avg * 0.45,
        }

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 밀도 통계
    # ------------------------------------------------------------------
    @staticmethod
    def _calculate_density_stats(
        densities: Optional[List[ElectronicDensity]],
    ) -> dict:
        if densities:
            vals = [d.density for d in densities]
            return {"min": min(vals), "max": max(vals)}
        return {"min": 0.0, "max": 1.0}

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 렌더링 순서 결정
    # ------------------------------------------------------------------
    @staticmethod
    def _build_render_order(
        charges: Dict,
        atoms: Dict,
        aromatic: set,
        atom_is_size: Dict,
    ) -> list:
        """치환기 먼저, 고리 탄소 나중에 (고리가 위에 보임)."""
        if not isinstance(atoms, dict):  # Rule N
            atoms = {}
        substituent_atoms: List = []
        ring_atoms: List = []

        for pt_key in charges:
            _ad_sub = atoms.get(pt_key, {})
            at_main = _ad_sub.get("main", "C") if isinstance(_ad_sub, dict) else "C"  # Rule N
            is_ring = (pt_key in aromatic or atom_is_size.get(pt_key, 0) >= 2)
            if at_main in ("O", "N", "F", "Cl", "Br", "S", "P") and not is_ring:
                substituent_atoms.append(pt_key)
            else:
                ring_atoms.append(pt_key)

        return substituent_atoms + ring_atoms

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 원자별 구름 렌더링
    # ------------------------------------------------------------------
    @staticmethod
    def _render_atom_clouds(
        painter,
        render_order: list,
        results: dict,
        contrast: dict,
        bond_stats: dict,
        density_stats: dict,
        atom_is_size: Dict,
        use_theory_coords: bool,
        densities: Optional[List[ElectronicDensity]],
    ) -> list:
        """
        각 원자에 대해 가우시안 구름을 렌더링하고,
        전자 풍부 탄소 목록을 반환.
        [U7] painter.save()/restore()로 상태 격리 (방어적 중복 보호).
        """
        painter.save()  # 🔴 U7: 헬퍼 레벨 방어적 save
        try:
            return CloudRenderer._render_atom_clouds_inner(
                painter, render_order, results, contrast,
                bond_stats, density_stats, atom_is_size,
                use_theory_coords, densities,
            )
        finally:
            painter.restore()  # 🔴 U7: 헬퍼 레벨 방어적 restore

    @staticmethod
    def _render_atom_clouds_inner(
        painter,
        render_order: list,
        results: dict,
        contrast: dict,
        bond_stats: dict,
        density_stats: dict,
        atom_is_size: Dict,
        use_theory_coords: bool,
        densities: Optional[List[ElectronicDensity]],
    ) -> list:
        """_render_atom_clouds의 내부 구현 (save/restore 래퍼에서 호출)."""
        charges = results.get("charges", {})
        if not isinstance(charges, dict):  # Rule N
            charges = {}
        atoms = results.get("atoms", {})
        if not isinstance(atoms, dict):  # Rule N
            atoms = {}
        aromatic = results.get("aromatic", set())
        if not isinstance(aromatic, (set, list, frozenset)):  # Rule N
            aromatic = set()
        bonds = results.get("bonds", {})
        if not isinstance(bonds, dict):  # Rule N
            bonds = {}

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔴 명령 1: 공명구조 전자구름 균등화 — 고리 원자 전하 평균화
        #   방향족/공명 고리 내 원자들은 전자밀도가 동등해야 하므로
        #   전하 평균을 계산하여 동일 색상으로 렌더링
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        charges = dict(charges)  # 원본 오염 방지를 위해 복사

        ring_atoms_all: set = set()
        rings_data = results.get("rings", [])
        if rings_data:
            for ring in rings_data:
                ring_atoms_all.update(ring)
        # fallback 1: rings 데이터 없으면 aromatic set 사용
        if not ring_atoms_all and aromatic:
            ring_atoms_all = set(aromatic)
        # fallback 2: aromatic도 없으면 island size >= 3인 탄소 원자 사용
        # → 사이클로펜타디에닐 음이온(isl=5), 트로필리움(isl=7) 등
        #   Hückel 방향족 이온: 4n+2 π-전자, 고리 전체에 균등 분포
        #   이전 20회 실패의 근본 원인: 이 fallback 없이 averaging 미적용
        if not ring_atoms_all and atom_is_size:
            for pt_key, is_size in atom_is_size.items():
                _ad_fb = atoms.get(pt_key, {})
                at_sym = _ad_fb.get("main", "C") if isinstance(_ad_fb, dict) else "C"  # Rule N
                # [BUG-3 FIX] carbon은 main=''로 저장됨 (not "C")
                # at_sym == "C"는 절대 True가 되지 않는 버그 → in ('', 'C')로 수정
                # [TASK-RENDER-003] 헤테로 원자(N, O, S)도 고리 구성원으로 포함
                # 피리딘(N), 퓨란(O), 티오펜(S) 등 헤테로고리 방향족 지원
                if is_size >= 3 and at_sym in ('', 'C', 'N', 'O', 'S'):
                    ring_atoms_all.add(pt_key)
            if ring_atoms_all:
                logger.debug(
                    "Ring fallback 2: using %d atoms with isl_size>=3 "
                    "(charged/heterocyclic aromatic ring — Hückel delocalization)",
                    len(ring_atoms_all),
                )

        # [ISSUE-1 fallback 3] 결합 그래프에서 고리 탄소 탐색
        # get_pi_islands_in_mol이 방향족 단결합을 π-참여로 인식 못해
        # all_aromatic/islands 모두 비어있는 경우를 대비한 최후 수단
        # 방법: bond degree >= 2인 원자 = 고리의 일부 (선형 말단 원자는 degree=1)
        # ⚠️ 포화 고리(사이클로헥세인 등) 제외: 이중결합/전하가 하나도 없으면 skip
        if not ring_atoms_all and bonds:
            atom_degree: dict = {}
            for k1, k2 in bonds.keys():
                atom_degree[k1] = atom_degree.get(k1, 0) + 1
                atom_degree[k2] = atom_degree.get(k2, 0) + 1
            ring_candidates = {k for k, d in atom_degree.items() if d >= 2}
            if len(ring_candidates) >= 3:
                # 포화 고리 판별: 고리 원자 간 이중결합 또는 형식전하가 있는지 확인
                has_pi_or_charge = False
                for (k1, k2), bdata in bonds.items():
                    if k1 in ring_candidates and k2 in ring_candidates:
                        bond_order = bdata if isinstance(bdata, (int, float)) else (bdata.get("order", 1) if isinstance(bdata, dict) else 1)  # Rule N
                        if bond_order >= 2:
                            has_pi_or_charge = True
                            break
                if not has_pi_or_charge:
                    # 형식전하 확인 (이온성 방향족: Cp⁻, 트로필리움⁺)
                    for k in ring_candidates:
                        at_data = atoms.get(k, {})
                        if at_data.get("charge", "") in ("+", "-"):
                            has_pi_or_charge = True
                            break
                        fc = at_data.get("formal_charge", 0)
                        if isinstance(fc, (int, float)) and fc != 0:
                            has_pi_or_charge = True
                            break

                if has_pi_or_charge:
                    # 탄소 원자만 포함 (이종원자 고리도 포함하되 순수 C-ring 우선)
                    c_ring = {k for k in ring_candidates
                              if atoms.get(k, {}).get("main", "") in ('', 'C')}
                    ring_atoms_all = c_ring if len(c_ring) >= 3 else ring_candidates
                    logger.debug(
                        "Ring fallback 3 (bond-graph): %d ring atoms detected "
                        "(Cp⁻/tropylium SMILES aromatic-bond fix)",
                        len(ring_atoms_all),
                    )
                else:
                    logger.debug(
                        "Ring fallback 3 skipped: %d ring candidates are saturated "
                        "(no double bonds or formal charges — no π electrons)",
                        len(ring_candidates),
                    )

        if ring_atoms_all:
            # [ISSUE-1] 누락된 ring 원자를 charges에 추가 (기본값 0 = 중성)
            # 이온성 방향족(Cp⁻ 등) → 전하 균등화 후 ionic_bias 적용
            # 중성 방향족(benzene, aspirin 등) → 평준화 하지 않고 자연 분포 유지
            #   (오쏘/파라 선택성 등 치환기 효과를 표현하기 위해 평준화 금지)
            new_ring_atoms = []
            for k in ring_atoms_all:
                if k not in charges:
                    charges[k] = 0.0
                    new_ring_atoms.append(k)
            if new_ring_atoms:
                render_order = list(render_order) + new_ring_atoms
                logger.debug("render_order extended with %d new ring atoms", len(new_ring_atoms))
            # ★ 원본 ring charges 보존 (ionic_bias fallback + 평준화용)
            ring_charges = [charges[k] for k in ring_atoms_all]
            orig_ring_charges = list(ring_charges)
            # ※ 무조건 avg 적용 제거 — ionic_bias 감지 후 이온성만 평준화 (아래)
        else:
            orig_ring_charges = []

        # [Fix v3.1] 사용자 형식전하에 따른 고리 전체 구름 색상 강제 보정
        # 방향족 이온(음이온/양이온)은 charge 비편재화를 고려해 고리 전체에 동일 색상 bias 적용
        # 음이온(charge="-") → 전자 풍부 → charges 값 감소 → RED 방향
        # 양이온(charge="+") → 전자 빈곤 → charges 값 증가 → BLUE 방향
        if ring_atoms_all:
            ionic_bias = 0.0
            for pt_key in ring_atoms_all:
                _adc = atoms.get(pt_key, {})
                atom_data_check = _adc if isinstance(_adc, dict) else {}  # Rule N
                # charge는 문자열 "+"/"-" 또는 정수 formal_charge 두 형식 모두 지원
                user_charge_flag = atom_data_check.get("charge", "")
                formal_charge_val = atom_data_check.get("formal_charge", 0)
                # formal_charge가 int가 아닌 경우 처리
                if isinstance(user_charge_flag, int):
                    formal_charge_val = user_charge_flag
                    user_charge_flag = ""
                elif not isinstance(formal_charge_val, int):
                    formal_charge_val = 0

                # [ISSUE-1 FIX] attach[-1]에 저장된 이온 전하도 확인
                # analyzer.py는 charge 정보를 attach[-1] = "+" 또는 "-"로 저장함
                # "charge"/"formal_charge" 키로는 찾을 수 없어 ionic_bias 미작동
                attach_dict = atom_data_check.get("attach", {})
                if not isinstance(attach_dict, dict):  # Rule N
                    attach_dict = {}
                attach_charge_sign = attach_dict.get(-1, "")
                if attach_charge_sign == "-":
                    formal_charge_val = -1
                elif attach_charge_sign == "+":
                    formal_charge_val = 1

                # ★ 부호 수정 (2026-03-10): 이전 코드는 부호가 반대였음 (mistakes.md 참조)
                if user_charge_flag == "-" or formal_charge_val < 0:
                    ionic_bias = -0.55   # 음이온: charge 음수화 → RED
                    break
                elif user_charge_flag == "+" or formal_charge_val > 0:
                    ionic_bias = +0.45   # 양이온: charge 양수화 → BLUE
                    break

            # ★ Fallback: 원본 charges 분포로 이온성 감지 (atom dict에 charge 정보 없는 경우)
            # 이온성 방향족: RDKit이 formal_charge를 charges dict에 반영했을 경우
            # → 원본 ring charges 중 하나라도 극단값이 있으면 이온성으로 간주
            if ionic_bias == 0.0 and orig_ring_charges:
                max_rc = max(orig_ring_charges)
                min_rc = min(orig_ring_charges)
                if max_rc > 0.35:
                    ionic_bias = +0.45   # 양이온 패턴 → BLUE
                    logger.debug("Ionic fallback (positive): max_ring_charge=%+.3f", max_rc)
                elif min_rc < -0.35:
                    ionic_bias = -0.55   # 음이온 패턴 → RED
                    logger.debug("Ionic fallback (negative): min_ring_charge=%+.3f", min_rc)

            # SMILES에서 이온성 감지 (최후 수단)
            smiles_str = results.get("smiles", "") or ""
            if ionic_bias == 0.0 and smiles_str:
                if "[CH+]" in smiles_str or "[NH+]" in smiles_str or "[cH+]" in smiles_str or "[c+]" in smiles_str:
                    ionic_bias = +0.45   # 양이온 SMILES 패턴 → BLUE
                    logger.debug("Ionic fallback (SMILES cation): %s", smiles_str[:30])
                elif "[CH-]" in smiles_str or "[NH-]" in smiles_str or "[cH-]" in smiles_str or "[c-]" in smiles_str:
                    ionic_bias = -0.55   # 음이온 SMILES 패턴 → RED
                    logger.debug("Ionic fallback (SMILES anion): %s", smiles_str[:30])

            if ionic_bias != 0.0:
                # 이온성 방향족(Cp⁻, 트로필리움 등): 먼저 균등화 후 bias 적용
                # 중성 방향족(benzene, aspirin 등): ionic_bias=0 → 이 블록 통과 안 함
                # → 치환기 효과(오쏘/파라 선택성)가 자연 전하 분포로 보존됨
                ring_charges_now = [charges[k] for k in ring_atoms_all if k in charges]
                if ring_charges_now:
                    avg_eq = sum(ring_charges_now) / len(ring_charges_now)
                    for k in ring_atoms_all:
                        if k in charges:
                            charges[k] = avg_eq + ionic_bias  # 균등화 + bias 동시
                logger.debug(
                    "Ionic ring: equalize(avg=%+.3f) + bias(%+.2f) → %d atoms",
                    avg_eq if ring_charges_now else 0.0, ionic_bias, len(ring_atoms_all),
                )

        base_alpha = VISUAL_SETTINGS.get("cloud_opacity", 140)
        ring_avg_charge = contrast["ring_avg_charge"]
        ring_carbon_charges = contrast["ring_carbon_charges"]
        charge_range = contrast["charge_range"]
        min_charge = contrast["min_charge"]
        max_charge = contrast["max_charge"]
        max_cloud_radius = bond_stats["max_cloud_radius"]
        min_density = density_stats["min"]
        max_density = density_stats["max"]

        electron_rich_carbons: list = []

        # [B9-2 / M222] analyzer ESP 스타일 맵 조회 (sp3 halogen 특화).
        # Rule N: dict 타입 가드.
        esp_style_map_inner = results.get("esp_style_per_atom", {})
        if not isinstance(esp_style_map_inner, dict):
            esp_style_map_inner = {}

        for pt_key in render_order:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔴 명령 2: 사용자 비공유전자쌍 전자구름 제외
            #   user_lp 플래그(사용자가 수동 추가한 비공유전자쌍)나
            #   원소 기호 "LP"는 전자구름 계산에서 완전 스킵
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            _ad_lp = atoms.get(pt_key, {})
            atom_data = _ad_lp if isinstance(_ad_lp, dict) else {}  # Rule N
            if atom_data.get("user_lp") or atom_data.get("main") == "LP":
                continue

            # [B9-2 / M222] ESP 스타일 조회 (show_esp=False → 조기 skip)
            _style_inner = esp_style_map_inner.get(pt_key, None)
            if isinstance(_style_inner, dict):
                if not _style_inner.get("show_esp", True):
                    continue
                _alpha_scale_inner = float(_style_inner.get("alpha_scale", 1.0))
                _radius_scale_inner = float(_style_inner.get("radius_scale", 1.0))
            else:
                _alpha_scale_inner = 1.0
                _radius_scale_inner = 1.0

            charge = charges[pt_key]
            at_main = atom_data.get("main", "C")
            at_lookup = at_main if at_main and at_main != "C" else "C"
            el_data = ELEMENT_DATA.get(at_lookup, ELEMENT_DATA["C"])

            # Phase B: density 매칭
            atom_density = None
            if densities:
                for d in densities:
                    d_pos = (round(d.position[0], 2), round(d.position[1], 2))
                    if d_pos == pt_key:
                        atom_density = d
                        break

            # ── 스케일 계산 ──
            c_scale, d_scale = CloudRenderer._atom_scales(
                at_main, pt_key, el_data, aromatic, atom_is_size, results,
            )

            # ── 좌표 선택 ──
            if use_theory_coords:
                _td_lp = results.get("theory_data", {})
                if not isinstance(_td_lp, dict):  # Rule N
                    _td_lp = {}
                t_map = _td_lp.get("map", {})
                if not isinstance(t_map, dict):  # Rule N
                    t_map = {}
                lookup_key = (round(pt_key[0], 2), round(pt_key[1], 2))
                center = t_map.get(lookup_key, QPointF(*pt_key))
            else:
                center = QPointF(*pt_key)

            isl_size = atom_is_size.get(pt_key, 0)

            # ── strength / charge_intensity ──
            # ★ [BUG-3 Fix] ring_atoms_all에 포함된 모든 원자는 방향족 강도(2.2) 사용
            # 이유: [cH-]/[cH+] 등 이온화 원자는 aromatic set에 누락될 수 있으나,
            #       ring_atoms_all에는 포함됨. strength 불일치 → 고리 내 불균등 cloud 크기 유발
            raw_strength = 2.2 if (pt_key in aromatic or pt_key in ring_atoms_all) else (0.85 if isl_size >= 2 else 0.0)
            strength = math.sqrt(raw_strength) * 1.3

            # [FIX-ESP v6] Hybridization-based ESP cloud gating:
            #   sp2/sp atoms: always show cloud (pi system)
            #   sp3 + halogen neighbor (F,Cl,Br,I): faint wide cloud (inductive effect)
            #   sp3 without EDG/EWG neighbors: NO cloud
            is_heteroatom = at_main not in ('', 'C', 'H')
            is_in_pi_system = (pt_key in aromatic or pt_key in ring_atoms_all or isl_size >= 2)
            has_formal_charge = atom_data.get("charge", "") in ("+", "-")

            # Check bonds for multiple bond or halogen neighbor
            has_multiple_bond = False
            has_halogen_neighbor = False
            _HALOGENS = {'F', 'Cl', 'Br', 'I'}
            for (k1, k2), bdata in bonds.items():
                if k1 == pt_key or k2 == pt_key:
                    bo = bdata if isinstance(bdata, (int, float)) else 1
                    if bo >= 1.5:
                        has_multiple_bond = True
                    # Check if neighbor is a halogen
                    neighbor_key = k2 if k1 == pt_key else k1
                    _nd = atoms.get(neighbor_key, {})
                    neighbor_data = _nd if isinstance(_nd, dict) else {}  # Rule N
                    neighbor_sym = neighbor_data.get("main", "")
                    if neighbor_sym in _HALOGENS:
                        has_halogen_neighbor = True

            # Determine if this is an sp3 carbon (no pi bonds, no aromaticity)
            is_sp3_carbon = (at_main in ('', 'C') and not is_in_pi_system
                             and not has_multiple_bond and not has_formal_charge)

            # sp3 carbon gating: skip unless it has a halogen neighbor
            _sp3_halogen_faint = False  # flag for faint cloud rendering
            if is_sp3_carbon:
                if has_halogen_neighbor:
                    # sp3 + halogen: allow but mark for faint rendering
                    _sp3_halogen_faint = True
                elif not is_heteroatom:
                    # Pure sp3 C-H with no special neighbors: skip cloud
                    continue

            # Non-carbon sp3 atoms (O, N, S etc.) without pi/charge: skip cloud
            # unless they ARE heteroatoms (lone pairs create ESP effects)
            if not (is_heteroatom or is_in_pi_system or has_formal_charge
                    or has_multiple_bond or _sp3_halogen_faint):
                continue

            charge_intensity = abs(charge - ring_avg_charge) * 100.0 * d_scale
            charge_intensity = min(charge_intensity, 5.0)

            # [FIX-ESP v6] sp3+halogen atoms always pass the intensity check
            # (their inductive effect cloud is handled via _sp3_halogen_faint flag)
            if charge_intensity < 0.1 and strength < 0.1 and not _sp3_halogen_faint:
                continue
            # For sp3+halogen, ensure minimum charge_intensity for visible cloud
            if _sp3_halogen_faint and charge_intensity < 0.5:
                charge_intensity = 0.5  # minimum inductive effect visibility

            # ── 반응성 가중치 (v3.2) ──
            # [BUG-3 FIX] at_main=="" (빈 문자열) = 탄소 (ChemGrid 규칙)
            # at_main == "C"는 절대 True가 안 됨 → is_ring_carbon 항상 False → local_normalized 미사용
            is_ring_carbon = (at_main in ('', 'C') and (pt_key in aromatic or isl_size >= 2))
            if is_ring_carbon:
                charge_deviation = charge - ring_avg_charge
                reactivity_weight = min(math.exp(abs(charge_deviation) * 15.0), 3.0)
                if charge < ring_avg_charge:
                    electron_rich_carbons.append((pt_key, charge, center))
            else:
                reactivity_weight = 1.0

            # ── 반지름 계산 (v3.3 — 지향성 강화 가변 구름) ──
            base_radius = (
                19.5
                + math.log1p(charge_intensity) * 15.0
                + strength * 7.5
            ) * c_scale
            radius = min(base_radius, max_cloud_radius, 90.0)  # [FIX-CONTOUR v1] 절대 한도

            # [FIX-ESP v4] 고리 탄소 반지름 차이 제거 — 균일 전자구름
            # 방향족 고리의 π전자는 비편재화 → 모든 위치 동일 크기
            # (반응 분석 모드에서만 지향성 크기 차이를 별도로 표시)

            # ── 색상 결정 ──
            color, alpha = CloudRenderer._calculate_charge_color(
                pt_key, charge, at_main, is_ring_carbon,
                isl_size, atom_density, densities,
                ring_carbon_charges, ring_avg_charge,
                charge_range, min_charge, max_charge,
                min_density, max_density,
                base_alpha, strength, charge_intensity,
                reactivity_weight,
            )

            # [FIX-ESP v6] sp3 + halogen neighbor: faint wide cloud (inductive effect)
            # Reduce alpha by 60% and increase radius by 30% for diffuse inductive cloud
            if _sp3_halogen_faint:
                alpha = int(alpha * 0.4)   # 40% of normal opacity — faint
                radius = radius * 1.3      # 30% wider — diffuse inductive effect

            # [B9-2 / M222] analyzer 제공 ESP 스타일 스케일 적용 (sp3 halogen 원자 자체 얕게).
            # Rule I: alpha_scale 0.3 = 교과서 관찰 기반 매직넘버 (낮은 유효 전하 대비
            # 적정 가시성 유지). 두 플래그(_sp3_halogen_faint + esp_style)는 서로 다른
            # 상황에 적용되므로 누적 가능 — halogen 이웃 탄소 + 자신도 halogen인 드문 경우.
            if _alpha_scale_inner != 1.0:
                alpha = int(alpha * _alpha_scale_inner)
            if _radius_scale_inner != 1.0:
                radius = radius * _radius_scale_inner

            # ── 가우시안 렌더링 (3-stop gradient: 중심→중간→가장자리) ──
            alpha = max(0, min(255, alpha))  # [FIX] clamp to valid range
            color.setAlpha(alpha)
            mid_color = QColor(color.red(), color.green(), color.blue(), max(0, min(255, int(alpha * 0.4))))
            grad = QRadialGradient(center, radius)
            grad.setColorAt(0, color)              # 중심: 최대 색상
            grad.setColorAt(0.55, mid_color)       # 중간: 40% 밀도 유지
            grad.setColorAt(1, QColor(255, 255, 255, 0))  # 가장자리: 투명
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, radius + 2, radius + 2)

        return electron_rich_carbons

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 원자별 스케일 계산
    # ------------------------------------------------------------------
    @staticmethod
    def _atom_scales(
        at_main: str,
        pt_key,
        el_data: dict,
        aromatic: set,
        atom_is_size: Dict,
        results: dict,
    ) -> Tuple[float, float]:
        """원자별 (cloud_scale, density_scale) 반환."""
        bonds = results.get("bonds", {})
        if not isinstance(bonds, dict):  # Rule N
            bonds = {}
        atoms = results.get("atoms", {})
        if not isinstance(atoms, dict):  # Rule N
            atoms = {}

        if at_main == "H":
            is_polar_h = False
            for bond_pair in bonds.keys():
                if pt_key in bond_pair:
                    neighbor = bond_pair[1] if bond_pair[0] == pt_key else bond_pair[0]
                    _nd_h = atoms.get(neighbor, {})
                    n_main = _nd_h.get("main", "") if isinstance(_nd_h, dict) else ""  # Rule N
                    if n_main in ("N", "O", "F"):
                        is_polar_h = True
                        break
            if is_polar_h:
                return 0.38, 1.3
            return 0.5, 0.5

        is_substituent = (
            at_main in ("O", "N", "F", "Cl", "Br", "S", "P")
            and pt_key not in aromatic
            and atom_is_size.get(pt_key, 0) < 2
        )
        if is_substituent:
            base_c = el_data.get("cloud_scale", 1.0)
            return base_c * 0.80, el_data.get("density_scale", 1.0) * 1.5

        return el_data.get("cloud_scale", 1.0), el_data.get("density_scale", 1.0)

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 색상 계산
    # ------------------------------------------------------------------
    @staticmethod
    def _calculate_charge_color(
        pt_key,
        charge: float,
        at_main: str,
        is_ring_carbon: bool,
        isl_size: int,
        atom_density,
        densities,
        ring_carbon_charges: list,
        ring_avg_charge: float,
        charge_range: float,
        min_charge: float,
        max_charge: float,
        min_density: float,
        max_density: float,
        base_alpha: int,
        strength: float,
        charge_intensity: float,
        reactivity_weight: float,
    ) -> Tuple[QColor, int]:
        """원자 하나의 (QColor, alpha) 를 반환."""
        # Phase B: ESP 기반
        if densities and atom_density:
            color = CloudRenderer.calculate_esp_color(
                atom_density.density, min_density, max_density,
            )
            alpha = max(0, min(255, int(base_alpha * min(charge_intensity, 1.5))))
            return color, alpha

        # 고리 원자 (isl_size >= 2)
        if isl_size >= 2:
            if is_ring_carbon and ring_carbon_charges and len(ring_carbon_charges) > 1:
                # [FIX-ESP v5 / TASK-RENDER-003] 복잡 치환 방향족 처리
                # 단순 방향족 (벤젠, 톨루엔): π전자 비편재화 → 균일 색상
                # 복합 치환 방향족 (니트로아닐린 NH2+NO2): 푸시-풀 효과 →
                #   개별 전하와 평균 전하를 블렌딩하여 약한 그라데이션 표현
                #
                # 판별 기준: ring_carbon_charges의 범위(max-min)
                #   < 0.08: 약한 치환 효과 → 순수 ring_avg (벤젠/톨루엔/나프탈렌)
                #   >= 0.08: 강한 push-pull → 80% avg + 20% individual (니트로아닐린)
                #   >= 0.15: 매우 강한 push-pull → 60% avg + 40% individual
                ring_min_c = min(ring_carbon_charges)
                ring_max_c = max(ring_carbon_charges)
                ring_spread = ring_max_c - ring_min_c

                if ring_spread < 0.08:
                    # 약한 치환 효과: 순수 균일 색상 (기존 동작)
                    effective_charge = ring_avg_charge
                elif ring_spread < 0.15:
                    # 중간 push-pull: 약한 그라데이션 (80% avg + 20% individual)
                    effective_charge = ring_avg_charge * 0.80 + charge * 0.20
                else:
                    # 강한 push-pull (nitroaniline 등): 뚜렷한 그라데이션
                    effective_charge = ring_avg_charge * 0.60 + charge * 0.40

                color = CloudRenderer.charge_to_color(effective_charge, -1.0, 1.0)
            else:
                # 고리 내 비탄소 원자 (N, O 등) → 고유 전하 기반 색상
                color = CloudRenderer.charge_to_color(charge, -1.0, 1.0)

            base_layer_alpha = base_alpha * min(
                max(strength, charge_intensity * 1.1), 1.5,
            )
            if is_ring_carbon:
                base_layer_alpha *= 1.5
            alpha = max(0, min(255, int(base_layer_alpha)))
            return color, alpha

        # 기본: 전하 기반
        color = CloudRenderer.charge_to_color(charge, min_charge, max_charge)
        alpha = max(0, min(255, int(base_alpha * min(charge_intensity, 1.5))))
        return color, alpha

    # ------------------------------------------------------------------
    # draw_clouds 내부 헬퍼: 조준선 데이터 저장
    # ------------------------------------------------------------------
    @staticmethod
    def _store_crosshair_data(results: dict, electron_rich_carbons: list):
        """전자 밀도 상위 탄소 조준선 좌표를 results에 저장."""
        if not electron_rich_carbons:
            return

        electron_rich_carbons.sort(key=lambda x: x[1])
        num_markers = min(3, max(2, len(electron_rich_carbons) // 3))
        top_sites = electron_rich_carbons[:num_markers]

        logger.debug(
            "Crosshairs: storing %d markers (top electron-rich carbons)",
            len(top_sites),
        )

        results["crosshairs_v32"] = [
            (pt_key, charge_val, pos)
            for pt_key, charge_val, pos in top_sites
        ]

    # ==================================================================
    # [CHEM-7] 방향족 π 비편재화 halo 렌더링
    # ==================================================================
    @staticmethod
    def draw_pi_cloud_halo(
        painter,
        rings: list,
        aromatic_nodes: set,
        charges: Dict,
        use_theory_coords: bool = False,
        theory_map: Dict = None,
        base_alpha: int = 55,
    ):
        """[CHEM-7] 방향족 고리의 연속 π 비편재화 halo를 렌더링합니다.

        개별 원자 가우시안 구름보다 먼저 그려져 π cloud 배경을 형성합니다.
        방향족 고리 원자들의 전자밀도(charges) 차이를 반영하여
        EDG 치환기가 있는 경우 전자 풍부 방향으로 그라데이션이 이동합니다.

        이론적 근거:
        - 방향족 π 시스템: 전자가 고리 전체에 비편재화 → 고리를 덮는 연속 구름
        - sp2 탄소의 p 오비탈이 겹쳐 delocalized π MO 형성 → 도넛 모양 전자밀도
        - EDG 치환기(OH, NH2 등): 오쏘/파라 위치 전자밀도 증가 → 그라데이션 편향
        """
        if not rings or not aromatic_nodes:
            return

        if not isinstance(theory_map, dict):  # Rule N
            theory_map = {}
        if not isinstance(charges, dict):  # Rule N
            charges = {}

        painter.save()
        try:
            for ring in rings:
                if len(ring) < 3:
                    continue
                # 방향족 고리인지 확인 (모든 원자가 방향족)
                if not all(node in aromatic_nodes for node in ring):
                    continue

                # 좌표 계산 (theory 또는 drawing)
                positions_with_nodes = []
                for node in ring:
                    if use_theory_coords and theory_map:
                        lookup = (round(node[0], 2), round(node[1], 2))
                        pt = theory_map.get(lookup, QPointF(*node))
                    else:
                        pt = QPointF(*node)
                    positions_with_nodes.append((pt, node))

                if not positions_with_nodes:
                    continue

                pts = [p for p, _ in positions_with_nodes]

                # 무게중심 계산
                cx = sum(p.x() for p in pts) / len(pts)
                cy = sum(p.y() for p in pts) / len(pts)
                center = QPointF(cx, cy)

                # 반지름 (무게중심 ~ 원자 평균 거리)
                radii = [math.sqrt((p.x() - cx) ** 2 + (p.y() - cy) ** 2) for p in pts]
                avg_radius = sum(radii) / len(radii) if radii else 30.0
                halo_radius = min(avg_radius * 1.35, 120.0)  # [FIX-CONTOUR v1] 클램프

                # 전자 분포 비대칭 감지 (EDG → 전자 풍부 위치 찾기)
                ring_charges = {node: charges.get(node, 0.0) for _, node in positions_with_nodes}
                if ring_charges and len(ring_charges) > 1:
                    min_charge_node = min(ring_charges, key=ring_charges.get)
                    avg_ch = sum(ring_charges.values()) / len(ring_charges)
                    min_ch = ring_charges[min_charge_node]
                    charge_asymmetry = abs(avg_ch - min_ch)

                    # 전자 풍부 위치로 중심 이동 (비대칭이 있을 때만)
                    if charge_asymmetry > 0.02:
                        if use_theory_coords and theory_map:
                            lookup = (round(min_charge_node[0], 2), round(min_charge_node[1], 2))
                            rich_pt = theory_map.get(lookup, QPointF(*min_charge_node))
                        else:
                            rich_pt = QPointF(*min_charge_node)
                        # 중심에서 전자 풍부 방향으로 최대 18% 이동
                        shift_ratio = min(charge_asymmetry * 4.0, 0.18)
                        shifted_cx = cx + (rich_pt.x() - cx) * shift_ratio
                        shifted_cy = cy + (rich_pt.y() - cy) * shift_ratio
                        center = QPointF(shifted_cx, shifted_cy)

                # π halo 방사 그라데이션 (McMurry 기준: π 전자는 전자풍부 → RED)
                # 방향족 π 전자는 고리 전체에 비편재화된 전자 → 전자 밀도 높음 → RED
                pi_color = QColor(220, 60, 30)

                grad = QRadialGradient(center, halo_radius)
                inner_c = QColor(pi_color)
                inner_c.setAlpha(int(base_alpha * 0.25))   # 중심: 연하게
                mid_c = QColor(pi_color)
                mid_c.setAlpha(base_alpha)                  # 고리 근처: 최대
                edge_c = QColor(pi_color)
                edge_c.setAlpha(0)

                grad.setColorAt(0.0, inner_c)
                grad.setColorAt(0.62, mid_c)   # avg_radius / halo_radius ≈ 0.74
                grad.setColorAt(1.0, edge_c)

                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(center, halo_radius, halo_radius)
        finally:
            painter.restore()

    # ==================================================================
    # 2D Pi 오비탈 로브 렌더링 (CHEM-PI-2D)
    # ==================================================================
    @staticmethod
    def draw_pi_orbital_lobes_2d(
        painter,
        results,
        use_theory_coords: bool = False,
    ):
        """[CHEM-PI-2D] sp2/sp 원자의 p-오비탈 로브를 2D로 렌더링합니다.

        화학적 원리:
        - sp2 혼성 원자의 비혼성화 p 오비탈은 분자 평면에 수직 방향
        - 2D 투영에서는 결합 방향에 수직인 방향으로 두 로브를 표시
        - 양의 위상(파란색)과 음의 위상(빨간색) 로브가 결합축 양쪽에 배치

        구현:
        - 이중/삼중결합 또는 방향족에 참여하는 원자 감지
        - 각 원자에서 pi결합 방향의 평균 수직 벡터 계산
        - 결합축에 수직(= 분자면에 수직의 2D 투영) 방향으로 로브 배치
        """
        if not results or not isinstance(results, dict):  # Rule N
            return

        atoms_data = results.get("atoms", {})
        if not isinstance(atoms_data, dict):  # Rule N
            atoms_data = {}
        bonds = results.get("bonds", {})
        if not isinstance(bonds, dict):  # Rule N
            bonds = {}
        aromatic = results.get("aromatic", set())
        if not isinstance(aromatic, (set, list, frozenset)):  # Rule N
            aromatic = set()
        _td_pi = results.get("theory_data", {})
        if not isinstance(_td_pi, dict):  # Rule N
            _td_pi = {}
        theory_map = _td_pi.get("map", {}) if use_theory_coords else {}
        if not isinstance(theory_map, dict):  # Rule N
            theory_map = {}

        if not bonds:
            return

        # 1) sp2/pi 참여 원자 및 해당 결합 방향 수집
        # 각 원자에 대해 pi결합 이웃 방향들을 수집
        pi_atom_bonds = {}  # {atom_key: [(neighbor_key, bond_order), ...]}
        for (k1, k2), bdata in bonds.items():
            order = bdata if isinstance(bdata, (int, float)) else 1
            is_pi = (order >= 1.5 or k1 in aromatic or k2 in aromatic)
            if not is_pi:
                continue
            pi_atom_bonds.setdefault(k1, []).append((k2, order))
            pi_atom_bonds.setdefault(k2, []).append((k1, order))

        if not pi_atom_bonds:
            return

        painter.save()
        try:
            painter.setPen(Qt.PenStyle.NoPen)

            # 로브 색상 (교과서 표준: 양의 위상 = 파랑, 음의 위상 = 빨강)
            lobe_pos_color = QColor(65, 130, 255, 100)  # 파란색 반투명
            lobe_neg_color = QColor(255, 90, 65, 100)   # 빨간색 반투명

            for pt_key, neighbors in pi_atom_bonds.items():
                atom_data = atoms_data.get(pt_key, {})
                at_main = atom_data.get("main", "") or "C"

                # H 원자는 p-오비탈 없음
                if at_main == "H":
                    continue

                # 좌표 계산
                if use_theory_coords and theory_map:
                    lookup = (round(pt_key[0], 2), round(pt_key[1], 2))
                    center = theory_map.get(lookup, QPointF(*pt_key))
                else:
                    center = QPointF(*pt_key)

                # 2) 이 원자의 pi결합 이웃들의 방향 벡터 수집
                bond_dirs = []
                for nb_key, _order in neighbors:
                    if use_theory_coords and theory_map:
                        nb_lookup = (round(nb_key[0], 2), round(nb_key[1], 2))
                        nb_pos = theory_map.get(nb_lookup, QPointF(*nb_key))
                    else:
                        nb_pos = QPointF(*nb_key)
                    dx = nb_pos.x() - center.x()
                    dy = nb_pos.y() - center.y()
                    mag = math.hypot(dx, dy)
                    if mag > 1.0:
                        bond_dirs.append((dx / mag, dy / mag))

                if not bond_dirs:
                    continue

                # 3) pi결합 방향들의 평균 → 그 수직이 로브 방향
                # 방향족의 경우 여러 결합이 있으므로, 가장 의미 있는 수직 방향을 구함
                # 방법: 모든 결합 방향의 수직 벡터를 평균하여 일관된 방향 산출
                # 단일 결합: 수직벡터 = (-dy, dx)
                # 복수 결합: 각 수직벡터의 부호를 정렬 후 평균

                perp_x, perp_y = 0.0, 0.0
                for dx, dy in bond_dirs:
                    # 결합 방향의 수직 (2D에서 90도 회전)
                    px, py = -dy, dx
                    # 부호 일관성: 항상 "위쪽"(음의 y) 방향을 양으로 설정
                    if py > 0:
                        px, py = -px, -py
                    perp_x += px
                    perp_y += py

                mag = math.hypot(perp_x, perp_y)
                if mag < 0.01:
                    # 모든 결합이 대칭이면 기본 수직 방향 사용
                    perp_x, perp_y = 0.0, -1.0
                else:
                    perp_x /= mag
                    perp_y /= mag

                # 4) 평균 결합 길이로 로브 크기 결정
                # [FIX-CONTOUR v1] 비정상 길이 필터 + 클램프
                bond_lengths = []
                for nb_key, _order in neighbors:
                    if use_theory_coords and theory_map:
                        nb_lookup = (round(nb_key[0], 2), round(nb_key[1], 2))
                        nb_pos = theory_map.get(nb_lookup, QPointF(*nb_key))
                    else:
                        nb_pos = QPointF(*nb_key)
                    bl = math.hypot(nb_pos.x() - center.x(), nb_pos.y() - center.y())
                    if 1 < bl < 300:  # [FIX-CONTOUR v1] 비정상 길이 필터
                        bond_lengths.append(bl)

                avg_bl = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 40.0
                avg_bl = min(avg_bl, 120.0)  # [FIX-CONTOUR v1] 클램프
                lobe_offset = avg_bl * 0.32   # 로브 중심까지 거리 (결합 길이의 32%)
                lobe_rx = avg_bl * 0.18        # 로브 가로 반경 (결합 방향)
                lobe_ry = avg_bl * 0.28        # 로브 세로 반경 (수직 방향, 더 길게)

                # 5) 양쪽 로브 렌더링 (수직 방향으로 오프셋)
                for sign, color in ((+1, lobe_pos_color), (-1, lobe_neg_color)):
                    lobe_cx = center.x() + sign * perp_x * lobe_offset
                    lobe_cy = center.y() + sign * perp_y * lobe_offset
                    lobe_center = QPointF(lobe_cx, lobe_cy)

                    # 로브 방향에 맞는 타원: 결합축을 따라 좁고, 수직 방향으로 김
                    # 타원 회전을 위해 QPainterPath 사용
                    lobe_path = QPainterPath()

                    # 수직 방향 각도 계산 (타원 회전용)
                    angle_rad = math.atan2(perp_y, perp_x)

                    # 반투명 가우시안 그라데이션 로브
                    grad = QRadialGradient(lobe_center, max(lobe_rx, lobe_ry))
                    inner_c = QColor(color)
                    inner_c.setAlpha(color.alpha())
                    mid_c = QColor(color)
                    mid_c.setAlpha(int(color.alpha() * 0.5))
                    edge_c = QColor(color)
                    edge_c.setAlpha(0)
                    grad.setColorAt(0.0, inner_c)
                    grad.setColorAt(0.6, mid_c)
                    grad.setColorAt(1.0, edge_c)

                    painter.setBrush(QBrush(grad))
                    painter.drawEllipse(lobe_center, lobe_rx, lobe_ry)

        finally:
            painter.restore()

    # ==================================================================
    # 조준선 렌더링  (v3.2)
    # ==================================================================
    @staticmethod
    def draw_crosshairs_v32(painter, results):
        if not results or not isinstance(results, dict):  # Rule N
            return

        crosshair_data = results.get("crosshairs_v32", [])
        if not isinstance(crosshair_data, list):  # Rule N
            crosshair_data = []
        if not crosshair_data:
            return

        painter.save()
        painter.setClipping(False)

        pen = QPen(QColor(0, 255, 0, 255))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        for _pt_key, _charge_val, pos in crosshair_data:
            marker_size = 24.0

            # 수평선
            p1_h = QPointF(pos.x() - marker_size, pos.y())
            p2_h = QPointF(pos.x() + marker_size, pos.y())
            painter.drawLine(p1_h, p2_h)
            
            # 수직선
            p1_v = QPointF(pos.x(), pos.y() - marker_size)
            p2_v = QPointF(pos.x(), pos.y() + marker_size)
            painter.drawLine(p1_v, p2_v)
            
            # 외곽 원 3개 (조준경 효과)
            painter.drawEllipse(pos, marker_size * 0.7, marker_size * 0.7)
            painter.drawEllipse(pos, marker_size * 0.45, marker_size * 0.45)
            painter.drawEllipse(pos, marker_size * 0.2, marker_size * 0.2)

        painter.restore()

    # ==================================================================
    # 입체 라벨 렌더링
    # ==================================================================
    @staticmethod
    def draw_stereo_labels(painter, results):
        """[해결] 입체 중심 라벨 전용 렌더링: 9pt 적색, 최상단 배치 고정."""
        if not results or not isinstance(results, dict):  # Rule N
            return
        stereo_data = results.get("stereo", {})
        if not isinstance(stereo_data, dict):  # Rule N
            stereo_data = {}
        if not stereo_data:
            return

        painter.save()
        painter.setPen(QColor("#FF0000"))
        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        for pt_key, label in stereo_data.items():
            pos = QPointF(*pt_key)
            painter.drawText(pos + QPointF(6, -6), label)
        painter.restore()

    # ==================================================================
    # [RENDER-R03] Drawing 레이어 부분전하 표시 (ESP와 별도)
    # ==================================================================
    @staticmethod
    def draw_partial_charges(
        painter,
        results,
    ):
        """
        Drawing 레이어 전용 간단한 부분전하(delta+/delta-) 표시.

        ESP 전자구름과 별도로, 각 원자의 Gasteiger 부분전하를
        delta+/delta- 기호로 원자 옆에 작게 표시합니다.

        표시 기준:
        - |charge| >= 0.10: delta 기호 표시 (미세한 전하는 생략)
        - 음전하: delta- (적색, 전자 풍부)
        - 양전하: delta+ (청색, 전자 부족)
        - 순수 sp3 C-H 원자는 생략

        Args:
            painter: QPainter 인스턴스
            results: analysis_results 딕셔너리
        """
        if not results or not isinstance(results, dict):  # Rule N
            return

        charges = results.get("charges", {})
        if not isinstance(charges, dict):  # Rule N
            charges = {}
        atoms_data = results.get("atoms", {})
        if not isinstance(atoms_data, dict):  # Rule N
            atoms_data = {}
        bonds = results.get("bonds", {})
        if not isinstance(bonds, dict):  # Rule N
            bonds = {}
        if not charges:
            return

        CHARGE_THRESHOLD = 0.10  # |charge| < 0.10 → 표시 안함

        painter.save()
        try:
            font = QFont("Arial", 9, QFont.Weight.Bold)
            painter.setFont(font)

            for pt_key, charge in charges.items():
                if abs(charge) < CHARGE_THRESHOLD:
                    continue

                atom_data = atoms_data.get(pt_key, {})
                at_main = atom_data.get("main", "") or "C"

                # sp3 포화 탄화수소 필터 (π계/헤테로/전하 원자만 표시)
                is_hetero = at_main not in ('', 'C', 'H')
                has_formal_charge = atom_data.get("charge", "") in ("+", "-")
                has_mult_bond = False
                for (k1, k2), bdata in bonds.items():
                    if k1 == pt_key or k2 == pt_key:
                        bo = bdata if isinstance(bdata, (int, float)) else 1
                        if bo >= 1.5:
                            has_mult_bond = True
                            break
                if not (is_hetero or has_formal_charge or has_mult_bond):
                    continue

                center = QPointF(*pt_key)

                # delta 기호 및 색상
                if charge < 0:
                    symbol = "δ⁻"  # delta-minus
                    color = QColor(200, 30, 30, 180)  # 적색 반투명
                else:
                    symbol = "δ⁺"  # delta-plus
                    color = QColor(30, 80, 200, 180)  # 청색 반투명

                painter.setPen(color)

                # 원자 기호 크기 기반 오프셋 (우상단 배치)
                main_font = QFont("Arial", 14, QFont.Weight.Bold)
                fm_main = QFontMetrics(main_font)
                display_sym = at_main if at_main not in ('', 'C') else "C"
                sym_half_w = fm_main.horizontalAdvance(display_sym) / 2
                sym_half_h = fm_main.height() / 2

                # 우상단에 작게 표시
                offset_x = max(sym_half_w, 6) + 2
                offset_y = -sym_half_h - 1

                painter.drawText(
                    QPointF(center.x() + offset_x, center.y() + offset_y),
                    symbol,
                )
        finally:
            painter.restore()

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------
    @staticmethod
    def _blend(c1: QColor, c2: QColor, r: float) -> QColor:
        return QColor(
            int(c1.red() * (1 - r) + c2.red() * r),
            int(c1.green() * (1 - r) + c2.green() * r),
            int(c1.blue() * (1 - r) + c2.blue() * r),
        )


# ============================================================================
# 하위 호환 별칭: 기존 코드에서 DFTDensityRenderer를 참조하는 곳 지원
# ============================================================================
DFTDensityRenderer = CloudRenderer
