# 📋 Agent 06: 입체 구조(3D) — Context Plan
## 최종 업데이트: 2026-03-01 01:14 / Manager 긴급 명령 v4

---

### 0. 환경
- 작업 폴더: `agents/06_3d_structure/`
- 작업 대상: `popup_3d.py` (~66KB)
- conda: `chemgrid` (PyQt6, PyOpenGL, matplotlib, requests, google-generativeai)

### ⚠️ 세션 시작
1. 이 파일 → `context_list.md` → `context_note.md` → `docs/ai/mistakes.md` 순서로 읽기
2. **반드시** `popup_3d.py` 전체를 읽고 현재 코드 숙지 후 작업 (66KB 대형)

---

### 1. 🔴 긴급 명령 4건 (이슈 #6: 3D 팝업 전면 개선)

> **사용자 피드백:** "원자 알갱이가 너무 작고 무슨 원소인지 못 알아봄, 다중결합 표현 안됨, 계산값/PubChem/DFT 전부 오류"

#### 📌 명령 1: 원자 크기 확대 + CPK 색상 강화
**문제:** 원자 구(sphere)가 결합 실린더에 비해 너무 작아서 원소 구분 불가.

**해결 (BallAndStickRenderer 또는 동등 렌더러):**
- 원자 반지름을 현재값의 **2~3배**로 확대
  - H: 0.25→0.5, C: 0.3→0.7, N: 0.3→0.65, O: 0.3→0.6 (단위: 렌더링 좌표)
- CPK 색상 강화 (Jmol/Avogadro 표준):
  - C: (50,50,50) 진한 회색/검정
  - H: (255,255,255) 흰색
  - O: (255,13,13) 빨강
  - N: (48,80,248) 파랑
  - S: (255,255,48) 노랑
  - Cl: (31,240,31) 녹색
  - Br: (166,41,41) 진갈색
- `glMaterialfv` ambient/diffuse 값을 CPK에 맞게 밝게 조정
- 선택적: 원자 라벨(원소기호 텍스트)을 구 위에 표시 → `renderText()` 또는 QPainter 오버레이

#### 📌 명령 2: 다중결합 표현
**문제:** 이중/삼중결합이 단일결합과 동일하게 1개 실린더로 표현됨.

**해결:**
- 이중결합: 2개 평행 실린더 (약간의 오프셋)
- 삼중결합: 3개 평행 실린더
```python
def _draw_bond(self, p1, p2, bond_order, quad):
    if bond_order == 1:
        self._draw_cylinder(quad, p1, p2, radius=0.08)
    elif bond_order == 2:
        # 수직 오프셋 벡터 계산
        offset = self._perpendicular_offset(p1, p2, dist=0.12)
        self._draw_cylinder(quad, p1+offset, p2+offset, radius=0.06)
        self._draw_cylinder(quad, p1-offset, p2-offset, radius=0.06)
    elif bond_order >= 3:
        self._draw_cylinder(quad, p1, p2, radius=0.06)
        offset = self._perpendicular_offset(p1, p2, dist=0.15)
        self._draw_cylinder(quad, p1+offset, p2+offset, radius=0.05)
        self._draw_cylinder(quad, p1-offset, p2-offset, radius=0.05)
```

#### 📌 명령 3: PropertiesPanel 오류 핸들링 개선
**문제:** 계산값, PubChem DB, DFT 결과 탭에서 전부 오류 표시.

**원인 가능성:**
1. SMILES가 비어있거나 잘못됨 → RDKit 계산 실패
2. PubChem API 네트워크 실패 → 타임아웃
3. ORCA 결과 파일 없음 → 파싱 실패
4. 예외가 catch 안 되고 패널 전체가 오류 상태

**해결:**
- 각 데이터 소스 (RDKit, PubChem, ORCA)에 **독립적 try/except**
- 실패 시 해당 섹션만 "데이터 없음" 표시, 나머지는 정상 표시
- PubChem: timeout=3, 실패 시 "오프라인 — PubChem 조회 불가" 표시
- ORCA: 파일 없으면 "ORCA 결과 없음 — 📂 버튼으로 .out 파일 로드" 표시
- RDKit: SMILES 검증 후 계산. 실패 시 "분자 구조 분석 실패" 표시

```python
# PropertiesPanel._load_properties() 패턴
try:
    # RDKit 계산
    mol = Chem.MolFromSmiles(smiles)
    if mol:
        self.add_row("분자식", Chem.rdMolDescriptors.CalcMolFormula(mol))
        self.add_row("분자량", f"{Descriptors.MolWt(mol):.2f}")
    else:
        self.add_row("분자식", "계산 실패")
except Exception as e:
    self.add_row("RDKit", f"오류: {str(e)[:50]}")

try:
    # PubChem 조회
    ...
except Exception:
    self.add_row("PubChem", "오프라인 — 조회 불가")

try:
    # ORCA DFT
    ...
except Exception:
    self.add_row("DFT", "결과 없음 — .out 파일 로드 필요")
```

#### 📌 명령 4: v3 AI 오버레이 유지
이전 context_plan v3의 AI 피크 분석 그래프 오버레이 + 토글 버튼 **그대로 적용**.

---

### 2. 자가 검증
```cmd
C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python -c "import ast; ast.parse(open(r'agents/06_3d_structure/popup_3d.py',encoding='utf-8').read()); print('AST OK')"
```

### 3. 산출물
| 파일 | 변경 | 상태 |
|------|------|------|
| popup_3d.py | 원자 크기 확대 + CPK 색상 강화 | [x] ✅ |
| popup_3d.py | 다중결합 평행 실린더 | [x] ✅ |
| popup_3d.py | PropertiesPanel 오류 핸들링 | [x] ✅ |
| popup_3d.py | AI 오버레이 (v3) | [x] ✅ (이전 v3에서 완료) |

> **상태:** 🟢 **v4 명령 4건 모두 완료 (2026-03-01 01:20)**
