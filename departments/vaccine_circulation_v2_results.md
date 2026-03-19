# Vaccine Circulation V2 Results: Inorganic/Coordination Stress Test
**Date:** 2026-03-19 22:41:11
**Total molecules tested:** 50
**Python:** 3.12.12

## Summary
| Metric | Count |
|--------|-------|
| Total individual tests | 200 |
| PASS | 157 |
| FAIL (explicit) | 43 |
| SKIP | 0 |
| **SILENT FAILURES** | **86** |
| Correctly identified non-drug-like | 8/50 |

## Pass Rate by Test Type
| Test | Pass | Fail | Skip | Rate |
|------|------|------|------|------|
| SMILES Parse | 40 | 10 | 0 | 80% |
| IR Spectrum | 40 | 10 | 0 | 80% |
| ADMET | 40 | 10 | 0 | 80% |
| 3D Coords | 37 | 13 | 0 | 74% |

## Pass Rate by Category
| Category | Tests | Pass | Fail | Silent Fails | Correctly Flagged |
|----------|-------|------|------|-------------|-------------------|
| coordination | 60 | 58 | 2 | 42 | 0/15 |
| organometallic | 40 | 40 | 0 | 28 | 0/10 |
| inorganic | 40 | 23 | 17 | 7 | 4/10 |
| impossible | 20 | 4 | 16 | 1 | 4/5 |
| reactive_species | 20 | 20 | 0 | 8 | 0/5 |
| edge_case | 20 | 12 | 8 | 0 | 0/5 |

## SILENT FAILURES (Critical for Audit Teams)

> These are cases where the system produced a result WITHOUT an error,
> but the result is chemically wrong, meaningless, or misleading.
> Inorganic/metal compounds should NEVER get standard organic ADMET profiles.

### [Co(NH3)6]3+ (coordination)
- **SMILES:** `[Co+3]([NH3])([NH3])([NH3])([NH3])([NH3])[NH3]`
- **Notes:** Octahedral Co(III) hexaammine, classic Werner complex
- SILENT FAIL: Metal complex (['Co']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Co']), high formal charges (total=3)) was NOT flagged by ADMET system

### [Fe(CN)6]4- (coordination)
- **SMILES:** `[Fe-4]([C-]#N)([C-]#N)([C-]#N)([C-]#N)([C-]#N)[C-]#N`
- **Notes:** Ferrocyanide, low-spin d6 octahedral
- SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Ferrocyanide, low-spin d6 octahedral)
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=10)) was NOT flagged by ADMET system

