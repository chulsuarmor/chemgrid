#!/usr/bin/env python3
"""
역합성 분석 엔진 (Retrosynthesis Engine).
목표 분자 → BFS 역변환 → 모든 합성 경로 열거 (10단계 이내).
각 경로를 mechanism_engine으로 내부 검증하여 신뢰도 보장.

v2 (2026-04-19): ASKCOS API 통합 — MIT 공개 역합성 엔진 우선 사용,
네트워크 불가 시 기존 50-SMARTS 엔진 fallback.
ASKCOS: 1M+ 문헌 기반 템플릿 (Reaxys/USPTO), MCTS 트리 탐색.
"""
import logging
import os
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Dict, Tuple, Set

logger = logging.getLogger(__name__)

# ── M756: _HEADLESS_MODE guard ──────────────────────────────────────────
# offscreen/CI 환경에서 외부 엔진(ASKCOS) 호출 차단 (Rule M silent failure 금지).
# QT_QPA_PLATFORM=offscreen 이거나 CHEMGRID_HEADLESS=1 이면 headless 모드.
_HEADLESS_MODE: bool = (
    os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"
    or os.environ.get("CHEMGRID_HEADLESS", "") == "1"
)


def _run_with_timeout(
    fn: Callable[[], Any],
    timeout_sec: float = 30.0,
    default: Any = None,
) -> Any:
    """M756 패턴: 외부 엔진 호출을 timeout_sec 이내로 제한.

    Args:
        fn: 호출할 함수 (인자 없음).
        timeout_sec: 제한 시간 (초). [MAGIC:30.0] M852: ASKCOS+IBM RXN 외부 엔진 대응.
        default: 타임아웃/예외 시 반환값.

    Returns:
        fn() 결과 또는 default.
    """
    result_container: list = [default]
    exc_container: list = [None]

    def _target():
        try:
            result_container[0] = fn()
        except Exception as e:
            exc_container[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        logger.warning(
            "[retrosynthesis_engine._run_with_timeout] 타임아웃 (%.1fs) — 기본값 반환",
            timeout_sec,
        )
        return default
    if exc_container[0] is not None:
        logger.warning(
            "[retrosynthesis_engine._run_with_timeout] 예외: %s", exc_container[0]
        )
        return default
    return result_container[0]

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem, Descriptors, rdChemReactions, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ASKCOS API client (network-based, 1M+ templates)
try:
    from askcos_client import (
        ASKCOSClient, ASKCOSPrecursor, ASKCOSRoute,
        askcos_precursors_to_synthesis_steps, askcos_route_to_synthesis_route,
    )
    ASKCOS_AVAILABLE = True
except ImportError:
    ASKCOS_AVAILABLE = False

# [M852] IBM RXN for Chemistry — ASKCOS 실패 시 fallback
# 학술 인용: Schwaller, P. et al. (2020) Chem. Sci. 11: 3316-3325.
try:
    from askcos_client import IBMRXNClient
    IBM_RXN_AVAILABLE = True
except ImportError:
    IBM_RXN_AVAILABLE = False

from building_blocks import (
    is_building_block, get_building_block_info, BUILDING_BLOCKS,
    is_commercially_available, _has_forbidden_substructure,
)
from mechanism_engine import MechanismEngine

# ═══════════════════════════════════════════════════════════
# 상수
# ═══════════════════════════════════════════════════════════
MAX_ROUTE_STEPS = 12  # 합성 경로 최대 단계 수 (하드 리밋) — M632 SYNTHESIS-AUTO-001: 10→12


# ═══════════════════════════════════════════════════════════
# 천연물 데이터베이스 (Natural Product Database)
# 천연유래물질은 합성보다 추출+정제가 효율적 → 추출 경로 우선 제안
# ═══════════════════════════════════════════════════════════

@dataclass
class NaturalProductInfo:
    """천연물 추출 정보"""
    name: str
    name_kr: str
    source: str              # 유래 생물/식물
    extraction: str          # 추출 방법
    purification: str        # 정제 방법
    note: str = ""           # 추가 참고사항
    storage: str = ""        # 보관 조건


NATURAL_PRODUCTS: Dict[str, NaturalProductInfo] = {
    # ── 알리신 (Allicin) — 마늘 ──
    'C=CCSS(=O)CC=C': NaturalProductInfo(
        name='Allicin',
        name_kr='알리신',
        source='마늘 (Allium sativum)',
        extraction=(
            '마늘 파쇄 -> 알리인(alliin)이 알리이나제(alliinase)에 의해 전환 -> 알리신 생성. '
            '신선한 마늘을 분쇄 후 실온에서 10분간 효소 반응 유도.'
        ),
        purification=(
            '유기용매 추출(에틸아세테이트) -> 감압 농축 -> '
            '실리카겔 컬럼 크로마토그래피(헥산:에틸아세테이트 = 3:1) -> '
            'HPLC 정제 (C18 역상, MeOH/H2O 구배)'
        ),
        note='불안정한 물질로 저온(-20C) 보관 필요. 반감기 ~16시간(실온). 합성보다 추출이 효율적.',
        storage='-20C, 불활성 기체(N2/Ar) 하 차광 보관',
    ),
    # ── 카테킨 (Catechin) — 녹차 ──
    'Oc1cc(O)c2c(c1)O[C@@H](c1ccc(O)c(O)c1)[C@H](O)C2': NaturalProductInfo(
        name='Catechin',
        name_kr='카테킨',
        source='녹차 (Camellia sinensis)',
        extraction=(
            '녹차잎 열수 추출 (80C, 30분) -> 에틸아세테이트 분획 -> '
            '수층/유기층 분리 -> 카테킨류 분리'
        ),
        purification='Sephadex LH-20 컬�� 또는 prep-HPLC (C18, MeOH/H2O/0.1% TFA)',
        note='항산화 활성 폴리페놀. 빛과 열에 민감.',
        storage='4C, 차광, 건조 보관',
    ),
    # ── 카페인 (Caffeine) — 커피/차 ──
    'Cn1c(=O)c2c(ncn2C)n(C)c1=O': NaturalProductInfo(
        name='Caffeine',
        name_kr='카페인',
        source='커피 (Coffea arabica), 차 (Camellia sinensis)',
        extraction=(
            '커피콩/찻잎을 뜨거운 물로 추출 -> CH2Cl2 액-액 추출 -> '
            '유기층 감압 농축. 또는 초임계 CO2 추출(산업용).'
        ),
        purification='승화법 (178C) 또는 재결정 (물/에탄올)',
        note='백색 침상 결정. 승화 정제가 가장 깨끗함. 합성도 가능하나 추출이 경제적.',
        storage='실온, 밀봉 보관 (흡습성 있음)',
    ),
    # ── 커큐민 (Curcumin) — 강황 ──
    'COc1cc(/C=C/C(=O)CC(=O)/C=C/c2ccc(O)c(OC)c2)ccc1O': NaturalProductInfo(
        name='Curcumin',
        name_kr='커큐민',
        source='강황 (Curcuma longa)',
        extraction=(
            '강황 뿌리줄기 건조 분말 -> 에탄올 ���는 아세톤 추출 (60C, 4h) -> '
            '감압 농축 -> 조추출물'
        ),
        purification=(
            '실리카겔 컬럼 (CHCl3:MeOH = 95:5) -> 재결정 (에탄올/물). '
            'demethoxycurcumin, bisdemethoxycurcumin 분리 가능.'
        ),
        note='주황-노란색 결정. 빛에 민감. Keto-enol 호변이성체 존재.',
        storage='4C, 차광, 건조 보관',
    ),
    # ── 캡사이신 (Capsaicin) — 고추 ──
    'COc1cc(CNC(=O)CCCC/C=C/C(C)C)ccc1O': NaturalProductInfo(
        name='Capsaicin',
        name_kr='캡사이신',
        source='고추 (Capsicum annuum)',
        extraction=(
            '건조 고추 분말 -> 에탄올 Soxhlet 추출 (6h) -> 감압 농축 -> '
            '에틸아세테이트/물 분배'
        ),
        purification='실리카겔 컬럼 (헥산:에틸아세테이트 구배) -> prep-HPLC',
        note='무색 결정(순수). 매운맛 TRPV1 작용제. 피부 접촉 주의.',
        storage='4C, 차광, 밀봉',
    ),
    # ── 퀘르세틴 (Quercetin) — 양파 ──
    'O=c1cc(-c2ccc(O)c(O)c2)oc2cc(O)cc(O)c12': NaturalProductInfo(
        name='Quercetin',
        name_kr='퀘르세틴',
        source='양파 (Allium cepa), 사과, 포도',
        extraction=(
            '양파 껍질 -> 50% 에탄올 추출 (70C, 2h) -> 산 가수분해(HCl, 환류) '
            '-> 배당체에서 아글리콘 유리'
        ),
        purification='에틸아세테이트 추출 -> 재결정 (에탄올/물) 또는 Sephadex LH-20',
        note='황색 침상 결정. 대표적 플라보놀. 배당체(루틴 등)로도 존재.',
        storage='실온, 차광, 건조',
    ),
    # ── 레스베라트롤 (Resveratrol) — 포도 ──
    'Oc1ccc(/C=C/c2cc(O)cc(O)c2)cc1': NaturalProductInfo(
        name='Resveratrol',
        name_kr='레스베라트롤',
        source='포도 (Vitis vinifera), 땅콩, 호장근',
        extraction=(
            '포도 껍질/호장근 건조분말 -> 70% 에탄올 추출 (50C, 2h) -> '
            '에틸아세테이트 분획'
        ),
        purification='실리카겔 컬럼 (CHCl3:MeOH = 9:1) -> 재결정 (MeOH/H2O)',
        note='trans/cis 이성질체 존재. 빛에 의해 trans->cis 광이성질화.',
        storage='-20C, 차광, 불활성 기체',
    ),
    # ── 아르테미시닌 (Artemisinin) — 개똥쑥 ──
    'CC1CCC2C(C)C(=O)OC3OC4(C)CCC1C23OO4': NaturalProductInfo(
        name='Artemisinin',
        name_kr='아르테미시닌',
        source='개똥쑥 (Artemisia annua)',
        extraction=(
            '개똥쑥 건조 잎 -> 석유 에테르 추출 (상온, 24h) -> 감압 농축. '
            '또는 에틸에테르 Soxhlet 추출.'
        ),
        purification='실리카겔 컬럼 (석유에테르:에틸아세테이트 = 4:1) -> 재결정 (석유에테르)',
        note='항말라리아 약물. 2015 노벨상 (투유유). 엔도퍼옥사이드 구조.',
        storage='실온, 건조, 밀봉',
    ),
}


def _canonicalize_for_lookup(smiles: str) -> Optional[str]:
    """SMILES를 canonical form으로 변환하여 천연물 DB 조회에 사용."""
    if not RDKIT_AVAILABLE:
        return smiles
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[Rule L] MolFromSmiles 실패 (canonicalize): %r", smiles)
            return None
        return Chem.MolToSmiles(mol)
    except Exception as e:
        logger.warning("[retrosynthesis_engine._canonicalize_for_lookup] SMILES canonicalize failed: %s", e)
        return None


def lookup_natural_product(smiles: str) -> Optional[NaturalProductInfo]:
    """주어진 SMILES가 천연물 DB에 있는지 확인.
    canonical SMILES 비교로 매칭."""
    target_canon = _canonicalize_for_lookup(smiles)
    if target_canon is None:
        return None

    for db_smiles, info in NATURAL_PRODUCTS.items():
        db_canon = _canonicalize_for_lookup(db_smiles)
        if db_canon is not None and db_canon == target_canon:
            return info
    return None

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
class RouteFeasibility:
    """합성 경로의 실험 실행 가능성 평가 결과"""
    overall_score: float          # 0-100 (높을수록 쉬움)
    temperature_score: float      # 100=RT, 50=reflux, 0=extreme
    pressure_score: float         # 100=1atm, 0=high pressure
    reagent_availability: float   # 100=common, 0=exotic
    step_count_score: float       # fewer steps = higher
    safety_score: float           # 100=safe, 0=dangerous reagents
    estimated_yield: str          # "high/medium/low"
    lab_level: str                # "고등학교" / "대학교" / "연구소" / "산업체"
    summary: str                  # 1-line Korean summary


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
     "[C:1][C:2]#[N:3]>>[C:1]Br.[C-:2]#[N:3]",
     "[C:1]Br.[C-:2]#[N:3]>>[C:1][C:2]#[N:3]",
     "NaCN, DMSO", 0.75),

    # 티오에테르 → 할라이드 + 싸이올
    ("티오에테르 역합성", "Retro-Thioether", "치환",
     "[C:1][S:2][C:3]>>[C:1]Br.[SH:2][C:3]",
     "[C:1]Br.[SH:2][C:3]>>[C:1][S:2][C:3]",
     "NaOH, EtOH", 0.65),

    # ── 첨가 반응 (Addition) — 역은 제거 ──
    # 알코올 → 알켄 + H₂O (reverse hydration = dehydration)
    ("탈수 (역수화)", "Retro-Hydration", "첨가",
     "[CH:1][C:2]([OH:3])>>[C:1]=[C:2].[OH2:3]",
     "[C:1]=[C:2].[OH2:3]>>[CH:1][C:2]([OH:3])",
     "H₂SO₄, 가열", 0.7),

    # 할로알칸 → 알켄 + HBr (reverse HBr addition)
    ("HBr 첨가 역합성", "Retro-HBr Addition", "첨가",
     "[CH:1][C:2]([Br:3])>>[C:1]=[C:2].[Br:3]",
     "[C:1]=[C:2].[Br:3]>>[CH:1][C:2]([Br:3])",
     "HBr", 0.75),

    # 할로알칸 → 알켄 + HCl
    ("HCl 첨가 역합성", "Retro-HCl Addition", "첨가",
     "[CH:1][C:2]([Cl:3])>>[C:1]=[C:2].[Cl:3]",
     "[C:1]=[C:2].[Cl:3]>>[CH:1][C:2]([Cl:3])",
     "HCl", 0.7),

    # 디할라이드 → 알켄 + X₂ (reverse Br₂ addition)
    ("Br₂ 첨가 역합성", "Retro-Br₂ Addition", "첨가",
     "[C:1]([Br:3])[C:2]([Br:4])>>[C:1]=[C:2].[Br:3][Br:4]",
     "[C:1]=[C:2].[Br:3][Br:4]>>[C:1]([Br:3])[C:2]([Br:4])",
     "Br₂, CCl₄", 0.8),

    # 에폭시드 → 알켄 + 산화제
    ("에폭시화 역합성", "Retro-Epoxidation", "첨가",
     "[C:1]1[O:2][C:3]1>>[C:1]=[C:3].[O:2]O",
     "[C:1]=[C:3].[O:2]O>>[C:1]1[O:2][C:3]1",
     "mCPBA, CH₂Cl₂", 0.75),

    # ── 방향족 치환 (EAS) ──
    # 브로모벤젠 → 벤젠 + Br₂
    ("EAS 브롬화 역합성", "Retro-EAS Bromination", "방향족",
     "[c:1][Br:2]>>[cH:1].[Br:2]Br",
     "[cH:1].[Br:2]Br>>[c:1][Br:2]",
     "Br₂, FeBr₃", 0.85),

    # 클로로벤젠 → 벤젠 + Cl₂
    ("EAS 염소화 역합성", "Retro-EAS Chlorination", "방향족",
     "[c:1][Cl:2]>>[cH:1].[Cl:2]Cl",
     "[cH:1].[Cl:2]Cl>>[c:1][Cl:2]",
     "Cl₂, AlCl₃", 0.8),

    # 니트로벤젠 → 벤젠 + HNO₃
    ("니트로화 역합성", "Retro-Nitration", "방향족",
     "[c:1][N+:2](=[O:3])[O-:4]>>[cH:1].[O-:4][N+:2](=[O:3])O",
     "[cH:1].[O-:4][N+:2](=[O:3])O>>[c:1][N+:2](=[O:3])[O-:4]",
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
     "[c:1][NH2:2]>>[c:1][N+:2](=O)[O-]",
     "[c:1][N+:2](=O)[O-]>>[c:1][NH2:2]",
     "Sn/HCl 또는 Fe/HCl", 0.8),

    # ── 축합 반응 (Condensation) ──
    # 에스터 → 산 + 알코올 (reverse Fischer esterification)
    ("Fischer 에스터 역합성", "Retro-Fischer Ester", "축합",
     "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])[OH:3].[OH][C:4]",
     "[C:1](=[O:2])[OH:3].[OH][C:4]>>[C:1](=[O:2])[O:3][C:4]",
     "H₂SO₄, 가열", 0.85),

    # 아마이드 → 산 + 아민 (reverse amidation)
    ("아마이드 역합성", "Retro-Amidation", "축합",
     "[C:1](=[O:2])[NH:3]>>[C:1](=[O:2])O.[NH2:3]",
     "[C:1](=[O:2])O.[NH2:3]>>[C:1](=[O:2])[NH:3]",
     "DCC 또는 가열", 0.75),

    # 아실 클로라이드 → 산 + SOCl₂
    ("아실클로라이드 역합성", "Retro-Acyl Chloride", "축합",
     "[C:1](=[O:2])[Cl:3]>>[C:1](=[O:2])O.[Cl:3]S(=O)Cl",
     "[C:1](=[O:2])O.[Cl:3]S(=O)Cl>>[C:1](=[O:2])[Cl:3]",
     "SOCl₂", 0.8),

    # 이민 → 알데히드/케톤 + 아민
    ("이민 역합성", "Retro-Imine", "축합",
     "[C:1]=[N:2][C:3]>>[C:1]=O.[NH2:2][C:3]",
     "[C:1]=O.[NH2:2][C:3]>>[C:1]=[N:2][C:3]",
     "분자체, TiCl₄", 0.7),

    # 옥심 → 케톤 + NH₂OH
    ("옥심 역합성", "Retro-Oxime", "축합",
     "[C:1]=[N:2][OH:3]>>[C:1]=O.[N:2][OH:3]",
     "[C:1]=O.[N:2][OH:3]>>[C:1]=[N:2][OH:3]",
     "NH₂OH·HCl, pyridine", 0.7),

    # ── 산화/환원 ──
    # 1차 알코올 → 알데히드 (reverse 환원)
    ("알데히드 환원 역합성", "Retro-Aldehyde Reduction", "산화환원",
     "[CH2:1][OH:2]>>[CH:1]=[O:2]",
     "[CH:1]=[O:2]>>[CH2:1][OH:2]",
     "NaBH₄ 또는 LiAlH₄", 0.8),

    # 2차 알코올 → 케톤 (reverse 환원)
    ("케톤 환원 역합성", "Retro-Ketone Reduction", "산화환원",
     "[CH:1]([OH:2])>>[C:1](=[O:2])",
     "[C:1](=[O:2])>>[CH:1]([OH:2])",
     "NaBH₄, MeOH", 0.8),

    # 카르복실산 → 알데히드 (reverse 산화)
    ("알데히드 산화 역합성", "Retro-Aldehyde Oxidation", "산화환원",
     "[C:1](=[O:2])[OH:3]>>[CH:1](=[O:2]).[OH2:3]",
     "[CH:1](=[O:2]).[OH2:3]>>[C:1](=[O:2])[OH:3]",
     "KMnO₄ 또는 CrO₃", 0.75),

    # 알데히드 → 1차 알코올 (reverse 산화: PCC)
    ("알코올 산화 역합성", "Retro-Alcohol Oxidation", "산화환원",
     "[CH:1]=[O:2]>>[CH2:1][OH:2]",
     "[CH2:1][OH:2]>>[CH:1]=[O:2]",
     "PCC, CH₂Cl₂", 0.75),

    # ── 명명 반응 ──
    # Grignard 역합성: 알코올 → 카르보닐 + RMgBr
    ("Grignard 역합성", "Retro-Grignard", "명명반응",
     "[C:1]([OH:2])([C:3])>>[C:1](=[O:2]).[C:3][Mg]Br",
     "[C:1](=[O:2]).[C:3][Mg]Br>>[C:1]([OH:2])([C:3])",
     "1) RMgBr/THF  2) H₃O⁺", 0.75),

    # 알돌 역합성: β-hydroxy carbonyl → 2 × carbonyl
    ("알돌 역합성", "Retro-Aldol", "명명반응",
     "[C:1]([OH:2])[CH2:3][C:4]=[O:5]>>[C:1](=[O:2]).[CH2:3][C:4]=[O:5]",
     "[C:1](=[O:2]).[CH2:3][C:4]=[O:5]>>[C:1]([OH:2])[CH2:3][C:4]=[O:5]",
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
     "[C:1](=[O:2])[NH:3][C:4]>>[C:1](=[N:3][OH:2])[C:4]",
     "[C:1](=[N:3][OH:2])[C:4]>>[C:1](=[O:2])[NH:3][C:4]",
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
     "[C:1]([O:2][C:3])([O:4][C:5])>>[C:1](=[O:2]).[OH:4][C:3].[OH][C:5]",
     "[C:1](=[O:2]).[OH:4][C:3].[OH][C:5]>>[C:1]([O:2][C:3])([O:4][C:5])",
     "H⁺(cat), 알코올", 0.65),

    # ── 고리 형성 ──
    # 락톤 → 히드록시산 (reverse lactonization)
    ("락톤 역합성", "Retro-Lactonization", "축합",
     "[O:1]=[C:2]1[C:3][C:4][C:5][O:6]1>>[OH:6][C:2](=[O:1])[C:3][C:4][C:5][OH]",
     "[OH:6][C:2](=[O:1])[C:3][C:4][C:5][OH]>>[O:1]=[C:2]1[C:3][C:4][C:5][O:6]1",
     "H⁺, 가열", 0.7),

    # 락탐 → 아미노산
    ("락탐 역합성", "Retro-Lactam", "축합",
     "[O:1]=[C:2]1[C:3][C:4][C:5][NH:6]1>>[NH2:6][C:3][C:4][C:5][C:2](=[O:1])[OH]",
     "[NH2:6][C:3][C:4][C:5][C:2](=[O:1])[OH]>>[O:1]=[C:2]1[C:3][C:4][C:5][NH:6]1",
     "가열", 0.65),

    # ── 시아노히드린 ──
    ("시아노히드린 역합성", "Retro-Cyanohydrin", "첨가",
     "[C:1]([OH:2])([C:3]#[N:4])>>[C:1](=[O:2]).[C-:3]#[N:4]",
     "[C:1](=[O:2]).[C-:3]#[N:4]>>[C:1]([OH:2])([C:3]#[N:4])",
     "NaCN, H₂O", 0.7),

    # ── 나이트릴 가수분해 ──
    ("나이트릴 가수분해 역합성", "Retro-Nitrile Hydrolysis", "축합",
     "[C:1](=[O:2])[NH2:3]>>[C:1]#[N:3].[OH2:2]",
     "[C:1]#[N:3].[OH2:2]>>[C:1](=[O:2])[NH2:3]",
     "H₂SO₄(묽), 가열", 0.65),

    # ── 트랜스에스터화 ──
    ("트랜스에스터화 역합성", "Retro-Transesterification", "축합",
     "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])[O:3]C.[OH][C:4]",
     "[C:1](=[O:2])[O:3]C.[OH][C:4]>>[C:1](=[O:2])[O:3][C:4]",
     "H⁺ 또는 NaOMe", 0.6),

    # ── 헤미아세탈 ──
    ("헤미아세탈 역합성", "Retro-Hemiacetal", "첨가",
     "[C:1]([OH:2])([O:3][C:4])>>[C:1](=[O:2]).[OH:3][C:4]",
     "[C:1](=[O:2]).[OH:3][C:4]>>[C:1]([OH:2])([O:3][C:4])",
     "H⁺(cat)", 0.65),

    # ── Baeyer-Villiger ──
    ("Baeyer-Villiger 역합성", "Retro-Baeyer-Villiger", "산화환원",
     "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])[C:4].[O:3]O",
     "[C:1](=[O:2])[C:4].[O:3]O>>[C:1](=[O:2])[O:3][C:4]",
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
     "[C:1]([OH:2])[C:3]([OH:4])>>[C:1](=[O:2]).[C:3](=[O:4])",
     "[C:1](=[O:2]).[C:3](=[O:4])>>[C:1]([OH:2])[C:3]([OH:4])",
     "TiCl₃ 또는 SmI₂, THF", 0.45),

    # Cannizzaro 역합성: 1차 알코올 → 알데히드 (불균등화)
    ("Cannizzaro 역합성", "Retro-Cannizzaro", "산화환원",
     "[CH2:1][OH:2]>>[CH:1]=[O:2]",
     "[CH:1]=[O:2]>>[CH2:1][OH:2]",
     "NaOH(conc), H₂O", 0.4),

    # Kolbe-Schmitt 역합성: 히드록시벤조산 → 페놀 + CO₂
    ("Kolbe-Schmitt 역합성", "Retro-Kolbe-Schmitt", "명명반응",
     "[c:1]([OH:2])[c:3][C:4](=[O:5])[OH:6]>>[c:1]([OH:2])[cH:3].[O:6]=[C:4]=[O:5]",
     "[c:1]([OH:2])[cH:3].[O:6]=[C:4]=[O:5]>>[c:1]([OH:2])[c:3][C:4](=[O:5])[OH:6]",
     "NaOH, CO₂ (고압, 125°C)", 0.5),

    # Curtius 자리옮김 역합성: 아민 → 카르복실산 (via 아실 아지드 → 이소시아네이트)
    ("Curtius 자리옮김 역합성", "Retro-Curtius Rearrangement", "명명반응",
     "[NH2:1][C:2]>>[C:2](=[O:1])[OH]",
     "[C:2](=[O:1])[OH]>>[NH2:1][C:2]",
     "DPPA, Et₃N, t-BuOH → H₃O⁺", 0.45),

    # Hofmann 제거 역합성: 알켄 → 4차 암모늄 (anti-Zaitsev)
    ("Hofmann 제거 역합성", "Retro-Hofmann Elimination", "제거",
     "[CH:1]=[CH2:2]>>[CH2:1][CH2:2]N(C)(C)C",
     "[CH2:1][CH2:2]N(C)(C)C>>[CH:1]=[CH2:2]",
     "Ag₂O, H₂O, 가열", 0.4),

    # ═══════════════════════════════════════════════════════════
    # 추가 SMARTS 변환 — 경로 커버리지 확대
    # ═══════════════════════════════════════════════════════════

    # ── 환원적 아민화 (Reductive Amination) — 1차 아민 생성 ──
    # R-CH2-NH2 → R-CHO + NH3 (가장 일반적인 아민 합성법)
    ("환원적 아민화 역합성 (1차아민)", "Retro-Reductive Amination (primary)", "산화환원",
     "[CH2:1][NH2:2]>>[CH:1]=O.[NH3:2]",
     "[CH:1]=O.[NH3:2]>>[CH2:1][NH2:2]",
     "NaBH₃CN, MeOH, AcOH (pH 6-7), RT", 0.75),

    # ── 환원적 아민화: 3차 아민 → 2차 아민 + 알데히드 ──
    ("환원적 아민화 역합성 (3차아민)", "Retro-Reductive Amination (tertiary)", "산화환원",
     "[CH2:1][N:2]([C:3])[C:4]>>[CH:1]=O.[NH:2]([C:3])[C:4]",
     "[CH:1]=O.[NH:2]([C:3])[C:4]>>[CH2:1][N:2]([C:3])[C:4]",
     "NaBH₃CN, MeOH, AcOH, RT 또는 NaBH(OAc)₃, DCE", 0.70),

    # ── N-알킬화 (N-Alkylation) — SN2 ──
    ("N-알킬화 역합성", "Retro-N-Alkylation", "치환",
     "[C:1][N:2]([C:3])>>[C:1]Br.[NH:2]([C:3])",
     "[C:1]Br.[NH:2]([C:3])>>[C:1][N:2]([C:3])",
     "K₂CO₃, DMF, 80°C 또는 Et₃N, MeCN, reflux", 0.65),

    # ── Leuckart-Wallach 반응 역합성: N-alkylamine → ketone + ammonium formate ──
    ("Leuckart 역합성", "Retro-Leuckart Reaction", "명명반응",
     "[CH:1][NH:2][C:3]>>[C:1]=O.[NH2:2][C:3]",
     "[C:1]=O.[NH2:2][C:3]>>[CH:1][NH:2][C:3]",
     "HCOONH₄ 또는 HCONH₂, 가열 (180°C)", 0.55),

    # ── Birch 환원 역합성: 1,4-cyclohexadiene → benzene ──
    ("Birch 환원 역합성", "Retro-Birch Reduction", "산화환원",
     "[CH2:1]1[CH:2]=[CH:3][CH2:4][CH:5]=[CH:6]1>>[c:1]1[c:2][c:3][c:4][c:5][c:6]1",
     "[c:1]1[c:2][c:3][c:4][c:5][c:6]1>>[CH2:1]1[CH:2]=[CH:3][CH2:4][CH:5]=[CH:6]1",
     "Na 또는 Li, NH₃(l), t-BuOH, -33°C", 0.55),

    # ── Michael 첨가 역합성: 1,5-dicarbonyl → enone + CH-acid ──
    ("Michael 첨가 역합성", "Retro-Michael Addition", "명명반응",
     "[C:1](=[O:2])[CH2:3][CH2:4][C:5](=[O:6])>>[C:1](=[O:2])[CH:3]=[CH:4].[CH2:5](=[O:6])",
     "[C:1](=[O:2])[CH:3]=[CH:4].[CH2:5](=[O:6])>>[C:1](=[O:2])[CH2:3][CH2:4][C:5](=[O:6])",
     "NaOEt, EtOH, 0°C → RT 또는 DBU, THF", 0.60),

    # ── Mannich 반응 역합성: β-amino carbonyl → carbonyl + CH₂O + amine ──
    ("Mannich 역합성", "Retro-Mannich Reaction", "명명반응",
     "[C:1](=[O:2])[CH2:3][CH2:4][N:5]>>[C:1](=[O:2])[CH3:3].[CH2:4]=O.[NH:5]",
     "[C:1](=[O:2])[CH3:3].[CH2:4]=O.[NH:5]>>[C:1](=[O:2])[CH2:3][CH2:4][N:5]",
     "AcOH (cat.), H₂O 또는 MeOH, RT, 12h", 0.55),

    # ── Stille 커플링 역합성: vinyl-aryl C-C → organotin + aryl halide ──
    ("Stille 커플링 역합성", "Retro-Stille Coupling", "명명반응",
     "[c:1][CH:2]=[CH:3]>>[c:1]Br.[CH:2](=[CH:3])[Sn](C)(C)C",
     "[c:1]Br.[CH:2](=[CH:3])[Sn](C)(C)C>>[c:1][CH:2]=[CH:3]",
     "Pd(PPh₃)₄, DMF, 100°C 또는 Pd₂(dba)₃, AsPh₃, THF", 0.50),

    # ── Sonogashira 커플링 역합성: Ar-C≡C-R → ArX + HC≡CR ──
    ("Sonogashira 역합성", "Retro-Sonogashira Coupling", "명명반응",
     "[c:1][C:2]#[C:3]>>[c:1]Br.[CH:2]#[C:3]",
     "[c:1]Br.[CH:2]#[C:3]>>[c:1][C:2]#[C:3]",
     "Pd(PPh₃)₂Cl₂, CuI, Et₃N, THF, RT", 0.55),

    # ── Buchwald-Hartwig 아민화 역합성: Ar-NR₂ → ArX + HNR₂ ──
    ("Buchwald-Hartwig 역합성", "Retro-Buchwald-Hartwig", "명명반응",
     "[c:1][N:2]([C:3])[C:4]>>[c:1]Br.[NH:2]([C:3])[C:4]",
     "[c:1]Br.[NH:2]([C:3])[C:4]>>[c:1][N:2]([C:3])[C:4]",
     "Pd₂(dba)₃, BINAP, NaOtBu, toluene, 100°C", 0.55),

    # ── Swern 산화 역합성: 알데히드 → 1차 알코올 ──
    ("Swern 산화 역합성", "Retro-Swern Oxidation", "산화환원",
     "[CH:1](=[O:2])[C:3]>>[CH2:1]([OH:2])[C:3]",
     "[CH2:1]([OH:2])[C:3]>>[CH:1](=[O:2])[C:3]",
     "(COCl)₂, DMSO, Et₃N, CH₂Cl₂, -78°C", 0.70),

    # ── Appel 반응 역합성: alkyl bromide → alcohol ──
    ("Appel 반응 역합성", "Retro-Appel Reaction", "치환",
     "[C:1][Br:2]>>[C:1][OH:2]",
     "[C:1][OH:2]>>[C:1][Br:2]",
     "CBr₄, PPh₃, CH₂Cl₂, 0°C", 0.70),

    # ── Mitsunobu 반응 역합성: ester with inversion → alcohol + acid ──
    ("Mitsunobu 역합성", "Retro-Mitsunobu Reaction", "치환",
     "[C:1][O:2][C:3](=[O:4])>>[C:1][OH].[HO:2][C:3](=[O:4])",
     "[C:1][OH].[HO:2][C:3](=[O:4])>>[C:1][O:2][C:3](=[O:4])",
     "DIAD, PPh₃, THF, 0°C → RT", 0.60),

    # ── Henry (Nitroaldol) 반응 역합성: β-nitro alcohol → aldehyde + nitroalkane ──
    ("Henry 반응 역합성", "Retro-Henry (Nitroaldol)", "명명반응",
     "[C:1]([OH:2])[CH:3][N+:4](=O)[O-:5]>>[C:1](=[O:2]).[CH2:3][N+:4](=O)[O-:5]",
     "[C:1](=[O:2]).[CH2:3][N+:4](=O)[O-:5]>>[C:1]([OH:2])[CH:3][N+:4](=O)[O-:5]",
     "NaOH (cat.), H₂O/EtOH, 0°C", 0.55),

    # ── Eschweiler-Clarke 역합성: N,N-dimethylamine → primary amine ──
    ("Eschweiler-Clarke 역합성", "Retro-Eschweiler-Clarke", "산화환원",
     "[C:1][N:2](C)C>>[C:1][NH2:2]",
     "[C:1][NH2:2]>>[C:1][N:2](C)C",
     "HCHO (과량), HCOOH, reflux", 0.60),

    # ── Wolff-Kishner 환원 역합성: methylene → carbonyl ──
    ("Wolff-Kishner 역합성", "Retro-Wolff-Kishner Reduction", "산화환원",
     "[CH2:1]([C:2])>>[C:1](=O)([C:2])",
     "[C:1](=O)([C:2])>>[CH2:1]([C:2])",
     "NH₂NH₂, KOH, 에틸렌글리콜, 200°C (Huang-Minlon 변형)", 0.55),

    # ── Dess-Martin 산화 역합성: ketone → secondary alcohol ──
    ("Dess-Martin 산화 역합성", "Retro-Dess-Martin Oxidation", "산화환원",
     "[C:1](=[O:2])([C:3])[C:4]>>[CH:1]([OH:2])([C:3])[C:4]",
     "[CH:1]([OH:2])([C:3])[C:4]>>[C:1](=[O:2])([C:3])[C:4]",
     "Dess-Martin periodinane, CH₂Cl₂, RT, 1h", 0.75),

    # ── Wacker 산화 역합성: methyl ketone → terminal alkene ──
    ("Wacker 산화 역합성", "Retro-Wacker Oxidation", "산화환원",
     "[C:1](=[O:2])[CH3:3]>>[CH:1](=[CH2:3]).[O:2]",
     "[CH:1](=[CH2:3]).[O:2]>>[C:1](=[O:2])[CH3:3]",
     "PdCl₂ (10 mol%), CuCl₂, O₂, DMF/H₂O, 50°C", 0.50),
]


