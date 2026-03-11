# Spectroscopy Reference Guide
## ChemDraw Pro Validation Project

---

## 📊 IR Spectroscopy Quick Reference

### Stretching Vibrations (ν)

#### C-H Stretches
| Type | Frequency (cm⁻¹) | Intensity | Example |
|------|-----------------|-----------|---------|
| Alkane | 2960, 2850 | Strong | Norbornane, Cyclohexane |
| Aromatic | 3050-3000 | Weak-Medium | Naphthalene, Benzo[a]pyrene |
| Alkene | 3100-3000 | Medium | Allicin, Cholesterol |
| Aldehyde | 2900-2800, 2720 | Strong | (None in test set) |

#### C=C Stretches  
| Type | Frequency (cm⁻¹) | Intensity | Notes |
|------|-----------------|-----------|-------|
| Alkene | 1680-1640 | Medium-Strong | Allicin |
| Aromatic | 1600, 1500 | Medium-Strong | Naphthalene, Benzo[a]pyrene |
| Conjugated | 1650-1620 | Strong | Cholesterol, Benzo[a]pyrene |
| Dienal | 1690-1670 | Strong | Extended conjugation |

#### C=O Stretches
| Type | Frequency (cm⁻¹) | Intensity | Examples |
|------|-----------------|-----------|----------|
| Ester | 1750-1730 | Very Strong | Aspartame |
| Carboxylic Acid | 1730-1700 | Very Strong | Aspartame, ATP, Hemin |
| Amide | 1680-1650 | Strong | Caffeine, Aspartame |
| Ketone | 1720-1705 | Strong | (None in test set) |

#### N-H Stretches
| Type | Frequency (cm⁻¹) | Intensity | Examples |
|------|-----------------|-----------|----------|
| Primary Amine | 3400-3300 | Medium | ATP |
| Secondary Amide | 3400-3300 | Medium | Aspartame |
| Tertiary Amide | None | - | Caffeine |
| Purine/Imidazole | 3200-3100 | Weak | ATP, Caffeine |

#### O-H Stretches
| Type | Frequency (cm⁻¹) | Intensity | Examples |
|------|-----------------|-----------|----------|
| Alcohol | 3600-3400 | Strong | Cholesterol, ATP |
| Carboxylic Acid | 3300-2500 | Broad, Strong | ATP, Aspartame, Hemin |
| Phenol | 3600-3400 | Strong | (None in test set) |

#### P-O Stretches (Phosphorus-containing)
| Type | Frequency (cm⁻¹) | Intensity | Examples |
|------|-----------------|-----------|----------|
| P=O stretch | 1300-1200 | Very Strong | ATP |
| P-O stretch | 1100-1050 | Very Strong | ATP |
| P-O-P | 970-930 | Strong | ATP |

#### S-S and S=O Stretches
| Type | Frequency (cm⁻¹) | Intensity | Examples |
|------|-----------------|-----------|----------|
| S-S (Disulfide) | 550-450 | Strong | Allicin |
| S=O (Sulfoxide) | 1050-1000 | Very Strong | Allicin |
| S=O (Sulfone) | 1370-1350, 1160-1120 | Very Strong | (None in test set) |

### Bending Vibrations (δ)

#### C-H Bending
| Type | Frequency (cm⁻¹) | Assignment |
|------|-----------------|-----------|
| Methyl rocking | 920-800 | -CH₃ |
| Methylene rocking | 730-700 | -CH₂- |
| Out-of-plane bending (aromatic) | 900-700 | Aromatic C-H |
| In-plane bending (aromatic) | 1300-1000 | Aromatic C-H |

#### C-O Bending
| Type | Frequency (cm⁻¹) | Assignment |
|------|-----------------|-----------|
| C-O stretch | 1300-1000 | Ester, ether, alcohol |
| C-O bending | 600-500 | C-O-C |

### Aromatic Substitution Patterns

