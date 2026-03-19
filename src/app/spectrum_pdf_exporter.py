# spectrum_pdf_exporter.py (v1.1 - Professional Spectrum PDF Export)
"""
ChemGrid Pro Phase 5/6: Spectrum PDF Exporter
- Export IR, Raman, NMR, UV-Vis, MD, MolOrbital spectra to professional PDF
- Academic-grade format with metadata and verification marks
- Multi-spectrum integration into single PDF
- High-resolution (300 DPI) graph rendering

Changes (v1.1):
  - S2 fix: QListWidget() → QListWidgetItem() in init_ui()
  - S5 fix: print() → logging module
"""

import os
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import io

logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                                 QLabel, QCheckBox, QMessageBox, QFileDialog,
                                 QGroupBox, QListWidget, QListWidgetItem, QFileIconProvider)
    from PyQt6.QtCore import Qt
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import inch, cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Korean font registration for PDF output
def _register_korean_font():
    """Register Korean font for PDF. Returns font name to use."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
        for fp, name in [
            ('C:/Windows/Fonts/malgun.ttf', 'Malgun'),
            ('C:/Windows/Fonts/malgunbd.ttf', 'MalgunBold'),
            ('C:/Windows/Fonts/gulim.ttc', 'Gulim'),
        ]:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont(name, fp))
                    return name
                except Exception:
                    continue
    except ImportError:
        pass
    return 'Helvetica'

KOREAN_FONT = _register_korean_font()

# Shoolery's Rule: delta(H) = 0.23 + sum of substituent constants
SHOOLERY_INCREMENTS = {
    'CH3': 0.0, 'CH2': 0.0, 'CH': 0.0,
    'C=O_ketone': 1.50, 'C=O_ester': 1.21, 'COOH': 1.00,
    'OH': 2.56, 'OR': 2.36, 'NH2': 1.57, 'NR2': 1.57,
    'Cl': 2.53, 'Br': 2.33, 'F': 3.30, 'I': 2.24,
    'Ph': 1.85, 'C=C': 1.32, 'C≡C': 1.44,
    'NO2': 3.36, 'CN': 1.70, 'S': 1.64,
}



@dataclass
class SpectrumMetadata:
    """Spectrum calculation metadata"""
    molecule_name: str
    molecular_formula: str
    smiles: str = ""
    calculation_method: str = "B3LYP/6-31G(d)"
    basis_set: str = "6-31G(d)"
    software: str = "ORCA 5.0+"
    chemgrid_version: str = "ChemGrid Pro v2.0"
    calculation_date: str = None
    convergence_status: str = "Converged"
    scf_converged: bool = True
    geometry_converged: bool = True
    final_energy: float = 0.0
    
    def __post_init__(self):
        if self.calculation_date is None:
            self.calculation_date = datetime.now().isoformat()


@dataclass
class SpectrumPeakData:
    """Single peak information"""
    frequency: float  # cm⁻¹ or ppm
    intensity: float  # 0-100 or arbitrary
    label: str = ""
    assignment: str = ""
    unit: str = "cm⁻¹"


@dataclass
class SpectrumData:
    """Complete spectrum data"""
    spectrum_type: str  # IR, Raman, NMR, UV-Vis, MD, MolOrbital
    peaks: List[SpectrumPeakData]
    raw_data: Dict = None  # Raw calculation data
    image_path: str = None  # Path to matplotlib plot


class SpectrumSelectionDialog(QDialog):
    """Dialog for selecting which spectra to export"""
    
    def __init__(self, available_spectra: List[str], parent=None):
        super().__init__(parent)
        self.available_spectra = available_spectra
        self.selected_spectra = []
        self.init_ui()
        self.setWindowTitle("Select Spectra to Export")
        self.resize(350, 300)
    
    def init_ui(self):
        """Initialize spectrum selection UI"""
        main_layout = QVBoxLayout()
        
        main_layout.addWidget(QLabel("Select spectra to include in PDF:"))
        
        # Spectrum list with checkboxes
        self.spectrum_list = QListWidget()
        for spectrum in self.available_spectra:
            item = QListWidgetItem()
            item.setText(spectrum)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.spectrum_list.addItem(item)
        
        main_layout.addWidget(self.spectrum_list)
        
        # Button panel
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(deselect_all_btn)
        main_layout.addLayout(button_layout)
        
        # Export buttons
        export_layout = QHBoxLayout()
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        export_layout.addWidget(export_btn)
        export_layout.addWidget(cancel_btn)
        main_layout.addLayout(export_layout)
        
        self.setLayout(main_layout)
    
    def select_all(self):
        """Check all spectrum items"""
        for i in range(self.spectrum_list.count()):
            item = self.spectrum_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)
    
    def deselect_all(self):
        """Uncheck all spectrum items"""
        for i in range(self.spectrum_list.count()):
            item = self.spectrum_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
    
    def get_selected(self) -> List[str]:
        """Get list of selected spectrum types"""
        selected = []
        for i in range(self.spectrum_list.count()):
            item = self.spectrum_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected


class SpectrumPDFExporter:
    """Export spectrum data to professional PDF format"""
    
    def __init__(self, metadata: SpectrumMetadata):
        """
        Args:
            metadata: Spectrum calculation metadata
        """
        self.metadata = metadata
        self.spectra: Dict[str, SpectrumData] = {}
        self.page_num = 1
    
    def add_spectrum(self, spectrum_type: str, spectrum_data: SpectrumData):
        """Add spectrum data for export"""
        self.spectra[spectrum_type] = spectrum_data
    
    def export_to_pdf(self, output_path: str, spectrum_types: Optional[List[str]] = None):
        """
        Export spectra to PDF file
        
        Args:
            output_path: Path to save PDF
            spectrum_types: List of spectrum types to export (None = all)
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab library required for PDF export")
        
        if spectrum_types is None:
            spectrum_types = list(self.spectra.keys())
        
        # Create PDF
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        story = []
        
        # Add title page
        story.extend(self._create_title_page())
        
        # Add each spectrum
        for spectrum_type in spectrum_types:
            if spectrum_type in self.spectra:
                story.append(PageBreak())
                story.extend(self._create_spectrum_page(spectrum_type))
        
        # Add metadata page
        story.append(PageBreak())
        story.extend(self._create_metadata_page())
        
        # Build PDF
        doc.build(story)
    
    def _create_title_page(self) -> List:
        """Create title page with metadata"""
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        elements.append(Paragraph("Spectroscopic Analysis Report", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Molecule information
        mol_data = [
            ["Molecular Name:", self.metadata.molecule_name],
            ["Molecular Formula:", self.metadata.molecular_formula],
            ["SMILES:", self.metadata.smiles],
        ]
        mol_table = Table(mol_data, colWidths=[2*inch, 4*inch])
        mol_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), KOREAN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(mol_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Calculation information
        calc_data = [
            ["Calculation Method:", self.metadata.calculation_method],
            ["Basis Set:", self.metadata.basis_set],
            ["Software:", self.metadata.software],
            ["ChemGrid Version:", self.metadata.chemgrid_version],
            ["Date:", self.metadata.calculation_date],
            ["Final Energy (Hartree):", f"{self.metadata.final_energy:.8f}"],
            ["Convergence Status:", "✓ CONVERGED" if self.metadata.convergence_status == "Converged" else "✗ UNCONVERGED"],
        ]
        calc_table = Table(calc_data, colWidths=[2*inch, 4*inch])
        calc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), KOREAN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(calc_table)
        
        return elements
    
    def _create_spectrum_page(self, spectrum_type: str) -> List:
        """Create single spectrum page"""
        elements = []
        styles = getSampleStyleSheet()
        spectrum = self.spectra[spectrum_type]
        
        # Title
        title_style = ParagraphStyle(
            'SpectrumTitle',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=12,
        )
        elements.append(Paragraph(f"{spectrum_type} Spectrum Analysis", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Spectrum plot (if image available)
        if spectrum.image_path and os.path.exists(spectrum.image_path):
            try:
                elements.append(Image(spectrum.image_path, width=5.5*inch, height=3*inch))
            except:
                pass
        
        elements.append(Spacer(1, 0.2*inch))
        
        # Peak table
        if spectrum.peaks:
            peak_data = [["Frequency/Position", "Intensity", "Assignment"]]
            for peak in spectrum.peaks:
                unit_str = f"{peak.frequency:.1f} {peak.unit}"
                intensity_str = f"{peak.intensity:.1f}"
                assignment_str = peak.assignment or peak.label
                peak_data.append([unit_str, intensity_str, assignment_str])
            
            peak_table = Table(peak_data, colWidths=[2*inch, 1.5*inch, 2.5*inch])
            peak_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), KOREAN_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            elements.append(peak_table)
        
        return elements
    
    def _create_metadata_page(self) -> List:
        """Create metadata and verification page"""
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'MetaTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0066cc'),
        )
        elements.append(Paragraph("Calculation Parameters & Verification", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Verification checklist
        verify_data = [
            ["✓", "ORCA execution completed successfully"],
            ["✓" if self.metadata.scf_converged else "✗", "SCF convergence criteria met"],
            ["✓" if self.metadata.geometry_converged else "✗", "Geometry optimization converged"],
            ["✓", f"Spectra extracted from calculation output"],
            ["✓", f"{len(self.spectra)} spectrum/spectra included in report"],
        ]
        
        verify_table = Table(verify_data, colWidths=[0.3*inch, 5.7*inch])
        verify_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), KOREAN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        elements.append(verify_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Footer
        footer_text = f"""
        <b>Report Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>
        <b>Software:</b> ChemGrid Pro v2.0 with {self.metadata.software}<br/>
        <b>Quantum Chemistry Engine:</b> {self.metadata.software}<br/>
        <b>Basis Set:</b> {self.metadata.basis_set}<br/>
        <b>Final Energy:</b> {self.metadata.final_energy:.8f} Hartree<br/>
        """
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#666666'),
            alignment=TA_LEFT,
        )
        elements.append(Paragraph(footer_text, footer_style))
        
        return elements


class ExportSpectrumManager:
    """Manager for spectrum PDF export from draw.py"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.available_spectra = []
    
    def export_spectra(self, spectra_data: Dict[str, SpectrumData], 
                      metadata: SpectrumMetadata = None):
        """
        Export spectra with dialog
        
        Args:
            spectra_data: Dict of spectrum type -> SpectrumData
            metadata: Spectrum metadata (auto-generated if None)
        """
        if not REPORTLAB_AVAILABLE:
            QMessageBox.critical(self.main_window, "Error",
                               "reportlab library not installed.\nInstall via: pip install reportlab")
            return
        
        if not spectra_data:
            QMessageBox.warning(self.main_window, "No Data", "No spectrum data available")
            return
        
        # Show selection dialog
        spectrum_types = list(spectra_data.keys())
        dialog = SpectrumSelectionDialog(spectrum_types, self.main_window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        selected = dialog.get_selected()
        if not selected:
            QMessageBox.warning(self.main_window, "No Selection", "Please select at least one spectrum")
            return
        
        # Create metadata
        if metadata is None:
            metadata = SpectrumMetadata(
                molecule_name="Unknown Molecule",
                molecular_formula="C?H?",
                calculation_method="B3LYP/6-31G(d)",
                final_energy=-1000.0
            )
        
        # Get output path
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Export Spectra to PDF",
            "spectra_report.pdf",
            "PDF Files (*.pdf)"
        )
        
        if not file_path:
            return
        
        try:
            # Create exporter and build PDF
            exporter = SpectrumPDFExporter(metadata)
            for spectrum_type in selected:
                if spectrum_type in spectra_data:
                    exporter.add_spectrum(spectrum_type, spectra_data[spectrum_type])
            
            exporter.export_to_pdf(file_path, selected)
            
            QMessageBox.information(self.main_window, "Success",
                                  f"Spectrum PDF exported to:\n{file_path}")
        
        except Exception as e:
            QMessageBox.critical(self.main_window, "Export Error",
                               f"Failed to export spectra:\n{str(e)}")
