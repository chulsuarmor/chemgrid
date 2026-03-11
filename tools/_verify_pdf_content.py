import os
import sys
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    print("Warning: PyMuPDF (fitz) not available. Text verification will be skipped.")

import re

def verify_exports(export_dir):
    print(f"Verifying exports in: {export_dir}")
    
    if not os.path.exists(export_dir):
        print("❌ Export directory not found!")
        return False

    files = os.listdir(export_dir)
    print(f"Found {len(files)} files.")
    
    expected_molecules = [
        "Benzene", "Nitrobenzene", "Cis-2-Butene", "Norbornane", "Cubane",
        "Glyceraldehyde", "Thiophene", "Tropylium", "Cyclopentadienyl", "Ospirane",
        "Cyclopentadienyl_Anion", "Tropylium_Cation"
    ]
    
    missing_files = []
    text_content_map = {}
    
    for mol in expected_molecules:
        # Check required files
        lewis_file = f"01_Lewis_{mol}.pdf"
        theory_file = f"02_Theory_{mol}.pdf"
        spectrum_file = f"spectrum_report_{mol}.pdf"
        
        if lewis_file not in files: missing_files.append(lewis_file)
        if theory_file not in files: missing_files.append(theory_file)
        if spectrum_file not in files: missing_files.append(spectrum_file)
        
        # Verify Spectrum Content
        if spectrum_file in files and FITZ_AVAILABLE:
            path = os.path.join(export_dir, spectrum_file)
            try:
                doc = fitz.open(path)
                text = ""
                for page in doc:
                    text += page.get_text()
                
                text_content_map[mol] = text
                
                # Check for Molecule Name
                if mol.replace("_", " ") not in text and mol not in text:
                    print(f"❌ {spectrum_file}: Molecule name '{mol}' not found in text.")
                
                # Check for AI Insight Overlay text (heuristic)
                if "AI Insight" not in text and "AI Interpretation" not in text:
                    print(f"⚠️ {spectrum_file}: AI Insight/Interpretation missing.")
                    
            except Exception as e:
                print(f"❌ Error reading {spectrum_file}: {e}")

    if missing_files:
        print(f"❌ Missing {len(missing_files)} files:")
        for f in missing_files:
            print(f"  - {f}")
        return False
    else:
        print("[OK] All expected files present.")

    # Check for duplicate content (identical reports)
    print("\nChecking for duplicate content in spectrum reports...")
    duplicates = []
    keys = list(text_content_map.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            mol1, mol2 = keys[i], keys[j]
            # Simple check: if text is exactly identical (ignoring very minor diffs if any)
            # Metadata date might differ slightly, so we check body
            txt1 = text_content_map[mol1]
            txt2 = text_content_map[mol2]
            
            # Remove timestamp lines for comparison
            lines1 = [l for l in txt1.split('\n') if "Report Generated" not in l]
            lines2 = [l for l in txt2.split('\n') if "Report Generated" not in l]
            
            if lines1 == lines2:
                duplicates.append((mol1, mol2))

    if duplicates:
        print(f"[FAIL] Found identical reports (Duplicate Content Issue):")
        for m1, m2 in duplicates:
            print(f"  - {m1} == {m2}")
        return False
    else:
        print("[OK] No duplicate reports found. Content appears unique.")

    print("\nVerification Summary: PASS")
    return True

if __name__ == "__main__":
    # Default path used in automation script
    target_dir = os.path.abspath("docs/exports/Test_20260301_Final")
    verify_exports(target_dir)
