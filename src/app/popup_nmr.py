# popup_nmr.py (v1.1 - NMR Spectrum Analysis Popup)
"""
ChemGrid Pro: NMR Spectrum Viewer with Lorentzian Simulation
- ¹H, ¹³C, ¹⁹F NMR spectrum parsing from ORCA
- Lorentzian peak simulation
- Interactive linewidth and frequency adjustment
- Chemical shift and coupling constant analysis
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import re
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

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

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# --- Korean font support for matplotlib ---
_MPL_KR_FONT = None
_KR_FONT_PATHS = [
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
for _fp in _KR_FONT_PATHS:
    if os.path.exists(_fp):
        _MPL_KR_FONT = fm.FontProperties(fname=_fp)
        matplotlib.rcParams["font.family"] = _MPL_KR_FONT.get_name()
        fm.fontManager.addfont(_fp)
        break
_fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}


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

        if not isinstance(filepath, (str, Path)):
            logger.warning("parse_nmr_from_orca: invalid filepath type: %s", type(filepath).__name__)
            return nmr_data

        filepath = Path(filepath)
        if not filepath.exists():
            logger.warning("parse_nmr_from_orca: file does not exist: %s", filepath)
            return nmr_data

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if not isinstance(content, str) or not content.strip():
                logger.warning("parse_nmr_from_orca: empty or invalid file content: %s", filepath)
                return nmr_data

            # Parse ¹H NMR
            nmr_data["1H"] = NMRParser._extract_h_nmr(content)

            # Parse ¹³C NMR
            nmr_data["13C"] = NMRParser._extract_c_nmr(content)

            # Parse ¹⁹F NMR
            nmr_data["19F"] = NMRParser._extract_f_nmr(content)

            total = sum(len(v) for v in nmr_data.values())
            if total == 0:
                logger.warning("parse_nmr_from_orca: no NMR signals found in %s", filepath.name)

        except Exception as e:
            logger.warning("parse_nmr_from_orca: NMR parsing failed for %s: %s", filepath, e)

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
        if not isinstance(signals, list):
            logger.warning("simulate_spectrum: signals is not a list: %s", type(signals).__name__)
            signals = []
        if not isinstance(nucleus, str):
            logger.warning("simulate_spectrum: nucleus is not str: %s", type(nucleus).__name__)
            nucleus = "1H"

        freq = np.linspace(freq_min, freq_max, points)
        intensity = np.zeros_like(freq, dtype=float)

        # Add contribution from each signal
        for signal in signals:
            if not isinstance(signal, NMRSignal):
                logger.warning("simulate_spectrum: skipping non-NMRSignal item: %s",
                               type(signal).__name__)
                continue
            if signal.nucleus == nucleus:
                intensity += NMRSpectrumSimulator.lorentzian(
                    freq, signal.chemical_shift, linewidth, signal.intensity
                )
        
        # Reverse x-axis for NMR convention (high field on left)
        return freq[::-1], intensity[::-1]


class NMRPlottingWidget(FigureCanvas):
    """Matplotlib widget for NMR spectrum display"""
    
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(9.0, 4.5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
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

        if not isinstance(signals, list):
            logger.warning("plot_stick_spectrum: signals is not list: %s", type(signals).__name__)
            signals = []

        filtered_signals = [s for s in signals if isinstance(s, NMRSignal) and s.nucleus == nucleus]
        
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
    """NMR spectrum viewer with Lorentzian simulation.

    Supports two data sources:
      1. ORCA output file (filepath-based loading)
      2. Predicted spectra from ChemGrid engine (NMRPeak/C13Peak lists)
    """

    nmr_data_loaded = pyqtSignal(dict)

    def __init__(self, orca_filepath: Optional[Path] = None,
                 predicted_h1: Optional[List] = None,
                 predicted_c13: Optional[List] = None,
                 mol_name: str = "",
                 parent=None):
        super().__init__(parent)
        self.nmr_signals: Dict[str, List[NMRSignal]] = {}
        self.current_nucleus = "1H"
        self.linewidth = 1.0
        self.mol_name = mol_name

        if orca_filepath:
            self.load_nmr_data(orca_filepath)
        elif predicted_h1 or predicted_c13:
            self._load_predicted_spectra(predicted_h1, predicted_c13)

        self.init_ui()
        title = "NMR Spectrum Analysis"
        if mol_name:
            title += f" - {mol_name}"
        self.setWindowTitle(title)
        self.resize(1000, 700)

    def _load_predicted_spectra(self, h1_peaks: Optional[List] = None,
                                c13_peaks: Optional[List] = None):
        """Load NMR signals from ChemGrid predicted spectra (predict_spectra.py).

        Accepts NMRPeak objects (shift, integration, multiplicity, assignment)
        and C13Peak objects (shift, assignment, dept_type) from predict_spectra module.
        """
        self.nmr_signals = {"1H": [], "13C": [], "19F": []}

        # Convert predicted 1H NMR peaks
        if h1_peaks and isinstance(h1_peaks, list):
            for peak in h1_peaks:
                if not hasattr(peak, 'shift'):
                    logger.warning("_load_predicted_spectra: invalid h1 peak (no shift attr): %r", peak)
                    continue
                try:
                    signal = NMRSignal(
                        nucleus="1H",
                        chemical_shift=float(peak.shift),
                        intensity=float(getattr(peak, 'integration', 1.0)),
                        multiplicity=getattr(peak, 'multiplicity', 's'),
                    )
                    self.nmr_signals["1H"].append(signal)
                except (ValueError, TypeError) as e:
                    logger.warning("_load_predicted_spectra: failed to convert h1 peak: %s", e)

        # Convert predicted 13C peaks
        if c13_peaks and isinstance(c13_peaks, list):
            for peak in c13_peaks:
                if not hasattr(peak, 'shift'):
                    logger.warning("_load_predicted_spectra: invalid c13 peak (no shift attr): %r", peak)
                    continue
                try:
                    signal = NMRSignal(
                        nucleus="13C",
                        chemical_shift=float(peak.shift),
                        intensity=1.0,
                        multiplicity="s",
                    )
                    self.nmr_signals["13C"].append(signal)
                except (ValueError, TypeError) as e:
                    logger.warning("_load_predicted_spectra: failed to convert c13 peak: %s", e)

        total = sum(len(v) for v in self.nmr_signals.values())
        logger.info("Loaded %d predicted NMR signals (1H=%d, 13C=%d)",
                    total, len(self.nmr_signals["1H"]), len(self.nmr_signals["13C"]))
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()

        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("NMR Spectrum Simulation")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)

        # Show data source info
        total_signals = sum(len(v) for v in self.nmr_signals.values()) if self.nmr_signals else 0
        if total_signals > 0 and self.mol_name:
            info_text = f"Predicted: {total_signals} signals ({self.mol_name})"
        elif total_signals > 0:
            info_text = f"Loaded: {total_signals} signals"
        else:
            info_text = "No data loaded"
        self.info_label = QLabel(info_text)
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        main_layout.addLayout(title_layout)

        # [M646_ENDPOINTS] Rule GG: SIMULATION_MODE 노랑 배너 + 학술 인용 (Rule NN)
        # NMRDB 라이브 endpoint 미제공 (검증: M646_ENDPOINTS HTTP probes 2026-04-28)
        # — /api/predict 404 / /new_predictor HTML JS visualizer / /service/predictor POST 폼
        # 따라서 본 팝업은 ORCA 결과 또는 내장 시뮬레이션만 표시.
        sim_banner = QLabel(
            "[SIMULATION_MODE] 이론적 NMR 스펙트럼 (ORCA/내장 시뮬레이션) — "
            "NMRDB 라이브 예측 미연동. "
            "출처: NMRDB Banfi & Patiny (2008) Chimia 62:280 / "
            "참고 UI: https://www.nmrdb.org/new_predictor/ (학생 직접 입력)"
        )
        # [MAGIC] _SIM_BANNER_BG=#fff3cd, _SIM_BANNER_FG=#856404 — Bootstrap warning 톤
        sim_banner.setStyleSheet(
            "QLabel { background-color: #fff3cd; color: #856404; "
            "border: 1px solid #ffeeba; border-radius: 4px; "
            "padding: 6px 10px; font-weight: bold; font-size: 11px; }"
        )
        sim_banner.setWordWrap(True)
        main_layout.addWidget(sim_banner)

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
        result = NMRParser.parse_nmr_from_orca(filepath)
        if not isinstance(result, dict):
            logger.warning("load_nmr_data: parser returned non-dict: %s", type(result).__name__)
            result = {"1H": [], "13C": [], "19F": []}
        self.nmr_signals = result

        # Update info
        total_signals = sum(len(v) for v in self.nmr_signals.values())
        if total_signals == 0:
            logger.warning("load_nmr_data: no signals loaded from %s", filepath)
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
        if not isinstance(self.nmr_signals, dict):
            logger.warning("update_table: nmr_signals is not dict: %s", type(self.nmr_signals).__name__)
            self.nmr_signals = {}
        signals = self.nmr_signals.get(self.current_nucleus, [])
        if not isinstance(signals, list):
            logger.warning("update_table: signals for %s is not list: %s",
                           self.current_nucleus, type(signals).__name__)
            signals = []
        self.signals_table.setRowCount(len(signals))
        
        for row, signal in enumerate(signals):
            self.signals_table.setItem(row, 0, QTableWidgetItem(signal.nucleus))
            self.signals_table.setItem(row, 1, QTableWidgetItem(f"{signal.chemical_shift:.2f}"))
            self.signals_table.setItem(row, 2, QTableWidgetItem(f"{signal.intensity:.3f}"))
            self.signals_table.setItem(row, 3, QTableWidgetItem(signal.multiplicity))
    
    def update_plot(self):
        """Update spectrum plot"""
        if not isinstance(self.nmr_signals, dict):
            logger.warning("update_plot: nmr_signals is not dict: %s", type(self.nmr_signals).__name__)
            self.nmr_signals = {}
        signals = self.nmr_signals.get(self.current_nucleus, [])

        if not signals:
            logger.warning("update_plot: no signals for nucleus %s", self.current_nucleus)
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


def launch_nmr_viewer(orca_filepath: Optional[Path] = None,
                      predicted_h1: Optional[List] = None,
                      predicted_c13: Optional[List] = None,
                      mol_name: str = "",
                      parent=None) -> NMRPopup:
    """Convenience function to launch NMR viewer.

    Args:
        orca_filepath: Path to ORCA output file (optional)
        predicted_h1: List of NMRPeak objects from predict_spectra (optional)
        predicted_c13: List of C13Peak objects from predict_spectra (optional)
        mol_name: Display name for the molecule (optional)
        parent: Parent widget (optional)

    Returns:
        NMRPopup instance
    """
    popup = NMRPopup(orca_filepath=orca_filepath,
                     predicted_h1=predicted_h1,
                     predicted_c13=predicted_c13,
                     mol_name=mol_name,
                     parent=parent)
    popup.exec()
    return popup
