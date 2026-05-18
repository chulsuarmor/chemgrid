# mechanism_engine.py (v1.0 - General-Purpose Reaction Mechanism Engine)
"""
ChemGrid: 범용 반응 메커니즘 생성 엔진
- 하드코딩된 gold standard 메커니즘 우선 반환
- 미등록 반응 → BondChangeDetector + ArrowGenerator로 자동 생성
- ORCA DFT (Tier 1) / Gasteiger (Tier 2) / 전기음성도 (Tier 3) 품질 등급
"""

import logging
import os
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdChemReactions
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from reaction_mechanisms import (
    ArrowData, MechanismStep, MechanismData,
    get_mechanism, MECHANISMS
)
from bond_change_detector import BondChangeDetector, BondChangeResult
from arrow_generator import ArrowGenerator


# ============================================================================
# ORCA Availability Check
# ============================================================================

def _check_orca() -> bool:
    """ORCA 실행파일 존재 여부 확인"""
    try:
        from orca_interface import find_orca_executable
        return find_orca_executable() is not None
    except ImportError:
        return False


# ============================================================================
# REACTION SMARTS TEMPLATES (for product prediction)
# ============================================================================

REACTION_SMARTS: Dict[str, str] = {
    # 기본 치환/제거 반응
    "sn2_halide_oh": "[C:1][F,Cl,Br,I:2].[OH-:3]>>[C:1][OH:3].[F,Cl,Br,I-:2]",
    "sn2_halide_cn": "[C:1][F,Cl,Br,I:2].[C-:3]#[N:4]>>[C:1][C:3]#[N:4].[F,Cl,Br,I-:2]",
    "ester_formation": "[C:1](=[O:2])[OH:3].[OH:4][C:5]>>[C:1](=[O:2])[O:4][C:5].[OH2:3]",
    "amide_formation": "[C:1](=[O:2])[OH:3].[NH2:4][C:5]>>[C:1](=[O:2])[NH:4][C:5].[OH2:3]",

    # 페리고리 반응
    "diels_alder": "[C:1]=[C:2][C:3]=[C:4].[C:5]=[C:6]>>[C:1]1[C:2]=[C:3][C:4][C:6][C:5]1",

    # E2 제거
    "e2_halide_base": "[C:1][C:2]([H:6])[F,Cl,Br,I:3].[OH-:4]>>[C:1]=[C:2].[F,Cl,Br,I-:3].[OH2:4]",

    # Suzuki coupling
    "suzuki_coupling": "[c:1][Cl,Br,I:2].[c:3][B:4]([OH:5])[OH:6]>>[c:1][c:3]",

    # Heck reaction (simplified)
    "heck_reaction": "[c:1][Cl,Br,I:2].[C:3]=[C:4]>>[c:1]/[C:3]=[C:4]",
}


# ============================================================================
# MULTI-STEP DECOMPOSITION HEURISTICS
# ============================================================================

def _get_substitution_degree(mol, atom_idx: int) -> int:
    """탄소의 치환도 (1차/2차/3차/4차)"""
    atom = mol.GetAtomWithIdx(atom_idx)
    if atom.GetAtomicNum() != 6:
        return 0
    carbon_neighbors = sum(1 for n in atom.GetNeighbors() if n.GetAtomicNum() == 6)
    return carbon_neighbors


LEAVING_GROUPS = {9, 17, 35, 53}  # F, Cl, Br, I

# ============================================================================
# TRANSFORM NAME → MECHANISM KEY MAPPING
# Maps retrosynthesis transform names (Korean + English) and condition strings
# to gold-standard mechanism keys in reaction_mechanisms.MECHANISMS.
# ============================================================================

