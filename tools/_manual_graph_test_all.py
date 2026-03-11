
try:
    import sys
    import os
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    # Manually import by file path to avoid package issues
    import importlib.util
    spec = importlib.util.spec_from_file_location("spectrum_pdf_exporter", "agents/09_data_export/spectrum_pdf_exporter.py")
    exporter_module = importlib.util.module_from_spec(spec)
    sys.modules["spectrum_pdf_exporter"] = exporter_module
    spec.loader.exec_module(exporter_module)
    
    print("Module loaded.")
    
    peaks = [
        exporter_module.SpectrumPeakData(frequency=3350, intensity=20, label="O-H str", width=150),
        exporter_module.SpectrumPeakData(frequency=2980, intensity=10, label="C-H str", width=50),
        exporter_module.SpectrumPeakData(frequency=1050, intensity=15, label="C-O str", width=40)
    ]
    
    # Generate all types
    types = ["IR", "NMR_H1", "NMR_C13", "UV_Vis"]
    
    for t in types:
        output_path = f"manual_{t}_test.png"
        print(f"Generating {t} graph to {output_path}...")
        success = exporter_module.GraphGenerator.generate_graph(t, peaks, output_path)
        if success:
            print(f"{t} Graph generation SUCCESS")
        else:
            print(f"{t} Graph generation FAILED")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
