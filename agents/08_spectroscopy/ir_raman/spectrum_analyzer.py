# spectrum_analyzer.py (v1.1 - IR/Raman Spectrum Analysis)
"""
ChemDraw Pro: IR/Raman Spectrum Analyzer
- Parse vibrational frequencies from ORCA .out files
- Calculate IR intensity (Lorentzian broadening)
- Generate matplotlib-based spectrum visualization
- PyQt6 integration for interactive display
"""

import os
import math
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("Matplotlib not available")

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpinBox, QDoubleSpinBox
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class VibrationalMode:
    """Single vibrational mode (frequency + intensity)"""
    frequency: float       # cm^-1
    intensity: float       # km/mol (IR intensity)
    raman_activity: float  # A^4/amu (Raman scattering intensity)
    mode_index: int        # Mode number
    atom_contributions: Dict[int, float] = None  # Contribution per atom
    
    def __post_init__(self):
        if self.atom_contributions is None:
            self.atom_contributions = {}


@dataclass
class SpectrumData:
    """Complete spectral dataset"""
    modes: List[VibrationalMode]
    ir_frequencies: List[float]      # All IR frequencies (cm^-1)
    ir_intensities: List[float]      # All IR intensities (km/mol)
    raman_frequencies: List[float]    # All Raman frequencies (cm^-1)
    raman_activities: List[float]     # All Raman activities
    frequency_range: Tuple[float, float]  # (min_freq, max_freq)
    computation_time: float           # Calculation time in seconds
    converged: bool                   # Convergence status


# ============================================================================
# ORCA OUTPUT PARSING
# ============================================================================

def parse_orca_frequencies(out_path: Path) -> SpectrumData:
    """
    Parse ORCA vibrational analysis output (.out file)
    
    Extracts:
    - Vibrational frequencies (cm^-1)
    - IR intensities (km/mol)
    - Raman scattering intensities (A^4/amu)
    - Mode displacements per atom
    
    Returns:
        SpectrumData object with all parsed information
    """
    modes = []
    ir_freqs = []
    ir_ints = []
    raman_freqs = []
    raman_acts = []
    
    if not out_path.exists():
        logger.error(f"ORCA output file not found: {out_path}")
        return SpectrumData([], [], [], [], [], (0, 0), 0.0, False)
    
    try:
        content = out_path.read_text()
        lines = content.split('\n')
        
        # === Step 1: Extract Harmonic Vibrational Frequencies ===
        in_freq_section = False
        mode_idx = 0
        
        for i, line in enumerate(lines):
            if "HARMONIC VIBRATIONAL FREQUENCIES (CM**-1)" in line or \
               "VIBRATIONAL FREQUENCIES (CM**-1)" in line or \
               "Harmonic frequencies" in line:
                in_freq_section = True
                start_idx = i + 1
                break
        
        if in_freq_section:
            for line in lines[start_idx:start_idx+500]:
                # Skip header and separator lines
                if "---" in line or not line.strip():
                    continue
                
                # Look for frequency lines
                parts = line.split()
                if len(parts) >= 2:
                    # Format: Mode_Num Frequency(cm^-1) IR_Intensity ...
                    try:
                        mode_num = int(parts[0])
                        freq = float(parts[1])
                        
                        # Extract IR intensity if present
                        ir_intensity = 0.0
                        if len(parts) >= 4:
                            try:
                                # Format varies: some have "IR_Intensity" label
                                ir_intensity = float(parts[3])
                            except (ValueError, IndexError):
                                ir_intensity = 0.0
                        
                        # Extract Raman activity if present
                        raman_activity = 0.0
                        if len(parts) >= 6:
                            try:
                                raman_activity = float(parts[5])
                            except (ValueError, IndexError):
                                raman_activity = 0.0
                        
                        # Normalize coordinates
                        freq = round(freq, 2)
                        ir_intensity = round(ir_intensity, 4)
                        raman_activity = round(raman_activity, 6)
                        
                        # Create mode object
                        mode = VibrationalMode(
                            frequency=freq,
                            intensity=ir_intensity,
                            raman_activity=raman_activity,
                            mode_index=mode_idx
                        )
                        modes.append(mode)
                        
                        ir_freqs.append(freq)
                        ir_ints.append(ir_intensity)
                        raman_freqs.append(freq)
                        raman_acts.append(raman_activity)
                        
                        mode_idx += 1
                        
                        # Stop if we've read enough modes
                        if mode_idx > 1000:
                            break
                            
                    except (ValueError, IndexError):
                        continue
        
        # === Step 2: Determine frequency range ===
        if ir_freqs:
            min_freq = min(ir_freqs) * 0.8  # 20% buffer below
            max_freq = max(ir_freqs) * 1.2  # 20% buffer above
        else:
            min_freq, max_freq = 0, 4000
        
        # === Step 3: Extract computation info ===
        converged = "ORCA finished by error termination" not in content
        
        # Parse timing information
        comp_time = 0.0
        for line in lines:
            if "Total Runtime" in line or "Execution time" in line:
                try:
                    parts = line.split()
                    for j, part in enumerate(parts):
                        if part == "seconds" and j > 0:
                            comp_time = float(parts[j-1])
                            break
                except:
                    pass
        
        logger.info(f"Parsed {len(modes)} vibrational modes")
        logger.info(f"Frequency range: {min_freq:.1f} - {max_freq:.1f} cm^-1")
        logger.info(f"Max IR intensity: {max(ir_ints) if ir_ints else 0:.2f} km/mol")
        
        spectrum_data = SpectrumData(
            modes=modes,
            ir_frequencies=ir_freqs,
            ir_intensities=ir_ints,
            raman_frequencies=raman_freqs,
            raman_activities=raman_acts,
            frequency_range=(round(min_freq, 1), round(max_freq, 1)),
            computation_time=comp_time,
            converged=converged
        )
        
        return spectrum_data
        
    except Exception as e:
        logger.error(f"Spectrum parsing error: {e}")
        return SpectrumData([], [], [], [], [], (0, 0), 0.0, False)


