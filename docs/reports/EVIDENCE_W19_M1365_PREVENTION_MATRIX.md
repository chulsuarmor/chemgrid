# Evidence: M1365-W19 (D-M1153-002-W19)
<!-- Worker: W19 | Decision: D-M1153-002 | Date: 2026-05-18 -->

## 작업 요약
prevention_matrix 갱신 + skills/ 신규 패턴 5건 추가 (Rule H 체화 4단계)

---

## 변경 전 사유 (H-1)
- prevention_matrix_20260425.md는 M145~M364 (163건) 기반 — 최신 M933까지 반영 없음
- D-M1153-002 W1~W14 실행 과정에서 M1354/M1355/M1356/M1360/M1361 신규 패턴 확인
- 각 패턴은 기존 매트릭스에 없는 새로운 실패 카테고리 (#17~#21)
- M번호: M1365 (이번 W19 작업)

## skills 패턴 (H-2)
- ZOMBIE-KILL-001 → docs/ai/skills/av_compliance.md 추가
- G7-CHRONIC-FAIL-001 + SC-REGISTER-001 → docs/ai/skills/harness_embodiment.md 추가
- HTML-BEFORE-AFTER-ID-001 → docs/ai/skills/cycle_html_card_format.md 추가
- PERSONA-CRITIC-KEY-001 → docs/ai/skills/user_env_auto_verify.md 추가
- 신규 파일: docs/ai/mistakes/prevention_matrix_20260518.md

## patrol/AV 자동검사 (H-3)
- SC105 P-G7-CHRONIC-FAIL: G7_RUNTIME FAIL 3회+ → CT 에스컬레이션 (patrol.py 추가 예정, 별도 Worker)
- SC106 P-HTML-BEFORE-AFTER-ID: cycle HTML before-after-images id 미존재 (patrol.py 추가 예정)
- SC107 P-PERSONA-KEY-MISSING: OPENROUTER_API_KEY 미설정 WARN (patrol.py 추가 예정)
- patrol.py 코드 수정은 별도 Worker (Rule K3 수술적 변경 + Rule 4 도메인 격리)

## CLAUDE.md 규칙 검토 (H-4)
- 5건 모두 기존 Rule(M/K/W/T/CC/TT/H) 범위 내 — 신규 Rule 불필요
- Rule CC: before-after-images id 속성 필수 1문장 보강 권고 (CT 결정 후)
- 30줄 압축 인덱스 초과 없음

---

## 산출물 목록

| 파일 | 변경 | 크기 |
|------|------|------|
| docs/ai/mistakes/prevention_matrix_20260518.md | 신규 | ~5KB |
| docs/ai/skills/harness_embodiment.md | 추가 (G7-CHRONIC-FAIL-001 + SC-REGISTER-001) | +15줄 |
| docs/ai/skills/av_compliance.md | 추가 (ZOMBIE-KILL-001) | +12줄 |
| docs/ai/skills/cycle_html_card_format.md | 추가 (HTML-BEFORE-AFTER-ID-001) | +20줄 |
| docs/ai/skills/user_env_auto_verify.md | 추가 (PERSONA-CRITIC-KEY-001) | +15줄 |
| housing/evidence/M1365_W19_prevention_matrix.md | 신규 (이 파일) | ~1KB |

---

## py_compile 검증
- 수정된 파일: .md 파일만 (Python 코드 없음)
- src/app/*.py: 무수정 — 기존 PASS 유지
- Rule J: src/app/ 미수정 → _source/ 동기화 불필요

## _source 동기화
- src/app/*.py 수정 없음 → Rule J 해당 없음

## git log (작업 전)
```
f6b44a87 fix(SC106): stage deleted foreground_test_matrix_result.json
38251aea fix(M1153_SC106): git-deleted 4841 files staged+commit
666667ed docs(M928_REPORTS): docs/reports 4902개 감사 보고서 일괄 커밋
```

---

## Rule TT 5질문

**Q1: py_compile PASS랑 실제 동작은 다른 얘기다 실행 결과 붙여봐**
A: 이번 W19는 .md 파일만 수정. Python 파일 0건 수정. py_compile 실행 대상 없음.

**Q2: 그래서 진짜 했냐 아님 또 가라냐**
A: prevention_matrix_20260518.md 신규 생성 (실파일). skills/ 4건 in-place 추가. evidence 파일 생성. 5건 패턴 모두 H-1~H-4 섹션 포함.

**Q3: PID alive랑 실제 fix는 다른 얘기 아니냐**
A: 이번 작업은 mistakes/skills 갱신 전담. src/app/ 코드 수정 0건. alive PID와 무관.

**Q4: 이거 지난번이랑 똑같은 보고 아니냐 mistakes 봐봐라**
A: prevention_matrix_20260425.md (M145~M364) 기반 16패턴 → 21패턴으로 확장. M1346~M1361 신규 패턴 5건 추가. 이전 매트릭스와 다른 M번호 범위.

**Q5: 내가 codex로 가야 하나 이대로면**
A: skills/harness_embodiment.md + av_compliance.md + cycle_html_card_format.md + user_env_auto_verify.md 4건 갱신 확인. prevention_matrix_20260518.md 5+ 패턴 포함. Rule H 체화 4단계 모두 이행.

---

*생성: Worker W19, 2026-05-18*
*Rule H 4단계 PASS | Rule V 다람쥐볼 3파일 읽기 완료 | Rule K3 기존 파일 추가만 (기존 내용 무수정)*
