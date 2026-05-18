# export_manager_enhanced.py (v4.0 - 8-Page Integrated PDF + .chem Enhancement)
"""
ChemGrid Pro Phase 5/6/7: Advanced Export Manager
- Export selected molecular structures (Lasso Select)
- PNG (white/transparent background), PDF, SVG support
- High-resolution DPI settings (up to 300 DPI)
- EXIF metadata embedding
- Lewis structure & Theory structure layers support
- [v3.0] 6-page integrated PDF report (2D, IR, NMR, UV-Vis, 3D, Reaction)
- [v3.0] Enhanced .chem save/load with metadata + version header
- [v4.0] 8-page PDF: +Page 7 (ADMET Analysis) +Page 8 (Drug Screening Results)
"""

import os
import io
import json
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (QFileDialog, QMessageBox, QDialog, QVBoxLayout,
                                 QHBoxLayout, QLabel, QSpinBox, QComboBox,
                                 QCheckBox, QPushButton, QGroupBox, QApplication)
    from PyQt6.QtGui import QPainter, QImage, QColor, QPen, QBrush, QFont
    from PyQt6.QtCore import Qt, QRect, QPointF, QSize
    from PyQt6.QtSvg import QSvgGenerator
    from PyQt6.QtPrintSupport import QPrinter
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch, cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, PageBreak, Image as RLImage)
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Korean font registration (shared with spectrum_pdf_exporter)
_KOREAN_FONT = 'Helvetica'
def _register_korean_font():
    global _KOREAN_FONT
    if not REPORTLAB_AVAILABLE:
        return
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        # Rule Q: Korean/Unicode font registration — Malgun Gothic preferred,
        # NanumGothic fallback, Gulim last resort
        for fp, name in [
            ('C:/Windows/Fonts/malgun.ttf', 'Malgun'),
            ('C:/Windows/Fonts/NanumGothic.ttf', 'NanumGothic'),
            ('C:/Windows/Fonts/gulim.ttc', 'Gulim'),
        ]:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont(name, fp))
                    _KOREAN_FONT = name
                    return
                except Exception as e:
                    logger.debug("SMILES processing failed, skipping: %s", e)
                    continue
    except ImportError as e:
        logger.debug("Optional import unavailable: %s", e)

_register_korean_font()


# ============================================================================
# CHEM FILE FORMAT (v2) - Enhanced save/load with metadata
# ============================================================================

CHEM_FORMAT_VERSION = "2.0"


@dataclass
class ChemFileMetadata:
    """Metadata header for .chem files (v2.0+)"""
    version: str = CHEM_FORMAT_VERSION
    molecule_name: str = ""
    smiles: str = ""
    molecular_formula: str = ""
    view_state: str = "Lewis"
    created_at: str = ""
    modified_at: str = ""
    software: str = "ChemGrid Pro v2.0"
    atom_count: int = 0
    bond_count: int = 0
    has_analysis: bool = False

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        self.modified_at = now


class ChemFileManager:
    """
    Enhanced .chem file manager with version header and metadata preservation.

    v1 format: {"atoms": {...}, "bonds": {...}}
    v2 format: {"_chem_version": "2.0", "_metadata": {...}, "atoms": {...},
                "bonds": {...}, "arrows": [...], "text_boxes": [...],
                "analysis_snapshot": {...}}

    Backward-compatible: loads v1 files transparently.
    """

    @staticmethod
    def build_save_data(canvas, metadata: Optional[ChemFileMetadata] = None) -> Dict[str, Any]:
        """
        Build a v2 save payload from a canvas widget.

        Args:
            canvas: MoleculeCanvas instance (has .atoms, .bonds, .arrows, .text_boxes)
            metadata: Optional pre-filled metadata. Auto-populated if None.

        Returns:
            Dictionary ready for json.dump
        """
        # Serialize atoms
        s_atoms: Dict[str, Any] = {}
        for k, v in canvas.atoms.items():
            atom_copy = dict(v)
            if "user_lp" in atom_copy and isinstance(atom_copy["user_lp"], set):
                atom_copy["user_lp"] = list(atom_copy["user_lp"])
            s_atoms[f"{k[0]},{k[1]}"] = atom_copy

        # Serialize bonds
        s_bonds: Dict[str, Any] = {}
        for (k1, k2), v in canvas.bonds.items():
            b_key = f"{k1[0]},{k1[1]}|{k2[0]},{k2[1]}"
            if isinstance(v, tuple) and len(v) == 3:
                # Wedge/Dash bond: (QPointF, QPointF, type_int)
                try:
                    s_bonds[b_key] = [[v[0].x(), v[0].y()], [v[1].x(), v[1].y()], v[2]]
                except AttributeError:
                    s_bonds[b_key] = v
            else:
                s_bonds[b_key] = v

        # Serialize arrows
        s_arrows = []
        for arrow in getattr(canvas, 'arrows', []):
            if isinstance(arrow, (list, tuple)) and len(arrow) == 2:
                a_s, a_e = arrow
                try:
                    s_arrows.append([[a_s.x(), a_s.y()], [a_e.x(), a_e.y()]])
                except AttributeError:
                    s_arrows.append(arrow)

        # Serialize text_boxes
        s_text_boxes = []
        for tb in getattr(canvas, 'text_boxes', []):
            try:
                s_text_boxes.append({
                    "pos": [tb["pos"].x(), tb["pos"].y()],
                    "text": tb["text"],
                    "font_size": tb.get("font_size", 12),
                })
            except (AttributeError, KeyError):
                s_text_boxes.append(tb)

        # Build metadata
        if metadata is None:
            metadata = ChemFileMetadata()
        metadata.atom_count = len(s_atoms)
        metadata.bond_count = len(s_bonds)
        metadata.view_state = getattr(canvas, 'view_state', 'Lewis')
        # Try to get SMILES and molecule name from canvas
        if not metadata.smiles:
            metadata.smiles = _safe_get_smiles(canvas)
        if not metadata.molecule_name:
            metadata.molecule_name = getattr(canvas, 'selected_molecule_name', '')
        metadata.modified_at = datetime.now().isoformat()

        # Capture analysis snapshot (lightweight summary, not full data)
        analysis_snapshot = {}
        ar = getattr(canvas, 'analysis_results', None)
        if ar and isinstance(ar, dict):
            metadata.has_analysis = True
            for safe_key in ('molecular_formula', 'smiles', 'identified_name',
                             'functional_groups', 'aromatic_count', 'stereo_centers'):
                if safe_key in ar:
                    val = ar[safe_key]
                    # Only store JSON-serializable values
                    if isinstance(val, (str, int, float, bool, list)):
                        analysis_snapshot[safe_key] = val
            if not metadata.molecular_formula and 'molecular_formula' in ar:
                metadata.molecular_formula = str(ar['molecular_formula'])

        save_data = {
            "_chem_version": CHEM_FORMAT_VERSION,
            "_metadata": asdict(metadata),
            "atoms": s_atoms,
            "bonds": s_bonds,
            "arrows": s_arrows,
            "text_boxes": s_text_boxes,
        }
        if analysis_snapshot:
            save_data["analysis_snapshot"] = analysis_snapshot

        return save_data

    @staticmethod
    def parse_load_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a .chem file payload (v1 or v2) into a normalized structure.

        Returns dict with keys:
            atoms, bonds, arrows, text_boxes, metadata (ChemFileMetadata or None),
            analysis_snapshot (dict or None), version (str)
        """
        if not isinstance(data, dict):
            logger.warning("parse_load_data: data is not dict (type=%s)", type(data).__name__)
            data = {}
        version = data.get("_chem_version", "1.0")
        raw_meta = data.get("_metadata")
        metadata = None
        if raw_meta and isinstance(raw_meta, dict):
            try:
                metadata = ChemFileMetadata(**{
                    k: v for k, v in raw_meta.items()
                    if k in ChemFileMetadata.__dataclass_fields__
                })
            except Exception as e:
                logger.debug("Metadata parsing failed: %s", e)
                metadata = None

        assert isinstance(data, dict)  # Rule N: 타입 가드 (재확인)
        return {
            "atoms": data.get("atoms", {}),
            "bonds": data.get("bonds", {}),
            "arrows": data.get("arrows", []),
            "text_boxes": data.get("text_boxes", []),
            "metadata": metadata,
            "analysis_snapshot": data.get("analysis_snapshot"),
            "version": version,
        }

    @staticmethod
    def get_metadata_from_file(filepath: str) -> Optional[ChemFileMetadata]:
        """Read only the metadata header from a .chem file without full load."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Rule N: isinstance guard for data
            if not isinstance(data, dict): data = {}
            raw = data.get("_metadata")
            if raw and isinstance(raw, dict):
                return ChemFileMetadata(**{
                    k: v for k, v in raw.items()
                    if k in ChemFileMetadata.__dataclass_fields__
                })
        except Exception as e:
            logger.warning("Failed to read .chem metadata from %s: %s", filepath, e)
        return None


