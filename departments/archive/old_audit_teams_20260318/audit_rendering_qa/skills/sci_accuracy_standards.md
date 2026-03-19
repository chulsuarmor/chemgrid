# SCI급 정합성 검증 기준서 — 렌더링QA 감사팀
> 이 문서는 렌더링(ESP, Lewis, Theory) 출력이 학술 표준에 부합하는지 검증하는 기준입니다.
> **참조 표준**: Avogadro 1.2/2.0, ORCA 6.x output, Gaussian, GaussView, Jmol

---

## 1. ESP (Electrostatic Potential) 전자구름 표준

### 1.1 색상 매핑 (Color Convention)
- **국제 표준**: Red(−) → Yellow → Green → Cyan → Blue(+)
  - ORCA `%plots` / GaussView / Avogadro 모두 이 rainbow 스킴 사용
  - ChemGrid도 이 매핑을 정확히 따라야 함
- **값 범위**: Hartree 단위 또는 kcal/mol. 범위 지정이 없으면 min/max 자동 스케일링
- **조밀도**: isosurface density = 0.002 e/bohr³ (표준 van der Waals surface)

### 1.2 Gasteiger 전하 정합성
- **RDKit `ComputeGasteigerCharges()`** 사용
- **Blending rule**: 60% Gasteiger + 40% custom (ChemGrid 규칙)
- **검증 방법**: 벤젠(C₆H₆)의 모든 탄소가 동일 전하, H₂O의 O가 음(−), ethanol OH의 O가 음(−)
- **Avogadro 참조**: Open Babel Gasteiger charges → 소수점 3자리까지 비교

### 1.3 ESP 표시 조건
- `view_state == "Theory"` 일 때만 표시 (Drawing/Lewis 모드에서는 숨김)
- sp3 lone pair 필터 적용 여부 확인

## 2. Lewis 구조 표현 표준

### 2.1 론쌍 (Lone Pairs)
- **H₂O**: O에 2쌍 론쌍 (4개 점)
- **NH₃**: N에 1쌍 론쌍 (2개 점)
- **아세트산(CH₃COOH)**: C=O의 O에 2쌍, C-OH의 O에 2쌍
- **Avogadro/Jmol**: Lone pair는 별도 표시하지 않지만, Lewis 구조에서는 필수
- **교과서 기준**: Atkins "Chemical Principles", Clayden "Organic Chemistry" 의 Lewis dot 표기법

### 2.2 형식 전하 (Formal Charge)
- FC = 원자가전자 − 비결합전자 − ½(결합전자)
- **표기**: 원 안에 + 또는 − 기호 (예: NH₄⁺의 N에 +1)
- **검증**: NO₃⁻(N:+1, 각 O:−⅔ resonance average), SO₄²⁻(S:+2)

### 2.3 공명 (Resonance)
- 벤젠: Kekulé 구조 또는 원형 표기
- 카르복실레이트(RCOO⁻): 두 산소 동등
- **RDKit `Chem.ResonanceMolSupplier`**: 공명 구조 열거 가능 → 결합 차수 평균화

### 2.4 라디칼
- 홑전자: 단일 점(·)으로 표기
- **TEMPO, NO₂**: 라디칼 종의 올바른 표기 확인

## 3. 입체화학 표현 표준

### 3.1 CIP 우선순위 (R/S)
- **IUPAC 2013 권고안** 기준
- Cahn-Ingold-Prelog 규칙: 원자번호 > 질량수 > 연결원자
- **RDKit**: `Chem.AssignStereochemistry(mol, cleanIt=True, force=True)`
- **Avogadro**: 자동 R/S 할당 미지원 → ORCA/Gaussian output에서 참조

### 3.2 Wedge-Dash 표기
- 굵은 쐐기(Wedge): 관찰자 방향으로 나옴
- 점선 쐐기(Dash): 관찰자 반대 방향
- **ChemDraw/Avogadro 표준**: 쐐기 너비가 결합 길이의 ~15-20%

### 3.3 E/Z 이성질체
- C=C 이중결합 주위 시스/트랜스
- 우선순위 높은 치환기가 같은 쪽: Z(zusammen)
- **RDKit**: `Chem.SetBondStereoFromGeometry(mol)`

## 4. 학술 출판물 수준 검증 체크리스트

| 항목 | 기준 | 참조 소프트웨어 |
|------|------|----------------|
| ESP 색상 | Red(−)→Blue(+) | Avogadro, GaussView |
| Gasteiger 전하 합 | ≈0 (중성분자) | RDKit, Open Babel |
| Lewis 론쌍 수 | 옥텟 규칙 만족 | 교과서 (Atkins) |
| 형식전하 합 | = 분자 순전하 | Clayden OrgChem |
| R/S 할당 | CIP 2013 | RDKit |
| Wedge/Dash | 3D→2D 투영 정합 | ChemDraw |
| 공명 구조 | 모든 기여 구조 동등 표기 | ResonanceMolSupplier |
| 결합 길이 | Å 단위 (px 아님) | Avogadro, ORCA |
| 결합 각도 | degree (±0.5°) | ORCA geometry opt |
| 전자밀도 | isoval=0.002 e/bohr³ | Gaussian, ORCA |

## 5. FAIL 판정 기준 (즉시 시정명령)
- ESP 색상이 반전되어 있음 (양전하에 빨강 등)
- 론쌍이 완전히 누락됨
- 형식전하 합 ≠ 분자 순전하
- R/S 할당이 반대
- Wedge/Dash 방향이 3D 좌표와 불일치
- 결합 길이가 픽셀 단위로 표시됨 (Å이어야 함)
- 공명 구조에서 한 쪽에만 이중결합 고정

## 6. 참조 문헌
1. Atkins, P. "Chemical Principles" 7th ed.
2. Clayden, J. et al. "Organic Chemistry" 2nd ed.
3. IUPAC Recommendations 2013 — Stereochemical nomenclature
4. Avogadro Documentation: https://avogadro.cc/docs/
5. ORCA Manual 6.0: Input Library, %plots block
6. RDKit Documentation: Gasteiger charges, ResonanceMolSupplier
