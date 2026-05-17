# EVIDENCE M1367 W187 — G3 Reaction Arrow Direction Fix

**날짜:** 2026-05-18
**Worker:** W187 (D-M1153-002 WAVE 1)
**CT Decision:** D-M1153-003 G3 reaction arrow direction accuracy fix
**CT 보고:** PENDING

## 수정 범위 (K3 surgical)
- `src/app/arrow_generator.py`: SEMI-FROZEN patch — 3개 상수 추가 (코드 로직 변경 없음)
- `src/app/reaction_mechanisms.py`: OPEN-UPDATE — 2개 버그 수정 (Grignard self-arrow, Aldol E1cb 인덱스)

## 수정 내용

### 1. arrow_generator.py (SEMI-FROZEN patch)
Rule O M473 PDF 표준 상수 3종 모듈레벨에 추가:
```python
_ARROW_HEAD_MIN_PX: float = 10.0       # 화살촉 최소 10px
_ARROW_HEAD_HALF_W_RATIO: float = 0.42 # McMurry 삼각형 너비 비율
_FISHHOOK_BARB_MIN_RATIO: float = 0.40 # 라디칼 fishhook 식별 최소 비율
```
기존 popup_reaction.py의 inline 상수값과 동일 — 단일 소스 정의.

### 2. reaction_mechanisms.py — Grignard step 3 self-arrow 수정
**버그:** `from_atom_idx=5, to_atom_idx=5` (자기 자신 가리킴 — 렌더링 오류)
**수정:** `to_atom_idx=-1` (외부/H₂O 이탈 표현 — 교과서 정확)

### 3. reaction_mechanisms.py — Aldol step 4 E1cb 인덱스 수정
**버그:** `from=1,to=2` (잘못된 인접 C 인덱스), `from=2,to=0` (틀린 OH 이탈 방향)
**수정:**
- Arrow 2: `from=1(α-C), to=5(β-C)` — 올바른 C=C pi 결합 형성 방향
- Arrow 3: `from=5(β-C), to=6(β-OH)` — β-OH 이탈기 방향 정확

## 5 메커니즘 방향성 검증 결과
```
SN2: O(2)→C(0) [Nu], C(0)→Br(1) [LG]           ✓ 이미 정확
E2:  OH(3)→αC(0), C(0)→C(1) pi, C(1)→Br(2)     ✓ 이미 정확
Aldol CC: enolate(0)→C=O(4), pi(4)→O⁻(5)        ✓ 이미 정확
Aldol E1cb: OH⁻→αC(1), αC(1)→βC(5), βC(5)→βOH(6) ✓ 수정 완료
Diels-Alder: diene(0)→(4), (4→5), diene(3)→(5) ✓ 이미 정확
Grignard step2: R-Mg(3)→C=O(1), pi(1→2), O→Mg(4) ✓ 이미 정확
Grignard step3: self-arrow → to=-1(external)    ✓ 수정 완료
```

## 테스트 결과
```
55 PASS / 0 FAIL — housing/evidence/M1367_W187_mechanism_test.py
```

## py_compile
```
arrow_generator.py: PASS
reaction_mechanisms.py: PASS
```

## _source/ 동기화 (Rule J)
```
diff -q src/app/arrow_generator.py _source/arrow_generator.py → IDENTICAL
diff -q src/app/reaction_mechanisms.py _source/reaction_mechanisms.py → IDENTICAL
```

---

## 변경 전 사유 (H-1)
**왜 이 코드가 잘못됐는가:**
1. Grignard step 3: `from_atom_idx=5, to_atom_idx=5` — self-arrow는 시작=끝이라 렌더러가 길이=0 화살표를 그리거나 크래시 발생. 화학적으로도 틀림 (H₂O 이탈은 외부 방향).
2. Aldol E1cb step 4: `from=1,to=2` (alpha→인접 branch C)는 분자 내에서 올바른 beta-carbon을 가리키지 않음. SMILES `OC(CC=O)CO`에서 beta-C는 인덱스 5이고 beta-OH는 인덱스 6임.
3. arrow_generator.py에 M473 상수 미정의 — popup_reaction.py의 inline 값과 분리되어 향후 불일치 위험.

**실패 상황:** G3 reaction arrow 방향 검사에서 self-arrow와 잘못된 인덱스 발견.
**M번호:** M1367

## skills 패턴 (H-2)
- **ARROW-SELF-001**: ArrowData에서 `from_atom_idx >= 0` AND `to_atom_idx >= 0`일 때 양쪽이 동일하면 self-arrow 버그. 렌더러는 방향 벡터 = 0으로 처리 불가. 항상 `to_atom_idx=-1` (external)로 표현.
- **SMILES-IDX-001**: SMILES 내 원자 인덱스는 분자 표기 순서 기반. 브랜치 `(X)`의 원자는 브랜치 위치 순서로 인덱싱. `OC(CC=O)CO`에서 branch-C가 idx=2가 아닌 메인체인 연속으로 계산 필요.
- **CONST-SINGLE-SOURCE-001**: 렌더링 상수는 모듈레벨 단일 정의 후 참조. popup_reaction.py inline + arrow_generator.py inline = 이중 정의 위험.

갱신 파일: `docs/ai/mistakes/rendering.md` (M1367 기록)

## patrol/AV 자동검사 (H-3)
- G7-SC-ARROW-SELF: `from_atom_idx == to_atom_idx` 동시 `>= 0` 검출 → patrol.py check 추가 가능
- SC번호: SC-ARROW-SELF-001 (신설 권장, patrol.py 추가 대상)
- 탐지 로직: `re.search(r'from_atom_idx=(\d+),.*to_atom_idx=\1\b', source)` 패턴

## CLAUDE.md 규칙 검토 (H-4)
- 해당 Rule: Rule O (렌더링 품질), Rule L (SMILES 파싱 방어)
- Rule O에 "ArrowData self-arrow (from==to>=0) = 렌더링 실패" 추가 권장
- 변경 내용: 기존 Rule O 보강 (신규 Rule 불필요)
