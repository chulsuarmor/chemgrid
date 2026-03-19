# 도킹 부서 기술 노트
> 최종 업데이트: 2026-03-18 | DOCK-003/DOCK-004 구현 완료

---

## [세션 3] DOCK-003 + DOCK-004: AI 해석 & Binding Site 시각화 (2026-03-18)

### 수정 파일

| 파일 | 변경 내용 | src/app/ | _source/ |
|------|----------|---------|---------|
| popup_docking.py | v1.1: AI 해석 탭(Tab 5) 추가, binding site cache, Gemini 연동 | OK | OK |
| docking_interaction_analyzer.py | `extract_binding_site_residues` 정적 메서드 추가 | OK | OK |
| docking_3d_viewer.py | v1.1: stick model 강화, H-bond role 색상, pocket highlight | OK | OK |

### 구현 상세

#### 1. Binding Site Residue 추출 (`docking_interaction_analyzer.py`)
- `InteractionAnalyzer.extract_binding_site_residues(receptor, pose, radius=5.0)`
- SpatialHash 기반 5A 반경 내 잔기 추출
- 각 잔기의 H-bond donor/acceptor 역할 판별
- 반환: `List[(res_name, res_id, chain, is_donor, is_acceptor)]`

#### 2. 3D Viewer 강화 (`docking_3d_viewer.py`)
- `set_data()` 확장: `binding_site_residues` 파라미터 추가
- Stick model: 잔기 내 heavy atom 간 1.7A 이내 결합 그리기
- H-bond role 색상:
  - Blue: donor only
  - Red: acceptor only
  - Purple: both donor and acceptor
  - Gray: neutral
- 포켓 하이라이트: 결합 부위 CA 원자 기반 translucent yellow 타원
- Info overlay에 잔기 수 + 역할 범례 추가
- halogen_bond 색상 추가 (Cyan)

#### 3. AI 해석 탭 (`popup_docking.py`)
- Tab 5 "AI 해석": 포즈 선택 → "AI 해석 실행" 버튼
- Gemini API 연동:
  - `google.generativeai` import (optional)
  - API key: `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` 환경변수
  - Model: gemini-2.0-flash
  - 프롬프트: 수용체 위치/기능, 결합 친화도 해석, 핵심 상호작용 분석, 포켓 특성, 최적화 제안
- Rule-based fallback:
  - 결합 강도 분류 (매우 강한/강한/보통/약한)
  - 상호작용 유형별 개수 테이블
  - 핵심 잔기 목록
  - 포켓 친수성/소수성 판단
- API 오류 시 자동 fallback 전환
- 의존성 상태에 Gemini 표시

### 검증

| 항목 | 결과 |
|------|------|
| py_compile popup_docking.py | PASS |
| py_compile docking_interaction_analyzer.py | PASS |
| py_compile docking_3d_viewer.py | PASS |
| _source/ 동기화 | 3/3 SYNC OK |

---

## [Cascade #3 Wave 4] P-DOCK + R-DOCK 상신 보고서 (2026-03-18)

### 수정파일

| 파일 | 변경 내용 | src/app/ | _source/ |
|------|----------|---------|---------|
| docking_interface.py | 변경 없음 (검수만) | OK | OK |
| docking_data.py | 변경 없음 (검수만) | OK | OK |
| docking_interaction_analyzer.py | 변경 없음 (검수만) | OK | OK |
| popup_docking.py | 변경 없음 (검수만) | OK | OK |
| popup_md.py | 변경 없음 (검수만) | OK | OK |

> 이번 세션은 코드 수정 없이 기존 코드의 품질 검증만 수행하였음.

### 기획자보고 (P-DOCK)

#### DOCK-R01: Vina 도킹 완성 검증 결과

1. **Vina 통합 구조**: 3단계 fallback (Python Vina > subprocess Vina > simulation) 정상 구현
2. **VINA_PATH 가드**: `is_file()` 기반 빈 문자열/dot 경로 차단 정상 (BUG-DOCK-001 해결 확인)
3. **Ligand prep**: RDKit ETKDGv3 + MMFF 최적화, PDBQT 변환 3-tier fallback (Meeko > OpenBabel > simple Gasteiger)
4. **Receptor prep**: PDB 파싱 정상, 물/이온 제거 로직 정상, binding site 자동 감지 (HETATM centroid + 10A padding)
5. **detect_binding_site**: tuple comprehension 정상 (BUG-DOCK-002 해결 확인)
6. **Simulation fallback**: 거리 기반 휴리스틱, heavy atom 수 비례 affinity, deterministic seed(42), 다중 포즈 생성, is_simulation=True 플래그
7. **Result parsing**: multi-model PDBQT 파싱 + Vina log 파싱 모두 정상
8. **Binding energy display**: 바 차트 + 포즈 테이블 + 요약 레이블 모두 정상 구현

#### DOCK-R02: 상호작용 분석 검증 결과