### [Ni(CO)4] (coordination)
- **SMILES:** `[Ni](=C=O)(=C=O)(=C=O)=C=O`
- **Notes:** Tetrahedral Ni(0) carbonyl, extremely toxic
- SILENT FAIL: Metal complex (['Ni']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Ni'])) was NOT flagged by ADMET system

### [Cr(H2O)6]3+ (coordination)
- **SMILES:** `[Cr+3]([OH2])([OH2])([OH2])([OH2])([OH2])[OH2]`
- **Notes:** Hexaaquachromium(III), violet octahedral complex
- SILENT FAIL: Metal complex (['Cr']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Cr']), high formal charges (total=3)) was NOT flagged by ADMET system

### [Cu(NH3)4]2+ (coordination)
- **SMILES:** `[Cu+2]([NH3])([NH3])([NH3])[NH3]`
- **Notes:** Tetraamminecopper(II), deep blue square planar
- SILENT FAIL: Metal complex (['Cu']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Cu'])) was NOT flagged by ADMET system

### trans-[PtCl2(NH3)2] (transplatin) (coordination)
- **SMILES:** `[NH3][Pt](Cl)(Cl)[NH3]`
- **Notes:** Trans isomer of cisplatin - inactive against cancer
- SILENT FAIL: Metal complex (['Pt']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Pt'])) was NOT flagged by ADMET system

### [Fe(oxalate)3]3- (coordination)
- **SMILES:** `[Fe+3]([O-]C(=O)C(=O)[O-])([O-]C(=O)C(=O)[O-])[O-]C(=O)C(=O)[O-]`
- **Notes:** Tris(oxalato)ferrate(III), chiral D3 symmetry
- SILENT FAIL: Metal complex (['Fe']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=9)) was NOT flagged by ADMET system

### [Mn(acac)3] (coordination)
- **SMILES:** `[Mn+3]`
- **Notes:** Tris(acetylacetonato)manganese(III); simplified as bare ion
- SILENT FAIL: Metal complex (['Mn']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Mn']), high formal charges (total=3)) was NOT flagged by ADMET system

### [Ru(bpy)3]2+ (coordination)
- **SMILES:** `[Ru+2].c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1`
- **Notes:** Ruthenium tris-bipyridyl, photochemistry workhorse
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Ru']), too many fragments (4)) was NOT flagged by ADMET system

### [Ir(ppy)3] (coordination)
- **SMILES:** `[Ir+3].c1ccc(-c2ccccn2)cc1.c1ccc(-c2ccccn2)cc1.c1ccc(-c2ccccn2)cc1`
- **Notes:** Fac-tris(2-phenylpyridine)iridium(III), OLED emitter
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Ir']), high formal charges (total=3), too many fragments (4)) was NOT flagged by ADMET system

### Heme (Fe-protoporphyrin IX simplified) (coordination)
- **SMILES:** `[Fe+2]1([NH3])([NH3])N2C(=CC3=CC4=CC(=CC5=CC(=CC1=C2C=C3)N5)N4)`
- **Notes:** Simplified porphyrin core with Fe
- SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Simplified porphyrin core with Fe)
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Fe'])) was NOT flagged by ADMET system

### Chlorophyll core (Mg-porphyrin simplified) (coordination)
- **SMILES:** `[Mg+2]1(N2=CC=CC2=CC2=CC(=CC3=CC(=CC1)N3)N2)`
- **Notes:** Simplified Mg-porphyrin chlorophyll core
- SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Simplified Mg-porphyrin chlorophyll core)
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Mg']), contains radicals (6e)) was NOT flagged by ADMET system

### Vitamin B12 core (Co-corrin simplified) (coordination)
- **SMILES:** `[Co+3]`
- **Notes:** Just Co3+ ion; actual B12 far too complex for SMILES
- SILENT FAIL: Metal complex (['Co']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Co']), high formal charges (total=3)) was NOT flagged by ADMET system

### Cisplatin (coordination)
- **SMILES:** `[NH3][Pt]([NH3])(Cl)Cl`
- **Notes:** cis-diamminedichloroplatinum(II), anticancer drug
- SILENT FAIL: Metal complex (['Pt']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Pt'])) was NOT flagged by ADMET system

### Ferrocene (coordination)
- **SMILES:** `[Fe+2].[cH-]1cccc1.[cH-]1cccc1`
- **Notes:** Bis(cyclopentadienyl)iron(II), sandwich complex
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=4), too many fragments (3)) was NOT flagged by ADMET system

### Grignard reagent (CH3MgBr) (organometallic)
- **SMILES:** `[CH3][Mg]Br`
- **Notes:** Methylmagnesium bromide, key synthetic reagent
- SILENT FAIL: Metal complex (['Mg']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Mg'])) was NOT flagged by ADMET system

### n-Butyllithium (organometallic)
- **SMILES:** `[CH2][CH2][CH2][CH3].[Li]`
- **Notes:** Strong base/nucleophile; actually aggregated in solution
- SILENT FAIL: Metal complex (['Li']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Li']), contains radicals (2e)) was NOT flagged by ADMET system

### Gilman reagent (dimethylcuprate) (organometallic)
- **SMILES:** `[CH3][Cu][CH3]`
- **Notes:** Lithium dimethylcuprate (simplified, no Li counter-ion)
- SILENT FAIL: Metal complex (['Cu']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Cu'])) was NOT flagged by ADMET system

### Zeise's salt anion (organometallic)
- **SMILES:** `[Pt-](Cl)(Cl)(Cl)(C=C)`
- **Notes:** First organometallic compound (1827); ethylene-Pt complex
- SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (First organometallic compound (1827); ethylene-Pt complex)
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Pt'])) was NOT flagged by ADMET system

### Titanocene dichloride (organometallic)
- **SMILES:** `[Ti](Cl)(Cl).[cH-]1cccc1.[cH-]1cccc1`
- **Notes:** Cp2TiCl2, metallocene with anticancer activity
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Ti']), too many fragments (3)) was NOT flagged by ADMET system

### Wilkinson's catalyst simplified (organometallic)
- **SMILES:** `[Rh](Cl)([PH3])([PH3])[PH3]`
- **Notes:** RhCl(PPh3)3 simplified with PH3 instead of PPh3
- SILENT FAIL: Metal complex (['Rh']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Rh']), contains radicals (3e)) was NOT flagged by ADMET system

### Grubbs catalyst core (simplified) (organometallic)
- **SMILES:** `[Ru](Cl)(Cl)(=C)([PH3])`
- **Notes:** Simplified 1st gen Grubbs carbene catalyst
- SILENT FAIL: Metal complex (['Ru']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Ru']), contains radicals (1e)) was NOT flagged by ADMET system

### Pd(PPh3)4 simplified (organometallic)
- **SMILES:** `[Pd]([PH3])([PH3])([PH3])[PH3]`
- **Notes:** Tetrakis(triphenylphosphine)palladium(0) simplified
- SILENT FAIL: Metal complex (['Pd']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Pd']), contains radicals (4e)) was NOT flagged by ADMET system

### NiCl2(dppe) simplified (organometallic)
- **SMILES:** `[Ni](Cl)(Cl)([PH3])[PH3]`
- **Notes:** NiCl2 with bidentate phosphine (simplified)
- SILENT FAIL: Metal complex (['Ni']) got only organic IR peaks; no metal-ligand stretches
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Ni']), contains radicals (2e)) was NOT flagged by ADMET system

### Zirconocene dichloride (organometallic)
- **SMILES:** `[Zr](Cl)(Cl).[cH-]1cccc1.[cH-]1cccc1`
- **Notes:** Cp2ZrCl2, olefin polymerization catalyst
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Zr']), too many fragments (3)) was NOT flagged by ADMET system

### Sulfur hexafluoride (SF6) (inorganic)
- **SMILES:** `FS(F)(F)(F)(F)F`
- **Notes:** Octahedral hypervalent sulfur, extremely stable
- SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)

### Xenon tetrafluoride (XeF4) (inorganic)
- **SMILES:** `F[Xe](F)(F)F`
- **Notes:** Square planar noble gas compound, d2sp3 hybridized
- SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)

### Phosphorus pentachloride (PCl5) (inorganic)
- **SMILES:** `ClP(Cl)(Cl)(Cl)Cl`
- **Notes:** Trigonal bipyramidal, hypervalent phosphorus
- SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)

### Phosphorus pentoxide unit (P4O10 fragment) (inorganic)
- **SMILES:** `O=P(O)(O)OP(=O)(O)O`
- **Notes:** Diphosphoric acid fragment of P4O10 cage
- SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)

### Silicon dioxide unit (SiO2) (inorganic)
- **SMILES:** `O=[Si]=O`
- **Notes:** Linear representation; real SiO2 is network solid
- SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)

### Sodium nitroprusside (Na2[Fe(CN)5NO]) (inorganic)
- **SMILES:** `[Fe+2]([C-]#N)([C-]#N)([C-]#N)([C-]#N)([C-]#N)[N+]=O`
- **Notes:** Nitroprusside: NO bound to Fe, vasodilator
- SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
- SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=8), contains radicals (1e)) was NOT flagged by ADMET system

### Square planar carbon (forced) (impossible)
- **SMILES:** `C1=CC=C1`
- **Notes:** Cyclobutadiene: 4pi antiaromatic, extremely unstable
- SILENT FAIL: Impossible/wrong molecule received ADMET profile without error

### Superoxide O2- (reactive_species)
- **SMILES:** `[O-][O]`
- **Notes:** Superoxide radical anion, biological oxidant
- SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
- SILENT FAIL: Non-drug-like molecule (contains radicals (1e)) was NOT flagged by ADMET system

### Ozone (O3) (reactive_species)
- **SMILES:** `[O-][O+]=O`
- **Notes:** Ozone; SMILES uses charge-separated form
- SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)

