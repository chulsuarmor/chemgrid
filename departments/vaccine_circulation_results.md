# Vaccine Circulation Test Results (백신 공회전 결과)
**Date:** 2026-03-19 22:15:30
**Total molecules tested:** 50

## Summary
| Metric | Count |
|--------|-------|
| Total individual tests | 250 |
| PASS | 215 |
| FAIL (explicit) | 35 |
| SKIP | 0 |
| **SILENT FAILURES** | **13** |

## Pass Rate by Test Type
| Test | Pass | Fail | Skip | Rate |
|------|------|------|------|------|
| SMILES Parse | 44 | 6 | 0 | 88% |
| IR Spectrum | 44 | 6 | 0 | 88% |
| 3D Coords | 41 | 9 | 0 | 82% |
| Lead Variants | 42 | 8 | 0 | 84% |
| ADMET | 44 | 6 | 0 | 88% |

## Pass Rate by Category
| Category | Tests | Pass | Fail | Silent Fails |
|----------|-------|------|------|-------------|
| bridged_cage | 25 | 24 | 1 | 0 |
| metal_complex | 25 | 18 | 7 | 5 |
| large_drug | 50 | 50 | 0 | 1 |
| stereochemistry | 25 | 25 | 0 | 0 |
| reactive_intermediate | 25 | 19 | 6 | 4 |
| heterocyclic_fused | 25 | 20 | 5 | 0 |
| natural_product | 25 | 25 | 0 | 0 |
| intentionally_wrong | 25 | 14 | 11 | 3 |
| edge_case | 25 | 20 | 5 | 0 |

## SILENT FAILURES (Critical for Audit Teams)

> These are cases where the system produced a result WITHOUT an error,
> but the result is chemically wrong, meaningless, or misleading.
> A good audit team MUST catch these.

### Ferrocene (metal_complex)
- **SMILES:** `[Fe+2].[cH-]1cccc1.[cH-]1cccc1`
- **Notes:** Sandwich complex; RDKit can parse but 3D embedding is unreliable
- SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)

### Cisplatin (metal_complex)
- **SMILES:** `[NH3][Pt]([NH3])(Cl)Cl`
- **Notes:** Square planar Pt(II), cis geometry crucial for activity
- SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)

### Hemoglobin Fe-porphyrin core (simplified) (metal_complex)
- **SMILES:** `[Fe+2]1(N2=CC3=CC4=CC(=CC5=CC(=CC1=C2C=C3)N5)N4)([NH3])[NH3]`
- **Notes:** Simplified iron porphyrin; may not parse correctly
- SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Simplified iron porphyrin; may not parse correctly)
- SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)

### Ruthenium tris-bipyridyl (metal_complex)
- **SMILES:** `[Ru+2].c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1`
- **Notes:** Photochemistry workhorse; disconnected fragments with metal ion
- SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)

### Osimertinib (large_drug)
- **SMILES:** `C=CC(=O)NC1=CC(=C(C=C1NC2=NC=CC(=N2)C3=CN(C=C3)C)OC)N(C)CCN(C)C`
- **Notes:** 3rd-gen EGFR inhibitor; acrylamide warhead (Michael acceptor)
- SILENT FAIL: Molecule has C=O but no IR peak in 1650-1800 cm-1 range

### tert-Butyl carbocation (reactive_intermediate)
- **SMILES:** `CC(C)[CH2+]`
- **Notes:** Tertiary carbocation; positive formal charge
- SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)

### Phenyl radical (SMILES approx) (reactive_intermediate)
- **SMILES:** `[CH2]c1ccccc1`
- **Notes:** Benzyl radical approximation; radical notation limited in SMILES
- SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)

### Dichlorocarbene (reactive_intermediate)
- **SMILES:** `Cl[C]Cl`
- **Notes:** Carbene: divalent carbon; extremely reactive
- SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)

### Phenyl nitrene (approx) (reactive_intermediate)
- **SMILES:** `[N]c1ccccc1`
- **Notes:** Nitrene: monovalent nitrogen; SMILES encoding is approximate
- SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)

### WRONG: Cyclopropyne (impossible ring strain) (intentionally_wrong)
- **SMILES:** `C1#CC1`
- **Notes:** Triple bond in 3-membered ring = impossible angle strain
- SILENT FAIL: Intentionally wrong molecule received ADMET profile without error

