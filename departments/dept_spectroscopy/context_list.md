# 분광학 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 2

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED (Cascade #6)

### TASK-SPEC-C6-001: 스펙트럼 팝업 크기 확대 + PDF 리포트 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `popup_spectrum.py` (+ `_source/` 동기화)
- **변경**: 팝업 1000x700→1200x800, 그래프 최소크기 1100x600, `export_pdf_report()` 추가 (PdfPages 멀티페이지: IR+Raman+Combined+PeakTable+Summary)
- **검증**: py_compile PASS, _source/ sync OK

### TASK-SPEC-C6-002: 진동 모드 IR/Raman 활성도 표시 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `vibration_engine.py` (+ `_source/` 동기화)
- **변경**: VibrationMode에 ir_active/raman_active/explanations/wavelength_um/freq_range_label 필드 추가
- **검증**: py_compile PASS, _source/ sync OK

## ✅ COMPLETED (이전)

### Cascade #3 Wave 2 — SPEC-R01: IR/NMR 정밀도 개선 [P0] ← PASS
- **수정 내용 (2026-03-18)**:
  - (A) IR `has_sp2_ch` 로직 수정: C=O 탄소 제외 → acetone 거짓양성 =C-H 제거
  - (B) pyridine C=N SMARTS `[nX2]` 추가 + IR_LOOKUP C=N_pyridine 1590/1480 cm-1
  - (B-2) predict_ir() 우선순위 로직: specific groups > generic groups (dedup 충돌 해소)
  - (C) 13C alpha-carbonyl CH3 보정: -5 → -2 (acetone 28.0 ppm, Silverstein 30.0 대비 diff=2.0)
  - (D) 신규 작용기 7종: C-F, C-I, S-H, S=O(sulfoxide/sulfone), P=O, NO2, C=N_imine
  - (D-2) NO2 SMARTS dual pattern: `[$([NX3](=O)=O),$([NX3+](=O)[O-])]`
- **수정 파일**: predict_spectra.py
- **동기화**: src/app/ → _source/ 완료
- **R-SPEC 검증**: py_compile PASS, ast.parse PASS, sync PASS, 화학 정확성 6/6 PASS
- **하달일**: 2026-03-18

### Cascade #3 Wave 2 — SPEC-R02: UV-Vis 예측 완성 [P1] ← PASS
- **수정 내용 (2026-03-18)**:
  - (A) Woodward-Fieser 다이엔 규칙: `_woodward_fieser_diene()` 신규 구현
  - (B) Woodward-Fieser 엔온 규칙: `_woodward_fieser_enone()` 신규 구현
  - (C) 방향족 auxochrome 치환기 보정 (-OH +11nm, -NH2 +13nm 등)
  - (D) 다환 방향족 세분화 (naphthalene 275/310nm, anthracene 350/375nm)
  - (E) S lone pair n→sigma* 추가, graceful fallback (sigma→sigma* only)
- **수정 파일**: predict_spectra.py
- **동기화**: src/app/ → _source/ 완료
- **R-SPEC 검증**: butadiene 217nm PASS, MVK enone 215nm PASS, ethane fallback PASS
- **하달일**: 2026-03-18

### ⚠️ 이전 세션 태스크 (Cascade #3 Wave 2 이전, 참조용)

### TASK-SPEC-001: 복잡 분자 IR 스펙트럼 정확성 [P1] ← invalidated by Cascade #3 Wave 2
- 세션 2에서 검증 통과 (4/4 PASS), Wave 2에서 추가 개선됨

### TASK-SPEC-002: NMR 스펙트럼 피크 정확성 [P1] ← invalidated by Cascade #3 Wave 2
- 세션 2에서 3건 수정 완료, Wave 2에서 alpha-carbonyl CH3 추가 개선됨

### TASK-SPEC-003: 스펙트럼 팝업 크기 일관성 [P1] ← 유지 (변경 없음)
- resize(1000,700) + figsize(9.0,4.5) 통일 상태 유지

## ⛔ BLOCKED
(없음)
