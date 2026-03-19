# UI/Canvas 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #5 완료

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED

### TASK-UC-C5-001: PubChem fuzzy filter 추가 [P1] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `main_window.py` (+ `_source/` 동기화)
- **변경**: `_name_is_similar()` 헬퍼 — trigram Jaccard ≥0.35 필터로 PubChem 오매칭 차단
- **검증**: py_compile PASS, _source/ sync OK

### TASK-UC-C5-002: 2D 배위결합 렌더링 [P1] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `main_window.py`, `canvas.py` (+ `_source/` 동기화)
- **변경**: `_detect_2d_coordination_bonds()` + canvas Dative 대시선+화살표
- **검증**: py_compile PASS, _source/ sync OK

### TASK-UC-ALPHA-001: "신약개발" 메뉴 추가 [P0] ✅ — Cascade #4 Wave 2
- **하달일**: 2026-03-18 | **완료일**: 2026-03-18
- **수정 파일**: `toolbar_setup.py`, `main_window.py` (+ `_source/` 동기화)
- **변경 사항**: QMenu "신약개발" 4항목 (AlphaFold/ADMET/스크리닝/도킹) + QAction 드롭다운
- **검증**: py_compile PASS, _source/ sync OK

### TASK-UC-ALPHA-002: main_window.py 트리거 메서드 4개 [P0] ✅ — Cascade #4 Wave 2
- **하달일**: 2026-03-18 | **완료일**: 2026-03-18
- **수정 파일**: `main_window.py` (+ `_source/` 동기화)
- **변경 사항**: open_alphafold_popup/open_admet_popup/open_drug_screening_popup/open_docking_popup — import-on-demand + try/except fallback. ADMET은 다중 SMILES 소스 시도.
- **검증**: py_compile PASS, _source/ sync OK

### TASK-UC-003: _draw_smiles_on_canvas pan_offset 정밀 보정 [P0] ✅
- **하달일**: 2026-03-18 | **완료일**: 2026-03-18
- **수정 파일**: `src/app/main_window.py` (+ `_source/main_window.py` 동기화)
- **변경 사항**:
  1. `scale = 26.7` (하드코딩) → `scale = self.cv.grid_size / 1.5` (동적 계산, grid_size=40 → 26.67)
  2. 키 충돌 오프셋: `offset * 2.0` → `offset * self.cv.grid_size` (그리드 정렬 보장)
  3. 줌/팬 상태 디버그 로그 추가 (sf, pan, center_logical)
- **검증**: py_compile OK, ast.parse OK, _source/ sync OK, 10종 분자 headless 테스트 PASS
- **감사 배정**: 구조화학

### TASK-UC-004: analysis_results 갱신 100% 보장 [P0] ✅
- **하달일**: 2026-03-18 | **완료일**: 2026-03-18
- **수정 파일**: `src/app/main_window.py` (+ `_source/main_window.py` 동기화)
- **변경 사항**:
  1. analyze() 전체 실패 시 guaranteed fallback: minimal dict 생성 (smiles, atoms, norm_atoms, theory_data, formula)
  2. 'smiles' 키 항상 존재 보장 (belt-and-suspenders)
  3. analysis_results 상태 요약 로그 추가
- **검증**: py_compile OK, ast.parse OK, _source/ sync OK, 10종 분자 headless 테스트 PASS
  - 테스트 분자: benzene, aspirin, caffeine, ethanol, tropylium, cp-, glucose, acetic_acid, naphthalene, pyridine
  - 결과: 10/10 PASS, analysis_results None 0건
- **감사 배정**: 구조화학

### TASK-UC-001: _draw_smiles_on_canvas grid snap 폴백 강화 ✅
- `canvas.py` get_closest_pt(): `strict=False` 파라미터 추가 → 항상 최근접 grid point 반환
- `main_window.py` line 1040: `strict=False` 호출 → SMILES 드로잉 항상 hex grid 정렬
- `_source/` 동기화 완료, py_compile 통과

### TASK-UC-002: analysis_results silent exception 제거 ✅
- `main_window.py` line 1096-1115: 3개 bare except → 에러 로깅 + fallback analyze() 재시도
- smiles 파라미터 실패 시 smiles 없이 재호출
- `_source/` 동기화 완료, py_compile 통과

## ⛔ BLOCKED
(없음)
