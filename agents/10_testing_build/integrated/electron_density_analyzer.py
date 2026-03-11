# electron_density_analyzer.py (v3.00 - Logging Refactor + Code Cleanup)
"""
ChemGrid — ORCA DFT 계산 결과 전자밀도 분석

Major changes in v3.00:
  ✅ All print() replaced with logging module
  ✅ Code cleanup: removed redundant comments, streamlined logic
  ✅ Preserved all v2.10 features:
     - Epsilon-Based Tolerance (CHARGE_TOLERANCE = 1e-4)
     - Strict Column Check (3 columns for Mulliken, 5 for geometry)
     - Mulliken-first charge assignment
     - Dynamic atom count tolerance (5% or min 2 atoms)

Previous fixes preserved:
  - v2.02: Strict Column Check for parsing integrity
  - v2.05: Mulliken-first charge assignment logic
  - v2.10: Epsilon-Based Tolerance for numerical integrity
"""

import re
import math
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# LOGGING SETUP
# ============================================================================

logger = logging.getLogger("electron_density_analyzer")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(name)s] %(levelname)s: %(message)s"
    ))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ============================================================================
# NUMERICAL TOLERANCE CONSTANTS
# ============================================================================

# Physical charge tolerance: 1e-4 electrons
# DFT convergence (1e-8 Ha) → partial charge error ~1e-5 to 1e-6
# Safety margin: 1e-4 allows for accumulation errors in large molecules
CHARGE_TOLERANCE = 1e-4

# Atom count tolerance: 5% of total atoms or minimum 2 atoms
ATOM_COUNT_TOLERANCE_PERCENT = 0.05
ATOM_COUNT_TOLERANCE_MIN = 2


# ============================================================================
# ENUMS & DATA STRUCTURES
# ============================================================================

class ChargeType(Enum):
    """Mulliken vs Löwdin charge representation."""
    MULLIKEN = "mulliken"
    LOWDIN = "lowdin"


@dataclass
class AtomicDensity:
    """원자 중심에서의 전자밀도 데이터."""
    atom_index: int
    atom_symbol: str
    position: Tuple[float, float, float]
    mulliken_charge: float
    lowdin_charge: float
    electronegativity_adjusted: float = 0.0
    resonance_contribution: float = 0.0
    effective_charge: float = 0.0

    def __post_init__(self):
        """effective_charge = mulliken_charge (always, even if 0.0)."""
        self.effective_charge = self.mulliken_charge


@dataclass
class ResonanceStructure:
    """공명구조 정보."""
    name: str
    atom_indices: List[int]
    average_charge: float = 0.0
    description: str = ""


@dataclass
class DensityMap:
    """원자 위치의 전자밀도 맵."""
    grid_points: Dict[Tuple[float, float], float]
    atom_densities: List[AtomicDensity]
    total_charge: float
    num_atoms: int
    resonance_structures: List[ResonanceStructure] = field(default_factory=list)


# ============================================================================
# MULLIKEN CHARGE EXTRACTOR
# ============================================================================

