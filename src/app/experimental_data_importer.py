"""
experimental_data_importer.py
==============================
Experimental spectroscopy data import and comparison pipeline.

Supports:
  - JCAMP-DX (.jdx/.dx) files -- universal spectroscopy exchange format
  - CSV/TSV column data (wavenumber/wavelength, intensity)
  - Peak extraction from continuous data (local minima/maxima)
  - Quantitative comparison: cosine similarity, peak RMSD, Hungarian matching

Usage:
    from experimental_data_importer import (
        load_experimental_file, compare_spectra,
        ExperimentalSpectrum, SpectrumComparison,
    )

    exp = load_experimental_file("sample.jdx")
    result = compare_spectra(exp, theoretical_peaks, tolerance=50.0)
    print(f"Overall match: {result.overall_score:.1f}%")
"""
from __future__ import annotations

import csv
import io
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional: numpy for vectorized operations and interpolation
try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False
    logger.warning("numpy not available -- comparison accuracy may be reduced")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ExperimentalSpectrum:
    """Standardized container for experimental spectroscopy data."""
    spectrum_type: str                      # "IR", "UV-Vis", "NMR", "Raman", "GC-MS"
    x_data: List[float]                     # wavenumber, wavelength, or chemical shift
    y_data: List[float]                     # transmittance, absorbance, or intensity
    x_unit: str                             # "cm-1", "nm", "ppm"
    y_unit: str                             # "%T", "Abs", "a.u."
    peaks: List[Tuple[float, float]] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def num_points(self) -> int:
        return len(self.x_data)

    @property
    def x_range(self) -> Tuple[float, float]:
        if not self.x_data:
            return (0.0, 0.0)
        return (min(self.x_data), max(self.x_data))


@dataclass
class PeakMatch:
    """Single matched peak pair between experimental and theoretical."""
    exp_position: float
    exp_intensity: float
    theo_position: float
    theo_intensity: float
    delta: float                            # exp - theo position difference
    assignment: str = ""                    # functional group assignment if available


@dataclass
class SpectrumComparison:
    """Result of comparing experimental vs theoretical spectra."""
    overall_score: float                    # 0-100%
    peak_matches: List[PeakMatch]           # matched pairs
    unmatched_exp: List[float]              # experimental peaks with no match
    unmatched_theo: List[float]             # theoretical peaks with no match
    cosine_similarity: float                # full-spectrum cosine sim (0-1)
    peak_rmsd: float                        # RMS of peak position deviations
    method: str                             # "IR", "UV-Vis", etc.
    match_percentage: float                 # fraction of peaks matched (0-100)
    tolerance_used: float                   # tolerance window used (cm-1 or nm)


# ============================================================================
# JCAMP-DX PARSER
# ============================================================================

def _try_decode(raw_bytes: bytes) -> str:
    """Try multiple encodings to decode raw file bytes."""
    for encoding in ("utf-8", "latin-1", "ascii", "cp949"):
        try:
            return raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    # Last resort: latin-1 always succeeds
    return raw_bytes.decode("latin-1", errors="replace")


def _parse_jcamp_labeled_data(lines: List[str]) -> Tuple[List[float], List[float]]:
    """Parse JCAMP ##XYDATA= (X++(Y..Y)) or ##XYPOINTS= lines."""
    x_vals: List[float] = []
    y_vals: List[float] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("##"):
            continue

        # Split on whitespace or commas
        parts = re.split(r"[,\s]+", line)
        numeric_parts: List[float] = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            try:
                numeric_parts.append(float(p))
            except ValueError:
                continue

        if len(numeric_parts) >= 2:
            x_vals.append(numeric_parts[0])
            # For multi-Y per line, first Y is primary
            y_vals.append(numeric_parts[1])
        elif len(numeric_parts) == 1:
            # Single value on a line -- could be continuation Y
            # We skip these to avoid misalignment
            pass

    return x_vals, y_vals


