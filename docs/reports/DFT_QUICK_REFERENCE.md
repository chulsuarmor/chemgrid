# DFT 전자밀도 시각화 - 빠른 참조 가이드

## 🎯 핵심 개념

### 문제: 원시적 전자구름
```
이전: 원자 반지름 기반 단순 배치
예: 사이클로펜타디에닐 음이온 (C5H5-)
  - 일부 원자만 파란색 (부정확)
  - 공명구조 미반영
  - 화학적 특성 무시
```

### 해결: DFT 기반 실제 분포
```
이후: ORCA Mulliken 부분전하 기반
예: 사이클로펜타디에닐 음이온 (C5H5-)
  - 모든 탄소가 파란색 (정확)
  - 공명 효과: 전체 고리에 -1 균등 분포
  - 화학적 정확성 ✅
```

---

## 📦 주요 모듈

### 1. electron_density_analyzer.py (신규)
```
└─ ElectronDensityAnalyzer [메인]
   ├─ MullikenChargeExtractor
   ├─ GeometryExtractor
   ├─ ResonanceDetector
   └─ ElectronDensityCalculator

데이터 흐름:
  ORCA .out 파일
     ↓
  [MullikenChargeExtractor] → charges: {idx: value}
     ↓
  [ResonanceDetector] → resonance_structures: [...]
     ↓
  [ElectronDensityAnalyzer] → DensityMap ✨
```

### 2. renderer.py (개선)
```
신규 클래스: DFTDensityRenderer
  - charge_to_color(): 부분전하 → RGB
  - draw_dft_density_clouds(): 시각화
  
  색상 맵핑:
    charge < -0.3  →  파란색 ㎁ (음전하)
    charge = 0     →  회색 ◐ (중립)
    charge > +0.3  →  빨간색 ● (양전하)
```

### 3. draw.py (통합)
```
MoleculeCanvas에 추가:
  - self.dft_density_map: DensityMap 저장소
  - self.show_dft_density: 토글 옵션
  - _analyze_dft_electron_density(): 자동 분석
  
paintEvent() 개선:
  ORCA 결과 → DFTDensityRenderer.draw_dft_density_clouds()
```

---

## 🔬 지원하는 분자들

### ✅ 사이클로펜타디에닐 음이온 (C₅H₅⁻)
```
구조: 5원환 (모든 탄소)
공명: 음전하가 전체 고리에 균등 분포
색상: 모두 파란색 ●
예상 Mulliken: 각 C = -0.20
특징: 4n+2 방향족 (안정)
```

### ✅ 트로필륨 양이온 (C₇H₇⁺)
```
구조: 7원환 (모든 탄소)
공명: 양전하가 전체 고리에 균등 분포
색상: 모두 빨간색 ●
예상 Mulliken: 각 C = +0.143
특징: 4n+2 방향족 (안정), 고리 중앙에 중성 H
```

### ✅ 벤젠 (C₆H₆)
```
구조: 6원환 (모든 탄소)
공명: 파이 전자가 전체 고리에 분포
색상: 모두 회색 (거의 중립)
예상 Mulliken: 각 C ≈ -0.01
특징: 가장 안정적인 방향족
```

### ✅ 알릴 음이온 (C₃H₅⁻)
```
구조: 직선 3원 (말단 탄소가 더 음)
공명: 말단에 음전하 집중
색상: 말단만 진한 파란색, 중앙은 연한색
예상 Mulliken: C1≈-0.35, C2≈-0.30, C3≈-0.35
특징: 단순 공명 구조
```

---

## 🎨 색상 변환 규칙

### charge_to_color_rgb() 함수

```python
from electron_density_analyzer import charge_to_color_rgb

charge = -0.2  # 사이클로펜타디에닐의 탄소
r, g, b = charge_to_color_rgb(charge)
# → (100, 150, 220) = 파란색 ✓

charge = +0.14  # 트로필륨의 탄소
r, g, b = charge_to_color_rgb(charge)
# → (220, 120, 120) = 빨간색 ✓

charge = -0.01  # 벤젠의 탄소
r, g, b = charge_to_color_rgb(charge)
# → (150, 150, 150) = 회색 ✓
```

