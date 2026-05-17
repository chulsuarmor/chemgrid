# Skill: External API Audit (외부 API 13종 HTTP 검증)
> 신설: M721 / Worker CT-D-A58-W2 (2026-05-04)
> 갱신: M1363 / W17 (2026-05-18) — SSL EOF fallback 패턴 추가
> 관련 스킬: external_api_versioning.md

---

## M721 13종 외부 엔진 HTTP 실측 결과 (2026-05-04)

### HTTP 200 확인 엔진 (7종 — 즉시 사용 가능)

| # | 엔진 | 엔드포인트 유형 | JSON API | 비고 |
|---|------|----------------|----------|------|
| 1 | RCSB PDB | REST JSON | O | data.rcsb.org/rest/v1/core/entry/{pdb_id} |
| 2 | AlphaFold EBI | REST JSON | O | alphafold.ebi.ac.uk/api/prediction/{uid} |
| 3 | PDBe entry | HTML + Summary API | O | www.ebi.ac.uk/pdbe/api/pdb/entry/summary/{id} |
| 4 | PubChem | REST JSON | O | pubchem.ncbi.nlm.nih.gov/rest/pug/... |
| 5 | ChEMBL | REST JSON | O | www.ebi.ac.uk/chembl/api/data/... |
| 6 | NCI Cactus | Plain text | plain-text | cactus.nci.nih.gov/chemical/structure/... |
| 7 | Reactome | REST JSON (HTTP only) | O | reactome.org/ContentService/... (HTTP만 작동) |

### HTML만 제공 (3종 — 브라우저 링크 전용)

| # | 엔진 | 상태 | 비고 |
|---|------|------|------|
| 8 | NIST WebBook | HTTP 200 HTML | JSON API 없음, 브라우저 링크만 |
| 9 | KNApSAcK | HTTP 200 HTML | JSON API 없음, HTTP만 |
| 10 | PDBj | HTTP 200 HTML (웹), REST 404 | RCSB 사용 권장 |

### 인증 또는 DNS 문제 (3종)

| # | 엔진 | HTTP | 상태 | 해결책 |
|---|------|------|------|--------|
| 11 | ChemSpider | 403 | API 키 필요 (RSC) | developer.rsc.org 무료 등록 |
| 12 | EPA CompTox | 200 HTML, REST 0 | CCTE API DNS fail | 웹 링크 사용 / 키 발급 후 재시도 |
| 13 | OPSIN | 404 | DEPRECATED | NCI Cactus ?resolver=iupac_name 으로 완전 대체 (M712) |

---

## PUBCHEM-SSL-001: PubChem SSLEOFError fallback 패턴 (M1363)

**증상**: `SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING]')` — 방화벽/프록시 환경에서 간헐 발생.
**파일**: `pubchem_client.py` `_get()`, `canvas.py`, `docking_interface.py`, `innate_defense_docking.py`, `popup_3d.py`
**올바른 패턴**:
```python
try:
    resp = requests.get(url, timeout=T)           # 1차: verify=True (정상 환경)
    return resp
except Exception as e:
    _is_ssl = ("SSL" in type(e).__name__ or "ssl" in str(e).lower()
               or "UNEXPECTED_EOF" in str(e) or "certificate" in str(e).lower())
    if _is_ssl:
        logger.warning("[M1363] SSL 오류 → verify=False 재시도: %s", str(e)[:100])
        resp = requests.get(url, timeout=T, verify=False)  # 2차: bypass
        return resp
    logger.warning("GET 오류: %s", str(e)[:100])
    return None
```
**Rule M 준수**: verify=False 재시도도 실패 시 `logger.warning` + `None` 반환 (silent 금지).
**certifi**: `pip install --upgrade certifi` 정기 갱신 권장 (2026.4.22 최신).

## RCSB-SSL-001: RCSB PDB download SSL fallback (M1363)
**파일**: `docking_interface.py`, `innate_defense_docking.py`, `popup_3d.py`
**패턴**: PUBCHEM-SSL-001과 동일. `verify=False` 재시도 + logger.warning.

---

## API-AUDIT-001: 신규 엔진 추가 시 필수 절차

신규 외부 엔진을 ChemGrid에 통합하기 전 반드시:

