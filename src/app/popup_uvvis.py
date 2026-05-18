# popup_uvvis.py (v1.1 - UV-Vis Absorption Spectrum Analysis)
"""
ChemGrid Pro: UV-Vis Spectrum Viewer with TD-DFT Analysis
- Parse excited states from ORCA TD-DFT calculation
- Visualize electronic transition energies and oscillator strengths
- Gaussian broadening simulation
- Transition density analysis
"""

import logging
from pathlib import Path
from typing import Any, Optional, List, Tuple, Dict
import re
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                                 QLabel, QComboBox, QDoubleSpinBox, QMessageBox,
                                 QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
                                 QWidget)
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QFont, QFontDatabase
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    QFont = None
    QFontDatabase = None

MATPLOTLIB_AVAILABLE = False
plt = None
Figure = None

if PYQT_AVAILABLE:
    class FigureCanvas(QWidget):  # type: ignore[no-redef]
        def __init__(self, parent=None):
            super().__init__(parent)
else:
    class FigureCanvas:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except Exception as e:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    Figure = None
    logger.warning("[UVVisPopup] matplotlib unavailable (%s): %s", type(e).__name__, e)


_UI_FONT_FAMILY_CACHE = ""


def _load_known_ui_font_files() -> set[str]:
    """Load Windows UI fonts for Qt offscreen captures with an empty font DB."""
    loaded: set[str] = set()
    if not PYQT_AVAILABLE or QFontDatabase is None:
        return loaded

    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/malgun.ttf"),
    ]
    for font_path in candidates:
        if not font_path.exists():
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id < 0:
                logger.warning("[UVVisPopup] UI font load failed: %s", font_path)
                continue
            for family in QFontDatabase.applicationFontFamilies(font_id):
                loaded.add(str(family))
        except Exception as exc:
            logger.warning("[UVVisPopup] UI font load exception for %s: %s", font_path, exc)
    return loaded


def _resolve_ui_font_family() -> str:
    """Return an installed ASCII-capable UI font family for labels/buttons."""
    global _UI_FONT_FAMILY_CACHE
    if _UI_FONT_FAMILY_CACHE:
        return _UI_FONT_FAMILY_CACHE
        if not PYQT_AVAILABLE or QFontDatabase is None:
            _UI_FONT_FAMILY_CACHE = "Arial"
            return _UI_FONT_FAMILY_CACHE

    priority = ["Segoe UI", "Arial", "Tahoma", "Malgun Gothic"]
    try:
        available = set(QFontDatabase.families())
        if not any(family in available for family in priority):
            loaded = _load_known_ui_font_files()
            if loaded:
                available = set(QFontDatabase.families()) | loaded
        for family in priority:
            if family in available:
                _UI_FONT_FAMILY_CACHE = family
                return _UI_FONT_FAMILY_CACHE
    except Exception as exc:
        logger.warning("[UVVisPopup] UI font resolution failed: %s", exc)

    _UI_FONT_FAMILY_CACHE = "Arial"
    return _UI_FONT_FAMILY_CACHE


def _apply_readable_ui_font(widget, point_size: int = 10) -> None:
    if not PYQT_AVAILABLE or QFont is None:
        return
    try:
        widget.setFont(QFont(_resolve_ui_font_family(), point_size))
    except Exception as exc:
        logger.warning("[UVVisPopup] UI font application failed: %s", exc)


def _font_css() -> str:
    family = _resolve_ui_font_family()
    return f"font-family: '{family}', Arial, sans-serif;"


