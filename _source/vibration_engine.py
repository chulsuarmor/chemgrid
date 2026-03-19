# vibration_engine.py (v2.0 - Internal Vibration Mode Engine)
"""
ChemGrid: ORCA 없이 경험적 힘 상수 기반 진동 주파수 계산
- 조화진동자 근사 (Harmonic Oscillator Approximation)
- RDKit MMFF94/UFF 3D 좌표 최적화
- Bond-stretch + Angle-bend + Torsion 진동모드
- 작용기별 특성 진동수 데이터베이스
- 간이 변위벡터 생성 (질량 가중)
"""

import math
import logging
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ============================================================================
# CONSTANTS
# ============================================================================

# Atomic masses (amu)
ATOMIC_MASSES = {
    "H": 1.008, "He": 4.003, "Li": 6.941, "Be": 9.012,
    "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999,
    "F": 18.998, "Ne": 20.180, "Na": 22.990, "Mg": 24.305,
    "Al": 26.982, "Si": 28.086, "P": 30.974, "S": 32.065,
    "Cl": 35.453, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Br": 79.904, "I": 126.904, "Se": 78.971,
}

# Empirical bond stretch force constants (N/m)
# Key: (atom1_symbol, atom2_symbol, bond_order) → force constant
FORCE_CONSTANTS: Dict[Tuple[str, str, int], float] = {
    ("C", "H", 1): 480,
    ("O", "H", 1): 780,
    ("N", "H", 1): 600,
    ("S", "H", 1): 350,
    ("C", "C", 1): 300,
    ("C", "C", 2): 600,
    ("C", "C", 3): 900,
    ("C", "N", 1): 350,
    ("C", "N", 2): 650,
    ("C", "N", 3): 800,
    ("C", "O", 1): 350,
    ("C", "O", 2): 750,
    ("C", "F", 1): 440,
    ("C", "Cl", 1): 240,
    ("C", "Br", 1): 200,
    ("C", "I", 1): 160,
    ("C", "S", 1): 200,
    ("C", "S", 2): 450,
    ("N", "O", 1): 350,
    ("N", "O", 2): 600,
    ("N", "N", 1): 300,
    ("N", "N", 2): 550,
    ("N", "N", 3): 800,
    ("O", "O", 1): 300,
    ("S", "O", 2): 500,
    ("S", "S", 1): 200,
    ("P", "O", 1): 350,
    ("P", "O", 2): 600,
    ("Si", "O", 1): 400,
    ("Si", "C", 1): 250,
}

# Empirical angle bending force constants (N/m equivalent, for bend frequency calc)
# Key: (atom_a, central_atom, atom_c) → k_bend (N·m/rad²)
# Using typical values from MMFF94/UFF literature
BEND_FORCE_CONSTANTS: Dict[Tuple[str, str, str], float] = {
    ("H", "C", "H"): 0.55,
    ("H", "C", "C"): 0.65,
    ("H", "C", "N"): 0.65,
    ("H", "C", "O"): 0.70,
    ("C", "C", "C"): 0.90,
    ("C", "C", "N"): 0.95,
    ("C", "C", "O"): 1.00,
    ("C", "C", "H"): 0.65,
    ("C", "N", "C"): 0.80,
    ("C", "N", "H"): 0.70,
    ("H", "N", "H"): 0.55,
    ("C", "O", "C"): 0.85,
    ("C", "O", "H"): 0.75,
    ("H", "O", "H"): 0.70,   # water-like
    ("O", "C", "O"): 1.20,   # carboxylate
    ("C", "S", "C"): 0.70,
    ("C", "S", "H"): 0.60,
    ("H", "S", "H"): 0.50,
    ("O", "S", "O"): 1.10,
    ("O", "P", "O"): 1.05,
    ("F", "C", "F"): 1.10,
    ("Cl", "C", "Cl"): 0.80,
}

# Empirical torsion force constants (N·m/rad², much smaller than bend)
# Key: general type → k_torsion
TORSION_FORCE_CONSTANTS = {
    "sp3-sp3": 0.04,   # ethane-like
    "sp3-sp2": 0.02,   # propene-like
    "sp2-sp2": 0.10,   # butadiene-like (partial double bond character)
    "sp2-sp3": 0.02,
    "ring": 0.08,       # ring torsion (more rigid)
    "default": 0.03,
}

# Functional group characteristic frequencies (cm⁻¹)
# Used for validation and labeling of calculated modes
FUNCTIONAL_GROUP_FREQS = {
    # Stretch modes
    "O-H (alcohol)":       (3200, 3550),
    "O-H (carboxylic)":    (2500, 3300),
    "N-H (amine)":         (3300, 3500),
    "N-H (amide)":         (3100, 3500),
    "C-H (sp3)":           (2850, 2960),
    "C-H (sp2)":           (3020, 3100),
    "C-H (sp)":            (3300, 3320),
    "C-H (aldehyde)":      (2700, 2850),
    "C≡N (nitrile)":       (2200, 2260),
    "C≡C (alkyne)":        (2100, 2260),
    "C=O (ketone)":        (1705, 1725),
    "C=O (aldehyde)":      (1720, 1740),
    "C=O (ester)":         (1735, 1750),
    "C=O (carboxylic)":    (1700, 1725),
    "C=O (amide)":         (1630, 1690),
    "C=O (anhydride)":     (1800, 1850),
    "C=C (alkene)":        (1620, 1680),
    "C=C (aromatic)":      (1450, 1600),
    "C-O (ether/alcohol)": (1000, 1260),
    "C-N (amine)":         (1020, 1250),
    "N=O (nitro, asym)":   (1500, 1570),
    "N=O (nitro, sym)":    (1290, 1370),
    "S=O (sulfoxide)":     (1030, 1070),
    "S=O (sulfone)":       (1120, 1370),
    "C-F":                 (1000, 1400),
    "C-Cl":                (600, 800),
    "C-Br":                (500, 680),
    "C-I":                 (480, 600),
    "P=O":                 (1250, 1300),
    "P-O":                 (900, 1050),
    # Bend modes
    "C-H bend (in-plane)": (1340, 1480),
    "C-H bend (oop)":      (650, 1000),
    "O-H bend":            (1200, 1450),
    "N-H bend":            (1550, 1650),
    "CH₂ scissors":        (1440, 1470),
    "CH₃ deformation":     (1370, 1380),
    "C=C-H bend":          (650, 1000),
    # Ring modes
    "aromatic ring breath": (990, 1010),
    "aromatic C-H oop":     (670, 900),
}