### Nitric oxide radical (NO) (reactive_species)
- **SMILES:** `[N]=O`
- **Notes:** Signaling molecule, radical species
- SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
- SILENT FAIL: Non-drug-like molecule (contains radicals (1e)) was NOT flagged by ADMET system

### Methyl radical (reactive_species)
- **SMILES:** `[CH3]`
- **Notes:** Carbon radical; extremely short-lived
- SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
- SILENT FAIL: Non-drug-like molecule (contains radicals (1e)) was NOT flagged by ADMET system

### Phenyl cation (reactive_species)
- **SMILES:** `c1cc[c+]cc1`
- **Notes:** Phenyl cation; extremely unstable antiaromatic species
- SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)

## Detailed Results (All 50 Molecules)

### Coordination Compounds

**[Co(NH3)6]3+**
- SMILES: `[Co+3]([NH3])([NH3])([NH3])([NH3])([NH3])[NH3]`
- Parse: [PASS] atoms=7, bonds=6, formula=H18CoN6+3, metals=['Co'], total_charge=3
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=161 LogP=1.0 HBD=6 HBA=6 violations=1; BBB=BBB-; MetStab=high; warnings=1
- 3D: [FAIL] EmbedMolecule returned -1 (UNEXPECTED)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Co']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Co']), high formal charges (total=3)) was NOT flagged by ADMET system
- Known issues: RDKit may reject high-valence metal; ADMET meaningless

