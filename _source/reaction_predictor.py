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
    ("활성화된 방향족", "Activated Aromatic",
     "c1cc([OH,NH2,OCH3,N(C)C])ccc1", "nucleophile"),

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
        "substrate_fg": ["방향족 고리", "활성화된 방향족"],
        "reagent_fg": ["할로겐 음이온"],
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
]


# ============================================================================
# REACTION PREDICTOR
# ============================================================================

class ReactionPredictor:
    """두 분자의 SMILES를 받아 가능한 반응 경로 목록을 반환"""

    def __init__(self):
        self._compiled_patterns = {}  # SMARTS 캐시

    def detect_functional_groups(self, smiles: str) -> List[FunctionalGroup]:
        """분자의 작용기 감지"""
        if not RDKIT_AVAILABLE:
            return []
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []

        groups = []
        for name_kr, name_en, smarts, role in FUNCTIONAL_GROUP_PATTERNS:
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
            return []

        fg_a = self.detect_functional_groups(smiles_a)
        fg_b = self.detect_functional_groups(smiles_b)

        if not fg_a and not fg_b:
            return []

        pathways = []

        # 양방향 매칭: A가 기질이고 B가 시약인 경우 + 반대
        for rule in REACTION_RULES:
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

    def _create_pathway(self, rule: Dict, substrate_fg: FunctionalGroup,
                        reagent_fg: Optional[FunctionalGroup],
                        substrate_smiles: str, reagent_smiles: str,
                        sub_label: str, rea_label: str) -> ReactionPathway:
        """규칙으로부터 ReactionPathway 생성"""
        return ReactionPathway(
            name=rule["name"],
            name_en=rule["name_en"],
            category=rule["category"],
            mechanism_type=rule["mechanism_type"],
            conditions=rule.get("conditions", []),
            confidence=rule.get("confidence", 0.5),
            description=rule.get("description", ""),
            reactant_a_role=f"분자 {sub_label}: {substrate_fg.name} (기질)",
            reactant_b_role=f"분자 {rea_label}: {reagent_fg.name if reagent_fg else '시약'} (시약)",
            fg_a=substrate_fg,
            fg_b=reagent_fg,
            regiochemistry=rule.get("regiochemistry", ""),
            stereochemistry=rule.get("stereochemistry", ""),
        )

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
        if pathway.conditions:
            lines.append(f"")
            lines.append(f"가능한 반응 조건:")
            for i, cond in enumerate(pathway.conditions, 1):
                lines.append(f"  {i}. {cond.reagent} / {cond.temperature} / {cond.solvent}"
                             + (f" / cat. {cond.catalyst}" if cond.catalyst else ""))
        return "\n".join(lines)
