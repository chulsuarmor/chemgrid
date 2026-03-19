# 👑 ChemGrid Master Project Plan v2.0
## 최종 업데이트: 2026-03-18 | 작성: Control Tower AI (Opus 4.6)
## 아키텍처: Harness-over-Harness v2 — 트리거 기반 다계층 자율 에이전트 시스템

---

## 1. 프로젝트 최종 비전

ChemGrid: **"처음 보는 분자를 그리더라도 완전하게 분석하는 종합 화학 플랫폼"**

```
[사용자: 분자명/SMILES 입력]
    ↓
2D 레이어 (루이스 / 그리기 / 이론적 구조)
    ├→ ESP 전자구름 분포 (Gasteiger 60% + Custom 40%)
    ├→ Lewis 론쌍, 형식전하
    ├→ RS 입체성, wedge-dash
    ├→ 반응 예측 + 메커니즘 (곡선 화살표)
    ├→ 역합성 경로 + Gemini 합성 실험 프로토콜
    ├→ 스펙트럼 5종 (IR/Raman/¹H-NMR/¹³C-NMR/UV-Vis)
    ├→ 3D 구조 + 오비탈 (gradient isosurface HOMO/LUMO)
    ├→ 진동 모드 (경험적 + ORCA GFN2-xTB)
    └→ AutoDock Vina 도킹 + AI 해석 세션
           ↓
    [타겟 단백질 FASTA 시퀀스]
           ↓
    AlphaFold 구조 예측 (ColabFold)
           ↓
    도킹 시뮬레이션 + ADMET + 약물체 매핑
           ↓
    신약 후보 순위화 + 리드 최적화
           ↓
    종합 보고서 PDF (6페이지/후보)
```

### 핵심 품질 기준
- **박사급 연구자가 검수하더라도 완벽하다고 느낄 수준**
- 전문 감사팀이 Misser 유기화학, PubChem, 최신 DFT 논문과 교차검증
- 최종 감사팀이 실제 GUI에서 가상 마우스로 기능 통합 검증

---

## 2. 에이전트 계층 구조 (Harness-over-Harness v2)

```
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 0: CONTROL TOWER (CT) — 최종 관리자                               │
│ 역할: 사용자 소통, 전략 하달, 전체 진척도 관리                            │
│ ⛔ 직접 코딩/파일수정 절대 금지. 문서(md)만 읽기/쓰기                     │
│ ✅ Agent cascade로 하위 관리자 awake                                    │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 1-A: 최종 감사팀 (Final Audit)                                    │
│ 역할: 사용자 환경 피드백 — 가상 마우스/키보드로 ChemGrid GUI 통합 검증     │
│ 위치: departments/audit_final/                                          │
│ 트리거: 전문 감사팀 PASS → 최종 감사팀 awake                             │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 1-B: 전문 감사팀 (Professional Audit) × 3팀                       │
│ 역할: 학술/연구 기준 교차검증 — 교과서/PubChem/논문과 비교                │
│ 위치: departments/audit_professional_{domain}/                          │
│ 트리거: 부서 MM 상신 → 전문 감사팀 awake                                │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 2: 부서 중간관리자 (MM) × 12부서                                  │
│ 역할: 상부 지시 → 세부 작업 분해 → 기획자/검수자 spawn                   │
│ ⛔ 직접 코딩 금지. Agent로 기획자를 spawn하여 위임                       │
│ 트리거: CT 명령 하달 (context_list.md 🔴 PENDING)                       │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 3-A: 기획자 (Planner/Coder) × 부서당 1~3명                        │
│ 역할: 실제 코드 구현. OWNED_FILES만 수정 가능                            │
│ 트리거: MM 작업 지시                                                    │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 3-B: 검수자 (Reviewer) × 부서당 1명                               │
│ 역할: 부서 내 기능 검증. 기획자 산출물 PASS/FAIL 판정                    │
│ 트리거: 기획자 작업 완료 상신                                            │
└────────────────────────────────────────────────────────────────────────┘
```

### 작업 흐름 (Trigger-Based Pipeline)
```
① CT → master_plan.md 명령 기록 → 부서 context_list.md 🔴 PENDING
② MM awake → 세부 작업 분해 → 기획자 spawn
③ 기획자 구현 완료 → MM에 상신 요청
④ MM → 검수자 spawn (부서 내 기능 테스트)
⑤ 검수자 PASS → MM이 전문 감사팀에 상신
   검수자 FAIL → 구체적 피드백 → 기획자 재작업 (최대 3회)
⑥ 전문 감사팀 PASS → 최종 감사팀에 상신
   전문 감사팀 FAIL → 구체적 피드백 → 해당 부서 MM에 반려
⑦ 최종 감사팀 PASS → CT에 보고
   최종 감사팀 FAIL → 구체적 피드백 → 해당 부서 MM에 반려
⑧ CT가 사용자에게 확인 요청
```

