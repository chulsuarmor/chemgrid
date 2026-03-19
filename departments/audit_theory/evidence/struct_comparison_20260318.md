# [R1] Structural & Spectroscopic Comparison Report — 2026-03-18
# audit_theory: ChemGrid predict_spectra.py vs Literature Values

> Tolerance criteria: IR +/-30 cm-1 | 1H NMR +/-0.5 ppm | 13C NMR +/-5 ppm | UV-Vis +/-15 nm

---

## Molecule: Benzene (C6H6, SMILES: c1ccccc1)

### IR Spectrum

| Item | App Value (cm-1) | Literature Value (cm-1) | Source | Error | Verdict |
|------|-----------------|------------------------|--------|-------|---------|
| Ar-H str. | 3070 | 3062-3080 | NIST WebBook / Silverstein | 0 (within range) | PASS |
| C=C ring str. | 1600 | 1600 | NIST / Spectroscopy Online | 0 | PASS |
| C=C ring str. | 1500 | 1500 | NIST / Spectroscopy Online | 0 | PASS |
| Ar-H oop | 750 | 671 (mono-substituted; neat benzene ~673) | NIST WebBook | +77 | FAIL |
| ring C-H oop | 700 | 671 | NIST WebBook | +29 | PASS |

**Note:** Benzene literature shows strong oop bend near 671 cm-1 (liquid film). App predicts 750 cm-1 for Ar-H oop (generic monosubstituted pattern). The ring C-H oop at 700 is within tolerance. The 750 cm-1 peak is outside tolerance for neat benzene.

### 1H NMR

| Item | App Value (ppm) | Literature Value (ppm) | Source | Error | Verdict |
|------|----------------|----------------------|--------|-------|---------|
| Ar-H (6H, singlet) | 7.3 | 7.36 (CDCl3) | Silverstein / docbrown.info | -0.06 | PASS |

### 13C NMR

| Item | App Value (ppm) | Literature Value (ppm) | Source | Error | Verdict |
|------|----------------|----------------------|--------|-------|---------|
| Ar-C (CH) | 128.0 | 128.4 | Silverstein / docbrown.info | -0.4 | PASS |

### UV-Vis

| Item | App Value (nm) | Literature Value (nm) | Source | Error | Verdict |
|------|---------------|---------------------|--------|-------|---------|
| K-band (pi->pi*) | 204 | 204 | NIST / Chegg reference | 0 | PASS |
| B-band (forbidden) | 254 | 254-256 | NIST WebBook | 0 | PASS |

---

## Molecule: Aspirin / Acetylsalicylic Acid (C9H8O4, SMILES: CC(=O)Oc1ccccc1C(=O)O)

### IR Spectrum

| Item | App Value (cm-1) | Literature Value (cm-1) | Source | Error | Verdict |
|------|-----------------|------------------------|--------|-------|---------|
| O-H str. (carboxylic, broad) | 2700 | 2500-3300 (broad) | NIST / Sheffield | 0 (within range) | PASS |
| C=O str. | 1710 | 1753 (ester C=O) / 1689 (acid C=O) | NIST / Brainly / ChemSkills | -43 to +21 | MIXED |
| C=C ring str. | 1600 | 1605 | NIST / RSC | -5 | PASS |
| C=C ring str. | 1500 | 1518 | NIST | -18 | PASS |
| Ar-H str. | 3070 | 3080 | NIST | -10 | PASS |
| C-H str. (sp3) | 2960 | 2999 | NIST | -39 | FAIL |

**Note on C=O:** Aspirin has TWO distinct C=O stretches: ester at ~1753 and carboxylic acid at ~1689 cm-1. The app outputs a single C=O peak at 1710 cm-1, which is an average but does not resolve the two distinct carbonyls. This is a significant limitation.

### 1H NMR

| Item | App Value (ppm) | Literature Value (ppm) | Source | Error | Verdict |
|------|----------------|----------------------|--------|-------|---------|
| CH3 (3H, s) | 2.3 | 2.36-2.43 | ThermoFisher / DrugBank | -0.06 to -0.13 | PASS |
| Ar-H (4H) | 7.3 | 7.1-8.2 (multiplet, 4 peaks) | ThermoFisher / CliffsNotes | within range | PASS |
| O-H carboxylic (1H, s) | 11.5 | 11.77-11.89 | ThermoFisher / CliffsNotes | -0.27 to -0.39 | PASS |

**Note:** The app treats all 4 aromatic protons as equivalent at 7.3 ppm. In reality, the ortho-substituted benzene ring gives 4 distinct signals at ~7.1, 7.4, 7.7, 8.2 ppm. The centroid is reasonable but resolution is lost.

### 13C NMR

