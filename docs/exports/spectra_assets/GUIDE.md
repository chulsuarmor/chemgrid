# ChemGrid 완전한 분광분석 데이터 출력 지침 (GUIDE.md)

> **최종 갱신:** 2026-03-11  
> **작성 근거:** 각 분광 폴더 내 `explanatory.txt` + 참조 이미지 + Silverstein 8판 · Pavia 5판 · Skoog 기기분석학 기준  
> **적용 파일:** `src/app/popup_predicted_spectrum.py`, `src/app/popup_3d.py` (SpectrumPanel)

---

## 0. 목적 및 배경

ChemGrid의 분광 그래프는 단순한 선 그래프가 아닌 **대학 기기분석 수준의 전문 출력물**이어야 합니다.  
본 지침은 5종 분광법(IR / ¹H NMR / ¹³C NMR / Raman / UV-Vis)의 각 그래프가 **어떤 요소를 반드시 포함해야 하는지**, **어떤 디자인 규칙을 따라야 하는지**, 그리고 **아직 미구현인 항목이 무엇인지** 명확히 정의합니다.

---

## 1. 현재 구현 현황 (2026-03-11 기준)

| 항목 | 상태 | 비고 |
|------|------|------|
| IR: 투과율 반전 축 + Lorentzian 브로드닝 | ✅ 구현 | `_make_ir_figure()` |
| IR: 작용기 annotation (주요 피크) | ✅ 구현 | 자동 레이블링 |
| ¹H NMR: 화학적 이동 + 구역 레이블 | ✅ 구현 | 0~12 ppm 범위 |
| ¹H NMR: 루이스 구조 삽입 (우상단) | ✅ 구현 | `smiles=smiles` 전달 필요 (2026-03-11 수정) |
| ¹H NMR: 각 수소-피크 색상/번호 매핑 | ❌ 미구현 | **핵심 미구현 항목 #1** |
| ¹H NMR: 적분선(Integration curve) 표시 | ❌ 미구현 | **핵심 미구현 항목 #2** |
| ¹H NMR: 갈라짐 패턴 (d/t/q/m 표시) | ❌ 미구현 | **핵심 미구현 항목 #3** |
| ¹³C NMR: 탄소 번호 + 혼성화별 색상 | ✅ 구현 | `plot_predicted()` NMR_C13 분기 |
| ¹³C NMR: DEPT 구분 (CH/CH₂/CH₃/C) | ❌ 미구현 | **핵심 미구현 항목 #4** |
| Raman: 강도 스타일 피크 | ✅ 구현 | `_make_raman_figure()` |
| Raman: IR 보완 관계 (ghost 오버레이) | ❌ 미구현 | **핵심 미구현 항목 #5** |
| UV-Vis: ε / log ε 이중 뷰 | ✅ 구현 | `_make_uvvis_figure()` |
| UV-Vis: 가시광 스펙트럼 배경 컬러밴드 | ✅ 구현 | 380-750 nm 7색 |
| UV-Vis: λmax 정확한 수치 표시 | ✅ 구현 | — |
| figsize 통일 (9.0 × 4.5) | ✅ 구현 | 2026-03-11 수정 |
| 흰 배경 (백색 출판 품질) | ✅ 구현 | `_make_*_figure()` |
| PDF 일괄 내보내기 | ✅ 구현 | `SpectrumPDFExporter` |

---

## 2. 미구현 항목 우선순위 분류

### 🔴 P0 — 즉시 구현 필요 (전문성 핵심)

#### #1 ¹H NMR: 수소-피크 대응 매핑 (색상 + 번호)
**기기분석 기준 (Silverstein 8판, Ch.3 §3.3):**
- 분자 구조식(루이스 구조)에서 **화학적으로 동등한 수소(Homotopic/Diastereotopic H) 그룹**을 색상으로 분류
- 동일 색상의 수소 → 동일 색상의 NMR 피크
- 피크 옆에 `H_a`, `H_b` 등 라벨 표기
- 분자 구조식의 해당 수소에도 동일 색상 하이라이트

**구현 방법:**
```python
# RDKit으로 화학적 동등성 그룹 감지
from rdkit.Chem import rdMolDescriptors
sym_classes = list(rdMolDescriptors.GetSymmSSSR(mol))
# → 동등한 H들에 같은 인덱스 부여
# 색상 팔레트 (최대 12그룹): MATPLOTLIB_COLORS_HGROUP
H_COLORS = ['#E74C3C','#3498DB','#2ECC71','#9B59B6',
            '#F39C12','#1ABC9C','#E67E22','#34495E',...]
```