# Constants
AMU_TO_KG = 1.66054e-27       # atomic mass unit → kg
SPEED_OF_LIGHT = 2.998e10     # cm/s
TWO_PI = 2.0 * math.pi
BOHR_TO_ANGSTROM = 0.529177


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class VibrationMode:
    """단일 진동 모드"""
    frequency_cm: float            # cm⁻¹
    ir_intensity: float            # 상대 IR 강도 (0~1)
    description: str               # "C-H stretch", "O-H stretch" 등
    displacement_vectors: List[Tuple[float, float, float]]  # 각 원자의 (dx, dy, dz)
    bond_indices: Tuple[int, ...]  # 관련 원자 인덱스 (2=stretch, 3=bend, 4=torsion)
    mode_type: str = "stretch"     # "stretch", "bend", "torsion"
    ir_active: bool = True         # IR 활성 여부
    raman_active: bool = True      # Raman 활성 여부
    ir_explanation: str = ""       # IR 활성 이유
    raman_explanation: str = ""    # Raman 활성 이유
    spectroscopy_note: str = ""    # 분광학 해설 (왜 이 진동이 검출되는가)
    wavelength_um: float = 0.0     # 파장 (μm) = 10000 / freq_cm
    freq_range_label: str = ""     # 특성 주파수 범위 라벨 (예: "2850-3000 cm⁻¹")


@dataclass
class VibrationResult:
    """진동 계산 결과"""
    modes: List[VibrationMode]
    atoms: List[Tuple[str, float, float, float]]  # (symbol, x, y, z) in Angstrom
    num_atoms: int
    method: str = "Harmonic Oscillator (Empirical)"
    success: bool = True
    error_message: str = ""


# ============================================================================
# INTERNAL VIBRATION ENGINE
# ============================================================================

