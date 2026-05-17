# Skill: AV (Antivirus) Compliance — Worker/CT 필수 준수 지침
> 최초 작성: 2026-05-03 | Worker A19 | CT-42 결정
> 근거: docs/ai/mistakes.md M647_W5_A19 (AV skill 1년 미작성 = 하네스 공백)
> 연관 파일: housing/immune/antivirus.py, housing/sinktank/cron_av_unified.py

---

## 1. 정책 개요

ChemGrid AV 체계는 두 레이어로 구성된다.

| 레이어 | 파일 | 역할 |
|--------|------|------|
| AntivirusEngine | `housing/immune/antivirus.py` | 바이러스 주입·면역 검증·보안 감사·적응형 난이도 (4-A ~ 4-E, 4-F 유기 통합) |
| cron_av_unified | `housing/sinktank/cron_av_unified.py` | 20분 주기 4모듈 실시간 점검 (M1~M4) → `.claude/notifications/` JSON |

Worker는 산출물 생성 전 반드시 cron_av_unified.py의 4모듈 판정을 확인해야 한다.
감사팀은 cron_av_unified.py 결과 JSON을 직접 열어 `overall_verdict` 확인 의무가 있다.

---

## 2. 5 Issue 카테고리 상세

### Category 1 (HIGH): _source 미동기 — `ct_source_desync`

**감지 패턴 (cron_av_unified.py Module 1, L209~L229):**
```python
# module_ct_integrity() — filecmp.cmp(src/app/X.py, _source/X.py, shallow=False)
# 불일치 시: issues.append({"type": "ct_source_desync", "severity": "HIGH", ...})
```
감지 조건: `src/app/*.py` 각 파일과 `_source/` 대응 파일을 바이트 단위 비교, 불일치 또는 _source 미존재.

**해소 방법:**
1. `cp C:/chemgrid/src/app/X.py C:/chemgrid/_source/X.py` (수정 파일 전부)
2. `diff -q C:/chemgrid/src/app/X.py C:/chemgrid/_source/X.py` → "identical" 확인
3. Rule J 준수: src/app 수정 즉시 _source 복사, 작업 완료 후 미루기 금지

**사고 인용:**
- M647_A1_PATH: main repo + _source 동기화 후 worktree 미동기 → audit REJECT
- M647_W5_A12: src vs _source 헤더 22byte 차이 → diff fail

---

### Category 2 (WARN): EVIDENCE CT PENDING 형식 누락 — `hollow_evidence_no_ct`

**감지 패턴 (cron_av_unified.py Module 2, L302~L314):**
```python
# module_hollow_check() — re 패턴
_CT_PENDING_RE = re.compile(r"CT\s*보고\s*[::：]\s*PENDING", re.IGNORECASE)
# docs/reports/EVIDENCE_*.md 중 이 패턴 없으면 ct_missing 목록에 추가
```
감지 조건: `docs/reports/EVIDENCE_*.md` 파일에 `CT 보고: PENDING` (한글/영문 콜론 허용) 문자열 없음.

**해소 방법:**
EVIDENCE 파일 생성 시 반드시 아래 줄 포함:
```
CT 보고: PENDING
```
antivirus.py `check_ct_bypass()` 함수(L1191)도 동일 키워드 확인 — CT 경유 없이 사용자 전달 탐지 용도.

**사고 인용:**
- M349, M391, 2026-04-25 CT 미경유 사고 = 3회 반복 → antivirus.py 4-G 블록 신설

---

### Category 3 (WARN): 감사팀 오늘 보고서 N/3팀 미생성 — `hollow_audit_missing`

**감지 패턴 (cron_av_unified.py Module 2, L323~L339):**
```python
_AUDIT_TEAMS = ["theory", "gui", "integration"]  # [MAGIC] 감사팀 3종
# docs/reports/audit/audit_{team}_{YYYYMMDD}*.md glob → 없으면 audit_missing 추가
```
감지 조건: 오늘 날짜(YYYYMMDD)로 `docs/reports/audit/` 아래 3팀 보고서 중 하나라도 없음.

**해소 방법:**
감사팀 보고서 파일명 규칙: `audit_{theory|gui|integration}_{YYYYMMDD}_{설명}.md`
예: `audit_theory_20260503_A19.md`
Rule G: 감사팀은 산출물 직접 열어 확인 후 전체 판정 기재 필수.

---

### Category 4 (WARN): 감사 N/3팀 PASS 미달 — `serial_audit_incomplete`

**감지 패턴 (cron_av_unified.py Module 3, L387~L409):**
```python
# module_serial_violation() — .claude/audit_{theory|gui|integration}_report.md 파싱
# re.search(r"전체\s*판정\s*[:\-]?\s*PASS", text) → PASS
# re.search(r"COND_PASS|CONDITIONAL_PASS|조건부\s*PASS", text) → COND_PASS
# pass_count < 3 → serial_audit_incomplete WARN
```
감지 조건: `.claude/` 디렉토리 아래 3개 보고서 파일 중 PASS/COND_PASS 합산 < 3.

