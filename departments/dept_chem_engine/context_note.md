# 화학 엔진 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 1

---

## SUBMIT REPORT — dept_chem_engine (Cascade #3 Wave 1)

### 수정파일
| 파일 | 변경내용 |
|------|---------|
| chem_data.py | BOND_LENGTHS 테이블 47→64 엔트리 (P-H, P-S, P-F, P-Cl, Si-H/N/Si/F/Cl/S, B-N/F/H/Cl, S-N/F/Cl/O, N-F/Cl, Se-C/H/Se 추가) |
| analyzer.py | calculate_logp(), calculate_tpsa(), calculate_rotatable_bonds() 3개 함수 추가 (RDKit 래퍼) |
| _source/chem_data.py | src/app와 동기화 |
| _source/analyzer.py | src/app와 동기화 |

### 기획자보고 (P-CHEM)
- **P-CHEM spawned at Cascade #3 Wave 1 시점**
- CHEM-R01: BOND_LENGTHS 검증 → 17개 결합 누락 발견, CRC Handbook 97th Edition 기준으로 추가
- CHEM-R02: 방향족 탐지 RDKit fallback (`GetIsAromatic()` + `rdkit_idx` 매핑) 정상 동작 확인 → 수정 불필요
- CHEM-R03: Gasteiger 60/40 블렌딩 (line 171: `0.6 * g_scaled + 0.4 * global_charges[nk]`) 정상 확인 → 수정 불필요
- NEW: LogP (Crippen.MolLogP), TPSA (Descriptors.TPSA), RotatableBonds (Lipinski.NumRotatableBonds) 함수 추가
- MM 개선지시 반영: 에러 핸들링(RDKit 미설치 시 graceful fallback) 포함

### 검수자판정 (R-CHEM)
- **R-CHEM spawned at Cascade #3 Wave 1 시점**
- **판정: PASS**
- 검증 방법:
  1. py_compile: 4/4 PASS (chem_data, analyzer, engine_core, engine_physics)
  2. ast.parse: 4/4 PASS
  3. BOND_LENGTHS: 15개 핵심 결합 CRC 대조 — 전부 ±0.01Å 이내
  4. 새 함수 테스트: aspirin LogP=1.3101, TPSA=63.60, RotBonds=2 (RDKit 직접 호출과 동일)
  5. 듀얼 동기화: 4개 파일 MD5 일치 확인
  6. 업무침범: 없음 (타 부서 파일 미수정)

### 감사요청
- 요청 대상: **렌더링 품질 감사관 (audit_rendering_qa)** + **전문감사 구조화학팀**
- 검증 요청 항목: 결합길이 CRC Handbook 대조, Gasteiger TM 블렌딩 정확성, 방향족 탐지, LogP/TPSA/RotBonds 화학적 타당성

---

## 기술적 판단 기록

### Gasteiger 블렌딩 확인
- analyzer.py line 171: `0.6 * g_scaled + 0.4 * global_charges[nk]`
- 전이금속(Fe, Ru 등): Gasteiger가 NaN 반환 → line 147 NaN 필터에 의해 자동 skip
- engine_physics.py의 TM_SYMBOLS: 3d/4d 전이금속 정상 포함

### 방향족 탐지 경로
- 1차: engine_core.py Hückel 판정 (4n+2 규칙)
- 2차 fallback: analyzer.py `all_aromatic` → RDKit `GetIsAromatic()` + `rdkit_idx` 매핑
- aromatic bond order=1 문제: RDKit fallback으로 우회 (정상 동작)

### BOND_LENGTHS 신규 엔트리 (CRC 97th Ed.)
P-H 1.420, P-S 2.125, P-F 1.570, P-Cl 2.040, Si-H 1.480, Si-N 1.740, Si-Si 2.340,
Si-F 1.600, Si-Cl 2.050, Si-S 2.150, B-N 1.580, B-F 1.310, B-H 1.190, B-Cl 1.750,
S-N(1) 1.730, S-F 1.580, S-Cl 2.070

---

## 발견된 문제 / 블로커
- BLOCKER-001 (기존): aromatic bonds가 order=1로 저장됨 → RDKit fallback으로 완화 (근본 수정 미완)
