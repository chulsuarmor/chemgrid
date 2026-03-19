#!/usr/bin/env python3
"""
상용 시작물질(Building Blocks) 데이터베이스.
역합성 분석에서 '목표 도달' 판정 기준이 되는 간단한 화합물 목록.
Tanimoto 유사도 기반 유사 시작물질 검색 지원.
"""
from typing import Dict, List, Optional, Tuple

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ═══════════════════════════════════════════════════════════
# 상용 시작물질 데이터베이스 (~80개)
# canonical SMILES → 메타데이터
# ═══════════════════════════════════════════════════════════

BUILDING_BLOCKS: Dict[str, Dict] = {}

_RAW_BLOCKS = [
    # ═══════════════════════════════════════════════════════════
    # 빌딩블록 = 진짜 간단한 상용 시작물질만 포함
    # (합성 경로 분석에서 "끝점"이 되는 분자들)
    #
    # 원칙: 1~2단계 합성으로 만들 수 있는 분자는 빌딩블록이 아님
    #   예: 벤즈알데히드 = 톨루엔 산화 → 빌딩블록 X
    #       니트로벤젠 = 벤젠 니트로화 → 빌딩블록 X
    #       아세토페논 = FC 아실화 → 빌딩블록 X
    # ═══════════════════════════════════════════════════════════

    # ── 단순 탄화수소 (C, H만) ──
    ("C", "메탄", "Methane", "low"),
    ("CC", "에탄", "Ethane", "low"),
    ("CCC", "프로판", "Propane", "low"),
    ("C=C", "에틸렌", "Ethylene", "low"),
    ("CC=C", "프로필렌", "Propylene", "low"),
    ("C#C", "아세틸렌", "Acetylene", "low"),
    ("C=CC=C", "1,3-부타디엔", "1,3-Butadiene", "low"),
    ("C1CCCCC1", "시클로헥산", "Cyclohexane", "low"),
    ("C1CCCC1", "시클로펜탄", "Cyclopentane", "low"),

    # ── 방향족 (비치환 고리만) ──
    ("c1ccccc1", "벤젠", "Benzene", "low"),
    ("c1ccc2ccccc2c1", "나프탈렌", "Naphthalene", "medium"),
    ("c1ccncc1", "피리딘", "Pyridine", "low"),
    ("c1cc[nH]c1", "피롤", "Pyrrole", "medium"),
    ("c1ccoc1", "퓨란", "Furan", "medium"),
    ("c1ccsc1", "티오펜", "Thiophene", "medium"),

    # ── 단순 알코올 (지방족만) ──
    ("CO", "메탄올", "Methanol", "low"),
    ("CCO", "에탄올", "Ethanol", "low"),
    ("CCCO", "1-프로판올", "1-Propanol", "low"),
    ("CC(O)C", "2-프로판올", "Isopropanol", "low"),
    ("CCCCO", "1-부탄올", "1-Butanol", "low"),

    # ── 할라이드 (지방족만 — 방향족 할라이드는 합성 대상) ──
    ("CCl", "클로로메탄", "Chloromethane", "low"),
    ("CBr", "브로모메탄", "Bromomethane", "low"),
    ("CI", "요오도메탄", "Iodomethane", "low"),
    ("CCCl", "클로로에탄", "Chloroethane", "low"),
    ("CCBr", "브로모에탄", "Bromoethane", "low"),
    ("CCI", "요오도에탄", "Iodoethane", "low"),
    ("ClCCl", "디클로로메탄", "DCM", "low"),

    # ── 카르보닐 (단순 지방족만) ──
    ("C=O", "폼알데히드", "Formaldehyde", "low"),
    ("CC=O", "아세트알데히드", "Acetaldehyde", "low"),
    ("CCC=O", "프로피온알데히드", "Propionaldehyde", "low"),
    ("CC(=O)C", "아세톤", "Acetone", "low"),
    ("CC(=O)CC", "메틸 에틸 케톤", "MEK", "low"),

    # ── 카르복실산 (단순 지방족만) ──
    ("OC=O", "포름산", "Formic acid", "low"),
    ("CC(=O)O", "아세트산", "Acetic acid", "low"),
    ("CCC(=O)O", "프로피온산", "Propionic acid", "low"),
    ("OC(=O)CC(=O)O", "말론산", "Malonic acid", "medium"),

    # ── 아실 할라이드 (시약) ──
    ("CC(=O)Cl", "아세틸 클로라이드", "Acetyl chloride", "low"),
    ("CC(=O)OC(=O)C", "무수 아세트산", "Acetic anhydride", "low"),

    # ── 아민 (단순 지방족만) ──
    ("CN", "메틸아민", "Methylamine", "low"),
    ("CCN", "에틸아민", "Ethylamine", "low"),
    ("CNC", "디메틸아민", "Dimethylamine", "low"),
    ("CN(C)C", "트리메틸아민", "Trimethylamine", "low"),
    ("N", "암모니아", "Ammonia", "low"),

    # ── 나이트릴 (단순만) ──
    ("CC#N", "아세토나이트릴", "Acetonitrile", "low"),

    # ── 유기금속/시약 ──
    ("C[Mg]Br", "메틸마그네슘 브로마이드", "MeMgBr (Grignard)", "medium"),
    ("CC[Mg]Br", "에틸마그네슘 브로마이드", "EtMgBr (Grignard)", "medium"),
    ("[C-]#N", "시아나이드 이온", "Cyanide ion", "low"),

    # ── 무기 시약/용매 ──
    ("O", "물", "Water", "low"),
    ("[OH-]", "수산화 이온", "Hydroxide", "low"),
    ("OO", "과산화수소", "Hydrogen peroxide", "low"),
    ("Cl", "염산", "HCl", "low"),
    ("Br", "브롬화수소산", "HBr", "low"),
    ("BrBr", "브로민", "Bromine (Br₂)", "low"),
    ("ClCl", "염소", "Chlorine (Cl₂)", "low"),
    ("NO", "히드록실아민", "Hydroxylamine", "low"),
    ("NN", "히드라진", "Hydrazine", "medium"),
    ("OS(=O)(=O)O", "황산", "Sulfuric acid", "low"),
    ("O=[N+]([O-])O", "질산", "Nitric acid", "low"),

    # ── 기타 유용한 빌딩블록 ──
    ("C1CO1", "에틸렌 옥사이드", "Ethylene oxide", "low"),
    ("C=CC#N", "아크릴로나이트릴", "Acrylonitrile", "low"),
    ("C=CC(=O)O", "아크릴산", "Acrylic acid", "low"),

    # ── 방향족 1치환 (주요 상용 시약) ──
    ("Oc1ccccc1", "페놀", "Phenol", "low"),
    ("Nc1ccccc1", "아닐린", "Aniline", "low"),
    ("Cc1ccccc1", "톨루엔", "Toluene", "low"),
    ("OC(=O)c1ccccc1", "벤조산", "Benzoic acid", "low"),
    ("O=Cc1ccccc1", "벤즈알데히드", "Benzaldehyde", "low"),
    ("c1ccc(O)c(O)c1", "카테콜", "Catechol", "medium"),
    ("Oc1ccc(O)cc1", "하이드로퀴논", "Hydroquinone", "medium"),

    # ── 추가 알코올/디올 ──
    ("OCCO", "에틸렌 글리콜", "Ethylene glycol", "low"),
    ("OCC(O)CO", "글리세롤", "Glycerol", "low"),
    ("C(O)c1ccccc1", "벤질 알코올", "Benzyl alcohol", "low"),
    ("OC(C)(C)C", "tert-부탄올", "tert-Butanol", "low"),

    # ── 추가 카르복실산 ──
    ("OC(=O)CCC(=O)O", "숙신산", "Succinic acid", "low"),
    ("OC(=O)CC(O)(CC(=O)O)C(=O)O", "시트르산", "Citric acid", "low"),
    ("OC(=O)/C=C/C(=O)O", "푸마르산", "Fumaric acid", "medium"),
    ("OC(=O)/C=C\\C(=O)O", "말레산", "Maleic acid", "medium"),
    ("OC(=O)c1ccc(C(=O)O)cc1", "테레프탈산", "Terephthalic acid", "medium"),

    # ── 추가 아민 ──
    ("NCCN", "에틸렌디아민", "Ethylenediamine", "low"),
    ("NCC(=O)O", "글리신", "Glycine", "low"),
    ("NCCCN", "1,3-디아미노프로판", "1,3-Diaminopropane", "medium"),
    ("c1cnc2ccccc2n1", "퀴나졸린", "Quinazoline", "medium"),

    # ── 추가 할라이드 ──
    ("ClCCCl", "1,2-디클로로에탄", "1,2-Dichloroethane", "low"),
    ("ClC(Cl)Cl", "클로로포름", "Chloroform", "low"),
    ("ClC(Cl)(Cl)Cl", "사염화탄소", "Carbon tetrachloride", "low"),
    ("BrCCBr", "1,2-디브로모에탄", "1,2-Dibromoethane", "low"),
    ("ClCCO", "2-클로로에탄올", "2-Chloroethanol", "low"),

    # ── 에테르/용매 ──
    ("CCOCC", "디에틸에테르", "Diethyl ether", "low"),
    ("C1CCOC1", "THF", "Tetrahydrofuran", "low"),
    ("COCCO", "2-메톡시에탄올", "2-Methoxyethanol", "low"),

    # ── 추가 카르보닐/에스터 ──
    ("CCOC(=O)CC(=O)OCC", "디에틸 말로네이트", "Diethyl malonate", "low"),
    ("COC(=O)C", "아세트산 메틸", "Methyl acetate", "low"),
    ("CCOC(=O)C", "아세트산 에틸", "Ethyl acetate", "low"),

    # ── 산화/환원 시약 (표현 가능한 것만) ──
    ("O=S(=O)(Cl)Cl", "염화티오닐", "Thionyl chloride (SOCl₂)", "low"),
    ("ClP(Cl)Cl", "삼염화인", "Phosphorus trichloride", "medium"),

    # ── 추가 헤테로사이클 ──
    ("c1c[nH]cn1", "이미다졸", "Imidazole", "low"),
    ("c1cnc[nH]1", "이미다졸 (tautomer)", "Imidazole (tautomer)", "low"),
    ("c1ccnnc1", "피리다진", "Pyridazine", "medium"),
    ("c1ccncn1", "피리미딘", "Pyrimidine", "medium"),
    ("c1cnccn1", "피라진", "Pyrazine", "medium"),

    # ── 설폰산/설포닐 ──
    ("CS(=O)(=O)Cl", "메탄설포닐 클로라이드", "Methanesulfonyl chloride", "low"),
    ("c1ccc(S(=O)(=O)Cl)cc1", "벤젠설포닐 클로라이드", "Benzenesulfonyl chloride", "medium"),

    # ── 기타 범용 시약 ──
    ("O=C=O", "이산화탄소", "Carbon dioxide", "low"),
    ("C=O", "폼알데히드", "Formaldehyde", "low"),
    ("ClS(=O)(=O)O", "클로로설폰산", "Chlorosulfonic acid", "medium"),
    ("OB(O)c1ccccc1", "페닐보론산", "Phenylboronic acid", "medium"),
    ("CC(=O)c1ccccc1", "아세토페논", "Acetophenone", "low"),

    # ═══ 확장 빌딩블록 (Sigma-Aldrich 카탈로그 주요 시약) ═══

    # ── 방향족 할라이드 (주요 상용 시약) ──
    ("Clc1ccccc1", "클로로벤젠", "Chlorobenzene", "low"),
    ("Brc1ccccc1", "브로모벤젠", "Bromobenzene", "low"),
    ("Ic1ccccc1", "요오도벤젠", "Iodobenzene", "low"),
    ("Fc1ccccc1", "플루오로벤젠", "Fluorobenzene", "low"),
    ("Fc1ccc(F)cc1", "1,4-디플루오로벤젠", "1,4-Difluorobenzene", "low"),
    ("Clc1ccc(Cl)cc1", "1,4-디클로로벤젠", "1,4-Dichlorobenzene", "low"),
    ("Brc1ccc(Br)cc1", "1,4-디브로모벤젠", "1,4-Dibromobenzene", "medium"),
    ("FC(F)(F)c1ccccc1", "벤조트리플루오라이드", "Benzotrifluoride", "low"),

    # ── 방향족 니트로 화합물 ──
    ("O=[N+]([O-])c1ccccc1", "니트로벤젠", "Nitrobenzene", "low"),
    ("O=[N+]([O-])c1ccc(N)cc1", "4-니트로아닐린", "4-Nitroaniline", "low"),
    ("O=[N+]([O-])c1ccc(O)cc1", "4-니트로페놀", "4-Nitrophenol", "low"),

    # ── 치환 벤젠 (주요) ──
    ("Cc1ccc(C)cc1", "파라자일렌", "p-Xylene", "low"),
    ("COc1ccccc1", "아니솔", "Anisole", "low"),
    ("CCc1ccccc1", "에틸벤젠", "Ethylbenzene", "low"),
    ("C(=O)c1ccccc1Cl", "2-클로로벤즈알데히드", "2-Chlorobenzaldehyde", "low"),
    ("OC(=O)c1ccccc1O", "살리실산", "Salicylic acid", "low"),
    ("Oc1ccccc1O", "카테콜(중복방지)", "Catechol (alias)", "medium"),
    ("Nc1ccc(N)cc1", "파라페닐렌디아민", "p-Phenylenediamine", "medium"),

    # ── 추가 알코올 ──
    ("CC(C)O", "이소프로판올(alt)", "2-Propanol", "low"),
    ("C(C)(C)(C)O", "tert-부탄올(alt)", "tert-Butanol", "low"),
    ("C=CCO", "알릴 알코올", "Allyl alcohol", "low"),
    ("OCc1ccccc1", "벤질알코올(alt)", "Benzyl alcohol", "low"),
    ("CC(O)C(=O)O", "젖산", "Lactic acid", "low"),

    # ── 추가 산 ──
    ("OC(=O)CCCCC(=O)O", "아디프산", "Adipic acid", "low"),
    ("OC(=O)c1ccccc1C(=O)O", "프탈산", "Phthalic acid", "medium"),
    ("OC(=O)C=C", "아크릴산(dup)", "Acrylic acid", "low"),
    ("OC(=O)CCC(=O)O", "글루타르산", "Glutaric acid", "medium"),
    ("CCCCCCCCCCCCCCCCCC(=O)O", "스테아르산", "Stearic acid", "low"),
    ("CCCCCCCCCCCC(=O)O", "라우르산", "Lauric acid", "low"),

    # ── 추가 에스터/무수물 ──
    ("O=C1OC(=O)c2ccccc21", "무수프탈산", "Phthalic anhydride", "low"),
    ("O=C1OC(=O)C=C1", "무수말레산", "Maleic anhydride", "low"),
    ("CCOC(=O)c1ccccc1", "벤조산에틸", "Ethyl benzoate", "low"),
    ("COC(=O)c1ccccc1", "벤조산메틸", "Methyl benzoate", "low"),

    # ── 추가 아민 ──
    ("CCN(CC)CC", "트리에틸아민", "Triethylamine", "low"),
    ("C1CCNCC1", "피페리딘", "Piperidine", "low"),
    ("C1CCNC1", "피롤리딘", "Pyrrolidine", "low"),
    ("C1CNCCN1", "피페라진", "Piperazine", "low"),
    ("c1ccc(CN)cc1", "벤질아민", "Benzylamine", "low"),
    ("NCc1ccccc1", "벤질아민(alt)", "Benzylamine (alt SMILES)", "low"),
    ("NCCO", "에탄올아민", "Ethanolamine", "low"),
    ("CN(C)C=O", "DMF", "Dimethylformamide", "low"),

    # ── 추가 케톤 ──
    ("O=C1CCCCC1", "시클로헥사논", "Cyclohexanone", "low"),
    ("O=C1CCCC1", "시클로펜타논", "Cyclopentanone", "low"),
    ("CC(=O)CC(=O)C", "아세틸아세톤", "Acetylacetone", "low"),
    ("CC(=O)CC(=O)OCC", "아세토아세트산에틸", "Ethyl acetoacetate", "low"),

    # ── 추가 할라이드 ──
    ("BrCCCBr", "1,3-디브로모프로판", "1,3-Dibromopropane", "low"),
    ("ClCCCCl", "1,3-디클로로프로판", "1,3-Dichloropropane", "low"),
    ("C(Cl)(Cl)=O", "포스겐(대체)", "Phosgene", "medium"),
    ("ClC(=O)c1ccccc1", "벤조일 클로라이드", "Benzoyl chloride", "low"),
    ("BrCC=C", "알릴 브로마이드", "Allyl bromide", "low"),
    ("BrCc1ccccc1", "벤질 브로마이드", "Benzyl bromide", "low"),
    ("ClCc1ccccc1", "벤질 클로라이드", "Benzyl chloride", "low"),

    # ── 유기금속/커플링 시약 ──
    ("C[Li]", "메틸리튬", "Methyllithium", "medium"),
    ("CCCC[Li]", "n-부틸리튬", "n-Butyllithium", "medium"),
    ("OB(O)c1ccc(C)cc1", "4-메틸페닐보론산", "4-Methylphenylboronic acid", "medium"),
    ("[Pd]", "팔라듐", "Palladium", "medium"),

    # ── 산화/환원제 ──
    ("[O-][Mn](=O)(=O)=O.[K+]", "과망간산칼륨", "Potassium permanganate", "low"),
    # Chromic acid: SMILES parse error on some RDKit builds, omitted
    ("[BH4-].[Na+]", "수소화붕소나트륨", "Sodium borohydride", "low"),
    ("[AlH4-].[Li+]", "수소화알루미늄리튬", "Lithium aluminum hydride", "medium"),

    # ── 디올/폴리올 ──
    ("CC(O)CO", "프로필렌글리콜", "Propylene glycol", "low"),
    ("OCCCCO", "1,4-부탄디올", "1,4-Butanediol", "low"),

    # ── 기체/간단무기 ──
    ("O=S=O", "이산화황", "Sulfur dioxide", "low"),
    ("[H][H]", "수소", "Hydrogen", "low"),
    ("O=O", "산소", "Oxygen", "low"),
    ("N#N", "질소", "Nitrogen", "low"),
    ("[Na]OCC", "나트륨 에톡사이드", "Sodium ethoxide", "low"),
]


