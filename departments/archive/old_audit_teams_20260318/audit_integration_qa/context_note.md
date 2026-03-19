# 통합 파이프라인 감사관 감사 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 3 감사 완료

## 감사 이력

### 2026-03-18: Cascade #3 Wave 3 감사 (3개 부서)

---

#### 1. dept_dft_orca — orca_interface.py (v3.10)

**1-A. %plots block format (ORCA 6.1.1)** — PASS
- `ORBITAL_PLOT_TEMPLATE` (line 211-227) 확인 완료
- `! B3LYP 6-31G(d) TIGHTSCF MINIPRINT MOREAD NOITER` 헤더 정확
- `%moinp "{gbw_file}"` 로 기존 .gbw 재사용, SCF 재계산 없음
- `%plots` 블록: dim1/dim2/dim3=100, Format Gaussian_Cube, MO/ElDens 지시어 올바름
- ORCA 6.1.1에 orca_plot 없음을 정확히 반영 (입력 파일 내 %plots 직접 사용)
- `generate_orbital_cubes()` (line 975-1053) 에서 HOMO/LUMO 인덱스 자동 탐지 후 template 적용, 120초 timeout 포함

**1-B. xtb subprocess call safety** — PASS
- `run_xtb_charges()` (line 1262-1341):
  - `subprocess.run()` 사용 (not Popen) with `capture_output=True, text=True`
  - `timeout=60` 기본값 적용
  - `cwd=str(work_dir)` 로 작업 디렉토리 격리
  - cmd 인자: `[str(xtb_exe), str(xyz_path), "--gfn", "2", "--chrg", str(charge), "--pop"]` — shell=False (기본값), 인젝션 위험 없음
  - 경로 처리: `find_xtb_executable()` 에서 `Path` 객체 사용, `str()` 변환 후 subprocess에 전달
  - 임시 디렉토리: `tempfile.mkdtemp(prefix="chemgrid_xtb_")` 사용

**1-C. Graceful fallback (xtb 미설치)** — PASS
- `find_xtb_executable()` → None 반환 시 `run_xtb_charges()` → 빈 dict `{}` 반환
- `get_xtb_charges_for_molecule()` → 빈 dict 반환
- 예외 처리: `TimeoutExpired`, `FileNotFoundError`, 일반 `Exception` 모두 catch → 빈 dict 반환, warning 로그
- 비정상 종료 (returncode != 0) → 빈 dict 반환, stderr 500자 로깅

**1-D. Mulliken charge parsing robustness** — PASS (경미한 주의사항 있음)
- `_parse_xtb_mulliken_charges()` (line 1344-1393):
  - 헤더 탐지: `"#   Z" in line and "q" in line` — xtb 표준 출력 형식과 일치
  - 마지막 발생 사용 (`charges = {}` 리셋) — 다중 출력 블록 안전 처리
  - 5열 이상 파싱, atom_num 1-based → 0-based 변환
  - ValueError/IndexError catch 후 섹션 종료
  - **주의사항**: xtb 버전 업데이트로 출력 형식이 변경될 경우 파서가 깨질 수 있음. 현재 xtb 6.x 기준으로는 정확함. 향후 xtb 버전 변경 시 재검증 권장.

---

#### 2. dept_export_integration — export_manager_enhanced.py (v3.0), error_handler.py

**2-A. PDF 6페이지 구조** — PASS
- `IntegratedPDFExporter` (line 285-) 확인
- 6페이지: 2D Structure / IR / NMR / UV-Vis / 3D Structure / Reaction
- `IntegratedPDFPageData` 데이터클래스 (line 275-282): page_title, page_type, image_path, peaks, description, available
- page_order = ["ir", "nmr", "uvvis", "structure_3d", "reaction"] (2D는 첫 페이지 title에 통합)
- 데이터 미존재 시 `_rl_placeholder_page()` 호출로 graceful degradation

**2-B. reportlab / QPrinter fallback** — PASS
- line 431-437: `REPORTLAB_AVAILABLE` → `_export_pdf_reportlab()`, 아니면 `PYQT_AVAILABLE` → `_export_pdf_qprinter()`, 둘 다 없으면 False 반환
- reportlab import (line 37-47): try/except로 `REPORTLAB_AVAILABLE` 플래그 설정
- QPrinter fallback (line 632-689): `QPrinter.PrinterMode.HighResolution`, A4, PdfFormat
- 한국어 폰트: Malgun > Gulim > Helvetica fallback (line 51-72)