**레이아웃:**  
```
┌─────────────────────────────┬──────────────────┐
│  ¹H NMR 스펙트럼 (색상 피크) │  루이스 구조      │
│  Ha ──── 빨강 피크 (3H)      │  (Ha=빨강 표시)  │
│  Hb ──── 파란 피크 (2H)      │  (Hb=파란 표시)  │
│  적분선 곡선 표시             │                  │
└─────────────────────────────┴──────────────────┘
```

#### #2 ¹H NMR: 적분선(Integration Curve) 표시
**기기분석 기준 (Pavia 5판, Ch.5 §Integration):**
- 피크 아래에 **계단식 적분 곡선**(step integral)을 반드시 표시
- 각 피크군 아래에 **상대 수소 개수** 숫자 표기 (예: `3H`, `2H`, `1H`)
- 가장 작은 피크 = 1H로 정규화

**구현 방법:**
```python
# 피크별 면적 계산 후 step 함수로 시각화
integral_heights = np.cumsum(y_under_peaks) / y_under_peaks.max()
ax.plot(x, integral_heights * 0.3 + baseline, 
        color='#E74C3C', lw=1.5, ls='--', label='Integration')
```

#### #3 ¹H NMR: 갈라짐 패턴 (Multiplicity) 표시
**기기분석 기준:**
- 피크 상단에 `s`(singlet), `d`(doublet), `t`(triplet), `q`(quartet), `m`(multiplet) 표기
- **n+1 규칙**: 인접 C의 H 개수 n개 → (n+1)개 선으로 분열
- J-coupling 상수(Hz) 표기: 예 `J = 7.2 Hz`

**구현 방법:**
```python
# RDKit으로 인접 수소 수 계산 → multiplicity 결정
def get_multiplicity(atom, mol_h):
    neighbors_H = sum(
        n.GetAtomicNum() == 1 
        for n in atom.GetNeighbors() 
        for a in n.GetNeighbors()
        if a.GetIdx() != atom.GetIdx() and a.GetAtomicNum() == 1
    )
    return {0:'s', 1:'d', 2:'t', 3:'q'}.get(neighbors_H, 'm')
```

### 🟠 P1 — 중요 개선 항목

#### #4 ¹³C NMR: DEPT 실험 구분 표시
**기기분석 기준 (Silverstein 8판, Ch.4 §DEPT):**
- **DEPT-135**: CH, CH₃ = 양의 피크; CH₂ = 음의 피크; 4급 C = 없음
- **DEPT-90**: CH만 양의 피크
- 색상 코드: CH₃=파랑, CH₂=초록, CH=주황, 4급 C=회색

**레이아웃 추가:**
```
DEPT-135 서브플롯을 ¹³C 스펙트럼 위에 세로 배치
CH₃ + CH (↑) / CH₂ (↓) / 4급 C (없음)
```

#### #5 Raman: IR 보완 관계 Ghost 오버레이
**기기분석 기준 (Skoog §Raman 5.4):**
- IR에서 강한 피크 → 극성 진동 (비대칭)
- Raman에서 강한 피크 → 비극성 진동 (대칭)
- IR과 Raman을 같은 x축에 겹쳐 보여주면 상보성 직관적으로 파악 가능

**구현 방법:**
```python
# IR 스펙트럼을 연한 빨강으로 ghost layer
ax_raman.plot(ir_x, ir_y * 0.5, color='#FF5252', alpha=0.25, lw=0.8, ls=':')
ax_raman.text(0.97, 0.92, '점선: IR (참고)', transform=ax.transAxes,
              color='#FF5252', fontsize=7, alpha=0.7, ha='right')
```

### 🟡 P2 — 장기 개선 항목

#### #6 UV-Vis: Woodward-Fieser 규칙 공명 구조 시각화
- 공액 π 시스템 길이 → λmax 이동 표시
- 치환기 효과 (+bathochromic, -hypsochromic) 화살표 표시

#### #7 IR: 베이스라인 보정 시뮬레이션
- ATR-IR vs. KBr disk 차이 표시
- 용매 잔류 피크 마킹 (예: H₂O의 3400, 1630 cm⁻¹)

