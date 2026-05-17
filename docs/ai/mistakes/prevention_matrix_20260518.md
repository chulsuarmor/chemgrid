# 재발 방지 매트릭스 갱신 (Prevention Matrix 2026-05-18)
> **작성자**: Worker W19 (D-M1153-002-W19)
> **작성일**: 2026-05-18
> **기반**: prevention_matrix_20260425.md (M145~M365, 16 패턴) + D-M1153-002 W1~W14 산출물 (M1346~M1361)
> **목적**: 신규 5건 패턴 추출 → Rule/Hook/Skills 매핑 (Rule H 체화 4단계 의무)
> **임무**: M1354 zombie_check결함 / M1355 G7 timeout / M1356 HTML id누락 / M1360 persona 5Q raw / M1361 SC56~SC106 매트릭스
> **기존 매트릭스**: prevention_matrix_20260425.md (16패턴 유지 — K3 수정금지)

---

## 변경 전 사유 (H-1)

| M번호 | 패턴 | 왜 잘못됐는가 | 재현 조건 |
|-------|------|-------------|----------|
| M1354 | zombie_check.py 결함 | tools/zombie_check.py가 low-CPU claude 프로세스를 "zombie"로 분류했으나 CT 승인 없이 kill을 시도할 경우 활성 Worker 프로세스 종료 위험. hook이 차단해야 할 동작을 harness 도구가 실수로 수행 | zombie 6건 (PID 21508/21932/21972/22452/22460/24440) — 측정만 의무, kill 금지 |
| M1355 | G7 RUNTIME timeout | G7 runtime gate (MainWindow/predict_all/get_mechanism/DryLab_export)가 timeout으로 FAIL. 기존 미해소 문제가 매 사이클 반복 보고되나 수정 없이 "scope 외" 처리됨 | SC106 scope 외 기록 — 처리 없는 반복 = Rule W "같은 문제 2회 반복=하네스결함" 경계 |
| M1356 | HTML before-after-images id 누락 | cycle HTML의 before-after-images 섹션에 `id` 속성이 없어 AV check_html_quality가 탐지 실패. W5 산출물에서 2건 발생 | cycle_M1306, cycle_D-M858 — patrol 탐지 대상이었으나 SC 미등록 |
| M1360 | user_persona_critic 5질문 raw evidence | Rule TT-c raw evidence 의무(tasklist/ps/git log/파일경로/diff IDENTICAL 중 1개 이상)가 실제 출력 없이 "fallback" 처리될 위험. OPENROUTER_API_KEY 미설정 = Kimi K2.6 base 패턴만 사용 → 약화된 검증 | OPENROUTER_API_KEY NOT_SET 환경에서 self_simulate() 호출 시 |
| M1361 | patrol SC56~SC106 매트릭스 갱신 | SC56~SC106 매트릭스가 신규 패턴을 반영하지 않아 자동 탐지 공백 발생. W14에서 확인된 SC 등록 누락이 재발 방지 chain을 끊음 | 신규 패턴 등록 후 patrol.py SC 번호 미추가 시 탐지 공백 |

---

## 신규 반복 패턴 5건 (매트릭스 #17~#21)

