# 전문감사-구조화학 기술 노트
## 마지막 업데이트: 2026-03-18 | Cascade #3 Wave 1 감사 완료

### 감사 기준 참조
- Gasteiger 60% + Custom 40% 블렌딩 규칙
- carbon main='' (빈 문자열) 저장 규칙
- 공명 등가 원자 전하 균등화 규칙
- CRC Handbook of Chemistry and Physics, 97th Edition (결합 길이 참조)
- RDKit Crippen.MolLogP, Descriptors.TPSA, Lipinski.NumRotatableBonds (API 참조)

---

## Cascade #3 Wave 1 감사 보고서

### 감사 대상
1. dept_chem_engine (chem_data.py, analyzer.py)
2. dept_rendering (renderer.py)
3. dept_ui_canvas (main_window.py, canvas.py)

---

### 항목 1: BOND_LENGTHS 테이블 (dept_chem_engine) — CONDITIONAL PASS

**검증 방법:** chem_data.py lines 66-146의 BOND_LENGTHS 딕셔너리를 CRC 97th Ed. 표준값과 대조.

**정상 확인 (5개 이상 핵심 결합):**
| 결합 | 코드 값 (A) | CRC 참조값 (A) | 판정 |
|------|------------|----------------|------|
| P-S single (line 113) | 2.12 | 2.12 (H3P=S) | PASS |
| Si-H (line 120) | 1.48 | 1.48 (SiH4) | PASS |
| Si-Si (line 122) | 2.33 | 2.34 (Si2H6) | PASS (within 0.01) |
| B-F (line 130) | 1.30 | 1.30 (BF3) | PASS |
| B-H (line 131) | 1.19 | 1.19 (BH3/B2H6) | PASS |
| B-Cl (line 132) | 1.75 | 1.75 (BCl3) | PASS |
| S-F (line 136) | 1.56 | 1.56 (SF6) | PASS |
| S-Cl (line 137) | 2.07 | 2.07 (SCl2) | PASS |
| Se-C (line 143) | 1.96 | 1.95-1.97 | PASS |
| Se-H (line 144) | 1.47 | 1.47 (H2Se) | PASS |
| Se-Se (line 145) | 2.32 | 2.32 (Se2) | PASS |
| P-F (line 115) | 1.54 | 1.54 (PF3) | PASS |
| P-Cl (line 116) | 2.04 | 2.04 (PCl3) | PASS |

**주의 사항 (2건):**

1. **P-H (line 112): 코드=1.44, CRC PH3=1.42**
   - 편차: +0.02. PH3의 정밀 측정값은 1.4200. 코드값이 약간 높음.
   - 심각도: 낮음 (0.02 이내). 교과서 범위 내이지만 정밀화 권장.
   - 권장: 1.42로 수정 권장.

2. **B-N single (line 129): 코드=1.42, 일반적 B-N dative bond=1.58**
   - 코드값 1.42는 borazine (B3N3H6)의 방향족 B-N 결합에 해당.
   - CRC의 B-N 단일(dative) 결합 (예: H3B-NH3)은 1.58.
   - 현재 코드에 B-N aromatic (order=1.5) 엔트리가 없어, single bond 값이 aromatic 환경에서도 사용됨.
   - 심각도: 중간. Borazine 계열 분자에서는 적절하나, 일반 B-N 단일결합(아민보란 등)에는 부적절.
   - 권장: ('B','N',1): 1.58 (dative single), ('B','N',1.5): 1.42 (borazine aromatic) 분리 등록.

3. **context_note.md와 코드 불일치 (경미):**
   - context_note에 P-H=1.420으로 기재되었으나 코드는 1.44
   - context_note에 B-N=1.580으로 기재되었으나 코드는 1.42
   - context_note에 S-N(1)=1.730으로 기재되었으나 코드는 1.68
   - 문서-코드 정합성 재확인 필요.

**판정: CONDITIONAL PASS** — CRC 대조 대부분 정확하나 B-N 단일결합값과 문서-코드 불일치 수정 권장.

---

### 항목 2: LogP/TPSA/RotBonds RDKit 래퍼 (dept_chem_engine) — PASS

**검증 위치:** analyzer.py lines 639-708

