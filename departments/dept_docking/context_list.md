# 도킹 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 4 — P-DOCK/R-DOCK 검수 완료

## 🔴 PENDING

### TASK-DOCK-001: 도킹 팝업 안정성 [P1]
- **지시**: popup_docking.py에서 PDB 검색/다운로드 → Vina 도킹 → 결과 표시 전체 파이프라인 안정화
- **관련 파일**: popup_docking.py, docking_interface.py
- **검증**: aspirin+COX-2(PDB:5KIR), ibuprofen+COX-2, caffeine+A2A(PDB:5MZP) 도킹 성공
- **하달일**: 2026-03-18
- **P-DOCK 세부 계획**:
  - [x] **DOCK-001-A**: BUG-DOCK-001 수정 — VINA_PATH 빈 문자열 가드 (`is_file()` 사용)
  - [x] **DOCK-001-B**: Vina 미설치 시 Fallback 시뮬레이션 모드 구현 (`_run_simulation_fallback`)
  - [x] **DOCK-001-C**: BUG-DOCK-002 수정 — `detect_binding_site` generator → tuple comprehension
  - [ ] **DOCK-001-D**: PDB 다운로드 → 파싱 → 리간드 3D 생성 → 결합부위 감지 단계별 테스트
  - [ ] **DOCK-001-E**: Vina 도킹 실행 → 결과 파싱 → UI 표시 end-to-end 테스트
  - [ ] **DOCK-001-F**: aspirin(CC(=O)Oc1ccccc1C(=O)O) + COX-2(5KIR) 검증
  - [ ] **DOCK-001-G**: ibuprofen(CC(C)Cc1ccc(CC(C)C(=O)O)cc1) + COX-2(5KIR) 검증
  - [ ] **DOCK-001-H**: caffeine(Cn1c(=O)c2[nH]cnc2n(C)c1=O) + A2A(5MZP) 검증
  - [x] **DOCK-001-I**: _source/ 동기화 (docking_interface.py, docking_data.py)

### TASK-DOCK-002: 상호작용 분석 개선 [P1]
- **지시**: docking_interaction_analyzer.py에서 H-bond, hydrophobic, pi-stacking 감지 정확도 향상
- **관련 파일**: docking_interaction_analyzer.py
- **검증**: aspirin+COX-2에서 Arg120 H-bond, Tyr385 상호작용 감지
- **하달일**: 2026-03-18
- **P-DOCK 세부 계획**:
  - [x] **DOCK-002-A**: BUG-DOCK-003 — H-bond 감지 조건 리팩토링 (명시적 donor-acceptor 쌍)
  - [x] **DOCK-002-B**: BUG-DOCK-005 — 공간 해싱 도입 (5.5A 그리드 기반 근접 원자 필터)
  - [x] **DOCK-002-C**: BUG-DOCK-006 — pi-stacking 각도 검증 추가 (ring normal vector + Newell method)
  - [ ] **DOCK-002-D**: aspirin+COX-2(5KIR) 도킹 후 Arg120 H-bond 감지 확인
  - [ ] **DOCK-002-E**: Tyr385 상호작용 감지 확인
  - [x] **DOCK-002-F**: Halogen bond 감지 추가 (F/Cl/Br/I → N/O/S acceptor)
  - [x] **DOCK-002-G**: _source/ 동기화 (docking_interaction_analyzer.py)

### TASK-DOCK-003: Vina AI 해석 세션 추가 [P2] → ✅ DONE
- **지시**: 도킹 결과를 Gemini API로 해석하여 결합 친화도, 핵심 상호작용, 최적화 제안 생성
- **관련 파일**: popup_docking.py, docking_interaction_analyzer.py, docking_3d_viewer.py
- **하달일**: 2026-03-18
- **P-DOCK 세부 계획**:
  - [x] **DOCK-003-A**: Binding site residue 추출 메서드 (`extract_binding_site_residues`) — 5A 반경
  - [x] **DOCK-003-B**: 3D 뷰어 binding site 강화 — stick model + H-bond donor/acceptor 색상 + 포켓 하이라이트
  - [x] **DOCK-003-C**: AI 해석 탭 (Tab 5) 추가 — Gemini 2.0 Flash API 연동
  - [x] **DOCK-003-D**: Rule-based fallback 해석 (API 미연결 시)
  - [x] **DOCK-003-E**: _source/ 동기화 (3파일)
  - [x] **DOCK-003-F**: py_compile 3/3 PASS

