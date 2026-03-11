import sys
try:
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    print("Qt initialized successfully")
except Exception as e:
    print(f"Qt initialization failed: {e}")
