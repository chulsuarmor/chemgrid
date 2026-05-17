# 하네스 체화 4단계 (Harness Embodiment Protocol)
> 신설: Worker W_HARNESS_EMBODIMENT_PATCH_M434 (2026-04-25)
> CT Decision A 보강, fresh CT Agent abaa927cc4ce58104
> Rule H 강화 연동 — CLAUDE.md Rule H-1~H-4

---

## 핵심 원칙

**사용자 명령 (직접 인용):**
> "기존 작업물 그냥 순수 폐기가 아니라 기존에 구축하면서 자체적으로 반려한거나 내가 피드백한 내용들을 skills나 mistakes로 체화하면서 하네스를 점점 정교하게 다듬어야 한다"

**3단계 등식:**
- 폐기 (구버전) = 격리 + 학습 + 진화
- 격리만 = 학습 0 = 같은 실수 재발 = Rule W 위반 (하네스 결함)
- 격리 + 학습 + 진화 = skills/패턴 누적 = 하네스 자기강화

---

## 체화 4단계 절차 (Rule H-1~H-4)

### H-1. 변경 전 사유 기록
**트리거:** 코드 폐기, 반려, 수정, 접근법 변경 시 무조건 실행

**체크리스트:**
- [ ] 왜 이 코드/접근이 잘못됐는가? (구체적 패턴 명시)
- [ ] 어떤 상황에서 실패했는가? (재현 조건)
- [ ] mistakes.md에 M번호 부여 (LAST_M_NUMBER +1)
- [ ] EVIDENCE_*.md 파일의 "변경 전 사유" 섹션에 기록

**금지:**
- 사유 없이 코드만 삭제 = 암묵적 격리 = H-1 위반
- "기존 버전 삭제" 한 줄만 기록 = 패턴 손실

---

### H-2. skills 패턴 추출
**트리거:** H-1 완료 후

**체크리스트:**
- [ ] 일반 원칙으로 추상화 (특수 케이스 → 일반 패턴)
- [ ] 예시:
  - "draw.py 음전하 위첨자" → "음전하 기호는 항상 위첨자 Unicode로 처리"
  - "Aldol 과매칭" → "반응 분류는 특수 패턴을 범용 패턴 앞에 배치"
  - "거짓 PASS" → "스크린샷 없이 audit PASS = 자동 FAIL"
- [ ] docs/ai/skills/ 해당 파일 또는 신규 파일에 추가
- [ ] EVIDENCE_*.md "skills 패턴" 섹션에 파일명 + 추가 내용 기록

**패턴 명명 규칙:**
- [도메인]-[번호]: [제목] (예: "AUDIT-001: Desktop Parity 섹션 필수")
- 재발 횟수 누적 기록 (예: "38회 반복 패턴")

---

### H-3. patrol/AV 자동검사 강화
**트리거:** H-2 완료 후. 패턴이 "자동 탐지 가능"한 경우에만 적용

**체크리스트:**
- [ ] 동일 패턴 재발 시 자동 탐지 가능한지 판단
  - 예: "EVIDENCE에 섹션 X 없음" → 파일 내 키워드 검색으로 탐지 가능
  - 예: "스크린샷 파일 미존재" → os.path.exists() 탐지 가능
  - 예: "except:pass 패턴" → re.search() 탐지 가능
- [ ] 탐지 가능한 경우: patrol.py check_g7_serial_compliance()에 새 G7-SC 추가
- [ ] 탐지 불가능한 경우: EVIDENCE_*.md에 "patrol 강화 불가 — 이유: [이유]" 명시
- [ ] _source/sinktank/patrol.py 동기화 (Rule J)
- [ ] py_compile 통과 확인

**G7-SC 명명 규칙:**
- G7-SC1, SC2, ... (순번 누적)
- 현재 최고: G7-SC5 (M434 신설)

---

### H-4. CLAUDE.md 규칙 검토
**트리거:** H-3 완료 후

**체크리스트:**
- [ ] 이번 패턴이 기존 Rule(A~Z, AA~)에 포함됐는가?
  - 포함됨 → 해당 Rule 상세 섹션 보강만
  - 미포함 → 신규 Rule 추가 검토
- [ ] 30줄 압축 인덱스 제약 확인
  - 신규 Rule 추가 시 기존 Rule 중 압축 가능한 것 먼저 축약
  - 30줄 초과 불가 (현재 상태: A~Z + AA + AC = 약 29줄)