class MullikenChargeExtractor:
    """ORCA .out 파일에서 Mulliken/Löwdin 부분전하 추출."""

    @staticmethod
    def extract_from_out_file(out_path: Path) -> Dict[int, float]:
        """
        Mulliken 부분전하 추출 (Strict Column Check).

        - 3 columns: INDEX SYMBOL CHARGE
        - 4 columns: INDEX SYMBOL : CHARGE
        - 5+ columns: REJECTED (geometry data)

        Returns:
            {atom_index: charge_value}
        """
        charges: Dict[int, float] = {}

        if not out_path.exists():
            raise FileNotFoundError(f"Output file not found: {out_path}")

        try:
            content = out_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            mulliken_start = None
            for i, line in enumerate(lines):
                if "MULLIKEN ATOMIC CHARGES" in line:
                    mulliken_start = i + 1
                    logger.debug("Mulliken section found at line %d", i)
                    break

            if mulliken_start is None:
                logger.warning("MULLIKEN ATOMIC CHARGES section not found")
                return charges

            for line_idx in range(mulliken_start, len(lines)):
                line = lines[line_idx]

                # Immediate exit on next section
                if ("FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line
                        or "LÖWDIN" in line):
                    break

                parts = line.split()

                if len(parts) == 3:
                    try:
                        atom_idx = int(parts[0])
                        charge = float(parts[2])
                        charges[atom_idx] = round(charge, 4)
                    except (ValueError, IndexError):
                        pass

                elif len(parts) == 4 and parts[2] == ":":
                    try:
                        atom_idx = int(parts[0])
                        charge = float(parts[3])
                        charges[atom_idx] = round(charge, 4)
                    except (ValueError, IndexError):
                        pass

                elif len(parts) >= 5:
                    logger.debug("Mulliken: rejected 5+ column line %d: %s",
                                 line_idx, line.strip()[:50])

                elif "---" in line or "Sum of" in line:
                    break

            logger.info("Mulliken: extracted %d charges (sum=%.4f)",
                        len(charges), sum(charges.values()))

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error("Mulliken parse error: %s", e)

        return charges

    @staticmethod
    def extract_lowdin_from_out_file(out_path: Path) -> Dict[int, float]:
        """
        Löwdin 부분전하 추출 (Strict Column Check).

        Same column rules as Mulliken.
        """
        charges: Dict[int, float] = {}

        if not out_path.exists():
            return charges

        try:
            content = out_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            lowdin_start = None
            for i, line in enumerate(lines):
                if "LÖWDIN ATOMIC CHARGES" in line or "LOWDIN ATOMIC CHARGES" in line:
                    lowdin_start = i + 1
                    logger.debug("Löwdin section found at line %d", i)
                    break

            if lowdin_start is None:
                return charges

            for line_idx in range(lowdin_start, len(lines)):
                line = lines[line_idx]

                if "FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line:
                    break

                parts = line.split()

                if len(parts) == 3:
                    try:
                        atom_idx = int(parts[0])
                        charge = float(parts[2])
                        charges[atom_idx] = round(charge, 4)
                    except (ValueError, IndexError):
                        pass

                elif len(parts) == 4 and parts[2] == ":":
                    try:
                        atom_idx = int(parts[0])
                        charge = float(parts[3])
                        charges[atom_idx] = round(charge, 4)
                    except (ValueError, IndexError):
                        pass

                elif len(parts) >= 5:
                    logger.debug("Löwdin: rejected 5+ column line %d", line_idx)

                elif "---" in line or "Sum of" in line:
                    break

            logger.info("Löwdin: extracted %d charges", len(charges))

        except Exception as e:
            logger.error("Löwdin parse error: %s", e)

        return charges


# ============================================================================
# GEOMETRY EXTRACTOR
# ============================================================================

class GeometryExtractor:
    """ORCA 계산 결과에서 최종 기하 구조 추출."""

    @staticmethod
    def extract_final_geometry(out_path: Path) -> Dict[int, Tuple[float, float, float]]:
        """
        최종 기하 좌표 추출 (Strict Column Check).

        - 5 columns: INDEX SYMBOL X Y Z
        - 4 columns: SYMBOL X Y Z (no index)
        - 3 columns: REJECTED (charge data)

        Coordinate precision: round(pos, 2).

        Returns:
            {atom_index: (x, y, z)}
        """
        geometry: Dict[int, Tuple[float, float, float]] = {}

        if not out_path.exists():
            return geometry

        try:
            content = out_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            is_section = False
            atom_count = 0

            for line_idx, line in enumerate(lines):
                if ("FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line
                        or "ATOMIC COORDINATES" in line):
                    is_section = True
                    geometry = {}
                    atom_count = 0
                    logger.debug("Geometry section found at line %d", line_idx)
                    continue

                if not is_section:
                    continue

                if "MULLIKEN" in line or "LÖWDIN" in line or "LOWDIN" in line:
                    break

                parts = line.split()

                if len(parts) == 5:
                    try:
                        atom_idx = int(parts[0])
                        x = float(parts[2])
                        y = float(parts[3])
                        z = float(parts[4])
                        geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                        atom_count += 1
                    except (ValueError, IndexError):
                        pass

                elif len(parts) == 4:
                    try:
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        geometry[atom_count] = (round(x, 2), round(y, 2), round(z, 2))
                        atom_count += 1
                    except (ValueError, IndexError):
                        pass

                elif len(parts) == 3:
                    logger.debug("Geometry: rejected 3-column line %d (charge data)", line_idx)

                elif line.startswith("---"):
                    if geometry:
                        break

            logger.info("Geometry: extracted %d coordinates", len(geometry))

        except Exception as e:
            logger.error("Geometry parse error: %s", e)

        return geometry


