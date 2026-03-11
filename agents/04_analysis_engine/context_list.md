# 📋 ⚗️ 화학 분석 엔진 — Task List
## 최종 업데이트: 2026-03-01 00:03

- [x] analyzer.py 함수 목록 및 책임 분석
- [x] generate_smiles() 리팩토링 (M4 중복 루프 제거)
- [x] RDKit fallback 강화 (RDKIT_AVAILABLE 가드 추가)
- [x] engine_core.py 정리 (타입힌트/독스트링/is_huckel 인자 순서 통일)
- [x] engine_physics.py 정리 (타입힌트/독스트링 추가)
- [x] engine_resonance.py 정리 (타입힌트/독스트링 추가)
- [x] **U4: Procrustes 정렬 구현** — 루이스/이론 변환 시 방향 보존
  - [x] `_align_to_original()` SVD 기반 Procrustes 메서드 추가
  - [x] `_compute_dynamic_scale()` numpy 미설치 fallback 메서드 추가
  - [x] generate_smiles() theory_data 생성에 Procrustes 적용 (고정 스케일 45.0 제거)
  - [x] numpy import (NUMPY_AVAILABLE fallback 가드 포함)
  - [x] ast.parse 4파일 전부 OK
- [x] **🧊 입체 구조(3D) Technical Notes 작성** — Agent 04↔06 인터페이스 문서화
  - [x] Wedge/Dash → Z축 좌표 할당 로직 문서화
  - [x] 좌표계 변환 (화면↔RDKit↔OpenGL) 정리
  - [x] CIP R/S 판정 + Chirality Audit 알고리즘 기록
  - [x] M3(Z=0) 문제 분석 및 해결 방안 3가지 제시
  - [x] chem_data.py 3D 물리 상수 vs popup_3d.py 상수 비교
  - [x] Phase 7 대비 확장 포인트 정리
- [x] **SMILES 10종 비교 검증** — conda 환경 런타임 검증 완료
  - [x] Procrustes 수학 테스트 6/6 PASS (90°회전, 45°+스케일, 평행이동, 거울상방지, edge case, fallback)
  - [x] SMILES 10종 전부 PASS (메탄, 에탄올, 에틸렌, 포름알데히드, 물, 암모니아, 벤젠, 아세트산, HCl, CO2)
  - [x] 벤젠 → `c1ccccc1` (방향족 정상 인식), 아세트산 → `CC(=O)O`, CO2 → `O=C=O`
- [x] **NMR 피크 예측 로직 강화** — Manager 긴급 지시 v3 완료
  - [x] engine_physics.py에 NMR_H_SHIFTS, NMR_C_SHIFTS 상수 테이블 추가
  - [x] engine_physics.py에 predict_nmr_shifts() 메서드 구현
  - [x] analyzer.py에서 analyze() 시 nmr_shifts 반환하도록 연동
  - [x] 벤젠(C6H6) 등 방향족 시료의 실제 값(H:7.36, C:128.5) 우선 반환 로직 적용

### 블로커
- ✅ ~~conda 환경 `chemgrid`에서 런타임 검증 필요~~ → **2026-03-01 완료**
- 🟡 실제 캔버스에서 벤젠/피리딘 시각 검증은 Agent 10 통합 테스트에서 확인 필요
