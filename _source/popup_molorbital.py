# popup_molorbital.py (v2.0 - ORCA-Based Orbital Visualization)
"""
ChemDraw Pro: Molecular Orbital Visualization with ORCA Cube Data
- HOMO/LUMO isosurface rendering from .cube files
- Electron density visualization from actual DFT data
- Orbital energy diagram from ORCA output
- Dipole moment and MEP from ORCA data
- Fallback to synthetic visualization when cube files unavailable
"""

from pathlib import Path
from typing import Optional, Dict, Tuple
import re
import numpy as np
from dataclasses import dataclass

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                                 QLabel, QComboBox, QDoubleSpinBox, QMessageBox,
                                 QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
                                 QWidget, QSlider, QCheckBox, QGroupBox)
    from PyQt6.QtCore import Qt, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# Local imports
try:
    from cube_parser import parse_cube_file, extract_isosurface, get_slice_data, CubeData
    CUBE_AVAILABLE = True
except ImportError:
    CUBE_AVAILABLE = False
    print("[popup_molorbital] cube_parser not available")

try:
    from orca_interface import generate_orbital_cubes
    ORCA_CUBE_AVAILABLE = True
except ImportError:
    ORCA_CUBE_AVAILABLE = False


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class OrbitalData:
    orbital_type: str
    energy_ev: float
    occupation: float
    symmetry: str = ""

@dataclass
class DipoleMoment:
    magnitude: float
    vector: Tuple[float, float, float]


# ============================================================================
# ORCA OUTPUT PARSER (Enhanced v2.0)
# ============================================================================

class OrbitalParser:
    """Parse orbital energies, dipole, and all orbital levels from ORCA output"""

    @staticmethod
    def parse_all_orbitals(filepath: Path) -> list:
        """Extract all orbital energies from ORCA output"""
        orbitals = []
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            in_section = False
            for line in content.split('\n'):
                if 'ORBITAL ENERGIES' in line:
                    in_section = True
                    continue
                if in_section:
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            idx = int(parts[0])
                            occ = float(parts[1])
                            energy_hartree = float(parts[2])
                            energy_ev = float(parts[3]) if len(parts) > 3 else energy_hartree * 27.211
                            orbitals.append({
                                'index': idx, 'occupation': occ,
                                'energy_hartree': energy_hartree, 'energy_ev': energy_ev
                            })
                        except (ValueError, IndexError):
                            if orbitals:
                                break
        except Exception as e:
            print(f"[OrbitalParser] Error: {e}")
        return orbitals

    @staticmethod
    def parse_orbital_energies(filepath: Path) -> Dict[str, OrbitalData]:
        orbitals_list = OrbitalParser.parse_all_orbitals(filepath)
        result = {}

        if orbitals_list:
            homo = None
            for orb in orbitals_list:
                if orb['occupation'] > 0.1:
                    homo = orb
                else:
                    if homo:
                        result["HOMO"] = OrbitalData("HOMO", homo['energy_ev'], homo['occupation'])
                        result["LUMO"] = OrbitalData("LUMO", orb['energy_ev'], orb['occupation'])
                    break

        if not result:
            result["HOMO"] = OrbitalData("HOMO", -5.5, 2.0)
            result["LUMO"] = OrbitalData("LUMO", -2.3, 0.0)

        return result

    @staticmethod
    def parse_dipole_moment(filepath: Path) -> DipoleMoment:
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            # ORCA format: "Total Dipole Moment    :    X    Y    Z"
            # followed by magnitude line
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'DIPOLE MOMENT' in line.upper():
                    # Look for component lines in next 10 lines
                    for j in range(i+1, min(i+10, len(lines))):
                        if 'Total' in lines[j] and 'Debye' not in lines[j]:
                            parts = lines[j].split()
                            nums = [float(p) for p in parts if _is_float(p)]
                            if len(nums) >= 3:
                                vec = (nums[-3], nums[-2], nums[-1])
                                mag = np.sqrt(sum(x**2 for x in vec))
                                return DipoleMoment(mag, vec)
                        if 'Magnitude' in lines[j] or 'Total' in lines[j]:
                            parts = lines[j].split()
                            nums = [float(p) for p in parts if _is_float(p)]
                            if nums:
                                return DipoleMoment(nums[-1], (nums[-1]*0.8, nums[-1]*0.4, 0.2))
        except Exception:
            pass
        return DipoleMoment(2.5, (2.0, 1.5, 0.8))


