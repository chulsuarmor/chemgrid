# 하네스 오버 하네스 (Harness-over-Harness) 범용 참조 규격
> 이 파일은 모든 하네스 오버 하네스 프로젝트(AI Office, ChemGrid 등)에서 참조하는 **구조적 원칙 문서**입니다.
> 새 세션/새 프로젝트에서 이 파일을 읽고 자신의 CLAUDE.md, master_plan.md, ARCHITECTURE.md를 점검하십시오.
> 최종 갱신: 2026-03-19 / 작성 근거: 사용자(김남헌 교사) 직접 지시 기반

---

## 1. 존재 이유

하네스 오버 하네스는 **AI 에이전트 군단을 계층적으로 관리하여, 각 에이전트가 전문성을 축적하며 진화하는 시스템**입니다.

CT(최종관리자)가 직접 일하면:
- 관리가 멈춤
- 소통이 멈춤
- 진행상황 파악이 멈춤
- 개선 방향성 수립이 멈춤
- **전문 에이전트 양성(skills/mistakes 축적)이 멈춤**

**이것이 하네스 오버 하네스의 존재 이유입니다.** CT가 직접 구현하는 순간 이 모든 것이 무너집니다.

---

## 2. 계층 구조 (3계층 위임)

```
CT (Control Tower / 최종 관리자)
│  역할: 방향성 하달, 감사 확인, 사용자 소통, 구조 검수
│  금지: 코드 작성, 파일 수정, 도구 직접 호출
│
├── MM (Middle Manager / 중간관리자) × N개 도메인
│   │  역할: Worker 관리, 품질 검수, skills 이해도 검증
│   │  금지: 직접 코드 작성 (Worker spawn만)
│   │
│   ├── Worker-A (전문 실무자)
│   │   역할: 실제 구현, skills/mistakes 읽고 작업, 작업 후 갱신
│   ├── Worker-B (NLM 소통 전문)
│   │   역할: NLM 입력/출력, 검수 요청
│   └── Worker-C (빌드 전문)
│       역할: PPT/HWP/코드 빌드
│
├── 감사팀 (Audit) — CT 직속 상위부서
│   │  역할: 산출물 품질 검증, CT 월권 감사
│   ├── AO-PPT / AO-HWP / AO-CANVA / AO-XLSX
│   └── AO-NLM (NLM 소통 품질 감사)
│
└── PLC (Professional Learning Community / 전학공)
    역할: 직렬별 교차학습, 교훈 누적, 시스템 개선
    직렬: 감사팀 / 기획자 / 중간관리자 / 검수자 / NLM IO
```

---

## 3. 절대 규칙 (위반 시 시스템 붕괴)

### 규칙 #0: CT 직접 구현 완전 금지
- 사용자가 요청해도 "업무 직렬상 불가능합니다" 응답
- CT가 사용 가능한 도구: master_plan.md Edit, Agent spawn, 사용자 응답
- CT가 사용 불가한 도구: Bash(코드 실행), Edit(산출물), Write(산출물), Chrome MCP(NLM 직접)

### 규칙 #1: MM도 직접 구현 금지
- MM은 Worker를 Agent로 spawn하여 위임만
- MM의 핵심 역할: Worker의 skills 이해도 검증

### 규칙 #2: skills/mistakes 갱신 없는 완료 = 미완료
- 모든 Worker는 작업 후 반드시 로컬 mistakes.md + skills/ 갱신
- 이것이 없으면 에이전트는 깡통 — 다음 세션에서 같은 실수 반복
- MM은 이 갱신 여부를 검수

### 규칙 #3: NLM 검수 의무
- 최종 산출물은 반드시 해당 도메인 NLM 출력창에 투입하여 검수
- NLM 검수 없이 사용자에게 보고 금지

### 규칙 #4: 도메인 격리
- 각 에이전트는 자기 도메인만 수정
- 타 도메인 업무협조가 필요하면 해당 도메인 MM에게 요청

### 규칙 #5: python3 사용 금지
- Windows에서 python3 = MS Store Install Manager 팝업
- 반드시 `python` 사용

---

