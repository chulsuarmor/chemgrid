# domain_core — 핵심 화학 엔진
> MM-CORE + Worker + Reviewer

---

## OWNED_FILES
- `src/app/analyzer.py`
- `src/app/chem_data.py`
- `src/app/engine_physics.py`
- `src/app/engine_resonance.py`
- `src/app/coord_utils.py`
- `src/app/electron_density_analyzer.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_core/context_list.md` → 현재 할 일 확인
3. `departments/domain_core/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_core/skills/` → 관련 스킬 발췌독

---

## MM-CORE (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT(Control Tower)로부터 받은 지시를 Worker에게 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백을 Worker에게 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- 화학 계산 엔진 구현: 결합 길이, 결합각, ESP(정전기 포텐셜), 공명 구조
- RDKit 기반 분자 분석 파이프라인 유지보수
- 전자 밀도 분석기 개선 (electron_density_analyzer.py)
- 공명 구조 생성 및 기여도 계산 (engine_resonance.py)

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자)
- Worker의 산출물을 아래 기준으로 검수
- 검수 통과 시 MM-CORE에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려 (모호한 피드백 금지)

### 검수 체크리스트
1. **정확성 검증 (NIST/CRC Handbook 대조)**
   - [ ] 결합 길이: 허용 오차 ±0.05 Angstrom
   - [ ] 결합각: 허용 오차 ±5도
   - [ ] ESP 값: 부호(+/-) 및 상대적 크기가 물리적으로 타당한가
   - [ ] 공명 구조: 유기화학 교과서 기준 유효한 공명 형태인가

2. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] 단위 테스트 실행 및 PASS 확인
   - [ ] 에러 처리(try/except) 적절히 추가되었는가
   - [ ] 타입 힌트가 일관적인가

3. **도메인 규칙 준수**
   - [ ] Carbon은 `''` (빈 문자열)로 저장되는가 (`"C"` 사용 금지)
   - [ ] Gasteiger blending: 60% Gasteiger + 40% custom 비율 준수
   - [ ] `RDKit Chem.MolFromSmiles()` 호출 후 None 체크 존재

4. **회귀 확인**
   - [ ] 기존 테스트가 깨지지 않았는가
   - [ ] 다른 도메인에서 호출하는 public API 시그니처가 변경되지 않았는가

---

## skills 필수 항목
- **Carbon 빈 문자열 규칙**: 내부 데이터 구조에서 탄소 원소는 `''`(빈 문자열)로 저장. `"C"`를 사용하면 파싱 오류 발생.
- **Gasteiger blending**: `0.6 * gasteiger_charge + 0.4 * custom_charge` 공식 엄수.
- **RDKit 유효성 검사 패턴**: `mol = Chem.MolFromSmiles(smiles)` 후 반드시 `if mol is None: return` 패턴 적용.
- **좌표 변환**: `coord_utils.py`의 pixel<->Angstrom 변환 함수 사용 (직접 계산 금지).

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

