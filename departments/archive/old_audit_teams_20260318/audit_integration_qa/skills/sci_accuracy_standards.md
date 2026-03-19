# SCI급 정합성 검증 기준서 — 통합QA 감사팀
> 이 문서는 모듈 간 데이터 흐름, 단위 변환, 파일 형식의 학술 표준 검증 기준입니다.
> **참조 표준**: IUPAC, PDB, ORCA, RDKit, Open Babel

---

## 1. 단위 체계 표준

### 1.1 길이
- **내부 계산**: Å (Angstrom, 10⁻¹⁰ m)
- **UI 표시**: Å 단위 명시
- **절대 금지**: 픽셀(px) 단위를 물리량으로 표시
- **변환**: 1 Bohr = 0.529177 Å

### 1.2 에너지
- **ORCA 출력**: Hartree (Eh)
- **UI 표시**: eV, kcal/mol, kJ/mol 중 사용자 선택
- **변환**: 1 Eh = 27.2114 eV = 627.509 kcal/mol

### 1.3 진동수
- **단위**: cm⁻¹ (wavenumber)
- **ORCA 출력**: cm⁻¹
- **변환**: ν(cm⁻¹) = 1/λ(cm)

## 2. 파일 형식 호환성

### 2.1 분자 파일 형식
| 형식 | 용도 | 참조 |
|------|------|------|
| SMILES | 2D 구조 입출력 | RDKit canonical |
| SDF/MOL | 3D 좌표 + 결합 정보 | MDL V2000/V3000 |
| PDB | 단백질 구조 | RCSB PDB 형식 |
| PDBQT | 도킹 입력 | AutoDock 형식 |
| XYZ | 간단한 3D 좌표 | ORCA/Avogadro |
| Cube | 전자밀도/MO | Gaussian cube format |

### 2.2 ORCA ↔ ChemGrid 인터페이스
- **입력**: .inp 파일 생성 → ORCA 실행
- **출력**: .out 파싱 + .cube 파일 읽기
- **주의**: ORCA 6.1.1에는 orca_plot 없음 → %plots 블록 사용

## 3. 데이터 정합성 검증

### 3.1 SMILES ↔ 2D ↔ 3D 일치
- SMILES에서 생성한 2D 구조의 원자/결합 수 일치
- 2D→3D 변환 후 결합 길이/각도 합리성
- 수소 추가(AddHs) 일관성

### 3.2 전하 보존
- 분자 전체 형식 전하 합 = 분자 순전하
- Gasteiger 부분전하 합 ≈ 0 (중성분자)
- 이온의 경우 합 = 이온 전하

## 4. NLM 동아리 세션 연동 메모
> **향후 참조**: 사용자의 NLM '동아리 대화' 세션은 간이 Raman 분광기
> 하드웨어 구축 관련 전문지식 보유. 분광기 하드웨어 통합 시 MCP 경유 소통 예정.
> 현재는 미사용 — Phase 8+ 이후 활성화 대상.

## 5. 참조 문헌
1. IUPAC Gold Book — 표준 화학 용어 및 단위
2. RCSB PDB: https://www.rcsb.org/
3. RDKit Documentation: Canonical SMILES, Mol objects
4. Open Babel: Format conversion reference
5. ORCA Manual 6.0: Input/Output file formats