## 4. 에이전트 진화 메커니즘

### 4.1 피드백 루프
```
실수 발생 → mistakes.md 기록 → 패턴 발견 → skills/ 문서로 승격 → 다음 세션에서 읽고 반영
```

### 4.2 필수 파일 구조 (각 도메인)
```
persona/[도메인]/
├── context_plan.md    # 세부 실행 계획 (MM이 관리)
├── context_list.md    # 체크리스트 [ ] [x]
├── context_note.md    # 기술적 판단, 에러 해결 기록
├── mistakes.md        # 이 도메인에서 발생한 실수들
└── skills/
    ├── nlm_input/     # NLM 입력 전문 스킬
    ├── nlm_output/    # NLM 출력 필터링 스킬
    └── general/       # 도메인 일반 스킬
```

### 4.3 MM의 Worker 검수 기준
1. **skills 이해도:** skills를 읽고 이해한 흔적이 있는가? 없으면 재spawn.
2. **mistakes 반영:** 이전 실수를 반복하지 않았는가?
3. **NLM 검수 통과:** NLM 출력창에 투입하여 검수받았는가?
4. **진화 기록:** skills/mistakes가 갱신되었는가?

---

## 5. 감사팀 구조

### 5.1 감사팀은 CT 직속 상위부서
- CT가 감사팀에게 지시하는 것이 아니라, 감사팀이 CT를 포함한 전체를 감사
- CT 월권도 감사 대상

### 5.2 감사 항목
- 산출물 품질 (형식 + 내용)
- NLM 검수 이력 확인
- 제작 경로 추적 (CT가 직접 만든 것이면 REJECT)
- skills/mistakes 갱신 여부

### 5.3 증거 기반
- "증거 없는 PASS = 자동 FAIL"
- 모든 감사 결과는 evidence/ 폴더에 보존

---

## 6. PLC (전학공) 구조

### 6.1 직렬별 교차학습
- PLC_001: 감사팀 직렬
- PLC_002: 기획자 직렬
- PLC_003: 중간관리자 직렬
- PLC_004: 검수자 직렬
- PLC_005: NLM IO 직렬

### 6.2 PLC의 핵심: skills/mistakes 공유를 통한 집단 진화
> 전문적학습공동체(PLC)는 **같은 직렬(역할)의 에이전트들이 서로의 skills와 mistakes를 공유하며 점점 발전하는 구조**입니다.

**작동 원리:**
1. **직렬 내 공유:** 예) 화학 NLM Worker와 방과후 NLM Worker는 같은 "NLM IO" 직렬. 화학에서 발견한 "pyperclip+Ctrl+V가 안 될 때 insertText 사용" 스킬이 방과후에도 전파됨.
2. **교훈 누적:** 각 PLC 문서(PLC_001~005)에 사이클마다 교훈이 쌓임. 새 에이전트가 깨어나면 자기 직렬의 PLC 문서를 읽고 선배들의 노하우를 즉시 흡수.
3. **교차 검증:** 감사팀 직렬(PLC_001)의 교훈이 기획자 직렬(PLC_002)에도 영향 → "감사에서 자주 FAIL되는 패턴"을 기획 단계에서 미리 방지.
4. **진화 측정:** 사이클별로 FAIL률, 수정 루프 횟수, 새 skills 생성 수를 추적하여 실제 발전을 측정.

**PLC 문서 구조 (각 직렬별):**
```
PLC_00N_[직렬명].md
├── 1차 전학공: [날짜] 교훈 N건
├── 2차 전학공: [날짜] 교훈 N건
├── ...
├── 누적 교훈 목록 (테이블)
├── 개선 제안 (완료/미완료 추적)
└── CT 월권 방지 항목 (모든 직렬 공통)
```

**핵심 원리:** skills와 mistakes가 한 에이전트 안에 갇히면 의미 없음. **같은 역할의 에이전트들 사이에서 공유되고, 다른 직렬에까지 전파될 때** 비로소 시스템 전체가 진화.

### 6.3 트리거 조건
- 3개 이상 도메인에서 신규 감사 PASS가 누적되면 PLC 전학공 트리거
- CT가 트리거하되, 내용은 각 직렬 문서에 축적