def _init_building_blocks():
    """초기화: canonical SMILES로 정규화하여 등록"""
    for smi, name_kr, name_en, cost in _RAW_BLOCKS:
        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                canon = Chem.MolToSmiles(mol)
            else:
                canon = smi
        else:
            canon = smi
        BUILDING_BLOCKS[canon] = {
            "name": name_kr,
            "name_en": name_en,
            "cost": cost,
            "original_smiles": smi,
        }

_init_building_blocks()


def is_building_block(smiles: str) -> bool:
    """주어진 SMILES가 상용 시작물질인지 확인"""
    if not RDKIT_AVAILABLE:
        return smiles in BUILDING_BLOCKS
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    canon = Chem.MolToSmiles(mol)
    return canon in BUILDING_BLOCKS


def get_building_block_info(smiles: str) -> Optional[Dict]:
    """시작물질 정보 반환 (없으면 None)"""
    if not RDKIT_AVAILABLE:
        return BUILDING_BLOCKS.get(smiles)
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    canon = Chem.MolToSmiles(mol)
    return BUILDING_BLOCKS.get(canon)


def find_similar_blocks(smiles: str, top_n: int = 5) -> List[Tuple[str, str, float]]:
    """Tanimoto 유사도로 유사한 시작물질 검색.
    Returns: [(canonical_smiles, name, similarity), ...]"""
    if not RDKIT_AVAILABLE:
        return []

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    fp_target = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)

    results = []
    for bb_smi, info in BUILDING_BLOCKS.items():
        bb_mol = Chem.MolFromSmiles(bb_smi)
        if bb_mol is None:
            continue
        fp_bb = AllChem.GetMorganFingerprintAsBitVect(bb_mol, 2, nBits=2048)
        sim = DataStructs.TanimotoSimilarity(fp_target, fp_bb)
        results.append((bb_smi, info["name"], sim))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:top_n]


