
import os
from pathlib import Path
import numpy as np # Need numpy for logic check if we were running it, but for patching text string it's fine.

# Target file
target_path = Path("popup_nmr.py")

if not target_path.exists():
    print(f"Error: {target_path} not found")
    exit(1)

content = target_path.read_text(encoding='utf-8')

# Fix: NMR Integration Line
search_nmr = """    def plot_nmr_spectrum(self, freq: np.ndarray, intensity: np.ndarray, 
                          nucleus: str = "1H", linewidth_hz: float = 1.0):
        \"\"\"Plot NMR spectrum\"\"\"
        self.ax.clear()
        
        # Plot spectrum
        self.ax.fill_between(freq, intensity, alpha=0.3, color='blue')
        self.ax.plot(freq, intensity, color='blue', linewidth=1.5)
        
        # Labels and title
        self.ax.set_xlabel('Chemical Shift (ppm)', fontsize=12)
        self.ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        self.ax.set_title(f'{nucleus} NMR Spectrum (Linewidth: {linewidth_hz:.1f} Hz)', fontsize=13)
        self.ax.invert_xaxis()  # NMR convention
        self.ax.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.draw()"""

replace_nmr = """    def plot_nmr_spectrum(self, freq: np.ndarray, intensity: np.ndarray, 
                          nucleus: str = "1H", linewidth_hz: float = 1.0):
        \"\"\"Plot NMR spectrum with Integral\"\"\"
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        
        # Plot spectrum
        self.ax.fill_between(freq, intensity, alpha=0.3, color='blue')
        self.ax.plot(freq, intensity, color='blue', linewidth=1.5)
        
        # [Fix] Add Integration Line (Step-wise, Cumulative)
        if nucleus == "1H":
            ax2 = self.ax.twinx()
            
            # NMR integration: cumulative sum from right (0 ppm) to left (10 ppm)
            # freq array is sorted Descending (e.g. 15 -> 0)
            
            if len(freq) > 1 and freq[0] > freq[-1]: # Descending
                # Calculate cumulative sum from end (right) to start (left)
                integral = np.cumsum(intensity[::-1])[::-1]
                
                # Normalize integral
                if integral.max() > 0:
                    integral = (integral / integral.max()) * 60.0 # Max height 60%
                
                ax2.plot(freq, integral, 'r-', linewidth=1.5, alpha=0.6, label='Integral')
                ax2.set_ylim(0, 100)
                ax2.set_yticks([])
        
        # Labels and title
        self.ax.set_xlabel('Chemical Shift (ppm)', fontsize=12)
        self.ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        self.ax.set_title(f'{nucleus} NMR Spectrum (Linewidth: {linewidth_hz:.1f} Hz)', fontsize=13)
        self.ax.invert_xaxis()  # NMR convention
        self.ax.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.draw()"""

if search_nmr in content:
    content = content.replace(search_nmr, replace_nmr)
    print("Applied NMR Integration Fix")
else:
    print("Warning: Could not apply NMR Fix (pattern not found)")
    # Debug
    start_idx = content.find("def plot_nmr_spectrum")
    if start_idx != -1:
        print(f"Found function start at {start_idx}")
        print("Actual content snippet:")
        print(content[start_idx:start_idx+200])

# Save changes
target_path.write_text(content, encoding='utf-8')
print("Successfully patched popup_nmr.py")
