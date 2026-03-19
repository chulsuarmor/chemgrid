# ChemGrid Harness-over-Harness v3 아키텍처
> 범용 규격: docs/ai/HARNESS_OVER_HARNESS_REFERENCE.md 준수
> 최종 갱신: 2026-03-19 / v2→v3 전면 개편

---

## 1. 계층 구조

```
사용자 (Human Supervisor)
│
├── 감사팀 (CT 직속 상위부서 — 교차 검증 필수)
│   ├── audit_theory: 학술 정확성 (NIST/Silverstein/Clayden 대조)
│   ├── audit_gui: GUI 실행 검증 (실제 클릭 + 스크린샷)
│   ├── audit_integration: 빌드/E2E (py_compile + 테스트)
│   └── 전문 감사관 (기능별 교차 검증):
│       ├── AO-EXPORT: 내보내기 전문 (PDF/PNG/XYZ 파일 생성+내용)
│       ├── AO-UX: 사용자 환경 피드백 (학생 관점 편의성)
│       ├── AO-REACTION: 반응 시뮬레이션 표현 (메커니즘/애니메이션/화살표)
│       ├── AO-LINK: 연결 통로 동작성 (버튼 클릭→팝업 열림→기능 작동)
│       ├── AO-DFT: 밀도범함수 이론 (에너지/쌍극자/기저함수 정확성)
│       ├── AO-MECHANISM: 반응 메커니즘 (화살표/중간체/전이상태)
│       ├── AO-BONDING: 결합거리/이론적구조 (±0.05Å/±5°)
│       ├── AO-STEREOCHEM: 입체화학 (R/S, E/Z, 아노머)
│       ├── AO-ANIMATION: 3D 애니메이션 (분자 충돌/전이상태 표현)
│       └── AO-COMPLIANCE: 직렬 준수 감시 (CT월권/Worker의무/감사우회/도메인침범)
│
CT (Control Tower)
│  역할: 방향성 하달, 감사 확인, 사용자 소통
│  금지: 코드 작성, 파일 수정(master_plan 외), Bash/Edit/Write
│  사용 가능: master_plan.md Edit, Agent spawn, 사용자 응답
│
├── MM-CORE → Worker (chem_engine, rendering, coord_utils, analyzer)
├── MM-UI → Worker (canvas, main_window, toolbar, draw)
├── MM-3D → Worker (popup_3d, vibration_engine, orbital)
├── MM-SPECTRUM → Worker (predict_spectra, spectrum_calculator)
├── MM-SYNTHESIS → Worker (retrosynthesis, mechanism, building_blocks)
├── MM-DRUG → Worker (docking, lead_optimizer, alphafold, admet)
├── MM-EXPORT → Worker (export_manager, mechanism_pdf, spectrum_pdf)
└── MM-TEST → Worker (test_visual_auto, test_visual_3d, build)
```

## 2. 절대 규칙

| # | 규칙 | 위반 시 |
|---|------|---------|
| 0 | CT 직접 구현 완전 금지 | 하네스 존재 이유 부정 → 시스템 붕괴 |
| 1 | MM도 직접 구현 금지 (Worker spawn만) | Worker 양성 불가 |
| 2 | skills/mistakes 갱신 없는 완료 = 미완료 | 깡통 에이전트 양산 |
| 3 | 감사팀 = CT 직속 상위 (CT 월권 감사) | 품질 보증 불가 |
| 4 | 도메인 격리 (OWNED_FILES만 수정) | 충돌 발생 |
| 5 | python3 사용 금지 (python만) | MS Store 팝업 |

## 2.5 CLAUDE.md 전문화 진화
- 각 에이전트의 CLAUDE.md는 **해당 역할에 특화**되어야 함
- CT용 규칙(Rule 10 등)은 Worker/감사관에게 불필요 → 제거
- 대신 해당 분야의 전문 지침, 체크리스트, 허용 오차로 채움
- 에이전트가 작업 중 발견한 새 패턴 → CLAUDE.md에 반영 (skills 승격)
- MM이 Worker CLAUDE.md 갱신 여부도 검수

## 3. 도메인 파일 구조

```
departments/[도메인명]/
├── CLAUDE.md
├── context_plan.md
├── context_list.md
├── context_note.md
├── mistakes.md        ← 도메인 실수 DB (필수)
├── skills/            ← 도메인 전문 스킬 (필수)
│   └── *.md
└── evidence/
```