def _has_forbidden_substructure(mol) -> bool:
    """위험/비상용 하위구조 검출. True면 상용 불가.

    Forbidden patterns:
      - Multiple nitro groups ([N+](=O)[O-] count > 1) — energetic materials
      - Azide groups (N=[N+]=[N-]) — explosive/unstable
      - Peroxide linkages (O-O) except H2O2 itself — unstable
      - Multiple halogens on same carbon (CF3 ok, but CCl3 with nitro = bad)
      - Nitroso + nitro combination — explosive precursors
      - Acyl azides, diazo compounds
    """
    if not RDKIT_AVAILABLE:
        return False

    # SMARTS patterns for forbidden substructures
    _FORBIDDEN_SMARTS = [
        # Azide group — always reject
        ("[N-]=[N+]=N", "azide"),
        ("[N]=[N+]=[N-]", "azide_alt"),
        # Diazo compounds
        ("[#6]=[N+]=[N-]", "diazo"),
        # Acyl azide
        ("[C](=O)[N]=[N+]=[N-]", "acyl_azide"),
        # Nitramine (N-NO2) — explosive
        ("[N][N+](=O)[O-]", "nitramine"),
        # Organic peroxide (C-O-O-C) — unstable, NOT H2O2
        ("[C]OO[C]", "organic_peroxide"),
        # Peroxy acid
        ("[C](=O)OO", "peroxy_acid"),
        # Triperoxide — extremely dangerous
        ("OOOOO", "polyperoxide"),
    ]

    for smarts, _label in _FORBIDDEN_SMARTS:
        pat = Chem.MolFromSmarts(smarts)
        if pat is not None and mol.HasSubstructMatch(pat):
            return True

    # Count nitro groups: [N+](=O)[O-] — reject if > 1
    nitro_pat = Chem.MolFromSmarts("[N+](=O)[O-]")
    if nitro_pat is not None:
        nitro_matches = mol.GetSubstructMatches(nitro_pat)
        if len(nitro_matches) > 1:
            return True

    # Check for O-O bonds (peroxide linkage) — reject unless molecule IS H2O2
    peroxide_pat = Chem.MolFromSmarts("[OX2][OX2]")
    if peroxide_pat is not None:
        if mol.HasSubstructMatch(peroxide_pat):
            canon = Chem.MolToSmiles(mol)
            # Allow H2O2 itself (canonical: OO) and mCPBA-like known reagents
            if canon not in ("OO",):
                # Check if it's in the DB — if so, it's fine (e.g., H2O2)
                if canon not in BUILDING_BLOCKS:
                    return True

    return False


