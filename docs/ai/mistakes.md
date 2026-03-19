# 🚫 ChemGrid AI 실수 기록부
> 다시는 반복하지 않기 위한 패턴 기록

---

## [2026-03-19] PiOrbitalRenderer를 잘못 MC 점밀도로 변환한 실수
- **상황:** 오비탈 렌더링 개선 중 π orbital (sp2 모드)과 전체 오비탈(혼성) 모드를 구분하지 않고 일괄 MC 변환
- **실수 내용:** 사용자가 만족한 gluSphere 물방울형 p-orbital 로브를 MC 점밀도로 교체함. "전체 오비탈" 모드(AdvancedOrbitalRenderer)만 MC가 필요했는데 PiOrbitalRenderer까지 변환해버림
- **올바른 방법:**
  - PiOrbitalRenderer._draw_p_orbital_lobes → gluSphere 물방울형 유지 (사용자가 좋아한 원본)
  - PiOrbitalRenderer._draw_ring_pi_cloud → gluSphere 납작 디스크 유지
  - AdvancedOrbitalRenderer._lobe → MC 점밀도 (개구리알 문제 해결용)
  - **렌더러별 용도를 구분하고, 사용자가 승인한 시각적 결과물을 임의로 변경하지 말 것**

---

## 🔴 [절대 규칙] 시각 피드백(visual feedback) 검증은 반드시 실제 앱에서 수행해야 한다

**위반 금지**: 백그라운드 Python 스크립트(RDKit MW 계산, SMILES 파싱 등)만으로 "검증 완료"를 선언하는 것

**이유**: 코드 레벨 검증과 실제 사용자 화면 동작은 완전히 다름
- RDKit이 SMILES를 파싱할 수 있어도, 앱 캔버스에서 올바르게 렌더링되지 않을 수 있음
- 버튼 클릭 시 팝업이 뜨는지, 레이어 전환이 되는지는 코드만으로 알 수 없음
- 전자구름 색상, 원자 위치, 결합 표시 등은 실제 화면 캡처로만 확인 가능

**올바른 시각 피드백 절차 (이 순서를 반드시 따를 것)**:
1. `Run_ChemGrid.bat` 또는 직접 실행으로 **실제 앱을 화면에 띄운다**
2. `browser_action` 도구로 스크린샷을 찍어 **실제 화면을 확인**한다
3. 각 분자마다 AI 입력 또는 직접 그리기로 분자를 불러온다
4. **레이어별 직접 버튼 클릭**:
   - S0: 그리기 레이어 (Lewis 구조, 전하/라디칼 표시)
   - S1: 이론적 구조 레이어 (bond order, 방향족 표기)
   - S2: 이론적 구조 선택 도구 (드래그 선택 후 인식 원자 수 확인)
   - S3: 입체 구조 팝업 (3D 뷰어, RS 배열 표기)
   - S4: 분광분석 버튼 (IR/Raman/NMR/UV-Vis/MO 팝업 확인)
   - S5: PDF 내보내기 버튼 클릭 후 파일 생성 확인
5. 스크린샷을 수집하여 `docs/reports/visual_feedback/` 에 저장
6. HTML 리포트(`file:///C:/chemgrid/docs/reports/visual_feedback_report.html`)로 일괄 이미지 분석
7. 문제 발견 시 코드 수정 → 앱 재시작 → 동일 분자 재검증 (무한 반복)
8. **모든 문제가 해결될 때까지 이 루프를 종료하지 않는다**


---

## [2026-03-10] 전자구름 균등화 — 20회 이상 RDKit 기반 접근 실패

**상황**: 사이클로펜타디에닐 음이온(Cp-), 트로필리움 이온 등 방향족 이온의 π 전자를 고리 전체에 균등 표시해야 함

**시도된 실패 방법 (절대 재시도 금지)**:
1. RDKit `GetFormalCharge()` + 원자별 density 계산 → 국소화 문제 해결 안 됨
2. 공명 구조 SMILES 목록 생성 후 가중 평균 → RDKit이 공명 구조를 같은 것으로 canonical화 해버림
3. `Chem.ResonanceMolSupplier()` → 느리고 단순 이온에 한정
4. `GetAromaticAtoms()` + 균등 density 강제 할당 → 비방향족 공명 구조(allyl 등)에서 오작동
5. SMILES 내 소문자(aromatic) 여부로 density 판별 → 이온 표기 시 소문자 미보장
6. 그 외 renderer.py, engine_resonance.py에서의 각종 density 재계산 패치

**올바른 방향**:
- RDKit 기반은 구조적 한계 존재. **반드시 QM 계산 필요**
- 단기 해결: `AllChem.GetAromaticAtoms()`로 방향족 원자 탐지 → **해당 원자들 density 강제 균등화** (완벽하지 않지만 이론값 근사 가능)
- 장기 해결: SMILES → `xtb` (GFN2-xTB) → Mulliken charges → 2D density 매핑

---

## [2026-03-10] live_test.py 창 탐지 — VS Code 오인 버그

**상황**: ChemGrid V5 앱을 `pygetwindow`로 탐지하려 했음

**실수**: `find_win("ChemGrid")` → VS Code 창("live_test.py - chemgrid - Visual Studio Code") 을 ChemGrid로 오인

**올바른 방법**: VS Code, 탐색기, Discord 등을 명시적으로 제외한 후 검색
```python
if "Visual Studio Code" in t or "탐색기" in t:
    continue
if "ChemGrid V5" in t and w.width > 200:
    return w
```

---

## [2026-03-10] live_test.py 입력창 좌표 계산 — -90 보정 오류

**상황**: ChemGrid 입력창(mol_name_input)의 화면 좌표를 계산

**실수**: `iy = win.top + win.height - INPUT_H - 18 - 90` → 90px 위 (캔버스 중간) 클릭됨

**원인**: pygetwindow의 `win.height`는 OS 전체 창 높이 (title bar 포함). PyQt6의 `self.height()`와 약 32px 차이가 있지만, `win.top + win.height`가 창 하단 절대좌표이므로 `-90` 불필요

**올바른 공식**:
```python
iy = win.top + win.height - INPUT_H - 18  # 추가 보정값 없음
cy = iy + INPUT_H // 2
```

---

## [2026-03-10] current_state.json으로 SMILES 검증 — 잘못된 방법

**상황**: 텍스트 입력 후 분자가 올바르게 그려졌는지 확인하기 위해 `current_state.json`의 SMILES 읽음

**실수**: `current_state.json`은 명시적 저장(save_file) 또는 이론적 구조 버튼 클릭 시에만 업데이트됨. 텍스트 입력으로 그린 분자는 즉시 반영 안 됨 → 이전 세션 stale 데이터 반환

**올바른 검증 방법**:
- 스크린샷의 캔버스 영역에서 실제 그려진 구조 확인 (시각적 검증)
- ChemGrid 앱 로그 파일(`launch_error.log`) 에서 SMILES 출력 확인
- 또는 앱 종료 전 저장 버튼 클릭 유도 후 JSON 읽기

---

## [2026-03-09] SMILES 파이프라인 — 레이어 간 SMILES 소실

**상황**: 그리기 레이어 → 이론적 구조 변환 시 SMILES가 누락됨

**실수 패턴**: 
- 분자 식별 방법으로 `canvas.get_smiles()` (atoms/bonds 재구성) 사용
- 원자/결합 목록이 완전하지 않으면 유효하지 않은 SMILES 생성
- 특히 전하(+/-) 원자, 이중결합 원자 포함 시 재구성 실패율 높음

**올바른 방법**:
- 그리기 레이어에서 SMILES가 확정되는 순간(루이스 구조 완성, 텍스트 입력 완료) `cv._last_drawn_smiles = smiles` 태그 저장
- 모든 하위 파이프라인은 `canvas.get_smiles()` 대신 `cv._last_drawn_smiles` 우선 사용

---

## [2026-03-10] tropylium SMILES — RDKit 원자가 초과 오류

**상황**: tropylium(C7H7+) 이온의 SMILES를 BUILTIN 사전에 등록

**실수**: `[CH+]1=CC=CC=CC1` 사용 → RDKit `"Explicit valence for atom #0 C, 4, is greater than permitted"` 오류  
- `[CH+]` 탄소에 + 전하 + 이중결합 + H = 4 valence → C+ 허용 valence(3) 초과

