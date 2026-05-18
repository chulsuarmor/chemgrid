# vibration_engine.py (v3.0 - Internal Vibration Mode Engine)
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
# GOLD-STANDARD VIBRATION DATABASE (textbook values for small molecules)
# Key: canonical SMILES -> list of (freq_cm, description, mode_type, ir_active, raman_active)
# Sources: NIST, Shimanouchi tables, Herzberg
# ============================================================================
GOLD_STANDARD_VIBRATIONS: Dict[str, list] = {
    # Water: 3 modes (3N-6=3, nonlinear)
    "O": [
        (3657, "O-H symmetric stretch", "stretch", True, True,
         "대칭 신축: 두 O-H 결합이 동시에 늘어남/줄어듦. 쌍극자 변화 있음 → IR 활성, 편극률 변화 → Raman 활성"),
        (3756, "O-H asymmetric stretch", "stretch", True, False,
         "비대칭 신축: 한쪽 O-H 늘어날 때 다른쪽 줄어듦. 강한 쌍극자 변화 → 강한 IR, Raman 약함"),
        (1595, "H-O-H scissoring bend", "bend", True, True,
         "가위질 굽힘: H-O-H 결합각이 변화. 쌍극자/편극률 모두 변화"),
    ],
    # CO2: 4 modes (3N-5=4, linear) - bend is doubly degenerate
    "O=C=O": [
        (1388, "C=O symmetric stretch", "stretch", False, True,
         "대칭 신축: 두 C=O가 동시에 신축. 중심대칭 분자 → 쌍극자 변화 없음(IR 비활성), 편극률 변화(Raman 활성)"),
        (2349, "C=O asymmetric stretch", "stretch", True, False,
         "비대칭 신축: 한쪽 C=O 늘어남+다른쪽 줄어듦. 강한 쌍극자 변화(IR 활성), 편극률 무변화(Raman 비활성)"),
        (667, "O=C=O bend (degenerate 1)", "bend", True, False,
         "굽힘 진동 (이중 축퇴 중 1): 면내 굽힘. 쌍극자 변화 → IR 활성, 중심대칭 → Raman 비활성"),
        (667, "O=C=O bend (degenerate 2)", "bend", True, False,
         "굽힘 진동 (이중 축퇴 중 2): 면외 굽힘. 첫번째 굽힘과 직교하는 방향"),
    ],
    # HCN: 4 modes (3N-5=4, linear) - bend is doubly degenerate
    "C#N": [
        (3311, "C-H stretch", "stretch", True, True,
         "C-H sp 신축: sp 탄소의 C-H는 s 성격이 높아 높은 주파수. IR/Raman 모두 활성"),
        (2097, "C≡N stretch", "stretch", True, True,
         "C≡N 삼중결합 신축: 강한 결합 → 높은 주파수. 극성 결합 → IR 활성"),
        (712, "H-C≡N bend (degenerate 1)", "bend", True, True,
         "H-C-N 굽힘 진동 (이중 축퇴 중 1): 면내 굽힘"),
        (712, "H-C≡N bend (degenerate 2)", "bend", True, True,
         "H-C-N 굽힘 진동 (이중 축퇴 중 2): 면외 굽힘"),
    ],
    # Formaldehyde (H2C=O): 6 modes (3N-6=6, nonlinear)
    "C=O": [
        (2783, "C-H symmetric stretch", "stretch", True, True,
         "C-H 대칭 신축: 두 C-H가 동시에 신축. 알데히드 C-H는 sp2 → ~2783 cm-1"),
        (2843, "C-H asymmetric stretch", "stretch", True, True,
         "C-H 비대칭 신축: 한쪽 C-H 늘어남+다른쪽 줄어듦"),
        (1746, "C=O stretch", "stretch", True, True,
         "C=O 이중결합 신축: 알데히드 카르보닐. 강한 IR 흡수 (극성 이중결합)"),
        (1500, "CH2 scissors", "bend", True, True,
         "CH2 가위질 진동: H-C-H 결합각 변화"),
        (1251, "CH2 wagging", "bend", True, True,
         "CH2 흔들림(wagging): 두 H가 분자 면에서 같은 방향으로 움직임"),
        (1167, "CH2 rocking", "bend", True, True,
         "CH2 흔들림(rocking): 두 H가 분자 면 내에서 같은 방향으로 움직임"),
    ],
    # Methane (CH4): 9 modes (3N-6=9), but grouped: nu1(A1) + nu3(T2,3x) stretches, nu2(E,2x) + nu4(T2,3x) bends
    "C": [
        (2917, "C-H symmetric stretch (nu1, A1)", "stretch", False, True,
         "nu1 (A1): 4개 C-H가 동시에 대칭 신축. Td 대칭 → IR 비활성, Raman 활성"),
        (3019, "C-H asymmetric stretch (nu3, T2a)", "stretch", True, True,
         "nu3 (T2): 비대칭 C-H 신축. 삼중 축퇴 중 하나. IR 활성"),
        (3019, "C-H asymmetric stretch (nu3, T2b)", "stretch", True, True,
         "nu3 (T2): 비대칭 C-H 신축. 삼중 축퇴 중 둘째"),
        (3019, "C-H asymmetric stretch (nu3, T2c)", "stretch", True, True,
         "nu3 (T2): 비대칭 C-H 신축. 삼중 축퇴 중 셋째"),
        (1534, "H-C-H deformation (nu2, Ea)", "bend", False, True,
         "nu2 (E): H-C-H 변형. 이중 축퇴. IR 비활성, Raman 활성"),
        (1534, "H-C-H deformation (nu2, Eb)", "bend", False, True,
         "nu2 (E): H-C-H 변형. 이중 축퇴 중 둘째"),
        (1306, "H-C-H deformation (nu4, T2a)", "bend", True, True,
         "nu4 (T2): H-C-H 변형. 삼중 축퇴. IR 활성"),
        (1306, "H-C-H deformation (nu4, T2b)", "bend", True, True,
         "nu4 (T2): H-C-H 변형. 삼중 축퇴 중 둘째"),
        (1306, "H-C-H deformation (nu4, T2c)", "bend", True, True,
         "nu4 (T2): H-C-H 변형. 삼중 축퇴 중 셋째"),
    ],
    # Ammonia (NH3): 6 modes (3N-6=6)
    "N": [
        (3337, "N-H symmetric stretch (nu1, A1)", "stretch", True, True,
         "nu1 (A1): 3개 N-H가 동시에 대칭 신축"),
        (3444, "N-H asymmetric stretch (nu3, Ea)", "stretch", True, True,
         "nu3 (E): 비대칭 N-H 신축. 이중 축퇴 중 하나"),
        (3444, "N-H asymmetric stretch (nu3, Eb)", "stretch", True, True,
         "nu3 (E): 비대칭 N-H 신축. 이중 축퇴 중 둘째"),
        (1627, "H-N-H scissors (nu4, Ea)", "bend", True, True,
         "nu4 (E): H-N-H 가위질. 이중 축퇴"),
        (1627, "H-N-H scissors (nu4, Eb)", "bend", True, True,
         "nu4 (E): H-N-H 가위질. 이중 축퇴 중 둘째"),
        (950, "N-H umbrella inversion (nu2, A1)", "bend", True, True,
         "nu2 (A1): 우산형 뒤집기(inversion). N 원자가 H3 평면을 통과하는 운동"),
    ],
    # Ethylene (C2H4): selected key modes
    "C=C": [
        (3106, "=C-H asymmetric stretch", "stretch", True, True, ""),
        (3026, "=C-H symmetric stretch", "stretch", False, True, ""),
        (1623, "C=C stretch", "stretch", False, True, "C=C 이중결합 대칭 신축. 비극성 → IR 약함, Raman 강함"),
        (1444, "CH2 scissors", "bend", True, True, ""),
        (1236, "CH2 rocking", "bend", True, True, ""),
        (949, "CH2 wagging", "bend", True, False, ""),
        (810, "CH2 twisting", "bend", False, True, ""),
    ],
    # Acetylene (C#C): linear, 3N-5=7, 2 degenerate bends
    "C#C": [
        (3374, "C-H symmetric stretch", "stretch", False, True, ""),
        (3289, "C-H asymmetric stretch", "stretch", True, False, ""),
        (1974, "C-C triple stretch", "stretch", False, True, "C#C 삼중결합 신축. 대칭 → Raman만 활성"),
        (730, "CCH bend (degenerate 1a)", "bend", True, False, ""),
        (730, "CCH bend (degenerate 1b)", "bend", True, False, ""),
        (612, "CCH bend (degenerate 2a)", "bend", True, False, ""),
        (612, "CCH bend (degenerate 2b)", "bend", True, False, ""),
    ],
    # Hydrogen cyanide alt SMILES
    "[H]C#N": [
        (3311, "C-H stretch", "stretch", True, True, ""),
        (2097, "C-N triple stretch", "stretch", True, True, ""),
        (712, "H-C-N bend (degenerate 1)", "bend", True, True, ""),
        (712, "H-C-N bend (degenerate 2)", "bend", True, True, ""),
    ],
}

