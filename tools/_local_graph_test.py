
try:
    import sys
    import os
    import importlib.util
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing Graph Generation with absolute minimal dependency...")
    
    # 1. Define classes locally to avoid imports
    from dataclasses import dataclass
    from typing import List, Dict
    
    @dataclass
    class SpectrumPeakData:
        frequency: float
        intensity: float
        label: str = ""
        width: float = 1.0
        multiplicity: str = 's'
        integral: float = 1.0
        assignment: str = ""
        unit: str = "cm⁻¹"

    # 2. Define Generator locally
    import matplotlib.pyplot as plt
    import numpy as np
    
    def generate_ir_graph(peaks, output_path):
        fig = plt.figure(figsize=(10, 6), dpi=300)
        ax = fig.add_subplot(111)
        
        # IR Logic
        x = np.linspace(400, 4000, 3600)
        y = np.ones_like(x) * 100
        
        for peak in peaks:
            width = peak.width
            height = (100 - peak.intensity)
            y -= height / (1 + ((x - peak.frequency) / (width / 2)) ** 2)
            
        ax.plot(x, y, color='#CC0000')
        ax.set_xlim(4000, 400)
        ax.set_ylim(0, 105)
        ax.set_xlabel("Wavenumber")
        ax.set_ylabel("Transmittance")
        
        plt.savefig(output_path)
        return True

    # 3. Test
    peaks = [
        SpectrumPeakData(frequency=3350, intensity=20, label="O-H", width=150),
        SpectrumPeakData(frequency=2980, intensity=10, label="C-H", width=50),
        SpectrumPeakData(frequency=1050, intensity=15, label="C-O", width=40)
    ]
    
    output_path = "manual_ir_local_def.png"
    print(f"Generating to {output_path}...")
    generate_ir_graph(peaks, output_path)
    
    if os.path.exists(output_path):
        print("SUCCESS: File created.")
    else:
        print("FAILURE: File not found.")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
