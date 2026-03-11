# popup_uvvis.py (v1.1 - UV-Vis Absorption Spectrum Analysis)
"""
ChemDraw Pro: UV-Vis Spectrum Viewer with TD-DFT Analysis
- Parse excited states from ORCA TD-DFT calculation
- Visualize electronic transition energies and oscillator strengths
- Gaussian broadening simulation
- Transition density analysis
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import re
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QComboBox, QDoubleSpinBox, QMessageBox,
                                 QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem)
    from PyQt6.QtCore import Qt, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


@dataclass
class ExcitedState:
    """Electronic excited state from TD-DFT"""
    state_id: int
    energy_ev: float  # excitation energy in eV
    wavelength_nm: float  # wavelength in nm
    oscillator_strength: float  # f
    main_configuration: str  # e.g., "HOMO -> LUMO"


class TDDFTParser:
    """Parse TD-DFT results from ORCA output"""
    
    @staticmethod
    def parse_excited_states(filepath: Path) -> List[ExcitedState]:
        """Extract excited states from ORCA TD-DFT calculation"""
        states = []
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Find TD-DFT section
            tddft_start = content.find("TD-DFT")
            if tddft_start == -1:
                tddft_start = content.find("TDDFT")
            
            if tddft_start == -1:
                return states
            
            # Extract excited state information
            # Pattern: State #, Energy (eV), f, Main config
            pattern = r'(?:State|Transition)\s+(\d+).*?(\d+\.?\d*)\s*eV.*?f\s*=\s*(\d+\.?\d+)'
            
            for match in re.finditer(pattern, content[tddft_start:], re.IGNORECASE | re.DOTALL):
                try:
                    state_id = int(match.group(1))
                    energy_ev = float(match.group(2))
                    f = float(match.group(3))
                    
                    # Calculate wavelength
                    wavelength_nm = 1240 / energy_ev if energy_ev > 0 else 0
                    
                    state = ExcitedState(
                        state_id=state_id,
                        energy_ev=energy_ev,
                        wavelength_nm=wavelength_nm,
                        oscillator_strength=f,
                        main_configuration="transition"
                    )
                    states.append(state)
                except:
                    pass
            
            # If no detailed parsing worked, try simpler pattern
            if not states:
                states = TDDFTParser._parse_simple_pattern(content)
        
        except Exception as e:
            logger.error(f"TDDFTParser error: {e}")
        
        return states
    
    @staticmethod
    def _parse_simple_pattern(content: str) -> List[ExcitedState]:
        """Fallback: simple pattern matching"""
        states = []
        
        # Look for any excited state information
        lines = content.split('\n')
        state_count = 0
        
        for i, line in enumerate(lines):
            # Look for energy or wavelength indicators
            if 'excited' in line.lower() or 'state' in line.lower():
                # Try to extract numbers
                numbers = re.findall(r'\d+\.?\d*', line)
                if len(numbers) >= 2:
                    try:
                        state_count += 1
                        energy_ev = float(numbers[0]) if float(numbers[0]) < 100 else float(numbers[0]) / 1000
                        f = float(numbers[1]) if len(numbers) > 1 else 0.1
                        
                        state = ExcitedState(
                            state_id=state_count,
                            energy_ev=energy_ev,
                            wavelength_nm=1240 / energy_ev if energy_ev > 0 else 0,
                            oscillator_strength=f,
                            main_configuration="detected"
                        )
                        states.append(state)
                    except:
                        pass
        
        return states


class UVVisSpectrumSimulator:
    """Generate UV-Vis spectrum with Gaussian broadening"""
    
    @staticmethod
    def gaussian(wavelength: np.ndarray, center: float, sigma: float, intensity: float) -> np.ndarray:
        """Gaussian lineshape"""
        return intensity * np.exp(-0.5 * ((wavelength - center) / sigma) ** 2)
    
    @staticmethod
    def simulate_spectrum(states: List[ExcitedState],
                         wavelength_min: float = 200,
                         wavelength_max: float = 800,
                         bandwidth: float = 20.0,
                         points: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Simulate UV-Vis absorption spectrum with Gaussian broadening
        Returns: (wavelength_array, absorption_array)
        """
        wavelengths = np.linspace(wavelength_min, wavelength_max, points)
        absorption = np.zeros_like(wavelengths, dtype=float)
        
        # Add contribution from each excited state
        for state in states:
            if wavelength_min <= state.wavelength_nm <= wavelength_max:
                # Gaussian broadening
                sigma = bandwidth / 4  # FWHM to sigma conversion
                absorption += UVVisSpectrumSimulator.gaussian(
                    wavelengths, state.wavelength_nm, sigma, state.oscillator_strength
                )
        
        return wavelengths, absorption


