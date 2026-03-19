# domain_spectrum Mistakes Log

## [2026-03-19] Circulation Test: No code fix needed
- **Situation:** Benzene IR peaks compared against NIST WebBook fundamentals
- **Finding:** All functional-group peaks within +/-30 cm-1 tolerance. No mistakes to correct.
- **Note for future:** The 1600 cm-1 aromatic peak is Raman-active only for pure benzene (e2g symmetry). This is acceptable in a general predictor because substituted benzenes break the mutual exclusion rule and practical IR tables (Silverstein) list it. If a future task requires strict symmetry-aware selection rules, this would need to be gated behind an `is_centrosymmetric` check.
