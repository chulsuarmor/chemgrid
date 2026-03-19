# 팝업 기능 감사관 감사 기술 노트
> 최종 업데이트: 2026-03-17 | Auditor: Claude Opus 4.6

## 감사 이력

### 2026-03-17: Full 6-Popup Audit (A-F)
- **결과 요약:** 1 PASS, 4 WARN, 1 FAIL
- **FAIL 항목:** E (Spectrum Prediction) — lookup table approach falls far below DFT-level accuracy
- **PASS 항목:** F (Docking) — proper AutoDock Vina integration

### Priority Fix Order (CT에 보고)
1. **E (Spectrum) [FAIL]**: predict_spectra.py의 IR 예측을 vibration_engine.py 연동으로 교체. NMR increment table 추가. UV-Vis Woodward-Fieser 규칙 구현.
2. **D (Orbital) [WARN]**: 기본 HOMO/LUMO 값(-5.5/-2.3 eV) 제거 또는 경고 라벨 필수. 폴백 시각화에 "approximate" 경고 표시.
3. **B (Reaction) [WARN]**: RDKit ReactionFromSmarts()로 product_smiles 생성 구현.
4. **A (Vibration) [WARN]**: IR selection rule 체크 추가. 내부 엔진 결과에 "approximate" 라벨.
5. **C (Synthesis) [WARN]**: 기질 적응형 조건 선택 및 온도 명시.

## 이론값 참조 캐시

### Harmonic Oscillator
- ν = (1/2π)√(k/μ) — standard diatomic formula
- Force constants: C-H ~500 N/m, C=O ~1200 N/m, C-C ~500 N/m
- vibration_engine.py 구현 확인: 정확

### IR Selection Rules
- IR active: dμ/dQ ≠ 0 (dipole moment change required)
- Raman active: dα/dQ ≠ 0 (polarizability change required)
- Mutual exclusion rule for centrosymmetric molecules
- vibration_engine.py: 미구현 (FAIL point)

### Curved Arrow Notation
- Full arrow: 2-electron heterolytic movement (Clayden convention)
- Fishhook (half arrow): 1-electron radical movement
- Source: lone pair, pi bond, sigma bond → Sink: electrophilic center
- arrow_generator.py: 정확히 구현

### NMR Chemical Shifts (Pretsch Standard Increments)
- Aliphatic CH3: 0.9 ppm base + substituent corrections
- Alpha to C=O: +1.0-1.2 ppm increment
- Alpha to halide: +1.5-2.5 ppm increment
- predict_spectra.py: increment 미적용 (FAIL point)

### UV-Vis Woodward-Fieser Rules
- Homodiene base: 217 nm
- Each alkyl substituent: +5 nm
- Ring residue: +5 nm
- Exocyclic double bond: +5 nm
- predict_spectra.py: 미구현, 단순 규칙만 사용 (FAIL point)

### AutoDock Vina Workflow
- PDBQT format with Gasteiger charges + AD4 atom types
- Meeko: proper torsion tree generation
- Grid box: centered on binding site, typically 20-30 Å per side
- docking_interface.py: 정확히 구현 (PASS)

## 감사 방법론
- 전체 소스 코드 7개 엔진 파일 + 4개 팝업 파일 정독
- 웹 검색 8회 수행 (6회 성공, 2회 불가 — 학습 데이터로 보완)
- PhD-level 이론 기준 대조 검증