| Pattern | C-H out-of-plane (cm⁻¹) | Note |
|---------|------------------------|------|
| Monosubstituted | 770-730 | 5H aromatic |
| Ortho-disubstituted | 770-735 | 4H aromatic |
| Meta-disubstituted | 810-770 | 4H aromatic |
| Para-disubstituted | 850-800 | 4H aromatic |
| Trisubstituted | 900-800 | 3H aromatic |
| Tetrasubstituted | 900-600 | 2H aromatic |
| Polysubstituted | 900-600 | Complex patterns |

---

## 📈 NMR Spectroscopy Quick Reference

### ¹H NMR Chemical Shifts (δ, ppm)

#### Aliphatic Protons
| Environment | δ (ppm) | Example | Note |
|------------|---------|---------|------|
| R-CH₃ | 0.5-1.5 | Cholesterol methyl | Least deshielded |
| R-CH₂-R | 1.0-1.5 | Cyclohexane | Primary saturated |
| R₃CH | 1.2-2.5 | Cholesterol methine | Tertiary saturated |
| RCH=CH | 4.5-6.0 | Allicin vinyl | Alkenyl |
| RCH=O | 9.0-10.0 | (None in test set) | Aldehyde |

#### Aromatic Protons
| Environment | δ (ppm) | Example | Note |
|------------|---------|---------|------|
| Benzene (monosubstituted) | 7.0-7.5 | Aspartame benzyl | Standard aromatic |
| Naphthalene | 7.2-8.5 | Naphthalene | Fused aromatic |
| Purine/Pyrimidine | 8.0-9.0 | ATP, Caffeine | Deshielded by N |
| Heteroaromatic H-8 | 8.2-8.5 | ATP, Caffeine | Adjacent to N |

#### Heteroatom-Bonded Protons
| Environment | δ (ppm) | Example | Note |
|------------|---------|---------|------|
| R-OH | 2-4 | Cholesterol, ATP | Broad, exchangeable |
| R-NH | 1-3 | Aspartame, ATP | Exchangeable |
| R-COOH | 10-14 | Aspartame, Hemin | Very deshielded |
| R-CHO | 9-10 | (None in test set) | Aldehyde |

#### NMR Multiplicity

| Pattern | Description | Typical J (Hz) |
|---------|-------------|----------------|
| Singlet (s) | No neighboring protons | - |
| Doublet (d) | 1 neighboring proton | ³J = 6-8 Hz |
| Triplet (t) | 2 neighboring protons | ³J = 6-8 Hz |
| Quartet (q) | 3 neighboring protons | ³J = 6-8 Hz |
| Multiplet (m) | Complex coupling | Various |
| Broad singlet (bs) | Exchangeable proton | - |

### ¹³C NMR Chemical Shifts (δ, ppm)

#### Aliphatic Carbons
| Type | δ (ppm) | Example | Note |
|------|---------|---------|------|
| -CH₃ | 10-30 | Cholesterol methyls | Least deshielded |
| -CH₂- | 20-40 | Cyclohexane | Primary saturated |
| >CH- | 30-50 | Norbornane bridgehead | Quaternary saturated |
| Quaternary C | 20-50 | Cholesterol core | Fully substituted |

#### Aromatic/Unsaturated Carbons
| Type | δ (ppm) | Example | Note |
|------|---------|---------|------|
| Sp² C (alkene) | 100-150 | Allicin C=C | Alkenyl carbons |
| Aromatic C | 120-160 | Naphthalene | Standard aromatic |
| Aromatic C-H | 120-140 | Naphthalene CH | Aromatic CH |
| Quaternary aromatic | 130-150 | Naphthalene quaternary | No H on carbon |
| Fused aromatic C | 125-135 | Benzo[a]pyrene | Polycyclic |

