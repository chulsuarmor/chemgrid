# AlphaFold/신약개발 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #4 Wave 1+4 완료

## 🔴 PENDING

### 기존 미완 (Cascade #3 이월)
- [ ] ColabFold API 실제 호출 테스트 (짧은 서열로 end-to-end)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED
- [x] ALPHA-GUI-001: popup_alphafold.py — AlphaFold 구조 예측 팝업 (4탭: Input/3D/Residue/BindingSite) (2026-03-18)
- [x] ALPHA-GUI-002: popup_admet.py — ADMET 분석 팝업 (4탭: MolInfo/Rules/BBB/Radar) (2026-03-18)
- [x] ALPHA-GUI-003: popup_drug_screening.py — 신약 스크리닝 팝업 (4탭: Input/Results/Chart/Filters) (2026-03-18)
- [x] BUG-FIX: drug_screening.py CompoundEntry.smiles default="" 추가 (ScreeningHit default_factory 호환) (2026-03-18)
- [x] ALPHA-001: alphafold_interface.py 생성 [P0] — ColabFold API wrapper, PDB parser, RCSB fallback (2026-03-18)
- [x] ALPHA-002: admet_predictor.py 생성 [P1] — Lipinski, BBB, metabolic stability, drug-likeness (2026-03-18)
- [x] ALPHA-003: drug_screening.py 생성 [P1] — QED, composite ranking, screening pipeline (2026-03-18)
- [x] ALPHA-004: pharmacophore_mapper.py 생성 [P2] — SMARTS feature detection, 3D mapping (2026-03-18)
- [x] 듀얼 코드베이스 동기화 (src/app/ → _source/) MD5 일치 확인 (2026-03-18)
- [x] R-DRUG 검증: py_compile(8/8), ast.parse(8/8), import(4/4), fallback(4/4) 전부 PASS (2026-03-18)

## ⛔ BLOCKED
(없음)