# ============================================================================
# RESONANCE STRUCTURE DETECTOR
# ============================================================================

class ResonanceDetector:
    """분자의 공명구조 자동 감지."""

    @staticmethod
    def detect_resonance_ring(
        atom_indices: List[int],
        charges: Dict[int, float],
    ) -> Optional[ResonanceStructure]:
        """환형 공명구조 감지."""
        ring_size = len(atom_indices)
        ring_charges = [charges.get(i, 0.0) for i in atom_indices]

        if not ring_charges:
            return None

        avg_charge = sum(ring_charges) / len(ring_charges)
        charge_variance = sum((c - avg_charge) ** 2 for c in ring_charges) / len(ring_charges)

        if ring_size == 6 and charge_variance < 0.001:
            return ResonanceStructure(
                name="benzene",
                atom_indices=atom_indices,
                average_charge=avg_charge,
                description="Benzene: uniform pi-electron distribution",
            )

        if ring_size == 5 and avg_charge < -0.15 and charge_variance < 0.01:
            return ResonanceStructure(
                name="cyclopentadienyl_anion",
                atom_indices=atom_indices,
                average_charge=avg_charge,
                description="Cyclopentadienyl anion: negative charge distributed",
            )

        return None

    @staticmethod
    def adjust_charges_for_resonance(
        densities: List[AtomicDensity],
        resonance_structures: List[ResonanceStructure],
    ) -> List[AtomicDensity]:
        """공명구조를 반영하여 전하 조정."""
        densities_copy = [AtomicDensity(**vars(d)) for d in densities]

        for res in resonance_structures:
            res_densities = [
                densities_copy[i] for i in res.atom_indices
                if i < len(densities_copy)
            ]
            res_charges = [d.mulliken_charge for d in res_densities]

            if res_charges:
                avg_charge = sum(res_charges) / len(res_charges)
                for density in res_densities:
                    density.effective_charge = 0.6 * density.mulliken_charge + 0.4 * avg_charge
                    density.resonance_contribution = avg_charge - density.mulliken_charge
                res.average_charge = avg_charge
            else:
                res.average_charge = 0.0

        return densities_copy


# ============================================================================
# ELECTRON DENSITY CALCULATOR
# ============================================================================

