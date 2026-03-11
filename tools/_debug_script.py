
print("DEBUG: Script Loaded")
try:
    with open("_early_debug.txt", "w") as f:
        f.write("Script started\n")
except Exception as e:
    print(f"DEBUG: File write failed: {e}")
# spectrum_pdf_exporter.py (v1.2 - Enhanced Spectrum PDF Export)
"""
ChemDraw Pro: Spectrum PDF Exporter
- Generates high-quality PDF reports for spectral analysis
- Supports IR, Raman, UV-Vis, and NMR (1H, 13C) spectra
- Includes molecular structure visualization
- Uses ReportLab for PDF generation
- Uses Matplotlib for graph generation
"""

import os
import sys
import logging
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("spectrum_export_log.txt", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- Dependencies ---
try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak
    from reportlab.lib.units import inch, cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    logger.error("ReportLab not found. Install with: pip install reportlab")
    REPORTLAB_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg') # Force headless backend for server/CLI environments
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import matplotlib.colors as mcolors
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    import matplotlib.patches as patches
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError as e:
    logger.error(f"Matplotlib import error: {e}")
    MATPLOTLIB_AVAILABLE = False

# --- Local Modules (Simulated imports for standalone mode) ---
# In a real integration, these would import from agents.08_spectroscopy...
# For this script, we'll implement necessary helper functions directly or import if available

def get_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path: Path):
    if not path.exists():
        path.mkdir(parents=True)

# ============================================================================
# GRAPH GENERATION HELPERS
# ============================================================================