#### #8 전체: 2D 구조 + 분광 피크 인터랙티브 하이라이트
- 마우스 hover 시 피크 → 해당 원자 하이라이트
- PyQt6 `FigureCanvasQTAgg.mpl_connect('motion_notify_event')` 활용

---

## 3. 분광법별 완전한 출력 지침

---

### 3.1 IR (적외선 분광법)

#### 기본 이론 (Silverstein 8판 참조)
- **측정 원리**: 분자 쌍극자 모멘트의 변화를 수반하는 진동 모드만 IR 활성
- **진동 유형**: Stretching (σ) — symmetric, asymmetric; Bending (δ) — in-plane, out-of-plane
- **Beer-Lambert 법칙**: A = εbc (흡광도 = 몰흡광계수 × 농도 × 광경로)

#### 필수 그래프 요소
| 요소 | 규격 | 구현 상태 |
|------|------|-----------|
| x축: 파수 (cm⁻¹) | 4000→400 역순 | ✅ |
| y축: 투과율 (%) | 0~100%, 피크 하향 | ✅ |
| 배경색: 흰색 | `facecolor='white'` | ✅ |
| 지문영역 구분선 | `axvline(1500)` + 레이블 | ✅ |
| 주요 작용기 annotation | 피크 상단 텍스트 | ✅ |
| Lorentzian 브로드닝 | FWHM ≈ 20 cm⁻¹ | ✅ |
| 강도별 피크 색상 구분 | 강/약 피크 색 차별화 | 🔲 개선 필요 |

#### 작용기 피크 표준 테이블 (기기분석 교재 기준)

| 파수 (cm⁻¹) | 작용기 | 강도 | 비고 |
|------------|--------|------|------|
| 3200–3600 | O-H stretch | 강, 넓음 | 수소결합 시 브로드 |
| 3300–3500 | N-H stretch | 중간 | Primary: 2개 피크 |
| 2850–3000 | sp³ C-H | 중간 | 알케인 특징 |
| 3000–3100 | sp² C-H (방향족) | 중간 | 3030 cm⁻¹ 특징적 |
| ~3300 | sp C-H (알카인) | 강, 날카로움 | — |
| 2100–2260 | C≡C, C≡N | 약~중간 | 대칭이면 IR 비활성 |
| 1735 ± 15 | 에스터 C=O | 매우 강 | 알데히드보다 고파수 |
| 1715 ± 10 | 케톤 C=O | 매우 강 | 대표적 카르보닐 |
| 1680–1650 | 아미드 C=O | 강 | Amide I band |
| 1600, 1500 | 방향족 C=C | 중간, 2개 | 방향족 특징 |
| 1000–1300 | C-O single bond | 강 | 에테르, 알코올 |
| 700–900 | 방향족 C-H oop | 강 | 치환 패턴 결정 |

#### 그래프 코드 표준 (`_make_ir_figure`)
```python
# figsize=(9.0, 4.5), dpi=120, white background
# x: 4000→400 (invert), y: 투과율 % (반전: 피크 하향)
# 선 색상: '#C0392B' (진한 빨강-갈색) — 전통적 IR 색상
# 채움: fill_between(x, y, 100, alpha=0.15, color='#C0392B')
# 작용기 annotation: bbox=dict(boxstyle='round', fc='white', ec='gray', alpha=0.85)
# 지문영역: axvspan(400, 1500, alpha=0.04, color='#95A5A6')
```

---

### 3.2 ¹H NMR (수소 핵자기공명)

#### 기본 이론 (Pavia 5판, Ch.3-5 참조)
- **화학적 이동**: 전자차폐 효과에 의한 공명 주파수 차이 (TMS = 0 ppm 기준)
- **적분**: 피크 면적 ∝ 해당 환경의 수소 개수
- **갈라짐**: 인접 C의 H와 J-coupling (n+1 규칙)
- **핵심 영역**:
  - 0.5–3.0 ppm: 알킬 C-H (sp³)
  - 3.0–5.0 ppm: O/N 인접 C-H
  - 5.0–7.0 ppm: 알켄 =C-H
  - 6.5–8.5 ppm: 방향족 Ar-H
  - 9.0–10.0 ppm: 알데히드 CHO
  - 10.0–12.0 ppm: 카르복시산 COOH, 넓은 OH

