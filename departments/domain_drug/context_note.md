# domain_drug Technical Notes

## [2026-03-19] ADMET Pre-filter Design Decisions

### _validate_molecule_type() — 6-check gate
1. **Metal detection**: Checks atom symbols against `_ORGANIC_ELEMENTS` set (C,H,N,O,S,P,F,Cl,Br,I,B,Si,Se). Only reports first non-organic element found.
2. **Radical detection**: `atom.GetNumRadicalElectrons() > 0`. Catches carbenes, radicals.
3. **High charge**: `sum(abs(formal_charge))` > 2 flags ionic species unsuitable for oral drugs.
4. **Disconnected fragments**: `GetMolFrags()` length > 1 catches salts and mixtures.
5. **Impossible ring strain**: Triple bonds in 3-4 membered rings (e.g., cyclopropyne).
6. **Anti-aromatic**: 4-membered fully-SP2 rings (4n pi electron systems).

### Key bug found and fixed
The original code at line ~556 used `warnings = []` then `profile.warnings = warnings`, which **overwrote** any previously-stored warnings. Changed to direct `.append()` calls on `profile.warnings` to preserve pre-filter warnings.

### is_organic field
Added `is_organic: bool = True` to ADMETProfile. Set to False when any non-organic element detected. Exposed in `admet_to_dict()` for downstream consumers.

### Test coverage
Tested with: aspirin (clean organic), [Fe] (metal), [Na+].[Cl-] (metal+fragments), [CH2] (radical), cisplatin (Pt complex), benzene (simple organic), caffeine (complex organic). All pass.
