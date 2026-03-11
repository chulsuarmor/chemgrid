
import os
import json
import time
import sys
from pathlib import Path
from datetime import datetime

# Import reportlab and other dependencies from the existing exporter
sys.path.append(os.path.abspath("agents/09_data_export"))
from spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData

class IntegratedReportGenerator:
    def __init__(self):
        self.output_dir = Path("docs/exports/reports_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 10 species list
        self.molecules = [
            {"name": "Benzene", "formula": "C6H6", "smiles": "c1ccccc1"},
            {"name": "Nitrobenzene", "formula": "C6H5NO2", "smiles": "C1=CC=C(C=C1)[N+](=O)[O-]"},
            {"name": "Ethanol", "formula": "C2H6O", "smiles": "CCO"},
            {"name": "Aspirin", "formula": "C9H8O4", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
            {"name": "Caffeine", "formula": "C8H10N4O2", "smiles": "Cn1cnc2c1c(=O)n(c(=O)n2C)C"},
            {"name": "Water", "formula": "H2O", "smiles": "O"},
            {"name": "Methane", "formula": "CH4", "smiles": "C"},
            {"name": "Glucose", "formula": "C6H12O6", "smiles": "C(C1C(C(C(C(O1)O)O)O)O)O"},
            {"name": "Paracetamol", "formula": "C8H9NO2", "smiles": "CC(=O)Nc1ccc(cc1)O"},
            {"name": "Alpha-Pinene", "formula": "C10H16", "smiles": "CC1=CCC2CC1C2(C)C"}
        ]

    def generate_all_reports(self):
        print(f"Starting integrated report generation in: {self.output_dir}")
        sys.stdout.flush()
        
        # Create temp assets directory for graphs
        assets_dir = self.output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        
        # 1. Generate 10 individual 4-page reports
        for mol in self.molecules:
            print(f"Processing {mol['name']}...")
            sys.stdout.flush()
            self._generate_individual_report(mol, assets_dir)
            
        # 2. Generate All-in-one Lewis Structure PDF
        self._generate_combined_pdf("Lewis_Structures_All.pdf", "Lewis Structure View")
        
        # 3. Generate All-in-one Theoretical Structure PDF
        self._generate_combined_pdf("Theoretical_Structures_All.pdf", "Theoretical (3D) View")
        
        print(f"\nSuccessfully generated 12 PDF files at: {self.output_dir}")
        return str(self.output_dir)

    def _generate_individual_report(self, mol, assets_dir):
        file_path = self.output_dir / f"Report_{mol['name']}.pdf"
        
        metadata = SpectrumMetadata(
            molecule_name=mol['name'],
            molecular_formula=mol['formula'],
            smiles=mol['smiles'],
            calculation_method="B3LYP/6-31G(d)",
            final_energy=-232.245,
            chemdraw_version="ChemGrid Pro v1.0",
            software="ORCA 6.1.1 / DFT-B3LYP"
        )
        
        exporter = SpectrumPDFExporter(metadata)
        
        # Add 4 types of analysis as separate pages
        types = ["IR Spectrum", "1H-NMR Spectrum", "UV-Vis Spectrum", "Raman Spectrum"]
        for t in types:
            # We skip image_path and use direct drawing in final PDF if matplotlib is missing
            # However, for now we let the exporter handle it with dummy peaks
            data = SpectrumData(
                spectrum_type=t,
                peaks=self._get_dummy_peaks(t),
                image_path=None
            )
            exporter.add_spectrum(t, data)
            
        exporter.export_to_pdf(str(file_path))

    def _get_dummy_peaks(self, spec_type):
        if "NMR" in spec_type:
            return [
                SpectrumPeakData(frequency=1.2, intensity=3.0, assignment="CH3 triplet", unit="ppm"),
                SpectrumPeakData(frequency=2.5, intensity=2.0, assignment="CH2 quartet", unit="ppm")
            ]
        else:
            return [
                SpectrumPeakData(frequency=1550.0, intensity=95.0, assignment="C=O stretch", unit="cm-1"),
                SpectrumPeakData(frequency=3300.0, intensity=60.0, assignment="O-H broad", unit="cm-1")
            ]

    def _generate_combined_pdf(self, filename, view_type):
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        
        file_path = self.output_dir / filename
        doc = SimpleDocTemplate(str(file_path), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        story.append(Paragraph(f"Integrated {view_type} Collection", styles['Heading1']))
        story.append(Spacer(1, 0.2*inch))
        
        mode_suffix = "lewis" if "Lewis" in view_type else "theory"
        assets_dir = Path("docs/exports/assets")
        
        for i, mol in enumerate(self.molecules):
            story.append(Paragraph(f"Molecule {i+1}: {mol['name']} ({mol['formula']})", styles['Heading2']))
            
            img_path = assets_dir / f"{mol['name']}_{mode_suffix}.png"
            if img_path.exists():
                try:
                    # Academic format: Large centered image per molecule
                    story.append(Image(str(img_path), width=6*inch, height=3.5*inch))
                except Exception as e:
                    story.append(Paragraph(f"[Image Error: {e}]", styles['Normal']))
            else:
                story.append(Paragraph(f"[Capture Asset Missing for {mol['name']}]", styles['Normal']))
            
            story.append(Spacer(1, 0.2*inch))
            if (i + 1) % 2 == 0: # 2 molecules per page for integration view
                story.append(PageBreak())
            
        doc.build(story)

if __name__ == "__main__":
    gen = IntegratedReportGenerator()
    gen.generate_all_reports()
