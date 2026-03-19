# lead_optimizer.py — Lead Optimization Pipeline Engine
"""
ChemGrid 리드 최적화 파이프라인:
캔버스 분자 → 목표 선택 → AI 전략 해석 → RDKit 유도체 생성 → 배치 도킹 → ADMET → 랭킹

LLM 통합: Groq(Llama 3.1) 1차 → Gemini 2차 → 프리셋 3차
API 키: ~/.chemgrid/config.json에서 로드, os.environ에 자동 주입
"""

import json
import math
import os
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── API 키 관리 (config.json ↔ os.environ 자동 동기화) ───────────────
CONFIG_DIR = Path.home() / ".chemgrid"
CONFIG_FILE = CONFIG_DIR / "config.json"

def _load_config() -> Dict:
    """~/.chemgrid/config.json 로드. 없으면 빈 dict."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_config(cfg: Dict):
    """~/.chemgrid/config.json 저장."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def inject_api_keys():
    """config.json의 API 키를 os.environ에 주입. 앱 시작 시 1회 호출."""
    cfg = _load_config()
    for key_name in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = cfg.get(key_name, "")
        if val and not os.environ.get(key_name):
            os.environ[key_name] = val

def save_api_key(key_name: str, key_value: str):
    """API 키를 config.json에 저장 + os.environ에 즉시 주입."""
    cfg = _load_config()
    cfg[key_name] = key_value
    _save_config(cfg)
    os.environ[key_name] = key_value

def get_api_key(key_name: str) -> str:
    """API 키 조회: os.environ 우선, config.json fallback."""
    val = os.environ.get(key_name, "")
    if not val:
        cfg = _load_config()
        val = cfg.get(key_name, "")
        if val:
            os.environ[key_name] = val
    return val

# 앱 시작 시 자동 주입
inject_api_keys()

# ── RDKit / 의존성 ────────────────────────────────────────────────
RDKIT_OK = False
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors, Draw
    RDKIT_OK = True
except ImportError:
    pass

GROQ_OK = False
try:
    from groq import Groq
    GROQ_OK = True
except ImportError:
    pass

GEMINI_OK = False
try:
    import google.genai as genai
    GEMINI_OK = True
except ImportError:
    pass

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ModificationStrategy:
    """AI가 해석한 분자 변형 전략."""
    name: str                    # "R-group replacement"
    name_kr: str                 # "R기 치환"
    description: str             # 상세 설명
    strategies: List[str]        # ["r_group", "bioisostere", "chain", "ring"]
    preferred_substituents: List[str]  # ["F", "CF3", "NH2"] — 우선 치환기
    target_protein: str          # 추천 표적 단백질 PDB ID
    rationale: str               # AI 근거


@dataclass
class VariantResult:
    """단일 유도체 평가 결과."""
    smiles: str
    parent_smiles: str
    modification_type: str       # "r_group", "bioisostere", "chain", "ring", "stereo"
    modification_detail: str     # "벤젠 C4 → F 치환"
    # ── 스코어링 (파이프라인에서 채움) ──
    docking_score: float = 0.0   # kcal/mol (음수 = 좋음)
    docking_delta: float = 0.0   # 부모 대비 개선도
    admet_pass: bool = False
    admet_violations: int = 0
    bbb_score: float = 0.0
    qed_score: float = 0.0
    sa_score: float = 5.0        # Synthetic Accessibility (1=쉬움, 10=어려움)
    composite_rank: float = 0.0  # 종합 점수 (0~1, 높을수록 좋음)
    tier: str = "C"              # A/B/C


@dataclass
class LeadOptimizationResult:
    """전체 최적화 결과."""
    base_smiles: str
    goal: str
    receptor_pdb_id: str
    total_variants: int
    ranked_variants: List[VariantResult]
    stages_completed: List[str] = field(default_factory=list)
    base_docking_score: float = 0.0
    error: str = ""


# ============================================================================
# LLM UNIFIED CALLER
# ============================================================================

