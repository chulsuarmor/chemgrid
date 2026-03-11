# text_input_handler.py (v2.0 - Gemini API 연동 분자 이름 해석)
# 변경 이력:
#   v2.0: [FEAT] Gemini API를 통한 화학명/분자식/IUPAC → SMILES 자동 변환
#         [FEAT] 로컬 사전(80+ 분자) 우선 조회 → API 폴백
#         [FEAT] RDKit 유효성 검증 후 SMILES 반환
#         [FIX] v1.0의 하드코딩 3개 이름 + drawing_tools 의존성 제거
#   v1.0: 관용명(한국어 3개) 또는 직접 SMILES 입력만 지원

import os
import logging
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# Gemini API 키 로드
# ============================================================================
_GEMINI_API_KEY: Optional[str] = None
try:
    from dotenv import load_dotenv
    # MCP 서버 .env 파일 로드 (프로젝트 루트 기준)
    import pathlib
    _env_path = pathlib.Path(__file__).parent.parent / "mcp_server" / ".env"
    if _env_path.exists():
        load_dotenv(str(_env_path))
    _GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
except ImportError:
    _GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

# ============================================================================
# 로컬 분자 사전 (API 호출 최소화, 자주 사용하는 분자 우선 제공)
# ============================================================================
KNOWN_SMILES: dict = {
    # ── 기본 분자 ──────────────────────────────────────────────────────
    "water": "O",
    "물": "O",
    "h2o": "O",
    "methane": "C",
    "메탄": "C",
    "ch4": "C",
    "ethane": "CC",
    "에탄": "CC",
    "propane": "CCC",
    "프로판": "CCC",
    "butane": "CCCC",
    "부탄": "CCCC",
    "pentane": "CCCCC",
    "펜탄": "CCCCC",
    "hexane": "CCCCCC",
    "헥산": "CCCCCC",

    # ── 알코올 ────────────────────────────────────────────────────────
    "methanol": "CO",
    "메탄올": "CO",
    "ethanol": "CCO",
    "에탄올": "CCO",
    "ethyl alcohol": "CCO",
    "isopropanol": "CC(O)C",
    "isopropyl alcohol": "CC(O)C",
    "2-propanol": "CC(O)C",

    # ── 방향족 ────────────────────────────────────────────────────────
    "benzene": "c1ccccc1",
    "벤젠": "c1ccccc1",
    "toluene": "Cc1ccccc1",
    "톨루엔": "Cc1ccccc1",
    "aniline": "Nc1ccccc1",
    "아닐린": "Nc1ccccc1",
    "phenol": "Oc1ccccc1",
    "페놀": "Oc1ccccc1",
    "nitrobenzene": "O=[N+]([O-])c1ccccc1",
    "나이트로벤젠": "O=[N+]([O-])c1ccccc1",
    "benzoic acid": "OC(=O)c1ccccc1",
    "벤조산": "OC(=O)c1ccccc1",
    "naphthalene": "c1ccc2ccccc2c1",
    "나프탈렌": "c1ccc2ccccc2c1",
    "anthracene": "c1ccc2cc3ccccc3cc2c1",
    "안트라센": "c1ccc2cc3ccccc3cc2c1",
    "styrene": "C=Cc1ccccc1",
    "스티렌": "C=Cc1ccccc1",
    "pyridine": "c1ccncc1",
    "피리딘": "c1ccncc1",
    "pyrrole": "c1cc[nH]c1",
    "피롤": "c1cc[nH]c1",
    "furan": "c1ccoc1",
    "퓨란": "c1ccoc1",
    "thiophene": "c1ccsc1",
    "싸이오펜": "c1ccsc1",
    "imidazole": "c1cnc[nH]1",
    "이미다졸": "c1cnc[nH]1",

    # ── 이온성 방향족 (공명 구조 균등화 대상) ───────────────────────
    "cyclopentadienyl anion": "[cH-]1cccc1",
    "사이클로펜타디에닐 음이온": "[cH-]1cccc1",
    "cp-": "[cH-]1cccc1",
    "cyclopentadienyl": "C1=CC=CC1",
    "tropylium": "[CH+]1=CC=CC=CC1",
    "tropylium ion": "[CH+]1=CC=CC=CC1",
    "트로필리움": "[CH+]1=CC=CC=CC1",
    "트로필리움 이온": "[CH+]1=CC=CC=CC1",
    "cycloheptatrienyl cation": "[CH+]1=CC=CC=CC1",

    # ── 카르보닐 화합물 ───────────────────────────────────────────────
    "formaldehyde": "C=O",
    "포름알데히드": "C=O",
    "acetaldehyde": "CC=O",
    "아세트알데히드": "CC=O",
    "acetone": "CC(=O)C",
    "아세톤": "CC(=O)C",
    "acetic acid": "CC(=O)O",
    "아세트산": "CC(=O)O",
    "formic acid": "OC=O",
    "포름산": "OC=O",

    # ── 아미노산 ──────────────────────────────────────────────────────
    "glycine": "NCC(=O)O",
    "글리신": "NCC(=O)O",
    "alanine": "C[C@@H](N)C(=O)O",
    "알라닌": "C[C@@H](N)C(=O)O",
    "serine": "N[C@@H](CO)C(=O)O",
    "세린": "N[C@@H](CO)C(=O)O",

    # ── 약물/생체 분자 ────────────────────────────────────────────────
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "아스피린": "CC(=O)Oc1ccccc1C(=O)O",
    "acetylsalicylic acid": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "카페인": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "글루코스": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "fructose": "OC[C@@H]1OC(O)(CO)[C@H](O)[C@@H]1O",
    "프럭토스": "OC[C@@H]1OC(O)(CO)[C@H](O)[C@@H]1O",
    "sucrose": "OC[C@H]1O[C@@](CO)(O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)[C@@H](O)[C@@H]1O",
    "succinic acid": "OC(=O)CCC(=O)O",
    "glutamic acid": "N[C@@H](CCC(=O)O)C(=O)O",
    "glutamine": "N[C@@H](CCC(N)=O)C(=O)O",
    "adenine": "Nc1ncnc2ncnc12",
    "아데닌": "Nc1ncnc2ncnc12",
    "guanine": "Nc1nc2[nH]cnc2c(=O)[nH]1",
    "구아닌": "Nc1nc2[nH]cnc2c(=O)[nH]1",
    "uracil": "O=c1cc[nH]c(=O)[nH]1",
    "우라실": "O=c1cc[nH]c(=O)[nH]1",
    "thymine": "Cc1c[nH]c(=O)[nH]c1=O",
    "타이민": "Cc1c[nH]c(=O)[nH]c1=O",
    "cytosine": "Nc1cc[nH]c(=O)n1",
    "사이토신": "Nc1cc[nH]c(=O)n1",
    "cholesterol": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
    "콜레스테롤": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "이부프로펜": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "acetaminophen": "CC(=O)Nc1ccc(O)cc1",
    "타이레놀": "CC(=O)Nc1ccc(O)cc1",

    # ── 폴리머/고분자 단량체 ────────────────────────────────────────
    "ethylene": "C=C",
    "에틸렌": "C=C",
    "propylene": "CC=C",
    "vinyl chloride": "ClC=C",
    "acrylonitrile": "C=CC#N",

    # ── 무기 분자 ────────────────────────────────────────────────────
    "ammonia": "N",
    "암모니아": "N",
    "nh3": "N",
    "hydrogen chloride": "Cl",
    "hydrochloric acid": "Cl",
    "carbon dioxide": "O=C=O",
    "이산화탄소": "O=C=O",
    "co2": "O=C=O",
    "carbon monoxide": "[C-]#[O+]",
    "일산화탄소": "[C-]#[O+]",
    "sulfur dioxide": "O=S=O",
    "이산화황": "O=S=O",

    # ── 분자식 직접 입력 폴백 ─────────────────────────────────────────
    "c6h6": "c1ccccc1",
    "c2h5oh": "CCO",
    "ch3oh": "CO",
    "ch3ch2oh": "CCO",
    "ch3cooh": "CC(=O)O",
}


