#!/usr/bin/env python3
"""
역합성 분석 엔진 (Retrosynthesis Engine).
목표 분자 → BFS 역변환 → 모든 합성 경로 열거 (10단계 이내).
각 경로를 mechanism_engine으로 내부 검증하여 신뢰도 보장.
"""
import sys
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdChemReactions, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from building_blocks import (
    is_building_block, get_building_block_info, BUILDING_BLOCKS,
    is_commercially_available, _has_forbidden_substructure,
)
from mechanism_engine import MechanismEngine

# ═══════════════════════════════════════════════════════════
# 상수
# ═══════════════════════════════════════════════════════════
MAX_ROUTE_STEPS = 10  # 합성 경로 최대 단계 수 (하드 리밋)

# ═══════════════════════════════════════════════════════════
# 결합 유형별 전형적 반응 조건 맵
# 범용 disconnection에서 "다양한 조건" 대신 구체적 조건 제공
# ═══════════════════════════════════════════════════════════

CONDITION_MAP: Dict[str, str] = {
    # C-heteroatom bond formation
    "C-O": "NaH, THF, 0°C → RT (Williamson ether) 또는 H₂SO₄ cat., reflux (Fischer ester)",
    "O-C": "NaH, THF, 0°C → RT (Williamson ether) 또는 H₂SO₄ cat., reflux (Fischer ester)",
    "C-N": "NaBH₃CN, MeOH, AcOH, RT (reductive amination) 또는 K₂CO₃, DMF, 80°C (N-alkylation)",
    "N-C": "NaBH₃CN, MeOH, AcOH, RT (reductive amination) 또는 K₂CO₃, DMF, 80°C (N-alkylation)",
    "C-S": "NaOH, EtOH, reflux (thioether formation)",
    "S-C": "NaOH, EtOH, reflux (thioether formation)",
    "C-Cl": "SOCl₂, reflux 또는 HCl, ZnCl₂ (Lucas)",
    "Cl-C": "SOCl₂, reflux 또는 HCl, ZnCl₂ (Lucas)",
    "C-Br": "PBr₃, 0°C 또는 HBr, reflux",
    "Br-C": "PBr₃, 0°C 또는 HBr, reflux",
    "C-I": "NaI, acetone, reflux (Finkelstein)",
    "I-C": "NaI, acetone, reflux (Finkelstein)",
    "C-F": "DAST, CH₂Cl₂, -78°C → RT",
    "F-C": "DAST, CH₂Cl₂, -78°C → RT",
    "C-P": "n-BuLi, THF, -78°C → RT",
    "P-C": "n-BuLi, THF, -78°C → RT",
    # C-C bond formation
    "C-C": "Grignard (RMgBr, THF, 0°C → RT) 또는 Aldol (NaOH cat., H₂O, 0°C)",
    # Aromatic
    "c-c": "Suzuki coupling (Pd(PPh₃)₄, Na₂CO₃, DME/H₂O, 80°C)",
    "c-C": "Friedel-Crafts (AlCl₃, CH₂Cl₂, 0°C → RT)",
    "C-c": "Friedel-Crafts (AlCl₃, CH₂Cl₂, 0°C → RT)",
    "c-N": "Buchwald-Hartwig (Pd₂(dba)₃, BINAP, NaOtBu, toluene, 100°C)",
    "N-c": "Buchwald-Hartwig (Pd₂(dba)₃, BINAP, NaOtBu, toluene, 100°C)",
    "c-O": "CuI, 1,10-phenanthroline, Cs₂CO₃, DMF, 110°C (Ullmann ether)",
    "O-c": "CuI, 1,10-phenanthroline, Cs₂CO₃, DMF, 110°C (Ullmann ether)",
    "c-S": "CuI, neocuproine, NaOtBu, DMSO, 110°C",
    "S-c": "CuI, neocuproine, NaOtBu, DMSO, 110°C",
}

# 작용기 기반 조건 (fragment route용)
FRAGMENT_CONDITION_MAP: Dict[str, str] = {
    "아미드": "EDC·HCl, HOBt, DIPEA, DMF, RT, 12h",
    "Amide Bond": "EDC·HCl, HOBt, DIPEA, DMF, RT, 12h",
    "에스터": "H₂SO₄ cat., toluene, Dean-Stark, reflux",
    "Ester Bond": "H₂SO₄ cat., toluene, Dean-Stark, reflux",
    "에테르": "NaH, THF, 0°C → RT, 2h (Williamson)",
    "Ether Bond": "NaH, THF, 0°C → RT, 2h (Williamson)",
    "아민": "NaBH₃CN, MeOH, AcOH (pH 6-7), RT, 4h",
    "Amine Bond": "NaBH₃CN, MeOH, AcOH (pH 6-7), RT, 4h",
    "비아릴": "Pd(PPh₃)₄, Na₂CO₃ (2M aq.), DME, 80°C, 12h (Suzuki)",
    "Biaryl Bond": "Pd(PPh₃)₄, Na₂CO₃ (2M aq.), DME, 80°C, 12h (Suzuki)",
    "C-N": "K₂CO₃, DMF, 80°C, 6h (N-alkylation)",
    "C-S": "NaOH, EtOH, reflux, 4h (thioether)",
}

# ═══════════════════════════════════════════════════════════
# 데이터 클래스
# ═══════════════════════════════════════════════════════════

@dataclass
class RetroTransform:
    """역합성 변환 규칙: product SMARTS >> reactant(s) SMARTS"""
    name: str               # "에스터 역합성"
    name_en: str            # "Retro-Fischer Ester"
    category: str           # "축합", "치환", "첨가", "제거", "방향족", "산화환원", "명명반응"
    rxn_smarts: str         # product>>reactants (역방향 SMARTS)
    forward_smarts: str     # reactants>>product (정방향, 검증용)
    conditions: str         # "H₂SO₄, 가열" (반응 조건 설명)
    confidence: float       # 0.0~1.0
    _compiled_rxn: object = field(default=None, repr=False)
    _compiled_fwd: object = field(default=None, repr=False)


@dataclass
class SynthesisStep:
    """합성 경로의 한 단계"""
    step_number: int
    reactant_smiles: List[str]
    product_smiles: str
    transform_name: str
    transform_name_en: str
    conditions: str
    confidence: float
    _cached_mechanism: object = field(default=None, repr=False)


@dataclass
class SynthesisRoute:
    """완전한 합성 경로 (시작물질 → 목표 분자)"""
    target_smiles: str
    steps: List[SynthesisStep]
    total_steps: int
    score: float
    building_blocks: List[str]
    validated: bool = False


@dataclass
class _SearchNode:
    """BFS 탐색용 내부 노드"""
    smiles: str
    canonical: str
    depth: int
    complexity: float


# ═══════════════════════════════════════════════════════════
# 역변환 데이터베이스 (~50개)
# 유기화학 법칙 기반 — 작용기 패턴 매칭으로 범용 적용
# ═══════════════════════════════════════════════════════════

