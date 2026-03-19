# SCI급 정합성 검증 기준서 — 시각적 피드백 감사팀
> 이 문서는 스크린샷 기반 시각 검증의 학술 표준 기준입니다.
> **참조 표준**: Avogadro, GaussView, ChemDraw, Jmol, ORCA output

---

## 1. 시각적 정합성 기준 (Avogadro/ORCA 참조)

### 1.1 분자 렌더링 품질
- **Ball & Stick**: 원자 반경 비례 (van der Waals 비율), 결합 원통형
- **Avogadro 참조**: 원자 색상 = CPK convention (C:회색, N:파랑, O:빨강, S:노랑, H:흰색)
- **ORCA 참조**: xyz2mol 변환 후 결합 자동 감지 = 공유결합 반경 합 + 0.4Å tolerance

### 1.2 ESP Surface 시각 검증
- 색상이 Red(−)→Blue(+) 순서인지 스크린샷으로 확인
- 전자가 풍부한 곳(O, N lone pair 근처)이 빨간색인지
- 전자가 부족한 곳(양전하, H 근처)이 파란색인지

### 1.3 Lewis 구조 시각 검증
- 론쌍 점이 올바른 위치에 표시되는지
- 형식전하 숫자가 명확히 보이는지
- 공명 구조 표기 시 이중화살표(↔)가 있는지

### 1.4 궤도함수 시각 검증
- **절대 금지**: scatter-point 렌더링 ("개구리알")
- **필수**: connected isosurface (매끄러운 곡면)
- **양/음 위상**: 두 가지 색상으로 명확 구분
- **Avogadro/Jmol 참조**: 매끄러운 marching cubes isosurface

## 2. 레이아웃 및 라벨링 기준

### 2.1 축 라벨
- 모든 그래프에 X/Y축 라벨 + 단위 필수
- 글씨 크기: 최소 10pt 이상 (읽기 가능)
- **학회 포스터 기준**: 1m 거리에서 읽을 수 있는 크기

### 2.2 색상 대비
- 배경색과 전경색의 명도 차이 충분
- 색맹 고려: red-green 외에 blue-orange 대안 제공 권장

### 2.3 범례 (Legend)
- 색상 매핑이 있는 시각화에는 반드시 범례 포함
- ESP: 전하 값 범위 + 색상 바
- MO: isovalue + 양/음 색상 표시

## 3. 36개 시나리오별 PASS/FAIL 판정

| # | 시나리오 | 핵심 검증 항목 |
|---|---------|---------------|
| 1 | ESP 전자구름 (H₂O) | O 주위 빨간색, H 주위 파란색 |
| 2 | ESP 전자구름 (벤젠) | 링 위/아래 빨간색 (π전자) |
| 3 | Lewis 론쌍 (H₂O) | O에 2쌍 |
| 4 | Lewis 론쌍 (NH₃) | N에 1쌍 |
| 5 | Lewis 론쌍 (아세트산) | 각 O에 2쌍 |
| 6 | 형식전하 (NO₃⁻) | N에 +1 |
| 7 | R/S 표기 | 정확한 CIP 우선순위 |
| 8 | Wedge/Dash | 3D 투영과 일치 |
| 9-13 | 스펙트럼 5종 | 축 방향/단위/피크 위치 |
| 14-16 | 3D Ball&Stick | CPK 색상, 결합 측정 |
| 17-20 | 진동 모드 | 화살표 방향, 진동수 라벨 |
| 21-24 | 도킹 UI | PDBQT, grid box, scoring |
| 25-28 | 반응 메커니즘 | 곡선 화살표, 전자 흐름 |
| 29-32 | 합성 경로 | 역합성 화살표, 시약 조건 |
| 33-36 | 궤도함수 | isosurface(≠scatter), 위상 색 |

## 4. 참조 문헌
1. CPK color convention — Corey, Pauling, Koltun (1952)
2. Avogadro visualization: https://avogadro.cc/docs/
3. Jmol scripting: http://jmol.sourceforge.net/
4. GaussView manual — ESP surface rendering
5. ORCA 6.0 Manual — %plots visualization