def generate_spectrum_graph(
    spectrum_type: str,
    data: Dict[str, Any],
    output_path: Path,
    molecule_name: str = "Molecule",
    figsize: Tuple[int, int] = (8, 5),
    structure_image_path: Optional[str] = None
) -> bool:
    """
    Generate a spectrum graph using Matplotlib and save as PNG.
    
    Args:
        spectrum_type: "IR", "Raman", "UV-Vis", "NMR_1H", "NMR_13C"
        data: Dictionary containing spectrum data points (x, y) or peaks
        output_path: Path to save the image
    """
    if not MATPLOTLIB_AVAILABLE:
        return False

    try:
        if spectrum_type == "UV-Vis":
            # [Dual-View Implementation for UV-Vis]
            # Left: Epsilon (Molar Absorptivity) vs Wavelength
            # Right: Log Epsilon vs Wavelength
            
            # Use wider figure for dual plots
            fig = Figure(figsize=(10, 5), dpi=300)
            canvas = FigureCanvasAgg(fig)
            ax1, ax2 = fig.subplots(1, 2)
            
            x = np.array(data.get('x', []))
            y_absorbance = np.array(data.get('y', [])) # Absorbance

            if x.size == 0 or y_absorbance.size == 0:
                logger.error(f"No data provided for {spectrum_type}")
                return False
                
            # Beer-Lambert Law: A = epsilon * c * l
            # Defaults: c=1e-4 M, l=1 cm (Standard path length)
            concentration = data.get('concentration', 1e-4)
            path_length = data.get('path_length', 1.0)
            
            # Calculate Epsilon & Log Epsilon
            epsilon = y_absorbance / (concentration * path_length)
            # Avoid log(0) or log(negative) issues
            log_epsilon = np.log10(np.maximum(epsilon, 1e-10))
            
            # --- Plot 1: Molar Absorptivity (Linear) ---
            ax1.plot(x, epsilon, color='darkblue', linewidth=1.5)
            ax1.set_xlabel("Wavelength (nm)")
            ax1.set_ylabel(r"$\epsilon$ ($M^{-1} cm^{-1}$)")
            ax1.set_title(r"Molar Absorptivity ($\epsilon$)")
            
            # Auto-zoom based on peak location (e.g., 200-350 nm)
            # Find where significant absorption occurs (e.g., > 5% of max)
            max_eps = np.max(epsilon)
            significant_indices = np.where(epsilon > max_eps * 0.05)[0]
            if len(significant_indices) > 0:
                min_idx, max_idx = significant_indices[0], significant_indices[-1]
                min_lambda, max_lambda = x[min_idx], x[max_idx]
                # Add padding
                zoom_min = max(200, min_lambda - 20)
                zoom_max = min(800, max_lambda + 50)
                # Ensure minimum window size
                if zoom_max - zoom_min < 100:
                    zoom_max = zoom_min + 100
                ax1.set_xlim(zoom_min, zoom_max)
            else:
                ax1.set_xlim(200, 800) # Fallback

            ax1.grid(True, linestyle='--', alpha=0.3)
            
            # Add visible spectrum background (Rainbow gradient) - ONLY if in range
            if ax1.get_xlim()[1] > 380:
                ax1.axvspan(380, 450, color='violet', alpha=0.1) # Violet
                ax1.axvspan(450, 495, color='blue', alpha=0.1)   # Blue
                ax1.axvspan(495, 570, color='green', alpha=0.1)  # Green
                ax1.axvspan(570, 590, color='yellow', alpha=0.1) # Yellow
                ax1.axvspan(590, 620, color='orange', alpha=0.1) # Orange
                ax1.axvspan(620, 750, color='red', alpha=0.1)    # Red

            # --- Plot 2: Log Molar Absorptivity (Log) ---
            ax2.plot(x, log_epsilon, color='darkviolet', linewidth=1.5)
            ax2.set_xlabel("Wavelength (nm)")
            ax2.set_ylabel(r"$\log \epsilon$")
            ax2.set_title(r"Log Absorptivity ($\log \epsilon$)")
            
            # Use same zoom for consistency
            ax2.set_xlim(ax1.get_xlim())
            ax2.grid(True, linestyle='--', alpha=0.3)

            # [Layout Optimization] Insert Molecular Structure or Diagram in empty space
            # If we zoomed in (e.g. 200-350), the right side of the plot is NOT empty.
            # But the user asked to use the "empty space after 400nm" to show structure.
            # If we zoomed in to 200-350, then 400nm is not visible.
            # We will add an inset axes or annotation to show the structure/diagram.
            
            # Add Electronic Transition Diagram (Schematic)
            # Create an inset axes for the diagram
            from mpl_toolkits.axes_grid1.inset_locator import inset_axes
            
            # Place it in the upper right of the second plot
            ax_ins = inset_axes(ax2, width="40%", height="40%", loc='upper right', borderpad=1)
            ax_ins.axis('off')
            
            # Draw simplified energy levels
            ax_ins.plot([0.2, 0.8], [0.2, 0.2], 'k-', lw=2) # HOMO / Pi
            ax_ins.text(0.9, 0.2, r'$\pi$', va='center')
            ax_ins.plot([0.2, 0.8], [0.8, 0.8], 'k-', lw=2) # LUMO / Pi*
            ax_ins.text(0.9, 0.8, r'$\pi^*$', va='center')
            
            # Arrow
            ax_ins.annotate('', xy=(0.5, 0.78), xytext=(0.5, 0.22),
                           arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
            ax_ins.text(0.55, 0.5, r'$h\nu$', color='red', fontsize=10)
            ax_ins.set_title("Electronic Transition", fontsize=8)
            
            # If structure image is provided, add it to the first plot
            if structure_image_path and os.path.exists(structure_image_path):
                try:
                    img = plt.imread(structure_image_path)
                    imagebox = OffsetImage(img, zoom=0.3, alpha=0.8) # Adjust zoom as needed
                    ab = AnnotationBbox(imagebox, (0.8, 0.6), xycoords='axes fraction', frameon=False)
                    ax1.add_artist(ab)
                except Exception as e:
                    pass
            
            fig.suptitle(f"{molecule_name} - UV-Vis Spectrum", fontsize=14, fontweight='bold')

        else:
            # [Single View for IR, Raman, NMR]
            fig = Figure(figsize=figsize, dpi=300)
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)

            # Common styling
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.set_title(f"{molecule_name} - {spectrum_type} Spectrum", fontsize=14, fontweight='bold')

            if spectrum_type == "IR":
                # IR: Wavenumber (cm-1) vs Transmittance/Absorbance
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))
                
                if x.size == 0 or y.size == 0:
                    logger.error(f"No data provided for {spectrum_type}")
                    return False

                ax.plot(x, y, color='blue', linewidth=1.5)
                ax.set_xlabel("Wavenumber (cm⁻¹)")
                ax.set_ylabel("Transmittance (%)")
                ax.invert_xaxis()
                ax.set_xlim(4000, 400)
                ax.set_ylim(0, 105)
                
                # Fingerprint region marker
                ax.axvline(x=1500, color='gray', linestyle=':', alpha=0.7)
                ax.text(1450, 5, "Fingerprint Region", ha='right', fontsize=9, color='gray', style='italic')

                # Highlight Peaks with Red Labels
                peaks = data.get('peaks', [])
                for px, py in peaks:
                    # Simple heuristic for labels based on position
                    label = ""
                    if 3200 <= px <= 3600: label = "O-H/N-H"
                    elif 2800 <= px <= 3100: label = "C-H"
                    elif 2100 <= px <= 2260: label = "C≡C/C≡N"
                    elif 1600 <= px <= 1800: label = "C=O"
                    elif 1450 <= px <= 1600: label = "C=C/Ar"
                    
                    if label:
                        ax.annotate(label, xy=(px, py), xytext=(px, py-10),
                                    arrowprops=dict(facecolor='red', arrowstyle='->', alpha=0.5),
                                    color='red', fontsize=8, ha='center')

            elif spectrum_type == "Raman":
                # Raman: Raman Shift (cm-1) vs Intensity
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))
                
                if x.size == 0 or y.size == 0:
                    logger.error(f"No data provided for {spectrum_type}")
                    return False
                
                # [Raman Improvement] Ghost Layer (IR Overlay)
                ir_overlay_data = data.get('ir_overlay')
                if ir_overlay_data:
                    ir_x = np.array(ir_overlay_data.get('x', []))
                    ir_y = np.array(ir_overlay_data.get('y', []))
                    if ir_x.size > 0 and ir_y.size > 0:
                        # Normalize IR to match Raman scale roughly for visual comparison
                        # IR is usually transmittance (100 -> 0), invert it to look like absorbance/intensity
                        ir_inv = 100 - ir_y
                        ir_norm = ir_inv * (np.max(y) / np.max(ir_inv)) if np.max(ir_inv) > 0 else ir_inv
                        ax.plot(ir_x, ir_norm, color='gray', alpha=0.2, linestyle='--', label='IR (Ghost)')
                        ax.legend(loc='upper right')

                ax.plot(x, y, color='green', linewidth=1.5)
                ax.set_xlabel("Raman Shift (cm⁻¹)")
                ax.set_ylabel("Intensity (a.u.)")
                ax.set_xlim(0, 3500)
                
                # Tooltips/Labels for major peaks
                peaks = data.get('peaks', [])
                for px, py in peaks:
                     ax.text(px, py, f"{px:.0f}", ha='center', va='bottom', fontsize=8, color='darkgreen')

            elif spectrum_type.startswith("NMR"):
                # NMR: Chemical Shift (ppm) vs Intensity
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))
                nucleus = "¹H" if "1H" in spectrum_type else "¹³C"
                
                if x.size == 0 or y.size == 0:
                    logger.error(f"No data provided for {spectrum_type}")
                    return False
                
                # [NMR Improvement] Zoning Labels (Background removed for clarity)
                if "13C" in spectrum_type:
                    # Carbon zones - Text Only, smaller font, lower alpha
                    ax.text(190, max(y)*0.95, "C=O", ha='center', fontsize=7, alpha=0.3)
                    ax.text(130, max(y)*0.95, "C=C / Ar", ha='center', fontsize=7, alpha=0.3)
                    ax.text(75, max(y)*0.95, "C-O / C-N", ha='center', fontsize=7, alpha=0.3)
                    ax.text(25, max(y)*0.95, "Aliphatic", ha='center', fontsize=7, alpha=0.3)
                    
                    # Highlight Sample Peak (if known, e.g., 128.5)
                    # For general purpose, we can iterate peaks and highlight major ones
                    peaks = data.get('peaks', [])
                    for px, py in peaks:
                        if py > max(y) * 0.5: # Major peak
                             ax.annotate(f"{px:.1f}", xy=(px, py), xytext=(px, py + max(y)*0.1),
                                        arrowprops=dict(facecolor='black', arrowstyle='->', alpha=0.5),
                                        fontsize=8, ha='center')

                else:
                    # Proton zones - Simplified
                    pass # Remove background zones as requested

                ax.plot(x, y, color='red', linewidth=1.5)
                
                # [NMR Improvement] Integral Curve
                if "1H" in spectrum_type:
                    # Calculate cumulative sum for integration
                    # Need to sort X first because NMR x axis is usually reversed
                    sort_idx = np.argsort(x)
                    x_sorted = x[sort_idx]
                    y_sorted = y[sort_idx]
                    integral = np.cumsum(y_sorted)
                    # Normalize integral to fit on plot
                    if np.max(integral) > 0:
                        integral = integral / np.max(integral) * np.max(y) * 0.8
                    
                    # Plot integral line using STEP function (Step-wise integral)
                    ax.step(x_sorted, integral, where='post', color='navy', linestyle='-', alpha=0.6, linewidth=1.2, label='Integral')

                ax.set_xlabel(f"{nucleus} Chemical Shift (ppm)")
                ax.set_ylabel("Intensity")
                ax.invert_xaxis()
                
                # Add peaks labels if provided
                peaks = data.get('peaks', [])
                if peaks:
                    for px, py in peaks:
                        ax.text(px, py + (max(y)*0.05), f"{px:.2f}", ha='center', fontsize=8, rotation=90)

        # Save plot
        fig.tight_layout()
        fig.savefig(str(output_path))
        logger.info(f"Generated graph: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error generating graph for {spectrum_type}: {e}")
        return False

