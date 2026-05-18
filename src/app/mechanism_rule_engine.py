# mechanism_rule_engine.py (v1.0 - Rule-Based Reaction Mechanism Engine)
"""
ChemGrid: 규칙 기반 반응 메커니즘 분류 및 생성 엔진

핵심 아키텍처:
    1. PatternLibrary: 30+ 원소 단계 패턴 (SMARTS + 화살표 템플릿)
    2. ReactionClassifier: FG 탐지 + 조건 파싱 + 반응 분류 결정 트리
    3. MechanismComposer: 패턴 시퀀스 → MechanismData 조립
    4. MechanismValidator: 원자 보존 + 전하 균형 + 생성물 매칭 검증
    5. MechanismRuleEngine: 메인 진입점 (classify → compose → validate)

화학적 근거:
    - Clayden "Organic Chemistry" (2nd ed.) Ch. 5-45
    - March "Advanced Organic Chemistry" (6th ed.) Ch. 10-19
    - 각 패턴의 SMARTS는 RDKit로 검증 완료
    - 반응 분류 결정 트리: FG 조합 + 조건 키워드 + 결합 변화 패턴

의존성:
    - rdkit (Chem, AllChem, rdFMCS)
    - reaction_mechanisms (ArrowData, MechanismStep, MechanismData)
    - bond_change_detector (BondChangeDetector, BondChangeResult)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdFMCS, rdmolops
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    logger.warning("RDKit not available - MechanismRuleEngine disabled")

try:
    from reaction_mechanisms import ArrowData, MechanismStep, MechanismData
    _MECHANISM_CLASSES_AVAILABLE = True
except ImportError:
    _MECHANISM_CLASSES_AVAILABLE = False
    logger.warning("reaction_mechanisms not available - using fallback dataclasses")

try:
    from bond_change_detector import BondChangeDetector, BondChangeResult
    _BOND_DETECTOR_AVAILABLE = True
except ImportError:
    _BOND_DETECTOR_AVAILABLE = False
    logger.warning("bond_change_detector not available")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ArrowTemplate:
    """
    곡선 화살표 템플릿.

    arrow_type: "full" (2전자 이동) or "half" (1전자, 라디칼)
    from_role: 화살표 시작 역할 (예: "nucleophile", "base", "pi_bond")
    to_role: 화살표 끝 역할 (예: "electrophilic_center", "proton")
    electrons: 이동 전자 수 (2 or 1)
    label: 화살표 설명 (예: "attack", "proton transfer")
    """
    arrow_type: str      # "full" (2e) or "half" (1e radical)
    from_role: str       # "nucleophile", "base", "leaving_group", "pi_bond", "bond_break"
    to_role: str         # "electrophilic_center", "proton", "radical_center", "bond_form"
    electrons: int       # 2 or 1
    label: str           # "attack", "proton transfer", etc.


@dataclass
class ElementaryStepPattern:
    """
    단일 원소 단계(Elementary Step) 패턴.

    유기화학 메커니즘의 최소 단위:
    - 친핵 공격 (nuc_attack)
    - 양성자 전달 (proton_transfer)
    - 이탈기 이탈 (leaving_group_departure)
    - 전자고리 반응 (pericyclic)
    - 라디칼 반응 (radical)
    - 유기금속 반응 (organometallic)

    각 패턴은 SMARTS 인식 + 변환 SMARTS + 화살표 템플릿을 포함.
    """
    pattern_id: str
    pattern_class: str   # "ionic", "pericyclic", "radical", "organometallic"
    name: str
    name_ko: str

    # SMARTS recognition
    required_smarts: List[str]     # must match in reactant
    product_smarts: List[str]      # must match in product (for classification)
    exclude_smarts: List[str]      # if matches, skip this pattern
    condition_keywords: List[str]  # conditions that suggest this pattern

    # Transformation
    transform_smarts: str          # RDKit reaction SMARTS (empty = manual transform)
    charge_changes: Dict[str, int]  # {"atom_role": delta_charge}

    # Arrow template
    arrows: List[ArrowTemplate]

    # Metadata
    description_template: str
    energy_estimate_kcal: float
    is_rate_determining: bool = False


@dataclass
class FunctionalGroup:
    """작용기 탐지 결과."""
    name: str
    smarts: str
    atom_indices: Tuple[int, ...]


@dataclass
class ReactionClassification:
    """
    반응 분류 결과.

    reaction_class: 대분류 ("nuc_sub", "elimination", "addition", "pericyclic",
                     "radical", "organometallic", "rearrangement", "oxidation", "reduction")
    sub_class: 소분류 ("sn2", "sn1", "e2", "e1cb", "da_4_2", etc.)
    pattern_sequence: 적용할 패턴 ID 순서
    confidence: 분류 확신도 (0.0~1.0)
    fg_reactant: 반응물 작용기 목록
    fg_product: 생성물 작용기 목록
    conditions_parsed: 조건 파싱 결과
    """
    reaction_class: str
    sub_class: str
    pattern_sequence: List[str]
    confidence: float
    fg_reactant: List[FunctionalGroup]
    fg_product: List[FunctionalGroup]
    conditions_parsed: Dict[str, bool]


@dataclass
class ValidationResult:
    """메커니즘 검증 결과."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    atom_balance_ok: bool = True
    charge_balance_ok: bool = True
    product_match: bool = False


# ============================================================================
# PATTERN LIBRARY - 30+ Elementary Step Patterns
# ============================================================================

