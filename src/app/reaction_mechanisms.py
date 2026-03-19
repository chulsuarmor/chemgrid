# reaction_mechanisms.py (v2.0 - Organic Reaction Mechanism Data)
"""
ChemGrid: 유기합성반응 메커니즘 단계별 데이터
- 각 반응 유형의 전자 이동 단계를 정의
- 곡선 화살표 렌더링 데이터 포함
- v2.0: 모든 SMILES를 RDKit 파싱 가능한 유효 SMILES로 교체
        ArrowData에 from_atom_idx/to_atom_idx 추가하여 정확한 원자 매칭
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class ArrowData:
    """곡선 화살표 렌더링 데이터"""
    arrow_type: str          # "full" (2전자), "half" (1전자/라디칼)
    from_type: str           # "lone_pair", "bond", "pi_bond", "negative_charge"
    from_label: str          # 시작 위치 설명 (렌더링용)
    to_type: str             # "atom", "bond", "antibonding"
    to_label: str            # 끝 위치 설명
    color: str = "#E53935"   # 화살표 색상 (기본: 빨강)
    curvature: float = 0.3   # 곡률 (0=직선, 1=반원)
    from_atom_idx: int = -1  # 시작 원자 인덱스 (-1=자동 매칭)
    to_atom_idx: int = -1    # 끝 원자 인덱스 (-1=자동 매칭)


@dataclass
class MechanismStep:
    """반응 메커니즘의 단일 단계"""
    step_number: int
    title: str               # "친핵체 공격", "이탈기 이탈"
    description: str         # 상세 설명
    reactant_smiles: str     # 이 단계 시작 SMILES
    product_smiles: str      # 이 단계 끝 SMILES (중간체 또는 최종 생성물)
    arrows: List[ArrowData]  # 전자 이동 화살표들
    labels: Dict[str, str] = field(default_factory=dict)  # {위치: 라벨} (δ+, δ-, ‡ 등)
    is_transition_state: bool = False  # 전이 상태 표시 여부
    energy_label: str = ""   # "ΔG‡", "안정한 중간체" 등
    reagents: str = ""       # 화살표 위 시약/조건 (예: "H₂SO₄", "AlCl₃, CH₂Cl₂")
    notes: str = ""          # 추가 참고사항


@dataclass
class MechanismData:
    """완전한 반응 메커니즘"""
    mechanism_type: str      # "sn2", "sn1", "e2" 등
    title: str
    total_steps: int
    steps: List[MechanismStep]
    energy_diagram: List[Tuple[str, float]] = field(default_factory=list)  # [(라벨, 상대에너지)]
    overall_description: str = ""


# ============================================================================
# MECHANISM DEFINITIONS
# 모든 SMILES는 RDKit이 파싱 가능한 유효 SMILES만 사용
# ArrowData의 from_atom_idx/to_atom_idx는 reactant_smiles 기준 원자 인덱스
# ============================================================================

MECHANISMS: Dict[str, MechanismData] = {}

# ─── SN2 ────────────────────────────────────────────────────────────────────
# 대표 반응: CH3Br + OH⁻ → CH3OH + Br⁻

MECHANISMS["sn2"] = MechanismData(
    mechanism_type="sn2",
    title="SN2 (이분자 친핵성 치환)",
    total_steps=1,
    overall_description=(
        "SN2는 1단계 동시 반응입니다. 친핵체가 이탈기의 반대편(후면)에서 "
        "탄소를 공격하면서 이탈기가 동시에 이탈합니다. "
        "전이 상태에서 탄소는 5배위로 sp2-유사 기하를 가지며, "
        "결과적으로 입체배치가 반전(Walden 전환)됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵체 후면 공격 + 이탈기 이탈 (동시)",
            description=(
                "친핵체(OH-)의 론페어가 탄소의 C-Br 반결합 오비탈을 공격합니다.\n"
                "전이 상태 [HO···C···Br]-에서 탄소는 5배위를 형성합니다.\n"
                "이탈기(Br-)가 이탈하면서 탄소의 입체배치가 반전됩니다."
            ),
            # [OH-] = idx0, C=idx1, Br=idx2 in "CBr.[OH-]"
            reactant_smiles="CBr.[OH-]",
            product_smiles="CO.[Br-]",
            arrows=[
                ArrowData("full", "lone_pair", "OH- 론페어",
                          "atom", "C (delta+)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=0),  # O→C
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C→Br
            ],
            labels={"OH-": "친핵체", "C": "delta+ 탄소", "Br": "이탈기"},
            is_transition_state=True,
            energy_label="전이 상태",
            notes="반응 속도 = k[Nu-][R-X] (2차 반응)",
        ),
    ],
    energy_diagram=[
        ("반응물\nCH3Br + OH-", 0.0),
        ("[HO···C···Br]-\n전이 상태", 20.0),
        ("생성물\nCH3OH + Br-", -5.0),
    ],
)

# ─── SN1 ────────────────────────────────────────────────────────────────────
# 대표: (CH3)3CBr → (CH3)3C+ + Br- → (CH3)3COH

MECHANISMS["sn1"] = MechanismData(
    mechanism_type="sn1",
    title="SN1 (단분자 친핵성 치환)",
    total_steps=2,
    overall_description=(
        "SN1은 2단계 반응입니다. 먼저 이탈기가 이탈하여 카르보카티온 중간체를 형성하고, "
        "그 후 친핵체가 카르보카티온을 공격합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이탈기 이탈 → 카르보카티온 형성 (속도 결정)",
            description=(
                "C-Br 결합이 이종 개열(heterolysis)합니다: 결합 전자쌍 2개가 모두 Br로 이동.\n"
                "이유: 3차 탄소는 3개의 알킬기에 의한 초공액/유도 효과로 양전하를 안정화.\n"
                "Br이 이탈기(leaving group)로 떠남 → Br⁻ (할라이드 음이온).\n"
                "남은 탄소는 빈 p 오비탈을 가진 평면 삼각형 카르보카티온(sp2)이 됩니다.\n"
                "이 단계가 속도 결정 단계: 활성화 에너지가 가장 높음."
            ),
            # CC(C)(C)Br: C0-C1(-C2)(-C3)-Br4
            reactant_smiles="CC(C)(C)Br",
            product_smiles="CC(C)([CH2+]).[Br-]",
            arrows=[
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br (이탈기)", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=4),  # C→Br
            ],
            labels={"C": "C+", "Br": "Br-"},
            energy_label="속도 결정 단계",
            notes="속도 = k[R-X] (1차 반응). 3차 탄소에서 유리",
        ),
        MechanismStep(
            step_number=2,
            title="친핵체 공격 (빠른 단계)",
            description=(
                "H2O(친핵체)의 산소 론페어가 카르보카티온의 빈 p 오비탈을 공격합니다.\n"
                "새 C-O 결합 형성: O의 론페어 2개 전자가 C-O sigma 결합을 만듦.\n"
                "카르보카티온은 평면(sp2)이므로 위/아래 양면에서 공격 가능 → 라세미 혼합물.\n"
                "SN2와 달리 입체배치 반전이 아닌 라세미화가 일어나는 이유입니다."
            ),
            reactant_smiles="CC(C)([CH2+]).O",
            product_smiles="CC(C)(C)O",
            arrows=[
                ArrowData("full", "lone_pair", "H2O 론페어",
                          "atom", "C+ (빈 p 오비탈)", "#4CAF50", 0.4,
                          from_atom_idx=4, to_atom_idx=3),  # O→C+
            ],
            labels={"C": "C+ (sp2)", "O": "H2O (친핵체)"},
            energy_label="낮은 에너지 장벽",
        ),
    ],
    energy_diagram=[
        ("반응물\n(CH3)3CBr", 0.0),
        ("전이 상태 1", 25.0),
        ("카르보카티온\n+ Br-", 15.0),
        ("전이 상태 2", 18.0),
        ("생성물\n(CH3)3COH", -3.0),
    ],
)

# ─── E2 ─────────────────────────────────────────────────────────────────────
# 대표: CH3CH2Br + OH- → CH2=CH2 + H2O + Br-

MECHANISMS["e2"] = MechanismData(
    mechanism_type="e2",
    title="E2 (이분자 제거)",
    total_steps=1,
    overall_description=(
        "E2는 1단계 동시 반응입니다. 강한 염기가 beta-수소를 제거하면서 "
        "이탈기가 동시에 이탈합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="beta-H 제거 + 이탈기 이탈 + pi-결합 형성 (동시)",
            description=(
                "염기(OH-)가 beta-수소를 제거합니다.\n"
                "C-H 결합 전자쌍이 C=C pi-결합을 형성합니다.\n"
                "동시에 C-Br 결합 전자쌍이 Br-로 이동합니다."
            ),
            # CCBr: C0-C1-Br2, OH-: O3
            reactant_smiles="CCBr.[OH-]",
            product_smiles="C=C.O.[Br-]",
            arrows=[
                ArrowData("full", "lone_pair", "OH- (염기)",
                          "atom", "beta-H", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=0),  # OH→C(H)
                ArrowData("full", "bond", "C-H 결합",
                          "bond", "C=C pi 형성", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-H→C=C
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br- (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C→Br
            ],
            labels={"OH": "염기", "H": "beta-H", "Br": "이탈기"},
            energy_label="전이 상태",
            notes="Zaitsev 법칙: 더 치환된 알켄이 주생성물",
        ),
    ],
    energy_diagram=[
        ("반응물\nCH3CH2Br + OH-", 0.0),
        ("[HO···H-C-C···Br]-", 22.0),
        ("생성물\nCH2=CH2 + H2O + Br-", -8.0),
    ],
)

# ─── E1 ─────────────────────────────────────────────────────────────────────

MECHANISMS["e1"] = MechanismData(
    mechanism_type="e1",
    title="E1 (단분자 제거)",
    total_steps=2,
    overall_description=(
        "E1은 2단계 반응입니다. 먼저 이탈기가 이종 개열로 떠나 카르보카티온이 형성되고(속도 결정), "
        "이어서 약한 염기/용매가 beta-수소를 제거하면서 C-H 결합 전자쌍이 C=C pi-결합을 형성합니다. "
        "Zaitsev 법칙에 따라 더 치환된 알켄이 주생성물입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이탈기 이탈 → 카르보카티온 (속도 결정)",
            description=(
                "C-Br 결합이 이종 개열(heterolysis): 결합 전자쌍 2개가 모두 Br로 이동 → Br⁻.\n"
                "3차 탄소의 양전하는 3개 알킬기의 초공액 효과로 안정화됩니다.\n"
                "빈 p 오비탈을 가진 평면 삼각형 카르보카티온(sp2) 중간체 형성.\n"
                "이 단계가 속도 결정 단계(RDS): 반응 속도 = k[(CH₃)₃CBr] (1차 반응)."
            ),
            reactant_smiles="CC(C)(C)Br",
            product_smiles="CC(C)([CH2+]).[Br-]",
            arrows=[
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br-", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=4),
            ],
            labels={"C": "C+", "Br": "Br-"},
            energy_label="속도 결정 단계",
        ),
        MechanismStep(
            step_number=2,
            title="beta-수소 제거 → 알켄 형성",
            description=(
                "약한 염기 또는 용매가 beta-수소를 제거합니다.\n"
                "C-H 결합 전자쌍이 C=C 이중결합을 형성합니다."
            ),
            reactant_smiles="C[C+](C)C",
            product_smiles="CC(=C)C",
            arrows=[
                ArrowData("full", "bond", "C-H 결합",
                          "bond", "C=C pi-결합", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=1),  # CH3→C+
            ],
            labels={"H": "beta-H"},
            energy_label="낮은 장벽",
        ),
    ],
    energy_diagram=[
        ("반응물\n(CH3)3CBr", 0.0),
        ("전이 상태 1", 25.0),
        ("카르보카티온", 15.0),
        ("전이 상태 2", 17.0),
        ("생성물\n이소부틸렌", -5.0),
    ],
)

# ─── 친전자 첨가 ─────────────────────────────────────────────────────────────
# 대표: CH2=CH2 + HBr → CH3CH2Br

MECHANISMS["electrophilic_addition"] = MechanismData(
    mechanism_type="electrophilic_addition",
    title="친전자 첨가 (Markovnikov)",
    total_steps=2,
    overall_description=(
        "알켄의 pi-전자가 친전자체(H+)를 공격하여 카르보카티온을 형성하고, "
        "이어서 친핵체가 공격합니다. Markovnikov 법칙을 따릅니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="pi-결합이 H+ 공격 → 카르보카티온",
            description=(
                "알켄의 C=C pi-결합 전자쌍(HOMO)이 H⁺(친전자체)를 공격합니다.\n"
                "pi-결합이 끊어짐: 전자쌍 2개가 새 C-H sigma 결합을 형성.\n"
                "Markovnikov 법칙: H⁺는 H가 더 많은 탄소에 결합 → 더 안정한 카르보카티온 형성.\n"
                "나머지 탄소는 빈 p 오비탈의 카르보카티온(C⁺)이 됩니다."
            ),
            # C=C: C0=C1, HBr: not included (H+ is electrophile)
            reactant_smiles="C=C",
            product_smiles="C[CH2+]",
            arrows=[
                ArrowData("full", "pi_bond", "C=C pi 결합",
                          "atom", "H+ (프로톤)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=1),  # pi→C+
            ],
            labels={"C=C": "pi-결합 (HOMO)"},
            energy_label="속도 결정",
        ),
        MechanismStep(
            step_number=2,
            title="Br- 공격 → 생성물",
            description=(
                "Br⁻(친핵체)의 론페어가 카르보카티온의 빈 p 오비탈을 공격합니다.\n"
                "새 C-Br sigma 결합 형성: Br의 론페어 2개 전자가 결합에 사용됨.\n"
                "Br⁻의 음전하가 중화되고, C⁺의 양전하도 중화 → 중성 할로겐화 알킬 생성."
            ),
            reactant_smiles="C[CH2+].[Br-]",
            product_smiles="CCBr",
            arrows=[
                ArrowData("full", "negative_charge", "Br-",
                          "atom", "C+", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=1),  # Br→C+
            ],
            labels={"C": "C+", "Br": "Br- (친핵체)"},
            energy_label="낮은 장벽",
        ),
    ],
    energy_diagram=[
        ("반응물\nC=C + HBr", 0.0),
        ("전이 상태 1", 15.0),
        ("카르보카티온\n+ Br-", 10.0),
        ("전이 상태 2", 12.0),
        ("생성물\nCH3CH2Br", -10.0),
    ],
)

# ─── 친핵 첨가 (카르보닐) ─────────────────────────────────────────────────

MECHANISMS["nucleophilic_addition"] = MechanismData(
    mechanism_type="nucleophilic_addition",
    title="친핵 첨가 (카르보닐)",
    total_steps=2,
    overall_description=(
        "친핵체가 카르보닐 탄소(delta+)를 공격하여 사면체 알콕사이드 중간체를 형성합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵체 → 카르보닐 탄소 공격",
            description=(
                "친핵체(CN-)의 론페어가 카르보닐 C(delta+)의 pi* 오비탈을 공격합니다.\n"
                "C=O pi-결합이 끊어지면서 전자쌍이 산소로 이동 → O- 형성."
            ),
            # CC=O: C0-C1(=O2), [CN-]: C3#N4
            reactant_smiles="CC=O.[C-]#N",
            product_smiles="CC([O-])C#N",
            arrows=[
                ArrowData("full", "lone_pair", "CN- 론페어",
                          "atom", "C=O (delta+)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=1),  # CN→C(=O)
                ArrowData("full", "pi_bond", "C=O pi 결합",
                          "atom", "O (론페어로)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C=O→O-
            ],
            labels={"CN": "친핵체", "C": "delta+ (sp2→sp3)", "O": "→ O-"},
            energy_label="전이 상태",
        ),
        MechanismStep(
            step_number=2,
            title="양성자화 → 시아노히드린",
            description=(
                "알콕사이드(O⁻)의 론페어가 용매의 H⁺를 공격 → 새 O-H 결합 형성.\n"
                "O⁻의 음전하가 중화되어 안정한 시아노히드린(-OH) 생성.\n"
                "산-염기 반응: O⁻(강한 염기)가 양성자를 받아 안정화되는 발열 과정."
            ),
            reactant_smiles="CC([O-])C#N",
            product_smiles="CC(O)C#N",
            arrows=[
                ArrowData("full", "lone_pair", "O-",
                          "atom", "H+ (용매)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),  # O-→H (외부)
            ],
            labels={"O": "O- → OH"},
            energy_label="발열 (안정화)",
        ),
    ],
    energy_diagram=[
        ("반응물\nCN- + CH3CHO", 0.0),
        ("전이 상태", 12.0),
        ("알콕사이드\n중간체", 5.0),
        ("생성물\n시아노히드린", -15.0),
    ],
)

# ─── EAS (친전자 방향족 치환) ────────────────────────────────────────────────
# 대표: 벤젠 + Br2/AlCl3 → 브로모벤젠

MECHANISMS["eas"] = MechanismData(
    mechanism_type="eas",
    title="친전자 방향족 치환 (EAS)",
    total_steps=3,
    overall_description=(
        "Lewis acid(AlCl₃)가 Br₂를 활성화하여 Br⁺를 생성합니다. "
        "방향족 고리의 pi-전자가 친전자체를 공격하여 sigma-complex를 형성하고, "
        "양성자 이탈로 방향족성이 회복됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Lewis acid 활성화: AlCl₃ + Br₂ → Br⁺",
            description=(
                "AlCl₃의 빈 p 오비탈이 Br₂의 Br 론페어를 받아 착물을 형성합니다.\n"
                "Br-Br 결합이 이종 개열(heterolysis) → Br⁺ + AlCl₃Br⁻.\n"
                "Br⁺가 친전자체로 작용합니다."
            ),
            # BrBr: Br0-Br1
            reactant_smiles="BrBr",
            product_smiles="[Br+].[Br-]",
            arrows=[
                ArrowData("full", "lone_pair", "Br 론페어",
                          "atom", "AlCl₃ (Lewis acid)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=-1),  # Br→외부 AlCl₃
                ArrowData("full", "bond", "Br-Br σ 결합",
                          "atom", "Br⁻ (→AlCl₃Br⁻)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # Br-Br heterolysis
            ],
            labels={"Br": "Br⁺ (친전자체)", "AlCl₃": "Lewis acid"},
            energy_label="착물 형성",
            reagents="AlCl₃",
        ),
        MechanismStep(
            step_number=2,
            title="pi-공격 → sigma-complex 형성 (속도 결정)",
            description=(
                "방향족 pi-전자가 생성된 Br⁺를 공격합니다.\n"
                "방향족성이 일시적으로 깨지면서 sigma-complex(Wheland 중간체) 형성."
            ),
            reactant_smiles="c1ccccc1",
            product_smiles="[CH-]1C=CC=CC1Br",
            arrows=[
                ArrowData("full", "pi_bond", "벤젠 pi-전자",
                          "atom", "Br⁺ (친전자체)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"Ar": "방향족 (HOMO)", "Br": "Br⁺"},
            energy_label="속도 결정 단계",
            notes="sigma-complex에서 양전하는 ortho/para 위치에 비편재화",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 이탈 → 방향족성 회복",
            description=(
                "AlCl₃Br⁻가 염기로 작용하여 sigma-complex의 H⁺를 제거합니다.\n"
                "C-H 결합 전자쌍이 pi-결합으로 복귀 → 방향족성 회복."
            ),
            reactant_smiles="C1=CC=CC(Br)C1",
            product_smiles="c1ccc(Br)cc1",
            arrows=[
                ArrowData("full", "bond", "C-H 결합",
                          "atom", "H⁺ (→ AlCl₃Br⁻에 의해 탈양성자)", "#4CAF50", 0.3,
                          from_atom_idx=5, to_atom_idx=-1),
            ],
            labels={"H": "H⁺ (이탈)"},
            energy_label="발열 (방향족성 회복)",
            reagents="AlCl₃Br⁻ (base)",
        ),
    ],
    energy_diagram=[
        ("반응물\nC6H6 + Br2", 0.0),
        ("AlCl₃ 착물\nBr⁺ 형성", 5.0),
        ("전이 상태 1", 20.0),
        ("sigma-complex\n[ArHBr]+", 15.0),
        ("전이 상태 2", 16.0),
        ("생성물\nC6H5Br + HBr", -5.0),
    ],
)

# ─── Fischer 에스터화 ─────────────────────────────────────────────────────────
# 대표: CH3COOH + CH3CH2OH → CH3COOCH2CH3 + H2O

MECHANISMS["esterification"] = MechanismData(
    mechanism_type="esterification",
    title="Fischer 에스터화",
    total_steps=4,
    overall_description=(
        "산 촉매(H₂SO₄) 하에서 카르복실산과 알코올이 반응하여 에스터와 물을 생성합니다. "
        "H₂SO₄가 H⁺를 제공하여 카르보닐을 활성화하고, 반응 후 H⁺를 회수합니다. "
        "평형 반응이므로 물을 제거하면 반응이 진행됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="H₂SO₄가 H⁺ 제공 → 카르보닐 양성자화",
            description=(
                "H₂SO₄의 O-H 결합이 끊어지며 H⁺가 방출됩니다.\n"
                "카르보닐 산소의 론페어가 H⁺를 잡아 C=O가 양성자화됩니다.\n"
                "이로써 카르보닐 탄소의 친전자성이 크게 증가합니다."
            ),
            # CC(=O)O: C0-C1(=O2)-O3(H)
            reactant_smiles="CC(=O)O",
            product_smiles="CC(=[OH+])O",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (from H₂SO₄)",
                          "atom", "C=O 산소", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=2),  # 외부 H⁺→O
            ],
            labels={"O": "→ OH⁺", "H₂SO₄": "산 촉매"},
            energy_label="산 촉매 활성화",
            reagents="H₂SO₄ → H⁺ + HSO₄⁻",
        ),
        MechanismStep(
            step_number=2,
            title="알코올 친핵 공격 → 사면체 중간체",
            description=(
                "알코올(EtOH)의 산소 론페어가 활성화된 카르보닐 C(δ⁺⁺)를 공격합니다.\n"
                "카르보닐 탄소가 sp2 → sp3로 변화하며 사면체 중간체 형성."
            ),
            reactant_smiles="CC(=[OH+])O.CCO",
            product_smiles="CC(O)(O)OCC",
            arrows=[
                ArrowData("full", "lone_pair", "EtOH O: 론페어",
                          "atom", "C (δ⁺⁺, 활성화됨)", "#4CAF50", 0.4,
                          from_atom_idx=6, to_atom_idx=1),  # EtO→C(=O)
                ArrowData("full", "pi_bond", "C=OH⁺ pi 결합",
                          "atom", "O (→ OH)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C=O pi→O
            ],
            labels={"EtOH": "친핵체", "C": "sp2 → sp3"},
            energy_label="전이 상태",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 전달 + H₂O 이탈",
            description=(
                "사면체 중간체 내부에서 양성자 전달이 일어나 -OH가 -OH₂⁺로 변합니다.\n"
                "H₂O가 좋은 이탈기가 되어 이탈합니다."
            ),
            reactant_smiles="CC(O)(O)OCC",
            product_smiles="CCOC(C)=O",
            arrows=[
                ArrowData("full", "bond", "C-OH 결합",
                          "atom", "H₂O (이탈기)", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C-OH→H2O 이탈
                ArrowData("full", "lone_pair", "에스터 O 론페어",
                          "bond", "C=O 재형성", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=1),  # OR→C(=O)
            ],
            labels={"OH": "→ H₂O (이탈)", "C": "sp3 → sp2"},
            energy_label="물 이탈",
        ),
        MechanismStep(
            step_number=4,
            title="H⁺ 재생 → 산 촉매 회수",
            description=(
                "에스터의 카르보닐 산소에서 H⁺가 떨어져 HSO₄⁻에 돌아갑니다.\n"
                "H₂SO₄ 촉매가 재생되어 다음 반응 사이클에 사용됩니다."
            ),
            reactant_smiles="CCOC(C)=O",
            product_smiles="CCOC(C)=O",
            arrows=[
                ArrowData("full", "bond", "O-H⁺ 결합",
                          "atom", "HSO₄⁻ (촉매 회수)", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=-1),  # O-H⁺→H⁺ 방출
            ],
            labels={"H⁺": "촉매 재생"},
            energy_label="촉매 재생",
            reagents="HSO₄⁻ → H₂SO₄",
            notes="Le Chatelier: 물 제거 또는 알코올 과량으로 평형 이동",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOOH + R'OH", 0.0),
        ("H⁺ 양성자화", 3.0),
        ("전이 상태\n친핵 공격", 15.0),
        ("사면체 중간체", 8.0),
        ("H₂O 이탈", 10.0),
        ("생성물\nRCOOR' + H₂O", 1.0),
    ],
)

# ─── Diels-Alder ─────────────────────────────────────────────────────────────
# 대표: 부타디엔 + 에틸렌 → 사이클로헥센

MECHANISMS["diels_alder"] = MechanismData(
    mechanism_type="diels_alder",
    title="Diels-Alder [4+2] 고리화 첨가",
    total_steps=1,
    overall_description=(
        "디엔(4pi)과 디에노필(2pi)이 동시 [4+2] 고리화 첨가 반응을 합니다. "
        "6원 고리가 형성됩니다. 열허용 페리사이클릭 반응입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[4+2] 동시 고리화 — 6원 고리 형성",
            description=(
                "디엔의 HOMO와 디에노필의 LUMO가 suprafacial 중첩합니다.\n"
                "6개의 전자가 동시에 재배열되며 2개의 새 sigma-결합이 형성됩니다."
            ),
            # C=CC=C: 1,3-butadiene C0=C1-C2=C3
            # C=C: ethylene C4=C5
            reactant_smiles="C=CC=C.C=C",
            product_smiles="C1CC=CCC1",
            arrows=[
                ArrowData("full", "pi_bond", "디엔 C1-C2 pi",
                          "atom", "디에노필 C5", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=4),  # C1→dienophile C5
                ArrowData("full", "pi_bond", "디에노필 C5-C6 pi",
                          "bond", "새 sigma-결합", "#4CAF50", 0.5,
                          from_atom_idx=4, to_atom_idx=5),  # C5→C6
                ArrowData("full", "pi_bond", "디엔 C3-C4 pi",
                          "atom", "디에노필 C6", "#1565C0", 0.5,
                          from_atom_idx=3, to_atom_idx=5),  # C4→dienophile C6
            ],
            labels={"diene": "디엔 (HOMO, 4pi)", "dienophile": "디에노필 (LUMO, 2pi)"},
            energy_label="동시 전이 상태",
            notes="Woodward-Hoffmann: 열허용 [4s+2s]",
        ),
    ],
    energy_diagram=[
        ("반응물\n디엔 + 디에노필", 0.0),
        ("[4+2] 전이 상태", 18.0),
        ("생성물\n사이클로헥센", -25.0),
    ],
)

# ─── 산화 ─────────────────────────────────────────────────────────────────────
# 대표: CH3CH2OH + [O] → CH3CHO

MECHANISMS["oxidation"] = MechanismData(
    mechanism_type="oxidation",
    title="1차 알코올 산화",
    total_steps=2,
    overall_description=(
        "1차 알코올이 산화제에 의해 알데히드 또는 카르복실산으로 산화됩니다. "
        "PCC는 알데히드에서 정지, KMnO4/CrO3는 카르복실산까지 진행합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="알코올 O가 Cr(VI) 공격 → 크로메이트 에스터",
            description=(
                "알코올의 산소 론페어가 CrO₃(산화제)의 Cr(δ⁺)를 친핵 공격합니다.\n"
                "Cr-O 결합이 형성되면서 크로메이트 에스터 중간체 생성."
            ),
            # CCO: C0-C1-O2(H)
            reactant_smiles="CCO",
            product_smiles="CCOC(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "알코올 O: 론페어",
                          "atom", "CrO₃ (Cr δ⁺)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=-1),  # O→외부 Cr
            ],
            labels={"O": "친핵체 (알코올 O)", "Cr": "산화제 Cr(VI)"},
            energy_label="에스터 형성",
            reagents="CrO₃ / PCC",
        ),
        MechanismStep(
            step_number=2,
            title="E2-유사 제거 → 알데히드",
            description=(
                "염기가 alpha-수소를 제거하면서 Cr 이탈기가 동시에 이탈.\n"
                "결과: C=O 이중결합 형성 → 알데히드."
            ),
            # CCOC(=O)O 중간체에서
            reactant_smiles="CCOC(=O)O",
            product_smiles="CC=O",
            arrows=[
                ArrowData("full", "lone_pair", "B- (염기)",
                          "atom", "alpha-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),  # 외부→C(H)
                ArrowData("full", "bond", "C-H sigma",
                          "bond", "C=O pi", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-H→C=O
                ArrowData("full", "bond", "O-Cr",
                          "atom", "Cr(IV)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # O→Cr
            ],
            labels={"H": "alpha-H", "Cr": "이탈기"},
            energy_label="E2-유사",
            notes="PCC: 여기서 정지. KMnO4: 카르복실산까지 진행.",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCH2OH", 0.0),
        ("크로메이트 에스터", 5.0),
        ("전이 상태", 15.0),
        ("생성물\nRCHO", -10.0),
    ],
)

# ─── 아마이드화 ─────────────────────────────────────────────────────────────
# 대표: CH3COCl + CH3NH2 → CH3CONHCH3 + HCl

MECHANISMS["amidation"] = MechanismData(
    mechanism_type="amidation",
    title="아마이드 결합 형성",
    total_steps=2,
    overall_description=(
        "아실 할로겐화물(RCOCl)의 카르보닐 탄소(delta+)에 아민(RNH2)이 친핵 공격합니다. "
        "사면체 중간체를 거쳐 Cl⁻이탈기가 떠나면서 C=O가 회복되고 아마이드 결합(C-N)이 형성됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아민의 친핵 공격 → 사면체 중간체",
            description=(
                "아민(CH₃NH₂)의 질소 론페어가 아실 탄소(C=O의 delta+)를 친핵 공격합니다.\n"
                "C=O pi-결합이 끊어짐 → 전자쌍이 산소로 이동하여 O⁻ 형성.\n"
                "카르보닐 탄소: sp2 → sp3 혼성 변화, 사면체 중간체 형성.\n"
                "새 C-N 결합 형성: N의 론페어 2개 전자가 C-N sigma 결합에 사용됨."
            ),
            # CC(=O)Cl: C0-C1(=O2)-Cl3, CN: C4-N5
            reactant_smiles="CC(=O)Cl.CN",
            product_smiles="CC(O)(NC)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "NH2 론페어",
                          "atom", "C=O (delta+)", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=1),  # N→C(=O)
            ],
            labels={"N": "친핵체", "C": "delta+"},
            energy_label="전이 상태",
        ),
        MechanismStep(
            step_number=2,
            title="이탈기 이탈 → 아마이드",
            description=(
                "사면체 중간체의 C-Cl 결합이 이종 개열: 전자쌍 2개가 Cl로 이동 → Cl⁻ 이탈.\n"
                "Cl⁻이 좋은 이탈기인 이유: Cl의 큰 원자 크기로 음전하를 안정화.\n"
                "동시에 N의 론페어가 C쪽으로 밀어 C=O pi-결합이 회복됩니다.\n"
                "최종: 아마이드 결합(C(=O)-N) 형성, sp3 → sp2 복귀."
            ),
            reactant_smiles="CC(O)(NC)Cl",
            product_smiles="CC(=O)NC",
            arrows=[
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl-", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=4),  # C→Cl
                ArrowData("full", "lone_pair", "N 론페어",
                          "bond", "C=O 회복", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=1),  # N→C
            ],
            labels={"Cl": "이탈기", "N": "아마이드 N"},
            energy_label="발열",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOCl + RNH2", 0.0),
        ("전이 상태", 15.0),
        ("사면체 중간체", 8.0),
        ("생성물\nRCONHR + HCl", -12.0),
    ],
)


# ─── Friedel-Crafts 알킬화 ────────────────────────────────────────────────
# 대표: C6H6 + CH3Cl + AlCl3 → C6H5CH3 + HCl + AlCl3

MECHANISMS["friedel_crafts_alkylation"] = MechanismData(
    mechanism_type="friedel_crafts_alkylation",
    title="Friedel-Crafts 알킬화",
    total_steps=3,
    overall_description=(
        "Lewis acid(AlCl₃)가 할로겐화 알킬의 C-X 결합을 활성화하여 "
        "카르보카티온을 형성합니다. 방향족 pi-전자가 친전자체를 공격하고, "
        "AlCl₄⁻가 염기로 작용하여 양성자를 제거합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="AlCl₃ Lewis acid 활성화 → CH₃⁺ 생성",
            description=(
                "AlCl₃(Lewis acid)의 빈 p 오비탈이 CH₃Cl의 Cl 론페어를 받아 배위합니다.\n"
                "Cl의 전자밀도가 AlCl₃로 이동 → C-Cl 결합이 이종 개열.\n"
                "CH₃⁺ 카르보카티온이 친전자체로 생성됩니다."
            ),
            # CCl: C0-Cl1
            reactant_smiles="CCl",
            product_smiles="[CH3+].[Cl-]",
            arrows=[
                ArrowData("full", "lone_pair", "Cl: 론페어",
                          "atom", "AlCl₃ 빈 오비탈", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=-1),  # Cl→외부 AlCl₃
                ArrowData("full", "bond", "C-Cl σ 결합",
                          "atom", "Cl (→ AlCl₄⁻)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-Cl heterolysis
            ],
            labels={"C": "CH₃⁺", "Cl": "→ AlCl₄⁻"},
            energy_label="Lewis acid 활성화",
            reagents="AlCl₃",
        ),
        MechanismStep(
            step_number=2,
            title="방향족 pi-공격 → σ-complex (속도 결정)",
            description=(
                "벤젠의 pi-전자가 CH₃⁺를 공격합니다.\n"
                "방향족성이 깨지면서 Wheland 중간체(σ-complex) 형성.\n"
                "양전하가 ortho/para 위치에 비편재화됩니다."
            ),
            reactant_smiles="c1ccccc1",
            product_smiles="C1=CC(C)=CC=C1",
            arrows=[
                ArrowData("full", "pi_bond", "벤젠 pi-전자",
                          "atom", "CH₃⁺ (친전자체)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"ring": "pi → sigma", "CH₃⁺": "친전자체"},
            energy_label="속도 결정 단계",
        ),
        MechanismStep(
            step_number=3,
            title="AlCl₄⁻ 탈양성자화 → 방향족성 회복",
            description=(
                "AlCl₄⁻가 염기로 작용하여 σ-complex의 H⁺를 제거합니다.\n"
                "C-H 결합 전자쌍이 pi-계로 복귀 → 방향족성 회복.\n"
                "AlCl₃ 촉매가 재생됩니다 (AlCl₄⁻ + H⁺ → HCl + AlCl₃)."
            ),
            reactant_smiles="C1=CC(C)=CC=C1",
            product_smiles="Cc1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "AlCl₄⁻ (염기)",
                          "atom", "H (σ-complex)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),  # AlCl₄⁻→H
                ArrowData("full", "bond", "C-H 결합",
                          "bond", "pi-계 복귀", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C-H→pi
            ],
            labels={"H": "→ HCl", "ring": "방향족 회복"},
            energy_label="발열",
            reagents="AlCl₄⁻ → HCl + AlCl₃",
        ),
    ],
    energy_diagram=[
        ("반응물\nC₆H₆ + CH₃Cl", 0.0),
        ("AlCl₃ 착물\nCH₃⁺ 생성", 5.0),
        ("σ-complex\n(Wheland)", 18.0),
        ("탈양성자화", 16.0),
        ("생성물\nToluene + HCl", -8.0),
    ],
)

# ─── 토실화 (Tosylation) ──────────────────────────────────────────────────
# 대표: ROH + TsCl → ROTs + HCl (pyridine 촉매)

MECHANISMS["tosylation"] = MechanismData(
    mechanism_type="tosylation",
    title="알코올 토실화 (Tosylation)",
    total_steps=2,
    overall_description=(
        "토실 클로라이드(TsCl, p-CH₃C₆H₄SO₂Cl)가 알코올의 -OH를 좋은 이탈기인 "
        "-OTs로 변환합니다. 피리딘이 염기/촉매로 작용하여 HCl을 제거합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="알코올 O가 TsCl의 S를 친핵 공격",
            description=(
                "알코올의 산소 론페어가 TsCl의 S(δ⁺)를 공격합니다.\n"
                "S는 확장된 옥텟으로 5배위 중간체를 형성.\n"
                "동시에 S-Cl 결합이 약화됩니다."
            ),
            # CCO: C0-C1-O2, [S=O 대표] ClS(=O)(=O)c1ccc(C)cc1
            # 간략화: CCO + ClS(C)(=O)=O (ethanol + methanesulfonyl chloride)
            reactant_smiles="CCO.CS(=O)(=O)Cl",
            product_smiles="CCOS(C)(=O)=O",
            arrows=[
                ArrowData("full", "lone_pair", "알코올 O 론페어",
                          "atom", "S (δ⁺, 친전자)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=4),  # O→S
                ArrowData("full", "bond", "S-Cl 결합",
                          "atom", "Cl⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=7),  # S→Cl
            ],
            labels={"O": "친핵체 (ROH)", "S": "δ⁺", "Cl": "이탈기"},
            energy_label="전이 상태",
            reagents="TsCl, Pyridine",
        ),
        MechanismStep(
            step_number=2,
            title="양성자 제거 → 토실레이트 생성",
            description=(
                "피리딘이 염기로 작용하여 O-H의 양성자를 제거합니다.\n"
                "최종 생성물: 알킬 토실레이트 (좋은 이탈기)."
            ),
            reactant_smiles="CCOS(C)(=O)=O",
            product_smiles="CCOS(C)(=O)=O",
            arrows=[
                ArrowData("full", "lone_pair", "Pyridine N: 론페어",
                          "atom", "O-H → H⁺", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=2),  # 외부 Py→O(H)
            ],
            labels={"Py": "염기", "O": "→ OTs"},
            energy_label="발열",
            reagents="Pyridine (base)",
            notes="ROTs는 SN2 반응의 좋은 기질 (OTs는 좋은 이탈기)",
        ),
    ],
    energy_diagram=[
        ("반응물\nROH + TsCl", 0.0),
        ("전이 상태", 12.0),
        ("생성물\nROTs + HCl", -5.0),
    ],
)

# ─── 라디칼 할로겐화 (UV) ─────────────────────────────────────────────────
# 대표: CH4 + Cl2 → CH3Cl + HCl (hv/UV, radical chain)

MECHANISMS["radical_halogenation"] = MechanismData(
    mechanism_type="radical_halogenation",
    title="라디칼 할로겐화 (UV 개시)",
    total_steps=3,
    overall_description=(
        "UV/열에 의해 Cl₂가 균일하게 개열(homolysis)하여 Cl·라디칼이 생성됩니다. "
        "라디칼 연쇄 반응: 개시(Initiation) → 전파(Propagation) → 종결(Termination)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="개시 (Initiation): Cl₂ 균일 개열",
            description=(
                "UV 에너지가 Cl-Cl 결합을 균일 개열합니다.\n"
                "각 Cl 원자가 전자 1개씩 가져갑니다 → 2 Cl· 라디칼."
            ),
            # ClCl: Cl0-Cl1
            reactant_smiles="ClCl",
            product_smiles="[Cl].[Cl]",
            arrows=[
                ArrowData("half", "bond", "Cl-Cl σ 결합",
                          "atom", "Cl· 라디칼", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # fishhook: Cl←Cl
                ArrowData("half", "bond", "Cl-Cl σ 결합",
                          "atom", "Cl· 라디칼", "#E53935", -0.3,
                          from_atom_idx=1, to_atom_idx=0),  # fishhook: Cl→Cl
            ],
            labels={"Cl": "Cl·"},
            energy_label="hν (UV)",
            reagents="hν (UV light)",
            notes="피셔훅(반쪽) 화살표: 1전자 이동",
        ),
        MechanismStep(
            step_number=2,
            title="전파 1 (Propagation): H 탈취",
            description=(
                "Cl· 라디칼이 CH₄에서 H를 탈취합니다.\n"
                "C-H 결합이 균일 개열 → CH₃· 라디칼 + HCl 생성."
            ),
            # C: methane (C0), [Cl]: radical
            reactant_smiles="C.[Cl]",
            product_smiles="[CH3].[ClH]",
            arrows=[
                ArrowData("half", "lone_pair", "Cl· 부전자",
                          "atom", "H (from CH₄)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=0),  # Cl·→C(H)
                ArrowData("half", "bond", "C-H 결합",
                          "atom", "H → Cl", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-H→H-Cl
            ],
            labels={"Cl": "Cl·", "C": "→ CH₃·"},
            energy_label="전파 단계 1",
            reagents="Cl· radical",
        ),
        MechanismStep(
            step_number=3,
            title="전파 2 (Propagation): Cl₂ 공격",
            description=(
                "CH₃· 라디칼이 Cl₂ 분자를 공격합니다.\n"
                "Cl-Cl 결합이 균일 개열 → CH₃Cl + Cl· 재생성.\n"
                "연쇄 반응이 계속됩니다."
            ),
            reactant_smiles="[CH3].ClCl",
            product_smiles="CCl.[Cl]",
            arrows=[
                ArrowData("half", "lone_pair", "CH₃· 부전자",
                          "atom", "Cl (from Cl₂)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=1),  # CH3·→Cl
                ArrowData("half", "bond", "Cl-Cl 결합",
                          "atom", "Cl· 재생성", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # Cl-Cl→Cl·
            ],
            labels={"CH3": "CH₃·", "Cl": "Cl· 재생"},
            energy_label="전파 단계 2",
            reagents="Cl₂",
            notes="Cl· 라디칼이 재생성 → 연쇄반응",
        ),
    ],
    energy_diagram=[
        ("Cl₂\n(안정)", 0.0),
        ("개시\n2 Cl·", 58.0),
        ("전파1\nCH₃· + HCl", 2.0),
        ("전파2\nCH₃Cl + Cl·", -25.0),
    ],
)

# ─── Beckmann 전위 (Rearrangement) ──────────────────────────────────────
# 대표: 사이클로헥사논 옥심 → ε-카프로락탐 (나일론 전구체)

MECHANISMS["beckmann"] = MechanismData(
    mechanism_type="beckmann",
    title="Beckmann 전위",
    total_steps=3,
    overall_description=(
        "옥심(R₂C=N-OH)이 산 촉매 하에 전위하여 아마이드로 변환됩니다. "
        "anti-periplanar 알킬기가 질소로 이동합니다. "
        "카프로락탐(나일론 6 전구체) 합성에 산업적으로 중요합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="H₂SO₄가 H⁺ 제공 → N-OH 양성자화",
            description=(
                "H₂SO₄의 O-H 결합이 끊어지며 H⁺가 방출됩니다.\n"
                "옥심 -OH의 산소 론페어가 이 H⁺를 잡습니다.\n"
                "-OH₂⁺는 좋은 이탈기(물)가 되어 다음 단계를 가능하게 합니다."
            ),
            # CC(=NO)C: acetone oxime C0-C1(=N2-O3)-C4
            reactant_smiles="CC(C)=NO",
            product_smiles="CC(C)=N[OH2+]",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (from H₂SO₄)",
                          "atom", "O (옥심 -OH)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=3),  # 외부 H⁺→O
            ],
            labels={"O": "→ OH₂⁺", "H₂SO₄": "산 → H⁺ + HSO₄⁻"},
            energy_label="양성자화",
            reagents="H₂SO₄ → H⁺",
        ),
        MechanismStep(
            step_number=2,
            title="1,2-알킬 이동 + H₂O 이탈 (동시)",
            description=(
                "Anti-periplanar 알킬기가 1,2-이동으로 N에 결합합니다.\n"
                "동시에 H₂O가 이탈 → 나이트릴리움 이온 중간체.\n"
                "이것이 Beckmann 전위의 핵심 단계입니다."
            ),
            # CC(C)=N[OH2+]: C0-C1(=N2-OH2+3)-C4
            reactant_smiles="CC(C)=N[OH2+]",
            product_smiles="CC(=O)NC",
            arrows=[
                ArrowData("full", "bond", "C-R σ 결합 (anti)",
                          "atom", "N (1,2-이동)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=2),  # C→N 이동
                ArrowData("full", "bond", "N-O 결합",
                          "atom", "H₂O 이탈", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # N-O→H₂O
            ],
            labels={"R": "1,2-이동", "H₂O": "이탈기"},
            energy_label="속도 결정 단계",
            reagents="",
            notes="Anti-periplanar 관계의 R만 이동 → 입체선택적",
        ),
        MechanismStep(
            step_number=3,
            title="물에 의한 가수분해 → 아마이드",
            description=(
                "H₂O(친핵체)의 산소 론페어가 나이트릴리움 이온의 C⁺를 공격합니다.\n"
                "새 C-O 결합 형성 → 불안정한 이미닐 중간체.\n"
                "양성자 전달(tautomerism)을 거쳐 안정한 아마이드(C(=O)-NH) 구조로 재배열.\n"
                "최종: R-CO-NH-R' 아마이드 + H₂O 부산물."
            ),
            reactant_smiles="CC(=O)NC",
            product_smiles="CC(=O)NC",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C⁺ (나이트릴리움)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),  # 외부 H2O→C
            ],
            labels={"H2O": "친핵체"},
            energy_label="가수분해",
            reagents="H₂O",
        ),
    ],
    energy_diagram=[
        ("반응물\n옥심", 0.0),
        ("양성자화", 3.0),
        ("[1,2]-이동\n전이 상태", 25.0),
        ("나이트릴리움", 12.0),
        ("생성물\n아마이드", -8.0),
    ],
)

# ─── Michael 첨가 (1,4-공역 첨가) ───────────────────────────────────────
# 대표: malonate + methyl vinyl ketone → 1,4-adduct

MECHANISMS["michael_addition"] = MechanismData(
    mechanism_type="michael_addition",
    title="Michael 1,4-공역 첨가",
    total_steps=3,
    overall_description=(
        "Michael 반응은 안정화된 카르보음이온(Michael donor)이 α,β-불포화 카르보닐의 "
        "β-위치를 1,4-공역 첨가하는 반응입니다. 전자가 4원자 경로(C→C=C-C=O)를 "
        "따라 이동하는 대표적인 긴 전자이동 반응입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="염기에 의한 enolate 형성 (Michael donor 활성화)",
            description=(
                "염기(NaOEt)가 활성 메틸렌의 alpha-H를 제거합니다.\n"
                "생성된 enolate는 안정화된 카르보음이온 → Michael donor."
            ),
            # CC(=O)CC(=O)C: acetylacetone (2,4-pentanedione)
            # C0-C1(=O2)-C3(H2)-C4(=O5)-C6
            reactant_smiles="CC(=O)CC(=O)C",
            product_smiles="CC(=O)[CH-]C(=O)C",
            arrows=[
                ArrowData("full", "lone_pair", "EtO⁻ (염기)",
                          "atom", "alpha-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=3),  # 외부→C(H)
                ArrowData("full", "bond", "C-H sigma",
                          "bond", "C=C enolate", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=1),  # C-H→enolate
            ],
            labels={"H": "alpha-H", "C": "→ enolate"},
            energy_label="enolate 형성",
            reagents="NaOEt (base)",
        ),
        MechanismStep(
            step_number=2,
            title="1,4-공역 첨가 (β-탄소 공격) — 긴 전자이동",
            description=(
                "Enolate의 카르보음이온이 MVK(methyl vinyl ketone)의 β-탄소를 공격.\n"
                "전자가 C→C=C-C=O 4원자 경로를 따라 이동합니다:\n"
                "  ①enolate C: → ②β-C → ③α-C → ④C=O (→ O⁻)\n"
                "이것이 '1,4-첨가'의 핵심: 전자가 공역계를 타고 이동합니다."
            ),
            # [CH2-]와 C=CC(=O)C (MVK)
            # enolate: C0(-)  MVK: C1=C2-C3(=O4)-C5
            reactant_smiles="[CH3-].C=CC(C)=O",
            product_smiles="CC=CC(C)=O",
            arrows=[
                # 긴 전자이동 경로: 4원자
                ArrowData("full", "lone_pair", "enolate C⁻",
                          "atom", "β-C (MVK)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=2),  # C⁻→β-C
                ArrowData("full", "pi_bond", "C=C pi (α-β)",
                          "bond", "C-C sigma 형성", "#FF9800", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # β=α → β-α
                ArrowData("full", "pi_bond", "C=O 재배열",
                          "atom", "O⁻ (enolate 산소)", "#1565C0", 0.4,
                          from_atom_idx=3, to_atom_idx=4),  # C=O → C-O⁻
            ],
            labels={"donor": "Michael donor", "β": "β-C (공격점)"},
            energy_label="1,4-첨가 (속도 결정)",
            reagents="",
            notes="전자 흐름: donor → β-C → α-C → O (4원자 경로). 교과서 1-4에디션 참고.",
        ),
        MechanismStep(
            step_number=3,
            title="양성자화 → Michael adduct",
            description=(
                "Enolate 산소가 양성자화되어 최종 Michael adduct가 됩니다."
            ),
            reactant_smiles="CC=CC(C)=O",
            product_smiles="CCCC(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (용매)",
                          "atom", "O⁻ → OH", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=4),
            ],
            labels={"O": "양성자화"},
            energy_label="발열",
            reagents="H₃O⁺",
        ),
    ],
    energy_diagram=[
        ("반응물\ndonor + MVK", 0.0),
        ("enolate", 5.0),
        ("1,4-첨가\n전이 상태", 15.0),
        ("enolate 중간체", 3.0),
        ("생성물\nMichael adduct", -8.0),
    ],
)

# ─── Curtius 전위 (acyl azide → isocyanate) ──────────────────────────────
# 대표: RCON₃ → R-N=C=O + N₂ (NCO 형성)

MECHANISMS["curtius"] = MechanismData(
    mechanism_type="curtius",
    title="Curtius 전위 (NCO 형성)",
    total_steps=2,
    overall_description=(
        "아실 아지드(RCON₃)가 열분해하여 나이트렌 중간체를 거쳐 "
        "이소시아네이트(R-N=C=O)를 생성합니다. N₂가 이탈하면서 "
        "알킬기가 C→N으로 1,2-이동합니다. CNO → NCO 전환의 대표적 반응."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="N₂ 이탈 + 1,2-알킬 이동 (동시, 협주)",
            description=(
                "열에 의해 아실 아지드가 분해합니다.\n"
                "C-N₃ 결합에서 N₂가 이탈하면서 동시에\n"
                "알킬기 R이 C→N으로 1,2-이동합니다.\n"
                "결과: R-N=C=O (이소시아네이트, NCO).\n"
                "C-N-N-N 구조가 N-C-O 구조로 재배열됩니다."
            ),
            # CC(=O)N=[N+]=[N-]: methyl acyl azide
            # C0-C1(=O2)-N3=N4+=N5-
            reactant_smiles="CC(=O)N=[N+]=[N-]",
            product_smiles="CN=C=O",
            arrows=[
                ArrowData("full", "bond", "R-C(=O) 결합",
                          "atom", "N (1,2-이동)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=3),  # C(R)→N
                ArrowData("full", "bond", "N-N₂ 결합",
                          "atom", "N₂ 이탈", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),  # N→N₂
                ArrowData("full", "lone_pair", "C=O 전자",
                          "bond", "C=N=C=O 형성", "#4CAF50", 0.4,
                          from_atom_idx=2, to_atom_idx=1),  # O→C(형성)
            ],
            labels={"R": "1,2-이동", "N₂": "이탈기", "NCO": "이소시아네이트"},
            energy_label="협주 전이 상태",
            reagents="Δ (열)",
            notes="CNO→NCO 재배열: 원래 C(=O)-N-N₂ 구조가 N=C=O로 변환",
        ),
        MechanismStep(
            step_number=2,
            title="이소시아네이트 + H₂O → 카르밤산 → 아민 + CO₂",
            description=(
                "이소시아네이트에 물이 첨가되면 불안정한 카르밤산이 형성.\n"
                "카르밤산이 자발적으로 탈카르복실화 → 아민 + CO₂."
            ),
            reactant_smiles="CN=C=O",
            product_smiles="CN",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C=O (친전자)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=2),  # H2O→C(NCO)
            ],
            labels={"H2O": "친핵체", "CO2": "이탈"},
            energy_label="가수분해",
            reagents="H₂O",
            notes="최종: R-NH₂ + CO₂ (1급 아민 합성)",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCON₃", 0.0),
        ("전이 상태\n[1,2]-이동", 28.0),
        ("RNCO\n이소시아네이트", -5.0),
        ("생성물\nRNH₂ + CO₂", -15.0),
    ],
)


# ─── [2+2] 고리화 첨가 (Photochemical) ────────────────────────────────────
MECHANISMS["cycloaddition_2_2"] = MechanismData(
    mechanism_type="cycloaddition_2_2",
    title="[2+2] 고리화 첨가 (광화학)",
    total_steps=1,
    overall_description=(
        "두 알켄이 자외선(hv) 조사 하에 [2+2] 고리화 첨가를 통해 "
        "사이클로부탄 유도체를 형성합니다. Woodward-Hoffmann 규칙에 의해 "
        "열적으로 금지, 광화학적으로 허용됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[2+2] 초면적 고리화 첨가 (광화학 협주 반응)",
            description=(
                "광여기(hv)된 알켄의 LUMO가 바닥상태 알켄의 HOMO와 상호작용.\n"
                "두 π 결합이 동시에 끊어지며 두 σ 결합 형성 → 사이클로부탄."
            ),
            reactant_smiles="C=C.C=C",
            product_smiles="C1CCC1",
            arrows=[
                ArrowData("full", "pi_bond", "알켄 1 π 전자",
                          "atom", "알켄 2 C", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=2),
                ArrowData("full", "pi_bond", "알켄 2 π 전자",
                          "atom", "알켄 1 C", "#1565C0", 0.5,
                          from_atom_idx=3, to_atom_idx=1),
            ],
            labels={"hv": "광화학적 허용"},
            energy_label="광여기 전이 상태",
            reagents="hν (UV)",
            notes="열적 금지: [π2s + π2s] suprafacial, 광화학 허용",
        ),
    ],
    energy_diagram=[
        ("반응물\n2 알켄", 0.0),
        ("S₁ 여기 상태", 85.0),
        ("TS", 75.0),
        ("생성물\n사이클로부탄", -5.0),
    ],
)

# ─── Cope 재배열 ───────────────────────────────────────────────────────────
MECHANISMS["cope_rearrangement"] = MechanismData(
    mechanism_type="cope_rearrangement",
    title="Cope [3,3]-시그마트로피 재배열",
    total_steps=1,
    overall_description=(
        "1,5-헥사디엔 골격이 열적 [3,3]-시그마트로피 재배열을 거쳐 "
        "σ 결합이 이동합니다. 의자형 전이 상태를 경유하며 "
        "suprafacial-suprafacial 과정입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[3,3]-시그마트로피 재배열 (의자형 TS)",
            description=(
                "C1-C6 σ 결합이 끊어지면서 C3-C4 새 σ 결합이 형성.\n"
                "동시에 π 결합 위치가 재배열됩니다.\n"
                "6원자 의자형 전이 상태를 경유하는 협주 반응."
            ),
            reactant_smiles="C=CCC=CC",
            product_smiles="CC=CCC=C",
            arrows=[
                ArrowData("full", "bond", "C1-C6 σ 결합",
                          "bond", "C1=C2 π 이동", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=5),
                ArrowData("full", "pi_bond", "C2=C3 π 전자",
                          "bond", "C3-C4 σ 형성", "#FF9800", 0.4,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "pi_bond", "C4=C5 π 전자",
                          "bond", "C5=C6 π 이동", "#1565C0", 0.4,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"TS": "의자형 6원자"},
            energy_label="[3,3] 협주 TS",
            reagents="Δ (150-250°C)",
        ),
    ],
    energy_diagram=[
        ("반응물\n1,5-헥사디엔", 0.0),
        ("의자형 TS", 33.5),
        ("생성물", -2.0),
    ],
)

# ─── Claisen 재배열 ───────────────────────────────────────────────────────
MECHANISMS["claisen_rearrangement"] = MechanismData(
    mechanism_type="claisen_rearrangement",
    title="Claisen [3,3]-시그마트로피 재배열",
    total_steps=1,
    overall_description=(
        "알릴 비닐 에터가 열적 [3,3]-시그마트로피 재배열을 거쳐 "
        "γ,δ-불포화 카르보닐 화합물로 변환됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[3,3]-시그마트로피 재배열 (O-allyl → C-allyl)",
            description=(
                "O-C(allyl) σ 결합이 끊어지면서 C-C 새 결합 형성.\n"
                "산소가 카르보닐(C=O)로 전환됩니다."
            ),
            reactant_smiles="C=COCC=C",
            product_smiles="C=CCC(=O)C",
            arrows=[
                ArrowData("full", "bond", "O-C(allyl) σ 결합",
                          "bond", "C=C → C=O 전환", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "pi_bond", "비닐 C=C π 전자",
                          "bond", "새 C-C σ 형성", "#FF9800", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "pi_bond", "알릴 C=C π 전자",
                          "bond", "π 재배열", "#1565C0", 0.4,
                          from_atom_idx=4, to_atom_idx=5),
            ],
            labels={"O": "→ C=O"},
            energy_label="[3,3] 협주 TS",
            reagents="Δ (150-200°C)",
        ),
    ],
    energy_diagram=[
        ("반응물\n알릴 비닐 에터", 0.0),
        ("TS", 30.0),
        ("생성물\nγ,δ-불포화 카르보닐", -15.0),
    ],
)

# ─── Suzuki-Miyaura 커플링 ────────────────────────────────────────────────
MECHANISMS["suzuki_coupling"] = MechanismData(
    mechanism_type="suzuki_coupling",
    title="Suzuki-Miyaura 교차 커플링",
    total_steps=3,
    overall_description=(
        "Pd(0) 촉매에 의한 교차 커플링 반응. "
        "Ar-X + Ar'-B(OH)₂ → Ar-Ar'. "
        "산화적 첨가 → 트랜스메탈화 → 환원적 제거 3단계 촉매 사이클."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가 (Oxidative Addition)",
            description=(
                "Pd(0)의 충만한 d-전자가 Ar-Br 결합의 sigma* 반결합 오비탈에 역공여.\n"
                "Ar-Br 결합이 끊어짐: 전자쌍이 재분배되어 Ar-Pd와 Pd-Br 두 새 결합 형성.\n"
                "Pd가 0가 → 2가로 산화됨 (전자 2개를 Ar-X 결합에 제공).\n"
                "결과: cis-[Ar-Pd(II)-Br(L)₂] 정사각 평면 착물 형성."
            ),
            reactant_smiles="c1ccccc1Br",
            product_smiles="c1ccccc1[Pd]Br",
            arrows=[
                ArrowData("full", "lone_pair", "Pd(0) d-전자",
                          "bond", "Ar-X σ* (반결합)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=6),
            ],
            labels={"Pd": "Pd(0)→Pd(II)"},
            energy_label="산화적 첨가",
            reagents="Pd(PPh₃)₄",
        ),
        MechanismStep(
            step_number=2,
            title="트랜스메탈화 (Transmetalation)",
            description=(
                "염기(Na₂CO₃)가 보론산을 활성화: Ar'-B(OH)₂ + OH⁻ → Ar'-B(OH)₃⁻ (보레이트).\n"
                "보레이트의 Ar'-B 결합이 끊어지고 Ar'-Pd 새 결합이 형성됩니다.\n"
                "동시에 Pd-Br 결합이 끊어짐 → Br⁻ 이탈.\n"
                "결과: Ar-Pd(II)-Ar' 디아릴 Pd 착물 + B(OH)₃ 부산물."
            ),
            reactant_smiles="c1ccccc1[Pd]Br",
            product_smiles="c1ccccc1[Pd]c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "Ar'-B σ 결합",
                          "atom", "Pd (트랜스메탈화)", "#FF9800", 0.4,
                          from_atom_idx=-1, to_atom_idx=7),
            ],
            labels={"B(OH)2": "→ B(OH)₃", "Pd": "Ar-Pd-Ar'"},
            energy_label="트랜스메탈화",
            reagents="Ar'B(OH)₂, Na₂CO₃",
        ),
        MechanismStep(
            step_number=3,
            title="환원적 제거 (Reductive Elimination)",
            description=(
                "Ar-Pd 결합과 Pd-Ar' 결합이 동시에 끊어짐: 각 결합의 전자쌍이 재분배.\n"
                "두 아릴기 사이에 새 Ar-Ar' sigma 결합이 형성됩니다.\n"
                "Pd(II) → Pd(0)로 환원: 2개 전자를 되돌려 받음.\n"
                "Pd(0) 촉매가 재생되어 다음 사이클에 재사용됩니다."
            ),
            reactant_smiles="c1ccccc1[Pd]c1ccccc1",
            product_smiles="c1ccc(-c2ccccc2)cc1",
            arrows=[
                ArrowData("full", "bond", "Ar-Pd σ 결합",
                          "bond", "Ar-Ar' σ 형성", "#4CAF50", 0.4,
                          from_atom_idx=0, to_atom_idx=8),
            ],
            labels={"Pd": "Pd(II)→Pd(0) 재생"},
            energy_label="환원적 제거",
            reagents="",
            notes="촉매 사이클 완료 → Pd(0) 재생",
        ),
    ],
    energy_diagram=[
        ("Pd(0) + ArX\n+ Ar'B(OH)₂", 0.0),
        ("산화적 첨가\nAr-Pd(II)-X", 12.0),
        ("트랜스메탈화\nAr-Pd(II)-Ar'", 8.0),
        ("환원적 제거\nTS", 15.0),
        ("Ar-Ar'\n+ Pd(0)", -10.0),
    ],
)

# ─── Heck 반응 ─────────────────────────────────────────────────────────────
MECHANISMS["heck_reaction"] = MechanismData(
    mechanism_type="heck_reaction",
    title="Heck 반응 (Mizoroki-Heck)",
    total_steps=3,
    overall_description=(
        "Pd(0) 촉매에 의한 아릴 할로겐화물과 알켄의 커플링. "
        "Ar-X + CH₂=CHR → Ar-CH=CHR. "
        "산화적 첨가 → syn-삽입 → β-H 제거 3단계."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가 (Oxidative Addition)",
            description=(
                "Pd(0)의 d-전자가 Ar-Br sigma* 반결합 오비탈에 역공여합니다.\n"
                "Ar-Br 결합 끊어짐 → Ar-Pd, Pd-Br 두 새 결합 형성.\n"
                "Pd: 0가 → 2가 산화 (전자 2개 제공). Ar-Pd(II)-Br 착물 생성."
            ),
            reactant_smiles="c1ccccc1Br",
            product_smiles="c1ccccc1[Pd]Br",
            arrows=[
                ArrowData("full", "lone_pair", "Pd(0) d-전자",
                          "bond", "Ar-X σ*", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=6),
            ],
            labels={"Pd": "Pd(0)→Pd(II)"},
            energy_label="산화적 첨가",
            reagents="Pd(OAc)₂ / PPh₃",
        ),
        MechanismStep(
            step_number=2,
            title="syn-삽입 (Migratory Insertion)",
            description=(
                "알켄의 pi-전자가 Pd에 배위 → pi-착물 형성.\n"
                "Ar-Pd 결합이 끊어지면서 Ar이 알켄 탄소에 새 C-C 결합을 형성.\n"
                "동시에 Pd가 다른 알켄 탄소에 새 Pd-C 결합 형성 (syn-삽입).\n"
                "Ar과 Pd가 알켄의 같은 면에서 첨가 → syn 입체화학."
            ),
            reactant_smiles="c1ccccc1[Pd]Br.C=C",
            product_smiles="c1ccccc1CC[Pd]Br",
            arrows=[
                ArrowData("full", "pi_bond", "알켄 π 전자",
                          "atom", "Pd (syn-삽입)", "#FF9800", 0.4,
                          from_atom_idx=8, to_atom_idx=7),
                ArrowData("full", "bond", "Ar-Pd σ",
                          "atom", "C (삽입)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=8),
            ],
            labels={"Pd": "syn-삽입"},
            energy_label="삽입 단계",
            reagents="",
        ),
        MechanismStep(
            step_number=3,
            title="β-수소 제거 (β-Hydride Elimination)",
            description=(
                "Pd-C 결합의 beta-위치 C-H 결합이 끊어짐: H가 Pd로 이동(beta-수소 제거).\n"
                "동시에 Pd-C 결합 끊어짐 → C=C pi-결합 형성 (알켄 생성물).\n"
                "Pd-H 중간체 형성 후, Et₃N(염기)가 H를 제거 → Pd(0) 재생.\n"
                "촉매 사이클 완료: Pd(0)이 다음 반응에 재사용됩니다."
            ),
            reactant_smiles="c1ccccc1CC[Pd]Br",
            product_smiles="c1ccccc1/C=C",
            arrows=[
                ArrowData("full", "bond", "C-H σ (β-H)",
                          "atom", "Pd (β-H 제거)", "#4CAF50", 0.4,
                          from_atom_idx=8, to_atom_idx=9),
                ArrowData("full", "bond", "Pd-C σ",
                          "bond", "C=C π 형성", "#1565C0", 0.3,
                          from_atom_idx=9, to_atom_idx=7),
            ],
            labels={"Pd": "β-H 제거 → Pd(0)"},
            energy_label="β-H 제거",
            reagents="Et₃N (base)",
            notes="촉매 사이클 완료 → Pd(0) + Et₃N·HBr",
        ),
    ],
    energy_diagram=[
        ("Pd(0) + ArX\n+ 알켄", 0.0),
        ("산화적 첨가", 12.0),
        ("syn-삽입", 18.0),
        ("β-H 제거", 10.0),
        ("Ar-CH=CHR\n+ Pd(0)", -8.0),
    ],
)

# ─── 노르보르넨 친전자 첨가 ──────────────────────────────────────────────
MECHANISMS["norbornene_addition"] = MechanismData(
    mechanism_type="norbornene_addition",
    title="노르보르넨 친전자 첨가 (exo 선택적)",
    total_steps=2,
    overall_description=(
        "노르보르넨(다리걸침 알켄)에 대한 친전자 첨가 반응. "
        "비고전적 카르보카티온 안정화(σ-참여)로 인해 exo 공격이 선호됨."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친전자 공격 → 비고전적 카르보카티온",
            description=(
                "H⁺(또는 Br⁺)가 노르보르넨 이중결합을 공격.\n"
                "exo 면에서 접근 → 비고전적 카보카티온 생성.\n"
                "C7 다리 σ 결합의 전자가 C⁺를 안정화(σ-참여)."
            ),
            reactant_smiles="C1CC2CC1C=C2",
            product_smiles="C1CC2CC1[CH+]C2",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (친전자)",
                          "pi_bond", "C=C π 결합", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=5),
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "C → C⁺", "#1565C0", 0.4,
                          from_atom_idx=5, to_atom_idx=6),
            ],
            labels={"C+": "비고전적 C⁺\n(σ-참여 안정화)"},
            energy_label="전이 상태",
            reagents="HBr",
        ),
        MechanismStep(
            step_number=2,
            title="exo 면 친핵체 공격",
            description=(
                "Br⁻가 exo 면에서 카르보카티온을 공격.\n"
                "endo 면은 C7 다리에 의해 차폐 → exo 생성물."
            ),
            reactant_smiles="C1CC2CC1[CH+]C2",
            product_smiles="C1CC2CC1C(Br)C2",
            arrows=[
                ArrowData("full", "lone_pair", "Br⁻ 론페어",
                          "atom", "C⁺ (exo 공격)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=5),
            ],
            labels={"Br": "exo 공격"},
            energy_label="exo 생성물",
            reagents="Br⁻",
        ),
    ],
    energy_diagram=[
        ("반응물\n노르보르넨", 0.0),
        ("비고전적 C⁺", 12.0),
        ("exo 생성물", -8.0),
    ],
)

# ─── 다치환 방향족 EAS ────────────────────────────────────────────────────
MECHANISMS["eas_multi_substituted"] = MechanismData(
    mechanism_type="eas_multi_substituted",
    title="다치환 방향족 EAS (배향 효과)",
    total_steps=2,
    overall_description=(
        "이미 치환기가 있는 방향족 고리의 EAS. "
        "전자 주개(EDG): ortho/para 배향, 전자 끌개(EWG): meta 배향. "
        "두 치환기 충돌 시 '활성화 치환기 우선' 규칙 적용."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친전자체 공격 → σ-complex (Wheland 중간체)",
            description=(
                "친전자체(E⁺)가 방향족 고리를 공격.\n"
                "기존 치환기의 배향 효과에 따라 공격 위치 결정:\n"
                "  - EDG(OH, NH₂, OMe): ortho/para 활성화\n"
                "  - EWG(NO₂, CF₃, COR): meta 비활성화\n"
                "공명 안정화된 σ-complex(Wheland) 중간체 형성."
            ),
            reactant_smiles="c1cc(O)ccc1",
            product_smiles="C1(O)=CC(Br)=CC=C1",
            arrows=[
                ArrowData("full", "pi_bond", "방향족 π 전자",
                          "atom", "E⁺ (친전자)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=-1),
            ],
            labels={"E+": "친전자체", "sigma": "σ-complex"},
            energy_label="σ-complex 형성",
            reagents="E⁺ (Br₂/FeBr₃)",
        ),
        MechanismStep(
            step_number=2,
            title="양성자 이탈 → 방향족성 회복",
            description=(
                "σ-complex에서 H⁺가 이탈하여 방향족성 회복.\n"
                "치환 생성물이 형성됩니다."
            ),
            reactant_smiles="C1(O)=CC(Br)=CC=C1",
            product_smiles="c1cc(O)cc(Br)c1",
            arrows=[
                ArrowData("full", "bond", "C-H σ 결합",
                          "atom", "Base (H⁺ 제거)", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=-1),
            ],
            labels={"H": "→ HBr (이탈)"},
            energy_label="방향족성 회복 (발열)",
            reagents="FeBr₃ (base)",
        ),
    ],
    energy_diagram=[
        ("반응물\n치환 방향족", 0.0),
        ("σ-complex\nWheland 중간체", 15.0),
        ("생성물\n다치환 방향족", -10.0),
    ],
)


def get_mechanism(mechanism_type: str) -> Optional[MechanismData]:
    """메커니즘 타입으로 데이터 조회"""
    return MECHANISMS.get(mechanism_type)


def get_available_mechanisms() -> List[str]:
    """사용 가능한 메커니즘 타입 목록"""
    return list(MECHANISMS.keys())