---

## 3. 감사 체계 (2-Tier Audit System)

### 3-A. 전문 감사팀 (Professional Audit) — 3팀

| 팀 | 폴더 | 감독 부서 | 검증 기준 |
|----|------|-----------|----------|
| 전문감사-구조화학 | audit_professional_structural | ui_canvas, chem_engine, rendering | Misser 유기화학 교과서, IUPAC 명명법, RS 입체화학, 공명 구조 이론값 |
| 전문감사-분광물성 | audit_professional_spectral | spectroscopy, 3d_viewer, dft_orca, reaction_synthesis | 분광학 교과서, NIST WebBook, 최신 DFT/오비탈 논문, 진동모드 이론값 |
| 전문감사-약리도킹 | audit_professional_pharma | docking, alphafold_drug, export_integration | AutoDock Vina 문헌값, ADMET 기준, DrugBank 참조, PDB 구조 데이터 |

**전문 감사팀의 핵심 원칙:**
- 웹 검색 권한: 있음 (PubChem, NIST, 논문 검색)
- 코드 수정 권한: 없음 (검증만 수행)
- 판정 기준: "박사급 연구자가 검수하더라도 완벽"하지 않으면 FAIL
- FAIL 시: 어떤 데이터/이론과 불일치하는지 구체적 근거 + 참조 문헌/URL 명시

### 3-B. 최종 감사팀 (Final Audit) — 1팀

| 팀 | 폴더 | 역할 |
|----|------|------|
| 최종감사 | audit_final | 가상 마우스/키보드로 ChemGrid 앱을 실제 실행하여 통합 기능 검증 |

**최종 감사팀의 핵심 원칙:**
- GUI 실행: `C:\ProgramData\anaconda3\envs\chemgrid\python.exe c:\chemgrid\src\app\draw.py`
- 검증 방법: 가상 마우스 클릭, 키보드 입력 시뮬레이션, 스크린샷 캡처
- 판정 기준: 하위 부서의 보고 내용과 실제 GUI 동작이 일치해야 PASS
- FAIL 시: 스크린샷 + 불일치 내용 + 재현 절차를 기록하여 반려

---

## 4. 12개 실무 부서

### 부서별 에이전트 구성 (최소 3인 체제)

| # | 부서 | 중간관리자(MM) | 기획자(P) | 검수자(R) | 소유 파일 | 전문감사 배정 |
|---|------|--------------|----------|----------|----------|-------------|
| 1 | dept_ui_canvas | MM-UI | P-UI (×1) | R-UI | 10개 | 구조화학 |
| 2 | dept_chem_engine | MM-CHEM | P-CHEM (×1) | R-CHEM | 7개 | 구조화학 |
| 3 | dept_rendering | MM-RENDER | P-RENDER (×1) | R-RENDER | 3개 | 구조화학 |
| 4 | dept_3d_viewer | MM-3D | P-3D (×1) | R-3D | 4개 | 분광물성 |
| 5 | dept_spectroscopy | MM-SPEC | P-SPEC (×2) | R-SPEC | 9개 | 분광물성 |
| 6 | dept_reaction_synthesis | MM-RXTN | P-RXTN (×2) | R-RXTN | 9개 | 분광물성 |
| 7 | dept_dft_orca | MM-DFT | P-DFT (×1) | R-DFT | 2개 | 분광물성 |
| 8 | dept_docking | MM-DOCK | P-DOCK (×1) | R-DOCK | 5개 | 약리도킹 |
| 9 | dept_export_integration | MM-EXPORT | P-EXPORT (×1) | R-EXPORT | 6개 | 약리도킹 |
| 10 | dept_visual_feedback | MM-VF | P-VF (×1) | R-VF | 1개 | 최종감사 |
| 11 | dept_testing_build | MM-TEST | P-TEST (×1) | R-TEST | 2+개 | 최종감사 |
| 12 | dept_alphafold_drug | MM-DRUG | P-DRUG (×2) | R-DRUG | 4개(계획) | 약리도킹 |

### 부서 내 3-에이전트 역할 정의