class UVVisPlottingWidget(FigureCanvas):
    """Matplotlib widget for UV-Vis spectrum"""
    
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
    
    def plot_uvvis_spectrum(self, wavelengths: np.ndarray, absorption: np.ndarray, bandwidth: float = 20):
        """Plot simulated UV-Vis spectrum (Dual-View: Linear & Log Scale)"""
        self.figure.clear()
        
        # 1. Linear Scale Plot
        ax1 = self.figure.add_subplot(121)
        ax1.fill_between(wavelengths, absorption, alpha=0.3, color='purple')
        ax1.plot(wavelengths, absorption, color='purple', linewidth=2)
        
        ax1.set_xlabel('Wavelength (nm)', fontsize=10)
        ax1.set_ylabel('Absorption (a.u.)', fontsize=10)
        ax1.set_title(f'Linear Scale', fontsize=11)
        ax1.grid(True, alpha=0.3)
        ax1.invert_xaxis()
        # [Fix] Optimize Y-axis range
        ax1.set_ylim(0, 10000)
        
        # 2. Log Scale Plot
        ax2 = self.figure.add_subplot(122)
        ax2.plot(wavelengths, absorption, color='darkviolet', linewidth=2)
        
        ax2.set_xlabel('Wavelength (nm)', fontsize=10)
        ax2.set_ylabel('Log Absorption', fontsize=10)
        ax2.set_title(f'Log Scale', fontsize=11)
        ax2.grid(True, alpha=0.3)
        ax2.set_yscale('log')
        ax2.invert_xaxis()
        # Log scale needs positive ylim
        ax2.set_ylim(1, 10000)
        
        self.figure.suptitle(f'UV-Vis Absorption Spectrum (Bandwidth: {bandwidth:.1f} nm)', fontsize=13)
        self.figure.tight_layout()
        self.draw()
    
    def plot_stick_spectrum(self, states: List[ExcitedState]):
        """Plot transition energies as stick spectrum"""
        self.ax.clear()
        
        if states:
            wavelengths = [s.wavelength_nm for s in states]
            f_values = [s.oscillator_strength for s in states]
            
            # Normalize for visualization
            max_f = max(f_values) if f_values else 1.0
            normalized_f = [f / max_f for f in f_values]
            
            self.ax.vlines(wavelengths, 0, normalized_f, colors='blue', linewidth=2)
            self.ax.scatter(wavelengths, normalized_f, color='blue', s=100, zorder=5)
            
            # Add labels
            for wl, f in zip(wavelengths, normalized_f):
                self.ax.text(wl, f + 0.05, f'{wl:.0f}', ha='center', va='bottom', fontsize=9)
        
        self.ax.set_xlabel('Wavelength (nm)', fontsize=12)
        self.ax.set_ylabel('Oscillator Strength (normalized)', fontsize=12)
        self.ax.set_title('Electronic Transitions', fontsize=13)
        self.ax.invert_xaxis()
        self.ax.grid(True, alpha=0.3, axis='y')
        self.ax.set_ylim(bottom=0)
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_molar_extinction(self, states: List[ExcitedState]):
        """Plot molar extinction coefficient estimate"""
        self.ax.clear()
        
        if states:
            wavelengths = [s.wavelength_nm for s in states]
            # Simple approximation: ε ≈ f * constant
            extinction = [s.oscillator_strength * 5000 for s in states]
            
            self.ax.bar(wavelengths, extinction, width=10, color='green', alpha=0.7)
            
        self.ax.set_xlabel('Wavelength (nm)', fontsize=12)
        self.ax.set_ylabel('Molar Extinction (L mol⁻¹ cm⁻¹)', fontsize=12)
        self.ax.set_title('Estimated Molar Extinction Coefficient', fontsize=13)
        self.ax.invert_xaxis()
        self.ax.grid(True, alpha=0.3, axis='y')
        
        self.figure.tight_layout()
        self.draw()