**올바른 방법**: Kekulé 형으로 전하 탄소를 단일결합 위치에 배치  
```
C1=CC=CC=C[CH+]1   ✅ (RDKit canonical: c1cc[cH+]ccc1)
```
규칙: 양이온 탄소 `[CH+]`는 **이중결합 없이 단일결합만** 가져야 한다.

---

## [2026-03-10] heme SMILES — 파이썬 이스케이프 시퀀스 경고

**상황**: Fe 배위 결합 표기 `\[` 를 파이썬 일반 문자열에 삽입

**실수**: `"...N2\[Fe]N34..."` → `SyntaxWarning: invalid escape sequence '\['`

**올바른 방법**: raw string 접두사 사용  
```python
r"...N2\[Fe]N34..."   ✅
```
규칙: SMILES 안에 `\` 가 포함된 경우(입체화학 표기 포함) **반드시 r"..." raw string** 사용.

---

## [2026-03-10] BUG-A: _draw_smiles_on_canvas — 캔버스 미초기화로 분자 누적

**상황**: AI 텍스트 입력창에 benzene → tropylium 순서로 분자명 입력

**실수**: `_draw_smiles_on_canvas()` 안에서 `save_state()` 후 `atoms.clear()` / `bonds.clear()`를 호출하지 않아, 이전 분자 원자/결합이 캔버스에 잔류함  
→ 시각 결과: benzene(6원자) + tropylium(7원자) = 13원자가 동일 캔버스에 겹쳐서 표시됨  
→ SMILES 결과: `C1=CC=CCC=C1.c1ccccc1` (두 분자 조합)

**올바른 방법**:
```python
self.cv.save_state()
# 반드시 clear 먼저 하고 새 분자 그리기
self.cv.atoms.clear()
self.cv.bonds.clear()
```
규칙: `_draw_smiles_on_canvas()`가 호출될 때마다 **항상 atoms와 bonds를 초기화**한다.  
save_state()는 clear 전에 호출해야 undo 기능이 유지된다.

**수정 날짜**: 2026-03-10 01:34 ✅ **수정 완료 및 시각 검증 통과**

---

## [2026-03-10] BUG-B: 방향족 분자 이론 구조 — 이중결합 없는 plain hexagon

**상황**: benzene 입력 → 이론적 구조 탭 전환 시

**실수/원인**: `clearAromaticFlags=False`로 Kekulize 시 bond type이 SINGLE/DOUBLE로 전환되지만,  
`GetBondTypeAsDouble()` 반환값이 1.5(AROMATIC)일 경우 `order = 2`로 잘못 분류됨  
→ 모든 결합이 order=2 → OR 전체 order=1로 균등화 가능성 있음  
→ 결과: benzene 이론 구조가 cyclohexane과 시각적으로 동일한 plain hexagon으로 표시

**미수정 상태**: 현재 theory view에서 benzene은 여전히 plain hexagon으로 표시됨  
**해결 방향**:
1. `clearAromaticFlags=True`로 변경하여 bond type을 SINGLE/DOUBLE로 완전 전환
2. OR theory view에서 방향족 고리 탐지 후 내접원(aromatic notation) 그리기 추가

---

## [2026-03-10] 이온 방향족 전자구름 SMILES fallback — 파이프라인 누락 해결 ✅

**상황**: tropylium(BLUE 기대), cp-(RED 기대) 입력 시 전자구름이 GREEN으로 표시됨 (20회 시도 실패)

**근본 원인**:
1. renderer.py는 `results["atoms"][key].get("charge","")` 로 charge 읽음
2. analyzer.py의 `norm_atoms`에는 `"charge"` 키 없음 (attach[-1]에만 "+"/"-" 저장)
3. `results["smiles"]`가 없어서 SMILES fallback 미작동
4. `_draw_smiles_on_canvas`에서 formal_charge를 atoms dict에 미저장

**해결 방법 (2026-03-10 수정 완료)**:
- `main_window.py` `_draw_smiles_on_canvas`: `atom.GetFormalCharge() != 0`이면 `"formal_charge"`, `"charge"` 키 atoms dict에 저장
- `main_window.py` analyze 후: `analysis_results["smiles"] = smiles` 저장 → SMILES fallback 활성화
- `renderer.py` ionic_bias: 3중 fallback (atom_dict → orig_ring_charges → SMILES `[CH+]`/`[cH-]`/`[NH3+]` 패턴)
- `visual_verify.py` `type_molecule`: `win.activate()` try/except + 핸들 무효 시 재검색

**검증**: 7차 자동화 테스트 tropylium=BLUE ✓, cp-=RED ✓

**교훈**: 데이터 파이프라인 중간에서 charge 정보가 누락되는 단계가 있으면 fallback이 필요. `results["smiles"]`를 항상 저장하는 것이 가장 안전한 fallback 기반.

---

## [2026-03-10] 6단계 테스트 결과 — 새 버그 3종 확인

**상황**: visual_verify.py v3.0으로 12분자 × 6단계 자동 테스트 실행 (2026-03-10 03:09)

### 신규 Bug #1: cp- 5각형 → 4각형 렌더링 오류
- **증상**: [cH-]1cccc1 (5-membered ring) 렌더링 시 4개 원자만 표시 (정사각형)
- **원인 추정**: 5각형 2D layout 좌표 계산 오류, 또는 [cH-] 원자가 별도 처리되면서 레이아웃 누락
- **기대**: 5개 C 원자가 정오각형 배치
- **절대 금지**: `coords = AllChem.Compute2DCoords()` 재호출 없이 원자 좌표만 보정하는 시도 → ring topology 무시

### 신규 Bug #2: 분광분석 6종 전부 ORCA 파일 요구
- **증상**: btn_spectrum/nmr/uvvis/md/molorbital 모두 클릭 시 파일 선택 다이얼로그만 출현
- **원인**: 현재 구현이 ORCA .out 파일 파싱에만 의존 (`parse_orca_frequencies()`)
- **올바른 방향**: SMILES/원자 구조 기반 **예측 스펙트럼** 구현 필요
  - IR 예측: RDKit `GetBondLength()` + 진동 추정 (Hooke's Law 근사)
  - NMR 예측: RDKit `GetNumAromaticRings()` + chemical shift 룩업 테이블
  - UV-Vis 예측: HOMO-LUMO gap 추정 (Hückel method)
- **절대 금지**: ORCA 파일 없이 기존 코드를 그대로 두는 것 → 분광분석 기능 전체 작동 불가

### 신규 Bug #3: S2 이론구조 네비게이션 불안정
- **증상**: Lewis mode에서 Theory button 좌표 클릭 시 실제 Theory mode 전환이 불확실
- **원인**: Lewis mode에서는 view_container가 보이지 않아 좌표 미스매칭 가능
- **확인 방법**: S4 3D 팝업이 성공적으로 열렸으므로 Theory mode 도달은 가능
- **개선 방향**: S2 시작 전 Drawing mode 확인 후 Theory 버튼 클릭

---

## [2026-03-10] 테스트 스크립트 timeout — 단일 실행 30초 제한

**상황**: `execute_command`가 30초 후 timeout

**실수**: pyautogui 기반 GUI 테스트는 앱 실행 대기 + 각 테스트 케이스 대기로 90초+ 소요

**올바른 방법**: 
- 단기 테스트만 30초 내 수행 (1~2 케이스만)
- 또는 테스트를 백그라운드로 분리 실행: `Start-Process python -ArgumentList "tools/live_test.py"`
- 완료 후 HTML 보고서를 browser_action으로 확인

---

## [2026-03-10] +/- 기호가 탄소 골격 위를 가려 "탄소 소실" 버그 (canvas.py charge 렌더링)

**상황**: 트로필리움 이온에서 그리기 레이어(S0)를 보면 [CH+] 위치의 탄소가 사라지고 큰 + 기호가 대체

**실수 내용**:
1. `draw_atom_group()` charge_sym 렌더링: `cx = pt.x() + label_w/2 + 2`, `cy = pt.y() - fm.height()/2 + cfm.ascent() - 4` → cy ≈ pt.y() - 3 (원자 중심 거의 동일) → bond 교차점 겹침
2. `main_window.py` `_draw_smiles_on_canvas()`: C 원자 `main = atom.GetSymbol()` = "C" → 그리기 레이어에서 모든 탄소에 "C" 라벨 표시 → 탄소 위에 "C" + "+" 동시 표시로 혼잡

**올바른 방법**:
1. `canvas.py`: `cx_charge = pt.x() + label_w/2 + 8`, `cy_charge = pt.y() - fm.height()/2` → 우상단 위첨자 명확히 배치
2. `main_window.py`: `sym = "" if atom.GetSymbol() == "C" else atom.GetSymbol()` → skeleton 방식으로 C 라벨 숨김

**수정 일자**: 2026-03-10 (이번 세션 수정 완료 ✅)

---

## [2026-03-10] 이론적 구조 선택 도구 — 분자 일부만 인식 버그 (미수정)

**상황**: 이론적 구조 레이어에서 드래그 선택 시 benzene 6원자 중 2~3개만 선택되거나, 큰 분자는 전혀 선택 안 됨

**근본 원인**:
- canvas.py `mouseMoveEvent` Lewis/Theory 브랜치에서 `pt = t_map.get(k, QPointF(*k))` 사용
- 그러나 `analysis_results["theory_data"]["map"]`이 모든 원자를 포함하지 않을 수 있음 (일부 원자 키 누락)
- 키 누락 시 원본 hex-grid 좌표로 fallback → 이 좌표는 theory 레이어 렌더링 좌표와 다름 → 선택 박스가 hit하지 않음

**절대 금지**: t_map 좌표를 수정하지 않고 selection_rect.contains()만 수정하는 방법 → theory_data map 자체를 완전히 채우는 것이 필수

**올바른 방법**:
- `layer_logic.py` TheoryRenderer.render()에서 theory_data["map"]에 모든 원자 키를 빠짐없이 기록하는 로직 추가
- 또는 `canvas.py` mouseMoveEvent에서 map 없는 원자는 atoms 전체 범위 내에 있으면 선택 포함

**미수정 상태 (다음 세션 해결 대상)**

---

## [2026-03-10] AI 텍스트 입력 benzene → cyclohexane 버그 (Kekulize 우선순위 문제)

**상황**: AI 입력창에 "benzene" 입력 시 단순 6각형(cyclohexane)으로 렌더링

**실수 내용**: `_draw_smiles_on_canvas()`에서 Kekulize 실패 시 방향족 결합(AROMATIC type)을 order=1(단일결합)로 처리 → 이중결합 없이 6각형만 그려짐

**해결됨**: Kekulize 성공 시 `bond.GetBondTypeAsDouble()` 기반 order 결정 → benzene의 3개 이중결합 표시 (2026-03-09 수정)

**남은 문제**: Kekulize 실패하는 복잡한 방향족(포르피린, coronene 등)은 여전히 단일결합으로 표시됨. 장기 해결책: aromaticity 기반 내접원 표기법 추가

---

## [2026-03-10] BUG-3 전자구름 편재화 — raw_strength 불균등 원인 발견

**상황**: cp-, tropylium 같은 이온성 방향족 고리에서 전자구름이 일부 탄소에 집중

**실수/원인**: 
- 
aw_strength = 2.2 if pt_key in aromatic else (0.85 if isl_size >= 2 else 0.0)
- [cH-], [cH+] 이온화 원자는 RDKit aromatic set에 누락될 수 있음 (SMILES 파싱 방식에 따라)
- 결과: 이온화 원자(raw_strength=0.85) vs 나머지 방향족 원자(raw_strength=2.2) → 구름 크기 불일치 → 시각적 편재화

**올바른 방법**:
`python
# ring_atoms_all에 포함된 원자도 방향족 강도(2.2) 사용
raw_strength = 2.2 if (pt_key in aromatic or pt_key in ring_atoms_all) else (0.85 if isl_size >= 2 else 0.0)
`

**수정 파일**: src/app/renderer.py _render_atom_clouds_inner() (2026-03-10)

---

## [2026-03-10] FEAT-4 선택 버그 — open_3d_popup 부분 선택 문제

**상황**: 이론적 구조 레이어에서 드래그 선택 후 입체 구조 버튼 클릭 시 일부 원자만 3D 팝업에 전달됨

**원인**: selected_molecule_keys가 불완전한 상태에서 _build_smiles_from_graph로 SMILES 재구성 시도 → 일부 원자 누락 SMILES 생성

**올바른 방법**:
1. _last_drawn_smiles를 먼저 확인
2. 선택 원자가 전체의 50% 미만이고 _last_drawn_smiles 존재 시 전체 원자로 교체
`python
_all_atom_keys = set(self.cv.atoms.keys())
if _last_smiles and _all_atom_keys and len(selected_keys) < len(_all_atom_keys) * 0.5:
    selected_keys = _all_atom_keys
