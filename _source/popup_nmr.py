# popup_nmr.py (v1.0 - NMR Spectrum Analysis Popup)
"""
ChemDraw Pro: NMR Spectrum Viewer with Lorentzian Simulation
- ¹H, ¹³C, ¹⁹F NMR spectrum parsing from ORCA
- Lorentzian peak simulation
- Interactive linewidth and frequency adjustment
- Chemical shift and coupling constant analysis
"""

from pathlib import Path
from typing import Optional, List, Tuple, Dict
import re
import numpy as np
from dataclasses import dataclass

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QComboBox, QSpinBox, QDoubleSpinBox, 
                                 QMessageBox, QFileDialog, QTabWidget, QTableWidget,
                                 QTableWidgetItem, QTextEdit, QSlider)
    from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread
    from PyQt6.QtGui import QIcon
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


@dataclass
class NMRSignal:
    """Single NMR signal: chemical shift, intensity, multiplicity"""
    nucleus: str  # ¹H, ¹³C, ¹⁹F
    chemical_shift: float  # ppm
    intensity: float  # relative intensity
    coupling_constant: float = 0.0  # Hz
    multiplicity: str = "s"  # s, d, t, q, m


class NMRParser:
    """Parse NMR data from ORCA output file"""
    
    @staticmethod
    def parse_nmr_from_orca(filepath: Path) -> Dict[str, List[NMRSignal]]:
        """
        Extract NMR parameters from ORCA calculation result
        Returns dict: {nucleus_type: [NMRSignal, ...]}
        """
        nmr_data = {"1H": [], "13C": [], "19F": []}
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse ¹H NMR
            nmr_data["1H"] = NMRParser._extract_h_nmr(content)
            
            # Parse ¹³C NMR
            nmr_data["13C"] = NMRParser._extract_c_nmr(content)
            
            # Parse ¹⁹F NMR
            nmr_data["19F"] = NMRParser._extract_f_nmr(content)
            
        except Exception as e:
            print(f"[NMRParser] Error parsing file: {e}")
        
        return nmr_data
    
    @staticmethod
    def _extract_h_nmr(content: str) -> List[NMRSignal]:
        """Extract ¹H NMR signals"""
        signals = []
        
        # Pattern for ¹H chemical shifts (typical ranges 0-15 ppm)
        # Look for lines like "  Nucleus 1H : CS = 5.234"
        pattern = r'(?:¹H|1H).*?CS\s*=\s*([\d.-]+)'
        matches = re.finditer(pattern, content, re.IGNORECASE)
        
        for i, match in enumerate(matches):
            cs = float(match.group(1))
            signal = NMRSignal(
                nucleus="1H",
                chemical_shift=cs,
                intensity=1.0,
                multiplicity="s"
            )
            signals.append(signal)
        
        return signals
    
    @staticmethod
    def _extract_c_nmr(content: str) -> List[NMRSignal]:
        """Extract ¹³C NMR signals"""
        signals = []
        
        # Pattern for ¹³C chemical shifts (typical ranges 0-200 ppm)
        pattern = r'(?:¹³C|13C).*?CS\s*=\s*([\d.-]+)'
        matches = re.finditer(pattern, content, re.IGNORECASE)
        
        for i, match in enumerate(matches):
            cs = float(match.group(1))
            signal = NMRSignal(
                nucleus="13C",
                chemical_shift=cs,
                intensity=1.0,
                multiplicity="s"
            )
            signals.append(signal)
        
        return signals
    
    @staticmethod
    def _extract_f_nmr(content: str) -> List[NMRSignal]:
        """Extract ¹⁹F NMR signals"""
        signals = []
        
        # Pattern for ¹⁹F chemical shifts (typical ranges -300 to 100 ppm)
        pattern = r'(?:¹⁹F|19F).*?CS\s*=\s*([\d.-]+)'
        matches = re.finditer(pattern, content, re.IGNORECASE)
        
        for i, match in enumerate(matches):
            cs = float(match.group(1))
            signal = NMRSignal(
                nucleus="19F",
                chemical_shift=cs,
                intensity=1.0,
                multiplicity="s"
            )
            signals.append(signal)
        
        return signals


