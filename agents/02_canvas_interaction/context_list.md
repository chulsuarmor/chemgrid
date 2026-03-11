# 📋 🖱️ 캔버스/그리기 — Task List
## 최종 업데이트: 2026-03-01 01:21

- [x] MoleculeCanvas 클래스 구조 분석
- [x] MoleculeCanvas → canvas.py 분리
- [x] [M1] 조준선 3중 렌더링 버그 수정 → 최상위 Z-INDEX 1회만 호출
- [x] [M2] paintEvent 내부 디버그 print() 전부 제거
- [x] [C3] self.canvas.repaint() → self.update() 수정
- [x] [C4] verification_report except 블록 Orbital 메시지 혼입 분리
- [x] [C5] _analyze_dft_electron_density() 하드코딩 절대 경로 → __file__ 기반 상대 경로
- [x] draw.py에 `from canvas import MoleculeCanvas, CanvasMode, get_coord_key` 추가
- [x] canvas.py + draw.py ast.parse 구문 검증 통과
- [x] draw.py 내 _OBSOLETE dead code 완전 제거 (46,890자 삭제)
- [x] [U5] draw_bond() 고리 이중결합 안쪽 방향 수정 — coord_utils.py에 고리 감지 BFS 구현, canvas.py 적용
- [x] 🧊 입체 구조(3D) 연동 Technical Notes 작성 — 데이터 플로우, 좌표 인터페이스 규약, U2/U3 문제점 문서화
- [x] [Phase 6-3 명령 1] Theory 모드 선택 분자에 점선 테두리(DashLine + RoundedRect) 표시
- [x] [Phase 6-3 명령 2] 선택 분자 아래 IUPAC명/관용명 표시 (PubChem REST API + RDKit SMILES 폴백)
- [x] [Phase 6-3 명령 3] 바닥 클릭 시 선택 해제 + molecule_selected pyqtSignal(bool) 시그널 추가
- [x] [v4 명령1] +/- 기호 → atoms["charge"] 별도 필드 분리 (main 원소 보존, 위첨자 렌더링)
- [x] [v4 명령3] 반응 화살표 도구 (Arrow) — 4방향 스냅, 고스트(파란색 점선), 모든 레이어에서 표시, 화살촉 삼각형
- [x] [v4 명령4] 텍스트 상자 도구 (Text) — 클릭 생성/편집, 아래첨자 변환(CH_3→CH₃), T모드 전용 표시, 빨간 점선 테두리
- [x] [v4 명령5] 비공유전자쌍 user_lp 플래그 추가 (atoms[k]["user_lp"] = set of directions)
- [x] Undo/Redo에 arrows, text_boxes 포함
- [x] Eraser에 arrows, text_boxes 삭제 추가
- [x] 전체 AST 구문 검증 통과
- [ ] Undo/Redo 시스템 모듈화 (Phase 7 대기)
- [ ] coord_utils.py 개선 (Phase 7 대기)

### 블로커
- (없음)
