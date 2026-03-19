# domain_drug — 신약 개발
> MM-DRUG + Worker + Reviewer

---

## OWNED_FILES
- `src/app/docking_interface.py`
- `src/app/docking_data.py`
- `src/app/docking_3d_viewer.py`
- `src/app/docking_interaction_analyzer.py`
- `src/app/lead_optimizer.py`
- `src/app/popup_lead_optimizer.py`
- `src/app/popup_docking.py`
- `src/app/alphafold_interface.py`
- `src/app/popup_alphafold.py`
- `src/app/admet_predictor.py`
- `src/app/popup_admet.py`
- `src/app/drug_screening.py`
- `src/app/popup_drug_screening.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_drug/context_list.md` → 현재 할 일 확인
3. `departments/domain_drug/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_drug/skills/` → 관련 스킬 발췌독

---

## MM-DRUG (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 신약 개발 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- 도킹 시뮬레이션 인터페이스 구현
- 리드 최적화: 유도체 생성 및 점수 평가
- AlphaFold 연동: 단백질 구조 예측 인터페이스
- ADMET 예측: Lipinski, BBB 투과, 대사 안정성
- 학생 친화적 UI: PDB ID 입력 불필요, 목표 단백질 선택만으로 작동

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자 — 약리학 전문)
- Worker의 산출물을 약리학/의약화학 기준으로 검수
- 검수 통과 시 MM-DRUG에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려

### 검수 체크리스트
1. **도킹 시각적 검증**
   - [ ] 도킹 결합부 ball & stick 3D 시각적 확인
   - [ ] 리간드-수용체 상호작용(수소 결합, 소수성 등)이 표시되는가
   - [ ] 결합 에너지 값이 물리적으로 타당한 범위인가

2. **ADMET 규칙 정확성**
   - [ ] Lipinski Rule of Five 계산이 정확한가 (MW<500, LogP<5, HBD<=5, HBA<=10)
   - [ ] BBB 투과 예측 기준이 올바른가
   - [ ] 대사 안정성 평가 기준이 문헌과 일치하는가

3. **유도체 생성 검증**
   - [ ] 생성된 유도체가 실제 신약 개발 방향과 일치하는가 (문헌 대조)
   - [ ] 30종 이상 분자로 유도체 생성 테스트
   - [ ] 유도체의 SMILES가 유효한가 (RDKit 파싱 가능)

4. **점수 체계 검증**
   - [ ] score_variant 복합 점수 가중치: 도킹 30% + QED 20% + ADMET 20% + SA 15% + 개선도 15%
   - [ ] 각 개별 점수가 0~1 범위로 정규화되었는가

5. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] LLM fallback chain (Groq -> Gemini -> 프리셋) 동작 확인
   - [ ] API 키 로딩: `~/.chemgrid/config.json` -> `os.environ` 자동 주입 경로 확인

---

## skills 필수 항목
- **Groq -> Gemini -> 프리셋 LLM fallback chain**: 유도체 생성 시 Groq API 우선 호출, 실패 시 Gemini, 그마저 실패 시 프리셋 유도체 목록 사용. 세 단계 모두 구현 필수.
- **API 키 관리**: `~/.chemgrid/config.json`에서 읽어 `os.environ`에 자동 주입. 키가 없으면 프리셋 모드로 graceful fallback.
- **RECEPTOR_DATABASE 8개 수용체**: 각 수용체의 약리학적 맥락(적응증, 기전, 선택성)을 코드 내 문서화. 학생이 수용체 선택 시 맥락 설명 표시.
- **score_variant 복합 점수**: 도킹 30% + QED 20% + ADMET 20% + SA(합성 접근성) 15% + 개선도 15%. 가중치 변경 시 반드시 MM 승인.

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