### WRONG: Anti-aromatic cyclobutadiene (forced) (intentionally_wrong)
- **SMILES:** `C1=CC=C1`
- **Notes:** 4pi anti-aromatic; extremely unstable; should be flagged
- SILENT FAIL: Intentionally wrong molecule received ADMET profile without error

### WRONG: Disconnected aspirin (meant to be bonded) (intentionally_wrong)
- **SMILES:** `CC(=O)O.c1ccccc1C(=O)O`
- **Notes:** Acetic acid + benzoic acid as separate fragments instead of aspirin ester
- SILENT FAIL: Intentionally wrong molecule received ADMET profile without error

## Detailed Results (All 50 Molecules)

### Bridged/Cage Structures

**Cubane**
- SMILES: `C12C3C4C1C5C3C4C25`
- Parse: [PASS] atoms=8, bonds=12, formula=?
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- 3D: [FAIL] EmbedMolecule returned -1 (UNEXPECTED: should have embedded)
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=104 LogP=1.0 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- Known issues: 3D embedding may fail due to strain; IR should show no C=C

**Norbornane (bicyclo[2.2.1]heptane)**
- SMILES: `C1CC2CC1CC2`
- Parse: [PASS] atoms=7, bonds=8, formula=?
- IR: [PASS] 10 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=96 LogP=2.2 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high

**2-Adamantanone**
- SMILES: `O=C1C2CC3CC1CC(C2)C3`
- Parse: [PASS] atoms=11, bonds=13, formula=?
- IR: [PASS] 11 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=150 LogP=2.0 HBD=0 HBA=1 violations=0; BBB=BBB+; MetStab=high

**Bicyclo[2.2.2]octane**
- SMILES: `C1CC2CCC1CC2`
- Parse: [PASS] atoms=8, bonds=9, formula=?
- IR: [PASS] 10 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=110 LogP=2.6 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high

**Spiro[4.5]decan-6-one**
- SMILES: `O=C1CCCCC12CCCC2`
- Parse: [PASS] atoms=11, bonds=12, formula=?
- IR: [PASS] 11 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=152 LogP=2.7 HBD=0 HBA=1 violations=0; BBB=BBB+; MetStab=high

### Metal Complexes

**Ferrocene**
- SMILES: `[Fe+2].[cH-]1cccc1.[cH-]1cccc1`
- Parse: [PASS] atoms=11, bonds=10, formula=?
- IR: [PASS] 10 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=186 LogP=2.8 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)
- Known issues: Metal complexes: 3D often fails, ADMET meaningless for organometallics

**Cisplatin**
- SMILES: `[NH3][Pt]([NH3])(Cl)Cl`
- Parse: [PASS] atoms=5, bonds=4, formula=?
- IR: [PASS] 5 peaks: 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region), 600cm-1(fingerprint region)
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Lead: [FAIL] 0 variants generated (molecule has atoms but no variants)
- ADMET: [PASS] Lipinski: MW=300 LogP=1.7 HBD=2 HBA=2 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)
- Known issues: RDKit 3D embedding unreliable for Pt; ADMET not designed for metals

**Hemoglobin Fe-porphyrin core (simplified)**
- SMILES: `[Fe+2]1(N2=CC3=CC4=CC(=CC5=CC(=CC1=C2C=C3)N5)N4)([NH3])[NH3]`
- Parse: [PASS] atoms=21, bonds=25, formula=?
- IR: [PASS] 10 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 1600cm-1(N-H bend), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region)
- 3D: [FAIL] EmbedMolecule returned -1
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=322 LogP=3.5 HBD=4 HBA=4 violations=0; BBB=uncertain; MetStab=high
- **SILENT FAILURES (2):**
  - SILENT FAIL: SMILES parsed OK but was EXPECTED to fail! (Simplified iron porphyrin; may not parse correctly)
  - SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)
- Known issues: Complex coordination chemistry; SMILES may be invalid

**Zinc phthalocyanine core**
- SMILES: `[Zn+2].c1cc2nc1cc1ccc(nc1cc1ccc([nH]c1cc1ccc(nc1cc1ccc2[nH]1)c1)c1)c1`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- 3D: [FAIL] Skipped (SMILES parse failed)
- Lead: [FAIL] Skipped (SMILES parse failed)
- ADMET: [FAIL] Error: Invalid SMILES: [Zn+2].c1cc2nc1cc1ccc(nc1cc1ccc([nH]c1cc1ccc(nc1cc1ccc2[nH]1)c1)c1)c1
- Known issues: Very large ring system with metal; 3D embedding almost certainly fails