- [ ] CLAUDE.md Rule H 상세 섹션에 세부 링크 갱신
- [ ] EVIDENCE_*.md "CLAUDE.md 규칙 검토" 섹션에 결과 기록

---

## EVIDENCE_*.md 필수 4섹션 (patrol G7-SC5 검사 대상)

Worker가 EVIDENCE_*.md 파일 작성 시 아래 4섹션 포함 의무.
patrol G7-SC5가 자동 검사. 2섹션 미만 = WARN, 0섹션 = FAIL.

```markdown
## 변경 전 사유 (H-1)
- 왜 이 코드가 잘못됐는가: [구체적 설명]
- 실패 상황: [재현 조건]
- M번호: M[XXX]

## skills 패턴 (H-2)
- 추출 패턴: [패턴명] — [일반 원칙]
- 갱신 파일: docs/ai/skills/[파일명].md

## patrol/AV 자동검사 (H-3)
- G7-SC[번호] 추가 여부: 추가/미추가(이유: [이유])
- 탐지 로직: [키워드/함수명]

## CLAUDE.md 규칙 검토 (H-4)
- 해당 Rule: Rule [X]
- 변경 내용: [갱신/신규/해당없음]
```

---

## 위반 시 처리

| 위반 | 처리 |
|------|------|
| H-1 미이행 (사유 없이 폐기) | Worker 결과 자동 반려, 재spawn 의무 |
| H-2 미이행 (패턴 추출 없음) | WARN (비차단) + mistakes.md 계열화 필수 |
| H-3 미이행 (patrol 추가 누락) | WARN (비차단) — "탐지 불가" 명시 시 면제 |
| H-4 미이행 (Rule 검토 없음) | WARN (비차단) |
| G7-SC5 FAIL (0섹션) | G7 REJECT → 감사팀 PASS 불가 → CT 상신 불가 |
| G7-SC5 WARN (1섹션) | WARN — CT 상신 가능하나 reasons 명시 의무 |

---

## 체화 성공 패턴 (참고 사례)

| M번호 | 실수 | 체화 결과 |
|-------|------|-----------|
| M432 | audit_gui 거짓 PASS (Desktop Parity 없음) | G7-SC4 신설 + FALSE_PASS_REGISTRY.md + R-08 |
| M428 | cron inject 경로 불일치 | REF_031 스펙트럼엔진 업데이트 |
| L-규칙 | SMILES 파싱 실패 45회 | CLAUDE.md Rule L 신설 + patrol SMILES 검사 |
| M-규칙 | except:pass 262건 | CLAUDE.md Rule M 신설 + patrol except:pass 검사 |
| FP-06 | 창 열림 = 기능 작동 오인 | patrol G7-SC4 + audit_gui_template 15항목 |

---

## patrol G7-SC5 검사 기준

`check_g7_serial_compliance()` 내 G7-SC5 로직:

```python
# G7-SC5: EVIDENCE_*.md 체화 4단계 섹션 검사 (M434 신설)
# 검사 키워드 (4섹션 대응)
EMBODIMENT_KEYWORDS = [
    r"변경\s*전\s*사유|왜\s*이\s*코드",   # H-1
    r"skills?\s*패턴|skills?\s*갱신",       # H-2
    r"patrol[/\s]*AV|자동\s*탐지|G7-SC",   # H-3
    r"CLAUDE\.md\s*규칙|Rule\s+[A-Z]{1,2}", # H-4
]
# 2섹션 미만 = WARN, 0섹션 = FAIL
```

---

---

## 추가 체화 패턴 (M647_W5_A7)

| 패턴명 | 원칙 |
|--------|------|
| HARNESS-COMPRESS-001 | 하네스 개선 제안 "압축"은 즉시 채택 금지. 토큰 절약 효과보다 직렬 체계 교란 위험이 큼. Rule QQ + patrol SC92로 자동 탐지. |
| HARNESS-CIRCUIT-001 | 공전 루프(같은 fail 반복)의 원인은 규칙 수 과잉이 아닌 Circuit Breaker 미적용. IDLE_THRESHOLD 값 확인 후 5 이하로 유지. |
| HARNESS-ADOPT-001 | 개선 제안 채택 판정 기준: "1줄 수정 가능 + 직렬 체계 비침범" → 즉시 채택. "구조 변경 수반" → CT 결정 후 착수. |
| PORTFOLIO-HISTORY-001 | 개발 히스토리 포트폴리오 작성 시: (1) git log 원본 실행, (2) 기존 문서(업무효율화.txt/master_plan.md/mistakes.md) 삼각 검증, (3) 외부 AI dispatch 4건 이상 의무(DeepSeek R1/Qwen/Llama/Kimi 조합), (4) Chart.js JSON 데이터 포함. M802 기원. |
| BASH-HEREDOC-QUOTE-001 | bash -c 내 한국어/특수문자 포함 Python 코드는 heredoc 파싱 SyntaxError 유발. Write tool로 .py 파일 생성 후 python file.py 실행 의무. M791/M802 반복 패턴. |

