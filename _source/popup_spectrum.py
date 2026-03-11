# popup_spectrum.py (v1.0 - IR/Raman Spectrum Viewer Popup)
"""
ChemDraw Pro: Interactive Spectrum Viewer Popup
- Displays IR/Raman spectra in PyQt6 dialog
- Real-time linewidth and resolution adjustment
- Peak identification with frequency labels
- Export capabilities (PNG, CSV)
"""

from pathlib import Path
from typing import Optional

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QComboBox, QSpinBox, QDoubleSpinBox, 
                                 QMessageBox, QFileDialog, QTabWidget, QTableWidget,
                                 QTableWidgetItem, QTextEdit)
    from PyQt6.QtCore import Qt, QSize, pyqtSignal
    from PyQt6.QtGui import QIcon
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from spectrum_analyzer import (
    SpectrumData, SpectrumViewerWidget, 
    parse_orca_frequencies, plot_ir_spectrum, plot_raman_spectrum
)


class SpectrumPopup(QDialog):
    """
    Modal dialog for viewing IR/Raman spectra
    Triggered from theoretical structure layer with ORCA calculation results
    """
    
    spectrum_changed = pyqtSignal(str)  # Emits spectrum data description
    
    def __init__(self, spectrum_data: SpectrumData = None, parent=None):
        super().__init__(parent)
        self.spectrum_data = spectrum_data
        self.init_ui()
        self.setWindowTitle("IR/Raman Spectrum Analysis")
        self.resize(1000, 700)
    
    def init_ui(self):
        """Initialize UI components"""
        main_layout = QVBoxLayout()
        
        # ===== Title Section =====
        title_layout = QHBoxLayout()
        title_label = QLabel("Vibrational Spectrum Analysis")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        # Info label
        self.info_label = QLabel()
        self.update_info_label()
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        
        main_layout.addLayout(title_layout)
        
        # ===== Tab Widget =====
        self.tabs = QTabWidget()
        
        # Tab 1: Spectrum Viewer
        spectrum_tab = self.create_spectrum_tab()
        self.tabs.addTab(spectrum_tab, "Spectrum")
        
        # Tab 2: Peak Table
        peak_tab = self.create_peak_table_tab()
        self.tabs.addTab(peak_tab, "Peaks & Frequencies")
        
        # Tab 3: Analysis Info
        analysis_tab = self.create_analysis_tab()
        self.tabs.addTab(analysis_tab, "Analysis")
        
        main_layout.addWidget(self.tabs)
        
        # ===== Control Panel =====
        control_layout = self.create_control_panel()
        main_layout.addLayout(control_layout)
        
        # ===== Button Panel =====
        button_layout = QHBoxLayout()
        
        export_btn = QPushButton("Export Spectrum...")
        export_btn.clicked.connect(self.export_spectrum)
        button_layout.addWidget(export_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def create_spectrum_tab(self):
        """Create spectrum visualization tab"""
        layout = QVBoxLayout()
        
        self.spectrum_widget = SpectrumViewerWidget(self.spectrum_data)
        layout.addWidget(self.spectrum_widget)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_peak_table_tab(self):
        """Create peak frequency table"""
        layout = QVBoxLayout()
        
        # Create table
        self.peak_table = QTableWidget()
        self.peak_table.setColumnCount(5)
        self.peak_table.setHorizontalHeaderLabels([
            "Mode", "Frequency (cm⁻¹)", "IR Intensity (km/mol)", 
            "Raman Activity (A⁴/amu)", "Type"
        ])
        self.peak_table.setColumnWidth(0, 60)
        self.peak_table.setColumnWidth(1, 120)
        self.peak_table.setColumnWidth(2, 150)
        self.peak_table.setColumnWidth(3, 150)
        self.peak_table.setColumnWidth(4, 80)
        
        # Populate table
        if self.spectrum_data and self.spectrum_data.modes:
            self.peak_table.setRowCount(len(self.spectrum_data.modes))
            
            for row, mode in enumerate(self.spectrum_data.modes):
                # Mode index
                self.peak_table.setItem(row, 0, QTableWidgetItem(str(mode.mode_index + 1)))
                
                # Frequency
                self.peak_table.setItem(row, 1, QTableWidgetItem(f"{mode.frequency:.2f}"))
                
                # IR intensity
                self.peak_table.setItem(row, 2, QTableWidgetItem(f"{mode.intensity:.4f}"))
                
                # Raman activity
                self.peak_table.setItem(row, 3, QTableWidgetItem(f"{mode.raman_activity:.6f}"))
                
                # Type (IR-active or Raman-active)
                mode_type = []
                if mode.intensity > 0.01:
                    mode_type.append("IR")
                if mode.raman_activity > 0.001:
                    mode_type.append("Raman")
                
                mode_type_str = "/".join(mode_type) if mode_type else "-"
                self.peak_table.setItem(row, 4, QTableWidgetItem(mode_type_str))
        
        layout.addWidget(self.peak_table)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_analysis_tab(self):
        """Create analysis information tab"""
        layout = QVBoxLayout()
        
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.update_analysis_text()
        layout.addWidget(self.analysis_text)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_control_panel(self) -> QHBoxLayout:
        """Create control panel for spectrum adjustment"""
        layout = QHBoxLayout()
        
        # Spectrum type selector
        layout.addWidget(QLabel("View:"))
        spectrum_combo = QComboBox()
        spectrum_combo.addItems(["IR Spectrum", "Raman Spectrum", "Both (stacked)"])
        if hasattr(self.spectrum_widget, 'spectrum_combo'):
            spectrum_combo = self.spectrum_widget.spectrum_combo
        layout.addWidget(spectrum_combo)
        
        layout.addSpacing(20)
        
        # Linewidth control
        layout.addWidget(QLabel("Linewidth (cm⁻¹):"))
        linewidth_spin = QDoubleSpinBox()
        linewidth_spin.setMinimum(1.0)
        linewidth_spin.setMaximum(100.0)
        linewidth_spin.setValue(15.0)
        linewidth_spin.setSingleStep(1.0)
        if hasattr(self.spectrum_widget, 'linewidth_spin'):
            linewidth_spin = self.spectrum_widget.linewidth_spin
        layout.addWidget(linewidth_spin)
        
        layout.addSpacing(20)
        
        # Resolution control
        layout.addWidget(QLabel("Resolution:"))
        resolution_spin = QSpinBox()
        resolution_spin.setMinimum(1)
        resolution_spin.setMaximum(10)
        resolution_spin.setValue(1)
        if hasattr(self.spectrum_widget, 'resolution_spin'):
            resolution_spin = self.spectrum_widget.resolution_spin
        layout.addWidget(resolution_spin)
        
        layout.addStretch()
        
        return layout
    
    def update_info_label(self):
        """Update info label with spectrum summary"""
        if self.spectrum_data and len(self.spectrum_data.modes) > 0:
            num_modes = len(self.spectrum_data.modes)
            freq_range = self.spectrum_data.frequency_range
            max_ir = max(self.spectrum_data.ir_intensities) if self.spectrum_data.ir_intensities else 0
            
            info_text = (
                f"Modes: {num_modes} | "
                f"Freq Range: {freq_range[0]:.0f}-{freq_range[1]:.0f} cm⁻¹ | "
                f"Max IR: {max_ir:.2f} km/mol"
            )
            self.info_label.setText(info_text)
        else:
            self.info_label.setText("No spectrum data loaded")
    
    def update_analysis_text(self):
        """Update analysis information text"""
        if not self.spectrum_data:
            self.analysis_text.setText("No spectrum data available")
            return
        
        modes = self.spectrum_data.modes
        text = "=== VIBRATIONAL ANALYSIS ===\n\n"
        
        # Summary statistics
        text += "SUMMARY\n"
        text += "-" * 50 + "\n"
        text += f"Total Vibrational Modes: {len(modes)}\n"
        text += f"Frequency Range: {self.spectrum_data.frequency_range[0]:.1f} - "
        text += f"{self.spectrum_data.frequency_range[1]:.1f} cm⁻¹\n"
        text += f"Computation Time: {self.spectrum_data.computation_time:.2f} sec\n"
        text += f"Converged: {'Yes' if self.spectrum_data.converged else 'No'}\n\n"
        
        # IR-active modes
        ir_modes = [m for m in modes if m.intensity > 0.01]
        text += f"IR-ACTIVE MODES ({len(ir_modes)})\n"
        text += "-" * 50 + "\n"
        
        if ir_modes:
            for mode in sorted(ir_modes, key=lambda m: m.frequency)[:10]:  # Top 10
                text += f"  Mode {mode.mode_index+1}: {mode.frequency:.1f} cm⁻¹ "
                text += f"(I = {mode.intensity:.2f} km/mol)\n"
            
            if len(ir_modes) > 10:
                text += f"  ... and {len(ir_modes) - 10} more\n"
        
        text += "\n"
        
        # Raman-active modes
        raman_modes = [m for m in modes if m.raman_activity > 0.001]
        text += f"RAMAN-ACTIVE MODES ({len(raman_modes)})\n"
        text += "-" * 50 + "\n"
        
        if raman_modes:
            for mode in sorted(raman_modes, key=lambda m: m.frequency)[:10]:
                text += f"  Mode {mode.mode_index+1}: {mode.frequency:.1f} cm⁻¹ "
                text += f"(A = {mode.raman_activity:.4f})\n"
            
            if len(raman_modes) > 10:
                text += f"  ... and {len(raman_modes) - 10} more\n"
        
        self.analysis_text.setText(text)
    
    def set_spectrum_data(self, spectrum_data: SpectrumData):
        """Update displayed spectrum data"""
        self.spectrum_data = spectrum_data
        if self.spectrum_widget:
            self.spectrum_widget.set_spectrum_data(spectrum_data)
        self.update_info_label()
        self.update_analysis_text()
        
        # Refresh peak table
        if hasattr(self, 'peak_table'):
            self.peak_table.setRowCount(0)
            if spectrum_data and spectrum_data.modes:
                self.peak_table.setRowCount(len(spectrum_data.modes))
                
                for row, mode in enumerate(spectrum_data.modes):
                    self.peak_table.setItem(row, 0, QTableWidgetItem(str(mode.mode_index + 1)))
                    self.peak_table.setItem(row, 1, QTableWidgetItem(f"{mode.frequency:.2f}"))
                    self.peak_table.setItem(row, 2, QTableWidgetItem(f"{mode.intensity:.4f}"))
                    self.peak_table.setItem(row, 3, QTableWidgetItem(f"{mode.raman_activity:.6f}"))
                    
                    mode_type = []
                    if mode.intensity > 0.01:
                        mode_type.append("IR")
                    if mode.raman_activity > 0.001:
                        mode_type.append("Raman")
                    mode_type_str = "/".join(mode_type) if mode_type else "-"
                    self.peak_table.setItem(row, 4, QTableWidgetItem(mode_type_str))
    
    def export_spectrum(self):
        """Export spectrum data to file"""
        if not self.spectrum_data or len(self.spectrum_data.modes) == 0:
            QMessageBox.warning(self, "Export Error", "No spectrum data to export")
            return
        
        # File dialog
        file_path, file_filter = QFileDialog.getSaveFileName(
            self, 
            "Export Spectrum",
            "",
            "PNG Image (*.png);;CSV Data (*.csv);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            if file_path.endswith('.png'):
                # Export as PNG
                fig = plot_ir_spectrum(self.spectrum_data, title="IR Spectrum")
                if fig:
                    fig.savefig(file_path, dpi=150, bbox_inches='tight')
                    QMessageBox.information(self, "Export Success", f"Spectrum exported to\n{file_path}")
            
            elif file_path.endswith('.csv'):
                # Export as CSV
                import csv
                with open(file_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Mode', 'Frequency (cm-1)', 'IR Intensity (km/mol)', 
                                   'Raman Activity (A4/amu)'])
                    
                    for mode in self.spectrum_data.modes:
                        writer.writerow([
                            mode.mode_index + 1,
                            f"{mode.frequency:.2f}",
                            f"{mode.intensity:.4f}",
                            f"{mode.raman_activity:.6f}"
                        ])
                
                QMessageBox.information(self, "Export Success", f"Data exported to\n{file_path}")
        
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")


def launch_spectrum_viewer(orca_output_path: str, parent=None):
    """
    Convenience function to load ORCA output and show spectrum
    
    Usage in draw.py:
        from popup_spectrum import launch_spectrum_viewer
        launch_spectrum_viewer("path/to/orca_output.out")
    """
    try:
        spectrum_data = parse_orca_frequencies(Path(orca_output_path))
        
        if len(spectrum_data.modes) == 0:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(parent, "No Data", 
                              f"No vibrational data found in {orca_output_path}")
            return None
        
        popup = SpectrumPopup(spectrum_data, parent)
        popup.exec()
        return popup
    
    except Exception as e:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(parent, "Error", f"Failed to load spectrum:\n{str(e)}")
        return None


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Test with dummy data
    from spectrum_analyzer import VibrationalMode
    test_modes = [
        VibrationalMode(frequency=1000.0, intensity=10.5, raman_activity=0.05, mode_index=0),
        VibrationalMode(frequency=1500.0, intensity=50.2, raman_activity=0.15, mode_index=1),
        VibrationalMode(frequency=3000.0, intensity=80.1, raman_activity=0.25, mode_index=2),
    ]
    
    test_spectrum = SpectrumData(
        modes=test_modes,
        ir_frequencies=[1000.0, 1500.0, 3000.0],
        ir_intensities=[10.5, 50.2, 80.1],
        raman_frequencies=[1000.0, 1500.0, 3000.0],
        raman_activities=[0.05, 0.15, 0.25],
        frequency_range=(500.0, 3500.0),
        computation_time=120.0,
        converged=True
    )
    
    popup = SpectrumPopup(test_spectrum)
    popup.exec()