def call_llm(prompt: str, system: str = "당신은 유기화학 및 약학 전문가입니다.") -> str:
    """통합 LLM 호출: Groq 1차 → Gemini 2차 → 빈 문자열.

    API 키가 없거나 호출 실패 시 다음 모델로 자동 전환.
    """
    # 1차: Groq (Llama 3.1 70B)
    groq_key = get_api_key("GROQ_API_KEY")
    if GROQ_OK and groq_key:
        try:
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            text = resp.choices[0].message.content.strip()
            if text:
                return text
        except Exception as e:
            logger.warning(f"Groq API failed: {e}")

    # 2차: Gemini (gemini-2.5-flash)
    gemini_key = get_api_key("GEMINI_API_KEY") or get_api_key("GOOGLE_API_KEY")
    if GEMINI_OK and gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            for model_name in ["gemini-2.5-flash", "gemini-2.0-flash"]:
                try:
                    resp = client.models.generate_content(
                        model=model_name, contents=prompt
                    )
                    if resp.text:
                        return resp.text.strip()
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Gemini API failed: {e}")

    return ""


# ============================================================================
# GOAL TRANSLATOR
# ============================================================================

# 프리셋 목표 → 변형 전략 (API 불필요)
PRESET_GOALS: Dict[str, ModificationStrategy] = {
    "항암 효과 추가": ModificationStrategy(
        name="Anticancer optimization",
        name_kr="항암 최적화",
        description="키나아제 억제제 약리단 도입 + 소수성 증가",
        strategies=["r_group", "bioisostere", "ring"],
        preferred_substituents=["F", "C(F)(F)F", "c1ccncc1", "NS(=O)(=O)c1ccccc1",
                                "Nc1ncccn1", "c1ccc2[nH]ccc2c1"],
        target_protein="1M17",  # EGFR
        rationale="EGFR 키나아제 억제 → 아미노피리미딘/설폰아미드 도입이 효과적. F, CF3로 대사 안정성 동시 개선.",
    ),
    "BBB 투과 개선": ModificationStrategy(
        name="BBB permeability optimization",
        name_kr="혈뇌장벽 투과 최적화",
        description="친유성 증가 + 분자량 감소 + HBD 감소",
        strategies=["r_group", "bioisostere"],
        preferred_substituents=["F", "C", "CC", "C(F)(F)F", "OC"],
        target_protein="2HYY",  # AChE (뇌 표적)
        rationale="BBB 투과: MW<400, LogP 1~4, TPSA<90, HBD≤3. 극성기 제거 + F 도입으로 친유성 증가.",
    ),
    "대사 안정성 향상": ModificationStrategy(
        name="Metabolic stability optimization",
        name_kr="대사 안정성 최적화",
        description="CYP450 대사 핫스팟 차단 (F, Cl 치환)",
        strategies=["r_group"],
        preferred_substituents=["F", "Cl", "C(F)(F)F", "OC(F)(F)F"],
        target_protein="",
        rationale="벤질 위치, 방향족 파라 위치가 CYP3A4/2D6 대사 핫스팟. F/CF3로 차단하면 반감기 2~5배 연장.",
    ),
    "수용성 개선": ModificationStrategy(
        name="Solubility optimization",
        name_kr="수용성 최적화",
        description="극성기 추가 + 지방족 사슬 단축",
        strategies=["r_group", "bioisostere", "chain"],
        preferred_substituents=["O", "N", "CO", "C(=O)O", "S(=O)(=O)N",
                                "C1CCNCC1", "C1CNCCN1"],
        target_protein="",
        rationale="LogP 감소: -OH, -NH2, 모르폴리노, 피페라진 도입. 카르복실산/설폰아미드로 염 형성 가능.",
    ),
    "지속 시간 개선": ModificationStrategy(
        name="Duration optimization",
        name_kr="약효 지속시간 최적화",
        description="대사 안정성 + 단백질 결합 최적화",
        strategies=["r_group", "chain"],
        preferred_substituents=["F", "Cl", "C(F)(F)F", "CC(C)C", "C1CCCCC1"],
        target_protein="",
        rationale="대사 차단(F/CF3) + 소수성 체인으로 혈장 단백질 결합 증가 → 유리형 약물 서방 효과.",
    ),
    "선택성 향상": ModificationStrategy(
        name="Selectivity optimization",
        name_kr="표적 선택성 최적화",
        description="입체 장벽 도입 + 특이적 상호작용 강화",
        strategies=["r_group", "bioisostere", "ring"],
        preferred_substituents=["C(C)C", "C1CC1", "c1ccoc1", "c1ccsc1",
                                "OC", "NC"],
        target_protein="",
        rationale="비표적 수용체 포켓에 안 맞는 입체 장벽(이소프로필, 사이클로프로필) 도입으로 선택성 확보.",
    ),
}