**Ruthenium tris-bipyridyl**
- SMILES: `[Ru+2].c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1.c1ccnc(-c2ccccn2)c1`
- Parse: [PASS] atoms=37, bonds=39, formula=?
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1590cm-1(C=N ring str. (pyridine)), 1480cm-1(C=N ring str. (pyridine)), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=570 LogP=6.4 HBD=0 HBA=6 violations=2; BBB=BBB-; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Metal complex received normal ADMET profile (ADMET is meaningless for organometallics)
- Known issues: RDKit handles as disconnected fragments; ADMET meaningless

### Large Drugs

**Taxol (paclitaxel) core**
- SMILES: `CC1=C2C(C(=O)C3(C(CC4C(C3C(C(C2(C)C)(CC1OC(=O)C(C(C5=CC=CC=C5)NC(=O)C6=CC=CC=C6)O)O)OC(=O)C7=CC=CC=C7)(CO4)OC(=O)C)O)C)OC(=O)C`
- Parse: [PASS] atoms=62, bonds=68, formula=?
- IR: [PASS] 19 peaks: 3400cm-1(O-H str. (broad)), 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3))
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=854 LogP=3.7 HBD=4 HBA=14 violations=2; BBB=BBB-; MetStab=moderate

**Erythromycin A**
- SMILES: `CCC1C(C(C(C(=O)C(CC(C(C(C(C(C(=O)O1)C)OC2CC(C(C(O2)C)O)(C)OC)C)OC3C(C(CC(O3)C)N(C)C)O)(C)O)C)C)O)(C)O`
- Parse: [PASS] atoms=51, bonds=53, formula=?
- IR: [PASS] 14 peaks: 3400cm-1(O-H str. (broad)), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone)), 1460cm-1(C-H bend)
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=734 LogP=1.8 HBD=5 HBA=14 violations=2; BBB=BBB-; MetStab=high

**Vancomycin core (simplified)**
- SMILES: `CC1C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC1C(C(C2=CC(=C(C(=C2)Cl)OC3=CC=C(C=C3)C(C(=O)N)NC(=O)C4CC(=O)N4)O)Cl)O)CC5=CC=CC=C5)CC(=O)N)C(C)C)CC(=O)N)C(C)O`
- Parse: [PASS] atoms=78, bonds=82, formula=?
- IR: [PASS] 20 peaks: 3400cm-1(O-H str. (broad)), 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3))
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=1127 LogP=-2.4 HBD=14 HBA=15 violations=3; BBB=BBB-; MetStab=moderate

**Cyclosporin A fragment (linear)**
- SMILES: `CC1C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)NC(C(=O)N1C)CC2=CC=CC=C2)C(C)C)CC(C)C)C(C)C)CC(=O)O`
- Parse: [PASS] atoms=47, bonds=48, formula=?
- IR: [PASS] 18 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 2700cm-1(O-H str. (carboxylic))
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=659 LogP=0.3 HBD=6 HBA=7 violations=2; BBB=BBB-; MetStab=high

**Doxorubicin**
- SMILES: `CC1C(C(CC(O1)OC2CC(CC3=C2C(=C4C(=C3O)C(=O)C5=C(C4=O)C(=CC=C5)OC)O)(C(=O)CO)O)N)O`
- Parse: [PASS] atoms=39, bonds=43, formula=?
- IR: [PASS] 16 peaks: 3400cm-1(O-H str. (broad)), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=544 LogP=0.0 HBD=6 HBA=12 violations=3; BBB=BBB-; MetStab=high

**Sorafenib**
- SMILES: `CNC(=O)C1=CC(=C(C=C1)OC2=CC=C(C=C2)NC(=O)NC3=CC(=C(C=C3)Cl)C(F)(F)F)C`
- Parse: [PASS] atoms=33, bonds=35, formula=?
- IR: [PASS] 17 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1660cm-1(C=O str. (amide I))
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=478 LogP=6.5 HBD=3 HBA=3 violations=1; BBB=uncertain; MetStab=moderate