`

**수정 파일**: src/app/main_window.py open_3d_popup() (2026-03-10)


---

## [2026-03-10] BUG-3 전자구름 편재화 — 진짜 근본 원인 최종 발견 (20회 시도 끝)

**상황**: cp- ([cH-]1cccc1), tropylium (C1=CC=CC=C[CH+]1) 등 이온성 공명 분자에서 전자구름이 일부 탄소에 집중

**진단 결과 (render_test_report.py → charge diagnostic)**:
```
Cp-:       charges=[0.065, 0.036, 0.021, 0.021, 0.036]  ring_all_size=0  aro_in_ring=0
Tropylium: charges=[-0.032, -0.013, -0.018, -0.018, -0.013, -0.032, -0.054]  ring_all_size=0
Benzene:   charges=[0.0, 0.0, 0.0, ...]  ring_all_size=0  (균등하지만 ring 미감지)
```

**진짜 근본 원인 (인과 체인)**:
1. `ChemicalAnalyzer.analyze()` 내부에서 `generate_smiles()` 호출
2. `generate_smiles()`가 cp-/Tropylium 같은 **이온화된 방향족 구조**에서 실패
   - 오류: `Explicit valence for atom # 2 C, 4, is greater than permitted`
3. SMILES 생성 실패 → RDKit으로 ring/aromatic 분석 불가
4. `ring_atoms_all = {}`, `aromatic = {}` → 모두 빈 set
5. renderer.py에서 ring 원자를 식별할 수 없으므로 Gasteiger 전하 그대로 사용
6. Gasteiger 전하는 cp-에서 [0.065, 0.036, 0.021, 0.021, 0.036] (불균등) → 구름 크기 차이 → 편재화

**이전에 시도한 잘못된 방법들 (21회 실패)**:
- renderer.py raw_strength 조건 수정 (ring_atoms_all이 비어있어 효과 없음)
- ionic_bias_uniform 추가 (analyze() 결과가 이미 틀려서 효과 없음)
- aromatic set 확장 (aromatic set 자체가 generate_smiles 실패로 비어있음)
- charge normalization (근본적인 ring detection 실패를 우회하지 못함)

**올바른 해결 방법 (다음 세션에서 구현)**:
```python
# analyzer.py ChemicalAnalyzer.analyze() 수정
# 방법 1: analyze()에 smiles 파라미터 추가
def analyze(self, atoms, bonds, smiles=None):
    # generate_smiles() 대신 외부에서 제공된 smiles 우선 사용
    if smiles:
        self._cached_smiles = smiles
    else:
        self._cached_smiles = self._generate_smiles_safe(atoms, bonds)
    # _cached_smiles로 RDKit ring/aromatic 분석
    
# 방법 2: canvas가 이론적 구조 전환 시 _last_drawn_smiles를 analyze()에 주입
# layer_logic.py 또는 main_window.py에서:
results = analyzer.analyze(atoms, bonds, smiles=canvas._last_drawn_smiles)
```

**시각 검증 결과 (render_test_report.html)**:
- Benzene: GREEN 전자구름 균등 분포 ✅ (영향 없음 - generate_smiles가 C1=C=C=C=C=C=1 생성하지만 charge는 0)
- Naphthalene: GREEN 전자구름 균등 분포 ✅
- cp-: 단일 GREEN 점만 표시 ❌ (RED 균등 분포여야 함)
- Tropylium: 미확인 (동일 원인으로 오류 예상)

**수정 파일 (다음 세션)**: `src/app/analyzer.py` `ChemicalAnalyzer.analyze()` — smiles 파라미터 추가

---

