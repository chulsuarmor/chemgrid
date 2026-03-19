# [R2] Spectroscopy & Pharmacophore Comparison Report — 2026-03-18
# audit_theory: ChemGrid predict_spectra.py Deep-Dive Analysis

> Tolerance: IR +/-30 cm-1 | 1H NMR +/-0.5 ppm | 13C NMR +/-5 ppm | UV-Vis +/-15 nm

---

## 1. IR Spectroscopy Assessment

### 1.1 Benzene IR

| Peak # | App Wavenumber | App Assignment | Lit. Wavenumber | Lit. Assignment | Delta | Verdict |
|--------|---------------|----------------|-----------------|-----------------|-------|---------|
| 1 | 3070 cm-1 | Ar-H str. | 3062-3080 | Ar C-H stretch | 0 | PASS |
| 2 | 1600 cm-1 | C=C ring str. | 1600 | Ring C=C stretch | 0 | PASS |
| 3 | 1500 cm-1 | C=C ring str. | 1500 | Ring C=C stretch | 0 | PASS |
| 4 | 750 cm-1 | Ar-H oop | 671 (neat benzene) | C-H oop deformation | +79 | FAIL |
| 5 | 700 cm-1 | ring C-H oop | 671 | Ring oop | +29 | PASS |

**Analysis:** The IR_LOOKUP table in predict_spectra.py uses 750 cm-1 for "C-H_aromatic" Ar-H oop and 700 cm-1 for "ring_6" C-H oop. Neat benzene's strong absorption at ~671 cm-1 is not well represented. The 750 cm-1 value is more typical of a monosubstituted benzene pattern. For unsubstituted benzene, this is a systematic error.

**Missing peaks:** Benzene should also show absorptions near 1480 and 1036 cm-1 (in-plane C-H bending). These are absent from the app output.

### 1.2 Aspirin IR

| Peak # | App Wavenumber | App Assignment | Lit. Wavenumber | Lit. Assignment | Delta | Verdict |
|--------|---------------|----------------|-----------------|-----------------|-------|---------|
| 1 | 3070 cm-1 | Ar-H str. | 3080 | Ar C-H stretch | -10 | PASS |
| 2 | 2960 cm-1 | C-H str. (sp3) | 2999 | C-H stretch | -39 | FAIL |
| 3 | 2700 cm-1 | O-H str. (carboxylic) | 2500-3300 broad | Carboxylic O-H | in range | PASS |
| 4 | 1710 cm-1 | C=O str. | 1753 (ester) | Ester C=O | -43 | FAIL |
| 5 | 1710 cm-1 | C=O str. | 1689 (acid) | Acid C=O | +21 | PASS |
| 6 | 1600 cm-1 | C=C ring str. | 1605 | Aromatic C=C | -5 | PASS |
| 7 | 1500 cm-1 | C=C ring str. | 1518 | Aromatic C=C | -18 | PASS |

**Critical finding:** Aspirin has TWO C=O groups (ester at ~1753, acid at ~1689 cm-1). The app's SMARTS-based detection finds "O-H_carboxyl" which triggers a single C=O at 1710. It does NOT separately detect the ester C=O. The "C=O_ester" SMARTS pattern `[CX3](=O)[OX2][CX4]` fails to match aspirin because the ester oxygen connects to an aromatic carbon, not CX4.

**Root cause in code:** Line 129 of predict_spectra.py defines: `"C=O_ester": "[CX3](=O)[OX2][CX4]"` -- the `[CX4]` should be `[#6]` to match aromatic carbons too.

### 1.3 Ethanol IR

| Peak # | App Wavenumber | App Assignment | Lit. Wavenumber | Lit. Assignment | Delta | Verdict |
|--------|---------------|----------------|-----------------|-----------------|-------|---------|
| 1 | 3400 cm-1 | O-H str. (broad) | 3200-3500 | O-H stretch (H-bonded) | in range | PASS |
| 2 | 2960 cm-1 | C-H str. (sp3) | 2981 | C-H asym. stretch | -21 | PASS |
| 3 | 2870 cm-1 | C-H str. (sp3) | 2900 | C-H sym. stretch | -30 | PASS |
| 4 | 1460 cm-1 | C-H bend | 1460 | CH2/CH3 deformation | 0 | PASS |
| 5 | 1380 cm-1 | C-H sym. bend | 1380 | CH3 sym. deformation | 0 | PASS |
| 6 | 1080 cm-1 | C-O str. | 1050-1075 | C-O stretch (primary) | +5 to +30 | PASS |