**Imatinib**
- SMILES: `CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5`
- Parse: [PASS] atoms=37, bonds=41, formula=?
- IR: [PASS] 16 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1660cm-1(C=O str. (amide I))
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=494 LogP=4.6 HBD=2 HBA=7 violations=0; BBB=uncertain; MetStab=moderate

**Osimertinib**
- SMILES: `C=CC(=O)NC1=CC(=C(C=C1NC2=NC=CC(=N2)C3=CN(C=C3)C)OC)N(C)CCN(C)C`
- Parse: [PASS] atoms=33, bonds=35, formula=?
- IR: [PASS] 17 peaks: 3350cm-1(N-H str.), 3080cm-1(=C-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1640cm-1(C=C str.)
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=450 LogP=3.4 HBD=2 HBA=7 violations=0; BBB=uncertain; MetStab=moderate
- **SILENT FAILURES (1):**
  - SILENT FAIL: Molecule has C=O but no IR peak in 1650-1800 cm-1 range

**Lenalidomide**
- SMILES: `C1CC(=O)NC(=O)C1N2CC3=CC=CC=C3C2=O`
- Parse: [PASS] atoms=18, bonds=20, formula=?
- IR: [PASS] 17 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=244 LogP=0.4 HBD=1 HBA=3 violations=0; BBB=BBB+; MetStab=high

**Bortezomib**
- SMILES: `CC(C)CC(NC(=O)C(CC1=CC=CC=C1)NC(=O)C2=NC=CN=C2)B(O)O`
- Parse: [PASS] atoms=28, bonds=29, formula=?
- IR: [PASS] 17 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + UFF optimized (MMFF failed)
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=384 LogP=0.4 HBD=4 HBA=6 violations=0; BBB=BBB-; MetStab=high

### Stereochemistry Challenges

**(R)-Thalidomide vs (S)-Thalidomide (R-form)**
- SMILES: `O=C1CC[C@H](N1C2=CC=CC=C2C(=O)O)C(=O)O`
- Parse: [PASS] atoms=18, bonds=19, formula=?
- IR: [PASS] 18 peaks: 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 2700cm-1(O-H str. (carboxylic)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=249 LogP=1.0 HBD=2 HBA=3 violations=0; BBB=BBB+; MetStab=high
- Known issues: If chirality is lost in processing, this is a CRITICAL silent failure

**Meso-tartaric acid**
- SMILES: `OC(=O)[C@H](O)[C@@H](O)C(=O)O`
- Parse: [PASS] atoms=10, bonds=9, formula=?
- IR: [PASS] 13 peaks: 3400cm-1(O-H str. (broad)), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 2700cm-1(O-H str. (carboxylic)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=150 LogP=-2.1 HBD=4 HBA=4 violations=0; BBB=BBB-; MetStab=high
- Known issues: System should recognize this as achiral despite having stereocenters

**BINAP (axial chirality)**
- SMILES: `C1=CC=C(C2=C1C3=CC=CC=C3C=C2P(C4=CC=CC=C4)C5=CC=CC=C5)C6=CC=CC7=CC=CC=C76`
- Parse: [PASS] atoms=37, bonds=43, formula=?
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=489 LogP=8.6 HBD=0 HBA=0 violations=1; BBB=uncertain; MetStab=high
- Known issues: Axial chirality cannot be encoded in standard SMILES; system may not flag this

**cis-Decalin**
- SMILES: `C1CCC2CCCCC2C1`
- Parse: [PASS] atoms=10, bonds=11, formula=?
- IR: [PASS] 10 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=138 LogP=3.4 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- Known issues: Without explicit stereo, 3D may generate either isomer randomly

**(S)-Ibuprofen**
- SMILES: `CC(C)Cc1ccc([C@H](C)C(=O)O)cc1`
- Parse: [PASS] atoms=15, bonds=15, formula=?
- IR: [PASS] 14 peaks: 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 2700cm-1(O-H str. (carboxylic)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=206 LogP=3.1 HBD=1 HBA=1 violations=0; BBB=BBB+; MetStab=high
- Known issues: Lead optimizer must preserve stereochemistry in variants

### Reactive Intermediates

**tert-Butyl carbocation**
- SMILES: `CC(C)[CH2+]`
- Parse: [PASS] atoms=4, bonds=3, formula=?
- IR: [PASS] 11 peaks: 3080cm-1(=C-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=57 LogP=1.5 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)
- Known issues: Charged species; ADMET makes no physical sense; should warn

**Triphenylmethyl carbanion**
- SMILES: `[CH-](c1ccccc1)(c1ccccc1)c1ccccc1`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- 3D: [FAIL] Skipped (SMILES parse failed)
- Lead: [FAIL] Skipped (SMILES parse failed)
- ADMET: [FAIL] Error: Invalid SMILES: [CH-](c1ccccc1)(c1ccccc1)c1ccccc1
- Known issues: Charged species; ADMET/drug properties meaningless

**Phenyl radical (SMILES approx)**
- SMILES: `[CH2]c1ccccc1`
- Parse: [PASS] atoms=7, bonds=7, formula=?
- IR: [PASS] 12 peaks: 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=91 LogP=1.9 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)
- Known issues: Standard SMILES cannot represent radicals properly; silent misparse likely

**Dichlorocarbene**
- SMILES: `Cl[C]Cl`
- Parse: [PASS] atoms=3, bonds=2, formula=?
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [FAIL] 0 variants generated
- ADMET: [PASS] Lipinski: MW=83 LogP=1.5 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)
- Known issues: RDKit may reject or misinterpret divalent carbon

**Phenyl nitrene (approx)**
- SMILES: `[N]c1ccccc1`
- Parse: [PASS] atoms=7, bonds=7, formula=?
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1600cm-1(C=C ring str.), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=91 LogP=1.4 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Reactive intermediate passed Lipinski (reactive species are not viable drugs)
- Known issues: Monovalent N unusual; RDKit may add implicit H or reject

### Heterocyclic Fused

**Acridine**
- SMILES: `c1ccc2nc3ccccc3cc2c1`
- Parse: [PASS] atoms=14, bonds=16, formula=?
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1590cm-1(C=N ring str. (pyridine)), 1480cm-1(C=N ring str. (pyridine)), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=179 LogP=3.4 HBD=0 HBA=1 violations=0; BBB=BBB+; MetStab=high

**Phenothiazine**
- SMILES: `c1ccc2c(c1)Sc1ccccc1N2`
- Parse: [PASS] atoms=14, bonds=16, formula=?
- IR: [PASS] 10 peaks: 3350cm-1(N-H str.), 3070cm-1(Ar-H str.), 1600cm-1(N-H bend), 1500cm-1(C=C ring str.), 1350cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=199 LogP=3.9 HBD=1 HBA=2 violations=0; BBB=BBB+; MetStab=high

**Benzimidazole-fused pyridine (1H-imidazo[4,5-b]pyridine)**
- SMILES: `c1cc2[nH]cnc2nc1`
- Parse: [PASS] atoms=9, bonds=10, formula=?
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1590cm-1(C=N ring str. (pyridine)), 1480cm-1(C=N ring str. (pyridine)), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=119 LogP=1.0 HBD=1 HBA=2 violations=0; BBB=BBB+; MetStab=high

**Pteridine**
- SMILES: `c1cnc2nccnc2n1`
- Parse: [PASS] atoms=10, bonds=11, formula=?
- IR: [PASS] 9 peaks: 3070cm-1(Ar-H str.), 1590cm-1(C=N ring str. (pyridine)), 1480cm-1(C=N ring str. (pyridine)), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=132 LogP=0.4 HBD=0 HBA=4 violations=0; BBB=BBB+; MetStab=high

**Free-base porphyrin**
- SMILES: `c1cc2cc3ccc([nH]3)cc3ccc([nH]3)cc3ccc(n3)cc3ccc1n3`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- 3D: [FAIL] Skipped (SMILES parse failed)
- Lead: [FAIL] Skipped (SMILES parse failed)
- ADMET: [FAIL] Error: Invalid SMILES: c1cc2cc3ccc([nH]3)cc3ccc([nH]3)cc3ccc(n3)cc3ccc1n3
- Known issues: Large macrocycle; 3D embedding may fail or produce poor geometry

### Natural Products

**Camphor**
- SMILES: `CC1(C)C2CCC1(C)C(=O)C2`
- Parse: [PASS] atoms=11, bonds=12, formula=?
- IR: [PASS] 11 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=152 LogP=2.4 HBD=0 HBA=1 violations=0; BBB=BBB+; MetStab=high

**(-)-Menthol**
- SMILES: `C[C@@H]1CC[C@H]([C@@H](C1)O)C(C)C`
- Parse: [PASS] atoms=11, bonds=11, formula=?
- IR: [PASS] 12 peaks: 3400cm-1(O-H str. (broad)), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=156 LogP=2.4 HBD=1 HBA=1 violations=0; BBB=BBB+; MetStab=high

**(R)-Limonene**
- SMILES: `C=C(C)[C@@H]1CC=C(C)CC1`
- Parse: [PASS] atoms=10, bonds=10, formula=?
- IR: [PASS] 13 peaks: 3080cm-1(=C-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1640cm-1(C=C str.), 1460cm-1(C-H bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=136 LogP=3.3 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high

**Artemisinin core**
- SMILES: `CC1CCC2C(C)C(OO3)OC3(O2)C1CC(C)=O`
- Parse: [PASS] atoms=18, bonds=20, formula=?
- IR: [PASS] 11 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1715cm-1(C=O str. (ketone)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=256 LogP=2.0 HBD=0 HBA=5 violations=0; BBB=BBB+; MetStab=high
- Known issues: Peroxide bond unusual; may affect IR predictions

**Quinine**
- SMILES: `COC1=CC2=C(C=CN=C2C=C1)[C@@H](O)[C@H]1CC2CCN1CC2C=C`
- Parse: [PASS] atoms=24, bonds=27, formula=?
- IR: [PASS] 17 peaks: 3400cm-1(O-H str. (broad)), 3080cm-1(=C-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1640cm-1(C=C str.)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=324 LogP=3.2 HBD=1 HBA=4 violations=0; BBB=BBB+; MetStab=high

### Intentionally Wrong

**WRONG: Pentavalent carbon**
- SMILES: `C(C)(C)(C)(C)C`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- 3D: [FAIL] Skipped (SMILES parse failed)
- Lead: [FAIL] Skipped (SMILES parse failed)
- ADMET: [FAIL] Error: Invalid SMILES: C(C)(C)(C)(C)C
- Known issues: If RDKit accepts this, it is a CRITICAL validation failure

**WRONG: Cyclopropyne (impossible ring strain)**
- SMILES: `C1#CC1`
- Parse: [PASS] atoms=3, bonds=3, formula=?
- IR: [PASS] 10 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 2100cm-1(C≡C str.), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend)
- 3D: [FAIL] EmbedMolecule returned -1 (UNEXPECTED: should have embedded)
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=38 LogP=0.4 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Intentionally wrong molecule received ADMET profile without error
- Known issues: RDKit may accept this; a GOOD audit catches that it is chemically impossible

**WRONG: Anti-aromatic cyclobutadiene (forced)**
- SMILES: `C1=CC=C1`
- Parse: [PASS] atoms=4, bonds=4, formula=?
- IR: [PASS] 8 peaks: 3080cm-1(=C-H str.), 1640cm-1(C=C str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=52 LogP=1.1 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Intentionally wrong molecule received ADMET profile without error
- Known issues: Parses fine but is anti-aromatic and chemically unstable; good audit flags it

**WRONG: Nitrogen with impossible charge state**
- SMILES: `[N+5](=O)(=O)(=O)(=O)=O`
- Parse: [FAIL] MolFromSmiles returned None
- IR: [FAIL] No IR peaks returned
- 3D: [FAIL] Skipped (SMILES parse failed)
- Lead: [FAIL] Skipped (SMILES parse failed)
- ADMET: [FAIL] Error: Invalid SMILES: [N+5](=O)(=O)(=O)(=O)=O
- Known issues: Chemically impossible; must be rejected

**WRONG: Disconnected aspirin (meant to be bonded)**
- SMILES: `CC(=O)O.c1ccccc1C(=O)O`
- Parse: [PASS] atoms=13, bonds=12, formula=?
- IR: [PASS] 14 peaks: 3070cm-1(Ar-H str.), 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 2700cm-1(O-H str. (carboxylic)), 1715cm-1(C=O str. (ketone))
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=182 LogP=1.5 HBD=2 HBA=2 violations=0; BBB=BBB+; MetStab=high
- **SILENT FAILURES (1):**
  - SILENT FAIL: Intentionally wrong molecule received ADMET profile without error
- Known issues: Parses as 2 valid fragments; audit should catch it is NOT aspirin but disconnected pieces

### Edge Cases

**Triacontane (C30 linear alkane)**
- SMILES: `CCCCCCCCCCCCCCCCCCCCCCCCCCCCCC`
- Parse: [PASS] atoms=30, bonds=29, formula=?
- IR: [PASS] 9 peaks: 2960cm-1(C-H str. (sp3)), 2870cm-1(C-H str. (sp3)), 1460cm-1(C-H bend), 1380cm-1(C-H sym. bend), 1350cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF converged with issues
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=423 LogP=11.9 HBD=0 HBA=0 violations=1; BBB=uncertain; MetStab=moderate

**Buckminsterfullerene C60**
- SMILES: `c12c3c4c5c1c1c6c7c8c2c2c9c%10c3c3c%11c4c4c%12c%13c5c5c1c1c6c6c%14c7c7c%15c8c2c2c9c8c9c%10c3c3c%11c%10c4c4c%12c%11c%12c%13c5c5c1c1c6c%14c6c7c%15c2c2c8c7c9c3c%10c3c4c%11c%12c5c1c6c2c7c3`
- Parse: [FAIL] MolFromSmiles returned None (UNEXPECTED: should have parsed)
- IR: [FAIL] No IR peaks returned
- 3D: [FAIL] Skipped (SMILES parse failed)
- Lead: [FAIL] Skipped (SMILES parse failed)
- ADMET: [FAIL] Error: Invalid SMILES: c12c3c4c5c1c1c6c7c8c2c2c9c%10c3c3c%11c4c4c%12c%13c5c5c1c1c6c6c%14c7c7c%15c8c2c2c9c8c9c%10c3c3c%11c%10c4c4c%12c%11c%12c%13c5c5c1c1c6c%14c6c7c%15c2c2c8c7c9c3c%10c3c4c%11c%12c5c1c6c2c7c3
- Known issues: Extremely complex topology; 3D embedding almost always fails

**1,2-Propadiene (allene)**
- SMILES: `C=C=C`
- Parse: [PASS] atoms=3, bonds=2, formula=?
- IR: [PASS] 7 peaks: 3080cm-1(=C-H str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=40 LogP=1.0 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high

**1,2,3-Butatriene (cumulene)**
- SMILES: `C=C=C=C`
- Parse: [PASS] atoms=4, bonds=3, formula=?
- IR: [PASS] 7 peaks: 3080cm-1(=C-H str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=52 LogP=1.1 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high

**1,3,5,7-Octatetrayne (polyyne)**
- SMILES: `C#CC#CC#CC#C`
- Parse: [PASS] atoms=8, bonds=7, formula=?
- IR: [PASS] 6 peaks: 2100cm-1(C≡C str.), 1350cm-1(fingerprint region), 1250cm-1(fingerprint region), 1100cm-1(fingerprint region), 900cm-1(fingerprint region)
- 3D: [PASS] Embedded + MMFF optimized
- Lead: [PASS] 5 variants generated
- ADMET: [PASS] Lipinski: MW=98 LogP=0.3 HBD=0 HBA=0 violations=0; BBB=BBB+; MetStab=high

## Audit Team Scoring Guide

A good audit team should catch the following:
1. **Intentionally wrong molecules that silently pass** - If the system accepts pentavalent carbon or cyclopropyne without complaint, the validation is broken.
2. **Metal complexes getting meaningful ADMET scores** - ADMET models are trained on organic drug molecules; applying them to ferrocene or cisplatin is scientifically meaningless.
3. **Reactive intermediates passing Lipinski** - Carbocations and radicals are not viable drug candidates.
4. **Missing IR peaks for obvious functional groups** - If a ketone has no C=O stretch, the spectrum predictor has a bug.
5. **Generated variants identical to parent** - Lead optimizer producing duplicates is wasteful at best, misleading at worst.
6. **Disconnected fragments treated as valid molecules** - The 'wrong aspirin' test checks if the system distinguishes bonded vs disconnected structures.

**Total silent failures found: 13**

**VERDICT: HIGH number of silent failures. Audit teams have SIGNIFICANT work to do.**