1. **H-bond**: 3.5A, explicit donor-acceptor pair validation, Carbon='' 규칙 준수 -- 화학적으로 정확
2. **Hydrophobic**: 4.0A, C-C proximity -- 정상
3. **Pi-stacking**: 5.5A centroid-centroid + Newell's method ring normal + face-to-face(<30deg)/T-shaped(>60deg) 각도 필터 -- 정확
4. **Salt bridge**: 4.0A, 잔기별 charged atom name 구체적 지정 (ARG NH1/NH2/NE, LYS NZ, ASP OD1/OD2, GLU OE1/OE2, HIS ND1/NE2) -- 정확
5. **Halogen bond**: 3.5A, F/Cl/Br/I to N/O/S -- 정확
6. **SpatialHash**: 5.5A cell, 인접 셀 동적 계산(`n_cells = ceil(radius/cell_size)`) -- 효율적
7. **Deduplication**: residue 단위 closest interaction 유지 -- 정상
8. **2D interaction map**: Circle + Ligand-centric 두 가지 모드 지원 -- 정상

#### 미해결 태스크

- DOCK-001-D~H: PDB 다운로드 + 시뮬레이션 모드 end-to-end 테스트 미수행 (GUI 실행 필요)
- DOCK-002-D~E: aspirin+COX-2 특정 잔기 상호작용 검증 미수행 (실제 PDB 데이터 필요)
- DOCK-003: Gemini AI 해석 세션 미착수

### 검수자판정 (R-DOCK)

**판정: PASS**

| 검증 항목 | 결과 | 상세 |
|----------|------|------|
| py_compile (5 files) | 5/5 PASS | src/app/ 전체 PASS |
| ast.parse (5 files) | 5/5 PASS | 구문 오류 없음 |
| _source/ 동기화 | 5/5 SYNC OK | diff -q 전체 일치 |
| SpatialHash 기능 | PASS | query(10.5,10,10, r=3.5) -> 2 atoms 정상 |
| ring normal 계산 | PASS | XY hexagon -> (0,0,1), 평행=0deg, 수직=90deg |
| angle_between_normals | PASS | 경계값 정상 |
| SIMULATION_MODE 플래그 | PASS | Vina 미설치 시 True 정상 |
| DOCKING_AVAILABLE 플래그 | PASS | RDKIT_AVAILABLE 기반 정상 |
| 타 부서 파일 수정 | NONE | 검수만 수행, 코드 수정 0건 |

**검증 방법**: py_compile + ast.parse + diff sync check + 단위 테스트 스크립트 실행

### 감사요청

- **audit_professional_pharmacology_docking** (약리도킹 전문감사)에 검수 결과 상신 요청
- 요청 사항: DOCK-001-D~H end-to-end 테스트는 GUI 실행 환경에서 수행 필요 (Vina 미설치 환경에서 시뮬레이션 모드로 파이프라인 테스트 가능 여부 확인 요청)

---

## 기술적 판단 기록

### [2026-03-18] 세션 2: 6개 버그 수정 + 2개 신규 기능 구현

#### 수정 파일 목록
| 파일 | 변경 내용 | src/app/ | _source/ |
|------|----------|---------|---------|
| docking_interface.py | BUG-001 + BUG-002 + simulation mode | OK | OK |
| docking_interaction_analyzer.py | BUG-003 + BUG-005 + BUG-006 + halogen bond | OK | OK |
| docking_data.py | is_simulation 필드 추가 | OK | OK |
| popup_docking.py | 변경 없음 (동기화만) | OK | OK |
| popup_md.py | 변경 없음 (동기화만) | OK | OK |

#### 버그 수정 상세

##### BUG-DOCK-001 [CRITICAL → FIXED]: VINA_PATH 빈 문자열 가드
- **수정**: `Path("")` → Windows에서 `Path(".")`로 변환되어 `exists()=True` 오판
- **해결**:
  1. `_vina_env` 문자열 검사 후 `is_file()` 사용
  2. `_vina_exe_available` 변수로 `str(VINA_PATH) != '' and str(VINA_PATH) != '.' and VINA_PATH.is_file()` 검사
  3. `DOCKING_AVAILABLE = RDKIT_AVAILABLE` (시뮬레이션 모드 포함)
  4. `SIMULATION_MODE = not VINA_AVAILABLE` 플래그 추가

##### BUG-DOCK-002 [HIGH → FIXED]: generator → tuple
- **수정**: `size = (max(s, 20.0) for s in size)` → `size = tuple(max(s, 20.0) for s in size)`
- **검증**: `(15, 25, 8)` → `(20.0, 25.0, 20.0)` 정상 변환 확인

##### BUG-DOCK-003 [HIGH → FIXED]: H-bond explicit donor-acceptor
- **수정 전**: 중첩 if/continue 조건문 (유지보수 어렵고 일부 유효 쌍 누락 가능)
- **수정 후**:
  ```
  lig_is_donor = lig_elem in HBOND_DONORS
  lig_is_acceptor = lig_elem in HBOND_ACCEPTORS
  valid_pair = (lig_is_donor and p_is_acceptor) or (lig_is_acceptor and p_is_donor)
  ```
- **탄소 규칙 준수**: `lig_elem in ('', 'C', 'H')` → skip (Carbon = '' 빈 문자열)

