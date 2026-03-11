# 📋 🌈 렌더링 엔진 — Task List
## 최종 업데이트: 2026-03-01 01:18

### Phase 6-1A (완료)
- [x] renderer.py 구조 분석
- [x] 디버그 print 전면 제거 → logging 교체 (15개 print → 0개)
- [x] draw_clouds() 200줄 → 오케스트레이터 + 8개 헬퍼 메서드 분리
- [x] DFTDensityRenderer → CloudRenderer 통합 (하위 호환 별칭 유지)
- [x] QPen import 누락 버그 수정
- [x] 자가 검증 (AST parse OK, API 호환성 OK)

### Phase 6-2 U7 긴급 수정 (완료)
- [x] draw_clouds() painter.save()/restore() 추가 — 전자구름 색상 누출 방지
- [x] _render_atom_clouds() 방어적 save/restore 래퍼 추가 (_render_atom_clouds_inner 분리)
- [x] ELEMENT_COLORS CPK 표준 색상 테이블 추가 (20개 원소)
- [x] get_element_color() 공용 함수 추가 (Agent 03/02에서 import 가능)
- [x] 최종 검증: AST OK, save/restore 6:6 BALANCED, ELEMENT_COLORS+get_element_color 존재 확인

### Phase 6-3 긴급 명령 (완료)
- [x] 명령 1: 공명구조 전자구름 균등화 — 고리 원자 전하 평균화 (rings/aromatic → avg_charge)
- [x] 명령 2: 사용자 비공유전자쌍(user_lp/LP) 전자구름 제외
- [x] charges dict 복사로 원본 데이터 오염 방지
- [x] 자가 검증: AST OK, save/restore 6:6 BALANCED, 신규 로직 전항목 FOUND

### Phase 6-4 (R1 논리 구축 및 준비 완료)
- [x] R1 독자적 렌더링 논리 체계 구축 (r1_gemini_commands.md)
- [x] Gemini API 연동 명령 템플릿 설계
- [x] 전자구름/ESP 맵 통합 및 최적화 준비 완료
- [x] 전 파일 (renderer.py, layer_logic.py, coord_utils.py) AST 검증 완료

### 협업 대기
- [x] Agent 03: layer_logic.py에서 `from renderer import get_element_color` 사용 가능 알림
- [x] Agent 02: draw.py draw_atom_group에서 `from renderer import get_element_color` 사용 가능 알림
