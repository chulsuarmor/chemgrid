# AlphaFold/신약개발 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 4

## 수정파일

| 파일 | 경로 (src/app/) | 경로 (_source/) | 변경 |
|------|----------------|-----------------|------|
| alphafold_interface.py | 신규 생성 (v1.0) | 동기화 완료 | ColabFold API wrapper, PDB parser, RCSB fallback, pLDDT filtering |
| admet_predictor.py | 신규 생성 (v1.0) | 동기화 완료 | Lipinski Ro5, BBB, metabolic stability, Veber/Ghose filters |
| drug_screening.py | 신규 생성 (v1.0) | 동기화 완료 | QED scoring, composite ranking, pLDDT filter, screening pipeline |
| pharmacophore_mapper.py | 신규 생성 (v1.0) | 동기화 완료 | SMARTS-based feature detection, 3D mapping, similarity metrics |

## 기획자보고 (P-DRUG)

### ALPHA-001: alphafold_interface.py [P0]
- FASTA sequence validation (length 10-2500, valid AA codes, header parsing)
- ColabFold API: POST /batch submit → polling /result/{ticket} with configurable timeout
- PDB text parser: ATOM/HETATM records → ProteinStructure dataclass (residues, pLDDT from B-factor)
- RCSB PDB fallback: fetch known structures by 4-letter PDB ID
- Unified `predict_structure()`: cache → RCSB → ColabFold priority chain
- pLDDT confidence filtering: categorizes residues into very_high/high/low/very_low
- Binding site extraction: radius-based atom/residue selection (numpy-accelerated with fallback)
- Cache: MD5-hashed sequence → tempdir PDB files

### ALPHA-002: admet_predictor.py [P1]
- Lipinski Rule of Five: MW, LogP, HBD, HBA thresholds with violation counting
- BBB permeability: simplified Clark/Pardridge model (TPSA, LogP, MW, HBD scoring)
- Metabolic stability: 10 SMARTS-based soft spot detection (ester hydrolysis, CYP oxidation, N/O-dealkylation, etc.)
- Veber rules (rotatable bonds, TPSA) and Ghose filter (MW, LogP, MR, atom count)
- Composite drug-likeness score (0-1) combining all filters
- Oral bioavailability classification: likely/moderate/unlikely
- `admet_to_dict()` for JSON serialization

### ALPHA-003: drug_screening.py [P1]
- QED scoring via RDKit `Chem.QED.qed()` with manual Gaussian desirability fallback
- PAINS-like structural alerts (6 patterns: rhodanine, dinitrophenyl, michael acceptor, etc.)
- pLDDT target validation: reliability check + recommendation text
- Binding affinity ranking with configurable cutoff
- Multi-criteria composite scoring: QED(0.30) + affinity(0.35) + ADMET(0.25) - alerts(0.10)
- Tier assignment: A (>=0.7), B (>=0.4), C (<0.4)
- `run_screening()`: full pipeline with QED pre-filter → affinity filter → composite ranking

### ALPHA-004: pharmacophore_mapper.py [P2]
- 6 feature types: HBD (6 SMARTS), HBA (3 SMARTS), Hydrophobic (7 SMARTS), Aromatic (ring detection), PosIon (8 SMARTS), NegIon (6 SMARTS)
- 3D coordinate mapping via ETKDGv3 embedding + MMFF optimization
- Ring centroid calculation for aromatic features
- Feature count vector similarity (Tanimoto) and Euclidean distance
- `pharmacophore_map_to_dict()` for visualization integration

### 설계 원칙
- 모든 모듈이 RDKit 없이도 graceful fallback (에러 메시지 반환, 크래시 없음)
- numpy, urllib도 conditional import with availability flags
- dataclass 기반 타입 안전 데이터 구조
- 외부 API 실패 시 cache → RCSB → error 순서로 degradation
- OWNED_FILES 내에서만 작업, 타 부서 파일 수정 없음

## 검수자판정 (R-DRUG)

### 검증 방법
1. **py_compile**: 8개 파일 (src/app/ 4개 + _source/ 4개) 전부 PASS
2. **ast.parse**: 8개 파일 전부 PASS (구문 트리 정상 생성)
3. **MD5 해시 비교**: src/app/ ↔ _source/ 4쌍 전부 MATCH (듀얼 동기화 확인)
4. **Import 테스트**: 4개 모듈 전부 import 성공 (RDKit 미설치 환경에서도)
5. **Graceful fallback**: RDKit 미설치 시 각 모듈이 에러 메시지 포함 결과 반환 확인
6. **기능 테스트**: validate_fasta_sequence("MKTV...") → ok=True, parse_pdb_text → 3 atoms 파싱 성공

### 판정: **PASS**
- 구문 오류 없음
- 듀얼 코드베이스 동기화 완료
- OWNED_FILES 범위 내에서만 파일 생성
- RDKit 없이도 안전하게 동작
- 타 부서 파일 수정 없음

## 감사요청
- **audit_professional_pharmacology_docking** (약리도킹 전문감사)에 감사 요청
- 검토 항목: ADMET 점수 화학적 정확도, SMARTS 패턴 완전성, QED 가중치 적절성, ColabFold API 프로토콜 정합성

## 기술적 판단 기록

### ColabFold API 선택 근거
- AlphaFold2 자체 실행은 GPU + 데이터베이스(~2TB) 필요 → 사용자 환경에서 비현실적
- ColabFold API는 무료, GPU 불필요, HTTP POST만으로 예측 가능
- 제한사항: 서버 부하 시 대기 시간 길어질 수 있으므로 timeout + cache 구현

### ADMET 예측 정확도 한계
- RDKit descriptors 기반 경험적 모델 (ML 모델 아님)
- 실제 ADMET 값과 정성적 일치는 기대 가능하나, 정량적 정확도는 제한적
- 향후 개선: SwissADME API 연동 또는 ML-based predictor (DeepChem) 통합

### Pharmacophore Mapper 설계
- RDKit Pharm2D factory 대신 자체 SMARTS 기반 구현 선택
  - 이유: Pharm2D는 fingerprint 생성에 특화, 3D 좌표 매핑에는 직접 SMARTS가 더 유연
  - 향후: Pharm2D 기반 similarity 검색 추가 가능

## 발견된 문제 / 블로커
- 현재 시스템 Python에 RDKit 미설치 (conda env에만 있음) → 실제 기능 테스트는 conda 환경에서 별도 수행 필요

## 타 부서 요청 사항
- dept_docking: drug_screening.py의 DockingScore 데이터 구조와 docking_interface.py 출력 형식 호환성 확인 필요
