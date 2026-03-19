# 렌더링 품질 감사관 감사 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 1 감사 수행

---

## 감사 보고서 — Cascade #3 Wave 1

### 감사 대상
- **Primary**: dept_rendering — draw_partial_charges() 신규 추가 (renderer.py)
- **Secondary**: dept_chem_engine — Gasteiger 60/40 블렌딩 (analyzer.py)
- **Secondary**: dept_ui_canvas — ESP Theory 가드 (canvas.py)

### 감사 기준
- `skills/sci_accuracy_standards.md` (SCI급 정합성 검증 기준서)
- ChemGrid MEMORY 규칙 (Carbon='', Gasteiger 60/40, ESP Theory guard, _reveal_radius=max_r)

---

## 체크리스트 판정 결과

### 1. ESP 전자구름 Gasteiger 블렌딩 (60% Gasteiger + 40% custom) — PASS

**근거**: `analyzer.py` line 170-171
```python
global_charges[nk] = 0.6 * g_scaled + 0.4 * global_charges[nk]
```
- 정확히 60% Gasteiger + 40% custom physics 비율 적용
- RDKit `ComputeGasteigerCharges()` 사용 확인 (line 142)
- `rdkit_idx` 기반 매핑으로 정확한 원자 대응 (line 152-156)
- nan/inf 가드 존재 (line 147)
- 스케일링 팩터 `sf = c_range / g_range` 적용으로 범위 정규화 (line 167)
- v8.3 공명 등가 원자 균등화 추가 (line 173-190): Gasteiger 전하 3자리 반올림 그룹핑

### 2. +/- 형식 전하(formal charge) 및 라디칼 반영 — PASS

**근거**:
- `layer_logic.py` LewisRenderer._render_formal_charges() (line 528-581): formal_charge + charge 필드 fallback 정상
- `layer_logic.py` TheoryRenderer STAGE 3-A (line 820-846): Theory 레이어에서도 형식전하 표시
- `analyzer.py` line 265-275: lewis_data에서 formal_charge가 attach[-1]에 +/- 기호로 복원
- `analyzer.py` line 350-365: generate_smiles에서 charge 필드 및 attach 딕셔너리 양방향 전하 복원
- 라디칼: `analyzer.py` line 368-371에서 attach "dot" 기호 감지 후 `SetNumRadicalElectrons()` 호출
- `layer_logic.py` TheoryRenderer STAGE 3-C (line 923-934): 라디칼 도트 렌더링 정상

### 3. Lewis 론쌍(lone pair) 표시 — PASS

**근거**:
- `layer_logic.py` LewisRenderer._render_vsepr_extensions() (line 360-382): lp_count 기반 VSEPR 배치
- `analyzer.py` line 448: `lp = max(0, (outer_elecs - bonds_val - formal_charge) // 2)` — 옥텟 기반 계산 정상
- H2O: O (외각 6 - 결합가 2 - 전하 0) / 2 = 2쌍 -- 정상
- NH3: N (외각 5 - 결합가 3 - 전하 0) / 2 = 1쌍 -- 정상
- 방향족 이온 탄소(C-) LP 억제: line 370-376에서 aromatic set 소속 시 lp_count=0 강제 — 화학적으로 정확 (pi 비편재화)
- TheoryRenderer STAGE 3-B (line 848-921): Theory 모드에서도 LP 독립 렌더링 확인

### 4. Theory mode에서만 ESP clouds 표출 (view_state == "Theory") — PASS

**근거**: `canvas.py` 3개 레이어 모두 가드 확인
- **LAYER 2** (애니메이션 배경) line 1212: `self.view_state == "Theory"` 가드 존재
- **LAYER 3** (원형 확장) line 1269: `self.view_state == "Theory"` 가드 존재
- **LAYER 4** (Drawing 모드) line 1326+1332: LAYER 4는 `view_state == "Drawing"` 블록 내부이고, line 1332에서 `self.view_state == "Theory"` 조건이 있어 실질적으로 ESP 호출 불가 (Drawing 모드에서 Theory 조건은 항상 False) — 의도대로 정상 동작

**참고**: dept_rendering의 context_note.md에서 "LAYER 4 ESP가 Drawing 모드에서도 호출됨" 버그를 보고했고 dept_ui_canvas가 수정 완료했다고 기록됨. 현재 코드 확인 결과 3개 레이어 모두 가드가 정상 적용됨.

### 5. draw_partial_charges: threshold/color/filter 화학적 타당성 — PASS (경미한 권고사항 있음)

**근거**: `renderer.py` line 1486-1570
- **CHARGE_THRESHOLD = 0.10** (line 1515): Gasteiger 전하 기준 |0.10| 미만 노이즈 필터 — 적절함. 일반 알칸 C-H 전하는 ~0.03-0.06이므로 이를 걸러냄.
- **색상 체계** (line 1545-1550):
  - delta-: QColor(200,30,30,180) — 적색 반투명 (전자 풍부)
  - delta+: QColor(30,80,200,180) — 청색 반투명 (전자 부족)
  - McMurry/Clayden 교과서 ESP 표준(Red=negative, Blue=positive)과 일치 -- 정상