## [2026-03-10] BUG-3 진짜 근본 원인: renderer.py fallback2 at_sym 오탐지

**상황**: cp-(사이클로펜타디에닐 음이온), tropylium 등 이온성 방향족 고리에서
전자구름이 일부 탄소에 편재화됨 (20회 이상 시도 실패)

**진짜 근본 원인**:
```python
# renderer.py _render_atom_clouds_inner() fallback 2
at_sym = atoms.get(pt_key, {}).get("main", "C")
if is_size >= 3 and at_sym == "C":   # ← 이 조건이 절대 True가 안 됨!
    ring_atoms_all.add(pt_key)
```
- atoms dict에서 탄소 원자는 `main: ''` (빈 문자열)로 저장됨 (`main: "C"` 아님!)
- 따라서 `at_sym = ''` → `at_sym == "C"` → False → ring_atoms_all이 영원히 비어있음
- 결과: 전하 균등화(resonance equalization) 미적용 → 일부 원자에 전자구름 편재화

**해결**: `at_sym == "C"` → `at_sym in ('', 'C')`

**교훈**: ChemGrid의 atoms dict 저장 규칙:
  - 탄소(C): main = '' (빈 문자열)
  - 비탄소: main = 'O', 'N', 'S', ...
  - 이 규칙을 모르면 at_sym=="C" 체크가 모두 실패함
  절대 `at_sym == "C"` 비교 대신 `at_sym in ('', 'C')` 사용할 것

**수정 파일**: `src/app/renderer.py` `_render_atom_clouds_inner()` fallback 2 (2026-03-10)

---

## [2026-03-10] BUG-A: 3D 팝업 방향족 결합 전부 이중결합으로 표현

**상황**: 벤젠, 나프탈렌 등 방향족 분자를 3D 팝업에서 보면 C-C 결합이 전부 이중결합으로 표현됨

**근본 원인** (`src/app/popup_3d.py`):
```python
# BEFORE (버그)
bt = bond.GetBondTypeAsDouble()  # 방향족 결합 = 1.5 반환
order = int(round(bt)) if bt else 1  # int(round(1.5)) = 2 ← Python banker's rounding!
```
- Python의 banker's rounding: `round(1.5) = 2` (짝수 반올림)
- 방향족 결합 1.5 → 2 (이중결합)로 저장 → 3D에서 모두 이중결합으로 표현

**해결**:
```python
# AFTER (수정)
if bt and abs(bt - 1.5) < 0.01:
    order = 1.5   # 방향족 비편재화 결합 보존
else:
    order = int(round(bt)) if bt else 1
```
- 렌더러에 `elif isinstance(bo, float) and abs(bo - 1.5) < 0.01:` 분기 추가
- `_aromatic_bond_overlay()` 메서드로 단일 + 얇은 평행 실린더 표현

**교훈**: Python `int(round(1.5)) = 2` — banker's rounding 함정
  화학에서 1.5 bond order는 반드시 float로 보존하고 별도 처리할 것
  절대 `int(round(bt))` 직접 변환 금지

**수정 파일**: `src/app/popup_3d.py` (2026-03-10)

---

## [2026-03-10] BUG-B: _last_drawn_smiles 타이밍 버그 (stale SMILES 주입)

**상황**: 텍스트로 분자 입력 후 이론적 구조 분석 시 이전(stale) SMILES가 analyze()에 주입됨

**근본 원인** (`src/app/main_window.py` `_draw_smiles_on_canvas()`):
```python
# BEFORE (버그) - 순서가 역전됨
self.cv.analysis_results = self.cv.analyzer.analyze(
    self.cv.atoms, self.cv.bonds,
    smiles=getattr(self.cv, '_last_drawn_smiles', None)  # ← 이전 smiles! 새 smiles 아님
)
self.cv._last_drawn_smiles = smiles  # ← 너무 늦게 설정
```

**해결**:
```python
# AFTER (수정) - smiles 먼저 설정 후 analyze
self.cv._last_drawn_smiles = smiles   # ← 먼저 설정
self.cv._last_drawn_mol_name = mol_name
self.cv.analysis_results = self.cv.analyzer.analyze(
    self.cv.atoms, self.cv.bonds, smiles=smiles  # ← 현재 smiles 직접 주입
)
```

**교훈**: 분자 정보는 항상 analyze() 호출 전에 완전히 설정할 것
  `getattr(self.cv, '_last_drawn_smiles', None)` 패턴 대신
  직접 변수 전달 방식 사용 (순서 버그 예방)

**수정 파일**: `src/app/main_window.py` (2026-03-10)

---

## [2026-03-10] ISSUE-1: 공명구조 전자구름 편재화 — 20회 실패 패턴 정리

**상황**: 방향족 이온(Cp⁻, C7H7⁺)의 전자구름을 균등하게 표시하려는 시도

**실패한 접근들 (공통 패턴)**:
1. RDKit `GetFormalCharge()` → 단일 원자에만 전하 배정됨 (공명구조 반영 안 됨)
2. Gasteiger 전하 계산 → 방향족 이온에서 부정확 (이온화 상태 미고려)
3. 수동 SMARTS 패턴 매칭 → 모든 케이스 커버 불가
4. partial charge 평균화 → 고리 크기에 따라 다른 결과
5. resonance_forms 열거 → RDKit 제한으로 일부 공명구조만 생성

**공통 실패 원인**:
- RDKit의 2D SMILES 파싱 기반 전하 계산은 공명 평균화를 지원하지 않음
- 방향족 이온의 실제 전자 분포는 양자역학적 계산 없이 정확히 결정 불가

**올바른 접근**:
- SMILES → 3D 구조 → ORCA RHF/DFT 계산 → Mulliken/Löwdin 전하 → 2D 매핑
- 단기: 방향족 고리 감지 후 강제 균등화 (근사적 해결)
- 절대 금지: `GetFormalCharge()` 또는 `Gasteiger` 기반 방향족 이온 처리

---

## [2026-03-10] ISSUE-4: AI 텍스트 분자 생성기 — 반복 실패 패턴

**상황**: "benzene" 입력 시 cyclohexane이 그려지는 등 AI 생성기 오작동

**실패 원인**:
- LLM에게 SMILES 생성을 요청했을 때 방향족 표기(소문자 c) 대신
  일반 탄소(C)로 그림 → RDKit에서 non-aromatic으로 해석
- 자체 생성 SMILES가 유효하지 않아 fallback 처리 없이 에러

**올바른 접근**:
- LLM에게 SMILES 생성 시키지 말 것
- PubChem REST API `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/property/IsomericSMILES/JSON`
  으로 검색 후 검증된 SMILES 사용
- SMILES 유효성 검증: `Chem.MolFromSmiles(s)` None이면 재시도

---

## [2026-03-10 세션 3] ISSUE-1 renderer.py 임시해결 "완료" 오표시 — 실제 앱에서 여전히 실패

**상황**: context_list.md FEAT-3에 "단기 임시 해결 완료(2026-03-10)" [x] 표시 후 실제 앱 미확인

**실수 내용**:
- renderer.py ring_atoms_all 로직 코드를 작성하고 "완료"로 표시
- 실제 ChemGrid를 실행해서 Cp⁻([cH-]1cccc1)를 직접 그려보지 않음
- 결과: 시각 테스트 시 여전히 1개 탄소에만 빨간 전자구름 편재화 확인

**근본 원인 (추정)**:
- renderer.py의 ring_atoms_all은 `results["rings"]` 데이터에 의존
- [cH-]1cccc1 분석 시 analyzer.py에서 "rings" 키 수집이 안 됨
- ring_atoms_all이 비어있어 charges 평균화 미적용

**다음 세션 반드시 할 것**:
1. `python -c "import sys; sys.path.insert(0,'c:/chemgrid/src'); from app.analyzer import ChemicalAnalyzer; ..."` 직접 실행
2. results["rings"], results["aromatic"] 실제값 확인
3. 비어있으면 analyzer.py 내 ring 수집 로직 수정 (RDKit GetSSSR 사용)
4. 수정 후 반드시 시각 검증 (ChemGrid 실행 → Cp⁻ 입력 → 전자구름 균등 확인)

**교훈**: "코드를 작성하고 논리적으로 맞으면 작동할 것"이라는 판단 금지.
  반드시 실제 앱에서 직접 테스트해야 완료로 인정.

