# ChemGrid GuidedTest 정밀 분석 보고서
## 작성일: 2026-03-06 22:28 | 작성자: Act AI (Claude Sonnet 4.6)
## 세션 로그: tools/test_logs/session_20260306_222036.log

---

## 0. 테스트 개요 (로그 해석)

| 단계 | 결과 | 스크린샷 | 비고 |
|------|------|---------|------|
| STEP 0: 앱 실행 | ✅ 성공 | 00_app_launched_222036.png | PID 330922, 창 1285×852 |
| STEP 1: 벤젠 그리기 | ⚠️ 타임아웃 (35초) | 01_benzene_timeout_222114.png | [MolDraw] 키워드 미감지 |
| STEP 2: 이론적 구조 | ⚠️ 타임아웃 (30초) | 02_theory_mode_222146.png | 레이어 전환 로그 미감지 |
| STEP 3: 3D 팝업 | ✅ 창 열림 | 03_3d_popup_222147.png | 창 크기 1116×1173 |
| STEP 4: 최종 상태 | ✅ | 99_final_state_222148.png | 25개 스크린샷 저장 |

**앱 시작 시 주요 경고 로그:**
```
popup_3d.py:85: FutureWarning: All support for the `google.generativeai` package has ended
[Phase D] RDKit not available, IUPAC naming disabled
[main_window.py] Verification report module not available
QFont::setPointSize: Point size <= 0 (-1), must be greater than 0  ← 반복 다량 발생
```

---

## 1. 🔴 BUG-01: hemoglobin 그리기 실패 (복잡 분자 미지원)

### 현상
- "hemoglobin" 입력 시 그리기 실패, 오류 메시지 표시

### 근본 원인 (코드 분석)
`main_window.py` → `_lookup_smiles_for_name("hemoglobin")` 3단계 실패:

```
1. 내장 사전 (BUILTIN dict): hemoglobin 없음 ❌
2. PubChem REST API: hemoglobin은 단백질/대형 복합체 → SMILES 없음 ❌
3. Gemini AI fallback: GEMINI_API_KEY 없음 + google-generativeai deprecated ❌
```

### 추가 구조적 문제
- `_draw_smiles_on_canvas()`가 `AllChem.Compute2DCoords(mol)` 사용: 수백~수천 원자 분자는 연산 매우 느리고 그리드 스냅 충돌 필연적
- **Hemoglobin은 폴리펩타이드 복합체 (α2β2 tetramer) → 단순 SMILES 구조 표현 원천 불가**

### 수정 방향
- [ ] `_lookup_smiles_for_name()` 실패 시 사용자 친화적 오류 메시지 강화
  - "헤모글로빈은 대형 단백질 복합체로 2D 구조 그리기가 불가합니다. 헴(heme) 그룹을 그려드릴까요?"
- [ ] 원자 수 임계값 필터 추가 (예: 100개 초과 시 경고 후 중단)
- [ ] GEMINI_API_KEY 미설정 시 명확한 설정 안내 다이얼로그 표시

---

## 2. 🔴 BUG-02: 벤젠 그리기 - 그리드 비정렬 (핵심 버그)

### 현상
- AI 텍스트 입력으로 벤젠 그리기 성공 (그림 그려짐)
- 그러나 결과가 캔버스 그리드 포인트와 전혀 맞지 않음 (임의 위치)
- 이론적 구조 레이어 전환 시 구조가 보이지 않음

### 근본 원인 (코드 정밀 분석)

**A. 좌표계 불일치 (가장 심각)**

`main_window.py` `_draw_smiles_on_canvas()`:
```python
scale = 55.0  # 픽셀/Å
cx_canvas = self.cv.width() / 2 + self.cv.pan_offset.x()  # ← 버그!
cy_canvas = self.cv.height() / 2 + self.cv.pan_offset.y()  # ← 버그!
# ...
snap = 30
cx = round(cx / snap) * snap  # ← 직교 30px 스냅
cy = round(cy / snap) * snap
```

캔버스 논리 좌표계 변환 공식 (`canvas.py`):
```python
def to_logical(self, pos):
    return (pos - self.pan_offset) / self.scale_factor  # pan_offset을 뺌
```

