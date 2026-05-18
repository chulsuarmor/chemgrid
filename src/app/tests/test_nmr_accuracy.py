"""
test_nmr_accuracy.py  --  NMR Spectrum Accuracy Audit (domain_spectrum)
=====================================================================
Tests 1H-NMR and 13C-NMR prediction accuracy for common molecules
against known chemical shift data from Silverstein/Pavia/SDBS.

Grading per molecule:
  PASS = all checks pass (peak count, shift ranges, integration ratios)
  FAIL = one or more checks fail

Run:
  python -m pytest tests/test_nmr_accuracy.py -v
  python tests/test_nmr_accuracy.py           (standalone)
"""
from __future__ import annotations
import sys, os
from typing import List, Dict, Tuple, Optional
from dataclasses import asdict

# Ensure src/app is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predict_spectra import predict_h1_nmr, predict_c13_nmr, NMRPeak, C13Peak

# ══════════════════════════════════════════════════════════════════
# 1H-NMR Reference Data
# ══════════════════════════════════════════════════════════════════
# Format per molecule:
#   "SMILES": {
#       "name": str,
#       "expected_peak_count": int,   # number of chemically distinct H groups
#       "peaks": [
#           {
#               "label": str,
#               "shift_range": (low_ppm, high_ppm),
#               "expected_integration": int,   # number of H
#               "expected_multiplicity": str or None,  # None = don't check
#           }, ...
#       ],
#       "ratios": [  # optional integration ratio checks
#           (label_a, label_b, expected_ratio, tolerance),
#       ]
#   }

H1_REFERENCE: Dict[str, dict] = {
    "c1ccccc1": {  # benzene
        "name": "Benzene",
        "expected_peak_count": 1,
        "peaks": [
            {
                "label": "ArH",
                "shift_range": (6.5, 8.5),
                "expected_integration": 6,
                "expected_multiplicity": "s",
            },
        ],
        "ratios": [],
    },
    "CCO": {  # ethanol
        "name": "Ethanol",
        "expected_peak_count": 3,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (0.5, 2.0),
                "expected_integration": 3,
                "expected_multiplicity": "t",
            },
            {
                "label": "CH2",
                "shift_range": (3.0, 4.5),
                "expected_integration": 2,
                "expected_multiplicity": "q",
            },
            {
                "label": "OH",
                "shift_range": (1.0, 5.5),
                "expected_integration": 1,
                "expected_multiplicity": "s",
            },
        ],
        "ratios": [
            ("CH3", "CH2", 3 / 2, 0.3),
        ],
    },
    "CC(=O)O": {  # acetic acid
        "name": "Acetic acid",
        "expected_peak_count": 2,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (1.5, 3.0),
                "expected_integration": 3,
                "expected_multiplicity": "s",
            },
            {
                "label": "COOH",
                "shift_range": (9.0, 13.0),
                "expected_integration": 1,
                "expected_multiplicity": "s",
            },
        ],
        "ratios": [
            ("CH3", "COOH", 3.0, 0.5),
        ],
    },
    "CC(=O)C": {  # acetone
        "name": "Acetone",
        "expected_peak_count": 1,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (1.5, 3.0),
                "expected_integration": 6,
                "expected_multiplicity": "s",
            },
        ],
        "ratios": [],
    },
    "Cc1ccccc1": {  # toluene
        "name": "Toluene",
        "expected_peak_count": 2,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (1.5, 3.0),
                "expected_integration": 3,
                "expected_multiplicity": "s",
            },
            {
                "label": "ArH",
                "shift_range": (6.5, 8.5),
                "expected_integration": 5,
                "expected_multiplicity": None,  # complex pattern
            },
        ],
        "ratios": [
            ("CH3", "ArH", 3 / 5, 0.3),
        ],
    },
    "ClC(Cl)Cl": {  # chloroform
        "name": "Chloroform",
        "expected_peak_count": 1,
        "peaks": [
            {
                "label": "CHCl3",
                "shift_range": (6.5, 8.5),
                "expected_integration": 1,
                "expected_multiplicity": "s",
            },
        ],
        "ratios": [],
    },
    "CS(=O)C": {  # DMSO
        "name": "DMSO",
        "expected_peak_count": 1,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (1.5, 3.5),
                "expected_integration": 6,
                "expected_multiplicity": "s",
            },
        ],
        "ratios": [],
    },
    "CC=O": {  # acetaldehyde
        "name": "Acetaldehyde",
        "expected_peak_count": 2,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (1.5, 3.0),
                "expected_integration": 3,
                "expected_multiplicity": None,
            },
            {
                "label": "CHO",
                "shift_range": (9.0, 10.5),
                "expected_integration": 1,
                "expected_multiplicity": None,
            },
        ],
        "ratios": [
            ("CH3", "CHO", 3.0, 0.5),
        ],
    },
}

