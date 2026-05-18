# mechanism_dft_engine.py (v1.0 - DFT-Based Mechanism Inference via ORCA)
"""
ChemGrid: DFT 양자화학 기반 반응 메커니즘 추론 엔진

Priority chain integration:
    gold standard → hardcoded → rule engine → **DFT ENGINE** → generic fallback

규칙 엔진이 None을 반환할 때(미지의 반응 패턴), ORCA DFT 계산을 사용하여:
1. 전이 상태(TS) 탐색 — 선형 보간 또는 NEB 기반 초기 추정
2. IRC(고유 반응 좌표) — TS에서 반응물/생성물 방향으로 경로 추적
3. 중간체 추출 — IRC 경로의 에너지 극소점 = 중간체
4. 메커니즘 생성 — IRC 궤적을 MechanismData 단계로 변환

주의:
- ORCA가 설치되지 않은 환경에서는 graceful하게 None 반환
- 계산은 수 분~수 시간 소요될 수 있음 (사용자 동의 하에 실행)
- B3LYP/6-31G(d)/D3BJ 조합으로 TS 탐색, 6-311+G(2d,p)로 최종 에너지
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# RDKit availability
# ============================================================================

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolTransforms, rdmolops
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    logger.warning("RDKit not available - DFT mechanism engine features limited")

# ============================================================================
# CONSTANTS
# ============================================================================

HARTREE_TO_KCAL = 627.5094740631  # 1 Hartree = 627.5 kcal/mol
BOHR_TO_ANG = 0.529177249        # 1 Bohr = 0.529 Angstrom


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DFTConfig:
    """DFT calculation configuration.

    Attributes:
        method: DFT functional (default B3LYP — widely validated for organic reactions)
        basis_set: Basis set for geometry optimization / TS search (moderate cost)
        basis_set_fine: Basis set for final single-point energy (higher accuracy)
        dispersion: Empirical dispersion correction (D3BJ = Grimme D3 + BJ damping)
        solvent: CPCM solvent model name (empty string = gas phase)
        nprocs: Number of parallel processes for ORCA
        maxcore: Memory per core in MB
        charge: Total system charge
        multiplicity: Spin multiplicity (1 = singlet, 2 = doublet, etc.)
        do_ts_search: Whether to attempt transition state optimization
        do_irc: Whether to run IRC from TS
        do_neb: Whether to use NEB-TS (more robust, 3-5x slower than QST2)
        max_irc_steps: Maximum IRC steps per direction
        neb_images: Number of NEB images (8 is a good balance of cost/accuracy)
        timeout_sec: Maximum wall time for a single ORCA job in seconds
    """
    method: str = "B3LYP"
    basis_set: str = "6-31G(d)"
    basis_set_fine: str = "6-311+G(2d,p)"
    dispersion: str = "D3BJ"
    solvent: str = ""               # empty = gas phase
    nprocs: int = 4
    maxcore: int = 2000             # MB per core
    charge: int = 0
    multiplicity: int = 1

    # Calculation control
    do_ts_search: bool = True
    do_irc: bool = True
    do_neb: bool = False            # NEB is more robust but more expensive
    max_irc_steps: int = 50
    neb_images: int = 8             # number of images along NEB path
    timeout_sec: int = 3600         # 1 hour default timeout per job


@dataclass
class IRCPoint:
    """Single point on an IRC (Intrinsic Reaction Coordinate) path.

    Attributes:
        step: Step index along the IRC path
        energy_hartree: Absolute energy in Hartree
        energy_kcal_rel: Energy relative to the reactant-side minimum (kcal/mol)
        xyz_block: Atomic coordinates in XYZ format (atom_symbol x y z per line)
        smiles: RDKit-derived SMILES from the xyz geometry (may be None if conversion fails)
        is_minimum: True if this point is an energy minimum (intermediate or reactant/product)
        is_ts: True if this point is a transition state (energy maximum along path)
    """
    step: int
    energy_hartree: float
    energy_kcal_rel: float
    xyz_block: str
    smiles: Optional[str] = None
    is_minimum: bool = False
    is_ts: bool = False


@dataclass
class DFTMechanismResult:
    """Result of a DFT-based mechanism calculation.

    Attributes:
        success: Whether the calculation completed successfully
        method_used: Calculation approach ("TS+IRC", "NEB", "relaxed_scan")
        irc_path: Full IRC trajectory as list of IRCPoints
        intermediates: Energy minima along the path (intermediates)
        transition_states: Energy maxima along the path (transition states)
        mechanism_data: Converted MechanismData object for rendering
        energy_diagram: List of (label, relative_energy_kcal) pairs for plotting
        calculation_time_sec: Total wall time for all calculations
        orca_output_dir: Directory containing all ORCA output files
        error_message: Error description if success=False
    """
    success: bool
    method_used: str
    irc_path: List[IRCPoint] = field(default_factory=list)
    intermediates: List[IRCPoint] = field(default_factory=list)
    transition_states: List[IRCPoint] = field(default_factory=list)
    mechanism_data: object = None  # Optional[MechanismData]
    energy_diagram: List[Tuple[str, float]] = field(default_factory=list)
    calculation_time_sec: float = 0.0
    orca_output_dir: str = ""
    error_message: str = ""


# ============================================================================
# MAIN ENGINE CLASS
# ============================================================================

class MechanismDFTEngine:
    """
    DFT-based mechanism inference using ORCA quantum chemistry.

    This engine sits in the priority chain after the rule-based mechanism engine:
        gold standard → hardcoded → rule engine → **DFT ENGINE** → generic fallback

    When the rule engine cannot determine a reaction mechanism (returns None for
    unknown reaction types), this module uses actual quantum mechanical calculations:

    1. Generate 3D coordinates for reactant and product (RDKit ETKDG + MMFF)
    2. Create initial TS geometry guess (linear interpolation between R and P)
    3. Run ORCA TS optimization (OptTS with Hessian calculation)
    4. Run IRC from TS to trace the minimum energy path in both directions
    5. Identify intermediates (energy minima) and transition states (energy maxima)
    6. Convert the IRC trajectory to MechanismData format with electron-flow arrows

    This is computationally expensive (minutes to hours) but yields theoretically
    rigorous results grounded in quantum mechanics.

    Usage:
        engine = MechanismDFTEngine()
        result = engine.generate("CBr", "CO", conditions="NaOH, H2O")
        if result and result.success:
            mechanism = result.mechanism_data
    """

    def __init__(self, config: Optional[DFTConfig] = None,
                 orca_path: str = ""):
        """Initialize the DFT mechanism engine.

        Args:
            config: DFT calculation configuration. Uses defaults if None.
            orca_path: Explicit path to ORCA executable. Auto-detected if empty.
        """
        self.config = config or DFTConfig()
        self.orca_path = orca_path or self._find_orca()
        self._work_dir = ""
        self._cache = DFTMechanismCache()

    # ════════════════════════════════════════════════════════════════════
    # ORCA DISCOVERY
    # ════════════════════════════════════════════════════════════════════

    def _find_orca(self) -> str:
        """Find the ORCA executable by checking common paths and system PATH.

        Search order:
            1. ORCA_PATH environment variable (from .env or system)
            2. ChemGrid bundled ORCA (project_root/Orca.6.1.1/)
            3. Common Windows install paths
            4. Common Linux/macOS paths
            5. System PATH via shutil.which

        Returns:
            Path to ORCA executable, or empty string if not found.
        """
        # 1. Environment variable
        env_path = os.environ.get("ORCA_PATH", "")
        if env_path and os.path.isfile(env_path):
            return env_path

        # 2. Relative to this script (ChemGrid bundled ORCA)
        script_dir = Path(__file__).resolve().parent
        relative_candidates = [
            script_dir / "Orca.6.1.1" / "orca.exe",
            script_dir.parent / "Orca.6.1.1" / "orca.exe",
            script_dir.parent.parent / "Orca.6.1.1" / "orca.exe",
        ]
        for candidate in relative_candidates:
            if candidate.is_file():
                return str(candidate)

        # 3. Common absolute paths
        absolute_candidates = [
            r"C:\Orca.6.1.1\orca.exe",
            r"C:\ORCA\orca.exe",
            r"C:\Program Files\ORCA\orca.exe",
            os.path.expanduser("~/orca/orca"),
            "/usr/local/bin/orca",
            "/opt/orca/orca",
        ]
        for candidate in absolute_candidates:
            if os.path.isfile(candidate):
                return candidate

        # 4. System PATH
        import shutil
        which_orca = shutil.which("orca")
        if which_orca:
            return which_orca

        logger.info("ORCA executable not found — DFT engine will be unavailable")
        return ""

    @property
    def is_available(self) -> bool:
        """Check if ORCA is available for calculations."""
        # [M529] CHEMGRID_DISABLE_ORCA=1 환경변수 즉시 차단 — 사이클 다중 spawn 시 ORCA 폭주 방지
        if os.environ.get("CHEMGRID_DISABLE_ORCA", "0") == "1":
            logger.warning(
                "[mechanism_dft_engine] CHEMGRID_DISABLE_ORCA=1 — ORCA 호출 차단 (사용자 환경변수)"
            )
            return False
        return bool(self.orca_path) and os.path.isfile(self.orca_path)

    # ════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ════════════════════════════════════════════════════════════════════

    def generate(self, reactant_smi: str, product_smi: str,
                 conditions: str = "",
                 config_override: Optional[DFTConfig] = None
                 ) -> Optional[DFTMechanismResult]:
        """
        Main entry: DFT-based mechanism inference.

        Performs a full quantum chemical analysis of the reaction path:
        1. Generate 3D coordinates for reactant + product via RDKit
        2. Atom-atom mapping between reactant and product
        3. Transition state search (OptTS or NEB-TS)
        4. IRC from TS to trace minimum energy path
        5. Extract intermediates from energy profile
        6. Convert to MechanismData for ChemGrid rendering

        Args:
            reactant_smi: Reactant SMILES (may be multi-fragment with '.')
            product_smi: Product SMILES (may be multi-fragment with '.')
            conditions: Reaction conditions string (e.g. "NaOH, H2O, reflux")
            config_override: Override default DFT config for this calculation

        Returns:
            DFTMechanismResult with full IRC path and MechanismData,
            or None if ORCA is not available.
        """
        if not self.is_available:
            logger.debug("ORCA not available — DFT mechanism inference skipped")
            return None

        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available — cannot generate 3D coordinates")
            return None

        # N-code: type guard — external callers may pass non-str values
        if not isinstance(reactant_smi, str) or not isinstance(product_smi, str):
            logger.warning("DFT generate() received non-str SMILES: reactant=%s, product=%s",
                           type(reactant_smi).__name__, type(product_smi).__name__)
            return None
        if not isinstance(conditions, str):
            logger.warning("DFT generate() conditions is not str: type=%s, coercing", type(conditions).__name__)
            conditions = str(conditions) if conditions else ""
        if config_override is not None and not isinstance(config_override, DFTConfig):
            logger.warning("DFT generate() config_override is not DFTConfig: type=%s", type(config_override).__name__)
            config_override = None

        config = config_override or self.config
        start_time = time.time()

        # Check cache first
        cached = self._cache.get(reactant_smi, product_smi)
        if cached is not None:
            logger.info("DFT mechanism loaded from cache")
            return cached

        # Canonicalize SMILES
        r_canon = self._canonicalize(reactant_smi)
        p_canon = self._canonicalize(product_smi)
        if not r_canon or not p_canon:
            return DFTMechanismResult(
                success=False, method_used="none",
                error_message="Invalid SMILES input"
            )

        # Parse charge from conditions (e.g., "[OH-]" implies charge=-1 on nucleophile)
        charge, mult = self._determine_charge_mult(r_canon, config)

        # Create temporary working directory
        self._work_dir = tempfile.mkdtemp(prefix="chemgrid_dft_")
        logger.info(f"DFT working directory: {self._work_dir}")

        try:
            # Step 1: Generate 3D coordinates
            r_xyz = self._generate_3d_coords(r_canon)
            p_xyz = self._generate_3d_coords(p_canon)
            if not r_xyz or not p_xyz:
                return DFTMechanismResult(
                    success=False, method_used="none",
                    error_message="Failed to generate 3D coordinates",
                    orca_output_dir=self._work_dir,
                    calculation_time_sec=time.time() - start_time,
                )

            # Step 2: Atom-atom mapping
            atom_map = self._compute_atom_map(r_canon, p_canon)

            # Step 3+4: TS search + IRC (or NEB)
            if config.do_neb:
                result = self._run_neb_pathway(r_xyz, p_xyz, charge, mult, config)
            else:
                result = self._run_ts_irc_pathway(r_xyz, p_xyz, atom_map,
                                                   charge, mult, config)

            # If TS+IRC failed, try NEB as fallback
            if not result.success and not config.do_neb:
                logger.info("TS+IRC failed, falling back to NEB-TS")
                result = self._run_neb_pathway(r_xyz, p_xyz, charge, mult, config)

            # If NEB also failed, try relaxed scan as last resort
            if not result.success:
                logger.info("NEB failed, trying relaxed scan fallback")
                result = self._run_relaxed_scan_fallback(
                    r_canon, r_xyz, p_xyz, charge, mult, config
                )

            result.orca_output_dir = self._work_dir
            result.calculation_time_sec = time.time() - start_time

            # Step 5: Extract intermediates and TS from path
            if result.success and result.irc_path:
                intermediates, tss = self._identify_intermediates(result.irc_path)
                result.intermediates = intermediates
                result.transition_states = tss

                # Step 6: Convert to MechanismData
                result.mechanism_data = self._irc_to_mechanism(
                    result, r_canon, p_canon
                )

                # Build energy diagram
                result.energy_diagram = self._build_energy_diagram(result)

            # Cache successful results
            if result.success:
                self._cache.put(reactant_smi, product_smi, result)

            logger.info(
                f"DFT mechanism complete: success={result.success}, "
                f"method={result.method_used}, "
                f"time={result.calculation_time_sec:.1f}s, "
                f"intermediates={len(result.intermediates)}, "
                f"TSs={len(result.transition_states)}"
            )
            return result

        except Exception as e:
            logger.warning(f"DFT mechanism inference failed: {e}")
            return DFTMechanismResult(
                success=False, method_used="none",
                error_message=str(e),
                orca_output_dir=self._work_dir,
                calculation_time_sec=time.time() - start_time,
            )

    # ════════════════════════════════════════════════════════════════════
    # 3D COORDINATE GENERATION
    # ════════════════════════════════════════════════════════════════════

    def _generate_3d_coords(self, smiles: str) -> Optional[str]:
        """
        Convert SMILES to 3D XYZ coordinates using RDKit.

        Uses ETKDG (Experimental-Torsion Knowledge Distance Geometry) for
        conformer generation, followed by MMFF94 force field optimization
        to get a reasonable 3D geometry.

        Args:
            smiles: Valid SMILES string

        Returns:
            XYZ coordinate block (one line per atom: "SYMBOL x y z"),
            or None if embedding fails.
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning(f"RDKit cannot parse SMILES: {smiles}")
            return None

        mol = Chem.AddHs(mol)

        # ETKDG with random seed for reproducibility
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        status = AllChem.EmbedMolecule(mol, params)
        if status != 0:
            # Fallback: try without ETKDG constraints
            status = AllChem.EmbedMolecule(mol, randomSeed=42)
            if status != 0:
                logger.warning(f"3D embedding failed for: {smiles}")
                return None

        # MMFF optimization (up to 500 iterations)
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        except Exception as e:
            # UFF fallback if MMFF fails
            logger.warning("MMFF optimization failed, trying UFF: %s", e)
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            except Exception as e:
                logger.warning("Force field optimization failed for %s: %s", smiles, e)
                # Continue with un-optimized coordinates

        # Extract XYZ block
        conf = mol.GetConformer()
        lines = []
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            sym = mol.GetAtomWithIdx(i).GetSymbol()
            lines.append(f"  {sym}   {pos.x:12.8f}   {pos.y:12.8f}   {pos.z:12.8f}")

        return "\n".join(lines)

    def _canonicalize(self, smiles: str) -> str:
        """Canonicalize SMILES via RDKit. Returns empty string on failure."""
        if not RDKIT_AVAILABLE:
            return smiles
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        return Chem.MolToSmiles(mol)

    def _determine_charge_mult(self, smiles: str,
                                config: DFTConfig) -> Tuple[int, int]:
        """
        Determine total system charge and multiplicity from SMILES.

        Parses formal charges from the molecular graph. The multiplicity
        defaults to 1 (singlet) unless the config overrides it.

        Args:
            smiles: Canonical SMILES
            config: DFT configuration (may have user-specified charge/mult)

        Returns:
            (charge, multiplicity) tuple
        """
        if config.charge != 0 or config.multiplicity != 1:
            return config.charge, config.multiplicity

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return 0, 1

        charge = Chem.GetFormalCharge(mol)
        return charge, 1  # assume singlet for most organic reactions

    def _compute_atom_map(self, r_smi: str, p_smi: str) -> Dict[int, int]:
        """
        Compute atom-atom mapping between reactant and product.

        Uses RDKit's maximum common substructure (MCS) to find the
        best correspondence between atoms in reactant and product molecules.

        Args:
            r_smi: Reactant canonical SMILES
            p_smi: Product canonical SMILES

        Returns:
            Dictionary mapping reactant atom indices to product atom indices.
        """
        r_mol = Chem.MolFromSmiles(r_smi)
        p_mol = Chem.MolFromSmiles(p_smi)
        if r_mol is None or p_mol is None:
            return {}

        try:
            from rdkit.Chem import rdFMCS
            mcs_result = rdFMCS.FindMCS(
                [r_mol, p_mol],
                bondCompare=rdFMCS.BondCompare.CompareAny,
                atomCompare=rdFMCS.AtomCompare.CompareElements,
                timeout=10,  # seconds
            )
            if mcs_result.canceled or not mcs_result.smartsString:
                return {}

            mcs_mol = Chem.MolFromSmarts(mcs_result.smartsString)
            if mcs_mol is None:
                return {}

            r_match = r_mol.GetSubstructMatch(mcs_mol)
            p_match = p_mol.GetSubstructMatch(mcs_mol)

            atom_map = {}
            for i, (ri, pi) in enumerate(zip(r_match, p_match)):
                atom_map[ri] = pi

            return atom_map
        except Exception as e:
            logger.debug(f"Atom mapping failed: {e}")
            return {}

    # ════════════════════════════════════════════════════════════════════
    # TS + IRC PATHWAY
    # ════════════════════════════════════════════════════════════════════

    def _run_ts_irc_pathway(self, r_xyz: str, p_xyz: str,
                             atom_map: Dict[int, int],
                             charge: int, mult: int,
                             config: DFTConfig) -> DFTMechanismResult:
        """
        Run TS optimization followed by IRC.

        1. Create TS guess by linear interpolation of R and P coordinates
        2. Run ORCA OptTS (transition state optimization with Hessian)
        3. Run ORCA IRC in both directions from the optimized TS
        4. Parse the IRC trajectory

        Args:
            r_xyz: Reactant XYZ coordinate block
            p_xyz: Product XYZ coordinate block
            atom_map: Reactant→Product atom index mapping
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            DFTMechanismResult (may have success=False)
        """
        # 1. Create TS guess geometry
        ts_guess_xyz = self._create_ts_guess(r_xyz, p_xyz, atom_map)

        # 2. Write and run TS optimization
        ts_inp = self._write_orca_ts_input(ts_guess_xyz, charge, mult, config)
        ts_input_file = os.path.join(self._work_dir, "ts_opt.inp")
        with open(ts_input_file, "w", encoding="utf-8") as f:
            f.write(ts_inp)

        success, ts_out_file = self._run_orca(ts_input_file, config.timeout_sec)
        if not success:
            return DFTMechanismResult(
                success=False, method_used="TS+IRC",
                error_message="TS optimization failed"
            )

        # 3. Parse TS geometry from output
        ts_xyz_opt = self._parse_optimized_geometry(ts_out_file)
        if not ts_xyz_opt:
            return DFTMechanismResult(
                success=False, method_used="TS+IRC",
                error_message="Could not parse TS geometry from output"
            )

        # Verify we have exactly one imaginary frequency
        imaginary_count = self._count_imaginary_frequencies(ts_out_file)
        if imaginary_count != 1:
            logger.warning(
                f"TS has {imaginary_count} imaginary frequencies "
                f"(expected exactly 1)"
            )
            if imaginary_count == 0:
                return DFTMechanismResult(
                    success=False, method_used="TS+IRC",
                    error_message="No imaginary frequency — not a true TS"
                )

        # 4. Run IRC from TS in both directions
        if config.do_irc:
            irc_inp = self._write_orca_irc_input(ts_xyz_opt, charge, mult, config)
            irc_input_file = os.path.join(self._work_dir, "irc.inp")
            with open(irc_input_file, "w", encoding="utf-8") as f:
                f.write(irc_inp)

            success_irc, irc_out_file = self._run_orca(
                irc_input_file, config.timeout_sec
            )
            if not success_irc:
                return DFTMechanismResult(
                    success=False, method_used="TS+IRC",
                    error_message="IRC calculation failed"
                )

            irc_path = self._parse_irc_trajectory(
                os.path.dirname(irc_out_file)
            )
        else:
            # Without IRC, just return the TS point
            ts_energy = self._parse_final_energy(ts_out_file)
            irc_path = [
                IRCPoint(step=0, energy_hartree=ts_energy,
                         energy_kcal_rel=0.0, xyz_block=ts_xyz_opt,
                         is_ts=True)
            ]

        if not irc_path:
            return DFTMechanismResult(
                success=False, method_used="TS+IRC",
                error_message="IRC trajectory parsing failed"
            )

        return DFTMechanismResult(
            success=True, method_used="TS+IRC",
            irc_path=irc_path,
        )

    def _create_ts_guess(self, r_xyz: str, p_xyz: str,
                          atom_map: Dict[int, int]) -> str:
        """
        Create initial TS geometry by linear interpolation between R and P.

        For each atom, the TS guess coordinate is the midpoint (50%) between
        reactant and product positions. This is a crude but common starting
        point for TS optimization.

        If atom counts differ (e.g., associative/dissociative reactions),
        falls back to using reactant geometry as the TS guess.

        Args:
            r_xyz: Reactant XYZ block
            p_xyz: Product XYZ block
            atom_map: Reactant→Product atom index mapping

        Returns:
            XYZ block for TS guess geometry
        """
        r_lines = [l.strip() for l in r_xyz.strip().split("\n") if l.strip()]
        p_lines = [l.strip() for l in p_xyz.strip().split("\n") if l.strip()]

        if len(r_lines) != len(p_lines):
            # Different atom counts — can't interpolate, use reactant as guess
            logger.warning(
                "Atom count mismatch (R=%d, P=%d), using reactant as TS guess",
                len(r_lines), len(p_lines)
            )
            return r_xyz

        ts_lines = []
        interpolation_factor = 0.5  # midpoint between R and P

        for i, (r_line, p_line) in enumerate(zip(r_lines, p_lines)):
            r_parts = r_line.split()
            p_parts = p_line.split()

            if len(r_parts) < 4 or len(p_parts) < 4:
                ts_lines.append(r_line)
                continue

            sym = r_parts[0]
            try:
                rx, ry, rz = float(r_parts[1]), float(r_parts[2]), float(r_parts[3])
                px, py, pz = float(p_parts[1]), float(p_parts[2]), float(p_parts[3])

                # Linear interpolation
                tx = rx + interpolation_factor * (px - rx)
                ty = ry + interpolation_factor * (py - ry)
                tz = rz + interpolation_factor * (pz - rz)

                ts_lines.append(
                    f"  {sym}   {tx:12.8f}   {ty:12.8f}   {tz:12.8f}"
                )
            except (ValueError, IndexError):
                ts_lines.append(r_line)

        return "\n".join(ts_lines)

    # ════════════════════════════════════════════════════════════════════
    # ORCA INPUT GENERATION
    # ════════════════════════════════════════════════════════════════════

    def _build_method_line(self, config: DFTConfig, job_type: str) -> str:
        """Build ORCA method/keyword line.

        Args:
            config: DFT configuration
            job_type: ORCA job keyword (e.g., "OptTS Freq", "IRC", "NEB-TS")

        Returns:
            ORCA keyword line starting with '!'
        """
        parts = [config.method, config.basis_set]
        if config.dispersion:
            parts.append(config.dispersion)
        if config.solvent:
            parts.append(f"CPCM({config.solvent})")
        parts.append(job_type)
        return "! " + " ".join(parts)

    def _build_pal_block(self, config: DFTConfig) -> str:
        """Build ORCA %pal (parallelization) block."""
        return f"%pal nprocs {config.nprocs} end"

    def _build_maxcore_line(self, config: DFTConfig) -> str:
        """Build ORCA %maxcore line."""
        return f"%maxcore {config.maxcore}"

    def _write_orca_ts_input(self, ts_guess_xyz: str, charge: int,
                              mult: int, config: DFTConfig) -> str:
        """
        Generate ORCA input for transition state optimization.

        Uses OptTS with analytical or numerical Hessian calculation at the
        initial geometry. The Hessian eigenvalues guide the optimizer to
        follow the correct imaginary mode toward the saddle point.

        ORCA keywords: OptTS Freq — optimize to saddle point, then compute
        vibrational frequencies to verify exactly one imaginary frequency.

        Args:
            ts_guess_xyz: XYZ coordinate block for TS guess geometry
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            Complete ORCA input file content as string
        """
        method_line = self._build_method_line(config, "OptTS Freq")
        lines = [
            method_line,
            self._build_maxcore_line(config),
            self._build_pal_block(config),
            "",
            "%geom",
            "  Calc_Hess true      # Calculate Hessian at starting geometry",
            "  NumHess true        # Use numerical Hessian (more robust)",
            "  MaxIter 100         # Maximum optimization cycles",
            "end",
            "",
            f"* xyz {charge} {mult}",
            ts_guess_xyz,
            "*",
            "",
        ]
        return "\n".join(lines)

    def _write_orca_irc_input(self, ts_xyz: str, charge: int,
                               mult: int, config: DFTConfig) -> str:
        """
        Generate ORCA input for IRC (Intrinsic Reaction Coordinate) calculation.

        IRC traces the minimum energy path from the transition state downhill
        in both directions (toward reactant and product). This reveals the
        full reaction coordinate including any intermediates.

        Direction 'both' means ORCA will follow the imaginary mode in the
        forward direction (toward product), then restart from TS and follow
        backward (toward reactant).

        Args:
            ts_xyz: Optimized TS geometry XYZ block
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            Complete ORCA input file content
        """
        method_line = self._build_method_line(config, "IRC")
        lines = [
            method_line,
            self._build_maxcore_line(config),
            self._build_pal_block(config),
            "",
            "%irc",
            f"  MaxIter {config.max_irc_steps}",
            "  InitHess calc_numfreq   # Calculate Hessian via numerical freqs",
            "  Direction both           # Follow path in both directions from TS",
            "  PrintLevel 1             # Detailed output for trajectory parsing",
            "end",
            "",
            f"* xyz {charge} {mult}",
            ts_xyz,
            "*",
            "",
        ]
        return "\n".join(lines)

    def _write_orca_neb_input(self, r_xyz: str, p_xyz: str,
                               charge: int, mult: int,
                               config: DFTConfig) -> str:
        """
        Generate ORCA NEB-TS input for transition state search.

        NEB (Nudged Elastic Band) is more robust than QST2/OptTS for finding
        transition states, especially when the TS guess is poor. It optimizes
        a chain of images between reactant and product, with spring forces
        maintaining even spacing. The NEB-TS variant additionally refines
        the climbing image to locate the exact saddle point.

        Cost: ~3-5x more expensive than direct OptTS, but significantly
        more reliable for complex reactions.

        Args:
            r_xyz: Reactant XYZ coordinate block
            p_xyz: Product XYZ coordinate block
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            Complete ORCA input file content
        """
        method_line = self._build_method_line(config, "NEB-TS")

        # Write product geometry to separate file for NEB endpoint
        product_xyz_file = os.path.join(self._work_dir, "product.xyz")
        p_lines = [l.strip() for l in p_xyz.strip().split("\n") if l.strip()]
        with open(product_xyz_file, "w", encoding="utf-8") as f:
            f.write(f"{len(p_lines)}\n")
            f.write("Product geometry\n")
            f.write(p_xyz.strip() + "\n")

        lines = [
            method_line,
            self._build_maxcore_line(config),
            self._build_pal_block(config),
            "",
            "%neb",
            f'  Product "{product_xyz_file}"',
            f"  NImages {config.neb_images}",
            "  PrintLevel 1",
            "end",
            "",
            f"* xyz {charge} {mult}",
            r_xyz,
            "*",
            "",
        ]
        return "\n".join(lines)

    def _write_orca_scan_input(self, xyz_block: str,
                                bond_i: int, bond_j: int,
                                start_dist: float, end_dist: float,
                                n_points: int,
                                charge: int, mult: int,
                                config: DFTConfig) -> str:
        """
        Generate ORCA input for relaxed surface scan along a bond.

        Scans a bond distance from start_dist to end_dist in n_points steps,
        optimizing all other coordinates at each step. The resulting energy
        profile approximates the reaction coordinate for simple bond-breaking
        or bond-forming reactions.

        Args:
            xyz_block: Starting geometry XYZ block
            bond_i: First atom index (0-based)
            bond_j: Second atom index (0-based)
            start_dist: Starting bond distance in Angstrom
            end_dist: Ending bond distance in Angstrom
            n_points: Number of scan points
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            Complete ORCA input file content
        """
        method_line = self._build_method_line(config, "Opt")
        lines = [
            method_line,
            self._build_maxcore_line(config),
            self._build_pal_block(config),
            "",
            "%geom",
            "  Scan",
            f"    B {bond_i} {bond_j} = {start_dist:.4f}, {end_dist:.4f}, {n_points}",
            "  end",
            "end",
            "",
            f"* xyz {charge} {mult}",
            xyz_block,
            "*",
            "",
        ]
        return "\n".join(lines)

    def _write_orca_sp_input(self, xyz_block: str, charge: int,
                              mult: int, config: DFTConfig) -> str:
        """
        Generate ORCA input for single-point energy calculation.

        Uses the fine basis set for higher accuracy on a pre-optimized geometry.

        Args:
            xyz_block: Geometry XYZ block
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            Complete ORCA input file content
        """
        parts = [config.method, config.basis_set_fine]
        if config.dispersion:
            parts.append(config.dispersion)
        if config.solvent:
            parts.append(f"CPCM({config.solvent})")
        method_line = "! " + " ".join(parts)

        lines = [
            method_line,
            self._build_maxcore_line(config),
            self._build_pal_block(config),
            "",
            f"* xyz {charge} {mult}",
            xyz_block,
            "*",
            "",
        ]
        return "\n".join(lines)

    # ════════════════════════════════════════════════════════════════════
    # ORCA EXECUTION
    # ════════════════════════════════════════════════════════════════════

    def _run_orca(self, input_file: str,
                   timeout_sec: int = 3600) -> Tuple[bool, str]:
        """
        Execute an ORCA calculation.

        Runs the ORCA executable as a subprocess with the given input file.
        Captures stdout/stderr, enforces a timeout, and checks for successful
        termination.

        Args:
            input_file: Absolute path to ORCA .inp file
            timeout_sec: Maximum wall time in seconds (default: 3600 = 1 hour)

        Returns:
            (success: bool, output_file_path: str)
            output_file_path is the .out file (same name as .inp but .out extension)
        """
        # [M529] CHEMGRID_DISABLE_ORCA=1 재진입 차단 — _run_orca 진입부에서 이중 방어
        if os.environ.get("CHEMGRID_DISABLE_ORCA", "0") == "1":
            logger.warning(
                "[mechanism_dft_engine] CHEMGRID_DISABLE_ORCA=1 — _run_orca 호출 차단"
            )
            return False, ""

        output_file = input_file.replace(".inp", ".out")

        cmd = [self.orca_path, input_file]
        logger.info(f"Running ORCA: {' '.join(cmd)}")

        try:
            with open(output_file, "w", encoding="utf-8") as out_f:
                proc = subprocess.run(
                    cmd,
                    stdout=out_f,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_sec,
                    cwd=os.path.dirname(input_file),
                )

            if proc.returncode != 0:
                logger.warning(f"ORCA returned non-zero exit code: {proc.returncode}")
                return False, output_file

            # Check for "ORCA TERMINATED NORMALLY" in output
            if os.path.isfile(output_file):
                with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if "ORCA TERMINATED NORMALLY" in content:
                    logger.info("ORCA terminated normally")
                    return True, output_file
                elif "ORCA TERMINATED WITH ERROR" in content:
                    logger.warning("ORCA terminated with error")
                    return False, output_file

            # If we can't find termination string, assume success if exit code 0
            return proc.returncode == 0, output_file

        except subprocess.TimeoutExpired:
            logger.warning(f"ORCA timed out after {timeout_sec}s")
            return False, output_file
        except FileNotFoundError:
            logger.warning(f"ORCA executable not found: {self.orca_path}")
            return False, output_file
        except Exception as e:
            logger.warning(f"ORCA execution error: {e}")
            return False, output_file

    # ════════════════════════════════════════════════════════════════════
    # OUTPUT PARSING
    # ════════════════════════════════════════════════════════════════════

    def _parse_optimized_geometry(self, output_file: str) -> Optional[str]:
        """
        Parse the final optimized geometry from an ORCA output file.

        Looks for the "CARTESIAN COORDINATES (ANGSTROEM)" section after
        geometry optimization convergence.

        Args:
            output_file: Path to ORCA .out file

        Returns:
            XYZ coordinate block, or None if parsing fails.
        """
        if not os.path.isfile(output_file):
            logger.warning("ORCA 출력 파일 없음: %s", output_file)
            return None

        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            logger.warning("Failed to read ORCA output file %s: %s", output_file, e)
            return None

        # Find last occurrence of CARTESIAN COORDINATES (ANGSTROEM)
        last_geom_start = -1
        for i, line in enumerate(lines):
            if "CARTESIAN COORDINATES (ANGSTROEM)" in line:
                last_geom_start = i

        if last_geom_start < 0:
            logger.warning("ORCA 출력에서 좌표 블록 없음: %s", output_file)
            return None

        # Parse coordinates (skip header lines)
        xyz_lines = []
        for line in lines[last_geom_start + 2:]:  # skip header + dashes
            stripped = line.strip()
            if not stripped or stripped.startswith("-"):
                if xyz_lines:
                    break
                continue
            parts = stripped.split()
            if len(parts) >= 4:
                try:
                    sym = parts[0]
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    xyz_lines.append(f"  {sym}   {x:12.8f}   {y:12.8f}   {z:12.8f}")
                except (ValueError, IndexError):
                    break

        return "\n".join(xyz_lines) if xyz_lines else None

    def _parse_final_energy(self, output_file: str) -> float:
        """
        Parse the final total energy from an ORCA output file.

        Looks for "FINAL SINGLE POINT ENERGY" line.

        Args:
            output_file: Path to ORCA .out file

        Returns:
            Energy in Hartree, or 0.0 if parsing fails.
        """
        if not os.path.isfile(output_file):
            return 0.0

        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                for line in reversed(f.readlines()):
                    if "FINAL SINGLE POINT ENERGY" in line:
                        parts = line.strip().split()
                        return float(parts[-1])
        except Exception as e:
            logger.warning("Failed to extract single point energy from %s: %s", output_file, e)
        return 0.0

    def _count_imaginary_frequencies(self, output_file: str) -> int:
        """
        Count imaginary vibrational frequencies in ORCA output.

        A true transition state has exactly one imaginary frequency
        (negative value in ORCA's frequency listing).

        Args:
            output_file: Path to ORCA .out file

        Returns:
            Number of imaginary (negative) frequencies found.
        """
        if not os.path.isfile(output_file):
            return -1  # unknown

        count = 0
        in_freq_section = False
        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "VIBRATIONAL FREQUENCIES" in line:
                        in_freq_section = True
                        continue
                    if in_freq_section:
                        if line.strip() == "" or "---" in line:
                            if count > 0 or "NORMAL MODES" in line:
                                break
                            continue
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            try:
                                freq = float(parts[1])
                                if freq < -50.0:
                                    # Ignore very small imaginary freqs (numerical noise)
                                    count += 1
                            except ValueError as e:
                                logger.warning("Failed to parse frequency value: %s", e)
        except Exception as e:
            logger.warning("Failed to count imaginary frequencies: %s", e)
            return -1
        return count

    def _parse_irc_trajectory(self, output_dir: str) -> List[IRCPoint]:
        """
        Parse ORCA IRC output files to extract the full trajectory.

        ORCA IRC generates:
        - *_IRC_Full_trj.xyz: Full trajectory in multi-frame XYZ format
        - *.out: Contains energies at each IRC step

        The trajectory is ordered from the backward (reactant-side) end
        through the TS to the forward (product-side) end.

        Args:
            output_dir: Directory containing ORCA IRC output files

        Returns:
            List of IRCPoints ordered along the reaction coordinate.
        """
        points: List[IRCPoint] = []

        # Find trajectory XYZ file
        trj_files = [f for f in os.listdir(output_dir)
                      if f.endswith("_IRC_Full_trj.xyz")]
        if not trj_files:
            # Try alternate naming
            trj_files = [f for f in os.listdir(output_dir)
                          if "trj" in f.lower() and f.endswith(".xyz")]

        # Find output file for energies
        out_files = [f for f in os.listdir(output_dir)
                      if f.endswith(".out") and "irc" in f.lower()]
        if not out_files:
            out_files = [f for f in os.listdir(output_dir) if f.endswith(".out")]

        # Parse energies from output
        energies: List[float] = []
        if out_files:
            out_path = os.path.join(output_dir, out_files[0])
            energies = self._parse_irc_energies(out_path)

        # Parse geometries from trajectory file
        if trj_files:
            trj_path = os.path.join(output_dir, trj_files[0])
            frames = self._parse_multi_xyz(trj_path)

            for i, xyz_block in enumerate(frames):
                energy = energies[i] if i < len(energies) else 0.0
                points.append(IRCPoint(
                    step=i,
                    energy_hartree=energy,
                    energy_kcal_rel=0.0,  # calculated below
                    xyz_block=xyz_block,
                    smiles=self._xyz_to_smiles(xyz_block),
                ))

        # Calculate relative energies (referenced to first point = reactant side)
        if points:
            ref_energy = points[0].energy_hartree
            for pt in points:
                pt.energy_kcal_rel = (pt.energy_hartree - ref_energy) * HARTREE_TO_KCAL

        return points

    def _parse_irc_energies(self, output_file: str) -> List[float]:
        """Parse IRC step energies from ORCA output.

        Looks for lines like:
            IRC step   X ...  E= -XXX.XXXXXXXX

        Args:
            output_file: Path to ORCA .out file

        Returns:
            List of energies in Hartree, ordered by IRC step.
        """
        energies = []
        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    # Pattern: "IRC step" followed by energy
                    if "IRC step" in line or "CURRENT ENERGY" in line:
                        # Try to extract energy from line
                        match = re.search(r"E\s*=\s*(-?\d+\.\d+)", line)
                        if match:
                            energies.append(float(match.group(1)))
                    elif "FINAL SINGLE POINT ENERGY" in line:
                        parts = line.strip().split()
                        try:
                            energies.append(float(parts[-1]))
                        except (ValueError, IndexError) as e:
                            logger.warning("Failed to parse IRC energy value: %s", e)
        except Exception as e:
            logger.debug(f"Error parsing IRC energies: {e}")
        return energies

    def _parse_multi_xyz(self, xyz_file: str) -> List[str]:
        """
        Parse a multi-frame XYZ file into individual coordinate blocks.

        Multi-frame XYZ format:
            N           (number of atoms)
            comment     (comment line)
            SYM x y z   (repeated N times)
            N           (next frame)
            ...

        Args:
            xyz_file: Path to multi-frame XYZ file

        Returns:
            List of XYZ coordinate blocks (one per frame).
        """
        frames = []
        try:
            with open(xyz_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            logger.warning("Failed to read multi-XYZ file %s: %s", xyz_file, e)
            return frames

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            try:
                n_atoms = int(line)
            except ValueError:
                i += 1
                continue

            # Skip comment line
            i += 2  # skip atom count + comment
            if i + n_atoms > len(lines):
                break

            coord_lines = []
            for j in range(n_atoms):
                if i + j < len(lines):
                    parts = lines[i + j].strip().split()
                    if len(parts) >= 4:
                        sym = parts[0]
                        x, y, z = parts[1], parts[2], parts[3]
                        coord_lines.append(f"  {sym}   {x}   {y}   {z}")

            if coord_lines:
                frames.append("\n".join(coord_lines))
            i += n_atoms

        return frames

    # ════════════════════════════════════════════════════════════════════
    # NEB PATHWAY
    # ════════════════════════════════════════════════════════════════════

    def _run_neb_pathway(self, r_xyz: str, p_xyz: str,
                          charge: int, mult: int,
                          config: DFTConfig) -> DFTMechanismResult:
        """
        Run NEB-TS pathway for transition state search.

        NEB (Nudged Elastic Band) simultaneously optimizes a chain of
        molecular images between reactant and product. The climbing image
        variant (NEB-CI or NEB-TS in ORCA) drives the highest-energy image
        toward the true saddle point.

        This is 3-5x more expensive than direct TS optimization but is
        significantly more robust for reactions where the TS guess is poor.

        Args:
            r_xyz: Reactant XYZ coordinate block
            p_xyz: Product XYZ coordinate block
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            DFTMechanismResult with the NEB path as irc_path
        """
        neb_inp = self._write_orca_neb_input(r_xyz, p_xyz, charge, mult, config)
        neb_input_file = os.path.join(self._work_dir, "neb.inp")
        with open(neb_input_file, "w", encoding="utf-8") as f:
            f.write(neb_inp)

        success, neb_out_file = self._run_orca(neb_input_file, config.timeout_sec)
        if not success:
            return DFTMechanismResult(
                success=False, method_used="NEB",
                error_message="NEB-TS calculation failed"
            )

        path = self._parse_neb_trajectory(os.path.dirname(neb_out_file))
        if not path:
            return DFTMechanismResult(
                success=False, method_used="NEB",
                error_message="NEB trajectory parsing failed"
            )

        return DFTMechanismResult(
            success=True, method_used="NEB",
            irc_path=path,
        )

    def _parse_neb_trajectory(self, output_dir: str) -> List[IRCPoint]:
        """
        Parse ORCA NEB output to extract the converged path.

        ORCA NEB generates:
        - *_NEB-TS_converged.xyz: Final optimized path images
        - *.interp: Interpolated path with energies
        - *.out: Detailed output with per-image energies

        Args:
            output_dir: Directory containing ORCA NEB output files

        Returns:
            List of IRCPoints along the NEB path.
        """
        points: List[IRCPoint] = []

        # Find converged trajectory
        conv_files = [f for f in os.listdir(output_dir)
                       if "converged" in f.lower() and f.endswith(".xyz")]
        if not conv_files:
            # Try the interpolated path
            conv_files = [f for f in os.listdir(output_dir)
                           if f.endswith(".interp") or
                           ("neb" in f.lower() and f.endswith(".xyz"))]

        # Find energies from .out or .interp
        out_files = [f for f in os.listdir(output_dir)
                      if f.endswith(".out") and "neb" in f.lower()]
        if not out_files:
            out_files = [f for f in os.listdir(output_dir)
                          if f.endswith(".out")]

        energies: List[float] = []
        if out_files:
            out_path = os.path.join(output_dir, out_files[0])
            energies = self._parse_neb_energies(out_path)

        # Parse geometries
        if conv_files:
            trj_path = os.path.join(output_dir, conv_files[0])
            frames = self._parse_multi_xyz(trj_path)

            for i, xyz_block in enumerate(frames):
                energy = energies[i] if i < len(energies) else 0.0
                points.append(IRCPoint(
                    step=i,
                    energy_hartree=energy,
                    energy_kcal_rel=0.0,
                    xyz_block=xyz_block,
                    smiles=self._xyz_to_smiles(xyz_block),
                ))

        # Calculate relative energies
        if points:
            ref_energy = points[0].energy_hartree
            for pt in points:
                pt.energy_kcal_rel = (pt.energy_hartree - ref_energy) * HARTREE_TO_KCAL

        return points

    def _parse_neb_energies(self, output_file: str) -> List[float]:
        """Parse NEB image energies from ORCA output.

        Looks for the NEB summary table with per-image energies.

        Args:
            output_file: Path to ORCA .out file

        Returns:
            List of energies in Hartree for each NEB image.
        """
        energies = []
        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                in_summary = False
                for line in f:
                    if "PATH SUMMARY" in line or "Images" in line:
                        in_summary = True
                        continue
                    if in_summary:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            try:
                                _ = int(parts[0])  # image index
                                energy = float(parts[1])
                                energies.append(energy)
                            except ValueError:
                                if energies:
                                    break
        except Exception as e:
            logger.debug(f"Error parsing NEB energies: {e}")
        return energies

    # ════════════════════════════════════════════════════════════════════
    # RELAXED SCAN FALLBACK
    # ════════════════════════════════════════════════════════════════════

    def _run_relaxed_scan_fallback(self, r_smi: str, r_xyz: str, p_xyz: str,
                                     charge: int, mult: int,
                                     config: DFTConfig) -> DFTMechanismResult:
        """
        Last-resort fallback: relaxed surface scan along the most-changed bond.

        When both TS+IRC and NEB fail, this method identifies the bond that
        changes most between reactant and product, then performs a relaxed
        scan along that coordinate. This gives an approximate energy profile
        but cannot locate precise saddle points.

        Args:
            r_smi: Reactant SMILES (for identifying reactive bonds)
            r_xyz: Reactant XYZ coordinate block
            p_xyz: Product XYZ coordinate block
            charge: System charge
            mult: Spin multiplicity
            config: DFT configuration

        Returns:
            DFTMechanismResult with the scan path as irc_path
        """
        # Identify the most-changed bond
        bond_info = self._find_reactive_bond(r_smi, r_xyz, p_xyz)
        if bond_info is None:
            return DFTMechanismResult(
                success=False, method_used="relaxed_scan",
                error_message="Could not identify reactive bond for scan"
            )

        bond_i, bond_j, start_dist, end_dist = bond_info
        n_points = 20  # 20 scan points along the coordinate

        scan_inp = self._write_orca_scan_input(
            r_xyz, bond_i, bond_j, start_dist, end_dist,
            n_points, charge, mult, config
        )
        scan_input_file = os.path.join(self._work_dir, "scan.inp")
        with open(scan_input_file, "w", encoding="utf-8") as f:
            f.write(scan_inp)

        success, scan_out_file = self._run_orca(scan_input_file, config.timeout_sec)
        if not success:
            return DFTMechanismResult(
                success=False, method_used="relaxed_scan",
                error_message="Relaxed scan calculation failed"
            )

        # Parse scan trajectory
        scan_dir = os.path.dirname(scan_out_file)
        trj_files = [f for f in os.listdir(scan_dir)
                      if f.endswith("_trj.xyz") or f.endswith("_Scan.xyz")]

        points: List[IRCPoint] = []
        if trj_files:
            frames = self._parse_multi_xyz(
                os.path.join(scan_dir, trj_files[0])
            )
            energies = self._parse_scan_energies(scan_out_file)

            for i, xyz_block in enumerate(frames):
                energy = energies[i] if i < len(energies) else 0.0
                points.append(IRCPoint(
                    step=i,
                    energy_hartree=energy,
                    energy_kcal_rel=0.0,
                    xyz_block=xyz_block,
                    smiles=self._xyz_to_smiles(xyz_block),
                ))

        if points:
            ref_energy = points[0].energy_hartree
            for pt in points:
                pt.energy_kcal_rel = (
                    (pt.energy_hartree - ref_energy) * HARTREE_TO_KCAL
                )

        return DFTMechanismResult(
            success=bool(points),
            method_used="relaxed_scan",
            irc_path=points,
            error_message="" if points else "No scan points parsed"
        )

    def _find_reactive_bond(self, r_smi: str, r_xyz: str,
                             p_xyz: str) -> Optional[Tuple[int, int, float, float]]:
        """
        Identify the bond that changes most between reactant and product.

        Compares interatomic distances between corresponding atoms in R and P.
        The bond with the largest distance change is assumed to be the
        reactive bond (either breaking or forming).

        Args:
            r_smi: Reactant SMILES (for bond topology)
            r_xyz: Reactant XYZ block
            p_xyz: Product XYZ block

        Returns:
            (atom_i, atom_j, start_distance, end_distance) or None
        """
        r_coords = self._parse_xyz_coords(r_xyz)
        p_coords = self._parse_xyz_coords(p_xyz)

        if len(r_coords) != len(p_coords) or len(r_coords) < 2:
            logger.warning("스캔 좌표 불일치: r_coords=%d, p_coords=%d", len(r_coords), len(p_coords))
            return None

        # Find the pair with largest distance change
        max_delta = 0.0
        best_pair = None

        mol = Chem.MolFromSmiles(r_smi)
        if mol is None:
            logger.warning("스캔 좌표 분석 실패 - SMILES 파싱 실패: %s", r_smi)
            return None
        mol = Chem.AddHs(mol)

        # Check bonds in reactant
        for bond in mol.GetBonds():
            i = bond.GetBeginAtomIdx()
            j = bond.GetEndAtomIdx()
            if i >= len(r_coords) or j >= len(p_coords):
                continue
            if i >= len(p_coords) or j >= len(p_coords):
                continue

            r_dist = self._distance(r_coords[i], r_coords[j])
            p_dist = self._distance(p_coords[i], p_coords[j])
            delta = abs(p_dist - r_dist)

            if delta > max_delta:
                max_delta = delta
                best_pair = (i, j, r_dist, p_dist)

        return best_pair if max_delta > 0.3 else None  # 0.3 Å threshold

    def _parse_xyz_coords(self, xyz_block: str) -> List[Tuple[float, float, float]]:
        """Parse XYZ block into list of (x, y, z) tuples."""
        coords = []
        for line in xyz_block.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 4:
                try:
                    coords.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except (ValueError, IndexError) as e:
                    logger.warning("Failed to parse XYZ coordinate line: %s", e)
        return coords

    @staticmethod
    def _distance(a: Tuple[float, float, float],
                   b: Tuple[float, float, float]) -> float:
        """Euclidean distance between two 3D points."""
        return ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5

    def _parse_scan_energies(self, output_file: str) -> List[float]:
        """Parse relaxed scan energies from ORCA output."""
        energies = []
        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "FINAL SINGLE POINT ENERGY" in line:
                        parts = line.strip().split()
                        try:
                            energies.append(float(parts[-1]))
                        except (ValueError, IndexError) as e:
                            logger.warning("Failed to parse scan energy value: %s", e)
        except Exception as e:
            logger.warning("Failed to parse scan energies from %s: %s", output_file, e)
        return energies

    # ════════════════════════════════════════════════════════════════════
    # ANALYSIS: INTERMEDIATES & TS IDENTIFICATION
    # ════════════════════════════════════════════════════════════════════

    def _identify_intermediates(self,
                                 irc_path: List[IRCPoint]
                                 ) -> Tuple[List[IRCPoint], List[IRCPoint]]:
        """
        Identify intermediates (energy minima) and transition states (energy
        maxima) from the IRC path by numerical differentiation.

        Uses a simple first-derivative sign change criterion:
        - Sign change from positive to negative → local maximum (TS)
        - Sign change from negative to positive → local minimum (intermediate)

        The first and last points are always classified as minima
        (reactant and product endpoints).

        Args:
            irc_path: Ordered list of IRCPoints along the reaction coordinate

        Returns:
            (intermediates, transition_states) — both as lists of IRCPoints
            with is_minimum/is_ts flags set appropriately.
        """
        if len(irc_path) < 3:
            return irc_path[:], []

        intermediates: List[IRCPoint] = []
        transition_states: List[IRCPoint] = []

        # First point = reactant endpoint (minimum)
        irc_path[0].is_minimum = True
        intermediates.append(irc_path[0])

        # Scan for sign changes in energy gradient
        for i in range(1, len(irc_path) - 1):
            e_prev = irc_path[i - 1].energy_kcal_rel
            e_curr = irc_path[i].energy_kcal_rel
            e_next = irc_path[i + 1].energy_kcal_rel

            grad_before = e_curr - e_prev
            grad_after = e_next - e_curr

            # Local maximum (TS): energy rises then falls
            if grad_before > 0.5 and grad_after < -0.5:  # 0.5 kcal/mol threshold
                irc_path[i].is_ts = True
                transition_states.append(irc_path[i])

            # Local minimum (intermediate): energy falls then rises
            elif grad_before < -0.5 and grad_after > 0.5:
                irc_path[i].is_minimum = True
                intermediates.append(irc_path[i])

        # Last point = product endpoint (minimum)
        irc_path[-1].is_minimum = True
        intermediates.append(irc_path[-1])

        return intermediates, transition_states

    # ════════════════════════════════════════════════════════════════════
    # XYZ TO SMILES CONVERSION
    # ════════════════════════════════════════════════════════════════════

    def _xyz_to_smiles(self, xyz_block: str) -> Optional[str]:
        """
        Convert XYZ coordinates to SMILES string.

        This is the most challenging step — inferring molecular connectivity
        from 3D coordinates. Uses a distance-based heuristic approach:

        1. Parse atom symbols and coordinates
        2. For each atom pair, check if the distance is within covalent
           bonding range (sum of covalent radii * tolerance factor)
        3. Build an RDKit molecule from the inferred connectivity
        4. Generate canonical SMILES

        Limitations:
        - May not correctly handle bond orders (single/double/triple)
        - Charged species and radicals may be misassigned
        - Works best for closed-shell organic molecules

        Args:
            xyz_block: XYZ coordinate block (atom_symbol x y z per line)

        Returns:
            Canonical SMILES string, or None if conversion fails.
        """
        if not RDKIT_AVAILABLE:
            logger.warning("xyz_to_smiles: RDKit 미사용 - XYZ→SMILES 변환 불가")
            return None

        # Covalent radii in Angstrom (approximate) for bond detection
        COVALENT_RADII = {
            'H': 0.31, 'He': 0.28,
            'Li': 1.28, 'Be': 0.96, 'B': 0.84, 'C': 0.76, 'N': 0.71,
            'O': 0.66, 'F': 0.57, 'Ne': 0.58,
            'Na': 1.66, 'Mg': 1.41, 'Al': 1.21, 'Si': 1.11, 'P': 1.07,
            'S': 1.05, 'Cl': 1.02, 'Ar': 1.06,
            'Br': 1.20, 'I': 1.39,
        }
        BOND_TOLERANCE = 1.3  # factor above sum of covalent radii

        atoms = []
        coords = []
        for line in xyz_block.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 4:
                try:
                    atoms.append(parts[0])
                    coords.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except (ValueError, IndexError):
                    continue

        if not atoms:
            logger.warning("xyz_to_smiles: XYZ 블록에서 원자 파싱 실패")
            return None

        n = len(atoms)

        try:
            # Build editable molecule
            emol = Chem.RWMol()

            # Add atoms
            for sym in atoms:
                atom = Chem.Atom(sym)
                emol.AddAtom(atom)

            # Add bonds based on distance criterion
            for i in range(n):
                r_i = COVALENT_RADII.get(atoms[i], 0.77)
                for j in range(i + 1, n):
                    r_j = COVALENT_RADII.get(atoms[j], 0.77)
                    dist = self._distance(coords[i], coords[j])
                    max_bond_dist = (r_i + r_j) * BOND_TOLERANCE

                    if dist < max_bond_dist:
                        emol.AddBond(i, j, Chem.BondType.SINGLE)

            # Try to sanitize and generate SMILES
            try:
                Chem.SanitizeMol(emol)
                smiles = Chem.MolToSmiles(emol)
                return smiles
            except Exception as e:
                # If sanitization fails, try removing problematic bonds
                logger.warning("Molecule sanitization failed: %s", e)
                return None

        except Exception as e:
            logger.debug(f"xyz_to_smiles failed: {e}")
            return None

    # ════════════════════════════════════════════════════════════════════
    # MECHANISM DATA CONVERSION
    # ════════════════════════════════════════════════════════════════════

    def _irc_to_mechanism(self, result: DFTMechanismResult,
                           reactant_smi: str, product_smi: str
                           ) -> object:
        """
        Convert IRC/NEB result to MechanismData format for ChemGrid rendering.

        For each pair of consecutive intermediates:
        - The path between them is one "step" of the mechanism
        - Bond changes between the two structures determine electron flow
        - ArrowData objects are generated from bond changes

        Args:
            result: DFT calculation result with irc_path, intermediates, TSs
            reactant_smi: Original reactant SMILES
            product_smi: Original product SMILES

        Returns:
            MechanismData object, or None if conversion fails.
        """
        try:
            from reaction_mechanisms import MechanismData, MechanismStep, ArrowData
        except ImportError:
            logger.warning("Cannot import MechanismData — mechanism conversion skipped")
            return None

        if not result.intermediates:
            logger.warning("DFT→MechanismData 변환 실패: 중간체 없음")
            return None

        steps: List[MechanismStep] = []

        # Build steps from consecutive intermediates
        for i in range(len(result.intermediates) - 1):
            inter_start = result.intermediates[i]
            inter_end = result.intermediates[i + 1]

            # Use SMILES from IRC points, fall back to input SMILES
            start_smi = inter_start.smiles or (
                reactant_smi if i == 0 else f"intermediate_{i}"
            )
            end_smi = inter_end.smiles or (
                product_smi if i == len(result.intermediates) - 2
                else f"intermediate_{i+1}"
            )

            # Find the TS between these intermediates
            ts_energy = 0.0
            for ts in result.transition_states:
                if inter_start.step < ts.step < inter_end.step:
                    ts_energy = ts.energy_kcal_rel
                    break

            # Generate arrows from bond changes
            arrows = self._estimate_arrows_from_bond_changes(start_smi, end_smi)

            # Energy label
            barrier = ts_energy - inter_start.energy_kcal_rel
            energy_label = f"ΔG‡ ≈ {barrier:.1f} kcal/mol" if barrier > 0 else ""

            step = MechanismStep(
                step_number=i + 1,
                title=self._describe_step(start_smi, end_smi, i + 1),
                description=(
                    f"DFT-computed step: {start_smi} → {end_smi}\n"
                    f"Activation barrier: {barrier:.1f} kcal/mol\n"
                    f"Method: {result.method_used} ({self.config.method}/"
                    f"{self.config.basis_set})"
                ),
                reactant_smiles=start_smi,
                product_smiles=end_smi,
                arrows=arrows,
                is_transition_state=False,
                energy_label=energy_label,
            )
            steps.append(step)

        if not steps:
            logger.warning("DFT→MechanismData 변환 실패: 단계 생성 실패")
            return None

        mechanism = MechanismData(
            mechanism_type="dft_computed",
            title=f"DFT Mechanism: {reactant_smi} → {product_smi}",
            total_steps=len(steps),
            steps=steps,
            energy_diagram=result.energy_diagram,
            overall_description=(
                f"Mechanism inferred from DFT calculation "
                f"({result.method_used}, {self.config.method}/{self.config.basis_set}). "
                f"Found {len(result.intermediates)} stationary points and "
                f"{len(result.transition_states)} transition state(s). "
                f"Total calculation time: {result.calculation_time_sec:.1f}s."
            ),
        )
        return mechanism

    def _estimate_arrows_from_bond_changes(self, smi1: str,
                                             smi2: str) -> list:
        """
        Compare two consecutive intermediates to determine electron flow.

        Identifies bonds that are broken (present in smi1, absent in smi2)
        and bonds that are formed (absent in smi1, present in smi2).
        Converts these changes to ArrowData objects representing curved
        electron-pushing arrows.

        Args:
            smi1: SMILES of the starting structure
            smi2: SMILES of the ending structure

        Returns:
            List of ArrowData objects (may be empty if SMILES are invalid
            or no bond changes detected).
        """
        try:
            from reaction_mechanisms import ArrowData
        except ImportError:
            logger.warning("reaction_mechanisms 모듈 미사용 - 화살표 데이터 생성 불가")
            return []

        mol1 = Chem.MolFromSmiles(smi1) if RDKIT_AVAILABLE else None
        mol2 = Chem.MolFromSmiles(smi2) if RDKIT_AVAILABLE else None

        if mol1 is None or mol2 is None:
            logger.warning("DFT 화살표 생성 실패 - SMILES 파싱 실패: smi1=%s, smi2=%s", smi1, smi2)
            return []

        # Get bond sets for each molecule
        bonds1 = set()
        for bond in mol1.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            bonds1.add((min(i, j), max(i, j)))

        bonds2 = set()
        for bond in mol2.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            bonds2.add((min(i, j), max(i, j)))

        broken_bonds = bonds1 - bonds2
        formed_bonds = bonds2 - bonds1

        arrows = []

        # Broken bonds → electron flow away from bond
        for (i, j) in broken_bonds:
            # Electrons flow from bond to the more electronegative atom
            arrows.append(ArrowData(
                arrow_type="full",
                from_type="bond",
                from_label=f"σ({i}-{j})",
                to_type="atom",
                to_label=f"atom {j}",
                from_atom_idx=i,
                to_atom_idx=j,
                color="#E53935",
                curvature=0.3,
            ))

        # Formed bonds → electron flow toward new bond
        for (i, j) in formed_bonds:
            arrows.append(ArrowData(
                arrow_type="full",
                from_type="lone_pair",
                from_label=f"lone pair on {i}",
                to_type="bond",
                to_label=f"σ*({i}-{j})",
                from_atom_idx=i,
                to_atom_idx=j,
                color="#1E88E5",
                curvature=0.3,
            ))

        return arrows

    def _describe_step(self, start_smi: str, end_smi: str,
                        step_num: int) -> str:
        """Generate a human-readable title for a mechanism step."""
        if "intermediate" in start_smi or "intermediate" in end_smi:
            return f"Step {step_num}: DFT-computed transformation"

        mol1 = Chem.MolFromSmiles(start_smi) if RDKIT_AVAILABLE else None
        mol2 = Chem.MolFromSmiles(end_smi) if RDKIT_AVAILABLE else None

        if mol1 is None or mol2 is None:
            return f"Step {step_num}: DFT-computed transformation"

        # Count atoms to describe the transformation
        n1 = mol1.GetNumAtoms()
        n2 = mol2.GetNumAtoms()

        if n2 > n1:
            return f"Step {step_num}: Bond formation"
        elif n2 < n1:
            return f"Step {step_num}: Bond cleavage / fragmentation"
        else:
            return f"Step {step_num}: Rearrangement"

    def _build_energy_diagram(self,
                               result: DFTMechanismResult
                               ) -> List[Tuple[str, float]]:
        """
        Build energy diagram data from IRC path for plotting.

        Returns a list of (label, relative_energy_kcal) tuples suitable
        for rendering as a reaction coordinate diagram.

        Args:
            result: DFTMechanismResult with intermediates and TSs

        Returns:
            List of (label, energy) tuples.
        """
        diagram: List[Tuple[str, float]] = []

        all_points = sorted(
            result.intermediates + result.transition_states,
            key=lambda p: p.step
        )

        for pt in all_points:
            if pt.is_ts:
                label = f"TS (step {pt.step})"
            elif pt.is_minimum:
                label = pt.smiles or f"Min (step {pt.step})"
            else:
                label = f"Point {pt.step}"
            diagram.append((label, pt.energy_kcal_rel))

        return diagram

    # ════════════════════════════════════════════════════════════════════
    # CONVENIENCE METHODS
    # ════════════════════════════════════════════════════════════════════

    def run_relaxed_scan(self, reactant_smi: str,
                          bond_indices: Tuple[int, int],
                          scan_range: Tuple[float, float],
                          n_points: int = 20
                          ) -> Optional[List[IRCPoint]]:
        """
        Run a relaxed surface scan along a specific bond coordinate.

        Useful for simple bond-breaking/forming reactions where a full TS
        search is overkill. All other degrees of freedom are optimized at
        each scan step.

        Args:
            reactant_smi: Reactant SMILES
            bond_indices: (atom_i, atom_j) defining the scanned bond
            scan_range: (start_distance, end_distance) in Angstrom
            n_points: Number of scan points (default: 20)

        Returns:
            List of IRCPoints along the scan, or None on failure.
        """
        if not self.is_available or not RDKIT_AVAILABLE:
            logger.warning("run_relaxed_scan: ORCA/RDKit 미사용 (is_available=%s, RDKIT=%s)",
                           self.is_available, RDKIT_AVAILABLE)
            return None

        # N-code: type guard — external callers may pass non-str reactant_smi
        if not isinstance(reactant_smi, str):
            logger.warning("run_relaxed_scan() reactant_smi is not str: type=%s", type(reactant_smi).__name__)
            return None

        config = self.config
        charge, mult = self._determine_charge_mult(reactant_smi, config)

        xyz = self._generate_3d_coords(reactant_smi)
        if not xyz:
            logger.warning("run_relaxed_scan: 3D 좌표 생성 실패: %s", reactant_smi)
            return None

        self._work_dir = tempfile.mkdtemp(prefix="chemgrid_scan_")

        scan_inp = self._write_orca_scan_input(
            xyz, bond_indices[0], bond_indices[1],
            scan_range[0], scan_range[1], n_points,
            charge, mult, config
        )
        scan_file = os.path.join(self._work_dir, "scan.inp")
        with open(scan_file, "w", encoding="utf-8") as f:
            f.write(scan_inp)

        success, out_file = self._run_orca(scan_file, config.timeout_sec)
        if not success:
            logger.warning("run_relaxed_scan: ORCA 실행 실패")
            return None

        # Parse scan trajectory
        scan_dir = os.path.dirname(out_file)
        trj_files = [f for f in os.listdir(scan_dir)
                      if f.endswith("_trj.xyz") or f.endswith("_Scan.xyz")]

        if not trj_files:
            logger.warning("run_relaxed_scan: 스캔 궤적 파일 없음: %s", scan_dir)
            return None

        frames = self._parse_multi_xyz(os.path.join(scan_dir, trj_files[0]))
        energies = self._parse_scan_energies(out_file)

        points = []
        for i, xyz_block in enumerate(frames):
            energy = energies[i] if i < len(energies) else 0.0
            points.append(IRCPoint(
                step=i, energy_hartree=energy, energy_kcal_rel=0.0,
                xyz_block=xyz_block,
                smiles=self._xyz_to_smiles(xyz_block),
            ))

        if points:
            ref = points[0].energy_hartree
            for pt in points:
                pt.energy_kcal_rel = (pt.energy_hartree - ref) * HARTREE_TO_KCAL

        return points

    def run_single_point_energies(self, smiles_list: List[str],
                                   method: str = ""
                                   ) -> List[Tuple[str, float]]:
        """
        Run single-point energy calculations on a list of structures.

        Useful for refining energies of known intermediates at a higher
        level of theory. Uses the fine basis set (6-311+G(2d,p)) by default.

        Args:
            smiles_list: List of SMILES strings to calculate
            method: Override DFT method (empty = use config default)

        Returns:
            List of (smiles, energy_hartree) tuples.
        """
        if not self.is_available or not RDKIT_AVAILABLE:
            return []

        # N-code: type guard — smiles_list must be a list of str
        if not isinstance(smiles_list, list):
            logger.warning("run_single_point_energies() smiles_list is not list: type=%s", type(smiles_list).__name__)
            return []

        config = self.config
        results: List[Tuple[str, float]] = []
        self._work_dir = tempfile.mkdtemp(prefix="chemgrid_sp_")

        for i, smi in enumerate(smiles_list):
            # N-code: type guard — each item must be str
            if not isinstance(smi, str):
                logger.warning("run_single_point_energies() item %d is not str: type=%s", i, type(smi).__name__)
                results.append((str(smi), 0.0))
                continue
            xyz = self._generate_3d_coords(smi)
            if not xyz:
                results.append((smi, 0.0))
                continue

            charge, mult = self._determine_charge_mult(smi, config)
            sp_inp = self._write_orca_sp_input(xyz, charge, mult, config)
            sp_file = os.path.join(self._work_dir, f"sp_{i}.inp")
            with open(sp_file, "w", encoding="utf-8") as f:
                f.write(sp_inp)

            success, out_file = self._run_orca(sp_file, config.timeout_sec)
            if success:
                energy = self._parse_final_energy(out_file)
                results.append((smi, energy))
            else:
                results.append((smi, 0.0))

        return results

    def generate_for_drylab(self, reactant_smi: str, product_smi: str,
                             conditions: str = ""
                             ) -> Optional[List[dict]]:
        """
        Generate DFT mechanism data in the format expected by
        drylab_report_exporter.py.

        Returns a list of step dictionaries with keys:
            - step_number, title, description
            - reactant_smiles, product_smiles
            - barrier_kcal (activation energy)
            - method (DFT method string)

        Args:
            reactant_smi: Reactant SMILES
            product_smi: Product SMILES
            conditions: Reaction conditions string

        Returns:
            List of step dicts, or None on failure.
        """
        # N-code: type guard — external callers may pass non-str values
        if not isinstance(reactant_smi, str) or not isinstance(product_smi, str):
            logger.warning("DFT generate_for_drylab() received non-str SMILES: reactant=%s, product=%s",
                           type(reactant_smi).__name__, type(product_smi).__name__)
            return None
        if not isinstance(conditions, str):
            conditions = str(conditions) if conditions else ""

        result = self.generate(reactant_smi, product_smi, conditions)
        if result is None or not result.success:
            logger.warning("generate_for_drylab: DFT 메커니즘 생성 실패: %s → %s", reactant_smi, product_smi)
            return None

        steps = []
        for i in range(len(result.intermediates) - 1):
            start = result.intermediates[i]
            end = result.intermediates[i + 1]

            # Find barrier
            barrier = 0.0
            for ts in result.transition_states:
                if start.step < ts.step < end.step:
                    barrier = ts.energy_kcal_rel - start.energy_kcal_rel
                    break

            steps.append({
                "step_number": i + 1,
                "title": f"Step {i+1}: {start.smiles or 'R'} → {end.smiles or 'P'}",
                "description": (
                    f"DFT-computed ({self.config.method}/{self.config.basis_set})"
                ),
                "reactant_smiles": start.smiles or reactant_smi,
                "product_smiles": end.smiles or product_smi,
                "barrier_kcal": round(barrier, 1),
                "method": f"{self.config.method}/{self.config.basis_set}/{self.config.dispersion}",
            })

        return steps if steps else None


# ============================================================================
# CACHE SYSTEM
# ============================================================================

class DFTMechanismCache:
    """
    Cache DFT results to avoid recalculating known reactions.

    Results are stored as JSON files with canonical SMILES as the key.
    This prevents expensive re-computation when the same reaction is
    queried multiple times (e.g., during DryLab report generation).

    Cache location: departments/domain_mechanism/dft_cache/
    """

    def __init__(self, cache_dir: str = ""):
        """Initialize cache with directory path.

        Args:
            cache_dir: Path to cache directory. Auto-detected if empty.
        """
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            # Relative to src/app/ → ../../departments/domain_mechanism/dft_cache/
            base = Path(__file__).resolve().parent
            self.cache_dir = str(
                base / ".." / ".." / "departments" / "domain_mechanism" / "dft_cache"
            )

    def get(self, reactant_smi: str, product_smi: str
            ) -> Optional[DFTMechanismResult]:
        """
        Look up a cached DFT result by canonical SMILES.

        Args:
            reactant_smi: Reactant SMILES
            product_smi: Product SMILES

        Returns:
            Cached DFTMechanismResult, or None if not found.
        """
        key = self._make_key(reactant_smi, product_smi)
        cache_file = os.path.join(self.cache_dir, f"{key}.json")

        if not os.path.isfile(cache_file):
            logger.debug("DFT 캐시 미스: %s", cache_file)
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # N-code: type guard — JSON cache may be corrupt or non-dict
            if not isinstance(data, dict):
                logger.warning("DFT cache file is not a dict: %s (type=%s)", cache_file, type(data).__name__)
                return None

            # Reconstruct IRCPoints with type guards on list items
            raw_irc = data.get("irc_path", [])
            if not isinstance(raw_irc, list):
                logger.warning("DFT cache 'irc_path' is not a list: type=%s", type(raw_irc).__name__)
                raw_irc = []
            irc_path = [
                IRCPoint(**pt) for pt in raw_irc if isinstance(pt, dict)
            ]

            raw_intermediates = data.get("intermediates", [])
            if not isinstance(raw_intermediates, list):
                logger.warning("DFT cache 'intermediates' is not a list: type=%s", type(raw_intermediates).__name__)
                raw_intermediates = []
            intermediates = [
                IRCPoint(**pt) for pt in raw_intermediates if isinstance(pt, dict)
            ]

            raw_ts = data.get("transition_states", [])
            if not isinstance(raw_ts, list):
                logger.warning("DFT cache 'transition_states' is not a list: type=%s", type(raw_ts).__name__)
                raw_ts = []
            transition_states = [
                IRCPoint(**pt) for pt in raw_ts if isinstance(pt, dict)
            ]

            raw_diagram = data.get("energy_diagram", [])
            if not isinstance(raw_diagram, list):
                logger.warning("DFT cache 'energy_diagram' is not a list: type=%s", type(raw_diagram).__name__)
                raw_diagram = []

            result = DFTMechanismResult(
                success=data.get("success", False),
                method_used=data.get("method_used", "") if isinstance(data.get("method_used"), str) else "",
                irc_path=irc_path,
                intermediates=intermediates,
                transition_states=transition_states,
                energy_diagram=[
                    tuple(x) for x in raw_diagram if isinstance(x, (list, tuple))
                ],
                calculation_time_sec=float(data.get("calculation_time_sec", 0.0)) if isinstance(data.get("calculation_time_sec"), (int, float)) else 0.0,
                orca_output_dir=data.get("orca_output_dir", "") if isinstance(data.get("orca_output_dir"), str) else "",
            )
            return result

        except Exception as e:
            logger.debug(f"Cache read failed for key {key}: {e}")
            return None

    def put(self, reactant_smi: str, product_smi: str,
            result: DFTMechanismResult):
        """
        Store a DFT result in the cache.

        Args:
            reactant_smi: Reactant SMILES
            product_smi: Product SMILES
            result: DFTMechanismResult to cache
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        key = self._make_key(reactant_smi, product_smi)
        cache_file = os.path.join(self.cache_dir, f"{key}.json")

        try:
            def irc_to_dict(pt: IRCPoint) -> dict:
                return {
                    "step": pt.step,
                    "energy_hartree": pt.energy_hartree,
                    "energy_kcal_rel": pt.energy_kcal_rel,
                    "xyz_block": pt.xyz_block,
                    "smiles": pt.smiles,
                    "is_minimum": pt.is_minimum,
                    "is_ts": pt.is_ts,
                }

            data = {
                "reactant_smi": reactant_smi,
                "product_smi": product_smi,
                "success": result.success,
                "method_used": result.method_used,
                "irc_path": [irc_to_dict(pt) for pt in result.irc_path],
                "intermediates": [irc_to_dict(pt) for pt in result.intermediates],
                "transition_states": [irc_to_dict(pt) for pt in result.transition_states],
                "energy_diagram": result.energy_diagram,
                "calculation_time_sec": result.calculation_time_sec,
                "orca_output_dir": result.orca_output_dir,
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"DFT result cached: {cache_file}")

        except Exception as e:
            logger.debug(f"Cache write failed: {e}")

    def _make_key(self, r_smi: str, p_smi: str) -> str:
        """
        Generate a cache key from canonical SMILES.

        Uses MD5 hash of the sorted canonical SMILES to create a
        filesystem-safe filename.

        Args:
            r_smi: Reactant SMILES
            p_smi: Product SMILES

        Returns:
            MD5 hash string suitable for use as a filename.
        """
        # Canonicalize
        if RDKIT_AVAILABLE:
            r_mol = Chem.MolFromSmiles(r_smi)
            if r_mol is None:  # Rule L: None guard
                logger.warning("Invalid reactant SMILES for DFT: %s", r_smi)
            p_mol = Chem.MolFromSmiles(p_smi)
            if p_mol is None:  # Rule L: None guard
                logger.warning("Invalid product SMILES for DFT: %s", p_smi)
            r_can = Chem.MolToSmiles(r_mol) if r_mol else r_smi
            p_can = Chem.MolToSmiles(p_mol) if p_mol else p_smi
        else:
            r_can, p_can = r_smi, p_smi

        # Sort to make R+P == P+R (same reaction, different direction)
        combined = "||".join(sorted([r_can, p_can]))
        return hashlib.md5(combined.encode("utf-8")).hexdigest()