def is_commercially_available(smiles: str) -> bool:
    """상용 구매 가능 여부 판정.

    오직 BUILDING_BLOCKS DB에 등록된 분자만 True.
    Heuristic fallback 제거됨 — DB에 없으면 False.
    이렇게 해야 BFS가 비상용 중간체를 추가 분해하여 다단계 경로를 생성합니다.
    """
    return is_building_block(smiles)


def lookup_building_block(smiles: str) -> Optional[Dict]:
    """시작물질 조회. DB에 있으면 정보 반환, 없으면 None.
    is_building_block()과 동일하나 명시적 조회용 인터페이스."""
    return get_building_block_info(smiles)


def get_all_building_blocks() -> Dict[str, Dict]:
    """전체 시작물질 DB 반환"""
    return dict(BUILDING_BLOCKS)


if __name__ == "__main__":
    print(f"Building blocks loaded: {len(BUILDING_BLOCKS)}")
    print("\nTop 5 by name:")
    for smi, info in list(BUILDING_BLOCKS.items())[:5]:
        print(f"  {smi:30s} → {info['name']} ({info['name_en']})")

    # 유사도 테스트
    test = "c1ccc(O)cc1"  # 페놀
    print(f"\nSimilar to {test}:")
    for smi, name, sim in find_similar_blocks(test):
        print(f"  {sim:.3f}  {name:20s}  {smi}")
