
import os
from pathlib import Path

# Target file
target_path = Path("spectrum_analyzer.py")

if not target_path.exists():
    print(f"Error: {target_path} not found")
    exit(1)

content = target_path.read_text(encoding='utf-8')

# 1. Fix Fingerprint Region Label and C=O Stretch
search_ir = "    # Fill under curve\n    ax.fill_between(frequencies, intensities, alpha=0.3, color='blue')"
replace_ir = """    # Fill under curve
    ax.fill_between(frequencies, intensities, alpha=0.3, color='blue')
    
    # [Fix] Add Fingerprint Region Label
    # Draw a shaded region for fingerprint (400-1500 cm-1)
    ax.axvspan(1500, 400, color='gray', alpha=0.1)
    ax.text(950, 95, "Fingerprint Region", fontsize=10, color='gray', ha='center', style='italic')

    # [Fix] Add C=O Stretch Label if peak exists near 1720
    # Search for strongest peak in C=O region (1680-1760)
    co_peak = None
    max_co_int = 0
    for freq, inten in zip(spectrum_data.ir_frequencies, spectrum_data.ir_intensities):
        if 1680 <= freq <= 1760 and inten > 10: # Threshold
            if inten > max_co_int:
                max_co_int = inten
                co_peak = (freq, inten)
    
    if co_peak:
        # Normalize intensity for annotation position (since Y is 0-100%)
        # But spectrum_data.ir_intensities are in km/mol, while plot is normalized.
        # We need to map km/mol to % relative to max intensity.
        max_total_int = max(spectrum_data.ir_intensities) if spectrum_data.ir_intensities else 1.0
        norm_y = (co_peak[1] / max_total_int) * 100.0
        
        ax.annotate("C=O stretch", xy=(co_peak[0], norm_y), xytext=(co_peak[0], norm_y+15),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), 
                    ha='center', fontsize=9, fontweight='bold')
"""

if search_ir in content:
    content = content.replace(search_ir, replace_ir)
    print("Applied IR Label Fix")
else:
    print("Warning: Could not apply IR Label Fix (pattern not found)")


# 2. Fix Raman Peak Labels
search_raman = "                  color='darkgreen', s=50, marker='x', label='Peak positions', zorder=5)"
replace_raman = """                  color='darkgreen', s=50, marker='x', label='Peak positions', zorder=5)

        # [Fix] Add Peak Labels (Values)
        for freq, act in zip(spectrum_data.raman_frequencies, norm_acts):
            if act > 5.0:  # Show label for significant peaks
                ax.text(freq, act + 3, f"{freq:.0f}", ha='center', va='bottom', 
                       fontsize=8, rotation=90, color='darkgreen')"""

if search_raman in content:
    content = content.replace(search_raman, replace_raman)
    print("Applied Raman Label Fix")
else:
    print("Warning: Could not apply Raman Label Fix (pattern not found)")

# Save changes
target_path.write_text(content, encoding='utf-8')
print("Successfully patched spectrum_analyzer.py")
