# 📋 Agent 01: UI/디자인 — Context Plan
## 최종 업데이트: 2026-03-02 / Manager 긴급 명령 v5 (벤젠 스펙트럼 시각화 개선)

---

### [긴급 수정] 스펙트럼 리포트 시각화 디자인 개선
- [x] **AI 종합 판독 카드 디자인**:
  - 리포트 하단 또는 상단에 요약 정보를 보여주는 'AI 판독 카드' 컴포넌트 디자인.
  - 성공/경고/에러 상태에 따른 색상 코드 정의 (Green/Yellow/Red).
- [x] **피크-구조 연동 시각화 (Color Mapping)**:
  - 스펙트럼의 주요 피크와 분자 구조의 해당 원자/결합을 동일한 색상으로 하이라이팅하는 스타일 가이드 수립.
  - NMR 분석 결과(Zoning)에 따른 색상 띠 디자인.

---

### 0. 환경
- 작업 폴더: `agents/01_ui_design/`
- 작업 대상: `draw.py`, `main_window.py`, `toolbar_setup.py`
- conda: `chemgrid` (PyQt6 6.10.2)
- 실행: `C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python <script>`

### ⚠️ 세션 시작
1. 이 파일 → `context_list.md` → `context_note.md` → `docs/ai/mistakes.md` 순서로 읽기
2. 작업 대상 파일을 반드시 읽고 현재 코드 숙지 후 작업

---

### 1. 🔴 긴급 명령 4건

#### 📌 명령 1: 툴바 2줄로 분리 (사용자 직접 보고)
**문제:** 현재 툴바가 1줄이라 창이 좁으면 저장/내보내기/원소 등이 잘려 보임.

**해결:**
- **tb1** (1줄): 로고, 새파일, 열기, 저장, 내보내기, 구분선, Undo, Redo
- `self.addToolBarBreak()` 호출 → 줄바꿈
- **tb2** (2줄): 펜, 반응화살표(신규 #7), 지우개, 텍스트도구(신규 #8), 선택, 손, 구분선, 대쉬, 웨지, 구분선, 전체지우기, 원소선택

```python
# MainWindow.__init__() 내 툴바 구성
tb1 = QToolBar("파일")
tb1.setMovable(False)
self.addToolBar(tb1)
# tb1에 로고/새파일/열기/저장/내보내기/Undo/Redo 추가

self.addToolBarBreak()  # ← 이 한 줄로 2줄 전환

tb2 = QToolBar("그리기")
tb2.setMovable(False)
self.addToolBar(tb2)
# tb2에 펜/화살표/지우개/T/선택/손/대쉬/웨지/전체지우기/원소 추가
```

#### 📌 명령 2: Theory 버튼 누를 때 3D 팝업 자동 오픈 제거
**문제:** "이론적 구조" 버튼 클릭 시 `open_3d_popup()`이 자동 호출되어 팝업이 바로 뜸.
**해결:** `switch_view("Theory")` 또는 `on_theory_layer_interaction()` 내에서 `open_3d_popup()` 호출 코드를 찾아 **제거**. 3D 팝업은 오직 `btn_3d` 클릭으로만 열려야 함.

검색 키워드: `open_3d_popup`, `Molecule3DPopup`, `popup.show()`를 `switch_view` 함수 내에서 찾아서 제거.

#### 📌 명령 3: btn_3d 비활성화 (이전 v3 명령 유지)
이전 context_plan v3의 명령 1 그대로 적용:
- `btn_3d.setEnabled(False)` 기본값
- `molecule_selected` 시그널 연결 (hasattr 가드)
- `_on_molecule_selection_changed()` 핸들러

#### 📌 명령 4: 반응 화살표 + 텍스트 도구 버튼 추가 (tb2에)
**반응 화살표:** tb2에서 대쉬 앞, 펜 뒤에 위치. 아이콘은 `→` 또는 arrow.png. QAction으로 추가.
```python
self.arrow_action = QAction("→", self)
self.arrow_action.setToolTip("반응 화살표")
self.arrow_action.setCheckable(True)
tb2.addAction(self.arrow_action)
```
**텍스트 도구:** 펜과 지우개 사이에 "T" 아이콘.
```python
self.text_action = QAction("T", self)
self.text_action.setToolTip("텍스트 상자")
self.text_action.setCheckable(True)
tb2.addAction(self.text_action)
```

캔버스와의 연결은 Agent 02가 구현하므로, 여기서는 **버튼만 생성하고 시그널은 캔버스로 전달**.

---

### 2. 자가 검증
```cmd
C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python -c "import ast; ast.parse(open(r'agents/01_ui_design/draw.py',encoding='utf-8').read()); ast.parse(open(r'agents/01_ui_design/main_window.py',encoding='utf-8').read()); print('AST OK')"
```

### 3. 산출물
| 파일 | 변경 | 상태 |
|------|------|------|
| ui_utils.py | AIReportCard, SpectrumColorMap 추가 | [x] ✅ |
| draw.py / main_window.py / toolbar_setup.py | 툴바 2줄 (addToolBarBreak) | [x] ✅ |
| draw.py / main_window.py | Theory→3D 자동오픈 제거 | [x] ✅ |
| draw.py / main_window.py | btn_3d 비활성화 | [x] ✅ (이전 세션) |
| draw.py / main_window.py / toolbar_setup.py | 반응화살표+텍스트 버튼 추가 | [x] ✅ |

> **상태:** ✅ 전부 완료 (2026-03-01 01:21 AST 검증 통과)
