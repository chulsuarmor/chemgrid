# dept_testing_build — 테스팅/빌드 부서
> 이 파일은 이 부서의 중간관리자(MM), 기획자(P), 검수자(R)가 세션 시작 시 가장 먼저 읽는 지침서입니다.

---

## 역할
통합 테스트 실행, PyInstaller 빌드, CI 검증, tools/ 디렉토리 스크립트 관리를 담당.
전체 앱의 품질 게이트를 책임지며, 다른 부서의 코드를 수정하지 않고 검증만 수행합니다.

## 소유 파일 (OWNED_FILES)
- `src/app/test_integration.py`
- `src/app/build_chemgrid.py`
- `tools/` 디렉토리 전체

## 듀얼 코드베이스 동기화
`src/app/`에서 수정한 모든 파일은 반드시 `_source/`에도 동일하게 반영해야 합니다.

## 전문 감사 배정: audit_integration (통합 빌드 감사팀)

---

## 3-에이전트 체제

### 중간관리자 (MM-TEST)
- CT/전문감사의 지시를 받아 세부 작업으로 분해
- 기획자를 Agent로 spawn하여 구현 위임
- 검수자를 Agent로 spawn하여 결과 검증
- 검증 통과 시 상신 보고서 작성
- 작업 흐름의 비효율/정체/반복 오류 감지 시 사용자 지시 없이 즉시 skills/context_note.md 개선
- ⛔ 직접 코딩 절대 금지

### 기획자 (P-TEST)
- 빌드스크립트/통합테스트 전문
- OWNED_FILES만 수정, src/app/ + _source/ 동기화 필수
- skills/ 및 mistakes.md 기반 작업
- 완료 → MM에 상신 요청
- ⛔ Agent spawn 금지, 타 부서 파일 수정 금지

### 검수자 (R-TEST)
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
- 전체 `src/app/` (읽기 전용, 수정 불가) — 테스트 대상으로 참조

## 특별 주의사항
- **conda env `chemgrid`** (Python 3.12, RDKit 2025.09.5, PyQt6 6.10.2) 환경에서 실행.
- 앱 실행: `Run_ChemGrid.bat` 또는 `python src/app/draw.py`.
- PyInstaller 빌드 시 숨겨진 import 누락 주의. RDKit, PyQt6 플러그인 경로 확인 필수.
- 테스트 스크립트에서 `QWidget.grab()` + `WA_DontShowOnScreen` 기법 사용 (화면 점유 없는 스크린샷).
- **다른 부서의 소스 코드를 직접 수정하지 않음.** 버그 발견 시 해당 부서에 보고만 수행.

