
try:
    import sys
    import os
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing ReportLab PDF Generation with Vector Graphics...")
    
    # Import modified exporter
    try:
        from agents.09_data_export.spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData
    except ImportError:
        pass
        # Fallback for running from root
        # sys.path.append(os.getcwd())
        # from agents.09_data_export.spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData
    
    # Mock Data
    metadata = SpectrumMetadata(
        molecule_name="Vector Test Molecule",
        molecular_formula="C2H6O",
        smiles="CCO",
        final_energy=-154.0
    )
    
    exporter = SpectrumPDFExporter(metadata)
    
    # 1. IR
    ir_peaks = [
        SpectrumPeakData(frequency=3350, intensity=20, label="O-H str", width=150),
        SpectrumPeakData(frequency=2980, intensity=10, label="C-H str", width=50),
        SpectrumPeakData(frequency=1050, intensity=15, label="C-O str", width=40),
        SpectrumPeakData(frequency=1450, intensity=40, label="C-H bend", width=30)
    ]
    ir_data = SpectrumData("IR", ir_peaks, ai_analysis="ReportLab vector graphic test.")
    exporter.add_spectrum("IR", ir_data)
    
    # 2. H1 NMR
    nmr_h1_peaks = [
        SpectrumPeakData(frequency=1.2, intensity=3.0, multiplicity='t', integral=3.0, assignment="CH3"),
        SpectrumPeakData(frequency=3.7, intensity=2.0, multiplicity='q', integral=2.0, assignment="CH2"),
        SpectrumPeakData(frequency=2.6, intensity=1.0, multiplicity='s', integral=1.0, assignment="OH")
    ]
    nmr_h1_data = SpectrumData("NMR_H1", nmr_h1_peaks, ai_analysis="Clean vector lines.")
    exporter.add_spectrum("NMR_H1", nmr_h1_data)
    
    # 3. UV-Vis
    uv_peaks = [
        SpectrumPeakData(frequency=210, intensity=0.8, width=20, assignment="pi->pi*"),
        SpectrumPeakData(frequency=280, intensity=0.1, width=30, assignment="n->pi*")
    ]
    uv_data = SpectrumData("UV_Vis", uv_peaks, ai_analysis="Smooth curves.")
    exporter.add_spectrum("UV_Vis", uv_data)
    
    # Export
    output_pdf = "vector_spectrum_report.pdf"
    exporter.export_to_pdf(output_pdf)
    print(f"Exported to {output_pdf}")
    
    if os.path.exists(output_pdf):
        print("SUCCESS: PDF created.")
    else:
        print("FAILURE: PDF not found.")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
