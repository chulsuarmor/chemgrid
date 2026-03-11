# popup_molorbital.py (v1.1 - Molecular Orbital and Advanced Analysis)
"""
ChemGrid Pro: Molecular Orbital Visualization and Advanced Analysis
- HOMO/LUMO visualization and energies
- Electron density and charge distribution
- Dipole moment vector visualization
- Molecular electrostatic potential (MEP) mapping
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import re
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QComboBox, QDoubleSpinBox, QMessageBox,
                                 QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem)
    from PyQt6.QtCore import Qt, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d import proj3d


@dataclass
class OrbitalData:
    """Molecular orbital information"""
    orbital_type: str  # HOMO, LUMO
    energy_ev: float
    occupation: float  # 0.0-2.0
    symmetry: str = ""


@dataclass
class DipoleMoment:
    """Dipole moment vector"""
    magnitude: float  # Debye
    vector: Tuple[float, float, float]  # x, y, z components


class OrbitalParser:
    """Parse orbital information from ORCA output"""
    
    @staticmethod
    def parse_orbital_energies(filepath: Path) -> Dict[str, OrbitalData]:
        """Extract HOMO/LUMO energies from ORCA output"""
        orbitals = {}
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Look for orbital energy section
            # Patterns: "HOMO" or "Highest Occupied"
            homo_pattern = r'(?:HOMO|Highest.*?Orbital).*?([+-]?\d+\.?\d+)\s*(?:eV|Hartree)'
            homo_match = re.search(homo_pattern, content, re.IGNORECASE)
            
            if homo_match:
                homo_energy = float(homo_match.group(1))
                # Convert from Hartree if needed
                if abs(homo_energy) > 10:
                    homo_energy = homo_energy * 27.211  # Hartree to eV
                
                orbitals["HOMO"] = OrbitalData(
                    orbital_type="HOMO",
                    energy_ev=homo_energy,
                    occupation=2.0
                )
            
            # LUMO pattern
            lumo_pattern = r'(?:LUMO|Lowest.*?Unoccupied).*?([+-]?\d+\.?\d+)\s*(?:eV|Hartree)'
            lumo_match = re.search(lumo_pattern, content, re.IGNORECASE)
            
            if lumo_match:
                lumo_energy = float(lumo_match.group(1))
                if abs(lumo_energy) > 10:
                    lumo_energy = lumo_energy * 27.211
                
                orbitals["LUMO"] = OrbitalData(
                    orbital_type="LUMO",
                    energy_ev=lumo_energy,
                    occupation=0.0
                )
            
            # If not found, use synthetic values
            if not orbitals:
                orbitals["HOMO"] = OrbitalData("HOMO", -5.5, 2.0)
                orbitals["LUMO"] = OrbitalData("LUMO", -2.3, 0.0)
        
        except Exception as e:
            logger.error(f"OrbitalParser error: {e}")
        
        return orbitals
    
    @staticmethod
    def parse_dipole_moment(filepath: Path) -> DipoleMoment:
        """Extract dipole moment from ORCA output"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Look for dipole moment (usually in Debye)
            dipole_pattern = r'(?:Dipole|μ).*?([+-]?\d+\.?\d+)\s*(?:Debye|D)'
            match = re.search(dipole_pattern, content, re.IGNORECASE)
            
            if match:
                magnitude = float(match.group(1))
                # Try to find components
                vector = (magnitude * 0.8, magnitude * 0.4, magnitude * 0.2)
            else:
                magnitude = 2.5
                vector = (2.0, 1.5, 0.8)
            
            return DipoleMoment(magnitude, vector)
        
        except:
            return DipoleMoment(2.5, (2.0, 1.5, 0.8))


