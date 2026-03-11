
import os
from pathlib import Path

# Target file
target_path = Path("popup_uvvis.py")

if not target_path.exists():
    print(f"Error: {target_path} not found")
    exit(1)

content = target_path.read_text(encoding='utf-8')

# Fix: Dual-View and Y-axis Optimization
search_uvvis = """    def plot_uvvis_spectrum(self, wavelengths: np.ndarray, absorption: np.ndarray, bandwidth: float = 20):
        \"\"\"Plot simulated UV-Vis spectrum\"\"\"
        self.ax.clear()
        
        self.ax.fill_between(wavelengths, absorption, alpha=0.3, color='purple')
        self.ax.plot(wavelengths, absorption, color='purple', linewidth=2)
        
        self.ax.set_xlabel('Wavelength (nm)', fontsize=12)
        self.ax.set_ylabel('Absorption (a.u.)', fontsize=12)
        self.ax.set_title(f'UV-Vis Absorption Spectrum (Bandwidth: {bandwidth:.1f} nm)', fontsize=13)
        self.ax.grid(True, alpha=0.3)
        self.ax.invert_xaxis()  # Short wavelengths on right
        
        self.figure.tight_layout()
        self.draw()"""

replace_uvvis = """    def plot_uvvis_spectrum(self, wavelengths: np.ndarray, absorption: np.ndarray, bandwidth: float = 20):
        \"\"\"Plot simulated UV-Vis spectrum (Dual-View: Linear & Log Scale)\"\"\"
        self.figure.clear()
        
        # 1. Linear Scale Plot
        ax1 = self.figure.add_subplot(121)
        ax1.fill_between(wavelengths, absorption, alpha=0.3, color='purple')
        ax1.plot(wavelengths, absorption, color='purple', linewidth=2)
        
        ax1.set_xlabel('Wavelength (nm)', fontsize=10)
        ax1.set_ylabel('Absorption (a.u.)', fontsize=10)
        ax1.set_title(f'Linear Scale', fontsize=11)
        ax1.grid(True, alpha=0.3)
        ax1.invert_xaxis()
        # [Fix] Optimize Y-axis range
        ax1.set_ylim(0, 10000)
        
        # 2. Log Scale Plot
        ax2 = self.figure.add_subplot(122)
        ax2.plot(wavelengths, absorption, color='darkviolet', linewidth=2)
        
        ax2.set_xlabel('Wavelength (nm)', fontsize=10)
        ax2.set_ylabel('Log Absorption', fontsize=10)
        ax2.set_title(f'Log Scale', fontsize=11)
        ax2.grid(True, alpha=0.3)
        ax2.set_yscale('log')
        ax2.invert_xaxis()
        # Log scale needs positive ylim
        ax2.set_ylim(1, 10000)
        
        self.figure.suptitle(f'UV-Vis Absorption Spectrum (Bandwidth: {bandwidth:.1f} nm)', fontsize=13)
        self.figure.tight_layout()
        self.draw()"""

if search_uvvis in content:
    content = content.replace(search_uvvis, replace_uvvis)
    print("Applied UV-Vis Dual-View Fix")
else:
    print("Warning: Could not apply UV-Vis Fix (pattern not found)")
    # Debug: print first few chars of function to help diagnose
    start_idx = content.find("def plot_uvvis_spectrum")
    if start_idx != -1:
        print(f"Found function start at {start_idx}")
        print("Actual content snippet:")
        print(content[start_idx:start_idx+200])
    else:
        print("Function 'plot_uvvis_spectrum' not found")

# Save changes
target_path.write_text(content, encoding='utf-8')
print("Successfully patched popup_uvvis.py")