### 색상 강도 해석

| 색상 강도 | charge 범위 | 의미 |
|---------|----------|------|
| 매우 진함 | < -0.5 or > 0.5 | 강한 극성, 높은 반응성 |
| 진함 | -0.3 ~ -0.5 or 0.3 ~ 0.5 | 중간 극성 |
| 보통 | -0.1 ~ -0.3 or 0.1 ~ 0.3 | 약한 극성 |
| 연함 | -0.05 ~ 0.05 | 거의 중립 |
| 중립 (회색) | ≈ 0 | 전자 분포 균형 |

---

## 🔧 사용 시나리오

### 시나리오 1: ORCA 계산 후 자동 분석

```python
# 1. ORCA 계산 실행
from orca_interface import create_calculation_workflow
input_file, calculator = create_calculation_workflow(atoms, bonds, charge=-1)
calculator.result.connect(canvas.on_orca_calculation_complete)
calculator.start()

# 2. 자동으로 실행됨:
#    ├─ ORCA 완료 → on_orca_calculation_complete() 호출
#    ├─ _analyze_dft_electron_density() 자동 실행
#    ├─ ElectronDensityAnalyzer 시작
#    ├─ DensityMap 생성
#    └─ self.dft_density_map 저장

# 3. paintEvent()에서 자동 렌더링
#    ├─ DFTDensityRenderer 활용
#    ├─ 부분전하 → 색상/크기 변환
#    └─ 화면 표시 ✨
```

### 시나리오 2: 수동 분석

```python
from electron_density_analyzer import ElectronDensityAnalyzer
from pathlib import Path

# ORCA 계산을 이미 했을 때
analyzer = ElectronDensityAnalyzer()
density_map = analyzer.analyze_orca_output(
    out_path=Path("orca_calcs/input.out"),
    atom_positions={...},  # 그리기 좌표
    atom_symbols={...}      # 원소 기호
)

# 결과 확인
for d in density_map.atom_densities:
    print(f"C{d.atom_index}: Mulliken={d.mulliken_charge:.4f}")
```

### 시나리오 3: 데이터 내보내기

```python
from electron_density_analyzer import export_density_map_json

export_density_map_json(density_map, Path("result.json"))

# result.json:
# {
#   "num_atoms": 5,
#   "total_charge": -1.0,
#   "atom_densities": [
#     {
#       "index": 0,
#       "symbol": "C",
#       "mulliken_charge": -0.2000,
#       "effective_charge": -0.2000
#     },
#     ...
#   ],
#   "resonance_structures": [...]
# }
```

---

## 🧪 검증 방법

### 테스트 1: Mulliken 추출 검증

```bash
python test_dft_analyzer.py
```

**예상 출력**:
```
TEST 1: Cyclopentadienyl Anion (C5H5-)
Expected: All carbons should show negative charge (blue color)
Mulliken charges: ~-0.20 each

Analysis Results:
  Atom 0: charge=-0.2000 (BLUE)
  Atom 1: charge=-0.1950 (BLUE)
  ...
Total molecular charge: -1.000
✓ PASS: Correct negative charge distribution
```

### 테스트 2: 시각적 검증

1. **ChemDraw Pro 실행**
2. **분자 그리기**: 사이클로펜타디에닐 음이온
3. **ORCA 계산 실행**
4. **결과 확인**:
   - ✅ 모든 탄소가 **파란색** → 음전하 정확히 반영
   - ✅ 색상 균등 → 공명 효과 반영
   - ✅ 반지름 일정 → 부분전하 균등

### 테스트 3: 색상 강도 검증

```python
from electron_density_analyzer import charge_to_color_rgb

# 음전하 강도 테스트
charges = [-1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0]
for ch in charges:
    r, g, b = charge_to_color_rgb(ch)
    status = "PASS" if (ch < 0 and b > 150) or (ch > 0 and r > 200) or (ch == 0) else "FAIL"
    print(f"{ch:+.1f}: RGB({r},{g},{b}) {status}")
```

