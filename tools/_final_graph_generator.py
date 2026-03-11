
import sys
import os
import shutil
import matplotlib.pyplot as plt
import numpy as np
from dataclasses import dataclass

# Ensure temp directory exists
temp_dir = "temp_spectra_images"
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)

@dataclass
class SpectrumPeakData:
    frequency: float
    intensity: float
    width: float = 1.0
    label: str = ""
    multiplicity: str = 's'
    integral: float = 1.0
    assignment: str = ""
    unit: str = "cm⁻¹"

def generate_graphs():
    print("Generating IR graph...", flush=True)
    try:
        fig = plt.figure(figsize=(10, 6), dpi=300)
        ax = fig.add_subplot(111)
        
        # IR Logic: Wavenumber 4000->400, Transmittance 0-100%
        x = np.linspace(400, 4000, 3600)
        y = np.ones_like(x) * 100
        
        peaks = [
            SpectrumPeakData(3350, 20, width=150, label="O-H"),
            SpectrumPeakData(2980, 10, width=50, label="C-H"),
            SpectrumPeakData(1050, 15, width=40, label="C-O")
        ]
        
        for peak in peaks:
            height = (100 - peak.intensity)
            y -= height / (1 + ((x - peak.frequency) / (peak.width / 2)) ** 2)
            
        ax.plot(x, y, color='#CC0000')
        ax.set_xlim(4000, 400)
        ax.set_ylim(0, 105)
        ax.set_xlabel("Wavenumber ($cm^{-1}$)")
        ax.set_ylabel("Transmittance (%)")
        ax.set_title("FT-IR Spectrum")
        ax.grid(True, linestyle='--', alpha=0.5)
        
        # Fingerprint region
        ax.axvline(x=1500, color='gray', linestyle='--', alpha=0.7)
        ax.text(1450, 5, "Fingerprint Region", ha='right', fontsize=10, color='gray', style='italic')
        
        output_path = os.path.join(temp_dir, "IR_graph.png")
        plt.savefig(output_path)
        plt.close(fig)
        print(f"Saved IR graph to {output_path}")
    except Exception as e:
        print(f"Failed to generate IR: {e}")

    print("Generating H1 NMR graph...", flush=True)
    try:
        fig = plt.figure(figsize=(10, 6), dpi=300)
        ax = fig.add_subplot(111)
        
        # H1 NMR Logic: 12->0 ppm
        x = np.linspace(-0.5, 12.5, 5000)
        y = np.zeros_like(x)
        
        peaks = [
            SpectrumPeakData(1.2, 3.0, width=0.01, multiplicity='t', integral=3.0),
            SpectrumPeakData(3.7, 2.0, width=0.01, multiplicity='q', integral=2.0),
            SpectrumPeakData(7.26, 0.5, width=0.01, label="Solvent") 
        ]
        
        for peak in peaks:
            # Simplified Lorentzian
            y += peak.intensity / (1 + ((x - peak.frequency) / (peak.width / 2)) ** 2)
            
        ax.plot(x, y, color='blue')
        ax.set_xlim(12.5, -0.5)
        ax.set_xlabel("Chemical Shift (ppm)")
        ax.set_yticks([])
        ax.set_title("1H NMR Spectrum")
        
        # Add labels
        for peak in peaks:
            if peak.integral > 0:
                ax.text(peak.frequency, peak.intensity + 0.1, f"{peak.integral}H", ha='center')
        
        output_path = os.path.join(temp_dir, "NMR_H1_graph.png")
        plt.savefig(output_path)
        plt.close(fig)
        print(f"Saved H1 NMR graph to {output_path}")
    except Exception as e:
        print(f"Failed to generate H1 NMR: {e}")

    print("Generating C13 NMR graph...", flush=True)
    try:
        fig = plt.figure(figsize=(10, 6), dpi=300)
        ax = fig.add_subplot(111)
        
        # C13 NMR Logic: 230->-10 ppm
        x = np.linspace(-10, 230, 5000)
        y = np.zeros_like(x)
        
        peaks = [
            SpectrumPeakData(18.4, 1.0, width=0.5),
            SpectrumPeakData(58.2, 0.9, width=0.5)
        ]
        
        for peak in peaks:
            y += peak.intensity / (1 + ((x - peak.frequency) / (peak.width / 2)) ** 2)
            
        ax.plot(x, y, color='blue')
        ax.set_xlim(230, -10)
        ax.set_xlabel("Chemical Shift (ppm)")
        ax.set_yticks([])
        ax.set_title("13C NMR Spectrum")
        
        # Zoning background
        ax.axvspan(50, 0, color='#FFFFE0', alpha=0.3)
        ax.text(25, np.max(y)*0.9, "Aliphatic", ha='center', fontsize=8, alpha=0.6)
        
        output_path = os.path.join(temp_dir, "NMR_C13_graph.png")
        plt.savefig(output_path)
        plt.close(fig)
        print(f"Saved C13 NMR graph to {output_path}")
    except Exception as e:
        print(f"Failed to generate C13 NMR: {e}")

    print("Generating UV-Vis graph...", flush=True)
    try:
        fig = plt.figure(figsize=(10, 6), dpi=300)
        ax = fig.add_subplot(111)
        
        # UV Logic: 200->800 nm
        x = np.linspace(200, 800, 1000)
        y = np.zeros_like(x)
        
        peaks = [
            SpectrumPeakData(210, 0.8, width=20),
            SpectrumPeakData(280, 0.1, width=30)
        ]
        
        for peak in peaks:
            sigma = peak.width / 2.355
            y += peak.intensity * np.exp(-0.5 * ((x - peak.frequency) / sigma) ** 2)
            
        ax.plot(x, y, color='purple')
        ax.fill_between(x, y, color='purple', alpha=0.1)
        ax.set_xlim(200, 800)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Absorbance")
        ax.set_title("UV-Vis Spectrum")
        
        output_path = os.path.join(temp_dir, "UV_Vis_graph.png")
        plt.savefig(output_path)
        plt.close(fig)
        print(f"Saved UV-Vis graph to {output_path}")
    except Exception as e:
        print(f"Failed to generate UV-Vis: {e}")

if __name__ == "__main__":
    generate_graphs()