| # | 카테고리 | 등장 M번호 | 추정 빈도 | 현재 방어 수단 | 추가 권고 |
|---|---------|-----------|---------|--------------|---------|
| 17 | **Zombie 프로세스 오처리 (CT 승인 없이 kill 시도)** | M1352 M1354 | 매 배포 사이클 1회+ | av_compliance.md SC98 P-CHEMGRID-LITE-ZOMBIE; Rule M (silent failure 금지) | tools/zombie_check.py에 `--dry-run` 기본 모드 강제. kill 실행은 `--execute` 플래그 + CT_APPROVED 환경변수 조합만. 측정 결과를 evidence json에 저장하고 kill은 별도 CT Worker에서만 수행 |
| 18 | **G7 RUNTIME 만성 FAIL 미해소 (scope 외 처리 반복)** | M1355 M846 M1346 | 매 사이클 반복 (10회+) | mistakes/other.md; Rule M; patrol G7 체계 전체 | G7_RUNTIME FAIL이 N회 연속 발생 시 CT 강제 에스컬레이션. "scope 외" 레이블로 무시하는 패턴을 patrol SC105 P-G7-CHRONIC-FAIL로 탐지 (WARN). IDLE_THRESHOLD 이내 해소 없으면 CRITICAL 격상 |
| 19 | **cycle HTML before-after-images id 속성 누락** | M1356 M1347 | cycle HTML 신규 생성 시마다 위험 | Rule CC (메타 사이클 HTML 품질); AV check_html_quality | cycle_html 생성 모든 경로에서 `id="before-after-images"` 속성 강제 삽입 검증. patrol SC106 P-HTML-BEFORE-AFTER-ID 신설 탐지 (grep `before-after-images` in HTML) |
| 20 | **user_persona_critic API key 미설정 시 약화 검증** | M1360 | OPENROUTER_API_KEY 미설정 환경마다 | Rule TT-b (base 패턴 fallback 허용 명시); skills/user_env_auto_verify.md | OPENROUTER_API_KEY 미설정 시 Rule TT-b fallback 허용이지만 base 패턴만으로는 anger_simulator 189건 중 고난도 한국어 패턴 커버 불가. .env에 OPENROUTER_API_KEY 등록 의무화 제안 + 미설정 시 patrol SC107 P-PERSONA-KEY-MISSING WARN |
| 21 | **patrol SC 번호 누락 (신규 패턴 → SC 미등록 chain 단절)** | M1361 | 신규 패턴 등록 시마다 (매 체화 4단계 H-3) | Rule H-3 (patrol/AV 자동검사 강화); harness_embodiment.md G7-SC5 | 체화 4단계 H-3 완료 기록에 SC 번호 명시 의무. "탐지 불가"로 면제받은 것과 "미등록"을 구분. prevention_matrix 갱신 시 H-3 컬럼에 SC번호 또는 "SC-N/A(이유)" 중 하나 필수 기재 |

---

## skills 패턴 추출 (H-2)

### ZOMBIE-KILL-001
- **원칙**: Worker가 직접 kill 실행 금지. tools/zombie_check.py는 측정+evidence json 저장만. kill은 CT 명시 승인 + 별도 Worker만 수행.
- **갱신 파일**: `docs/ai/skills/av_compliance.md` (M1354 패턴 추가)

### G7-CHRONIC-FAIL-001
- **원칙**: G7_RUNTIME FAIL이 "scope 외"로 3회 이상 연속 반복되면 Rule W "2회=하네스결함" 발동 의무. CT가 해소 Worker를 즉시 dispatch.
- **갱신 파일**: `docs/ai/skills/harness_embodiment.md` (M1355 패턴 추가)

### HTML-BEFORE-AFTER-ID-001
- **원칙**: cycle HTML 생성 시 `<section id="before-after-images">` 또는 해당 id 속성 필수. AV check_html_quality 6번째 체크 항목에 포함.
- **갱신 파일**: `docs/ai/skills/cycle_html_card_format.md` (M1356 패턴 추가)

### PERSONA-CRITIC-KEY-001
- **원칙**: Rule TT-b base fallback은 기능적 degradation이며 P1. .env OPENROUTER_API_KEY 설정 = 완전 검증의 전제조건. 미설정 시 patrol WARN 발생.
- **갱신 파일**: `docs/ai/skills/user_env_auto_verify.md` (M1360 패턴 추가)

### SC-REGISTER-001
- **원칙**: 체화 4단계 H-3 완료 시 반드시 SC번호 명시. "탐지 불가 — 이유" 또는 "SC-NNN 신설" 중 하나. 빈 칸 = H-3 미이행 = G7-SC5 WARN.
- **갱신 파일**: `docs/ai/skills/harness_embodiment.md` (M1361 패턴 추가)

---

## patrol/AV 자동검사 강화 (H-3)

| 신규 SC | 패턴 | 탐지 로직 | 비고 |
|---------|------|---------|------|
| SC105 P-G7-CHRONIC-FAIL | G7_RUNTIME FAIL이 mistakes.md에 3회+ 동일 원인으로 기록됨 | mistakes.md에 "G7_RUNTIME" + "FAIL" + "timeout" 3회+ grep | WARN 비차단. CT 에스컬레이션 의무 |
| SC106 P-HTML-BEFORE-AFTER-ID | cycle HTML에 before-after-images id 미존재 | glob docs/reports/cycle_*.html → grep `before-after-images` 0건이면 WARN | WARN 비차단 |
| SC107 P-PERSONA-KEY-MISSING | OPENROUTER_API_KEY 미설정 | os.environ.get('OPENROUTER_API_KEY') is None | WARN 비차단 (Rule TT-b fallback 허용이므로) |