**중간관리자 (MM):**
- CT/전문감사의 지시를 받아 세부 작업으로 분해
- 기획자를 Agent로 spawn하여 구현 위임
- 검수자를 Agent로 spawn하여 결과 검증
- 검증 통과 시 상신 보고서 작성 → 전문 감사팀에 전달
- ⛔ 직접 코딩 절대 금지

**기획자 (Planner/Coder, P-XXX):**
- skills/ 및 mistakes.md를 기반으로 효율적 구현
- OWNED_FILES만 수정 가능, 타 부서 파일 절대 금지
- src/app/ 수정 시 _source/ 반드시 동기화
- 작업 완료 → MM에 상신 요청 (수정 파일 목록 + 테스트 결과)
- ⛔ Agent spawn 금지 (Worker는 Worker를 깨울 수 없음)

**검수자 (Reviewer, R-XXX):**
- 기획자 산출물의 기능 정합성을 객관적으로 검증
- 검증 방법: headless 테스트 실행, py_compile, ast.parse, 로직 리뷰
- PASS: 상신 승인 → MM에 보고
- FAIL: 구체적 수정사항 작성 → MM을 통해 기획자에 피드백
- ⛔ 코드 수정 금지 (검증만 수행)

---

## 5. CT 절대 행동 규칙

1. **CT는 직접 코드를 작성하지 않는다.** 모든 구현은 Agent cascade로 위임.
2. **CT는 .py 파일을 절대 수정하지 않는다.** .md 문서만 읽기/쓰기.
3. **CT가 부서를 신설할 때만** 폴더 생성 + 초기 CLAUDE.md/context 파일 배치 가능.
4. **CT는 사용자에게 확인 요청 시** 감사 체계를 모두 거친 건만 보고한다.
5. **각 에이전트는 자신의 담당 업무 이외의 그 어떤 내용도 임의로 수행할 수 없다.**

---

## 6. 트리거 기반 오케스트레이션 (Ralph Loop v4)

### 기존 방식 (v3): 10분 타이머 기반 → 토큰 낭비
### 신규 방식 (v4): 작업 완료 트리거 기반

**CT 작동 방식:**
- CT가 명령 하달 → 부서 MM awake (background)
- MM 작업 완료 → CT에 결과 반환 (trigger)
- CT가 결과 검토 → 전문 감사팀 awake (필요 시)
- 감사 완료 → CT에 결과 반환 (trigger)
- 모든 체인 완료 → CT가 사용자에게 보고

**Ralph Loop v4 핵심:**
- 타이머 순찰이 아닌, **상신 trigger**로 동작
- 다만 장기간 응답 없는 부서 감지를 위해 **30분 watchdog** 유지
- 여러 부서 작업을 `run_in_background: true`로 병렬 처리
- 각 에이전트는 작업 완료 시 즉시 세션 종료 (컨텍스트 클리어)

---

## 7. 기술 스택

| 항목 | 사양 |
|------|------|
| Python | 3.12, Anaconda `chemgrid` 환경 |
| UI | PyQt6 6.10.2 |
| 화학 | RDKit 2025.09.5 |
| DFT | ORCA 6.1.1 (설치됨), xtb (GFN2-xTB, 예정) |
| API | PubChem PUG REST, Gemini 1.5 Flash, Google Knowledge Graph |
| 도킹 | AutoDock Vina (Python bindings) |
| 단백질 | ColabFold (예정), biopython, pdb-tools |
| 실행 | `C:\ProgramData\anaconda3\envs\chemgrid\python.exe c:\chemgrid\src\app\draw.py` |
| 창 제목 | "ChemGrid V5" |

---

## 8. 장기 로드맵

### Phase 5: 핵심 기능 완성 (현재)
- ESP 전자구름 이론값 정합성 (공명구조, Gasteiger 블렌딩)
- Lewis 론쌍 정확성 (H₂O, NH₃, 아세트산)
- 이론적 구조 입체성 (RS, wedge-dash)
- 진동 모드 (bond stretching + ORCA 연동)
- 반응 결과 2분자 인식 + 곡선 화살표
- 합성 방법 → Gemini 실험 프로토콜
- 오비탈 시각화 (gradient isosurface HOMO/LUMO)
- AutoDock Vina 완성 (실제 도킹 + AI 해석)

### Phase 6: AlphaFold 연계
- alphafold_interface.py (ColabFold API)
- admet_predictor.py (Lipinski, BBB, 대사안정성)
- drug_screening.py (pLDDT → 필터링 + 순위화)
- pharmacophore_mapper.py (약물체 3D 매핑)
- AlphaFold PDB → Vina 도킹 → 결합 에너지 파이프라인