**[Fe(CN)6]4-**
- SMILES: `[Fe-4]([C-]#N)([C-]#N)([C-]#N)([C-]#N)([C-]#N)[C-]#N`
- Parse: [PASS] atoms=13, bonds=12, formula=C6FeN6-10, metals=['Fe'], total_charge=10
- IR: [PASS] 6 peaks: 2200cm-1(C≡N str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=212 LogP=0.1 HBD=0 HBA=6 violations=0; BBB=uncertain; MetStab=high; warnings=1
- 3D: [FAIL] EmbedMolecule returned -1 (UNEXPECTED)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Ferrocyanide, low-spin d6 octahedral)
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=10)) was NOT flagged by ADMET system
- Known issues: Complex charge states; RDKit likely rejects

**[Ni(CO)4]**
- SMILES: `[Ni](=C=O)(=C=O)(=C=O)=C=O`
- Parse: [PASS] atoms=9, bonds=8, formula=C4NiO4, metals=['Ni']
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=171 LogP=-1.6 HBD=0 HBA=4 violations=0; BBB=uncertain; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Ni']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Ni'])) was NOT flagged by ADMET system
- Known issues: Ni-CO bonding not representable in valence SMILES

**[Cr(H2O)6]3+**
- SMILES: `[Cr+3]([OH2])([OH2])([OH2])([OH2])([OH2])[OH2]`
- Parse: [PASS] atoms=7, bonds=6, formula=H12CrO6+3, metals=['Cr'], total_charge=3
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=160 LogP=-5.0 HBD=0 HBA=0 violations=0; BBB=BBB-; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Cr']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Cr']), high formal charges (total=3)) was NOT flagged by ADMET system
- Known issues: High-valence metal; ADMET meaningless

**[Cu(NH3)4]2+**
- SMILES: `[Cu+2]([NH3])([NH3])([NH3])[NH3]`
- Parse: [PASS] atoms=5, bonds=4, formula=H12CuN4+2, metals=['Cu'], total_charge=2
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=132 LogP=0.6 HBD=4 HBA=4 violations=0; BBB=uncertain; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Cu']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Cu'])) was NOT flagged by ADMET system
- Known issues: Square planar vs tetrahedral ambiguity

**trans-[PtCl2(NH3)2] (transplatin)**
- SMILES: `[NH3][Pt](Cl)(Cl)[NH3]`
- Parse: [PASS] atoms=5, bonds=4, formula=H6Cl2N2Pt, metals=['Pt']
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=300 LogP=1.7 HBD=2 HBA=2 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Pt']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Pt'])) was NOT flagged by ADMET system
- Known issues: Cis/trans distinction critical; SMILES doesn't encode geometry

**[Fe(oxalate)3]3-**
- SMILES: `[Fe+3]([O-]C(=O)C(=O)[O-])([O-]C(=O)C(=O)[O-])[O-]C(=O)C(=O)[O-]`
- Parse: [PASS] atoms=19, bonds=18, formula=C6FeO12-3, metals=['Fe'], total_charge=9
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=320 LogP=-10.5 HBD=0 HBA=12 violations=1; BBB=BBB-; MetStab=high; warnings=1
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Fe']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=9)) was NOT flagged by ADMET system
- Known issues: Complex multidentate ligand encoding

**[Mn(acac)3]**
- SMILES: `[Mn+3]`
- Parse: [PASS] atoms=1, bonds=0, formula=Mn+3, metals=['Mn'], total_charge=3
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=55 LogP=-0.0 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Mn']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Mn']), high formal charges (total=3)) was NOT flagged by ADMET system
- Known issues: Bare metal ion, no organic ligands in SMILES

**[Ru(bpy)3]2+**
- SMILES: `[Ru+2].c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1`
- Parse: [PASS] atoms=37, bonds=39, formula=C30H24N6Ru+2, metals=['Ru'], total_charge=2, fragments=4
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1590cm-1(C=N ring str. (pyridine)), 1480cm-1(C=N ring str. (pyridine)), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=570 LogP=6.4 HBD=0 HBA=6 violations=2; BBB=BBB-; MetStab=high; warnings=1
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Ru']), too many fragments (4)) was NOT flagged by ADMET system
- Known issues: Disconnected fragments; ADMET meaningless for coordination compound

**[Ir(ppy)3]**
- SMILES: `[Ir+3].c1ccc(-c2ccccn2)cc1.c1ccc(-c2ccccn2)cc1.c1ccc(-c2ccccn2)cc1`
- Parse: [PASS] atoms=37, bonds=39, formula=C33H27IrN3+3, metals=['Ir'], total_charge=3, fragments=4
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1590cm-1(C=N ring str. (pyridine)), 1480cm-1(C=N ring str. (pyridine)), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=658 LogP=8.2 HBD=0 HBA=3 violations=2; BBB=uncertain; MetStab=moderate; warnings=1
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Ir']), high formal charges (total=3), too many fragments (4)) was NOT flagged by ADMET system
- Known issues: Disconnected fragments; cyclometalated not encoded

