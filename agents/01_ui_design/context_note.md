# 📝 🧊 입체 구조(3D) — Technical Notes
## Agent 01 (UI/디자인) 관점의 3D 시스템 기술 판단 기록
## 최종 업데이트: 2026-03-01 01:22

---

## 1. 아키텍처 개요

### 1.1 시스템 계층 구조

```
┌─────────────────────────────────────────────────────────────────┐
│ MainWindow (draw.py / main_window.py)         [Agent 01 관할]  │
│  ├── MoleculeCanvas (draw.py SECTION 4)       [Agent 02 관할]  │
│  │    ├── atoms: Dict{(x,y): {"main": str, "attach": {}}}     │
│  │    ├── bonds: Dict{(k1,k2): int|tuple}                     │
│  │    ├── analysis_results: Dict (ChemicalAnalyzer 출력)       │
│  │    └── view_state: "Drawing" | "Lewis" | "Theory"           │
│  │                                                              │
│  ├── btn_3d: QPushButton("입체 구조")         [Agent 01 관할]  │
│  │    └── clicked → open_3d_popup()                            │
│  │                                                              │
│  └── open_3d_popup()                          [Agent 01 구현]  │
│       ├── PHASE_C_AVAILABLE 체크                               │
│       ├── analysis_results 존재 확인                            │
│       ├── Molecule3DData 생성 (atoms, bonds, theory_data)      │
│       └── Molecule3DPopup(mol_data, self).show()               │
│                                                                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │ popup_3d.py import
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ Molecule3DPopup (popup_3d.py)                 [Agent 06 관할]  │
│  ├── Molecule3DViewer (OpenGL) / FallbackRenderer2D (QPainter) │
│  ├── 📊 속성 탭 (PropertiesPanel)                              │
│  │    ├── RDKit 계산값 (분자식, MW, LogP, TPSA 등)             │
│  │    ├── PubChem DB (IUPAC명, CAS번호, 관용명)                │
│  │    ├── ORCA DFT 결과 (에너지, 쌍극자, 수렴)                 │
│  │    └── 결합 길이/각도 자동 측정                              │
│  ├── 📈 스펙트럼 탭 (SpectrumPanel — matplotlib)               │
│  ├── 🎵 진동모드 탭 (VibrationPanel — QTimer 애니메이션)       │
│  └── 📝 AI분석 탭 (AIAnalysisPanel — Gemini API)               │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Agent 01 ↔ Agent 06 인터페이스 계약

| 항목 | Agent 01 (UI) 책임 | Agent 06 (3D) 책임 |
|------|--------------------|--------------------|
| **버튼 생성** | `btn_3d` 생성, 위치 배치, show/hide 제어 | — |
| **이벤트 연결** | `btn_3d.clicked.connect(self.open_3d_popup)` | — |
| **데이터 전달** | `Molecule3DData(atoms, bonds, theory_data)` 생성 | 수신 후 좌표 변환 |
| **팝업 표시** | `Molecule3DPopup(mol_data, self).show()` | `__init__` + `_load_data()` |
| **조건부 임포트** | `PHASE_C_AVAILABLE` 플래그 관리 | `popup_3d.py` 정상 임포트 보장 |
| **레이어 제어** | Theory 모드에서만 `btn_3d.show()` | — |
| **5개 분석 버튼** | 제거 완료 (U3) | 3D 팝업 탭으로 통합 |

---

## 2. 데이터 흐름 상세

### 2.1 트리거 경로

```
[사용자] 분자 그리기
    → mouseReleaseEvent()
    → ChemicalAnalyzer.analyze(atoms, bonds)
    → self.analysis_results 저장

[사용자] "이론적 구조" 버튼 클릭
    → switch_view("Theory")
    → btn_3d.show() (분자 미선택 시 disabled)
    # ⚠️ [명령 2] on_theory_layer_interaction() 자동 호출 제거됨
    # 3D 팝업은 오직 btn_3d 수동 클릭으로만 열림

[사용자] "입체 구조" 버튼 클릭
    → open_3d_popup()
    → Molecule3DData(atoms, bonds, theory_data)
    → Molecule3DPopup(mol_data).show()
