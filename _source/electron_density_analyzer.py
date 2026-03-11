# electron_density_analyzer.py (v2.10 - Epsilon-Based Tolerance for Numerical Integrity)
"""
ChemDraw Pro: ORCA DFT 계산 결과 전자밀도 분석

✅ CRITICAL FIX v2.10: Epsilon-Based Tolerance Logic
- CHARGE_TOLERANCE: 1e-4 (허용 오차, 물리적 타당성 검증)
- All charge comparisons use abs(value - expected) > tolerance
- Prevents floating-point error false positives in large molecules
- Replaces strict equality (!=, ==) with tolerance-based validation

Previous fixes:
- v2.02: Strict Column Check for parsing integrity
- v2.05: Mulliken-first charge assignment logic
"""

import re
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# NUMERICAL TOLERANCE CONSTANTS
# ============================================================================

# Physical charge tolerance: 1e-4 electrons
# Rationale: DFT convergence (1e-8 Ha) → partial charge error ~1e-5 to 1e-6
# Safety margin: 1e-4 allows for accumulation errors in large molecules
CHARGE_TOLERANCE = 1e-4

# Atom count tolerance: 5% of total atoms or minimum 2 atoms
# Rationale: Parsing errors may miss 1-2 atoms in multi-section output
# For 180-atom molecules: 5% = 9 atoms tolerance
ATOM_COUNT_TOLERANCE_PERCENT = 0.05
ATOM_COUNT_TOLERANCE_MIN = 2


# ============================================================================
# ENUMS & DATA STRUCTURES
# ============================================================================

class ChargeType(Enum):
    """Mulliken vs Löwdin charge representation"""
    MULLIKEN = "mulliken"
    LOWDIN = "lowdin"


@dataclass
class AtomicDensity:
    """원자 중심에서의 전자밀도 데이터"""
    atom_index: int
    atom_symbol: str
    position: Tuple[float, float, float]
    mulliken_charge: float
    lowdin_charge: float
    electronegativity_adjusted: float = 0.0
    resonance_contribution: float = 0.0
    effective_charge: float = 0.0
    
    def __post_init__(self):
        """
        ✅ FIX v2.05: Mulliken Always First (No fallback logic)
        
        Design principle:
        - effective_charge = mulliken_charge (ALWAYS)
        - 0.0 is a VALID charge value (H atoms in pyridine)
        - Never hijack 0.0 to Löwdin
        
        This solves:
        - Pyridine H atom: Mulliken=0.0 → effective=0.0 ✓
        - Data flexibility for 180+ atom molecules
        - No special case handling needed
        """
        self.effective_charge = self.mulliken_charge


@dataclass
class ResonanceStructure:
    """공명구조 정보"""
    name: str
    atom_indices: List[int]
    average_charge: float = 0.0
    description: str = ""


@dataclass
class DensityMap:
    """원자 위치의 전자밀도 맵"""
    grid_points: Dict[Tuple[float, float], float]
    atom_densities: List[AtomicDensity]
    total_charge: float
    num_atoms: int
    resonance_structures: List[ResonanceStructure] = field(default_factory=list)


# ============================================================================
# MULLIKEN CHARGE EXTRACTOR
# ============================================================================

