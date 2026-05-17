"""
pubchem_client.py — ChemGrid 공통 PubChem API 클라이언트
=========================================================
- API 키: .env 파일에서 PUBCHEM_API_KEY 로드
- 속도 제한: 초당 최대 1회 호출 (PubChem 허용 3회/초이지만 안전하게 1회로 제한)
- 모든 PubChem REST 호출은 이 모듈을 통해야 합니다.

사용법:
    import pubchem_client as pc
    smiles = pc.get_smiles_by_name("dopamine")
    info   = pc.get_info_by_smiles("NCCc1ccc(O)c(O)c1")
    iupac  = pc.get_iupac_name_by_smiles("CCO")
    suggs  = pc.get_suggestions("acetaminoph")
"""
from __future__ import annotations

import os
import re
import time
import threading
import logging
import urllib.parse
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── .env 로드 ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logger.warning("python-dotenv 모듈 없음 — .env 파일 자동 로드 비활성화")

# ── PubChem API 키 (.env에서 로드) ─────────────────────────────────────────
PUBCHEM_API_KEY: str = os.getenv("PUBCHEM_API_KEY", "")

# ── requests 가용성 확인 ────────────────────────────────────────────────────
_requests = None
REQUESTS_AVAILABLE: bool = False
try:
    import requests as _requests  # type: ignore
    REQUESTS_AVAILABLE = True
except ImportError:
    logger.warning("requests 모듈 없음 — PubChem API 비활성화")