- **sp3 포화탄화수소 필터** (line 1529-1540): hetero/charge/다중결합 원자만 표시 — 화학적으로 합리적
- **QFontMetrics 사용** (line 1556): 정확한 텍스트 오프셋 측정 확인
- **painter.save()/restore() + try/finally 패턴** (line 1517-1570): QPainter 상태 보호 정상

**권고 (ADVISORY, FAIL 아님)**: sp3 필터에서 bond order >= 1.5를 다중결합 기준으로 사용 (line 1536). 방향족 결합이 order=1로 저장되는 ChemGrid 특성상, 방향족 고리 탄소가 필터에 걸릴 수 있음. 다만 방향족 탄소는 `is_hetero`도 False이고 formal charge도 보통 없으므로 표시되지 않아 실질적 문제는 없음.

### 6. 그리기/루이스/이론적 레이어 간 전자구름 정합성 — PASS

**근거**:
- **Drawing 레이어**: draw_partial_charges()는 Gasteiger 블렌딩된 global_charges 사용 (analyzer.py 출력)
- **Lewis 레이어**: 형식전하/론쌍만 표시, ESP 구름 없음 (view_state 가드)
- **Theory 레이어**: CloudRenderer.draw_esp_isosurface() + draw_clouds() 사용, 동일한 analysis_results 참조
- 세 레이어 모두 동일한 `analysis_results` 딕셔너리를 source of truth로 사용하므로 전하 데이터 정합성 유지됨
- ESP 색상 체계: draw_esp_isosurface() (line 514-521) 및 charge_to_color() (line 252-266) 모두 Red(-)→Green(0)→Blue(+) 매핑으로 일관

### 7. Carbon이 빈 문자열('')로 저장되는 규칙 준수 — PASS

**근거**:
- `renderer.py` line 733, 886, 1127, 1129: `at_main in ('', 'C')` 패턴으로 carbon 빈 문자열 정상 처리
- `draw_partial_charges()` line 1527: `at_main = atom_data.get("main", "") or "C"` — fallback 정상
- `draw_esp_isosurface()` line 485: `at_main = atom_data.get("main", "") or "C"` — fallback 정상
- sp3 필터: line 1530에서 `at_main not in ('', 'C', 'H')` — 빈 문자열을 탄소로 올바르게 처리
- `analyzer.py` line 34: 결합 복구 시 `{"main": "", "attach": {}}` — 빈 문자열 규칙 준수

### 8. _reveal_radius가 max_r로 설정되어 스크린샷 완전 — PASS

**근거**: `canvas.py` line 184-185
```python
max_r = math.hypot(self.width(), self.height()) * 1.0
self.anim.setEndValue(max_r)
```
- start_reveal_animation()에서 대각선 길이 * 1.0 = 전체 캔버스 커버
- 애니메이션 종료 시 _reveal_radius == max_r → 원형 클리핑이 전체 캔버스를 포함
- LAYER 3 원형 확장(line 1244-1248)에서 `l_radius = self._reveal_radius / self.scale_factor` 사용 — 스케일 보정 정상

---

## 종합 판정

| # | 체크리스트 항목 | 판정 |
|---|----------------|------|
| 1 | Gasteiger 60/40 블렌딩 | **PASS** |
| 2 | 형식전하/라디칼 반영 | **PASS** |
| 3 | Lewis 론쌍 표시 | **PASS** |
| 4 | Theory mode ESP 가드 | **PASS** |
| 5 | draw_partial_charges 타당성 | **PASS** |
| 6 | 레이어 간 전자구름 정합성 | **PASS** |
| 7 | Carbon 빈 문자열 규칙 | **PASS** |
| 8 | _reveal_radius = max_r | **PASS** |

### 최종 판정: **ALL PASS (8/8)**

### 권고사항 (비강제)
1. draw_partial_charges()의 sp3 필터에서 방향족 결합 order=1 케이스에 대한 명시적 처리 고려 (현재 실질적 문제 없음)
2. sci_accuracy_standards.md 기준서에서 요구하는 "결합 길이 Angstrom 단위" 항목은 Known Bugs P2에 이미 등록됨 (본 감사 범위 외)

---

## 이론값 참조 캐시
- Gasteiger 전하 범위: 일반 유기분자 ±0.5 내외 (RDKit 기준)
- CHARGE_THRESHOLD 0.10: 알칸 C-H 전하 ~0.03-0.06 필터에 적합
- ESP 색상: McMurry/Clayden 교과서 Red(delta-) → Green(neutral) → Blue(delta+) 표준
- 옥텟 론쌍: O=2쌍, N=1쌍(NH3), Cl=3쌍 — RDKit outer_elecs 기반 자동 계산