class NMRSpectrumSimulator:
    """Generate synthetic NMR spectrum using Lorentzian lineshape"""
    
    @staticmethod
    def lorentzian(freq: np.ndarray, center: float, width: float, intensity: float) -> np.ndarray:
        """Lorentzian lineshape"""
        return intensity * (width / np.pi) / ((freq - center) ** 2 + width ** 2)
    
    @staticmethod
    def simulate_spectrum(signals: List[NMRSignal], nucleus: str,
                         freq_min: float, freq_max: float, 
                         linewidth: float = 1.0, points: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Simulate NMR spectrum with Lorentzian broadening
        Returns: (frequency_array, intensity_array)
        """
        freq = np.linspace(freq_min, freq_max, points)
        intensity = np.zeros_like(freq, dtype=float)
        
        # Add contribution from each signal
        for signal in signals:
            if signal.nucleus == nucleus:
                intensity += NMRSpectrumSimulator.lorentzian(
                    freq, signal.chemical_shift, linewidth, signal.intensity
                )
        
        # Reverse x-axis for NMR convention (high field on left)
        return freq[::-1], intensity[::-1]


class NMRPlottingWidget(FigureCanvas):
    """Matplotlib widget for NMR spectrum display"""
    
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
        self.setSizePolicy(4, 4)  # expanding
    
    def plot_nmr_spectrum(self, freq: np.ndarray, intensity: np.ndarray, 
                          nucleus: str = "1H", linewidth_hz: float = 1.0):
        """Plot NMR spectrum"""
        self.ax.clear()
        
        # Plot spectrum
        self.ax.fill_between(freq, intensity, alpha=0.3, color='blue')
        self.ax.plot(freq, intensity, color='blue', linewidth=1.5)
        
        # Labels and title
        self.ax.set_xlabel('Chemical Shift (ppm)', fontsize=12)
        self.ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        self.ax.set_title(f'{nucleus} NMR Spectrum (Linewidth: {linewidth_hz:.1f} Hz)', fontsize=13)
        self.ax.invert_xaxis()  # NMR convention
        self.ax.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_stick_spectrum(self, signals: List[NMRSignal], nucleus: str):
        """Plot stick spectrum (peaks only)"""
        self.ax.clear()
        
        filtered_signals = [s for s in signals if s.nucleus == nucleus]
        
        if filtered_signals:
            shifts = [s.chemical_shift for s in filtered_signals]
            intensities = [s.intensity for s in filtered_signals]
            
            self.ax.vlines(shifts, 0, intensities, colors='red', linewidth=2)
            self.ax.scatter(shifts, intensities, color='red', s=50, zorder=5)
            
            # Add shift labels
            for shift, intensity in zip(shifts, intensities):
                self.ax.text(shift, intensity + 0.05, f'{shift:.2f}', 
                           ha='center', va='bottom', fontsize=9)
        
        self.ax.set_xlabel('Chemical Shift (ppm)', fontsize=12)
        self.ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        self.ax.set_title(f'{nucleus} NMR Peaks', fontsize=13)
        self.ax.invert_xaxis()
        self.ax.grid(True, alpha=0.3)
        self.ax.set_ylim(bottom=0)
        
        self.figure.tight_layout()
        self.draw()


class NMRPopup(QDialog):
    """NMR spectrum viewer with Lorentzian simulation"""
    
    nmr_data_loaded = pyqtSignal(dict)
    
    def __init__(self, orca_filepath: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.nmr_signals = {}
        self.current_nucleus = "1H"
        self.linewidth = 1.0
        
        if orca_filepath:
            self.load_nmr_data(orca_filepath)
        
        self.init_ui()
        self.setWindowTitle("NMR Spectrum Analysis")
        self.resize(1000, 700)
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        
        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("NMR Spectrum Simulation")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        self.info_label = QLabel("No data loaded")
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        main_layout.addLayout(title_layout)
        
        # Tab widget
        self.tabs = QTabWidget()
        
        # Plot tab
        plot_tab = self.create_plot_tab()
        self.tabs.addTab(plot_tab, "Spectrum")
        
        # Signals table
        signals_tab = self.create_signals_table()
        self.tabs.addTab(signals_tab, "Chemical Shifts")
        
        main_layout.addWidget(self.tabs)
        
        # Controls
        control_layout = self.create_control_panel()
        main_layout.addLayout(control_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load ORCA Output...")
        load_btn.clicked.connect(self.load_orca_file)
        button_layout.addWidget(load_btn)
        
        export_btn = QPushButton("Export Spectrum...")
        export_btn.clicked.connect(self.export_spectrum)
        button_layout.addWidget(export_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
    def create_plot_tab(self) -> QTabWidget:
        """Create plot visualization tab"""
        layout = QVBoxLayout()
        
        # Plotting options
        options_layout = QHBoxLayout()
        
        type_label = QLabel("Plot Type:")
        self.plot_type = QComboBox()
        self.plot_type.addItems(["Simulated Spectrum", "Stick Spectrum"])
        self.plot_type.currentIndexChanged.connect(self.update_plot)
        
        options_layout.addWidget(type_label)
        options_layout.addWidget(self.plot_type)
        options_layout.addStretch()
        
        layout.addLayout(options_layout)
        
        # Canvas
        self.nmr_canvas = NMRPlottingWidget()
        layout.addWidget(self.nmr_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_signals_table(self) -> QTabWidget:
        """Create signals table"""
        layout = QVBoxLayout()
        
        self.signals_table = QTableWidget()
        self.signals_table.setColumnCount(4)
        self.signals_table.setHorizontalHeaderLabels([
            "Nucleus", "Shift (ppm)", "Intensity", "Multiplicity"
        ])
        
        layout.addWidget(self.signals_table)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_control_panel(self) -> QHBoxLayout:
        """Create control panel"""
        layout = QHBoxLayout()
        
        # Nucleus selector
        nucleus_label = QLabel("Nucleus:")
        self.nucleus_combo = QComboBox()
        self.nucleus_combo.addItems(["¹H (1H)", "¹³C (13C)", "¹⁹F (19F)"])
        self.nucleus_combo.currentIndexChanged.connect(self.on_nucleus_changed)
        
        layout.addWidget(nucleus_label)
        layout.addWidget(self.nucleus_combo)
        layout.addSpacing(20)
        
        # Linewidth control
        width_label = QLabel("Linewidth (Hz):")
        self.linewidth_spinner = QDoubleSpinBox()
        self.linewidth_spinner.setRange(0.1, 10.0)
        self.linewidth_spinner.setValue(self.linewidth)
        self.linewidth_spinner.setSingleStep(0.1)
        self.linewidth_spinner.valueChanged.connect(self.on_linewidth_changed)
        
        layout.addWidget(width_label)
        layout.addWidget(self.linewidth_spinner)
        layout.addStretch()
        
        return layout
    
    def load_orca_file(self):
        """Load ORCA output file"""
        filepath, _ = QFileDialog.getOpenFileName(self, "Select ORCA output", "",
                                                   "ORCA Files (*.out);;All Files (*)")
        if filepath:
            self.load_nmr_data(Path(filepath))
    
    def load_nmr_data(self, filepath: Path):
        """Load NMR data from ORCA file"""
        self.nmr_signals = NMRParser.parse_nmr_from_orca(filepath)
        
        # Update info
        total_signals = sum(len(v) for v in self.nmr_signals.values())
        self.info_label.setText(f"Loaded: {total_signals} signals from {filepath.name}")
        
        self.update_table()
        self.update_plot()
    
    def on_nucleus_changed(self):
        """Handle nucleus selection change"""
        combo_text = self.nucleus_combo.currentText()
        if "1H" in combo_text:
            self.current_nucleus = "1H"
        elif "13C" in combo_text:
            self.current_nucleus = "13C"
        elif "19F" in combo_text:
            self.current_nucleus = "19F"
        
        self.update_table()
        self.update_plot()
    
    def on_linewidth_changed(self):
        """Handle linewidth change"""
        self.linewidth = self.linewidth_spinner.value()
        self.update_plot()
    
    def update_table(self):
        """Update signals table"""
        signals = self.nmr_signals.get(self.current_nucleus, [])
        self.signals_table.setRowCount(len(signals))
        
        for row, signal in enumerate(signals):
            self.signals_table.setItem(row, 0, QTableWidgetItem(signal.nucleus))
            self.signals_table.setItem(row, 1, QTableWidgetItem(f"{signal.chemical_shift:.2f}"))
            self.signals_table.setItem(row, 2, QTableWidgetItem(f"{signal.intensity:.3f}"))
            self.signals_table.setItem(row, 3, QTableWidgetItem(signal.multiplicity))
    
    def update_plot(self):
        """Update spectrum plot"""
        signals = self.nmr_signals.get(self.current_nucleus, [])
        
        if not signals:
            self.nmr_canvas.ax.clear()
            self.nmr_canvas.ax.text(0.5, 0.5, 'No data available',
                                   ha='center', va='center', transform=self.nmr_canvas.ax.transAxes)
            self.nmr_canvas.draw()
            return
        
        # Determine frequency range based on nucleus
        freq_ranges = {
            "1H": (0, 15),
            "13C": (0, 250),
            "19F": (-300, 100)
        }
        
        freq_min, freq_max = freq_ranges[self.current_nucleus]
        
        # Choose plot type
        if self.plot_type.currentIndex() == 0:  # Simulated
            freq, intensity = NMRSpectrumSimulator.simulate_spectrum(
                signals, self.current_nucleus, freq_min, freq_max, self.linewidth
            )
            self.nmr_canvas.plot_nmr_spectrum(freq, intensity, self.current_nucleus, self.linewidth)
        else:  # Stick
            self.nmr_canvas.plot_stick_spectrum(signals, self.current_nucleus)
    
    def export_spectrum(self):
        """Export spectrum to image"""
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Spectrum", "",
                                                   "PNG Image (*.png);;PDF (*.pdf)")
        if filepath:
            self.nmr_canvas.figure.savefig(filepath, dpi=300, bbox_inches='tight')
            QMessageBox.information(self, "Export", f"Spectrum saved to {filepath}")


def launch_nmr_viewer(orca_filepath: Optional[Path] = None, parent=None) -> NMRPopup:
    """Convenience function to launch NMR viewer"""
    popup = NMRPopup(orca_filepath, parent)
    popup.exec()
    return popup