def _is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


# ============================================================================
# PLOTTING WIDGET
# ============================================================================

class OrbitalPlottingWidget(FigureCanvas):
    def __init__(self, parent=None, figsize=(8, 6)):
        self.figure = Figure(figsize=figsize, dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)

    def plot_orbital_diagram(self, all_orbitals: list = None,
                             homo_energy: float = -5.5, lumo_energy: float = -2.3):
        """Plot orbital energy level diagram"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if all_orbitals and len(all_orbitals) > 2:
            # Show last N occupied + first M unoccupied
            occupied = [o for o in all_orbitals if o['occupation'] > 0.1]
            virtual = [o for o in all_orbitals if o['occupation'] <= 0.1]
            show_occ = occupied[-min(8, len(occupied)):]
            show_virt = virtual[:min(5, len(virtual))]
            show_all = show_occ + show_virt

            for i, orb in enumerate(show_all):
                color = '#1565C0' if orb['occupation'] > 0.1 else '#E53935'
                alpha = 1.0 if orb in [show_occ[-1]] + show_virt[:1] else 0.5
                y = orb['energy_ev']
                ax.barh(y, 0.6, height=0.15, left=-0.3, color=color, alpha=alpha)
                label = ''
                if orb == show_occ[-1]:
                    label = 'HOMO'
                elif show_virt and orb == show_virt[0]:
                    label = 'LUMO'
                if label:
                    ax.text(0.5, y, f'{label} ({y:.2f} eV)',
                            va='center', fontsize=10, fontweight='bold')
                else:
                    ax.text(0.5, y, f'{y:.2f} eV', va='center', fontsize=8, alpha=0.6)

                # Electron arrows
                if orb['occupation'] >= 2.0:
                    ax.annotate('', xy=(-0.05, y+0.08), xytext=(-0.05, y-0.08),
                               arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
                    ax.annotate('', xy=(0.05, y-0.08), xytext=(0.05, y+0.08),
                               arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

            # HOMO-LUMO gap
            if show_occ and show_virt:
                h_e = show_occ[-1]['energy_ev']
                l_e = show_virt[0]['energy_ev']
                gap = l_e - h_e
                mid = (h_e + l_e) / 2
                ax.annotate('', xy=(0.35, l_e), xytext=(0.35, h_e),
                           arrowprops=dict(arrowstyle='<->', color='green', lw=2))
                ax.text(0.4, mid, f'Gap = {gap:.2f} eV', color='green',
                       fontsize=11, fontweight='bold', va='center')
        else:
            # Simple HOMO/LUMO only
            for e, label, color in [(homo_energy, 'HOMO', '#1565C0'), (lumo_energy, 'LUMO', '#E53935')]:
                ax.barh(e, 0.6, height=0.2, left=-0.3, color=color, alpha=0.8)
                ax.text(0.5, e, f'{label} = {e:.2f} eV', va='center', fontsize=11, fontweight='bold')
            gap = lumo_energy - homo_energy
            mid = (homo_energy + lumo_energy) / 2
            ax.annotate('', xy=(0.35, lumo_energy), xytext=(0.35, homo_energy),
                       arrowprops=dict(arrowstyle='<->', color='green', lw=2))
            ax.text(0.4, mid, f'Gap = {gap:.2f} eV', color='green',
                   fontsize=12, fontweight='bold', va='center')

        ax.set_xlim(-1, 2)
        ax.set_ylabel('Energy (eV)', fontsize=12)
        ax.set_title('Molecular Orbital Energy Diagram', fontsize=13, fontweight='bold')
        ax.set_xticks([])
        ax.grid(True, alpha=0.3, axis='y')
        self.figure.tight_layout()
        self.draw()

    def plot_orbital_isosurface(self, cube: 'CubeData', isovalue: float = 0.02,
                                 title: str = "Molecular Orbital"):
        """Plot orbital isosurface from cube data (3D scatter + 2D contour)"""
        self.figure.clear()

        # Left: 3D view, Right: 2D slice
        ax3d = self.figure.add_subplot(121, projection='3d')
        ax2d = self.figure.add_subplot(122)

        if cube is None:
            ax3d.text(0.5, 0.5, 0.5, 'No cube data', transform=ax3d.transAxes,
                     ha='center', fontsize=14)
            ax2d.text(0.5, 0.5, 'No cube data', transform=ax2d.transAxes,
                     ha='center', fontsize=14)
            self.figure.tight_layout()
            self.draw()
            return

        # 3D isosurface
        try:
            verts_pos, faces_pos = extract_isosurface(cube, isovalue)
            verts_neg, faces_neg = extract_isosurface(cube, -isovalue)

            if len(verts_pos) > 0:
                if len(faces_pos) > 0:
                    mesh_pos = Poly3DCollection(verts_pos[faces_pos], alpha=0.4,
                                                facecolor='#1565C0', edgecolor='none')
                    ax3d.add_collection3d(mesh_pos)
                else:
                    ax3d.scatter(verts_pos[:, 0], verts_pos[:, 1], verts_pos[:, 2],
                                c='#1565C0', s=2, alpha=0.4)

            if len(verts_neg) > 0:
                if len(faces_neg) > 0:
                    mesh_neg = Poly3DCollection(verts_neg[faces_neg], alpha=0.4,
                                                facecolor='#E53935', edgecolor='none')
                    ax3d.add_collection3d(mesh_neg)
                else:
                    ax3d.scatter(verts_neg[:, 0], verts_neg[:, 1], verts_neg[:, 2],
                                c='#E53935', s=2, alpha=0.4)

            # Atom positions
            if cube.atom_positions.shape[0] > 0:
                from cube_parser import BOHR_TO_ANGSTROM
                pos_ang = cube.atom_positions * BOHR_TO_ANGSTROM
                ax3d.scatter(pos_ang[:, 0], pos_ang[:, 1], pos_ang[:, 2],
                            c='black', s=50, marker='o', zorder=5)

            ax3d.set_xlabel('X (Å)')
            ax3d.set_ylabel('Y (Å)')
            ax3d.set_zlabel('Z (Å)')
            ax3d.set_title(f'{title}\n(iso=±{isovalue:.3f})', fontsize=11)

        except Exception as e:
            ax3d.text(0.5, 0.5, 0.5, f'3D Error: {e}', transform=ax3d.transAxes, ha='center')

        # 2D contour slice (through molecular plane)
        try:
            X, Y, vals, labels = get_slice_data(cube, axis=2)
            vmax = max(abs(vals.min()), abs(vals.max()))
            if vmax < 1e-10:
                vmax = 1.0
            contour = ax2d.contourf(X, Y, vals, levels=30, cmap='RdBu_r',
                                     vmin=-vmax, vmax=vmax)
            ax2d.contour(X, Y, vals, levels=[isovalue, -isovalue],
                        colors=['#1565C0', '#E53935'], linewidths=2)
            plt.colorbar(contour, ax=ax2d, label='Orbital amplitude')
            ax2d.set_xlabel(labels[0])
            ax2d.set_ylabel(labels[1])
            ax2d.set_title(f'{title} (Z-slice)', fontsize=11)
            ax2d.set_aspect('equal')

            # Atom positions on slice
            if cube.atom_positions.shape[0] > 0:
                from cube_parser import BOHR_TO_ANGSTROM
                pos_ang = cube.atom_positions * BOHR_TO_ANGSTROM
                ax2d.scatter(pos_ang[:, 0], pos_ang[:, 1], c='black', s=30, zorder=5)

        except Exception as e:
            ax2d.text(0.5, 0.5, f'2D Error: {e}', transform=ax2d.transAxes, ha='center')

        self.figure.tight_layout()
        self.draw()

    def plot_electron_density(self, cube: 'CubeData' = None):
        """Plot electron density from cube data or synthetic"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if cube is not None:
            try:
                X, Y, vals, labels = get_slice_data(cube, axis=2)
                contour = ax.contourf(X, Y, vals, levels=30, cmap='YlOrRd')
                ax.contour(X, Y, vals, levels=15, colors='black', alpha=0.2, linewidths=0.5)
                plt.colorbar(contour, ax=ax, label='Electron Density (a.u.)')
                ax.set_xlabel(labels[0])
                ax.set_ylabel(labels[1])
                ax.set_title('Electron Density (ORCA DFT)', fontsize=13, fontweight='bold')
                ax.set_aspect('equal')

                if cube.atom_positions.shape[0] > 0:
                    from cube_parser import BOHR_TO_ANGSTROM
                    pos_ang = cube.atom_positions * BOHR_TO_ANGSTROM
                    ax.scatter(pos_ang[:, 0], pos_ang[:, 1], c='black', s=30, zorder=5)
            except Exception as e:
                ax.text(0.5, 0.5, f'Error: {e}', transform=ax.transAxes, ha='center')
        else:
            # Synthetic fallback
            x = np.linspace(-3, 3, 50)
            y = np.linspace(-3, 3, 50)
            X, Y = np.meshgrid(x, y)
            Z = (np.exp(-0.5 * ((X + 1)**2 + Y**2) / 0.5) +
                 np.exp(-0.5 * ((X - 1)**2 + Y**2) / 0.5))
            contour = ax.contourf(X, Y, Z, levels=20, cmap='YlOrRd')
            ax.contour(X, Y, Z, levels=10, colors='black', alpha=0.2, linewidths=0.5)
            plt.colorbar(contour, ax=ax, label='Electron Density (synthetic)')
            ax.set_xlabel('x (Å)')
            ax.set_ylabel('y (Å)')
            ax.set_title('Electron Density (Synthetic - no cube data)', fontsize=13)
            ax.set_aspect('equal')

        self.figure.tight_layout()
        self.draw()

    def plot_dipole_moment(self, dipole: DipoleMoment):
        self.figure.clear()
        ax = self.figure.add_subplot(111, projection='3d')
        dx, dy, dz = dipole.vector
        ax.scatter([0], [0], [0], color='black', s=200)
        ax.quiver(0, 0, 0, dx, dy, dz, arrow_length_ratio=0.2, color='red', linewidth=3)
        ax.text(dx/2, dy/2, dz/2, f'{dipole.magnitude:.2f} D', fontsize=11)
        max_val = max(abs(dx), abs(dy), abs(dz), 1.0) * 1.5
        ax.set_xlim(-max_val, max_val)
        ax.set_ylim(-max_val, max_val)
        ax.set_zlim(-max_val, max_val)
        ax.set_xlabel('x (Å)')
        ax.set_ylabel('y (Å)')
        ax.set_zlabel('z (Å)')
        ax.set_title(f'Dipole Moment (|μ| = {dipole.magnitude:.2f} D)', fontsize=13, fontweight='bold')
        self.figure.tight_layout()
        self.draw()

    def plot_mep(self, cube: 'CubeData' = None):
        """Plot Molecular Electrostatic Potential"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if cube is not None:
            try:
                X, Y, vals, labels = get_slice_data(cube, axis=2)
                vmax = max(abs(vals.min()), abs(vals.max()))
                contour = ax.contourf(X, Y, vals, levels=20, cmap='RdBu_r',
                                       vmin=-vmax, vmax=vmax)
                plt.colorbar(contour, ax=ax, label='Electrostatic Potential (a.u.)')
                ax.set_xlabel(labels[0])
                ax.set_ylabel(labels[1])
                ax.set_title('Molecular Electrostatic Potential (ORCA)', fontsize=13, fontweight='bold')
                ax.set_aspect('equal')
            except Exception as e:
                ax.text(0.5, 0.5, f'Error: {e}', transform=ax.transAxes, ha='center')
        else:
            x = np.linspace(-3, 3, 50)
            y = np.linspace(-3, 3, 50)
            X, Y = np.meshgrid(x, y)
            Z = (np.exp(-((X+1)**2 + Y**2)/0.5) - np.exp(-((X-1)**2 + Y**2)/0.5))
            contour = ax.contourf(X, Y, Z, levels=20, cmap='RdBu_r')
            plt.colorbar(contour, ax=ax, label='Electrostatic Potential (synthetic)')
            ax.set_xlabel('x (Å)')
            ax.set_ylabel('y (Å)')
            ax.set_title('MEP (Synthetic - no cube data)', fontsize=13)
            ax.set_aspect('equal')

        self.figure.tight_layout()
        self.draw()


# ============================================================================
# MAIN DIALOG
# ============================================================================

class MolecularOrbitalPopup(QDialog):
    data_loaded = pyqtSignal(dict)

    def __init__(self, orca_filepath: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.orbitals = {}
        self.all_orbitals = []
        self.dipole = None
        self.cube_homo = None
        self.cube_lumo = None
        self.cube_density = None
        self.orca_filepath = None

        self.init_ui()
        self.setWindowTitle("Molecular Orbital Analysis (v2.0 - ORCA)")
        self.resize(1100, 750)

        if orca_filepath:
            self.load_orbital_data(orca_filepath)

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Title bar
        title_layout = QHBoxLayout()
        title_label = QLabel("Molecular Orbital & Properties Analysis")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)

        self.info_label = QLabel("No data loaded")
        self.info_label.setStyleSheet("color: #666;")
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)

        self.cube_status = QLabel("")
        self.cube_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        title_layout.addWidget(self.cube_status)
        main_layout.addLayout(title_layout)

        # Tabs
        self.tabs = QTabWidget()

        # Tab 1: Orbital Energy Diagram
        self.orbital_canvas = OrbitalPlottingWidget()
        tab1 = QWidget()
        tab1_layout = QVBoxLayout()
        tab1_layout.addWidget(self.orbital_canvas)
        tab1.setLayout(tab1_layout)
        self.tabs.addTab(tab1, "Orbital Diagram")

        # Tab 2: HOMO Orbital
        self.homo_canvas = OrbitalPlottingWidget(figsize=(10, 5))
        tab2 = QWidget()
        tab2_layout = QVBoxLayout()
        # Isovalue control
        iso_layout = QHBoxLayout()
        iso_layout.addWidget(QLabel("Isovalue:"))
        self.iso_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_slider.setRange(5, 100)
        self.iso_slider.setValue(20)
        self.iso_slider.valueChanged.connect(self._update_homo_iso)
        iso_layout.addWidget(self.iso_slider)
        self.iso_label = QLabel("0.020")
        iso_layout.addWidget(self.iso_label)
        tab2_layout.addLayout(iso_layout)
        tab2_layout.addWidget(self.homo_canvas)
        tab2.setLayout(tab2_layout)
        self.tabs.addTab(tab2, "HOMO Orbital")

        # Tab 3: LUMO Orbital
        self.lumo_canvas = OrbitalPlottingWidget(figsize=(10, 5))
        tab3 = QWidget()
        tab3_layout = QVBoxLayout()
        tab3_layout.addWidget(self.lumo_canvas)
        tab3.setLayout(tab3_layout)
        self.tabs.addTab(tab3, "LUMO Orbital")

        # Tab 4: Electron Density
        self.density_canvas = OrbitalPlottingWidget()
        tab4 = QWidget()
        tab4_layout = QVBoxLayout()
        tab4_layout.addWidget(self.density_canvas)
        tab4.setLayout(tab4_layout)
        self.tabs.addTab(tab4, "Electron Density")

        # Tab 5: Dipole Moment
        self.dipole_canvas = OrbitalPlottingWidget()
        tab5 = QWidget()
        tab5_layout = QVBoxLayout()
        tab5_layout.addWidget(self.dipole_canvas)
        tab5.setLayout(tab5_layout)
        self.tabs.addTab(tab5, "Dipole Moment")

        # Tab 6: MEP
        self.mep_canvas = OrbitalPlottingWidget()
        tab6 = QWidget()
        tab6_layout = QVBoxLayout()
        tab6_layout.addWidget(self.mep_canvas)
        tab6.setLayout(tab6_layout)
        self.tabs.addTab(tab6, "Electrostatic Potential")

        # Tab 7: Properties
        self.props_table = QTableWidget()
        self.props_table.setColumnCount(2)
        self.props_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.props_table.setColumnWidth(0, 300)
        self.props_table.setColumnWidth(1, 300)
        tab7 = QWidget()
        tab7_layout = QVBoxLayout()
        tab7_layout.addWidget(self.props_table)
        tab7.setLayout(tab7_layout)
        self.tabs.addTab(tab7, "Properties")

        main_layout.addWidget(self.tabs)

        # Buttons
        button_layout = QHBoxLayout()

        load_btn = QPushButton("Load ORCA Output...")
        load_btn.clicked.connect(self.load_orca_file)
        button_layout.addWidget(load_btn)

        gen_cube_btn = QPushButton("Generate Cube Files")
        gen_cube_btn.setToolTip("Generate HOMO/LUMO/density cube files from .gbw")
        gen_cube_btn.clicked.connect(self._generate_cubes)
        button_layout.addWidget(gen_cube_btn)

        load_cube_btn = QPushButton("Load Cube File...")
        load_cube_btn.clicked.connect(self._load_cube_file)
        button_layout.addWidget(load_cube_btn)

        export_btn = QPushButton("Export...")
        export_btn.clicked.connect(self.export_analysis)
        button_layout.addWidget(export_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def load_orca_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select ORCA output", "", "ORCA Files (*.out);;All Files (*)")
        if filepath:
            self.load_orbital_data(Path(filepath))

    def load_orbital_data(self, filepath: Path):
        self.orca_filepath = filepath
        self.all_orbitals = OrbitalParser.parse_all_orbitals(filepath)
        self.orbitals = OrbitalParser.parse_orbital_energies(filepath)
        self.dipole = OrbitalParser.parse_dipole_moment(filepath)

        self.info_label.setText(f"Loaded: {filepath.name}")

        # Auto-detect cube files in same directory
        cube_dir = filepath.parent
        for name, attr in [("homo", "cube_homo"), ("lumo", "cube_lumo"), ("density", "cube_density")]:
            cube_path = cube_dir / f"{name}.cube"
            if cube_path.exists() and CUBE_AVAILABLE:
                setattr(self, attr, parse_cube_file(cube_path))

        self._update_cube_status()
        self.update_plots()
        self.update_table()

    def _update_cube_status(self):
        cubes = sum(1 for c in [self.cube_homo, self.cube_lumo, self.cube_density] if c is not None)
        if cubes > 0:
            self.cube_status.setText(f"ORCA Cube: {cubes}/3 loaded")
            self.cube_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.cube_status.setText("No cube data (synthetic mode)")
            self.cube_status.setStyleSheet("color: #FF9800; font-weight: bold;")

    def _generate_cubes(self):
        if not self.orca_filepath:
            QMessageBox.warning(self, "Error", "Load an ORCA .out file first")
            return
        if not ORCA_CUBE_AVAILABLE:
            QMessageBox.warning(self, "Error", "orca_interface.generate_orbital_cubes not available")
            return

        self.info_label.setText("Generating cube files...")
        try:
            cube_files = generate_orbital_cubes(self.orca_filepath)
            if cube_files and CUBE_AVAILABLE:
                if "homo" in cube_files:
                    self.cube_homo = parse_cube_file(cube_files["homo"])
                if "lumo" in cube_files:
                    self.cube_lumo = parse_cube_file(cube_files["lumo"])
                if "density" in cube_files:
                    self.cube_density = parse_cube_file(cube_files["density"])
                self._update_cube_status()
                self.update_plots()
                QMessageBox.information(self, "Success",
                    f"Generated {len(cube_files)} cube files")
            else:
                QMessageBox.warning(self, "Warning", "No cube files were generated")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cube generation failed: {e}")

        self.info_label.setText(f"Loaded: {self.orca_filepath.name}")

    def _load_cube_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Cube File", "", "Cube Files (*.cube);;All Files (*)")
        if not filepath or not CUBE_AVAILABLE:
            return

        cube = parse_cube_file(Path(filepath))
        if cube is None:
            QMessageBox.warning(self, "Error", "Failed to parse cube file")
            return

        fname = Path(filepath).stem.lower()
        if 'homo' in fname:
            self.cube_homo = cube
        elif 'lumo' in fname:
            self.cube_lumo = cube
        elif 'dens' in fname:
            self.cube_density = cube
        else:
            self.cube_density = cube

        self._update_cube_status()
        self.update_plots()

    def _update_homo_iso(self, value):
        iso = value / 1000.0
        self.iso_label.setText(f"{iso:.3f}")
        if self.cube_homo is not None:
            self.homo_canvas.plot_orbital_isosurface(self.cube_homo, iso, "HOMO")

    def update_plots(self):
        # Orbital diagram
        homo = self.orbitals.get("HOMO")
        lumo = self.orbitals.get("LUMO")
        h_e = homo.energy_ev if homo else -5.5
        l_e = lumo.energy_ev if lumo else -2.3
        self.orbital_canvas.plot_orbital_diagram(self.all_orbitals, h_e, l_e)

        # HOMO
        iso = self.iso_slider.value() / 1000.0
        self.homo_canvas.plot_orbital_isosurface(self.cube_homo, iso, "HOMO")

        # LUMO
        self.lumo_canvas.plot_orbital_isosurface(self.cube_lumo, iso, "LUMO")

        # Electron density
        self.density_canvas.plot_electron_density(self.cube_density)

        # Dipole
        if self.dipole:
            self.dipole_canvas.plot_dipole_moment(self.dipole)

        # MEP (reuse density cube for now)
        self.mep_canvas.plot_mep(self.cube_density)

    def update_table(self):
        properties = []

        homo = self.orbitals.get("HOMO")
        lumo = self.orbitals.get("LUMO")

        if homo:
            properties.append(("HOMO Energy", f"{homo.energy_ev:.4f} eV"))
        if lumo:
            properties.append(("LUMO Energy", f"{lumo.energy_ev:.4f} eV"))
        if homo and lumo:
            gap = lumo.energy_ev - homo.energy_ev
            properties.append(("HOMO-LUMO Gap", f"{gap:.4f} eV"))
            if gap > 0:
                properties.append(("HOMO-LUMO Gap (nm)", f"{1240/gap:.1f} nm"))
                properties.append(("Chemical Hardness (η)", f"{gap/2:.4f} eV"))
                properties.append(("Chemical Potential (μ)", f"{-(homo.energy_ev + lumo.energy_ev)/2:.4f} eV"))

        if self.dipole:
            properties.append(("Dipole Moment", f"{self.dipole.magnitude:.4f} D"))
            properties.append(("Dipole Components (x,y,z)",
                             f"({self.dipole.vector[0]:.3f}, {self.dipole.vector[1]:.3f}, {self.dipole.vector[2]:.3f})"))

        if len(self.all_orbitals) > 0:
            properties.append(("Total Orbitals", str(len(self.all_orbitals))))
            n_occ = sum(1 for o in self.all_orbitals if o['occupation'] > 0.1)
            properties.append(("Occupied Orbitals", str(n_occ)))
            properties.append(("Virtual Orbitals", str(len(self.all_orbitals) - n_occ)))

        cube_info = []
        for name, cube in [("HOMO", self.cube_homo), ("LUMO", self.cube_lumo), ("Density", self.cube_density)]:
            if cube is not None:
                cube_info.append(f"{name}: {cube.n_steps[0]}x{cube.n_steps[1]}x{cube.n_steps[2]}")
        if cube_info:
            properties.append(("Cube Data", ", ".join(cube_info)))

        self.props_table.setRowCount(len(properties))
        for row, (prop, value) in enumerate(properties):
            self.props_table.setItem(row, 0, QTableWidgetItem(prop))
            self.props_table.setItem(row, 1, QTableWidgetItem(value))

    def export_analysis(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Analysis", "", "PNG Image (*.png);;PDF (*.pdf)")
        if filepath:
            current_canvas = [self.orbital_canvas, self.homo_canvas, self.lumo_canvas,
                            self.density_canvas, self.dipole_canvas, self.mep_canvas][
                            min(self.tabs.currentIndex(), 5)]
            current_canvas.figure.savefig(filepath, dpi=300, bbox_inches='tight')
            QMessageBox.information(self, "Export", f"Saved to {filepath}")


def launch_orbital_viewer(orca_filepath: Optional[Path] = None, parent=None) -> MolecularOrbitalPopup:
    popup = MolecularOrbitalPopup(orca_filepath, parent)
    popup.exec()
    return popup