# Calibrated force constants for more accurate harmonic frequencies
# These are tuned so that nu = sqrt(k/mu)/(2*pi*c) matches known frequencies
# Key: (atom1, atom2, bond_order) -> force constant (N/m)
CALIBRATED_FORCE_CONSTANTS: Dict[Tuple[str, str, int], float] = {
    # C-H bonds: hybridization matters, but bond order is always 1
    # sp3 C-H: target ~2960 -> k ~ 480 N/m (mu=0.923 amu)
    ("C", "H", 1): 480,
    # O-H: target ~3650 -> k ~ 780 N/m (mu=0.948 amu)
    ("O", "H", 1): 780,
    # N-H: target ~3400 -> k ~ 650 N/m (mu=0.940 amu)
    ("N", "H", 1): 650,
    # S-H: target ~2570 -> k ~ 350 N/m
    ("S", "H", 1): 350,
    # C-C single: target ~1000 -> k ~ 300
    ("C", "C", 1): 300,
    # C=C: target ~1650 -> k ~ 840
    ("C", "C", 2): 840,
    # C-C triple: target ~2150 -> k ~ 1500
    ("C", "C", 3): 1500,
    # C=O: target ~1750 -> k ~ 1200 (mu = 6.86 amu)
    ("C", "O", 2): 1200,
    # C-O single: target ~1100 -> k ~ 450
    ("C", "O", 1): 450,
    # C-N single: target ~1050 -> k ~ 380
    ("C", "N", 1): 380,
    # C=N: target ~1660 -> k ~ 900
    ("C", "N", 2): 900,
    # C-N triple: target ~2250 -> k ~ 1930 (mu = 6.46 amu)
    ("C", "N", 3): 1930,
    # C-F: target ~1100 -> k ~ 520
    ("C", "F", 1): 520,
    # C-Cl: target ~750 -> k ~ 280
    ("C", "Cl", 1): 280,
    # C-Br: target ~600 -> k ~ 230
    ("C", "Br", 1): 230,
    # C-I: target ~500 -> k ~ 170
    ("C", "I", 1): 170,
    # C-S: target ~700 -> k ~ 220
    ("C", "S", 1): 220,
    # C=S: target ~1100 -> k ~ 500
    ("C", "S", 2): 500,
    # N-O single: target ~1050 -> k ~ 370
    ("N", "O", 1): 370,
    # N=O: target ~1550 -> k ~ 800
    ("N", "O", 2): 800,
    # N-N: target ~900 -> k ~ 330
    ("N", "N", 1): 330,
    # N=N: target ~1550 -> k ~ 750
    ("N", "N", 2): 750,
    # N-N triple: target ~2330 -> k ~ 2200
    ("N", "N", 3): 2200,
    # O-O: target ~880 -> k ~ 350
    ("O", "O", 1): 350,
    # S=O: target ~1050 -> k ~ 550
    ("S", "O", 2): 550,
    # S-S: target ~500 -> k ~ 200
    ("S", "S", 1): 200,
    # P-O: target ~1000 -> k ~ 400
    ("P", "O", 1): 400,
    # P=O: target ~1280 -> k ~ 700
    ("P", "O", 2): 700,
    # Si-O: target ~1050 -> k ~ 450
    ("Si", "O", 1): 450,
    # Si-C: target ~800 -> k ~ 280
    ("Si", "C", 1): 280,
}


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

        # N-code: type guard — external callers may pass non-str smiles
        if smiles is not None and not isinstance(smiles, str):
            logger.warning("[VibrationEngine] smiles is not str: type=%s", type(smiles).__name__)
            return VibrationResult(
                modes=[], atoms=[], num_atoms=0,
                success=False, error_message=f"Invalid SMILES type: {type(smiles).__name__}"
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
        # N-code: type guard — mol must be RDKit Mol object
        if not hasattr(mol, 'GetNumAtoms'):
            logger.warning("[VibrationEngine] mol is not RDKit Mol: type=%s",
                           type(mol).__name__)
            return VibrationResult(
                modes=[], atoms=[], num_atoms=0,
                success=False, error_message=f"Invalid mol type: {type(mol).__name__}"
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
        except Exception as e:
            logger.warning("MMFF optimization failed, trying UFF: %s", e)
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            except Exception as e2:
                logger.warning("UFF optimization also failed, using initial coords: %s", e2)

        # Step 2: Extract atom data
        conf = mol.GetConformer()
        num_atoms = mol.GetNumAtoms()
        atoms = []
        for i in range(num_atoms):
            pos = conf.GetAtomPosition(i)
            sym = mol.GetAtomWithIdx(i).GetSymbol()
            # N-code: type guard — symbol must be str
            if not isinstance(sym, str):
                logger.warning("[VibrationEngine] atom symbol not str at idx %d: type=%s",
                               i, type(sym).__name__)
                sym = str(sym) if sym is not None else "C"
            atoms.append((sym, pos.x, pos.y, pos.z))

        # Step 2.5: Check gold-standard database for small well-known molecules
        gold_result = self._try_gold_standard(smiles, mol, conf, atoms, num_atoms)
        if gold_result is not None:
            return gold_result

        # Step 3: Calculate all vibration modes (empirical engine)
        modes = []

        # Detect linear molecules for correct mode counting
        is_linear = self._is_linear_molecule(mol, conf, num_atoms)

        # 3a: Bond stretch modes (with symmetric/asymmetric splitting)
        stretch_modes = self._calc_all_stretch_modes(mol, conf, atoms, num_atoms)
        modes.extend(stretch_modes)

        # 3b: Angle bending modes
        angle_modes = self._calc_all_bend_modes(mol, conf, atoms, num_atoms)
        modes.extend(angle_modes)

        # 3b2: For linear molecules, add degenerate bend modes
        if is_linear:
            for m in list(angle_modes):
                # Each bend in a linear molecule is doubly degenerate
                degen = VibrationMode(
                    frequency_cm=m.frequency_cm,
                    ir_intensity=m.ir_intensity,
                    description=m.description.replace("bend", "bend (degenerate)"),
                    displacement_vectors=self._rotate_displacement_90(
                        m.displacement_vectors, conf, m.bond_indices),
                    bond_indices=m.bond_indices,
                    mode_type="bend",
                    ir_active=m.ir_active,
                    raman_active=m.raman_active,
                )
                modes.append(degen)

        # 3c: Torsion modes (dihedral) - not for linear molecules
        if not is_linear:
            torsion_modes = self._calc_all_torsion_modes(mol, conf, atoms, num_atoms)
            modes.extend(torsion_modes)

        # Step 4: Match functional group labels
        self._assign_functional_group_labels(modes, mol, atoms)

        # Step 5: Assign IR/Raman activity & spectroscopy info
        self._assign_spectroscopy_info(modes, atoms)

        # Step 5b: Deduplicate modes with identical frequency + mode_type
        # Symmetric molecules (e.g., benzene) can produce degenerate modes where
        # multiple dihedral paths yield the same frequency and label. We group
        # them and label as "degenerate" rather than showing duplicate entries.
        modes = self._deduplicate_modes(modes)

        # Sort by frequency (ascending)
        modes.sort(key=lambda m: m.frequency_cm)

        # Filter out imaginary/zero/too-low frequencies
        modes = [m for m in modes if m.frequency_cm > 50]

        # Correct mode count: 3N-6 for nonlinear, 3N-5 for linear
        expected_modes = 3 * num_atoms - 5 if is_linear else 3 * num_atoms - 6
        max_modes = max(expected_modes, 30)
        if len(modes) > max_modes:
            # Keep highest IR intensity modes + ensure coverage of all types
            s_modes = [m for m in modes if m.mode_type == "stretch"]
            b_modes = [m for m in modes if m.mode_type == "bend"]
            t_modes = [m for m in modes if m.mode_type == "torsion"]

            # Sort each by IR intensity, keep top
            s_modes.sort(key=lambda m: m.ir_intensity, reverse=True)
            b_modes.sort(key=lambda m: m.ir_intensity, reverse=True)
            t_modes.sort(key=lambda m: m.ir_intensity, reverse=True)

            n_stretch = min(len(s_modes), max(max_modes // 2, 10))
            n_bend = min(len(b_modes), max(max_modes // 3, 8))
            n_torsion = min(len(t_modes), max(max_modes // 6, 4))

            modes = s_modes[:n_stretch] + b_modes[:n_bend] + t_modes[:n_torsion]
            modes.sort(key=lambda m: m.frequency_cm)

        return VibrationResult(
            modes=modes,
            atoms=atoms,
            num_atoms=num_atoms,
            method="Harmonic Oscillator (Empirical, Stretch+Bend+Torsion)",
            success=True
        )

    # ========================================================================
    # GOLD-STANDARD DATABASE LOOKUP
    # ========================================================================

    def _try_gold_standard(self, smiles: str, mol, conf, atoms: list,
                           num_atoms: int) -> Optional[VibrationResult]:
        """Check if molecule has gold-standard vibration data.
        Returns VibrationResult if found, None otherwise."""
        # Try canonical SMILES
        try:
            can_smiles = Chem.MolToSmiles(Chem.RemoveHs(mol))
        except Exception as e:
            logger.warning("Failed to canonicalize SMILES for gold-standard lookup: %s", e)
            can_smiles = smiles or ""

        # Search in database (try original and canonical)
        gold_data = GOLD_STANDARD_VIBRATIONS.get(can_smiles)
        if gold_data is None and smiles:
            gold_data = GOLD_STANDARD_VIBRATIONS.get(smiles)

        if gold_data is None:
            return None

        # N-code: type guard — gold_data must be a list/tuple of entries
        if not isinstance(gold_data, (list, tuple)):
            logger.warning("[VibrationEngine] gold_data is not list/tuple: type=%s",
                           type(gold_data).__name__)
            return None

        logger.info(f"[VibrationEngine] Using gold-standard data for {can_smiles}")

        modes = []
        for entry in gold_data:
            # N-code: type guard — each entry must be a list/tuple with >= 5 elements
            if not isinstance(entry, (list, tuple)) or len(entry) < 5:
                logger.warning("[VibrationEngine] gold_data entry is malformed: type=%s, len=%s",
                               type(entry).__name__, len(entry) if isinstance(entry, (list, tuple)) else "N/A")
                continue
            freq, desc, mode_type, ir_act, raman_act = entry[0], entry[1], entry[2], entry[3], entry[4]
            spect_note = entry[5] if len(entry) > 5 else ""

            # Generate approximate displacement vectors based on mode type
            displacement = [(0.0, 0.0, 0.0)] * num_atoms

            # Try to generate meaningful displacements from 3D coords
            if mode_type == "stretch" and num_atoms >= 2:
                displacement = self._generate_gold_stretch_displacement(
                    desc, mol, conf, atoms, num_atoms)
            elif mode_type == "bend" and num_atoms >= 3:
                displacement = self._generate_gold_bend_displacement(
                    desc, mol, conf, atoms, num_atoms)

            # IR intensity from activity
            ir_intensity = 0.7 if ir_act else 0.05

            # [M683 FIX] \uc0ac\uc6a9\uc790 LV.14 item 22 \u2014 "\uc9c4\ub3d9\ubaa8\ub4dc \ub178\ub780 \uad6c\uccb4 4\uac1c\uc5d0\ub9cc \uc50c\uc6cc\uc9d0" \ubc84\uadf8 \ud574\uc18c
            # \uae30\uc874: bond_indices=tuple(range(min(num_atoms, 4))) \u2192 \ud56d\uc0c1 4\uac1c \uc81c\ud55c
            # \uc218\uc815: displacement \ubca1\ud130 \ud06c\uae30 > 1e-6 \uc778 \uc6d0\uc790\ub9cc \uc120\ud0dd (\uc2e4\uc81c \uc9c4\ub3d9 \uc6d0\uc790)
            # fallback: non-zero \uc5c6\uc73c\uba74 \uc804\uccb4 \uc6d0\uc790 \uc0ac\uc6a9
            # Rule I: 1e-6 \ub9e4\uc9c1\ub118\ubc84 \u2014 \ubd80\ub3d9\uc18c\uc218 \ube44\uad50 \ucd5c\uc18c \uc758\ubbf8 \ub2e8\uc704 (Bohr \ub2e8\uc704 \ubcc0\uc704)
            if displacement:
                _nz_idx = tuple(
                    i for i, (dx, dy, dz) in enumerate(displacement)
                    if (dx * dx + dy * dy + dz * dz) > 1e-6  # [MAGIC:1e-6] \ucd5c\uc18c \ubcc0\uc704 \uc784\uacc4\uac12 (Bohr \ub2e8\uc704)
                )
                # [M751 F5-13 FIX] \uc9c4\ub3d9\ubaa8\ub4dc 4\uac1c \uace0\uc815 \ubc84\uadf8 \uc7ac\ubc1c \ubc29\uc9c0
                # \uacbd\ud5d8\uc801 \uc5d4\uc9c4: \ud2b9\uc815 bond \uc6d0\uc790\ub9cc displacement \u2192 threshold \ud6c4 4\uac1c \ubbf8\ub9cc \ub0a8\uc74c
                # \uc218\uc815: non-zero\uac00 \ub108\ubb34 \uc801\uc73c\uba74 \uc804\uccb4 \uc6d0\uc790\ub85c fallback (\uc2e4\uc81c \ubd84\uc790 \ud06c\uae30\uc5d0 \ube44\ub840 \ud45c\uc2dc)
                _MIN_DISPLAY = max(6, num_atoms // 3)  # [MAGIC:6,//3] \ucd5c\uc18c 6\uac1c \ub610\ub294 \ubd84\uc790\uc758 1/3
                if len(_nz_idx) < _MIN_DISPLAY:
                    _bond_indices = tuple(range(num_atoms))
                else:
                    _bond_indices = _nz_idx
            else:
                _bond_indices = tuple(range(num_atoms))
            mode = VibrationMode(
                frequency_cm=freq,
                ir_intensity=ir_intensity,
                description=f"{desc} ({freq:.0f} cm\u207b\u00b9)",
                displacement_vectors=displacement,
                bond_indices=_bond_indices,
                mode_type=mode_type,
                ir_active=ir_act,
                raman_active=raman_act,
                spectroscopy_note=spect_note,
            )
            if freq > 0:
                mode.wavelength_um = 10000.0 / freq
            modes.append(mode)

        return VibrationResult(
            modes=modes,
            atoms=atoms,
            num_atoms=num_atoms,
            method="Gold Standard (Textbook/NIST)",
            success=True,
        )

    def _generate_gold_stretch_displacement(self, desc: str, mol, conf,
                                             atoms: list, num_atoms: int) -> list:
        """Generate displacement vectors for gold-standard stretch modes."""
        # Rule N: 타입 가드 — ATOMIC_MASSES는 모듈 상수 dict
        assert isinstance(ATOMIC_MASSES, dict), "ATOMIC_MASSES must be dict"
        displacement = [(0.0, 0.0, 0.0)] * num_atoms
        desc_lower = desc.lower()

        # Find the relevant bond
        target_pairs = []
        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            si, sj = atoms[i][0], atoms[j][0]

            if "o-h" in desc_lower and set([si, sj]) == {"O", "H"}:
                target_pairs.append((i, j))
            elif "n-h" in desc_lower and set([si, sj]) == {"N", "H"}:
                target_pairs.append((i, j))
            elif "c-h" in desc_lower and set([si, sj]) == {"C", "H"}:
                target_pairs.append((i, j))
            elif "c=o" in desc_lower and set([si, sj]) == {"C", "O"}:
                target_pairs.append((i, j))
            elif "c=c" in desc_lower and si == "C" and sj == "C":
                target_pairs.append((i, j))
            elif ("c-n" in desc_lower or "c≡n" in desc_lower) and set([si, sj]) == {"C", "N"}:
                target_pairs.append((i, j))
            elif "c-c" in desc_lower and si == "C" and sj == "C":
                target_pairs.append((i, j))

        if not target_pairs:
            # Fallback: use first bond
            if mol.GetNumBonds() > 0:
                b = mol.GetBondWithIdx(0)
                target_pairs = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx())]

        is_symmetric = "symmetric" in desc_lower and "asymmetric" not in desc_lower
        is_asymmetric = "asymmetric" in desc_lower

        for idx, (i, j) in enumerate(target_pairs):
            m_i = ATOMIC_MASSES.get(atoms[i][0], 12.0)
            m_j = ATOMIC_MASSES.get(atoms[j][0], 12.0)
            displacement = self._calc_stretch_displacement(i, j, conf, m_i, m_j, num_atoms)

            if is_asymmetric and idx > 0:
                # Reverse direction for second bond in asymmetric mode
                for k in range(num_atoms):
                    old = displacement[k]
                    if k == i or k == j:
                        displacement[k] = (-old[0], -old[1], -old[2])
            break  # Use first matching pair for displacement

        return displacement

    def _generate_gold_bend_displacement(self, desc: str, mol, conf,
                                          atoms: list, num_atoms: int) -> list:
        """Generate displacement vectors for gold-standard bend modes."""
        # Rule N: 타입 가드 — ATOMIC_MASSES는 모듈 상수 dict
        assert isinstance(ATOMIC_MASSES, dict), "ATOMIC_MASSES must be dict"
        displacement = [(0.0, 0.0, 0.0)] * num_atoms

        # Find a central atom with 2+ neighbors
        for atom in mol.GetAtoms():
            neighbors = [n.GetIdx() for n in atom.GetNeighbors()]
            if len(neighbors) >= 2:
                center = atom.GetIdx()
                a_idx, c_idx = neighbors[0], neighbors[1]
                m_a = ATOMIC_MASSES.get(atoms[a_idx][0], 12.0)
                m_b = ATOMIC_MASSES.get(atoms[center][0], 12.0)
                m_c = ATOMIC_MASSES.get(atoms[c_idx][0], 12.0)
                displacement = self._calc_bend_displacement(
                    a_idx, center, c_idx, conf, m_a, m_b, m_c, num_atoms)
                break

        return displacement

    # ========================================================================
    # LINEAR MOLECULE DETECTION
    # ========================================================================

    def _is_linear_molecule(self, mol, conf, num_atoms: int) -> bool:
        """Detect if molecule is linear (all atoms collinear)."""
        if num_atoms <= 2:
            return True
        if num_atoms > 4:
            return False  # Very few molecules with >4 atoms are linear

        # Check if all atoms lie on a line (max deviation < 5 degrees)
        pos = [conf.GetAtomPosition(i) for i in range(num_atoms)]

        # Use first two atoms to define line direction
        dx = pos[1].x - pos[0].x
        dy = pos[1].y - pos[0].y
        dz = pos[1].z - pos[0].z
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 0.01:
            return False
        ux, uy, uz = dx/length, dy/length, dz/length

        for i in range(2, num_atoms):
            vx = pos[i].x - pos[0].x
            vy = pos[i].y - pos[0].y
            vz = pos[i].z - pos[0].z
            vlen = math.sqrt(vx*vx + vy*vy + vz*vz)
            if vlen < 0.01:
                continue
            # Cross product magnitude = sin(angle) * |u| * |v|
            cx = uy*vz - uz*vy
            cy = uz*vx - ux*vz
            cz = ux*vy - uy*vx
            cross_mag = math.sqrt(cx*cx + cy*cy + cz*cz)
            sin_angle = cross_mag / vlen  # |u|=1
            if sin_angle > 0.087:  # > ~5 degrees
                return False

        return True

    def _rotate_displacement_90(self, displacement: list, conf,
                                 bond_indices: tuple) -> list:
        """Rotate displacement vectors 90 degrees around the molecular axis
        to create the degenerate partner of a bend mode in linear molecules."""
        if not bond_indices or len(bond_indices) < 2:
            return displacement

        # Get molecular axis direction from first two atoms in bond_indices
        i, j = bond_indices[0], bond_indices[1]
        pos_i = conf.GetAtomPosition(i)
        pos_j = conf.GetAtomPosition(j)
        ax = pos_j.x - pos_i.x
        ay = pos_j.y - pos_i.y
        az = pos_j.z - pos_i.z
        alen = math.sqrt(ax*ax + ay*ay + az*az)
        if alen < 0.01:
            return displacement
        ax, ay, az = ax/alen, ay/alen, az/alen

        # Rotate each displacement vector 90 degrees around the axis
        # Using Rodrigues' rotation formula with theta=pi/2
        result = []
        for dx, dy, dz in displacement:
            # d_rot = d*cos(90) + (axis x d)*sin(90) + axis*(axis.d)*(1-cos(90))
            # cos(90)=0, sin(90)=1
            # d_rot = (axis x d) + axis*(axis.d)
            cross_x = ay*dz - az*dy
            cross_y = az*dx - ax*dz
            cross_z = ax*dy - ay*dx
            dot = ax*dx + ay*dy + az*dz
            rx = cross_x + ax*dot
            ry = cross_y + ay*dot
            rz = cross_z + az*dot
            result.append((rx, ry, rz))
        return result

    # ========================================================================
    # SYMMETRIC/ASYMMETRIC STRETCH MODE SPLITTING
    # ========================================================================

    def _calc_all_stretch_modes(self, mol, conf, atoms, num_atoms) -> list:
        """Calculate all stretch modes with symmetric/asymmetric splitting
        for equivalent bonds (e.g., two O-H in water, two C=O in CO2)."""
        # First, compute raw stretch modes per bond
        raw_modes = []
        for bond in mol.GetBonds():
            mode = self._calc_stretch_mode(bond, mol, conf, atoms, num_atoms)
            if mode:
                raw_modes.append((bond, mode))

        # Group equivalent bonds (same atom types and bond order)
        groups: Dict[str, list] = {}
        for bond, mode in raw_modes:
            i = bond.GetBeginAtomIdx()
            j = bond.GetEndAtomIdx()
            si, sj = atoms[i][0], atoms[j][0]
            bt = int(round(bond.GetBondTypeAsDouble()))
            key = tuple(sorted([si, sj])) + (bt,)
            groups.setdefault(str(key), []).append((bond, mode))

        result_modes = []
        for key, group in groups.items():
            if len(group) == 1:
                # Single bond of this type - no splitting
                result_modes.append(group[0][1])
            elif len(group) >= 2:
                # Multiple equivalent bonds - create sym/asym pairs
                base_freq = group[0][1].frequency_cm
                base_mode = group[0][1]

                # Coupling constant: symmetric is slightly lower, asymmetric higher
                # Typical splitting: ~50-100 cm-1 for X-H bonds
                bond0 = group[0][0]
                i0, j0 = bond0.GetBeginAtomIdx(), bond0.GetEndAtomIdx()
                s0, s1 = atoms[i0][0], atoms[j0][0]

                # Estimate coupling based on shared central atom
                # More coupling for lighter atoms
                if "H" in (s0, s1):
                    coupling_frac = 0.015  # ~1.5% splitting for X-H bonds
                else:
                    coupling_frac = 0.008  # smaller for heavier bonds

                freq_sym = base_freq * (1.0 - coupling_frac)
                freq_asym = base_freq * (1.0 + coupling_frac)

                # Symmetric mode
                sym_mode = VibrationMode(
                    frequency_cm=freq_sym,
                    ir_intensity=base_mode.ir_intensity * 0.8,
                    description=base_mode.description.replace(" stretch",
                                                               " symmetric stretch"),
                    displacement_vectors=base_mode.displacement_vectors,
                    bond_indices=base_mode.bond_indices,
                    mode_type="stretch",
                )
                result_modes.append(sym_mode)

                # Asymmetric mode
                asym_mode = VibrationMode(
                    frequency_cm=freq_asym,
                    ir_intensity=base_mode.ir_intensity,
                    description=base_mode.description.replace(" stretch",
                                                                " asymmetric stretch"),
                    displacement_vectors=base_mode.displacement_vectors,
                    bond_indices=base_mode.bond_indices,
                    mode_type="stretch",
                )
                result_modes.append(asym_mode)

                # If more than 2 equivalent bonds, add remaining as-is
                for extra_bond, extra_mode in group[2:]:
                    result_modes.append(extra_mode)

        return result_modes

    # ========================================================================
    # STRETCH MODES
    # ========================================================================

    def _calc_stretch_mode(self, bond, mol, conf, atoms, num_atoms) -> Optional[VibrationMode]:
        """단일 결합의 stretch 진동 모드 계산"""
        # Rule N: 타입 가드 — 상수 dict 확인
        assert isinstance(ATOMIC_MASSES, dict) and isinstance(FORCE_CONSTANTS, dict)
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
        # N-code: type guard — force constant must be numeric
        if not isinstance(k, (int, float)):
            logger.warning("[VibrationEngine] force constant not numeric for %s-%s: type=%s",
                           sym_i, sym_j, type(k).__name__)
            return None
        if k <= 0:
            return None

        # Apply hybridization correction for C-H bonds
        # sp C-H: ~3300 cm-1, sp2 C-H: ~3050 cm-1, sp3 C-H: ~2960 cm-1
        if set([sym_i, sym_j]) == {"C", "H"}:
            c_idx = i if sym_i == "C" else j
            c_atom = mol.GetAtomWithIdx(c_idx)
            hyb = str(c_atom.GetHybridization())
            if "SP3" in hyb:
                k = 480    # sp3 C-H → ~2960 cm-1
            elif "SP2" in hyb:
                k = 510    # sp2 C-H → ~3050 cm-1
            elif "SP" in hyb:
                k = 590    # sp C-H → ~3300 cm-1 (stronger due to more s character)

        # Reduced mass
        m_i = ATOMIC_MASSES.get(sym_i, 12.0)
        m_j = ATOMIC_MASSES.get(sym_j, 12.0)
        mu_amu = (m_i * m_j) / (m_i + m_j)
        mu_kg = mu_amu * AMU_TO_KG

        # Frequency: v = sqrt(k/mu) / (2*pi)  [Hz]
        freq_hz = math.sqrt(k / mu_kg) / TWO_PI
        freq_cm = freq_hz / SPEED_OF_LIGHT

        # IR intensity estimate
        ir_intensity = self._estimate_ir_intensity(sym_i, sym_j, bond_order)

        # Description with hybridization info for C-H
        bond_type_str = {1: "-", 2: "=", 3: "\u2261"}.get(bond_order, "-")
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
        # Rule N: 타입 가드 — 상수 dict 확인
        assert isinstance(ATOMIC_MASSES, dict) and isinstance(BEND_FORCE_CONSTANTS, dict)
        sym_a = atoms[a_idx][0]
        sym_b = atoms[b_idx][0]
        sym_c = atoms[c_idx][0]

        # Get bend force constant
        k_bend = self._get_bend_force_constant(sym_a, sym_b, sym_c)
        # N-code: type guard — bend force constant must be numeric
        if not isinstance(k_bend, (int, float)):
            logger.warning("[VibrationEngine] k_bend not numeric for %s-%s-%s: type=%s",
                           sym_a, sym_b, sym_c, type(k_bend).__name__)
            return None

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
        # Rule N: 타입 가드 — 상수 dict 확인
        assert isinstance(TORSION_FORCE_CONSTANTS, dict) and isinstance(ATOMIC_MASSES, dict)
        sym_a = atoms[a_idx][0]
        sym_b = atoms[b_idx][0]
        sym_c = atoms[c_idx][0]
        sym_d = atoms[d_idx][0]

        k_tor = TORSION_FORCE_CONSTANTS.get(tor_type, 0.03)
        # N-code: type guard — force constant must be numeric
        if not isinstance(k_tor, (int, float)):
            logger.warning("[VibrationEngine] k_tor not numeric for %s: type=%s",
                           tor_type, type(k_tor).__name__)
            k_tor = 0.03

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
    # DEDUPLICATION
    # ========================================================================

    def _deduplicate_modes(self, modes: List[VibrationMode]) -> List[VibrationMode]:
        """중복 모드 제거: 동일 주파수(1 cm⁻¹ 이내) + 동일 mode_type 인 모드들을 병합.
        축퇴(degenerate) 모드는 첫 번째를 대표로 유지하고 설명에 "(degenerate)" 태그 추가.
        완전히 동일한 원자 집합을 가진 모드는 하나만 유지한다.
        """
        # N-code: type guard — modes must be list
        if not isinstance(modes, list):
            logger.warning("[VibrationEngine] modes not list in deduplicate: type=%s",
                           type(modes).__name__)
            return []
        if not modes:
            return modes

        FREQ_TOL = 1.0  # cm⁻¹ tolerance for "same frequency"

        kept: List[VibrationMode] = []
        # Track which modes have already been merged
        merged_indices: set = set()

        for i, m_i in enumerate(modes):
            if i in merged_indices:
                continue

            # Find all modes that are degenerate with m_i
            degen_group = [i]
            for j in range(i + 1, len(modes)):
                if j in merged_indices:
                    continue
                m_j = modes[j]
                if (m_j.mode_type == m_i.mode_type and
                        abs(m_j.frequency_cm - m_i.frequency_cm) <= FREQ_TOL):
                    # Same atom set → true duplicate; different atom set → genuine degeneracy
                    degen_group.append(j)
                    merged_indices.add(j)

            if len(degen_group) == 1:
                # No degeneracy — keep as-is
                kept.append(m_i)
            else:
                # Genuine degenerate modes: keep first representative, update label
                # Check if atom sets are truly identical (pure duplicate) or different paths
                atom_sets = [frozenset(modes[k].bond_indices) for k in degen_group]
                all_same_atoms = len(set(atom_sets)) == 1

                if all_same_atoms:
                    # Pure artifact duplicate — keep only one, no label change
                    kept.append(m_i)
                else:
                    # Physics-valid degenerate modes — keep first, annotate
                    degen_count = len(degen_group)
                    # Strip any existing "(degenerate)" suffix before re-adding
                    base_desc = m_i.description
                    if "(degenerate" in base_desc:
                        base_desc = base_desc[:base_desc.index("(degenerate")].strip()
                    new_mode = VibrationMode(
                        frequency_cm=m_i.frequency_cm,
                        ir_intensity=m_i.ir_intensity,
                        description=f"{base_desc} (×{degen_count} degenerate)",
                        displacement_vectors=m_i.displacement_vectors,
                        bond_indices=m_i.bond_indices,
                        mode_type=m_i.mode_type,
                        ir_active=m_i.ir_active,
                        raman_active=m_i.raman_active,
                        ir_explanation=m_i.ir_explanation,
                    )
                    kept.append(new_mode)

        return kept

    # ========================================================================
    # FUNCTIONAL GROUP LABELING
    # ========================================================================

    def _assign_functional_group_labels(self, modes: List[VibrationMode],
                                         mol, atoms: list):
        """작용기 매칭으로 정확한 설명 부여"""
        # N-code: type guard — modes and atoms must be lists
        if not isinstance(modes, list) or not isinstance(atoms, list):
            logger.warning("[VibrationEngine] modes/atoms type error: modes=%s, atoms=%s",
                           type(modes).__name__, type(atoms).__name__)
            return
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

        # Mode type description in Korean — Rule N: isinstance for literal dicts
        type_kr: dict = {"stretch": "신축 진동", "bend": "굽힘 진동", "torsion": "비틀림 진동"}
        type_en: dict = {"stretch": "stretching", "bend": "bending", "torsion": "torsion"}
        assert isinstance(type_kr, dict) and isinstance(type_en, dict)
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
        """힘 상수 조회 - calibrated values first, then original, then fallback"""
        # Rule N: 타입 가드 — 상수 dict 확인
        assert isinstance(CALIBRATED_FORCE_CONSTANTS, dict) and isinstance(FORCE_CONSTANTS, dict)
        # 1. Try calibrated force constants first (more accurate)
        k = CALIBRATED_FORCE_CONSTANTS.get((sym_a, sym_b, order))
        if k is not None:
            return k
        k = CALIBRATED_FORCE_CONSTANTS.get((sym_b, sym_a, order))
        if k is not None:
            return k

        # 2. Try original force constants
        k = FORCE_CONSTANTS.get((sym_a, sym_b, order))
        if k is not None:
            return k
        k = FORCE_CONSTANTS.get((sym_b, sym_a, order))
        if k is not None:
            return k

        # 3. Fallback: similar bond estimation
        for test_order in [order, 1, 2]:
            for table in [CALIBRATED_FORCE_CONSTANTS, FORCE_CONSTANTS]:
                # Rule N: isinstance guard for table
                if not isinstance(table, dict): table = {}
                k = table.get((sym_a, sym_b, test_order))
                if k is not None:
                    return k * (order / test_order if test_order > 0 else 1)
                k = table.get((sym_b, sym_a, test_order))
                if k is not None:
                    return k * (order / test_order if test_order > 0 else 1)

        # 4. Generic fallback
        return 300.0

    def _get_bend_force_constant(self, sym_a: str, sym_b: str, sym_c: str) -> float:
        """결합각 bending 힘 상수 조회"""
        # Rule N: 타입 가드 — 상수 dict
        assert isinstance(BEND_FORCE_CONSTANTS, dict)
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
        except Exception as e:
            logger.warning("Failed to propagate displacement to neighbors: %s", e)

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

        # Scale — 시각적으로 충분히 보이는 진폭 (0.8: 굽힘 가시성 개선)
        scale = 0.8

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
        except Exception as e:
            logger.warning("Failed to propagate bending displacement to neighbors: %s", e)

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

        sym_a_disp = atoms[a_idx][0] if isinstance(atoms[a_idx], (list, tuple)) and len(atoms[a_idx]) > 0 else "C"
        sym_d_disp = atoms[d_idx][0] if isinstance(atoms[d_idx], (list, tuple)) and len(atoms[d_idx]) > 0 else "C"
        m_a = ATOMIC_MASSES.get(sym_a_disp, 12.0)
        m_d = ATOMIC_MASSES.get(sym_d_disp, 12.0)
        total_inv = 1.0 / m_a + 1.0 / m_d
        w_a = (1.0 / m_a) / total_inv if total_inv > 0 else 0.5
        w_d = (1.0 / m_d) / total_inv if total_inv > 0 else 0.5

        # Scale — 시각적으로 충분히 보이는 진폭 (0.7: 비틀림 가시성 개선)
        scale = 0.7

        displacement = [(0.0, 0.0, 0.0)] * num_atoms
        displacement[a_idx] = tuple(x * scale * w_a for x in disp_a)
        displacement[d_idx] = tuple(x * scale * w_d for x in disp_d)

        # 인접 원자 전파
        try:
            from rdkit import Chem
            mol = conf.GetOwningMol()
            displacement = self._propagate_to_neighbors(
                displacement, [a_idx, b_idx, c_idx, d_idx], mol, num_atoms)
        except Exception as e:
            logger.warning("Failed to propagate torsion displacement to neighbors: %s", e)

        return displacement

    @staticmethod
    def _propagate_to_neighbors(displacement, primary_indices, mol, num_atoms, damping=0.30):
        """인접 원자에 감쇠된 역방향 변위 전파 (normal mode 근사).
        primary_indices: 주 진동 원자 인덱스들
        damping: 1차 이웃에 전파되는 비율 (0.30 = 30%)"""
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
        except Exception as e:
            logger.warning("Neighbor propagation calculation failed: %s", e)
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
