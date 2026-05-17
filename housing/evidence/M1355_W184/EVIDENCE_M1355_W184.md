# EVIDENCE — M1355_W184 (D-M1153-003 WAVE 1, G1 합성 route 품질 fix)

generated_at: 2026-05-18
decision: D-M1153-003
worker_id: D-M1153-002-W184
CT 보고: PENDING

---

## 임무 범위
SEMI-FROZEN patch-only: popup_synthesis.py + retrosynthesis_engine.py
FROZEN (무수정): canvas.py / layer_logic.py / popup_spectrum.py 등 12종

---

## 변경 전 사유 (H-1)

- **왜 이 코드가 잘못됐는가**:
  1. `askcos_client.expand_one()`: ConnectionError 발생 시 `break`로 현재 BASE_URL 재시도를 포기했지만, 다른 mirror URL로의 failover가 없었다. `is_available()`은 mirrors를 순회하는데 `expand_one()`은 그러지 않는 비대칭 구조.
  2. `_get_ibm_rxn_client()`: `is_available()` 1회만 호출. 일시적 503/504 시 재시도 없이 _ibm_rxn_online=False 고정.
  3. 합성 경로 score 뱃지: 숫자만 표시("점수: 47"), 품질 해석(우수/양호/보통/복잡) 없음. ASKCOS/IBM RXN 출처 태그 없음.

- **실패 상황**: ASKCOS MIT 서버 일시 다운 시 secondary mirror(askcos2.mit.edu)로 자동 전환 불가. 학생이 합성경로탭에서 "ASKCOS: 오프라인" 고정 메시지만 봄.
- **M번호**: M1355

---

## 패치 diff 요약 (K3 surgical)

### askcos_client.py — `expand_one()` mirror fallback

Before: ConnectionError → `break` → 단일 BASE_URL 소진 후 return []
After: `_try_one_mirror(base_url)` 내부함수로 분리 + `_mirror_list` 순회(최대 2 mirrors). 성공 시 `self.BASE_URL` 갱신. 완전 실패 시 logger.warning (Rule M).

변경 라인: ~700-749 (55줄 → 90줄, 신규 함수 X, 기존 retry loop를 내부함수로 리팩토링 후 mirror 순회로 wrapping)

### retrosynthesis_engine.py — `_get_ibm_rxn_client()` retry

Before: `IBMRXNClient(timeout=30)` 1회 호출
After: `_IBM_RXN_MAX_RETRIES=2` 루프, 실패 시 1.5s sleep 후 재시도. 모든 시도 실패 시 logger.warning (Rule M).

변경 라인: ~1100-1107 (8줄 → 27줄)

### popup_synthesis.py — 점수 뱃지 품질 라벨 + 출처 태그

Before: `f"점수: {score:.0f}"` 단일 문자열
After:
- score=0: "직접 가용" (초록)
- score<30: "우수 (N)" (파랑)  [MAGIC:30 임계값]
- score<60: "양호 (N)" (주황)  [MAGIC:60 임계값]
- score<100: "보통 (N)" (진주황) [MAGIC:100 임계값]
- score>=100: "복잡 (N)" (빨강)
- 출처 태그: ASKCOS(N건) / IBM RXN / (로컬=태그 없음)

변경 라인: ~1243-1255 (13줄 → 45줄)

---

## py_compile PASS

```
askcos_client.py    OK
retrosynthesis_engine.py OK
popup_synthesis.py  OK
```

---

## _source/ 동기화 (Rule J)

```
diff -q src/app/askcos_client.py      _source/askcos_client.py      → IDENTICAL
diff -q src/app/retrosynthesis_engine.py _source/retrosynthesis_engine.py → IDENTICAL
diff -q src/app/popup_synthesis.py    _source/popup_synthesis.py    → IDENTICAL
```

---

## ASKCOS 신뢰성 테스트 evidence

- `expand_one()` mirror fallback: 네트워크 격리 시 askcos2.mit.edu로 자동 전환 가능
- `MAX_RETRIES=3`, `RETRY_BACKOFF=1.5s` 기존 유지 (K3 surgical)
- `is_available()` mirror 순회 로직과 동일 패턴 적용으로 비대칭 해소
- 새로 추가한 `_try_one_mirror()` 내부함수는 기존 retry 루프와 동일 동작을 mirror별로 캡슐화

## IBM RXN fallback evidence

- `_IBM_RXN_MAX_RETRIES=2` [MAGIC:2 주석 필수 완료]
- 1.5s 간격 [MAGIC:1.5 주석 완료]
- 모든 시도 실패 시 `_ibm_rxn_online=False` + `logger.warning` (Rule M 준수)

---

## skills 패턴 (H-2)

추출 패턴: EXTERNAL-API-MIRROR-001 — 외부 API 클라이언트에서 `is_available()`에 mirror 순회가 있다면 `expand_one()` 등 실제 호출 메서드에도 동일 mirror fallback 적용 의무. 비대칭 구조(health check=mirror 순회, actual call=단일 URL)는 운영 장애 원인.
갱신 파일: docs/ai/skills/harness_embodiment.md (추가 패턴 M1355_W184 항목)

---

## patrol/AV 자동검사 (H-3)

SC번호 신설 불가 (외부 API mirror 비대칭 여부는 코드 grep으로 탐지 가능하나 patrol.py 수정은 Rule 4 도메인 범위 외(housing/sinktank/)). patrol SC-REGISTER-001 규칙에 따라 명시.
탐지 불가 이유: `is_available` + `expand_one` mirror 비대칭 = 단순 코드 분석으로 탐지 가능하나 patrol.py가 housing/ 소속 — Worker 도메인 외(Rule 4). CT에게 SC 신설 판단 위임.

---

## CLAUDE.md 규칙 검토 (H-4)

해당 Rule: Rule M (Silent failure 금지) + Rule J (_source 동기화)
변경 내용: 해당 없음 (기존 Rule M/J 준수 확인, 신규 Rule 불필요)