## 4. 8개 도메인 매핑

| 도메인 | MM | OWNED_FILES |
|--------|-----|-------------|
| CORE | MM-CORE | analyzer.py, chem_data.py, engine_*.py, coord_utils.py |
| UI | MM-UI | canvas.py, main_window.py, toolbar_setup.py, draw.py |
| 3D | MM-3D | popup_3d.py, vibration_engine.py |
| SPECTRUM | MM-SPECTRUM | predict_spectra.py, spectrum_calculator.py, popup_spectrum.py, popup_predicted_spectrum.py |
| SYNTHESIS | MM-SYNTHESIS | retrosynthesis_engine.py, mechanism_engine.py, building_blocks.py, popup_synthesis.py, reaction_mechanisms.py, arrow_generator.py, mechanism_pdf_exporter.py |
| DRUG | MM-DRUG | docking_*.py, lead_optimizer.py, popup_lead_optimizer.py, popup_docking.py, alphafold_*.py, popup_alphafold.py, admet_*.py, popup_admet.py, drug_screening.py, popup_drug_screening.py |
| EXPORT | MM-EXPORT | export_manager*.py, spectrum_pdf_exporter.py |
| TEST | MM-TEST | tests/*.py, tools/build_*.bat |

## 5. 팀 내부 QA 루프 + 감사 자동 경유

### 5.1 MM 내부 QA 루프 (CT 개입 없이 팀 선에서 해결)
```
[1] MM: Worker spawn → 작업 지시
[2] Worker: skills 읽기 → 작업 → skills/mistakes 갱신
[3] MM: Reviewer(검수자) spawn → Worker 산출물 검수
[4] Reviewer: 도메인 기준으로 PASS/FAIL 판정
     → FAIL: 구체적 수정 지시 + Worker 재spawn (MM 선에서 반복)
     → PASS: 감사팀에 자동 상신
[5] 3회 재시도 후에도 FAIL → CT에 에스컬레이션
```

### 5.2 감사팀 자동 경유 (CT 수동 트리거 아님)
- MM이 "내부 QA PASS" 선언 → **자동으로** 감사팀에 상신
- 감사팀 PASS → CT에 최종 보고
- 감사팀 FAIL → MM에 반려 (CT 거치지 않음)
- CT에 올라오는 것: 감사 PASS된 최종 결과물만

### 5.3 에스컬레이션 기준 (CT에 올리는 것)
- (a) 대규모 방향성 변경 (새 기능, 아키텍처 변경)
- (b) 사용자 확인 필요 사항
- (c) 3회 재시도 + 감사 반려 후에도 해결 불가
- (d) 타 도메인 협조 필요

### 5.4 Ralph Loop v5
```
[1] CT: master_plan + context_list 읽기
[2] CT: 미완료 → master_plan에 태스크 하달
[3] CT: Agent spawn(MM)
[4] MM 내부: Worker → Reviewer → (FAIL→Worker 재시도) → PASS
[5] MM → 감사팀 자동 상신
[6] 감사팀 PASS → CT 보고
[7] CT: 확인 → 다음 루프
```

## 6. 하이브리드 위임 (Hybrid Delegation)
Agent 중첩 불가 문제 해결:
- **방법 1:** CT→Agent spawn(MM) → MM이 Worker 겸임 (Worker 의무 4항목 이행)
- **방법 2:** CT→`claude --print --model claude-opus-4-6`로 Worker를 CLI 독립 프로세스 실행
  - fresh context + 전체 도구 + Agent 중첩 가능
  - Worker에게 도메인 CLAUDE.md + skills/ + mistakes.md 경로를 프롬프트에 포함
- **방법 3:** CT→Agent spawn(MM) + CT→Agent spawn(Worker) 병렬 (2계층)

## 7. 공회전 (서큘레이션 테스트)
구조 개편 후 반드시 실행. 상세: docs/ai/HARNESS_OVER_HARNESS_REFERENCE.md §9

## 8. PLC (전학공)

| 직렬 | PLC 문서 |
|------|---------|
| 감사팀 | PLC_001_auditors.md |
| 기획자(Worker) | PLC_002_workers.md |
| 중간관리자(MM) | PLC_003_managers.md |