# ══════════════════════════════════════════════════════════════════
# 13C-NMR Reference Data
# ══════════════════════════════════════════════════════════════════
# Format per molecule:
#   "SMILES": {
#       "name": str,
#       "expected_peak_count": int,
#       "peaks": [
#           {
#               "label": str,
#               "shift_range": (low_ppm, high_ppm),
#               "expected_zone": str,  # "aliphatic"/"aromatic"/"carbonyl"
#           }, ...
#       ]
#   }

C13_REFERENCE: Dict[str, dict] = {
    "c1ccccc1": {  # benzene — all 6 C are equivalent
        "name": "Benzene",
        "expected_peak_count": 1,
        "peaks": [
            {
                "label": "ArC",
                "shift_range": (120.0, 140.0),
                "expected_zone": "aromatic",
            },
        ],
    },
    "CCO": {  # ethanol — 2 distinct carbons
        "name": "Ethanol",
        "expected_peak_count": 2,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (10.0, 25.0),
                "expected_zone": "aliphatic",
            },
            {
                "label": "CH2-O",
                "shift_range": (50.0, 70.0),
                "expected_zone": "aliphatic",
            },
        ],
    },
    "CC(=O)C": {  # acetone — 2 distinct carbons (2 CH3 equivalent + C=O)
        "name": "Acetone",
        "expected_peak_count": 2,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (25.0, 35.0),
                "expected_zone": "aliphatic",
            },
            {
                "label": "C=O",
                "shift_range": (190.0, 220.0),
                "expected_zone": "carbonyl",
            },
        ],
    },
    "CC(=O)O": {  # acetic acid — 2 distinct carbons
        "name": "Acetic acid",
        "expected_peak_count": 2,
        "peaks": [
            {
                "label": "CH3",
                "shift_range": (15.0, 25.0),
                "expected_zone": "aliphatic",
            },
            {
                "label": "COOH",
                "shift_range": (165.0, 185.0),
                "expected_zone": "carbonyl",
            },
        ],
    },
    "ClC(Cl)Cl": {  # chloroform — 1 carbon
        "name": "Chloroform",
        "expected_peak_count": 1,
        "peaks": [
            {
                "label": "CHCl3",
                "shift_range": (70.0, 85.0),
                "expected_zone": "aliphatic",
            },
        ],
    },
}

# ══════════════════════════════════════════════════════════════════
# Test Helpers
# ══════════════════════════════════════════════════════════════════

def _find_peak_in_range(peaks, low, high):
    """Find a peak whose shift falls within [low, high]. Returns first match or None."""
    for p in peaks:
        if low <= p.shift <= high:
            return p
    return None


def _find_peak_in_range_all(peaks, low, high):
    """Find ALL peaks whose shift falls within [low, high]."""
    return [p for p in peaks if low <= p.shift <= high]


# ══════════════════════════════════════════════════════════════════
# 1H-NMR Tests
# ══════════════════════════════════════════════════════════════════

def test_h1_nmr_accuracy():
    """Run 1H-NMR accuracy tests for all reference molecules."""
    total = 0
    passed = 0
    issues_all = []

    for smiles, ref in H1_REFERENCE.items():
        name = ref["name"]
        total += 1
        issues = []

        actual_peaks = predict_h1_nmr(smiles)
        actual_count = len(actual_peaks)
        expected_count = ref["expected_peak_count"]

        # --- Check 1: Peak count ---
        if actual_count != expected_count:
            issues.append(
                f"Peak count: expected {expected_count}, got {actual_count} "
                f"(shifts: {[p.shift for p in actual_peaks]})"
            )

        # --- Check 2: Each expected peak exists in the correct range ---
        for exp_peak in ref["peaks"]:
            label = exp_peak["label"]
            lo, hi = exp_peak["shift_range"]
            exp_int = exp_peak["expected_integration"]
            exp_mult = exp_peak.get("expected_multiplicity")

            matches = _find_peak_in_range_all(actual_peaks, lo, hi)
            if not matches:
                issues.append(
                    f"'{label}': no peak found in {lo}-{hi} ppm "
                    f"(actual shifts: {[round(p.shift, 2) for p in actual_peaks]})"
                )
                continue

            # Sum integration of all matches in the range
            total_int = sum(m.integration for m in matches)
            if total_int != exp_int:
                issues.append(
                    f"'{label}': integration expected {exp_int}H, got {total_int}H "
                    f"(peaks in range: {[(round(m.shift,2), m.integration) for m in matches]})"
                )

            # Multiplicity check (only for first/main match)
            if exp_mult is not None:
                main = matches[0]
                if main.multiplicity != exp_mult:
                    issues.append(
                        f"'{label}': multiplicity expected '{exp_mult}', got '{main.multiplicity}'"
                    )

        # --- Check 3: Integration ratios ---
        for ratio_check in ref.get("ratios", []):
            label_a, label_b, expected_ratio, tol = ratio_check
            # Find peaks by label match from expected peak list
            peak_a_info = next((p for p in ref["peaks"] if p["label"] == label_a), None)
            peak_b_info = next((p for p in ref["peaks"] if p["label"] == label_b), None)
            if not peak_a_info or not peak_b_info:
                continue

            lo_a, hi_a = peak_a_info["shift_range"]
            lo_b, hi_b = peak_b_info["shift_range"]

            matches_a = _find_peak_in_range_all(actual_peaks, lo_a, hi_a)
            matches_b = _find_peak_in_range_all(actual_peaks, lo_b, hi_b)

            if matches_a and matches_b:
                int_a = sum(m.integration for m in matches_a)
                int_b = sum(m.integration for m in matches_b)
                if int_b > 0:
                    actual_ratio = int_a / int_b
                    if abs(actual_ratio - expected_ratio) > tol:
                        issues.append(
                            f"Ratio {label_a}:{label_b} expected ~{expected_ratio:.2f}, "
                            f"got {actual_ratio:.2f} ({int_a}H:{int_b}H)"
                        )

        # --- Result ---
        status = "PASS" if not issues else "FAIL"
        if not issues:
            passed += 1
        issues_all.append((name, smiles, status, actual_count, expected_count, issues, actual_peaks))

    return total, passed, issues_all