→ `_draw_smiles_on_canvas()`는 screen 좌표에 `pan_offset`을 **더해서** 논리 좌표를 계산했지만,
  실제 논리 좌표는 `(screen - pan_offset) / scale_factor`이므로 **pan_offset이 반대로 적용됨**

**B. 그리드 타입 불일치 (핵심 버그)**

| | `_draw_smiles_on_canvas()` | 캔버스 실제 그리드 (`get_closest_pt()`) |
|---|---|---|
| 그리드 타입 | 직교(orthogonal) | **육각형(hexagonal)** |
| 간격 | 30px 균등 | grid_size=40px, row_height=34.64px |
| 오프셋 | 없음 | 홀수 행은 X방향 20px 오프셋 |
| 스냅 계산 | `round(x/30)*30` | 육각형 좌표 변환 후 거리 비교 |

→ 그린 원자들이 `get_closest_pt()` 육각형 그리드 포인트에서 최대 15~20px 벗어남
→ 결합 그리기 시 스냅이 안 걸려서 원자 연결 불가
→ theory_data["map"] 생성 시 올바른 좌표 매핑 실패

**C. analysis_results 미갱신**

`_draw_smiles_on_canvas()` 마지막:
```python
self.cv.update()  # 화면만 업데이트
# analysis_results = self.cv.analyzer.analyze(...)  ← 이 호출이 없음!
```

→ `view_state = "Theory"`로 전환해도 `analysis_results = None`이므로 TheoryRenderer가 아무것도 그리지 못함

### 수정 방향
- [ ] `_draw_smiles_on_canvas()`의 좌표 계산 수정:
  ```python
  # 올바른 논리 좌표 계산
  cx_logical = (self.cv.width() / 2 - self.cv.pan_offset.x()) / self.cv.scale_factor
  cy_logical = (self.cv.height() / 2 - self.cv.pan_offset.y()) / self.cv.scale_factor
  ```
- [ ] 스냅 로직을 `canvas.get_closest_pt()`로 교체:
  ```python
  for i in range(mol.GetNumAtoms()):
      raw_pos = QPointF(cx_logical + (pos.x - cx_mol)*scale,
                        cy_logical - (pos.y - cy_mol)*scale)
      snapped = self.cv.get_closest_pt(raw_pos) or raw_pos
      key = get_coord_key(snapped)
  ```
- [ ] `_draw_smiles_on_canvas()` 끝에 분석 트리거 추가:
  ```python
  self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds)
  self.cv.on_molecule_updated()
  self.cv.save_current_smiles()
  ```

---

## 3. 🔴 BUG-03: 이론적 구조 레이어 전환 시 구조 불표시

### 현상
- Drawing 레이어에서 분자를 그린 후 "이론적 구조" 버튼 클릭
- 이론적 구조 레이어에서 화면이 비어있거나 구조가 보이지 않음

### 근본 원인
1. **BUG-02의 파생 문제**: AI 입력으로 그린 분자는 hex grid에서 벗어나 있어 analyzer가 올바른 결합 관계를 인식 못함
2. **analysis_results 미갱신**: `_draw_smiles_on_canvas()` 후 `analysis_results = None`
3. **canvas.py `paintEvent` LAYER 3 조건**:
   ```python
   elif self.view_state == "Theory" and self.analysis_results:
       TheoryRenderer.render(...)  # analysis_results가 None이면 실행 안 됨
   ```

### 수정 방향
- BUG-02 수정으로 자동 해결 (그리드 정렬 + analysis_results 갱신)

---

## 4. 🔴 BUG-04: 3D 입체구조 팝업 기능 대부분 미완성

### 현상
- 팝업은 열림, 3D 구조 렌더링 가능, 회전 가능
- 하단 탭 4개 모두 거의 빈 상태 또는 기능 제한적

### 기능별 미완성 상태 분석

**[1] 속성 탭 (📊)**
| 기능 | 상태 | 원인 |
|------|------|------|
| RDKit 계산값 | ⚠️ 부분 작동 | `[Phase D] RDKit not available` 경고 발생 |
| PubChem 조회 | ❌ 느림/실패 | 동기 호출이라 UI 블로킹, 인터넷 필요 |
| ORCA DFT 결과 | ❌ 비어있음 | `.out` 파일 없음 |
| 결합 측정 | ⚠️ 자동 계산만 | VSEPR 좌표 기반, 클릭 측정 없음 |

