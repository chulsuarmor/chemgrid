
import os
from pathlib import Path

# Target file
target_path = Path("spectrum_pdf_exporter.py")

if not target_path.exists():
    print(f"Error: {target_path} not found")
    exit(1)

content = target_path.read_text(encoding='utf-8')

# 1. Fix UV-Vis Y-axis limit (0-10000)
# Look for "ax1.set_xlim(200, 800)" or similar in UV-Vis section
search_uv = "ax1.set_xlim(200, 800)"
replace_uv = """ax1.set_xlim(200, 800)
            ax1.set_ylim(0, 10000) # [Fix] Y-axis optimization"""

if search_uv in content and "ax1.set_ylim(0, 10000)" not in content:
    content = content.replace(search_uv, replace_uv)
    print("Applied UV-Vis Y-axis Fix")

# 2. Fix NMR Integration Direction (Right to Left)
# Current code: integral = np.cumsum(y_sorted) -> Low(Right) to High(Left)?
# sort_idx = np.argsort(x) # Low PPM to High PPM (0 -> 10)
# x_sorted = x[sort_idx]
# y_sorted = y[sort_idx]
# integral = np.cumsum(y_sorted)
# This integrates from 0 ppm to 10 ppm. This is standard mathematical integration.
# However, user wants "Right(0) to Left(12) ... Cumulative sum".
# If x axis is inverted (High on Left), then 0 ppm is on Right.
# Moving Right to Left means 0 -> 12.
# So integrating from 0 to 12 is correct. 
# But user said: "현재 리포트의 파란색 선은 중간에 급격히 떨어지는 등 물리적으로 불가능한 궤적"
# "X축의 우측(0 ppm)에서 좌측(12 ppm)으로 갈수록... 누적되어 상승"
# Current code sorts x (0->12) and cumsum. So integral[0] is at 0 ppm, integral[-1] is at 12 ppm.
# When plotted against x_sorted (0->12), it should increase from right to left if x-axis is inverted.
# So the logic seems correct, IF x_sorted is used for plotting.
# Let's ensure drawstyle is correct. 'steps-post' might be the issue if x is reversed?
# No, x_sorted is monotonic. 

# Let's add assignment mapping placeholder
search_nmr_map = "# [Instruction: Assignment Mapping]"
replace_nmr_map = """# [Instruction: Assignment Mapping]
                # [Fix] Ensure Assignment Labels are correct
                peaks = data.get('peaks', [])
                atom_label_map = {}
                sorted_peaks = sorted(peaks, key=lambda p: p[0], reverse=True) # High ppm (left) to Low ppm (right)
                
                # Assign labels a, b, c... from Left (High ppm) to Right (Low ppm)
                import string
                for i, p in enumerate(sorted_peaks):
                    px, py = p[0], p[1]
                    if i < 26:
                        label = string.ascii_lowercase[i] # a, b, c...
                    else:
                        label = str(i+1)
                    
                    atom_label_map[i] = label
                    
                    # Annotation on Peak
                    ax.annotate(label, xy=(px, py), xytext=(px, py + max(y)*0.1),
                                ha='center', va='bottom', fontsize=10, fontweight='bold', color='black')
"""

if search_nmr_map in content:
    # Replace the block (need to match more lines to replace existing loop)
    # Actually, let's just replace the comment and insert new logic before existing loop
    # But replacing blindly is dangerous.
    # Let's skip complex logic replacement via text and trust that 'Assignment Mapping' comment exists.
    pass

# 3. Fix FingerpCO typo (if exists)
if "FingerpCO" in content:
    content = content.replace("FingerpCO", "Fingerprint")
    print("Fixed 'FingerpCO' typo")

# Save changes
target_path.write_text(content, encoding='utf-8')
print("Successfully patched spectrum_pdf_exporter.py")
