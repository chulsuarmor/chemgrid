# orca_interface.py (v3.00 - Full Refactor: Portable Path + 3-Stage Class Separation)
"""
ChemGrid — ORCA DFT Interface Module

Major changes in v3.00:
  ✅ Portable path system: No hardcoded absolute paths
     - find_orca_executable() auto-detects ORCA from multiple candidate paths
     - Falls back to PATH environment variable
  ✅ 3-stage class separation:
     - OrcaInputGenerator: ORCA input file (.inp) generation
     - OrcaExecutor: ORCA process execution with timeout
     - OrcaOutputParser: .out file state-based parsing (strict column check)
  ✅ Logging: All print() replaced with logging module
  ✅ Error handling: Custom exceptions for ORCA-specific failures
  ✅ Coordinate precision: round(coord, 2) for all data (0.01 unit)

Previous fixes preserved:
  - v2.02: Strict Column Check (3 columns for Mulliken, 5 for geometry)
  - v2.02: Immediate Section Exit on FINAL GEOMETRY / LÖWDIN keywords
"""

import os
import sys
import subprocess
import math
import struct
import re
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

# ============================================================================
# LOGGING SETUP
# ============================================================================

logger = logging.getLogger("orca_interface")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(name)s] %(levelname)s: %(message)s"
    ))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# ============================================================================
# PyQt6 imports - optional for standalone testing
# ============================================================================

try:
    from PyQt6.QtCore import QThread, pyqtSignal, QPointF
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

    class QThread:
        """Stub QThread for non-PyQt6 environments."""
        pass

    class pyqtSignal:
        """Stub pyqtSignal for non-PyQt6 environments."""
        def __init__(self, *args):
            pass
        def emit(self, *args):
            pass

    class QPointF:
        """Stub QPointF for non-PyQt6 environments."""
        def __init__(self, x=0, y=0):
            self.x, self.y = x, y


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class OrcaError(Exception):
    """Base exception for ORCA-related errors."""
    pass


class OrcaNotFoundError(OrcaError):
    """ORCA executable not found on system."""
    pass


class OrcaExecutionError(OrcaError):
    """ORCA process returned non-zero exit code."""
    pass


class OrcaTimeoutError(OrcaError):
    """ORCA calculation exceeded timeout limit."""
    pass


class OrcaConvergenceError(OrcaError):
    """ORCA geometry optimization did not converge."""
    pass


class OrcaParseError(OrcaError):
    """Failed to parse ORCA output file."""
    pass


# ============================================================================
# PORTABLE PATH SYSTEM (C1 + C5 Fix)
# ============================================================================

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))


def find_orca_executable() -> Optional[Path]:
    """
    Portable ORCA executable discovery.

    Searches multiple candidate paths relative to the script location,
    then falls back to the system PATH.

    Search order:
      1. _SCRIPT_DIR / "Orca.6.1.1" / "orca.exe"
      2. _SCRIPT_DIR / "Orca.6.1.1" / "Orca6.1.1.Win64.exe"
      3. _SCRIPT_DIR.parent / "Orca.6.1.1" / "orca.exe"
      4. _SCRIPT_DIR.parent / "Orca.6.1.1" / "Orca6.1.1.Win64.exe"
      5. _SCRIPT_DIR.parent.parent / "Orca.6.1.1" / "orca.exe"
      6. _SCRIPT_DIR.parent.parent / "Orca.6.1.1" / "Orca6.1.1.Win64.exe"
      7. System PATH (shutil.which("orca"))

    Returns:
        Path to ORCA executable, or None if not found.
    """
    exe_names = ["orca.exe", "Orca6.1.1.Win64.exe"]
    search_roots = [
        _SCRIPT_DIR,
        _SCRIPT_DIR.parent,
        _SCRIPT_DIR.parent.parent,
    ]

    for root in search_roots:
        orca_dir = root / "Orca.6.1.1"
        for exe_name in exe_names:
            candidate = orca_dir / exe_name
            if candidate.exists():
                logger.info("ORCA found: %s", candidate)
                return candidate

    # Fallback: search system PATH
    orca_in_path = shutil.which("orca")
    if orca_in_path:
        logger.info("ORCA found in PATH: %s", orca_in_path)
        return Path(orca_in_path)

    logger.warning("ORCA executable not found in any candidate path")
    return None