### TASK-DOCK-004: Binding site 시각화 추가 [P2] → ✅ DONE (DOCK-003과 통합)
- **지시**: 수용체의 binding site 잔기만 stick model로 3D 뷰에 표시, H-bond donor/acceptor 색 구분
- **관련 파일**: docking_3d_viewer.py, docking_interaction_analyzer.py, popup_docking.py
- **완료**: DOCK-003과 함께 구현됨

### TASK-DOCK-005: drug_screening ↔ docking 데이터 호환 [P1] → ✅ DONE — Cascade #4 Wave 2
- **완료일**: 2026-03-18
- **수정 파일**: docking_data.py (to_screening_scores()), docking_interface.py (docking_result_to_screening_scores())
- **변경**: DockingResult → DockingScore 변환 브릿지. affinity_kcal→binding_affinity, rmsd_lb→pose_rmsd 매핑.
- **검증**: py_compile 3/3 PASS, _source/ sync OK

### TASK-DOCK-006: halogen bond 각도 적용 [P2] → ✅ DONE — Cascade #4 Wave 2
- **완료일**: 2026-03-18
- **수정 파일**: docking_interaction_analyzer.py
- **변경**: _detect_halogen_bonds에 C-X...Acceptor 각도 검증 (120-180°) 추가. _find_bonded_carbon() + _angle_three_points() 헬퍼. Carbon='' 규칙 준수.
- **검증**: py_compile PASS, _source/ sync OK

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED (Cascade #6)

### TASK-DOCK-C6-001: 수용체 정보 패널 + 상호작용 해석 [P0] ✅
- **완료일**: 2026-03-18
- **수정 파일**: popup_docking.py, docking_data.py, docking_3d_viewer.py, docking_interaction_analyzer.py (+ _source/)
- **변경**: ReceptorMetadata + RECEPTOR_DATABASE 8타겟, 수용체 정보/상호작용 해석 패널, 색상코딩
- **검증**: py_compile 4/4 PASS, _source/ sync OK

## ✅ COMPLETED (이전)

### [Cascade #3 Wave 4] P-DOCK + R-DOCK 코드 검수 완료 (2026-03-18)
- DOCK-R01: Vina 도킹 통합 검증 — 3단계 fallback, simulation mode, result parsing 모두 PASS
- DOCK-R02: 상호작용 분석 검증 — H-bond(3.5A), hydrophobic(4.0A), pi-stacking(5.5A), salt bridge(4.0A), halogen bond(3.5A) 거리 기준 화학적 정확성 확인
- R-DOCK: py_compile 5/5 PASS, ast.parse 5/5 PASS, _source/ 5/5 SYNC OK
- R-DOCK: SpatialHash, ring normal, angle validation 단위 테스트 PASS
- 코드 수정 0건 (검수만 수행)

### [세션 2] 코드 버그 수정 완료 (2026-03-18)
- BUG-DOCK-001: VINA_PATH 빈 문자열 가드 → `is_file()` 사용 + 시뮬레이션 모드
- BUG-DOCK-002: generator → tuple comprehension
- BUG-DOCK-003: H-bond explicit donor-acceptor pairs
- BUG-DOCK-004: _source/ 동기화 (popup_docking.py, docking_interaction_analyzer.py 복사)
- BUG-DOCK-005: 공간 해싱 SpatialHash 클래스 (O(n) proximity)
- BUG-DOCK-006: pi-stacking ring normal vector angle validation (Newell method)
- NEW: Halogen bond detection 추가
- NEW: Simulation fallback mode 추가 (Vina 없이 파이프라인 테스트 가능)

## ⛔ BLOCKED

### BLOCKER: Vina 미설치 (완화됨)
- chemgrid conda 환경에 `vina` Python 패키지 없음
- **완화**: 시뮬레이션 모드 구현으로 파이프라인 테스트 가능
- **영향**: DOCK-001-E~H 테스트는 시뮬레이션 모드로 부분 검증 가능
- **완전 해결 필요**: `pip install vina` 또는 실행파일 경로 설정
