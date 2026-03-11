# 📝 ⚗️ 화학 분석 엔진 — Technical Notes
## 기술적 판단 및 결정 기록

### [2026-03-03] Procrustes 및 NMR 통합 검증
- **상황:** Manager 긴급 지시 v3(벤젠 스펙트럼 수정) 및 Procrustes 정렬 로직 최종 검증 요청.
- **검증:** 
  - `analyzer.py`: Procrustes 정렬 메서드(`_align_to_original`) 및 `generate_smiles` 적용 로직 확인.
  - `engine_physics.py`: NMR Shift 예측(`predict_nmr_shifts`) 및 Lookup Table(`NMR_H_SHIFTS`, `NMR_C_SHIFTS`) 확인.
  - 자가 검증 스크립트(`_verify_04.py`) 실행 결과: AST 문법 이상 없음, Procrustes 정렬 오차 0.000000.
- **결론:** 기 구현된 코드의 무결성 확인 완료.

### [2026-02-28] M4 중복 루프 제거
- **문제:** `generate_smiles()` STAGE 3에서 `final_mol.GetAtoms()`를 2번 순회. 첫 번째 루프는 `outer_elecs`, `bonds_val`, `lp`를 계산하지만 결과를 어디에도 저장하지 않아 완전히 무의미했음.
- **해결:** 첫 번째 루프 삭제, 두 번째 루프(lewis_map에 저장하는 루프)만 유지.
- **영향:** 성능 개선 (원자 수 N에 대해 O(N) → O(N) 동일하지만 상수 계수 절반)

### [2026-02-28] RDKit Graceful Fallback
- **문제:** `RDKIT_AVAILABLE` 플래그가 존재하지만, `generate_smiles()` 진입 시 체크 없이 바로 `Chem.RWMol()` 호출 → RDKit 미설치 시 즉시 크래시.
- **해결:** `generate_smiles()` 최상단에 `if not RDKIT_AVAILABLE: return "", {}, {}, {"coords": {}, "bonds": []}` 가드 추가.

### [2026-02-28] engine_*.py 인터페이스 통일
- **문제:** `is_huckel(r, adj, atoms)` — 다른 메서드와 달리 `adj`가 `atoms` 앞에 위치하는 비일관성.
- **해결:** `is_huckel(r, atoms, adj)`로 인자 순서 통일. 현재 호출처 없으므로 파급 영향 없음.
- **추가:** 세 엔진 모두에 `typing` 타입힌트 및 Google-style 독스트링 추가. `CoordKey`, `AdjDict`, `AtomDict` 타입 별칭 도입.

### [2026-02-28] 인코딩 주의
- 자가 검증 시 `open(file)` → `UnicodeDecodeError (cp949)` 발생. Windows cmd 기본 인코딩이 cp949이므로 반드시 `encoding='utf-8'` 명시 필요.

### [2026-02-28 23:29] U4: Procrustes 정렬 구현 (v6.11)
- **문제:** `generate_smiles()`에서 `rdDepictor.Compute2DCoords()`가 RDKit 자체 방향으로 2D 좌표를 생성. 기존 코드는 고정 스케일 `* 45.0`으로 평행이동만 수행하여 **원본 그리기 방향이 회전됨** (U4 사용자 피드백).
- **근본 원인:** 스케일(45.0 하드코딩) + 회전 미보정 + 줌 레벨 무시
- **해결 방법: Procrustes 정렬 (SVD 기반)**
  1. `_align_to_original(orig_coords, rdkit_coords)` 메서드 추가
  2. 원본 좌표(P)와 RDKit 좌표(Q)의 중심을 원점으로 이동
  3. 원본/RDKit RMS 스케일 비율로 동적 스케일 계산 (45.0 하드코딩 제거)
  4. SVD로 최적 회전 행렬 R 계산: `H = Q^T @ P → U, S, Vt = svd(H) → R = Vt^T @ sign @ U^T`
  5. 거울상(reflection) 방지: `det(R) < 0`이면 sign_matrix로 보정
  6. 최종: `aligned = (Q_scaled @ R^T) + P_center`
- **RDKit Y축 반전:** RDKit는 수학 좌표계(y↑), 화면은 (y↓). `conf.GetAtomPosition(i).y`에 부호 반전(`-y`) 적용하여 screen 좌표계로 통일 후 Procrustes 수행.
- **numpy fallback:** `NUMPY_AVAILABLE=False`일 때 `_compute_dynamic_scale()`로 평균 거리 비율 기반 스케일 계산 + 평행이동만 수행 (기존 동작 유지).
- **검증:** ast.parse 4파일 전부 OK. 런타임 검증은 conda 환경에서 벤젠/피리딘/사이클로헥산으로 수행 예정.

