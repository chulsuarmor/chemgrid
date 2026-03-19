# AO-LINK Mistakes Log

## [2026-03-19] LeadOptimizerPopup parameter name mismatch
- **Location:** `main_window.py:2499`, `popup_3d.py:8009`
- **Bug:** Both call `LeadOptimizerPopup(initial_smiles=...)` but the constructor expects `smiles=`
- **Impact:** Clicking "리드 최적화" from toolbar or 3D popup drug design tab will crash with TypeError
- **Fix needed:** Change `initial_smiles=smiles` to `smiles=smiles` in both files
