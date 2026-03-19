# domain_test - Technical Notes
## Last Updated: 2026-03-19

### Cascade #8 Regression Analysis

#### 1. 3D Popup Regression (NEW - P0)
- `popup_3d.py` line 7537: `Molecule3DPopup._init_ui()` calls `self._create_alphafold_synthesis_tab()`
- This method is defined at line 7025 inside class `DockingEnergyPanel`, NOT `Molecule3DPopup`
- Root cause: method placed in wrong class during refactoring
- Impact: ALL 3D-related tests fail (11 in test_visual_3d, ~14 sub-tests blocked in test_visual_auto)
- Fix: Move/copy `_create_alphafold_synthesis_tab` (lines 7025-7314) into `Molecule3DPopup` class

#### 2. DockingPopup Error (PRE-EXISTING)
- `popup_docking.py`: `QTableWidget` does not have `currentRowChanged` signal
- Should use `currentCellChanged` or `QTableWidget.selectionModel().currentRowChanged`

#### 3. ADMETPopup Error (PRE-EXISTING)
- `popup_admet.py` line 352: `Descriptors.MolecularFormula(self._mol)`
- `MolecularFormula` is not an attribute of `rdkit.Chem.Descriptors`
- Correct API: `from rdkit.Chem import rdMolDescriptors; rdMolDescriptors.CalcMolFormula(mol)`

#### 4. Windows cp949 Encoding
- test_visual_auto.py print statements contain em-dash (U+2014) and other Unicode
- Crashes with `UnicodeEncodeError: 'cp949'` on Korean Windows unless PYTHONIOENCODING=utf-8
- Workaround: set env var before running tests
