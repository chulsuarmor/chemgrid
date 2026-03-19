# domain_ui — 사용자 인터페이스
> MM-UI + Worker + Reviewer

---

## OWNED_FILES
- `src/app/canvas.py`
- `src/app/main_window.py`
- `src/app/toolbar_setup.py`
- `src/app/draw.py`
- `src/app/dialogs.py`
- `src/app/lasso_selection.py`
- `src/app/pubchem_client.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_ui/context_list.md` → 현재 할 일 확인
3. `departments/domain_ui/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_ui/skills/` → 관련 스킬 발췌독

---

## MM-UI (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 UI 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- PyQt6 기반 UI 구현: 메뉴, 툴바, 캔버스, 다이얼로그
- 한국어 UI 라벨 필수 (메뉴, 버튼, 툴팁 모두 한국어)
- PubChem 검색 클라이언트 유지보수
- 올가미 선택(lasso) 도구 구현

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자)
- Worker의 산출물을 아래 기준으로 검수
- **실제 앱 실행 필수** — headless 테스트만으로 PASS 불가
- 검수 통과 시 MM-UI에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려

### 검수 체크리스트
1. **시각적 검증 (스크린샷 필수)**
   - [ ] 앱 실행 후 메인 윈도우 스크린샷 캡처
   - [ ] 수정된 UI 요소가 화면에 올바르게 표시되는가
   - [ ] 한국어 라벨이 깨지지 않고 정상 렌더링되는가
   - [ ] 레이아웃이 겹치거나 잘리지 않는가

2. **인터랙션 테스트**
   - [ ] 버튼/메뉴 클릭이 정상 동작하는가
   - [ ] 키보드 단축키가 올바르게 작동하는가
   - [ ] 마우스 이벤트(클릭, 드래그, 스크롤)가 정상인가

3. **사용자 편의성 평가**
   - [ ] 화학과 학생이 직관적으로 이해할 수 있는 UI인가
   - [ ] 에러 발생 시 사용자에게 이해 가능한 메시지를 표시하는가
   - [ ] 툴팁이 적절히 제공되는가

4. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] 시그널/슬롯 연결이 올바른가
   - [ ] 메모리 누수 가능성이 있는 위젯 참조가 없는가

5. **회귀 확인**
   - [ ] 기존 기능(그리기, 분석, 저장 등)이 깨지지 않았는가
   - [ ] `_last_drawn_smiles` 파이프라인이 정상 유지되는가

---

## skills 필수 항목
- **`_last_drawn_smiles` 파이프라인**: SMILES 그리기 후 `_last_drawn_smiles` 속성이 반드시 업데이트되어야 함. 이 값이 누락되면 분석 결과가 갱신되지 않는 버그 발생.
- **QWidget.grab() 스크린샷 패턴**: `widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)` 설정 후 `widget.grab()` 호출. `_reveal_radius = max_r` 설정 필수.
- **한국어 UI 라벨**: 모든 사용자 대면 텍스트는 한국어. 내부 로그/변수명은 영어.
- **PyQt6 시그널 문법**: `signal.connect(slot)` 형태 사용 (PyQt5 구문 사용 금지).

---

## 세션 종료 프로토콜 (Context Clear)
1. 자가 검증 완료 확인
2. `context_list.md`, `context_note.md` 업데이트
3. 실수 있었으면 `docs/ai/mistakes.md` 추가
4. 다음 세션 AI가 100% 맥락 파악 가능하도록 문서 완비 확인
5. "Task Completed" 선언 후 세션 종료


## 팀 내부 QA 루프 (필수)
1. Worker 작업 완료 → MM이 Reviewer(검수자) spawn
2. Reviewer: 도메인 기준(체크리스트) 대조 → PASS/FAIL
3. FAIL → 구체적 수정 지시 + Worker 재spawn (MM 선에서 해결)
4. PASS → 감사팀에 자동 상신 (CT 개입 없음)
5. 3회 FAIL 후에도 미해결 → CT 에스컬레이션

## CT에 올리지 않는 것
- 사소한 버그 수정 (팀 내부에서 해결)
- 코드 스타일/포맷 문제
- py_compile 에러 (Worker가 직접 수정)
- 단순 반복 작업