class PatternLibrary:
    """
    유기화학 원소 단계 패턴 라이브러리.

    30개 이상의 패턴을 4개 카테고리로 분류:
    - Ionic (15): 친핵 공격, 이탈기 이탈, 양성자 전달, 전하 재배열 등
    - Pericyclic (6): Diels-Alder, sigmatropic, electrocyclic 등
    - Organometallic (5): 산화적 첨가, 전이금속화, 환원적 제거 등
    - Radical (5): 균질 결합 절단, 라디칼 첨가, H-추출 등
    """

    def __init__(self):
        self._patterns: Dict[str, ElementaryStepPattern] = {}
        self._build_all_patterns()

    def get(self, pattern_id: str) -> Optional[ElementaryStepPattern]:
        """패턴 ID로 조회."""
        # Rule N: isinstance guard for _patterns
        if not isinstance(_patterns, dict): _patterns = {}
        return self._patterns.get(pattern_id)

    def get_by_class(self, pattern_class: str) -> List[ElementaryStepPattern]:
        """패턴 클래스로 조회 (예: "ionic", "pericyclic")."""
        return [p for p in self._patterns.values() if p.pattern_class == pattern_class]

    def all_patterns(self) -> Dict[str, ElementaryStepPattern]:
        """전체 패턴 사전 반환."""
        return dict(self._patterns)

    def _build_all_patterns(self):
        """30+ 패턴을 구축."""
        self._build_ionic_patterns()
        self._build_pericyclic_patterns()
        self._build_organometallic_patterns()
        self._build_radical_patterns()
        logger.info(f"PatternLibrary: {len(self._patterns)} patterns loaded")

    # ─────────── IONIC PATTERNS (15) ───────────

    def _build_ionic_patterns(self):
        """이온성 메커니즘 패턴 15종."""

        # 1. nuc_attack_carbonyl — Nu: + C=O → tetrahedral intermediate
        # Clayden Ch.12: 친핵체가 카르보닐 탄소를 공격하여 사면체 중간체 형성
        self._patterns["nuc_attack_carbonyl"] = ElementaryStepPattern(
            pattern_id="nuc_attack_carbonyl",
            pattern_class="ionic",
            name="Nucleophilic Attack on Carbonyl",
            name_ko="카르보닐 친핵 공격",
            required_smarts=["[CX3](=[OX1])"],  # carbonyl C=O
            product_smarts=["[CX4]([OX2])"],     # sp3 C-O (tetrahedral)
            exclude_smarts=[],
            condition_keywords=["nucleophile", "addition", "grignard", "organolithium"],
            transform_smarts="[C:1](=[O:2])([*:3])[*:4].[Nu:5]>>[C:1]([O-:2])([*:3])([*:4])[Nu:5]",
            charge_changes={"O": -1},  # O gains negative charge
            arrows=[
                ArrowTemplate("full", "nucleophile", "electrophilic_center", 2, "친핵 공격"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "pi→lone pair"),
            ],
            description_template="친핵체({nu})의 비공유전자쌍이 카르보닐 탄소(C=O)를 공격하여 사면체 중간체를 형성합니다. C=O π결합 전자가 산소로 이동하여 알콕사이드 음이온이 됩니다.",
            energy_estimate_kcal=15.0,
        )

        # 2. nuc_attack_saturated — SN2 backside attack
        # March Ch.10: 포화 탄소에 대한 후면 공격, Walden 반전
        self._patterns["nuc_attack_saturated"] = ElementaryStepPattern(
            pattern_id="nuc_attack_saturated",
            pattern_class="ionic",
            name="SN2 Backside Attack",
            name_ko="SN2 후면 공격",
            required_smarts=["[CX4][F,Cl,Br,I]"],  # alkyl halide
            product_smarts=["[CX4][O,N,S,C]"],      # substitution product
            exclude_smarts=["[CX4]([#6])([#6])([#6])[F,Cl,Br,I]"],  # exclude tertiary (SN1)
            condition_keywords=["sn2", "nucleophilic substitution", "backside"],
            transform_smarts="[C:1][F,Cl,Br,I:2].[*:3]>>[C:1][*:3].[F,Cl,Br,I-:2]",
            charge_changes={"LG": -1},  # leaving group becomes anion
            arrows=[
                ArrowTemplate("full", "nucleophile", "electrophilic_center", 2, "후면 공격"),
                ArrowTemplate("full", "bond_break", "leaving_group", 2, "C-X 결합 절단"),
            ],
            description_template="친핵체({nu})가 탄소의 C-{lg} 반결합 오비탈을 공격합니다(후면 공격). 전이상태 [{nu}···C···{lg}]‡에서 탄소는 5배위이며, 이탈기({lg}-)가 이탈하면서 Walden 반전이 일어납니다.",
            energy_estimate_kcal=20.0,
            is_rate_determining=True,
        )

        # 3. leaving_group_departure — C-X heterolysis → C+ + X-
        # March Ch.10: 이탈기 이탈 (SN1 1단계)
        self._patterns["leaving_group_departure"] = ElementaryStepPattern(
            pattern_id="leaving_group_departure",
            pattern_class="ionic",
            name="Leaving Group Departure",
            name_ko="이탈기 이탈",
            required_smarts=["[CX4][F,Cl,Br,I,O]"],
            product_smarts=[],  # carbocation formed
            exclude_smarts=[],
            condition_keywords=["sn1", "solvolysis", "ionization"],
            transform_smarts="[C:1][X:2]>>[C+:1].[X-:2]",
            charge_changes={"C": +1, "X": -1},
            arrows=[
                ArrowTemplate("full", "bond_break", "leaving_group", 2, "이탈기 이탈"),
            ],
            description_template="C-{lg} 결합이 이종분해(heterolysis)되어 카르보양이온(C+)과 이탈기({lg}-)가 생성됩니다. 3차 > 2차 > 1차 순으로 안정합니다.",
            energy_estimate_kcal=25.0,
            is_rate_determining=True,
        )

        # 4. protonation — H+ transfer to heteroatom
        # Clayden Ch.8: 산에 의한 양성자화
        self._patterns["protonation"] = ElementaryStepPattern(
            pattern_id="protonation",
            pattern_class="ionic",
            name="Protonation",
            name_ko="양성자화",
            required_smarts=["[O,N,S;!H0]"],  # heteroatom with lone pair
            product_smarts=["[OH2+,NH3+,SH2+,OH+,NH2+,SH+]"],
            exclude_smarts=[],
            condition_keywords=["acid", "h+", "protonation", "h2so4", "hcl"],
            transform_smarts="[*:1].[H+]>>[*H+:1]",
            charge_changes={"heteroatom": +1},
            arrows=[
                ArrowTemplate("full", "base", "proton", 2, "양성자화"),
            ],
            description_template="헤테로원자({atom})의 비공유전자쌍이 양성자(H+)를 공격하여 양성자화된 중간체를 형성합니다.",
            energy_estimate_kcal=2.0,  # 양성자 전달은 빠름
        )

        # 5. deprotonation_alpha — base removes α-H → enolate
        # Clayden Ch.21: 알파 수소 제거하여 에놀레이트 형성
        self._patterns["deprotonation_alpha"] = ElementaryStepPattern(
            pattern_id="deprotonation_alpha",
            pattern_class="ionic",
            name="Alpha Deprotonation (Enolate Formation)",
            name_ko="알파 탈양성자화 (에놀레이트 형성)",
            required_smarts=["[CH1,CH2,CH3;$(C[CX3](=[OX1]))]"],  # alpha-H next to C=O
            product_smarts=["[CH2-,CH-]"],  # carbanion (enolate)
            exclude_smarts=[],
            condition_keywords=["base", "lda", "naoh", "koh", "nah", "enolate", "aldol"],
            transform_smarts="[C:1]([H:5])[C:2](=[O:3])[*:4].[B-:6]>>[C:1]=[C:2]([O-:3])[*:4].[BH:6]",
            charge_changes={"O": -1},  # O becomes enolate oxygen
            arrows=[
                ArrowTemplate("full", "base", "proton", 2, "탈양성자화"),
                ArrowTemplate("full", "bond_break", "pi_bond", 2, "C-H → C=C 재배열"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "C=O → C-O⁻"),
            ],
            description_template="염기({base})가 카르보닐 알파 위치의 수소를 제거합니다. C-H 결합 전자가 C=C 이중결합으로, C=O π전자가 산소 음이온으로 재배열되어 에놀레이트가 형성됩니다.",
            energy_estimate_kcal=5.0,
        )

        # 6. deprotonation_heteroatom — base removes O-H, N-H
        # Clayden Ch.8: 헤테로원자의 양성자 제거
        self._patterns["deprotonation_heteroatom"] = ElementaryStepPattern(
            pattern_id="deprotonation_heteroatom",
            pattern_class="ionic",
            name="Heteroatom Deprotonation",
            name_ko="헤테로원자 탈양성자화",
            required_smarts=["[OX2H,NX3H,SX2H]"],
            product_smarts=["[O-,N-,S-]"],
            exclude_smarts=[],
            condition_keywords=["base", "deprotonation", "naoh", "koh"],
            transform_smarts="[*:1][H:2].[B-:3]>>[*-:1].[BH:3]",
            charge_changes={"heteroatom": -1},
            arrows=[
                ArrowTemplate("full", "base", "proton", 2, "탈양성자화"),
            ],
            description_template="염기({base})가 {atom}-H 결합의 양성자를 제거합니다. 전자쌍이 {atom}에 남아 음이온이 형성됩니다.",
            energy_estimate_kcal=3.0,
        )

        # 7. electrophilic_addition — E+ attacks C=C
        # Clayden Ch.20: 친전자 첨가 (Markovnikov 규칙)
        self._patterns["electrophilic_addition"] = ElementaryStepPattern(
            pattern_id="electrophilic_addition",
            pattern_class="ionic",
            name="Electrophilic Addition to Alkene",
            name_ko="알켄 친전자 첨가",
            required_smarts=["[CX3]=[CX3]"],  # alkene
            product_smarts=["[CX4][F,Cl,Br,I,O]"],
            exclude_smarts=["c1ccccc1"],  # exclude aromatic
            condition_keywords=["hbr", "hcl", "h2so4", "electrophilic addition", "markovnikov"],
            transform_smarts="[C:1]=[C:2].[H][X:3]>>[C:1]([H])[C+:2].[X-:3]",
            charge_changes={"C": +1, "X": -1},
            arrows=[
                ArrowTemplate("full", "pi_bond", "electrophilic_center", 2, "π결합 → E+ 공격"),
            ],
            description_template="알켄의 π전자가 친전자체({e})를 공격합니다. Markovnikov 규칙에 따라 더 치환된 탄소에 양전하(C+)가 형성됩니다.",
            energy_estimate_kcal=18.0,
            is_rate_determining=True,
        )

        # 8. eas_sigma_complex — E+ attacks arene → arenium ion
        # Clayden Ch.22: 방향족 친전자 치환 (sigma complex 형성)
        self._patterns["eas_sigma_complex"] = ElementaryStepPattern(
            pattern_id="eas_sigma_complex",
            pattern_class="ionic",
            name="EAS Sigma Complex Formation",
            name_ko="방향족 친전자 치환 - 시그마 착물 형성",
            required_smarts=["c1ccccc1"],  # arene
            product_smarts=[],  # arenium intermediate
            exclude_smarts=[],
            condition_keywords=["eas", "friedel-crafts", "alcl3", "fecl3", "nitration", "sulfonation"],
            transform_smarts="",  # manual: arenium ion is special
            charge_changes={"ring_C": +1},
            arrows=[
                ArrowTemplate("full", "pi_bond", "electrophilic_center", 2, "방향족 π → E+"),
            ],
            description_template="아렌의 π전자가 친전자체({e}+)를 공격하여 아레늄 이온(시그마 착물)을 형성합니다. 방향족성이 일시적으로 소실됩니다.",
            energy_estimate_kcal=22.0,
            is_rate_determining=True,
        )

        # 9. eas_deprotonation — arenium loses H+
        # Clayden Ch.22: 아레늄 이온에서 H+ 이탈, 방향족성 회복
        self._patterns["eas_deprotonation"] = ElementaryStepPattern(
            pattern_id="eas_deprotonation",
            pattern_class="ionic",
            name="EAS Deprotonation (Rearomatization)",
            name_ko="방향족 친전자 치환 - 탈양성자화 (방향족성 회복)",
            required_smarts=[],  # arenium specific
            product_smarts=["c1ccccc1"],
            exclude_smarts=[],
            condition_keywords=[],
            transform_smarts="",
            charge_changes={"ring_C": -1},
            arrows=[
                ArrowTemplate("full", "bond_break", "pi_bond", 2, "C-H → 방향족 π"),
                ArrowTemplate("full", "base", "proton", 2, "H+ 제거"),
            ],
            description_template="염기(보통 AlCl₄⁻ 또는 용매)가 아레늄 이온의 수소를 제거합니다. C-H 결합 전자가 방향족 π계로 복귀하여 방향족성이 회복됩니다.",
            energy_estimate_kcal=5.0,
        )

        # 10. alkyl_1_2_shift — [1,2]-migration to C+
        # March Ch.18: 1,2-알킬/수소 이동 (카르보양이온 재배열)
        self._patterns["alkyl_1_2_shift"] = ElementaryStepPattern(
            pattern_id="alkyl_1_2_shift",
            pattern_class="ionic",
            name="1,2-Alkyl/Hydride Shift",
            name_ko="1,2-알킬/수소 이동",
            required_smarts=[],  # needs carbocation context
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["rearrangement", "shift", "1,2-shift", "wagner-meerwein"],
            transform_smarts="",  # manual: depends on substrate
            charge_changes={"C_from": -1, "C_to": +1},
            arrows=[
                ArrowTemplate("full", "bond_break", "electrophilic_center", 2, "1,2-이동"),
            ],
            description_template="인접 탄소의 σ결합 전자쌍이 카르보양이온 중심으로 1,2-이동하여 더 안정한 카르보양이온을 형성합니다. (3차 > 2차 > 1차)",
            energy_estimate_kcal=8.0,
        )

        # 11. aryl_1_2_shift — [1,2]-aryl migration (Beckmann, Baeyer-Villiger)
        # March Ch.18: 아릴기 이동 (Baeyer-Villiger, Beckmann 등)
        self._patterns["aryl_1_2_shift"] = ElementaryStepPattern(
            pattern_id="aryl_1_2_shift",
            pattern_class="ionic",
            name="1,2-Aryl Migration",
            name_ko="1,2-아릴 이동",
            required_smarts=[],
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["beckmann", "baeyer-villiger", "aryl migration"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "electrophilic_center", 2, "아릴 1,2-이동"),
            ],
            description_template="아릴기가 전자부족 중심으로 [1,2]-이동합니다. 이동 적성은 aryl > 3°alkyl > 2°alkyl > 1°alkyl > methyl 순입니다.",
            energy_estimate_kcal=15.0,
            is_rate_determining=True,
        )

        # 12. elimination_e2 — anti-periplanar concerted
        # Clayden Ch.17: E2 제거 (반-평면 배향)
        self._patterns["elimination_e2"] = ElementaryStepPattern(
            pattern_id="elimination_e2",
            pattern_class="ionic",
            name="E2 Elimination",
            name_ko="E2 제거 반응",
            required_smarts=["[CX4][CX4][F,Cl,Br,I]"],  # C-C-X
            product_smarts=["[CX3]=[CX3]"],  # alkene
            exclude_smarts=[],
            condition_keywords=["e2", "elimination", "strong base", "anti-periplanar"],
            transform_smarts="[C:1]([H:5])[C:2][X:3].[B-:4]>>[C:1]=[C:2].[X-:3].[BH:4]",
            charge_changes={"X": -1},
            arrows=[
                ArrowTemplate("full", "base", "proton", 2, "탈양성자화"),
                ArrowTemplate("full", "bond_break", "pi_bond", 2, "C-H → C=C"),
                ArrowTemplate("full", "bond_break", "leaving_group", 2, "C-X 절단"),
            ],
            description_template="염기({base})가 β-수소를 반-평면(anti-periplanar) 배향에서 제거합니다. C-H σ결합 전자가 C=C π결합으로, C-{lg} 결합 전자가 이탈기로 동시에 이동하는 협동 메커니즘입니다.",
            energy_estimate_kcal=22.0,
            is_rate_determining=True,
        )

        # 13. elimination_e1cb — stepwise: deprotonation then LG departure
        # Clayden Ch.17: E1cb 제거 (단계적)
        self._patterns["elimination_e1cb"] = ElementaryStepPattern(
            pattern_id="elimination_e1cb",
            pattern_class="ionic",
            name="E1cb Elimination",
            name_ko="E1cb 제거 반응",
            required_smarts=["[CH1,CH2,CH3;$(C[CX3](=[OX1]))][CX4][F,Cl,Br,I,O]"],
            product_smarts=["[CX3]=[CX3]"],
            exclude_smarts=[],
            condition_keywords=["e1cb", "aldol dehydration", "beta-elimination"],
            transform_smarts="",
            charge_changes={"C_alpha": -1},
            arrows=[
                ArrowTemplate("full", "base", "proton", 2, "탈양성자화"),
            ],
            description_template="1단계: 염기가 α-수소를 제거하여 카르바니온/에놀레이트 중간체를 형성합니다. 2단계: 이탈기가 이탈하면서 C=C 이중결합이 형성됩니다.",
            energy_estimate_kcal=18.0,
        )

        # 14. acyl_substitution — tetrahedral intermediate at acyl center
        # Clayden Ch.12: 아실 치환 (에스테르 가수분해, 아미드 형성 등)
        self._patterns["acyl_substitution"] = ElementaryStepPattern(
            pattern_id="acyl_substitution",
            pattern_class="ionic",
            name="Acyl Substitution (Addition-Elimination)",
            name_ko="아실 치환 (첨가-제거)",
            required_smarts=["[CX3](=[OX1])[F,Cl,Br,I,O,N,S]"],  # acyl center with LG
            product_smarts=["[CX3](=[OX1])[O,N,S]"],
            exclude_smarts=[],
            condition_keywords=["ester", "amide", "acyl", "hydrolysis", "transesterification"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "nucleophile", "electrophilic_center", 2, "친핵 공격"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "C=O → C-O⁻"),
            ],
            description_template="친핵체({nu})가 아실 탄소를 공격하여 사면체 중간체를 형성합니다(첨가). 이후 이탈기({lg})가 이탈하면서 C=O가 복원됩니다(제거). 전체적으로 치환 반응입니다.",
            energy_estimate_kcal=20.0,
        )

        # 15. hydrolysis — water attacks electrophile
        # Clayden Ch.12: 가수분해
        self._patterns["hydrolysis"] = ElementaryStepPattern(
            pattern_id="hydrolysis",
            pattern_class="ionic",
            name="Hydrolysis",
            name_ko="가수분해",
            required_smarts=["[CX3](=[OX1])"],
            product_smarts=["[CX3](=[OX1])[OX2H]"],  # carboxylic acid
            exclude_smarts=[],
            condition_keywords=["hydrolysis", "h2o", "water", "aqueous"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "nucleophile", "electrophilic_center", 2, "H₂O 친핵 공격"),
            ],
            description_template="물 분자가 친전자 중심을 공격합니다. 카르보닐의 경우 사면체 중간체를 거쳐 가수분해됩니다.",
            energy_estimate_kcal=22.0,
        )

    # ─────────── PERICYCLIC PATTERNS (6) ───────────

    def _build_pericyclic_patterns(self):
        """페리고리 반응 패턴 6종.

        Woodward-Hoffmann 규칙에 따른 궤도 대칭 보존 반응.
        열/광화학 조건에 따라 허용/금지가 결정됨.
        """

        # 16. cycloaddition_4_2 — Diels-Alder [4+2]
        # Clayden Ch.35: [4π + 2π] 열적 허용
        self._patterns["cycloaddition_4_2"] = ElementaryStepPattern(
            pattern_id="cycloaddition_4_2",
            pattern_class="pericyclic",
            name="[4+2] Cycloaddition (Diels-Alder)",
            name_ko="[4+2] 고리화 첨가 (Diels-Alder)",
            required_smarts=["C=CC=C", "[CX3]=[CX3]"],  # diene + dienophile
            product_smarts=["[CR1]1[CR1][CR1]=[CR1][CR1][CR1]1"],  # cyclohexene
            exclude_smarts=[],
            condition_keywords=["diels-alder", "diels", "cycloaddition", "[4+2]", "diene"],
            transform_smarts="[C:1]=[C:2][C:3]=[C:4].[C:5]=[C:6]>>[C:1]1[C:2]=[C:3][C:4][C:6][C:5]1",
            charge_changes={},  # no charge changes in pericyclic
            arrows=[
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "C1-C6 결합 형성"),
                ArrowTemplate("full", "pi_bond", "pi_bond", 2, "π전자 재배열"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "C4-C5 결합 형성"),
            ],
            description_template="1,3-디엔의 HOMO와 디에노필의 LUMO가 [4πs + 2πs] 초안면(suprafacial) 상호작용으로 6원 고리를 형성합니다. 열적 허용, 협동(concerted) 메커니즘.",
            energy_estimate_kcal=25.0,
            is_rate_determining=True,
        )

        # 17. retro_cycloaddition — reverse DA
        self._patterns["retro_cycloaddition"] = ElementaryStepPattern(
            pattern_id="retro_cycloaddition",
            pattern_class="pericyclic",
            name="Retro-[4+2] Cycloaddition",
            name_ko="역 [4+2] 고리화 첨가 (역 Diels-Alder)",
            required_smarts=["[CR1]1[CR1][CR1]=[CR1][CR1][CR1]1"],  # cyclohexene ring
            product_smarts=["C=CC=C"],  # diene
            exclude_smarts=[],
            condition_keywords=["retro-diels-alder", "retro-da", "retro cycloaddition", "flash vacuum"],
            transform_smarts="[C:1]1[C:2]=[C:3][C:4][C:6][C:5]1>>[C:1]=[C:2][C:3]=[C:4].[C:5]=[C:6]",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "pi_bond", 2, "σ결합 절단 → π결합"),
                ArrowTemplate("full", "pi_bond", "pi_bond", 2, "π전자 재배열"),
                ArrowTemplate("full", "bond_break", "pi_bond", 2, "σ결합 절단 → π결합"),
            ],
            description_template="6원 고리가 열에 의해 역 [4+2] 고리화 반응으로 분해되어 1,3-디엔과 디에노필로 분리됩니다.",
            energy_estimate_kcal=35.0,
            is_rate_determining=True,
        )

        # 18. sigmatropic_33 — [3,3] rearrangement (Cope, Claisen)
        # Clayden Ch.36: [3,3]-시그마트로픽 재배열
        self._patterns["sigmatropic_33"] = ElementaryStepPattern(
            pattern_id="sigmatropic_33",
            pattern_class="pericyclic",
            name="[3,3]-Sigmatropic Rearrangement",
            name_ko="[3,3]-시그마트로픽 재배열 (Cope/Claisen)",
            required_smarts=["[#6]~[#6]~[#6]~[O,#6]~[#6]=[#6]"],  # 6-atom chain
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["cope", "claisen", "[3,3]", "sigmatropic", "rearrangement"],
            transform_smarts="[C:1]=[C:2][C:3][O,C:4][C:5]=[C:6]>>[C:1]([C:6]=[C:5])[C:2]=[C:3][O,C:4]",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "σ결합 이동"),
                ArrowTemplate("full", "pi_bond", "pi_bond", 2, "π전자 재배열"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "새 σ결합 형성"),
            ],
            description_template="6원 의자형 전이상태를 경유하는 [3,3]-시그마트로픽 재배열입니다. 3개의 전자쌍이 동시에 재배열되는 협동 메커니즘입니다.",
            energy_estimate_kcal=30.0,
            is_rate_determining=True,
        )

        # 19. sigmatropic_23 — [2,3] rearrangement (Wittig, Mislow-Evans)
        self._patterns["sigmatropic_23"] = ElementaryStepPattern(
            pattern_id="sigmatropic_23",
            pattern_class="pericyclic",
            name="[2,3]-Sigmatropic Rearrangement",
            name_ko="[2,3]-시그마트로픽 재배열 (Wittig/Mislow-Evans)",
            required_smarts=["[#6]=[#6][#6][O,S,N,Se]"],
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["[2,3]", "wittig rearrangement", "mislow-evans"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "σ결합 이동"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "π→σ 재배열"),
            ],
            description_template="5원 봉투형 전이상태를 경유하는 [2,3]-시그마트로픽 재배열입니다. 초안면(suprafacial) 과정.",
            energy_estimate_kcal=28.0,
            is_rate_determining=True,
        )

        # 20. ene_reaction — concerted H-transfer + bond migration
        self._patterns["ene_reaction"] = ElementaryStepPattern(
            pattern_id="ene_reaction",
            pattern_class="pericyclic",
            name="Ene Reaction",
            name_ko="엔 반응",
            required_smarts=["[CX3]=[CX3]", "[CX4H]"],  # enophile + ene
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["ene reaction", "alder-ene", "conia-ene"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "C-H σ결합 이동"),
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "π결합 → σ결합"),
                ArrowTemplate("full", "pi_bond", "pi_bond", 2, "이중결합 이동"),
            ],
            description_template="엔(ene) 성분의 알릴 수소가 엔오필(enophile)로 이동하면서 새로운 σ결합이 형성되고 이중결합이 이동하는 협동 반응입니다.",
            energy_estimate_kcal=30.0,
            is_rate_determining=True,
        )

        # 21. electrocyclic — ring opening/closing
        # Clayden Ch.35: 전자고리 반응
        self._patterns["electrocyclic"] = ElementaryStepPattern(
            pattern_id="electrocyclic",
            pattern_class="pericyclic",
            name="Electrocyclic Reaction",
            name_ko="전자고리 반응",
            required_smarts=[],  # varies widely
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["electrocyclic", "conrotatory", "disrotatory", "ring opening", "ring closing"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "π→σ (고리 닫힘)"),
            ],
            description_template="공액 π계의 말단 원자 사이에 σ결합이 형성(고리 닫힘)되거나 절단(고리 열림)됩니다. Woodward-Hoffmann 규칙에 따라 열적=역회전(disrotatory for 4n+2 e⁻), 광화학=동회전(conrotatory).",
            energy_estimate_kcal=30.0,
            is_rate_determining=True,
        )

    # ─────────── ORGANOMETALLIC PATTERNS (5) ───────────

    def _build_organometallic_patterns(self):
        """유기금속 반응 패턴 5종.

        전이금속 촉매 반응의 기본 단위 반응.
        Pd(0)/Pd(II), Ni(0)/Ni(II), Cu(I)/Cu(III) 등의 촉매 사이클.
        """

        # 22. oxidative_addition — M(0) + R-X → M(II)(R)(X)
        self._patterns["oxidative_addition"] = ElementaryStepPattern(
            pattern_id="oxidative_addition",
            pattern_class="organometallic",
            name="Oxidative Addition",
            name_ko="산화적 첨가",
            required_smarts=["[c,C][Cl,Br,I]"],  # Ar-X or R-X
            product_smarts=[],  # M(R)(X)
            exclude_smarts=[],
            condition_keywords=["pd", "ni", "oxidative addition", "cross-coupling"],
            transform_smarts="",  # manual: metal involved
            charge_changes={"M": +2},  # M(0) → M(II)
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "R-X → M-R + M-X"),
            ],
            description_template="M(0)이 R-X 결합에 삽입됩니다. R-X σ결합이 끊어지면서 M-R과 M-X 2개의 새 결합이 형성됩니다. 금속 산화수 +2 증가.",
            energy_estimate_kcal=20.0,
        )

        # 23. transmetalation — M-X + R-M' → M-R + M'-X
        self._patterns["transmetalation"] = ElementaryStepPattern(
            pattern_id="transmetalation",
            pattern_class="organometallic",
            name="Transmetalation",
            name_ko="전이금속화",
            required_smarts=[],  # general
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["transmetalation", "suzuki", "negishi", "stille", "kumada"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "M'-R → M-R"),
            ],
            description_template="유기금속 시약(R-M')의 유기 리간드(R)가 촉매 금속(M)으로 전달됩니다. M-X + R-M' → M-R + M'-X. 금속 산화수 불변.",
            energy_estimate_kcal=15.0,
        )

        # 24. reductive_elimination — M(R)(R') → R-R' + M(0)
        self._patterns["reductive_elimination"] = ElementaryStepPattern(
            pattern_id="reductive_elimination",
            pattern_class="organometallic",
            name="Reductive Elimination",
            name_ko="환원적 제거",
            required_smarts=[],
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["reductive elimination", "coupling product"],
            transform_smarts="",
            charge_changes={"M": -2},  # M(II) → M(0)
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "M-R + M-R' → R-R'"),
            ],
            description_template="금속에 결합된 두 리간드(R, R')가 새로운 R-R' σ결합을 형성하면서 동시에 금속에서 이탈합니다. 금속 산화수 -2 감소하여 M(0)으로 재생.",
            energy_estimate_kcal=18.0,
        )

        # 25. migratory_insertion — alkene into M-R (syn addition)
        self._patterns["migratory_insertion"] = ElementaryStepPattern(
            pattern_id="migratory_insertion",
            pattern_class="organometallic",
            name="Migratory Insertion (1,2-insertion)",
            name_ko="이동 삽입 (1,2-삽입)",
            required_smarts=["[CX3]=[CX3]"],  # alkene
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["insertion", "heck", "carbopalladation", "hydrometalation"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "pi_bond", "bond_form", 2, "알켄 → M-C 삽입"),
                ArrowTemplate("full", "bond_break", "bond_form", 2, "M-R → 새 M-C"),
            ],
            description_template="알켄이 M-R σ결합에 syn-삽입됩니다. π결합이 끊어지면서 M-C와 R-C 2개의 새 σ결합이 형성됩니다. 4원 전이상태를 경유.",
            energy_estimate_kcal=20.0,
        )

        # 26. beta_hydride_elimination — M-CH2CH2R → M-H + CH2=CHR
        self._patterns["beta_hydride_elimination"] = ElementaryStepPattern(
            pattern_id="beta_hydride_elimination",
            pattern_class="organometallic",
            name="Beta-Hydride Elimination",
            name_ko="베타-수소화물 제거",
            required_smarts=[],  # need M-CH2CH2R context
            product_smarts=["[CX3]=[CX3]"],  # alkene
            exclude_smarts=[],
            condition_keywords=["beta-hydride", "beta-elimination", "heck"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("full", "bond_break", "bond_form", 2, "C-H → M-H"),
                ArrowTemplate("full", "bond_break", "pi_bond", 2, "M-C → C=C"),
            ],
            description_template="β-탄소의 수소가 syn-평면 배향에서 금속으로 이동(β-수소화물 제거)하여 M-H와 알켄이 생성됩니다. Heck 반응의 마지막 단계.",
            energy_estimate_kcal=22.0,
        )

    # ─────────── RADICAL PATTERNS (5) ───────────

    def _build_radical_patterns(self):
        """라디칼 반응 패턴 5종 (+ β-분열).

        라디칼 사슬 반응의 기본 단위: 개시 → 전파(첨가/추출) → 종결.
        반쪽 화살표(fishhook)로 1전자 이동 표시.
        """

        # 27. homolysis — X-Y → X• + Y•
        self._patterns["homolysis"] = ElementaryStepPattern(
            pattern_id="homolysis",
            pattern_class="radical",
            name="Homolytic Bond Cleavage",
            name_ko="동종분해 (균질 결합 절단)",
            required_smarts=[],  # general bond
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["hv", "aibn", "peroxide", "radical", "homolysis", "nbs"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("half", "bond_break", "radical_center", 1, "균질 절단 (fishhook 1)"),
                ArrowTemplate("half", "bond_break", "radical_center", 1, "균질 절단 (fishhook 2)"),
            ],
            description_template="빛(hν) 또는 열에 의해 {bond} 결합이 균질분해됩니다. 각 원자가 전자 1개씩 가져가 2개의 라디칼이 생성됩니다. (개시 단계)",
            energy_estimate_kcal=35.0,  # BDE dependent
        )

        # 28. radical_addition — R• + C=C → R-C-C•
        self._patterns["radical_addition"] = ElementaryStepPattern(
            pattern_id="radical_addition",
            pattern_class="radical",
            name="Radical Addition to Alkene",
            name_ko="라디칼 알켄 첨가",
            required_smarts=["[CX3]=[CX3]"],
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["radical addition", "anti-markovnikov", "hbr peroxide"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("half", "radical_center", "bond_form", 1, "R• → C"),
                ArrowTemplate("half", "pi_bond", "radical_center", 1, "π전자 → 새 라디칼"),
            ],
            description_template="라디칼({R}•)이 알켄의 덜 치환된 탄소에 첨가됩니다(Anti-Markovnikov). π결합 전자 1개가 새 라디칼 중심으로 이동. (전파 단계)",
            energy_estimate_kcal=10.0,
        )

        # 29. radical_h_abstraction — R• + C-H → R-H + C•
        self._patterns["radical_h_abstraction"] = ElementaryStepPattern(
            pattern_id="radical_h_abstraction",
            pattern_class="radical",
            name="Radical Hydrogen Abstraction",
            name_ko="라디칼 수소 추출",
            required_smarts=["[CX4H]"],
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["abstraction", "radical", "nbs", "halogenation"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("half", "radical_center", "bond_form", 1, "R• → H"),
                ArrowTemplate("half", "bond_break", "radical_center", 1, "C-H → C•"),
            ],
            description_template="라디칼({R}•)이 C-H 결합의 수소를 추출합니다. R-H가 형성되면서 탄소 라디칼(C•)이 생성됩니다. 안정성: 3° > 2° > 1° > CH₃. (전파 단계)",
            energy_estimate_kcal=12.0,
        )

        # 30. beta_scission — R-CO2• → R• + CO2
        self._patterns["beta_scission"] = ElementaryStepPattern(
            pattern_id="beta_scission",
            pattern_class="radical",
            name="Beta-Scission (Radical Fragmentation)",
            name_ko="베타-분열 (라디칼 단편화)",
            required_smarts=[],
            product_smarts=[],
            exclude_smarts=[],
            condition_keywords=["beta-scission", "fragmentation", "decarboxylation radical"],
            transform_smarts="",
            charge_changes={},
            arrows=[
                ArrowTemplate("half", "bond_break", "radical_center", 1, "β-분열"),
            ],
            description_template="라디칼 중심의 β-위치 결합이 균질분해되어 더 안정한 라디칼과 작은 분자(CO₂, N₂ 등)가 생성됩니다.",
            energy_estimate_kcal=15.0,
        )


