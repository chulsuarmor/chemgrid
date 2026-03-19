# spectrum_pdf_exporter.py (v1.3 - Fixed Spectrum Visualization)
"""
ChemDraw Pro: Spectrum PDF Exporter
- Generates high-quality PDF reports for spectral analysis
- Supports IR, Raman, UV-Vis, and NMR (1H, 13C) spectra
- Includes molecular structure visualization (RDKit)
- Uses ReportLab for PDF generation
- Uses Matplotlib for graph generation
"""

print("SCRIPT START: Loading modules...")
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
    matplotlib.use('Agg') # Force headless backend
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import matplotlib.colors as mcolors
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    import matplotlib.patches as patches
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError as e:
    logger.error(f"Matplotlib import error: {e}")
    MATPLOTLIB_AVAILABLE = False

# --- RDKit Integration ---
try:
    from rdkit import Chem
    from rdkit.Chem import Draw
    from rdkit.Chem import AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    logger.warning("RDKit not found. Structure generation will be limited.")


def get_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path: Path):
    if not path.exists():
        path.mkdir(parents=True)

# ============================================================================
# GRAPH GENERATION HELPERS
# ============================================================================

def generate_structure_image_with_labels(smiles: str, labels: Dict[int, str], output_path: Path) -> bool:
    """
    Generate a structure image with atom labels using RDKit.
    Strictly requires RDKit and valid SMILES.
    """
    if not RDKIT_AVAILABLE:
        logger.error("RDKit unavailable - cannot generate structure.")
        return False
    
    if not smiles:
        logger.error("No SMILES string provided for structure generation.")
        return False

    try:
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            logger.error(f"Invalid SMILES string: {smiles}")
            return False
        
        # Kekulize for standard representation (Double bonds shown explicitly)
        try:
            Chem.Kekulize(mol)
        except Exception as e:
            logger.warning(f"Kekulize failed (aromatic view used): {e}")
        
        # Set atom labels based on mapping
        for atom in mol.GetAtoms():
            idx = atom.GetIdx()
            if idx in labels:
                # Use atom property to display label (e.g., 'a', 'b')
                atom.SetProp('atomNote', labels[idx])
        
        # Draw options
        options = Draw.MolDrawOptions()
        options.bondLineWidth = 2.5
        options.padding = 0.05
        try:
            options.atomLabelFontSize = 14
        except AttributeError:
            pass
        options.annotationFontScale = 0.8
        
        # Generate image
        img = Draw.MolToImage(mol, size=(400, 400), options=options, kekulize=True)
        img.save(str(output_path))
        return True
    except Exception as e:
        logger.error(f"Failed to generate labeled structure: {e}")
        return False

