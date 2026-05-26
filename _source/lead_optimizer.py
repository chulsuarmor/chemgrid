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
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_LEAD_INPUT_ALIASES: Dict[str, Tuple[str, str]] = {
    "cadaverine": ("NCCCCCN", "cadaverine"),
    "cadaverin": ("NCCCCCN", "cadaverine"),
    "cadeverin": ("NCCCCCN", "cadaverine"),
}


def normalize_lead_optimizer_input(input_text: str) -> Tuple[str, Optional[str]]:
    """Normalize supported common-name lead inputs to SMILES.

    Returns (smiles_or_original_text, normalized_name). normalized_name is None
    when the input was not a supported alias and should be parsed as SMILES.
    """
    raw_text = str(input_text or "").strip()
    alias_key = re.sub(r"[^a-z0-9]+", "", raw_text.lower())
    alias = SUPPORTED_LEAD_INPUT_ALIASES.get(alias_key)
    if alias:
        smiles, normalized_name = alias
        logger.warning(
            "[D891] Lead optimizer input normalized: %r -> %s (%s)",
            raw_text,
            smiles,
            normalized_name,
        )
        return smiles, normalized_name
    return raw_text, None

# ── API 키 관리 (config.json ↔ os.environ 자동 동기화) ───────────────
CONFIG_DIR = Path.home() / ".chemgrid"
CONFIG_FILE = CONFIG_DIR / "config.json"

def _load_config() -> Dict:
    """~/.chemgrid/config.json 로드. 없으면 빈 dict."""
    if CONFIG_FILE.exists():
        try:
            parsed = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                logger.warning("config.json이 dict가 아님: type=%s", type(parsed).__name__)
                return {}
            return parsed
        except Exception as e:
            logger.warning("Config file load failed: %s", e)
    return {}

