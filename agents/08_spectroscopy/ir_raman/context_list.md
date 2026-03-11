# 📋 🔴 IR/Raman 분광학 — Task List
## 최종 업데이트: 2026-02-28 23:56 / 중간관리자(08) 직접 수행

- [x] S1: `spectrum_analyzer.py` 하단 절대 경로 → `argparse` + `_SCRIPT_DIR` 기반 (🔴 최우선)
- [x] S3: `spectrum_analyzer.py` matplotlib `backend_qt5agg` → `backend_qtagg`
- [x] S9: `spectrum_analyzer.py` Raman scatter 스케일 불일치 수정 (정규화 적용, 2곳)
- [x] S5: 두 파일 `print()` → `logging` 교체 (spectrum_analyzer 7건 + popup_spectrum logging 추가)
- [x] S6: `popup_spectrum.py` import 구조 정비 (try relative/absolute import)
- [ ] BaseSpectrumPopup 상속 적용 → Phase 7에서 Agent 06 통합 시 수행

### 수행자
- 중간관리자(08)가 하위 에이전트 미착수로 인해 직접 패치 수행 (2026-02-28 23:55)
- AST 검증 완료 (conda chemgrid Python 3.12.12)