#### 필수 그래프 요소
| 요소 | 규격 | 구현 상태 |
|------|------|-----------|
| x축: δ(ppm) 역순 | 12→0 (우에서 좌) | ✅ |
| y축: 상대 강도 | — | ✅ |
| 구역 배경 색띠 | 알킬/O인접/알켄/방향족 | ✅ 일부 |
| 루이스 구조 삽입 (우상단) | RDKit 2D 렌더링 | ✅ (smiles 전달 필요) |
| **수소-피크 색상 매핑** | 동등 H 그룹별 색상 | ❌ **미구현** |
| **적분선 (계단형)** | 피크군 아래 누적 곡선 | ❌ **미구현** |
| **갈라짐 패턴 (s/d/t/q/m)** | 피크 상단 텍스트 | ❌ **미구현** |
| 용매 피크 표시 | CDCl₃ 7.26 ppm 회색 | 🔲 개선 필요 |

#### 수소-피크 매핑 구현 계획 (P0 #1)
```python
# 1단계: RDKit으로 화학적 동등성 그룹 분류
mol_h = Chem.AddHs(Chem.MolFromSmiles(smiles))
ranks = list(Chem.rdmolfiles.CanonicalRankAtoms(mol_h, breakTies=False))
# 같은 rank = 화학적 동등 H 그룹

# 2단계: 그룹별 색상 할당
H_GROUP_COLORS = [
    '#E74C3C', '#3498DB', '#27AE60', '#9B59B6',
    '#F39C12', '#16A085', '#E67E22', '#2C3E50',
    '#8E44AD', '#1ABC9C', '#D35400', '#2980B9'
]

# 3단계: 각 H 원자 피크에 그룹 색상 적용
for i, atom in enumerate(mol_h.GetAtoms()):
    if atom.GetAtomicNum() == 1:
        group_id = rank_to_group[ranks[i]]
        color = H_GROUP_COLORS[group_id % len(H_GROUP_COLORS)]
        # 스펙트럼 피크 색상 = color
        # 루이스 구조 해당 H 하이라이트 = color

# 4단계: 루이스 구조에 동일 색상으로 H 하이라이트
drawer.DrawMolecule(mol_h,
    highlightAtoms=h_indices,
    highlightAtomColors={idx: rgba for idx, rgba in h_color_map.items()},
    highlightBonds=[], highlightBondColors={})
```

#### 레이아웃 표준
```
┌──────────────────────────────────────────────┐
│  ¹H NMR Predicted Spectrum  |  Molecule: ...  │
├────────────────────────────────┬─────────────┤
│                                │ 루이스 구조 │
│  스펙트럼 (색상 피크)           │ (H 색상 O) │
│  ─────────────────────────     │             │
│  적분선 ∫∫∫   계단형           │  Ha=빨강   │
│                                │  Hb=파랑   │
│  [δ값] [multiplicity] [nH]     │  Hc=초록   │
└────────────────────────────────┴─────────────┘
│ 구역 레이블: 알킬 | CH-O | 알켄 | 방향족 | CHO │
└──────────────────────────────────────────────┘
```

---

### 3.3 ¹³C NMR (탄소 핵자기공명)

#### 기본 이론 (Silverstein 8판, Ch.4 참조)
- **¹³C 자연존재비**: 1.1% → 신호 매우 약함, 적분 신뢰도 낮음
- **NOE 효과**: 수소 디커플링 시 피크 높이 균일하지 않음 → 탄소 개수 ≠ 피크 높이
- **DEPT**: Distortionless Enhancement by Polarization Transfer
  - DEPT-135: CH(↑), CH₂(↓), CH₃(↑), 4급 C(없음)
  - DEPT-90: CH만 양의 피크
- **핵심 영역**:
  - 0–50 ppm: sp³ 알킬 C
  - 50–90 ppm: C-O 또는 C-X (할로겐)
  - 100–150 ppm: sp² (방향족, 알켄)
  - 160–185 ppm: 에스터/카르복시산 C=O
  - 190–220 ppm: 케톤/알데히드 C=O

#### 필수 그래프 요소
| 요소 | 규격 | 구현 상태 |
|------|------|-----------|
| x축: δ(ppm) 역순 | 220→0 | ✅ |
| 구역 색띠 + 레이블 | sp³/C-O/sp²/C=O | ✅ |
| 탄소 번호 주석 (C1, C2...) | 피크 상단 | ✅ |
| 혼성화별 색상 (sp³/sp²/C=O) | — | ✅ |
| 분자 구조 이미지 (탄소번호 표기) | RDKit rdMolDraw2D | ✅ |
| **DEPT 서브플롯** | CH/CH₂/CH₃ 구분 | ❌ **미구현** |