```

### 2.2 Molecule3DData 생성 시점의 데이터 구조

```python
# Agent 01이 전달하는 데이터
mol_data = Molecule3DData(
    atoms=self.cv.atoms,         # {(x,y): {"main": "C", "attach": {d: sym}}}
    bonds=self.cv.bonds,         # {((x1,y1),(x2,y2)): 1|2|3|tuple}
    theory_data=theory_data      # {"map": {orig_key: QPointF}, "coords": {...}}
)

# Agent 06이 내부적으로 수행하는 좌표 변환 (Molecule3DData._build_data)
# 우선순위:
# 1. ORCA parser (orca_parser.atoms → xyz)
# 2. ORCA xyz dict (외부 전달)
# 3. RDKit ETKDG+MMFF (smiles → 3D)
# 4. VSEPR Z축 추정 (2D + bonds → approx Z)
# 5. 2D flat (Z=0) — 최후 수단
```

### 2.3 theory_data 구조 분석

```python
# analysis_results["theory_data"]의 구조:
theory_data = {
    "map": {
        (orig_x, orig_y): QPointF(theory_x, theory_y),  # 이론적 좌표
        ...
    },
    "coords": {
        (orig_x, orig_y): {"angle": float, "length": float, ...},
        ...
    }
}
# ⚠️ 주의: QPointF 객체 → popup_3d.py에서 .x()/.y() 메서드로 접근
#   theory_pos.x() if hasattr(theory_pos, 'x') else theory_pos[0]
```

---

## 3. 조건부 임포트 체계

### 3.1 PHASE_C_AVAILABLE 플래그

```python
# draw.py 및 main_window.py 상단
PHASE_C_AVAILABLE = False
try:
    from popup_3d import Molecule3DData, Molecule3DPopup
    PHASE_C_AVAILABLE = True
except ImportError:
    PHASE_C_AVAILABLE = False
```

**PHASE_C_AVAILABLE = False가 되는 경우:**
1. `popup_3d.py` 파일이 sys.path에 없음
2. popup_3d.py 내부 import 실패 (PyOpenGL, rdkit 등 — 이제 모두 optional)
3. ❌ `from PyQt6.QtOpenGL import GL` — **C2 버그** (Agent 06이 수정 완료)

### 3.2 팝업 내부 선택적 의존성

| 패키지 | 플래그 | 없을 때 동작 |
|--------|--------|-------------|
| PyOpenGL | `OPENGL_AVAILABLE` | QPainter 2.5D 폴백 렌더러 사용 |
| RDKit | `RDKIT_AVAILABLE` | VSEPR Z축 추정 또는 Z=0 flat |
| matplotlib | `MATPLOTLIB_AVAILABLE` | 스펙트럼 탭 비활성화 |
| requests | `REQUESTS_AVAILABLE` | PubChem 조회 비활성화 |
| google.generativeai | `GEMINI_AVAILABLE` | AI 분석 탭 비활성화 |

**핵심 판단:** popup_3d.py의 모든 외부 의존성은 try/except로 감싸져 있어, PyQt6만 있으면 최소한의 2.5D 뷰어는 항상 동작함. 이 설계가 `PHASE_C_AVAILABLE = True`를 보장하는 핵심.

---

## 4. UI 레이아웃 결정 사항

### 4.1 btn_3d 위치 및 가시성 규칙

```python
# resizeEvent() 내부
# btn_3d는 btn_back("그리기 화면으로 복귀") 10px 위에 배치
self.btn_3d.setFixedSize(200, 50)
tx = bx        # btn_back과 X좌표 동일 (우하단)
ty = by - self.btn_3d.height() - 10  # btn_back 10px 위