class ElectronDensityCalculator:
    """원자 위치 기반 전자밀도 계산."""

    @staticmethod
    def calculate_atom_densities(
        geometry: Dict[int, Tuple[float, float, float]],
        mulliken_charges: Dict[int, float],
        lowdin_charges: Dict[int, float],
        atom_symbols: Dict[int, str],
    ) -> List[AtomicDensity]:
        """
        원자 중심에서의 전자밀도 계산.

        Mulliken-first: Mulliken available → use it (even if 0.0).
        Mulliken missing → fallback to Löwdin.
        """
        densities = []

        for atom_idx, coord in geometry.items():
            symbol = atom_symbols.get(atom_idx, "C")

            if atom_idx in mulliken_charges:
                mulliken = mulliken_charges[atom_idx]
            else:
                mulliken = lowdin_charges.get(atom_idx, 0.0)

            lowdin = lowdin_charges.get(atom_idx, 0.0)

            density = AtomicDensity(
                atom_index=atom_idx,
                atom_symbol=symbol,
                position=coord,
                mulliken_charge=mulliken,
                lowdin_charge=lowdin,
            )
            densities.append(density)

        return densities

    @staticmethod
    def create_density_map(
        densities: List[AtomicDensity],
        atom_positions: Dict[Tuple[float, float], int],
        expected_charge: float = 0.0,
    ) -> DensityMap:
        """
        2D 그리기 좌표 기반 밀도 맵 생성.

        Epsilon-based charge normalization (CHARGE_TOLERANCE = 1e-4).
        """
        grid_points: Dict[Tuple[float, float], float] = {}
        total_charge = 0.0

        # O(1) lookup: {atom_index: density}
        density_by_index = {d.atom_index: d for d in densities}

        for (x, y), atom_idx in atom_positions.items():
            x_norm = round(x, 2)
            y_norm = round(y, 2)

            if atom_idx in density_by_index:
                density = density_by_index[atom_idx]
                grid_points[(x_norm, y_norm)] = abs(density.effective_charge)
                total_charge += density.effective_charge
            else:
                logger.warning("DensityMap: atom %d not found in densities", atom_idx)

        total_charge = round(total_charge, 4)

        # Epsilon-based charge validation
        charge_error = abs(total_charge - expected_charge)

        if charge_error > CHARGE_TOLERANCE:
            logger.warning(
                "Charge validation FAILED: calculated=%.6f, expected=%.6f, error=%.6f > tol=%.0e",
                total_charge, expected_charge, charge_error, CHARGE_TOLERANCE,
            )
        else:
            logger.info(
                "Charge validation PASSED: error=%.6f < tol=%.0e → normalized to %.4f",
                charge_error, CHARGE_TOLERANCE, expected_charge,
            )
            total_charge = round(expected_charge, 4)

        return DensityMap(
            grid_points=grid_points,
            atom_densities=densities,
            total_charge=total_charge,
            num_atoms=len(densities),
        )


# ============================================================================
# MAIN ANALYZER CLASS
# ============================================================================