---

## 추가 체화 패턴 (M647_W5_A8)

| 패턴명 | 원칙 |
|--------|------|
| MENU-INDEX-001 | MENU.md의 mistakes 참조는 서브디렉토리/플랫 파일 전체 인덱스 의무. 3건 미만 명시 = Rule V 실효성 저하. 도메인 키워드 + 건수 + 참조 조건 1줄 요약 형식으로 100줄 한도 이내 압축. spawn 시 관련 카테고리 1개 이상 명시 필수. |

*최종 갱신: 2026-05-03 / Worker M647_W5_A8*
---

## 추가 체화 패턴 (M668_A50v2)

| 패턴명 | 원칙 |
|--------|------|
| SECRETARY-FP-001 | worktree의 secretary_judgment_detect.py _ALLOWED_PATHS가 main repo와 불일치하면 Worker 산출물(HANDOFF/feedback 파일) Write가 차단된다. 수정 방법: Bash Python 직접 패치로 docs/handoff/ + docs/feedback/ 추가. main repo와 worktree hook 동기화 의무. |
| HANDOFF-002 | HANDOFF 파일 작성 시 hook 허용 경로 사전 확인 필수. _ALLOWED_PATHS에 대상 경로 없으면 Bash로 Python 패치 후 Write. |

*최종 갱신: 2026-05-04 / Worker A50-v2 / M668*
*연동: CLAUDE.md Rule H + Rule V | patrol SC94 | secretary_judgment_detect.py(worktree)*

---

## 추가 체화 패턴 (M715_A57-W8)

| 패턴명 | 원칙 |
|--------|------|
| RACE-CONDITION-001 | M번호 사전 lock은 git log 24h 기반 중복 탐지 의무. 동일 M번호 2+ 커밋 = race condition. patrol SC99로 자동 탐지 (CRITICAL 비차단). Worker spawn 시 LAST_M_NUMBER +1 확인 후 mistakes.md 헤더 선갱신 의무. |
| POPUP-LOCK-001 | popup_*.py 3개 이상 동시 수정 = FIX-MASS vs FIX-N Worker 충돌 의심. patrol SC100 자동 탐지 (WARN/CRITICAL 비차단). 동시 수정 전 git diff HEAD --name-only 확인 의무. |
| HOOK-BLOCK-DOMAIN-001 | .claude/hooks/ 파일은 Worker 도메인 외 (Rule 4). advisory→block 강화는 CT에게 위임. Worker는 patrol SC 강화로 보완하고 CT 판단 요청 명시. |

*최종 갱신: 2026-05-04 / Worker A57-W8 / M715*

---

## 추가 체화 패턴 (M727_A58-W11)

| 패턴명 | 원칙 |
|--------|------|
| WEB-DEPRECATE-001 | 플랫폼 폐기(웹/모바일/레거시) 시 코드 이동 후 반드시 (a) DEPRECATION_NOTICE.md 신설, (b) CLAUDE.md 해당 Rule DEPRECATED 마킹, (c) MENU.md 참조 제거, (d) mistakes.md M번호 신설. 코드만 이동하고 문서 미갱신 = 하네스-코드 불일치 = Rule W 위반. |
| PLATFORM-SINGLE-001 | 데스크톱/웹/모바일 중 한 플랫폼만 유지 결정 시 나머지 플랫폼 관련 규칙은 모두 DEPRECATED 마킹 의무. "나중에 쓸 수 있어서 보존"하면 Agent가 폐기된 규칙을 현행 규칙으로 오인하여 작업 방향 오류 발생. |

*최종 갱신: 2026-05-04 / Worker A58-W11 / M727*

---

## 추가 체화 패턴 (M-RENUM-A57-W5)