# switch_view() 내부 가시성 규칙
# Drawing: btn_3d.hide()
# Lewis:   btn_3d.hide()
# Theory:  btn_3d.show(), btn_3d.raise_()
```

**결정 근거:** 입체 구조 버튼은 이론적 구조를 확인한 후에만 의미 있으므로, Theory 레이어에서만 노출. "그리기로 돌아가기" 버튼 바로 위에 배치하여 자연스러운 워크플로우 제공.

### 4.2 U3: 5개 분석 버튼 제거 결정

**제거된 버튼:** `btn_spectrum`, `btn_nmr`, `btn_uvvis`, `btn_md`, `btn_molorbital`

**제거 이유:**
1. Theory 레이어에 6개 버튼(입체구조 포함)이 떠있으면 UI 혼잡
2. 스펙트럼/오비탈 등은 3D 구조와 함께 보는 것이 학술적으로 적절
3. Phase 7 설계에서 통합 팝업의 하단 탭으로 이동하기로 확정

**잔여 참조 처리:**
- `switch_view()` 내 `analysis_buttons` 리스트 → `hasattr()` 가드로 안전
- `resizeEvent()` 내 배치 코드 → `hasattr()` 체크로 에러 없음
- `open_*_viewer()` 메서드들 → **유지** (Agent 06의 탭에서 재호출 가능)

### 4.3 switch_view()의 btn_3d 중복 코드 문제

현재 `switch_view()`에 `btn_3d` show/hide 로직이 **3곳**에 분산되어 있음:

```python
# 위치 1: Theory 모드 체크
if hasattr(self, 'btn_3d'):
    if mode == "Theory": self.btn_3d.show()
    else: self.btn_3d.hide()

# 위치 2: Drawing/비Drawing 분기
if is_drawing:
    self.btn_3d.hide()
else:
    self.btn_3d.setVisible(mode == "Theory")

# 위치 3: 최종 raise
if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
    self.btn_3d.raise_()
```

**판단:** 중복이지만 방어적 코딩. 3번의 show/hide 호출은 성능 영향 없음. 리팩토링 시 하나로 통합 가능하나, 현재는 안정성 우선으로 유지.

---

## 5. Agent 06 (popup_3d.py) 아키텍처 분석

### 5.1 원본 vs 리팩토링 비교

| 항목 | 원본 (_source) ~300줄 | Agent 06 리팩토링 ~1400줄 |
|------|----------------------|--------------------------|
| GL import | ❌ `from PyQt6.QtOpenGL import GL` (C2 버그) | ✅ 제거, `OpenGL.GL` 만 사용 |
| OpenGL Profile | CoreProfile (glColor3f 무시) | ✅ CompatibilityProfile + glMaterialfv |
| Quadric 관리 | 매 프레임 gluNewQuadric (메모리 누수) | ✅ GLQuadricManager 재사용 |
| 좌표 생성 | Z=0 고정 (M3 버그) | ✅ 5단계 우선순위 (ORCA > RDKit > VSEPR) |
| 폴백 렌더러 | 없음 | ✅ QPainter 2.5D (FallbackRenderer2D) |
| 탭 패널 | 없음 | ✅ 4탭 (속성/스펙트럼/진동모드/AI분석) |
| ORCA 파싱 | 없음 | ✅ OrcaOutputParser (geometry, freq, modes) |
| PubChem API | 없음 | ✅ PubChemClient (IUPAC, CAS, 물성) |
| Gemini AI | 없음 | ✅ GeminiAnalyzer (선택적, 라벨 포함) |
| 진동 애니메이션 | 없음 | ✅ QTimer 30ms, sin(phase) × amplitude |
| 결합 측정 | 없음 | ✅ get_bond_length(), get_bond_angle() |
| 다크 UI | 없음 | ✅ Avogadro 스타일 다크 테마 |
| 2광원 조명 | 1광원 | ✅ 2광원 (정면 + 뒤 아래) |

### 5.2 렌더링 파이프라인

```
[OpenGL 경로]
Molecule3DViewer.paintGL()
  → glClear + glLoadIdentity
  → Camera: translate(pan) → scale(zoom) → rotate(rx, ry) → translate(-center)
  → BallAndStickRenderer.render() 또는 SpaceFillingRenderer.render()
    → _set_material(r, g, b) — glMaterialfv 기반
    → _draw_cylinder(quad, p1, p2, radius) — 결합
    → gluSphere(quad, radius, slices, stacks) — 원자
    → [진동 시] _draw_arrow(quad, origin, dir, length) — 화살표

[QPainter 폴백 경로]
FallbackRenderer2D.paintEvent()
  → 3D→2D 투영 (rotation_x, rotation_y 행렬 적용)
  → Z-정렬 (깊이순 렌더)
  → QRadialGradient 구체 효과
  → 결합선 (Z 깊이에 따른 밝기 변화)
```

### 5.3 ORCA 파서 핵심 regex

```python
# Geometry: 마지막 "CARTESIAN COORDINATES (ANGSTROEM)" 블록
r"CARTESIAN COORDINATES \(ANGSTROEM\)\s*\n-+\n(.*?)(?:\n\s*\n|\n-+)"

