# reaction_predictor.py (v1.0 - Organic Reaction Prediction Engine)
"""
ChemGrid: 유기합성반응 예측 엔진
- 두 분자의 SMILES를 받아 가능한 반응 경로 목록 반환
- SMARTS 패턴 매칭 기반 rule-based 예측
- Gemini AI 보조 (선택적)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors, rdmolops
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FunctionalGroup:
    """감지된 작용기"""
    name: str           # "알킬 할로겐화물", "카르복실산" 등
    name_en: str        # "Alkyl Halide", "Carboxylic Acid"
    smarts: str         # 매칭에 사용된 SMARTS
    atom_indices: tuple  # RDKit 분자 내 매칭 원자 인덱스
    role: str           # "electrophile", "nucleophile", "acid", "base", "diene", "dienophile"


@dataclass
class ReactionCondition:
    """반응 조건"""
    reagent: str        # "NaOH (aq)", "H2SO4 (cat.)"
    temperature: str    # "RT", "Heat (60°C)", "Reflux"
    solvent: str        # "H2O", "EtOH", "DMSO"
    catalyst: str = ""  # "FeBr3", "Pd/C"


@dataclass
class ReactionPathway:
    """예측된 반응 경로"""
    name: str                           # "SN2 (친핵성 치환)"
    name_en: str                        # "SN2 Nucleophilic Substitution"
    category: str                       # "치환", "제거", "첨가", "방향족", "산화환원", "축합"
    mechanism_type: str                 # "sn2", "sn1", "e2", "e1", "eas", "nuc_add", etc.
    conditions: List[ReactionCondition] # 가능한 반응 조건들
    product_smiles: str = ""            # 예측 생성물 SMILES
    confidence: float = 0.5            # 0.0~1.0 신뢰도
    description: str = ""               # 한글 설명
    reactant_a_role: str = ""           # "기질 (substrate)"
    reactant_b_role: str = ""           # "친핵체 (nucleophile)"
    fg_a: Optional[FunctionalGroup] = None  # 분자 A의 관련 작용기
    fg_b: Optional[FunctionalGroup] = None  # 분자 B의 관련 작용기
    regiochemistry: str = ""            # "Markovnikov", "Anti-Markovnikov", "Zaitsev"
    stereochemistry: str = ""           # "Inversion", "Retention", "Racemic"


# ============================================================================
# FUNCTIONAL GROUP DETECTION
# ============================================================================

# (name_kr, name_en, SMARTS, role)
FUNCTIONAL_GROUP_PATTERNS = [
    # === 할로겐화물 ===
    ("1차 알킬 할로겐화물", "Methyl Alkyl Halide",
     "[CH3X4][F,Cl,Br,I]", "electrophile"),
    ("1차 알킬 할로겐화물", "Primary Alkyl Halide",
     "[CH2X4][F,Cl,Br,I]", "electrophile"),
    ("2차 알킬 할로겐화물", "Secondary Alkyl Halide",
     "[CHX4]([#6])[F,Cl,Br,I]", "electrophile"),
    ("3차 알킬 할로겐화물", "Tertiary Alkyl Halide",
     "[CX4]([#6])([#6])([#6])[F,Cl,Br,I]", "electrophile"),
    ("알릴/벤질 할로겐화물", "Allylic/Benzylic Halide",
     "[CX4;$([CX4]C=C),$([CX4]c)][F,Cl,Br,I]", "electrophile"),
    ("아실 할로겐화물", "Acyl Halide",
     "[CX3](=O)[F,Cl,Br,I]", "electrophile"),

    # === 알코올 ===
    ("1차 알코올", "Primary Alcohol", "[CH2][OH]", "nucleophile"),
    ("2차 알코올", "Secondary Alcohol", "[CH]([#6])([#6])[OH]", "nucleophile"),
    ("3차 알코올", "Tertiary Alcohol", "[CX4]([#6])([#6])([#6])[OH]", "nucleophile"),
    ("페놀", "Phenol", "c[OH]", "nucleophile"),

    # === 카르보닐 ===
    ("알데히드", "Aldehyde", "[CH]=O", "electrophile"),
    ("케톤", "Ketone", "[#6][CX3](=O)[#6]", "electrophile"),
    ("카르복실산", "Carboxylic Acid", "[CX3](=O)[OH]", "acid"),
    ("에스터", "Ester", "[CX3](=O)[OX2][#6]", "electrophile"),
    ("아마이드", "Amide", "[CX3](=O)[NX3]", "electrophile"),
    ("카르복실산 무수물", "Acid Anhydride", "[CX3](=O)O[CX3](=O)", "electrophile"),

    # === 아민 ===
    ("1차 아민", "Primary Amine", "[NX3;H2][#6]", "nucleophile"),
    ("2차 아민", "Secondary Amine", "[NX3;H1]([#6])[#6]", "nucleophile"),
    ("3차 아민", "Tertiary Amine", "[NX3]([#6])([#6])[#6]", "base"),

    # === 불포화 결합 ===
    ("알켄", "Alkene", "[#6]=[#6]", "dienophile"),
    ("공액 디엔", "Conjugated Diene", "[#6]=[#6]-[#6]=[#6]", "diene"),
    ("알카인", "Alkyne", "[#6]#[#6]", "dienophile"),

    # === 방향족 ===
    ("방향족 고리", "Aromatic Ring", "c1ccccc1", "electrophile"),
    ("활성화된 방향족 (페놀)", "Activated Aromatic (Phenol)",
     "c1cc(O)ccc1", "nucleophile"),
    ("활성화된 방향족 (아닐린)", "Activated Aromatic (Aniline)",
     "c1cc(N)ccc1", "nucleophile"),
    ("활성화된 방향족 (아니솔)", "Activated Aromatic (Anisole)",
     "c1cc(OC)ccc1", "nucleophile"),

    # === 기타 ===
    ("니트릴", "Nitrile", "[#6]C#N", "electrophile"),
    ("에폭사이드", "Epoxide", "C1OC1", "electrophile"),
    ("티올", "Thiol", "[#6][SH]", "nucleophile"),
    ("이소시아네이트", "Isocyanate", "[#6]N=C=O", "electrophile"),

    # === 무기 시약 (분자 B로 자주 등장) ===
    ("물", "Water", "[OH2]", "nucleophile"),
    ("하이드록사이드", "Hydroxide", "[OH-]", "nucleophile"),
    ("할로겐 음이온", "Halide Ion", "[F-,Cl-,Br-,I-]", "nucleophile"),
    ("시안화물", "Cyanide", "[C-]#N", "nucleophile"),
    ("하이드라이드", "Hydride", "[H-]", "nucleophile"),

    # === 이원자 할로겐 분자 (X2) ===
    ("이원자 할로겐", "Diatomic Halogen", "[F,Cl,Br,I]-[F,Cl,Br,I]", "electrophile"),
]


# ============================================================================
# REACTION RULES DATABASE
# ============================================================================

REACTION_RULES: List[Dict] = [
    # ═══ 치환 반응 (Substitution) ═══
    {
        "name": "SN2 (친핵성 치환)",
        "name_en": "SN2 Nucleophilic Substitution",
        "category": "치환",
        "mechanism_type": "sn2",
        "substrate_fg": ["1차 알킬 할로겐화물", "2차 알킬 할로겐화물", "알릴/벤질 할로겐화물"],
        "reagent_fg": ["하이드록사이드", "할로겐 음이온", "시안화물", "1차 아민", "티올"],
        "conditions": [
            ReactionCondition("NaOH (aq)", "RT", "DMSO"),
            ReactionCondition("NaCN", "RT", "DMSO"),
            ReactionCondition("NaI (Finkelstein)", "RT", "아세톤"),
        ],
        "confidence": 0.85,
        "description": "강한 친핵체가 1차/메틸 탄소를 후면 공격 (Walden 전환). 비극성 비양성자성 용매에서 유리.",
        "regiochemistry": "",
        "stereochemistry": "Inversion (Walden 전환)",
    },
    {
        "name": "SN1 (단분자 친핵성 치환)",
        "name_en": "SN1 Unimolecular Nucleophilic Substitution",
        "category": "치환",
        "mechanism_type": "sn1",
        "substrate_fg": ["3차 알킬 할로겐화물", "알릴/벤질 할로겐화물"],
        "reagent_fg": ["물", "1차 알코올", "2차 알코올"],
        "conditions": [
            ReactionCondition("H2O", "RT", "H2O (극성 양성자성)"),
            ReactionCondition("ROH", "RT", "알코올"),
        ],
        "confidence": 0.70,
        "description": "이탈기가 먼저 이탈 → 카르보카티온 중간체 생성 → 약한 친핵체 공격. 극성 양성자성 용매에서 유리.",
        "regiochemistry": "",
        "stereochemistry": "Racemization (라세미화)",
    },

    # ═══ 제거 반응 (Elimination) ═══
    {
        "name": "E2 (이분자 제거)",
        "name_en": "E2 Bimolecular Elimination",
        "category": "제거",
        "mechanism_type": "e2",
        "substrate_fg": ["2차 알킬 할로겐화물", "3차 알킬 할로겐화물"],
        "reagent_fg": ["하이드록사이드", "3차 아민"],
        "conditions": [
            ReactionCondition("KOH/EtOH", "Heat", "에탄올"),
            ReactionCondition("NaOEt", "Heat", "에탄올"),
            ReactionCondition("t-BuOK", "Heat", "t-BuOH"),
        ],
        "confidence": 0.75,
        "description": "강한 염기가 β-수소를 제거하면서 이탈기가 동시에 이탈. Anti-periplanar 배향 필요.",
        "regiochemistry": "Zaitsev (더 치환된 알켄)",
        "stereochemistry": "Anti-periplanar",
    },
    {
        "name": "E1 (단분자 제거)",
        "name_en": "E1 Unimolecular Elimination",
        "category": "제거",
        "mechanism_type": "e1",
        "substrate_fg": ["3차 알킬 할로겐화물"],
        "reagent_fg": ["물"],
        "conditions": [
            ReactionCondition("H2O", "Heat (60°C)", "H2O"),
        ],
        "confidence": 0.60,
        "description": "이탈기 먼저 이탈 → 카르보카티온 → β-수소 제거. SN1과 경쟁.",
        "regiochemistry": "Zaitsev",
        "stereochemistry": "혼합 (E/Z)",
    },

    # ═══ 첨가 반응 (Addition) ═══
    {
        "name": "Br₂ 반부가 (Bromonium Anti-Addition)",
        "name_en": "Bromine Anti-Addition via Bromonium Ion",
        "category": "첨가",
        "mechanism_type": "br2_anti_addition",
        "substrate_fg": ["알켄"],
        "reagent_fg": ["이원자 할로겐"],
        "conditions": [
            ReactionCondition("Br2", "RT", "CCl4 또는 CH2Cl2"),
        ],
        "confidence": 0.93,
        "description": "알켄 π 전자가 Br₂를 분극시켜 bromonium ion을 형성하고, Br⁻가 후면 공격하여 anti/trans-1,2-dibromide를 만든다.",
        "regiochemistry": "비대칭 알켄에서는 더 안정한 bromonium opening 경향",
        "stereochemistry": "Anti addition (trans)",
    },
    {
        "name": "친전자 첨가 (Markovnikov)",
        "name_en": "Electrophilic Addition (Markovnikov)",
        "category": "첨가",
        "mechanism_type": "electrophilic_addition",
        "substrate_fg": ["알켄"],
        "reagent_fg": ["물", "할로겐 음이온"],
        "conditions": [
            ReactionCondition("HBr", "RT", "—"),
            ReactionCondition("H2SO4/H2O", "RT", "H2O"),
            ReactionCondition("HCl", "RT", "—"),
        ],
        "confidence": 0.80,
        "description": "친전자체(H⁺)가 이중결합을 공격 → 카르보카티온 → 친핵체 첨가. Markovnikov 법칙 따름.",
        "regiochemistry": "Markovnikov",
        "stereochemistry": "혼합",
    },
    {
        "name": "친핵 첨가 (카르보닐)",
        "name_en": "Nucleophilic Addition to Carbonyl",
        "category": "첨가",
        "mechanism_type": "nucleophilic_addition",
        "substrate_fg": ["알데히드", "케톤"],
        "reagent_fg": ["하이드록사이드", "시안화물", "1차 아민", "하이드라이드"],
        "conditions": [
            ReactionCondition("NaBH4", "0°C", "MeOH"),
            ReactionCondition("LiAlH4", "0°C → RT", "THF"),
            ReactionCondition("RMgBr (Grignard)", "-78°C → RT", "THF"),
            ReactionCondition("NaCN/HCN", "RT", "H2O"),
        ],
        "confidence": 0.80,
        "description": "친핵체가 카르보닐 탄소(δ+)를 공격 → 사면체 중간체 생성.",
        "regiochemistry": "",
        "stereochemistry": "혼합 (프로카이럴 케톤: 라세미)",
    },

    # ═══ 방향족 반응 (Aromatic) ═══
    {
        "name": "친전자 방향족 치환 (EAS)",
        "name_en": "Electrophilic Aromatic Substitution",
        "category": "방향족",
        "mechanism_type": "eas",
        "substrate_fg": ["방향족 고리", "활성화된 방향족 (페놀)", "활성화된 방향족 (아닐린)", "활성화된 방향족 (아니솔)"],
        "reagent_fg": ["할로겐 음이온", "이원자 할로겐"],
        "conditions": [
            ReactionCondition("Br2/FeBr3", "RT", "CH2Cl2"),
            ReactionCondition("Cl2/AlCl3 (할로겐화)", "RT", "CH2Cl2"),
            ReactionCondition("HNO3/H2SO4 (니트로화)", "0°C", "H2SO4"),
            ReactionCondition("RCOCl/AlCl3 (아실화)", "RT", "CH2Cl2"),
        ],
        "confidence": 0.75,
        "description": "방향족 고리의 π-전자가 친전자체를 공격 → σ-complex → 양성자 이탈로 방향족성 회복.",
        "regiochemistry": "EDG: ortho/para, EWG: meta",
        "stereochemistry": "",
    },

    # ═══ 산화환원 (Redox) ═══
    {
        "name": "1차 알코올 산화",
        "name_en": "Primary Alcohol Oxidation",
        "category": "산화환원",
        "mechanism_type": "oxidation",
        "substrate_fg": ["1차 알코올"],
        "reagent_fg": [],
        "conditions": [
            ReactionCondition("PCC (알데히드까지)", "RT", "CH2Cl2"),
            ReactionCondition("KMnO4 (카르복실산까지)", "Heat", "H2O"),
            ReactionCondition("CrO3/H2SO4 (Jones)", "RT", "아세톤"),
        ],
        "confidence": 0.85,
        "description": "1차 알코올 → 알데히드 (PCC) 또는 → 카르복실산 (KMnO4). 산화제 선택이 생성물 결정.",
        "regiochemistry": "",
        "stereochemistry": "",
    },

    # ═══ 축합 반응 (Condensation) ═══
    {
        "name": "에스터화 (Fischer)",
        "name_en": "Fischer Esterification",
        "category": "축합",
        "mechanism_type": "esterification",
        "substrate_fg": ["카르복실산"],
        "reagent_fg": ["1차 알코올", "2차 알코올"],
        "conditions": [
            ReactionCondition("H2SO4 (cat.)", "Reflux", "—"),
            ReactionCondition("DCC/DMAP", "RT", "CH2Cl2"),
        ],
        "confidence": 0.80,
        "description": "카르복실산 + 알코올 → 에스터 + 물. 산 촉매하 평형반응 (Le Chatelier로 구동).",
        "regiochemistry": "",
        "stereochemistry": "",
    },
    {
        "name": "아마이드 결합 형성",
        "name_en": "Amide Bond Formation",
        "category": "축합",
        "mechanism_type": "amidation",
        "substrate_fg": ["카르복실산", "아실 할로겐화물"],
        "reagent_fg": ["1차 아민", "2차 아민"],
        "conditions": [
            ReactionCondition("DCC/EDC", "RT", "DMF"),
            ReactionCondition("SOCl2 → RNH2", "0°C → RT", "CH2Cl2"),
        ],
        "confidence": 0.80,
        "description": "카르복실산/아실 할로겐화물 + 아민 → 아마이드. 펩타이드 결합의 기본 반응.",
        "regiochemistry": "",
        "stereochemistry": "",
    },

    # ═══ 페리사이클릭 (Pericyclic) ═══
    {
        "name": "Diels-Alder 반응",
        "name_en": "Diels-Alder [4+2] Cycloaddition",
        "category": "첨가",
        "mechanism_type": "diels_alder",
        "substrate_fg": ["공액 디엔"],
        "reagent_fg": ["알켄", "알카인"],
        "conditions": [
            ReactionCondition("Heat (열적)", "100-200°C", "—"),
            ReactionCondition("Lewis acid (BF3·Et2O)", "RT", "CH2Cl2"),
        ],
        "confidence": 0.70,
        "description": "디엔(4π) + 디에노필(2π) → 사이클로헥센. 전자풍부 디엔 + 전자결핍 디에노필에서 유리.",
        "regiochemistry": "endo 법칙 (2차 오비탈 중첩)",
        "stereochemistry": "syn-addition (suprafacial)",
    },

    # ═══ 페리고리: [2+2] 고리화 첨가 ═══
    {
        "name": "[2+2] 고리화 첨가",
        "name_en": "[2+2] Cycloaddition",
        "category": "첨가",
        "mechanism_type": "cycloaddition_2_2",
        "substrate_fg": ["알켄"],
        "reagent_fg": ["알켄"],
        "conditions": [
            ReactionCondition("hν (광화학)", "RT", "—"),
            ReactionCondition("Lewis acid (BF3·Et2O)", "RT", "CH2Cl2"),
        ],
        "confidence": 0.55,
        "description": "두 알켄의 [2+2] 고리화 첨가. 열적으로 Woodward-Hoffmann 금지, 광화학적으로 허용.",
        "regiochemistry": "head-to-head (케텐류는 예외)",
        "stereochemistry": "suprafacial-suprafacial (광화학)",
    },

    # ═══ 페리고리: Cope 재배열 ═══
    {
        "name": "Cope 재배열",
        "name_en": "Cope Rearrangement",
        "category": "재배열",
        "mechanism_type": "cope_rearrangement",
        "substrate_fg": ["공액 디엔"],
        "reagent_fg": [],
        "conditions": [
            ReactionCondition("Heat (열적)", "150-250°C", "—"),
        ],
        "confidence": 0.50,
        "description": "1,5-헥사디엔 골격의 [3,3]-시그마트로피 재배열. 의자형 전이 상태를 경유.",
        "regiochemistry": "",
        "stereochemistry": "suprafacial-suprafacial",
    },

    # ═══ 페리고리: Claisen 재배열 ═══
    {
        "name": "Claisen 재배열",
        "name_en": "Claisen Rearrangement",
        "category": "재배열",
        "mechanism_type": "claisen_rearrangement",
        "substrate_fg": ["알릴 비닐 에터"],
        "reagent_fg": [],
        "conditions": [
            ReactionCondition("Heat (열적)", "150-200°C", "—"),
            ReactionCondition("Ireland-Claisen (LDA, TMSCl)", "-78°C → RT", "THF"),
        ],
        "confidence": 0.55,
        "description": "알릴 비닐 에터의 [3,3]-시그마트로피 재배열 → γ,δ-불포화 카르보닐 생성.",
        "regiochemistry": "",
        "stereochemistry": "suprafacial-suprafacial (의자형 TS)",
    },

    # ═══ 다리걸침 화합물: 노르보르넨 반응 ═══
    {
        "name": "노르보르넨 친전자 첨가",
        "name_en": "Norbornene Electrophilic Addition",
        "category": "첨가",
        "mechanism_type": "norbornene_addition",
        "substrate_fg": ["노르보르넨"],
        "reagent_fg": ["이원자 할로겐", "할로겐 음이온"],
        "conditions": [
            ReactionCondition("HBr", "RT", "—"),
            ReactionCondition("Br2/CCl4", "RT", "CCl4"),
        ],
        "confidence": 0.65,
        "description": "노르보르넨(다리걸침 알켄)의 친전자 첨가. exo 공격 선호 (비고전적 카르보카티온 안정화).",
        "regiochemistry": "exo-attack 선호",
        "stereochemistry": "exo-addition (anti-Bredt)",
    },

    # ═══ 다치환 방향족: EAS 다중 치환기 ═══
    {
        "name": "다치환 방향족 EAS",
        "name_en": "Multi-Substituted Aromatic EAS",
        "category": "방향족",
        "mechanism_type": "eas_multi_substituted",
        "substrate_fg": ["활성화된 방향족 (페놀)", "활성화된 방향족 (아닐린)", "활성화된 방향족 (아니솔)", "방향족 고리"],
        "reagent_fg": ["이원자 할로겐"],
        "conditions": [
            ReactionCondition("Br2/FeBr3", "RT", "CH2Cl2"),
            ReactionCondition("HNO3/H2SO4", "0°C", "H2SO4"),
        ],
        "confidence": 0.60,
        "description": "다치환 벤젠의 EAS. 기존 치환기들의 배향 효과(EDG: o/p, EWG: meta) 충돌 시 '활성화 치환기 우선' 규칙 적용.",
        "regiochemistry": "EDG 우선: ortho/para to strongest activator",
        "stereochemistry": "",
    },

    # ═══ 전이금속 촉매: Suzuki Coupling ═══
    {
        "name": "Suzuki-Miyaura 커플링",
        "name_en": "Suzuki-Miyaura Cross-Coupling",
        "category": "커플링",
        "mechanism_type": "suzuki_coupling",
        "substrate_fg": ["아릴 할로겐화물"],
        "reagent_fg": ["보론산"],
        "conditions": [
            ReactionCondition("Pd(PPh3)4 / Na2CO3 (aq)", "80°C", "THF/H2O"),
            ReactionCondition("Pd(dppf)Cl2 / K2CO3", "80°C", "Dioxane/H2O"),
        ],
        "confidence": 0.75,
        "description": "Pd(0) 촉매 사이클: 산화적 첨가 → 트랜스메탈화 → 환원적 제거. Ar-X + Ar'-B(OH)2 → Ar-Ar'.",
        "regiochemistry": "",
        "stereochemistry": "cis → trans 이성화 후 환원적 제거",
    },

    # ═══ 전이금속 촉매: Heck Reaction ═══
    {
        "name": "Heck 반응",
        "name_en": "Heck Reaction (Mizoroki-Heck)",
        "category": "커플링",
        "mechanism_type": "heck_reaction",
        "substrate_fg": ["아릴 할로겐화물"],
        "reagent_fg": ["알켄"],
        "conditions": [
            ReactionCondition("Pd(OAc)2 / PPh3 / Et3N", "100°C", "DMF"),
            ReactionCondition("Pd(PPh3)4 / K2CO3", "80°C", "DMF"),
        ],
        "confidence": 0.70,
        "description": "Pd(0) 촉매 사이클: 산화적 첨가 → syn-삽입 → β-H 제거. Ar-X + CH2=CHR → Ar-CH=CHR.",
        "regiochemistry": "β-위치에 아릴기 도입 (trans 생성물 우선)",
        "stereochemistry": "trans 알켄 선호 (열역학적 안정성)",
    },

    # ═══ [M708 F5-9] 추가 규칙: Grignard, Aldol, Wittig, 에폭사이드 개환 ═══
    {
        "name": "Grignard 반응",
        "name_en": "Grignard Reaction",
        "category": "첨가",
        "mechanism_type": "grignard_addition",
        "substrate_fg": ["알데히드", "케톤", "에스터"],
        "reagent_fg": [
            "1차 알킬 할로겐화물", "2차 알킬 할로겐화물", "아릴 할로겐화물"],
        "conditions": [
            ReactionCondition("Mg / Et2O, then H3O+", "-78C -> RT", "Et2O (무수)"),
            ReactionCondition("Mg / THF, then NH4Cl(aq)", "0C -> RT", "THF (무수)"),
        ],
        "confidence": 0.80,
        "description": (
            "RMgBr(Grignard 시약, March 16.24)이 카르보닐 탄소를 공격"
            " → 마그네슘 알콕사이드 → 수성 처리 후 알코올 생성."
            " 케톤 → 3차 알코올, 알데히드 → 2차 알코올."
        ),
        "regiochemistry": "",
        "stereochemistry": "혼합 (카르보닐 카이럴 시 라세미)",
    },
    {
        "name": "Aldol 반응/축합",
        "name_en": "Aldol Addition / Condensation",
        "category": "축합",
        "mechanism_type": "aldol",
        "substrate_fg": ["알데히드", "케톤"],
        "reagent_fg": ["알데히드", "케톤"],
        "conditions": [
            ReactionCondition("NaOH (aq)", "RT", "H2O"),
            ReactionCondition("LDA / THF, then NH4Cl(aq)", "-78C -> RT", "THF"),
            ReactionCondition("TiCl4 / Et3N (Evans)", "-78C -> RT", "CH2Cl2"),
        ],
        "confidence": 0.75,
        "description": (
            "알파-탄소의 친핵성 공격으로 베타-히드록시카르보닐 생성 (Aldol 부가, March 16.37)."
            " 이어서 가열 시 탈수 → 알파,베타-불포화 카르보닐 (Aldol 축합)."
        ),
        "regiochemistry": "알파-탄소 위치 (가장 산성적 알파-H 기준)",
        "stereochemistry": "Zimmermann-Traxler 모델: E-엔올레이트→anti, Z-엔올레이트→syn",
    },
    {
        "name": "Wittig 반응",
        "name_en": "Wittig Reaction",
        "category": "축합",
        "mechanism_type": "wittig",
        "substrate_fg": ["알데히드", "케톤"],
        "reagent_fg": ["에스터", "니트릴"],
        "conditions": [
            ReactionCondition("Ph3P=CH2 (ylide) / Et2O", "RT -> Reflux", "Et2O"),
            ReactionCondition("Ph3P=CHR / THF", "0C -> RT", "THF"),
        ],
        "confidence": 0.70,
        "description": (
            "포스포늄 일라이드(Ph3P=CHR)가 카르보닐에 [2+2] 부가 → 옥세탄"
            " → 레트로[2+2] → 알켄 + Ph3P=O (March 16.44)."
            " 비안정화 일라이드→Z, 안정화 일라이드→E."
        ),
        "regiochemistry": "",
        "stereochemistry": "비안정화: cis(Z) 선호; 안정화: trans(E) 선호",
    },
    {
        "name": "에폭사이드 개환",
        "name_en": "Epoxide Ring Opening",
        "category": "치환",
        "mechanism_type": "epoxide_opening",
        "substrate_fg": ["에폭사이드"],
        "reagent_fg": [
            "1차 아민", "2차 아민", "하이드록사이드",
            "할로겐 음이온", "티올"],
        "conditions": [
            ReactionCondition("Nu-H / EtOH", "RT", "EtOH"),
            ReactionCondition("BF3.Et2O / Nu-H (산성)", "0C -> RT", "CH2Cl2"),
            ReactionCondition("NaOH (aq) (염기성)", "RT", "H2O"),
        ],
        "confidence": 0.80,
        "description": (
            "에폭사이드 (March 10.57): 산성 조건 → 더 치환된 탄소 공격;"
            " 염기성 → 덜 치환된 탄소 공격(SN2 유사)."
            " 생성물: trans-베타-아미노알코올 등."
        ),
        "regiochemistry": "산성: 더 치환된 탄소; 염기성: 덜 치환된 탄소",
        "stereochemistry": "Anti-attack → trans 생성물",
    },
]

# ═══ 추가 작용기 패턴 (TASK-RXTN-002 확장분) ═══
FUNCTIONAL_GROUP_PATTERNS_EXTENDED = [
    # === 다리걸침 화합물 ===
    ("노르보르넨", "Norbornene",
     "C1CC2CC1C=C2", "electrophile"),

    # === Claisen 기질 ===
    ("알릴 비닐 에터", "Allyl Vinyl Ether",
     "C=COC/C=C", "electrophile"),

    # === 전이금속 커플링 기질 ===
    ("아릴 할로겐화물", "Aryl Halide",
     "c[F,Cl,Br,I]", "electrophile"),
    ("보론산", "Boronic Acid",
     "cB(O)O", "nucleophile"),
]


# ============================================================================
# REACTION PREDICTOR
# ============================================================================

class ReactionPredictor:
    """두 분자의 SMILES를 받아 가능한 반응 경로 목록을 반환"""

    # [M708 F5-9] mechanism_type → forward reaction SMARTS (RDKit rdChemReactions)
    # 학술 출처: March's Advanced Organic Chemistry (7th ed.), Smith & March
    # [M769 A73-W1 F5-9] _FORWARD_SMARTS 확장 — grignard/aldol/wittig/sn1/reductive_amination
    # 학술 출처: March's Advanced Organic Chemistry 7th ed. + Clayden Organic Chemistry 2nd ed.
    # Rule M: product_smiles="" 빈 반환이 많아 사용자 "계산되는건 아무것도 없다" 격분 (F5-9).
    # 해결: 주요 mechanism_type 8종 추가 → _compute_product_smiles 커버리지 확장.
    _FORWARD_SMARTS: Dict[str, str] = {
        # SN2: RX + Nu- → RNu + X- (March 10.1)
        "sn2": "[C:1][Br,Cl,I:2].[#7,#8,#16:3]>>[C:1][*:3]",
        # E2: R-CHR-CX + base → alkene (March 17.2)
        "e2": "[C:1][C:2][Br,Cl,I:3]>>[C:1]=[C:2]",
        # Esterification: RCOOH + R'OH → RCOOR' (March 16.63)
        "esterification": "[CX3:1](=O)[OH:2].[OX2H:3][CX4:4]>>[CX3:1](=O)[OX2:3][CX4:4]",
        # Amidation: RCOCl + RNH2 → RCONHR (March 16.72)
        "amidation": "[CX3:1](=O)[Cl,Br,I].[NX3H2:2]>>[CX3:1](=O)[NX3H:2]",
        # EAS halogenation: ArH + Br2 → ArBr + HBr (March 11.2)
        "eas": "[c:1][H]>>[c:1][Br]",
        # Electrophilic addition: C=C + HBr → C-C-Br (Markovnikov, March 15.2)
        "electrophilic_addition": "[C:1]=[C:2].[Br,Cl,I:3]>>[C:1][C:2][*:3]",
        # Bromination of alkene: C=C + Br2 → vicinal dibromide via bromonium ion (anti).
        "br2_anti_addition": "[C:1]=[C:2].[Br:3][Br:4]>>[C:1]([Br:3])[C:2]([Br:4])",
        # Oxidation of primary alcohol → aldehyde (PCC, March 19.3)
        "oxidation": "[CH2:1][OH]>>[CH:1]=O",
        # Nucleophilic addition to carbonyl: R2C=O → R2CHOH (NaBH4, March 16.24)
        "nucleophilic_addition": "[C:1]=O>>[C:1][OH]",
        # [M769] Grignard addition: RMgBr + R'CHO → R-CH(OH)-R' (March 16.24)
        # 알데히드 기질 + 알킬 마그네슘 브로마이드 → 2차 알코올
        "grignard_addition": "[C:1]=O.[C:2][MgBr]>>[C:1]([OH])[C:2]",
        # [M769] Aldol addition: 2×R-CH2-CHO → β-hydroxy aldehyde (March 16.37 NaOH/H2O)
        # 케톤 α-H 친핵성 공격 → β-히드록시카르보닐
        "aldol": "[CX4:1][C:2]=O.[C:3][C:4]=O>>[C:3]([OH])[C:4][C:1][C:2]=O",
        # [M769] Wittig: Ph3P=CH2 + RCHO → RCH=CH2 (March 16.44)
        # 포스포늄 일라이드 + 알데히드/케톤 → 알켄 + Ph3P=O
        "wittig": "[C:1]=O.[C:2]=[P]>>[C:1]=[C:2]",
        # [M769] SN1: 3차 RX → R+ → ROH (March 10.1 — tert-alkyl halide + H2O)
        "sn1": "[CX4:1]([!H])([!H])([!H])[Br,Cl,I]>>[CX4:1]([!H])([!H])([!H])[OH]",
        # [M769] Reductive amination: R-CHO + R'NH2 → R-CH2-NHR' (NaBH3CN, March 16.72)
        # 알데히드/케톤 + 아민 → 이민 → 환원 → 2차 아민
        "reductive_amination": "[C:1]=O.[NX3H2:2]>>[C:1][NX3H:2]",
        # [M769] Diels-Alder: diene + dienophile → cyclohexene (March 15.56)
        # [4+2] 환화첨가
        "diels_alder": "[C:1]=[C:2]-[C:3]=[C:4].[C:5]=[C:6]>>[C:1]1[C:2]=[C:3][C:4][C:5][C:6]1",
        # [M769] Acid halide + alcohol → ester (March 16.63 acylation)
        "acylation": "[CX3:1](=O)[Cl,F].[OX2H:2]>>[CX3:1](=O)[OX2:2]",
    }

    def __init__(self):
        self._compiled_patterns = {}  # SMARTS 캐시
        # [M708 F5-9] 전향 반응 SMARTS 사전 컴파일 (Rule L: None guard 필수)
        self._compiled_forward: Dict[str, object] = {}
        if RDKIT_AVAILABLE:
            try:
                from rdkit.Chem import rdChemReactions as _rxn_module
                for mtype, sma in self._FORWARD_SMARTS.items():
                    try:
                        rxn = _rxn_module.ReactionFromSmarts(sma)
                        if rxn is not None:
                            self._compiled_forward[mtype] = rxn
                    except Exception as _ce:
                        logger.warning(
                            "[M708 F5-9] _FORWARD_SMARTS compile failed mtype=%s: %s",
                            mtype, _ce)
            except Exception as _ie:
                logger.warning("[M708 F5-9] rdChemReactions import failed: %s", _ie)

    def detect_functional_groups(self, smiles: str) -> List[FunctionalGroup]:
        """분자의 작용기 감지"""
        if not RDKIT_AVAILABLE:
            logger.warning("detect_functional_groups: RDKit not available")
            return []

        if not isinstance(smiles, str) or not smiles.strip():
            logger.warning("detect_functional_groups: invalid SMILES input (type=%s, value=%r)", type(smiles).__name__, smiles)
            return []

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("detect_functional_groups: failed to parse SMILES=%s", smiles)
            return []

        # 기본 + 확장 패턴 결합
        all_patterns = FUNCTIONAL_GROUP_PATTERNS + FUNCTIONAL_GROUP_PATTERNS_EXTENDED

        groups = []
        for name_kr, name_en, smarts, role in all_patterns:
            if smarts not in self._compiled_patterns:
                pat = Chem.MolFromSmarts(smarts)
                self._compiled_patterns[smarts] = pat
            pat = self._compiled_patterns[smarts]
            if pat is None:
                continue
            matches = mol.GetSubstructMatches(pat)
            for match in matches:
                groups.append(FunctionalGroup(
                    name=name_kr, name_en=name_en,
                    smarts=smarts, atom_indices=match, role=role
                ))
        return groups

    def predict(self, smiles_a: str, smiles_b: str) -> List[ReactionPathway]:
        """두 분자 간 가능한 반응 경로 예측

        Args:
            smiles_a: 첫 번째 분자 SMILES
            smiles_b: 두 번째 분자 SMILES

        Returns:
            신뢰도 내림차순 정렬된 ReactionPathway 리스트
        """
        if not RDKIT_AVAILABLE:
            logger.warning("predict: RDKit not available")
            return []

        if not isinstance(smiles_a, str) or not smiles_a.strip():
            logger.warning("predict: invalid smiles_a (type=%s, value=%r)", type(smiles_a).__name__, smiles_a)
            return []

        if not isinstance(smiles_b, str) or not smiles_b.strip():
            logger.warning("predict: invalid smiles_b (type=%s, value=%r)", type(smiles_b).__name__, smiles_b)
            return []

        fg_a = self.detect_functional_groups(smiles_a)
        fg_b = self.detect_functional_groups(smiles_b)

        if not fg_a and not fg_b:
            logger.info("predict: no functional groups detected in either molecule (A=%s, B=%s)", smiles_a, smiles_b)
            return []

        pathways = []

        # 양방향 매칭: A가 기질이고 B가 시약인 경우 + 반대
        for rule in REACTION_RULES:
            # Rule N: 타입 가드 — rule은 dict
            if not isinstance(rule, dict):
                continue
            # Case 1: A = substrate, B = reagent
            matches_a = self._match_fg_list(fg_a, rule.get("substrate_fg", []))
            matches_b = self._match_fg_list(fg_b, rule.get("reagent_fg", []))

            if matches_a and (matches_b or not rule.get("reagent_fg")):
                pw = self._create_pathway(rule, matches_a[0], matches_b[0] if matches_b else None,
                                          smiles_a, smiles_b, "A", "B")
                pathways.append(pw)

            # Case 2: B = substrate, A = reagent (중복 방지)
            matches_b2 = self._match_fg_list(fg_b, rule.get("substrate_fg", []))
            matches_a2 = self._match_fg_list(fg_a, rule.get("reagent_fg", []))

            if matches_b2 and (matches_a2 or not rule.get("reagent_fg")):
                pw = self._create_pathway(rule, matches_b2[0], matches_a2[0] if matches_a2 else None,
                                          smiles_b, smiles_a, "B", "A")
                # 중복 체크
                if not any(p.mechanism_type == pw.mechanism_type for p in pathways):
                    pathways.append(pw)

        # 신뢰도 내림차순 정렬
        pathways.sort(key=lambda p: p.confidence, reverse=True)

        return pathways

    def _match_fg_list(self, detected_fgs: List[FunctionalGroup],
                       required_names: List[str]) -> List[FunctionalGroup]:
        """감지된 작용기 목록에서 필요한 이름 매칭"""
        matched = []
        for fg in detected_fgs:
            if fg.name in required_names:
                matched.append(fg)
        return matched

    def _compute_product_smiles(self, mechanism_type: str,
                                substrate_smiles: str,
                                reagent_smiles: str) -> str:
        """[M708 F5-9] RDKit rdChemReactions으로 생성물 SMILES 계산.

        _FORWARD_SMARTS에 등록된 반응만 처리 가능.
        실패 시 빈 문자열 반환 (Rule M: logger.warning 기록, silent return 허용은 반환값""뿐).
        Rule L: MolFromSmiles + None 체크 의무.
        """
        if not RDKIT_AVAILABLE:
            return ""  # silent-ok: 엔진 미설치 케이스
        rxn = self._compiled_forward.get(mechanism_type)
        if rxn is None:
            return ""  # 미등록 mechanism_type → 빈 반환 (정상 케이스)
        try:
            # Rule L: None 체크
            sub_mol = Chem.MolFromSmiles(substrate_smiles) if isinstance(substrate_smiles, str) else None
            if sub_mol is None:
                logger.warning("[M708 F5-9] substrate parse fail: %r", substrate_smiles)
                return ""
            rea_mol = None
            if isinstance(reagent_smiles, str) and reagent_smiles.strip():
                rea_mol = Chem.MolFromSmiles(reagent_smiles)
                if rea_mol is None:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", reagent_smiles)
            # 2-반응물 시도 먼저, 실패 시 1-반응물
            reactant_sets = [(sub_mol, rea_mol)] if rea_mol is not None else []
            reactant_sets.append((sub_mol,))
            for reactants in reactant_sets:
                try:
                    products = rxn.RunReactants(reactants)
                    if products:
                        prod_mol = products[0][0]
                        Chem.SanitizeMol(prod_mol)
                        smi = Chem.MolToSmiles(prod_mol)
                        if smi:
                            return smi
                except Exception:
                    continue
        except Exception as _e:
            logger.warning(
                "[M708 F5-9] product compute failed mtype=%s sub=%r rea=%r: %s",
                mechanism_type, substrate_smiles, reagent_smiles, _e)
        return ""

    def _create_pathway(self, rule: Dict, substrate_fg: FunctionalGroup,
                        reagent_fg: Optional[FunctionalGroup],
                        substrate_smiles: str, reagent_smiles: str,
                        sub_label: str, rea_label: str) -> ReactionPathway:
        """규칙으로부터 ReactionPathway 생성"""
        # Rule N: isinstance guard (function-level)
        if not isinstance(rule, dict):
            return ReactionPathway(name="", name_en="", category="", mechanism_type="",
                                   conditions=[], product_smiles="", confidence=0.0,
                                   description="invalid rule type")
        mtype = rule["mechanism_type"]
        # [M708 F5-9] 생성물 SMILES 계산 (실패 시 "" — silent ok for product field)
        product_smi = self._compute_product_smiles(mtype, substrate_smiles, reagent_smiles)
        return ReactionPathway(
            name=rule["name"],
            name_en=rule["name_en"],
            category=rule["category"],
            mechanism_type=mtype,
            conditions=rule.get("conditions", []),
            product_smiles=product_smi,
            confidence=rule.get("confidence", 0.5),
            description=rule.get("description", ""),
            reactant_a_role=f"분자 {sub_label}: {substrate_fg.name} (기질)",
            reactant_b_role=f"분자 {rea_label}: {reagent_fg.name if reagent_fg else '시약'} (시약)",
            fg_a=substrate_fg,
            fg_b=reagent_fg,
            regiochemistry=rule.get("regiochemistry", ""),
            stereochemistry=rule.get("stereochemistry", ""),
        )

    def predict_from_combined_smiles(self, combined_smiles: str) -> List[ReactionPathway]:
        """Dot-separated SMILES에서 반응물을 분리하여 반응 예측

        캔버스에 2개 이상의 분자가 따로 그려진 경우, main_window가
        "CCBr.O" 등의 dot-separated SMILES를 전달합니다.
        이 메서드는 그것을 개별 반응물로 분리하여 predict()를 호출합니다.

        Args:
            combined_smiles: Dot-separated SMILES (예: "CCBr.[OH-]", "C=CC=C.C=C")

        Returns:
            신뢰도 내림차순 정렬된 ReactionPathway 리스트.
            분자가 1개이면 빈 리스트 반환 (자기 반응은 미지원).
            분자가 3개 이상이면 모든 2-분자 조합을 시도.
        """
        if not RDKIT_AVAILABLE:
            logger.warning("predict_from_combined_smiles: RDKit not available")
            return []

        if not isinstance(combined_smiles, str) or not combined_smiles.strip():
            logger.warning("predict_from_combined_smiles: invalid combined_smiles (type=%s, value=%r)",
                           type(combined_smiles).__name__, combined_smiles)
            return []

        # Parse and separate fragments
        mol = Chem.MolFromSmiles(combined_smiles)
        if mol is None:
            logger.warning("predict_from_combined_smiles: failed to parse SMILES=%s", combined_smiles)
            return []

        frags = Chem.GetMolFrags(mol, asMols=True)
        if len(frags) < 2:
            logger.info("predict_from_combined_smiles: fewer than 2 fragments in SMILES=%s (self-reaction not supported)",
                        combined_smiles)
            return []

        # Get canonical SMILES for each fragment
        frag_smiles = []
        for frag in frags:
            try:
                smi = Chem.MolToSmiles(frag)
                if smi:
                    frag_smiles.append(smi)
            except Exception as e:
                logger.warning("predict_from_combined_smiles: failed to convert fragment to SMILES: %s", e)
                continue

        if len(frag_smiles) < 2:
            logger.warning("predict_from_combined_smiles: fewer than 2 valid fragments after conversion")
            return []

        # 2 fragments: direct predict
        if len(frag_smiles) == 2:
            return self.predict(frag_smiles[0], frag_smiles[1])

        # 3+ fragments: try all pairwise combinations, merge & deduplicate
        all_pathways = []
        seen_types = set()
        for i in range(len(frag_smiles)):
            for j in range(i + 1, len(frag_smiles)):
                pws = self.predict(frag_smiles[i], frag_smiles[j])
                for pw in pws:
                    if pw.mechanism_type not in seen_types:
                        seen_types.add(pw.mechanism_type)
                        all_pathways.append(pw)

        all_pathways.sort(key=lambda p: p.confidence, reverse=True)
        return all_pathways

    def get_reaction_summary(self, pathway: ReactionPathway) -> str:
        """반응 경로 요약 텍스트 생성"""
        lines = [
            f"━━━ {pathway.name} ({pathway.name_en}) ━━━",
            f"분류: {pathway.category}",
            f"신뢰도: {'★' * int(pathway.confidence * 5)}{'☆' * (5 - int(pathway.confidence * 5))} ({pathway.confidence:.0%})",
            f"",
            f"역할:",
            f"  • {pathway.reactant_a_role}",
            f"  • {pathway.reactant_b_role}",
        ]
        if pathway.regiochemistry:
            lines.append(f"위치선택성: {pathway.regiochemistry}")
        if pathway.stereochemistry:
            lines.append(f"입체선택성: {pathway.stereochemistry}")
        lines.append(f"")
        lines.append(f"설명: {pathway.description}")
        # [M751 F5-9 FIX] 생성물 SMILES 명시 — 사용자: "계산되는건 아무것도 없냐"
        # product_smiles 있으면 표시, 없으면 명시적으로 "미계산" 안내 (Rule M)
        lines.append(f"")
        if pathway.product_smiles:
            lines.append(f"예측 생성물 SMILES: {pathway.product_smiles}")
        else:
            lines.append(f"생성물 SMILES: 미계산 (복잡 반응 또는 템플릿 미등록)")
        if pathway.conditions:
            lines.append(f"")
            lines.append(f"가능한 반응 조건 ({len(pathway.conditions)}종):")
            for i, cond in enumerate(pathway.conditions, 1):
                lines.append(f"  {i}. {cond.reagent} / {cond.temperature} / {cond.solvent}"
                             + (f" / cat. {cond.catalyst}" if cond.catalyst else ""))
        else:
            lines.append(f"반응 조건: 표준 조건 참조 (conditions 미등록)")
        return "\n".join(lines)