# ══════════════════════════════════════════════════════════════════
# 13C-NMR Tests
# ══════════════════════════════════════════════════════════════════

def test_c13_nmr_accuracy():
    """Run 13C-NMR accuracy tests for all reference molecules."""
    total = 0
    passed = 0
    issues_all = []

    for smiles, ref in C13_REFERENCE.items():
        name = ref["name"]
        total += 1
        issues = []

        actual_peaks = predict_c13_nmr(smiles)
        actual_count = len(actual_peaks)
        expected_count = ref["expected_peak_count"]

        # --- Check 1: Peak count ---
        if actual_count != expected_count:
            issues.append(
                f"Peak count: expected {expected_count}, got {actual_count} "
                f"(shifts: {[p.shift for p in actual_peaks]})"
            )

        # --- Check 2: Each expected peak in correct range ---
        for exp_peak in ref["peaks"]:
            label = exp_peak["label"]
            lo, hi = exp_peak["shift_range"]
            exp_zone = exp_peak["expected_zone"]

            matches = _find_peak_in_range_all(actual_peaks, lo, hi)
            if not matches:
                issues.append(
                    f"'{label}': no peak in {lo}-{hi} ppm "
                    f"(actual: {[(round(p.shift,1), p.assignment) for p in actual_peaks]})"
                )
                continue

            # Zone check
            for m in matches:
                if m.zone != exp_zone:
                    issues.append(
                        f"'{label}' at {m.shift} ppm: zone expected '{exp_zone}', got '{m.zone}'"
                    )

        # --- Result ---
        status = "PASS" if not issues else "FAIL"
        if not issues:
            passed += 1
        issues_all.append((name, smiles, status, actual_count, expected_count, issues, actual_peaks))

    return total, passed, issues_all


# ══════════════════════════════════════════════════════════════════
# Report & Main
# ══════════════════════════════════════════════════════════════════

def print_report():
    print("=" * 78)
    print("  NMR Accuracy Audit Report")
    print("=" * 78)

    # ── 1H-NMR ──
    print("\n" + "-" * 78)
    print("  1H-NMR Accuracy")
    print("-" * 78)

    h1_total, h1_passed, h1_results = test_h1_nmr_accuracy()

    for name, smiles, status, actual_n, expected_n, issues, peaks in h1_results:
        tag = "PASS" if status == "PASS" else "FAIL"
        print(f"\n  [{tag}] {name} ({smiles})")
        print(f"    Expected peaks: {expected_n}  |  Actual peaks: {actual_n}")
        if peaks:
            print(f"    Actual detail:")
            for p in peaks:
                print(f"      {p.shift:.1f} ppm | {p.integration}H | {p.multiplicity} | {p.assignment}")
        if issues:
            for iss in issues:
                print(f"    >> ISSUE: {iss}")

    print(f"\n  1H-NMR Score: {h1_passed}/{h1_total}")

    # ── 13C-NMR ──
    print("\n" + "-" * 78)
    print("  13C-NMR Accuracy")
    print("-" * 78)

    c13_total, c13_passed, c13_results = test_c13_nmr_accuracy()

    for name, smiles, status, actual_n, expected_n, issues, peaks in c13_results:
        tag = "PASS" if status == "PASS" else "FAIL"
        print(f"\n  [{tag}] {name} ({smiles})")
        print(f"    Expected peaks: {expected_n}  |  Actual peaks: {actual_n}")
        if peaks:
            print(f"    Actual detail:")
            for p in peaks:
                print(f"      {p.shift:.1f} ppm | {p.carbon_type} | {p.zone} | {p.assignment}")
        if issues:
            for iss in issues:
                print(f"    >> ISSUE: {iss}")

    print(f"\n  13C-NMR Score: {c13_passed}/{c13_total}")

    # ── Overall ──
    overall_total = h1_total + c13_total
    overall_passed = h1_passed + c13_passed
    print("\n" + "=" * 78)
    print(f"  OVERALL NMR Score: {overall_passed}/{overall_total}")
    print("=" * 78)

    return overall_passed, overall_total


if __name__ == "__main__":
    p, t = print_report()
    sys.exit(0 if p == t else 1)
