# Context List — Agent 01 (UI/디자인)

## 수정된 파일 목록 (2026-03-01 세션 #2)

| 파일명 | 변경 내용 | 상태 |
|--------|-----------|------|
| draw.py | Phase 6-3 v4: 툴바 2줄 분리(addToolBarBreak), Theory→3D 자동오픈 제거, 반응화살표+텍스트 버튼 추가, set_mode tb2 탐색, draw_tools Arrow/Text 추가 | ✅ AST 통과 |
| main_window.py | Phase 6-3 v4: Theory→3D 자동오픈 제거, set_mode tb2 탐색, draw_tools Arrow/Text 추가 | ✅ AST 통과 |
| toolbar_setup.py | Phase 6-3 v4: 완전 재작성 — 2줄 분리(tb1:파일, tb2:그리기), 반응화살표+텍스트 버튼 추가 | ✅ AST 통과 |
| ui_utils.py | Phase 6-3 v5: AIReportCard, SpectrumColorMap 추가 (벤젠 스펙트럼 시각화) | ✅ AST 통과 |
| dialogs.py | 변경 없음 | ✅ |

## 적용된 Manager 지시사항 (Phase 6-3 v5)

### [긴급] 스펙트럼 리포트 시각화 디자인 개선 ✅
- [x] **AI 종합 판독 카드 (AIReportCard)**: ui_utils.py에 클래스 추가. 성공/경고/에러 상태별 스타일(Green/Yellow/Red) 정의.
- [x] **피크-구조 연동 시각화 (SpectrumColorMap)**: ui_utils.py에 클래스 추가. 10가지 고대비 색상 팔레트 정의.

## 적용된 Manager 지시사항 (Phase 6-3 v4)

### 명령 1: 툴바 2줄로 분리 ✅
- [x] tb1 (1줄): 로고, 파일메뉴, 내보내기메뉴, |, Undo, Redo
- [x] `self.addToolBarBreak()` 호출 → 줄바꿈
- [x] tb2 (2줄): Bond, Pen, →(반응화살표), Eraser, T(텍스트), Select, Hand, |, Dash, Wedge, |, 원소·기호, |, 전체지우기, 원소선택
- [x] draw.py + toolbar_setup.py 양쪽 모두 적용
- [x] set_mode에서 Pen 위젯 탐색을 tb2 우선으로 변경

### 명령 2: Theory 버튼 누를 때 3D 팝업 자동 오픈 제거 ✅
- [x] draw.py switch_view("Theory") 내 `self.cv.on_theory_layer_interaction()` 호출 삭제
- [x] main_window.py switch_view("Theory") 내 동일 호출 삭제
- [x] 3D 팝업은 오직 btn_3d 클릭으로만 열림

### 명령 3: btn_3d 비활성화 ✅ (이전 세션에서 완료)
- [x] btn_3d 초기 상태 `setEnabled(False)`
- [x] QPushButton:disabled 스타일시트
- [x] molecule_selected 시그널 연결 (hasattr 가드)
- [x] _on_molecule_selection_changed 핸들러

### 명령 4: 반응 화살표 + 텍스트 도구 버튼 추가 ✅
- [x] `arrow_action = QAction("→")` — 반응 화살표, checkable, "Arrow" 모드
- [x] `text_action = QAction("T")` — 텍스트 상자, checkable, "Text" 모드
- [x] draw.py + toolbar_setup.py 양쪽 모두 적용
- [x] switch_view draw_tools 리스트에 "Arrow", "Text" 추가 (Lewis/Theory에서 비활성화)
- [x] 캔버스 연결은 Agent 02 담당 (버튼만 생성)

## 이전 완료 항목 (2026-02-28 ~ 03-01 세션)
- ✅ U1: tb2에서 분자비교/히스토리/배치처리 버튼 제거
- ✅ U2: btn_3d.clicked.connect + open_3d_popup() 추가
- ✅ U3: 5개 분석 버튼 생성 코드 제거
- ✅ C3: self.canvas → self 수정
- ✅ C4: self.canvas.update() → self.update() 수정
- ✅ PHASE_C_AVAILABLE 조건부 import 추가
- ✅ draw.py 분리 (main_window.py, dialogs.py, toolbar_setup.py, ui_utils.py)
- ✅ btn_3d 비활성화 + molecule_selected 시그널
- ✅ ChemDraw→ChemGrid 전면 교체
- ✅ open_3d_popup 선택 분자 필터링

## 검증 기록 (2026-03-01 세션 #2)
- draw.py: ✅ AST 통과
- main_window.py: ✅ AST 통과
- toolbar_setup.py: ✅ AST 통과

## 협업 의존성 상태
| 대상 | 내용 | 상태 |
|------|------|------|
| Agent 02 | `molecule_selected = pyqtSignal(bool)` 시그널 | 🟡 대기 (hasattr 가드로 안전) |
| Agent 02 | `selected_molecule_keys` 속성 | 🟡 대기 (getattr 기본값으로 안전) |
| Agent 02 | Arrow/Text 모드 캔버스 동작 구현 | 🟡 대기 (버튼만 생성됨) |
| Agent 06 | `Molecule3DPopup(mol_data).show()` 인터페이스 | 🟡 대기 |
