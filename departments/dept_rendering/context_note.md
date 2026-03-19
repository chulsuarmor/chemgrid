# 렌더링/시각화 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 1

---

## SUBMIT REPORT — dept_rendering (Cascade #3 Wave 1)

### 수정파일
| 파일 | 변경내용 |
|------|---------|
| renderer.py | draw_partial_charges() 정적 메서드 추가 (CloudRenderer 클래스). QFontMetrics import 추가. CHARGE_THRESHOLD=0.10, δ-/δ+ 색상분리, sp3 포화탄화수소 필터 |
| _source/renderer.py | src/app와 동기화 |

### 기획자보고 (P-RENDER)
- **P-RENDER spawned at Cascade #3 Wave 1 시점**
- RENDER-R01: Lewis 론쌍 점 표시 재검증 → 정상 동작 확인, 수정 불필요
- RENDER-R02: ESP push-pull 그라데이션 재검증 → ring_spread 기반 블렌딩 정상 확인, 수정 불필요
- RENDER-NEW-01: draw_partial_charges() 함수 신규 추가
  - CHARGE_THRESHOLD = 0.10 (미세 전하 필터)
  - δ- red QColor(200,30,30,180) / δ+ blue QColor(30,80,200,180)
  - sp3 포화탄화수소 원자 필터링 (헤테로/전하/다중결합 원자만 표시)
  - painter.save()/restore() try/finally 패턴
- **크로스-부서 버그 보고**: canvas.py LAYER 4에서 ESP가 Drawing 모드에서도 호출됨 (`view_state == "Theory"` 가드 누락) → dept_ui_canvas에 수정 요청 전달 (P-RENDER는 OWNED_FILES 외 미수정)
- MM 개선지시 반영: QFontMetrics 정확한 텍스트 측정

### 검수자판정 (R-RENDER)
- **R-RENDER spawned at Cascade #3 Wave 1 시점**
- **판정: PASS**
- 검증 방법:
  1. py_compile: 3/3 PASS (renderer.py, layer_logic.py, arrow_generator.py)
  2. ast.parse: 3/3 PASS
  3. Lewis 론쌍: H2O=2쌍, NH3=1쌍 정상
  4. draw_partial_charges: threshold/color/filter 완비, QFontMetrics import 정상
  5. ESP 조건: renderer.py는 view_state 미참조 (호출자 위임) — 정상
  6. 듀얼 동기화: 3개 파일 동일 확인
  7. 업무침범: 없음 (타 부서 파일 미수정, canvas.py 버그는 보고만)

### 감사요청
- 요청 대상: **렌더링 품질 감사관 (audit_rendering_qa)** + **전문감사 구조화학팀**
- 검증 요청 항목: draw_partial_charges 화학적 타당성, ESP push-pull 정확성, Lewis 론쌍 정합성

---

## 기술적 판단 기록

### draw_partial_charges 설계
- CHARGE_THRESHOLD=0.10: Gasteiger 전하가 ±0.10 미만인 원자는 표시 생략 (노이즈 방지)
- δ- red / δ+ blue: 화학 교과서 표준 색상 체계
- sp3 포화탄화수소 필터: 알칸 C-H 원자의 미세 전하 표시 방지 → 유의미한 전하만 시각화
- painter.save()/restore(): QPainter 상태 오염 방지

### 크로스-부서 ESP 버그 (해결됨)
- 발견: canvas.py line ~1306 LAYER 4에서 `CloudRenderer.draw_esp_isosurface()` 호출 시 `view_state == "Theory"` 가드 없음
- P-RENDER: canvas.py는 OWNED_FILES 아님 → "REQUEST TO dept_ui_canvas" 보고
- P-UI: canvas.py line 1332에 `and self.view_state == "Theory"` 가드 추가 완료
- 업무침범 없이 정상적 크로스-부서 협업 사례

### 이전 Cascade #2 기술 기록 (참고용)
- arrow_generator.py v2.0: 적응형 곡률, 결합 소스 세분류
- ESP push-pull 그라데이션: ring_spread 기반 블렌딩 (0.08/0.15 임계값)
- 헤테로고리 fallback 확장: N, O, S 포함

---

## Bug Fix 2026-03-18 — ESP 전체 레이어 + Theory -OH 표시

### Bug 1: ESP 전자구름 Lewis/Drawing 미표시
- **원인**: canvas.py LAYER 2(line 1212), LAYER 3(line 1269), LAYER 4(line 1332)에서 `self.view_state == "Theory"` 조건으로 ESP 호출을 Theory 전용으로 제한
- **수정**: 3개소 모두 `self.view_state == "Theory"` 조건 제거 → `self.show_clouds`만으로 판단
- **LAYER 4 특이점**: Drawing 모드 블록 내에서 `view_state == "Theory"` 조건은 항상 False → ESP가 Drawing에서 절대 표시 불가능한 dead code였음

### Bug 2: Theory 모드 -OH → "O" 표시 문제
- **원인**: TheoryRenderer STAGE 2가 `atom_data["main"]` (원소 기호만) 렌더링, implicit H 미반영
- **수정**: `h_count` - user_placed_h 계산 후 display_label 생성
  - h=1 → "OH", h=2 → "NH2", h=3 → "NH3" 등
  - `get_bond_gap()`도 동일 display_label 기준으로 gap 계산 (결합선 겹침 방지)
- **주의**: user가 attach로 직접 배치한 H는 차감하여 중복 표시 방지

### 수정 파일
| 파일 | 변경 |
|------|------|
| canvas.py | 3개소 `view_state == "Theory"` 제거 |
| layer_logic.py | TheoryRenderer.get_bond_gap + STAGE 2 implicit H 표시 |
| _source/canvas.py | 동기화 |
| _source/layer_logic.py | 동기화 |

### py_compile 검증: 전체 PASS

---

## 발견된 문제 / 블로커
- 실제 앱 GUI 시각 검증 미수행 (최종 감사 시 수행 예정)

## 타 부서 요청 사항
- dept_reaction_synthesis: popup_reaction.py CurvedArrowRenderer에서 aromatic_pi 시각화 구현 권장
