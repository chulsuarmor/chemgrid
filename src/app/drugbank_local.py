"""
drugbank_local.py — DrugBank 로컬 데이터셋 검색 모듈 (M646_INTEGRATE)
=====================================================================
입력 파일 (data/drugbank/):
  - "drugbank vocabulary.csv" : 11,000+ 약물 메타데이터 (ID/Name/CAS/UNII/InChIKey)
  - "open structures.sdf"     : 분자 구조 SDF (RDKit Mol Block)

기능:
  1. lazy_load_vocabulary()   : CSV 라이트 로드 + Korean-friendly 검색
  2. lazy_build_sdf_index()   : SDF → Morgan fingerprint 인덱스 (1회)
  3. search_by_smiles(smiles, k=5, cutoff=0.4)
       → Tanimoto 유사도 기반 Top-k 약물 후보 (cutoff 이상)
  4. lookup_by_id(drugbank_id) / lookup_by_inchikey(key)

학술 인용 (Rule NN — academic_integrity_auto.md FP-28):
  Wishart, D.S. et al. (2018) DrugBank 5.0: a major update to the DrugBank
    database for 2018. Nucleic Acids Res. 46(D1): D1074-D1082.
  Knox, C. et al. (2024) DrugBank 6.0: the DrugBank Knowledgebase for 2024.
    Nucleic Acids Res. 52(D1): D1265-D1275.
  Rogers, D.; Hahn, M. (2010) Extended-Connectivity Fingerprints (ECFP).
    J. Chem. Inf. Model. 50(5): 742-754.

Rule 준수:
  - I (하드코딩 금지) : 경로/매직넘버 모두 [MAGIC] 주석.
  - L (SMILES 방어)   : MolFromSmiles + None 체크 + sanitize 분리.
  - M (Silent fail)   : 모든 예외 분기 logger.warning + 원인 명시.
  - N (타입 가드)     : isinstance() 가드 — CSV row dict / SDF Mol object.
  - GG (SIMULATION)   : 데이터 부재시 "DRUGBANK_DATA_MISSING" 명시.
"""

from __future__ import annotations

import csv
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 경로 설정 (Rule I: env var override 가능, 매직넘버 주석 의무)
# ─────────────────────────────────────────────────────────────────

_DEFAULT_DATA_ROOT = os.environ.get(
    "CHEMGRID_DRUGBANK_DIR",
    # housing/config.py 미사용 — 모듈 단독 사용 가능 (Rule K 준수, 단지 경로 명시)
    "C:/chemgrid/data/drugbank",
)
# DrugBank vocabulary csv (CSV header: DrugBank ID,Accession Numbers,Common name,
# CAS,UNII,Synonyms,Standard InChI Key)
_VOCAB_CSV_NAME = "drugbank vocabulary.csv"
# DrugBank open structures SDF (분자 구조 데이터)
_SDF_NAME = "open structures.sdf"

# Morgan fingerprint 파라미터 (Rogers&Hahn 2010 ECFP 기준)
_MORGAN_RADIUS = 2  # [MAGIC: 2] ECFP4 등가 (radius=2 → diameter 4 atoms)
_MORGAN_NBITS = 2048  # [MAGIC: 2048] Standard ECFP fingerprint 길이

# Tanimoto 검색 기본값
_DEFAULT_K = 5  # [MAGIC: 5] Top-k 후보 (popup 표시용)
_DEFAULT_CUTOFF = 0.4  # [MAGIC: 0.4] Tanimoto 유사도 하한 (0.4 이상이면 의미있는 매칭, ECFP4 표준)

# SDF 로딩 한도 (테스트/메모리 절약, 0=무제한)
_SDF_MAX_RECORDS = int(os.environ.get("CHEMGRID_DRUGBANK_SDF_LIMIT", "0"))

# ─────────────────────────────────────────────────────────────────
# Lazy load 상태 (스레드 안전 lock)
# ─────────────────────────────────────────────────────────────────