**[2] 스펙트럼 탭 (📈)**
| 기능 | 상태 | 원인 |
|------|------|------|
| IR 스펙트럼 | ❌ 비어있음 | ORCA `.out` 로드 전까지 빈 그래프 |
| AI 피크 분석 | ❌ 미작동 | Gemini API 키 없음 + 라이브러리 deprecated |

**[3] 진동모드 탭 (🎵)**
| 기능 | 상태 | 원인 |
|------|------|------|
| 모드 목록 | ❌ 비어있음 | ORCA normal modes 없음 |
| 3D 애니메이션 | ❌ 비활성 | 위와 동일 |

**[4] AI 분석 탭 (📝)**
| 기능 | 상태 | 원인 |
|------|------|------|
| Gemini 분석 | ❌ 미작동 | google-generativeai deprecated, API 키 없음 |

**[5] 측정 도구 - 완전 미구현**
```python
# Molecule3DViewer에 있지만:
self._measure_mode = False  # 있음
self._selected_atoms = []   # 있음
# 하지만:
# - 팝업 UI에 측정 도구 버튼 없음
# - mousePressEvent에서 원자 클릭 감지 로직 없음
# - 클릭된 원자의 결합 길이/각도 표시 로직 없음
```

### 수정 방향 (우선순위별)

**즉시 수정 가능 (ORCA 없이)**
- [ ] PubChem 조회를 QThread로 비동기화 (UI 블로킹 해결)
- [ ] `update_rdkit()` 시 SMILES 미입력 처리 개선
- [ ] 측정 버튼 UI 추가 + 클릭 감지 로직 구현 (간단)

**ORCA 연동 필요**
- [ ] ORCA `.out` 드래그 앤 드롭 지원
- [ ] 스펙트럼, 진동모드 자동 로드

**API 키 필요**
- [ ] `google.generativeai` → `google.genai` 마이그레이션
- [ ] AI 분석 폴백: RDKit 기반 로컬 분석 (API 없이도 동작)

---

## 5. 🔴 BUG-05: activation_handler.py - 연결 안 된 죽은 코드

### 현상
- `agents/06_3d_structure/activation_handler.py` 존재하지만 실제로 사용되지 않음

### 코드 분석
```python
# activation_handler.py
class StructureActivator:
    def enable_3d_button(self, molecule):
        return (
            molecule.has_3d_coordinates()              # ← 해당 메서드 없음
            and self.validator.check_stereochemistry(molecule)   # ← 해당 메서드 없음
            and self.validator.validate_quantum_data(molecule)   # ← 해당 메서드 없음
        )
```

```python
# main_window.py (실제 사용되는 로직)
has_atoms = bool(self.cv.atoms)
self.btn_3d.setEnabled(has_atoms)  # ← 단순 원자 존재 여부로 판단
```

→ `activation_handler.py`는 실제 `main_window.py`에 import/연결되어 있지 않음
→ `agents/06_3d_structure/activate.py`도 `engine_core.validate_stereo()` 호출만 있고 실제 연동 없음

### 수정 방향
- [ ] `activation_handler.py`를 `main_window.py`에 실제 연결하거나, 불필요하면 deprecated 표시
- [ ] 현재 로직 (`has_atoms`)으로도 충분하므로 추가 조건 필요 시에만 연결

---

## 6. 🟠 BUG-06: QFont::setPointSize <= 0 오류 대량 발생

### 현상
```
QFont::setPointSize: Point size <= 0 (-1), must be greater than 0
```
로그에서 20회 이상 반복 발생

### 원인 추정
`canvas.py` `draw_atom_group()`:
```python
if self.render_mode == "ball_and_stick" and sym not in ("C", "H") and rad > 8:
    p.setFont(QFont("Arial", max(7, int(rad*0.6))))  # rad가 매우 작으면 < 1
```

또는 `toolbar_setup.py`의 버튼 아이콘 폰트 설정에서 스케일 계산 오류

### 수정 방향
- [ ] 폰트 크기 설정 전 `max(8, ...)` 보호 로직 추가
- [ ] toolbar_setup.py의 폰트 설정 검토

