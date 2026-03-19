# 화학 엔진 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #5 완료

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED

### TASK-CHEM-C5-001: Pi conjugation 전이금속 제외 [P0] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `engine_core.py` (+ `_source/` 동기화)
- **변경**: TRANSITION_METALS frozenset (27종) + BFS 진입점/전파 양쪽에서 TM skip. 포르피린 18π 거시환 정확히 보존.
- **검증**: py_compile PASS, _source/ sync OK

### (Cascade #3 Wave 1)

### CHEM-R01: BOND_LENGTHS 재검증 + 확장 [P0] ✅
- **지시**: CRC Handbook 대조, 누락 결합 추가
- **하달일**: 2026-03-18 (Cascade #3)
- **완료일**: 2026-03-18
- **수정**: chem_data.py — 47→64 엔트리 (17개 신규: P, Si, B, Se계 결합)
- **R-CHEM**: PASS — 15개 핵심 결합 CRC ±0.01Å 이내

### CHEM-R02: 방향족 탐지 재검증 [P0] ✅
- **지시**: aromatic bond order=1 workaround 동작 확인
- **완료일**: 2026-03-18
- **결과**: 수정 불필요 — RDKit fallback (GetIsAromatic + rdkit_idx) 정상 동작
- **R-CHEM**: PASS

### CHEM-R03: Gasteiger TM 블렌딩 재검증 [P1] ✅
- **지시**: 60/40 비율 + 전이금속 skip 확인
- **완료일**: 2026-03-18
- **결과**: 수정 불필요 — analyzer.py line 171 정상, TM NaN 필터 정상
- **R-CHEM**: PASS

### CHEM-NEW-01: LogP/TPSA/RotatableBonds [NEW] ✅
- **지시**: CT 추가 기능 — 약물유사성 지표 함수 추가
- **완료일**: 2026-03-18
- **수정**: analyzer.py — calculate_logp(), calculate_tpsa(), calculate_rotatable_bonds()
- **R-CHEM**: PASS — aspirin LogP=1.31, TPSA=63.60, RotBonds=2 (RDKit 직접 호출과 일치)

### **SUBMIT 상태: 감사 대기 중**
- SUBMIT 보고서: context_note.md 참조
- 감사 대상: audit_rendering_qa + 전문감사 구조화학팀

## ⛔ BLOCKED
- BLOCKER-001 (기존): aromatic bonds order=1 → RDKit fallback 완화 (근본 수정 미완)

---

## (이전 Cascade #2 — 무효 처리됨, 아래는 기록용)

### TASK-CHEM-001: 결합 길이 Angstrom 변환 [P2] ✅ (무효)
### TASK-CHEM-002: 복잡 분자 분석 안정성 [P1] ✅ (무효)
### TASK-CHEM-003: Gasteiger 전하 정확성 [P1] ✅ (무효)
