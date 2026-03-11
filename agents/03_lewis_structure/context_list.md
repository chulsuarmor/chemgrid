# 📋 🔬 루이스 구조 — Task List
## 최종 업데이트: 2026-03-01

- [x] layer_logic.py LewisRenderer 구조 분석
- [x] VSEPR H 배치 알고리즘 리팩토링 (v2.0 → v3.0 빈 공간 탐색)
- [x] 형식전하 렌더링 추가 (_render_formal_charges)
- [x] 전하 기반 수소 차단 로직 제거 (RDKit h_count 신뢰)
- [x] 고립전자쌍 렌더링 개선 (동적 gap 계산)
- [x] 디버그 print 제거 → logging 모듈 교체
- [x] LassoSelectionRenderer → lasso_selection.py 분리
- [x] 🔴 U5: 고리 내 이중결합 짧은 선이 고리 안쪽 향하도록 수정
  - [x] _find_ring_containing_bond() BFS 유틸 함수 구현
  - [x] _get_ring_center_direction() 고리 중심 방향 단위벡터 함수 구현
  - [x] LewisRenderer._render_bonds() perp 방향 고리 중심 정렬
  - [x] TheoryRenderer.render() perp 방향 고리 중심 정렬
  - [x] 검증: 벤젠/피리딘/사이클로프로판/비고리 5건 전부 통과
- [ ] 분자 5종 시각 테스트 통과 확인 (PyQt6 런타임 검증 대기)

### 블로커
- PyQt6 런타임 시각 검증은 Agent 10 통합 시 수행 예정