**Assessment:** Ethanol IR is well-represented. All major diagnostic peaks are within tolerance.

---

## 2. NMR Spectroscopy Assessment

### 2.1 1H NMR

#### Benzene
| Environment | App (ppm) | Lit. (ppm) | Multiplicity App/Lit | Integration App/Lit | Delta | Verdict |
|------------|-----------|-----------|---------------------|--------------------|----|---------|
| Ar-H | 7.3 | 7.36 | s / s | 6 / 6 | -0.06 | PASS |

#### Aspirin
| Environment | App (ppm) | Lit. (ppm) | Multiplicity App/Lit | Integration App/Lit | Delta | Verdict |
|------------|-----------|-----------|---------------------|--------------------|----|---------|
| OCOCH3 | 2.3 | 2.36-2.43 | s / s | 3 / 3 | -0.06 to -0.13 | PASS |
| Ar-H (all) | 7.3 | 7.1-8.2 (4 peaks) | s / m (complex) | 4 / 4 | centroid OK | PASS* |
| COOH | 11.5 | 11.77-11.89 | s / s | 1 / 1 | -0.27 to -0.39 | PASS |

*Note: Ar-H reported as single peak rather than 4 distinct signals. Acceptable for educational/estimation use but would fail in analytical identification.

#### Ethanol
| Environment | App (ppm) | Lit. (ppm) | Multiplicity App/Lit | Integration App/Lit | Delta | Verdict |
|------------|-----------|-----------|---------------------|--------------------|----|---------|
| CH3 | 1.2 | 1.0-1.2 | s / t | 3 / 3 | 0 | PASS (shift), FAIL (mult.) |
| O-H | 2.6 | ~2.0 (variable) | s / br s | 1 / 1 | +0.6 | FAIL |
| OCH2 | 3.5 | 3.6-3.7 | s / q | 2 / 2 | -0.1 to -0.2 | PASS (shift), FAIL (mult.) |

**Multiplicity Bug Analysis:** The `_get_h_neighbors` function (line 271) counts H on neighboring C atoms, but the `_multiplicity_str` result is not propagated correctly. For ethanol CH3 (parent C has 2 adjacent H on CH2), it should output "t" (triplet). The code at line 352 calls `_get_h_neighbors(parent, mol)` but this function only counts H on C neighbors, skipping O-H coupling. The fundamental issue is that all H atoms bonded to the same parent are grouped together, and the multiplicity of the GROUP is computed from neighboring C-H count -- but the grouping key at line 356 may cause the multiplicity to be computed from the first H encountered rather than the parent carbon's full environment.

### 2.2 13C NMR

#### Benzene
| Carbon | App (ppm) | Lit. (ppm) | Type App/Lit | Delta | Verdict |
|--------|-----------|-----------|-------------|-------|---------|
| Ar-C | 128.0 | 128.4 | CH / CH | -0.4 | PASS |

#### Aspirin
| Carbon | App (ppm) | Lit. (ppm) | Type App/Lit | Delta | Verdict |
|--------|-----------|-----------|-------------|-------|---------|
| Acetyl CH3 | 28.0 | 20-21 | CH3 / CH3 | +7 to +8 | FAIL |
| Ar-C | 130.0 | 122-152 (6 peaks) | C / various | in range | PASS* |
| C=O | 205.5 | 169-170 | C / C | +35.5 | FAIL |

*Note: App outputs only 1 aromatic carbon peak. Literature shows 6 distinct peaks (122, 125, 126, 132, 135, 152 ppm). The deduplication at +/-3 ppm (line 484) collapses most of these.

**Root cause of C=O error:** In `predict_c13_nmr()`, the code at line 410-424 checks for ester C=O by looking for O atoms with no H that have a C neighbor. For aspirin's ester carbonyl, the oxygen connects to an aromatic C, and the code correctly identifies this path. However, the carboxylic acid C=O has an -OH neighbor, which triggers line 425-428 (shift = 175 ppm, "carboxylic"). The ester C=O at line 418-420 gives 170 ppm. But due to the deduplication at +/-3 ppm, only one survives. The surviving peak appears to be the "ketone" classification at 205 ppm, suggesting the SMARTS matching in the sp2 carbonyl detection is not correctly distinguishing between aspirin's two C=O groups.

