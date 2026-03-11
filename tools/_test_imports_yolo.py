
try:
    from reportlab.lib.pagesizes import A4
    print("ReportLab: OK")
except ImportError:
    print("ReportLab: MISSING")

try:
    from PyQt6.QtWidgets import QApplication
    print("PyQt6: OK")
except ImportError:
    print("PyQt6: MISSING")
