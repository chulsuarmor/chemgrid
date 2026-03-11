
import sys
import os
import json
import logging
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QPointF, QTimer, QEvent
from PyQt6.QtGui import QMouseEvent, QPainter, QColor
import traceback

print(f"DEBUG: Current CWD: {os.getcwd()}")

# Add project root to path
sys.path.append(r"C:\chemgrid")
sys.path.append(r"C:\chemgrid\agents\10_testing_build\integrated")
print(f"DEBUG: sys.path added hardcoded paths")

try:
    # Import canvas directly
    from canvas import MoleculeCanvas
    from renderer import CloudRenderer
    print("DEBUG: Successfully imported canvas and renderer")
except Exception as e:
    print(f"CRITICAL ERROR importing modules: {e}")
    traceback.print_exc()
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ReproRadical")

class ReproCanvasTester(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Repro Radical Tester")
        self.resize(1200, 800)
        
        self.layout = QVBoxLayout(self)
        self.canvas = MoleculeCanvas()
        self.layout.addWidget(self.canvas)
        
        self.step_delay = 100 # Faster than interactive
        
        self.test_atoms = {}
        self.test_bonds = {}
        
        self.grid_size = 40
        self.rh = self.grid_size * 0.866
        
        self._init_recipe()
        
    def _get_grid_point(self, col, row):
        y = row * self.rh
        off = self.grid_size / 2 if row % 2 != 0 else 0
        x = col * self.grid_size + off
        return (x, y)

    def _init_recipe(self):
        def to_key(grid_x, grid_y):
            pt = self._get_grid_point(grid_x, grid_y)
            return (round(pt[0], 2), round(pt[1], 2))

        # New 5-membered ring coordinates
        # p1(5,4) -> p2(4,5) -> p3(5,6) -> p4(6,6) -> p5(6,5) -> p1(5,4)
        
        p1 = to_key(5, 4) # Top
        p2 = to_key(4, 5) # Left Top
        p3 = to_key(5, 6) # Left Bottom
        p4 = to_key(6, 6) # Right Bottom
        p5 = to_key(6, 5) # Right Top

        self.recipe = [
            ("mode", "Bond"),
            ("drag", (p1, p2)),
            ("drag", (p2, p3)),
            ("drag", (p3, p4)),
            ("drag", (p4, p5)),
            ("drag", (p5, p1)),
            
            # Double bonds: p2-p3, p4-p5
            ("drag", (p2, p3)),
            ("drag", (p4, p5)),

            # Radical on p1
            ("mode", "Radical"),
            ("click", p1)
        ]

    def run_test(self):
        logger.info("Starting Repro Test for Level 4 (Server Def)")
        
        # Reset canvas state
        self.canvas.atoms = {}
        self.canvas.bonds = {}
        self.canvas.update()
        
        self.execute_steps(self.recipe, 0)

    def execute_steps(self, steps, index):
        if index >= len(steps):
            self.verify_result()
            return
            
        step = steps[index]
        action, params = step
        
        logger.info(f"Action: {action} {params}")
        
        if action == "mode":
            self.canvas.mode = params
            
        elif action == "click":
            key = params
            if self.canvas.mode == "Radical":
                if key in self.test_atoms:
                    atom_data = self.test_atoms[key]
                    atom_data["attach"][0] = "·" 
            
            self.canvas.atoms = self.test_atoms.copy()
            self.canvas.bonds = self.test_bonds.copy()
            self.canvas.update()
            
        elif action == "drag":
            start_t, end_t = params
            key1 = start_t
            key2 = end_t
            
            if key1 != key2:
                bond_key = tuple(sorted((key1, key2)))
                
                # Ensure atoms
                if key1 not in self.test_atoms:
                    self.test_atoms[key1] = {"main": "C", "attach": {}}
                if key2 not in self.test_atoms:
                    self.test_atoms[key2] = {"main": "C", "attach": {}}
                
                if self.canvas.mode == "Bond":
                    current = self.test_bonds.get(bond_key, 0)
                    self.test_bonds[bond_key] = (current % 3) + 1
            
            self.canvas.atoms = self.test_atoms.copy()
            self.canvas.bonds = self.test_bonds.copy()
            self.canvas.update()
            self.canvas.on_molecule_updated() # Trigger analysis

        QTimer.singleShot(self.step_delay, lambda: self.execute_steps(steps, index + 1))

    def verify_result(self):
        logger.info("Steps completed. Capturing result...")
        self.canvas.atoms = self.test_atoms.copy()
        self.canvas.bonds = self.test_bonds.copy()
        
        # Force Analysis
        self.canvas.analysis_results = self.canvas.analyzer.analyze(self.canvas.atoms, self.canvas.bonds)
        res = self.canvas.analysis_results
        
        smiles = self.canvas.get_smiles()
        logger.info(f"Generated SMILES: {smiles}")
        
        if res:
            logger.info(f"Analysis Result Keys: {list(res.keys())}")
            logger.info(f"Islands: {res.get('islands')}")
            logger.info(f"Aromatic Rings: {res.get('aromatic')}")
            
            if "electron_clouds" in res:
                logger.info(f"Electron Clouds: {len(res['electron_clouds'])}")
            else:
                logger.warning("No electron_clouds key (expected)")
        else:
            logger.error("Analysis failed (None)")

        # Save Screenshot
        self.canvas.resize(600, 600)
        pixmap = self.canvas.grab()
        pixmap.save("_repro_radical_C.png")
        logger.info("Saved _repro_radical_C.png")
        
        QTimer.singleShot(1000, QApplication.instance().quit)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    tester = ReproCanvasTester()
    tester.show()
    QTimer.singleShot(1000, tester.run_test)
    sys.exit(app.exec())
