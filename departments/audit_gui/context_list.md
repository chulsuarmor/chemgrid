# GUI 실행 감사팀 태스크 리스트
> 최종 업데이트: 2026-03-19

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED
- [x] Cascade #8 전수조사 GUI 감사 (2026-03-19)
  - py_compile: 67/67 PASS
  - test_visual_auto: 45/45 PASS, 2 ERR (DockingPopup, ADMETPopup)
  - test_visual_3d: 10/10 PASS, 1 ERR (DockingPopup same bug)
  - Popup imports: 7/7 PASS
  - Retrosynthesis: PASS (3 routes)
  - Lead Optimizer: PASS
  - ADMET: FAIL (MolecularFormula API error)
  - PDF: PASS (in-test), FAIL (standalone)
  - CT boundary: NO VIOLATION
  - 결과: CONDITIONAL PASS (P1 버그 2건 수정 필요)
  - 증거: `evidence/cascade8_gui_audit_20260319.md`
  - 스크린샷: `departments/archive/screenshots/visual_qa_20260319/` (45 PNG + PDF + HTML)

## ⛔ BLOCKED
- DockingPopup runtime crash (P1) - dept_docking 수정 필요
- ADMETPopup runtime crash (P1) - dept_alphafold_drug 수정 필요