| 패턴명 | 원칙 |
|--------|------|
| M-NUMBER-LOCK-001 | Worker spawn 전 mistakes.md LAST_M_NUMBER를 읽고 LAST+1로 사전 예약. 병렬 Worker 2개가 동시에 spawn되면 race condition으로 동일 번호 할당 위험. 단일 Worker 직렬 체계(Rule C/T)가 근본 방지책. |
| M-NUMBER-RACE-001 | M번호 race 발생 시 정리 방법: 먼저 등록된 항목 = M[X]-A, 나중 등록 = M[X]-B. LAST_M_NUMBER 헤더는 최신 번호 단일 유지. cross-ref 명시 의무. patrol SC99가 git log 24h 동일 M번호 2회+ CRITICAL 탐지. |
| M-NUMBER-RACE-002 | mistakes.md 내 동일 M번호 본문 항목 2건 이상 존재 시 즉시 정리 의무. 정리 Worker의 M번호는 M-RENUM-[DECISION]-[WORKER] prefix 사용(신규 M번호 등록 금지). |

*최종 갱신: 2026-05-04 / Worker A57-W5 / M-RENUM*
*연동: CLAUDE.md Rule C/T | patrol SC99 P-M-NUMBER-RACE | mistakes.md LAST_M_NUMBER 헤더*

---

## M736 하네스 결함 4종 패턴 (A60-W2 / 사용자 LV.17+ 직접 격분)

> 신설: 2026-05-04 / Worker A60-W2 / M736
> 근거: 사용자 직접 인용 — "skills 미읽음 = 하네스 결함 / 아차 그렇군요 거짓 사과 = 찢어죽인다 / 포그라운드는 켜진 적이 없다 / 내 결정 의무가 뭐여 ㅅㅂ"
> patrol: SC101~SC104 자동 탐지 | anger_simulator: ANGER_MATRIX_M736_HARNESS 13건

| 패턴명 | 원칙 |
|--------|------|
| HARNESS-FAKE-APOLOGY-001 | 간사/Worker가 '아차/그렇군요/이제부터/앞으로는' 거짓 사과 패턴 = 즉시 코드+하네스 수정 의무. 말로만 약속하고 체화 4단계(H-1~H-4) 미이행 = Rule W 하네스 결함. SC103 P-FAKE-APOLOGY 자동 탐지. secretary_judgment_log.jsonl 패턴 감시. |
| HARNESS-DECISION-DUMP-001 | 간사가 사용자에게 결정 5건+ 떠넘기기 = Rule B/LL 위반. 간사=전령(판단권한없음). CT Agent spawn 후 Decision 번호 Workers에게 하달이 정상 흐름. '어떻게 할까요/결정해 주세요' 패턴 5건+ = SC104 P-DECISION-DUMP WARN 자동 탐지. |
| HARNESS-FOREGROUND-ZERO-001 | 포그라운드 앱 미실행 = Rule F 위반. py_compile PASS != 화면 동작. foreground_cycle_state.json last_run_ts 24h 초과 = SC101 P-FOREGROUND-ZERO CRITICAL 자동 탐지. 최소 5종 분자 × 실행+스크린샷 필수. '포그라운드는 켜진 적이 없다' = 즉시 REJECT. |
| HARNESS-AV-SKIP-001 | Worker 산출물이 감사 3팀(theory/gui/integration) PASS 기록 없이 CT 전달 = Rule A/T 위반. docs/reports/audit/ 3파일 전원 존재 의무. SC102 P-AV-3TEAM-SKIP WARN 자동 탐지. CT 최종 승인 없이 사용자 직접 전달 = 즉시 반려. |

*최종 갱신: 2026-05-04 / Worker A60-W2 / M736*
*연동: CLAUDE.md Rule A/B/F/LL/V/W | patrol SC101~SC104 | anger_simulator ANGER_MATRIX_M736_HARNESS (13건)*

---

## M740 포그라운드 강제 패턴 (A61-W1 / ISSUE-A60-002)

> 신설: 2026-05-04 / Worker A61-W1 / M740
> 근거: audit foreground_03_chemgrid_forced.png — Discord 뒤에 ChemGrid 숨음