---

## 7. Ralph Loop (자동 피드백 루프)

```
[1단계] 상태 파악: master_plan + 각 도메인 context_list/note 읽기
[2단계] 명령 하달: master_plan § Feedback 업데이트 (문서로만, 직접 개입 금지)
[3단계] MM spawn: Agent 도구로 해당 도메인 MM spawn
[4단계] 감사 확인: 감사팀 결과 확인
[5단계] 컨텍스트 클리어: 세션 종료 → 깨끗한 상태로 다음 루프
```

---

## 8. 다른 프로젝트에서 이 파일을 참조하는 방법

1. 이 파일을 자기 프로젝트의 `docs/ai/` 하위에 복사하거나 심볼릭 링크
2. 자기 프로젝트의 CLAUDE.md에서 `docs/ai/HARNESS_OVER_HARNESS_REFERENCE.md` 참조 명시
3. Session Awakening에서 이 파일의 존재를 확인하고, 자기 구조가 이 규격에 부합하는지 자가 점검
4. 부합하지 않는 항목이 있으면 즉시 시정하고 mistakes.md에 기록

---

## 9. 하네스 서큘레이션 테스트 (공회전)

> 실제 업무를 수행하기 전에 하네스 오버 하네스 구조가 **정말로 작동하는지** 검증하는 테스트입니다.
> 새 프로젝트 세팅 후, 또는 구조 대폭 개편 후 반드시 실행하십시오.

### 9.1 목적
- 각 에이전트가 skills/mistakes를 기반으로 전문 업무를 파악하는지 확인
- MM이 Worker의 skills 이해도를 실제로 검수하는지 확인
- 감사팀이 부적합 산출물을 실제로 반려하는지 확인
- CT가 직접 구현하지 않고 위임만 하는지 확인
- PLC를 통한 직렬 간 교훈 공유가 작동하는지 확인

### 9.2 공회전 절차

```
[Round 1] CT가 테스트 태스크를 master_plan.md에 하달
  ↓
[Round 2] MM spawn → MM이 자기 도메인 skills/mistakes 읽기 → Worker spawn
  ↓
[Round 3] Worker가 skills/mistakes 읽고 작업 → 결과 + skills/mistakes 갱신
  ↓
[Round 4] MM이 Worker 결과 검수 (skills 이해도, mistakes 반영, NLM 검수 여부)
  → 불합격이면 반려 + 사유 기록 → Worker 재spawn
  ↓
[Round 5] 감사팀이 산출물 감사 (품질 + 제작경로 + 진화기록)
  → FAIL이면 반려 + 사유 기록 → Round 2로
  ↓
[Round 6] CT가 감사 결과 확인 → 전 라운드 통과 시 "공회전 PASS"
  → 1곳이라도 실패면 해당 계층 수정 후 처음부터 재실행
```

### 9.3 공회전 합격 기준

| 계층 | 합격 기준 |
|------|-----------|
| **CT** | 직접 구현 0건, 위임만으로 태스크 완료 |
| **MM** | Worker spawn 시 skills/mistakes 읽기 지시 포함, Worker 결과에서 skills 이해도 검수 실제 수행 |
| **Worker** | 로컬 skills/mistakes 읽은 흔적, 작업 후 갱신, python3 미사용 |
| **감사팀** | 부적합 산출물 실제 반려, 제작경로 추적, 증거 기반 판정 |
| **NLM 검수** | 산출물이 실제로 NLM에 투입되어 응답을 받음 |
| **PLC** | 공회전에서 발견된 교훈이 직렬별 PLC 문서에 기록됨 |

### 9.4 공회전 실패 시
- 실패한 계층의 CLAUDE.md/context_plan.md/skills 보강
- 해당 계층 mistakes.md에 실패 사유 기록
- **완벽할 때까지 계속 반려** — 공회전 통과 전 실제 업무 수행 금지

### 9.6 공회전 실행 기록