# ============================================================================
# SPECTRUM CALCULATION & BROADENING
# ============================================================================

def calculate_ir_spectrum(
    spectrum_data: SpectrumData,
    frequency_range: Tuple[float, float] = None,
    resolution: int = 1,  # cm^-1 per point
    linewidth: float = 15.0  # FWHM in cm^-1
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate IR spectrum with Lorentzian broadening
    
    Args:
        spectrum_data: SpectrumData object
        frequency_range: (min, max) in cm^-1 (uses data range if None)
        resolution: Points per cm^-1
        linewidth: Full width at half maximum (FWHM)
    
    Returns:
        (frequencies, intensities) as numpy arrays
    """
    if frequency_range is None:
        frequency_range = spectrum_data.frequency_range
    
    # Generate frequency axis
    min_freq, max_freq = frequency_range
    num_points = int((max_freq - min_freq) * resolution) + 1
    frequencies = np.linspace(min_freq, max_freq, num_points)
    
    # Initialize intensity array
    intensities = np.zeros_like(frequencies, dtype=float)
    
    # Apply Lorentzian broadening to each mode
    gamma = linewidth / 2.0  # Half-width at half-maximum
    
    for mode in spectrum_data.modes:
        nu = mode.frequency
        I_0 = mode.intensity
        
        # Lorentzian function: I = I_0 * gamma^2 / ((nu - nu0)^2 + gamma^2)
        lorentzian = (gamma ** 2) / ((frequencies - nu) ** 2 + gamma ** 2)
        intensities += I_0 * lorentzian
    
    # Normalize intensities to 0-100 scale
    if intensities.max() > 0:
        intensities = (intensities / intensities.max()) * 100.0
    
    return frequencies, intensities


def calculate_raman_spectrum(
    spectrum_data: SpectrumData,
    frequency_range: Tuple[float, float] = None,
    resolution: int = 1,
    linewidth: float = 8.0  # Raman typically narrower than IR
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate Raman spectrum with Lorentzian broadening
    (Similar to IR but uses Raman activity instead of IR intensity)
    """
    if frequency_range is None:
        frequency_range = spectrum_data.frequency_range
    
    min_freq, max_freq = frequency_range
    num_points = int((max_freq - min_freq) * resolution) + 1
    frequencies = np.linspace(min_freq, max_freq, num_points)
    
    intensities = np.zeros_like(frequencies, dtype=float)
    gamma = linewidth / 2.0
    
    for mode in spectrum_data.modes:
        nu = mode.frequency
        I_0 = mode.raman_activity * 100  # Scale up Raman activity
        
        lorentzian = (gamma ** 2) / ((frequencies - nu) ** 2 + gamma ** 2)
        intensities += I_0 * lorentzian
    
    if intensities.max() > 0:
        intensities = (intensities / intensities.max()) * 100.0
    
    return frequencies, intensities


# ============================================================================
# MATPLOTLIB VISUALIZATION
# ============================================================================

def plot_ir_spectrum(
    spectrum_data: SpectrumData,
    figure_size: Tuple[int, int] = (10, 6),
    show_peaks: bool = True,
    title: str = "IR Spectrum"
) -> Figure:
    """
    Create matplotlib figure for IR spectrum
    
    Returns:
        matplotlib.figure.Figure object
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    
    fig = Figure(figsize=figure_size, dpi=100)
    ax = fig.add_subplot(111)
    
    # Calculate IR spectrum
    frequencies, intensities = calculate_ir_spectrum(spectrum_data)
    
    # Plot spectrum
    ax.plot(frequencies, intensities, 'b-', linewidth=2, label='IR Spectrum')
    
    # Plot peak positions if requested
    if show_peaks:
        ax.scatter(spectrum_data.ir_frequencies, spectrum_data.ir_intensities,
                  color='red', s=50, marker='x', label='Peak positions', zorder=5)
    
    # Fill under curve
    ax.fill_between(frequencies, intensities, alpha=0.3, color='blue')
    
    # [Fix] Add Fingerprint Region Label
    # Draw a shaded region for fingerprint (400-1500 cm-1)
    ax.axvspan(1500, 400, color='gray', alpha=0.1)
    ax.text(950, 95, "Fingerprint Region", fontsize=10, color='gray', ha='center', style='italic')

    # [Fix] Add C=O Stretch Label if peak exists near 1720
    # Search for strongest peak in C=O region (1680-1760)
    co_peak = None
    max_co_int = 0
    for freq, inten in zip(spectrum_data.ir_frequencies, spectrum_data.ir_intensities):
        if 1680 <= freq <= 1760 and inten > 10: # Threshold
            if inten > max_co_int:
                max_co_int = inten
                co_peak = (freq, inten)
    
    if co_peak:
        # Normalize intensity for annotation position (since Y is 0-100%)
        # But spectrum_data.ir_intensities are in km/mol, while plot is normalized.
        # We need to map km/mol to % relative to max intensity.
        max_total_int = max(spectrum_data.ir_intensities) if spectrum_data.ir_intensities else 1.0
        norm_y = (co_peak[1] / max_total_int) * 100.0
        
        ax.annotate("C=O stretch", xy=(co_peak[0], norm_y), xytext=(co_peak[0], norm_y+15),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), 
                    ha='center', fontsize=9, fontweight='bold')

    
    # [Fix] Add Fingerprint Region Label
    # Draw a shaded region for fingerprint (400-1500 cm-1)
    ax.axvspan(1500, 400, color='gray', alpha=0.1)
    ax.text(950, 95, "Fingerprint Region", fontsize=10, color='gray', ha='center', style='italic')

    # [Fix] Add C=O Stretch Label if peak exists near 1720
    # Search for strongest peak in C=O region (1680-1760)
    co_peak = None
    max_co_int = 0
    for freq, inten in zip(spectrum_data.ir_frequencies, spectrum_data.ir_intensities):
        if 1680 <= freq <= 1760 and inten > 10: # Threshold
            if inten > max_co_int:
                max_co_int = inten
                co_peak = (freq, inten)
    
    if co_peak:
        # Normalize intensity for annotation position (since Y is 0-100%)
        # But spectrum_data.ir_intensities are in km/mol, while plot is normalized.
        # We need to map km/mol to % relative to max intensity.
        max_total_int = max(spectrum_data.ir_intensities) if spectrum_data.ir_intensities else 1.0
        norm_y = (co_peak[1] / max_total_int) * 100.0
        
        ax.annotate("C=O stretch", xy=(co_peak[0], norm_y), xytext=(co_peak[0], norm_y+15),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), 
                    ha='center', fontsize=9, fontweight='bold')

    
    # [Fix] Add Fingerprint Region Label
    # Draw a shaded region for fingerprint (400-1500 cm-1)
    ax.axvspan(1500, 400, color='gray', alpha=0.1)
    ax.text(950, 95, "Fingerprint Region", fontsize=10, color='gray', ha='center', style='italic')

    # [Fix] Add C=O Stretch Label if peak exists near 1720
    # Search for strongest peak in C=O region (1680-1760)
    co_peak = None
    max_co_int = 0
    for freq, inten in zip(spectrum_data.ir_frequencies, spectrum_data.ir_intensities):
        if 1680 <= freq <= 1760 and inten > 10: # Threshold
            if inten > max_co_int:
                max_co_int = inten
                co_peak = (freq, inten)
    
    if co_peak:
        # Normalize intensity for annotation position (since Y is 0-100%)
        # But spectrum_data.ir_intensities are in km/mol, while plot is normalized.
        # We need to map km/mol to % relative to max intensity.
        max_total_int = max(spectrum_data.ir_intensities) if spectrum_data.ir_intensities else 1.0
        norm_y = (co_peak[1] / max_total_int) * 100.0
        
        ax.annotate("C=O stretch", xy=(co_peak[0], norm_y), xytext=(co_peak[0], norm_y+15),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), 
                    ha='center', fontsize=9, fontweight='bold')

    
    # [Fix] Add Fingerprint Region Label
    # Draw a shaded region for fingerprint (400-1500 cm-1)
    ax.axvspan(1500, 400, color='gray', alpha=0.1)
    ax.text(950, 95, "Fingerprint Region", fontsize=10, color='gray', ha='center', style='italic')

    # [Fix] Add C=O Stretch Label if peak exists near 1720
    # Search for strongest peak in C=O region (1680-1760)
    co_peak = None
    max_co_int = 0
    for freq, inten in zip(spectrum_data.ir_frequencies, spectrum_data.ir_intensities):
        if 1680 <= freq <= 1760 and inten > 10: # Threshold
            if inten > max_co_int:
                max_co_int = inten
                co_peak = (freq, inten)
    
    if co_peak:
        # Normalize intensity for annotation position (since Y is 0-100%)
        # But spectrum_data.ir_intensities are in km/mol, while plot is normalized.
        # We need to map km/mol to % relative to max intensity.
        max_total_int = max(spectrum_data.ir_intensities) if spectrum_data.ir_intensities else 1.0
        norm_y = (co_peak[1] / max_total_int) * 100.0
        
        ax.annotate("C=O stretch", xy=(co_peak[0], norm_y), xytext=(co_peak[0], norm_y+15),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), 
                    ha='center', fontsize=9, fontweight='bold')

    
    # Formatting
    ax.set_xlabel('Wavenumber (cm⁻¹)', fontsize=12)
    ax.set_ylabel('Intensity (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10)
    ax.set_xlim(spectrum_data.frequency_range)
    ax.set_ylim(-5, 105)
    
    # Invert X-axis (standard IR spectrum convention)
    ax.invert_xaxis()
    
    fig.tight_layout()
    return fig


def plot_raman_spectrum(
    spectrum_data: SpectrumData,
    figure_size: Tuple[int, int] = (10, 6),
    show_peaks: bool = True,
    title: str = "Raman Spectrum"
) -> Figure:
    """
    Create matplotlib figure for Raman spectrum
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    
    fig = Figure(figsize=figure_size, dpi=100)
    ax = fig.add_subplot(111)
    
    # Calculate Raman spectrum
    frequencies, intensities = calculate_raman_spectrum(spectrum_data)
    
    # Plot spectrum
    ax.plot(frequencies, intensities, 'g-', linewidth=2, label='Raman Spectrum')
    
    # Plot peak positions
    if show_peaks:
        # S9 fix: normalize raman_activities to 0-100 scale to match broadened spectrum
        raw_acts = np.array(spectrum_data.raman_activities)
        if raw_acts.max() > 0:
            norm_acts = (raw_acts / raw_acts.max()) * 100.0
        else:
            norm_acts = raw_acts
        ax.scatter(spectrum_data.raman_frequencies, norm_acts,
                  color='darkgreen', s=50, marker='x', label='Peak positions', zorder=5)

        # [Fix] Add Peak Labels (Values)
        for freq, act in zip(spectrum_data.raman_frequencies, norm_acts):
            if act > 5.0:  # Show label for significant peaks
                ax.text(freq, act + 3, f"{freq:.0f}", ha='center', va='bottom', 
                       fontsize=8, rotation=90, color='darkgreen')

        # [Fix] Add Peak Labels (Values)
        for freq, act in zip(spectrum_data.raman_frequencies, norm_acts):
            if act > 5.0:  # Show label for significant peaks
                ax.text(freq, act + 3, f"{freq:.0f}", ha='center', va='bottom', 
                       fontsize=8, rotation=90, color='darkgreen')

        # [Fix] Add Peak Labels (Values)
        for freq, act in zip(spectrum_data.raman_frequencies, norm_acts):
            if act > 5.0:  # Show label for significant peaks
                ax.text(freq, act + 3, f"{freq:.0f}", ha='center', va='bottom', 
                       fontsize=8, rotation=90, color='darkgreen')

        # [Fix] Add Peak Labels (Values)
        for freq, act in zip(spectrum_data.raman_frequencies, norm_acts):
            if act > 5.0:  # Show label for significant peaks
                ax.text(freq, act + 3, f"{freq:.0f}", ha='center', va='bottom', 
                       fontsize=8, rotation=90, color='darkgreen')
    
    # Fill under curve
    ax.fill_between(frequencies, intensities, alpha=0.3, color='green')
    
    # Formatting
    ax.set_xlabel('Wavenumber (cm⁻¹)', fontsize=12)
    ax.set_ylabel('Intensity (a.u.)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10)
    ax.set_xlim(spectrum_data.frequency_range)
    ax.set_ylim(-5, 105)
    
    fig.tight_layout()
    return fig


def plot_both_spectra(
    spectrum_data: SpectrumData,
    figure_size: Tuple[int, int] = (14, 10)
) -> Figure:
    """
    Create side-by-side IR and Raman spectra
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    
    fig = Figure(figsize=figure_size, dpi=100)
    
    # IR spectrum
    ax_ir = fig.add_subplot(211)
    ir_freq, ir_int = calculate_ir_spectrum(spectrum_data)
    ax_ir.plot(ir_freq, ir_int, 'b-', linewidth=2)
    ax_ir.fill_between(ir_freq, ir_int, alpha=0.3, color='blue')
    ax_ir.scatter(spectrum_data.ir_frequencies, spectrum_data.ir_intensities,
                 color='red', s=40, marker='x', zorder=5)
    ax_ir.set_ylabel('Intensity (%)', fontsize=11)
    ax_ir.set_title('IR Spectrum', fontsize=12, fontweight='bold')
    ax_ir.grid(True, alpha=0.3)
    ax_ir.set_xlim(spectrum_data.frequency_range)
    ax_ir.invert_xaxis()
    
    # Raman spectrum
    ax_raman = fig.add_subplot(212)
    raman_freq, raman_int = calculate_raman_spectrum(spectrum_data)
    ax_raman.plot(raman_freq, raman_int, 'g-', linewidth=2)
    ax_raman.fill_between(raman_freq, raman_int, alpha=0.3, color='green')
    # S9 fix: normalize raman_activities to match 0-100 broadened scale
    raw_acts = np.array(spectrum_data.raman_activities)
    if raw_acts.max() > 0:
        norm_acts = (raw_acts / raw_acts.max()) * 100.0
    else:
        norm_acts = raw_acts
    ax_raman.scatter(spectrum_data.raman_frequencies, norm_acts,
                    color='darkgreen', s=40, marker='x', zorder=5)
    ax_raman.set_xlabel('Wavenumber (cm⁻¹)', fontsize=11)
    ax_raman.set_ylabel('Intensity (a.u.)', fontsize=11)
    ax_raman.set_title('Raman Spectrum', fontsize=12, fontweight='bold')
    ax_raman.grid(True, alpha=0.3)
    ax_raman.set_xlim(spectrum_data.frequency_range)
    
    fig.tight_layout()
    return fig


# ============================================================================
# SPECTRUM VIEWER WIDGET (PyQt6)
# ============================================================================

if PYQT_AVAILABLE:
    class SpectrumViewerWidget(QWidget):
        """Interactive spectrum viewer for PyQt6"""
        
        def __init__(self, spectrum_data: SpectrumData = None):
            super().__init__()
            self.spectrum_data = spectrum_data
            self.init_ui()
        
        def init_ui(self):
            """Initialize UI components"""
            layout = QVBoxLayout()
            
            # Control panel
            control_layout = QHBoxLayout()
            
            # Spectrum type selector
            self.spectrum_combo = QComboBox()
            self.spectrum_combo.addItems(["IR Spectrum", "Raman Spectrum", "Both (stacked)"])
            self.spectrum_combo.currentIndexChanged.connect(self.update_plot)
            control_layout.addWidget(QLabel("View:"))
            control_layout.addWidget(self.spectrum_combo)
            
            # Linewidth control
            self.linewidth_spin = QDoubleSpinBox()
            self.linewidth_spin.setMinimum(1.0)
            self.linewidth_spin.setMaximum(100.0)
            self.linewidth_spin.setValue(15.0)
            self.linewidth_spin.setSingleStep(1.0)
            self.linewidth_spin.valueChanged.connect(self.update_plot)
            control_layout.addWidget(QLabel("Linewidth (cm⁻¹):"))
            control_layout.addWidget(self.linewidth_spin)
            
            # Resolution control
            self.resolution_spin = QSpinBox()
            self.resolution_spin.setMinimum(1)
            self.resolution_spin.setMaximum(10)
            self.resolution_spin.setValue(1)
            self.resolution_spin.valueChanged.connect(self.update_plot)
            control_layout.addWidget(QLabel("Resolution:"))
            control_layout.addWidget(self.resolution_spin)
            
            layout.addLayout(control_layout)
            
            # Matplotlib canvas
            if MATPLOTLIB_AVAILABLE:
                self.figure = Figure(figsize=(10, 6), dpi=100)
                self.canvas = FigureCanvas(self.figure)
                layout.addWidget(self.canvas)
            
            self.setLayout(layout)
        
        def set_spectrum_data(self, spectrum_data: SpectrumData):
            """Update spectrum data and refresh plot"""
            self.spectrum_data = spectrum_data
            self.update_plot()
        
        def update_plot(self):
            """Redraw spectrum based on current settings"""
            if self.spectrum_data is None or len(self.spectrum_data.modes) == 0:
                return
            
            spectrum_type = self.spectrum_combo.currentIndex()
            linewidth = self.linewidth_spin.value()
            resolution = self.resolution_spin.value()
            
            self.figure.clear()
            
            if spectrum_type == 0:  # IR
                ax = self.figure.add_subplot(111)
                ir_freq, ir_int = calculate_ir_spectrum(
                    self.spectrum_data,
                    linewidth=linewidth,
                    resolution=resolution
                )
                ax.plot(ir_freq, ir_int, 'b-', linewidth=2)
                ax.fill_between(ir_freq, ir_int, alpha=0.3, color='blue')
                ax.scatter(self.spectrum_data.ir_frequencies, 
                          self.spectrum_data.ir_intensities,
                          color='red', s=30, marker='x')
                ax.set_ylabel('Intensity (%)')
                ax.set_title('IR Spectrum')
                ax.invert_xaxis()
            
            elif spectrum_type == 1:  # Raman
                ax = self.figure.add_subplot(111)
                raman_freq, raman_int = calculate_raman_spectrum(
                    self.spectrum_data,
                    linewidth=linewidth,
                    resolution=resolution
                )
                ax.plot(raman_freq, raman_int, 'g-', linewidth=2)
                ax.fill_between(raman_freq, raman_int, alpha=0.3, color='green')
                ax.scatter(self.spectrum_data.raman_frequencies, 
                          self.spectrum_data.raman_activities,
                          color='darkgreen', s=30, marker='x')
                ax.set_ylabel('Intensity (a.u.)')
                ax.set_title('Raman Spectrum')
            
            else:  # Both
                ax_ir = self.figure.add_subplot(211)
                ir_freq, ir_int = calculate_ir_spectrum(
                    self.spectrum_data,
                    linewidth=linewidth,
                    resolution=resolution
                )
                ax_ir.plot(ir_freq, ir_int, 'b-', linewidth=2)
                ax_ir.fill_between(ir_freq, ir_int, alpha=0.3, color='blue')
                ax_ir.set_ylabel('IR Intensity (%)')
                ax_ir.set_title('IR Spectrum')
                ax_ir.invert_xaxis()
                ax_ir.grid(True, alpha=0.3)
                
                ax_raman = self.figure.add_subplot(212)
                raman_freq, raman_int = calculate_raman_spectrum(
                    self.spectrum_data,
                    linewidth=linewidth,
                    resolution=resolution
                )
                ax_raman.plot(raman_freq, raman_int, 'g-', linewidth=2)
                ax_raman.fill_between(raman_freq, raman_int, alpha=0.3, color='green')
                ax_raman.set_ylabel('Raman Intensity (a.u.)')
                ax_raman.set_xlabel('Wavenumber (cm⁻¹)')
                ax_raman.set_title('Raman Spectrum')
                ax_raman.grid(True, alpha=0.3)
            
            if spectrum_type != 2:
                ax.set_xlabel('Wavenumber (cm⁻¹)')
                ax.grid(True, alpha=0.3)
                ax.set_xlim(self.spectrum_data.frequency_range)
                ax.set_ylim(-5, 105)
            
            self.figure.tight_layout()
            self.canvas.draw()


# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="IR/Raman Spectrum Analyzer")
    parser.add_argument("orca_file", nargs="?", default=None, help="ORCA .out file path")
    args = parser.parse_args()
    
    test_path = Path(args.orca_file) if args.orca_file else _SCRIPT_DIR / "test.out"
    if test_path.exists():
        spec_data = parse_orca_frequencies(test_path)
        logger.info(f"Parsed {len(spec_data.modes)} vibrational modes")
        logger.info(f"IR frequencies: {len(spec_data.ir_frequencies)}")
        logger.info(f"Raman frequencies: {len(spec_data.raman_frequencies)}")
    else:
        logger.info("No test.out file found - module loaded successfully")

def create_benzene_mock_data() -> SpectrumData:
    """
    Create high-precision mock data for Benzene (C6H6)
    Used when ORCA calculation is not available but spectrum display is needed.
    
    Features:
    - No C=O peak at 1700 cm-1
    - C-H out-of-plane bending at 674 cm-1
    - Strong Raman breathing mode at 992 cm-1
    """
    modes = []
    
    # Define Benzene characteristic peaks
    # Format: (Frequency, IR_Intensity, Raman_Activity)
    peaks = [
        (404.0, 0.0, 0.0),      # E2u
        (606.0, 0.0, 0.0),      # E2g
        (674.0, 45.0, 0.0),     # A2u (C-H bending, IR active)
        (849.0, 0.0, 0.0),      # E1g
        (992.0, 0.0, 100.0),    # A1g (Ring breathing, Raman active, very strong)
        (1037.0, 12.0, 0.0),    # E1u (C-H in-plane)
        (1178.0, 0.0, 5.0),     # E2g
        (1309.0, 0.0, 0.0),     # A2g
        (1482.0, 15.0, 0.0),    # E1u (C-C stretching)
        (1599.0, 0.0, 15.0),    # E2g (C-C stretching)
        (3048.0, 30.0, 45.0),   # E1u (C-H stretching)
        (3064.0, 0.0, 0.0),     # B1u
    ]
    
    mode_idx = 0
    ir_freqs = []
    ir_ints = []
    raman_freqs = []
    raman_acts = []
    
    for freq, ir, raman in peaks:
        mode = VibrationalMode(
            frequency=freq,
            intensity=ir,
            raman_activity=raman,
            mode_index=mode_idx
        )
        modes.append(mode)
        
        if ir > 0.01:
            ir_freqs.append(freq)
            ir_ints.append(ir)
        
        if raman > 0.001:
            raman_freqs.append(freq)
            raman_acts.append(raman)
            
        mode_idx += 1
        
    return SpectrumData(
        modes=modes,
        ir_frequencies=ir_freqs,
        ir_intensities=ir_ints,
        raman_frequencies=raman_freqs,
        raman_activities=raman_acts,
        frequency_range=(400.0, 3200.0),
        computation_time=0.05,
        converged=True
    )
