"""
pubchem_client.py — ChemGrid 공통 PubChem API 클라이언트
=========================================================
- API 키: a2808d0d729397dd8d063c86ff3fa3145d08
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

import re
import time
import threading
import logging
import urllib.parse
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── PubChem API 키 ──────────────────────────────────────────────────────────
PUBCHEM_API_KEY: str = "a2808d0d729397dd8d063c86ff3fa3145d08"

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
    """
    속도 제한 + API 키를 적용한 PubChem GET 요청.
    성공 시 Response 객체 반환, 실패 시 None 반환.
    """
    if not REQUESTS_AVAILABLE or _requests is None:
        return None
    _rate_limiter.wait()
    try:
        # PubChem PUG REST는 api_key 쿼리 파라미터 또는 X-API-Key 헤더 지원
        resp = _requests.get(
            url,
            params={"api_key": PUBCHEM_API_KEY},
            headers={"X-API-Key": PUBCHEM_API_KEY},
            timeout=timeout,
        )
        return resp
    except Exception as e:
        logger.warning(f"PubChem GET 오류 ({url[:60]}...): {e}")
        return None


# ── 공개 API 함수 ──────────────────────────────────────────────────────────

def get_smiles_by_name(name: str) -> Optional[str]:
    """
    분자명(관용명/IUPAC명/한국명 등) → IsomericSMILES 조회.
    실패 시 None 반환.
    """
    if not REQUESTS_AVAILABLE or not name:
        return None
    try:
        url = (
            f"{BASE_URL}/compound/name/"
            f"{urllib.parse.quote(name)}/property/IsomericSMILES/JSON"
        )
        resp = _get(url, timeout=5)
        if resp is None or resp.status_code != 200:
            return None
        props = resp.json().get("PropertyTable", {}).get("Properties", [])
        if props:
            # PubChem이 "IsomericSMILES" 또는 "SMILES" 키 중 하나로 반환
            p = props[0]
            return p.get("IsomericSMILES") or p.get("SMILES")
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
        props = resp.json().get("PropertyTable", {}).get("Properties", [])
        if not props:
            return None
        p = props[0]
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
                syn_info = (
                    syn_resp.json()
                    .get("InformationList", {})
                    .get("Information", [{}])
                )
                synonyms = syn_info[0].get("Synonym", []) if syn_info else []
                for syn in synonyms:
                    if re.match(r"^\d{2,7}-\d{2}-\d$", syn):
                        result["cas_number"] = syn
                        break
        return result
    except Exception as e:
        logger.warning(f"get_info_by_smiles 실패: {e}")
    return None


def get_iupac_name_by_smiles(smiles: str) -> Optional[str]:
    """
    SMILES → IUPAC명 조회.
    실패 시 None 반환.
    """
    if not REQUESTS_AVAILABLE or not smiles:
        return None
    try:
        url = (
            f"{BASE_URL}/compound/smiles/"
            f"{urllib.parse.quote(smiles, safe='')}/property/IUPACName/JSON"
        )
        resp = _get(url, timeout=5)
        if resp is None or resp.status_code != 200:
            return None
        props = resp.json().get("PropertyTable", {}).get("Properties", [])
        if props:
            return props[0].get("IUPACName")
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
        return resp.json().get("dictionary_terms", {}).get("compound", [])
    except Exception as e:
        logger.warning(f"get_suggestions({name!r}) 실패: {e}")
    return []
