# AutoDock Vina 통합 가이드

## 35+ 단백질 타겟 DB
docking_interface.py에 내장된 타겟 목록.
RCSB PDB REST API로 실시간 검색 가능.

## Vina Scoring v8.7
- 결합 에너지 (kcal/mol)
- 상호작용 분석: H-bond, π-stacking, hydrophobic
- docking_interaction_analyzer.py에서 분석

## 실행 흐름
1. 리간드 SMILES → 3D 좌표 생성
2. PDB에서 수용체 다운로드
3. Vina 실행 → 결합 포즈 + 에너지
4. 상호작용 분석 → 시각화

## popup_md.py
분자동역학 시뮬레이션 시각화 (실험적).