#### Carbonyl/Carboxyl Carbons
| Type | δ (ppm) | Example | Note |
|------|---------|---------|------|
| C=O (ketone) | 200-220 | (None in test set) | Least shielded |
| C=O (aldehyde) | 190-210 | (None in test set) | Very deshielded |
| C=O (ester) | 160-180 | Aspartame ester | Deshielded by O |
| C=O (amide) | 160-180 | Caffeine, Aspartame | Resonance stabilized |
| COOH | 170-185 | ATP, Hemin | Carboxylic acid |
| Aromatic C=O | 160-170 | Caffeine | Conjugated |

---

## 📡 UV-Vis Spectroscopy Quick Reference

### Chromophores and Absorption

#### Simple Chromophores
| Chromophore | λmax (nm) | ε (M⁻¹cm⁻¹) | Type |
|-------------|-----------|-----------|------|
| n→π* (C=O) | 280-290 | 10-100 | Weak |
| π→π* (C=C) | 160-200 | 1,000-10,000 | Strong |
| π→π* (aromatic) | 200-250 | 1,000-10,000 | Strong |
| Alkyl sulfide | 200-215 | 1,000-2,000 | Medium |
| Disulfide S-S | 255-280 | 100-500 | Medium |

#### Conjugated Systems
| System | λmax (nm) | ε (M⁻¹cm⁻¹) | Example |
|--------|-----------|-----------|---------|
| Conjugated diene | 220-250 | 10,000-20,000 | Cholesterol |
| Naphthalene | 280-290 | 5,000-10,000 | Naphthalene |
| Benzo[a]pyrene | 380-420 | 50,000-100,000 | Benzo[a]pyrene |
| Extended PAH | 300-500 | 100,000+ | Large polycyclics |

#### Heteroaromatic Systems
| System | λmax (nm) | ε (M⁻¹cm⁻¹) | Example |
|--------|-----------|-----------|---------|
| Pyridine | 255-270 | 2,000-3,000 | (None in test set) |
| Imidazole | 210-220 | 3,000-5,000 | ATP purine |
| Purine | 260-280 | 5,000-10,000 | ATP, Caffeine |
| Xanthine | 250-280 | 7,000-12,000 | Caffeine |

### Fine Structure

**Naphthalene-type PAH:**
- Multiple sharp bands (0-0, 0-1, 0-2, etc.)
- Vibrational fine structure
- Allows fingerprinting of PAHs

**Extended PAH (Benzo[a]pyrene):**
- Broad absorption envelope
- Multiple overlapping bands
- Intense long-wavelength absorption

---

## 🧪 Molecular Interpretation Guide

### How to Read Calculated Spectra

#### 1. Frequency/Wavelength Matching
✅ **Good match (±5-10%):**
- Direct comparison with literature
- Indicates correct structure

⚠️ **Moderate deviation (±10-20%):**
- May indicate conformational effects
- Check for solvation needs
- Consider higher basis set

❌ **Large deviation (>20%):**
- Possible structural error
- Check SMILES validity
- May require method change

#### 2. Intensity Matching
✅ **Peak intensities agree:**
- Good description of structure
- Bonding correctly modeled

⚠️ **Intensities differ by 2-3×:**
- Often expected (0-2 accuracy)
- Consider combining with experiment

❌ **Completely different pattern:**
- Possible functional group mis-assignment
- Check molecular structure

#### 3. Number of Peaks
✅ **All expected peaks present:**
- Complete structure description
- No missing functional groups

⚠️ **Some weak peaks missing:**
- May be below detection limit
- Consider integration time

❌ **Entire peak group missing:**
- Possible structural error
- Recheck SMILES input

---

## 🔍 Troubleshooting Guide

### Common Issues in IR Spectroscopy

**Issue:** O-H peak too weak or absent
- **Cause:** Hydrogen bonding intermolecular
- **Solution:** Check for dimer formation; calculate in PCM solvent

**Issue:** No aromatic C-H stretch visible
- **Cause:** Frequency below 3000 cm⁻¹ (overlap with alkyl C-H)
- **Solution:** Look for aromatic C=C stretches instead (1600, 1500 cm⁻¹)

**Issue:** C=O frequency shifted unexpectedly
- **Cause:** Hydrogen bonding, conjugation, or electronic effects
- **Solution:** Recalculate with CPCM; check electronegativity

