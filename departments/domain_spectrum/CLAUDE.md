# domain_spectrum — 분광 분석
> MM-SPECTRUM + Worker + Reviewer

---

## OWNED_FILES
- `src/app/predict_spectra.py`
- `src/app/spectrum_calculator.py`
- `src/app/popup_spectrum.py`
- `src/app/popup_predicted_spectrum.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_spectrum/context_list.md` → 현재 할 일 확인
3. `departments/domain_spectrum/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_spectrum/skills/` → 관련 스킬 발췌독

---

## MM-SPECTRUM (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 분광 분석 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- IR/NMR/UV-Vis/Raman 스펙트럼 예측 알고리즘 구현
- SMARTS 기반 작용기 탐지 로직 유지보수
- 스펙트럼 데이터 계산 엔진 (spectrum_calculator.py)
- 스펙트럼 시각화 팝업 UI (popup_spectrum.py, popup_predicted_spectrum.py)

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자 — NIST 대조 전문)
- Worker의 산출물을 교과서/데이터베이스 기준으로 검수
- 검수 통과 시 MM-SPECTRUM에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려 (예: "에탄올 O-H stretch가 3200 cm-1인데, 교과서 기준 3200-3550 범위이므로 3400 cm-1으로 수정 필요")

### 검수 체크리스트
1. **IR 스펙트럼 정확성 (Silverstein/Pavia 기준)**
   - [ ] O-H, N-H, C=O 등 주요 작용기 피크 위치가 교과서와 일치하는가
   - [ ] 피크 강도(strong/medium/weak)가 상대적으로 올바른가
   - [ ] 허용 오차: ±30 cm-1

2. **NMR 정확성**
   - [ ] 1H NMR: 화학적 이동 허용 오차 ±0.5 ppm
   - [ ] 13C NMR: 화학적 이동 허용 오차 ±5 ppm
   - [ ] 적분비(multiplicity)가 H 개수와 일치하는가
   - [ ] 커플링 패턴(singlet, doublet, triplet 등)이 올바른가

3. **UV-Vis 정확성**
   - [ ] lambda_max 허용 오차 ±15 nm
   - [ ] 발색단(chromophore) 기여가 올바르게 반영되었는가
   - [ ] 조색단(auxochrome) additive 보정이 적용되었는가

4. **스트레스 테스트**
   - [ ] 50종 이상 분자로 스펙트럼 생성 테스트
   - [ ] 예외 분자(방향족, 카보닐, 아민 등 다양한 작용기)가 포함되었는가
   - [ ] 에러 없이 모든 분자 처리 완료

5. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] 에러 처리가 적절한가 (유효하지 않은 SMILES 입력 시)

---

## skills 필수 항목
- **AddHs() explicit H 카운트**: `Chem.AddHs(mol)` 호출 후 명시적 수소 원자를 카운트해야 NMR multiplicity 계산이 정확함. 암묵적(implicit) H만으로 계산하면 다중선 패턴 오류 발생.
- **13C dedup ±1 ppm 윈도우**: 동일 화학 환경의 13C 피크는 ±1 ppm 이내이면 하나로 합산(deduplication). 중복 피크 방지.
- **UV-Vis auxochrome additive 모델**: 기본 발색단 lambda_max에 조색단 보정값을 가산하는 방식. Woodward-Fieser 규칙 기반.
- **SMARTS 패턴 매칭**: `mol.HasSubstructMatch(Chem.MolFromSmarts(pattern))` 사용. 패턴이 None이 아닌지 반드시 검증.

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