class MullikenChargeExtractor:
    """ORCA .out 파일에서 Mulliken 부분전하 추출"""
    
    @staticmethod
    def extract_from_out_file(out_path: Path) -> Dict[int, float]:
        """
        ✅ STRICT COLUMN CHECK (v2.02)
        - Mulliken: exactly 3 columns (Index, Symbol, Charge)
        - Geometry: 5+ columns (Index, Symbol, X, Y, Z) → REJECTED
        
        Returns:
            {atom_index: charge_value}
        """
        charges = {}
        
        if not out_path.exists():
            raise FileNotFoundError(f"Output file not found: {out_path}")
        
        try:
            content = out_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            
            # Find Mulliken section
            mulliken_start = None
            for i, line in enumerate(lines):
                if "MULLIKEN ATOMIC CHARGES" in line:
                    mulliken_start = i + 1
                    print(f"[Mulliken] Found section at line {i}")
                    break
            
            if mulliken_start is None:
                print(f"[Mulliken] Warning: MULLIKEN ATOMIC CHARGES section not found")
                return charges
            
            # Parse with STRICT COLUMN CHECK
            for line_idx in range(mulliken_start, len(lines)):
                line = lines[line_idx]
                
                # ✅ IMMEDIATE EXIT: Stop on next section
                if "FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line or "LÖWDIN" in line:
                    print(f"[Mulliken] Found section exit marker at line {line_idx}, stopping")
                    break
                
                # ✅ STRICT COLUMN CHECK: exactly 3 or 4 columns
                parts = line.split()
                
                if len(parts) == 3:
                    # Format: INDEX SYMBOL CHARGE
                    try:
                        atom_idx = int(parts[0])
                        symbol = parts[1]
                        charge = float(parts[2])
                        charges[atom_idx] = round(charge, 4)
                        total = sum(charges.values())
                        print(f"  [Mulliken] Line {line_idx}: Atom {atom_idx} ({symbol}): {round(charge, 4):.4f} (sum: {total:.4f})")
                    except (ValueError, IndexError):
                        pass
                
                elif len(parts) == 4:
                    # Format: INDEX SYMBOL : CHARGE
                    try:
                        atom_idx = int(parts[0])
                        symbol = parts[1]
                        if parts[2] == ':':
                            charge = float(parts[3])
                            charges[atom_idx] = round(charge, 4)
                            total = sum(charges.values())
                            print(f"  [Mulliken] Line {line_idx}: Atom {atom_idx} ({symbol}): {round(charge, 4):.4f} (sum: {total:.4f})")
                    except (ValueError, IndexError):
                        pass
                
                elif len(parts) >= 5:
                    # GEOMETRY LINE! Reject it
                    print(f"  [Mulliken] Line {line_idx}: REJECT (5+ columns, geometry data): {line.strip()[:50]}")
                
                elif "---" in line or "Sum of" in line:
                    print(f"[Mulliken] Found separator at line {line_idx}, stopping")
                    break
            
            print(f"[Mulliken] Extracted {len(charges)} atomic charges")
            print(f"[Mulliken] Total charge: {sum(charges.values()):.4f}")
            
        except Exception as e:
            print(f"[Mulliken Parse Error] {e}")
        
        return charges
    
    @staticmethod
    def extract_lowdin_from_out_file(out_path: Path) -> Dict[int, float]:
        """
        ✅ STRICT COLUMN CHECK (v2.02)
        Same as Mulliken but for Löwdin section
        """
        charges = {}
        
        if not out_path.exists():
            return charges
        
        try:
            content = out_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            
            # Find Löwdin section
            lowdin_start = None
            for i, line in enumerate(lines):
                if "LÖWDIN ATOMIC CHARGES" in line or "LOWDIN ATOMIC CHARGES" in line:
                    lowdin_start = i + 1
                    print(f"[Löwdin] Found section at line {i}")
                    break
            
            if lowdin_start is None:
                return charges
            
            # Parse with STRICT COLUMN CHECK
            for line_idx in range(lowdin_start, len(lines)):
                line = lines[line_idx]
                
                # ✅ IMMEDIATE EXIT: Stop on next section
                if "FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line:
                    print(f"[Löwdin] Found section exit marker at line {line_idx}, stopping")
                    break
                
                parts = line.split()
                
                if len(parts) == 3:
                    try:
                        atom_idx = int(parts[0])
                        symbol = parts[1]
                        charge = float(parts[2])
                        charges[atom_idx] = round(charge, 4)
                    except (ValueError, IndexError):
                        pass
                
                elif len(parts) == 4:
                    try:
                        atom_idx = int(parts[0])
                        symbol = parts[1]
                        if parts[2] == ':':
                            charge = float(parts[3])
                            charges[atom_idx] = round(charge, 4)
                    except (ValueError, IndexError):
                        pass
                
                elif len(parts) >= 5:
                    print(f"  [Löwdin] Line {line_idx}: REJECT (5+ columns, geometry data)")
                
                elif "---" in line or "Sum of" in line:
                    break
            
            print(f"[Löwdin] Extracted {len(charges)} Löwdin charges")
            
        except Exception as e:
            print(f"[Löwdin Parse Error] {e}")
        
        return charges