def _safe_get_smiles(canvas) -> str:
    """Safely get SMILES from canvas."""
    try:
        if hasattr(canvas, 'get_smiles'):
            return canvas.get_smiles() or ""
        return getattr(canvas, '_last_drawn_smiles', '') or ""
    except Exception as e:
        logger.warning("Content extraction failed: %s", e)
        return ""


# ============================================================================
# 6-PAGE INTEGRATED PDF EXPORTER
# ============================================================================

@dataclass
class IntegratedPDFPageData:
    """Data for a single page in the 6-page PDF report"""
    page_title: str
    page_type: str  # "structure_2d", "ir", "nmr", "uvvis", "structure_3d", "reaction"
    image_path: Optional[str] = None
    peaks: Optional[List[Dict]] = None
    description: str = ""
    available: bool = False


class IntegratedPDFExporter:
    """
    Multi-page integrated PDF analytical chemistry report generator.

    Pages:
      1. Molecular Structure (2D drawing + key properties: MW, formula, SMILES)
      2. IR Spectrum (full graph + peak table with functional group assignments)
      3. 1H NMR Spectrum (full graph + chemical shift table)
      4. 13C NMR Spectrum (full graph + peak assignments)
      5. UV-Vis Spectrum (lambda_max values + molar absorptivity)
      6. Mass Spectrum (molecular ion peak + fragmentation pattern) [placeholder if unavailable]
      7. ADMET Analysis (Lipinski Ro5, BBB, Metabolism, Drug-likeness)
      8. Drug Screening Results (QED, Composite Score, Tier Classification)

    Falls back gracefully when reportlab is missing (uses QPrinter-based PDF).
    Each page is optional; unavailable sections display a placeholder message.
    """

    def __init__(self, molecule_name: str = "", smiles: str = "",
                 molecular_formula: str = "", calculation_method: str = "B3LYP/6-31G(d)"):
        self.molecule_name = molecule_name or "Unknown Molecule"
        self.smiles = smiles
        self.molecular_formula = molecular_formula
        self.calculation_method = calculation_method
        self.pages: Dict[str, IntegratedPDFPageData] = {}
        self._temp_files: List[str] = []

    # -- Page setters -------------------------------------------------------

    def set_2d_structure(self, image_path: str, description: str = ""):
        """Set page 1: 2D structural formula image."""
        self.pages["structure_2d"] = IntegratedPDFPageData(
            page_title="2D Structural Formula",
            page_type="structure_2d",
            image_path=image_path,
            description=description or f"Lewis structure of {self.molecule_name}",
            available=True,
        )

    def set_ir_spectrum(self, image_path: Optional[str] = None,
                        peaks: Optional[List[Dict]] = None, description: str = ""):
        """Set page 2: IR spectrum."""
        self.pages["ir"] = IntegratedPDFPageData(
            page_title="IR Spectrum",
            page_type="ir",
            image_path=image_path,
            peaks=peaks,
            description=description or f"Infrared spectrum of {self.molecule_name}",
            available=bool(image_path or peaks),
        )

    def set_nmr_spectrum(self, image_path: Optional[str] = None,
                         peaks: Optional[List[Dict]] = None, description: str = "",
                         nmr_type: str = "1H"):
        """Set page 3: 1H NMR spectrum."""
        self.pages["nmr"] = IntegratedPDFPageData(
            page_title=f"\u00b9H NMR Spectrum",
            page_type="nmr",
            image_path=image_path,
            peaks=peaks,
            description=description or f"\u00b9H NMR spectrum of {self.molecule_name}",
            available=bool(image_path or peaks),
        )

    def set_nmr_c13_spectrum(self, image_path: Optional[str] = None,
                              peaks: Optional[List[Dict]] = None, description: str = ""):
        """Set page 4: 13C NMR spectrum."""
        self.pages["nmr_c13"] = IntegratedPDFPageData(
            page_title="\u00b9\u00b3C NMR Spectrum",
            page_type="nmr_c13",
            image_path=image_path,
            peaks=peaks,
            description=description or f"\u00b9\u00b3C NMR spectrum of {self.molecule_name}",
            available=bool(image_path or peaks),
        )

    def set_uvvis_spectrum(self, image_path: Optional[str] = None,
                           peaks: Optional[List[Dict]] = None, description: str = ""):
        """Set page 5: UV-Vis spectrum."""
        self.pages["uvvis"] = IntegratedPDFPageData(
            page_title="UV-Vis Spectrum",
            page_type="uvvis",
            image_path=image_path,
            peaks=peaks,
            description=description or f"UV-Vis absorption spectrum of {self.molecule_name}",
            available=bool(image_path or peaks),
        )

    def set_mass_spectrum(self, image_path: Optional[str] = None,
                          peaks: Optional[List[Dict]] = None, description: str = ""):
        """Set page 6: Mass spectrum."""
        self.pages["mass"] = IntegratedPDFPageData(
            page_title="Mass Spectrum (EI-MS)",
            page_type="mass",
            image_path=image_path,
            peaks=peaks,
            description=description or f"Electron impact mass spectrum of {self.molecule_name}",
            available=bool(image_path or peaks),
        )

    def set_3d_structure(self, image_path: str, description: str = ""):
        """Set page 5: 3D optimized structure image."""
        self.pages["structure_3d"] = IntegratedPDFPageData(
            page_title="3D Optimized Structure",
            page_type="structure_3d",
            image_path=image_path,
            description=description or f"Geometry-optimized structure of {self.molecule_name}",
            available=True,
        )

    def set_reaction_mechanism(self, image_path: Optional[str] = None,
                               description: str = ""):
        """Set page 6: Reaction mechanism."""
        self.pages["reaction"] = IntegratedPDFPageData(
            page_title="Reaction Mechanism",
            page_type="reaction",
            image_path=image_path,
            description=description or "Reaction mechanism information",
            available=bool(image_path or description),
        )

    def set_admet_data(self, admet_profile: Optional[Dict] = None):
        """
        Set page 7: ADMET analysis results.

        Args:
            admet_profile: Dict from admet_predictor.admet_to_dict() or raw ADMETProfile fields.
                Expected keys: lipinski, bbb, metabolic_stability, drug_likeness_score,
                oral_bioavailability, overall_assessment, warnings, descriptors.
        """
        page = IntegratedPDFPageData(
            page_title="ADMET 분석 결과 (ADMET Analysis)",
            page_type="admet",
            description="",
            available=False,
        )
        if admet_profile and isinstance(admet_profile, dict) and not admet_profile.get("error"):
            page.available = True
            page.peaks = [admet_profile]  # Store profile dict in peaks field for convenience
            page.description = admet_profile.get("overall_assessment", "")
        self.pages["admet"] = page

    def set_drug_screening_data(self, screening_result: Optional[Dict] = None):
        """
        Set page 8: Drug screening results.

        Args:
            screening_result: Dict from drug_screening.screening_result_to_dict() or
                a list of hit dicts under the "hits" key.
                Each hit: {rank, smiles, name, composite_score, tier, qed, ...}
        """
        page = IntegratedPDFPageData(
            page_title="신약 스크리닝 결과 (Drug Screening Results)",
            page_type="drug_screening",
            description="",
            available=False,
        )
        if screening_result and isinstance(screening_result, dict):
            hits = screening_result.get("hits", [])
            if not isinstance(hits, list):
                hits = []
            if hits or screening_result.get("n_compounds", 0) > 0:
                page.available = True
                page.peaks = [screening_result]  # Store full result in peaks field
                page.description = (
                    f"Screened {screening_result.get('n_compounds', '?')} compounds, "
                    f"{screening_result.get('n_hits', 0)} hits identified"
                )
        self.pages["drug_screening"] = page

    # -- Canvas capture helpers ---------------------------------------------

    def capture_canvas_state(self, canvas, view_state: str) -> Optional[str]:
        """
        Capture canvas as a temporary PNG for embedding in PDF.

        Args:
            canvas: MoleculeCanvas widget
            view_state: "Lewis" or "Theory"

        Returns:
            Path to temporary PNG file, or None on failure.
        """
        if not PYQT_AVAILABLE:
            return None
        try:
            import math as _math
            original_state = getattr(canvas, 'view_state', 'Lewis')
            original_radius = getattr(canvas, '_reveal_radius', 0)
            original_center = getattr(canvas, 'reveal_center', None)
            canvas.view_state = view_state
            # [FIX-CAPTURE] Rule: _reveal_radius must equal max_r for offscreen capture.
            # If radius=0 (animation not started), Lewis/Theory layer renders blank.
            # chemgrid_architecture.md: "_reveal_radius = max_r 필수"
            if view_state in ("Lewis", "Theory"):
                max_r = _math.hypot(canvas.width() or 800, canvas.height() or 600)
                canvas._reveal_radius = max_r  # reveal full canvas for capture
                from PyQt6.QtCore import QPointF as _QPointF
                canvas.reveal_center = _QPointF(
                    (canvas.width() or 800) / 2,
                    (canvas.height() or 600) / 2
                )
            canvas.update()
            QApplication.processEvents()

            tmp_path = os.path.join(
                tempfile.gettempdir(),
                f"chemgrid_{view_state.lower()}_{os.getpid()}_{id(self)}.png"
            )
            pixmap = canvas.grab()
            if pixmap.isNull():
                logger.warning("capture_canvas_state: grab() returned null pixmap for %s", view_state)
            pixmap.save(tmp_path)
            self._temp_files.append(tmp_path)

            # Restore original state
            canvas.view_state = original_state
            canvas._reveal_radius = original_radius
            if original_center is not None:
                canvas.reveal_center = original_center
            canvas.update()
            QApplication.processEvents()

            return tmp_path
        except Exception as e:
            logger.error("Canvas capture failed for %s: %s", view_state, e)
            return None

    # -- PDF generation -----------------------------------------------------

    def export_pdf(self, output_path: str) -> bool:
        """
        Generate the 6-page integrated PDF.

        Args:
            output_path: Destination file path.

        Returns:
            True on success, False on failure.
        """
        if REPORTLAB_AVAILABLE:
            return self._export_pdf_reportlab(output_path)
        elif PYQT_AVAILABLE:
            return self._export_pdf_qprinter(output_path)
        else:
            logger.error("Neither reportlab nor PyQt6 available for PDF export")
            return False

    def _export_pdf_reportlab(self, output_path: str) -> bool:
        """Generate PDF using reportlab (professional analytical chemistry report)."""
        try:
            doc = SimpleDocTemplate(
                output_path, pagesize=A4,
                leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                topMargin=2 * cm, bottomMargin=2 * cm,
            )
            story = []

            # -- Page 1: Title + 2D Structure + Key Properties --
            # Rule N: 타입 가드 — self.pages는 dict
            assert isinstance(self.pages, dict)
            story.extend(self._rl_title_page())

            # -- Page 2: IR Spectrum --
            story.append(PageBreak())
            ir_page = self.pages.get("ir")
            if ir_page and ir_page.available:
                story.extend(self._rl_content_page(ir_page))
            else:
                story.extend(self._rl_placeholder_page("ir"))

            # -- Page 3: 1H NMR Spectrum --
            story.append(PageBreak())
            nmr_page = self.pages.get("nmr")
            if nmr_page and nmr_page.available:
                story.extend(self._rl_content_page(nmr_page))
            else:
                story.extend(self._rl_placeholder_page("nmr"))

            # -- Page 4: 13C NMR Spectrum -- Rule N: isinstance
            assert isinstance(self.pages, dict)
            story.append(PageBreak())
            nmr_c13_page = self.pages.get("nmr_c13")
            if nmr_c13_page and nmr_c13_page.available:
                story.extend(self._rl_content_page(nmr_c13_page))
            else:
                story.extend(self._rl_placeholder_page("nmr_c13"))

            # -- Page 5: UV-Vis Spectrum --
            story.append(PageBreak())
            uvvis_page = self.pages.get("uvvis")
            if uvvis_page and uvvis_page.available:
                story.extend(self._rl_content_page(uvvis_page))
            else:
                story.extend(self._rl_placeholder_page("uvvis"))

            # -- Page 6: Mass Spectrum -- Rule N: isinstance
            assert isinstance(self.pages, dict)
            story.append(PageBreak())
            mass_page = self.pages.get("mass")
            if mass_page and mass_page.available:
                story.extend(self._rl_content_page(mass_page))
            else:
                story.extend(self._rl_placeholder_page("mass"))

            # -- Page 7: ADMET Analysis --
            story.append(PageBreak())
            admet_page = self.pages.get("admet")
            if admet_page and admet_page.available:
                story.extend(self._rl_admet_page(admet_page))
            else:
                story.extend(self._rl_placeholder_page("admet"))

            # -- Page 8: Drug Screening Results -- Rule N: isinstance
            assert isinstance(self.pages, dict)
            story.append(PageBreak())
            drug_page = self.pages.get("drug_screening")
            if drug_page and drug_page.available:
                story.extend(self._rl_drug_screening_page(drug_page))
            else:
                story.extend(self._rl_placeholder_page("drug_screening"))

            doc.build(story)
            page_count = 8
            logger.info("Integrated PDF exported: %s (%d pages)", output_path, page_count)
            return True

        except Exception as e:
            logger.error("PDF export failed: %s", e)
            return False

    def _rl_title_page(self) -> List:
        """Build reportlab title page (page 1) with 2D structure."""
        elements = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'IntTitle', parent=styles['Heading1'],
            fontSize=22, textColor=colors.HexColor('#1a1a2e'),
            spaceAfter=20, alignment=TA_CENTER,
            fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph("ChemGrid Pro - Integrated Analysis Report", title_style))
        elements.append(Spacer(1, 0.15 * inch))

        # Molecule info table — include MW if available
        mw_str = "N/A"
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors
            mol = Chem.MolFromSmiles(self.smiles) if self.smiles else None
            if mol is not None:  # Rule L: None guard
                mw_str = f"{Descriptors.ExactMolWt(mol):.4f} g/mol"
        except Exception as e:
            logger.warning("Module import failed: %s", e)
        info_rows = [
            ["Molecule:", self.molecule_name],
            ["SMILES:", self.smiles or "N/A"],
            ["Formula:", self.molecular_formula or "N/A"],
            ["Mol. Weight:", mw_str],
            ["Method:", self.calculation_method],
            ["Date:", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ]
        info_table = Table(info_rows, colWidths=[2.8 * cm, 13.4 * cm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (-1, -1), _KOREAN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bbbbbb')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.3 * inch))

        # 2D Structure image
        page_2d = self.pages.get("structure_2d")
        subtitle_style = ParagraphStyle(
            'SubTitle', parent=styles['Heading2'],
            fontSize=14, textColor=colors.HexColor('#0066cc'),
            spaceAfter=8, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph("2D Structural Formula", subtitle_style))

        if page_2d and page_2d.available and page_2d.image_path and os.path.exists(page_2d.image_path):
            try:
                elements.append(RLImage(page_2d.image_path, width=14 * cm, height=9 * cm,
                                        kind='proportional'))
            except Exception as e:
                logger.warning("Failed to embed 2D image: %s", e)
                elements.append(Paragraph("(2D structure image not available)", styles['Normal']))
        else:
            elements.append(Paragraph("(No 2D structure captured)", styles['Normal']))

        if page_2d and page_2d.description:
            desc_style = ParagraphStyle(
                'Desc', parent=styles['Normal'], fontSize=9,
                textColor=colors.HexColor('#555555'), fontName=_KOREAN_FONT,
            )
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(Paragraph(page_2d.description, desc_style))

        return elements

    def _rl_content_page(self, page_data: IntegratedPDFPageData) -> List:
        """Build a single content page (spectrum or structure) with full-width graph."""
        elements = []
        styles = getSampleStyleSheet()

        # Page title with molecule name and date
        title_text = page_data.page_title
        title_style = ParagraphStyle(
            'PageTitle', parent=styles['Heading2'],
            fontSize=16, textColor=colors.HexColor('#0066cc'),
            spaceAfter=6, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph(title_text, title_style))

        # Subtitle with molecule name and date
        subtitle_style = ParagraphStyle(
            'PageSubtitle', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#666666'),
            spaceAfter=10, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph(
            f"{self.molecule_name} | {datetime.now().strftime('%Y-%m-%d')}",
            subtitle_style))

        # Full-width spectrum image (18cm = A4 width minus margins)
        if page_data.image_path and os.path.exists(page_data.image_path):
            try:
                elements.append(RLImage(page_data.image_path, width=18 * cm, height=7.2 * cm,
                                        kind='proportional'))
                elements.append(Spacer(1, 0.15 * inch))
            except Exception as e:
                logger.warning("Failed to embed image for %s: %s", page_data.page_type, e)

        # Peak table with context-aware column headers
        if page_data.peaks:
            # Choose header labels based on spectrum type
            ptype = page_data.page_type
            if ptype == "ir":
                header = ["Wavenumber", "Intensity", "Functional Group Assignment"]
            elif ptype == "nmr":
                header = ["Chemical Shift", "Integration / Multiplicity", "Assignment"]
            elif ptype == "nmr_c13":
                header = ["Chemical Shift", "Carbon Type", "Assignment (Zone)"]
            elif ptype == "uvvis":
                header = ["\u03bbmax", "Molar Absorptivity (\u03b5)", "Transition / Assignment"]
            elif ptype == "mass":
                header = ["m/z", "Rel. Intensity", "Fragment Assignment"]
            else:
                header = ["Position", "Intensity", "Assignment"]

            elements.append(Paragraph("Peak Analysis Data", ParagraphStyle(
                'PeakTitle', parent=styles['Heading3'], fontSize=11,
                fontName=_KOREAN_FONT,
            )))
            elements.append(Spacer(1, 0.05 * inch))

            rows = [header]
            for peak in page_data.peaks[:30]:  # Limit to 30 peaks
                if not isinstance(peak, dict):
                    continue
                rows.append([
                    str(peak.get("frequency", peak.get("position", ""))),
                    str(peak.get("intensity", "")),
                    str(peak.get("assignment", peak.get("label", ""))),
                ])
            peak_table = Table(rows, colWidths=[4.5 * cm, 4.5 * cm, 9 * cm])
            peak_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#37474f')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, -1), _KOREAN_FONT),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(peak_table)

        # Description
        if page_data.description:
            desc_style = ParagraphStyle(
                'PageDesc', parent=styles['Normal'], fontSize=9,
                textColor=colors.HexColor('#555555'), fontName=_KOREAN_FONT,
                spaceBefore=10,
            )
            elements.append(Paragraph(page_data.description, desc_style))

        return elements

    def _rl_admet_page(self, page_data: IntegratedPDFPageData) -> List:
        """Build page 7: ADMET analysis results using reportlab."""
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'ADMETTitle', parent=styles['Heading2'],
            fontSize=16, textColor=colors.HexColor('#0066cc'),
            spaceAfter=12, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph(page_data.page_title, title_style))
        elements.append(Spacer(1, 0.15 * inch))

        # Extract ADMET profile from peaks[0]
        profile = {}
        if page_data.peaks and isinstance(page_data.peaks, list) and len(page_data.peaks) > 0:
            profile = page_data.peaks[0]

        if not profile:
            elements.append(Paragraph("데이터 없음 (No ADMET data available)",
                                      styles['Normal']))
            return elements

        sub_style = ParagraphStyle(
            'ADMETSub', parent=styles['Heading3'],
            fontSize=12, textColor=colors.HexColor('#333333'),
            spaceAfter=6, spaceBefore=10, fontName=_KOREAN_FONT,
        )
        normal_style = ParagraphStyle(
            'ADMETNormal', parent=styles['Normal'],
            fontSize=9, fontName=_KOREAN_FONT,
        )

        # -- Lipinski Rule of Five --
        if not isinstance(profile, dict):
            logger.warning("ADMET profile is not dict (type=%s)", type(profile).__name__)
            profile = {}
        lipinski = profile.get("lipinski", {})
        if lipinski and isinstance(lipinski, dict):
            elements.append(Paragraph("Lipinski Rule of Five", sub_style))
            lip_rows = [
                ["Property", "Value", "Threshold", "Status"],
                ["MW (Da)", str(lipinski.get("mw", "N/A")), "≤ 500",
                 "PASS" if lipinski.get("mw", 999) <= 500 else "FAIL"],
                ["LogP", str(lipinski.get("logp", "N/A")), "≤ 5",
                 "PASS" if lipinski.get("logp", 999) <= 5 else "FAIL"],
                ["HBD", str(lipinski.get("hbd", "N/A")), "≤ 5",
                 "PASS" if lipinski.get("hbd", 999) <= 5 else "FAIL"],
                ["HBA", str(lipinski.get("hba", "N/A")), "≤ 10",
                 "PASS" if lipinski.get("hba", 999) <= 10 else "FAIL"],
            ]
            lip_table = Table(lip_rows, colWidths=[4 * cm, 3.5 * cm, 3.5 * cm, 3 * cm])
            lip_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#455a64')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, -1), _KOREAN_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                 [colors.white, colors.HexColor('#f5f5f5')]),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ]))
            elements.append(lip_table)
            assert isinstance(lipinski, dict)  # Rule N: 타입 가드
            verdict = "PASS (Drug-like)" if lipinski.get("passes") else "FAIL"
            elements.append(Paragraph(
                f"Lipinski Verdict: {verdict} ({lipinski.get('violations', '?')} violations)",
                normal_style))
            elements.append(Spacer(1, 0.1 * inch))

        # -- BBB Permeability --
        bbb = profile.get("bbb", {})
        if bbb and isinstance(bbb, (dict, str)):
            elements.append(Paragraph("BBB (Blood-Brain Barrier) Permeability", sub_style))
            if isinstance(bbb, str):
                elements.append(Paragraph(bbb, normal_style))
                bbb_rows = None
            else:
                bbb_rows = [
                    ["Parameter", "Value"],
                    ["BBB Score", f"{bbb.get('score', 'N/A')}"],
                    ["Classification", bbb.get("classification", "N/A")],
                    ["TPSA (A²)", f"{bbb.get('tpsa', 'N/A')}"],
                ]
                factors = bbb.get("factors", {})
                if not isinstance(factors, dict):
                    factors = {}
                for fname, fval in factors.items():
                    bbb_rows.append([fname, str(fval)])
            if bbb_rows is not None:
                bbb_table = Table(bbb_rows, colWidths=[5 * cm, 11 * cm])
                bbb_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#455a64')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, -1), _KOREAN_FONT),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                     [colors.white, colors.HexColor('#f5f5f5')]),
                ]))
                elements.append(bbb_table)
            elements.append(Spacer(1, 0.1 * inch))

        # -- Metabolic Stability -- Rule N: isinstance
        assert isinstance(profile, dict)
        metab = profile.get("metabolic_stability", {})
        if metab and isinstance(metab, (dict, str)):
            elements.append(Paragraph("Metabolic Stability", sub_style))
            if isinstance(metab, str):
                elements.append(Paragraph(metab, normal_style))
            else:
                metab_info = (
                    f"Classification: {metab.get('classification', 'N/A')} | "
                    f"Score: {metab.get('score', 'N/A')} | "
                    f"Rotatable Bonds: {metab.get('n_rotatable_bonds', 'N/A')} | "
                    f"Aromatic Rings: {metab.get('n_aromatic_rings', 'N/A')}"
                )
                elements.append(Paragraph(metab_info, normal_style))
                alerts = metab.get("alerts", [])
                if not isinstance(alerts, list):
                    alerts = []
                if alerts:
                    elements.append(Paragraph(
                        f"Metabolic Alerts ({len(alerts)}): " + "; ".join(alerts[:8]),
                        normal_style))
            elements.append(Spacer(1, 0.1 * inch))

        # -- Drug-likeness Summary --
        elements.append(Paragraph("Drug-likeness Summary", sub_style))
        dl_score = profile.get("drug_likeness_score", "N/A")
        oral_ba = profile.get("oral_bioavailability", "N/A")
        assessment = profile.get("overall_assessment", "N/A")
        summary_rows = [
            ["Metric", "Value"],
            ["Drug-likeness Score", f"{dl_score}"],
            ["Oral Bioavailability", oral_ba],
            ["Overall Assessment", assessment],
        ]
        summary_table = Table(summary_rows, colWidths=[5 * cm, 11 * cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), _KOREAN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#f0f0f0')]),
        ]))
        elements.append(summary_table)

        # Warnings
        warnings = profile.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
        if warnings:
            elements.append(Spacer(1, 0.1 * inch))
            warn_style = ParagraphStyle(
                'ADMETWarn', parent=styles['Normal'],
                fontSize=8, textColor=colors.HexColor('#cc3300'),
                fontName=_KOREAN_FONT,
            )
            for w in warnings[:6]:
                elements.append(Paragraph(f"⚠ {w}", warn_style))

        return elements

    def _rl_drug_screening_page(self, page_data: IntegratedPDFPageData) -> List:
        """Build page 8: Drug screening results using reportlab."""
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DrugScreenTitle', parent=styles['Heading2'],
            fontSize=16, textColor=colors.HexColor('#0066cc'),
            spaceAfter=12, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph(page_data.page_title, title_style))
        elements.append(Spacer(1, 0.15 * inch))

        # Extract screening result from peaks[0]
        result = {}
        if page_data.peaks and isinstance(page_data.peaks, list) and len(page_data.peaks) > 0:
            result = page_data.peaks[0]

        if not result:
            elements.append(Paragraph("데이터 없음 (No screening data available)",
                                      styles['Normal']))
            return elements

        normal_style = ParagraphStyle(
            'DSNormal', parent=styles['Normal'],
            fontSize=9, fontName=_KOREAN_FONT,
        )

        # -- Screening summary --
        if not isinstance(result, dict):
            logger.warning("Drug screening result is not dict (type=%s)", type(result).__name__)
            result = {}
        n_compounds = result.get("n_compounds", 0)
        n_hits = result.get("n_hits", 0)
        filters = result.get("filters_applied", [])
        if not isinstance(filters, list):
            filters = []
        elements.append(Paragraph(
            f"Total Compounds Screened: {n_compounds} | Hits: {n_hits}",
            normal_style))
        if filters:
            elements.append(Paragraph(
                "Filters: " + " → ".join(filters[:5]), normal_style))
        elements.append(Spacer(1, 0.15 * inch))

        # -- Candidate table --
        hits = result.get("hits", [])
        if not isinstance(hits, list):
            hits = []
        if hits:
            sub_style = ParagraphStyle(
                'DSSubTitle', parent=styles['Heading3'],
                fontSize=12, textColor=colors.HexColor('#333333'),
                spaceAfter=6, fontName=_KOREAN_FONT,
            )
            elements.append(Paragraph("Candidate Compounds", sub_style))

            header = ["Rank", "Name", "QED", "Composite", "Tier", "Oral BA"]
            rows = [header]
            for hit in hits[:25]:  # Limit to 25 entries for readability
                if not isinstance(hit, dict):
                    continue
                rows.append([
                    str(hit.get("rank", "")),
                    str(hit.get("name", hit.get("smiles", "")[:20])),
                    str(hit.get("qed", "N/A")),
                    str(hit.get("composite_score", "N/A")),
                    str(hit.get("tier", "N/A")),
                    str(hit.get("oral_bioavailability", "N/A")),
                ])

            col_widths = [1.5 * cm, 5 * cm, 2 * cm, 2.5 * cm, 1.5 * cm, 3 * cm]
            hit_table = Table(rows, colWidths=col_widths)
            # Color tier cells
            table_styles = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, -1), _KOREAN_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                 [colors.white, colors.HexColor('#f5f5f5')]),
            ]
            # Highlight tier A rows in green, tier C in red
            for i, hit in enumerate(hits[:25], start=1):
                if not isinstance(hit, dict):
                    continue
                tier = hit.get("tier", "")
                if tier == "A":
                    table_styles.append(
                        ('BACKGROUND', (4, i), (4, i), colors.HexColor('#c8e6c9')))
                elif tier == "C":
                    table_styles.append(
                        ('BACKGROUND', (4, i), (4, i), colors.HexColor('#ffcdd2')))
            hit_table.setStyle(TableStyle(table_styles))
            elements.append(hit_table)
        else:
            elements.append(Paragraph("No hit compounds identified.", normal_style))

        # -- Description / Error --
        if result.get("error"):
            err_style = ParagraphStyle(
                'DSError', parent=styles['Normal'],
                fontSize=9, textColor=colors.HexColor('#cc3300'),
                fontName=_KOREAN_FONT, spaceBefore=8,
            )
            elements.append(Paragraph(f"Error: {result['error']}", err_style))

        if page_data.description:
            desc_style = ParagraphStyle(
                'DSDesc', parent=styles['Normal'],
                fontSize=9, textColor=colors.HexColor('#555555'),
                fontName=_KOREAN_FONT, spaceBefore=10,
            )
            elements.append(Paragraph(page_data.description, desc_style))

        return elements

    def _rl_placeholder_page(self, page_key: str) -> List:
        """Build a placeholder page for unavailable data."""
        elements = []
        styles = getSampleStyleSheet()

        titles = {
            "ir": "IR Spectrum",
            "nmr": "\u00b9H NMR Spectrum",
            "nmr_c13": "\u00b9\u00b3C NMR Spectrum",
            "uvvis": "UV-Vis Spectrum",
            "mass": "Mass Spectrum (EI-MS)",
            "structure_3d": "3D Optimized Structure",
            "reaction": "Reaction Mechanism",
            "admet": "ADMET Analysis",
            "drug_screening": "Drug Screening Results",
        }
        assert isinstance(titles, dict)  # Rule N: 타입 가드
        title = titles.get(page_key, page_key.replace("_", " ").title())

        title_style = ParagraphStyle(
            'PlaceholderTitle', parent=styles['Heading2'],
            fontSize=16, textColor=colors.HexColor('#999999'),
            spaceAfter=20, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 1 * inch))

        note_style = ParagraphStyle(
            'PlaceholderNote', parent=styles['Normal'],
            fontSize=12, textColor=colors.HexColor('#aaaaaa'),
            alignment=TA_CENTER, fontName=_KOREAN_FONT,
        )
        elements.append(Paragraph(
            "Data not available for this section.<br/>"
            "Run the corresponding analysis to populate this page.",
            note_style,
        ))

        return elements

    def _export_pdf_qprinter(self, output_path: str) -> bool:
        """Fallback: generate a basic multi-page PDF using QPrinter."""
        if not PYQT_AVAILABLE:
            return False
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(output_path)
            printer.setPageSize(QPrinter.PageSize.A4)

            painter = QPainter(printer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            font = QFont("Arial", 14)
            painter.setFont(font)

            page_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            margin = 100
            y_pos = margin
            first_page = True

            page_order = ["structure_2d", "ir", "nmr", "uvvis", "structure_3d", "reaction",
                          "admet", "drug_screening"]
            for page_key in page_order:
                if not first_page:
                    printer.newPage()
                first_page = False

                y_pos = margin
                assert isinstance(self.pages, dict)  # Rule N: 타입 가드
                page_data = self.pages.get(page_key)

                # Title
                painter.setFont(QFont("Arial", 16))
                painter.setPen(QPen(QColor(0, 102, 204)))
                title = page_data.page_title if page_data else page_key.replace("_", " ").title()
                painter.drawText(margin, y_pos, title)
                y_pos += 60

                # Image
                if page_data and page_data.image_path and os.path.exists(page_data.image_path):
                    img = QImage(page_data.image_path)
                    if not img.isNull():
                        max_w = page_rect.width() - 2 * margin
                        max_h = page_rect.height() // 2
                        scaled = img.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
                        painter.drawImage(margin, y_pos, scaled)
                        y_pos += scaled.height() + 30

                # Description
                painter.setFont(QFont("Arial", 10))
                painter.setPen(QPen(QColor(80, 80, 80)))
                desc = page_data.description if page_data and page_data.description else "No data available"
                painter.drawText(margin, y_pos, page_rect.width() - 2 * margin, 200,
                                 Qt.TextFlag.TextWordWrap, desc)

            painter.end()
            logger.info("QPrinter PDF exported: %s", output_path)
            return True
        except Exception as e:
            logger.error("QPrinter PDF export failed: %s", e)
            return False

    def cleanup_temp_files(self):
        """Remove temporary capture files."""
        for fp in self._temp_files:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError as e:
                logger.warning("Failed to remove temp file %s: %s", fp, e)
        self._temp_files.clear()


# ============================================================================
# EXISTING CLASSES (preserved from v2.0)
# ============================================================================

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

        if not isinstance(settings, dict):
            logger.warning("export_selection: settings is not dict (type=%s)", type(settings).__name__)
            settings = {"format": "PNG", "dpi": 300}
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
        if not isinstance(settings, dict):
            settings = {}
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
        # Paint bonds first (background)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        for bond_key, bond_info in self.selected_bonds:
            if bond_key in self.canvas.bonds:
                pos1, pos2 = bond_key
                painter.drawLine(
                    int(pos1[0]), int(pos1[1]),
                    int(pos2[0]), int(pos2[1])
                )

        # Paint atoms (foreground)
        for atom_pos in self.selected_atoms:
            if atom_pos in self.canvas.atoms:
                atom_data = self.canvas.atoms[atom_pos]
                if not isinstance(atom_data, dict):
                    atom_data = {}
                element = atom_data.get("element", "C")

                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.setBrush(QBrush(QColor(200, 200, 200)))
                painter.drawEllipse(int(atom_pos[0] - 10), int(atom_pos[1] - 10), 20, 20)

                painter.drawText(int(atom_pos[0] - 5), int(atom_pos[1] + 5), element)

    def _embed_metadata_png(self, image_path: str, settings: Dict):
        """Embed EXIF metadata into PNG file"""
        if not isinstance(settings, dict) or not settings.get("add_metadata", False):
            return

        try:
            metadata = ExportMetadata(
                title=Path(image_path).stem,
                layer_type=self.layer_type,
                molecule_count=len(self.selected_atoms),
                has_selection=True,
                export_format="PNG",
                dpi=settings.get("dpi", 300)
            )

            meta_file = Path(image_path).with_stem(Path(image_path).stem + "_metadata")
            with open(str(meta_file.with_suffix(".json")), 'w') as f:
                json.dump(asdict(metadata), f, indent=2)

        except Exception as e:
            logger.warning("Could not embed metadata: %s", e)


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

    def export_integrated_pdf(self):
        """
        Export a comprehensive 6-page PDF report.
        Captures Lewis & Theory views, collects spectrum data if available.
        """
        if not self.canvas:
            QMessageBox.warning(self.main_window, "Error", "Canvas not found")
            return

        try:
            # Gather molecule info
            mol_name = getattr(self.canvas, 'selected_molecule_name', '') or 'Unknown Molecule'
            ar = getattr(self.canvas, 'analysis_results', None) or {}
            if isinstance(ar, dict) and ar.get('identified_name'):
                mol_name = ar['identified_name']

            smiles = _safe_get_smiles(self.canvas)
            formula = ar.get('molecular_formula', '') if isinstance(ar, dict) else ''

            # Compute formula from RDKit if not available from analysis_results
            if not formula and smiles:
                try:
                    from rdkit import Chem
                    from rdkit.Chem import rdMolDescriptors
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is not None:  # Rule L: None guard
                        formula = rdMolDescriptors.CalcMolFormula(mol)
                except Exception as e:
                    logger.warning("Module import failed: %s", e)

            exporter = IntegratedPDFExporter(
                molecule_name=mol_name,
                smiles=smiles,
                molecular_formula=formula,
            )

            # Page 1: 2D Lewis structure
            lewis_img = exporter.capture_canvas_state(self.canvas, "Lewis")
            if lewis_img:
                exporter.set_2d_structure(lewis_img,
                    f"Lewis structure of {mol_name}. Shows valence electrons and bonding connectivity.")

            # Pages 2-5: Spectra generated from SMILES (IR, 1H NMR, 13C NMR, UV-Vis, Mass)
            self._collect_spectrum_data(exporter)

            # Page 7: ADMET analysis
            self._collect_admet_data(exporter, smiles, mol_name)

            # Page 8: Drug screening results
            self._collect_drug_screening_data(exporter)

            # Ask for save path
            default_name = f"{mol_name.replace(' ', '_')}_report.pdf"
            default_path = os.path.join(os.path.expanduser("~"), "Desktop", default_name)
            file_path, _ = QFileDialog.getSaveFileName(
                self.main_window,
                "Export Integrated PDF Report",
                default_path,
                "PDF Files (*.pdf)"
            )

            if not file_path:
                exporter.cleanup_temp_files()
                return

            success = exporter.export_pdf(file_path)
            exporter.cleanup_temp_files()

            if success:
                QMessageBox.information(self.main_window, "Success",
                    f"8-page integrated PDF exported to:\n{file_path}")
            else:
                QMessageBox.critical(self.main_window, "Export Error",
                    "Failed to generate PDF. Check logs for details.")

        except Exception as e:
            logger.error("Integrated PDF export failed: %s", e)
            QMessageBox.critical(self.main_window, "Export Error",
                               f"Failed to export integrated PDF:\n{str(e)}")

    def _save_figure_to_temp(self, fig, prefix: str) -> Optional[str]:
        """Save a matplotlib Figure to a temporary PNG file for PDF embedding.

        Rule Q: Ensures Korean font (Malgun Gothic / NanumGothic) is registered
        with matplotlib before saving, so axis labels and annotations render
        correctly in the exported PDF images.
        """
        try:
            # Rule Q: ensure matplotlib Korean font is set before saving
            try:
                import matplotlib
                import matplotlib.font_manager as fm
                _kr_paths = [
                    'C:/Windows/Fonts/malgun.ttf',
                    'C:/Windows/Fonts/NanumGothic.ttf',
                ]
                # Rule N: isinstance guard for rcParams
                if not isinstance(rcParams, dict): rcParams = {}
                if 'Malgun' not in matplotlib.rcParams.get('font.family', ''):
                    for _fp in _kr_paths:
                        if os.path.exists(_fp):
                            _kr_fp = fm.FontProperties(fname=_fp)
                            matplotlib.rcParams['font.family'] = _kr_fp.get_name()
                            matplotlib.rcParams['axes.unicode_minus'] = False
                            break
            except Exception as e:
                logger.debug("matplotlib Korean font setup skipped: %s", e)

            tmp_path = os.path.join(
                tempfile.gettempdir(),
                f"chemgrid_{prefix}_{os.getpid()}_{id(fig)}.png"
            )
            # Use a wide figure for full-width PDF embedding
            fig.set_size_inches(10.0, 4.0)
            fig.set_dpi(200)
            fig.tight_layout()
            fig.savefig(tmp_path, dpi=200, bbox_inches='tight',
                        facecolor=fig.get_facecolor(), edgecolor='none')
            return tmp_path
        except Exception as e:
            logger.warning("Failed to save figure %s: %s", prefix, e)
            return None

    def _collect_spectrum_data(self, exporter: IntegratedPDFExporter):
        """Generate spectrum data and images directly from SMILES.

        Uses predict_spectra.predict_all() and popup_predicted_spectrum figure
        generators to create full-width spectrum images for the PDF report.
        Falls back to popup window data if available.
        """
        smiles = exporter.smiles
        if not smiles:
            logger.info("No SMILES available for spectrum generation")
            return

        # Try to generate spectra from SMILES using predict_all
        try:
            import sys as _sys
            _src_dir = os.path.dirname(os.path.abspath(__file__))
            if _src_dir not in _sys.path:
                _sys.path.insert(0, _src_dir)
            from predict_spectra import predict_all
            from popup_predicted_spectrum import (
                _make_ir_figure, _make_raman_figure,
                _make_nmr_h1_figure, _make_nmr_c13_figure,
                _make_uvvis_figure,
            )
        except ImportError as e:
            logger.warning("Cannot import spectrum modules: %s", e)
            return

        try:
            spec = predict_all(smiles)
        except Exception as e:
            logger.warning("predict_all failed for '%s': %s", smiles[:30], e)
            return

        # -- IR Spectrum (Page 2) --
        try:
            if spec.ir_peaks:
                fig = _make_ir_figure(spec.ir_peaks)
                img_path = self._save_figure_to_temp(fig, "ir")
                if img_path:
                    exporter._temp_files.append(img_path)
                ir_peaks = []
                for p in spec.ir_peaks:
                    ir_peaks.append({
                        "frequency": f"{p.wavenumber:.0f} cm\u207b\u00b9",
                        "intensity": f"{100.0 - p.transmittance:.1f}%",
                        "assignment": p.assignment,
                    })
                exporter.set_ir_spectrum(image_path=img_path, peaks=ir_peaks)
                try:
                    import matplotlib.pyplot as plt
                    plt.close(fig)
                except Exception as e:
                    logger.warning("Figure save failed: %s", e)
        except Exception as e:
            logger.warning("IR spectrum generation failed: %s", e)

        # -- 1H NMR Spectrum (Page 3) --
        try:
            if spec.h1_nmr_peaks:
                fig = _make_nmr_h1_figure(spec.h1_nmr_peaks, spec.formula, smiles=smiles)
                img_path = self._save_figure_to_temp(fig, "nmr_h1")
                if img_path:
                    exporter._temp_files.append(img_path)
                nmr_peaks = []
                for p in spec.h1_nmr_peaks:
                    nmr_peaks.append({
                        "frequency": f"\u03b4 {p.shift:.2f} ppm",
                        "intensity": f"{p.integration:.1f}H, {p.multiplicity}",
                        "assignment": p.assignment,
                    })
                exporter.set_nmr_spectrum(image_path=img_path, peaks=nmr_peaks,
                                          nmr_type="1H")
                try:
                    import matplotlib.pyplot as plt
                    plt.close(fig)
                except Exception as e:
                    logger.warning("Figure save failed: %s", e)
        except Exception as e:
            logger.warning("1H NMR spectrum generation failed: %s", e)

        # -- 13C NMR Spectrum (Page 4) --
        try:
            if spec.c13_peaks:
                fig = _make_nmr_c13_figure(spec.c13_peaks, spec.formula, smiles=smiles)
                img_path = self._save_figure_to_temp(fig, "nmr_c13")
                if img_path:
                    exporter._temp_files.append(img_path)
                c13_peaks = []
                for p in spec.c13_peaks:
                    c13_peaks.append({
                        "frequency": f"\u03b4 {p.shift:.1f} ppm",
                        "intensity": p.carbon_type,
                        "assignment": f"{p.assignment} ({p.zone})",
                    })
                exporter.set_nmr_c13_spectrum(image_path=img_path, peaks=c13_peaks)
                try:
                    import matplotlib.pyplot as plt
                    plt.close(fig)
                except Exception as e:
                    logger.warning("Figure save failed: %s", e)
        except Exception as e:
            logger.warning("13C NMR spectrum generation failed: %s", e)

        # -- UV-Vis Spectrum (Page 5) --
        try:
            if spec.uvvis_peaks:
                fig = _make_uvvis_figure(spec.uvvis_peaks)
                img_path = self._save_figure_to_temp(fig, "uvvis")
                if img_path:
                    exporter._temp_files.append(img_path)
                uvvis_peaks = []
                for p in spec.uvvis_peaks:
                    uvvis_peaks.append({
                        "frequency": f"\u03bbmax = {p.wavelength:.0f} nm",
                        "intensity": f"\u03b5 = {p.epsilon:.0f} L\u00b7mol\u207b\u00b9\u00b7cm\u207b\u00b9",
                        "assignment": f"{p.transition_type}: {p.assignment}",
                    })
                exporter.set_uvvis_spectrum(image_path=img_path, peaks=uvvis_peaks)
                try:
                    import matplotlib.pyplot as plt
                    plt.close(fig)
                except Exception as e:
                    logger.warning("Figure save failed: %s", e)
        except Exception as e:
            logger.warning("UV-Vis spectrum generation failed: %s", e)

        # -- Mass Spectrum (Page 6) — generate basic EI-MS from MW --
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:  # Rule L: None guard
                mw = Descriptors.ExactMolWt(mol)
                mass_peaks = [
                    {"frequency": f"m/z = {mw:.1f}", "intensity": "100% (M\u207a)",
                     "assignment": "Molecular ion peak"},
                ]
                # Common fragmentation losses
                common_losses = [
                    (15, "CH\u2083 loss (M-15)"), (17, "OH loss (M-17)"),
                    (18, "H\u2082O loss (M-18)"), (28, "CO loss (M-28)"),
                    (29, "CHO loss (M-29)"), (31, "OCH\u2083 loss (M-31)"),
                    (44, "CO\u2082 loss (M-44)"), (45, "OEt loss (M-45)"),
                ]
                for loss, label in common_losses:
                    if mw - loss > 10:
                        mass_peaks.append({
                            "frequency": f"m/z = {mw - loss:.1f}",
                            "intensity": f"~{max(5, 80 - loss):.0f}%",
                            "assignment": label,
                        })
                exporter.set_mass_spectrum(peaks=mass_peaks,
                    description=f"Predicted EI-MS fragmentation of {exporter.molecule_name} "
                                f"(MW = {mw:.4f} g/mol). M\u207a at m/z {mw:.1f}.")
        except Exception as e:
            logger.warning("Mass spectrum generation failed: %s", e)

    def _collect_reaction_data(self, exporter: IntegratedPDFExporter):
        """Collect reaction mechanism data if available."""
        mw = self.main_window
        reaction_popup = getattr(mw, 'reaction_popup', None)
        if reaction_popup:
            img_path = getattr(reaction_popup, 'last_image_path', None)
            desc = getattr(reaction_popup, 'reaction_description', "Reaction mechanism")
            exporter.set_reaction_mechanism(image_path=img_path, description=desc)

    def _collect_admet_data(self, exporter: IntegratedPDFExporter,
                            smiles: str, mol_name: str):
        """
        Collect ADMET prediction data for page 7.

        Attempts to use admet_predictor.predict_admet() with the current molecule's
        SMILES. Falls back gracefully if admet_predictor is not available or SMILES
        is empty.
        """
        try:
            if not smiles:
                logger.info("No SMILES available for ADMET prediction")
                exporter.set_admet_data(None)
                return

            # Try importing admet_predictor
            try:
                from admet_predictor import predict_admet, admet_to_dict
            except ImportError:
                logger.info("admet_predictor not available, skipping ADMET page")
                exporter.set_admet_data(None)
                return

            profile = predict_admet(smiles, mol_name=mol_name)
            profile_dict = admet_to_dict(profile)
            exporter.set_admet_data(profile_dict)

        except Exception as e:
            logger.warning("ADMET data collection failed: %s", e)
            exporter.set_admet_data(None)

    def _collect_drug_screening_data(self, exporter: IntegratedPDFExporter):
        """
        Collect drug screening results for page 8.

        Looks for screening results stored on main_window (e.g., from a previous
        screening run). Falls back gracefully if no data is available.
        """
        try:
            mw = self.main_window

            # Check for screening result on main_window or canvas
            screening_result = (
                getattr(mw, 'last_screening_result', None)
                or getattr(mw, 'screening_result', None)
            )

            if screening_result is not None:
                # If it's a ScreeningResult dataclass, convert to dict
                try:
                    from drug_screening import screening_result_to_dict, ScreeningResult
                    if isinstance(screening_result, ScreeningResult):
                        screening_result = screening_result_to_dict(screening_result)
                except ImportError as e:
                    logger.debug("Optional module import failed: %s", e)

                if isinstance(screening_result, dict):
                    exporter.set_drug_screening_data(screening_result)
                    return

            # No pre-existing screening data found
            logger.info("No drug screening result available for PDF page 8")
            exporter.set_drug_screening_data(None)

        except Exception as e:
            logger.warning("Drug screening data collection failed: %s", e)
            exporter.set_drug_screening_data(None)