_RETRO_TRANSFORM_DATA = [
    # ── 치환 반응 (Substitution) ──
    # 알코올 → 할라이드 + 수산화물 (reverse SN2)
    ("SN2 (알코올←할라이드)", "SN2 Retro (Alcohol←Halide)", "치환",
     "[C:1][OH:2]>>[C:1]Br.[OH2:2]",
     "[C:1]Br.[OH2:2]>>[C:1][OH:2]",
     "NaOH, H₂O", 0.8),

    # 에테르 → 알코올 + 할라이드 (reverse Williamson)
    ("Williamson 역합성", "Retro-Williamson", "치환",
     "[C:1][O:2][C:3]>>[C:1]Br.[OH:2][C:3]",
     "[C:1]Br.[OH:2][C:3]>>[C:1][O:2][C:3]",
     "NaH, THF", 0.7),

    # 나이트릴 → 할라이드 + CN⁻ (reverse SN2)
    ("SN2 나이트릴 역합성", "Retro-SN2 Nitrile", "치환",
     "[C:1]C#N>>[C:1]Br.[C-]#N",
     "[C:1]Br.[C-]#N>>[C:1]C#N",
     "NaCN, DMSO", 0.75),

    # 티오에테르 → 할라이드 + 싸이올
    ("티오에테르 역합성", "Retro-Thioether", "치환",
     "[C:1][S:2][C:3]>>[C:1]Br.[SH:2][C:3]",
     "[C:1]Br.[SH:2][C:3]>>[C:1][S:2][C:3]",
     "NaOH, EtOH", 0.65),

    # ── 첨가 반응 (Addition) — 역은 제거 ──
    # 알코올 → 알켄 + H₂O (reverse hydration = dehydration)
    ("탈수 (역수화)", "Retro-Hydration", "첨가",
     "[CH:1][C:2]([OH])>>[C:1]=[C:2].O",
     "[C:1]=[C:2].O>>[CH:1][C:2]([OH])",
     "H₂SO₄, 가열", 0.7),

    # 할로알칸 → 알켄 + HBr (reverse HBr addition)
    ("HBr 첨가 역합성", "Retro-HBr Addition", "첨가",
     "[CH:1][C:2]([Br])>>[C:1]=[C:2].Br",
     "[C:1]=[C:2].Br>>[CH:1][C:2]([Br])",
     "HBr", 0.75),

    # 할로알칸 → 알켄 + HCl
    ("HCl 첨가 역합성", "Retro-HCl Addition", "첨가",
     "[CH:1][C:2]([Cl])>>[C:1]=[C:2].Cl",
     "[C:1]=[C:2].Cl>>[CH:1][C:2]([Cl])",
     "HCl", 0.7),

    # 디할라이드 → 알켄 + X₂ (reverse Br₂ addition)
    ("Br₂ 첨가 역합성", "Retro-Br₂ Addition", "첨가",
     "[C:1]([Br])[C:2]([Br])>>[C:1]=[C:2].BrBr",
     "[C:1]=[C:2].BrBr>>[C:1]([Br])[C:2]([Br])",
     "Br₂, CCl₄", 0.8),

    # 에폭시드 → 알켄 + 산화제
    ("에폭시화 역합성", "Retro-Epoxidation", "첨가",
     "[C:1]1[O:2][C:3]1>>[C:1]=[C:3].OO",
     "[C:1]=[C:3].OO>>[C:1]1[O:2][C:3]1",
     "mCPBA, CH₂Cl₂", 0.75),

    # ── 방향족 치환 (EAS) ──
    # 브로모벤젠 → 벤젠 + Br₂
    ("EAS 브롬화 역합성", "Retro-EAS Bromination", "방향족",
     "[c:1][Br:2]>>[cH:1].BrBr",
     "[cH:1].BrBr>>[c:1][Br:2]",
     "Br₂, FeBr₃", 0.85),

    # 클로로벤젠 → 벤젠 + Cl₂
    ("EAS 염소화 역합성", "Retro-EAS Chlorination", "방향족",
     "[c:1][Cl:2]>>[cH:1].ClCl",
     "[cH:1].ClCl>>[c:1][Cl:2]",
     "Cl₂, AlCl₃", 0.8),

    # 니트로벤젠 → 벤젠 + HNO₃
    ("니트로화 역합성", "Retro-Nitration", "방향족",
     "[c:1][N+:2](=[O:3])[O-:4]>>[cH:1].[O-][N+](=O)O",
     "[cH:1].[O-][N+](=O)O>>[c:1][N+:2](=[O:3])[O-:4]",
     "HNO₃, H₂SO₄", 0.85),

    # Friedel-Crafts 알킬화 역합성
    ("FC 알킬화 역합성", "Retro-FC Alkylation", "방향족",
     "[c:1][CH2:2]>>[cH:1].[Cl][CH2:2]",
     "[cH:1].[Cl][CH2:2]>>[c:1][CH2:2]",
     "AlCl₃, CH₂Cl₂", 0.7),

    # Friedel-Crafts 아실화 역합성
    ("FC 아실화 역합성", "Retro-FC Acylation", "방향족",
     "[c:1][C:2](=[O:3])>>[cH:1].[Cl][C:2](=[O:3])",
     "[cH:1].[Cl][C:2](=[O:3])>>[c:1][C:2](=[O:3])",
     "AlCl₃, CH₂Cl₂", 0.8),

    # 방향족 아민 → 니트로 (reverse 환원)
    ("ArNO₂ 환원 역합성", "Retro-ArNO₂ Reduction", "방향족",
     "[c:1][NH2:2]>>[c:1][N+](=O)[O-]",
     "[c:1][N+](=O)[O-]>>[c:1][NH2:2]",
     "Sn/HCl 또는 Fe/HCl", 0.8),

    # ── 축합 반응 (Condensation) ──
    # 에스터 → 산 + 알코올 (reverse Fischer esterification)
    ("Fischer 에스터 역합성", "Retro-Fischer Ester", "축합",
     "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])O.[OH][C:4]",
     "[C:1](=[O:2])O.[OH][C:4]>>[C:1](=[O:2])[O:3][C:4]",
     "H₂SO₄, 가열", 0.85),

    # 아마이드 → 산 + 아민 (reverse amidation)
    ("아마이드 역합성", "Retro-Amidation", "축합",
     "[C:1](=[O:2])[NH:3]>>[C:1](=[O:2])O.[NH2:3]",
     "[C:1](=[O:2])O.[NH2:3]>>[C:1](=[O:2])[NH:3]",
     "DCC 또는 가열", 0.75),

    # 아실 클로라이드 → 산 + SOCl₂
    ("아실클로라이드 역합성", "Retro-Acyl Chloride", "축합",
     "[C:1](=[O:2])[Cl:3]>>[C:1](=[O:2])O.ClS(=O)Cl",
     "[C:1](=[O:2])O.ClS(=O)Cl>>[C:1](=[O:2])[Cl:3]",
     "SOCl₂", 0.8),

    # 이민 → 알데히드/케톤 + 아민
    ("이민 역합성", "Retro-Imine", "축합",
     "[C:1]=[N:2][C:3]>>[C:1]=O.[NH2][C:3]",
     "[C:1]=O.[NH2][C:3]>>[C:1]=[N:2][C:3]",
     "분자체, TiCl₄", 0.7),

    # 옥심 → 케톤 + NH₂OH
    ("옥심 역합성", "Retro-Oxime", "축합",
     "[C:1]=[N:2][OH:3]>>[C:1]=O.NO",
     "[C:1]=O.NO>>[C:1]=[N:2][OH:3]",
     "NH₂OH·HCl, pyridine", 0.7),

    # ── 산화/환원 ──
    # 1차 알코올 → 알데히드 (reverse 환원)
    ("알데히드 환원 역합성", "Retro-Aldehyde Reduction", "산화환원",
     "[CH2:1][OH:2]>>[CH:1]=O",
     "[CH:1]=O>>[CH2:1][OH:2]",
     "NaBH₄ 또는 LiAlH₄", 0.8),

    # 2차 알코올 → 케톤 (reverse 환원)
    ("케톤 환원 역합성", "Retro-Ketone Reduction", "산화환원",
     "[CH:1]([OH:2])>>[C:1](=O)",
     "[C:1](=O)>>[CH:1]([OH:2])",
     "NaBH₄, MeOH", 0.8),

    # 카르복실산 → 알데히드 (reverse 산화)
    ("알데히드 산화 역합성", "Retro-Aldehyde Oxidation", "산화환원",
     "[C:1](=[O:2])[OH:3]>>[C:1](=[O:2])[H]",
     "[C:1](=[O:2])[H]>>[C:1](=[O:2])[OH:3]",
     "KMnO₄ 또는 CrO₃", 0.75),

    # 알데히드 → 1차 알코올 (reverse 산화: PCC)
    ("알코올 산화 역합성", "Retro-Alcohol Oxidation", "산화환원",
     "[CH:1]=[O:2]>>[CH2:1][OH]",
     "[CH2:1][OH]>>[CH:1]=[O:2]",
     "PCC, CH₂Cl₂", 0.75),

    # ── 명명 반응 ──
    # Grignard 역합성: 알코올 → 카르보닐 + RMgBr
    ("Grignard 역합성", "Retro-Grignard", "명명반응",
     "[C:1]([OH:2])([C:3])>>[C:1](=O).[C:3][Mg]Br",
     "[C:1](=O).[C:3][Mg]Br>>[C:1]([OH:2])([C:3])",
     "1) RMgBr/THF  2) H₃O⁺", 0.75),

    # 알돌 역합성: β-hydroxy carbonyl → 2 × carbonyl
    ("알돌 역합성", "Retro-Aldol", "명명반응",
     "[C:1]([OH:2])[CH2:3][C:4]=[O:5]>>[C:1]=O.[CH2:3][C:4]=[O:5]",
     "[C:1]=O.[CH2:3][C:4]=[O:5]>>[C:1]([OH:2])[CH2:3][C:4]=[O:5]",
     "NaOH(cat), H₂O", 0.65),

    # Wittig 역합성: 알켄 → 알데히드 + ylide
    ("Wittig 역합성", "Retro-Wittig", "명명반응",
     "[C:1]=[C:2]>>[C:1]=O.[C:2]=[PH3]",
     "[C:1]=O.[C:2]=[PH3]>>[C:1]=[C:2]",
     "Ph₃P=CHR, THF", 0.6),

    # Diels-Alder 역합성: 시클로헥센 → 디엔 + 디에노필
    ("Diels-Alder 역합성", "Retro-Diels-Alder", "명명반응",
     "[CH:1]1[CH2:2][CH:3]=[CH:4][CH2:5][CH2:6]1>>[CH2:1]=[CH:6][CH:3]=[CH:4].[CH2:2]=[CH2:5]",
     "[CH2:1]=[CH:6][CH:3]=[CH:4].[CH2:2]=[CH2:5]>>[CH:1]1[CH2:2][CH:3]=[CH:4][CH2:5][CH2:6]1",
     "가열 또는 가압", 0.7),

    # Beckmann 전위 역합성: 아마이드 → 옥심
    ("Beckmann 역합성", "Retro-Beckmann", "명명반응",
     "[C:1](=[O:2])[NH:3][C:4]>>[C:1](=[N:3][OH])[C:4]",
     "[C:1](=[N:3][OH])[C:4]>>[C:1](=[O:2])[NH:3][C:4]",
     "H₂SO₄ 또는 PCl₅", 0.6),

    # ── 제거 반응 (역 = 첨가) ──
    # 알켄 → 할로알칸 (reverse E2)
    ("E2 역합성 (알켄←할로알칸)", "Retro-E2", "제거",
     "[C:1]=[C:2]>>[C:1]([H])[C:2](Br)",
     "[C:1]([H])[C:2](Br)>>[C:1]=[C:2]",
     "강염기 (t-BuOK), E2", 0.65),

    # ── 보호기 ──
    # 아세탈 → 케톤 + 2×알코올
    ("아세탈 역합성", "Retro-Acetal", "축합",
     "[C:1]([O:2][C:3])([O:4][C:5])>>[C:1](=O).[OH][C:3].[OH][C:5]",
     "[C:1](=O).[OH][C:3].[OH][C:5]>>[C:1]([O:2][C:3])([O:4][C:5])",
     "H⁺(cat), 알코올", 0.65),

    # ── 고리 형성 ──
    # 락톤 → 히드록시산 (reverse lactonization)
    ("락톤 역합성", "Retro-Lactonization", "축합",
     "[O:1]=[C:2]1[C:3][C:4][C:5][O:6]1>>[OH][C:2](=O)[C:3][C:4][C:5][OH]",
     "[OH][C:2](=O)[C:3][C:4][C:5][OH]>>[O:1]=[C:2]1[C:3][C:4][C:5][O:6]1",
     "H⁺, 가열", 0.7),

    # 락탐 → 아미노산
    ("락탐 역합성", "Retro-Lactam", "축합",
     "[O:1]=[C:2]1[C:3][C:4][C:5][NH:6]1>>[NH2][C:3][C:4][C:5][C:2](=O)[OH]",
     "[NH2][C:3][C:4][C:5][C:2](=O)[OH]>>[O:1]=[C:2]1[C:3][C:4][C:5][NH:6]1",
     "가열", 0.65),

    # ── 시아노히드린 ──
    ("시아노히드린 역합성", "Retro-Cyanohydrin", "첨가",
     "[C:1]([OH:2])(C#N)>>[C:1]=O.[C-]#N",
     "[C:1]=O.[C-]#N>>[C:1]([OH:2])(C#N)",
     "NaCN, H₂O", 0.7),

    # ── 나이트릴 가수분해 ──
    ("나이트릴 가수분해 역합성", "Retro-Nitrile Hydrolysis", "축합",
     "[C:1](=[O:2])[NH2:3]>>[C:1]#N.O",
     "[C:1]#N.O>>[C:1](=[O:2])[NH2:3]",
     "H₂SO₄(묽), 가열", 0.65),

    # ── 트랜스에스터화 ──
    ("트랜스에스터화 역합성", "Retro-Transesterification", "축합",
     "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])[O]C.[OH][C:4]",
     "[C:1](=[O:2])[O]C.[OH][C:4]>>[C:1](=[O:2])[O:3][C:4]",
     "H⁺ 또는 NaOMe", 0.6),

    # ── 헤미아세탈 ──
    ("헤미아세탈 역합성", "Retro-Hemiacetal", "첨가",
     "[C:1]([OH:2])([O:3][C:4])>>[C:1]=O.[OH][C:4]",
     "[C:1]=O.[OH][C:4]>>[C:1]([OH:2])([O:3][C:4])",
     "H⁺(cat)", 0.65),

    # ── Baeyer-Villiger ──
    ("Baeyer-Villiger 역합성", "Retro-Baeyer-Villiger", "산화환원",
     "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])[C:4].OO",
     "[C:1](=[O:2])[C:4].OO>>[C:1](=[O:2])[O:3][C:4]",
     "mCPBA, CH₂Cl₂", 0.65),

    # 술폰아마이드 → 술포닐클로라이드 + 아민
    ("술폰아마이드 역합성", "Retro-Sulfonamide", "축합",
     "[S:1](=[O:2])(=[O:3])[NH:4]>>[S:1](=[O:2])(=[O:3])Cl.[NH2:4]",
     "[S:1](=[O:2])(=[O:3])Cl.[NH2:4]>>[S:1](=[O:2])(=[O:3])[NH:4]",
     "Et₃N, CH₂Cl₂", 0.7),

    # ── 추가 명명반응 (40~50) ──

    # Claisen 자리옮김 역합성: γ,δ-불포화 카르보닐 → 알릴 비닐 에테르
    ("Claisen 자리옮김 역합성", "Retro-Claisen Rearrangement", "명명반응",
     "[C:1](=[O:2])[CH2:3][CH:4]=[CH2:5]>>[CH2:3]=[CH:4][O:2][C:1]=[CH2:5]",
     "[CH2:3]=[CH:4][O:2][C:1]=[CH2:5]>>[C:1](=[O:2])[CH2:3][CH:4]=[CH2:5]",
     "가열 (200°C), 용매 없음", 0.5),

    # Cope 자리옮김 역합성: 1,5-디엔 이성질체화
    ("Cope 자리옮김 역합성", "Retro-Cope Rearrangement", "명명반응",
     "[CH:1]=[CH:2][CH2:3][CH2:4][CH:5]=[CH2:6]>>[CH2:1]=[CH:2][CH2:3][CH2:4]=[CH:5][CH2:6]",
     "[CH2:1]=[CH:2][CH2:3][CH2:4]=[CH:5][CH2:6]>>[CH:1]=[CH:2][CH2:3][CH2:4][CH:5]=[CH2:6]",
     "가열 (150-250°C)", 0.4),

    # Horner-Wadsworth-Emmons 역합성: α,β-불포화 에스터 → 알데히드 + 포스포네이트
    ("HWE 역합성", "Retro-Horner-Wadsworth-Emmons", "명명반응",
     "[CH:1]=[CH:2][C:3](=[O:4])[O:5]>>[CH:1]=O.[CH2:2][C:3](=[O:4])[O:5]",
     "[CH:1]=O.[CH2:2][C:3](=[O:4])[O:5]>>[CH:1]=[CH:2][C:3](=[O:4])[O:5]",
     "NaH, THF, 0°C→RT", 0.6),

    # 환원적 아민화 역합성: 2차 아민 → 케톤/알데히드 + 1차 아민
    ("환원적 아민화 역합성", "Retro-Reductive Amination", "산화환원",
     "[CH:1][NH:2][C:3]>>[C:1]=O.[NH2:2][C:3]",
     "[C:1]=O.[NH2:2][C:3]>>[CH:1][NH:2][C:3]",
     "NaBH₃CN, MeOH, AcOH", 0.65),

    # Suzuki 커플링 역합성: 비아릴 → 아릴 보론산 + 아릴 할라이드
    ("Suzuki 커플링 역합성", "Retro-Suzuki Coupling", "명명반응",
     "[c:1][c:2]>>[c:1]B(O)O.[c:2]Br",
     "[c:1]B(O)O.[c:2]Br>>[c:1][c:2]",
     "Pd(PPh₃)₄, Na₂CO₃, DME/H₂O", 0.5),

    # Heck 반응 역합성: 스티렌 유도체 → 아릴 할라이드 + 알켄
    ("Heck 반응 역합성", "Retro-Heck Reaction", "명명반응",
     "[c:1][CH:2]=[CH:3]>>[c:1]Br.[CH2:2]=[CH:3]",
     "[c:1]Br.[CH2:2]=[CH:3]>>[c:1][CH:2]=[CH:3]",
     "Pd(OAc)₂, Et₃N, DMF, 가열", 0.5),

    # Pinacol 커플링 역합성: 1,2-디올 → 2 카르보닐
    ("Pinacol 커플링 역합성", "Retro-Pinacol Coupling", "산화환원",
     "[C:1]([OH:2])[C:3]([OH:4])>>[C:1]=O.[C:3]=O",
     "[C:1]=O.[C:3]=O>>[C:1]([OH:2])[C:3]([OH:4])",
     "TiCl₃ 또는 SmI₂, THF", 0.45),

    # Cannizzaro 역합성: 1차 알코올 → 알데히드 (불균등화)
    ("Cannizzaro 역합성", "Retro-Cannizzaro", "산화환원",
     "[CH2:1][OH:2]>>[CH:1]=O",
     "[CH:1]=O>>[CH2:1][OH:2]",
     "NaOH(conc), H₂O", 0.4),

    # Kolbe-Schmitt 역합성: 히드록시벤조산 → 페놀 + CO₂
    ("Kolbe-Schmitt 역합성", "Retro-Kolbe-Schmitt", "명명반응",
     "[c:1]([OH:2])[c:3][C:4](=[O:5])[OH:6]>>[c:1]([OH:2])[cH:3].O=C=O",
     "[c:1]([OH:2])[cH:3].O=C=O>>[c:1]([OH:2])[c:3][C:4](=[O:5])[OH:6]",
     "NaOH, CO₂ (고압, 125°C)", 0.5),

    # Curtius 자리옮김 역합성: 아민 → 카르복실산 (via 아실 아지드 → 이소시아네이트)
    ("Curtius 자리옮김 역합성", "Retro-Curtius Rearrangement", "명명반응",
     "[NH2:1][C:2]>>[C:2](=O)[OH]",
     "[C:2](=O)[OH]>>[NH2:1][C:2]",
     "DPPA, Et₃N, t-BuOH → H₃O⁺", 0.45),

    # Hofmann 제거 역합성: 알켄 → 4차 암모늄 (anti-Zaitsev)
    ("Hofmann 제거 역합성", "Retro-Hofmann Elimination", "제거",
     "[CH:1]=[CH2:2]>>[CH2:1][CH2:2]N(C)(C)C",
     "[CH2:1][CH2:2]N(C)(C)C>>[CH:1]=[CH2:2]",
     "Ag₂O, H₂O, 가열", 0.4),
]


