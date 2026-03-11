
try:
    import sys
    import os
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing imports...", flush=True)
    
    # Try imports
    try:
        import matplotlib.pyplot as plt
        print("Matplotlib OK", flush=True)
    except ImportError:
        print("Matplotlib MISSING", flush=True)
        
    try:
        from reportlab.pdfgen import canvas
        print("ReportLab OK", flush=True)
    except ImportError:
        print("ReportLab MISSING", flush=True)

    try:
        import agents.09_data_export.spectrum_pdf_exporter as spe
        print("SpectrumPDFExporter Import OK", flush=True)
    except ImportError as e:
        print(f"SpectrumPDFExporter Import FAILED: {e}", flush=True)
        
except Exception as e:
    print(f"Top level error: {e}", flush=True)