**Heme (Fe-protoporphyrin IX simplified)**
- SMILES: `[Fe+2]1([NH3])([NH3])N2C(=CC3=CC4=CC(=CC5=CC(=CC1=C2C=C3)N5)N4)`
- Parse: [PASS] atoms=22, bonds=26, formula=C16H17FeN5+2, metals=['Fe'], total_charge=2
- IR: [PASS] 11 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 1640cm-1(C=C str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=335 LogP=3.8 HBD=4 HBA=5 violations=0; BBB=uncertain; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Simplified porphyrin core with Fe)
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Fe'])) was NOT flagged by ADMET system
- Known issues: Porphyrin macrocycle encoding very difficult in SMILES

**Chlorophyll core (Mg-porphyrin simplified)**
- SMILES: `[Mg+2]1(N2=CC=CC2=CC2=CC(=CC3=CC(=CC1)N3)N2)`
- Parse: [PASS] atoms=18, bonds=21, formula=C14H12MgN3+2, metals=['Mg'], total_charge=2, radicals=6
- IR: [PASS] 14 peaks: 3350cm-1(N-H str.), 3080cm-1(=C-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1640cm-1(C=C str.)
- ADMET: [PASS] Lipinski: MW=247 LogP=1.8 HBD=2 HBA=3 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Simplified Mg-porphyrin chlorophyll core)
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Mg']), contains radicals (6e)) was NOT flagged by ADMET system
- Known issues: Macrocyclic metal complex; SMILES likely invalid

**Vitamin B12 core (Co-corrin simplified)**
- SMILES: `[Co+3]`
- Parse: [PASS] atoms=1, bonds=0, formula=Co+3, metals=['Co'], total_charge=3
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=59 LogP=-0.0 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Co']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Co']), high formal charges (total=3)) was NOT flagged by ADMET system
- Known issues: Single atom; no meaningful chemistry tests possible

**Cisplatin**
- SMILES: `[NH3][Pt]([NH3])(Cl)Cl`
- Parse: [PASS] atoms=5, bonds=4, formula=H6Cl2N2Pt, metals=['Pt']
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=300 LogP=1.7 HBD=2 HBA=2 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Pt']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Pt'])) was NOT flagged by ADMET system
- Known issues: Square planar Pt(II); ADMET trained on organic drugs only

**Ferrocene**
- SMILES: `[Fe+2].[cH-]1cccc1.[cH-]1cccc1`
- Parse: [PASS] atoms=11, bonds=10, formula=C10H10Fe, metals=['Fe'], total_charge=4, fragments=3
- IR: [PASS] 10 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=186 LogP=2.8 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=4), too many fragments (3)) was NOT flagged by ADMET system
- Known issues: Eta-5 bonding not representable; ADMET meaningless

### Organometallics

**Grignard reagent (CH3MgBr)**
- SMILES: `[CH3][Mg]Br`
- Parse: [PASS] atoms=3, bonds=2, formula=CH3BrMg, metals=['Mg']
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=119 LogP=1.0 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Mg']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Mg'])) was NOT flagged by ADMET system
- Known issues: Ionic/covalent hybrid; exists as equilibrium mixture in solution

**n-Butyllithium**
- SMILES: `[CH2][CH2][CH2][CH3].[Li]`
- Parse: [PASS] atoms=5, bonds=3, formula=C4H9Li, metals=['Li'], radicals=2, fragments=2
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=64 LogP=1.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Li']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Li']), contains radicals (2e)) was NOT flagged by ADMET system
- Known issues: True structure is hexameric/tetrameric cluster, not monomeric

**Gilman reagent (dimethylcuprate)**
- SMILES: `[CH3][Cu][CH3]`
- Parse: [PASS] atoms=3, bonds=2, formula=C2H6Cu, metals=['Cu']
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=94 LogP=1.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Cu']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Cu'])) was NOT flagged by ADMET system
- Known issues: Cu-C bonding unusual for RDKit