**SC105-107 patrol.py 등록 대상** — housing/sinktank/patrol.py check_g7_serial_compliance() 내 추가 의무 (Rule H-3 → 별도 Worker가 patrol.py 수정 시)

**주의**: 본 W19는 mistakes/skills 갱신 전담. patrol.py 코드 수정은 Rule K3 (Surgical Changes) + Rule 4 (도메인 격리) 상 별도 Worker 임무. 본 파일에 SC 번호 사전 예약만 수행.

---

## CLAUDE.md 규칙 검토 (H-4)

| 패턴 | 해당 Rule | 변경 내용 |
|------|---------|---------|
| ZOMBIE-KILL-001 | Rule M (silent failure 금지) + Rule K (housing/ 인프라) | 기존 Rule M/K로 충분. 신규 Rule 불필요 |
| G7-CHRONIC-FAIL-001 | Rule W (2회=하네스결함) + Rule T (직렬강제) | Rule W 이미 "같은 문제 2회 반복=하네스결함" 명시. 강화 보완: patrol SC105로 자동 탐지 |
| HTML-BEFORE-AFTER-ID-001 | Rule CC (메타 사이클 HTML 품질) | Rule CC에 "before-after-images id 속성 필수" 1문장 보강 권고 (CT 결정 후) |
| PERSONA-CRITIC-KEY-001 | Rule TT (사용자시뮬레이션의무) | Rule TT-b 이미 "미설정 시 base 패턴 fallback" 허용 명시. SC107 WARN 추가로 가시성 확보 |
| SC-REGISTER-001 | Rule H-3 (patrol/AV 자동검사 강화) | Rule H-3 이미 "탐지 불가 시 EVIDENCE에 명시" 규정. SC 번호 의무 기재 강화는 harness_embodiment.md 체화 |

**신규 Rule 불필요**: 5건 모두 기존 Rule(M/K/W/T/CC/TT/H) 범위 내. 30줄 압축 인덱스 유지.

---

## 요약 통계 (갱신)

| 항목 | 2026-04-25 | 2026-05-18 갱신 |
|------|-----------|----------------|
| 총 mistakes.md 항목 수 | 163건 (M145~M364) | ~780건 (M145~M933, 본 작업 기준) |
| 신규 패턴 카테고리 | 16개 | 21개 (+5) |
| 현재 LAST_M_NUMBER | M364 | M933 (실제 최신) |
| 본 W19 M번호 | — | M1365 (예약) |
| 신규 SC 예약 | — | SC105~SC107 |

---

## 고빈도 패턴 Top 5 갱신 (2026-05-18)

기존 Top 5 (prevention_matrix_20260425.md) 유지 + W19 신규 관찰:

6. **G7 RUNTIME 만성 FAIL (#18)** — 10회+ 반복: SC105 WARN 탐지 후 CT dispatch 강제화 필요
7. **zombie 오처리 (#17)** — 배포 사이클마다: kill 전 CT 승인 체계 강화
8. **HTML id 속성 누락 (#19)** — cycle HTML 생성 시: SC106 + check_html_quality 6번째 항목 통합

---

## 연동 파일 갱신 목록

- `docs/ai/mistakes/prevention_matrix_20260425.md` — 기존 매트릭스 유지 (K3: 수정 금지, 이 파일이 추가 보완)
- `docs/ai/skills/harness_embodiment.md` — G7-CHRONIC-FAIL-001 + SC-REGISTER-001 패턴 추가
- `docs/ai/skills/av_compliance.md` — ZOMBIE-KILL-001 패턴 추가
- `docs/ai/skills/cycle_html_card_format.md` — HTML-BEFORE-AFTER-ID-001 패턴 추가
- `docs/ai/skills/user_env_auto_verify.md` — PERSONA-CRITIC-KEY-001 패턴 추가
- `housing/evidence/M1365_W19_prevention_matrix.md` — evidence 파일

---

*생성: Worker W19, D-M1153-002-W19, 2026-05-18*
*Rule H 체화 4단계 이행: H-1(변경 전 사유) + H-2(skills 패턴) + H-3(patrol SC 예약) + H-4(CLAUDE.md 검토)*
*Rule W 이행: 신규 5건 패턴 → 방어 매트릭스화 완료*
