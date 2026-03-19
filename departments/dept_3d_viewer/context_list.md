# 3D 뷰어/궤도함수 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #5 완료

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED (Cascade #6)

### TASK-3D-C6-001: Pi 오비탈 방향 수정 — sp2 평면 수직 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `popup_3d.py` (+ `_source/` 동기화)
- **변경**: 전역 SVD normal → 원자별 `_calc_local_normal()` (이웃 결합 벡터 cross product). `_calc_ring_normal()` Newell's method.
- **검증**: py_compile PASS, _source/ sync OK

### TASK-3D-C6-002: 오비탈 시각화 개구리알→등치면 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `popup_3d.py`, `cube_parser.py` (+ `_source/` 동기화)
- **변경**: 테셀레이션 16→32 슬라이스, Phong material, scikit-image marching cubes 설치, pure-numpy MC fallback (`_numpy_marching_cubes()`), 3-tier fallback chain
- **검증**: py_compile PASS, scikit-image 0.26.0 + scipy 1.17.1 설치됨

### TASK-3D-C6-003: 진동 모드 IR/Raman + 확대 뷰 [P1] ✅
- **완료일**: 2026-03-18
- **수정 파일**: `popup_3d.py` (+ `_source/` 동기화)
- **변경**: 진동 디테일 패널 (IR/Raman 활성도, 주파수, 파장영역), `_zoom_viewer_to_atoms()` 자동 확대
- **검증**: py_compile PASS, _source/ sync OK

## ✅ COMPLETED

### TASK-3D-C5-001: 3D 배위결합 범용 감지/렌더링 [P0] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `popup_3d.py` (+ `_source/` 동기화)
- **변경**: `_detect_coordination_bonds()` — TM 27종 + 리간드 도너 6종(N,O,P,S,As,Se) + 카보닐 CO/CN. RDKit DATIVE bond type 감지. 3D 대시 실린더.
- **검증**: py_compile PASS, _source/ sync OK

### Cascade #3 Wave 2: 3D-R01 오비탈 시각화 개선 ✅
- **완료일**: 2026-03-18
- **수정 파일**: popup_molorbital.py
- **변경 내용**:
  - [FIX-3D-007v2] Colormap을 화학 표준으로 통일: 모든 오비탈에서 +phase=Blues, -phase=Reds
  - `_interpolate_amplitude_at_points()` 정적 메서드 추가: scipy trilinear 보간으로 face centroid에서 실제 orbital amplitude 샘플링
  - `_compute_gradient_colors()` 개선: amplitude 보간 우선, scipy 미설치 시 거리 기반 fallback
- **검증**: py_compile PASS, ast.parse PASS
- **듀얼 동기화**: `_source/popup_molorbital.py` 동기화 완료

### Cascade #3 Wave 2: 3D-R02 진동 애니메이션 검증 ✅
- **완료일**: 2026-03-18
- **수정 파일**: (없음 - 수정 불필요)
- **검증 결과**:
  - start_vibration/stop_vibration/_vib_tick: 3개 뷰어 클래스 모두 정상
  - displacement vectors 연결: vibration_engine -> VibrationPanel -> viewer 체인 정상
  - bond strain 색상 코딩: OpenGL/QPainter 양쪽 정상
  - 타이머 33fps, sin wave 진동 정상
  - 인덱스 안전 가드 일관 적용 확인

### TASK-3D-007: 오비탈 시각화 gradient isosurface ✅
- **완료일**: 2026-03-18 (v1), 업그레이드: 2026-03-18 (v2)
- **수정 파일**: popup_molorbital.py
- **변경 내용**:
  - v1: `_compute_gradient_colors()` 메서드 추가 (거리 기반 gradient)
  - v2: amplitude 보간 + 표준 colormap 적용
- **검증**: py_compile PASS, ast.parse PASS
- **듀얼 동기화**: `_source/popup_molorbital.py` 동기화 완료

### TASK-3D-005: 진동 모드 bond stretching 시각화 ✅
- **완료일**: 2026-03-18
- **수정 파일**: popup_3d.py
- **변경 내용**:
  - BallStickRenderer.render(): 진동 중 결합 길이 변화(strain) 계산 -> 색상 코딩
    - 신장(stretched): 회색->빨강 그라데이션 (strain_t > 0.02)
    - 압축(compressed): 회색->파랑 그라데이션 (strain_t < -0.02)
    - 평형: 기본 회색
  - QPainter fallback (Viewer3DFallback.paintEvent): 동일한 bond strain 색상 코딩 적용
- **검증**: py_compile PASS, ast.parse PASS
- **듀얼 동기화**: `_source/popup_3d.py` 동기화 완료

### TASK-3D-006: 복잡 분자 3D 렌더링 안정성 ✅
- **완료일**: 2026-03-18
- **수정 파일**: popup_3d.py
- **변경 내용**:
  - `_fix_metallocene_geometry()` 함수 추가
  - `_dashed_bond()` 메서드 추가: 배위 결합 점선 실린더 렌더링
  - `generate_3d_full_from_smiles()`: 메탈로센 후처리 호출
- **검증**: py_compile PASS, ast.parse PASS
- **듀얼 동기화**: `_source/popup_3d.py` 동기화 완료

### TASK-3D-001: O(n^2) bond detection -> spatial hash 최적화 ✅
- `popup_3d.py` _precompute_ligand_bonds(): cell_size=3.5A 공간 해시 도입
- `_cached_ligand_bonds` + `_ligand_bonds_dirty` 플래그로 1회 계산 후 캐싱

### TASK-3D-002: gluNewQuadric 캐싱 ✅
- `__init__`: `self._protein_quadric = None` 1회 생성
- `_draw_protein_impl()`: 캐시된 quadric 재사용

### TASK-3D-003: 거대분자 size guard ✅
- `_draw_protein()` 3단계 가드: >5000(skip) / >1000(backbone_simple) / >300(ribbon_only) / <=300(full)

### TASK-3D-004: secondary structure 인덱싱 수정 ✅
- `_detect_secondary_structure()`: 6곳 bounds checking 추가

## ⛔ BLOCKED
(없음)
