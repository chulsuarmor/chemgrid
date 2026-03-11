# 📝 ⚛️ ORCA DFT — Technical Notes
## 기술적 판단 및 결정 기록

### [2026-02-28] v3.00 리팩토링 결정 사항

#### 1. 포터블 경로 시스템 (C1 + C5 수정)
- **문제:** `ORCA_PATH = Path(r"C:\Users\김남헌\Desktop\organicdraw\Orca.6.1.1")` 하드코딩
- **해결:** `find_orca_executable()` 함수 — 7개 후보 경로 순차 탐색
  - `_SCRIPT_DIR / Orca.6.1.1 / orca.exe`
  - `_SCRIPT_DIR / Orca.6.1.1 / Orca6.1.1.Win64.exe`
  - 상위 디렉토리 2단계까지 탐색
  - 최종 폴백: `shutil.which("orca")` (시스템 PATH)
- **캐싱:** `_orca_exe_cache` 전역 변수로 lazy 초기화 (최초 1회만 탐색)

#### 2. 3단계 클래스 분리
- **OrcaInputGenerator:** DFT_TEMPLATE 기반 .inp 파일 생성
- **OrcaExecutor:** subprocess.run + timeout + cwd 지정 (os.chdir 제거!)
- **OrcaOutputParser:** 정적 메서드 기반 섹션별 독립 파싱
  - `_parse_geometry()`, `_parse_mulliken()`, `_parse_lowdin()`
  - `_parse_energy()`, `_parse_convergence()`, `_parse_bond_orders()`
  - `_parse_atom_symbols()`, `_build_densities()`
- **OrcaCalculatorThread:** 3개 스테이지를 조합하는 QThread

#### 3. os.chdir() 제거
- **문제:** 원본 코드에서 `os.chdir(self.work_dir)` 사용 → 프로세스 전체 cwd 변경
- **해결:** `subprocess.run(cwd=str(work_dir))` 파라미터로 대체
- **이유:** os.chdir은 멀티스레드 환경에서 race condition 유발

#### 4. 커스텀 예외 체계
- `OrcaError` (기반)
  - `OrcaNotFoundError`: ORCA 실행 파일 미발견
  - `OrcaExecutionError`: 비정상 종료 코드
  - `OrcaTimeoutError`: 타임아웃 초과
  - `OrcaConvergenceError`: 수렴 실패 (미래 사용)
  - `OrcaParseError`: 출력 파일 파싱 실패

#### 5. 하위 호환성
- `generate_orca_input()`, `create_calculation_workflow()`, `parse_gbw_file()` 등
  기존 함수 시그니처 유지 → 내부적으로 새 클래스 위임
- `extract_atom_symbols()`, `extract_bond_orders()`, `validate_orca_installation()` 동일

#### 6. OrcaCalculationResult 개선
- `field(default_factory=dict)` 사용 → mutable default 안전
- `atom_symbols` 필드 추가 (파서에서 직접 심볼 추출)

#### 7. electron_density_analyzer.py 변경점
- 모든 `print()` → `logging.getLogger("electron_density_analyzer")` 교체
- `import json` 모듈 레벨로 이동 (기존: export 함수 내부 import)
- 불필요한 중복 주석 제거, 코드 간결화
- 모든 기능(Epsilon tolerance, Strict Column Check, Mulliken-first) 보존
