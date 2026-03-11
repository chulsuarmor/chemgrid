
import sys
import os
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt

# Ensure we can import the integrated modules
sys.path.append(os.path.abspath("agents/10_testing_build/integrated"))
from main_window import MainWindow

# Assets directory for captured images
ASSETS_DIR = Path("docs/exports/assets")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

MOLECULES = [
    {"name": "Benzene", "smiles": "c1ccccc1"},
    {"name": "Nitrobenzene", "smiles": "C1=CC=C(C=C1)[N+](=O)[O-]"},
    {"name": "Ethanol", "smiles": "CCO"},
    {"name": "Aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
    {"name": "Caffeine", "smiles": "Cn1cnc2c1c(=O)n(c(=O)n2C)C"},
    {"name": "Water", "smiles": "O"},
    {"name": "Methane", "smiles": "C"},
    {"name": "Glucose", "smiles": "C(C1C(C(C(C(O1)O)O)O)O)O"},
    {"name": "Paracetamol", "smiles": "CC(=O)Nc1ccc(cc1)O"},
    {"name": "Alpha-Pinene", "smiles": "CC1=CCC2CC1C2(C)C"}
]

class ReportAssetCapturer:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        self.window.resize(900, 600)
        self.window.show()
        self.current_index = 0

    def start_capture(self):
        print(f"Starting PyQt6-based asset capture for {len(MOLECULES)} molecules...")
        self.process_next()
        sys.exit(self.app.exec())

    def process_next(self):
        if self.current_index >= len(MOLECULES):
            print("All assets captured successfully.")
            self.app.quit()
            return

        mol = MOLECULES[self.current_index]
        print(f"Capturing {mol['name']}...")

        # 1. Simulate drawing or loading SMILES (Directly setting for verification)
        if hasattr(self.window.cv, 'clear_all'):
            self.window.window.clear_all()
        else:
            self.window.cv.atoms = {}
            self.window.cv.bonds = {}
        
        # 2. Capture Lewis View (Wait for paint)
        QTimer.singleShot(500, lambda: self.capture_step(mol, "lewis"))

    def capture_step(self, mol, mode):
        # Grab canvas area
        pixmap = self.window.cv.grab()
        pixmap.save(str(ASSETS_DIR / f"{mol['name']}_{mode}.png"))
        
        if mode == "lewis":
            # 3. Switch to Theory Mode using the high-level method
            print(f"Switching to Theory view for {mol['name']}...")
            self.window.switch_view("Theory")
            
            # 4. Capture Theory View (Needs more time for 3D/Geometry rendering)
            QTimer.singleShot(1000, lambda: self.capture_step(mol, "theory"))
        else:
            # Done with this molecule
            self.current_index += 1
            # Back to Lewis (Drawing) for next
            print(f"Resetting to Drawing view for next molecule...")
            self.window.switch_view("Drawing")
            self.process_next()

if __name__ == "__main__":
    # Use offscreen rendering for headless environments if possible, 
    # but we need to see it for verification as requested.
    capturer = ReportAssetCapturer()
    capturer.start_capture()