#### DEPT 시각화 구현 계획 (P1 #4)
```python
# _make_nmr_c13_figure에 DEPT 서브플롯 추가
fig = Figure(figsize=(9.0, 6.0))  # DEPT 추가 시 높이 확장
ax_c13  = fig.add_subplot(3, 1, (1,2))  # ¹³C 스펙트럼 (2/3 공간)
ax_dept = fig.add_subplot(3, 1, 3)      # DEPT-135 (1/3 공간)

# DEPT-135 규칙:
DEPT_COLORS = {
    'CH3': '#3498DB',    # 파랑 (↑)
    'CH2': '#E74C3C',    # 빨강 (↓ — 음의 피크)
    'CH' : '#F39C12',    # 주황 (↑)
    'C'  : '#95A5A6',    # 회색 (없음 → 점선 표시)
}
```

---

### 3.4 Raman (라만 분광법)

#### 기본 이론 (Skoog "Principles of Instrumental Analysis" 참조)
- **IR vs Raman 상보성**:
  - IR 활성: 쌍극자 모멘트 변화 수반 (비대칭 진동)
  - Raman 활성: 분극률 변화 수반 (대칭 진동)
  - 대칭 분자 (CO₂ 등): IR 비활성 진동이 Raman에서 나타남
- **대표 Raman 피크**:
  - C=C 신축: ~1620 cm⁻¹ (Raman 강함)
  - C-C 신축: ~1000 cm⁻¹ (Raman 강함)
  - O-H 신축: ~3400 cm⁻¹ (Raman 약함)
  - 그래핀 G band: ~1580 cm⁻¹, D band: ~1350 cm⁻¹

#### 필수 그래프 요소
| 요소 | 규격 | 구현 상태 |
|------|------|-----------|
| x축: 라만 이동 (cm⁻¹) 정순 | 0→4000 | ✅ |
| y축: 강도 (Intensity, ↑방향) | — | ✅ |
| 선 색상: 자주/마젠타 | `#9B59B6` 계열 | ✅ |
| 주요 피크 레이블 | — | ✅ |
| **IR ghost 오버레이 (점선)** | IR을 연하게 겹침 | ❌ **미구현** |
| **형광 배경 보정 안내** | baseline 참고선 | ❌ 미구현 |

---

### 3.5 UV-Vis (자외선-가시광선 분광법)

#### 기본 이론 (Pavia 5판, Skoog 참조)
- **전자 전이 유형**:
  - σ→σ*: ~150 nm (진공 UV, 포화 화합물)
  - n→σ*: ~200 nm (O/N/S 비결합 전자쌍)
  - π→π*: 200–250 nm (공액 없는 알켄) → 공액 길어질수록 적색 이동
  - n→π*: 270–350 nm (C=O, 금지 전이 → 약함, log ε < 3)
  - 방향족 π→π*: 254 nm (B band), 204 nm (E₁ band)
- **Beer-Lambert 법칙**: A = εbc → ε = A / (bc)
- **Woodward-Fieser 규칙** (공액 다이엔):
  - 기본값: 217 nm (s-trans 다이엔)
  - 알킬 치환 +5 nm / 고리 내 이중결합 +5 nm / 치환 이중결합 +5 nm

#### 필수 그래프 요소
| 요소 | 규격 | 구현 상태 |
|------|------|-----------|
| 이중 서브플롯 (ε / log ε) | 나란히 배치 | ✅ |
| 가시광선 배경 색띠 (380-750 nm) | 7색 | ✅ |
| λmax 수치 표시 | — | ✅ |
| x축: 파장 (nm) | 200~800 nm | ✅ |
| 전이 유형 레이블 | π→π*, n→π* | 🔲 개선 필요 |
| Gaussian 브로드닝 | σ=20 nm | ✅ |
| **흡광도 A = εbc 표시** | c=10⁻⁴ M, l=1 cm 가정 | 🔲 개선 필요 |

---

## 4. 그래프 레이아웃 표준

### 4.1 figsize 통일 규격