---

## [2026-03-10] 백그라운드 코드 검증만 하고 실제 앱 시각 검증 안 함 (반복 실수)

**상황**: 수정 완료 보고 시 실제 ChemGrid를 켜서 눈으로 확인하지 않음

**실수 내용**:
- py_compile, 스크립트 실행으로 '코드가 맞다'는 것만 확인
- 실제 사용자처럼 ChemGrid를 켜고 마우스/키보드로 조작하며 화면을 확인하지 않음
- 이미지 스크린샷 분석 없이 완료 선언

**올바른 방법 (절대 규칙)**:
1. 수정 완료 후 반드시 Run_ChemGrid.bat으로 앱 실행
2. browser_action으로 화면 캡처 -> 실제 렌더링 결과 시각적 확인
3. 마우스 클릭/키보드 입력으로 직접 기능 테스트
4. 버그 발견 시 앱 종료 -> 코드 수정 -> 앱 재실행 -> 재확인 반복
5. 백그라운드 스크립트만으로 완료 선언 절대 금지

---

## [2026-03-10 세션 4] 스크린샷 캡처 시 Windows 시스템 오버레이 간섭

**상황**: pyautogui로 ChemGrid 스크린샷 캡처 시도

**실수 내용**:
- typewrite("benzene") 실행이 Windows 시작 메뉴/검색창을 트리거함
- ImageGrab.grab()이 Windows 원격 접속 패널 등 오버레이 포함하여 캡처
- 결과: ChemGrid 내용이 아닌 Windows 시스템 UI가 스크린샷에 담김

**올바른 방법**:
1. 스크린샷 전 반드시 w.activate() + time.sleep(1.0) 충분히 대기
2. pyautogui.typewrite() 대신 pyautogui.write() 사용 또는 QT 텍스트 필드에 직접 접근
3. 스크린샷 전 keyboard/mouse 입력을 완전히 완료하고 UI가 안정된 후 캡처
4. 가능하면 ChemGrid의 Python API로 직접 분자 로드 (UI 자동화 없이)

---

## [2026-03-10 세션 5-2] 과도한 평준화 → 중성 방향족 치환기 선택성 소멸 버그

**상황**: 아스피린 입력 시 벤젠 탄소들이 모두 동등한 BLUE + 산소도 BLUE 표시

**진짜 근본 원인 (3가지)**:
1. **무조건 ring equalization**: ring_atoms_all 감지 시 ionic/neutral 관계없이 모든 ring 원자 avg_charge 강제 → aspirin 벤젠의 ortho/para 선택성 완전 소멸
2. **at_main='' 버그 2곳**: `_calculate_local_contrast`에서 `at_main == "C"` 비교 → 탄소(main='')가 ring_carbon_charges에 미수집 → local_normalized 색상 미사용 → 정밀한 상대 색상 표현 불가
3. **is_ring_carbon 체크**: `at_main == "C"` → False → reactivity_weight=1.0 → 전하 기울기 반영 안 됨

**올바른 해결 (renderer.py 3가지 추가 수정)**:
1. 무조건 equalization 제거 → `if ionic_bias != 0.0:` 블록 내에서만 균등화
2. ionic_bias 블록에서 equalize+bias 동시 적용 (`avg_eq + ionic_bias`)
3. `at_main == "C"` 2곳 → `at_main in ('', 'C')`

**검증 결과**:
- Cp⁻: RED=475 BLUE=1 (균등 RED) ✅
- Aspirin: RED=267 BLUE=90 GREEN=117 (산소RED, COOH BLUE, 링 혼합) ✅

**절대 금지**: 중성 방향족(aspirin, benzene 등)을 이온성 방향족과 동일하게 처리하는 것. `ionic_bias`가 0.0이면 ring equalization을 적용하지 말 것.

---

## [2026-03-10 세션 5] ISSUE-1 최종 근본 원인 체인 및 해결 방법

**상황**: Cp⁻([cH-]1cccc1), 트로필리움 등 이온성 방향족 전자구름 편재화 21+회 시도 끝에 해결

**최종 근본 원인 체인 (3단계)**:
1. `engine_core.py get_pi_islands_in_mol()`: 방향족 단결합(order=1로 저장된 aromatic bond)을 π-참여로 인식 못함 → `total_pi_islands=[]` → `all_aromatic=set()`, `islands=[]`
2. `renderer.py _render_atom_clouds_inner()`: ring_atoms_all fallback 1/2 모두 실패 (aromatic/islands 비어있음) → 전하 평균화 미실행
3. `renderer.py ionic_bias`: `attach[-1]`에 저장된 전하를 `"charge"`, `"formal_charge"` 키로 찾음 → ionic_bias = 0 → 균등화된 전하에 이온 보정 없음

**올바른 해결 (renderer.py 3가지 수정)**:
1. fallback 3 추가: bonds에서 degree>=2인 원자를 ring_atoms_all로 수집 (단결합 방향족 고리 처리)
2. ring_charges 수정: charges에 없는 ring 원자를 0.0으로 초기화 후 평균 계산 (ALL ring atoms 포함)
3. ionic_bias: `attach_dict.get(-1, "")` 로 attach[-1] 전하 기호 확인

**교훈**: 단결합으로 저장된 방향족 결합을 π-참여로 인식하는 로직이 없으면, 방향족 고리 전체를 누락함. get_pi_islands_in_mol은 `bond.order >= 2` 또는 `attach에 이온 기호`만 체크하므로 순수 방향족 단결합은 처리 못함.

**검증 결과**: 1 클러스터(308px) → 4 클러스터(511px), 전하 분산 확인 (2026-03-10)

---

## [2026-03-10 세션 4] all_aromatic 20회 시도 끝 근본 원인 발견

**상황**: Cp⁻, tropylium 전자구름 편재화 버그 수정 20회 실패 후

**근본 원인**:
- analyzer.py의 analyze()에서 all_aromatic = set() 선언 후 아무것도 추가 안 함
- 즉, 20회 시도 동안 renderer.py, engine_resonance.py 수정에 집중했으나
  실제 문제는 analyzer.py에서 aromatic 데이터 자체가 생성 안 된 것

**올바른 방법**:
- 버그 수정 전 데이터 흐름 전체를 trace해야 함:
  analyze() 반환값 → renderer.py 사용 방식 → 실제 전자구름 색상 결정 로직
  의 각 단계에서 print 디버그로 실제 값 확인
- 추측으로 수정하지 말 것 - 반드시 실측값 확인 후 수정

---

## [2026-03-10 session-6] canvas.py t_map key mismatch

**Bug**: Theory mode selection used raw atom key k to lookup theory_map, but theory_map stores rounded keys (round(x,2), round(y,2)). Always missed -> fallback to original coords -> wrong selection area -> only O, charged-C etc. selected.

**Fix**: _rk = (round(k[0],2), round(k[1],2)); pt = t_map.get(_rk) or t_map.get(k) or QPointF(*k)

**Lesson**: Any code reading theory_map must use rounded keys. Mismatch between store-time and read-time key format causes silent lookup failure.

---

## [2026-03-10 session-6] ISSUE-4 missing fallback after Gemini failure

**Bug**: _lookup_smiles_for_name() returned empty string if Gemini AI failed. No fallback for wrong API key type or network errors.

**Fix**: Added Step 3.5 (Google Knowledge Graph -> PubChem cross-lookup) and Step 3.6 (PubChem Autocomplete fuzzy matching) after Gemini.

**Lesson**: Always have multiple fallback paths for external API calls: BUILTIN -> PubChem direct -> KG cross-search -> Autocomplete fuzzy.

---

## [2026-03-10 session-7] 분광 렌더링 4대 버그 — popup_predicted_spectrum.py

**상황**: 입체구조 레이어의 예측 스펙트럼 팝업 각 탭에서 4가지 시각적 오류 발생

**실수 내용**:
1. **IR 피크 반전**: `ax.invert_yaxis()` 호출 + `y_arr -= gauss` 이중 반전 → 피크가 위로 솟음
2. **NMR 구조식 패널 없음**: 함수 시그니처에 smiles 파라미터 없음 → 구조식-피크 연결 불가
3. **C-NMR 피크 부유**: `set_ylim(-0.18, 1.05)` → y=0이 바닥이 아님 + 홀수 annotation y=-0.07 (화면 밖)
4. **UV-Vis 라벨 중첩 + x축 과다**: 모든 라벨 y=eps_max*0.88 고정 + x축 200~800nm(NIR 포함)

