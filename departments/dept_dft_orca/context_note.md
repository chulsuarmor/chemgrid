# DFT/ORCA 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 3 P-DFT + R-DFT 완료

## 기술적 판단 기록

### DFT-001: ORCA %plots cube 파일 생성 [P0] — 검증 완료
- `ORBITAL_PLOT_TEMPLATE` (line 210-226) 이미 올바른 `%plots` 블록 포함
- ORCA 6.1.1에는 `orca_plot` 유틸리티 없음 → 입력 파일 내 `%plots` 블록으로 직접 cube 생성
- 구조: `MOREAD + NOITER` → 기존 `.gbw` 파동함수 재사용, SCF 재계산 없이 빠른 cube 생성
- dim1/dim2/dim3 = 100 (고해상도), Format = Gaussian_Cube
- 생성 파일: homo.cube, lumo.cube, density.cube
- `generate_orbital_cubes()` 함수(line 974-1052)가 자동으로 HOMO/LUMO 인덱스 탐지 후 cube 생성
- `DFT_TEMPLATE`에는 `%plots` 미포함 (올바름) — 메인 계산과 cube 생성은 별도 단계로 분리

### DFT-002: xtb GFN2-xTB 연동 [P1] — 신규 구현 완료
- 7개 함수 추가:
  - `find_xtb_executable()` — 포터블 경로 탐색 (ORCA와 동일 패턴)
  - `validate_xtb_installation()` — 설치 확인
  - `_generate_xtb_xyz()` — ChemGrid atoms dict → XYZ 파일 변환 (pixel/40 = approx Angstrom)
  - `run_xtb_charges()` — GFN2-xTB 실행, `--gfn 2 --pop` 플래그로 Mulliken 전하 요청
  - `_parse_xtb_mulliken_charges()` — stdout에서 `#   Z ... q` 테이블 파싱, 0-based 인덱스 반환
  - `map_xtb_charges_to_2d()` — atom_index → 2D (x,y) key 매핑
  - `get_xtb_charges_for_molecule()` — 고수준 편의 함수 (run + map 통합)
- Graceful fallback: xtb 미설치 시 빈 dict 반환 (에러 없음)
- timeout: 60초 (GFN2-xTB는 수백 원자도 수초 내 완료)
- 차후 renderer.py ESP 렌더링에서 Gasteiger 대신 xtb 전하 사용 가능

## 발견된 문제 / 블로커
- `orca_output_parser.py` 파일이 별도로 존재하지 않음 — 파싱 로직은 `orca_interface.py` 내 `OrcaOutputParser` 클래스에 통합됨
- `dft_visualizer.py` 파일 미존재 — 시각화는 `renderer.py` (dept_rendering 소유)에서 담당
- xtb 바이너리가 프로젝트에 포함되어 있지 않음 → 사용자가 별도 설치 필요 (https://github.com/grimme-lab/xtb)

## 타 부서 요청 사항
- **dept_rendering**: `get_xtb_charges_for_molecule()` 함수를 ESP 렌더링에서 Gasteiger fallback 대신 사용 가능. `renderer.py`에서 import 후 `xtb_charges = get_xtb_charges_for_molecule(atoms, charge)` 호출, 빈 dict이면 기존 Gasteiger 사용.
- **dept_3d_viewer**: `generate_orbital_cubes()` 함수로 HOMO/LUMO cube 파일 생성 후 3D isosurface 렌더링에 활용 가능.