```python
# 모든 분광 그래프: 가로 9인치 × 세로 4.5인치
STANDARD_FIGSIZE = (9.0, 4.5)
STANDARD_DPI = 120

# 예외: DEPT 추가 시
DEPT_FIGSIZE = (9.0, 6.0)

# PDF 출력 시
PDF_FIGSIZE = (11.0, 7.0)  # A4 landscape
```

### 4.2 색상 팔레트 표준

```python
# 배경: 흰색 (출판 품질)
BG_COLOR = 'white'
FIGURE_BG = 'white'

# 선 색상 (분광법별)
LINE_COLORS = {
    'IR':      '#C0392B',   # 진빨강
    'Raman':   '#8E44AD',   # 보라
    'NMR_H':   '#1A5276',   # 진파랑
    'NMR_C13': '#1E8449',   # 진초록
    'UV_Vis':  '#E67E22',   # 주황
}

# 채움 알파
FILL_ALPHA = 0.12

# 텍스트/레이블 색상
LABEL_COLOR = '#2C3E50'     # 진회색 (흰 배경에서 가독성)
GRID_COLOR  = '#ECF0F1'     # 연회색 격자

# 구역 배경 (NMR)
ZONE_COLORS = {
    'alkyl':    ('#F8F9FA', 0.6),   # 매우 연회색
    'O-adjacent': ('#EBF5FB', 0.5), # 연파랑
    'alkene':   ('#EAF7EA', 0.5),   # 연초록
    'aromatic': ('#FDF2F8', 0.5),   # 연분홍
    'carbonyl': ('#FEF9E7', 0.5),   # 연노랑
}
```

### 4.3 annotation 표준 (작용기 레이블)

```python
# 피크 레이블 bbox 스타일
ANNOTATION_STYLE = dict(
    fontsize=8,
    color='#2C3E50',
    bbox=dict(
        boxstyle='round,pad=0.25',
        facecolor='white',
        edgecolor='#BDC3C7',
        alpha=0.9,
    ),
    arrowprops=dict(
        arrowstyle='->',
        color='#7F8C8D',
        lw=0.8,
    )
)
```

---

## 5. 기기분석 전공서 참조 내용

### 5.1 Silverstein (Spectrometric Identification of Organic Compounds, 8e)

**IR 해석 체계 (Ch.2):**
- 4000–2500 cm⁻¹: X-H 신축 영역 (C-H, N-H, O-H)
- 2500–2000 cm⁻¹: 삼중결합 및 누적 이중결합 (C≡N, C≡C, C=C=O)
- 2000–1500 cm⁻¹: 이중결합 신축 (C=O, C=N, C=C)
- 1500–400 cm⁻¹: 지문영역 (단일결합 신축 + 굽힘 진동)

