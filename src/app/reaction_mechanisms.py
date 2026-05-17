# reaction_mechanisms.py (v2.1 - Organic Reaction Mechanism Data + xTB Energy)
"""
ChemGrid: 유기합성반응 메커니즘 단계별 데이터
- 각 반응 유형의 전자 이동 단계를 정의
- 곡선 화살표 렌더링 데이터 포함
- v2.0: 모든 SMILES를 RDKit 파싱 가능한 유효 SMILES로 교체
        ArrowData에 from_atom_idx/to_atom_idx 추가하여 정확한 원자 매칭
- v2.1: compute_mechanism_energies() — xTB GFN2-xTB single-point 에너지로
        하드코딩 에너지 다이어그램 대체 (on-demand, 실패 시 기존값 유지)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class ArrowData:
    """곡선 화살표 렌더링 데이터"""
    arrow_type: str          # "full" (2전자), "half" (1전자/라디칼), "retrosynthetic" (역합성)
    from_type: str           # "lone_pair", "bond", "pi_bond", "negative_charge"
    from_label: str          # 시작 위치 설명 (렌더링용)
    to_type: str             # "atom", "bond", "antibonding"
    to_label: str            # 끝 위치 설명
    color: str = "#E53935"   # 화살표 색상 (기본: 빨강)
    curvature: float = 0.3   # 곡률 (0=직선, 1=반원)
    from_atom_idx: int = -1  # 시작 원자 인덱스 (-1=자동 매칭)
    to_atom_idx: int = -1    # 끝 원자 인덱스 (-1=자동 매칭)
    # Bug 3 Fix (M894): atom_map_num 기반 역추적 — RDKit SMILES 재정렬 후 idx 보정
    # SMILES atom map 번호 예: [CH3:1]Br → from_atom_map=1 (map num, not idx)
    # -1이면 atom_map_num 미사용 (기존 idx 그대로)
    from_atom_map: int = -1  # atom map number for from-atom (M894)
    to_atom_map: int = -1    # atom map number for to-atom (M894)


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
    # ── v2.2 스키마 확장 (M165 P1-D fix, 2026-04-21) ──────────────────────────
    solvent: str = ""        # 용매 (예: "MeOH", "THF", "DMF/H₂O (1:1)")
    temperature: str = ""   # 온도/조건 (예: "0°C → rt", "reflux", "-78°C")
    leaving_group: str = "" # 이탈기 (예: "Cl⁻", "Br⁻", "H₂O", "OTs⁻", "N₂↑")
    byproducts: List[str] = field(default_factory=list)  # 부산물 (예: ["HCl", "H₂O"])


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
    total_steps=2,
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
            reagents="NaOH (2 eq)",
            solvent="H₂O/DMSO (1:1)",
            temperature="rt, 2 h",
            leaving_group="Br⁻",
            byproducts=["NaBr"],
            notes="반응 속도 = k[Nu-][R-X] (2차 반응)",
        ),
        MechanismStep(
            step_number=2,
            title="생성물 형성 — Walden 반전 완료",
            description=(
                "C-Nu 결합이 완전히 형성되고 이탈기(Br-)가 완전히 이탈합니다.\n"
                "탄소의 입체배치가 반전(Walden 전환)됩니다.\n"
                "생성물: CH₃OH + Br⁻."
            ),
            reactant_smiles="CO.[Br-]",
            product_smiles="CO.[Br-]",
            arrows=[],
            labels={"생성물": "입체 반전"},
            energy_label="생성물",
            leaving_group="Br⁻",
            byproducts=["NaBr"],
            notes="Walden 전환: 입체배치 100% 반전",
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
            solvent="80% EtOH/H₂O",
            temperature="reflux",
            leaving_group="Br⁻",
            byproducts=["HBr"],
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
            leaving_group="Br⁻",
            byproducts=["HBr"],
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
            reagents="KOH (2 eq) or KOtBu (strong base)",
            solvent="EtOH, reflux (78°C)",
            temperature="reflux, 1 h",
            leaving_group="Br⁻",
            byproducts=["H₂O", "KBr"],
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
            # M859: include the acid pair as visible fragments.  Without H+/Br-
            # in the graph the popup can only draw step-to-step connector lines,
            # not real intermolecular curved-arrow evidence.
            reactant_smiles="C=C.[H+].[Br-]",
            product_smiles="C[CH2+].[Br-]",
            arrows=[
                ArrowData("full", "pi_bond", "C=C pi 결합",
                          "atom", "H+ (프로톤)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=2),  # pi bond → H+
                ArrowData("full", "bond", "H-Br 결합 전자쌍",
                          "atom", "Br- 형성", "#8E44AD", 0.35,
                          from_atom_idx=2, to_atom_idx=3),  # H-Br bond → Br-
            ],
            labels={"C=C": "pi-결합 (HOMO)", "H+": "HBr의 Hδ+", "Br": "Brδ-/Br⁻"},
            energy_label="속도 결정",
            reagents="HBr",
            solvent="극성 양성자성 용매",
            temperature="0°C → rt",
            leaving_group="Br⁻",
            byproducts=[],
            notes="HBr은 Hδ+–Brδ-로 분극되어 표시됩니다. π 결합→H, H-Br 결합→Br 전자 이동을 함께 보여야 합니다.",
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
            reagents="Br⁻",
            solvent="극성 양성자성 용매",
            leaving_group="",
            notes="용매가 이온쌍을 안정화하고 Br⁻가 카르보카티온을 공격합니다.",
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
    total_steps=2,
    overall_description=(
        "디엔(4pi)과 디에노필(2pi)이 동시 [4+2] 고리화 첨가 반응을 합니다. "
        "6원 고리가 형성됩니다. 열허용 페리사이클릭 반응입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[4+2] 동시 고리화 — 6원 전이 상태",
            description=(
                "디엔의 HOMO와 디에노필의 LUMO가 suprafacial 중첩합니다.\n"
                "6개의 전자가 동시에 재배열되며 2개의 새 sigma-결합이 형성됩니다.\n"
                "보트형 6원 전이 상태를 경유합니다."
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
            is_transition_state=True,
            energy_label="동시 전이 상태",
            notes="Woodward-Hoffmann: 열허용 [4s+2s]",
        ),
        MechanismStep(
            step_number=2,
            title="생성물: 사이클로헥센 유도체",
            description=(
                "동시 [4+2] 반응이 완료되어 사이클로헥센 고리가 형성됩니다.\n"
                "endo/exo 선택성: endo 생성물이 운동학적으로 선호됩니다 (2차 오비탈 상호작용).\n"
                "syn 입체화학: 디엔 치환기와 디에노필 치환기의 상대 배향이 보존됩니다."
            ),
            reactant_smiles="C1CC=CCC1",
            product_smiles="C1CC=CCC1",
            arrows=[],
            labels={"product": "사이클로헥센"},
            energy_label="생성물 (발열)",
            notes="endo rule: 2차 오비탈 상호작용으로 endo 선호",
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
    total_steps=4,
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
        MechanismStep(
            step_number=4,
            title="생성물: 톨루엔 + HCl + AlCl₃ 촉매 재생",
            description=(
                "방향족성이 완전히 회복된 톨루엔이 생성됩니다.\n"
                "AlCl₃ 촉매가 재생: AlCl₄⁻ + H⁺ → HCl + AlCl₃.\n"
                "HCl은 부산물로 방출됩니다.\n"
                "주의: Friedel-Crafts 알킬화는 과알킬화 문제 (생성물이 더 반응성)."
            ),
            reactant_smiles="Cc1ccccc1",
            product_smiles="Cc1ccccc1",
            arrows=[],
            labels={"toluene": "생성물", "HCl": "부산물"},
            energy_label="생성물",
            notes="과알킬화 주의: 아실화(FC acylation)는 이 문제 없음",
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
    total_steps=4,
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
            title="1,2-알킬 이동 + H₂O 이탈 → 나이트릴리움 이온",
            description=(
                "Anti-periplanar 알킬기가 1,2-이동으로 N에 결합합니다.\n"
                "동시에 H₂O가 이탈 → 나이트릴리움 이온(R-C≡N⁺-R') 중간체.\n"
                "이것이 Beckmann 전위의 핵심 단계(속도 결정)입니다."
            ),
            # CC(C)=N[OH2+]: C0-C1(=N2-OH2+3)-C4
            reactant_smiles="CC(C)=N[OH2+]",
            product_smiles="C[C+]=NC",
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
            title="물에 의한 친핵 공격 → 이미닐 수화물",
            description=(
                "H₂O(친핵체)의 산소 론페어가 나이트릴리움 이온의 C⁺를 공격합니다.\n"
                "새 C-O 결합 형성 → 불안정한 이미닐 수화물 중간체."
            ),
            reactant_smiles="C[C+]=NC",
            product_smiles="CC(=O)NC",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C⁺ (나이트릴리움)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),  # 외부 H2O→C
            ],
            labels={"H2O": "친핵체"},
            energy_label="수화",
            reagents="H₂O",
        ),
        MechanismStep(
            step_number=4,
            title="양성자 전달 → 아마이드 (토토머화)",
            description=(
                "양성자 전달(tautomerism)을 거쳐 안정한 아마이드(C(=O)-NH) 구조로 재배열.\n"
                "최종: R-CO-NH-R' 아마이드 + H₂O 부산물."
            ),
            reactant_smiles="CC(=O)NC",
            product_smiles="CC(=O)NC",
            arrows=[],
            labels={"amide": "생성물"},
            energy_label="생성물",
            reagents="",
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
    total_steps=4,
    overall_description=(
        "Michael 반응은 안정화된 카르보음이온(Michael donor)이 α,β-불포화 카르보닐(Michael acceptor)의 "
        "β-위치를 1,4-공역 첨가하는 반응입니다. 전자가 4원자 경로(C⁻ → β-C = α-C - C=O)를 "
        "따라 이동하는 대표적인 공역 첨가 반응입니다. "
        "1,2-첨가(카르보닐 직접 공격)와 달리 1,4-첨가는 열역학적 산물이며, "
        "Michael donor는 '소프트' 친핵체(안정화된 카르보음이온), "
        "Michael acceptor는 α,β-불포화 카르보닐입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="염기에 의한 에놀레이트 형성 (Michael donor 활성화)",
            description=(
                "염기(NaOEt)가 아세틸아세톤(2,4-pentanedione)의 활성 메틸렌 α-H를 제거합니다.\n"
                "C-H sigma 결합 전자쌍이 C=C 에놀레이트로 이동합니다.\n"
                "동시에 C=O pi 결합 전자쌍이 산소에 잔류합니다.\n"
                "양쪽 카르보닐에 의한 이중 안정화로 pKa ≈ 9 (매우 산성).\n"
                "생성된 에놀레이트가 Michael donor로 작용합니다."
            ),
            # CC(=O)CC(=O)C: C0-C1(=O2)-C3(H2)-C4(=O5)-C6
            reactant_smiles="CC(=O)CC(=O)C",
            product_smiles="CC(=O)[CH-]C(=O)C",
            arrows=[
                ArrowData("full", "lone_pair", "EtO⁻ (염기)",
                          "atom", "α-H (활성 메틸렌)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=3),
                ArrowData("full", "bond", "C-H sigma 결합",
                          "bond", "C=C 에놀레이트 형성", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=O pi 결합",
                          "atom", "O⁻ (공명 안정화)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"H": "α-H (pKa ≈ 9)", "C₃": "→ 에놀레이트 C⁻"},
            energy_label="에놀레이트 형성 (빠른 평형)",
            reagents="NaOEt / EtOH",
            notes="이중 카르보닐 안정화로 pKa가 매우 낮아 에놀레이트 형성이 용이.",
        ),
        MechanismStep(
            step_number=2,
            title="1,4-공역 첨가 (β-탄소 공격) — 핵심 전자이동 경로",
            description=(
                "에놀레이트의 α-탄소(C⁻)가 MVK(methyl vinyl ketone)의 β-탄소를 공격합니다.\n"
                "전자가 4원자 공역 경로를 따라 이동합니다:\n"
                "  ①에놀레이트 C⁻ → ②β-C (새 C-C sigma 형성)\n"
                "  ②β-C=α-C pi → ③α-C (pi → sigma 전환)\n"
                "  ③α-C=O pi → ④O⁻ (카르보닐 → 엔올레이트)\n"
                "이것이 '1,4-첨가'의 핵심: 전자가 공역계(C=C-C=O)를 타고 이동합니다.\n"
                "1,2-첨가(직접 C=O 공격)보다 열역학적으로 유리합니다."
            ),
            # 에놀레이트 C⁻: [CH2-] idx0. MVK: C1=C2-C3(=O4)-C5
            reactant_smiles="[CH3-].C=CC(C)=O",
            product_smiles="CC=CC(C)=O",
            arrows=[
                ArrowData("full", "negative_charge", "에놀레이트 C⁻ (Michael donor)",
                          "atom", "β-C (MVK, Michael acceptor)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=2),
                ArrowData("full", "pi_bond", "C=C pi (α-β 이중결합)",
                          "bond", "C-C sigma 형성 (β→α)", "#FF9800", 0.4,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "pi_bond", "C=O pi (α-C=O)",
                          "atom", "O⁻ (엔올레이트 산소)", "#1565C0", 0.4,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"C⁻": "Michael donor", "β-C": "공격점 (소프트 LUMO)"},
            is_transition_state=True,
            energy_label="ΔG‡ (1,4-첨가, 속도 결정 단계)",
            reagents="",
            notes=(
                "전자 흐름 경로: donor C⁻ → β-C → α-C → O⁻ (4원자 공역 경로). "
                "HSAB 이론: 소프트 친핵체(에놀레이트) + 소프트 친전자체(β-C) → 1,4-산물. "
                "하드 친핵체(RMgBr)는 카르보닐 직접 공격 → 1,2-산물."
            ),
        ),
        MechanismStep(
            step_number=3,
            title="엔올레이트 중간체 형성 → 1,5-디카르보닐 골격",
            description=(
                "1,4-첨가 완료: 새 C-C sigma 결합이 형성됩니다.\n"
                "엔올레이트(C=C-O⁻) 형태의 안정한 중간체.\n"
                "Michael donor와 acceptor가 연결된 1,5-디카르보닐 골격이 형성됩니다.\n"
                "이 1,5-관계가 Robinson 고리화 등 후속 반응의 기초입니다."
            ),
            reactant_smiles="CC=CC(C)=O",
            product_smiles="CC(CC(C)=O)=O",
            arrows=[
                ArrowData("full", "bond", "C=C 이중결합 → C-C 단일결합",
                          "bond", "케토-에놀 호변이성", "#FF9800", 0.4,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"1,5-디카르보닐": "Michael adduct 골격"},
            energy_label="엔올레이트 → 케토 호변이성",
            reagents="",
            notes="1,5-디카르보닐 골격은 분자 내 알돌 반응(Robinson 고리화)의 전구체.",
        ),
        MechanismStep(
            step_number=4,
            title="양성자화 → 최종 Michael adduct (1,5-디카르보닐)",
            description=(
                "엔올레이트 산소가 용매(H₂O 또는 H₃O⁺)에 의해 양성자화됩니다.\n"
                "최종 생성물: 1,5-디카르보닐 화합물 (Michael adduct).\n"
                "2,4-pentanedione과 MVK로부터 2-acetyl-5-oxohexanoic acid 유도체 생성.\n"
                "이 1,5-디카르보닐은 Robinson 고리화의 기질이 됩니다."
            ),
            reactant_smiles="CC(CC(C)=O)=O",
            product_smiles="CC(=O)CC(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "H₃O⁺ → H⁺",
                          "atom", "O⁻ → OH (양성자화)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=5),
            ],
            labels={"O": "양성자화 → OH"},
            energy_label="양성자화 (발열)",
            reagents="H₃O⁺ (산성 후처리)",
            notes=(
                "전체 반응 요약: Michael donor(1,3-디카르보닐) + acceptor(α,β-불포화 케톤) "
                "→ 1,5-디카르보닐. 이후 Robinson 고리화 → 사이클로헥세논 가능."
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\ndonor + MVK", 0.0),
        ("에놀레이트\n(donor 활성화)", 5.0),
        ("TS (1,4-첨가)\n속도 결정", 15.0),
        ("엔올레이트\n중간체", 3.0),
        ("생성물\n1,5-디카르보닐\n(Michael adduct)", -8.0),
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
    total_steps=2,
    overall_description=(
        "알릴 비닐 에터가 열적 [3,3]-시그마트로피 재배열을 거쳐 "
        "γ,δ-불포화 카르보닐 화합물로 변환됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[3,3]-시그마트로피 재배열 — 의자형 전이 상태",
            description=(
                "O-C(allyl) σ 결합이 끊어지면서 C-C 새 결합 형성.\n"
                "6원 의자형 전이 상태를 경유합니다.\n"
                "6개의 전자가 동시에 재배열되는 협주 반응."
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
            is_transition_state=True,
            energy_label="[3,3] 협주 TS",
            reagents="Δ (150-200°C)",
        ),
        MechanismStep(
            step_number=2,
            title="생성물: γ,δ-불포화 카르보닐 화합물",
            description=(
                "재배열이 완료되어 산소는 카르보닐(C=O)로 전환됩니다.\n"
                "새 C-C 결합이 형성된 γ,δ-불포화 카르보닐이 최종 생성물입니다.\n"
                "케토-엔올 토토머화를 거쳐 가장 안정한 형태로 이성질화."
            ),
            reactant_smiles="C=CCC(=O)C",
            product_smiles="C=CCC(=O)C",
            arrows=[],
            labels={"product": "γ,δ-불포화 카르보닐"},
            energy_label="생성물 (발열)",
            notes="Claisen의 모든 변형(aromatic, Ireland, Johnson)은 이 [3,3]-재배열을 공유",
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


# ============================================================================
# CYCLE 2-5 ADDITIONS (16 templates from DryLab integration)
# ============================================================================

# ─── Br₂ Anti-Addition ──────────────────────────────────────────────────────
# 대표: Cyclohexene + Br₂ → trans-1,2-dibromocyclohexane
MECHANISMS["br2_anti_addition"] = MechanismData(
    mechanism_type="br2_anti_addition",
    title="Br₂ 반부가 반응 (Anti-Addition)",
    total_steps=2,
    overall_description=(
        "알켄에 Br₂가 반응하면 bromonium ion 중간체를 거쳐 anti 입체선택적으로 "
        "trans-디브로모 생성물이 형성됩니다. 고리형 브로모늄 이온이 "
        "SN2-유사 후면 공격만 허용하므로 anti-addition이 됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Bromonium Ion 형성 (π → Br 친전자 공격)",
            description=(
                "알켄의 π 전자가 Br₂의 Br(δ+)를 공격합니다.\n"
                "Br-Br 결합이 이종 개열하여 Br⁻가 이탈합니다.\n"
                "3원환 bromonium ion [C-Br⁺-C] 중간체가 형성됩니다.\n"
                "bromonium ion은 두 탄소를 동시에 연결하여 회전을 억제합니다."
            ),
            # C=C: C0=C1, BrBr: Br2-Br3
            reactant_smiles="C=C.BrBr",
            product_smiles="C1C[Br+]1.[Br-]",  # bromonium ion (3-membered ring)
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "Br (δ+)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=2),  # π→Br
                ArrowData("full", "bond", "Br-Br σ 결합",
                          "atom", "Br⁻ (이탈)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # Br→Br⁻
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "Br (반대쪽 C)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=2),  # 3원환 형성
            ],
            labels={"C=C": "π 공여체", "Br": "δ+/δ-"},
            energy_label="Bromonium ion 형성",
            reagents="Br₂, CH₂Cl₂",
            notes="Bromonium ion은 비고전적 3원환 양이온",
        ),
        MechanismStep(
            step_number=2,
            title="Br⁻ 후면 공격 (Anti SN2-유사)",
            description=(
                "Br⁻가 bromonium ion의 반대편(anti face)에서 탄소를 공격합니다.\n"
                "3원환이 열리면서 새로운 C-Br 결합이 형성됩니다.\n"
                "결과: trans-1,2-디브로마이드 (anti-addition 생성물)."
            ),
            reactant_smiles="C1C[Br+]1.[Br-]",  # bromonium ion (3-membered ring)
            product_smiles="BrCCBr",
            arrows=[
                ArrowData("full", "lone_pair", "Br⁻ 론페어",
                          "atom", "C (anti face)", "#4CAF50", 0.5,
                          from_atom_idx=3, to_atom_idx=1),  # Br⁻→C
                ArrowData("full", "bond", "C-Br⁺ 결합 (3원환)",
                          "atom", "Br (재분배)", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # ring opening
                ArrowData("full", "bond", "C-Br⁺ 결합",
                          "atom", "Br 이동", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # other C-Br
            ],
            labels={"Br-": "친핵체 (anti)", "C": "electrophilic C"},
            energy_label="Anti 부가",
            notes="SN2-유사: 후면 공격 → anti 입체선택성",
        ),
    ],
    energy_diagram=[
        ("반응물\n알켄 + Br₂", 0.0),
        ("TS1", 12.0),
        ("Bromonium\nion + Br⁻", 8.0),
        ("TS2", 14.0),
        ("생성물\ntrans-디브로마이드", -15.0),
    ],
)

# ─── Acid-Catalyzed Hydration ──────────────────────────────────────────────
# 대표: Propylene + H₂O/H₂SO₄ → 2-Propanol (Markovnikov)
MECHANISMS["acid_hydration"] = MechanismData(
    mechanism_type="acid_hydration",
    title="산촉매 수화 (Acid-Catalyzed Hydration)",
    total_steps=3,
    overall_description=(
        "알켄에 H₃O⁺/H₂SO₄ 조건에서 물이 Markovnikov 배향으로 부가됩니다. "
        "카르보카티온 중간체를 경유하므로 재배열 가능성이 있습니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="π 결합에 양성자 부가 (Markovnikov)",
            description=(
                "H₃O⁺의 양성자가 알켄의 π 전자를 공격합니다.\n"
                "Markovnikov 규칙: 치환도가 낮은 탄소에 H가 부가.\n"
                "→ 더 안정한(치환도 높은) 카르보카티온 형성."
            ),
            # CC=C: C0-C1=C2
            reactant_smiles="CC=C.[OH3+]",
            product_smiles="C[CH+]C.O",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "H⁺", "#E53935", 0.5,
                          from_atom_idx=1, to_atom_idx=3),  # π→H⁺
                ArrowData("full", "bond", "O-H 결합 (H₃O⁺)",
                          "atom", "O (H₂O 재생)", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=3),  # O-H break
                ArrowData("full", "pi_bond", "π 전자 재분배",
                          "atom", "C⁺ (Markovnikov)", "#FF9800", 0.4,
                          from_atom_idx=2, to_atom_idx=1),  # C⁺ formation
            ],
            labels={"C=C": "π 공여체", "H": "친전자체"},
            energy_label="카르보카티온 형성",
            reagents="H₂SO₄ (cat.), H₂O",
            notes="Markovnikov 배향: 안정한 2° C⁺ 형성",
        ),
        MechanismStep(
            step_number=2,
            title="물 친핵 공격 → 옥소늄 이온",
            description=(
                "H₂O의 론페어가 카르보카티온의 빈 p 오비탈을 공격합니다.\n"
                "옥소늄 이온(oxonium ion) 중간체가 형성됩니다."
            ),
            reactant_smiles="C[CH+]C.O",
            product_smiles="CC([OH2+])C",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C⁺ (빈 p 오비탈)", "#4CAF50", 0.5,
                          from_atom_idx=3, to_atom_idx=1),  # O→C⁺
            ],
            labels={"O": "H₂O (Nu:)", "C": "C⁺ (electrophile)"},
            energy_label="옥소늄 이온",
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자 → 알코올 생성물",
            description=(
                "옥소늄 이온에서 H₂O가 양성자를 제거합니다.\n"
                "촉매(H⁺)가 재생되며, 최종 알코올 생성물 형성."
            ),
            reactant_smiles="CC([OH2+])C",
            product_smiles="CC(O)C",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어 (염기)",
                          "atom", "H (옥소늄)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=2),  # base→H
                ArrowData("full", "bond", "O-H 결합",
                          "atom", "O (알코올)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=2),  # O-H break
            ],
            labels={"H₂O": "양성자 수용체"},
            energy_label="촉매 재생",
            notes="H₂SO₄ 촉매 재생 (cat. cycle)",
        ),
    ],
    energy_diagram=[
        ("반응물\n알켄 + H₃O⁺", 0.0),
        ("TS1", 15.0),
        ("카르보카티온", 10.0),
        ("TS2", 12.0),
        ("옥소늄 이온", 5.0),
        ("생성물\n알코올", -8.0),
    ],
)

# ─── Ozonolysis ──────────────────────────────────────────────────────────
# 대표: 알켄 + O₃ → 오존화물 → (Zn) 알데히드/케톤
MECHANISMS["ozonolysis"] = MechanismData(
    mechanism_type="ozonolysis",
    title="오존 분해 (Ozonolysis)",
    total_steps=3,
    overall_description=(
        "O₃가 알켄과 [3+2] 고리화첨가로 molozonide를 형성한 후, "
        "재배열하여 ozonide를 거쳐 환원적 또는 산화적 분해로 "
        "카르보닐 화합물(알데히드/케톤)을 생성합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[3+2] 고리화첨가 → Molozonide",
            description=(
                "O₃의 1,3-쌍극자가 알켄과 동시 고리화 반응.\n"
                "5원환 molozonide(1,2,3-trioxolane) 형성.\n"
                "이 중간체는 불안정합니다."
            ),
            reactant_smiles="C=C.[O-][O+]=O",
            product_smiles="C1COOOC1",  # molozonide (1,2,3-trioxolane, 5-membered ring)
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "O⁺ (O₃ terminal)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=3),  # C→O
                ArrowData("full", "lone_pair", "O⁻ 론페어",
                          "atom", "C (반대쪽)", "#4CAF50", 0.5,
                          from_atom_idx=2, to_atom_idx=1),  # O⁻→C
                ArrowData("full", "pi_bond", "O=O⁺ π 결합",
                          "atom", "재분배", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),  # bond redistribution
            ],
            labels={"O₃": "1,3-쌍극자"},
            energy_label="[3+2] 협동 반응",
            reagents="O₃, CH₂Cl₂, -78°C",
            notes="Molozonide: 불안정, 즉시 재배열",
        ),
        MechanismStep(
            step_number=2,
            title="Molozonide 재배열 → Ozonide",
            description=(
                "Molozonide가 retro-[3+2]로 개열합니다.\n"
                "→ carbonyl oxide + aldehyde/ketone 단편.\n"
                "이 단편들이 다시 [3+2]로 재결합 → ozonide (1,2,4-trioxolane)."
            ),
            reactant_smiles="C1COOOC1",  # molozonide (1,2,3-trioxolane, 5-membered ring)
            product_smiles="C1OOC(C)O1",
            arrows=[
                ArrowData("full", "bond", "C-O 결합 (molozonide)",
                          "atom", "retro-[3+2]", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "bond", "O-O 결합",
                          "atom", "개열", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "lone_pair", "재결합",
                          "atom", "ozonide 형성", "#4CAF50", 0.5,
                          from_atom_idx=1, to_atom_idx=3),
            ],
            labels={"intermediate": "carbonyl oxide"},
            energy_label="retro-[3+2] → [3+2]",
        ),
        MechanismStep(
            step_number=3,
            title="환원적 분해 (Zn/AcOH 또는 Me₂S)",
            description=(
                "Ozonide를 Zn 또는 Me₂S로 환원적 분해합니다.\n"
                "C=C 이중결합이 완전히 절단되어 두 개의 카르보닐 화합물 생성.\n"
                "말단 알켄: 포름알데히드 + 다른 알데히드/케톤."
            ),
            reactant_smiles="C1OOC(C)O1",
            product_smiles="C=O.CC=O",
            arrows=[
                ArrowData("full", "bond", "O-O 결합",
                          "atom", "Zn 환원", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "bond", "C-O 결합",
                          "atom", "알데히드/케톤 생성", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "bond", "C-O 결합",
                          "atom", "두번째 C=O 형성", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"Zn": "환원제"},
            energy_label="환원적 분해",
            reagents="Zn, AcOH (또는 Me₂S)",
            notes="산화적 분해 (H₂O₂)시: 카르복실산 생성",
        ),
    ],
    energy_diagram=[
        ("반응물\n알켄 + O₃", 0.0),
        ("Molozonide", -5.0),
        ("Carbonyl oxide\n+ 단편", 10.0),
        ("Ozonide", -8.0),
        ("생성물\n카르보닐 × 2", -30.0),
    ],
)

# ─── Wittig Reaction ──────────────────────────────────────────────────────
# 대표: R₂C=O + Ph₃P=CHR' → R₂C=CHR' + Ph₃P=O
MECHANISMS["wittig"] = MechanismData(
    mechanism_type="wittig",
    title="위티히 반응 (Wittig Reaction)",
    total_steps=3,
    overall_description=(
        "인 일리드(phosphorus ylide)가 알데히드/케톤의 카르보닐과 반응하여 "
        "알켄을 생성합니다. 4원환 betaine/oxaphosphetane 중간체를 거칩니다. "
        "C=O → C=C 변환의 핵심 방법론."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Ylide 친핵 공격 → Betaine",
            description=(
                "Wittig 시약(Ph₃P=CH₂)의 카르바니온 탄소가 카르보닐 탄소를 친핵 공격.\n"
                "C-C 결합 형성. Betaine(zwitterion) 중간체 생성."
            ),
            # CC=O: C0-C1=O2, [CH2-][P+]: C3-P4
            reactant_smiles="CC=O.[CH2-][P+](c1ccccc1)(c1ccccc1)c1ccccc1",
            product_smiles="CC([O-])[CH2][P+](c1ccccc1)(c1ccccc1)c1ccccc1",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻ (ylide)",
                          "atom", "C=O (카르보닐)", "#E53935", 0.5,
                          from_atom_idx=3, to_atom_idx=1),  # C⁻→C=O
                ArrowData("full", "pi_bond", "C=O π 전자",
                          "atom", "O⁻ (alkoxide)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # π→O⁻
                ArrowData("full", "bond", "P=C 이중결합",
                          "atom", "P⁺ (양전하 유지)", "#8E44AD", 0.3,
                          from_atom_idx=4, to_atom_idx=3),  # P-C sigma: σ결합 이동 → 보라(결합끊김) M442 Rule P
            ],
            labels={"C⁻": "친핵체 (ylide)", "C=O": "친전자체"},
            energy_label="Betaine 중간체",
            reagents="THF, 0°C",
        ),
        MechanismStep(
            step_number=2,
            title="고리 닫힘 → Oxaphosphetane",
            description=(
                "Betaine의 O⁻가 인접 P⁺를 공격하여 4원환 형성.\n"
                "Oxaphosphetane (1,2-oxaphosphetane) 중간체."
            ),
            reactant_smiles="CC([O-])[CH2][P+](c1ccccc1)(c1ccccc1)c1ccccc1",
            product_smiles="CC1OP(c2ccccc2)(c2ccccc2)(c2ccccc2)C1",
            arrows=[
                ArrowData("full", "lone_pair", "O⁻ 론페어",
                          "atom", "P⁺", "#4CAF50", 0.5,
                          from_atom_idx=2, to_atom_idx=4),  # O⁻→P⁺
            ],
            labels={"O-P": "4원환 형성"},
            energy_label="Oxaphosphetane",
        ),
        MechanismStep(
            step_number=3,
            title="Retro [2+2] → 알켄 + Ph₃P=O",
            description=(
                "Oxaphosphetane이 retro [2+2] 분해.\n"
                "P-O 결합 유지, C-C 이중결합 형성.\n"
                "Ph₃P=O (triphenylphosphine oxide)가 부산물."
            ),
            reactant_smiles="CC1OP(c2ccccc2)(c2ccccc2)(c2ccccc2)C1",
            product_smiles="CC=C.O=P(c1ccccc1)(c1ccccc1)c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-O 결합",
                          "atom", "O → P=O", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # C-O→P=O
                ArrowData("full", "bond", "C-P 결합",
                          "atom", "C=C 형성", "#4CAF50", 0.4,
                          from_atom_idx=4, to_atom_idx=0),  # C-P→C=C
                ArrowData("full", "bond", "재분배",
                          "atom", "π 결합 형성", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"Ph₃P=O": "부산물 (구동력)"},
            energy_label="retro [2+2]",
            notes="P=O 결합 형성이 반응 구동력 (ΔH ≈ -548 kJ/mol)",
        ),
    ],
    energy_diagram=[
        ("반응물\nR₂C=O + Ylide", 0.0),
        ("Betaine", 5.0),
        ("Oxaphosphetane", 2.0),
        ("생성물\nR₂C=CHR' + Ph₃P=O", -25.0),
    ],
)

# ─── Grignard Reaction ──────────────────────────────────────────────────────
# 대표: RMgBr + R'CHO → R'R-CHOH (after H₃O⁺ workup)
MECHANISMS["grignard"] = MechanismData(
    mechanism_type="grignard",
    title="그리냐르 반응 (Grignard Reaction)",
    total_steps=3,
    overall_description=(
        "유기마그네슘 할라이드(RMgX)가 카르보닐 화합물에 친핵 부가하여 "
        "알코올을 생성합니다. C-C 결합 형성의 핵심 반응."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Mg 배위 → 카르보닐 활성화",
            description=(
                "Grignard 시약(RMgBr)의 Mg²⁺가 카르보닐 산소에 배위합니다.\n"
                "Lewis acid(Mg²⁺)가 카르보닐 C의 친전자성을 증가시킵니다.\n"
                "C=O 결합이 분극되어 C(δ+)가 친핵 공격에 더 취약해집니다."
            ),
            reactant_smiles="CC=O.[CH3][Mg]Br",
            product_smiles="CC(=O)([Mg]Br).[CH4]",
            arrows=[
                ArrowData("full", "lone_pair", "O 론페어",
                          "atom", "Mg²⁺ (배위)", "#4CAF50", 0.4,
                          from_atom_idx=2, to_atom_idx=4),  # O→Mg
            ],
            labels={"Mg": "Lewis acid 활성화", "C=O": "분극 증가"},
            energy_label="배위 활성화",
            reagents="Et₂O (무수), N₂",
        ),
        MechanismStep(
            step_number=2,
            title="Grignard 시약 친핵 공격 → Mg alkoxide",
            description=(
                "RMgBr의 카르바니온성 탄소(R⁻)가 카르보닐 C(δ+)를 친핵 공격.\n"
                "Mg²⁺는 카르보닐 O와 배위 → 친전자성 활성화.\n"
                "4원환 전이상태: R-C-O-Mg 고리.\n"
                "새 C-C σ 결합 형성, π 결합 → O⁻ (alkoxide)."
            ),
            # CC=O: C0-C1=O2, [CH3][Mg]Br: C3-Mg4-Br5
            reactant_smiles="CC=O.[CH3][Mg]Br",
            product_smiles="CC([O-][Mg]Br)C",
            arrows=[
                ArrowData("full", "bond", "C-Mg 결합 (R⁻ 성질)",
                          "atom", "C=O (카르보닐 C)", "#E53935", 0.5,
                          from_atom_idx=3, to_atom_idx=1),  # R→C=O
                ArrowData("full", "pi_bond", "C=O π 전자",
                          "atom", "O⁻ (alkoxide)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # π→O⁻
                ArrowData("full", "lone_pair", "O 론페어",
                          "atom", "Mg²⁺ (배위)", "#4CAF50", 0.4,
                          from_atom_idx=2, to_atom_idx=4),  # O→Mg coordination
            ],
            labels={"R-Mg": "친핵체 (C⁻)", "C=O": "친전자체"},
            energy_label="4원환 TS",
            reagents="Et₂O (무수), N₂",
            notes="무수 조건 필수: Grignard는 물/양성자와 격렬 반응",
        ),
        MechanismStep(
            step_number=3,
            title="산 가수분해 (Acid Workup) → 알코올",
            description=(
                "Mg-alkoxide 중간체에 H₃O⁺ (또는 NH₄Cl 수용액) 처리.\n"
                "O-Mg 결합이 끊어지고 O-H 결합 형성.\n"
                "최종 생성물: 2차 알코올 (알데히드) 또는 3차 알코올 (케톤)."
            ),
            reactant_smiles="CC([O-][Mg]Br)C.[OH3+]",
            product_smiles="CC(O)C.[Mg](O)Br",
            arrows=[
                ArrowData("full", "lone_pair", "H₃O⁺ → H⁺ 공여",
                          "atom", "O⁻ (alkoxide)", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=2),  # H₃O⁺ O(idx5)→alkoxide O(idx2)
                ArrowData("full", "bond", "O-Mg 결합",
                          "atom", "Mg²⁺ (이탈)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # alkoxide O→Mg breaks
                ArrowData("full", "bond", "O-H (H₃O⁺) 결합 개열",
                          "atom", "H₂O 재생 (이탈)", "#4CAF50", 0.3,
                          from_atom_idx=5, to_atom_idx=-1),  # H₃O⁺ O-H → H₂O leaves (external)
            ],
            labels={"H₃O⁺": "양성자 원", "O⁻": "→ OH"},
            energy_label="양성자화",
            reagents="H₃O⁺ (또는 sat. NH₄Cl)",
            notes="Workup 후 Mg(OH)Br 침전 제거",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCHO + RMgBr", 0.0),
        ("4원환 TS", 10.0),
        ("Mg alkoxide", -15.0),
        ("H₃O⁺ workup", -13.0),
        ("생성물\n알코올", -20.0),
    ],
)

# ─── Baeyer-Villiger Oxidation ──────────────────────────────────────────────
# 대표: Cyclohexanone + mCPBA → ε-Caprolactone
MECHANISMS["baeyer_villiger"] = MechanismData(
    mechanism_type="baeyer_villiger",
    title="바이어-빌리거 산화 (Baeyer-Villiger Oxidation)",
    total_steps=2,
    overall_description=(
        "케톤을 과산(peracid)으로 산화하여 에스테르(또는 락톤)를 생성합니다. "
        "Criegee 중간체를 경유하여 [1,2]-알킬 전위가 일어납니다. "
        "이동 적성(migratory aptitude): 3° > 2° > Ph > 1° > CH₃"
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵 부가 → Criegee 중간체",
            description=(
                "과산(mCPBA)의 -OOH가 카르보닐 C를 친핵 공격.\n"
                "사면체(tetrahedral) Criegee 중간체 형성.\n"
                "산 촉매가 카르보닐 O를 활성화."
            ),
            # CC(=O)C: C0-C1(=O2)-C3, mCPBA: OO
            reactant_smiles="CC(=O)C.OO",
            product_smiles="CC(OO)(O)C",
            arrows=[
                ArrowData("full", "lone_pair", "과산 -OOH 론페어",
                          "atom", "C=O (카르보닐)", "#E53935", 0.5,
                          from_atom_idx=4, to_atom_idx=1),  # OOH→C
                ArrowData("full", "pi_bond", "C=O π 전자",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # π→O
                ArrowData("full", "lone_pair", "H 이동 (분자내)",
                          "atom", "O (카르보닐)", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=2),  # H transfer
            ],
            labels={"mCPBA": "과산 산화제", "C=O": "기질"},
            energy_label="Criegee 중간체",
            reagents="mCPBA, CH₂Cl₂",
            notes="Lewis산 촉매(BF₃) 사용 시 속도 증가",
        ),
        MechanismStep(
            step_number=2,
            title="[1,2]-전위 → 에스테르/락톤",
            description=(
                "알킬/아릴기가 O-O 결합의 anti-periplanar 위치에서 이동.\n"
                "[1,2]-alkyl/aryl shift: C→O 이동.\n"
                "O-O 결합 개열, 카르복실산 이탈.\n"
                "이동 적성: tert-alkyl > sec > aryl > prim > methyl."
            ),
            reactant_smiles="CC(OO)(O)C",
            product_smiles="COC(=O)C.O",
            arrows=[
                ArrowData("full", "bond", "C-C 결합 (이동기)",
                          "atom", "O (삽입)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=3),  # R migration
                ArrowData("full", "bond", "O-O 결합",
                          "atom", "RCOOH 이탈", "#1565C0", 0.4,
                          from_atom_idx=3, to_atom_idx=4),  # O-O break
                ArrowData("full", "bond", "C-O 재형성",
                          "atom", "에스테르 C=O", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C=O reform
            ],
            labels={"R": "이동기 (migration)", "O-O": "개열"},
            energy_label="[1,2]-전위",
            notes="Migratory aptitude: 전자 풍부한 기가 우선 이동",
        ),
    ],
    energy_diagram=[
        ("반응물\n케톤 + mCPBA", 0.0),
        ("Criegee\n중간체", 8.0),
        ("[1,2]-전위\nTS", 18.0),
        ("생성물\n에스테르 + RCOOH", -30.0),
    ],
)

# ─── Birch Reduction ──────────────────────────────────────────────────────
# 대표: Benzene + Na/NH₃(l)/t-BuOH → 1,4-Cyclohexadiene
MECHANISMS["birch_reduction"] = MechanismData(
    mechanism_type="birch_reduction",
    title="버치 환원 (Birch Reduction)",
    total_steps=4,
    overall_description=(
        "방향족 고리를 Na(또는 Li)/액체 NH₃ 조건에서 부분 환원하여 "
        "1,4-사이클로헥사다이엔을 생성합니다. "
        "EDG-치환: 비치환 위치 환원, EWG-치환: 치환 위치 환원."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="1차 전자 전달 → 라디칼 음이온",
            description=(
                "Na가 액체 NH₃에 용해 → 용매화 전자(solvated electron).\n"
                "e⁻가 방향족 π* 반결합 오비탈로 전달.\n"
                "라디칼 음이온(radical anion) 중간체 형성."
            ),
            reactant_smiles="c1ccccc1.[Na]",
            product_smiles="[C-]1C=CC=CC1.[Na+]",
            arrows=[
                ArrowData("half", "lone_pair", "Na → e⁻ (용매화)",
                          "atom", "방향족 π*", "#E53935", 0.5,
                          from_atom_idx=6, to_atom_idx=0),  # e⁻→ring
                ArrowData("half", "pi_bond", "π 재분배",
                          "atom", "라디칼 음이온", "#FF9800", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # radical delocalization
            ],
            labels={"Na": "전자 공여체", "ring": "라디칼 음이온"},
            energy_label="1차 SET",
            reagents="Na, NH₃(l), -33°C",
            notes="용매화 전자: NH₃ 용매 cage 내 자유 전자",
        ),
        MechanismStep(
            step_number=2,
            title="1차 양성자화 (t-BuOH)",
            description=(
                "약한 양성자 공여체(t-BuOH)가 라디칼 음이온을 양성자화.\n"
                "가장 전자 밀도 높은 탄소에 H 부가.\n"
                "비공액 라디칼 중간체 형성."
            ),
            reactant_smiles="[C-]1C=CC=CC1.OC(C)(C)C",
            product_smiles="[CH]1C=CC=CC1.[O-]C(C)(C)C",
            arrows=[
                ArrowData("full", "bond", "O-H 결합 (t-BuOH)",
                          "atom", "C⁻ (양성자화)", "#4CAF50", 0.4,
                          from_atom_idx=6, to_atom_idx=0),  # H→C⁻
                ArrowData("full", "negative_charge", "C⁻ 론페어",
                          "atom", "H (t-BuOH)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=6),  # C⁻ protonation
            ],
            labels={"t-BuOH": "약한 양성자 원"},
            energy_label="1차 양성자화",
            notes="NH₃보다 t-BuOH이 적절한 산 강도",
        ),
        MechanismStep(
            step_number=3,
            title="2차 전자 전달 → 카르바니온",
            description=(
                "두 번째 Na 원자가 전자를 라디칼에 전달.\n"
                "라디칼 → 카르바니온(carbanion) 변환.\n"
                "음전하가 비공약 위치에 가장 안정."
            ),
            reactant_smiles="[CH]1C=CC=CC1.[Na]",
            product_smiles="C1C=C[C-]=CC1.[Na+]",
            arrows=[
                ArrowData("half", "lone_pair", "Na → e⁻",
                          "atom", "라디칼 C·", "#E53935", 0.5,
                          from_atom_idx=6, to_atom_idx=3),  # e⁻→radical
            ],
            labels={"Na": "2차 전자 공여"},
            energy_label="2차 SET",
        ),
        MechanismStep(
            step_number=4,
            title="2차 양성자화 → 1,4-사이클로헥사다이엔",
            description=(
                "t-BuOH이 카르바니온을 양성자화.\n"
                "최종 생성물: 1,4-사이클로헥사다이엔.\n"
                "1,4-패턴: 열역학적으로 비공액 다이엔이 선호됨."
            ),
            reactant_smiles="C1C=C[C-]=CC1.OC(C)(C)C",
            product_smiles="C1C=CCC=C1",
            arrows=[
                ArrowData("full", "bond", "O-H (t-BuOH)",
                          "atom", "C⁻", "#4CAF50", 0.4,
                          from_atom_idx=7, to_atom_idx=3),  # H→C⁻
                ArrowData("full", "negative_charge", "C⁻",
                          "atom", "H 수용", "#E53935", 0.3,
                          from_atom_idx=3, to_atom_idx=7),
            ],
            labels={"product": "1,4-diene"},
            energy_label="최종 양성자화",
            notes="EDG 치환기: ipso/ortho 위치 유지, meta/para 환원",
        ),
    ],
    energy_diagram=[
        ("벤젠 + Na", 0.0),
        ("라디칼 음이온", -5.0),
        ("1차 양성자화", -12.0),
        ("2차 SET", -8.0),
        ("1,4-다이엔", -20.0),
    ],
)

# ─── Hydroboration-Oxidation ──────────────────────────────────────────────
# 대표: 1-Hexene + BH₃ → (H₂O₂/NaOH) → 1-Hexanol (anti-Markovnikov)
MECHANISMS["hydroboration"] = MechanismData(
    mechanism_type="hydroboration",
    title="하이드로붕소화-산화 (Hydroboration-Oxidation)",
    total_steps=3,
    overall_description=(
        "BH₃(또는 9-BBN)가 알켄에 syn-부가합니다. "
        "이후 H₂O₂/NaOH 산화로 anti-Markovnikov 알코올을 생성합니다. "
        "syn 부가 + anti-Mark → 유용한 입체/위치 선택성."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Hydroboration: BH₃ syn-부가 (4원환 TS)",
            description=(
                "BH₃의 빈 p 오비탈이 알켄 π 전자와 상호작용.\n"
                "4원환 전이상태를 거쳐 B-C, C-H 동시 형성.\n"
                "Anti-Markovnikov: B가 덜 치환된 C에, H가 더 치환된 C에.\n"
                "Syn 부가: 같은 면에서 B,H 동시 부가."
            ),
            # CC=C: C0-C1=C2, [BH3]: B3
            reactant_smiles="CC=C.[BH3]",
            product_smiles="CC(B)C",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "B (빈 p 오비탈)", "#E53935", 0.5,
                          from_atom_idx=1, to_atom_idx=3),  # π→B
                ArrowData("full", "bond", "B-H σ 결합",
                          "atom", "C (H 전달)", "#4CAF50", 0.4,
                          from_atom_idx=3, to_atom_idx=2),  # B-H→C-H
                ArrowData("full", "pi_bond", "동시 4원환",
                          "atom", "B-C 결합 형성", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # C-B form
            ],
            labels={"BH₃": "Lewis acid (빈 p)", "C=C": "π 공여"},
            energy_label="4원환 TS (syn)",
            reagents="BH₃·THF (또는 9-BBN)",
            notes="3회 반복: trialkylborane (R₃B) 형성",
        ),
        MechanismStep(
            step_number=2,
            title="산화: HOO⁻ 친핵 공격 → B-O 이동",
            description=(
                "H₂O₂/NaOH → HOO⁻ (hydroperoxide anion).\n"
                "HOO⁻가 B의 빈 오비탈을 친핵 공격 → 'ate' complex.\n"
                "[1,2]-알킬 전위: R이 B→O로 이동. B-O 결합 형성."
            ),
            reactant_smiles="CC(B)C.OO",
            product_smiles="CC(OB)C.O",
            arrows=[
                ArrowData("full", "lone_pair", "HOO⁻ 론페어",
                          "atom", "B (빈 오비탈)", "#E53935", 0.5,
                          from_atom_idx=3, to_atom_idx=2),  # OO⁻→B
                ArrowData("full", "bond", "C-B 결합",
                          "atom", "O (1,2-전위)", "#4CAF50", 0.4,
                          from_atom_idx=1, to_atom_idx=3),  # R migration B→O
                ArrowData("full", "bond", "O-O 결합",
                          "atom", "OH⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),  # O-O break
            ],
            labels={"HOO⁻": "산화제", "R-B": "1,2-전위"},
            energy_label="[1,2]-alkyl shift",
            reagents="H₂O₂, NaOH",
        ),
        MechanismStep(
            step_number=3,
            title="가수분해 → anti-Markovnikov 알코올",
            description=(
                "NaOH에 의해 B-O 결합이 가수분해됩니다.\n"
                "최종 생성물: anti-Markovnikov 1차 알코올.\n"
                "B(OH)₃ 부산물."
            ),
            reactant_smiles="CC(OB)C.[OH-]",
            product_smiles="CC(O)C.OB(O)O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ 론페어",
                          "atom", "B", "#4CAF50", 0.4,
                          from_atom_idx=4, to_atom_idx=3),  # OH⁻→B
                ArrowData("full", "bond", "B-O 결합",
                          "atom", "O (알코올)", "#E53935", 0.3,
                          from_atom_idx=3, to_atom_idx=2),  # B-O break → ROH
            ],
            labels={"OH⁻": "가수분해", "ROH": "anti-Mark 알코올"},
            energy_label="가수분해",
            notes="전체: anti-Markovnikov, syn-부가, retention",
        ),
    ],
    energy_diagram=[
        ("알켄 + BH₃", 0.0),
        ("4원환 TS", 8.0),
        ("R₃B", -10.0),
        ("HOO⁻ 공격", -5.0),
        ("1,2-전위", 5.0),
        ("알코올", -25.0),
    ],
)

# ─── Simmons-Smith Cyclopropanation ──────────────────────────────────────
# 대표: Cyclohexene + CH₂I₂/Zn(Cu) → Norcarane
MECHANISMS["simmons_smith"] = MechanismData(
    mechanism_type="simmons_smith",
    title="시몬스-스미스 반응 (Simmons-Smith Cyclopropanation)",
    total_steps=2,
    overall_description=(
        "CH₂I₂와 Zn(Cu)로 생성된 카르베노이드(ICH₂ZnI)가 "
        "알켄에 [2+1] 고리화 첨가하여 사이클로프로판을 형성합니다. "
        "Syn 부가, 입체특이적."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="카르베노이드 형성 (ICH₂ZnI)",
            description=(
                "Zn(Cu)가 CH₂I₂에 산화적 첨가(oxidative addition).\n"
                "C-I 결합에 Zn 삽입 → ICH₂ZnI (Simmons-Smith 시약).\n"
                "이 시약은 자유 카르벤(:CH₂)보다 온화하고 선택적."
            ),
            reactant_smiles="ICI.[Zn]",
            product_smiles="I[CH2][Zn]I",
            arrows=[
                ArrowData("full", "bond", "C-I 결합",
                          "atom", "Zn (삽입)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # Zn insertion
                ArrowData("full", "lone_pair", "Zn 전자쌍",
                          "atom", "C-I (삽입)", "#4CAF50", 0.4,
                          from_atom_idx=3, to_atom_idx=1),  # Zn→C
                ArrowData("full", "bond", "C-I 재분배",
                          "atom", "Zn-I 형성", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),  # I→Zn-I
            ],
            labels={"Zn": "산화적 첨가", "CH₂I₂": "메틸렌 원"},
            energy_label="카르베노이드 형성",
            reagents="CH₂I₂, Zn(Cu), Et₂O",
        ),
        MechanismStep(
            step_number=2,
            title="[2+1] 사이클로프로판화 (Butterfly TS)",
            description=(
                "ICH₂ZnI가 알켄 π 결합에 접근합니다.\n"
                "나비(butterfly) 전이상태를 거쳐 동시에:\n"
                "  - CH₂가 두 C에 동시 부가\n"
                "  - ZnI₂ 이탈\n"
                "Syn 부가: 같은 면에서 CH₂ 전달."
            ),
            reactant_smiles="C=C.I[CH2][Zn]I",
            product_smiles="C1CC1.I[Zn]I",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "CH₂ (카르베노이드)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=3),  # π→CH₂
                ArrowData("full", "bond", "CH₂-ZnI 결합",
                          "atom", "ZnI₂ 이탈", "#1565C0", 0.4,
                          from_atom_idx=3, to_atom_idx=4),  # CH₂-Zn break
                ArrowData("full", "pi_bond", "π 재분배",
                          "atom", "C-C 결합 형성", "#4CAF50", 0.4,
                          from_atom_idx=1, to_atom_idx=3),  # second C-CH₂
            ],
            labels={"butterfly": "나비 TS", "CH₂": "메틸렌"},
            energy_label="[2+1] Butterfly TS",
            notes="방향성 효과: allylic -OH 존재 시 같은 면에서 syn 전달",
        ),
    ],
    energy_diagram=[
        ("CH₂I₂ + Zn(Cu)", 0.0),
        ("ICH₂ZnI", -5.0),
        ("알켄 + 카르베노이드", -3.0),
        ("Butterfly TS", 12.0),
        ("사이클로프로판", -18.0),
    ],
)

# ─── Pinacol Rearrangement ──────────────────────────────────────────────
# 대표: Pinacol (2,3-dimethyl-2,3-butanediol) → Pinacolone
MECHANISMS["pinacol"] = MechanismData(
    mechanism_type="pinacol",
    title="피나콜 전위 (Pinacol Rearrangement)",
    total_steps=4,
    overall_description=(
        "1,2-다이올(vicinal diol)이 산촉매 조건에서 탈수 + [1,2]-알킬 전위를 거쳐 "
        "케톤(피나콜론)을 생성합니다. 카르보카티온 안정화가 전위 구동력."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="양성자화 → -OH₂⁺ 이탈기 형성",
            description=(
                "산(H₂SO₄)이 하나의 -OH를 양성자화 → -OH₂⁺.\n"
                "좋은 이탈기(물)로 전환됩니다."
            ),
            # OC(C)(C)C(C)(C)O: O0-C1(-C2)(-C3)-C4(-C5)(-C6)-O7
            reactant_smiles="OC(C)(C)C(C)(C)O",
            product_smiles="OC(C)(C)C(C)(C)[OH2+]",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (산촉매)",
                          "atom", "OH (양성자화)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=7),  # H⁺→OH
            ],
            labels={"OH₂⁺": "이탈기 형성"},
            energy_label="양성자화",
            reagents="H₂SO₄ (cat.), Δ",
        ),
        MechanismStep(
            step_number=2,
            title="물 이탈 → 3차 카르보카티온",
            description=(
                "물이 이탈기가 되어 이탈 → 3차 카르보카티온 형성.\n"
                "인접 -OH기의 비공유 전자쌍이 카르보카티온을 안정화."
            ),
            reactant_smiles="OC(C)(C)C(C)(C)[OH2+]",
            product_smiles="OC(C)(C)[C+](C)C.O",
            arrows=[
                ArrowData("full", "bond", "C-OH₂⁺ 결합",
                          "atom", "H₂O (이탈)", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=7),  # C-O break
            ],
            labels={"C⁺": "카르보카티온", "H₂O": "이탈"},
            energy_label="카르보카티온 형성",
        ),
        MechanismStep(
            step_number=3,
            title="[1,2]-메틸 전위 → 더 안정한 양이온",
            description=(
                "인접 메틸기가 [1,2]-전위: C-C 결합의 전자쌍이\n"
                "빈 p 오비탈(C⁺)로 이동하여 새 C-C 결합 형성.\n"
                "옥소카르보카티온(C=O⁺) → 산소의 론페어가 양전하 안정화."
            ),
            reactant_smiles="OC(C)(C)[C+](C)C",
            product_smiles="[OH+]=C(C)C(C)C",
            arrows=[
                ArrowData("full", "bond", "C-CH₃ σ 결합 (이동기)",
                          "atom", "C⁺ (빈 p 오비탈)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=4),  # methyl migration
                ArrowData("full", "lone_pair", "O 론페어",
                          "atom", "C⁺ (안정화)", "#4CAF50", 0.4,
                          from_atom_idx=0, to_atom_idx=1),  # O→C⁺
                ArrowData("full", "bond", "전위 결합 재분배",
                          "atom", "C (새 위치)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=4),  # bond redistribution
            ],
            labels={"CH₃": "[1,2]-전위", "O": "안정화"},
            energy_label="[1,2]-메틸 전위",
            notes="옥소카르보카티온: O의 론페어로 인한 공명 안정화",
        ),
        MechanismStep(
            step_number=4,
            title="탈양성자 → 피나콜론",
            description=(
                "옥소카르보카티온에서 양성자 이탈.\n"
                "C=O 이중결합 형성 → 피나콜론(케톤) 생성.\n"
                "산 촉매 재생."
            ),
            reactant_smiles="[OH+]=C(C)C(C)C",
            product_smiles="O=C(C)C(C)C",
            arrows=[
                ArrowData("full", "bond", "O-H 결합",
                          "atom", "base (H₂O)", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),  # deprotonation
                ArrowData("full", "lone_pair", "O 전자쌍 재분배",
                          "atom", "C=O 형성", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C=O
            ],
            labels={"pinacolone": "최종 생성물"},
            energy_label="탈양성자",
        ),
    ],
    energy_diagram=[
        ("피나콜\n1,2-다이올", 0.0),
        ("양성자화\nOH₂⁺", 5.0),
        ("카르보카티온", 12.0),
        ("[1,2]-전위", 10.0),
        ("피나콜론", -25.0),
    ],
)

# ─── Hofmann Rearrangement ──────────────────────────────────────────────
# 대표: RCONH₂ + Br₂/NaOH → RNH₂ + CO₂
MECHANISMS["hofmann"] = MechanismData(
    mechanism_type="hofmann",
    title="호프만 전위 (Hofmann Rearrangement)",
    total_steps=4,
    overall_description=(
        "1차 아마이드를 Br₂/NaOH로 처리하면 이소시아네이트를 경유하여 "
        "아민을 생성합니다. 탄소 수가 1개 줄어드는 분해 반응."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="N-브로모화 → N-bromoamide",
            description=(
                "NaOH가 아마이드 N-H를 탈양성자.\n"
                "N⁻이 Br₂를 친핵 공격 → N-Br 결합 형성.\n"
                "N-bromoamide 중간체."
            ),
            reactant_smiles="CC(=O)N.BrBr.[Na]O",
            product_smiles="CC(=O)NBr.[Na]Br.O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ (염기)",
                          "atom", "N-H (탈양성자)", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=3),  # OH⁻→N-H
                ArrowData("full", "lone_pair", "N⁻ 론페어",
                          "atom", "Br-Br", "#4CAF50", 0.5,
                          from_atom_idx=3, to_atom_idx=4),  # N⁻→Br
                ArrowData("full", "bond", "Br-Br",
                          "atom", "Br⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=5),  # Br-Br break
            ],
            labels={"N": "친핵체", "Br₂": "전기양성 Br"},
            energy_label="N-브로모화",
            reagents="Br₂, NaOH (aq.)",
        ),
        MechanismStep(
            step_number=2,
            title="2차 탈양성자 → N-bromoamide 음이온",
            description=(
                "NaOH가 N-H를 다시 탈양성자.\n"
                "N-bromoamide 음이온 형성.\n"
                "이 음이온이 전위의 전구체."
            ),
            reactant_smiles="CC(=O)NBr.[OH-]",
            product_smiles="CC(=O)[N-]Br.O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻",
                          "atom", "N-H", "#4CAF50", 0.4,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"OH⁻": "염기"},
            energy_label="탈양성자",
        ),
        MechanismStep(
            step_number=3,
            title="[1,2]-전위 → 이소시아네이트",
            description=(
                "알킬기(R)가 C→N으로 [1,2]-전위.\n"
                "동시에 Br⁻ 이탈.\n"
                "나이트렌 중간체 없이 협동적(concerted) 전위.\n"
                "이소시아네이트(R-N=C=O) 중간체 형성."
            ),
            reactant_smiles="CC(=O)[N-]Br",
            product_smiles="CN=C=O.[Br-]",
            arrows=[
                ArrowData("full", "bond", "R-C 결합 (이동기)",
                          "atom", "N (전위)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=3),  # R migration C→N
                ArrowData("full", "bond", "N-Br 결합",
                          "atom", "Br⁻ 이탈", "#1565C0", 0.4,
                          from_atom_idx=3, to_atom_idx=4),  # N-Br break
                ArrowData("full", "pi_bond", "C=O → C=N=C=O",
                          "atom", "이소시아네이트 형성", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # isocyanate
            ],
            labels={"R": "[1,2]-전위", "N=C=O": "이소시아네이트"},
            energy_label="[1,2]-전위 (concerted)",
            notes="Curtius와 유사: 아마이드 → 이소시아네이트",
        ),
        MechanismStep(
            step_number=4,
            title="가수분해 → 아민 + CO₂",
            description=(
                "이소시아네이트가 물에 의해 가수분해.\n"
                "카르밤산(H₂N-COOH) 중간체 → 탈카르복실화.\n"
                "최종: RNH₂ + CO₂ (탄소 1개 감소)."
            ),
            reactant_smiles="CN=C=O.O",
            product_smiles="CN.O=C=O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C=N (이소시아네이트)", "#4CAF50", 0.5,
                          from_atom_idx=3, to_atom_idx=2),  # H₂O→C
                ArrowData("full", "bond", "C-N 결합",
                          "atom", "NH₂ 형성", "#E53935", 0.3,
                          from_atom_idx=2, to_atom_idx=1),  # C-N→RNH₂
                ArrowData("full", "pi_bond", "CO₂ 형성",
                          "atom", "탈카르복실", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=2),  # C=O=C=O
            ],
            labels={"H₂O": "가수분해", "CO₂": "부산물"},
            energy_label="가수분해 + 탈카르복실",
            notes="전체: RCONH₂ → RNH₂ (C-1 degradation)",
        ),
    ],
    energy_diagram=[
        ("아마이드\nRCONH₂", 0.0),
        ("N-Br 아마이드", -3.0),
        ("음이온", -5.0),
        ("[1,2]-전위 TS", 15.0),
        ("이소시아네이트", -10.0),
        ("아민 + CO₂", -20.0),
    ],
)

# ─── Appel Reaction ──────────────────────────────────────────────────────
# 대표: ROH + PPh₃/CCl₄ → RCl + OPPh₃ + CHCl₃
MECHANISMS["appel"] = MechanismData(
    mechanism_type="appel",
    title="아펠 반응 (Appel Reaction)",
    total_steps=3,
    overall_description=(
        "알코올을 PPh₃/CCl₄로 온화한 조건에서 알킬 클로라이드로 변환합니다. "
        "P-O 결합 형성(ΔH ≈ -544 kJ/mol)이 반응 구동력. "
        "입체배치 반전(SN2) 또는 유지(SNi)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="PPh₃ + CCl₄ → [Ph₃PCCl₃]⁺Cl⁻",
            description=(
                "PPh₃의 론페어가 CCl₄의 Cl을 SN2 공격.\n"
                "Ph₃P-Cl⁺ 중간체 + :CCl₃⁻ (트리클로로메타나이드) 형성.\n"
                "이온 쌍 생성."
            ),
            reactant_smiles="P(c1ccccc1)(c1ccccc1)c1ccccc1.ClC(Cl)(Cl)Cl",
            product_smiles="Cl[P+](c1ccccc1)(c1ccccc1)c1ccccc1.Cl[C-](Cl)Cl",  # Ph3PCl+ + CCl3-
            arrows=[
                ArrowData("full", "lone_pair", "P 론페어 (PPh₃)",
                          "atom", "Cl (CCl₄)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=7),  # P→Cl
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=8, to_atom_idx=7),  # C-Cl break
                ArrowData("full", "bond", "C-Cl 재분배",
                          "atom", ":CCl₃⁻", "#4CAF50", 0.3,
                          from_atom_idx=8, to_atom_idx=9),
            ],
            labels={"PPh₃": "친핵체", "CCl₄": "Cl 원"},
            energy_label="이온 쌍 형성",
            reagents="PPh₃, CCl₄",
        ),
        MechanismStep(
            step_number=2,
            title="알코올 활성화 → 알콕시포스포늄",
            description=(
                "알코올의 O가 Ph₃P-Cl⁺를 친핵 공격.\n"
                "알콕시포스포늄(R-O-PPh₃⁺) 중간체 형성.\n"
                "Cl⁻ 이탈."
            ),
            reactant_smiles="CO.[P+](Cl)(c1ccccc1)(c1ccccc1)c1ccccc1",
            product_smiles="CO[P+](c1ccccc1)(c1ccccc1)c1ccccc1.[Cl-]",
            arrows=[
                ArrowData("full", "lone_pair", "O 론페어 (ROH)",
                          "atom", "P⁺", "#E53935", 0.5,
                          from_atom_idx=1, to_atom_idx=2),  # O→P
                ArrowData("full", "bond", "P-Cl 결합",
                          "atom", "Cl⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # P-Cl break
            ],
            labels={"ROH": "기질", "Ph₃PCl⁺": "활성화제"},
            energy_label="알콕시포스포늄",
        ),
        MechanismStep(
            step_number=3,
            title="Cl⁻ SN2 공격 → R-Cl + OPPh₃",
            description=(
                "Cl⁻가 R-O 결합의 탄소를 SN2 후면 공격.\n"
                "새 C-Cl 결합 형성, OPPh₃ 이탈기 이탈.\n"
                "P-O 결합의 강한 구동력(ΔH ≈ -544 kJ/mol)."
            ),
            reactant_smiles="CO[P+](c1ccccc1)(c1ccccc1)c1ccccc1.[Cl-]",
            product_smiles="CCl.O=P(c1ccccc1)(c1ccccc1)c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "Cl⁻ 론페어",
                          "atom", "C (SN2 후면)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),  # Cl⁻→C
                ArrowData("full", "bond", "C-O 결합",
                          "atom", "OPPh₃ (이탈기)", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=1),  # C-O break
                ArrowData("full", "lone_pair", "O 론페어",
                          "atom", "P (P=O 형성)", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # O→P=O
            ],
            labels={"Cl⁻": "SN2 친핵체", "OPPh₃": "이탈기"},
            energy_label="SN2 (입체반전)",
            notes="P=O 구동력: 열역학적으로 매우 유리",
        ),
    ],
    energy_diagram=[
        ("PPh₃ + CCl₄", 0.0),
        ("이온 쌍", -10.0),
        ("알콕시포스포늄", -8.0),
        ("SN2 TS", 5.0),
        ("R-Cl + OPPh₃", -40.0),
    ],
)

# ─── Jones Oxidation ──────────────────────────────────────────────────────
# 대표: R₂CHOH + CrO₃/H₂SO₄ → R₂C=O
MECHANISMS["jones_oxidation"] = MechanismData(
    mechanism_type="jones_oxidation",
    title="존스 산화 (Jones Oxidation)",
    total_steps=3,
    overall_description=(
        "CrO₃/H₂SO₄(존스 시약)으로 1차 알코올 → 카르복실산, "
        "2차 알코올 → 케톤으로 산화합니다. "
        "크롬산 에스테르를 경유하는 E2-유사 제거 메커니즘."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="크롬산 에스테르 형성",
            description=(
                "알코올 O가 CrO₃의 Cr(VI)를 친핵 공격.\n"
                "크롬산 에스테르(chromate ester) R-O-CrO₃H 형성.\n"
                "Cr(VI) → Cr(IV)로의 환원이 시작."
            ),
            reactant_smiles="CC(O)C.O=[Cr](=O)=O",
            product_smiles="CC(O[Cr](=O)(=O)O)C",
            arrows=[
                ArrowData("full", "lone_pair", "O 론페어 (알코올)",
                          "atom", "Cr (VI)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=4),  # O→Cr
                ArrowData("full", "pi_bond", "Cr=O π 결합",
                          "atom", "O⁻ (크롬산)", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=5),  # Cr=O→Cr-O⁻
                ArrowData("full", "bond", "양성자 이동",
                          "atom", "CrO₃ 양성자화", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=6),  # H transfer
            ],
            labels={"ROH": "기질", "CrO₃": "산화제 (Cr⁶⁺)"},
            energy_label="크롬산 에스테르",
            reagents="CrO₃, H₂SO₄, 아세톤",
        ),
        MechanismStep(
            step_number=2,
            title="E2-유사 제거 → 카르보닐 + Cr(IV)",
            description=(
                "염기(H₂O)가 α-H를 탈양성자.\n"
                "C-H 결합 전자쌍 → C=O π 결합 형성.\n"
                "동시에 O-Cr 결합 개열 → CrO₃H₂ (Cr⁴⁺).\n"
                "E2-유사: anti-periplanar 배열 필요."
            ),
            reactant_smiles="CC(O[Cr](=O)(=O)O)C",
            product_smiles="CC(=O)C.O[Cr](=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (염기)",
                          "atom", "α-H", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),  # base→α-H
                ArrowData("full", "bond", "C-H 결합",
                          "bond", "C=O π 형성", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=2),  # C-H→C=O
                ArrowData("full", "bond", "O-Cr 결합",
                          "atom", "Cr(IV) 이탈", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # O-Cr break
            ],
            labels={"α-H": "E2 제거", "Cr": "Cr⁶⁺→Cr⁴⁺"},
            energy_label="E2-유사 제거",
            notes="1차 알코올: 추가 산화 → RCOOH (존스 시약 과잉 시)",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 케톤 (2차) 또는 카르복실산 (1차)",
            description=(
                "2차 알코올: 케톤에서 산화 정지 (α-H 없음).\n"
                "1차 알코올: 알데히드 중간체가 수화되어 gem-diol → 추가 산화 → 카르복실산.\n"
                "Jones 산화: 과잉 산화제로 1차 알코올을 직접 RCOOH로 변환.\n"
                "Cr(VI) → Cr(III): 산화크로뮴 침전 (녹색)."
            ),
            reactant_smiles="CC(=O)C.O[Cr](=O)O",
            product_smiles="CC(=O)C",
            arrows=[],
            labels={"ketone": "최종 생성물", "Cr(III)": "환원된 산화제"},
            energy_label="생성물",
            notes="PCC/PDC: 1차 알코올을 알데히드에서 정지시킬 수 있음",
        ),
    ],
    energy_diagram=[
        ("알코올 + CrO₃", 0.0),
        ("크롬산 에스테르", -5.0),
        ("E2 TS", 10.0),
        ("케톤 + Cr(IV)", -30.0),
    ],
)

# ─── EAS Nitration ──────────────────────────────────────────────────────
# 대표: Benzene + HNO₃/H₂SO₄ → Nitrobenzene
MECHANISMS["eas_nitration"] = MechanismData(
    mechanism_type="eas_nitration",
    title="방향족 니트로화 (EAS Nitration)",
    total_steps=3,
    overall_description=(
        "HNO₃/H₂SO₄ 혼합산에서 NO₂⁺(니트로늄 이온)이 생성되어 "
        "방향족 고리에 친전자 치환합니다. TNT, 니트로벤젠 합성의 기본."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="NO₂⁺ (니트로늄 이온) 생성",
            description=(
                "H₂SO₄가 HNO₃를 양성자화 → H₂NO₃⁺.\n"
                "H₂O 이탈 → NO₂⁺ (니트로늄 이온) 생성.\n"
                "NO₂⁺ 는 강력한 친전자체."
            ),
            reactant_smiles="[O-][N+](=O)O.OS(=O)(=O)O",
            product_smiles="[O-][N+]=O.O.OS(=O)(=O)[O-]",
            arrows=[
                ArrowData("full", "lone_pair", "H₂SO₄ (양성자화)",
                          "atom", "HNO₃ → H₂NO₃⁺", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=3),  # H⁺→O
                ArrowData("full", "bond", "N-OH₂ 결합",
                          "atom", "H₂O 이탈", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=3),  # N-O break
                ArrowData("full", "lone_pair", "전자 재분배",
                          "atom", "NO₂⁺ 형성", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # N=O+ formation
            ],
            labels={"H₂SO₄": "양성자 원", "NO₂⁺": "친전자체"},
            energy_label="NO₂⁺ 생성",
            reagents="HNO₃, H₂SO₄ (conc.)",
        ),
        MechanismStep(
            step_number=2,
            title="NO₂⁺ + 방향족 → σ-complex (아레늄 이온)",
            description=(
                "NO₂⁺가 방향족 π 전자를 공격.\n"
                "방향족성 상실, σ-complex(Wheland 중간체) 형성.\n"
                "양전하가 고리 위에 비편재화."
            ),
            # c1ccccc1: aromatic, [N+]: nitronium
            reactant_smiles="c1ccccc1.[N+](=O)=O",
            product_smiles="O=[N+]([O-])C1C=C[CH+]C=C1",  # sigma-complex (arenium ion, non-aromatic)
            arrows=[
                ArrowData("full", "pi_bond", "방향족 π 전자",
                          "atom", "NO₂⁺ (N)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=6),  # π→NO₂⁺
                ArrowData("full", "pi_bond", "π 재분배",
                          "atom", "σ-complex", "#FF9800", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # ring delocalization
                ArrowData("full", "pi_bond", "π 재분배",
                          "atom", "양전하 비편재화", "#FF9800", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"NO₂⁺": "친전자체", "σ": "Wheland 중간체"},
            energy_label="σ-complex (RDS)",
        ),
        MechanismStep(
            step_number=3,
            title="H⁺ 이탈 → 니트로벤젠",
            description=(
                "σ-complex에서 H⁺가 이탈.\n"
                "방향족성이 회복되어 니트로벤젠 생성.\n"
                "H₂SO₄ 촉매 재생."
            ),
            reactant_smiles="O=[N+]([O-])C1C=C[CH+]C=C1",  # sigma-complex (arenium ion, non-aromatic)
            product_smiles="c1ccc([N+](=O)[O-])cc1",
            arrows=[
                ArrowData("full", "bond", "C-H σ 결합",
                          "atom", "Base (H⁺ 제거)", "#4CAF50", 0.4,
                          from_atom_idx=8, to_atom_idx=-1),  # C-H→base
                ArrowData("full", "bond", "σ 결합 → π",
                          "bond", "방향족성 회복", "#E53935", 0.3,
                          from_atom_idx=7, to_atom_idx=8),  # aromaticity
            ],
            labels={"H⁺": "이탈", "NO₂": "치환기"},
            energy_label="방향족성 회복",
            notes="다니트로화: 추가 HNO₃/H₂SO₄/가열 시 진행",
        ),
    ],
    energy_diagram=[
        ("벤젠 + HNO₃", 0.0),
        ("NO₂⁺ 생성", 10.0),
        ("σ-complex", 20.0),
        ("니트로벤젠", -15.0),
    ],
)

# ─── EAS Sulfonation ──────────────────────────────────────────────────────
# 대표: Benzene + SO₃/H₂SO₄ → Benzenesulfonic acid
MECHANISMS["eas_sulfonation"] = MechanismData(
    mechanism_type="eas_sulfonation",
    title="방향족 술폰화 (EAS Sulfonation)",
    total_steps=2,
    overall_description=(
        "SO₃(삼산화황)가 방향족 고리에 친전자 치환하여 "
        "아릴술폰산을 생성합니다. 가역 반응 — 묽은 산/가열로 역반응 가능."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="SO₃ 친전자 공격 → σ-complex",
            description=(
                "SO₃의 S(δ+)가 방향족 π 전자에 의해 공격받음.\n"
                "σ-complex(아레늄 이온) 형성.\n"
                "SO₃ 는 중성이지만 S가 강한 δ+를 가짐."
            ),
            reactant_smiles="c1ccccc1.O=S(=O)=O",
            product_smiles="O=S(=O)([O-])C1=CC=C[CH+]C1",
            arrows=[
                ArrowData("full", "pi_bond", "방향족 π 전자",
                          "atom", "S (δ+, SO₃)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=7),  # π→S
                ArrowData("full", "pi_bond", "S=O π 결합",
                          "atom", "O⁻ (전자 수용)", "#1565C0", 0.3,
                          from_atom_idx=7, to_atom_idx=8),  # S=O→S-O⁻
                ArrowData("full", "pi_bond", "π 재분배",
                          "atom", "σ-complex", "#FF9800", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # ring charge
            ],
            labels={"SO₃": "친전자체 (S δ+)", "σ": "아레늄 이온"},
            energy_label="σ-complex",
            reagents="SO₃, H₂SO₄ (발연황산)",
        ),
        MechanismStep(
            step_number=2,
            title="H⁺ 이탈 → 아릴술폰산",
            description=(
                "σ-complex에서 H⁺ 이탈.\n"
                "방향족성 회복 + 벤젠술폰산 생성.\n"
                "가역 반응: 묽은 H₂SO₄/Δ로 역술폰화 가능."
            ),
            reactant_smiles="O=S(=O)([O-])C1=CC=C[CH+]C1",
            product_smiles="c1ccc(S(=O)(=O)O)cc1",
            arrows=[
                ArrowData("full", "bond", "C-H σ 결합",
                          "atom", "Base (H⁺ 제거)", "#4CAF50", 0.4,
                          from_atom_idx=9, to_atom_idx=-1),
                ArrowData("full", "bond", "σ → π 재분배",
                          "bond", "방향족성 회복", "#E53935", 0.3,
                          from_atom_idx=8, to_atom_idx=9),
            ],
            labels={"H⁺": "이탈", "SO₃H": "술폰기"},
            energy_label="방향족성 회복",
            notes="가역: ipso-탈술폰화 (묽은 H₂SO₄, Δ, H₂O)",
        ),
    ],
    energy_diagram=[
        ("벤젠 + SO₃", 0.0),
        ("σ-complex", 15.0),
        ("벤젠술폰산", -5.0),
    ],
)

# ─── HX Addition to Alkene ──────────────────────────────────────────────
# 대표: Propylene + HBr → 2-Bromopropane (Markovnikov)
MECHANISMS["hx_addition"] = MechanismData(
    mechanism_type="hx_addition",
    title="HX 부가 (Markovnikov)",
    total_steps=2,
    overall_description=(
        "HX(HCl, HBr, HI)가 알켄에 Markovnikov 배향으로 부가합니다. "
        "양성자화 → 카르보카티온 → X⁻ 공격의 2단계 반응."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="양성자 부가 → 카르보카티온 (Markovnikov)",
            description=(
                "HX의 H⁺가 알켄 π 전자를 공격.\n"
                "Markovnikov: 덜 치환된 C에 H 부가.\n"
                "→ 더 안정한(더 치환된) 카르보카티온 형성.\n"
                "속도 결정 단계."
            ),
            # CC=C: C0-C1=C2, HBr: Br3-H
            reactant_smiles="CC=C.Br",
            product_smiles="C[CH+]C.[Br-]",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "H⁺ (HBr)", "#E53935", 0.5,
                          from_atom_idx=1, to_atom_idx=3),  # π→H
                ArrowData("full", "bond", "H-Br 결합",
                          "atom", "Br⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=3),  # H-Br break
                ArrowData("full", "pi_bond", "π → σ 재분배",
                          "atom", "C⁺ (Markov.)", "#FF9800", 0.4,
                          from_atom_idx=2, to_atom_idx=1),  # C⁺ formation
            ],
            labels={"C=C": "π 공여체", "H⁺": "친전자체"},
            energy_label="카르보카티온 (RDS)",
            reagents="HBr (anhydrous)",
            notes="Markovnikov: 가장 안정한 C⁺ 형성 경로",
        ),
        MechanismStep(
            step_number=2,
            title="X⁻ 친핵 공격 → 할로겐화물",
            description=(
                "Br⁻가 카르보카티온의 빈 p 오비탈을 친핵 공격.\n"
                "새 C-Br 결합 형성.\n"
                "라세미 혼합물 (C⁺ 평면 → 양면 공격)."
            ),
            reactant_smiles="C[CH+]C.[Br-]",
            product_smiles="CC(Br)C",
            arrows=[
                ArrowData("full", "lone_pair", "Br⁻ 론페어",
                          "atom", "C⁺ (빈 p)", "#4CAF50", 0.5,
                          from_atom_idx=3, to_atom_idx=1),  # Br⁻→C⁺
            ],
            labels={"Br⁻": "친핵체", "C⁺": "electrophile"},
            energy_label="친핵 공격 (빠름)",
            notes="anti-Mark 원하면: 과산화물(ROOR) 조건 사용 (라디칼)",
        ),
    ],
    energy_diagram=[
        ("알켄 + HBr", 0.0),
        ("카르보카티온\n+ Br⁻", 12.0),
        ("2-브로모프로판", -15.0),
    ],
)


# ─── Dess-Martin Oxidation ──────────────────────────────────────────────────
# 대표 반응: R-CH₂OH → R-CHO (1° alcohol) or R₂CHOH → R₂C=O (2° alcohol)
# DMP = Dess-Martin Periodinane, hypervalent I(III) reagent

MECHANISMS["dess_martin"] = MechanismData(
    mechanism_type="dess_martin",
    title="Dess-Martin 산화 (Periodinane Oxidation)",
    total_steps=3,
    overall_description=(
        "Dess-Martin periodinane(DMP)는 hypervalent I(III) 시약으로 "
        "1차 알코올을 알데히드로, 2차 알코올을 케톤으로 온화하게 산화합니다. "
        "과산화(over-oxidation)가 일어나지 않아 알데히드 합성에 특히 유용합니다. "
        "메커니즘: 리간드 교환 → α-제거 → 생성물 형성."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="리간드 교환 (Ligand Exchange)",
            description=(
                "알코올의 산소 론페어가 DMP의 요오드(I)를 친핵 공격합니다.\n"
                "아세테이트 리간드 하나가 이탈하면서 알코올이 요오드에 결합합니다.\n"
                "I(III) → I(III) 산화 상태 유지 (리간드 치환만 발생)."
            ),
            reactant_smiles="OCC.CC(=O)O[I](OC(C)=O)(OC(C)=O)c1ccccc1C(=O)O",
            product_smiles="CCO[I](OC(C)=O)(OC(C)=O)c1ccccc1C(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "R-OH 론페어",
                          "atom", "I (DMP)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=5),  # O→I attack
                ArrowData("full", "bond", "I-OAc 결합",
                          "atom", "OAc (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=5, to_atom_idx=3),  # I-OAc break
                ArrowData("full", "lone_pair", "OAc⁻ 이탈",
                          "atom", "AcOH 생성", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=4),  # OAc departure
            ],
            labels={"O": "친핵체 (알코올)", "I": "electrophile (DMP)", "OAc": "이탈기"},
            energy_label="리간드 교환",
            reagents="DMP, CH₂Cl₂",
            notes="DMP = 1,1,1-triacetoxy-1,1-dihydro-1,2-benziodoxol-3(1H)-one, I(III)",
        ),
        MechanismStep(
            step_number=2,
            title="α-제거 (α-Elimination)",
            description=(
                "C-H 결합과 I-O 결합이 동시에 절단됩니다 (α-elimination).\n"
                "알파 수소가 아세테이트 산소로 이동하면서 C=O 이중결합이 형성됩니다.\n"
                "요오드는 I(III)에서 I(I)로 환원됩니다."
            ),
            reactant_smiles="CCO[I](OC(C)=O)(OC(C)=O)c1ccccc1C(=O)O",
            product_smiles="CC=O.O[I](OC(C)=O)c1ccccc1C(=O)O",
            arrows=[
                ArrowData("full", "bond", "C-H 결합 (α-수소)",
                          "atom", "OAc 산소", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=4),  # C-H→O
                ArrowData("full", "bond", "O-I 결합",
                          "atom", "I (환원)", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # O-I break
                ArrowData("full", "pi_bond", "C=O 형성",
                          "atom", "카르보닐", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C=O form
            ],
            labels={"H": "α-수소", "C=O": "카르보닐 형성"},
            is_transition_state=True,
            energy_label="전이 상태 (α-제거)",
            notes="동시 메커니즘: C-H 절단 + I-O 절단 + C=O 형성",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알데히드/케톤 + IBA",
            description=(
                "카르보닐 화합물(알데히드 또는 케톤)이 생성됩니다.\n"
                "부산물: 2-iodobenzoic acid (IBA) + acetic acid.\n"
                "DMP는 I(III)→I(I)로 환원되어 IBA가 됩니다."
            ),
            reactant_smiles="CC=O.O[I](OC(C)=O)c1ccccc1C(=O)O",
            product_smiles="CC=O.OI(c1ccccc1C(=O)O)",
            arrows=[],
            labels={"C=O": "알데히드/케톤", "IBA": "2-iodobenzoic acid"},
            energy_label="생성물 (발열)",
            notes="과산화 없음: DMP는 알데히드를 카르복실산으로 산화하지 않음",
        ),
    ],
    energy_diagram=[
        ("알코올 + DMP", 0.0),
        ("리간드 교환\n중간체", -5.0),
        ("α-제거\n전이상태", 15.0),
        ("알데히드/케톤\n+ IBA", -25.0),
    ],
)


# ─── Gabriel Synthesis ──────────────────────────────────────────────────────
# 대표 반응: Phthalimide + R-X → R-NH₂ (1차 아민만)
# 3단계: 탈양자화 → SN2 알킬화 → 히드라진분해

MECHANISMS["gabriel"] = MechanismData(
    mechanism_type="gabriel",
    title="Gabriel 합성 (Primary Amine Synthesis)",
    total_steps=4,
    overall_description=(
        "Gabriel 합성은 프탈이미드를 이용하여 1차 아민만을 선택적으로 합성하는 방법입니다. "
        "프탈이미드 음이온의 SN2 반응으로 N-알킬프탈이미드를 만든 후, "
        "히드라진(N₂H₄)으로 분해하여 유리 1차 아민을 얻습니다. "
        "과알킬화(over-alkylation)가 원천적으로 방지됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="프탈이미드 탈양자화 (Deprotonation)",
            description=(
                "KOH 또는 K₂CO₃에 의해 프탈이미드 N-H가 탈양자화됩니다.\n"
                "생성된 프탈이미드 음이온(potassium phthalimide)은 안정한 친핵체입니다.\n"
                "두 카르보닐에 의한 공명 안정화로 N⁻가 안정합니다."
            ),
            reactant_smiles="O=C1NC(=O)c2ccccc21.[OH-]",
            product_smiles="O=C1[N-]C(=O)c2ccccc21.O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ 론페어",
                          "atom", "N-H 수소", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=2),  # OH→H
                ArrowData("full", "bond", "N-H 결합",
                          "atom", "N (음이온)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=2),  # N-H break
                ArrowData("full", "lone_pair", "N⁻ 공명",
                          "bond", "C=O (공명)", "#4CAF50", 0.4,
                          from_atom_idx=2, to_atom_idx=0),  # N resonance
            ],
            labels={"N-H": "산성 수소 (pKa ~8.3)", "OH⁻": "염기"},
            energy_label="탈양자화 (빠름)",
            reagents="KOH, DMF",
            notes="프탈이미드 pKa ≈ 8.3 (두 C=O의 공명 안정화)",
        ),
        MechanismStep(
            step_number=2,
            title="SN2 알킬화 (N-Alkylation)",
            description=(
                "프탈이미드 음이온(N⁻)이 알킬 할라이드를 SN2 공격합니다.\n"
                "N-알킬프탈이미드가 생성되고 할라이드 이온이 이탈합니다.\n"
                "1차 할라이드에서 가장 효율적 (SN2 특성)."
            ),
            reactant_smiles="O=C1[N-]C(=O)c2ccccc21.CCBr",
            product_smiles="O=C1N(CC)C(=O)c2ccccc21.[Br-]",
            arrows=[
                ArrowData("full", "negative_charge", "N⁻ 론페어",
                          "atom", "C (alpha)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=9),  # N→C
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br⁻ (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=9, to_atom_idx=10),  # C-Br break
                ArrowData("full", "lone_pair", "Br⁻ 이탈",
                          "atom", "할라이드 이온", "#FF9800", 0.3,
                          from_atom_idx=10, to_atom_idx=10),  # Br departure
            ],
            labels={"N⁻": "친핵체", "C-Br": "electrophilic C", "Br": "이탈기"},
            is_transition_state=True,
            energy_label="SN2 전이 상태",
            reagents="R-X (1° alkyl halide)",
            notes="2° halide → E2 부반응 우려, 3° → 불가 (SN2 장벽)",
        ),
        MechanismStep(
            step_number=3,
            title="히드라진분해 (Hydrazinolysis)",
            description=(
                "N₂H₄ (히드라진)가 N-알킬프탈이미드의 카르보닐을 친핵 공격합니다.\n"
                "두 카르보닐 탄소가 순차적으로 공격받아 C-N 결합이 절단됩니다.\n"
                "프탈히드라자이드(부산물)와 유리 아민이 분리됩니다."
            ),
            reactant_smiles="O=C1N(CC)C(=O)c2ccccc21.NN",
            product_smiles="O=C1NNC(=O)c2ccccc21.NCC",
            arrows=[
                ArrowData("full", "lone_pair", "N₂H₄ 론페어",
                          "atom", "C=O (카르보닐)", "#E53935", 0.5,
                          from_atom_idx=9, to_atom_idx=0),  # NH2→C=O
                ArrowData("full", "bond", "C-N(alkyl) 결합",
                          "atom", "N (유리 아민)", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=2),  # C-N break
                ArrowData("full", "lone_pair", "두번째 N₂H₄ 공격",
                          "atom", "C=O (두번째)", "#4CAF50", 0.5,
                          from_atom_idx=9, to_atom_idx=3),  # NH2→C=O(2nd)
            ],
            labels={"N₂H₄": "히드라진", "C-N": "절단 결합"},
            energy_label="히드라진분해",
            reagents="N₂H₄, EtOH, reflux",
            notes="Ing-Manske 변형: 대안으로 NaOH/H₂O 가수분해도 가능",
        ),
        MechanismStep(
            step_number=4,
            title="유리 1차 아민 생성물",
            description=(
                "최종 생성물: 유리 1차 아민 (R-NH₂).\n"
                "부산물: 프탈히드라자이드 (phthalhydrazide), 침전으로 쉽게 분리.\n"
                "과알킬화 없이 순수한 1차 아민만 얻을 수 있음."
            ),
            reactant_smiles="O=C1NNC(=O)c2ccccc21.NCC",
            product_smiles="CCN.O=C1NNC(=O)c2ccccc21",
            arrows=[],
            labels={"R-NH₂": "1차 아민 (생성물)", "phthalhydrazide": "부산물 (침전)"},
            energy_label="생성물 (발열)",
            notes="과알킬화 방지: 프탈이미드가 보호기 역할 → 1차 아민만 생성",
        ),
    ],
    energy_diagram=[
        ("프탈이미드\n+ KOH", 0.0),
        ("K-프탈이미드\n(음이온)", -8.0),
        ("SN2\n전이상태", 18.0),
        ("N-알킬프탈이미드", -10.0),
        ("히드라진분해\n전이상태", 12.0),
        ("R-NH₂\n+ 프탈히드라자이드", -20.0),
    ],
)


# ─── Sharpless Epoxidation ─────────────────────────────────────────────────
# 대표 반응: allyl alcohol + Ti(OiPr)₄ / TBHP / DET → epoxy alcohol (>90% ee)

MECHANISMS["sharpless_epoxidation"] = MechanismData(
    mechanism_type="sharpless_epoxidation",
    title="Sharpless 비대칭 에폭시화 (Asymmetric Epoxidation)",
    total_steps=4,
    overall_description=(
        "Sharpless 비대칭 에폭시화는 Ti(OiPr)₄, TBHP, 그리고 키랄 타르트레이트 에스터(DET)를 "
        "사용하여 알릴 알코올을 높은 거울상이성질체 선택성(>90% ee)으로 에폭시화합니다. "
        "키랄 Ti-peroxo 복합체가 산소를 비대칭적으로 전달합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="키랄 Ti-퍼옥소 복합체 형성",
            description=(
                "Ti(OiPr)₄가 DET 및 TBHP와 리간드 교환하여\n"
                "C₂ 대칭 키랄 Ti 복합체를 형성합니다.\n"
                "이것이 촉매 활성종입니다."
            ),
            reactant_smiles="C=CCO.[Ti](OCC(C)C)(OCC(C)C)(OCC(C)C)OCC(C)C",
            product_smiles="OO[Ti](OCC(C)C)(OCC(C)C)OCC(C)C",
            arrows=[
                ArrowData("full", "lone_pair", "DET 산소",
                          "atom", "Ti 중심", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=3),
                ArrowData("full", "bond", "Ti-OiPr 결합",
                          "atom", "OiPr 이탈", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("full", "lone_pair", "TBHP 배위",
                          "atom", "Ti (peroxo)", "#4CAF50", 0.4,
                          from_atom_idx=6, to_atom_idx=3),
            ],
            labels={"Ti": "루이스 산", "DET": "키랄 리간드", "TBHP": "산화제"},
            energy_label="복합체 형성",
            reagents="Ti(OiPr)₄, (+)-DET, TBHP, CH₂Cl₂, -20°C",
            notes="C₂ 대칭 키랄 포켓이 입체선택성 결정",
        ),
        MechanismStep(
            step_number=2,
            title="알릴 알코올 배위",
            description=(
                "알릴 알코올의 OH가 Ti에 배위합니다.\n"
                "알켄 π계가 타르트레이트 키랄 포켓에 배치됩니다.\n"
                "(+)-DET → β-면, (-)-DET → α-면 산소 전달."
            ),
            reactant_smiles="OO[Ti](OCC(C)C)(OCC(C)C)OCC(C)C.C=CCO",
            product_smiles="OO[Ti](OCC(C)C)(OCC(C)C)OCC=C",
            arrows=[
                ArrowData("full", "lone_pair", "알릴 OH",
                          "atom", "Ti", "#E53935", 0.4,
                          from_atom_idx=7, to_atom_idx=2),
                ArrowData("full", "bond", "Ti-OiPr",
                          "atom", "OiPr 이탈", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "pi_bond", "알켄 π",
                          "atom", "키랄 포켓 배치", "#4CAF50", 0.3,
                          from_atom_idx=8, to_atom_idx=9),
            ],
            labels={"OH": "배위 기능기", "C=C": "에폭시화 대상"},
            is_transition_state=False,
            energy_label="배위 (중간체)",
            reagents="",
            notes="Sharpless 니모닉: (+)-DET → β-면 공격",
        ),
        MechanismStep(
            step_number=3,
            title="비대칭 산소 전달 [‡]",
            description=(
                "TBHP의 산소가 스피로 전이상태를 통해 알켄에 전달됩니다.\n"
                "두 C-O 결합이 동시에 형성 (협동적, 비동기적).\n"
                "속도결정단계. 키랄 리간드가 에난시오면 선택성 제어."
            ),
            reactant_smiles="OO[Ti](OCC(C)C)(OCC(C)C)OCC=C",
            product_smiles="OC1CO1.[Ti](OCC(C)C)(OCC(C)C)OCC(C)C",
            arrows=[
                ArrowData("full", "lone_pair", "퍼옥소 O",
                          "atom", "C=C (근접)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=7),
                ArrowData("full", "lone_pair", "퍼옥소 O",
                          "atom", "C=C (원격)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=8),
                ArrowData("full", "bond", "O-O 결합",
                          "atom", "tBuO 이탈", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"O-O": "절단", "C=C": "에폭시화"},
            is_transition_state=True,
            energy_label="ΔG‡ (속도결정단계)",
            reagents="",
            notes=">90% ee (알릴 알코올), 동역학적 분할도 가능",
        ),
        MechanismStep(
            step_number=4,
            title="에폭시 알코올 생성물",
            description=(
                "에난시오 풍부 2,3-에폭시 알코올 생성.\n"
                "Ti 촉매 방출, 부산물: tert-부탄올.\n"
                "키랄 빌딩 블록으로 광범위 응용."
            ),
            reactant_smiles="OC1CO1.OC(C)(C)C",
            product_smiles="OC1CO1",
            arrows=[],
            labels={"에폭시 알코올": "생성물 (>90% ee)", "tBuOH": "부산물"},
            energy_label="생성물",
            notes="응용: Payne 전위, 개환 반응으로 다양한 키랄 합성 중간체",
        ),
    ],
    energy_diagram=[
        ("알릴 알코올\n+ Ti/DET/TBHP", 0.0),
        ("Ti-퍼옥소\n복합체", -5.0),
        ("알릴 알코올\n배위", -8.0),
        ("스피로 TS\n[‡]", 15.0),
        ("에폭시 알코올\n+ tBuOH", -25.0),
    ],
)

# ─── Wacker Oxidation ──────────────────────────────────────────────────────
# 대표 반응: terminal alkene + PdCl₂/CuCl₂/O₂/H₂O → methyl ketone

MECHANISMS["wacker_oxidation"] = MechanismData(
    mechanism_type="wacker_oxidation",
    title="Wacker 산화 (Terminal Alkene → Methyl Ketone)",
    total_steps=4,
    overall_description=(
        "Wacker 산화는 PdCl₂/CuCl₂ 촉매계를 사용하여 말단 알켄을 메틸 케톤으로 "
        "산화하는 반응입니다. Pd(II)가 알켄을 활성화하고, 물이 Markovnikov 선택성으로 "
        "공격하며, β-수소화물 제거로 케톤이 생성됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Pd(II) η²-알켄 배위",
            description=(
                "PdCl₂가 알켄 π-결합에 η² 배위합니다.\n"
                "Pd(II)는 친전자적이며 알켄을 친핵 공격에 활성화합니다.\n"
                "수용성 조건에서 Cl이 H₂O로 교환될 수 있습니다."
            ),
            reactant_smiles="C=CC.Cl[Pd]Cl",
            product_smiles="C(=C)C.[Pd](Cl)Cl",
            arrows=[
                ArrowData("full", "pi_bond", "알켄 π 전자",
                          "atom", "Pd(II)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=3),
                ArrowData("full", "lone_pair", "Pd d 오비탈",
                          "bond", "C=C (역공여)", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=0),
                ArrowData("full", "lone_pair", "Cl 론페어",
                          "atom", "Pd 잔류", "#4CAF50", 0.2,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"Pd": "친전자 활성화", "C=C": "π-배위"},
            energy_label="배위 (빠름)",
            reagents="PdCl₂, CuCl₂, H₂O/DMF",
            notes="η² 배위: Dewar-Chatt-Duncanson 모델",
        ),
        MechanismStep(
            step_number=2,
            title="H₂O 친핵 공격 (Markovnikov)",
            description=(
                "물이 Pd-활성화 알켄을 공격합니다 (trans to Pd, anti-attack).\n"
                "말단 알켄에서 Markovnikov 선택성: 내부 탄소 공격.\n"
                "β-히드록시 알킬-Pd(II) 중간체 형성."
            ),
            reactant_smiles="C(=C)C.[Pd](Cl)Cl.O",
            product_smiles="CC(O)[Pd](Cl)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C (Markovnikov)", "#E53935", 0.5,
                          from_atom_idx=5, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=C → C-Pd",
                          "atom", "Pd (σ-결합)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=3),
                ArrowData("full", "bond", "O-H",
                          "atom", "탈양자화", "#4CAF50", 0.3,
                          from_atom_idx=5, to_atom_idx=5),
            ],
            labels={"H₂O": "친핵체", "C": "Markovnikov 위치"},
            is_transition_state=True,
            energy_label="친핵 공격 TS",
            reagents="H₂O",
            notes="anti-Pd 공격 (trans-hydroxypalladation)",
        ),
        MechanismStep(
            step_number=3,
            title="β-수소화물 제거 → 에놀 → 케톤",
            description=(
                "β-수소화물 제거로 에놀 생성.\n"
                "에놀이 케토 호변이성질체화로 메틸 케톤 형성.\n"
                "Pd(II) → Pd(0) + HCl 환원."
            ),
            reactant_smiles="CC(O)[Pd](Cl)Cl",
            product_smiles="CC(C)=O.[Pd]",
            arrows=[
                ArrowData("full", "bond", "C-H (β)",
                          "atom", "Pd", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=3),
                ArrowData("full", "bond", "Pd-C",
                          "atom", "Pd(0) 방출", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=1),
                ArrowData("full", "lone_pair", "O (에놀)",
                          "bond", "C=O (케톤화)", "#4CAF50", 0.4,
                          from_atom_idx=2, to_atom_idx=1),
            ],
            labels={"β-H": "제거", "Pd(0)": "환원"},
            energy_label="β-수소화물 제거",
            reagents="",
            notes="에놀-케토 호변이성질체화로 최종 케톤 형성",
        ),
        MechanismStep(
            step_number=4,
            title="촉매 재생: CuCl₂/O₂ 재산화",
            description=(
                "Pd(0)은 CuCl₂에 의해 Pd(II)로 재산화됩니다.\n"
                "Cu(II) → Cu(I), 이후 Cu(I)은 O₂에 의해 재산화.\n"
                "순 반응: 알켄 + O₂ → 케톤 + H₂O (Pd, Cu 모두 촉매적)."
            ),
            reactant_smiles="[Pd].[Cu](Cl)Cl.[Cu](Cl)Cl.O=O",
            product_smiles="Cl[Pd]Cl.[Cu]Cl.[Cu]Cl",
            arrows=[
                ArrowData("full", "lone_pair", "Cu(II)",
                          "atom", "Pd(0)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=0),
                ArrowData("full", "lone_pair", "O₂",
                          "atom", "Cu(I)", "#1565C0", 0.3,
                          from_atom_idx=5, to_atom_idx=1),
                ArrowData("full", "bond", "Pd-Cl 재형성",
                          "atom", "Pd(II)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=0),
            ],
            labels={"Pd(0)": "재산화 대상", "Cu(II)": "산화제", "O₂": "최종 산화제"},
            energy_label="촉매 재생 (발열)",
            reagents="CuCl₂, O₂ (공기)",
            notes="Wacker-Hoechst 공정: 에틸렌 → 아세트알데히드 (산업적)",
        ),
    ],
    energy_diagram=[
        ("알켄\n+ PdCl₂", 0.0),
        ("Pd-알켄\nπ-복합체", -5.0),
        ("H₂O 공격\nTS", 12.0),
        ("β-OH 알킬\nPd 중간체", -3.0),
        ("β-수소화물\n제거 TS", 8.0),
        ("메틸 케톤\n+ Pd(0)", -18.0),
    ],
)

# ─── Stetter Reaction ──────────────────────────────────────────────────────
# 대표 반응: aldehyde + enone → 1,4-dicarbonyl (NHC 촉매, umpolung)

MECHANISMS["stetter_reaction"] = MechanismData(
    mechanism_type="stetter_reaction",
    title="Stetter 반응 (NHC 촉매 Umpolung)",
    total_steps=5,
    overall_description=(
        "Stetter 반응은 NHC(N-헤테로사이클릭 카르벤) 촉매를 사용하여 "
        "알데히드의 극성을 역전(umpolung)시켜 Michael 수용체에 1,4-결합 첨가하는 반응입니다. "
        "Breslow 중간체(아실 음이온 등가체)가 핵심입니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="NHC 카르벤 생성: 티아졸리움 탈양자화",
            description=(
                "티아졸리움 염의 C(2)-H가 염기에 의해 탈양자화됩니다.\n"
                "자유 NHC 카르벤 생성 (싱글릿 바닥상태).\n"
                "N과 S의 π-공여로 안정화."
            ),
            reactant_smiles="C1=C[NH]C(=S)S1.CC(C)([O-])C",
            product_smiles="[C-]1=CSC=N1.OC(C)(C)C",
            arrows=[
                ArrowData("full", "lone_pair", "tBuO⁻",
                          "atom", "C(2)-H", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=3),
                ArrowData("full", "bond", "C-H 결합",
                          "atom", "카르벤 C", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=3),
                ArrowData("full", "lone_pair", "N→C(2) π-공여",
                          "bond", "안정화", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=3),
            ],
            labels={"C(2)-H": "산성 (pKa ~18)", "NHC": "싱글릿 카르벤"},
            energy_label="탈양자화",
            reagents="KOtBu 또는 Et₃N, THF",
            notes="NHC: 채워진 σ(sp²) + 빈 p 오비탈 on C(2)",
        ),
        MechanismStep(
            step_number=2,
            title="NHC + 알데히드 → Breslow 중간체",
            description=(
                "NHC 카르벤이 알데히드 C=O를 공격합니다.\n"
                "사면체 중간체 → Breslow 중간체(에나미놀)로 전환.\n"
                "핵심 umpolung: 알데히드 C(1)이 친핵성으로 전환."
            ),
            reactant_smiles="C1=CN=CS1.CC=O",
            product_smiles="OC(=CN1C=CSC1)C",  # Breslow intermediate (Kekule thiazole)
            arrows=[
                ArrowData("full", "lone_pair", "NHC C: (카르벤)",
                          "atom", "알데히드 C=O", "#E53935", 0.5,
                          from_atom_idx=3, to_atom_idx=5),
                ArrowData("full", "bond", "C=O → C-OH",
                          "atom", "양자 이동", "#1565C0", 0.4,
                          from_atom_idx=6, to_atom_idx=5),
                ArrowData("full", "lone_pair", "OH",
                          "bond", "에나미놀 형성", "#4CAF50", 0.3,
                          from_atom_idx=6, to_atom_idx=5),
            ],
            labels={"NHC": "친핵 카르벤", "C=O": "친전자체"},
            is_transition_state=False,
            energy_label="Breslow 중간체",
            reagents="알데히드",
            notes="Breslow (1958): 아실 음이온 등가체 (d¹ 합성자)",
        ),
        MechanismStep(
            step_number=3,
            title="1,4-결합 첨가 (Michael 첨가)",
            description=(
                "Breslow 중간체가 α,β-불포화 카르보닐에\n"
                "1,4-결합(Michael) 첨가를 수행합니다.\n"
                "β-위치에 C-C 결합 형성. 열역학적 제어."
            ),
            reactant_smiles="OC(=CN1C=CSC1)C.C=CC(=O)C",  # Breslow + Michael acceptor
            product_smiles="OC(CC(CC(=O)C)N1C=CSC1)C",  # 1,4-addition product (Kekule thiazole)
            arrows=[
                ArrowData("full", "lone_pair", "Breslow C (친핵)",
                          "atom", "β-C (Michael)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=7),
                ArrowData("full", "pi_bond", "C=C (에논)",
                          "atom", "에놀레이트", "#1565C0", 0.4,
                          from_atom_idx=7, to_atom_idx=8),
                ArrowData("full", "lone_pair", "O (에놀레이트)",
                          "bond", "공명 안정화", "#4CAF50", 0.3,
                          from_atom_idx=9, to_atom_idx=8),
            ],
            labels={"Breslow": "친핵 탄소", "β-C": "공격 위치"},
            energy_label="1,4-첨가 TS",
            reagents="α,β-불포화 카르보닐",
            notes="1,4- > 1,2- 선택성 (열역학적 제어)",
        ),
        MechanismStep(
            step_number=4,
            title="NHC 방출 (촉매 순환)",
            description=(
                "NHC가 사면체 중간체에서 방출됩니다.\n"
                "자유 카르벤 촉매 재생.\n"
                "양자 이동이 수반될 수 있습니다."
            ),
            reactant_smiles="OC(CC(CC(=O)C)N1C=CSC1)C",  # NHC adduct (Kekule thiazole)
            product_smiles="O=C(C)CC(CC(=O)C).C1=CN=CS1",
            arrows=[
                ArrowData("full", "bond", "C-N(NHC) 결합",
                          "atom", "NHC 이탈", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=5),
                ArrowData("full", "lone_pair", "O",
                          "bond", "C=O 재형성", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "lone_pair", "NHC C:",
                          "atom", "재생 카르벤", "#4CAF50", 0.3,
                          from_atom_idx=5, to_atom_idx=5),
            ],
            labels={"C-N": "절단", "NHC": "재생"},
            energy_label="촉매 방출",
            reagents="",
            notes="촉매 부하: 10-20 mol%. 부반응: 벤조인 축합",
        ),
        MechanismStep(
            step_number=5,
            title="1,4-디카르보닐 생성물",
            description=(
                "1,4-디카르보닐 화합물 분리.\n"
                "직접법으로는 접근 어려운 구조 (umpolung 필요).\n"
                "응용: Robinson 환화, Paal-Knorr 합성."
            ),
            reactant_smiles="O=C(C)CC(=O)CC(=O)C",
            product_smiles="O=C(C)CCC(=O)C",
            arrows=[],
            labels={"1,4-디케톤": "생성물"},
            energy_label="생성물 (발열)",
            notes="Paal-Knorr: 1,4-디케톤 → 퓨란/피롤",
        ),
    ],
    energy_diagram=[
        ("티아졸리움\n+ 염기", 0.0),
        ("NHC 카르벤", -3.0),
        ("Breslow\n중간체", -8.0),
        ("1,4-첨가\nTS", 10.0),
        ("NHC 방출", -5.0),
        ("1,4-디카르보닐", -22.0),
    ],
)

# ─── Reformatsky Reaction ──────────────────────────────────────────────────
# 대표 반응: α-bromoester + Zn + aldehyde → β-hydroxy ester

MECHANISMS["reformatsky"] = MechanismData(
    mechanism_type="reformatsky",
    title="Reformatsky 반응 (Zn 에놀레이트 + 카르보닐)",
    total_steps=4,
    overall_description=(
        "Reformatsky 반응은 α-할로에스터를 아연과 반응시켜 유기아연 에놀레이트를 만든 후, "
        "알데히드 또는 케톤의 카르보닐에 친핵 첨가하여 β-히드록시 에스터를 생성합니다. "
        "Grignard와 달리 에스터와 반응하지 않습니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아연 삽입: Reformatsky 시약 형성",
            description=(
                "아연 금속이 α-브로모에스터의 C-Br 결합에 삽입.\n"
                "Zn(0) → Zn(II): 유기아연 에놀레이트 형성.\n"
                "활성화 필요: Zn-Cu 커플, TMSCl, 또는 초음파."
            ),
            reactant_smiles="BrCC(=O)OCC.[Zn]",
            product_smiles="[Zn](Br)CC(=O)OCC",
            arrows=[
                ArrowData("full", "lone_pair", "Zn(0)",
                          "bond", "C-Br 결합", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=0),
                ArrowData("full", "bond", "C-Br",
                          "atom", "Br (Zn에 결합)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),
                ArrowData("full", "lone_pair", "Zn",
                          "atom", "C (새 결합)", "#4CAF50", 0.4,
                          from_atom_idx=5, to_atom_idx=1),
            ],
            labels={"Zn": "산화적 첨가", "C-Br": "절단/재형성"},
            energy_label="Zn 삽입",
            reagents="Zn (활성화), THF, reflux",
            notes="Grignard와 달리 에스터 기능기에 비반응성",
        ),
        MechanismStep(
            step_number=2,
            title="카르보닐 친핵 첨가",
            description=(
                "Reformatsky 시약이 알데히드/케톤 C=O에 첨가.\n"
                "Zn이 C=O 산소에 배위 (루이스 산 활성화).\n"
                "α-탄소가 카르보닐 탄소를 공격.\n"
                "Zimmerman-Traxler 6원 TS로 적당한 부분입체선택성."
            ),
            reactant_smiles="[Zn](Br)CC(=O)OCC.CC=O",
            product_smiles="CC(O[Zn]Br)CC(=O)OCC",
            arrows=[
                ArrowData("full", "lone_pair", "α-C (에놀레이트)",
                          "atom", "C=O 탄소", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=6),
                ArrowData("full", "lone_pair", "C=O 산소",
                          "atom", "Zn (배위)", "#1565C0", 0.4,
                          from_atom_idx=7, to_atom_idx=0),
                ArrowData("full", "bond", "C=O → C-O",
                          "atom", "Zn 알콕사이드", "#4CAF50", 0.3,
                          from_atom_idx=6, to_atom_idx=7),
            ],
            labels={"α-C": "친핵체", "C=O": "친전자체", "Zn": "루이스 산"},
            is_transition_state=True,
            energy_label="첨가 TS (Zimmerman-Traxler)",
            reagents="알데히드 또는 케톤",
            notes="6원 의자형 TS → 적당한 anti-선택성",
        ),
        MechanismStep(
            step_number=3,
            title="수성 후처리: Zn 알콕사이드 가수분해",
            description=(
                "묽은 HCl 또는 NH₄Cl로 수성 후처리.\n"
                "Zn-O 결합 절단, 유리 β-히드록시 에스터 방출.\n"
                "Zn 염은 수층으로 추출."
            ),
            reactant_smiles="CC(O[Zn]Br)CC(=O)OCC.[H+]",
            product_smiles="CC(O)CC(=O)OCC.[Zn+2].[Br-]",
            arrows=[
                ArrowData("full", "lone_pair", "H₃O⁺",
                          "atom", "O-Zn", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=2),
                ArrowData("full", "bond", "O-Zn",
                          "atom", "Zn 이탈", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "lone_pair", "Br⁻",
                          "atom", "Zn²⁺", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"O-Zn": "절단", "H⁺": "양성자화"},
            energy_label="후처리 (발열)",
            reagents="dil. HCl 또는 sat. NH₄Cl (aq)",
            notes="유기층 추출로 생성물 분리",
        ),
        MechanismStep(
            step_number=4,
            title="β-히드록시 에스터 생성물",
            description=(
                "β-히드록시 에스터 분리.\n"
                "탈수하면 α,β-불포화 에스터 (E1cb).\n"
                "장점: 에스터 자기축합 없음, 온화한 조건."
            ),
            reactant_smiles="CC(O)CC(=O)OCC",
            product_smiles="CC(O)CC(=O)OCC",
            arrows=[],
            labels={"β-OH 에스터": "생성물"},
            energy_label="생성물 (발열)",
            notes="현대 변형: Rathke 수정 (LDA + ZnCl₂)",
        ),
    ],
    energy_diagram=[
        ("α-브로모에스터\n+ Zn", 0.0),
        ("Reformatsky\n시약", -12.0),
        ("카르보닐 첨가\nTS", 8.0),
        ("Zn 알콕사이드\n중간체", -15.0),
        ("β-히드록시\n에스터", -20.0),
    ],
)

# ─── Sonogashira Coupling ──────────────────────────────────────────────────
# 대표 반응: Ar-X + RC≡CH → Ar-C≡CR (Pd/Cu 이중 촉매)

MECHANISMS["sonogashira_coupling"] = MechanismData(
    mechanism_type="sonogashira_coupling",
    title="Sonogashira 커플링 (Pd/Cu 이중 촉매)",
    total_steps=4,
    overall_description=(
        "Sonogashira 커플링은 Pd(0)/Cu(I) 이중 촉매계를 사용하여 "
        "아릴 할라이드와 말단 알카인을 커플링하는 반응입니다. "
        "Pd 순환(산화적 첨가→트랜스메탈화→환원적 제거)과 "
        "Cu 순환(아세틸라이드 형성)이 상호 연동됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가: Pd(0) + Ar-X → Ar-Pd(II)-X",
            description=(
                "Pd(0)이 Ar-X 결합에 삽입 (Suzuki/Heck와 동일 메커니즘).\n"
                "Pd(0) → Pd(II): 2전자 산화.\n"
                "반응성: Ar-I > Ar-Br > Ar-OTf >> Ar-Cl."
            ),
            reactant_smiles="c1ccc(Br)cc1.[Pd]",
            product_smiles="c1ccc([Pd]Br)cc1",
            arrows=[
                ArrowData("full", "lone_pair", "Pd(0) d 전자",
                          "bond", "Ar-X 결합", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=3),
                ArrowData("full", "bond", "C-Br",
                          "atom", "Pd-Br 형성", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=5),
                ArrowData("full", "lone_pair", "Pd",
                          "atom", "C-Pd 형성", "#4CAF50", 0.4,
                          from_atom_idx=6, to_atom_idx=3),
            ],
            labels={"Pd(0)": "14e⁻ 활성종", "Ar-Br": "기질"},
            energy_label="산화적 첨가",
            reagents="Pd(PPh₃)₂Cl₂, CuI, Et₃N",
            notes="cis 첨가 → 이후 cis/trans 이성질화 가능",
        ),
        MechanismStep(
            step_number=2,
            title="Cu(I) 아세틸라이드 형성 (Cu 순환)",
            description=(
                "말단 알카인이 아민 염기에 의해 탈양자화됩니다.\n"
                "Cu(I)이 π-산으로 알카인에 배위하여 C-H 산성도 증가.\n"
                "Cu 아세틸라이드 (RC≡C-Cu) 형성."
            ),
            reactant_smiles="C#CC.[Cu]I.CCN(CC)CC",
            product_smiles="[Cu]C#CC.[NH+](CC)(CC)CC.[I-]",
            arrows=[
                ArrowData("full", "lone_pair", "Cu(I) d 전자",
                          "bond", "C≡C π", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=0),
                ArrowData("full", "lone_pair", "Et₃N",
                          "atom", "≡C-H", "#1565C0", 0.4,
                          from_atom_idx=5, to_atom_idx=0),
                ArrowData("full", "bond", "C-Cu",
                          "atom", "σ-아세틸라이드", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=3),
            ],
            labels={"Cu(I)": "π-산", "≡C-H": "활성화", "Et₃N": "염기"},
            energy_label="Cu 아세틸라이드 형성",
            reagents="CuI (1-5 mol%), Et₃N",
            notes="Cu 순환: Cu-I → Cu-C≡CR → Cu-X (재생)",
        ),
        MechanismStep(
            step_number=3,
            title="트랜스메탈화: Cu → Pd",
            description=(
                "Cu 아세틸라이드의 알키닐기가 Pd(II)로 이동.\n"
                "Pd-X 결합 절단, Cu-X 재형성 (Cu 순환 턴오버).\n"
                "Ar-Pd-C≡CR (cis 배열) 형성."
            ),
            reactant_smiles="c1ccc([Pd]Br)cc1.[Cu]C#CC",
            product_smiles="c1ccc([Pd]C#CC)cc1.[Cu]Br",
            arrows=[
                ArrowData("full", "bond", "Cu-C≡C",
                          "atom", "Pd", "#E53935", 0.5,
                          from_atom_idx=7, to_atom_idx=6),
                ArrowData("full", "bond", "Pd-Br",
                          "atom", "Cu", "#1565C0", 0.4,
                          from_atom_idx=6, to_atom_idx=7),
                ArrowData("full", "lone_pair", "Br",
                          "atom", "Cu-Br 재형성", "#4CAF50", 0.3,
                          from_atom_idx=5, to_atom_idx=7),
            ],
            labels={"Cu-C≡C": "이동 기질", "Pd-X": "교환"},
            energy_label="트랜스메탈화",
            reagents="",
            notes="Cu(I) 재생으로 촉매 순환 완성",
        ),
        MechanismStep(
            step_number=4,
            title="환원적 제거: Ar-C≡CR + Pd(0)",
            description=(
                "Ar과 C≡CR이 Pd에서 환원적 제거.\n"
                "Pd(II) → Pd(0): 2전자 환원.\n"
                "새로운 Ar-C≡C 결합 형성 (sp²-sp 커플링).\n"
                "Pd(0)은 촉매 순환에 재진입."
            ),
            reactant_smiles="c1ccc([Pd]C#CC)cc1",
            product_smiles="c1ccc(C#CC)cc1.[Pd]",
            arrows=[
                ArrowData("full", "bond", "Pd-C(Ar)",
                          "bond", "C-C≡C (새 결합)", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=3),
                ArrowData("full", "bond", "Pd-C(≡C)",
                          "atom", "Pd(0) 방출", "#1565C0", 0.3,
                          from_atom_idx=6, to_atom_idx=7),
                ArrowData("full", "lone_pair", "Pd(0)",
                          "atom", "촉매 재생", "#4CAF50", 0.3,
                          from_atom_idx=6, to_atom_idx=6),
            ],
            labels={"Ar-C≡C": "새 결합", "Pd(0)": "재생"},
            energy_label="환원적 제거 (발열)",
            notes="응용: 공액 재료, 천연물 합성, 클릭 화학 전구체",
        ),
    ],
    energy_diagram=[
        ("Ar-X + RC≡CH\n+ Pd(0)/CuI", 0.0),
        ("Ar-Pd(II)-X\n(산화적 첨가)", 8.0),
        ("Cu 아세틸라이드\n형성", 3.0),
        ("트랜스메탈화\nAr-Pd-C≡CR", 5.0),
        ("환원적 제거\nTS", 10.0),
        ("Ar-C≡CR\n+ Pd(0)", -25.0),
    ],
)


# ─── Sharpless Dihydroxylation ─────────────────────────────────────────────
# 대표 반응: alkene + OsO₄ (cat.) + AD-mix + NMO → syn-1,2-diol (>90% ee)
# Rule P exclusion guard (M1370 G3 patch):
#   Sharpless Dihydroxylation 트리거 조건: OsO₄ + 키랄 리간드(AD-mix/DHQ 계열) 필수
#   일반 Dihydroxylation(KMnO₄/H₂O₂)과 구분: Sharpless = OsO₄ + 비대칭 키랄 = 특수 패턴
#   exclusion: OsO₄ 없으면 sharpless_dihydroxylation 적용 금지 → 일반 산화 반응 분기
#   Sharpless Epoxidation과 구분: 에폭시화=Ti(OiPr)₄+TBHP+타르트레이트, 디히드록실화=OsO₄+AD-mix

MECHANISMS["sharpless_dihydroxylation"] = MechanismData(
    mechanism_type="sharpless_dihydroxylation",
    title="Sharpless 비대칭 디히드록실화 (Asymmetric Dihydroxylation)",
    total_steps=4,
    overall_description=(
        "Sharpless 비대칭 디히드록실화는 촉매량의 OsO₄와 키랄 리간드(AD-mix)를 사용하여 "
        "알켄을 높은 거울상이성질체 선택성(>90% ee)으로 syn-1,2-디올로 산화합니다. "
        "NMO 또는 K₃Fe(CN)₆가 Os(VI)→Os(VIII) 재산화제 역할을 합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="OsO₄ + 키랄 리간드 → Os-알켄 [3+2] 고리첨가",
            description=(
                "OsO₄(촉매, 0.2-2 mol%)가 알켄과 [3+2] 고리첨가 반응.\n"
                "AD-mix-α((DHQ)₂PHAL) 또는 AD-mix-β((DHQD)₂PHAL) 키랄 환경 제공.\n"
                "두 C-O 결합이 같은 면에서 동시 형성 (syn 첨가)."
            ),
            reactant_smiles="C=CC.O=[Os](=O)(=O)=O",
            product_smiles="O1[Os](=O)(=O)OC1C",
            arrows=[
                ArrowData("full", "lone_pair", "Os=O",
                          "bond", "C=C (proximal)", "#E53935", 0.5,
                          from_atom_idx=4, to_atom_idx=0),
                ArrowData("full", "lone_pair", "Os=O",
                          "bond", "C=C (distal)", "#E53935", 0.5,
                          from_atom_idx=4, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=C π 결합",
                          "atom", "끊어짐", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"OsO₄": "산화제 (촉매)", "C=C": "[3+2] 대상"},
            energy_label="[3+2] 고리첨가",
            reagents="OsO₄ (cat.), AD-mix-β, t-BuOH/H₂O",
            notes="입체결정 단계: syn 첨가, >90% ee",
        ),
        MechanismStep(
            step_number=2,
            title="오스메이트(VI) 에스터 중간체",
            description=(
                "5원환 오스메이트(VI) 에스터 형성.\n"
                "Os는 Os(VIII)→Os(VI)로 환원.\n"
                "키랄 리간드가 공격 면 결정: AD-mix-α→α면, AD-mix-β→β면."
            ),
            reactant_smiles="O1[Os](=O)(=O)OC1C",
            product_smiles="O1[Os](=O)(=O)OC1C",
            arrows=[],
            labels={"오스메이트 에스터": "5원환 중간체", "Os(VI)": "환원된 Os"},
            is_transition_state=False,
            energy_label="오스메이트 에스터 (중간체)",
            notes="5원환: Os, 2×O, 2×C",
        ),
        MechanismStep(
            step_number=3,
            title="오스메이트 에스터 가수분해 + Os(VI)→Os(VIII) 재산화",
            description=(
                "NaOH/H₂O로 오스메이트 에스터 가수분해.\n"
                "Os(VI) → Os(VIII) 재산화: NMO 또는 K₃Fe(CN)₆.\n"
                "촉매적 OsO₄ 사용 가능 (0.2-2 mol%)."
            ),
            reactant_smiles="O1[Os](=O)(=O)OC1C.O",
            product_smiles="OC(O)C.O=[Os](=O)(=O)=O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O",
                          "atom", "Os", "#E53935", 0.4,
                          from_atom_idx=7, to_atom_idx=1),
                ArrowData("full", "bond", "Os-O(알킬)",
                          "atom", "가수분해", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),
            ],
            labels={"NMO": "재산화제", "H₂O": "가수분해"},
            energy_label="가수분해 + 재산화",
            reagents="NMO 또는 K₃Fe(CN)₆, NaOH/H₂O",
            notes="Os 촉매 재생 (턴오버)",
        ),
        MechanismStep(
            step_number=4,
            title="syn-1,2-디올 생성물 (>90% ee)",
            description=(
                "syn-1,2-디올 생성물.\n"
                "두 OH기가 같은 면 (syn 첨가).\n"
                "노벨상 2001 (K.B. Sharpless)."
            ),
            reactant_smiles="OC(O)C",
            product_smiles="OC(O)C",
            arrows=[],
            labels={"syn-디올": "생성물 (>90% ee)"},
            energy_label="생성물",
            notes="응용: 천연물 합성, 폴리엔 위치선택적 디히드록실화",
        ),
    ],
    energy_diagram=[
        ("알켄 + OsO₄\n+ AD-mix", 0.0),
        ("[3+2] TS", 12.0),
        ("오스메이트\n에스터", -8.0),
        ("가수분해\nTS", 5.0),
        ("syn-1,2-디올\n+ OsO₄(재생)", -22.0),
    ],
)


# ─── Olefin Metathesis ────────────────────────────────────────────────────
# 대표 반응: 2 alkenes + Grubbs Ru catalyst → new alkenes + ethylene

MECHANISMS["olefin_metathesis"] = MechanismData(
    mechanism_type="olefin_metathesis",
    title="올레핀 메타세시스 (Olefin Metathesis)",
    total_steps=3,
    overall_description=(
        "올레핀 메타세시스는 Grubbs(Ru) 또는 Schrock(Mo/W) 촉매를 사용하여 "
        "알켄의 알킬리덴 조각을 교환하는 반응입니다. "
        "[2+2] 고리첨가로 메탈라시클로부탄을 형성한 후 역-[2+2]로 새 알켄을 생성합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="[2+2] 고리첨가: Ru=CHR + 알켄 → 메탈라시클로부탄",
            description=(
                "Grubbs 촉매(Ru=CHPh)가 알켄과 [2+2] 고리첨가.\n"
                "4원환 메탈라시클로부탄 형성.\n"
                "Chauvin 메커니즘 (노벨상 2005)."
            ),
            reactant_smiles="C=CC.[Ru]=CC1=CC=CC=C1",
            product_smiles="C1C[Ru]C1",
            arrows=[
                ArrowData("full", "pi_bond", "Ru=C",
                          "bond", "C=C (알켄)", "#E53935", 0.5,
                          from_atom_idx=3, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=C π",
                          "atom", "Ru", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=3),
            ],
            labels={"Ru=CHR": "카르벤 촉매", "C=C": "[2+2] 대상"},
            energy_label="[2+2] 고리첨가",
            reagents="Grubbs 2nd gen (5 mol%), CH₂Cl₂, 40°C",
            notes="Chauvin 메커니즘: [2+2] → 메탈라시클로부탄 → 역-[2+2]",
        ),
        MechanismStep(
            step_number=2,
            title="역-[2+2]: 메탈라시클로부탄 → 새 알켄 + Ru=CHR'",
            description=(
                "메탈라시클로부탄이 반대 방향으로 역-[2+2] 고리역전.\n"
                "생산적 메타세시스: 알킬리덴 조각 교환.\n"
                "에틸렌(CH₂=CH₂) 부산물 방출."
            ),
            reactant_smiles="C1C[Ru]C1",
            product_smiles="C=C.[Ru]=C",
            arrows=[
                ArrowData("full", "bond", "C-Ru",
                          "atom", "새 C=C", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=2),
                ArrowData("full", "bond", "C-C",
                          "atom", "Ru=C 재형성", "#1565C0", 0.4,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"메탈라시클로부탄": "4원환 중간체"},
            is_transition_state=False,
            energy_label="역-[2+2] (중간체)",
            notes="에틸렌 방출이 RCM 평형 이동에 기여",
        ),
        MechanismStep(
            step_number=3,
            title="생성물 알켄 + 에틸렌 부산물",
            description=(
                "새 알켄 생성물.\n"
                "RCM: 분자 내 고리 닫힘 (거대고리 등).\n"
                "CM: 분자 간 교환. ROMP: 변형 고리 개환."
            ),
            reactant_smiles="C=C.C=C",
            product_smiles="C=C",
            arrows=[],
            labels={"생성물": "새 알켄", "CH₂=CH₂": "부산물"},
            energy_label="생성물",
            notes="응용: 거대고리 락톤, 고분자, 천연물 합성 (노벨상 2005)",
        ),
    ],
    energy_diagram=[
        ("알켄 + Ru=CHR", 0.0),
        ("[2+2] TS", 10.0),
        ("메탈라시클로\n부탄", -3.0),
        ("역-[2+2] TS", 8.0),
        ("새 알켄\n+ CH₂=CH₂", -5.0),
    ],
)


# ─── Ene Reaction ─────────────────────────────────────────────────────────
# 대표 반응: allylsilane + aldehyde → homoallylic alcohol (concerted)

MECHANISMS["ene_reaction"] = MechanismData(
    mechanism_type="ene_reaction",
    title="엔 반응 (Ene Reaction)",
    total_steps=2,
    overall_description=(
        "엔 반응은 알릴 C-H 결합이 엔오필(C=O, C=C 등)로 이동하면서 "
        "새 C-C 결합이 형성되고 이중결합이 이동하는 열적 페리고리 반응입니다. "
        "Woodward-Hoffmann 규칙에 의해 열적으로 허용([σ2s+π2s+π2s])됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="협동적 엔 반응 전이상태 [‡]",
            description=(
                "6전자 고리형 전이상태.\n"
                "σ(C-H) + π(C=C, ene) + π(C=X, enophile) 동시 관여.\n"
                "알릴 H가 엔오필로 초안면 이동. C-C 결합 형성 + C=C 이동."
            ),
            reactant_smiles="C=CCC.C=O",
            product_smiles="OCC(/C)=C\\C",
            arrows=[
                ArrowData("full", "bond", "C-H σ 결합",
                          "atom", "엔오필 C/O", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=5),
                ArrowData("full", "pi_bond", "C=C π",
                          "bond", "C=C 이동", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "atom", "C (ene)",
                          "atom", "C (enophile)", "#4CAF50", 0.5,
                          from_atom_idx=0, to_atom_idx=4),
            ],
            labels={"C-H": "σ 결합 끊어짐", "C=C": "이동", "C-C": "형성"},
            is_transition_state=True,
            energy_label="ΔG‡ (엔 반응 TS)",
            reagents="열 또는 Lewis acid (AlCl₃, SnCl₄)",
            notes="Woodward-Hoffmann: [σ2s+π2s+π2s] 열적 허용",
        ),
        MechanismStep(
            step_number=2,
            title="생성물 (호모알릴 알코올 등)",
            description=(
                "이중결합 이동된 생성물.\n"
                "엔오필=포름알데히드 → 호모알릴 알코올.\n"
                "엔오필=singlet O₂ → 알릴 하이드로퍼옥사이드."
            ),
            reactant_smiles="OCC(/C)=C\\C",
            product_smiles="OCC(/C)=C\\C",
            arrows=[],
            labels={"생성물": "호모알릴 알코올"},
            energy_label="생성물",
            notes="응용: Conia-ene 고리화, terpene 합성",
        ),
    ],
    energy_diagram=[
        ("ene + enophile", 0.0),
        ("협동적 TS [‡]", 25.0),
        ("생성물", -10.0),
    ],
)


# ─── 1,3-Dipolar Cycloaddition ────────────────────────────────────────────
# 대표 반응: azide + alkyne → 1,2,3-triazole (Huisgen / CuAAC click)

MECHANISMS["dipolar_cycloaddition"] = MechanismData(
    mechanism_type="dipolar_cycloaddition",
    title="1,3-쌍극자 고리첨가 (1,3-Dipolar Cycloaddition)",
    total_steps=3,
    overall_description=(
        "1,3-쌍극자 고리첨가는 1,3-쌍극자(아자이드, 디아조, 니트론 등)가 "
        "친쌍극자체(알켄, 알카인)와 협동적 [π4s+π2s] 고리첨가를 통해 "
        "5원환 헤테로사이클을 형성하는 반응입니다. "
        "노벨상 2022 (클릭 화학: Sharpless, Meldal, Bertozzi)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="1,3-쌍극자 접근",
            description=(
                "1,3-쌍극자(4π 전자)가 친쌍극자체에 접근.\n"
                "FMO 분석: HOMO(쌍극자)-LUMO(친쌍극자체) 상호작용.\n"
                "위치선택성은 FMO 계수로 예측."
            ),
            reactant_smiles="[N-]=[N+]=NC.C#CC",
            product_smiles="[N-]=[N+]=NC.C#CC",
            arrows=[
                ArrowData("full", "lone_pair", "쌍극자 말단",
                          "atom", "친쌍극자체", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=4),
                ArrowData("full", "lone_pair", "쌍극자 다른 말단",
                          "atom", "친쌍극자체", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=5),
            ],
            labels={"아자이드": "1,3-쌍극자 (4π)", "알카인": "친쌍극자체 (2π)"},
            energy_label="접근 (van der Waals)",
            reagents="CuSO₄·5H₂O, sodium ascorbate, t-BuOH/H₂O (CuAAC)",
            notes="Type I (정상)/Type III (역전) 전자 요구",
        ),
        MechanismStep(
            step_number=2,
            title="협동적 [π4s+π2s] 고리첨가 [‡]",
            description=(
                "열적으로 허용된 [4πs+2πs] 고리첨가 (Woodward-Hoffmann).\n"
                "두 새 σ-결합 동시 형성.\n"
                "전이상태: 방향족 (6전자 고리형 배열)."
            ),
            reactant_smiles="[N-]=[N+]=NC.C#CC",
            product_smiles="c1nn[nH]c1C",
            arrows=[
                ArrowData("full", "lone_pair", "N(말단)",
                          "atom", "C(알카인)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=4),
                ArrowData("full", "pi_bond", "C≡C π",
                          "atom", "끊어짐", "#1565C0", 0.4,
                          from_atom_idx=4, to_atom_idx=5),
                ArrowData("full", "lone_pair", "N(다른 말단)",
                          "atom", "C(알카인)", "#4CAF50", 0.5,
                          from_atom_idx=2, to_atom_idx=5),
            ],
            labels={"TS": "방향족 6전자"},
            is_transition_state=True,
            energy_label="ΔG‡ ([π4s+π2s])",
            notes="CuAAC: Cu(I)가 아자이드-알카인 배위 → 1,4-위치선택",
        ),
        MechanismStep(
            step_number=3,
            title="1,2,3-트리아졸 생성물",
            description=(
                "5원환 헤테로사이클 생성.\n"
                "CuAAC: 1,4-이치환 1,2,3-트리아졸만 생성.\n"
                "RuAAC: 1,5-위치이성질체. 열적: 1,4/1,5 혼합물."
            ),
            reactant_smiles="c1nn[nH]c1C",
            product_smiles="c1nn[nH]c1C",
            arrows=[],
            labels={"트리아졸": "5원환 생성물"},
            energy_label="생성물",
            notes="응용: 바이오컨쥬게이션, 의약화학, 재료과학 (노벨상 2022)",
        ),
    ],
    energy_diagram=[
        ("아자이드 + 알카인", 0.0),
        ("접근", 2.0),
        ("[π4s+π2s] TS", 20.0),
        ("1,2,3-트리아졸", -35.0),
    ],
)


# ─── Corey-Chaykovsky Reaction ────────────────────────────────────────────
# 대표 반응: ketone + Me₃S⁺I⁻ + NaH → epoxide + Me₂S

MECHANISMS["corey_chaykovsky"] = MechanismData(
    mechanism_type="corey_chaykovsky",
    title="Corey-Chaykovsky 반응 (에폭시드/시클로프로판 형성)",
    total_steps=3,
    overall_description=(
        "Corey-Chaykovsky 반응은 술포늄/술폭소늄 일라이드가 카르보닐(C=O)에 "
        "친핵 공격하여 에폭시드(술포늄) 또는 시클로프로판(술폭소늄)을 형성합니다. "
        "일라이드는 Me₃S⁺I⁻(또는 Me₃S⁺(O)I⁻) + NaH로 생성됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="일라이드 생성: 술포늄염 + NaH",
            description=(
                "트리메틸술포늄 아이오다이드(Me₃S⁺I⁻)를 NaH로 탈양자화.\n"
                "술포늄 일라이드(Me₂S=CH₂) 생성: C에 음전하.\n"
                "술폭소늄 일라이드: S=O 공명으로 더 안정화."
            ),
            reactant_smiles="C[S+](C)C.[Na][H]",
            product_smiles="[CH2-][S+](C)C",
            arrows=[
                ArrowData("full", "lone_pair", "NaH (H⁻)",
                          "atom", "S-CH₃ (H 추출)", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=0),
                ArrowData("full", "bond", "C-H",
                          "atom", "C⁻ (일라이드)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=0),
            ],
            labels={"NaH": "강염기", "S⁺": "술포늄"},
            energy_label="탈양자화",
            reagents="Me₃S⁺I⁻, NaH, DMSO, 0°C→RT",
            notes="술포늄: 반응성 높음→에폭시드. 술폭소늄: 안정→시클로프로판",
        ),
        MechanismStep(
            step_number=2,
            title="일라이드 C=O 공격 → 베타인 → 고리 닫힘",
            description=(
                "친핵성 일라이드 탄소가 C=O 공격.\n"
                "쌍성이온 베타인 중간체 형성.\n"
                "분자 내 SN2: O⁻(또는 C⁻)가 Me₂S를 치환 → 에폭시드(또는 시클로프로판)."
            ),
            reactant_smiles="[CH2-][S+](C)C.CC=O",
            product_smiles="C1OC1C.CSC",
            arrows=[
                ArrowData("full", "lone_pair", "C⁻ (일라이드)",
                          "atom", "C=O (카르보닐)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=4),
                ArrowData("full", "lone_pair", "O⁻",
                          "atom", "CH₂ (고리닫힘)", "#1565C0", 0.4,
                          from_atom_idx=5, to_atom_idx=0),
                ArrowData("full", "bond", "C-S",
                          "atom", "Me₂S 이탈", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"베타인": "쌍성이온 중간체", "SN2": "고리 닫힘"},
            is_transition_state=False,
            energy_label="베타인 형성 + 고리 닫힘",
            reagents="",
            notes="술포늄→에폭시드 (동역학), 술폭소늄→시클로프로판 (열역학)",
        ),
        MechanismStep(
            step_number=3,
            title="에폭시드(또는 시클로프로판) + Me₂S 부산물",
            description=(
                "에폭시드 또는 시클로프로판 생성물.\n"
                "부산물: Me₂S(악취) 또는 DMSO.\n"
                "이민(C=N)과 반응 시 아지리딘 생성 가능."
            ),
            reactant_smiles="C1OC1C.CSC",
            product_smiles="C1OC1C",
            arrows=[],
            labels={"에폭시드": "생성물", "Me₂S": "부산물"},
            energy_label="생성물",
            notes="응용: 테르펜 합성, Simmons-Smith 대안",
        ),
    ],
    energy_diagram=[
        ("Me₃S⁺ + NaH", 0.0),
        ("일라이드\n생성", -5.0),
        ("C=O 공격\n(베타인)", 12.0),
        ("고리닫힘\nTS", 15.0),
        ("에폭시드\n+ Me₂S", -20.0),
    ],
)


# ─── Bamford-Stevens Reaction ─────────────────────────────────────────────
# 대표 반응: tosylhydrazone + NaOMe → diazo → carbene → alkene

MECHANISMS["bamford_stevens"] = MechanismData(
    # Rule P exclusion guard (M1370 G3 patch):
    #   필수 트리거 조건: 기질에 토실히드라존 (-NHNHTs / -N=N-Ts) 구조 존재
    #   Aldol 과매칭 방지: 단순 케톤 + 염기 패턴과 구분 필수
    #   exclusion: Bamford-Stevens는 N₂↑ 가스 방출 + 카벤 중간체가 특징 — Aldol과 비호환
    #   Sharpless Dihydroxylation과 구분: OsO₄/AD-mix 없으면 Sharpless 아님
    mechanism_type="bamford_stevens",
    title="Bamford-Stevens 반응 (토실히드라존 → 알켄)",
    total_steps=4,
    overall_description=(
        "Bamford-Stevens 반응은 케톤의 토실히드라존을 염기 처리하여 "
        "디아조 중간체를 거쳐 카벤(또는 카베노이드)을 형성하고, "
        "[1,2]-수소 이동으로 알켄을 생성합니다. "
        "Shapiro 변형: 2당량 n-BuLi → 비닐 음이온 → 알켄."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="토실히드라존 형성: 케톤 + TsNHNH₂",
            description=(
                "케톤 카르보닐에 TsNHNH₂의 NH₂가 친핵 공격.\n"
                "축합 반응: H₂O 이탈 → C=N-NHTs (토실히드라존).\n"
                "산 촉매(AcOH) 사용 가능."
            ),
            reactant_smiles="CC(=O)C.NNS(=O)(=O)c1ccc(C)cc1",
            product_smiles="CC(=NNS(=O)(=O)c1ccc(C)cc1)C",
            arrows=[
                ArrowData("full", "lone_pair", "NH₂",
                          "atom", "C=O", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=1),
            ],
            labels={"TsNHNH₂": "토실히드라지드"},
            energy_label="축합",
            reagents="TsNHNH₂, AcOH, MeOH, RT",
            notes="결정성 고체, 정제 가능",
        ),
        MechanismStep(
            step_number=2,
            title="염기 처리 → 디아조 화합물",
            description=(
                "강염기(NaOMe)가 N-H 탈양자화.\n"
                "Retro-[1,4]-제거: TsH 이탈 → 디아조 화합물.\n"
                "IR: ~2100 cm⁻¹ 강한 N=N 신축 흡수."
            ),
            reactant_smiles="CC(=NNS(=O)(=O)c1ccc(C)cc1)C",
            product_smiles="CC(=[N+]=[N-])C",
            arrows=[
                ArrowData("full", "lone_pair", "NaOMe",
                          "atom", "N-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=3),
                ArrowData("full", "bond", "N-Ts",
                          "atom", "Ts⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"디아조": "R₂C=N₂"},
            energy_label="TsH 제거",
            reagents="NaOMe, diglyme, Δ",
        ),
        MechanismStep(
            step_number=3,
            title="N₂ 이탈 → 카벤",
            description=(
                "열분해 또는 광분해: N₂ 이탈.\n"
                "자유 카벤: 단일항(쌍 전자) 또는 삼중항(비쌍 전자).\n"
                "양성자성 용매: 양이온 중간체 (카보카티온) 가능."
            ),
            reactant_smiles="CC(=[N+]=[N-])C",
            product_smiles="C[C]C",
            arrows=[
                ArrowData("full", "bond", "C=N",
                          "atom", "N₂ 이탈", "#4CAF50", 0.5,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"카벤": "R₂C:", "N₂": "이탈기"},
            energy_label="N₂ 손실",
            reagents="Δ or hν",
            notes="N₂는 열역학적으로 매우 안정 → 비가역",
        ),
        MechanismStep(
            step_number=4,
            title="[1,2]-H 이동 → 알켄",
            description=(
                "단일항 카벤: 협동적 [1,2]-수소 이동.\n"
                "인접 C-H 결합의 H가 카벤 중심으로 이동.\n"
                "C=C π결합 형성 → 알켄 생성물."
            ),
            reactant_smiles="C[C]C",
            product_smiles="CC=C",
            arrows=[
                ArrowData("full", "bond", "C-H (인접)",
                          "atom", "카벤 C", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"[1,2]-H 이동": "초안면 이동"},
            energy_label="생성물",
            reagents="",
            notes="Shapiro 변형: n-BuLi 2당량 → E-알켄 선택성",
        ),
    ],
    energy_diagram=[
        ("케톤\n+ TsNHNH₂", 0.0),
        ("토실히드라존", -10.0),
        ("디아조\n화합물", 5.0),
        ("카벤", 25.0),
        ("알켄\n+ N₂", -15.0),
    ],
)


# ─── Barton Decarboxylation ───────────────────────────────────────────────
# 대표 반응: R-COOH + Barton reagent → R-H + CO2

MECHANISMS["barton_decarboxylation"] = MechanismData(
    mechanism_type="barton_decarboxylation",
    title="Barton 탈카르복실화 (라디칼 사슬)",
    total_steps=5,
    overall_description=(
        "Barton 탈카르복실화는 카르복실산을 티오히드록삼산 에스터(Barton ester)로 "
        "활성화한 뒤, 광분해로 라디칼 사슬을 개시합니다. "
        "CO₂ 이탈 후 탄소 라디칼이 H-공여체에 의해 환원됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Barton 에스터 형성",
            description=(
                "카르복실산을 DCC 또는 옥살릴 클로라이드로 활성화.\n"
                "N-하이드록시-2-티오피리돈(Barton 시약)과 커플링.\n"
                "황색 티오히드록삼산 에스터 생성."
            ),
            reactant_smiles="CC(=O)O.ON1C=CC=CS1",
            product_smiles="CC(=O)ON1C=CC=CS1",
            arrows=[
                ArrowData("full", "lone_pair", "O (Barton 시약)",
                          "atom", "C=O (산)", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=1),
            ],
            labels={"Barton 에스터": "티오히드록삼산 에스터"},
            energy_label="에스터 형성",
            reagents="DCC, DMAP, CH₂Cl₂, 0°C→RT",
        ),
        MechanismStep(
            step_number=2,
            title="광분해 (hν) → 라디칼 쌍",
            description=(
                "UV 조사(254–350 nm) → N-O 결합 균일 분해.\n"
                "카르복실옥시 라디칼(R-CO₂•) + 피리딘-2-티올릴 라디칼(Pyr-S•)."
            ),
            reactant_smiles="CC(=O)ON1C=CC=CS1",
            product_smiles="CC(=O)[O].S1C=CC=C[N]1",
            arrows=[
                ArrowData("half", "bond", "N-O",
                          "atom", "N• + O•", "#ff6600", 0.5,
                          from_atom_idx=3, to_atom_idx=2),
            ],
            labels={"hν": "광분해", "N-O": "균일 분해"},
            energy_label="라디칼 개시",
            reagents="hν (254–350 nm) or AIBN",
            notes="라디칼 사슬 개시 단계",
        ),
        MechanismStep(
            step_number=3,
            title="탈카르복실화: CO₂ 이탈 → R•",
            description=(
                "카르복실옥시 라디칼의 β-분열.\n"
                "CO₂ 방출 (열역학적으로 매우 유리).\n"
                "탄소 중심 라디칼 R• 형성."
            ),
            reactant_smiles="CC(=O)[O]",
            product_smiles="[CH3].O=C=O",
            arrows=[
                ArrowData("half", "bond", "C-C (β-분열)",
                          "atom", "R• + CO₂", "#ff6600", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"β-분열": "~10⁹ s⁻¹"},
            energy_label="CO₂ 이탈",
            reagents="",
            notes="속도: ~10⁹ s⁻¹ (매우 빠름)",
        ),
        MechanismStep(
            step_number=4,
            title="라디칼 포획: R• + Bu₃SnH",
            description=(
                "탄소 라디칼 R•가 H-공여체로부터 H 추출.\n"
                "Bu₃SnH → R-H + Bu₃Sn•.\n"
                "Bu₃Sn•이 새 Barton 에스터 공격 → 사슬 전파."
            ),
            reactant_smiles="[CH3].[Sn](CCCC)(CCCC)CCCC",
            product_smiles="C.[Sn](CCCC)(CCCC)CCCC",
            arrows=[
                ArrowData("half", "bond", "Sn-H",
                          "atom", "R• (H 추출)", "#ff6600", 0.3,
                          from_atom_idx=1, to_atom_idx=0),
            ],
            labels={"Bu₃SnH": "H-공여체"},
            energy_label="라디칼 포획",
            reagents="Bu₃SnH, benzene, reflux",
            notes="대안: t-BuSH, (TMS)₃SiH",
        ),
        MechanismStep(
            step_number=5,
            title="생성물: R-H + CO₂",
            description=(
                "환원적 탈카르복실화 생성물.\n"
                "탄소 1개 감소 (COOH → H).\n"
                "응용: 아미노산 분해, 데옥시 당 합성."
            ),
            reactant_smiles="C",
            product_smiles="C",
            arrows=[],
            labels={"R-H": "생성물", "CO₂": "부산물"},
            energy_label="생성물",
            notes="Hunsdiecker 반응의 온화한 대안",
        ),
    ],
    energy_diagram=[
        ("R-COOH\n+ Barton시약", 0.0),
        ("Barton\n에스터", -5.0),
        ("hν → R-CO₂•\n+ Pyr-S•", 20.0),
        ("R• + CO₂", 5.0),
        ("R-H\n(생성물)", -25.0),
    ],
)


# ─── Paternò-Büchi Reaction ──────────────────────────────────────────────
# 대표 반응: C=O + C=C → oxetane (photochemical [2+2])

MECHANISMS["paterno_buchi"] = MechanismData(
    mechanism_type="paterno_buchi",
    title="Patern\u00f2-B\u00fcchi 반응 (광화학 [2+2] → 옥세탄)",
    total_steps=3,
    overall_description=(
        "Paternò-Büchi 반응은 카르보닐(C=O)의 n→π* 여기 후 "
        "알켄(C=C)과의 단계적 [2+2] 고리 첨가를 통해 옥세탄(4원환)을 형성합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="카르보닐 n→π* 여기 (hν)",
            description=(
                "UV 조사: C=O n→π* 전이.\n"
                "S₁ → ISC → T₁ (항간 교차).\n"
                "삼중항 카르보닐: 1,2-이라디칼 성격."
            ),
            reactant_smiles="CC=O",
            product_smiles="CC=O",
            arrows=[
                ArrowData("half", "lone_pair", "n (O 비공유전자쌍)",
                          "antibonding", "π* (C=O)", "#ff6600", 0.5,
                          from_atom_idx=2, to_atom_idx=1),
            ],
            labels={"hν": "280–330 nm", "ISC": "항간 교차"},
            energy_label="T₁ 여기",
            reagents="hν (UV), acetone sensitizer",
        ),
        MechanismStep(
            step_number=2,
            title="단계적 [2+2]: 삼중항 이라디칼 중간체",
            description=(
                "삼중항 C=O 라디칼이 C=C 공격.\n"
                "첫 C-C 결합 형성 → 1,4-이라디칼.\n"
                "위치선택성: Paternò 규칙 (안정한 이라디칼 선호)."
            ),
            reactant_smiles="CC=O.C=C",
            product_smiles="CC([O])C[CH2]",
            arrows=[
                ArrowData("half", "atom", "C• (카르보닐)",
                          "atom", "C=C (알켄)", "#ff6600", 0.5,
                          from_atom_idx=1, to_atom_idx=3),
            ],
            labels={"이라디칼": "1,4-biradical"},
            is_transition_state=False,
            energy_label="이라디칼",
            reagents="",
            notes="열적 [2+2]는 Woodward-Hoffmann 금지",
        ),
        MechanismStep(
            step_number=3,
            title="고리 닫힘 → 옥세탄",
            description=(
                "ISC: 삼중항 → 단일항 이라디칼.\n"
                "스핀 반전 후 O-C 결합 형성.\n"
                "옥세탄 4원환 생성물."
            ),
            reactant_smiles="CC([O])C[CH2]",
            product_smiles="CC1OCC1",
            arrows=[
                ArrowData("full", "atom", "O•",
                          "atom", "C•", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),
            ],
            labels={"옥세탄": "4원환 에테르"},
            energy_label="생성물",
            notes="의약화학에서 생체등배체로 활용",
        ),
    ],
    energy_diagram=[
        ("C=O + C=C\n(기저 상태)", 0.0),
        ("T₁ C=O*", 30.0),
        ("1,4-이라디칼", 15.0),
        ("옥세탄\n(생성물)", -10.0),
    ],
)


# ─── Norrish Type II Reaction ─────────────────────────────────────────────
# 대표 반응: ketone + hν → enol + alkene (γ-H abstraction + retro-[2+2])

MECHANISMS["norrish_type_ii"] = MechanismData(
    mechanism_type="norrish_type_ii",
    title="Norrish Type II 반응 (γ-H 추출 + 역 [2+2])",
    total_steps=4,
    overall_description=(
        "Norrish Type II 반응: 케톤의 광여기 후 6원환 전이상태를 통한 "
        "γ-수소 추출 → 1,4-이라디칼 → 역-[2+2] 분열 → 에놀 + 알켄."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="hν 여기: C=O n→π* → 삼중항",
            description=(
                "UV 조사: 카르보닐 n→π* 전이.\n"
                "ISC → 삼중항 케톤 (T₁).\n"
                "γ-H 필요: C=O에서 4번째 탄소에 H."
            ),
            reactant_smiles="CCCCC(=O)C",
            product_smiles="CCCCC(=O)C",
            arrows=[
                ArrowData("half", "lone_pair", "n (O)",
                          "antibonding", "π* (C=O)", "#ff6600", 0.5,
                          from_atom_idx=5, to_atom_idx=4),
            ],
            labels={"hν": "UV", "T₁": "삼중항"},
            energy_label="T₁ 여기",
            reagents="hν (280–320 nm)",
        ),
        MechanismStep(
            step_number=2,
            title="γ-H 추출: 6원환 TS (Zimmerman)",
            description=(
                "삼중항 O•가 γ-H를 추출.\n"
                "의자형 6원환 전이상태 (Zimmerman TS).\n"
                "1,4-이라디칼 형성: O에 OH, Cγ에 라디칼."
            ),
            reactant_smiles="CCCCC(=O)C",
            product_smiles="CCCC(O)C([CH2])C",
            arrows=[
                ArrowData("half", "atom", "O• (삼중항)",
                          "atom", "γ-H", "#ff6600", 0.4,
                          from_atom_idx=5, to_atom_idx=0),
            ],
            labels={"6원환 TS": "Zimmerman", "γ-H": "추출"},
            is_transition_state=True,
            energy_label="γ-H 추출 TS",
        ),
        MechanismStep(
            step_number=3,
            title="역-[2+2] 분열: Cα-Cβ 결합 절단",
            description=(
                "1,4-이라디칼 → 역-[2+2] 분열.\n"
                "Cα-Cβ 결합 균일 분해.\n"
                "동시에 Cγ=Cδ 이중결합 형성."
            ),
            reactant_smiles="CCCC(O)C([CH2])C",
            product_smiles="C=C.CC(=O)C",
            arrows=[
                ArrowData("half", "bond", "Cα-Cβ",
                          "atom", "Cγ=Cδ (알켄)", "#ff6600", 0.5,
                          from_atom_idx=3, to_atom_idx=2),
            ],
            labels={"역-[2+2]": "분열"},
            energy_label="분열",
            notes="Yang 고리화(시클로부탄올)와 경쟁",
        ),
        MechanismStep(
            step_number=4,
            title="생성물: 에놀(→ 케톤) + 알켄",
            description=(
                "에놀이 호변이성화 → 메틸 케톤.\n"
                "알켄 + 케톤 두 조각.\n"
                "광화학적 β-제거 등가 반응."
            ),
            reactant_smiles="C=C.CC(=O)C",
            product_smiles="C=C.CC(=O)C",
            arrows=[],
            labels={"에놀": "호변이성화", "알켄": "생성물"},
            energy_label="생성물",
            notes="고분자 광분해, 광보호기에 응용",
        ),
    ],
    energy_diagram=[
        ("케톤\n(기저 상태)", 0.0),
        ("T₁ 케톤*", 30.0),
        ("γ-H 추출\nTS", 25.0),
        ("1,4-이라디칼", 10.0),
        ("에놀 + 알켄", -5.0),
    ],
)


# ─── Norrish Type I Reaction ─────────────────────────────────────────────
# 대표 반응: ketone + hν → acyl radical + alkyl radical → products

MECHANISMS["norrish_type_i"] = MechanismData(
    mechanism_type="norrish_type_i",
    title="Norrish Type I 반응 (α-절단)",
    total_steps=4,
    overall_description=(
        "Norrish Type I: 케톤의 광여기 후 C=O에 인접한 α-C-C 결합의 "
        "균일 분해. 아실 라디칼 + 알킬 라디칼 생성 → 탈카르보닐화 또는 재결합."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="hν 여기: C=O n→π*",
            description=(
                "UV 조사: 카르보닐 n→π* 전이.\n"
                "ISC → 삼중항. α-C-C 결합 약화.\n"
                "BDE 약 350 kJ/mol 감소."
            ),
            reactant_smiles="CCC(=O)CC",
            product_smiles="CCC(=O)CC",
            arrows=[
                ArrowData("half", "lone_pair", "n (O)",
                          "antibonding", "π* (C=O)", "#ff6600", 0.5,
                          from_atom_idx=3, to_atom_idx=2),
            ],
            labels={"hν": "UV"},
            energy_label="T₁ 여기",
            reagents="hν (280–320 nm)",
        ),
        MechanismStep(
            step_number=2,
            title="α-C-C 결합 균일 분해",
            description=(
                "C=O 인접 α-C-C 결합 균일 분해.\n"
                "아실 라디칼(R-CO•) + 알킬 라디칼(R'•).\n"
                "더 치환된(안정한) 라디칼 쪽이 우선 절단."
            ),
            reactant_smiles="CCC(=O)CC",
            product_smiles="CC[C](=O).[CH2]C",
            arrows=[
                ArrowData("half", "bond", "α-C-C",
                          "atom", "R-CO• + R'•", "#ff6600", 0.5,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"α-절단": "균일 분해"},
            energy_label="α-절단",
        ),
        MechanismStep(
            step_number=3,
            title="탈카르보닐화 (CO 이탈) 또는 재결합",
            description=(
                "아실 라디칼 → R• + CO (탈카르보닐화).\n"
                "또는 라디칼 재결합 (용매 우리 효과).\n"
                "불균등화: β-H 전달 → 알칸 + 알켄."
            ),
            reactant_smiles="CC[C](=O).[CH2]C",
            product_smiles="[CH2]C.CC.[C-]#[O+]",
            arrows=[
                ArrowData("half", "bond", "C-CO",
                          "atom", "R• + CO", "#ff6600", 0.4,
                          from_atom_idx=0, to_atom_idx=2),
            ],
            labels={"탈카르보닐화": "CO 이탈"},
            energy_label="CO 이탈",
            notes="1° 아실 라디칼에서 유리",
        ),
        MechanismStep(
            step_number=4,
            title="최종 생성물",
            description=(
                "라디칼 운명: 재결합(R-R'), 불균등화(알칸+알켄), "
                "또는 용매 H-추출(R-H).\n"
                "아세톤 광분해: 2 CH₃• + CO."
            ),
            reactant_smiles="CC.CC",
            product_smiles="CC.CC",
            arrows=[],
            labels={"라디칼 운명": "재결합/불균등화"},
            energy_label="생성물",
            notes="광중합 개시제, 대기화학에 응용",
        ),
    ],
    energy_diagram=[
        ("케톤\n(기저 상태)", 0.0),
        ("T₁ 케톤*", 35.0),
        ("α-절단\n(R-CO• + R'•)", 20.0),
        ("탈카르보닐화\n(R• + CO)", 10.0),
        ("생성물", -5.0),
    ],
)


# ─── Lindlar Hydrogenation (Cycle 10) ─────────────────────────────────────────
# 대표 반응: 2-Butyne + H2/Pd-CaCO3(poisoned) → cis-2-Butene (Z)

MECHANISMS["lindlar_hydrogenation"] = MechanismData(
    mechanism_type="lindlar_hydrogenation",
    title="Lindlar 촉매 수소화 (알카인 → cis-알켄)",
    total_steps=2,
    overall_description=(
        "Lindlar 촉매(Pd/CaCO3, quinoline 독으로 비활성화)를 이용한 "
        "알카인의 부분 수소화. syn-첨가로 Z(cis)-알켄만 생성. "
        "촉매 독이 과환원(알칸 형성)을 방지."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="H₂의 Pd 표면 해리 흡착 + syn 전달 (표면 매개 TS)",
            description=(
                "H₂가 Pd(0) 표면에 해리 흡착.\n"
                "독(quinoline/Pb(OAc)₂)이 활성 자리 비활성화 → 알켄 단계에서 정지.\n"
                "알카인 π결합이 Pd에 배위 → 같은 면에서 H₂개 전달 (syn).\n"
                "4-중심 전이상태: [H-Pd-H···C≡C]."
            ),
            reactant_smiles="CC#CC",
            product_smiles="C/C=C\\C",
            arrows=[
                ArrowData("full", "bond", "H-H",
                          "atom", "Pd 표면", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "C≡C π",
                          "atom", "Pd 배위", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "atom", "H(Pd)",
                          "atom", "C(alkyne)", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),
            ],
            labels={"syn 전달": "같은 면"},
            energy_label="표면 매개 TS",
            reagents="H₂, Pd/CaCO₃, quinoline",
            notes="4-중심 전이상태, Z-선택적",
        ),
        MechanismStep(
            step_number=2,
            title="생성물: cis-알켄 (Z-이성질체)",
            description=(
                "부분 수소화 완료. Z(cis)-알켄 형성.\n"
                "독된 촉매는 알켄을 더 환원할 수 없음.\n"
                "비독 Pd/C는 알칸까지 완전 환원됨.\n"
                "E-알켄 필요 시: Na/NH₃(l) (용해 금속 환원)."
            ),
            reactant_smiles="C/C=C\\C",
            product_smiles="C/C=C\\C",
            arrows=[],
            labels={"Z-알켄": "syn 첨가"},
            energy_label="생성물",
            notes="천연물 합성, cis-지방산에 활용",
        ),
    ],
    energy_diagram=[
        ("알카인\n+ H₂/Pd", 0.0),
        ("표면 흡착 TS", 15.0),
        ("cis-알켄\n(Z)", -25.0),
    ],
)


# ─── Clemmensen Reduction (Cycle 10) ─────────────────────────────────────────
# 대표 반응: Acetophenone + Zn(Hg)/HCl → Ethylbenzene

MECHANISMS["clemmensen_reduction"] = MechanismData(
    mechanism_type="clemmensen_reduction",
    title="Clemmensen 환원 (C=O → CH₂)",
    total_steps=3,
    overall_description=(
        "Clemmensen 환원은 Zn(Hg) 아말감과 농염산으로 "
        "케톤/알데히드의 카르보닐을 완전히 제거(탈산소화)하여 "
        "CH₂로 변환. 산성 조건. Wolff-Kishner(염기)와 상보적."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="C=O의 Zn(Hg) 표면 배위",
            description=(
                "카르보닐 O가 아연 금속 표면에 배위.\n"
                "Hg은 HCl에 의한 Zn 부동태화 방지.\n"
                "SET 메커니즘: Zn(0) → Zn(II), 2전자 제공."
            ),
            reactant_smiles="CC(=O)c1ccccc1",
            product_smiles="CC([Zn])c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "C=O",
                          "atom", "Zn 표면", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),
                ArrowData("full", "atom", "Zn(0)",
                          "atom", "C=O 탄소", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "bond", "C=O",
                          "atom", "O", "#FF9800", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"SET": "단일전자이동"},
            energy_label="표면 배위",
            reagents="Zn(Hg), conc. HCl, reflux",
            notes="메커니즘 논쟁: SET vs 카르벤/카르베노이드",
        ),
        MechanismStep(
            step_number=2,
            title="단계적 환원: 아연 카르베노이드 → CH₂",
            description=(
                "C=O → C-OH → C-Cl → C-Zn → CH₂ (단계적).\n"
                "HCl이 중간체를 양성자화, Zn이 전자 공급.\n"
                "완전한 산소 제거(탈산소화).\n"
                "Wolff-Kishner와 비교: 동일 생성물, 염기 조건."
            ),
            reactant_smiles="CC([Zn])c1ccccc1",
            product_smiles="CCc1ccccc1",
            arrows=[
                ArrowData("full", "bond", "Zn-C",
                          "atom", "H(HCl)", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "atom", "H(HCl)",
                          "bond", "C-Zn", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "lone_pair", "O",
                          "atom", "Zn", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),
            ],
            labels={"카르베노이드": "C-Zn"},
            energy_label="중간체",
            notes="산 민감 기질은 Wolff-Kishner 사용",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알칸 (C=O → CH₂)",
            description=(
                "완전 탈산소화: C=O → CH₂.\n"
                "부산물: ZnCl₂, H₂O.\n"
                "범위: 아릴 케톤에 최적 (FC 아실화/Clemmensen 연속).\n"
                "현대 대안: Et₃SiH/TFA (이온성 수소화)."
            ),
            reactant_smiles="CCc1ccccc1",
            product_smiles="CCc1ccccc1",
            arrows=[],
            labels={"탈산소화": "완전"},
            energy_label="생성물",
            notes="에폭사이드, 아세탈과 비호환",
        ),
    ],
    energy_diagram=[
        ("케톤\n+ Zn(Hg)/HCl", 0.0),
        ("Zn 표면 배위", 10.0),
        ("카르베노이드\n중간체", 5.0),
        ("알칸\n(CH₂)", -30.0),
    ],
)


# ─── Sandmeyer Reaction (Cycle 10) ───────────────────────────────────────────
# 대표 반응: Aniline → Benzenediazonium → Chlorobenzene (via CuCl)

MECHANISMS["sandmeyer_reaction"] = MechanismData(
    mechanism_type="sandmeyer_reaction",
    title="Sandmeyer 반응 (ArNH₂ → ArX via 디아조늄)",
    total_steps=4,
    overall_description=(
        "Sandmeyer 반응: (1) ArNH₂의 디아조화(NaNO₂/HCl) → ArN₂⁺, "
        "(2) Cu(I) 염(CuCl, CuBr, CuCN)에 의한 SET 메커니즘으로 "
        "N₂ 방출 + ArX 형성. 직접 할로겐화로 얻을 수 없는 위치의 Ar-X 합성."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="디아조화: ArNH₂ + NaNO₂/HCl → ArN₂⁺",
            description=(
                "0-5°C에서 NaNO₂ + HCl → HNO₂.\n"
                "NO⁺ 친전자체가 ArNH₂의 N 고립쌍 공격.\n"
                "N-니트로사민 → 디아조히드록시드 → ArN₂⁺.\n"
                "온도 유지 필수: 고온 시 N₂ 조기 방출."
            ),
            reactant_smiles="Nc1ccccc1",
            product_smiles="[N+](#N)c1ccccc1.[Cl-]",
            arrows=[
                ArrowData("full", "lone_pair", "NH₂",
                          "atom", "NO⁺", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N-O",
                          "atom", "H₂O 이탈", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "N-H",
                          "atom", "탈양자화", "#FF9800", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"NO⁺": "니트로소늄"},
            energy_label="디아조화",
            reagents="NaNO₂, HCl, 0-5°C",
            notes="디아조늄 염: 건조 시 폭발성",
        ),
        MechanismStep(
            step_number=2,
            title="CuCl의 SET: Cu(I) → ArN₂• 라디칼",
            description=(
                "Cu(I) → Cu(II) + e⁻.\n"
                "디아조늄에 전자 전달 → ArN₂• 라디칼.\n"
                "N₂ 이탈 후 Ar• 아릴 라디칼 형성.\n"
                "Kochi 메커니즘: Cu 매개 라디칼 체인."
            ),
            reactant_smiles="[N+](#N)c1ccccc1.[Cl-]",
            product_smiles="[N+](#N)c1ccccc1.[Cl-]",
            arrows=[
                ArrowData("half", "atom", "Cu(I)",
                          "atom", "N₂⁺", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("half", "bond", "C-N",
                          "atom", "N₂ 이탈", "#E53935", 0.3,
                          from_atom_idx=2, to_atom_idx=0),
                ArrowData("full", "atom", "Cu",
                          "atom", "Cl", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"SET": "단일전자이동"},
            energy_label="라디칼 중간체",
            notes="Kochi 메커니즘",
        ),
        MechanismStep(
            step_number=3,
            title="N₂ 방출 → Ar• + X 결합",
            description=(
                "N₂(g) 방출 (ΔG° 매우 음수, 비가역).\n"
                "Ar• 라디칼이 Cu(II)X₂에서 X 추출.\n"
                "ipso 치환만 발생 (원래 NH₂ 위치)."
            ),
            reactant_smiles="[N+](#N)c1ccccc1.[Cl-]",
            product_smiles="Clc1ccccc1",
            arrows=[
                ArrowData("half", "bond", "C-N",
                          "atom", "Ar•", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=0),
                ArrowData("full", "atom", "Cl(Cu)",
                          "atom", "Ar", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
                ArrowData("full", "bond", "N≡N",
                          "atom", "N₂(g)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"N₂": "이탈 기체"},
            energy_label="N₂ 방출",
            reagents="CuCl",
            notes="부반응: Ar-OH, Ar-H, Ar-Ar",
        ),
        MechanismStep(
            step_number=4,
            title="생성물: Ar-Cl (아릴 할라이드)",
            description=(
                "아릴 할라이드 생성.\n"
                "Sandmeyer 범위: ArCl, ArBr, ArCN.\n"
                "관련: Balz-Schiemann (ArF), Gattermann (Cu 분말).\n"
                "meta-치환 아릴 할라이드에 유용."
            ),
            reactant_smiles="Clc1ccccc1",
            product_smiles="Clc1ccccc1",
            arrows=[],
            labels={"ArCl": "생성물"},
            energy_label="생성물",
            notes="직접 할로겐화 불가능한 위치에 활용",
        ),
    ],
    energy_diagram=[
        ("ArNH₂\n+ NaNO₂/HCl", 0.0),
        ("ArN₂⁺\n(디아조늄)", 5.0),
        ("Ar•\n(라디칼) + N₂", 15.0),
        ("Ar-Cl\n(생성물)", -20.0),
    ],
)


# ─── SNAr — Nucleophilic Aromatic Substitution (Cycle 10) ─────────────────────
# 대표 반응: 2,4-Dinitrochlorobenzene + NaOMe → 2,4-Dinitroanisole

MECHANISMS["snar"] = MechanismData(
    mechanism_type="snar",
    title="SNAr 친핵 방향족 치환 (Meisenheimer 착물)",
    total_steps=3,
    overall_description=(
        "SNAr: 친핵체가 이탈기 달린 ipso 탄소를 공격 → "
        "Meisenheimer 착물(σ-complex, 음이온 시클로헥사디에닐) 형성 → "
        "이탈기 이탈 + 재방향족화. EWG(NO₂, CN) 필수."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵체의 ipso-탄소 공격 → Meisenheimer 착물",
            description=(
                "Nu⁻(OH⁻, OR⁻, NH₂R)가 이탈기(F, Cl) 달린 C 공격.\n"
                "EWG(NO₂, CN)가 ortho/para에서 음전하 안정화.\n"
                "속도결정단계: 첨가(제거가 아님).\n"
                "σ-complex: sp³ 탄소, Nu+LG 모두 결합."
            ),
            reactant_smiles="O=[N+]([O-])c1ccc(Cl)c([N+](=O)[O-])c1",
            product_smiles="O=[N+]([O-])c1ccc([O-])c([N+](=O)[O-])c1",
            arrows=[
                ArrowData("full", "lone_pair", "Nu⁻",
                          "atom", "ipso-C", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=4),
                ArrowData("full", "pi_bond", "C=C",
                          "atom", "NO₂", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=1),
                ArrowData("full", "pi_bond", "방향족 π",
                          "atom", "σ-complex", "#FF9800", 0.3,
                          from_atom_idx=5, to_atom_idx=6),
            ],
            labels={"Meisenheimer": "σ-착물"},
            energy_label="속도결정단계",
            reagents="NaOMe, DMF",
            notes="F가 SNAr에서 최고 이탈기 (SN2와 반대!)",
        ),
        MechanismStep(
            step_number=2,
            title="이탈기 이탈 → 재방향족화",
            description=(
                "Meisenheimer 착물 붕괴: LG가 전자쌍과 함께 이탈.\n"
                "sp³ → sp² 재혼성화 (방향족 안정화 ~150 kJ/mol 회복).\n"
                "SNAr LG 순서: F > NO₂ > Cl > Br > I.\n"
                "F: 첨가 단계가 RDS이므로 유도 효과로 σ-complex 안정화."
            ),
            reactant_smiles="O=[N+]([O-])c1ccc([O-])c([N+](=O)[O-])c1",
            product_smiles="O=[N+]([O-])c1ccc(OC)c([N+](=O)[O-])c1",
            arrows=[
                ArrowData("full", "bond", "C-F",
                          "atom", "F⁻ 이탈", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "C-C",
                          "bond", "재방향족화", "#43A047", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("full", "bond", "π 복원",
                          "bond", "방향족 π", "#1565C0", 0.3,
                          from_atom_idx=5, to_atom_idx=6),
            ],
            labels={"재방향족화": "구동력"},
            energy_label="중간체 → 생성물",
            notes="방향족성 회복이 구동력",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 치환 아렌",
            description=(
                "Nu가 LG를 대체. ipso 치환만 발생.\n"
                "예: 2,4-디니트로클로로벤젠 + 아민 (Sanger 시약).\n"
                "벤자인 메커니즘: 다른 경로 (EWG 불필요, 강염기)."
            ),
            reactant_smiles="O=[N+]([O-])c1ccc(OC)c([N+](=O)[O-])c1",
            product_smiles="O=[N+]([O-])c1ccc(OC)c([N+](=O)[O-])c1",
            arrows=[],
            labels={"ipso 치환": "완료"},
            energy_label="생성물",
            notes="의약품 합성에서 SNAr 절단 다수",
        ),
    ],
    energy_diagram=[
        ("ArF + Nu⁻", 0.0),
        ("Meisenheimer\n착물 (σ)", 20.0),
        ("생성물\n+ F⁻", -15.0),
    ],
)


# ─── SOCl2 Conversion (Cycle 10) ─────────────────────────────────────────────
# 대표 반응: 1-Butanol + SOCl2 → 1-Chlorobutane + SO2 + HCl

MECHANISMS["socl2_conversion"] = MechanismData(
    mechanism_type="socl2_conversion",
    title="SOCl₂에 의한 알코올 → 알킬 클로라이드 변환",
    total_steps=3,
    overall_description=(
        "알코올을 SOCl₂(티오닐 클로라이드)로 처리하면 "
        "클로로설파이트 에스터 중간체를 거쳐 알킬 클로라이드 생성. "
        "조건에 따라 SNi(보유) 또는 SN2(반전) 메커니즘."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="SOCl₂의 알코올 공격 → 클로로설파이트 에스터",
            description=(
                "알코올 O 고립쌍이 SOCl₂의 S(친전자성) 공격.\n"
                "Cl⁻가 S에서 이탈: 첨가-제거.\n"
                "R-O-S(=O)-Cl (클로로설파이트 에스터) 형성.\n"
                "HCl 기체 방출 (1당량)."
            ),
            reactant_smiles="CCCCO",
            product_smiles="CCCCOS(=O)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "O(OH)",
                          "atom", "S(SOCl₂)", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=-1),
                ArrowData("full", "bond", "S-Cl",
                          "atom", "Cl⁻ 이탈", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "O-H",
                          "atom", "HCl 방출", "#FF9800", 0.3,
                          from_atom_idx=4, to_atom_idx=-1),
            ],
            labels={"클로로설파이트": "R-OSO-Cl"},
            energy_label="에스터 형성",
            reagents="SOCl₂, RT or reflux",
            notes="저온에서 중간체 분리 가능",
        ),
        MechanismStep(
            step_number=2,
            title="SNi/SN2: Cl⁻가 -OSO-Cl 치환",
            description=(
                "NEAT: SNi(내부 복귀) → 입체 보유.\n"
                "Cl이 같은 면에서 공격 (밀착 이온쌍).\n"
                "SO₂ 기체 방출.\n"
                "피리딘 존재: SN2 → Walden 반전.\n"
                "조건에 따라 입체화학이 완전히 달라짐!"
            ),
            reactant_smiles="CCCCOS(=O)Cl",
            product_smiles="CCCCCl",
            arrows=[
                ArrowData("full", "atom", "Cl⁻",
                          "atom", "C", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=3),
                ArrowData("full", "bond", "C-O",
                          "atom", "SO₂ 이탈", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("full", "bond", "S=O",
                          "atom", "SO₂ 형성", "#FF9800", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"SNi/SN2": "조건 의존"},
            energy_label="치환",
            notes="피리딘 유무가 메커니즘 결정",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알킬 클로라이드 + SO₂ + HCl",
            description=(
                "알킬 클로라이드 생성.\n"
                "부산물: SO₂(g) + HCl(g) — 기체 → 르 샤틀리에.\n"
                "PBr₃/PCl₅ 대비 장점: 깨끗한 반응.\n"
                "1차 > 2차 >> 3차 (제거 경쟁)."
            ),
            reactant_smiles="CCCCCl",
            product_smiles="CCCCCl",
            arrows=[],
            labels={"알킬 클로라이드": "생성물"},
            energy_label="생성물",
            notes="옥살릴 클로라이드: 산 민감 기질용 대안",
        ),
    ],
    energy_diagram=[
        ("R-OH\n+ SOCl₂", 0.0),
        ("클로로설파이트\n에스터", 10.0),
        ("SNi/SN2 TS", 20.0),
        ("R-Cl\n+ SO₂ + HCl", -25.0),
    ],
)


# ─── Beckmann Fragmentation (Cycle 11) ────────────────────────────────────────
# 대표 반응: Cyclohexanone oxime + H2SO4 → ω-cyanopentyl cation (ring opening)

MECHANISMS["beckmann_fragmentation"] = MechanismData(
    mechanism_type="beckmann_fragmentation",
    title="Beckmann 분절 (고리 옥심 → 니트릴 + 양이온)",
    total_steps=3,
    overall_description=(
        "고리형 옥심의 Beckmann 분절. 일반 Beckmann 전위(락탐)와 달리, "
        "고리 기질에서 C-C 결합이 절단되어 니트릴과 카보양이온을 생성. "
        "anti-periplanar 배향의 C-C/N-O 필수."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="옥심 활성화 (H₂SO₄ / PCl₅)",
            description=(
                "옥심 -OH가 양성자화 또는 활성화.\n"
                "이탈기 능력 향상 (-OH₂⁺ 또는 -OPCl₄).\n"
                "고리형 기질: C-C가 N-O에 anti-periplanar → 분절 선호.\n"
                "입체전자 요건이 전위/분절 경로를 결정."
            ),
            reactant_smiles="ON=C1CCCCC1",
            product_smiles="[OH2+]N=C1CCCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "O(옥심)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "lone_pair", "O lp",
                          "atom", "H", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N=C",
                          "atom", "N", "#43A047", 0.4,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"활성화": "이탈기 생성"},
            energy_label="활성화",
            reagents="H₂SO₄ 또는 PCl₅",
            notes="anti-periplanar 배향 필수",
        ),
        MechanismStep(
            step_number=2,
            title="C-C 결합 절단 → 니트릴 + 카보양이온",
            description=(
                "N-O 결합 절단과 동시에 anti-periplanar C-C 절단.\n"
                "한쪽 조각: 니트릴 (C≡N, 전 C=N에서 유래).\n"
                "다른 조각: 카보양이온 (인접기 안정화).\n"
                "고리 변형 에너지 해소가 분절 구동력."
            ),
            reactant_smiles="[OH2+]N=C1CCCCC1",
            product_smiles="N#CCCCC[CH2+]",
            arrows=[
                ArrowData("full", "bond", "C-C(ring)",
                          "atom", "C(carbocation)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "bond", "N-O",
                          "atom", "O(이탈)", "#FF6F00", 0.4,
                          from_atom_idx=1, to_atom_idx=0),
                ArrowData("full", "bond", "C=N → C≡N",
                          "atom", "N", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=1),
            ],
            labels={"C-C 절단": "분절"},
            is_transition_state=True,
            energy_label="TS (분절)",
            notes="니트릴 안정성이 구동력",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: ω-시아노알킬 유도체",
            description=(
                "카보양이온이 친핵체에 포획 (H₂O, ROH 등).\n"
                "순수 결과: 고리 옥심 → 선형 니트릴 함유 생성물.\n"
                "응용: 고리 케톤의 이기능성 사슬 합성.\n"
                "유리: 변형 고리, 4차 α-탄소, 가교 비고리."
            ),
            reactant_smiles="N#CCCCCO",
            product_smiles="N#CCCCCO",
            arrows=[],
            labels={"니트릴": "생성물"},
            energy_label="생성물",
            notes="고리 개환 → 이기능성 사슬",
        ),
    ],
    energy_diagram=[
        ("고리 옥심", 0.0),
        ("활성화 옥심", 8.0),
        ("분절 TS", 22.0),
        ("ω-시아노알킬\n유도체", -15.0),
    ],
)


# ─── Mannich Reaction (Cycle 11) ──────────────────────────────────────────────
# 대표 반응: CH2O + (CH3)2NH + CH3COCH3 → (CH3)2NCH2COCH3 (Mannich base)

MECHANISMS["mannich_reaction"] = MechanismData(
    mechanism_type="mannich_reaction",
    title="Mannich 반응 (3성분 → β-아미노 케톤)",
    total_steps=4,
    overall_description=(
        "알데히드 + 아민 + 에놀화 가능 케톤 → β-아미노 케톤(Mannich 염기). "
        "3성분 축합 반응. 이미늄 이온 형성 후 에놀이 공격."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이미늄 이온 형성 (알데히드 + 아민)",
            description=(
                "아민이 알데히드 카보닐을 친핵 공격.\n"
                "카비놀아민 → 탈수 → 이미늄 이온 (C=N⁺).\n"
                "최적 pH 4-5: 유리 아민 + 탈수 산 촉매.\n"
                "속도 결정 단계."
            ),
            reactant_smiles="C=O",
            product_smiles="C=[NH2+]",
            arrows=[
                ArrowData("full", "lone_pair", "N lp",
                          "atom", "C(=O)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O π",
                          "atom", "O", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "lone_pair", "O lp",
                          "atom", "H", "#43A047", 0.3,
                          from_atom_idx=1, to_atom_idx=-1),
            ],
            labels={"이미늄": "전기양성"},
            energy_label="이미늄 형성",
            reagents="CH₂O + R₂NH",
            notes="pH 4-5 최적",
        ),
        MechanismStep(
            step_number=2,
            title="케톤의 에놀화",
            description=(
                "에놀화 가능 케톤이 에놀 형태로 호변이성질체화.\n"
                "산 촉매: C=O 양성자화 → α-C-H 산성 증가.\n"
                "에놀/에놀레이트 = C-친핵체.\n"
                "pKa < 20인 CH-산성 케톤만 참여."
            ),
            reactant_smiles="CC(=O)C",
            product_smiles="CC(O)=C",
            arrows=[
                ArrowData("full", "bond", "C-H(α)",
                          "atom", "B(base)", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C=O",
                          "atom", "O-H", "#1565C0", 0.4,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "lone_pair", "C=C(에놀)",
                          "atom", "C(α)", "#43A047", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"에놀": "친핵체"},
            energy_label="에놀화",
            notes="산/염기 촉매",
        ),
        MechanismStep(
            step_number=3,
            title="C-C 결합 형성: 에놀이 이미늄 공격",
            description=(
                "에놀 탄소가 이미늄 탄소를 공격.\n"
                "핵심 C-C 결합 형성 단계.\n"
                "위치선택성: 치환 적은 α-탄소에서 공격.\n"
                "비대칭 Mannich: 프롤린 촉매 (List, 2000)."
            ),
            reactant_smiles="CC(O)=C",
            product_smiles="O=C(C)CCNC",
            arrows=[
                # CC(O)=C: C0-C1(OH)-=C2-... wait: RDKit "CC(O)=C" idx 0=C,1=C,2=O,3=C(=)
                # Textbook (Solomons §19.7 Mannich): enol C=C pi → iminium C; C=N+ → N; enol O-H → C=O
                ArrowData("full", "pi_bond", "C=C(에놀) → 이미늄 친핵 공격",
                          "atom", "C(이미늄, 외부)", "#E53935", 0.5,
                          from_atom_idx=3, to_atom_idx=-1),  # 에놀 말단 C(idx3) → 이미늄C(외부)
                ArrowData("full", "pi_bond", "C=N⁺ → N (이미늄 전자쌍 이동)",
                          "atom", "N (이미늄, 외부)", "#2980B9", 0.3,
                          from_atom_idx=-1, to_atom_idx=-2),  # Rule P exclusion: 이미늄 양쪽 외부 = 별도 fragment
                ArrowData("full", "bond", "O-H(에놀) → C=O 회복",
                          "atom", "C=O (케톤 회복)", "#8E44AD", 0.3,
                          from_atom_idx=2, to_atom_idx=1),  # O(idx2) 론페어 → C1으로 이동 → C=O 재형성
            ],
            labels={"C-C 형성": "핵심"},
            is_transition_state=True,
            energy_label="TS (C-C 형성)",
            notes="라세미 생성물 (비대칭 촉매 없을 시)",
        ),
        MechanismStep(
            step_number=4,
            title="생성물: β-아미노 케톤 (Mannich 염기)",
            description=(
                "β-아미노 케톤 생성물.\n"
                "응용: 트로피논 합성 (Robinson), 그라민, 약물.\n"
                "Mannich 제거 → α,β-불포화 케톤 가능.\n"
                "관련: Kabachnik-Fields, Petasis."
            ),
            reactant_smiles="O=C(C)CCNC",
            product_smiles="O=C(C)CCNC",
            arrows=[],
            labels={"Mannich 염기": "생성물"},
            energy_label="생성물",
            notes="3성분 축합",
        ),
    ],
    energy_diagram=[
        ("RCHO + R₂NH\n+ R'COCH₃", 0.0),
        ("이미늄 이온", 5.0),
        ("에놀", 8.0),
        ("C-C TS", 18.0),
        ("β-아미노 케톤", -10.0),
    ],
)


# ─── Strecker Synthesis (Cycle 11) ────────────────────────────────────────────
# 대표 반응: RCHO + NH3 + HCN → RCH(NH2)COOH (via aminonitrile)

MECHANISMS["strecker_synthesis"] = MechanismData(
    mechanism_type="strecker_synthesis",
    title="Strecker 합성 (알데히드 → α-아미노산)",
    total_steps=4,
    overall_description=(
        "알데히드 + NH₃ + HCN → α-아미노산 (아미노니트릴 경유). "
        "가장 간단한 α-아미노산 합성법 (1850). "
        "이민 형성 → 시안화물 첨가 → 니트릴 가수분해."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이민 (Schiff 염기) 형성: 알데히드 + NH₃",
            description=(
                "암모니아가 알데히드 카보닐을 공격.\n"
                "카비놀아민 → 탈수 → 이민 (R-CH=NH).\n"
                "가역적 축합 반응.\n"
                "이민 C=N: C에서 전기양성 (2단계 활성화)."
            ),
            reactant_smiles="CC=O",
            product_smiles="CC=N",
            arrows=[
                ArrowData("full", "lone_pair", "NH₃ lp",
                          "atom", "C(=O)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=O π",
                          "atom", "O", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "lone_pair", "O-H",
                          "atom", "탈수", "#43A047", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),
            ],
            labels={"이민": "전기양성"},
            energy_label="이민 형성",
            reagents="NH₃",
            notes="Strecker (1850) — 최초 아미노산 합성",
        ),
        MechanismStep(
            step_number=2,
            title="시안화물 첨가 → α-아미노니트릴",
            description=(
                "HCN/KCN이 CN⁻ 친핵체 제공.\n"
                "CN⁻가 이민 C(=NH) 공격.\n"
                "결과: α-아미노니트릴 (H₂N-CHR-C≡N).\n"
                "핵심 C-C 결합 형성.\n"
                "라세미 (프로키랄 이민)."
            ),
            reactant_smiles="CC=N",
            product_smiles="CC(N)C#N",
            arrows=[
                ArrowData("full", "negative_charge", "CN⁻",
                          "atom", "C(=NH)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=N π",
                          "atom", "N", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "bond", "C-CN",
                          "atom", "C", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),
            ],
            labels={"C-C 형성": "핵심"},
            is_transition_state=True,
            energy_label="TS (CN⁻ 첨가)",
            reagents="HCN 또는 KCN",
            notes="비대칭: Jacobsen 티오우레아 촉매",
        ),
        MechanismStep(
            step_number=3,
            title="니트릴 가수분해 → 카복실산",
            description=(
                "α-아미노니트릴의 산성/염기성 가수분해.\n"
                "C≡N + 2H₂O → COOH (+ NH₄⁺는 α-C에서 잔류).\n"
                "메커니즘: 니트릴 → 이미드산 → 아미드 → 카복실산.\n"
                "6M HCl 가열 필요."
            ),
            reactant_smiles="CC(N)C#N",
            product_smiles="CC(N)C(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O",
                          "atom", "C(≡N)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=3),
                ArrowData("full", "pi_bond", "C≡N",
                          "atom", "N-H", "#E53935", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("full", "lone_pair", "H₂O(2차)",
                          "atom", "C=NH", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=3),
            ],
            labels={"가수분해": "니트릴→산"},
            energy_label="가수분해",
            reagents="6M HCl, Δ",
            notes="단계적: C≡N → 아미드 → 산",
        ),
        MechanismStep(
            step_number=4,
            title="생성물: α-아미노산",
            description=(
                "α-아미노산 생성물.\n"
                "범위: 임의 알데히드 → 해당 아미노산.\n"
                "한계: 라세미 (DL-혼합물).\n"
                "산업: DL-메티오닌 (동물 사료).\n"
                "전생물 화학: Miller-Urey (HCN+NH₃+HCHO→글리신)."
            ),
            reactant_smiles="CC(N)C(=O)O",
            product_smiles="CC(N)C(=O)O",
            arrows=[],
            labels={"α-아미노산": "생성물"},
            energy_label="생성물",
            notes="1850, 최초 아미노산 합성",
        ),
    ],
    energy_diagram=[
        ("RCHO + NH₃\n+ HCN", 0.0),
        ("이민", 5.0),
        ("CN⁻ 첨가 TS", 15.0),
        ("아미노니트릴", -5.0),
        ("α-아미노산", -20.0),
    ],
)


# ─── Wolff Rearrangement (Cycle 11) ───────────────────────────────────────────
# 대표 반응: α-Diazoketone → Ketene (→ homologated acid/ester/amide)

MECHANISMS["wolff_rearrangement"] = MechanismData(
    mechanism_type="wolff_rearrangement",
    title="Wolff 전위 (α-디아조케톤 → 케텐)",
    total_steps=3,
    overall_description=(
        "α-디아조케톤에서 N₂ 이탈 후 [1,2]-전이로 케텐 생성. "
        "Arndt-Eistert 동족체화의 핵심 단계. "
        "RCOOH → RCH₂COOH (1탄소 연장)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="N₂ 이탈: α-디아조케톤 → α-케토카벤",
            description=(
                "광분해(hν), 열분해(Δ), 또는 Ag⁺ 촉매로 N₂ 이탈.\n"
                "Ag⁺: C-N₂ 결합에 배위하여 활성화.\n"
                "생성물: α-케토카벤 (일중항, 매우 반응성).\n"
                "부산물: N₂ 기체 (열역학 구동력)."
            ),
            reactant_smiles="O=CC=[N+]=[N-]",
            product_smiles="O=C[C]",
            arrows=[
                ArrowData("full", "bond", "C-N₂",
                          "atom", "N₂(이탈)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "bond", "N=N",
                          "atom", "N₂ 기체", "#FF6F00", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("half", "bond", "카벤",
                          "atom", "C:", "#9C27B0", 0.3,
                          from_atom_idx=2, to_atom_idx=2),
            ],
            labels={"카벤": "일중항"},
            energy_label="N₂ 이탈",
            reagents="hν 또는 Ag₂O",
            notes="ΔG << 0 (N₂ 매우 안정)",
        ),
        MechanismStep(
            step_number=2,
            title="[1,2]-전이 → 케텐 (C=C=O)",
            description=(
                "α-케토카벤의 [1,2]-전이.\n"
                "R기가 C1에서 C2(카벤)로 이동.\n"
                "C1-C2 결합 차수: 1 → 2, C2=O: C=O → =C=O.\n"
                "생성물: 케텐 (누적 이중결합).\n"
                "입체특이적: 이동기 입체배치 보존."
            ),
            reactant_smiles="O=C[C]",
            product_smiles="C=C=O",
            arrows=[
                ArrowData("full", "bond", "R 이동",
                          "atom", "C(카벤)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=2),
                ArrowData("full", "bond", "C-C → C=C",
                          "atom", "케텐", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "bond", "C=O → =C=O",
                          "atom", "O", "#43A047", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"[1,2]-전이": "Wolff"},
            is_transition_state=True,
            energy_label="TS (Wolff)",
            notes="Arndt-Eistert 핵심 단계",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 케텐 + 친핵체 포획",
            description=(
                "케텐이 친핵체에 의해 포획.\n"
                "H₂O → 카복실산 (동족체화: RCOOH → RCH₂COOH).\n"
                "ROH → 에스터, RNH₂ → 아미드.\n"
                "응용: β-아미노산 합성 (α-아미노산에서)."
            ),
            reactant_smiles="CC(=O)O",
            product_smiles="CC(=O)O",
            arrows=[],
            labels={"케텐 포획": "생성물"},
            energy_label="생성물",
            notes="1탄소 동족체화",
        ),
    ],
    energy_diagram=[
        ("α-디아조케톤", 0.0),
        ("α-케토카벤\n+ N₂", 25.0),
        ("Wolff TS", 20.0),
        ("케텐\n+ 친핵체", -15.0),
    ],
)


# ─── Henry Reaction / Nitroaldol (Cycle 11) ───────────────────────────────────
# 대표 반응: CH3NO2 + RCHO → RCH(OH)CH2NO2 (β-nitro alcohol)

MECHANISMS["henry_reaction"] = MechanismData(
    mechanism_type="henry_reaction",
    title="Henry 반응 (니트로알돌, β-니트로 알코올)",
    total_steps=3,
    overall_description=(
        "니트로알칸 + 알데히드 → β-니트로 알코올. "
        "염기 촉매 C-C 결합 형성. 니트로네이트 음이온이 친핵체. "
        "원자 경제성 100%."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="염기 탈양성자화 → 니트로네이트 음이온",
            description=(
                "염기(NaOH, K₂CO₃, Et₃N, DBU)가 니트로알칸 α-H 제거.\n"
                "니트로기 전자끌기: α-H 산성 (pKa ~17).\n"
                "니트로네이트: C와 양 O에 음전하 비편재.\n"
                "니트로네이트 = C-친핵체 (움폴룽)."
            ),
            reactant_smiles="C[N+](=O)[O-]",
            product_smiles="[CH2-][N+](=O)[O-]",
            arrows=[
                ArrowData("full", "lone_pair", "B: (염기)",
                          "atom", "H(α)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "C-H",
                          "atom", "B-H", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C-N",
                          "atom", "C=N", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"니트로네이트": "음이온"},
            energy_label="탈양성자화",
            reagents="NaOH 또는 Et₃N",
            notes="pKa(CH₃NO₂) ≈ 17",
        ),
        MechanismStep(
            step_number=2,
            title="니트로네이트의 알데히드 C=O 공격",
            description=(
                "니트로네이트 α-탄소가 알데히드 카보닐 공격.\n"
                "핵심 C-C 결합 형성.\n"
                "결과: β-니트로 알콕사이드 중간체.\n"
                "부분입체선택성: syn/anti 혼합물 일반적.\n"
                "비대칭: Cu(II)-BOX, La-Li-BINOL."
            ),
            reactant_smiles="[CH2-][N+](=O)[O-]",
            product_smiles="OC(C[N+](=O)[O-])C",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻(니트로네이트)",
                          "atom", "C(=O)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "C=O π",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-C(new)",
                          "atom", "bond", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"C-C 형성": "핵심"},
            is_transition_state=True,
            energy_label="TS (C-C 형성)",
            notes="syn/anti 혼합 (비대칭 촉매로 제어)",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: β-니트로 알코올",
            description=(
                "알콕사이드 양성자화 → β-니트로 알코올.\n"
                "다용도 중간체:\n"
                "환원(NO₂→NH₂) → 1,2-아미노알코올;\n"
                "탈수 → 니트로알켄;\n"
                "Nef 반응 → 알데히드/케톤.\n"
                "원자 경제성 100%."
            ),
            reactant_smiles="OC(C[N+](=O)[O-])C",
            product_smiles="OC(C[N+](=O)[O-])C",
            arrows=[],
            labels={"β-니트로 알코올": "생성물"},
            energy_label="생성물",
            notes="Louis Henry, 1895",
        ),
    ],
    energy_diagram=[
        ("RCH₂NO₂\n+ RCHO", 0.0),
        ("니트로네이트", 5.0),
        ("C-C TS", 14.0),
        ("β-니트로\n알코올", -12.0),
    ],
)


# ══════════════════════════════════════════════════════════════════════
# Cycle 12 Gold Standard Templates (TASK-MECH-128~132, 2026-03-22)
# ══════════════════════════════════════════════════════════════════════

MECHANISMS["shapiro_reaction"] = MechanismData(
    mechanism_type="shapiro_reaction",
    title="Shapiro 반응 (토실히드라존 → 알켄)",
    total_steps=4,
    overall_description=(
        "토실히드라존 + 2당량 BuLi → 이중음이온 → 비닐 디아조늄 → N₂ 손실 → 비닐 음이온 → 알켄. "
        "Hofmann 선택성 (덜 치환된 알켄). Robert Shapiro (1967)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이중 탈양성자화 → 이중음이온",
            description=(
                "1당량 BuLi: N-H 탈양성자화 (pKa ~13).\n"
                "2당량 BuLi: α-C-H 탈양성자화.\n"
                "결과: 이중음이온 (C⁻ + N⁻).\n"
                "조건: -78°C, THF."
            ),
            reactant_smiles="CC(=NNS(=O)(=O)c1ccc(C)cc1)C",
            product_smiles="[CH-]=NN(S(=O)(=O)c1ccc(C)cc1)[Li]",
            arrows=[
                ArrowData("full", "lone_pair", "BuLi",
                          "atom", "H(N)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "N-H",
                          "atom", "Bu-H", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "lone_pair", "BuLi(2nd)",
                          "atom", "H(α)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"이중음이온": "핵심 중간체"},
            energy_label="탈양성자화",
            reagents="n-BuLi (2 equiv), THF, -78°C",
            notes="pKa(NHTos) ≈ 13, pKa(α-H) ≈ 30+",
        ),
        MechanismStep(
            step_number=2,
            title="α-제거 → 비닐 디아조늄",
            description=(
                "승온 시 α-제거 (1,1-제거).\n"
                "토실술폰아미드 이탈 → TsNLi⁻.\n"
                "비닐 디아조늄 종 (C=C-N₂) 생성.\n"
                "α-제거: 카르밴이온과 N₂가 같은 탄소에."
            ),
            reactant_smiles="[CH-]=NN(S(=O)(=O)c1ccc(C)cc1)[Li]",
            product_smiles="C=C[N-][N+]#N",
            arrows=[
                ArrowData("full", "bond", "C-N(Ts)",
                          "atom", "TsNLi⁻", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N-S",
                          "atom", "이탈", "#FF6D00", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C=N",
                          "atom", "보존", "#43A047", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"비닐 디아조늄": "중간체"},
            is_transition_state=True,
            energy_label="α-제거 TS",
            notes="승온 (-78°C → 0°C)",
        ),
        MechanismStep(
            step_number=3,
            title="N₂ 손실 → 비닐 카르밴이온",
            description=(
                "비닐 디아조늄에서 N₂ 가스 방출.\n"
                "ΔG ≈ -60 kcal/mol (강력 추진력).\n"
                "비닐 카르밴이온 (sp² 혼성) 생성.\n"
                "Bamford-Stevens와 대비: 1당량 base → 카르벤."
            ),
            reactant_smiles="C=C[N-][N+]#N",
            product_smiles="[CH2-]C=C",
            arrows=[
                ArrowData("full", "bond", "C-N₂",
                          "atom", "N≡N↑", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "negative_charge", "C⁻",
                          "atom", "비닐 음이온", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=0),
                ArrowData("full", "bond", "C=C",
                          "atom", "보존", "#43A047", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"비닐 카르밴이온": "sp²"},
            energy_label="N₂ 손실",
            notes="N₂ 가스 방출이 반응 추진력",
        ),
        MechanismStep(
            step_number=4,
            title="양성자화 → 알켄 (Hofmann 선택성)",
            description=(
                "비닐 카르밴이온이 양성자화.\n"
                "덜 치환된 끝에서 양성자화 → 덜 치환된 알켄.\n"
                "Hofmann 선택성: 입체적 제어.\n"
                "부산물: TsNHLi + N₂ + LiH."
            ),
            reactant_smiles="[CH2-]C=C",
            product_smiles="C=CC",
            arrows=[],
            labels={"Hofmann 알켄": "생성물"},
            energy_label="생성물",
            notes="Hofmann 선택성 (덜 치환된 알켄)",
        ),
    ],
    energy_diagram=[
        ("토실히드라존", 0.0),
        ("이중음이온", 8.0),
        ("α-제거 TS", 22.0),
        ("비닐 음이온", 10.0),
        ("알켄", -15.0),
    ],
)

MECHANISMS["peterson_olefination"] = MechanismData(
    mechanism_type="peterson_olefination",
    title="Peterson 올레핀화 (α-실릴 카르밴이온 → 알켄)",
    total_steps=3,
    overall_description=(
        "α-실릴 카르밴이온 + C=O → β-히드록시실란 → 알켄 + R₃SiOH. "
        "산 조건: E-알켄, 염기 조건: Z-알켄. Donald J. Peterson (1968)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵 첨가: α-실릴 카르밴이온 → C=O",
            description=(
                "TMSCH₂Li/MgCl이 알데히드/케톤 C=O를 공격.\n"
                "α-실리콘 효과: σ*C-Si / p 오비탈 겹침으로 안정화.\n"
                "β-히드록시실란 중간체 (syn + anti 부분입체이성질체)."
            ),
            reactant_smiles="[CH2-][Si](C)(C)C",
            product_smiles="OC(C[Si](C)(C)C)C",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻(실릴)",
                          "atom", "C(=O)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "C=O π",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-C(new)",
                          "atom", "결합", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"β-히드록시실란": "중간체"},
            energy_label="친핵 첨가",
            reagents="TMSCH₂Li, THF, -78°C",
            notes="α-실리콘 효과 (σ*C-Si 안정화)",
        ),
        MechanismStep(
            step_number=2,
            title="제거: 산(E) 또는 염기(Z) 조건",
            description=(
                "산(BF₃, TsOH): anti-periplanar E2-유사 → E-알켄.\n"
                "염기(KH, NaH): syn-periplanar E1cb-유사 → Z-알켄.\n"
                "입체특이적: anti-diastereomer → E, syn → Z.\n"
                "Wittig 대비 장점: E/Z 제어 용이."
            ),
            reactant_smiles="OC(C[Si](C)(C)C)C",
            product_smiles="C=CC",
            arrows=[
                ArrowData("full", "bond", "O-Si",
                          "atom", "silicate", "#FF6D00", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-Si",
                          "atom", "절단", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C=C",
                          "atom", "형성", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"E/Z 제어": "핵심"},
            is_transition_state=True,
            energy_label="제거 TS",
            notes="산=E-알켄, 염기=Z-알켄",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알켄 + R₃SiOH",
            description=(
                "알켄 + 트리알킬실라놀 (R₃SiOH) 부산물.\n"
                "Wittig 대비: (1) E/Z 제어, (2) P=O 없음, (3) 온건 조건.\n"
                "제한: α-실릴 유기리튬 제조 필요."
            ),
            reactant_smiles="C=CC",
            product_smiles="C=CC",
            arrows=[],
            labels={"알켄": "생성물"},
            energy_label="생성물",
            notes="부산물: R₃SiOH",
        ),
    ],
    energy_diagram=[
        ("α-실릴 카르밴이온\n+ RCHO", 0.0),
        ("β-히드록시실란", -5.0),
        ("제거 TS", 12.0),
        ("알켄 + R₃SiOH", -18.0),
    ],
)

MECHANISMS["mitsunobu_reaction"] = MechanismData(
    mechanism_type="mitsunobu_reaction",
    title="Mitsunobu 반응 (ROH → R-Nu, 입체반전)",
    total_steps=4,
    overall_description=(
        "ROH + DIAD + PPh₃ + NuH → R-Nu (입체반전). "
        "S_N2 메커니즘으로 배치 반전. Oyo Mitsunobu (1967)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="PPh₃ + DIAD → 베타인 형성",
            description=(
                "PPh₃가 DIAD의 N=N 이중결합을 공격.\n"
                "쯔비터이온 베타인: P⁺-N⁻ 형성.\n"
                "이 종이 알코올을 활성화하는 반응성 종.\n"
                "조건: 0°C, THF."
            ),
            reactant_smiles="c1ccc(cc1)P(c1ccccc1)c1ccccc1",
            product_smiles="O=C(OC(C)C)N([P+](c1ccccc1)(c1ccccc1)c1ccccc1)NC(=O)OC(C)C",
            arrows=[
                ArrowData("full", "lone_pair", "PPh₃",
                          "atom", "N=N", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "N=N π",
                          "atom", "N⁻", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "P-N(new)",
                          "atom", "결합", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"베타인": "쯔비터이온"},
            energy_label="베타인 형성",
            reagents="PPh₃, DIAD, THF, 0°C",
            notes="발열 반응",
        ),
        MechanismStep(
            step_number=2,
            title="알코올 활성화 → 옥시포스포늄",
            description=(
                "베타인 N⁻가 알코올 OH를 탈양성자화.\n"
                "알콕사이드가 인(P)을 공격 → 히드라지드 N⁻ 이탈.\n"
                "옥시포스포늄 염 (R-O-P⁺Ph₃) 형성.\n"
                "C-O 결합이 SN2 공격에 활성화됨."
            ),
            reactant_smiles="O=C(OC(C)C)N([P+](c1ccccc1)(c1ccccc1)c1ccccc1)NC(=O)OC(C)C",
            product_smiles="CO[P+](c1ccccc1)(c1ccccc1)c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "O⁻(알콕사이드)",
                          "atom", "P⁺", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "N-P",
                          "atom", "이탈", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "O-P(new)",
                          "atom", "결합", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"옥시포스포늄": "활성 종"},
            energy_label="활성화",
            notes="알코올 OH → 좋은 이탈기",
        ),
        MechanismStep(
            step_number=3,
            title="SN2 치환 → 입체반전",
            description=(
                "친핵체(카르복실레이트, 아지드, 프탈이미드 등)가\n"
                "활성화된 탄소에 후면 공격.\n"
                "OPPh₃⁺ = 우수한 이탈기.\n"
                "Walden 반전: 배치 반전."
            ),
            reactant_smiles="CO[P+](c1ccccc1)(c1ccccc1)c1ccccc1",
            product_smiles="COC(=O)C",
            arrows=[
                ArrowData("full", "lone_pair", "Nu⁻",
                          "atom", "C(활성)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "C-O(PPh₃)",
                          "atom", "이탈", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C-Nu(new)",
                          "atom", "결합", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"SN2": "속도결정단계"},
            is_transition_state=True,
            energy_label="SN2 TS",
            notes="1°/2° 알코올만. 3° = 실패.",
        ),
        MechanismStep(
            step_number=4,
            title="생성물: R-Nu (반전) + OPPh₃ + 히드라지드",
            description=(
                "R-Nu: 출발 알코올 대비 입체반전.\n"
                "부산물: OPPh₃ + 디이소프로필 히드라지드.\n"
                "원자 비경제적 (PPh₃ + DIAD 화학양론적 소모).\n"
                "응용: 락톤화, sec-알코올 반전, 에스테르/에테르 형성."
            ),
            reactant_smiles="COC(=O)C",
            product_smiles="COC(=O)C",
            arrows=[],
            labels={"R-Nu": "생성물 (반전)"},
            energy_label="생성물",
            notes="Oyo Mitsunobu, 1967",
        ),
    ],
    energy_diagram=[
        ("ROH + DIAD\n+ PPh₃", 0.0),
        ("베타인", -5.0),
        ("옥시포스포늄", 2.0),
        ("SN2 TS", 18.0),
        ("R-Nu + OPPh₃", -20.0),
    ],
)

MECHANISMS["eschenmoser_tanabe"] = MechanismData(
    mechanism_type="eschenmoser_tanabe",
    title="Eschenmoser-Tanabe 단편화 (에폭시 케톤 → 알키닐 케톤)",
    total_steps=3,
    overall_description=(
        "α,β-에폭시 케톤 + TsNHNH₂ → 토실히드라존 → 염기 유도 retro-[2+2+2] → "
        "알키닐 케톤 + N₂ + TsH. Albert Eschenmoser & Masato Tanabe (1967)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="토실히드라존 형성",
            description=(
                "에폭시 케톤의 C=O + TsNHNH₂ → 토실히드라존.\n"
                "표준 축합: C=O + H₂N-NHTs → C=N-NHTs + H₂O.\n"
                "에폭사이드 고리는 유지됨.\n"
                "조건: AcOH 촉매, 상온."
            ),
            reactant_smiles="O=C1C(O1)CCC",
            product_smiles="C(=NNS(=O)(=O)c1ccc(C)cc1)C1(OC1)CCC",
            arrows=[
                ArrowData("full", "lone_pair", "NH₂(TsNHNH₂)",
                          "atom", "C=O", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O",
                          "atom", "H₂O", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C=N(new)",
                          "atom", "형성", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"토실히드라존": "기질"},
            energy_label="축합",
            reagents="TsNHNH₂, AcOH, rt",
            notes="에폭사이드 유지",
        ),
        MechanismStep(
            step_number=2,
            title="염기 유도 retro-[2+2+2] 단편화",
            description=(
                "염기(NaOMe, DBU, Et₃N)에 의한 단편화.\n"
                "협주적 retro-[2+2+2]: 에폭사이드 C-O, α-C-C, N-N 결합 동시 절단.\n"
                "anti-periplanar 기하 필수.\n"
                "N₂ 방출이 반응 추진력."
            ),
            reactant_smiles="C(=NNS(=O)(=O)c1ccc(C)cc1)C1(OC1)CCC",
            product_smiles="C#CC(=O)CCC",
            arrows=[
                ArrowData("full", "bond", "에폭사이드 C-O",
                          "atom", "절단", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "α-C-C",
                          "atom", "절단", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N-N → N₂",
                          "atom", "N₂↑", "#FF6D00", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C≡C(new)",
                          "atom", "형성", "#43A047", 0.5,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"retro-[2+2+2]": "핵심"},
            is_transition_state=True,
            energy_label="단편화 TS",
            notes="협주적 메커니즘",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알키닐 케톤",
            description=(
                "고리 열림 생성물: 알키닐 케톤 (α,β-이논).\n"
                "N₂ 가스 방출, TsH 부산물.\n"
                "응용: 스테로이드 합성 (비타민 B12), 매크로라이드, 테르펜."
            ),
            reactant_smiles="C#CC(=O)CCC",
            product_smiles="C#CC(=O)CCC",
            arrows=[],
            labels={"알키닐 케톤": "생성물"},
            energy_label="생성물",
            notes="Eschenmoser (1967), Tanabe (1967)",
        ),
    ],
    energy_diagram=[
        ("에폭시 케톤", 0.0),
        ("토실히드라존", -3.0),
        ("retro-[2+2+2] TS", 20.0),
        ("알키닐 케톤\n+ N₂", -22.0),
    ],
)

MECHANISMS["ramberg_backlund"] = MechanismData(
    mechanism_type="ramberg_backlund",
    title="Ramberg-Bäcklund 반응 (α-할로 술폰 → 알켄 + SO₂)",
    total_steps=3,
    overall_description=(
        "α-할로 술폰 + 염기 → 티이란 디옥사이드 (에피술폰) → "
        "켈레트로픽 SO₂ 방출 → 알켄. Ramberg & Bäcklund (1940)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="분자내 고리화 → 티이란 디옥사이드",
            description=(
                "강염기(t-BuOK, KOH/Al₂O₃)가 α-H 제거 (pKa ~22-25).\n"
                "카르밴이온이 인접 탄소의 할로겐화물 분자내 SN2 치환.\n"
                "생성물: 티이란 1,1-디옥사이드 (에피술폰) — 변형 3원 고리.\n"
                "Meerwein 변형: KOH/Al₂O₃/CCl₄ (원위치 α-염소화)."
            ),
            reactant_smiles="ClCC(S(=O)(=O)CC)CC",
            product_smiles="O=S1(=O)CC1",
            arrows=[
                ArrowData("full", "lone_pair", "t-BuO⁻",
                          "atom", "H(α)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "negative_charge", "C⁻",
                          "atom", "C-Cl", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C-Cl",
                          "atom", "Cl⁻", "#FF6D00", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C-S(고리)",
                          "atom", "형성", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"에피술폰": "변형 3원 고리"},
            energy_label="고리화",
            reagents="t-BuOK 또는 KOH/Al₂O₃",
            notes="분자내 SN2",
        ),
        MechanismStep(
            step_number=2,
            title="켈레트로픽 SO₂ 방출 → 알켄",
            description=(
                "티이란 디옥사이드 → 켈레트로픽 SO₂ 탈출.\n"
                "켈레트로픽 = 같은 원자(S)에서 두 σ결합 동시 절단.\n"
                "[2σ + 2σ] retro-시클로첨가 (궤도 대칭 허용).\n"
                "3원 고리 변형이 추진력.\n"
                "입체화학: suprafacial → cis-알켄 선택적."
            ),
            reactant_smiles="O=S1(=O)CC1",
            product_smiles="C=C",
            arrows=[
                ArrowData("full", "bond", "C-S(1)",
                          "atom", "절단", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C-S(2)",
                          "atom", "절단", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "C=C(new)",
                          "atom", "형성", "#43A047", 0.5,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"켈레트로픽": "궤도대칭 허용"},
            is_transition_state=True,
            energy_label="켈레트로픽 TS",
            notes="SO₂ 가스 탈출 (비가역)",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알켄 + SO₂",
            description=(
                "알켄 생성물: 정의된 입체화학.\n"
                "Z (cis) 선택성 (suprafacial 과정).\n"
                "부산물: SO₂ 가스.\n"
                "응용: 변형 알켄, 매크로사이클릭 알켄.\n"
                "관련: Julia-Lythgoe (또 다른 술폰 기반, 다른 메커니즘)."
            ),
            reactant_smiles="C=C",
            product_smiles="C=C",
            arrows=[],
            labels={"알켄": "생성물"},
            energy_label="생성물",
            notes="Ramberg & Bäcklund, 1940",
        ),
    ],
    energy_diagram=[
        ("α-할로 술폰", 0.0),
        ("에피술폰", 8.0),
        ("켈레트로픽 TS", 18.0),
        ("알켄 + SO₂", -25.0),
    ],
)


# ─── Schmidt Reaction (TASK-MECH-133) ──────────────────────────────────────
# Ketone + HN₃ → amide/lactam via [1,2]-alkyl shift
MECHANISMS["schmidt_reaction"] = MechanismData(
    mechanism_type="schmidt_reaction",
    title="Schmidt 반응 (케톤 + HN₃ → 아미드/락탐)",
    total_steps=5,
    overall_description=(
        "케톤 + HN₃ (산촉매) → 아지도 알코올 → [1,2]-알킬 이동 + N₂ 방출 → "
        "나이트릴륨 이온 → 물 소광 → 아미드 (또는 고리 확장 → 락탐). "
        "Karl Friedrich Schmidt (1924). Curtius 전위의 케톤 버전."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="HN₃ 친핵 공격 → 아지도 알코올",
            description=(
                "산촉매(H₂SO₄, TFA)가 케톤 C=O 양성자화.\n"
                "HN₃ (하이드라조산)의 말단 N이 활성화된 카보닐 탄소에 공격.\n"
                "사면체 중간체: 아지도 알코올 형성.\n"
                "주의: HN₃는 극독성/폭발성 — TMSN₃ 등 안전한 대체제 사용."
            ),
            reactant_smiles="CC(=O)C",
            product_smiles="CC(O)(C)[N-][N+]#N",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "O(C=O)", "#FF6D00", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "lone_pair", "Nα(HN₃)",
                          "atom", "C⁺(카보닐)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O",
                          "atom", "O⁻", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"아지도 알코올": "사면체 중간체"},
            energy_label="친핵 첨가",
            reagents="H₂SO₄ 또는 TFA, HN₃",
            notes="HN₃ 극독성 — 안전 주의",
        ),
        MechanismStep(
            step_number=2,
            title="[1,2]-알킬 이동 + N₂ 방출 → 나이트릴륨 이온",
            description=(
                "OH 양성자화 → H₂O 이탈 → 아지도카르보늄 이온.\n"
                "anti-periplanar 알킬기가 [1,2]-이동: C→N.\n"
                "동시에 N₂ 방출 (강력한 추진력, ΔG ≈ −50 kcal/mol).\n"
                "생성: 나이트릴륨 이온 (R-C≡N⁺-R').\n"
                "고리 케톤: 알킬 이동이 고리 확장을 유발."
            ),
            reactant_smiles="CC(O)(C)[N-][N+]#N",
            product_smiles="C[C+]=NC",
            arrows=[
                ArrowData("full", "bond", "C-OH",
                          "atom", "H₂O", "#FF6D00", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "Cα-R(알킬)",
                          "atom", "N(이동)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N-N₂",
                          "atom", "N₂↑", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"나이트릴륨": "선형 양이온"},
            is_transition_state=True,
            energy_label="[1,2]-이동 TS",
            reagents="H⁺ (산촉매)",
            notes="N₂ 방출이 열역학적 추진력",
        ),
        MechanismStep(
            step_number=3,
            title="물 소광 → 이미늄 수화물",
            description=(
                "나이트릴륨 이온 (R-C≡N⁺-R') + H₂O → 이미늄 수화물.\n"
                "H₂O가 전자 결핍 탄소 공격.\n"
                "사면체 중간체(이미늄 수화물) 형성."
            ),
            reactant_smiles="C[C+]=NC",
            product_smiles="CC(O)(NC)O",
            arrows=[
                ArrowData("full", "lone_pair", "O(H₂O)",
                          "atom", "C⁺(나이트릴륨)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=N⁺",
                          "atom", "N", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "lone_pair", "양성자 이동",
                          "atom", "O→N", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"아미드": "수화 생성물"},
            energy_label="수화",
            reagents="H₂O",
            notes="나이트릴륨 가수분해",
        ),
        MechanismStep(
            step_number=4,
            title="양성자 전달 (토토머화) → 아미드",
            description=(
                "이미늄 수화물 중간체에서 양성자 전달.\n"
                "-OH → C=O, N-H 형성.\n"
                "안정한 아미드(C(=O)-NH) 구조로 재배열."
            ),
            reactant_smiles="CC(O)(NC)O",
            product_smiles="CC(=O)NC",
            arrows=[
                ArrowData("full", "bond", "O-H",
                          "atom", "base", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"tautomer": "양성자 전달"},
            energy_label="토토머화",
        ),
        MechanismStep(
            step_number=5,
            title="생성물: 아미드 (또는 락탐)",
            description=(
                "최종 생성물: 2차 아미드 R-CO-NHR'.\n"
                "고리 확장 시: 원래 n원 고리 → (n+1)원 락탐.\n"
                "응용: ε-카프로락탐 (나일론-6), 대환 락탐.\n"
                "관련 반응: Curtius, Beckmann, Hofmann.\n"
                "Karl Friedrich Schmidt, Ber. 1924, 57, 704."
            ),
            reactant_smiles="CC(=O)NC",
            product_smiles="CC(=O)NC",
            arrows=[],
            labels={"아미드/락탐": "최종 생성물"},
            energy_label="생성물",
            notes="Schmidt, 1924",
        ),
    ],
    energy_diagram=[
        ("케톤 + HN₃", 0.0),
        ("아지도 알코올", -3.0),
        ("[1,2]-이동 TS", 22.0),
        ("나이트릴륨 + N₂", 5.0),
        ("아미드/락탐", -30.0),
    ],
)

# ─── Dakin Reaction (TASK-MECH-134) ─────────────────────────────────────
# Aryl aldehyde/ketone + H₂O₂ (basic) → phenol
MECHANISMS["dakin_reaction"] = MechanismData(
    mechanism_type="dakin_reaction",
    title="Dakin 반응 (아릴 알데히드 + H₂O₂ → 페놀)",
    total_steps=3,
    overall_description=(
        "전자 풍부 아릴 알데히드 (또는 케톤) + H₂O₂/NaOH → "
        "Criegee-유사 중간체 → 아릴 이동 (Baeyer-Villiger형) → 포르메이트 에스터 → "
        "가수분해 → 페놀 + 포름산. Henry Dakin (1909)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="HOO⁻ 친핵 공격 → Criegee-유사 중간체",
            description=(
                "NaOH가 H₂O₂ 탈양성자화 → HOO⁻ (히드로퍼옥시드 음이온).\n"
                "HOO⁻가 아릴 알데히드의 C=O 공격.\n"
                "사면체 Criegee-유사 부가물 형성.\n"
                "기질: p-OH, p-OMe, p-NR₂ 등 전자 공여기 치환 아릴 필수.\n"
                "전자 부족 아릴은 Baeyer-Villiger (mCPBA)로."
            ),
            reactant_smiles="Oc1ccc(C=O)cc1",
            product_smiles="Oc1ccc(C(O)OO)cc1",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻",
                          "atom", "H(H₂O₂)", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "lone_pair", "O⁻(HOO⁻)",
                          "atom", "C=O(ArCHO)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O",
                          "atom", "O⁻", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"Criegee 부가물": "사면체 중간체"},
            energy_label="친핵 첨가",
            reagents="H₂O₂, NaOH (aq)",
            notes="Baeyer-Villiger와 동일 메커니즘",
        ),
        MechanismStep(
            step_number=2,
            title="아릴 이동 → 포르메이트 에스터",
            description=(
                "Criegee 중간체에서 [1,2]-아릴 이동 (Baeyer-Villiger형).\n"
                "아릴기 이동 → O-O 결합 절단 → OH⁻ 이탈.\n"
                "이동 적성: 전자 풍부 아릴 > 알킬 > H.\n"
                "생성물: 아릴 포르메이트 (Ar-O-CHO).\n"
                "비대칭 케톤: 더 전자 풍부한 아릴기가 이동."
            ),
            reactant_smiles="Oc1ccc(C(O)OO)cc1",
            product_smiles="Oc1ccc(OC=O)cc1",
            arrows=[
                ArrowData("full", "bond", "Ar-C(이동)",
                          "atom", "O(퍼옥시)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "O-OH",
                          "atom", "OH⁻(이탈)", "#FF6D00", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "Ar-O(new)",
                          "atom", "형성", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"아릴 이동": "BV형"},
            is_transition_state=True,
            energy_label="[1,2]-이동 TS",
            notes="전자 풍부 아릴만 이동 가능",
        ),
        MechanismStep(
            step_number=3,
            title="가수분해 → 페놀 + 포름산",
            description=(
                "아릴 포르메이트 + NaOH → 가수분해.\n"
                "최종: 페놀 (Ar-OH) + 포름산나트륨 (HCOONa).\n"
                "순효과: ArCHO → ArOH (알데히드 → 페놀, 산화 상태 보존).\n"
                "수율: 전자 공여기 치환 시 60-90%.\n"
                "Henry Dakin, Am. Chem. J. 1909, 42, 477."
            ),
            reactant_smiles="Oc1ccc(OC=O)cc1",
            product_smiles="Oc1ccc(O)cc1",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻",
                          "atom", "C=O(포르메이트)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "Ar-O(에스터)",
                          "atom", "ArO⁻", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "lone_pair", "H⁺ 이동",
                          "atom", "ArOH", "#43A047", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"페놀": "최종 생성물"},
            energy_label="생성물",
            reagents="NaOH (aq)",
            notes="Dakin, 1909",
        ),
    ],
    energy_diagram=[
        ("ArCHO + HOO⁻", 0.0),
        ("Criegee 부가물", -5.0),
        ("아릴 이동 TS", 15.0),
        ("ArO-CHO", -8.0),
        ("ArOH + HCO₂⁻", -25.0),
    ],
)

# ─── Tiffeneau-Demjanov Rearrangement (TASK-MECH-135) ──────────────────
# Cyclic ketone → ring-expanded ketone (+1 C)
MECHANISMS["tiffeneau_demjanov"] = MechanismData(
    mechanism_type="tiffeneau_demjanov",
    title="Tiffeneau-Demjanov 전위 (고리 확장: n → n+1원 케톤)",
    total_steps=5,
    overall_description=(
        "고리형 케톤 + CH₂N₂ → α-디아조케톤 (또는 β-아미노 알코올 경유) → "
        "HNO₂에 의한 디아조화 → N₂ 방출 + [1,2]-알킬 이동 → "
        "한 탄소 확장된 고리 케톤. Tiffeneau (1937), Demjanov."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="디아조메탄 첨가 → α-디아조케톤",
            description=(
                "고리형 케톤 + CH₂N₂ → α-에폭시 케톤 또는 α-아미노 알코올.\n"
                "경로 A: CH₂N₂가 C=O 공격 → α,β-에폭시 케톤.\n"
                "경로 B (고전적): 환원 + 아민화 → β-아미노 알코올.\n"
                "현대적: LiAlH₄ 환원 → NH₂ 도입 → 아미노 알코올.\n"
                "CH₂N₂: 위험물 — Et₂O 용액으로 사용."
            ),
            reactant_smiles="O=C1CCCC1",
            product_smiles="NCC1(O)CCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "C⁻(CH₂N₂)",
                          "atom", "C=O", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O",
                          "atom", "O⁻", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "bond", "C-N₂(new)",
                          "atom", "형성", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"β-아미노 알코올": "핵심 중간체"},
            energy_label="첨가",
            reagents="CH₂N₂ / Et₂O 또는 LiAlH₄→NH₂",
            notes="CH₂N₂ 독성/폭발성 주의",
        ),
        MechanismStep(
            step_number=2,
            title="아질산 탈아민화 → 디아조늄 이온",
            description=(
                "β-아미노 알코올 + HNO₂ (NaNO₂/HCl) → 디아조늄.\n"
                "NH₂ + HONO → N₂⁺ (디아조늄 이온).\n"
                "디아조늄은 극히 불안정: 즉시 다음 단계 진행.\n"
                "수용액, 0-5°C에서 반응 (디아조늄 안정화).\n"
                "van Slyke 탈아민화와 동일 메커니즘."
            ),
            reactant_smiles="NCC1(O)CCCC1",
            product_smiles="[N-]=[N+]=CC1(O)CCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "N(NH₂)",
                          "atom", "NO⁺", "#1565C0", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N-H",
                          "atom", "H₂O", "#FF6D00", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "N=N⁺(형성)",
                          "atom", "디아조늄", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"디아조늄": "불안정 중간체"},
            energy_label="디아조화",
            reagents="NaNO₂, HCl, 0°C",
            notes="디아조늄 즉시 분해",
        ),
        MechanismStep(
            step_number=3,
            title="OH 기반 안키머 보조 → 에폭시드 경유",
            description=(
                "인접 -OH가 anchimeric assistance를 제공합니다.\n"
                "OH가 카르보카티온을 안정화하면서 semi-pinacol 전위 준비.\n"
                "동시에 디아조늄의 N₂ 이탈이 촉진됩니다."
            ),
            reactant_smiles="[N-]=[N+]=CC1(O)CCCC1",
            product_smiles="OC1(CC2CC2)CCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "O 론페어",
                          "atom", "C⁺ (안정화)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"anchimeric": "안키머 보조"},
            energy_label="안키머 보조",
            notes="인접 OH가 전위를 촉진",
        ),
        MechanismStep(
            step_number=4,
            title="N₂ 방출 + [1,2]-알킬 이동 → 고리 확장",
            description=(
                "디아조늄에서 N₂ 이탈 → 1차 카르보양이온.\n"
                "인접 C-C 결합의 anti-periplanar [1,2]-이동.\n"
                "고리형 기질: 이동 → n원 고리가 (n+1)원 고리로 확장.\n"
                "예: 시클로펜타논(5원) → 시클로헥사논(6원).\n"
                "이동 선택성: anti-periplanar 기하에 있는 C-C 결합만 이동."
            ),
            reactant_smiles="OC1(CC2CC2)CCCC1",
            product_smiles="O=C1CCCCC1",
            arrows=[
                ArrowData("full", "bond", "C-N₂⁺",
                          "atom", "N₂↑", "#FF6D00", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "Cα-Cβ(이동)",
                          "atom", "C⁺", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "bond", "C=O(복원)",
                          "atom", "케톤", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"고리 확장": "n→n+1"},
            is_transition_state=True,
            energy_label="[1,2]-이동 TS",
            notes="N₂ 추진력 + 고리 변형 해소",
        ),
        MechanismStep(
            step_number=5,
            title="생성물: 고리 확장 케톤",
            description=(
                "최종 생성물: (n+1)원 고리형 케톤.\n"
                "시클로부타논(4) → 시클로펜타논(5).\n"
                "시클로펜타논(5) → 시클로헥사논(6).\n"
                "시클로헥사논(6) → 시클로헵타논(7).\n"
                "응용: 중대환 고리(7~12원) 합성에 유용.\n"
                "관련: Buchner-Curtius-Schlotterbeck, Arndt-Eistert."
            ),
            reactant_smiles="O=C1CCCCC1",
            product_smiles="O=C1CCCCC1",
            arrows=[],
            labels={"시클로헥사논": "생성물 (6원)"},
            energy_label="생성물",
            notes="Tiffeneau, 1937; Demjanov",
        ),
    ],
    energy_diagram=[
        ("고리형 케톤", 0.0),
        ("β-아미노 알코올", -5.0),
        ("디아조늄", 10.0),
        ("[1,2]-이동 TS", 20.0),
        ("(n+1)원 케톤", -28.0),
    ],
)

# ─── Paal-Knorr Synthesis (TASK-MECH-136) ──────────────────────────────
# 1,4-Diketone + amine → pyrrole (furan/thiophene variants)
MECHANISMS["paal_knorr"] = MechanismData(
    mechanism_type="paal_knorr",
    title="Paal-Knorr 합성 (1,4-디케톤 + 아민 → 피롤)",
    total_steps=3,
    overall_description=(
        "1,4-디케톤 + 1차 아민 → 헤미아미날 → 분자내 고리화 → "
        "이중 탈수 → 방향족 헤테로사이클 (피롤). "
        "변형: NH₃ → 피롤, 산촉매 (아민 없이) → 퓨란, P₄S₁₀ → 티오펜. "
        "Carl Paal & Ludwig Knorr (1884)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아민 첨가 → 헤미아미날 (첫 번째 C=O 공격)",
            description=(
                "1차 아민(RNH₂)이 1,4-디케톤의 첫 번째 C=O 친핵 공격.\n"
                "사면체 중간체 → 탈수 → 에나민/이민.\n"
                "산촉매(AcOH, p-TsOH) 또는 무촉매(가열).\n"
                "첫 번째 H₂O 이탈로 C=N 결합 형성.\n"
                "Dean-Stark 또는 분자체(4Å)로 물 제거."
            ),
            reactant_smiles="CC(=O)CCC(=O)C",
            product_smiles="CC(=NC)CCC(=O)C",
            arrows=[
                ArrowData("full", "lone_pair", "N(RNH₂)",
                          "atom", "C=O(1)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O",
                          "atom", "O⁻", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "bond", "C-O(탈수)",
                          "atom", "H₂O↑", "#FF6D00", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"이민/에나민": "중간체"},
            energy_label="첫 번째 축합",
            reagents="RNH₂, AcOH (촉매), Δ",
            notes="첫 번째 H₂O 이탈",
        ),
        MechanismStep(
            step_number=2,
            title="분자내 고리화 (두 번째 C=O 공격)",
            description=(
                "질소의 비공유전자쌍이 두 번째 C=O를 분자내 공격.\n"
                "5원 고리 형성 → 헤미아미날 중간체.\n"
                "5-exo-trig 고리화 (Baldwin 규칙 허용).\n"
                "두 번째 H₂O 이탈로 추가 C=N 또는 C=C 형성.\n"
                "총 2분자 H₂O 이탈."
            ),
            reactant_smiles="CC(=NC)CCC(=O)C",
            product_smiles="Cc1ccc(C)[nH]1",
            arrows=[
                ArrowData("full", "lone_pair", "N(이민)",
                          "atom", "C=O(2)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O(2)",
                          "atom", "O⁻", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "bond", "C-O(탈수)",
                          "atom", "H₂O↑", "#FF6D00", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"5원 고리": "고리화"},
            is_transition_state=True,
            energy_label="고리화 TS",
            reagents="AcOH, Δ",
            notes="5-exo-trig (Baldwin 허용)",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 피롤 (방향족 헤테로사이클)",
            description=(
                "이중 탈수 후 방향족화 → 2,5-이치환 피롤.\n"
                "6π 전자 방향족 (Hückel 규칙 충족).\n"
                "변형: NH₃ 사용 → N-비치환 피롤.\n"
                "산촉매 (아민 없이) → 퓨란 (O-헤테로사이클).\n"
                "P₄S₁₀ → 티오펜 (S-헤테로사이클).\n"
                "Paal, Ber. 1884; Knorr, Ber. 1884."
            ),
            reactant_smiles="Cc1ccc(C)[nH]1",
            product_smiles="Cc1ccc(C)[nH]1",
            arrows=[],
            labels={"피롤": "방향족 생성물"},
            energy_label="생성물",
            notes="Paal & Knorr, 1884",
        ),
    ],
    energy_diagram=[
        ("1,4-디케톤\n+ RNH₂", 0.0),
        ("이민 중간체", -3.0),
        ("고리화 TS", 12.0),
        ("피롤 + 2H₂O", -35.0),
    ],
)

# ─── Chichibabin Amination (TASK-MECH-137) ──────────────────────────────
# Pyridine + NaNH₂ → 2-aminopyridine
MECHANISMS["chichibabin_amination"] = MechanismData(
    mechanism_type="chichibabin_amination",
    title="Chichibabin 아민화 (피리딘 + NaNH₂ → 2-아미노피리딘)",
    total_steps=3,
    overall_description=(
        "피리딘 + NaNH₂ → Meisenheimer-유사 음이온 σ-복합체 → "
        "H⁻ 이탈 + 재방향족화 → 2-아미노피리딘 + NaH. "
        "Aleksei Chichibabin (1914). SNAr의 특수 사례."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="NH₂⁻ 친핵 공격 → Meisenheimer-유사 σ-복합체",
            description=(
                "NaNH₂의 NH₂⁻ (강한 친핵체/염기)가 피리딘 C2 공격.\n"
                "N의 전자 끌기 효과로 C2, C4 전자 부족.\n"
                "C2 공격이 지배적 (C4보다 덜 입체적).\n"
                "결과: 음이온 σ-복합체 (Meisenheimer 부가물).\n"
                "sp3 C2: 방향족성 일시 상실."
            ),
            reactant_smiles="c1ccncc1",
            product_smiles="NC1C=CN=CC1",
            arrows=[
                ArrowData("full", "lone_pair", "N⁻(NH₂⁻)",
                          "atom", "C2(피리딘)", "#1565C0", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C2=C3",
                          "atom", "C3", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C-N(고리)",
                          "atom", "N⁻", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"σ-복합체": "Meisenheimer-유사"},
            energy_label="σ-복합체",
            reagents="NaNH₂, 무용매 또는 PhNMe₂",
            notes="C2 선택적 (C4도 소량)",
        ),
        MechanismStep(
            step_number=2,
            title="H⁻ 이탈 + 재방향족화",
            description=(
                "σ-복합체에서 C2-H가 히드리드(H⁻)로 이탈.\n"
                "이탈 추진력: 방향족성 회복 (RE ≈ 25 kcal/mol).\n"
                "H⁻ + Na⁺ → NaH (부산물).\n"
                "대안적 관점: E1cb 메커니즘 (NH₂⁻가 H⁻ 이탈 보조).\n"
                "고온(100-150°C) 필요: 무용매 또는 PhNMe₂(DMF 대용)."
            ),
            reactant_smiles="NC1C=CN=CC1",
            product_smiles="Nc1ccccn1",
            arrows=[
                ArrowData("full", "bond", "C2-H",
                          "atom", "H⁻(이탈)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "C=C(복원)",
                          "atom", "방향족화", "#43A047", 0.4,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=N(복원)",
                          "atom", "방향족화", "#43A047", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"재방향족화": "추진력"},
            is_transition_state=True,
            energy_label="H⁻ 이탈 TS",
            reagents="Δ (100-150°C)",
            notes="NaH 부산물 → H₂ 방출 가능",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 2-아미노피리딘 + NaH",
            description=(
                "최종 생성물: 2-아미노피리딘.\n"
                "NaH 부산물 (물 분해 시 H₂ 발생).\n"
                "수율: 40-80% (기질, 조건 의존).\n"
                "응용: 의약품 중간체, 리간드, 촉매.\n"
                "2-아미노피리딘 유도체: 피리미딘 합성 전구체.\n"
                "Chichibabin, J. Russ. Phys. Chem. Soc. 1914, 46, 1216."
            ),
            reactant_smiles="Nc1ccccn1",
            product_smiles="Nc1ccccn1",
            arrows=[],
            labels={"2-아미노피리딘": "생성물"},
            energy_label="생성물",
            notes="Chichibabin, 1914",
        ),
    ],
    energy_diagram=[
        ("피리딘 + NH₂⁻", 0.0),
        ("σ-복합체", 12.0),
        ("H⁻ 이탈 TS", 25.0),
        ("2-아미노피리딘\n+ NaH", -15.0),
    ],
)


# ─── Neber Rearrangement ─────────────────────────────────────────────
# 대표 반응: R-C(=N-OTs)R' + base → azirine → α-amino ketone
# Neber, P.W.; Burgard, A. Liebigs Ann. 1932, 493, 281.

MECHANISMS["neber_rearrangement"] = MechanismData(
    mechanism_type="neber_rearrangement",
    title="Neber 전위 (옥심 토실레이트 → α-아미노 케톤)",
    total_steps=5,
    overall_description=(
        "Neber 전위: 옥심의 토실레이트(O-토실옥심)를 염기 처리하면 "
        "α-탈양성자화 → 아지린(2H-azirine) 중간체 형성 → 가수분해를 거쳐 "
        "α-아미노 케톤을 생성합니다. α-수소가 있는 케톤 옥심에서만 진행."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="α-탈양성자화 (Base-mediated)",
            description=(
                "염기(KOEt, NaH 등)가 C=N 인접 α-H를 제거합니다.\n"
                "C=N 옆 탄소에 음전하(카르바니온) 형성.\n"
                "N-OTs의 이탈능이 구동력."
            ),
            reactant_smiles="CC(=NOC)C",
            product_smiles="[CH2-]C(=NOC)C",
            arrows=[
                ArrowData("full", "lone_pair", "Base: 론페어",
                          "atom", "α-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"α-C": "탈양성자화 위치"},
            energy_label="ΔG‡ ≈ 20 kcal/mol",
            reagents="KOEt / EtOH",
        ),
        MechanismStep(
            step_number=2,
            title="OTs 이탈 + 3원환 형성 (아지린 형성)",
            description=(
                "α-카르바니온의 론페어가 N을 분자내 공격.\n"
                "OTs 이탈기가 떠나면서 C-N 결합 형성.\n"
                "고도로 변형된 2H-아지린(3원환) 중간체 생성."
            ),
            reactant_smiles="[CH2-]C(=NOC)C",
            product_smiles="CC1(C)C=N1",
            arrows=[
                ArrowData("full", "negative_charge", "α-C⁻",
                          "atom", "N (electrophilic)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "N-OTs",
                          "atom", "OTs (이탈기)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N": "친전자 중심", "OTs": "이탈기"},
            is_transition_state=True,
            energy_label="TS: 고리화",
        ),
        MechanismStep(
            step_number=3,
            title="2H-아지린 중간체",
            description=(
                "2H-아지린: 3원환 이민.\n"
                "높은 고리 변형 에너지 → 가수분해에 취약.\n"
                "이 중간체는 분리 가능한 경우도 있음 (Neber, 1932)."
            ),
            reactant_smiles="CC1(C)C=N1",
            product_smiles="CC1(C)C=N1",
            arrows=[],
            labels={"아지린": "3원환 중간체"},
            energy_label="불안정 중간체",
            notes="2H-Azirine: separable in some cases",
        ),
        MechanismStep(
            step_number=4,
            title="가수분해: 아지린 개환",
            description=(
                "수용액 조건에서 H₂O가 아지린 C=N 결합을 공격.\n"
                "3원환이 열리면서 α-아미노 알코올 → 타우토머화.\n"
                "최종적으로 α-아미노 케톤 생성."
            ),
            reactant_smiles="CC1(C)C=N1",
            product_smiles="CC(=O)C(C)N",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O",
                          "atom", "C=N", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"H₂O": "친핵체"},
            energy_label="가수분해",
            reagents="H₂O / H⁺",
        ),
        MechanismStep(
            step_number=5,
            title="생성물: α-아미노 케톤",
            description=(
                "α-아미노 케톤 (R-CO-CHR'-NH₂).\n"
                "의약품 합성에 중요한 빌딩 블록.\n"
                "Neber, P.W.; Burgard, A. Liebigs Ann. 1932, 493, 281."
            ),
            reactant_smiles="CC(=O)C(C)N",
            product_smiles="CC(=O)C(C)N",
            arrows=[],
            labels={"α-아미노 케톤": "생성물"},
            energy_label="생성물",
            notes="Neber, 1932",
        ),
    ],
    energy_diagram=[
        ("옥심 토실레이트", 0.0),
        ("α-카르바니온", 8.0),
        ("고리화 TS", 22.0),
        ("2H-아지린", 15.0),
        ("가수분해 TS", 20.0),
        ("α-아미노 케톤", -10.0),
    ],
)

# ─── Lossen Rearrangement ─────────────────────────────────────────────
# 대표 반응: R-CO-NHOH (hydroxamic acid) → R-N=C=O (isocyanate) + R'COOH
# Lossen, W. Liebigs Ann. 1872, 161, 347.

MECHANISMS["lossen_rearrangement"] = MechanismData(
    mechanism_type="lossen_rearrangement",
    title="Lossen 전위 (히드록삼산 → 이소시아네이트)",
    total_steps=5,
    overall_description=(
        "Lossen 전위: 히드록삼산(R-CO-NHOH)의 O-아실화 유도체를 "
        "염기 처리하면 [1,2]-작용기 이동(R → N) → 이소시아네이트(R-N=C=O)를 "
        "생성합니다. Curtius, Hofmann 전위와 유사한 니트렌 경로."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="히드록삼산 O-활성화",
            description=(
                "히드록삼산 N-OH를 이탈기(OAc, OTs, OCOCl 등)로 활성화.\n"
                "O-아실히드록삼산: R-CO-NH-O-COR'.\n"
                "이탈기 능력이 전위 구동력."
            ),
            reactant_smiles="CC(=O)NO",
            product_smiles="CC(=O)NOC(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "OH 론페어",
                          "atom", "C=O (활성화제)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"OH": "활성화 위치"},
            energy_label="활성화",
            reagents="Ac₂O or ClCOOEt",
        ),
        MechanismStep(
            step_number=2,
            title="N-탈양성자화",
            description=(
                "염기(Et₃N, pyridine)가 N-H를 제거.\n"
                "N 음이온 형성 → 이탈기 방출 준비.\n"
                "음이온이 전위의 직접적 전구체."
            ),
            reactant_smiles="CC(=O)NOC(C)=O",
            product_smiles="CC(=O)[N-]OC(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "Base",
                          "atom", "N-H", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N": "탈양성자화"},
            energy_label="탈양성자화",
            reagents="Et₃N",
        ),
        MechanismStep(
            step_number=3,
            title="[1,2]-이동 + 이탈기 방출 (전이상태)",
            description=(
                "R기(alkyl/aryl)가 C에서 N으로 [1,2]-이동.\n"
                "동시에 O-COR' 이탈기 방출.\n"
                "Curtius 전위와 동일한 전이상태 토폴로지.\n"
                "전이상태: 부분적 C-R 절단 + 부분적 N-R 형성."
            ),
            reactant_smiles="CC(=O)[N-]OC(C)=O",
            product_smiles="CN=C=O",
            arrows=[
                ArrowData("full", "bond", "C-R 결합",
                          "atom", "N (electron-deficient)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "N-O 결합",
                          "atom", "O (이탈기)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"R": "[1,2]-이동기", "OCOR'": "이탈기"},
            is_transition_state=True,
            energy_label="TS: [1,2]-shift",
        ),
        MechanismStep(
            step_number=4,
            title="이소시아네이트 생성",
            description=(
                "R-N=C=O (이소시아네이트) 형성.\n"
                "부산물: R'COO⁻ (카르복실레이트).\n"
                "이소시아네이트는 반응성이 높아 즉시 후속반응 가능."
            ),
            reactant_smiles="CN=C=O",
            product_smiles="CN=C=O",
            arrows=[],
            labels={"이소시아네이트": "핵심 중간체"},
            energy_label="이소시아네이트",
            notes="Curtius/Hofmann과 동일한 중간체",
        ),
        MechanismStep(
            step_number=5,
            title="H₂O 가수분해 → 아민 + CO₂",
            description=(
                "이소시아네이트 + H₂O → 카르밤산 → 자발적 탈카르복실화.\n"
                "최종 생성물: 1차 아민 (R-NH₂) + CO₂.\n"
                "또는 알코올 → 카르바메이트(우레탄) 형성.\n"
                "Lossen, Liebigs Ann. 1872, 161, 347."
            ),
            reactant_smiles="CN=C=O",
            product_smiles="CN",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O",
                          "atom", "C=N=O", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"H₂O": "가수분해"},
            energy_label="생성물",
            reagents="H₂O",
            notes="Lossen, 1872",
        ),
    ],
    energy_diagram=[
        ("히드록삼산", 0.0),
        ("O-아실화체", 5.0),
        ("N-음이온", 10.0),
        ("[1,2]-이동 TS", 28.0),
        ("이소시아네이트", -5.0),
        ("아민 + CO₂", -25.0),
    ],
)

# ─── Hofmann-Löffler-Freytag Reaction ─────────────────────────────────
# 대표 반응: N-chloroamine + hν → radical → δ-C-H abstraction → pyrrolidine
# Hofmann, A.W. Ber. 1883, 16, 558; Löffler, K.; Freytag, C. Ber. 1909, 42, 3427.

MECHANISMS["hofmann_loffler_freytag"] = MechanismData(
    mechanism_type="hofmann_loffler_freytag",
    title="Hofmann-Löffler-Freytag 반응 (N-할로아민 → 피롤리딘)",
    total_steps=6,
    overall_description=(
        "Hofmann-Löffler-Freytag: N-할로아민(R₂N-Cl)에 광조사(hν) 또는 "
        "산 촉매하에 N-라디칼 생성 → 1,5-HAT(δ-C-H 추출) → "
        "δ-탄소 라디칼 → 분자내 고리화 → 피롤리딘 형성."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="N-Cl 동종분해 (hν)",
            description=(
                "광조사(hν, 254 nm) 또는 H₂SO₄/Fe²⁺ 조건에서\n"
                "N-Cl 결합이 동종분해(homolysis).\n"
                "N-라디칼(아미닐 라디칼) + Cl· 생성."
            ),
            reactant_smiles="ClN(CCCC)C",
            product_smiles="[NH](CCCC)C",
            arrows=[
                ArrowData("half", "bond", "N-Cl",
                          "atom", "N· + Cl·", "#FF6600", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N-Cl": "동종분해"},
            energy_label="hν (254 nm)",
            reagents="hν or H₂SO₄",
            notes="라디칼 화살표: 반쪽 화살표(주황)",
        ),
        MechanismStep(
            step_number=2,
            title="1,5-HAT (δ-C-H 추출)",
            description=(
                "아미닐 라디칼(N·)이 6원환 전이상태를 통해\n"
                "δ-탄소의 H를 추출 (1,5-수소 원자 이동, HAT).\n"
                "6원환 TS가 5원환이나 7원환보다 유리 (Barton rule)."
            ),
            reactant_smiles="[NH](CCCC)C",
            product_smiles="N(CC[CH]C)C",
            arrows=[
                ArrowData("half", "bond", "δ-C-H",
                          "atom", "N·", "#FF6600", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"δ-C": "H 추출 위치", "N·": "아미닐 라디칼"},
            is_transition_state=True,
            energy_label="TS: 6원환 (1,5-HAT)",
        ),
        MechanismStep(
            step_number=3,
            title="δ-탄소 라디칼 중간체",
            description=(
                "δ-탄소에 라디칼 형성.\n"
                "N-H가 복원됨 (HAT로 수소 획득).\n"
                "라디칼 안정성: 3° > 2° > 1° (선택성 영향)."
            ),
            reactant_smiles="N(CC[CH]C)C",
            product_smiles="N(CC[CH]C)C",
            arrows=[],
            labels={"δ-C·": "라디칼"},
            energy_label="라디칼 중간체",
            notes="탄소 라디칼: sp2-like",
        ),
        MechanismStep(
            step_number=4,
            title="Cl· 재결합 → δ-클로로아민",
            description=(
                "용액 내 Cl 라디칼이 δ-탄소 라디칼과 재결합.\n"
                "δ-클로로아민(N-H, δ-C-Cl) 형성.\n"
                "라디칼 체인 종결 단계."
            ),
            reactant_smiles="N(CC[CH]C)C",
            product_smiles="N(CCC(Cl)C)C",
            arrows=[
                ArrowData("half", "atom", "Cl·",
                          "atom", "δ-C·", "#FF6600", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"Cl·": "라디칼 재결합"},
            energy_label="재결합",
        ),
        MechanismStep(
            step_number=5,
            title="분자내 SN2 고리화 (염기 처리)",
            description=(
                "NaOH/KOH 처리 시 N-H 탈양성자화.\n"
                "N 음이온이 δ-C-Cl을 분자내 SN2 공격.\n"
                "5원환(피롤리딘) 형성 + Cl⁻ 이탈."
            ),
            reactant_smiles="N(CCC(Cl)C)C",
            product_smiles="CN1CCC(C)C1",
            arrows=[
                ArrowData("full", "lone_pair", "N⁻",
                          "atom", "δ-C-Cl", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-Cl",
                          "atom", "Cl⁻", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N⁻": "친핵체", "C-Cl": "이탈기"},
            is_transition_state=True,
            energy_label="TS: 고리화",
            reagents="NaOH",
        ),
        MechanismStep(
            step_number=6,
            title="생성물: 피롤리딘",
            description=(
                "N-메틸피롤리딘 (또는 치환 피롤리딘) 생성.\n"
                "부산물: NaCl, H₂O.\n"
                "응용: 알칼로이드 합성 (니코틴 등).\n"
                "Hofmann (1883), Löffler-Freytag (1909)."
            ),
            reactant_smiles="CN1CCC(C)C1",
            product_smiles="CN1CCC(C)C1",
            arrows=[],
            labels={"피롤리딘": "생성물"},
            energy_label="생성물",
            notes="Hofmann, 1883; Löffler & Freytag, 1909",
        ),
    ],
    energy_diagram=[
        ("N-클로로아민", 0.0),
        ("N· + Cl·", 35.0),
        ("1,5-HAT TS", 28.0),
        ("δ-C·", 15.0),
        ("δ-클로로아민", -5.0),
        ("고리화 TS", 18.0),
        ("피롤리딘", -20.0),
    ],
)

# ─── Sommelet-Hauser Rearrangement ─────────────────────────────────────
# 대표 반응: benzyl-NR₃⁺ + NaNH₂ → ortho-alkylated product
# Sommelet, M. C.R. Hebd. Seances Acad. Sci. 1937, 205, 56; Hauser, C.R. JACS 1951, 73, 1437.

MECHANISMS["sommelet_hauser"] = MechanismData(
    mechanism_type="sommelet_hauser",
    title="Sommelet-Hauser 전위 (벤질암모늄 → 오르토 알킬화)",
    total_steps=5,
    overall_description=(
        "Sommelet-Hauser 전위: 벤질 4급 암모늄 염에 NaNH₂(강한 염기)를 작용시키면 "
        "벤질 위치 탈양성자화 → [2,3]-시그마트로픽 전위 → 오르토 치환 제품.\n"
        "Stevens 전위와 경쟁하나 열역학적 지배(더 안정한 생성물)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="벤질 위치 탈양성자화",
            description=(
                "NaNH₂가 벤질 C-H를 제거.\n"
                "NH₂⁻ (pKa ≈ 38) → 벤질 카르바니온 형성.\n"
                "카르바니온은 방향족 고리와 공명 안정화."
            ),
            reactant_smiles="C[N+](C)(C)Cc1ccccc1",
            product_smiles="C[N+](C)(C)[CH-]c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "NH₂⁻",
                          "atom", "벤질 C-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"벤질 C": "탈양성자화"},
            energy_label="탈양성자화",
            reagents="NaNH₂ / NH₃(l)",
        ),
        MechanismStep(
            step_number=2,
            title="[2,3]-시그마트로픽 전위 (전이상태)",
            description=(
                "벤질 카르바니온 → [2,3]-시그마트로픽 전위.\n"
                "5원환 봉투형 전이상태.\n"
                "C-N 결합 절단 + C-C(ortho) 결합 형성 동시진행.\n"
                "Woodward-Hoffmann: 초면 허용 [σ2s+π2s]."
            ),
            reactant_smiles="C[N+](C)(C)[CH-]c1ccccc1",
            product_smiles="CN(C)C=C1C=CC=CC1=C",
            arrows=[
                ArrowData("full", "negative_charge", "카르바니온",
                          "atom", "ortho-C", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"ortho-C": "[2,3]-시그마트로픽"},
            is_transition_state=True,
            energy_label="TS: [2,3]-시그마트로픽",
        ),
        MechanismStep(
            step_number=3,
            title="탈방향족화 중간체 (사이클로헥사디엔이민)",
            description=(
                "방향족성이 일시 상실된 중간체.\n"
                "ortho-C에 새로운 C-C 결합, N은 3차 아민으로 환원.\n"
                "사이클로헥사디엔이민 타입 구조."
            ),
            reactant_smiles="CN(C)C=C1C=CC=CC1=C",
            product_smiles="CN(C)C=C1C=CC=CC1=C",
            arrows=[],
            labels={"중간체": "탈방향족화"},
            energy_label="탈방향족화 중간체",
        ),
        MechanismStep(
            step_number=4,
            title="[1,3]-양성자 이동 → 재방향족화",
            description=(
                "[1,3]-프로토트로피(양성자 이동).\n"
                "방향족성 복원 (사이클로헥사디엔 → 벤젠).\n"
                "열역학적으로 크게 유리 (ΔG ≈ -36 kcal/mol)."
            ),
            reactant_smiles="CN(C)C=C1C=CC=CC1=C",
            product_smiles="CN(C)Cc1ccccc1C",
            arrows=[
                ArrowData("full", "bond", "C-H",
                          "atom", "탈방향족 C", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"재방향족화": "[1,3]-H shift"},
            energy_label="재방향족화",
        ),
        MechanismStep(
            step_number=5,
            title="생성물: ortho-알킬화 벤질아민",
            description=(
                "o-(디메틸아미노메틸)톨루엔.\n"
                "Stevens 전위 산물과 다른 위치이성체.\n"
                "열역학 지배: Sommelet-Hauser가 선호 (방향족화 구동력).\n"
                "Sommelet (1937), Hauser (1951)."
            ),
            reactant_smiles="CN(C)Cc1ccccc1C",
            product_smiles="CN(C)Cc1ccccc1C",
            arrows=[],
            labels={"ortho-알킬화": "생성물"},
            energy_label="생성물",
            notes="Sommelet (1937), Hauser (1951)",
        ),
    ],
    energy_diagram=[
        ("벤질암모늄 + NaNH₂", 0.0),
        ("카르바니온", 12.0),
        ("[2,3]-시그마트로픽 TS", 25.0),
        ("탈방향족화 중간체", 8.0),
        ("재방향족화", 2.0),
        ("ortho-알킬화 생성물", -18.0),
    ],
)

# ─── Stevens Rearrangement ─────────────────────────────────────────────
# 대표 반응: R₃N⁺-CH₂R' + base → [1,2]-shift → R₂N-CHR'R
# Stevens, T.S. et al. J. Chem. Soc. 1928, 3193.

MECHANISMS["stevens_rearrangement"] = MechanismData(
    mechanism_type="stevens_rearrangement",
    title="Stevens 전위 (4급 암모늄 → [1,2]-이동)",
    total_steps=4,
    overall_description=(
        "Stevens 전위: 4급 암모늄(또는 술포늄)의 α-탈양성자화 후 "
        "[1,2]-알킬/벤질/알릴 이동 → 3급 아민 생성.\n"
        "Sommelet-Hauser와 경쟁: Stevens = 동역학 지배, S-H = 열역학 지배."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="α-탈양성자화 → 질소 일리드",
            description=(
                "강한 염기(NaNH₂, NaH, KOtBu)가 N⁺ 인접 α-H를 제거.\n"
                "질소 일리드(ammonium ylide) 형성: R₃N⁺-CR'⁻.\n"
                "4급 N의 양전하가 α-C의 산성도를 높임."
            ),
            reactant_smiles="C[N+](C)(CC)Cc1ccccc1",
            product_smiles="C[N+](C)([CH-]C)Cc1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "Base",
                          "atom", "α-C-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"α-C": "탈양성자화 위치"},
            energy_label="일리드 형성",
            reagents="NaNH₂",
        ),
        MechanismStep(
            step_number=2,
            title="[1,2]-이동 (전이상태)",
            description=(
                "벤질기(또는 알릴/알킬)가 N에서 α-C로 [1,2]-이동.\n"
                "C-N 결합 절단 + C-C 결합 형성 동시진행.\n"
                "3원환 TS (또는 라디칼 쌍 경로 — 논란).\n"
                "Woodward-Hoffmann: [1,2]-초면 이동 → 금지 (열적).\n"
                "실제로는 라디칼 쌍 메커니즘으로 진행 가능."
            ),
            reactant_smiles="C[N+](C)([CH-]C)Cc1ccccc1",
            product_smiles="CN(C)C(Cc1ccccc1)C",
            arrows=[
                ArrowData("full", "bond", "N-CH₂Ar",
                          "atom", "α-C⁻", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"benzyl": "[1,2]-이동기"},
            is_transition_state=True,
            energy_label="TS: [1,2]-shift",
            notes="라디칼 쌍 vs. 협동적 — 논쟁적",
        ),
        MechanismStep(
            step_number=3,
            title="3차 아민 생성",
            description=(
                "N의 양전하 소멸 → 중성 3차 아민.\n"
                "α-C에 벤질기 결합된 분기점.\n"
                "동역학 지배 생성물 (Sommelet-Hauser보다 빠름)."
            ),
            reactant_smiles="CN(C)C(Cc1ccccc1)C",
            product_smiles="CN(C)C(Cc1ccccc1)C",
            arrows=[],
            labels={"3차 아민": "생성물"},
            energy_label="생성물",
        ),
        MechanismStep(
            step_number=4,
            title="최종 생성물",
            description=(
                "3차 아민 (R₂N-CHR'-R'').\n"
                "Stevens 전위 vs Sommelet-Hauser:\n"
                "  - Stevens: 저온, 짧은 반응시간 → 동역학 지배.\n"
                "  - S-H: 고온, 긴 반응시간 → 열역학 지배.\n"
                "Stevens, T.S. et al. J. Chem. Soc. 1928, 3193."
            ),
            reactant_smiles="CN(C)C(Cc1ccccc1)C",
            product_smiles="CN(C)C(Cc1ccccc1)C",
            arrows=[],
            labels={"Stevens": "1928"},
            energy_label="생성물",
            notes="Stevens, 1928",
        ),
    ],
    energy_diagram=[
        ("4급 암모늄", 0.0),
        ("질소 일리드", 15.0),
        ("[1,2]-shift TS", 30.0),
        ("3차 아민", -10.0),
    ],
)


# ─── Barton Reaction (Photolytic Nitrite) ─────────────────────────────────
# Barton, D.H.R. J. Am. Chem. Soc. 1960, 82, 2640.
# δ-Nitroso alcohol synthesis via alkoxy radical → 1,5-HAT

MECHANISMS["barton_reaction"] = MechanismData(
    mechanism_type="barton_reaction",
    title="Barton 반응 (광분해 니트라이트 → δ-니트로소 알코올)",
    total_steps=5,
    overall_description=(
        "Barton 반응: 알킬 니트라이트(RONO)의 광분해로 알콕시 라디칼 생성 후,\n"
        "1,5-수소 원자 이동(HAT)을 통해 δ-탄소 라디칼 형성.\n"
        "NO 포획 → δ-니트로소 알코올 → 옥심 호변이성.\n"
        "스테로이드 합성에서 원격 C-H 관능기화에 광범위 활용 (Barton, 1960)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="광분해: O-NO 결합 균열",
            description=(
                "자외선(hν) 조사로 알킬 니트라이트의 O-N 결합 균등분해.\n"
                "알콕시 라디칼(RO·) + 일산화질소(NO·) 생성.\n"
                "BDE(O-NO) ≈ 155 kJ/mol — UV 에너지로 쉽게 절단."
            ),
            reactant_smiles="CCCCCON=O",
            product_smiles="CCCCC[O]",
            arrows=[
                ArrowData("half", "bond", "O-N",
                          "atom", "O·", "#ff6600", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O-N": "균등분해"},
            energy_label="hν 활성화",
            reagents="hν (UV)",
        ),
        MechanismStep(
            step_number=2,
            title="1,5-수소 원자 이동 (HAT)",
            description=(
                "알콕시 라디칼이 6원환 전이상태를 통해 δ-C-H 수소 추출.\n"
                "1,5-HAT는 의자형 6원환 TS로 기하학적으로 유리.\n"
                "Barton 규칙: 1,5-HAT > 1,4-HAT >> 1,6-HAT (열역학적 선택)."
            ),
            reactant_smiles="CCCCC[O]",
            product_smiles="[CH2]CCCC[OH]",
            arrows=[
                ArrowData("half", "atom", "O·",
                          "atom", "δ-C-H", "#ff6600", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"δ-C": "HAT 위치"},
            is_transition_state=True,
            energy_label="TS: 6원환 의자형",
        ),
        MechanismStep(
            step_number=3,
            title="δ-탄소 라디칼 중간체",
            description=(
                "δ-탄소에 라디칼 형성, O-H 결합 형성 → δ-히드록시 라디칼.\n"
                "탄소 라디칼 안정성: 3° > 2° > 1°.\n"
                "라디칼 위치가 δ(5번) 탄소인 이유: 6원환 TS 선호."
            ),
            reactant_smiles="[CH2]CCCC[OH]",
            product_smiles="[CH2]CCCCO",
            arrows=[],
            labels={"δ-C·": "탄소 라디칼"},
            energy_label="δ-C 라디칼 중간체",
        ),
        MechanismStep(
            step_number=4,
            title="NO· 포획 → δ-니트로소 알코올",
            description=(
                "유리 NO· 라디칼이 δ-탄소 라디칼과 결합.\n"
                "C-NO 결합 형성 → δ-니트로소 알코올 생성.\n"
                "라디칼-라디칼 결합 (발열)."
            ),
            reactant_smiles="[CH2]CCCCO",
            product_smiles="ONC(=O)CCCCO",
            arrows=[
                ArrowData("half", "atom", "C·",
                          "atom", "N(NO·)", "#ff6600", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"C-NO": "라디칼 결합"},
            energy_label="NO 포획",
            reagents="NO·",
        ),
        MechanismStep(
            step_number=5,
            title="δ-니트로소 알코올 → 옥심 호변이성",
            description=(
                "니트로소 화합물이 옥심으로 호변이성화.\n"
                "R-CH=N-OH (옥심) ↔ R-CH₂-NO (니트로소).\n"
                "옥심 형태가 열역학적으로 안정.\n"
                "최종 생성물: δ-옥시모 알코올 — Beckmann 전위로 lactam 합성 가능."
            ),
            reactant_smiles="ONC(=O)CCCCO",
            product_smiles="OCC(/C=N/O)CCC",
            arrows=[],
            labels={"oxime": "호변이성체"},
            energy_label="옥심 생성물",
            notes="Barton, 1960 — 스테로이드 C-18/C-19 관능기화",
        ),
    ],
    energy_diagram=[
        ("알킬 니트라이트", 0.0),
        ("알콕시 라디칼 + NO·", 25.0),
        ("1,5-HAT TS", 35.0),
        ("δ-탄소 라디칼", 15.0),
        ("δ-니트로소 알코올", -5.0),
        ("옥심", -12.0),
    ],
)

# ─── Eschenmoser-Claisen Rearrangement ────────────────────────────────────
# Wick, A.E.; Felix, D.; Steen, K.; Eschenmoser, A. Helv. Chim. Acta 1964, 47, 2425.
# Allyl alcohol + N,N-dimethylacetamide dimethyl acetal → γ,δ-unsaturated amide

MECHANISMS["eschenmoser_claisen"] = MechanismData(
    mechanism_type="eschenmoser_claisen",
    title="Eschenmoser-Claisen 전위 (알릴 알코올 → γ,δ-불포화 아미드)",
    total_steps=5,
    overall_description=(
        "Eschenmoser-Claisen 전위: 알릴 알코올과 N,N-디메틸아세트아미드 디메틸 아세탈의\n"
        "교환 → 알릴 비닐 에테르(케텐 아미날) → [3,3]-시그마트로픽 전위.\n"
        "생성물: γ,δ-불포화 N,N-디메틸아미드.\n"
        "Eschenmoser (1964). Claisen 변형 중 가장 온화한 조건."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아세탈 교환: 알릴 알코올 → 케텐 N,O-아세탈",
            description=(
                "알릴 알코올의 OH가 DMA 디메틸 아세탈의 OMe를 교환.\n"
                "MeOH 이탈 → 케텐 N,O-아세탈 형성.\n"
                "반응 조건: 가열 (xylene, 140°C) 또는 실온 (CH₂Cl₂, 촉매)."
            ),
            reactant_smiles="C=CCO",
            product_smiles="C=CCOC(=C)N(C)C",
            arrows=[
                ArrowData("full", "lone_pair", "O(allyl)",
                          "atom", "C(acetal)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O": "친핵 공격"},
            energy_label="아세탈 교환",
            reagents="MeC(OMe)₂NMe₂",
        ),
        MechanismStep(
            step_number=2,
            title="케텐 N,O-아세탈 중간체",
            description=(
                "알릴 비닐 에테르 동등체 (케텐 아미날).\n"
                "C=C-O-C-C=C 프레임워크가 [3,3]-전위 기질.\n"
                "NMe₂ 기가 전자 공여로 케텐 아미날 안정화."
            ),
            reactant_smiles="C=CCOC(=C)N(C)C",
            product_smiles="C=CCOC(=C)N(C)C",
            arrows=[],
            labels={"ketene aminal": "[3,3] 기질"},
            energy_label="케텐 아미날 중간체",
        ),
        MechanismStep(
            step_number=3,
            title="[3,3]-시그마트로픽 전위 (전이상태)",
            description=(
                "의자형 6원환 전이상태를 통한 협동적 결합 재편.\n"
                "C-O 결합 절단 + C-C 결합 형성 동시진행.\n"
                "의자형 TS → E-올레핀 선택성 (Eschenmoser 선택성).\n"
                "Woodward-Hoffmann: [3,3]-초면 전위 = 열적 허용."
            ),
            reactant_smiles="C=CCOC(=C)N(C)C",
            product_smiles="O=C(CC=C)N(C)C",
            arrows=[
                ArrowData("full", "bond", "C-O",
                          "bond", "C-C(new)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TS": "[3,3]-sigmatropic"},
            is_transition_state=True,
            energy_label="TS: 의자형 [3,3]",
        ),
        MechanismStep(
            step_number=4,
            title="이미늄 이온 가수분해",
            description=(
                "[3,3]-전위 직후 생성되는 이미늄/에놀레이트.\n"
                "작업후처리에서 가수분해 → 아미드.\n"
                "또는 직접 아미드 토토머 형성."
            ),
            reactant_smiles="O=C(CC=C)N(C)C",
            product_smiles="O=C(CC=C)N(C)C",
            arrows=[],
            labels={"amide": "생성물"},
            energy_label="아미드 형성",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: γ,δ-불포화 아미드",
            description=(
                "γ,δ-불포화 N,N-디메틸아미드 생성.\n"
                "높은 E-선택성 (의자형 TS 유래).\n"
                "합성 활용: 아미드 → 산/알데히드 변환 후 추가 반응.\n"
                "Eschenmoser (1964), Wick, A.E. et al."
            ),
            reactant_smiles="O=C(CC=C)N(C)C",
            product_smiles="O=C(CC=C)N(C)C",
            arrows=[],
            labels={"product": "γ,δ-불포화 아미드"},
            energy_label="생성물",
            notes="Eschenmoser, 1964",
        ),
    ],
    energy_diagram=[
        ("알릴 알코올 + 아세탈", 0.0),
        ("케텐 N,O-아세탈", 5.0),
        ("[3,3]-TS", 28.0),
        ("이미늄/에놀레이트", -8.0),
        ("γ,δ-불포화 아미드", -15.0),
    ],
)

# ─── Ireland-Claisen Rearrangement ────────────────────────────────────────
# Ireland, R.E.; Mueller, R.H. J. Am. Chem. Soc. 1972, 94, 5897.
# Ester enolate [3,3]-sigmatropic → carboxylic acid

MECHANISMS["ireland_claisen"] = MechanismData(
    mechanism_type="ireland_claisen",
    title="Ireland-Claisen 전위 (에스터 에놀레이트 → 카르복시산)",
    total_steps=5,
    overall_description=(
        "Ireland-Claisen 전위: 에스터를 LDA로 탈양성자화 → 에놀레이트.\n"
        "TMSCl 포획 → 실릴 케텐 아세탈.\n"
        "[3,3]-시그마트로픽 전위 → 카르복시산.\n"
        "E/Z-에놀레이트 기하이성질체가 syn/anti 선택성 결정.\n"
        "Ireland (1972). 온화한 조건(-78°C)에서 높은 입체선택성."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에스터 α-탈양성자화 (LDA)",
            description=(
                "LDA(리튬 디이소프로필아미드)가 에스터 α-수소 제거.\n"
                "에놀레이트 형성: -78°C에서 동역학 조건.\n"
                "E/Z 선택성: 용매 효과 (THF → Z, THF/HMPA → E)."
            ),
            reactant_smiles="C=CCOC(=O)CC",
            product_smiles="C=CCOC(=O)[CH-]C",
            arrows=[
                ArrowData("full", "lone_pair", "N(LDA)",
                          "atom", "α-C-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"α-C": "탈양성자화"},
            energy_label="에놀레이트 형성",
            reagents="LDA, THF, -78°C",
        ),
        MechanismStep(
            step_number=2,
            title="TMSCl 포획 → 실릴 케텐 아세탈",
            description=(
                "에놀레이트 산소가 TMSCl과 반응 → O-실릴화.\n"
                "실릴 케텐 아세탈 형성: 안정한 [3,3]-전위 기질.\n"
                "TMS 보호가 에놀레이트 E/Z 기하를 고정."
            ),
            reactant_smiles="C=CCOC(=O)[CH-]C",
            product_smiles="C=CCOC(=C(C)O[Si](C)(C)C)C",
            arrows=[
                ArrowData("full", "lone_pair", "O⁻",
                          "atom", "Si(TMSCl)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O-Si": "실릴화"},
            energy_label="실릴 케텐 아세탈",
            reagents="TMSCl",
        ),
        MechanismStep(
            step_number=3,
            title="[3,3]-시그마트로픽 전위 (전이상태)",
            description=(
                "의자형 6원환 TS를 통한 협동적 [3,3]-전위.\n"
                "C-O(알릴) 결합 절단 + C-C 결합 형성.\n"
                "Z-에놀레이트 → syn 생성물, E-에놀레이트 → anti 생성물.\n"
                "Woodward-Hoffmann: [3,3] 초면 = 열적 허용."
            ),
            reactant_smiles="C=CCOC(=C(C)O[Si](C)(C)C)C",
            product_smiles="O=C(O)C(C)CC=C",
            arrows=[
                ArrowData("full", "bond", "C-O(allyl)",
                          "bond", "C-C(new)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TS": "[3,3]-sigmatropic"},
            is_transition_state=True,
            energy_label="TS: 의자형 [3,3]",
        ),
        MechanismStep(
            step_number=4,
            title="TMS 제거 + 산 처리",
            description=(
                "작업후처리: 수성 산 처리로 TMS 제거.\n"
                "실릴 에스터/에놀 → 유리 카르복시산.\n"
                "또는 TBAF/HF로 실릴기 제거."
            ),
            reactant_smiles="O=C(O)C(C)CC=C",
            product_smiles="O=C(O)C(C)CC=C",
            arrows=[],
            labels={"COOH": "카르복시산"},
            energy_label="TMS 제거",
            reagents="H₃O⁺",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: γ,δ-불포화 카르복시산",
            description=(
                "γ,δ-불포화 카르복시산 생성.\n"
                "syn/anti 비율: E/Z-에놀레이트에 의해 제어.\n"
                "Ireland-Claisen은 Claisen 변형 중 가장 높은 입체선택성.\n"
                "Ireland, R.E.; Mueller, R.H. JACS 1972, 94, 5897."
            ),
            reactant_smiles="O=C(O)C(C)CC=C",
            product_smiles="O=C(O)C(C)CC=C",
            arrows=[],
            labels={"product": "γ,δ-불포화 산"},
            energy_label="생성물",
            notes="Ireland, 1972",
        ),
    ],
    energy_diagram=[
        ("알릴 에스터", 0.0),
        ("에놀레이트", 8.0),
        ("실릴 케텐 아세탈", 3.0),
        ("[3,3]-TS", 25.0),
        ("카르복시산", -18.0),
    ],
)

# ─── Overman Rearrangement ────────────────────────────────────────────────
# Overman, L.E. J. Am. Chem. Soc. 1974, 96, 597.
# [3,3]-Sigmatropic rearrangement of allylic trichloroacetimidates → allylic amines

MECHANISMS["overman_rearrangement"] = MechanismData(
    mechanism_type="overman_rearrangement",
    title="Overman 전위 (알릴 트리클로로아세트이미데이트 → 알릴 아민)",
    total_steps=5,
    overall_description=(
        "Overman 전위: 알릴 트리클로로아세트이미데이트의 [3,3]-시그마트로픽 전위.\n"
        "C-O 결합 → C-N 결합 변환 (aza-Claisen 유사).\n"
        "열적 또는 Pd(II)/Hg(II) 촉매 조건.\n"
        "키랄 Pd(II) 촉매 → 비대칭 Overman 가능.\n"
        "Overman (1974). 알릴 아민 합성의 핵심 전략."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이미데이트 형성: 알릴 알코올 + CCl₃CN",
            description=(
                "알릴 알코올이 트리클로로아세토니트릴과 반응.\n"
                "NaH 또는 DBU 촉매 → O-알킬 트리클로로아세트이미데이트.\n"
                "O-C=NH(CCl₃) 결합 형성."
            ),
            reactant_smiles="C=CCO",
            product_smiles="C=CCOC(=N)C(Cl)(Cl)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "O(allyl)",
                          "atom", "C≡N", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O": "친핵 첨가"},
            energy_label="이미데이트 형성",
            reagents="Cl₃CCN, NaH",
        ),
        MechanismStep(
            step_number=2,
            title="알릴 트리클로로아세트이미데이트",
            description=(
                "[3,3]-전위 기질: O-C-C=C 프레임워크.\n"
                "열적 조건: xylene, 140°C, 수시간.\n"
                "또는 촉매: PdCl₂(MeCN)₂ (실온, 수분)."
            ),
            reactant_smiles="C=CCOC(=N)C(Cl)(Cl)Cl",
            product_smiles="C=CCOC(=N)C(Cl)(Cl)Cl",
            arrows=[],
            labels={"imidate": "[3,3] 기질"},
            energy_label="이미데이트 중간체",
        ),
        MechanismStep(
            step_number=3,
            title="[3,3]-시그마트로픽 전위 (전이상태)",
            description=(
                "의자형 6원환 TS를 통한 협동적 전위.\n"
                "C-O 결합 절단 + C-N 결합 형성.\n"
                "1,3-chirality transfer: 기질의 입체화학이 생성물로 전달.\n"
                "Suprafacial/suprafacial: Woodward-Hoffmann 허용."
            ),
            reactant_smiles="C=CCOC(=N)C(Cl)(Cl)Cl",
            product_smiles="C=CCNC(=O)C(Cl)(Cl)Cl",
            arrows=[
                ArrowData("full", "bond", "O-C(allyl)",
                          "bond", "N-C(new)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TS": "aza-[3,3]"},
            is_transition_state=True,
            energy_label="TS: [3,3]-전위",
        ),
        MechanismStep(
            step_number=4,
            title="트리클로로아세트아미드 중간체",
            description=(
                "알릴 아민에 트리클로로아세틸 보호기.\n"
                "NHC(=O)CCl₃ → 가수분해로 유리 아민 생성 가능."
            ),
            reactant_smiles="C=CCNC(=O)C(Cl)(Cl)Cl",
            product_smiles="C=CCNC(=O)C(Cl)(Cl)Cl",
            arrows=[],
            labels={"amide": "보호된 아민"},
            energy_label="아미드 중간체",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: 알릴 아민",
            description=(
                "염기성 가수분해(NaOH/MeOH)로 CCl₃C(=O) 제거 → 유리 알릴 아민.\n"
                "또는 K₂CO₃/MeOH 온화 조건.\n"
                "높은 1,3-chirality transfer → 비대칭 합성 활용.\n"
                "Overman, L.E. JACS 1974, 96, 597."
            ),
            reactant_smiles="C=CCNC(=O)C(Cl)(Cl)Cl",
            product_smiles="C=CCN",
            arrows=[],
            labels={"allylamine": "최종 생성물"},
            energy_label="생성물",
            notes="Overman, 1974",
        ),
    ],
    energy_diagram=[
        ("알릴 알코올 + CCl₃CN", 0.0),
        ("이미데이트", -3.0),
        ("[3,3]-TS", 30.0),
        ("아미드 중간체", -10.0),
        ("알릴 아민", -15.0),
    ],
)

# ─── Rupe Rearrangement ──────────────────────────────────────────────────
# Rupe, H.; Kambli, E. Helv. Chim. Acta 1926, 9, 672.
# Propargylic alcohol → α,β-unsaturated ketone (acid-catalyzed)

MECHANISMS["rupe_rearrangement"] = MechanismData(
    mechanism_type="rupe_rearrangement",
    title="Rupe 전위 (프로파길 알코올 → α,β-불포화 케톤)",
    total_steps=5,
    overall_description=(
        "Rupe 전위: 3차 프로파길 알코올의 산촉매 탈수/전위.\n"
        "프로파길 양이온 → 알레닐 양이온 → 1,2-이동 → α,β-불포화 케톤.\n"
        "Meyer-Schuster와 경쟁: Meyer-Schuster = 1,3-OH 이동 (α,β-불포화 카르보닐).\n"
        "Rupe = 탈수 + 1,2-이동 (공액 에논).\n"
        "Rupe, 1926. 3차 프로파길 알코올에 선호."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="프로파길 알코올 양성자화",
            description=(
                "산 촉매(H₂SO₄, p-TsOH, BF₃·Et₂O)가 OH를 양성자화.\n"
                "이탈기 형성: -OH₂⁺."
            ),
            reactant_smiles="CC(O)(C#C)C",
            product_smiles="CC([OH2+])(C#C)C",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "O", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O": "양성자화"},
            energy_label="양성자화",
            reagents="H⁺ (산촉매)",
        ),
        MechanismStep(
            step_number=2,
            title="탈수 → 프로파길 양이온",
            description=(
                "H₂O 이탈 → 3차 프로파길(프로파르길) 양이온.\n"
                "3차 탄소양이온 안정성 → 용이한 탈수.\n"
                "프로파길 양이온 ↔ 알레닐 양이온 공명."
            ),
            reactant_smiles="CC([OH2+])(C#C)C",
            product_smiles="CC([C+]=C)C",
            arrows=[
                ArrowData("full", "bond", "C-OH₂",
                          "atom", "O(H₂O)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"C⁺": "카르보양이온"},
            energy_label="탈수",
        ),
        MechanismStep(
            step_number=3,
            title="알레닐 양이온 → 1,2-메틸 이동",
            description=(
                "프로파길/알레닐 양이온에서 1,2-알킬(메틸) 이동.\n"
                "비닐 양이온 중간체 형성.\n"
                "Rupe 특징: Meyer-Schuster와 달리 1,2-이동 경로."
            ),
            reactant_smiles="CC([C+]=C)C",
            product_smiles="CC(C)=C[CH2+]",
            arrows=[
                ArrowData("full", "bond", "C-CH₃",
                          "atom", "C⁺", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"CH₃": "1,2-이동"},
            is_transition_state=True,
            energy_label="TS: 1,2-shift",
        ),
        MechanismStep(
            step_number=4,
            title="비닐 양이온 포획 (H₂O)",
            description=(
                "비닐 양이온이 H₂O에 의해 포획.\n"
                "에놀 형성 → 케토-에놀 호변이성.\n"
                "α,β-불포화 케톤 (공액 에논) 생성."
            ),
            reactant_smiles="CC(C)=C[CH2+]",
            product_smiles="CC(=CC=O)C",
            arrows=[
                ArrowData("full", "lone_pair", "O(H₂O)",
                          "atom", "C⁺(vinyl)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"enol": "포획"},
            energy_label="에놀 형성",
            reagents="H₂O",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: α,β-불포화 케톤",
            description=(
                "α,β-불포화 케톤 (메틸비닐케톤 유도체).\n"
                "Rupe vs Meyer-Schuster: 3° 알코올 → Rupe 선호.\n"
                "2° 알코올 → Meyer-Schuster 선호.\n"
                "Rupe, H.; Kambli, E. Helv. Chim. Acta 1926, 9, 672."
            ),
            reactant_smiles="CC(=CC=O)C",
            product_smiles="CC(=CC=O)C",
            arrows=[],
            labels={"enone": "최종 생성물"},
            energy_label="생성물",
            notes="Rupe, 1926",
        ),
    ],
    energy_diagram=[
        ("프로파길 알코올", 0.0),
        ("양성자화", 5.0),
        ("프로파길 양이온", 20.0),
        ("1,2-shift TS", 32.0),
        ("에놀", 8.0),
        ("α,β-불포화 케톤", -10.0),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Cycle 16: Aza-Cope/Mannich, Carroll, Meyer-Schuster, Meinwald, VCP (2026-03-22)
# ═══════════════════════════════════════════════════════════════════════════════

MECHANISMS["aza_cope_mannich"] = MechanismData(
    mechanism_type="aza_cope_mannich",
    title="2-Aza-Cope/Mannich 반응 (이미늄 → [3,3] → Mannich 고리화)",
    total_steps=5,
    overall_description=(
        "2-Aza-Cope/Mannich 반응: 이미늄 이온의 [3,3]-시그마트로피 전위 후\n"
        "Mannich 고리화로 피페리딘/피롤리딘 골격 형성.\n"
        "Overman 등이 개발, 천연물 전합성에 광범위 활용.\n"
        "열역학적 구동력: C=N → C=C 이성화 + 분자내 Mannich 반응 (비가역).\n"
        "Overman, L. E. J. Am. Chem. Soc. 1992, 114, 5898."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이미늄 이온 형성",
            description=(
                "아민과 알데히드/케톤의 축합.\n"
                "탈수 → 이미늄 이온 (C=N⁺) 형성.\n"
                "산 촉매 하 가속."
            ),
            reactant_smiles="C=CCC(N)CC=O",
            product_smiles="C=CCC(/[NH2+])=C\\C",
            arrows=[
                ArrowData("full", "lone_pair", "N",
                          "atom", "C(=O)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N": "축합"},
            energy_label="이미늄 형성",
            reagents="H⁺ (산촉매)",
        ),
        MechanismStep(
            step_number=2,
            title="2-Aza-Cope [3,3]-시그마트로피 전위",
            description=(
                "이미늄 이온의 [3,3]-시그마트로피 전위.\n"
                "C-C 결합 절단 + C-C 결합 형성 (협주적).\n"
                "의자형 전이상태, C=N⁺ → C=C 이성화."
            ),
            reactant_smiles="C=CCC(/[NH2+])=C\\C",
            product_smiles="C(/C=C)=C\\CC[NH3+]",
            arrows=[
                ArrowData("full", "bond", "C-C(breaking)",
                          "atom", "C(forming)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"[3,3]": "시그마트로피"},
            is_transition_state=True,
            energy_label="[3,3]-TS",
        ),
        MechanismStep(
            step_number=3,
            title="에날아민/이미늄 호변이성",
            description=(
                "[3,3] 전위 생성물: 불포화 아민.\n"
                "산 촉매 하 이미늄 이온 재형성.\n"
                "분자 내 Mannich 반응 전단계."
            ),
            reactant_smiles="C(/C=C)=C\\CC[NH3+]",
            product_smiles="O=CCC(CC=C)[NH3+]",
            arrows=[
                ArrowData("full", "atom", "H",
                          "atom", "N", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"taut": "호변이성"},
            energy_label="호변이성",
        ),
        MechanismStep(
            step_number=4,
            title="분자 내 Mannich 고리화",
            description=(
                "에놀이 분자 내 이미늄 탄소를 공격.\n"
                "5-exo-trig 또는 6-exo-trig 고리화.\n"
                "비가역적: 열역학적 구동력 (C-C 결합 형성)."
            ),
            reactant_smiles="O=CCC(CC=C)[NH3+]",
            product_smiles="OC1CCNCC1",
            arrows=[
                ArrowData("full", "atom", "C(enol)",
                          "atom", "C=N⁺", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"Mannich": "고리화"},
            energy_label="Mannich 고리화",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: 피페리디놀",
            description=(
                "β-히드록시 피페리딘 (피페리디놀) 생성.\n"
                "단일 포트 반응으로 2개 C-C 결합 + 1개 C-N 결합 형성.\n"
                "Overman, 1992. 천연물 전합성 핵심 전략."
            ),
            reactant_smiles="OC1CCNCC1",
            product_smiles="OC1CCNCC1",
            arrows=[],
            labels={"product": "피페리디놀"},
            energy_label="생성물",
            notes="Overman, 1992",
        ),
    ],
    energy_diagram=[
        ("이미늄 이온", 0.0),
        ("[3,3]-TS", 28.0),
        ("불포화 아민", 5.0),
        ("이미늄 재형성", 10.0),
        ("Mannich TS", 22.0),
        ("피페리디놀", -15.0),
    ],
)

MECHANISMS["carroll_rearrangement"] = MechanismData(
    mechanism_type="carroll_rearrangement",
    title="Carroll 전위 (알릴 β-케토에스터 → γ,δ-불포화산)",
    total_steps=5,
    overall_description=(
        "Carroll 전위: 알릴 β-케토에스터의 [3,3]-시그마트로피 전위.\n"
        "에놀화 → allyl vinyl ether → [3,3] → β-케토산 → 탈카르복실화.\n"
        "최종 생성물: γ,δ-불포화 케톤.\n"
        "Carroll, M. F. J. Chem. Soc. 1940, 704.\n"
        "Claisen 전위의 에놀 변형. Saucy-Marbet 변형 포함."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에놀화 (β-케토에스터)",
            description=(
                "β-케토에스터의 α-H 제거.\n"
                "에놀레이트/에놀 형성.\n"
                "allyl vinyl ether 골격 구성 → [3,3] 가능."
            ),
            reactant_smiles="CC(=O)CC(=O)OCC=C",
            product_smiles="CC(O)=CC(=O)OCC=C",
            arrows=[
                ArrowData("full", "atom", "alpha-H",
                          "atom", "base", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"enol": "에놀화"},
            energy_label="에놀화",
            reagents="Base or heat",
        ),
        MechanismStep(
            step_number=2,
            title="[3,3]-시그마트로피 전위 (Carroll)",
            description=(
                "allyl vinyl ether 유닛의 [3,3] 전위.\n"
                "O-알릴 결합 절단 + C-C 결합 형성 (협주적).\n"
                "의자형 전이상태. Claisen 전위 변형."
            ),
            reactant_smiles="CC(O)=CC(=O)OCC=C",
            product_smiles="CC(=O)CC(CC=C)C(=O)O",
            arrows=[
                ArrowData("full", "bond", "O-allyl",
                          "atom", "C(vinyl)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"[3,3]": "시그마트로피"},
            is_transition_state=True,
            energy_label="[3,3]-TS",
        ),
        MechanismStep(
            step_number=3,
            title="β-케토산 중간체",
            description=(
                "[3,3] 전위 후 β-케토산 형성.\n"
                "불안정 1,3-디카르보닐산.\n"
                "탈카르복실화 전단계."
            ),
            reactant_smiles="CC(=O)CC(CC=C)C(=O)O",
            product_smiles="CC(=O)CC(CC=C)C(=O)O",
            arrows=[],
            labels={"beta-keto acid": "중간체"},
            energy_label="β-케토산",
        ),
        MechanismStep(
            step_number=4,
            title="탈카르복실화 (CO₂ 이탈)",
            description=(
                "β-케토산의 열적 탈카르복실화.\n"
                "6원 고리 전이상태 경유 → 에놀 + CO₂.\n"
                "비가역적: CO₂ 기체 이탈이 구동력."
            ),
            reactant_smiles="CC(=O)CC(CC=C)C(=O)O",
            product_smiles="CC(=O)/C=C\\CC=C",
            arrows=[
                ArrowData("full", "bond", "C-CO₂",
                          "atom", "C=O", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"CO₂": "탈카르복실화"},
            energy_label="탈카르복실화 TS",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: γ,δ-불포화 케톤",
            description=(
                "γ,δ-불포화 케톤 생성.\n"
                "에놀 → 케토 호변이성 (자발적).\n"
                "Carroll, 1940. 탈카르복실적 알릴화."
            ),
            reactant_smiles="CC(=O)CC(C)C=C",
            product_smiles="CC(=O)CC(C)C=C",
            arrows=[],
            labels={"ketone": "최종 생성물"},
            energy_label="생성물",
            notes="Carroll, 1940",
        ),
    ],
    energy_diagram=[
        ("β-케토에스터", 0.0),
        ("에놀", 5.0),
        ("[3,3]-TS", 30.0),
        ("β-케토산", 2.0),
        ("탈카르복실화 TS", 25.0),
        ("γ,δ-불포화 케톤", -12.0),
    ],
)

MECHANISMS["meyer_schuster"] = MechanismData(
    mechanism_type="meyer_schuster",
    title="Meyer-Schuster 전위 (프로파길 알코올 → α,β-불포화 카르보닐)",
    total_steps=5,
    overall_description=(
        "Meyer-Schuster 전위: 프로파길 알코올의 산촉매 1,3-이동.\n"
        "프로파길 알코올 → [1,3]-OH 이동 → 알레놀 → α,β-불포화 카르보닐.\n"
        "2차 프로파길 알코올에 선호 (3차 → Rupe 선호).\n"
        "Meyer, K.; Schuster, K. Ber. dtsch. chem. Ges. 1922, 55, 819.\n"
        "최근 Au/Ag 촉매 변형이 활발."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="프로파길 알코올 양성자화",
            description=(
                "산 촉매가 OH를 양성자화.\n"
                "H₂O 이탈기 형성.\n"
                "또는 Lewis 산(Au³⁺, Ag⁺)이 알카인 활성화."
            ),
            reactant_smiles="OC(C)C#CC",
            product_smiles="[OH2+]C(C)C#CC",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "O", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O": "양성자화"},
            energy_label="양성자화",
            reagents="H⁺ (산촉매) or Au(III)",
        ),
        MechanismStep(
            step_number=2,
            title="1,3-히드록실 이동 (프로파길 → 알레닐)",
            description=(
                "프로파길 위치에서 알레닐 위치로 OH 1,3-이동.\n"
                "[1,3]-시그마트로피 이동 또는 단계적 경로.\n"
                "알레놀 중간체 형성."
            ),
            reactant_smiles="[OH2+]C(C)C#CC",
            product_smiles="OC(C)=C=CC",
            arrows=[
                ArrowData("full", "atom", "O",
                          "atom", "C(terminal)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"[1,3]": "OH 이동"},
            is_transition_state=True,
            energy_label="[1,3]-이동 TS",
        ),
        MechanismStep(
            step_number=3,
            title="알레놀 중간체",
            description=(
                "알레놀 (=C=C(OH)-) 형성.\n"
                "불안정 중간체: 알렌 + 에놀 결합.\n"
                "호변이성화 → α,β-불포화 카르보닐."
            ),
            reactant_smiles="OC(C)=C=CC",
            product_smiles="OC(C)=C=CC",
            arrows=[],
            labels={"allenol": "알레놀"},
            energy_label="알레놀",
        ),
        MechanismStep(
            step_number=4,
            title="호변이성화 → α,β-불포화 알데히드/케톤",
            description=(
                "알레놀의 케토-에놀 호변이성.\n"
                "양성자 이동 → α,β-불포화 카르보닐 형성.\n"
                "열역학적으로 안정한 공액계."
            ),
            reactant_smiles="OC(C)=C=CC",
            product_smiles="CC(/C=O)=C\\C",
            arrows=[
                ArrowData("full", "atom", "O-H",
                          "atom", "C=C", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"taut": "호변이성"},
            energy_label="호변이성 TS",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: α,β-불포화 카르보닐",
            description=(
                "α,β-불포화 알데히드 또는 케톤 생성.\n"
                "Meyer-Schuster vs Rupe: 2° 알코올 → M-S 선호.\n"
                "3° 알코올 → Rupe 선호.\n"
                "Meyer & Schuster, 1922."
            ),
            reactant_smiles="CC(/C=O)=C\\C",
            product_smiles="CC(/C=O)=C\\C",
            arrows=[],
            labels={"enal": "최종 생성물"},
            energy_label="생성물",
            notes="Meyer & Schuster, 1922",
        ),
    ],
    energy_diagram=[
        ("프로파길 알코올", 0.0),
        ("양성자화", 5.0),
        ("[1,3]-이동 TS", 28.0),
        ("알레놀", 12.0),
        ("호변이성", 18.0),
        ("α,β-불포화 카르보닐", -8.0),
    ],
)

MECHANISMS["meinwald_rearrangement"] = MechanismData(
    mechanism_type="meinwald_rearrangement",
    title="Meinwald 전위 (에폭시드 → 카르보닐)",
    total_steps=4,
    overall_description=(
        "Meinwald 전위: 에폭시드의 산촉매 이성화.\n"
        "에폭시드 → Lewis/Bronsted 산 개환 → 1,2-이동 → 카르보닐.\n"
        "이동기 선택성: 전자풍부 C-H/C-R이 이동.\n"
        "Meinwald, J.; Sinz, S. S.; Lichtenberger, H. J. Am. Chem. Soc. 1963, 85, 582.\n"
        "향료화학, 테르펜 화학에서 중요."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에폭시드 양성자화/Lewis 산 배위",
            description=(
                "Bronsted 산(H⁺, H₂SO₄) 또는 Lewis 산(BF₃, ZnCl₂)이\n"
                "에폭시드 산소를 활성화.\n"
                "C-O 결합 약화 → 개환 준비."
            ),
            reactant_smiles="CC1OC1C",
            product_smiles="CC1[OH+]C1C",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "O(epox)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"O": "활성화"},
            energy_label="양성자화",
            reagents="H⁺ or BF₃·Et₂O",
        ),
        MechanismStep(
            step_number=2,
            title="에폭시드 개환 → 카르보양이온",
            description=(
                "더 치환된 C에서 C-O 결합 절단.\n"
                "카르보양이온 형성 (anti-Markovnikov 개환).\n"
                "3차 > 2차 > 1차 안정성 순."
            ),
            reactant_smiles="CC1[OH+]C1C",
            product_smiles="CC([CH+]C)O",
            arrows=[
                ArrowData("full", "bond", "C-O(epox)",
                          "atom", "O", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"C⁺": "카르보양이온"},
            energy_label="개환",
        ),
        MechanismStep(
            step_number=3,
            title="1,2-수소/알킬 이동 (semi-pinacol)",
            description=(
                "인접 C-H (또는 C-R) 결합의 1,2-이동.\n"
                "카르보양이온 → 옥소카르베늄/카르보닐.\n"
                "이동기 선택: anti-periplanar 배향의 H/R."
            ),
            reactant_smiles="CC([CH+]C)O",
            product_smiles="CC(C)C=O",
            arrows=[
                ArrowData("full", "bond", "C-H(migrating)",
                          "atom", "C⁺", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"1,2-H": "이동"},
            is_transition_state=True,
            energy_label="1,2-shift TS",
        ),
        MechanismStep(
            step_number=4,
            title="최종 생성물: 알데히드/케톤",
            description=(
                "에폭시드 → 카르보닐 이성화 완료.\n"
                "알데히드 (H 이동) 또는 케톤 (알킬 이동).\n"
                "Meinwald, 1963. 양성자 촉매 이성화."
            ),
            reactant_smiles="CC(C)C=O",
            product_smiles="CC(C)C=O",
            arrows=[],
            labels={"carbonyl": "최종 생성물"},
            energy_label="생성물",
            notes="Meinwald, 1963",
        ),
    ],
    energy_diagram=[
        ("에폭시드", 0.0),
        ("양성자화", 5.0),
        ("카르보양이온", 18.0),
        ("1,2-shift TS", 25.0),
        ("카르보닐", -15.0),
    ],
)

MECHANISMS["vinylcyclopropane_rearrangement"] = MechanismData(
    mechanism_type="vinylcyclopropane_rearrangement",
    title="비닐시클로프로판 전위 (VCP → 시클로펜텐)",
    total_steps=4,
    overall_description=(
        "비닐시클로프로판 전위: VCP의 열적 [1,3]-시그마트로피 전위.\n"
        "시클로프로판 고리 개환 + 비닐기와 결합 → 시클로펜텐.\n"
        "Neureiter, 1959; Vogel, 1960.\n"
        "협주적 + 비라디칼 경로 경쟁 (활성화 에너지 ~51 kcal/mol).\n"
        "전자끌개/주개기 치환으로 온도 조건 완화 가능."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="시클로프로판 C-C 결합 균열 개열",
            description=(
                "열적 조건(300-500 °C)에서 시클로프로판 C-C 결합 균열.\n"
                "비닐기에 인접한 C-C 결합이 선택적 개열.\n"
                "1,3-비라디칼 중간체 형성 (또는 협주적)."
            ),
            reactant_smiles="C=CC1CC1",
            product_smiles="[CH2]CC=C[CH2]",
            arrows=[
                ArrowData("half", "bond", "C-C(cycloprop)",
                          "atom", "C(radical)", "#ff6600", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"homolysis": "균열 개열"},
            energy_label="C-C 균열",
            reagents="heat (300-500 C)",
        ),
        MechanismStep(
            step_number=2,
            title="1,3-비라디칼 중간체",
            description=(
                "개방형 1,3-비라디칼.\n"
                "알릴 라디칼 안정화에 의해 부분 안정.\n"
                "회전 → suprafacial/antarafacial 배향 결정."
            ),
            reactant_smiles="[CH2]CC=C[CH2]",
            product_smiles="[CH2]CC=C[CH2]",
            arrows=[
                ArrowData("half", "atom", "C(rad1)",
                          "atom", "C(rad2)", "#ff6600", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"biradical": "1,3-비라디칼"},
            energy_label="비라디칼",
        ),
        MechanismStep(
            step_number=3,
            title="고리 닫힘 → 시클로펜텐",
            description=(
                "라디칼 재결합으로 5원 고리 형성.\n"
                "C1-C5 결합 형성 → 시클로펜텐.\n"
                "suprafacial: cis 생성물 우세."
            ),
            reactant_smiles="[CH2]CC=C[CH2]",
            product_smiles="C1CC=CC1",
            arrows=[
                ArrowData("half", "atom", "C(rad)",
                          "atom", "C(rad)", "#ff6600", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"closure": "고리 닫힘"},
            is_transition_state=True,
            energy_label="고리화 TS",
        ),
        MechanismStep(
            step_number=4,
            title="최종 생성물: 시클로펜텐",
            description=(
                "시클로펜텐 생성.\n"
                "열역학적 구동력: 시클로프로판 변형 에너지 해소.\n"
                "Neureiter, 1959. Vogel, 1960.\n"
                "donor-acceptor VCP → 실온 가능 (de Meijere)."
            ),
            reactant_smiles="C1CC=CC1",
            product_smiles="C1CC=CC1",
            arrows=[],
            labels={"cyclopentene": "최종 생성물"},
            energy_label="생성물",
            notes="Neureiter, 1959; Vogel, 1960",
        ),
    ],
    energy_diagram=[
        ("비닐시클로프로판", 0.0),
        ("C-C 균열 TS", 35.0),
        ("1,3-비라디칼", 25.0),
        ("고리화 TS", 30.0),
        ("시클로펜텐", -10.0),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Cycle 17: Retro-Diels-Alder, Oxy-Cope, Mislow-Evans, Negishi, Stille
# ═══════════════════════════════════════════════════════════════════════════════

MECHANISMS["retro_diels_alder"] = MechanismData(
    mechanism_type="retro_diels_alder",
    title="레트로 딜스-알더 반응 (Retro-Diels-Alder)",
    total_steps=5,
    overall_description=(
        "레트로 딜스-알더: 시클로헥센 유도체의 열적 [4+2] 역반응.\n"
        "협주적 pericyclic 과정으로 디엔 + 디에노필로 분해.\n"
        "Woodward-Hoffmann 규칙에 따라 supra/supra 허용.\n"
        "활성화 에너지: ~200-300 kJ/mol. Flash Vacuum Pyrolysis(FVP) 조건."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="출발물: 시클로헥센 유도체",
            description=(
                "시클로헥센 고리에 전자끌개기/이탈기 치환.\n"
                "열적 조건(400-600 °C) 또는 FVP 적용.\n"
                "Woodward-Hoffmann: [4s+2s] 역반응 열허용."
            ),
            reactant_smiles="O=C1C=CC(=O)CC1",
            product_smiles="O=C1C=CC(=O)CC1",
            arrows=[],
            labels={"substrate": "시클로헥센 유도체"},
            energy_label="출발물",
            reagents="heat (400-600 C) or FVP",
        ),
        MechanismStep(
            step_number=2,
            title="C1-C6 및 C3-C4 결합 동시 신장",
            description=(
                "열에너지에 의해 두 시그마 결합 동시 신장 시작.\n"
                "보트형 전이상태로 이행.\n"
                "6전자 협주적 과정 (4pi 디엔 + 2pi 디에노필 역반응)."
            ),
            reactant_smiles="O=C1C=CC(=O)CC1",
            product_smiles="O=C1C=CC(=O)CC1",
            arrows=[
                ArrowData("full", "bond", "C1-C6",
                          "atom", "C1", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C3-C4",
                          "atom", "C3", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"bond_stretch": "결합 신장"},
            energy_label="결합 신장",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=3,
            title="협주적 전이상태 [보트형]",
            description=(
                "6원 고리 보트형 전이상태.\n"
                "C1-C6, C3-C4 시그마 결합 부분 절단.\n"
                "C2-C3, C4-C5 파이 결합 형성 진행.\n"
                "초분자면 궤도대칭 보존."
            ),
            reactant_smiles="O=C1C=CC(=O)CC1",
            product_smiles="O=CC=CC=O.C=C",
            arrows=[
                ArrowData("full", "bond", "C1-C6",
                          "atom", "C6", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C3-C4",
                          "atom", "C4", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TS": "보트형 TS"},
            energy_label="[4+2] 역반응 TS",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=4,
            title="결합 절단 완료 → 디엔 + 디에노필 분리",
            description=(
                "두 시그마 결합 완전 절단.\n"
                "디엔(1,3-부타디엔 유도체) + 디에노필(에틸렌 유도체) 생성.\n"
                "기체상에서 엔트로피 구동력(Delta S > 0)."
            ),
            reactant_smiles="O=CC=CC=O.C=C",
            product_smiles="O=CC=CC=O.C=C",
            arrows=[],
            labels={"fragmentation": "단편화"},
            energy_label="단편화",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: 디엔 + 디에노필",
            description=(
                "레트로 딜스-알더 생성물.\n"
                "말레알데히드(디엔) + 에틸렌(디에노필) 분리.\n"
                "고온 기상 조건에서 비가역적.\n"
                "합성 응용: 보호기 제거, 천연물 분해 분석."
            ),
            reactant_smiles="O=CC=CC=O",
            product_smiles="O=CC=CC=O",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Retro-Diels-Alder, FVP conditions",
        ),
    ],
    energy_diagram=[
        ("시클로헥센 유도체", 0.0),
        ("결합 신장", 15.0),
        ("보트형 TS", 45.0),
        ("단편화", 10.0),
        ("디엔 + 디에노필", -5.0),
    ],
)

MECHANISMS["oxy_cope_rearrangement"] = MechanismData(
    mechanism_type="oxy_cope_rearrangement",
    title="옥시-코프 전위 (Oxy-Cope Rearrangement)",
    total_steps=5,
    overall_description=(
        "옥시-코프 전위: 1,5-디엔-3-올의 [3,3]-시그마트로피 전위.\n"
        "KH(수소화칼륨) 등 강염기로 알콕사이드 형성 → anionic oxy-Cope.\n"
        "에놀레이트 중간체 → 토토머화 → 케톤 생성물.\n"
        "Berson, 1964; Evans, Golob, 1975 (anionic accelerated)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="알콕사이드 형성 (염기 탈양성자화)",
            description=(
                "KH에 의한 C3-OH 탈양성자화.\n"
                "알콕사이드 음이온 형성.\n"
                "anionic oxy-Cope는 중성 oxy-Cope보다\n"
                "10^10~10^17배 가속 (Evans-Golob 효과)."
            ),
            reactant_smiles="C=CC(O)CC=C",
            product_smiles="C=CC([O-])CC=C",
            arrows=[
                ArrowData("full", "atom", "H(OH)",
                          "atom", "K(KH)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"deprotonation": "탈양성자화"},
            energy_label="알콕사이드 형성",
            reagents="KH, THF, -78 to 25 C",
        ),
        MechanismStep(
            step_number=2,
            title="의자형 전이상태 ([3,3]-시그마트로피)",
            description=(
                "6원 의자형 전이상태 형성.\n"
                "C1-C6 결합 형성 + C3-C4 결합 절단 동시 진행.\n"
                "음이온 가속: 알콕사이드의 전자공여 효과.\n"
                "Woodward-Hoffmann 열허용 [3,3]."
            ),
            reactant_smiles="C=CC([O-])CC=C",
            product_smiles="C=CC([O-])CC=C",
            arrows=[
                ArrowData("full", "atom", "C1",
                          "atom", "C6", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C3-C4",
                          "atom", "C3", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TS": "의자형 TS"},
            energy_label="[3,3] TS",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=3,
            title="에놀레이트 중간체 형성",
            description=(
                "[3,3]-전위 후 에놀레이트 음이온 생성.\n"
                "C-C 결합 재배열 완료.\n"
                "dienolate: O-C=C-C=C-C 공액 체계."
            ),
            reactant_smiles="[O-]C(=CC=CC)CC",
            product_smiles="[O-]C(=CC=CC)CC",
            arrows=[],
            labels={"enolate": "에놀레이트"},
            energy_label="에놀레이트",
        ),
        MechanismStep(
            step_number=4,
            title="에놀레이트 → 케톤 토토머화",
            description=(
                "수용성 워크업(H3O+) 시 양성자화.\n"
                "에놀 → 케톤 호변이성.\n"
                "열역학적으로 안정한 케톤 형태로 수렴."
            ),
            reactant_smiles="[O-]C(=CC=CC)CC",
            product_smiles="O=C(CC=CC)CC",
            arrows=[
                ArrowData("full", "atom", "H(H3O+)",
                          "atom", "C(alpha)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"tautomerization": "토토머화"},
            energy_label="토토머화",
            reagents="H3O+, workup",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: 케톤",
            description=(
                "옥시-코프 전위 생성물.\n"
                "1,5-디엔-3-올 → 불포화 케톤.\n"
                "Berson, 1964. Evans, Golob, 1975.\n"
                "합성 응용: 10원 고리 케톤 합성 (Paquette)."
            ),
            reactant_smiles="O=C(CC=CC)CC",
            product_smiles="O=C(CC=CC)CC",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Evans, Golob, 1975; Berson, 1964",
        ),
    ],
    energy_diagram=[
        ("1,5-디엔-3-올", 0.0),
        ("알콕사이드", -5.0),
        ("[3,3] TS", 15.0),
        ("에놀레이트", -20.0),
        ("케톤", -25.0),
    ],
)

MECHANISMS["mislow_evans_elimination"] = MechanismData(
    mechanism_type="mislow_evans_elimination",
    title="미슬로우-에반스 syn-제거 (Selenoxide/Sulfoxide Elimination)",
    total_steps=5,
    overall_description=(
        "미슬로우-에반스 syn-제거: 셀레녹사이드/설폭사이드의\n"
        "열적 syn-제거 → 알켄 + PhSeOH/PhSOH.\n"
        "Ei 메커니즘 (내부 제거): 5원 고리 전이상태.\n"
        "Sharpless, 1973 (selenoxide). Mislow, 1965 (sulfoxide)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="셀레나이드 산화 → 셀레녹사이드 형성",
            description=(
                "PhSeCH2R을 H2O2 또는 mCPBA로 산화.\n"
                "셀레녹사이드(PhSe(=O)CH2R) 형성.\n"
                "Se 원자에 산소 도입, Se(IV) 산화 상태."
            ),
            reactant_smiles="C(C)[Se]c1ccccc1",
            product_smiles="C(C)[Se](=O)c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "O(mCPBA)",
                          "atom", "Se", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"oxidation": "Se 산화"},
            energy_label="셀레녹사이드 형성",
            reagents="H2O2 or mCPBA, CH2Cl2, 0 C",
        ),
        MechanismStep(
            step_number=2,
            title="5원 고리 전이상태 (Ei 메커니즘)",
            description=(
                "셀레녹사이드 Se=O의 산소가 beta-H를 추출.\n"
                "5원 고리 평면 전이상태 형성.\n"
                "syn-periplanar 배향 필수: Se-C-C-H 이면각 = 0 deg.\n"
                "Ei (intramolecular elimination) 메커니즘."
            ),
            reactant_smiles="C(C)[Se](=O)c1ccccc1",
            product_smiles="C(C)[Se](=O)c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "O(Se=O)",
                          "atom", "H(beta)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-Se",
                          "atom", "Se", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"Ei_TS": "5원 고리 TS"},
            energy_label="Ei 전이상태",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=3,
            title="C-Se 결합 절단 + C=C 형성",
            description=(
                "C-Se 시그마 결합 절단.\n"
                "beta-C와 alpha-C 사이 이중결합 형성.\n"
                "PhSeOH 이탈 (셀렌산).\n"
                "syn-제거이므로 cis 생성물 우세."
            ),
            reactant_smiles="C(C)[Se](=O)c1ccccc1",
            product_smiles="C=C.O[Se]c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-Se",
                          "atom", "C(alpha)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"elimination": "syn-제거"},
            energy_label="결합 절단",
        ),
        MechanismStep(
            step_number=4,
            title="생성물 분리: 알켄 + PhSeOH",
            description=(
                "알켄(올레핀) + 페닐셀레노산(PhSeOH) 생성.\n"
                "PhSeOH는 자발적으로 PhSeSePh + H2O로 이합체화.\n"
                "낮은 온도(0-25 °C)에서도 원활 진행."
            ),
            reactant_smiles="C=C",
            product_smiles="C=C",
            arrows=[],
            labels={"separation": "생성물 분리"},
            energy_label="분리",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물: 알켄",
            description=(
                "미슬로우-에반스 syn-제거 생성물.\n"
                "온화한 조건의 알켄 합성법.\n"
                "Sharpless, 1973; Mislow, 1965.\n"
                "설폭사이드의 경우 더 높은 온도 필요 (80-110 °C)."
            ),
            reactant_smiles="C=C",
            product_smiles="C=C",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Sharpless, 1973; Mislow, 1965",
        ),
    ],
    energy_diagram=[
        ("셀레나이드", 0.0),
        ("셀레녹사이드", -5.0),
        ("Ei TS", 20.0),
        ("알켄 + PhSeOH", -15.0),
        ("최종 알켄", -18.0),
    ],
)

MECHANISMS["negishi_coupling"] = MechanismData(
    mechanism_type="negishi_coupling",
    title="네기시 커플링 (Negishi Coupling)",
    total_steps=5,
    overall_description=(
        "네기시 커플링: Pd(0) 촉매, 유기아연(R-ZnX) + 유기할라이드(R'-X).\n"
        "Negishi, 1977. 노벨화학상 2010 공동수상.\n"
        "sp2-sp2, sp2-sp3 커플링 모두 가능.\n"
        "Zn의 높은 친전자성 → 빠른 전이금속화(transmetalation)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가 (Oxidative Addition)",
            description=(
                "Pd(0)(PPh3)4에서 리간드 해리 → Pd(0)(PPh3)2.\n"
                "ArBr(유기할라이드)의 C-Br 결합에 산화적 첨가.\n"
                "Pd(0) → Pd(II): Ar-Pd(II)-Br 착물 형성."
            ),
            reactant_smiles="c1ccc(Br)cc1",
            product_smiles="Br[Pd]c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "Pd",
                          "bond", "C-Br", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"OA": "산화적 첨가"},
            energy_label="산화적 첨가",
            reagents="Pd(PPh3)4, THF, rt",
        ),
        MechanismStep(
            step_number=2,
            title="전이금속화 (Transmetalation)",
            description=(
                "R-ZnCl(유기아연)이 Ar-Pd(II)-Br 착물에 접근.\n"
                "Zn에서 Pd로 R기 이동 (전이금속화).\n"
                "ZnBrCl 부산물 이탈.\n"
                "Zn의 높은 루이스 산성이 Br- 친화력 제공."
            ),
            reactant_smiles="Br[Pd]c1ccccc1",
            product_smiles="C[Pd]c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "C(R-ZnCl)",
                          "atom", "Pd", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "atom", "Br(Pd)",
                          "atom", "Zn", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TM": "전이금속화"},
            energy_label="전이금속화",
            reagents="R-ZnCl",
        ),
        MechanismStep(
            step_number=3,
            title="cis/trans 이성화",
            description=(
                "trans-Ar-Pd(II)-R 착물 → cis 이성화.\n"
                "환원적 제거를 위해 두 유기기가\n"
                "서로 cis 위치에 있어야 함.\n"
                "리간드 교환/해리에 의한 기하 이성화."
            ),
            reactant_smiles="C[Pd]c1ccccc1",
            product_smiles="C[Pd]c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "R(trans)",
                          "atom", "R(cis)", "#cc0000", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"isomerization": "이성화"},
            energy_label="cis/trans 이성화",
        ),
        MechanismStep(
            step_number=4,
            title="환원적 제거 (Reductive Elimination)",
            description=(
                "cis-Ar-Pd(II)-R에서 C-C 결합 형성.\n"
                "Pd(II) → Pd(0) 환원.\n"
                "Ar-R 생성물 방출.\n"
                "Pd(0) 촉매 재생 → 촉매 순환 완료."
            ),
            reactant_smiles="C[Pd]c1ccccc1",
            product_smiles="Cc1ccccc1",
            arrows=[
                ArrowData("full", "atom", "C(R)",
                          "atom", "C(Ar)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"RE": "환원적 제거"},
            energy_label="환원적 제거",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물 + 촉매 재생",
            description=(
                "Ar-R 커플링 생성물 + Pd(0) 촉매 재생.\n"
                "부산물: ZnBrCl (무기 Zn 염).\n"
                "Negishi, 1977. 2010 노벨화학상.\n"
                "관용도: 에스터, 니트릴, 아미드 등 다양한 관능기 호환."
            ),
            reactant_smiles="Cc1ccccc1",
            product_smiles="Cc1ccccc1",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Negishi, 1977; Nobel Prize 2010",
        ),
    ],
    energy_diagram=[
        ("Pd(0) + ArBr + RZnCl", 0.0),
        ("산화적 첨가", 15.0),
        ("전이금속화", 5.0),
        ("cis 이성화", 8.0),
        ("환원적 제거", 12.0),
        ("Ar-R + Pd(0)", -20.0),
    ],
)

MECHANISMS["stille_coupling"] = MechanismData(
    mechanism_type="stille_coupling",
    title="스틸 커플링 (Stille Coupling)",
    total_steps=5,
    overall_description=(
        "스틸 커플링: Pd(0) 촉매, 유기주석(R-SnBu3) + 유기할라이드(R'-X).\n"
        "Stille, Milstein, 1978.\n"
        "높은 관능기 내성. vinyl, aryl, acyl 모두 가능.\n"
        "단점: 유기주석의 독성. Sn 부산물 제거 어려움."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가 (Oxidative Addition)",
            description=(
                "Pd(0)(PPh3)2L2 활성종에 R'-X(할라이드) 산화적 첨가.\n"
                "C-X 결합 끊어짐, Pd(0) → Pd(II).\n"
                "R'-Pd(II)-X 착물 형성.\n"
                "요오드 > 브롬 >> 클로르 반응성 순서."
            ),
            reactant_smiles="C(=O)(Cl)c1ccccc1",
            product_smiles="Cl[Pd]C(=O)c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "Pd",
                          "bond", "C-Cl", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"OA": "산화적 첨가"},
            energy_label="산화적 첨가",
            reagents="Pd(PPh3)4 or Pd2(dba)3, DMF, 80 C",
        ),
        MechanismStep(
            step_number=2,
            title="전이금속화 (Transmetalation with Sn)",
            description=(
                "R-SnBu3(유기주석)이 R'-Pd(II)-X 착물과 전이금속화.\n"
                "Sn에서 Pd로 R기 이동.\n"
                "Bu3SnX 부산물 이탈.\n"
                "속도결정단계 (rate-determining step)."
            ),
            reactant_smiles="Cl[Pd]C(=O)c1ccccc1",
            product_smiles="C=C[Pd]C(=O)c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "C(vinyl-SnBu3)",
                          "atom", "Pd", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "atom", "Cl(Pd)",
                          "atom", "Sn", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TM": "전이금속화"},
            energy_label="전이금속화 (RDS)",
            reagents="R-SnBu3",
        ),
        MechanismStep(
            step_number=3,
            title="cis/trans 이성화",
            description=(
                "trans-R'-Pd(II)-R → cis 이성화.\n"
                "환원적 제거를 위한 기하학적 요건 충족.\n"
                "인 리간드의 해리/재결합이 이성화 촉진."
            ),
            reactant_smiles="C=C[Pd]C(=O)c1ccccc1",
            product_smiles="C=C[Pd]C(=O)c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "R(trans)",
                          "atom", "R(cis)", "#cc0000", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"isomerization": "이성화"},
            energy_label="cis 이성화",
        ),
        MechanismStep(
            step_number=4,
            title="환원적 제거 (Reductive Elimination)",
            description=(
                "cis 착물에서 R'-R 결합 형성.\n"
                "Pd(II) → Pd(0) 환원.\n"
                "비닐 케톤 생성물 방출.\n"
                "Pd(0) 촉매 재생."
            ),
            reactant_smiles="C=C[Pd]C(=O)c1ccccc1",
            product_smiles="C=CC(=O)c1ccccc1",
            arrows=[
                ArrowData("full", "atom", "C(vinyl)",
                          "atom", "C(acyl)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"RE": "환원적 제거"},
            energy_label="환원적 제거",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물 + 촉매 재생",
            description=(
                "R'-R 커플링 생성물 + Pd(0) 재생.\n"
                "부산물: Bu3SnCl (독성, 크로마토그래피 제거 필요).\n"
                "Stille, Milstein, 1978.\n"
                "최근: SnBu3 대신 SnMe3(덜 독성) 사용 연구."
            ),
            reactant_smiles="C=CC(=O)c1ccccc1",
            product_smiles="C=CC(=O)c1ccccc1",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Stille, Milstein, 1978",
        ),
    ],
    energy_diagram=[
        ("Pd(0) + R'X + RSnBu3", 0.0),
        ("산화적 첨가", 12.0),
        ("전이금속화 (RDS)", 25.0),
        ("cis 이성화", 18.0),
        ("환원적 제거", 15.0),
        ("R'-R + Pd(0)", -18.0),
    ],
)


# ============================================================================
# Cycle 18: Kumada, Tebbe, Petasis, Buchwald-Hartwig, Chan-Lam
# ============================================================================

MECHANISMS["kumada_coupling"] = MechanismData(
    mechanism_type="kumada_coupling",
    title="Kumada 커플링 (Kumada Coupling)",
    total_steps=5,
    overall_description=(
        "Pd 또는 Ni 촉매 하에 ArX + RMgBr → Ar-R 생성.\n"
        "Grignard 시약을 직접 사용하는 유일한 크로스커플링.\n"
        "Kumada, Tamao, 1972. Corriu, 1972 (독립 발견).\n"
        "관능기 허용범위 제한적 (Grignard의 높은 반응성)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가 (Oxidative Addition)",
            description=(
                "Pd(0) 또는 Ni(0) 촉매가 Ar-X 결합에 삽입.\n"
                "M(0) → M(II) 산화. Ar-M(II)-X 착물 형성.\n"
                "Ni 촉매: NiCl2(dppf) 또는 Ni(acac)2 사용.\n"
                "Pd 촉매: Pd(dppf)Cl2 또는 PdCl2(PPh3)2 사용."
            ),
            reactant_smiles="Clc1ccccc1",
            product_smiles="Cl[Ni]c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "Ni(0)",
                          "bond", "C-Cl", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"OA": "산화적 첨가"},
            energy_label="산화적 첨가",
            reagents="NiCl2(dppf), THF, rt",
        ),
        MechanismStep(
            step_number=2,
            title="전이금속화 (Transmetalation)",
            description=(
                "RMgBr(그리냐르 시약)이 Ar-Ni(II)-Cl에 접근.\n"
                "Mg에서 Ni로 R기 이동 (전이금속화).\n"
                "MgBrCl 부산물 이탈.\n"
                "그리냐르의 높은 반응성으로 빠른 전이금속화."
            ),
            reactant_smiles="Cl[Ni]c1ccccc1",
            product_smiles="C[Ni]c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-Mg(RMgBr)",
                          "atom", "Ni", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "Cl-Ni",
                          "atom", "Mg", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TM": "전이금속화"},
            energy_label="전이금속화",
            reagents="RMgBr",
        ),
        MechanismStep(
            step_number=3,
            title="cis/trans 이성화",
            description=(
                "trans-Ar-Ni(II)-R → cis 이성화.\n"
                "환원적 제거를 위한 기하학적 요건.\n"
                "인산 리간드 해리/재결합이 이성화 촉진."
            ),
            reactant_smiles="C[Ni]c1ccccc1",
            product_smiles="C[Ni]c1ccccc1",
            arrows=[],
            labels={"isom": "이성화"},
            energy_label="이성화",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=4,
            title="환원적 제거 (Reductive Elimination)",
            description=(
                "cis 착물에서 Ar-R 결합 형성.\n"
                "Ni(II) → Ni(0) 환원. 촉매 재생.\n"
                "속도결정단계 (bulky 리간드 시)."
            ),
            reactant_smiles="C[Ni]c1ccccc1",
            product_smiles="Cc1ccccc1",
            arrows=[
                ArrowData("full", "bond", "Ar-Ni",
                          "bond", "R-Ni", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"RE": "환원적 제거"},
            energy_label="환원적 제거",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물 + 촉매 재생",
            description=(
                "Ar-R 커플링 생성물 + Ni(0) 재생.\n"
                "부산물: MgBrCl.\n"
                "Kumada, Tamao, 1972. Corriu, 1972.\n"
                "제한: 에스터/알데히드 관능기와 그리냐르 반응."
            ),
            reactant_smiles="Cc1ccccc1",
            product_smiles="Cc1ccccc1",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Kumada, Tamao, 1972",
        ),
    ],
    energy_diagram=[
        ("Ni(0) + ArX + RMgBr", 0.0),
        ("산화적 첨가", 10.0),
        ("전이금속화", 8.0),
        ("cis/trans 이성화", 14.0),
        ("환원적 제거", 18.0),
        ("Ar-R + Ni(0)", -22.0),
    ],
)

MECHANISMS["tebbe_olefination"] = MechanismData(
    mechanism_type="tebbe_olefination",
    title="Tebbe 올레핀화 (Tebbe Olefination)",
    total_steps=5,
    overall_description=(
        "Tebbe 시약(Cp2TiCH2·ClAlMe2) + C=O → 알켄.\n"
        "에스터/아미드의 C=O도 올레핀화 가능 (Wittig 불가 기질).\n"
        "핵심: Cp2Ti=CH2 카르벤 중간체 (티타나사이클 경유).\n"
        "Tebbe, Parshall, Reddy, 1978."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Tebbe 시약 활성화",
            description=(
                "Tebbe 시약(Cp2TiCH2·ClAlMe2)에 루이스 염기(피리딘) 첨가.\n"
                "AlMe2Cl 이탈. Cp2Ti=CH2 (Petasis 시약) 생성.\n"
                "Ti=C 이중결합: 14전자 티타늄 카르벤."
            ),
            reactant_smiles="[Ti]([CH2])Cl",
            product_smiles="[Ti]=[CH2]",
            arrows=[
                ArrowData("full", "lone_pair", "pyridine N",
                          "atom", "Al", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"act": "활성화"},
            energy_label="시약 활성화",
            reagents="pyridine, toluene, -40 °C",
        ),
        MechanismStep(
            step_number=2,
            title="[2+2] 고리화 첨가",
            description=(
                "Cp2Ti=CH2가 카르보닐 C=O에 [2+2] 고리화 첨가.\n"
                "4원 옥사티타나사이클부탄 형성.\n"
                "Ti-O 친화력이 열역학적 구동력."
            ),
            reactant_smiles="[Ti]=[CH2]",
            product_smiles="C1[Ti]OC1",
            arrows=[
                ArrowData("full", "pi_bond", "Ti=CH2",
                          "atom", "C(C=O)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "C=O",
                          "atom", "Ti", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"[2+2]": "고리화 첨가"},
            energy_label="[2+2] 고리화",
            reagents="",
        ),
        MechanismStep(
            step_number=3,
            title="옥사티타나사이클부탄 중간체",
            description=(
                "4원 고리 중간체: Ti-CH2-C-O-Ti.\n"
                "Ti-O 결합이 매우 강함 (BDE ~110 kcal/mol).\n"
                "고리 변형으로 인한 결합 약화."
            ),
            reactant_smiles="C1[Ti]OC1",
            product_smiles="C1[Ti]OC1",
            arrows=[],
            labels={"intermediate": "옥사티타나사이클부탄"},
            energy_label="4원 고리 중간체",
            is_transition_state=False,
        ),
        MechanismStep(
            step_number=4,
            title="[2+2] 역고리 첨가 (Retro-[2+2])",
            description=(
                "옥사티타나사이클부탄의 역 [2+2] 고리 열림.\n"
                "C=C 알켄 + Cp2Ti=O (강한 Ti=O 결합) 생성.\n"
                "열역학적 구동력: Ti=O 결합 에너지."
            ),
            reactant_smiles="C1[Ti]OC1",
            product_smiles="C=C",
            arrows=[
                ArrowData("full", "bond", "Ti-CH2",
                          "bond", "C-O", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"retro": "역 [2+2]"},
            energy_label="역고리 첨가",
        ),
        MechanismStep(
            step_number=5,
            title="알켄 생성물 + Cp2Ti=O",
            description=(
                "알켄(올레핀) 생성물 + Cp2Ti=O 부산물.\n"
                "Tebbe, 1978. Grubbs, Tumas, 1989 (메커니즘 규명).\n"
                "장점: 에스터→에놀에테르, 아미드→에남인 변환 가능.\n"
                "단점: Tebbe 시약 취급 어려움 (공기/수분 민감)."
            ),
            reactant_smiles="C=C",
            product_smiles="C=C",
            arrows=[],
            labels={"product": "알켄 생성물"},
            energy_label="생성물",
            notes="Tebbe, 1978; Grubbs mechanism, 1989",
        ),
    ],
    energy_diagram=[
        ("Cp2TiCH2·ClAlMe2 + C=O", 0.0),
        ("Cp2Ti=CH2 활성화", 5.0),
        ("[2+2] 고리화 TS", 18.0),
        ("옥사티타나사이클부탄", 8.0),
        ("retro-[2+2] TS", 22.0),
        ("C=C + Cp2Ti=O", -25.0),
    ],
)

MECHANISMS["petasis_reaction"] = MechanismData(
    mechanism_type="petasis_reaction",
    title="Petasis 반응 (Petasis Borono-Mannich Reaction)",
    total_steps=5,
    overall_description=(
        "ArB(OH)2 + 아민 + 알데히드 → α-아미노산 유도체.\n"
        "3성분 반응 (multicomponent reaction).\n"
        "보론산의 유기기가 이미늄 이온에 전이.\n"
        "Petasis, Akritopoulou, 1993."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이미늄 이온 형성",
            description=(
                "아민(R2NH)이 알데히드(RCHO)에 친핵 첨가.\n"
                "카르비놀아민 → 탈수 → 이미늄 이온 생성.\n"
                "헤미아미날 경유."
            ),
            reactant_smiles="O=CC(=O)O",
            product_smiles="OC(=O)C=[NH+]C",
            arrows=[
                ArrowData("full", "lone_pair", "N(amine)",
                          "atom", "C(C=O)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"iminium": "이미늄 이온"},
            energy_label="이미늄 형성",
            reagents="R2NH, glyoxylic acid",
        ),
        MechanismStep(
            step_number=2,
            title="보론산-이미늄 착물 형성",
            description=(
                "ArB(OH)2가 이미늄 이온의 카르복실레이트 O와 배위.\n"
                "보론의 루이스 산성 → O-B 결합 형성.\n"
                "4배위 '먹는(ate)' 착물 (tetracoordinate boron)."
            ),
            reactant_smiles="OC(=O)C=[NH+]C",
            product_smiles="O[B-](O)(c1ccccc1)OC(=O)C=[NH+]C",
            arrows=[
                ArrowData("full", "lone_pair", "O(COO-)",
                          "atom", "B", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"ate": "보론 ate 착물"},
            energy_label="B-O 배위",
            reagents="ArB(OH)2",
        ),
        MechanismStep(
            step_number=3,
            title="1,3-Ar 이동 (Aryl Migration)",
            description=(
                "보론의 Ar기가 C=N+ 탄소로 [1,3] 이동.\n"
                "C-B 결합 절단 + C-C 결합 형성 (동시적).\n"
                "속도결정단계. 전자풍부 Ar기일수록 빠름."
            ),
            reactant_smiles="O[B-](O)(c1ccccc1)OC(=O)C=[NH+]C",
            product_smiles="OC(=O)C(c1ccccc1)NCC",
            arrows=[
                ArrowData("full", "bond", "C-B(Ar)",
                          "atom", "C(=N+)", "#cc0000", 0.5,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"migration": "Ar 이동"},
            energy_label="1,3-Ar 이동 (RDS)",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=4,
            title="보론 이탈 + 아미노산 형성",
            description=(
                "B(OH)2 이탈. α-아미노산 유도체 형성.\n"
                "B(OH)3 부산물 (무독성).\n"
                "입체선택성: chiral diol 리간드로 유도 가능."
            ),
            reactant_smiles="OC(=O)C(c1ccccc1)NCC",
            product_smiles="OC(=O)C(c1ccccc1)NCC",
            arrows=[],
            labels={"product": "α-아미노산"},
            energy_label="아미노산 형성",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물",
            description=(
                "α-아릴글리신 유도체.\n"
                "Petasis, 1993.\n"
                "장점: 수성 조건, 관능기 허용범위 넓음.\n"
                "응용: 비천연 아미노산, 항경련제 합성."
            ),
            reactant_smiles="OC(=O)C(c1ccccc1)NCC",
            product_smiles="OC(=O)C(c1ccccc1)NCC",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Petasis, 1993",
        ),
    ],
    energy_diagram=[
        ("ArB(OH)2 + R2NH + RCHO", 0.0),
        ("이미늄 이온", 5.0),
        ("B-O 배위 착물", 2.0),
        ("1,3-Ar 이동 TS (RDS)", 20.0),
        ("α-아미노산 + B(OH)3", -15.0),
    ],
)

MECHANISMS["buchwald_hartwig"] = MechanismData(
    mechanism_type="buchwald_hartwig",
    title="Buchwald-Hartwig 아민화 (Buchwald-Hartwig Amination)",
    total_steps=5,
    overall_description=(
        "ArX + R2NH + Pd 촉매 → Ar-NR2.\n"
        "C-N 결합 형성의 가장 중요한 방법론.\n"
        "Buchwald, Hartwig 독립 개발, 1994.\n"
        "Bulky biaryl phosphine 리간드(SPhos, XPhos) 핵심."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="산화적 첨가 (Oxidative Addition)",
            description=(
                "Pd(0)L2 활성종이 Ar-X 결합에 삽입.\n"
                "Pd(0) → Pd(II) 산화.\n"
                "Ar-Pd(II)(L)-X 착물 형성.\n"
                "반응성: I > OTf > Br >> Cl."
            ),
            reactant_smiles="Brc1ccccc1",
            product_smiles="Br[Pd]c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "Pd(0)",
                          "bond", "C-Br", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"OA": "산화적 첨가"},
            energy_label="산화적 첨가",
            reagents="Pd2(dba)3, SPhos, NaOtBu, toluene, 80 °C",
        ),
        MechanismStep(
            step_number=2,
            title="아민 배위 + 염기 보조 탈양성자화",
            description=(
                "아민(R2NH)이 Pd(II) 중심에 배위.\n"
                "NaOtBu 염기가 N-H 탈양성자화.\n"
                "Pd-N(amido) 결합 형성. NaBr + tBuOH 이탈.\n"
                "Pd에서 Br- → amido 리간드 교환."
            ),
            reactant_smiles="Br[Pd]c1ccccc1",
            product_smiles="c1ccc([Pd]NC2CCCCC2)cc1",
            arrows=[
                ArrowData("full", "lone_pair", "N(amine)",
                          "atom", "Pd", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "lone_pair", "tBuO-",
                          "atom", "H(N-H)", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"coord": "아민 배위"},
            energy_label="아민 배위 + 탈양성자화",
            reagents="cyclohexylamine, NaOtBu",
        ),
        MechanismStep(
            step_number=3,
            title="Pd(II)-amido 중간체",
            description=(
                "Ar-Pd(II)-NR2 amido 착물.\n"
                "이 중간체에서 Ar과 NR2가 cis 배치 필요.\n"
                "Bulky phosphine 리간드가 cis 배치 유도."
            ),
            reactant_smiles="c1ccc([Pd]NC2CCCCC2)cc1",
            product_smiles="c1ccc([Pd]NC2CCCCC2)cc1",
            arrows=[],
            labels={"amido": "Pd-amido 중간체"},
            energy_label="Pd-amido 중간체",
            is_transition_state=False,
        ),
        MechanismStep(
            step_number=4,
            title="환원적 제거 (Reductive Elimination)",
            description=(
                "Ar-Pd(II)-NR2에서 C-N 결합 형성.\n"
                "Pd(II) → Pd(0) 환원. 촉매 재생.\n"
                "속도결정단계: bulky ligand가 환원적 제거 가속.\n"
                "전이상태: 3원 고리 구조."
            ),
            reactant_smiles="c1ccc([Pd]NC2CCCCC2)cc1",
            product_smiles="c1ccc(NC2CCCCC2)cc1",
            arrows=[
                ArrowData("full", "bond", "Ar-Pd",
                          "bond", "Pd-N", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"RE": "환원적 제거"},
            energy_label="환원적 제거 (RDS)",
        ),
        MechanismStep(
            step_number=5,
            title="최종 생성물 + 촉매 재생",
            description=(
                "Ar-NR2 아릴아민 생성물 + Pd(0) 재생.\n"
                "부산물: NaBr, tBuOH.\n"
                "Buchwald, 1994; Hartwig, 1994.\n"
                "응용: 의약품 합성(Gleevec, Nexavar 등)."
            ),
            reactant_smiles="c1ccc(NC2CCCCC2)cc1",
            product_smiles="c1ccc(NC2CCCCC2)cc1",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Buchwald, 1994; Hartwig, 1994",
        ),
    ],
    energy_diagram=[
        ("Pd(0) + ArBr + R2NH + NaOtBu", 0.0),
        ("산화적 첨가", 12.0),
        ("아민 배위 + 탈양성자화", 8.0),
        ("Pd-amido 중간체", 10.0),
        ("환원적 제거 (RDS)", 22.0),
        ("Ar-NR2 + Pd(0)", -20.0),
    ],
)

MECHANISMS["chan_lam_coupling"] = MechanismData(
    mechanism_type="chan_lam_coupling",
    title="Chan-Lam 커플링 (Chan-Lam Coupling)",
    total_steps=5,
    overall_description=(
        "ArB(OH)2 + R2NH + Cu(OAc)2 → Ar-NR2.\n"
        "구리 촉매 C-N 결합 형성. 실온, 공기 중 반응.\n"
        "Pd-free 대안. Chan, Lam, 1998.\n"
        "산화제: O2 (공기). 염기: Et3N 또는 pyridine."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Cu(II)-아민 배위",
            description=(
                "Cu(OAc)2가 아민(R2NH)과 배위.\n"
                "N의 비공유전자쌍 → Cu(II) 배위.\n"
                "Cu(II)(OAc)(NR2) 착물 형성.\n"
                "Et3N이 NH 탈양성자화 보조."
            ),
            reactant_smiles="CC(=O)O[Cu]OC(C)=O",
            product_smiles="CC(=O)O[Cu]NC1CCCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "N(amine)",
                          "atom", "Cu", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"coord": "Cu-아민 배위"},
            energy_label="아민 배위",
            reagents="Cu(OAc)2, Et3N, CH2Cl2, rt, air",
        ),
        MechanismStep(
            step_number=2,
            title="전이금속화 (Transmetalation)",
            description=(
                "ArB(OH)2가 Cu(II) 착물과 전이금속화.\n"
                "B에서 Cu로 Ar기 이동.\n"
                "Cu(II)(Ar)(NR2) 착물 형성.\n"
                "B(OH)3 부산물 이탈."
            ),
            reactant_smiles="CC(=O)O[Cu]NC1CCCCC1",
            product_smiles="c1ccc([Cu]NC2CCCCC2)cc1",
            arrows=[
                ArrowData("full", "bond", "C-B(ArB(OH)2)",
                          "atom", "Cu", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"TM": "전이금속화"},
            energy_label="전이금속화",
            reagents="ArB(OH)2",
        ),
        MechanismStep(
            step_number=3,
            title="Cu(III) 중간체 형성 (산화)",
            description=(
                "Cu(II) → Cu(III) 1전자 산화 (O2에 의해).\n"
                "Cu(III)(Ar)(NR2) 착물.\n"
                "또는 Cu(II)에서 직접 환원적 제거 논쟁.\n"
                "최근 DFT 연구: Cu(III) 경로 유력."
            ),
            reactant_smiles="c1ccc([Cu]NC2CCCCC2)cc1",
            product_smiles="c1ccc([Cu]NC2CCCCC2)cc1",
            arrows=[],
            labels={"Cu(III)": "산화"},
            energy_label="Cu(III) 중간체",
            is_transition_state=True,
        ),
        MechanismStep(
            step_number=4,
            title="환원적 제거 (Reductive Elimination)",
            description=(
                "Cu(III)(Ar)(NR2)에서 C-N 결합 형성.\n"
                "Cu(III) → Cu(I) 환원.\n"
                "Ar-NR2 아릴아민 생성물 방출.\n"
                "Cu(I) → O2 산화 → Cu(II) 촉매 재생."
            ),
            reactant_smiles="c1ccc([Cu]NC2CCCCC2)cc1",
            product_smiles="c1ccc(NC2CCCCC2)cc1",
            arrows=[
                ArrowData("full", "bond", "Ar-Cu",
                          "bond", "Cu-N", "#cc0000", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"RE": "환원적 제거"},
            energy_label="환원적 제거",
        ),
        MechanismStep(
            step_number=5,
            title="촉매 재생 + 최종 생성물",
            description=(
                "Ar-NR2 커플링 생성물.\n"
                "Cu(I) + O2 → Cu(II) 촉매 재생.\n"
                "부산물: B(OH)3, AcOH.\n"
                "Chan, Evans, Lam, 1998.\n"
                "장점: Pd-free, 실온, 공기 중 반응."
            ),
            reactant_smiles="c1ccc(NC2CCCCC2)cc1",
            product_smiles="c1ccc(NC2CCCCC2)cc1",
            arrows=[],
            labels={"product": "최종 생성물"},
            energy_label="생성물",
            notes="Chan, Evans, Lam, 1998",
        ),
    ],
    energy_diagram=[
        ("Cu(OAc)2 + ArB(OH)2 + R2NH", 0.0),
        ("Cu(II)-아민 배위", 3.0),
        ("전이금속화", 10.0),
        ("Cu(III) 산화", 18.0),
        ("환원적 제거", 15.0),
        ("Ar-NR2 + Cu(II)", -12.0),
    ],
)


# ─── Cope Elimination (열적 syn-제거) ──────────────────────────────────
# 아민 옥사이드 → 알켄 + 하이드록실아민 (5원 고리 전이상태)
MECHANISMS["cope_elimination"] = MechanismData(
    mechanism_type="cope_elimination",
    title="Cope 제거 (Cope Elimination)",
    total_steps=2,
    overall_description=(
        "아민 옥사이드(3차 아민의 N-옥사이드)가 열적 syn-제거를 거쳐 "
        "알켄과 하이드록실아민을 생성합니다. "
        "5원 고리 전이상태(pericyclic)를 경유하는 동시(concerted) 반응."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="5원 고리 전이 상태 (syn-periplanar 배열)",
            description=(
                "N-옥사이드의 O가 β-H를 내부적으로 잡아당깁니다.\n"
                "5원 고리 전이 상태: O···H-C-C-N+ 배열.\n"
                "syn-periplanar(같은 쪽) 배열이 필요.\n"
                "Woodward-Hoffmann: 열허용 [σ2s+σ2s+π2s] 반응."
            ),
            reactant_smiles="CCC(C)[N+]([O-])(C)C",
            product_smiles="CC=CC.CN(C)O",
            arrows=[
                ArrowData("full", "bond", "β C-H 결합",
                          "atom", "N-O (산소)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=5),
                ArrowData("full", "bond", "C-N 결합",
                          "atom", "N (이탈)", "#1565C0", 0.4,
                          from_atom_idx=1, to_atom_idx=3),
            ],
            labels={"β-H": "내부 추출", "O": "수소 수용체"},
            is_transition_state=True,
            energy_label="5원 고리 TS",
            reagents="Δ (80-150°C)",
            notes="syn-제거: E2의 anti와 대비됨",
        ),
        MechanismStep(
            step_number=2,
            title="생성물: 알켄 + N,N-디알킬하이드록실아민",
            description=(
                "동시 반응 완료: C=C 이중결합 형성.\n"
                "부산물: N,N-디알킬하이드록실아민(R₂N-OH).\n"
                "Hofmann 규칙: 덜 치환된 알켄이 주생성물 (anti-Zaitsev).\n"
                "이유: 5원 고리 TS에서 sterically less hindered β-H가 선호."
            ),
            reactant_smiles="CC=CC.CN(C)O",
            product_smiles="CC=CC",
            arrows=[],
            labels={"alkene": "생성물", "hydroxylamine": "부산물"},
            energy_label="생성물",
            notes="anti-Zaitsev (Hofmann) 선택성",
        ),
    ],
    energy_diagram=[
        ("아민 옥사이드", 0.0),
        ("5원 TS", 25.0),
        ("알켄 + R₂NOH", -10.0),
    ],
)

# ─── Reductive Amination (환원적 아민화) ──────────────────────────────
# 케톤/알데히드 + 아민 → 이민 → 환원 → 아민
MECHANISMS["reductive_amination"] = MechanismData(
    mechanism_type="reductive_amination",
    title="환원적 아민화 (Reductive Amination)",
    total_steps=4,
    overall_description=(
        "카르보닐 화합물 + 1차 아민 → 이민(Schiff base) 형성 → "
        "선택적 환원제(NaBH₃CN)로 C=N 결합만 환원 → 2차 아민. "
        "C=O는 환원하지 않는 것이 핵심."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵 첨가 → 카르비놀아민 (헤미아미날)",
            description=(
                "1차 아민의 질소 론페어가 카르보닐 C를 친핵 공격.\n"
                "사면체 중간체(카르비놀아민/헤미아미날) 형성.\n"
                "산 촉매(AcOH)가 카르보닐을 활성화."
            ),
            reactant_smiles="O=C1CCCCC1",
            product_smiles="OC1(NCc2ccccc2)CCCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "N 론페어 (아민)",
                          "atom", "C=O (카르보닐)", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O π",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"amine": "친핵체", "C=O": "친전자체"},
            energy_label="친핵 첨가",
            reagents="AcOH (cat.)",
        ),
        MechanismStep(
            step_number=2,
            title="탈수 → 이민 (Schiff base)",
            description=(
                "카르비놀아민에서 물이 이탈 → C=N 이중결합 형성.\n"
                "산 촉매가 -OH 양성자화 → 좋은 이탈기(H₂O).\n"
                "Schiff base(이민) 중간체 형성."
            ),
            reactant_smiles="OC1(NCc2ccccc2)CCCCC1",
            product_smiles="C(=N/C1CCCCC1)c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-OH 결합",
                          "atom", "H₂O 이탈", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "lone_pair", "N 론페어",
                          "bond", "C=N 형성", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"imine": "Schiff base", "H₂O": "이탈"},
            energy_label="탈수",
            reagents="AcOH, mol sieves",
        ),
        MechanismStep(
            step_number=3,
            title="NaBH₃CN 선택적 환원 → 아민",
            description=(
                "NaBH₃CN의 히드라이드(H⁻)가 C=N에 전달.\n"
                "C=N 이중결합만 선택적으로 환원 (C=O는 환원 안 됨).\n"
                "NaBH₃CN의 pKa ≈ 6: pH 6-7에서 이민은 양성자화되어 반응성 증가,\n"
                "케톤 C=O는 양성자화되지 않아 환원 방지."
            ),
            reactant_smiles="C(=N/C1CCCCC1)c1ccccc1",
            product_smiles="C(NC1CCCCC1)c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "B-H (히드라이드)",
                          "atom", "C=N (이민)", "#4CAF50", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=N π",
                          "atom", "N-H", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"NaBH₃CN": "선택적 환원제", "H⁻": "히드라이드 전달"},
            energy_label="환원",
            reagents="NaBH₃CN, pH 6-7",
            notes="NaBH₄는 비선택적(C=O도 환원). NaBH(OAc)₃도 사용 가능.",
        ),
        MechanismStep(
            step_number=4,
            title="생성물: 2차 아민",
            description=(
                "최종 생성물: N-벤질시클로헥실아민 (2차 아민).\n"
                "원래 케톤이 아민으로 완전히 변환.\n"
                "합성적 등가: C=O → C-NH-R (탄소 산화 수준 유지)."
            ),
            reactant_smiles="C(NC1CCCCC1)c1ccccc1",
            product_smiles="C(c1ccccc1)NC1CCCCC1",
            arrows=[],
            labels={"amine": "최종 생성물"},
            energy_label="생성물",
            notes="one-pot 반응: 이민 형성과 환원을 동시에 진행",
        ),
    ],
    energy_diagram=[
        ("케톤 + 아민", 0.0),
        ("카르비놀아민", -3.0),
        ("이민 + H₂O", 5.0),
        ("환원 TS", 8.0),
        ("2차 아민", -15.0),
    ],
)


# ══════════════════════════════════════════════════════════════════════
# Cycle 20 Gold Standard Templates — L4 Exam Reactions (2026-03-22)
# ══════════════════════════════════════════════════════════════════════

# ─── Acyloin Condensation ────────────────────────────────────────────
MECHANISMS["acyloin_condensation"] = MechanismData(
    mechanism_type="acyloin_condensation",
    title="Acyloin 축합 (Na 환원, α-하이드록시 케톤)",
    total_steps=4,
    overall_description=(
        "디에스테르 + Na → 라디칼 음이온 → 커플링 → 1,2-디케톤 → 에네디올레이트 → α-하이드록시 케톤. "
        "TMSCl로 중간체 보호 (Rühlmann 변형). 중/대형 고리 합성."
    ),
    steps=[
        MechanismStep(step_number=1, title="Na 전자전달 → 케틸 라디칼",
            description="Na가 에스테르 C=O에 전자 전달. 케틸 라디칼 음이온 형성.",
            reactant_smiles="O=C(OCC)CCCCC(=O)OCC", product_smiles="O=C(OCC)CCCCC([O-])OCC",
            arrows=[ArrowData("half", "atom", "Na", "atom", "C=O", "#ff6600", 0.4)],
            labels={"ketyl": "라디칼 음이온"}, energy_label="SET", reagents="Na, xylene"),
        MechanismStep(step_number=2, title="라디칼 커플링 + EtO⁻ 이탈 → 디케톤",
            description="두 케틸 라디칼 C-C 커플링. 2×EtO⁻ 이탈 → 1,2-디케톤.",
            reactant_smiles="O=C(OCC)CCCCC([O-])OCC", product_smiles="O=C1CCCCC1=O",
            arrows=[ArrowData("half", "atom", "C·", "atom", "C·", "#ff6600", 0.5)],
            labels={"coupling": "C-C"}, energy_label="커플링"),
        MechanismStep(step_number=3, title="Na 환원 → 에네디올레이트",
            description="디케톤을 Na로 추가 환원 → 에네디올레이트 이음이온.",
            reactant_smiles="O=C1CCCCC1=O", product_smiles="[O-]/C1=C(\\[O-])CCCC1",
            arrows=[ArrowData("full", "atom", "Na", "atom", "C=O", "#E53935", 0.4)],
            labels={"enediolate": "이음이온"}, energy_label="환원"),
        MechanismStep(step_number=4, title="산성 가수분해 → α-하이드록시 케톤",
            description="양성자화 → 아실로인(α-하이드록시 케톤).",
            reactant_smiles="[O-]/C1=C(\\[O-])CCCC1", product_smiles="OC1CCCCC1=O",
            arrows=[], labels={"acyloin": "생성물"}, energy_label="생성물"),
    ],
    energy_diagram=[("디에스테르 + Na", 0.0), ("케틸 라디칼", 8.0), ("디케톤", -5.0),
                    ("에네디올레이트", -15.0), ("아실로인", -20.0)],
)

# ─── Thorpe-Ziegler Cyclization ──────────────────────────────────────
MECHANISMS["thorpe_ziegler"] = MechanismData(
    mechanism_type="thorpe_ziegler",
    title="Thorpe-Ziegler 고리화 (분자내 니트릴 축합)",
    total_steps=4,
    overall_description=(
        "디니트릴 + 강염기 → α-시아노 카르바니온 → 분자내 C≡N 공격 → 고리형 이민 → 토토머화."
    ),
    steps=[
        MechanismStep(step_number=1, title="탈양성자화 → α-시아노 카르바니온",
            description="NaH가 C≡N 인접 α-H 제거. pKa ≈ 25.",
            reactant_smiles="N#CCCCCCC#N", product_smiles="[CH-](C#N)CCCCC#N",
            arrows=[ArrowData("full", "lone_pair", "H⁻", "atom", "α-H", "#1565C0", 0.4)],
            labels={"carbanion": "안정화"}, energy_label="탈양성자화", reagents="NaH, THF"),
        MechanismStep(step_number=2, title="분자내 C≡N 공격 (6-exo-dig)",
            description="카르바니온이 먼 쪽 C≡N 공격. Baldwin 규칙: 6-exo-dig 허용.",
            reactant_smiles="[CH-](C#N)CCCCC#N", product_smiles="N=C1CCCCC1C#N",
            arrows=[ArrowData("full", "negative_charge", "C⁻", "atom", "C≡N", "#E53935", 0.5)],
            labels={"cyclization": "C-C 형성"}, is_transition_state=True, energy_label="TS"),
        MechanismStep(step_number=3, title="토토머화 → 에나민",
            description="이민 → 에나민 토토머화 (공액 안정화).",
            reactant_smiles="N=C1CCCCC1C#N", product_smiles="N=C1CCCCC1C#N",
            arrows=[], labels={"tautomer": "에나민"}, energy_label="토토머화"),
        MechanismStep(step_number=4, title="생성물: 2-아미노-1-시아노시클로헥센",
            description="고리형 β-아미노니트릴.",
            reactant_smiles="N=C1CCCCC1C#N", product_smiles="N=C1CCCCC1C#N",
            arrows=[], labels={"product": "생성물"}, energy_label="생성물",
            notes="Thorpe (1904), Ziegler 고희석 기법"),
    ],
    energy_diagram=[("디니트릴", 0.0), ("카르바니온", 8.0), ("고리화 TS", 18.0),
                    ("이민", -5.0), ("에나민", -12.0)],
)

# ─── Darzens Condensation ────────────────────────────────────────────
MECHANISMS["darzens_condensation"] = MechanismData(
    mechanism_type="darzens_condensation",
    title="Darzens 축합 (글리시드 에스테르, 에폭시 에스테르)",
    total_steps=4,
    overall_description=(
        "알데히드 + α-할로 에스테르 + 염기 → α-할로 에놀레이트 → 알돌 → 분자내 SN2 → 에폭시 에스테르."
    ),
    steps=[
        MechanismStep(step_number=1, title="α-클로로 에놀레이트 형성",
            description="NaOEt가 α-할로 에스테르 탈양성자화.",
            reactant_smiles="CCOC(=O)CCl", product_smiles="CCOC(=O)[CH-]Cl",
            arrows=[ArrowData("full", "lone_pair", "EtO⁻", "atom", "α-H", "#1565C0", 0.4)],
            labels={"enolate": "α-Cl"}, energy_label="탈양성자화", reagents="NaOEt"),
        MechanismStep(step_number=2, title="에놀레이트의 알데히드 공격",
            description="알돌형 C-C 결합 형성 → β-알콕사이드.",
            reactant_smiles="CCOC(=O)[CH-]Cl", product_smiles="CCOC(=O)C([O-])(c1ccccc1)CCl",
            arrows=[ArrowData("full", "negative_charge", "C⁻", "atom", "C=O", "#E53935", 0.5)],
            labels={"aldol": "C-C"}, is_transition_state=True, energy_label="TS (C-C)"),
        MechanismStep(step_number=3, title="분자내 SN2 → 에폭사이드",
            description="β-알콕사이드가 α-C의 Cl 치환 → 3원환.",
            reactant_smiles="CCOC(=O)C([O-])(c1ccccc1)CCl",
            product_smiles="CCOC(=O)C1OC1c1ccccc1",
            arrows=[ArrowData("full", "negative_charge", "O⁻", "atom", "C-Cl", "#E53935", 0.4)],
            labels={"SN2": "고리닫힘"}, energy_label="SN2"),
        MechanismStep(step_number=4, title="생성물: 글리시드 에스테르",
            description="에틸 3-페닐글리시데이트.",
            reactant_smiles="CCOC(=O)C1OC1c1ccccc1",
            product_smiles="CCOC(=O)C1OC1c1ccccc1",
            arrows=[], labels={"glycidate": "생성물"}, energy_label="생성물",
            notes="Darzens (1904)"),
    ],
    energy_diagram=[("알데히드 + ClCH₂COOEt", 0.0), ("에놀레이트", 5.0),
                    ("알돌 TS", 15.0), ("β-알콕사이드", -3.0), ("글리시데이트", -18.0)],
)

# ─── Knoevenagel Condensation ────────────────────────────────────────
MECHANISMS["knoevenagel_condensation"] = MechanismData(
    mechanism_type="knoevenagel_condensation",
    title="Knoevenagel 축합 (활성 메틸렌 + 알데히드)",
    total_steps=4,
    overall_description=(
        "알데히드 + 활성 메틸렌(말론산 등) → 탈양성자화 → 알돌 → 탈수 → α,β-불포화 산."
    ),
    steps=[
        MechanismStep(step_number=1, title="아민 촉매 탈양성자화",
            description="피페리딘이 활성 메틸렌 탈양성자화 (pKa ≈ 13).",
            reactant_smiles="OC(=O)CC(=O)O", product_smiles="[CH-](C(=O)O)C(=O)O",
            arrows=[ArrowData("full", "lone_pair", "N:", "atom", "H", "#1565C0", 0.4)],
            labels={"carbanion": "안정화"}, energy_label="탈양성자화",
            reagents="피페리딘, AcOH"),
        MechanismStep(step_number=2, title="카르바니온의 알데히드 공격",
            description="C-C 결합 형성 (알돌형).",
            reactant_smiles="[CH-](C(=O)O)C(=O)O",
            product_smiles="OC(c1ccccc1)C(C(=O)O)C(=O)O",
            arrows=[ArrowData("full", "negative_charge", "C⁻", "atom", "C=O", "#E53935", 0.5)],
            labels={"aldol": "C-C"}, is_transition_state=True, energy_label="TS"),
        MechanismStep(step_number=3, title="E1cb 탈수",
            description="β-하이드록시 → 탈수 → C=C 이중결합 형성.",
            reactant_smiles="OC(c1ccccc1)C(C(=O)O)C(=O)O",
            product_smiles="O=C(O)/C(=C/c1ccccc1)C(=O)O",
            arrows=[ArrowData("full", "bond", "C-OH", "atom", "H₂O", "#E53935", 0.3)],
            labels={"E1cb": "탈수"}, energy_label="탈수"),
        MechanismStep(step_number=4, title="생성물: 벤질리덴말론산",
            description="α,β-불포화 디카르복시산.",
            reactant_smiles="O=C(O)/C(=C/c1ccccc1)C(=O)O",
            product_smiles="O=C(O)/C(=C/c1ccccc1)C(=O)O",
            arrows=[], labels={"product": "생성물"}, energy_label="생성물",
            notes="Knoevenagel (1898)"),
    ],
    energy_diagram=[("PhCHO + 말론산", 0.0), ("카르바니온", 5.0),
                    ("알돌 TS", 13.0), ("β-OH 중간체", -2.0), ("탈수 생성물", -18.0)],
)

# ─── Baylis-Hillman Reaction ─────────────────────────────────────────
MECHANISMS["baylis_hillman"] = MechanismData(
    mechanism_type="baylis_hillman",
    title="Baylis-Hillman 반응 (DABCO 촉매, α-메틸렌-β-하이드록시 에스테르)",
    total_steps=5,
    overall_description=(
        "DABCO가 아크릴레이트 Michael 첨가 → 쯔비터이온 → 알데히드 공격 → 양자 이동 → DABCO 이탈."
    ),
    steps=[
        MechanismStep(step_number=1, title="DABCO Michael 첨가",
            description="DABCO N이 아크릴레이트 β-C 공격 (1,4-첨가). 속도결정단계.",
            reactant_smiles="C=CC(=O)OC", product_smiles="[O-]C(=C)C[N+]1(CC2)CCN2CC1",
            arrows=[ArrowData("full", "lone_pair", "N:", "atom", "β-C", "#E53935", 0.5)],
            labels={"zwitterion": "쯔비터이온"}, energy_label="RDS", reagents="DABCO"),
        MechanismStep(step_number=2, title="쯔비터이온의 알데히드 공격",
            description="에놀레이트 C가 PhCHO 공격 (알돌형).",
            reactant_smiles="[O-]C(=C)C[N+]1(CC2)CCN2CC1",
            product_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            arrows=[ArrowData("full", "negative_charge", "C⁻", "atom", "C=O", "#E53935", 0.5)],
            labels={"aldol": "C-C"}, is_transition_state=True, energy_label="TS"),
        MechanismStep(step_number=3, title="양자 이동",
            description="분자내/용매 양자 이동: 알콕사이드 양성자화 + α-탈양성자화.",
            reactant_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            product_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            arrows=[], labels={"proton_transfer": "셔틀"}, energy_label="양자이동"),
        MechanismStep(step_number=4, title="DABCO E1cb 이탈",
            description="DABCO 이탈 → 촉매 재생 + 엑소사이클릭 C=C.",
            reactant_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            product_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            arrows=[], labels={"elimination": "DABCO 이탈"}, energy_label="촉매재생"),
        MechanismStep(step_number=5, title="생성물: α-메틸렌-β-하이드록시 에스테르",
            description="Baylis-Hillman 생성물.",
            reactant_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            product_smiles="OC(c1ccccc1)C(=C)C(=O)OC",
            arrows=[], labels={"product": "생성물"}, energy_label="생성물",
            notes="Baylis & Hillman (1972)"),
    ],
    energy_diagram=[("아크릴레이트 + PhCHO", 0.0), ("DABCO 첨가 TS", 20.0),
                    ("쯔비터이온", 10.0), ("알돌 TS", 22.0), ("양자이동", 5.0),
                    ("생성물", -8.0)],
)

# ─── Staudinger Ligation ─────────────────────────────────────────────
MECHANISMS["staudinger_ligation"] = MechanismData(
    mechanism_type="staudinger_ligation",
    title="Staudinger 반응 (아지드 + 포스핀 → 아민)",
    total_steps=4,
    overall_description=(
        "유기 아지드 + PPh₃ → 포스파지드 → N₂ 이탈 → 이미노포스포란 → 가수분해 → 아민 + OPPh₃."
    ),
    steps=[
        MechanismStep(step_number=1, title="PPh₃ → 아지드 말단 N 공격",
            description="P(III) 친핵체가 아지드 말단 N 공격.",
            reactant_smiles="c1ccc(cc1)[N-][N+]#N",
            product_smiles="c1ccc(cc1)N=NN=P(c1ccccc1)(c1ccccc1)c1ccccc1",
            arrows=[ArrowData("full", "lone_pair", "P:", "atom", "N(terminal)", "#E53935", 0.5)],
            labels={"phosphazide": "중간체"}, energy_label="친핵공격", reagents="PPh₃"),
        MechanismStep(step_number=2, title="N₂ 이탈 → 이미노포스포란",
            description="역 [2+3] → N₂ 방출 (ΔG ≈ −50 kcal/mol).",
            reactant_smiles="c1ccc(cc1)N=NN=P(c1ccccc1)(c1ccccc1)c1ccccc1",
            product_smiles="c1ccc(cc1)/N=P(c1ccccc1)(c1ccccc1)c1ccccc1",
            arrows=[ArrowData("full", "bond", "N-N", "atom", "N₂", "#E53935", 0.4)],
            labels={"N2_loss": "구동력"}, energy_label="N₂ 이탈"),
        MechanismStep(step_number=3, title="H₂O 가수분해: P=N 절단",
            description="물이 P=N 가수분해. 강한 P=O 결합 형성.",
            reactant_smiles="c1ccc(cc1)/N=P(c1ccccc1)(c1ccccc1)c1ccccc1",
            product_smiles="Nc1ccccc1",
            arrows=[ArrowData("full", "lone_pair", "O(H₂O)", "atom", "P", "#1565C0", 0.4)],
            labels={"hydrolysis": "P=O 형성"}, energy_label="가수분해", reagents="H₂O"),
        MechanismStep(step_number=4, title="생성물: 아닐린 + OPPh₃",
            description="1차 아민 + 트리페닐포스핀 옥사이드.",
            reactant_smiles="Nc1ccccc1", product_smiles="Nc1ccccc1",
            arrows=[], labels={"amine": "생성물"}, energy_label="생성물",
            notes="Staudinger (1919). Bertozzi: 생체직교 결찰."),
    ],
    energy_diagram=[("PhN₃ + PPh₃", 0.0), ("포스파지드", -10.0),
                    ("이미노포스포란 + N₂", -45.0), ("아닐린 + OPPh₃", -60.0)],
)

# ─── Kulinkovich Reaction ────────────────────────────────────────────
MECHANISMS["kulinkovich_reaction"] = MechanismData(
    mechanism_type="kulinkovich_reaction",
    title="Kulinkovich 반응 (에스테르 → 시클로프로판올)",
    total_steps=4,
    overall_description=(
        "Ti(OiPr)₄ + EtMgBr → 티타나시클로프로판 → 에스테르 C=O 삽입 → 고리 수축 → 시클로프로판올."
    ),
    steps=[
        MechanismStep(step_number=1, title="티타나시클로프로판 형성",
            description="2 EtMgBr + Ti(OiPr)₄ → β-H 이탈 → Ti(II) 메탈라사이클.",
            reactant_smiles="CC", product_smiles="C1C[Ti]1",
            arrows=[ArrowData("full", "bond", "C-Ti", "atom", "Ti", "#E53935", 0.4)],
            labels={"titanacyclo": "Ti(II)"}, energy_label="메탈라사이클",
            reagents="Ti(OiPr)₄, EtMgBr"),
        MechanismStep(step_number=2, title="에스테르 C=O 삽입",
            description="Ti가 에스테르 O에 배위 → C-C가 C=O 공격.",
            reactant_smiles="CC(=O)OCC", product_smiles="CC1(OCC)CC1[O-]",
            arrows=[ArrowData("full", "bond", "C-C(ring)", "atom", "C=O", "#E53935", 0.5)],
            labels={"insertion": "C=O"}, is_transition_state=True, energy_label="삽입 TS"),
        MechanismStep(step_number=3, title="고리 수축 → 시클로프로판",
            description="알콕사이드가 C-Ti 치환 → 3원환.",
            reactant_smiles="CC1(OCC)CC1[O-]", product_smiles="OC1(C)CC1",
            arrows=[ArrowData("full", "negative_charge", "O⁻", "atom", "C-Ti", "#E53935", 0.4)],
            labels={"contraction": "SN2"}, energy_label="고리수축"),
        MechanismStep(step_number=4, title="생성물: 1-메틸시클로프로판올",
            description="시클로프로판올 (형식적 [1+2] C=O 첨가).",
            reactant_smiles="OC1(C)CC1", product_smiles="OC1(C)CC1",
            arrows=[], labels={"product": "생성물"}, energy_label="생성물",
            notes="Kulinkovich (1989)"),
    ],
    energy_diagram=[("에스테르 + EtMgBr + Ti", 0.0), ("티타나시클로프로판", -5.0),
                    ("삽입 TS", 12.0), ("옥사티타나", -8.0), ("시클로프로판올", -22.0)],
)

# ─── Trost Allylation ────────────────────────────────────────────────
MECHANISMS["trost_allylation"] = MechanismData(
    mechanism_type="trost_allylation",
    title="Trost 비대칭 알릴화 (Pd 촉매, 연성 친핵체)",
    total_steps=4,
    overall_description=(
        "Pd(0) + 알릴 아세테이트 → π-알릴 Pd(II) → 연성 친핵체 공격 → 환원적 이탈 → Pd(0) 재생."
    ),
    steps=[
        MechanismStep(step_number=1, title="산화적 첨가 → π-알릴 Pd 착물",
            description="Pd(0)이 C-OAc 산화적 첨가. η³-알릴 + AcO⁻.",
            reactant_smiles="C=CCOC(=O)C", product_smiles="C=CC.[Pd]",
            arrows=[ArrowData("full", "lone_pair", "Pd(0)", "atom", "C-OAc", "#E53935", 0.5)],
            labels={"pi-allyl": "Pd(II)"}, energy_label="산화적첨가",
            reagents="Pd(PPh₃)₄"),
        MechanismStep(step_number=2, title="말론산 디메틸 탈양성자화",
            description="NaH가 활성 메틸렌 탈양성자화 (pKa ≈ 13).",
            reactant_smiles="COC(=O)CC(=O)OC", product_smiles="[CH-](C(=O)OC)C(=O)OC",
            arrows=[ArrowData("full", "lone_pair", "H⁻", "atom", "α-H", "#1565C0", 0.4)],
            labels={"malonate": "카르바니온"}, energy_label="탈양성자화", reagents="NaH"),
        MechanismStep(step_number=3, title="친핵공격 + 환원적 이탈",
            description="말론산 음이온이 π-알릴 말단 C 공격. Pd(0) 재생.",
            reactant_smiles="[CH-](C(=O)OC)C(=O)OC",
            product_smiles="C=CCC(C(=O)OC)C(=O)OC",
            arrows=[ArrowData("full", "negative_charge", "C⁻", "atom", "π-allyl", "#E53935", 0.5)],
            labels={"RE": "환원적이탈"}, is_transition_state=True, energy_label="TS"),
        MechanismStep(step_number=4, title="생성물: 알릴 디메틸 말로네이트",
            description="알릴화 생성물. Pd(0) 촉매 순환 완결.",
            reactant_smiles="C=CCC(C(=O)OC)C(=O)OC",
            product_smiles="C=CCC(C(=O)OC)C(=O)OC",
            arrows=[], labels={"product": "생성물"}, energy_label="생성물",
            notes="Barry Trost, Stanford. DPPBA 키랄 리간드."),
    ],
    energy_diagram=[("알릴 OAc + 말론산", 0.0), ("π-알릴 Pd", 5.0),
                    ("친핵공격 TS", 15.0), ("생성물 + Pd(0)", -12.0)],
)

# ─── Mukaiyama Aldol ─────────────────────────────────────────────────
MECHANISMS["mukaiyama_aldol"] = MechanismData(
    mechanism_type="mukaiyama_aldol",
    title="Mukaiyama 알돌 (Lewis산 + 실릴 에놀 에테르)",
    total_steps=4,
    overall_description=(
        "TiCl₄ + 알데히드 → 활성화 → 실릴 에놀 에테르 공격 → β-하이드록시 케톤."
    ),
    steps=[
        MechanismStep(step_number=1, title="TiCl₄ → 알데히드 활성화",
            description="Lewis산 TiCl₄가 알데히드 O에 배위 → C=O 전기양성도 증가.",
            reactant_smiles="O=Cc1ccccc1", product_smiles="O=Cc1ccccc1.[Ti](Cl)(Cl)(Cl)Cl",
            arrows=[ArrowData("full", "lone_pair", "O:", "atom", "Ti", "#1565C0", 0.4)],
            labels={"activation": "Lewis산"}, energy_label="배위",
            reagents="TiCl₄, CH₂Cl₂, −78 °C"),
        MechanismStep(step_number=2, title="실릴 에놀 에테르 공격",
            description="TMS 에놀 에테르 C-친핵체가 활성화된 알데히드 공격.",
            reactant_smiles="O=Cc1ccccc1.[Ti](Cl)(Cl)(Cl)Cl",
            product_smiles="[O-]C(c1ccccc1)CC(=O)C",
            arrows=[ArrowData("full", "pi_bond", "C=C(enol)", "atom", "C=O", "#E53935", 0.5)],
            labels={"C-C": "알돌"}, is_transition_state=True, energy_label="TS (C-C)"),
        MechanismStep(step_number=3, title="수계 후처리",
            description="Ti-O, Si-O 결합 절단. 알콕사이드 양성자화.",
            reactant_smiles="[O-]C(c1ccccc1)CC(=O)C",
            product_smiles="OC(c1ccccc1)CC(=O)C",
            arrows=[ArrowData("full", "lone_pair", "H₂O", "atom", "O⁻", "#1565C0", 0.3)],
            labels={"workup": "양성자화"}, energy_label="후처리"),
        MechanismStep(step_number=4, title="생성물: β-하이드록시 케톤",
            description="교차 알돌 생성물. 자기축합 없음.",
            reactant_smiles="OC(c1ccccc1)CC(=O)C",
            product_smiles="OC(c1ccccc1)CC(=O)C",
            arrows=[], labels={"product": "생성물"}, energy_label="생성물",
            notes="Mukaiyama (1973). 촉매적: Kobayashi Zr/Cu."),
    ],
    energy_diagram=[("PhCHO + TMS enol ether", 0.0), ("TiCl₄ 활성화", -5.0),
                    ("C-C TS", 10.0), ("β-하이드록시 케톤", -15.0)],
)


# ─── Robinson Annulation (Michael 첨가 + 분자 내 Aldol 축합) ─────────────
# 대표 반응: Cyclohex-2-enone + MVK (NaOH) → 2-Decalone 유도체
# Robinson Annulation = Michael Addition + Intramolecular Aldol Condensation
# 14단계 상세 메커니즘

MECHANISMS["robinson_annulation"] = MechanismData(
    mechanism_type="robinson_annulation",
    title="Robinson Annulation (고리 형성 반응)",
    total_steps=14,
    overall_description=(
        "Robinson Annulation은 Michael 1,4-공역 첨가와 분자 내 Aldol 축합이 "
        "연속적으로 일어나 새로운 6원 고리를 형성하는 반응입니다. "
        "Cyclohex-2-enone과 MVK(methyl vinyl ketone)가 NaOH 존재 하에 "
        "1,5-디케톤 중간체를 거쳐 α,β-불포화 데칼론(Wieland-Miescher 케톤 골격)을 "
        "생성합니다. 스테로이드 전합성의 핵심 반응(Robinson, 1935)."
    ),
    steps=[
        # Phase I: Michael Addition (Steps 1-5)
        MechanismStep(
            step_number=1,
            title="NaOH에 의한 Cyclohex-2-enone α-H 탈양성자화 → 에놀레이트",
            description=(
                "NaOH가 cyclohex-2-enone의 α-수소를 제거합니다.\n"
                "카르보닐 α-위치의 pKa ~20으로, NaOH(pKa 15.7)가 충분히 탈양성자화 가능.\n"
                "생성된 에놀레이트 이온은 음전하가 산소와 α-탄소에 비편재화됩니다."
            ),
            # O=C1CC=CCC1: cyclohex-2-enone
            # idx: O0=C1-C2(H)-C3=C4-C5(H2)-C6(H2)
            reactant_smiles="O=C1CC=CCC1",
            product_smiles="[O-]C1=CC=CCC1",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ (염기)",
                          "atom", "α-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=2),  # OH⁻ → α-H
                ArrowData("full", "bond", "C-H σ결합",
                          "bond", "C=O → C-O⁻", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=1),  # C-H → enolate
            ],
            labels={"OH-": "염기", "H": "α-H (pKa ~20)"},
            energy_label="에놀레이트 형성",
            reagents="NaOH, H₂O/EtOH",
        ),
        MechanismStep(
            step_number=2,
            title="에놀레이트 공명 안정화 (C=C-C=O ↔ C-C=C-O⁻)",
            description=(
                "에놀레이트 이온의 음전하가 공명으로 비편재화됩니다.\n"
                "공명 구조 ①: C α에 음전하 (C⁻-C=O)\n"
                "공명 구조 ②: O에 음전하 (C=C-O⁻)\n"
                "α-탄소의 친핵성이 증가하여 Michael donor로 활성화됩니다."
            ),
            reactant_smiles="[O-]C1=CC=CCC1",
            product_smiles="[O-]C1=CC=CCC1",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π (공명 이동)",
                          "atom", "O⁻ (공명 기여자)", "#FF9800", 0.4,
                          from_atom_idx=3, to_atom_idx=0),  # C=C → C-O⁻
            ],
            labels={"resonance": "공명 안정화", "C-": "친핵성 α-C"},
            energy_label="공명 안정화 (ΔG < 0)",
            reagents="",
            notes="HOMO 계수: α-탄소 > 산소 → 탄소 친핵체(kinetic control).",
        ),
        MechanismStep(
            step_number=3,
            title="에놀레이트 1,4-공역 첨가 → MVK β-탄소 공격 (Michael 첨가)",
            description=(
                "에놀레이트의 α-탄소가 MVK(methyl vinyl ketone)의 β-탄소를 공격합니다.\n"
                "1,4-공역 첨가: 전자가 C→C=C-C=O 4원자 경로를 따라 이동.\n"
                "새 C-C σ결합이 형성되며, MVK의 카르보닐 산소에 음전하 전달.\n"
                "이것이 Robinson Annulation의 첫 번째 핵심 단계입니다."
            ),
            # Enolate + MVK
            reactant_smiles="[O-]C1=CC=CCC1.C=CC(C)=O",
            product_smiles="O=C1CC=CCC1CCC(C)=O",
            arrows=[
                ArrowData("full", "negative_charge", "에놀레이트 C⁻ (α-탄소)",
                          "atom", "MVK β-C", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=8),  # α-C → β-C(MVK)
                ArrowData("full", "pi_bond", "C=C π (MVK α-β)",
                          "bond", "C-C σ 형성", "#FF9800", 0.4,
                          from_atom_idx=8, to_atom_idx=9),  # β=α → β-α
                ArrowData("full", "pi_bond", "C=O 재배열 (MVK)",
                          "atom", "O⁻ (에놀레이트 산소)", "#1565C0", 0.4,
                          from_atom_idx=9, to_atom_idx=10),  # C=O → C-O⁻
            ],
            labels={"donor": "Michael donor (에놀레이트)", "β": "β-C (공격점)"},
            is_transition_state=True,
            energy_label="1,4-첨가 전이 상태 (ΔG‡ ~15 kcal/mol)",
            reagents="",
            notes="Michael 첨가: kinetic control → 1,4-첨가 우세 (vs 1,2-첨가).",
        ),
        MechanismStep(
            step_number=4,
            title="용매로부터 양성자 전달 → 1,5-디케톤 중간체 형성",
            description=(
                "Michael 첨가 생성물의 에놀레이트 산소가 용매(H₂O)로부터 양성자화됩니다.\n"
                "에놀레이트 → 케톤 (tautomerization).\n"
                "1,5-디케톤 중간체가 생성됩니다."
            ),
            reactant_smiles="O=C1CC=CCC1CCC(C)=O",
            product_smiles="O=C1CC=CCC1CCC(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (양성자원)",
                          "atom", "O⁻ → OH → C=O", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=0),  # H⁺ → O
            ],
            labels={"protonation": "양성자화", "1,5-diketone": "1,5-디케톤"},
            energy_label="양성자 전달 (발열)",
            reagents="H₂O (용매)",
        ),
        MechanismStep(
            step_number=5,
            title="1,5-디케톤의 호변이성질체 평형 (케토-에놀)",
            description=(
                "1,5-디케톤의 α-수소 사이에서 케토-에놀 호변이성질체 평형이 존재합니다.\n"
                "두 카르보닐 사이의 메틸렌 수소(pKa ~11)는 산성도가 높아\n"
                "다음 단계의 분자 내 알돌 반응을 위한 전구체 역할을 합니다."
            ),
            reactant_smiles="O=C1CC=CCC1CCC(C)=O",
            product_smiles="O=C1CC=CCC1CCC(C)=O",
            arrows=[
                ArrowData("full", "bond", "C-H (케토형)",
                          "pi_bond", "C=C (에놀형)", "#FF9800", 0.3,
                          from_atom_idx=7, to_atom_idx=8),  # keto-enol
            ],
            labels={"tautomer": "호변이성질체 평형"},
            energy_label="평형 상태",
            reagents="",
            notes="두 카르보닐 사이 메틸렌 pKa ~11 (활성 메틸렌).",
        ),
        # Phase II: Intramolecular Aldol Condensation (Steps 6-14)
        MechanismStep(
            step_number=6,
            title="NaOH에 의한 두 카르보닐 사이 α-H 탈양성자화",
            description=(
                "NaOH가 1,5-디케톤의 두 카르보닐 사이 메틸렌 수소를 제거합니다.\n"
                "이 위치는 양쪽 카르보닐에 의해 안정화되어 pKa ~11로 매우 산성.\n"
                "분자 내 Aldol 반응의 시작점."
            ),
            reactant_smiles="O=C1CC=CCC1CCC(C)=O",
            product_smiles="O=C1CC=CCC1C[CH-]C(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻",
                          "atom", "α-H (디카르보닐 사이)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=8),  # OH⁻ → H
                ArrowData("full", "bond", "C-H σ",
                          "bond", "C-C=O (에놀레이트화)", "#4CAF50", 0.3,
                          from_atom_idx=8, to_atom_idx=9),  # C-H → enolate
            ],
            labels={"H": "α-H (pKa ~11)", "base": "NaOH"},
            energy_label="탈양성자화",
            reagents="NaOH",
        ),
        MechanismStep(
            step_number=7,
            title="새 에놀레이트 형성 (kinetic vs thermodynamic control)",
            description=(
                "새로운 에놀레이트가 형성됩니다.\n"
                "Kinetic enolate: 덜 치환된 쪽 (접근 가능한 H)\n"
                "Thermodynamic enolate: 더 치환된 쪽 (더 안정)\n"
                "NaOH는 열역학적 조건 → thermodynamic enolate 선호."
            ),
            reactant_smiles="O=C1CC=CCC1C[CH-]C(C)=O",
            product_smiles="O=C1CC=CCC1CC(=CC)O",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻ (음전하)",
                          "pi_bond", "C=O (공명 안정화)", "#1565C0", 0.4,
                          from_atom_idx=8, to_atom_idx=9),  # C⁻ → C=O
            ],
            labels={"kinetic": "kinetic enolate", "thermo": "thermodynamic enolate"},
            energy_label="에놀레이트 (공명 안정화)",
            reagents="",
            notes="NaOH 조건: 가역적 탈양성자화 → thermodynamic control.",
        ),
        MechanismStep(
            step_number=8,
            title="분자 내 Aldol 반응 — 에놀레이트가 인접 C=O 공격",
            description=(
                "에놀레이트의 α-탄소가 같은 분자 내 다른 카르보닐(C=O)을 친핵 공격합니다.\n"
                "6-exo-trig 고리화 (Baldwin's rules: 유리).\n"
                "새 C-C 결합 형성 → 6원 고리 골격 완성."
            ),
            reactant_smiles="O=C1CC=CCC1C[CH-]C(C)=O",
            product_smiles="O=C1CC=CCC1(O)CC(C)=O",
            arrows=[
                ArrowData("full", "negative_charge", "에놀레이트 C⁻",
                          "atom", "C=O (카르보닐 탄소)", "#E53935", 0.5,
                          from_atom_idx=8, to_atom_idx=1),  # C⁻ → C=O
                ArrowData("full", "pi_bond", "C=O π",
                          "atom", "O⁻ (알콕사이드)", "#1565C0", 0.4,
                          from_atom_idx=1, to_atom_idx=0),  # C=O → C-O⁻
            ],
            labels={"C-C": "새 C-C 결합", "6-exo": "6-exo-trig (Baldwin 유리)"},
            is_transition_state=True,
            energy_label="Aldol TS (ΔG‡ ~12 kcal/mol)",
            reagents="",
            notes="분자 내 반응: 유효 몰농도 매우 높음 → 분자 간 반응 대비 유리.",
        ),
        MechanismStep(
            step_number=9,
            title="사면체 중간체 형성 (C-O⁻ 알콕사이드)",
            description=(
                "카르보닐 탄소가 sp3 혼성화로 전환됩니다.\n"
                "산소에 음전하가 위치한 사면체 중간체(알콕사이드) 형성.\n"
                "새 6원 고리의 C-C 결합이 완성된 상태."
            ),
            reactant_smiles="O=C1CC=CCC1(O)CC(C)=O",
            product_smiles="[O-]C1(CC(C)=O)CC=CCC1",
            arrows=[
                ArrowData("full", "pi_bond", "C=O → C-O⁻",
                          "atom", "O⁻ (사면체 중간체)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),  # C=O → C-O⁻
            ],
            labels={"tetrahedral": "사면체 중간체", "O-": "알콕사이드"},
            energy_label="사면체 중간체",
            reagents="",
        ),
        MechanismStep(
            step_number=10,
            title="알콕사이드 양성자화 → β-하이드록시케톤 (Aldol 생성물)",
            description=(
                "알콕사이드(C-O⁻)가 용매로부터 양성자화됩니다.\n"
                "β-하이드록시케톤이 형성됩니다 (Aldol 생성물).\n"
                "아직 탈수가 일어나지 않은 상태."
            ),
            reactant_smiles="[O-]C1(CC(C)=O)CC=CCC1",
            product_smiles="OC1(CC(C)=O)CC=CCC1",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (양성자원)",
                          "atom", "O⁻ → OH", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=0),  # H⁺ → O⁻
            ],
            labels={"β-OH": "β-하이드록시케톤"},
            energy_label="양성자화 (발열)",
            reagents="H₂O",
        ),
        MechanismStep(
            step_number=11,
            title="NaOH에 의한 α-H 탈양성자화 (C-OH 인접 위치)",
            description=(
                "NaOH가 β-하이드록시케톤의 α-수소를 제거합니다.\n"
                "하이드록시기 인접 탄소의 C-H 결합이 끊어지면서\n"
                "E1cb 탈거 반응의 전구체 에놀레이트가 형성됩니다."
            ),
            reactant_smiles="OC1(CC(C)=O)CC=CCC1",
            product_smiles="OC1([CH-]C(C)=O)CC=CCC1",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ (염기)",
                          "atom", "α-H (C-OH 인접)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=2),  # OH⁻ → H
                ArrowData("full", "bond", "C-H σ",
                          "bond", "C=C (에놀레이트화)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # C-H → enolate
            ],
            labels={"H": "α-H", "E1cb": "E1cb 전구체"},
            energy_label="탈양성자화",
            reagents="NaOH",
        ),
        MechanismStep(
            step_number=12,
            title="E1cb 탈거 — 하이드록사이드 이탈",
            description=(
                "E1cb(unimolecular conjugate base) 메커니즘으로 탈수가 진행됩니다.\n"
                "에놀레이트 중간체에서 β-위치의 -OH가 이탈기로 작용.\n"
                "음전하가 카르보닐로 밀려나면서 OH⁻가 이탈합니다.\n"
                "E1cb는 이탈기가 좋지 않은 경우(OH)에 유리한 메커니즘."
            ),
            reactant_smiles="OC1([CH-]C(C)=O)CC=CCC1",
            product_smiles="O=C(/C=C\\1CC=CC1)C",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻ (에놀레이트)",
                          "bond", "C-OH (이탈기)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=1),  # C⁻ → C-OH
                ArrowData("full", "bond", "C-O σ (이탈)",
                          "atom", "OH⁻ (이탈기)", "#1565C0", 0.4,
                          from_atom_idx=1, to_atom_idx=0),  # C-O → OH⁻
            ],
            labels={"E1cb": "E1cb 탈거", "OH": "이탈기"},
            is_transition_state=True,
            energy_label="E1cb 전이 상태",
            reagents="",
            notes="E1cb vs E2: OH⁻는 나쁜 이탈기 → E1cb (단계적 탈거) 우세.",
        ),
        MechanismStep(
            step_number=13,
            title="α,β-불포화 에논 형성 (공역계 확장)",
            description=(
                "탈수 완료: C=C 이중결합이 형성되며 카르보닐과 공역합니다.\n"
                "공역된 α,β-불포화 에논 시스템(C=C-C=O)이 형성됩니다.\n"
                "이 공역계는 UV-Vis 흡수에서 확인 가능(약 240 nm).\n"
                "열역학적으로 매우 안정한 구조."
            ),
            reactant_smiles="O=C(/C=C\\1CC=CC1)C",
            product_smiles="O=C1CCC2=CC(=O)CCC2C1",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π (공역)",
                          "pi_bond", "C=O π (공역 확장)", "#FF9800", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # conjugation
            ],
            labels={"conjugation": "공역계 형성", "enone": "α,β-불포화 에논"},
            energy_label="공역 안정화 (ΔG ~-5 kcal/mol)",
            reagents="",
        ),
        MechanismStep(
            step_number=14,
            title="최종 생성물: 2-Decalone 유도체 (Wieland-Miescher 골격)",
            description=(
                "Robinson Annulation 최종 생성물.\n"
                "Octalin-1,6-dione (trans-2-decalone 유도체) 골격이 형성되었습니다.\n"
                "이 구조는 Wieland-Miescher 케톤의 기본 골격으로,\n"
                "스테로이드(콜레스테롤, 테스토스테론 등) 전합성의 핵심 중간체입니다.\n"
                "Robinson(1935)이 개발, Woodward의 전합성에서 핵심적 활용."
            ),
            reactant_smiles="O=C1CCC2=CC(=O)CCC2C1",
            product_smiles="O=C1CCC2=CC(=O)CCC2C1",
            arrows=[],
            labels={
                "product": "Robinson Annulation 생성물",
                "decalone": "2-Decalone 유도체",
                "steroid": "스테로이드 전합성 핵심 골격",
            },
            energy_label="최종 생성물 (ΔG ~-25 kcal/mol)",
            reagents="",
            notes=(
                "Robinson Annulation (Sir Robert Robinson, 1935).\n"
                "응용: Wieland-Miescher ketone, Hajos-Parrish ketone (비대칭 촉매).\n"
                "스테로이드/테르페노이드 전합성의 핵심 전략."
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\nCyclohex-2-enone\n+ MVK + NaOH", 0.0),
        ("에놀레이트\n(Step 1-2)", 5.0),
        ("Michael 첨가 TS\n(Step 3)", 18.0),
        ("1,5-디케톤\n(Step 4-5)", -5.0),
        ("에놀레이트 2\n(Step 6-7)", 2.0),
        ("Aldol TS\n(Step 8)", 14.0),
        ("β-하이드록시케톤\n(Step 9-10)", -3.0),
        ("E1cb TS\n(Step 11-12)", 10.0),
        ("α,β-불포화 에논\n(Step 13)", -15.0),
        ("최종 생성물\n2-Decalone", -25.0),
    ],
)

# ─── SWERN OXIDATION ────────────────────────────────────────────────────────
# 대표 반응: R-CH2OH + DMSO / (COCl)2 / Et3N -> R-CHO + DMS + CO + CO2

MECHANISMS["swern_oxidation"] = MechanismData(
    mechanism_type="swern_oxidation",
    title="Swern 산화 (Swern Oxidation)",
    total_steps=12,
    overall_description=(
        "Swern 산화는 1차/2차 알코올을 각각 알데히드/케톤으로 온화하게 산화하는 반응입니다. "
        "DMSO를 산화제로 사용하며 옥살릴 클로라이드로 활성화합니다. "
        "-78 degC 저온 조건에서 수행하여 과산화(over-oxidation)를 방지합니다. "
        "Cr(VI) 기반 산화제(Jones, PCC)와 달리 중금속 부산물이 없어 "
        "독성/환경 문제가 적고, 에피머화 없이 온화한 조건에서 진행됩니다. "
        "최종 단계에서 Et3N 염기가 분자내 [2,3]-시그마트로픽 제거를 유도하여 "
        "C=O 이중결합과 DMS 부산물을 생성합니다."
    ),
    steps=[
        # Step 1: DMSO + oxalyl chloride -> activated complex
        MechanismStep(
            step_number=1,
            title="옥살릴 클로라이드에 의한 DMSO 활성화 개시",
            description=(
                "DMSO의 산소 론페어가 옥살릴 클로라이드의 친전자성 카르보닐 탄소(C=O)를 공격합니다.\n"
                "DMSO 산소는 풍부한 론페어를 가진 친핵체이고, 옥살릴 클로라이드의 C=O 탄소는\n"
                "두 Cl 원자의 전자 끌기 효과로 강한 친전자체입니다.\n"
                "반응 온도: -78 degC (드라이아이스/아세톤 배스)."
            ),
            reactant_smiles="CS(C)=O.ClC(=O)C(=O)Cl",
            product_smiles="CS(C)(=O)OC(=O)C(=O)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "DMSO S=O 론페어",
                          "atom", "C=O (옥살릴 클로라이드)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=5),
            ],
            labels={"O": "친핵체 (DMSO)", "C=O": "친전자체"},
            energy_label="활성화 에너지",
            reagents="(COCl)2, -78 degC, CH2Cl2",
            notes="DMSO 산소가 친핵체로 작용. 저온 필수(-78 degC).",
        ),
        # Step 2: Tetrahedral intermediate formation
        MechanismStep(
            step_number=2,
            title="사면체 중간체 형성",
            description=(
                "DMSO 산소가 옥살릴 클로라이드 카르보닐에 첨가되어\n"
                "사면체 중간체(tetrahedral intermediate)가 형성됩니다.\n"
                "카르보닐 C=O pi 결합 전자쌍이 산소로 이동하여 알콕사이드를 형성합니다."
            ),
            reactant_smiles="CS(C)(=O)OC(=O)C(=O)Cl",
            product_smiles="CS(C)(=O)OC(=O)C(=O)Cl",
            arrows=[
                ArrowData("full", "pi_bond", "C=O pi 결합",
                          "atom", "O (알콕사이드)", "#1565C0", 0.3,
                          from_atom_idx=5, to_atom_idx=6),
            ],
            labels={"C": "사면체 중간체"},
            energy_label="사면체 중간체",
            notes="친핵성 아실 치환 메커니즘의 전형적 사면체 중간체",
        ),
        # Step 3: Collapse -> chlorosulfonium + CO + CO2 + Cl-
        MechanismStep(
            step_number=3,
            title="사면체 붕괴 -> 클로로술포늄 이온 + CO + CO2",
            description=(
                "사면체 중간체가 붕괴합니다. Cl-가 이탈기로 떠나면서\n"
                "옥살릴 부분이 분해되어 CO와 CO2 기체를 방출합니다.\n"
                "황 원자에 클로라이드가 결합한 클로로술포늄 이온 [Me2S+-Cl]이 형성됩니다.\n"
                "기체 방출(CO, CO2)이 반응의 비가역성 구동력입니다."
            ),
            reactant_smiles="CS(C)(=O)OC(=O)C(=O)Cl",
            product_smiles="C[S+](C)Cl.[O-]C(=O)C=O",
            arrows=[
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl- (이탈기)", "#E53935", 0.3,
                          from_atom_idx=9, to_atom_idx=9),
                ArrowData("full", "bond", "O-C 결합 (옥살릴)",
                          "atom", "S+ (클로로술포늄)", "#4CAF50", 0.4,
                          from_atom_idx=3, to_atom_idx=0),
            ],
            labels={"S": "S+ (술포늄)", "Cl": "Cl-"},
            energy_label="발열 단계",
            reagents="CO(g) + CO2(g) 방출",
            notes="CO/CO2 기체 방출이 반응 구동력. Le Chatelier 원리.",
        ),
        # Step 4: Alcohol attacks sulfonium
        MechanismStep(
            step_number=4,
            title="알코올의 술포늄 이온 공격",
            description=(
                "기질 알코올(R-CH2-OH)의 산소 론페어가 클로로술포늄 이온의\n"
                "양전하를 띤 황(S+)을 친핵 공격합니다.\n"
                "알코올 산소는 풍부한 론페어를 가진 친핵체이며,\n"
                "S+는 강한 친전자체입니다."
            ),
            reactant_smiles="C[S+](C)Cl.CCO",
            product_smiles="C[S+](C)(OCC)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "R-OH 론페어",
                          "atom", "S+ (술포늄)", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=1),
            ],
            labels={"O": "친핵체 (알코올)", "S+": "친전자체"},
            energy_label="",
            notes="알코올 산소의 론페어가 S+의 빈 오비탈을 공격",
        ),
        # Step 5: Alkoxysulfonium salt formation
        MechanismStep(
            step_number=5,
            title="알콕시술포늄 염 형성",
            description=(
                "알코올 산소와 황 사이에 새로운 O-S 결합이 형성됩니다.\n"
                "알콕시술포늄 염([R-CH2-O-SMe2]+)이 생성됩니다.\n"
                "이 중간체는 다음 단계의 핵심 전구체입니다."
            ),
            reactant_smiles="C[S+](C)(OCC)Cl",
            product_smiles="C[S+](C)OCC.[Cl-]",
            arrows=[
                ArrowData("full", "bond", "S-Cl 결합",
                          "atom", "Cl- (이탈)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=3),
            ],
            labels={"S": "알콕시술포늄"},
            energy_label="알콕시술포늄 중간체",
            notes="S-Cl 결합 이종 개열, Cl- 이탈",
        ),
        # Step 6: Chloride departure
        MechanismStep(
            step_number=6,
            title="클로라이드 이온 완전 이탈",
            description=(
                "클로라이드 이온(Cl-)이 완전히 이탈하여 자유 이온이 됩니다.\n"
                "알콕시술포늄 양이온이 안정한 중간체로 존재합니다.\n"
                "이 단계에서 Cl-는 반응 혼합물에서 카운터이온으로 존재합니다."
            ),
            reactant_smiles="C[S+](C)OCC.[Cl-]",
            product_smiles="C[S+](C)OCC.[Cl-]",
            arrows=[],
            labels={"Cl-": "카운터이온"},
            energy_label="안정한 중간체",
            notes="Cl- 이탈 완료. 알콕시술포늄 양이온 확인.",
        ),
        # Step 7: Et3N deprotonates alpha-carbon
        MechanismStep(
            step_number=7,
            title="Et3N에 의한 alpha-탄소 탈양성자화",
            description=(
                "트리에틸아민(Et3N)이 알콕시술포늄 중간체의 alpha-탄소에서\n"
                "양성자(H)를 제거합니다. Et3N은 비친핵성 유기 염기로,\n"
                "alpha-C-H 결합의 pKa(~20)보다 강한 염기성(pKa ~11 공액산)은 아니지만\n"
                "반응 조건(-78 degC)에서 분자내 제거가 열역학적으로 유리하여 진행됩니다."
            ),
            reactant_smiles="CCN(CC)CC.C[S+](C)OCC",
            product_smiles="CC[NH+](CC)CC.[CH-]=CO[S+](C)C",
            arrows=[
                ArrowData("full", "lone_pair", "Et3N 론페어",
                          "atom", "alpha-H", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=12),
                ArrowData("full", "bond", "C-H (alpha) 결합",
                          "bond", "C=이탈 방향", "#4CAF50", 0.3,
                          from_atom_idx=12, to_atom_idx=11),
            ],
            labels={"N": "Et3N (염기)", "H": "alpha-H"},
            energy_label="탈양성자화",
            reagents="Et3N (트리에틸아민)",
            notes="Et3N은 비친핵성 염기. -78 degC에서 첨가.",
        ),
        # Step 8: [2,3]-sigmatropic elimination
        MechanismStep(
            step_number=8,
            title="분자내 [2,3]-시그마트로픽 제거 개시",
            description=(
                "alpha-탄소에서 양성자가 제거된 후, 생성된 카르바니온이\n"
                "분자내 [2,3]-시그마트로픽 전위(sigmatropic rearrangement)를 개시합니다.\n"
                "C-H 결합이 끊어지면서 전자쌍이 C=O 형성 방향으로 이동합니다.\n"
                "동시에 C-S 결합이 약화됩니다."
            ),
            reactant_smiles="[CH-]=CO[S+](C)C",
            product_smiles="[CH-]=CO[S+](C)C",
            arrows=[
                ArrowData("full", "bond", "C-S 결합 (약화)",
                          "atom", "S (DMS 방향)", "#FF9800", 0.4,
                          from_atom_idx=3, to_atom_idx=0),
                ArrowData("full", "negative_charge", "카르바니온",
                          "bond", "C=O 형성", "#E53935", 0.3,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"C-S": "약화 결합"},
            is_transition_state=True,
            energy_label="[2,3]-시그마트로픽 전이 상태",
            notes="5원 고리 전이 상태를 통한 협동적(concerted) 제거",
        ),
        # Step 9: Ylide intermediate
        MechanismStep(
            step_number=9,
            title="일라이드(Ylide) 중간체",
            description=(
                "탈양성자화 후 생성된 일라이드(ylide) 중간체입니다.\n"
                "탄소에 음전하, 황에 양전하가 공존하는 양성이온 구조를 갖습니다.\n"
                "이 중간체는 불안정하여 빠르게 제거 반응으로 진행됩니다."
            ),
            reactant_smiles="O=[S+](C)(C)[CH-]C",
            product_smiles="O=[S+](C)(C)[CH-]C",
            arrows=[
                ArrowData("full", "negative_charge", "C- (일라이드)",
                          "bond", "C=O 결합 형성 방향", "#9C27B0", 0.3,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"C-": "카르바니온", "S+": "술포늄"},
            energy_label="일라이드 중간체",
            notes="일라이드: 인접 원자에 반대 전하가 존재하는 양성이온",
        ),
        # Step 10: Concerted elimination -> C=O + DMS
        MechanismStep(
            step_number=10,
            title="협동적 제거 -> C=O + DMS 형성",
            description=(
                "5원 고리 전이 상태를 통해 협동적(concerted) 제거가 일어납니다.\n"
                "alpha-C에서 H가 이탈하면서 C=O 이중결합이 형성되고,\n"
                "동시에 C-S 결합이 끊어져 디메틸 설파이드(DMS, CH3-S-CH3)가 이탈합니다.\n"
                "이것이 Swern 산화의 핵심 단계입니다."
            ),
            reactant_smiles="[CH-]=CO[S+](C)C",
            product_smiles="CC=O.CSC",
            arrows=[
                ArrowData("full", "bond", "C-S 결합",
                          "atom", "S (DMS 이탈)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=0),
                ArrowData("full", "bond", "C-H 결합 전자",
                          "bond", "C=O pi 결합 형성", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"C=O": "카르보닐 형성", "DMS": "이탈기"},
            is_transition_state=True,
            energy_label="속도 결정 단계",
            notes="5원 고리 전이 상태(pericyclic). E_act ~ 15 kcal/mol",
        ),
        # Step 11: DMS departs
        MechanismStep(
            step_number=11,
            title="디메틸 설파이드(DMS) 이탈 완료",
            description=(
                "C-S 결합이 완전히 끊어지고 디메틸 설파이드(DMS, CH3SCH3)가\n"
                "자유 분자로 이탈합니다. DMS는 휘발성 부산물(bp 37 degC)이며\n"
                "특유의 불쾌한 냄새가 납니다. 저온(-78 degC) 반응이므로\n"
                "DMS는 용액에 남아 있다가 워크업 시 증발합니다."
            ),
            reactant_smiles="CC=O.CSC",
            product_smiles="CC=O.CSC",
            arrows=[],
            labels={"DMS": "CH3SCH3 (부산물)"},
            energy_label="DMS 이탈",
            notes="DMS는 악취 부산물. 흄 후드에서 반응 수행 필수.",
        ),
        # Step 12: Product formed
        MechanismStep(
            step_number=12,
            title="알데히드/케톤 최종 생성물",
            description=(
                "최종 생성물인 알데히드(1차 알코올 기질) 또는 케톤(2차 알코올 기질)이 형성됩니다.\n"
                "Swern 산화의 큰 장점: 1차 알코올 -> 알데히드 단계에서 멈추며,\n"
                "카르복실산으로의 과산화(over-oxidation)가 일어나지 않습니다.\n"
                "부산물: DMS + Et3N-HCl + CO + CO2."
            ),
            reactant_smiles="CC=O",
            product_smiles="CC=O",
            arrows=[],
            labels={"C=O": "알데히드 (최종 생성물)"},
            energy_label="생성물 (발열)",
            notes=(
                "전체 반응: RCH2OH + DMSO + (COCl)2 + Et3N "
                "-> RCHO + DMS + CO + CO2 + Et3N-HCl"
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\nR-CH2OH + DMSO\n+ (COCl)2", 0.0),
        ("TS1\nDMSO 활성화", 12.0),
        ("클로로술포늄\n+ CO + CO2", -8.0),
        ("알콕시술포늄\n중간체", -2.0),
        ("TS2 (탈양성자화)\n+ Et3N", 5.0),
        ("일라이드\n중간체", 3.0),
        ("TS3 ([2,3]-제거)\n속도 결정", 18.0),  # 18 kcal/mol 속도 결정 단계
        ("생성물\nRCHO + DMS", -15.0),
    ],
)

# ─── FAVORSKII REARRANGEMENT ────────────────────────────────────────────────
# 대표 반응: alpha-haloketone + NaOMe -> ring contraction -> cyclopentane carboxylate

MECHANISMS["favorskii_rearrangement"] = MechanismData(
    mechanism_type="favorskii_rearrangement",
    title="Favorskii 자리옮김 (Favorskii Rearrangement)",
    total_steps=10,
    overall_description=(
        "Favorskii 자리옮김은 alpha-할로케톤이 염기와 반응하여 "
        "고리 수축(ring contraction)을 거쳐 카르복실산 유도체를 생성하는 반응입니다. "
        "핵심 중간체는 사이클로프로파논(cyclopropanone)이며, "
        "이것이 친핵체(알콕사이드, 수산화물)에 의해 열려 "
        "고리가 한 탄소 줄어든 카르복실레이트를 생성합니다. "
        "환형 alpha-할로케톤의 경우 n원 고리가 (n-1)원 고리 카르복실산으로 변환됩니다. "
        "대안 경로인 반-벤질산(semibenzilic) 메커니즘은 alpha-H가 없는 기질에 적용됩니다."
    ),
    steps=[
        # Step 1: Base deprotonates alpha-H opposite to halide
        MechanismStep(
            step_number=1,
            title="염기에 의한 alpha-H 탈양성자화 (할로겐 반대편)",
            description=(
                "나트륨 메톡사이드(NaOMe)가 alpha-할로케톤의 alpha-수소를 제거합니다.\n"
                "중요: 할로겐이 결합된 alpha-탄소가 아닌, 할로겐 반대편 alpha-탄소의 H를 제거합니다.\n"
                "케톤 카르보닐의 전자 끌기 효과로 alpha-H의 pKa가 ~20으로 낮아져 있습니다.\n"
                "NaOMe(pKa ~15.5 공액산)는 충분히 강한 염기입니다."
            ),
            reactant_smiles="O=C1CCCCC1Cl.[O-]C",
            product_smiles="O=C1CCCC(=C1)[O-].Cl.OC",
            arrows=[
                ArrowData("full", "lone_pair", "MeO- 론페어 (염기)",
                          "atom", "alpha-H (할로겐 반대편)", "#E53935", 0.4,
                          from_atom_idx=8, to_atom_idx=6),
                ArrowData("full", "bond", "C-H (alpha) 결합",
                          "bond", "C=C (에놀레이트) 형성", "#4CAF50", 0.3,
                          from_atom_idx=6, to_atom_idx=1),
            ],
            labels={"MeO-": "염기 (NaOMe)", "H": "alpha-H"},
            energy_label="탈양성자화",
            reagents="NaOMe, MeOH, 0 degC",
            notes="할로겐 반대편 alpha-H 제거가 핵심. Regioselectivity 결정.",
        ),
        # Step 2: Enolate formation
        MechanismStep(
            step_number=2,
            title="에놀레이트 형성",
            description=(
                "alpha-탈양성자화로 생성된 카르바니온이 카르보닐과 공명하여\n"
                "에놀레이트 음이온을 형성합니다. 카르보닐 pi 전자가 산소로 이동하고\n"
                "alpha-탄소와 카르보닐 탄소 사이에 C=C 이중결합이 생깁니다.\n"
                "에놀레이트의 HOMO가 높아져 분자내 친핵 치환이 가능해집니다."
            ),
            reactant_smiles="[O-]C1=CCCCC1Cl",
            product_smiles="[O-]C1=CCCCC1Cl",
            arrows=[
                ArrowData("full", "negative_charge", "카르바니온",
                          "pi_bond", "C=C 형성 (공명)", "#9C27B0", 0.3,
                          from_atom_idx=6, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=O pi 전자",
                          "atom", "O- (에놀레이트)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),
            ],
            labels={"O-": "에놀레이트 산소", "C=C": "에놀 이중결합"},
            energy_label="에놀레이트 중간체",
            notes="에놀레이트: C=C-O- 공명 안정화. pKa ~20 -> ~25 (안정화 후)",
        ),
        # Step 3: Intramolecular displacement -> cyclopropanone
        MechanismStep(
            step_number=3,
            title="분자내 SN2 치환 -> 사이클로프로파논 형성",
            description=(
                "에놀레이트 alpha-탄소가 할로겐이 결합된 탄소를 분자내 SN2 공격합니다.\n"
                "이것은 3-exo-tet 고리닫힘(Baldwin 규칙 허용)입니다.\n"
                "Cl-가 이탈기로 떠나면서 3원 고리(사이클로프로파논)가 형성됩니다.\n"
                "이 단계가 Favorskii 자리옮김의 핵심 고리 수축 단계입니다."
            ),
            reactant_smiles="[O-]C1=CCCCC1Cl",
            product_smiles="O=C1CC1CCC.[Cl-]",
            arrows=[
                ArrowData("full", "negative_charge", "에놀레이트 C- (HOMO)",
                          "atom", "C-Cl (LUMO, sigma*)", "#E53935", 0.5,
                          from_atom_idx=2, to_atom_idx=6),
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl- (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=6, to_atom_idx=7),
            ],
            labels={"C-": "친핵 탄소", "C-Cl": "친전자 탄소", "Cl": "이탈기"},
            is_transition_state=True,
            energy_label="속도 결정 단계",
            notes=(
                "3-exo-tet 고리닫힘 (Baldwin 규칙 favored). "
                "사이클로프로파논은 ~115 deg 각변형(strain)에도 불구하고 형성."
            ),
        ),
        # Step 4: Semibenzilic mechanism - methoxide attacks cyclopropanone
        MechanismStep(
            step_number=4,
            title="반-벤질산(Semibenzilic) 메커니즘: MeO- 의 사이클로프로파논 공격",
            description=(
                "메톡사이드(MeO-)가 사이클로프로파논의 카르보닐 탄소를 친핵 공격합니다.\n"
                "사이클로프로파논은 극도의 각변형(angle strain, ~60 deg vs 이상 120 deg)으로\n"
                "카르보닐 탄소의 친전자성이 매우 높습니다.\n"
                "Buergi-Dunitz 각도(~107 deg)로 접근합니다."
            ),
            reactant_smiles="O=C1CC1CCC.[O-]C",
            product_smiles="[O-]C1(OC)CC1CCC",
            arrows=[
                ArrowData("full", "lone_pair", "MeO- 론페어",
                          "atom", "C=O (사이클로프로파논)", "#E53935", 0.4,
                          from_atom_idx=7, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=O pi 전자",
                          "atom", "O- (알콕사이드)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),
            ],
            labels={"MeO-": "친핵체", "C=O": "친전자 (변형 카르보닐)"},
            energy_label="친핵 첨가",
            notes="사이클로프로파논의 높은 각변형이 친핵 공격을 촉진",
        ),
        # Step 5: Ring opens at C-C bond
        MechanismStep(
            step_number=5,
            title="사이클로프로파논 고리 개환 (C-C 결합 절단)",
            description=(
                "사면체 중간체의 알콕사이드(O-)가 인접 C-C 결합을 이동시킵니다.\n"
                "3원 고리의 극심한 각변형 에너지가 해소되면서 C-C 결합이 절단됩니다.\n"
                "이것은 1,2-알킬 이동(1,2-alkyl shift)의 일종으로,\n"
                "결합 전자쌍이 인접 탄소로 이동하면서 고리가 열립니다.\n"
                "결과: 5원 고리(사이클로펜탄) + 에스터 작용기."
            ),
            reactant_smiles="[O-]C1(OC)CC1CCC",
            product_smiles="COC(=O)C1CCCC1",
            arrows=[
                ArrowData("full", "bond", "C-C (3원 고리) 결합",
                          "atom", "C (고리 확장 방향)", "#FF9800", 0.5,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("full", "negative_charge", "알콕사이드 O-",
                          "bond", "C=O 재형성", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"C-C": "절단 결합", "O-": "구동력 (C=O 재형성)"},
            is_transition_state=True,
            energy_label="고리 개환 전이 상태",
            notes="각변형 해소 + C=O 재형성이 열역학적 구동력 (~27 kcal/mol 해소)",
        ),
        # Step 6: beta-keto ester or carboxylate formation
        MechanismStep(
            step_number=6,
            title="메틸 사이클로펜탄카르복실레이트 형성",
            description=(
                "고리 개환 완료 후, 메틸 사이클로펜탄카르복실레이트가 형성됩니다.\n"
                "6원 고리(사이클로헥산)가 5원 고리(사이클로펜탄) + 에스터로 변환되었습니다.\n"
                "이것이 Favorskii 자리옮김의 고리 수축(ring contraction) 산물입니다."
            ),
            reactant_smiles="COC(=O)C1CCCC1",
            product_smiles="COC(=O)C1CCCC1",
            arrows=[],
            labels={"에스터": "COOMe 작용기", "고리": "사이클로펜탄"},
            energy_label="고리 수축 산물",
            notes="n원 고리 -> (n-1)원 고리 + COOR. 여기서 6 -> 5원 고리.",
        ),
        # Step 7: Protonation
        MechanismStep(
            step_number=7,
            title="양성자화 (산성 워크업)",
            description=(
                "산성 워크업(aqueous acid)으로 에스터 또는 카르복실레이트를 양성자화합니다.\n"
                "NaOMe 대신 NaOH를 사용한 경우, 카르복실레이트 나트륨 염을 거쳐\n"
                "산성화 후 카르복실산이 됩니다.\n"
                "MeOH 용매에서 NaOMe 사용 시 직접 메틸 에스터가 생성됩니다."
            ),
            reactant_smiles="COC(=O)C1CCCC1",
            product_smiles="COC(=O)C1CCCC1",
            arrows=[],
            labels={"에스터": "최종 에스터 (MeOH 조건)"},
            energy_label="안정한 생성물",
            reagents="H3O+ (산성 워크업)",
            notes="NaOH 사용 시: 카르복실산. NaOMe 사용 시: 메틸 에스터.",
        ),
        # Step 8: Alternative pathway - direct displacement
        MechanismStep(
            step_number=8,
            title="대안 경로: 직접 치환 (비-에놀화 기질)",
            description=(
                "alpha-H가 없는 기질(예: alpha,alpha-이치환 할로케톤)에서는\n"
                "에놀레이트 경로 대신 직접 치환 메커니즘이 작동합니다.\n"
                "친핵체(MeO-)가 직접 C-Cl의 alpha-탄소를 SN2 공격하여\n"
                "메톡시 치환체를 형성한 후 rearrangement가 진행됩니다."
            ),
            reactant_smiles="O=C1CCCCC1Cl.[O-]C",
            product_smiles="O=C1CCCCC1OC.[Cl-]",
            arrows=[
                ArrowData("full", "lone_pair", "MeO- (친핵체)",
                          "atom", "C-Cl (alpha 탄소)", "#E53935", 0.4,
                          from_atom_idx=8, to_atom_idx=7),
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl- (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=7, to_atom_idx=9),
            ],
            labels={"MeO-": "친핵체", "C-Cl": "SN2 기질"},
            energy_label="대안 경로",
            notes="비-에놀화(non-enolizable) 기질에만 적용. 예: 2,2-disubstituted",
        ),
        # Step 9: Benzilic-type 1,2-shift
        MechanismStep(
            step_number=9,
            title="벤질산형 1,2-이동 (Benzilic-type 1,2-shift)",
            description=(
                "직접 치환 경로에서의 후속 단계입니다.\n"
                "카르보닐 인접 C-C 결합이 1,2-알킬 이동(1,2-alkyl shift)을 겪습니다.\n"
                "이것은 벤질산 자리옮김(benzilic acid rearrangement)과 유사한 메커니즘으로,\n"
                "카르보닐 탄소에 음전하가 생기면서 인접 C-C 결합이 이동합니다."
            ),
            reactant_smiles="O=C1CCCCC1OC",
            product_smiles="COC(=O)C1CCCC1",
            arrows=[
                ArrowData("full", "bond", "C-C (인접) 결합",
                          "atom", "카르보닐 C", "#FF9800", 0.5,
                          from_atom_idx=2, to_atom_idx=1),
                ArrowData("full", "pi_bond", "C=O 전자",
                          "atom", "O- (알콕사이드)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),
            ],
            labels={"C-C": "1,2-이동 결합"},
            is_transition_state=True,
            energy_label="1,2-이동 전이 상태",
            notes="벤질산 자리옮김과 동일 메커니즘. Wagner-Meerwein 유형.",
        ),
        # Step 10: Final ester/acid product
        MechanismStep(
            step_number=10,
            title="최종 에스터/카르복실산 생성물",
            description=(
                "두 경로(에놀레이트 또는 직접 치환) 모두 동일한 최종 생성물을 제공합니다:\n"
                "사이클로펜탄카르복실산 메틸 에스터 (MeOH/NaOMe 조건)\n"
                "또는 사이클로펜탄카르복실산 (H2O/NaOH 조건).\n"
                "6원 고리(사이클로헥사논)가 5원 고리(사이클로펜탄) + COOR로 전환됩니다.\n"
                "이 고리 수축은 천연물 합성과 의약품 합성에서 광범위하게 활용됩니다."
            ),
            reactant_smiles="COC(=O)C1CCCC1",
            product_smiles="COC(=O)C1CCCC1",
            arrows=[],
            labels={"에스터": "메틸 사이클로펜탄카르복실레이트"},
            energy_label="최종 생성물 (발열)",
            notes=(
                "전체 반응: alpha-chlorocyclohexanone + NaOMe "
                "-> methyl cyclopentanecarboxylate + NaCl"
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\nalpha-클로로사이클로헥사논\n+ NaOMe", 0.0),
        ("TS1 (탈양성자화)", 8.0),
        ("에놀레이트\n중간체", -3.0),
        ("TS2 (3-exo-tet)\n사이클로프로파논 형성\n속도 결정 단계", 22.0),  # 22 kcal/mol
        ("사이클로프로파논\n+ Cl-", 10.0),
        ("TS3 (MeO- 공격)", 14.0),
        ("사면체\n중간체", 5.0),
        ("TS4 (고리 개환)", 12.0),
        ("생성물\nMeOOC-C5H9", -18.0),  # -18 kcal/mol 전체 발열
    ],
)

# ─── 에스터 가수분해 (산촉매) ─────────────────────────────────────────────────
# 대표: CH3COOCH2CH3 + H2O → CH3COOH + CH3CH2OH (산촉매)
# 핵심: 사면체 중간체(tetrahedral intermediate) 경유

MECHANISMS["acid_ester_hydrolysis"] = MechanismData(
    mechanism_type="acid_ester_hydrolysis",
    title="산촉매 에스터 가수분해",
    total_steps=4,
    overall_description=(
        "산촉매 에스터 가수분해는 Fischer 에스터화의 역반응입니다. "
        "H₃O⁺가 카르보닐 산소를 양성자화하여 친전자성을 높이고, "
        "물이 친핵체로 공격하여 사면체 중간체를 형성합니다. "
        "양성자 이동 후 알코올이 이탈하여 카르복실산을 생성합니다. "
        "Le Chatelier 원리에 의해 물 과량 시 가수분해 방향으로 진행합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="카르보닐 산소 양성자화",
            description=(
                "산 촉매(H₃O⁺)가 에스터 카르보닐 산소에 H⁺를 전달합니다.\n"
                "카르보닐 산소의 론페어가 양성자를 포획합니다.\n"
                "양성자화된 카르보닐(C=OH⁺)은 탄소의 친전자성이 크게 증가합니다.\n"
                "이는 물 분자의 친핵 공격을 용이하게 합니다."
            ),
            # CCOC(C)=O: C0-C1-O2-C3(-C4)(=O5)
            reactant_smiles="CCOC(C)=O",
            product_smiles="CCOC(C)=[OH+]",
            arrows=[
                ArrowData("full", "lone_pair", "C=O 산소 론페어",
                          "atom", "H⁺ (외부, H₃O⁺ 유래)", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=-1),
            ],
            labels={"O": "C=O → C=OH⁺", "H₃O⁺": "산 촉매"},
            energy_label="양성자화 (빠른 평형)",
            reagents="H₃O⁺ (산 촉매)",
            notes="카르보닐 양성자화는 빠른 가역 평형이며 속도 결정 단계가 아님.",
        ),
        MechanismStep(
            step_number=2,
            title="물의 친핵 공격 → 사면체 중간체 형성",
            description=(
                "물 분자의 산소 론페어가 양성자화된 카르보닐 탄소(sp2, 강한 δ⁺)를 공격합니다.\n"
                "카르보닐 탄소가 sp2 → sp3로 재혼성화됩니다.\n"
                "동시에 C=OH⁺의 pi 결합 전자쌍이 산소로 이동합니다.\n"
                "결과: 사면체 중간체(tetrahedral intermediate) 형성.\n"
                "이 단계가 속도 결정 단계입니다."
            ),
            # 양성자화 에스터 + 물
            reactant_smiles="CCOC(C)=[OH+].O",
            product_smiles="CCOC(C)(O)[OH2+]",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 산소 론페어",
                          "atom", "C (δ⁺⁺, 양성자화 카르보닐)", "#4CAF50", 0.5,
                          from_atom_idx=7, to_atom_idx=3),  # H2O O → carbonyl C
                ArrowData("full", "pi_bond", "C=OH⁺ pi 결합 전자",
                          "atom", "O (→ OH)", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=5),  # C=O pi → O
            ],
            labels={"H₂O": "친핵체", "C": "sp2 → sp3 (사면체)"},
            is_transition_state=True,
            energy_label="ΔG‡ (속도 결정 단계)",
            reagents="",
            notes="Burgi-Dunitz 각도(~107°)로 친핵 공격. 사면체 중간체는 비교적 불안정.",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 이동 + 알코올 이탈기 활성화",
            description=(
                "사면체 중간체 내부에서 양성자 이동(proton transfer)이 일어납니다.\n"
                "에스터 산소(-OR)가 양성자화되어 -OHR⁺가 됩니다.\n"
                "이로써 알코올(ROH)이 좋은 이탈기로 전환됩니다.\n"
                "(양성자화 전 -OR은 강한 염기여서 이탈기 불가)."
            ),
            reactant_smiles="CCOC(C)(O)[OH2+]",
            product_smiles="CC([OH2+])(O)OCC",
            arrows=[
                ArrowData("full", "lone_pair", "에스터 O 론페어",
                          "atom", "H⁺ (양성자 이동)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=-1),
            ],
            labels={"OR": "→ OHR⁺ (이탈기 활성화)"},
            energy_label="양성자 이동 (빠른 평형)",
            reagents="",
            notes="분자 내 양성자 이동 또는 용매(H₂O) 매개 양성자 전달.",
        ),
        MechanismStep(
            step_number=4,
            title="알코올 이탈 → 카르복실산 생성",
            description=(
                "양성자화된 알코올(-OHR⁺)이 C-O 결합이 끊어지며 이탈합니다.\n"
                "C-O 결합 전자쌍이 산소에 남아 알코올(ROH)로 이탈.\n"
                "탄소가 sp3 → sp2로 복귀하며 C=O 결합이 재형성됩니다.\n"
                "최종 탈양성자화를 거쳐 카르복실산(RCOOH)이 생성됩니다.\n"
                "촉매(H⁺)가 재생됩니다."
            ),
            reactant_smiles="CC([OH2+])(O)OCC",
            product_smiles="CC(=O)O.CCO",
            arrows=[
                ArrowData("full", "bond_center", "C-OR 결합",
                          "atom", "알코올 산소 (이탈기)", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=4),  # C-O bond → O (ROH leaves)
                ArrowData("full", "lone_pair", "O 론페어",
                          "bond", "C=O 재형성", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=1),  # O lp → C=O
            ],
            labels={"ROH": "이탈기 (EtOH)", "C": "sp3 → sp2"},
            energy_label="알코올 이탈 + C=O 재형성",
            reagents="",
            notes=(
                "전체 반응: RCOOR' + H₂O ⇌ RCOOH + R'OH. "
                "Le Chatelier: 물 과량이면 가수분해 진행. "
                "촉매량 H₂SO₄ 사용."
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOOR' + H₂O", 0.0),
        ("양성자화\nRCOOR'·H⁺", 3.0),
        ("TS1 (친핵 공격)\n속도 결정", 18.0),
        ("사면체 중간체\nRC(OH)(OHR')(OH₂)", 10.0),
        ("양성자 이동", 11.0),
        ("TS2 (이탈기 이탈)", 14.0),
        ("생성물\nRCOOH + R'OH", 1.0),
    ],
)


# ─── 알돌 축합 (Aldol Condensation) ──────────────────────────────────────────
# 대표: 2 × CH3CHO → CH3CH=CHCHO + H2O (NaOH 촉매)
# 알돌 첨가(aldol addition) 후 탈수(elimination)를 포함하는 완전 메커니즘
#
# Rule P exclusion guard (M1370 G3 patch):
#   Aldol trigger: 염기(NaOH/OH⁻) + 알데히드/케톤 α-H 탈양성자화 → C-C 결합 형성
#   Bamford-Stevens trigger: 케톤-히드라존(토실히드라존) + 강염기 → 디아조/카벤 → 알켄
#   구분 기준: Aldol = 두 카르보닐 사이 C-C sigma bond 형성 / Bamford-Stevens = N₂ 방출 + 카벤
#   과매칭 방지: 케톤의 단순 탈양성자화가 Bamford-Stevens로 인식되지 않도록
#   exclusion: reactant에 토실히드라존(-NHNHTs) 구조가 없으면 aldol_condensation 우선 적용

MECHANISMS["aldol_condensation"] = MechanismData(
    mechanism_type="aldol_condensation",
    title="알돌 축합 (Aldol Condensation)",
    total_steps=4,
    overall_description=(
        "알돌 반응은 에놀레이트(enolate)가 다른 카르보닐의 α,β-불포화 결합을 형성하는 "
        "핵심 C-C 결합 형성 반응입니다. "
        "1단계: 염기가 α-수소를 제거하여 에놀레이트를 형성합니다. "
        "2단계: 에놀레이트가 다른 알데히드의 카르보닐 탄소를 친핵 공격합니다. "
        "3단계: β-하이드록시 알데히드(알돌 산물)가 형성됩니다. "
        "4단계: 탈수(E1cb)에 의해 α,β-불포화 카르보닐(enal)이 생성됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에놀레이트 형성 (α-탈양성자화)",
            description=(
                "NaOH(OH⁻)가 아세트알데히드의 α-수소를 제거합니다.\n"
                "C-H sigma 결합 전자쌍이 C=C pi 결합으로 이동합니다.\n"
                "동시에 C=O pi 결합 전자쌍이 산소로 이동하여 O⁻가 됩니다.\n"
                "에놀레이트 음이온은 공명 안정화됩니다 (C⁻ ↔ O⁻)."
            ),
            # CH3CHO: C0(H3)-C1(H)(=O2)
            reactant_smiles="CC=O",
            product_smiles="[CH2-]C=O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ 론페어 (염기)",
                          "atom", "α-H", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=0),  # OH⁻ → α-H
                ArrowData("full", "bond", "C-H sigma 결합",
                          "bond", "C=C 에놀레이트", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-H → C=C
                ArrowData("full", "pi_bond", "C=O pi 결합",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C=O → O⁻
            ],
            labels={"H": "α-H (pKa ≈ 17)", "OH⁻": "염기"},
            energy_label="에놀레이트 형성",
            reagents="NaOH (cat.)",
            notes="에놀레이트는 열역학 제어(LDA, -78°C) 또는 속도 제어(NaOH, RT)로 형성.",
        ),
        MechanismStep(
            step_number=2,
            title="카르보닐 친핵 공격 → C-C 결합 형성",
            description=(
                "에놀레이트의 α-탄소가 두 번째 아세트알데히드의 카르보닐 탄소를 공격합니다.\n"
                "새 C-C sigma 결합이 형성됩니다.\n"
                "카르보닐 C=O의 pi 전자쌍이 산소로 이동하여 알콕사이드(O⁻)가 됩니다.\n"
                "이것이 알돌 반응의 핵심 C-C 결합 형성 단계입니다."
            ),
            # 에놀레이트 + 알데히드
            reactant_smiles="[CH2-]C=O.CC=O",
            product_smiles="OCC(CC=O)[O-]",
            arrows=[
                ArrowData("full", "negative_charge", "에놀레이트 C⁻",
                          "atom", "카르보닐 C (δ⁺)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=4),  # C⁻ → C=O
                ArrowData("full", "pi_bond", "C=O pi 결합",
                          "atom", "O⁻ (알콕사이드)", "#1565C0", 0.4,
                          from_atom_idx=4, to_atom_idx=5),  # C=O → O⁻
            ],
            labels={"C⁻": "친핵체 (에놀레이트)", "C=O": "친전자체"},
            is_transition_state=True,
            energy_label="ΔG‡ (C-C 결합 형성)",
            reagents="",
            notes="Zimmerman-Traxler 6원 의자형 전이상태로 입체화학 설명 가능.",
        ),
        MechanismStep(
            step_number=3,
            title="양성자화 → β-하이드록시 알데히드 (알돌 산물)",
            description=(
                "알콕사이드(O⁻)가 물로부터 양성자를 받습니다.\n"
                "β-하이드록시 알데히드(알돌 산물, aldol)가 형성됩니다.\n"
                "이 중간체가 알돌 '첨가' 산물이며, "
                "축합(condensation)은 다음 탈수 단계를 포함합니다."
            ),
            reactant_smiles="OCC(CC=O)[O-]",
            product_smiles="OC(CC=O)CO",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (양성자 공급원)",
                          "atom", "O⁻ → OH", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=5),
            ],
            labels={"알돌": "β-하이드록시 알데히드"},
            energy_label="알돌 산물",
            reagents="H₂O",
            notes="여기서 멈추면 '알돌 첨가(aldol addition)' 산물. 가열하면 탈수 진행.",
        ),
        MechanismStep(
            step_number=4,
            title="탈수 (E1cb) → α,β-불포화 알데히드",
            description=(
                "가열 조건에서 β-하이드록시 알데히드가 탈수됩니다.\n"
                "메커니즘: E1cb — 먼저 α-H 탈양성자화, 그 다음 β-OH 이탈.\n"
                "새로운 C=C 이중 결합이 형성되어 공액계(C=C-C=O)를 만듭니다.\n"
                "공액이 열역학적 구동력을 제공합니다.\n"
                "최종 산물: α,β-불포화 알데히드(크로톤알데히드)."
            ),
            # OC(CC=O)CO atom indices: O=0(α-OH), C=1(α-C), C=2, C=3, O=4(=O),
            #                           C=5(β-C), O=6(β-OH leaving group)
            # E1cb: 1) OH⁻ removes α-H from C1; 2) C1-H sigma→C1=C5 pi; 3) β-OH(O6) leaves
            reactant_smiles="OC(CC=O)CO",
            product_smiles="O=CC=CC.O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ (염기)",
                          "atom", "α-H 제거", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),   # 외부 OH⁻ → α-C(idx1)
                ArrowData("full", "bond", "C-H 결합 → C=C",
                          "bond", "C=C 형성", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=5),    # α-C(idx1)→β-C(idx5) pi형성
                ArrowData("full", "bond", "β-C-OH 결합 개열 (이탈기)",
                          "atom", "OH⁻ (이탈기)", "#8E44AD", 0.3,
                          from_atom_idx=5, to_atom_idx=6),    # β-C(idx5)→β-OH(idx6) 이탈 / σ결합끊김→보라 M442
            ],
            labels={"α,β": "공액계 형성", "H₂O": "이탈"},
            energy_label="탈수 (ΔG < 0, 공액 안정화)",
            reagents="NaOH, Δ (가열)",
            notes=(
                "E1cb 메커니즘: α-H 제거 → 에놀레이트 중간체 → β-OH 이탈. "
                "공액 C=C-C=O 시스템이 구동력."
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\n2 × CH₃CHO", 0.0),
        ("에놀레이트\nCH₂=CHO⁻", 5.0),
        ("TS (C-C 형성)", 14.0),
        ("알돌 산물\nβ-OH 알데히드", 2.0),
        ("TS (탈수, E1cb)", 10.0),
        ("생성물\nCH₃CH=CHCHO + H₂O", -6.0),
    ],
)


# ─── EAS 브롬화 (Br2/FeBr3 특이적) ───────────────────────────────────────────
# 대표: C6H6 + Br2 → C6H5Br + HBr (FeBr3 촉매)
# 일반 EAS와 구별: FeBr3 특이적 Lewis acid 활성화 포함

MECHANISMS["eas_bromination"] = MechanismData(
    mechanism_type="eas_bromination",
    title="친전자 방향족 브롬화 (EAS Bromination)",
    total_steps=3,
    overall_description=(
        "벤젠의 친전자 방향족 브롬화는 3단계로 진행됩니다. "
        "1단계: FeBr₃(Lewis acid)가 Br₂를 활성화하여 Br⁺ 등가체를 생성합니다. "
        "2단계: 벤젠 pi 전자가 Br⁺를 공격하여 아레늄 이온(sigma complex, Wheland 중간체)을 형성합니다. "
        "이 단계가 속도 결정 단계이며, 방향족성이 일시 소실됩니다. "
        "3단계: 염기(FeBr₃Br⁻)가 아레늄 이온의 C-H를 탈양성자화하여 방향족성을 회복합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="FeBr₃에 의한 Br₂ 활성화 → Br⁺ 등가체 생성",
            description=(
                "FeBr₃는 빈 p 오비탈을 가진 Lewis acid입니다.\n"
                "Br₂의 한쪽 Br 론페어가 Fe의 빈 p 오비탈에 배위합니다.\n"
                "Br-Br 결합이 이종개열(heterolysis)되어 Br⁺ 등가체와 [FeBr₄]⁻가 형성됩니다.\n"
                "실제로는 Br-Br···FeBr₃ 착물 상태로 존재하며, 완전한 Br⁺는 아닙니다."
            ),
            # Br-Br: Br0-Br1
            reactant_smiles="BrBr",
            product_smiles="[Br+].[Br-]",
            arrows=[
                ArrowData("full", "lone_pair", "Br 론페어",
                          "atom", "Fe (Lewis acid, 빈 p 오비탈)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=-1),  # Br lp → FeBr3
                ArrowData("full", "bond_center", "Br-Br sigma 결합",
                          "atom", "Br⁻ (→ [FeBr₄]⁻)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # Br-Br bond → Br
            ],
            labels={"FeBr₃": "Lewis acid", "Br⁺": "친전자체"},
            energy_label="착물 형성 (빠른 평형)",
            reagents="FeBr₃",
            notes="FeBr₃ 대신 AlCl₃도 사용 가능. Lewis acid의 역할은 Br-Br 분극화.",
        ),
        MechanismStep(
            step_number=2,
            title="벤젠 pi 공격 → 아레늄 이온 형성 (속도 결정)",
            description=(
                "벤젠의 pi 전자(HOMO)가 Br⁺(LUMO)를 공격합니다.\n"
                "새 C-Br sigma 결합이 형성되면서 방향족성이 깨집니다.\n"
                "양전하가 ortho/para 위치에 비편재화된 아레늄 이온(sigma complex) 형성.\n"
                "이것이 속도 결정 단계이며 Hammond 가설에 의해 "
                "전이상태는 아레늄 이온과 유사한 구조입니다.\n"
                "ipso-탄소는 sp3 혼성, 나머지 5개 탄소는 sp2를 유지합니다."
            ),
            # benzene: c1ccccc1 (aromatic, idx 0-5)
            reactant_smiles="c1ccccc1",
            product_smiles="C1=CC(Br)=CC=C1",
            arrows=[
                ArrowData("full", "pi_bond", "벤젠 pi 전자 (HOMO)",
                          "atom", "Br⁺ (LUMO)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=-1),
                ArrowData("full", "pi_bond", "pi 전자 비편재화",
                          "atom", "C₂ (ortho, δ⁺)", "#FF9800", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
                ArrowData("full", "pi_bond", "pi 전자 비편재화",
                          "atom", "C₄ (para, δ⁺)", "#FF9800", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"Ar": "벤젠 (pi donor)", "Br⁺": "친전자체"},
            is_transition_state=True,
            energy_label="ΔG‡ ≈ 25 kcal/mol (속도 결정)",
            reagents="",
            notes=(
                "아레늄 이온의 양전하는 공명 구조 3개로 안정화: "
                "C₁⁺, C₃⁺(ortho), C₅⁺(para). meta 위치에는 양전하 불가."
            ),
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자화 → 방향족성 회복 + HBr 생성",
            description=(
                "[FeBr₄]⁻가 염기로 작용하여 아레늄 이온의 C-H를 제거합니다.\n"
                "C-H 결합의 전자쌍이 방향족 pi 시스템으로 복귀합니다.\n"
                "방향족성이 회복되면서 큰 안정화 에너지(~36 kcal/mol)를 얻습니다.\n"
                "FeBr₃ 촉매가 재생되고 HBr 부산물이 생성됩니다.\n"
                "이 단계가 빠른 이유: 방향족성 회복의 열역학적 구동력."
            ),
            reactant_smiles="C1=CC(Br)=CC=C1",
            product_smiles="c1ccc(Br)cc1",
            arrows=[
                ArrowData("full", "bond", "C-H sigma 결합",
                          "pi_bond", "방향족 pi 계 복귀", "#4CAF50", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-H bond electrons → pi
                ArrowData("full", "lone_pair", "[FeBr₄]⁻ (염기)",
                          "atom", "H (탈양성자화)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),  # base → H
            ],
            labels={"H⁺": "이탈 (→ HBr)"},
            energy_label="방향족성 회복 (ΔG ≪ 0)",
            reagents="[FeBr₄]⁻ → FeBr₃ + HBr",
            notes=(
                "치환 vs 첨가: 첨가 산물은 방향족성을 잃으므로 불리. "
                "탈양성자화로 방향족성 회복이 열역학적으로 강하게 유리."
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\nC₆H₆ + Br₂\n+ FeBr₃", 0.0),
        ("FeBr₃·Br₂\n착물 형성", 3.0),
        ("TS₁ (pi 공격)\n속도 결정", 25.0),
        ("아레늄 이온\n[C₆H₆Br]⁺", 18.0),
        ("TS₂ (탈양성자화)", 19.0),
        ("생성물\nC₆H₅Br + HBr", -8.0),
    ],
)


# ─── Claisen 축합 (Claisen Condensation) ─────────────────────────────────────
# 대표: 2 × CH3COOC2H5 → CH3COCH2COOC2H5 + C2H5OH (NaOEt 촉매)
# 에스터 에놀레이트 + 에스터 → β-케토에스터

MECHANISMS["claisen_condensation"] = MechanismData(
    mechanism_type="claisen_condensation",
    title="Claisen 축합 (에스터 에놀레이트 축합)",
    total_steps=4,
    overall_description=(
        "Claisen 축합은 에스터의 α-수소를 염기로 제거하여 에놀레이트를 형성한 후, "
        "이 에놀레이트가 다른 에스터 분자의 카르보닐을 친핵 공격하는 반응입니다. "
        "사면체 중간체를 경유하여 알콕사이드가 이탈하고 β-케토에스터가 형성됩니다. "
        "최종 단계에서 생성물의 α-수소가 알콕사이드에 의해 제거되어 "
        "반응이 비가역적으로 진행됩니다 (구동력)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에스터 에놀레이트 형성",
            description=(
                "NaOEt(에톡사이드, 강한 염기)가 에틸 아세테이트의 α-수소를 제거합니다.\n"
                "C-H sigma 결합 전자쌍이 에놀레이트 C=C로 이동합니다.\n"
                "동시에 C=O pi 전자쌍이 O로 이동하여 에놀레이트 음이온 형성.\n"
                "에스터 에놀레이트는 알데히드 에놀레이트보다 약한 친핵체입니다."
            ),
            # CH3COOC2H5: C0(H3)-C1(=O2)-O3-C4(H2)-C5(H3)
            reactant_smiles="CCOC(C)=O",
            product_smiles="CCOC(=O)[CH2-]",
            arrows=[
                ArrowData("full", "lone_pair", "EtO⁻ (강한 염기)",
                          "atom", "α-H", "#E53935", 0.5,
                          from_atom_idx=-1, to_atom_idx=4),  # EtO⁻ → α-H
                ArrowData("full", "bond", "C-H sigma",
                          "bond", "C=C (에놀레이트)", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=3),  # C-H → C=C
                ArrowData("full", "pi_bond", "C=O pi",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=5),  # C=O → O⁻
            ],
            labels={"H": "α-H (pKa ≈ 25)", "EtO⁻": "염기"},
            energy_label="에놀레이트 형성 (평형 좌편)",
            reagents="NaOEt / EtOH",
            notes="에스터 α-H의 pKa (~25)는 알데히드 (~17)보다 높아 평형이 좌편에 놓임.",
        ),
        MechanismStep(
            step_number=2,
            title="에놀레이트의 카르보닐 공격 → 사면체 중간체",
            description=(
                "에놀레이트의 α-탄소가 두 번째 에스터의 카르보닐 탄소를 공격합니다.\n"
                "새 C-C sigma 결합이 형성됩니다.\n"
                "카르보닐 C=O의 pi 전자쌍이 산소로 이동합니다.\n"
                "사면체 중간체(tetrahedral intermediate)가 형성됩니다.\n"
                "이 중간체에는 2개의 OEt 기가 있습니다."
            ),
            reactant_smiles="CCOC(=O)[CH2-].CCOC(C)=O",
            product_smiles="CCOC(CC(=O)OCC)([O-])C",
            arrows=[
                ArrowData("full", "negative_charge", "에놀레이트 C⁻",
                          "atom", "카르보닐 C (δ⁺)", "#E53935", 0.5,
                          from_atom_idx=4, to_atom_idx=7),  # C⁻ → C=O
                ArrowData("full", "pi_bond", "C=O pi 결합",
                          "atom", "O⁻", "#1565C0", 0.4,
                          from_atom_idx=7, to_atom_idx=9),  # C=O → O⁻
            ],
            labels={"C⁻": "에놀레이트", "C=O": "두 번째 에스터"},
            is_transition_state=True,
            energy_label="ΔG‡ (C-C 형성)",
            reagents="",
            notes="Burgi-Dunitz 각도(~107°)로 접근. 사면체 중간체는 2개의 -OEt 보유.",
        ),
        MechanismStep(
            step_number=3,
            title="에톡사이드 이탈 → β-케토에스터 형성",
            description=(
                "사면체 중간체에서 에톡사이드(EtO⁻)가 이탈합니다.\n"
                "C-OEt 결합이 끊어지며 전자쌍이 에톡사이드로 이동합니다.\n"
                "탄소가 sp3 → sp2로 복귀하며 C=O 결합이 재형성됩니다.\n"
                "β-케토에스터(에틸 아세토아세테이트)가 생성됩니다."
            ),
            reactant_smiles="CCOC(CC(=O)OCC)([O-])C",
            product_smiles="CCOC(=O)CC(C)=O.[CH2-]C",
            arrows=[
                ArrowData("full", "lone_pair", "O⁻ 론페어",
                          "bond", "C=O 재형성", "#1565C0", 0.3,
                          from_atom_idx=9, to_atom_idx=7),  # O⁻ → C=O
                ArrowData("full", "bond_center", "C-OEt 결합",
                          "atom", "EtO⁻ (이탈기)", "#E53935", 0.3,
                          from_atom_idx=7, to_atom_idx=0),  # C-OEt → EtO⁻
            ],
            labels={"EtO⁻": "이탈기 + 다음 단계 염기"},
            energy_label="이탈기 이탈",
            reagents="",
            notes="이탈된 EtO⁻가 다음 단계에서 염기로 작용.",
        ),
        MechanismStep(
            step_number=4,
            title="비가역 탈양성자화 → 반응 완결 (구동력)",
            description=(
                "이탈된 에톡사이드(EtO⁻)가 β-케토에스터의 α-수소를 제거합니다.\n"
                "두 카르보닐기 사이의 α-H는 매우 산성(pKa ≈ 11)입니다.\n"
                "에놀레이트 음이온이 형성되면서 반응이 비가역적으로 진행됩니다.\n"
                "이 마지막 탈양성자화가 전체 반응의 열역학적 구동력입니다.\n"
                "산성 후처리(H₃O⁺)로 β-케토에스터를 회수합니다."
            ),
            reactant_smiles="CCOC(=O)CC(C)=O",
            product_smiles="CCOC(=O)[CH-]C(C)=O",
            arrows=[
                ArrowData("full", "lone_pair", "EtO⁻ (염기)",
                          "atom", "α-H (pKa ≈ 11)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=4),  # EtO⁻ → α-H
                ArrowData("full", "bond", "C-H → 에놀레이트",
                          "bond", "공명 안정화", "#4CAF50", 0.3,
                          from_atom_idx=4, to_atom_idx=3),
            ],
            labels={"α-H": "pKa ≈ 11 (매우 산성)", "반응 구동력": "비가역"},
            energy_label="비가역 탈양성자화 (ΔG ≪ 0)",
            reagents="EtO⁻ (이전 단계 이탈기)",
            notes=(
                "Claisen 축합의 핵심 구동력: 마지막 탈양성자화 단계가 비가역적. "
                "양쪽 카르보닐에 의한 이중 안정화로 pKa ≈ 11 (에스터 α-H의 pKa 25 대비 크게 낮음). "
                "산성 후처리(H₃O⁺)로 β-케토에스터 회수."
            ),
        ),
    ],
    energy_diagram=[
        ("반응물\n2 × EtOAc", 0.0),
        ("에놀레이트", 8.0),
        ("TS₁ (C-C 형성)", 18.0),
        ("사면체 중간체", 12.0),
        ("β-케토에스터", 5.0),
        ("에놀레이트 음이온\n(비가역)", -10.0),
        ("생성물\n(H₃O⁺ 후처리)", -2.0),
    ],
)


# ─── Wolff-Kishner 환원 ─────────────────────────────────────────────────────
# C=O → CH₂ (히드라진 + KOH, 고비점 용매 환류)
# 대표: PhCOCH₃ + NH₂NH₂ + KOH → PhCH₂CH₃

MECHANISMS["wolff_kishner"] = MechanismData(
    mechanism_type="wolff_kishner",
    title="Wolff-Kishner 환원 (Wolff-Kishner Reduction)",
    total_steps=4,
    overall_description=(
        "카르보닐(C=O)을 메틸렌(CH₂)으로 환원하는 반응입니다. "
        "히드라진(NH₂NH₂)과 카르보닐의 축합으로 히드라존을 형성한 뒤, "
        "강염기(KOH) 존재하에 고비점 용매(에틸렌글리콜 또는 DMSO)에서 환류하면 "
        "히드라존이 분해되어 N₂가 이탈하고 CH₂가 생성됩니다. "
        "Huang-Minlon 변법: 에틸렌글리콜 용매에서 one-pot 수행. "
        "Clemmensen 환원(Zn-Hg/HCl)의 염기성 대안."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="히드라존 형성 — 카르보닐 축합",
            description=(
                "히드라진(NH₂NH₂)의 론페어가 카르보닐 탄소를 친핵 공격합니다.\n"
                "카르보날아민(carbinolamine) 중간체 형성 → 탈수 → 히드라존(C=N-NH₂).\n"
                "이 단계는 산성 또는 중성 조건에서도 진행 가능."
            ),
            # CC(=O)c1ccccc1: acetophenone
            reactant_smiles="CC(=O)c1ccccc1",
            product_smiles="CC(=NN)c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "NH₂NH₂ 론페어",
                          "atom", "C=O 탄소", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "pi_bond", "C=O π-결합",
                          "atom", "O (이탈)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"C=O": "친전자체", "NH₂NH₂": "친핵체"},
            energy_label="히드라존 형성",
            reagents="NH₂NH₂, 가열",
            notes="Carbinolamine → 탈수 → 히드라존 (이민 형성과 동일 메커니즘)",
        ),
        MechanismStep(
            step_number=2,
            title="히드라존 탈양성자화 — 강염기에 의한 음이온 형성",
            description=(
                "KOH(강염기)가 히드라존의 N-H를 탈양성자화합니다.\n"
                "히드라존 음이온(C=N-N⁻) 형성.\n"
                "고비점 용매(에틸렌글리콜, bp 197°C) 환류 필요."
            ),
            reactant_smiles="CC(=NN)c1ccccc1",
            product_smiles="CC(=N[NH-])c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ 론페어",
                          "atom", "N-H (양성자)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "N-H 결합 이종개열",
                          "atom", "N (음이온화)", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N-H": "산성 양성자", "OH⁻": "강염기"},
            energy_label="히드라존 음이온",
            reagents="KOH, 에틸렌글리콜, Δ (197°C)",
            notes="고온 필요: 활성화 에너지 극복",
        ),
        MechanismStep(
            step_number=3,
            title="[1,2]-수소 이동 + N₂ 이탈 (속도 결정 단계)",
            description=(
                "히드라존 음이온에서 C→N 양성자 이동(tautomerization)으로 "
                "디아조 중간체(C⁻-N=N) 형성.\n"
                "C-N 결합이 끊어지며 N₂(질소 기체)가 이탈.\n"
                "카르바니온(C⁻) 생성.\n"
                "N₂ 이탈이 반응의 열역학적 구동력 (매우 안정한 기체, ΔG ≪ 0)."
            ),
            reactant_smiles="CC(=N[NH-])c1ccccc1",
            product_smiles="[CH2-]c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-N 결합 개열",
                          "atom", "N=N (이탈기)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"N₂": "이탈기 (매우 안정)", "C⁻": "카르바니온"},
            is_transition_state=True,
            energy_label="TS: N₂ 이탈 (속도 결정)",
            reagents="KOH, 에틸렌글리콜, Δ",
            notes=(
                "N₂ 이탈이 구동력: N≡N 결합 에너지 = 945 kJ/mol. "
                "이 단계가 속도 결정 단계."
            ),
        ),
        MechanismStep(
            step_number=4,
            title="카르바니온 양성자화 → 최종 생성물",
            description=(
                "카르바니온(C⁻)이 용매(에틸렌글리콜) 또는 H₂O로부터 양성자를 받습니다.\n"
                "C-H 결합 형성 → 최종 CH₂ 생성물.\n"
                "결과: C=O → CH₂ (2단계 환원)."
            ),
            reactant_smiles="[CH2-]c1ccccc1",
            product_smiles="CCc1ccccc1",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻ 카르바니온",
                          "atom", "H (양성자원)", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"C⁻": "카르바니온", "H-OR": "양성자원"},
            energy_label="생성물",
            reagents="H₂O (양성자원)",
            notes="최종 생성물: 에틸벤젠 (PhCH₂CH₃)",
        ),
    ],
    energy_diagram=[
        ("반응물\nPhCOCH₃ + NH₂NH₂", 0.0),
        ("히드라존", -5.0),
        ("히드라존 음이온", 5.0),
        ("TS: N₂ 이탈", 30.0),
        ("카르바니온 + N₂↑", 10.0),
        ("생성물\nPhCH₂CH₃", -15.0),
    ],
)


# ─── Epoxide Ring Opening (Acid-Catalyzed) ──────────────────────────────────
# 대표: 에폭시 + H₃O⁺ → 트랜스-디올 (anti 첨가, Markovnikov)
# 기출: Ch 18 (2014-A 서술4, 2018-A 기입4, 2020-B 서술7)

MECHANISMS["epoxide_acid_opening"] = MechanismData(
    mechanism_type="epoxide_acid_opening",
    title="에폭시드 산촉매 개환 (Anti/Markovnikov)",
    total_steps=3,
    overall_description=(
        "에폭시드가 산촉매 조건에서 개환합니다. 먼저 산(H⁺)이 에폭시드의 산소를 양성자화하여 "
        "에폭시드를 활성화합니다. 이어서 친핵체(H₂O)가 더 치환된 탄소를 뒤쪽(anti)에서 공격하여 "
        "트랜스-디올이 형성됩니다. Markovnikov 위치선택성: 부분 양전하가 더 큰 쪽(3차 > 2차)에 "
        "친핵체 공격이 일어납니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에폭시드 양성자화 → 활성화",
            description=(
                "산(H₃O⁺ 또는 H⁺)이 에폭시드 산소의 론페어를 양성자화합니다.\n"
                "C-O 결합이 약화되고, 탄소에 부분 양전하(δ+)가 발생합니다.\n"
                "더 치환된 탄소에 더 큰 δ+가 발생 → Markovnikov 위치선택성 결정."
            ),
            # C1C2O3 에폭시드
            reactant_smiles="C1CO1",
            product_smiles="C1C[OH+]1",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "에폭시드 O", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),  # H+ → O
            ],
            labels={"O": "에폭시드 산소", "H": "산촉매"},
            energy_label="양성자화",
            reagents="H₃O⁺ (산촉매)",
            notes="에폭시드 산소의 론페어가 양성자를 받음",
        ),
        MechanismStep(
            step_number=2,
            title="H₂O 친핵 공격 (anti, Markovnikov)",
            description=(
                "물(H₂O)의 산소 론페어가 양성자화된 에폭시드의 더 치환된 탄소를 공격합니다.\n"
                "SN2-유사 기전: anti 공격 → 입체배치 반전(Walden 전환).\n"
                "C-O(에폭시드) 결합이 개열되면서 새 C-O(물) 결합이 형성됩니다.\n"
                "결과: 트랜스(anti) 배치의 1,2-디올 전구체."
            ),
            reactant_smiles="C1C[OH+]1.O",
            product_smiles="OCC[OH2+]",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C (δ+, 더 치환된 탄소)", "#4CAF50", 0.4,
                          from_atom_idx=3, to_atom_idx=0),  # H2O→C
                ArrowData("full", "bond", "C-O(에폭시) 결합",
                          "atom", "O (이탈)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C-O 개열
            ],
            labels={"H₂O": "친핵체", "C": "δ+ 탄소"},
            is_transition_state=True,
            energy_label="속도 결정 단계",
            notes="anti 공격 → 트랜스-디올, Markovnikov 위치선택성",
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자화 → 트랜스-1,2-디올 생성",
            description=(
                "옥소늄 이온(R-OH₂⁺)에서 H₂O 또는 염기가 양성자를 제거합니다.\n"
                "최종 생성물: 트랜스-1,2-디올.\n"
                "산촉매 조건이므로 Markovnikov + anti 첨가 규칙 적용."
            ),
            reactant_smiles="OCC[OH2+]",
            product_smiles="OCCO",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (염기 역할)",
                          "atom", "H (옥소늄)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"생성물": "트랜스-1,2-디올"},
            energy_label="생성물",
            reagents="H₂O (탈양성자화)",
            notes="최종 입체화학: anti 첨가 → 트랜스-디올",
        ),
    ],
    energy_diagram=[
        ("반응물\n에폭시드 + H₃O⁺", 0.0),
        ("양성자화된 에폭시드", -5.0),
        ("전이 상태\n[H₂O···C···O]-", 15.0),
        ("옥소늄 중간체", -2.0),
        ("생성물\n트랜스-1,2-디올", -12.0),
    ],
)


# ─── Epoxide Ring Opening (Base-Catalyzed) ──────────────────────────────────
# 대표: 에폭시 + OH⁻/RO⁻ → anti-Markovnikov, anti 첨가
# 기출: Ch 18 (2015-A 서술3, 2021-A 서술9)

MECHANISMS["epoxide_base_opening"] = MechanismData(
    mechanism_type="epoxide_base_opening",
    title="에폭시드 염기촉매 개환 (Anti/Anti-Markovnikov)",
    total_steps=2,
    overall_description=(
        "에폭시드가 강한 친핵체(OH⁻, RO⁻, RS⁻ 등)에 의해 개환됩니다. "
        "SN2 기전: 친핵체가 덜 치환된(덜 입체장애 있는) 탄소를 anti로 공격합니다. "
        "Anti-Markovnikov 위치선택성 + anti 입체배치 → 트랜스-디올 또는 베타-알콕시 알코올."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="친핵체 SN2 공격 (anti, anti-Markovnikov)",
            description=(
                "강한 친핵체(OH⁻)의 론페어가 에폭시드의 덜 치환된(덜 입체장애) 탄소를 공격합니다.\n"
                "SN2 기전: 에폭시드 반대편(anti)에서 공격 → 입체배치 반전.\n"
                "C-O(에폭시드) 결합이 동시에 개열됩니다.\n"
                "Anti-Markovnikov: 입체 효과가 전자 효과보다 우세."
            ),
            reactant_smiles="C1CO1.[OH-]",
            product_smiles="OCC[O-]",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ 론페어",
                          "atom", "C (덜 치환, δ+)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=0),  # OH→C (덜 치환)
                ArrowData("full", "bond", "C-O(에폭시) 결합",
                          "atom", "O⁻ (알콕사이드)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C-O 개열
            ],
            labels={"OH⁻": "친핵체", "C": "덜 치환 탄소"},
            is_transition_state=True,
            energy_label="속도 결정 단계",
            notes="SN2: 덜 입체장애 탄소 공격, anti 입체화학",
        ),
        MechanismStep(
            step_number=2,
            title="양성자 이동 → 1,2-디올 생성",
            description=(
                "생성된 알콕사이드(RO⁻)가 용매(H₂O)로부터 양성자를 받습니다.\n"
                "최종 생성물: 트랜스-1,2-디올.\n"
                "염기촉매: anti-Markovnikov + anti 첨가."
            ),
            reactant_smiles="OCC[O-]",
            product_smiles="OCCO",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O",
                          "atom", "O⁻ (알콕사이드)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=3),
            ],
            labels={"생성물": "트랜스-1,2-디올"},
            energy_label="생성물",
            notes="anti-Markovnikov + anti 첨가",
        ),
    ],
    energy_diagram=[
        ("반응물\n에폭시드 + OH⁻", 0.0),
        ("[HO···C···O]⁻\n전이 상태", 18.0),
        ("알콕사이드 중간체", -3.0),
        ("생성물\n트랜스-1,2-디올", -10.0),
    ],
)


# ─── Cannizzaro Reaction ────────────────────────────────────────────────────
# 대표: 2 PhCHO + NaOH → PhCOO⁻ + PhCH₂OH
# 기출: Ch 19-23 (2009-25, 2012-39, 2021-A 기입3)

MECHANISMS["cannizzaro"] = MechanismData(
    mechanism_type="cannizzaro",
    title="Cannizzaro 반응 (불균등화)",
    total_steps=3,
    overall_description=(
        "alpha-수소가 없는 알데하이드(예: 벤즈알데하이드, 포름알데하이드)가 강염기(NaOH) 존재 하에서 "
        "불균등화(disproportionation)합니다. 한 분자는 산화(→ 카르복실산 염)되고, "
        "다른 분자는 환원(→ 1차 알코올)됩니다. 핵심: hydride transfer(1,2-수소이동)."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="OH⁻의 카르보닐 친핵 첨가 → 사면체 중간체",
            description=(
                "OH⁻가 알데하이드 카르보닐 탄소의 π* 오비탈을 공격합니다.\n"
                "카르보닐 C=O의 π-결합이 끊어지고, 산소는 음전하(O⁻)를 가집니다.\n"
                "사면체(tetrahedral) 알콕사이드 중간체 형성: PhCH(OH)(O⁻)."
            ),
            reactant_smiles="O=Cc1ccccc1.[OH-]",
            product_smiles="OC([O-])c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ 론페어",
                          "atom", "C=O (카르보닐 탄소)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=1),  # OH→C
                ArrowData("full", "pi_bond", "C=O π-결합",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=0),  # C=O→O⁻
            ],
            labels={"OH⁻": "친핵체", "C=O": "친전자체"},
            energy_label="사면체 중간체",
            notes="alpha-H 없는 알데하이드만 가능 (aldol 불가)",
        ),
        MechanismStep(
            step_number=2,
            title="수소화물 이동 (Hydride Transfer) — 속도 결정",
            description=(
                "사면체 중간체의 C-H 결합이 이종 개열: 수소화물(H⁻)이 두 번째 알데하이드의 카르보닐 탄소로 이동합니다.\n"
                "이것은 분자간 hydride transfer입니다.\n"
                "첫 번째 분자: 산화 → 카르복실산 (PhCOO⁻)\n"
                "두 번째 분자: 환원 → 알코올 (PhCH₂O⁻)\n"
                "이 단계가 속도 결정 단계입니다."
            ),
            reactant_smiles="OC([O-])c1ccccc1.O=Cc1ccccc1",
            product_smiles="O=C([O-])c1ccccc1.[O-]Cc1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-H 결합 (hydride)",
                          "atom", "C=O (두 번째 알데하이드)", "#E53935", 0.5,
                          from_atom_idx=1, to_atom_idx=9),  # H⁻→C2
                ArrowData("full", "pi_bond", "C=O π-결합 (두 번째)",
                          "atom", "O⁻ (두 번째)", "#1565C0", 0.3,
                          from_atom_idx=9, to_atom_idx=8),  # C=O→O⁻
                ArrowData("full", "negative_charge", "O⁻ → C=O 복원",
                          "bond", "C=O (첫 번째)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=1),  # O⁻→C=O
            ],
            labels={"H⁻": "수소화물 이동", "PhCHO(1)": "산화", "PhCHO(2)": "환원"},
            is_transition_state=True,
            energy_label="속도 결정 단계",
            reagents="분자간 hydride transfer",
            notes="핵심: H⁻ 이동 (이종 개열). 교차 Cannizzaro 가능 (HCHO + ArCHO)",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 교환 → 카르복실산 염 + 알코올",
            description=(
                "알콕사이드(PhCH₂O⁻)가 용매 또는 카르복실산으로부터 양성자를 받아 알코올 형성.\n"
                "카르복실산은 NaOH에 의해 카르복실산 나트륨(PhCOO⁻Na⁺)으로 존재.\n"
                "최종 생성물: 벤조산 나트륨 + 벤질 알코올."
            ),
            reactant_smiles="O=C([O-])c1ccccc1.[O-]Cc1ccccc1",
            product_smiles="O=C([O-])c1ccccc1.OCc1ccccc1",
            arrows=[],
            labels={"생성물": "PhCOO⁻ + PhCH₂OH"},
            energy_label="생성물",
            notes="산처리 시: PhCOOH + PhCH₂OH",
        ),
    ],
    energy_diagram=[
        ("반응물\n2 PhCHO + NaOH", 0.0),
        ("사면체 중간체", -3.0),
        ("TS: hydride transfer", 25.0),
        ("이온쌍 중간체", -5.0),
        ("생성물\nPhCOO⁻ + PhCH₂OH", -18.0),
    ],
)


# ─── Alcohol Dehydration (E1) ───────────────────────────────────────────────
# 대표: R-OH + H₂SO₄ → 알켄 + H₂O
# 기출: Ch 17 (2007-11, 2011-37, 2013-38, 2020-B 서술8)

MECHANISMS["alcohol_dehydration"] = MechanismData(
    mechanism_type="alcohol_dehydration",
    title="알코올 탈수 (E1, 산촉매)",
    total_steps=3,
    overall_description=(
        "알코올이 산촉매(H₂SO₄ 또는 H₃PO₄) 존재 하에서 E1 기전으로 탈수되어 알켄을 생성합니다. "
        "3단계: (1) OH 양성자화 → 좋은 이탈기(H₂O), (2) H₂O 이탈 → 카르보카티온(속도 결정), "
        "(3) beta-H 탈양성자 → 알켄. Zaitsev 법칙: 더 치환된 알켄이 주생성물."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="OH 양성자화 → 옥소늄 이온",
            description=(
                "산(H₂SO₄)이 알코올의 OH 산소를 양성자화합니다.\n"
                "OH → OH₂⁺: OH는 나쁜 이탈기(pKa ~15.7)이지만, H₂O는 좋은 이탈기(pKa = -1.7).\n"
                "이 양성자화가 탈수 반응을 가능하게 합니다."
            ),
            # CC(C)(C)O: C0-C1(-C2)(-C3)-O4
            reactant_smiles="CC(C)(C)O",
            product_smiles="CC(C)(C)[OH2+]",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (H₂SO₄)",
                          "atom", "OH (알코올)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=4),  # H+→O
            ],
            labels={"O": "OH → OH₂⁺"},
            energy_label="옥소늄 이온",
            reagents="H₂SO₄ (산촉매)",
            notes="OH는 나쁜 이탈기, H₂O는 좋은 이탈기",
        ),
        MechanismStep(
            step_number=2,
            title="H₂O 이탈 → 카르보카티온 형성 (속도 결정)",
            description=(
                "옥소늄 이온에서 H₂O가 이탈하여 카르보카티온을 형성합니다.\n"
                "C-O 결합의 이종 개열: 결합 전자쌍이 산소(H₂O)로 이동.\n"
                "3차 카르보카티온이 초공액 효과로 안정화됩니다.\n"
                "이 단계가 속도 결정 단계(RDS): E1 반응의 1차 역학."
            ),
            reactant_smiles="CC(C)(C)[OH2+]",
            product_smiles="C[C+](C)C.O",
            arrows=[
                ArrowData("full", "bond", "C-OH₂ 결합",
                          "atom", "H₂O (이탈기)", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=4),  # C-O→O
            ],
            labels={"C": "C+ (sp2)", "H₂O": "이탈기"},
            is_transition_state=True,
            energy_label="속도 결정 단계",
            notes="반응 속도 = k[R-OH₂⁺]. 3차 > 2차 > 1차",
        ),
        MechanismStep(
            step_number=3,
            title="beta-H 탈양성자 → 알켄 형성",
            description=(
                "용매 또는 HSO₄⁻가 beta-수소를 탈양성자합니다.\n"
                "C-H 결합 전자쌍이 C=C π-결합을 형성합니다.\n"
                "Zaitsev 법칙: 더 치환된(더 안정한) 알켄이 주생성물.\n"
                "결과: 2-메틸프로펜(이소부틸렌) + H₂O."
            ),
            reactant_smiles="C[C+](C)C",
            product_smiles="CC(=C)C",
            arrows=[
                ArrowData("full", "bond", "C-H 결합",
                          "bond", "C=C π-결합 형성", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=1),  # CH₃→C⁺
            ],
            labels={"H": "beta-H", "C=C": "알켄"},
            energy_label="생성물",
            reagents="HSO₄⁻ (약한 염기)",
            notes="Zaitsev 법칙: 더 치환된 알켄 우선",
        ),
    ],
    energy_diagram=[
        ("반응물\n(CH₃)₃COH + H₂SO₄", 0.0),
        ("옥소늄 이온", -3.0),
        ("TS: C-O 개열", 28.0),
        ("카르보카티온 + H₂O", 18.0),
        ("TS: 탈양성자", 20.0),
        ("생성물\n(CH₃)₂C=CH₂ + H₂O", -8.0),
    ],
)


# ─── Halohydrin Formation ──────────────────────────────────────────────────
# 대표: 알켄 + Br₂/H₂O → 브로모하이드린 (anti, Markovnikov)
# 기출: Ch 7-8 (2009-23, 2011-35, 2015-A 서술3, 2018-A 기입4)

MECHANISMS["halohydrin_formation"] = MechanismData(
    mechanism_type="halohydrin_formation",
    title="할로하이드린 형성 (Br₂/H₂O)",
    total_steps=3,
    overall_description=(
        "알켄이 Br₂/H₂O 조건에서 반응하여 할로하이드린(halohydrin)을 형성합니다. "
        "3단계: (1) π-결합이 Br₂ 공격 → 브로모늄 이온, (2) H₂O가 Markovnikov 위치 공격(anti), "
        "(3) 탈양성자화. 무수(CCl₄) 조건이면 Br₂ anti 첨가(1,2-디브로모 화합물), "
        "H₂O 존재 시 H₂O가 Br⁻보다 빠르게 친핵 공격 → 할로하이드린."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="π-결합의 Br₂ 공격 → 브로모늄 이온 형성",
            description=(
                "알켄의 C=C π-결합 전자쌍(HOMO)이 Br₂의 σ* 오비탈을 공격합니다.\n"
                "Br-Br 결합이 이종 개열: 한 Br은 브로모늄 이온 형성, 다른 Br은 Br⁻로 이탈.\n"
                "브로모늄 이온: 3원환 고리 양이온(bridged cation). 양전하가 두 탄소에 분산.\n"
                "더 치환된 탄소에 더 큰 δ+ → Markovnikov 위치선택성."
            ),
            reactant_smiles="C=C.BrBr",
            product_smiles="C1[Br+]C1.[Br-]",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π-결합",
                          "atom", "Br (Br-Br)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=2),  # π→Br
                ArrowData("full", "bond", "Br-Br 결합",
                          "atom", "Br⁻ (이탈)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # Br→Br
            ],
            labels={"C=C": "π-결합", "Br⁺": "브로모늄 이온"},
            energy_label="브로모늄 이온",
            notes="3원환 브로모늄 이온: 양전하 분산, 키랄 중심",
        ),
        MechanismStep(
            step_number=2,
            title="H₂O 친핵 공격 (anti, Markovnikov 위치)",
            description=(
                "물(H₂O, 용매)이 브로모늄 이온의 더 치환된(더 δ+) 탄소를 anti로 공격합니다.\n"
                "SN2-유사: 브로모늄 반대편에서 공격 → anti 입체화학.\n"
                "H₂O가 Br⁻보다 훨씬 높은 농도(용매)이므로 먼저 반응.\n"
                "C-Br(브로모늄) 결합이 동시에 개열됩니다."
            ),
            reactant_smiles="C1[Br+]C1.O",
            product_smiles="[OH2+]CCBr",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C (δ+, Markovnikov)", "#4CAF50", 0.4,
                          from_atom_idx=3, to_atom_idx=1),  # H₂O→C
                ArrowData("full", "bond", "C-Br(브로모늄)",
                          "atom", "Br (개열)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),  # C-Br 개열
            ],
            labels={"H₂O": "친핵체 (용매)", "C": "Markovnikov 위치"},
            is_transition_state=True,
            energy_label="SN2-유사 전이 상태",
            notes="H₂O 농도 >> Br⁻ 농도 → 할로하이드린 생성",
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자화 → 할로하이드린 생성",
            description=(
                "옥소늄 이온(R-OH₂⁺)에서 H₂O 또는 Br⁻가 양성자를 제거합니다.\n"
                "최종 생성물: 할로하이드린 (anti-OH, anti-Br).\n"
                "입체화학: OH와 Br이 anti 배치(trans-디액시알)."
            ),
            reactant_smiles="[OH2+]CCBr",
            product_smiles="OCCBr",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (염기)",
                          "atom", "H (옥소늄)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"생성물": "할로하이드린 (anti-OH, anti-Br)"},
            energy_label="생성물",
            notes="Markovnikov: OH on more substituted C, Br on less substituted C",
        ),
    ],
    energy_diagram=[
        ("반응물\n알켄 + Br₂/H₂O", 0.0),
        ("브로모늄 이온 + Br⁻", 8.0),
        ("TS: H₂O 공격", 14.0),
        ("옥소늄 중간체", 2.0),
        ("생성물\n할로하이드린", -6.0),
    ],
)


# ─── mCPBA Epoxidation ──────────────────────────────────────────────────────
# 대표: 알켄 + mCPBA → 에폭시드 (syn 첨가, 협동 기전)
# 기출: Ch 7-8 (2014-A 서술4, 2016-A 서술13, 2018-A 기입5)

MECHANISMS["mcpba_epoxidation"] = MechanismData(
    mechanism_type="mcpba_epoxidation",
    title="mCPBA 에폭시화 (3단계 협동 기전)",
    total_steps=3,  # M561 보강: 1단계→3단계 (peracid 형성/oxygen transfer/byproduct)
    overall_description=(
        "알켄이 과산(peracid, mCPBA)과 반응하여 에폭시드를 형성합니다. "
        "3단계 기전: (1) mCPBA의 분자내 H-결합으로 5원 고리 사전배열(pre-organization), "
        "(2) 나비(butterfly) 전이 상태에서 π-결합 공격 + O-O 개열 + 양성자 이동 동시 발생, "
        "(3) 에폭시드 생성 + mCBA(meta-클로로벤조산) 부생성물 분리. "
        "협동(concerted)이지만 단계별 전자 흐름을 학생이 이해할 수 있도록 분리. "
        "syn 첨가: 산소가 이중결합의 같은 면에 첨가. 입체특이적(stereospecific). "
        "참고: Bartlett 1950 Rec.Chem.Prog 11:47, Plesnicar 1991 J.Chem.Soc.Perkin 1:5, "
        "Clayden Organic Chemistry §35.6."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="과산 활성화: 분자내 H-결합 사전배열 (5원 고리)",
            description=(
                "mCPBA의 -O-O-H가 카르보닐 C=O 산소와 분자내 수소결합을 형성하여 "
                "5원 고리(spiro) 사전배열 상태(pre-organized)가 됩니다.\n"
                "  - O-H 양성자가 인접 C=O 산소로 부분 이동 (H-bond 강화)\n"
                "  - 말단 산소(distal O)의 친전자성 증가 (LUMO 낮아짐)\n"
                "  - 이 사전배열로 알켄 C=C가 distal O에 접근하기 좋은 기하 형성\n"
                "이 단계에서 이온성 중간체는 형성되지 않으나 H-결합으로 원자가 재배열되어 "
                "다음 협동 단계의 활성화 에너지를 낮춥니다."
            ),
            # mCPBA 단순화 OO + 카르보닐 (실제로는 m-Cl-C6H4-CO-O-O-H)
            reactant_smiles="C=C.OO",
            product_smiles="C=C.OO",  # 동일 분자, H-bond 사전배열
            arrows=[
                # H-bond 형성: O-H ... O=C (분자내)
                ArrowData("full", "lone_pair", "O-H (peracid)",
                          "atom", "O (carbonyl)", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # H-bond pre-org
            ],
            labels={"H-bond": "5원 고리 사전배열", "distal O": "친전자성 증가"},
            energy_label="사전배열 상태",
            reagents="mCPBA (meta-클로로퍼벤조산), CH₂Cl₂",
            solvent="CH₂Cl₂ (디클로로메탄)",
            temperature="0°C → rt",
            notes="이온성 중간체 없음. 분자내 H-결합이 친전자성 증가시킴.",
        ),
        MechanismStep(
            step_number=2,
            title="나비 전이 상태: π-공격 + O-O 개열 + 양성자 이동 (협동)",
            description=(
                "사전배열된 mCPBA에서 알켄의 C=C π-결합 전자쌍이 친전자적 distal O를 공격합니다.\n"
                "나비(butterfly) 전이 상태: 5개 원자가 동시에 재배열.\n"
                "  - C=C π-결합 → C-O 결합 2개 형성 (에폭시드 골격)\n"
                "  - O-O 결합 이종(heterolytic) 개열 (proximal O에 lone pair)\n"
                "  - O-H 양성자 → 카르복실산의 C=O 산소로 이동 (1,3-shift)\n"
                "이 모든 결합 변화가 한 단계에서 동시에 일어나 syn 첨가 보장 → 입체배치 보존.\n"
                "더 전자 밀도가 높은(더 치환된) 알켄이 더 빠르게 반응 (HOMO 에너지 ↑)."
            ),
            reactant_smiles="C=C.OO",
            product_smiles="C1CO1.O",
            arrows=[
                # π-결합이 distal O 공격
                ArrowData("full", "pi_bond", "C=C π-결합",
                          "atom", "O (distal, 친전자)", "#E53935", 0.5,
                          from_atom_idx=0, to_atom_idx=2),  # π→O
                # O-O 결합 개열 → proximal O로 lone pair
                ArrowData("full", "bond", "O-O 결합",
                          "atom", "O (proximal, 카르복실 측)", "#1565C0", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # O-O 개열
                # distal O lone pair → C2 (에폭시드 형성)
                ArrowData("full", "lone_pair", "O (distal) lone pair",
                          "bond", "C-O (에폭시드 형성)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=1),  # O→C2
            ],
            labels={"C=C": "π-결합 (HOMO)", "distal O": "친전자체",
                    "TS": "‡ butterfly", "1,3-H shift": "양성자 이동"},
            is_transition_state=True,
            energy_label="ΔG‡ butterfly TS",
            reagents="mCPBA (active form)",
            notes="협동 기전: 5개 원자 동시 재배열. ΔG‡ ≈ 12-18 kcal/mol",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 에폭시드 + mCBA 분리",
            description=(
                "에폭시드(epoxide)가 형성되고, mCPBA는 mCBA(meta-클로로벤조산)로 환원됩니다.\n"
                "  - 에폭시드: 3원 고리 (C-O-C) — strain 27 kcal/mol\n"
                "  - mCBA: 부생성물 (carboxylic acid, water-washable)\n"
                "  - 양성자 이동 결과: peracid의 O-H가 mCBA의 C=O-H로 이동\n"
                "입체화학 분석:\n"
                "  - cis-알켄 → cis-에폭시드 (R,S 또는 S,R)\n"
                "  - trans-알켄 → trans-에폭시드 (R,R 또는 S,S)\n"
                "  - syn 첨가이므로 반응물의 입체 관계가 그대로 보존됩니다.\n"
                "후처리: NaHCO₃ 수용액 세척으로 mCBA 제거. 에폭시드 추출 후 정제."
            ),
            reactant_smiles="C1CO1.OC(=O)c1cccc(Cl)c1",
            product_smiles="C1CO1.OC(=O)c1cccc(Cl)c1",
            arrows=[],  # 분리 단계 — 화살표 없음 (이미 모든 결합 형성 완료)
            labels={"에폭시드": "주생성물 (3원 고리)", "mCBA": "부생성물 (수용성)"},
            energy_label="안정한 생성물",
            byproducts=["mCBA (meta-클로로벤조산)"],
            notes="입체특이적: cis→cis, trans→trans. NaHCO₃ 세척으로 mCBA 제거.",
        ),
    ],
    energy_diagram=[
        ("반응물\n알켄 + mCPBA", 0.0),
        ("사전배열\n(H-bond)", 3.0),  # M561: 사전배열 단계 추가
        ("나비 TS\n(butterfly)", 14.0),
        ("생성물\n에폭시드 + mCBA", -15.0),
    ],
)


# ─── Fischer Esterification (Acid-Catalyzed) ────────────────────────────────
# 대표: RCOOH + R'OH + H⁺ → RCOOR' + H₂O
# 기출: Ch 19-23 (2009-26, 2010-37, 2013-36, 2016-A 기입5)

MECHANISMS["fischer_esterification"] = MechanismData(
    mechanism_type="fischer_esterification",
    title="Fischer 에스터화 (산촉매, 사면체 중간체)",
    total_steps=4,
    overall_description=(
        "카르복실산과 알코올이 산촉매(H₂SO₄) 하에서 반응하여 에스터와 물을 생성합니다. "
        "핵심: 사면체 중간체(tetrahedral intermediate)를 거치는 친핵 아실 치환(nucleophilic acyl substitution). "
        "가역반응이므로 Le Chatelier 원리(생성물 제거 또는 반응물 과량)로 평형을 이동시킵니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="카르보닐 양성자화 → 옥소카르베늄 이온 활성화",
            description=(
                "산촉매(H⁺)가 카르보닐 산소를 양성자화합니다.\n"
                "C=O⁺H: 카르보닐 탄소의 친전자성이 크게 증가합니다.\n"
                "양성자화되지 않은 카르보닐보다 친핵체 공격이 ~10⁴배 용이."
            ),
            reactant_smiles="CC(=O)O",
            product_smiles="CC(=[OH+])O",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "C=O 산소", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),  # H+→O
            ],
            labels={"C=O": "카르보닐", "H⁺": "산촉매"},
            energy_label="활성화",
            reagents="H₂SO₄ (촉매)",
            notes="카르보닐 양성자화 → 친전자성 증가",
        ),
        MechanismStep(
            step_number=2,
            title="알코올 친핵 공격 → 사면체 중간체",
            description=(
                "알코올(R'OH)의 산소 론페어가 양성자화된 카르보닐 탄소를 공격합니다.\n"
                "C=O π-결합이 끊어지고 사면체 중간체가 형성됩니다.\n"
                "사면체 중간체: 탄소가 4개의 산소 관련 치환기에 결합."
            ),
            reactant_smiles="CC(=[OH+])O.CO",
            product_smiles="CC([OH+])(O)OC",
            arrows=[
                ArrowData("full", "lone_pair", "R'OH 론페어",
                          "atom", "C (친전자, δ++)", "#4CAF50", 0.4,
                          from_atom_idx=4, to_atom_idx=0),  # ROH→C
                ArrowData("full", "pi_bond", "C=O⁺H",
                          "atom", "OH (카르보닐)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C=O→OH
            ],
            labels={"ROH": "친핵체 (알코올)", "C": "sp3 사면체"},
            energy_label="사면체 중간체",
            notes="친핵 아실 치환의 핵심 단계",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 이동 + OH 이탈 준비",
            description=(
                "사면체 중간체 내에서 양성자 이동이 일어납니다.\n"
                "카르복실산의 원래 OH가 양성자화 → H₂O(좋은 이탈기)로 활성화.\n"
                "새 알코올의 OH₂⁺가 아닌, 원래 COOH의 OH가 이탈."
            ),
            reactant_smiles="CC([OH+])(O)OC",
            product_smiles="CC(=[OH+])OC.O",
            arrows=[
                ArrowData("full", "lone_pair", "OH 론페어 (이탈기)",
                          "atom", "H⁺ 이동", "#E53935", 0.3,
                          from_atom_idx=3, to_atom_idx=-1),
                ArrowData("full", "bond", "C-OH₂ 결합",
                          "atom", "H₂O (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=3),  # C-OH₂→H₂O
            ],
            labels={"H₂O": "이탈기"},
            energy_label="이탈 단계",
            notes="가역: H₂O 제거(Dean-Stark) → 평형 이동",
        ),
        MechanismStep(
            step_number=4,
            title="탈양성자화 → 에스터 생성물",
            description=(
                "에스터의 양성자화된 카르보닐이 탈양성자화됩니다.\n"
                "산촉매 재생: H⁺가 반환.\n"
                "최종 생성물: 에스터(RCOOR') + H₂O.\n"
                "가역반응이므로 Le Chatelier 원리 적용."
            ),
            reactant_smiles="CC(=[OH+])OC",
            product_smiles="CC(=O)OC",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (염기)",
                          "atom", "H⁺ (카르보닐)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
            ],
            labels={"생성물": "에스터 + H₂O"},
            energy_label="생성물",
            reagents="H₂SO₄ 재생 (촉매 순환)",
            notes="가역 반응: 에스터 + H₂O ⇌ 카르복실산 + 알코올",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOOH + R'OH", 0.0),
        ("양성자화 카르보닐", -2.0),
        ("TS: 친핵 공격", 18.0),
        ("사면체 중간체", 5.0),
        ("TS: H₂O 이탈", 16.0),
        ("생성물\nRCOOR' + H₂O", -1.0),
    ],
)


# ─── NaBH4 REDUCTION ────────────────────────────────────────────────────────
# 대표 반응: RCHO + NaBH₄ → RCH₂OH (1차 알코올) / RCOR' + NaBH₄ → RCHOHR'(2차 알코올)
# McMurry Ch17/19: 선택적 환원 — 카르보닐만 환원, 에스터/카르복실산은 환원하지 않음

MECHANISMS["nabh4_reduction"] = MechanismData(
    mechanism_type="nabh4_reduction",
    title="NaBH₄ 환원 (Sodium Borohydride Reduction)",
    total_steps=3,
    overall_description=(
        "NaBH₄는 온건한 하이드라이드 환원제로, 알데하이드와 케톤의 카르보닐(C=O)을 선택적으로 환원합니다. "
        "에스터나 카르복실산은 환원하지 않습니다(LUMO 에너지 차이). "
        "BH₄⁻의 B-H 결합에서 하이드라이드(H⁻)가 카르보닐 탄소에 친핵 공격하여 "
        "알콕사이드 중간체를 형성하고, 이후 양성자 처리(H₃O⁺)로 알코올이 됩니다. "
        "MeOH/EtOH 용매 중에서 0°C~RT 조건으로 수행합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="하이드라이드 전달 (H⁻ → C=O)",
            description=(
                "BH₄⁻의 B-H σ-결합이 하이드라이드(H⁻)를 공급합니다.\n"
                "H⁻가 카르보닐 탄소(δ+)에 친핵 공격: 1,2-첨가.\n"
                "C=O π-결합이 끊어지면서 산소에 음전하 발생 → 알콕사이드 형성.\n"
                "BH₄⁻ 1당량으로 최대 4개의 카르보닐을 환원 가능 (순차적 H 전달)."
            ),
            reactant_smiles="CC=O.[Na+].[BH4-]",
            product_smiles="CC([H])[O-].[Na+].B",
            arrows=[
                ArrowData("full", "bond", "B-H σ-결합 (하이드라이드)",
                          "atom", "C (카르보닐, δ+)", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=0),  # BH4→C
                ArrowData("full", "pi_bond", "C=O π-결합",
                          "atom", "O (론페어 수용)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C=O→O⁻
            ],
            labels={"BH₄⁻": "환원제 (하이드라이드 공급원)", "C=O": "기질 (전자 수용체)"},
            energy_label="전이 상태: 4원 고리 TS",
            reagents="NaBH₄, MeOH, 0°C",
            notes="NaBH₄ 선택성: 알데하이드/케톤만 환원, 에스터/아마이드 미반응",
        ),
        MechanismStep(
            step_number=2,
            title="알콕사이드 중간체",
            description=(
                "사면체 알콕사이드(RCH₂O⁻ 또는 R₂CHO⁻) 중간체가 형성됩니다.\n"
                "카르보닐 탄소: sp2 → sp3 혼성화 변환.\n"
                "BH₃ (보레인)이 부산물로 생성 → 용매의 다음 카르보닐과 반응 가능."
            ),
            reactant_smiles="CC([H])[O-]",
            product_smiles="CC([H])[O-]",
            arrows=[],
            labels={"알콕사이드": "RCH₂O⁻"},
            energy_label="중간체 (안정)",
            notes="BH₃ + 3 C=O → 추가 하이드라이드 전달 가능",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 처리 → 알코올 생성",
            description=(
                "산성 수용액 처리(H₃O⁺)로 알콕사이드가 양성자화됩니다.\n"
                "RCH₂O⁻ + H₃O⁺ → RCH₂OH + H₂O.\n"
                "최종 생성물: 1차 알코올(알데하이드 기질) 또는 2차 알코올(케톤 기질)."
            ),
            reactant_smiles="CC([H])[O-]",
            product_smiles="CCO",
            arrows=[
                ArrowData("full", "lone_pair", "H₃O⁺",
                          "atom", "O⁻ (알콕사이드)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
            ],
            labels={"H₃O⁺": "양성자 공급원"},
            energy_label="생성물",
            reagents="H₃O⁺ (산성 처리)",
            notes="알데하이드 → 1차 알코올, 케톤 → 2차 알코올",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCHO + NaBH₄", 0.0),
        ("TS: H⁻ 전달", 12.0),
        ("알콕사이드\nRCH₂O⁻", -15.0),
        ("생성물\nRCH₂OH", -20.0),
    ],
)


# ─── LiAlH4 REDUCTION ──────────────────────────────────────────────────────
# 대표 반응: RCOOR' + LiAlH₄ → RCH₂OH + R'OH
# McMurry Ch17/19: 강력한 하이드라이드 — 에스터, 카르복실산, 아마이드 모두 환원

MECHANISMS["lialh4_reduction"] = MechanismData(
    mechanism_type="lialh4_reduction",
    title="LiAlH₄ 환원 (Lithium Aluminium Hydride Reduction)",
    total_steps=3,
    overall_description=(
        "LiAlH₄는 매우 강력한 하이드라이드 환원제입니다. NaBH₄와 달리 에스터, 카르복실산, "
        "아마이드까지 환원합니다. Al-H 결합의 높은 극성(Al δ+, H δ-)으로 인해 하이드라이드 "
        "반응성이 매우 높습니다. 무수 조건(Et₂O 또는 THF)에서만 사용 — H₂O/알코올과 격렬히 "
        "반응하여 H₂ 가스를 발생시킵니다. 에스터 환원 시 2당량의 H⁻가 전달됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="1차 하이드라이드 전달 → 사면체 중간체",
            description=(
                "AlH₄⁻의 Al-H 결합에서 H⁻가 에스터 카르보닐 탄소(δ+)에 친핵 공격합니다.\n"
                "C=O π-결합이 끊어져 사면체 중간체가 형성됩니다.\n"
                "Al-H의 높은 극성으로 NaBH₄보다 ~100배 강한 하이드라이드 전달."
            ),
            reactant_smiles="CC(=O)OC.[Li+].[AlH4-]",
            product_smiles="CC([H])([O-])OC.[Li+].[AlH3]",
            arrows=[
                ArrowData("full", "bond", "Al-H σ-결합",
                          "atom", "C (카르보닐, δ+)", "#E53935", 0.4,
                          from_atom_idx=5, to_atom_idx=0),  # AlH4→C
                ArrowData("full", "pi_bond", "C=O π-결합",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C=O→O
            ],
            labels={"AlH₄⁻": "강환원제", "C=O": "에스터 카르보닐"},
            energy_label="TS: 1차 H⁻ 전달",
            reagents="LiAlH₄, Et₂O (무수 조건)",
            notes="에스터 환원의 첫 번째 단계: 사면체 중간체 → R'O⁻ 이탈 예정",
        ),
        MechanismStep(
            step_number=2,
            title="알콕사이드 이탈 → 알데하이드 + 2차 H⁻ 전달",
            description=(
                "사면체 중간체에서 R'O⁻(알콕사이드)가 이탈 → 알데하이드 중간체 형성.\n"
                "알데하이드는 매우 반응성이 높아 즉시 2차 H⁻ 전달을 받습니다.\n"
                "결과: 알데하이드가 1차 알콕사이드로 환원.\n"
                "에스터 → 알데하이드 → 1차 알코올 (2단계 환원)."
            ),
            reactant_smiles="CC([H])([O-])OC",
            product_smiles="CC([H])([H])[O-]",
            arrows=[
                ArrowData("full", "lone_pair", "R'O⁻ 론페어",
                          "bond", "C-O 결합 (이탈)", "#E53935", 0.3,
                          from_atom_idx=3, to_atom_idx=0),  # RO⁻ departure
                ArrowData("full", "bond", "Al-H (2차 H⁻)",
                          "atom", "C (알데하이드)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),  # 2nd H⁻→C
            ],
            labels={"R'O⁻": "이탈기 (알콕사이드)", "CHO": "알데하이드 중간체 (순간적)"},
            energy_label="TS: 2차 H⁻ 전달",
            notes="알데하이드 중간체는 반응 조건에서 즉시 환원됨 → 분리 불가",
        ),
        MechanismStep(
            step_number=3,
            title="양성자 처리 → 1차 알코올",
            description=(
                "반응 완료 후 주의 깊은 양성자 처리가 필요합니다.\n"
                "1) 먼저 H₂O를 소량씩 적가 (과잉 LiAlH₄ 분해: LiAlH₄ + 4H₂O → LiOH + Al(OH)₃ + 4H₂↑)\n"
                "2) 그 다음 NaOH 수용액 또는 묽은 H₂SO₄로 알콕사이드 양성자화.\n"
                "최종: RCH₂OH (1차 알코올) + R'OH (부산물 알코올)."
            ),
            reactant_smiles="CC([H])([H])[O-]",
            product_smiles="CCO",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O",
                          "atom", "O⁻ (알콕사이드)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
            ],
            labels={"H₃O⁺": "양성자 처리 (주의 필요)"},
            energy_label="생성물",
            reagents="1) H₂O (소량) 2) NaOH aq 또는 묽은 H₂SO₄",
            notes="에스터 → 1차 알코올 (2 H⁻), 카르복실산 → 1차 알코올 (2 H⁻), 아마이드 → 아민 (2 H⁻)",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOOR' + LiAlH₄", 0.0),
        ("TS: 1차 H⁻ 전달", 10.0),
        ("사면체 중간체", -5.0),
        ("알데하이드 + R'O⁻", 8.0),
        ("TS: 2차 H⁻ 전달", 6.0),
        ("알콕사이드", -20.0),
        ("생성물\nRCH₂OH", -25.0),
    ],
)


# ─── CATALYTIC HYDROGENATION ───────────────────────────────────────────────
# 대표 반응: R₂C=CR₂ + H₂ → R₂CH-CHR₂ (Pd/C, Pt, 또는 Ni 촉매)
# McMurry Ch7-8: syn-첨가, 금속 표면에서 동시 수소 전달

MECHANISMS["catalytic_hydrogenation"] = MechanismData(
    mechanism_type="catalytic_hydrogenation",
    title="촉매적 수소화 (Catalytic Hydrogenation, H₂/Pd)",
    total_steps=3,
    overall_description=(
        "알켄, 알카인, 방향족 등의 불포화 결합을 H₂ + 금속 촉매(Pd/C, Pt, Ni)로 환원합니다. "
        "금속 표면에 H₂와 기질이 모두 흡착된 후, 같은 면(syn)에서 두 수소가 동시에 전달됩니다. "
        "Lindlar 촉매(Pd/CaCO₃/Pb(OAc)₂)는 알카인을 cis-알켄까지만 환원(부분 수소화)합니다. "
        "이종 촉매 반응: 반응이 금속 표면에서 진행."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="H₂ + 기질 흡착 → 금속 표면 활성화",
            description=(
                "H₂ 분자가 금속 표면(Pd, Pt)에 흡착(dissociative chemisorption)됩니다.\n"
                "H-H σ-결합이 끊어지고 두 수소 원자가 금속에 개별 결합합니다 (M-H).\n"
                "동시에 알켄의 π-결합이 금속 표면에 배위(π-complexation)합니다.\n"
                "금속 d-오비탈 → 알켄 π* (반결합)로 역공여(back-donation)."
            ),
            reactant_smiles="C=C.[HH]",
            product_smiles="C=C.[HH]",
            arrows=[
                ArrowData("full", "bond", "H-H σ-결합",
                          "atom", "Pd 표면", "#E53935", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),  # H₂ → surface
                ArrowData("full", "pi_bond", "C=C π-결합",
                          "atom", "Pd 표면 (배위)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=-1),  # alkene → surface
            ],
            labels={"Pd": "이종 촉매", "H₂": "수소 기체 (1 atm)"},
            energy_label="흡착 단계",
            reagents="H₂ (1 atm), Pd/C",
            notes="Chemisorption: H₂ 해리 + 알켄 π-배위 (금속 표면)",
        ),
        MechanismStep(
            step_number=2,
            title="수소 전달 (syn-첨가)",
            description=(
                "금속 표면에 흡착된 두 수소 원자가 알켄의 같은 면(syn face)에서 전달됩니다.\n"
                "첫 번째 H가 한쪽 탄소에, 두 번째 H가 다른 쪽 탄소에 거의 동시에 결합합니다.\n"
                "syn-첨가: 두 수소가 같은 면에서 추가 → 입체화학적으로 중요.\n"
                "π-결합이 완전히 끊어지고 두 새로운 C-H σ-결합이 형성."
            ),
            reactant_smiles="C=C",
            product_smiles="CC",
            arrows=[
                ArrowData("full", "bond", "Pd-H (표면)",
                          "atom", "C₁ (알켄)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=0),  # H→C1
                ArrowData("full", "bond", "Pd-H (표면)",
                          "atom", "C₂ (알켄)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),  # H→C2
            ],
            labels={"syn": "같은 면 첨가"},
            is_transition_state=True,
            energy_label="TS: syn-수소 전달",
            notes="syn-첨가 → cis 입체화학 (알카인 → cis-알켄 가능 with Lindlar)",
        ),
        MechanismStep(
            step_number=3,
            title="생성물 탈착 → 알칸",
            description=(
                "수소화된 생성물(알칸)이 금속 표면에서 탈착(desorption)됩니다.\n"
                "촉매 표면이 재생되어 다음 반응 사이클 진행 가능.\n"
                "최종 생성물: 알칸(완전 수소화) 또는 cis-알켄(Lindlar 부분 수소화)."
            ),
            reactant_smiles="CC",
            product_smiles="CC",
            arrows=[],
            labels={"생성물": "알칸 (포화)"},
            energy_label="생성물 (탈착)",
            reagents="촉매 재생",
            notes="Lindlar (Pd/CaCO₃/Pb(OAc)₂): 알카인→cis-알켄 선택적 정지",
        ),
    ],
    energy_diagram=[
        ("반응물\nR₂C=CR₂ + H₂", 0.0),
        ("흡착 복합체", -5.0),
        ("TS: H 전달", 8.0),
        ("생성물\nR₂CH-CHR₂", -30.0),
    ],
)


# ─── PCC OXIDATION ──────────────────────────────────────────────────────────
# 대표 반응: RCH₂OH → RCHO (1차 → 알데하이드에서 정지)
# McMurry Ch17: PCC(Pyridinium Chlorochromate)는 1차 알코올을 알데하이드까지만 산화

MECHANISMS["pcc_oxidation"] = MechanismData(
    mechanism_type="pcc_oxidation",
    title="PCC 선택적 산화 (Pyridinium Chlorochromate Oxidation)",
    total_steps=3,
    overall_description=(
        "PCC(C₅H₅NH⁺·CrO₃Cl⁻)는 1차 알코올을 알데하이드까지만 선택적으로 산화하는 시약입니다. "
        "Jones 산화(CrO₃/H₂SO₄)와 달리 무수 CH₂Cl₂ 용매를 사용하므로 "
        "카르복실산까지 과산화되지 않습니다. Cr(VI) → Cr(IV): 2전자 산화. "
        "크로메이트 에스터를 경유하는 E2-유사 β-제거 메커니즘."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="크로메이트 에스터 형성",
            description=(
                "알코올의 산소가 Cr(VI) 중심에 친핵 공격하여 크로메이트 에스터를 형성합니다.\n"
                "R-OH + CrO₃Cl⁻ → R-O-CrO₂Cl + Cl⁻.\n"
                "Cr-Cl 결합이 끊어지면서 Cr-O-R 에스터 결합이 형성."
            ),
            reactant_smiles="CCO.[O-][Cr](=O)(=O)Cl",
            product_smiles="CCO[Cr](=O)(=O)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "R-OH 론페어",
                          "atom", "Cr(VI) 중심", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=3),  # O→Cr
                ArrowData("full", "bond", "Cr-Cl 결합",
                          "atom", "Cl⁻ (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=6),  # Cr-Cl→Cl
            ],
            labels={"PCC": "CrO₃Cl⁻ (산화제)", "ROH": "1차 알코올 (기질)"},
            energy_label="크로메이트 에스터",
            reagents="PCC, CH₂Cl₂ (무수)",
            notes="무수 조건이 핵심 — H₂O 존재 시 과산화 위험",
        ),
        MechanismStep(
            step_number=2,
            title="E2-유사 β-수소 제거 (속도 결정 단계)",
            description=(
                "염기(피리딘 또는 Cl⁻)가 α-탄소의 C-H를 추출합니다 (β-제거).\n"
                "동시에 C-O-Cr 결합이 끊어지면서 C=O 이중결합 형성.\n"
                "E2-유사 동시 메커니즘: B:→H + C-H→C=O + O-Cr→Cr(IV).\n"
                "속도 결정 단계: 1차 동위원소 효과(kH/kD ≈ 6) 관찰."
            ),
            reactant_smiles="CCO[Cr](=O)(=O)Cl",
            product_smiles="CC=O.O[Cr](=O)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "B: (염기, 피리딘)",
                          "atom", "α-H", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),  # base→H
                ArrowData("full", "bond", "C-H σ-결합",
                          "pi_bond", "C=O 형성", "#E53935", 0.3,
                          from_atom_idx=0, to_atom_idx=1),  # C-H→C=O
                ArrowData("full", "bond", "O-Cr 결합",
                          "atom", "Cr(IV) (환원)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # O-Cr→Cr(IV)
            ],
            labels={"B:": "염기 (피리딘/Cl⁻)", "α-H": "beta 제거 대상"},
            is_transition_state=True,
            energy_label="TS: β-제거 (RDS)",
            reagents="피리딘 (내부 염기)",
            notes="kH/kD ≈ 6: 1차 동위원소 효과 → C-H 절단이 속도 결정",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 알데하이드 (과산화 없음)",
            description=(
                "알데하이드(RCHO)가 최종 생성물로 형성됩니다.\n"
                "Cr(VI) → Cr(IV)로 환원 (2전자 산화).\n"
                "무수 CH₂Cl₂ 용매 때문에 알데하이드의 수화물 형성이 불가 → 과산화 방지.\n"
                "Jones 산화(CrO₃/H₂SO₄/H₂O)와의 차이점: H₂O가 있으면 알데하이드 수화물 → RCOOH."
            ),
            reactant_smiles="CC=O",
            product_smiles="CC=O",
            arrows=[],
            labels={"생성물": "알데하이드 (RCHO)"},
            energy_label="생성물",
            notes="PCC 선택성: 1차 알코올→알데하이드(정지) / 2차 알코올→케톤",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCH₂OH + PCC", 0.0),
        ("크로메이트 에스터", -3.0),
        ("TS: β-제거 (RDS)", 18.0),
        ("생성물\nRCHO + Cr(IV)", -10.0),
    ],
)


# ─── WILLIAMSON ETHER SYNTHESIS ─────────────────────────────────────────────
# 대표 반응: R-O⁻ + R'-X → R-O-R' (SN2)
# McMurry Ch18: 에테르 합성의 가장 일반적인 방법

MECHANISMS["williamson_ether"] = MechanismData(
    mechanism_type="williamson_ether",
    title="Williamson 에테르 합성 (Williamson Ether Synthesis)",
    total_steps=2,
    overall_description=(
        "Williamson 에테르 합성은 알콕사이드(R-O⁻)가 1차 할라이드(R'-X)에 SN2 공격하여 "
        "에테르(R-O-R')를 형성하는 반응입니다. 알코올을 먼저 NaH 또는 Na 금속으로 탈양성자화하여 "
        "알콕사이드를 만든 후, 1차 알킬 할라이드와 반응시킵니다. "
        "SN2 메커니즘이므로 1차 할라이드가 최적이며, 2차/3차에서는 E2 부반응이 우세합니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="알콕사이드 형성 (전처리)",
            description=(
                "알코올(R-OH)을 강염기(NaH)로 탈양성자화하여 알콕사이드(R-O⁻)를 형성합니다.\n"
                "NaH + R-OH → R-O⁻Na⁺ + H₂↑.\n"
                "NaH의 H⁻가 알코올의 O-H 양성자를 추출.\n"
                "이 단계는 비가역적: H₂ 기체가 방출되어 평형이 생성물 쪽으로 완전히 치우침."
            ),
            reactant_smiles="CO.[NaH]",
            product_smiles="C[O-].[Na+]",
            arrows=[
                ArrowData("full", "bond", "Na-H (하이드라이드)",
                          "atom", "O-H 양성자", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=1),  # NaH→OH
                ArrowData("full", "bond", "O-H 결합",
                          "atom", "O⁻ (알콕사이드)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=1),  # O-H→O⁻
            ],
            labels={"NaH": "강염기 (비친핵성)", "ROH": "알코올"},
            energy_label="탈양성자화",
            reagents="NaH, THF (무수)",
            notes="NaH는 비친핵성 강염기 — 직접 치환 반응하지 않음",
        ),
        MechanismStep(
            step_number=2,
            title="SN2 에테르 형성",
            description=(
                "알콕사이드(R-O⁻)의 론페어가 1차 알킬 할라이드의 탄소를 후면 공격합니다.\n"
                "전형적인 SN2 메커니즘: 동시 결합 형성/절단.\n"
                "R-O⁻ + R'-CH₂Br → R-O-CH₂R' + Br⁻.\n"
                "입체 반전(Walden 전환) 발생."
            ),
            reactant_smiles="C[O-].CCBr",
            product_smiles="COCC.[Br-]",
            arrows=[
                ArrowData("full", "lone_pair", "R-O⁻ 론페어",
                          "atom", "C (δ+, 1차)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=2),  # O⁻→C
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br⁻ (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # C-Br→Br⁻
            ],
            labels={"R-O⁻": "친핵체 (알콕사이드)", "R'-Br": "친전자체 (1차 할라이드)"},
            is_transition_state=True,
            energy_label="TS: SN2 (동시)",
            reagents="THF, RT",
            notes="2차/3차 할라이드 사용 시 E2 우세 → 에테르 수율 급감",
        ),
    ],
    energy_diagram=[
        ("반응물\nR-O⁻ + R'-Br", 0.0),
        ("TS: SN2 공격", 15.0),
        ("생성물\nR-O-R' + Br⁻", -10.0),
    ],
)


# ─── ACETAL FORMATION ───────────────────────────────────────────────────────
# 대표 반응: RCHO + 2 R'OH → RCH(OR')₂ + H₂O (산촉매)
# McMurry Ch19: 카르보닐 보호기, 아세탈 형성

MECHANISMS["acetal_formation"] = MechanismData(
    mechanism_type="acetal_formation",
    title="아세탈 형성 (Acetal Formation, 카르보닐 보호)",
    total_steps=4,
    overall_description=(
        "알데하이드 또는 케톤에 2당량의 알코올이 산촉매 하에서 반응하여 아세탈을 형성합니다. "
        "가역 반응으로, 물을 제거(Dean-Stark)하면 아세탈 방향으로 진행합니다. "
        "1당량 알코올 반응 → 헤미아세탈(불안정), 2당량 → 아세탈(안정). "
        "아세탈은 카르보닐 보호기로 광범위하게 사용됩니다: 염기성/친핵성 조건에서 안정, "
        "산성 조건에서만 탈보호."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="카르보닐 양성자화 → 활성화",
            description=(
                "산촉매(H⁺)가 카르보닐 산소를 양성자화합니다.\n"
                "C=O⁺H: 카르보닐 탄소의 친전자성 증가.\n"
                "양성자화에 의해 알코올의 친핵 공격이 용이."
            ),
            reactant_smiles="CC=O",
            product_smiles="CC=[OH+]",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (산촉매)",
                          "atom", "C=O 산소", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
            ],
            labels={"H⁺": "산촉매", "C=O": "카르보닐"},
            energy_label="양성자화",
            reagents="H⁺ (p-TsOH), 무수 조건",
            notes="산촉매량: 촉매량으로 충분",
        ),
        MechanismStep(
            step_number=2,
            title="1차 알코올 공격 → 헤미아세탈",
            description=(
                "알코올(R'OH)의 산소 론페어가 활성화된 카르보닐 탄소를 공격합니다.\n"
                "C=O π-결합 끊어짐 → 사면체 중간체(헤미아세탈) 형성.\n"
                "양성자 이동 + 탈양성자화 → 헤미아세탈(R-CH(OH)(OR')).\n"
                "헤미아세탈은 불안정 — 산성 조건에서 즉시 다음 단계로 진행."
            ),
            reactant_smiles="CC=[OH+].CO",
            product_smiles="CC(O)OC",
            arrows=[
                ArrowData("full", "lone_pair", "R'OH 론페어",
                          "atom", "C (카르보닐, δ+)", "#4CAF50", 0.4,
                          from_atom_idx=3, to_atom_idx=0),  # ROH→C
                ArrowData("full", "pi_bond", "C=O⁺H",
                          "atom", "OH", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C=O→OH
            ],
            labels={"R'OH": "1차 알코올 (친핵체)", "헤미아세탈": "불안정 중간체"},
            energy_label="헤미아세탈",
            notes="헤미아세탈: 탄소에 -OH + -OR' 동시 결합",
        ),
        MechanismStep(
            step_number=3,
            title="OH 양성자화 + H₂O 이탈 → 옥소카르베늄 이온",
            description=(
                "헤미아세탈의 OH가 양성자화 → H₂O(좋은 이탈기)로 활성화.\n"
                "H₂O 이탈 → 옥소카르베늄 이온(R-CH=O⁺R') 형성.\n"
                "옥소카르베늄 이온: 산소의 론페어가 양전하를 안정화 (공명 기여)."
            ),
            reactant_smiles="CC(O)OC",
            product_smiles="CC(=[OH+])OC",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "OH (양성자화)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),  # H+→OH
                ArrowData("full", "bond", "C-OH₂⁺ 결합",
                          "atom", "H₂O (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C-OH₂→H₂O
            ],
            labels={"옥소카르베늄": "안정화된 카르보카티온"},
            energy_label="옥소카르베늄 이온",
            notes="옥소카르베늄 이온: O의 론페어 공명으로 안정화",
        ),
        MechanismStep(
            step_number=4,
            title="2차 알코올 공격 → 아세탈 형성",
            description=(
                "두 번째 알코올(R'OH)이 옥소카르베늄 이온을 공격합니다.\n"
                "탈양성자화 → 아세탈(R-CH(OR')₂) 최종 생성물.\n"
                "아세탈: 카르보닐 보호기 — 염기/친핵 조건에서 안정.\n"
                "탈보호: 묽은 산 + H₂O → 원래 카르보닐 재생."
            ),
            reactant_smiles="CC(=[OH+])OC.CO",
            product_smiles="CC(OC)OC",
            arrows=[
                ArrowData("full", "lone_pair", "R'OH 론페어 (2차)",
                          "atom", "C⁺ (옥소카르베늄)", "#4CAF50", 0.4,
                          from_atom_idx=4, to_atom_idx=0),  # ROH→C
            ],
            labels={"아세탈": "R-CH(OR')₂ (보호기)"},
            energy_label="생성물 (아세탈)",
            reagents="H⁺ (cat.), Dean-Stark (H₂O 제거)",
            notes="가역: 산 + H₂O → 탈보호(카르보닐 재생). 1,3-디올 사용 → 환형 아세탈",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCHO + 2R'OH", 0.0),
        ("양성자화 카르보닐", -2.0),
        ("TS: 1차 ROH 공격", 14.0),
        ("헤미아세탈", -3.0),
        ("옥소카르베늄", 10.0),
        ("TS: 2차 ROH 공격", 12.0),
        ("생성물\nRCH(OR')₂ + H₂O", -5.0),
    ],
)


# ─── IMINE FORMATION (Schiff Base) ─────────────────────────────────────────
# 대표 반응: RCHO + R'NH₂ → RCH=NR' + H₂O
# McMurry Ch19: 1차 아민과 카르보닐의 축합

MECHANISMS["imine_formation"] = MechanismData(
    mechanism_type="imine_formation",
    title="이민 형성 (Schiff 염기, Imine Formation)",
    total_steps=3,
    overall_description=(
        "1차 아민(R'NH₂)이 알데하이드 또는 케톤과 반응하여 이민(Schiff 염기, RCH=NR')을 형성합니다. "
        "약산성 조건(pH 4-5)이 최적: 너무 산성이면 아민 양성자화, 너무 염기성이면 탈수 느림. "
        "카르비놀아민(aminol) 중간체를 경유하며, 탈수 단계가 속도 결정. "
        "이민은 환원적 아민화(NaBH₃CN), 아자-Wittig 등 다양한 반응에 활용됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아민 친핵 공격 → 카르비놀아민",
            description=(
                "1차 아민(R'NH₂)의 질소 론페어가 카르보닐 탄소(δ+)에 친핵 공격합니다.\n"
                "C=O π-결합 끊어짐 → 사면체 카르비놀아민(aminol) 중간체 형성.\n"
                "R-CH(OH)(NHR') — 탄소에 -OH와 -NHR'이 동시에 결합한 상태."
            ),
            reactant_smiles="CC=O.CN",
            product_smiles="CC(O)NC",
            arrows=[
                ArrowData("full", "lone_pair", "R'NH₂ 론페어",
                          "atom", "C (카르보닐, δ+)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=0),  # N→C
                ArrowData("full", "pi_bond", "C=O π-결합",
                          "atom", "O⁻ → OH (양성자화)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C=O→O
            ],
            labels={"R'NH₂": "1차 아민 (친핵체)", "카르비놀아민": "aminol 중간체"},
            energy_label="카르비놀아민 (사면체 중간체)",
            reagents="pH 4-5 (약산성), RT",
            notes="카르비놀아민 = aminol = hemiaminal",
        ),
        MechanismStep(
            step_number=2,
            title="OH 양성자화 → 탈수 (속도 결정 단계)",
            description=(
                "카르비놀아민의 OH가 양성자화되어 H₂O(좋은 이탈기)가 됩니다.\n"
                "H₂O가 이탈하면서 이미늄 이온(R-CH=N⁺HR') 형성.\n"
                "질소의 론페어가 양전하를 안정화 → 이미늄 이온은 비교적 안정.\n"
                "이 탈수 단계가 속도 결정(RDS): pH에 민감."
            ),
            reactant_smiles="CC(O)NC",
            product_smiles="CC(=[NH+]C).[OH2]",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (산촉매)",
                          "atom", "OH (양성자화)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),  # H+→OH
                ArrowData("full", "bond", "C-OH₂⁺ 결합",
                          "atom", "H₂O (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C-OH₂→H₂O
                ArrowData("full", "lone_pair", "N 론페어",
                          "pi_bond", "C=N⁺ 형성", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=0),  # N→C=N
            ],
            labels={"이미늄 이온": "R-CH=N⁺HR'"},
            is_transition_state=True,
            energy_label="TS: 탈수 (RDS)",
            notes="pH 4-5 최적: 낮은 pH → NH₃⁺R' (비반응), 높은 pH → 탈수 느림",
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자화 → 이민 (Schiff 염기)",
            description=(
                "이미늄 이온의 N-H가 탈양성자화되어 중성 이민(RCH=NR')이 형성됩니다.\n"
                "최종 생성물: Schiff 염기 + H₂O.\n"
                "이민은 NaBH₃CN로 환원 → 아민(환원적 아민화).\n"
                "2차 아민 사용 시: 이미늄 이온에서 정지(엔아민 형성 불가에서 탈양성자화)."
            ),
            reactant_smiles="CC(=[NH+]C)",
            product_smiles="CC(=NC)",
            arrows=[
                ArrowData("full", "bond", "N-H 결합",
                          "atom", "B: (염기)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),  # N-H→base
            ],
            labels={"이민": "Schiff 염기 (RCH=NR')"},
            energy_label="생성물 (이민)",
            notes="이민: C=N 이중결합, E/Z 이성질체 가능",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCHO + R'NH₂", 0.0),
        ("TS: N 공격", 12.0),
        ("카르비놀아민", -5.0),
        ("TS: 탈수 (RDS)", 15.0),
        ("이미늄 이온", 5.0),
        ("생성물\nRCH=NR' + H₂O", -3.0),
    ],
)


# ─── ENAMINE FORMATION (Stork) ──────────────────────────────────────────────
# 대표 반응: R₂C(=O)CHR' + R''₂NH → R₂C(=CHR')NR''₂ + H₂O
# McMurry Ch19/23: 2차 아민 + 카르보닐 → 엔아민 (Stork 에나민)

MECHANISMS["enamine_formation"] = MechanismData(
    mechanism_type="enamine_formation",
    title="엔아민 형성 (Stork Enamine Synthesis)",
    total_steps=3,
    overall_description=(
        "2차 아민(R₂NH)이 알데하이드 또는 케톤과 반응하여 엔아민을 형성합니다. "
        "1차 아민의 이민 형성과 유사하지만, 2차 아민에는 N-H가 하나뿐이므로 이민을 형성할 수 없습니다. "
        "대신 이미늄 이온에서 α-탄소의 C-H가 제거되어 엔아민(α,β-불포화 아민)이 됩니다. "
        "엔아민은 Stork 에나민 합성에서 핵심 중간체: 친핵적 α-알킬화/아실화에 사용."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="2차 아민 공격 → 카르비놀아민",
            description=(
                "2차 아민(R₂NH)의 질소 론페어가 카르보닐 탄소에 친핵 공격합니다.\n"
                "C=O π-결합이 끊어지고 카르비놀아민(aminol) 중간체 형성.\n"
                "1차 아민의 경우와 동일한 첫 번째 단계."
            ),
            reactant_smiles="CC(C)=O.C1CCNC1",
            product_smiles="CC(C)(O)N1CCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "R₂NH 론페어",
                          "atom", "C (카르보닐)", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=0),  # N→C
                ArrowData("full", "pi_bond", "C=O π-결합",
                          "atom", "O⁻", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),  # C=O→O
            ],
            labels={"피롤리딘": "2차 아민 (가장 흔한 선택)", "카르보닐": "기질"},
            energy_label="카르비놀아민",
            reagents="p-TsOH (cat.), 톨루엔, Dean-Stark",
            notes="피롤리딘 > 모르폴린 > 디에틸아민 (반응성 순서)",
        ),
        MechanismStep(
            step_number=2,
            title="탈수 → 이미늄 이온",
            description=(
                "카르비놀아민의 OH가 양성자화 → H₂O 이탈 → 이미늄 이온 형성.\n"
                "2차 아민이므로 N에 H가 없음 → 이민(C=NR)을 형성할 수 없습니다.\n"
                "이미늄 이온: R₂N⁺=CHR (질소에 양전하, 결합 회전 제한).\n"
                "이 이미늄 이온에서 α-H 제거가 가능."
            ),
            reactant_smiles="CC(C)(O)N1CCCC1",
            product_smiles="CC(C)=[N+]1CCCC1",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺",
                          "atom", "OH", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
                ArrowData("full", "bond", "C-OH₂⁺",
                          "atom", "H₂O (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=2),
                ArrowData("full", "lone_pair", "N 론페어",
                          "pi_bond", "C=N⁺ 형성", "#4CAF50", 0.3,
                          from_atom_idx=3, to_atom_idx=0),  # N→C=N+
            ],
            labels={"이미늄 이온": "2차 아민 → 이민 불가 → α-H 제거"},
            energy_label="이미늄 이온",
            notes="2차 아민: N-H 없으므로 이민 형성 불가 → 엔아민으로 진행",
        ),
        MechanismStep(
            step_number=3,
            title="α-H 제거 → 엔아민",
            description=(
                "이미늄 이온의 α-탄소에서 C-H 양성자가 제거됩니다.\n"
                "전자쌍이 C=C π-결합 형성에 사용 → 엔아민(α,β-불포화 아민).\n"
                "엔아민: 질소의 론페어가 C=C와 공액 → 강한 친핵체.\n"
                "Stork 합성: 엔아민 + R-X → α-알킬화 → 가수분해 → α-치환 케톤."
            ),
            reactant_smiles="CC(C)=[N+]1CCCC1",
            product_smiles="C/C(=C)\\N1CCCC1",
            arrows=[
                ArrowData("full", "bond", "α-C-H 결합",
                          "atom", "B: (염기)", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=-1),  # α-CH→base
                ArrowData("full", "bond", "C-C σ → C=C π",
                          "pi_bond", "C=C 형성", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=0),  # C-C→C=C
            ],
            labels={"엔아민": "α,β-불포화 아민 (친핵적)"},
            energy_label="생성물 (엔아민)",
            reagents="p-TsOH (cat.), Dean-Stark (H₂O 제거)",
            notes="엔아민 반응성: C=C β-탄소에서 친핵 공격 (Stork 에나민 알킬화/아실화)",
        ),
    ],
    energy_diagram=[
        ("반응물\nR₂C=O + R₂NH", 0.0),
        ("TS: N 공격", 12.0),
        ("카르비놀아민", -4.0),
        ("TS: 탈수", 14.0),
        ("이미늄 이온", 6.0),
        ("생성물\n엔아민 + H₂O", -2.0),
    ],
)


# ─── HELL-VOLHARD-ZELINSKY ──────────────────────────────────────────────────
# 대표 반응: RCH₂COOH + Br₂/PBr₃ → RCHBrCOOH
# McMurry Ch22: α-할로겐화 (카르복실산의 alpha 위치)

MECHANISMS["hell_volhard_zelinsky"] = MechanismData(
    mechanism_type="hell_volhard_zelinsky",
    title="Hell-Volhard-Zelinsky 반응 (α-할로겐화)",
    total_steps=4,
    overall_description=(
        "HVZ 반응은 카르복실산의 α-위치를 선택적으로 할로겐화하는 반응입니다. "
        "PBr₃ 촉매가 카르복실산을 아실 브로마이드로 변환 → 에놀화 가능 → α-브롬화. "
        "카르복실산은 직접 에놀화가 불가능하지만, 아실 할라이드로 변환하면 에놀화가 용이합니다. "
        "최종 가수분해로 α-브로모카르복실산을 얻습니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아실 브로마이드 형성 (PBr₃ 촉매)",
            description=(
                "PBr₃가 카르복실산(-COOH)을 아실 브로마이드(-COBr)로 변환합니다.\n"
                "R-COOH + PBr₃ → R-COBr + HOPBr₂.\n"
                "아실 할라이드의 α-H는 카르복실산보다 에놀화가 훨씬 용이합니다."
            ),
            reactant_smiles="CCC(=O)O.[Br][P]([Br])[Br]",
            product_smiles="CCC(=O)Br",
            arrows=[
                ArrowData("full", "lone_pair", "COOH 론페어",
                          "atom", "P (PBr₃)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=5),  # O→P
                ArrowData("full", "bond", "P-Br 결합",
                          "atom", "Br⁻", "#1565C0", 0.3,
                          from_atom_idx=5, to_atom_idx=4),  # P-Br→Br
            ],
            labels={"PBr₃": "촉매 (카탈리틱 사이클)", "COOH": "기질"},
            energy_label="아실 브로마이드",
            reagents="PBr₃ (촉매량), Br₂",
            notes="PBr₃ 촉매량만으로 충분: 카탈리틱 사이클 형성",
        ),
        MechanismStep(
            step_number=2,
            title="에놀화 → 에놀 형성",
            description=(
                "아실 브로마이드의 α-H가 염기에 의해 추출 → 에놀 형성.\n"
                "아실 할라이드는 카르복실산보다 pKa(α-H)가 ~4단위 낮아 에놀화 용이.\n"
                "에놀의 C=C 이중결합이 친핵적 — Br₂에 반응 가능."
            ),
            reactant_smiles="CCC(=O)Br",
            product_smiles="CC=C(O)Br",
            arrows=[
                ArrowData("full", "bond", "α-C-H",
                          "atom", "B: (염기)", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=-1),  # α-CH→base
                ArrowData("full", "bond", "C-C σ → C=C π",
                          "pi_bond", "에놀 C=C", "#E53935", 0.3,
                          from_atom_idx=1, to_atom_idx=0),  # σ→π
            ],
            labels={"에놀": "친핵적 C=C"},
            energy_label="에놀 중간체",
            notes="에놀화: 아실 할라이드 >> 카르복실산 >> 아마이드",
        ),
        MechanismStep(
            step_number=3,
            title="α-브롬화 (에놀 + Br₂)",
            description=(
                "에놀의 C=C π-전자가 Br₂의 Br-Br σ*를 공격합니다.\n"
                "α-탄소에 Br가 도입되고 Br⁻가 이탈.\n"
                "결과: α-브로모아실 브로마이드 형성.\n"
                "이 단계는 친전자 첨가와 유사한 메커니즘."
            ),
            reactant_smiles="CC=C(O)Br.BrBr",
            product_smiles="CC(Br)C(=O)Br.[Br-]",
            arrows=[
                ArrowData("full", "pi_bond", "에놀 C=C π",
                          "atom", "Br₂ (δ+)", "#E53935", 0.4,
                          from_atom_idx=1, to_atom_idx=4),  # C=C→Br
                ArrowData("full", "bond", "Br-Br σ",
                          "atom", "Br⁻ (이탈)", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=5),  # Br-Br→Br⁻
            ],
            labels={"Br₂": "친전자체", "α-C": "브롬화 위치"},
            energy_label="α-브로모아실 브로마이드",
            notes="α-모노브롬화가 주 생성물 (과할로겐화는 드묾)",
        ),
        MechanismStep(
            step_number=4,
            title="가수분해 → α-브로모카르복실산",
            description=(
                "α-브로모아실 브로마이드를 H₂O로 가수분해합니다.\n"
                "R-CHBr-COBr + H₂O → R-CHBr-COOH + HBr.\n"
                "최종 생성물: α-브로모카르복실산.\n"
                "동시에 PBr₃ 촉매 사이클이 재생됩니다."
            ),
            reactant_smiles="CC(Br)C(=O)Br",
            product_smiles="CC(Br)C(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O 론페어",
                          "atom", "C=O (아실)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),  # H₂O→C
            ],
            labels={"생성물": "α-브로모카르복실산"},
            energy_label="생성물",
            reagents="H₂O",
            notes="α-BrCH₂COOH: Gabriel 합성 또는 Kolbe-Schmitt 출발물질로 활용",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCH₂COOH + Br₂", 0.0),
        ("아실 브로마이드", -5.0),
        ("에놀", 8.0),
        ("TS: α-Br화", 15.0),
        ("α-BrCH(R)COBr", -8.0),
        ("생성물\nα-BrCH(R)COOH", -12.0),
    ],
)


# ─── MALONIC ESTER SYNTHESIS ────────────────────────────────────────────────
# 대표 반응: CH₂(CO₂Et)₂ → RCH(CO₂Et)₂ → RCH₂COOH
# McMurry Ch22: 말론산 에스터 알킬화 → 가수분해/탈카르복실화

MECHANISMS["malonic_ester_synthesis"] = MechanismData(
    mechanism_type="malonic_ester_synthesis",
    title="말론산 에스터 합성 (Malonic Ester Synthesis)",
    total_steps=4,
    overall_description=(
        "말론산 디에틸(diethyl malonate, CH₂(CO₂Et)₂)의 α-H(pKa ≈ 13)를 강염기(NaOEt)로 "
        "탈양성자화 → 에놀레이트 형성 → 알킬 할라이드로 C-알킬화 → "
        "가수분해 + 탈카르복실화 → 최종 치환 아세트산(RCH₂COOH) 획득. "
        "2번 반복하면 R₂CHCOOH도 합성 가능. β-케토 에스터 유사체인 "
        "아세토아세트산 에틸(acetoacetic ester synthesis)과 병행 학습."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="에놀레이트 형성 (탈양성자화)",
            description=(
                "NaOEt 강염기가 말론산 에스터의 α-H를 추출합니다.\n"
                "α-H pKa ≈ 13: 두 에스터 카르보닐에 의한 이중 안정화로 매우 산성.\n"
                "생성된 에놀레이트: 두 C=O의 공명에 의해 안정화(음전하가 두 O로 비편재화).\n"
                "NaOEt vs NaH: NaOEt는 약간의 에스터 교환 위험, NaH는 비가역적."
            ),
            reactant_smiles="CCOC(=O)CC(=O)OCC",
            product_smiles="CCOC(=O)[CH-]C(=O)OCC",
            arrows=[
                ArrowData("full", "lone_pair", "EtO⁻ (NaOEt)",
                          "atom", "α-H (pKa ≈ 13)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=4),  # EtO⁻→H
                ArrowData("full", "bond", "C-H 결합",
                          "atom", "C⁻ (에놀레이트)", "#1565C0", 0.3,
                          from_atom_idx=4, to_atom_idx=4),  # C-H→C⁻
            ],
            labels={"NaOEt": "강염기", "α-H": "pKa ≈ 13 (이중 활성화)"},
            energy_label="에놀레이트 (공명 안정화)",
            reagents="NaOEt, EtOH, RT",
            notes="이중 활성화: 두 C=O에 의한 공명 안정화 → pKa ≈ 13 (에스터 단독 pKa ≈ 25)",
        ),
        MechanismStep(
            step_number=2,
            title="SN2 C-알킬화",
            description=(
                "에놀레이트 탄소(C 친핵체)가 1차 알킬 할라이드(R-X)에 SN2 공격합니다.\n"
                "새로운 C-C 결합 형성: RCH(CO₂Et)₂.\n"
                "C-알킬화 vs O-알킬화: 말론산 에놀레이트는 C-알킬화 우세(열역학적 생성물).\n"
                "1차 할라이드만 사용: 2차/3차 → E2 부반응."
            ),
            reactant_smiles="CCOC(=O)[CH-]C(=O)OCC.CCBr",
            product_smiles="CCOC(=O)C(CC)C(=O)OCC.[Br-]",
            arrows=[
                ArrowData("full", "negative_charge", "C⁻ (에놀레이트, 친핵체)",
                          "atom", "CH₂-Br (δ+)", "#E53935", 0.4,
                          from_atom_idx=4, to_atom_idx=9),  # C⁻→C-Br
                ArrowData("full", "bond", "C-Br 결합",
                          "atom", "Br⁻ (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=9, to_atom_idx=10),  # C-Br→Br⁻
            ],
            labels={"에놀레이트": "C 친핵체", "R-Br": "1차 알킬 할라이드"},
            is_transition_state=True,
            energy_label="TS: SN2 C-알킬화",
            reagents="R-Br, EtOH, RT",
            notes="2번 반복 가능: RCH(CO₂Et)₂ → R₂C(CO₂Et)₂ (이중 알킬화)",
        ),
        MechanismStep(
            step_number=3,
            title="에스터 가수분해 → 디카르복실산",
            description=(
                "NaOH 수용액(가열)으로 두 에스터를 가수분해합니다.\n"
                "RCH(CO₂Et)₂ + 2 NaOH → RCH(COO⁻)₂ + 2 EtOH.\n"
                "산성 처리 → RCH(COOH)₂ (치환 말론산).\n"
                "이 가수분해는 비가역적(carboxylate 안정성)."
            ),
            reactant_smiles="CCOC(=O)C(CC)C(=O)OCC",
            product_smiles="OC(=O)C(CC)C(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻",
                          "atom", "C=O (에스터)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),  # OH⁻→C
            ],
            labels={"NaOH": "가수분해 조건"},
            energy_label="디카르복실산",
            reagents="1) NaOH, H₂O, Δ  2) H₃O⁺",
            notes="사포닌화(비가역적 에스터 가수분해)",
        ),
        MechanismStep(
            step_number=4,
            title="탈카르복실화 → 모노카르복실산",
            description=(
                "치환 말론산(RCH(COOH)₂)을 가열하면 CO₂가 이탈합니다.\n"
                "6원 고리 전이 상태를 경유하는 페리고리 탈카르복실화.\n"
                "β-케토산 패턴: C=O의 β-위치에 COOH → 에놀 중간체 → 타우토머화.\n"
                "최종: RCH₂COOH (치환 아세트산).\n"
                "이 전략으로 C₂ 단위(CH₂COOH)를 도입할 수 있습니다."
            ),
            reactant_smiles="OC(=O)C(CC)C(=O)O",
            product_smiles="CCC(=O)O",
            arrows=[
                ArrowData("full", "bond", "C-COOH 결합",
                          "atom", "CO₂ (이탈)", "#E53935", 0.3,
                          from_atom_idx=2, to_atom_idx=3),  # C-COOH→CO₂
            ],
            labels={"탈카르복실화": "6원 고리 TS", "CO₂": "이탈 기체"},
            energy_label="생성물 (RCH₂COOH)",
            reagents="Δ (100-150°C)",
            notes="말론산 에스터 합성 총괄: CH₂(CO₂Et)₂ → (1) NaOEt → (2) R-X → (3) NaOH/Δ → (4) H⁺/Δ → RCH₂COOH",
        ),
    ],
    energy_diagram=[
        ("반응물\nCH₂(CO₂Et)₂", 0.0),
        ("에놀레이트", -8.0),
        ("TS: SN2 알킬화", 12.0),
        ("알킬화 생성물\nRCH(CO₂Et)₂", -15.0),
        ("디카르복실산\nRCH(COOH)₂", -10.0),
        ("TS: 탈카르복실화", 5.0),
        ("생성물\nRCH₂COOH + CO₂", -20.0),
    ],
)


# ─── Friedel-Crafts Acylation ───────────────────────────────────────────────
# 대표 반응: C₆H₆ + CH₃COCl / AlCl₃ → C₆H₅COCH₃
# FC 알킬화와 달리 아실리움은 재배열하지 않음 (공명 안정화)

MECHANISMS["friedel_crafts_acylation"] = MechanismData(
    mechanism_type="friedel_crafts_acylation",
    title="프리델-크래프츠 아실화 (Friedel-Crafts Acylation)",
    total_steps=3,
    overall_description=(
        "아실 클로라이드(RCOCl)가 Lewis 산(AlCl₃)에 의해 활성화되어 "
        "아실리움 이온(RC≡O⁺, 공명 안정화)을 형성합니다. "
        "아실리움은 재배열하지 않으므로(알킬화와 다름) 생성물 구조가 예측 가능합니다. "
        "아렌의 π 전자가 아실리움을 공격(σ-complex) → 탈양성자화 → 방향족 케톤. "
        "생성물 케톤은 EWG이므로 과반응(다중 아실화)이 억제됩니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아실리움 이온 형성 (Lewis 산 활성화)",
            description=(
                "AlCl₃가 아실 클로라이드의 Cl에 배위합니다.\n"
                "C-Cl 결합이 끊어지면서 아실리움 양이온(RCO⁺) 생성.\n"
                "아실리움은 RC≡O⁺ 공명으로 안정화: 재배열 없음.\n"
                "이것이 FC 알킬화(카르보양이온 재배열 위험)와의 핵심 차이."
            ),
            reactant_smiles="CC(=O)Cl",
            product_smiles="CC(=O)[AlH3-]",
            arrows=[
                ArrowData("full", "lone_pair", "AlCl₃ (Lewis 산)",
                          "atom", "Cl (아실클로라이드)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=3),
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "아실리움 C⁺", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=3),
            ],
            labels={"AlCl₃": "Lewis 산", "RCO⁺": "아실리움 (공명 안정화)"},
            energy_label="아실리움 이온",
            reagents="AlCl₃, CH₂Cl₂, 0°C",
            notes="아실리움은 RC≡O⁺ 공명 덕분에 재배열 없음 (cf. 알킬화: 1,2-shift 위험)",
        ),
        MechanismStep(
            step_number=2,
            title="σ-복합체 형성 (친전자 방향족 치환)",
            description=(
                "벤젠 π 전자가 아실리움 이온의 탄소를 공격합니다.\n"
                "Wheland 중간체(σ-복합체, 아레늄 이온) 형성.\n"
                "방향족성이 깨지므로 에너지가 높은 중간체.\n"
                "공격 위치는 기존 치환기의 배향 효과에 따름."
            ),
            reactant_smiles="c1ccccc1",
            product_smiles="O=C(C)[C@@H]1C=CC=C1",
            arrows=[
                ArrowData("full", "pi_bond", "벤젠 π 전자",
                          "atom", "RCO⁺ (아실리움)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"σ-복합체": "Wheland 중간체", "ArH": "방향족 기질"},
            is_transition_state=True,
            energy_label="TS: σ-복합체 (방향족성 상실)",
            reagents="",
            notes="속도 결정 단계: 방향족성 상실로 높은 활성화 에너지",
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자화 (방향족성 회복)",
            description=(
                "AlCl₄⁻(또는 염기)가 σ-복합체의 H를 제거합니다.\n"
                "방향족성이 회복되면서 방향족 케톤(ArCOR) 생성.\n"
                "생성물 케톤의 C=O는 EWG: 고리를 비활성화하여 과반응 억제.\n"
                "AlCl₃ 촉매는 생성물과 배위하므로 화학양론적 사용 필요."
            ),
            reactant_smiles="O=C(C)[C@@H]1C=CC=C1",
            product_smiles="O=C(C)c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "C-H 결합",
                          "atom", "π 계 (방향족성 회복)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"AlCl₄⁻": "염기 역할", "ArCOR": "방향족 케톤"},
            energy_label="생성물 (아세토페논)",
            reagents="",
            notes="AlCl₃는 화학양론적: 생성물 케톤에 배위하므로 촉매량 부족",
        ),
    ],
    energy_diagram=[
        ("반응물\nC₆H₆ + RCOCl", 0.0),
        ("아실리움 이온\nRCO⁺", 5.0),
        ("TS: σ-복합체", 22.0),
        ("σ-복합체\n(아레늄 이온)", 15.0),
        ("생성물\nArCOR + HCl", -12.0),
    ],
)

# ─── Oxymercuration ────────────────────────────────────────────────────────
# 대표 반응: R-CH=CH₂ + Hg(OAc)₂/H₂O → NaBH₄ → R-CH(OH)-CH₃
# Markovnikov 수화, anti 첨가, 재배열 없음

MECHANISMS["oxymercuration"] = MechanismData(
    mechanism_type="oxymercuration",
    title="산화수은 수화 (Oxymercuration-Demercuration)",
    total_steps=3,
    overall_description=(
        "알켄의 Markovnikov 수화를 달성하는 2단계 합성법입니다. "
        "(1) Hg(OAc)₂/H₂O로 머큐리늄 이온(3원 고리) 형성 → 물 공격(anti, Markovnikov). "
        "(2) NaBH₄로 C-Hg 결합을 환원적으로 절단. "
        "장점: 산촉매 수화와 달리 카르보양이온 중간체를 거치지 않아 재배열이 없습니다."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="머큐리늄 이온 형성",
            description=(
                "Hg(OAc)₂의 Hg²⁺가 알켄 π 결합에 친전자 공격합니다.\n"
                "3원 고리 머큐리늄 이온(bromonium과 유사 구조) 형성.\n"
                "Hg-C 결합 2개가 동시 형성: 열린 카르보양이온보다 안정.\n"
                "재배열이 일어나지 않는 이유: 3원 고리 양전하가 분산됨."
            ),
            reactant_smiles="C=CC",
            product_smiles="C1([Hg])CC1",
            arrows=[
                ArrowData("full", "pi_bond", "C=C π 전자",
                          "atom", "Hg²⁺ (친전자체)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"Hg(OAc)₂": "친전자 시약", "머큐리늄": "3원 고리"},
            energy_label="머큐리늄 이온",
            reagents="Hg(OAc)₂, H₂O/THF",
            notes="브로모늄 이온과 유사한 가교 구조, 카르보양이온 재배열 방지",
        ),
        MechanismStep(
            step_number=2,
            title="물의 Markovnikov 공격 (anti 첨가)",
            description=(
                "H₂O가 머큐리늄 이온의 더 치환된 탄소를 anti 방향에서 공격합니다.\n"
                "Markovnikov 위치선택성: δ⁺가 더 치환된 C에 집중.\n"
                "Anti 첨가: 물이 Hg 반대편에서 공격.\n"
                "유기수은 알코올 중간체 형성."
            ),
            reactant_smiles="C1([Hg])CC1",
            product_smiles="CC(O)C[Hg]",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (친핵체)",
                          "atom", "C (δ⁺, 더 치환된)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
            ],
            labels={"H₂O": "친핵체", "Markovnikov": "더 치환된 C 공격"},
            is_transition_state=True,
            energy_label="TS: 물 공격",
            reagents="H₂O",
            notes="위치선택성: 머큐리늄의 δ⁺가 더 치환된 탄소에 집중 → Markovnikov",
        ),
        MechanismStep(
            step_number=3,
            title="탈수은화 (NaBH₄ 환원)",
            description=(
                "NaBH₄가 C-Hg 결합을 환원적으로 절단합니다.\n"
                "C-Hg → C-H 치환: 라디칼 메커니즘으로 진행.\n"
                "Hg⁰(금속 수은)이 침전.\n"
                "최종 생성물: Markovnikov 알코올(재배열 없음)."
            ),
            reactant_smiles="CC(O)C[Hg]",
            product_smiles="CC(O)C",
            arrows=[
                ArrowData("full", "lone_pair", "NaBH₄ (H⁻ 공급원)",
                          "atom", "C-Hg 결합", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=3),
            ],
            labels={"NaBH₄": "환원제", "Hg⁰": "침전"},
            energy_label="생성물 (Markovnikov 알코올)",
            reagents="NaBH₄, NaOH",
            notes="총괄: 알켄 → Markovnikov 알코올, 재배열 없음, anti 첨가",
        ),
    ],
    energy_diagram=[
        ("반응물\nR-CH=CH₂", 0.0),
        ("머큐리늄 이온", 8.0),
        ("TS: H₂O 공격", 14.0),
        ("유기수은 중간체", -5.0),
        ("생성물\nR-CH(OH)-CH₃", -10.0),
    ],
)

# ─── Anti-Markovnikov Addition (Radical HBr) ────────────────────────────────
# 대표 반응: R-CH=CH₂ + HBr (ROOR) → R-CH₂-CH₂Br
# 라디칼 연쇄 메커니즘, 과산화물 효과(Kharasch 효과)

MECHANISMS["anti_markovnikov_addition"] = MechanismData(
    mechanism_type="anti_markovnikov_addition",
    title="라디칼 HBr 첨가 (Anti-Markovnikov, 과산화물 효과)",
    total_steps=4,
    overall_description=(
        "과산화물(ROOR) 존재 하에 HBr이 라디칼 메커니즘으로 알켄에 첨가됩니다. "
        "개시(initiation): ROOR → RO· → RO· + HBr → ROH + Br·. "
        "전파(propagation): Br·가 알켄에 첨가(더 안정한 라디칼 형성) → "
        "Anti-Markovnikov 위치선택성. C 라디칼 + HBr → 생성물 + Br·. "
        "HBr에서만 작동: HCl/HI는 전파 단계의 열역학이 불리."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="개시 (Initiation): 라디칼 생성",
            description=(
                "과산화물(ROOR)의 약한 O-O 결합(BDE ≈ 150 kJ/mol)이 "
                "열 또는 UV에 의해 균일 분해됩니다.\n"
                "RO· + HBr → ROH + Br· (Br 라디칼 생성).\n"
                "이 단계가 연쇄 반응을 시작합니다."
            ),
            reactant_smiles="OOCC",
            product_smiles="[Br].[OH]CC",
            arrows=[
                ArrowData("half", "bond", "O-O 결합 (균일 분해)",
                          "atom", "RO· (알콕시 라디칼)", "#FF6F00", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("half", "bond", "H-Br 결합",
                          "atom", "Br· (라디칼)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"ROOR": "과산화물 (개시제)", "Br·": "브롬 라디칼"},
            energy_label="개시 (Initiation)",
            reagents="ROOR, Δ 또는 hν",
            notes="O-O BDE ≈ 150 kJ/mol (약한 결합, 쉽게 균일 분해)",
        ),
        MechanismStep(
            step_number=2,
            title="전파 1: Br· 의 알켄 첨가",
            description=(
                "Br·가 알켄의 덜 치환된(말단) 탄소에 첨가합니다.\n"
                "이유: 더 치환된 탄소에 라디칼이 남아야 더 안정(3° > 2° > 1°).\n"
                "결과: Anti-Markovnikov 위치선택성.\n"
                "새로운 C-Br 결합 형성 + 안정한 2° 또는 3° 탄소 라디칼."
            ),
            reactant_smiles="C=CC.[Br]",
            product_smiles="BrC[CH]C",
            arrows=[
                ArrowData("half", "lone_pair", "Br· (라디칼)",
                          "atom", "말단 C (덜 치환된)", "#E53935", 0.4,
                          from_atom_idx=3, to_atom_idx=0),
                ArrowData("half", "pi_bond", "C=C π 전자 (1개)",
                          "atom", "내부 C· (라디칼)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
            ],
            labels={"Br·": "라디칼", "C·": "2° 탄소 라디칼"},
            energy_label="탄소 라디칼 중간체",
            reagents="",
            notes="Anti-Markovnikov: Br가 말단에, C·가 내부에(더 안정한 라디칼)",
        ),
        MechanismStep(
            step_number=3,
            title="전파 2: C· + HBr → C-H + Br·",
            description=(
                "탄소 라디칼이 HBr에서 H를 추출합니다.\n"
                "새 C-H 결합 형성 + Br· 재생(연쇄 전파).\n"
                "이 단계에서 Br· 가 재생되므로 다시 전파 1로 돌아감.\n"
                "연쇄 길이(chain length) = 수백~수천 사이클."
            ),
            reactant_smiles="BrC[CH]C",
            product_smiles="BrCCC.[Br]",
            arrows=[
                ArrowData("half", "bond", "H-Br 결합",
                          "atom", "C· (라디칼)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
            ],
            labels={"HBr": "H 공급원", "Br·": "재생됨 (연쇄)"},
            energy_label="전파 (연쇄 지속)",
            reagents="HBr",
            notes="발열 반응: C-H 결합(~410 kJ) 형성 > H-Br 결합(~370 kJ) 절단",
        ),
        MechanismStep(
            step_number=4,
            title="종결 (Termination)",
            description=(
                "두 라디칼이 만나 결합하면 연쇄가 종결됩니다.\n"
                "가능한 조합: Br· + Br· → Br₂, Br· + C· → C-Br, C· + C· → C-C.\n"
                "종결은 확률적 과정: 라디칼 농도가 낮으므로 낮은 빈도.\n"
                "최종 생성물: anti-Markovnikov 1-브로모알칸."
            ),
            reactant_smiles="BrCCC.[Br]",
            product_smiles="BrCCC",
            arrows=[
                ArrowData("half", "lone_pair", "Br·",
                          "atom", "Br· (또는 C·)", "#9C27B0", 0.3,
                          from_atom_idx=3, to_atom_idx=3),
            ],
            labels={"종결": "라디칼 커플링"},
            energy_label="생성물 (1-브로모프로판)",
            reagents="",
            notes="HBr만 Anti-Markovnikov: HCl은 전파 1 흡열, HI는 전파 2 흡열",
        ),
    ],
    energy_diagram=[
        ("반응물\nR-CH=CH₂ + HBr", 0.0),
        ("개시: Br· 생성", 15.0),
        ("전파 1: C· 중간체", -3.0),
        ("전파 2: C-H 형성", -8.0),
        ("생성물\nR-CH₂CH₂Br", -12.0),
    ],
)

# ─── Hofmann Elimination ────────────────────────────────────────────────────
# 대표 반응: R₂CHCH₂NMe₃⁺ + OH⁻ → R₂C=CH₂ (덜 치환된 알켄, Hofmann 생성물)
# Ch22: 4차 암모늄 열분해, E2 메커니즘, Hofmann 규칙

MECHANISMS["hofmann_elimination"] = MechanismData(
    mechanism_type="hofmann_elimination",
    title="호프만 제거 (Hofmann Elimination)",
    total_steps=3,
    overall_description=(
        "4차 암모늄 염(R₄N⁺)의 E2 제거 반응입니다. "
        "통상적 E2(Zaitsev 규칙: 더 치환된 알켄)와 달리, "
        "이탈기가 매우 큰 NMe₃이므로 입체적 요인이 지배: "
        "접근이 쉬운 덜 치환된 β-H를 추출 → Hofmann 생성물(덜 치환된 알켄). "
        "Cope 제거와 비교 학습 필수."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="완전 메틸화 (4차 암모늄 염 합성)",
            description=(
                "아민을 과량의 CH₃I로 완전 메틸화합니다.\n"
                "1° → 2° → 3° → 4차 암모늄(NR₄⁺ I⁻).\n"
                "이어서 Ag₂O/H₂O 처리로 I⁻ → OH⁻ 교환(4차 암모늄 수산화물).\n"
                "OH⁻가 제거 반응의 염기 역할."
            ),
            reactant_smiles="CCNC",
            product_smiles="CC[N+](C)(C)C",
            arrows=[
                ArrowData("full", "lone_pair", "N 론페어 (친핵체)",
                          "atom", "CH₃I (기질)", "#E53935", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),
            ],
            labels={"CH₃I": "과량 (완전 메틸화)", "NR₄⁺": "4차 암모늄"},
            energy_label="4차 암모늄 이온",
            reagents="과량 CH₃I, 이후 Ag₂O/H₂O",
            notes="Exhaustive methylation: RNH₂ → RNMe₃⁺ (SN2 반복)",
        ),
        MechanismStep(
            step_number=2,
            title="E2 제거 (Hofmann 규칙)",
            description=(
                "OH⁻ 강염기가 덜 치환된 β-H를 추출합니다 (E2, 동시).\n"
                "Hofmann 규칙: 큰 이탈기(NMe₃) → 입체적으로 접근 쉬운 1° H 우선 추출.\n"
                "Zaitsev 규칙의 예외: NMe₃ 이탈기가 너무 커서 2°/3° H 접근 어려움.\n"
                "Anti-periplanar 배치: H와 NMe₃가 반(anti) 방향."
            ),
            reactant_smiles="CC[N+](C)(C)C.[OH-]",
            product_smiles="C=C.NC",
            arrows=[
                ArrowData("full", "lone_pair", "OH⁻ (강염기)",
                          "atom", "β-H (덜 치환된)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-H 결합",
                          "atom", "C=C π 결합 (형성)", "#1565C0", 0.3,
                          from_atom_idx=0, to_atom_idx=1),
                ArrowData("full", "bond", "C-NMe₃ 결합",
                          "atom", "NMe₃ (이탈기)", "#4CAF50", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"OH⁻": "강염기", "β-H": "Hofmann (덜 치환된)", "NMe₃": "이탈기"},
            is_transition_state=True,
            energy_label="TS: E2 (anti-periplanar)",
            reagents="Δ (가열)",
            notes="Hofmann 규칙: 큰 이탈기 → 1° H 우선 → 덜 치환된 알켄",
        ),
        MechanismStep(
            step_number=3,
            title="생성물: 덜 치환된 알켄 + NMe₃",
            description=(
                "E2 제거가 완료되면 덜 치환된 알켄이 주생성물입니다.\n"
                "NMe₃(트리메틸아민)은 기체로 이탈.\n"
                "Hofmann vs Zaitsev: 이탈기 크기가 선택성을 결정.\n"
                "응용: 아민의 구조 결정(Hofmann 분해 분석)에 역사적으로 사용."
            ),
            reactant_smiles="C=C",
            product_smiles="C=C",
            arrows=[],
            labels={"Hofmann 생성물": "덜 치환된 알켄"},
            energy_label="생성물 (1-알켄)",
            reagents="",
            notes="역사적 의의: von Hofmann이 알칼로이드 구조 분석에 활용",
        ),
    ],
    energy_diagram=[
        ("반응물\nR₄N⁺OH⁻", 0.0),
        ("TS: E2 anti-periplanar", 25.0),
        ("생성물\n덜 치환된 알켄 + NMe₃", -15.0),
    ],
)

# ─── Horner-Wadsworth-Emmons ────────────────────────────────────────────────
# 대표 반응: (EtO)₂P(O)CH₂CO₂Et + RCHO → RCH=CHCO₂Et (E-선택적)
# Ch19: 포스포네이트 올레핀화, Wittig 변형

MECHANISMS["horner_wadsworth_emmons"] = MechanismData(
    mechanism_type="horner_wadsworth_emmons",
    title="호너-워즈워스-에몬스 반응 (HWE Olefination)",
    total_steps=3,
    overall_description=(
        "포스포네이트 에스터를 사용하는 Wittig 반응의 변형입니다. "
        "안정화된 일리드(포스포네이트 카르바니온)가 알데히드/케톤과 반응하여 "
        "α,β-불포화 에스터를 E-선택적으로 생성합니다. "
        "장점: (1) Wittig보다 E-선택성 우수, (2) 부산물 (EtO)₂PO₂⁻는 수용성(정제 용이), "
        "(3) 반응성이 높아 케톤과도 반응 가능."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="포스포네이트 카르바니온 형성",
            description=(
                "NaH 또는 n-BuLi로 포스포네이트 α-H를 탈양성자화합니다.\n"
                "pKa ≈ 18-20 (안정화된 카르바니온: P=O + C=O 이중 안정화).\n"
                "Wittig 일리드와 달리 P=O 결합은 유지됨.\n"
                "반응성: 안정화 일리드 → E-선택성 (Schlosser 변형으로 Z도 가능)."
            ),
            reactant_smiles="CCOP(=O)(OCC)CC(=O)OCC",
            product_smiles="CCOP(=O)(OCC)[CH-]C(=O)OCC",
            arrows=[
                ArrowData("full", "lone_pair", "NaH (강염기)",
                          "atom", "α-H", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=6),
                ArrowData("full", "bond", "C-H 결합",
                          "atom", "C⁻ (카르바니온)", "#1565C0", 0.3,
                          from_atom_idx=6, to_atom_idx=6),
            ],
            labels={"NaH": "강염기", "포스포네이트": "(EtO)₂P(O)CH₂CO₂Et"},
            energy_label="포스포네이트 카르바니온",
            reagents="NaH, THF, 0°C",
            notes="Still-Gennari 변형: (CF₃CH₂O)₂P(O) 사용 → Z-선택적",
        ),
        MechanismStep(
            step_number=2,
            title="알데히드 첨가 → 베타인/옥사포스페탄",
            description=(
                "포스포네이트 카르바니온이 알데히드 C=O에 친핵 첨가합니다.\n"
                "베타인(betaine) 중간체 형성 → 옥사포스페탄(4원 고리).\n"
                "E-선택성 기원: anti-베타인이 열역학적으로 유리(큰 치환기 trans).\n"
                "가역적 첨가: 열역학 제어로 E-이성질체 우세."
            ),
            reactant_smiles="CCOP(=O)(OCC)[CH-]C(=O)OCC.O=CC",
            product_smiles="CCOP(=O)(OCC)C(C(=O)OCC)C(C)[O-]",  # betaine (open-chain, RDKit-safe)
            arrows=[
                ArrowData("full", "negative_charge", "C⁻ (카르바니온)",
                          "atom", "C=O (알데히드)", "#E53935", 0.4,
                          from_atom_idx=6, to_atom_idx=-1),
            ],
            labels={"카르바니온": "친핵체", "RCHO": "알데히드"},
            is_transition_state=True,
            energy_label="TS: 옥사포스페탄",
            reagents="",
            notes="가역적 첨가 → 열역학 제어 → anti-베타인 우세 → E-알켄",
        ),
        MechanismStep(
            step_number=3,
            title="역 [2+2] 고리 열림 → E-알켄 + 포스페이트",
            description=(
                "옥사포스페탄이 역 [2+2] 고리 열림(retro-cycloaddition)합니다.\n"
                "syn-제거: C-P 및 O-C 결합 동시 절단.\n"
                "생성물: α,β-불포화 에스터(E-배치) + 디에틸포스페이트.\n"
                "(EtO)₂PO₂⁻는 수용성: 간단한 세척으로 분리 가능."
            ),
            reactant_smiles="CCOP(=O)(OCC)C(C(=O)OCC)C(C)[O-]",  # betaine (open-chain, RDKit-safe)
            product_smiles="CC=CC(=O)OCC.CCOP(=O)(OCC)O",
            arrows=[
                ArrowData("full", "bond", "C-P 결합",
                          "atom", "P (포스페이트 이탈)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "O-C 결합",
                          "atom", "C=C (형성)", "#1565C0", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"retro [2+2]": "고리 열림", "(EtO)₂PO₂⁻": "수용성 부산물"},
            energy_label="생성물 (E-α,β-불포화 에스터)",
            reagents="",
            notes="Wittig vs HWE: Wittig은 Ph₃P=O(비수용성, 분리 어려움), HWE는 정제 용이",
        ),
    ],
    energy_diagram=[
        ("반응물\n포스포네이트 + RCHO", 0.0),
        ("카르바니온", -5.0),
        ("TS: 옥사포스페탄", 12.0),
        ("옥사포스페탄", 5.0),
        ("생성물\nE-α,β-불포화 에스터", -18.0),
    ],
)

# ─── Fischer Indole Synthesis ───────────────────────────────────────────────
# 대표 반응: PhNHNH₂ + RCOCH₃ → 2-치환 인돌
# Ch24: [3,3]-시그마트로피 전위 핵심, 헤테로 고리 합성

MECHANISMS["fischer_indole"] = MechanismData(
    mechanism_type="fischer_indole",
    title="피셔 인돌 합성 (Fischer Indole Synthesis)",
    total_steps=4,
    overall_description=(
        "페닐히드라진과 케톤/알데히드의 산촉매 축합으로 인돌 고리를 형성합니다. "
        "핵심 단계: 페닐히드라존의 [3,3]-시그마트로피 전위. "
        "(1) 히드라존 형성, (2) 에나민-이민 호변이성질 → ene-hydrazine, "
        "(3) [3,3]-전위 → C-C 결합 형성, (4) NH₃ 이탈 + 방향족화 → 인돌."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="페닐히드라존 형성 (축합)",
            description=(
                "페닐히드라진(PhNHNH₂)의 말단 NH₂가 케톤 C=O에 친핵 첨가합니다.\n"
                "카르비놀아민 중간체 → 탈수(-H₂O) → 페닐히드라존(C=N-NHPh).\n"
                "이 단계는 이민 형성과 동일한 메커니즘.\n"
                "산촉매(HCl, AcOH 등)가 카르보닐 활성화 + 탈수 촉진."
            ),
            reactant_smiles="NNc1ccccc1.CC(=O)C",
            product_smiles="C(/C)=N/Nc1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "PhNHNH₂ (친핵체)",
                          "atom", "C=O (케톤)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=2),
            ],
            labels={"PhNHNH₂": "페닐히드라진", "축합": "-H₂O"},
            energy_label="페닐히드라존",
            reagents="HCl (촉매), EtOH, Δ",
            notes="이민 형성과 동일 메커니즘: 친핵 첨가 → 카르비놀아민 → 탈수",
        ),
        MechanismStep(
            step_number=2,
            title="호변이성질화 → ene-히드라진",
            description=(
                "산촉매 하에 히드라존이 ene-히드라진으로 호변이성질화합니다.\n"
                "C=N-NH → C-NH-N=C → ene-히드라진(C=C-NH-NHPh).\n"
                "이 호변이성질체가 [3,3]-전위의 기질.\n"
                "메틸 케톤: CH₃ 쪽으로 이중결합 이동 → 2-메틸인돌."
            ),
            reactant_smiles="C(/C)=N/Nc1ccccc1",
            product_smiles="C(=C)NNc1ccccc1",
            arrows=[
                ArrowData("full", "bond", "N-H 결합",
                          "atom", "C=N → C-NH (호변이성질)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"호변이성질": "히드라존 ⇌ ene-히드라진"},
            energy_label="ene-히드라진",
            reagents="H⁺ (촉매)",
            notes="호변이성질화는 [3,3]-전위를 위한 필수 전제 조건",
        ),
        MechanismStep(
            step_number=3,
            title="[3,3]-시그마트로피 전위 (핵심 단계)",
            description=(
                "ene-히드라진이 의자형(chair-like) 전이 상태를 거쳐 [3,3]-전위합니다.\n"
                "N-N 결합이 끊어지면서 새로운 C-C 결합이 형성됩니다.\n"
                "오르토 위치의 C가 알킬 사슬의 C와 결합.\n"
                "Claisen 전위와 유사한 페리고리 메커니즘."
            ),
            reactant_smiles="C(=C)NNc1ccccc1",
            product_smiles="NC(=N)C(C)c1ccccc1",
            arrows=[
                ArrowData("full", "bond", "N-N 결합 (절단)",
                          "atom", "C-C 결합 (형성)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"[3,3]": "시그마트로피 전위", "chair TS": "의자형 전이 상태"},
            is_transition_state=True,
            energy_label="TS: [3,3]-시그마트로피 전위",
            reagents="",
            notes="Woodward-Hoffmann 허용: suprafacial-suprafacial [3,3]-전위",
        ),
        MechanismStep(
            step_number=4,
            title="방향족화 + NH₃ 이탈 → 인돌",
            description=(
                "[3,3]-전위 생성물이 재방향족화합니다.\n"
                "양성자 이동 + NH₃ 이탈로 인돌 고리 완성.\n"
                "방향족성 회복이 강한 열역학적 driving force.\n"
                "최종 생성물: 2-치환 인돌(메틸 케톤 → 2-메틸인돌)."
            ),
            reactant_smiles="NC(=N)C(C)c1ccccc1",
            product_smiles="Cc1[nH]c2ccccc2c1",
            arrows=[
                ArrowData("full", "bond", "C-NH₂ 결합",
                          "atom", "NH₃ (이탈)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"NH₃": "이탈", "인돌": "방향족 고리 형성"},
            energy_label="생성물 (2-메틸인돌)",
            reagents="",
            notes="Fischer 인돌: 인돌 합성의 가장 고전적 방법, 1883년 Emil Fischer",
        ),
    ],
    energy_diagram=[
        ("반응물\nPhNHNH₂ + RCOCH₃", 0.0),
        ("페닐히드라존", -5.0),
        ("ene-히드라진", -2.0),
        ("TS: [3,3]-전위", 20.0),
        ("디이민 중간체", 10.0),
        ("생성물\n2-치환 인돌 + NH₃", -25.0),
    ],
)

# ─── Diazotization ──────────────────────────────────────────────────────────
# 대표 반응: ArNH₂ + NaNO₂/HCl → ArN₂⁺ → 치환 (Sandmeyer 등)
# Ch16: 디아조늄 이온 화학

MECHANISMS["diazotization"] = MechanismData(
    mechanism_type="diazotization",
    title="디아조화 반응 (Diazotization)",
    total_steps=3,
    overall_description=(
        "1차 방향족 아민(ArNH₂)을 아질산(NaNO₂/HCl, 0°C)으로 처리하면 "
        "디아조늄 이온(ArN₂⁺)이 형성됩니다. "
        "디아조늄 이온은 매우 좋은 이탈기(N₂ 기체)를 가지므로 "
        "다양한 치환 반응의 출발점: Sandmeyer(ArCl, ArBr, ArCN), "
        "Schiemann(ArF), 아조 커플링(염료 합성) 등."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="니트로소늄 이온(NO⁺) 생성",
            description=(
                "NaNO₂ + HCl → NaCl + HNO₂ (아질산 in situ 생성).\n"
                "HNO₂ + H⁺ → H₂O + NO⁺ (니트로소늄 이온).\n"
                "NO⁺는 강한 친전자체: N에 빈 오비탈.\n"
                "반응은 반드시 0°C 이하에서 수행(디아조늄 분해 방지)."
            ),
            reactant_smiles="[O-][N+]=O",
            product_smiles="[N+]=[O]",  # NO+ nitrosonium (RDKit-safe)
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (산)",
                          "atom", "HNO₂ → NO⁺", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"NaNO₂": "아질산 나트륨", "NO⁺": "니트로소늄 이온"},
            energy_label="NO⁺ (친전자체)",
            reagents="NaNO₂, HCl, 0°C",
            notes="반드시 0°C: 디아조늄 이온은 5°C 이상에서 분해(N₂ 이탈)",
        ),
        MechanismStep(
            step_number=2,
            title="아민의 N-니트로소화 → 디아조늄 형성",
            description=(
                "ArNH₂의 론페어가 NO⁺에 친핵 공격합니다.\n"
                "N-니트로소아민(ArNH-N=O) 형성 → 양성자 이동.\n"
                "탈수(-H₂O) → 디아조늄 이온(ArN₂⁺) 형성.\n"
                "디아조늄 이온은 공명 안정화: Ar-N≡N⁺ ↔ Ar-N=N."
            ),
            reactant_smiles="Nc1ccccc1",
            product_smiles="c1ccc(cc1)[N+]#N",  # ArN2+ diazonium (RDKit-safe)
            arrows=[
                ArrowData("full", "lone_pair", "ArNH₂ (친핵체)",
                          "atom", "NO⁺ (친전자체)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"ArNH₂": "아닐린", "ArN₂⁺": "디아조늄 이온"},
            is_transition_state=True,
            energy_label="TS: N-니트로소화",
            reagents="0°C (필수)",
            notes="1차 아민만 가능: 2차 → N-니트로소아민(발암물질), 3차 → 고리 니트로소화",
        ),
        MechanismStep(
            step_number=3,
            title="디아조늄 이온의 치환 반응 (Sandmeyer 등)",
            description=(
                "디아조늄 이온(ArN₂⁺)에서 N₂가 이탈(최고의 이탈기).\n"
                "아릴 양이온 등가체 → 다양한 친핵체와 반응:\n"
                "CuCl → ArCl, CuBr → ArBr, CuCN → ArCN (Sandmeyer).\n"
                "HBF₄ → ArF (Balz-Schiemann).\n"
                "H₃PO₂ → ArH (환원적 탈아미노)."
            ),
            reactant_smiles="c1ccc(cc1)[N+]#N",  # ArN2+ diazonium (RDKit-safe)
            product_smiles="Clc1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "Cu(I)Cl (친핵체/촉매)",
                          "atom", "Ar (아릴 탄소)", "#1565C0", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
                ArrowData("full", "bond", "C-N₂⁺ 결합",
                          "atom", "N₂ (이탈기, 기체)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"N₂": "최고의 이탈기", "Sandmeyer": "CuX 촉매 치환"},
            energy_label="생성물 (ArCl)",
            reagents="CuCl (Sandmeyer 조건)",
            notes="응용: ArNH₂ → ArN₂⁺ → ArX/ArCN/ArOH/ArH 전환의 허브 반응",
        ),
    ],
    energy_diagram=[
        ("반응물\nArNH₂ + NaNO₂/HCl", 0.0),
        ("NO⁺ 생성", 5.0),
        ("TS: N-니트로소화", 15.0),
        ("ArN₂⁺ (디아조늄)", -8.0),
        ("생성물\nArCl + N₂", -20.0),
    ],
)

# ─── Fries Rearrangement ────────────────────────────────────────────────────
# 대표 반응: PhOCOCH₃ + AlCl₃ → o/p-HO-C₆H₄-COCH₃
# Ch16: 페놀 에스터 → 히드록시케톤 (FC 아실화 역반응)

MECHANISMS["fries_rearrangement"] = MechanismData(
    mechanism_type="fries_rearrangement",
    title="프리스 자리옮김 (Fries Rearrangement)",
    total_steps=3,
    overall_description=(
        "페놀 에스터(ArOCOR)를 Lewis 산(AlCl₃)으로 처리하면 "
        "아실기가 방향족 고리로 이동하여 히드록시케톤을 생성합니다. "
        "메커니즘: (1) AlCl₃가 에스터 C=O에 배위 → (2) C-O 결합 절단으로 "
        "아실리움 이온 + 페녹사이드 생성 → (3) 분자 내 FC 아실화. "
        "온도 제어: 저온 → para, 고온 → ortho 선택성."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="Lewis 산 배위 + 아실리움 생성",
            description=(
                "AlCl₃가 페놀 에스터의 C=O 산소에 배위합니다.\n"
                "에스터 C-O 결합이 절단: 아실리움 이온(RCO⁺) + 페녹사이드-AlCl₃ 복합체.\n"
                "아실리움은 공명 안정화(RC≡O⁺).\n"
                "실질적으로 FC 아실화의 역반응의 역반응(에스터 → 다시 FC)."
            ),
            reactant_smiles="CC(=O)Oc1ccccc1",
            product_smiles="[O-]c1ccccc1.CC(=O)[AlH3-]",
            arrows=[
                ArrowData("full", "lone_pair", "AlCl₃",
                          "atom", "C=O (에스터)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
                ArrowData("full", "bond", "Ar-O 결합 (절단)",
                          "atom", "아실리움 + 페녹사이드", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=0),
            ],
            labels={"AlCl₃": "Lewis 산", "RCO⁺": "아실리움"},
            energy_label="이온쌍 (아실리움 + ArO⁻)",
            reagents="AlCl₃ (화학양론적), 무수 조건",
            notes="AlCl₃는 촉매량이 아닌 화학양론적 사용 (페놀 OH에도 배위)",
        ),
        MechanismStep(
            step_number=2,
            title="분자 내 FC 아실화 (σ-복합체)",
            description=(
                "아실리움 이온이 페녹사이드의 방향족 고리를 공격합니다.\n"
                "분자 내(intramolecular) 또는 이온쌍 내부에서 진행.\n"
                "σ-복합체(Wheland 중간체) 형성.\n"
                "온도 제어: 저온(25°C) → para 배향, 고온(>160°C) → ortho 배향."
            ),
            reactant_smiles="[O-]c1ccccc1",
            product_smiles="Oc1ccc(C(=O)C)cc1",
            arrows=[
                ArrowData("full", "pi_bond", "Ar π 전자",
                          "atom", "RCO⁺ (아실리움)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"σ-복합체": "Wheland 중간체", "para": "저온 선택"},
            is_transition_state=True,
            energy_label="TS: σ-복합체",
            reagents="",
            notes="para(열역학적 생성물) vs ortho(운동학적 생성물): 온도로 제어",
        ),
        MechanismStep(
            step_number=3,
            title="탈양성자화 → 히드록시케톤",
            description=(
                "σ-복합체에서 H⁺가 이탈하며 방향족성이 회복됩니다.\n"
                "생성물: p-히드록시아세토페논(저온) 또는 o-히드록시아세토페논(고온).\n"
                "수처리(work-up)로 AlCl₃ 복합체를 분해.\n"
                "Photo-Fries: UV 조건에서도 유사한 자리옮김 가능."
            ),
            reactant_smiles="Oc1ccc(C(=O)C)cc1",
            product_smiles="Oc1ccc(C(=O)C)cc1",
            arrows=[],
            labels={"p-히드록시케톤": "주생성물 (저온)"},
            energy_label="생성물 (p-히드록시아세토페논)",
            reagents="H₂O (work-up)",
            notes="Fries = FC 아실화의 분자 내 변형. Photo-Fries는 UV로도 가능.",
        ),
    ],
    energy_diagram=[
        ("반응물\nArOCOR", 0.0),
        ("이온쌍\nArO⁻ + RCO⁺", 12.0),
        ("TS: σ-복합체", 20.0),
        ("σ-복합체", 15.0),
        ("생성물\nHO-Ar-COR", -8.0),
    ],
)

# ─── Arndt-Eistert Synthesis ────────────────────────────────────────────────
# 대표 반응: RCOOH → RCOCl → RCOCHN₂ → (Ag₂O) → RCH₂COOH (동족산)
# Ch20: 탄소 1개 삽입, Wolff 전위

MECHANISMS["arndt_eistert"] = MechanismData(
    mechanism_type="arndt_eistert",
    title="아른트-아이스테르트 합성 (Arndt-Eistert Homologation)",
    total_steps=4,
    overall_description=(
        "카르복실산에 탄소 1개를 삽입하여 동족산(homologous acid)을 합성합니다. "
        "(1) 산 → 아실 클로라이드, (2) CH₂N₂(디아조메탄) 처리 → α-디아조케톤, "
        "(3) Ag₂O 또는 hν 촉매로 Wolff 전위(케텐 중간체), "
        "(4) H₂O 또는 ROH 포획 → 동족 카르복실산 또는 에스터."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="아실 클로라이드 제조",
            description=(
                "카르복실산(RCOOH)을 SOCl₂(또는 (COCl)₂)로 처리합니다.\n"
                "RCOOH + SOCl₂ → RCOCl + SO₂ + HCl.\n"
                "아실 클로라이드는 좋은 이탈기(Cl⁻)를 가진 활성화된 카르보닐.\n"
                "이 단계는 통상적 산 활성화."
            ),
            reactant_smiles="CC(=O)O",
            product_smiles="CC(=O)Cl",
            arrows=[
                ArrowData("full", "lone_pair", "SOCl₂",
                          "atom", "C=O (카르복실산)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=1),
            ],
            labels={"SOCl₂": "염소화 시약", "RCOCl": "아실 클로라이드"},
            energy_label="아실 클로라이드",
            reagents="SOCl₂, DMF (촉매), 환류",
            notes="(COCl)₂(옥살릴 클로라이드)도 사용 가능, 더 온화한 조건",
        ),
        MechanismStep(
            step_number=2,
            title="디아조메탄 반응 → α-디아조케톤",
            description=(
                "아실 클로라이드에 디아조메탄(CH₂N₂) 2당량을 가합니다.\n"
                "1당량: 친핵 아실 치환으로 RCOCHN₂(α-디아조케톤) 형성.\n"
                "2번째 당량: 부산물 HCl 중화.\n"
                "CH₂N₂는 매우 독성/폭발성: 밀리몰 스케일만."
            ),
            reactant_smiles="CC(=O)Cl",
            product_smiles="CC(=O)C=[N+]=[N-]",
            arrows=[
                ArrowData("full", "lone_pair", "CH₂N₂ (C 친핵체)",
                          "atom", "C=O (아실 클로라이드)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl⁻ (이탈)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=3),
            ],
            labels={"CH₂N₂": "디아조메탄 (2 eq)", "α-디아조케톤": "RCOCHN₂"},
            energy_label="α-디아조케톤",
            reagents="CH₂N₂ (에테르, 0°C)",
            notes="⚠️ CH₂N₂는 독성+폭발성. TMS-디아조메탄(TMSCHN₂)이 안전 대안.",
        ),
        MechanismStep(
            step_number=3,
            title="Wolff 전위 → 케텐 중간체",
            description=(
                "Ag₂O(또는 hν, Δ) 촉매로 α-디아조케톤에서 N₂가 이탈합니다.\n"
                "카르벤 중간체 형성 → 1,2-shift(Wolff 전위) → 케텐(R-CH=C=O).\n"
                "케텐은 매우 반응성이 높은 중간체.\n"
                "Ag⁺는 N₂ 이탈을 촉진하는 Lewis 산 역할."
            ),
            reactant_smiles="CC(=O)C=[N+]=[N-]",
            product_smiles="CC=C=O",
            arrows=[
                ArrowData("full", "bond", "C-N₂ 결합 (N₂ 이탈)",
                          "atom", "카르벤", "#E53935", 0.3,
                          from_atom_idx=2, to_atom_idx=2),
                ArrowData("full", "bond", "C-C 결합 (1,2-shift)",
                          "atom", "케텐 C=C=O", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=2),
            ],
            labels={"Wolff 전위": "1,2-shift", "케텐": "RCH=C=O"},
            is_transition_state=True,
            energy_label="TS: Wolff 전위 (카르벤 → 케텐)",
            reagents="Ag₂O, H₂O, THF, Δ",
            notes="Wolff 전위: α-카르보닐 카르벤의 1,2-shift. 입체화학 보존.",
        ),
        MechanismStep(
            step_number=4,
            title="케텐 포획 → 동족산",
            description=(
                "케텐(RCH=C=O)이 H₂O(또는 ROH, NHR₂)와 반응합니다.\n"
                "H₂O 포획 → RCH₂COOH (동족 카르복실산, C₁ 삽입).\n"
                "ROH 포획 → RCH₂CO₂R' (동족 에스터).\n"
                "총괄: RCOOH → RCH₂COOH (탄소 1개 증가)."
            ),
            reactant_smiles="CC=C=O",
            product_smiles="CCC(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "H₂O (친핵체)",
                          "atom", "C=C=O (케텐)", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=2),
            ],
            labels={"H₂O": "친핵체", "RCH₂COOH": "동족산"},
            energy_label="생성물 (동족 카르복실산)",
            reagents="H₂O 또는 MeOH",
            notes="총괄: RCOOH → RCH₂COOH. C₁ homologation의 대표적 방법.",
        ),
    ],
    energy_diagram=[
        ("반응물\nRCOOH", 0.0),
        ("RCOCl", -2.0),
        ("α-디아조케톤\nRCOCHN₂", 5.0),
        ("TS: Wolff 전위\n(카르벤)", 25.0),
        ("케텐\nRCH=C=O", 10.0),
        ("생성물\nRCH₂COOH", -15.0),
    ],
)

# ─── Yamaguchi Esterification ───────────────────────────────────────────────
# 대표 반응: RCOOH + R'OH (Yamaguchi reagent) → 매크로락톤
# Ch21: 매크로락톤화의 핵심 방법

MECHANISMS["yamaguchi_esterification"] = MechanismData(
    mechanism_type="yamaguchi_esterification",
    title="야마구치 에스터화 (Yamaguchi Macrolactonization)",
    total_steps=3,
    overall_description=(
        "2,4,6-트리클로로벤조일 클로라이드(Yamaguchi 시약)를 사용하는 "
        "매크로락톤화(macrolactonization) 방법입니다. "
        "(1) 혼합 무수물(mixed anhydride) 형성, "
        "(2) DMAP 촉매에 의한 활성 에스터 형성, "
        "(3) 고희석 조건에서 분자 내 에스터화 → 매크로락톤. "
        "천연물 전합성(erythromycin, epothilone 등)에 필수적 방법."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="혼합 무수물 형성",
            description=(
                "카르복실산(seco-acid)의 카르복실레이트가 "
                "Yamaguchi 시약(2,4,6-Cl₃C₆H₂COCl)에 친핵 아실 치환합니다.\n"
                "혼합 무수물(mixed anhydride) 형성.\n"
                "Et₃N이 생성된 HCl을 중화.\n"
                "트리클로로벤조일의 ortho-Cl이 입체적으로 차폐 → 선택적 반응."
            ),
            reactant_smiles="CC(=O)O.O=C(Cl)c1c(Cl)cc(Cl)cc1Cl",
            product_smiles="CC(=O)OC(=O)c1c(Cl)cc(Cl)cc1Cl",
            arrows=[
                ArrowData("full", "lone_pair", "RCOO⁻ (카르복실레이트)",
                          "atom", "C=O (Yamaguchi Cl)", "#E53935", 0.4,
                          from_atom_idx=2, to_atom_idx=3),
                ArrowData("full", "bond", "C-Cl 결합",
                          "atom", "Cl⁻ (이탈기)", "#1565C0", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
            ],
            labels={"Yamaguchi": "2,4,6-Cl₃C₆H₂COCl", "Et₃N": "HCl 중화"},
            energy_label="혼합 무수물",
            reagents="2,4,6-Cl₃C₆H₂COCl, Et₃N, THF, 0°C",
            notes="ortho-Cl₂ 치환 → 입체 효과로 혼합 무수물의 대칭 무수물화 억제",
        ),
        MechanismStep(
            step_number=2,
            title="DMAP 촉매 활성 에스터 형성",
            description=(
                "DMAP(4-디메틸아미노피리딘)이 혼합 무수물의 덜 입체적인 쪽을 공격합니다.\n"
                "DMAP-아실 에스터(활성 에스터) 형성.\n"
                "DMAP의 초친핵성: 피리딘보다 10⁴배 빠른 아실 전달.\n"
                "Yamaguchi의 ortho-Cl → DMAP이 R-CO 쪽만 선택적 공격."
            ),
            reactant_smiles="CC(=O)OC(=O)c1c(Cl)cc(Cl)cc1Cl",
            product_smiles="CC(=O)[n+]1ccc(N(C)C)cc1",  # DMAP-acyl pyridinium (RDKit-safe)
            arrows=[
                ArrowData("full", "lone_pair", "DMAP (초친핵 촉매)",
                          "atom", "C=O (R-CO 쪽)", "#4CAF50", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
            ],
            labels={"DMAP": "아실 전달 촉매", "활성 에스터": "DMAP-acyl"},
            energy_label="DMAP-아실 에스터",
            reagents="DMAP (촉매량), 톨루엔",
            notes="DMAP 메커니즘: 빈 p-궤도 안정화 → 뛰어난 이탈기 → 빠른 전달",
        ),
        MechanismStep(
            step_number=3,
            title="분자 내 매크로락톤화 (고희석)",
            description=(
                "DMAP-아실 에스터의 같은 분자 내 OH가 분자 내 에스터화합니다.\n"
                "고희석(0.001-0.01 M): 분자 내 반응 >> 분자 간 반응(올리고머화 방지).\n"
                "서서히 적가(syringe pump): 국소 농도를 낮게 유지.\n"
                "최종: 매크로락톤(12~20원 고리) + DMAP 재생."
            ),
            reactant_smiles="CC(=O)[n+]1ccc(N(C)C)cc1",  # DMAP-acyl pyridinium (RDKit-safe)
            product_smiles="CC(=O)O",
            arrows=[
                ArrowData("full", "lone_pair", "OH (분자 내 친핵체)",
                          "atom", "C=O (DMAP-acyl)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=1),
            ],
            labels={"고희석": "0.001-0.01 M", "매크로락톤": "12-20원 고리"},
            energy_label="생성물 (매크로락톤)",
            reagents="고희석 (톨루엔, syringe pump 적가)",
            notes="대안: Mitsunobu/Corey-Nicolaou/Mukaiyama. Yamaguchi가 가장 범용적.",
        ),
    ],
    energy_diagram=[
        ("반응물\nseco-acid", 0.0),
        ("혼합 무수물", -5.0),
        ("DMAP-아실 에스터", -8.0),
        ("TS: 분자 내 공격", 15.0),
        ("생성물\n매크로락톤", -12.0),
    ],
)

# ─── Julia Olefination ──────────────────────────────────────────────────────
# 대표 반응: ArSO₂CH₂R + R'CHO → RCH=CHR' (E-선택적)
# Ch19: 술폰 → 알켄

MECHANISMS["julia_olefination"] = MechanismData(
    mechanism_type="julia_olefination",
    title="줄리아 올레핀화 (Julia-Lythgoe Olefination)",
    total_steps=3,
    overall_description=(
        "페닐술폰(PhSO₂CH₂R)을 염기(n-BuLi)로 탈양성자화하여 "
        "α-술포닐 카르바니온을 생성한 뒤 알데히드에 첨가합니다. "
        "β-히드록시술폰 중간체 → 아세틸화 → Na/Hg 환원적 제거 → E-알켄. "
        "Modified Julia(Barbier 조건)는 1-pot: BT-술폰 사용 → 직접 E-알켄. "
        "Wittig/HWE와 상보적: 특히 trans-이중결합에 유리."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="α-술포닐 카르바니온 형성 + 알데히드 첨가",
            description=(
                "n-BuLi로 PhSO₂CH₂R의 α-H를 탈양성자화합니다.\n"
                "pKa ≈ 22-25 (술포닐 안정화된 카르바니온).\n"
                "카르바니온이 알데히드(R'CHO) C=O에 친핵 첨가.\n"
                "β-히드록시술폰(β-hydroxy sulfone) 형성."
            ),
            reactant_smiles="CS(=O)(=O)c1ccccc1.O=CC",
            product_smiles="CC(O)CS(=O)(=O)c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "n-BuLi (강염기)",
                          "atom", "α-H (술포닐)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
                ArrowData("full", "negative_charge", "C⁻ (카르바니온)",
                          "atom", "C=O (알데히드)", "#1565C0", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"n-BuLi": "강염기", "β-히드록시술폰": "중간체"},
            energy_label="β-히드록시술폰",
            reagents="n-BuLi, THF, -78°C",
            notes="Classic Julia: 2단계 (첨가 후 별도 환원). Modified Julia: 1-pot.",
        ),
        MechanismStep(
            step_number=2,
            title="아세틸화 (활성화)",
            description=(
                "β-히드록시술폰의 OH를 아세틸화(AcCl 또는 Ac₂O)합니다.\n"
                "β-아세톡시술폰 → 이탈기로 활성화.\n"
                "이 단계가 다음 환원적 제거를 가능하게 함.\n"
                "벤조일화(BzCl)나 메실화(MsCl)도 사용 가능."
            ),
            reactant_smiles="CC(O)CS(=O)(=O)c1ccccc1",
            product_smiles="CC(OC(=O)C)CS(=O)(=O)c1ccccc1",
            arrows=[
                ArrowData("full", "lone_pair", "OH (친핵체)",
                          "atom", "Ac₂O (아실 전달)", "#4CAF50", 0.3,
                          from_atom_idx=2, to_atom_idx=-1),
            ],
            labels={"Ac₂O": "아세틸화 시약", "OAc": "이탈기로 활성화"},
            energy_label="β-아세톡시술폰",
            reagents="Ac₂O (또는 AcCl), 피리딘",
            notes="Modified Julia는 이 단계 불필요: BT-술폰이 직접 제거됨",
        ),
        MechanismStep(
            step_number=3,
            title="환원적 제거 → E-알켄",
            description=(
                "Na/Hg(나트륨 아말감) 환원으로 C-SO₂Ar 결합을 절단합니다.\n"
                "라디칼 또는 카르바니온 중간체를 경유하여 anti 제거.\n"
                "E-선택성: anti-periplanar 배치에서 OAc와 SO₂Ph 동시 제거.\n"
                "최종: E-알켄 + PhSO₂Na + AcONa."
            ),
            reactant_smiles="CC(OC(=O)C)CS(=O)(=O)c1ccccc1",
            product_smiles="C/C=C\\C",
            arrows=[
                ArrowData("full", "bond", "C-SO₂Ph (환원적 절단)",
                          "atom", "PhSO₂⁻ (이탈)", "#E53935", 0.3,
                          from_atom_idx=3, to_atom_idx=4),
                ArrowData("full", "bond", "C-OAc (제거)",
                          "atom", "AcO⁻ (이탈)", "#1565C0", 0.3,
                          from_atom_idx=1, to_atom_idx=2),
            ],
            labels={"Na/Hg": "환원제", "anti 제거": "E-선택적"},
            energy_label="생성물 (E-알켄)",
            reagents="Na/Hg, MeOH, -20°C",
            notes="E-선택성 기원: anti-periplanar 제거. Modified Julia는 retro-[2,3] 메커니즘.",
        ),
    ],
    energy_diagram=[
        ("반응물\nPhSO₂CH₂R + R'CHO", 0.0),
        ("β-히드록시술폰", -8.0),
        ("β-아세톡시술폰", -10.0),
        ("TS: 환원적 제거", 5.0),
        ("생성물\nE-알켄", -20.0),
    ],
)

# ─── Pictet-Spengler ────────────────────────────────────────────────────────
# 대표 반응: 트립타민 + RCHO → β-카르볼린 (테트라하이드로-β-카르볼린)
# Ch24: 알칼로이드 합성의 핵심 반응

MECHANISMS["pictet_spengler"] = MechanismData(
    mechanism_type="pictet_spengler",
    title="픽테-스펭글러 반응 (Pictet-Spengler)",
    total_steps=4,
    overall_description=(
        "트립타민(또는 페닐에틸아민)과 알데히드의 산촉매 축합으로 "
        "테트라하이드로-β-카르볼린(또는 테트라하이드로이소퀴놀린)을 형성합니다. "
        "알칼로이드 합성의 핵심 반응: reserpine, yohimbine, vincristine 등. "
        "(1) 이민(iminium) 형성, (2) 인돌 C2 → 이미늄 고리 닫힘, "
        "(3) 재방향족화 → 1,2,3,4-테트라하이드로-β-카르볼린."
    ),
    steps=[
        MechanismStep(
            step_number=1,
            title="이민(Schiff base) 형성",
            description=(
                "트립타민의 1차 아민(-NH₂)이 알데히드(RCHO)에 친핵 첨가합니다.\n"
                "카르비놀아민 → 탈수(-H₂O) → 이민(Schiff base, C=N).\n"
                "산촉매: 카르보닐 활성화 + 탈수 촉진.\n"
                "이민은 이후 양성자화되어 이미늄 이온(C=N⁺H)으로 활성화."
            ),
            reactant_smiles="NCCc1c[nH]c2ccccc12.O=CC",
            product_smiles="C(/CC)=N/CCc1c[nH]c2ccccc12",
            arrows=[
                ArrowData("full", "lone_pair", "NH₂ (트립타민)",
                          "atom", "C=O (알데히드)", "#E53935", 0.4,
                          from_atom_idx=0, to_atom_idx=-1),
            ],
            labels={"트립타민": "1차 아민", "RCHO": "알데히드"},
            energy_label="이민 (Schiff base)",
            reagents="H⁺ (촉매, TFA 또는 AcOH)",
            notes="이민 형성은 pH 4-5에서 최적 (산이 너무 강하면 아민 양성자화)",
        ),
        MechanismStep(
            step_number=2,
            title="이미늄 이온 형성 (양성자화)",
            description=(
                "산촉매에 의해 이민이 양성자화되어 이미늄 이온(C=N⁺H) 형성.\n"
                "이미늄 이온은 강한 친전자체: 인돌의 π 전자 공격을 유도.\n"
                "6-exo-trig 고리 닫힘(Baldwin 규칙 허용) 준비 단계.\n"
                "이 단계에서 입체화학이 결정됩니다."
            ),
            reactant_smiles="C(/CC)=N/CCc1c[nH]c2ccccc12",
            product_smiles="C(/CC)=[NH+]/CCc1c[nH]c2ccccc12",
            arrows=[
                ArrowData("full", "lone_pair", "H⁺ (산촉매)",
                          "atom", "C=N (이민 N)", "#E53935", 0.3,
                          from_atom_idx=-1, to_atom_idx=3),
            ],
            labels={"이미늄": "C=N⁺H (강한 친전자체)"},
            energy_label="이미늄 이온",
            reagents="H⁺",
            notes="이미늄 LUMO 에너지 저하 → 인돌 C2의 HOMO와 상호작용 촉진",
        ),
        MechanismStep(
            step_number=3,
            title="인돌 C2 → 이미늄 고리 닫힘 (Mannich-type)",
            description=(
                "인돌 C2 위치(전자밀도 높은)가 이미늄 탄소를 공격합니다.\n"
                "새로운 C-C 결합 형성: 6원 고리 완성.\n"
                "Mannich 반응의 분자 내 변형.\n"
                "σ-복합체 유사 중간체(인돌의 방향족성 일시 깨짐)."
            ),
            reactant_smiles="C(/CC)=[NH+]/CCc1c[nH]c2ccccc12",
            product_smiles="C1(CC)NCC2c3ccccc3[nH]C12",
            arrows=[
                ArrowData("full", "pi_bond", "인돌 C2 (π 전자)",
                          "atom", "C=N⁺H (이미늄)", "#E53935", 0.4,
                          from_atom_idx=-1, to_atom_idx=0),
            ],
            labels={"C2 공격": "인돌 β-위치", "Mannich-type": "분자 내"},
            is_transition_state=True,
            energy_label="TS: 6-exo-trig 고리 닫힘",
            reagents="",
            notes="Baldwin 규칙: 6-exo-trig = favored. 인돌 C2 > C3 반응성 (전자 밀도).",
        ),
        MechanismStep(
            step_number=4,
            title="재방향족화 → β-카르볼린",
            description=(
                "탈양성자화에 의해 인돌의 방향족성이 회복됩니다.\n"
                "최종 생성물: 1,2,3,4-테트라하이드로-β-카르볼린.\n"
                "방향족성 회복이 강한 열역학적 driving force.\n"
                "1-위치에 R기(알데히드 유래) 치환."
            ),
            reactant_smiles="C1(CC)NCC2c3ccccc3[nH]C12",
            product_smiles="C1(CC)NCC2c3ccccc3[nH]C12",
            arrows=[
                ArrowData("full", "bond", "C-H (탈양성자화)",
                          "atom", "인돌 방향족성 회복", "#4CAF50", 0.3,
                          from_atom_idx=-1, to_atom_idx=-1),
            ],
            labels={"β-카르볼린": "테트라하이드로", "재방향족화": "driving force"},
            energy_label="생성물 (테트라하이드로-β-카르볼린)",
            reagents="",
            notes="응용: reserpine, yohimbine, vincristine 전합성의 핵심 고리 닫힘 단계",
        ),
    ],
    energy_diagram=[
        ("반응물\n트립타민 + RCHO", 0.0),
        ("이민 (Schiff base)", -5.0),
        ("이미늄 이온", -2.0),
        ("TS: 고리 닫힘", 18.0),
        ("σ-복합체 유사", 10.0),
        ("생성물\nTH-β-카르볼린", -20.0),
    ],
)


# ============================================================================
# xTB DFT ENERGY COMPUTATION
# 하드코딩 에너지 다이어그램을 GFN2-xTB 단일점 에너지로 대체
# 호출 시점: 사용자가 메커니즘을 열 때 on-demand (각 xtb 계산 ~2-5초)
# 실패 시 기존 하드코딩 energy_diagram 유지 (graceful fallback)
# ============================================================================

# 1 Hartree = 627.509474 kcal/mol (NIST CODATA 2018)
_HARTREE_TO_KCAL = 627.509474


def _get_smiles_charge(smiles: str) -> int:
    """RDKit으로 SMILES의 총 형식 전하를 계산.

    Rule L: MolFromSmiles + None 체크 필수.
    Rule M: 실패 시 silent return 금지, logger.warning 필수.

    Args:
        smiles: SMILES 문자열 (단일 분자 또는 '.'로 연결된 복합 시스템)

    Returns:
        총 형식 전하 (정수). 파싱 실패 시 0 (중성 가정).
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import rdmolops
    except ImportError:
        logger.warning("_get_smiles_charge: RDKit not available, assuming charge=0")
        return 0

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("_get_smiles_charge: invalid SMILES '%s', assuming charge=0", smiles)
        return 0

    return rdmolops.GetFormalCharge(mol)


def compute_mechanism_energies(
    mech_data: 'MechanismData',
    timeout_per_calc: int = 30,
) -> Optional[List[Tuple[str, float]]]:
    """메커니즘의 각 단계 reactant/product SMILES에 대해 xTB SP 에너지를 계산하여
    실제 에너지 프로파일(kcal/mol 상대 에너지)을 생성.

    GFN2-xTB (Grimme group, 2019) level of theory 사용.
    각 고유 SMILES에 대해 한 번만 계산 (캐시).

    Args:
        mech_data: MechanismData 인스턴스 (steps 필드에 reactant/product SMILES 포함)
        timeout_per_calc: 개별 xtb 계산 타임아웃 (초, 기본 30초)

    Returns:
        [(라벨, 상대에너지_kcal)] 리스트, 또는 실패 시 None (기존 energy_diagram 사용 신호).

    Note:
        xtb WSL 호출이므로 각 계산 ~2-5초 소요.
        150개 메커니즘 전체를 사전 계산하지 않고, 사용자가 메커니즘을 열 때 on-demand로 호출.
    """
    # Rule N: 타입 가드
    if not isinstance(mech_data, MechanismData):
        logger.warning("compute_mechanism_energies: mech_data is not MechanismData (got %s)",
                       type(mech_data).__name__)
        return None

    if not isinstance(mech_data.steps, list) or len(mech_data.steps) == 0:
        logger.warning("compute_mechanism_energies: no steps in mechanism '%s'",
                       mech_data.mechanism_type)
        return None

    # Lazy import to avoid circular dependency and startup cost
    try:
        from orca_interface import run_xtb_calculation
    except ImportError:
        logger.warning("compute_mechanism_energies: orca_interface not available")
        return None

    # Collect all unique SMILES that need computation
    # 순서: 첫 번째 step의 reactant → 각 step의 product
    # 이렇게 하면 반응물 → (중간체) → 생성물 경로를 추적 가능
    ordered_smiles: List[str] = []
    ordered_labels: List[str] = []

    # 첫 번째 반응물
    first_step = mech_data.steps[0]
    if isinstance(first_step.reactant_smiles, str) and first_step.reactant_smiles.strip():
        ordered_smiles.append(first_step.reactant_smiles.strip())
        ordered_labels.append(first_step.energy_label or f"반응물")

    # 각 step의 product
    for step in mech_data.steps:
        if not isinstance(step, MechanismStep):
            continue
        prod = step.product_smiles if isinstance(step.product_smiles, str) else ""
        prod = prod.strip()
        if prod:
            # 중복 제거: 이전 SMILES와 동일하면 skip
            if ordered_smiles and prod == ordered_smiles[-1]:
                continue
            label = step.energy_label or step.title or f"Step {step.step_number}"
            ordered_smiles.append(prod)
            ordered_labels.append(label)

    if len(ordered_smiles) < 2:
        logger.warning("compute_mechanism_energies: need at least 2 species for energy profile "
                       "(got %d) in '%s'", len(ordered_smiles), mech_data.mechanism_type)
        return None

    # Calculate xtb SP energy for each unique SMILES
    # 다중 프래그먼트 SMILES (예: "CBr.[OH-]")는 각 프래그먼트를 개별 계산 후 합산
    # 이유: xtb가 dot-separated 시스템을 3D 임베딩할 때 fragment 간 거리 의존적 오차 발생
    # 물리적 근거: 비결합 fragment의 총 에너지 = sum(E_fragment_i)
    fragment_cache: Dict[str, Optional[float]] = {}  # single-fragment SMILES → energy (Eh)
    absolute_energies: List[Optional[float]] = []

    for smi in ordered_smiles:
        # Split multi-fragment SMILES
        fragments = [f.strip() for f in smi.split('.') if f.strip()]
        if not fragments:
            logger.warning("compute_mechanism_energies: empty SMILES encountered")
            absolute_energies.append(None)
            continue

        total_energy: float = 0.0
        all_ok = True

        for frag in fragments:
            if frag in fragment_cache:
                cached = fragment_cache[frag]
                if cached is None:
                    all_ok = False
                    break
                total_energy += cached
                continue

            frag_charge = _get_smiles_charge(frag)
            result = run_xtb_calculation(frag, calc_type='sp', charge=frag_charge,
                                         timeout=timeout_per_calc)

            if result.success and result.energy_eh is not None:
                fragment_cache[frag] = result.energy_eh
                total_energy += result.energy_eh
                logger.info("xTB SP energy for fragment '%s': %.6f Eh (charge=%d)",
                            frag, result.energy_eh, frag_charge)
            else:
                err_msg = result.error_message if hasattr(result, 'error_message') else "unknown"
                logger.warning("xTB SP failed for fragment '%s': %s", frag, err_msg)
                fragment_cache[frag] = None
                all_ok = False
                break

        if all_ok:
            absolute_energies.append(total_energy)
            logger.info("xTB total energy for '%s': %.6f Eh (%d fragments)",
                        smi, total_energy, len(fragments))
        else:
            absolute_energies.append(None)

    # Check that at least the reference (first) and one other energy succeeded
    if absolute_energies[0] is None:
        logger.warning("compute_mechanism_energies: reference energy (first reactant) failed "
                       "for '%s' — falling back to hardcoded values",
                       mech_data.mechanism_type)
        return None

    # Convert to relative energies in kcal/mol (relative to first species)
    ref_energy = absolute_energies[0]
    new_diagram: List[Tuple[str, float]] = []
    any_success = False

    for i, (label, abs_e) in enumerate(zip(ordered_labels, absolute_energies)):
        if abs_e is not None:
            # Eh → kcal/mol relative to reference
            rel_kcal = (abs_e - ref_energy) * _HARTREE_TO_KCAL
            new_diagram.append((label, round(rel_kcal, 1)))
            if i > 0:
                any_success = True
        else:
            # This species failed — use placeholder "?" but keep the profile going
            new_diagram.append((label, 0.0))

    if not any_success:
        logger.warning("compute_mechanism_energies: no product/intermediate energies computed "
                       "for '%s' — falling back to hardcoded values",
                       mech_data.mechanism_type)
        return None

    # Sanity check: gas-phase xTB can give unreasonable values for ionic reactions
    # (heterolysis in vacuum vs solution is ~100+ kcal/mol different).
    # 임계값: 어떤 단계든 |ΔE| > 200 kcal/mol이면 gas-phase artifact로 판단하고
    # 하드코딩 값으로 fallback (교육용 목적에서 솔벤트 효과가 중요한 반응은 경험값이 더 적절)
    _MAX_REASONABLE_DELTA = 200.0  # kcal/mol — gas-phase cutoff for ionic reactions
    for label, rel_e in new_diagram:
        if abs(rel_e) > _MAX_REASONABLE_DELTA:
            logger.warning(
                "compute_mechanism_energies: unreasonable energy %.1f kcal/mol for '%s' "
                "in '%s' (gas-phase artifact for ionic reaction) — falling back to hardcoded",
                rel_e, label, mech_data.mechanism_type
            )
            return None

    logger.info("xTB energy profile for '%s': %s (GFN2-xTB level of theory)",
                mech_data.mechanism_type,
                [(lbl, f"{e:.1f}") for lbl, e in new_diagram])

    return new_diagram


def get_mechanism(mechanism_type: str) -> Optional[MechanismData]:
    """메커니즘 타입으로 데이터 조회

    M450: 대소문자/공백 정규화 후 조회 — MECHANISMS 키는 소문자 언더스코어.
    e.g. "SN2" → "sn2", "Diels-Alder" → "diels-alder" (하이픈 보존, 키는 diels_alder).
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    _mechs = MECHANISMS if isinstance(MECHANISMS, dict) else {}  # N guard

    if not isinstance(mechanism_type, str):
        _log.warning("get_mechanism: mechanism_type is not str (got %s)", type(mechanism_type).__name__)
        return None

    # 1차: 원본 그대로 조회
    result = _mechs.get(mechanism_type)
    if result is not None:
        return result

    # 2차: 소문자 + 공백→언더스코어 + 하이픈→언더스코어 정규화 (M450 대소문자 불일치 방어)
    normalized = mechanism_type.strip().lower().replace(" ", "_").replace("-", "_")
    result = _mechs.get(normalized)
    if result is not None:
        _log.info("get_mechanism: '%s' → normalized '%s' 조회 성공", mechanism_type, normalized)
        return result

    _log.warning(
        "get_mechanism: '%s' (normalized='%s') not found in MECHANISMS (%d keys)",
        mechanism_type, normalized, len(_mechs),
    )
    return None


def get_available_mechanisms() -> List[str]:
    """사용 가능한 메커니즘 타입 목록"""
    return list(MECHANISMS.keys())


class ReactionMechanismDB:
    """반응 메커니즘 데이터베이스 접근 인터페이스.

    MECHANISMS 딕셔너리를 감싸는 편의 클래스.
    외부 코드(DryLab 보고서, 테스트 스크립트 등)에서 통일된 API로 접근 가능.
    """

    def get_mechanism(self, mechanism_type: str) -> Optional[MechanismData]:
        """메커니즘 타입으로 데이터 조회"""
        _mechs = MECHANISMS if isinstance(MECHANISMS, dict) else {}  # N guard
        return _mechs.get(mechanism_type)

    def get_all_reactions(self) -> List[dict]:
        """모든 등록된 반응 메커니즘 목록을 딕셔너리 형태로 반환.

        각 항목은 최소한 'name'(title), 'key'(mechanism_type) 키를 포함.
        """
        result = []
        for key, mdata in MECHANISMS.items():
            result.append({
                "key": key,
                "name": mdata.title,
                "mechanism_type": mdata.mechanism_type,
            })
        return result

    def get_all_keys(self) -> List[str]:
        """등록된 메커니즘 키 목록"""
        return list(MECHANISMS.keys())

    def __len__(self) -> int:
        return len(MECHANISMS)


def resolve_atom_map_indices(arrows: List[ArrowData], mol) -> List[ArrowData]:
    """Bug 3 Fix (M894): atom_map_num 기반 ArrowData idx 보정.

    MECHANISMS dict의 from_atom_idx/to_atom_idx는 하드코딩된 값으로
    Chem.MolFromSmiles() 이후 RDKit 원자 재정렬에 의해 잘못된 원자를 가리킬 수 있음.

    이 함수는 ArrowData.from_atom_map/to_atom_map이 설정된 경우
    현재 mol 객체에서 해당 atom map number를 가진 원자의 실제 idx로 보정한다.

    from_atom_map == -1이면 기존 from_atom_idx 유지 (하위 호환).

    Args:
        arrows: 보정할 ArrowData 리스트
        mol: Chem.MolFromSmiles()로 파싱된 RDKit Mol 객체

    Returns:
        보정된 ArrowData 리스트 (기존 리스트를 수정하지 않고 새 리스트 반환)
    """
    import copy  # 모듈 레벨 import 불필요 — 함수 내 lazy import

    if mol is None:
        logger.warning("resolve_atom_map_indices: mol is None, 원래 arrows 반환")
        return arrows

    # Rule N: isinstance guard
    if not isinstance(arrows, list):
        logger.warning("resolve_atom_map_indices: arrows is not list (got %s)",
                       type(arrows).__name__)
        return arrows

    # atom_map_num → 현재 idx 역변환 맵 구성
    mapnum_to_idx: Dict[int, int] = {}
    try:
        for atom in mol.GetAtoms():
            mnum = atom.GetAtomMapNum()
            if mnum > 0:
                mapnum_to_idx[mnum] = atom.GetIdx()
    except Exception as e:
        logger.warning("resolve_atom_map_indices: atom map 구성 실패: %s", e)
        return arrows

    if not mapnum_to_idx:
        # atom_map_num이 없는 SMILES (대부분의 경우) — 기존 idx 그대로
        return arrows

    resolved: List[ArrowData] = []
    for arrow in arrows:
        # Rule N: isinstance guard
        if not isinstance(arrow, ArrowData):
            resolved.append(arrow)
            continue

        new_arrow = copy.copy(arrow)  # shallow copy (fromt_type/labels 공유)

        # from_atom_map 보정
        if getattr(new_arrow, 'from_atom_map', -1) > 0:
            from_map = new_arrow.from_atom_map
            if from_map in mapnum_to_idx:
                new_arrow.from_atom_idx = mapnum_to_idx[from_map]
                logger.debug("resolve: from_atom_map=%d → from_atom_idx=%d",
                             from_map, new_arrow.from_atom_idx)
            else:
                logger.warning("resolve_atom_map_indices: from_atom_map=%d not found in mol",
                               from_map)

        # to_atom_map 보정
        if getattr(new_arrow, 'to_atom_map', -1) > 0:
            to_map = new_arrow.to_atom_map
            if to_map in mapnum_to_idx:
                new_arrow.to_atom_idx = mapnum_to_idx[to_map]
                logger.debug("resolve: to_atom_map=%d → to_atom_idx=%d",
                             to_map, new_arrow.to_atom_idx)
            else:
                logger.warning("resolve_atom_map_indices: to_atom_map=%d not found in mol",
                               to_map)

        resolved.append(new_arrow)

    return resolved