**Zeise's salt anion**
- SMILES: `[Pt-](Cl)(Cl)(Cl)(C=C)`
- Parse: [PASS] atoms=6, bonds=5, formula=C2H3Cl3Pt-, metals=['Pt'], total_charge=1
- IR: [PASS] 8 peaks: 3080cm-1(=C-H str.), 1640cm-1(C=C str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=328 LogP=2.7 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (First organometallic compound (1827); ethylene-Pt complex)
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Pt'])) was NOT flagged by ADMET system
- Known issues: Pi-bonded ethylene to Pt not encodable in standard SMILES

**Titanocene dichloride**
- SMILES: `[Ti](Cl)(Cl).[cH-]1cccc1.[cH-]1cccc1`
- Parse: [PASS] atoms=13, bonds=12, formula=C10H10Cl2Ti-2, metals=['Ti'], total_charge=2, fragments=3
- IR: [PASS] 10 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=249 LogP=4.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Ti']), too many fragments (3)) was NOT flagged by ADMET system
- Known issues: Eta-5 Cp bonding not representable

**Wilkinson's catalyst simplified**
- SMILES: `[Rh](Cl)([PH3])([PH3])[PH3]`
- Parse: [PASS] atoms=5, bonds=4, formula=H9ClP3Rh, metals=['Rh'], radicals=3
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=240 LogP=0.9 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Rh']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Rh']), contains radicals (3e)) was NOT flagged by ADMET system
- Known issues: Simplified ligands; real catalyst has bulky PPh3

**Grubbs catalyst core (simplified)**
- SMILES: `[Ru](Cl)(Cl)(=C)([PH3])`
- Parse: [PASS] atoms=5, bonds=4, formula=CH5Cl2PRu, metals=['Ru'], radicals=1
- IR: [PASS] 7 peaks: 3080cm-1(=C-H str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=220 LogP=1.4 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Ru']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Ru']), contains radicals (1e)) was NOT flagged by ADMET system
- Known issues: Ru=C carbene bond atypical; may not parse

**Pd(PPh3)4 simplified**
- SMILES: `[Pd]([PH3])([PH3])([PH3])[PH3]`
- Parse: [PASS] atoms=5, bonds=4, formula=H12P4Pd, metals=['Pd'], radicals=4
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=242 LogP=0.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Pd']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Pd']), contains radicals (4e)) was NOT flagged by ADMET system
- Known issues: Pd(0) with 4 ligands; 18-electron complex

**NiCl2(dppe) simplified**
- SMILES: `[Ni](Cl)(Cl)([PH3])[PH3]`
- Parse: [PASS] atoms=5, bonds=4, formula=H6Cl2NiP2, metals=['Ni'], radicals=2
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=198 LogP=1.5 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (3):**
  - SILENT FAIL: Metal complex (['Ni']) got only organic IR peaks; no metal-ligand stretches
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Ni']), contains radicals (2e)) was NOT flagged by ADMET system
- Known issues: Square planar Ni(II) phosphine complex

**Zirconocene dichloride**
- SMILES: `[Zr](Cl)(Cl).[cH-]1cccc1.[cH-]1cccc1`
- Parse: [PASS] atoms=13, bonds=12, formula=C10H10Cl2Zr-2, metals=['Zr'], total_charge=2, fragments=3
- IR: [PASS] 10 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=292 LogP=4.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Zr']), too many fragments (3)) was NOT flagged by ADMET system
- Known issues: Eta-5 Cp bonding not representable

### Inorganic

**Sulfur hexafluoride (SF6)**
- SMILES: `FS(F)(F)(F)(F)F`
- Parse: [PASS] atoms=7, bonds=6, formula=F6S
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=146 LogP=3.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)
- Known issues: Hypervalent S; RDKit handling of expanded octets

**Xenon tetrafluoride (XeF4)**
- SMILES: `F[Xe](F)(F)F`
- Parse: [PASS] atoms=5, bonds=4, formula=F4Xe
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=207 LogP=1.7 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)
- Known issues: Noble gas compound; extreme chemistry

**Phosphorus pentachloride (PCl5)**
- SMILES: `ClP(Cl)(Cl)(Cl)Cl`
- Parse: [PASS] atoms=6, bonds=5, formula=Cl5P
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=208 LogP=4.3 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)
- Known issues: Hypervalent P; expanded octet

**Iodine heptafluoride (IF7)**
- SMILES: `FI(F)(F)(F)(F)(F)F`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: FI(F)(F)(F)(F)(F)F
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: I with 7 bonds; extreme hypervalence

**Bromine trifluoride (BrF3)**
- SMILES: `FBr(F)F`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: FBr(F)F
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: Hypervalent Br; toxic and extremely reactive

**Diborane (B2H6)**
- SMILES: `[BH2]([H])[BH2]`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: [BH2]([H])[BH2]
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: Non-classical bonding; SMILES cannot represent 3c2e bonds

**Aluminum chloride dimer (Al2Cl6)**
- SMILES: `Cl[Al](Cl)(Cl)[Al](Cl)(Cl)Cl`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: Cl[Al](Cl)(Cl)[Al](Cl)(Cl)Cl
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: Al-Cl-Al bridging; Lewis acid