1. **HTTP 실측 확인** — 5종 분자로 GET 요청 (requests/urllib, timeout=10s)
2. **Schema 검증** — housing/external/schemas/{N}_{engine_id}.json 신설
3. **인증 분류** — 무인증/API키/유료/HTML전용 중 하나
4. **USER_LOGIN_REQUIRED.md 갱신** — API 키 발급 절차 추가
5. **popup_*.py 매핑** — 어느 popup이 해당 엔진 사용하는지 기록
6. **fallback 전략** — HTTP 4xx/5xx 시 대체 엔진 명시

---

## API-AUDIT-002: HTTP 응답 형식별 파싱 전략

### JSON API (RCSB/AlphaFold/PubChem/ChEMBL/Reactome)
```python
# Rule N: isinstance 타입 가드 필수
data = json.loads(raw)
if not isinstance(data, (dict, list)):
    logger.warning("[M721] 예상치 못한 응답 타입: %s", type(data).__name__)
    return None, "응답 형식 오류"
```

### Plain text (NCI Cactus)
```python
# Rule N + Rule M: 길이 검증 + silent failure 금지
raw = raw.strip()
if not raw or len(raw) < 2:  # [MAGIC: 2] 최소 유효 SMILES 길이
    logger.warning("[NCI Cactus] 빈 응답 또는 오류: %r", raw)
    return None
```

### HTML 전용 (NIST/KNApSAcK/PDBj/EPA CompTox 웹)
```python
# 프로그래밍 파싱 금지 — webbrowser.open() 사용
webbrowser.open(f"https://webbook.nist.gov/cgi/cbook.cgi?ID={cas}")
```

---

## API-AUDIT-003: Reactome HTTPS fallback 패턴 (M712)

```python
# HTTPS → HTTP 자동 fallback
_url_https = f"https://reactome.org/ContentService/..."
_url_http  = f"http://reactome.org/ContentService/..."

for _attempt in (_url_https, _url_http):
    try:
        resp = requests.get(_attempt, timeout=10, verify=(_attempt.startswith("https")))
        break
    except Exception as e:
        if "ssl" in type(e).__name__.lower() and _attempt == _url_https:
            logger.warning("[Reactome] HTTPS SSL 오류 → HTTP fallback: %s", e)
            continue
        return []  # 완전 실패
```

---

## API-AUDIT-004: AlphaFold 버전 동적 조회 (M455 패턴)

```python
# 절대 금지: version 하드코딩
# url = f"...AF-{uid}-F1-model_v4.pdb"   <- M455 버그

# 올바른 방법: API로 latestVersion 조회
url = f"https://alphafold.ebi.ac.uk/api/prediction/{uid}"
data = json.loads(raw)
entry = data[0]  # array[0] 구조
pdb_url = entry.get("pdbUrl")  # 동적 URL 사용
```

---

## schema 파일 위치

```
housing/external/schemas/
├── 01_rcsb_pdb.json          # HTTP 200, JSON API
├── 02_alphafold_ebi.json     # HTTP 200, JSON API, v6 latestVersion
├── 03_pdbe_entry.json        # HTTP 200, HTML + Summary API
├── 04_pubchem.json           # HTTP 200, JSON API
├── 05_chembl.json            # HTTP 200, JSON API
├── 06_nci_cactus.json        # HTTP 200, plain text, OPSIN 대체
├── 07_nist_webbook.json      # HTTP 200, HTML only
├── 08_reactome.json          # HTTP 200, JSON (HTTP only)
├── 09_opsin_deprecated.json  # HTTP 404, DEPRECATED
├── 10_knapsack.json          # HTTP 200, HTML only
├── 11_chemspider.json        # HTTP 403, API key needed
├── 12_pdbj.json              # HTTP 200 web, REST 404
└── 13_epa_comptox.json       # HTTP 200 web, CCTE API DNS fail
```

---

## popup 매핑 요약

| popup 파일 | 사용 엔진 |
|-----------|----------|
| popup_alphafold.py | AlphaFold EBI, PDBe entry, RCSB PDB |
| popup_docking.py | RCSB PDB, PDBe entry, PDBj (link) |
| popup_synthesis.py | Reactome |
| popup_3d.py | ChEMBL, NCI Cactus, ChemSpider (link) |
| popup_lead_optimizer.py | ChEMBL, PubChem, KNApSAcK (link) |
| popup_drug_screening.py | PubChem, ChEMBL, EPA CompTox (link) |
| popup_predicted_spectrum.py | NCI Cactus, NIST (link) |
| main_window.py | NCI Cactus (OPSIN 대체, M712) |

---

*최종 업데이트: 2026-05-04 / M721 / Worker CT-D-A58-W2*
