# domain_drug Mistakes Log

## [2026-03-19] admet_predictor.py — predict_admet()의 warnings 덮어쓰기 버그
- **상황:** `_validate_molecule_type` pre-filter를 추가하여 profile.warnings에 검증 경고를 넣었으나, 후반부에서 `warnings = []` 로컬 리스트 생성 후 `profile.warnings = warnings`로 덮어써서 pre-filter 경고가 사라짐
- **실수 내용:** 기존 코드의 `profile.warnings = warnings` 패턴이 이전에 추가된 경고를 완전히 덮어씀
- **올바른 방법:** 기존 리스트에 `.append()` 또는 `.extend()`로 추가해야 함. 새 리스트를 할당하면 이전 데이터 소실. 기존 코드 패턴을 먼저 확인하고 삽입 위치의 부작용을 검토할 것.

## [2026-03-19] admet_predictor.py — 비유기 분자 ADMET 무검증 (P0 silent failure)
- **상황:** 금속 착물(Fe, Pt, Ru 등), 라디칼, 분리된 조각 등이 ADMET 분석을 통과하여 Lipinski PASS 등 잘못된 결과 반환
- **실수 내용:** predict_admet()에 화학적 타당성 검증이 전혀 없어 비유기 분자 86건이 무시됨
- **올바른 방법:** mol 파싱 직후 `_validate_molecule_type()` pre-filter 게이트를 추가하여 금속/라디칼/고전하/분리조각/불가능 구조를 검출하고 warnings에 기록. ADMETProfile에 `is_organic` 필드 추가.

## [2026-03-19] popup_docking.py — 존재하지 않는 시그널 사용 (P1 crash)
- **상황:** audit_gui가 도킹 결과 팝업 실행 시 런타임 크래시 발견
- **실수 내용:** `QTableWidget.currentRowChanged` 시그널은 존재하지 않음. `QTableWidget`은 `currentCellChanged(int,int,int,int)`를 제공.
- **올바른 방법:** `currentCellChanged` 시그널을 사용하고 lambda로 row만 추출하여 슬롯에 전달: `currentCellChanged.connect(lambda row, col, prevRow, prevCol: self._on_pose_selected(row))`

## [2026-03-19] popup_admet.py — 존재하지 않는 RDKit 함수 호출 (P1 crash)
- **상황:** audit_gui가 ADMET 팝업에서 분자 정보 표시 시 런타임 크래시 발견
- **실수 내용:** `Descriptors.MolecularFormula(mol)` 함수는 RDKit에 존재하지 않음.
- **올바른 방법:** `rdMolDescriptors.CalcMolFormula(mol)`을 사용. `from rdkit.Chem import rdMolDescriptors` 필요.

## [2026-03-19] Morphine SMILES 오류 (Cascade #8 Test)
- **상황:** 50종 분자 파이프라인 테스트 중 Morphine SMILES parse 실패
- **실수 내용:** `CN1CC[C@]23c4c(cc(O)c4O2)C[C@@H]1[C@@H]3C=C[C@@H]1O` — ring index `1`이 세 번 사용되어 unclosed ring error 발생
- **올바른 방법:** Morphine 정규 SMILES는 `CN1CC[C@@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@@H]3[C@@H]1C5`. 복잡한 폴리사이클릭 분자의 SMILES는 PubChem/ChEBI에서 검증된 것을 사용할 것.

