
import os
import sys
import json
import logging
from pathlib import Path
import PyPDF2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def verify_pdf(file_path):
    result = {
        "file": str(file_path),
        "exists": False,
        "valid_pdf": False,
        "page_count": 0,
        "has_images": False,
        "text_content_length": 0,
        "keywords_found": [],
        "error": None
    }
    
    p = Path(file_path)
    if not p.exists():
        return result
        
    result["exists"] = True
    
    try:
        with open(p, 'rb') as f:
            try:
                reader = PyPDF2.PdfReader(f)
                
                # Check encryption
                if reader.is_encrypted:
                    result["error"] = "PDF is encrypted"
                    return result
                
                result["page_count"] = len(reader.pages)
                
                if result["page_count"] > 0:
                    result["valid_pdf"] = True
                    
                    # Analyze first page
                    page = reader.pages[0]
                    text = page.extract_text()
                    result["text_content_length"] = len(text)
                    
                    # Keywords to look for
                    keywords = ["Molecule", "SMILES", "Spectrum", "Report", "Analysis"]
                    found = [k for k in keywords if k in text]
                    result["keywords_found"] = found
                    
                    # Check for images (basic check)
                    if '/XObject' in page['/Resources']:
                        xObject = page['/Resources']['/XObject'].get_object()
                        for obj in xObject:
                            if xObject[obj]['/Subtype'] == '/Image':
                                result["has_images"] = True
                                break
                                
            except Exception as e:
                 result["error"] = f"PyPDF2 Error: {str(e)}"
                 
    except Exception as e:
        result["error"] = f"File Error: {str(e)}"
        
    return result

def main():
    # Directories to scan
    dirs_to_scan = [
        Path("_source/lewis_structures/pdf"),
        Path("docs/exports/spectra_assets/auto_generated")
    ]
    
    summary = {
        "scanned_files": 0,
        "valid_pdfs": [],
        "invalid_pdfs": [],
        "issues": []
    }
    
    print("=== Advanced Lewis Structure PDF Verification ===")
    
    for d in dirs_to_scan:
        if not d.exists():
            print(f"[WARN] Directory not found: {d}")
            continue
            
        print(f"Scanning: {d}")
        pdf_files = list(d.glob("*.pdf"))
        
        for pdf in pdf_files:
            summary["scanned_files"] += 1
            print(f"  Verifying {pdf.name}...", end=" ")
            
            res = verify_pdf(pdf)
            
            if res["valid_pdf"]:
                print("OK")
                summary["valid_pdfs"].append(res)
                
                # Further checks for structural validity issues based on text/content
                issues = []
                if not res["has_images"]:
                    issues.append(f"{pdf.name}: No images found (Structure likely missing)")
                if res["text_content_length"] < 50:
                    issues.append(f"{pdf.name}: Very little text content ({res['text_content_length']} chars)")
                
                if issues:
                    summary["issues"].extend(issues)
                    print(f"    [ISSUES] {', '.join(issues)}")
                    
            else:
                print(f"FAIL - {res['error']}")
                summary["invalid_pdfs"].append(res)

    # Report generation
    print("\n=== Verification Summary ===")
    print(f"Total Scanned: {summary['scanned_files']}")
    print(f"Valid PDFs: {len(summary['valid_pdfs'])}")
    print(f"Invalid PDFs: {len(summary['invalid_pdfs'])}")
    
    if summary["issues"]:
        print("\n[Identified Potential Issues]")
        for issue in summary["issues"]:
            print(f" - {issue}")
            
    # Save detailed JSON
    with open("_verification_results_advanced.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nDetailed results saved to _verification_results_advanced.json")

if __name__ == "__main__":
    main()
