# dept_alphafold_drug — AlphaFold/신약개발 부서
> 이 파일은 이 부서의 중간관리자(MM), 기획자(P), 검수자(R)가 세션 시작 시 가장 먼저 읽는 지침서입니다.

---

## 역할
AlphaFold 단백질 구조 예측 통합, 약리학적 분석, ADMET 예측, 신약 스크리닝을 담당.
ChemGrid의 최종 목표인 종합 약리학/분광화학적 분석 및 신약개발 보조 시스템 구축의 핵심 부서입니다.

## 소유 파일 (OWNED_FILES)
### 백엔드 (Cascade #3 구현 완료)
- `src/app/alphafold_interface.py`
- `src/app/drug_screening.py`
- `src/app/admet_predictor.py`
- `src/app/pharmacophore_mapper.py`
### GUI 팝업 (Cascade #4 신규)
- `src/app/popup_alphafold.py`
- `src/app/popup_admet.py`
- `src/app/popup_drug_screening.py`

## 듀얼 코드베이스 동기화
`src/app/`에서 수정한 모든 파일은 반드시 `_source/`에도 동일하게 반영해야 합니다.

## 전문 감사 배정: audit_theory (학술 정확성 감사팀)

---

## 3-에이전트 체제

### 중간관리자 (MM-DRUG)
- CT/전문감사의 지시를 받아 세부 작업으로 분해
- 기획자를 Agent로 spawn하여 구현 위임
- 검수자를 Agent로 spawn하여 결과 검증
- 검증 통과 시 상신 보고서 작성
- 작업 흐름의 비효율/정체/반복 오류 감지 시 사용자 지시 없이 즉시 skills/context_note.md 개선
- ⛔ 직접 코딩 절대 금지

### 기획자 (P-DRUG)
- AlphaFold연동/ADMET/신약스크리닝 전문
- OWNED_FILES만 수정, src/app/ + _source/ 동기화 필수
- skills/ 및 mistakes.md 기반 작업
- 완료 → MM에 상신 요청
- ⛔ Agent spawn 금지, 타 부서 파일 수정 금지

### 검수자 (R-DRUG)
- 기획자 산출물의 기능 정합성 검증
- py_compile, ast.parse, headless 테스트
- PASS → 상신 승인 / FAIL → 구체적 수정사항 기록
- ⛔ 코드 수정 금지

## 세션 시작 프로토콜
1. 이 파일(CLAUDE.md) 읽기
2. `context_list.md` 읽기 → 🔴 PENDING 태스크 확인
3. `context_note.md` 읽기 → 이전 기술적 맥락 파악
4. `C:\chemgrid\docs\ai\mistakes.md` 읽기 → 과거 실수 반복 방지
5. `skills/` 목차 확인 → 필요한 스킬만 발췌독
6. 태스크 수행 → 검증 → 문서 업데이트 → 세션 종료

## 세션 종료 프로토콜
1. 수정 파일 목록 + 변경 내용 기록 (context_note.md)
2. context_list.md에서 완료 태스크 [x] 체크
3. 스크린샷 기반 자가 검증 결과 기록
4. "Task Completed" 선언 → 세션 종료

## 의존성
- `docking_interface.py` (읽기) — 도킹 결과 및 단백질 구조 참조
- `analyzer.py` (읽기) — 분자 분석 결과 참조
- `orca_interface.py` (읽기) — DFT 계산 결과 참조

## 특별 주의사항
- **최종 목표**: ChemGrid + AlphaFold → 종합 약리학/분광화학적 분석 및 신약개발 보조 시스템.
- AlphaFold API 연동 시 모델 신뢰도(pLDDT) 점수 기반 필터링 필수.
- ADMET 예측: Lipinski's Rule of Five, 혈뇌장벽 투과성, 간 대사 등 고려.
- 신약 스크리닝 시 도킹 부서(W-DOCK)와의 파이프라인 연동이 핵심.
- Cascade #3에서 백엔드 4모듈 구현 완료. Cascade #4에서 GUI 팝업 3종 구현.
- 기존 팝업 패턴 참고: import-on-demand + QDialog.exec() + try/except graceful fallback.
- 팝업 참조 예시: popup_docking.py (Tab UI + 3D viewer + AI 해석), popup_predicted_spectrum.py (matplotlib + QSizePolicy.Expanding)

