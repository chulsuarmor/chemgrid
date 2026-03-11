
import sys
import os

# Add the project root to the python path
sys.path.append(os.getcwd())

from agents.09_data_export.spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData, GraphGenerator
from datetime import datetime

print("Testing SpectrumPDFExporter with Graph Generation...")

# Mock Data
metadata = SpectrumMetadata(
    molecule_name="Test Molecule (Ethanol)",
    molecular_formula="C2H6O",
    smiles="CCO",
    final_energy=-154.0
)

# Initialize exporter without cleaning up temp files immediately to inspect them
exporter = SpectrumPDFExporter(metadata)

# 1. IR Test Data (Ethanol features)
ir_peaks = [
    SpectrumPeakData(frequency=3350, intensity=20, label="O-H str", width=150),
    SpectrumPeakData(frequency=2980, intensity=10, label="C-H str", width=50),
    SpectrumPeakData(frequency=1050, intensity=15, label="C-O str", width=40),
    SpectrumPeakData(frequency=1450, intensity=40, label="C-H bend", width=30)
]
ir_data = SpectrumData(
    spectrum_type="IR",
    peaks=ir_peaks,
    ai_analysis="Broad peak at 3350 cm-1 indicates O-H stretching. Strong peak at 1050 cm-1 confirms C-O bond."
)
exporter.add_spectrum("IR", ir_data)
print(f"IR Image Path: {ir_data.image_path}")

# 2. H1 NMR Test Data (Ethanol: CH3-CH2-OH)
nmr_h1_peaks = [
    SpectrumPeakData(frequency=1.2, intensity=3.0, multiplicity='t', integral=3.0, assignment="CH3"),
    SpectrumPeakData(frequency=3.7, intensity=2.0, multiplicity='q', integral=2.0, assignment="CH2"),
    SpectrumPeakData(frequency=2.6, intensity=1.0, multiplicity='s', integral=1.0, assignment="OH")
]
nmr_h1_data = SpectrumData(
    spectrum_type="NMR_H1",
    peaks=nmr_h1_peaks,
    ai_analysis="Triplet at 1.2 ppm (3H) and Quartet at 3.7 ppm (2H) confirms ethyl group structure."
)
exporter.add_spectrum("NMR_H1", nmr_h1_data)
print(f"NMR H1 Image Path: {nmr_h1_data.image_path}")

# 3. C13 NMR Test Data (Ethanol)
nmr_c13_peaks = [
    SpectrumPeakData(frequency=18.4, intensity=1.0, multiplicity='s', assignment="CH3"),
    SpectrumPeakData(frequency=58.2, intensity=0.9, multiplicity='s', assignment="CH2")
]
nmr_c13_data = SpectrumData(
    spectrum_type="NMR_C13",
    peaks=nmr_c13_peaks,
    ai_analysis="Two signals at 18.4 and 58.2 ppm correspond to methyl and methylene carbons respectively."
)
exporter.add_spectrum("NMR_C13", nmr_c13_data)
print(f"NMR C13 Image Path: {nmr_c13_data.image_path}")

# 4. UV-Vis Test Data (Mock)
uv_peaks = [
    SpectrumPeakData(frequency=210, intensity=0.8, width=20, assignment="pi->pi*"),
    SpectrumPeakData(frequency=280, intensity=0.1, width=30, assignment="n->pi*")
]
uv_data = SpectrumData(
    spectrum_type="UV_Vis",
    peaks=uv_peaks,
    ai_analysis="Strong absorption at 210nm suggests pi-pi* transition."
)
exporter.add_spectrum("UV_Vis", uv_data)
print(f"UV-Vis Image Path: {uv_data.image_path}")

# Export
output_pdf = "test_spectrum_report_v2.pdf"
exporter.export_to_pdf(output_pdf)
print(f"Exported to {output_pdf}")