---

## 🧊 입체 구조(3D) — Technical Notes
> Agent 04(화학 분석 엔진)이 생성하는 3D 관련 데이터의 기술적 상세 기록.
> Agent 06(3D 구조)이 소비하는 데이터의 근본 생성 로직을 문서화합니다.

---

### 1. 아키텍처 개요: Agent 04 → Agent 06 데이터 흐름

```
사용자 2D 그리기 (atoms, bonds)
       │
       ▼
 analyzer.py: generate_smiles()
       │
       ├─ STAGE 1: RWMol 구성 (2D → RDKit 분자 객체)
       │     └─ attach 수소 승격, 결합 주입
       │
       ├─ STAGE 2: Wedge/Dash → Z축 좌표 할당
       │     └─ idx_to_coord[i][2] = ±1.5 (3D 깊이 결정)
       │
       ├─ STAGE 3: RDKit 3D 분석
       │     ├─ Conformer 생성 (x/20, -y/20, -z)
       │     ├─ CIP R/S 판정 + Chirality Audit
       │     ├─ Lewis 데이터 (H개수, 비공유전자쌍, 형식전하)
       │     └─ Theory 좌표 (Procrustes 정렬된 2D 최적화 좌표)
       │
       ▼
 반환: (smiles, stereo_map, lewis_map, theory_data)
       │
       ▼
 popup_3d.py: Molecule3DData (Agent 06)
       └─ theory_data["map"], theory_data["coords"], theory_data["bonds"]
```

**핵심 포인트:** Agent 04는 3D **데이터 생산자**, Agent 06는 3D **데이터 소비자/렌더러**. 두 에이전트 간 인터페이스는 `theory_data` 딕셔너리.

---

### 2. Wedge/Dash → Z축 3D 좌표 할당 (STAGE 2)

#### 2-1. 결합 유형별 Z축 할당 규칙

```
Wedge (쐐기형 ▲): 뾰족한 곳(i1) → 넓은 면(i2)
  • i2의 Z = +1.5 (화면 앞으로 돌출)
  • i1의 Z = -1.5 (화면 뒤로 후퇴)

Dash (파선형 ╎╎): 뾰족한 곳(i1) → 넓은 면(i2)
  • i2의 Z = -1.5 (화면 뒤로 후퇴)
  • i1의 Z = +1.5 (화면 앞으로 돌출)

일반 결합 (Bond): Z = 0.0 (평면 위)
```

#### 2-2. 코드 위치 및 로직

```python
# analyzer.py STAGE 2 (L130~L145 부근)
if b_type == "Wedge":
    idx_to_coord[i2][2] = 1.5    # 끝점(넓은 면) → 앞으로
    idx_to_coord[i1][2] = -1.5   # 시작점(뾰족) → 뒤로
elif b_type == "Dash":
    idx_to_coord[i2][2] = -1.5   # 끝점(넓은 면) → 뒤로
    idx_to_coord[i1][2] = 1.5    # 시작점(뾰족) → 앞으로
```

#### 2-3. 설계 판단: 왜 ±1.5인가?

- RDKit `Conformer`에 전달 시 좌표를 `/20.0`으로 스케일 다운 → 실제 3D 좌표에서 `±1.5/20 = ±0.075 Å`
- 이 값은 CIP 우선순위 판정에만 사용되므로 **화학적 정확도보다 위상적 구분이 목적**
- 실제 사면체 각도(109.5°)와 결합 길이(1.54 Å C-C)는 Agent 06의 3D 뷰어에서 별도 처리 필요

#### 2-4. ⚠️ 알려진 한계: 다중 입체중심

- 동일 원자가 여러 Wedge/Dash 결합의 끝점이면 **마지막 할당이 덮어씀**
- 예: 2개의 Wedge가 동일 원자를 가리키면, 두 번째 할당만 남음
- **현재 영향:** 단일 키랄 중심에서는 문제 없음. 다중 키랄 중심 분자(예: 포도당)에서 Z 충돌 가능성 있음
- **해결 방안:** Z축 할당을 누적 방식으로 변경하거나, RDKit의 `EmbedMolecule()` 3D 좌표 생성 활용 (Agent 06 Phase 7 범위)

---