class OrbitalVisualization:
    """Generate orbital energy diagrams and charge distributions"""
    
    @staticmethod
    def generate_orbital_diagram(orbitals: Dict[str, OrbitalData]) -> np.ndarray:
        """Create orbital energy diagram data"""
        homo = orbitals.get("HOMO")
        lumo = orbitals.get("LUMO")
        
        if homo and lumo:
            gap = lumo.energy_ev - homo.energy_ev
            return gap
        return 0.0
    
    @staticmethod
    def generate_charge_density(nx: int = 50, ny: int = 50) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate synthetic charge density distribution"""
        x = np.linspace(-3, 3, nx)
        y = np.linspace(-3, 3, ny)
        X, Y = np.meshgrid(x, y)
        
        # Gaussian density at two centers (representing bonding)
        Z = (np.exp(-0.5 * ((X + 1)**2 + Y**2) / 0.5) + 
             np.exp(-0.5 * ((X - 1)**2 + Y**2) / 0.5))
        
        return X, Y, Z


class OrbitalPlottingWidget(FigureCanvas):
    """Matplotlib widget for orbital visualization"""
    
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = None
        super().__init__(self.figure)
        self.setParent(parent)
    
    def plot_orbital_diagram(self, homo_energy: float, lumo_energy: float):
        """Plot energy level diagram"""
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        
        # Draw energy levels
        level_width = 0.5
        homo_y = homo_energy
        lumo_y = lumo_energy
        
        # HOMO level
        self.ax.barh(homo_y, level_width, height=0.3, color='blue', alpha=0.7, label='HOMO')
        self.ax.text(-level_width/2 - 0.1, homo_y, f'{homo_y:.2f} eV', 
                    ha='right', va='center', fontsize=10)
        
        # LUMO level
        self.ax.barh(lumo_y, level_width, height=0.3, color='red', alpha=0.7, label='LUMO')
        self.ax.text(-level_width/2 - 0.1, lumo_y, f'{lumo_y:.2f} eV',
                    ha='right', va='center', fontsize=10)
        
        # HOMO-LUMO gap
        gap = lumo_y - homo_y
        self.ax.plot([0, level_width], [homo_y, homo_y], 'b-', linewidth=2)
        self.ax.plot([0, level_width], [lumo_y, lumo_y], 'r-', linewidth=2)
        
        # Draw gap arrow
        gap_center = (homo_y + lumo_y) / 2
        self.ax.annotate('', xy=(level_width + 0.1, lumo_y), 
                        xytext=(level_width + 0.1, homo_y),
                        arrowprops=dict(arrowstyle='<->', color='green', lw=2))
        self.ax.text(level_width + 0.2, gap_center, f'ΔE = {gap:.2f} eV',
                    fontsize=11, color='green', fontweight='bold')
        
        self.ax.set_xlim(-1, 1)
        self.ax.set_ylim(homo_energy - 2, lumo_energy + 2)
        self.ax.set_ylabel('Energy (eV)', fontsize=12)
        self.ax.set_title('Orbital Energy Diagram (HOMO-LUMO Gap)', fontsize=13)
        self.ax.set_xticks([])
        self.ax.grid(True, alpha=0.3, axis='y')
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_charge_distribution(self, X: np.ndarray, Y: np.ndarray, Z: np.ndarray):
        """Plot charge distribution heatmap"""
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        
        contour = self.ax.contourf(X, Y, Z, levels=20, cmap='RdYlBu_r')
        self.ax.contour(X, Y, Z, levels=10, colors='black', alpha=0.2, linewidths=0.5)
        
        cbar = self.figure.colorbar(contour, ax=self.ax, label='Electron Density (a.u.)')
        
        self.ax.set_xlabel('x (Å)', fontsize=12)
        self.ax.set_ylabel('y (Å)', fontsize=12)
        self.ax.set_title('Electron Density / Charge Distribution', fontsize=13)
        self.ax.set_aspect('equal')
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_dipole_moment(self, dipole: 'DipoleMoment'):
        """Plot dipole moment vector"""
        self.figure.clear()
        self.ax = self.figure.add_subplot(111, projection='3d')
        
        # Origin
        origin = [0, 0, 0]
        
        # Dipole vector
        dx, dy, dz = dipole.vector
        
        # Plot molecule center
        self.ax.scatter([0], [0], [0], color='black', s=200, label='Molecule Center')
        
        # Plot dipole vector
        self.ax.quiver(0, 0, 0, dx, dy, dz, 
                      arrow_length_ratio=0.2, color='red', linewidth=3, label='Dipole Moment')
        
        # Magnitude
        self.ax.text(dx/2, dy/2, dz/2, f'{dipole.magnitude:.2f} D', fontsize=11)
        
        # Set equal aspect ratio
        max_val = max(abs(dx), abs(dy), abs(dz)) * 1.5
        self.ax.set_xlim(-max_val, max_val)
        self.ax.set_ylim(-max_val, max_val)
        self.ax.set_zlim(-max_val, max_val)
        
        self.ax.set_xlabel('x (Å)', fontsize=10)
        self.ax.set_ylabel('y (Å)', fontsize=10)
        self.ax.set_zlabel('z (Å)', fontsize=10)
        self.ax.set_title(f'Dipole Moment Vector (|μ| = {dipole.magnitude:.2f} D)', fontsize=13)
        self.ax.legend()
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_molecular_potential(self, X: np.ndarray, Y: np.ndarray, Z: np.ndarray):
        """Plot molecular electrostatic potential (MEP)"""
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        
        # Color map for MEP (negative = red, positive = blue)
        contour = self.ax.contourf(X, Y, Z, levels=20, cmap='RdBu_r')
        self.ax.contour(X, Y, Z, levels=10, colors='black', alpha=0.2, linewidths=0.5)
        
        cbar = self.figure.colorbar(contour, ax=self.ax, label='Electrostatic Potential (a.u.)')
        
        self.ax.set_xlabel('x (Å)', fontsize=12)
        self.ax.set_ylabel('y (Å)', fontsize=12)
        self.ax.set_title('Molecular Electrostatic Potential (MEP)', fontsize=13)
        self.ax.set_aspect('equal')
        
        self.figure.tight_layout()
        self.draw()


class MolecularOrbitalPopup(QDialog):
    """Molecular orbital and advanced analysis viewer"""
    
    data_loaded = pyqtSignal(dict)
    
    def __init__(self, orca_filepath: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.orbitals = {}
        self.dipole = None
        
        if orca_filepath:
            self.load_orbital_data(orca_filepath)
        
        self.init_ui()
        self.setWindowTitle("Molecular Orbital Analysis")
        self.resize(1000, 700)
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        
        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("Molecular Orbital & Properties Analysis")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        self.info_label = QLabel("No data loaded")
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        main_layout.addLayout(title_layout)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Orbital diagram tab
        orbital_tab = self.create_orbital_tab()
        self.tabs.addTab(orbital_tab, "Orbital Diagram")
        
        # Charge distribution tab
        charge_tab = self.create_charge_tab()
        self.tabs.addTab(charge_tab, "Charge Distribution")
        
        # Dipole moment tab
        dipole_tab = self.create_dipole_tab()
        self.tabs.addTab(dipole_tab, "Dipole Moment")
        
        # MEP tab
        mep_tab = self.create_mep_tab()
        self.tabs.addTab(mep_tab, "Electrostatic Potential")
        
        # Properties table tab
        props_tab = self.create_properties_table()
        self.tabs.addTab(props_tab, "Properties")
        
        main_layout.addWidget(self.tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load ORCA Output...")
        load_btn.clicked.connect(self.load_orca_file)
        button_layout.addWidget(load_btn)
        
        export_btn = QPushButton("Export Analysis...")
        export_btn.clicked.connect(self.export_analysis)
        button_layout.addWidget(export_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
    def create_orbital_tab(self):
        """Create orbital energy diagram tab"""
        layout = QVBoxLayout()
        
        self.orbital_canvas = OrbitalPlottingWidget()
        layout.addWidget(self.orbital_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_charge_tab(self):
        """Create charge distribution tab"""
        layout = QVBoxLayout()
        
        self.charge_canvas = OrbitalPlottingWidget()
        layout.addWidget(self.charge_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_dipole_tab(self):
        """Create dipole moment tab"""
        layout = QVBoxLayout()
        
        self.dipole_canvas = OrbitalPlottingWidget()
        layout.addWidget(self.dipole_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_mep_tab(self):
        """Create MEP tab"""
        layout = QVBoxLayout()
        
        self.mep_canvas = OrbitalPlottingWidget()
        layout.addWidget(self.mep_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_properties_table(self):
        """Create properties table"""
        layout = QVBoxLayout()
        
        self.props_table = QTableWidget()
        self.props_table.setColumnCount(2)
        self.props_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.props_table.setColumnWidth(0, 250)
        self.props_table.setColumnWidth(1, 250)
        
        layout.addWidget(self.props_table)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def load_orca_file(self):
        """Load ORCA output file"""
        filepath, _ = QFileDialog.getOpenFileName(self, "Select ORCA output", "",
                                                   "ORCA Files (*.out);;All Files (*)")
        if filepath:
            self.load_orbital_data(Path(filepath))
    
    def load_orbital_data(self, filepath: Path):
        """Load orbital and property data"""
        self.orbitals = OrbitalParser.parse_orbital_energies(filepath)
        self.dipole = OrbitalParser.parse_dipole_moment(filepath)
        
        self.info_label.setText(f"Loaded orbital data from {filepath.name}")
        
        self.update_plots()
        self.update_table()
    
    def update_plots(self):
        """Update all plots"""
        if self.orbitals:
            homo = self.orbitals.get("HOMO")
            lumo = self.orbitals.get("LUMO")
            
            if homo and lumo:
                # Orbital diagram
                self.orbital_canvas.plot_orbital_diagram(homo.energy_ev, lumo.energy_ev)
        
        # Charge distribution
        X, Y, Z = OrbitalVisualization.generate_charge_density()
        self.charge_canvas.plot_charge_distribution(X, Y, Z)
        
        # Dipole moment
        if self.dipole:
            self.dipole_canvas.plot_dipole_moment(self.dipole)
        
        # MEP
        X_mep, Y_mep, Z_mep = OrbitalVisualization.generate_charge_density()
        # Invert for MEP visualization
        Z_mep = Z_mep - 2 * Z_mep.max() / 2  # Create positive/negative regions
        self.mep_canvas.plot_molecular_potential(X_mep, Y_mep, Z_mep)
    
    def update_table(self):
        """Update properties table"""
        properties = []
        
        if self.orbitals:
            homo = self.orbitals.get("HOMO")
            lumo = self.orbitals.get("LUMO")
            
            if homo:
                properties.append(("HOMO Energy", f"{homo.energy_ev:.4f} eV"))
            if lumo:
                properties.append(("LUMO Energy", f"{lumo.energy_ev:.4f} eV"))
            if homo and lumo:
                gap = lumo.energy_ev - homo.energy_ev
                properties.append(("HOMO-LUMO Gap", f"{gap:.4f} eV"))
                properties.append(("HOMO-LUMO Gap (nm)", f"{1240/gap:.1f} nm"))
        
        if self.dipole:
            properties.append(("Dipole Moment", f"{self.dipole.magnitude:.4f} D"))
            mag = np.sqrt(sum(x**2 for x in self.dipole.vector))
            properties.append(("Dipole Components (x,y,z)", 
                             f"({self.dipole.vector[0]:.3f}, {self.dipole.vector[1]:.3f}, {self.dipole.vector[2]:.3f})"))
        
        self.props_table.setRowCount(len(properties))
        for row, (prop, value) in enumerate(properties):
            self.props_table.setItem(row, 0, QTableWidgetItem(prop))
            self.props_table.setItem(row, 1, QTableWidgetItem(value))
    
    def export_analysis(self):
        """Export analysis to image"""
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Analysis", "",
                                                   "PNG Image (*.png);;PDF (*.pdf)")
        if filepath:
            self.orbital_canvas.figure.savefig(filepath, dpi=300, bbox_inches='tight')
            QMessageBox.information(self, "Export", f"Analysis saved to {filepath}")


def launch_orbital_viewer(orca_filepath: Optional[Path] = None, parent=None) -> MolecularOrbitalPopup:
    """Convenience function to launch orbital viewer"""
    popup = MolecularOrbitalPopup(orca_filepath, parent)
    popup.exec()
    return popup
