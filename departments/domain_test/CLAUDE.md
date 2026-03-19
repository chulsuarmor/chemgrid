# domain_test — 테스트/빌드
> MM-TEST + Worker + Reviewer

---

## OWNED_FILES
- `src/app/tests/*.py`
- `tools/build_chemdraw.bat`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_test/context_list.md` → 현재 할 일 확인
3. `departments/domain_test/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_test/skills/` → 관련 스킬 발췌독

---

## MM-TEST (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 테스트/빌드 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- 자동화 테스트 작성 및 실행
- PyInstaller 기반 빌드 스크립트 관리 (build_chemdraw.bat)
- 50종 이상 분자 스트레스 테스트 시나리오 구현
- 각 도메인의 기능 통합 테스트 작성

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자)
- Worker의 산출물을 아래 기준으로 검수
- 검수 통과 시 MM-TEST에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려

### 검수 체크리스트
1. **테스트 결과 검증**
   - [ ] 전체 테스트 PASS/FAIL 집계 보고서 작성
   - [ ] FAIL 테스트의 원인 분석 포함
   - [ ] 새 기능 추가 후 기존 테스트 회귀(regression) 확인
   - [ ] 테스트 커버리지가 주요 기능을 포괄하는가

2. **스트레스 테스트**
   - [ ] 50종 이상 분자로 전체 파이프라인 테스트
   - [ ] 예외 분자(큰 분자, 특수 원소, 빈 입력 등) 포함
   - [ ] 메모리 사용량이 비정상적으로 증가하지 않는가

3. **빌드 산출물 검증**
   - [ ] `tools/build_chemdraw.bat` 실행 성공
   - [ ] 빌드된 실행 파일(.exe)이 생성되었는가
   - [ ] 실행 파일이 독립적으로 실행 가능한가 (conda 환경 없이)
   - [ ] 실행 시 주요 기능(그리기, 분석, 저장)이 동작하는가

4. **코드 품질**
   - [ ] `py_compile` 전체 `src/app/*.py` 통과
   - [ ] 테스트 코드 자체에 하드코딩된 경로가 없는가
   - [ ] 테스트 간 의존성이 없는가 (독립 실행 가능)

---

## skills 필수 항목
- **QT_QPA_PLATFORM=offscreen**: headless 환경에서 PyQt6 테스트 실행 시 `os.environ['QT_QPA_PLATFORM'] = 'offscreen'` 설정. GUI 없는 CI/CD 환경에서 필수.
- **QWidget.grab() 스크린샷 패턴**: 테스트 중 위젯 상태를 캡처할 때 `widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)` 후 `widget.grab()` 사용.
- **py_compile 전체 파일 검사**: `python -m py_compile src/app/<file>.py` 패턴으로 OWNED_FILES 뿐 아니라 전체 src/app/*.py 문법 검사 실행.
- **테스트 분자 목록**: 에탄올, 아세트산, 벤젠, 아스피린, 카페인, 콜레스테롤 등 다양한 크기/작용기의 분자 50종 이상 유지.

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

