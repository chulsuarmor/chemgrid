# domain_drug Task Checklist

## [2026-03-19] ADMET Chemical Plausibility Pre-filter
- [x] Read admet_predictor.py and understand current flow
- [x] Add `_validate_molecule_type()` function (6 checks: metal, radical, charge, fragments, ring strain, anti-aromatic)
- [x] Add `is_organic` field to ADMETProfile dataclass
- [x] Integrate validation call in `predict_admet()` after mol parsing
- [x] Fix bug: existing `profile.warnings = warnings` was overwriting pre-filter warnings
- [x] py_compile pass
- [x] Smoke test: 8 test cases (aspirin, Fe, NaCl, methylene radical, cisplatin, benzene, caffeine, dict serialization)
- [x] Copy to `_source/`
- [x] Update mistakes.md
