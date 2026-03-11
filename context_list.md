# ✅ ChemGrid 할일 목록 (context_list.md)
## 마지막 업데이트: 2026-03-10 세션 7

---

## 완료된 작업

- [x] **FEAT-1**: 루이스 구조/이론적 구조 렌더링 기본 동작 (benzene 등 그리기)
- [x] **FEAT-2**: 전자구름 이온성 레이어 렌더링 (benzene 구름 색상 기본 표시)
- [x] **FEAT-3 (ISSUE-1)**: 이온성 방향족 전자구름 균등화 — 세션 5-2 최종 수정 완료
  - [x] BUG-3 FIX: at_sym in ('', 'C') 수정 (main='' 탄소 규칙)
  - [x] fallback 3: bonds에서 degree>= 환형 ring 탐지
  - [x] ionic_bias: attach[-1] 전하 기호 직접 검출
  - [x] ring_charges: 모든 ring 원자 포함 avg
  - [x] 세션 5-2 추가 수정: 무조건 ring equalization 제거 → ionic_bias!=0 블록에서만 균등화
  - [x] 세션 5-2 추가 수정: `at_main == "C"` → `at_main in ('', 'C')` 2곳 (local_contrast, is_ring_carbon)
  - ✅ 시각 검증: Cp- RED 균등(475px), Aspirin 산소 RED + COOH BLUE 분산 (2026-03-10)
- [x] **BUG-A**: _draw_smiles_on_canvas 캔버스 미초기화 → 원자 누적 수정
- [x] **BUG-B**: _last_drawn_smiles 타이밍 버그 (stale SMILES)
- [x] **BUG-C**: +/- 기호가 탄소 골격 위를 가리는 버그
- [x] **BUG-D**: 3D 팝업 방향족 결합 전부 이중결합 (banker's rounding)
- [x] **ISSUE-3 canvas.py**: theory_map rounded key 수정 (2026-03-10 세션 6)
  - `_rk = (round(k[0], 2), round(k[1], 2)); pt = t_map.get(_rk) or t_map.get(k) or QPointF(*k)`
- [x] **ISSUE-3 open_3d_popup fallback**: 선택 원자 < 전체의 50%이고 `_last_drawn_smiles` 존재 시 전체 원자로 교체 (세션 7 확인 — 이미 구현됨)
  ```python
  if _last_smiles and _all_atom_keys and len(selected_keys) < len(_all_atom_keys) * 0.5:
      selected_keys = _all_atom_keys
  ```
- [x] **ISSUE-4 PubChem REST API**: IsomericSMILES 조회 구현 완료
- [x] **ISSUE-4 Google Knowledge Graph + PubChem Autocomplete**: 세션 7 확인 — `_lookup_smiles_for_name`에 Step 3.5, 3.6 모두 구현됨
  - Step 1: BUILTIN 사전 (100+ 분자)
  - Step 1.5: 축약식/분자식 파싱 (`_try_parse_condensed`)
  - Step 2: PubChem REST API
  - Step 3: Gemini AI 폴백
  - Step 3.5: Google Knowledge Graph API → PubChem 교차 검색
  - Step 3.6: PubChem Autocomplete fuzzy matching
- [x] **구문 오류 없음**: main_window.py, canvas.py, layer_logic.py, analyzer.py 모두 py_compile 통과 (세션 7)

---

## [2026-03-10 세션 8] 완료 — SPEC-GUIDE-v2 그래프 교체

- [x] `popup_3d.py` → `load_predicted()` 내 기존 `predict_spectrum_from_smiles()` 직접 호출을 `_render_guide_spectrum()` 위임으로 교체
- [x] `_render_guide_spectrum()` 메서드 신규 추가
  - `predict_all(smiles)` → `PredictedSpectrum` 호출
  - `_make_ir_figure / _make_raman_figure / _make_nmr_h1_figure / _make_nmr_c13_figure / _make_uvvis_figure` 사용
  - `canvas.figure` 동적 교체로 흰 배경 전문 그래프 연결
  - fallback: 기존 Lorentzian (흰 배경)
- [x] 문법 검증 통과 (ast.parse OK)

---

## 남은 이슈 — 우선순위별 정리

### 🔴 HIGH: ISSUE-5 — 선택 도구 검증 (테스트 필요)
**현황**: 코드 수정은 완료(canvas.py + open_3d_popup). 실제 앱 실행으로 확인 필요.

**검증 목표**:
1. benzene 텍스트 입력 → 이론적 구조 전환 → 전체 드래그 선택 → 3D 팝업 → 6원자 모두 전달
2. aspirin 텍스트 입력 → 이론적 구조 전환 → btn_3d 클릭 → 전체 분자 3D 뷰

**예상 결과**: `_last_drawn_smiles` 있으므로 50% 미만 선택이어도 전체 원자 사용

---

### 🟡 MEDIUM: ISSUE-6 — 소형 잔여 버그

| 버그 | 위치 | 상태 |
|------|------|------|
| benzene 이론구조 이중결합 표시 (Kekulé vs 원 표기) | layer_logic.py | 미수정 |
| cp- 5각형 → 4각형 렌더링 오류 | analyzer.py? | 미검증 |

---

### 🟢 LOW: ISSUE-7 — 스펙트럼 예측 (ORCA 없이)
**현황**: `popup_predicted_spectrum.py` 이미 존재, SMILES → 예측 스펙트럼 통로 구현됨.

**검증 목표**:
- benzene SMILES → IR 예측 스펙트럼 팝업 표시
- 실패 시 `predict_spectra.py` 로직 점검

---

## 다음 세션 우선순위

```
1단계: 앱 실행 + 선택 도구 실제 검증 (30분)
   → benzene 입력 → 이론적 구조 → 전체 드래그 선택 → 3D 팝업
   → aspirin 입력 → btn_3d 직접 클릭 → 3D 팝업

2단계: 스펙트럼 예측 시스템 확인 (30분)
   → benzene SMILES로 IR/NMR 예측 스펙트럼 팝업 테스트
   → 실패 시 popup_predicted_spectrum.py 점검

3단계: cp- 5각형 오류 재확인 (20분)
   → cp- 입력 → 이론적 구조 → 5각형 정상 렌더링 확인

4단계: 종합 10개 분자 테스트 보고서
```

---

## 잔여 소형 버그 (낮은 우선순위)

- [ ] benzene 이론구조 → plain hexagon (이중결합 없는 표시) 수정 (BUG-B theory hexagon)
- [ ] 분광분석 6종 전부 ORCA 파일 요구 (ORCA 없이 예측 스펙트럼 구현 필요)
- [ ] cp- 5각형 → 4각형 렌더링 오류 확인

## [2026-03-11 00:49] 세션 패치 완료
- [x] popup_3d.py MS 탭 제거 (spec_buttons에서 MS 엔트리 삭제)
- [x] popup_3d.py NMR smiles 파라미터 전달 (_render_guide_spectrum → _make_nmr_h1_figure/c13 smiles=smiles 추가)
- [x] popup_predicted_spectrum.py figsize 5개 → (9.0, 4.5) 통일
- [x] main_window.py QIcon 멀티사이즈 (16/32/48/64/128/256px) 적용