def translate_goal(goal_text: str, base_smiles: str) -> ModificationStrategy:
    """자연어 목표 → 구체적 변형 전략.

    1순위: 프리셋 매칭 → 2순위: LLM 해석 → 3순위: 범용 fallback
    """
    # 1. 프리셋 매칭
    goal_lower = goal_text.strip()
    for preset_key, strategy in PRESET_GOALS.items():
        if preset_key in goal_lower or goal_lower in preset_key:
            return strategy

    # 2. LLM 해석
    prompt = (
        f"분자 SMILES: {base_smiles}\n"
        f"사용자 목표: {goal_text}\n\n"
        f"이 분자를 '{goal_text}' 방향으로 최적화하기 위한 구조 변형 전략을 JSON으로 알려줘:\n"
        f'{{"strategies": ["r_group"/"bioisostere"/"chain"/"ring" 중 선택],\n'
        f' "preferred_substituents": ["F", "NH2" 등 SMILES 조각 리스트],\n'
        f' "target_protein_pdb": "PDB ID (없으면 빈 문자열)",\n'
        f' "rationale": "한국어 설명"}}\n'
        f"JSON만 출력."
    )
    llm_response = call_llm(prompt)
    if llm_response:
        try:
            # JSON 추출 (코드 블록 제거)
            text = llm_response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())
            return ModificationStrategy(
                name="AI-designed optimization",
                name_kr=f"AI 최적화: {goal_text[:20]}",
                description=data.get("rationale", goal_text),
                strategies=data.get("strategies", ["r_group", "bioisostere"]),
                preferred_substituents=data.get("preferred_substituents", ["F", "OH", "NH2"]),
                target_protein=data.get("target_protein_pdb", ""),
                rationale=data.get("rationale", "AI 생성 전략"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"LLM JSON parse failed: {e}")

    # 3. 범용 fallback
    return ModificationStrategy(
        name="Broad optimization",
        name_kr="범용 최적화",
        description="다양한 치환기를 시도하여 최적 유도체 탐색",
        strategies=["r_group", "bioisostere"],
        preferred_substituents=["F", "Cl", "OH", "NH2", "C(F)(F)F", "OC", "C#N"],
        target_protein="",
        rationale="특정 목표 없이 다양한 구조 변형을 시도합니다.",
    )


# ============================================================================
# MOLECULE VARIANT GENERATOR
# ============================================================================

# R-group 치환기 라이브러리 (SMILES fragment → 한국어 이름)
R_GROUP_LIBRARY: Dict[str, str] = {
    "F": "플루오로",
    "Cl": "클로로",
    "Br": "브로모",
    "O": "하이드록시",
    "N": "아미노",
    "OC": "메톡시",
    "OCC": "에톡시",
    "C": "메틸",
    "CC": "에틸",
    "C(C)C": "이소프로필",
    "C1CC1": "사이클로프로필",
    "C#N": "시아노",
    "C(=O)O": "카르복실",
    "C(=O)N": "카르바모일",
    "C(=O)C": "아세틸",
    "S(=O)(=O)N": "설폰아미도",
    "C(F)(F)F": "트리플루오로메틸",
    "OC(F)(F)F": "트리플루오로메톡시",
    "[N+](=O)[O-]": "니트로",
    "c1ccncc1": "4-피리딜",
    "c1ccoc1": "2-퓨릴",
    "c1ccsc1": "2-티에닐",
    "C1CCNCC1": "피페리디닐",
    "C1CNCCN1": "피페라지닐",
    "C1CCOCC1": "모르폴리닐",
    "C1CCNC1": "피롤리디닐",
    "Nc1ncccn1": "2-아미노피리미디닐",
    "NS(=O)(=O)c1ccccc1": "벤젠설폰아미도",
}

# 등가체 쌍 (SMARTS pattern → replacement SMILES)
BIOISOSTERE_PAIRS: List[Tuple[str, str, str, str]] = [
    # (name, source_smarts, replacement_smarts, description)
    ("COOH→테트라졸", "C(=O)[OH]", "c1nnn[nH]1", "카르복실산 → 테트라졸 (pKa 유사, 대사 안정)"),
    ("페닐→피리딜", "c1ccccc1", "c1ccncc1", "벤젠 → 피리딘 (수용성 증가, LogP 감소)"),
    ("에스터→아미드", "C(=O)OC", "C(=O)NC", "에스터 → 아미드 (대사 안정성 증가)"),
    ("-NH-→-O-", "[NH]", "O", "아민 → 에테르 (수소결합 공여 제거)"),
    ("-CH2-→-O-", "[CH2]", "O", "메틸렌 → 산소 (극성 증가)"),
    ("-CH2-→-NH-", "[CH2]", "NH", "메틸렌 → 아민 (염기성 추가)"),
    ("페놀→인돌", "Oc1ccccc1", "c1ccc2[nH]ccc2c1", "페놀 → 인돌 (소수성 증가)"),
    ("설파이드→설폰", "CSC", "CS(=O)(=O)C", "티오에테르 → 설폰 (대사 안정)"),
]


class MoleculeVariantGenerator:
    """RDKit 기반 분자 유도체 생성기."""

    def generate_r_group_variants(self, mol, preferred: List[str] = None,
                                   max_count: int = 50) -> List[VariantResult]:
        """방향족/지방족 H를 치환기로 교체하여 유도체 생성."""
        if not RDKIT_OK or mol is None:
            return []

        parent_smi = Chem.MolToSmiles(mol)
        results = []
        seen = {parent_smi}

        # 치환 가능한 위치: 방향족 H
        arom_h_pat = Chem.MolFromSmarts("[cH]")
        if arom_h_pat is None:
            return []

        matches = mol.GetSubstructMatches(arom_h_pat)
        if not matches:
            # 방향족 없으면 지방족 C-H 위치 시도
            aliph_pat = Chem.MolFromSmarts("[CH3,CH2,CH]")
            if aliph_pat:
                matches = mol.GetSubstructMatches(aliph_pat)

        # 치환기 선택 (preferred 우선)
        subs_to_try = []
        if preferred:
            for s in preferred:
                if s in R_GROUP_LIBRARY:
                    subs_to_try.append((s, R_GROUP_LIBRARY[s]))
                else:
                    subs_to_try.append((s, s))
        # 나머지 라이브러리 추가
        for smi, name in R_GROUP_LIBRARY.items():
            if not any(s[0] == smi for s in subs_to_try):
                subs_to_try.append((smi, name))

        for match in matches:
            atom_idx = match[0]
            atom = mol.GetAtomWithIdx(atom_idx)

            for sub_smi, sub_name in subs_to_try:
                if len(results) >= max_count:
                    break
                try:
                    # RWMol 편집으로 H → 치환기
                    sub_mol = Chem.MolFromSmiles(sub_smi)
                    if sub_mol is None:
                        continue

                    # CombineMols + 결합 형성
                    combo = Chem.CombineMols(mol, sub_mol)
                    ed = Chem.RWMol(combo)
                    # 원본 원자 idx
                    n_orig = mol.GetNumAtoms()
                    # 치환기의 첫 원자
                    sub_first = n_orig  # CombineMols는 뒤에 붙음

                    # 기존 H 하나 제거 후 결합 형성
                    ed_atom = ed.GetAtomWithIdx(atom_idx)
                    n_h = ed_atom.GetNumExplicitHs()
                    if n_h > 0:
                        ed_atom.SetNumExplicitHs(n_h - 1)
                    ed.AddBond(atom_idx, sub_first, Chem.BondType.SINGLE)

                    try:
                        Chem.SanitizeMol(ed)
                        new_smi = Chem.MolToSmiles(ed)
                        if new_smi and new_smi not in seen:
                            # 유효성 재확인
                            check = Chem.MolFromSmiles(new_smi)
                            if check is not None:
                                seen.add(new_smi)
                                atom_label = f"C{atom_idx+1}" if atom.GetIsAromatic() else f"atom{atom_idx+1}"
                                results.append(VariantResult(
                                    smiles=new_smi,
                                    parent_smiles=parent_smi,
                                    modification_type="r_group",
                                    modification_detail=f"{atom_label} → {sub_name} 치환",
                                ))
                    except Exception:
                        continue
                except Exception:
                    continue

        return results

    def generate_bioisostere_variants(self, mol, max_count: int = 20) -> List[VariantResult]:
        """등가체(bioisostere) 교환으로 유도체 생성."""
        if not RDKIT_OK or mol is None:
            return []

        parent_smi = Chem.MolToSmiles(mol)
        results = []
        seen = {parent_smi}

        for name, src_sma, repl_smi, desc in BIOISOSTERE_PAIRS:
            if len(results) >= max_count:
                break
            try:
                src_pat = Chem.MolFromSmarts(src_sma)
                repl_mol = Chem.MolFromSmiles(repl_smi)
                if src_pat is None or repl_mol is None:
                    continue

                if mol.HasSubstructMatch(src_pat):
                    replacements = AllChem.ReplaceSubstructs(mol, src_pat, repl_mol)
                    for rep in replacements:
                        try:
                            Chem.SanitizeMol(rep)
                            new_smi = Chem.MolToSmiles(rep)
                            if new_smi and new_smi not in seen:
                                check = Chem.MolFromSmiles(new_smi)
                                if check is not None:
                                    seen.add(new_smi)
                                    results.append(VariantResult(
                                        smiles=new_smi,
                                        parent_smiles=parent_smi,
                                        modification_type="bioisostere",
                                        modification_detail=f"{name}: {desc}",
                                    ))
                        except Exception:
                            continue
            except Exception:
                continue

        return results

    def generate_chain_variants(self, mol, max_count: int = 10) -> List[VariantResult]:
        """알킬 사슬 길이 변형 (CH2 삽입/제거)."""
        if not RDKIT_OK or mol is None:
            return []

        parent_smi = Chem.MolToSmiles(mol)
        results = []
        seen = {parent_smi}

        # CH2CH2 패턴 찾기 → CH2 제거 (사슬 단축)
        ch2ch2 = Chem.MolFromSmarts("[CH2][CH2]")
        ch2 = Chem.MolFromSmiles("C")
        if ch2ch2 and ch2 and mol.HasSubstructMatch(ch2ch2):
            try:
                reps = AllChem.ReplaceSubstructs(mol, ch2ch2, ch2)
                for rep in reps[:3]:
                    try:
                        Chem.SanitizeMol(rep)
                        new_smi = Chem.MolToSmiles(rep)
                        if new_smi and new_smi not in seen:
                            check = Chem.MolFromSmiles(new_smi)
                            if check:
                                seen.add(new_smi)
                                results.append(VariantResult(
                                    smiles=new_smi, parent_smiles=parent_smi,
                                    modification_type="chain",
                                    modification_detail="CH₂ 제거 (사슬 단축)",
                                ))
                    except Exception:
                        continue
            except Exception:
                pass

        # CH2 → CH2CH2 (사슬 연장)
        ch2_single = Chem.MolFromSmarts("[CH2]")
        ch2ch2_repl = Chem.MolFromSmiles("CC")
        if ch2_single and ch2ch2_repl and mol.HasSubstructMatch(ch2_single):
            try:
                reps = AllChem.ReplaceSubstructs(mol, ch2_single, ch2ch2_repl)
                for rep in reps[:3]:
                    try:
                        Chem.SanitizeMol(rep)
                        new_smi = Chem.MolToSmiles(rep)
                        if new_smi and new_smi not in seen:
                            check = Chem.MolFromSmiles(new_smi)
                            if check:
                                seen.add(new_smi)
                                results.append(VariantResult(
                                    smiles=new_smi, parent_smiles=parent_smi,
                                    modification_type="chain",
                                    modification_detail="CH₂ 삽입 (사슬 연장)",
                                ))
                    except Exception:
                        continue
            except Exception:
                pass

        return results[:max_count]

    def generate_ring_variants(self, mol, max_count: int = 10) -> List[VariantResult]:
        """고리 변형 (방향족↔포화, 5원↔6원)."""
        if not RDKIT_OK or mol is None:
            return []

        parent_smi = Chem.MolToSmiles(mol)
        results = []
        seen = {parent_smi}

        # 벤젠 → 피리딘 (이미 bioisostere에 있지만 다른 위치)
        ring_swaps = [
            ("c1ccccc1", "c1ccncc1", "벤젠→피리딘"),
            ("c1ccccc1", "c1ccnc(N)n1", "벤젠→아미노피리미딘"),
            ("C1CCCC1", "C1CCCCC1", "5원→6원 확장"),
            ("C1CCCCC1", "C1CCCC1", "6원→5원 축소"),
        ]

        for src_smi, dst_smi, desc in ring_swaps:
            if len(results) >= max_count:
                break
            try:
                src = Chem.MolFromSmarts(src_smi) or Chem.MolFromSmiles(src_smi)
                dst = Chem.MolFromSmiles(dst_smi)
                if src and dst and mol.HasSubstructMatch(src):
                    reps = AllChem.ReplaceSubstructs(mol, src, dst)
                    for rep in reps[:2]:
                        try:
                            Chem.SanitizeMol(rep)
                            new_smi = Chem.MolToSmiles(rep)
                            if new_smi and new_smi not in seen:
                                check = Chem.MolFromSmiles(new_smi)
                                if check:
                                    seen.add(new_smi)
                                    results.append(VariantResult(
                                        smiles=new_smi, parent_smiles=parent_smi,
                                        modification_type="ring",
                                        modification_detail=desc,
                                    ))
                        except Exception:
                            continue
            except Exception:
                continue

        return results

    def generate_all(self, smiles: str, n_target: int = 50,
                     strategy: ModificationStrategy = None) -> List[VariantResult]:
        """전략에 따라 유도체 생성. 중복 제거 후 n_target개 반환."""
        if not RDKIT_OK:
            return []

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []

        strategies = strategy.strategies if strategy else ["r_group", "bioisostere"]
        preferred = strategy.preferred_substituents if strategy else []

        all_variants = []
        per_strategy = max(5, n_target // max(1, len(strategies)))

        if "r_group" in strategies:
            all_variants.extend(
                self.generate_r_group_variants(mol, preferred, per_strategy * 2)
            )
        if "bioisostere" in strategies:
            all_variants.extend(
                self.generate_bioisostere_variants(mol, per_strategy)
            )
        if "chain" in strategies:
            all_variants.extend(
                self.generate_chain_variants(mol, per_strategy)
            )
        if "ring" in strategies:
            all_variants.extend(
                self.generate_ring_variants(mol, per_strategy)
            )

        # 중복 제거
        seen = set()
        unique = []
        for v in all_variants:
            if v.smiles not in seen:
                seen.add(v.smiles)
                unique.append(v)

        # n_target 이하로 잘라서 반환
        return unique[:n_target]


# ============================================================================
# SCORING
# ============================================================================

def score_variant(variant: VariantResult, base_docking: float) -> float:
    """유도체 종합 점수 계산 (0~1, 높을수록 좋음)."""
    # 도킹 점수 정규화 (-12 = 1.0, 0 = 0.0)
    dock_norm = max(0, min(1, variant.docking_score / -12.0)) if variant.docking_score < 0 else 0

    # 개선도 (부모 대비)
    if base_docking < 0:
        delta_norm = max(0, min(1, (variant.docking_score - base_docking) / (-4.0)))
    else:
        delta_norm = dock_norm * 0.5

    # SA Score 정규화 (1=최고, 10=최악 → 역변환)
    sa_norm = max(0, min(1, (10 - variant.sa_score) / 9.0))

    # ADMET 점수 (violations 기반)
    admet_norm = max(0, 1 - variant.admet_violations * 0.2)

    # 복합 점수
    composite = (
        dock_norm * 0.30 +
        variant.qed_score * 0.20 +
        admet_norm * 0.20 +
        sa_norm * 0.15 +
        delta_norm * 0.15
    )

    variant.composite_rank = round(composite, 3)
    variant.docking_delta = round(variant.docking_score - base_docking, 2) if base_docking != 0 else 0

    # 티어 분류
    if composite >= 0.65:
        variant.tier = "A"
    elif composite >= 0.40:
        variant.tier = "B"
    else:
        variant.tier = "C"

    return composite


def calculate_sa_score(smiles: str) -> float:
    """Synthetic Accessibility Score (1=쉬움, 10=어려움)."""
    if not RDKIT_OK:
        return 5.0
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return 8.0
        # RDKit SA Score (Ertl & Schuffenhauer)
        from rdkit.Chem import RDConfig
        import sys
        sa_path = os.path.join(RDConfig.RDContribDir, 'SA_Score')
        if sa_path not in sys.path:
            sys.path.insert(0, sa_path)
        try:
            import sascorer
            return sascorer.calculateScore(mol)
        except ImportError:
            # Fallback: 간단한 휴리스틱
            n_rings = rdMolDescriptors.CalcNumRings(mol)
            n_stereo = rdMolDescriptors.CalcNumAtomStereoCenters(mol)
            n_heavy = mol.GetNumHeavyAtoms()
            mw = Descriptors.MolWt(mol)
            # 간단 근사: 무거울수록, 복잡할수록 합성 어려움
            score = 1.0 + n_rings * 0.5 + n_stereo * 1.0 + max(0, (n_heavy - 10)) * 0.15
            return min(10, max(1, score))
    except Exception:
        return 5.0
