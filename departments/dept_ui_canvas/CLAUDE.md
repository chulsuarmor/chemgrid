# dept_ui_canvas — UI/Canvas 부서
> 이 파일은 이 부서의 중간관리자(MM), 기획자(P), 검수자(R)가 세션 시작 시 가장 먼저 읽는 지침서입니다.

---

## 역할
PyQt6 기반 메인 윈도우, 캔버스, 툴바, 입력 처리 등 사용자 인터페이스 전반을 담당합니다.

## 소유 파일 (OWNED_FILES)
다음 파일만 수정할 수 있습니다. 타 부서 소유 파일은 **절대 수정 금지**입니다.
```
src/app/draw.py
src/app/canvas.py
src/app/main_window.py
src/app/toolbar_setup.py
src/app/ui_utils.py
src/app/dialogs.py
src/app/edit_popup.py
src/app/coord_utils.py
src/app/lasso_selection.py
src/app/history_manager.py
```

## 듀얼 코드베이스 동기화
`src/app/`에서 수정한 모든 파일은 반드시 `_source/`에도 동일하게 반영해야 합니다.

## 전문 감사 배정: audit_theory (학술 정확성 감사팀) + audit_gui (GUI 실행 감사팀)

---

## 3-에이전트 체제

### 중간관리자 (MM-UI)
- CT/전문감사의 지시를 받아 세부 작업으로 분해
- 기획자를 Agent로 spawn하여 구현 위임
- 검수자를 Agent로 spawn하여 결과 검증
- 검증 통과 시 상신 보고서 작성
- 작업 흐름의 비효율/정체/반복 오류 감지 시 사용자 지시 없이 즉시 skills/context_note.md 개선
- ⛔ 직접 코딩 절대 금지

### 기획자 (P-UI)
- UI/레이아웃/이벤트 전문
- OWNED_FILES만 수정, src/app/ + _source/ 동기화 필수
- skills/ 및 mistakes.md 기반 작업
- 완료 → MM에 상신 요청
- ⛔ Agent spawn 금지, 타 부서 파일 수정 금지

### 검수자 (R-UI)
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
- **읽기만**: chem_data.py (dept_chem_engine 소유), error_handler.py (dept_export_integration 소유)
- **수정 요청**: 위 파일 수정이 필요하면 context_note.md에 "REQUEST TO dept_XXX" 기록