#### Ethanol
| Carbon | App (ppm) | Lit. (ppm) | Type App/Lit | Delta | Verdict |
|--------|-----------|-----------|-------------|-------|---------|
| CH3 | 15.0 | 18.2 | CH3 / CH3 | -3.2 | PASS |
| CH2-OH | 58.5 | 57.8-60 | CH2 / CH2 | in range | PASS |

---

## 3. UV-Vis Spectroscopy Assessment

### Benzene
| Band | App (nm) | App epsilon | Lit. (nm) | Lit. epsilon | Delta | Verdict |
|------|---------|------------|----------|-------------|-------|---------|
| K-band (pi->pi*) | 204 | 7000 | 204 | 7900 | 0 nm, -11% eps | PASS |
| B-band (forbidden) | 254 | 200 | 254-256 | 200 | 0 nm | PASS |

### Aspirin
| Band | App (nm) | App epsilon | Lit. (nm) | Lit. epsilon | Delta | Verdict |
|------|---------|------------|----------|-------------|-------|---------|
| C=O pi->pi* | 200 | 10000 | ~227 | -- | -27 | FAIL |
| K-band (aromatic) | 211 | 7000 | ~230 (est.) | -- | -19 | FAIL |
| B-band (forbidden) | 257 | 200 | 276 | -- | -19 | FAIL |
| n->pi* (C=O) | 270 | 15 | ~276 | ~1000 | -6 nm, low eps | PASS (nm) |

**Analysis:** The auxochrome increment calculation in predict_uvvis() applies a maximum of +7 nm for -OR on benzene (line 715). Aspirin has both -OCOCH3 (ester) and -COOH on the ring. The combined auxochrome effect should be larger. Literature shows aspirin absorbs at ~276 nm (comparable to salicylic acid at ~303 nm minus the acetyl protection). The app's +7 nm auxochrome shift is insufficient.

### Ethanol
| Band | App (nm) | App epsilon | Lit. (nm) | Lit. epsilon | Delta | Verdict |
|------|---------|------------|----------|-------------|-------|---------|
| sigma->sigma* | 150 | 50000 | ~150 (vacuum UV) | -- | 0 | PASS |

**Note:** Correct behavior -- ethanol has no UV chromophore in the standard 200-800 nm range. The app correctly falls back to sigma->sigma* only.

---

## 4. Code-Level Bug Summary

| # | File:Line | Issue | Severity | Affected Molecules |
|---|-----------|-------|----------|--------------------|
| 1 | predict_spectra.py:129 | Ester SMARTS `[CX4]` doesn't match aromatic C | Medium | Aspirin (IR) |
| 2 | predict_spectra.py:410-424 | C=O type classification fails for mixed ester/acid molecules | High | Aspirin (13C NMR) |
| 3 | predict_spectra.py:484 | 3 ppm deduplication collapses distinct aromatic carbons | Medium | Aspirin (13C NMR) |
| 4 | predict_spectra.py:352-363 | Multiplicity not correctly assigned for ethanol CH3/CH2 | Medium | Ethanol (1H NMR) |
| 5 | predict_spectra.py:715 | Auxochrome shift for -OR too low (+7 nm) | Medium | Aspirin (UV-Vis) |
| 6 | predict_spectra.py:88 | Aromatic oop at 750 cm-1 generic; benzene is 671 | Low | Benzene (IR) |

---

## 5. Recommendations

1. **Fix ester SMARTS** to `[CX3](=O)[OX2][#6]` to capture aromatic esters
2. **Separate ester vs acid C=O in 13C NMR** with distinct shift ranges (ester ~170, acid ~175)
3. **Reduce 13C deduplication window** from +/-3 to +/-1 ppm for aromatic carbons
4. **Fix multiplicity propagation** -- ensure n+1 rule is applied per carbon group
5. **Increase auxochrome increments** for multi-substituted rings (additive model)
6. **Add substitution-pattern-dependent oop bending** frequencies (mono/di/tri)
