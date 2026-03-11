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
    QColor, QRadialGradient, QBrush, QFont, QPainterPath, QPen,
)
from PyQt6.QtCore import Qt, QPointF, QThread, pyqtSignal
from chem_data import VISUAL_SETTINGS, ELEMENT_DATA
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

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
    "Fe": QColor(224, 102, 51),       # 주황갈색
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
        charge_range = max(abs(min_charge), abs(max_charge), 0.05)
        normalized = max(-1.0, min(1.0, charge / charge_range))

        if normalized < -0.05:   # 전자 풍부 → RED
            intensity = abs(normalized)
            r = 255
            g = int(60 - 60 * intensity)    # 0~60 (순수 RED로)
            b = int(60 - 60 * intensity)
            alpha = int(130 + 125 * intensity)
        elif normalized > 0.05:  # 전자 부족 → BLUE
            intensity = normalized
            r = int(60 - 60 * intensity)
            g = int(60 - 60 * intensity)
            b = 255
            alpha = int(130 + 125 * intensity)
        else:                    # 중성 → GREEN
            intensity = 1.0 - abs(normalized) / 0.05 if abs(normalized) < 0.05 else 0.0
            r = int(30 + 20 * intensity)
            g = int(180 + 50 * intensity)
            b = int(30 + 20 * intensity)
            alpha = int(110 + 40 * intensity)

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
        if not results:
            return

        charges = results.get("charges", {})
        islands = results.get("islands", [])
        aromatic = results.get("aromatic", set())
        atoms = results.get("atoms", {})
        bonds = results.get("bonds", {})

        logger.debug(
            "draw_clouds called — atoms=%d, use_theory=%s",
            len(charges), use_theory_coords,
        )

        if not charges:
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
            _theory_map = results.get("theory_data", {}).get("map", {}) if use_theory_coords else {}
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
        ring_carbon_charges: List[float] = []
        for pt_key, charge in charges.items():
            at_main = atoms.get(pt_key, {}).get("main", "C")
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
                bond_lengths.append(dist)
        avg = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 40.0
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
        substituent_atoms: List = []
        ring_atoms: List = []

        for pt_key in charges:
            at_main = atoms.get(pt_key, {}).get("main", "C")
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
        atoms = results.get("atoms", {})
        aromatic = results.get("aromatic", set())
        bonds = results.get("bonds", {})

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
                at_sym = atoms.get(pt_key, {}).get("main", "C")
                # [BUG-3 FIX] carbon은 main=''로 저장됨 (not "C")
                # at_sym == "C"는 절대 True가 되지 않는 버그 → in ('', 'C')로 수정
                if is_size >= 3 and at_sym in ('', 'C'):
                    ring_atoms_all.add(pt_key)
            if ring_atoms_all:
                logger.debug(
                    "Ring fallback 2: using %d atoms with isl_size>=3 "
                    "(charged aromatic ring — Hückel delocalization)",
                    len(ring_atoms_all),
                )

        # [ISSUE-1 fallback 3] 결합 그래프에서 고리 탄소 탐색
        # get_pi_islands_in_mol이 방향족 단결합을 π-참여로 인식 못해
        # all_aromatic/islands 모두 비어있는 경우를 대비한 최후 수단
        # 방법: bond degree >= 2인 원자 = 고리의 일부 (선형 말단 원자는 degree=1)
        if not ring_atoms_all and bonds:
            atom_degree: dict = {}
            for k1, k2 in bonds.keys():
                atom_degree[k1] = atom_degree.get(k1, 0) + 1
                atom_degree[k2] = atom_degree.get(k2, 0) + 1
            ring_candidates = {k for k, d in atom_degree.items() if d >= 2}
            if len(ring_candidates) >= 3:
                # 탄소 원자만 포함 (이종원자 고리도 포함하되 순수 C-ring 우선)
                c_ring = {k for k in ring_candidates
                          if atoms.get(k, {}).get("main", "") in ('', 'C')}
                ring_atoms_all = c_ring if len(c_ring) >= 3 else ring_candidates
                logger.debug(
                    "Ring fallback 3 (bond-graph): %d ring atoms detected "
                    "(Cp⁻/tropylium SMILES aromatic-bond fix)",
                    len(ring_atoms_all),
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
                atom_data_check = atoms.get(pt_key, {})
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

        for pt_key in render_order:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔴 명령 2: 사용자 비공유전자쌍 전자구름 제외
            #   user_lp 플래그(사용자가 수동 추가한 비공유전자쌍)나
            #   원소 기호 "LP"는 전자구름 계산에서 완전 스킵
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            atom_data = atoms.get(pt_key, {})
            if atom_data.get("user_lp") or atom_data.get("main") == "LP":
                continue

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
                t_map = results.get("theory_data", {}).get("map", {})
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

            charge_intensity = abs(charge - ring_avg_charge) * 100.0 * d_scale
            charge_intensity = min(charge_intensity, 5.0)

            if charge_intensity < 0.1 and strength < 0.1:
                continue

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

            # ── 반지름 계산 (v3.2 가변 구름) ──
            base_radius = (
                19.5
                + math.log1p(charge_intensity) * 15.0
                + strength * 7.5
            ) * c_scale
            radius = min(base_radius, max_cloud_radius)

            if is_ring_carbon and charge > ring_avg_charge:
                radius *= 0.60  # 비활성 탄소 40% 축소

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

            # ── 가우시안 렌더링 ──
            color.setAlpha(alpha)
            grad = QRadialGradient(center, radius)
            grad.setColorAt(0, color)
            grad.setColorAt(1, QColor(255, 255, 255, 0))
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
        atoms = results.get("atoms", {})

        if at_main == "H":
            is_polar_h = False
            for bond_pair in bonds.keys():
                if pt_key in bond_pair:
                    neighbor = bond_pair[1] if bond_pair[0] == pt_key else bond_pair[0]
                    n_main = atoms.get(neighbor, {}).get("main", "")
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
            alpha = int(base_alpha * min(charge_intensity, 1.5))
            return color, alpha

        # 고리 원자 (isl_size >= 2)
        if isl_size >= 2:
            if is_ring_carbon and ring_carbon_charges and len(ring_carbon_charges) > 1:
                ring_min = min(ring_carbon_charges)
                ring_max = max(ring_carbon_charges)
                ring_range = ring_max - ring_min
                if ring_range > 0.05:
                    # 충분한 분산 → local_normalized 방식 사용
                    local_normalized = max(0.0, min(1.0, (charge - ring_min) / ring_range))
                    if local_normalized < 0.45:
                        ratio = local_normalized / 0.45
                        r = 255
                        g = int(60 * ratio)
                        b = int(60 * ratio)
                    elif local_normalized > 0.55:
                        ratio = (local_normalized - 0.55) / 0.45
                        r = int(60 * (1.0 - ratio))
                        g = int(60 * (1.0 - ratio))
                        b = 255
                    else:
                        r = 30
                        g = 200
                        b = 30
                    color = QColor(r, g, b)
                else:
                    # 균등화된 고리 (ring_range 작음) → 절대 charge 값으로 직접 결정
                    # ionic_bias 적용 후의 charge가 양수/음수임을 반영
                    # 이 분기가 Cp-(RED), tropylium(BLUE), benzene(GREEN)을 정확히 처리
                    color = CloudRenderer.charge_to_color(charge, -1.0, 1.0)
            else:
                # VISUAL_SETTINGS 의존 제거 → McMurry 직접 색상 사용
                # charge < 0: 전자풍부 → RED bias, charge > 0: 전자부족 → BLUE bias
                normalized_charge = max(-1.0, min(1.0, charge / max(charge_range, 0.05)))
                mix = pow(abs(normalized_charge), 0.6) * 2.0 * reactivity_weight
                mix = min(mix, 0.98)
                if charge < 0:
                    target = QColor(255, 30, 30)    # RED (전자 풍부)
                elif charge > 0:
                    target = QColor(30, 30, 255)    # BLUE (전자 부족)
                else:
                    target = QColor(30, 200, 30)    # GREEN (중성)
                base = QColor(30, 200, 30)          # GREEN 베이스
                color = CloudRenderer._blend(base, target, mix)

            base_layer_alpha = base_alpha * min(
                max(strength, charge_intensity * 1.1), 1.5,
            )
            if is_ring_carbon:
                base_layer_alpha *= 1.5
            alpha = int(base_layer_alpha)
            return color, alpha

        # 기본: 전하 기반
        color = CloudRenderer.charge_to_color(charge, min_charge, max_charge)
        alpha = int(base_alpha * min(charge_intensity, 1.5))
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

        if theory_map is None:
            theory_map = {}

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
                halo_radius = avg_radius * 1.35

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
    # 조준선 렌더링  (v3.2)
    # ==================================================================
    @staticmethod
    def draw_crosshairs_v32(painter, results):
        if not results:
            return

        crosshair_data = results.get("crosshairs_v32", [])
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
        if not results:
            return
        stereo_data = results.get("stereo", {})
        if not stereo_data:
            return

        painter.save()
        painter.setPen(QColor("#FF0000"))
        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        for pt_key, label in stereo_data.items():
            pos = QPointF(*pt_key)
            painter.drawText(pos + QPointF(6, -6), label)
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