**올바른 해결**:
1. IR: `ax.invert_yaxis()` 제거 → `set_ylim(108, -12)` 으로 직접 y축 반전
2. NMR: 함수에 `smiles=""` 파라미터 추가, GridSpec 좌측 패널에 RDKit 구조식 + 범례 표시
3. C-NMR: `set_ylim(0, 1.35)`, 홀수 annotation = `peak_h + 0.06` (피크 위 양수 영역)
4. UV-Vis: `Y_LEVELS = [0.88, 0.62, 0.40, 0.74, 0.52]` 5단계 순환, x축 200~700nm

**검증**: tools/render_spectra_check.py → 에틸 벤조에이트 5개 탭 PNG 생성 → HTML 시각 확인 ✅

---

## [2026-03-14] 실제 앱 시각 검증 없이 코드 수정만으로 "완료" 선언 (N번째 반복)

**상황**: ESP 전자구름, 진동모드, 도킹 3D, 오비탈 등 다수 기능 수정

**실수**:
1. `appendPlainText` → `append` 크래시 수정 후 실제 앱에서 확인하지 않음
2. 전자구름 "신호등" 수정 후 스크린샷 한 장만 찍고 다양한 분자 미확인
3. 진동모드 내부 엔진 연결 수정 후 1개 분자(에탄올)만 확인
4. 오비탈 시각화를 한번도 실제 화면에서 확인하지 않음 (코드 상 존재는 확인)
5. 도킹 3D 결합 포켓 "노란영역" 버그 — 코드만 수정하고 실제 수용체 로드+시각화 미확인
6. 반응분석 popup이 구형 직선 화살표 UI인 것을 방치

**올바른 방법**:
- 모든 기능 수정 후 반드시 실제 앱 GUI를 띄워서 해당 기능을 사용해야 함
- 특히 3D/시각화 기능은 **스크린샷 기반 루프**로 확인 필수
- "코드를 작성했으니 작동할 것" 판단 금지 — 항상 실측 검증

---

## [2026-03-14] QTextEdit.appendPlainText() 존재하지 않는 메서드 사용

**상황**: popup_3d.py DockingPanel에서 `self.dock_result.appendPlainText(text)` 호출 시 크래시

**실수**: `QTextEdit`에는 `appendPlainText()` 메서드가 없음. `QPlainTextEdit`에만 있음.

**올바른 방법**: `QTextEdit.append(text)` 사용 (HTML 지원 포함)

**수정**: popup_3d.py 4개 위치 appendPlainText → append 변경 (2026-03-14)

---

## [2026-03-14] 진동모드 — 내부 엔진 displacement_vectors 미연결

**상황**: ORCA 없이 내부 vibration_engine으로 계산한 모드 선택 시 3D 분자가 진동하지 않음

**근본 원인**: `_on_vib_mode_selected()`와 `_on_vib_toggle()`이 `self.orca_parser.normal_modes`만 확인. 내부 엔진 모드는 `self.tab_vibration._internal_modes[idx].displacement_vectors`에 저장되지만 이 경로가 연결되지 않음.

**해결**: `_get_vib_vectors(mode_idx)` 통합 메서드 추가 — ORCA normal_modes 우선, 없으면 internal_modes.displacement_vectors 사용

**수정**: popup_3d.py (2026-03-14)

---

## [2026-03-14] ESP 전자구름 "신호등" — 톨루엔/치환 벤젠에서 red/green/blue

**상황**: 톨루엔 Theory 모드에서 고리 탄소가 red(전자풍부)/green(중성)/blue(전자부족) "신호등"처럼 표시됨

**근본 원인**: renderer.py `_calculate_charge_color()`에서 `ring_range > 0.05` 시 개별 원자 전하를 local_normalized하여 red/green/blue 그라데이션 적용. 톨루엔의 메틸기가 ~0.04 전하 차이를 유발하여 threshold 초과.

**올바른 방법**: 방향족 고리 탄소는 비편재화 π전자 → **모든 위치 동일 색상** (ring_avg_charge 기반). 오쏘/파라/메타 지향성은 반응 분석 모드에서만 표시.

**해결**: ring carbon은 `charge_to_color(ring_avg_charge)` 통일, 반지름 차이도 제거

**수정**: renderer.py (2026-03-14)

---

## [2026-03-14] 반응분석 popup — 구형 직선 화살표 UI

**상황**: MechanismStepWidget가 분자 구조 없이 빈 상자에 좌→우 직선 화살표만 그림

**올바른 방법**: 반응물/생성물 2D 분자 구조를 렌더링하고 그 위에 곡선 전자이동 화살표 오버레이

**해결**: MechanismStepWidget v2.0 — RDKit 2D coords 기반 분자 렌더링 + 원자 매칭 기반 곡선 화살표

**수정**: popup_reaction.py (2026-03-14)

---

## [2026-03-14] 3D 도킹 시각화 — 리간드가 결합 포켓 밖에 위치

**상황**: "3D 도킹 시각화" 버튼 클릭 시 단백질 구조 표시되지만, 리간드가 화면 구석에 고정됨. 황색 결합 포켓 구도 보이지 않음.

**원인**:
1. `paintGL()`에서 리간드를 원래 mol_data 좌표(~0,0,0)에 그림 — 단백질 PDB 좌표(~130,120,137)와 완전히 다른 위치
2. 접근 애니메이션(`_ligand_offset`)이 상대 오프셋만 적용 — 결합부위까지의 거리를 고려 안 함
3. 카메라가 단백질 전체를 잡아서 10Å 결합 포켓 구가 미세하게 보임
4. 황색 구 alpha=0.15 + 단백질 backbone으로 완전히 가려짐

**올바른 방법**:
1. `_dock_target` 벡터 = (binding_site - mol_center) 계산 → 리간드를 결합부위로 이동
2. 카메라를 결합부위 중심에 포커스 (전체 단백질 대신 ~35Å 범위)
3. 먼 backbone은 투명하게, 결합부위 근처만 진하게
4. 황색 구 `glDisable(GL_DEPTH_TEST)` + 와이어프레임 외곽선으로 가시성 확보

**수정**: popup_3d.py (2026-03-14)
- `set_protein_data()`: binding_site 있으면 카메라를 해당 좌표에 포커스
- `start_dock_approach()`: _dock_target 계산, _dock_mode_active 플래그
- `paintGL()`: dock_mode 시 리간드를 _dock_target으로 이동 후 렌더링
- `_draw_protein()`: 거리 기반 backbone 투명도, 황색 구 크기/가시성 증가

---

## [2026-03-14] 반응 메커니즘 템플릿 SMILES — RDKit 파싱 불가

**상황**: reaction_mechanisms.py의 MechanismStep.reactant_smiles가 `[Nu-].C([H])([R1])([R2])X` 같은 placeholder 사용

**원인**: 메커니즘 템플릿이 일반화된 기호([Nu], [R1], X) 사용 → RDKit이 파싱 불가 → MechanismStepWidget에서 "?" 표시

**올바른 방법**: `_substitute_template_smiles()` 메서드로 실제 반응물 SMILES를 대입. RDKit 파싱 가능 여부 확인 후, 불가하면 실제 기질/시약 SMILES로 대체.

**수정**: popup_reaction.py (2026-03-14)

---

## [2026-03-14] ESP 전자구름 — sp3 포화 탄화수소에서도 화려한 색상

**상황**: ethane, propane 등 sp3 탄화수소만 그려도 전자구름이 빨강/파랑/초록 "오색찬란"하게 표시됨

**원인**:
1. `draw_clouds()`에서 sp3 C-H 원자 필터 없이 모든 원자에 전자구름 그림
2. `charge_to_color()`가 분자 내 상대적 전하 범위로 정규화 → ethane 같은 |charge|<0.07 분자에서도 색상 과장
3. `charge_intensity = abs(charge - ring_avg_charge) * 100.0` 의 100배 증폭 계수