def _parse_jcamp_peak_table(lines: List[str]) -> List[Tuple[float, float]]:
    """Parse JCAMP ##PEAKTABLE= (XY..XY) format."""
    peaks: List[Tuple[float, float]] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("##"):
            continue

        parts = re.split(r"[,\s]+", line)
        numeric_parts: List[float] = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            try:
                numeric_parts.append(float(p))
            except ValueError:
                continue

        # Peak table: pairs of (X, Y)
        for i in range(0, len(numeric_parts) - 1, 2):
            peaks.append((numeric_parts[i], numeric_parts[i + 1]))

    return peaks


def parse_jcamp_dx(filepath: Path) -> ExperimentalSpectrum:
    """
    Parse a JCAMP-DX (.jdx/.dx) spectroscopy file.

    Handles:
      - ##XYDATA= (X++(Y..Y)) continuous data
      - ##PEAKTABLE= (XY..XY) discrete peaks
      - Common metadata: TITLE, DATA TYPE, XUNITS, YUNITS, ORIGIN, etc.

    Args:
        filepath: Path to .jdx or .dx file

    Returns:
        ExperimentalSpectrum with parsed data and metadata

    Raises:
        FileNotFoundError: if file does not exist
        ValueError: if file cannot be parsed as valid JCAMP-DX
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"JCAMP-DX file not found: {filepath}")

    raw = filepath.read_bytes()
    text = _try_decode(raw)
    all_lines = text.splitlines()

    # --- Extract metadata from ## labels ---
    metadata: Dict[str, str] = {}
    x_unit = "cm-1"
    y_unit = "%T"
    data_type = ""
    spectrum_type = "IR"  # default

    # Data section tracking
    data_mode: Optional[str] = None  # "XYDATA" or "PEAKTABLE"
    data_lines: List[str] = []
    in_data_section = False

    for line in all_lines:
        stripped = line.strip()

        # Metadata labels
        if stripped.startswith("##"):
            label_match = re.match(r"##\s*([^=]+)\s*=\s*(.*)", stripped)
            if label_match:
                key = label_match.group(1).strip().upper()
                value = label_match.group(2).strip()

                # Store in metadata dict
                metadata[key] = value

                if key == "XUNITS":
                    x_unit = _normalize_unit(value)
                elif key == "YUNITS":
                    y_unit = _normalize_unit(value)
                elif key in ("DATA TYPE", "DATATYPE"):
                    data_type = value.upper()
                elif key == "XYDATA":
                    data_mode = "XYDATA"
                    in_data_section = True
                    continue
                elif key in ("PEAKTABLE", "PEAK TABLE"):
                    data_mode = "PEAKTABLE"
                    in_data_section = True
                    continue
                elif key == "XYPOINTS":
                    data_mode = "XYDATA"  # same parsing logic
                    in_data_section = True
                    continue
                elif key == "END":
                    in_data_section = False
                    continue

            # If we hit a new ## label while in data, stop data capture
            if in_data_section and stripped.startswith("##"):
                # Check if it's END or a new section
                if "END" in stripped.upper():
                    in_data_section = False
                elif "=" in stripped:
                    # New labeled field -- end data section
                    in_data_section = False
            continue

        # Data lines (non-## lines inside data section)
        if in_data_section:
            data_lines.append(stripped)

    # --- Determine spectrum type from data type ---
    spectrum_type = _infer_spectrum_type(data_type, x_unit, y_unit)

    # --- Parse data ---
    x_data: List[float] = []
    y_data: List[float] = []
    peaks: List[Tuple[float, float]] = []

    if data_mode == "XYDATA":
        x_data, y_data = _parse_jcamp_labeled_data(data_lines)
    elif data_mode == "PEAKTABLE":
        peaks = _parse_jcamp_peak_table(data_lines)
        if peaks:
            x_data = [p[0] for p in peaks]
            y_data = [p[1] for p in peaks]

    if not x_data and not peaks:
        # Fallback: try to parse the entire file as numeric data
        x_data, y_data = _parse_jcamp_labeled_data(all_lines)

    if not x_data:
        raise ValueError(
            f"No spectral data found in JCAMP-DX file: {filepath.name}. "
            f"Data mode detected: {data_mode}"
        )

    # Extract peaks if not from peak table
    if not peaks and x_data and y_data:
        peaks = extract_peaks(x_data, y_data, spectrum_type)

    return ExperimentalSpectrum(
        spectrum_type=spectrum_type,
        x_data=x_data,
        y_data=y_data,
        x_unit=x_unit,
        y_unit=y_unit,
        peaks=peaks,
        metadata=metadata,
    )


def _normalize_unit(raw: str) -> str:
    """Normalize unit strings to canonical form."""
    r = raw.strip().upper()
    if r in ("1/CM", "CM-1", "CM^-1", "WAVENUMBER", "WAVENUMBERS"):
        return "cm-1"
    if r in ("MICROMETERS", "UM"):
        return "um"
    if r in ("NANOMETERS", "NM"):
        return "nm"
    if r in ("PPM",):
        return "ppm"
    if r in ("TRANSMITTANCE", "%T", "PERCENT TRANSMITTANCE"):
        return "%T"
    if r in ("ABSORBANCE", "ABS", "A"):
        return "Abs"
    if r in ("ARBITRARY UNITS", "A.U.", "AU"):
        return "a.u."
    # Fallback: return cleaned version
    return raw.strip()


def _infer_spectrum_type(data_type: str, x_unit: str, y_unit: str) -> str:
    """Infer spectrum type (IR, UV-Vis, NMR, Raman) from metadata."""
    dt = data_type.upper()
    if "INFRARED" in dt or "IR" in dt:
        return "IR"
    if "UV" in dt or "VISIBLE" in dt or "ELECTRONIC" in dt:
        return "UV-Vis"
    if "NMR" in dt or "NUCLEAR" in dt:
        return "NMR"
    if "RAMAN" in dt:
        return "Raman"
    if "MASS" in dt or "MS" in dt:
        return "GC-MS"

    # Infer from units
    if x_unit == "cm-1":
        if y_unit in ("%T", "Abs"):
            return "IR"
        return "Raman"
    if x_unit == "nm":
        return "UV-Vis"
    if x_unit == "ppm":
        return "NMR"

    return "IR"  # safe default


# ============================================================================
# CSV / TSV PARSER
# ============================================================================

def parse_csv(filepath: Path,
              x_col: int = 0,
              y_col: int = 1,
              delimiter: Optional[str] = None,
              spectrum_type: str = "IR",
              x_unit: str = "cm-1",
              y_unit: str = "%T") -> ExperimentalSpectrum:
    """
    Parse a CSV/TSV file with spectral data columns.

    Attempts auto-detection of delimiter (comma, tab, semicolon).
    Skips header rows that contain non-numeric data.

    Args:
        filepath: Path to .csv or .tsv file
        x_col: column index for X data (default 0)
        y_col: column index for Y data (default 1)
        delimiter: field separator (auto-detected if None)
        spectrum_type: "IR", "UV-Vis", "NMR", "Raman"
        x_unit: X axis unit
        y_unit: Y axis unit

    Returns:
        ExperimentalSpectrum with parsed data

    Raises:
        FileNotFoundError: if file does not exist
        ValueError: if no numeric data found
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    raw = filepath.read_bytes()
    text = _try_decode(raw)

    # Auto-detect delimiter
    if delimiter is None:
        delimiter = _detect_delimiter(text)

    x_data: List[float] = []
    y_data: List[float] = []
    metadata: Dict[str, str] = {"source_file": filepath.name}

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header_row: Optional[str] = None

    for row_num, row in enumerate(reader):
        if len(row) <= max(x_col, y_col):
            continue

        try:
            x_val = float(row[x_col].strip())
            y_val = float(row[y_col].strip())
            x_data.append(x_val)
            y_data.append(y_val)
        except ValueError:
            # Likely a header row
            if row_num == 0:
                header_row = delimiter.join(row)
                metadata["header"] = header_row
                # Try to infer units from header
                hdr_lower = header_row.lower()
                if "nm" in hdr_lower:
                    x_unit = "nm"
                    spectrum_type = "UV-Vis"
                elif "ppm" in hdr_lower:
                    x_unit = "ppm"
                    spectrum_type = "NMR"
                elif "cm" in hdr_lower:
                    x_unit = "cm-1"
                if "absorbance" in hdr_lower or "abs" in hdr_lower:
                    y_unit = "Abs"
                elif "transmittance" in hdr_lower:
                    y_unit = "%T"
            continue

    if not x_data:
        raise ValueError(f"No numeric data found in CSV: {filepath.name}")

    peaks = extract_peaks(x_data, y_data, spectrum_type)

    return ExperimentalSpectrum(
        spectrum_type=spectrum_type,
        x_data=x_data,
        y_data=y_data,
        x_unit=x_unit,
        y_unit=y_unit,
        peaks=peaks,
        metadata=metadata,
    )


