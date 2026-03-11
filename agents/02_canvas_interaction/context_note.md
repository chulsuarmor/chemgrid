# 📝 🖱️ 캔버스/그리기 — Technical Notes
## 기술적 판단 및 결정 기록

### [2026-02-28] MoleculeCanvas 분리 결정

**결정:** draw.py에서 MoleculeCanvas를 canvas.py로 분리

**근거:**
- draw.py가 Agent 01(UI)과 공유 파일이므로 MoleculeCanvas 부분만 독립 모듈로 분리
- MainWindow는 `from canvas import MoleculeCanvas, CanvasMode, get_coord_key`로 사용

**canvas.py 구조:**
- `CanvasMode` 클래스 (Drawing/Lewis/Theory 상수)
- `get_coord_key()` 함수 (0.01 정밀도 좌표 키)
- `MoleculeCanvas(QWidget)` 클래스 (마우스, 키보드, paintEvent, Undo/Redo, 줌/팬)

### [2026-02-28] 조준선 3중 렌더링 수정 (M1)

**문제:** paintEvent에서 `CloudRenderer.draw_crosshairs_v32()`가 3곳에서 호출
1. LAYER 3 (Lewis/Theory 원형 확장) — early return 전
2. LAYER 4 (Drawing 모드) — p.restore() 전
3. 최상위 Z-INDEX — paintEvent 끝

**분석:**
- Lewis/Theory 모드: LAYER 3에서 호출 후 `if not is_animating: return`으로 #3 미도달 → 1회만 호출 (정상)
- Drawing 모드: LAYER 4에서 호출 + #3에서 또 호출 → **2회 렌더링 (버그)**
- 애니메이션 중: Lewis/Theory에서 #1 호출 후 return 없이 → #3까지 도달 → **2회 렌더링 (버그)**

**수정:**
- LAYER 3, LAYER 4에서 조준선 호출 제거
- LAYER 3의 early return 제거 (최상위 Z-INDEX까지 항상 도달하도록)
- 최상위 Z-INDEX에서만 1회 호출 (모든 모드에서 동일)

### [2026-02-28] 포터블 경로 수정 (C5)

**문제:** `_analyze_dft_electron_density()`에서 절대 경로 하드코딩
```python
Path(r"C:\Users\김남헌\Desktop\organicdraw\orca_calcs\input.out")
```

**수정:** `__file__` 기반 상대 경로로 교체
```python
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
orca_out_candidates = [
    _SCRIPT_DIR / "orca_calcs" / "input.out",
    _SCRIPT_DIR / "input.out",
]
```

### [2026-02-28] 고리 이중결합 안쪽 방향 수정 (U5)

**문제:** `draw_bond()`에서 이중결합의 짧은 선(offset line)이 고리 안쪽을 향하지 않음.
기존 코드는 `neighbors` 리스트의 평균 위치로 방향을 결정했으나, 이것이 항상 고리 내부를 가리키지는 않았음.

**해결 방법:** `coord_utils.py`에 고리 감지 유틸 함수 2개를 추가하고 `canvas.py`에서 사용.

1. `find_shortest_ring_through_bond(k1, k2, bonds)` — BFS로 결합(k1,k2)를 포함하는 최소 고리 탐색 (최대 8원환)
2. `get_ring_center_for_bond(k1, k2, bonds)` — 고리의 중심점(QPointF) 반환

**적용 로직 (canvas.py `draw_bond()`):**
```python
ring_center = get_ring_center_for_bond(k1, k2, self.bonds)
if ring_center is not None:
    # 고리 결합: 결합 중점 → 고리 중심 방향으로 nx,ny 정렬
    mid = (p1 + p2) / 2
    dot = nx * (ring_center.x() - mid.x()) + ny * (ring_center.y() - mid.y())
    if dot < 0: nx, ny = -nx, -ny
else:
    # 비고리 결합: 기존 neighbors 평균 기반 방향
```

**검증:** 벤젠(6원환), 사슬(비고리), 사각형(4원환), 방향벡터 dot product — 4건 모두 통과.