_TRANSFORM_TO_MECHANISM: Dict[str, str] = {
    # --- Korean transform names (from _RETRO_TRANSFORM_DATA) ---
    "sn2": "sn2",
    "sn1": "sn1",
    "e2": "e2",
    "e1": "e1",
    "williamson": "sn2",
    "fischer": "esterification",
    "에스터": "esterification",
    "esterification": "esterification",
    "에스터화": "esterification",
    "아마이드": "amidation",
    "amidation": "amidation",
    "아마이드 역합성": "amidation",
    "eas": "eas",
    "eas 염소화": "eas",
    "eas chlorination": "eas",
    "eas nitration": "eas_nitration",
    "eas sulfonation": "eas_sulfonation",
    "니트로화": "eas_nitration",
    "술폰화": "eas_sulfonation",
    "friedel-crafts": "friedel_crafts_alkylation",
    "fc 알킬화": "friedel_crafts_alkylation",
    "fc alkylation": "friedel_crafts_alkylation",
    "diels-alder": "diels_alder",
    "diels alder": "diels_alder",
    "딜스 알더": "diels_alder",
    "딜스-알더": "diels_alder",
    "beckmann": "beckmann",
    "베크만": "beckmann",
    "curtius": "curtius",
    "쿠르티우스": "curtius",
    "michael": "michael_addition",
    "마이클": "michael_addition",
    "michael addition": "michael_addition",
    "wittig": "wittig",
    "비티히": "wittig",
    "grignard": "grignard",
    "그리냐르": "grignard",
    "suzuki": "suzuki_coupling",
    "스즈키": "suzuki_coupling",
    "suzuki coupling": "suzuki_coupling",
    "heck": "heck_reaction",
    "헥": "heck_reaction",
    "heck reaction": "heck_reaction",
    "cope": "cope_rearrangement",
    "claisen": "claisen_rearrangement",
    "클라이젠": "claisen_rearrangement",
    "ozonolysis": "ozonolysis",
    "오존분해": "ozonolysis",
    "br₂ 첨가": "br2_anti_addition",
    "br2 addition": "br2_anti_addition",
    "acid hydration": "acid_hydration",
    "산촉매 수화": "acid_hydration",
    "탈수": "acid_hydration",
    "hydration": "acid_hydration",
    "radical": "radical_halogenation",
    "라디칼": "radical_halogenation",
    "nbs": "radical_halogenation",
    "tosylation": "tosylation",
    "토실화": "tosylation",
    "oxidation": "oxidation",
    "산화": "oxidation",
    "dess-martin": "dess_martin",
    "swern": "swern_oxidation",
    "swern oxidation": "swern_oxidation",
    "스원 산화": "swern_oxidation",
    "robinson": "robinson_annulation",
    "robinson annulation": "robinson_annulation",
    "로빈슨": "robinson_annulation",
    "로빈슨 환화": "robinson_annulation",
    "favorskii": "favorskii_rearrangement",
    "favorskii rearrangement": "favorskii_rearrangement",
    "파보르스키": "favorskii_rearrangement",
    "파보르스키 자리옮김": "favorskii_rearrangement",
    "reduction": "clemmensen_reduction",
    "환원": "clemmensen_reduction",
    "에폭시화 (친전자)": "electrophilic_addition",
    "epoxidation (ea)": "electrophilic_addition",
    "hbr 첨가": "electrophilic_addition",
    "hcl 첨가": "electrophilic_addition",
    "gabriel": "gabriel",
    "가브리엘": "gabriel",
    "appel": "appel",
    "아펠": "appel",
    "birch": "birch_reduction",
    "버치": "birch_reduction",
    "buchwald": "buchwald_hartwig",
    "부흐발트": "buchwald_hartwig",
    "baeyer-villiger": "baeyer_villiger",
    "바이어-빌리거": "baeyer_villiger",
    "henry": "henry_reaction",
    "헨리": "henry_reaction",
    # 산촉매 에스터 가수분해
    "ester hydrolysis": "acid_ester_hydrolysis",
    "에스터 가수분해": "acid_ester_hydrolysis",
    "acid ester hydrolysis": "acid_ester_hydrolysis",
    "산촉매 가수분해": "acid_ester_hydrolysis",
    "가수분해": "acid_ester_hydrolysis",
    "hydrolysis": "acid_ester_hydrolysis",
    # 알돌 축합
    "aldol": "aldol_condensation",
    "aldol condensation": "aldol_condensation",
    "알돌": "aldol_condensation",
    "알돌 축합": "aldol_condensation",
    "aldol addition": "aldol_condensation",
    # EAS 브롬화 (특이적)
    "eas bromination": "eas_bromination",
    "eas 브롬화": "eas_bromination",
    "bromination": "eas_bromination",
    "브롬화": "eas_bromination",
    # Claisen 축합
    "claisen condensation": "claisen_condensation",
    "claisen 축합": "claisen_condensation",
    "클라이젠 축합": "claisen_condensation",
    # Wolff-Kishner 환원
    "wolff-kishner": "wolff_kishner",
    "wolff kishner": "wolff_kishner",
    "울프-키슈너": "wolff_kishner",
    "울프 키슈너": "wolff_kishner",
    # Pinacol 전위
    "pinacol": "pinacol",
    "pinacol rearrangement": "pinacol",
    "피나콜": "pinacol",
    "피나콜 전위": "pinacol",
    # Hofmann 전위
    "hofmann": "hofmann",
    "hofmann rearrangement": "hofmann",
    "호프만": "hofmann",
    "호프만 전위": "hofmann",
    # Cope 제거
    "cope elimination": "cope_elimination",
    "cope 제거": "cope_elimination",
    "코프": "cope_elimination",
    "코프 제거": "cope_elimination",
    # Baeyer-Villiger 산화 (추가 한국어)
    "baeyer villiger": "baeyer_villiger",
    "바이어 빌리거": "baeyer_villiger",
    # Diels-Alder (추가 한국어)
    "딜스알더": "diels_alder",
    # Grignard (추가 한국어)
    "grignard reaction": "grignard",
    "그리냐르 반응": "grignard",
    # Wittig (추가 한국어)
    "wittig reaction": "wittig",
    "비티히 반응": "wittig",
    # Beckmann (추가 한국어)
    "beckmann rearrangement": "beckmann",
    "베크만 전위": "beckmann",
    # Curtius (추가 한국어)
    "curtius rearrangement": "curtius",
    "커티우스": "curtius",
    "커티우스 전위": "curtius",
    # Epoxide ring opening (산촉매/염기촉매)
    "epoxide opening": "epoxide_acid_opening",
    "에폭시드 개환": "epoxide_acid_opening",
    "에폭시 개환": "epoxide_acid_opening",
    "epoxide acid opening": "epoxide_acid_opening",
    "epoxide base opening": "epoxide_base_opening",
    "에폭시드 염기 개환": "epoxide_base_opening",
    # Cannizzaro 반응
    "cannizzaro": "cannizzaro",
    "칸니자로": "cannizzaro",
    "cannizzaro reaction": "cannizzaro",
    "칸니자로 반응": "cannizzaro",
    "불균등화": "cannizzaro",
    # 알코올 탈수
    "alcohol dehydration": "alcohol_dehydration",
    "알코올 탈수": "alcohol_dehydration",
    "탈수 반응": "alcohol_dehydration",
    "dehydration": "alcohol_dehydration",
    # 할로하이드린 형성
    "halohydrin": "halohydrin_formation",
    "halohydrin formation": "halohydrin_formation",
    "할로하이드린": "halohydrin_formation",
    "할로하이드린 형성": "halohydrin_formation",
    "bromohydrin": "halohydrin_formation",
    "브로모하이드린": "halohydrin_formation",
    # mCPBA 에폭시화
    "epoxidation": "mcpba_epoxidation",
    "mcpba epoxidation": "mcpba_epoxidation",
    "에폭시화": "mcpba_epoxidation",
    "mcpba": "mcpba_epoxidation",
    # Fischer 에스터화
    "fischer esterification": "fischer_esterification",
    "피셔 에스터화": "fischer_esterification",
    "피셔": "fischer_esterification",
    # NaBH4 환원
    "nabh4": "nabh4_reduction",
    "nabh4 reduction": "nabh4_reduction",
    "sodium borohydride": "nabh4_reduction",
    "소듐 보로하이드라이드": "nabh4_reduction",
    "보로하이드라이드 환원": "nabh4_reduction",
    "NaBH4 환원": "nabh4_reduction",
    # LiAlH4 환원
    "lialh4": "lialh4_reduction",
    "lialh4 reduction": "lialh4_reduction",
    "lithium aluminium hydride": "lialh4_reduction",
    "리튬 알루미늄 하이드라이드": "lialh4_reduction",
    "LiAlH4 환원": "lialh4_reduction",
    # 촉매적 수소화
    "catalytic hydrogenation": "catalytic_hydrogenation",
    "수소화": "catalytic_hydrogenation",
    "촉매적 수소화": "catalytic_hydrogenation",
    "hydrogenation": "catalytic_hydrogenation",
    # PCC 산화
    "pcc": "pcc_oxidation",
    "pcc oxidation": "pcc_oxidation",
    "pcc 산화": "pcc_oxidation",
    "pyridinium chlorochromate": "pcc_oxidation",
    # Williamson 에테르 합성
    "williamson ether": "williamson_ether",
    "williamson ether synthesis": "williamson_ether",
    "윌리엄슨": "williamson_ether",
    "윌리엄슨 에테르": "williamson_ether",
    "에테르 합성": "williamson_ether",
    # 아세탈 형성
    "acetal": "acetal_formation",
    "acetal formation": "acetal_formation",
    "acetal protection": "acetal_formation",
    "아세탈": "acetal_formation",
    "아세탈 형성": "acetal_formation",
    "아세탈 보호": "acetal_formation",
    "카르보닐 보호": "acetal_formation",
    # 이민 형성 (Schiff 염기)
    "imine": "imine_formation",
    "imine formation": "imine_formation",
    "schiff base": "imine_formation",
    "이민": "imine_formation",
    "이민 형성": "imine_formation",
    "쉬프 염기": "imine_formation",
    # 엔아민 형성 (Stork)
    "enamine": "enamine_formation",
    "enamine formation": "enamine_formation",
    "stork enamine": "enamine_formation",
    "stork": "enamine_formation",
    "엔아민": "enamine_formation",
    "에나민": "enamine_formation",
    "엔아민 형성": "enamine_formation",
    "스토크": "enamine_formation",
    "스토크 에나민": "enamine_formation",
    # Hell-Volhard-Zelinsky
    "hvz": "hell_volhard_zelinsky",
    "hell-volhard-zelinsky": "hell_volhard_zelinsky",
    "hell volhard zelinsky": "hell_volhard_zelinsky",
    "헬-볼하르트-젤린스키": "hell_volhard_zelinsky",
    "alpha halogenation": "hell_volhard_zelinsky",
    "알파 할로겐화": "hell_volhard_zelinsky",
    # 말론산 에스터 합성
    "malonic ester": "malonic_ester_synthesis",
    "malonic ester synthesis": "malonic_ester_synthesis",
    "말론산 에스터": "malonic_ester_synthesis",
    "말론산 에스터 합성": "malonic_ester_synthesis",
    "말론산 합성": "malonic_ester_synthesis",
    # Friedel-Crafts 아실화
    "friedel-crafts acylation": "friedel_crafts_acylation",
    "friedel crafts acylation": "friedel_crafts_acylation",
    "fc acylation": "friedel_crafts_acylation",
    "fc 아실화": "friedel_crafts_acylation",
    "프리델-크래프츠 아실화": "friedel_crafts_acylation",
    "프리델 크래프츠 아실화": "friedel_crafts_acylation",
    "아실화": "friedel_crafts_acylation",
    # Oxymercuration
    "oxymercuration": "oxymercuration",
    "oxymercuration-demercuration": "oxymercuration",
    "산화수은 수화": "oxymercuration",
    "옥시머큐레이션": "oxymercuration",
    "머큐레이션": "oxymercuration",
    # Anti-Markovnikov 라디칼 HBr
    "anti-markovnikov": "anti_markovnikov_addition",
    "anti markovnikov": "anti_markovnikov_addition",
    "anti-markovnikov addition": "anti_markovnikov_addition",
    "라디칼 hbr": "anti_markovnikov_addition",
    "과산화물 효과": "anti_markovnikov_addition",
    "카라시 효과": "anti_markovnikov_addition",
    "kharasch": "anti_markovnikov_addition",
    # Hofmann 제거 (4차 암모늄)
    "hofmann elimination": "hofmann_elimination",
    "hofmann 제거": "hofmann_elimination",
    "호프만 제거": "hofmann_elimination",
    "호프만 탈리": "hofmann_elimination",
    "4차 암모늄 제거": "hofmann_elimination",
    "exhaustive methylation": "hofmann_elimination",
    # Horner-Wadsworth-Emmons
    "hwe": "horner_wadsworth_emmons",
    "horner-wadsworth-emmons": "horner_wadsworth_emmons",
    "horner wadsworth emmons": "horner_wadsworth_emmons",
    "호너-워즈워스-에몬스": "horner_wadsworth_emmons",
    "호너 워즈워스 에몬스": "horner_wadsworth_emmons",
    # Fischer 인돌 합성
    "fischer indole": "fischer_indole",
    "fischer indole synthesis": "fischer_indole",
    "피셔 인돌": "fischer_indole",
    "피셔 인돌 합성": "fischer_indole",
    # Diazotization
    "diazotization": "diazotization",
    "디아조화": "diazotization",
    "디아조화 반응": "diazotization",
    "디아조늄": "diazotization",
    # Fries 자리옮김
    "fries": "fries_rearrangement",
    "fries rearrangement": "fries_rearrangement",
    "프리스": "fries_rearrangement",
    "프리스 자리옮김": "fries_rearrangement",
    "프리스 전위": "fries_rearrangement",
    # Arndt-Eistert
    "arndt-eistert": "arndt_eistert",
    "arndt eistert": "arndt_eistert",
    "아른트-아이스테르트": "arndt_eistert",
    "아른트 아이스테르트": "arndt_eistert",
    "동족산 합성": "arndt_eistert",
    "homologation": "arndt_eistert",
    # Yamaguchi 에스터화
    "yamaguchi": "yamaguchi_esterification",
    "yamaguchi esterification": "yamaguchi_esterification",
    "야마구치": "yamaguchi_esterification",
    "야마구치 에스터화": "yamaguchi_esterification",
    "매크로락톤화": "yamaguchi_esterification",
    "macrolactonization": "yamaguchi_esterification",
    # Julia 올레핀화
    "julia": "julia_olefination",
    "julia olefination": "julia_olefination",
    "julia-lythgoe": "julia_olefination",
    "줄리아": "julia_olefination",
    "줄리아 올레핀화": "julia_olefination",
    # Pictet-Spengler
    "pictet-spengler": "pictet_spengler",
    "pictet spengler": "pictet_spengler",
    "픽테-스펭글러": "pictet_spengler",
    "픽테 스펭글러": "pictet_spengler",
}

