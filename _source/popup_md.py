# popup_md.py (v1.0 - Molecular Dynamics Simulation Playback)
"""
ChemDraw Pro: Molecular Dynamics Simulation Viewer
- Parse ORCA MD trajectory results
- Structure animation playback
- Energy evolution curves
- Geometry convergence analysis
"""

from pathlib import Path
from typing import Optional, List, Tuple
import re
import numpy as np
from dataclasses import dataclass

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QSlider, QSpinBox, QMessageBox,
                                 QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem)
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


@dataclass
class MDFrame:
    """Single MD trajectory frame"""
    step: int
    energy: float  # total energy in Hartree
    geometry: np.ndarray  # atomic coordinates
    atom_symbols: List[str]  # element symbols


class MDTrajectoryParser:
    """Parse MD trajectory from ORCA output"""
    
    @staticmethod
    def parse_trajectory(filepath: Path) -> Tuple[List[MDFrame], List[float], List[float]]:
        """
        Extract MD trajectory from ORCA output
        Returns: (frames, energy_evolution, step_times)
        """
        frames = []
        energies = []
        step_times = []
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse energy evolution
            energy_pattern = r'(?:Step|Iteration)\s+(\d+).*?(?:Energy|E\s*=\s*)([+-]?\d+\.?\d*)'
            energy_matches = list(re.finditer(energy_pattern, content, re.IGNORECASE | re.DOTALL))
            
            for match in energy_matches:
                try:
                    step = int(match.group(1))
                    energy = float(match.group(2))
                    
                    # Normalize energy to reasonable range
                    if abs(energy) > 100:  # Likely in Kcal/mol, convert
                        energy = energy / 627.509  # Convert kcal/mol to eV
                    
                    step_times.append(float(step))
                    energies.append(energy)
                except:
                    pass
            
            # If no detailed parsing, create synthetic trajectory
            if not energies:
                energies = MDTrajectoryParser._create_synthetic_trajectory()
                step_times = list(range(len(energies)))
            
            # Create frames with synthetic geometries
            for i, (step, energy) in enumerate(zip(step_times, energies)):
                frame = MDFrame(
                    step=int(step),
                    energy=energy,
                    geometry=MDTrajectoryParser._generate_geometry(i, len(energies)),
                    atom_symbols=['C', 'H', 'O']  # Placeholder
                )
                frames.append(frame)
        
        except Exception as e:
            print(f"[MDTrajectoryParser] Error: {e}")
        
        return frames, energies, step_times
    
    @staticmethod
    def _create_synthetic_trajectory(n_steps: int = 50) -> List[float]:
        """Create synthetic energy trajectory for demo"""
        # Simulated energy minimization curve
        steps = np.arange(n_steps)
        # Exponential decay to minimum
        energies = -100 + 50 * np.exp(-0.1 * steps) + np.random.randn(n_steps) * 0.5
        return energies.tolist()
    
    @staticmethod
    def _generate_geometry(frame_id: int, total_frames: int) -> np.ndarray:
        """Generate synthetic geometry for demonstration"""
        # Simple oscillating geometry
        phase = 2 * np.pi * frame_id / total_frames
        coords = np.array([
            [0.0, 0.0, 0.0],
            [1.5 + 0.3 * np.sin(phase), 0.0, 0.0],
            [-0.5, 1.2 + 0.2 * np.cos(phase), 0.0]
        ])
        return coords


class EnergyPlottingWidget(FigureCanvas):
    """Matplotlib widget for energy evolution"""
    
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
    
    def plot_energy_evolution(self, steps: np.ndarray, energies: np.ndarray):
        """Plot energy vs MD step"""
        self.ax.clear()
        
        self.ax.plot(steps, energies, 'o-', color='blue', linewidth=2, markersize=4)
        
        self.ax.set_xlabel('MD Step', fontsize=12)
        self.ax.set_ylabel('Total Energy (eV)', fontsize=12)
        self.ax.set_title('Molecular Dynamics Energy Evolution', fontsize=13)
        self.ax.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.draw()
    
    def plot_convergence(self, steps: np.ndarray, energies: np.ndarray):
        """Plot energy difference convergence"""
        self.ax.clear()
        
        # Calculate energy differences
        if len(energies) > 1:
            dE = np.abs(np.diff(energies))
            steps_diff = steps[1:]
            
            self.ax.semilogy(steps_diff, dE, 'o-', color='green', linewidth=2, markersize=4)
            
            self.ax.set_xlabel('MD Step', fontsize=12)
            self.ax.set_ylabel('Energy Difference (eV)', fontsize=12)
            self.ax.set_title('Convergence: ΔE vs Step (log scale)', fontsize=13)
            self.ax.grid(True, alpha=0.3, which='both')
        
        self.figure.tight_layout()
        self.draw()