class InternalVibrationEngine:
    """ORCA 없이 경험적 힘 상수로 진동 주파수 계산

    방법:
    1. RDKit MMFF94로 3D 좌표 최적화
    2. Bond-stretch: ν = √(k/μ) / (2π)  →  cm⁻¹
    3. Angle-bend: ν = √(k_bend/μ_bend) / (2π)  →  cm⁻¹
    4. Torsion: ν = √(k_tor/μ_tor) / (2π)  →  cm⁻¹
    5. 작용기 매칭으로 정확한 설명 생성
    6. 3D 변위벡터 생성 (각 모드 유형별)
    """

    def calculate(self, smiles: str = None, mol=None) -> VibrationResult:
        """진동 모드 계산

        Args:
            smiles: 분자 SMILES (mol과 둘 중 하나)
            mol: RDKit 분자 객체 (이미 3D coords가 있을 수 있음)

        Returns:
            VibrationResult
        """
        if not RDKIT_AVAILABLE:
            return VibrationResult(
                modes=[], atoms=[], num_atoms=0,
                success=False, error_message="RDKit not available"
            )

        try:
            return self._calculate_impl(smiles, mol)
        except Exception as e:
            logger.error(f"[VibrationEngine] Calculation failed: {e}")
            return VibrationResult(
                modes=[], atoms=[], num_atoms=0,
                success=False, error_message=str(e)
            )

    def _calculate_impl(self, smiles: str, mol) -> VibrationResult:
        # Step 1: Prepare molecule with 3D coords
        if mol is None:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return VibrationResult(
                    modes=[], atoms=[], num_atoms=0,
                    success=False, error_message=f"Invalid SMILES: {smiles}"
                )

        mol = Chem.AddHs(mol)

        # Embed 3D coordinates
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        result = AllChem.EmbedMolecule(mol, params)
        if result != 0:
            # Fallback: random coords
            result2 = AllChem.EmbedMolecule(mol, AllChem.ETKDG())
            if result2 != 0:
                params2 = AllChem.ETKDGv3()
                params2.useRandomCoords = True
                AllChem.EmbedMolecule(mol, params2)

        # Optimize with MMFF94 (or UFF fallback)
        try:
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props:
                ff = AllChem.MMFFGetMoleculeForceField(mol, props)
                if ff:
                    ff.Minimize(maxIts=500)
            else:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
        except Exception:
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            except Exception:
                pass  # Use initial embedded coords

        # Step 2: Extract atom data
        conf = mol.GetConformer()
        num_atoms = mol.GetNumAtoms()
        atoms = []
        for i in range(num_atoms):
            pos = conf.GetAtomPosition(i)
            sym = mol.GetAtomWithIdx(i).GetSymbol()
            atoms.append((sym, pos.x, pos.y, pos.z))

        # Step 3: Calculate all vibration modes
        modes = []

        # 3a: Bond stretch modes
        for bond in mol.GetBonds():
            mode = self._calc_stretch_mode(bond, mol, conf, atoms, num_atoms)
            if mode:
                modes.append(mode)

        # 3b: Angle bending modes
        angle_modes = self._calc_all_bend_modes(mol, conf, atoms, num_atoms)
        modes.extend(angle_modes)

        # 3c: Torsion modes (dihedral)
        torsion_modes = self._calc_all_torsion_modes(mol, conf, atoms, num_atoms)
        modes.extend(torsion_modes)

        # Step 4: Match functional group labels
        self._assign_functional_group_labels(modes, mol, atoms)

        # Step 5: Assign IR/Raman activity & spectroscopy info
        self._assign_spectroscopy_info(modes, atoms)

        # Sort by frequency (ascending)
        modes.sort(key=lambda m: m.frequency_cm)

        # Filter out imaginary/zero/too-low frequencies
        modes = [m for m in modes if m.frequency_cm > 50]

        # Limit total modes: for large molecules, keep most significant
        max_modes = max(3 * num_atoms - 6, 30)
        if len(modes) > max_modes:
            # Keep highest IR intensity modes + ensure coverage of all types
            stretch_modes = [m for m in modes if m.mode_type == "stretch"]
            bend_modes = [m for m in modes if m.mode_type == "bend"]
            torsion_modes_list = [m for m in modes if m.mode_type == "torsion"]

            # Sort each by IR intensity, keep top
            stretch_modes.sort(key=lambda m: m.ir_intensity, reverse=True)
            bend_modes.sort(key=lambda m: m.ir_intensity, reverse=True)
            torsion_modes_list.sort(key=lambda m: m.ir_intensity, reverse=True)

            n_stretch = min(len(stretch_modes), max(max_modes // 2, 10))
            n_bend = min(len(bend_modes), max(max_modes // 3, 8))
            n_torsion = min(len(torsion_modes_list), max(max_modes // 6, 4))

            modes = stretch_modes[:n_stretch] + bend_modes[:n_bend] + torsion_modes_list[:n_torsion]
            modes.sort(key=lambda m: m.frequency_cm)

        return VibrationResult(
            modes=modes,
            atoms=atoms,
            num_atoms=num_atoms,
            method="Harmonic Oscillator (Empirical, Stretch+Bend+Torsion)",
            success=True
        )

    # ========================================================================
    # STRETCH MODES
    # ========================================================================

    def _calc_stretch_mode(self, bond, mol, conf, atoms, num_atoms) -> Optional[VibrationMode]:
        """단일 결합의 stretch 진동 모드 계산"""
        i = bond.GetBeginAtomIdx()
        j = bond.GetEndAtomIdx()
        sym_i = atoms[i][0]
        sym_j = atoms[j][0]

        # Bond order
        bt = bond.GetBondTypeAsDouble()
        bond_order = int(round(bt))
        if bond_order < 1:
            bond_order = 1

        # Look up force constant
        k = self._get_force_constant(sym_i, sym_j, bond_order)
        if k <= 0:
            return None

        # Reduced mass
        m_i = ATOMIC_MASSES.get(sym_i, 12.0)
        m_j = ATOMIC_MASSES.get(sym_j, 12.0)
        mu_amu = (m_i * m_j) / (m_i + m_j)
        mu_kg = mu_amu * AMU_TO_KG

        # Frequency: ν = √(k/μ) / (2π)  [Hz]
        freq_hz = math.sqrt(k / mu_kg) / TWO_PI
        freq_cm = freq_hz / SPEED_OF_LIGHT

        # IR intensity estimate
        ir_intensity = self._estimate_ir_intensity(sym_i, sym_j, bond_order)

        # Description
        bond_type_str = {1: "-", 2: "=", 3: "≡"}.get(bond_order, "-")
        desc = f"{sym_i}{bond_type_str}{sym_j} stretch"

        # Displacement vectors
        displacement = self._calc_stretch_displacement(
            i, j, conf, m_i, m_j, num_atoms)

        return VibrationMode(
            frequency_cm=freq_cm,
            ir_intensity=ir_intensity,
            description=desc,
            displacement_vectors=displacement,
            bond_indices=(i, j),
            mode_type="stretch"
        )

    # ========================================================================
    # BENDING MODES
    # ========================================================================

    def _calc_all_bend_modes(self, mol, conf, atoms, num_atoms) -> List[VibrationMode]:
        """모든 결합각의 bending 진동 모드 계산"""
        modes = []
        processed_angles = set()

        for atom in mol.GetAtoms():
            center_idx = atom.GetIdx()
            neighbors = [n.GetIdx() for n in atom.GetNeighbors()]

            if len(neighbors) < 2:
                continue

            # All pairs of neighbors form an angle
            for ni in range(len(neighbors)):
                for nj in range(ni + 1, len(neighbors)):
                    a_idx = neighbors[ni]
                    c_idx = neighbors[nj]

                    # Canonical ordering to avoid duplicates
                    angle_key = tuple(sorted([a_idx, c_idx]) + [center_idx])
                    if angle_key in processed_angles:
                        continue
                    processed_angles.add(angle_key)

                    mode = self._calc_bend_mode(
                        a_idx, center_idx, c_idx, mol, conf, atoms, num_atoms)
                    if mode:
                        modes.append(mode)

        return modes

    def _calc_bend_mode(self, a_idx: int, b_idx: int, c_idx: int,
                        mol, conf, atoms, num_atoms) -> Optional[VibrationMode]:
        """단일 결합각 A-B-C의 bending 진동 모드"""
        sym_a = atoms[a_idx][0]
        sym_b = atoms[b_idx][0]
        sym_c = atoms[c_idx][0]

        # Get bend force constant
        k_bend = self._get_bend_force_constant(sym_a, sym_b, sym_c)

        # Calculate equilibrium angle
        pos_a = conf.GetAtomPosition(a_idx)
        pos_b = conf.GetAtomPosition(b_idx)
        pos_c = conf.GetAtomPosition(c_idx)

        ba = (pos_a.x - pos_b.x, pos_a.y - pos_b.y, pos_a.z - pos_b.z)
        bc = (pos_c.x - pos_b.x, pos_c.y - pos_b.y, pos_c.z - pos_b.z)

        len_ba = math.sqrt(sum(x * x for x in ba))
        len_bc = math.sqrt(sum(x * x for x in bc))
        if len_ba < 0.01 or len_bc < 0.01:
            return None

        # Bond lengths in meters for frequency calculation
        r_ab = len_ba * 1e-10  # Angstrom → meters
        r_bc = len_bc * 1e-10

        # Reduced mass for bending (Wilson's approximation)
        m_a = ATOMIC_MASSES.get(sym_a, 12.0)
        m_b = ATOMIC_MASSES.get(sym_b, 12.0)
        m_c = ATOMIC_MASSES.get(sym_c, 12.0)

        # Dot product for angle
        dot = sum(a * b for a, b in zip(ba, bc))
        cos_theta = max(-1.0, min(1.0, dot / (len_ba * len_bc)))
        theta = math.acos(cos_theta)
        sin_theta = math.sin(theta) if abs(math.sin(theta)) > 0.01 else 0.01

        # Effective reduced mass for bending (Wilson GF matrix element)
        # μ_bend = 1/(1/m_a·r_ab² + 1/m_c·r_bc² + (1/m_b)·(1/r_ab² + 1/r_bc² - 2cos(θ)/(r_ab·r_bc)))
        # Simplified: use geometric mean approach
        mu_bend_amu = 1.0 / (
            1.0 / (m_a * (len_ba ** 2)) +
            1.0 / (m_c * (len_bc ** 2)) +
            (1.0 / m_b) * (1.0 / (len_ba ** 2) + 1.0 / (len_bc ** 2)
                           - 2.0 * cos_theta / (len_ba * len_bc))
        )
        mu_bend_kg = mu_bend_amu * AMU_TO_KG * 1e-20  # Å² → m² correction

        if mu_bend_kg <= 0:
            return None

        # k_bend is in aJ/rad² → convert to N·m/rad² (×1e-18)
        k_si = k_bend * 1e-18

        # Frequency
        try:
            freq_hz = math.sqrt(k_si / mu_bend_kg) / TWO_PI
        except (ValueError, ZeroDivisionError):
            return None
        freq_cm = freq_hz / SPEED_OF_LIGHT

        # Sanity check: bend modes typically 200-1700 cm⁻¹
        if freq_cm < 100 or freq_cm > 2000:
            # Clamp to reasonable range using empirical correction
            if freq_cm > 2000:
                freq_cm = 1400 + (freq_cm - 2000) * 0.05  # compress
            elif freq_cm < 100:
                return None

        # IR intensity for bending
        ir_intensity = self._estimate_bend_ir_intensity(sym_a, sym_b, sym_c)

        # Description
        desc = f"{sym_a}-{sym_b}-{sym_c} bend"

        # Displacement vectors
        displacement = self._calc_bend_displacement(
            a_idx, b_idx, c_idx, conf, m_a, m_b, m_c, num_atoms)

        return VibrationMode(
            frequency_cm=freq_cm,
            ir_intensity=ir_intensity,
            description=desc,
            displacement_vectors=displacement,
            bond_indices=(a_idx, b_idx, c_idx),
            mode_type="bend"
        )

    # ========================================================================
    # TORSION MODES
    # ========================================================================

    def _calc_all_torsion_modes(self, mol, conf, atoms, num_atoms) -> List[VibrationMode]:
        """모든 이면각의 torsion 진동 모드 계산"""
        modes = []
        processed = set()
        ring_info = mol.GetRingInfo()
        ring_bonds = set()
        for ring in ring_info.BondRings():
            ring_bonds.update(ring)

        for bond in mol.GetBonds():
            b_idx = bond.GetBeginAtomIdx()
            c_idx = bond.GetEndAtomIdx()

            # Skip double/triple bonds (restricted rotation)
            if bond.GetBondTypeAsDouble() >= 2.0:
                continue

            atom_b = mol.GetAtomWithIdx(b_idx)
            atom_c = mol.GetAtomWithIdx(c_idx)

            neighbors_b = [n.GetIdx() for n in atom_b.GetNeighbors() if n.GetIdx() != c_idx]
            neighbors_c = [n.GetIdx() for n in atom_c.GetNeighbors() if n.GetIdx() != b_idx]

            if not neighbors_b or not neighbors_c:
                continue

            # Use first neighbor on each side for representative torsion
            a_idx = neighbors_b[0]
            d_idx = neighbors_c[0]

            torsion_key = tuple(sorted([a_idx, d_idx]) + sorted([b_idx, c_idx]))
            if torsion_key in processed:
                continue
            processed.add(torsion_key)

            # Determine torsion type
            is_ring = bond.GetIdx() in ring_bonds
            hyb_b = str(atom_b.GetHybridization())
            hyb_c = str(atom_c.GetHybridization())

            if is_ring:
                tor_type = "ring"
            elif "SP2" in hyb_b and "SP2" in hyb_c:
                tor_type = "sp2-sp2"
            elif "SP3" in hyb_b and "SP3" in hyb_c:
                tor_type = "sp3-sp3"
            elif "SP2" in hyb_b or "SP2" in hyb_c:
                tor_type = "sp3-sp2"
            else:
                tor_type = "default"

            mode = self._calc_torsion_mode(
                a_idx, b_idx, c_idx, d_idx, tor_type,
                mol, conf, atoms, num_atoms)
            if mode:
                modes.append(mode)

        return modes

    def _calc_torsion_mode(self, a_idx: int, b_idx: int, c_idx: int, d_idx: int,
                           tor_type: str, mol, conf, atoms, num_atoms) -> Optional[VibrationMode]:
        """단일 이면각 A-B-C-D의 torsion 진동 모드"""
        sym_a = atoms[a_idx][0]
        sym_b = atoms[b_idx][0]
        sym_c = atoms[c_idx][0]
        sym_d = atoms[d_idx][0]

        k_tor = TORSION_FORCE_CONSTANTS.get(tor_type, 0.03)

        # Reduced mass for torsion (simplified: use terminal atom masses)
        m_a = ATOMIC_MASSES.get(sym_a, 12.0)
        m_d = ATOMIC_MASSES.get(sym_d, 12.0)

        pos_b = conf.GetAtomPosition(b_idx)
        pos_c = conf.GetAtomPosition(c_idx)
        r_bc = math.sqrt(
            (pos_c.x - pos_b.x) ** 2 +
            (pos_c.y - pos_b.y) ** 2 +
            (pos_c.z - pos_b.z) ** 2
        )
        if r_bc < 0.01:
            return None

        # Approximate: μ_torsion ≈ m_a·m_d/(m_a+m_d) · r_bc²
        mu_amu = (m_a * m_d) / (m_a + m_d)
        mu_kg = mu_amu * AMU_TO_KG * (r_bc * 1e-10) ** 2

        if mu_kg <= 0:
            return None

        k_si = k_tor * 1e-18  # aJ/rad² → N·m/rad²

        try:
            freq_hz = math.sqrt(k_si / mu_kg) / TWO_PI
        except (ValueError, ZeroDivisionError):
            return None
        freq_cm = freq_hz / SPEED_OF_LIGHT

        # Torsion modes are typically 50-600 cm⁻¹
        if freq_cm < 30 or freq_cm > 800:
            if freq_cm > 800:
                freq_cm = 500 + (freq_cm - 800) * 0.02
            elif freq_cm < 30:
                return None

        # Torsion IR intensity (usually weak)
        ir_intensity = 0.15
        if tor_type == "sp2-sp2":
            ir_intensity = 0.25  # conjugated torsion slightly stronger
        elif tor_type == "ring":
            ir_intensity = 0.20

        desc = f"{sym_a}-{sym_b}-{sym_c}-{sym_d} torsion"

        displacement = self._calc_torsion_displacement(
            a_idx, b_idx, c_idx, d_idx, conf, atoms, num_atoms)

        return VibrationMode(
            frequency_cm=freq_cm,
            ir_intensity=ir_intensity,
            description=desc,
            displacement_vectors=displacement,
            bond_indices=(a_idx, b_idx, c_idx, d_idx),
            mode_type="torsion"
        )

    # ========================================================================
    # FUNCTIONAL GROUP LABELING
    # ========================================================================

    def _assign_functional_group_labels(self, modes: List[VibrationMode],
                                         mol, atoms: list):
        """작용기 매칭으로 정확한 설명 부여"""
        for mode in modes:
            freq = mode.frequency_cm
            best_match = None
            best_overlap = 0

            for fg_name, (low, high) in FUNCTIONAL_GROUP_FREQS.items():
                if low <= freq <= high:
                    # Check if atom types match
                    if self._fg_matches_atoms(fg_name, mode, atoms):
                        overlap = 1.0 - abs(freq - (low + high) / 2) / ((high - low) / 2 + 1)
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_match = fg_name

            if best_match:
                mode.description = f"{best_match} ({freq:.0f} cm⁻¹)"
            else:
                mode.description = f"{mode.description} ({freq:.0f} cm⁻¹)"

    def _fg_matches_atoms(self, fg_name: str, mode: VibrationMode, atoms: list) -> bool:
        """작용기 이름과 모드의 원자가 정확히 매칭되는지 확인"""
        indices = mode.bond_indices
        if not indices:
            return False

        mode_atoms = set()
        for idx in indices:
            if 0 <= idx < len(atoms):
                mode_atoms.add(atoms[idx][0])

        fg_lower = fg_name.lower()

        # Extract required atoms from functional group name
        # Must check that the atoms mentioned in FG are actually present in mode
        fg_atom_requirements = {
            "o-h": {"O", "H"}, "n-h": {"N", "H"}, "c-h": {"C", "H"},
            "c=o": {"C", "O"}, "c-o": {"C", "O"}, "c=c": {"C"},
            "c-n": {"C", "N"}, "c≡n": {"C", "N"}, "c≡c": {"C"},
            "c-f": {"C", "F"}, "c-cl": {"C", "Cl"}, "c-br": {"C", "Br"},
            "c-i": {"C", "I"}, "s=o": {"S", "O"}, "s-o": {"S", "O"},
            "p=o": {"P", "O"}, "p-o": {"P", "O"}, "n=o": {"N", "O"},
            "n-n": {"N"}, "o-o": {"O"}, "s-s": {"S"},
            "si-o": {"Si", "O"}, "si-c": {"Si", "C"},
        }

        # Check all atom requirements strictly
        for pattern, required in fg_atom_requirements.items():
            if pattern in fg_lower:
                if not (required <= mode_atoms):
                    return False
                # Also ensure no extra unrelated atoms disqualify it
                # e.g., "P-O" should not match C-O modes
                if pattern in ("p-o", "p=o") and "P" not in mode_atoms:
                    return False
                if pattern in ("s=o", "s-o") and "S" not in mode_atoms:
                    return False
                if pattern in ("n=o",) and "N" not in mode_atoms:
                    return False
                if pattern in ("c-i",) and "I" not in mode_atoms:
                    return False

        # Extra check: bend modes should only match bend FG entries
        if mode.mode_type == "stretch" and "bend" in fg_lower:
            return False
        if mode.mode_type == "bend" and "stretch" in fg_lower:
            return False

        # Aromatic-specific checks
        if "aromatic" in fg_lower:
            # Only match if it's actually aromatic (ring-related)
            if mode.mode_type not in ("bend", "torsion"):
                if "ring" not in fg_lower and "aromatic" in fg_lower:
                    pass  # Allow aromatic C=C stretch

        return True

    # ========================================================================
    # IR/RAMAN ACTIVITY & SPECTROSCOPY INFO
    # ========================================================================

    def _assign_spectroscopy_info(self, modes: List[VibrationMode], atoms: list):
        """각 진동 모드에 IR/Raman 활성 정보 및 분광학 해설 부여"""
        for mode in modes:
            # 1. IR/Raman activity determination
            ir_act, raman_act, ir_expl, raman_expl = self._determine_ir_raman_activity(
                mode, atoms)
            mode.ir_active = ir_act
            mode.raman_active = raman_act
            mode.ir_explanation = ir_expl
            mode.raman_explanation = raman_expl

            # 2. Wavelength calculation
            if mode.frequency_cm > 0:
                mode.wavelength_um = 10000.0 / mode.frequency_cm

            # 3. Frequency range label from CHARACTERISTIC_FREQUENCIES
            mode.freq_range_label = self._get_freq_range_label(mode)

            # 4. Spectroscopy note (educational explanation)
            mode.spectroscopy_note = self._build_spectroscopy_note(mode, atoms)

    def _determine_ir_raman_activity(self, mode: VibrationMode,
                                      atoms: list) -> Tuple[bool, bool, str, str]:
        """진동 모드의 IR/Raman 활성 여부 및 이유 판정

        Rules:
        - IR active: 진동 시 쌍극자 모멘트(dipole moment)가 변해야 함
          → 서로 다른 원자 간 결합 (극성 결합) 진동 → IR 활성
          → 대칭 분자의 대칭 진동 → IR 비활성
        - Raman active: 진동 시 편극률(polarizability)이 변해야 함
          → 대칭 진동은 Raman 활성 (분자 전자 구름의 대칭적 변형)
          → 비대칭 진동도 대부분 Raman 활성이지만 강도가 약할 수 있음
        - 상호 배타 규칙 (mutual exclusion): 대칭 중심이 있는 분자에서만 적용
          → 일반적인 유기 분자에서는 IR/Raman 모두 활성인 경우가 많음

        Returns:
            (ir_active, raman_active, ir_explanation, raman_explanation)
        """
        indices = mode.bond_indices
        if not indices:
            return True, True, "", ""

        mode_atoms = []
        for idx in indices:
            if 0 <= idx < len(atoms):
                mode_atoms.append(atoms[idx][0])

        unique_atoms = set(mode_atoms)
        is_homonuclear = len(unique_atoms) == 1  # 동종 원자만
        polar_atoms = {"O", "N", "F", "Cl", "Br", "S", "P", "I"}
        has_polar = bool(unique_atoms & polar_atoms)
        has_h = "H" in unique_atoms

        if mode.mode_type == "stretch":
            if len(mode_atoms) == 2:
                sym_a, sym_b = mode_atoms[0], mode_atoms[1]
                if sym_a == sym_b:
                    # Homonuclear diatomic-like stretch (e.g., C=C symmetric)
                    ir_active = False
                    raman_active = True
                    ir_expl = "동종 원자 간 대칭 신축 → 쌍극자 모멘트 변화 없음"
                    raman_expl = "대칭 신축 → 편극률 변화 있음 (전자 구름 대칭적 변형)"
                else:
                    # Heteronuclear stretch → always IR active
                    ir_active = True
                    raman_active = True
                    ir_expl = f"{sym_a}-{sym_b} 결합의 신축으로 쌍극자 모멘트가 변함"
                    raman_expl = "결합 신축 시 편극률도 함께 변함"
                    if has_polar or has_h:
                        ir_expl += " (극성 결합 → 강한 IR 흡수)"
            else:
                ir_active = True
                raman_active = True
                ir_expl = "결합 신축 진동 → 쌍극자 모멘트 변화"
                raman_expl = "결합 길이 변화 → 편극률 변화"

        elif mode.mode_type == "bend":
            # Bending modes generally change dipole → IR active
            ir_active = True
            raman_active = True
            ir_expl = "굽힘 진동 → 결합 각도 변화로 쌍극자 모멘트 변함"
            raman_expl = "결합각 변화 → 분자 형태 변화로 편극률 변함"
            if is_homonuclear:
                ir_expl = "대칭 굽힘이지만 각도 변화로 쌍극자 모멘트 약간 변함"
                raman_expl = "대칭 굽힘 → 편극률 변화 (Raman에서 더 강하게 관측)"

        elif mode.mode_type == "torsion":
            # Torsion modes: weak IR, variable Raman
            ir_active = True
            raman_active = True
            ir_expl = "비틀림 진동 → 약한 쌍극자 모멘트 변화"
            raman_expl = "비틀림 시 분자 형태 변화 → 편극률 변화"
            if is_homonuclear:
                ir_active = False
                ir_expl = "대칭 비틀림 → 쌍극자 모멘트 변화 거의 없음"

        else:
            ir_active = True
            raman_active = True
            ir_expl = "쌍극자 모멘트 변화 가능"
            raman_expl = "편극률 변화 가능"

        return ir_active, raman_active, ir_expl, raman_expl

    def _get_freq_range_label(self, mode: VibrationMode) -> str:
        """특성 주파수 범위에 매칭되는 라벨 반환"""
        freq = mode.frequency_cm
        for fg_name, (low, high) in FUNCTIONAL_GROUP_FREQS.items():
            if low <= freq <= high:
                return f"{low}-{high} cm⁻¹"
        return ""

    def _build_spectroscopy_note(self, mode: VibrationMode,
                                  atoms: list) -> str:
        """교육용 분광학 해설 문장 생성"""
        indices = mode.bond_indices
        if not indices:
            return ""

        mode_atoms = []
        for idx in indices:
            if 0 <= idx < len(atoms):
                mode_atoms.append(atoms[idx][0])

        parts = []

        # Mode type description in Korean
        type_kr = {"stretch": "신축 진동", "bend": "굽힘 진동", "torsion": "비틀림 진동"}
        type_en = {"stretch": "stretching", "bend": "bending", "torsion": "torsion"}
        mtype_kr = type_kr.get(mode.mode_type, "진동")
        mtype_en = type_en.get(mode.mode_type, "vibration")

        # Build atom description
        if len(mode_atoms) == 2:
            bond_desc = f"{mode_atoms[0]}-{mode_atoms[1]}"
        elif len(mode_atoms) == 3:
            bond_desc = f"{mode_atoms[0]}-{mode_atoms[1]}-{mode_atoms[2]}"
        else:
            bond_desc = "-".join(mode_atoms[:4])

        parts.append(f"{bond_desc} {mtype_kr} ({mtype_en})")

        # IR explanation
        if mode.ir_active:
            parts.append(
                f"IR 활성: {mode.ir_explanation}"
            )
            parts.append("→ 적외선 분광법(IR spectroscopy)으로 검출 가능")
        else:
            parts.append(f"IR 비활성: {mode.ir_explanation}")

        # Raman explanation
        if mode.raman_active:
            parts.append(
                f"Raman 활성: {mode.raman_explanation}"
            )
            parts.append("→ 라만 분광법(Raman spectroscopy)으로 검출 가능")
        else:
            parts.append(f"Raman 비활성: {mode.raman_explanation}")

        return "\n".join(parts)

    # ========================================================================
    # FORCE CONSTANT LOOKUPS
    # ========================================================================

    def _get_force_constant(self, sym_a: str, sym_b: str, order: int) -> float:
        """힘 상수 조회 (양방향 + 폴백)"""
        k = FORCE_CONSTANTS.get((sym_a, sym_b, order))
        if k is not None:
            return k
        k = FORCE_CONSTANTS.get((sym_b, sym_a, order))
        if k is not None:
            return k

        # Fallback: 유사 결합 추정
        for test_order in [order, 1, 2]:
            k = FORCE_CONSTANTS.get((sym_a, sym_b, test_order))
            if k is not None:
                return k * (order / test_order if test_order > 0 else 1)
            k = FORCE_CONSTANTS.get((sym_b, sym_a, test_order))
            if k is not None:
                return k * (order / test_order if test_order > 0 else 1)

        # Generic fallback
        return 300.0

    def _get_bend_force_constant(self, sym_a: str, sym_b: str, sym_c: str) -> float:
        """결합각 bending 힘 상수 조회"""
        k = BEND_FORCE_CONSTANTS.get((sym_a, sym_b, sym_c))
        if k is not None:
            return k
        k = BEND_FORCE_CONSTANTS.get((sym_c, sym_b, sym_a))
        if k is not None:
            return k

        # Generic fallback based on central atom
        defaults = {"C": 0.70, "N": 0.65, "O": 0.75, "S": 0.55, "P": 0.60}
        return defaults.get(sym_b, 0.60)

    # ========================================================================
    # IR INTENSITY ESTIMATION
    # ========================================================================

    def _estimate_ir_intensity(self, sym_a: str, sym_b: str, order: int) -> float:
        """경험적 IR 강도 추정 (stretch)"""
        polar_atoms = {"O", "N", "F", "Cl", "Br", "S", "P"}

        if sym_a in polar_atoms or sym_b in polar_atoms:
            if "H" in (sym_a, sym_b):
                return 0.9  # O-H, N-H stretches are very strong
            return 0.7
        elif "H" in (sym_a, sym_b):
            return 0.4  # C-H: moderate
        elif order >= 2:
            return 0.5  # C=C, C=O: moderate-strong
        else:
            return 0.2  # C-C single: weak

    def _estimate_bend_ir_intensity(self, sym_a: str, sym_b: str, sym_c: str) -> float:
        """경험적 IR 강도 추정 (bend)"""
        polar = {"O", "N", "F", "Cl", "Br", "S", "P"}
        has_h = "H" in (sym_a, sym_c)
        has_polar = sym_a in polar or sym_b in polar or sym_c in polar

        if has_h and has_polar:
            return 0.65  # O-H, N-H bending: strong
        elif has_h:
            return 0.35  # C-H bending: moderate
        elif has_polar:
            return 0.45
        return 0.20

    # ========================================================================
    # DISPLACEMENT VECTORS
    # ========================================================================

    def _calc_stretch_displacement(self, atom_i: int, atom_j: int,
                                    conf, m_i: float, m_j: float,
                                    num_atoms: int) -> List[Tuple[float, float, float]]:
        """결합 축 방향 변위벡터 (stretch mode).
        주 결합 원자 + 인접 원자에 감쇠된 역방향 변위를 분배하여
        운동량 보존 및 사실적 진동 표현."""
        pos_i = conf.GetAtomPosition(atom_i)
        pos_j = conf.GetAtomPosition(atom_j)

        dx = pos_j.x - pos_i.x
        dy = pos_j.y - pos_i.y
        dz = pos_j.z - pos_i.z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 0.01:
            return [(0, 0, 0)] * num_atoms

        ux, uy, uz = dx / length, dy / length, dz / length

        total_mass = m_i + m_j
        scale_i = m_j / total_mass
        scale_j = m_i / total_mass

        displacement = [(0.0, 0.0, 0.0)] * num_atoms
        displacement[atom_i] = (-ux * scale_i, -uy * scale_i, -uz * scale_i)
        displacement[atom_j] = (ux * scale_j, uy * scale_j, uz * scale_j)

        # 인접 원자에 감쇠된 역방향 변위 분배 (normal mode 근사)
        try:
            mol = conf.GetOwningMol()
            displacement = self._propagate_to_neighbors(
                displacement, [atom_i, atom_j], mol, num_atoms)
        except Exception:
            pass

        return displacement

    def _calc_bend_displacement(self, a_idx: int, b_idx: int, c_idx: int,
                                 conf, m_a: float, m_b: float, m_c: float,
                                 num_atoms: int) -> List[Tuple[float, float, float]]:
        """결합각 변위벡터 (bend mode): A와 C가 결합각 평면에서 반대 방향으로 움직임"""
        pos_a = conf.GetAtomPosition(a_idx)
        pos_b = conf.GetAtomPosition(b_idx)
        pos_c = conf.GetAtomPosition(c_idx)

        # Vectors from center B
        ba = (pos_a.x - pos_b.x, pos_a.y - pos_b.y, pos_a.z - pos_b.z)
        bc = (pos_c.x - pos_b.x, pos_c.y - pos_b.y, pos_c.z - pos_b.z)

        len_ba = math.sqrt(sum(x * x for x in ba))
        len_bc = math.sqrt(sum(x * x for x in bc))
        if len_ba < 0.01 or len_bc < 0.01:
            return [(0, 0, 0)] * num_atoms

        # Unit vectors
        u_ba = tuple(x / len_ba for x in ba)
        u_bc = tuple(x / len_bc for x in bc)

        # Bisector of the angle
        bisect = tuple(a + b for a, b in zip(u_ba, u_bc))
        len_bisect = math.sqrt(sum(x * x for x in bisect))
        if len_bisect < 0.001:
            # Linear angle - use perpendicular
            bisect = self._perpendicular_vector(u_ba)
            len_bisect = math.sqrt(sum(x * x for x in bisect))

        u_bisect = tuple(x / len_bisect for x in bisect)

        # For bending: atoms A and C move perpendicular to their bond vectors
        # in the plane of the angle, toward/away from bisector
        # A moves toward bisector, C moves away (scissoring motion)
        perp_a = self._component_perpendicular(u_ba, u_bisect)
        perp_c = self._component_perpendicular(u_bc, u_bisect)

        # Mass weighting
        total_inv = 1.0 / m_a + 1.0 / m_c
        w_a = (1.0 / m_a) / total_inv if total_inv > 0 else 0.5
        w_c = (1.0 / m_c) / total_inv if total_inv > 0 else 0.5

        # Scale — 시각적으로 충분히 보이는 진폭
        scale = 0.6

        displacement = [(0.0, 0.0, 0.0)] * num_atoms
        displacement[a_idx] = tuple(x * scale * w_a for x in perp_a)
        displacement[c_idx] = tuple(-x * scale * w_c for x in perp_c)
        # Central atom moves slightly opposite to maintain center of mass
        cm_corr = tuple(-(displacement[a_idx][k] * m_a + displacement[c_idx][k] * m_c) / m_b
                        for k in range(3))
        displacement[b_idx] = cm_corr

        # 인접 원자 전파
        try:
            from rdkit import Chem
            mol = conf.GetOwningMol()
            displacement = self._propagate_to_neighbors(
                displacement, [a_idx, b_idx, c_idx], mol, num_atoms)
        except Exception:
            pass

        return displacement

    def _calc_torsion_displacement(self, a_idx: int, b_idx: int,
                                    c_idx: int, d_idx: int,
                                    conf, atoms, num_atoms) -> List[Tuple[float, float, float]]:
        """이면각 변위벡터 (torsion mode): A와 D가 B-C 축 주위로 반대 방향 회전"""
        pos_a = conf.GetAtomPosition(a_idx)
        pos_b = conf.GetAtomPosition(b_idx)
        pos_c = conf.GetAtomPosition(c_idx)
        pos_d = conf.GetAtomPosition(d_idx)

        # B-C axis
        bc = (pos_c.x - pos_b.x, pos_c.y - pos_b.y, pos_c.z - pos_b.z)
        len_bc = math.sqrt(sum(x * x for x in bc))
        if len_bc < 0.01:
            return [(0, 0, 0)] * num_atoms

        u_bc = tuple(x / len_bc for x in bc)

        # For atom A: vector from B to A, then cross with BC axis
        ba = (pos_a.x - pos_b.x, pos_a.y - pos_b.y, pos_a.z - pos_b.z)
        disp_a = self._cross_product(u_bc, ba)
        len_da = math.sqrt(sum(x * x for x in disp_a))
        if len_da > 0.001:
            disp_a = tuple(x / len_da for x in disp_a)
        else:
            disp_a = (0, 0, 0)

        # For atom D: vector from C to D, then cross with BC axis (opposite sense)
        cd = (pos_d.x - pos_c.x, pos_d.y - pos_c.y, pos_d.z - pos_c.z)
        disp_d = self._cross_product(u_bc, cd)
        len_dd = math.sqrt(sum(x * x for x in disp_d))
        if len_dd > 0.001:
            disp_d = tuple(-x / len_dd for x in disp_d)
        else:
            disp_d = (0, 0, 0)

        m_a = ATOMIC_MASSES.get(atoms[a_idx][0], 12.0)
        m_d = ATOMIC_MASSES.get(atoms[d_idx][0], 12.0)
        total_inv = 1.0 / m_a + 1.0 / m_d
        w_a = (1.0 / m_a) / total_inv if total_inv > 0 else 0.5
        w_d = (1.0 / m_d) / total_inv if total_inv > 0 else 0.5

        # Scale — 시각적으로 충분히 보이는 진폭
        scale = 0.5

        displacement = [(0.0, 0.0, 0.0)] * num_atoms
        displacement[a_idx] = tuple(x * scale * w_a for x in disp_a)
        displacement[d_idx] = tuple(x * scale * w_d for x in disp_d)

        # 인접 원자 전파
        try:
            from rdkit import Chem
            mol = conf.GetOwningMol()
            displacement = self._propagate_to_neighbors(
                displacement, [a_idx, b_idx, c_idx, d_idx], mol, num_atoms)
        except Exception:
            pass

        return displacement

    @staticmethod
    def _propagate_to_neighbors(displacement, primary_indices, mol, num_atoms, damping=0.25):
        """인접 원자에 감쇠된 역방향 변위 전파 (normal mode 근사).
        primary_indices: 주 진동 원자 인덱스들
        damping: 1차 이웃에 전파되는 비율 (0.25 = 25%)"""
        try:
            primary_set = set(primary_indices)
            for pi in primary_indices:
                pd = displacement[pi]
                if sum(abs(x) for x in pd) < 0.001:
                    continue
                atom_obj = mol.GetAtomWithIdx(pi)
                neighbors = [n.GetIdx() for n in atom_obj.GetNeighbors()
                             if n.GetIdx() not in primary_set and n.GetIdx() < num_atoms]
                if not neighbors:
                    continue
                share = damping / len(neighbors)
                for ni in neighbors:
                    old = displacement[ni]
                    displacement[ni] = (
                        old[0] - pd[0] * share,
                        old[1] - pd[1] * share,
                        old[2] - pd[2] * share,
                    )
                    # 2차 이웃에도 미약한 전파 (10%)
                    n2_atom = mol.GetAtomWithIdx(ni)
                    n2_neighbors = [n.GetIdx() for n in n2_atom.GetNeighbors()
                                    if n.GetIdx() not in primary_set and n.GetIdx() != ni
                                    and n.GetIdx() < num_atoms]
                    if n2_neighbors:
                        share2 = (damping * 0.4) / len(n2_neighbors)
                        for n2i in n2_neighbors:
                            old2 = displacement[n2i]
                            displacement[n2i] = (
                                old2[0] - pd[0] * share2,
                                old2[1] - pd[1] * share2,
                                old2[2] - pd[2] * share2,
                            )
        except Exception:
            pass
        return displacement

    # ========================================================================
    # VECTOR MATH UTILITIES
    # ========================================================================

    @staticmethod
    def _cross_product(a: tuple, b: tuple) -> tuple:
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]
        )

    @staticmethod
    def _perpendicular_vector(v: tuple) -> tuple:
        """v에 수직인 임의 벡터 반환"""
        if abs(v[0]) < 0.9:
            return (0, v[2], -v[1])
        return (-v[2], 0, v[0])

    @staticmethod
    def _component_perpendicular(v: tuple, ref: tuple) -> tuple:
        """v에서 ref 방향 성분을 제거한 수직 성분"""
        dot = sum(a * b for a, b in zip(v, ref))
        perp = tuple(v[i] - dot * ref[i] for i in range(3))
        length = math.sqrt(sum(x * x for x in perp))
        if length < 0.001:
            return (0, 0, 0)
        return tuple(x / length for x in perp)


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def calculate_vibrations(smiles: str) -> VibrationResult:
    """편의 함수: SMILES로부터 진동 모드 계산"""
    engine = InternalVibrationEngine()
    return engine.calculate(smiles=smiles)