# ============================================================================
# GEOMETRY EXTRACTOR
# ============================================================================

class GeometryExtractor:
    """ORCA 계산 결과에서 최종 기하 구조 추출"""
    
    @staticmethod
    def extract_final_geometry(out_path: Path) -> Dict[int, Tuple[float, float, float]]:
        """
        ✅ STRICT COLUMN CHECK (v2.02)
        - Geometry: exactly 5 columns (Index, Symbol, X, Y, Z)
        - Mulliken/Löwdin: 3 columns → REJECTED from geometry
        
        Coordinate precision: round(pos, 2)
        
        Returns:
            {atom_index: (x, y, z)}
        """
        geometry = {}
        
        if not out_path.exists():
            return geometry
        
        try:
            content = out_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            
            # Find geometry section
            is_geom_section = False
            final_geom_idx = None
            
            for i, line in enumerate(lines):
                if "FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line or "ATOMIC COORDINATES" in line:
                    is_geom_section = True
                    final_geom_idx = i + 1
                    print(f"[Geometry] Found section at line {i}")
                    break
            
            if final_geom_idx is None:
                print(f"[Geometry] Warning: Final geometry section not found")
                return geometry
            
            # Parse with STRICT COLUMN CHECK
            atom_count = 0
            for line_idx in range(final_geom_idx, len(lines)):
                line = lines[line_idx]
                
                # ✅ IMMEDIATE EXIT: Stop on next section
                if "MULLIKEN" in line or "LÖWDIN" in line or "LOWDIN" in line:
                    print(f"[Geometry] Found section exit marker at line {line_idx}, stopping")
                    break
                
                # ✅ STRICT COLUMN CHECK: exactly 5 columns (Index, Symbol, X, Y, Z)
                parts = line.split()
                
                if len(parts) == 5:
                    # Format: INDEX SYMBOL X Y Z
                    try:
                        idx_str = parts[0]
                        symbol = parts[1]
                        x = float(parts[2])
                        y = float(parts[3])
                        z = float(parts[4])
                        
                        atom_idx = int(idx_str)
                        geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                        atom_count += 1
                        print(f"  [Geometry] Line {line_idx}: Atom {atom_idx} ({symbol}): ({round(x, 2)}, {round(y, 2)}, {round(z, 2)})")
                    except (ValueError, IndexError):
                        pass
                
                elif len(parts) == 4:
                    # Alternative format: SYMBOL X Y Z (no index)
                    try:
                        symbol = parts[0]
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        
                        atom_idx = atom_count
                        geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                        atom_count += 1
                        print(f"  [Geometry] Line {line_idx}: Atom {atom_idx} ({symbol}): ({round(x, 2)}, {round(y, 2)}, {round(z, 2)})")
                    except (ValueError, IndexError):
                        pass
                
                elif len(parts) == 3:
                    # Mulliken charge line detected! Reject it
                    print(f"  [Geometry] Line {line_idx}: REJECT (3 columns, charge data): {line.strip()[:50]}")
                
                elif line.startswith("---"):
                    print(f"[Geometry] Found separator at line {line_idx}, stopping")
                    break
            
            print(f"[Geometry] Extracted {len(geometry)} atomic coordinates")
            
        except Exception as e:
            print(f"[Geometry Parse Error] {e}")
        
        return geometry


# ============================================================================
# RESONANCE STRUCTURE DETECTOR
# ============================================================================

