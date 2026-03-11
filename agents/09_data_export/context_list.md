# 📋 📦 데이터/내보내기 — Task List
## 최종 업데이트: 2026-02-28

### ✅ 완료
- [x] 9개 모듈 구조 분석
- [x] 중복 기능 식별 (CalculationEntry 2중 정의)
- [x] 모듈 간 의존성 맵 작성
- [x] 포터블 경로 위반 3건 식별
- [x] spectrum_pdf_exporter QListWidgetItem 버그 식별

### ⏸️ 대기 (Phase 6-1B 리팩토링 시 진행)
- [ ] `CalculationEntry` 클래스 통합 (calculation_logger + history_manager)
- [ ] 포터블 경로 시스템 적용 (error_handler, history_manager, calculation_logger)
- [ ] spectrum_pdf_exporter QListWidgetItem 버그 수정
- [ ] 공통 API 인터페이스 설계
- [ ] error_handler.py 에러 처리 통일
- [ ] draw.py 통합 인터페이스 설계 (Agent 01 리팩토링 이후)
- [ ] 내보내기 기능 E2E 검증

### 블로커
- Agent 01/02 리팩토링 미완료 (draw.py 분리 이후 통합 가능)
- Agent 08 분광학 모듈 리팩토링 미완료 (스펙트럼 데이터 인터페이스 확정 이후 PDF 내보내기 연동)