| Item | App Value (ppm) | Literature Value (ppm) | Source | Error | Verdict |
|------|----------------|----------------------|--------|-------|---------|
| CH3 (alpha-C=O) | 28.0 | 20-21 | RSC / ThermoFisher | +7.0 | FAIL |
| Ar-C | 130.0 | 122-152 (multiple peaks) | RSC Supplement / Bartleby | within range | PASS |
| C=O | 205.5 | 169-170 (ester/acid C=O) | RSC Supplement | +35.5 | FAIL |

**Critical Issue:** The app classifies aspirin's C=O as "ketone" (205 ppm) instead of ester/acid carbonyl (~169-170 ppm). The acetyl methyl at 28 ppm vs literature 20-21 ppm is also outside the +/-5 ppm tolerance.

### UV-Vis

| Item | App Value (nm) | Literature Value (nm) | Source | Error | Verdict |
|------|---------------|---------------------|--------|-------|---------|
| K-band (aromatic) | 211 | ~227 (ethanol solvent) | ResearchGate / Springer | -16 | FAIL |
| B-band (forbidden) | 257 | 276 (ethanol) | ResearchGate / SIELC | -19 | FAIL |
| n->pi* (C=O) | 270 | ~276 | Literature consensus | -6 | PASS |

**Note:** The auxochrome shift for the -OH and -OCOCH3 groups on the benzene ring is underestimated in the app, resulting in blue-shifted predictions.

---

## Molecule: Ethanol (C2H6O, SMILES: CCO)

### IR Spectrum

| Item | App Value (cm-1) | Literature Value (cm-1) | Source | Error | Verdict |
|------|-----------------|------------------------|--------|-------|---------|
| O-H str. (broad) | 3400 | 3200-3500 | NIST / docbrown.info | 0 (within range) | PASS |
| C-H str. (sp3) | 2960 | 2981 (primary) | NIST / docbrown.info | -21 | PASS |
| C-H str. (sp3) | 2870 | 2900 (symmetric) | NIST | -30 | PASS |
| C-H bend | 1460 | 1460 | Silverstein | 0 | PASS |
| C-H sym. bend | 1380 | 1380 | Silverstein | 0 | PASS |
| C-O str. | 1080 | 1050-1075 | NIST / docbrown.info | +5 to +30 | PASS |

### 1H NMR

| Item | App Value (ppm) | Literature Value (ppm) | Source | Error | Verdict |
|------|----------------|----------------------|--------|-------|---------|
| CH3 (3H) | 1.2 | 1.0-1.2 (triplet) | docbrown.info / Sigma-Aldrich | 0 (within range) | PASS |
| O-H (1H) | 2.6 | ~2.0 (broad, variable) | Wolfram / ChemicalBook | +0.6 | FAIL |
| OCH2 (2H) | 3.5 | 3.6-3.7 (quartet) | docbrown.info / Sigma-Aldrich | -0.1 to -0.2 | PASS |

**Note on multiplicity:** App reports all ethanol peaks as singlets. Literature: CH3 = triplet, CH2 = quartet, OH = singlet (exchangeable). The app's _get_h_neighbors function does not propagate coupling from O-H exchange correctly, but the multiplicity for CH3 and CH2 should be t and q respectively.

### 13C NMR

| Item | App Value (ppm) | Literature Value (ppm) | Source | Error | Verdict |
|------|----------------|----------------------|--------|-------|---------|
| CH3 | 15.0 | 18.2 | docbrown.info / Silverstein | -3.2 | PASS |
| CH2-OH | 58.5 | 57.8-60 | docbrown.info / Silverstein | +0.5 | PASS |

### UV-Vis

| Item | App Value (nm) | Literature Value (nm) | Source | Error | Verdict |
|------|---------------|---------------------|--------|-------|---------|
| sigma->sigma* | 150 | ~150 (vacuum UV, no chromophore) | Silverstein Ch.7 | 0 | PASS |

**Note:** Ethanol has no significant chromophore. The app correctly identifies only sigma->sigma* at 150 nm. This is correct behavior: ethanol is transparent in the standard UV-Vis range (200-800 nm).

---

## Summary of Structural/Spectroscopic Findings

### PASS Rates by Molecule:
- **Benzene:** 9/10 items PASS (1 FAIL: Ar-H oop frequency)
- **Aspirin:** 9/17 items PASS (5 FAIL, 1 MIXED, 2 Notes)
- **Ethanol:** 10/11 items PASS (1 FAIL: O-H NMR shift)

### Critical Issues Identified:
1. **Aspirin C=O misclassification:** ester/acid carbonyl classified as ketone C=O (205 ppm vs 169-170 ppm)
2. **Aspirin C=O IR:** single peak at 1710 instead of two resolved peaks (1753 ester, 1689 acid)
3. **Aspirin acetyl CH3 13C:** 28 ppm vs literature 20-21 ppm
4. **Aspirin UV-Vis auxochrome underestimation:** K-band and B-band both blue-shifted
5. **Multiplicity not computed for ethanol:** all peaks reported as singlets