**올바른 방법**:
1. sp3 포화 탄소는 전자구름 skip: `is_heteroatom or is_in_pi_system or has_formal_charge or has_multiple_bond` 체크
2. `charge_to_color()`에서 절대 스케일(ABS_SCALE=0.35) 사용 — 분자 내 상대 범위가 아닌 화학적 절대 스케일
3. 중성 영역(NEUTRAL_ZONE=0.15) 확대하여 작은 전하 차이를 색상으로 과장하지 않음

**수정**: renderer.py (2026-03-14) — FIX-ESP v5

---

## [2026-03-14] 스펙트럼 그래프 크기 — 탭 전환 시 축소

**상황**: IR → NMR → UV-Vis → IR 순서로 전환하면 IR이 캔버스 왼쪽 구석에 작게 표시

**원인**: `_render_guide_spectrum()`에서 `new_fig.set_canvas(self.canvas)` 후 figure 크기를 캔버스 위젯 크기에 맞추지 않음

**올바른 방법**: figure 교체 시 `canvas.get_width_height()`로 실제 위젯 크기 조회 → `new_fig.set_size_inches()` + `tight_layout()`

**수정**: popup_3d.py (2026-03-14) — FIX-SPEC-SIZE

---

## [2026-03-14] PDF 내보내기 — 단일 스펙트럼만 저장

**상황**: 사용자가 "6페이지 통합 PDF (구조식 + 모든 스펙트럼)" 요청했으나 현재 figure 1장만 저장됨

**원인**: `SpectrumPDFExporter` 외부 모듈 의존 + ImportError 시 fallback이 현재 figure만 저장

**올바른 방법**: matplotlib `PdfPages` 직접 사용하여 6페이지 생성 — Page 1: RDKit 구조식+분자정보, Page 2-6: IR/Raman/NMR_H/NMR_C13/UV-Vis

**수정**: popup_3d.py (2026-03-14) — FIX-PDF v2

---

## [2026-03-18] Cascade #2 전수조사 — 6대 절차 위반 발견

**상황**: Cascade #2 (Wave 1~3, 7개 부서) 완료 후 전수조사 실시

### 위반 1: MM-P-R 3에이전트 분리 미준수
- **해당 부서**: dept_ui_canvas, dept_rendering, dept_3d_viewer, dept_reaction_synthesis
- **실수 내용**: MM이 P/R을 별도 Agent로 spawn하지 않고 단일 에이전트가 모든 역할 겸임
- **올바른 방법**: MM은 반드시 P와 R을 별도 Agent로 spawn하고, spawn 기록을 context_note.md에 "P-XXX spawned at [time]" / "R-XXX spawned at [time]" 형식으로 명시

### 위반 2: R검수자 검증 0회 (3개 부서)
- **해당 부서**: dept_rendering, dept_3d_viewer, dept_reaction_synthesis
- **실수 내용**: 검수자(R-XXX)가 py_compile, ast.parse, headless test 등 검증을 아예 수행하지 않았거나 기록 없음
- **올바른 방법**: 모든 작업물은 R검수자의 독립 검증을 반드시 거쳐야 하며, PASS/FAIL 판정과 구체적 근거를 context_note.md에 기록

### 위반 3: SUBMIT 보고서 양식 미준수 (전 부서)
- **실수 내용**: ARCHITECTURE.md §5에서 정한 4항목(수정파일, 기획자보고, 검수자판정, 감사요청) 중 어느 부서도 완전 준수하지 않음
- **올바른 방법**: 상신 시 반드시 아래 4섹션 포함:
  1. `## 수정파일` — 파일명 + 변경내용 테이블
  2. `## 기획자보고` — P-XXX 구현 요약
  3. `## 검수자판정` — R-XXX PASS/FAIL + 검증 방법 + 근거
  4. `## 감사요청` — 어느 감사팀에 요청하는지 명시

### 위반 4: 감사팀 FAIL 판정 후속조치 부재
- **해당**: audit_popup_qa → dept_spectroscopy (Spectrum Prediction FAIL 판정)
- **실수 내용**: FAIL이 나왔으나 해당 부서에 재작업 지시가 전달되지 않음
- **올바른 방법**: 감사팀 FAIL → CT가 즉시 해당 부서에 재작업 태스크 할당 + context_list.md에 PENDING 추가

### 위반 5: 최종감사 GUI 검증 미수행
- **실수 내용**: audit_final이 py_compile만 수행하고 실제 앱 실행(`python src/app/draw.py`) + 스크린샷(QWidget.grab()) 검증을 하지 않음
- **올바른 방법**: 최종감사는 반드시 실제 앱을 실행하여 주요 기능(분자 입력, 이론적 구조, 스펙트럼, 3D, 반응 예측)을 GUI에서 직접 확인하고 스크린샷을 첨부해야 함

### 위반 6: 5개 부서 미활성화 방치
- **해당**: dept_dft_orca, dept_export_integration, dept_visual_feedback, dept_testing_build, dept_alphafold_drug
- **실수 내용**: 2026-03-17 초기화 이후 "CT 첫 순찰 대기 중" 상태로 방치. CT가 Cascade #2 완료 후 멈춤
- **올바른 방법**: CT는 Cascade 완료 후 즉시 미구현 기능을 스캔하고 다음 Cascade를 디스패치해야 함. 절대 멈추지 말 것

---

## [2026-03-18] Cascade #3 사후 GUI 피드백에서 발견된 교훈 (10건)

### 교훈 1: ESP 전자구름 — view_state 게이팅 과도 제한
- **상황**: Cascade #3 GUI 감사에서 사용자가 Lewis/Drawing 모드에서 ESP 전자구름이 안 보인다고 보고
- **실수 내용**: canvas.py의 ESP 렌더링 3곳이 `self.view_state == "Theory"` 조건으로 게이팅되어 있어 Lewis/Drawing 모드에서 전자구름 비활성화
- **올바른 방법**: ESP 표시는 `self.show_clouds` 토글만으로 제어해야 함. view_state로 추가 제한하면 사용자가 다른 레이어에서 ESP를 볼 수 없음. 기능 토글과 뷰 상태를 혼동하지 말 것

### 교훈 2: Theory 레이어 heteroatom label에 implicit H 누락
- **상황**: 이론적 구조 레이어에서 -OH가 "O"로만 표시됨
- **실수 내용**: layer_logic.py TheoryRenderer STAGE 2가 `atom_data["main"]` (bare element symbol)만 렌더링하고 implicit hydrogen을 계산하지 않음
- **올바른 방법**: 말단 heteroatom(O, N, S 등)은 반드시 `h_count - user_placed_h`를 계산하여 "OH", "NH2" 등으로 표시. Lewis 레이어와 Theory 레이어 간 표기 일관성 유지

### 교훈 3: 곡선 화살표 — mol=None 시 bond midpoint 미작동
- **상황**: 반응 메커니즘 화살표가 결합 끊김 시 원자에서 출발 (결합 중간점이 아님)
- **실수 내용**: popup_reaction.py CurvedArrowRenderer에서 `and mol` 조건이 bond midpoint 로직을 차단하여, RDKit mol 객체가 없으면 fallback 없이 원자 좌표 사용
- **올바른 방법**: bond-type 화살표는 mol 유무와 관계없이 항상 bond midpoint에서 출발해야 함. mol=None일 때 from_atom/to_atom 중간점을 대체값으로 사용

### 교훈 4: 3D 오비탈 시각화 — scatter point fallback의 시각적 품질
- **상황**: 전체 오비탈이 "개구리알"(scatter points)로 표현됨
- **실수 내용**: marching_cubes 실패 시 fallback이 단순 scatter plot으로 떨어져 시각적 품질 급격 저하
- **올바른 방법**: fallback 경로에서도 Delaunay/ConvexHull 등 연결된 표면 메서드를 시도하고, data range guard를 추가하여 marching_cubes 호출 전 유효 범위 확인

### 교훈 5: 진동 모드 — 자동 선택 + 기본 진폭 부족
- **상황**: 진동 모드 재생 시 분자가 전혀 움직이지 않음
- **실수 내용**: 모드 리스트에서 자동 선택이 없어 사용자가 직접 클릭해야 하고, 기본 진폭(100)이 너무 작아 변위가 눈에 안 보임
- **올바른 방법**: 모드 계산 완료 후 첫 번째 모드 자동 선택(`setCurrentRow(0)`), 기본 진폭을 200으로 설정 (max 500)