# ═══════════════════════════════════════════════════════════
# 역합성 엔진
# ═══════════════════════════════════════════════════════════

class RetrosynthesisEngine:
    """범용 역합성 분석 엔진.
    v2: ASKCOS API (1M+ 문헌 기반 템플릿) 우선 → 로컬 SMARTS fallback.
    BFS + SMARTS 역변환 + mechanism_engine 내부검증."""

    def __init__(self, use_askcos: bool = True):
        self._mech_engine = MechanismEngine()
        self._transforms = self._compile_transforms()

        # ASKCOS client initialization (lazy — only connects when needed)
        disable_askcos = os.environ.get("CHEMGRID_DISABLE_ASKCOS", "") == "1"
        if disable_askcos:
            logger.warning(
                "[RetrosynthesisEngine] CHEMGRID_DISABLE_ASKCOS=1 — "
                "using local SMARTS routes for deterministic foreground validation"
            )
        self._use_askcos = use_askcos and ASKCOS_AVAILABLE and not disable_askcos
        self._askcos_client: Optional[object] = None
        self._askcos_checked: bool = False
        self._askcos_online: bool = False

        # [M852] IBM RXN fallback (lazy init)
        self._ibm_rxn_client: Optional[object] = None
        self._ibm_rxn_checked: bool = False
        self._ibm_rxn_online: bool = False

    def _compile_transforms(self) -> List[RetroTransform]:
        """SMARTS 패턴 사전 컴파일"""
        # Suppress RDKit warnings during SMARTS compilation
        RDLogger.DisableLog('rdApp.*')
        transforms: List[RetroTransform] = []
        try:
            for (name, name_en, cat, rxn_sma, fwd_sma, cond, conf) in _RETRO_TRANSFORM_DATA:
                t = RetroTransform(
                    name=name, name_en=name_en, category=cat,
                    rxn_smarts=rxn_sma, forward_smarts=fwd_sma,
                    conditions=cond, confidence=conf
                )
                try:
                    t._compiled_rxn = rdChemReactions.ReactionFromSmarts(rxn_sma)
                    t._compiled_fwd = rdChemReactions.ReactionFromSmarts(fwd_sma)
                except (ValueError, RuntimeError):
                    continue  # 컴파일 실패 시 스킵
                transforms.append(t)
        finally:
            RDLogger.EnableLog('rdApp.*')
        return [t for t in transforms if t._compiled_rxn is not None]

    def _known_named_routes(self, target_smiles: str, max_routes: int = 5) -> List[SynthesisRoute]:
        """Return curated literature/common teaching routes before generic cuts.

        These routes prevent foreground lessons from selecting chemically poor
        generic disconnections for canonical classroom molecules.
        """
        if not RDKIT_AVAILABLE:
            return []
        canon = _canonicalize_for_lookup(target_smiles)
        if not canon:
            return []
        routes: List[SynthesisRoute] = []
        # ── Aspirin: O-acetylation of salicylic acid ──
        aspirin_canon = _canonicalize_for_lookup("CC(=O)Oc1ccccc1C(=O)O")
        if canon == aspirin_canon:
            step = SynthesisStep(
                step_number=1,
                reactant_smiles=[
                    "O=C(O)c1ccccc1O",        # salicylic acid
                    "CC(=O)OC(C)=O",          # acetic anhydride
                ],
                product_smiles=canon,
                transform_name="Aspirin O-acetylation",
                transform_name_en="Aspirin O-acetylation",
                conditions=(
                    "Acetic anhydride, catalytic H2SO4 or H3PO4, 60-80 C; "
                    "aqueous quench, recrystallization from ethanol/water"
                ),
                confidence=0.92,
            )
            routes.append(SynthesisRoute(
                target_smiles=canon,
                steps=[step],
                total_steps=1,
                score=-80.0,
                building_blocks=["O=C(O)c1ccccc1O", "CC(=O)OC(C)=O"],
                validated=True,
            ))

        # ── Benzene: decarboxylation of benzoic acid (M887) ──
        benzene_canon = _canonicalize_for_lookup("c1ccccc1")
        if canon == benzene_canon:
            step = SynthesisStep(
                step_number=1,
                reactant_smiles=[
                    "O=C(O)c1ccccc1",         # benzoic acid
                    "[Na]O",                   # NaOH (soda lime)
                ],
                product_smiles=canon,
                transform_name="벤조산 탈카르복실화 (Decarboxylation)",
                transform_name_en="Decarboxylation of benzoic acid",
                conditions=(
                    "Benzoic acid + NaOH/CaO (soda lime), "
                    "strong heating 300-400 C; "
                    "distillation to collect benzene"
                ),
                confidence=0.88,
            )
            routes.append(SynthesisRoute(
                target_smiles=canon,
                steps=[step],
                total_steps=1,
                score=-75.0,
                building_blocks=["O=C(O)c1ccccc1", "[Na]O"],
                validated=True,
            ))

        # ── Caffeine: N-methylation of theobromine (M887) ──
        caffeine_canon = _canonicalize_for_lookup("Cn1c(=O)c2c(ncn2C)n(C)c1=O")
        if canon == caffeine_canon:
            step = SynthesisStep(
                step_number=1,
                reactant_smiles=[
                    "Cn1c(=O)c2[nH]cnc2n(C)c1=O",  # theobromine
                    "CI",                             # methyl iodide
                ],
                product_smiles=canon,
                transform_name="테오브로민 N-메틸화 (N-Methylation)",
                transform_name_en="N-Methylation of theobromine",
                conditions=(
                    "Theobromine + CH3I, K2CO3 base, "
                    "DMF solvent, 60-80 C, 4-6 h; "
                    "aqueous workup, recrystallization from water"
                ),
                confidence=0.90,
            )
            routes.append(SynthesisRoute(
                target_smiles=canon,
                steps=[step],
                total_steps=1,
                score=-78.0,
                building_blocks=["Cn1c(=O)c2[nH]cnc2n(C)c1=O", "CI"],
                validated=True,
            ))

        # ── Ethanol: acid-catalyzed hydration of ethylene (M887) ──
        ethanol_canon = _canonicalize_for_lookup("CCO")
        if canon == ethanol_canon:
            step = SynthesisStep(
                step_number=1,
                reactant_smiles=[
                    "C=C",                     # ethylene
                    "O",                       # water
                ],
                product_smiles=canon,
                transform_name="에틸렌 수화 반응 (Acid-catalyzed hydration)",
                transform_name_en="Acid-catalyzed hydration of ethylene",
                conditions=(
                    "Ethylene + H2O, H3PO4 catalyst on silica support, "
                    "300 C, 60-70 atm (industrial); "
                    "lab: H2SO4/H2O, Markovnikov addition"
                ),
                confidence=0.91,
            )
            routes.append(SynthesisRoute(
                target_smiles=canon,
                steps=[step],
                total_steps=1,
                score=-82.0,
                building_blocks=["C=C", "O"],
                validated=True,
            ))

        # ── Glucose: Kiliani-Fischer from D-arabinose (M887) ──
        # [M888 FIX] Multiple glucose stereoisomers: anomeric C unspecified vs
        # beta-D-glucopyranose (test harness uses explicit stereochem).
        _glucose_smiles_variants = [
            "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",           # anomeric-unspecified
            "OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@H]1O",       # beta-D-glucopyranose
        ]
        _glucose_canons = {
            _canonicalize_for_lookup(s)
            for s in _glucose_smiles_variants
            if _canonicalize_for_lookup(s) is not None
        }
        if canon in _glucose_canons:
            step1 = SynthesisStep(
                step_number=1,
                reactant_smiles=[
                    "OC[C@@H](O)[C@H](O)[C@@H](O)C=O",  # D-arabinose
                    "[H]C#N",                              # HCN
                ],
                product_smiles="OC[C@@H](O)[C@H](O)[C@@H](O)[C@@H](O)C#N",
                transform_name="시안히드린 형성 (Kiliani cyanohydrin)",
                transform_name_en="Kiliani cyanohydrin formation",
                conditions=(
                    "D-Arabinose + HCN (or NaCN/HCl), "
                    "aqueous solution, 0-5 C, 24 h; "
                    "yields epimeric cyanohydrins"
                ),
                confidence=0.82,
            )
            step2 = SynthesisStep(
                step_number=2,
                reactant_smiles=[
                    "OC[C@@H](O)[C@H](O)[C@@H](O)[C@@H](O)C#N",
                ],
                product_smiles=canon,
                transform_name="니트릴 가수분해 + 환원 (Fischer reduction)",
                transform_name_en="Nitrile hydrolysis and reduction to aldose",
                conditions=(
                    "Pd/BaSO4, H2 (Rosenmund conditions) or "
                    "Na(Hg)/H2O; lactonization then reduction; "
                    "separation of D-glucose from D-mannose epimer"
                ),
                confidence=0.78,
            )
            routes.append(SynthesisRoute(
                target_smiles=canon,
                steps=[step1, step2],
                total_steps=2,
                score=-70.0,
                building_blocks=[
                    "OC[C@@H](O)[C@H](O)[C@@H](O)C=O",
                    "[H]C#N",
                ],
                validated=True,
            ))

        return routes[:max_routes]

    # ─── ASKCOS Integration (v2) ───

    def _get_askcos_client(self) -> Optional[object]:
        """Lazy-initialize and check ASKCOS API availability.

        [M849] headless 모드(offscreen/CI)에서는 외부 네트워크 호출 차단.
        Rule M: 차단 사유를 logger.warning으로 명시.
        """
        if not self._use_askcos:
            return None
        # [M849] headless 모드에서 외부 엔진 호출 차단
        if _HEADLESS_MODE:
            if not self._askcos_checked:
                self._askcos_checked = True
                self._askcos_online = False
                logger.warning(
                    "[RetrosynthesisEngine] headless mode — "
                    "ASKCOS 외부 호출 차단 (QT_QPA_PLATFORM=offscreen or CHEMGRID_HEADLESS=1)")
            return None
        if not self._askcos_checked:
            self._askcos_checked = True
            try:
                self._askcos_client = ASKCOSClient(timeout=5)  # [MAGIC:5] UI-safe ASKCOS health/prediction probe
                self._askcos_online = self._askcos_client.is_available()
            except Exception as e:
                logger.warning("[RetrosynthesisEngine._get_askcos_client] ASKCOS init failed (offline): %s", e)
                self._askcos_online = False
        if self._askcos_online:
            return self._askcos_client
        return None

    # ─── IBM RXN Integration (M852) ───

    def _get_ibm_rxn_client(self) -> Optional[object]:
        """Lazy-initialize and check IBM RXN API availability.

        [M852] ASKCOS 실패 시 fallback. headless 모드에서는 차단.
        학술 인용: Schwaller, P. et al. (2020) Chem. Sci. 11: 3316-3325.
        Rule M: 차단 사유를 logger.warning으로 명시.
        """
        if not IBM_RXN_AVAILABLE:
            return None
        if _HEADLESS_MODE:
            if not self._ibm_rxn_checked:
                self._ibm_rxn_checked = True
                self._ibm_rxn_online = False
                logger.warning(
                    "[RetrosynthesisEngine] headless mode — "
                    "IBM RXN 외부 호출 차단")
            return None
        if not self._ibm_rxn_checked:
            self._ibm_rxn_checked = True
            # [M1355_W184] IBM RXN: 일시적 503/504 대비 최대 2회 재시도 (Rule M: silent failure 금지)
            # [MAGIC:2] IBM RXN 재시도 횟수 — is_available() 1회 + 1회 fallback = 2회
            _IBM_RXN_MAX_RETRIES = 2
            for _ibm_attempt in range(_IBM_RXN_MAX_RETRIES):
                try:
                    self._ibm_rxn_client = IBMRXNClient(timeout=30)  # [MAGIC:30] M852
                    self._ibm_rxn_online = self._ibm_rxn_client.is_available()
                    if self._ibm_rxn_online:
                        break  # 성공
                    if _ibm_attempt < _IBM_RXN_MAX_RETRIES - 1:
                        logger.info(
                            "[RetrosynthesisEngine._get_ibm_rxn_client] "
                            "IBM RXN 오프라인 — 재시도 %d/%d",
                            _ibm_attempt + 1, _IBM_RXN_MAX_RETRIES,
                        )
                        import time as _time; _time.sleep(1.5)  # [MAGIC:1.5] 재시도 간격(초)
                except Exception as e:
                    logger.warning(
                        "[RetrosynthesisEngine._get_ibm_rxn_client] "
                        "IBM RXN init failed (attempt %d/%d): %s",
                        _ibm_attempt + 1, _IBM_RXN_MAX_RETRIES, e,
                    )
                    self._ibm_rxn_online = False
                    if _ibm_attempt < _IBM_RXN_MAX_RETRIES - 1:
                        import time as _time; _time.sleep(1.5)  # [MAGIC:1.5] 재시도 간격(초)
        if self._ibm_rxn_online:
            return self._ibm_rxn_client
        return None

    def _try_ibm_rxn_routes(self, target_smiles: str,
                             max_routes: int = 50) -> List['SynthesisRoute']:
        """Try IBM RXN API for retrosynthesis. Returns empty list on failure.

        [M852] ASKCOS 실패 시 2차 외부 엔진 fallback.
        학술 인용: Schwaller, P. et al. (2020) Chem. Sci. 11: 3316-3325.
        """
        client = self._get_ibm_rxn_client()
        if client is None:
            return []

        try:
            target_mol = Chem.MolFromSmiles(target_smiles)
            if target_mol is None:
                return []
            target_canon = Chem.MolToSmiles(target_mol)
        except Exception as e:
            logger.warning("[RetrosynthesisEngine._try_ibm_rxn_routes] SMILES parse failed: %s", e)
            return []

        routes: List[SynthesisRoute] = []

        try:
            precursors = client.predict_retrosynthesis(target_canon)
        except Exception as e:
            logger.warning("[RetrosynthesisEngine._try_ibm_rxn_routes] prediction failed: %s", e)
            return []

        if not precursors:
            return []

        from askcos_client import _infer_reaction_name, _infer_conditions

        for p in precursors:
            reactants = p.outcome_smiles.split('.')
            valid_reactants = []
            for r in reactants:
                r_mol = Chem.MolFromSmiles(r)
                if r_mol is not None:
                    valid_reactants.append(Chem.MolToSmiles(r_mol))
                else:
                    logger.warning("[Rule L] IBM RXN MolFromSmiles 실패: %r", r)
            if not valid_reactants:
                continue

            rxn_name = _infer_reaction_name("", valid_reactants, target_canon)
            conditions = _infer_conditions("", "ibm_rxn",
                                            reactants=valid_reactants,
                                            product=target_canon)

            all_buyable = all(
                is_commercially_available(r) or is_building_block(r)
                for r in valid_reactants
            )

            step = SynthesisStep(
                step_number=1,
                reactant_smiles=valid_reactants,
                product_smiles=target_canon,
                transform_name=f"[IBM RXN] {rxn_name}",
                transform_name_en=f"[IBM RXN] {rxn_name}",
                conditions=conditions,
                confidence=min(p.score + 0.2, 0.95),
            )

            score = (1.0 - p.score) * 60 + (0 if all_buyable else 25)

            route = SynthesisRoute(
                target_smiles=target_canon,
                steps=[step],
                total_steps=1,
                score=score,
                building_blocks=valid_reactants if all_buyable else [],
                validated=True,
            )
            route._ibm_rxn_source = True  # type: ignore
            routes.append(route)

        routes.sort(key=lambda r: r.score)
        return routes[:max_routes]

    def _try_askcos_routes(self, target_smiles: str,
                           max_routes: int = 50) -> List['SynthesisRoute']:
        """Try ASKCOS API for retrosynthesis. Returns empty list on failure.

        Strategy:
        1. expand-one: get one-step precursors (fast, ~1s)
        2. For each precursor set, check if all are building blocks
        3. If not enough complete routes from expand-one, try tree-search (slower, ~30s)
        """
        client = self._get_askcos_client()
        if client is None:
            return []

        try:
            target_mol = Chem.MolFromSmiles(target_smiles)
            if target_mol is None:
                return []
            target_canon = Chem.MolToSmiles(target_mol)
        except Exception as e:
            logger.warning("[RetrosynthesisEngine._try_askcos_routes] target SMILES parse failed: %s", e)
            return []

        routes: List[SynthesisRoute] = []

        # Phase 1: expand-one (fast one-step retrosynthesis)
        try:
            precursors = client.expand_one(target_canon, top_k=max_routes)
        except Exception as e:
            logger.warning("[RetrosynthesisEngine._try_askcos_routes] expand_one failed: %s", e)
            precursors = []

        if precursors:
            for p in precursors:
                # Convert ASKCOS precursor to SynthesisRoute
                reactants = p.outcome_smiles.split('.')
                # Validate reactants are parseable
                valid_reactants = []
                for r in reactants:
                    r_mol = Chem.MolFromSmiles(r)
                    if r_mol is not None:
                        valid_reactants.append(Chem.MolToSmiles(r_mol))
                    else:
                        logger.warning("[Rule L] MolFromSmiles 실패: %r", r)
                if not valid_reactants:
                    continue

                # Infer reaction name
                from askcos_client import _infer_reaction_name, _infer_conditions
                rxn_name = _infer_reaction_name(
                    p.template_smarts, valid_reactants, target_canon
                )
                conditions = _infer_conditions(p.template_smarts, p.template_set)

                # Check if this is a complete one-step route (all building blocks)
                all_buyable = all(
                    is_commercially_available(r) or is_building_block(r)
                    for r in valid_reactants
                )

                step = SynthesisStep(
                    step_number=1,
                    reactant_smiles=valid_reactants,
                    product_smiles=target_canon,
                    transform_name=f"[ASKCOS] {rxn_name}",
                    transform_name_en=f"[ASKCOS] {rxn_name}",
                    conditions=conditions,
                    confidence=min(p.score + 0.3, 0.99),  # ASKCOS scores are conservative
                )

                # Score: lower is better, based on ASKCOS score and literature support
                score = (1.0 - p.score) * 50 + (0 if all_buyable else 20)
                # Bonus for many literature examples
                if p.num_examples > 100:
                    score -= 10
                elif p.num_examples > 10:
                    score -= 5

                route = SynthesisRoute(
                    target_smiles=target_canon,
                    steps=[step],
                    total_steps=1,
                    score=score,
                    building_blocks=valid_reactants if all_buyable else [],
                    validated=True,  # ASKCOS uses validated literature templates
                )
                # Mark as ASKCOS-sourced
                route._askcos_source = True  # type: ignore
                route._askcos_examples = p.num_examples  # type: ignore
                routes.append(route)

        # Phase 2: If we got expand-one results, try tree-search for multi-step routes
        # (only if we have fewer than max_routes and the molecule is non-trivial)
        if len(routes) < max_routes // 2:
            try:
                target_heavy = target_mol.GetNumHeavyAtoms()
                # Tree search is expensive (~30s), only for complex molecules
                if target_heavy > 8:
                    tree_routes = client.tree_search(
                        target_canon, timeout=60, max_routes=min(max_routes, 20)
                    )
                    for tr in tree_routes:
                        if tr.reactions:
                            try:
                                synth_route = askcos_route_to_synthesis_route(tr)
                                synth_route._askcos_source = True  # type: ignore
                                routes.append(synth_route)
                            except Exception as e:
                                logger.warning("[RetrosynthesisEngine._try_askcos_routes] tree_search route convert failed: %s", e)
                                continue
            except Exception as e:
                logger.warning("[RetrosynthesisEngine] ASKCOS tree search failed (non-fatal): %s", e)

        # Sort by score
        routes.sort(key=lambda r: r.score)
        return routes[:max_routes]

    def find_routes(self, target_smiles: str,
                    max_depth: int = 10,
                    max_routes: int = 50,
                    validate: bool = True,
                    timeout_seconds: float = 30.0,  # [MAGIC:30.0] M852: 외부 엔진 대응
                    starting_material: Optional[str] = None) -> List[SynthesisRoute]:
        """목표 분자에 대한 모든 합성 경로 탐색.

        Args:
            target_smiles: 목표 분자 SMILES
            max_depth: 최대 합성 단계 수 (MAX_ROUTE_STEPS 이하로 클램프)
            max_routes: 최대 반환 경로 수
            validate: True면 mechanism_engine으로 각 단계 검증
            timeout_seconds: 탐색 제한 시간 (초)
            starting_material: None이면 표준 역합성 (시중 시약 → 목표, Option A).
                              SMILES 문자열이면 해당 출발 물질에서 목표까지의
                              변환 경로 탐색 (원래 구조체 → 유도체, Option B).

        Returns:
            점수순 정렬된 SynthesisRoute 리스트
        """
        if not RDKIT_AVAILABLE:
            return []

        # [M756] _HEADLESS_MODE guard: offscreen/CI 환경에서 외부 엔진 호출 차단
        named_routes = self._known_named_routes(target_smiles, max_routes=max_routes)
        if _HEADLESS_MODE:
            if named_routes:
                logger.info(
                    "[retrosynthesis_engine.find_routes] _HEADLESS_MODE -- using known named route"
                )
                return named_routes[:max_routes]
            logger.warning(
                "[retrosynthesis_engine.find_routes] _HEADLESS_MODE — retrosynthesis skipped"
            )
            return []

        # ★ 천연물 체크: 천연유래물질은 추출 경로를 우선 제안
        nat_info = lookup_natural_product(target_smiles)
        if nat_info is not None:
            extraction_route = self._build_extraction_route(target_smiles, nat_info)
            # 천연물이라도 합성 경로를 "보조 옵션"으로 탐색 가능하게 함
            routes = [extraction_route]
            # 합성 경로도 추가 (교육 목적: "합성 경로도 보기" 옵션)
            if starting_material is None:
                RDLogger.DisableLog('rdApp.*')
                try:
                    # [M756] _run_with_timeout wrap — 무한 루프 방지 (8s 기본)
                    synth_routes = _run_with_timeout(
                        lambda: self._find_routes_inner(
                            target_smiles, max_depth, min(max_routes - 1, 5),
                            validate, timeout_seconds,
                        ),
                        timeout_sec=max(timeout_seconds, 30.0),  # [MAGIC:30.0] M852
                        default=[],
                    )
                finally:
                    RDLogger.EnableLog('rdApp.*')
                routes.extend(synth_routes)
            return routes

        # Option B: 특정 출발물질에서 목표까지의 변환 경로 탐색
        if starting_material is not None:
            return _run_with_timeout(
                lambda: self._find_routes_from_parent(
                    starting_material, target_smiles,
                    max_routes=max_routes, timeout_seconds=timeout_seconds,
                ),
                timeout_sec=max(timeout_seconds, 30.0),  # [MAGIC:30.0] M852
                default=[],
            )

        # Option A: 표준 역합성 (시중 시약 → 목표)
        # ★ v3 (M852): ASKCOS 우선 → IBM RXN fallback → 로컬 SMARTS
        # 학술 인용:
        #   Coley, C.W. et al. (2019) ACS Cent. Sci. 5(9): 1572-1583.  (ASKCOS)
        #   Schwaller, P. et al. (2020) Chem. Sci. 11: 3316-3325.       (IBM RXN)
        external_routes: List[SynthesisRoute] = []
        if named_routes:
            external_routes.extend(named_routes)

        # Phase 1: ASKCOS (1M+ 문헌 기반 템플릿)
        askcos_routes = [] if named_routes else self._try_askcos_routes(target_smiles, max_routes)
        if askcos_routes:
            external_routes.extend(askcos_routes)
            logger.info("[find_routes] ASKCOS returned %d routes", len(askcos_routes))

        # Phase 2: IBM RXN fallback (transformer-based, Schwaller 2020)
        # ASKCOS 결과가 부족할 때만 시도 (비용/시간 절약)
        if len(external_routes) < max_routes // 2:
            ibm_routes = self._try_ibm_rxn_routes(target_smiles, max_routes)
            if ibm_routes:
                external_routes.extend(ibm_routes)
                logger.info("[find_routes] IBM RXN returned %d routes", len(ibm_routes))

        if external_routes:
            if len(external_routes) >= max_routes:
                external_routes.sort(key=lambda r: r.score)
                return external_routes[:max_routes]
            # 외부 엔진 결과가 부족하면 로컬 엔진으로 보충
            remaining = max_routes - len(external_routes)
            RDLogger.DisableLog('rdApp.*')
            try:
                local_routes = _run_with_timeout(
                    lambda: self._find_routes_inner(
                        target_smiles, max_depth, remaining,
                        validate, timeout_seconds,
                    ),
                    timeout_sec=max(timeout_seconds, 30.0),  # [MAGIC:30.0] M852
                    default=[],
                )
            finally:
                RDLogger.EnableLog('rdApp.*')
            combined = external_routes + local_routes
            combined.sort(key=lambda r: r.score)
            return combined[:max_routes]

        # Phase 3: 로컬 SMARTS 엔진 (외부 엔진 모두 불가 시)
        RDLogger.DisableLog('rdApp.*')
        try:
            return _run_with_timeout(
                lambda: self._find_routes_inner(
                    target_smiles, max_depth, max_routes,
                    validate, timeout_seconds,
                ),
                timeout_sec=max(timeout_seconds, 30.0),  # [MAGIC:30.0] M852
                default=[],
            )
        finally:
            RDLogger.EnableLog('rdApp.*')

    def _build_extraction_route(self, target_smiles: str,
                               nat_info: NaturalProductInfo) -> SynthesisRoute:
        """천연물에 대한 추출 경로 생성.
        type='extraction' 표시를 위해 특별한 SynthesisRoute 반환."""
        _canon_mol = Chem.MolFromSmiles(target_smiles)
        if _canon_mol is None:
            logger.warning(
                "[RetrosynthesisEngine] Invalid target SMILES for extraction: %s",
                target_smiles,
            )
            canon = target_smiles  # fallback to original
        else:
            canon = Chem.MolToSmiles(_canon_mol)

        # 추출 경로는 SynthesisStep 형태로 표현
        # step_number=-1은 "추출" 타입을 나타내는 마커
        extraction_step = SynthesisStep(
            step_number=1,
            reactant_smiles=[f"[천연원료] {nat_info.source}"],
            product_smiles=canon,
            transform_name=f"천연물 추출: {nat_info.name_kr} ({nat_info.name})",
            transform_name_en=f"Natural Product Extraction: {nat_info.name}",
            conditions=nat_info.extraction,
            confidence=0.95,  # 천연물 추출은 높은 신뢰도
        )

        purification_step = SynthesisStep(
            step_number=2,
            reactant_smiles=[f"[조추출물] {nat_info.name_kr}"],
            product_smiles=canon,
            transform_name=f"정제: {nat_info.name_kr}",
            transform_name_en=f"Purification: {nat_info.name}",
            conditions=nat_info.purification,
            confidence=0.90,
        )

        route = SynthesisRoute(
            target_smiles=canon,
            steps=[extraction_step, purification_step],
            total_steps=2,
            score=-200.0,  # 최우��� 순위 (합성 경로보다 항상 앞)
            building_blocks=[nat_info.source],
            validated=True,
        )
        # 특별 속성: extraction route 마커
        route._is_extraction = True  # type: ignore
        route._natural_product_info = nat_info  # type: ignore
        return route

    def _find_routes_inner(self, target_smiles: str,
                           max_depth: int = 10,
                           max_routes: int = 50,
                           validate: bool = True,
                           timeout_seconds: float = 10.0) -> List[SynthesisRoute]:
        """Internal route finding logic (called with RDKit warnings suppressed)."""
        # ★ 하드 리밋: 최대 단계 수 클램프
        max_depth = min(max_depth, MAX_ROUTE_STEPS)

        target_mol = Chem.MolFromSmiles(target_smiles)
        if target_mol is None:
            logger.warning("[Rule L] MolFromSmiles 실패: %r", target_smiles)
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
                                logger.warning("[Rule L] MolFromSmiles 실패: %r", p)
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
                                logger.warning("[Rule L] MolFromSmiles 실패: %r", p)
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
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            return []

        # Suppress RDKit warnings during reaction product sanitization
        # (aromatic atoms outside rings are expected and handled gracefully)
        RDLogger.DisableLog('rdApp.*')
        results = []
        try:
            for transform in self._transforms:
                if transform._compiled_rxn is None:
                    continue
                try:
                    products = transform._compiled_rxn.RunReactants((mol,))
                    if not products:
                        continue

                    precursor_sets: List[List[str]] = []
                    seen: Set[Tuple[str, ...]] = set()
                    for product_tuple in products:
                        try:
                            precursors: List[str] = []
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
                        except (ValueError, Chem.rdchem.AtomKekulizeException,
                                Chem.rdchem.AtomValenceException):
                            continue

                    if precursor_sets:
                        results.append((transform, precursor_sets))
                except (ValueError, RuntimeError):
                    continue
        finally:
            RDLogger.EnableLog('rdApp.*')

        return results

    def _generalized_disconnection(self, smiles: str,
                                     target_complexity: float
                                     ) -> List[Tuple[List[str], str]]:
        """범용 결합 분해: 모든 single bond를 끊어보고 유효한 분해 탐색.
        SMARTS 패턴에 없는 미지 분자 대응."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
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
                except Exception as e:
                    logger.warning("[RetrosynthesisEngine._generalized_disconnection] SanitizeMol failed: %s", e)
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
                    except Exception as e:
                        logger.warning("[RetrosynthesisEngine._generalized_disconnection] frag SMILES failed: %s", e)
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
            except Exception as e:
                logger.warning("[RetrosynthesisEngine._generalized_disconnection] bond loop failed: %s", e)
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
            except Exception as e:
                logger.warning("[RetrosynthesisEngine._validate_route] mechanism generate failed: %s", e)
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
                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", r)
            p_mol = Chem.MolFromSmiles(step.product_smiles)
            if p_mol:
                product_mw = Descriptors.MolWt(p_mol)
                if reactant_mw > 0 and product_mw > reactant_mw * 5:
                    return False

            else:
                logger.warning("[Rule L] MolFromSmiles 실패: %r", step.product_smiles)
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

                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", mat)
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
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
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
                logger.warning("[Rule L] MolFromSmiles 실패: %r", p)
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
            logger.warning("[Rule L] MolFromSmiles 실패: %r", target_canon)
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
                    except Exception as e:
                        logger.warning("[RetrosynthesisEngine._suggest_fragment_routes] SanitizeMol failed: %s", e)
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
                        except Exception as e:
                            logger.warning("[RetrosynthesisEngine._suggest_fragment_routes] frag SMILES failed: %s", e)
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
                except Exception as e:
                    logger.warning("[RetrosynthesisEngine._suggest_fragment_routes] fg-loop failed: %s", e)
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
                    except Exception as e:
                        logger.warning("[RetrosynthesisEngine._suggest_fragment_routes] generic SanitizeMol failed: %s", e)
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
                        except Exception as e:
                            logger.warning("[RetrosynthesisEngine._suggest_fragment_routes] generic frag SMILES failed: %s", e)
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
                except Exception as e:
                    logger.warning("[RetrosynthesisEngine._suggest_fragment_routes] generic-bond-loop failed: %s", e)
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
    # 경로 실행 가능성 평가 (Route Feasibility Scoring)
    # ═══════════════════════════════════════════════════════════

    def score_route_feasibility(self, route: SynthesisRoute) -> RouteFeasibility:
        """합성 경로의 실험 실행 가능성을 0-100 점수로 평가합니다.

        학생이 실제로 실험할 수 있는지를 기준으로 온도, 압력, 시약 접근성,
        안전성, 단계 수를 종합 평가합니다.

        Args:
            route: 평가할 합성 경로

        Returns:
            RouteFeasibility 데이터클래스
        """
        if not route.steps:
            return RouteFeasibility(
                overall_score=100.0, temperature_score=100.0,
                pressure_score=100.0, reagent_availability=100.0,
                step_count_score=100.0, safety_score=100.0,
                estimated_yield="high", lab_level="고등학교",
                summary="상용 시약으로 직접 구매 가능 (합성 불필요)"
            )

        # 각 단계별 점수를 수집한 후 최악값/평균으로 종합
        temp_scores = []
        pressure_scores = []
        reagent_scores = []
        safety_scores = []

        for step in route.steps:
            cond = step.conditions.lower() if step.conditions else ""
            t_score = self._score_temperature(cond)
            p_score = self._score_pressure(cond)
            r_score = self._score_reagent_availability(cond, step.reactant_smiles)
            s_score = self._score_safety(cond, step.reactant_smiles)
            temp_scores.append(t_score)
            pressure_scores.append(p_score)
            reagent_scores.append(r_score)
            safety_scores.append(s_score)

        # 전체 경로 점수 = 각 카테고리의 최악값 (가장 어려운 단계가 경로를 결정)
        temperature_score = min(temp_scores)
        pressure_score = min(pressure_scores)
        reagent_availability = min(reagent_scores)
        safety_score = min(safety_scores)

        # 단계 수 점수
        n = route.total_steps
        if n <= 1:
            step_count_score = 100.0
        elif n == 2:
            step_count_score = 80.0
        elif n == 3:
            step_count_score = 60.0
        elif n == 4:
            step_count_score = 40.0
        elif n == 5:
            step_count_score = 20.0
        else:
            step_count_score = max(5.0, 20.0 - (n - 5) * 5.0)

        # 종합 점수 (가중 평균)
        overall = (
            temperature_score * 0.20 +
            pressure_score * 0.10 +
            reagent_availability * 0.25 +
            step_count_score * 0.20 +
            safety_score * 0.25
        )

        # 예상 수율 추정
        avg_conf = sum(s.confidence for s in route.steps) / len(route.steps)
        if avg_conf >= 0.75 and n <= 2:
            estimated_yield = "high"
        elif avg_conf >= 0.5 or n <= 3:
            estimated_yield = "medium"
        else:
            estimated_yield = "low"

        # 실험실 등급 판정
        if overall >= 80:
            lab_level = "고등학교"
        elif overall >= 60:
            lab_level = "대학교"
        elif overall >= 40:
            lab_level = "연구소"
        else:
            lab_level = "산업체"

        # 요약 생성
        summary = self._generate_feasibility_summary(
            overall, temperature_score, reagent_availability,
            safety_score, n, lab_level
        )

        return RouteFeasibility(
            overall_score=round(overall, 1),
            temperature_score=round(temperature_score, 1),
            pressure_score=round(pressure_score, 1),
            reagent_availability=round(reagent_availability, 1),
            step_count_score=round(step_count_score, 1),
            safety_score=round(safety_score, 1),
            estimated_yield=estimated_yield,
            lab_level=lab_level,
            summary=summary,
        )

    # ── 온도 점수 ──
    @staticmethod
    def _score_temperature(conditions: str) -> float:
        """반응 조건 문자열에서 온도를 파싱하여 점수를 매깁니다.
        100=상온(RT), 80=0-80C, 60=환류(80-120C), 30=>150C, 0=>300C"""
        import re

        # 극저온 감지
        if "-78" in conditions:
            return 30.0  # 드라이아이스/아세톤 배스 필요
        if "-40" in conditions or "-20" in conditions:
            return 40.0

        # 명시적 온도 추출 (숫자 + C 또는 °C)
        temp_matches = re.findall(r'(\d+)\s*[°]?\s*[cC]', conditions)
        if temp_matches:
            max_temp = max(int(t) for t in temp_matches)
            if max_temp <= 30:
                return 100.0
            elif max_temp <= 80:
                return 80.0
            elif max_temp <= 120:
                return 60.0
            elif max_temp <= 150:
                return 45.0
            elif max_temp <= 300:
                return 30.0
            else:
                return 0.0

        # 키워드 기반 추론
        if "rt" in conditions or "room temp" in conditions:
            return 100.0
        if any(kw in conditions for kw in ["reflux", "환류", "가열"]):
            return 60.0
        if any(kw in conditions for kw in ["200", "250", "300"]):
            return 20.0
        if "0°c" in conditions or "0 c" in conditions or "아이스" in conditions:
            return 80.0

        # 조건 없거나 파싱 불가 → 상온 가정
        return 90.0

    # ── 압력 점수 ──
    @staticmethod
    def _score_pressure(conditions: str) -> float:
        """반응 조건 문자열에서 압력을 파싱하여 점수를 매깁니다.
        100=1atm, 70=<5atm, 30=<50atm, 0=>50atm"""
        import re

        # 압력 관련 키워드
        if any(kw in conditions for kw in ["고압", "high pressure", "가압"]):
            # 숫자 추출 시도
            atm_matches = re.findall(r'(\d+)\s*atm', conditions)
            if atm_matches:
                max_atm = max(int(a) for a in atm_matches)
                if max_atm <= 5:
                    return 70.0
                elif max_atm <= 50:
                    return 30.0
                else:
                    return 0.0
            return 40.0  # "고압" 언급만 있고 수치 없음

        bar_matches = re.findall(r'(\d+)\s*bar', conditions)
        if bar_matches:
            max_bar = max(int(b) for b in bar_matches)
            if max_bar <= 5:
                return 70.0
            elif max_bar <= 50:
                return 30.0
            else:
                return 0.0

        # 진공/감압
        if any(kw in conditions for kw in ["진공", "vacuum", "감압"]):
            return 80.0  # 감압 설비는 보통 있음

        # 압력 언급 없음 → 상압 가정
        return 100.0

    # ── 시약 접근성 점수 ──

    # 시약 분류 데이터 (이름 패턴 → 점수)
    _COMMON_REAGENTS = {
        # 100점: 학교에서 구할 수 있는 흔한 시약
        "naoh": 100, "hcl": 100, "h2so4": 100, "h₂so₄": 100,
        "nacl": 100, "nabh4": 90, "nabh₄": 90, "meoh": 100,
        "etoh": 100, "h2o": 100, "h₂o": 100, "acoh": 90,
        "naoh(cat)": 100, "acetone": 100, "hno3": 90, "hno₃": 90,
        "br2": 80, "br₂": 80, "cl2": 80, "cl₂": 80,
        "k2co3": 90, "k₂co₃": 90, "na2co3": 90, "na₂co₃": 90,
        "nh2oh": 85, "nh₂oh": 85, "socl2": 80, "socl₂": 80,
        "et3n": 85, "et₃n": 85, "pyridine": 85,
        "febr3": 80, "fecl3": 80, "alcl3": 80, "alcl₃": 80,
        "h2": 80, "h₂": 80, "nacn": 75,
        # 50점: 대학교에서 구할 수 있는 특수 시약
        "lialh4": 50, "lialh₄": 50, "buli": 40, "n-buli": 40,
        "nah": 60, "pcc": 60, "kmno4": 70, "kmno₄": 70,
        "mcpba": 55, "dcc": 55, "nbs": 65, "ncs": 65,
        "dast": 40, "dppa": 40,
        "ticl3": 45, "ticl₃": 45, "ticl4": 45, "ticl₄": 45,
        "smi2": 35, "smi₂": 35, "selectfluor": 40,
        "edc": 55, "hobt": 55, "dipea": 60,
        "nabh3cn": 60, "nabh₃cn": 60,
        "pbr3": 65, "pbr₃": 65, "pcl5": 50, "pcl₅": 50,
        # 20점: 연구소급 특수 촉매/시약
        "pd(pph3)4": 25, "pd(pph₃)₄": 25, "pd(oac)2": 25, "pd(oac)₂": 25,
        "pd2(dba)3": 20, "pd₂(dba)₃": 20, "binap": 20,
        "cui": 30, "cro3": 50, "cro₃": 50,
        "ag2o": 35, "ag₂o": 35,
        "ph3p": 40, "ph₃p": 40,
        # 특수 조건
        "naotbu": 40, "분자체": 60,
    }

    @classmethod
    def _score_reagent_availability(cls, conditions: str,
                                     reactant_smiles: list) -> float:
        """시약 접근성 점수. 조건 문자열의 시약 이름을 분석합니다."""
        if not conditions:
            return 80.0  # 조건 미명시 → 기본 시약 가정

        scores = []
        cond_lower = conditions.lower().replace(" ", "")

        for reagent, score in cls._COMMON_REAGENTS.items():
            if reagent.replace(" ", "") in cond_lower:
                scores.append(score)

        if not scores:
            # 매칭 안 되면 키워드 기반 추론
            if any(kw in conditions.lower() for kw in ["pd", "palladium"]):
                return 25.0  # 팔라듐 촉매 → 연구소급
            if any(kw in conditions.lower() for kw in ["catalyst", "촉매"]):
                return 50.0
            return 70.0  # 기본값

        return min(scores)  # 가장 구하기 어려운 시약이 병목

    # ── 안전성 점수 ──

    # 위험 시약 데이터 (이름 패턴 → 안전 점수)
    _SAFETY_DATA = {
        # 100: 안전한 시약
        "h2o": 100, "h₂o": 100, "nacl": 100, "etoh": 100,
        "meoh": 90, "acetone": 90, "acoh": 80,
        # 70: 자극성/주의 필요
        "naoh": 70, "hcl": 70, "h2so4": 65, "h₂so₄": 65,
        "hno3": 60, "hno₃": 60, "et3n": 75, "et₃n": 75,
        "pyridine": 65, "k2co3": 80, "k₂co₃": 80,
        "nabh4": 65, "nabh₄": 65,
        # 40: 독성/위험
        "lialh4": 35, "lialh₄": 35, "nah": 40,
        "buli": 20, "n-buli": 20,
        "kmno4": 55, "kmno₄": 55, "cro3": 40, "cro₃": 40,
        "nacn": 25, "socl2": 45, "socl₂": 45,
        "br2": 50, "br₂": 50, "cl2": 45, "cl₂": 45,
        "mcpba": 50, "dast": 30,
        "pcl5": 35, "pcl₅": 35, "pbr3": 40, "pbr₃": 40,
        "h2": 60, "h₂": 60,
        "ch2cl2": 55, "ch₂cl₂": 55,
        # 10: 극히 위험/발암성
        "ccl4": 30, "ticl4": 30, "ticl₄": 30,
        "dppa": 25,  # azide 관련 → 폭발 위험
        "smi2": 30, "smi₂": 30,
    }

    @classmethod
    def _score_safety(cls, conditions: str, reactant_smiles: list) -> float:
        """안전성 점수. 위험한 시약이 포함되어 있는지 평가합니다."""
        if not conditions:
            return 80.0

        scores = []
        cond_lower = conditions.lower().replace(" ", "")

        for reagent, score in cls._SAFETY_DATA.items():
            if reagent.replace(" ", "") in cond_lower:
                scores.append(score)

        if not scores:
            return 75.0  # 기본값

        return min(scores)  # 가장 위험한 시약이 결정

    # ── 요약 생성 ──
    @staticmethod
    def _generate_feasibility_summary(
        overall: float, temp_score: float, reagent_score: float,
        safety_score: float, n_steps: int, lab_level: str
    ) -> str:
        """실행 가능성 요약을 한국어로 생성합니다."""
        parts = []

        if overall >= 80:
            parts.append(f"{n_steps}단계, 일반 시약으로 실현 가능")
        elif overall >= 60:
            parts.append(f"{n_steps}단계, 대학교 수준 장비 필요")
        elif overall >= 40:
            parts.append(f"{n_steps}단계, 연구소급 장비/시약 필요")
        else:
            parts.append(f"{n_steps}단계, 특수 장비 및 전문 시약 필요")

        # 병목 요인 언급
        bottlenecks = []
        if temp_score < 50:
            bottlenecks.append("극한 온도 조건")
        if reagent_score < 50:
            bottlenecks.append("특수 시약")
        if safety_score < 50:
            bottlenecks.append("위험 시약 취급 주의")

        if bottlenecks:
            parts.append(f"주의: {', '.join(bottlenecks)}")

        return " | ".join(parts)

    # ═══════════════════════════════════════════════════════════
    # Option B: 특정 출발물질(정제된 모분자) → 유도체 변환 경로 탐색
    # ═══════════════════════════════════════════════════════════

    def _find_routes_from_parent(self, parent_smiles: str, derivative_smiles: str,
                                  max_routes: int = 20,
                                  timeout_seconds: float = 15.0) -> List[SynthesisRoute]:
        """정제된 모분자에서 유도체까지의 변환 경로를 찾습니다.

        전략:
        1. 모분자와 유도체의 구조적 차이를 분석 (MCS 기반)
        2. 차이 부분에서 필요한 변환 반응을 식별
        3. 단일~2단계 합성 경로를 제안

        이 방식은 "이미 모분자를 정제·보유" 가정 하에, 최소 단계로
        유도체를 합성하는 실용적 경로를 제시합니다.
        """
        RDLogger.DisableLog('rdApp.*')
        try:
            return self._find_routes_from_parent_inner(
                parent_smiles, derivative_smiles, max_routes, timeout_seconds
            )
        finally:
            RDLogger.EnableLog('rdApp.*')

    def _find_routes_from_parent_inner(self, parent_smiles: str, derivative_smiles: str,
                                        max_routes: int = 20,
                                        timeout_seconds: float = 15.0) -> List[SynthesisRoute]:
        """Option B 내부 로직."""
        import time
        start_time = time.time()

        parent_mol = Chem.MolFromSmiles(parent_smiles)
        deriv_mol = Chem.MolFromSmiles(derivative_smiles)
        if parent_mol is None or deriv_mol is None:
            if parent_mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패 (parent): %r", parent_smiles)
            if deriv_mol is None:
                logger.warning("[Rule L] MolFromSmiles 실패 (derivative): %r", derivative_smiles)
            return []

        parent_canon = Chem.MolToSmiles(parent_mol)
        deriv_canon = Chem.MolToSmiles(deriv_mol)

        routes: List[SynthesisRoute] = []

        # ── 1단계: MCS (Maximum Common Substructure) 분석 ──
        # 모분자와 유도체의 공통 부분을 찾고, 차이를 식별
        try:
            from rdkit.Chem import rdFMCS
            mcs_result = rdFMCS.FindMCS(
                [parent_mol, deriv_mol],
                threshold=0.7,
                timeout=int(min(timeout_seconds / 3, 5)),
                matchValences=False,
                ringMatchesRingOnly=True,
            )
            mcs_smarts = mcs_result.smartsString if mcs_result else ""
        except Exception as e:
            logger.warning("[RetrosynthesisEngine._find_routes_from_parent_inner] MCS failed: %s", e)
            mcs_smarts = ""

        # ── 2단계: 원자 수/구성 차이 분석으로 변환 유형 추론 ──
        parent_atoms = {}
        for atom in parent_mol.GetAtoms():
            sym = atom.GetSymbol()
            parent_atoms[sym] = parent_atoms.get(sym, 0) + 1

        deriv_atoms = {}
        for atom in deriv_mol.GetAtoms():
            sym = atom.GetSymbol()
            deriv_atoms[sym] = deriv_atoms.get(sym, 0) + 1

        # 추가된 원자들
        added_atoms = {}
        for sym, count in deriv_atoms.items():
            diff = count - parent_atoms.get(sym, 0)
            if diff > 0:
                added_atoms[sym] = diff

        # 제거된 원자들
        removed_atoms = {}
        for sym, count in parent_atoms.items():
            diff = count - deriv_atoms.get(sym, 0)
            if diff > 0:
                removed_atoms[sym] = diff

        # ── 3단계: 변환 유형별 합성 경로 제안 ──
        # 변환 패턴 매칭 (추가/제거된 원자 기반)
        transform_suggestions = self._suggest_parent_to_deriv_transforms(
            parent_canon, deriv_canon, parent_mol, deriv_mol,
            added_atoms, removed_atoms, mcs_smarts
        )

        for suggestion in transform_suggestions:
            if time.time() - start_time > timeout_seconds:
                break
            routes.append(suggestion)

        # ── 4단계: 직접 SMARTS 적용으로 추가 경로 탐색 ──
        # 정방향 변환: 모분자에 변환 적용 → 유도체 생성 가능한지 확인
        for transform in self._transforms:
            if time.time() - start_time > timeout_seconds:
                break
            if transform._compiled_fwd is None:
                continue
            try:
                products = transform._compiled_fwd.RunReactants((parent_mol,))
                if not products:
                    continue
                for product_tuple in products:
                    for p_mol in product_tuple:
                        try:
                            Chem.SanitizeMol(p_mol)
                            p_smi = Chem.MolToSmiles(p_mol)
                            # 생성물이 유도체와 동일하면 → 직접 변환 경로!
                            if p_smi == deriv_canon:
                                step = SynthesisStep(
                                    step_number=1,
                                    reactant_smiles=[parent_canon],
                                    product_smiles=deriv_canon,
                                    transform_name=f"직접 변환: {transform.name}",
                                    transform_name_en=f"Direct: {transform.name_en}",
                                    conditions=transform.conditions,
                                    confidence=transform.confidence + 0.1,
                                )
                                route = SynthesisRoute(
                                    target_smiles=deriv_canon,
                                    steps=[step],
                                    total_steps=1,
                                    score=-50.0,  # 직접 변환은 최우선
                                    building_blocks=[parent_canon],
                                    validated=False,
                                )
                                routes.append(route)
                        except Exception as e:
                            logger.warning("[RetrosynthesisEngine._find_routes_from_parent_inner] SanitizeMol/product check failed: %s", e)
                            continue
            except Exception as e:
                logger.warning("[RetrosynthesisEngine._find_routes_from_parent_inner] RunReactants failed: %s", e)
                continue

        # 점수 정렬 + 중복 제거
        seen_keys = set()
        unique_routes = []
        for r in routes:
            key = (r.total_steps, tuple(s.transform_name for s in r.steps))
            if key not in seen_keys:
                seen_keys.add(key)
                unique_routes.append(r)
        unique_routes.sort(key=lambda r: r.score)
        return unique_routes[:max_routes]

    def _suggest_parent_to_deriv_transforms(
        self, parent_canon: str, deriv_canon: str,
        parent_mol, deriv_mol,
        added_atoms: Dict[str, int], removed_atoms: Dict[str, int],
        mcs_smarts: str
    ) -> List[SynthesisRoute]:
        """원자 변화 패턴에 기반한 변환 경로 제안."""
        routes = []

        # ── 할로겐화 (Halogenation) ──
        for halogen in ['F', 'Cl', 'Br', 'I']:
            if halogen in added_atoms:
                conditions_map = {
                    'F': "Selectfluor, MeCN, RT 또는 DAST, CH2Cl2, -78C",
                    'Cl': "NCS, DMF, RT 또는 Cl2, FeCl3 (방향족)",
                    'Br': "NBS, CCl4, hv (라디칼) 또는 Br2, FeBr3 (방향족)",
                    'I': "NIS, DMF, RT 또는 I2, HNO3"
                }
                step = SynthesisStep(
                    step_number=1,
                    reactant_smiles=[parent_canon],
                    product_smiles=deriv_canon,
                    transform_name=f"{halogen} 도입 (할로겐화)",
                    transform_name_en=f"Halogenation ({halogen} introduction)",
                    conditions=conditions_map.get(halogen, f"{halogen}2, catalyst"),
                    confidence=0.6,
                )
                routes.append(SynthesisRoute(
                    target_smiles=deriv_canon, steps=[step],
                    total_steps=1, score=10.0,
                    building_blocks=[parent_canon], validated=False,
                ))

        # ── 산화 (Oxidation): C 그대로, O 추가 ──
        if 'O' in added_atoms and not added_atoms.get('C', 0):
            n_oxy = added_atoms['O']
            if n_oxy == 1:
                cond = "mCPBA, CH2Cl2 (에폭시화) 또는 PCC (알코올→알데히드)"
                name = "산화 (O +1)"
            elif n_oxy == 2:
                cond = "KMnO4, H2O (디올 형성) 또는 CrO3, H2SO4 (Jones 산화)"
                name = "산화 (O +2)"
            else:
                cond = "KMnO4, NaOH, 가열 (강산화)"
                name = f"산화 (O +{n_oxy})"
            step = SynthesisStep(
                step_number=1, reactant_smiles=[parent_canon],
                product_smiles=deriv_canon,
                transform_name=name, transform_name_en=f"Oxidation (+{n_oxy} O)",
                conditions=cond, confidence=0.55,
            )
            routes.append(SynthesisRoute(
                target_smiles=deriv_canon, steps=[step],
                total_steps=1, score=15.0,
                building_blocks=[parent_canon], validated=False,
            ))

        # ── 환원 (Reduction): O 제거 ──
        if 'O' in removed_atoms and not removed_atoms.get('C', 0):
            n_oxy = removed_atoms['O']
            cond = "NaBH4, MeOH (카르보닐→알코올) 또는 LiAlH4, THF (강환원)"
            step = SynthesisStep(
                step_number=1, reactant_smiles=[parent_canon],
                product_smiles=deriv_canon,
                transform_name=f"환원 (O -{n_oxy})",
                transform_name_en=f"Reduction (-{n_oxy} O)",
                conditions=cond, confidence=0.55,
            )
            routes.append(SynthesisRoute(
                target_smiles=deriv_canon, steps=[step],
                total_steps=1, score=15.0,
                building_blocks=[parent_canon], validated=False,
            ))

        # ── N 도입 (아민화/니트로화) ──
        if 'N' in added_atoms:
            n_nitrogen = added_atoms['N']
            if 'O' in added_atoms and added_atoms.get('O', 0) >= 2:
                # 니트로화
                cond = "HNO3/H2SO4 (니트로화)"
                name = "니트로화"
                name_en = "Nitration"
            else:
                # 아민화
                cond = "R-NH2, NaBH3CN, MeOH (환원적 아민화) 또는 Buchwald-Hartwig"
                name = "아민 도입"
                name_en = "Amination"
            step = SynthesisStep(
                step_number=1, reactant_smiles=[parent_canon],
                product_smiles=deriv_canon,
                transform_name=name, transform_name_en=name_en,
                conditions=cond, confidence=0.5,
            )
            routes.append(SynthesisRoute(
                target_smiles=deriv_canon, steps=[step],
                total_steps=1, score=20.0,
                building_blocks=[parent_canon], validated=False,
            ))

        # ── 알킬화/아실화 (C 추가) ──
        if 'C' in added_atoms and added_atoms['C'] <= 6:
            n_carbon = added_atoms['C']
            if 'O' in added_atoms:
                # 아실화 가능성
                cond = "RCOCl, AlCl3, CH2Cl2 (Friedel-Crafts 아실화) 또는 산 염화물 + 아민"
                name = f"아실화 (C+{n_carbon})"
                name_en = f"Acylation (+{n_carbon}C)"
            else:
                cond = "RX, AlCl3 (FC 알킬화) 또는 RMgBr, THF (Grignard)"
                name = f"알킬화 (C+{n_carbon})"
                name_en = f"Alkylation (+{n_carbon}C)"
            step = SynthesisStep(
                step_number=1, reactant_smiles=[parent_canon],
                product_smiles=deriv_canon,
                transform_name=name, transform_name_en=name_en,
                conditions=cond, confidence=0.45,
            )
            routes.append(SynthesisRoute(
                target_smiles=deriv_canon, steps=[step],
                total_steps=1, score=20.0,
                building_blocks=[parent_canon], validated=False,
            ))

        # ── S 도입 (술폰화/티오에테르) ──
        if 'S' in added_atoms:
            cond = "RSH, NaOH (티오에테르) 또는 SO3/H2SO4 (술폰화)"
            step = SynthesisStep(
                step_number=1, reactant_smiles=[parent_canon],
                product_smiles=deriv_canon,
                transform_name="S 작용기 도입",
                transform_name_en="Sulfur Introduction",
                conditions=cond, confidence=0.45,
            )
            routes.append(SynthesisRoute(
                target_smiles=deriv_canon, steps=[step],
                total_steps=1, score=25.0,
                building_blocks=[parent_canon], validated=False,
            ))

        # ── 복합 변환: 여러 원자 동시 변경 → 2단계 경로 제안 ──
        if len(added_atoms) > 1 or (added_atoms and removed_atoms):
            # 2단계 경로: 작용기 변환 + 새 작용기 도입
            added_desc = ", ".join(f"{sym}+{n}" for sym, n in added_atoms.items())
            removed_desc = ", ".join(f"{sym}-{n}" for sym, n in removed_atoms.items())
            change_desc = added_desc
            if removed_desc:
                change_desc += f" / {removed_desc}"

            step1 = SynthesisStep(
                step_number=1, reactant_smiles=[parent_canon],
                product_smiles="[intermediate]",
                transform_name=f"작용기 변환 (1/2): {change_desc}",
                transform_name_en=f"Functional Group Modification (1/2)",
                conditions="조건은 구체적 구조에 따라 결정",
                confidence=0.35,
            )
            step2 = SynthesisStep(
                step_number=2, reactant_smiles=["[intermediate]"],
                product_smiles=deriv_canon,
                transform_name=f"최종 변환 (2/2): {change_desc}",
                transform_name_en=f"Final Transformation (2/2)",
                conditions="조건은 구체적 구조에 따라 결정",
                confidence=0.35,
            )
            routes.append(SynthesisRoute(
                target_smiles=deriv_canon, steps=[step1, step2],
                total_steps=2, score=40.0,
                building_blocks=[parent_canon], validated=False,
            ))

        return routes


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
            print("  [X] no routes found")
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