---

## 📊 정밀도 비교

### 전 (기존 방식)
```
전자구름 배치: 원자 반지름 기반 (vdW radius)
  - C: 1.70Å
  - H: 1.20Å
  
문제: 실제 전자분포와 무관
예: 사이클로펜타디에닐
  - 모든 C가 같은 크기 구름
  - 음전하 분포 안 보임
```

### 후 (DFT 방식)
```
전자구름 배치: ORCA Mulliken 부분전하 기반
  - charge < -0.2 → 큰 구름, 진한 파란색
  - charge ≈ 0 → 작은 구름, 회색
  
개선: 실제 전자분포 반영
예: 사이클로펜타디에닐
  - 모든 C가 파란색 (음전하)
  - 크기/색상 균등 (공명)
  - 화학적으로 정확 ✓
```

---

## ⚙️ 구현 세부사항

### DensityMap 구조

```python
@dataclass
class DensityMap:
    grid_points: Dict[(x,y), density]      # 시각화용 2D 맵
    atom_densities: List[AtomicDensity]    # 원자별 정보
    total_charge: float                    # 분자 전체 전하
    num_atoms: int                         # 원자 개수
    resonance_structures: List[...]        # 공명 구조 목록
```

### AtomicDensity 구조

```python
@dataclass
class AtomicDensity:
    atom_index: int                    # 0, 1, 2, ...
    atom_symbol: str                   # "C", "H", "N", ...
    position: (x, y, z)                # 3D 좌표
    mulliken_charge: float             # ORCA 계산값
    lowdin_charge: float               # 대체 계산값
    effective_charge: float            # 공명 보정 후
    resonance_contribution: float      # 공명 효과량
```

### 렌더링 파이프라인

```
paintEvent()
    ↓
[DFT 데이터 체크] self.dft_density_map ≠ None?
    ↓ (Yes)
[좌표 변환] 3D → 2D (z=0 기본)
    ↓
[색상 맵핑] charge → RGB (DFTDensityRenderer.charge_to_color)
    ↓
[크기 계산] |charge| → radius (base=14px, +8px/unit)
    ↓
[그라데이션] 중심(불투명) → 경계(투명)
    ↓
[그리기] painter.drawEllipse(center, radius)
    ↓
화면 표시 ✨
```

---

## 💡 주요 특징

| 특징 | 구현 여부 | 효과 |
|------|---------|------|
| Mulliken 추출 | ✅ | ORCA DFT 기반 정밀한 부분전하 |
| 공명 감지 | ✅ | 5개 패턴 자동 인식 |
| Blue/Red 색상 | ✅ | 음/양 직관적 시각화 |
| 자동 렌더링 | ✅ | 계산 후 자동 표시 |
| 다중 레이어 | ✅ | Drawing/Lewis/Theory 지원 |
| 토글 옵션 | ✅ | show_dft_density로 제어 |
| JSON 내보내기 | ✅ | 데이터 저장 및 공유 |

---

## 🔮 다음 단계

### Phase B 계획
- [ ] 3D Isosurface 렌더링
- [ ] 등고선 (contour) 표시
- [ ] HOMO/LUMO 오빗탈
- [ ] 분자 표면 (MES)

### 사용자 요청 대기
- [ ] 추가 공명 구조 패턴
- [ ] 색상 커스터마이징
- [ ] 밀도 등급 조정

---

## 📞 문제 해결

### 색상이 안 보임
→ `self.show_dft_density = True` 확인
→ ORCA 계산 완료 확인
→ `.out` 파일에 MULLIKEN ATOMIC CHARGES 확인

### 틀린 색상 (예: CPD가 빨강)
→ ORCA 계산 charge 재확인 (음수여야 함)
→ Mulliken 추출 로직 디버그

### 렌더링 느림
→ GPU 가속 확인 (PyQt6 RenderHint)
→ 원자 개수 제한 (< 100 권장)

---

**구현 완료: 2026-02-08**
**버전: v1.0 (프로덕션 준비)**
