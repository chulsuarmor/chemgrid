# ChemDraw Pro: 상세 코드 변경 로그

## 파일 변경: `_source/draw.py`

### 변경 1: load_icon() 함수 - 절대 경로 기반 이미지 로드

**위치:** `load_icon()` 함수 시작 부분

**이전 코드:**
```python
def load_icon(file_name, mode_name=None, symbol_text=None):
    """[해결] v1.71 툴바 부피 15% 축소, 로고 30% 확대, 대쉬 실물화 통합 + 경로 자동 해결"""
    pixmap = QPixmap(40, 40); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if file_name:
        # 상대 경로를 절대 경로로 변환
        if not os.path.isabs(file_name):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_name = os.path.join(script_dir, file_name)
        
        if os.path.exists(file_name):
            try:
                img = QPixmap(file_name)
                # ... 이후 코드
```

**수정된 코드:**
```python
def load_icon(file_name, mode_name=None, symbol_text=None):
    """[해결] v1.71 툴바 부피 15% 축소, 로고 30% 확대, 대쉬 실물화 통합 + 경로 자동 해결"""
    pixmap = QPixmap(40, 40); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if file_name:
        # 현재 스크립트의 디렉토리 기반으로 _source 폴더의 이미지 파일 찾기
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_file_name = os.path.join(script_dir, file_name)
        
        if os.path.exists(abs_file_name):
            try:
                img = QPixmap(abs_file_name)
                if not img.isNull():  # 이미지 로드 확인
                    pad = 4 if "hand" in file_name.lower() else 1
                    painter.drawPixmap(pad, pad, 40-pad*2, 40-pad*2, img)
                    painter.end(); return QIcon(pixmap)
                else:
                    print(f"[load_icon] ⚠️ 이미지 파일 손상: {abs_file_name}")
            except Exception as e:
                print(f"[load_icon] ⚠️ 이미지 로드 실패: {abs_file_name} - {e}")
        else:
            print(f"[load_icon] ⚠️ 파일 없음: {abs_file_name}")
```

**변경 이유:**
- 절대 경로 계산을 명시적으로 처리하여 _source 폴더의 이미지 파일을 확실하게 로드
- 에러 메시지에 절대 경로 표시하여 디버깅 용이

---

### 변경 2: tool_icons 딕셔너리 - eraser.png 파일명 수정

**위치:** `MainWindow.__init__()` 함수 내 tool_icons 정의

**이전 코드:**
```python
tool_icons = {
    "Select": ("select.png", None), "Hand": ("hand.png", None), 
    "Pen": ("pen.png", None), "Eraser": ("ereser.png", None),  # ❌ 오타
    "Bond": ("bond.png", None), "LonePair": ("", ".."), 
    "Radical": ("", "·"), "Positive": ("", "+"), "Negative": ("", "-")
}
```

**수정된 코드:**
```python
tool_icons = {
    "Select": ("select.png", None), "Hand": ("hand.png", None), 
    "Pen": ("pen.png", None), "Eraser": ("eraser.png", None),  # ✅ 수정됨
    "Bond": ("bond.png", None), "LonePair": ("", ".."), 
    "Radical": ("", "·"), "Positive": ("", "+"), "Negative": ("", "-")
}
```

**변경 이유:**
- 파일명 오타 ("ereser" → "eraser") 수정
- 파일시스템의 실제 파일명과 매칭

---

### 변경 3: MainWindow.__init__() - 윈도우 아이콘 설정

**위치:** `MainWindow.__init__()` 함수 시작

**이전 코드:**
```python
self.setWindowTitle("ChemDraw Pro"); self.setGeometry(100, 100, 1350, 850)
# [해결] load_icon 엔진을 사용하여 작업표시줄 및 윈도우 로고 무결성 확보
self.setWindowIcon(load_icon("logo.png"))
```

**수정된 코드:**
```python
self.setWindowTitle("ChemDraw Pro"); self.setGeometry(100, 100, 1350, 850)
# [해결] load_icon 엔진을 사용하여 작업표시줄 및 윈도우 로고 무결성 확보
# logo.png를 QPixmap으로 직접 로드하여 윈도우 아이콘 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(script_dir, "logo.png")
if os.path.exists(logo_path):
    self.setWindowIcon(QIcon(QPixmap(logo_path)))
else:
    print(f"[MainWindow] Logo not found at {logo_path}")
```

**변경 이유:**
- 절대 경로로 logo.png를 로드하여 윈도우 아이콘 확실하게 설정
- 파일이 없을 경우 피드백 메시지 제공

---

### 변경 4: switch_view() 함수 - +/- 도구 비활성화

**위치:** `MainWindow.switch_view()` 함수 내

**이전 코드:**
```python
# 그리기 관련 도구 비활성화 (회색 처리)
draw_tools = ["Bond", "Wedge", "Dash", "H", "R", "O", "N", "P", "S", "F", "Cl", "Br", "I", "LonePair", "Radical"]
for action in self.findChildren(QAction):
    if action.text() in draw_tools:
        action.setEnabled(is_drawing)
```

**수정된 코드:**
```python
# 그리기 관련 도구 비활성화 (회색 처리)
draw_tools = ["Bond", "Wedge", "Dash", "H", "R", "O", "N", "P", "S", "F", "Cl", "Br", "I", "LonePair", "Radical"]
# Lewis/Theory 레이어에서는 +/- 도구도 비활성화
disable_in_lewis_theory = ["Positive", "Negative"]
for action in self.findChildren(QAction):
    action_text = action.text()
    if action_text in draw_tools:
        action.setEnabled(is_drawing)
    elif action_text in disable_in_lewis_theory:
        action.setEnabled(is_drawing)
```