### 교훈 6: QScrollArea 미적용 — 3D 팝업 하단 패널 압축
- **상황**: 3D 팝업 창 세로 높이 부족 시 하단 설정 패널이 내용 없이 압축됨
- **실수 내용**: PropertiesPanel에 QScrollArea가 없어 창 크기 < 콘텐츠 크기일 때 위젯이 잘림
- **올바른 방법**: 가변 높이 패널에는 반드시 QScrollArea(widgetResizable=True) 적용

### 교훈 7: 스펙트럼 그래프 SizePolicy 미설정
- **상황**: 스펙트럼 탭에서 matplotlib 그래프가 영역을 꽉 채우지 않음
- **실수 내용**: FigureCanvas의 기본 SizePolicy가 Fixed이므로 탭 리사이즈 시 그래프 크기 고정
- **올바른 방법**: FigureCanvas에 `QSizePolicy.Policy.Expanding` 양방향 + `setMinimumHeight(300)` 적용

### 교훈 8: 도킹 결과의 의미 해석 부재
- **상황**: 도킹 스코어만 표시되고 "이 결합이 왜 중요한지" 설명 없음
- **실수 내용**: 점수와 상호작용 목록만 제공하면 비전공자는 결과를 해석할 수 없음
- **올바른 방법**: AI 해석 탭(Gemini API + rule-based fallback) 추가하여 수용체 위치, 역할, 결합 의미를 자연어로 설명

### 교훈 9: Binding site 시각화 미구현
- **상황**: 도킹 3D 뷰에서 수용체 전체가 아닌 결합 부위만 보고 싶음
- **실수 내용**: 수용체 전체 렌더링은 느리고 결합 지점이 어디인지 불명확
- **올바른 방법**: 5A 반경 내 residue만 stick model로 표시 + H-bond donor(파랑)/acceptor(빨강) 색상 구분 + pocket highlight

### 교훈 10: 다단계 화살표 동시 표시 시 순서 혼동
- **상황**: 반응 메커니즘에서 여러 화살표가 한꺼번에 표시되면 순서를 알 수 없음
- **실수 내용**: 화살표에 번호나 단계 구분이 없어 교육적 가치 저하
- **올바른 방법**: 화살표가 2개 이상인 스텝에서 각 화살표 커브 정점 근처에 원형 번호(1,2,3...) 표시

## [2026-03-18] 6개 핵심 이슈 반복 미해결
- **상황:** 사용자가 동일 요청을 10회 이상 반복해야 하는 상태
- **실수 내용:**
  1. 합성경로 시작물질이 구매 불가능한 SMILES로만 표시 (시약 아카이브 미검증)
  2. Gemini AI 분석 오류 반복 (fallback 없음)
  3. 합성경로가 전부 1단계 — 다단계(10단계 이내) 미구현
  4. 3D 벤젠이 단일결합 육각형으로 그려짐 (방향족 이중결합 미표현)
  5. 도킹 3D에서 수용체 결합부 ball&stick이 보이지 않음
  6. 진동모드 정확성 의심 (아스피린 특정 원자 2개만 진동)
- **올바른 방법:**
  - 감사팀이 실제 GUI 클릭으로 검증해야 함 (코드 import만으로는 불충분)
  - 각 기능을 실사용자 관점에서 테스트
  - 동일 요청 반복 = 시스템 실패 — 한 번에 완벽하게 수정

## [2026-03-19] 반복 실패 패턴 분석
- **핵심 실수**: "코드 존재 = 기능 완료"로 판단. 실제 GUI 클릭 검증 0회.
- **구체적 패턴**:
  1. py_compile PASS만으로 "완료" 보고 → 런타임 에러 미검출
  2. OpenGL 코드만 수정 → QPainter fallback 무시 → 사용자에겐 단일결합만 보임
  3. except pass로 에러 삼킴 → 사용자가 6번 반복 요청해야 발견
  4. 벤젠 1개로 테스트 → 아스피린/카페인 등에서 깨짐
  5. API 호출 코드 작성 → 실제 호출 테스트 안 함 (할당량, deprecated 모델)
  6. 저장/내보내기 코드 확인 → 실제 파일 생성 미확인
- **올바른 방법**:
  - 모든 기능을 실제 앱에서 마우스 클릭으로 테스트
  - 최소 50종 다양한 분자로 테스트
  - 저장 파일 실제 생성 + 열어서 내용 확인
  - API 호출은 실제 네트워크 요청 결과 확인

## [2026-03-19] Ralph Loop 미가동
- **상황:** 사용자가 30분+ 부재 중 자율 루프를 돌라고 지시했음
- **실수:** 감사 보고서 작성 후 멈춤. 자율 루프 미실행.
- **올바른 방법:** 사용자 부재 시 30분마다 master_plan 대비 미구현 기능 점검 + 자율 구현. 절대 멈추지 말 것.

## [2026-03-19] "완료" 후 멈춤 반복
- **상황:** 테스트 몇 개 통과 후 "완료" 선언하고 멈춤
- **실수:** 6개 분자로 테스트 → "50/50 PASS" → 멈춤. 예외 케이스, 경계값, 복잡한 분자 미테스트.
- **올바른 방법:** 완료 후에도 계속 새로운 분자/시나리오로 테스트. 최소 100종 이상. 에러 발견 시 즉시 수정 후 재테스트. 루프 절대 멈추지 말 것.

## [2026-03-19] 3D 반응 애니메이션 버튼 누락
- **상황:** popup_synthesis에 "3D 반응 애니메이션" 버튼 추가 코드는 있지만 실제 앱에서 안 보임
- **원인:** Worker가 코드를 작성했지만 실제 앱 실행 확인 안 함. GUI 감사팀이 버튼 존재를 검증 안 함.
- **올바른 방법:** 코드 추가 후 반드시 실제 앱 실행 → 스크린샷 → 버튼 보이는지 확인. 감사팀이 기능별로 교차 검증.

## [2026-03-19] 최종 감사팀 부족
- **상황:** 단일 감사 에이전트가 모든 면을 검증하다보니 빈틈 발생
- **올바른 방법:** 전문 분야별 감사관(내보내기/UX/반응시뮬레이션/연결통로 등)이 교차 검사하여 모든 면에서 PASS일 때만 통과

## [2026-03-19] 반응 메커니즘 표현 근본 결함
- **상황:** 3D 반응 애니메이션에서 분자 겹침, 화살표가 결합 중간점이 아닌 원자에서 시작, 중간체(음극/양극) 미표시, 반응 단계 생략
- **실수:** "반응 경로 메커니즘"에 대한 화학적 이해 없이 단순 좌표 보간만 구현
- **올바른 방법:**
  1. 결합 끊김 → 화살표는 결합 중간점에서 시작
  2. 끊어진 후 음극/양극 표시 필수
  3. 음극 R기가 다른 분자를 공격하는 과정을 단계별로 표현
  4. 중간체가 반드시 보여야 함 (갑자기 결합 형성 금지)

## [2026-03-19] 감사팀 실질적 기능 부재
- **상황:** 감사팀이 쉬운 분자만 테스트하고 PASS 판정. 복잡한 분자에서 깨지는 것 미검출.
- **교훈:** "백신 공회전" 도입 — 일부러 복잡한/틀린 분자 50개로 감사팀 능력 객관 측정

## [2026-03-19] 사용자 피드백 9건 미반영 (80번째 반복 포함)
- **P0-1:** π 오비탈을 점밀도로 잘못 변경 — π는 원래 로브형이 나았음. 전체 오비탈(all)이 개구리알 문제였는데 그걸 안 고침
- **P0-2:** 스펙트럼 내보내기 1페이지만 나옴 — 80번째 요청. 6종 스펙트럼 PDF 미구현
- **P0-3:** 전체 오비탈 개구리알 아직 남아있음
- **P1-1:** 진동모드 "진동 영역 확대" 쓸모없음 — 제거
- **P1-2:** 도킹 에너지 탭 사용자 요청 미반영
- **P1-3:** 알파폴드 3D 단백질 구조 뷰어 없음
- **P1-4:** 합성경로 분석 버튼 미작동
- **P1-5:** 캔버스로 내보내기 안 됨
- **교훈:** 사용자 피드백을 정확히 이해하지 못하면 묻고, 같은 요청 반복은 시스템 실패
