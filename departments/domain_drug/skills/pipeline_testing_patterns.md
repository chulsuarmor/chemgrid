# Skill: Lead Optimizer Pipeline Testing Patterns

## 1. R_GROUP_LIBRARY SMILES 유효성
- `CF3`는 유효한 SMILES가 아님. `C(F)(F)F` 사용 필수.
- `NH`도 비표준. RDKit MolFromSmiles 실패함. 치환기 이름으로는 `[NH2]` 또는 `N` 사용.
- PRESET_GOALS.preferred_substituents에 사용된 문자열은 R_GROUP_LIBRARY 키와 매칭되어야 함. 매칭 안 되면 MolFromSmiles로 직접 파싱 시도 → 실패 시 skip.

## 2. 유도체 생성 안 되는 분자 유형
- **방향족 H 없고 + aliph CH3/CH2/CH 없는 분자**: Urea(NC(=O)N), 기타 매우 단순한 아미드/요소계
- **Morphine 등 복잡 폴리사이클릭**: SMILES 문자열 자체가 정확해야 함. PubChem canonical SMILES 사용 권장.
- **비유기 분자 (ferrocene 등)**: RDKit에서 금속 유기 화합물 파싱 제한적

## 3. 테스트 분자 선정 가이드 (50종 기준)
- 단순 방향족 6종, 의약품 10종, 천연물 8종, 헤테로사이클 10종, 신경전달물질 6종, 엣지케이스 10종
- 각 카테고리에서 최소 1개 이상 유도체 생성 성공 확인
- 6개 프리셋 목표 모두 커버

## 4. 성능 벤치마크 (2026-03-19 기준)
- 50분자 전체 실행: ~2초 (docking 시뮬 포함)
- 분자당 평균 변이체: ~26개
- Tier A 비율: 86% (43/50)
- 실패율: 4% (2/50, Morphine SMILES 오류 + Urea 구조적 한계)

## 5. Docking Score 시뮬레이션 주의
- 실제 AutoDock/ORCA 없이 테스트 시 `random.uniform(-8, -3)` 사용
- composite_rank의 dock_norm에 직접 영향 → Tier 분류에 랜덤 요소 존재
- 실제 GUI 환경에서는 도킹 시뮬레이션 모듈이 연결되어야 정확한 Tier 분류 가능

## 6. ADMET 검증 포인트
- Lipinski violations: MW>500, LogP>5, HBD>5, HBA>10 각각 체크
- BBB score: TPSA, LogP, MW, HBD 기반 0~1 점수
- Metabolic stability: SMARTS 기반 soft spot 탐지 + cLogP/MW/rotatable bonds 페널티
- 모든 점수는 RDKit 순수 계산 (외부 API 불필요)