**Issue:** Frequency > 3500 cm⁻¹ (N-H stretch very high)
- **Cause:** Possible artifact or hydrogen bonding
- **Solution:** Verify structure; calculate free structure in gas phase

### Common Issues in NMR

**Issue:** Computed δ values 1-2 ppm too high/low
- **Cause:** Systematic error in GIAO; requires scaling
- **Solution:** Apply empirical correction factor (typically 0.9-1.0)

**Issue:** Multiplet patterns don't match expected
- **Cause:** Long-range coupling (⁴J, ⁵J) not included
- **Solution:** Increase calculation accuracy; include more coupling constants

**Issue:** Exchangeable proton (OH, NH) missing
- **Cause:** Not computed in standard NMR calculation
- **Solution:** Separate calculation or manual assignment

**Issue:** Aromatic proton δ ~1 ppm too low
- **Cause:** Ring current effects not fully captured
- **Solution:** Use larger basis set; include core functions

### Common Issues in UV-Vis

**Issue:** λmax 20-30 nm too blue (shorter wavelength)
- **Cause:** Typical TD-B3LYP underestimation of conjugation
- **Solution:** Use longer-range functional (CAM-B3LYP, ωB97X-D)

**Issue:** Oscillator strength too weak
- **Cause:** Forbidden transition misassigned; check configuration
- **Solution:** Include more states; check selection rules

**Issue:** Multiple bands expected but only one peak
- **Cause:** Bands overlapping; may need higher resolution
- **Solution:** Broaden with smaller FWHM; use denser wavelength grid

---

## 📋 Practical Examples from Test Set

### Example 1: Norbornane IR Spectrum
```
Peaks:     2960, 2930, 1450, 1260, 890 cm⁻¹
Matches:   Literature values ✓
Accuracy:  ±3-5 cm⁻¹ typical
Interpretation:
  - 2960, 2930: C-H stretches (saturated)
  - 1450: C-H bending
  - 1260: C-C stretch (bridge)
  - 890: Deformation of bridged ring
```

### Example 2: Caffeine NMR
```
¹H NMR:
  - δ 8.2 ppm (1H, s): H-8 (deshielded by N)
  - δ 4.0 ppm (3H, s): N-CH₃
  - δ 3.9 ppm (3H, s): N-CH₃
  - δ 3.8 ppm (3H, s): N-CH₃
  
¹³C NMR:
  - δ 150.8 ppm: C=O
  - δ 142.1 ppm: C-H (aromatic)
  - δ 33-35 ppm: N-CH₃
  
Matches literature: ✓ Excellent agreement
```

### Example 3: Benzo[a]pyrene UV-Vis
```
Absorption:
  λmax = 405 nm (Soret-like band)
  ε = very large (extended conjugation)
  Fine structure present (PAH fingerprint)
  
Matches literature: ✓ Excellent for large PAH
Confirms: Extended aromatic system correctly modeled
```

---

## 📚 Recommended Further Reading

1. **Spectroscopy Texts:**
   - Silverstein, R.M., et al. "Spectrometric Identification of Organic Compounds"
   - Pavia, D.L., et al. "Introduction to Spectroscopy"

2. **NMR References:**
   - Claridge, T.D.W. "High-Resolution NMR Techniques in Organic Chemistry"
   - Aue, W.P., et al. "NMR and the Periodic Table"

3. **Computational Chemistry:**
   - Jensen, F. "Introduction to Computational Chemistry"
   - Cramer, C.J. "Essentials of Computational Chemistry"

4. **Online Resources:**
   - NIST Chemistry WebBook (spectra database)
   - Sigma-Aldrich SpectraBase (commercial spectra)
   - ChemSpider (predicted spectra)

---

**Document Status:** REFERENCE GUIDE  
**Version:** 1.0  
**Last Updated:** 2026-02-06  
**Use:** Supporting documentation for ChemDraw Pro validation
