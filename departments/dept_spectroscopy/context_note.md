# 분광학 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 2

## 기술적 판단 기록

### [2026-03-18] Cascade #3 Wave 2 — SPEC-R01 IR/NMR 정밀도 개선

**수정 파일**: `predict_spectra.py` (src/app/ + _source/ 동기화 완료)

**(A) IR 거짓양성 =C-H str. 제거 (P0 fix)**
- 위치: `_detect_functional_groups()` — `has_sp2_ch` 로직
- 문제: C=O의 탄소가 sp2로 감지되어 acetone에 3030 cm-1 거짓 양성 피크 발생
- 수정: sp2 C-H 감지 시 (1) H가 실제로 붙어있는지 확인 (GetTotalNumHs > 0), (2) C=O 이중결합 가진 탄소 제외
- 검증: acetone IR에서 =C-H str. 피크 완전 제거 PASS

**(B) pyridine C=N SMARTS 패턴 추가 (P0 fix)**
- 위치: `_detect_functional_groups()` smarts_map + `IR_LOOKUP`
- 문제: pyridine의 C=N ring stretch가 1600 cm-1에서 C=C ring으로 잘못 귀속
- 수정: `"C=N_pyridine": "[nX2]"` SMARTS 추가, IR_LOOKUP에 1590/1480 cm-1 피크 추가
- 추가 수정: `predict_ir()` 에서 specific groups가 generic groups보다 먼저 처리되도록 우선순위 로직 도입
- 검증: pyridine IR에서 C=N ring str. @1590, @1480 정상 출력 PASS (NIST 1580 대비 diff=10)

**(C) 13C-NMR alpha-carbonyl CH3 보정 개선**
- 위치: `predict_c13_nmr()` sp3 블록
- 문제: acetone CH3 = 25.0 ppm (Silverstein 30.0 대비 diff=5.0, 경계값). CH3 보정(-5)이 alpha-carbonyl(30)과 상쇄.
- 수정: alpha-carbonyl CH3에 대해 보정값을 -5에서 -2로 변경 (30-2=28, Silverstein 30.0 대비 diff=2.0)
- 검증: acetone CH3 alpha-C=O = 28.0 ppm, diff=2.0 PASS

**(D) IR 신규 작용기 7종 추가**
- C-F (1100 cm-1), C-I (500 cm-1), S-H (2550 cm-1)
- S=O sulfoxide (1050 cm-1), S=O sulfone (1300/1150 cm-1)
- P=O (1250 cm-1), NO2 (1540/1350 cm-1)
- C=N imine (1660 cm-1)
- SMARTS 패턴: C-F, C-I, S-H, S=O_sulfoxide, S=O_sulfone, P=O, NO2 (dual pattern: neutral + charged)
- 검증: thiol S-H @2550 PASS, nitrobenzene NO2 @1540/@1350 PASS

### [2026-03-18] Cascade #3 Wave 2 — SPEC-R02 UV-Vis 예측 완성

**수정 파일**: `predict_spectra.py` (src/app/ + _source/ 동기화 완료)

**(A) Woodward-Fieser 다이엔 규칙 구현**
- 신규 함수: `_woodward_fieser_diene(mol)`
- 기본값: s-trans (heteroannular) = 217 nm, s-cis (homoannular) = 253 nm
- 치환기 보정: alkyl +5, -OR +6, -Cl/Br +5, -NR2 +5, exocyclic C=C +5
- 검증: 1,3-butadiene = 217 nm (실험값 217, diff=0) PASS

**(B) Woodward-Fieser 엔온 규칙 구현**
- 신규 함수: `_woodward_fieser_enone(mol)`
- 기본값: acyclic = 215 nm, 6-ring = 202 nm
- 치환기 보정: beta-alkyl +12, beta-OR +35, alpha-alkyl +10, alpha-OR +35, beta-Cl +15, beta-Br +25
- 엔온 n->pi* 전이도 자동 추가 (lambda_max + 50 nm, low epsilon)
- 검증: methyl vinyl ketone = 215 nm PASS

**(C) 방향족 치환기 효과 (auxochrome)**
- 벤젠 고리 K-band에 치환기 bathochromic shift 추가
- -OH: +11 nm, -OR: +7 nm, -NH2: +13 nm, -Cl: +6 nm, -Br: +2 nm
- 다환 방향족: naphthalene 275/310 nm, anthracene 350/375 nm 별도 처리

**(D) 기타 개선**
- S lone pair n->sigma* 전이 추가 (215 nm)
- chromophore 미감지 시 graceful fallback: sigma->sigma* only (150 nm)
- 에틸렌계 기존 로직은 diene/enone이 아닌 경우에만 적용 (중복 방지)

### [2026-03-18] 이전 세션 기록 (참조용)

**TASK-SPEC-001**: IR 정확성 4/4 PASS (norbornane/pyridine/acetone/ethanol)
**TASK-SPEC-002**: NMR ethanol O-H 2.6ppm, ethanol C-O 58.0ppm, acetone alpha-C=O 보정
**TASK-SPEC-003**: 팝업 크기 통일 resize(1000,700) + figsize(9.0,4.5)

## 발견된 문제 / 블로커

1. ~~**P2-BUG**: acetone IR =C-H 거짓양성~~ → **Cascade #3 Wave 2에서 수정 완료**
2. ~~**P2-BUG**: pyridine C=N SMARTS 누락~~ → **Cascade #3 Wave 2에서 수정 완료**
3. ~~**P2-NOTE**: acetone CH3 13C diff=5.0 경계값~~ → **diff=2.0으로 개선 완료**
4. **INFO**: popup_3d.py SpectrumPanel 크기 통일은 본 부서 OWNED_FILES 밖이므로 dept_3d_viewer 부서 소관.

## 타 부서 요청 사항
- **dept_3d_viewer**: popup_3d.py 내 SpectrumPanel에 `setFixedHeight(245)` 또는 figsize 1178x245 제약 적용 요청 (SPEC-003 관련)
