
import sys
import os
import json
import logging
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QPointF, QTimer, QEvent
from PyQt6.QtGui import QMouseEvent

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "agents", "10_testing_build", "integrated"))

# Import canvas directly, bypassing MainWindow complexity
from canvas import MoleculeCanvas

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InteractiveTest")

class IsolatedCanvasTester(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Isolated Canvas Tester")
        self.resize(1200, 800)
        
        self.layout = QVBoxLayout(self)
        self.canvas = MoleculeCanvas()
        self.layout.addWidget(self.canvas)
        
        self.step_delay = 500
        
        # Internal data storage to prevent loss
        self.test_atoms = {}
        self.test_bonds = {}
        
        # Grid parameters from canvas
        self.grid_size = 40
        self.rh = self.grid_size * 0.866
        
        self._init_molecules()
        
    def _get_grid_point(self, col, row):
        y = row * self.rh
        off = self.grid_size / 2 if row % 2 != 0 else 0
        x = col * self.grid_size + off
        return (x, y)

    def _init_molecules(self):
        # Convert to key format directly
        def to_key(pt):
            return (round(pt[0], 2), round(pt[1], 2))
            
        pt_n = to_key(self._get_grid_point(10, 9))
        pt_h1 = to_key(self._get_grid_point(9, 7))
        pt_h2 = to_key(self._get_grid_point(11, 7))
        pt_h3 = to_key(self._get_grid_point(10, 11))
        
        c1 = to_key(self._get_grid_point(5, 9))
        c2 = to_key(self._get_grid_point(6, 9))
        c3 = to_key(self._get_grid_point(7, 9))
        c4 = to_key(self._get_grid_point(8, 9))
        c5 = to_key(self._get_grid_point(9, 9))
        
        ph1 = to_key(self._get_grid_point(6, 7))
        ph2 = to_key(self._get_grid_point(7, 7))
        ph3 = to_key(self._get_grid_point(7, 9))
        ph4 = to_key(self._get_grid_point(7, 11))
        ph5 = to_key(self._get_grid_point(6, 11))
        ph6 = to_key(self._get_grid_point(6, 9))
        ph_o = to_key(self._get_grid_point(8, 9))
        
        # Ethanol
        et_c1 = to_key(self._get_grid_point(7, 9))
        et_c2 = to_key(self._get_grid_point(8, 9))
        et_o = to_key(self._get_grid_point(9, 9))
        
        # S-Lactic Acid points
        sl_c1 = to_key(self._get_grid_point(7, 7))
        sl_c2 = to_key(self._get_grid_point(8, 7))
        sl_c3 = to_key(self._get_grid_point(9, 7))
        sl_o1 = to_key(self._get_grid_point(10, 6))
        sl_o2 = to_key(self._get_grid_point(10, 8))
        sl_oh = to_key(self._get_grid_point(8, 5))
        
        self.molecules = {
            "Ammonia": {
                "steps": [
                    ("mode", "N"), ("click", pt_n),
                    ("mode", "H"), ("click", pt_h1), ("click", pt_h2), ("click", pt_h3),
                    ("mode", "LonePair"), ("click", pt_n),
                    ("mode", "Bond"), ("drag", (pt_n, pt_h1)), ("drag", (pt_n, pt_h2)), ("drag", (pt_n, pt_h3))
                ],
                "expected_smiles": "N"
            },
            "Ethanol": {
                "steps": [
                    ("mode", "Bond"), 
                    ("drag", (et_c1, et_c2)), 
                    ("drag", (et_c2, et_o)), 
                    ("mode", "O"), ("click", et_o)
                ],
                "expected_smiles": "CCO"
            },
            "Pentane": {
                "steps": [
                    ("mode", "Bond"),
                    ("drag", (c1, c2)), ("drag", (c2, c3)), ("drag", (c3, c4)), ("drag", (c4, c5))
                ],
                "expected_smiles": "CCCCC"
            },
            "Phenol": {
                "steps": [
                    ("mode", "Bond"),
                    ("drag", (ph1, ph2)), ("drag", (ph2, ph3)), ("drag", (ph3, ph4)),
                    ("drag", (ph4, ph5)), ("drag", (ph5, ph6)), ("drag", (ph6, ph1)),
                    ("drag", (ph1, ph2)), ("drag", (ph3, ph4)), ("drag", (ph5, ph6)),
                    ("drag", (ph3, ph_o)), ("mode", "O"), ("click", ph_o)
                ],
                "expected_smiles": "Oc1ccccc1" 
            },
            "S-Lactic Acid": {
                 "steps": [
                    ("mode", "Bond"),
                    ("drag", (sl_c1, sl_c2)), # C-C (Center)
                    ("drag", (sl_c2, sl_c3)), # C-C (Carboxyl)
                    ("drag", (sl_c3, sl_o1)), # C=O
                    ("drag", (sl_c3, sl_o1)), # Double
                    ("drag", (sl_c3, sl_o2)), # C-O
                    ("mode", "O"), ("click", sl_o1), ("click", sl_o2),
                    ("mode", "Wedge"),
                    ("drag", (sl_c2, sl_oh)), # Center to OH
                    ("mode", "O"), ("click", sl_oh)
                 ],
                 "expected_smiles": "C[C@H](O)C(=O)O"
            }
        }

    def run_test(self, molecule_name):
        logger.info(f"Starting ISOLATED test for {molecule_name}")
        recipe = self.molecules.get(molecule_name)
        if not recipe:
            logger.error(f"No recipe found for {molecule_name}")
            return

        # Initialize data storage
        self.test_atoms = {}
        self.test_bonds = {}
        
        # Reset canvas state
        self.canvas.atoms = {}
        self.canvas.bonds = {}
        self.canvas.update()
        
        self.execute_steps(recipe["steps"], 0)

    def execute_steps(self, steps, index):
        if index >= len(steps):
            self.verify_result()
            return
            
        step = steps[index]
        if len(step) == 2:
            action, params = step
        else:
            logger.error(f"Invalid step format at index {index}: {step}")
            QTimer.singleShot(self.step_delay, lambda: self.execute_steps(steps, index + 1))
            return

        logger.info(f"Action: {action} {params}")
        
        if action == "mode":
            self.canvas.mode = params
        elif action == "click":
            # Direct Data Injection for Click (Atom Placement)
            # Use params directly as grid coordinates are already snapped in recipe
            x, y = float(params[0]), float(params[1])
            key = (round(x, 2), round(y, 2))
            
            if self.canvas.mode in ["LonePair", "Radical", "Positive", "Negative", "H"]:
                if key in self.test_atoms:
                    atom_data = self.test_atoms[key]
                    if self.canvas.mode == "LonePair":
                        if "user_lp" not in atom_data: atom_data["user_lp"] = set()
                        atom_data["user_lp"].add(0)
                        atom_data["attach"][0] = ".."
            elif self.canvas.mode not in ["Bond", "Wedge", "Dash"]:
                # Place Atom
                # Check if atom already exists to preserve attachments
                if key not in self.test_atoms:
                    self.test_atoms[key] = {"main": self.canvas.mode, "attach": {}}
                else:
                    self.test_atoms[key]["main"] = self.canvas.mode
                logger.info(f"  [INJECT] Placed atom {self.canvas.mode} at {key}")
            
            # Sync to canvas
            self.canvas.atoms = self.test_atoms.copy()
            self.canvas.bonds = self.test_bonds.copy()
            self.canvas.update()
            self.canvas.on_molecule_updated()
            
        elif action == "drag":
            # Direct Data Injection for Bond
            # params is (start_tuple, end_tuple)
            if len(params) < 2: 
                logger.error(f"Invalid drag params length: {params}")
                return
            start_t, end_t = params
            
            key1 = (round(float(start_t[0]), 2), round(float(start_t[1]), 2))
            key2 = (round(float(end_t[0]), 2), round(float(end_t[1]), 2))
            
            if key1 != key2:
                bond_key = tuple(sorted((key1, key2)))
                # Force ensure atoms exist in local store
                if key1 not in self.test_atoms:
                    self.test_atoms[key1] = {"main": "C", "attach": {}}
                    logger.info(f"  [INJECT] Auto-created C atom at {key1}")
                if key2 not in self.test_atoms:
                    self.test_atoms[key2] = {"main": "C", "attach": {}}
                    logger.info(f"  [INJECT] Auto-created C atom at {key2}")
                
                if self.canvas.mode == "Bond":
                    current_order = self.test_bonds.get(bond_key, 0)
                    self.test_bonds[bond_key] = (current_order % 3) + 1
                    logger.info(f"  [INJECT] Created bond {bond_key} order {self.test_bonds[bond_key]}")
                elif self.canvas.mode in ["Wedge", "Dash"]:
                    p1 = QPointF(key1[0], key1[1])
                    p2 = QPointF(key2[0], key2[1])
                    self.test_bonds[bond_key] = (p1, p2, self.canvas.mode)
                    logger.info(f"  [INJECT] Created stereo bond {bond_key} type {self.canvas.mode}")
            
            # Sync to canvas
            self.canvas.atoms = self.test_atoms.copy()
            self.canvas.bonds = self.test_bonds.copy()
            self.canvas.update()
            self.canvas.on_molecule_updated()

        QTimer.singleShot(self.step_delay, lambda: self.execute_steps(steps, index + 1))

    def verify_result(self):
        # Force sync before verify
        self.canvas.atoms = self.test_atoms.copy()
        self.canvas.bonds = self.test_bonds.copy()
        
        logger.info(f"Canvas Atoms ({len(self.canvas.atoms)}): {list(self.canvas.atoms.keys())}")
        logger.info(f"Canvas Bonds ({len(self.canvas.bonds)}): {list(self.canvas.bonds.keys())}")
        
        smiles = self.canvas.get_smiles()
        logger.info(f"Generated SMILES: {smiles}")
        
        normalized_smiles = smiles.replace(".[HH]", "").replace(".[H]", "")
        logger.info(f"Normalized SMILES: {normalized_smiles}")

        with open("_interactive_test_result.json", "w") as f:
            json.dump({"smiles": normalized_smiles}, f)
            
        try:
            pixmap = self.canvas.grab()
            img_path = f"_interactive_capture_canvas.png"
            pixmap.save(img_path)
            logger.info(f"Captured canvas to {img_path}")
        except Exception as e:
            logger.error(f"Capture failed: {e}")

        QTimer.singleShot(1000, QApplication.instance().quit)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    target_molecule = "Ammonia"
    if len(sys.argv) > 1:
        target_molecule = sys.argv[1]
        
    tester = IsolatedCanvasTester()
    tester.show()
    
    QTimer.singleShot(2000, lambda: tester.run_test(target_molecule))
    sys.exit(app.exec())


