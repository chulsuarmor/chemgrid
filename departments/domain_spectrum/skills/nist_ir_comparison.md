# Skill: NIST IR Comparison Methodology

## When to use
When validating predicted IR peak positions against NIST standard reference data.

## Procedure
1. Run `predict_ir(smiles)` to get current predicted peaks
2. Identify the molecule's point group symmetry (determines IR vs Raman activity)
3. Look up NIST WebBook fundamentals at https://webbook.nist.gov/
4. For each predicted peak, find the closest NIST IR-active mode (u symmetry for centrosymmetric molecules)
5. Calculate delta = predicted - NIST. Tolerance: +/-30 cm-1 per Reviewer checklist
6. Note: Only compare specifically-assigned peaks (not generic fingerprint region peaks)

## Benzene Reference (D6h symmetry)
Key IR-active fundamentals:
- 3068 cm-1 (v5, b1u): C-H stretch
- 3063 cm-1 (v12, e1u): C-H stretch
- 1486 cm-1 (v13, e1u): ring stretch + deformation
- 1038 cm-1 (v14, e1u): C-H in-plane bend
- 673 cm-1 (v4, b1u): C-H out-of-plane bend (strongest)
- 703 cm-1 (v8, b2u): ring deformation
- 1310 cm-1 (v9, b2u): ring stretch
- 1150 cm-1 (v10, b2u): C-H in-plane bend

## Gotchas
- v16 (1596 cm-1) is e2g = Raman-only for pure benzene. Do NOT flag 1600 cm-1 as wrong in general predictor context.
- The dedup window in predict_ir is +/-50 cm-1 which can merge distinct NIST peaks (e.g., v4=673 and v8=703). This is by design for simplified output.
- Fingerprint region peaks (added as baseline) are generic and should NOT be compared 1:1 against NIST fundamentals.

## Source
NIST Chemistry WebBook (https://webbook.nist.gov/cgi/cbook.cgi?ID=C71432)
VPL Molecular Spectroscopy (https://vpl.astro.washington.edu/spectra/c6h6.htm)
