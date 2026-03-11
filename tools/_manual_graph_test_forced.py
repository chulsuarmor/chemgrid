
try:
    import sys
    import os
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing Graph Generation with direct matplotlib usage...")
    
    # Manually import by file path to avoid package issues
    import importlib.util
    spec = importlib.util.spec_from_file_location("spectrum_pdf_exporter", "agents/09_data_export/spectrum_pdf_exporter.py")
    exporter_module = importlib.util.module_from_spec(spec)
    sys.modules["spectrum_pdf_exporter"] = exporter_module
    spec.loader.exec_module(exporter_module)
    
    # Override MATPLOTLIB_AVAILABLE to force check
    print(f"MATPLOTLIB_AVAILABLE: {exporter_module.MATPLOTLIB_AVAILABLE}")
    
    if not exporter_module.MATPLOTLIB_AVAILABLE:
        print("Forcing MATPLOTLIB_AVAILABLE = True")
        exporter_module.MATPLOTLIB_AVAILABLE = True
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        import numpy as np
    
    peaks = [
        exporter_module.SpectrumPeakData(frequency=3350, intensity=20, label="O-H str", width=150),
        exporter_module.SpectrumPeakData(frequency=2980, intensity=10, label="C-H str", width=50),
        exporter_module.SpectrumPeakData(frequency=1050, intensity=15, label="C-O str", width=40)
    ]
    
    output_path = os.path.abspath("manual_ir_test_forced.png")
    print(f"Generating graph to {output_path}...")
    
    # Direct call to internal logic if generate_graph fails silently
    try:
        success = exporter_module.GraphGenerator.generate_graph("IR", peaks, output_path)
        print(f"generate_graph returned: {success}")
    except Exception as e:
        print(f"generate_graph crashed: {e}")
        import traceback
        traceback.print_exc()
    
    if os.path.exists(output_path):
        print(f"File verified at: {output_path}")
    else:
        print("File MISSING after attempt")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