**변경 이유:**
- Lewis/Theory 레이어에서 Positive와 Negative 도구를 비활성화
- 도구 사용 가능 범위를 명확히 제한

---

### 변경 5: paintEvent() - Lewis/Theory 레이어 선택 범위 표시

**위치:** `MoleculeCanvas.paintEvent()` 함수, LAYER 3 섹션

**추가된 코드:**
```python
# [LAYER 3] 원형 확장 레이어 (새 뷰 모드가 원 안에서 나타남)
if self.view_state != "Drawing":
    p.save()
    p.translate(self.pan_offset); p.scale(self.scale_factor, self.scale_factor)
    
    # ... 기존 렌더링 코드 ...
    
    # [신규] Lewis/Theory 레이어에서도 선택 범위 사각형 표시
    if self.selection_rect:
        p.setPen(QPen(Qt.GlobalColor.blue, 1/self.scale_factor, Qt.PenStyle.DashLine))
        p.setBrush(QColor(0,0,255,15))
        p.drawRect(self.selection_rect)
```

**변경 이유:**
- Lewis/Theory 레이어에서도 선택 범위를 파란색 점선으로 시각화
- 사용자가 선택 상태를 명확히 인식 가능

---

### 변경 6: mouseMoveEvent() - Lewis 레이어 드래그 이동

**위치:** `MoleculeCanvas.mouseMoveEvent()` 함수

**추가된 코드:**
```python
def mouseMoveEvent(self, event):
    # ... 기존 코드 ...
    elif event.buttons() & Qt.MouseButton.LeftButton and self.mode == "Select" and self.drag_origin:
        # 드래그 선택 영역 업데이트
        self.selection_rect = QRectF(self.drag_origin, l_pos).normalized()
        
        # Lewis/Theory 레이어에서 이미 선택된 원자가 있으면 이동시키기
        if self.view_state in ["Lewis", "Theory"] and self.selected_atoms:
            # 드래그 벡터 계산
            delta = l_pos - self.drag_origin
            # 선택된 각 원자를 이동
            new_atoms = {}
            atom_key_mapping = {}  # 기존 key -> 새로운 key 맵핑
            
            for k in list(self.atoms.keys()):
                if k in self.selected_atoms:
                    # 원자 이동
                    new_key = (k[0] + delta.x(), k[1] + delta.y())
                    new_atoms[new_key] = self.atoms[k]
                    atom_key_mapping[k] = new_key
                else:
                    new_atoms[k] = self.atoms[k]
            
            self.atoms = new_atoms
            
            # 결합 업데이트
            new_bonds = {}
            for (b_k1, b_k2), bond_data in list(self.bonds.items()):
                new_k1 = atom_key_mapping.get(b_k1, b_k1)
                new_k2 = atom_key_mapping.get(b_k2, b_k2)
                if new_k1 != b_k1 or new_k2 != b_k2:
                    new_bonds[(new_k1, new_k2)] = bond_data
                else:
                    new_bonds[(b_k1, b_k2)] = bond_data
            self.bonds = new_bonds
            
            # 선택 범위도 업데이트
            self.drag_origin = l_pos
        else:
            # Drawing 모드 또는 새로운 선택
            self.selected_atoms = {k for k in self.atoms if self.selection_rect.contains(QPointF(*k))}
            self.selected_bonds = set()
            for k in self.bonds:
                mid = (QPointF(*k[0]) + QPointF(*k[1])) / 2
                if self.selection_rect.contains(mid): self.selected_bonds.add(k)
```

**변경 이유:**
- Lewis/Theory 레이어에서 선택된 원자를 드래그하여 이동 가능하게 구현
- 원자의 좌표와 결합을 함께 업데이트하여 분자 구조 유지

---

## 파일 변경: `_source/eraser.png`

### 파일 이름 변경
- **이전:** `ereser.png`
- **수정:** `eraser.png`

**변경 이유:**
- 파일명 오타 수정
- draw.py의 tool_icons 참조와 매칭

---

## 파일 변경: `_source/layer_logic.py`

**상태:** 수정 불필요 ✅

- LewisRenderer.render() 메서드이미 selected_atoms, selected_bonds 파라미터 구현됨
- TheoryRenderer.render() 메서드: 이미 selected_atoms, selected_bonds 파라미터 구현됨
- 선택된 원자/결합의 파란색 하이라이트: 이미 구현됨

---

## 요약

| 변경 항목 | 파일 | 상태 | 목적 |
|---------|------|------|------|
| load_icon() 절대경로 | draw.py | ✅ | 이미지 로드 안정화 |
| eraser.png 파일명 | draw.py | ✅ | 오타 수정 |
| 윈도우 아이콘 설정 | draw.py | ✅ | logo.png 로드 |
| +/- 도구 비활성화 | draw.py | ✅ | Lewis/Theory 제약 |
| 선택 범위 표시 | draw.py | ✅ | Lewis 시각화 |
| 원자 드래그 이동 | draw.py | ✅ | Lewis 상호작용 |
| eraser.png 이름변경 | 파일시스템 | ✅ | 오타 수정 |

**총 변경 사항:** 7가지 주요 수정 (모두 완료) ✅