**확인 사항:**
- calculate_logp (line 657): `Crippen.MolLogP(mol)` 정확히 사용. PASS.
- calculate_tpsa (line 681): `Descriptors.TPSA(mol)` 정확히 사용. PASS.
- calculate_rotatable_bonds (line 705): `Lipinski.NumRotatableBonds(mol)` 정확히 사용. PASS.
- Graceful fallback: 3개 함수 모두 `if not RDKIT_AVAILABLE: return 0/0.0` + `try/except` 2단계 방어. PASS.
- `Chem.MolFromSmiles(smiles)` None 체크 포함. PASS.

**판정: PASS** — RDKit API 사용이 정확하고 fallback 패턴이 올바름.

---

### 항목 3: Gasteiger 60/40 블렌딩 (dept_chem_engine) — PASS

**검증 위치:** analyzer.py line 171

**코드:**
```
global_charges[nk] = 0.6 * g_scaled + 0.4 * global_charges[nk]
```

**확인 사항:**
- 60% Gasteiger + 40% custom physics 비율 정확. PASS.
- g_scaled는 커스텀 전하 범위에 맞춰 스케일링됨 (line 167-169). PASS.
- NaN/Inf 필터: line 147 `math.isnan(gc) or math.isinf(gc)` 체크. PASS.
- rdkit_idx 기반 매핑 (line 152-156): 정확한 원자 대응. PASS.

**판정: PASS** — 블렌딩 비율 및 구현 정확.

---

### 항목 4: draw_partial_charges (dept_rendering) — PASS

**검증 위치:** renderer.py lines 1486-1570

**확인 사항:**

1. **CHARGE_THRESHOLD = 0.10 (line 1515):** 화학적으로 합리적. Gasteiger 전하에서 |q| < 0.10인 원자는 사실상 비편극(nonpolar)이므로 표시 생략이 적절. PASS.

2. **색상 체계:**
   - delta- (음전하, 전자 풍부) = red QColor(200,30,30,180) (line 1547). PASS.
   - delta+ (양전하, 전자 부족) = blue QColor(30,80,200,180) (line 1550). PASS.
   - 이는 ESP 전자밀도 교과서 색상 관례(RED=electron-rich, BLUE=electron-poor)와 일치.

3. **sp3 포화탄화수소 필터 (lines 1529-1540):**
   - is_hetero: 헤테로원자 여부 확인. PASS.
   - has_formal_charge: 형식전하 여부 확인. PASS.
   - has_mult_bond: 다중결합(order >= 1.5) 여부 확인. PASS.
   - 3가지 조건 모두 False일 때만 생략 → 알칸 C-H의 미세 전하 노이즈 방지. 화학적으로 타당.

4. **QPainter 안전:** painter.save()/restore() + try/finally 패턴. PASS.

**판정: PASS** — 전하 임계값, 색상 관례, 필터 로직 모두 화학적으로 정확.

---

### 항목 5: Lewis 론쌍 (dept_rendering/chem_engine 경계) — PASS

**검증 위치:** analyzer.py line 448

**수식:** `lp = max(0, (outer_elecs - bonds_val - formal_charge) // 2)`

**검증 (RDKit GetNOuterElecs + GetTotalValence 기반):**

| 분자 | 원자 | outer_elecs | bonds_val | formal_charge | lp 계산 | 정답 |
|------|------|-------------|-----------|---------------|---------|------|
| H2O | O | 6 | 2 | 0 | (6-2-0)//2 = 2 | 2쌍 PASS |
| NH3 | N | 5 | 3 | 0 | (5-3-0)//2 = 1 | 1쌍 PASS |
| HF | F | 7 | 1 | 0 | (7-1-0)//2 = 3 | 3쌍 PASS |
| CH4 | C | 4 | 4 | 0 | (4-4-0)//2 = 0 | 0쌍 PASS |
| NH4+ | N | 5 | 4 | +1 | (5-4-1)//2 = 0 | 0쌍 PASS |
| CO | C | 4 | 3 | -1 | (4-3-(-1))//2 = 1 | 1쌍 PASS |

**판정: PASS** — Lewis 론쌍 계산 수식이 정확하며, formal_charge 보정도 포함됨.

---

### 항목 6: ESP Theory 가드 (dept_ui_canvas) — PASS

**검증 위치:** canvas.py

**ESP 렌더링 호출 지점 3곳 모두 `view_state == "Theory"` 가드 확인:**
- Line 1212: `self.view_state == "Theory"` PASS
- Line 1269: `self.view_state == "Theory"` PASS
- Line 1332: `self.view_state == "Theory"` PASS