**2-C. .chem v2 backward compatibility** — PASS
- `ChemFileManager` (line 104-257):
  - v2 포맷: `_chem_version`, `_metadata` 헤더 추가
  - `parse_load_data()`: `data.get("_chem_version", "1.0")` — 키 없으면 v1 취급
  - v1 파일 (atoms/bonds만 존재) → 정상 로드, metadata=None 반환
  - `get_metadata_from_file()`: 전체 로드 없이 메타데이터만 읽기 — 예외 시 None 반환
  - 직렬화: QPointF → [x,y], set → list 변환, Wedge/Dash 결합 처리

**2-D. Error handler subtypes** — PASS
- `error_handler.py` line 247-293: EXPORT 타입에 `pdf_reportlab`, `chem_save`, `chem_load` 서브타입 추가
- 키워드 매칭 (line 324-329): `"reportlab"`, `".chem" + "save"`, `".chem" + "load"` — exc_str.lower() 기반
- **주의사항**: 키워드 매칭은 예외 메시지 내용에 의존하므로, 예외 생성 시 해당 키워드가 포함되지 않으면 default 메시지로 폴백됨. 현재로서는 합리적인 구현.

---

#### 3. dept_testing_build — test_integration.py (v2.0), spec files

**3-A. 10개 대표 분자 테스트 커버리지** — PASS
- MOLECULES 리스트 (line 106-118): benzene, aspirin, caffeine, ethanol, glucose, pyridine, naphthalene, norbornane, acetone, tropylium
- 대표성: 방향족(3), 다관능기(aspirin, caffeine), 당류(glucose), 이온(tropylium), 지방족(ethanol, acetone, norbornane)
- 테스트 케이스 4개 클래스, 7+ subTest 기반 검증:
  - TestSMILESParse: 파싱 + 원자/결합 수 검증
  - TestFormulaAndMW: 분자식 + 분자량 범위 검증
  - TestAnalyzerIntegration: analyze() 반환값, 필수키, charges, aromatic 탐지
  - TestImportModules: 6개 코어 모듈 import 검증
- Carbon = `""` 규칙 준수 (line 70)

**3-B. Hidden imports 완전성** — PASS
- `tools/ChemGrid.spec` + `tools/ChemDraw.spec` 모두 24개 hiddenimports 포함
- 포함 목록: rdkit(7개), scipy(2개), numpy, matplotlib(2개), PyQt6(6개), OpenGL(3개), networkx, requests
- `build_chemgrid.py` 기존 목록과 일치 확인됨 (context_note.md 기록)

**3-C. Headless 실행 (GUI 의존성 없음)** — PASS
- `smiles_to_chemgrid_data()` 함수가 RDKit만 사용, PyQt6 불필요
- `ChemicalAnalyzer` import는 `analyzer.py` 모듈 (GUI 의존 없음)
- unittest 프레임워크 사용, `exit=False`로 프로세스 종료 제어
- QWidget/QApplication 생성 없음 — 완전한 headless 실행

---

## 감사 요약

| 부서 | 항목 | 판정 | 비고 |
|------|------|------|------|
| dept_dft_orca | %plots block format | PASS | ORCA 6.1.1 규격 준수 |
| dept_dft_orca | xtb subprocess safety | PASS | shell=False, timeout, cwd 격리 |
| dept_dft_orca | xtb graceful fallback | PASS | 빈 dict 반환, 3종 예외 처리 |
| dept_dft_orca | Mulliken parsing robustness | PASS | 5열 파싱, 0-based 변환. xtb 버전 변경 시 재검증 권장 |
| dept_export | PDF 6페이지 구조 | PASS | 정의된 구조와 일치 |
| dept_export | reportlab/QPrinter fallback | PASS | 이중 폴백 체인 구현 완료 |
| dept_export | .chem v2 하위 호환 | PASS | v1 파일 투명 로드 |
| dept_export | error_handler subtypes | PASS | 키워드 매칭 방식, 합리적 구현 |
| dept_testing | 10분자 테스트 커버리지 | PASS | 다양한 분자 유형 대표 |
| dept_testing | Hidden imports 완전성 | PASS | 24개 항목, 양 spec 파일 일치 |
| dept_testing | Headless 실행 | PASS | GUI 의존성 없음 확인 |

**전체 판정: ALL PASS (11/11)**

권고사항 (비차단):
1. xtb Mulliken 파서는 xtb 메이저 버전 업그레이드 시 출력 형식 변경 가능성 있음 — 버전 체크 로직 추가 권장
2. error_handler의 키워드 매칭은 예외 메시지 내용 의존 — 커스텀 예외 클래스로 전환하면 더 안정적

## 이론값 참조 캐시
(웹 검색으로 확인한 이론값을 캐싱하여 재검증 시 활용)
