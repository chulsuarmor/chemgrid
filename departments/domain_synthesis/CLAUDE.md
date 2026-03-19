# domain_synthesis — 합성/반응 경로
> MM-SYNTHESIS + Worker + Reviewer

---

## OWNED_FILES
- `src/app/retrosynthesis_engine.py`
- `src/app/mechanism_engine.py`
- `src/app/building_blocks.py`
- `src/app/popup_synthesis.py`
- `src/app/reaction_mechanisms.py`
- `src/app/arrow_generator.py`
- `src/app/mechanism_pdf_exporter.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_synthesis/context_list.md` → 현재 할 일 확인
3. `departments/domain_synthesis/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_synthesis/skills/` → 관련 스킬 발췌독

---

## MM-SYNTHESIS (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 합성/반응 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- 역합성 경로 BFS 탐색 + 다단계 재귀 분해 구현
- 반응 메커니즘 화살표(굽은 화살표, electron pushing) 생성
- 합성 경로 PDF 내보내기 (mechanism_pdf_exporter.py)
- building_blocks.py 상용 시약 DB 관리

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자 — Clayden/March 대조)
- Worker의 산출물을 유기화학 교과서 기준으로 검수
- 검수 통과 시 MM-SYNTHESIS에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려

### 검수 체크리스트
1. **합성 경로 정확성 (Clayden/March 기준)**
   - [ ] 각 단계의 반응 조건(시약, 온도, 용매)이 교과서와 일치하는가
   - [ ] 반응 유형(SN1/SN2, E1/E2, 친전자 첨가 등)이 올바르게 분류되었는가
   - [ ] 선택성(위치선택성, 입체선택성)이 반영되었는가

2. **시작물질 검증**
   - [ ] 시작물질이 `building_blocks.py` DB에 등록된 상용 시약인가
   - [ ] `is_commercially_available()` 함수가 DB 조회만 수행하는가 (heuristic 제거 확인)

3. **다단계 경로 검증**
   - [ ] 2단계 이상의 합성 경로가 생성되는가
   - [ ] 재귀 분해(`_recurse_depth`)가 올바르게 작동하는가
   - [ ] 무한 재귀 방지 장치가 있는가

4. **PDF 내보내기 검증**
   - [ ] PDF 파일이 실제로 생성되는가 (크기 > 1KB)
   - [ ] 반응 화살표가 PDF에 올바르게 렌더링되는가
   - [ ] 한국어 텍스트(반응 조건 설명 등)가 깨지지 않는가

5. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] `SynthesisStep`/`SynthesisRoute` 데이터 구조가 일관적인가
   - [ ] 에러 처리가 적절한가

---

## skills 필수 항목
- **is_commercially_available() = DB only**: 이 함수는 `building_blocks.py`의 DB에서만 조회. heuristic 기반 판단은 완전히 제거됨. 새 시약 추가는 DB에 직접 등록해야 함.
- **fragment route 재귀 분해 (_recurse_depth)**: 목표 분자를 재귀적으로 분해할 때 `_recurse_depth` 파라미터로 깊이 제한. 기본값 3, 최대 5.
- **SynthesisStep/SynthesisRoute 데이터 구조**: `SynthesisStep`은 단일 반응 단계(reactants, products, conditions), `SynthesisRoute`는 여러 Step의 순서 목록.
- **메커니즘 PDF ㄹ자 레이아웃**: 다단계 메커니즘을 PDF로 내보낼 때 ㄹ자(serpentine) 레이아웃 사용. 페이지 너비를 초과하면 다음 줄로 접힘.

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

