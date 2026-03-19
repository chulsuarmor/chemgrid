# domain_synthesis Context List
## Cascade #8 Task 3 (2026-03-19)

### PDF Export Testing
- [x] Aspirin (CC(=O)Oc1ccccc1C(=O)O) -- 38,775B PDF, 1-step route
- [x] Caffeine (Cn1cnc2c1c(=O)n(C)c(=O)n2C) -- 62,407B PDF, 3-step route
- [x] Ibuprofen (CC(C)Cc1ccc(C(C)C(=O)O)cc1) -- 42,614B PDF, 2-step route
- [x] Phenol (Oc1ccccc1) -- Building block, no synthesis needed (expected)
- [x] Aniline (Nc1ccccc1) -- Building block, no synthesis needed (expected)

### Mechanism Engine Testing
- [x] SN2: CCBr + [OH-] -> CCO + [Br-] -- PASS (gold standard, 2 arrows)
- [x] EAS: benzene + Br2 -> bromobenzene -- PASS (auto-generated, 2 arrows, simplified)
- [x] Ester Hydrolysis: aspirin + H2O -> salicylic acid + acetic acid -- PASS (auto-generated, 2 arrows)

### py_compile
- [x] All 7 OWNED_FILES pass

### Blockers
- None

### TODO (future cascades)
- [ ] Add gold standard EAS bromination mechanism to reaction_mechanisms.py
- [ ] Add gold standard ester hydrolysis mechanism to reaction_mechanisms.py
- [ ] Consider "building block info" PDF for molecules already in DB