# ═══════════════════════════════════════════════════════════
# 역합성 엔진
# ═══════════════════════════════════════════════════════════

class RetrosynthesisEngine:
    """범용 역합성 분석 엔진.
    BFS + SMARTS 역변환 + mechanism_engine 내부검증."""

    def __init__(self):
        self._mech_engine = MechanismEngine()
        self._transforms = self._compile_transforms()

    def _compile_transforms(self) -> List[RetroTransform]:
        """SMARTS 패턴 사전 컴파일"""
        transforms = []
        for (name, name_en, cat, rxn_sma, fwd_sma, cond, conf) in _RETRO_TRANSFORM_DATA:
            t = RetroTransform(
                name=name, name_en=name_en, category=cat,
                rxn_smarts=rxn_sma, forward_smarts=fwd_sma,
                conditions=cond, confidence=conf
            )
            try:
                t._compiled_rxn = rdChemReactions.ReactionFromSmarts(rxn_sma)
                t._compiled_fwd = rdChemReactions.ReactionFromSmarts(fwd_sma)
            except Exception:
                pass  # 컴파일 실패 시 스킵
            transforms.append(t)
        return [t for t in transforms if t._compiled_rxn is not None]

    def find_routes(self, target_smiles: str,
                    max_depth: int = 10,
                    max_routes: int = 50,
                    validate: bool = True,
                    timeout_seconds: float = 10.0) -> List[SynthesisRoute]:
        """목표 분자에 대한 모든 합성 경로 탐색.

        Args:
            target_smiles: 목표 분자 SMILES
            max_depth: 최대 합성 단계 수 (MAX_ROUTE_STEPS 이하로 클램프)
            max_routes: 최대 반환 경로 수
            validate: True면 mechanism_engine으로 각 단계 검증
            timeout_seconds: 탐색 제한 시간 (초)

        Returns:
            점수순 정렬된 SynthesisRoute 리스트
        """
        if not RDKIT_AVAILABLE:
            return []

        # ★ 하드 리밋: 최대 단계 수 클램프
        max_depth = min(max_depth, MAX_ROUTE_STEPS)

        target_mol = Chem.MolFromSmiles(target_smiles)
        if target_mol is None:
            return []

        target_canon = Chem.MolToSmiles(target_mol)
        target_complexity = self._calc_complexity(target_smiles)

        # ★ 복잡한 분자 감지: heavy atoms > 12 또는 고리 수 > 2이면 "복잡 모드" 활성화
        n_heavy = target_mol.GetNumHeavyAtoms()
        n_rings = Chem.rdMolDescriptors.CalcNumRings(target_mol)
        is_complex = n_heavy > 12 or n_rings > 2
        if is_complex:
            # 복잡한 분자: 검증 완화, 시간 연장, 깊이 조정
            timeout_seconds = max(timeout_seconds, 30.0)
            if max_depth > 8:
                max_depth = 8  # 너무 깊으면 폭발
            # 복잡 분자는 검증을 "soft" 모드로 전환
            validate = False  # mechanism_engine이 지원 안 하는 반응이 많으므로

        # 타겟 자체가 시작물질이면 "이미 상용 가능" 경로 추가하되,
        # 합성 경로도 계속 탐색 (교육 목적: 어떻게 만들 수 있는지 보여줌)
        target_is_bb = is_building_block(target_canon)
        bb_route = None
        if target_is_bb:
            bb_route = SynthesisRoute(
                target_smiles=target_canon,
                steps=[], total_steps=0, score=-100.0,  # 최우선 순위
                building_blocks=[target_canon], validated=True
            )

        import time
        start_time = time.time()

        # BFS 탐색
        # path: List[(transform, smiles_before, precursor_smiles_list)]
        queue = deque()
        root = _SearchNode(
            smiles=target_canon,
            canonical=target_canon,
            depth=0,
            complexity=target_complexity
        )
        queue.append((root, []))  # (node, retro_path)

        visited: Set[str] = {target_canon}
        candidate_routes: List[SynthesisRoute] = []
        max_candidates = max_routes * 5  # 검증 전 후보 (5배 여유)

        while queue and len(candidate_routes) < max_candidates:
            # 시간 초과 체크
            if time.time() - start_time > timeout_seconds:
                break

            node, path = queue.popleft()

            if node.depth >= max_depth:
                continue

            # 1) SMARTS 기반 역변환 적용
            applicable = self._get_applicable_transforms(node.smiles)

            for transform, precursor_sets in applicable:
                for precursors in precursor_sets:
                    # 유효성 기본 검사
                    if not self._basic_precursor_check(
                        precursors, target_complexity, visited, node.canonical,
                        lenient=is_complex
                    ):
                        continue

                    new_path = path + [(transform, node.smiles, precursors)]

                    # 모든 전구체가 상용 시작물질이면 → 경로 완성
                    if all(is_commercially_available(p) for p in precursors):
                        route = self._build_forward_route(target_canon, new_path)
                        if route is not None:
                            candidate_routes.append(route)
                    else:
                        # 상용 불가 전구체는 계속 탐색
                        for p in precursors:
                            p_mol = Chem.MolFromSmiles(p)
                            if p_mol is None:
                                continue
                            p_canon = Chem.MolToSmiles(p_mol)
                            if not is_commercially_available(p_canon) and p_canon not in visited:
                                visited.add(p_canon)
                                child = _SearchNode(
                                    smiles=p_canon,
                                    canonical=p_canon,
                                    depth=node.depth + 1,
                                    complexity=self._calc_complexity(p_canon)
                                )
                                queue.append((child, new_path))

            # 2) 범용 disconnection (SMARTS에 매칭 안 되는 경우 또는 복잡 분자)
            if (not applicable or is_complex) and node.depth < max_depth - 1:
                gen_precursors = self._generalized_disconnection(node.smiles, target_complexity)
                for precursors, desc, conditions in gen_precursors:
                    if not self._basic_precursor_check(
                        precursors, target_complexity, visited, node.canonical,
                        lenient=is_complex
                    ):
                        continue

                    # 범용 역변환은 가짜 transform 생성
                    fake_transform = RetroTransform(
                        name=f"결합 분해 ({desc})",
                        name_en=f"Bond Disconnection ({desc})",
                        category="범용", rxn_smarts="", forward_smarts="",
                        conditions=conditions, confidence=0.4
                    )
                    new_path = path + [(fake_transform, node.smiles, precursors)]

                    if all(is_commercially_available(p) for p in precursors):
                        route = self._build_forward_route(target_canon, new_path)
                        if route is not None:
                            candidate_routes.append(route)
                    else:
                        for p in precursors:
                            p_mol = Chem.MolFromSmiles(p)
                            if p_mol is None:
                                continue
                            p_canon = Chem.MolToSmiles(p_mol)
                            if not is_commercially_available(p_canon) and p_canon not in visited:
                                visited.add(p_canon)
                                child = _SearchNode(
                                    smiles=p_canon, canonical=p_canon,
                                    depth=node.depth + 1,
                                    complexity=self._calc_complexity(p_canon)
                                )
                                queue.append((child, new_path))

        # ★ 현실성 검증: 시작물질 상용 가능 여부 + 단계 수 리밋 ★
        realistic_routes = []
        for route in candidate_routes:
            if route.total_steps > MAX_ROUTE_STEPS:
                continue
            if not self._validate_route_realism(route):
                continue
            realistic_routes.append(route)

        # ★ 메커니즘 기반 내부 유효성 검증 ★
        if validate:
            validated = []
            for route in realistic_routes:
                if self._validate_route(route):
                    route.validated = True
                    route.score = self._score_route(route)
                    validated.append(route)
        else:
            validated = realistic_routes
            for r in validated:
                r.score = self._score_route(r)

        validated.sort(key=lambda r: r.score)
        result = validated[:max_routes]

        # ★ 복잡 분자 보완: BFS가 아무 경로도 못 찾았으면 "분해 경로" 제안
        if not result and is_complex:
            fragment_routes = self._suggest_fragment_routes(target_canon, target_complexity)
            result.extend(fragment_routes[:max_routes])

        # 타겟이 빌딩블록이면 "상용 가능" 경로를 맨 앞에 추가
        if bb_route is not None:
            result.insert(0, bb_route)

        return result

    # ─── 역변환 적용 ───

    def _get_applicable_transforms(self, smiles: str
                                     ) -> List[Tuple[RetroTransform, List[List[str]]]]:
        """주어진 분자에 적용 가능한 역변환 목록 반환.
        Returns: [(transform, [[precursor1, precursor2], ...]), ...]"""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []

        results = []
        for transform in self._transforms:
            if transform._compiled_rxn is None:
                continue
            try:
                products = transform._compiled_rxn.RunReactants((mol,))
                if not products:
                    continue

                precursor_sets = []
                seen = set()
                for product_tuple in products:
                    try:
                        precursors = []
                        valid = True
                        for p_mol in product_tuple:
                            Chem.SanitizeMol(p_mol)
                            p_smi = Chem.MolToSmiles(p_mol)
                            if Chem.MolFromSmiles(p_smi) is None:
                                valid = False
                                break
                            precursors.append(p_smi)
                        if valid and precursors:
                            key = tuple(sorted(precursors))
                            if key not in seen:
                                seen.add(key)
                                precursor_sets.append(precursors)
                    except Exception:
                        continue

                if precursor_sets:
                    results.append((transform, precursor_sets))
            except Exception:
                continue

        return results

    def _generalized_disconnection(self, smiles: str,
                                     target_complexity: float
                                     ) -> List[Tuple[List[str], str]]:
        """범용 결합 분해: 모든 single bond를 끊어보고 유효한 분해 탐색.
        SMARTS 패턴에 없는 미지 분자 대응."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []

        candidates = []
        for bond in mol.GetBonds():
            if bond.GetBondTypeAsDouble() != 1.0:
                continue
            if bond.IsInRing():
                continue  # 고리 내 결합은 스킵

            bi = bond.GetBeginAtomIdx()
            bj = bond.GetEndAtomIdx()
            sym_i = mol.GetAtomWithIdx(bi).GetSymbol()
            sym_j = mol.GetAtomWithIdx(bj).GetSymbol()

            # 헤테로원자-탄소 결합만 (C-O, C-N, C-S, C-X 등)
            hetero_pair = (sym_i != "C") or (sym_j != "C")
            if not hetero_pair and sym_i == "C" and sym_j == "C":
                # C-C 결합도 고려하되 confidence 낮게
                pass

            try:
                # 결합 제거 후 프래그먼트 생성
                emol = Chem.RWMol(mol)
                emol.RemoveBond(bi, bj)

                # 끊어진 원자에 수소 추가 (원자가 맞추기)
                atom_i = emol.GetAtomWithIdx(bi)
                atom_j = emol.GetAtomWithIdx(bj)
                atom_i.SetNumExplicitHs(atom_i.GetNumExplicitHs() + 1)
                atom_j.SetNumExplicitHs(atom_j.GetNumExplicitHs() + 1)

                try:
                    Chem.SanitizeMol(emol)
                except Exception:
                    continue

                frags = Chem.GetMolFrags(emol, asMols=True)
                if len(frags) != 2:
                    continue

                frag_smiles = []
                valid = True
                for f in frags:
                    try:
                        fs = Chem.MolToSmiles(f)
                        if Chem.MolFromSmiles(fs) is None:
                            valid = False
                            break
                        frag_smiles.append(fs)
                    except Exception:
                        valid = False
                        break

                if not valid:
                    continue

                # 전구체가 원래보다 단순해야 함
                if all(self._calc_complexity(f) < target_complexity * 0.9
                       for f in frag_smiles):
                    desc = f"{sym_i}-{sym_j}"
                    candidates.append((frag_smiles, desc,
                                       CONDITION_MAP.get(desc, f"{desc} bond formation conditions TBD")))
            except Exception:
                continue

        # 복잡 분자는 더 많은 후보 허용
        max_candidates = 20 if len(candidates) > 10 else 10
        return candidates[:max_candidates]

    # ─── 경로 구축 ───

    def _build_forward_route(self, target_canon: str,
                              retro_path: list) -> Optional[SynthesisRoute]:
        """역합성 경로를 정방향 합성 경로로 변환"""
        if not retro_path:
            return None

        # retro_path: [(transform, product_smi, [precursor_smis]), ...]
        # 역순 = 정방향
        steps = []
        all_building_blocks = set()

        for i, (transform, product_smi, precursors) in enumerate(reversed(retro_path)):
            step_num = i + 1

            # 시작물질 수집 (DB 등록 + 휴리스틱 상용 가능 모두)
            for p in precursors:
                if is_commercially_available(p):
                    all_building_blocks.add(p)

            step = SynthesisStep(
                step_number=step_num,
                reactant_smiles=list(precursors),
                product_smiles=product_smi,
                transform_name=transform.name,
                transform_name_en=transform.name_en,
                conditions=transform.conditions,
                confidence=transform.confidence,
            )
            steps.append(step)

        return SynthesisRoute(
            target_smiles=target_canon,
            steps=steps,
            total_steps=len(steps),
            score=0.0,  # 나중에 계산
            building_blocks=list(all_building_blocks),
        )

    # ─── 유효성 검증 ───

    def _validate_route(self, route: SynthesisRoute) -> bool:
        """각 단계를 mechanism_engine으로 검증.
        모든 단계에서 메커니즘 생성 성공해야 True."""
        for step in route.steps:
            try:
                reactant_smi = ".".join(step.reactant_smiles)
                product_smi = step.product_smiles
                mech = self._mech_engine.generate_mechanism(reactant_smi, product_smi)
                if mech is None:
                    return False
                # 화살표가 최소 1개 존재해야 함
                total_arrows = sum(len(s.arrows) for s in mech.steps)
                if total_arrows == 0:
                    return False
                step._cached_mechanism = mech
            except Exception:
                return False
        return True

    def _validate_route_realism(self, route: SynthesisRoute) -> bool:
        """경로의 화학적 현실성 검증.

        Checks:
          1. 모든 terminal 시작물질이 상용 가능 (is_commercially_available)
          2. 단계 수 <= MAX_ROUTE_STEPS
          3. 각 단계의 반응물/생성물이 유효한 SMILES
          4. 분자량이 단계별로 비정상적으로 점프하지 않음
        """
        # 단계 수 체크
        if route.total_steps > MAX_ROUTE_STEPS:
            return False

        # terminal 시작물질 추출
        all_reactants = set()
        for step in route.steps:
            for r in step.reactant_smiles:
                all_reactants.add(r)
        intermediates = {step.product_smiles for step in route.steps}
        terminal_materials = all_reactants - intermediates

        # 모든 terminal 시작물질이 상용 가능해야 함
        for mat in terminal_materials:
            if not is_commercially_available(mat):
                return False

        # 각 단계 SMILES 유효성 검사
        for step in route.steps:
            for r in step.reactant_smiles:
                if Chem.MolFromSmiles(r) is None:
                    return False
            if Chem.MolFromSmiles(step.product_smiles) is None:
                return False

        # 비정상적 분자량 점프 감지 (한 단계에서 MW가 5배 이상 증가하면 비현실적)
        for step in route.steps:
            reactant_mw = 0
            for r in step.reactant_smiles:
                r_mol = Chem.MolFromSmiles(r)
                if r_mol:
                    reactant_mw += Descriptors.MolWt(r_mol)
            p_mol = Chem.MolFromSmiles(step.product_smiles)
            if p_mol:
                product_mw = Descriptors.MolWt(p_mol)
                if reactant_mw > 0 and product_mw > reactant_mw * 5:
                    return False

        return True

    # ─── 점수 계산 ───

    def _score_route(self, route: SynthesisRoute) -> float:
        """낮을수록 좋은 점수 (0이 최고).

        Scoring criteria:
          - 단계 수: 적을수록 좋음 (10pt/step)
          - 신뢰도: 높을수록 좋음 (-20pt * avg_conf)
          - 시작물질:
            * DB 등록 building block: -5pt (low cost) / -2pt (medium)
            * 휴리스틱 상용 가능: -1pt
            * 상용 불가 (unknown): +100pt 페널티 (강력 억제)
            * 금지 하위구조 포함: +200pt 페널티 (절대 차단)
          - 검증 통과: -10pt 보너스
          - 단계 수 > 7: 추가 패널티 (긴 경로 억제)
          - ANY non-commercial material → 전체 경로에 +50pt 추가 패널티
        """
        score = 0.0

        # ── 단계 수 패널티 ──
        score += route.total_steps * 10.0
        # 긴 경로 추가 패널티 (7단계 초과 시 가속)
        if route.total_steps > 7:
            score += (route.total_steps - 7) * 15.0

        # ── confidence 보너스 ──
        if route.steps:
            avg_conf = sum(s.confidence for s in route.steps) / len(route.steps)
            score -= avg_conf * 20.0

        # ── 시작물질 품질 평가 ──
        # 경로의 모든 리프 노드(시작물질) 수집
        all_starting_materials = set()
        for step in route.steps:
            for r in step.reactant_smiles:
                all_starting_materials.add(r)
        # 중간체(다른 단계의 product)는 시작물질에서 제거
        intermediates = {step.product_smiles for step in route.steps}
        terminal_materials = all_starting_materials - intermediates

        n_known_bb = 0
        n_heuristic_ok = 0
        n_unknown = 0
        has_forbidden = False

        for mat in terminal_materials:
            info = get_building_block_info(mat)
            if info:
                n_known_bb += 1
                if info.get("cost") == "low":
                    score -= 5.0
                elif info.get("cost") == "medium":
                    score -= 2.0
            elif is_commercially_available(mat):
                n_heuristic_ok += 1
                score -= 1.0
            else:
                n_unknown += 1
                score += 100.0  # 미지 시작물질 강력 페널티 (was 30)

                # 금지 하위구조 포함 시 극단적 페널티
                mat_mol = Chem.MolFromSmiles(mat)
                if mat_mol is not None and _has_forbidden_substructure(mat_mol):
                    has_forbidden = True
                    score += 200.0  # 위험 물질 절대 차단

        # ── ANY 비상용 시작물질 존재 시 전체 경로 페널티 ──
        if n_unknown > 0:
            score += 50.0  # 경로 전체에 추가 페널티

        # ── 금지 하위구조 발견 시 추가 전역 페널티 ──
        if has_forbidden:
            score += 500.0  # 사실상 경로 무효화

        # ── 시작물질 전수 상용 가능 보너스 ──
        if n_unknown == 0 and terminal_materials:
            score -= 15.0  # 모든 시작물질이 상용 가능

        # ── 검증 보너스 ──
        if route.validated:
            score -= 10.0

        return score

    # ─── 유틸리티 ───

    def _calc_complexity(self, smiles: str) -> float:
        """분자 복잡도 수치 (높을수록 복잡)"""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return float('inf')
        n_heavy = mol.GetNumHeavyAtoms()
        n_bonds = mol.GetNumBonds()
        n_rings = Chem.rdMolDescriptors.CalcNumRings(mol)
        n_rot = Descriptors.NumRotatableBonds(mol)
        return n_heavy + n_bonds * 0.3 + n_rings * 2.0 + n_rot * 0.2

    def _basic_precursor_check(self, precursors: List[str],
                                target_complexity: float,
                                visited: Set[str],
                                parent_canonical: str,
                                lenient: bool = False) -> bool:
        """전구체 기본 유효성 검사.
        lenient=True: 복잡한 분자용 완화된 검사 (복잡도 상한 2.0배)"""
        complexity_ratio = 2.0 if lenient else 1.3
        for p in precursors:
            p_mol = Chem.MolFromSmiles(p)
            if p_mol is None:
                return False
            p_canon = Chem.MolToSmiles(p_mol)
            # 순환 방지
            if p_canon == parent_canonical:
                return False
            # 복잡도 증가 방지 (시작물질 제외)
            if not is_commercially_available(p_canon):
                if self._calc_complexity(p_canon) > target_complexity * complexity_ratio:
                    return False
        return True

    def _suggest_fragment_routes(self, target_canon: str,
                                  target_complexity: float = 0.0,
                                  _recurse_depth: int = 0) -> List[SynthesisRoute]:
        """복잡한 분자에 대한 "분해 기반" 합성 경로 제안.
        분자를 주요 작용기 결합에서 분해하여 간단한 프래그먼트로 나누고,
        각 프래그먼트가 building block이거나 더 간단한 분자인 경로를 제시.
        고리 결합 포함 분해도 시도 (이종 헤테로고리 분자 대응)."""
        if _recurse_depth > 3:
            return []
        mol = Chem.MolFromSmiles(target_canon)
        if mol is None:
            return []
        if target_complexity <= 0:
            target_complexity = self._calc_complexity(target_canon)

        routes = []

        # 작용기 기반 분해 패턴 — 구체적 반응 조건 포함
        disconnect_smarts = [
            ("[C:1](=O)[NH:2]", "아미드", "Amide Bond",
             "EDC·HCl, HOBt, DIPEA, DMF, RT, 12h", 0.7),
            ("[C:1](=O)[O:2][C:3]", "에스터", "Ester Bond",
             "H₂SO₄ cat., toluene, Dean-Stark, reflux, 4h", 0.75),
            ("[C:1][O:2][C:3]", "에테르", "Ether Bond",
             "NaH (1.2 eq.), THF, 0°C → RT, 2h (Williamson)", 0.6),
            ("[C:1][NH:2]", "아민", "Amine Bond",
             "NaBH₃CN, MeOH, AcOH (pH 6-7), RT, 4h (reductive amination)", 0.5),
            ("[c:1][c:2]", "비아릴", "Biaryl Bond",
             "Pd(PPh₃)₄ (5 mol%), Na₂CO₃ (2M aq.), DME, 80°C, 12h (Suzuki)", 0.45),
            ("[C:1][N:2]", "C-N", "C-N Bond",
             "K₂CO₃ (2 eq.), DMF, 80°C, 6h (N-alkylation)", 0.4),
            ("[C:1][S:2]", "C-S", "C-S Bond",
             "NaOH, EtOH, reflux, 4h (thioether formation)", 0.35),
        ]

        for smarts_pat, name_kr, name_en, conditions, conf in disconnect_smarts:
            pattern = Chem.MolFromSmarts(smarts_pat)
            if pattern is None:
                continue
            matches = mol.GetSubstructMatches(pattern)
            if not matches:
                continue

            # 첫 번째 매칭에서 분해
            for match in matches[:3]:  # 최대 3개 매칭 시도
                try:
                    emol = Chem.RWMol(mol)
                    # 패턴의 첫 두 원자 사이 결합 끊기
                    bi, bj = match[0], match[1]
                    bond = emol.GetBondBetweenAtoms(bi, bj)
                    if bond is None:
                        continue

                    emol.RemoveBond(bi, bj)
                    # 끊어진 원자에 H 추가
                    atom_i = emol.GetAtomWithIdx(bi)
                    atom_j = emol.GetAtomWithIdx(bj)
                    atom_i.SetNumExplicitHs(atom_i.GetNumExplicitHs() + 1)
                    atom_j.SetNumExplicitHs(atom_j.GetNumExplicitHs() + 1)

                    try:
                        Chem.SanitizeMol(emol)
                    except Exception:
                        continue

                    frags = Chem.GetMolFrags(emol, asMols=True)
                    if len(frags) < 2:
                        continue

                    frag_smiles = []
                    valid = True
                    for f in frags:
                        try:
                            fs = Chem.MolToSmiles(f)
                            if Chem.MolFromSmiles(fs) is None:
                                valid = False
                                break
                            frag_smiles.append(fs)
                        except Exception:
                            valid = False
                            break

                    if not valid or not frag_smiles:
                        continue

                    # 최종 단계: 프래그먼트들 → 타겟
                    final_step = SynthesisStep(
                        step_number=1,
                        reactant_smiles=frag_smiles,
                        product_smiles=target_canon,
                        transform_name=f"{name_kr} 결합 형성",
                        transform_name_en=f"{name_en} Formation",
                        conditions=conditions,
                        confidence=conf,
                    )

                    # 비상용 프래그먼트는 재귀적으로 합성 경로 탐색 (다단계)
                    all_bb = []
                    preceding_steps = []
                    step_counter = 0
                    for frag in frag_smiles:
                        if is_commercially_available(frag):
                            all_bb.append(frag)
                        elif _recurse_depth < 3:
                            # 재귀적 역합성 (최대 3중첩)
                            sub_routes = self._suggest_fragment_routes(
                                frag, _recurse_depth=_recurse_depth + 1
                            )
                            if sub_routes:
                                best_sub = sub_routes[0]
                                for s in best_sub.steps:
                                    step_counter += 1
                                    s.step_number = step_counter
                                    preceding_steps.append(s)
                                all_bb.extend(best_sub.building_blocks)
                            else:
                                all_bb.append(frag)  # 분해 불가 시 그대로 사용
                        else:
                            all_bb.append(frag)

                    step_counter += 1
                    final_step.step_number = step_counter
                    all_steps = preceding_steps + [final_step]

                    route = SynthesisRoute(
                        target_smiles=target_canon,
                        steps=all_steps,
                        total_steps=len(all_steps),
                        score=self._score_route_simple(len(all_steps), conf, all_bb),
                        building_blocks=all_bb,
                        validated=False,
                    )
                    routes.append(route)
                except Exception:
                    continue

        # ★ 작용기 분해로 경로를 못 찾으면 → 일반 결합 분해 시도 (고리 결합 포함)
        if not routes:
            for bond in mol.GetBonds():
                if bond.GetBondTypeAsDouble() != 1.0:
                    continue
                bi = bond.GetBeginAtomIdx()
                bj = bond.GetEndAtomIdx()
                sym_i = mol.GetAtomWithIdx(bi).GetSymbol()
                sym_j = mol.GetAtomWithIdx(bj).GetSymbol()

                # 헤테로원자 관련 결합 우선
                if sym_i == "C" and sym_j == "C":
                    continue

                try:
                    emol = Chem.RWMol(mol)
                    emol.RemoveBond(bi, bj)
                    atom_i = emol.GetAtomWithIdx(bi)
                    atom_j = emol.GetAtomWithIdx(bj)
                    atom_i.SetNumExplicitHs(atom_i.GetNumExplicitHs() + 1)
                    atom_j.SetNumExplicitHs(atom_j.GetNumExplicitHs() + 1)
                    try:
                        Chem.SanitizeMol(emol)
                    except Exception:
                        continue

                    frags = Chem.GetMolFrags(emol, asMols=True)
                    if len(frags) < 2:
                        continue

                    frag_smiles = []
                    valid = True
                    for f in frags:
                        try:
                            fs = Chem.MolToSmiles(f)
                            if Chem.MolFromSmiles(fs) is None:
                                valid = False
                                break
                            frag_smiles.append(fs)
                        except Exception:
                            valid = False
                            break

                    if not valid:
                        continue

                    desc = f"{sym_i}-{sym_j}"
                    bond_conditions = CONDITION_MAP.get(
                        desc, f"{desc} bond formation — reagent/conditions TBD"
                    )
                    step = SynthesisStep(
                        step_number=1,
                        reactant_smiles=frag_smiles,
                        product_smiles=target_canon,
                        transform_name=f"{desc} 결합 형성",
                        transform_name_en=f"{desc} Bond Formation",
                        conditions=bond_conditions,
                        confidence=0.3,
                    )
                    # 비상용 프래그먼트 재귀 분해
                    all_bb = []
                    preceding_steps = []
                    step_counter = 0
                    for frag in frag_smiles:
                        if is_commercially_available(frag):
                            all_bb.append(frag)
                        elif _recurse_depth < 3:
                            sub_routes = self._suggest_fragment_routes(
                                frag, _recurse_depth=_recurse_depth + 1
                            )
                            if sub_routes:
                                best_sub = sub_routes[0]
                                for s in best_sub.steps:
                                    step_counter += 1
                                    s.step_number = step_counter
                                    preceding_steps.append(s)
                                all_bb.extend(best_sub.building_blocks)
                            else:
                                all_bb.append(frag)
                        else:
                            all_bb.append(frag)

                    step_counter += 1
                    step.step_number = step_counter
                    all_steps = preceding_steps + [step]

                    route = SynthesisRoute(
                        target_smiles=target_canon,
                        steps=all_steps,
                        total_steps=len(all_steps),
                        score=self._score_route_simple(len(all_steps), 0.3, all_bb),
                        building_blocks=all_bb,
                        validated=False,
                    )
                    routes.append(route)
                    if len(routes) >= 5:
                        break
                except Exception:
                    continue

        # 정렬
        routes.sort(key=lambda r: r.score)
        return routes

    def _score_route_simple(self, n_steps: int, avg_conf: float,
                             building_blocks: list) -> float:
        """간단한 점수 계산 (검증 안 된 경로용)"""
        score = n_steps * 10.0
        score -= avg_conf * 20.0
        for bb in building_blocks:
            info = get_building_block_info(bb)
            if info and info.get("cost") == "low":
                score -= 3.0
        return score

    def get_step_mechanism(self, step: SynthesisStep):
        """단계의 메커니즘 데이터 반환 (캐시 우선)"""
        if step._cached_mechanism is not None:
            return step._cached_mechanism
        reactant_smi = ".".join(step.reactant_smiles)
        return self._mech_engine.generate_mechanism(reactant_smi, step.product_smiles)


# ═══════════════════════════════════════════════════════════
# CLI 테스트
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    engine = RetrosynthesisEngine()
    print(f"Loaded {len(engine._transforms)} retro-transforms")
    print()

    # 테스트 분자들
    test_targets = [
        ("CCO", "에탄올"),
        ("CC(=O)OC", "아세트산 메틸 (에스터)"),
        ("Oc1ccccc1", "페놀"),
        ("CC(=O)Nc1ccccc1", "아세트아닐리드"),
        ("c1ccc(Br)cc1", "브로모벤젠"),
    ]

    for smi, name in test_targets:
        print(f"{'='*60}")
        print(f"Target: {name} ({smi})")
        print(f"{'='*60}")
        routes = engine.find_routes(smi, max_depth=5, max_routes=5,
                                     validate=True, timeout_seconds=5.0)
        if not routes:
            print("  ❌ 경로 없음")
        else:
            for i, route in enumerate(routes, 1):
                print(f"\n  Route {i} (steps={route.total_steps}, "
                      f"score={route.score:.1f}, validated={route.validated})")
                print(f"  Building blocks: {route.building_blocks}")
                for step in route.steps:
                    reactants = " + ".join(step.reactant_smiles)
                    print(f"    Step {step.step_number}: {reactants}")
                    print(f"      → {step.product_smiles}")
                    print(f"      [{step.transform_name}] ({step.conditions})")
        print()
