# popup_spectrum.py (v1.2 - IR/Raman Spectrum Viewer Popup)
"""
ChemGrid Pro: Interactive Spectrum Viewer Popup
- Displays IR/Raman spectra in PyQt6 dialog
- Real-time linewidth and resolution adjustment
- Peak identification with frequency labels
- Export capabilities (PNG, CSV, PDF multi-page report)
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

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

try:
    from .spectrum_analyzer import (
        SpectrumData, SpectrumViewerWidget, 
        parse_orca_frequencies, plot_ir_spectrum, plot_raman_spectrum
    )
except ImportError:
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
        self.resize(1200, 800)
    
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

        # [M646_ENDPOINTS] Rule GG: 데이터 출처 배너 — ORCA 있음/없음에 따라 색 분기 (Rule NN)
        # ORCA(theory) 결과 있으면 파란 정보 배너, 없으면 노랑 SIMULATION 배너.
        # NIST WebBook은 라이브 (M646_ENDPOINTS 검증 — chemical/x-jcamp-dx HTTP 200).
        has_orca = bool(
            self.spectrum_data
            and getattr(self.spectrum_data, "modes", None)
            and len(self.spectrum_data.modes) > 0
        )
        if has_orca:
            source_banner = QLabel(
                "[이론적 스펙트럼 — ORCA 기반] DFT vibrational frequencies + IR/Raman 강도. "
                "외부 비교: NIST Chemistry WebBook (실측 데이터, "
                "Linstrom & Mallard SRD 69, public domain)."
            )
            # [MAGIC] _LIVE_BANNER_BG=#d1ecf1, _LIVE_BANNER_FG=#0c5460 — Bootstrap info 톤
            source_banner.setStyleSheet(
                "QLabel { background-color: #d1ecf1; color: #0c5460; "
                "border: 1px solid #bee5eb; border-radius: 4px; "
                "padding: 6px 10px; font-weight: bold; font-size: 11px; }"
            )
        else:
            source_banner = QLabel(
                "[SIMULATION_MODE] ORCA 결과 미로드 — 데이터 없음. "
                "NIST WebBook 실측 IR 스펙트럼 직접 조회 가능 (아래 'NIST WebBook' 버튼)."
            )
            # [MAGIC] _SIM_BANNER_BG=#fff3cd, _SIM_BANNER_FG=#856404 — Bootstrap warning 톤
            source_banner.setStyleSheet(
                "QLabel { background-color: #fff3cd; color: #856404; "
                "border: 1px solid #ffeeba; border-radius: 4px; "
                "padding: 6px 10px; font-weight: bold; font-size: 11px; }"
            )
        source_banner.setWordWrap(True)
        main_layout.addWidget(source_banner)

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

        pdf_btn = QPushButton("PDF 저장")
        pdf_btn.clicked.connect(self.export_pdf_report)
        button_layout.addWidget(pdf_btn)

        # [M646_ENDPOINTS] NIST WebBook 외부 링크 버튼 — Rule GG/NN
        # 라이브 검증 완료: chemical/x-jcamp-dx, /cgi/cbook.cgi?JCAMP=...&Type=IR HTTP 200
        nist_btn = QPushButton("NIST WebBook 검색")
        nist_btn.setToolTip(
            "NIST Chemistry WebBook에서 실측 IR/MS 스펙트럼 검색.\n"
            "Linstrom & Mallard, NIST Standard Reference Database 69 (public domain)."
        )
        nist_btn.clicked.connect(self._open_nist_webbook)
        button_layout.addWidget(nist_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def create_spectrum_tab(self):
        """Create spectrum visualization tab"""
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)

        self.spectrum_widget = SpectrumViewerWidget(self.spectrum_data)
        self.spectrum_widget.setMinimumSize(QSize(1100, 600))
        layout.addWidget(self.spectrum_widget, stretch=1)

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
    
    def _open_nist_webbook(self):
        """[M646_ENDPOINTS] NIST WebBook 외부 검색 — Rule GG/NN.

        라이브 endpoint: https://webbook.nist.gov/cgi/cbook.cgi?Name=...&Units=SI
        검증: M646_ENDPOINTS HTTP probes 2026-04-28 — HTTP 200, JCAMP-DX 사용 가능.
        Rule M: webbrowser.open() 실패 시 logger.warning + 사용자 메시지.
        Rule N: mol_name 타입 가드 (str 보장).
        """
        import webbrowser
        # [MAGIC] _NIST_BASE: NIST Chemistry WebBook 공식 검색 페이지
        nist_base = "https://webbook.nist.gov/cgi/cbook.cgi"
        mol_name = ""
        if self.spectrum_data and hasattr(self.spectrum_data, "mol_name"):
            raw_name = self.spectrum_data.mol_name
            if isinstance(raw_name, str):  # Rule N
                mol_name = raw_name.strip()
        if mol_name:
            from urllib.parse import quote
            url = f"{nist_base}?Name={quote(mol_name, safe='')}&Units=SI"
        else:
            url = f"{nist_base}?Units=SI"  # 검색 홈으로 이동
        try:
            opened = webbrowser.open(url, new=2)
            if not opened:
                logger.warning("[NIST] webbrowser.open() returned False: %s", url)
                QMessageBox.information(
                    self, "NIST WebBook",
                    f"브라우저 열기 실패. 직접 방문: {url}\n\n"
                    "Linstrom & Mallard, NIST Chemistry WebBook, "
                    "NIST Standard Reference Database 69 (public domain)."
                )
        except Exception as e:
            logger.warning("[NIST] webbrowser.open() failed (%s): %s", type(e).__name__, e)
            QMessageBox.information(
                self, "NIST WebBook",
                f"브라우저 열기 실패: {e}\n직접 방문: {url}"
            )

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

    def export_pdf_report(self):
        """Export multi-page PDF report with all available spectra"""
        if not self.spectrum_data or len(self.spectrum_data.modes) == 0:
            QMessageBox.warning(self, "Export Error", "No spectrum data to export")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF 저장",
            "",
            "PDF Document (*.pdf);;All Files (*.*)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith('.pdf'):
            file_path += '.pdf'

        try:
            import os
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages
            import numpy as np
            # ── Korean font for matplotlib ──
            import matplotlib.font_manager as fm
            for _fp in [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/NanumGothic.ttf",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            ]:
                if os.path.exists(_fp):
                    _kr = fm.FontProperties(fname=_fp)
                    matplotlib.rcParams["font.family"] = _kr.get_name()
                    fm.fontManager.addfont(_fp)
                    break

            modes = self.spectrum_data.modes
            ir_modes = [m for m in modes if m.intensity > 0.01]
            raman_modes = [m for m in modes if m.raman_activity > 0.001]

            with PdfPages(file_path) as pdf:
                # --- Page 1: IR Spectrum ---
                if ir_modes:
                    fig, ax = plt.subplots(figsize=(11, 7))
                    fig_ir = plot_ir_spectrum(
                        self.spectrum_data,
                        figure_size=(11, 7),
                        show_peaks=True,
                        title="IR Spectrum"
                    )
                    if fig_ir is not None:
                        pdf.savefig(fig_ir, bbox_inches='tight')
                        plt.close(fig_ir)
                    plt.close(fig)

                # --- Page 2: Raman Spectrum ---
                if raman_modes:
                    fig, ax = plt.subplots(figsize=(11, 7))
                    fig_raman = plot_raman_spectrum(
                        self.spectrum_data,
                        figure_size=(11, 7),
                        show_peaks=True,
                        title="Raman Spectrum"
                    )
                    if fig_raman is not None:
                        pdf.savefig(fig_raman, bbox_inches='tight')
                        plt.close(fig_raman)
                    plt.close(fig)

                # --- Page 3: Combined IR + Raman overlay ---
                if ir_modes and raman_modes:
                    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9))
                    fig.suptitle("Combined Vibrational Spectra", fontsize=14, fontweight='bold')

                    # IR subplot
                    freqs_ir = [m.frequency for m in ir_modes]
                    ints_ir = [m.intensity for m in ir_modes]
                    ax1.stem(freqs_ir, ints_ir, linefmt='b-', markerfmt='bx', basefmt='k-')
                    ax1.set_xlabel("Wavenumber (cm$^{-1}$)")
                    ax1.set_ylabel("IR Intensity (km/mol)")
                    ax1.set_title("IR Spectrum")
                    ax1.invert_xaxis()
                    # Annotate top 5 peaks
                    for m in sorted(ir_modes, key=lambda x: x.intensity, reverse=True)[:5]:
                        ax1.annotate(f"{m.frequency:.0f}", xy=(m.frequency, m.intensity),
                                     fontsize=7, ha='center', va='bottom')

                    # Raman subplot
                    freqs_r = [m.frequency for m in raman_modes]
                    acts_r = [m.raman_activity for m in raman_modes]
                    ax2.stem(freqs_r, acts_r, linefmt='g-', markerfmt='gx', basefmt='k-')
                    ax2.set_xlabel("Wavenumber (cm$^{-1}$)")
                    ax2.set_ylabel("Raman Activity (A$^4$/amu)")
                    ax2.set_title("Raman Spectrum")
                    for m in sorted(raman_modes, key=lambda x: x.raman_activity, reverse=True)[:5]:
                        ax2.annotate(f"{m.frequency:.0f}", xy=(m.frequency, m.raman_activity),
                                     fontsize=7, ha='center', va='bottom')

                    fig.tight_layout(rect=[0, 0, 1, 0.95])
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close(fig)

                # --- Page 4: Peak Summary Table ---
                fig, ax = plt.subplots(figsize=(11, 7))
                ax.axis('off')
                ax.set_title("Peak Summary Table", fontsize=14, fontweight='bold', pad=20)

                table_data = []
                for m in sorted(modes, key=lambda x: x.frequency):
                    mtype = []
                    if m.intensity > 0.01:
                        mtype.append("IR")
                    if m.raman_activity > 0.001:
                        mtype.append("Raman")
                    table_data.append([
                        str(m.mode_index + 1),
                        f"{m.frequency:.1f}",
                        f"{m.intensity:.2f}",
                        f"{m.raman_activity:.4f}",
                        "/".join(mtype) if mtype else "-"
                    ])

                # Limit rows per page to keep readable
                max_rows = 35
                for chunk_start in range(0, len(table_data), max_rows):
                    if chunk_start > 0:
                        fig, ax = plt.subplots(figsize=(11, 7))
                        ax.axis('off')
                        ax.set_title("Peak Summary Table (continued)", fontsize=14,
                                     fontweight='bold', pad=20)

                    chunk = table_data[chunk_start:chunk_start + max_rows]
                    col_labels = ["Mode", "Freq (cm\u207b\u00b9)", "IR Int (km/mol)",
                                  "Raman Act (A\u2074/amu)", "Type"]
                    tbl = ax.table(cellText=chunk, colLabels=col_labels,
                                   loc='center', cellLoc='center')
                    tbl.auto_set_font_size(False)
                    tbl.set_fontsize(8)
                    tbl.scale(1.0, 1.2)
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close(fig)

                # --- Page 5: Analysis Summary ---
                fig, ax = plt.subplots(figsize=(11, 7))
                ax.axis('off')
                summary = (
                    f"Vibrational Analysis Summary\n"
                    f"{'=' * 50}\n"
                    f"Total Modes: {len(modes)}\n"
                    f"IR-Active Modes: {len(ir_modes)}\n"
                    f"Raman-Active Modes: {len(raman_modes)}\n"
                    f"Frequency Range: {self.spectrum_data.frequency_range[0]:.1f} - "
                    f"{self.spectrum_data.frequency_range[1]:.1f} cm\u207b\u00b9\n"
                    f"Computation Time: {self.spectrum_data.computation_time:.2f} sec\n"
                    f"Converged: {'Yes' if self.spectrum_data.converged else 'No'}\n"
                )
                ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                        fontsize=12, verticalalignment='top', fontfamily='monospace')
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            QMessageBox.information(self, "PDF Export",
                                   f"PDF report saved to\n{file_path}")

        except Exception as e:
            logger.error(f"PDF export failed: {e}", exc_info=True)
            QMessageBox.critical(self, "PDF Export Error",
                                 f"Failed to create PDF:\n{str(e)}")


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
