# 출력/통합 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | P-EXPORT Cascade #4 Wave 3

## 🔴 PENDING

### 기존 미완
- [ ] reportlab 설치 확인 및 conda 환경 반영

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED
- [x] EXPORT-001: IntegratedPDFExporter 6페이지 PDF 클래스 구현 (export_manager_enhanced.py v3.0)
  - 6페이지: 2D구조 / IR / NMR / UV-Vis / 3D구조 / 반응메커니즘
  - reportlab 우선, QPrinter fallback
  - 캔버스 캡처, 스펙트럼 데이터 수집, placeholder 페이지
- [x] EXPORT-002: ChemFileManager / ChemFileMetadata (.chem v2 포맷)
  - v2 헤더: _chem_version, _metadata, analysis_snapshot
  - v1 하위 호환, build_save_data/parse_load_data 인터페이스
- [x] error_handler.py에 PDF/chem 관련 에러 서브타입 추가
- [x] R-EXPORT: py_compile PASS, ast.parse PASS, _source/ 동기화 완료
- [x] DUAL SYNC: src/app/ -> _source/ 동기화 확인
- [x] TASK-EXPORT-ALPHA: ADMET/Drug PDF 페이지 추가 (v3.0→v4.0, 6→8페이지)
  - Page 7: ADMET (Lipinski Ro5, BBB, Metabolism, Drug-likeness) — admet_predictor.py 연동
  - Page 8: Drug Screening (QED, Composite Score, Tier) — drug_screening.py 연동
  - reportlab + QPrinter fallback, missing data placeholder 처리
  - py_compile PASS, _source/ 동기화 완료
- [x] TASK-EXPORT-MENU: API 정비 완료 (main_window.py 통합은 dept_ui_canvas에 요청)
  - export_integrated_pdf() 내부에서 _collect_admet_data(), _collect_drug_screening_data() 자동 호출
  - set_admet_data(), set_drug_screening_data() public API 제공

## ⛔ BLOCKED
(없음)

---
## SUBMIT (Cascade #3 Wave 3)

### 수정파일
| 파일 | 경로 | 변경 유형 |
|------|------|-----------|
| export_manager_enhanced.py | src/app/, _source/ | v2.0 -> v3.0 대폭 확장 |
| error_handler.py | src/app/, _source/ | EXPORT 에러 서브타입 추가 |

### 기획자 보고 (P-EXPORT)
1. **EXPORT-001**: `IntegratedPDFExporter` 클래스 신설. 6페이지 통합 PDF 생성 가능. reportlab 기반 전문 PDF + QPrinter fallback. `ExportManager.export_integrated_pdf()` 메서드로 main_window에서 호출 가능.
2. **EXPORT-002**: `ChemFileManager` / `ChemFileMetadata` 신설. .chem v2 포맷으로 분자명, SMILES, 분자식, view_state, 분석 스냅샷 등 메타데이터 보존. v1 하위 호환.
3. **error_handler.py**: PDF reportlab 에러, .chem save/load 에러에 대한 한국어 사용자 메시지 추가.

### 검수자 판정 (R-EXPORT)
- **py_compile**: export_manager_enhanced.py PASS, error_handler.py PASS
- **ast.parse**: export_manager_enhanced.py (26 top-level nodes) PASS, error_handler.py (12 nodes) PASS
- **_source/ 동기화**: 2개 파일 모두 동기화 확인
- **미수정 파일 검증**: OWNED_FILES 외부 파일 수정 없음 확인
- **판정: PASS**

### 감사 요청
- 약리도킹 전문 감사 (audit_professional_pharmacology_docking) 배정에 따라 해당 전문 감사자의 리뷰 요청
- main_window.py 통합은 dept_ui_canvas 부서에 별도 요청 필요
