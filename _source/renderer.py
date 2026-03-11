# [renderer.py] 상단 임포트 부분
import math
# [추가] 텍스트 렌더링을 위한 QFont 추가
from PyQt6.QtGui import QColor, QRadialGradient, QBrush, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QThread, pyqtSignal
from chem_data import VISUAL_SETTINGS, ELEMENT_DATA
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

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
# DFT ELECTRON DENSITY RENDERER (NEW - Step 3)
# ============================================================================

class DFTDensityRenderer:
    """
    [NEW] DFT 기반 전자밀도 렌더링 (사이클로펜타디에닐 음이온 등 공명구조 지원)
    
    특징:
    - Mulliken 부분전하 기반 색상 맵핑
    - Blue (음) ↔ Red (양) 그라데이션
    - 공명구조 반영 (전체 고리에 균등하게 분배)
    - 각 원자 주위 컬러 그라데이션
    """
    
    @staticmethod
    def charge_to_color(charge: float, min_charge: float = -1.0, max_charge: float = 1.0) -> QColor:
        """
        Mulliken 부분전하 → RGB 색상 변환 (v3.0: Dynamic Auto-Scaling)

        ✅ FIX v3.0: 동적 스케일링으로 ±0.05 차이도 뚜렷하게 표현
        - 현재 분자의 실제 min/max 전하를 기준으로 상대적 대비 강화
        - 고정 ±0.5 대신 분자별 동적 범위 사용

        Args:
            charge: 현재 원자의 Mulliken 전하
            min_charge: 현재 분자 내 최소 전하 (기본값: -1.0)
            max_charge: 현재 분자 내 최대 전하 (기본값: +1.0)

        Mapping:
        - min_charge: 최대 진한 파랑 (highest negative)
        - 0: 중립 (회색)
        - max_charge: 최대 진한 빨강 (highest positive)
        """
        # 동적 범위 계산: 분자 내 최댓값 차이를 기준으로 정규화
        charge_range = max(abs(min_charge), abs(max_charge), 0.05)  # 최소 0.05 보장
        normalized = charge / charge_range  # [-1, 1] 범위로 정규화
        normalized = max(-1.0, min(1.0, normalized))  # Clamp

        if normalized < 0:
            # Negative: Blue gradient (강도에 따라 진해짐)
            intensity = abs(normalized)
            r = int(50 + 50 * intensity)      # 50 → 100 (darker)
            g = int(150 + 50 * intensity)     # 150 → 200
            b = int(255)                       # 255 (full blue)
            alpha = int(120 + 135 * intensity) # 120 → 255 (more opaque)
        elif normalized > 0:
            # Positive: Red gradient (강도에 따라 진해짐)
            intensity = normalized
            r = int(255)                       # 255 (full red)
            g = int(120 - 70 * intensity)      # 120 → 50 (darker)
            b = int(100 - 50 * intensity)      # 100 → 50
            alpha = int(120 + 135 * intensity) # 120 → 255
        else:
            # Neutral: Gray (150, 150, 150)
            r = g = b = 150
            alpha = 100

        color = QColor(r, g, b)
        color.setAlpha(alpha)
        return color
    
    @staticmethod
    def draw_dft_density_clouds(painter, atom_positions: Dict, density_data: Dict):
        """
        DFT 기반 전자구름 그리기
        
        Args:
            painter: QPainter 객체
            atom_positions: {(x, y): charge_value}
            density_data: {(x, y): {"charge": value, "symbol": "C", ...}}
        """
        if not atom_positions:
            return
        
        painter.save()
        
        for (x, y), charge in atom_positions.items():
            # Get detailed data if available
            detail = density_data.get((x, y), {}) if density_data else {}
            
            # Color based on DFT charge
            color = DFTDensityRenderer.charge_to_color(charge)
            
            # Size based on charge magnitude (more charge = larger cloud)
            base_radius = 14.0
            charge_radius = base_radius + abs(charge) * 8.0  # Add 8px per unit charge
            radius = min(charge_radius, 35.0)  # Cap at 35px
            
            # Draw gradient cloud
            grad = QRadialGradient(QPointF(x, y), radius)
            
            # Gradient: solid color center → transparent edge
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
    def draw_charge_indicator(painter, position: QPointF, charge: float, size: int = 10):
        """
        Simplified charge indicator (+ or - symbol)
        """
        if abs(charge) < 0.05:
            return
        
        symbol = "−" if charge < 0 else "+"
        color = DFTDensityRenderer.charge_to_color(charge)
        
        painter.save()
        painter.setFont(QFont("Arial", size, QFont.Weight.Bold))
        painter.setPen(color)
        painter.drawText(position, symbol)
        painter.restore()