_LOCK = threading.RLock()
_VOCAB_CACHE: Optional[List[Dict[str, str]]] = None  # 모든 약물 메타데이터
_VOCAB_BY_ID: Dict[str, Dict[str, str]] = {}
_VOCAB_BY_INCHIKEY: Dict[str, Dict[str, str]] = {}

# SDF 인덱스 (lazy build)
_FP_INDEX: Optional[List[Tuple[str, Any]]] = None  # [(drugbank_id, fingerprint), ...]
_INDEX_BUILD_ATTEMPTED = False  # 빌드 1회 시도 후 None이면 미사용 (Rule M silent failure 차단)
_INDEX_BUILD_ERROR: Optional[str] = None


def _data_path(filename: str) -> str:
    return os.path.join(_DEFAULT_DATA_ROOT, filename)


def is_data_available() -> bool:
    """DrugBank 데이터 파일이 로컬에 존재하는지 검사 (UI 토글용)."""
    csv_ok = os.path.exists(_data_path(_VOCAB_CSV_NAME))
    sdf_ok = os.path.exists(_data_path(_SDF_NAME))
    return csv_ok and sdf_ok


def get_data_status() -> Dict[str, Any]:
    """현재 로딩 상태 (UI 진단용 — Rule M silent failure 차단)."""
    return {
        "data_root": _DEFAULT_DATA_ROOT,
        "csv_exists": os.path.exists(_data_path(_VOCAB_CSV_NAME)),
        "sdf_exists": os.path.exists(_data_path(_SDF_NAME)),
        "vocabulary_loaded": _VOCAB_CACHE is not None,
        "vocabulary_count": len(_VOCAB_CACHE) if _VOCAB_CACHE else 0,
        "fp_index_built": _FP_INDEX is not None,
        "fp_index_count": len(_FP_INDEX) if _FP_INDEX else 0,
        "build_error": _INDEX_BUILD_ERROR,
    }


# ─────────────────────────────────────────────────────────────────
# CSV 로드
# ─────────────────────────────────────────────────────────────────

def lazy_load_vocabulary() -> List[Dict[str, str]]:
    """DrugBank vocabulary CSV를 1회 lazy 로드 (스레드 안전).

    Returns: 각 row는 dict[str,str] (CSV 헤더 그대로 키).
             데이터 부재시 [] (logger.warning 출력).
    """
    global _VOCAB_CACHE, _VOCAB_BY_ID, _VOCAB_BY_INCHIKEY
    with _LOCK:
        if _VOCAB_CACHE is not None:
            return _VOCAB_CACHE
        path = _data_path(_VOCAB_CSV_NAME)
        if not os.path.exists(path):
            logger.warning(
                "[drugbank_local] vocabulary CSV missing: %s. "
                "DrugBank lookup disabled (DRUGBANK_DATA_MISSING).", path)
            _VOCAB_CACHE = []
            return _VOCAB_CACHE
        rows: List[Dict[str, str]] = []
        try:
            # utf-8-sig: CSV BOM 처리 (Rule Q 한국어/유니코드)
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not isinstance(row, dict):  # Rule N
                        continue
                    cleaned: Dict[str, str] = {}
                    for k, v in row.items():
                        if not isinstance(k, str):
                            continue
                        cleaned[k.strip()] = (v or "").strip() if isinstance(v, str) else ""
                    rows.append(cleaned)
                    drugbank_id = cleaned.get("DrugBank ID", "").upper()
                    if drugbank_id:
                        _VOCAB_BY_ID[drugbank_id] = cleaned
                    inchikey = cleaned.get("Standard InChI Key", "").strip()
                    if inchikey:
                        _VOCAB_BY_INCHIKEY[inchikey] = cleaned
        except Exception as e:  # Rule M
            logger.warning("[drugbank_local] vocabulary CSV 읽기 실패 (%s): %s",
                           type(e).__name__, e)
            _VOCAB_CACHE = []
            return _VOCAB_CACHE
        logger.info("[drugbank_local] vocabulary loaded: %d entries (path=%s)",
                    len(rows), path)
        _VOCAB_CACHE = rows
        return _VOCAB_CACHE