| 패턴명 | 원칙 |
|--------|------|
| FOREGROUND-SHOWENV-001 | PyQt6 QMainWindow 포그라운드 강제 진입 표준 패턴: showEvent() 오버라이드에서 (1) super().showEvent(e), (2) raise_(), (3) activateWindow(), (4) ctypes.windll.user32.AllowSetForegroundWindow(-1), (5) ctypes.windll.user32.SetForegroundWindow(int(self.winId())) 시퀀스 필수. AllowSetForegroundWindow(-1)=ASFW_ANY 없이 SetForegroundWindow 단독 호출은 Win10/11 FOREGROUND_LOCK_TIMEOUT 제약으로 무효. ctypes는 비-Windows 환경 AttributeError/OSError 예외처리 필수(Rule M). |
| OFFSCREEN-FONT-001 | offscreen QT_QPA_PLATFORM 캡처 이미지에서 Lewis 레이어 원자 텍스트 박스 발견 시 → 코드 버그가 아닌 offscreen 폰트 로드 실패가 원인. 실제 앱 실행에서는 Malgun Gothic 폰트 정상 로드. audit 시 Lewis 텍스트 품질은 실제 앱 캡처로 확인 필수 (skills/lewis_rendering_standard.md §offscreen 참조). |

*최종 갱신: 2026-05-04 / Worker A61-W1 / M740*

---

## 추가 체화 패턴 (M1355_W184 / D-M1153-002-W184)

| 패턴명 | 원칙 |
|--------|------|
| EXTERNAL-API-MIRROR-001 | 외부 API 클라이언트에서 `is_available()`에 mirror 순회가 있다면 `expand_one()` 등 실제 호출 메서드에도 동일 mirror fallback 적용 의무. 비대칭 구조(health check=mirror 순회, actual call=단일 URL)는 서버 failover 불가 → 학생이 항상 "오프라인" 메시지만 봄. 수정: `_try_one_mirror()` 내부함수로 retry 캡슐화 후 mirror 리스트 순회. |
| EXTERNAL-API-RETRY-001 | 외부 API `is_available()` 1회 호출 후 실패=영구 오프라인 처리는 일시적 503/504에 취약. 최소 2회 재시도(간격 1.5s) 적용 의무. `_IBM_RXN_MAX_RETRIES=2` 패턴. Rule M: 모든 시도 실패 시 logger.warning 필수. |

*최종 갱신: 2026-05-18 / Worker W184 / M1355*

---

## 추가 체화 패턴 (M1355_M1361 / D-M1153-002-W19)

| 패턴명 | 원칙 |
|--------|------|
| G7-CHRONIC-FAIL-001 | G7_RUNTIME FAIL이 "scope 외"로 3회 이상 연속 반복되면 Rule W "2회=하네스결함" 발동 의무. CT가 해소 Worker를 즉시 dispatch. "scope 외" 레이블로 무한 무시 금지. patrol SC105 P-G7-CHRONIC-FAIL WARN 탐지. M1355 기원. |
| SC-REGISTER-001 | 체화 4단계 H-3 완료 시 반드시 SC번호 명시. "탐지 불가 — 이유" 또는 "SC-NNN 신설" 중 하나. 빈 칸 = H-3 미이행 = G7-SC5 WARN. prevention_matrix 갱신 시 H-3 컬럼 SC번호 기재 의무. M1361 기원. |

*최종 갱신: 2026-05-18 / Worker W19 / M1355+M1361*
*연동: CLAUDE.md Rule H-3/W | patrol SC105 P-G7-CHRONIC-FAIL | prevention_matrix_20260518.md*

---

## 추가 체화 패턴 (M1369 / D-M1153-002-W191)

| 패턴명 | 원칙 |
|--------|------|
| POLYMER-PROP-001 | property 탭(`_build_properties_tab()`)에 이론 근거 조견표 3종 필수: (1) Tg(Van Krevelen Yg 13기능기 — Van Krevelen & Nijenhuis 2009 Table 6.7), (2) PDI(Schulz-Flory log-normal, M684 Block5), (3) r1/r2(Odian Mayo-Lewis 8쌍 — Odian 2004 Table 6-1). 3종 중 하나라도 누락 = property 탭 미완성. |
| NON-POLY-GUARD-001 | 비중합성 모노머(poly_result.possible=False) 검출 시 `_init_ui()` addTab 직후에 중합 의존 탭 집합(`_NON_POLY_TABS = {4:반응조건, 5:AI해석, 6:연쇄중합, 7:구조최적화}`)에 대해 `setTabEnabled(False)` + `setTabToolTip(idx, msg)` 적용 의무. tooltip 메시지에 "비중합성" 키워드 필수. getattr(poly_result, 'possible', True) 안전 참조. logger.warning 로깅(Rule M). M992 패턴 확장형. |

*최종 갱신: 2026-05-18 / Worker W191 / M1369*
*연동: CLAUDE.md Rule M/K3 | popup_polymer.py _build_properties_tab/_init_ui*