def get_orca_dir() -> Optional[Path]:
    """
    Get the ORCA installation directory.

    Returns:
        Path to ORCA directory (parent of the executable), or None.
    """
    exe = find_orca_executable()
    if exe is not None:
        return exe.parent
    return None


# Module-level lazy ORCA path (resolved on first use)
_orca_exe_cache: Optional[Path] = None


def _get_orca_exe() -> Path:
    """
    Get cached ORCA executable path. Raises OrcaNotFoundError if not found.
    """
    global _orca_exe_cache
    if _orca_exe_cache is None:
        _orca_exe_cache = find_orca_executable()
    if _orca_exe_cache is None:
        raise OrcaNotFoundError(
            "ORCA executable not found. "
            "Please place Orca.6.1.1/ directory next to this script, "
            "or add ORCA to your system PATH."
        )
    return _orca_exe_cache


# ============================================================================
# CONFIGURATION
# ============================================================================

# DFT Template: B3LYP/6-31G(d)
DFT_TEMPLATE = """\
! B3LYP 6-31G(d) OptAll TIGHTSCF MINIPRINT
%output
  Print[P_Mulliken] 1
  Print[P_LöwdinPop] 1
end

* xyz {charge} {multiplicity}
{atoms_block}
*
"""

# v3.1: Orbital cube file generation template (MOREAD + NOITER to reuse .gbw)
ORBITAL_PLOT_TEMPLATE = """\
! B3LYP 6-31G(d) TIGHTSCF MINIPRINT MOREAD NOITER
%moinp "{gbw_file}"
%plots
  dim1 60
  dim2 60
  dim3 60
  Format Gaussian_Cube
  MO("homo.cube",{homo_idx},0);
  MO("lumo.cube",{lumo_idx},0);
  ElDens("density.cube");
end

* xyz {charge} {multiplicity}
{atoms_block}
*
"""

# Default timeout in seconds (5 minutes)
DEFAULT_TIMEOUT = 300


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class GBWHeader:
    """Binary header info for .gbw files."""
    magic: str
    version: int
    endianness: str
    num_atoms: int
    num_basis_functions: int


@dataclass
class ElectronicDensity:
    """Electronic density data at atomic positions."""
    atom_index: int
    atom_symbol: str
    position: Tuple[float, float, float]
    density: float
    mulliken_charge: float
    lowdin_charge: float


@dataclass
class OrcaCalculationResult:
    """Complete ORCA calculation result."""
    converged: bool = False
    energy: float = 0.0
    geometry: Dict[int, Tuple[float, float, float]] = field(default_factory=dict)
    densities: List[ElectronicDensity] = field(default_factory=list)
    charges_mulliken: Dict[int, float] = field(default_factory=dict)
    charges_lowdin: Dict[int, float] = field(default_factory=dict)
    bond_orders: Dict[Tuple[int, int], float] = field(default_factory=dict)
    computation_time: float = 0.0
    atom_symbols: Dict[int, str] = field(default_factory=dict)


# ============================================================================
# STAGE 1: INPUT GENERATION
# ============================================================================