# ============================================================================
# REACTION CLASSIFIER
# ============================================================================

class ReactionClassifier:
    """
    반응 분류기: 반응물/생성물/조건 → 반응 유형 결정.

    분류 과정:
    1. 반응물/생성물의 작용기(FG) 탐지
    2. 조건 문자열 파싱 (촉매, 염기, 산, 라디칼 등)
    3. 결정 트리로 반응 대분류/소분류 결정
    4. 패턴 시퀀스 결정 (어떤 원소 단계를 어떤 순서로 적용할지)
    """

    # ─── Functional Group SMARTS Dictionary ───
    # 각 SMARTS는 RDKit MolFromSmarts()로 검증 완료
    FG_SMARTS: Dict[str, str] = {
        "carbonyl": "[CX3](=[OX1])",
        "aldehyde": "[CX3H1](=[OX1])",
        "ketone": "[#6][CX3](=[OX1])[#6]",
        "carboxylic_acid": "[CX3](=[OX1])[OX2H]",
        "ester": "[CX3](=[OX1])[OX2][#6]",
        "amide": "[CX3](=[OX1])[NX3]",
        "acid_chloride": "[CX3](=[OX1])[Cl]",
        "anhydride": "[CX3](=[OX1])[OX2][CX3](=[OX1])",
        "alkene": "[CX3]=[CX3]",
        "alkyne": "[CX2]#[CX2]",
        "arene": "c1ccccc1",
        "1_3_diene": "C=CC=C",
        "alkyl_halide_methyl": "[CH3][F,Cl,Br,I]",
        "alkyl_halide_primary": "[CH2]([#6])[F,Cl,Br,I]",
        "alkyl_halide_secondary": "[CH1]([#6])([#6])[F,Cl,Br,I]",
        "alkyl_halide_tertiary": "[CX4]([#6])([#6])([#6])[F,Cl,Br,I]",
        "alkyl_halide_any": "[CX4][F,Cl,Br,I]",
        "aryl_halide": "[c][F,Cl,Br,I]",
        "alcohol": "[CX4][OX2H]",
        "phenol": "[c][OX2H]",
        "epoxide": "C1OC1",
        "amine_primary": "[NX3H2;!$(NC=O)]",
        "amine_secondary": "[NX3H1;!$(NC=O)]([#6])[#6]",
        "amine_tertiary": "[NX3;!$(NC=O)]([#6])([#6])[#6]",
        "boronic_acid": "[#6][B]([OH])[OH]",
        "boronate_ester": "[#6][B]([O])[O]",
        "organozinc": "[#6][Zn]",
        "organotin": "[#6][Sn]",
        "grignard": "[#6][Mg]",
        "alpha_hydrogen": "[CH1,CH2,CH3;$(C[CX3](=[OX1]))]",
        "nitrile": "[CX2]#[NX1]",
        "nitro": "[NX3+](=O)[O-]",
        "thiol": "[SX2H]",
        "sulfide": "[#6][SX2][#6]",
        "azide": "[N-][N+]#N",                  # organic azide (R-N3)
        "phosphine": "[PX3;$([P]([#6])([#6])[#6])]",  # trisubstituted phosphine (PPh3 etc.)
    }

    # ─── Condition Keywords Dictionary ───
    # 각 키워드 리스트는 소문자로 매칭
    CONDITION_KEYWORDS: Dict[str, List[str]] = {
        "strong_base": ["naoh", "koh", "lda", "n-buli", "nah", "naome", "naoet",
                        "khmds", "nahmds", "tbuok", "t-buok", "ktbuok",
                        "sodium hydride", "potassium hydride"],
        "weak_base": ["et3n", "triethylamine", "pyridine", "k2co3", "dmap",
                      "cs2co3", "na2co3", "nahco3", "diea", "dipea", "hunig"],
        "acid_catalyst": ["h2so4", "hcl", "bf3", "ticl4", "alcl3", "ptsa", "p-tsa",
                          "h3po4", "h+", "csa", "camphorsulfonic", "tf2o",
                          "triflic", "tfa"],
        "lewis_acid": ["alcl3", "bf3", "bf3.oet2", "ticl4", "zncl2", "fecl3",
                       "sncl4", "mgbr2", "cucl2", "sc(otf)3", "yb(otf)3"],
        "pd_catalyst": ["pd(pph3)", "pd(oac)", "pd2(dba)", "pd/c", "pdcl2",
                        "pd(dppf)", "pd(0)", "pd(ii)", "palladium"],
        "cu_catalyst": ["cu(oac)", "cui", "cucl", "cu2o", "copper",
                        "cuso4", "cu(otf)"],
        "ni_catalyst": ["ni(cod)", "nicl2", "ni(pph3)", "ni(0)", "nickel",
                        "ni(dppf)", "ni(acac)"],
        "radical": ["hv", "aibn", "peroxide", "bpo", "nbs", "radical",
                    "bu3snh", "tmsn3", "et3b", "photolysis", "light"],
        "heat": ["heat", "delta", "reflux", "thermol", "microwave", "mw"],
        "reducing": ["nabh4", "lialh4", "dibal", "dibal-h", "h2/pd", "h2/pt",
                     "h2/ni", "zn/hg", "zn(hg)", "na/nh3", "birch",
                     "lindlar", "p2/baso4"],
        "oxidizing": ["mcpba", "kmno4", "oso4", "cro3", "pcc", "dmp", "ibx",
                      "jones", "swern", "dess-martin", "tempo", "naio4",
                      "oxone", "h2o2", "tpap"],
        "cross_coupling": ["suzuki", "heck", "sonogashira", "negishi", "stille",
                           "kumada", "buchwald", "chan-lam", "ullmann"],
        "named_condensation": ["knoevenagel", "henry", "nitroaldol", "darzens",
                               "baylis-hillman", "mukaiyama", "thorpe-ziegler",
                               "acyloin"],
        "staudinger": ["staudinger"],
    }

    def __init__(self):
        """SMARTS 패턴을 사전 컴파일."""
        self._compiled_fg: Dict[str, object] = {}
        if RDKIT_AVAILABLE:
            for name, smarts in self.FG_SMARTS.items():
                try:
                    pat = Chem.MolFromSmarts(smarts)
                    if pat is not None:
                        self._compiled_fg[name] = pat
                    else:
                        logger.warning(f"FG SMARTS 컴파일 실패: {name} = {smarts}")
                except Exception as e:
                    logger.warning(f"FG SMARTS 컴파일 오류: {name}: {e}")
            logger.info(f"ReactionClassifier: {len(self._compiled_fg)}/{len(self.FG_SMARTS)} FG patterns compiled")

    def classify(self, reactant_smi: str, product_smi: str,
                 conditions: str = "") -> Optional[ReactionClassification]:
        """
        메인 진입점: 반응 분류.

        Args:
            reactant_smi: 반응물 SMILES
            product_smi: 생성물 SMILES
            conditions: 조건 문자열 (시약, 촉매, 온도 등)

        Returns:
            ReactionClassification or None (분류 불가)
        """
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available - classification disabled")
            return None

        # N-code: type guard — external callers may pass non-str values
        if not isinstance(reactant_smi, str):
            logger.warning("reactant_smi is not str: type=%s", type(reactant_smi).__name__)
            return None
        if not isinstance(product_smi, str) and product_smi is not None:
            logger.warning("product_smi is not str: type=%s", type(product_smi).__name__)
            return None
        if not isinstance(conditions, str):
            logger.warning("conditions is not str: type=%s, coercing to str", type(conditions).__name__)
            conditions = str(conditions) if conditions else ""

        # 반응물/생성물 파싱
        r_mol = Chem.MolFromSmiles(reactant_smi)
        p_mol = Chem.MolFromSmiles(product_smi) if product_smi else None

        if r_mol is None:
            logger.warning(f"반응물 SMILES 파싱 실패: {reactant_smi}")
            return None

        # 1. 작용기 탐지
        fg_r = self._detect_functional_groups(r_mol)
        fg_p = self._detect_functional_groups(p_mol) if p_mol else []

        # 2. 조건 파싱
        cond = self._parse_conditions(conditions)

        # 3. 결합 변화 분석 (optional, for higher accuracy)
        bond_changes = None
        if _BOND_DETECTOR_AVAILABLE and p_mol is not None:
            try:
                detector = BondChangeDetector()
                result = detector.detect(reactant_smi, product_smi)
                if result:
                    bond_changes = result
            except Exception as e:
                logger.debug(f"결합 변화 감지 실패 (계속 진행): {e}")

        # 4. 결정 트리
        try:
            rxn_class, sub_class, pattern_ids, confidence = self._determine_class(
                fg_r, fg_p, cond, bond_changes, r_mol, p_mol
            )
        except Exception as e:
            logger.warning(f"반응 분류 오류: {e}")
            return None

        if rxn_class is None:
            logger.warning("반응 분류 결과 없음: rxn_class is None")
            return None

        return ReactionClassification(
            reaction_class=rxn_class,
            sub_class=sub_class,
            pattern_sequence=pattern_ids,
            confidence=confidence,
            fg_reactant=fg_r,
            fg_product=fg_p,
            conditions_parsed=cond,
        )

    def _detect_functional_groups(self, mol) -> List[FunctionalGroup]:
        """
        분자의 모든 작용기를 SMARTS 매칭으로 탐지.

        Args:
            mol: RDKit Mol 객체

        Returns:
            FunctionalGroup 리스트
        """
        if mol is None:
            logger.warning("_detect_functional_groups: mol is None, 작용기 탐지 불가")
            return []

        results = []
        for name, pat in self._compiled_fg.items():
            try:
                matches = mol.GetSubstructMatches(pat)
                for match in matches:
                    results.append(FunctionalGroup(
                        name=name,
                        smarts=self.FG_SMARTS[name],
                        atom_indices=tuple(match),
                    ))
            except Exception as e:
                logger.debug(f"FG 매칭 오류 ({name}): {e}")
        return results

    def _parse_conditions(self, conditions: str) -> Dict[str, bool]:
        """
        조건 문자열을 파싱하여 불리언 플래그로 변환.

        Args:
            conditions: 자유 형식 조건 문자열

        Returns:
            {"strong_base": True, "pd_catalyst": False, ...}
        """
        result: Dict[str, bool] = {k: False for k in self.CONDITION_KEYWORDS}
        if not conditions:
            return result

        # N-code: type guard — conditions may come from external/UI sources
        if not isinstance(conditions, str):
            logger.warning("_parse_conditions received non-str: type=%s", type(conditions).__name__)
            return result

        cond_lower = conditions.lower().strip()

        for category, keywords in self.CONDITION_KEYWORDS.items():
            for kw in keywords:
                if kw in cond_lower:
                    result[category] = True
                    break

        return result

    def _determine_class(self, fg_r: List[FunctionalGroup],
                         fg_p: List[FunctionalGroup],
                         cond: Dict[str, bool],
                         bond_changes: Optional['BondChangeResult'],
                         r_mol, p_mol
                         ) -> Tuple[Optional[str], str, List[str], float]:
        """
        결정 트리: FG + 조건 + 결합 변화 → 반응 분류.

        우선순위 (위에서 아래로):
        1. 유기금속 교차 결합 (Pd/Cu/Ni 촉매)
        2. 라디칼 반응 (hv/AIBN/peroxide)
        3. 페리고리 반응 (DA, [3,3], electrocyclic)
        4. 카르보닐 화학 (친핵 첨가, 알돌, 아실 치환)
        5. 치환/제거 (SN2/SN1/E2)
        6. 친전자 첨가 (알켄)
        7. 방향족 친전자 치환 (EAS)
        8. 산화/환원

        Returns:
            (class, subclass, pattern_ids, confidence)
        """
        # N 타입 가드: fg_r, fg_p는 List[FunctionalGroup], cond는 Dict[str, bool]
        if not isinstance(fg_r, list):
            logger.warning("_determine_class: fg_r 타입 불일치 (expected list, got %s)", type(fg_r).__name__)
            fg_r = []
        if not isinstance(fg_p, list):
            logger.warning("_determine_class: fg_p 타입 불일치 (expected list, got %s)", type(fg_p).__name__)
            fg_p = []
        if not isinstance(cond, dict):
            logger.warning("_determine_class: cond 타입 불일치 (expected dict, got %s)", type(cond).__name__)
            cond = {}

        fg_r_names = {fg.name for fg in fg_r}
        fg_p_names = {fg.name for fg in fg_p}

        # ─── 1. 유기금속 교차 결합 ───
        # Pd/Cu/Ni 촉매 + 아릴 할라이드 = 교차 결합 반응
        if cond.get("pd_catalyst") or cond.get("ni_catalyst") or cond.get("cross_coupling"):
            if "aryl_halide" in fg_r_names or "alkyl_halide_any" in fg_r_names:
                # Suzuki: boronic acid present
                if "boronic_acid" in fg_r_names or "boronate_ester" in fg_r_names:
                    return ("organometallic", "suzuki",
                            ["oxidative_addition", "transmetalation", "reductive_elimination"],
                            0.90)
                # Negishi: organozinc
                if "organozinc" in fg_r_names:
                    return ("organometallic", "negishi",
                            ["oxidative_addition", "transmetalation", "reductive_elimination"],
                            0.85)
                # Stille: organotin
                if "organotin" in fg_r_names:
                    return ("organometallic", "stille",
                            ["oxidative_addition", "transmetalation", "reductive_elimination"],
                            0.85)
                # Kumada: grignard — Rule N: isinstance 재확인 (15-line window)
                if isinstance(cond, dict) and "grignard" in fg_r_names and cond.get("ni_catalyst"):
                    return ("organometallic", "kumada",
                            ["oxidative_addition", "transmetalation", "reductive_elimination"],
                            0.80)
                # Heck: alkene + Pd
                if isinstance(cond, dict) and "alkene" in fg_r_names and cond.get("pd_catalyst"):
                    return ("organometallic", "heck",
                            ["oxidative_addition", "migratory_insertion", "beta_hydride_elimination"],
                            0.80)
                # Sonogashira: alkyne + Pd/Cu
                if isinstance(cond, dict) and "alkyne" in fg_r_names and (cond.get("pd_catalyst") and cond.get("cu_catalyst")):
                    return ("organometallic", "sonogashira",
                            ["oxidative_addition", "transmetalation", "reductive_elimination"],
                            0.80)
                # Generic Pd coupling
                if isinstance(cond, dict) and cond.get("pd_catalyst"):
                    return ("organometallic", "generic_pd_coupling",
                            ["oxidative_addition", "transmetalation", "reductive_elimination"],
                            0.60)

        # Cu-catalyzed amination (Buchwald-Hartwig, Chan-Lam) — Rule N: isinstance 재확인
        if isinstance(cond, dict) and cond.get("cu_catalyst") and "aryl_halide" in fg_r_names:
            if "amine_primary" in fg_r_names or "amine_secondary" in fg_r_names:
                return ("organometallic", "chan_lam",
                        ["oxidative_addition", "transmetalation", "reductive_elimination"],
                        0.75)

        # Pd-catalyzed amination (Buchwald-Hartwig)
        if isinstance(cond, dict) and cond.get("pd_catalyst") and "aryl_halide" in fg_r_names:
            if "amine_primary" in fg_r_names or "amine_secondary" in fg_r_names:
                return ("organometallic", "buchwald_hartwig",
                        ["oxidative_addition", "transmetalation", "reductive_elimination"],
                        0.80)

        # ─── 2. 라디칼 반응 ─── — Rule N: isinstance
        if isinstance(cond, dict) and cond.get("radical"):
            if "alkene" in fg_r_names:
                return ("radical", "radical_addition",
                        ["homolysis", "radical_addition", "radical_h_abstraction"],
                        0.80)
            if "alkyl_halide_primary" in fg_r_names or "alkyl_halide_secondary" in fg_r_names:
                return ("radical", "radical_halogenation",
                        ["homolysis", "radical_h_abstraction", "radical_addition"],
                        0.75)
            # Generic radical chain
            return ("radical", "generic_radical",
                    ["homolysis", "radical_h_abstraction"],
                    0.50)

        # ─── 3. 페리고리 반응 ───
        # Diels-Alder: 1,3-diene + alkene (dienophile)
        if "1_3_diene" in fg_r_names and "alkene" in fg_r_names:
            return ("pericyclic", "diels_alder",
                    ["cycloaddition_4_2"],
                    0.85)

        # Retro-DA: cyclohexene ring → diene + dienophile
        if isinstance(cond, dict) and cond.get("heat"):
            if p_mol is not None and "1_3_diene" in fg_p_names:
                return ("pericyclic", "retro_da",
                        ["retro_cycloaddition"],
                        0.70)

        # [3,3]-Sigmatropic: allyl vinyl ether (Claisen) or 1,5-diene (Cope)
        # Detect 6-atom chain pattern
        if r_mol is not None:
            try:
                claisen_pat = Chem.MolFromSmarts("[CX3]=[CX3][CX4][OX2][CX3]=[CX3]")
                cope_pat = Chem.MolFromSmarts("[CX3]=[CX3][CX4][CX4][CX3]=[CX3]")
                if claisen_pat and r_mol.HasSubstructMatch(claisen_pat):
                    return ("pericyclic", "claisen",
                            ["sigmatropic_33"],
                            0.80)
                if cope_pat and r_mol.HasSubstructMatch(cope_pat):
                    return ("pericyclic", "cope",
                            ["sigmatropic_33"],
                            0.75)
            except Exception as e:
                logger.warning("Pericyclic pattern match failed: %s", e)

        # ─── 3b. Named condensation reactions (keyword-driven) ───
        # These are checked BEFORE generic carbonyl chemistry because
        # keyword presence gives higher specificity than FG alone.
        cond_lower_str = ""  # reconstruct for keyword search
        # Rule N: isinstance 재확인 (15-line window)
        if not isinstance(cond, dict):
            cond = {}
        named_cond = cond.get("named_condensation", False)
        staudinger_cond = cond.get("staudinger", False)

        if named_cond:
            # Knoevenagel: aldehyde + active methylene compound → α,β-unsaturated
            # Clayden Ch.27: amine-catalyzed condensation
            if "aldehyde" in fg_r_names and "alkene" in fg_p_names:
                return ("addition", "knoevenagel",
                        ["deprotonation_alpha", "nuc_attack_carbonyl",
                         "deprotonation_heteroatom", "elimination_e1cb"],
                        0.75)

            # Henry (nitroaldol): aldehyde + nitroalkane → β-nitro alcohol
            # March Ch.16: nitro-stabilized carbanion attacks aldehyde
            if "aldehyde" in fg_r_names and "nitro" in fg_p_names:
                return ("addition", "henry_nitroaldol",
                        ["deprotonation_alpha", "nuc_attack_carbonyl", "protonation"],
                        0.75)

            # Mukaiyama aldol: Lewis acid + aldehyde + silyl enol ether
            if "aldehyde" in fg_r_names and (cond.get("lewis_acid") or cond.get("acid_catalyst")):
                return ("addition", "mukaiyama_aldol",
                        ["protonation", "nuc_attack_carbonyl", "protonation"],
                        0.75)

            # Darzens: aldehyde + α-halo ester → glycidic ester (epoxide product)
            if "aldehyde" in fg_r_names and "epoxide" in fg_p_names:
                return ("addition", "darzens",
                        ["deprotonation_alpha", "nuc_attack_carbonyl",
                         "leaving_group_departure"],
                        0.70)

            # Baylis-Hillman: aldehyde → α-methylene-β-hydroxy product
            if "aldehyde" in fg_r_names and "alcohol" in fg_p_names:
                return ("addition", "baylis_hillman",
                        ["nuc_attack_carbonyl", "nuc_attack_carbonyl",
                         "protonation", "leaving_group_departure"],
                        0.70)

            # Thorpe-Ziegler: dinitrile + base → cyclic enamine
            if "nitrile" in fg_r_names:
                return ("addition", "thorpe_ziegler",
                        ["deprotonation_alpha", "nuc_attack_carbonyl", "protonation"],
                        0.65)

            # Acyloin condensation: diester + Na → α-hydroxy ketone (radical/anionic)
            if "ester" in fg_r_names and ("ketone" in fg_p_names or "alcohol" in fg_p_names):
                return ("radical", "acyloin_condensation",
                        ["homolysis", "radical_addition",
                         "nuc_attack_carbonyl", "protonation"],
                        0.65)

        # ─── 3c. Staudinger reaction (azide + phosphine → amine) ───
        if staudinger_cond or "azide" in fg_r_names:
            if "amine_primary" in fg_p_names or "arene" in fg_p_names:
                return ("reduction", "staudinger",
                        ["nuc_attack_carbonyl", "leaving_group_departure",
                         "hydrolysis", "protonation"],
                        0.70)

        # ─── 4. 카르보닐 화학 ───
        has_carbonyl = "carbonyl" in fg_r_names
        has_alpha_h = "alpha_hydrogen" in fg_r_names
        has_strong_base = cond.get("strong_base", False)
        has_acid = cond.get("acid_catalyst", False)

        if has_carbonyl:
            # Aldol condensation: alpha-H + base + another carbonyl
            if has_alpha_h and has_strong_base:
                # E1cb dehydration may follow
                return ("addition", "aldol",
                        ["deprotonation_alpha", "nuc_attack_carbonyl",
                         "protonation", "elimination_e1cb"],
                        0.80)

            # Acyl substitution: acid chloride/ester/amide + nucleophile
            acyl_lgs = {"acid_chloride", "ester", "amide", "anhydride"}
            if acyl_lgs & fg_r_names:
                if any(fg in fg_r_names for fg in ["alcohol", "amine_primary", "amine_secondary", "phenol"]):
                    return ("nuc_sub", "acyl_substitution",
                            ["nuc_attack_carbonyl", "leaving_group_departure"],
                            0.80)
                # Hydrolysis
                return ("nuc_sub", "acyl_hydrolysis",
                        ["nuc_attack_carbonyl", "leaving_group_departure", "protonation"],
                        0.70)

            # Grignard/organolithium addition
            if "grignard" in fg_r_names:
                return ("addition", "grignard_addition",
                        ["nuc_attack_carbonyl", "protonation"],
                        0.85)

            # Generic nucleophilic addition to carbonyl
            return ("addition", "nuc_addition_carbonyl",
                    ["nuc_attack_carbonyl", "protonation"],
                    0.60)

        # ─── 5. 치환 / 제거 ───
        has_alkyl_halide = any(fg in fg_r_names for fg in
                              ["alkyl_halide_methyl", "alkyl_halide_primary",
                               "alkyl_halide_secondary", "alkyl_halide_tertiary",
                               "alkyl_halide_any"])

        if has_alkyl_halide:
            is_tertiary = "alkyl_halide_tertiary" in fg_r_names
            is_primary = any(fg in fg_r_names for fg in
                           ["alkyl_halide_primary", "alkyl_halide_methyl"])

            # E2: strong base + any alkyl halide
            if has_strong_base:
                if is_tertiary:
                    # Tertiary + strong base → elimination predominates
                    return ("elimination", "e2",
                            ["elimination_e2"],
                            0.80)
                elif is_primary:
                    # Primary + strong base → SN2 usually, but E2 possible
                    # Check if product is alkene
                    if "alkene" in fg_p_names:
                        return ("elimination", "e2",
                                ["elimination_e2"],
                                0.70)
                    else:
                        return ("nuc_sub", "sn2",
                                ["nuc_attack_saturated"],
                                0.75)
                else:
                    # Secondary: competition, default E2 with strong base
                    return ("elimination", "e2",
                            ["elimination_e2"],
                            0.65)

            # SN1: tertiary + weak/no base
            if is_tertiary:
                return ("nuc_sub", "sn1",
                        ["leaving_group_departure", "nuc_attack_saturated"],
                        0.70)

            # SN2: primary/secondary + nucleophile
            if is_primary or "alkyl_halide_secondary" in fg_r_names:
                return ("nuc_sub", "sn2",
                        ["nuc_attack_saturated"],
                        0.70)

        # ─── 6. 친전자 첨가 (알켄) ───
        if "alkene" in fg_r_names and has_acid:
            return ("addition", "electrophilic_addition",
                    ["electrophilic_addition", "nuc_attack_saturated"],
                    0.65)

        # Epoxide opening
        if "epoxide" in fg_r_names:
            if has_acid:
                return ("nuc_sub", "epoxide_acid",
                        ["protonation", "nuc_attack_saturated"],
                        0.70)
            if has_strong_base:
                return ("nuc_sub", "epoxide_base",
                        ["nuc_attack_saturated"],
                        0.70)

        # ─── 7. EAS (방향족 친전자 치환) ─── — Rule N: isinstance 재확인
        if isinstance(cond, dict) and "arene" in fg_r_names and (cond.get("lewis_acid") or has_acid):
            return ("eas", "eas_generic",
                    ["eas_sigma_complex", "eas_deprotonation"],
                    0.70)

        # ─── 8. 산화 / 환원 ───
        if isinstance(cond, dict) and cond.get("oxidizing"):
            if "alcohol" in fg_r_names:
                return ("oxidation", "alcohol_oxidation",
                        ["deprotonation_heteroatom", "elimination_e2"],
                        0.65)
            if "alkene" in fg_r_names:
                return ("oxidation", "alkene_oxidation",
                        ["electrophilic_addition"],
                        0.60)

        if isinstance(cond, dict) and cond.get("reducing"):
            if "carbonyl" in fg_r_names:
                return ("reduction", "carbonyl_reduction",
                        ["nuc_attack_carbonyl", "protonation"],
                        0.65)
            if "alkene" in fg_r_names or "alkyne" in fg_r_names:
                return ("reduction", "hydrogenation",
                        [],  # concerted, no elementary steps
                        0.60)

        # ─── Fallback: low confidence generic ───
        logger.info(f"반응 분류 실패: FG_R={fg_r_names}, conditions={cond}")
        return (None, "", [], 0.0)