def lookup_by_id(drugbank_id: str) -> Optional[Dict[str, str]]:
    """DrugBank ID(예: DB00945)로 메타데이터 조회."""
    if not isinstance(drugbank_id, str) or not drugbank_id.strip():
        logger.warning("[drugbank_local] lookup_by_id: empty input")
        return None
    lazy_load_vocabulary()
    return _VOCAB_BY_ID.get(drugbank_id.strip().upper())


def lookup_by_inchikey(inchikey: str) -> Optional[Dict[str, str]]:
    """Standard InChI Key로 메타데이터 조회."""
    if not isinstance(inchikey, str) or not inchikey.strip():
        logger.warning("[drugbank_local] lookup_by_inchikey: empty input")
        return None
    lazy_load_vocabulary()
    return _VOCAB_BY_INCHIKEY.get(inchikey.strip())


def search_vocabulary_by_name(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Common name + Synonyms 부분일치 (한국어 사용자 친화).

    Rule M: 빈 쿼리 logger.warning + 빈 리스트 반환.
    """
    if not isinstance(query, str) or not query.strip():
        logger.warning("[drugbank_local] search_vocabulary_by_name: empty query")
        return []
    if not isinstance(limit, int) or limit <= 0:
        limit = 20  # [MAGIC: 20] 기본 검색 결과 표시 한도
    q = query.strip().lower()
    rows = lazy_load_vocabulary()
    out: List[Dict[str, str]] = []
    for row in rows:
        name = row.get("Common name", "").lower()
        syn = row.get("Synonyms", "").lower()
        if q in name or q in syn:
            out.append(row)
            if len(out) >= limit:
                break
    return out


# ─────────────────────────────────────────────────────────────────
# SDF + Morgan fingerprint 인덱스
# ─────────────────────────────────────────────────────────────────

def _get_morgan_generator():
    """RDKit MorganGenerator 인스턴스 (Rule M deprecation 경고 회피).

    rdkit-2025+ 권장 API. 구버전(이전 GetMorganFingerprintAsBitVect)은 deprecation
    경고 출력하지만 동작은 동일. Rule N: None 반환 가드.
    """
    try:
        from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
        return GetMorganGenerator(radius=_MORGAN_RADIUS, fpSize=_MORGAN_NBITS)
    except ImportError:  # Rule M (구 RDKit 폴백)
        return None


def _morgan_fp(mol, generator) -> Any:
    """Morgan fingerprint 생성 (generator 또는 deprecated API 폴백).

    Rule M: 둘 다 실패 시 None 반환 (silent return 차단).
    """
    if generator is not None:
        try:
            return generator.GetFingerprint(mol)
        except Exception as e:
            logger.debug("[drugbank_local] Morgan generator fingerprint 실패: %s", e)
    # 폴백: deprecated API (RDKit 2024 이전)
    try:
        from rdkit.Chem import AllChem
        return AllChem.GetMorganFingerprintAsBitVect(
            mol, _MORGAN_RADIUS, nBits=_MORGAN_NBITS)
    except Exception as e:  # Rule M
        logger.debug("[drugbank_local] AllChem Morgan FP 실패: %s", e)
        return None


def _build_fp_index() -> List[Tuple[str, Any]]:
    """SDF → 모든 분자 fingerprint 인덱스 구축 (1회).

    Rule L: MolFromSmiles 대신 SDMolSupplier — sanitize 실패는 skip.
    Rule M: 빈 인덱스도 logger.warning 통해 사용자 피드백 가능.
    """
    global _INDEX_BUILD_ATTEMPTED, _INDEX_BUILD_ERROR
    _INDEX_BUILD_ATTEMPTED = True
    _INDEX_BUILD_ERROR = None
    try:
        from rdkit import Chem
    except ImportError as e:  # Rule M
        msg = f"RDKit 미설치 — DrugBank 유사도 검색 불가: {e}"
        logger.warning("[drugbank_local] %s", msg)
        _INDEX_BUILD_ERROR = msg
        return []
    sdf_path = _data_path(_SDF_NAME)
    if not os.path.exists(sdf_path):
        msg = f"SDF 파일 부재: {sdf_path} (DRUGBANK_DATA_MISSING)"
        logger.warning("[drugbank_local] %s", msg)
        _INDEX_BUILD_ERROR = msg
        return []
    generator = _get_morgan_generator()
    index: List[Tuple[str, Any]] = []
    n_processed = 0
    n_skipped = 0
    try:
        # sanitize=True (default) - 잘못된 분자는 None 반환 → skip (Rule L)
        suppl = Chem.SDMolSupplier(sdf_path, sanitize=True, removeHs=False)
        for mol in suppl:
            n_processed += 1
            if mol is None:  # Rule L: 파싱 실패 skip
                n_skipped += 1
                continue
            # SDF 내부 props에서 DrugBank ID 추출
            drugbank_id = ""
            try:
                if mol.HasProp("DRUGBANK_ID"):
                    drugbank_id = mol.GetProp("DRUGBANK_ID")
                elif mol.HasProp("DATABASE_ID"):
                    drugbank_id = mol.GetProp("DATABASE_ID")
                elif mol.HasProp("_Name"):
                    drugbank_id = mol.GetProp("_Name")
            except Exception:  # Rule M (단지 prop 없으면 패스)
                pass
            if not isinstance(drugbank_id, str) or not drugbank_id.strip():
                n_skipped += 1
                continue
            fp = _morgan_fp(mol, generator)
            if fp is None:
                n_skipped += 1
                continue
            index.append((drugbank_id.strip().upper(), fp))
            if _SDF_MAX_RECORDS > 0 and len(index) >= _SDF_MAX_RECORDS:
                logger.info(
                    "[drugbank_local] SDF index limited to %d records "
                    "(env CHEMGRID_DRUGBANK_SDF_LIMIT)", _SDF_MAX_RECORDS)
                break
    except Exception as e:  # Rule M
        msg = f"SDF 인덱스 구축 실패 ({type(e).__name__}): {e}"
        logger.warning("[drugbank_local] %s", msg)
        _INDEX_BUILD_ERROR = msg
        return index  # 부분 결과라도 반환 (silent failure 차단)
    logger.info(
        "[drugbank_local] FP index built: %d entries (processed=%d skipped=%d)",
        len(index), n_processed, n_skipped)
    return index


def lazy_build_sdf_index() -> List[Tuple[str, Any]]:
    """SDF → fingerprint 인덱스 (1회 빌드, 스레드 안전)."""
    global _FP_INDEX
    with _LOCK:
        if _FP_INDEX is not None:
            return _FP_INDEX
        _FP_INDEX = _build_fp_index()
        return _FP_INDEX


def search_by_smiles(
    smiles: str,
    k: int = _DEFAULT_K,
    cutoff: float = _DEFAULT_CUTOFF,
) -> List[Dict[str, Any]]:
    """사용자 SMILES → Tanimoto 유사도 기반 Top-k DrugBank 후보.

    Returns: [{drugbank_id, name, similarity, cas, inchikey, synonyms}, ...]
             또는 [{"_data_missing": True, "_reason": ...}] (데이터 부재시).

    Rule L: SMILES None 가드.
    Rule M: 결과 0건도 logger.warning + 빈 리스트 (silent return 차단).
    Rule N: cutoff/k isinstance 검증.
    """
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("[drugbank_local] search_by_smiles: empty SMILES")
        return []
    if not isinstance(k, int) or k <= 0:
        k = _DEFAULT_K
    try:
        cutoff_f = float(cutoff)
    except (TypeError, ValueError):  # Rule N
        cutoff_f = _DEFAULT_CUTOFF
    cutoff_f = max(0.0, min(1.0, cutoff_f))  # [0.0, 1.0] clamp

    # 데이터 부재 사전 검사 (Rule M+GG: 명시적 SIMULATION 신호)
    if not is_data_available():
        logger.warning(
            "[drugbank_local] DRUGBANK_DATA_MISSING: csv=%s sdf=%s",
            os.path.exists(_data_path(_VOCAB_CSV_NAME)),
            os.path.exists(_data_path(_SDF_NAME)))
        return [{
            "_data_missing": True,
            "_reason": "DrugBank vocabulary CSV 또는 SDF 파일이 로컬에 없습니다. "
                       f"data/drugbank/ 폴더를 확인하세요.",
        }]

    try:
        from rdkit import Chem
        from rdkit.Chem import DataStructs
    except ImportError as e:
        logger.warning("[drugbank_local] RDKit 미설치: %s", e)
        return [{"_rdkit_missing": True, "_reason": str(e)}]

    # Rule L: 사용자 SMILES 파싱 + None 체크
    query_mol = Chem.MolFromSmiles(smiles.strip())
    if query_mol is None:
        logger.warning(
            "[drugbank_local] 사용자 SMILES 파싱 실패: %s", smiles[:80])
        return [{"_invalid_smiles": True, "_reason": f"잘못된 SMILES: {smiles[:80]}"}]
    generator = _get_morgan_generator()
    query_fp = _morgan_fp(query_mol, generator)
    if query_fp is None:  # Rule M
        logger.warning("[drugbank_local] 쿼리 Morgan FP 생성 실패")
        return [{"_fp_failed": True, "_reason": "Morgan fingerprint 생성 실패"}]

    index = lazy_build_sdf_index()
    if not index:
        return [{
            "_data_missing": True,
            "_reason": _INDEX_BUILD_ERROR or "SDF 인덱스 구축 실패",
        }]

    # Tanimoto 유사도 계산
    scored: List[Tuple[str, float]] = []
    for drugbank_id, fp in index:
        try:
            tanimoto = DataStructs.TanimotoSimilarity(query_fp, fp)
        except Exception:  # Rule M (개별 비교 실패 skip)
            continue
        if tanimoto >= cutoff_f:
            scored.append((drugbank_id, tanimoto))
    scored.sort(key=lambda t: t[1], reverse=True)
    top = scored[:k]
    if not top:
        logger.warning(
            "[drugbank_local] search_by_smiles: 매칭 0건 (cutoff=%.2f, "
            "index=%d). cutoff를 낮추거나 다른 SMILES 시도.",
            cutoff_f, len(index))

    # 메타데이터 조인
    results: List[Dict[str, Any]] = []
    lazy_load_vocabulary()  # vocab 로드 보장
    for drugbank_id, score in top:
        meta = _VOCAB_BY_ID.get(drugbank_id, {})
        results.append({
            "drugbank_id": drugbank_id,
            "name": meta.get("Common name", "") or "(이름 없음)",
            "similarity": round(score, 3),
            "cas": meta.get("CAS", ""),
            "inchikey": meta.get("Standard InChI Key", ""),
            "synonyms": meta.get("Synonyms", "")[:200],  # [MAGIC: 200] UI 표시 길이 제한
            "drugbank_url": f"https://go.drugbank.com/drugs/{drugbank_id}",
        })
    return results


# ─────────────────────────────────────────────────────────────────
# CLI / 자가 진단 (Rule M 사용자 피드백)
# ─────────────────────────────────────────────────────────────────

def self_diagnose() -> Dict[str, Any]:
    """모듈 자가 진단 — 데이터 로드 + 1건 샘플 검색.

    Returns: 실패 사유 명시 (Rule M silent failure 차단).
    """
    status = get_data_status()
    if not status["csv_exists"]:
        status["self_test"] = "FAIL: CSV missing"
        return status
    rows = lazy_load_vocabulary()
    status["vocabulary_loaded"] = len(rows) > 0
    status["vocabulary_count"] = len(rows)
    if not status["sdf_exists"]:
        status["self_test"] = "PARTIAL: SDF missing — vocabulary lookup only"
        return status
    # 샘플 검색 (Aspirin: CC(=O)Oc1ccccc1C(=O)O)
    sample = search_by_smiles(
        "CC(=O)Oc1ccccc1C(=O)O", k=3, cutoff=0.3)
    status["self_test_sample_aspirin"] = sample
    status["self_test"] = "PASS" if sample and not sample[0].get("_data_missing") else "FAIL"
    return status


if __name__ == "__main__":  # Rule M: CLI 자가 진단
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(self_diagnose(), indent=2, ensure_ascii=False))