**context_note.md 크로스-부서 협업 기록:** P-RENDER가 ESP 가드 누락 발견 → dept_ui_canvas에 보고 → P-UI가 수정. 절차 정상.

**판정: PASS** — Drawing/Lewis 모드에서 ESP 구름이 표시되지 않도록 3중 가드 완비.

---

### 항목 7: Carbon 빈 문자열 저장 규칙 — PASS

**검증 위치:** analyzer.py line 34

**코드:** `full_atoms[pt_key] = {"main": "", "attach": {}}`

**추가 검증:**
- analyzer.py line 302-303: `e1 = norm_atoms.get(pk1, {}).get("main") or "C"` — 빈 문자열을 "C"로 안전하게 변환.
- renderer.py line 1527: `at_main = atom_data.get("main", "") or "C"` — 동일 패턴.
- chem_data.py: ELEMENT_DATA에 "C" 키 존재, BOND_LENGTHS에 ('C','C',1) 등 정상.

**판정: PASS** — `main=""` 규칙이 코드 전반에서 일관되게 준수되며, `or "C"` fallback으로 안전하게 처리됨.

---

### 항목 8: 듀얼 코드베이스 동기화 — PASS

**검증 방법:** `diff src/app/FILE _source/FILE` 실행

| 파일 | diff 결과 |
|------|----------|
| chem_data.py | 동일 (exit 0) |
| analyzer.py | 동일 (exit 0) |
| renderer.py | 동일 (exit 0) |
| main_window.py | 동일 (exit 0) |

**판정: PASS** — 4개 수정 파일 모두 src/app/와 _source/ 간 완벽 동기화 확인.

---

### 항목 9 (추가): UC-003 pan_offset 동적 스케일 (dept_ui_canvas) — PASS

**검증 위치:** main_window.py line 1009

**코드:** `scale = self.cv.grid_size / 1.5`

**화학적 근거:** RDKit 2D 좌표는 Angstrom 단위이며 C-C 단일결합 = 1.5A. grid_size를 1.5로 나누면 RDKit 단위 -> 픽셀 변환이 됨. grid_size=40일 때 scale=26.67, 이전 하드코딩값 26.7과 일치. PASS.

---

### 항목 10 (추가): UC-004 analysis_results guaranteed fallback (dept_ui_canvas) — PASS

**검증 위치:** main_window.py lines 1124-1135

**구현:**
- 3단계 방어선: analyze(atoms, bonds, smiles) -> analyze(atoms, bonds) -> minimal dict fallback
- minimal dict에 'smiles' 키 포함 (line 1128)
- line 1134: `if 'smiles' not in self.cv.analysis_results:` 추가 보장

**판정: PASS** — None 크래시 방지 로직이 완비됨.

---

## 최종 종합 판정

| 항목 | 부서 | 판정 |
|------|------|------|
| BOND_LENGTHS CRC 대조 | chem_engine | **CONDITIONAL PASS** |
| LogP/TPSA/RotBonds | chem_engine | PASS |
| Gasteiger 60/40 | chem_engine | PASS |
| draw_partial_charges | rendering | PASS |
| Lewis 론쌍 | rendering/chem_engine | PASS |
| ESP Theory 가드 | ui_canvas | PASS |
| Carbon '' 규칙 | 전체 | PASS |
| 듀얼 코드베이스 동기 | 전체 | PASS |
| UC-003 동적 스케일 | ui_canvas | PASS |
| UC-004 fallback | ui_canvas | PASS |

### 수정 권장 사항 (CONDITIONAL PASS 해소 조건)
1. **chem_data.py line 112:** P-H 1.44 -> 1.42 수정 (CRC PH3 정밀값)
2. **chem_data.py line 129:** B-N single 1.42 -> 1.58 수정, 별도로 ('B','N',1.5): 1.44 aromatic 엔트리 추가
3. **dept_chem_engine context_note.md:** 코드와 불일치하는 결합 길이값(P-H, B-N, S-N) 수정

위 3건 수정 시 전체 PASS 판정으로 승격 가능.

---

### 감사자 서명
- 감사 수행: 전문감사팀 구조화학 (audit_professional_structural)
- 감사 일시: 2026-03-18
- Cascade: #3 Wave 1