# ── 전역 속도 제한기 (초당 1회) ────────────────────────────────────────────
class _RateLimiter:
    """초당 최대 N회 호출을 보장하는 스레드 안전 속도 제한기."""

    def __init__(self, calls_per_second: float = 1.0):
        self._min_interval: float = 1.0 / max(calls_per_second, 0.01)
        self._last_call: float = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """필요 시 대기 후 호출 허가."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            wait_for = self._min_interval - elapsed
            if wait_for > 0:
                time.sleep(wait_for)
            self._last_call = time.monotonic()


_rate_limiter = _RateLimiter(calls_per_second=1.0)  # 안전 제한: 초당 1회

BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


# ── 내부 GET 헬퍼 ──────────────────────────────────────────────────────────
def _get(url: str, timeout: int = 10):
    """속도 제한 + API 키를 적용한 PubChem GET 요청.

    성공 시 Response 객체 반환, 실패 시 None 반환.

    M1363 SSL 복구 전략:
      1차: verify=True (default, 인증서 검증) — 정상 환경
      2차: SSLEOFError/SSLError 발생 시 verify=False + 경고 로그 (Rule M: silent 금지)
      근거: UNEXPECTED_EOF_WHILE_READING는 방화벽/프록시 TLS 차단 패턴 (D888_W17)
    Rule M: None 반환 전 logger.warning 필수.
    """
    if not REQUESTS_AVAILABLE or _requests is None:
        return None
    _rate_limiter.wait()

    _kwargs = dict(
        params={"api_key": PUBCHEM_API_KEY},
        headers={"X-API-Key": PUBCHEM_API_KEY},
        timeout=timeout,
    )

    try:
        # 1차 시도: verify=True (정상 TLS 검증)
        # PubChem PUG REST는 api_key 쿼리 파라미터 또는 X-API-Key 헤더 지원
        # _requests is the 'requests' module (not a dict) — already guarded above
        resp = _requests.get(url, **_kwargs)
        return resp
    except Exception as e:
        _ename = type(e).__name__
        _emsg  = str(e)
        # SSLEOFError / SSLError → verify=False fallback (M1363: 방화벽 환경 대응)
        _is_ssl = (
            "SSL" in _ename
            or "ssl" in _emsg.lower()
            or "UNEXPECTED_EOF" in _emsg
            or "certificate" in _emsg.lower()
            or "handshake" in _emsg.lower()
        )
        if _is_ssl:
            logger.warning(
                "[M1363] PubChem SSL 오류 → verify=False 재시도 (%s): %s",
                url[:60], _emsg[:120]
            )
            try:
                resp = _requests.get(url, verify=False, **_kwargs)
                return resp
            except Exception as e2:
                logger.warning(
                    "[M1363] PubChem verify=False 재시도도 실패 (%s): %s",
                    url[:60], str(e2)[:120]
                )
                return None
        logger.warning("PubChem GET 오류 (%s...): %s", url[:60], _emsg[:120])
        return None


# ── 타입 가드 헬퍼 (N코드: 외부 API 데이터 isinstance 필수) ────────────────
def _safe_get_properties(resp_json: Any) -> List[Dict[str, Any]]:
    """PubChem JSON 응답에서 PropertyTable.Properties를 타입 안전하게 추출.

    외부 API 응답이므로 각 단계마다 isinstance 가드를 적용한다.
    반환값: list[dict] (실패 시 빈 리스트)
    """
    if not isinstance(resp_json, dict):
        logger.warning("PubChem 응답이 dict가 아님: type=%s", type(resp_json).__name__)
        return []
    prop_table = resp_json.get("PropertyTable", {})
    if not isinstance(prop_table, dict):
        logger.warning("PropertyTable이 dict가 아님: type=%s", type(prop_table).__name__)
        return []
    props = prop_table.get("Properties", [])
    if not isinstance(props, list):
        logger.warning("Properties가 list가 아님: type=%s", type(props).__name__)
        return []
    return props


# ── 공개 API 함수 ──────────────────────────────────────────────────────────

def get_smiles_by_name(name: str) -> Optional[str]:
    """
    분자명(관용명/IUPAC명/한국명 등) → SMILES 조회.
    IsomericSMILES > CanonicalSMILES > ConnectivitySMILES 순으로 반환.
    실패 시 None 반환.
    """
    if not REQUESTS_AVAILABLE or not name:
        return None
    try:
        url = (
            f"{BASE_URL}/compound/name/"
            f"{urllib.parse.quote(name)}/property/IsomericSMILES,CanonicalSMILES/JSON"
        )
        resp = _get(url, timeout=5)
        if resp is None or resp.status_code != 200:
            return None
        props = _safe_get_properties(resp.json())
        if props:
            p = props[0]
            if not isinstance(p, dict):
                logger.warning("Properties[0]이 dict가 아님: type=%s", type(p).__name__)
                return None
            return (p.get("IsomericSMILES") or p.get("CanonicalSMILES")
                    or p.get("ConnectivitySMILES") or p.get("SMILES"))
    except Exception as e:
        logger.warning(f"get_smiles_by_name({name!r}) 실패: {e}")
    return None


def get_info_by_smiles(smiles: str) -> Optional[Dict[str, Any]]:
    """
    SMILES → PubChem 분자 정보 딕셔너리 조회.
    CAS 번호 포함 (동의어 추가 1회 호출).
    실패 시 None 반환.
    """
    if not REQUESTS_AVAILABLE or not smiles:
        return None
    try:
        url = (
            f"{BASE_URL}/compound/smiles/"
            f"{urllib.parse.quote(smiles, safe='')}/property/"
            f"IUPACName,MolecularFormula,MolecularWeight,XLogP,TPSA,Complexity,"
            f"HBondDonorCount,HBondAcceptorCount,RotatableBondCount,ExactMass/JSON"
        )
        resp = _get(url, timeout=10)
        if resp is None or resp.status_code != 200:
            return None
        props = _safe_get_properties(resp.json())
        if not props:
            return None
        p = props[0]
        if not isinstance(p, dict):
            logger.warning("Properties[0]이 dict가 아님: type=%s", type(p).__name__)
            return None
        cid = p.get("CID")
        result: Dict[str, Any] = {
            "cid": cid,
            "iupac_name": p.get("IUPACName", ""),
            "molecular_formula": p.get("MolecularFormula", ""),
            "molecular_weight": p.get("MolecularWeight", ""),
            "xlogp": p.get("XLogP", ""),
            "tpsa": p.get("TPSA", ""),
            "complexity": p.get("Complexity", ""),
            "hbd": p.get("HBondDonorCount", ""),
            "hba": p.get("HBondAcceptorCount", ""),
            "rotatable_bonds": p.get("RotatableBondCount", ""),
            "exact_mass": p.get("ExactMass", ""),
            "cas_number": "",
            "source": "PubChem DB",
        }
        # CAS 번호 조회 (추가 rate-limited 1회 호출)
        if cid:
            syn_url = f"{BASE_URL}/compound/cid/{cid}/synonyms/JSON"
            syn_resp = _get(syn_url, timeout=10)
            if syn_resp and syn_resp.status_code == 200:
                syn_json = syn_resp.json()
                if not isinstance(syn_json, dict):
                    logger.warning("동의어 응답이 dict가 아님: type=%s", type(syn_json).__name__)
                else:
                    info_list = syn_json.get("InformationList", {})
                    if not isinstance(info_list, dict):
                        logger.warning("InformationList가 dict가 아님: type=%s", type(info_list).__name__)
                        info_list = {}
                    syn_info = info_list.get("Information", [])
                    if not isinstance(syn_info, list):
                        logger.warning("Information이 list가 아님: type=%s", type(syn_info).__name__)
                        syn_info = []
                    if syn_info:
                        first_info = syn_info[0]
                        if isinstance(first_info, dict):
                            synonyms = first_info.get("Synonym", [])
                            if isinstance(synonyms, list):
                                for syn in synonyms:
                                    if isinstance(syn, str) and re.match(r"^\d{2,7}-\d{2}-\d$", syn):
                                        result["cas_number"] = syn
                                        break
        return result
    except Exception as e:
        logger.warning(f"get_info_by_smiles 실패: {e}")
    return None


def get_iupac_name_by_smiles(smiles: str) -> Optional[str]:
    """
    SMILES → IUPAC명 또는 관용명(Title) 조회.
    IUPACName 우선, 없으면 Title(관용명) 폴백.
    대형 분자(헤모글로빈 등)는 IUPAC 없이 Title만 존재할 수 있음.
    실패 시 None 반환.
    """
    if not REQUESTS_AVAILABLE or not smiles:
        return None
    try:
        url = (
            f"{BASE_URL}/compound/smiles/"
            f"{urllib.parse.quote(smiles, safe='')}/property/IUPACName,Title/JSON"
        )
        resp = _get(url, timeout=5)
        if resp is None or resp.status_code != 200:
            return None
        props = _safe_get_properties(resp.json())
        if props:
            p0 = props[0]
            if isinstance(p0, dict):
                iupac = p0.get("IUPACName")
                if iupac:
                    return iupac
                # IUPAC 없으면 Title(관용명) 폴백
                title = p0.get("Title")
                if title:
                    return title
            else:
                logger.warning("Properties[0]이 dict가 아님: type=%s", type(p0).__name__)
    except Exception as e:
        logger.warning(f"get_iupac_name_by_smiles 실패: {e}")
    return None


def get_suggestions(name: str, limit: int = 3) -> List[str]:
    """
    PubChem Autocomplete로 분자명 제안 목록 반환.
    실패 시 빈 리스트 반환.
    """
    if not REQUESTS_AVAILABLE or not name:
        return []
    try:
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/autocomplete/compound/"
            f"{urllib.parse.quote(name)}/JSON?limit={limit}"
        )
        resp = _get(url, timeout=5)
        if resp is None or resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, dict):
            logger.warning("Autocomplete 응답이 dict가 아님: type=%s", type(data).__name__)
            return []
        dict_terms = data.get("dictionary_terms", {})
        if not isinstance(dict_terms, dict):
            logger.warning("dictionary_terms가 dict가 아님: type=%s", type(dict_terms).__name__)
            return []
        compound = dict_terms.get("compound", [])
        if not isinstance(compound, list):
            logger.warning("compound가 list가 아님: type=%s", type(compound).__name__)
            return []
        return compound
    except Exception as e:
        logger.warning(f"get_suggestions({name!r}) 실패: {e}")
    return []
