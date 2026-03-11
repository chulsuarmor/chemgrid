# 📋 Agent 04: 화학 분석 엔진 — Context Plan
## 최종 업데이트: 2026-03-02 / Manager 긴급 명령 v3 (벤젠 스펙트럼 수정)

---

### [긴급 수정] NMR 분석 로직 개선 및 스펙트럼 데이터 연동
- [x] **NMR 피크 예측 로직 강화**:
  - 현재 `spectrum_pdf_exporter.py`에서 용매 피크($CDCl_3$)만 강조되는 문제를 해결.
  - 시료(벤젠)의 실제 $^1H$ (7.36 ppm) 및 $^{13}C$ (128.5 ppm) 화학적 이동값을 우선적으로 반환하도록 로직 수정.
  - 필요 시 간단한 피크 예측 테이블(Lookup Table)을 `engine_physics.py`에 추가 완료 (NMR_H_SHIFTS, NMR_C_SHIFTS).
- [x] **구조-피크 매핑(Color Mapping) 데이터 생성**:
  - `analyzer.py`의 `analyze` 함수 결과에 원자 좌표별 예상 NMR Shift 값(`nmr_shifts`)을 포함시켜 UI 팀이 시각화할 수 있도록 지원.

---

### 0. 역할 및 환경
- **Worker AI** (화학 분석 엔진 전담)
- 작업 폴더: `agents/04_analysis_engine/`
- **작업 대상:** `c:\chemgrid\agents\10_testing_build\integrated\analyzer.py`
- **원본 참조 (읽기 전용):** `c:\chemgrid\_source\analyzer.py`
- **conda 환경:** `chemgrid` (Python 3.12.12, PyQt6 6.10.2, numpy 2.4.2, RDKit 2025.09.5)
- **실행 명령:** `C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python <script>`

---

### 1. 🔴🔴🔴 긴급 명령 1건 (Phase 6-2 사용자 직접 보고 이슈 U4)

> **사용자가 분자를 그리고 루이스/이론적 구조로 변환하면 방향이 회전되어 원본과 다르게 보임. 줌도 보존되지 않음.**

---

#### 📌 명령 1: Procrustes 정렬로 RDKit 좌표를 원본 방향에 맞추기 [U4]

**현재 문제:**
`generate_smiles()` 함수에서 `rdDepictor.Compute2DCoords(temp_mol)` 호출 후, RDKit이 자체 방향으로 2D 좌표를 생성함. 현재 코드는 **평행이동만** 수행하고 있어 **회전 각도가 보존되지 않음**.

```python
# 현재 코드 (문제): 평행이동 + 고정 스케일만
new_pos = QPointF(orig_center.x() + (pos.x - rdkit_cx) * 45.0,
                  orig_center.y() - (pos.y - rdkit_cy) * 45.0)
```

---

**STEP 1. `_align_to_original()` 메서드를 `ChemicalAnalyzer` 클래스에 추가**

```python
def _align_to_original(self, orig_coords, rdkit_coords):
    """
    Procrustes 정렬: RDKit 2D 좌표를 원본 그리기 좌표의 방향/스케일에 최적 정렬
    
    SVD 기반 최적 회전 행렬 계산:
    1. 두 점 집합의 중심을 원점으로 이동
    2. 원본 스케일에 맞게 RDKit 좌표 스케일 조정
    3. SVD로 최적 회전 행렬 R 계산
    4. 회전 적용 후 원본 중심으로 이동
    
    Args:
        orig_coords: list of (x, y) - 원본 그리기 좌표 (target)
        rdkit_coords: list of (x, y) - RDKit 생성 좌표 (source, Y축 이미 반전됨)
    
    Returns:
        list of (x, y) - 정렬된 좌표
    """
    import numpy as np
    
    if len(orig_coords) < 2 or len(rdkit_coords) < 2:
        return rdkit_coords
    
    if len(orig_coords) != len(rdkit_coords):
        return rdkit_coords
    
    P = np.array(orig_coords, dtype=float)  # target (원본)
    Q = np.array(rdkit_coords, dtype=float)  # source (RDKit)
    
    # 1. 중심점
    P_center = P.mean(axis=0)
    Q_center = Q.mean(axis=0)
    
    # 2. 중심을 원점으로
    P_c = P - P_center
    Q_c = Q - Q_center
    
    # 3. 스케일 (원본 스케일 보존)
    P_scale = np.sqrt((P_c ** 2).sum() / len(P))
    Q_scale = np.sqrt((Q_c ** 2).sum() / len(Q))
    
    if Q_scale < 1e-10:
        return rdkit_coords
    
    scale = P_scale / Q_scale
    Q_scaled = Q_c * scale
    
    # 4. SVD로 최적 회전
    H = Q_scaled.T @ P_c
    U, S, Vt = np.linalg.svd(H)
    
    # 거울상 방지 (det < 0이면 반전)
    d = np.linalg.det(Vt.T @ U.T)
    sign_mat = np.eye(2)
    sign_mat[1, 1] = np.sign(d)
    
    R = Vt.T @ sign_mat @ U.T
    
    # 5. 변환 적용
    aligned = (Q_scaled @ R.T) + P_center
    
    return aligned.tolist()
```

---

**STEP 2. `generate_smiles()` 함수의 theory_data 좌표 생성 부분 수정**

현재 코드에서 **분자 프래그먼트별 좌표 매핑 루프**를 찾기 (보통 `for frag_atoms in ...` 또는 `for i in range(temp_mol.GetNumAtoms()):` 패턴):