def _save_config(cfg: Dict):
    """~/.chemgrid/config.json 저장."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def inject_api_keys():
    """config.json의 API 키를 os.environ에 주입. 앱 시작 시 1회 호출."""
    cfg = _load_config()
    for key_name in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        # Rule N: isinstance guard for cfg
        if not isinstance(cfg, dict): cfg = {}
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
        # Rule N: isinstance guard for cfg
        if not isinstance(cfg, dict): cfg = {}
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
except ImportError as e:
    logger.debug("Optional module RDKit not available: %s", e)

GROQ_OK = False
try:
    from groq import Groq
    GROQ_OK = True
except ImportError as e:
    logger.debug("Optional module groq not available: %s", e)

GEMINI_OK = False
try:
    import google.genai as genai
    GEMINI_OK = True
except ImportError as e:
    logger.debug("Optional module google.genai not available: %s", e)

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


LEAD_VARIANT_RATIONALE_BOUNDARY = (
    "RDKit-only structural variant; heuristic rationale; "
    "not experimental or engine-validated pharmacology."
)


def _canonical_single_fragment_smiles(smiles: str, parent_smiles: str, context: str) -> Optional[str]:
    """Return canonical SMILES only for valid changed single-fragment variants."""
    if not RDKIT_OK:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("[Rule L] MolFromSmiles failed for generated %s: %r", context, smiles)
        return None
    fragments = Chem.GetMolFrags(mol)
    if len(fragments) != 1:
        logger.warning("[D891] Rejected disconnected lead optimizer %s variant: %r", context, smiles)
        return None
    canonical = Chem.MolToSmiles(mol, canonical=True)
    parent_mol = Chem.MolFromSmiles(parent_smiles)
    parent_canonical = Chem.MolToSmiles(parent_mol, canonical=True) if parent_mol is not None else parent_smiles
    if canonical == parent_canonical:
        logger.warning("[D891] Rejected unchanged lead optimizer %s variant: %r", context, smiles)
        return None
    return canonical


def _make_variant_result(
    smiles: str,
    parent_smiles: str,
    modification_type: str,
    modification_detail: str,
) -> VariantResult:
    variant = VariantResult(
        smiles=smiles,
        parent_smiles=parent_smiles,
        modification_type=modification_type,
        modification_detail=modification_detail,
    )
    variant.rdkit_validated = True
    variant.generation_rationale = (
        f"{modification_type}: RDKit sanitized single-fragment structural edit; "
        f"{modification_detail}"
    )
    variant.rationale_boundary = LEAD_VARIANT_RATIONALE_BOUNDARY
    variant.validation_notes = (
        "MolFromSmiles parsed; Chem.GetMolFrags count=1; canonical SMILES differs from parent."
    )
    return variant


def _annotate_variant_result(variant: VariantResult) -> VariantResult:
    """Attach explicit RDKit-only rationale boundaries to an existing variant."""
    variant.rdkit_validated = True
    variant.generation_rationale = (
        f"{variant.modification_type}: RDKit sanitized single-fragment structural edit; "
        f"{variant.modification_detail}"
    )
    variant.rationale_boundary = LEAD_VARIANT_RATIONALE_BOUNDARY
    variant.validation_notes = (
        "MolFromSmiles parsed; Chem.GetMolFrags count=1; canonical SMILES differs from parent."
    )
    return variant


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
                model="llama-3.3-70b-versatile",
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
                except Exception as e:
                    logger.warning("Gemini model %s attempt failed: %s", model_name, e)
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


# ============================================================================
# GOAL → RECEPTOR AUTO-MAPPING
# ============================================================================
# 최적화 목표별 최적 수용체 자동 매핑 (RECEPTOR_DATABASE의 PDB ID 사용)
# 학생이 목표를 선택하면 적합한 수용체가 자동 선택되어 "원클릭" 경험 제공
GOAL_RECEPTOR_MAP: Dict[str, List[str]] = {
    "항암 효과 추가": ["1M17", "5KIR"],     # EGFR, COX-2
    "BBB 투과 개선": ["4EY7", "2HYY"],      # B2AR (BBB-related GPCR), AChE (뇌 표적)
    "대사 안정성 향상": ["3ERT"],            # ERa (대사 경로 관련)
    "수용성 개선": [],                       # 수용체 불필요 (물리화학적 최적화)
    "지속 시간 개선": ["3ERT"],              # ERa (단백질 결합/대사 관련)
    "선택성 향상": [],                       # 사용자가 직접 수용체 선택
    "custom": [],                            # 사용자 수동 선택
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
            if not isinstance(data, dict):
                logger.warning("LLM 응답이 dict가 아님: type=%s", type(data).__name__)
            else:
                # N코드: LLM 응답 필드별 타입 가드
                strategies_raw = data.get("strategies", ["r_group", "bioisostere"])
                if not isinstance(strategies_raw, list):
                    logger.warning("strategies가 list가 아님: type=%s", type(strategies_raw).__name__)
                    strategies_raw = ["r_group", "bioisostere"]
                subs_raw = data.get("preferred_substituents", ["F", "OH", "NH2"])
                if not isinstance(subs_raw, list):
                    logger.warning("preferred_substituents가 list가 아님: type=%s", type(subs_raw).__name__)
                    subs_raw = ["F", "OH", "NH2"]
                return ModificationStrategy(
                    name="AI-designed optimization",
                    name_kr=f"AI 최적화: {goal_text[:20]}",
                    description=str(data.get("rationale", goal_text)),
                    strategies=strategies_raw,
                    preferred_substituents=subs_raw,
                    target_protein=str(data.get("target_protein_pdb", "")),
                    rationale=str(data.get("rationale", "AI 생성 전략")),
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"LLM JSON parse failed: {e}")

    # 3. 범용 fallback
    return ModificationStrategy(
        name="Broad optimization",
        name_kr="범용 최적화",
        description="다양한 치환기를 시도하여 최적 유도체 탐색",
        strategies=["r_group", "bioisostere", "chain", "ring"],
        preferred_substituents=["F", "Cl", "O", "N", "C(F)(F)F", "OC", "C#N"],
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
    ("COOH→아실설폰아미드", "C(=O)[OH]", "C(=O)NS(=O)(=O)C", "카르복실산 → 아실설폰아미드 (대사 안정)"),
    ("페닐→피리딜", "c1ccccc1", "c1ccncc1", "벤젠 → 피리딘 (수용성 증가, LogP 감소)"),
    ("페닐→피리미딜", "c1ccccc1", "c1ccncn1", "벤젠 → 피리미딘 (수용성 대폭 증가)"),
    ("에스터→아미드", "C(=O)OC", "C(=O)NC", "에스터 → 아미드 (대사 안정성 증가)"),
    ("에스터→역아미드", "C(=O)OC", "NCC(=O)", "에스터 → 역아미드 (결합 방향 역전)"),
    ("-NH-→-O-", "[NH]", "O", "아민 → 에테르 (수소결합 공여 제거)"),
    ("-OH→-NH2", "[OH]", "[NH2]", "하이드록시 → 아미노 (염기성 추가)"),
    ("-CH2-→-O-", "[CH2]", "O", "메틸렌 → 산소 (극성 증가)"),
    ("-CH2-→-NH-", "[CH2]", "[NH]", "메틸렌 → 아민 (염기성 추가)"),
    ("페놀→인돌", "Oc1ccccc1", "c1ccc2[nH]ccc2c1", "페놀 → 인돌 (소수성 증가)"),
    ("설파이드→설폰", "CSC", "CS(=O)(=O)C", "티오에테르 → 설폰 (대사 안정)"),
    ("아세틸→MeSO2", "C(=O)C", "CS(=O)(=O)", "카르보닐 → 메탄설포닐 (대사 안정)"),
    ("t-부틸→아다만틸", "C(C)(C)C", "C12CC3CC(CC(C3)C1)C2", "t-부틸 → 아다만틸 (소수성 증가, 대사 차단)"),
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

        # 치환 가능한 위치: 방향족 H → 지방족 C-H → CH4 전체
        matches = []
        arom_h_pat = Chem.MolFromSmarts("[cH]")
        if arom_h_pat is not None:
            matches = list(mol.GetSubstructMatches(arom_h_pat))

        if not matches:
            # 방향족 없으면 지방족 C-H 위치 시도 (CH4 포함하도록 [CH4] 추가)
            aliph_pat = Chem.MolFromSmarts("[CH4,CH3,CH2,CH]")
            if aliph_pat:
                matches = list(mol.GetSubstructMatches(aliph_pat))

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
                        logger.warning("[Rule L] MolFromSmiles 실패: %r", sub_smi)
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
                        new_smi = Chem.MolToSmiles(ed, canonical=True)
                        new_smi = _canonical_single_fragment_smiles(new_smi, parent_smi, "r_group")
                        if new_smi is None:
                            continue
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
                            else:
                                logger.warning("[Rule L] MolFromSmiles 실패: %r", new_smi)
                    except Exception as e:
                        logger.warning("R-group sanitization failed for atom %d: %s", atom_idx, e)
                        continue
                except Exception as e:
                    logger.warning("R-group variant generation failed for atom %d: %s", atom_idx, e)
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
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", repl_smi)
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
                        except Exception as e:
                            logger.warning("Bioisostere sanitization failed for %s: %s", name, e)
                            continue
            except Exception as e:
                logger.warning("Bioisostere variant generation failed for %s: %s", name, e)
                continue

        return results

    def generate_chain_variants(self, mol, max_count: int = 10) -> List[VariantResult]:
        """알킬 사슬 길이 변형 (CH2 삽입/제거) + 메틸 제거/추가."""
        if not RDKIT_OK or mol is None:
            return []

        parent_smi = Chem.MolToSmiles(mol)
        results = []
        seen = {parent_smi}

        def _try_replace(src_smarts, repl_smiles, desc, limit=3):
            """SMARTS→SMILES 치환을 시도하고 유효한 결과를 results에 추가."""
            src_pat = Chem.MolFromSmarts(src_smarts)
            repl_mol = Chem.MolFromSmiles(repl_smiles)
            if src_pat is None or repl_mol is None or not mol.HasSubstructMatch(src_pat):  # Rule L: None guard
                logger.warning("[Rule L] MolFromSmiles 실패: %r", repl_smiles)
                return
            try:
                reps = AllChem.ReplaceSubstructs(mol, src_pat, repl_mol)
                for rep in reps[:limit]:
                    if len(results) >= max_count:
                        return
                    try:
                        Chem.SanitizeMol(rep)
                        new_smi = Chem.MolToSmiles(rep)
                        if new_smi and new_smi not in seen:
                            check = Chem.MolFromSmiles(new_smi)
                            if check is not None:  # Rule L: None guard
                                seen.add(new_smi)
                                results.append(VariantResult(
                                    smiles=new_smi, parent_smiles=parent_smi,
                                    modification_type="chain",
                                    modification_detail=desc,
                                ))
                            else:
                                logger.warning("[Rule L] MolFromSmiles 실패 (chain check): %r", new_smi)
                    except Exception as e:
                        logger.warning("Chain variant sanitization failed: %s", e)
                        continue
            except Exception as e:
                logger.warning("Chain variant replacement failed: %s", e)

        # CH2CH2 → CH2 (사슬 단축)
        _try_replace("[CH2][CH2]", "C", "CH₂ 제거 (사슬 단축)")

        # CH2 → CH2CH2 (사슬 연장)
        _try_replace("[CH2]", "CC", "CH₂ 삽입 (사슬 연장)")

        # CH3 → H (메틸기 제거, N-demethylation 유사)
        _try_replace("[CH3]", "[H]", "메틸기 제거 (탈메틸화)")

        # O-CH3 → O-CH2CH3 (에톡시화)
        _try_replace("[OH1]", "OC", "하이드록시 → 메톡시 (친유성 증가)")

        # -OC → -OCC (메톡시 → 에톡시 연장)
        _try_replace("O[CH3]", "OCC", "메톡시 → 에톡시 (사슬 연장)")

        return results[:max_count]

    def generate_ring_variants(self, mol, max_count: int = 10) -> List[VariantResult]:
        """고리 변형 (방향족↔포화, 5원↔6원)."""
        if not RDKIT_OK or mol is None:
            return []

        parent_smi = Chem.MolToSmiles(mol)
        results = []
        seen = {parent_smi}

        # 고리 교환 라이브러리 — bioisostere와 독립적인 변환 포함
        ring_swaps = [
            ("c1ccccc1", "c1ccnc(N)n1", "벤젠→아미노피리미딘"),
            ("c1ccccc1", "c1cc[nH]c1", "벤젠→피롤 (5원 방향족)"),
            ("c1ccccc1", "c1ccoc1", "벤젠→퓨란 (5원 방향족)"),
            ("c1ccccc1", "c1ccsc1", "벤젠→티오펜 (5원 방향족)"),
            ("c1ccccc1", "c1ccc2[nH]ccc2c1", "벤젠→인돌 (이환)"),
            ("c1ccccc1", "c1ccc2ccccc2c1", "벤젠→나프탈렌 (이환)"),
            ("C1CCCC1", "C1CCCCC1", "5원→6원 확장"),
            ("C1CCCCC1", "C1CCCC1", "6원→5원 축소"),
            ("C1CCCCC1", "C1CCNCC1", "사이클로헥산→피페리딘"),
            ("C1CCCC1", "C1CCNC1", "사이클로펜탄→피롤리딘"),
        ]

        for src_smi, dst_smi, desc in ring_swaps:
            if len(results) >= max_count:
                break
            try:
                src = Chem.MolFromSmarts(src_smi)
                if src is None:  # Rule L: None guard — fallback to SMILES
                    src = Chem.MolFromSmiles(src_smi)
                dst = Chem.MolFromSmiles(dst_smi)
                if src is not None and dst is not None and mol.HasSubstructMatch(src):  # Rule L: None guard
                    reps = AllChem.ReplaceSubstructs(mol, src, dst)
                    for rep in reps[:2]:
                        try:
                            Chem.SanitizeMol(rep)
                            new_smi = Chem.MolToSmiles(rep)
                            if new_smi and new_smi not in seen:
                                check = Chem.MolFromSmiles(new_smi)
                                if check is not None:  # Rule L: None guard
                                    seen.add(new_smi)
                                    results.append(VariantResult(
                                        smiles=new_smi, parent_smiles=parent_smi,
                                        modification_type="ring",
                                        modification_detail=desc,
                                    ))
                        except Exception as e:
                            logger.warning("Ring variant sanitization failed: %s", e)
                            continue
                else:
                    if src is None:
                        logger.warning("[Rule L] MolFromSmiles 실패 (src): %r", src_smi)
                    if dst is None:
                        logger.warning("[Rule L] MolFromSmiles 실패 (dst): %r", dst_smi)
            except Exception as e:
                logger.warning("Ring variant generation failed for %s: %s", name, e)
                continue

        return results

    def generate_all(self, smiles: str, n_target: int = 50,
                     strategy: ModificationStrategy = None) -> List[VariantResult]:
        """전략에 따라 유도체 생성. 중복 제거 후 n_target개 반환.

        전략이 주어지면 해당 전략 우선으로 생성하되, 결과가 부족하면
        나머지 전략도 시도하여 최소 variant 수를 확보한다.
        """
        if not RDKIT_OK:
            return []

        normalized_smiles, normalized_name = normalize_lead_optimizer_input(smiles)
        mol = Chem.MolFromSmiles(normalized_smiles)
        if mol is None:
            logger.warning(
                "[Rule L] MolFromSmiles failed for lead optimizer input: %r "
                "(normalized=%r, alias=%r). Enter a valid SMILES or supported "
                "common name such as cadaverine.",
                smiles,
                normalized_smiles,
                normalized_name,
            )
            return []
        parent_smi = Chem.MolToSmiles(mol, canonical=True)

        strategies = strategy.strategies if strategy else ["r_group", "bioisostere", "chain", "ring"]
        preferred = strategy.preferred_substituents if strategy else []

        all_variants = []
        n_strat = max(1, len(strategies))

        # ── 전략별 할당량 계산 ──
        # r_group은 가장 많이 생성되므로 다른 전략에 최소 슬롯 보장
        # non-r_group 전략당 최소 10개, r_group은 나머지
        non_rgroup = [s for s in strategies if s != "r_group"]
        non_rgroup_alloc = min(15, n_target // 4)  # 전략당 최대 15개
        rgroup_alloc = n_target - len(non_rgroup) * non_rgroup_alloc

        # ── 1차: 요청된 전략 실행 (r_group 이외 먼저) ──
        if "bioisostere" in strategies:
            all_variants.extend(
                self.generate_bioisostere_variants(mol, non_rgroup_alloc)
            )
        if "chain" in strategies:
            all_variants.extend(
                self.generate_chain_variants(mol, non_rgroup_alloc)
            )
        if "ring" in strategies:
            all_variants.extend(
                self.generate_ring_variants(mol, non_rgroup_alloc)
            )
        if "r_group" in strategies:
            all_variants.extend(
                self.generate_r_group_variants(mol, preferred, max(rgroup_alloc, 10))
            )

        # ── 2차: 부족하면 나머지 전략도 시도 (다양성 확보) ──
        # 최소 3개 이상의 variant를 확보하기 위한 보충 생성
        MIN_VARIANTS = 3  # 약물 유사 분자 최소 variant 수
        fallback_limit = max(5, n_target // 4)  # 보충 전략당 최대 생성 수
        all_strategy_names = ["r_group", "bioisostere", "chain", "ring"]
        if len(all_variants) < MIN_VARIANTS:
            for strat_name in all_strategy_names:
                if strat_name in strategies:
                    continue  # 이미 시도함
                if strat_name == "r_group":
                    all_variants.extend(
                        self.generate_r_group_variants(mol, preferred, fallback_limit)
                    )
                elif strat_name == "bioisostere":
                    all_variants.extend(
                        self.generate_bioisostere_variants(mol, fallback_limit)
                    )
                elif strat_name == "chain":
                    all_variants.extend(
                        self.generate_chain_variants(mol, fallback_limit)
                    )
                elif strat_name == "ring":
                    all_variants.extend(
                        self.generate_ring_variants(mol, fallback_limit)
                    )

        # 중복 제거
        seen = set()
        unique = []
        for v in all_variants:
            valid_smi = _canonical_single_fragment_smiles(
                v.smiles,
                parent_smi,
                getattr(v, "modification_type", "variant"),
            )
            if valid_smi and valid_smi not in seen:
                v.smiles = valid_smi
                seen.add(valid_smi)
                unique.append(_annotate_variant_result(v))

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
    """Synthetic Accessibility Score (1=쉬움, 10=어려움).

    RDKit sascorer (Ertl & Schuffenhauer) 기반.
    매우 작은 분자(heavy atoms ≤ 5)는 sascorer가 비정상적으로 높은 값을
    반환하므로 보정 적용: 간단한 분자는 합성이 쉽다는 화학적 직관 반영.
    """
    if not RDKIT_OK:
        return 5.0
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            return 8.0

        n_heavy = mol.GetNumHeavyAtoms()

        # RDKit SA Score (Ertl & Schuffenhauer)
        from rdkit.Chem import RDConfig
        import sys
        sa_path = os.path.join(RDConfig.RDContribDir, 'SA_Score')
        if sa_path not in sys.path:
            sys.path.insert(0, sa_path)
        try:
            import sascorer
            raw_score = sascorer.calculateScore(mol)
        except ImportError:
            # Fallback: 간단한 휴리스틱
            n_rings = rdMolDescriptors.CalcNumRings(mol)
            n_stereo = rdMolDescriptors.CalcNumAtomStereoCenters(mol)
            # 간단 근사: 무거울수록, 복잡할수록 합성 어려움
            raw_score = 1.0 + n_rings * 0.5 + n_stereo * 1.0 + max(0, (n_heavy - 10)) * 0.15
            raw_score = min(10.0, max(1.0, raw_score))

        # ── 소분자 보정 ──────────────────────────────────────────
        # sascorer는 heavy atoms ≤ 5인 분자에 대해 비정상적으로 높은
        # 점수를 매기는 경향이 있음 (예: methane=7.3, ethane=2.8).
        # 실제로 이런 분자들은 합성이 매우 쉬우므로 상한을 적용.
        if n_heavy <= 2:
            # 1~2 heavy atoms: 합성 극히 쉬움 (methane, ethane, methanol 등)
            raw_score = min(raw_score, 1.5)  # 상한 1.5
        elif n_heavy <= 5:
            # 3~5 heavy atoms: 여전히 간단한 분자 (ethanol, acetone 등)
            raw_score = min(raw_score, 2.5)  # 상한 2.5

        return round(raw_score, 2)
    except Exception as e:
        logger.warning("SA score calculation failed, returning default 5.0: %s", e)
        return 5.0
