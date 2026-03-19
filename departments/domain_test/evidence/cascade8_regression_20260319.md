# Cascade #8 Regression Test Evidence
## Date: 2026-03-19
## Executor: MM-TEST (Worker)

---

## 1. py_compile Results

**67/67 PASS** (src/app/*.py)
**9/9 PASS** (src/app/tests/*.py)
**Total: 76/76 PASS** -- Zero syntax errors.

---

## 2. test_visual_auto.py Results

**30/30 PASS, 0 FAIL, 3 ERRORS**
Duration: 7.7s

### Passing Tests (30):
- 01_initial_empty, 02_text_input_typed
- 03_benzene_drawn, 03_benzene_theory, 03_benzene_lewis
- 03_benzene_resonance, 03_analysis_persistence
- Predicted spectrum popups: ir, raman, nmr_h, nmr_c13, uv_vis
- 06_reaction_popup, 07_synthesis_popup
- 10_drug_screening, 11_alphafold_popup
- PDF export, manual draw tests, etc.

### Errors (3):
1. **[3d_popup] -- REGRESSION (NEW)**
   - `popup_3d.py:7537`: `Molecule3DPopup._init_ui()` calls `self._create_alphafold_synthesis_tab()` but this method is defined in `DockingEnergyPanel` (line 7025), not in `Molecule3DPopup`.
   - Root cause: Method placed in wrong class during recent refactoring.
   - Impact: Blocks 3D popup creation, ~14 sub-tests that depended on it now skipped (44 passed on 03-18 vs 30 on 03-19).

2. **[docking_popup] -- PRE-EXISTING (same as 03-18)**
   - `popup_docking.py`: `'QTableWidget' object has no attribute 'currentRowChanged'`
   - `QTableWidget` uses `currentCellChanged` signal, not `currentRowChanged`.

3. **[admet] -- PRE-EXISTING (same as 03-18)**
   - `popup_admet.py:352`: `Descriptors.MolecularFormula(self._mol)` -- `MolecularFormula` is not in `rdkit.Chem.Descriptors`. Should use `rdMolDescriptors.CalcMolFormula()`.

### Regression Comparison (03-18 vs 03-19):
| Metric         | 03-18 | 03-19 | Delta |
|----------------|-------|-------|-------|
| PASS           | 44    | 30    | -14   |
| FAIL           | 0     | 0     | 0     |
| ERRORS         | 2     | 3     | +1    |
| New regression | --    | 3d_popup | +1 |

---

## 3. test_visual_3d.py Results

**0/0 PASS, 11 ERRORS**
Duration: 3.8s

All 11 test cases failed with the same root cause:
- `Molecule3DPopup.__init__` -> `_init_ui()` -> calls `self._create_alphafold_synthesis_tab()` which does not exist on `Molecule3DPopup`.
- `AttributeError: 'Molecule3DPopup' object has no attribute '_create_alphafold_synthesis_tab'`

### Failed Tests:
- A: 3D_benzene, 3D_aspirin, 3D_ferrocene
- B: orbital_benzene_pi, orbital_benzene_hybrid, orbital_benzene_all, orbital_ethanol_hybrid, orbital_ferrocene_d_orbital
- B2: orbital_comparison
- C: docking
- D: spectrum_tabs

---

## 4. Blocker Summary for CT

### P0 - Regression (requires immediate fix by domain_3d or domain_chem):
- **popup_3d.py**: `_create_alphafold_synthesis_tab` method must be moved/copied from `DockingEnergyPanel` to `Molecule3DPopup`, or the call at line 7537 must reference the correct location.

### P1 - Pre-existing (requires fix by respective domains):
- **popup_docking.py**: Replace `currentRowChanged` with correct QTableWidget signal.
- **popup_admet.py**: Replace `Descriptors.MolecularFormula()` with `rdMolDescriptors.CalcMolFormula()`.

---

## 5. Note on Encoding
- `test_visual_auto.py` crashes with `UnicodeEncodeError: 'cp949'` unless `PYTHONIOENCODING=utf-8` is set. This is a Windows Korean locale issue. Consider adding `PYTHONIOENCODING=utf-8` to `Run_ChemGrid.bat` or the test runner.

---

## Evidence Locations
- test_visual_auto screenshots: `departments/archive/screenshots/visual_qa_20260319/`
- test_visual_auto HTML report: `departments/archive/screenshots/visual_qa_20260319/report.html`
- test_visual_3d screenshots: `departments/archive/screenshots/3d_audit_20260319/`
- test_visual_3d HTML report: `departments/archive/screenshots/3d_audit_20260319/report.html`
