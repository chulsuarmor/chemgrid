# domain_test - Task Checklist
## Last Updated: 2026-03-19

### Cascade #8 Task 4: Regression Test
- [x] py_compile all 67 src/app/*.py (67/67 PASS)
- [x] py_compile all 9 src/app/tests/*.py (9/9 PASS)
- [x] Run test_visual_auto.py (30/30 PASS, 3 ERR)
- [x] Run test_visual_3d.py (0/0 PASS, 11 ERR)
- [x] Compare with 03-18 baseline (regression found: 3d_popup)
- [x] Write evidence to evidence/cascade8_regression_20260319.md
- [x] Update context documents

### Blockers (owned by other domains):
- [ ] **P0**: popup_3d.py `_create_alphafold_synthesis_tab` in wrong class (blocks ALL 3D tests)
- [ ] **P1**: popup_docking.py `currentRowChanged` signal does not exist on QTableWidget
- [ ] **P1**: popup_admet.py `Descriptors.MolecularFormula` not in RDKit Descriptors module
