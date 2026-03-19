# Cascade #8 Task 3: Synthesis Domain Test Evidence
> Date: 2026-03-19
> Author: MM-SYNTHESIS Worker
> Python: 3.12.12 (chemgrid conda env)

---

## PART 1: PDF Export Test (5 molecules)

| Molecule | SMILES | Routes Found | Best Route Steps | PDF Size | Result |
|----------|--------|-------------|-----------------|----------|--------|
| Aspirin | CC(=O)Oc1ccccc1C(=O)O | 3 | 1 step (score=-23.00) | 38,775 B | PASS |
| Caffeine | Cn1cnc2c1c(=O)n(C)c(=O)n2C | 3 | 3 steps (score=15.00) | 62,407 B | PASS |
| Ibuprofen | CC(C)Cc1ccc(C(C)C(=O)O)cc1 | 2 | 2 steps (score=-18.00) | 42,614 B | PASS |
| Phenol | Oc1ccccc1 | 2 | 0 steps (building block) | N/A | EXPECTED (BB) |
| Aniline | Nc1ccccc1 | 2 | 0 steps (building block) | N/A | EXPECTED (BB) |

### PDF Files Generated
- `test_aspirin_route.pdf` (38,775 bytes) -- 1-step: Salicylic acid + Acetaldehyde -> Aspirin
- `test_caffeine_route.pdf` (62,407 bytes) -- 3-step: Triple N-methylation of xanthine core
- `test_ibuprofen_route.pdf` (42,614 bytes) -- 2-step: Toluene + Propionic acid + Propane -> Ibuprofen

### Phenol/Aniline Note
Phenol and Aniline are registered building blocks in `building_blocks.py`, so the retrosynthesis engine correctly returns 0-step routes (they are commercially available starting materials). The PDF exporter correctly rejects empty routes at line 180 (`if not route or not route.steps`). This is **expected behavior**, not a bug.

### PDF Quality Observations
- All 3 exported PDFs exceed 10KB threshold
- Molecule 2D structure images render correctly via RDKit
- Reaction arrows with conditions text display properly
- Korean font (malgun.ttf) registered successfully for Korean labels
- Snake (serpentine) layout works for multi-step routes (Caffeine 3-step)

---

## PART 2: Mechanism Engine Accuracy Test

### Test 2a: SN2 (Bromoethane -> Ethanol)
- **Reactants**: CCBr + [OH-]
- **Products**: CCO + [Br-]
- **Mechanism type**: `sn2` (gold standard hardcoded)
- **Steps**: 1
- **Arrows**: 2
  1. OH- lone pair -> C (delta+) [full arrow]
  2. C-Br bond -> Br (leaving group) [full arrow]
- **Chemistry accuracy**: CORRECT -- SN2 is a concerted mechanism with simultaneous backside attack by nucleophile (OH-) and departure of leaving group (Br-). Two arrows is the standard representation.
- **Result**: PASS

### Test 2b: EAS (Benzene + Br2 -> Bromobenzene)
- **Reactants**: c1ccccc1 + BrBr
- **Products**: Brc1ccccc1
- **Mechanism type**: `auto_generated` (no gold standard for EAS bromination)
- **Steps**: 1
- **Arrows**: 2
  1. Br-Br sigma bond -> Br (electron pair acceptor) [full arrow]
  2. Br (incoming) -> C (reaction center) [full arrow]
- **Chemistry accuracy**: PARTIAL -- The auto-generated mechanism captures the key bond changes (Br-Br breaking, C-Br forming) but simplifies the 3-step EAS mechanism (sigma complex formation, proton loss) into a single concerted step. For educational accuracy, a gold standard EAS mechanism with sigma complex intermediate would be preferable.
- **Known limitation**: No hardcoded EAS bromination mechanism in `reaction_mechanisms.py`. Recommend adding gold standard EAS mechanism.
- **Result**: PASS (functional), PARTIAL (educational accuracy)

### Test 2c: Ester Hydrolysis (Aspirin Decomposition)
- **Reactants**: CC(=O)Oc1ccccc1C(=O)O + H2O
- **Products**: Oc1ccccc1C(=O)O + CH3COOH
- **Mechanism type**: `auto_generated`
- **Steps**: 1
- **Arrows**: 2
  1. O lone pair -> C (electrophilic center) [full arrow]
  2. C-O sigma bond -> O (electron pair acceptor) [full arrow]
- **Chemistry accuracy**: PARTIAL -- Captures the key bond changes (nucleophilic addition of water, C-O ester bond cleavage) but real acid/base-catalyzed ester hydrolysis is multi-step (tetrahedral intermediate). Auto-generation collapses this to a single step.
- **Known limitation**: No hardcoded ester hydrolysis mechanism. Recommend adding gold standard.
- **Result**: PASS (functional), PARTIAL (educational accuracy)

### Test 2d: auto_mechanism() Convenience Function
- **Input**: CCBr + [OH-] -> CCO + [Br-]
- **Result**: OK (1 step, 2 arrows)
- Same output as direct MechanismEngine.generate_mechanism() call

---

## PART 3: py_compile Verification

| File | Result |
|------|--------|
| retrosynthesis_engine.py | PASS |
| mechanism_engine.py | PASS |
| building_blocks.py | PASS |
| popup_synthesis.py | PASS |
| reaction_mechanisms.py | PASS |
| arrow_generator.py | PASS |
| mechanism_pdf_exporter.py | PASS |

All 7 OWNED_FILES pass py_compile without errors.

---

## SUMMARY

| Category | Result | Details |
|----------|--------|---------|
| PDF Export | 3/3 PASS | Aspirin, Caffeine, Ibuprofen (>10KB each) |
| PDF Export (BB) | 2/2 EXPECTED | Phenol, Aniline are building blocks (no synthesis needed) |
| SN2 Mechanism | PASS | Gold standard, 2 arrows, chemically correct |
| EAS Mechanism | PASS (functional) | Auto-generated, simplified from 3-step to 1-step |
| Ester Hydrolysis | PASS (functional) | Auto-generated, simplified from multi-step to 1-step |
| py_compile | 7/7 PASS | All OWNED_FILES compile cleanly |

### Recommendations for Future Cascades
1. Add gold standard EAS bromination mechanism to `reaction_mechanisms.py`
2. Add gold standard ester hydrolysis mechanism to `reaction_mechanisms.py`
3. Consider adding a "building block report" PDF export option for molecules that are already starting materials
