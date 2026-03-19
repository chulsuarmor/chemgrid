# domain_3d — 3D 시각화
> MM-3D + Worker + Reviewer

---

## OWNED_FILES
- `src/app/popup_3d.py`
- `src/app/vibration_engine.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_3d/context_list.md` → 현재 할 일 확인
3. `departments/domain_3d/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_3d/skills/` → 관련 스킬 발췌독

---

## MM-3D (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 3D 시각화 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- OpenGL/QPainter 기반 3D 분자 렌더링 구현
- 오비탈 시각화: Monte Carlo 점밀도(rejection sampling) 방식
- 진동 모드 애니메이션 (vibration_engine.py)
- 도킹 결합부 3D 시각화

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자)
- Worker의 산출물을 아래 기준으로 검수
- **실제 3D 팝업 실행 필수** — headless 테스트만으로 PASS 불가
- 검수 통과 시 MM-3D에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려

### 검수 체크리스트
1. **시각적 검증 (스크린샷 필수)**
   - [ ] 3D 팝업 실행 후 스크린샷 캡처
   - [ ] 빈 화면이 아닌, 실제 3D 렌더링이 보이는가
   - [ ] 색상 다양성 검증: 원소별 구분 가능한 색상이 사용되는가
   - [ ] 결합선(단일/이중/삼중)이 올바르게 렌더링되는가

2. **렌더링 경로 이중 테스트**
   - [ ] OpenGL 경로 정상 동작 확인
   - [ ] QPainter fallback 경로 정상 동작 확인
   - [ ] 두 경로 간 시각적 차이가 허용 범위 내인가

3. **교과서 기준 검증**
   - [ ] 오비탈 모양이 교과서(Atkins/Shriver) 기준과 일치하는가
   - [ ] s-오비탈: 구형, p-오비탈: 아령형, d-오비탈: 해당 대칭
   - [ ] 양/음 위상이 색상으로 올바르게 구분되는가

4. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] OpenGL 컨텍스트 생성/해제가 올바른가
   - [ ] 에러 처리 및 fallback 로직이 적절한가

5. **회귀 확인**
   - [ ] 기존 3D 뷰어 기능이 깨지지 않았는가
   - [ ] 다른 도메인(domain_drug 등)에서 호출하는 API가 변경되지 않았는가

---

## skills 필수 항목
- **Kekulize 방향족 처리**: `Chem.Kekulize(mol)` 호출 후 교대 단일/이중 결합으로 렌더링. 방향족 고리는 교대 결합으로 표시.
- **Monte Carlo rejection sampling**: 오비탈 시각화 시 |psi|^2에 비례하는 점밀도 생성. 균일 분포에서 샘플링 후 |psi(r)|^2 / max(|psi|^2)와 비교하여 reject/accept.
- **QPainter fallback 이중선**: OpenGL 사용 불가 환경에서 QPainter로 이중 결합을 평행 이중선으로 렌더링. 오프셋 거리 = bond_length * 0.1.
- **진동 모드**: 정규 모드 벡터를 원자 좌표에 sin(omega*t) 진폭으로 적용. 주기적 애니메이션.

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

