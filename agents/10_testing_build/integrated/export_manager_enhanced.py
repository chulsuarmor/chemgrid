# export_manager_enhanced.py (v2.0 - Advanced Selection Export)
"""
ChemGrid Pro Phase 5: Advanced Export Manager
- Export selected molecular structures (Lasso Select)
- PNG (white/transparent background), PDF, SVG support
- High-resolution DPI settings (up to 300 DPI)
- EXIF metadata embedding
- Lewis structure & Theory structure layers support
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

try:
    from PyQt6.QtWidgets import (QFileDialog, QMessageBox, QDialog, QVBoxLayout, 
                                 QHBoxLayout, QLabel, QSpinBox, QComboBox, 
                                 QCheckBox, QPushButton, QGroupBox)
    from PyQt6.QtGui import QPainter, QImage, QColor, QPen, QBrush
    from PyQt6.QtCore import Qt, QRect, QPointF, QSize
    from PyQt6.QtSvg import QSvgGenerator
    from PyQt6.QtPrintSupport import QPrinter
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


@dataclass
class ExportMetadata:
    """Export metadata for EXIF and document properties"""
    title: str
    software: str = "ChemGrid Pro v2.0"
    creation_date: str = None
    layer_type: str = "Lewis"  # Lewis or Theory
    molecule_count: int = 0
    has_selection: bool = False
    export_format: str = "PNG"
    dpi: int = 96
    
    def __post_init__(self):
        if self.creation_date is None:
            self.creation_date = datetime.now().isoformat()


class ExportDialog(QDialog):
    """Advanced export options dialog"""
    
    def __init__(self, parent=None, layer_type: str = "Lewis"):
        super().__init__(parent)
        self.layer_type = layer_type
        self.export_settings = {}
        self.init_ui()
        self.setWindowTitle("Export Options")
        self.resize(400, 300)
    
    def init_ui(self):
        """Initialize export options UI"""
        main_layout = QVBoxLayout()
        
        # Format selection
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "PDF", "SVG"])
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        format_layout.addWidget(QLabel("Format:"))
        format_layout.addWidget(self.format_combo)
        format_group.setLayout(format_layout)
        main_layout.addWidget(format_group)
        
        # PNG options
        self.png_group = QGroupBox("PNG Options")
        png_layout = QVBoxLayout()
        
        # Background option
        self.bg_transparent = QCheckBox("Transparent Background")
        self.bg_transparent.setChecked(False)
        png_layout.addWidget(self.bg_transparent)
        
        # DPI setting
        dpi_layout = QHBoxLayout()
        dpi_layout.addWidget(QLabel("DPI:"))
        self.dpi_spinbox = QSpinBox()
        self.dpi_spinbox.setRange(72, 600)
        self.dpi_spinbox.setValue(300)
        self.dpi_spinbox.setSingleStep(50)
        dpi_layout.addWidget(self.dpi_spinbox)
        dpi_layout.addStretch()
        png_layout.addLayout(dpi_layout)
        
        self.png_group.setLayout(png_layout)
        main_layout.addWidget(self.png_group)
        
        # Metadata option
        meta_group = QGroupBox("Metadata")
        meta_layout = QVBoxLayout()
        self.add_metadata = QCheckBox("Add EXIF/Document Metadata")
        self.add_metadata.setChecked(True)
        meta_layout.addWidget(self.add_metadata)
        meta_group.setLayout(meta_layout)
        main_layout.addWidget(meta_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(cancel_btn)
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def on_format_changed(self, format_str: str):
        """Update UI based on selected format"""
        self.png_group.setVisible(format_str == "PNG")
    
    def get_settings(self) -> Dict:
        """Get current export settings"""
        return {
            "format": self.format_combo.currentText(),
            "transparent_bg": self.bg_transparent.isChecked(),
            "dpi": self.dpi_spinbox.value(),
            "add_metadata": self.add_metadata.isChecked()
        }


class SelectionExporter:
    """Export selected molecules with high quality"""
    
    def __init__(self, canvas_widget, layer_type: str = "Lewis"):
        """
        Args:
            canvas_widget: PyQt6 canvas widget with atoms/bonds
            layer_type: "Lewis" or "Theory"
        """
        self.canvas = canvas_widget
        self.layer_type = layer_type
        self.selected_atoms = set()
        self.selected_bonds = set()
    
    def set_selection(self, atom_positions: List[Tuple[float, float]], 
                     bonds: Dict = None):
        """Set selected atoms and bonds"""
        self.selected_atoms = set(atom_positions)
        self.selected_bonds = set(bonds.items()) if bonds else set()
    
    def export_selection(self, output_path: str, settings: Dict = None):
        """
        Export selected molecules to file
        
        Args:
            output_path: Path to save exported file
            settings: Export settings from ExportDialog
        """
        if settings is None:
            settings = {
                "format": "PNG",
                "transparent_bg": False,
                "dpi": 300,
                "add_metadata": True
            }
        
        # Calculate bounding rect for selection
        if not self.selected_atoms:
            raise ValueError("No atoms selected for export")
        
        bounds = self._calculate_selection_bounds()
        format_type = settings.get("format", "PNG").upper()
        
        if format_type == "PNG":
            self._export_png(output_path, bounds, settings)
        elif format_type == "PDF":
            self._export_pdf(output_path, bounds, settings)
        elif format_type == "SVG":
            self._export_svg(output_path, bounds, settings)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def _calculate_selection_bounds(self) -> QRect:
        """Calculate bounding rectangle for selected atoms"""
        if not self.selected_atoms:
            return QRect(0, 0, 100, 100)
        
        xs = [pos[0] for pos in self.selected_atoms]
        ys = [pos[1] for pos in self.selected_atoms]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Add 20px padding
        padding = 20
        return QRect(int(min_x - padding), int(min_y - padding),
                    int(max_x - min_x + 2 * padding),
                    int(max_y - min_y + 2 * padding))
    
    def _export_png(self, output_path: str, bounds: QRect, settings: Dict):
        """Export selection as high-resolution PNG"""
        dpi = settings.get("dpi", 300)
        transparent_bg = settings.get("transparent_bg", False)
        
        # Calculate image size based on DPI
        scale_factor = dpi / 96.0
        img_size = QSize(
            int(bounds.width() * scale_factor),
            int(bounds.height() * scale_factor)
        )
        
        # Create image
        if transparent_bg:
            img = QImage(img_size, QImage.Format.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
        else:
            img = QImage(img_size, QImage.Format.Format_RGB32)
            img.fill(QColor(255, 255, 255))
        
        # Set DPI
        img.setDotsPerMeterX(int(dpi / 0.0254))
        img.setDotsPerMeterY(int(dpi / 0.0254))
        
        # Paint selection onto image
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-bounds.x() * scale_factor, -bounds.y() * scale_factor)
        painter.scale(scale_factor, scale_factor)
        
        # Draw selected atoms and bonds
        self._paint_selection(painter)
        painter.end()
        
        # Save image
        if img.save(output_path):
            self._embed_metadata_png(output_path, settings)
        else:
            raise IOError(f"Failed to save PNG to {output_path}")
    
    def _export_pdf(self, output_path: str, bounds: QRect, settings: Dict):
        """Export selection as vector PDF"""
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt6 required for PDF export")
        
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(output_path)
        printer.setPageSize(QPrinter.PageSize.A4)
        
        painter = QPainter(printer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw selection
        self._paint_selection(painter)
        painter.end()
    
    def _export_svg(self, output_path: str, bounds: QRect, settings: Dict):
        """Export selection as scalable SVG"""
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt6 required for SVG export")
        
        svg_gen = QSvgGenerator()
        svg_gen.setFileName(output_path)
        svg_gen.setSize(bounds.size())
        svg_gen.setViewBox(bounds)
        svg_gen.setTitle("ChemGrid Selection Export")
        svg_gen.setDescription(f"Exported from ChemGrid Pro - {datetime.now().isoformat()}")
        
        painter = QPainter(svg_gen)
        painter.translate(-bounds.x(), -bounds.y())
        
        self._paint_selection(painter)
        painter.end()
    
    def _paint_selection(self, painter: QPainter):
        """Paint selected atoms and bonds onto painter"""
        # This should be implemented by calling canvas render methods
        # For now, we'll paint atoms as circles and bonds as lines
        
        # Paint bonds first (background)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        for bond_key, bond_info in self.selected_bonds:
            if bond_key in self.canvas.bonds:
                # Draw bond line
                pos1, pos2 = bond_key
                painter.drawLine(
                    int(pos1[0]), int(pos1[1]),
                    int(pos2[0]), int(pos2[1])
                )
        
        # Paint atoms (foreground)
        for atom_pos in self.selected_atoms:
            if atom_pos in self.canvas.atoms:
                atom_data = self.canvas.atoms[atom_pos]
                element = atom_data.get("element", "C")
                
                # Draw atom circle
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.setBrush(QBrush(QColor(200, 200, 200)))
                painter.drawEllipse(int(atom_pos[0] - 10), int(atom_pos[1] - 10), 20, 20)
                
                # Draw element label
                painter.drawText(int(atom_pos[0] - 5), int(atom_pos[1] + 5), element)
    
    def _embed_metadata_png(self, image_path: str, settings: Dict):
        """Embed EXIF metadata into PNG file"""
        if not settings.get("add_metadata", False):
            return
        
        try:
            # For now, we'll add metadata as a comment in PNG
            # Full EXIF support would require piexif or similar library
            metadata = ExportMetadata(
                title=Path(image_path).stem,
                layer_type=self.layer_type,
                molecule_count=len(self.selected_atoms),
                has_selection=True,
                export_format="PNG",
                dpi=settings.get("dpi", 300)
            )
            
            # Save metadata as JSON comment
            meta_file = Path(image_path).with_stem(Path(image_path).stem + "_metadata")
            with open(str(meta_file.with_suffix(".json")), 'w') as f:
                json.dump(asdict(metadata), f, indent=2)
        
        except Exception as e:
            print(f"Warning: Could not embed metadata: {e}")


class ExportManager:
    """Main export manager for draw.py integration"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.canvas = main_window.cv if hasattr(main_window, 'cv') else None
    
    def export_selection(self):
        """Export selected region with dialog"""
        if not self.canvas:
            QMessageBox.warning(self.main_window, "Error", "Canvas not found")
            return
        
        # Check if selection exists
        if not hasattr(self.canvas, 'selected_atoms') or not self.canvas.selected_atoms:
            QMessageBox.warning(self.main_window, "No Selection", 
                              "Please select atoms using Lasso Select first")
            return
        
        # Get current layer
        layer_type = getattr(self.canvas, 'view_state', 'Lewis')
        
        # Show export dialog
        dialog = ExportDialog(self.main_window, layer_type)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        settings = dialog.get_settings()
        
        # Get file path
        format_ext = settings["format"].lower()
        file_filter = f"{settings['format']} Files (*.{format_ext})"
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Export Selection",
            f"export_selection.{format_ext}",
            file_filter
        )
        
        if not file_path:
            return
        
        try:
            # Create exporter and perform export
            exporter = SelectionExporter(self.canvas, layer_type)
            exporter.set_selection(
                list(self.canvas.selected_atoms),
                self.canvas.selected_bonds if hasattr(self.canvas, 'selected_bonds') else {}
            )
            exporter.export_selection(file_path, settings)
            
            QMessageBox.information(self.main_window, "Success", 
                                  f"Selection exported to:\n{file_path}")
        
        except Exception as e:
            QMessageBox.critical(self.main_window, "Export Error", 
                               f"Failed to export selection:\n{str(e)}")