def _detect_delimiter(text: str) -> str:
    """Auto-detect CSV delimiter from first few lines."""
    sample = text[:2000]
    tab_count = sample.count("\t")
    comma_count = sample.count(",")
    semicolon_count = sample.count(";")

    if tab_count > comma_count and tab_count > semicolon_count:
        return "\t"
    if semicolon_count > comma_count:
        return ";"
    return ","


# ============================================================================
# UNIFIED LOADER
# ============================================================================

def load_experimental_file(filepath: str | Path,
                           **kwargs) -> ExperimentalSpectrum:
    """
    Load experimental spectral data from file.

    Auto-detects format from file extension:
      .jdx, .dx  -> JCAMP-DX parser
      .csv, .tsv, .txt -> CSV parser

    Args:
        filepath: path to data file
        **kwargs: passed to the appropriate parser

    Returns:
        ExperimentalSpectrum

    Raises:
        ValueError: if file format is not recognized
        FileNotFoundError: if file does not exist
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    if ext in (".jdx", ".dx"):
        return parse_jcamp_dx(filepath)
    elif ext in (".csv", ".tsv", ".txt"):
        return parse_csv(filepath, **kwargs)
    else:
        raise ValueError(
            f"Unsupported file format: {ext}. "
            f"Supported: .jdx, .dx, .csv, .tsv, .txt"
        )


# ============================================================================
# PEAK EXTRACTION
# ============================================================================

def extract_peaks(x_data: List[float],
                  y_data: List[float],
                  spectrum_type: str = "IR",
                  prominence: float = 0.0,
                  min_distance_x: float = 0.0) -> List[Tuple[float, float]]:
    """
    Extract peaks from continuous spectral data.

    For IR transmittance: finds local MINIMA (absorption dips).
    For absorbance/intensity: finds local MAXIMA.

    Uses scipy.signal.find_peaks if available, otherwise falls back
    to a simple local extrema algorithm.

    Args:
        x_data: X values (wavenumber, wavelength, etc.)
        y_data: Y values (transmittance, absorbance, etc.)
        spectrum_type: "IR", "UV-Vis", "NMR", "Raman"
        prominence: minimum peak prominence (auto-calculated if 0)
        min_distance_x: minimum distance between peaks in X units

    Returns:
        List of (x_position, y_value) tuples for detected peaks
    """
    if len(x_data) < 3 or len(y_data) < 3:
        return []

    if not NP_OK:
        return _extract_peaks_simple(x_data, y_data, spectrum_type)

    x_arr = np.array(x_data, dtype=float)
    y_arr = np.array(y_data, dtype=float)

    # For IR transmittance, invert to find absorption peaks (minima -> maxima)
    find_minima = (spectrum_type == "IR")

    if find_minima:
        search_signal = -y_arr  # invert so peaks become maxima
    else:
        search_signal = y_arr

    # Auto-calculate prominence
    if prominence <= 0:
        signal_range = float(np.ptp(search_signal))
        prominence = max(signal_range * 0.05, 0.01)

    # Calculate minimum sample distance from X units
    min_distance_samples = 1
    if min_distance_x > 0 and len(x_arr) > 1:
        avg_dx = abs(float(np.mean(np.diff(x_arr))))
        if avg_dx > 0:
            min_distance_samples = max(1, int(min_distance_x / avg_dx))

    # Try scipy first
    try:
        from scipy.signal import find_peaks as sp_find_peaks
        indices, properties = sp_find_peaks(
            search_signal,
            prominence=prominence,
            distance=min_distance_samples,
        )
    except ImportError:
        # Fallback to manual peak finding
        indices = _find_peaks_manual(search_signal, min_distance_samples)

    peaks: List[Tuple[float, float]] = []
    for idx in indices:
        if 0 <= idx < len(x_arr):
            peaks.append((float(x_arr[idx]), float(y_arr[idx])))

    # Sort by X position
    peaks.sort(key=lambda p: p[0])
    return peaks


def _find_peaks_manual(signal: "np.ndarray",
                       min_distance: int = 1) -> List[int]:
    """Simple local maxima detection without scipy."""
    peaks: List[int] = []
    n = len(signal)

    for i in range(1, n - 1):
        if signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
            # Check minimum distance from last peak
            if peaks and (i - peaks[-1]) < min_distance:
                # Keep the taller peak
                if signal[i] > signal[peaks[-1]]:
                    peaks[-1] = i
            else:
                peaks.append(i)

    return peaks


def _extract_peaks_simple(x_data: List[float],
                          y_data: List[float],
                          spectrum_type: str) -> List[Tuple[float, float]]:
    """Pure-Python peak extraction without numpy."""
    peaks: List[Tuple[float, float]] = []
    n = len(y_data)

    find_minima = (spectrum_type == "IR")

    for i in range(1, n - 1):
        if find_minima:
            if y_data[i] < y_data[i - 1] and y_data[i] < y_data[i + 1]:
                peaks.append((x_data[i], y_data[i]))
        else:
            if y_data[i] > y_data[i - 1] and y_data[i] > y_data[i + 1]:
                peaks.append((x_data[i], y_data[i]))

    return peaks


# ============================================================================
# SPECTRUM COMPARISON ENGINE
# ============================================================================

def compare_spectra(experimental: ExperimentalSpectrum,
                    theoretical_peaks: List[Tuple[float, float]],
                    tolerance: float = 50.0,
                    assignments: Optional[Dict[float, str]] = None,
                    method: Optional[str] = None) -> SpectrumComparison:
    """
    Compare experimental spectrum against theoretical peak predictions.

    Algorithm:
    1. Greedy nearest-neighbor peak matching within tolerance window
    2. Cosine similarity of interpolated full spectra
    3. Composite score = 0.6 * match_pct + 0.25 * (1 - norm_rmsd) + 0.15 * cosine

    Args:
        experimental: parsed experimental data
        theoretical_peaks: list of (position, intensity) from prediction
        tolerance: maximum position difference for a peak match (cm-1 or nm)
        assignments: optional dict mapping theo_position -> functional group name
        method: spectrum type override (default: from experimental.spectrum_type)

    Returns:
        SpectrumComparison with detailed matching results
    """
    if assignments is None:
        assignments = {}
    if method is None:
        method = experimental.spectrum_type

    exp_peaks = list(experimental.peaks)
    theo_peaks = list(theoretical_peaks)

    # --- Peak Matching (greedy nearest-neighbor) ---
    matches, unmatched_exp_positions, unmatched_theo_positions = _match_peaks(
        exp_peaks, theo_peaks, tolerance, assignments
    )

    # --- Match percentage ---
    total_peaks = max(len(exp_peaks), len(theo_peaks), 1)
    match_pct = (len(matches) / total_peaks) * 100.0

    # --- Peak RMSD ---
    peak_rmsd = 0.0
    if matches:
        sum_sq = sum(m.delta ** 2 for m in matches)
        peak_rmsd = math.sqrt(sum_sq / len(matches))

    # --- Cosine similarity of full spectra ---
    cosine_sim = _compute_cosine_similarity(
        experimental, theo_peaks, method
    )

    # --- Composite score ---
    # Normalize RMSD: 0 = perfect, tolerance = worst
    norm_rmsd = min(peak_rmsd / max(tolerance, 1.0), 1.0)
    overall_score = (
        0.60 * match_pct
        + 0.25 * (1.0 - norm_rmsd) * 100.0
        + 0.15 * cosine_sim * 100.0
    )
    overall_score = max(0.0, min(100.0, overall_score))

    return SpectrumComparison(
        overall_score=overall_score,
        peak_matches=matches,
        unmatched_exp=unmatched_exp_positions,
        unmatched_theo=unmatched_theo_positions,
        cosine_similarity=cosine_sim,
        peak_rmsd=peak_rmsd,
        method=method,
        match_percentage=match_pct,
        tolerance_used=tolerance,
    )


def _match_peaks(exp_peaks: List[Tuple[float, float]],
                 theo_peaks: List[Tuple[float, float]],
                 tolerance: float,
                 assignments: Dict[float, str]) -> Tuple[
                     List[PeakMatch], List[float], List[float]]:
    """
    Greedy nearest-neighbor peak matching.

    For each experimental peak, find the closest unmatched theoretical peak
    within tolerance. Matches are assigned in order of smallest delta first.
    """
    if not exp_peaks or not theo_peaks:
        unm_exp = [p[0] for p in exp_peaks]
        unm_theo = [p[0] for p in theo_peaks]
        return [], unm_exp, unm_theo

    # Build all possible pairings with their deltas
    candidates: List[Tuple[float, int, int]] = []  # (|delta|, exp_idx, theo_idx)
    for ei, (ex, ey) in enumerate(exp_peaks):
        for ti, (tx, ty) in enumerate(theo_peaks):
            delta = abs(ex - tx)
            if delta <= tolerance:
                candidates.append((delta, ei, ti))

    # Sort by delta (smallest first) for greedy assignment
    candidates.sort(key=lambda c: c[0])

    matched_exp: set = set()
    matched_theo: set = set()
    matches: List[PeakMatch] = []

    for delta_abs, ei, ti in candidates:
        if ei in matched_exp or ti in matched_theo:
            continue

        ex, ey = exp_peaks[ei]
        tx, ty = theo_peaks[ti]
        assignment = assignments.get(tx, "")

        matches.append(PeakMatch(
            exp_position=ex,
            exp_intensity=ey,
            theo_position=tx,
            theo_intensity=ty,
            delta=ex - tx,
            assignment=assignment,
        ))
        matched_exp.add(ei)
        matched_theo.add(ti)

    unmatched_exp_pos = [exp_peaks[i][0] for i in range(len(exp_peaks))
                         if i not in matched_exp]
    unmatched_theo_pos = [theo_peaks[i][0] for i in range(len(theo_peaks))
                          if i not in matched_theo]

    return matches, unmatched_exp_pos, unmatched_theo_pos


def _compute_cosine_similarity(experimental: ExperimentalSpectrum,
                                theo_peaks: List[Tuple[float, float]],
                                method: str) -> float:
    """
    Compute cosine similarity between experimental and theoretical spectra.

    Interpolates both to a common X grid, then calculates:
        cos_sim = dot(A, B) / (||A|| * ||B||)
    """
    if not NP_OK:
        return 0.0

    if not experimental.x_data or not experimental.y_data or not theo_peaks:
        return 0.0

    x_exp = np.array(experimental.x_data, dtype=float)
    y_exp = np.array(experimental.y_data, dtype=float)

    # For IR transmittance, convert to absorbance for fair comparison
    if experimental.y_unit == "%T":
        # Clamp to avoid log(0)
        y_exp_clamped = np.clip(y_exp, 0.1, 100.0)
        y_exp = 2.0 - np.log10(y_exp_clamped)

    # Build common X grid
    x_min = float(np.min(x_exp))
    x_max = float(np.max(x_exp))
    n_points = 1000
    x_common = np.linspace(x_min, x_max, n_points)

    # Interpolate experimental onto common grid
    sort_idx = np.argsort(x_exp)
    x_exp_sorted = x_exp[sort_idx]
    y_exp_sorted = y_exp[sort_idx]
    y_exp_interp = np.interp(x_common, x_exp_sorted, y_exp_sorted)

    # Generate theoretical spectrum on common grid
    y_theo = np.zeros(n_points)
    for pos, intensity in theo_peaks:
        if x_min <= pos <= x_max:
            # Gaussian broadening
            sigma = 15.0  # cm-1 or nm
            y_theo += abs(intensity) * np.exp(
                -0.5 * ((x_common - pos) / sigma) ** 2
            )

    # Normalize both
    exp_norm = np.linalg.norm(y_exp_interp)
    theo_norm = np.linalg.norm(y_theo)

    if exp_norm < 1e-10 or theo_norm < 1e-10:
        return 0.0

    cosine = float(np.dot(y_exp_interp, y_theo) / (exp_norm * theo_norm))
    return max(0.0, min(1.0, cosine))


# ============================================================================
# HELPER: CONVERT PREDICTED PEAKS TO COMPARISON FORMAT
# ============================================================================

def ir_peaks_to_comparison_format(
    ir_peaks: list,
) -> Tuple[List[Tuple[float, float]], Dict[float, str]]:
    """
    Convert predict_spectra.IRPeak list to (position, intensity) tuples
    and assignment dict for use with compare_spectra.

    The IRPeak dataclass has:
      .wavenumber, .transmittance, .assignment

    For comparison, we use absorbance-like intensity:
      intensity = (100 - transmittance) / 100

    Returns:
        (peaks_list, assignments_dict)
    """
    peaks: List[Tuple[float, float]] = []
    assignments: Dict[float, str] = {}

    for pk in ir_peaks:
        wn = pk.wavenumber
        # Convert transmittance to absorbance-like (0-1)
        intensity = (100.0 - pk.transmittance) / 100.0
        peaks.append((wn, intensity))
        assignments[wn] = pk.assignment

    return peaks, assignments


def uvvis_peaks_to_comparison_format(
    uvvis_peaks: list,
) -> Tuple[List[Tuple[float, float]], Dict[float, str]]:
    """
    Convert predict_spectra.UVVisPeak list to comparison format.

    UVVisPeak has: .wavelength, .epsilon, .transition_type, .assignment

    Returns:
        (peaks_list, assignments_dict)
    """
    peaks: List[Tuple[float, float]] = []
    assignments: Dict[float, str] = {}

    for pk in uvvis_peaks:
        peaks.append((pk.wavelength, pk.epsilon))
        assignments[pk.wavelength] = f"{pk.transition_type}: {pk.assignment}"

    return peaks, assignments


def raman_peaks_to_comparison_format(
    raman_peaks: list,
) -> Tuple[List[Tuple[float, float]], Dict[float, str]]:
    """
    Convert predict_spectra.RamanPeak list to comparison format.

    RamanPeak has: .shift, .intensity, .assignment

    Returns:
        (peaks_list, assignments_dict)
    """
    peaks: List[Tuple[float, float]] = []
    assignments: Dict[float, str] = {}

    for pk in raman_peaks:
        peaks.append((pk.shift, pk.intensity))
        assignments[pk.shift] = pk.assignment

    return peaks, assignments