**¹H NMR 해석 체계 (Ch.3):**
- Shoolery 치환기 상수 (Shoolery's rules): δ(CH₂) = 0.23 + Σσ
  - σ(CH₃) = 0.47, σ(Cl) = 2.53, σ(OH) = 2.56, σ(C=O) = 1.20
- 방향족 H: 7.27 ppm (CDCl₃에서 CHCl₃ 잔류 신호 분리 주의)
- NH, OH: 넓은 피크, 위치 가변 (D₂O 교환으로 확인)

**¹³C NMR 해석 체계 (Ch.4):**
- 4급 탄소: DEPT에 나타나지 않음 → 분자 골격 확인에 핵심
- 방향족 탄소: 110–160 ppm (치환 패턴에 따라 상세 분류 가능)
- 카르보닐 탄소: 일반적으로 DEPT에서 확인 불가 → 직접 ¹³C에서만 관찰

### 5.2 Pavia (Introduction to Spectroscopy, 5e)

**NMR 구조 결정 순서 (Ch.5 §5.7):**
1. 분자식 → 불포화도(DoU) 계산: DoU = (2C + 2 + N - H - X) / 2
2. DoU → 고리 + 이중결합 수 추정
3. IR에서 작용기 확인 (C=O, O-H 등)
4. ¹³C NMR에서 탄소 환경 확인
5. ¹H NMR에서 수소 개수, 위치, 갈라짐 패턴 확인
6. 종합하여 구조 결정

**적분 이론 (Ch.3 §3.4):**
- 적분 값은 **몰당 수소 비율**을 나타냄
- 절대값이 아닌 상대값 → 가장 작은 정수비로 표현
- 예: 적분 비 2.0:1.5:1.0 → 4:3:2 또는 4H:3H:2H

### 5.3 Skoog (Principles of Instrumental Analysis, 7e)

**UV-Vis 전이 이론 (Ch.14):**
- Franck-Condon 원리: 수직 전이 → 진동 구조 (fine structure)
- 용매 효과: 극성 용매에서 π→π* 청색 이동, n→π* 적색 이동
- 몰흡광계수 크기: π→π* (ε > 10⁴), n→π* (ε < 10³)

**Raman 이론 (Ch.18):**
- Stokes vs Anti-Stokes: 실온에서 Stokes 라인 훨씬 강함
- Resonance Raman: 흡수 파장 근처 레이저 → 감도 극대화
- SERS (표면 증강 라만): 나노입자 금속 표면에서 10⁶~10⁸ 배 강화

### 5.4 NIST 웹 데이터베이스 활용

ChemGrid는 다음 공개 DB를 참조하여 분광 예측을 보정할 수 있음:

| DB | URL | 내용 |
|----|-----|------|
| NIST WebBook | `webbook.nist.gov` | IR, MS, UV-Vis 실측 스펙트럼 |
| SDBS (AIST) | `sdbs.db.aist.go.jp` | IR, NMR, MS 실측 비교 |
| PubChem | `pubchem.ncbi.nlm.nih.gov` | 분자 물성 + IR 피크 데이터 |

---

## 6. 현재 auto_generated 폴더 이미지 분석 결과

### 6.1 `temp_assets/` 디렉토리 (82개 이미지)
- `benzene_*`, `ethanol_*`, `aspirin_*` 등 주요 분자별 각 분광법 PNG
- 현재 그래프의 색상/레이아웃 참고용

### 6.2 PDF 리포트 분석 (Ethyl Benzoate Test v14)
- 현재 레이아웃: 상단 IR → 중단 NMR → 하단 UV-Vis 세로 배치
- **개선 방향**: 각 그래프를 독립 페이지(A4)로 분리하여 더 큰 크기로 출력
- 루이스 구조를 그래프 본문 좌상단이 아닌 **독립 삽화(inset)**로 배치

### 6.3 `fixed_test/batch_1_10/` (71개 파일)
- 10개 분자 배치 테스트 결과
- 대부분 동일한 figsize → 통일성 있으나 NMR 가독성 부족

---

## 7. 구현 우선순위 로드맵

```
Phase 1 (즉시):
  ✅ figsize 통일 (9.0×4.5) — 완료
  ✅ MS 탭 제거 — 완료
  ✅ NMR smiles 파라미터 전달 — 완료

Phase 2 (다음 세션):
  🔲 [P0-#1] ¹H NMR 수소-피크 색상 매핑
  🔲 [P0-#2] ¹H NMR 적분선 표시
  🔲 [P0-#3] ¹H NMR 갈라짐 패턴 (s/d/t/q/m)

Phase 3:
  🔲 [P1-#4] ¹³C NMR DEPT 서브플롯
  🔲 [P1-#5] Raman IR ghost 오버레이

Phase 4:
  🔲 [P2-#6] UV-Vis Woodward-Fieser 시각화
  🔲 [P2-#7] IR 베이스라인 보정 시뮬레이션
  🔲 [P2-#8] 인터랙티브 피크-원자 매핑
```

---

## 8. 코드 적용 위치 매핑

| 지침 항목 | 적용 파일 | 함수명 |
|-----------|-----------|--------|
| IR 출력 표준 | `popup_predicted_spectrum.py` | `_make_ir_figure()` |
| ¹H NMR 출력 표준 | `popup_predicted_spectrum.py` | `_make_nmr_h1_figure()` |
| ¹³C NMR 출력 표준 | `popup_predicted_spectrum.py` | `_make_nmr_c13_figure()` |
| Raman 출력 표준 | `popup_predicted_spectrum.py` | `_make_raman_figure()` |
| UV-Vis 출력 표준 | `popup_predicted_spectrum.py` | `_make_uvvis_figure()` |
| 3D 팝업 스펙트럼 탭 | `popup_3d.py` | `SpectrumPanel._render_guide_spectrum()` |
| PDF 일괄 출력 | `agents/09_data_export/spectrum_pdf_exporter.py` | `SpectrumPDFExporter` |

---

*본 GUIDE.md는 세션마다 갱신. 미구현 항목 완료 시 상태를 ✅로 업데이트할 것.*