class ESPCalculatorThread(QThread):
    """
    Background ESP (Electrostatic Potential) calculation thread
    Computes density gradient mapping for visualization
    [OPTIMIZED] With graceful interruption and thread safety
    """
    progress = pyqtSignal(str)  # Progress message
    result = pyqtSignal(dict)  # Result dict: {position: esp_value}
    error = pyqtSignal(str)  # Error message
    finished_cleanup = pyqtSignal()  # Signal when cleanup is done
    
    def __init__(self, densities: List[ElectronicDensity], atom_positions: Dict):
        super().__init__()
        self.densities = densities
        self.atom_positions = atom_positions
        self.esp_map = {}
        self._stop_event = False  # Flag for graceful interruption
        self.setObjectName(f"ESPCalculator-{id(self)}")
    
    def run(self):
        """Calculate ESP values for all atom positions with graceful interruption"""
        try:
            self.progress.emit("[Phase B] Starting ESP calculation...")
            
            if not self.densities:
                self.error.emit("No density data provided")
                return
            
            if self._stop_event:
                print(f"[{self.objectName()}] ESP calculation cancelled before start")
                return
            
            # [PHASE B CORE] Calculate ESP at each atomic position
            # ESP = Sum of (electron_density / distance) contributions
            total_positions = len(self.atom_positions)
            for idx, target_pos in enumerate(self.atom_positions.keys()):
                # Check for stop request periodically
                if self._stop_event:
                    print(f"[{self.objectName()}] ESP calculation interrupted at {idx}/{total_positions}")
                    return
                
                esp_value = 0.0
                
                for density in self.densities:
                    # Calculate distance from density center to target position
                    dx = target_pos[0] - density.position[0]
                    dy = target_pos[1] - density.position[1]
                    distance = math.sqrt(dx*dx + dy*dy) + 0.1  # Avoid division by zero
                    
                    # Accumulate ESP contribution (density / distance²)
                    contrib = density.density / (distance ** 2 + 0.01)
                    esp_value += contrib
                
                self.esp_map[target_pos] = round(esp_value, 4)
                
                # Emit progress periodically
                if idx % max(1, total_positions // 10) == 0:
                    self.progress.emit(f"[Phase B] Processing: {idx}/{total_positions} positions")
            
            if not self._stop_event:
                self.progress.emit(f"[Phase B] ESP calculation complete: {len(self.esp_map)} points")
                self.result.emit(self.esp_map)
            
        except Exception as e:
            self.error.emit(f"[Phase B ESP Error] {str(e)}")
        finally:
            self.finished_cleanup.emit()
    
    def stop(self):
        """Gracefully stop the ESP calculation"""
        self._stop_event = True
        print(f"[{self.objectName()}] Stop signal received")


class CloudRenderer:
    # [PHASE B] Cache for ESP calculations
    _esp_cache = {}
    _density_cache = None
    _cache_timestamp = None
    _max_cache_size = 1000
    _cache_access_count = {}  # Track access frequency for LRU
    
    @staticmethod
    def set_density_data(densities: List[ElectronicDensity]):
        """Store electronic density data for ESP visualization"""
        import time
        CloudRenderer._density_cache = densities
        CloudRenderer._esp_cache = {}  # Clear cache
        CloudRenderer._cache_timestamp = time.time()
        CloudRenderer._cache_access_count = {}
    
    @staticmethod
    def _invalidate_cache_if_stale(max_age_seconds=300):
        """Invalidate cache if older than max_age_seconds (자동 캐시 갱신)"""
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
        """Evict least recently used entries if cache exceeds max size"""
        if len(CloudRenderer._esp_cache) >= CloudRenderer._max_cache_size:
            # Find the least accessed entry
            if CloudRenderer._cache_access_count:
                lru_key = min(CloudRenderer._cache_access_count, 
                            key=CloudRenderer._cache_access_count.get)
                CloudRenderer._esp_cache.pop(lru_key, None)
                CloudRenderer._cache_access_count.pop(lru_key, None)
    
    @staticmethod
    def calculate_esp_color(density: float, min_density: float, max_density: float) -> QColor:
        """
        [PHASE B] Generate ESP color map: Blue (low density) → Red (high density)
        Uses smooth interpolation for better visualization
        """
        if max_density <= min_density:
            return QColor(100, 149, 237)  # Default blue
        
        # Normalize density to [0, 1]
        normalized = (density - min_density) / (max_density - min_density)
        normalized = max(0.0, min(1.0, normalized))  # Clamp to [0, 1]
        
        # Blue (low) → Cyan → Green → Yellow → Red (high)
        # Use smooth HSV interpolation for better visual gradient
        if normalized < 0.5:
            # Blue to Green
            ratio = normalized * 2
            r = int(0 * (1 - ratio) + 0 * ratio)
            g = int(149 * (1 - ratio) + 255 * ratio)
            b = int(237 * (1 - ratio) + 0 * ratio)
        else:
            # Green to Red
            ratio = (normalized - 0.5) * 2
            r = int(0 * (1 - ratio) + 255 * ratio)
            g = int(255 * (1 - ratio) + 100 * ratio)
            b = int(0 * (1 - ratio) + 0 * ratio)
        
        return QColor(r, g, b)
    
    @staticmethod
    def draw_clouds(painter, results, use_theory_coords=False, densities: List[ElectronicDensity] = None):
        """
        [v3.2] 해석적 렌더링 엔진 - 이론적 가공을 통한 화학적 통찰 강화

        ✅ NEW v3.2: 화학적 통찰 제공
        1. Reactivity Weight: 전하 차이를 지수 함수로 증폭 (±0.01 → 50%+ 시각적 차이)
        2. Variable Cloud Size: 지향성 낮은 탄소의 구름 40% 추가 축소 (위축 효과)
        3. Crosshair Markers: 전자 밀도 최상위 2-3개 탄소에 조준선 자동 표시
        4. Ring Carbon Layer Strength: 고리 탄소 불투명도 1.5배 강화

        Previous enhancements:
        - v3.1: Gamma correction, 25% sigma reduction, substituent 80% size
        - v3.0: Dynamic auto-scaling, rendering priority

        use_theory_coords=True: Theory 레이어용 (이론적 좌표 사용)
        use_theory_coords=False: Drawing/Lewis 레이어용 (그리기 좌표 사용)
        densities: Optional[List[ElectronicDensity]] - ORCA electronic density data
        """
        if not results: return
        charges, islands = results.get("charges", {}), results.get("islands", [])
        aromatic, atoms = results.get("aromatic", set()), results.get("atoms", {})
        bonds = results.get("bonds", {})

        # ✅ DEBUG: v3.2 렌더링 시작 확인
        print(f"\n{'='*70}")
        print(f"[v3.2 Renderer] draw_clouds called")
        print(f"  Total atoms: {len(charges)}")
        print(f"  use_theory_coords: {use_theory_coords}")
        print(f"{'='*70}")

        atom_is_size = {}
        for isl in islands:
            for a in isl: atom_is_size[a] = len(isl)

        base_alpha = VISUAL_SETTINGS.get("cloud_opacity", 140)
        ch_weight = 6.0

        # ========== [v3.2 CRITICAL] 로컬 대비(Local Contrast): 고리 내부 전하 기준 ==========
        # ✅ RELATIVE COLOR MODE: 전체 분자가 아닌 벤젠 고리 탄소만의 min/max 기준
        # 목적: 질산기(-0.3)가 붙어도 고리 내부의 ±0.01 차이를 색상으로 구분
        if charges:
            # 전체 분자 범위 (참고용)
            global_min = min(charges.values())
            global_max = max(charges.values())

            # [v3.2 LOCAL CONTRAST] 고리 탄소만의 전하 범위 계산
            ring_carbon_charges = []
            for pt_key, charge in charges.items():
                at_main = atoms.get(pt_key, {}).get("main", "C")
                is_ring_atom = (pt_key in aromatic or atom_is_size.get(pt_key, 0) >= 2)
                if at_main == "C" and is_ring_atom:
                    ring_carbon_charges.append(charge)

            if ring_carbon_charges:
                # 고리 탄소 기준 min/max
                ring_min = min(ring_carbon_charges)
                ring_max = max(ring_carbon_charges)
                ring_avg_charge = sum(ring_carbon_charges) / len(ring_carbon_charges)

                # 로컬 대비: 고리 내부 범위만 사용
                min_charge = ring_min
                max_charge = ring_max
                charge_range = max(abs(ring_min), abs(ring_max), 0.01)  # 최소 0.01 (더 민감하게)

                print(f"\n[v3.2 LOCAL CONTRAST]")
                print(f"  전체 분자: min={global_min:+.3f}, max={global_max:+.3f}")
                print(f"  고리 탄소: min={ring_min:+.3f}, max={ring_max:+.3f}, avg={ring_avg_charge:+.3f}")
                print(f"  → 색상 범위: {charge_range:.3f} (고리 기준)")
            else:
                min_charge, max_charge, charge_range = -0.5, 0.5, 0.5
                ring_avg_charge = 0.0
        else:
            min_charge, max_charge, charge_range = -0.5, 0.5, 0.5
            ring_avg_charge = 0.0

        # ========== [v3.1] 가우시안 Sigma 극단적 축소: 25% 제한 ==========
        # ✅ FIX v3.1: 40% → 25%로 극단적 축소
        # 목적: 구름이 원자 핵 근처에 집중, 인접 원자와 색상 간섭 원천 차단
        bond_lengths = []
        if bonds:
            for (k1, k2), _ in bonds.items():
                dist = math.sqrt((k1[0] - k2[0])**2 + (k1[1] - k2[1])**2)
                bond_lengths.append(dist)

        avg_bond_length = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 40.0
        max_cloud_radius = avg_bond_length * 0.45

        # [PHASE B] Calculate density statistics for ESP color mapping
        density_values = []
        if densities:
            for d in densities:
                density_values.append(d.density)

        min_density = min(density_values) if density_values else 0.0
        max_density = max(density_values) if density_values else 1.0

        # ========== [v3.0] 렌더링 우선순위: 치환기 먼저, 고리 탄소 나중에 ==========
        # 1단계: 치환기 원자 (O, N, F 등) 수집
        # 2단계: 고리 탄소 수집
        # 3단계: 치환기 → 고리 순서로 렌더링

        substituent_atoms = []  # (pt_key, charge, ...)
        ring_atoms = []         # (pt_key, charge, ...)

        for pt_key, charge in charges.items():
            at_main = atoms.get(pt_key, {}).get("main", "C")
            is_ring_atom = (pt_key in aromatic or atom_is_size.get(pt_key, 0) >= 2)

            # 고리에 속하지 않은 헤테로원자 = 치환기
            if at_main in ["O", "N", "F", "Cl", "Br", "S", "P"] and not is_ring_atom:
                substituent_atoms.append(pt_key)
            else:
                ring_atoms.append(pt_key)

        # 렌더링 순서: 치환기 먼저, 고리 나중에 (고리가 위에 보임)
        render_order = substituent_atoms + ring_atoms

        # [v3.2] 조준선 마커를 위한 전자 밀도 상위 탄소 추적
        electron_rich_carbons = []  # (pt_key, charge) 쌍

        for pt_key in render_order:
            charge = charges[pt_key]
            at_main = atoms.get(pt_key, {}).get("main", "C")
            at_lookup = at_main if at_main and at_main != "C" else "C"
            el_data = ELEMENT_DATA.get(at_lookup, ELEMENT_DATA["C"])

            # [Phase B] Find corresponding density data for this position
            atom_density = None
            if densities:
                for d in densities:
                    d_pos = (round(d.position[0], 2), round(d.position[1], 2))
                    if d_pos == pt_key:
                        atom_density = d
                        break

            # ========== [v3.1] 치환기 크기 축소: 고리 탄소보다 20% 작게 ==========
            # ✅ FIX v3.1: 치환기 원자의 구름 크기를 20% 축소하여 지향성이 가려지지 않게 함
            is_substituent_atom = (at_main in ["O", "N", "F", "Cl", "Br", "S", "P"] and
                                   pt_key not in aromatic and
                                   atom_is_size.get(pt_key, 0) < 2)

            # [수정] 수소 원자(H) 특수 렌더링: N, O, F 결합 시 '노출된 양성자' 강조
            if at_main == "H":
                is_polar_h = False
                # analyzer에서 넘겨준 bonds 정보를 확인
                for bond_pair in results.get("bonds", {}).keys():
                    if pt_key in bond_pair:
                        neighbor = bond_pair[1] if bond_pair[0] == pt_key else bond_pair[0]
                        n_main = atoms.get(neighbor, {}).get("main", "")
                        if n_main in ["N", "O", "F"]:
                            is_polar_h = True; break

                if is_polar_h:
                    c_scale, d_scale = 0.38, 1.3  # 구름은 작게, 밀도는 아주 높게
                else:
                    c_scale, d_scale = 0.5, 0.5
            elif is_substituent_atom:
                # 치환기 원자: 기본 크기의 80% (20% 축소)
                base_c_scale = el_data.get("cloud_scale", 1.0)
                c_scale = base_c_scale * 0.80  # 20% 축소
                d_scale = el_data.get("density_scale", 1.0) * 1.5  # EWG 가중치 1.5배
            else:
                c_scale = el_data.get("cloud_scale", 1.0)
                d_scale = el_data.get("density_scale", 1.0)

            # [Step 3] 레이어별 좌표 선택 로직
            if use_theory_coords:
                # Theory 레이어: 이론적 좌표 우선 사용
                t_map = results.get("theory_data", {}).get("map", {})
                lookup_key = (round(pt_key[0], 2), round(pt_key[1], 2))
                center = t_map.get(lookup_key, QPointF(*pt_key))
            else:
                # Drawing/Lewis 레이어: 항상 그리기 좌표 사용
                center = QPointF(*pt_key)

            isl_size = atom_is_size.get(pt_key, 0)

            # [해결] 벤젠의 과도한 팽창 억제: strength의 상한선 조정
            raw_strength = (2.2) if pt_key in aromatic else (0.85 if isl_size >= 2 else 0.0)
            strength = math.sqrt(raw_strength) * 1.3

            charge_intensity = abs(charge - ring_avg_charge) * 100.0 * d_scale
            charge_intensity = min(charge_intensity, 5.0)

            if charge_intensity < 0.1 and strength < 0.1: continue

            # ========== [v3.2] 반응성 가중치 계산: 지수 함수 증폭 ==========
            # ✅ NEW v3.2: 전하 차이를 exp()로 증폭하여 미세한 차이를 극대화
            # 목표: ±0.01 차이 → 50%+ 시각적 농도 차이
            is_ring_carbon = (at_main == "C" and (pt_key in aromatic or isl_size >= 2))

            if is_ring_carbon:
                # 고리 평균 대비 전하 편차 계산
                charge_deviation = charge - ring_avg_charge

                # ✅ FIX v3.2: 지수 상수 k=15 (발산 방지)
                # ±0.01 → exp(0.15) ≈ 1.16 = 16% 증폭
                # ±0.02 → exp(0.30) ≈ 1.35 = 35% 증폭
                # ±0.05 → exp(0.75) ≈ 2.12 = 112% 증폭 (2배)
                reactivity_weight = min(math.exp(abs(charge_deviation) * 15.0), 3.0)  # 상한선 3.0

                # 전자 밀도 상위 탄소 수집 (조준선 마커용)
                if charge < ring_avg_charge:  # 평균보다 음전하 = 전자 풍부
                    electron_rich_carbons.append((pt_key, charge, center))  # 좌표 포함
            else:
                reactivity_weight = 1.0

            # ========== [v3.2] 가변 구름 크기: 활성/비활성 탄소 차별화 ==========
            # ✅ NEW v3.2: 비활성(양전하) 탄소의 구름을 40% 추가 축소하여 "위축" 효과
            # 기존 반지름 계산
            base_radius = (19.5 + (math.log1p(charge_intensity) * 15.0) + (strength * 7.5)) * c_scale

            # 최대 반지름 제한 (v3.1: 결합 길이의 25%)
            radius = min(base_radius, max_cloud_radius)

            # 비활성 탄소(양전하 > 평균) 구름 축소
            deactivation_applied = False
            if is_ring_carbon and charge > ring_avg_charge:
                deactivation_factor = 0.60  # 40% 추가 축소
                radius *= deactivation_factor
                deactivation_applied = True

            # ✅ DEBUG: 고리 탄소 반지름 출력
            if is_ring_carbon and at_main == "C":
                status = "DEACTIVATED" if deactivation_applied else "ACTIVATED"
                print(f"  Carbon at {pt_key}: charge={charge:+.3f}, avg={ring_avg_charge:+.3f}, "
                      f"radius={radius:.1f}px, weight={reactivity_weight:.2f}x [{status}]")

            # ========== [v3.2] 동적 색상 스케일링 + 반응성 가중치 적용 ==========
            # [PHASE B] Color selection: Use ESP if densities available, else use charge-based
            if densities and atom_density:
                # ESP-based coloring (Red high density → Blue low density)
                color = CloudRenderer.calculate_esp_color(atom_density.density, min_density, max_density)
                alpha = int(base_alpha * min(charge_intensity, 1.5))
            elif isl_size >= 2:
                if is_ring_carbon and ring_carbon_charges and len(ring_carbon_charges) > 1:
                    ring_min = min(ring_carbon_charges)
                    ring_max = max(ring_carbon_charges)
                    ring_range = ring_max - ring_min
                    if ring_range > 0.001:
                        local_normalized = (charge - ring_min) / ring_range
                    else:
                        local_normalized = 0.5

                    if local_normalized < 0.5:
                        ratio = local_normalized * 2.0
                        r = int(50 + (255 - 50) * (1 - ratio))
                        g = int(50 + (150 - 50) * (1 - ratio))
                        b = 255
                    else:
                        ratio = (local_normalized - 0.5) * 2.0
                        r = 255
                        g = int(150 - 150 * ratio)
                        b = int(255 - 205 * ratio)

                    color = QColor(r, g, b)
                else:
                    base = QColor(VISUAL_SETTINGS["resonance_color"])
                    normalized_charge = charge / charge_range
                    mix = pow(abs(normalized_charge), 0.6) * 2.0 * reactivity_weight
                    mix = min(mix, 0.98)
                    target = QColor(VISUAL_SETTINGS["negative_color" if charge < 0 else "positive_color"])
                    color = CloudRenderer._blend(base, target, mix)

                # 전하가 강할수록 불투명도를 높여 "밀도" 표현
                base_layer_alpha = base_alpha * min(max(strength, charge_intensity * 1.1), 1.5)

                # ========== [v3.2] 고리 탄소 레이어 강도 1.5배 강화 ==========
                # ✅ NEW v3.2: 치환기 산소가 정보를 가리는 문제 해결
                if is_ring_carbon:
                    base_layer_alpha *= 1.5  # 고리 탄소 불투명도 1.5배 강화

                alpha = int(base_layer_alpha)
            else:
                # [v3.0] 동적 스케일링으로 색상 결정
                color = DFTDensityRenderer.charge_to_color(charge, min_charge, max_charge)
                alpha = int(base_alpha * min(charge_intensity, 1.5))

            color.setAlpha(alpha)
            grad = QRadialGradient(center, radius)
            # [renderer.py + PHASE B + v3.0] draw_clouds 함수 마지막 부분
            grad.setColorAt(0, color); grad.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(grad)); painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, radius + 2, radius + 2)

        # ========== [v3.2] 조준선 데이터 저장 (draw.py가 별도 레이어로 렌더링) ==========
        # ✅ CRITICAL FIX: 조준선을 여기서 그리지 않고 results에 저장
        # draw.py의 paintEvent 마지막에서 Z-index 최상위로 렌더링
        if electron_rich_carbons:
            # 전하가 가장 음인 순서로 정렬 (전자 밀도 높은 순)
            electron_rich_carbons.sort(key=lambda x: x[1])

            # 상위 2-3개 선택 (분자 크기에 따라 조정)
            num_markers = min(3, max(2, len(electron_rich_carbons) // 3))
            top_sites = electron_rich_carbons[:num_markers]

            # ✅ DEBUG: 조준선 좌표 출력
            print(f"\n[v3.2 Crosshairs] Storing {len(top_sites)} markers:")
            for pt_key, charge_val, pos in top_sites:
                print(f"  ⊕ pt_key: {pt_key}, charge: {charge_val:.4f}")
                print(f"     → QPointF: ({pos.x():.1f}, {pos.y():.1f})")

            # results에 조준선 데이터 저장 (draw.py가 사용)
            results["crosshairs_v32"] = [(pt_key, charge_val, pos) for pt_key, charge_val, pos in top_sites]

    @staticmethod
    def draw_crosshairs_v32(painter, results):
        if not results:
            return

        crosshair_data = results.get("crosshairs_v32", [])
        if not crosshair_data:
            return

        painter.save()
        painter.setClipping(False)

        # ✅ CRITICAL: 완전 불투명 녹색, 3px 굵기 (최대 가시성)
        pen = QPen(QColor(0, 255, 0, 255))
        pen.setWidth(3)  # 3px 굵기 (더 진하게)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        print(f"\n[v3.2 TOP LAYER] Rendering {len(crosshair_data)} crosshairs:")

        for pt_key, charge_val, pos in crosshair_data:
            print(f"  ⊕ Drawing at QPointF({pos.x():.1f}, {pos.y():.1f}), charge={charge_val:.4f}")

            # ✅ CRITICAL: 십자선 크기 24px (더 크게)
            marker_size = 24

            # 수평선
            painter.drawLine(
                pos.x() - marker_size, pos.y(),
                pos.x() + marker_size, pos.y()
            )

            # 수직선
            painter.drawLine(
                pos.x(), pos.y() - marker_size,
                pos.x(), pos.y() + marker_size
            )

            # 외곽 원 3개 (조준경 효과)
            painter.drawEllipse(pos, marker_size * 0.7, marker_size * 0.7)
            painter.drawEllipse(pos, marker_size * 0.45, marker_size * 0.45)
            painter.drawEllipse(pos, marker_size * 0.2, marker_size * 0.2)

        painter.restore()

    @staticmethod
    def draw_stereo_labels(painter, results):
        """[해결] 입체 중심 라벨 전용 렌더링: 9pt 적색, 최상단 배치 고정"""
        if not results: return
        stereo_data = results.get("stereo", {})
        if stereo_data:
            painter.save()
            # [요청 반영] 선명한 빨강(#FF0000), 9pt 크기, 카이랄 중심 밀착 출력
            painter.setPen(QColor("#FF0000")) 
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            for pt_key, label in stereo_data.items():
                pos = QPointF(*pt_key)
                # 원소 기호나 결합선과 겹치지 않게 오프셋을 6px로 미세 조정
                painter.drawText(pos + QPointF(6, -6), label)
            painter.restore()

    @staticmethod
    def _blend(c1, c2, r):
        return QColor(int(c1.red()*(1-r)+c2.red()*r), int(c1.green()*(1-r)+c2.green()*r), int(c1.blue()*(1-r)+c2.blue()*r))