class UVVisPopup(QDialog):
    """UV-Vis spectrum viewer with TD-DFT analysis"""
    
    data_loaded = pyqtSignal(list)
    
    def __init__(self, orca_filepath: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.states = []
        self.bandwidth = 20.0
        
        if orca_filepath:
            self.load_uvvis_data(orca_filepath)
        
        self.init_ui()
        self.setWindowTitle("UV-Vis Absorption Analysis")
        self.resize(1000, 700)
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        
        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("UV-Vis Absorption Spectrum (TD-DFT)")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        self.info_label = QLabel("No data loaded")
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        main_layout.addLayout(title_layout)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Plot tab
        plot_tab = self.create_plot_tab()
        self.tabs.addTab(plot_tab, "Spectrum")
        
        # States table
        states_tab = self.create_states_table()
        self.tabs.addTab(states_tab, "Excited States")
        
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
    
    def create_plot_tab(self):
        """Create plot tab"""
        layout = QVBoxLayout()
        
        options_layout = QHBoxLayout()
        plot_label = QLabel("Display Mode:")
        self.plot_mode = QComboBox()
        self.plot_mode.addItems(["Simulated Spectrum", "Transitions (Stick)", "Molar Extinction"])
        self.plot_mode.currentIndexChanged.connect(self.update_plot)
        
        options_layout.addWidget(plot_label)
        options_layout.addWidget(self.plot_mode)
        options_layout.addStretch()
        
        layout.addLayout(options_layout)
        
        self.uvvis_canvas = UVVisPlottingWidget()
        layout.addWidget(self.uvvis_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_states_table(self):
        """Create excited states table"""
        layout = QVBoxLayout()
        
        self.states_table = QTableWidget()
        self.states_table.setColumnCount(4)
        self.states_table.setHorizontalHeaderLabels([
            "State", "Energy (eV)", "Wavelength (nm)", "Oscillator Strength"
        ])
        
        layout.addWidget(self.states_table)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_control_panel(self) -> QHBoxLayout:
        """Create control panel"""
        layout = QHBoxLayout()
        
        bandwidth_label = QLabel("Bandwidth (nm):")
        self.bandwidth_spinner = QDoubleSpinBox()
        self.bandwidth_spinner.setRange(5.0, 100.0)
        self.bandwidth_spinner.setValue(self.bandwidth)
        self.bandwidth_spinner.setSingleStep(5.0)
        self.bandwidth_spinner.valueChanged.connect(self.on_bandwidth_changed)
        
        layout.addWidget(bandwidth_label)
        layout.addWidget(self.bandwidth_spinner)
        layout.addStretch()
        
        return layout
    
    def load_orca_file(self):
        """Load ORCA output file"""
        filepath, _ = QFileDialog.getOpenFileName(self, "Select ORCA output", "",
                                                   "ORCA Files (*.out);;All Files (*)")
        if filepath:
            self.load_uvvis_data(Path(filepath))
    
    def load_uvvis_data(self, filepath: Path):
        """Load UV-Vis data from ORCA file"""
        self.states = TDDFTParser.parse_excited_states(filepath)
        
        if self.states:
            self.info_label.setText(f"Loaded: {len(self.states)} excited states from {filepath.name}")
        else:
            self.info_label.setText(f"No TD-DFT data found in {filepath.name}")
        
        self.update_table()
        self.update_plot()
    
    def on_bandwidth_changed(self):
        """Handle bandwidth change"""
        self.bandwidth = self.bandwidth_spinner.value()
        self.update_plot()
    
    def update_table(self):
        """Update states table"""
        self.states_table.setRowCount(len(self.states))
        
        for row, state in enumerate(self.states):
            self.states_table.setItem(row, 0, QTableWidgetItem(str(state.state_id)))
            self.states_table.setItem(row, 1, QTableWidgetItem(f"{state.energy_ev:.4f}"))
            self.states_table.setItem(row, 2, QTableWidgetItem(f"{state.wavelength_nm:.1f}"))
            self.states_table.setItem(row, 3, QTableWidgetItem(f"{state.oscillator_strength:.6f}"))
    
    def update_plot(self):
        """Update spectrum plot"""
        if not self.states:
            self.uvvis_canvas.ax.clear()
            self.uvvis_canvas.ax.text(0.5, 0.5, 'No data available',
                                     ha='center', va='center', transform=self.uvvis_canvas.ax.transAxes)
            self.uvvis_canvas.draw()
            return
        
        mode = self.plot_mode.currentIndex()
        
        if mode == 0:  # Simulated spectrum
            wavelengths, absorption = UVVisSpectrumSimulator.simulate_spectrum(
                self.states, bandwidth=self.bandwidth
            )
            self.uvvis_canvas.plot_uvvis_spectrum(wavelengths, absorption, self.bandwidth)
        elif mode == 1:  # Stick spectrum
            self.uvvis_canvas.plot_stick_spectrum(self.states)
        else:  # Molar extinction
            self.uvvis_canvas.plot_molar_extinction(self.states)
    
    def export_spectrum(self):
        """Export spectrum to image"""
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Spectrum", "",
                                                   "PNG Image (*.png);;PDF (*.pdf)")
        if filepath:
            self.uvvis_canvas.figure.savefig(filepath, dpi=300, bbox_inches='tight')
            QMessageBox.information(self, "Export", f"Spectrum saved to {filepath}")


def launch_uvvis_viewer(orca_filepath: Optional[Path] = None, parent=None) -> UVVisPopup:
    """Convenience function to launch UV-Vis viewer"""
    popup = UVVisPopup(orca_filepath, parent)
    popup.exec()
    return popup