# ============================================================================
# PDF EXPORTER CLASS
# ============================================================================

class SpectrumPDFExporter:
    """Handles PDF report generation for spectral data."""

    def __init__(self, output_dir: str = "docs/exports/spectra"):
        self.output_dir = Path(output_dir)
        ensure_dir(self.output_dir)
        
        # Determine font path - try to find a system font that supports unicode
        # Ideally, we would bundle a font, but for now we look for common ones
        self.font_name = "Helvetica" # Default fallback
        self.register_fonts()

    def register_fonts(self):
        """Register fonts that support special characters if available."""
        if not REPORTLAB_AVAILABLE:
            return
            
        # Try to find Arial or Malgun Gothic (for Windows Korean support)
        # This is a basic attempt; a robust solution would check OS
        font_paths = [
            # Windows
            "C:/Windows/Fonts/malgun.ttf", # Malgun Gothic
            "C:/Windows/Fonts/arial.ttf",
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        ]

        for path in font_paths:
            if os.path.exists(path):
                try:
                    font_name = "CustomFont"
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    self.font_name = font_name
                    logger.info(f"Registered custom font: {path}")
                    return
                except Exception as e:
                    logger.warning(f"Failed to register font {path}: {e}")
        
        logger.info("Using default Helvetica font (may not support all unicode chars).")


    def create_report(
        self,
        molecule_name: str,
        spectra_data: Dict[str, Any],
        structure_image_path: Optional[str] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Create a PDF report containing spectra and analysis.

        Args:
            molecule_name: Name of the molecule
            spectra_data: Dictionary of spectrum data (IR, Raman, NMR, etc.)
            structure_image_path: Path to the molecule structure image file
            filename: Output filename (optional)

        Returns:
            Path to the generated PDF file
        """
        if not REPORTLAB_AVAILABLE:
            logger.error("Cannot generate PDF: ReportLab is missing.")
            return None

        if filename is None:
            safe_name = "".join(c for c in molecule_name if c.isalnum() or c in (' ', '_', '-')).strip()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_Report_{timestamp}.pdf"

        output_path = self.output_dir / filename
        
        # Temp dir for generated graphs
        temp_dir = self.output_dir / "temp_assets"
        ensure_dir(temp_dir)

        # --- Document Setup ---
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=50, leftMargin=50,
            topMargin=50, bottomMargin=50
        )

        elements = []
        styles = getSampleStyleSheet()
        
        # Custom Styles
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontName=self.font_name,
            fontSize=24,
            alignment=1, # Center
            spaceAfter=20
        )
        
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontName=self.font_name,
            fontSize=16,
            textColor=colors.darkblue,
            spaceBefore=15,
            spaceAfter=10
        )
        
        text_style = ParagraphStyle(
            'BodyTextCustom',
            parent=styles['Normal'],
            fontName=self.font_name,
            fontSize=10,
            leading=14
        )

        # --- 1. Title Page ---
        elements.append(Paragraph(f"Spectral Analysis Report", title_style))
        elements.append(Paragraph(f"Molecule: {molecule_name}", styles['Heading2']))
        
        # [Report Improvement] Add IUPAC and Common Names if available
        if metadata:
            if 'iupac_name' in metadata:
                elements.append(Paragraph(f"<b>IUPAC Name:</b> {metadata['iupac_name']}", text_style))
            if 'common_name' in metadata:
                elements.append(Paragraph(f"<b>Common Name:</b> {metadata['common_name']}", text_style))
            if 'formula' in metadata:
                elements.append(Paragraph(f"<b>Molecular Formula:</b> {metadata['formula']}", text_style))
        
        elements.append(Paragraph(f"Date: {get_timestamp()}", text_style))
        elements.append(Spacer(1, 20))

        # --- 2. Molecular Structure ---
        if structure_image_path and os.path.exists(structure_image_path):
            try:
                img = RLImage(structure_image_path)
                
                # Resize if too big
                max_width = 400
                max_height = 300
                aspect = img.imageWidth / float(img.imageHeight)
                
                if img.imageWidth > max_width:
                    img.drawWidth = max_width
                    img.drawHeight = max_width / aspect
                elif img.imageHeight > max_height:
                    img.drawHeight = max_height
                    img.drawWidth = max_height * aspect
                
                elements.append(Paragraph("Molecular Structure", header_style))
                elements.append(img)
                elements.append(Spacer(1, 20))
            except Exception as e:
                logger.error(f"Failed to embed structure image: {e}")
                elements.append(Paragraph(f"[Structure Image Missing: {e}]", text_style))
        else:
            elements.append(Paragraph("Molecular Structure", header_style))
            elements.append(Paragraph("[No structure image provided]", text_style))
            elements.append(Spacer(1, 20))


        # --- 3. Spectra Sections ---
        spectra_types = [
            ("IR", "Infrared Spectrum (IR)"),
            ("Raman", "Raman Spectrum"),
            ("UV-Vis", "UV-Vis Spectrum"),
            ("NMR_1H", "¹H NMR Spectrum"),
            ("NMR_13C", "¹³C NMR Spectrum")
        ]

        for spec_key, spec_title in spectra_types:
            if spec_key in spectra_data:
                elements.append(PageBreak())
                elements.append(Paragraph(spec_title, header_style))
                
                spec_info = spectra_data[spec_key]
                
                # Generate Graph
                graph_filename = f"graph_{spec_key}_{datetime.datetime.now().strftime('%f')}.png"
                graph_path = temp_dir / graph_filename
                
                # Pass structure image path for UV-Vis diagram
                if generate_spectrum_graph(spec_key, spec_info, graph_path, molecule_name, structure_image_path=structure_image_path):
                    img = RLImage(str(graph_path), width=450, height=280)
                    elements.append(img)
                else:
                    elements.append(Paragraph("[Graph generation failed]", text_style))
                
                elements.append(Spacer(1, 10))
                
                # Peak Table (if peaks data exists)
                if 'peaks' in spec_info and spec_info['peaks']:
                    elements.append(Paragraph("Peak List:", styles['Heading3']))
                    
                    # Create table data
                    table_data = [['Frequency / Shift', 'Intensity']]
                    for p in spec_info['peaks']: # Expecting tuples (x, y)
                         table_data.append([f"{p[0]:.2f}", f"{p[1]:.2f}"])
                    
                    # Limit table size
                    if len(table_data) > 15:
                        table_data = table_data[:15]
                        table_data.append(["...", "..."])

                    t = Table(table_data, colWidths=[150, 150])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ]))
                    elements.append(t)
                
                elements.append(Spacer(1, 10))
                
                # Interpretation/Notes
                if 'notes' in spec_info:
                    elements.append(Paragraph(f"<b>Interpretation:</b> {spec_info['notes']}", text_style))


        # --- Build PDF ---
        try:
            doc.build(elements)
            logger.info(f"PDF Report generated successfully: {output_path}")
            
            # Clean up temp files (optional - keeping them for debugging might be good)
            # for p in temp_dir.glob("*.png"):
            #     p.unlink()
                
            return str(output_path)
        except Exception as e:
            logger.error(f"Failed to build PDF document: {e}")
            return None

# ============================================================================
# MAIN EXECUTION (CLI MODE)
# ============================================================================

if __name__ == "__main__":
    try:
        print("Running Spectrum PDF Exporter Test Mode...")
        
        # 1. Mock Data for Testing (Benzene Calibration)
        # Corrected based on experimental values for Benzene (C6H6)
        x_ir = np.linspace(4000, 400, 1000)
        y_ir = 100 * np.ones_like(x_ir)
        # IR Peaks: 3035 (C-H str), 1479 (C-C str), 1035 (C-H bend), 674 (C-H out-of-plane)
        for center, depth, width in [(3035, 40, 50), (1479, 60, 20), (1035, 30, 15), (674, 90, 15)]:
            y_ir -= depth * np.exp(-((x_ir - center)**2) / (2 * width**2))

        x_raman = np.linspace(0, 3500, 1000)
        y_raman = np.zeros_like(x_raman)
        # Raman Peaks: 3062 (C-H), 992 (Ring breathing, VS), 606
        for center, height, width in [(3062, 0.4, 20), (992, 1.0, 5), (606, 0.2, 10)]:
            y_raman += height * np.exp(-((x_raman - center)**2) / (2 * width**2))

        x_uv = np.linspace(200, 300, 500) # Zoomed in for UV
        y_uv = np.zeros_like(x_uv)
        # UV: 254nm (E2g -> B2u, forbidden/weak), 203nm (E2g -> E1u, strong - but outside typical view)
        # Benzene finger structure around 254nm
        # User requested scale 210-250. With c=1e-4, path=1, Epsilon = A / 1e-4 = A * 10000.
        # So A should be around 0.021 - 0.025.
        for center in [239, 243, 249, 254, 260]:
            y_uv += 0.025 * np.exp(-((x_uv - center)**2) / 5) # Fine structure

        x_h1 = np.linspace(10, 0, 1000)
        y_h1 = np.zeros_like(x_h1)
        # H1 NMR: Benzene singlet at 7.36 ppm
        y_h1 += 10.0 * np.exp(-((x_h1 - 7.36)**2) / 0.001) # Sharp singlet
        # Solvent CDCl3 at 7.26 (residual)
        y_h1 += 1.0 * np.exp(-((x_h1 - 7.26)**2) / 0.001)

        x_c13 = np.linspace(200, 0, 1000)
        y_c13 = np.zeros_like(x_c13)
        # C13 NMR: Benzene singlet at 128.5 ppm
        y_c13 += 10.0 * np.exp(-((x_c13 - 128.5)**2) / 0.05)
        # Solvent CDCl3 triplet around 77
        for shift in [76.5, 77.0, 77.5]:
            y_c13 += 0.5 * np.exp(-((x_c13 - shift)**2) / 0.05)

        mock_data = {
            "IR": {
                "x": x_ir,
                "y": y_ir,
                "peaks": [(3035.0, 60.0), (1479.0, 40.0), (674.0, 10.0)],
                "notes": "Corrected: No C=O peak. Major peaks at 3035 (C-H) and 674 (C-H out-of-plane)."
            },
            "Raman": {
                "x": x_raman,
                "y": y_raman,
                "peaks": [(3062.0, 0.4), (992.0, 1.0)],
                "ir_overlay": {"x": x_ir, "y": y_ir}, # Add IR overlay for comparison
                "notes": "Dominant ring breathing mode at 992 cm-1 (VS)."
            },
            "UV-Vis": {
                "x": x_uv,
                "y": y_uv,
                "peaks": [(254.0, 0.2)],
                "notes": "Characteristic fine structure (B-band) centered at 254 nm."
            },
            "NMR_1H": {
                "x": x_h1,
                "y": y_h1,
                "peaks": [(7.36, 10.0), (7.26, 1.0)],
                "notes": "Benzene singlet at 7.36 ppm. Residual CDCl3 at 7.26 ppm."
            },
            "NMR_13C": {
                "x": x_c13,
                "y": y_c13,
                "peaks": [(128.5, 10.0), (77.0, 0.5)],
                "notes": "Benzene carbon at 128.5 ppm. Solvent triplet at 77 ppm."
            }
        }

        exporter = SpectrumPDFExporter(output_dir="docs/exports/spectra_assets/auto_generated")
        
        # Try to find a dummy structure image or generate a placeholder
        test_image_path = "docs/exports/spectra_assets/structure_placeholder.png"
        # Create a dummy structure image if not exists, for testing visualization
        if not os.path.exists(test_image_path):
            try:
                ensure_dir(Path(test_image_path).parent)
                fig_struct = plt.figure(figsize=(2, 2))
                ax_struct = fig_struct.add_subplot(111)
                # Draw a simple hexagon for Benzene
                hexagon = patches.RegularPolygon((0.5, 0.5), numVertices=6, radius=0.4, 
                                                orientation=np.pi/6, edgecolor='black', facecolor='none', linewidth=2)
                ax_struct.add_patch(hexagon)
                # Circle inside
                circle = patches.Circle((0.5, 0.5), radius=0.25, edgecolor='black', facecolor='none', linewidth=1)
                ax_struct.add_patch(circle)
                ax_struct.axis('off')
                fig_struct.savefig(test_image_path, dpi=100, bbox_inches='tight')
                plt.close(fig_struct)
                print(f"Created placeholder structure image at {test_image_path}")
            except Exception as e:
                print(f"Failed to create placeholder structure: {e}")

        # Metadata for the report
        metadata = {
            "iupac_name": "Benzene",
            "common_name": "Benzene, Benzol, Phene",
            "formula": "C6H6"
        }
        
        pdf_path = exporter.create_report(
            molecule_name="Benzene (Test)",
            spectra_data=mock_data,
            structure_image_path=test_image_path,
            metadata=metadata
        )
        
        if pdf_path:
            print(f"\n[SUCCESS] PDF Report generated:\n -> {pdf_path}")
        else:
            print("\n[ERROR] Failed to generate PDF report.")

    except Exception as e:
        import traceback
        with open("_exporter_crash.log", "w") as f:
            f.write(traceback.format_exc())
        print(f"CRASH: {e}")

