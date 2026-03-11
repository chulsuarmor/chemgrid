
try:
    import sys
    import os
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    # Minimal script to bypass import issues
    from agents.09_data_export import spectrum_pdf_exporter as exporter_module
    
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
    
    output_path = "manual_ir_test.png"
    print(f"Generating graph to {output_path}...")
    
    success = exporter_module.GraphGenerator.generate_graph("IR", peaks, output_path)
    
    if success:
        print("Graph generation SUCCESS")
    else:
        print("Graph generation FAILED")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
