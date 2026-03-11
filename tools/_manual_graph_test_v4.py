
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
    
    # Manually call graph generator
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    
    print("Matplotlib loaded.")
    
    peaks = [
        exporter_module.SpectrumPeakData(frequency=3350, intensity=20, label="O-H str", width=150),
        exporter_module.SpectrumPeakData(frequency=2980, intensity=10, label="C-H str", width=50),
        exporter_module.SpectrumPeakData(frequency=1050, intensity=15, label="C-O str", width=40)
    ]
    
    # Create temp directory
    temp_dir = "temp_spectra_images"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created directory: {temp_dir}")
    
    output_path = os.path.join(temp_dir, "manual_ir_test.png")
    print(f"Generating graph to {output_path}...")
    
    success = exporter_module.GraphGenerator.generate_graph("IR", peaks, output_path)
    
    if success:
        print("Graph generation SUCCESS")
        print(f"File created at: {os.path.abspath(output_path)}")
    else:
        print("Graph generation FAILED")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
