# 렌더링/시각화 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #5 완료

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED

### TASK-RENDER-C5-001: Lewis/Theory 배위결합 렌더링 [P1] ✅ — Cascade #5
- **완료일**: 2026-03-18
- **수정 파일**: `layer_logic.py` (+ `_source/` 동기화)
- **변경**: LewisRenderer + TheoryRenderer에 order==0.5 배위결합 대시선+화살표 렌더링 브랜치 추가
- **검증**: py_compile PASS, _source/ sync OK

### (Bug Fix 2026-03-18)

### RENDER-BUG-01: ESP 전자구름 Lewis/Drawing 모드 미표시 [P0] ✅
- **지시**: 전자구름 토글 켜진 상태에서 Lewis/Drawing 레이어에서도 ESP 표시
- **완료일**: 2026-03-18
- **수정**: canvas.py 3개소 — `self.view_state == "Theory"` 조건 제거 (LAYER 2/3/4)
- **비고**: canvas.py는 dept_ui_canvas 소유이나 사용자 직접 지시로 수정

### RENDER-BUG-02: Theory 모드 -OH가 "O"로만 표시 [P0] ✅
- **지시**: 말단 수산기(-OH) 등 헤테로원자의 암묵적 수소를 Theory 모드에서 표시
- **완료일**: 2026-03-18
- **수정**: layer_logic.py TheoryRenderer — STAGE 2 원자기호에 implicit H 표시 (OH, NH2 등), get_bond_gap도 동일 반영

## ✅ COMPLETED (Cascade #3 Wave 1)

### RENDER-R01: Lewis 론쌍 재검증 [P0] ✅
- **지시**: 론쌍 점 표시 정합성 확인
- **하달일**: 2026-03-18 (Cascade #3)
- **완료일**: 2026-03-18
- **결과**: 수정 불필요 — H2O=2쌍, NH3=1쌍 정상 동작
- **R-RENDER**: PASS

### RENDER-R02: ESP push-pull 재검증 [P0] ✅
- **지시**: ring_spread 기반 그라데이션 블렌딩 정상 확인
- **완료일**: 2026-03-18
- **결과**: 수정 불필요 — 임계값(0.08/0.15) 및 블렌딩 비율 정상
- **R-RENDER**: PASS

### RENDER-NEW-01: draw_partial_charges [NEW] ✅
- **지시**: CT 추가 기능 — 부분 전하 δ+/δ- 시각화 함수 추가
- **완료일**: 2026-03-18
- **수정**: renderer.py — draw_partial_charges() 정적 메서드, QFontMetrics import
- **R-RENDER**: PASS — threshold/color/filter 완비

### **SUBMIT 상태: 감사 대기 중**
- SUBMIT 보고서: context_note.md 참조
- 감사 대상: audit_rendering_qa + 전문감사 구조화학팀

## ⛔ BLOCKED
(없음)

---

## (이전 Cascade #2 — 무효 처리됨, 아래는 기록용)

### TASK-RENDER-001: 곡선 화살표 교과서 품질 완성 [P1] ✅ (무효)
### TASK-RENDER-002: Drawing 레이어 ESP 활성화 [P2] (무효)
### TASK-RENDER-003: 복잡 분자 ESP 정확성 [P1] ✅ (무효)
