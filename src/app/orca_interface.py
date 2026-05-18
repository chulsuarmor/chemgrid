# orca_interface.py (v3.14 - Remote ORCA server client)
"""
ChemGrid — ORCA DFT Interface Module

Major changes in v3.14:
  ✅ Remote ORCA Client: RemoteOrcaClient class for delegating DFT
     calculations to housing/services/orca_api_server.py via HTTP.
     - is_available(): strict /health JSON check; status must be ok
     - calculate(): POST /orca/submit, then GET /orca/result/{job_id}
     - Uses the shared orca_remote_client contract and Bearer auth
  ✅ run_orca_dft_auto(): Portable remote-first DFT:
     - Tries remote ORCA server first so LG Gram/student machines do not need ORCA.
     - Local ORCA fallback is opt-in only via CHEMGRID_ORCA_ALLOW_LOCAL=1.
     - Returns OrcaDftResult only from a real remote/local ORCA calculation.

Previous (v3.13):
  ✅ ORCA-WSL-DFT: Full ORCA 6.1.0 Linux DFT via WSL Ubuntu-24.04:
     - find_orca_wsl() now checks known paths first:
       /home/skagjs/orca/orca_6_1_0_linux_x86-64_shared_openmpi418_avx2/orca
     - _execute_wsl() rewritten: copies .inp to WSL /tmp/, sets LD_LIBRARY_PATH
       for OpenMPI shared libs, runs ORCA, copies output back
     - NEW: run_orca_dft(smiles, method, basis, calc_type) — high-level function:
       * SMILES → RDKit 3D → ORCA .inp → WSL execution → parsed results
       * Returns OrcaDftResult: energy, HOMO-LUMO gap, charges, dipole
     - NEW: OrcaDftResult dataclass for structured DFT results
     - NEW: _parse_orca_dipole() — extracts dipole moment (Debye) from output
     - NEW: _parse_orca_homo_lumo() — extracts HOMO-LUMO gap (eV) from orbital energies
     - NEW: _generate_orca_inp_from_smiles() — SMILES → ORCA .inp file generator

Previous (v3.12):
  ✅ XTB-WSL: Full xtb GFN2-xTB integration via WSL:
     - _find_xtb_in_wsl() discovers xtb in WSL Ubuntu-24.04
     - _run_xtb_via_wsl() executes xtb via WSL with stdin XYZ
       (avoids Korean path encoding issues with /mnt/ conversion)
     - find_xtb_executable() now falls back to WSL when native not found
     - run_xtb_charges() supports both native and WSL execution
     - NEW: run_xtb_calculation(smiles, calc_type) — high-level function:
       * SMILES → RDKit 3D → XYZ → xtb (sp/opt/freq) → XtbResult
       * Returns energy, HOMO-LUMO gap, charges, dipole, frequencies
     - NEW: XtbResult dataclass for structured results
     - NEW: _parse_xtb_full_results() extracts all data from xtb output
     - NEW: _generate_xyz_from_smiles() — RDKit ETKDGv3 + MMFF/UFF

Previous (v3.11):
  ✅ WSL-001: WSL (Windows Subsystem for Linux) fallback execution:
     - _check_wsl_available() detects WSL installation and distros
     - _win_path_to_wsl() / _wsl_path_to_win() path converters
     - find_orca_wsl() discovers ORCA in WSL (native Linux or interop)
     - OrcaExecutor._execute_wsl() runs ORCA via WSL relay
     - Automatic fallback: native fails → WSL retry (if available)
     - Force WSL mode: OrcaExecutor(use_wsl=True)

Previous (v3.10):
  ✅ DFT-001: %plots cube generation verified — ORBITAL_PLOT_TEMPLATE uses
     MOREAD+NOITER with dim1/dim2/dim3=100, Gaussian_Cube format for
     HOMO/LUMO/density cube files. ORCA 6.1.1 has NO orca_plot utility.
  ✅ DFT-002: xtb GFN2-xTB integration added:
     - find_xtb_executable() auto-detects xtb from multiple candidate paths
     - run_xtb_charges() executes GFN2-xTB and parses Mulliken charges
     - map_xtb_charges_to_2d() maps 3D xtb charges to 2D atom keys
     - Graceful fallback if xtb not installed (returns empty dict)

Previous (v3.00):
  ✅ Portable path system: find_orca_executable() auto-detects ORCA
  ✅ 3-stage class separation: OrcaInputGenerator / OrcaExecutor / OrcaOutputParser
  ✅ Logging, custom exceptions, coordinate precision round(coord, 2)
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


# ============================================================================
# WSL (Windows Subsystem for Linux) SUPPORT
# ============================================================================

# Cached WSL availability (None = not checked yet)
_wsl_available_cache: Optional[bool] = None
# Cached WSL ORCA path (None = not checked, "" = checked but not found)
_wsl_orca_path_cache: Optional[str] = None


def _check_wsl_available() -> bool:
    """
    Check if WSL is available on this Windows system.

    Tests:
      1. Platform is win32
      2. 'wsl' command exists in PATH
      3. 'wsl --list' executes successfully (at least one distro installed)

    Returns:
        True if WSL is available and has at least one distribution.
    """
    global _wsl_available_cache
    if _wsl_available_cache is not None:
        return _wsl_available_cache

    if sys.platform != "win32":
        _wsl_available_cache = False
        return False

    wsl_exe = shutil.which("wsl")
    if not wsl_exe:
        logger.debug("WSL not found in system PATH")
        _wsl_available_cache = False
        return False

    try:
        result = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True, text=True, timeout=10  # 10 seconds
        )
        # --list --quiet outputs distribution names, one per line
        has_distro = bool(result.stdout.strip())
        _wsl_available_cache = has_distro
        if has_distro:
            logger.info("WSL available with distributions")
        else:
            logger.debug("WSL installed but no distributions found")
        return has_distro
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("WSL check failed: %s", e)
        _wsl_available_cache = False
        return False


def _win_path_to_wsl(win_path: Path) -> str:
    """
    Convert a Windows path to WSL-compatible /mnt/ path.

    Example: C:\\chemgrid\\calc.inp -> /mnt/c/chemgrid/calc.inp

    Args:
        win_path: Windows Path object (absolute).

    Returns:
        WSL-compatible path string.
    """
    # Resolve to absolute
    resolved = win_path.resolve()
    path_str = str(resolved)

    # Handle UNC paths (not supported)
    if path_str.startswith("\\\\"):
        logger.warning("UNC paths not supported for WSL conversion: %s", path_str)
        return path_str

    # Convert drive letter: C:\foo -> /mnt/c/foo
    if len(path_str) >= 2 and path_str[1] == ":":
        drive_letter = path_str[0].lower()
        rest = path_str[2:].replace("\\", "/")
        return f"/mnt/{drive_letter}{rest}"

    # Fallback: just replace backslashes
    return path_str.replace("\\", "/")


def _wsl_path_to_win(wsl_path: str) -> Path:
    """
    Convert a WSL /mnt/ path back to a Windows path.

    Example: /mnt/c/chemgrid/calc.out -> C:\\chemgrid\\calc.out

    Args:
        wsl_path: WSL path string (e.g., /mnt/c/...).

    Returns:
        Windows Path object.
    """
    if wsl_path.startswith("/mnt/") and len(wsl_path) >= 6:
        drive_letter = wsl_path[5].upper()
        rest = wsl_path[6:]  # after /mnt/X
        return Path(f"{drive_letter}:{rest}")
    return Path(wsl_path)


def find_orca_wsl() -> Optional[str]:
    """
    Find ORCA executable accessible via WSL.

    Checks three scenarios:
      1. Known ORCA 6.1.0 Linux binary in WSL (verified installation path)
      2. ORCA Linux binary installed natively in WSL (e.g., /opt/orca/orca, via PATH)
      3. Windows ORCA accessible via /mnt/c/ path with WSL interop

    Returns:
        WSL-compatible path to ORCA executable, or None if not found.
    """
    global _wsl_orca_path_cache
    if _wsl_orca_path_cache is not None:
        return _wsl_orca_path_cache if _wsl_orca_path_cache else None

    if not _check_wsl_available():
        _wsl_orca_path_cache = ""
        return None

    # Scenario 1: Known ORCA 6.1.0 Linux paths (verified installations)
    # These are checked first because they are known-good locations
    _known_wsl_orca_paths = [
        "/home/skagjs/orca/orca_6_1_0_linux_x86-64_shared_openmpi418_avx2/orca",
        "/opt/orca/orca",
        "/usr/local/bin/orca",
    ]
    for known_path in _known_wsl_orca_paths:
        try:
            result = subprocess.run(
                ["wsl", "-d", "Ubuntu-24.04", "--", "test", "-x", known_path],
                capture_output=True, text=True, timeout=10  # 10 seconds
            )
            if result.returncode == 0:
                logger.info("ORCA found at known WSL path: %s", known_path)
                _wsl_orca_path_cache = known_path
                return known_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("WSL known path check failed for %s: %s", known_path, e)

    # Scenario 2: Check if ORCA is natively installed in WSL via PATH
    try:
        result = subprocess.run(
            ["wsl", "-d", "Ubuntu-24.04", "--", "which", "orca"],
            capture_output=True, text=True, timeout=15  # 15 seconds
        )
        if result.returncode == 0 and result.stdout.strip():
            wsl_orca = result.stdout.strip()
            logger.info("ORCA found natively in WSL PATH: %s", wsl_orca)
            _wsl_orca_path_cache = wsl_orca
            return wsl_orca
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("WSL native ORCA check failed: %s", e)

    # Scenario 3: Check if Windows ORCA is accessible via /mnt/c/
    win_exe = find_orca_executable()
    if win_exe is not None:
        wsl_path = _win_path_to_wsl(win_exe)
        try:
            result = subprocess.run(
                ["wsl", "-d", "Ubuntu-24.04", "--", "test", "-f", wsl_path],
                capture_output=True, text=True, timeout=10  # 10 seconds
            )
            if result.returncode == 0:
                logger.info("Windows ORCA accessible from WSL via: %s", wsl_path)
                _wsl_orca_path_cache = wsl_path
                return wsl_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("WSL Windows ORCA check failed: %s", e)

    logger.debug("No ORCA found accessible via WSL")
    _wsl_orca_path_cache = ""
    return None


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
# NOTE: Only request Mulliken — ORCA 6.1.0 Linux rejects non-ASCII ö in LöwdinPop
# and P_LoewdinPop is also not recognized. Loewdin charges are printed by default.
DFT_TEMPLATE = """\
! B3LYP 6-31G(d) OptAll TIGHTSCF
%output
  Print[P_Mulliken] 1
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
  dim1 100
  dim2 100
  dim3 100
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
            # Rule N: isinstance guard for data
            if not isinstance(data, dict): data = {}
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
    Supports WSL (Windows Subsystem for Linux) fallback when native
    Windows execution fails or WSL-installed ORCA is preferred.
    """

    def __init__(self, orca_exe: Optional[Path] = None, timeout: int = DEFAULT_TIMEOUT,
                 use_wsl: bool = False):
        """
        Args:
            orca_exe: Path to ORCA executable (auto-detected if None).
            timeout: Maximum execution time in seconds (default 300).
            use_wsl: Force WSL execution mode. If False, WSL is used
                     as automatic fallback when native execution fails.
        """
        self._orca_exe = orca_exe
        self.timeout = timeout
        self.use_wsl = use_wsl

    @property
    def orca_exe(self) -> Path:
        if self._orca_exe is None:
            self._orca_exe = _get_orca_exe()
        return self._orca_exe

    def _execute_native(self, input_path: Path, work_dir: Path) -> Path:
        """
        Execute ORCA natively on Windows.

        Args:
            input_path: Path to .inp file.
            work_dir: Working directory.

        Returns:
            Path to the .out output file.
        """
        cmd = [str(self.orca_exe), str(input_path)]
        logger.info("Executing (native): %s", " ".join(cmd))
        logger.info("Work dir: %s", work_dir)

        # ORCA needs its own directory in PATH for helper binaries
        env = os.environ.copy()
        orca_dir = str(self.orca_exe.parent)
        # Rule N: isinstance guard for env
        if not isinstance(env, dict): env = {}
        if orca_dir not in env.get("PATH", ""):
            env["PATH"] = orca_dir + os.pathsep + env.get("PATH", "")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(work_dir),
                env=env,
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
        logger.info("ORCA completed (native). Output: %s", out_path)
        return out_path

    def _execute_wsl(self, input_path: Path, work_dir: Path) -> Path:
        """
        Execute ORCA via WSL (Windows Subsystem for Linux).

        Copies input file to WSL /tmp/ to avoid cross-filesystem issues,
        runs ORCA with proper LD_LIBRARY_PATH, then copies output back.

        Two modes:
          - Native WSL ORCA: Linux ORCA installed in WSL (preferred)
          - Interop mode: Windows ORCA.exe called from WSL (uses binfmt)

        Args:
            input_path: Windows Path to .inp file.
            work_dir: Windows working directory.

        Returns:
            Path to the .out output file (Windows path).

        Raises:
            OrcaNotFoundError: No ORCA accessible via WSL.
            OrcaExecutionError: ORCA returned non-zero exit code.
            OrcaTimeoutError: Calculation exceeded timeout.
        """
        wsl_orca = find_orca_wsl()
        if wsl_orca is None:
            raise OrcaNotFoundError(
                "ORCA not found via WSL. Install ORCA in WSL "
                "(e.g., extract to /opt/orca/ and add to PATH), "
                "or ensure Windows ORCA is accessible at /mnt/c/."
            )

        # Derive the ORCA directory for LD_LIBRARY_PATH and PATH
        wsl_orca_dir = "/".join(wsl_orca.split("/")[:-1])

        # Strategy: copy input to WSL /tmp/ to avoid /mnt/ cross-fs issues
        # This prevents Korean path encoding problems and slow /mnt/ I/O
        import uuid
        wsl_tmp_id = uuid.uuid4().hex[:8]
        wsl_tmp_dir = f"/tmp/chemgrid_orca_{wsl_tmp_id}"
        wsl_input_name = input_path.name
        wsl_tmp_input = f"{wsl_tmp_dir}/{wsl_input_name}"
        wsl_tmp_output = f"{wsl_tmp_dir}/{input_path.stem}.out"

        # Convert Windows input path to WSL /mnt/ path for copying
        wsl_src_input = _win_path_to_wsl(input_path)

        # Build the complete WSL bash command:
        # 1. Create /tmp/ work directory
        # 2. Copy input file to /tmp/
        # 3. Set LD_LIBRARY_PATH for shared libraries (OpenMPI, etc.)
        # 4. Set PATH for helper binaries (orca_scf, etc.)
        # 5. Run ORCA
        # 6. Keep output in /tmp/ (we'll copy back)
        bash_script = (
            f'mkdir -p "{wsl_tmp_dir}" && '
            f'cp "{wsl_src_input}" "{wsl_tmp_input}" && '
            f'export LD_LIBRARY_PATH="{wsl_orca_dir}:${{LD_LIBRARY_PATH:-}}" && '
            f'export PATH="{wsl_orca_dir}:$PATH" && '
            f'cd "{wsl_tmp_dir}" && '
            f'"{wsl_orca}" "{wsl_tmp_input}" > "{wsl_tmp_output}" 2>&1; '
            f'EXIT_CODE=$?; '
            f'echo "ORCA_EXIT_CODE=$EXIT_CODE"; '
            f'exit $EXIT_CODE'
        )

        cmd = [
            "wsl", "-d", "Ubuntu-24.04", "-e",
            "bash", "-c", bash_script
        ]

        logger.info("Executing (WSL): ORCA in %s", wsl_tmp_dir)
        logger.info("WSL ORCA binary: %s", wsl_orca)
        logger.info("LD_LIBRARY_PATH: %s", wsl_orca_dir)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            # Clean up WSL /tmp/ on timeout
            try:
                subprocess.run(
                    ["wsl", "-d", "Ubuntu-24.04", "-e", "rm", "-rf", wsl_tmp_dir],
                    capture_output=True, timeout=5
                )
            except Exception as e:
                logger.debug("Best-effort WSL cleanup failed on timeout: %s", e)
            raise OrcaTimeoutError(
                f"ORCA (WSL) calculation timed out (> {self.timeout} seconds)"
            )
        except FileNotFoundError:
            raise OrcaNotFoundError(
                "WSL command not found. Ensure WSL is installed."
            )

        if result.returncode != 0:
            stderr_msg = result.stderr[:2000] if result.stderr else "(no stderr)"
            stdout_tail = result.stdout[-1000:] if result.stdout else ""
            logger.warning("ORCA (WSL) stderr: %s", stderr_msg)
            logger.warning("ORCA (WSL) stdout tail: %s", stdout_tail)
            # Don't raise yet — ORCA sometimes exits non-zero but still produces output
            # Check if output was actually produced
            check_result = subprocess.run(
                ["wsl", "-d", "Ubuntu-24.04", "-e", "test", "-s", wsl_tmp_output],
                capture_output=True, timeout=5
            )
            if check_result.returncode != 0:
                # No output file — real failure
                # Clean up
                try:
                    subprocess.run(
                        ["wsl", "-d", "Ubuntu-24.04", "-e", "rm", "-rf", wsl_tmp_dir],
                        capture_output=True, timeout=5
                    )
                except Exception as e:
                    logger.debug("Best-effort WSL cleanup failed on exec error: %s", e)
                raise OrcaExecutionError(
                    f"ORCA (WSL) exited with code {result.returncode}:\n{stderr_msg}"
                )
            logger.warning(
                "ORCA (WSL) exited with code %d but output exists — "
                "proceeding with output parsing", result.returncode
            )

        # Copy output file back to Windows work_dir
        out_path = work_dir / f"{input_path.stem}.out"
        wsl_win_out = _win_path_to_wsl(out_path)

        try:
            subprocess.run(
                ["wsl", "-d", "Ubuntu-24.04", "-e",
                 "bash", "-c", f'cp "{wsl_tmp_output}" "{wsl_win_out}"'],
                capture_output=True, text=True, timeout=10
            )
        except Exception as e:
            logger.warning("Failed to copy ORCA output via WSL cp: %s — trying direct read", e)

        # Fallback: if cp failed, read the content directly
        if not out_path.exists():
            try:
                cat_result = subprocess.run(
                    ["wsl", "-d", "Ubuntu-24.04", "-e", "cat", wsl_tmp_output],
                    capture_output=True, text=True, timeout=10
                )
                if cat_result.returncode == 0 and cat_result.stdout:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(cat_result.stdout, encoding="utf-8")
                    logger.info("ORCA output retrieved via cat: %s", out_path)
            except Exception as e:
                logger.warning("Failed to retrieve ORCA output: %s", e)

        # Clean up WSL /tmp/
        try:
            subprocess.run(
                ["wsl", "-d", "Ubuntu-24.04", "-e", "rm", "-rf", wsl_tmp_dir],
                capture_output=True, timeout=5
            )
        except Exception as e:
            logger.debug("Best-effort WSL tmp cleanup failed: %s", e)

        if not out_path.exists():
            logger.warning(
                "ORCA (WSL) completed but output not found at %s. "
                "Check WSL file system.", out_path
            )
        else:
            logger.info("ORCA completed (WSL). Output: %s (%d bytes)",
                        out_path, out_path.stat().st_size)
        return out_path

    def execute(self, input_path: Path, work_dir: Optional[Path] = None) -> Path:
        """
        Execute ORCA calculation.

        Priority order:
          1. If use_wsl=True, go directly to WSL execution.
          2. If WSL is available and WSL ORCA is found, try WSL first
             (WSL ORCA 6.1.0 is proven stable; Windows ORCA often fails
             with exit code 3758096385).
          3. Fall back to native Windows execution if WSL unavailable or fails.

        Args:
            input_path: Path to .inp file.
            work_dir: Working directory (default: input file's parent).

        Returns:
            Path to the .out output file.

        Raises:
            OrcaNotFoundError: ORCA executable not found (native or WSL).
            OrcaExecutionError: ORCA returned non-zero exit code.
            OrcaTimeoutError: Calculation exceeded timeout.
            FileNotFoundError: Input file does not exist.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if work_dir is None:
            work_dir = input_path.parent

        # WSL-forced mode: skip native execution entirely
        if self.use_wsl:
            logger.info("WSL mode forced — executing via WSL")
            return self._execute_wsl(input_path, work_dir)

        # WSL-preferred: if WSL is available and has ORCA, try WSL first
        # (Windows ORCA frequently fails with exit code 3758096385)
        if _check_wsl_available() and find_orca_wsl() is not None:
            logger.info("WSL ORCA available — trying WSL execution first")
            try:
                return self._execute_wsl(input_path, work_dir)
            except OrcaError as wsl_err:
                # WSL failed — attempt native Windows fallback
                logger.warning(
                    "WSL ORCA execution failed (%s). "
                    "Attempting native Windows fallback...", wsl_err
                )
                try:
                    return self._execute_native(input_path, work_dir)
                except OrcaError as native_err:
                    # Both WSL and native failed — report both errors
                    logger.error(
                        "Both WSL and native ORCA execution failed. "
                        "WSL: %s | Native: %s", wsl_err, native_err
                    )
                    raise OrcaExecutionError(
                        f"ORCA execution failed (WSL and native fallback).\n"
                        f"  WSL error: {wsl_err}\n"
                        f"  Native error: {native_err}"
                    ) from native_err

        # No WSL available — try native execution with WSL fallback
        try:
            return self._execute_native(input_path, work_dir)
        except (OrcaNotFoundError, OrcaExecutionError) as native_err:
            # Native failed — attempt WSL fallback if available
            if not _check_wsl_available():
                raise  # No WSL, re-raise original error

            logger.warning(
                "Native ORCA execution failed (%s). "
                "Attempting WSL fallback...", native_err
            )
            try:
                return self._execute_wsl(input_path, work_dir)
            except OrcaError as wsl_err:
                # Both native and WSL failed — report both errors
                logger.error(
                    "Both native and WSL ORCA execution failed. "
                    "Native: %s | WSL: %s", native_err, wsl_err
                )
                raise OrcaExecutionError(
                    f"ORCA execution failed (native and WSL fallback).\n"
                    f"  Native error: {native_err}\n"
                    f"  WSL error: {wsl_err}"
                ) from wsl_err

    def run(self, input_path, work_dir: Optional[Path] = None,
            timeout: Optional[int] = None) -> Path:
        """
        Compatibility wrapper for execute().

        Some callers (e.g., arrow_generator.py) use .run() instead of
        .execute(). This method normalizes arguments and delegates.

        Args:
            input_path: Path (str or Path) to .inp file.
            work_dir: Working directory (default: input file's parent).
            timeout: Override timeout for this execution (optional).

        Returns:
            Path to the .out output file.
        """
        # Normalize input_path to Path object
        if isinstance(input_path, str):
            input_path = Path(input_path)

        # Allow per-call timeout override
        if timeout is not None:
            old_timeout = self.timeout
            self.timeout = timeout
            try:
                return self.execute(input_path, work_dir)
            finally:
                self.timeout = old_timeout

        return self.execute(input_path, work_dir)


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
                    except (ValueError, IndexError) as e:
                        logger.warning("Failed to parse geometry line (fallback format): %s", e)

            # 4-column format: SYMBOL X Y Z
            elif len(parts) == 4:
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    atom_idx = len(geometry)
                    geometry[atom_idx] = (round(x, 2), round(y, 2), round(z, 2))
                except (ValueError, IndexError) as e:
                    logger.warning("Failed to parse 4-column geometry line: %s", e)

        logger.debug("Geometry: extracted %d atoms", len(geometry))
        return geometry

    # ------------------------------------------------------------------
    # Mulliken charge parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_mulliken(lines: List[str]) -> Dict[int, float]:
        """
        Extract Mulliken atomic charges.

        Handles both ORCA output formats:
          - 3 columns: INDEX SYMBOL CHARGE (ORCA 6.1.1 Windows)
          - 4 columns: INDEX SYMBOL : CHARGE (ORCA 6.1.0 Linux)
        5+ columns are rejected (geometry data leak protection).
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
                    or "LÖWDIN" in line or "LOWDIN" in line
                    or "MULLIKEN REDUCED" in line):
                break

            stripped = line.strip()

            # Skip separator lines (e.g., "---..." or blank lines)
            if stripped.startswith("---") or stripped == "":
                continue

            # "Sum of atomic charges" marks end of charge data
            if "Sum of" in stripped:
                break

            parts = stripped.split()

            if len(parts) == 3:
                # INDEX SYMBOL CHARGE
                try:
                    atom_idx = int(parts[0])
                    charge = float(parts[2])
                    charges[atom_idx] = round(charge, 4)
                except (ValueError, IndexError) as e:
                    logger.warning("Failed to parse Mulliken charge (3-col): %s", e)

            elif len(parts) == 4 and parts[2] == ":":
                # INDEX SYMBOL : CHARGE  (ORCA 6.1.0 format)
                try:
                    atom_idx = int(parts[0])
                    charge = float(parts[3])
                    charges[atom_idx] = round(charge, 4)
                except (ValueError, IndexError) as e:
                    logger.warning("Failed to parse Mulliken charge (4-col): %s", e)

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
                except (ValueError, IndexError) as e:
                    logger.warning("Failed to parse Loewdin charge (3-col): %s", e)

            elif len(parts) == 4 and parts[2] == ":":
                try:
                    atom_idx = int(parts[0])
                    charge = float(parts[3])
                    charges[atom_idx] = round(charge, 4)
                except (ValueError, IndexError) as e:
                    logger.warning("Failed to parse Loewdin charge (4-col): %s", e)

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
        """Check if calculation converged or completed successfully."""
        for line in lines:
            if ("THE OPTIMIZATION HAS CONVERGED" in line
                    or "ORCA finished" in line
                    or "ORCA TERMINATED NORMALLY" in line):
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
                except (ValueError, IndexError) as e:
                    logger.debug("Skipping unparseable bond order line: %s", e)
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
            # Rule N: isinstance guard for atom_symbols
            if not isinstance(atom_symbols, dict): atom_symbols = {}
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
# XTB GFN2-xTB INTEGRATION (DFT-002 + WSL support)
# ============================================================================

# Sentinel path indicating xtb is available via WSL, not as a native executable.
_XTB_WSL_SENTINEL = Path("__WSL_XTB__")

# Cached WSL xtb path (None = not checked, "" = checked but not found)
_wsl_xtb_path_cache: Optional[str] = None

# Known WSL xtb installation path (user-confirmed working 2026-04-12)
_WSL_XTB_PATH = "/home/skagjs/xtb/xtb-dist/bin/xtb"
_WSL_XTB_HOME = "/home/skagjs/xtb/xtb-dist"
_WSL_DISTRO = "Ubuntu-24.04"


def _find_xtb_in_wsl() -> Optional[str]:
    """
    Discover xtb executable inside WSL (Windows Subsystem for Linux).

    Checks:
      1. Known installation path: /home/skagjs/xtb/xtb-dist/bin/xtb
      2. WSL system PATH (which xtb)

    Returns:
        WSL path string to xtb, or None if not found.
    """
    global _wsl_xtb_path_cache
    if _wsl_xtb_path_cache is not None:
        return _wsl_xtb_path_cache if _wsl_xtb_path_cache else None

    if not _check_wsl_available():
        _wsl_xtb_path_cache = ""
        return None

    # Check known installation path
    try:
        result = subprocess.run(
            ["wsl", "-d", _WSL_DISTRO, "--", "test", "-x", _WSL_XTB_PATH],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            logger.info("xtb found in WSL at known path: %s", _WSL_XTB_PATH)
            _wsl_xtb_path_cache = _WSL_XTB_PATH
            return _WSL_XTB_PATH
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("WSL xtb known-path check failed: %s", e)

    # Fallback: search WSL system PATH
    try:
        result = subprocess.run(
            ["wsl", "-d", _WSL_DISTRO, "--", "which", "xtb"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            wsl_xtb = result.stdout.strip()
            logger.info("xtb found in WSL PATH: %s", wsl_xtb)
            _wsl_xtb_path_cache = wsl_xtb
            return wsl_xtb
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("WSL xtb PATH check failed: %s", e)

    logger.debug("xtb not found in WSL")
    _wsl_xtb_path_cache = ""
    return None


def find_xtb_executable() -> Optional[Path]:
    """
    Portable xtb executable discovery.

    Searches multiple candidate paths relative to the script location,
    then falls back to the system PATH, then to WSL.

    Search order:
      1. XTB_PATH / CHEMGRID_XTB_PATH env or project .env
      2. ChemGrid bundled bin/xtb release folders
      3. _SCRIPT_DIR / "xtb" / "xtb.exe"  (or "xtb" on Linux/Mac)
      4. _SCRIPT_DIR.parent / "xtb" / "xtb.exe"
      5. _SCRIPT_DIR.parent.parent / "xtb" / "xtb.exe"
      6. System PATH (shutil.which("xtb"))
      7. WSL: known path + WSL PATH  (returns _XTB_WSL_SENTINEL)

    Returns:
        Path to xtb executable, _XTB_WSL_SENTINEL if only in WSL, or None.
    """
    exe_name = "xtb.exe" if sys.platform == "win32" else "xtb"
    project_root = _SCRIPT_DIR.parent.parent

    def _project_env_value(*names: str) -> str:
        env_path = project_root / ".env"
        if not env_path.exists():
            return ""
        try:
            for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() in names:
                    return value.strip().strip('"').strip("'")
        except OSError as exc:
            logger.warning("xtb .env read failed: %s", exc)
        return ""

    env_candidates = [
        os.environ.get("XTB_PATH", ""),
        os.environ.get("CHEMGRID_XTB_PATH", ""),
        _project_env_value("XTB_PATH", "CHEMGRID_XTB_PATH"),
    ]
    for raw_path in env_candidates:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = Path(raw_path.strip())
        if candidate.is_file():
            logger.info("xtb found via env/.env: %s", candidate)
            return candidate

    bundled_candidates = [
        project_root / "bin" / "xtb" / "xtb-6.7.1" / "bin" / exe_name,
        project_root / "bin" / "xtb" / "xtb-6.7.1pre" / "bin" / exe_name,
    ]
    for candidate in bundled_candidates:
        if candidate.is_file():
            logger.info("xtb found in ChemGrid bundled bin: %s", candidate)
            return candidate

    search_roots = [
        _SCRIPT_DIR,
        _SCRIPT_DIR.parent,
        project_root,
    ]

    for root in search_roots:
        candidate = root / "xtb" / exe_name
        if candidate.exists():
            logger.info("xtb found: %s", candidate)
            return candidate

    # Fallback: search system PATH
    xtb_in_path = shutil.which("xtb")
    if xtb_in_path:
        logger.info("xtb found in PATH: %s", xtb_in_path)
        return Path(xtb_in_path)

    # WSL fallback (Windows only)
    if sys.platform == "win32":
        wsl_path = _find_xtb_in_wsl()
        if wsl_path:
            logger.info("xtb available via WSL: %s", wsl_path)
            return _XTB_WSL_SENTINEL

    logger.debug("xtb executable not found in any candidate path")
    return None


def _is_wsl_xtb(exe_path: Optional[Path]) -> bool:
    """Check if the xtb executable path indicates WSL mode."""
    return exe_path is not None and exe_path == _XTB_WSL_SENTINEL


def validate_xtb_installation() -> bool:
    """
    Check if xtb is properly installed (native or WSL).

    Returns:
        True if xtb executable is found, False otherwise.
    """
    exe = find_xtb_executable()
    if exe is None:
        logger.info("xtb not installed — GFN2-xTB charges unavailable (graceful fallback)")
        return False
    if _is_wsl_xtb(exe):
        logger.info("xtb installation verified via WSL: %s", _find_xtb_in_wsl())
    else:
        logger.info("xtb installation verified: %s", exe)
    return True


def _run_xtb_via_wsl(
    xyz_content: str,
    calc_type: str = "sp",
    charge: int = 0,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """
    Execute xtb calculation via WSL.

    Passes XYZ content via stdin to avoid Windows path encoding issues
    (Korean username in TEMP path causes WSL /mnt/ conversion failures).
    Uses /tmp/ inside WSL as the working directory.

    Args:
        xyz_content: Full XYZ file content as string.
        calc_type: "sp" (single point), "opt" (geometry optimization),
                   "freq" (vibrational frequencies / Hessian).
        charge: Total molecular charge (default 0).
        timeout: Maximum execution time in seconds.

    Returns:
        subprocess.CompletedProcess with stdout/stderr.

    Raises:
        subprocess.TimeoutExpired: If calculation exceeds timeout.
    """
    # Explicit PATH avoids Windows PATH leaking into WSL
    # (spaces in "Program Files" cause bash syntax errors)
    xtb_env = (
        f"export XTBHOME={_WSL_XTB_HOME} "
        f"&& export PATH={_WSL_XTB_HOME}/bin:/usr/local/bin:/usr/bin:/bin "
        f"&& export XTBPATH={_WSL_XTB_HOME}/share/xtb"
    )

    # Use PID-based unique tmpdir to avoid collisions
    wsl_tmpdir = "/tmp/chemgrid_xtb_$$"

    xtb_args = "xtb mol.xyz --gfn 2"
    xtb_args += f" --chrg {int(charge)}"

    if calc_type == "opt":
        xtb_args += " --opt"
    elif calc_type == "freq":
        xtb_args += " --hess"
    # "sp" is default — no extra flag needed

    xtb_args += " --pop"  # Always request population analysis (charges + Wiberg)

    # Pipe XYZ via stdin, run in WSL /tmp/, output optimized coords if opt
    opt_cat = ""
    if calc_type == "opt":
        # After xtb finishes, cat the optimized XYZ so we can parse it
        opt_cat = f" && echo '=== XTBOPT ===' && cat {wsl_tmpdir}/xtbopt.xyz 2>/dev/null"

    cmd_str = (
        f"{xtb_env} && "
        f"mkdir -p {wsl_tmpdir} && "
        f"cat > {wsl_tmpdir}/mol.xyz && "
        f"cd {wsl_tmpdir} && "
        f"{xtb_args}"
        f"{opt_cat} && "
        f"rm -rf {wsl_tmpdir}"
    )

    return subprocess.run(
        ["wsl", "-d", _WSL_DISTRO, "--", "bash", "-c", cmd_str],
        input=xyz_content,
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace"
    )


def _generate_xtb_xyz(
    atoms: Dict,
    output_path: Path,
) -> Path:
    """
    Generate XYZ coordinate file for xtb from 2D atom data.

    Args:
        atoms: {(x,y): {"main": "C"|""|"O"|..., "attach": {...}}}
        output_path: Where to write .xyz file.

    Returns:
        Path to the generated .xyz file.
    """
    atom_lines = []
    for (x, y), data in atoms.items():
        # Rule N: isinstance guard for data
        if not isinstance(data, dict): data = {}
        symbol = data.get("main", "")
        # Carbon stored as '' (empty string) in ChemGrid
        if symbol == "":
            symbol = "C"
        x_norm = round(float(x) / 40.0, 4)  # Pixel → approximate Angstrom
        y_norm = round(float(y) / 40.0, 4)
        z = 0.0  # 2D → Z = 0
        atom_lines.append(f"{symbol}  {x_norm:12.6f}  {y_norm:12.6f}  {z:12.6f}")

    num_atoms = len(atom_lines)
    content = f"{num_atoms}\nChemGrid xtb input\n" + "\n".join(atom_lines) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info("xtb XYZ file generated: %s (%d atoms)", output_path, num_atoms)
    return output_path


def run_xtb_charges(
    atoms: Dict,
    charge: int = 0,
    work_dir: Optional[Path] = None,
    timeout: int = 60,
) -> Dict[int, float]:
    """
    Run GFN2-xTB calculation and extract Mulliken charges.

    This provides fast semi-empirical charges as an alternative to
    full DFT (ORCA) calculation. Useful for improved ESP rendering
    when ORCA is unavailable or for quick previews.

    Supports both native xtb and WSL-based execution.

    Args:
        atoms: {(x,y): {"main": "C"|""|"O"|..., "attach": {...}}}
        charge: Total molecular charge (default 0).
        work_dir: Working directory (default: temp directory). Ignored for WSL mode.
        timeout: Maximum execution time in seconds (default 60).

    Returns:
        {atom_index: mulliken_charge} — empty dict if xtb not installed
        or calculation fails (graceful fallback).
    """
    xtb_exe = find_xtb_executable()
    if xtb_exe is None:
        logger.debug("xtb not available — returning empty charges")
        return {}

    # Generate XYZ content (needed for both native and WSL modes)
    if work_dir is None:
        import tempfile
        work_dir = Path(tempfile.mkdtemp(prefix="chemgrid_xtb_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    xyz_path = work_dir / "mol.xyz"
    _generate_xtb_xyz(atoms, xyz_path)

    # --- WSL execution path ---
    if _is_wsl_xtb(xtb_exe):
        logger.info("Running xtb GFN2-xTB via WSL (single point, charges)")
        xyz_content = xyz_path.read_text(encoding="utf-8")
        try:
            result = _run_xtb_via_wsl(
                xyz_content, calc_type="sp", charge=charge, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            logger.warning("xtb WSL calculation timed out (> %d seconds)", timeout)
            return {}
        except Exception as e:
            logger.warning("xtb WSL execution error: %s", e)
            return {}
    else:
        # --- Native execution path ---
        cmd = [
            str(xtb_exe),
            str(xyz_path),
            "--gfn", "2",
            "--chrg", str(charge),
            "--pop",  # Request population analysis (Mulliken charges)
        ]
        logger.info("Running xtb GFN2-xTB: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(work_dir),
            )
        except subprocess.TimeoutExpired:
            logger.warning("xtb calculation timed out (> %d seconds)", timeout)
            return {}
        except FileNotFoundError:
            logger.warning("xtb executable not found at runtime: %s", xtb_exe)
            return {}
        except Exception as e:
            logger.warning("xtb execution error: %s", e)
            return {}

    if result.returncode != 0:
        logger.warning("xtb exited with code %d: %s",
                        result.returncode, result.stderr[:500] if result.stderr else "")
        return {}

    # Parse Mulliken charges from xtb output
    charges = _parse_xtb_mulliken_charges(result.stdout)

    if charges:
        logger.info("xtb GFN2-xTB charges: %d atoms parsed", len(charges))
    else:
        logger.warning("xtb ran successfully but no charges extracted")

    return charges


def _parse_xtb_mulliken_charges(stdout: str) -> Dict[int, float]:
    """
    Parse Mulliken charges from xtb stdout output.

    xtb prints a section like:
        #   Z          covCN         q      C6AA      α(0)
        1   6 C        ...          -0.123   ...       ...
        2   1 H        ...           0.045   ...       ...

    The 'q' column (5th) contains the Mulliken partial charge.

    Args:
        stdout: Complete xtb stdout text.

    Returns:
        {atom_index (0-based): charge} dict.
    """
    charges: Dict[int, float] = {}
    lines = stdout.split("\n")
    in_charge_section = False

    for line in lines:
        stripped = line.strip()

        # Detect the Mulliken/CM5 charge table header
        if "#   Z" in line and "q" in line:
            in_charge_section = True
            charges = {}  # Reset — use last occurrence
            continue

        if not in_charge_section:
            continue

        # Empty line or non-data line exits section
        if stripped == "" or stripped.startswith("---") or stripped.startswith("*"):
            if charges:
                break
            continue

        parts = stripped.split()
        if len(parts) >= 5:
            try:
                atom_num = int(parts[0])  # 1-based in xtb output
                charge = float(parts[4])  # 'q' column
                charges[atom_num - 1] = round(charge, 4)  # Convert to 0-based
            except (ValueError, IndexError):
                if charges:
                    break

    return charges


def map_xtb_charges_to_2d(
    atoms: Dict,
    xtb_charges: Dict[int, float],
) -> Dict[tuple, float]:
    """
    Map xtb atom-index-based charges to 2D atom keys.

    The xtb charges are indexed by atom order (0-based), matching
    the iteration order of the atoms dict.

    Args:
        atoms: {(x,y): {"main": "C"|""|"O"|..., "attach": {...}}}
        xtb_charges: {atom_index: charge} from run_xtb_charges().

    Returns:
        {(x,y): charge} mapped to 2D atom positions.
    """
    mapped: Dict[tuple, float] = {}
    for idx, key in enumerate(atoms.keys()):
        if idx in xtb_charges:
            mapped[key] = xtb_charges[idx]
    return mapped


def get_xtb_charges_for_molecule(
    atoms: Dict,
    charge: int = 0,
) -> Dict[tuple, float]:
    """
    High-level convenience function: run xtb and return charges mapped to 2D keys.

    Graceful fallback: returns empty dict if xtb is not installed.

    Args:
        atoms: ChemGrid atoms dict {(x,y): {"main": ..., "attach": ...}}
        charge: Total molecular charge.

    Returns:
        {(x,y): mulliken_charge} — empty dict on any failure.
    """
    xtb_charges = run_xtb_charges(atoms, charge=charge)
    if not xtb_charges:
        return {}
    return map_xtb_charges_to_2d(atoms, xtb_charges)


# ============================================================================
# XTB FULL CALCULATION (SMILES-based, WSL-aware)
# ============================================================================

@dataclass
class XtbResult:
    """
    Container for xtb calculation results.

    Attributes:
        success: True if calculation completed successfully.
        energy_eh: Total energy in Hartree (Eh).
        homo_lumo_gap_ev: HOMO-LUMO gap in electron-volts (eV).
        charges: {atom_index (0-based): Mulliken charge}.
        dipole_debye: Molecular dipole moment magnitude in Debye.
        frequencies_cm1: Vibrational frequencies in cm^-1 (freq calc only).
        ir_intensities: IR intensities in km/mol (freq calc only).
        optimized_xyz: Optimized XYZ content string (opt calc only).
        calc_type: Calculation type that was performed.
        smiles: Input SMILES string.
        error_message: Error description if success is False.
    """
    success: bool = False
    energy_eh: Optional[float] = None
    homo_lumo_gap_ev: Optional[float] = None
    charges: Dict[int, float] = field(default_factory=dict)
    dipole_debye: Optional[float] = None
    frequencies_cm1: List[float] = field(default_factory=list)
    ir_intensities: List[float] = field(default_factory=list)
    optimized_xyz: Optional[str] = None
    calc_type: str = "sp"
    smiles: str = ""
    error_message: str = ""


def _parse_xtb_full_results(stdout: str, calc_type: str = "sp") -> XtbResult:
    """
    Parse comprehensive results from xtb stdout.

    Extracts: energy, HOMO-LUMO gap, charges, dipole, frequencies, IR intensities.

    Args:
        stdout: Complete xtb stdout text.
        calc_type: "sp", "opt", or "freq".

    Returns:
        XtbResult with all parsed fields.
    """
    result = XtbResult(calc_type=calc_type)

    if not isinstance(stdout, str) or not stdout.strip():
        result.error_message = "Empty xtb output"
        return result

    lines = stdout.split("\n")
    in_charge_section = False
    in_freq_section = False
    in_ir_section = False

    raw_freqs: List[float] = []
    raw_ir: List[float] = []
    charges: Dict[int, float] = {}

    for line in lines:
        stripped = line.strip()

        # --- Total energy ---
        if "| TOTAL ENERGY" in line:
            parts = stripped.split()
            for i, p in enumerate(parts):
                if p == "ENERGY":
                    try:
                        result.energy_eh = float(parts[i + 1])
                    except (IndexError, ValueError):
                        logger.warning("Failed to parse xtb energy from: %s", stripped)
                    break

        # --- HOMO-LUMO gap ---
        if "| HOMO-LUMO GAP" in line:
            parts = stripped.split()
            for i, p in enumerate(parts):
                if p == "GAP":
                    try:
                        result.homo_lumo_gap_ev = float(parts[i + 1])
                    except (IndexError, ValueError):
                        logger.warning("Failed to parse xtb HOMO-LUMO gap from: %s", stripped)
                    break

        # --- Dipole moment (from "full:" line after "molecular dipole:") ---
        if stripped.startswith("full:") and "q" not in stripped:
            parts = stripped.split()
            if len(parts) >= 5:
                try:
                    result.dipole_debye = abs(float(parts[-1]))
                except (ValueError, IndexError) as e:
                    logger.debug("Failed to parse xtb dipole from line: %s", e)

        # --- Charge table ---
        if "#   Z" in line and "q" in line:
            in_charge_section = True
            charges = {}
            continue

        if in_charge_section:
            if stripped == "" or stripped.startswith("---") or stripped.startswith("*"):
                if charges:
                    in_charge_section = False
                continue
            parts = stripped.split()
            if len(parts) >= 5:
                try:
                    atom_num = int(parts[0])
                    charge_val = float(parts[4])
                    charges[atom_num - 1] = round(charge_val, 4)  # 0-based
                except (ValueError, IndexError):
                    if charges:
                        in_charge_section = False

        # --- Vibrational frequencies (eigval lines after "projected vibrational") ---
        if "projected vibrational frequencies" in line.lower():
            in_freq_section = True
            raw_freqs = []
            continue

        if in_freq_section and stripped.startswith("eigval"):
            # "eigval :   290.31   426.83   478.82 ..."
            parts = stripped.split(":")[1].strip().split() if ":" in stripped else []
            for val_str in parts:
                try:
                    raw_freqs.append(float(val_str))
                except ValueError as e:
                    logger.debug("Skipping non-numeric frequency value '%s': %s", val_str, e)
        elif in_freq_section and not stripped.startswith("eigval") and raw_freqs:
            in_freq_section = False

        # --- IR intensities ---
        if "IR intensities" in line:
            in_ir_section = True
            raw_ir = []
            continue

        if in_ir_section:
            if stripped == "" or "Raman" in line:
                in_ir_section = False
                continue
            # "  1:  0.40   2:  3.33   3:  0.06 ..."
            import re as _re
            matches = _re.findall(r'\d+:\s*([\d.]+)', stripped)
            for m in matches:
                try:
                    raw_ir.append(float(m))
                except ValueError as e:
                    logger.debug("Skipping non-numeric IR intensity '%s': %s", m, e)

        # --- Optimized XYZ (appended by _run_xtb_via_wsl for opt runs) ---
        if "=== XTBOPT ===" in line:
            # Everything after this marker is the optimized XYZ
            idx = stdout.find("=== XTBOPT ===")
            if idx >= 0:
                result.optimized_xyz = stdout[idx + len("=== XTBOPT ==="):].strip()

    result.charges = charges

    # Filter out near-zero translational/rotational modes (first 6 for nonlinear)
    # Keep only real, positive frequencies
    MIN_FREQ_CM1 = 10.0  # threshold to exclude translational/rotational modes
    result.frequencies_cm1 = [f for f in raw_freqs if f > MIN_FREQ_CM1]

    # Align IR intensities with frequencies
    # xtb outputs all 3N modes in IR intensities; we need to align with filtered freqs
    if raw_ir and raw_freqs:
        # Build index map: which indices in raw_freqs survived the filter
        filtered_ir = []
        for i, freq in enumerate(raw_freqs):
            if freq > MIN_FREQ_CM1 and i < len(raw_ir):
                filtered_ir.append(raw_ir[i])
        result.ir_intensities = filtered_ir

    result.success = result.energy_eh is not None
    return result


def _generate_xyz_from_smiles(smiles: str) -> Optional[str]:
    """
    Generate XYZ coordinate string from SMILES using RDKit.

    Uses ETKDGv3 for 3D embedding + MMFF/UFF force field optimization.

    Args:
        smiles: SMILES string.

    Returns:
        XYZ file content as string, or None on failure.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        logger.warning("RDKit not available — cannot generate 3D coordinates from SMILES")
        return None

    # Rule L: MolFromSmiles + None check
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("Invalid SMILES for xtb calculation: %s", smiles)
        return None

    mol = Chem.AddHs(mol)

    # Embed 3D coordinates
    embed_result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    if embed_result != 0:
        # Fallback: random seed
        embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
        if embed_result != 0:
            logger.warning("Could not generate 3D coordinates for SMILES: %s", smiles)
            return None

    # Optimize geometry
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
    except Exception as e:
        logger.debug("MMFF optimization failed, falling back to UFF: %s", e)
        try:
            AllChem.UFFOptimizeMolecule(mol, maxIters=200)
        except Exception as e:
            logger.debug("Force field optimization skipped: %s", e)

    conf = mol.GetConformer()
    num_atoms = mol.GetNumAtoms()
    lines = [str(num_atoms), f"Generated from {smiles}"]
    for i in range(num_atoms):
        pos = conf.GetAtomPosition(i)
        sym = mol.GetAtomWithIdx(i).GetSymbol()
        lines.append(f"{sym}  {pos.x:12.6f}  {pos.y:12.6f}  {pos.z:12.6f}")

    return "\n".join(lines) + "\n"


def run_xtb_calculation(
    smiles: str,
    calc_type: str = "sp",
    charge: int = 0,
    timeout: int = 120,
) -> XtbResult:
    """
    Run xtb GFN2-xTB calculation from a SMILES string.

    Generates 3D coordinates via RDKit, then runs xtb (native or WSL).
    Supports single-point energy, geometry optimization, and frequency
    (vibrational) calculations.

    Args:
        smiles: SMILES string for the molecule.
        calc_type: "sp" (single point), "opt" (geometry optimization),
                   "freq" (vibrational frequencies / Hessian).
        charge: Total molecular charge (default 0).
        timeout: Maximum execution time in seconds (default 120).

    Returns:
        XtbResult dataclass with energy, homo_lumo_gap, charges, dipole,
        frequencies (if freq), optimized_xyz (if opt).
        On failure, XtbResult.success is False with error_message set.
    """
    # Rule N: validate inputs
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("run_xtb_calculation: empty or non-string SMILES")
        return XtbResult(success=False, error_message="Empty SMILES", smiles=str(smiles))

    if not isinstance(calc_type, str):
        calc_type = "sp"
    calc_type = calc_type.lower().strip()
    if calc_type not in ("sp", "opt", "freq"):
        logger.warning("run_xtb_calculation: invalid calc_type '%s', using 'sp'", calc_type)
        calc_type = "sp"

    # Check xtb availability
    xtb_exe = find_xtb_executable()
    if xtb_exe is None:
        logger.warning("run_xtb_calculation: xtb not available (native or WSL)")
        return XtbResult(
            success=False,
            error_message="xtb not installed (checked native paths, system PATH, and WSL)",
            smiles=smiles, calc_type=calc_type
        )

    # Generate 3D XYZ from SMILES
    xyz_content = _generate_xyz_from_smiles(smiles)
    if xyz_content is None:
        return XtbResult(
            success=False,
            error_message=f"Failed to generate 3D coordinates for SMILES: {smiles}",
            smiles=smiles, calc_type=calc_type
        )

    # Execute xtb
    use_wsl = _is_wsl_xtb(xtb_exe)

    if use_wsl:
        logger.info("Running xtb %s via WSL for: %s", calc_type, smiles)
        try:
            proc = _run_xtb_via_wsl(
                xyz_content, calc_type=calc_type, charge=charge, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            logger.warning("xtb WSL %s timed out (> %d s) for: %s", calc_type, timeout, smiles)
            return XtbResult(
                success=False,
                error_message=f"xtb {calc_type} timed out after {timeout}s",
                smiles=smiles, calc_type=calc_type
            )
        except Exception as e:
            logger.warning("xtb WSL %s error for %s: %s", calc_type, smiles, e)
            return XtbResult(
                success=False,
                error_message=f"xtb WSL execution error: {e}",
                smiles=smiles, calc_type=calc_type
            )
    else:
        # Native execution
        import tempfile
        work_dir = Path(tempfile.mkdtemp(prefix="chemgrid_xtb_"))
        xyz_path = work_dir / "mol.xyz"
        xyz_path.write_text(xyz_content, encoding="utf-8")

        cmd = [str(xtb_exe), str(xyz_path), "--gfn", "2", "--chrg", str(int(charge)), "--pop"]
        if calc_type == "opt":
            cmd.append("--opt")
        elif calc_type == "freq":
            cmd.append("--hess")

        logger.info("Running xtb %s natively: %s", calc_type, " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",  # M812: cp949 env xtb UTF-8 output guard
                timeout=timeout, cwd=str(work_dir)
            )
            # For opt, read the optimized XYZ file
            if calc_type == "opt":
                opt_xyz = work_dir / "xtbopt.xyz"
                if opt_xyz.exists():
                    opt_content = opt_xyz.read_text(encoding="utf-8")
                    # Prepend marker so parser can find it
                    proc = subprocess.CompletedProcess(
                        proc.args, proc.returncode,
                        proc.stdout + "\n=== XTBOPT ===\n" + opt_content,
                        proc.stderr
                    )
        except subprocess.TimeoutExpired:
            logger.warning("xtb native %s timed out (> %d s)", calc_type, timeout)
            return XtbResult(
                success=False,
                error_message=f"xtb {calc_type} timed out after {timeout}s",
                smiles=smiles, calc_type=calc_type
            )
        except Exception as e:
            logger.warning("xtb native %s error: %s", calc_type, e)
            return XtbResult(
                success=False,
                error_message=f"xtb execution error: {e}",
                smiles=smiles, calc_type=calc_type
            )

    if proc.returncode != 0:
        stderr_snippet = proc.stderr[:500] if proc.stderr else ""
        logger.warning("xtb %s exited with code %d: %s", calc_type, proc.returncode, stderr_snippet)
        return XtbResult(
            success=False,
            error_message=f"xtb exited with code {proc.returncode}: {stderr_snippet}",
            smiles=smiles, calc_type=calc_type
        )

    # Parse results
    xtb_result = _parse_xtb_full_results(proc.stdout, calc_type=calc_type)
    xtb_result.smiles = smiles

    if xtb_result.success:
        logger.info(
            "xtb %s complete: E=%.6f Eh, gap=%.2f eV, %d charges, dipole=%.2f D",
            calc_type,
            xtb_result.energy_eh or 0.0,
            xtb_result.homo_lumo_gap_ev or 0.0,
            len(xtb_result.charges),
            xtb_result.dipole_debye or 0.0,
        )
        if calc_type == "freq" and xtb_result.frequencies_cm1:
            logger.info("  Frequencies: %d modes, range %.1f–%.1f cm-1",
                        len(xtb_result.frequencies_cm1),
                        min(xtb_result.frequencies_cm1),
                        max(xtb_result.frequencies_cm1))
    else:
        logger.warning("xtb %s ran but parsing failed for: %s", calc_type, smiles)

    return xtb_result


# ============================================================================
# ORCA DFT HIGH-LEVEL INTERFACE (v3.12)
# ============================================================================

@dataclass
class OrcaDftResult:
    """
    Container for ORCA DFT calculation results from SMILES input.

    Attributes:
        success: True if calculation completed successfully.
        energy_eh: Total SCF energy in Hartree (Eh).
        homo_lumo_gap_ev: HOMO-LUMO gap in electron-volts (eV), or None if not parsed.
        mulliken_charges: {atom_index (0-based): Mulliken charge}.
        dipole_debye: Molecular dipole moment magnitude in Debye, or None.
        method: DFT method used (e.g., "B3LYP").
        basis: Basis set used (e.g., "6-31G(d)").
        calc_type: Calculation type ("sp", "opt").
        smiles: Input SMILES string.
        n_atoms: Number of atoms (including hydrogens).
        wall_time_s: Wall-clock time in seconds.
        error_message: Error description if success is False.
    """
    success: bool = False
    energy_eh: Optional[float] = None
    homo_lumo_gap_ev: Optional[float] = None
    mulliken_charges: Dict[int, float] = field(default_factory=dict)
    dipole_debye: Optional[float] = None
    method: str = "B3LYP"
    basis: str = "6-31G(d)"
    calc_type: str = "sp"
    smiles: str = ""
    n_atoms: int = 0
    wall_time_s: float = 0.0
    error_message: str = ""


def _parse_orca_dipole(lines: List[str]) -> Optional[float]:
    """
    Parse dipole moment magnitude from ORCA output.

    Looks for the DIPOLE MOMENT section and extracts the total magnitude.
    ORCA format:
        -------------
        DIPOLE MOMENT
        -------------
                                    X             Y             Z
        Electronic contribution:  -0.00000      -0.00000       0.00000
        Nuclear contribution   :   0.00000       0.00000       0.00000
                                -----------------------------------------
        Total Dipole Moment    :  -0.00000      -0.00000       0.00000
                                -----------------------------------------
        Magnitude (Debye)      :   0.00000

    Returns:
        Dipole moment in Debye, or None if not found.
    """
    for i, line in enumerate(lines):
        # Look for "Magnitude (Debye)" or "Magnitude (a.u.)"
        if "Magnitude (Debye)" in line:
            parts = line.strip().split()
            try:
                return float(parts[-1])
            except (ValueError, IndexError) as e:
                logger.warning("Failed to parse dipole magnitude: %s", e)
        # Alternative: some ORCA versions use "Total Dipole Moment" and magnitude on next line
        if "Total Dipole Moment" in line and ":" in line:
            # Check next few lines for magnitude
            for j in range(i + 1, min(i + 5, len(lines))):
                if "Magnitude" in lines[j]:
                    parts = lines[j].strip().split()
                    try:
                        return float(parts[-1])
                    except (ValueError, IndexError) as e:
                        logger.debug("Failed to parse ORCA dipole magnitude: %s", e)
    return None


def _parse_orca_homo_lumo(lines: List[str]) -> Optional[float]:
    """
    Parse HOMO-LUMO gap from ORCA output.

    ORCA prints orbital energies in the ORBITAL ENERGIES section.
    We find the last occupied orbital (occ > 0) = HOMO and the
    first unoccupied orbital (occ == 0) = LUMO, then compute the gap.

    ORCA format:
        ORBITAL ENERGIES
                         SPIN UP ORBITALS
          NO   OCC          E(Eh)            E(eV)
           0   2.0000     -10.174040      -276.9172
           ...
          20   2.0000      -0.325107        -8.8466   (HOMO)
          21   0.0000       0.112345         3.0571   (LUMO)
           ...

    Returns:
        HOMO-LUMO gap in eV, or None if not found.
    """
    in_orbital_section = False
    homo_ev = None
    lumo_ev = None

    for line in lines:
        if "ORBITAL ENERGIES" in line:
            in_orbital_section = True
            homo_ev = None
            lumo_ev = None
            continue

        if not in_orbital_section:
            continue

        # Section ends at blank line after data or next major section
        stripped = line.strip()
        if stripped.startswith("------") or stripped.startswith("======"):
            if homo_ev is not None and lumo_ev is not None:
                break
            continue

        # Skip header lines
        if stripped.startswith("NO") or stripped.startswith("SPIN") or not stripped:
            continue

        # Parse orbital line: NO  OCC  E(Eh)  E(eV)
        parts = stripped.split()
        if len(parts) >= 4:
            try:
                occ = float(parts[1])
                e_ev = float(parts[3])
                if occ > 0.0:
                    homo_ev = e_ev  # Keep updating — last occupied is HOMO
                elif occ == 0.0 and lumo_ev is None:
                    lumo_ev = e_ev  # First unoccupied is LUMO
                    break  # Found both, done
            except (ValueError, IndexError):
                continue

    if homo_ev is not None and lumo_ev is not None:
        gap = lumo_ev - homo_ev  # gap in eV (positive = stable)
        logger.debug("HOMO-LUMO: HOMO=%.4f eV, LUMO=%.4f eV, gap=%.4f eV",
                      homo_ev, lumo_ev, gap)
        return round(gap, 4)

    logger.debug("HOMO-LUMO gap not found in ORCA output")
    return None


def _generate_orca_inp_from_smiles(
    smiles: str,
    method: str = "B3LYP",
    basis: str = "6-31G(d)",
    calc_type: str = "sp",
    charge: int = 0,
    multiplicity: int = 1,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Generate ORCA input file from a SMILES string.

    Uses RDKit ETKDGv3 for 3D embedding + MMFF/UFF optimization.

    Args:
        smiles: SMILES string.
        method: DFT method (e.g., "B3LYP", "PBE").
        basis: Basis set (e.g., "6-31G(d)", "def2-SVP").
        calc_type: "sp" (single point) or "opt" (geometry optimization).
        charge: Molecular charge (default 0).
        multiplicity: Spin multiplicity (default 1).
        output_dir: Directory for .inp file (default: system temp).

    Returns:
        Path to generated .inp file, or None on failure.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        logger.warning("RDKit not available — cannot generate ORCA input from SMILES")
        return None

    # Rule L: MolFromSmiles + None check
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("Invalid SMILES for ORCA DFT: %s", smiles)
        return None

    mol = Chem.AddHs(mol)

    # Embed 3D coordinates with ETKDGv3
    embed_params = AllChem.ETKDGv3()
    embed_result = AllChem.EmbedMolecule(mol, embed_params)
    if embed_result != 0:
        # Fallback: random seed
        embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
        if embed_result != 0:
            logger.warning("Could not generate 3D coordinates for SMILES: %s", smiles)
            return None

    # Optimize geometry with MMFF, fallback to UFF
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)  # 500 iters for better geometry
    except Exception as e:
        logger.debug("MMFF optimization failed, trying UFF: %s", e)
        try:
            AllChem.UFFOptimizeMolecule(mol, maxIters=500)
        except Exception as e:
            logger.debug("Force field optimization skipped: %s", e)

    # Build XYZ atoms block
    conf = mol.GetConformer()
    n_atoms = mol.GetNumAtoms()
    atoms_lines = []
    for i in range(n_atoms):
        pos = conf.GetAtomPosition(i)
        sym = mol.GetAtomWithIdx(i).GetSymbol()
        atoms_lines.append(f"{sym:2s}  {pos.x:12.6f}  {pos.y:12.6f}  {pos.z:12.6f}")
    atoms_block = "\n".join(atoms_lines)

    # Build ORCA input content
    # calc_type keyword
    calc_keyword = "Opt" if calc_type.lower() == "opt" else ""

    # NOTE: ORCA 6.1.0 Linux rejects non-ASCII and some Loewdin keywords.
    # Only request Mulliken population; Loewdin is printed by default anyway.
    inp_content = (
        f"! {method} {basis} {calc_keyword} TightSCF\n"
        f"%output\n"
        f"  Print[P_Mulliken] 1\n"
        f"end\n"
        f"\n"
        f"* xyz {charge} {multiplicity}\n"
        f"{atoms_block}\n"
        f"*\n"
    )

    # Write to file
    if output_dir is None:
        import tempfile
        _orca_tmp = Path("C:/tmp/chemgrid_orca") if os.name == "nt" else None
        if _orca_tmp:
            _orca_tmp.mkdir(parents=True, exist_ok=True)
        output_dir = Path(tempfile.mkdtemp(prefix="chemgrid_orca_dft_", dir=str(_orca_tmp) if _orca_tmp else None))
    output_dir.mkdir(parents=True, exist_ok=True)

    inp_path = output_dir / "orca_dft.inp"
    inp_path.write_text(inp_content, encoding="utf-8")
    logger.info("ORCA DFT input generated: %s (%d atoms, %s/%s %s)",
                inp_path, n_atoms, method, basis, calc_type)

    return inp_path


def run_orca_dft(
    smiles: str,
    method: str = "B3LYP",
    basis: str = "6-31G(d)",
    calc_type: str = "sp",
    charge: int = 0,
    multiplicity: int = 1,
    timeout: int = 300,
) -> OrcaDftResult:
    """
    Run ORCA DFT calculation from a SMILES string.

    High-level function that:
      1. Generates 3D coordinates from SMILES (RDKit ETKDGv3 + MMFF)
      2. Creates ORCA input file
      3. Executes ORCA via WSL (Linux ORCA 6.1.0) or native Windows
      4. Parses output for energy, charges, dipole, HOMO-LUMO gap

    Args:
        smiles: SMILES string for the molecule.
        method: DFT method (default "B3LYP").
        basis: Basis set (default "6-31G(d)").
        calc_type: "sp" (single point) or "opt" (geometry optimization).
        charge: Total molecular charge (default 0).
        multiplicity: Spin multiplicity (default 1).
        timeout: Maximum execution time in seconds (default 300).

    Returns:
        OrcaDftResult with energy, charges, dipole, HOMO-LUMO gap.
        On failure, OrcaDftResult.success is False with error_message.
    """
    import time

    # Rule N: validate inputs
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("run_orca_dft: empty or non-string SMILES")
        return OrcaDftResult(
            success=False,
            error_message="Empty or non-string SMILES",
            smiles=str(smiles) if smiles else "",
        )

    if not isinstance(method, str):
        method = "B3LYP"
    if not isinstance(basis, str):
        basis = "6-31G(d)"
    if not isinstance(calc_type, str):
        calc_type = "sp"
    calc_type = calc_type.lower().strip()
    if calc_type not in ("sp", "opt"):
        logger.warning("run_orca_dft: invalid calc_type '%s', using 'sp'", calc_type)
        calc_type = "sp"

    start_time = time.time()

    # Step 1: Generate ORCA input file from SMILES
    import tempfile
    work_dir = Path(tempfile.mkdtemp(prefix="chemgrid_orca_dft_"))

    inp_path = _generate_orca_inp_from_smiles(
        smiles, method=method, basis=basis, calc_type=calc_type,
        charge=charge, multiplicity=multiplicity, output_dir=work_dir,
    )
    if inp_path is None:
        return OrcaDftResult(
            success=False,
            error_message=f"Failed to generate ORCA input for SMILES: {smiles}",
            smiles=smiles, method=method, basis=basis, calc_type=calc_type,
        )

    # Count atoms from .inp file
    n_atoms = 0
    try:
        inp_text = inp_path.read_text(encoding="utf-8")
        in_xyz = False
        for line in inp_text.split("\n"):
            if line.strip().startswith("* xyz"):
                in_xyz = True
                continue
            if in_xyz:
                if line.strip() == "*":
                    break
                if line.strip():
                    n_atoms += 1
    except Exception as e:
        logger.warning("Failed to count atoms from .inp file: %s", e)

    # Step 2: Execute ORCA (WSL-first, then native fallback)
    executor = OrcaExecutor(timeout=timeout, use_wsl=True)

    try:
        out_path = executor.execute(inp_path, work_dir)
    except OrcaNotFoundError:
        # WSL ORCA not found — try native
        logger.info("WSL ORCA not found, trying native execution...")
        try:
            executor_native = OrcaExecutor(timeout=timeout, use_wsl=False)
            out_path = executor_native.execute(inp_path, work_dir)
        except OrcaError as e:
            elapsed = time.time() - start_time
            return OrcaDftResult(
                success=False,
                error_message=f"ORCA execution failed (native fallback): {e}",
                smiles=smiles, method=method, basis=basis, calc_type=calc_type,
                n_atoms=n_atoms, wall_time_s=round(elapsed, 1),
            )
    except OrcaError as e:
        elapsed = time.time() - start_time
        return OrcaDftResult(
            success=False,
            error_message=f"ORCA execution failed: {e}",
            smiles=smiles, method=method, basis=basis, calc_type=calc_type,
            n_atoms=n_atoms, wall_time_s=round(elapsed, 1),
        )

    # Step 3: Parse output
    if not out_path.exists():
        elapsed = time.time() - start_time
        return OrcaDftResult(
            success=False,
            error_message=f"ORCA output file not found: {out_path}",
            smiles=smiles, method=method, basis=basis, calc_type=calc_type,
            n_atoms=n_atoms, wall_time_s=round(elapsed, 1),
        )

    try:
        parser = OrcaOutputParser()
        orca_result = parser.parse(out_path)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.warning("ORCA output parsing failed: %s", e)
        return OrcaDftResult(
            success=False,
            error_message=f"ORCA output parsing failed: {e}",
            smiles=smiles, method=method, basis=basis, calc_type=calc_type,
            n_atoms=n_atoms, wall_time_s=round(elapsed, 1),
        )

    # Step 4: Extract additional data (dipole, HOMO-LUMO)
    try:
        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            out_lines = f.readlines()
    except Exception as e:
        logger.warning("Failed to re-read ORCA output for dipole/HOMO-LUMO: %s", e)
        out_lines = []

    dipole = _parse_orca_dipole(out_lines)
    homo_lumo_gap = _parse_orca_homo_lumo(out_lines)

    elapsed = time.time() - start_time

    # Build result
    dft_result = OrcaDftResult(
        success=True,
        energy_eh=orca_result.energy if orca_result.energy != 0.0 else None,
        homo_lumo_gap_ev=homo_lumo_gap,
        mulliken_charges=orca_result.charges_mulliken,
        dipole_debye=dipole,
        method=method,
        basis=basis,
        calc_type=calc_type,
        smiles=smiles,
        n_atoms=n_atoms,
        wall_time_s=round(elapsed, 1),
    )

    # Check if we got meaningful results
    if dft_result.energy_eh is None:
        dft_result.success = False
        dft_result.error_message = "ORCA completed but no energy found in output"
        logger.warning("ORCA DFT for '%s': no energy parsed from output", smiles)
    else:
        logger.info(
            "ORCA DFT complete: %s %s/%s %s — E=%.6f Eh, gap=%s eV, "
            "dipole=%s D, %d charges, %.1f s",
            smiles, method, basis, calc_type,
            dft_result.energy_eh,
            f"{homo_lumo_gap:.2f}" if homo_lumo_gap is not None else "N/A",
            f"{dipole:.4f}" if dipole is not None else "N/A",
            len(dft_result.mulliken_charges),
            elapsed,
        )

    # Cleanup temp directory (keep on failure for debugging)
    if dft_result.success:
        try:
            import shutil as _shutil
            _shutil.rmtree(work_dir, ignore_errors=True)
        except Exception as e:
            logger.debug("Temp dir cleanup failed: %s", e)

    return dft_result


# ============================================================================
# REMOTE ORCA CLIENT (v3.13)
# ============================================================================


class RemoteOrcaClient:
    """
    HTTP client for the ChemGrid ORCA remote server.

    When ORCA is not installed locally (e.g., student laptops),
    this client delegates DFT calculations to a remote server
    running housing/services/orca_api_server.py on a desktop PC.

    Usage:
        client = RemoteOrcaClient(os.environ.get("ORCA_SERVER_URL"))
        if client.is_available():
            result = client.calculate("c1ccccc1")
            print(result)
    """

    DEFAULT_SERVER_URL = ""

    def __init__(self, server_url: Optional[str] = None):
        env_url = (
            os.environ.get("CHEMGRID_ORCA_SERVER_URL")
            or os.environ.get("ORCA_SERVER_URL")
            or os.environ.get("ORCA_REMOTE_URL")
        )
        self.server_url = (server_url or env_url or self.DEFAULT_SERVER_URL).strip().rstrip("/")

    def is_available(self) -> bool:
        """
        Check if the remote ORCA server is reachable and has ORCA.

        Returns:
            True if server responds and reports ORCA available.
            False on any connection error (never raises).
        """
        if not self.server_url:
            logger.warning("RemoteOrcaClient.is_available: ORCA_SERVER_URL is not configured")
            return False

        old_url = os.environ.get("ORCA_SERVER_URL")
        os.environ["ORCA_SERVER_URL"] = self.server_url
        try:
            from orca_remote_client import quick_health_check  # type: ignore
            data = quick_health_check()
        except Exception as e:
            logger.warning("RemoteOrcaClient.is_available: health check failed: %s", e)
            return False
        finally:
            if old_url is None:
                os.environ.pop("ORCA_SERVER_URL", None)
            else:
                os.environ["ORCA_SERVER_URL"] = old_url

        if not isinstance(data, dict):
            logger.warning("RemoteOrcaClient.is_available: health result not dict")
            return False
        health = data.get("health")
        server_status = data.get("server_status")
        status_code = data.get("health_status_code")
        orca_exists = data.get("orca_exists", True)
        api_key_set = data.get("api_key_set", True)
        orca_available = data.get("orca_available", True)
        return (
            health == "ok"
            and server_status == "ok"
            and status_code == 200
            and orca_exists is not False
            and api_key_set is not False
            and orca_available is not False
        )

    def calculate(
        self,
        smiles: str,
        method: str = "B3LYP",
        basis: str = "6-31G(d)",
        calc_type: str = "sp",
        charge: int = 0,
        multiplicity: int = 1,
        timeout: int = 300,
    ) -> OrcaDftResult:
        """
        Submit a DFT calculation to the remote ORCA server.

        Args:
            smiles: SMILES string for the molecule.
            method: DFT method (default "B3LYP").
            basis: Basis set (default "6-31G(d)").
            calc_type: "sp" (single point) or "opt" (geometry optimization).
            charge: Molecular charge (default 0).
            multiplicity: Spin multiplicity (default 1).
            timeout: Server-side timeout in seconds (default 300).

        Returns:
            OrcaDftResult with calculation results.
            On failure, success=False with error_message.
        """
        if not self.server_url:
            logger.warning("RemoteOrcaClient.calculate: ORCA_SERVER_URL is not configured")
            return OrcaDftResult(
                success=False,
                smiles=smiles,
                method=method,
                basis=basis,
                calc_type=calc_type,
                error_message="ORCA_SERVER_URL is not configured",
            )

        old_url = os.environ.get("ORCA_SERVER_URL")
        os.environ["ORCA_SERVER_URL"] = self.server_url
        try:
            from orca_remote_client import OrcaJobRequest, poll_result, submit_job  # type: ignore
            request = OrcaJobRequest(
                smiles=smiles,
                method=method,
                basis=basis,
                job_type=calc_type,
                charge=charge,
                mult=multiplicity,
                client_id="orca_interface",
            )
            submit_timeout = max(1, min(int(timeout), 30))
            submitted = submit_job(request, timeout=submit_timeout)
            if not isinstance(submitted, dict):
                return OrcaDftResult(
                    success=False,
                    smiles=smiles,
                    method=method,
                    basis=basis,
                    calc_type=calc_type,
                    error_message="Remote ORCA submit returned non-dict response",
                )
            if submitted.get("_simulation_mode") or submitted.get("_remote_error"):
                return OrcaDftResult(
                    success=False,
                    smiles=smiles,
                    method=method,
                    basis=basis,
                    calc_type=calc_type,
                    error_message=str(submitted.get("_reason", "Remote ORCA unavailable")),
                )
            job_id = submitted.get("job_id", "")
            if not isinstance(job_id, str) or not job_id.strip():
                return OrcaDftResult(
                    success=False,
                    smiles=smiles,
                    method=method,
                    basis=basis,
                    calc_type=calc_type,
                    error_message="Remote ORCA submit returned empty job_id",
                )
            remote = poll_result(job_id, timeout=timeout)
        except Exception as e:
            logger.warning("RemoteOrcaClient.calculate: %s", e)
            return OrcaDftResult(
                success=False,
                smiles=smiles,
                method=method,
                basis=basis,
                calc_type=calc_type,
                error_message=f"Remote server connection failed: {e}",
            )
        finally:
            if old_url is None:
                os.environ.pop("ORCA_SERVER_URL", None)
            else:
                os.environ["ORCA_SERVER_URL"] = old_url

        raw = getattr(remote, "raw_response", {})
        if not isinstance(raw, dict):
            raw = {}
        if not getattr(remote, "success", False):
            return OrcaDftResult(
                success=False,
                smiles=smiles,
                method=method,
                basis=basis,
                calc_type=calc_type,
                error_message=getattr(remote, "error", "Remote ORCA failed"),
                wall_time_s=float(getattr(remote, "elapsed_seconds", 0.0) or 0.0),
            )

        # Convert response dict to OrcaDftResult.  The current server contract
        # guarantees execution evidence and energy evidence; charges may be
        # absent until the server exposes full output or a charge endpoint.
        mulliken = raw.get("mulliken_charges", {})
        # JSON keys are strings; convert back to int
        if isinstance(mulliken, dict):
            parsed_mulliken = {}
            for k, v in mulliken.items():
                try:
                    parsed_mulliken[int(k)] = float(v)
                except (TypeError, ValueError) as e:
                    logger.warning("RemoteOrcaClient.calculate: bad Mulliken item %r=%r: %s", k, v, e)
            mulliken = parsed_mulliken
        else:
            mulliken = {}

        homo_lumo_gap = None
        homo_lumo = getattr(remote, "homo_lumo_ev", None)
        if isinstance(homo_lumo, tuple) and len(homo_lumo) == 2:
            try:
                homo_lumo_gap = round(float(homo_lumo[1]) - float(homo_lumo[0]), 4)
            except (TypeError, ValueError) as e:
                logger.warning("RemoteOrcaClient.calculate: HOMO/LUMO gap conversion failed: %s", e)

        return OrcaDftResult(
            success=getattr(remote, "energy_hartree", None) is not None,
            energy_eh=getattr(remote, "energy_hartree", None),
            homo_lumo_gap_ev=homo_lumo_gap,
            mulliken_charges=mulliken,
            dipole_debye=None,
            method=method,
            basis=basis,
            calc_type=calc_type,
            smiles=smiles,
            n_atoms=0,
            wall_time_s=float(getattr(remote, "elapsed_seconds", 0.0) or 0.0),
            error_message="" if getattr(remote, "energy_hartree", None) is not None
            else "Remote ORCA completed but no numeric energy was returned",
        )


def run_orca_dft_auto(
    smiles: str,
    method: str = "B3LYP",
    basis: str = "6-31G(d)",
    calc_type: str = "sp",
    charge: int = 0,
    multiplicity: int = 1,
    timeout: int = 300,
    server_url: Optional[str] = None,
) -> OrcaDftResult:
    """
    Run ORCA DFT with portable remote-first behavior.

    Execution order:
      1. Try remote ChemGrid ORCA server via RemoteOrcaClient
      2. If remote server unavailable, optionally try local ORCA
      3. If remote and allowed local fallback are unavailable, return failure

    Args:
        smiles: SMILES string.
        method: DFT method.
        basis: Basis set.
        calc_type: "sp" or "opt".
        charge: Molecular charge.
        multiplicity: Spin multiplicity.
        timeout: Max execution time (seconds).
        server_url: Remote server URL (default: ORCA_SERVER_URL/CHEMGRID_ORCA_SERVER_URL env).

    Returns:
        OrcaDftResult from remote ORCA, or opt-in local ORCA if explicitly enabled.
    """
    local_allowed = os.environ.get("CHEMGRID_ORCA_ALLOW_LOCAL", "0") == "1"

    # Step 1: Try remote ORCA server first.  Student laptops such as LG Gram
    # must not require local ORCA/WSL installation for ChemGrid DFT features.
    client = RemoteOrcaClient(server_url)
    if client.is_available():
        logger.info("run_orca_dft_auto: remote server available at %s", client.server_url)
        remote_result = client.calculate(
            smiles=smiles, method=method, basis=basis,
            calc_type=calc_type, charge=charge,
            multiplicity=multiplicity, timeout=timeout,
        )
        if remote_result.success:
            return remote_result
        logger.warning(
            "run_orca_dft_auto: remote server calculation failed: %s",
            remote_result.error_message,
        )

    # Step 2: Local ORCA is opt-in only, so a developer workstation WSL install
    # cannot hide a broken student/remote deployment path.
    if local_allowed:
        local_orca = find_orca_wsl() or find_orca_executable()
        if local_orca:
            logger.info("run_orca_dft_auto: using opt-in local ORCA")
            return run_orca_dft(
                smiles=smiles, method=method, basis=basis,
                calc_type=calc_type, charge=charge,
                multiplicity=multiplicity, timeout=timeout,
            )

    # Step 3: Neither available
    logger.warning("run_orca_dft_auto: remote ORCA unavailable and local fallback disabled")
    return OrcaDftResult(
        success=False,
        smiles=smiles,
        method=method,
        basis=basis,
        calc_type=calc_type,
        error_message=(
            "Remote ORCA server unavailable. Set CHEMGRID_ORCA_SERVER_URL to a "
            "reachable ChemGrid ORCA server, or set CHEMGRID_ORCA_ALLOW_LOCAL=1 "
            "only for lab/developer machines."
        ),
    )


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[orca_interface.py v3.13] Portable ORCA DFT Interface + xtb GFN2-xTB (WSL) + Remote Client")
    print(f"  Script dir: {_SCRIPT_DIR}")
    print(f"  ORCA found (native): {find_orca_executable()}")
    print(f"  ORCA found (WSL):    {find_orca_wsl()}")
    xtb_exe = find_xtb_executable()
    print(f"  xtb found:  {xtb_exe} {'(WSL)' if _is_wsl_xtb(xtb_exe) else ''}")
    validate_orca_installation()
    validate_xtb_installation()

    # Remote server check
    remote = RemoteOrcaClient()
    remote_ok = remote.is_available()
    print(f"  Remote ORCA server:  {'available' if remote_ok else 'not reachable'} ({remote.server_url})")

    print("[orca_interface.py v3.13] Ready")