### 3. 좌표계 변환: 화면 ↔ RDKit ↔ OpenGL

#### 3-1. 세 좌표계의 차이

```
화면 좌표계 (PyQt6):    RDKit 좌표계:        OpenGL 좌표계:
  x → (오른쪽)           x → (오른쪽)          x → (오른쪽)
  y ↓ (아래쪽)           y ↑ (위쪽)            y ↑ (위쪽)
  z   (없음, 2D)         z ↑ (앞쪽)            z ↑ (화면 밖)
```

#### 3-2. 변환 지점별 처리

| 변환 | 위치 | 수식 | 목적 |
|------|------|------|------|
| 화면→RDKit | STAGE 3 Conformer | `(x/20, -y/20, -z)` | CIP 판정용 3D 좌표 |
| RDKit→화면 | Theory 좌표 | `-conf.GetAtomPosition(i).y` | Procrustes 정렬 입력 |
| 화면→OpenGL | popup_3d.py | Z=0 그대로 전달 | 3D 뷰어 렌더링 |

#### 3-3. Y축 반전의 근거

```python
# analyzer.py STAGE 3: Conformer 생성 시
conf.SetAtomPosition(idx, (c3d[0]/20.0, -c3d[1]/20.0, -c3d[2]))
#                                         ^^^ Y반전      ^^^ Z반전
```

- **Y 반전 (`-y`):** 화면 좌표(y↓)를 RDKit 수학 좌표(y↑)로 변환. 반전 안 하면 분자가 상하 뒤집혀서 R/S 판정이 반대가 됨
- **Z 반전 (`-z`):** Wedge/Dash에서 할당한 Z값이 화면 관점("앞=+")인데, RDKit 3D 좌표계에서는 부호 반전 필요. 이 반전이 없으면 R↔S가 뒤바뀜
- **스케일 `/20.0`:** 화면 좌표(픽셀 단위, ~200~800 범위)를 RDKit 좌표(Å 단위, ~0~10 범위)로 정규화

---

### 4. CIP 입체화학 (R/S) 판정

#### 4-1. RDKit 자동 판정 + 수동 필터링 2단계 구조

```
Step 1: RDKit 자동 판정
  Chem.AssignStereochemistryFrom3D(final_mol)
  → atom.GetProp("_CIPCode") = "R" 또는 "S"

Step 2: Chirality Audit (수동 필터링)
  CanonicalRankAtoms(final_mol) → 각 원자의 우선순위 랭크
  → 이웃 4개의 랭크가 모두 고유해야 키랄
  → 랭크 중복 있으면 아키랄로 강제 기각
```

#### 4-2. Chirality Audit가 필요한 이유

RDKit의 `AssignStereochemistryFrom3D`는 3D 좌표만 보고 CIP를 판정하므로, **화학적으로 아키랄인 중심도 Z≠0이면 키랄로 잘못 표시**할 수 있음.

예시: `CH2Cl2` (디클로로메탄) — 탄소에 Wedge를 그리면 Z≠0이 되어 RDKit가 "R" 또는 "S"를 부여하지만, 실제로는 2개의 동일 치환기(H 2개)가 있어 아키랄.

```python
# Chirality Audit 핵심 로직
nb_ranks = sorted([ranks[nb.GetIdx()] for nb in atom.GetNeighbors()])
if len(set(nb_ranks)) < atom.GetDegree():
    # 이웃 원자들 중 동일 랭크 존재 → 아키랄 → CIP 기각
    atom.ClearProp("_CIPCode")
    atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
```

#### 4-3. stereo_map 출력 형식

```python
stereo_map = {
    (round(x, 1), round(y, 1) - 0.1): "(R)" 또는 "(S)"
}
```

- 키: 원자 좌표 (0.1 단위 반올림, y에 -0.1 오프셋 → 라벨이 원자 약간 위에 표시)
- 값: `"(R)"` 또는 `"(S)"` 문자열
- 이 데이터는 렌더러(Agent 05)가 화면에 R/S 라벨을 그릴 때 사용

---

### 5. M3 버그: Z=0 문제 (Agent 06 연계)

#### 5-1. 현재 상태

Master Plan에서 식별된 **M3 (Z=0 문제)**:
- `popup_3d.py`의 `Molecule3DData`가 theory_data를 받아서 3D 좌표를 구성할 때, **Z축이 항상 0.0**으로 설정됨
- 이유: theory_data의 좌표는 `rdDepictor.Compute2DCoords()`로 생성된 **2D 최적화 좌표**이므로 Z 정보가 없음
- Wedge/Dash에서 생성한 Z값(±1.5)은 `idx_to_coord`에만 존재하고, theory_data에는 전달되지 않음

