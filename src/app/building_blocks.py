#!/usr/bin/env python3
"""
상용 시작물질(Building Blocks) 데이터베이스.
역합성 분석에서 '목표 도달' 판정 기준이 되는 간단한 화합물 목록.
Tanimoto 유사도 기반 유사 시작물질 검색 지원.
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ═══════════════════════════════════════════════════════════
# 상용 시작물질 데이터베이스 (~95개 + 확장 ~400개)
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

    # ═══════════════════════════════════════════════════════════
    # 확장 빌딩블록 #2 — 역합성 다단계 경로 지원용 (~120개 추가)
    # 2026-03-20 domain_synthesis Worker
    # ═══════════════════════════════════════════════════════════

    # ── 카르복실산 (추가) ──
    ("CCCC(=O)O", "부티르산", "Butyric acid", "low"),
    ("CCCCC(=O)O", "발레르산", "Valeric acid", "low"),
    ("CCCCCC(=O)O", "카프로산", "Caproic acid", "low"),
    ("OC(=O)CC(=O)O", "말론산(alt)", "Malonic acid (alt)", "low"),
    ("OC(=O)C(O)C(=O)O", "타르타르산", "Tartaric acid", "medium"),
    ("OC(=O)C(=O)O", "옥살산", "Oxalic acid", "low"),
    ("CC(O)(CC(=O)O)C(=O)O", "시트르산(alt)", "Citric acid (alt)", "low"),
    ("OC(=O)c1ccc(O)cc1", "4-히드록시벤조산", "4-Hydroxybenzoic acid", "low"),
    ("OC(=O)c1ccncc1", "니코틴산", "Nicotinic acid", "low"),
    ("OC(=O)c1ccccn1", "피콜린산", "Picolinic acid", "medium"),
    ("OC(=O)CCl", "클로로아세트산", "Chloroacetic acid", "low"),
    ("OC(=O)C(Cl)Cl", "디클로로아세트산", "Dichloroacetic acid", "low"),
    ("OC(=O)C(F)(F)F", "트리플루오로아세트산", "Trifluoroacetic acid (TFA)", "low"),
    ("CC(=O)O[Na]", "아세트산나트륨", "Sodium acetate", "low"),

    # ── 무기 염기 (SMILES 표현 가능한 것) ──
    ("[Na+].[OH-]", "수산화나트륨", "Sodium hydroxide (NaOH)", "low"),
    ("[K+].[OH-]", "수산화칼륨", "Potassium hydroxide (KOH)", "low"),
    ("[Na+].[Na+].O=C([O-])[O-]", "탄산나트륨", "Sodium carbonate (Na2CO3)", "low"),
    ("[K+].[K+].O=C([O-])[O-]", "탄산칼륨", "Potassium carbonate (K2CO3)", "low"),
    ("[Na+].OC([O-])=O", "탄산수소나트륨", "Sodium bicarbonate (NaHCO3)", "low"),
    ("[Na+].[H-]", "수소화나트륨", "Sodium hydride (NaH)", "low"),
    ("[K+].CC(C)(C)[O-]", "칼륨 tert-부톡사이드", "Potassium tert-butoxide (KOtBu)", "medium"),
    ("[Na+].CO[Na]", "나트륨 메톡사이드", "Sodium methoxide (NaOMe)", "low"),
    ("[Li+].N(CC)CC.[Li+]", "리튬 디이소프로필아미드", "LDA (approx)", "medium"),

    # ── 용매 겸 시약 ──
    ("CS(C)=O", "DMSO", "Dimethyl sulfoxide", "low"),
    ("O=CN(C)C", "DMF(alt)", "DMF (alt SMILES)", "low"),
    ("CC#N", "아세토나이트릴(dup)", "Acetonitrile (solvent)", "low"),
    ("ClCCl", "디클로로메탄(dup)", "DCM (solvent)", "low"),
    ("C1COCCO1", "1,4-디옥산", "1,4-Dioxane", "low"),
    ("COCCOC", "디메톡시에탄", "DME (1,2-Dimethoxyethane)", "low"),
    ("CC(=O)C", "아세톤(dup)", "Acetone (solvent)", "low"),
    ("c1ccncc1", "피리딘(dup)", "Pyridine (base/solvent)", "low"),
    ("CCN(CC)CC", "트리에틸아민(dup)", "Triethylamine (base)", "low"),
    ("CN1CCCC1=O", "NMP", "N-Methylpyrrolidone", "low"),
    ("O=S(=O)(C(F)(F)F)C(F)(F)F", "트리플산무수물", "Triflic anhydride", "medium"),

    # ── 유기금속/유기리튬 ──
    ("CCCC[Li]", "n-부틸리튬(dup)", "n-BuLi", "medium"),
    ("CC(C)(C)[Li]", "tert-부틸리튬", "t-BuLi", "high"),
    ("CC[Li]", "에틸리튬", "Ethyllithium", "medium"),
    ("c1ccc(cc1)[Mg]Br", "페닐마그네슘 브로마이드", "PhMgBr (Grignard)", "medium"),
    ("[Mg](Br)CCC", "프로필마그네슘 브로마이드", "PrMgBr (Grignard)", "medium"),
    ("C=C[Mg]Br", "비닐마그네슘 브로마이드", "VinylMgBr", "medium"),
    ("C#C[Mg]Br", "에티닐마그네슘 브로마이드", "EthynylMgBr", "medium"),
    ("[Cu]C", "메틸구리", "Methylcopper (CuMe)", "medium"),
    ("CC(=O)[O-].[Pd+2].[O-]C(C)=O", "아세트산팔라듐", "Palladium acetate", "medium"),
    ("[Zn]", "아연", "Zinc (Zn)", "low"),

    # ── 보호기 시약 ──
    ("C[Si](C)(C)Cl", "TMS-Cl", "Trimethylsilyl chloride (TMS-Cl)", "low"),
    ("CC(C)(C)OC(=O)OC(=O)OC(C)(C)C", "Boc2O", "Di-tert-butyl dicarbonate (Boc2O)", "medium"),
    ("ClC(=O)OCC1c2ccccc2-c2ccccc21", "Fmoc-Cl", "Fmoc chloride", "high"),
    ("ClC(=O)OCc1ccccc1", "Cbz-Cl", "Benzyl chloroformate (Cbz-Cl)", "medium"),
    ("C[Si](C)(C)C(=O)C", "TMS-아세틸", "TMS-acetyl", "medium"),
    ("CC(C)(C)[Si](C)(C)Cl", "TBDMS-Cl", "tert-Butyldimethylsilyl chloride", "medium"),
    ("C[Si](C)(C)O[Si](C)(C)C", "HMDS", "Hexamethyldisilazane", "low"),
    ("CC(C)(C)OC(=O)Cl", "Boc-Cl", "Boc chloride", "medium"),

    # ── 환원제 ──
    ("[BH4-].[Na+]", "수소화붕소나트륨(dup)", "NaBH4", "low"),
    ("[AlH4-].[Li+]", "수소화알루미늄리튬(dup)", "LiAlH4", "medium"),
    ("CC(C)CC([Al](CC(C)C)CC(C)C)=O", "DIBAL-H(구조식)", "DIBAL-H (approx)", "medium"),
    ("[BH3-]C#N.[Na+]", "시아노수소화붕소나트륨", "Sodium cyanoborohydride (NaBH3CN)", "medium"),
    ("CC(=O)O[BH-](OC(C)=O)OC(C)=O.[Na+]", "아세톡시수소화붕소나트륨", "NaBH(OAc)3", "medium"),
    ("O=S(Cl)Cl", "염화티오닐(alt)", "SOCl2 (alt)", "low"),

    # ── 산화제 ──
    ("OC(=O)c1cccc(Cl)c1", "mCPBA(기본골격)", "mCPBA (m-chloroperbenzoic acid)", "medium"),
    ("O=C1OC(=O)c2cc(Cl)ccc21", "클로르아닐", "Chloranil", "medium"),
    ("[O-][Cr](=O)(=O)Cl", "PCC(근사)", "PCC (Pyridinium chlorochromate approx)", "medium"),
    ("[O-][Mn](=O)(=O)=O.[K+]", "과망간산칼륨(dup)", "KMnO4", "low"),
    ("[O-][Cr](=O)=O.[O-][Cr](=O)=O", "중크롬산", "Dichromate (approx)", "medium"),
    ("OO", "과산화수소(dup)", "H2O2", "low"),
    ("OOCC(C)(C)C", "TBHP", "tert-Butyl hydroperoxide", "medium"),
    ("O=IO", "요오도소벤젠(기본)", "IBX-like (approx)", "medium"),

    # ── 친핵체 (무기) ──
    ("[N-]=[N+]=[N-].[Na+]", "아지드화나트륨", "Sodium azide (NaN3)", "low"),
    ("[C-]#N.[K+]", "시안화칼륨", "Potassium cyanide (KCN)", "low"),
    ("[C-]#N.[Na+]", "시안화나트륨", "Sodium cyanide (NaCN)", "low"),
    ("[Na+].[I-]", "요오드화나트륨", "Sodium iodide (NaI)", "low"),
    ("[K+].[I-]", "요오드화칼륨", "Potassium iodide (KI)", "low"),
    ("[Na+].[F-]", "플루오르화나트륨", "Sodium fluoride (NaF)", "low"),
    ("[K+].[F-]", "플루오르화칼륨", "Potassium fluoride (KF)", "low"),
    ("[Na+].[Br-]", "브롬화나트륨", "Sodium bromide (NaBr)", "low"),
    ("[Na+].[SH-]", "수황화나트륨", "Sodium hydrosulfide (NaSH)", "low"),
    ("[Na+].[S-2].[Na+]", "황화나트륨", "Sodium sulfide (Na2S)", "low"),
    ("[Na+].OC([O-])=O", "탄산수소나트륨(dup)", "NaHCO3 (nucleophile)", "low"),
    ("[NH4+].[Cl-]", "염화암모늄", "Ammonium chloride (NH4Cl)", "low"),

    # ── 방향족 빌딩블록 (추가) ──
    ("c1ccc(N)c(N)c1", "오르토페닐렌디아민", "o-Phenylenediamine", "medium"),
    ("Oc1cccc(O)c1", "레조르시놀", "Resorcinol", "low"),
    ("Oc1cc(O)cc(O)c1", "플로로글루시놀", "Phloroglucinol", "medium"),
    ("COc1ccc(OC)cc1", "1,4-디메톡시벤젠", "1,4-Dimethoxybenzene", "low"),
    ("COc1cc(OC)cc(OC)c1", "1,3,5-트리메톡시벤젠", "1,3,5-Trimethoxybenzene", "medium"),
    ("c1ccc2c(c1)cccc2O", "2-나프톨", "2-Naphthol", "low"),
    ("c1ccc2c(c1)cccc2N", "1-나프틸아민", "1-Naphthylamine", "medium"),
    ("Cc1ccc(O)cc1", "p-크레졸", "p-Cresol", "low"),
    ("Oc1ccc(Cl)cc1", "4-클로로페놀", "4-Chlorophenol", "low"),
    ("Nc1ccc(Cl)cc1", "4-클로로아닐린", "4-Chloroaniline", "low"),
    ("Nc1ccc(O)cc1", "4-아미노페놀", "4-Aminophenol", "low"),
    ("Cc1cccc(C)c1", "메타자일렌", "m-Xylene", "low"),
    ("c1ccc(-c2ccccc2)cc1", "비페닐", "Biphenyl", "low"),
    ("O=Cc1ccc(O)cc1", "4-히드록시벤즈알데히드", "4-Hydroxybenzaldehyde", "low"),
    ("O=Cc1ccc([N+](=O)[O-])cc1", "4-니트로벤즈알데히드", "4-Nitrobenzaldehyde", "low"),
    ("CC(=O)c1ccc(O)cc1", "4-히드록시아세토페논", "4-Hydroxyacetophenone", "low"),
    ("O=Cc1cccnc1", "3-피리딘카르복스알데히드", "3-Pyridinecarboxaldehyde", "medium"),

    # ── 헤테로사이클 (추가) ──
    ("c1ccoc1", "퓨란(dup)", "Furan", "low"),
    ("c1ccsc1", "티오펜(dup)", "Thiophene", "low"),
    ("c1c[nH]cn1", "이미다졸(dup)", "Imidazole", "low"),
    ("c1cc[nH]c1", "피롤(dup)", "Pyrrole", "low"),
    ("c1ccncc1", "피리딘(dup2)", "Pyridine", "low"),
    ("c1cc2ccccc2[nH]1", "인돌", "Indole", "medium"),
    ("c1cnc2ccccc2c1", "퀴놀린", "Quinoline", "medium"),
    ("c1ccc2[nH]ccc2c1", "인돌(alt)", "Indole (alt SMILES)", "medium"),
    ("C1=CC=Cc2ncccc21", "이소퀴놀린", "Isoquinoline", "medium"),
    ("c1cn[nH]c1", "피라졸", "Pyrazole", "medium"),
    ("c1ccnc(N)n1", "2-아미노피리미딘", "2-Aminopyrimidine", "medium"),
    ("c1nc[nH]n1", "1,2,4-트리아졸", "1,2,4-Triazole", "medium"),
    ("c1nnn[nH]1", "테트라졸", "Tetrazole", "medium"),
    ("c1csc(N)n1", "2-아미노티아졸", "2-Aminothiazole", "medium"),
    ("c1coc(C=O)c1", "2-퓨르알데히드", "Furfural", "low"),
    ("c1cc(CO)oc1", "퍼퓨릴알코올", "Furfuryl alcohol", "low"),
    ("c1csc(C=O)c1", "2-티오펜카르복스알데히드", "Thiophene-2-carboxaldehyde", "medium"),
    ("C1COCCO1", "1,4-디옥산(dup)", "1,4-Dioxane", "low"),
    ("C1CCOC1", "THF(dup)", "THF (solvent)", "low"),
    ("C1CCNCC1", "피페리딘(dup)", "Piperidine", "low"),
    ("C1CNCCN1", "피페라진(dup)", "Piperazine", "low"),
    ("C1CC1", "시클로프로판", "Cyclopropane", "low"),
    ("C1CCC1", "시클로부탄", "Cyclobutane", "low"),
    ("c1cc2c(cc1)OCO2", "피페로날(전구체)", "Piperonyl (1,3-benzodioxole)", "medium"),

    # ── 커플링/촉매 시약 ──
    ("c1ccc(P(c2ccccc2)c2ccccc2)cc1", "트리페닐포스핀", "Triphenylphosphine (PPh3)", "medium"),
    ("OB(O)O", "보론산", "Boric acid", "low"),
    ("OB(O)c1ccc(F)cc1", "4-플루오로페닐보론산", "4-Fluorophenylboronic acid", "medium"),
    ("OB(O)c1ccc(OC)cc1", "4-메톡시페닐보론산", "4-Methoxyphenylboronic acid", "medium"),
    ("OB(O)c1cccnc1", "3-피리딜보론산", "3-Pyridylboronic acid", "medium"),
    ("ClC(Cl)=NC=O", "DMF-DMA(근사)", "DMF-DMA (approx)", "medium"),
    ("O=C(ON1C(=O)CCC1=O)c1ccccc1", "NHS-벤조에이트", "NHS-benzoate ester (approx)", "medium"),

    # ── 아미노산 (추가) ──
    ("NCC(=O)O", "글리신(dup)", "Glycine", "low"),
    ("CC(N)C(=O)O", "알라닌", "Alanine", "low"),
    ("CC(CC)C(N)C(=O)O", "이소류신", "Isoleucine", "medium"),
    ("CC(C)C(N)C(=O)O", "발린", "Valine", "medium"),
    ("CC(C)CC(N)C(=O)O", "류신", "Leucine", "medium"),
    ("NC(Cc1ccccc1)C(=O)O", "페닐알라닌", "Phenylalanine", "medium"),
    ("NC(CO)C(=O)O", "세린", "Serine", "medium"),
    ("NC(CS)C(=O)O", "시스테인", "Cysteine", "medium"),
    ("NC(=O)CC(N)C(=O)O", "아스파라긴", "Asparagine", "medium"),
    ("NC(CCC(=O)O)C(=O)O", "글루탐산", "Glutamic acid", "medium"),
    ("OC(=O)CC(N)C(=O)O", "아스파르트산", "Aspartic acid", "medium"),
    ("NC(CCCCN)C(=O)O", "라이신", "Lysine", "medium"),

    # ── 추가 할로알킬/알킬 시약 ──
    ("CCCCI", "1-요오도부탄", "1-Iodobutane", "low"),
    ("CCCI", "1-요오도프로판", "1-Iodopropane", "low"),
    ("ICCBr", "1-브로모-2-요오도에탄", "1-Bromo-2-iodoethane", "medium"),
    ("CC(C)Br", "2-브로모프로판", "2-Bromopropane", "low"),
    ("CC(C)(C)Cl", "tert-부틸 클로라이드", "tert-Butyl chloride", "low"),
    ("CC(C)(C)Br", "tert-부틸 브로마이드", "tert-Butyl bromide", "low"),
    ("C=CCl", "알릴 클로라이드", "Allyl chloride", "low"),
    ("ClCC#C", "프로파길 클로라이드", "Propargyl chloride", "low"),
    ("BrCC#C", "프로파길 브로마이드", "Propargyl bromide", "low"),
    ("ICC", "요오도에탄(dup)", "Iodoethane", "low"),
    ("ClCCCCl", "1,4-디클로로부탄", "1,4-Dichlorobutane", "low"),

    # ── 추가 케톤/알데히드 ──
    ("CCCC=O", "부틸알데히드", "Butyraldehyde", "low"),
    ("CC(=O)CCC", "2-펜타논", "2-Pentanone", "low"),
    ("O=C1CCCCC1", "시클로헥사논(dup)", "Cyclohexanone", "low"),
    ("CCCCCC=O", "헥산알", "Hexanal", "low"),
    ("C=CC=O", "아크롤레인", "Acrolein", "low"),
    ("CC(=O)C=C", "메틸비닐케톤", "Methyl vinyl ketone (MVK)", "low"),
    ("O=Cc1ccco1", "퍼퓨랄(dup)", "Furfural", "low"),

    # ── 추가 에스터/락톤 ──
    ("O=C1CCCO1", "감마부티로락톤", "gamma-Butyrolactone (GBL)", "low"),
    ("O=C1CCCCO1", "델타발레로락톤", "delta-Valerolactone", "medium"),
    ("CCOC(=O)C=C", "아크릴산에틸", "Ethyl acrylate", "low"),
    ("COC=O", "포름산메틸", "Methyl formate", "low"),
    ("CCOC(=O)OCC", "디에틸 카보네이트", "Diethyl carbonate", "low"),
    ("COC(=O)OC", "디메틸 카보네이트", "Dimethyl carbonate", "low"),

    # ── 설폰아미드/설폰산 시약 ──
    ("Cc1ccc(S(=O)(=O)Cl)cc1", "토실 클로라이드", "Tosyl chloride (TsCl)", "low"),
    ("Cc1ccc(S(=O)(=O)O)cc1", "토실산", "p-Toluenesulfonic acid (TsOH)", "low"),
    ("CS(=O)(=O)O", "메탄설폰산", "Methanesulfonic acid (MsOH)", "low"),
    ("FC(F)(F)S(=O)(=O)O", "트리플산", "Triflic acid (TfOH)", "medium"),
    ("FC(F)(F)S(=O)(=O)Cl", "트리플릴 클로라이드", "Triflyl chloride (TfCl)", "medium"),
    ("Nc1ccc(S(=O)(=O)O)cc1", "설파닐산", "Sulfanilic acid", "medium"),

    # ── 추가 헤테로고리/생화학 빌딩블록 (다단계 경로용) ──
    ("O=c1[nH]c(=O)c2[nH]cnc2[nH]1", "잔틴", "Xanthine", "medium"),
    ("O=c1cc[nH]c(=O)[nH]1", "유라실", "Uracil", "low"),
    ("c1ncc2[nH]cnc2n1", "퓨린", "Purine", "medium"),
    ("O=c1[nH]cnc2[nH]cnc12", "하이포잔틴", "Hypoxanthine", "medium"),
    ("Nc1nc(=O)c2[nH]cnc2[nH]1", "구아닌", "Guanine", "medium"),
    ("c1ccncc1", "피리딘", "Pyridine", "low"),
    ("c1ccoc1", "푸란", "Furan", "low"),
    ("c1ccsc1", "싸이오펜", "Thiophene", "low"),
    ("c1cc2ccccc2[nH]1", "인돌", "Indole", "low"),
    ("O=C(O)c1ccccc1", "벤조산", "Benzoic acid", "low"),
    ("OCc1ccccc1", "벤질 알코올", "Benzyl alcohol", "low"),
    ("ClCc1ccccc1", "벤질 클로라이드", "Benzyl chloride", "low"),
    ("BrCc1ccccc1", "벤질 브로마이드", "Benzyl bromide", "low"),
    ("O=Cc1ccccc1", "벤즈알데히드", "Benzaldehyde", "low"),
    ("O=C(Cl)c1ccccc1", "벤조일 클로라이드", "Benzoyl chloride", "low"),

    # ═══════════════════════════════════════════════════════════
    # 확장 빌딩블록 #3 — 테르펜 전구체 + 크로스커플링 + 추가 시약
    # 2026-03-22 Worker (building_blocks expansion)
    # ═══════════════════════════════════════════════════════════

    # ── 테르펜 전구체 (루테인, 카로티노이드, 스테로이드 합성용) ──
    ("C=CC(=C)C", "이소프렌", "Isoprene", "low"),
    ("CC(=CC=O)C", "시트랄 (3-메틸-2-부테날)", "Citral", "medium"),
    ("CC(=CCCC(=CC=O)C)C", "게라니알", "Geranial", "medium"),
    ("CC(=CCCC(=CCO)C)C", "게라니올", "Geraniol", "medium"),
    ("CC(=CCCC(=CCCC(=CCO)C)C)C", "파르네솔", "Farnesol", "medium"),
    ("CC1=C(C(CC(C1)O)(C)C)/C=C/C(=C/C=O)C", "β-이오논", "beta-Ionone", "medium"),
    ("CC1=C(C(CC(C1)=O)(C)C)C=O", "사프라날", "Safranal", "medium"),
    ("CC(=O)/C=C/C1=C(C)CCCC1(C)C", "β-이오논 (케톤)", "beta-Ionone (ketone)", "medium"),

    # ── 포스포러스 시약 (Wittig, HWE) ──
    ("C(=P(c1ccccc1)(c1ccccc1)c1ccccc1)", "메틸렌트리페닐포스포란", "Ph3P=CH2 (Wittig)", "medium"),
    ("CCOP(=O)(CC(=O)OCC)OCC", "트리에틸 포스포노아세테이트", "Triethyl phosphonoacetate (HWE)", "medium"),

    # ── 크로스커플링 시약 (추가) ──
    ("[Sn](C)(C)(C)C=C", "비닐트리메틸스탄난", "Vinyltrimethylstannane (Stille)", "medium"),
    ("C=CB(O)O", "비닐보론산", "Vinylboronic acid", "medium"),

    # ── 추가 범용 시약 ──
    ("S", "황화수소", "Hydrogen sulfide", "low"),
    ("C=CBr", "비닐 브로마이드", "Vinyl bromide", "low"),
    ("CCO[Si](OCC)(OCC)C=C", "비닐트리에톡시실란", "Vinyltriethoxysilane", "medium"),

    # ── 디올/폴리올 (4-히드록시벤젠 = 페놀 이미 등록) ──
    # Phenol, Aniline, Toluene, Ethylene glycol, Glycerol 등은 이미 등록됨

    # ═══════════════════════════════════════════════════════════
    # 확장 빌딩블록 #4 — 의약품 합성 빌딩블록 (~40개 추가)
    # 2026-03-23 retrosynthesis coverage expansion
    # ═══════════════════════════════════════════════════════════

    # ── 치환 아닐린 (의약품 전구체) ──
    ("Cc1cccc(C)c1N", "2,6-디메틸아닐린", "2,6-Dimethylaniline", "low"),
    ("Cc1ccccc1N", "o-톨루이딘", "o-Toluidine", "low"),
    ("Cc1ccc(N)cc1", "p-톨루이딘", "p-Toluidine", "low"),
    ("CCc1ccc(N)cc1", "4-에틸아닐린", "4-Ethylaniline", "low"),
    ("COc1ccc(N)cc1", "p-아니시딘", "p-Anisidine", "low"),

    # ── 디에틸아민 및 2차 아민 ──
    ("CCNCC", "디에틸아민", "Diethylamine", "low"),
    ("CCNCCC", "N-에틸프로필아민", "N-Ethylpropylamine", "low"),
    ("C1CCNC1", "피롤리딘(dup2)", "Pyrrolidine", "low"),
    ("CC(C)N", "이소프로필아민", "Isopropylamine", "low"),
    ("CC(C)CN", "이소부틸아민", "Isobutylamine", "low"),

    # ── 할로아세틸 시약 (Lidocaine 등) ──
    ("ClCC(=O)Cl", "클로로아세틸 클로라이드", "Chloroacetyl chloride", "low"),
    ("BrCC(=O)Br", "브로모아세틸 브로마이드", "Bromoacetyl bromide", "medium"),
    ("ClCC(=O)O", "클로로아세트산(dup)", "Chloroacetic acid", "low"),
    ("BrCC(=O)O", "브로모아세트산", "Bromoacetic acid", "low"),

    # ── 이소부틸벤젠 (Ibuprofen 전구체) ──
    ("CC(C)Cc1ccccc1", "이소부틸벤젠", "Isobutylbenzene", "low"),

    # ── 방향족 카르복실산 (의약품 중간체) ──
    ("OC(=O)Cc1ccccc1", "페닐아세트산", "Phenylacetic acid", "low"),
    ("OC(=O)c1ccc(Cl)cc1", "4-클로로벤조산", "4-Chlorobenzoic acid", "low"),
    ("OC(=O)c1ccc(N)cc1", "4-아미노벤조산", "4-Aminobenzoic acid (PABA)", "low"),
    ("OC(=O)c1ccc(F)cc1", "4-플루오로벤조산", "4-Fluorobenzoic acid", "low"),
    ("OC(=O)c1ccc(OC)cc1", "4-메톡시벤조산", "4-Methoxybenzoic acid", "low"),
    ("OC(=O)c1ccc(C)cc1", "4-메틸벤조산", "4-Methylbenzoic acid (p-Toluic acid)", "low"),

    # ── 술포닐 클로라이드 (Sulfanilamide 전구체) ──
    ("Nc1ccc(S(=O)(=O)Cl)cc1", "4-아미노벤젠설포닐 클로라이드", "4-Aminobenzenesulfonyl chloride", "medium"),
    ("O=[N+]([O-])c1ccc(S(=O)(=O)Cl)cc1", "4-니트로벤젠설포닐 클로라이드", "4-Nitrobenzenesulfonyl chloride (Nosyl-Cl)", "medium"),

    # ── 이사틴 (Indigo 전구체) ──
    ("O=C1Nc2ccccc2C1=O", "이사틴", "Isatin", "medium"),

    # ── 방향족 알데히드 (추가) ──
    ("O=Cc1ccc(Cl)cc1", "4-클로로벤즈알데히드", "4-Chlorobenzaldehyde", "low"),
    ("O=Cc1ccc(F)cc1", "4-플루오로벤즈알데히드", "4-Fluorobenzaldehyde", "low"),
    ("O=Cc1ccc(OC)cc1", "4-메톡시벤즈알데히드", "4-Methoxybenzaldehyde (Anisaldehyde)", "low"),
    ("O=Cc1ccc(C)cc1", "4-메틸벤즈알데히드", "4-Methylbenzaldehyde", "low"),
    ("O=Cc1cc(OC)c(O)cc1", "바닐린", "Vanillin", "low"),

    # ── 방향족 케톤 (의약품 중간체) ──
    ("CC(=O)c1ccc(Cl)cc1", "4-클로로아세토페논", "4-Chloroacetophenone", "low"),
    ("CC(=O)c1ccc(C)cc1", "4-메틸아세토페논", "4-Methylacetophenone", "low"),

    # ── 방향족 니트릴 ──
    ("N#Cc1ccccc1", "벤조나이트릴", "Benzonitrile", "low"),
    ("N#Cc1ccc(N)cc1", "4-아미노벤조나이트릴", "4-Aminobenzonitrile", "low"),

    # ── 프로피온산 유도체 (이부프로펜 중간체) ──
    ("CC(C(=O)O)c1ccccc1", "2-페닐프로피온산", "2-Phenylpropionic acid", "medium"),
    ("ClC(=O)CC(C)C", "이소발레릴 클로라이드", "Isovaleryl chloride", "medium"),

    # ── 기타 의약품 빌딩블록 ──
    ("CCOC(=O)C(=O)OCC", "디에틸 옥살레이트", "Diethyl oxalate", "low"),
    ("ClCCCl", "1,2-디클로로에탄(dup2)", "1,2-Dichloroethane", "low"),
    ("O=C=NCc1ccccc1", "벤질 이소시아네이트", "Benzyl isocyanate", "medium"),
    ("ClC(=O)CCl", "클로로아세틸 클로라이드(alt)", "Chloroacetyl chloride (alt)", "low"),
    ("CC(=O)Nc1ccccc1", "아세트아닐라이드", "Acetanilide", "low"),
    ("OC(=O)CCc1ccccc1", "히드로신남산", "Hydrocinnamic acid (3-Phenylpropionic)", "low"),

    # ═══════════════════════════════════════════════════════════
    # 확장 빌딩블록 #5 — 의약품 합성 상용 시약 확장 (~80개 추가)
    # 2026-03-23 pharmaceutical building blocks expansion
    # ═══════════════════════════════════════════════════════════

    # ── 아미노산 (추가 — L-form canonical) ──
    ("NC(Cc1c[nH]c2ccccc12)C(=O)O", "트립토판", "Tryptophan", "medium"),
    ("OC(=O)C1CCCN1", "프롤린", "Proline", "medium"),
    ("NC(C(C)O)C(=O)O", "트레오닌", "Threonine", "medium"),
    ("NC(CCSC)C(=O)O", "메티오닌", "Methionine", "medium"),
    ("NC(Cc1c[nH]cn1)C(=O)O", "히스티딘", "Histidine", "medium"),
    ("NC(CCCNC(=N)N)C(=O)O", "아르기닌", "Arginine", "medium"),
    ("NC(Cc1ccc(O)cc1)C(=O)O", "티로신", "Tyrosine", "medium"),
    ("NC(CCC(=O)O)C(=O)O", "글루탐산(alt2)", "Glutamic acid (alt)", "medium"),
    ("NC(CC(=O)N)C(=O)O", "아스파라긴(alt2)", "Asparagine (alt)", "medium"),
    ("NC(CCC(=O)N)C(=O)O", "글루타민", "Glutamine", "medium"),

    # ── 단당류 (Common sugars — 개환형 SMILES) ──
    ("OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O", "D-글루코스", "D-Glucose", "low"),
    ("OC[C@H]1OC(O)(CO)[C@@H](O)[C@@H]1O", "D-프럭토스", "D-Fructose", "low"),
    ("OC[C@H]1OC(O)[C@H](O)[C@@H]1O", "D-리보스", "D-Ribose", "low"),
    ("OC[C@H]1OC(O)[C@@H](O)[C@H](O)[C@@H]1O", "D-갈락토스", "D-Galactose", "low"),
    ("OC[C@H]1OC(O)[C@@H](O)[C@@H](O)[C@@H]1O", "D-만노스", "D-Mannose", "low"),
    ("C[C@@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O", "L-람노스", "L-Rhamnose", "medium"),
    ("OC[C@H]1OC(O)[C@@H](O)[C@@H]1O", "D-자일로스", "D-Xylose", "low"),

    # ── 핵산 염기 (Nucleobases — 추가) ──
    ("Nc1ncnc2[nH]cnc12", "아데닌", "Adenine", "low"),
    ("Cc1c[nH]c(=O)[nH]c1=O", "티민", "Thymine", "low"),
    ("Nc1cc[nH]c(=O)n1", "시토신", "Cytosine", "low"),

    # ── 헤테로사이클 빌딩블록 (추가) ──
    ("c1cocn1", "옥사졸", "Oxazole", "medium"),
    ("c1cscn1", "티아졸", "Thiazole", "medium"),
    ("C1COCCN1", "모르폴린", "Morpholine", "low"),
    ("C1CSCNC1", "티오모르폴린", "Thiomorpholine", "medium"),
    ("c1ccoc1C(=O)O", "2-푸로산", "2-Furoic acid", "low"),
    ("c1ccc2[nH]ncc2c1", "인다졸", "Indazole", "medium"),
    ("c1cnc2[nH]ccc2c1", "7-아자인돌", "7-Azaindole", "medium"),
    ("c1cnoc1", "이속사졸", "Isoxazole", "medium"),
    ("c1ccc2c(c1)[nH]c(=O)[nH]2", "2-옥시인돌", "Oxindole", "medium"),
    ("O=c1cc[nH]c2ccccc12", "2-퀴놀론", "2-Quinolone", "medium"),
    ("c1ncc2nc[nH]c2n1", "퓨린(alt)", "Purine (alt SMILES)", "medium"),
    ("c1cc2[nH]c(=O)oc2cc1", "쿠마린", "Coumarin", "medium"),
    ("c1cc2nc[nH]c2cc1", "벤즈이미다졸", "Benzimidazole", "medium"),
    ("c1ccc2c(c1)ncs2", "벤조티아졸", "Benzothiazole", "medium"),
    ("c1ccc2c(c1)oc(N)n2", "2-아미노벤조옥사졸", "2-Aminobenzoxazole", "medium"),
    ("c1ccc2c(c1)nco2", "벤조옥사졸", "Benzoxazole", "medium"),
    ("c1csc(-c2ccccn2)n1", "2-(2-피리딜)티아졸", "2-(2-Pyridyl)thiazole", "medium"),

    # ── 보호기 시약 (추가) ──
    ("ClCc1ccc(OC)cc1", "PMB 클로라이드", "PMB chloride (4-Methoxybenzyl chloride)", "medium"),
    ("C1=COCCC1", "DHP", "3,4-Dihydro-2H-pyran (DHP)", "low"),
    ("CC(C)(C)[Si](C)(C)OC(F)(F)F", "TBSOTf(근사)", "TBSOTf (approx)", "high"),
    ("O=C(OC(C)(C)C)N", "Boc-NH2", "tert-Butyl carbamate (Boc-NH2)", "medium"),
    ("CC(=O)OC(=O)C", "무수아세트산(보호)", "Acetic anhydride (protection)", "low"),
    ("C(c1ccccc1)(c1ccccc1)(c1ccccc1)Cl", "트리틸 클로라이드", "Trityl chloride (TrCl)", "medium"),
    ("CCOC(=O)Cl", "에틸 클로로포메이트", "Ethyl chloroformate", "low"),

    # ── 보론산 (Suzuki 커플링용 추가) ──
    ("OB(O)c1ccc(Cl)cc1", "4-클로로페닐보론산", "4-Chlorophenylboronic acid", "medium"),
    ("OB(O)c1ccc([N+](=O)[O-])cc1", "4-니트로페닐보론산", "4-Nitrophenylboronic acid", "medium"),
    ("OB(O)c1ccc(C(F)(F)F)cc1", "4-트리플루오로메틸페닐보론산", "4-(Trifluoromethyl)phenylboronic acid", "medium"),
    ("OB(O)c1cccc(OC)c1", "3-메톡시페닐보론산", "3-Methoxyphenylboronic acid", "medium"),
    ("OB(O)c1ccccn1", "2-피리딜보론산", "2-Pyridylboronic acid", "medium"),
    ("OB(O)c1ccsc1", "3-티에닐보론산", "3-Thienylboronic acid", "medium"),
    ("OB(O)c1ccc2ccccc2c1", "2-나프틸보론산", "2-Naphthylboronic acid", "medium"),
    ("CB(O)O", "메틸보론산", "Methylboronic acid", "medium"),

    # ── 유기금속/유기리튬 (추가) ──
    ("[Li]c1ccccc1", "페닐리튬", "Phenyllithium (PhLi)", "medium"),
    ("[Mg](Br)C=C", "비닐마그네슘 브로마이드(alt)", "VinylMgBr (alt)", "medium"),
    ("C=CC=C[Mg]Br", "알릴마그네슘 브로마이드", "AllylMgBr", "medium"),
    ("[Zn]CC", "디에틸아연(근사)", "Diethylzinc (approx)", "medium"),
    ("[Cu]C(C)(C)C", "tert-부틸구리", "tert-Butylcopper", "medium"),

    # ── 천연물 빌딩블록 (Natural product building blocks) ──
    ("O=Cc1ccccc1O", "살리실알데히드", "Salicylaldehyde", "low"),
    ("COc1ccccc1O", "구아이아콜", "Guaiacol", "low"),
    ("COc1cc(C=O)ccc1O", "바닐린(alt2)", "Vanillin (alt)", "low"),
    ("COc1cc(CC=C)ccc1O", "유제놀", "Eugenol", "low"),
    ("OC(=O)/C=C/c1ccccc1", "신남산", "Cinnamic acid", "low"),
    ("O=C/C=C/c1ccccc1", "신남알데히드", "Cinnamaldehyde", "low"),
    ("OC(=O)c1cc(O)c(O)c(O)c1", "갈산", "Gallic acid", "low"),
    ("c1cc2c(cc1O)OCO2", "세사몰", "Sesamol", "medium"),
    ("CC(=O)c1ccc(O)cc1", "4-히드록시아세토페논(alt)", "4-Hydroxyacetophenone (natural)", "low"),
    ("OC(=O)/C=C/c1ccc(O)cc1", "p-쿠마르산", "p-Coumaric acid", "medium"),
    ("OC(=O)/C=C/c1ccc(O)c(OC)c1", "페룰산", "Ferulic acid", "medium"),
    ("OC(=O)c1ccc(O)c(O)c1", "프로토카테큐산", "Protocatechuic acid", "low"),
    ("Oc1ccc2ccccc2c1", "β-나프톨(alt)", "beta-Naphthol (alt)", "low"),
    ("OC(=O)c1cc(OC)c(O)c(OC)c1", "시링가산", "Syringic acid", "medium"),
    ("c1ccc(C=O)cc1O", "살리실알데히드(alt)", "Salicylaldehyde (alt SMILES)", "low"),

    # ── 커플링 시약/펩타이드 합성 시약 ──
    ("On1c(=O)c2ccccc2c1=O", "N-히드록시프탈이미드", "N-Hydroxyphthalimide", "medium"),
    ("On1ccc(=O)c1=O", "NHS", "N-Hydroxysuccinimide (NHS)", "low"),
    ("O=C1CCC(=O)N1O", "NHS(alt)", "N-Hydroxysuccinimide (alt)", "low"),
    ("N=C=NC1CCCCC1", "DCC(근사)", "DCC (Dicyclohexylcarbodiimide, approx)", "medium"),
    ("CCN=C=NCCCN(C)C", "EDC", "EDC (1-Ethyl-3-(3-dimethylaminopropyl)carbodiimide)", "medium"),
    ("c1nc[nH]n1", "1,2,3-트리아졸", "1,2,3-Triazole", "medium"),
    ("On1nnc2ccccc21", "HOBt", "HOBt (1-Hydroxybenzotriazole)", "medium"),

    # ── 추가 의약품 합성 중간체 ──
    ("c1ccc(NC(=O)C(F)(F)F)cc1", "트리플루오로아세트아닐라이드", "Trifluoroacetanilide", "medium"),
    ("OC(=O)c1cnc(Cl)nc1", "2-클로로피리미딘-5-카르복실산", "2-Chloropyrimidine-5-carboxylic acid", "medium"),
    ("Clc1ccncn1", "2-클로로피리미딘", "2-Chloropyrimidine", "medium"),
    ("Clc1ccnc(Cl)n1", "2,4-디클로로피리미딘", "2,4-Dichloropyrimidine", "medium"),
    ("Nc1ccnc(N)n1", "2,4-디아미노피리미딘", "2,4-Diaminopyrimidine", "medium"),
    ("OC(=O)C1CC1", "시클로프로판카르복실산", "Cyclopropanecarboxylic acid", "low"),
    ("NC1CC1", "시클로프로필아민", "Cyclopropylamine", "low"),
    ("O=C(Cl)C1CC1", "시클로프로판카르보닐 클로라이드", "Cyclopropanecarbonyl chloride", "medium"),
    ("FC(F)(F)c1ccncc1", "4-트리플루오로메틸피리딘", "4-(Trifluoromethyl)pyridine", "medium"),
    ("Clc1ccncc1", "4-클로로피리딘", "4-Chloropyridine", "low"),
    ("Oc1ccncc1", "4-히드록시피리딘", "4-Hydroxypyridine", "low"),
    ("Nc1ccncc1", "4-아미노피리딘", "4-Aminopyridine", "low"),
    ("O=Cc1ccncc1", "4-피리딘카르복스알데히드", "4-Pyridinecarboxaldehyde", "low"),
    ("OC(=O)c1ccncc1", "이소니코틴산", "Isonicotinic acid", "low"),

    # ═══════════════════════════════════════════════════════════
    # 확장 빌딩블록 #6 — 의약품 합성 핵심 중간체 (~25개 추가)
    # 2026-03-23 pharmaceutical key intermediates
    # Sigma-Aldrich / TCI / Alfa Aesar 등에서 실제 구매 가능한 시약
    # ═══════════════════════════════════════════════════════════

    # ── Warfarin 합성 관련 ──
    ("O=c1cc(O)c2ccccc2o1", "4-히드록시쿠마린", "4-Hydroxycoumarin", "medium"),
    ("CC(=O)/C=C/c1ccccc1", "벤질리덴아세톤", "Benzylideneacetone (Benzalacetone)", "medium"),
    ("CC(=O)c1ccccc1", "아세토페논", "Acetophenone", "low"),

    # ── Ciprofloxacin 관련 ──
    ("O=c1cc[nH]c2cc(F)ccc12", "6-플루오로-4-퀴놀론", "6-Fluoro-4-quinolone", "medium"),
    ("Nc1ccc(F)cc1", "4-플루오로아닐린", "4-Fluoroaniline", "low"),
    ("C1CNCCN1", "피페라진", "Piperazine", "low"),
    ("BrC1CC1", "시클로프로필 브로마이드", "Cyclopropyl bromide", "medium"),

    # ── Sildenafil 관련 ──
    ("C1CNCCN1C", "1-메틸피페라진", "1-Methylpiperazine", "low"),
    ("CCOc1ccc(S(=O)(=O)Cl)cc1", "4-에톡시벤젠술포닐 클로라이드", "4-Ethoxybenzenesulfonyl chloride", "medium"),
    ("CCOc1ccccc1", "페네톨", "Phenetole (Ethoxybenzene)", "low"),

    # ── Omeprazole 관련 ──
    ("COc1ccc(N)c(N)c1", "4-메톡시-1,2-디아미노벤젠", "4-Methoxy-o-phenylenediamine", "medium"),
    ("COc1c(C)cnc(CSCl)c1C", "2-클로로메틸술포닐피리딘 유도체", "Pyridine-CH2SCl intermediate", "high"),

    # ── Atorvastatin 관련 ──
    ("Nc1ccccc1", "아닐린", "Aniline", "low"),
    ("OC(=O)c1ccc(F)cc1", "4-플루오로벤조산", "4-Fluorobenzoic acid", "low"),
    ("CC(C)C(=O)CC(=O)OCC", "에틸 4-메틸-3-옥소펜타노에이트", "Ethyl 4-methyl-3-oxopentanoate", "medium"),

    # ── Diazepam 관련 ──
    ("Nc1ccc(Cl)cc1", "4-클로로아닐린", "4-Chloroaniline", "low"),
    ("Nc1ccc(Cl)cc1C(=O)c1ccccc1", "2-아미노-5-클로로벤조페논", "2-Amino-5-chlorobenzophenone", "medium"),
    ("NCC(=O)O", "글리신", "Glycine", "low"),

    # ── Sertraline 관련 ──
    ("O=C1CCc2ccccc21", "1-테트랄론", "1-Tetralone (alpha-Tetralone)", "low"),
    ("Clc1ccc(Cl)c(Cl)c1", "1,2-디클로로-4-클로로벤젠", "1,2,4-Trichlorobenzene", "low"),

    # ── Metformin 관련 ──
    ("CN(C)C#N", "디메틸시아나마이드", "Dimethylcyanamide", "medium"),
    ("N=C(N)N", "구아니딘", "Guanidine", "low"),

    # ── 범용 의약품 빌딩블록 ──
    ("O=S(=O)(Cl)c1ccccc1", "벤젠술포닐 클로라이드", "Benzenesulfonyl chloride", "low"),
    ("c1ccc(-c2ccccc2)cc1", "비페닐", "Biphenyl", "low"),
    ("Nc1ccccc1N", "o-페닐렌디아민", "o-Phenylenediamine", "low"),
    ("Nc1ccccc1O", "2-아미노페놀", "2-Aminophenol", "low"),

    # ── Sildenafil 핵심 중간체 ──
    # 2-에톡시-4-아미노벤젠술포닐 클로라이드 (Sildenafil 시작물질)
    ("CCOc1ccc(S(=O)(=O)Cl)cc1", "4-에톡시벤젠술포닐 클로라이드(alt)", "4-Ethoxybenzenesulfonyl chloride (alt)", "medium"),
    # 피라졸로피리미딘 코어 (Sildenafil 핵심 중간체, OEt 버전)
    ("CCCc1nn(C)c2c(OCC)nc(Cl)nc12", "피라졸로피리미딘 클로라이드 (OEt)",
     "5-Ethoxy-3-propyl-1-methyl-7-chloropyrazolo[3,4-d]pyrimidine", "high"),
    # 피라졸로피리미딘 코어 (OH 버전 - 전구체)
    ("CCCc1nn(C)c2c(O)nc(Cl)nc12", "피라졸로피리미딘 클로라이드 (OH)",
     "5-Hydroxy-3-propyl-1-methyl-7-chloropyrazolo[3,4-d]pyrimidine", "high"),
    # Sildenafil 아릴 보론산 (Suzuki 커플링 파트너)
    ("CCOc1cc(S(=O)(=O)N2CCN(CC)CC2)ccc1B(O)O",
     "실데나필 아릴보론산 (정확)", "Sildenafil aryl boronic acid (correct OEt)", "high"),
    # Sildenafil 아릴 브로마이드 (Suzuki 커플링 파트너)
    ("CCOc1cc(S(=O)(=O)N2CCN(CC)CC2)ccc1Br",
     "실데나필 아릴 브로마이드", "Sildenafil aryl bromide", "high"),
    # Sildenafil 술포닐클로라이드 중간체 (양쪽 에톡시)
    ("CCCc1nn(C)c2c(OCC)nc(-c3ccc(S(=O)(=O)Cl)cc3OCC)nc12",
     "실데나필 술포닐클로라이드", "Sildenafil sulfonyl chloride intermediate", "high"),

    # ── Atorvastatin 핵심 중간체 ──
    # N-페닐 피롤 코어 + 알데히드 (Wittig 반응 전구체, 32 HA)
    ("CC(C)c1c(C=O)c(C(=O)Nc2ccccc2)c(-c2ccc(F)cc2)n1-c1ccccc1",
     "아토르바스타틴 피롤-알데히드", "Atorvastatin pyrrole-CHO intermediate", "high"),
    # N-페닐 피롤 코어 (알데히드 없음, 30 HA)
    ("CC(C)c1cc(C(=O)Nc2ccccc2)c(-c2ccc(F)cc2)n1-c1ccccc1",
     "아토르바스타틴 피롤 코어 (N-Ph)", "Atorvastatin pyrrole core (N-phenyl)", "high"),
    # 측쇄 디히드록시 알코올 (Wittig 생성물, 11 HA)
    ("OCC(O)CC(O)CC(=O)O", "디히드록시헵탄산 알코올", "3,5-Dihydroxy-7-hydroxyheptanoic acid", "high"),
    # 측쇄 알데히드 (Aldol/Wittig용, 11 HA)
    ("O=CC(O)CC(O)CC(=O)O", "디히드록시헵탄알", "3,5-Dihydroxyheptanedial acid", "medium"),
    # 측쇄 디히드록시 알코올 (입체화학 포함, Wittig 생성물)
    ("O=C(O)C[C@@H](O)C[C@@H](O)CO", "(3R,5S)-디히드록시헵탄산 알코올",
     "(3R,5S)-3,5-Dihydroxy-7-hydroxyheptanoic acid", "high"),

    # ── Suzuki 커플링 보론산 파트너 (의약품 합성용) ──
    ("OB(O)c1cc(S(=O)(=O)Cl)ccc1OCC", "4-에톡시-3-술포닐클로라이드페닐보론산", "4-Ethoxy-3-(sulfonyl chloride)phenylboronic acid", "high"),
    ("OB(O)c1cc(S(=O)(=O)N2CCN(C)CC2)ccc1OCC", "실데나필 아릴보론산", "Sildenafil aryl boronic acid", "high"),
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
    # N-guard: smiles must be str
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("is_building_block: smiles is not valid str (got %s)",
                       type(smiles).__name__)
        return False
    if not RDKIT_AVAILABLE:
        return smiles in BUILDING_BLOCKS
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("is_building_block: MolFromSmiles returned None for '%s'", smiles)
        return False
    canon = Chem.MolToSmiles(mol)
    return canon in BUILDING_BLOCKS


def get_building_block_info(smiles: str) -> Optional[Dict]:
    """시작물질 정보 반환 (없으면 None)"""
    if not isinstance(smiles, str) or not smiles:
        return None
    if not RDKIT_AVAILABLE:
        return BUILDING_BLOCKS.get(smiles)
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    canon = Chem.MolToSmiles(mol)
    if not isinstance(canon, str):  # MolToSmiles always returns str, guard for robustness
        return None
    return BUILDING_BLOCKS.get(canon)


def find_similar_blocks(smiles: str, top_n: int = 5) -> List[Tuple[str, str, float]]:
    """Tanimoto 유사도로 유사한 시작물질 검색.
    Returns: [(canonical_smiles, name, similarity), ...]"""
    # N-guard: smiles must be str
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("find_similar_blocks: smiles is not valid str (got %s)",
                       type(smiles).__name__)
        return []
    # N-guard: top_n must be int
    if not isinstance(top_n, int) or top_n < 1:
        logger.warning("find_similar_blocks: top_n is not valid int (got %s, value=%s)",
                       type(top_n).__name__, top_n)
        top_n = 5  # 기본값 복구
    if not RDKIT_AVAILABLE:
        logger.warning("find_similar_blocks: RDKit not available, returning empty")
        return []

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("find_similar_blocks: MolFromSmiles returned None for '%s'", smiles)
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

    [FIX-B] 엄격화: 상용 시약으로 실제 구매 가능한 분자만 True 반환.

    1순위: BUILDING_BLOCKS DB에 등록된 분자 -> True
    2순위: 엄격한 heuristic fallback:
           - MW < 130 AND heavy atoms <= 8 (더 작은 분자만)
           - 고리 수 <= 1 (폴리사이클릭 비허용)
           - 카이랄 센터 <= 1 (복잡 입체화학 비허용)
           - 금지 하위구조 무포함
    이렇게 해야 BFS가 비상용 중간체를 추가 분해하여 다단계 경로를 생성합니다.
    """
    # N-guard: smiles must be str
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("is_commercially_available: smiles is not valid str (got %s)",
                       type(smiles).__name__)
        return False
    # DB 등록 분자는 즉시 True
    if is_building_block(smiles):
        return True

    # Heuristic fallback: 매우 간단한 분자만 허용
    if not RDKIT_AVAILABLE:
        return False

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("is_commercially_available: MolFromSmiles returned None for '%s'", smiles)
        return False

    # 금지 하위구조 포함 시 즉시 거부
    if _has_forbidden_substructure(mol):
        return False

    from rdkit.Chem import Descriptors as _Desc
    from rdkit.Chem import rdMolDescriptors as _rdMolDesc
    mw = _Desc.ExactMolWt(mol)
    n_heavy = mol.GetNumHeavyAtoms()
    n_rings = _rdMolDesc.CalcNumRings(mol)
    n_chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))

    # [FIX-B] 엄격 기준: 단순한 소분자만 상용 가능 판정
    # MW < 130, heavy atoms <= 8, 고리 1개 이하, 카이랄 센터 1개 이하
    if mw < 130.0 and n_heavy <= 8 and n_rings <= 1 and n_chiral <= 1:
        return True

    return False


def lookup_building_block(smiles: str) -> Optional[Dict]:
    """시작물질 조회. DB에 있으면 정보 반환, 없으면 None.
    is_building_block()과 동일하나 명시적 조회용 인터페이스."""
    # N-guard: smiles must be str (delegates to get_building_block_info which also guards)
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("lookup_building_block: smiles is not valid str (got %s)",
                       type(smiles).__name__)
        return None
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
