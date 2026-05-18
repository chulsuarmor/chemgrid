"""고분자 물성 예측 엔진 (Polymer Property Prediction Engine).

Van Krevelen 그룹 기여법(Group Contribution Method)을 사용하여
단량체 SMILES로부터 고분자의 물리적·기계적·열적 특성을 예측한다.

지원 기능:
    1. 중합 가능 여부 판별 (첨가/축합/개환)
    2. 단량체 → 반복단위 변환
    3. 그룹 기여법 기반 물성 예측 (밀도, Tg, Tm, Td, 인장강도, 영률 등)
    4. 골드 스탠더드 DB (15+ 주요 고분자 문헌값)

References:
    - Van Krevelen, D.W. "Properties of Polymers", 4th Ed., Elsevier, 2009
    - Fedors, R.F. Polym. Eng. Sci. 14, 147 (1974)
    - Boyer-Beaman rule: Tg/Tm ≈ 0.5~0.67
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, AllChem, rdMolDescriptors, Draw
    from rdkit import RDLogger
    RDLogger.DisableLog('rdApp.*')
    RDKIT_OK = True
except ImportError:
    RDKIT_OK = False
    logger.warning("RDKit not available — polymer engine disabled")


# ═══════════════════════════════════════════════════════════════════
# 데이터 클래스
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PolymerizationResult:
    """중합 가능 여부 판별 결과."""
    possible: bool
    poly_type: str              # "addition" | "condensation" | "ring_opening" | "none"
    repeat_unit_smiles: str     # [*] 포함 반복단위 SMILES
    repeat_unit_display: str    # 화면 표시용 (예: "-[CF2-CF2]n-")
    monomer_smiles: str
    confidence: float           # 0.0~1.0


@dataclass
class PolymerProperties:
    """고분자 물성 예측 결과 전체."""
    monomer_smiles: str
    repeat_unit_smiles: str
    polymer_name: str
    polymer_name_kr: str
    poly_type: str
    M_repeat: float             # g/mol (반복단위 분자량)
    # 일반 물성
    density: float              # g/cm³
    solubility_param: float     # (MJ/m³)^0.5
    refractive_index: float
    # 열적 특성
    Tg: float                   # ℃ (유리전이온도)
    Tm: float                   # ℃ (녹는점)
    Td: float                   # ℃ (열분해온도)
    max_service_temp: float     # ℃
    CTE: float                  # ×10⁻⁶/K (열팽창계수)
    thermal_conductivity: float # W/(m·K)
    # 기계적 특성
    tensile_strength: float     # MPa
    youngs_modulus: float       # MPa
    elongation_at_break: float  # %
    # 메타
    group_decomposition: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    is_gold_standard: bool = False


# ═══════════════════════════════════════════════════════════════════
# 그룹 기여 상수 테이블 (Van Krevelen / Fedors 기반)
# ═══════════════════════════════════════════════════════════════════
# Ecoh: 응집 에너지 (J/mol)
# V:    몰 부피 (cm³/mol) at 298K
# Yg:   유리전이 함수 (K·g/mol)
# Fdi:  분산 용해도 (J^0.5·cm^1.5/mol)
# Fpi:  극성 용해도 (J^0.5·cm^1.5/mol)
# Ehi:  수소결합 에너지 (J/mol)
# Rm:   몰 굴절 (cm³/mol)

GROUP_CONTRIBUTIONS: Dict[str, Dict[str, float]] = {
    # ── 탄화수소 기본 ──
    "-CH3":     {"Ecoh": 4710,  "V": 33.5, "Yg": 2700,  "Fdi": 420,  "Fpi": 0,   "Ehi": 0,     "Rm": 5.64},
    "-CH2-":    {"Ecoh": 4940,  "V": 16.1, "Yg": 2700,  "Fdi": 270,  "Fpi": 0,   "Ehi": 0,     "Rm": 4.65},
    ">CH-":     {"Ecoh": 3430,  "V": -1.0, "Yg": 2700,  "Fdi": 80,   "Fpi": 0,   "Ehi": 0,     "Rm": 3.47},
    ">C<":      {"Ecoh": 1470,  "V": -19.2,"Yg": 2700,  "Fdi": -70,  "Fpi": 0,   "Ehi": 0,     "Rm": 2.42},
    "=CH2":     {"Ecoh": 4310,  "V": 28.5, "Yg": 2200,  "Fdi": 400,  "Fpi": 0,   "Ehi": 0,     "Rm": 5.50},
    "=CH-":     {"Ecoh": 4310,  "V": 13.5, "Yg": 2200,  "Fdi": 200,  "Fpi": 0,   "Ehi": 0,     "Rm": 4.50},
    "=C<":      {"Ecoh": 4310,  "V": -5.5, "Yg": 2200,  "Fdi": 70,   "Fpi": 0,   "Ehi": 0,     "Rm": 3.40},
    # ── 할로겐 (Yg: gold standard 역산 보정 2026-03-27) ──
    "-F":       {"Ecoh": 4190,  "V": 18.0, "Yg": 9000,  "Fdi": 220,  "Fpi": 0,   "Ehi": 0,     "Rm": 0.95},   # PVF Tg=40℃ 역산
    "-CF2-":    {"Ecoh": 4190,  "V": 23.1, "Yg": 12200, "Fdi": 150,  "Fpi": 0,   "Ehi": 0,     "Rm": 5.02},   # PVDF Tg=-40℃ 역산
    "-CF3":     {"Ecoh": 4190,  "V": 39.3, "Yg": 15000, "Fdi": 200,  "Fpi": 0,   "Ehi": 0,     "Rm": 5.97},   # CF2 비례 추정
    "-Cl":      {"Ecoh": 11550, "V": 24.0, "Yg": 17100, "Fdi": 450,  "Fpi": 550, "Ehi": 400,   "Rm": 5.97},   # PVC Tg=87℃ 역산; 다중-Cl은 _rdkit_correct_Tg에서 감쇠 보정
    "-Br":      {"Ecoh": 15490, "V": 30.0, "Yg": 20000, "Fdi": 550,  "Fpi": 0,   "Ehi": 0,     "Rm": 8.88},   # Cl 비례 추정
    # ── 산소 함유 ──
    "-OH":      {"Ecoh": 29800, "V": 10.0, "Yg": 10350, "Fdi": 210,  "Fpi": 500, "Ehi": 20000, "Rm": 2.55},   # PVA Tg=85℃ 역산
    "-O-":      {"Ecoh": 3350,  "V": 3.8,  "Yg": 3700,  "Fdi": 100,  "Fpi": 400, "Ehi": 3000,  "Rm": 1.64},   # PEO Tg=-67℃ 역산
    "-CO-":     {"Ecoh": 17370, "V": 10.8, "Yg": 8000,  "Fdi": 290,  "Fpi": 770, "Ehi": 2000,  "Rm": 5.09},
    "-COO-":    {"Ecoh": 18000, "V": 18.0, "Yg": 18000, "Fdi": 390,  "Fpi": 490, "Ehi": 7000,  "Rm": 6.73},  # PVAc Tg=30℃ 역산
    "-COOH":    {"Ecoh": 27630, "V": 38.0, "Yg": 21500, "Fdi": 530,  "Fpi": 420, "Ehi": 10000, "Rm": 7.28},  # PAA Tg=106℃ 역산; V=38(H-bond free volume 보정, Van Krevelen V=28.5+free vol ~10)
    "-CHO":     {"Ecoh": 21350, "V": 22.3, "Yg": 10000, "Fdi": 470,  "Fpi": 800, "Ehi": 4500,  "Rm": 5.73},
    # ── 질소 함유 ──
    "-NH2":     {"Ecoh": 12560, "V": 19.2, "Yg": 8400,  "Fdi": 280,  "Fpi": 0,   "Ehi": 8400,  "Rm": 4.03},
    "-NH-":     {"Ecoh": 8370,  "V": 4.5,  "Yg": 6500,  "Fdi": 160,  "Fpi": 210, "Ehi": 3100,  "Rm": 2.93},
    ">N-":      {"Ecoh": 4190,  "V": -9.0, "Yg": 5000,  "Fdi": 20,   "Fpi": 800, "Ehi": 5000,  "Rm": 1.76},
    "-CONH-":   {"Ecoh": 33490, "V": 9.5,  "Yg": 20000, "Fdi": 450,  "Fpi": 980, "Ehi": 12600, "Rm": 7.96},
    "-CN":      {"Ecoh": 25530, "V": 24.0, "Yg": 14100, "Fdi": 430,  "Fpi": 1100,"Ehi": 2500,  "Rm": 5.46},   # PAN Tg=95℃ 역산
    "-NO2":     {"Ecoh": 15360, "V": 32.0, "Yg": 9000,  "Fdi": 500,  "Fpi": 1070,"Ehi": 1500,  "Rm": 7.30},
    # ── 황 함유 ──
    "-S-":      {"Ecoh": 14140, "V": 12.0, "Yg": 5000,  "Fdi": 440,  "Fpi": 0,   "Ehi": 0,     "Rm": 7.69},
    "-SO2-":    {"Ecoh": 23430, "V": 22.3, "Yg": 14000, "Fdi": 600,  "Fpi": 800, "Ehi": 4000,  "Rm": 8.04},
    # ── 방향족 ──
    "p-C6H4-":  {"Ecoh": 31940, "V": 52.4, "Yg": 35000, "Fdi": 1270, "Fpi": 110, "Ehi": 0,     "Rm": 25.03},  # PET 기반 추정
    "-C6H5":    {"Ecoh": 37280, "V": 71.4, "Yg": 33400, "Fdi": 1520, "Fpi": 110, "Ehi": 0,     "Rm": 25.36},  # PS Tg=100℃ 역산
    # ── 규소 ──
    "-Si(CH3)2-O-": {"Ecoh": 11200, "V": 55.0, "Yg": 3000, "Fdi": 500, "Fpi": 0, "Ehi": 0,    "Rm": 18.50},
}


# ═══════════════════════════════════════════════════════════════════
# 그룹 SMARTS 매칭 패턴 (큰 그룹부터 매칭하여 이중 계수 방지)
# ═══════════════════════════════════════════════════════════════════

GROUP_SMARTS: List[Tuple[str, str]] = [
    # 큰 그룹 우선
    ("-Si(CH3)2-O-", "[Si]([CH3])([CH3])[O]"),
    ("p-C6H4-",       "[cR1]([!#1;!c])1[cR1][cR1][cR1]([!#1;!c])[cR1][cR1]1"),  # 방향족 파라-이치환 (in-chain, PET형): 비방향족 치환기 2개
    ("-C6H5",         "[cR1]1[cR1][cR1][cR1][cR1][cR1]1"),  # 방향족 6원환 (pendant phenyl 포함, p-C6H4- 매치 후 나머지)
    ("-CF3",          "[CX4](F)(F)F"),
    ("-CF2-",         "[CX4](F)(F)([!F])[!F]"),
    ("-CONH-",        "[CX3](=O)[NX3H1]"),
    ("-COO-",         "[CX3](=O)[OX2][#6]"),
    ("-COOH",         "[CX3](=O)[OX2H1]"),
    ("-CO-",          "[CX3](=O)([#6])[#6]"),
    ("-CHO",          "[CX3H1](=O)"),
    ("-NO2",          "[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    ("-SO2-",         "[SX4](=O)(=O)"),
    ("-CN",           "[CX2]#[NX1]"),
    ("-NH2",          "[NX3H2]"),
    ("-NH-",          "[NX3H1]([!H])([!H])"),
    (">N-",           "[NX3H0]([!H])([!H])([!H])"),
    ("-OH",           "[OX2H1]"),
    ("-O-",           "[OX2H0]([#6])[#6]"),
    ("-S-",           "[SX2]([#6])[#6]"),
    ("-F",            "[FX1]"),
    ("-Cl",           "[ClX1]"),
    ("-Br",           "[BrX1]"),
    # 탄화수소 (마지막)
    ("=CH2",          "[CH2]=[CX3]"),
    ("=CH-",          "[CH1]=[CX3]"),
    ("=C<",           "[CH0]=[CX3]"),
    ("-CH3",          "[CH3]"),
    ("-CH2-",         "[CH2]([!#0])([!#0])"),
    (">CH-",          "[CH1]([!#0])([!#0])([!#0])"),
    (">C<",           "[CX4H0]([!#0])([!#0])([!#0])([!#0])"),
]


# ═══════════════════════════════════════════════════════════════════
# 중합 가능 패턴
# ═══════════════════════════════════════════════════════════════════

POLYMERIZATION_SMARTS = {
    # 첨가 중합 (Addition)
    "vinyl":            "[CX3]=[CX3]",
    # 축합 중합 (Condensation) — 이관능기
    "diol":             "[OX2H1]",          # 2개 이상 시 축합 가능
    "diacid":           "[CX3](=O)[OX2H1]", # 2개 이상 시
    "diamine":          "[NX3H2]",          # 2개 이상 시
    # 개환 중합 (Ring-Opening)
    "epoxide":          "C1OC1",
    "lactone_4":        "O=C1OCC1",
    "lactone_5":        "O=C1OCCC1",
    "lactone_6":        "O=C1OCCCC1",
    "lactam_5":         "O=C1NCCC1",
    "lactam_6":         "O=C1NCCCC1",
    "lactam_7":         "O=C1NCCCCC1",
}


# ═══════════════════════════════════════════════════════════════════
# 골드 스탠더드 DB (문헌값 — 15종 주요 고분자)
# ═══════════════════════════════════════════════════════════════════
# 키: 정규화된 단량체 SMILES

KNOWN_POLYMERS: Dict[str, Dict] = {
    # ── 첨가 중합 ──
    "C=C": {
        "name": "PE", "name_kr": "폴리에틸렌",
        "repeat": "[*]CC[*]", "display": "-[CH2-CH2]n-",
        "M": 28.05, "density": 0.94, "Tg": -125, "Tm": 137, "Td": 400,
        "tensile": 30.0, "modulus": 1000, "elongation": 600,
        "delta": 16.2, "n": 1.51, "CTE": 200, "k_th": 0.46,
        "max_temp": 80, "symmetric": True,
    },
    "CC=C": {
        "name": "PP", "name_kr": "폴리프로필렌",
        "repeat": "[*]CC([*])C", "display": "-[CH2-CH(CH3)]n-",
        "M": 42.08, "density": 0.90, "Tg": -10, "Tm": 165, "Td": 380,
        "tensile": 35.0, "modulus": 1500, "elongation": 300,
        "delta": 16.0, "n": 1.49, "CTE": 150, "k_th": 0.22,
        "max_temp": 100, "symmetric": False,
    },
    "FC(F)=C(F)F": {
        "name": "PTFE", "name_kr": "폴리테트라플루오로에틸렌 (테플론)",
        "repeat": "[*]C(F)(F)C([*])(F)F", "display": "-[CF2-CF2]n-",
        "M": 100.02, "density": 2.15, "Tg": 127, "Tm": 327, "Td": 490,
        "tensile": 30.5, "modulus": 575, "elongation": 450,
        "delta": 12.6, "n": 1.35, "CTE": 100, "k_th": 0.24,
        "max_temp": 260, "symmetric": True,
    },
    "C=CCl": {
        "name": "PVC", "name_kr": "폴리염화비닐",
        "repeat": "[*]CC([*])Cl", "display": "-[CH2-CHCl]n-",
        "M": 62.50, "density": 1.40, "Tg": 87, "Tm": 212, "Td": 260,
        "tensile": 52.0, "modulus": 3000, "elongation": 40,
        "delta": 19.5, "n": 1.54, "CTE": 70, "k_th": 0.16,
        "max_temp": 65, "symmetric": False,
    },
    "C=Cc1ccccc1": {
        "name": "PS", "name_kr": "폴리스티렌",
        "repeat": "[*]CC([*])c1ccccc1", "display": "-[CH2-CH(C6H5)]n-",
        "M": 104.15, "density": 1.05, "Tg": 100, "Tm": 240, "Td": 350,
        "tensile": 40.0, "modulus": 3200, "elongation": 2,
        "delta": 18.5, "n": 1.59, "CTE": 70, "k_th": 0.13,
        "max_temp": 80, "symmetric": False,
    },
    "C=CC#N": {
        "name": "PAN", "name_kr": "폴리아크릴로니트릴",
        "repeat": "[*]CC([*])C#N", "display": "-[CH2-CH(CN)]n-",
        "M": 53.06, "density": 1.17, "Tg": 95, "Tm": 317, "Td": 300,
        "tensile": 60.0, "modulus": 4000, "elongation": 4,
        "delta": 25.3, "n": 1.51, "CTE": 70, "k_th": 0.26,
        "max_temp": 130, "symmetric": False,
    },
    "C=CC(=O)OC": {
        "name": "PMA", "name_kr": "폴리메틸아크릴레이트",
        "repeat": "[*]CC([*])C(=O)OC", "display": "-[CH2-CH(COOCH3)]n-",
        "M": 86.09, "density": 1.22, "Tg": 10, "Tm": -1, "Td": 330,
        "tensile": 7.0, "modulus": 200, "elongation": 750,
        "delta": 19.9, "n": 1.47, "CTE": 150, "k_th": 0.21,
        "max_temp": 50, "symmetric": False,
    },
    "C=C(C)C(=O)OC": {
        "name": "PMMA", "name_kr": "폴리메틸메타크릴레이트",
        "repeat": "[*]CC([*])(C)C(=O)OC", "display": "-[CH2-C(CH3)(COOCH3)]n-",
        "M": 100.12, "density": 1.19, "Tg": 105, "Tm": 160, "Td": 330,
        "tensile": 70.0, "modulus": 3100, "elongation": 5,
        "delta": 18.6, "n": 1.49, "CTE": 70, "k_th": 0.19,
        "max_temp": 90, "symmetric": False,
    },
    "C=COC(C)=O": {
        "name": "PVAc", "name_kr": "폴리초산비닐",
        "repeat": "[*]CC([*])OC(C)=O", "display": "-[CH2-CH(OOCCH3)]n-",
        "M": 86.09, "density": 1.19, "Tg": 30, "Tm": -1, "Td": 270,
        "tensile": 30.0, "modulus": 600, "elongation": 10,
        "delta": 19.1, "n": 1.47, "CTE": 120, "k_th": 0.17,
        "max_temp": 60, "symmetric": False,
    },
    "C=CF": {
        "name": "PVF", "name_kr": "폴리불화비닐",
        "repeat": "[*]CC([*])F", "display": "-[CH2-CHF]n-",
        "M": 46.04, "density": 1.39, "Tg": 40, "Tm": 200, "Td": 370,
        "tensile": 50.0, "modulus": 2000, "elongation": 100,
        "delta": 16.0, "n": 1.42, "CTE": 100, "k_th": 0.13,
        "max_temp": 110, "symmetric": False,
    },
    "FC=CF": {
        "name": "PVDF", "name_kr": "폴리불화비닐리덴",
        "repeat": "[*]C(F)C([*])F", "display": "-[CHF-CHF]n-",
        "M": 64.03, "density": 1.78, "Tg": -40, "Tm": 177, "Td": 400,
        "tensile": 50.0, "modulus": 2100, "elongation": 300,
        "delta": 17.2, "n": 1.42, "CTE": 130, "k_th": 0.19,
        "max_temp": 150, "symmetric": True,
    },
    "C=C(F)F": {
        "name": "PVDF2", "name_kr": "폴리비닐리덴플루오라이드",
        "repeat": "[*]CC([*])(F)F", "display": "-[CH2-CF2]n-",
        "M": 64.03, "density": 1.78, "Tg": -40, "Tm": 170, "Td": 390,
        "tensile": 50.0, "modulus": 2100, "elongation": 300,
        "delta": 17.2, "n": 1.42, "CTE": 130, "k_th": 0.19,
        "max_temp": 150, "symmetric": False,
    },
    # ── 개환 중합 ──
    "C1CO1": {
        "name": "PEO", "name_kr": "폴리에틸렌옥사이드",
        "repeat": "[*]CCO[*]", "display": "-[CH2-CH2-O]n-",
        "M": 44.05, "density": 1.13, "Tg": -67, "Tm": 65, "Td": 340,
        "tensile": 15.0, "modulus": 350, "elongation": 1200,
        "delta": 20.2, "n": 1.45, "CTE": 200, "k_th": 0.24,
        "max_temp": 50, "symmetric": True,
    },
    "O=C1CCCCN1": {
        "name": "Nylon-6", "name_kr": "나일론 6 (폴리카프로락탐)",
        "repeat": "[*]NCCCCCC([*])=O", "display": "-[NH-(CH2)5-CO]n-",
        "M": 113.16, "density": 1.14, "Tg": 50, "Tm": 220, "Td": 350,
        "tensile": 80.0, "modulus": 2800, "elongation": 60,
        "delta": 22.5, "n": 1.53, "CTE": 80, "k_th": 0.25,
        "max_temp": 100, "symmetric": False,
    },
    "C=CO": {
        "name": "PVA", "name_kr": "폴리비닐알코올",
        "repeat": "[*]CC([*])O", "display": "-[CH2-CHOH]n-",
        "M": 44.05, "density": 1.26, "Tg": 85, "Tm": 230, "Td": 260,
        "tensile": 40.0, "modulus": 2500, "elongation": 150,
        "delta": 25.8, "n": 1.50, "CTE": 85, "k_th": 0.20,
        "max_temp": 60, "symmetric": False,
    },
}

# ── 결합 분해 에너지 순서 (kJ/mol, Td 추정용) ──
BOND_DISSOCIATION_ENERGY = {
    "C-F":  485,  # 매우 강함
    "C-H":  413,
    "O-H":  463,
    "C-O":  360,
    "C-C":  348,
    "C-N":  305,
    "C-Cl": 339,
    "C-Br": 276,
    "C-S":  272,
    "N-H":  391,
    "Si-O": 452,
    "Si-C": 318,
}


# ═══════════════════════════════════════════════════════════════════
# 메인 엔진 클래스
# ═══════════════════════════════════════════════════════════════════

class PolymerPropertyEngine:
    """Van Krevelen 그룹 기여법 기반 고분자 물성 예측 엔진."""

    def __init__(self):
        self._compiled_smarts: Dict[str, object] = {}
        self._compiled_poly_smarts: Dict[str, object] = {}
        if RDKIT_OK:
            for name, smarts in GROUP_SMARTS:
                pat = Chem.MolFromSmarts(smarts)
                if pat:
                    self._compiled_smarts[name] = pat
            for name, smarts in POLYMERIZATION_SMARTS.items():
                pat = Chem.MolFromSmarts(smarts)
                if pat:
                    self._compiled_poly_smarts[name] = pat

    # ─── 중합 가능 여부 판별 ───────────────────────────────

    def detect_polymerization(self, smiles: str) -> PolymerizationResult:
        """단량체 SMILES로부터 중합 가능 여부와 유형을 판별한다."""
        # N 타입 가드: 외부 입력 SMILES 검증
        if not isinstance(smiles, str):
            logger.warning(f"detect_polymerization: smiles 타입 불일치 (expected str, got {type(smiles).__name__})")
            return PolymerizationResult(False, "none", "", "", str(smiles) if smiles else "", 0.0)
        if not RDKIT_OK or not smiles:
            return PolymerizationResult(False, "none", "", "", smiles or "", 0.0)

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return PolymerizationResult(False, "none", "", "", smiles, 0.0)

        canon = Chem.MolToSmiles(mol)

        # 1) 골드 스탠더드 DB 확인 (stereo 무시 비교 포함)
        # 입력 SMILES에 stereo (E/Z) 정보가 있을 수 있으므로 stereo 제거 후에도 매칭
        canon_nostereo = canon
        try:
            mol_ns = Chem.MolFromSmiles(canon)
            if mol_ns is not None:  # Rule L: None guard
                Chem.RemoveStereochemistry(mol_ns)
                canon_nostereo = Chem.MolToSmiles(mol_ns)
        except Exception as e:
            logger.warning("Stereochemistry removal failed during polymerization detection: %s", e)

        for known_smi, data in KNOWN_POLYMERS.items():
            known_mol = Chem.MolFromSmiles(known_smi)
            if known_mol is not None:  # Rule L: None guard
                known_canon = Chem.MolToSmiles(known_mol)
                # 정확한 canonical 매치 또는 stereo 제거 후 매치
                Chem.RemoveStereochemistry(known_mol)
                known_nostereo = Chem.MolToSmiles(known_mol)
                if known_canon == canon or known_nostereo == canon_nostereo:
                    return PolymerizationResult(
                        possible=True,
                        poly_type="addition" if "=" in known_smi or "1" in known_smi else "condensation",
                        repeat_unit_smiles=data["repeat"],
                        repeat_unit_display=data["display"],
                        monomer_smiles=canon,
                        confidence=1.0,
                    )

        # 2) 비닐 (첨가 중합) — Rule N: isinstance
        assert isinstance(self._compiled_poly_smarts, dict)
        vinyl_pat = self._compiled_poly_smarts.get("vinyl")
        if vinyl_pat and mol.HasSubstructMatch(vinyl_pat):
            repeat = self._vinyl_to_repeat_unit(mol)
            if repeat:
                display = self._repeat_to_display(repeat)
                return PolymerizationResult(True, "addition", repeat, display, canon, 0.85)

        # 3) 축합 중합 (이관능기)
        condensation = self._check_condensation(mol)
        if condensation:
            return PolymerizationResult(True, "condensation", condensation[0], condensation[1], canon, 0.7)

        # 4) 개환 중합
        rop = self._check_ring_opening(mol)
        if rop:
            return PolymerizationResult(True, "ring_opening", rop[0], rop[1], canon, 0.75)

        return PolymerizationResult(False, "none", "", "", canon, 0.0)

    # ─── 단량체 → 반복단위 변환 ───────────────────────────

    def _vinyl_to_repeat_unit(self, mol) -> Optional[str]:
        """비닐 C=C를 개환하여 [*]-C-C-[*] 반복단위를 생성한다."""
        try:
            rwmol = Chem.RWMol(mol)
            # C=C 이중결합 찾기
            double_bonds = []
            for bond in rwmol.GetBonds():
                if (bond.GetBondTypeAsDouble() == 2.0
                        and bond.GetBeginAtom().GetAtomicNum() == 6
                        and bond.GetEndAtom().GetAtomicNum() == 6):
                    double_bonds.append(bond.GetIdx())

            if not double_bonds:
                return None

            # 첫 번째 C=C 이중결합을 단일결합으로 변환
            bond = rwmol.GetBondWithIdx(double_bonds[0])
            idx1, idx2 = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            rwmol.RemoveBond(idx1, idx2)
            rwmol.AddBond(idx1, idx2, Chem.BondType.SINGLE)

            # 양 끝에 [*] 더미 원자 추가
            d1 = rwmol.AddAtom(Chem.Atom(0))  # dummy atom
            d2 = rwmol.AddAtom(Chem.Atom(0))
            rwmol.AddBond(idx1, d1, Chem.BondType.SINGLE)
            rwmol.AddBond(idx2, d2, Chem.BondType.SINGLE)

            # 수소 보정
            atom1 = rwmol.GetAtomWithIdx(idx1)
            atom2 = rwmol.GetAtomWithIdx(idx2)
            if atom1.GetNumExplicitHs() > 0:
                atom1.SetNumExplicitHs(atom1.GetNumExplicitHs())
            if atom2.GetNumExplicitHs() > 0:
                atom2.SetNumExplicitHs(atom2.GetNumExplicitHs())

            try:
                Chem.SanitizeMol(rwmol)
                return Chem.MolToSmiles(rwmol.GetMol())
            except Exception as e:
                logger.warning("Vinyl repeat unit sanitization failed, using fallback: %s", e)
                return f"[*]CC[*]"  # fallback

        except Exception as e:
            logger.warning("Vinyl→repeat unit conversion failed: %s", e)
            return None

    def _check_condensation(self, mol) -> Optional[Tuple[str, str]]:
        """축합 중합 가능 이관능기 검출."""
        # N 타입 가드: _compiled_poly_smarts가 dict인지 확인
        if not isinstance(self._compiled_poly_smarts, dict):
            logger.warning("_check_condensation: _compiled_poly_smarts 타입 불일치 (expected dict, got %s)",
                           type(self._compiled_poly_smarts).__name__)
            return None
        oh_pat = self._compiled_poly_smarts.get("diol")
        cooh_pat = self._compiled_poly_smarts.get("diacid")
        nh2_pat = self._compiled_poly_smarts.get("diamine")

        oh_count = len(mol.GetSubstructMatches(oh_pat)) if oh_pat else 0
        cooh_count = len(mol.GetSubstructMatches(cooh_pat)) if cooh_pat else 0
        nh2_count = len(mol.GetSubstructMatches(nh2_pat)) if nh2_pat else 0

        # 자기 축합: hydroxy acid, amino acid
        if oh_count >= 1 and cooh_count >= 1:
            return ("[*]OCC([*])=O", "-[O-CH2-CO]n-")
        if nh2_count >= 1 and cooh_count >= 1:
            return ("[*]NCC([*])=O", "-[NH-CH2-CO]n-")
        if oh_count >= 2:
            return ("[*]OCCO[*]", "-[O-CH2-CH2-O]n-")
        if cooh_count >= 2:
            return ("[*]C(=O)OC([*])=O", "-[CO-O-CO]n-")
        if nh2_count >= 2:
            return ("[*]NCCN[*]", "-[NH-CH2-CH2-NH]n-")

        return None

    def _check_ring_opening(self, mol) -> Optional[Tuple[str, str]]:
        """개환 중합 가능 고리 구조 검출."""
        # N 타입 가드: _compiled_poly_smarts가 dict인지 확인
        if not isinstance(self._compiled_poly_smarts, dict):
            logger.warning("_check_ring_opening: _compiled_poly_smarts 타입 불일치 (expected dict, got %s)",
                           type(self._compiled_poly_smarts).__name__)
            return None
        for name in ["epoxide", "lactone_4", "lactone_5", "lactone_6",
                      "lactam_5", "lactam_6", "lactam_7"]:
            pat = self._compiled_poly_smarts.get(name)
            if pat and mol.HasSubstructMatch(pat):
                if "epoxide" in name:
                    return ("[*]CCO[*]", "-[CH2-CH2-O]n-")
                elif "lactone" in name:
                    return ("[*]OCCCCC([*])=O", "-[O-(CH2)n-CO]n-")
                elif "lactam" in name:
                    return ("[*]NCCCCC([*])=O", "-[NH-(CH2)n-CO]n-")
        return None

    def _repeat_to_display(self, repeat_smiles: str) -> str:
        """반복단위 SMILES를 화면 표시용 문자열로 변환."""
        display = repeat_smiles.replace("[*]", "~")
        return f"-[{display}]n-"

    # ─── 그룹 분해 ────────────────────────────────────────

    # 그룹별 "코어 원자" 수 (SMARTS 매치 튜플의 앞 N개만 사용)
    # 나머지는 매칭 정확도를 위한 컨텍스트 원자이므로 used_atoms에 넣지 않는다.
    # 예: -O- SMARTS [OX2H0]([#6])[#6] → match=(O,C,C) 중 코어=O만(1개)
    _GROUP_CORE_COUNT: Dict[str, int] = {
        # 다원자 그룹: 코어 원자만 (컨텍스트 이웃 제외)
        "-CF2-": 3,   # C, F, F (2개의 [!F] 이웃은 컨텍스트)
        "-COO-": 3,   # C(=O), =O, O-bridge (마지막 [#6]는 컨텍스트)
        "-CO-":  2,   # C(=O), =O (2개의 [#6]는 컨텍스트)
        # 단일원자 브릿지 그룹: 중심 원자만
        "-NH-":  1,   # N만 (2개의 [!H]는 컨텍스트)
        ">N-":   1,   # N만 (3개의 [!H]는 컨텍스트)
        "-O-":   1,   # O만 (2개의 [#6]는 컨텍스트)
        "-S-":   1,   # S만 (2개의 [#6]는 컨텍스트)
        # 백본 탄소 그룹: 탄소 자체만 (이웃 원자는 다른 그룹에 속함)
        "-CH2-": 1,   # C만 (2개의 [!#0] 이웃은 컨텍스트)
        ">CH-":  1,   # C만 (3개의 [!#0] 이웃은 컨텍스트)
        ">C<":   1,   # C만 (4개의 [!#0] 이웃은 컨텍스트)
    }

    def decompose_groups(self, repeat_unit_smiles: str) -> Dict[str, int]:
        """반복단위의 작용기 분해 (SMARTS 매칭, 큰 그룹 우선).

        코어/컨텍스트 원자를 구분하여 브릿지 그룹(-O-, -S- 등)의
        이웃 원자가 다른 그룹과 중복되지 않도록 처리한다.
        더미 원자([*]/*)는 메틸캡(C)으로 치환하여 Van Krevelen 분석 수행.
        """
        # N 타입 가드
        if not isinstance(repeat_unit_smiles, str):
            logger.warning(f"decompose_groups: repeat_unit_smiles 타입 불일치 (expected str, got {type(repeat_unit_smiles).__name__})")
            return {}
        if not RDKIT_OK:
            return {}

        # 더미 원자를 메틸캡으로 치환 (backbone 연결을 C-C로 모사)
        smi = repeat_unit_smiles.replace("[*]", "C").replace("*", "C")
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return {}
        # 메틸캡 원자 인덱스를 기록 (그룹 매칭에서 제외)
        cap_indices: set = set()
        orig_mol = Chem.MolFromSmiles(repeat_unit_smiles)
        if orig_mol is not None:  # Rule L: None guard
            for atom in orig_mol.GetAtoms():
                if atom.GetAtomicNum() == 0:
                    cap_indices.add(atom.GetIdx())

        result: Dict[str, int] = {}
        used_atoms: set = set(cap_indices)  # 메틸캡은 미리 사용 처리

        # Rule N: 타입 가드 — _GROUP_CORE_COUNT는 dict
        assert isinstance(self._GROUP_CORE_COUNT, dict) and isinstance(result, dict)
        for group_name, pat in self._compiled_smarts.items():
            if group_name not in GROUP_CONTRIBUTIONS:
                continue
            matches = mol.GetSubstructMatches(pat)
            for match in matches:
                # 코어 원자만 추출 (컨텍스트 원자 제외)
                core_n = self._GROUP_CORE_COUNT.get(group_name, len(match))
                core_atoms = set(match[:core_n])
                # 메틸캡만으로 구성된 매치는 무시 (캡은 실제 반복단위 아님)
                if core_atoms <= cap_indices:
                    continue
                # 코어 원자가 이미 사용됐으면 스킵
                if core_atoms & used_atoms:
                    continue
                used_atoms |= core_atoms
                # Rule N: isinstance guard for result
                if not isinstance(result, dict): result = {}
                result[group_name] = result.get(group_name, 0) + 1

        return result

    # ─── RDKit 디스크립터 기반 보정 ────────────────────────

    def _rdkit_descriptors(self, repeat_unit_smiles: str) -> Dict[str, float]:
        """RDKit 분자 디스크립터 계산 (QSPR 보정용).

        그룹 기여법의 한계를 보완하기 위해 RDKit의 토폴로지/전자
        디스크립터를 추출하여 경험적 보정에 사용한다.
        """
        # N 타입 가드
        if not isinstance(repeat_unit_smiles, str):
            logger.warning(f"_rdkit_descriptors: repeat_unit_smiles 타입 불일치 ({type(repeat_unit_smiles).__name__})")
            return {}
        if not RDKIT_OK:
            return {}
        smi = repeat_unit_smiles.replace("[*]", "C").replace("*", "C")
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return {}
        try:
            desc = {
                "MW": Descriptors.MolWt(mol),
                "LogP": Descriptors.MolLogP(mol),          # Crippen LogP (소수성)
                "TPSA": Descriptors.TPSA(mol),              # 위상 극성 표면적
                "HBA": Descriptors.NumHAcceptors(mol),      # 수소결합 수용체
                "HBD": Descriptors.NumHDonors(mol),         # 수소결합 공여체
                "RotBonds": Descriptors.NumRotatableBonds(mol),  # 회전 가능 결합
                "RingCount": Descriptors.RingCount(mol),    # 고리 수
                "FractionCSP3": Descriptors.FractionCSP3(mol),  # sp3 탄소 비율
                "HeavyAtomCount": Descriptors.HeavyAtomCount(mol),
                "NumAromaticRings": rdMolDescriptors.CalcNumAromaticRings(mol),
                "Chi0": rdMolDescriptors.CalcChi0v(mol),    # Kier-Hall 연결성 지수
                "Chi1": rdMolDescriptors.CalcChi1v(mol),
                "HallKierAlpha": rdMolDescriptors.CalcHallKierAlpha(mol),
                # F/Cl/Br 비율 (불소 함량이 물성에 큰 영향)
                "F_count": sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 9),
                "Cl_count": sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 17),
            }
            return desc
        except Exception as e:
            logger.warning("RDKit descriptor calculation failed: %s", e)
            return {}

    def _rdkit_correct_Tg(self, Tg_group: float, desc: Dict[str, float],
                           M: float) -> float:
        """RDKit 디스크립터 기반 Tg 보정.

        그룹 기여법 Tg에 회전결합/고리/극성/다중치환 보정을 적용한다.
        """
        # N 타입 가드: desc는 _rdkit_descriptors()에서 올 수 있고, 실패 시 빈 dict
        if not isinstance(desc, dict):
            logger.warning(f"_rdkit_correct_Tg: desc 타입 불일치 (expected dict, got {type(desc).__name__})")
            return Tg_group
        if not desc:
            return Tg_group

        # 회전 가능 결합 → 사슬 유연성 ↑ → Tg ↓
        # -2°C/bond: 약한 보정 (그룹 기여 Yg가 이미 유연성 반영하므로)
        # 이전 -5는 과보정, -3도 장쇄 아크릴레이트에서 과도한 Tg 저하
        rot_bonds = desc.get("RotBonds", 0)
        rot_correction = -2.0 * rot_bonds  # 회전결합당 -2°C

        # 방향족 고리 → 강성 ↑ → Tg ↑ (그룹 기여에서 부분 반영됨)
        aromatic = desc.get("NumAromaticRings", 0)
        ring_correction = 10.0 * aromatic  # 방향족 고리당 +10°C 추가 보정

        # 수소결합 → 분자간 상호작용 ↑ → Tg ↑ — Rule N: isinstance 재확인
        assert isinstance(desc, dict)
        hbd = desc.get("HBD", 0)
        hb_correction = 15.0 * hbd

        # 불소 함량 → 특이 효과 (소량: Tg↑, 다량: 유연화)
        f_count = desc.get("F_count", 0)
        heavy = desc.get("HeavyAtomCount", 1)
        f_fraction = f_count / heavy if heavy > 0 else 0
        if f_fraction > 0.4:
            # 고도 불소화: PTFE 유사 → Tg 상승 효과
            f_correction = 30.0 * f_fraction
        elif f_fraction > 0:
            f_correction = 15.0 * f_fraction
        else:
            f_correction = 0

        # 다중 할로겐(Cl) 감쇠 보정: geminal Cl(같은 탄소에 2+ Cl)일 때
        # 그룹 기여법은 -Cl Yg를 PVC(1Cl) 기준으로 역산하므로,
        # PVDC(2Cl) 등에서 Tg를 과대예측함. Cl간 쌍극자 상쇄(dipole cancellation)
        # + 사슬 유연화 반영. PVDC lit Tg=17C, raw~135C, 보정필요~-118C.
        assert isinstance(desc, dict)  # Rule N: 타입 가드 재확인
        cl_count = desc.get("Cl_count", 0)
        if cl_count >= 2:
            # PVDC(2Cl): raw~135, need~17, correction~-118 → per extra Cl ~-60
            # But also rot=-2, so total needed = -(135-17+2) = -120 → per extra Cl ~-120
            # Geminal di-Cl causes strong dipole cancellation + chain mobility increase
            cl_dampening = -100.0 * (cl_count - 1)  # 2Cl→-100, 3Cl→-200
        else:
            cl_dampening = 0

        # 4급 탄소(>C<) 입체 보정: 알파-메틸 메타크릴레이트 등에서
        # 큰 치환기가 사슬 회전을 제한하여 Tg 상승. sp3 비율이 높은데
        # 회전결합도 많으면 이 효과가 상쇄되므로 (1 - FrCSP3) 가중.
        frac_sp3 = desc.get("FractionCSP3", 0.5)
        # sp3가 낮으면(방향족 등) 보정 불필요; sp3가 높으면 보정 적용
        steric_correction = 0
        if frac_sp3 > 0.6 and rot_bonds >= 3:
            # 장쇄 에스터 등: 분자 내 회전 자유도가 높아 Tg 약간 상승 보정
            steric_correction = 5.0 * max(0, frac_sp3 - 0.5)  # 최대 ~2.5C

        corrected = (Tg_group + rot_correction + ring_correction
                     + hb_correction + f_correction + cl_dampening
                     + steric_correction)
        return corrected

    def _rdkit_predict_density(self, desc: Dict[str, float], group_density: float) -> float:
        """RDKit 디스크립터 기반 밀도 보정.

        Van Krevelen V 합산에서 >C< 등 음수 V 그룹이 밀도를 과대평가하는
        문제를 보완한다. 불소 함량 비례 보정 적용.
        """
        # N 타입 가드
        if not isinstance(desc, dict):
            logger.warning(f"_rdkit_predict_density: desc 타입 불일치 (expected dict, got {type(desc).__name__})")
            return min(group_density, 2.20)
        if not desc:
            return min(group_density, 2.20)  # PTFE 이하로 클램핑
        f_count = desc.get("F_count", 0)
        heavy = desc.get("HeavyAtomCount", 1)
        f_mass_frac = (f_count * 19.0) / desc.get("MW", 100)  # F 질량 분율

        if f_mass_frac > 0.6:
            # 고도 불소화 (PTFE급): 밀도 2.0~2.2
            target_d = 2.0 + 0.3 * f_mass_frac
        elif f_mass_frac > 0.2:
            # 중간 불소화: 밀도 1.5~2.0
            target_d = 1.3 + 1.5 * f_mass_frac
        elif f_mass_frac > 0:
            # 저불소화: 밀도 1.2~1.5
            target_d = 1.2 + 1.0 * f_mass_frac
        else:
            # 일반 고분자: 그룹 기여값 사용, 상한 1.5
            target_d = min(group_density, 1.50)

        # 수소결합 공여체 밀도 보정: -OH, -COOH 등은 free volume ↑ → 밀도 ↓
        # Van Krevelen V 값이 H-bonded 그룹의 실제 자유부피를 과소평가하기 때문
        assert isinstance(desc, dict)  # Rule N
        hbd = desc.get("HBD", 0)
        if hbd > 0 and f_mass_frac < 0.1:
            # HBD당 ~5% 밀도 감소 보정 (최대 15%)
            hbd_factor = max(1.0 - 0.05 * hbd, 0.85)  # 최대 15% 감소
            target_d *= hbd_factor

        # 그룹 기여 결과와 혼합 (7:3 가중)
        blended = 0.3 * group_density + 0.7 * target_d
        # 물리적 범위: 0.85 (실리콘) ~ 2.20 (PTFE)
        return max(min(blended, 2.20), 0.85)

    # ─── 물성 예측 함수들 ─────────────────────────────────

    def predict_density(self, groups: Dict[str, int], M: float) -> float:
        """밀도 예측: ρ = M / ΣV_i (g/cm³)."""
        # N 타입 가드
        if not isinstance(groups, dict):
            logger.warning(f"predict_density: groups 타입 불일치 (expected dict, got {type(groups).__name__})")
            return 1.0
        V_total = sum(
            GROUP_CONTRIBUTIONS[g]["V"] * n
            for g, n in groups.items()
            if g in GROUP_CONTRIBUTIONS
        )
        if V_total <= 0:
            return 1.0  # fallback
        return M / V_total

    def predict_solubility_param(self, groups: Dict[str, int]) -> float:
        """용해도 파라미터: δ = √(ΣEcoh / ΣV) in (J/cm³)^0.5 → (MJ/m³)^0.5."""
        # N 타입 가드
        if not isinstance(groups, dict):
            logger.warning(f"predict_solubility_param: groups 타입 불일치 (expected dict, got {type(groups).__name__})")
            return 15.0
        Ecoh_total = sum(
            GROUP_CONTRIBUTIONS[g]["Ecoh"] * n
            for g, n in groups.items()
            if g in GROUP_CONTRIBUTIONS
        )
        V_total = sum(
            GROUP_CONTRIBUTIONS[g]["V"] * n
            for g, n in groups.items()
            if g in GROUP_CONTRIBUTIONS
        )
        if V_total <= 0:
            return 15.0
        delta_J = math.sqrt(Ecoh_total / V_total)  # (J/cm³)^0.5
        return delta_J / 1000 * math.sqrt(1e6)     # → (MJ/m³)^0.5 = (J/cm³)^0.5

    def fox_tg_blend(self, tg1_c: float, tg2_c: float, w1: float) -> float:
        """Fox 방정식으로 이성분 고분자 블렌드의 유리전이온도 계산 (℃).

        수식: 1/Tg_blend = w1/Tg1 + w2/Tg2  (K 단위)
        w2 = 1 - w1  (질량분율 정규화)

        References:
            Fox T.G. Bull Am Phys Soc 1956, 1(3):123
            Fox T.G.; Flory P.J. J Am Chem Soc 1950, 72(7):3580
        """
        # N 타입 가드
        if not isinstance(tg1_c, (int, float)):
            logger.warning("fox_tg_blend: tg1_c 타입 불일치 (%s)", type(tg1_c).__name__)
            tg1_c = 25.0
        if not isinstance(tg2_c, (int, float)):
            logger.warning("fox_tg_blend: tg2_c 타입 불일치 (%s)", type(tg2_c).__name__)
            tg2_c = 25.0
        if not isinstance(w1, (int, float)):
            logger.warning("fox_tg_blend: w1 타입 불일치 (%s)", type(w1).__name__)
            w1 = 0.5

        # 질량분율 범위 guard: 0 < w1 < 1
        w1 = max(1e-6, min(1.0 - 1e-6, float(w1)))  # [MAGIC:1e-6] division-by-zero 방지
        w2 = 1.0 - w1

        tg1_k = tg1_c + 273.15  # ℃ → K
        tg2_k = tg2_c + 273.15

        if tg1_k <= 0 or tg2_k <= 0:
            logger.warning("fox_tg_blend: Tg_K <= 0 (tg1=%.1f K, tg2=%.1f K)", tg1_k, tg2_k)
            return min(tg1_c, tg2_c)

        # Fox equation: 1/Tg_blend = w1/Tg1 + w2/Tg2
        inv_tg_blend = w1 / tg1_k + w2 / tg2_k
        tg_blend_k = 1.0 / inv_tg_blend
        return round(tg_blend_k - 273.15, 1)  # K → ℃

    def predict_Tg(self, groups: Dict[str, int], M: float) -> float:
        """유리전이온도 Tg: ΣYg_i / M (K → ℃)."""
        # N 타입 가드
        if not isinstance(groups, dict):
            logger.warning(f"predict_Tg: groups 타입 불일치 (expected dict, got {type(groups).__name__})")
            return 25.0
        Yg_total = sum(
            GROUP_CONTRIBUTIONS[g]["Yg"] * n
            for g, n in groups.items()
            if g in GROUP_CONTRIBUTIONS
        )
        if M <= 0:
            return 25.0
        Tg_K = Yg_total / M
        return Tg_K - 273.15  # K → ℃

    def predict_Tm(self, Tg_C: float, symmetric: bool, Td_C: float = 600) -> float:
        """녹는점 Tm: Boyer-Beaman rule (Td 상한 적용)."""
        # N 타입 가드
        if not isinstance(Tg_C, (int, float)):
            logger.warning("predict_Tm: Tg_C 타입 불일치 (expected numeric, got %s)", type(Tg_C).__name__)
            Tg_C = 25.0
        if not isinstance(Td_C, (int, float)):
            logger.warning("predict_Tm: Td_C 타입 불일치 (expected numeric, got %s)", type(Td_C).__name__)
            Td_C = 600.0
        Tg_K = Tg_C + 273.15
        # 대칭 사슬: Tm/Tg ≈ 1.5, 비대칭: Tm/Tg ≈ 2.0
        ratio = 1.5 if symmetric else 2.0  # Boyer-Beaman
        Tm_K = Tg_K * ratio
        Tm_C = Tm_K - 273.15
        # 물리적 제약: Tm은 Td보다 높을 수 없음
        return min(Tm_C, Td_C - 30)

    def predict_Td(self, groups: Dict[str, int]) -> float:
        """열분해온도 Td: 가중평균 BDE 기반 추정 (℃).

        최약 결합 BDE만 사용하면 강한 결합(C-F)의 안정화 효과가 무시된다.
        전체 결합의 가중평균을 사용하여 보다 정확한 Td를 추정한다.
        """
        # N 타입 가드
        if not isinstance(groups, dict):
            logger.warning(f"predict_Td: groups 타입 불일치 (expected dict, got {type(groups).__name__})")
            return 300.0
        bond_weights: Dict[str, int] = {}
        for g, count in groups.items():
            if "-F" in g or "-CF" in g:
                bond_weights["C-F"] = bond_weights.get("C-F", 0) + count * (
                    2 if "CF2" in g else 3 if "CF3" in g else 1)
            if "-Cl" in g:
                bond_weights["C-Cl"] = bond_weights.get("C-Cl", 0) + count
            if "-Br" in g:
                bond_weights["C-Br"] = bond_weights.get("C-Br", 0) + count
            if "-O-" in g or "-COO" in g or "-OH" in g:
                bond_weights["C-O"] = bond_weights.get("C-O", 0) + count
            if "-NH" in g or ">N" in g or "-CONH" in g:
                bond_weights["C-N"] = bond_weights.get("C-N", 0) + count
            if "-S-" in g:
                # Rule N: isinstance guard for bond_weights
                if not isinstance(bond_weights, dict): bond_weights = {}
                bond_weights["C-S"] = bond_weights.get("C-S", 0) + count
            if any(x in g for x in ("-CH", ">CH", ">C<", "C6H", "-CH2", "-CH3")):
                bond_weights["C-C"] = bond_weights.get("C-C", 0) + count
            if "Si" in g:
                bond_weights["Si-O"] = bond_weights.get("Si-O", 0) + count

        if not bond_weights:
            bond_weights = {"C-C": 2, "C-H": 4}

        # 가중평균 BDE 계산
        total_weight = sum(bond_weights.values())
        avg_bde = sum(
            BOND_DISSOCIATION_ENERGY.get(b, 350) * w
            for b, w in bond_weights.items()
        ) / max(total_weight, 1)

        # 최약 결합의 BDE (열분해 시작점)
        min_bde = min(BOND_DISSOCIATION_ENERGY.get(b, 350) for b in bond_weights)

        # Td = 0.4 × avg_BDE + 0.5 × min_BDE + 조정 (℃)
        # 강한 결합이 많으면 avg가 높아져 Td 상승
        Td = 0.5 * avg_bde + 0.4 * min_bde - 50  # ℃
        return max(Td, 150)  # 최소 150℃

    def predict_tensile_strength(self, density: float, delta: float,
                                  Tg_C: float = 25.0) -> float:
        """인장강도 추정 (MPa): 밀도×응집에너지+Tg 기반.

        Tg가 높을수록 강성↑ → 인장강도↑ (유리질 상태 기여).
        """
        # N 타입 가드: 외부 호출 시 비숫자 입력 방어
        if not isinstance(density, (int, float)):
            logger.warning("predict_tensile_strength: density 타입 불일치 (expected numeric, got %s)", type(density).__name__)
            density = 1.0
        if not isinstance(delta, (int, float)):
            logger.warning("predict_tensile_strength: delta 타입 불일치 (expected numeric, got %s)", type(delta).__name__)
            delta = 15.0
        if not isinstance(Tg_C, (int, float)):
            logger.warning("predict_tensile_strength: Tg_C 타입 불일치 (expected numeric, got %s)", type(Tg_C).__name__)
            Tg_C = 25.0
        # 기본: 응집 에너지 밀도 기반 (δ² ∝ Ecoh/V)
        sigma_base = 0.15 * density * delta  # MPa
        # Tg 보정: 상온 대비 유리질/고무질 상태 보정
        if Tg_C > 25:  # 유리질 (상온에서 강성)
            Tg_factor = 1.0 + 0.008 * (Tg_C - 25)  # Tg↑ → 인장강도↑
        else:  # 고무질 (상온에서 유연)
            Tg_factor = 0.5 + 0.02 * (Tg_C + 50)  # 저Tg → 인장강도↓
            Tg_factor = max(Tg_factor, 0.3)
        sigma = sigma_base * Tg_factor
        # 물리적 범위: 고분자 인장강도 5~150 MPa
        return max(min(sigma, 150.0), 5.0)

    def predict_youngs_modulus(self, Tg_C: float, density: float) -> float:
        """영률 추정 (MPa): Tg + 밀도 상관."""
        # N 타입 가드
        if not isinstance(Tg_C, (int, float)):
            logger.warning("predict_youngs_modulus: Tg_C 타입 불일치 (expected numeric, got %s)", type(Tg_C).__name__)
            Tg_C = 25.0
        if not isinstance(density, (int, float)):
            logger.warning("predict_youngs_modulus: density 타입 불일치 (expected numeric, got %s)", type(density).__name__)
            density = 1.0
        # Tg 높을수록, 밀도 높을수록 강성↑
        # 경험적: E ≈ k1 × (Tg + 273) + k2 × density
        E = 3.5 * (Tg_C + 273) + 500 * density  # MPa
        return max(E, 50.0)

    def predict_CTE(self, Tg_C: float) -> float:
        """열팽창계수 추정 (×10⁻⁶/K)."""
        # N 타입 가드
        if not isinstance(Tg_C, (int, float)):
            logger.warning("predict_CTE: Tg_C 타입 불일치 (expected numeric, got %s)", type(Tg_C).__name__)
            Tg_C = 25.0
        # Tg 높으면 CTE 낮음 (경험적 역상관)
        CTE = 300 - 1.5 * (Tg_C + 100)  # ×10⁻⁶/K
        return max(CTE, 20.0)

    def predict_refractive_index(self, groups: Dict[str, int],
                                  M: float, density: float) -> float:
        """굴절률: Lorentz-Lorenz 식 + 불소 보정."""
        # N 타입 가드
        if not isinstance(groups, dict):
            logger.warning(f"predict_refractive_index: groups 타입 불일치 (expected dict, got {type(groups).__name__})")
            return 1.50
        Rm_total = sum(
            GROUP_CONTRIBUTIONS[g]["Rm"] * n
            for g, n in groups.items()
            if g in GROUP_CONTRIBUTIONS
        )
        if M <= 0:
            return 1.50
        # (n² - 1)/(n² + 2) = (ρ/M) × Rm
        LL = (density / M) * Rm_total
        LL = max(min(LL, 0.40), 0.05)  # 물리적 범위 제한 (고분자 0.05~0.40)
        # n² = (1 + 2*LL) / (1 - LL)
        n_sq = (1 + 2 * LL) / (1 - LL)
        n = math.sqrt(max(n_sq, 1.0))
        # 불소 함량 보정: F는 저분극성이므로 n 감소 (PTFE n=1.35)
        # Rule N: isinstance guard for groups
        if not isinstance(groups, dict): groups = {}
        f_count = groups.get("-F", 0) + groups.get("-CF2-", 0) * 2 + groups.get("-CF3", 0) * 3
        total_atoms = sum(n_atoms for n_atoms in groups.values())
        if total_atoms > 0 and f_count > 0:
            f_ratio = f_count / (total_atoms + f_count)
            # F 비율에 비례하여 n 감소 (최대 0.25 감소, PTFE 기준)
            n -= 0.35 * f_ratio
        # 물리적 범위 클램핑: 고분자 굴절률 1.30~1.65
        return max(min(n, 1.65), 1.30)

    def predict_thermal_conductivity(self, density: float) -> float:
        """열전도율 추정 (W/(m·K))."""
        # N 타입 가드
        if not isinstance(density, (int, float)):
            logger.warning("predict_thermal_conductivity: density 타입 불일치 (expected numeric, got %s)", type(density).__name__)
            density = 1.0
        # 고분자 일반: 0.1 ~ 0.5 W/(m·K), 밀도에 약간 비례
        return 0.1 + 0.12 * density

    def _detect_symmetry(self, repeat_unit_smiles: str) -> bool:
        """반복단위의 대칭성 판별 (양 탄소 치환기 동일 여부)."""
        # N 타입 가드
        if not isinstance(repeat_unit_smiles, str):
            logger.warning("_detect_symmetry: repeat_unit_smiles 타입 불일치 (expected str, got %s)", type(repeat_unit_smiles).__name__)
            return False
        if not RDKIT_OK:
            return False
        smi = repeat_unit_smiles.replace("[*]", "C").replace("*", "C")
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return False
        # 대칭: 비수소/비캡 원자가 같은 원소이면 대칭으로 간주
        atoms = [a.GetAtomicNum() for a in mol.GetAtoms()
                 if a.GetAtomicNum() not in (0, 1)]
        if not atoms:
            return True
        # 단순 휴리스틱: 원소 종류가 2개 이하면 대칭 가능성 높음
        unique = set(atoms)
        return len(unique) <= 2

    # ─── 고분자명 추론 ───────────────────────────────────

    def _infer_polymer_name(self, monomer_smiles: str,
                             groups: Dict[str, int],
                             poly_type: str) -> Tuple[str, str]:
        """단량체 SMILES와 작용기 분해로부터 고분자명 추론."""
        # N 타입 가드
        if not isinstance(groups, dict):
            logger.warning(f"_infer_polymer_name: groups 타입 불일치 (expected dict, got {type(groups).__name__})")
            return ("unknown polymer", "미확인 고분자")

        parts_en = []
        parts_kr = []

        # 할로겐 접두어
        f_count = groups.get("-F", 0) + groups.get("-CF2-", 0) * 2 + groups.get("-CF3", 0) * 3
        cl_count = groups.get("-Cl", 0)
        if f_count > 0:
            prefix = {1: "fluoro", 2: "difluoro", 3: "trifluoro", 4: "tetrafluoro"}.get(
                f_count, f"{f_count}fluoro")
            parts_en.append(prefix)
            prefix_kr = {1: "플루오로", 2: "디플루오로", 3: "트리플루오로", 4: "테트라플루오로"}.get(
                f_count, f"{f_count}플루오로")
            parts_kr.append(prefix_kr)
        if cl_count > 0:
            parts_en.append("chloro" if cl_count == 1 else f"{cl_count}chloro")
            parts_kr.append("클로로" if cl_count == 1 else f"{cl_count}클로로")

        # 주골격 유형
        if poly_type == "addition":
            if "-O-" in groups and ("p-C6H4-" in groups or "-C6H5" in groups):
                parts_en.append("vinyl phenyl ether")
                parts_kr.append("비닐 페닐 에테르")
            elif "-O-" in groups:
                parts_en.append("vinyl ether")
                parts_kr.append("비닐 에테르")
            elif "p-C6H4-" in groups or "-C6H5" in groups:
                parts_en.append("styrene")
                parts_kr.append("스티렌")
            elif "-COO-" in groups:
                parts_en.append("acrylate")
                parts_kr.append("아크릴레이트")
            elif "-CN" in groups:
                parts_en.append("acrylonitrile")
                parts_kr.append("아크릴로니트릴")
            else:
                parts_en.append("ethylene")
                parts_kr.append("에틸렌")
        elif poly_type == "condensation":
            parts_en.append("condensation polymer")
            parts_kr.append("축합 고분자")
        elif poly_type == "ring_opening":
            parts_en.append("ring-opened polymer")
            parts_kr.append("개환 고분자")

        name_en = "poly(" + " ".join(parts_en) + ")"
        name_kr = "폴리(" + " ".join(parts_kr) + ")"
        return name_en, name_kr

    # ─── 전체 파이프라인 ──────────────────────────────────

    def predict_all(self, monomer_smiles: str) -> Optional[PolymerProperties]:
        """단량체 SMILES → 전체 고분자 물성 예측."""
        # N 타입 가드: 외부 입력 SMILES 검증
        if not isinstance(monomer_smiles, str) or not monomer_smiles.strip():
            logger.warning(f"predict_all: monomer_smiles 타입/값 불일치 ({type(monomer_smiles).__name__})")
            return None
        if not RDKIT_OK:
            return None

        poly_result = self.detect_polymerization(monomer_smiles)
        if not poly_result.possible:
            return None

        canon = poly_result.monomer_smiles

        # 골드 스탠더드 확인 (stereo 무시 비교 포함)
        canon_nostereo = canon
        try:
            mol_ns = Chem.MolFromSmiles(canon)
            if mol_ns is not None:  # Rule L: None guard
                Chem.RemoveStereochemistry(mol_ns)
                canon_nostereo = Chem.MolToSmiles(mol_ns)
        except Exception as e:
            logger.warning("Stereochemistry removal failed during predict_all: %s", e)

        for known_smi, data in KNOWN_POLYMERS.items():
            known_mol = Chem.MolFromSmiles(known_smi)
            if known_mol is None:  # Rule L: None guard
                continue
            known_canon = Chem.MolToSmiles(known_mol)
            Chem.RemoveStereochemistry(known_mol)
            known_nostereo = Chem.MolToSmiles(known_mol)
            if known_canon == canon or known_nostereo == canon_nostereo:
                return PolymerProperties(
                    monomer_smiles=canon,
                    repeat_unit_smiles=data["repeat"],
                    polymer_name=data["name"],
                    polymer_name_kr=data["name_kr"],
                    poly_type=poly_result.poly_type,
                    M_repeat=data["M"],
                    density=data["density"],
                    solubility_param=data["delta"],
                    refractive_index=data["n"],
                    Tg=data["Tg"],
                    Tm=data["Tm"] if data["Tm"] > 0 else data["Tg"] * 1.5 + 50,
                    Td=data["Td"],
                    max_service_temp=data["max_temp"],
                    CTE=data["CTE"],
                    thermal_conductivity=data["k_th"],
                    tensile_strength=data["tensile"],
                    youngs_modulus=data["modulus"],
                    elongation_at_break=data["elongation"],
                    group_decomposition={},
                    warnings=[],
                    is_gold_standard=True,
                )

        # 그룹 기여 계산
        repeat_smi = poly_result.repeat_unit_smiles
        groups = self.decompose_groups(repeat_smi)
        warnings = []

        if not groups:
            warnings.append("그룹 분해 실패 — 기본값 사용")
            groups = {"-CH2-": 2}

        # 반복단위 분자량 (더미→H로 치환하여 MW 계산)
        smi_for_mw = repeat_smi.replace("[*]", "[H]").replace("*", "[H]")
        mw_mol = Chem.MolFromSmiles(smi_for_mw)
        if mw_mol is None:
            # fallback: 메틸캡으로 시도
            smi_for_mw2 = repeat_smi.replace("[*]", "C").replace("*", "C")
            mw_mol = Chem.MolFromSmiles(smi_for_mw2)
            if mw_mol is None:  # Rule L: None guard
                M = 28.0  # ethylene MW fallback
            else:
                # 메틸캡 2개 분자량(30) 제거하여 반복단위 MW 추정
                M = Descriptors.MolWt(mw_mol) - 30.0
        else:
            M = Descriptors.MolWt(mw_mol) - 2.0  # H2 제거 (더미→H 보정)
        M = max(M, 14.0)  # 최소값 안전장치

        symmetric = self._detect_symmetry(repeat_smi)

        # RDKit 디스크립터 계산 (QSPR 보정용)
        rdkit_desc = self._rdkit_descriptors(repeat_smi)

        # ── 1단계: 그룹 기여법 기본 예측 ──
        density_raw = self.predict_density(groups, M)
        delta = self.predict_solubility_param(groups)
        Tg_raw = self.predict_Tg(groups, M)
        Td = self.predict_Td(groups)

        # ── 2단계: RDKit 디스크립터 기반 보정 ──
        Tg = self._rdkit_correct_Tg(Tg_raw, rdkit_desc, M)
        density = self._rdkit_predict_density(rdkit_desc, density_raw)

        # Tm: Boyer-Beaman + Td 상한 적용
        Tm = self.predict_Tm(Tg, symmetric, Td)

        tensile = self.predict_tensile_strength(density, delta, Tg)
        modulus = self.predict_youngs_modulus(Tg, density)
        CTE = self.predict_CTE(Tg)
        n_idx = self.predict_refractive_index(groups, M, density)
        k_th = self.predict_thermal_conductivity(density)

        # 최대 사용 온도: Td와 Tm 중 낮은 쪽 기준
        max_temp = min(Td - 50, Tm - 20) if Tm > 0 else Td - 100

        # 파단신장률 추정 (Tg 기반: 유리질=낮음, 고무질=높음)
        if Tg > 80:
            elongation = 5.0   # 유리질 (brittle)
        elif Tg > 0:
            elongation = 50.0  # 중간
        else:
            elongation = 400.0 # 고무질 (flexible)

        # RDKit 기반 인장강도 보정 (밀도×응집에너지 + 수소결합 기여)
        # N 타입 가드: rdkit_desc는 _rdkit_descriptors()에서 dict 또는 {} 반환
        if not isinstance(rdkit_desc, dict):
            logger.warning("predict_all: rdkit_desc 타입 불일치 (expected dict, got %s)", type(rdkit_desc).__name__)
            rdkit_desc = {}
        hbd = rdkit_desc.get("HBD", 0)
        tensile = tensile + 8.0 * hbd  # 수소결합당 ~8 MPa 보정

        # 고분자명 추론 (RDKit IUPAC 유사명)
        name, name_kr = self._infer_polymer_name(monomer_smiles, groups, poly_result.poly_type)

        if rdkit_desc:
            warnings.append(f"RDKit 보정 적용 (RotBonds={rdkit_desc.get('RotBonds',0)}, "
                            f"AromaticRings={rdkit_desc.get('NumAromaticRings',0)}, "
                            f"F_count={rdkit_desc.get('F_count',0)})")

        return PolymerProperties(
            monomer_smiles=canon,
            repeat_unit_smiles=repeat_smi,
            polymer_name=name,
            polymer_name_kr=name_kr,
            poly_type=poly_result.poly_type,
            M_repeat=round(M, 2),
            density=round(density, 3),
            solubility_param=round(delta, 1),
            refractive_index=round(n_idx, 3),
            Tg=round(Tg, 1),
            Tm=round(Tm, 1),
            Td=round(Td, 1),
            max_service_temp=round(max_temp, 0),
            CTE=round(CTE, 1),
            thermal_conductivity=round(k_th, 3),
            tensile_strength=round(tensile, 1),
            youngs_modulus=round(modulus, 0),
            elongation_at_break=round(elongation, 1),
            group_decomposition=groups,
            warnings=warnings,
            is_gold_standard=False,
        )

    # ─── 비교용 유틸리티 ──────────────────────────────────

    def get_known_polymer_list(self) -> List[Dict]:
        """골드 스탠더드 DB의 고분자 목록 반환 (비교 탭용)."""
        result = []
        for smi, data in KNOWN_POLYMERS.items():
            # N 타입 가드: KNOWN_POLYMERS의 값은 dict이어야 함
            if not isinstance(data, dict):
                logger.warning("get_known_polymer_list: 골드 스탠더드 데이터 타입 불일치 (smi=%s, type=%s)", smi, type(data).__name__)
                continue
            result.append({
                "monomer_smiles": smi,
                "name": data.get("name", "unknown"),
                "name_kr": data.get("name_kr", "미확인"),
                "density": data.get("density", 1.0),
                "Tg": data.get("Tg", 25),
                "Tm": data.get("Tm", 100),
                "Td": data.get("Td", 300),
                "tensile": data.get("tensile", 30.0),
                "modulus": data.get("modulus", 1000),
                "delta": data.get("delta", 16.0),
            })
        return result

    def get_known_polymer_properties(self, monomer_smiles: str) -> Optional[PolymerProperties]:
        """골드 스탠더드에서 특정 고분자 물성 반환."""
        # N 타입 가드: 외부 호출 시 비문자열 입력 방어
        if not isinstance(monomer_smiles, str):
            logger.warning("get_known_polymer_properties: monomer_smiles 타입 불일치 (expected str, got %s)", type(monomer_smiles).__name__)
            return None
        return self.predict_all(monomer_smiles)