```python
# popup_3d.py의 현재 코드 (Agent 06 소관)
self.atom_positions[orig_pos] = (round(x, 2), round(y, 2), 0.0)  # ← Z=0 하드코딩
```

#### 5-2. Agent 04 관점의 해결 방안

**방안 A: theory_data에 Z축 전달 (Agent 04 수정)**
```python
# generate_smiles() STAGE 3에서 theory_data에 Z 정보 추가
theory_data["z_coords"] = {}
for idx, c3d in idx_to_coord.items():
    if abs(c3d[2]) > 0.01:  # Wedge/Dash가 설정한 Z값만
        theory_data["z_coords"][idx] = round(c3d[2], 2)
```

**방안 B: RDKit EmbedMolecule로 진정한 3D 좌표 생성 (Agent 06 수정)**
```python
from rdkit.Chem import AllChem
AllChem.EmbedMolecule(mol, AllChem.ETKDG())
AllChem.MMFFOptimizeMolecule(mol)  # MMFF 역장 최적화
# → 실제 3D 좌표 (결합각 109.5°, 이면각 등 반영)
```

**방안 C: ORCA DFT 최적화 좌표 사용 (Agent 07 연계)**
- Phase 7에서 ORCA `.out` 파일의 최적화된 geometry를 파싱하여 3D 좌표로 사용
- 가장 정확하지만 계산 시간 필요 (H₂O: ~30초, 벤젠: ~5분)

**권장:** 방안 B를 기본값으로, 방안 C를 "정밀 모드"로 제공. 방안 A는 임시 패치로 적용 가능.

#### 5-3. Agent 04 ↔ Agent 06 인터페이스 계약

| 키 | 타입 | 설명 | 생산자 |
|----|------|------|--------|
| `theory_data["coords"]` | `{int: QPointF}` | RDKit idx → 2D 최적화 좌표 | Agent 04 |
| `theory_data["bonds"]` | `[(int, int, BondType)]` | 결합 목록 | Agent 04 |
| `theory_data["map"]` | `{(x,y): QPointF}` | 원본좌표 → 이론좌표 매핑 | Agent 04 |
| `theory_data["z_coords"]` | `{int: float}` | Wedge/Dash Z값 (미구현) | Agent 04 (예정) |
| `stereo_map` | `{(x,y): str}` | R/S 라벨 | Agent 04 |

---

### 6. chem_data.py 3D 관련 물리 상수

#### 6-1. 3D 렌더링에 사용되는 데이터

| 필드 | 용도 | 사용처 |
|------|------|--------|
| `radius` | 공유결합 반지름 (Å) | popup_3d.py Ball-and-Stick 모델 |
| `cloud_scale` | 전자구름 상대 크기 | renderer.py 2D 구름, popup_3d.py Space-filling |
| `density_scale` | 전자밀도 가중치 | 전하밀도 시각화 |

#### 6-2. popup_3d.py 자체 상수 vs chem_data.py

`popup_3d.py`는 `ELEMENT_RADII` (van der Waals 반지름)를 **자체 하드코딩**하고 있음:

```python
# popup_3d.py (Agent 06) — 자체 vdW 반지름
ELEMENT_RADII = {"H": 1.2, "C": 1.7, "N": 1.55, "O": 1.52, ...}

# chem_data.py (공유) — 공유결합 반지름
ELEMENT_DATA = {"H": {"radius": 0.37}, "C": {"radius": 0.77}, ...}
```

**⚠️ 주의:** 이 두 반지름은 **물리적으로 다른 양**:
- `chem_data.py`의 `radius`: **공유결합 반지름** (covalent radius) — 결합 길이 계산용
- `popup_3d.py`의 `ELEMENT_RADII`: **반데르발스 반지름** (vdW radius) — 분자 크기 시각화용
- vdW 반지름 ≈ 공유결합 반지름 × 2~3 (항상 더 큼)

**권장:** `chem_data.py`에 `vdw_radius` 필드를 추가하여 Agent 06이 참조하도록 통일. 현재는 popup_3d.py의 하드코딩이 10개 원소만 커버하므로 나머지 원소에서 기본값(1.7) 사용됨.

---

### 7. 수소 승격과 3D 좌표

#### 7-1. attach 수소 → 실제 원자 승격