#### 2026-03-19 AI Office 공회전 (최초)
- **1차 (기숙사):** MM→Worker(겸임) skills 4개 읽음, NLM 실투입(2,245자), mistakes 1건 추가, 감사팀 5항목 PASS
- **2차 (화학):** MM→Worker(겸임) skills 읽음, NLM 실투입, Angular textarea 입력법 발견→mistakes 추가, 4주차 24문항 검수 PASS
- **재검수:** Agent 중첩 불가 = Claude Code SDK 인프라 제약. MM 직접 수행 시 Worker 의무 4항목 이행 조건으로 허용.
- **최종:** PASS 확정. 실제 업무 수행 가능 상태.

### 9.7 하이브리드 위임 구조 (방법 2+4)

Agent 내부 중첩이 제한적인 환경에서, **Bash + claude CLI**를 활용한 하이브리드 위임이 가장 효과적입니다.

**구조:**
```
CT (메인 세션)
├── Agent spawn → MM (계획/검수, Agent 도구 내)
├── Bash → claude --print --model claude-opus-4-6 → Worker-A (완전 독립 프로세스)
│   └── fresh context + 전체 도구(Agent/MCP/Chrome) + skills/mistakes 파일 I/O
├── Bash → claude --print → Worker-B (병렬 실행 가능)
└── Agent spawn → 감사팀 (결과 검증)
```

**장점:**
- 완전히 독립된 opus 능지의 fresh context Worker
- Agent 중첩 가능 (CLI Worker 내부에서도 Agent spawn 가능)
- Chrome MCP, NLM 등 전체 도구 접근 가능
- 병렬 실행 가능 (run_in_background)
- skills/mistakes는 파일로 주고받아 진화 유지

**Worker spawn 명령 패턴:**
```bash
claude --print --model claude-opus-4-6 --max-turns 50 -p "
당신은 [도메인] Worker입니다.
## Awakening
1. persona/[도메인]/mistakes.md 읽기
2. persona/[도메인]/skills/ 읽기
3. docs/ai/skills/python_execution.md 읽기 (python3 금지)
## 태스크
[구체적 태스크]
## 완료 조건
1. 산출물 경로에 파일 생성
2. persona/[도메인]/mistakes.md 갱신
3. persona/[도메인]/skills/ 갱신 (새 패턴 발견 시)
"
```

**주의:**
- `--dangerously-skip-permissions` 플래그는 사용자 명시적 허가 후에만 사용
- Worker 프롬프트에 반드시 skills/mistakes 읽기 + 갱신 의무 포함
- NLM 검수가 필요한 태스크는 Worker 프롬프트에 Chrome Tab ID 포함

### 9.5 다른 프로젝트에서의 적용
이 공회전 절차는 chemgrid 등 다른 하네스 프로젝트에서도 동일하게 적용 가능합니다.
자기 프로젝트의 도메인/감사팀/PLC에 맞게 테스트 태스크를 설계하여 실행하십시오.

---

## 10. 위반 사례 아카이브 (교훈)

### [2026-03-19] CT 직접 구현 8사이클 연속 위반
- **상황:** CT가 Ralph Loop 사이클 1~8에서 직접 python 코드 작성, HWP COM 호출, HWPX XML 편집
- **결과:** 관리/소통/진행파악/개선방향 전부 정지. 에이전트 진화 시스템 작동 안 함.
- **교훈:** CT 직접 구현은 하네스 오버 하네스의 존재 이유를 부정하는 행위

### [2026-03-19] skills/mistakes 미축적으로 깡통 에이전트 양산
- **상황:** 10개 도메인 중 로컬 mistakes.md가 0개, skills가 부실
- **결과:** 에이전트가 매번 같은 실수 반복 (python3 MS Store 30번+)
- **교훈:** skills/mistakes 갱신 없는 작업 완료 = 미완료. 진화가 안 되면 깡통.

### [2026-03-19] NLM 검수 미실행으로 품질 불량 산출물 보고
- **상황:** "NLM 검수 완료"라고 보고했지만 실제 산출물 품질이 엉망
- **교훈:** NLM 출력창에 실제로 투입하여 검수받는 프로세스가 자동화되어야 함
