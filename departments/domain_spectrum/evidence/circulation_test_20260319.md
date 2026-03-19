# Circulation Test: Benzene IR Spectrum vs NIST
## Date: 2026-03-19
## Agent: MM-SPECTRUM (Worker mode)

---

## 1. Skills Read (Pre-work)
- Read `departments/domain_spectrum/CLAUDE.md` -- confirmed OWNED_FILES, Worker obligations
- Checked `departments/domain_spectrum/skills/` -- directory empty (no prior skills)
- Checked `departments/domain_spectrum/mistakes.md` -- file did not exist (no prior mistakes)
- Key domain knowledge from CLAUDE.md skills section:
  - SMARTS pattern matching requires None check
  - IR tolerance: +/-30 cm-1 (Silverstein/Pavia standard)

---

## 2. Current Predicted Peaks (predict_ir('c1ccccc1'))

| # | Wavenumber (cm-1) | Assignment | T% | Width |
|---|---|---|---|---|
| 1 | 3070 | Ar-H str. | 45% | 20 |
| 2 | 1600 | C=C ring str. | 55% | 30 |
| 3 | 1500 | C=C ring str. | 55% | 25 |
| 4 | 1350 | fingerprint region | 75% | 15 |
| 5 | 1250 | fingerprint region | 65% | 15 |
| 6 | 1100 | fingerprint region | 60% | 15 |
| 7 | 900 | fingerprint region | 70% | 20 |
| 8 | 680 | Ar-H oop | 30% | 50 |
| 9 | 600 | fingerprint region | 65% | 20 |

Detected functional groups: `C-H_aromatic`, `ring_6`

---

## 3. NIST Reference (Benzene Fundamental Frequencies)

Source: NIST Chemistry WebBook + VPL Astrobiology (Washington Univ.)

All 20 fundamental modes listed; IR-active (u symmetry) modes only:

| Mode | Freq (cm-1) | Symmetry | Description | IR Active? |
|---|---|---|---|---|
| v4 | 673 | b1u | CH oop bend | Yes (strongest) |
| v5 | 3068 | b1u | CH stretch | Yes |
| v8 | 703 | b2u | ring deform | Yes |
| v9 | 1310 | b2u | ring stretch | Yes |
| v10 | 1150 | b2u | CH bend | Yes |
| v12 | 3063 | e1u | CH stretch | Yes |
| v13 | 1486 | e1u | ring str+deform | Yes |
| v14 | 1038 | e1u | CH ip bend | Yes |
| v16 | 1596 | e2g | ring stretch | NO (Raman only) |

---

## 4. Peak-by-Peak Comparison

| Predicted | NIST Match | Delta | Within +/-30? | Verdict |
|---|---|---|---|---|
| 3070 (Ar-H str.) | 3068 (v5/v12) | +2 | YES | PASS |
| 1600 (C=C ring str.) | 1596 (v16, e2g) | +4 | YES* | PASS (see note) |
| 1500 (C=C ring str.) | 1486 (v13, e1u) | +14 | YES | PASS |
| 680 (Ar-H oop) | 673 (v4, b1u) | +7 | YES | PASS |

*Note on 1600 cm-1: v16 (1596) is strictly Raman-active only for centrosymmetric benzene. However, Silverstein/Pavia list ~1600 and ~1500 as characteristic aromatic ring stretches observable in practical organic IR (substituted benzenes break the mutual exclusion rule). Since predict_spectra.py is a general-purpose predictor for arbitrary aromatics (not just pure benzene), keeping this peak is chemically justified and pedagogically standard.

### Fingerprint region coverage:
- 1350 ~ 1310 (v9, ring stretch): delta = +40 -- slightly outside tolerance but this is a generic fingerprint peak, not a specifically assigned one
- 1100 ~ 1038/1150 (v14/v10): reasonable fingerprint coverage
- 900: no strong NIST match (v19=975 is IR-inactive e2u)

---

## 5. Verdict

**ALL specifically assigned functional-group peaks are within the +/-30 cm-1 tolerance.**

No code modification required for predict_spectra.py.

### Quality observations (non-blocking):
1. The 1600 cm-1 peak is technically Raman-only for pure benzene but standard in organic IR practice -- acceptable
2. The ring_6 peak (700 cm-1) is suppressed by dedup with Ar-H oop (680) -- NIST shows distinct v4=673 and v8=703; our 680 is a reasonable compromise
3. Fingerprint peaks are generic and not precisely mapped to NIST fundamentals -- expected behavior for a SMARTS-based predictor

---

## 6. Post-work Updates
- [x] Skills read before work: confirmed
- [x] mistakes.md updated: Yes (created with no-fix-needed note)
- [x] skills/ updated: Yes (created nist_comparison_methodology.md)
- [x] Evidence report written: this file