def generate_spectrum_graph(
    spectrum_type: str,
    data: Dict[str, Any],
    output_path: Path,
    molecule_name: str = "Molecule",
    figsize: Tuple[int, int] = (10, 6),
    structure_image_path: Optional[str] = None,
    smiles: Optional[str] = None
) -> bool:
    """
    Generate a spectrum graph using Matplotlib and save as PNG.
    """
    if not MATPLOTLIB_AVAILABLE:
        return False

    try:
        if spectrum_type == "UV-Vis":
            # [Instruction 2: UV-Vis Dual-View Reversion]
            # Two independent subplots: Linear Epsilon (Left), Log Epsilon (Right)
            
            fig = Figure(figsize=(12, 5), dpi=300)
            canvas = FigureCanvasAgg(fig)
            
            # Create 1x2 subplots
            ax1 = fig.add_subplot(1, 2, 1) # Linear
            ax2 = fig.add_subplot(1, 2, 2) # Log
            
            x = np.array(data.get('x', []))
            y_absorbance = np.array(data.get('y', []))

            if x.size == 0 or y_absorbance.size == 0:
                logger.error(f"No data provided for {spectrum_type}")
                return False
                
            concentration = data.get('concentration', 1e-4)
            path_length = data.get('path_length', 1.0)
            epsilon = y_absorbance / (concentration * path_length)
            
            # --- Left Plot: Linear Epsilon ---
            ax1.plot(x, epsilon, color='darkblue', linewidth=1.5, label='Epsilon')
            ax1.set_xlabel("Wavelength (nm)")
            ax1.set_ylabel(r"$\epsilon$ ($M^{-1} cm^{-1}$)")
            ax1.set_title("Linear Scale", fontsize=12)
            ax1.grid(True, linestyle='--', alpha=0.3)
            ax1.set_xlim(200, 800)
            ax1.set_ylim(0, 10000) # [Fix] Y-axis optimization
            
            # Visible Spectrum Background on Left Plot
            ax1.axvspan(380, 450, color='violet', alpha=0.1)
            ax1.axvspan(450, 495, color='blue', alpha=0.1)
            ax1.axvspan(495, 570, color='green', alpha=0.1)
            ax1.axvspan(570, 590, color='yellow', alpha=0.1)
            ax1.axvspan(590, 620, color='orange', alpha=0.1)
            ax1.axvspan(620, 750, color='red', alpha=0.1)

            # --- Right Plot: Log Epsilon ---
            # Avoid log(0)
            epsilon_log = np.log10(np.maximum(epsilon, 1e-5))
            ax2.plot(x, epsilon_log, color='darkred', linewidth=1.5, label='Log Epsilon')
            ax2.set_xlabel("Wavelength (nm)")
            ax2.set_ylabel(r"$\log(\epsilon)$")
            ax2.set_title("Log Scale", fontsize=12)
            ax2.grid(True, linestyle='--', alpha=0.3)
            ax2.set_xlim(200, 800)
            
            # --- Energy Diagram (Relocated to Right Plot Inset) ---
            # Place in upper right of right plot (Inset)
            # [x, y, width, height]
            # [Instruction: Energy Diagram Separation] Moved further right/up to avoid B-band overlap
            ax_diagram = ax2.inset_axes([0.70, 0.60, 0.28, 0.28]) 
            ax_diagram.set_xticks([])
            ax_diagram.set_yticks([])
            for spine in ax_diagram.spines.values():
                spine.set_edgecolor('gray')
                spine.set_linewidth(0.5)
            
            ax_diagram.set_xlim(0, 1)
            ax_diagram.set_ylim(0, 1)
            
            # Draw levels
            ax_diagram.plot([0.2, 0.8], [0.25, 0.25], 'k-', lw=2) # HOMO
            ax_diagram.text(0.1, 0.25, r'HOMO', va='center', ha='right', fontsize=7)
            ax_diagram.plot([0.2, 0.8], [0.75, 0.75], 'k-', lw=2) # LUMO
            ax_diagram.text(0.1, 0.75, r'LUMO', va='center', ha='right', fontsize=7)
            
            # Transition arrow
            ax_diagram.annotate('', xy=(0.5, 0.73), xytext=(0.5, 0.27),
                           arrowprops=dict(arrowstyle='->', color='purple', lw=1.5))
            ax_diagram.text(0.55, 0.5, r'$h\nu$', color='purple', fontsize=9, ha='left', va='center')
            ax_diagram.text(0.5, 0.9, r"Energy Diagram", ha='center', va='top', fontsize=7, fontweight='bold')
            
            # Overall Title
            fig.suptitle(f"{molecule_name} - UV-Vis Spectrum", fontsize=16, fontweight='bold')

        else:
            # Single View for IR, Raman, NMR
            fig = Figure(figsize=figsize, dpi=300)
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)
            
            # Use tight_layout or constrained_layout [Instruction 1: Frame Safety]
            # We will apply it at the end, but setup grid now
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.set_title(f"{molecule_name} - {spectrum_type} Spectrum", fontsize=14, fontweight='bold')

            if spectrum_type == "IR":
                # [Instruction: Page 1-3 IR Improvements]
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))
                
                ax.plot(x, y, color='blue', linewidth=1.0)
                ax.set_xlabel("Wavenumber (cm⁻¹)")
                ax.set_ylabel("Transmittance (%)")
                ax.invert_xaxis()
                ax.set_xlim(4000, 400)
                ax.set_ylim(0, 105)
                
                # Top Axis: Wavelength in microns
                def wavenumber2micron(w):
                    return 10000.0 / np.maximum(w, 1e-10)
                def micron2wavenumber(m):
                    return 10000.0 / np.maximum(m, 1e-10)

                secax = ax.secondary_xaxis('top', functions=(wavenumber2micron, micron2wavenumber))
                secax.set_xlabel(r"Wavelength ($\mu m$)")
                # Fix label overlap using MaxNLocator with fewer bins
                secax.xaxis.set_major_locator(MaxNLocator(nbins=6, prune='both'))
                
                # Fingerprint region
                ax.axvline(x=1500, color='gray', linestyle=':', alpha=0.7)
                ax.text(1450, 5, "Fingerprint Region", ha='right', fontsize=9, color='gray', style='italic')

                # Peak Labels
                peaks = data.get('peaks', [])
                for p in peaks:
                    px, py = p[0], p[1]
                    label = p[2] if len(p) > 2 else ""
                    if not label:
                        if 3000 <= px <= 3100: label = r"$sp^2$ C-H"
                        elif 2800 <= px < 3000: label = r"$sp^3$ C-H"
                        elif 1680 <= px <= 1750: label = "C=O"
                        elif 1450 <= px <= 1600: label = "Aromatic C=C"
                    
                    if label:
                         ax.annotate(label, xy=(px, py), xytext=(px, py-15),
                                    arrowprops=dict(facecolor='red', arrowstyle='->', alpha=0.5),
                                    color='darkred', fontsize=8, ha='center',
                                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7))

            elif spectrum_type == "Raman":
                # [Instruction: Page 1-3 Raman Improvements]
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))
                
                # Stick Bars (Simulated) - High Visibility (zorder=2)
                calculated_peaks = data.get('calculated_peaks', data.get('peaks', []))
                if calculated_peaks:
                    calc_x = [p[0] for p in calculated_peaks]
                    calc_y = [p[1] for p in calculated_peaks]
                    max_y = np.max(y) if len(y) > 0 else 1.0
                    max_calc = np.max(calc_y) if len(calc_y) > 0 else 1.0
                    calc_y_norm = [val * (max_y / max_calc) * 0.8 for val in calc_y]
                    
                    # Ensure stick bars are visible over grid
                    ax.vlines(calc_x, 0, calc_y_norm, colors='black', alpha=0.6, linewidth=2.5, label='Simulated', zorder=3)
                
                ax.plot(x, y, color='green', linewidth=1.5, label='Experimental', zorder=2)
                ax.set_xlabel("Raman Shift (cm⁻¹)")
                ax.set_ylabel("Intensity (a.u.)")
                ax.set_xlim(0, 3500)
                ax.legend(loc='upper right', fontsize=8)

            elif spectrum_type.startswith("NMR"):
                # [Instruction 1: NMR Layout & Integration]
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))
                nucleus = "¹H" if "1H" in spectrum_type else "¹³C"
                
                ax.plot(x, y, color='red', linewidth=1.2, label='Spectrum')
                
                # --- Stepwise Integral (Cumulative Sum) ---
                if "1H" in spectrum_type:
                    # Create secondary axis for integral to avoid clipping
                    ax_int = ax.twinx()
                    
                    sort_idx = np.argsort(x) # Low PPM to High PPM (0 -> 10)
                    x_sorted = x[sort_idx]
                    y_sorted = y[sort_idx]
                    
                    # Cumulative sum (Integration)
                    integral = np.cumsum(y_sorted)
                    
                    # Normalize to fit 0-1 range roughly, scaled to 80%
                    if np.max(integral) > 0:
                        integral = integral / np.max(integral) * 0.8 
                    
                    # [Instruction: Stepwise Calculus]
                    # 'steps-post': The interval [x[i], x[i+1]] has value y[i]
                    ax_int.plot(x_sorted, integral, color='blue', linestyle='-', linewidth=1.5, 
                               alpha=0.8, drawstyle='steps-post', label='Integral')
                    
                    ax_int.set_ylim(0, 1.0) 
                    ax_int.set_yticks([]) 

                ax.set_xlabel(f"{nucleus} Chemical Shift (ppm)")
                ax.set_ylabel("Intensity")
                ax.invert_xaxis() # High PPM on left
                
                # --- Zoning Labels ---
                ylim = ax.get_ylim()
                y_zone = ylim[1] * 0.95
                if "1H" in spectrum_type:
                    ax.text(1.0, y_zone, "Aliphatic", ha='center', fontsize=8, color='gray', alpha=0.7)
                    ax.text(7.5, y_zone, "Aromatic", ha='center', fontsize=8, color='gray', alpha=0.7)
                elif "13C" in spectrum_type:
                    ax.text(25, y_zone, "Aliphatic", ha='center', fontsize=8, color='gray', alpha=0.7)
                    ax.text(130, y_zone, "Aromatic", ha='center', fontsize=8, color='gray', alpha=0.7)
                    ax.text(190, y_zone, "Carbonyl", ha='center', fontsize=8, color='gray', alpha=0.7)

                # --- Atom Mapping Labels ---
                # [Instruction: Assignment Mapping]
                peaks = data.get('peaks', [])
                atom_label_map = {}
                for i, p in enumerate(peaks):
                    px, py = p[0], p[1]
                    # Assign number starting from 1
                    label = str(i + 1)
                    atom_label_map[i] = label
                    
                    # Annotation on Peak
                    ax.annotate(label, xy=(px, py), xytext=(px, py + max(y)*0.08),
                                ha='center', va='bottom', fontsize=9, fontweight='bold', color='white',
                                bbox=dict(boxstyle="circle,pad=0.2", fc=f"C{i%10}", ec="none"))

                # --- Inset Relocation ---
                # [Instruction: Safe-Zone Inset]
                # Force to left top (10.0 ~ 8.5 ppm) - Empty region
                if len(peaks) > 0 and "1H" in spectrum_type:
                    max_peak = max(peaks, key=lambda p: p[1])
                    center_ppm = max_peak[0]
                    span = 0.2
                    
                    # Safe zone: Top-Left (High PPM).
                    # Axes fraction: (0, 1) is Top-Left.
                    # Position: x=0.02 (Left edge), y=0.55 (Mid-Top)
                    ax_ins = ax.inset_axes([0.02, 0.55, 0.25, 0.25])
                    
                    mask_zoom = (x >= center_ppm - span) & (x <= center_ppm + span)
                    if np.any(mask_zoom):
                        ax_ins.plot(x[mask_zoom], y[mask_zoom], color='red', linewidth=1.5)
                        ax_ins.set_title(f"Zoom @ {center_ppm:.2f}", fontsize=8)
                        ax_ins.invert_xaxis()
                        ax_ins.set_yticks([])
                        ax_ins.tick_params(labelsize=6)
                        ax_ins.grid(True, linestyle=':')
                        # Background to ensure separation
                        ax_ins.patch.set_alpha(0.8)

                # --- Structure Image on Graph ---
                temp_struct_path = None
                if smiles and RDKIT_AVAILABLE:
                    temp_struct_path = output_path.parent / f"temp_struct_{spectrum_type}.png"
                    if generate_structure_image_with_labels(smiles, atom_label_map, temp_struct_path):
                        structure_image_path = str(temp_struct_path)
                
                if structure_image_path and os.path.exists(structure_image_path):
                    try:
                        img = plt.imread(structure_image_path)
                        imagebox = OffsetImage(img, zoom=0.35, alpha=0.9)
                        # Place in top right (low ppm, usually empty)
                        ab = AnnotationBbox(imagebox, (0.85, 0.75), xycoords='axes fraction', frameon=False)
                        ax.add_artist(ab)
                    except Exception as e:
                        pass
                
                if temp_struct_path and temp_struct_path.exists():
                    try:
                        os.remove(temp_struct_path)
                    except:
                        pass

            elif spectrum_type == "Mass":
                # Mass Spectrum (EI-MS) — stem plot
                x = np.array(data.get('x', []))
                y = np.array(data.get('y', []))

                if x.size > 0 and y.size > 0:
                    ax.stem(x, y, linefmt='b-', markerfmt='bo', basefmt='k-')
                    ax.set_xlabel("m/z")
                    ax.set_ylabel("Relative Intensity (%)")
                    ax.set_ylim(0, 110)
                    # Annotate top peaks
                    peaks = data.get('peaks', [])
                    for p in sorted(peaks, key=lambda p: p[1], reverse=True)[:5]:
                        px, py = p[0], p[1]
                        ax.annotate(f"{px:.1f}", xy=(px, py), xytext=(px, py + 5),
                                    ha='center', fontsize=8, fontweight='bold',
                                    arrowprops=dict(arrowstyle='->', color='red', alpha=0.6))

        # [Instruction 1: Frame Safety]
        # Save with bbox_inches='tight' to handle clipping automatically
        # fig.tight_layout() # Removed to avoid conflicts with insets

        fig.savefig(str(output_path), bbox_inches='tight')
        logger.info(f"Generated graph: {output_path}")
        plt.close(fig) # Close memory
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
        self.font_name = "Helvetica" 
        self.register_fonts()

    def register_fonts(self):
        """Register fonts that support special characters if available."""
        if not REPORTLAB_AVAILABLE:
            return
        font_paths = [
            "C:/Windows/Fonts/malgun.ttf", 
            "C:/Windows/Fonts/arial.ttf",
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
                    pass
        
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
        """
        if not REPORTLAB_AVAILABLE:
            logger.error("Cannot generate PDF: ReportLab is missing.")
            return None

        if filename is None:
            safe_name = "".join(c for c in molecule_name if c.isalnum() or c in (' ', '_', '-')).strip()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_Report_{timestamp}.pdf"

        output_path = self.output_dir / filename
        temp_dir = self.output_dir / "temp_assets"
        ensure_dir(temp_dir)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=50, leftMargin=50,
            topMargin=50, bottomMargin=50
        )

        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle('ReportTitle', parent=styles['Heading1'], fontName=self.font_name, fontSize=24, alignment=1, spaceAfter=20)
        header_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontName=self.font_name, fontSize=16, textColor=colors.darkblue, spaceBefore=15, spaceAfter=10)
        text_style = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontName=self.font_name, fontSize=10, leading=14)

        # Title
        elements.append(Paragraph(f"Spectral Analysis Report", title_style))
        elements.append(Paragraph(f"Molecule: {molecule_name}", styles['Heading2']))
        
        if metadata:
            if 'iupac_name' in metadata: elements.append(Paragraph(f"<b>IUPAC Name:</b> {metadata['iupac_name']}", text_style))
            if 'common_name' in metadata: elements.append(Paragraph(f"<b>Common Name:</b> {metadata['common_name']}", text_style))
            if 'formula' in metadata: elements.append(Paragraph(f"<b>Molecular Formula:</b> {metadata['formula']}", text_style))
        
        elements.append(Paragraph(f"Date: {get_timestamp()}", text_style))
        elements.append(Spacer(1, 20))

        # Structure
        # If RDKit is available, structure is handled per-spectrum or here?
        # Let's keep the main structure image if provided.
        if structure_image_path and os.path.exists(structure_image_path):
            try:
                img = RLImage(structure_image_path)
                max_width = 400; max_height = 300
                aspect = img.imageWidth / float(img.imageHeight)
                if img.imageWidth > max_width:
                    img.drawWidth = max_width; img.drawHeight = max_width / aspect
                elif img.imageHeight > max_height:
                    img.drawHeight = max_height; img.drawWidth = max_height * aspect
                elements.append(Paragraph("Molecular Structure", header_style))
                elements.append(img)
                elements.append(Spacer(1, 20))
            except Exception as e:
                pass

        # Spectra
        spectra_types = [("IR", "Infrared Spectrum (IR)"), ("Raman", "Raman Spectrum"),
                         ("UV-Vis", "UV-Vis Spectrum"), ("NMR_1H", "¹H NMR Spectrum"), ("NMR_13C", "¹³C NMR Spectrum"),
                         ("Mass", "Mass Spectrum (EI-MS)")]

        for spec_key, spec_title in spectra_types:
            if spec_key in spectra_data:
                elements.append(PageBreak())
                elements.append(Paragraph(spec_title, header_style))
                
                spec_info = spectra_data[spec_key]
                graph_filename = f"graph_{spec_key}_{datetime.datetime.now().strftime('%f')}.png"
                graph_path = temp_dir / graph_filename
                
                # Use SMILES from data if available, or fallback to metadata
                spec_smiles = spec_info.get("smiles", metadata.get("smiles", None))

                # Pass structure image path for UV-Vis diagram
                if generate_spectrum_graph(spec_key, spec_info, graph_path, molecule_name, 
                                          structure_image_path=structure_image_path,
                                          smiles=spec_smiles):
                    # Adjust image size for UV-Vis dual plot
                    if spec_key == "UV-Vis":
                        img = RLImage(str(graph_path), width=500, height=250)
                    else:
                        img = RLImage(str(graph_path), width=450, height=300)
                    elements.append(img)
                else:
                    elements.append(Paragraph("[Graph generation failed]", text_style))
                
                elements.append(Spacer(1, 10))
                
                if 'peaks' in spec_info and spec_info['peaks']:
                    elements.append(Paragraph("Peak List:", styles['Heading3']))
                    table_data = [['Frequency / Shift', 'Intensity']]
                    for p in spec_info['peaks']:
                         table_data.append([f"{p[0]:.2f}", f"{p[1]:.2f}"])
                    if len(table_data) > 15: table_data = table_data[:15] + [["...", "..."]]
                    t = Table(table_data, colWidths=[150, 150])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ]))
                    elements.append(t)
                
                if 'notes' in spec_info:
                    elements.append(Paragraph(f"<b>Interpretation:</b> {spec_info['notes']}", text_style))

        try:
            doc.build(elements)
            logger.info(f"PDF Report generated successfully: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"Failed to build PDF document: {e}")
            return None

# ============================================================================
# MAIN EXECUTION (CLI MODE)
# ============================================================================

if __name__ == "__main__":
    print("ENTERING MAIN BLOCK")
    try:
        print("Running Spectrum PDF Exporter Test Mode (v1.3)...")
        
        # 1. Mock Data for Testing (Ethyl Benzoate)
        # [Instruction: Molecular Complexity Upgrade]
        
        # IR
        x_ir = np.linspace(4000, 400, 1000)
        y_ir = 100 * np.ones_like(x_ir)
        # C=O (1720), C-O (1270), C-H (2980), Ar C=C (1600, 1450)
        peaks_ir = [(2980, 20, 30), (1720, 80, 20), (1600, 30, 20), (1450, 40, 20), (1270, 70, 20), (710, 60, 15)]
        for center, depth, width in peaks_ir:
            y_ir -= depth * np.exp(-((x_ir - center)**2) / (2 * width**2))

        # Raman
        x_raman = np.linspace(0, 3500, 1000)
        y_raman = np.zeros_like(x_raman)
        # Ring breathing (~1000), C=O (~1720)
        for center, height, width in [(1720, 0.5, 15), (1002, 1.0, 5), (3070, 0.3, 20)]:
            y_raman += height * np.exp(-((x_raman - center)**2) / (2 * width**2))

        # UV-Vis (Ethyl Benzoate has benzoyl chromophore)
        x_uv = np.linspace(200, 800, 1000) 
        y_uv = np.zeros_like(x_uv)
        # Pi->Pi* (~230 nm), n->Pi* (~270-280 nm weak)
        for center, height, width in [(228, 0.8, 15), (272, 0.1, 20)]:
            y_uv += height * np.exp(-((x_uv - center)**2) / (2 * width**2))

        # 1H NMR (Ethyl Benzoate)
        # Triplet (CH3, ~1.4), Quartet (CH2, ~4.4), Aromatic (7.4-8.1)
        x_h1 = np.linspace(12, -2, 2000)
        y_h1 = np.zeros_like(x_h1)
        
        # CH3 (Triplet at 1.4 ppm) - Integral 3
        for shift in [1.35, 1.40, 1.45]:
            y_h1 += 2.0 * np.exp(-((x_h1 - shift)**2) / 0.0005)
            
        # CH2 (Quartet at 4.4 ppm) - Integral 2
        for shift in [4.33, 4.38, 4.43, 4.48]:
            y_h1 += 1.5 * np.exp(-((x_h1 - shift)**2) / 0.0005)

        # Aromatic (Multiplets at ~7.4, ~7.5, ~8.0) - Integral 5
        # Meta/Para (~7.4-7.5)
        for shift in [7.4, 7.45, 7.5, 7.55]:
             y_h1 += 1.8 * np.exp(-((x_h1 - shift)**2) / 0.0005)
        # Ortho (~8.05)
        for shift in [8.03, 8.08]:
             y_h1 += 2.0 * np.exp(-((x_h1 - shift)**2) / 0.0005)
             
        # Solvent (CDCl3)
        y_h1 += 0.5 * np.exp(-((x_h1 - 7.26)**2) / 0.0002)

        # 13C NMR
        # C=O (166), Ar-C (132, 130, 129, 128), O-CH2 (61), CH3 (14)
        x_c13 = np.linspace(220, 0, 2000)
        y_c13 = np.zeros_like(x_c13)
        peaks_c13 = [166.5, 132.8, 130.5, 129.5, 128.3, 61.3, 14.3]
        for p in peaks_c13:
            y_c13 += 5.0 * np.exp(-((x_c13 - p)**2) / 0.02)
        
        # Solvent (CDCl3 triplet 77)
        for s in [76.5, 77.0, 77.5]:
            y_c13 += 1.0 * np.exp(-((x_c13 - s)**2) / 0.02)

        smiles = "CCOC(=O)c1ccccc1"

        mock_data = {
            "IR": {
                "x": x_ir, "y": y_ir,
                "peaks": [(2980, 20), (1720, 20), (1270, 30), (710, 40)],
                "notes": "Strong C=O stretch at 1720 cm-1, C-O stretch at 1270 cm-1.",
                "smiles": smiles
            },
            "Raman": {
                "x": x_raman, "y": y_raman,
                "peaks": [(1002, 1.0), (1720, 0.5)],
                "notes": "Ring breathing mode characteristic of mono-substituted benzene.",
                "smiles": smiles
            },
            "UV-Vis": {
                "x": x_uv, "y": y_uv,
                "peaks": [(228, 0.8), (272, 0.1)],
                "notes": "Pi-Pi* transition at 228 nm.",
                "smiles": smiles
            },
            "NMR_1H": {
                "x": x_h1, "y": y_h1,
                "peaks": [(8.05, 10.0, "1"), (7.5, 8.0, "2"), (7.4, 8.0, "3"), (4.4, 6.0, "4"), (1.4, 8.0, "5")], # Simplified peaks
                "notes": "Ethyl group (q, t) and aromatic region (m).",
                "smiles": smiles
            },
            "NMR_13C": {
                "x": x_c13, "y": y_c13,
                "peaks": [(166.5, 10.0), (132.8, 8.0), (128.3, 8.0), (61.3, 6.0), (14.3, 5.0)],
                "notes": "Carbonyl at 166.5 ppm, O-CH2 at 61.3 ppm.",
                "smiles": smiles
            }
        }

        exporter = SpectrumPDFExporter(output_dir="docs/exports/spectra_assets/auto_generated")
        
        main_struct_path = "docs/exports/spectra_assets/structure_ethyl_benzoate.png"
        ensure_dir(Path(main_struct_path).parent)
        generate_structure_image_with_labels(smiles, {}, Path(main_struct_path))

        metadata = {
            "iupac_name": "Ethyl Benzoate",
            "common_name": "Ethyl Benzoate",
            "formula": "C9H10O2",
            "smiles": smiles
        }
        
        pdf_path = exporter.create_report(
            molecule_name="Ethyl Benzoate (Test v1.4)",
            spectra_data=mock_data,
            structure_image_path=main_struct_path,
            metadata=metadata
        )
        
        if pdf_path:
            print(f"\n[SUCCESS] PDF Report generated:\n -> {pdf_path}")
        else:
            print("\n[ERROR] Failed to generate PDF report.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRASH: {e}")