---

## 7. 🟠 BUG-07: google-generativeai deprecated 경고

### 현상
```
popup_3d.py:85: FutureWarning: All support for the `google.generativeai` package has ended.
Please switch to the `google.genai` package as soon as possible.
```

### 수정 방향
- [ ] `popup_3d.py`, `main_window.py` 등에서 `import google.generativeai as genai_lib` 을
  `import google.genai as genai_lib`으로 교체
- [ ] 관련 API 호출 방식도 새 패키지에 맞게 수정

---

## 8. 🟠 BUG-08: [Phase D] RDKit not available 경고

### 현상
```
[Phase D] RDKit not available, IUPAC naming disabled
```

### 원인
- `iupac_analyzer.py`의 Phase D 로직에서 RDKit을 감지 못함
- 실제 main 그리기 기능은 RDKit 작동하지만, IUPAC 이름 분석 서브시스템에서 import 실패

### 수정 방향
- [ ] `iupac_analyzer.py`의 RDKit import 경로/환경 점검
- [ ] Phase D 조건 분기를 더 견고하게 처리

---

## 9. 🔴 BUG-10: 결합 길이가 픽셀 단위로 표시됨 (스크린샷 확인)

### 현상 (02_theory_mode_222146.png 직접 확인)
3D 팝업 속성 탭의 결합 측정 섹션에 다음 값이 표시됨:
```
C-C: 47.60 Å
C=C: 60.0 Å
C-C: 67.6 Å
```
실제 벤젠 C-C 결합 길이: ~1.40 Å → **47배 이상 과대 표시**

### 근본 원인
`Molecule3DData._build_data()` → 좌표 우선순위 5번 (flat 2D fallback):
```python
# Priority 5: flat 2D
self.atom_positions = dict(base_2d)
```

`base_2d` 생성 코드:
```python
for pos, data in self.atoms.items():
    base_2d[pos] = (round(pos[0], 2), round(pos[1], 2), 0.0)
```

→ `pos`가 캔버스 논리 좌표(픽셀 단위, ~400~600 범위)를 그대로 3D 좌표로 사용
→ `get_bond_length(k1, k2)` 계산 시 `sqrt((400-500)² + ...)` → 약 50Å 결과
→ **픽셀 좌표를 Å 좌표로 착각**

### 수정 방향
- [ ] `_draw_smiles_on_canvas()` 수정 시 atoms key에 **논리 좌표(Å 단위)** 저장
- [ ] 또는 `Molecule3DData`에서 픽셀→Å 변환 적용: `x_angstrom = x_pixel / 55.0`
- [ ] grid_size = 40px ≈ 1.5Å 비율로 역변환 필요

---

## 10. 🟠 BUG-11: 벤젠을 cyclohexadiene으로 잘못 인식 (스크린샷 확인)

### 현상 (02_theory_mode_222146.png 직접 확인)
3D 팝업 속성 탭 PubChem 섹션:
- **분자량: 72.07 g/mol** (벤젠의 정확한 MW: 78.11 g/mol)
- **PubChem 관용명: cyclohexadiene 또는 유사 분자로 표시**
- SMILES: `C1=CC=CC=CC=C1` 처럼 비표준 형식 저장 가능성

### 근본 원인
`_draw_smiles_on_canvas()`에서 atoms key에 픽셀 좌표를 사용:
- 저장된 구조의 SMILES가 원본 `c1ccccc1` (방향족)가 아닌 Kekulé 구조로 주입됨
- 또는 RDKit Compute2DCoords → SMILES 변환 과정에서 방향족 표기가 제거됨
- PubChem이 이 SMILES를 비표준 구조로 해석하여 가장 유사한 분자(cyclohexadiene)를 반환

### 수정 방향
- [ ] SMILES 조회 시 RDKit `Chem.MolToSmiles(mol, canonical=True)` 사용하여 표준 SMILES 생성
- [ ] 방향족 표기 유지: `Chem.MolFromSmiles('c1ccccc1')` 입력 그대로 사용

---

## 11. 🟡 BUG-09: guided_test.py 키워드 감지 실패 (테스트 인프라)