**해소 방법:**
1. 부족한 팀 보고서 생성 → `.claude/audit_{team}_report.md`
2. "전체 판정: PASS" 또는 "전체 판정: COND_PASS" 문구 포함 필수
3. Rule T: 3팀 전원 PASS 후에만 CT 보고 가능

**주의**: `전체 판정: REJECT/FAIL P0 없음` 형식은 post_serial_audit_gate.py에서 false positive를 유발했던 전력 있음 (M535). 판정 문구는 "전체 판정: PASS" 형태로 단순화.

---

### Category 5 (WARN): 직렬 위반 의심 — `serial_violation_evidence`

**감지 패턴 (cron_av_unified.py Module 3, L441~L470):**
```python
# 최근 24시간 EVIDENCE_*.md 중
# has_ct_report = re.search(r"CT\s*보고", text)  → CT 보고 언급
# has_audit_pass = re.search(r"감사.*PASS|audit.*PASS", text)  → 감사 PASS 언급
# has_ct_report AND NOT has_audit_pass → serial_violations 추가
```
감지 조건: EVIDENCE에 "CT 보고" 있는데 "감사.*PASS" 패턴 없음 = 감사 미경유 CT 상신 의심.

**해소 방법:**
EVIDENCE에 다음 두 항목 모두 포함:
```
감사팀 PASS: audit_theory PASS / audit_gui PASS / audit_integration PASS
CT 보고: PENDING
```

---

## 3. False Positive 패턴

### FP-1: worktree 기준 감사 (M647_A1_PATH)
**현상:** audit_gui가 worktree 경로 파일 기준으로 diff → main repo 수정이 미반영된 것처럼 판정.
**해소:** Worker는 src/app/ 수정 시 3곳 동기화 의무 — main repo + _source + worktree.
`tools/worktree_sync_all.py` 활용 권장.

### FP-2: post_serial_audit_gate.py REJECT 패턴 (M535)
**현상:** "REJECT/FAIL P0 없음" 문구가 REJECT_PATTERN에 매칭 → PASS 보고서가 BLOCK.
**해소:** 부정 lookahead `(?!.*없음)` 이미 적용됨. 감사 보고서 판정 문구에 REJECT/FAIL 단어 사용 시 반드시 "없음" 접미어 또는 다른 형식 사용.

### FP-3: EVIDENCE CT PENDING 오탐 — 신규 EVIDENCE에만 적용 (M2-HOLLOW)
**현상:** 오래된 완료 EVIDENCE가 CT PENDING 없이 남아 있어 hollow_evidence_no_ct 지속 발생.
**해소:** cron_av_unified.py Module 2가 `docs/reports/EVIDENCE_*.md` 전체를 검사.
완료된 EVIDENCE는 `CT 보고: DONE` 또는 `CT 보고: VERIFIED` 로 업데이트하거나 archive 이동.

### FP-4: serial_violation_evidence 오탐 — "감사 결과: PASS" 문구 누락 (M3-SERIAL)
**현상:** EVIDENCE에 "감사팀이 PASS 하였음" 같은 비정규 표현 → `감사.*PASS` 패턴 미매칭.
**해소:** EVIDENCE에 반드시 `감사팀 PASS:` 또는 `audit_theory PASS` 키워드 포함.

---

## 4. WARN → FAIL 승격 조건

cron_av_unified.py의 판정 로직 (L651~L663):

```python
severities = [i.get("severity", "WARN") for i in all_issues]
if "CRITICAL" in severities:
    overall_verdict = "FAIL"
elif "HIGH" in severities:
    overall_verdict = "FAIL"   # HIGH = FAIL
elif "WARN" in severities:
    overall_verdict = "WARN"   # WARN = WARN (비차단)
else:
    overall_verdict = "PASS"
```

| severity | 기본 판정 | 승격 조건 |
|----------|-----------|-----------|
| WARN | WARN (비차단) | 3회 연속 → mistakes.md 기록 의무 |
| HIGH | FAIL (차단) | _source 미동기 / 0byte .py 파일 |
| CRITICAL | FAIL (차단) | CLAUDE.md 없음 / py_compile FAIL |

**WARN이 사실상 FAIL인 경우:** Module 3 `serial_audit_incomplete`는 WARN이지만
Rule T(직렬강제)에 의해 3팀 PASS 없으면 CT 상신 자체가 차단됨.
patrol.py SC92 (P-ALIVE-NO-PROGRESS)는 REJECT 차단.

---

## 5. skills 미작성 시 발생하는 사고 사례

이 파일(av_compliance.md)은 2026-05-03 이전 **1년 이상 미작성** 상태였다.
결과로 발생한 반복 패턴:

### M647_A1_PATH (2026-05-03)
- 상황: Worker A1이 src/app/ 수정 후 _source 동기화했으나 worktree 미동기
- AV 판정: ct_source_desync HIGH → FAIL
- 결과: audit REJECT + A12-Sync 재작업 발생
- **skill이 있었다면:** "3곳 동기화 의무" 패턴을 사전에 확인하여 방지 가능

### M647_W5_A12 (2026-05-03)
- 상황: housing/sinktank/serial_hook_apply.py를 _source 복사 시 헤더 주석 22byte 차이
- AV 판정: ct_source_desync → diff fail
- **skill이 있었다면:** diff -q IDENTICAL 확인 단계를 표준화하여 방지 가능

### M349 / M391 / 2026-04-25 CT 미경유 3회 반복
- 상황: Worker EVIDENCE에 CT 보고 PENDING 없이 사용자 전달 패턴 반복
- AV 판정: hollow_evidence_no_ct WARN
- 결과: antivirus.py 4-G 블록(check_ct_bypass) 신설 강제
- **skill이 있었다면:** EVIDENCE 필수 형식을 표준화하여 반복 방지 가능

---

## 6. AV 실행 방법

### 즉시 검사 (1회)
```bash
cd C:/chemgrid
python housing/sinktank/cron_av_unified.py --run-once
```

### 모듈 단위 검사
```bash
python housing/sinktank/cron_av_unified.py --module ct      # _source 동기화만
python housing/sinktank/cron_av_unified.py --module hollow  # EVIDENCE CT 형식만
python housing/sinktank/cron_av_unified.py --module serial  # 감사 PASS만
python housing/sinktank/cron_av_unified.py --module halt    # 멈춤 검출만
```

### 결과 확인
```bash
# 최신 notification JSON
ls -t C:/chemgrid/.claude/notifications/cron_av_*.json | head -1
# 또는 stdout summary 출력 (--dry-run: 파일 저장 없음)
python housing/sinktank/cron_av_unified.py --run-once --dry-run
```

---

## 7. patrol SC94 — P-AV-SKILL-MISSING

patrol.py SC94가 이 파일의 존재 여부를 검사한다 (Rule H-3).
`docs/ai/skills/av_compliance.md` 부재 시 SC94 WARN 발생.
→ 구현 위치: housing/sinktank/patrol.py SC94 블록

---

---

## 8. Module 6: zombie 깡통 검사 5종 (M696 신설)

> 근거: 사용자 명시 "깡통 없는지 20분 주기로 AV 돌려서 검증" (CT-D-20260504-A55)
> 패턴 ID: AV-WATCHDOG-001

cron_av_unified.py Module 6 = 사용자 체감 깡통 검사 (M1~M5는 메타 정합성만).

| 검사 항목 | 구현 방법 | WARN 조건 |
|----------|-----------|-----------|
| lite_executable | Popen(draw.py, QT_QPA_PLATFORM=offscreen, timeout=5초) | Popen 실패 시 |
| popup_reachable | src/app/ glob *.py → re.search(5분자 패턴) | 3종 이상 미탐지 |
| engine_health | urllib.request.urlopen HEAD × 4종 (timeout=5초) | 2종 이상 DOWN |
| uncommitted | git diff HEAD --stat 줄 수 | count > 0 WARN |
| untracked | git status --porcelain \?\? 줄 수 | count > 5 WARN |

**실행**:
```bash
python housing/sinktank/cron_av_unified.py --module zombie --dry-run
python housing/sinktank/cron_av_unified.py --module zombie --run-once
```

**Phase 8** (cron_20min_dispatcher.py):
- zombie 결과를 AV_NEXT_PROMPT.md에 추가 (3번째 발화마다 격분 모드)
- zombie FAIL → sentinel next_action=FIX_REQUIRED

**patrol SC98** P-CHEMGRID-LITE-ZOMBIE:
- module_zombie_check 미존재 → WARN
- 24h zombie FAIL 5건+ → CRITICAL (비차단)

---

---

## M1354 ZOMBIE-KILL-001 패턴 (D-M1153-002-W19 추가)

| 패턴명 | 원칙 |
|--------|------|
| ZOMBIE-KILL-001 | Worker가 직접 zombie kill 실행 금지. tools/zombie_check.py는 측정+evidence json 저장만 수행. kill 실행은 `--execute` 플래그 + CT_APPROVED 환경변수 조합만 허용. CT 명시 승인 없이 kill = Rule K (housing 인프라 침범) + Rule M (silent failure 방지 오해) 복합 위반. M1354 기원. |

*갱신: 2026-05-18 / Worker W19 / M1354*
*연동: patrol SC98 P-CHEMGRID-LITE-ZOMBIE | Rule M/K | prevention_matrix_20260518.md #17*

---

## 연관 skills

- `cron_av_session_integration.md` — unified.py 4모듈 + session inject 흐름
- `harness_enforcement.md` — patrol SC 체계 전반
- `serial_compliance.md` — Rule T 직렬강제 / audit 3팀 체계
- `cmd_hidden_strict.md` — Rule JJ cmd 창 차단