# Condition string → mechanism key (fallback when transform name doesn't match)
_CONDITIONS_TO_MECHANISM: Dict[str, str] = {
    "H₂SO₄, 가열": "esterification",
    "NaOH, H₂O": "sn2",
    "NaOH, EtOH": "sn2",
    "NaH, THF": "sn2",
    "NaCN, DMSO": "sn2",
    "Br₂, FeBr₃": "eas_bromination",
    "Cl₂, AlCl₃": "eas",
    "HNO₃, H₂SO₄": "eas_nitration",
    "AlCl₃, CH₂Cl₂": "friedel_crafts_alkylation",
    "mCPBA, CH₂Cl₂": "electrophilic_addition",
    "HBr": "electrophilic_addition",
    "HCl": "electrophilic_addition",
    "Br₂, CCl₄": "br2_anti_addition",
    "DCC 또는 가열": "amidation",
    "SOCl₂": "amidation",
    "Pd(PPh₃)₄, Na₂CO₃": "suzuki_coupling",
    "Pd(OAc)₂, PPh₃, Et₃N": "heck_reaction",
    "O₃, DMS": "ozonolysis",
    "O₃, Me₂S": "ozonolysis",
    "PPh₃, CBr₄": "appel",
    "Na, NH₃(l)": "birch_reduction",
    "Li, NH₃(l)": "birch_reduction",
    "Pd₂(dba)₃": "buchwald_hartwig",
    "m-CPBA": "baeyer_villiger",
    "Zn(Hg), HCl": "clemmensen_reduction",
    "NH₂NH₂, KOH": "wolff_kishner",
    "(COCl)₂, DMSO, Et₃N": "swern_oxidation",
    "DMSO, (COCl)₂": "swern_oxidation",
    "MVK, KOH": "robinson_annulation",
    "NaOEt, EtOH": "favorskii_rearrangement",
    "NaOMe, MeOH": "favorskii_rearrangement",
    # 산촉매 에스터 가수분해
    "H₂SO₄, H₂O": "acid_ester_hydrolysis",
    "HCl, H₂O": "acid_ester_hydrolysis",
    "H₃O⁺": "acid_ester_hydrolysis",
    # 알돌 축합
    "NaOH, Δ": "aldol_condensation",
    "NaOH, H₂O, Δ": "aldol_condensation",
    "NaOH(cat), H₂O": "aldol_condensation",
    "NaOH(cat), H₂O, Δ": "aldol_condensation",
    "LDA, THF, -78°C": "aldol_condensation",
    # Claisen 축합
    "NaOEt, EtOH, Δ": "claisen_condensation",
    "NaOMe, MeOH, Δ": "claisen_condensation",
    # EAS 브롬화
    "Br₂, AlBr₃": "eas_bromination",
    "Br₂, AlCl₃": "eas_bromination",
    # Wolff-Kishner 환원
    "NH₂NH₂, KOH, Δ": "wolff_kishner",
    "NH₂NH₂, NaOH": "wolff_kishner",
    "NH₂NH₂, KOH, 에틸렌글리콜": "wolff_kishner",
    "N₂H₄, KOH": "wolff_kishner",
    # Pinacol 전위
    "H₂SO₄": "pinacol",
    "H₃PO₄": "pinacol",
    # Hofmann 전위
    "Br₂, NaOH": "hofmann",
    "NaOBr": "hofmann",
    # Cope 제거
    "mCPBA, Δ": "cope_elimination",
    "H₂O₂, Δ": "cope_elimination",
    # Curtius 전위 (아실 아지드 조건)
    "NaN₃, 가열": "curtius",
    "DPPA, Et₃N": "curtius",
    # Beckmann 전위
    "H₂SO₄, Δ": "beckmann",
    "PCl₅": "beckmann",
    # Baeyer-Villiger 산화
    "mCPBA": "baeyer_villiger",
    # Epoxide ring opening — substrate hint variants (English + Korean)
    "H₃O⁺, H₂O (에폭시드)": "epoxide_acid_opening",
    "H₃O⁺, H₂O (epoxide)": "epoxide_acid_opening",
    "H₂SO₄, H₂O (에폭시드)": "epoxide_acid_opening",
    "H₂SO₄, H₂O (epoxide)": "epoxide_acid_opening",
    "NaOH, H₂O (에폭시드)": "epoxide_base_opening",
    "NaOH, H₂O (epoxide)": "epoxide_base_opening",
    "NaOMe, MeOH (에폭시드)": "epoxide_base_opening",
    "NaOMe, MeOH (epoxide)": "epoxide_base_opening",
    # Cannizzaro — substrate hint variants (English + Korean)
    "NaOH, H₂O (알데하이드)": "cannizzaro",
    "NaOH, H₂O (aldehyde)": "cannizzaro",
    "NaOH, H₂O (알데히드)": "cannizzaro",
    "KOH, H₂O (알데하이드)": "cannizzaro",
    "KOH, H₂O (aldehyde)": "cannizzaro",
    "NaOH(conc), H₂O": "cannizzaro",
    "NaOH(conc), H₂O, 가열": "cannizzaro",
    # Alcohol dehydration
    "H₂SO₄, Δ (알코올)": "alcohol_dehydration",
    "H₃PO₄, Δ": "alcohol_dehydration",
    "Al₂O₃, Δ": "alcohol_dehydration",
    # Halohydrin formation
    "Br₂, H₂O": "halohydrin_formation",
    "Cl₂, H₂O": "halohydrin_formation",
    "NBS, H₂O": "halohydrin_formation",
    # mCPBA epoxidation — substrate hint variants
    "mCPBA, CH₂Cl₂ (알켄)": "mcpba_epoxidation",
    "mCPBA, CH₂Cl₂ (alkene)": "mcpba_epoxidation",
    "MMPP": "mcpba_epoxidation",
    # Fischer esterification
    "H₂SO₄, ROH": "fischer_esterification",
    "H⁺, MeOH": "fischer_esterification",
    "H⁺, EtOH": "fischer_esterification",
    "H₂SO₄, MeOH": "fischer_esterification",
    "H₂SO₄, EtOH": "fischer_esterification",
    # NaBH4 환원
    "NaBH₄, MeOH": "nabh4_reduction",
    "NaBH₄, EtOH": "nabh4_reduction",
    "NaBH₄": "nabh4_reduction",
    "NaBH₄, MeOH, 0°C": "nabh4_reduction",
    # LiAlH4 환원
    "LiAlH₄, Et₂O": "lialh4_reduction",
    "LiAlH₄, THF": "lialh4_reduction",
    "LiAlH₄": "lialh4_reduction",
    # 촉매적 수소화
    "H₂, Pd/C": "catalytic_hydrogenation",
    "H₂, Pd": "catalytic_hydrogenation",
    "H₂, Pt": "catalytic_hydrogenation",
    "H₂, PtO₂": "catalytic_hydrogenation",
    "H₂, Ni": "catalytic_hydrogenation",
    "H₂, Pd/C, EtOH": "catalytic_hydrogenation",
    "H₂, Lindlar": "catalytic_hydrogenation",
    # PCC 산화
    "PCC, CH₂Cl₂": "pcc_oxidation",
    "PCC": "pcc_oxidation",
    # Williamson 에테르 합성
    "NaH, R-X": "williamson_ether",
    "NaH, THF, R-X": "williamson_ether",
    # 아세탈 형성
    "R'OH, H⁺": "acetal_formation",
    "HOCH₂CH₂OH, H⁺": "acetal_formation",
    "MeOH, H⁺, Dean-Stark": "acetal_formation",
    "p-TsOH, ROH": "acetal_formation",
    # 이민 형성
    "R'NH₂, H⁺": "imine_formation",
    "RNH₂, pH 4-5": "imine_formation",
    # 엔아민 형성
    "피롤리딘, p-TsOH": "enamine_formation",
    "모르폴린, p-TsOH": "enamine_formation",
    "R₂NH, H⁺, Dean-Stark": "enamine_formation",
    # HVZ 반응
    "Br₂, PBr₃": "hell_volhard_zelinsky",
    "Br₂, P": "hell_volhard_zelinsky",
    "Cl₂, PCl₃": "hell_volhard_zelinsky",
    # 말론산 에스터 합성
    "NaOEt, EtOH, R-X": "malonic_ester_synthesis",
    "CH₂(CO₂Et)₂, NaOEt": "malonic_ester_synthesis",
    # Friedel-Crafts 아실화
    "RCOCl, AlCl₃": "friedel_crafts_acylation",
    "CH₃COCl, AlCl₃": "friedel_crafts_acylation",
    "AlCl₃, RCOCl": "friedel_crafts_acylation",
    "(RCO)₂O, AlCl₃": "friedel_crafts_acylation",
    # Oxymercuration
    "Hg(OAc)₂, H₂O, NaBH₄": "oxymercuration",
    "Hg(OAc)₂, THF/H₂O": "oxymercuration",
    "Hg(OAc)₂, NaBH₄": "oxymercuration",
    # Anti-Markovnikov HBr
    "HBr, ROOR": "anti_markovnikov_addition",
    "HBr, 과산화물": "anti_markovnikov_addition",
    "HBr, hν": "anti_markovnikov_addition",
    # Hofmann 제거
    "CH₃I (과량), Ag₂O, Δ": "hofmann_elimination",
    "Me₃N⁺, OH⁻, Δ": "hofmann_elimination",
    # HWE
    "(EtO)₂P(O)CH₂CO₂Et, NaH": "horner_wadsworth_emmons",
    "NaH, 포스포네이트": "horner_wadsworth_emmons",
    "n-BuLi, 포스포네이트": "horner_wadsworth_emmons",
    # Fischer 인돌
    "PhNHNH₂, H⁺, Δ": "fischer_indole",
    "페닐히드라진, HCl": "fischer_indole",
    "ArNHNH₂, 산촉매": "fischer_indole",
    # Diazotization — with plain "0C" variant for ASCII input
    "NaNO₂, HCl, 0°C": "diazotization",
    "NaNO₂, HCl, 0C": "diazotization",
    "NaNO₂, H₂SO₄, 0°C": "diazotization",
    "NaNO₂, H₂SO₄, 0C": "diazotization",
    "NaNO₂, HBF₄": "diazotization",
    # Fries 자리옮김
    "AlCl₃, Δ (페놀 에스터)": "fries_rearrangement",
    "AlCl₃ (페놀 에스터)": "fries_rearrangement",
    # Arndt-Eistert
    "SOCl₂, CH₂N₂, Ag₂O": "arndt_eistert",
    "CH₂N₂, Ag₂O, H₂O": "arndt_eistert",
    "TMSCHN₂, Ag₂O": "arndt_eistert",
    # Yamaguchi
    "2,4,6-Cl₃C₆H₂COCl, Et₃N, DMAP": "yamaguchi_esterification",
    "Yamaguchi 시약, DMAP": "yamaguchi_esterification",
    # Julia 올레핀화
    "PhSO₂CH₂R, n-BuLi": "julia_olefination",
    "n-BuLi, Na/Hg": "julia_olefination",
    # Pictet-Spengler
    "RCHO, TFA": "pictet_spengler",
    "RCHO, AcOH, Δ": "pictet_spengler",
    # --- Grignard multi-step conditions ---
    "1) RMgBr/THF  2) H₃O⁺": "grignard",
    "1) RMgBr, THF  2) H₃O⁺": "grignard",
    "RMgBr, THF, H₃O⁺": "grignard",
    "RMgBr/THF, H₃O⁺": "grignard",
    # --- Beckmann "or" variant (Korean + English) ---
    "H₂SO₄ 또는 PCl₅": "beckmann",
    "H₂SO₄ or PCl₅": "beckmann",
    # --- E2 with named base ---
    "t-BuOK, E2": "e2",
    "t-BuOK": "e2",
    "KOtBu": "e2",
    "KOtBu, E2": "e2",
    # --- Dilute acid hydrolysis variants ---
    "H₂SO₄(묽), 가열": "acid_ester_hydrolysis",
    "H₂SO₄ (dilute), 가열": "acid_ester_hydrolysis",
    "H₂SO₄ (dilute), heat": "acid_ester_hydrolysis",
    "H₂SO₄(dilute), heat": "acid_ester_hydrolysis",
}