```python
# STAGE 1: attach 내의 H를 RWMol에 실제 원자로 추가
for d, sym in data.get("attach", {}).items():
    if sym == "H":
        h_idx = mol.AddAtom(Chem.Atom("H"))
        mol.AddBond(idx, h_idx, Chem.rdchem.BondType.SINGLE)
        ang = math.radians(d * 60)
        idx_to_coord[h_idx] = [pos[0] + math.cos(ang)*20, pos[1] + math.sin(ang)*20, 0.0]
```

- `d`는 방향 인덱스 (0~5, 60° 간격 → 정육각형 배치)
- 수소 좌표: 부모 원자에서 20px 거리, d×60° 방향
- Z=0.0 (평면 위 — 수소는 Wedge/Dash가 아니므로)

#### 7-2. 3D 뷰어에서의 수소

- `Chem.RemoveHs(final_mol)` → SMILES 생성 시 명시적 수소 제거
- 하지만 CIP 판정은 수소 포함 상태(`final_mol`)에서 수행
- **Agent 06 참고:** 3D 뷰어에서 수소 표시/숨기기 토글 필요 시, `RemoveHs` 전의 full conformer 좌표를 theory_data에 포함해야 함 (현재 미구현)

---

### 8. 런타임 검증 결과 (2026-03-01 00:03)

**conda 환경:** `chemgrid` (Python 3.12.12, numpy 2.4.2, RDKit 2025.09.5, PyQt6 6.10.2)

#### Procrustes 수학 테스트: 6/6 PASS
| # | 테스트 | 결과 | max error |
|---|--------|------|-----------|
| 1 | 90° 회전 복구 | ✅ | 0.000000 |
| 2 | 벤젠 45°회전 + 0.5x스케일 복구 | ✅ | 0.000000 |
| 3 | 벤젠 평행이동 복구 | ✅ | 0.000000 |
| 4 | 거울상(reflection) 방지 | ✅ | — |
| 5 | 단일 원자 edge case | ✅ | — |
| 6 | numpy fallback 동적 스케일 | ✅ | 100.00 |

#### SMILES 10종 검증: 10/10 PASS
| # | 분자 | 기대값 | 실제 SMILES | theory atoms |
|---|------|--------|-------------|-------------|
| 1 | 메탄 CH₄ | `C` | `C` ✓ | 5 |
| 2 | 에탄올 C₂H₅OH | `CCO` | `CCO` ✓ | 9 |
| 3 | 에틸렌 C₂H₄ | `C=C` | `C=C` ✓ | 6 |
| 4 | 포름알데히드 CH₂O | `C=O` | `C=O` ✓ | 4 |
| 5 | 물 H₂O | `O` | `O` ✓ | 3 |
| 6 | 암모니아 NH₃ | `N` | `N` ✓ | 4 |
| 7 | 벤젠 C₆H₆ | (방향족) | `c1ccccc1` ✓ | 12 |
| 8 | 아세트산 CH₃COOH | — | `CC(=O)O` ✓ | 8 |
| 9 | HCl | `Cl` | `Cl` ✓ | 2 |
| 10 | CO₂ | `O=C=O` | `O=C=O` ✓ | 3 |

**방향 보존 검증:** 다원자 분자(아세트산, CO₂, HCl, 암모니아)에서 cos similarity > 0.7 확인. 단일 원자 분자는 H 원자 포함 시 map 키 순서 차이로 방향 비교가 무의미. 벤젠은 RDKit 방향족 좌표 재배치 특성상 시각적 검증은 통합 테스트에서 확인 필요.

---

### 9. Phase 7 대비: Agent 04 확장 포인트

| 항목 | 현재 상태 | Phase 7 변경 |
|------|----------|-------------|
| Z축 좌표 | Wedge/Dash ±1.5만 | `theory_data["z_coords"]` 전달 추가 |
| 3D 좌표 생성 | 없음 (2D only) | `AllChem.EmbedMolecule` + MMFF 옵션 추가 |
| ORCA 연동 | 없음 | ORCA `.out` 파싱 geometry → theory_data 주입 (Agent 07 협업) |
| 진동 모드 | 없음 | ORCA 진동수 + 변위 벡터 → theory_data["vibrations"] |
| 결합길이/각도 | 없음 | theory_data["measurements"] 추가 가능 |

> **원칙:** Agent 04는 **데이터 생성** (좌표, 입체화학, 물성)만 담당. 렌더링/UI는 Agent 06 전담.