**설계 판단:** Agent 03이 `layer_logic.py`에 유사 함수를 구현 예정이었으나 미구현 상태. `.clinerules`에 따라 `coord_utils.py`(Agent 02 도메인)에 직접 구현. Agent 03/05가 나중에 `from coord_utils import get_ring_center_for_bond`로 재활용 가능.

### [2026-02-28] Dead Code 잔류 문제

**상황:** draw.py에 구 MoleculeCanvas 코드가 `_OBSOLETE` 클래스로 ~600줄 남아있음
**원인:** replace_in_file 도구로 대형 클래스 전체 제거가 어려움 (시작/끝 경계만 교체 가능)
**영향:** 기능에 영향 없음 (`MainWindow`는 `from canvas import MoleculeCanvas` 사용)
**대응:** Agent 10 (테스트/빌드)에서 통합 시 `_OBSOLETE` 클래스 완전 삭제 요청

---

## 🧊 입체 구조(3D) 연동 — Agent 02 관점 Technical Notes

### [2026-02-28 23:43] 캔버스 → 3D 팝업 데이터 플로우 분석

#### 1. 전체 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│ draw.py (MainWindow)                                      │
│   btn_3d.clicked → open_3d_popup() [🔴 U2: 미연결!]       │
│   btn_spectrum/nmr/uvvis/md/orbital [🔴 U3: 3D탭으로 이동] │
├──────────────────────────────────────────────────────────┤
│ canvas.py (MoleculeCanvas)                                │
│   self.atoms  ─┐                                          │
│   self.bonds  ─┼──→  Molecule3DData(atoms, bonds,         │
│   self.smiles ─┤       theory_data, smiles, orca_parser)  │
│   analysis_results["theory_data"] ─┘                      │
│                                                           │
│   Hooks:                                                  │
│   ├─ on_theory_layer_interaction()                        │
│   │    → phase_manager.on_theory_layer_interaction()      │
│   ├─ on_orca_calculation_complete(result)                 │
│   │    → _analyze_dft_electron_density() → dft_density_map│
│   └─ on_molecule_updated()                                │
│        → phase_manager.on_molecule_updated()              │
├──────────────────────────────────────────────────────────┤
│ popup_3d.py (Agent 06 전담)                                │
│   Molecule3DData: 좌표 우선순위                             │
│     1. ORCA parser (DFT 최적화 geometry)                   │
│     2. ORCA xyz dict                                      │
│     3. RDKit ETKDG+MMFF (SMILES → 3D)                    │
│     4. VSEPR Z축 추정                                      │
│     5. Flat 2D (Z=0)                                      │
│                                                           │
│   Molecule3DPopup: 통합 뷰어                               │
│     ├─ OpenGL Ball-and-Stick / Space-Filling              │
│     ├─ QPainter 2.5D 폴백                                 │
│     └─ 탭: [📊 속성] [📈 스펙트럼] [🎵 진동모드] [📝 AI분석]  │
└──────────────────────────────────────────────────────────┘
```

#### 2. 데이터 핸드오프 상세

**canvas.py가 제공하는 데이터:**

| 데이터 | 타입 | 설명 |
|--------|------|------|
| `self.atoms` | `Dict[Tuple[float,float], Dict]` | `{(x,y): {"main":"C","attach":{...}}}` |
| `self.bonds` | `Dict[Tuple[Tuple,Tuple], int\|tuple]` | `{((x1,y1),(x2,y2)): 1\|2\|3\|(p1,p2,"Wedge")}` |
| `self.analysis_results["theory_data"]["map"]` | `Dict[Tuple, QPointF]` | 원본좌표→이론좌표 매핑 |
| `self.get_smiles()` | `str` | RDKit 기반 SMILES (3D 좌표 생성 시드) |

**Molecule3DData 소비 방식:**
```python
# canvas.py에서 생성 (phase_integration 또는 직접 호출)
mol_data = Molecule3DData(
    atoms=self.atoms,           # 원자 딕셔너리
    bonds=self.bonds,           # 결합 딕셔너리
    theory_data=analysis_results.get("theory_data", {}),  # 이론좌표
    smiles=self.get_smiles(),   # RDKit 3D 생성용
    orca_parser=None,           # ORCA 결과 (있으면)
)
```

**핵심:** `Molecule3DData._build_data()`에서 `theory_data["map"]`의 QPointF를 2D 기본 좌표로 사용하고, Z축은 우선순위에 따라 결정됨.

#### 3. 🔴 발견된 문제점 (Agent 01/06 담당)

##### U2: `btn_3d.clicked.connect()` 누락 — 3D 팝업 미작동
```python
# draw.py MainWindow.__init__()에서:
self.btn_3d = QPushButton("입체 구조", self)  # 버튼 생성됨 ✅
# 하지만 .clicked.connect() 호출이 없음! ❌
# btn_lewis, btn_theory처럼 연결 필요:
# self.btn_3d.clicked.connect(self.open_3d_popup)
```
**담당:** Agent 01 (UI/디자인)이 `open_3d_popup()` 메서드 추가 및 연결
**Agent 02 제공물:** `canvas.py`의 `get_smiles()`, `self.atoms`, `self.bonds`, `self.analysis_results`

##### U3: Theory 레이어 분석 버튼 → 3D 팝업 탭으로 이동
현재 draw.py에 5개 독립 분석 버튼이 Theory 모드에서 떠있음:
- `btn_spectrum` → IR/Raman → 3D 팝업 [📈 스펙트럼] 탭으로
- `btn_nmr` → NMR → 3D 팝업에 추가 탭으로
- `btn_uvvis` → UV-Vis → 3D 팝업에 추가 탭으로
- `btn_md` → MD → 3D 팝업에 추가 탭으로
- `btn_molorbital` → 오비탈 → 3D 팝업 [🔬 오비탈] 탭으로

**담당:** Agent 01 (버튼 제거) + Agent 06 (탭 통합)

#### 4. canvas.py Phase Integration Hooks 설계

`canvas.py`에 3개의 Hook이 있으며 `phase_integration.py`의 `PhaseIntegrationManager`를 통해 3D 시스템에 연결:

| Hook | 트리거 시점 | 동작 |
|------|-----------|------|
| `on_molecule_updated()` | 마우스 릴리즈 후 | 분자 수정 → Phase B-D 업데이트 |
| `on_theory_layer_interaction()` | Theory 전환 시 | 3D 팝업 준비 (데이터 전달) |
| `on_orca_calculation_complete(result)` | ORCA 완료 시 | ESP 시각화 + DFT 밀도 분석 |

**현재 상태:** `phase_integration.py`가 없으면 Hook은 no-op (안전하게 무시).

#### 5. SMILES 생성 (`get_smiles()`) — 3D 좌표 생성의 핵심

`canvas.py`의 `get_smiles()` 메서드가 캔버스의 원자/결합을 RDKit Mol로 변환:

```python
# 변환 체인:
canvas atoms/bonds
  → RDKit RWMol (editmol.AddAtom / editmol.AddBond)
  → Chem.SanitizeMol()
  → Chem.MolToSmiles()
  → SMILES 문자열
  → Molecule3DData에서 generate_3d_coords_rdkit(smiles) 호출
  → ETKDG+MMFF 3D 좌표 생성