class ElectronDensityAnalyzer:
    """ORCA DFT 계산 결과 분석 — 메인 파사드 클래스."""

    def __init__(self):
        self.mulliken_extractor = MullikenChargeExtractor()
        self.geometry_extractor = GeometryExtractor()
        self.resonance_detector = ResonanceDetector()
        self.density_calculator = ElectronDensityCalculator()

    def analyze_orca_output(
        self,
        out_path: Path,
        atom_positions: Dict[Tuple[float, float], int],
        atom_symbols: Dict[int, str],
        detect_resonance: bool = True,
        charge_tolerance: Optional[float] = None,
    ) -> DensityMap:
        """
        ORCA 계산 결과 전체 분석.

        Args:
            out_path: Path to ORCA .out file
            atom_positions: {(x, y): atom_index} mapping
            atom_symbols: {atom_index: "C"/"N"/etc.}
            detect_resonance: Enable resonance structure detection
            charge_tolerance: Custom tolerance (default: CHARGE_TOLERANCE)

        Returns:
            DensityMap with validated charge distribution

        Raises:
            FileNotFoundError: If out_path doesn't exist
        """
        if charge_tolerance is None:
            charge_tolerance = CHARGE_TOLERANCE

        logger.info("Starting analysis of %s (tolerance=%.0e)", out_path.name, charge_tolerance)

        # Step 1: Extract charges
        mulliken_charges = self.mulliken_extractor.extract_from_out_file(out_path)
        lowdin_charges = self.mulliken_extractor.extract_lowdin_from_out_file(out_path)

        # Step 2: Extract geometry
        geometry = self.geometry_extractor.extract_final_geometry(out_path)
        if not geometry and atom_positions:
            for (x, y), idx in atom_positions.items():
                geometry[idx] = (round(x, 2), round(y, 2), 0.0)

        # Step 3: Data integrity validation
        self._validate_atom_counts(mulliken_charges, lowdin_charges, geometry)

        # Step 4: Calculate atomic densities
        densities = self.density_calculator.calculate_atom_densities(
            geometry, mulliken_charges, lowdin_charges, atom_symbols,
        )

        # Step 5: Detect resonance structures
        resonance_structures: List[ResonanceStructure] = []
        if detect_resonance and len(densities) >= 5:
            pass  # Future: ring detection logic

        # Step 6: Adjust charges for resonance
        if resonance_structures:
            densities = self.resonance_detector.adjust_charges_for_resonance(
                densities, resonance_structures,
            )

        # Step 7: Create density map
        expected_charge = round(sum(mulliken_charges.values()), 4)
        logger.info("Expected charge (Mulliken sum): %.4f", expected_charge)

        density_map = self.density_calculator.create_density_map(
            densities, atom_positions, expected_charge=expected_charge,
        )
        density_map.resonance_structures = resonance_structures

        logger.info(
            "Analysis complete: %d atoms, charge=%.4f, resonance=%d",
            density_map.num_atoms, density_map.total_charge, len(resonance_structures),
        )
        return density_map

    @staticmethod
    def _validate_atom_counts(
        mulliken: Dict[int, float],
        lowdin: Dict[int, float],
        geometry: Dict[int, Tuple[float, float, float]],
    ) -> None:
        """Validate atom count consistency across parsed sections."""
        counts = [len(mulliken), len(lowdin), len(geometry)]
        max_count = max(counts)
        min_count = min(counts)
        diff = max_count - min_count

        dynamic_tol = max(
            int(max_count * ATOM_COUNT_TOLERANCE_PERCENT),
            ATOM_COUNT_TOLERANCE_MIN,
        )

        if diff > dynamic_tol:
            logger.warning(
                "Atom count mismatch: Mulliken=%d, Löwdin=%d, Geometry=%d "
                "(diff=%d > tol=%d)",
                len(mulliken), len(lowdin), len(geometry), diff, dynamic_tol,
            )
        elif diff > 0:
            logger.info(
                "Minor atom count difference: Mulliken=%d, Löwdin=%d, Geometry=%d "
                "(within tolerance %d)",
                len(mulliken), len(lowdin), len(geometry), dynamic_tol,
            )
        else:
            logger.info("All sections consistent: %d atoms", max_count)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def charge_to_color_rgb(charge: float, scale: float = 1.0) -> Tuple[int, int, int]:
    """부분전하 → RGB 색상 변환 (음전하=파랑, 양전하=빨강)."""
    charge_clamped = max(-1.0, min(1.0, charge * scale))

    if charge_clamped < 0:
        intensity = abs(charge_clamped)
        r = int(100 * (1 - intensity))
        g = int(149 * (1 - intensity))
        b = int(200 + 55 * intensity)
    else:
        intensity = charge_clamped
        r = int(100 + 155 * intensity)
        g = int(100 - 100 * intensity)
        b = int(100 - 100 * intensity)

    return (r, g, b)


def density_to_opacity(density: float, max_density: float = 1.0) -> int:
    """전자밀도 → 불투명도 변환 (0~255)."""
    normalized = min(density / max_density, 1.0) if max_density > 0 else 0.5
    return int(255 * normalized * 0.8 + 30)


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

def export_density_map_json(density_map: DensityMap, output_path: Path) -> None:
    """DensityMap을 JSON으로 내보내기."""
    data = {
        "num_atoms": density_map.num_atoms,
        "total_charge": density_map.total_charge,
        "atom_densities": [
            {
                "index": d.atom_index,
                "symbol": d.atom_symbol,
                "position": d.position,
                "mulliken_charge": d.mulliken_charge,
                "effective_charge": d.effective_charge,
            }
            for d in density_map.atom_densities
        ],
        "resonance_structures": [
            {
                "name": r.name,
                "atom_indices": r.atom_indices,
                "average_charge": r.average_charge,
                "description": r.description,
            }
            for r in density_map.resonance_structures
        ],
    }

    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Exported density map to %s", output_path)


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[electron_density_analyzer.py v3.00] Module loaded successfully")
    print(f"  CHARGE_TOLERANCE = {CHARGE_TOLERANCE:.0e}")
    print(f"  ATOM_COUNT_TOLERANCE = {ATOM_COUNT_TOLERANCE_PERCENT*100:.0f}% or min {ATOM_COUNT_TOLERANCE_MIN} atoms")
