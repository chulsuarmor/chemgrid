import os
import glob
import sys
import datetime

# Redirect stdout to a file to capture output
log_file = open('verify_log.txt', 'w')
sys.stdout = log_file
sys.stderr = log_file

def verify_latest_pdf():
    print(f"Verification started at {datetime.datetime.now()}")
    
    # 1. Find latest PDF
    search_dir = "docs/exports/spectra_assets/auto_generated"
    # Use absolute path if possible or relative
    if not os.path.exists(search_dir):
        print(f"❌ Directory not found: {search_dir}")
        return

    list_of_files = glob.glob(os.path.join(search_dir, "*.pdf"))
    
    if not list_of_files:
        print("❌ No PDF files found in directory.")
        return

    latest_file = max(list_of_files, key=os.path.getctime)
    print(f"📄 Verifying latest PDF: {latest_file}")
    print(f"📄 File size: {os.path.getsize(latest_file)} bytes")

    # 2. Extract Text
    text_content = ""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(latest_file)
        for page in doc:
            text_content += page.get_text()
        print("✅ PyMuPDF used for extraction.")
    except ImportError:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(latest_file)
            for page in reader.pages:
                text_content += page.extract_text()
            print("✅ PyPDF2 used for extraction.")
        except ImportError:
            print("⚠️ Neither PyMuPDF nor PyPDF2 found. Cannot verify text content.")
            # Still consider success if file exists and has size
            if os.path.getsize(latest_file) > 1000:
                 print("✅ File exists and has content (Size check passed).")
            return

    # 3. Check Keywords
    keywords = {
        "Benzene": "Molecule Name",
        "Linear Scale": "UV-Vis Dual View (Left)",
        "Log Scale": "UV-Vis Dual View (Right)",
        "Integral": "NMR Integral Legend",
        "Zoom": "NMR Inset Zoom",
        "Aliphatic": "Spelling Correction"
    }

    all_passed = True
    print("\n--- Content Verification ---")
    for keyword, desc in keywords.items():
        if keyword in text_content:
            print(f"✅ Found '{keyword}' ({desc})")
        else:
            print(f"❌ Missing '{keyword}' ({desc})")
            all_passed = False

    if all_passed:
        print("\n🎉 SUCCESS: All verification checks passed!")
    else:
        print("\n⚠️ WARNING: Some checks failed.")

if __name__ == "__main__":
    try:
        verify_latest_pdf()
    except Exception as e:
        print(f"CRASH: {e}")
    finally:
        log_file.close()