```

**주의점:**
- `get_smiles()`는 `self.atoms`에 `"main"` 키가 빈 문자열이면 `"C"`로 간주 (탄소 기본값)
- 웨지/대쉬 결합 정보는 SMILES에 반영되지 않음 (입체 정보 손실)
- RDKit SanitizeMol 실패 시 `"C"` 반환 (안전한 폴백)

#### 6. 좌표 정밀도 — Agent 02/06 인터페이스 규약

| 구간 | 정밀도 | 비고 |
|------|--------|------|
| canvas.py 원자 키 | `round(coord, 2)` | `get_coord_key()` 강제 |
| theory_data["map"] 좌표 | QPointF (부동소수점) | 3D 변환 시 `round(x, 2)` 적용 |
| Molecule3DData 내부 | `round(x, 2)` | `_build_data()`에서 강제 |
| ORCA parser 좌표 | `round(x, 2)` | `_parse_final_geometry()`에서 강제 |
| coord_utils.py 유틸 | `round_point_3d(pt, 2)` | 3D 확장 지원 |

**규약:** 모든 좌표 핸드오프는 0.01 단위. `coord_utils.py`의 `round_point_3d()`를 3D 전용 유틸로 사용 가능.

#### 7. Agent 06 popup_3d.py 아키텍처 요약 (참조용)

Agent 06이 완성한 `popup_3d.py` (~1400줄) 구조:

```
Section 1:  CPK 색상/반지름 데이터 (Jmol 표준, 22원소)
Section 2:  3D 좌표 생성 (RDKit ETKDG, VSEPR Z추정)
Section 3:  OrcaOutputParser (geometry, frequencies, modes, Mulliken)
Section 4:  PubChemClient (REST API, SMILES→IUPAC/CAS/물성, 캐시)
Section 5:  GeminiAnalyzer (google.generativeai, 한국어 분석)
Section 6:  Molecule3DData (좌표 우선순위 5단계, 결합길이/각도 측정)
Section 7:  OpenGL 렌더러 (BallAndStick, SpaceFilling, glMaterialfv)
Section 8:  QPainter 2.5D 폴백 (PyOpenGL 없을 때)
Section 9:  Molecule3DViewer (QOpenGLWidget, 진동 애니메이션, QTimer)
Section 10: 탭 패널 (PropertiesPanel, SpectrumPanel, VibrationPanel, AIAnalysisPanel)
Section 11: Molecule3DPopup (통합 팝업, 스플리터, ORCA 로드)
```

**Agent 02가 알아야 할 핵심:**
- `Molecule3DData(atoms, bonds, theory_data, smiles, orca_parser)` — 캔버스 데이터 수신 인터페이스
- `Molecule3DPopup(mol_data)` — 팝업 생성 시 mol_data만 전달하면 됨
- ORCA 파일은 팝업 내에서 별도 로드 가능 (📂 버튼)

### [2026-03-01] Phase 6-3: Theory 모드 분자 선택 UX 개선

**Manager 긴급 명령 v3 — 3건 모두 완료**

**명령 1: 점선 테두리 (DashLine)**
- `_find_atom_at_theory(l_pos)`: Theory 좌표계(`theory_data["map"]`) 기준 원자 탐색, 반경 18px
- `_select_molecule_at(atom_key)`: bonds 기반 BFS로 연결된 전체 분자 원자 집합 탐색
- `_compute_molecule_bbox()`: theory_data["map"] 좌표 기반 QRectF, PADDING=25px
- paintEvent LAYER 3에 `QPen(QColor(33,150,243), DashLine)` + `drawRoundedRect(bbox, 8, 8)` 렌더링
- `p.setClipping(False)`로 애니메이션 클리핑 영역 밖에서도 표시

**명령 2: IUPAC명 표시**
- `_get_molecule_smiles()`: 선택된 분자 원자/결합만으로 RDKit SMILES 생성 (전체 캔버스가 아님)
- `_fetch_molecule_name()`: PubChem REST API (`/rest/pug/compound/smiles/{smiles}/property/IUPACName/JSON`) 동기 호출, timeout=5s
- 네트워크 실패 시 SMILES 자체를 폴백으로 표시
- SMILES는 `urllib.parse.quote()`로 URL 인코딩 처리

**명령 3: 바닥 클릭 해제**
- `mousePressEvent`에서 `view_state == "Theory"` + `LeftButton` 시 전용 분기
- 원자 클릭 → `_select_molecule_at()`, 빈 영역 클릭 → `_deselect_molecule()`
- `molecule_selected = pyqtSignal(bool)` 시그널: Agent 01이 `btn_3d.setEnabled()` 연동에 사용

**설계 판단:**
- Theory 모드에서는 기존 Drawing 모드 마우스 로직을 완전 건너뜀 (`return`으로 조기 탈출)
- PubChem API 동기 호출은 UI 블록 가능성이 있으나, timeout=5s로 제한하고 단순 구현 우선
- `_get_molecule_smiles()`를 별도 메서드로 분리: 다중 분자 캔버스에서 선택된 분자만의 SMILES 생성
- BFS 인접리스트는 `self.bonds` 키에서 직접 구축 (analysis_results["adj"]와 독립적으로 안전하게 동작)

### [2026-03-01] Phase 6-3 v4: 신규 기능 4건 구현

**v4 명령1: +/- 기호 → charge 필드 분리**
- **문제:** Positive/Negative 도구가 `atoms[k]["attach"][d]`에 `"+"`/`"-"` 저장 → Lewis/Theory에서 형식전하와 이중 표시
- **해결:** `atoms[k]["charge"] = "+"/"-"` 별도 필드에 저장, `main` 원소 기호 보존
- `draw_atom_group()`에서 charge 필드가 있으면 원소 기호 우상단에 작은 위첨자(9pt)로 렌더링
- `+`는 빨간색(200,0,0), `-`는 파란색(0,0,200) 색상 구분
- 기존 attach의 `+`/`-` 렌더링 코드는 호환성을 위해 유지 (이미 attach에 저장된 기존 데이터 대응)

**v4 명령3: 반응 화살표 도구 (Arrow)**
- `self.arrows`: `[(QPointF_start, QPointF_end), ...]` — 확정된 화살표 리스트
- `mousePressEvent`: Arrow 모드에서 드래그 시작점 기록
- `mouseMoveEvent`: 동서남북 4방향 스냅 (`abs(dx) >= abs(dy)` → 수평, 아니면 수직)
- `mouseReleaseEvent`: 최소 길이 10px 필터 후 arrows에 추가
- `paintEvent`: 모든 뷰 모드(Drawing/Lewis/Theory)에서 렌더링 — 확정(검은 실선), 고스트(파란 점선)
- `_draw_arrow()`: 직선 + 삼각형 화살촉 (head_len = min(12, length*0.3))
- `erase()`: 화살표 중점 기준 지우기 지원
- Undo/Redo: `save_state`에 `"ar"` 키로 포함

**v4 명령4: 텍스트 상자 도구 (Text)**
- `self.text_boxes`: `[{"pos": QPointF, "text": str, "font_size": int}, ...]`
- `_handle_text_click()`: 기존 상자 선택(hit_radius=30) 또는 새 상자 생성
- `keyPressEvent`: Text 모드 + 편집 중일 때 키 입력을 상자에 전달 (Backspace/Enter/Esc/문자)
- `_render_subscript()`: `CH_3` → `CH₃` (유니코드 아래첨자 `₀₁₂₃₄₅₆₇₈₉`)
- `_draw_text_boxes()`: 빨간 점선 테두리 + 흰색 반투명 배경 + 편집 중 커서(|) 표시
- **Text 모드가 아닐 때는 텍스트 상자 렌더링 스킵** (사용자 요구 사항)
- Undo/Redo: `save_state`에 `"tb"` 키로 포함

**v4 명령5: 비공유전자쌍 user_lp 플래그**
- LonePair 모드로 `attach[d] = ".."` 저장 시 동시에 `atoms[k]["user_lp"].add(d)` 추가
- `user_lp`: `set()` — 사용자가 직접 그린 비공유전자쌍의 방향(d) 집합
- Agent 05(렌더링)가 전자구름 계산 시 `user_lp`에 포함된 방향의 lone pair는 제외 가능
- RDKit 계산에 의한 자동 lone pair와 구분하기 위한 메타데이터

**설계 판단:**
- Arrow, Text 모드는 Agent 01(UI)이 `self.canvas.mode = "Arrow"` / `"Text"`로 설정할 수 있도록 문자열 기반
- arrows/text_boxes는 atoms/bonds에 포함되지 않으므로 분석(analyzer)에 영향 없음
- charge 필드는 `.get("charge", "")`로 안전하게 접근 — 기존 데이터 하위 호환
- user_lp 필드도 `.get("user_lp", set())`로 안전하게 접근

#### 8. 향후 캔버스-3D 연동 개선 사항 (Phase 7+)

1. **웨지/대쉬 → 3D 변환**: 현재 `get_smiles()`에서 웨지/대쉬 정보 손실. `Chem.BondStereo`로 변환하면 RDKit이 정확한 3D 입체배치 생성 가능.
2. **원자 클릭 동기화**: 3D 팝업에서 원자 클릭 시 → 캔버스에서 해당 원자 하이라이트 (양방향 연동)
3. **실시간 업데이트**: 캔버스에서 분자 수정 → 3D 팝업 자동 갱신 (`on_molecule_updated` Hook 활용)
4. **Undo/Redo 연동**: 3D 팝업의 ORCA 로드/측정 작업도 Undo 스택에 포함
