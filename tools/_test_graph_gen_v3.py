
import sys
import os

# Add the project root to the python path
sys.path.append(os.getcwd())

from agents.09_data_export.spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData, GraphGenerator
from datetime import datetime

# Redirect stderr to stdout to see errors
sys.stderr = sys.stdout

print("Starting debug test...", flush=True)

try:
    # Mock Data
    metadata = SpectrumMetadata(
        molecule_name="Test Molecule (Ethanol)",
        molecular_formula="C2H6O",
        smiles="CCO",
        final_energy=-154.0
    )

    print("Initializing exporter...", flush=True)
    exporter = SpectrumPDFExporter(metadata)

    # 1. IR Test Data (Ethanol features)
    print("Generating IR...", flush=True)
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
    print(f"IR Image Path: {ir_data.image_path}", flush=True)

    # Export
    output_pdf = "test_spectrum_report_v2.pdf"
    print(f"Exporting PDF to {output_pdf}...", flush=True)
    exporter.export_to_pdf(output_pdf)
    print(f"Exported to {output_pdf}", flush=True)

except Exception as e:
    print(f"An error occurred: {e}", flush=True)
    import traceback
    traceback.print_exc()