# Pauling electronegativity (주요 원소)
_ELECTRONEG = {
    1: 2.20,   # H
    6: 2.55,   # C
    7: 3.04,   # N
    8: 3.44,   # O
    9: 3.98,   # F
    15: 2.19,  # P
    16: 2.58,  # S
    17: 3.16,  # Cl
    35: 2.96,  # Br
    53: 2.66,  # I
}


def _has_leaving_group(mol, atom_idx: int) -> bool:
    """원자에 이탈기가 연결되어 있는지"""
    # Rule N: 타입 가드
    if mol is None:
        return False
    if not isinstance(atom_idx, int):
        try:
            atom_idx = int(atom_idx)
        except (ValueError, TypeError):
            return False
    if atom_idx < 0 or atom_idx >= mol.GetNumAtoms():
        return False
    atom = mol.GetAtomWithIdx(atom_idx)
    for n in atom.GetNeighbors():
        if n.GetAtomicNum() in LEAVING_GROUPS:
            return True
    return False


# ============================================================================
# UNICODE ↔ ASCII NORMALIZATION FOR CONDITION MATCHING
# Converts Unicode subscripts/superscripts/special chars to ASCII equivalents
# so that both "NaBH₄, MeOH" and "NaBH4, MeOH" match the same key.
# ============================================================================

_UNICODE_TO_ASCII = {
    '\u2080': '0', '\u2081': '1', '\u2082': '2', '\u2083': '3',
    '\u2084': '4', '\u2085': '5', '\u2086': '6', '\u2087': '7',
    '\u2088': '8', '\u2089': '9',  # subscript digits
    '\u2070': '0', '\u00b9': '1', '\u00b2': '2', '\u00b3': '3',
    '\u2074': '4', '\u2075': '5', '\u2076': '6', '\u2077': '7',
    '\u2078': '8', '\u2079': '9',  # superscript digits
    '\u207a': '+', '\u207b': '-',  # superscript +/-
    '\u00b0': '',  # degree sign — strip for matching (0°C → 0C)
    '\u0394': 'delta',  # Greek capital delta (Δ)
    '\u2103': 'C',  # degree Celsius
}


def _normalize_to_ascii(text: str) -> str:
    """Unicode subscript/superscript/special → ASCII 변환.

    예: "NaBH₄, MeOH" → "NaBH4, MeOH"
        "H₂SO₄, Δ" → "H2SO4, delta"
    """
    result = []
    for ch in text:
        if ch in _UNICODE_TO_ASCII:
            result.append(_UNICODE_TO_ASCII[ch])
        else:
            result.append(ch)
    return ''.join(result)


# Pre-build ASCII-normalized lookup table for conditions
# Maps normalized(key) → mechanism_key for O(1) lookup of ASCII inputs
_CONDITIONS_ASCII_NORMALIZED: Dict[str, str] = {
    _normalize_to_ascii(k): v for k, v in _CONDITIONS_TO_MECHANISM.items()
}


# ============================================================================
# MAIN CLASS
# ============================================================================