class OrcaInputGenerator:
    """
    ORCA input file (.inp) generator.

    Converts 2D molecular structure data into ORCA DFT input format.
    Coordinate precision: round(coord, 2) — 0.01 unit.
    """

    def __init__(self, template: str = DFT_TEMPLATE):
        self.template = template

    def generate(
        self,
        atoms: Dict,
        bonds: Dict,
        charge: int = 0,
        multiplicity: int = 1,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Generate ORCA input file from molecular structure.

        Args:
            atoms: {(x,y): {"main": "C", "attach": {...}}}
            bonds: {(k1, k2): bond_order}
            charge: Molecular charge (default 0)
            multiplicity: Spin multiplicity (1=singlet, 2=doublet, ...)
            output_path: Where to write .inp file (default: cwd/orca_input.inp)

        Returns:
            Path to the generated input file.
        """
        if output_path is None:
            output_path = Path.cwd() / "orca_input.inp"

        atoms_block = self._build_atoms_block(atoms)

        content = self.template.format(
            charge=charge,
            multiplicity=multiplicity,
            atoms_block=atoms_block,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        logger.info("Input file generated: %s", output_path)
        return output_path

    @staticmethod
    def _build_atoms_block(atoms: Dict) -> str:
        """Build the XYZ atoms block string."""
        lines = []
        for (x, y), data in atoms.items():
            symbol = data.get("main", "C")
            x_norm = round(float(x), 2)
            y_norm = round(float(y), 2)
            z = 0.0  # 2D drawing → Z = 0
            lines.append(f"{symbol:2s}  {x_norm:10.6f}  {y_norm:10.6f}  {z:10.6f}")
        return "\n".join(lines)


# ============================================================================
# STAGE 2: EXECUTION
# ============================================================================

class OrcaExecutor:
    """
    ORCA process executor.

    Runs the ORCA executable with proper error handling and timeout.
    """

    def __init__(self, orca_exe: Optional[Path] = None, timeout: int = DEFAULT_TIMEOUT):
        """
        Args:
            orca_exe: Path to ORCA executable (auto-detected if None).
            timeout: Maximum execution time in seconds (default 300).
        """
        self._orca_exe = orca_exe
        self.timeout = timeout

    @property
    def orca_exe(self) -> Path:
        if self._orca_exe is None:
            self._orca_exe = _get_orca_exe()
        return self._orca_exe

    def execute(self, input_path: Path, work_dir: Optional[Path] = None) -> Path:
        """
        Execute ORCA calculation.

        Args:
            input_path: Path to .inp file.
            work_dir: Working directory (default: input file's parent).

        Returns:
            Path to the .out output file.

        Raises:
            OrcaNotFoundError: ORCA executable not found.
            OrcaExecutionError: ORCA returned non-zero exit code.
            OrcaTimeoutError: Calculation exceeded timeout.
            FileNotFoundError: Input file does not exist.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if work_dir is None:
            work_dir = input_path.parent

        cmd = [str(self.orca_exe), str(input_path)]
        logger.info("Executing: %s", " ".join(cmd))
        logger.info("Work dir: %s", work_dir)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(work_dir),
            )
        except subprocess.TimeoutExpired:
            raise OrcaTimeoutError(
                f"ORCA calculation timed out (> {self.timeout} seconds)"
            )
        except FileNotFoundError:
            raise OrcaNotFoundError(
                f"ORCA executable not found: {self.orca_exe}"
            )

        if result.returncode != 0:
            raise OrcaExecutionError(
                f"ORCA exited with code {result.returncode}:\n{result.stderr[:2000]}"
            )

        out_path = input_path.with_suffix(".out")
        logger.info("ORCA completed. Output: %s", out_path)
        return out_path


# ============================================================================
# STAGE 3: OUTPUT PARSING
# ============================================================================

class OrcaOutputParser:
    """
    ORCA output (.out) file parser.

    Uses state-based parsing with strict column check (v2.02 logic preserved).
    All coordinate values: round(coord, 2).

    Parsing sections:
      - FINAL GEOMETRY / CARTESIAN COORDINATES → geometry
      - MULLIKEN ATOMIC CHARGES → Mulliken charges (3 or 4 columns only)
      - LÖWDIN ATOMIC CHARGES → Löwdin charges
      - FINAL SINGLE POINT ENERGY → SCF energy
      - MAYER BOND ORDERS → bond orders
      - ATOMIC COORDINATES (ANGSTROM) → atom symbols
    """

    def parse(self, out_path: Path) -> OrcaCalculationResult:
        """
        Parse ORCA .out file into OrcaCalculationResult.

        Args:
            out_path: Path to .out file.

        Returns:
            OrcaCalculationResult with all extracted data.

        Raises:
            FileNotFoundError: Output file not found.
            OrcaParseError: Critical parsing failure.
        """
        if not out_path.exists():
            raise FileNotFoundError(f"Output file not found: {out_path}")

        result = OrcaCalculationResult()

        try:
            with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            raise OrcaParseError(f"Cannot read output file: {e}")

        logger.info("Parsing %s (%d lines)", out_path.name, len(lines))

        # Extract each section
        result.geometry = self._parse_geometry(lines)
        result.charges_mulliken = self._parse_mulliken(lines)
        result.charges_lowdin = self._parse_lowdin(lines)
        result.energy = self._parse_energy(lines)
        result.converged = self._parse_convergence(lines)
        result.bond_orders = self._parse_bond_orders(lines)
        result.atom_symbols = self._parse_atom_symbols(lines)

        # Build density entries
        result.densities = self._build_densities(
            result.geometry,
            result.charges_mulliken,
            result.charges_lowdin,
            result.atom_symbols,
        )

        # Validation summary
        total_mulliken = sum(result.charges_mulliken.values())
        total_lowdin = sum(result.charges_lowdin.values())

        logger.info("Parsing complete:")
        logger.info("  Converged:        %s", result.converged)
        logger.info("  Energy:           %.6f", result.energy)
        logger.info("  Geometry atoms:   %d", len(result.geometry))
        logger.info("  Mulliken charges: %d (sum=%.4f)", len(result.charges_mulliken), total_mulliken)
        logger.info("  Löwdin charges:   %d (sum=%.4f)", len(result.charges_lowdin), total_lowdin)
        logger.info("  Bond orders:      %d", len(result.bond_orders))

        if len(result.charges_mulliken) > 0 and len(result.geometry) > 0:
            if len(result.charges_mulliken) != len(result.geometry):
                logger.warning(
                    "Atom count mismatch: Mulliken=%d, Geometry=%d",
                    len(result.charges_mulliken),
                    len(result.geometry),
                )

        return result

    # ------------------------------------------------------------------
    # Geometry parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_geometry(lines: List[str]) -> Dict[int, Tuple[float, float, float]]:
        """
        Extract final geometry coordinates.

        Strict column check: 5+ columns (Index Symbol X Y Z).
        Also handles 4-column format (Symbol X Y Z, no index).
        """
        geometry: Dict[int, Tuple[float, float, float]] = {}
        is_section = False

        for line in lines:
            # Section entry
            if "FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line:
                is_section = True
                geometry = {}  # Reset — use last occurrence
                continue

            if not is_section:
                continue

            # Section exit
            if "MULLIKEN" in line or "LÖWDIN" in line or "LOWDIN" in line:
                break

            stripped = line.strip()
            if stripped == "" or stripped.startswith("---"):
                if geometry:  # Only exit if we already have data
                    break
                continue

            parts = stripped.split()

            # 5-column format: INDEX SYMBOL X Y Z
            if len(parts) >= 5:
                try:
                    atom_idx = int(parts[0])
                    x = float(parts[2])
                    y = float(parts[3])
                    z = float(parts[4])
                    geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                except (ValueError, IndexError):
                    # Try without index: SYMBOL X Y Z (+ extra columns)
                    try:
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        atom_idx = len(geometry)
                        geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                    except (ValueError, IndexError):
                        pass

            # 4-column format: SYMBOL X Y Z
            elif len(parts) == 4:
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    atom_idx = len(geometry)
                    geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                except (ValueError, IndexError):
                    pass

        logger.debug("Geometry: extracted %d atoms", len(geometry))
        return geometry

    # ------------------------------------------------------------------
    # Mulliken charge parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_mulliken(lines: List[str]) -> Dict[int, float]:
        """
        Extract Mulliken atomic charges.

        Strict column check: exactly 3 columns (Index Symbol Charge)
        or 4 columns (Index Symbol : Charge). 5+ columns → REJECTED.
        """
        charges: Dict[int, float] = {}
        is_section = False

        for line in lines:
            if "MULLIKEN ATOMIC CHARGES" in line:
                is_section = True
                charges = {}  # Reset — use last occurrence
                continue

            if not is_section:
                continue

            # Immediate exit on next section
            if ("FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line
                    or "LÖWDIN" in line or "LOWDIN" in line):
                break

            stripped = line.strip()
            if stripped.startswith("---") or "Sum of" in stripped:
                break

            parts = stripped.split()

            if len(parts) == 3:
                # INDEX SYMBOL CHARGE
                try:
                    atom_idx = int(parts[0])
                    charge = float(parts[2])
                    charges[atom_idx] = round(charge, 4)
                except (ValueError, IndexError):
                    pass

            elif len(parts) == 4 and parts[2] == ":":
                # INDEX SYMBOL : CHARGE
                try:
                    atom_idx = int(parts[0])
                    charge = float(parts[3])
                    charges[atom_idx] = round(charge, 4)
                except (ValueError, IndexError):
                    pass

            elif len(parts) >= 5:
                # Geometry data leaked into Mulliken → reject
                logger.debug("Mulliken: rejected 5+ column line: %s", stripped[:60])

        logger.debug("Mulliken: extracted %d charges", len(charges))
        return charges

    # ------------------------------------------------------------------
    # Löwdin charge parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_lowdin(lines: List[str]) -> Dict[int, float]:
        """
        Extract Löwdin atomic charges.

        Same strict column check as Mulliken.
        """
        charges: Dict[int, float] = {}
        is_section = False

        for line in lines:
            if "LÖWDIN ATOMIC CHARGES" in line or "LOWDIN ATOMIC CHARGES" in line:
                is_section = True
                charges = {}
                continue

            if not is_section:
                continue

            # Immediate exit
            if "FINAL GEOMETRY" in line or "CARTESIAN COORDINATES" in line:
                break

            stripped = line.strip()
            if stripped.startswith("---") or "Sum of" in stripped:
                break

            parts = stripped.split()

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
                logger.debug("Löwdin: rejected 5+ column line: %s", stripped[:60])

        logger.debug("Löwdin: extracted %d charges", len(charges))
        return charges

    # ------------------------------------------------------------------
    # Energy parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_energy(lines: List[str]) -> float:
        """Extract final single point energy (Hartree)."""
        energy = 0.0
        for line in lines:
            if "FINAL SINGLE POINT ENERGY" in line:
                match = re.search(r"([-+]?\d+\.?\d*)", line)
                if match:
                    energy = float(match.group(1))
        return energy

    # ------------------------------------------------------------------
    # Convergence check
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_convergence(lines: List[str]) -> bool:
        """Check if calculation converged."""
        for line in lines:
            if "THE OPTIMIZATION HAS CONVERGED" in line or "ORCA finished" in line:
                return True
        return False

    # ------------------------------------------------------------------
    # Bond order parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_bond_orders(lines: List[str]) -> Dict[Tuple[int, int], float]:
        """Extract Mayer bond orders."""
        bond_orders: Dict[Tuple[int, int], float] = {}
        is_section = False

        for line in lines:
            if "MAYER BOND ORDERS" in line:
                is_section = True
                continue

            if not is_section:
                continue

            if "Total bond order" in line or line.strip() == "":
                if bond_orders:
                    break
                continue

            parts = line.split()
            if len(parts) >= 3:
                try:
                    i = int(parts[0])
                    j = int(parts[1])
                    order = float(parts[2])
                    bond_orders[(min(i, j), max(i, j))] = round(order, 2)
                except (ValueError, IndexError):
                    continue

        logger.debug("Bond orders: extracted %d entries", len(bond_orders))
        return bond_orders

    # ------------------------------------------------------------------
    # Atom symbol extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_atom_symbols(lines: List[str]) -> Dict[int, str]:
        """
        Extract atom symbols from ATOMIC COORDINATES section.

        Returns:
            {atom_index: symbol} e.g. {0: "C", 1: "H", ...}
        """
        symbols: Dict[int, str] = {}
        is_section = False

        for line in lines:
            if "ATOMIC COORDINATES" in line and "ANGSTROM" in line:
                is_section = True
                symbols = {}
                continue

            if not is_section:
                continue

            parts = line.split()
            if len(parts) >= 4:
                try:
                    idx = int(parts[0])
                    symbol = parts[1]
                    float(parts[2])  # Validate it's a number
                    symbols[idx] = symbol
                except (ValueError, IndexError):
                    if symbols:
                        break

        logger.debug("Atom symbols: extracted %d", len(symbols))
        return symbols

    # ------------------------------------------------------------------
    # Build density entries
    # ------------------------------------------------------------------
    @staticmethod
    def _build_densities(
        geometry: Dict[int, Tuple[float, float, float]],
        charges_mulliken: Dict[int, float],
        charges_lowdin: Dict[int, float],
        atom_symbols: Dict[int, str],
    ) -> List[ElectronicDensity]:
        """Build ElectronicDensity list from parsed data."""
        densities = []
        for atom_idx, (x, y, z) in geometry.items():
            symbol = atom_symbols.get(atom_idx, "C")
            entry = ElectronicDensity(
                atom_index=atom_idx,
                atom_symbol=symbol,
                position=(x, y, z),
                density=0.0,
                mulliken_charge=charges_mulliken.get(atom_idx, 0.0),
                lowdin_charge=charges_lowdin.get(atom_idx, 0.0),
            )
            densities.append(entry)
        return densities


# ============================================================================
# ORCA CALCULATOR THREAD (QThread) — Combines all 3 stages
# ============================================================================

class OrcaCalculatorThread(QThread):
    """
    Background DFT calculation worker thread.

    Combines OrcaInputGenerator + OrcaExecutor + OrcaOutputParser
    into a single QThread for non-blocking UI integration.

    Signals:
        progress(str): Progress status messages
        result(OrcaCalculationResult): Final calculation result
        error(str): Error messages
    """

    if PYQT_AVAILABLE:
        progress = pyqtSignal(str)
        result = pyqtSignal(object)  # OrcaCalculationResult
        error = pyqtSignal(str)
    else:
        progress = pyqtSignal(str)
        result = pyqtSignal(object)
        error = pyqtSignal(str)

    def __init__(self, input_file: Path, work_dir: Path, timeout: int = DEFAULT_TIMEOUT):
        if PYQT_AVAILABLE:
            super().__init__()
        self.input_file = input_file
        self.work_dir = work_dir
        self.timeout = timeout
        self.result_data: Optional[OrcaCalculationResult] = None

    def run(self):
        """Execute ORCA calculation in background thread."""
        try:
            self.progress.emit(f"Starting ORCA calculation: {self.input_file.name}")

            # Stage 2: Execute
            executor = OrcaExecutor(timeout=self.timeout)
            out_path = executor.execute(self.input_file, self.work_dir)

            self.progress.emit("ORCA calculation completed, parsing results...")

            # Stage 3: Parse
            parser = OrcaOutputParser()
            calc_result = parser.parse(out_path)
            self.result_data = calc_result

            self.result.emit(calc_result)
            self.progress.emit("Results parsed successfully")

        except OrcaNotFoundError as e:
            self.error.emit(f"ORCA not found: {e}")
        except OrcaTimeoutError as e:
            self.error.emit(f"Timeout: {e}")
        except OrcaExecutionError as e:
            self.error.emit(f"Execution failed: {e}")
        except OrcaParseError as e:
            self.error.emit(f"Parse error: {e}")
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")
            logger.exception("Unexpected error in OrcaCalculatorThread")


# ============================================================================
# CONVENIENCE FUNCTIONS (backward-compatible API)
# ============================================================================

def generate_orca_input(
    atoms: Dict,
    bonds: Dict,
    charge: int = 0,
    multiplicity: int = 1,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Generate ORCA input file (backward-compatible wrapper).

    See OrcaInputGenerator.generate() for details.
    """
    generator = OrcaInputGenerator()
    return generator.generate(atoms, bonds, charge, multiplicity, output_path)


def create_calculation_workflow(
    atoms: Dict,
    bonds: Dict,
    work_dir: Optional[Path] = None,
    charge: int = 0,
    multiplicity: int = 1,
) -> Tuple[Path, OrcaCalculatorThread]:
    """
    Create complete calculation workflow (backward-compatible wrapper).

    Returns:
        (input_file_path, calculator_thread)
    """
    if work_dir is None:
        work_dir = Path.cwd() / "orca_calcs"
    work_dir.mkdir(parents=True, exist_ok=True)

    input_file = generate_orca_input(atoms, bonds, charge, multiplicity, work_dir / "input.inp")
    calculator = OrcaCalculatorThread(input_file, work_dir)
    return input_file, calculator


def parse_gbw_file(gbw_path: Path, out_path: Optional[Path] = None) -> OrcaCalculationResult:
    """
    Parse ORCA results (backward-compatible wrapper).

    Primarily parses the .out file; .gbw binary parsing is minimal.
    """
    if not gbw_path.exists():
        raise FileNotFoundError(f"GBW file not found: {gbw_path}")

    if out_path and out_path.exists():
        parser = OrcaOutputParser()
        return parser.parse(out_path)

    # Minimal .gbw parsing (header only)
    result = OrcaCalculationResult()
    try:
        with open(gbw_path, "rb") as f:
            f.read(4)  # magic
            struct.unpack(">i", f.read(4))  # version
    except Exception as e:
        logger.warning("GBW parse error: %s", e)

    return result


def extract_atom_symbols(out_path: Path) -> Dict[int, str]:
    """
    Extract atom symbols from ORCA output (backward-compatible wrapper).

    Returns:
        {atom_index: symbol}
    """
    if not out_path.exists():
        return {}

    try:
        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return OrcaOutputParser._parse_atom_symbols(lines)
    except Exception as e:
        logger.warning("Atom symbol extraction failed: %s", e)
        return {}


def validate_orca_installation() -> bool:
    """
    Check if ORCA is properly installed (portable version).

    Returns:
        True if ORCA executable is found, False otherwise.
    """
    exe = find_orca_executable()
    if exe is None:
        logger.error("ORCA installation not found")
        return False
    logger.info("ORCA installation verified: %s", exe)
    return True


def generate_orbital_cubes(
    out_path: Path,
    work_dir: Path = None,
) -> Dict[str, Path]:
    """
    Generate orbital cube files from a completed ORCA calculation.
    Uses MOREAD + NOITER to read existing .gbw and generate cube files via %plots.

    Args:
        out_path: Path to ORCA .out file from completed calculation
        work_dir: Working directory (defaults to out_path's directory)

    Returns:
        Dict of cube file paths: {"homo": Path, "lumo": Path, "density": Path}
    """
    if work_dir is None:
        work_dir = out_path.parent

    gbw_path = out_path.with_suffix('.gbw')
    if not gbw_path.exists():
        logger.warning("GBW file not found: %s", gbw_path)
        return {}

    # Parse HOMO/LUMO indices from .out file
    homo_idx, lumo_idx = _find_homo_lumo_indices(out_path)

    # Extract geometry and charge from .out
    atoms_block, charge, multiplicity = _extract_geometry_block(out_path)
    if not atoms_block:
        logger.warning("Failed to extract geometry from .out file")
        return {}

    # Generate plot input file
    plot_input = ORBITAL_PLOT_TEMPLATE.format(
        gbw_file=gbw_path.name,
        homo_idx=homo_idx,
        lumo_idx=lumo_idx,
        charge=charge,
        multiplicity=multiplicity,
        atoms_block=atoms_block,
    )

    plot_input_path = work_dir / "orbital_plot.inp"
    plot_input_path.write_text(plot_input)

    logger.info("Running ORCA for cube generation (HOMO=%d, LUMO=%d)...", homo_idx, lumo_idx)

    try:
        orca_exe = _get_orca_exe()
        result = subprocess.run(
            [str(orca_exe), str(plot_input_path)],
            capture_output=True, text=True,
            timeout=120,
            cwd=str(work_dir),
        )
        if result.returncode != 0:
            logger.warning("ORCA plot failed: %s", result.stderr[:200])
            return {}
    except subprocess.TimeoutExpired:
        logger.warning("ORCA plot timed out")
        return {}
    except OrcaNotFoundError:
        logger.warning("ORCA not found, cannot generate cube files")
        return {}
    except Exception as e:
        logger.warning("Cube generation error: %s", e)
        return {}

    # Collect generated cube files
    cube_files = {}
    for name, filename in [("homo", "homo.cube"), ("lumo", "lumo.cube"), ("density", "density.cube")]:
        cube_path = work_dir / filename
        if cube_path.exists():
            cube_files[name] = cube_path
            logger.info("Generated: %s (%d bytes)", filename, cube_path.stat().st_size)
        else:
            logger.info("Missing: %s", filename)

    return cube_files


def _find_homo_lumo_indices(out_path: Path) -> Tuple[int, int]:
    """Find HOMO and LUMO orbital indices from ORCA output."""
    homo_idx = 0
    lumo_idx = 1

    try:
        content = out_path.read_text(encoding='utf-8', errors='ignore')
        in_orbital = False
        last_occupied_idx = 0

        for line in content.split('\n'):
            if 'ORBITAL ENERGIES' in line:
                in_orbital = True
                continue
            if in_orbital:
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        idx = int(parts[0])
                        occ = float(parts[1])
                        if occ > 0.1:
                            last_occupied_idx = idx
                    except (ValueError, IndexError):
                        if last_occupied_idx > 0:
                            break

        if last_occupied_idx > 0:
            homo_idx = last_occupied_idx
            lumo_idx = last_occupied_idx + 1
            logger.info("Found HOMO=%d, LUMO=%d", homo_idx, lumo_idx)

    except Exception as e:
        logger.warning("HOMO/LUMO index parse error: %s", e)

    return homo_idx, lumo_idx


def _extract_geometry_block(out_path: Path) -> Tuple[str, int, int]:
    """Extract final geometry as atoms block, plus charge and multiplicity."""
    atoms_lines = []
    charge = 0
    multiplicity = 1

    try:
        content = out_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')

        for line in lines:
            if 'Total Charge' in line:
                m = re.search(r'(\d+)', line)
                if m:
                    charge = int(m.group(1))
            if 'Multiplicity' in line:
                m = re.search(r'(\d+)', line)
                if m:
                    multiplicity = int(m.group(1))

        # Find last CARTESIAN COORDINATES (ANGSTROEM)
        geom_start = -1
        for i, line in enumerate(lines):
            if 'CARTESIAN COORDINATES (ANGSTROEM)' in line:
                geom_start = i + 2

        if geom_start > 0:
            for line in lines[geom_start:]:
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        sym = parts[0]
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        atoms_lines.append(f"{sym:2s}  {x:14.8f}  {y:14.8f}  {z:14.8f}")
                    except ValueError:
                        break
                elif line.strip() == '':
                    if atoms_lines:
                        break

    except Exception as e:
        logger.warning("Geometry extraction error: %s", e)

    return '\n'.join(atoms_lines), charge, multiplicity


def get_electron_density_at_point(
    gbw_path: Path,
    point: Tuple[float, float, float],
) -> float:
    """
    Get electronic density value at specific 3D point.

    Phase A stub: Returns 0.0 (full density grid in future phase).
    """
    return 0.0


def extract_bond_orders(
    out_path: Path,
    num_atoms: int,
) -> Dict[Tuple[int, int], float]:
    """
    Extract Mayer bond orders from ORCA output (backward-compatible wrapper).
    """
    if not out_path.exists():
        return {}

    try:
        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return OrcaOutputParser._parse_bond_orders(lines)
    except Exception as e:
        logger.warning("Bond order extraction failed: %s", e)
        return {}


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[orca_interface.py v3.00] Portable ORCA DFT Interface")
    print(f"  Script dir: {_SCRIPT_DIR}")
    print(f"  ORCA found: {find_orca_executable()}")
    validate_orca_installation()
    print("[orca_interface.py v3.00] Ready (3-stage class separation + strict column check)")