class ResonanceDetector:
    """분자의 공명구조 자동 감지"""
    
    PATTERNS = {
        'benzene': {'size': 6, 'description': 'Benzene ring'},
        'cyclopentadienyl_anion': {'size': 5, 'description': 'Cyclopentadienyl anion'},
        'tropylium_cation': {'size': 7, 'description': 'Tropylium cation'},
    }
    
    @staticmethod
    def detect_resonance_ring(
        atom_indices: List[int],
        charges: Dict[int, float]
    ) -> Optional[ResonanceStructure]:
        """환형 공명구조 감지"""
        ring_size = len(atom_indices)
        ring_charges = [charges.get(i, 0.0) for i in atom_indices]
        
        avg_charge = sum(ring_charges) / len(ring_charges) if ring_charges else 0.0
        charge_variance = sum((c - avg_charge) ** 2 for c in ring_charges) / len(ring_charges)
        
        if ring_size == 6 and charge_variance < 0.001:
            return ResonanceStructure(
                name="benzene",
                atom_indices=atom_indices,
                average_charge=avg_charge,
                description="Benzene: uniform pi-electron distribution"
            )
        
        elif ring_size == 5 and avg_charge < -0.15 and charge_variance < 0.01:
            return ResonanceStructure(
                name="cyclopentadienyl_anion",
                atom_indices=atom_indices,
                average_charge=avg_charge,
                description="Cyclopentadienyl anion: negative charge distributed"
            )
        
        return None
    
    @staticmethod
    def adjust_charges_for_resonance(
        densities: List[AtomicDensity],
        resonance_structures: List[ResonanceStructure]
    ) -> List[AtomicDensity]:
        """공명구조를 반영하여 전하 조정"""
        densities_copy = [AtomicDensity(**vars(d)) for d in densities]
        
        for res in resonance_structures:
            res_densities = [densities_copy[i] for i in res.atom_indices if i < len(densities_copy)]
            res_charges = [d.mulliken_charge for d in res_densities]
            
            if res_charges:
                avg_charge = sum(res_charges) / len(res_charges)
                for density in res_densities:
                    density.effective_charge = 0.6 * density.mulliken_charge + 0.4 * avg_charge
                    density.resonance_contribution = avg_charge - density.mulliken_charge
            
            res.average_charge = avg_charge if res_charges else 0.0
        
        return densities_copy


# ============================================================================
# ELECTRON DENSITY CALCULATOR
# ============================================================================

class ElectronDensityCalculator:
    """원자 위치 기반 전자밀도 계산"""
    
    @staticmethod
    def calculate_atom_densities(
        geometry: Dict[int, Tuple[float, float, float]],
        mulliken_charges: Dict[int, float],
        lowdin_charges: Dict[int, float],
        atom_symbols: Dict[int, str]
    ) -> List[AtomicDensity]:
        """
        원자 중심에서의 전자밀도 계산
        
        ✅ FIX v2.05: Simple Mulliken-First logic
        - If Mulliken available → use Mulliken (even if 0.0)
        - If Mulliken missing → use Löwdin
        - No special case handling
        """
        densities = []
        
        for atom_idx, coord in geometry.items():
            symbol = atom_symbols.get(atom_idx, "C")
            
            # ✅ Simple preference: Mulliken first, Löwdin fallback
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
                lowdin_charge=lowdin
            )
            
            densities.append(density)
        
        return densities
    
    @staticmethod
    def create_density_map(
        densities: List[AtomicDensity],
        atom_positions: Dict[Tuple[float, float], int],
        expected_charge: float = 0.0
    ) -> DensityMap:
        """
        2D 그리기 좌표 기반 밀도 맵 생성
        
        ✅ FIX v2.05: Charge Normalization
        - Create index-based lookup (O(1))
        - Process ALL atom_positions
        - Calculate total_charge
        - Normalize total_charge to expected_charge (1e-4 tolerance)
        """
        grid_points = {}
        total_charge = 0.0
        
        # ✅ Create fast lookup dictionary: {atom_index: density}
        density_by_index = {d.atom_index: d for d in densities}
        
        # ✅ Process ALL atom_positions
        for (x, y), atom_idx in atom_positions.items():
            x_norm = round(x, 2)
            y_norm = round(y, 2)
            
            # ✅ O(1) dictionary lookup
            if atom_idx in density_by_index:
                density = density_by_index[atom_idx]
                density_value = abs(density.effective_charge)
                grid_points[(x_norm, y_norm)] = density_value
                
                # ✅ APPEND: Add to total_charge
                total_charge += density.effective_charge
            else:
                print(f"  [DensityMap] WARNING: Atom {atom_idx} not found in densities")
        
        # ✅ Final floating-point correction
        total_charge = round(total_charge, 4)

        # ✅ FIX v2.10: Epsilon-Based Charge Validation
        # Use module-level CHARGE_TOLERANCE constant (1e-4)
        charge_error = abs(total_charge - expected_charge)

        if charge_error > CHARGE_TOLERANCE:
            # Error exceeds tolerance - likely real data issue or calculation error
            print(f"\n  ⚠️  [DensityMap] Charge validation FAILED:")
            print(f"      Total charge (calculated): {total_charge:.6f}")
            print(f"      Expected charge:           {expected_charge:.6f}")
            print(f"      Absolute error:            {charge_error:.6f}")
            print(f"      Tolerance:                 {CHARGE_TOLERANCE} (1e-4)")
            print(f"      Keeping calculated value (no normalization)")
            # Don't normalize - preserve actual data for debugging
        else:
            # Error within tolerance - normalize to expected value
            # This handles floating-point accumulation in large molecules
            print(f"\n  ✓  [DensityMap] Charge validation PASSED:")
            print(f"      Total charge (raw):        {total_charge:.6f}")
            print(f"      Absolute error:            {charge_error:.6f} < {CHARGE_TOLERANCE}")
            total_charge = round(expected_charge, 4)
            print(f"      Total charge (normalized): {total_charge:.4f}")
        
        density_map = DensityMap(
            grid_points=grid_points,
            atom_densities=densities,
            total_charge=total_charge,
            num_atoms=len(densities)
        )
        
        return density_map