### Phase 7: 신약 개발 보조 시스템
- 리드 최적화 루프 (구조변형 → Vina → ADMET 반복)
- 레트로합성 → 합성 경로 → 실험 조건 → 비용 추정
- 예측 IR/NMR vs 실측값 비교 → 구조 확인
- 후보 분자별 종합 보고서 PDF (6페이지)
- AlphaFold 배치 모드 (교차 도킹 매트릭스)

---

## 9. 절대 하지 말 것 (mistakes.md 축약)

- ❌ RDKit 기반 공명 구조 density 재계산 시도
- ❌ `canvas.get_smiles()`를 유일한 SMILES 소스로 사용
- ❌ `at_sym == "C"` 비교 (반드시 `at_sym in ('', 'C')`)
- ❌ `int(round(1.5))` = 2 (banker's rounding) → 방향족 1.5 bond order는 float 보존
- ❌ pygetwindow "chemgrid" 키워드만 사용 (VS Code 오인)
- ❌ 코드 수정만으로 "완료" 선언 → 반드시 실제 앱 시각 검증
- ❌ ORCA 6.1.1에서 orca_plot 사용 → `%plots` 블록 사용
- ❌ reveal_radius 초기화 없이 Lewis/Theory 모드 전환

---

## 10. 🔴 Command Dispatch Table

### 현재 하달 명령 (2026-03-18)

| 부서 | 태스크 | 우선순위 | 상태 | 감사 배정 |
|------|--------|---------|------|----------|
| dept_ui_canvas | P0: grid snap 정밀도 + pan_offset 보정 | P0 | 🔴 PENDING | 구조화학 |
| dept_ui_canvas | P0: analysis_results 갱신 보장 | P0 | 🔴 PENDING | 구조화학 |
| dept_rendering | Full orbital gradient isosurface | P1 | 🔴 PENDING | 분광물성 |
| dept_rendering | Reaction curved arrows 완성 | P1 | 🔴 PENDING | 분광물성 |
| dept_3d_viewer | Bond stretching 진동 모드 | P1 | 🔴 PENDING | 분광물성 |
| dept_reaction_synthesis | 역합성 엔진 + 합성방법 탭 | P1 | 🔴 PENDING | 분광물성 |
| dept_spectroscopy | Drawing layer ESP 활성화 | P2 | ⬜ READY | 분광물성 |
| dept_docking | Vina 도킹 AI해석 세션 추가 | P2 | ⬜ READY | 약리도킹 |
| dept_alphafold_drug | Phase 6 모듈 4개 신규 개발 | P3 | ⬜ PLANNED | 약리도킹 |

### 이전 완료 사항 (레거시)
- ✅ W-UI: grid snap 폴백 + analysis_results silent exception (py_compile OK)
- ✅ W-3D: O(n²)→spatial hash + quadric캐싱 + size guard (py_compile OK)
- ✅ 85/85 GUI 자동화 테스트 ALL PASS (세션 10b)
- ✅ 도킹 스코어링 v8.7 (7/8 약물-타겟 쌍 ±2.0 kcal/mol)
- ✅ 반응경로 교과서 스타일 (ReactionPathwayWidget v3.0)

---

## 11. 🔄 Manager's Feedback & Next Action

### 현재 사이클 상태: 아키텍처 v2 구축 중
- [x] master_plan.md v2 작성
- [ ] ARCHITECTURE.md v2 업데이트
- [ ] 전문 감사팀 3팀 폴더 + CLAUDE.md 생성
- [ ] 최종 감사팀 폴더 + CLAUDE.md 생성
- [ ] 각 부서 CLAUDE.md에 3-에이전트 체제 반영
- [ ] Ralph Loop v4 스크립트 업데이트

### 다음 작업 방향
1. 아키텍처 구축 완료 후, P0 버그 2건을 dept_ui_canvas에 dispatch
2. P1 기능 4건을 해당 부서에 병렬 dispatch
3. 전문 감사팀이 Phase 5 기능들의 이론적 정합성 검증
4. 최종 감사팀이 GUI 통합 테스트
5. 모든 감사 통과 후 사용자에게 보고

---

## Session End Checklist
1. master_plan.md 업데이트 완료 ✅
2. 각 부서 context 파일 최신 상태 확인
3. mistakes.md 갱신
4. exit 선언