class MechanismEngine:
    """
    범용 반응 메커니즘 생성 엔진.

    사용법:
        engine = MechanismEngine()
        mech = engine.generate_mechanism("CBr.[OH-]", "CO.[Br-]")
        if mech:
            for step in mech.steps:
                print(step.title, len(step.arrows), "arrows")
    """

    def __init__(self):
        self._detector = BondChangeDetector()
        self._arrow_gen = ArrowGenerator(orca_available=_check_orca())

    @staticmethod
    def _infer_mechanism_type(transform_name: str = "",
                               conditions: str = "") -> str:
        """Transform 이름 또는 조건 문자열에서 mechanism key 추론.

        1차: transform_name의 부분 문자열을 _TRANSFORM_TO_MECHANISM에서 매칭
        2차: conditions를 _CONDITIONS_TO_MECHANISM에서 정확/부분 매칭
        매칭 실패 시 빈 문자열 반환.
        """
        # Rule N: 타입 가드
        if not isinstance(transform_name, str):
            transform_name = str(transform_name) if transform_name is not None else ""
        if not isinstance(conditions, str):
            conditions = str(conditions) if conditions is not None else ""

        # Normalize: lowercase, strip whitespace
        tn_lower = transform_name.lower().strip()
        cond_stripped = conditions.strip()

        # 1차: transform name matching (longest match first for accuracy)
        if tn_lower:
            # Try exact match first
            if tn_lower in _TRANSFORM_TO_MECHANISM:
                return _TRANSFORM_TO_MECHANISM[tn_lower]
            # Try substring matching — check if any key is contained in the name
            best_key = ""
            best_len = 0
            for pattern, mech_key in _TRANSFORM_TO_MECHANISM.items():
                if pattern in tn_lower and len(pattern) > best_len:
                    best_key = mech_key
                    best_len = len(pattern)
            if best_key:
                return best_key

        # 2차: conditions matching
        if cond_stripped:
            # Exact match (Unicode)
            if cond_stripped in _CONDITIONS_TO_MECHANISM:
                return _CONDITIONS_TO_MECHANISM[cond_stripped]

            # Exact match (ASCII-normalized fallback)
            # Handles cases where user/code passes "NaBH4, MeOH" instead of "NaBH₄, MeOH"
            cond_ascii = _normalize_to_ascii(cond_stripped)
            if cond_ascii in _CONDITIONS_ASCII_NORMALIZED:
                return _CONDITIONS_ASCII_NORMALIZED[cond_ascii]

            # Substring match (longest match first for specificity)
            # e.g. "NaOH, H₂O (aldehyde)" must match cannizzaro, not sn2
            best_key = ""
            best_len = 0
            for cond_pattern, mech_key in _CONDITIONS_TO_MECHANISM.items():
                if cond_pattern in cond_stripped and len(cond_pattern) > best_len:
                    best_key = mech_key
                    best_len = len(cond_pattern)
            if best_key:
                return best_key

            # Substring match (ASCII-normalized fallback, longest first)
            best_key = ""
            best_len = 0
            for cond_pattern_ascii, mech_key in _CONDITIONS_ASCII_NORMALIZED.items():
                if cond_pattern_ascii in cond_ascii and len(cond_pattern_ascii) > best_len:
                    best_key = mech_key
                    best_len = len(cond_pattern_ascii)
            if best_key:
                return best_key

        return ""

    def generate_mechanism(self,
                            reactant_smiles: str,
                            product_smiles: str = "",
                            reagent_smiles: str = "",
                            mechanism_type_hint: str = "",
                            transform_name: str = "",
                            conditions: str = "") -> Optional[MechanismData]:
        """
        반응 메커니즘 생성 (메인 진입점).

        Args:
            reactant_smiles: 반응물 SMILES (multi-fragment OK)
            product_smiles: 생성물 SMILES (빈 문자열이면 예측 시도)
            reagent_smiles: 시약 SMILES (옵션)
            mechanism_type_hint: 메커니즘 유형 힌트 (e.g. "sn2")
            transform_name: 역합성 변환 이름 (e.g. "Fischer 에스터 역합성")
            conditions: 반응 조건 문자열 (e.g. "H₂SO₄, 가열")

        Returns:
            MechanismData or None
        """
        # Rule N: 외부 입력 타입 가드 — str 아닌 값이 올 수 있음
        if not isinstance(reactant_smiles, str):
            logger.warning("reactant_smiles is not str: %s (%s)",
                           reactant_smiles, type(reactant_smiles).__name__)
            reactant_smiles = str(reactant_smiles) if reactant_smiles is not None else ""
        if not isinstance(product_smiles, str):
            logger.warning("product_smiles is not str: %s (%s)",
                           product_smiles, type(product_smiles).__name__)
            product_smiles = str(product_smiles) if product_smiles is not None else ""
        if not isinstance(reagent_smiles, str):
            logger.warning("reagent_smiles is not str: %s (%s)",
                           reagent_smiles, type(reagent_smiles).__name__)
            reagent_smiles = str(reagent_smiles) if reagent_smiles is not None else ""
        if not isinstance(mechanism_type_hint, str):
            logger.warning("mechanism_type_hint is not str: %s (%s)",
                           mechanism_type_hint, type(mechanism_type_hint).__name__)
            mechanism_type_hint = str(mechanism_type_hint) if mechanism_type_hint is not None else ""
        if not isinstance(transform_name, str):
            logger.warning("transform_name is not str: %s (%s)",
                           transform_name, type(transform_name).__name__)
            transform_name = str(transform_name) if transform_name is not None else ""
        if not isinstance(conditions, str):
            logger.warning("conditions is not str: %s (%s)",
                           conditions, type(conditions).__name__)
            conditions = str(conditions) if conditions is not None else ""

        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available - MechanismEngine disabled")
            return None

        # ─── 1. 하드코딩 gold standard 확인 ───
        # [M157 FIX] 반드시 deepcopy 후 반환 — 원본 MECHANISMS 딕셔너리 변경 방지.
        # generate_intermolecular_mechanism이 step.arrows를 in-place 수정하므로,
        # 공유 참조를 그대로 반환하면 다음 호출 시 인덱스가 이중 재매핑되어 오역됨.
        import copy as _copy

        # M433 DEFECT-2: 페리사이클릭 우선 가드
        # 페리사이클릭/협동 반응(Diels-Alder, 1,3-쌍극자 등)은
        # 친전자/친핵 분류 로직을 타면 잘못된 단계 분해가 일어남.
        # gold standard 탐색 전에 먼저 페리사이클릭 여부를 판별한다.
        # 규칙: pericyclic hint → gold standard → 없으면 'pericyclic' 태그 유지하여 단계 분해 비활성
        _PERICYCLIC_HINTS = {
            "pericyclic", "concerted", "diels_alder", "diels-alder",
            "cycloaddition_2_2", "cope_rearrangement", "claisen_rearrangement",
            "ene_reaction", "sigmatropic", "1,3-dipolar", "1,3_dipolar",
        }
        _effective_type = mechanism_type_hint.lower().replace(" ", "_") if mechanism_type_hint else ""
        _is_pericyclic_hint = _effective_type in _PERICYCLIC_HINTS

        # 1a. 명시적 hint가 있으면 직접 조회
        if mechanism_type_hint:
            hardcoded = get_mechanism(mechanism_type_hint)
            if hardcoded:
                logger.info(f"Gold standard 메커니즘 반환: {mechanism_type_hint}")
                return _copy.deepcopy(hardcoded)

        # 1b. hint가 없으면 transform_name/conditions에서 추론
        if not mechanism_type_hint:
            inferred = self._infer_mechanism_type(transform_name, conditions)
            # M433 DEFECT-2: 추론된 키도 페리사이클릭 여부 갱신
            if inferred and inferred in _PERICYCLIC_HINTS:
                _is_pericyclic_hint = True
            if inferred:
                hardcoded = get_mechanism(inferred)
                if hardcoded:
                    logger.info(f"Gold standard 메커니즘 추론 반환: "
                                f"{inferred} (from transform='{transform_name}', "
                                f"conditions='{conditions}')")
                    return _copy.deepcopy(hardcoded)

        # ─── 2. 생성물 예측 (필요 시) ───
        if not product_smiles:
            product_smiles = self._predict_product(reactant_smiles, reagent_smiles)
            if not product_smiles:
                logger.warning("생성물 예측 실패")
                return None

        # ─── 3. 결합 변화 탐지 ───
        result = self._detector.detect(reactant_smiles, product_smiles)
        if result is None or not result.bond_changes:
            logger.warning("결합 변화 감지 실패 또는 변화 없음 — DFT 폴백 시도")

            # ─── 3b. DFT Quantum Chemistry Fallback (expensive but rigorous) ───
            # When the rule engine cannot determine bond changes, fall back to
            # actual quantum mechanical calculation via ORCA DFT.
            try:
                from mechanism_dft_engine import MechanismDFTEngine
                dft_engine = MechanismDFTEngine()
                if dft_engine.is_available:
                    dft_result = dft_engine.generate(
                        reactant_smiles, product_smiles, reagent_smiles
                    )
                    if dft_result and dft_result.success and dft_result.mechanism_data:
                        logger.info(
                            f"DFT mechanism generated: "
                            f"{len(dft_result.intermediates)} intermediates, "
                            f"{len(dft_result.transition_states)} TSs"
                        )
                        return dft_result.mechanism_data
            except Exception as e:
                logger.debug(f"DFT engine not available: {e}")

            return None

        # ─── 4. 다단계 분해 여부 결정 ───
        # M433 DEFECT-2: 페리사이클릭 hint일 때 → 단일 단계 협주 반응 강제
        if _is_pericyclic_hint:
            logger.debug("페리사이클릭 hint(%s) → 단일 단계 협주 분해 강제", _effective_type)
            step_groups = [(result.bond_changes, "페리사이클릭 협주 반응: 전자가 고리형 전이 상태를 통해 동시 재배열")]
        else:
            step_groups = self._decompose_into_steps(result)

        # ─── 5. 각 단계별 화살표 생성 ───
        mechanism_steps: List[MechanismStep] = []

        if len(step_groups) == 1:
            # 단일 단계 (동시)
            arrows = self._arrow_gen.generate(result)
            step = MechanismStep(
                step_number=1,
                title=self._generate_step_title(result, arrows),
                description=self._generate_step_description(result, arrows),
                reactant_smiles=reactant_smiles,
                product_smiles=product_smiles,
                arrows=arrows,
                notes=reagent_smiles,
            )
            mechanism_steps.append(step)
        else:
            # 다단계
            for i, (step_changes, step_desc) in enumerate(step_groups):
                step_result = BondChangeResult(
                    mapping=result.mapping,
                    bond_changes=step_changes,
                    charge_changes=[cc for cc in result.charge_changes
                                    if any(cc.atom_idx in (bc.atom_i, bc.atom_j)
                                           for bc in step_changes)],
                    r_mol=result.r_mol,
                    p_mol=result.p_mol,
                )
                arrows = self._arrow_gen.generate(step_result)

                # 중간체 SMILES (근사)
                if i == 0:
                    r_smi = reactant_smiles
                    p_smi = self._estimate_intermediate_smiles(reactant_smiles, step_changes)
                else:
                    r_smi = mechanism_steps[-1].product_smiles if mechanism_steps else reactant_smiles
                    p_smi = product_smiles if i == len(step_groups) - 1 else \
                            self._estimate_intermediate_smiles(r_smi, step_changes)

                step = MechanismStep(
                    step_number=i + 1,
                    title=step_desc,
                    description=self._generate_step_description(step_result, arrows),
                    reactant_smiles=r_smi,
                    product_smiles=p_smi,
                    arrows=arrows,
                    notes=reagent_smiles if i == 0 else "",
                )
                mechanism_steps.append(step)

        # ─── 6. MechanismData 조립 ───
        mech = MechanismData(
            mechanism_type="auto_generated",
            title=self._generate_mechanism_title(reactant_smiles, product_smiles),
            total_steps=len(mechanism_steps),
            steps=mechanism_steps,
            energy_diagram=self._estimate_energy_diagram(mechanism_steps),
            overall_description=self._generate_overall_description(mechanism_steps, reactant_smiles, product_smiles),
        )

        logger.info(
            f"메커니즘 자동 생성 완료: {mech.title}, "
            f"{mech.total_steps}단계, "
            f"총 {sum(len(s.arrows) for s in mech.steps)}개 화살표"
        )
        return mech

    # ────────────────────────────────────────────────────────────────────
    # Intermolecular Mechanism (multi-fragment list → remapped arrows)
    # ────────────────────────────────────────────────────────────────────

    def generate_intermolecular_mechanism(self,
                                          reactant_smiles_list: list,
                                          product_smiles: str,
                                          transform_name: str = "",
                                          conditions: str = "") -> Optional["MechanismData"]:
        """분자간 반응 메커니즘 생성: 반응물 목록 순서를 유지한 채 원자 인덱스 재매핑.

        합성경로 팝업(popup_synthesis.py)의 SynthesisStep.reactant_smiles 목록을
        받아서 결합된 SMILES의 실제 원자 인덱스에 맞게 금 표준 화살표를 재매핑합니다.

        문제:
          금 표준 SN2는 "CBr.[OH-]" 순서의 인덱스(C=0, Br=1, O=2)로 고정.
          그러나 합성 단계의 reactant_smiles = ["[OH-]", "CBr"] 이면
          결합 SMILES "OH].[CBr]" 의 인덱스(O=0, C=1, Br=2)가 달라져 화살표가 오역됨.

        해결:
          1) 실제 combined SMILES(목록 순서)로 mol 생성 → 실제 원자 인덱스 확보
          2) 금 표준 template mol 서브구조 매칭으로 각 원자의 실제 인덱스 계산
          3) ArrowData.from_atom_idx / to_atom_idx 를 실제 인덱스로 교체한 사본 반환

        Args:
            reactant_smiles_list: 반응물 SMILES 목록 (순서 중요)
            product_smiles: 생성물 SMILES
            transform_name: 변환 이름 (금 표준 매칭용)
            conditions: 반응 조건 (금 표준 매칭용)

        Returns:
            MechanismData (인덱스 재매핑 완료) 또는 None
        """
        if not RDKIT_AVAILABLE:
            return None
        # Rule N: 타입 가드
        if not isinstance(reactant_smiles_list, list):
            logger.warning("generate_intermolecular_mechanism: reactant_smiles_list is not list: %s",
                           type(reactant_smiles_list).__name__)
            reactant_smiles_list = [reactant_smiles_list] if reactant_smiles_list else []
        if not isinstance(product_smiles, str):
            product_smiles = str(product_smiles) if product_smiles is not None else ""

        # 유효 SMILES만 필터링 (Rule L)
        valid_smiles = []
        for s in reactant_smiles_list:
            if not s or not isinstance(s, str):
                continue
            mol_check = Chem.MolFromSmiles(s)
            if mol_check is None:
                logger.warning("generate_intermolecular_mechanism: invalid SMILES skipped: %s", s)
                continue
            valid_smiles.append(s)

        if not valid_smiles:
            logger.warning("generate_intermolecular_mechanism: no valid reactant SMILES")
            return None

        # 목록 순서대로 결합 SMILES 구성
        combined_smi = ".".join(valid_smiles)

        # 기본 메커니즘 생성 (금 표준 우선)
        mech = self.generate_mechanism(
            combined_smi, product_smiles,
            transform_name=transform_name,
            conditions=conditions,
        )
        if mech is None:
            return None

        # ─── 금 표준 메커니즘의 인덱스 재매핑 ───────────────────────────────
        # gold standard의 reactant_smiles (예: "CBr.[OH-]") 과
        # 실제 combined_smi (예: "[OH-].CBr") 는 원자 순서가 다를 수 있다.
        # rdFMCS / GetSubstructMatch로 금 표준 template → actual molecule 매핑을 구한다.
        try:
            actual_mol = Chem.MolFromSmiles(combined_smi)
            if actual_mol is None:
                return mech  # 재매핑 불가 → 원본 반환

            actual_mol = Chem.RemoveHs(actual_mol)

            for step in mech.steps:
                # 금 표준 단계의 reactant_smiles 에서 template mol 생성
                template_smi = getattr(step, 'reactant_smiles', None)
                if not template_smi or not isinstance(template_smi, str):
                    continue
                template_mol = Chem.MolFromSmiles(template_smi)
                if template_mol is None:
                    continue
                template_mol = Chem.RemoveHs(template_mol)

                # [P0-4 FIX] 원자 수 동일 체크를 완화 — template은 combined_smi의
                # 부분 구조(subgraph)일 수 있음.
                # 예: EAS step1 template="BrBr"(2원자) vs actual="c1ccccc1.BrBr"(8원자)
                # template > actual 인 경우만 불가능하므로 스킵.
                _t_n = template_mol.GetNumAtoms()
                _a_n = actual_mol.GetNumAtoms()
                if _t_n > _a_n:
                    logger.debug(
                        "generate_intermolecular_mechanism: template(%d) > actual(%d) "
                        "— skipping remap for step %d",
                        _t_n, _a_n, step.step_number)
                    continue

                # template → actual 서브구조 매칭 (원자 심볼 기반)
                # useChirality=False, useQueryQueryMatches=False 로 너그럽게
                match = actual_mol.GetSubstructMatch(template_mol)
                if not match and _t_n < _a_n:
                    # [P0-4 FIX] 원소 불일치로 서브구조 매칭 실패한 경우
                    # (예: 금 표준 "BrBr" vs 실제 "ClCl") → 토폴로지 기반 프래그먼트 오프셋 매칭
                    # combined_smi 내 fragment 중 template과 원자 수가 같은 것을 찾아 offset 매핑
                    try:
                        _frag_mols = Chem.GetMolFrags(actual_mol, asMols=True,
                                                      sanitizeFrags=False)
                        _frag_offset = 0
                        _fallback_match = None
                        for _fm in _frag_mols:
                            _fm_n = _fm.GetNumAtoms()
                            if _fm_n == _t_n:
                                # 원자 수 일치 → 동일 위치의 분자로 간주
                                _fallback_match = tuple(_frag_offset + i
                                                        for i in range(_t_n))
                                break
                            _frag_offset += _fm_n
                        if _fallback_match:
                            match = _fallback_match
                            logger.debug(
                                "generate_intermolecular_mechanism: topology fallback "
                                "match for step %d (template_n=%d, frag_offset=%d)",
                                step.step_number, _t_n, _frag_offset)
                    except Exception as _fe:
                        logger.debug(
                            "generate_intermolecular_mechanism: topology fallback "
                            "error for step %d: %s", step.step_number, _fe)

                if not match and _t_n == _a_n:
                    # 동일 원자 수지만 서브구조 매칭 실패 — 역방향 시도
                    rev_match = template_mol.GetSubstructMatch(actual_mol)
                    if rev_match:
                        # rev_match[i] = actual의 i번 원자가 template의 어느 인덱스에 해당
                        # 필요: template_idx → actual_idx 매핑 (역 인버트)
                        match_list = [None] * _t_n
                        for actual_i, template_i in enumerate(rev_match):
                            if template_i < _t_n:
                                match_list[template_i] = actual_i
                        if None not in match_list:
                            match = tuple(match_list)

                if not match:
                    logger.debug(
                        "generate_intermolecular_mechanism: substructure match failed "
                        "for step %d — arrows kept as-is", step.step_number)
                    continue

                # match[template_idx] = actual_idx
                # ArrowData 인덱스 재매핑
                remapped_arrows = []
                for arrow in step.arrows:
                    import copy
                    new_arrow = copy.copy(arrow)
                    if arrow.from_atom_idx >= 0 and arrow.from_atom_idx < len(match):
                        new_arrow.from_atom_idx = match[arrow.from_atom_idx]
                    if arrow.to_atom_idx >= 0 and arrow.to_atom_idx < len(match):
                        new_arrow.to_atom_idx = match[arrow.to_atom_idx]
                    remapped_arrows.append(new_arrow)
                step.arrows = remapped_arrows
                logger.debug(
                    "generate_intermolecular_mechanism: remapped %d arrows for step %d "
                    "(template='%s' → actual='%s')",
                    len(remapped_arrows), step.step_number, template_smi, combined_smi)

        except Exception as e:
            logger.warning("generate_intermolecular_mechanism: remap error: %s", e)
            # 재매핑 실패 시 원본 메커니즘 반환 (화살표가 잘못될 수 있지만 크래시는 막음)

        return mech

    # ────────────────────────────────────────────────────────────────────
    # Product Prediction
    # ────────────────────────────────────────────────────────────────────

    def _predict_product(self, reactant_smiles: str, reagent_smiles: str) -> str:
        """
        RDKit RunReactants로 생성물 예측.
        REACTION_SMARTS 템플릿을 순회하며 첫 매칭 반환.
        """
        # Rule N: 타입 가드
        if not isinstance(reactant_smiles, str):
            logger.warning("_predict_product: reactant_smiles is not str: %s", type(reactant_smiles).__name__)
            reactant_smiles = str(reactant_smiles) if reactant_smiles is not None else ""
        if not isinstance(reagent_smiles, str):
            logger.warning("_predict_product: reagent_smiles is not str: %s", type(reagent_smiles).__name__)
            reagent_smiles = str(reagent_smiles) if reagent_smiles is not None else ""

        try:
            # 시약을 반응물에 포함
            combined = reactant_smiles
            if reagent_smiles:
                combined = f"{reactant_smiles}.{reagent_smiles}"

            r_mol = Chem.MolFromSmiles(combined)
            if r_mol is None:
                return ""

            # 각 반응 템플릿 시도
            for name, smarts in REACTION_SMARTS.items():
                try:
                    rxn = rdChemReactions.ReactionFromSmarts(smarts)
                    if rxn is None:
                        continue

                    # 반응물 분리
                    frags = Chem.GetMolFrags(r_mol, asMols=True)
                    if len(frags) < rxn.GetNumReactantTemplates():
                        continue

                    # 모든 순열 시도
                    from itertools import permutations
                    for perm in permutations(frags, rxn.GetNumReactantTemplates()):
                        products = rxn.RunReactants(perm)
                        if products:
                            # 모든 product fragment를 합산하여 완전한 생성물 SMILES 생성
                            product_smiles_list = []
                            for p in products[0]:
                                try:
                                    Chem.SanitizeMol(p)
                                    product_smiles_list.append(Chem.MolToSmiles(p))
                                except Exception as e:
                                    logger.warning("Product fragment sanitize/SMILES error: %s", e)
                            if product_smiles_list:
                                # 모든 fragment를 dot-separated로 합산 후 검증
                                combined = ".".join(product_smiles_list)
                                combined_mol = Chem.MolFromSmiles(combined)
                                if combined_mol is not None:
                                    # 정규화된 SMILES 반환 (모든 fragment 포함)
                                    result = Chem.MolToSmiles(combined_mol)
                                    logger.info(f"생성물 예측 성공 ({name}): {result}")
                                    return result
                                else:
                                    # 검증 실패 시 원본 합산 문자열 반환
                                    logger.info(f"생성물 예측 성공 ({name}, 미검증): {combined}")
                                    return combined

                except Exception as e:
                    logger.debug(f"반응 템플릿 {name} 실패: {e}")
                    continue

        except Exception as e:
            logger.warning(f"생성물 예측 오류: {e}")

        return ""

    # ────────────────────────────────────────────────────────────────────
    # Multi-Step Decomposition
    # ────────────────────────────────────────────────────────────────────

    def _decompose_into_steps(self, result: BondChangeResult) \
            -> List[Tuple[List, str]]:
        """
        결합 변화를 여러 단계로 분해.

        Returns:
            [(bond_changes, step_description), ...]
        """
        # Rule N: 타입 가드 — result가 BondChangeResult인지 확인
        if not isinstance(result, BondChangeResult):
            logger.warning("_decompose_into_steps: result is not BondChangeResult: %s",
                           type(result).__name__)
            return [([],  "알 수 없는 반응")]

        changes = result.bond_changes
        if not isinstance(changes, list):
            logger.warning("_decompose_into_steps: bond_changes is not list: %s",
                           type(changes).__name__)
            return [([], "알 수 없는 반응")]

        r_mol = result.r_mol

        # 페리고리 → 단일 단계
        from arrow_generator import ArrowGenerator
        temp_gen = ArrowGenerator()
        if temp_gen._detect_pericyclic(changes, r_mol):
            return [(changes, "페리고리 협주 반응: 전자가 고리형 전이 상태를 통해 동시 재배열")]

        # SN1/E1 패턴 감지 (3차 탄소 우선 — 변화 3개 이하라도 분해 시도)
        broken = [bc for bc in changes if bc.is_broken]
        formed = [bc for bc in changes if bc.is_formed]

        for bc in broken:
            # C-X 결합 끊김에서 C가 3차이면 → 2단계
            for atom_idx in (bc.atom_i, bc.atom_j):
                if 0 <= atom_idx < r_mol.GetNumAtoms():
                    atom = r_mol.GetAtomWithIdx(atom_idx)
                    if atom.GetAtomicNum() == 6:
                        degree = _get_substitution_degree(r_mol, atom_idx)
                        other_idx = bc.atom_j if atom_idx == bc.atom_i else bc.atom_i
                        if degree >= 3 and 0 <= other_idx < r_mol.GetNumAtoms():
                            other_atom = r_mol.GetAtomWithIdx(other_idx)
                            if other_atom.GetAtomicNum() in LEAVING_GROUPS:
                                # SN1/E1: 단계 1 = 이탈, 단계 2 = 공격
                                lg_name = {9: "F", 17: "Cl", 35: "Br", 53: "I"}.get(
                                    other_atom.GetAtomicNum(), "X")
                                step1 = [bc]  # C-X 끊김
                                step2 = [c for c in changes if c != bc]
                                return [
                                    (step1, f"C-{lg_name} 결합 이종 개열 → {lg_name}⁻ 이탈 + 카르보카티온(C⁺) 형성"),
                                    (step2, "친핵체의 론페어가 카르보카티온의 빈 p 오비탈을 공격"),
                                ]

        # 변화가 3개 이하면서 SN1 패턴이 아니면 → 단일 단계 (동시)
        if len(changes) <= 3:
            return [(changes, "동시 반응")]

        # 기본: 끊김 먼저, 생성 나중 (4개 이상 변화)
        if broken and formed:
            # 끊어지는 결합의 원자 기호를 추출
            broken_labels = []
            for bc in broken:
                if r_mol and 0 <= bc.atom_i < r_mol.GetNumAtoms() and 0 <= bc.atom_j < r_mol.GetNumAtoms():
                    si = r_mol.GetAtomWithIdx(bc.atom_i).GetSymbol()
                    sj = r_mol.GetAtomWithIdx(bc.atom_j).GetSymbol()
                    broken_labels.append(f"{si}-{sj}")
            formed_labels = []
            for bc in formed:
                if r_mol and 0 <= bc.atom_i < r_mol.GetNumAtoms() and 0 <= bc.atom_j < r_mol.GetNumAtoms():
                    si = r_mol.GetAtomWithIdx(bc.atom_i).GetSymbol()
                    sj = r_mol.GetAtomWithIdx(bc.atom_j).GetSymbol()
                    formed_labels.append(f"{si}-{sj}")

            other = [c for c in changes if c not in broken and c not in formed]
            step1 = broken + other
            step2 = formed
            bl = ", ".join(broken_labels) if broken_labels else "결합"
            fl = ", ".join(formed_labels) if formed_labels else "결합"
            return [
                (step1, f"{bl} 결합 끊어짐 → 전자쌍이 전기음성 원자로 이동"),
                (step2, f"새 {fl} 결합 형성 → 론페어/전자쌍이 결합으로 전환"),
            ]

        # 분해 불가 → 단일 단계
        return [(changes, "동시 협주 반응: 결합 끊김과 형성이 동시에 진행")]

    # ────────────────────────────────────────────────────────────────────
    # Helper Methods
    # ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _truncate_label(text: str) -> str:
        """라벨 텍스트 길이 제한 — 30자 초과 시 28자 + U+2026(…) ellipsis.

        Magic: MAX_LABEL_LEN = 30 — 메커니즘 캔버스 가로 폭 / 평균 글자 폭 ≈ 30자 (M433 DEFECT-3)
        U+2026(…) HORIZONTAL ELLIPSIS 사용. '...' (ASCII 3점) 금지 — 렌더링 폭 불일치.
        """
        MAX_LABEL_LEN = 30  # Magic: 메커니즘 캔버스 가로 폭 / 평균 글자 폭 ≈ 30 (M433 DEFECT-3)
        if not isinstance(text, str):
            return ""
        return text[:28] + "\u2026" if len(text) > MAX_LABEL_LEN else text

    def _generate_step_title(self, result: BondChangeResult,
                              arrows: List[ArrowData]) -> str:
        """단계 제목 자동 생성 — 화학적으로 의미있는 제목"""
        # Rule N: 타입 가드
        if not isinstance(result, BondChangeResult):
            logger.warning("_generate_step_title: result is not BondChangeResult: %s",
                           type(result).__name__)
            return "전자 재배열"

        broken = []
        formed = []
        order_changes = []

        for bc in result.bond_changes:
            sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)
            if bc.is_broken:
                broken.append(f"{sym_i}-{sym_j}")
            elif bc.is_formed:
                formed.append(f"{sym_i}-{sym_j}")
            else:
                order_changes.append(f"{sym_i}-{sym_j}")

        if broken and formed:
            return self._truncate_label(f"{', '.join(broken)} 결합 끊김 → {', '.join(formed)} 결합 형성 (동시)")
        elif broken:
            return self._truncate_label(f"{', '.join(broken)} 결합 이종 개열 (heterolysis)")
        elif formed:
            return self._truncate_label(f"{', '.join(formed)} 새 결합 형성 (친핵 공격)")
        elif order_changes:
            return self._truncate_label(f"{', '.join(order_changes)} 결합 차수 변화")
        else:
            return "전자 재배열"

    @staticmethod
    def _get_atom_symbols(mol, atom_i: int, atom_j: int):
        """원자 인덱스로부터 원소 기호 추출"""
        # Rule N: 타입 가드 — atom_i, atom_j가 int인지 확인
        if not isinstance(atom_i, int):
            logger.warning("_get_atom_symbols: atom_i is not int: %s", type(atom_i).__name__)
            try:
                atom_i = int(atom_i)
            except (ValueError, TypeError):
                return "?", "?"
        if not isinstance(atom_j, int):
            logger.warning("_get_atom_symbols: atom_j is not int: %s", type(atom_j).__name__)
            try:
                atom_j = int(atom_j)
            except (ValueError, TypeError):
                return "?", "?"

        if mol:
            sym_i = mol.GetAtomWithIdx(atom_i).GetSymbol() \
                if 0 <= atom_i < mol.GetNumAtoms() else "외부"
            sym_j = mol.GetAtomWithIdx(atom_j).GetSymbol() \
                if 0 <= atom_j < mol.GetNumAtoms() else "외부"
        else:
            sym_i, sym_j = "?", "?"
        return sym_i, sym_j

    @staticmethod
    def _classify_atom_role(mol, atom_idx: int, is_leaving: bool = False) -> str:
        """원자의 화학적 역할을 판별 (친핵체/친전자체/이탈기 등)"""
        # Rule N: 타입 가드
        if not isinstance(atom_idx, int):
            logger.warning("_classify_atom_role: atom_idx is not int: %s", type(atom_idx).__name__)
            try:
                atom_idx = int(atom_idx)
            except (ValueError, TypeError):
                return ""
        if mol is None or atom_idx < 0 or atom_idx >= mol.GetNumAtoms():
            return ""
        atom = mol.GetAtomWithIdx(atom_idx)
        anum = atom.GetAtomicNum()
        charge = atom.GetFormalCharge()
        symbol = atom.GetSymbol()

        # 이탈기 판별
        if is_leaving and anum in LEAVING_GROUPS:
            # 음전하 위첨자: U+207B (⁻) — 양전하 위첨자: U+207A (⁺) 짝.
            # U+2212(−)는 일반 마이너스(수식용), 위첨자 아님 — 혼용 금지 (M433 DEFECT-1)
            _names = {9: "F⁻", 17: "Cl⁻", 35: "Br⁻", 53: "I⁻"}
            # Rule N: isinstance guard for _names
            if not isinstance(_names, dict): _names = {}
            return f"{_names.get(anum, symbol + '⁻')} (이탈기)"  # ⁻ = U+207B

        # 음전하 → 친핵체 (⁻ = U+207B SUPERSCRIPT MINUS, ⁺ = U+207A SUPERSCRIPT PLUS)
        if charge < 0:
            return f"{symbol}⁻ (친핵체)"

        # 양전하 → 친전자체
        if charge > 0:
            return f"{symbol}⁺ (친전자체)"

        # 전기음성도 기반 역할 추론
        en = _ELECTRONEG.get(anum, 2.5)
        if en > 3.0 and anum != 6:  # O, N, F 등 전기음성 원소
            return f"{symbol} (론페어 보유, 친핵성)"
        if anum == 6:
            return f"C (탄소)"

        return symbol

    def _generate_step_description(self, result: BondChangeResult,
                                    arrows: List[ArrowData]) -> str:
        """
        단계 상세 설명 자동 생성 — 화학적으로 정확하고 교육적인 설명.
        각 결합 변화에 대해:
        - 어떤 결합이 끊어지는지/형성되는지
        - 전자가 어디로 이동하는지
        - 이탈기/친핵체/친전자체 명시
        - WHY 이 변화가 일어나는지 설명
        """
        # Rule N: 타입 가드
        if not isinstance(result, BondChangeResult):
            logger.warning("_generate_step_description: result is not BondChangeResult: %s",
                           type(result).__name__)
            return "전자 재배열이 일어남"
        if not isinstance(arrows, list):
            logger.warning("_generate_step_description: arrows is not list: %s",
                           type(arrows).__name__)
            arrows = []

        parts = []
        broken_bonds = []
        formed_bonds = []

        for bc in result.bond_changes:
            sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)

            if bc.is_broken:
                broken_bonds.append((sym_i, sym_j, bc))
            elif bc.is_formed:
                formed_bonds.append((sym_i, sym_j, bc))

        # 끊어지는 결합 설명
        for sym_i, sym_j, bc in broken_bonds:
            # 이탈기 여부 판별
            leaving_info = ""
            electron_info = ""
            if result.r_mol:
                en_i = _ELECTRONEG.get(
                    result.r_mol.GetAtomWithIdx(bc.atom_i).GetAtomicNum(), 2.5
                ) if 0 <= bc.atom_i < result.r_mol.GetNumAtoms() else 2.5
                en_j = _ELECTRONEG.get(
                    result.r_mol.GetAtomWithIdx(bc.atom_j).GetAtomicNum(), 2.5
                ) if 0 <= bc.atom_j < result.r_mol.GetNumAtoms() else 2.5

                if en_i > en_j:
                    electron_info = f"결합 전자쌍이 {sym_i}(전기음성도 {en_i:.1f})로 이동"
                    if 0 <= bc.atom_j < result.r_mol.GetNumAtoms() and \
                       result.r_mol.GetAtomWithIdx(bc.atom_j).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_j}⁻가 이탈기로 떠남"
                    elif 0 <= bc.atom_i < result.r_mol.GetNumAtoms() and \
                         result.r_mol.GetAtomWithIdx(bc.atom_i).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_i}⁻가 이탈기로 떠남"
                elif en_j > en_i:
                    electron_info = f"결합 전자쌍이 {sym_j}(전기음성도 {en_j:.1f})로 이동"
                    if 0 <= bc.atom_i < result.r_mol.GetNumAtoms() and \
                       result.r_mol.GetAtomWithIdx(bc.atom_i).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_i}⁻가 이탈기로 떠남"
                    elif 0 <= bc.atom_j < result.r_mol.GetNumAtoms() and \
                         result.r_mol.GetAtomWithIdx(bc.atom_j).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_j}⁻가 이탈기로 떠남"
                else:
                    electron_info = f"결합 전자쌍이 균일 개열(homolysis)"

            desc = f"{sym_i}-{sym_j} 결합이 이종 개열(heterolysis): {electron_info}{leaving_info}"
            parts.append(desc)

        # 형성되는 결합 설명
        for sym_i, sym_j, bc in formed_bonds:
            # 어느 쪽이 전자를 공여하는지 판별
            donor_info = ""
            if result.r_mol:
                # 음전하를 가진 쪽 또는 전기음성도가 높은 비탄소 원자가 전자 공여
                for idx, sym in [(bc.atom_i, sym_i), (bc.atom_j, sym_j)]:
                    if 0 <= idx < result.r_mol.GetNumAtoms():
                        atom = result.r_mol.GetAtomWithIdx(idx)
                        if atom.GetFormalCharge() < 0:
                            donor_info = f"{sym}⁻의 론페어가 전자를 공여 → "  # ⁻ = U+207B SUPERSCRIPT MINUS (M433 DEFECT-1)
                            break
                        elif atom.GetAtomicNum() in (7, 8, 16) and atom.GetAtomicNum() != 6:
                            donor_info = f"{sym}의 론페어가 전자를 공여 → "
                            break

            bond_type = "sigma"
            if hasattr(bc, 'product_order') and bc.product_order == 2.0:
                bond_type = "pi"

            desc = f"{donor_info}새 {sym_i}-{sym_j} {bond_type} 결합 형성"
            parts.append(desc)

        # 결합 차수 변화 설명
        for bc in result.bond_changes:
            if bc.change_type == "order_increase":
                sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)
                parts.append(
                    f"{sym_i}-{sym_j} 결합 차수 증가 ({bc.reactant_order}→{bc.product_order}): "
                    f"전자밀도가 결합 영역으로 이동하여 결합이 강화됨"
                )
            elif bc.change_type == "order_decrease":
                sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)
                parts.append(
                    f"{sym_i}-{sym_j} 결합 차수 감소 ({bc.reactant_order}→{bc.product_order}): "
                    f"전자밀도가 결합에서 빠져나가 결합이 약화됨"
                )

        if not parts:
            return "전자 재배열이 일어남"

        return ".\n".join(parts) + "."

    def _generate_overall_description(self, steps: List[MechanismStep],
                                        reactant_smiles: str,
                                        product_smiles: str) -> str:
        """메커니즘 전체 요약 설명 자동 생성"""
        n = len(steps)
        step_summaries = []
        for s in steps:
            # 제목에서 핵심 정보 추출
            step_summaries.append(f"단계 {s.step_number}: {s.title}")

        # 결합 변화 통계
        total_broken = sum(len([a for a in s.arrows if "끊" in a.from_label or "결합" in a.from_label])
                           for s in steps)
        total_formed = sum(len([a for a in s.arrows if "론페어" in a.from_label or "negative" in a.from_type])
                           for s in steps)

        desc = f"이 반응은 {n}단계로 진행됩니다. "
        if n == 1:
            desc += "모든 결합 변화가 동시에(협주적으로) 일어나는 반응입니다. "
        else:
            desc += "각 단계에서 결합이 순차적으로 끊어지고 형성됩니다. "

        desc += " → ".join(step_summaries) + "."
        return desc

    def _generate_mechanism_title(self, reactant_smiles: str,
                                   product_smiles: str) -> str:
        """메커니즘 전체 제목 생성"""
        # 간단한 SMILES → 이름 변환 시도
        try:
            r_mol = Chem.MolFromSmiles(reactant_smiles)
            p_mol = Chem.MolFromSmiles(product_smiles)
            if r_mol is not None and p_mol is not None:  # Rule L: None guard
                r_formula = Chem.rdMolDescriptors.CalcMolFormula(r_mol)
                p_formula = Chem.rdMolDescriptors.CalcMolFormula(p_mol)
                return f"{r_formula} → {p_formula}"
        except Exception as e:
            logger.warning("Reaction title generation error: %s", e)
        return f"반응 메커니즘"

    def _estimate_intermediate_smiles(self, start_smiles: str,
                                       step_changes) -> str:
        """
        RDKit RWMol 기반 중간체 SMILES 생성.

        결합 변화(BondChange) 목록을 start_smiles 분자에 적용하여
        중간체 구조를 생성한다.  Rule N 타입 가드 적용.  결합 끊김/생성/차수 변화를 RWMol
        AddBond/RemoveBond/SetBondType으로 수행한 뒤 SanitizeMol을
        거쳐 SMILES를 반환한다.

        SanitizeMol 실패 시 start_smiles를 그대로 반환 (안전 폴백).
        """
        # Rule N: 타입 가드
        if not isinstance(start_smiles, str):
            logger.warning("_estimate_intermediate_smiles: start_smiles is not str: %s",
                           type(start_smiles).__name__)
            start_smiles = str(start_smiles) if start_smiles is not None else ""
        if not isinstance(step_changes, list):
            logger.warning("_estimate_intermediate_smiles: step_changes is not list: %s",
                           type(step_changes).__name__)
            return start_smiles

        if not RDKIT_AVAILABLE:
            return start_smiles

        try:
            mol = Chem.MolFromSmiles(start_smiles)
            if mol is None:
                return start_smiles

            rwmol = Chem.RWMol(mol)
            num_atoms = rwmol.GetNumAtoms()

            # BondType 매핑
            _order_to_bondtype = {
                1.0: Chem.BondType.SINGLE,
                2.0: Chem.BondType.DOUBLE,
                3.0: Chem.BondType.TRIPLE,
                1.5: Chem.BondType.AROMATIC,
            }

            for bc in step_changes:
                ai = bc.atom_i
                aj = bc.atom_j

                # 범위 초과 원자 인덱스는 건너뛴다 (외부 조각 원자)
                if ai >= num_atoms or aj >= num_atoms or ai < 0 or aj < 0:
                    continue

                existing_bond = rwmol.GetBondBetweenAtoms(ai, aj)

                if bc.is_broken:
                    # ── 결합 끊김 ──
                    if existing_bond is not None:
                        rwmol.RemoveBond(ai, aj)
                        # 이탈기 원자의 형식전하 보정
                        self._adjust_charge_on_break(rwmol, ai, aj, bc.reactant_order)

                elif bc.is_formed:
                    # ── 새 결합 생성 ──
                    if existing_bond is None:
                        # Rule N: isinstance guard for _order_to_bondtype
                        if not isinstance(_order_to_bondtype, dict): _order_to_bondtype = {}
                        bt = _order_to_bondtype.get(bc.product_order, Chem.BondType.SINGLE)
                        rwmol.AddBond(ai, aj, bt)
                        # 형식전하 보정
                        self._adjust_charge_on_form(rwmol, ai, aj)

                elif bc.change_type in ("order_increase", "order_decrease"):
                    # ── 결합 차수 변화 ──
                    if existing_bond is not None:
                        new_bt = _order_to_bondtype.get(bc.product_order, Chem.BondType.SINGLE)
                        existing_bond.SetBondType(new_bt)

            # SanitizeMol 시도 — 실패 시 원래 SMILES 반환
            try:
                Chem.SanitizeMol(rwmol)
                result = Chem.MolToSmiles(rwmol)
                # 빈 SMILES나 유효하지 않은 결과 체크
                _val = Chem.MolFromSmiles(result) if result else None
                if _val is not None:  # Rule L: None guard
                    return result
            except Exception as e:
                logger.debug(f"중간체 SanitizeMol 실패 (partial sanitize 시도): {e}")
                # partial sanitize 시도 (valence 에러 무시)
                try:
                    Chem.SanitizeMol(rwmol,
                                     sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL ^
                                     Chem.SanitizeFlags.SANITIZE_PROPERTIES)
                    result = Chem.MolToSmiles(rwmol)
                    if result:
                        return result
                except Exception as e:
                    logger.warning("Intermediate SMILES sanitize error: %s", e)

        except Exception as e:
            logger.warning(f"중간체 SMILES 생성 오류: {e}")

        return start_smiles  # 안전 폴백

    @staticmethod
    def _adjust_charge_on_break(rwmol, ai: int, aj: int, bond_order: float):
        """결합 끊김 시 형식전하 보정 (헤테로리틱 분열 가정)"""
        try:
            atom_i = rwmol.GetAtomWithIdx(ai)
            atom_j = rwmol.GetAtomWithIdx(aj)

            # 전기음성도가 높은 쪽에 음전하 부여 (헤테로리틱)
            # SetFormalCharge(-1) = 음전하. 표시 라벨은 U+207B(⁻). U+2212(−) 혼용 금지 (M433 DEFECT-1)
            en_i = _ELECTRONEG.get(atom_i.GetAtomicNum(), 2.5)
            en_j = _ELECTRONEG.get(atom_j.GetAtomicNum(), 2.5)

            if en_i > en_j:
                # i가 더 전기음성적 → 전자 쌍을 가져감
                atom_i.SetFormalCharge(atom_i.GetFormalCharge() - 1)
                atom_j.SetFormalCharge(atom_j.GetFormalCharge() + 1)
            elif en_j > en_i:
                atom_j.SetFormalCharge(atom_j.GetFormalCharge() - 1)
                atom_i.SetFormalCharge(atom_i.GetFormalCharge() + 1)
            # en_i == en_j: 동종 분열 — 전하 변화 없음
        except Exception as e:
            logger.warning("Charge adjustment on bond break error: %s", e)

    @staticmethod
    def _adjust_charge_on_form(rwmol, ai: int, aj: int):
        """새 결합 형성 시 형식전하 보정"""
        try:
            atom_i = rwmol.GetAtomWithIdx(ai)
            atom_j = rwmol.GetAtomWithIdx(aj)

            # 음전하를 가진 쪽이 전자를 공여 → 전하 중화
            # 형식전하 -1 → 0 : 표시 ⁻(U+207B) 소멸. U+2212(−) 불가 (M433 DEFECT-1)
            if atom_i.GetFormalCharge() < 0:
                atom_i.SetFormalCharge(atom_i.GetFormalCharge() + 1)
            if atom_j.GetFormalCharge() > 0:
                atom_j.SetFormalCharge(atom_j.GetFormalCharge() - 1)
        except Exception as e:
            logger.warning("Charge adjustment on bond form error: %s", e)

    def _estimate_energy_diagram(self, steps: List[MechanismStep]) \
            -> List[Tuple[str, float]]:
        """에너지 다이어그램 근사"""
        # Rule N: 타입 가드
        if not isinstance(steps, list):
            logger.warning("_estimate_energy_diagram: steps is not list: %s",
                           type(steps).__name__)
            return [("반응물", 0.0), ("생성물", -10.0)]

        diagram = [("반응물", 0.0)]

        for i, step in enumerate(steps):
            # 전이 상태 (활성화 에너지 근사)
            n_arrows = len(step.arrows)
            barrier = 15.0 + n_arrows * 5.0  # 화살표 많을수록 높은 장벽
            diagram.append((f"TS{i + 1}", barrier))

            # 중간체/생성물
            if i < len(steps) - 1:
                diagram.append((f"중간체 {i + 1}", 5.0))
            else:
                diagram.append(("생성물", -10.0))

        return diagram


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def auto_mechanism(reactant_smiles: str,
                    product_smiles: str = "",
                    reagent_smiles: str = "",
                    mechanism_type_hint: str = "") -> Optional[MechanismData]:
    """
    편의 함수: MechanismEngine 인스턴스 생성 없이 직접 호출.

    사용법:
        mech = auto_mechanism("CBr.[OH-]", "CO.[Br-]")
    """
    # Rule N: 타입 가드 — 외부 호출부에서 비str 전달 방어
    if not isinstance(reactant_smiles, str):
        logger.warning("auto_mechanism: reactant_smiles is not str: %s", type(reactant_smiles).__name__)
        reactant_smiles = str(reactant_smiles) if reactant_smiles is not None else ""
    if not isinstance(product_smiles, str):
        product_smiles = str(product_smiles) if product_smiles is not None else ""
    if not isinstance(reagent_smiles, str):
        reagent_smiles = str(reagent_smiles) if reagent_smiles is not None else ""
    if not isinstance(mechanism_type_hint, str):
        mechanism_type_hint = str(mechanism_type_hint) if mechanism_type_hint is not None else ""

    engine = MechanismEngine()
    return engine.generate_mechanism(
        reactant_smiles=reactant_smiles,
        product_smiles=product_smiles,
        reagent_smiles=reagent_smiles,
        mechanism_type_hint=mechanism_type_hint,
    )
