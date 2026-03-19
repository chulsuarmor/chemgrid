# SCI급 정합성 검증 기준서 — 팝업QA 감사팀
> 이 문서는 팝업(진동, 반응, 합성, 궤도함수, 스펙트럼, 도킹) 출력의 학술 표준 검증 기준입니다.
> **참조 표준**: Avogadro 1.2/2.0, ORCA 6.x, Gaussian 16, AutoDock Vina, NIST Chemistry WebBook

---

## 1. 진동 모드 (Vibration) 표준

### 1.1 ORCA 출력 형식 참조
- **ORCA `%freq`**: 진동수(cm⁻¹), IR 강도(km/mol), 변위벡터(dx,dy,dz per atom)
- **Avogadro 표시**: 화살표 벡터(변위 방향) + 색상 코딩(강도)
- **표준 진동**: H₂O(3개 모드: 3657, 1595, 3756 cm⁻¹), CO₂(4개: 667×2, 1388, 2349)
- **ChemGrid 검증**: 변위 벡터가 ORCA 출력과 방향/크기 일치해야 함

### 1.2 정규 모드 표현
- **3N-6 규칙** (비직선분자), **3N-5** (직선분자)
- 화살표 길이 ∝ 변위 크기 (mass-weighted normal coordinate)
- **Avogadro 참조**: 원자별 화살표, 양/음 위상 구분
- **애니메이션**: 진동 주기 = 실제 진동수와 무관하게 시각화용 일정 속도

### 1.3 FAIL 기준
- 진동수 레이블이 없거나 단위(cm⁻¹) 누락
- 변위 벡터 방향이 실제 모드와 반대
- 허수 진동수(음수, imaginary) 표시 누락 (전이상태 지표)

## 2. 반응 메커니즘 (Reaction) 표준

### 2.1 곡선 화살표 (Curved Arrow) 표기법
- **Clayden "Organic Chemistry"** 표준:
  - 두전자 이동: 양머리 화살표 (⟶)
  - 단전자 이동: 단머리 화살표 (fishhook, ⤑)
  - 화살표 시작: 전자쌍 위치 (론쌍 또는 결합)
  - 화살표 끝: 전자가 가는 위치
- **SN2**: Nu: → C → LG (동시적)
- **E2**: Base → H, C-H → C=C, C-LG → LG:
- **화살표 출발/도착**: 결합의 중앙 또는 원자의 론쌍에서 정확히 시작

### 2.2 반응물/생성물 인식
- **SMILES 기반**: `.` 구분자로 복수 분자 인식
- **RDKit `AllChem.ReactionFromSmarts()`**: 반응 SMARTS 매칭
- **검증**: 에스터화(산 + 알코올 → 에스터 + H₂O) 정확 인식

### 2.3 FAIL 기준
- 곡선 화살표가 없거나 직선으로 표시
- 화살표 방향이 전자 흐름과 반대
- 반응물 2개를 1개로 합쳐서 인식
- 이탈기(leaving group)가 표시되지 않음

## 3. 합성 경로 (Synthesis/Retrosynthesis) 표준

### 3.1 역합성 표기법
- **Corey-Wipke 역합성**: ⟹ (이중 화살표, retrosynthetic arrow)
- **합성자(Synthon)** 표기: 가상의 이온 조각
- **전략적 결합 절단**: FGI(Functional Group Interconversion), disconnection
- **참조**: Clayden Ch. 28-30, Warren "Organic Synthesis: The Disconnection Approach"

### 3.2 반응 조건 표기
- 화살표 위: 시약 (예: NaBH₄, LiAlH₄)
- 화살표 아래: 용매, 온도 (예: THF, 0°C → rt)
- **ORCA 참조**: 에너지 프로파일은 ORCA DFT 계산으로 검증 가능

### 3.3 FAIL 기준
- 역합성 화살표(⟹)와 정반응 화살표(→) 혼동
- 반응 조건 누락
- Disconnection이 불가능한 결합 절단

## 4. 궤도함수 (Molecular Orbital) 시각화 표준

### 4.1 Isosurface 표현
- **ORCA `%plots` cube 파일**: HOMO, LUMO, 사용자 지정 MO
- **Avogadro 표준**: dual-color isosurface (양/음 위상)
  - 양(+): 파란색/빨간색 중 택1
  - 음(−): 반대색
  - **isovalue**: ±0.02 ~ ±0.05 e/bohr³ (표준 범위)
