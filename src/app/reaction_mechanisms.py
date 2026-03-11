# reaction_mechanisms.py (v1.0 - Organic Reaction Mechanism Data)
"""
ChemGrid: 유기합성반응 메커니즘 단계별 데이터
- 각 반응 유형의 전자 이동 단계를 정의
- 곡선 화살표 렌더링 데이터 포함
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
# ============================================================================

MECHANISMS: Dict[str, MechanismData] = {}

# ─── SN2 ────────────────────────────────────────────────────────────────────

MECHANISMS["sn2"] = MechanismData(
    mechanism_type="sn2",
    title="SN2 (이분자 친핵성 치환)",
    total_steps=1,
    overall_description=(
        "SN2는 1단계 동시 반응입니다. 친핵체가 이탈기의 반대편(후면)에서 "
        "탄소를 공격하면서 이탈기가 동시에 이탈합니다. "
        "전이 상태에서 탄소는 5배위로 sp²-유사 기하를 가지며, "
        "결과적으로 입체배치가 반전(Walden 전환)됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵체 후면 공격 + 이탈기 이탈 (동시)",
            description=(
                "친핵체(Nu⁻)의 론페어가 탄소의 σ* 반결합 오비탈을 공격합니다.\n"
                "전이 상태 [Nu···C···X]‡에서 탄소는 5배위(오각쌍추)를 형성합니다.\n"
                "이탈기(X⁻)가 이탈하면서 탄소의 입체배치가 반전됩니다."
            ),
            reactant_smiles="[Nu-].C([H])([R1])([R2])X",
            product_smiles="[Nu]C([H])([R1])([R2]).[X-]",
            arrows=[
                ArrowData("full", "lone_pair", "Nu⁻ 론페어",
                          "atom", "C-X σ* 오비탈", "#E53935", 0.4),
                ArrowData("full", "bond", "C-X σ 결합",
                          "atom", "X (이탈기)", "#1565C0", 0.3),
            ],
            labels={"Nu": "Nu⁻ (친핵체)", "C": "δ+ (친전자 탄소)", "X": "X (이탈기)"},
            is_transition_state=True,
            energy_label="ΔG‡ = 전이 상태",
            notes="반응 속도 = k[Nu⁻][R-X] (2차 반응)",
        ),
    ],
    energy_diagram=[
        ("반응물\nNu⁻ + R-X", 0.0),
        ("[Nu···C···X]‡\n전이 상태", 20.0),
        ("생성물\nNu-R + X⁻", -5.0),
    ],
)

# ─── SN1 ────────────────────────────────────────────────────────────────────

MECHANISMS["sn1"] = MechanismData(
    mechanism_type="sn1",
    title="SN1 (단분자 친핵성 치환)",
    total_steps=2,
    overall_description=(
        "SN1은 2단계 반응입니다. 먼저 이탈기가 이탈하여 카르보카티온 중간체를 형성하고, "
        "그 후 친핵체가 카르보카티온을 공격합니다. "
        "3차 탄소에서 유리하며, 극성 양성자성 용매가 이탈기의 안정화를 돕습니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이탈기 이탈 → 카르보카티온 형성 (느린 단계, 속도 결정)",
            description=(
                "이탈기(X)가 결합 전자쌍을 가지고 이탈합니다.\n"
                "평면 삼각형 카르보카티온(sp²) 중간체가 형성됩니다.\n"
                "이것이 속도 결정 단계(Rate-Determining Step)입니다."
            ),
            reactant_smiles="C([R1])([R2])([R3])X",
            product_smiles="[C+]([R1])([R2])([R3]).[X-]",
            arrows=[
                ArrowData("full", "bond", "C-X σ 결합",
                          "atom", "X (이탈기)", "#E53935", 0.3),
            ],
            labels={"C": "→ C⁺ (카르보카티온)", "X": "X⁻ (이탈기)"},
            energy_label="ΔG‡₁ (속도 결정 단계)",
            notes="속도 = k[R-X] (1차 반응). 카르보카티온 안정성: 3° > 2° > 1°",
        ),
        MechanismStep(
            step_number=2,
            title="친핵체 공격 (빠른 단계)",
            description=(
                "친핵체(Nu)가 평면 카르보카티온의 양쪽에서 공격합니다.\n"
                "양면 공격 → 라세미 혼합물 생성 (R과 S 동량).\n"
                "실제로는 이온쌍 효과로 약간의 반전 선호 가능."
            ),
            reactant_smiles="[C+]([R1])([R2])([R3]).Nu",
            product_smiles="NuC([R1])([R2])([R3])",
            arrows=[
                ArrowData("full", "lone_pair", "Nu 론페어",
                          "atom", "C⁺ (빈 p 오비탈)", "#4CAF50", 0.4),
            ],
            labels={"C": "C⁺ (sp², 평면)", "Nu": "Nu (친핵체)"},
            energy_label="ΔG‡₂ (낮은 에너지 장벽)",
        ),
    ],
    energy_diagram=[
        ("반응물\nR-X", 0.0),
        ("[R···X]‡₁\n전이 상태 1", 25.0),
        ("R⁺ + X⁻\n카르보카티온", 15.0),
        ("[R···Nu]‡₂\n전이 상태 2", 18.0),
        ("생성물\nR-Nu", -3.0),
    ],
)

# ─── E2 ─────────────────────────────────────────────────────────────────────

MECHANISMS["e2"] = MechanismData(
    mechanism_type="e2",
    title="E2 (이분자 제거)",
    total_steps=1,
    overall_description=(
        "E2는 1단계 동시 반응입니다. 강한 염기가 β-수소를 제거하면서 "
        "이탈기가 동시에 이탈합니다. C-H와 C-X가 anti-periplanar 배향이어야 합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="β-수소 제거 + 이탈기 이탈 + π-결합 형성 (동시)",
            description=(
                "염기(B⁻)가 β-수소를 제거합니다.\n"
                "C-H 결합 전자쌍이 C=C π-결합을 형성합니다.\n"
                "동시에 C-X 결합 전자쌍이 이탈기(X⁻)로 이동합니다.\n"
                "Anti-periplanar 기하 필수 (Newman 투영: H와 X가 anti)."
            ),
            reactant_smiles="B[H-].Cα([H])(R)-Cβ(R')(R'')X",
            product_smiles="BH.R(R)C=C(R')(R'').[X-]",
            arrows=[
                ArrowData("full", "lone_pair", "B⁻ (염기)",
                          "atom", "β-H", "#E53935", 0.4),
                ArrowData("full", "bond", "Cβ-H σ 결합",
                          "bond", "Cα=Cβ π-결합 형성", "#4CAF50", 0.3),
                ArrowData("full", "bond", "Cα-X σ 결합",
                          "atom", "X⁻ (이탈기)", "#1565C0", 0.3),
            ],
            labels={"B": "B⁻ (염기)", "Hβ": "β-H", "Cα": "Cα", "Cβ": "Cβ", "X": "X (이탈기)"},
            energy_label="ΔG‡ = 전이 상태",
            notes="Zaitsev 법칙: 더 치환된 알켄이 주생성물 (안정한 이중결합)",
        ),
    ],
    energy_diagram=[
        ("반응물\nB⁻ + R-X", 0.0),
        ("[B···H-C-C···X]‡", 22.0),
        ("생성물\nBH + C=C + X⁻", -8.0),
    ],
)

# ─── E1 ─────────────────────────────────────────────────────────────────────

MECHANISMS["e1"] = MechanismData(
    mechanism_type="e1",
    title="E1 (단분자 제거)",
    total_steps=2,
    overall_description="SN1과 같은 1단계(카르보카티온 형성) 후, 염기가 β-수소를 제거합니다.",
    steps=[
        MechanismStep(
            step_number=1,
            title="이탈기 이탈 → 카르보카티온 (속도 결정 단계)",
            description="SN1과 동일한 1단계. 이탈기가 결합 전자쌍을 가지고 이탈.",
            reactant_smiles="C([R1])([R2])([R3])X",
            product_smiles="[C+]([R1])([R2])([R3]).[X-]",
            arrows=[
                ArrowData("full", "bond", "C-X σ 결합",
                          "atom", "X⁻", "#E53935", 0.3),
            ],
            labels={"C": "→ C⁺", "X": "X⁻"},
            energy_label="ΔG‡₁ (속도 결정)",
        ),
        MechanismStep(
            step_number=2,
            title="β-수소 제거 → 알켄 형성",
            description=(
                "약한 염기 또는 용매가 β-수소를 제거합니다.\n"
                "C-H 결합 전자쌍이 C=C 이중결합을 형성합니다."
            ),
            reactant_smiles="[C+]([R1])([R2])-C([H])(R3)(R4)",
            product_smiles="R1(R2)C=C(R3)(R4)",
            arrows=[
                ArrowData("full", "lone_pair", "B (염기/용매)",
                          "atom", "β-H", "#E53935", 0.4),
                ArrowData("full", "bond", "Cβ-H σ 결합",
                          "bond", "C=C π-결합", "#4CAF50", 0.3),
            ],
            labels={"B": "B (염기)", "Hβ": "β-H"},
            energy_label="ΔG‡₂ (낮은 장벽)",
        ),
    ],
    energy_diagram=[
        ("반응물\nR-X", 0.0),
        ("[R···X]‡₁", 25.0),
        ("R⁺ + X⁻", 15.0),
        ("[B···H-C-C⁺]‡₂", 17.0),
        ("생성물\nBH + C=C", -5.0),
    ],
)

# ─── 친전자 첨가 ─────────────────────────────────────────────────────────────

MECHANISMS["electrophilic_addition"] = MechanismData(
    mechanism_type="electrophilic_addition",
    title="친전자 첨가 (Markovnikov)",
    total_steps=2,
    overall_description=(
        "알켄의 π-전자가 친전자체(H⁺)를 공격하여 카르보카티온을 형성하고, "
        "이어서 친핵체가 공격합니다. Markovnikov 법칙에 따라 "
        "수소는 수소가 더 많은 탄소에, 할로겐은 더 치환된 탄소에 결합합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="π-결합이 H⁺ 공격 → 카르보카티온",
            description=(
                "알켄의 π-전자쌍이 H⁺(프로톤)을 공격합니다.\n"
                "Markovnikov: H는 H가 더 많은 탄소에 결합.\n"
                "→ 더 안정한 카르보카티온 형성 (3° > 2° > 1°)."
            ),
            reactant_smiles="R1R2C=CR3R4.H-X",
            product_smiles="R1R2(H)C-[C+](R3)(R4).[X-]",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 결합",
                          "atom", "H⁺ (프로톤)", "#E53935", 0.4),
            ],
            labels={"C=C": "π-결합 (HOMO)", "H": "H⁺ (친전자체)"},
            energy_label="ΔG‡₁",
        ),
        MechanismStep(
            step_number=2,
            title="친핵체(X⁻) 공격 → 생성물",
            description="할로겐 음이온(X⁻)이 카르보카티온을 공격하여 최종 생성물 형성.",
            reactant_smiles="R1R2(H)C-[C+](R3)(R4).[X-]",
            product_smiles="R1R2(H)C-C(X)(R3)(R4)",
            arrows=[
                ArrowData("full", "negative_charge", "X⁻",
                          "atom", "C⁺", "#4CAF50", 0.3),
            ],
            labels={"C": "C⁺", "X": "X⁻ (친핵체)"},
            energy_label="ΔG‡₂ (낮은 장벽)",
        ),
    ],
    energy_diagram=[
        ("반응물\nC=C + HX", 0.0),
        ("전이 상태 1", 15.0),
        ("카르보카티온\n+ X⁻", 10.0),
        ("전이 상태 2", 12.0),
        ("생성물\nC-C(H)(X)", -10.0),
    ],
)

# ─── 친핵 첨가 (카르보닐) ─────────────────────────────────────────────────

MECHANISMS["nucleophilic_addition"] = MechanismData(
    mechanism_type="nucleophilic_addition",
    title="친핵 첨가 (카르보닐)",
    total_steps=2,
    overall_description=(
        "친핵체가 카르보닐 탄소(δ+)를 공격하여 사면체 알콕사이드 중간체를 형성합니다. "
        "이후 양성자화로 알코올이 생성됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵체 → 카르보닐 탄소 공격",
            description=(
                "친핵체(Nu⁻)의 론페어가 카르보닐 C(δ+)의 π* 오비탈을 공격합니다.\n"
                "C=O π-결합이 끊어지면서 전자쌍이 산소로 이동 → 알콕사이드(O⁻) 형성."
            ),
            reactant_smiles="[Nu-].R1C(=O)R2",
            product_smiles="R1C([Nu])([O-])R2",
            arrows=[
                ArrowData("full", "lone_pair", "Nu⁻ 론페어",
                          "atom", "C=O (δ+ 탄소)", "#E53935", 0.4),
                ArrowData("full", "pi_bond", "C=O π 결합",
                          "atom", "O (론페어로)", "#1565C0", 0.3),
            ],
            labels={"Nu": "Nu⁻", "C": "δ+ (sp² → sp³)", "O": "→ O⁻"},
            energy_label="ΔG‡",
        ),
        MechanismStep(
            step_number=2,
            title="양성자화 → 알코올",
            description="알콕사이드(O⁻)가 양성자(H⁺)를 받아 알코올(-OH)이 됩니다.",
            reactant_smiles="R1C([Nu])([O-])R2.H+",
            product_smiles="R1C([Nu])([OH])R2",
            arrows=[
                ArrowData("full", "lone_pair", "O⁻",
                          "atom", "H⁺", "#4CAF50", 0.3),
            ],
            labels={"O": "O⁻ → OH"},
            energy_label="발열 (안정화)",
        ),
    ],
    energy_diagram=[
        ("반응물\nNu⁻ + C=O", 0.0),
        ("전이 상태", 12.0),
        ("알콕사이드\n중간체", 5.0),
        ("생성물\nNu-C-OH", -15.0),
    ],
)

# ─── EAS ─────────────────────────────────────────────────────────────────────

MECHANISMS["eas"] = MechanismData(
    mechanism_type="eas",
    title="친전자 방향족 치환 (EAS)",
    total_steps=2,
    overall_description=(
        "방향족 고리의 π-전자가 친전자체를 공격하여 σ-complex(아레니움 이온)를 형성합니다. "
        "이후 양성자 이탈로 방향족성이 회복됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="π-공격 → σ-complex (아레니움 이온) 형성",
            description=(
                "방향족 π-전자가 친전자체(E⁺)를 공격합니다.\n"
                "방향족성이 일시적으로 깨지면서 σ-complex(Wheland 중간체) 형성.\n"
                "양전하가 고리 위에 비편재화됩니다."
            ),
            reactant_smiles="c1ccccc1.E+",
            product_smiles="σ-complex [ArHE]+",
            arrows=[
                ArrowData("full", "pi_bond", "Ar π-전자",
                          "atom", "E⁺ (친전자체)", "#E53935", 0.5),
            ],
            labels={"Ar": "방향족 (HOMO)", "E": "E⁺ (친전자체)"},
            energy_label="ΔG‡₁ (속도 결정)",
            notes="σ-complex에서 양전하는 ortho/para 위치에 비편재화",
        ),
        MechanismStep(
            step_number=2,
            title="양성자 이탈 → 방향족성 회복",
            description=(
                "σ-complex에서 H⁺가 이탈하면서 방향족성이 회복됩니다.\n"
                "이 단계는 발열반응이며 빠릅니다."
            ),
            reactant_smiles="σ-complex [ArHE]+",
            product_smiles="c1ccc(E)cc1.H+",
            arrows=[
                ArrowData("full", "bond", "C-H σ 결합",
                          "atom", "B (염기)", "#4CAF50", 0.3),
            ],
            labels={"H": "H⁺ (이탈)", "E": "E (치환됨)"},
            energy_label="발열 (방향족성 회복)",
        ),
    ],
    energy_diagram=[
        ("반응물\nArH + E⁺", 0.0),
        ("전이 상태 1", 20.0),
        ("σ-complex\n[ArHE]⁺", 15.0),
        ("전이 상태 2", 16.0),
        ("생성물\nArE + H⁺", -5.0),
    ],
)

# ─── 에스터화 ─────────────────────────────────────────────────────────────────

MECHANISMS["esterification"] = MechanismData(
    mechanism_type="esterification",
    title="Fischer 에스터화",
    total_steps=3,
    overall_description=(
        "산 촉매 하에서 카르복실산과 알코올이 반응하여 에스터와 물을 생성합니다. "
        "평형 반응이므로 물을 제거하면 반응이 진행됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="카르보닐 양성자화 → 친전자성 증가",
            description="산 촉매(H⁺)가 카르보닐 산소를 양성자화하여 C=O를 더 친전자적으로 만듦.",
            reactant_smiles="RC(=O)OH.H+",
            product_smiles="RC(=[OH+])OH",
            arrows=[
                ArrowData("full", "lone_pair", "C=O 론페어",
                          "atom", "H⁺", "#E53935", 0.3),
            ],
            labels={"O": "→ OH⁺", "C": "더 δ+"},
            energy_label="산 촉매",
        ),
        MechanismStep(
            step_number=2,
            title="알코올 친핵 공격 → 사면체 중간체",
            description="알코올(R'OH)의 론페어가 활성화된 카르보닐 C를 공격.",
            reactant_smiles="RC(=[OH+])OH.R'OH",
            product_smiles="RC(OH)(OH)(OR').[H+]",
            arrows=[
                ArrowData("full", "lone_pair", "R'OH 론페어",
                          "atom", "C (δ+)", "#4CAF50", 0.4),
            ],
            labels={"R'OH": "친핵체", "C": "sp² → sp³"},
            energy_label="ΔG‡",
        ),
        MechanismStep(
            step_number=3,
            title="물 이탈 → 에스터 생성",
            description="양성자 전달 후 물이 이탈하여 에스터가 생성.",
            reactant_smiles="RC(OH)(OH)(OR')",
            product_smiles="RC(=O)(OR').H2O",
            arrows=[
                ArrowData("full", "lone_pair", "O (이탈하는 OH)",
                          "atom", "H⁺", "#1565C0", 0.3),
                ArrowData("full", "bond", "C-OH",
                          "atom", "H2O (이탈)", "#E53935", 0.3),
            ],
            labels={"OH": "→ H2O", "C": "sp³ → sp²"},
            energy_label="ΔG° ≈ 0 (평형)",
            notes="Le Chatelier: 물 제거 또는 알코올 과량으로 평형 이동",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOOH + R'OH", 0.0),
        ("양성자화", 3.0),
        ("전이 상태", 15.0),
        ("사면체 중간체", 8.0),
        ("생성물\nRCOOR' + H2O", 1.0),
    ],
)

# ─── Diels-Alder ─────────────────────────────────────────────────────────────

MECHANISMS["diels_alder"] = MechanismData(
    mechanism_type="diels_alder",
    title="Diels-Alder [4+2] 고리화 첨가",
    total_steps=1,
    overall_description=(
        "디엔(4π)과 디에노필(2π)이 동시 [4+2] 고리화 첨가 반응을 합니다. "
        "단일 전이 상태를 거치며, 6원 고리가 형성됩니다. "
        "열허용(thermally allowed) 페리사이클릭 반응입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[4+2] 동시 고리화 — 6원 고리 형성",
            description=(
                "디엔의 HOMO와 디에노필의 LUMO가 suprafacial 중첩합니다.\n"
                "6개의 전자가 동시에 재배열되며 2개의 새 σ-결합이 형성됩니다.\n"
                "Endo 법칙: 2차 오비탈 중첩으로 endo 생성물이 선호됩니다."
            ),
            reactant_smiles="C=C-C=C.C=C",
            product_smiles="C1C=CCC1C",
            arrows=[
                ArrowData("full", "pi_bond", "디엔 C1-C2 π",
                          "atom", "디에노필 C5", "#E53935", 0.5),
                ArrowData("full", "pi_bond", "디에노필 C5-C6 π",
                          "bond", "새 σ-결합", "#4CAF50", 0.5),
                ArrowData("full", "pi_bond", "디엔 C3-C4 π",
                          "atom", "디에노필 C6", "#1565C0", 0.5),
            ],
            labels={"diene": "디엔 (HOMO, 4π)", "dienophile": "디에노필 (LUMO, 2π)"},
            energy_label="ΔG‡ (동시 전이 상태)",
            notes="Woodward-Hoffmann: 열허용 [4s+2s]. syn-addition으로 입체화학 보존.",
        ),
    ],
    energy_diagram=[
        ("반응물\n디엔 + 디에노필", 0.0),
        ("[4+2] 전이 상태", 18.0),
        ("생성물\n사이클로헥센", -25.0),
    ],
)

# ─── 산화 ─────────────────────────────────────────────────────────────────────

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
            title="크로메이트 에스터 형성",
            description="알코올이 산화제(CrO3, PCC 등)와 에스터를 형성합니다.",
            reactant_smiles="RCH2OH.[Cr]",
            product_smiles="RCH2-O-[Cr]",
            arrows=[
                ArrowData("full", "lone_pair", "OH 론페어",
                          "atom", "Cr(VI)", "#E53935", 0.3),
            ],
            labels={"O": "알코올 O", "Cr": "Cr(VI) → Cr(IV)"},
            energy_label="에스터 형성",
        ),
        MechanismStep(
            step_number=2,
            title="E2-유사 제거 → 알데히드",
            description=(
                "염기가 α-수소를 제거하면서 Cr 이탈기가 동시에 이탈.\n"
                "결과: C=O 이중결합 형성 → 알데히드."
            ),
            reactant_smiles="RCH2-O-[Cr]",
            product_smiles="RC(=O)H.[Cr(IV)]",
            arrows=[
                ArrowData("full", "lone_pair", "B⁻ (염기)",
                          "atom", "α-H", "#E53935", 0.4),
                ArrowData("full", "bond", "C-H σ",
                          "bond", "C=O π", "#4CAF50", 0.3),
                ArrowData("full", "bond", "O-Cr",
                          "atom", "Cr(IV)", "#1565C0", 0.3),
            ],
            labels={"H": "α-H", "Cr": "이탈기"},
            energy_label="E2-유사",
            notes="PCC: 여기서 정지. KMnO4: 알데히드가 다시 산화되어 카르복실산까지 진행.",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCH2OH", 0.0),
        ("크로메이트 에스터", 5.0),
        ("전이 상태", 15.0),
        ("알데히드\nRCHO", -10.0),
    ],
)

# ─── 아마이드화 ─────────────────────────────────────────────────────────────

MECHANISMS["amidation"] = MechanismData(
    mechanism_type="amidation",
    title="아마이드 결합 형성",
    total_steps=2,
    overall_description="아실 할로겐화물 또는 활성화된 카르복실산에 아민이 친핵 공격하여 아마이드를 형성합니다.",
    steps=[
        MechanismStep(
            step_number=1,
            title="아민의 친핵 공격 → 사면체 중간체",
            description="아민(R'NH2)의 론페어가 아실 탄소를 공격합니다.",
            reactant_smiles="RC(=O)X.R'NH2",
            product_smiles="RC(OH)(NHR')(X).-",
            arrows=[
                ArrowData("full", "lone_pair", "NH2 론페어",
                          "atom", "C=O (δ+)", "#E53935", 0.4),
            ],
            labels={"N": "친핵체", "C": "δ+"},
            energy_label="ΔG‡",
        ),
        MechanismStep(
            step_number=2,
            title="이탈기 이탈 → 아마이드",
            description="사면체 중간체에서 이탈기(X⁻)가 이탈하여 아마이드 생성.",
            reactant_smiles="RC(OH)(NHR')(X)",
            product_smiles="RC(=O)(NHR').[X-]",
            arrows=[
                ArrowData("full", "bond", "C-X σ",
                          "atom", "X⁻", "#1565C0", 0.3),
                ArrowData("full", "lone_pair", "N 론페어",
                          "bond", "C=O 회복", "#4CAF50", 0.3),
            ],
            labels={"X": "이탈기", "N": "아마이드 N"},
            energy_label="발열",
        ),
    ],
    energy_diagram=[
        ("반응물", 0.0),
        ("전이 상태", 15.0),
        ("사면체 중간체", 8.0),
        ("생성물\n아마이드 + HX", -12.0),
    ],
)


def get_mechanism(mechanism_type: str) -> Optional[MechanismData]:
    """메커니즘 타입으로 데이터 조회"""
    return MECHANISMS.get(mechanism_type)


def get_available_mechanisms() -> List[str]:
    """사용 가능한 메커니즘 타입 목록"""
    return list(MECHANISMS.keys())