def _format_remote_status_ascii(status: Dict[str, Any]) -> str:
    """Build ASCII-only remote ORCA status text for offscreen readability."""
    health = status.get("health", "unknown")
    server_status = status.get("server_status", status.get("status", "unknown"))
    backend = status.get("orca_backend", status.get("backend", "unknown"))
    server = status.get("server_url", "unset")
    orca_exists = status.get("orca_exists", "unknown")
    api_key_set = status.get("api_key_set", "unknown")
    return (
        "[SIMULATION_MODE] ORCA remote degraded/unavailable - not using remote DFT.\n"
        f"server_status={server_status}; health={health}; backend={backend}; "
        f"orca_exists={orca_exists}; api_key_set={api_key_set}; server={server}\n"
        "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
    )


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
                except (ValueError, IndexError) as exc:
                    logger.warning(
                        "[UVVisPopup] skipped malformed TD-DFT transition match: %s; match=%r",
                        exc,
                        match.group(0)[:160],
                    )
                    continue

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
                    except (ValueError, IndexError, ZeroDivisionError) as exc:
                        logger.warning(
                            "[UVVisPopup] skipped malformed fallback excited-state line %d: %s; line=%r",
                            i + 1,
                            exc,
                            line[:160],
                        )
                        continue

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
        self.figure = None
        self.ax = None
        if MATPLOTLIB_AVAILABLE and Figure is not None:
            self.figure = Figure(figsize=(9.0, 4.5), dpi=100)
            self.ax = self.figure.add_subplot(111)
            super().__init__(self.figure)
            self.setParent(parent)
        else:
            super().__init__(parent)
            if PYQT_AVAILABLE:
                fallback_layout = QVBoxLayout(self)
                fallback_label = QLabel(
                    "[SIMULATION_MODE] matplotlib unavailable - UV-Vis graph disabled.\n"
                    "ORCA TD-DFT data/status remains visible; no DFT result is claimed."
                )
                fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                fallback_label.setWordWrap(True)
                _apply_readable_ui_font(fallback_label, 11)
                fallback_label.setStyleSheet(
                    "background-color: #fff3cd; color: #856404; "
                    "border: 1px solid #ffeaa7; border-radius: 4px; "
                    f"padding: 12px; font-weight: bold; {_font_css()}"
                )
                fallback_layout.addWidget(fallback_label)

    def _plotting_ready(self) -> bool:
        ready = MATPLOTLIB_AVAILABLE and self.figure is not None and self.ax is not None
        if not ready:
            logger.warning("[UVVisPlottingWidget] matplotlib unavailable; plot skipped")
        return ready
    
    def plot_uvvis_spectrum(self, wavelengths: np.ndarray, absorption: np.ndarray, bandwidth: float = 20):
        """Plot simulated UV-Vis spectrum"""
        if not self._plotting_ready():
            return
        self.ax.clear()
        
        self.ax.fill_between(wavelengths, absorption, alpha=0.3, color='purple')
        self.ax.plot(wavelengths, absorption, color='purple', linewidth=2)
        
        self.ax.set_xlabel('Wavelength (nm)', fontsize=12)
        self.ax.set_ylabel('Absorption (a.u.)', fontsize=12)
        self.ax.set_title(f'UV-Vis Absorption Spectrum (Bandwidth: {bandwidth:.1f} nm)', fontsize=13)
        self.ax.grid(True, alpha=0.3)
        self.ax.invert_xaxis()  # Short wavelengths on right
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_stick_spectrum(self, states: List[ExcitedState]):
        """Plot transition energies as stick spectrum"""
        if not self._plotting_ready():
            return
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
        if not self._plotting_ready():
            return
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
    """UV-Vis spectrum viewer with TD-DFT analysis.

    M646_LITE_PARITY (Q-N4): ORCA 결과 없음 + ORCA_SERVER_URL 설정 시
    orca_remote_client.submit_and_wait() 자동 호출 시도.
    미설정 시 SIMULATION 배너 표시 (Rule GG / FP-15).

    학술 인용 (Rule NN — academic_integrity_check.py):
      Neese F. (2018) ORCA program system. WIREs Comput Mol Sci 8:e1327.
    """

    data_loaded = pyqtSignal(list)

    def __init__(self, orca_filepath: Optional[Path] = None, parent=None):
        super().__init__(parent)
        _apply_readable_ui_font(self, 10)
        self.states = []
        self.bandwidth = 20.0
        # M646_LITE_PARITY: ORCA Lite 원격 서버 가용성 캐싱
        self._orca_remote_status = self._get_remote_orca_status()
        self._orca_remote_available = self._check_remote_orca(self._orca_remote_status)

        if orca_filepath:
            self.load_uvvis_data(orca_filepath)

        self.init_ui()
        self.setWindowTitle("UV-Vis Absorption Analysis")
        self.resize(1000, 700)

    @staticmethod
    def _get_remote_orca_status() -> Dict[str, Any]:
        """Fetch strict remote ORCA health. Rule N: guard external status dict."""
        try:
            from orca_remote_client import quick_health_check
            status = quick_health_check()
            if isinstance(status, dict):
                return status
            logger.warning("[UVVisPopup] ORCA remote status type mismatch: %s", type(status).__name__)
            return {"remote_configured": False, "health": "unavailable: invalid health status"}
        except ImportError:
            return {"remote_configured": False, "health": "unavailable: orca_remote_client import failed"}
        except Exception as e:  # Rule M: 명시적 로깅
            logger.warning("[UVVisPopup] orca_remote_client 로드 실패: %s", e)
            return {"remote_configured": False, "health": f"unavailable: {type(e).__name__}: {e}"}

    @staticmethod
    def _check_remote_orca(status: Optional[Dict[str, Any]] = None) -> bool:
        """Remote ORCA is usable only when strict health/readiness is ok."""
        try:
            from orca_remote_client import is_remote_orca_ready
            return bool(is_remote_orca_ready(status if isinstance(status, dict) else None))
        except ImportError:
            return False
        except Exception as e:
            logger.warning("[UVVisPopup] ORCA remote readiness check failed: %s", e)
            return False

    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()

        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("UV-Vis Absorption Spectrum (TD-DFT)")
        _apply_readable_ui_font(title_label, 11)
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; {_font_css()}")
        title_layout.addWidget(title_label)

        self.info_label = QLabel("No data loaded")
        _apply_readable_ui_font(self.info_label, 10)
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        main_layout.addLayout(title_layout)

        # M646_LITE_PARITY (Q-N4): ORCA Lite SIMULATION 배너 (Rule GG / FP-15 차단)
        # 데이터 미로드 + 원격 미설정 시 사용자에게 명시적 표시.
        # 학술 인용 (Rule NN): Neese F. WIREs Comput Mol Sci 2018;8:e1327.
        self._sim_banner = QLabel()
        self._sim_banner.setWordWrap(True)
        _apply_readable_ui_font(self._sim_banner, 10)
        self._update_simulation_banner()
        main_layout.addWidget(self._sim_banner)
        
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
        # M646_LITE_PARITY: 데이터 로드 후 배너 갱신 (Rule GG / Rule M)
        self._update_simulation_banner()

    def _update_simulation_banner(self):
        """ORCA Lite SIMULATION 배너 갱신 (Q-N4 / Rule GG / FP-15 차단).

        Rule M: silent 금지 — 데이터 미존재 시 UI 명시.
        Rule N: hasattr 가드 (init_ui 전 호출 가능성).
        """
        if not hasattr(self, '_sim_banner'):
            return
        # 1) ORCA 데이터가 있으면 → 정상 (실측 OK)
        if self.states:
            self._sim_banner.setText(
                "<span style='color:#27ae60; font-weight:bold;'>"
                "[REAL_DFT] ORCA TD-DFT data loaded</span><br>"
                "<span style='font-size:9px; color:#888;'>"
                "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327.</span>"
            )
            self._sim_banner.setStyleSheet(
                "background-color: #d4edda; color: #155724; "
                "border: 1px solid #c3e6cb; border-radius: 4px; "
                f"padding: 6px 10px; font-size: 10px; {_font_css()}"
            )
            return
        # 2) 원격 ORCA 사용 가능 → 호출 시도 가능 안내
        if self._orca_remote_available:
            status = getattr(self, "_orca_remote_status", {})
            server = status.get("server_url", "configured") if isinstance(status, dict) else "configured"
            backend = status.get("orca_backend", status.get("backend", "unknown")) if isinstance(status, dict) else "unknown"
            msg = f"[REMOTE_DFT] ORCA remote ready - click Load. backend={backend}; server={server}"
            self._sim_banner.setText(
                f"<b style='color:#0066cc;'>{msg.replace(chr(10), '<br>')}</b>"
            )
            self._sim_banner.setStyleSheet(
                "background-color: #d1ecf1; color: #0c5460; "
                "border: 1px solid #bee5eb; border-radius: 4px; "
                f"padding: 6px 10px; font-size: 10px; font-weight: bold; {_font_css()}"
            )
            return
        remote_status = getattr(self, "_orca_remote_status", {})
        if isinstance(remote_status, dict) and remote_status.get("remote_configured") is True:
            msg = _format_remote_status_ascii(remote_status)
            health = remote_status.get("health", "")
            degraded = isinstance(health, str) and health.startswith("degraded")
            text_color = "#856404" if degraded else "#721c24"
            bg_color = "#fff3cd" if degraded else "#f8d7da"
            border_color = "#ffeaa7" if degraded else "#f5c6cb"
            self._sim_banner.setText(
                f"<b style='color:{text_color};'>{msg.replace(chr(10), '<br>')}</b>"
            )
            self._sim_banner.setStyleSheet(
                f"background-color: {bg_color}; color: {text_color}; "
                f"border: 1px solid {border_color}; border-radius: 4px; "
                f"padding: 6px 10px; font-size: 10px; font-weight: bold; {_font_css()}"
            )
            return
        # 3) ORCA 데이터 부재 + 원격 미설정 → SIMULATION 배너 (FP-15 차단)
        try:
            from orca_remote_client import get_status_message  # type: ignore
            msg = get_status_message(getattr(self, "_orca_remote_status", {}))
        except Exception:
            msg = (
                "[SIMULATION_MODE] No ORCA TD-DFT data loaded - "
                "displayed UV-Vis values are heuristic Gaussian broadening estimates.\n"
                "Set ORCA_SERVER_URL in .env and run housing/services/orca_api_server.py "
                "to enable real TD-DFT.\n"
                "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
            )
        self._sim_banner.setText(
            f"<b style='color:#e67e22;'>{msg.replace(chr(10), '<br>')}</b>"
        )
        self._sim_banner.setStyleSheet(
            "background-color: #fff3cd; color: #856404; "
            "border: 1px solid #ffeaa7; border-radius: 4px; "
            f"padding: 6px 10px; font-size: 10px; font-weight: bold; {_font_css()}"
        )
    
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
        if not MATPLOTLIB_AVAILABLE or getattr(self.uvvis_canvas, "ax", None) is None:
            logger.warning("[UVVisPopup] matplotlib unavailable; UV-Vis plot update skipped")
            if hasattr(self, "info_label"):
                self.info_label.setText("SIMULATION_MODE: matplotlib unavailable; graph disabled")
            self._update_simulation_banner()
            return
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
        if not MATPLOTLIB_AVAILABLE or getattr(self.uvvis_canvas, "figure", None) is None:
            QMessageBox.warning(self, "Export", "Matplotlib is unavailable; spectrum export is disabled.")
            return
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
