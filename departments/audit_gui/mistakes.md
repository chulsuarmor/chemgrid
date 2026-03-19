# audit_gui Mistakes Log

## [2026-03-19] Cascade #8 감사 중 발견된 문제
- **상황:** Cascade #8 전수조사 GUI 감사 수행
- **발견 사항:** 이전 Cascade #7 enhanced_test에서 "50/50 PASS, 44/44 PASS" 보고했으나, DockingPopup과 ADMETPopup의 runtime crash는 ERR로 처리되어 PASS 카운트에 포함되지 않았음. 즉, 이전 감사도 같은 2건의 ERR이 있었으나 PASS 카운트에 혼동이 있을 수 있음.
- **올바른 방법:** ERR과 FAIL을 별도 카테고리로 명확히 분리하여 보고. ERR은 "테스트 자체가 실행되지 못한 것"이므로 PASS도 FAIL도 아닌 별도 집계 필요.
