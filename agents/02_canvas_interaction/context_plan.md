# 📋 Agent 02: 캔버스/그리기 — Context Plan
## 최종 업데이트: 2026-03-01 01:13 / Manager 긴급 명령 v4

---

### 0. 환경
- 작업 폴더: `agents/02_canvas_interaction/`
- 작업 대상: `canvas.py`, `coord_utils.py`
- conda: `chemgrid` (PyQt6, RDKit, requests)
- 실행: `C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python <script>`

### ⚠️ 세션 시작
1. 이 파일 → `context_list.md` → `context_note.md` → `docs/ai/mistakes.md` 순서로 읽기
2. 작업 대상 파일을 반드시 읽고 현재 코드 숙지 후 작업

---

### 1. 🔴 긴급 명령 5건

#### 📌 명령 1: +/- 기호 데이터 구조 수정 (이슈 #3)
**문제:** 그리기 레이어에서 +/-를 원자에 붙이면 `atoms[(x,y)]["main"]`이 `"+"`/`"-"`로 치환됨 → Lewis/Theory에서 형식전하와 기호가 이중 표시.

**해결:**
- `+`/`-` 입력 시 `atoms[key]["main"]`은 **원래 원소 유지** (기본값 "C")
- `atoms[key]["charge"] = "+"` 또는 `"-"` **별도 필드**에 저장
- 기존 코드에서 `main`에 `+`/`-`를 넣는 부분을 찾아서 `charge` 필드로 분리
- `paintEvent()`에서 Drawing 모드일 때 `charge` 필드가 있으면 원자 옆에 작은 글씨로 표시

검색: `atoms[` 또는 `["main"]` 또는 `"+"`/`"-"` 할당 코드를 canvas.py에서 찾기

#### 📌 명령 2: 이전 v3 선택 도구 UX (점선 테두리 + IUPAC명 + 바닥 클릭 해제 + pyqtSignal)
이전 context_plan v3의 명령 1~3 **그대로 유지 적용**:
- `selected_molecule_keys`, `selected_molecule_bbox`, `selected_molecule_name`
- `_select_molecule_at()` BFS
- `_compute_molecule_bbox()` 바운딩 박스
- `_fetch_molecule_name()` PubChem
- `paintEvent()` 점선 테두리 + IUPAC명
- 바닥 클릭 해제
- `molecule_selected = pyqtSignal(bool)`

#### 📌 명령 3: 반응 화살표 도구 구현 (이슈 #7 — 신규 기능)
**사용자 요구:** "검은색 반응 화살표, 동서남북 4방향, 고스트(파란색), 모든 레이어에서 보이되 분자 인식 안됨"

**구현:**
```python
# MoleculeCanvas에 추가
self.arrows = []  # [(start_pos, end_pos), ...]
self.arrow_drawing = False
self.arrow_start = None
self.arrow_ghost_end = None
```

**마우스 이벤트 (arrow 모드):**
- `mousePressEvent`: `arrow_start = event.position()`, `arrow_drawing = True`
- `mouseMoveEvent`: 고스트 계산 — start에서 마우스까지의 dx, dy 중 큰 방향으로 스냅
  ```python
  dx = pos.x() - self.arrow_start.x()
  dy = pos.y() - self.arrow_start.y()
  if abs(dx) >= abs(dy):
      end = QPointF(pos.x(), self.arrow_start.y())  # 동서
  else:
      end = QPointF(self.arrow_start.x(), pos.y())  # 남북
  self.arrow_ghost_end = end
  ```
- `mouseReleaseEvent`: `self.arrows.append((self.arrow_start, self.arrow_ghost_end))`, `arrow_drawing = False`

**paintEvent:**
- 확정된 화살표: 검은색, 두께 2, 화살촉(삼각형)
- 고스트: 파란색, 점선, 화살촉
- **모든 view 모드에서 표시** (Drawing/Lewis/Theory)
- `self.arrows`는 `self.atoms`/`self.bonds`에 포함 안됨 → 분석에 영향 없음

#### 📌 명령 4: 텍스트 상자 도구 구현 (이슈 #8 — 신규 기능)
**사용자 요구:** "T 도구로 텍스트 상자 생성, 아래첨자(CH_3→CH₃), 텍스트 도구 선택 시만 보임"

**구현:**
```python
# MoleculeCanvas에 추가
self.text_boxes = []  # [{"pos": QPointF, "text": str, "font_size": int}, ...]
self.text_editing_idx = None  # 현재 편집 중인 텍스트 박스 인덱스
self.text_font_size = 12  # 기본 폰트 크기
```

**마우스 이벤트 (text 모드):**
- `mousePressEvent`: 클릭 위치에 새 텍스트 상자 생성 또는 기존 상자 선택
- 텍스트 입력: `keyPressEvent`에서 활성 텍스트 상자에 문자 추가
- `_render_subscript(text)` 함수: `CH_3` → `CH₃` 변환
  ```python
  import re
  def _render_subscript(self, text):
      """언더바+숫자를 아래첨자로 변환"""
      # 내부 저장은 원본(CH_3), 렌더링 시만 변환
      SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
      return re.sub(r'_(\d+)', lambda m: m.group(1).translate(SUBSCRIPT), text)
  ```

**paintEvent (text 모드일 때만):**
- 빨간 점선 테두리 (QPen DashLine, red)
- 텍스트 내용 (검은색, 사용자 지정 폰트 크기)
- 아래첨자 변환 적용

**다른 도구 선택 시:** 텍스트 상자 렌더링 스킵 (보이지 않음)
**내보내기 시:** 텍스트 상자 포함 안 함 (별도 옵션으로 포함 가능)

#### 📌 명령 5: 비공유전자쌍 데이터 구분 (이슈 #4 보조)
**문제:** 사용자가 그린 비공유전자쌍(lone pair)이 전자구름에 영향을 줌.
**해결:** `atoms[key]["attach"]`에서 lone pair 데이터에 `"user_lp": True` 플래그 추가하여 Agent 05가 전자구름 계산 시 제외할 수 있게 함. 또는 `attach`의 lone pair와 RDKit 계산 lone pair를 구분하는 메타데이터 추가.

---

### 2. 자가 검증
```cmd
C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python -c "import ast; ast.parse(open(r'agents/02_canvas_interaction/canvas.py',encoding='utf-8').read()); print('AST OK')"
```

### 3. 산출물
| 파일 | 변경 | 상태 |
|------|------|------|
| canvas.py | +/- → charge 필드 분리 | [x] ✅ |
| canvas.py | 선택 도구 UX (v3 전체) | [x] ✅ (이전 세션 완료) |
| canvas.py | 반응 화살표 도구 | [x] ✅ |
| canvas.py | 텍스트 상자 도구 | [x] ✅ |
| canvas.py | 비공유전자쌍 플래그 | [x] ✅ |

> **상태:** ✅ 전체 완료 (2026-03-01 01:23, AST 검증 통과)