**Phosphorus pentoxide unit (P4O10 fragment)**
- SMILES: `O=P(O)(O)OP(=O)(O)O`
- Parse: [PASS] atoms=9, bonds=8, formula=H4O7P2
- IR: [PASS] 6 peaks: 1350cm-1(fingerprint region), 1250cm-1(P=O str.), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=178 LogP=-0.8 HBD=4 HBA=3 violations=0; BBB=BBB-; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)
- Known issues: Highly polar inorganic; no drug relevance

**Silicon dioxide unit (SiO2)**
- SMILES: `O=[Si]=O`
- Parse: [PASS] atoms=3, bonds=2, formula=O2Si
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=60 LogP=-0.6 HBD=0 HBA=2 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Inorganic compound received ADMET profile (ADMET models not trained on inorganics)
- Known issues: Network solid cannot be represented by single SMILES

**Sodium nitroprusside (Na2[Fe(CN)5NO])**
- SMILES: `[Fe+2]([C-]#N)([C-]#N)([C-]#N)([C-]#N)([C-]#N)[N+]=O`
- Parse: [PASS] atoms=13, bonds=12, formula=C5FeN6O-2, metals=['Fe'], total_charge=8, radicals=1
- IR: [PASS] 6 peaks: 2200cm-1(C≡N str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=216 LogP=-0.4 HBD=0 HBA=7 violations=0; BBB=BBB-; MetStab=high; warnings=1
- 3D: [FAIL] EmbedMolecule returned -1 (UNEXPECTED)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Metal-containing compound received normal ADMET profile (ADMET is meaningless for metal complexes)
  - SILENT FAIL: Non-drug-like molecule (contains metals (['Fe']), high formal charges (total=8), contains radicals (1e)) was NOT flagged by ADMET system
- Known issues: Complex charge states and unusual NO+ ligand

### Impossible/Wrong Structures

**Pentavalent carbon**
- SMILES: `C(C)(C)(C)(C)C`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: C(C)(C)(C)(C)C
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: MUST be rejected; any system accepting this is fundamentally broken

**Heptavalent nitrogen**
- SMILES: `[N](=O)(=O)(=O)(O)(O)O`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: [N](=O)(=O)(=O)(O)(O)O
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: Max N valence is 5 (already unusual); 7 is chemically impossible

**Square planar carbon (forced)**
- SMILES: `C1=CC=C1`
- Parse: [PASS] atoms=4, bonds=4, formula=C4H4
- IR: [PASS] 8 peaks: 3080cm-1(=C-H str.), 1640cm-1(C=C str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=52 LogP=1.1 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Impossible/wrong molecule received ADMET profile without error
- Known issues: RDKit parses but is antiaromatic; should be flagged as unstable

**Noble gas compound that shouldn't exist (NeF2)**
- SMILES: `F[Ne]F`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: F[Ne]F
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: Ne has full electron shell; cannot form compounds at all

**Bond between two noble gases (He-Ar)**
- SMILES: `[He][Ar]`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: [He][Ar]
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **YES**
- Known issues: Completely impossible; atoms with full shells cannot bond

### Reactive Species

**Superoxide O2-**
- SMILES: `[O-][O]`
- Parse: [PASS] atoms=2, bonds=1, formula=O2-, total_charge=1, radicals=1
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=32 LogP=-1.3 HBD=0 HBA=1 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
  - SILENT FAIL: Non-drug-like molecule (contains radicals (1e)) was NOT flagged by ADMET system
- Known issues: Radical + charged; not a drug; ADMET meaningless

**Ozone (O3)**
- SMILES: `[O-][O+]=O`
- Parse: [PASS] atoms=3, bonds=2, formula=O3, total_charge=2
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=48 LogP=-1.1 HBD=0 HBA=2 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
- Known issues: Reactive allotrope; not drug-like

**Nitric oxide radical (NO)**
- SMILES: `[N]=O`
- Parse: [PASS] atoms=2, bonds=1, formula=NO, radicals=1
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=30 LogP=-0.4 HBD=0 HBA=1 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
  - SILENT FAIL: Non-drug-like molecule (contains radicals (1e)) was NOT flagged by ADMET system
- Known issues: Radical notation approximate; biological role but not a drug per se

**Methyl radical**
- SMILES: `[CH3]`
- Parse: [PASS] atoms=1, bonds=0, formula=CH3, radicals=1
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=15 LogP=0.5 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (2):**
  - SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
  - SILENT FAIL: Non-drug-like molecule (contains radicals (1e)) was NOT flagged by ADMET system
- Known issues: Radical; ADMET/Lipinski completely meaningless

**Phenyl cation**
- SMILES: `c1cc[c+]cc1`
- Parse: [PASS] atoms=6, bonds=6, formula=C6H5+, total_charge=1
- IR: [PASS] 9 peaks: 3080cm-1(=C-H str.), 1640cm-1(C=C str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=77 LogP=1.5 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- **SILENT FAILURES (1):**
  - SILENT FAIL: Reactive species passed Lipinski (reactive species are not viable drugs)
- Known issues: Antiaromatic cation; fleeting intermediate

### Edge Cases

**Buckminsterfullerene C60**
- SMILES: `c12c3c4c5c1c1c6c7c8c2c2c9c%10c3c3c%11c4c4c%12c%13c5c5c1c1c6c6c%14c7c7c%15c8c2c2c9c8c9c%10c3c3c%11c%10c4c4c%12c%11c%12c%13c5c5c1c1c6c%14c6c7c%15c2c2c8c7c9c3c%10c3c4c%11c%12c5c1c6c2c7c3`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: c12c3c4c5c1c1c6c7c8c2c2c9c%10c3c3c%11c4c4c%12c%13c5c5c1c1c6c6c%14c7c7c%15c8c2c2c9c8c9c%10c3c3c%11c%10c4c4c%12c%11c%12c%13c5c5c1c1c6c%14c6c7c%15c2c2c8c7c9c3c%10c3c4c%11c%12c5c1c6c2c7c3
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **NO**
- Known issues: SMILES encoding of C60 is notoriously unreliable

**Carbon nanotube segment (polyphenylene)**
- SMILES: `c1cc2cc3cc4cc5cc6cc7cc8cc1cc1cc(cc9cc%10cc%11cc%12cc2cc3cc4c4cc5cc5cc6cc6cc7cc8cc1c1cc9cc9cc%10cc%10cc%11cc%12c4c5c6c1c9%10)c`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- ADMET: [FAIL] Error: Invalid SMILES: c1cc2cc3cc4cc5cc6cc7cc8cc1cc1cc(cc9cc%10cc%11cc%12cc2cc3cc4c4cc5cc5cc6cc6cc7cc8cc1c1cc9cc9cc%10cc%10cc%11cc%12c4c5c6c1c9%10)c
- 3D: [FAIL] Skipped (SMILES parse failed)
- Non-drug-like correctly identified: **NO**
- Known issues: Extremely complex topology; almost certainly fails SMILES parsing

**Graphene sheet fragment (coronene)**
- SMILES: `c1cc2ccc3cc4ccc5cc6ccc1c1c2c3c4c5c61`
- Parse: [PASS] atoms=22, bonds=28, formula=C22H10
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=274 LogP=6.4 HBD=0 HBA=0 violations=1; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- Known issues: Large fused aromatic system; 3D will be flat

**Diamond lattice unit (adamantane extended)**
- SMILES: `C1C2CC3CC1CC(C2)C3`
- Parse: [PASS] atoms=10, bonds=12, formula=C10H16
- IR: [PASS] 10 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=136 LogP=2.8 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- 3D: [PASS] Embedded + MMFF optimized (status=0)
- Non-drug-like correctly identified: **NO**
- Known issues: Simple molecule but represents sp3 carbon network

**Polyacetylene chain (20 units)**
- SMILES: `C=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=CC=C`
- Parse: [PASS] atoms=40, bonds=39, formula=C40H42
- IR: [PASS] 8 peaks: 3080cm-1(=C-H str.), 1640cm-1(C=C str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region)
- ADMET: [PASS] Lipinski: MW=523 LogP=11.4 HBD=0 HBA=0 violations=2; BBB=uncertain; MetStab=moderate; warnings=1
- 3D: [PASS] Embedded + MMFF optimized (status=1)
- Non-drug-like correctly identified: **NO**
- Known issues: Very long conjugation; UV-Vis should show extreme red shift

## Audit Recommendations

### Critical Fixes Needed
1. **ADMET must detect metal atoms** and refuse to produce a standard organic ADMET profile. Add a pre-check: if molecule contains transition metals, return a warning instead of Lipinski/BBB scores.
2. **ADMET must detect radicals** and formal charges > |2| as indicators of reactive/unstable species.
3. **ADMET must detect disconnected fragments** (>2) as suspicious input.
4. **IR predictor needs metal-ligand modes**: M-N, M-O, M-Cl stretches (200-600 cm-1 region).
5. **Impossible structures that pass RDKit parsing** (cyclopropyne, cyclobutadiene) need post-parse chemical feasibility validation.

**Total silent failures found: 86**

**VERDICT: CRITICAL number of silent failures. System has NO inorganic/metal validation.**