```python
# 기존: 평행이동 + 고정 스케일 45.0
# ↓ 수정: Procrustes 정렬 (회전 + 동적 스케일 + 평행이동)

# numpy 가용성 체크
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# ... generate_smiles 함수 내 ...

# RDKit 좌표 추출 후:
conf = temp_mol.GetConformer()

# 원본 좌표와 RDKit 좌표 수집
orig_pts = []
rdkit_pts = []
atom_indices = []

for i in range(temp_mol.GetNumAtoms()):
    if i in idx_to_coord:
        orig_pts.append((idx_to_coord[i][0], idx_to_coord[i][1]))
        pos = conf.GetAtomPosition(i)
        rdkit_pts.append((pos.x, -pos.y))  # Y축 반전 (RDKit→Qt 좌표계)
        atom_indices.append(i)

if NUMPY_AVAILABLE and len(orig_pts) >= 2:
    aligned = self._align_to_original(orig_pts, rdkit_pts)
    
    for j, i in enumerate(atom_indices):
        ax, ay = aligned[j]
        orig_key = (round(idx_to_coord[i][0], 2), round(idx_to_coord[i][1], 2))
        new_pos = QPointF(round(ax, 2), round(ay, 2))
        theory_map[orig_key] = new_pos
else:
    # numpy 미설치 시 기존 방식 fallback
    # (기존 평행이동 + 45.0 스케일 코드 유지)
    ...
```

---

**STEP 3. 고정 스케일 `* 45.0` 제거**

Procrustes 내부에서 스케일이 자동 계산되므로, 기존의 `* 45.0` 하드코딩은 **제거**합니다.
단, `NUMPY_AVAILABLE = False`일 때의 fallback 경로에서는 기존 45.0 유지.

---

**STEP 4. 다중 프래그먼트(분리된 분자) 처리**

캔버스에 2개 이상의 분리된 분자가 있을 때, **각 프래그먼트별로** Procrustes 정렬을 독립 적용해야 함:

```python
# 프래그먼트별 처리
mol_frags = Chem.GetMolFrags(temp_mol)
for frag_atom_indices in mol_frags:
    frag_orig = [(idx_to_coord[i][0], idx_to_coord[i][1]) for i in frag_atom_indices if i in idx_to_coord]
    frag_rdkit = [(conf.GetAtomPosition(i).x, -conf.GetAtomPosition(i).y) for i in frag_atom_indices if i in idx_to_coord]
    
    if NUMPY_AVAILABLE and len(frag_orig) >= 2:
        frag_aligned = self._align_to_original(frag_orig, frag_rdkit)
        # ... 좌표 매핑
```

---

### 2. 자가 검증 체크리스트

```cmd
:: 1. AST 검증
C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python -c "import ast; ast.parse(open(r'agents/04_analysis_engine/analyzer.py', encoding='utf-8').read()); print('AST OK')"

:: 2. Procrustes 단독 테스트
C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python -c "
import numpy as np
# 테스트: 90도 회전된 사각형
orig = [(0,0), (1,0), (1,1), (0,1)]
rotated = [(0,0), (0,1), (-1,1), (-1,0)]  # 90도 회전
P = np.array(orig, dtype=float)
Q = np.array(rotated, dtype=float)
Pc = P - P.mean(0); Qc = Q - Q.mean(0)
Ps = np.sqrt((Pc**2).sum()/4); Qs = np.sqrt((Qc**2).sum()/4)
Qs2 = Qc * (Ps/Qs)
H = Qs2.T @ Pc
U,S,Vt = np.linalg.svd(H)
d = np.linalg.det(Vt.T @ U.T)
sm = np.eye(2); sm[1,1] = np.sign(d)
R = Vt.T @ sm @ U.T
aligned = (Qs2 @ R.T) + P.mean(0)
error = np.max(np.abs(aligned - P))
assert error < 0.01, f'Procrustes error too large: {error}'
print(f'Procrustes test PASS (max error: {error:.6f})')
"

:: 3. 함수 존재 확인
findstr /n "_align_to_original" agents\04_analysis_engine\analyzer.py
```

---

### 3. ✅ 기존 완료 항목 (변경 없음)
- ✅ generate_smiles() 중복 루프 통합 (M4)
- ✅ RDKit fallback 강화
- ✅ engine_*.py 인터페이스 통일
- ✅ ast.parse 4파일 전부 OK

---

### 4. 포터블 경로 규칙 (MANDATORY)
절대 경로 금지. `__file__` 기반 상대 경로 필수.

### 5. 산출물 체크리스트

| 파일 | 변경 내용 | 상태 |
|------|----------|------|
| `analyzer.py` | `_align_to_original()` Procrustes 메서드 추가 | [x] ✅ |
| `analyzer.py` | theory_data 좌표 생성에 Procrustes 적용 | [x] ✅ |
| `analyzer.py` | 고정 스케일 45.0 제거 (동적 스케일) | [x] ✅ |
| `analyzer.py` | 다중 프래그먼트 독립 정렬 | [x] ✅ |
| `analyzer.py` | numpy 미설치 시 fallback 유지 | [x] ✅ |

### 6. 협업 의존성

| 대상 | 내용 | 방향 |
|------|------|------|
| Agent 06 | Procrustes 정렬 완료 → theory_data.map이 원본과 일치 → 3D 팝업에서 추가 회전 불필요 | Agent 04 → Agent 06 |

> **상태:** 🔴🔴🔴 Manager 긴급 명령 v3 수신 — **NMR 피크 예측 로직 수정 및 스펙트럼 데이터 연동.**