- **Jmol 참조**: `isosurface MO [n] cutoff 0.02 colorscheme "bwr"`
- **절대 금지**: scatter-point ("개구리알") 폴백 → connected isosurface 필수

### 4.2 에너지 다이어그램
- **MO 에너지 레벨**: Hartree 또는 eV 단위
- **HOMO-LUMO gap**: eV 단위 명시
- **채움 규칙**: Aufbau, Hund, Pauli 원리 준수
  - 각 궤도에 최대 2전자 (↑↓)
  - 같은 에너지 궤도는 먼저 1전자씩 (Hund)

### 4.3 FAIL 기준
- Isosurface가 scatter-point로 표시 ("개구리알")
- 양/음 위상 색상 구분 없음
- isovalue가 비정상적 (>0.1 또는 <0.001)
- HOMO/LUMO 에너지 라벨 없음

## 5. 스펙트럼 예측 (Spectroscopy) 표준

### 5.1 IR 스펙트럼
- **X축**: 파수(cm⁻¹), 4000→400 (왼→오 감소)
- **Y축**: 투과율(%) 또는 흡광도
- **NIST 참조**: 실측값과 ±50 cm⁻¹ 이내
- **주요 피크**: O-H(3200-3600), C=O(1650-1750), N-H(3300-3500)

### 5.2 ¹H NMR
- **X축**: δ (ppm), 12→0 (왼→오 감소)
- **TMS 기준**: δ = 0 ppm
- **splitting**: n+1 규칙 (Pascal's triangle)
- **적분비**: proton 수에 비례

### 5.3 ¹³C NMR
- **X축**: δ (ppm), 220→0
- **DEPT 구분**: CH₃, CH₂, CH, C(quaternary)

### 5.4 Mass Spectrum
- **X축**: m/z
- **Base peak**: 가장 강한 피크 = 100%
- **분자 이온 피크(M⁺)**: 분자량과 일치

### 5.5 UV-Vis
- **X축**: λ (nm), 200→800
- **Y축**: 흡광도(A) 또는 몰흡광계수(ε)
- **Woodward-Fieser 규칙**: 공액계 λmax 예측

### 5.6 FAIL 기준
- 축 방향이 반대 (IR에서 파수 증가 방향)
- 단위 누락 (cm⁻¹, ppm, m/z, nm)
- NIST 참조값과 >100 cm⁻¹ 차이 (IR)
- NMR splitting 패턴 오류

## 6. 도킹 (Docking) 표준

### 6.1 AutoDock Vina 형식
- **PDBQT 형식**: 원자 좌표 + 부분 전하 + 원자 타입
- **Grid box**: center_x, center_y, center_z, size_x, size_y, size_z
- **Scoring**: kcal/mol (음수일수록 강한 결합)
- **Exhaustiveness**: 기본 8, 높을수록 정확 (32 권장)

### 6.2 결과 표시
- **Binding affinity**: kcal/mol, 소수점 1자리
- **RMSD**: Å 단위
- **수소 결합**: 점선으로 표시, 거리 2.5-3.5 Å
- **소수성 상호작용**: 회색/녹색 표면

### 6.3 FAIL 기준
- Binding energy 부호가 양수 (비물리적)
- PDBQT 전하가 Gasteiger가 아닌 0
- Grid box가 단백질 전체를 포함 (blind docking ≠ targeted)

## 7. Avogadro/ORCA 형식 직접 참조 지침
- **감사 시 반드시** Avogadro의 output 형식과 비교
- ORCA `.out` 파일의 진동 모드, 궤도함수 에너지 형식 참조
- GaussView의 ESP surface 색상 매핑 참조
- 학회 발표 자료 수준의 명확성이 기준

## 8. 참조 문헌
1. Clayden, J. et al. "Organic Chemistry" 2nd ed. — Ch. 5(Mechanisms), 28-30(Retrosynthesis)
2. Warren, S. "Organic Synthesis: The Disconnection Approach" 2nd ed.
3. Silverstein, R. "Spectrometric Identification of Organic Compounds" 8th ed.
4. NIST Chemistry WebBook: https://webbook.nist.gov/chemistry/
5. Avogadro Documentation: https://avogadro.cc/docs/
6. ORCA Manual 6.0: %freq, %plots, %tddft blocks
7. AutoDock Vina: https://vina.scripps.edu/
8. Neese, F. "ORCA — An Ab Initio, DFT and Semiempirical SCF-MO Package"