## [2026-03-19] R_GROUP_LIBRARY의 CF3/NH parse 경고 (비치명적) → FIXED
- **상황:** 유도체 생성 시 `CF3` → "unclosed ring" 경고, `NH` → parse error (stderr에 다수 출력)
- **실수 내용:** `CF3`는 올바른 SMILES가 아님 (C(F)(F)F 또는 [C](F)(F)F가 정확). `NH`도 비표준.
- **올바른 방법:** R_GROUP_LIBRARY에 `CF3`는 이미 `C(F)(F)F`로 등재되어 있으나, preferred_substituents에 `"CF3"` 문자열이 직접 사용되는 경우 MolFromSmiles 실패함. 그러나 generate_r_group_variants가 이를 graceful하게 skip하므로 치명적이지는 않음. 향후 PRESET_GOALS의 preferred_substituents에서 `"CF3"` → `"C(F)(F)F"`로 통일 권장.
- **수정 완료 (Cascade #8):** PRESET_GOALS 내 5개 항목(항암/BBB/대사안정성/지속시간/범용)의 preferred_substituents에서 `"CF3"` → `"C(F)(F)F"` 일괄 교체. 대사 안정성 항목은 기존 중복(`"CF3"`, `"C(F)(F)F"` 공존)을 `"C(F)(F)F"` 하나로 정리.

## [2026-03-19] LeadOptimizerPopup 호출 시 잘못된 kwarg (P1 crash)
- **상황:** AO-LINK 감사에서 LeadOptimizerPopup 생성자 호출 시 런타임 크래시 발견
- **실수 내용:** 생성자 시그니처는 `__init__(self, smiles, canvas, parent)`인데 main_window.py(line 2499)와 popup_3d.py(line 8009)에서 `initial_smiles=smiles`로 호출하여 `TypeError: unexpected keyword argument` 크래시 발생
- **올바른 방법:** `initial_smiles=smiles` → `smiles=smiles`로 수정. 함수 호출 시 반드시 대상 함수의 실제 파라미터명을 확인할 것.

## [2026-03-19] 신약개발 메뉴 구조 — 학생 비친화적 배치
- **상황:** 툴바 "신약개발" 메뉴에서 AlphaFold(PDB ID 필요)가 최상단, 학생 친화적인 리드 최적화가 최하단 배치
- **실수 내용:** 학생이 PDB ID 등 전문 입력값을 모르므로 AlphaFold/도킹이 최상단이면 사용 불가. 리드 최적화(PDB ID 불필요)가 맨 아래 숨어 있어 발견 어려움.
- **올바른 방법:** 리드 최적화 + ADMET(캔버스 SMILES 자동 전달)를 최상단 배치, AlphaFold/도킹/스크리닝은 "고급(전문가용)" 구분선 아래로 이동. `toolbar_setup.py` 수정 (cross-domain: CT 지시에 의한 예외 수정).

## [2026-03-19] Urea(NC(=O)N) 유도체 생성 0건
- **상황:** Urea는 방향족 H도 없고 aliph CH3/CH2/CH 패턴에도 매칭 안 됨
- **실수 내용:** 파이프라인 버그 아님. Urea의 N-H는 [cH] 또는 [CH3,CH2,CH] SMARTS에 매치되지 않음.
- **올바른 방법:** 매우 단순한 분자(원자 3개)에서 유도체 0건은 예상 결과. 필요시 N-H 치환 전략을 별도 구현하면 해결 가능.

## [2026-03-19] popup_3d.py — SynthesisPopup 호출 시 잘못된 kwarg (P1)
- **상황:** "합성경로 분석" 버튼 클릭 시 SynthesisPopup 생성 실패
- **실수 내용:** `SynthesisPopup(smiles=smiles, ...)` 호출했으나 실제 생성자는 `__init__(self, target_smiles: str, ...)`. `smiles`라는 kwarg 없음.
- **올바른 방법:** `SynthesisPopup(target_smiles=smiles, parent=self)` 사용. 호출 전 대상 클래스 생성자 시그니처 반드시 확인.

## [2026-03-19] popup_lead_optimizer.py — _on_draw_to_canvas가 존재하지 않는 메서드 호출 (P1)
- **상황:** "캔버스에 그리기" 버튼 클릭 시 실제 캔버스에 분자가 그려지지 않음
- **실수 내용:** `canvas.set_smiles()` 호출하나 MainWindow의 캔버스에는 `set_smiles` 메서드가 없음. `draw_on_canvas` 시그널도 어디에도 연결되지 않음.
- **올바른 방법:** 부모 위젯 체인을 따라 MainWindow를 찾아 `_draw_smiles_on_canvas(smiles, name)` 호출. 시그널은 fallback으로만 유지.