##### BUG-DOCK-004 [MEDIUM → FIXED]: _source/ 동기화
- popup_docking.py, docking_interaction_analyzer.py, docking_data.py 모두 _source/에 복사 완료

##### BUG-DOCK-005 [MEDIUM → FIXED]: O(n*m) → O(n) 공간 해싱
- `SpatialHash` 클래스 추가 (5.5A cell size)
- 3D 공간을 격자로 분할, 각 ligand 원자 주변 27개 인접 셀만 검색
- H-bond, hydrophobic, halogen bond 감지에 적용
- pi-stacking, salt bridge는 residue 단위 검색 유지 (원래 효율적)

##### BUG-DOCK-006 [LOW → FIXED]: pi-stacking angle validation
- `_compute_ring_normal()`: Newell's method로 링 평면 법선 벡터 계산
- `_angle_between_normals()`: 두 법선 벡터 간 각도 (0-90도)
- 검증: XY 평면 hexagon → 법선 = (0,0,1) ✓, 평행 각도 = 0° ✓, 수직 = 90° ✓
- Face-to-face: < 30° 허용, T-shaped: > 60° 허용, 30-60°: 거부

#### 신규 기능

##### Simulation Fallback Mode
- Vina 미설치 시 `_run_simulation_fallback()` 자동 호출
- 거리 기반 휴리스틱: 중원자 수에 비례한 대략적 binding affinity 추정
- 리간드 좌표를 binding site 중심으로 이동 + 작은 교란으로 다중 포즈 생성
- DockingResult.is_simulation = True 플래그로 실제 Vina 결과와 구분
- 파이프라인 테스트 목적으로만 사용 (실제 약물 설계에 사용 금지)

##### Halogen Bond Detection
- F, Cl, Br, I 원자가 N, O, S acceptor에 근접 시 감지
- 거리 기준: 3.5A
- 2D interaction diagram에 Cyan 점선으로 표시

### [2026-03-18] 세션 1: 전체 파이프라인 코드 분석 결과

#### 1. 의존성 현황
- **vina**: 미설치 (pip install vina 필요) → **시뮬레이션 모드로 완화**
- **meeko**: 미설치 (pip install meeko 필요)
- **openbabel**: 미설치
- **rdkit**: OK
- **requests**: OK
- **PyQt6**: OK
- **PyOpenGL (docking_3d_viewer)**: 미확인 (import시 DOCKING_3D_AVAILABLE 결정)

#### 2. Vina 미설치 시 대안 전략 (TASK-DOCK-001 핵심)

Vina Python 패키지(`pip install vina`)는 Windows에서 설치 어려움이 있을 수 있음.
대안:
1. **vina Python package**: `pip install vina` (우선 시도)
2. **AutoDock Vina 1.2.x 실행파일**: RCSB에서 다운로드 → VINA_PATH 환경변수 설정
3. **시뮬레이션 모드(Fallback)**: ✅ **구현 완료** — Vina 없이 파이프라인 테스트 가능

#### 3. 파일별 코드 품질 평가 (세션 2 업데이트)
| 파일 | py_compile | 구조 | 에러핸들링 | 동기화 |
|------|-----------|------|----------|-------|
| docking_data.py | OK | 우수 | N/A | OK |
| docking_interface.py | OK | 우수 (BUG-001,002 수정) | 양호 | OK |
| popup_docking.py | OK | 양호 | 양호 | OK |
| docking_interaction_analyzer.py | OK | 우수 (v2.0 리팩토링) | 양호 | OK |
| popup_md.py | OK | 미분석 | 미분석 | OK |

#### 4. R-DOCK 검증 결과 (세션 2)
- py_compile: 6/6 PASS (src/app + _source)
- ast.parse: 6/6 PASS
- BUG-001 논리 검증: `Path("")` → `exists()=True` 문제 확인, `is_file()` 기반 가드 정상 작동
- BUG-002 논리 검증: `(15.0, 25.0, 8.0)` → `(20.0, 25.0, 20.0)` 정상
- Spatial hash 검증: 생성 및 쿼리 정상
- Ring normal 검증: XY hexagon → (0,0,1) 정상, 각도 계산 정상
- chemgrid 환경 통합 테스트: RDKIT=True, DOCKING=True, SIMULATION=True, 상호작용 감지 정상

## 발견된 문제 / 블로커

### BLOCKER-1: Vina 미설치 (완화됨)
- `vina` Python 패키지가 chemgrid conda 환경에 없음
- **시뮬레이션 모드 구현으로 파이프라인 테스트 가능**
- 실제 도킹 스코어링은 Vina 설치 필요

## 다음 세션 작업 (DOCK-001 D~H)
1. PDB 다운로드 + 파싱 end-to-end 테스트 (RCSB API)
2. 시뮬레이션 모드로 aspirin + COX-2(5KIR) 파이프라인 테스트
3. popup_docking.py UI에서 시뮬레이션 모드 경고 배너 표시
4. TASK-DOCK-003 (Gemini AI 해석) 시작 준비

## 타 부서 요청 사항
(없음)