class TextInputParser:
    """
    텍스트 입력으로부터 SMILES 문자열을 해석하는 파서 (v2.0).

    우선순위:
    1. 직접 SMILES 입력 (RDKit 검증)
    2. 로컬 사전 조회 (대소문자/공백 무시)
    3. Gemini API 조회 → RDKit 유효성 검증
    """

    def __init__(self):
        self._api_key = _GEMINI_API_KEY
        self._cache: dict = {}  # API 결과 캐시 (세션 내 중복 요청 방지)

    def parse_input(self, text: str) -> Optional[Tuple[str, str]]:
        """
        텍스트 입력을 SMILES 문자열로 변환합니다.

        Args:
            text: 사용자 입력 (화학명, 분자식, SMILES, IUPAC명 등)

        Returns:
            ('smiles', smiles_string) 또는 None (인식 실패)
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # ── 1단계: 직접 SMILES 입력 여부 확인 ──────────────────────────
        smiles = self._try_direct_smiles(text)
        if smiles:
            logger.info("TextInputParser: direct SMILES '%s'", smiles)
            return ("smiles", smiles)

        # ── 2단계: 로컬 사전 조회 ────────────────────────────────────
        smiles = self._lookup_local(text)
        if smiles:
            logger.info("TextInputParser: local dict match '%s' → '%s'", text, smiles)
            return ("smiles", smiles)

        # ── 3단계: PubChem PUG REST API 조회 ─────────────────────────
        smiles = self._query_pubchem(text)
        if smiles:
            logger.info("TextInputParser: PubChem resolved '%s' → '%s'", text, smiles)
            return ("smiles", smiles)

        # ── 4단계: Gemini API 조회 (폴백) ────────────────────────────
        smiles = self._query_gemini(text)
        if smiles:
            logger.info("TextInputParser: Gemini resolved '%s' → '%s'", text, smiles)
            return ("smiles", smiles)

        logger.warning("TextInputParser: could not resolve '%s'", text)
        return None

    # ------------------------------------------------------------------
    # 1단계: SMILES 직접 입력 검증
    # ------------------------------------------------------------------
    def _try_direct_smiles(self, text: str) -> Optional[str]:
        """텍스트가 유효한 SMILES인지 RDKit으로 검증합니다."""
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(text)
            if mol is not None:
                return Chem.MolToSmiles(mol)  # 정규화된 SMILES 반환
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # 2단계: 로컬 사전 조회
    # ------------------------------------------------------------------
    def _lookup_local(self, text: str) -> Optional[str]:
        """대소문자/공백을 무시하고 로컬 사전에서 SMILES를 조회합니다."""
        key = text.lower().strip()
        # 직접 조회
        if key in KNOWN_SMILES:
            return KNOWN_SMILES[key]
        # 공백 제거 후 조회 (예: "acetic acid" → "aceticacid")
        no_space = key.replace(" ", "")
        if no_space in KNOWN_SMILES:
            return KNOWN_SMILES[no_space]
        return None

    # ------------------------------------------------------------------
    # 3단계: PubChem PUG REST API 조회 (BUG-04b/c Fix)
    # ------------------------------------------------------------------
    def _query_pubchem(self, name: str) -> Optional[str]:
        """
        PubChem PUG REST API로 화학명/분자식/CAS → SMILES 조회.

        완전 무료, 신뢰도 최고 (NIH 공식 데이터베이스):
        - 분자명 (benzene, aspirin, hemoglobin)
        - 분자식 (CH3CH2OH, C6H6)
        - IUPAC명 (2-hydroxypropanoic acid)
        - CAS 번호 (50-78-2)
        - 한국어 이름도 일부 지원
        대형 단백질(hemoglobin 등)은 SMILES 미제공 → 자동 None → Gemini 폴백
        """
        import urllib.parse

        cache_key = f"pubchem:{name.lower().strip()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        encoded = urllib.parse.quote(name.strip())
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            f"name/{encoded}/property/IsomericSMILES/JSON"
        )

        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                props = data.get("PropertyTable", {}).get("Properties", [{}])
                if props:
                    smiles = props[0].get("IsomericSMILES", "")
                    if smiles:
                        validated = self._validate_smiles(smiles)
                        self._cache[cache_key] = validated
                        return validated
            elif resp.status_code == 404:
                logger.debug("PubChem: '%s' not found", name)
            else:
                logger.warning("PubChem API %d for '%s'", resp.status_code, name)
        except requests.exceptions.Timeout:
            logger.warning("PubChem timeout for '%s'", name)
        except Exception as e:
            logger.debug("PubChem error for '%s': %s", name, e)

        self._cache[cache_key] = None
        return None

    # ------------------------------------------------------------------
    # 4단계: Gemini API 조회 (폴백)
    # ------------------------------------------------------------------
    def _query_gemini(self, name: str) -> Optional[str]:
        """
        Gemini API를 통해 화학명 → SMILES를 조회합니다.

        프롬프트 전략:
        - 전문 화학 지식을 갖춘 역할 지정
        - SMILES만 반환하도록 명시 (설명 없음)
        - 분자가 매우 크거나 알 수 없을 경우 "UNKNOWN" 반환 지시
        - RDKit으로 반환된 SMILES 유효성 최종 검증

        Args:
            name: 화학명, 분자식, IUPAC명 등

        Returns:
            유효한 SMILES 문자열 또는 None
        """
        if not self._api_key:
            logger.warning("TextInputParser: Gemini API key not configured")
            return None

        # 캐시 확인
        cache_key = name.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = (
            "You are a chemistry expert assistant. "
            "The user has entered a chemical identifier: \"{name}\"\n"
            "This may be:\n"
            "- A common chemical name (e.g., 'aspirin', 'benzene')\n"
            "- An IUPAC name (e.g., '2-hydroxypropanoic acid')\n"
            "- A molecular formula (e.g., 'C6H6', 'CH3CH2OH')\n"
            "- A Korean chemical name (e.g., '아스피린', '벤젠')\n"
            "- An abbreviation or trivial name\n\n"
            "Task: Provide ONLY the canonical SMILES string for this molecule.\n"
            "Rules:\n"
            "1. Output ONLY the SMILES string, nothing else\n"
            "2. No explanations, no punctuation, no code blocks\n"
            "3. If the molecule is too large (>200 atoms) or you cannot determine "
            "a valid SMILES, output exactly: UNKNOWN\n"
            "4. Use standard RDKit-compatible SMILES syntax\n\n"
            "Chemical identifier: {name}"
        ).format(name=name)

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-1.5-flash:generateContent"
            f"?key={self._api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,    # 낮은 온도 → 확정적 출력
                "maxOutputTokens": 256,
                "topP": 0.9,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            raw = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )

            logger.debug("Gemini raw response for '%s': '%s'", name, raw)

            if not raw or raw.upper() == "UNKNOWN":
                self._cache[cache_key] = None
                return None

            # 멀티라인 응답에서 첫 번째 줄만 사용
            first_line = raw.splitlines()[0].strip()

            # RDKit 유효성 검증
            validated = self._validate_smiles(first_line)
            self._cache[cache_key] = validated
            return validated

        except requests.exceptions.Timeout:
            logger.error("Gemini API timeout for '%s'", name)
            return None
        except requests.exceptions.HTTPError as e:
            logger.error("Gemini API HTTP error for '%s': %s", name, e)
            return None
        except Exception as e:
            logger.error("Gemini API error for '%s': %s", name, e)
            return None

    # ------------------------------------------------------------------
    # SMILES 유효성 검증
    # ------------------------------------------------------------------
    def _validate_smiles(self, smiles: str) -> Optional[str]:
        """RDKit으로 SMILES 유효성을 검증하고 정규화된 SMILES를 반환합니다."""
        if not smiles:
            return None
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                return Chem.MolToSmiles(mol)
        except Exception as e:
            logger.debug("SMILES validation failed for '%s': %s", smiles, e)
        return None

    # ------------------------------------------------------------------
    # 공개 유틸리티: SMILES → 분자식
    # ------------------------------------------------------------------
    def smiles_to_formula(self, smiles: str) -> Optional[str]:
        """SMILES에서 분자식(Hill 순서)을 계산합니다."""
        try:
            from rdkit import Chem
            from rdkit.Chem import rdMolDescriptors
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                return rdMolDescriptors.CalcMolFormula(mol)
        except Exception:
            pass
        return None