### 현상
- STEP 1 벤젠 그리기: 35초 타임아웃 (`[MolDraw]` 키워드 미감지)
- STEP 2 이론적 구조: 30초 타임아웃 (전환 로그 미감지)

### 원인
- `_draw_smiles_on_canvas()`의 `print(f"[MolDraw] ...")` 로그는 실제 키워드 감지됨
- 단, guided_test가 이미 타임아웃된 후 사용자가 입력했으므로 시퀀스 어긋남
- 또는 `print()`가 subprocess stdout으로 제대로 전달되지 않음

### 수정 방향
- [ ] guided_test.py STEP 1 타임아웃을 60초로 늘리기
- [ ] 감지 키워드에 `selected_keys` 포함 확인 (이미 있음)
- [ ] `_draw_smiles_on_canvas()` 내 `print()`를 `sys.stdout.flush()` 후 호출

---

## 10. 종합 우선순위 정리

### 🔴 즉시 수정 필요 (사용자 경험에 직접 영향)

| 우선순위 | 버그 | 담당 모듈 | 작업량 |
|--------|------|---------|------|
| P0 | BUG-02: AI 그리기 좌표계 + hex grid 스냅 | main_window.py | 중간 |
| P0 | BUG-02C: analysis_results 미갱신 | main_window.py | 소규모 |
| P1 | BUG-07: google-generativeai deprecated | popup_3d.py, main_window.py | 소규모 |
| P1 | BUG-06: QFont 폰트 크기 오류 | canvas.py/toolbar | 소규모 |

### 🟠 단기 수정 필요 (핵심 기능 완성)

| 우선순위 | 버그 | 담당 모듈 | 작업량 |
|--------|------|---------|------|
| P2 | BUG-04-1: 3D 팝업 PubChem 비동기화 | popup_3d.py | 중간 |
| P2 | BUG-04-2: 측정 도구 UI + 클릭 감지 | popup_3d.py | 중간 |
| P2 | BUG-04-3: AI 분석 폴백 (로컬 RDKit) | popup_3d.py | 중간 |
| P2 | BUG-08: iupac_analyzer RDKit 경로 | iupac_analyzer.py | 소규모 |

### 🟡 장기 개선 (ORCA 연동 등)

| 우선순위 | 버그 | 담당 모듈 | 작업량 |
|--------|------|---------|------|
| P3 | BUG-01: 복잡 분자 처리 개선 | main_window.py | 대규모 |
| P3 | BUG-04-4: 스펙트럼/진동모드 (ORCA 연동) | popup_3d.py | 대규모 |
| P3 | BUG-05: activation_handler.py 연결/정리 | activation_handler.py | 소규모 |

---

## 11. 수정 코드 스니펫 (P0 즉시 수정)

### [P0-A] _draw_smiles_on_canvas() 좌표 수정
```python
# main_window.py _draw_smiles_on_canvas() 내부 수정

# ❌ 기존 (잘못된 좌표계)
cx_canvas = self.cv.width() / 2 + self.cv.pan_offset.x()
cy_canvas = self.cv.height() / 2 + self.cv.pan_offset.y()
scale = 55.0
snap = 30
cx = round(cx / snap) * snap
cy = round(cy / snap) * snap

# ✅ 수정 (논리 좌표 + hex grid 스냅)
from canvas import get_coord_key
cx_logical = (self.cv.width() / 2 - self.cv.pan_offset.x()) / self.cv.scale_factor
cy_logical = (self.cv.height() / 2 - self.cv.pan_offset.y()) / self.cv.scale_factor
scale = 60.0 / self.cv.scale_factor  # grid_size=40에 맞춤 조정

# 원자 좌표 계산 시:
raw_x = cx_logical + (pos.x - cx_mol) * scale
raw_y = cy_logical - (pos.y - cy_mol) * scale
raw_pos = QPointF(raw_x, raw_y)
snapped = self.cv.get_closest_pt(raw_pos)
if snapped is None:
    snapped = raw_pos  # 스냅 실패 시 원본 위치
key = get_coord_key(snapped)
```

### [P0-B] analysis_results 갱신 트리거
```python
# main_window.py _draw_smiles_on_canvas() 맨 끝에 추가
self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds)
self.cv.on_molecule_updated()
self.cv.save_current_smiles()
self.cv.update()
```
