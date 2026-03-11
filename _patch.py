import ast
fp=r"c:\chemgrid\src\app\spectrum_pdf_exporter.py"
c=open(fp,encoding="utf-8").read()
print("size:",len(c))
print("anchor:","except ImportError:\n    MATPLOTLIB_AVAILABLE = False" in c)
print("HB:",c.count("Helvetica-Bold"))
print("KF:","KOREAN_FONT" in c)