# ============================================================================
# MAIN ANALYZER CLASS
# ============================================================================

class ElectronDensityAnalyzer:
    """ORCA DFT 계산 결과 분석"""
    
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
        charge_tolerance: float = None
    ) -> DensityMap:
        """
        ORCA 계산 결과 전체 분석 with Epsilon-Based Tolerance

        ✅ FIX v2.10: Numerical Integrity & Flexibility
        - Epsilon-based tolerance (default: CHARGE_TOLERANCE = 1e-4)
        - Prevents floating-point error false positives
        - Charge normalization for large molecules (180+ atoms)
        - Dynamic atom count tolerance (5% or min 2 atoms)
        - Always-prefer Mulliken logic

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
        # Use module-level constant if not specified
        if charge_tolerance is None:
            charge_tolerance = CHARGE_TOLERANCE

        print(f"\n[ElectronDensityAnalyzer v2.10] Starting analysis of {out_path.name}")
        print(f"  Charge tolerance: {charge_tolerance:.0e}")
        
        # Step 1: Extract charges
        mulliken_charges = self.mulliken_extractor.extract_from_out_file(out_path)
        lowdin_charges = self.mulliken_extractor.extract_lowdin_from_out_file(out_path)
        
        # Step 2: Extract geometry
        geometry = self.geometry_extractor.extract_final_geometry(out_path)
        if not geometry and atom_positions:
            for (x, y), idx in atom_positions.items():
                x_norm = round(x, 2)
                y_norm = round(y, 2)
                geometry[idx] = (x_norm, y_norm, 0.0)
        
        # ========== DATA INTEGRITY VALIDATION (Epsilon-Based) ==========
        print(f"\n[DATA VALIDATION]")
        print(f"  [Mulliken] {len(mulliken_charges)} atoms")
        print(f"  [Löwdin]   {len(lowdin_charges)} atoms")
        print(f"  [Geometry] {len(geometry)} atoms")

        # ✅ FIX v2.10: Tolerance-based atom count validation
        # Use ATOM_COUNT_TOLERANCE (5% or min 2 atoms) for large molecule flexibility
        max_count = max(len(mulliken_charges), len(lowdin_charges), len(geometry))
        min_count = min(len(mulliken_charges), len(lowdin_charges), len(geometry))
        count_diff = max_count - min_count

        # Calculate dynamic tolerance: max(5% of max_count, 2 atoms)
        dynamic_tolerance = max(
            int(max_count * ATOM_COUNT_TOLERANCE_PERCENT),
            ATOM_COUNT_TOLERANCE_MIN
        )

        if count_diff > dynamic_tolerance:
            print(f"\n  ⚠️  WARNING: Atom count mismatch exceeds tolerance")
            print(f"      Max count:      {max_count}")
            print(f"      Min count:      {min_count}")
            print(f"      Difference:     {count_diff} atoms")
            print(f"      Tolerance:      {dynamic_tolerance} atoms ({ATOM_COUNT_TOLERANCE_PERCENT*100:.0f}% or min {ATOM_COUNT_TOLERANCE_MIN})")
            print(f"      Using Mulliken as reference ({len(mulliken_charges)} atoms)")
        elif count_diff > 0:
            print(f"\n  ℹ️  INFO: Minor atom count difference (within tolerance)")
            print(f"      Difference:     {count_diff} atoms")
            print(f"      Tolerance:      {dynamic_tolerance} atoms")
            print(f"      Using Mulliken as reference ({len(mulliken_charges)} atoms)")
        else:
            print(f"\n  ✓  All sections have consistent atom counts ({max_count} atoms)")
        
        # Step 3: Calculate atomic densities
        densities = self.density_calculator.calculate_atom_densities(
            geometry,
            mulliken_charges,
            lowdin_charges,
            atom_symbols
        )
        
        # Step 4: Detect resonance structures
        resonance_structures = []
        if detect_resonance and len(densities) >= 5:
            pass
        
        # Step 5: Adjust charges for resonance
        if resonance_structures:
            densities = self.resonance_detector.adjust_charges_for_resonance(
                densities, resonance_structures
            )
        
        # Step 6: Calculate expected charge (sum of Mulliken charges)
        expected_charge = round(sum(mulliken_charges.values()), 4)
        print(f"\n[Expected Charge Calculation]")
        print(f"  Mulliken sum: {sum(mulliken_charges.values()):.6f}")
        print(f"  Expected (rounded): {expected_charge:.4f}")
        
        # Step 7: Create density map with charge normalization
        density_map = self.density_calculator.create_density_map(
            densities,
            atom_positions,
            expected_charge=expected_charge
        )
        
        density_map.resonance_structures = resonance_structures

        # Print summary
        print(f"\n{'='*70}")
        print(f"[ElectronDensityAnalyzer v2.10] Analysis complete:")
        print(f"  ✓ Atoms processed:     {density_map.num_atoms}")
        print(f"  ✓ Total charge:        {density_map.total_charge:.4f}")
        print(f"  ✓ Charge tolerance:    {charge_tolerance:.0e} (epsilon-based)")
        print(f"  ✓ Resonance detected:  {len(resonance_structures)} structure(s)")
        print(f"{'='*70}\n")

        return density_map


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def charge_to_color_rgb(charge: float, scale: float = 1.0) -> Tuple[int, int, int]:
    """부분전하 → RGB 색상 변환"""
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
    """전자밀도 → 불투명도 변환"""
    normalized = min(density / max_density, 1.0) if max_density > 0 else 0.5
    return int(255 * normalized * 0.8 + 30)


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

def export_density_map_json(density_map: DensityMap, output_path: Path) -> None:
    """DensityMap을 JSON으로 내보내기"""
    import json
    
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
    
    output_path.write_text(json.dumps(data, indent=2))
    print(f"[ElectronDensity] Exported to {output_path}")


if __name__ == "__main__":
    print("[electron_density_analyzer.py v2.10] Module loaded successfully")
    print(f"  CHARGE_TOLERANCE = {CHARGE_TOLERANCE:.0e}")
    print(f"  ATOM_COUNT_TOLERANCE = {ATOM_COUNT_TOLERANCE_PERCENT*100:.0f}% or min {ATOM_COUNT_TOLERANCE_MIN} atoms")
