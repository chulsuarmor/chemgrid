
try:
    import sys
    import os
    import importlib.util
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing Graph Generation with local class definition...")
    
    # 1. Define classes locally
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

    # 2. Define Generator using matplotlib
    import matplotlib.pyplot as plt
    import numpy as np
    
    class LocalGraphGenerator:
        @staticmethod
        def generate_graph(spectrum_type, peaks, output_path):
            fig = plt.figure(figsize=(10, 6), dpi=300)
            ax = fig.add_subplot(111)
            
            if "IR" in spectrum_type:
                LocalGraphGenerator._plot_ir(ax, peaks)
            elif "NMR" in spectrum_type:
                LocalGraphGenerator._plot_nmr(ax, peaks, spectrum_type)
            elif "UV" in spectrum_type:
                LocalGraphGenerator._plot_uv(ax, peaks)
                
            plt.savefig(output_path)
            plt.close(fig)
            return True

        @staticmethod
        def _plot_ir(ax, peaks):
            x = np.linspace(400, 4000, 3600)
            y = np.ones_like(x) * 100
            for peak in peaks:
                y -= (100 - peak.intensity) / (1 + ((x - peak.frequency) / (peak.width / 2)) ** 2)
            ax.plot(x, y, color='#CC0000')
            ax.set_xlim(4000, 400)
            ax.set_ylim(0, 105)
            ax.set_xlabel("Wavenumber ($cm^{-1}$)")
            ax.set_ylabel("Transmittance (%)")
            ax.set_title("FT-IR Spectrum")
            ax.grid(True, linestyle='--', alpha=0.5)

        @staticmethod
        def _plot_nmr(ax, peaks, stype):
            is_h1 = "H1" in stype
            x_min, x_max = (-0.5, 12.5) if is_h1 else (-10, 230)
            width = 0.01 if is_h1 else 0.5
            x = np.linspace(x_min, x_max, 5000)
            y = np.zeros_like(x)
            for peak in peaks:
                y += peak.intensity / (1 + ((x - peak.frequency) / (width / 2)) ** 2)
            ax.plot(x, y, color='blue')
            ax.set_xlim(x_max, x_min)
            ax.set_xlabel("Chemical Shift (ppm)")
            ax.set_yticks([])
            ax.set_title(f"{'1H' if is_h1 else '13C'} NMR Spectrum")

        @staticmethod
        def _plot_uv(ax, peaks):
            x = np.linspace(200, 800, 600)
            y = np.zeros_like(x)
            for peak in peaks:
                width = peak.width if peak.width > 0 else 40
                sigma = width / 2.355
                y += peak.intensity * np.exp(-0.5 * ((x - peak.frequency) / sigma) ** 2)
            ax.plot(x, y, color='purple')
            ax.fill_between(x, y, color='purple', alpha=0.1)
            ax.set_xlim(200, 800)
            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Absorbance")
            ax.set_title("UV-Vis Spectrum")

    # 3. Generate all test images
    temp_dir = "temp_spectra_images"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # IR
    ir_peaks = [
        SpectrumPeakData(3350, 20, width=150),
        SpectrumPeakData(2980, 10, width=50),
        SpectrumPeakData(1050, 15, width=40)
    ]
    LocalGraphGenerator.generate_graph("IR", ir_peaks, os.path.join(temp_dir, "test_IR.png"))
    print("Generated IR")

    # NMR H1
    h1_peaks = [
        SpectrumPeakData(1.2, 3.0),
        SpectrumPeakData(3.7, 2.0),
        SpectrumPeakData(7.26, 0.5) # Solvent
    ]
    LocalGraphGenerator.generate_graph("NMR_H1", h1_peaks, os.path.join(temp_dir, "test_NMR_H1.png"))
    print("Generated NMR H1")

    # NMR C13
    c13_peaks = [
        SpectrumPeakData(18.4, 1.0),
        SpectrumPeakData(58.2, 0.9)
    ]
    LocalGraphGenerator.generate_graph("NMR_C13", c13_peaks, os.path.join(temp_dir, "test_NMR_C13.png"))
    print("Generated NMR C13")

    # UV
    uv_peaks = [
        SpectrumPeakData(210, 0.8, width=20),
        SpectrumPeakData(280, 0.1, width=30)
    ]
    LocalGraphGenerator.generate_graph("UV_Vis", uv_peaks, os.path.join(temp_dir, "test_UV.png"))
    print("Generated UV")
    
    print("All test images generated successfully.")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