# Energy: 마지막 단일점 에너지
r"FINAL SINGLE POINT ENERGY\s+([-\d.]+)"

# Frequencies: 진동수 리스트
r"^\s*(\d+):\s+([-\d.]+)\s+cm\*\*-1"

# Dipole moment
r"Magnitude \(Debye\)\s*:\s+([\d.]+)"

# Mulliken charges
r"MULLIKEN ATOMIC CHARGES\s*\n-*\n(.*?)(?:Sum of|$)"

# Convergence
"****ORCA TERMINATED NORMALLY****"
```

---

## 6. 알려진 이슈 및 향후 작업

### 6.1 해결 완료된 이슈

| ID | 이슈 | 해결 | 담당 |
|----|------|------|------|
| C2 | `from PyQt6.QtOpenGL import GL` 크래시 | 해당 줄 삭제 | Agent 06 ✅ |
| U2 | `btn_3d.clicked.connect()` 누락 | `open_3d_popup()` 연결 | Agent 01 ✅ |
| U3 | Theory 레이어 5개 분석 버튼 과잉 | 생성 코드 제거 | Agent 01 ✅ |
| M3 | Z=0 고정 (3D 좌표 없음) | 5단계 좌표 우선순위 | Agent 06 ✅ |

### 6.2 미해결 / 향후 이슈

| ID | 이슈 | 상태 | 메모 |
|----|------|------|------|
| F1 | `google.genai` 패키지 미설치 | 🟡 | `google-generativeai` 0.8.6 동작하나 deprecated |
| F2 | PubChem 조회 동기식 (UI 블로킹 가능) | 🟡 | QThread 비동기화 필요 |
| F3 | PDF 내보내기 미구현 (팝업 내) | 🟡 | Phase 7+ |
| F4 | 원자 클릭 → 정보 팝업 미구현 | 🟡 | Phase 7+ |
| F5 | Agent 04 Procrustes 정렬 → theory_data 방향 보존 | 🔴 | Agent 04 대기 |
| F6 | switch_view()의 btn_3d 중복 로직 | 🟡 | 리팩토링 시 통합 |

### 6.3 데이터 신뢰도 계층 (Phase 7 설계)

```
★★★★★  RDKit 계산값 (로컬, 결정론적) — "계산값" 라벨
★★★★★  PubChem DB (실험값, NIST 기반) — "PubChem DB" 라벨
★★★★☆  ORCA DFT 결과 (B3LYP/6-31G(d)) — "DFT 결과" 라벨
★★★☆☆  Gemini AI 분석 — "⚡AI 보조 (참고용)" 라벨
```

---

## 7. Agent 01 ↔ Agent 06 공유 파일 주의사항

### 7.1 chem_data.py (공유 파일)

`chem_data.py`는 Agent 01, 03, 04, 05, 06 등 다수 에이전트가 참조하는 공유 파일.
- Agent 06의 popup_3d.py는 자체적으로 `CPK_COLORS`, `VDW_RADII` 등을 정의하여 chem_data.py 의존 최소화
- Agent 01은 chem_data.py의 `ELEMENT_DATA`, `VISUAL_SETTINGS`만 사용

### 7.2 draw.py (Agent 01 + 02 공유)

- Agent 01: MainWindow 클래스만 수정 (SECTION 4)
- Agent 02: MoleculeCanvas 클래스만 수정 (SECTION 4 상단)
- **절대 규칙:** Agent 01은 MoleculeCanvas 내부 메서드를 건드리지 않음

### 7.3 popup_3d.py (Agent 06 전담)

- Agent 01은 `from popup_3d import Molecule3DData, Molecule3DPopup`만 사용
- popup_3d.py 내부 구현 변경은 Agent 06 전담
- **인터페이스 계약:** `Molecule3DData(atoms, bonds, theory_data)` 생성자 시그니처 유지

---

## 8. 이번 세션(2026-03-01 #2) 작업 요약 — Phase 6-3 v4

### 수행한 작업
1. **명령 1: 툴바 2줄 분리** (draw.py, main_window.py, toolbar_setup.py)
   - `addToolBarBreak()` 사용하여 tb1(파일)/tb2(그리기) 분리
   - tb1: 로고 | 파일메뉴 | 내보내기메뉴 | Undo/Redo
   - tb2: Bond, Pen, →(Arrow), Eraser, T(Text), Select, Hand | Dash, Wedge | 원소/기호 | 전체지우기, 원소선택
   - set_mode에서 Pen 위젯 탐색을 tb2 우선으로 변경

2. **명령 2: Theory→3D 자동오픈 제거** (draw.py, main_window.py)
   - switch_view("Theory") 내 `self.cv.on_theory_layer_interaction()` 호출 삭제
   - 3D 팝업은 오직 btn_3d 클릭으로만 열림

3. **명령 4: 반응화살표 + 텍스트 버튼** (draw.py, main_window.py, toolbar_setup.py)
   - `arrow_action = QAction("→")` — "Arrow" 모드, checkable
   - `text_action = QAction("T")` — "Text" 모드, checkable
   - draw_tools 리스트에 "Arrow", "Text" 추가 (Lewis/Theory에서 비활성화)
   - 캔버스 동작 구현은 Agent 02 대기

### 자가 검증 결과
- draw.py: ✅ ast.parse 통과
- main_window.py: ✅ ast.parse 통과
- toolbar_setup.py: ✅ ast.parse 통과

---

## 9. 이전 세션(2026-02-28) 작업 요약

### 수행한 작업
1. **C3/C4 버그 수정** (draw.py MoleculeCanvas._analyze_dft_electron_density)
   - C3: `self.canvas` → `self` (MoleculeCanvas 내부 메서드이므로 self가 canvas)
   - C4: `self.canvas.update()` → `self.update()`
   
2. **U1: tb2 버튼 정리** (draw.py + main_window.py)
   - btn_comparator, btn_history, btn_batch 3개 QAction 및 separator 제거
   - 향후 3D 팝업 또는 메뉴에서 접근하도록 재배치 예정

3. **U2: 입체 구조 3D 팝업 연결** (draw.py + main_window.py)
   - btn_3d.clicked.connect(self.open_3d_popup) 추가
   - open_3d_popup() 메서드 구현: popup_3d 모듈의 Molecule3DPopup 호출

4. **U3: 5개 분석 버튼 제거** (draw.py + main_window.py)
   - btn_spectrum, btn_nmr, btn_uvvis, btn_md, btn_molorbital 생성 코드 제거
   - 관련 open_*_viewer() 메서드는 유지 (향후 3D 팝업 탭에서 호출 가능)
   - switch_view(), resizeEvent()의 analysis_buttons 배열 참조는 hasattr 가드로 안전

### 자가 검증 결과
- draw.py: ✅ ast.parse 통과
- main_window.py: ✅ ast.parse 통과
- toolbar_setup.py: ✅ ast.parse 통과
- dialogs.py: ✅ ast.parse 통과
- ui_utils.py: ✅ ast.parse 통과

---

## 10. 이번 세션(2026-03-01 #2 추가) 작업 요약 — Phase 6-3 v5

### 수행한 작업
1. **스펙트럼 리포트 시각화 개선** (`ui_utils.py`)
   - `AIReportCard` 클래스 추가: AI 분석 결과를 요약하여 보여주는 카드형 UI 컴포넌트.
     - 성공(Green), 경고(Yellow), 에러(Red) 상태에 따른 배경/텍스트 색상 정의 (QSS).
   - `SpectrumColorMap` 클래스 추가: 피크-구조 연동 시각화를 위한 헬퍼.
     - 10가지 고대비 색상 팔레트(Red, Green, Blue, Purple 등) 정의.
     - 인덱스 기반 색상 순환 (`get_color`, `get_qcolor`).

### 기술적 노트 (Mistakes & Fixes)
- **실수:** `ui_utils.py`의 `load_icon` 함수 중간에 새로운 클래스를 삽입하여 `try-except` 블록이 끊기는 문법 오류 발생.
- **해결:** `load_icon` 함수를 원래 로직대로 복원하고, 새로운 클래스(`AIReportCard`, `SpectrumColorMap`)를 파일 하단으로 이동 배치.
- **검증:** `ast.parse`를 통해 `ui_utils.py` 문법 오류 없음을 확인함.

### 자가 검증 결과
- ui_utils.py: ✅ ast.parse 통과
