# 테스팅/빌드 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 3

## 기술적 판단 기록

### TEST-001: 통합 테스트 스위트 (2026-03-18)
- **설계 판단:** headless 테스트를 위해 RDKit로 SMILES -> atoms/bonds 변환 함수(`smiles_to_chemgrid_data`)를 자체 구현. `_draw_smiles_on_canvas`의 핵심 로직을 GUI 의존성 없이 재현.
- **탄소 규칙:** Carbon은 `""` (빈 문자열)로 저장. `"C"` 아님 -- ChemGrid 프로젝트 규칙.
- **tropylium 공식:** RDKit `CalcMolFormula`는 이온에 대해 `C7H7+` 형태 반환 (charge 포함).
- **테스트 커버리지:** 10개 대표 분자, 7개 테스트 케이스 (unittest.subTest 활용):
  - SMILES 파싱 검증, 분자식/분자량 검증, analyze() 반환값 구조 검증, 전하 데이터 검증, 방향족 탐지 검증, 코어 모듈 import 검증
- **실행 시간:** ~0.26초 (전체 스위트)

### TEST-002: PyInstaller 빌드 검증 (2026-03-18)
- **발견:** `tools/ChemGrid.spec`와 `tools/ChemDraw.spec` 모두 `hiddenimports=[]` (빈 리스트)였음.
- **조치:** `src/app/build_chemgrid.py`의 hidden imports 목록을 기반으로 24개 항목 추가:
  rdkit, scipy, numpy, matplotlib, PyQt6 (6개 서브모듈), OpenGL (3개), networkx, requests
- **참고:** `src/app/build_chemgrid.py`는 이미 올바른 hidden imports를 포함하고 있었으나, spec 파일은 업데이트되지 않은 상태였음.

## 발견된 문제 / 블로커
- 없음. 모든 테스트 PASS.

## 타 부서 요청 사항
- 없음.
