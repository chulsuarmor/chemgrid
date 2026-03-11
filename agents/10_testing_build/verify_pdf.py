
import sys
import os
from pathlib import Path

def verify_pdf_content(pdf_path):
    print(f"Verifying PDF: {pdf_path}")
    
    try:
        from pypdf import PdfReader
    except ImportError:
        print("[SKIP] pypdf library not installed. Cannot verify PDF content directly.")
        print("Please install pypdf: pip install pypdf")
        return False

    if not os.path.exists(pdf_path):
        print(f"[ERROR] PDF file not found: {pdf_path}")
        return False

    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        print(f"Extracted {len(text)} characters from PDF.")
        
        # Check for keywords
        # Note: Text inside images (like 'Fingerprint Region' on graph) cannot be detected by pypdf.
        # We check for section headers and interpretative notes instead.
        required_keywords = [
            "Infrared Spectrum",  # Section Header
            "C=O stretch",       # From Interpretative Notes
            "Raman Spectrum",    # Section Header
            "UV-Vis Spectrum"    # Section Header
        ]
        
        missing = []
        for kw in required_keywords:
            if kw in text:
                print(f"[PASS] Found keyword: '{kw}'")
            else:
                print(f"[FAIL] Missing keyword: '{kw}'")
                missing.append(kw)
        
        with open("verification_result.txt", "w") as f:
            if missing:
                print("PDF Verification FAILED.")
                f.write(f"FAIL: Missing keywords {missing}\n")
                return False
            else:
                print("PDF Verification PASSED.")
                f.write("PASS: All keywords found.\n")
                return True
            
    except Exception as e:
        print(f"[ERROR] Failed to read PDF: {e}")
        with open("verification_result.txt", "w") as f:
            f.write(f"ERROR: {e}\n")
        return False

if __name__ == "__main__":
    import glob
    
    pdf_path = None
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Find latest PDF in docs/exports/spectra_assets/auto_generated
        search_dir = Path("docs/exports/spectra_assets/auto_generated")
        if search_dir.exists():
            pdf_files = list(search_dir.glob("*.pdf"))
            if pdf_files:
                # Sort by modification time
                latest_pdf = max(pdf_files, key=os.path.getmtime)
                pdf_path = str(latest_pdf)
                print(f"Auto-detected latest PDF: {pdf_path}")
            else:
                print(f"[ERROR] No PDF files found in {search_dir}")
        else:
            print(f"[ERROR] Directory not found: {search_dir}")

    if pdf_path:
        verify_pdf_content(pdf_path)
    else:
        print("Usage: python verify_pdf.py <path_to_pdf>")
        sys.exit(1)
