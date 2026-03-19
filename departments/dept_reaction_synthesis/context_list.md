# 반응/합성 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #5 완료

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED (Cascade #6)

### TASK-RXTN-C6-001: 메커니즘 서술 화살표 밀기 내러티브 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `reaction_mechanisms.py`, `mechanism_engine.py` (+ `_source/` 동기화)
- **변경**: 15+ 메커니즘 재작성 — 결합 끊김/이탈기/전자 이동 서술, `_classify_atom_role()` 분류
- **검증**: py_compile PASS, _source/ sync OK

### TASK-RXTN-C6-002: 합성 경로 현실성 강화 Round 2 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `retrosynthesis_engine.py`, `building_blocks.py` (+ `_source/` 동기화)
- **변경**: CONDITION_MAP 30+, SMARTS 금지 하부구조, MW<250/heavy<15, 비상업물질 +100pt
- **검증**: py_compile PASS, _source/ sync OK

### TASK-RXTN-C6-003: Gemini AI QThread 비동기화 [P1] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `popup_synthesis.py` (+ `_source/` 동기화)
- **변경**: `_GeminiWorker(QObject)` + QThread, 에러 분류 4종
- **검증**: py_compile PASS, _source/ sync OK

## ✅ COMPLETED (이전)

### TASK-RXTN-C5-001: 합성 경로 현실성 강화 [P0] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `retrosynthesis_engine.py`, `building_blocks.py` (+ `_source/` 동기화)
- **변경**: MAX_ROUTE_STEPS=10, `is_commercially_available()` 2단계 검증, `_validate_route_realism()` 필터, 미확인 시약 +30pt 페널티. building_blocks 60→110개 확장.
- **검증**: py_compile PASS, _source/ sync OK

### TASK-RXTN-C5-002: Gemini AI 파이프라인 개선 [P1] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `popup_synthesis.py` (+ `_source/` 동기화)
- **변경**: AI 버튼 경로 선택만으로 활성화, 2종 프롬프트(단계/전체), 에러 핸들링 개선, 자동 fallback
- **검증**: py_compile PASS, _source/ sync OK

### TASK-RXTN-005: 활성화된 방향족 SMARTS 수정 [P2] ✅ — Cascade #4 Wave 3
- **완료일**: 2026-03-18
- **수정 파일**: reaction_predictor.py
- **변경**: 파싱 실패 SMARTS → phenol/aniline/anisole 3개 개별 패턴으로 분리. REACTION_RULES 참조도 업데이트.
- **검증**: py_compile PASS, RDKit SMARTS parse 3/3 OK, _source/ sync OK

### TASK-RXTN-006: SN2 생성물 예측 — 전체 fragment 합산 [P2] ✅ — Cascade #4 Wave 3
- **완료일**: 2026-03-18
- **수정 파일**: mechanism_engine.py
- **변경**: _predict_product()에서 RunReactants 후 모든 fragments를 '.'.join()으로 합산 → MolFromSmiles 검증 → 정규화된 combined SMILES 반환.
- **검증**: py_compile PASS, _source/ sync OK

### RXTN-R01: 2분자 반응 인식 [P0] ✅ — Cascade #3 Wave 2
- **완료일**: 2026-03-18
- **수정 파일**: src/app/reaction_predictor.py, _source/reaction_predictor.py
- **변경 내용**:
  - `predict_from_combined_smiles(combined_smiles)` 메서드 추가
  - Dot-separated SMILES를 RDKit fragment 분리 → 개별 predict() 호출
  - 2분자: 직접 predict, 3+분자: 모든 조합 시도 후 합산/중복제거
- **검증**: SN2 ✅, E2 ✅, Diels-Alder ✅, 단일분자(0 결과) ✅

### RXTN-R02: 곡선 화살표 렌더러 개선 [P0] ✅ — Cascade #3 Wave 2
- **완료일**: 2026-03-18
- **수정 파일**: src/app/popup_reaction.py, _source/popup_reaction.py
- **변경 내용**:
  - `_calc_control_points()` 공통 헬퍼 추출
  - 짧은 화살표(<30px) 전용 bulge 범위
  - 화살촉 거리 비례 적응 크기 (7-12px)
  - 론페어 전자쌍 도트(··) 및 단일 전자 도트(·) 렌더링
  - `_draw_lone_pair_dots()`, `_draw_single_electron_dot()` 추가
- **검증**: py_compile ✅, ast.parse ✅

### RXTN-R03: 합성 → 실험 조건 도출 [P1] ✅ — Cascade #3 Wave 2
- **완료일**: 2026-03-18
- **수정 파일**: src/app/popup_synthesis.py, _source/popup_synthesis.py
- **변경 내용**:
  - Gemini 프롬프트 7개 섹션 구조화 (시약, 조건, 촉매, 수율, 후처리, 안전, 대체법)
  - `_show_fallback_protocol()` — API 미사용 시 rule-based 기본 프로토콜 생성
  - graceful fallback: genai 미설치/키 미설정 시 자동 전환
- **검증**: py_compile ✅, ast.parse ✅

### TASK-RXTN-003: 2분자 반응 경로 팝업 강화 [P1] ✅ — Cascade #3 Wave 2
- **완료일**: 2026-03-18
- **변경 내용**: RXTN-R02로 CurvedArrowRenderer 품질 개선 완료
- **주의**: arrow_generator.py 수정 불필요 확인됨

### TASK-RXTN-004: 합성방법 탭 — Gemini API 구체적 실험 프로토콜 [P2] ✅ — Cascade #3 Wave 2
- **완료일**: 2026-03-18
- **변경 내용**: RXTN-R03으로 프롬프트 강화 + fallback 완료

### TASK-RXTN-001: mechanism_engine.py 중간체 생성 정확도 개선 [P1] ✅
- **완료일**: 2026-03-18
- **수정 파일**: src/app/mechanism_engine.py, _source/mechanism_engine.py
- **변경 내용**:
  - `_estimate_intermediate_smiles()` — RDKit RWMol 기반 결합 편집 구현
  - `_adjust_charge_on_break()` — 헤테로리틱 분열 형식전하 보정 (전기음성도 기반)
  - `_adjust_charge_on_form()` — 새 결합 형성 시 전하 중화
  - `_ELECTRONEG` 전기음성도 테이블 추가
  - SanitizeMol 실패 시 partial sanitize 폴백
- **검증**: SN2 ✅, E2 ✅, Diels-Alder ✅

### TASK-RXTN-002: 복잡 반응 유형 지원 확장 [P1] ✅
- **완료일**: 2026-03-18
- **수정 파일**: reaction_predictor.py, reaction_mechanisms.py, mechanism_engine.py + _source/
- **추가된 반응 유형 (7종)**: [2+2], Cope, Claisen, Suzuki, Heck, 노르보르넨, 다치환 EAS
- **검증**: 모두 통과

## ⛔ BLOCKED
(없음)
