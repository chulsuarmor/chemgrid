
try:
    import sys
    import os
    import shutil
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing Graph Generation with direct matplotlib plotting (no class)...")
    
    import matplotlib.pyplot as plt
    import numpy as np
    from dataclasses import dataclass
    
    @dataclass
    class SpectrumPeakData:
        frequency: float
        intensity: float
        width: float = 1.0
        
    def plot_graph(stype, peaks, filename):
        try:
            fig = plt.figure(figsize=(10, 6), dpi=100)
            ax = fig.add_subplot(111)
            
            # Simple plotting logic just to see if file is created
            x = np.linspace(0, 100, 100)
            y = np.random.rand(100)
            ax.plot(x, y)
            ax.set_title(f"Test {stype}")
            
            plt.savefig(filename)
            plt.close(fig)
            print(f"Saved {filename}")
            return True
        except Exception as e:
            print(f"Failed to save {filename}: {e}")
            return False

    # Ensure directory exists
    if not os.path.exists("temp_spectra_images"):
        os.makedirs("temp_spectra_images")
        
    # Generate files directly in CWD first to test
    plot_graph("IR", [], "direct_IR.png")
    plot_graph("NMR", [], "direct_NMR.png")
    
    # Move to temp dir
    if os.path.exists("direct_IR.png"):
        shutil.move("direct_IR.png", "temp_spectra_images/direct_IR.png")
        print("Moved IR to temp dir")
        
    if os.path.exists("direct_NMR.png"):
        shutil.move("direct_NMR.png", "temp_spectra_images/direct_NMR.png")
        print("Moved NMR to temp dir")

except Exception as e:
    print(f"Error: {e}")
