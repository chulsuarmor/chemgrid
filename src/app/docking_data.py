# docking_data.py (v1.0 - Molecular Docking Data Structures)
"""
ChemDraw Pro: Data structures for molecular docking simulation
- Receptor (protein) data from PDB files
- Ligand data from canvas SMILES
- Docking configuration and results
- Protein-ligand interaction types
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional


@dataclass
class ReceptorMetadata:
    """Biological metadata for a known receptor/target"""
    pdb_id: str
    name: str               # e.g., "Cyclooxygenase-2 (COX-2)"
    gene: str = ""          # e.g., "PTGS2"
    description: str = ""   # brief biological description
    function: str = ""      # biological function in Korean
    disease_relevance: str = ""  # disease associations in Korean
    known_drugs: List[str] = field(default_factory=list)
    organism: str = "Homo sapiens"
    uniprot_id: str = ""
    binding_site_residues: List[str] = field(default_factory=list)  # key residue labels
    # ── 결합부위 물리화학적 특성 ──
    pocket_character: str = ""   # 소수성/친수성/혼합
    pocket_volume_A3: float = 0.0  # 결합부위 부피 (ų)
    key_interactions: List[str] = field(default_factory=list)  # 주요 상호작용 유형
    selectivity_notes: str = ""  # 선택성/특이성 정보
    autodock_tips: str = ""      # AutoDock Vina 도킹 팁
    # ── 약리학적/해부학적 컨텍스트 ──
    tissue_location: str = ""    # 체내 발현 위치 (장기/조직)
    nervous_system: str = ""     # 신경계 연관성
    bbb_notes: str = ""          # 혈뇌장벽(BBB) 통과 관련
    pharmacology: str = ""       # 약리학적 의의 (작용 기전, 부작용 등)


# ============================================================================
# KNOWN RECEPTOR DATABASE
# ============================================================================

RECEPTOR_DATABASE: Dict[str, 'ReceptorMetadata'] = {}

def _init_receptor_database():
    """Initialize the known receptor metadata database."""
    global RECEPTOR_DATABASE

    entries = [
        ReceptorMetadata(
            pdb_id="5KIR",
            name="Cyclooxygenase-2 (COX-2)",
            gene="PTGS2",
            description="Prostaglandin-endoperoxide synthase 2, inducible form of cyclooxygenase",
            function="프로스타글란딘 합성 효소 — 아라키돈산을 프로스타글란딘 H2로 전환하여 염증, 통증, 발열 반응을 매개",
            disease_relevance="관절염, 암(대장암, 유방암), 심혈관 질환, 알츠하이머, 만성 염증 질환",
            known_drugs=["Aspirin", "Ibuprofen", "Celecoxib", "Naproxen", "Diclofenac"],
            organism="Homo sapiens",
            uniprot_id="P35354",
            binding_site_residues=["Arg120", "Tyr355", "Tyr385", "Ser530", "Val349", "Leu352", "Phe518"],
            pocket_character="소수성 우세 (Leu/Val 소수성 잔기) + Arg120 양전하",
            pocket_volume_A3=390.0,
            key_interactions=["수소결합 (Arg120↔카르복실)", "소수성 (Val349/Leu352)", "π-스태킹 (Tyr385)"],
            selectivity_notes="COX-1 대비 COX-2 선택성: Ile523→Val523 치환으로 측쇄 포켓 확장 — sulfonamide 유도체(Celecoxib)가 선택적 결합",
            autodock_tips="Grid center: Arg120 Cα 좌표 / Grid size: 25×25×25Å / exhaustiveness=32 권장",
            tissue_location="전신 — 특히 염증 부위, 관절 활막, 혈관 내피, 신장, 뇌. 기저 발현: 신장, 위장관",
            nervous_system="중추/말초 신경계 모두 발현. 뇌에서 COX-2는 통증 전달(척수 후각)과 발열 반응(시상하부)에 관여",
            bbb_notes="COX-2는 BBB 내피세포에도 발현 → BBB 통과 불필요. 하지만 NSAIDs(이부프로펜)는 BBB를 일부 통과하여 중추 진통 효과 기여",
            pharmacology="비선택적 NSAIDs: 위장관 출혈(COX-1 억제 부작용). COX-2 선택적 억제제(Celecoxib): 위장관 안전하나 심혈관 위험 증가(VIGOR trial)",
        ),
        ReceptorMetadata(
            pdb_id="5MZP",
            name="Adenosine A2A Receptor",
            gene="ADORA2A",
            description="G-protein coupled adenosine receptor subtype A2A",
            function="G-단백질 결합 수용체 — 아데노신 신호전달을 매개하여 신경조절, 면역 반응, 혈관 확장 조절",
            disease_relevance="파킨슨병, 암 면역요법(면역관문), 불면증, 불안 장애, 천식",
            known_drugs=["Caffeine", "Istradefylline (Nourianz)", "Regadenoson", "Preladenant"],
            organism="Homo sapiens",
            uniprot_id="P29274",
            binding_site_residues=["Asn253", "Glu169", "Phe168", "Leu249", "His250", "Val84"],
            pocket_character="친수성/혼합 (Glu/Asn 극성 잔기 + Phe/Leu 소수성)",
            pocket_volume_A3=310.0,
            key_interactions=["수소결합 (Asn253↔리간드 아민)", "소수성 (Val84/Leu249)", "π-스태킹 (Phe168/His250)"],
            selectivity_notes="A1/A2A/A2B/A3 아형 선택성: Glu169 위치가 A2A 특이적 — xanthine 골격이 선택적 결합",
            autodock_tips="Grid center: 결합 포켓 중심 / Grid size: 22×22×22Å / Flexible residues: Glu169, His250",
            tissue_location="뇌(선조체, 후각결절, 해마), 면역세포(T세포, 수지상세포), 혈소판, 혈관 평활근",
            nervous_system="기저핵(선조체)의 도파민-A2A 길항적 상호작용이 핵심. A2A 차단 → 간접적 도파민 D2 활성화 → 운동 기능 개선",
            bbb_notes="카페인(A2A 길항제)은 친유성으로 BBB 쉽게 통과. 대부분의 A2A 리간드는 BBB 통과 설계가 핵심 과제",
            pharmacology="A2A 길항: 파킨슨병 보조요법(Istradefylline). A2A 작용: 심장 스트레스 검사(Regadenoson). 면역관문: A2A 차단 → 종양 면역 활성화",
        ),
        ReceptorMetadata(
            pdb_id="1M17",
            name="Epidermal Growth Factor Receptor (EGFR)",
            gene="EGFR",
            description="Receptor tyrosine kinase ErbB-1, epidermal growth factor receptor",
            function="수용체 타이로신 키나아제 — 세포 성장, 분화, 생존 신호전달 경로 활성화 (RAS/MAPK, PI3K/AKT)",
            disease_relevance="비소세포폐암(NSCLC), 교모세포종, 대장암, 두경부암, 유방암",
            known_drugs=["Erlotinib (Tarceva)", "Gefitinib (Iressa)", "Osimertinib (Tagrisso)", "Cetuximab (Erbitux)"],
            organism="Homo sapiens",
            uniprot_id="P00533",
            binding_site_residues=["Leu718", "Val726", "Ala743", "Lys745", "Met793", "Thr790", "Asp855"],
            pocket_character="소수성 ATP-결합 포켓 + Lys745 양전하 (ATP γ-인산 결합)",
            pocket_volume_A3=420.0,
            key_interactions=["수소결합 (Met793 hinge↔리간드 N)", "소수성 (Leu718/Val726)", "이온결합 (Lys745↔리간드)"],
            selectivity_notes="T790M 게이트키퍼 돌연변이: Met→Thr 치환으로 1세대 저해제 내성 — 3세대 Osimertinib이 Cys797과 공유결합으로 극복",
            autodock_tips="Grid center: ATP-binding hinge (Met793) / Grid size: 24×24×24Å / Covalent docking 시 Cys797 지정",
            tissue_location="상피세포 전반 — 폐, 유방, 대장, 피부, 뇌(교모세포종). 암세포에서 과발현/돌연변이",
            nervous_system="뇌에서 정상 EGFR은 신경세포 생존/분화에 관여. 교모세포종(GBM)에서 EGFRvIII 변이가 종양 성장 촉진",
            bbb_notes="대부분의 EGFR TKI(Gefitinib, Erlotinib)는 BBB 투과율 낮음. Osimertinib은 BBB 투과 설계 → 뇌전이 NSCLC 치료 가능",
            pharmacology="1세대(Gefitinib): exon 19 del/L858R에 효과. T790M 내성 → 3세대(Osimertinib)로 극복. C797S 내성 → 4세대 개발 중",
        ),
        ReceptorMetadata(
            pdb_id="6M0J",
            name="Angiotensin-Converting Enzyme 2 (ACE2)",
            gene="ACE2",
            description="ACE2 receptor bound with SARS-CoV-2 receptor binding domain",
            function="안지오텐신 전환 효소 2 — 안지오텐신 II를 안지오텐신(1-7)로 분해하여 혈압 조절. SARS-CoV-2 바이러스 침입 수용체",
            disease_relevance="COVID-19, 고혈압, 심부전, 당뇨병성 신증, 급성 폐손상(ARDS)",
            known_drugs=["Captopril (ACE inhibitor, 간접)", "Losartan (ARB)", "Remdesivir (간접 표적)"],
            organism="Homo sapiens",
            uniprot_id="Q9BYF1",
            binding_site_residues=["Gln24", "Asp30", "His34", "Tyr41", "Gln42", "Lys353", "Asp355"],
            pocket_character="친수성 우세 (Gln/Asp/His 극성 잔기) — SARS-CoV-2 RBD 단백질-단백질 상호작용 면",
            pocket_volume_A3=680.0,
            key_interactions=["수소결합 (Lys353↔RBD Gly502)", "염다리 (Asp30↔RBD Lys417)", "소수성 (Tyr41/Gln42)"],
            selectivity_notes="ACE2 활성 부위(Zn²⁺ 촉매)와 RBD 결합면은 별도 위치 — 약물 설계 시 RBD 결합면 차단 vs ACE2 활성 유지 균형 필요",
            autodock_tips="Grid center: Lys353 Cα / Grid size: 30×30×30Å (PPI 넓은 면) / 펩타이드 도킹 시 FlexPepDock 권장",
            tissue_location="폐(폐포 상피세포 II형), 심장, 신장, 장, 고환. 바이러스 침입 주요 관문: 비강 → 기관지 → 폐포",
            nervous_system="후각 상피에 ACE2 발현 → COVID-19 후각 상실 원인. 뇌간에도 소량 발현 → 신경학적 합병증 가능성",
            bbb_notes="ACE2는 BBB 내피세포에 미량 발현. SARS-CoV-2가 BBB를 직접 통과하기보다는 면역 반응에 의한 간접적 신경 손상이 주 기전",
            pharmacology="ACE2를 차단하면 바이러스 침입은 막지만 RAS 불균형으로 혈압/장기 손상 악화 위험. 가용성 ACE2(recombinant) 데코이 전략이 연구 중",
        ),
        ReceptorMetadata(
            pdb_id="1HVR",
            name="HIV-1 Protease",
            gene="HIV-1 pol",
            description="HIV-1 aspartyl protease, essential for viral polyprotein cleavage",
            function="HIV-1 바이러스 단백질 분해 효소 — Gag-Pol 폴리단백질을 절단하여 성숙한 바이러스 입자 형성에 필수적",
            disease_relevance="HIV/AIDS",
            known_drugs=["Ritonavir", "Lopinavir", "Darunavir", "Atazanavir", "Saquinavir", "Indinavir"],
            organism="HIV-1",
            uniprot_id="P04585",
            binding_site_residues=["Asp25", "Asp25'", "Gly27", "Ala28", "Ile50", "Ile50'", "Val82", "Ile84"],
            pocket_character="소수성 터널 구조 + 촉매 Asp25/25' 음전하 다이어드 (C2 대칭 이량체)",
            pocket_volume_A3=450.0,
            key_interactions=["수소결합 (Asp25↔리간드 OH)", "소수성 (Ile50 flap/Val82/Ile84)", "구조수 매개 (Ile50↔물↔리간드)"],
            selectivity_notes="V82A/I84V 돌연변이: Darunavir가 backbone 수소결합으로 내성 극복 — 측쇄가 아닌 주쇄에 결합하는 전략",
            autodock_tips="Grid center: 촉매 dyad 중심 (Asp25-Asp25') / Grid size: 22×22×22Å / 구조수 포함 권장",
            tissue_location="HIV-1 바이러스 내부 — 숙주 세포(CD4+ T세포, 대식세포)에서 바이러스 복제 시 필수 효소",
            nervous_system="HIV는 BBB를 통과하여 미세아교세포/대식세포에 감염 → HIV 관련 신경인지 장애(HAND) 유발",
            bbb_notes="프로테아제 억제제(PI)는 대부분 P-gp efflux로 BBB 투과 불량. Darunavir가 상대적으로 양호. HAND 치료에는 BBB 투과 ARV 조합 필요",
            pharmacology="HAART 요법의 핵심 약물군. 부스팅(Ritonavir로 CYP3A4 억제 → 다른 PI 혈중 농도 유지). 내성: V82A, I84V 등 축적 돌연변이",
        ),
        ReceptorMetadata(
            pdb_id="2HYY",
            name="Acetylcholinesterase (AChE)",
            gene="ACHE",
            description="Acetylcholinesterase, terminates neurotransmission at cholinergic synapses",
            function="아세틸콜린 분해 효소 — 시냅스 틈에서 아세틸콜린을 분해하여 콜린성 신경전달 종결",
            disease_relevance="알츠하이머병, 중증 근무력증, 녹내장, 유기인 중독",
            known_drugs=["Donepezil (Aricept)", "Rivastigmine", "Galantamine", "Tacrine"],
            organism="Homo sapiens",
            uniprot_id="P22303",
            binding_site_residues=["Ser203", "His447", "Glu334", "Trp86", "Tyr337", "Phe338"],
            pocket_character="깊은 좁은 협곡 (gorge) — 입구에 Trp86 방향족, 바닥에 Ser-His-Glu 촉매 트리아드",
            pocket_volume_A3=300.0,
            key_interactions=["공유결합 (Ser203↔기질 아세틸기)", "양이온-π (Trp86↔4차 아민)", "π-스태킹 (Tyr337/Phe338)"],
            selectivity_notes="AChE vs BuChE 선택성: Phe295/Phe297 잔기가 AChE 좁은 gorge 형성 — Donepezil이 AChE 선택적 (BuChE에는 Leu 치환)",
            autodock_tips="Grid center: Ser203 Oγ 좌표 / Grid size: 20×20×20Å / 좁은 gorge → exhaustiveness=48 권장",
            tissue_location="신경근 접합부(NMJ), 뇌(대뇌피질, 해마, 기저핵), 적혈구. 시냅스 틈에서 아세틸콜린 분해 담당",
            nervous_system="콜린성 신경계 핵심 효소. 해마(기억), 기저핵(운동), 대뇌피질(인지)의 아세틸콜린 신호전달 종결",
            bbb_notes="AChE 억제제는 BBB 통과가 치료 효과의 핵심. Donepezil: 친유성으로 BBB 통과 양호. Neostigmine: 4차 아민이라 BBB 통과 불가 → 말초 전용(MG 치료)",
            pharmacology="가역적 억제(Donepezil): 알츠하이머 증상 완화. 비가역적 억제(유기인 신경작용제: Sarin): 콜린성 위기 → 해독제 Atropine/Pralidoxime",
        ),
        ReceptorMetadata(
            pdb_id="3ERT",
            name="Estrogen Receptor Alpha (ERa)",
            gene="ESR1",
            description="Nuclear estrogen receptor alpha, ligand-activated transcription factor",
            function="에스트로겐 수용체 알파 — 핵 내 전사 인자로서 에스트로겐 결합 시 유전자 발현 조절 (세포 증식, 분화)",
            disease_relevance="유방암 (ER-양성), 골다공증, 자궁내막암, 폐경 증후군",
            known_drugs=["Tamoxifen", "Raloxifene", "Fulvestrant (Faslodex)", "Letrozole (간접)"],
            organism="Homo sapiens",
            uniprot_id="P03372",
            binding_site_residues=["Glu353", "Arg394", "His524", "Leu387", "Met388", "Leu525"],
            pocket_character="소수성 포켓 + Glu353/Arg394 극성 앵커 (에스트라디올 A-ring phenol 수소결합)",
            pocket_volume_A3=450.0,
            key_interactions=["수소결합 (Glu353↔리간드 OH, His524↔리간드 OH)", "소수성 (Leu387/Met388/Leu525)", "π-스태킹 (Phe404)"],
            selectivity_notes="ERα vs ERβ 선택성: Leu384(α)→Met336(β) 치환으로 포켓 크기 미세 차이 — SERM(Tamoxifen)은 AF-2 helix 12를 재배치하여 길항",
            autodock_tips="Grid center: Glu353-Arg394 사이 / Grid size: 22×22×22Å / Helix 12 유연성이 중요 → flexible residues 포함 검토",
            tissue_location="유방, 자궁, 난소, 뼈, 간, 뇌(시상하부, 해마), 심혈관계. 유방암의 ~70%가 ER-양성",
            nervous_system="시상하부의 ERα: 체온 조절(폐경 안면홍조), 생식 호르몬 축(GnRH). 해마: 기억/인지 보호 효과",
            bbb_notes="에스트라디올(E2)은 스테로이드 → BBB 자유 통과. Tamoxifen도 BBB 통과 → 뇌전이 유방암에 효과. Fulvestrant: BBB 투과 불량",
            pharmacology="SERM(Tamoxifen): 유방에서 길항, 뼈에서 작용 → 유방암+골다공증 동시 치료. SERD(Fulvestrant): 완전 분해 → 내성 ER+ 유방암",
        ),
        ReceptorMetadata(
            pdb_id="4EY7",
            name="Beta-2 Adrenergic Receptor (B2AR)",
            gene="ADRB2",
            description="G-protein coupled beta-2 adrenergic receptor",
            function="베타-2 아드레날린 수용체 — 에피네프린/노르에피네프린 결합 시 기관지 확장, 혈관 이완, 심박수 증가",
            disease_relevance="천식, 만성 폐쇄성 폐질환(COPD), 심부전, 조산 방지",
            known_drugs=["Salbutamol (Ventolin)", "Salmeterol", "Formoterol", "Propranolol (차단제)"],
            organism="Homo sapiens",
            uniprot_id="P07550",
            binding_site_residues=["Asp113", "Asn312", "Ser203", "Ser207", "Phe290", "Trp286"],
            pocket_character="소수성/방향족 풍부 + Asp113 음전하 앵커 (양전하 아민 인식)",
            pocket_volume_A3=350.0,
            key_interactions=["이온결합 (Asp113↔리간드 아민)", "수소결합 (Ser203/207↔catechol OH)", "소수성 (Phe290/Trp286)"],
            selectivity_notes="β1 vs β2 선택성: Thr164(β2)→Ile(β1) — β2 선택적 작용제(Salbutamol)는 bulky catechol 치환기로 β2 포켓에 적합",
            autodock_tips="Grid center: Asp113 Cα / Grid size: 22×22×22Å / GPCR 도킹 시 orthosteric vs allosteric 부위 구분 필수",
            tissue_location="기관지 평활근, 심장(심방>심실), 혈관 평활근, 자궁, 골격근, 간, 지방 조직",
            nervous_system="교감신경계 effector — 에피네프린/노르에피네프린의 β2 수용체 활성화 → '투쟁-도피' 반응(기관지 확장, 심박수 증가)",
            bbb_notes="β2 작용제(Salbutamol)는 친수성이 높아 BBB 거의 불통과 → 말초 효과만. Propranolol(차단제)은 친유성 → BBB 통과 → 중추 부작용(악몽, 우울)",
            pharmacology="SABA(Salbutamol): 급성 천식 발작 완화(속효성). LABA(Salmeterol): 유지 치료(지속성). β차단제(Propranolol): 고혈압, 무대공포증, 편두통 예방",
        ),
    ]

    for entry in entries:
        RECEPTOR_DATABASE[entry.pdb_id.upper()] = entry
        # Also store common alternate PDB IDs
    # Additional COX-2 structures
    for alt_id in ["1CX2", "3LN1", "5IKR"]:
        if alt_id not in RECEPTOR_DATABASE and "5KIR" in RECEPTOR_DATABASE:
            RECEPTOR_DATABASE[alt_id] = RECEPTOR_DATABASE["5KIR"]
    # Additional EGFR structures
    for alt_id in ["4HJO", "3W2S", "5UG9"]:
        if alt_id not in RECEPTOR_DATABASE and "1M17" in RECEPTOR_DATABASE:
            RECEPTOR_DATABASE[alt_id] = RECEPTOR_DATABASE["1M17"]
    # Additional HIV protease
    for alt_id in ["1HXW", "3OXC", "1HPV"]:
        if alt_id not in RECEPTOR_DATABASE and "1HVR" in RECEPTOR_DATABASE:
            RECEPTOR_DATABASE[alt_id] = RECEPTOR_DATABASE["1HVR"]


_init_receptor_database()


def get_receptor_metadata(pdb_id: str) -> Optional['ReceptorMetadata']:
    """Look up receptor metadata by PDB ID. Returns None if not found."""
    if not pdb_id:
        return None
    return RECEPTOR_DATABASE.get(pdb_id.upper())


@dataclass
class PDBAtom:
    """Single atom from a PDB file"""
    serial: int
    name: str           # atom name (e.g., "CA", "CB", "N")
    residue_name: str   # residue name (e.g., "ALA", "GLY")
    chain: str          # chain identifier
    residue_id: int     # residue sequence number
    x: float
    y: float
    z: float
    element: str        # element symbol
    occupancy: float = 1.0
    b_factor: float = 0.0
    is_hetatm: bool = False


@dataclass
class Residue:
    """Protein residue (amino acid)"""
    name: str           # 3-letter code (e.g., "ALA")
    chain: str
    residue_id: int
    atoms: List[PDBAtom] = field(default_factory=list)

    @property
    def ca_position(self) -> Optional[Tuple[float, float, float]]:
        """Get C-alpha position for backbone tracing"""
        for atom in self.atoms:
            if atom.name.strip() == "CA":
                return (atom.x, atom.y, atom.z)
        return None


@dataclass
class ReceptorData:
    """Parsed protein receptor structure"""
    pdb_id: Optional[str] = None
    filepath: Optional[Path] = None
    name: str = ""
    atoms: List[PDBAtom] = field(default_factory=list)
    residues: Dict[str, List[Residue]] = field(default_factory=dict)  # chain -> residues
    prepared_pdbqt: Optional[Path] = None

    @property
    def atom_count(self) -> int:
        return len(self.atoms)

    @property
    def residue_count(self) -> int:
        return sum(len(res) for res in self.residues.values())

    @property
    def chains(self) -> List[str]:
        return list(self.residues.keys())

    def get_center(self) -> Tuple[float, float, float]:
        """Calculate centroid of all atoms"""
        if not self.atoms:
            return (0.0, 0.0, 0.0)
        xs = [a.x for a in self.atoms]
        ys = [a.y for a in self.atoms]
        zs = [a.z for a in self.atoms]
        n = len(self.atoms)
        return (sum(xs)/n, sum(ys)/n, sum(zs)/n)

    def get_bounding_box(self) -> Tuple[Tuple[float,float,float], Tuple[float,float,float]]:
        """Get min/max corners of bounding box"""
        if not self.atoms:
            return ((0,0,0), (0,0,0))
        xs = [a.x for a in self.atoms]
        ys = [a.y for a in self.atoms]
        zs = [a.z for a in self.atoms]
        return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


@dataclass
class LigandData:
    """Ligand molecule data prepared for docking"""
    smiles: str = ""
    name: str = ""
    atoms: List[Tuple[str, float, float, float]] = field(default_factory=list)  # (element, x, y, z)
    prepared_pdbqt: Optional[Path] = None

    @property
    def atom_count(self) -> int:
        return len(self.atoms)


@dataclass
class DockingConfig:
    """Docking search parameters"""
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    size_x: float = 20.0  # Angstroms
    size_y: float = 20.0
    size_z: float = 20.0
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: float = 3.0  # kcal/mol

    @property
    def center(self) -> Tuple[float, float, float]:
        return (self.center_x, self.center_y, self.center_z)

    @property
    def size(self) -> Tuple[float, float, float]:
        return (self.size_x, self.size_y, self.size_z)


@dataclass
class DockingPose:
    """Single docking pose result"""
    pose_id: int
    affinity_kcal: float   # binding energy in kcal/mol (negative = favorable)
    rmsd_lb: float = 0.0   # RMSD lower bound
    rmsd_ub: float = 0.0   # RMSD upper bound
    atom_coords: List[Tuple[float, float, float]] = field(default_factory=list)
    atom_elements: List[str] = field(default_factory=list)


@dataclass
class Interaction:
    """Protein-ligand interaction"""
    type: str               # "hydrogen_bond", "hydrophobic", "pi_stacking", "salt_bridge", "halogen_bond"
    ligand_atom_idx: int    # index in ligand atom list
    protein_atom_name: str  # protein atom name
    residue_name: str       # e.g., "ALA"
    residue_id: int
    chain: str
    distance: float         # Angstroms
    angle: Optional[float] = None  # degrees (for directional interactions)

    @property
    def residue_label(self) -> str:
        """e.g., 'ALA-123:A'"""
        return f"{self.residue_name}-{self.residue_id}:{self.chain}"

    @property
    def type_label(self) -> str:
        labels = {
            "hydrogen_bond": "H-Bond",
            "hydrophobic": "Hydrophobic",
            "pi_stacking": "π-Stacking",
            "salt_bridge": "Salt Bridge",
            "halogen_bond": "Halogen Bond",
        }
        return labels.get(self.type, self.type)


@dataclass
class DockingResult:
    """Complete docking calculation result"""
    converged: bool = False
    poses: List[DockingPose] = field(default_factory=list)
    receptor: Optional[ReceptorData] = None
    ligand: Optional[LigandData] = None
    config: Optional[DockingConfig] = None
    interactions: Dict[int, List[Interaction]] = field(default_factory=dict)  # pose_id -> interactions
    computation_time: float = 0.0  # seconds
    vina_log: str = ""
    error_message: str = ""
    is_simulation: bool = False  # True when using fallback simulation mode (no Vina)

    @property
    def best_affinity(self) -> float:
        """Get best (most negative) binding affinity"""
        if not self.poses:
            return 0.0
        return min(p.affinity_kcal for p in self.poses)

    @property
    def num_poses(self) -> int:
        return len(self.poses)

    def to_screening_scores(
        self,
        interactions: Optional[Dict[int, "List[Interaction]"]] = None,
    ) -> Dict[str, dict]:
        """Convert DockingResult to drug_screening-compatible DockingScore dicts.

        Returns a mapping of smiles -> dict with keys compatible with
        drug_screening.DockingScore:
          - smiles: str
          - binding_affinity: float (kcal/mol)
          - pose_rmsd: float (best RMSD lower bound)
          - n_interactions: int
          - interaction_types: List[str]

        This bridges the gap between docking_interface output format
        (DockingResult/DockingPose) and drug_screening input format
        (DockingScore dataclass).
        """
        if interactions is None:
            interactions = self.interactions or {}

        smiles = ""
        if self.ligand:
            smiles = self.ligand.smiles

        if not smiles or not self.poses:
            return {}

        # Use the best pose (lowest affinity) for the screening score
        best_pose = min(self.poses, key=lambda p: p.affinity_kcal)
        pose_interactions = interactions.get(best_pose.pose_id, [])

        # Collect unique interaction types
        interaction_type_set: list = []
        seen_types: set = set()
        for inter in pose_interactions:
            if inter.type not in seen_types:
                interaction_type_set.append(inter.type)
                seen_types.add(inter.type)

        score_dict = {
            "smiles": smiles,
            "binding_affinity": best_pose.affinity_kcal,
            "pose_rmsd": best_pose.rmsd_lb,
            "n_interactions": len(pose_interactions),
            "interaction_types": interaction_type_set,
        }

        return {smiles: score_dict}