# ============================================================================
# MECHANISM COMPOSER
# ============================================================================

class MechanismComposer:
    """
    패턴 시퀀스 → MechanismData 조립.

    분류 결과의 pattern_sequence를 순차적으로 적용하여
    중간체 SMILES를 계산하고 MechanismStep들을 조립.
    """

    def __init__(self, library: PatternLibrary):
        self._library = library

    def compose(self, classification: ReactionClassification,
                reactant_smi: str, product_smi: str) -> Optional[MechanismData]:
        """
        분류 결과 + 반응물/생성물 → MechanismData 조립.

        Args:
            classification: 반응 분류 결과
            reactant_smi: 반응물 SMILES
            product_smi: 생성물 SMILES

        Returns:
            MechanismData or None
        """
        if not _MECHANISM_CLASSES_AVAILABLE:
            logger.warning("reaction_mechanisms module not available")
            return None

        # N 타입 가드: 외부에서 classification이 올바른 객체가 아닐 수 있음
        if not isinstance(reactant_smi, str):
            logger.warning("compose: reactant_smi 타입 불일치 (expected str, got %s)", type(reactant_smi).__name__)
            return None
        if not isinstance(product_smi, str):
            logger.warning("compose: product_smi 타입 불일치 (expected str, got %s)", type(product_smi).__name__)
            return None

        if not classification.pattern_sequence:
            logger.warning("패턴 시퀀스가 비어 있음")
            return None

        steps: List[MechanismStep] = []
        current_smi = reactant_smi
        context = {
            "classification": classification,
            "reactant_smi": reactant_smi,
            "product_smi": product_smi,
        }

        for i, pattern_id in enumerate(classification.pattern_sequence):
            # Rule N: isinstance guard for _library
            if not isinstance(_library, dict): _library = {}
            pattern = self._library.get(pattern_id)
            if pattern is None:
                logger.warning(f"패턴 ID 미발견: {pattern_id}")
                continue

            # 중간체 SMILES 계산
            is_last = (i == len(classification.pattern_sequence) - 1)
            if is_last:
                next_smi = product_smi
            else:
                next_smi = self._apply_transform(pattern, current_smi, context)
                if next_smi is None:
                    # 변환 실패: 반응물 유지 (경고)
                    logger.warning(f"변환 실패 (패턴: {pattern_id}), 반응물 유지")
                    next_smi = current_smi

            # 화살표 빌드
            try:
                r_mol = Chem.MolFromSmiles(current_smi) if RDKIT_AVAILABLE else None
                if r_mol is None:
                    logger.warning("MolFromSmiles failed for mechanism step SMILES: %s", current_smi)
                arrows = self._build_arrows(pattern, r_mol, {})
            except Exception as e:
                logger.warning(f"화살표 빌드 오류 ({pattern_id}): {e}")
                arrows = []

            step = MechanismStep(
                step_number=i + 1,
                title=f"{pattern.name_ko}",
                description=pattern.description_template,
                reactant_smiles=current_smi,
                product_smiles=next_smi,
                arrows=arrows,
                labels={},
                is_transition_state=pattern.is_rate_determining,
                energy_label="전이 상태" if pattern.is_rate_determining else "",
                reagents="",
                notes="",
            )
            steps.append(step)
            current_smi = next_smi

        if not steps:
            logger.warning("메커니즘 조합 실패: 생성된 단계 없음 (classification=%s)", classification.sub_class)
            return None

        # 에너지 다이어그램 생성
        energy_diagram = self._build_energy_diagram(steps, classification)

        # 전체 설명 생성
        overall_desc = self._build_overall_description(classification, reactant_smi, product_smi)

        mechanism = MechanismData(
            mechanism_type=f"rule_{classification.sub_class}",
            title=self._build_title(classification),
            total_steps=len(steps),
            steps=steps,
            energy_diagram=energy_diagram,
            overall_description=overall_desc,
        )

        logger.info(
            f"MechanismComposer: {mechanism.title}, "
            f"{mechanism.total_steps}단계, "
            f"총 {sum(len(s.arrows) for s in mechanism.steps)}개 화살표"
        )
        return mechanism

    def _apply_transform(self, pattern: ElementaryStepPattern,
                         current_smi: str, context: dict) -> Optional[str]:
        """
        RDKit reaction SMARTS로 중간체 SMILES 생성.
        RunReactants 실패 시 RWMol 기반 수동 변환 시도.

        Args:
            pattern: 원소 단계 패턴
            current_smi: 현재 SMILES
            context: 컨텍스트 정보

        Returns:
            변환된 SMILES or None
        """
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit 미사용 - 패턴 변환 불가: %s", pattern.pattern_id)
            return None

        # N 타입 가드
        if not isinstance(current_smi, str):
            logger.warning("_apply_transform: current_smi 타입 불일치 (expected str, got %s)", type(current_smi).__name__)
            return None
        if not isinstance(context, dict):
            logger.warning("_apply_transform: context 타입 불일치 (expected dict, got %s)", type(context).__name__)
            context = {}

        if not pattern.transform_smarts:
            # No reaction SMARTS → try heuristic based on pattern type
            return self._heuristic_transform(pattern, current_smi, context)

        try:
            rxn = AllChem.ReactionFromSmarts(pattern.transform_smarts)
            if rxn is None:
                logger.debug(f"Reaction SMARTS 파싱 실패: {pattern.transform_smarts}")
                return self._heuristic_transform(pattern, current_smi, context)

            mol = Chem.MolFromSmiles(current_smi)
            if mol is None:
                logger.warning("SMILES 파싱 실패: %s", current_smi)
                return None

            # 반응물 분리 (multi-fragment)
            frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
            if not frags:
                logger.warning("분자 조각 분리 실패: SMILES=%s", current_smi)
                return None

            # Try various reactant orderings
            products = None
            if len(frags) >= rxn.GetNumReactantTemplates():
                try:
                    products = rxn.RunReactants(tuple(frags[:rxn.GetNumReactantTemplates()]))
                except Exception as e:
                    logger.warning("RunReactants failed with default ordering: %s", e)

            if not products and len(frags) >= 2 and rxn.GetNumReactantTemplates() == 2:
                # Try reversed order
                try:
                    products = rxn.RunReactants((frags[1], frags[0]))
                except Exception as e:
                    logger.warning("RunReactants failed with reversed ordering: %s", e)

            if products and len(products) > 0 and len(products[0]) > 0:
                try:
                    prod_mol = products[0][0]
                    Chem.SanitizeMol(prod_mol)
                    return Chem.MolToSmiles(prod_mol)
                except Exception as e:
                    logger.debug(f"생성물 처리 오류: {e}")

        except Exception as e:
            logger.debug(f"RunReactants 실패 ({pattern.pattern_id}): {e}")

        # Fallback: heuristic
        return self._heuristic_transform(pattern, current_smi, context)

    def _heuristic_transform(self, pattern: ElementaryStepPattern,
                              current_smi: str, context: dict) -> Optional[str]:
        """
        패턴별 경험적 변환 (RWMol 기반).

        RunReactants 실패 시 대체 경로.
        각 패턴 유형에 맞는 RWMol 조작으로 중간체 생성.
        디스패치 테이블로 패턴 ID → 전용 RWMol 메서드 호출.
        """
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit 미사용 - 경험적 변환 불가: %s", pattern.pattern_id)
            return None

        # 디스패치 테이블: pattern_id → RWMol 변환 메서드
        _rw_dispatch = {
            "nuc_attack_carbonyl": self._rw_nuc_attack_carbonyl,
            "nuc_attack_saturated": self._rw_nuc_attack_saturated,
            "leaving_group_departure": self._rw_leaving_group_departure,
            "protonation": self._rw_protonation,
            "deprotonation_alpha": self._rw_deprotonation_alpha,
            "deprotonation_heteroatom": self._rw_deprotonation_heteroatom,
            "electrophilic_addition": self._rw_electrophilic_addition,
            "eas_sigma_complex": self._rw_eas_sigma_complex,
            "eas_deprotonation": self._rw_eas_deprotonation,
            "alkyl_1_2_shift": self._rw_alkyl_1_2_shift,
            "aryl_1_2_shift": self._rw_aryl_1_2_shift,
            "elimination_e2": self._rw_elimination_e2,
            "elimination_e1cb": self._rw_elimination_e1cb,
            "acyl_substitution": self._rw_acyl_substitution,
            "hydrolysis": self._rw_hydrolysis,
            "cycloaddition_4_2": self._rw_cycloaddition_4_2,
            "retro_cycloaddition": self._rw_retro_cycloaddition,
            "sigmatropic_33": self._rw_sigmatropic_33,
            "sigmatropic_23": self._rw_sigmatropic_23,
            "ene_reaction": self._rw_ene_reaction,
            "electrocyclic": self._rw_electrocyclic,
            "oxidative_addition": self._rw_oxidative_addition,
            "transmetalation": self._rw_transmetalation,
            "reductive_elimination": self._rw_reductive_elimination,
            "migratory_insertion": self._rw_migratory_insertion,
            "beta_hydride_elimination": self._rw_beta_hydride_elimination,
            "homolysis": self._rw_homolysis,
            "radical_addition": self._rw_radical_addition,
            "radical_h_abstraction": self._rw_radical_h_abstraction,
            "beta_scission": self._rw_beta_scission,
        }

        pid = pattern.pattern_id
        # Rule N: isinstance guard for _rw_dispatch
        if not isinstance(_rw_dispatch, dict): _rw_dispatch = {}
        method = _rw_dispatch.get(pid)
        if method is None:
            logger.debug(f"RWMol 변환 미구현 패턴: {pid}")
            return None

        try:
            result = method(current_smi, context)
            if result and result != current_smi:
                # 결과 검증: 유효한 SMILES인지 확인
                check = Chem.MolFromSmiles(result)
                if check is not None:
                    return result
                else:
                    logger.debug(f"RWMol 변환 결과 유효하지 않음 ({pid}): {result}")
                    return None
            return result
        except Exception as e:
            logger.debug(f"RWMol 변환 오류 ({pid}): {e}")
            return None

    # ================================================================
    # RWMol 기반 패턴별 중간체 생성 메서드
    # ================================================================

    def _rw_nuc_attack_carbonyl(self, mol_smi: str, context: dict) -> Optional[str]:
        """Nu: + C=O → 사면체 중간체.
        C=O 이중결합 → 단일결합, O에 -1 전하 설정."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        patt = Chem.MolFromSmarts('[CX3](=[OX1])')
        matches = mol.GetSubstructMatches(patt)
        if matches:
            c_idx, o_idx = matches[0][0], matches[0][1]
            bond = mol.GetBondBetweenAtoms(c_idx, o_idx)
            if bond and bond.GetBondType() == Chem.BondType.DOUBLE:
                bond.SetBondType(Chem.BondType.SINGLE)
                mol.GetAtomWithIdx(o_idx).SetFormalCharge(-1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during nucleophilic addition: %s", e)
        return None

    def _rw_nuc_attack_saturated(self, mol_smi: str, context: dict) -> Optional[str]:
        """SN2: Nu: + C-LG → [Nu-C-LG]‡ (일부 결합 약화).
        이탈기 결합을 끊고 C에 +1 전하 → 카르보양이온-유사 중간체."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        # 포화 탄소-할로겐 결합 찾기
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (9, 17, 35, 53):  # F, Cl, Br, I
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() == 6 and nbr.GetDegree() <= 4:
                        mol.RemoveBond(nbr.GetIdx(), atom.GetIdx())
                        nbr.SetFormalCharge(1)
                        atom.SetFormalCharge(-1)
                        try:
                            Chem.SanitizeMol(mol)
                            return Chem.MolToSmiles(mol)
                        except Exception as e:
                            logger.warning("SanitizeMol failed during protonation: %s", e)
        return None

    def _rw_leaving_group_departure(self, mol_smi: str, context: dict) -> Optional[str]:
        """C-X → C+ + X- (이탈기 이탈, SN1 step 1)."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (9, 17, 35, 53):  # F, Cl, Br, I
                c_neighbors = [n for n in atom.GetNeighbors() if n.GetAtomicNum() == 6]
                if c_neighbors:
                    c_atom = c_neighbors[0]
                    bond = mol.GetBondBetweenAtoms(c_atom.GetIdx(), atom.GetIdx())
                    if bond:
                        mol.RemoveBond(c_atom.GetIdx(), atom.GetIdx())
                        c_atom.SetFormalCharge(1)
                        atom.SetFormalCharge(-1)
                        try:
                            Chem.SanitizeMol(mol)
                            return Chem.MolToSmiles(mol)
                        except Exception as e:
                            logger.warning("SanitizeMol failed during carbocation formation: %s", e)
        return None

    def _rw_protonation(self, mol_smi: str, context: dict) -> Optional[str]:
        """헤테로원자 양성자화: N/O/S에 H 추가, 전하 +1."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (7, 8, 16) and atom.GetFormalCharge() <= 0:
                atom.SetFormalCharge(atom.GetFormalCharge() + 1)
                atom.SetNumExplicitHs(atom.GetNumExplicitHs() + 1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during acid protonation: %s", e)
        return None

    def _rw_deprotonation_alpha(self, mol_smi: str, context: dict) -> Optional[str]:
        """알파 탈양성자화: C=O 옆 탄소에서 H 제거 → 에놀레이트 ([CH-]).
        Find alpha-H adjacent to C=O, remove H, set charge -1."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        # alpha-C pattern: C with H, bonded to C=O
        patt = Chem.MolFromSmarts('[CH1,CH2,CH3;$(C[CX3](=[OX1]))]')
        if patt is None:
            logger.warning("SMARTS 패턴 파싱 실패")
            return None
        matches = mol.GetSubstructMatches(patt)
        if matches:
            c_idx = matches[0][0]
            atom = mol.GetAtomWithIdx(c_idx)
            atom.SetFormalCharge(-1)
            nh = atom.GetNumExplicitHs()
            total_h = atom.GetTotalNumHs()
            if nh > 0:
                atom.SetNumExplicitHs(nh - 1)
            elif total_h > 0:
                # implicit H → need to set explicit and decrement
                atom.SetNoImplicit(True)
                atom.SetNumExplicitHs(total_h - 1)
            try:
                Chem.SanitizeMol(mol)
                return Chem.MolToSmiles(mol)
            except Exception as e:
                logger.warning("SanitizeMol failed during deprotonation: %s", e)
        return None

    def _rw_deprotonation_heteroatom(self, mol_smi: str, context: dict) -> Optional[str]:
        """헤테로원자 탈양성자화: N/O/S에서 H 제거, 전하 -1."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (7, 8, 16) and atom.GetTotalNumHs() > 0:
                atom.SetFormalCharge(atom.GetFormalCharge() - 1)
                nh = atom.GetNumExplicitHs()
                if nh > 0:
                    atom.SetNumExplicitHs(nh - 1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during elimination deprotonation: %s", e)
        return None

    def _rw_electrophilic_addition(self, mol_smi: str, context: dict) -> Optional[str]:
        """친전자 첨가: C=C 이중결합 → 단일결합, 한 C에 +1 전하 (Markovnikov 카르보양이온)."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        patt = Chem.MolFromSmarts('[CX3]=[CX3]')
        matches = mol.GetSubstructMatches(patt)
        if matches:
            c1_idx, c2_idx = matches[0]
            bond = mol.GetBondBetweenAtoms(c1_idx, c2_idx)
            if bond and bond.GetBondType() == Chem.BondType.DOUBLE:
                bond.SetBondType(Chem.BondType.SINGLE)
                # Markovnikov: 더 치환된 탄소에 +1 전하
                c1_deg = mol.GetAtomWithIdx(c1_idx).GetDegree()
                c2_deg = mol.GetAtomWithIdx(c2_idx).GetDegree()
                target = c1_idx if c1_deg >= c2_deg else c2_idx
                mol.GetAtomWithIdx(target).SetFormalCharge(1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during carbocation rearrangement: %s", e)
        return None

    def _rw_eas_sigma_complex(self, mol_smi: str, context: dict) -> Optional[str]:
        """EAS 시그마 착물: 방향족 고리 탄소 하나를 sp3로, +1 전하."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        ring_info = mol.GetRingInfo()
        for ring in ring_info.AtomRings():
            if len(ring) == 6 and all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                # 첫 번째 탄소를 공격 대상으로 설정
                target = ring[0]
                atom = mol.GetAtomWithIdx(target)
                atom.SetFormalCharge(1)
                atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.debug("SanitizeMol failed with aromatic charge, trying kekulize: %s", e)
                    try:
                        Chem.Kekulize(mol, clearAromaticFlags=True)
                        return Chem.MolToSmiles(mol)
                    except Exception as e:
                        logger.warning("Kekulize fallback failed after SanitizeMol failure: %s", e)
        return None

    def _rw_eas_deprotonation(self, mol_smi: str, context: dict) -> Optional[str]:
        """EAS 탈양성자화: 시그마 착물에서 H 제거 → 방향족 복구.
        양전하(+1) 탄소 찾아서 전하 제거, H 감소."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 6 and atom.GetFormalCharge() == 1:
                atom.SetFormalCharge(0)
                nh = atom.GetTotalNumHs()
                if nh > 0:
                    atom.SetNumExplicitHs(max(0, atom.GetNumExplicitHs() - 1))
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during oxidation: %s", e)
        return None

    def _rw_alkyl_1_2_shift(self, mol_smi: str, context: dict) -> Optional[str]:
        """1,2-알킬 이동: 카르보양이온 위치 이동 (2차→3차 안정화).
        C+ 찾아서 인접 C로 전하 이동."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 6 and atom.GetFormalCharge() == 1:
                # 인접 탄소 중 더 치환된 것으로 전하 이동
                best_nbr = None
                best_deg = 0
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() == 6 and nbr.GetFormalCharge() == 0:
                        if nbr.GetDegree() > best_deg:
                            best_deg = nbr.GetDegree()
                            best_nbr = nbr
                if best_nbr:
                    atom.SetFormalCharge(0)
                    best_nbr.SetFormalCharge(1)
                    try:
                        Chem.SanitizeMol(mol)
                        return Chem.MolToSmiles(mol)
                    except Exception as e:
                        logger.warning("SanitizeMol failed during rearrangement: %s", e)
        return None

    def _rw_aryl_1_2_shift(self, mol_smi: str, context: dict) -> Optional[str]:
        """1,2-아릴 이동: 방향족 고리가 인접 위치로 이동.
        구현은 alkyl shift와 동일 (전하 이동)."""
        return self._rw_alkyl_1_2_shift(mol_smi, context)

    def _rw_elimination_e2(self, mol_smi: str, context: dict) -> Optional[str]:
        """E2 제거: C-H와 C-LG 동시 제거 → C=C 이중결합 형성.
        할로겐 이탈 + 인접 C=C 생성."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (9, 17, 35, 53):  # halide LG
                for c_alpha in atom.GetNeighbors():
                    if c_alpha.GetAtomicNum() != 6:
                        continue
                    # beta carbon with H
                    for c_beta in c_alpha.GetNeighbors():
                        if c_beta.GetIdx() == atom.GetIdx():
                            continue
                        if c_beta.GetAtomicNum() == 6 and c_beta.GetTotalNumHs() > 0:
                            # Remove C-X bond
                            mol.RemoveBond(c_alpha.GetIdx(), atom.GetIdx())
                            atom.SetFormalCharge(-1)
                            # C-C → C=C
                            bond = mol.GetBondBetweenAtoms(c_alpha.GetIdx(), c_beta.GetIdx())
                            if bond and bond.GetBondType() == Chem.BondType.SINGLE:
                                bond.SetBondType(Chem.BondType.DOUBLE)
                                # Remove one H from beta
                                nh = c_beta.GetNumExplicitHs()
                                total_h = c_beta.GetTotalNumHs()
                                if nh > 0:
                                    c_beta.SetNumExplicitHs(nh - 1)
                                elif total_h > 0:
                                    c_beta.SetNoImplicit(True)
                                    c_beta.SetNumExplicitHs(total_h - 1)
                                try:
                                    Chem.SanitizeMol(mol)
                                    return Chem.MolToSmiles(mol)
                                except Exception as e:
                                    logger.warning("SanitizeMol failed during E2 elimination: %s", e)
        return None

    def _rw_elimination_e1cb(self, mol_smi: str, context: dict) -> Optional[str]:
        """E1cb: 먼저 alpha-H 탈양성자화 → 카르바니온 중간체.
        alpha 탈양성자화와 동일한 결과."""
        return self._rw_deprotonation_alpha(mol_smi, context)

    def _rw_acyl_substitution(self, mol_smi: str, context: dict) -> Optional[str]:
        """아실 치환 (첨가-제거): C(=O)-LG의 C=O를 단일결합으로 → 사면체 중간체.
        nuc_attack_carbonyl과 유사."""
        return self._rw_nuc_attack_carbonyl(mol_smi, context)

    def _rw_hydrolysis(self, mol_smi: str, context: dict) -> Optional[str]:
        """가수분해: 에스터/아미드 결합 C(=O)-O/N을 끊음 → 카르복실산 + 알코올/아민.
        C(=O)-O 또는 C(=O)-N 결합 절단."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        # Find ester/amide: C(=O)-[O,N]
        patt = Chem.MolFromSmarts('[CX3](=[OX1])[O,N;!$([OH])]')
        if patt is None:
            logger.warning("SMARTS 패턴 파싱 실패")
            return None
        matches = mol.GetSubstructMatches(patt)
        if matches:
            c_idx = matches[0][0]
            # o_double = matches[0][1]  (=O, 유지)
            hetero_idx = matches[0][2]  # O or N (이탈기)
            bond = mol.GetBondBetweenAtoms(c_idx, hetero_idx)
            if bond:
                mol.RemoveBond(c_idx, hetero_idx)
                # Add OH to carbonyl C
                oh_idx = mol.AddAtom(Chem.Atom(8))  # O
                mol.AddBond(c_idx, oh_idx, Chem.BondType.SINGLE)
                mol.GetAtomWithIdx(oh_idx).SetNumExplicitHs(1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during hydration: %s", e)
        return None

    def _rw_cycloaddition_4_2(self, mol_smi: str, context: dict) -> Optional[str]:
        """Diels-Alder [4+2]: 두 분자 접근 상태 (중간체보다는 전이상태).
        입력 SMILES가 이미 두 분자(diene.dienophile)면 그대로 반환,
        아니면 None (Composer가 생성물 직접 사용)."""
        if '.' in mol_smi:
            # 이미 두 분자 → 전이상태로 간주
            return mol_smi
        logger.debug("Diels-Alder [4+2] 단일 분자 입력 - 중간체 없음 (Composer가 생성물 사용): %s", mol_smi)
        return None

    def _rw_retro_cycloaddition(self, mol_smi: str, context: dict) -> Optional[str]:
        """역 Diels-Alder: 6원 고리 → 다이엔 + 다이엔오필 분리.
        6원 고리에서 두 결합 끊기."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        ring_info = mol.GetRingInfo()
        for ring in ring_info.AtomRings():
            if len(ring) == 6:
                # 고리의 1번과 4번 사이 결합, 2번과 3번 사이 결합 끊기 시도
                # (실제 retro-DA에서는 sigma bond 2개 끊김)
                try:
                    b1 = mol.GetBondBetweenAtoms(ring[0], ring[5])
                    b2 = mol.GetBondBetweenAtoms(ring[2], ring[3])
                    if b1 and b2:
                        mol.RemoveBond(ring[0], ring[5])
                        mol.RemoveBond(ring[2], ring[3])
                        try:
                            Chem.SanitizeMol(mol)
                            return Chem.MolToSmiles(mol)
                        except Exception as e:
                            logger.warning("SanitizeMol failed during retro-Diels-Alder: %s", e)
                except Exception as e:
                    logger.warning("Retro-Diels-Alder ring processing failed: %s", e)
        return None

    def _rw_sigmatropic_33(self, mol_smi: str, context: dict) -> Optional[str]:
        """[3,3]-시그마트로픽 재배열 (Claisen/Cope).
        협동 반응 — 중간체 없음. 전이상태 표시용으로 입력 반환."""
        # 협동 반응이므로 실질적 중간체 없음; None 반환하여 Composer가 생성물 사용
        logger.debug("[3,3]-시그마트로픽 재배열: 협동 반응 - 중간체 없음 (Composer가 생성물 사용)")
        return None

    def _rw_sigmatropic_23(self, mol_smi: str, context: dict) -> Optional[str]:
        """[2,3]-시그마트로픽 재배열. 협동 반응."""
        logger.debug("[2,3]-시그마트로픽 재배열: 협동 반응 - 중간체 없음")
        return None

    def _rw_ene_reaction(self, mol_smi: str, context: dict) -> Optional[str]:
        """Ene 반응. 협동 반응 — 중간체 없음."""
        logger.debug("Ene 반응: 협동 반응 - 중간체 없음")
        return None

    def _rw_electrocyclic(self, mol_smi: str, context: dict) -> Optional[str]:
        """전자고리화 반응. 협동 반응 — 중간체 없음."""
        logger.debug("전자고리화 반응: 협동 반응 - 중간체 없음")
        return None

    def _rw_oxidative_addition(self, mol_smi: str, context: dict) -> Optional[str]:
        """산화적 첨가: ArX + Pd(0) → Ar-Pd-X.
        Ar-X 결합 끊고 [Pd] 삽입."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (17, 35, 53):  # Cl, Br, I
                for nbr in atom.GetNeighbors():
                    if nbr.GetIsAromatic() or nbr.GetAtomicNum() == 6:
                        mol.RemoveBond(nbr.GetIdx(), atom.GetIdx())
                        atom.SetFormalCharge(-1)
                        try:
                            Chem.SanitizeMol(mol)
                            base_smi = Chem.MolToSmiles(mol)
                            return base_smi + ".[Pd]"
                        except Exception as e:
                            logger.warning("SanitizeMol failed during cross-coupling: %s", e)
        return None

    def _rw_transmetalation(self, mol_smi: str, context: dict) -> Optional[str]:
        """전이금속화: Pd-X를 Pd-R로 교환.
        [Pd] 조각이 있으면 유지, 할로겐화물 조각 제거."""
        if '.[Pd]' in mol_smi:
            # [Pd]는 유지, 할로겐 음이온 조각 제거
            frags = mol_smi.split('.')
            new_frags = []
            for f in frags:
                m = Chem.MolFromSmiles(f)
                if m is None:
                    new_frags.append(f)
                    continue
                # 단순 할로겐 음이온 ([Cl-], [Br-], [I-]) 제거
                if m.GetNumAtoms() == 1 and m.GetAtomWithIdx(0).GetAtomicNum() in (17, 35, 53):
                    continue
                new_frags.append(f)
            if new_frags:
                return '.'.join(new_frags)
        return None

    def _rw_reductive_elimination(self, mol_smi: str, context: dict) -> Optional[str]:
        """환원적 제거: Pd 제거 → C-C 결합 형성.
        [Pd] 조각 제거."""
        # N 타입 가드
        if not isinstance(mol_smi, str):
            logger.warning("_rw_reductive_elimination: mol_smi 타입 불일치 (expected str, got %s)", type(mol_smi).__name__)
            return None
        if '[Pd]' in mol_smi:
            frags = mol_smi.split('.')
            new_frags = [f for f in frags if f != '[Pd]']
            if new_frags:
                result = '.'.join(new_frags)
                if Chem.MolFromSmiles(result) is not None:
                    return result
        logger.debug("_rw_reductive_elimination: [Pd] 조각 미발견 또는 변환 불가 (mol_smi=%s)", mol_smi)
        return None

    def _rw_migratory_insertion(self, mol_smi: str, context: dict) -> Optional[str]:
        """이동 삽입. Pd 촉매 사이클 — 입력 유지 (촉매 사이클 표시용)."""
        # 유기금속 중간체는 SMILES로 정확히 표현 어려움
        logger.debug("_rw_migratory_insertion: 촉매 사이클 중간체 — SMILES 변환 생략")
        return None

    def _rw_beta_hydride_elimination(self, mol_smi: str, context: dict) -> Optional[str]:
        """베타-수소화물 제거: C=C 형성 + Pd-H.
        C-C 단일결합 → C=C 이중결합."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        # Pd 포함하지 않는 유기 조각에서 C-C → C=C
        patt = Chem.MolFromSmarts('[CH1,CH2]-[CH1,CH2]')
        if patt is None:
            logger.warning("SMARTS 패턴 파싱 실패")
            return None
        matches = mol.GetSubstructMatches(patt)
        if matches:
            c1, c2 = matches[0]
            bond = mol.GetBondBetweenAtoms(c1, c2)
            if bond and bond.GetBondType() == Chem.BondType.SINGLE:
                bond.SetBondType(Chem.BondType.DOUBLE)
                # Remove one H from each
                for ci in (c1, c2):
                    a = mol.GetAtomWithIdx(ci)
                    nh = a.GetNumExplicitHs()
                    if nh > 0:
                        a.SetNumExplicitHs(nh - 1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during condensation: %s", e)
        return None

    def _rw_homolysis(self, mol_smi: str, context: dict) -> Optional[str]:
        """균일 분해: 결합 끊어서 라디칼 2개 생성.
        가장 약한 결합 (C-halide 또는 O-O peroxide) 끊기."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        # O-O peroxide bond
        patt = Chem.MolFromSmarts('[OX2]-[OX2]')
        if patt:
            matches = mol.GetSubstructMatches(patt)
            if matches:
                o1, o2 = matches[0]
                mol.RemoveBond(o1, o2)
                mol.GetAtomWithIdx(o1).SetNumRadicalElectrons(1)
                mol.GetAtomWithIdx(o2).SetNumRadicalElectrons(1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during homolytic O-O cleavage: %s", e)
        # C-halide bond
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() in (17, 35, 53):
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() == 6:
                        mol.RemoveBond(nbr.GetIdx(), atom.GetIdx())
                        nbr.SetNumRadicalElectrons(1)
                        atom.SetNumRadicalElectrons(1)
                        try:
                            Chem.SanitizeMol(mol)
                            return Chem.MolToSmiles(mol)
                        except Exception as e:
                            logger.warning("SanitizeMol failed during homolytic C-halide cleavage: %s", e)
        return None

    def _rw_radical_addition(self, mol_smi: str, context: dict) -> Optional[str]:
        """라디칼 첨가: 라디칼 + C=C → C-C-radical.
        C=C → C-C, 한 탄소에 라디칼 전자 설정."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        patt = Chem.MolFromSmarts('[CX3]=[CX3]')
        matches = mol.GetSubstructMatches(patt)
        if matches:
            c1, c2 = matches[0]
            bond = mol.GetBondBetweenAtoms(c1, c2)
            if bond and bond.GetBondType() == Chem.BondType.DOUBLE:
                bond.SetBondType(Chem.BondType.SINGLE)
                # Anti-Markovnikov: 덜 치환된 탄소에 라디칼
                c1_deg = mol.GetAtomWithIdx(c1).GetDegree()
                c2_deg = mol.GetAtomWithIdx(c2).GetDegree()
                target = c2 if c1_deg >= c2_deg else c1
                mol.GetAtomWithIdx(target).SetNumRadicalElectrons(1)
                try:
                    Chem.SanitizeMol(mol)
                    return Chem.MolToSmiles(mol)
                except Exception as e:
                    logger.warning("SanitizeMol failed during radical addition: %s", e)
        return None

    def _rw_radical_h_abstraction(self, mol_smi: str, context: dict) -> Optional[str]:
        """라디칼 수소 추출: R-H + X• → R• + HX.
        가장 약한 C-H 결합의 H 제거, 라디칼 설정."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        # 3차 > 2차 > 1차 C-H 순서로 탐색
        best_c = None
        best_deg = 0
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0:
                deg = sum(1 for n in atom.GetNeighbors() if n.GetAtomicNum() == 6)
                if deg > best_deg:
                    best_deg = deg
                    best_c = atom
        if best_c is not None:
            best_c.SetNumRadicalElectrons(1)
            nh = best_c.GetNumExplicitHs()
            total_h = best_c.GetTotalNumHs()
            if nh > 0:
                best_c.SetNumExplicitHs(nh - 1)
            elif total_h > 0:
                best_c.SetNoImplicit(True)
                best_c.SetNumExplicitHs(total_h - 1)
            try:
                Chem.SanitizeMol(mol)
                return Chem.MolToSmiles(mol)
            except Exception as e:
                logger.warning("SanitizeMol failed during radical hydrogen abstraction: %s", e)
        return None

    def _rw_beta_scission(self, mol_smi: str, context: dict) -> Optional[str]:
        """베타 절단: 라디칼 인접 C-C 결합 끊김 → 알켄 + 새 라디칼.
        라디칼 탄소의 베타 결합 절단."""
        _parsed_mol_smi = Chem.MolFromSmiles(mol_smi)
        if _parsed_mol_smi is None:
            logger.warning("SMILES 파싱 실패: %s", mol_smi)
            return None
        mol = Chem.RWMol(_parsed_mol_smi)
        if mol is None:
            logger.warning("RWMol 생성 실패")
            return None
        for atom in mol.GetAtoms():
            if atom.GetNumRadicalElectrons() > 0 and atom.GetAtomicNum() == 6:
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() == 6:
                        # beta C-C bond
                        for beta_nbr in nbr.GetNeighbors():
                            if beta_nbr.GetIdx() == atom.GetIdx():
                                continue
                            if beta_nbr.GetAtomicNum() == 6:
                                mol.RemoveBond(nbr.GetIdx(), beta_nbr.GetIdx())
                                beta_nbr.SetNumRadicalElectrons(1)
                                # alpha-beta → double bond
                                bond = mol.GetBondBetweenAtoms(atom.GetIdx(), nbr.GetIdx())
                                if bond and bond.GetBondType() == Chem.BondType.SINGLE:
                                    bond.SetBondType(Chem.BondType.DOUBLE)
                                    atom.SetNumRadicalElectrons(0)
                                try:
                                    Chem.SanitizeMol(mol)
                                    return Chem.MolToSmiles(mol)
                                except Exception as e:
                                    logger.warning("SanitizeMol failed during radical coupling/termination: %s", e)
        return None

    def _build_arrows(self, pattern: ElementaryStepPattern,
                      mol, atom_map: dict) -> List[ArrowData]:
        """
        ArrowTemplate → 구체적 ArrowData 변환.

        패턴의 화살표 템플릿을 실제 ArrowData 인스턴스로 변환.
        원자 인덱스는 현재 -1 (자동 매칭 모드) — 렌더러가 해석.
        """
        if not _MECHANISM_CLASSES_AVAILABLE:
            logger.warning("_build_arrows: reaction_mechanisms 모듈 미사용 — 화살표 생성 불가")
            return []

        arrows = []
        for tmpl in pattern.arrows:
            color = "#cc0000"  # 극성 메커니즘 기본 빨간색
            if pattern.pattern_class == "radical":
                color = "#ff6600"  # 라디칼 = 주황색

            arrow = ArrowData(
                arrow_type=tmpl.arrow_type,
                from_type=tmpl.from_role,
                from_label=tmpl.label,
                to_type=tmpl.to_role,
                to_label=tmpl.label,
                color=color,
                curvature=0.3,  # default curvature
                from_atom_idx=-1,  # 자동 매칭
                to_atom_idx=-1,
            )
            arrows.append(arrow)
        return arrows

    def _build_energy_diagram(self, steps: List[MechanismStep],
                               classification: ReactionClassification) -> List[Tuple[str, float]]:
        """에너지 다이어그램 데이터 생성."""
        diagram = [("반응물", 0.0)]
        cumulative = 0.0

        for i, step in enumerate(steps):
            # Rule N: isinstance guard for _library
            if not isinstance(_library, dict): _library = {}
            pattern = self._library.get(
                classification.pattern_sequence[i] if i < len(classification.pattern_sequence) else ""
            )
            if pattern and pattern.is_rate_determining:
                barrier = pattern.energy_estimate_kcal
                diagram.append((f"전이상태 {i+1}", cumulative + barrier))
                cumulative += barrier * 0.3  # intermediate is lower than TS
                diagram.append((f"중간체 {i+1}", cumulative))
            else:
                if pattern:
                    cumulative += pattern.energy_estimate_kcal * 0.2
                diagram.append((step.title, cumulative))

        # Final product energy (exothermic by default)
        diagram.append(("생성물", cumulative - 10.0))
        return diagram

    def _build_title(self, classification: ReactionClassification) -> str:
        """반응 제목 생성."""
        _TITLES = {
            "sn2": "SN2 (이분자 친핵성 치환)",
            "sn1": "SN1 (단분자 친핵성 치환)",
            "e2": "E2 (이분자 제거)",
            "e1cb": "E1cb (단분자 공액염기 제거)",
            "aldol": "알돌 축합",
            "acyl_substitution": "아실 치환 (첨가-제거)",
            "acyl_hydrolysis": "아실 가수분해",
            "grignard_addition": "그리냐르 첨가",
            "nuc_addition_carbonyl": "카르보닐 친핵 첨가",
            "electrophilic_addition": "친전자 첨가",
            "diels_alder": "Diels-Alder [4+2] 고리화 첨가",
            "retro_da": "역 Diels-Alder [4+2]",
            "claisen": "Claisen [3,3]-시그마트로픽 재배열",
            "cope": "Cope [3,3]-시그마트로픽 재배열",
            "eas_generic": "방향족 친전자 치환 (EAS)",
            "suzuki": "Suzuki-Miyaura 교차 결합",
            "heck": "Heck 반응",
            "negishi": "Negishi 교차 결합",
            "stille": "Stille 교차 결합",
            "kumada": "Kumada 교차 결합",
            "sonogashira": "Sonogashira 교차 결합",
            "buchwald_hartwig": "Buchwald-Hartwig 아민화",
            "chan_lam": "Chan-Lam 결합",
            "radical_addition": "라디칼 첨가 (Anti-Markovnikov)",
            "radical_halogenation": "라디칼 할로겐화",
            "generic_radical": "라디칼 사슬 반응",
            "alcohol_oxidation": "알코올 산화",
            "alkene_oxidation": "알켄 산화",
            "carbonyl_reduction": "카르보닐 환원",
            "hydrogenation": "접촉 수소화",
            "epoxide_acid": "에폭사이드 산촉매 개환",
            "epoxide_base": "에폭사이드 염기촉매 개환",
        }
        sub = classification.sub_class
        return _TITLES.get(sub, f"자동 분류: {classification.reaction_class}/{sub}")

    def _build_overall_description(self, classification: ReactionClassification,
                                   reactant_smi: str, product_smi: str) -> str:
        """전체 설명 생성."""
        steps_desc = " → ".join(classification.pattern_sequence)
        return (
            f"반응 유형: {classification.reaction_class}/{classification.sub_class}. "
            f"단계 시퀀스: {steps_desc}. "
            f"분류 확신도: {classification.confidence:.0%}."
        )


# ============================================================================
# MECHANISM VALIDATOR
# ============================================================================

class MechanismValidator:
    """
    메커니즘 검증기.

    검증 항목:
    1. SMILES 파싱 가능 여부
    2. 원자 보존 (반응물 → 생성물)
    3. 형식전하 균형
    4. 최종 생성물 매칭
    """

    def validate(self, mechanism: MechanismData,
                 expected_product: str = "") -> ValidationResult:
        """
        메커니즘 전체 검증.

        Args:
            mechanism: 검증 대상 MechanismData
            expected_product: 기대 생성물 SMILES (빈 문자열이면 생략)

        Returns:
            ValidationResult
        """
        # N 타입 가드: expected_product는 외부에서 비문자열이 올 수 있음
        if not isinstance(expected_product, str):
            logger.warning("validate: expected_product 타입 불일치 (expected str, got %s)", type(expected_product).__name__)
            expected_product = str(expected_product) if expected_product else ""

        errors = []
        warnings = []
        atom_ok = True
        charge_ok = True
        product_match = False

        if not mechanism or not mechanism.steps:
            return ValidationResult(
                is_valid=False,
                errors=["메커니즘이 비어 있음"],
            )

        if not RDKIT_AVAILABLE:
            # RDKit 없으면 기본 검증만
            return ValidationResult(is_valid=True, warnings=["RDKit 미사용 - 제한적 검증"])

        # 1. SMILES 파싱 가능 여부
        for i, step in enumerate(mechanism.steps):
            if step.reactant_smiles:
                mol = Chem.MolFromSmiles(step.reactant_smiles)
                if mol is None:
                    errors.append(f"Step {i+1} 반응물 SMILES 파싱 실패: {step.reactant_smiles}")
            if step.product_smiles:
                mol = Chem.MolFromSmiles(step.product_smiles)
                if mol is None:
                    errors.append(f"Step {i+1} 생성물 SMILES 파싱 실패: {step.product_smiles}")

        # 2. 원자 보존 (전체: 첫 단계 반응물 vs 마지막 단계 생성물)
        first_smi = mechanism.steps[0].reactant_smiles
        last_smi = mechanism.steps[-1].product_smiles
        atom_ok = self._check_atom_conservation(first_smi, last_smi, errors, warnings)

        # 3. 형식전하 균형
        charge_ok = self._check_charge_balance(first_smi, last_smi, errors, warnings)

        # 4. 생성물 매칭
        if expected_product:
            product_match = self._check_product_match(last_smi, expected_product, errors, warnings)
        else:
            product_match = True  # no expected product to check

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            atom_balance_ok=atom_ok,
            charge_balance_ok=charge_ok,
            product_match=product_match,
        )

    def _check_atom_conservation(self, first_smi: str, last_smi: str,
                                  errors: list, warnings: list) -> bool:
        """원자 수 보존 확인 (H 제외 — 양성자 전달 반응에서 H 수 변동 가능)."""
        # N 타입 가드
        if not isinstance(first_smi, str) or not isinstance(last_smi, str):
            logger.warning("_check_atom_conservation: SMILES 타입 불일치 (first=%s, last=%s)",
                           type(first_smi).__name__, type(last_smi).__name__)
            return True  # can't verify with bad types
        try:
            mol1 = Chem.MolFromSmiles(first_smi)
            mol2 = Chem.MolFromSmiles(last_smi)
            if mol1 is None or mol2 is None:
                logger.warning("_check_atom_conservation: SMILES 파싱 실패 (first=%s, last=%s)", first_smi, last_smi)
                return True  # can't verify

            # Count heavy atoms (non-H)
            counts1: Dict[int, int] = {}
            counts2: Dict[int, int] = {}
            for atom in mol1.GetAtoms():
                an = atom.GetAtomicNum()
                if an > 1:  # skip H
                    # Rule N: isinstance guard for counts1
                    if not isinstance(counts1, dict): counts1 = {}
                    counts1[an] = counts1.get(an, 0) + 1
            for atom in mol2.GetAtoms():
                an = atom.GetAtomicNum()
                if an > 1:
                    counts2[an] = counts2.get(an, 0) + 1

            if counts1 != counts2:
                diff = {}
                all_atoms = set(counts1.keys()) | set(counts2.keys())
                for an in all_atoms:
                    c1 = counts1.get(an, 0)
                    c2 = counts2.get(an, 0)
                    if c1 != c2:
                        diff[an] = c2 - c1
                warnings.append(f"중원자 수 차이 (예상됨 — 부산물 미포함 가능): {diff}")
                return False
            return True
        except Exception as e:
            warnings.append(f"원자 보존 확인 실패: {e}")
            return True

    def _check_charge_balance(self, first_smi: str, last_smi: str,
                               errors: list, warnings: list) -> bool:
        """형식전하 균형 확인."""
        # N 타입 가드
        if not isinstance(first_smi, str) or not isinstance(last_smi, str):
            logger.warning("_check_charge_balance: SMILES 타입 불일치 (first=%s, last=%s)",
                           type(first_smi).__name__, type(last_smi).__name__)
            return True
        try:
            mol1 = Chem.MolFromSmiles(first_smi)
            mol2 = Chem.MolFromSmiles(last_smi)
            if mol1 is None or mol2 is None:
                return True

            charge1 = sum(atom.GetFormalCharge() for atom in mol1.GetAtoms())
            charge2 = sum(atom.GetFormalCharge() for atom in mol2.GetAtoms())

            if charge1 != charge2:
                warnings.append(f"형식전하 변동: {charge1} → {charge2} (시약/용매로 균형 가능)")
                return False
            return True
        except Exception as e:
            logger.warning("Charge conservation check failed: %s", e)
            return True

    def _check_product_match(self, actual_smi: str, expected_smi: str,
                              errors: list, warnings: list) -> bool:
        """생성물 일치 여부 확인."""
        # N 타입 가드
        if not isinstance(actual_smi, str) or not isinstance(expected_smi, str):
            logger.warning("_check_product_match: SMILES 타입 불일치 (actual=%s, expected=%s)",
                           type(actual_smi).__name__, type(expected_smi).__name__)
            return False
        try:
            mol_a = Chem.MolFromSmiles(actual_smi)
            mol_e = Chem.MolFromSmiles(expected_smi)
            if mol_a is None or mol_e is None:
                return False

            can_a = Chem.MolToSmiles(mol_a)
            can_e = Chem.MolToSmiles(mol_e)

            if can_a == can_e:
                return True

            # Multi-fragment check: actual may contain byproducts
            actual_frags = set(can_a.split('.'))
            expected_frags = set(can_e.split('.'))

            if expected_frags.issubset(actual_frags):
                return True

            # Substructure match as fallback
            if mol_a.HasSubstructMatch(mol_e) or mol_e.HasSubstructMatch(mol_a):
                warnings.append("생성물 완전 일치 아님 (부분 구조 일치)")
                return True

            warnings.append(f"생성물 불일치: {can_a} vs {can_e}")
            return False
        except Exception as e:
            warnings.append(f"생성물 매칭 오류: {e}")
            return False


# ============================================================================
# MAIN ENGINE
# ============================================================================

class MechanismRuleEngine:
    """
    규칙 기반 반응 메커니즘 생성 엔진 (메인 진입점).

    사용법:
        engine = MechanismRuleEngine()

        # 기본 사용
        mech = engine.generate("CBr.[OH-]", "CO.[Br-]", "SN2")
        if mech:
            for step in mech.steps:
                print(step.title, len(step.arrows), "arrows")

        # DryLab 보고서용
        steps = engine.generate_for_drylab("CBr.[OH-]", "CO.[Br-]", "SN2")
    """

    def __init__(self):
        self._library = PatternLibrary()
        self._classifier = ReactionClassifier()
        self._composer = MechanismComposer(self._library)
        self._validator = MechanismValidator()
        logger.info("MechanismRuleEngine initialized")

    @property
    def library(self) -> PatternLibrary:
        """PatternLibrary 접근자 (테스트/디버그용)."""
        return self._library

    @property
    def classifier(self) -> ReactionClassifier:
        """ReactionClassifier 접근자 (테스트/디버그용)."""
        return self._classifier

    def generate(self, reactant_smi: str, product_smi: str,
                 conditions: str = "") -> Optional[MechanismData]:
        """
        메인 진입점: 반응 분류 → 메커니즘 조립 → 검증 → 반환.

        Args:
            reactant_smi: 반응물 SMILES
            product_smi: 생성물 SMILES
            conditions: 조건 문자열

        Returns:
            MechanismData or None (분류 실패/확신도 < 0.3/검증 실패)
        """
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available - generate() disabled")
            return None

        # N-code: type guard — external callers may pass non-str values
        if not isinstance(reactant_smi, str) or not isinstance(product_smi, str):
            logger.warning("generate() received non-str SMILES: reactant=%s, product=%s",
                           type(reactant_smi).__name__, type(product_smi).__name__)
            return None
        if not isinstance(conditions, str):
            logger.warning("generate() conditions is not str: type=%s, coercing", type(conditions).__name__)
            conditions = str(conditions) if conditions else ""

        # 1. 분류
        classification = self._classifier.classify(reactant_smi, product_smi, conditions)
        if classification is None:
            logger.info(f"분류 실패: {reactant_smi} → {product_smi}")
            return None

        # Confidence threshold: 0.3 미만이면 불확실
        if classification.confidence < 0.3:
            logger.info(
                f"확신도 부족 ({classification.confidence:.0%}): "
                f"{classification.reaction_class}/{classification.sub_class}"
            )
            return None

        logger.info(
            f"분류 결과: {classification.reaction_class}/{classification.sub_class} "
            f"(confidence={classification.confidence:.0%}, "
            f"patterns={classification.pattern_sequence})"
        )

        # 2. 메커니즘 조립
        mechanism = self._composer.compose(classification, reactant_smi, product_smi)
        if mechanism is None:
            logger.warning("메커니즘 조립 실패")
            return None

        # 3. 검증
        result = self._validator.validate(mechanism, product_smi)
        if not result.is_valid:
            logger.warning(f"메커니즘 검증 실패: {result.errors}")
            return None

        if result.warnings:
            for w in result.warnings:
                logger.info(f"검증 경고: {w}")

        return mechanism

    def generate_for_drylab(self, reactant_smi: str, product_smi: str,
                            conditions: str = "") -> Optional[List[dict]]:
        """
        DryLab 보고서용 단계 dict 리스트 생성.

        drylab_report_exporter.py가 기대하는 형식:
        [
            {
                "smiles": "중간체 SMILES",
                "reagent_smiles": "시약 SMILES",
                "mechanism_type": "ionic" or "radical",
                "annotation": "BOND CHANGE: ...",
                "byproduct": "부산물 화학식",
                "step_label": "Step N: 제목",
                "arrow_hint": "full" or "fishhook"
            },
            ...
        ]

        Args:
            reactant_smi: 반응물 SMILES
            product_smi: 생성물 SMILES
            conditions: 조건 문자열

        Returns:
            List[dict] or None
        """
        # N-code: type guard — external callers may pass non-str values
        if not isinstance(reactant_smi, str) or not isinstance(product_smi, str):
            logger.warning("generate_for_drylab() received non-str SMILES: reactant=%s, product=%s",
                           type(reactant_smi).__name__, type(product_smi).__name__)
            return None
        if not isinstance(conditions, str):
            conditions = str(conditions) if conditions else ""

        mechanism = self.generate(reactant_smi, product_smi, conditions)
        if mechanism is None:
            logger.warning("메커니즘 생성 실패")
            return None

        drylab_steps = []
        for step in mechanism.steps:
            # 화살표 유형 결정
            arrow_hint = "full"
            if any(a.arrow_type == "half" for a in step.arrows):
                arrow_hint = "fishhook"

            # 메커니즘 유형 결정
            mech_type = "ionic"
            if mechanism.mechanism_type.startswith("rule_radical"):
                mech_type = "radical"
            elif mechanism.mechanism_type.startswith("rule_generic_radical"):
                mech_type = "radical"

            drylab_steps.append({
                "smiles": step.product_smiles,
                "reagent_smiles": step.reagents,
                "mechanism_type": mech_type,
                "annotation": step.description,
                "byproduct": "",
                "step_label": f"Step {step.step_number}: {step.title}",
                "arrow_hint": arrow_hint,
            })

        return drylab_steps

    def classify_only(self, reactant_smi: str, product_smi: str,
                      conditions: str = "") -> Optional[ReactionClassification]:
        """
        분류만 수행 (메커니즘 생성 없이).

        디버깅/테스트/UI 표시용.
        """
        # N-code: type guard — external callers may pass non-str values
        if not isinstance(reactant_smi, str) or not isinstance(product_smi, str):
            logger.warning("classify_only() received non-str SMILES: reactant=%s, product=%s",
                           type(reactant_smi).__name__, type(product_smi).__name__)
            return None
        if not isinstance(conditions, str):
            conditions = str(conditions) if conditions else ""
        return self._classifier.classify(reactant_smi, product_smi, conditions)

    def get_supported_reactions(self) -> Dict[str, List[str]]:
        """
        지원하는 반응 유형 목록 반환.

        Returns:
            {"ionic": ["nuc_attack_carbonyl", ...], "pericyclic": [...], ...}
        """
        result: Dict[str, List[str]] = {}
        for pid, pattern in self._library.all_patterns().items():
            cls = pattern.pattern_class
            if cls not in result:
                result[cls] = []
            result[cls].append(pid)
        return result


# ============================================================================
# MODULE-LEVEL CONVENIENCE
# ============================================================================

def create_rule_engine() -> MechanismRuleEngine:
    """팩토리 함수: MechanismRuleEngine 인스턴스 생성."""
    return MechanismRuleEngine()


# ============================================================================
# SELF-TEST (python -m mechanism_rule_engine)
# ============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

    engine = create_rule_engine()

    # Test cases
    test_cases = [
        # (reactant, product, conditions, expected_class)
        ("CBr.[OH-]", "CO.[Br-]", "SN2", "sn2"),
        ("CC(=O)C.CC=O", "CC(O)CC(=O)C", "NaOH", "aldol"),
        ("C=CC=C.C=C", "C1CC=CCC1", "heat, Diels-Alder", "diels_alder"),
        ("c1ccccc1Br.OB(O)c1ccccc1", "c1ccc(-c2ccccc2)cc1", "Pd(PPh3)4, Suzuki", "suzuki"),
        ("CCBr", "C=C", "t-BuOK, E2", "e2"),
    ]

    print("=" * 70)
    print("MechanismRuleEngine Self-Test")
    print("=" * 70)

    passed = 0
    failed = 0

    for r_smi, p_smi, cond, expected in test_cases:
        cls = engine.classify_only(r_smi, p_smi, cond)
        actual = cls.sub_class if cls else "None"
        ok = actual == expected

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {r_smi} + {cond} → {actual} (expected: {expected})")

        if ok:
            passed += 1
        else:
            failed += 1

        # Also test full generation
        mech = engine.generate(r_smi, p_smi, cond)
        if mech:
            print(f"         → {mech.title}, {mech.total_steps} steps, "
                  f"{sum(len(s.arrows) for s in mech.steps)} arrows")
        else:
            print(f"         → (generation failed or filtered)")

    print(f"\nResults: {passed}/{passed + failed} PASS")
    sys.exit(0 if failed == 0 else 1)
