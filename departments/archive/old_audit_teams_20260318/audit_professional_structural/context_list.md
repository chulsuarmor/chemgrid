# 전문감사-구조화학 할일 목록
## 마지막 업데이트: 2026-03-18

---

## 완료된 감사

### Cascade #3 Wave 1 (2026-03-18)
- [x] dept_chem_engine: BOND_LENGTHS CRC 대조 (CONDITIONAL PASS — B-N, P-H 수정 권장)
- [x] dept_chem_engine: LogP/TPSA/RotBonds RDKit 래퍼 검증 (PASS)
- [x] dept_chem_engine: Gasteiger 60/40 블렌딩 검증 (PASS)
- [x] dept_rendering: draw_partial_charges 화학적 타당성 (PASS)
- [x] dept_rendering: Lewis 론쌍 정확성 (PASS)
- [x] dept_ui_canvas: ESP Theory 가드 확인 (PASS)
- [x] 전체: Carbon '' 규칙 준수 확인 (PASS)
- [x] 전체: 듀얼 코드베이스 동기화 확인 (PASS)
- [x] dept_ui_canvas: UC-003 동적 스케일 검증 (PASS)
- [x] dept_ui_canvas: UC-004 guaranteed fallback 검증 (PASS)

---

## 대기 중인 감사 요청
(없음)

---

## 후속 조치 필요 (dept_chem_engine 반환)
- [ ] P-H 결합 길이: 1.44 -> 1.42 수정 (chem_data.py line 112)
- [ ] B-N 결합 길이: single 1.42 -> 1.58, aromatic 1.44 추가 (chem_data.py line 129)
- [ ] context_note.md 결합 길이값 코드와 일치하도록 수정