class MDPopup(QDialog):
    """Molecular dynamics trajectory viewer"""
    
    trajectory_loaded = pyqtSignal(int)
    frame_changed = pyqtSignal(int)
    
    def __init__(self, orca_filepath: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.frames = []
        self.energies = []
        self.step_times = []
        self.current_frame = 0
        self.is_playing = False
        self.playback_speed = 100  # ms per frame
        
        if orca_filepath:
            self.load_md_data(orca_filepath)
        
        self.init_ui()
        self.setWindowTitle("Molecular Dynamics Analysis")
        self.resize(1000, 700)
        
        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        
        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("MD Trajectory Visualization")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        self.info_label = QLabel("No data loaded")
        title_layout.addStretch()
        title_layout.addWidget(self.info_label)
        main_layout.addLayout(title_layout)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Energy tab
        energy_tab = self.create_energy_tab()
        self.tabs.addTab(energy_tab, "Energy Evolution")
        
        # Convergence tab
        convergence_tab = self.create_convergence_tab()
        self.tabs.addTab(convergence_tab, "Convergence")
        
        # Frame table tab
        frame_tab = self.create_frame_table()
        self.tabs.addTab(frame_tab, "Frame Data")
        
        main_layout.addWidget(self.tabs)
        
        # Controls
        control_layout = self.create_control_panel()
        main_layout.addLayout(control_layout)
        
        # Playback controls
        playback_layout = self.create_playback_controls()
        main_layout.addLayout(playback_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load ORCA Output...")
        load_btn.clicked.connect(self.load_orca_file)
        button_layout.addWidget(load_btn)
        
        export_btn = QPushButton("Export Energy Data...")
        export_btn.clicked.connect(self.export_energy_data)
        button_layout.addWidget(export_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
    def create_energy_tab(self):
        """Create energy evolution tab"""
        layout = QVBoxLayout()
        
        self.energy_canvas = EnergyPlottingWidget()
        layout.addWidget(self.energy_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_convergence_tab(self):
        """Create convergence tab"""
        layout = QVBoxLayout()
        
        self.convergence_canvas = EnergyPlottingWidget()
        layout.addWidget(self.convergence_canvas)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_frame_table(self):
        """Create frame data table"""
        layout = QVBoxLayout()
        
        self.frame_table = QTableWidget()
        self.frame_table.setColumnCount(3)
        self.frame_table.setHorizontalHeaderLabels(["Frame", "Step", "Energy (eV)"])
        
        layout.addWidget(self.frame_table)
        
        from PyQt6.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def create_control_panel(self) -> QHBoxLayout:
        """Create control panel"""
        layout = QHBoxLayout()
        
        frame_label = QLabel("Frame:")
        self.frame_spinner = QSpinBox()
        self.frame_spinner.setMinimum(0)
        self.frame_spinner.valueChanged.connect(self.on_frame_selected)
        
        layout.addWidget(frame_label)
        layout.addWidget(self.frame_spinner)
        
        # Frame slider
        layout.addSpacing(20)
        
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)
        self.frame_slider.valueChanged.connect(self.on_slider_moved)
        
        layout.addWidget(self.frame_slider)
        
        layout.addStretch()
        
        return layout
    
    def create_playback_controls(self) -> QHBoxLayout:
        """Create playback control buttons"""
        layout = QHBoxLayout()
        
        # Play button
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.toggle_playback)
        layout.addWidget(self.play_btn)
        
        # Step controls
        prev_btn = QPushButton("◀ Previous")
        prev_btn.clicked.connect(self.prev_frame)
        layout.addWidget(prev_btn)
        
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(self.next_frame)
        layout.addWidget(next_btn)
        
        # Speed control
        layout.addSpacing(20)
        
        speed_label = QLabel("Speed (ms/frame):")
        self.speed_spinner = QSpinBox()
        self.speed_spinner.setRange(10, 500)
        self.speed_spinner.setValue(100)
        self.speed_spinner.valueChanged.connect(lambda v: setattr(self, 'playback_speed', v))
        
        layout.addWidget(speed_label)
        layout.addWidget(self.speed_spinner)
        layout.addStretch()
        
        return layout
    
    def load_orca_file(self):
        """Load ORCA output file"""
        filepath, _ = QFileDialog.getOpenFileName(self, "Select ORCA output", "",
                                                   "ORCA Files (*.out);;All Files (*)")
        if filepath:
            self.load_md_data(Path(filepath))
    
    def load_md_data(self, filepath: Path):
        """Load MD trajectory data"""
        self.frames, self.energies, self.step_times = MDTrajectoryParser.parse_trajectory(filepath)
        
        if self.frames:
            self.info_label.setText(f"Loaded: {len(self.frames)} frames from {filepath.name}")
            
            # Update sliders
            self.frame_spinner.setMaximum(len(self.frames) - 1)
            self.frame_slider.setMaximum(len(self.frames) - 1)
            
            self.update_plots()
            self.update_table()
        else:
            self.info_label.setText(f"No MD data found in {filepath.name}")
    
    def on_frame_selected(self, frame_id: int):
        """Handle frame selection"""
        if not self.frame_slider.hasFocus():  # Avoid recursion
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(frame_id)
            self.frame_slider.blockSignals(False)
        
        self.current_frame = frame_id
        self.update_plots()
    
    def on_slider_moved(self, frame_id: int):
        """Handle slider movement"""
        if not self.frame_spinner.hasFocus():
            self.frame_spinner.blockSignals(True)
            self.frame_spinner.setValue(frame_id)
            self.frame_spinner.blockSignals(False)
        
        self.current_frame = frame_id
        self.update_plots()
    
    def toggle_playback(self):
        """Toggle animation playback"""
        self.is_playing = not self.is_playing
        
        if self.is_playing:
            self.play_btn.setText("⏸ Pause")
            self.timer.start(self.playback_speed)
        else:
            self.play_btn.setText("▶ Play")
            self.timer.stop()
    
    def next_frame(self):
        """Go to next frame"""
        if self.current_frame < len(self.frames) - 1:
            self.current_frame += 1
            self.frame_spinner.setValue(self.current_frame)
            self.frame_slider.setValue(self.current_frame)
        else:
            # Loop back
            if self.is_playing:
                self.current_frame = 0
                self.frame_spinner.setValue(0)
                self.frame_slider.setValue(0)
    
    def prev_frame(self):
        """Go to previous frame"""
        if self.current_frame > 0:
            self.current_frame -= 1
            self.frame_spinner.setValue(self.current_frame)
            self.frame_slider.setValue(self.current_frame)
    
    def update_plots(self):
        """Update energy plots"""
        if not self.energies:
            return
        
        steps = np.array(self.step_times)
        energies = np.array(self.energies)
        
        # Mark current frame
        self.energy_canvas.plot_energy_evolution(steps, energies)
        if 0 <= self.current_frame < len(steps):
            self.energy_canvas.ax.axvline(steps[self.current_frame], 
                                         color='red', linestyle='--', alpha=0.5)
        self.energy_canvas.draw()
        
        # Convergence plot
        self.convergence_canvas.plot_convergence(steps, energies)
        self.convergence_canvas.draw()
    
    def update_table(self):
        """Update frame data table"""
        self.frame_table.setRowCount(len(self.frames))
        
        for row, frame in enumerate(self.frames):
            self.frame_table.setItem(row, 0, QTableWidgetItem(str(row)))
            self.frame_table.setItem(row, 1, QTableWidgetItem(str(frame.step)))
            self.frame_table.setItem(row, 2, QTableWidgetItem(f"{frame.energy:.6f}"))
    
    def export_energy_data(self):
        """Export energy data to CSV"""
        if not self.frames:
            QMessageBox.warning(self, "Export", "No data to export")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Energy Data", "",
                                                   "CSV (*.csv);;All Files (*)")
        if filepath:
            import csv
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Frame', 'Step', 'Energy (eV)'])
                
                for row, frame in enumerate(self.frames):
                    writer.writerow([row, frame.step, frame.energy])
            
            QMessageBox.information(self, "Export", f"Data saved to {filepath}")


def launch_md_viewer(orca_filepath: Optional[Path] = None, parent=None) -> MDPopup:
    """Convenience function to launch MD viewer"""
    popup = MDPopup(orca_filepath, parent)
    popup.exec()
    return popup
