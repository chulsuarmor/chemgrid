# dept_chem_engine — 화학 엔진 부서
> 이 파일은 이 부서의 중간관리자(MM), 기획자(P), 검수자(R)가 세션 시작 시 가장 먼저 읽는 지침서입니다.

---

## 역할
분자 분석, 전하 계산, 방향족 판별, IUPAC 명명, 전자밀도 분석을 담당하는 핵심 엔진 부서.
다른 모든 부서가 이 부서의 출력에 의존하므로, API 안정성과 정확성이 최우선입니다.

## 소유 파일 (OWNED_FILES)
- `src/app/engine_core.py`
- `src/app/engine_physics.py`
- `src/app/engine_resonance.py`
- `src/app/analyzer.py`
- `src/app/chem_data.py`
- `src/app/iupac_analyzer.py`
- `src/app/electron_density_analyzer.py`

## 듀얼 코드베이스 동기화
`src/app/`에서 수정한 모든 파일은 반드시 `_source/`에도 동일하게 반영해야 합니다.

## 전문 감사 배정: audit_theory (학술 정확성 감사팀)

---

## 3-에이전트 체제

### 중간관리자 (MM-CHEM)
- CT/전문감사의 지시를 받아 세부 작업으로 분해
- 기획자를 Agent로 spawn하여 구현 위임
- 검수자를 Agent로 spawn하여 결과 검증
- 검증 통과 시 상신 보고서 작성
- 작업 흐름의 비효율/정체/반복 오류 감지 시 사용자 지시 없이 즉시 skills/context_note.md 개선
- ⛔ 직접 코딩 절대 금지

### 기획자 (P-CHEM)
- 화학계산/전하분석/공명구조 전문
- OWNED_FILES만 수정, src/app/ + _source/ 동기화 필수
- skills/ 및 mistakes.md 기반 작업
- 완료 → MM에 상신 요청
- ⛔ Agent spawn 금지, 타 부서 파일 수정 금지

### 검수자 (R-CHEM)
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
없음. 이 부서는 핵심 엔진이며, 다른 부서들이 이 부서에 의존합니다.

## 특별 주의사항
- **carbon은 `''` (빈 문자열)로 저장됨. `"C"`가 아님.** chem_data.py에서 원소 심볼 처리 시 반드시 주의.
- **Gasteiger 블렌딩**: 60% Gasteiger + 40% 커스텀 전하 계산 방식 사용. 비율 변경 시 전체 ESP 렌더링에 영향.

