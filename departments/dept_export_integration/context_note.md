# 출력/통합 부서 기술 노트
> 최종 업데이트: 2026-03-18 | P-EXPORT Cascade #4 Wave 3

## 기술적 판단 기록

### 2026-03-18: EXPORT-001 (6페이지 통합 PDF) 설계 결정

1. **IntegratedPDFExporter 클래스 신설** (`export_manager_enhanced.py`)
   - 6페이지 구성: 2D구조(Lewis) / IR / NMR / UV-Vis / 3D구조(Theory) / 반응메커니즘
   - reportlab 우선, 미설치시 QPrinter fallback 자동 전환
   - 각 페이지는 `IntegratedPDFPageData` 데이터클래스로 관리
   - 데이터 미존재시 placeholder 페이지 출력 (graceful degradation)

2. **캔버스 캡처**: `capture_canvas_state(canvas, view_state)` 메서드로 Lewis/Theory 뷰를 임시 PNG로 캡처 후 PDF에 임베딩. 캡처 후 원래 view_state로 복원.

3. **스펙트럼 데이터 수집**: main_window의 ir_popup, nmr_popup, uvvis_popup에서 `get_spectrum_data_for_pdf()` 인터페이스를 통해 데이터 수집. base_spectrum.py 추상 메서드 계약 준수.

4. **한국어 폰트**: reportlab용 한국어 폰트 등록 로직을 spectrum_pdf_exporter.py와 동일하게 구현 (Malgun > Gulim > Helvetica fallback).

### 2026-03-18: EXPORT-002 (.chem v2 포맷) 설계 결정

1. **ChemFileManager / ChemFileMetadata 신설** (`export_manager_enhanced.py`)
   - v2 포맷: `_chem_version`, `_metadata` 헤더 추가
   - 메타데이터: molecule_name, smiles, molecular_formula, view_state, created_at, modified_at, atom_count, bond_count, has_analysis
   - `analysis_snapshot` 필드로 분석 결과 경량 스냅샷 저장
   - v1 포맷과 완전 하위 호환: `_chem_version` 없으면 v1으로 취급

2. **build_save_data()**: canvas에서 직렬화된 저장 데이터 생성. main_window.save_file()에서 호출 가능.
   - QPointF -> [x, y] 변환 포함
   - set -> list 변환 (user_lp)
   - Wedge/Dash 결합 직렬화

3. **parse_load_data()**: v1/v2 파일 모두 정규화된 구조로 파싱.

4. **get_metadata_from_file()**: 전체 로드 없이 메타데이터만 읽기 (파일 브라우저 미리보기용).

### error_handler.py 변경사항

- `EXPORT` 에러 타입에 `pdf_reportlab`, `chem_save`, `chem_load` 서브타입 추가
- 키워드 기반 매칭: "reportlab", ".chem" + "save"/"load" 감지

## 발견된 문제 / 블로커

- **reportlab 미설치 가능성**: build 환경에서 `missing module named 'reportlab.pdfgen'` 경고 확인됨 (warn-ChemGrid.txt). QPrinter fallback으로 대응 완료.
- **main_window.py 수정 불가**: OWNED_FILES 외부이므로 `export_integrated_pdf()` 호출은 main_window 담당 부서에서 통합 필요. `ExportManager.export_integrated_pdf()` 메서드로 호출 인터페이스 준비 완료.
- **main_window.save_file()에 ChemFileManager 통합 필요**: 현재 main_window의 save_file/load_file은 직접 직렬화. ChemFileManager.build_save_data/parse_load_data를 호출하도록 전환하면 v2 메타데이터 지원됨. 이 통합은 main_window 담당 부서 작업.

### 2026-03-18: TASK-EXPORT-ALPHA (8페이지 PDF, v3.0→v4.0) 설계 결정

1. **Page 7 (ADMET Analysis)**: `set_admet_data(admet_dict)` setter 추가. `_rl_admet_page()` 렌더링 메서드:
   - Lipinski Ro5: 4-row property table (MW, LogP, HBD, HBA) + pass/fail + violations
   - BBB Permeability: score, classification, TPSA, factor details table
   - Metabolic Stability: classification, score, alerts list (max 8)
   - Drug-likeness Summary: composite score, oral bioavailability, overall assessment
   - Warnings section (max 6, red text)
   - Data source: `admet_predictor.predict_admet()` → `admet_to_dict()` (try/except import)

2. **Page 8 (Drug Screening)**: `set_drug_screening_data(result_dict)` setter 추가. `_rl_drug_screening_page()`:
   - Screening summary: n_compounds, n_hits, filters
   - Candidate table (max 25 rows): Rank, Name, QED, Composite, Tier, Oral BA
   - Tier color-coding: A=green, C=red cell backgrounds
   - Data source: `main_window.last_screening_result` or `.screening_result` attribute
   - ScreeningResult dataclass → `screening_result_to_dict()` auto-conversion

3. **Graceful degradation**: 두 페이지 모두 데이터 없으면 "데이터 없음" placeholder 표시. admet_predictor/drug_screening import 실패 시 placeholder.

4. **QPrinter fallback**: page_order에 "admet", "drug_screening" 추가. QPrinter는 title + description만 렌더링 (테이블 미지원).

5. **ExportManager 통합**: `_collect_admet_data(exporter, smiles, mol_name)` — SMILES 기반 자동 ADMET 예측. `_collect_drug_screening_data(exporter)` — main_window에서 이전 스크리닝 결과 탐색.

### TASK-EXPORT-MENU: API 정비 (main_window.py 통합 대기)

- `export_integrated_pdf()`는 이미 8페이지 모두 자동 수집/생성하는 완전한 API.
- main_window.py 메뉴 연결은 **dept_ui_canvas 소관**. 이 부서는 API만 제공.
- main_window에서 호출 패턴: `ExportManager(self).export_integrated_pdf()`

## 타 부서 요청 사항

- **dept_ui_canvas**: main_window.py에 `export_integrated_pdf()` 호출을 위한 메뉴 항목 추가 요청
- **dept_ui_canvas**: main_window.py의 save_file/load_file에서 `ChemFileManager.build_save_data()` / `ChemFileManager.parse_load_data()` 사용으로 전환 요청
- **dept_ui_canvas**: (NEW) main_window.py에 `last_screening_result` 속성 저장 로직 추가 요청 (drug screening 실행 후 결과를 PDF 8페이지에 반영하기 위함)
