# [Phase C] popup_3d.py - 3D Interactive Molecular Visualization
# ✅ C2 FIX: `from PyQt6.QtOpenGL import GL` 제거 (PyQt6에 존재하지 않는 모듈)
"""
PyQt6 OpenGL-based 3D molecular viewer for ChemDraw Pro
- Ball-and-Stick and Space-filling models
- Real-time rotation/zoom interaction
- Triggered from theoretical structure layer

C2 FIX v1.01:
✅ Removed `from PyQt6.QtOpenGL import GL` — this module does not exist in PyQt6
   PyOpenGL (OpenGL.GL) is used instead, already handled via try/except
"""

import math
from typing import Dict, List, Tuple, Optional
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider
from PyQt6.QtCore import Qt, QPointF, QThread, pyqtSignal
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
# ✅ C2 FIX: 아래 줄 제거됨
# ❌ 이전: from PyQt6.QtOpenGL import GL  # 이 모듈은 PyQt6에 존재하지 않음
import numpy as np

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False
    print("[Phase C] PyOpenGL not available, using fallback rendering")


class Molecule3DData:
    """Container for 3D molecular coordinate data"""
    def __init__(self, atoms: Dict, bonds: Dict, theory_data: Dict = None):
        self.atoms = atoms  # {position: {"main": symbol, ...}}
        self.bonds = bonds  # {(k1, k2): order}
        self.theory_data = theory_data or {}  # {"coords": {}, "map": {}}
        self.atom_positions = {}
        self.atom_symbols = {}
        
        # Extract coordinates from theory data
        if theory_data and "map" in theory_data:
            t_map = theory_data["map"]
            for orig_pos, theory_pos in t_map.items():
                # Convert QPointF to (x, y, 0) coordinate
                x = theory_pos.x() if hasattr(theory_pos, 'x') else theory_pos[0]
                y = theory_pos.y() if hasattr(theory_pos, 'y') else theory_pos[1]
                self.atom_positions[orig_pos] = (round(x, 2), round(y, 2), 0.0)
                
                # Get atom symbol
                if orig_pos in atoms:
                    symbol = atoms[orig_pos].get("main", "C")
                    self.atom_symbols[orig_pos] = symbol
                else:
                    self.atom_symbols[orig_pos] = "C"
        else:
            # Fallback: use 2D coordinates with Z=0
            for pos, data in atoms.items():
                self.atom_positions[pos] = (round(pos[0], 2), round(pos[1], 2), 0.0)
                self.atom_symbols[pos] = data.get("main", "C")


class MoleculeRenderer3D:
    """Abstract base class for 3D molecular rendering"""
    
    ELEMENT_RADII = {
        "H": 1.2, "C": 1.7, "N": 1.55, "O": 1.52, "F": 1.47,
        "P": 1.8, "S": 1.8, "Cl": 1.75, "Br": 1.85, "I": 1.98
    }
    
    ELEMENT_COLORS = {
        "H": (1.0, 1.0, 1.0),    # White
        "C": (0.2, 0.2, 0.2),    # Dark gray
        "N": (0.0, 0.0, 1.0),    # Blue
        "O": (1.0, 0.0, 0.0),    # Red
        "F": (0.2, 1.0, 0.2),    # Green
        "P": (1.0, 0.65, 0.0),   # Orange
        "S": (1.0, 1.0, 0.0),    # Yellow
        "Cl": (0.0, 1.0, 0.0),   # Green
        "Br": (0.6, 0.2, 0.2),   # Brown
        "I": (0.4, 0.0, 0.4),    # Purple
    }
    
    BOND_RADII = {
        1: 0.3,  # Single bond
        2: 0.35, # Double bond
        3: 0.4,  # Triple bond
    }
    
    @staticmethod
    def get_vdw_radius(symbol: str) -> float:
        """Get van der Waals radius for element"""
        return MoleculeRenderer3D.ELEMENT_RADII.get(symbol, 1.7)
    
    @staticmethod
    def get_color(symbol: str) -> Tuple[float, float, float]:
        """Get RGB color for element"""
        return MoleculeRenderer3D.ELEMENT_COLORS.get(symbol, (0.5, 0.5, 0.5))
    
    @staticmethod
    def get_bond_radius(order: int = 1) -> float:
        """Get radius for bond rendering"""
        return MoleculeRenderer3D.BOND_RADII.get(order, 0.3)


class BallAndStickRenderer(MoleculeRenderer3D):
    """Ball-and-Stick model renderer"""
    
    def __init__(self):
        self.sphere_slices = 16
        self.sphere_stacks = 12
        self.cylinder_slices = 8
    
    def render_atom(self, x: float, y: float, z: float, symbol: str, scale: float = 1.0):
        """Render single atom as sphere"""
        radius = MoleculeRenderer3D.get_vdw_radius(symbol) * scale * 0.3
        color = MoleculeRenderer3D.get_color(symbol)
        
        glPushMatrix()
        glTranslatef(x, y, z)
        glColor3f(*color)
        
        # Draw sphere using GLU quad
        quad = gluNewQuadric()
        gluSphere(quad, radius, self.sphere_slices, self.sphere_stacks)
        
        glPopMatrix()
    
    def render_bond(self, p1: Tuple, p2: Tuple, order: int = 1, scale: float = 1.0):
        """Render bond as cylinder"""
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        
        # Bond parameters
        radius = MoleculeRenderer3D.get_bond_radius(order) * scale * 0.2
        
        # Calculate bond vector and rotation
        dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        if length < 0.001:
            return
        
        glPushMatrix()
        glTranslatef(x1, y1, z1)
        
        # Rotate to align with bond vector
        if abs(dz) < 0.999:
            axis = (-dy, dx, 0)
            axis_len = math.sqrt(axis[0]**2 + axis[1]**2)
            if axis_len > 0:
                axis = tuple(a / axis_len for a in axis)
                angle = math.degrees(math.acos(dz / length))
                glRotatef(angle, *axis)
        
        # Draw cylinder
        glColor3f(0.5, 0.5, 0.5)  # Gray bonds
        quad = gluNewQuadric()
        gluCylinder(quad, radius, radius, length, self.cylinder_slices, 1)
        
        glPopMatrix()
    
    def render_molecule(self, mol_data: Molecule3DData):
        """Render complete molecule in ball-and-stick style"""
        glEnable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        
        # Render bonds first
        for (k1, k2), order in mol_data.bonds.items():
            if k1 in mol_data.atom_positions and k2 in mol_data.atom_positions:
                p1 = mol_data.atom_positions[k1]
                p2 = mol_data.atom_positions[k2]
                bond_order = order if isinstance(order, int) else 1
                self.render_bond(p1, p2, bond_order)
        
        # Render atoms on top
        for pos, coords in mol_data.atom_positions.items():
            symbol = mol_data.atom_symbols.get(pos, "C")
            self.render_atom(*coords, symbol)


class SpaceFillingRenderer(MoleculeRenderer3D):
    """Space-filling (CPK) model renderer"""
    
    def __init__(self):
        self.sphere_slices = 24
        self.sphere_stacks = 16
    
    def render_atom(self, x: float, y: float, z: float, symbol: str, scale: float = 1.0):
        """Render single atom as scaled van der Waals sphere"""
        radius = MoleculeRenderer3D.get_vdw_radius(symbol) * scale * 0.5
        color = MoleculeRenderer3D.get_color(symbol)
        
        glPushMatrix()
        glTranslatef(x, y, z)
        glColor3f(*color)
        
        # Draw sphere with higher quality
        quad = gluNewQuadric()
        gluSphere(quad, radius, self.sphere_slices, self.sphere_stacks)
        
        glPopMatrix()
    
    def render_molecule(self, mol_data: Molecule3DData):
        """Render complete molecule in space-filling style"""
        glEnable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        
        # Render only atoms (bonds are implicitly represented by van der Waals overlap)
        for pos, coords in mol_data.atom_positions.items():
            symbol = mol_data.atom_symbols.get(pos, "C")
            self.render_atom(*coords, symbol)


class Molecule3DViewer(QOpenGLWidget):
    """
    [Phase C] OpenGL-based 3D molecular viewer
    - Supports Ball-and-Stick and Space-filling models
    - Real-time rotation and zoom interaction
    - Triggered from theoretical structure layer
    """
    
    def __init__(self, mol_data: Molecule3DData = None):
        super().__init__()
        
        # Set up OpenGL format
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)  # 4x MSAA
        self.setFormat(fmt)
        
        # Molecule data
        self.mol_data = mol_data
        self.molecule_center = (0.0, 0.0, 0.0)
        self.molecule_scale = 1.0
        
        # Rendering mode
        self.render_mode = "ball_and_stick"  # or "space_filling"
        self.ball_stick_renderer = BallAndStickRenderer() if OPENGL_AVAILABLE else None
        self.space_fill_renderer = SpaceFillingRenderer() if OPENGL_AVAILABLE else None
        
        # Interaction state
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.rotation_z = 0.0
        self.zoom = 45.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        
        # Mouse interaction
        self.mouse_last_x = 0
        self.mouse_last_y = 0
        self.mouse_pressed = False
        
        # Calculate molecule center if data provided
        if self.mol_data:
            self._calculate_center_and_scale()
    
    def _calculate_center_and_scale(self):
        """Calculate molecule center and scale for optimal viewing"""
        if not self.mol_data or not self.mol_data.atom_positions:
            return
        
        coords = list(self.mol_data.atom_positions.values())
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        zs = [c[2] for c in coords]
        
        self.molecule_center = (
            sum(xs) / len(xs),
            sum(ys) / len(ys),
            sum(zs) / len(zs)
        )
        
        # Calculate bounding box
        size = max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs)
        )
        
        self.molecule_scale = 20.0 / (size + 1.0)
        self.zoom = 45.0
    
    def initializeGL(self):
        """Initialize OpenGL context"""
        if not OPENGL_AVAILABLE:
            return
        
        glClearColor(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        
        # Set up light
        glLight(GL_LIGHT0, GL_POSITION, (1.0, 1.0, 1.0, 0.0))
        glLight(GL_LIGHT0, GL_AMBIENT, (0.2, 0.2, 0.2, 1.0))
        glLight(GL_LIGHT0, GL_DIFFUSE, (1.0, 1.0, 1.0, 1.0))
        glLight(GL_LIGHT0, GL_SPECULAR, (1.0, 1.0, 1.0, 1.0))
        
        # Set up material
        glMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_DIFFUSE, (0.8, 0.8, 0.8, 1.0))
        glMaterial(GL_FRONT_AND_BACK, GL_SPECULAR, (1.0, 1.0, 1.0, 1.0))
        glMaterial(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
    
    def resizeGL(self, w: int, h: int):
        """Handle window resize"""
        if h == 0:
            h = 1
        
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        
        aspect = w / h
        gluPerspective(self.zoom, aspect, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
    
    def paintGL(self):
        """Render the scene"""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # Set up camera
        glTranslatef(self.pan_x, self.pan_y, -40.0)
        glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
        glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
        glRotatef(self.rotation_z, 0.0, 0.0, 1.0)
        
        # Translate to molecule center
        glTranslatef(-self.molecule_center[0] * self.molecule_scale,
                    -self.molecule_center[1] * self.molecule_scale,
                    -self.molecule_center[2] * self.molecule_scale)
        
        glScalef(self.molecule_scale, self.molecule_scale, self.molecule_scale)
        
        # Render molecule
        if self.mol_data:
            if self.render_mode == "ball_and_stick" and self.ball_stick_renderer:
                self.ball_stick_renderer.render_molecule(self.mol_data)
            elif self.render_mode == "space_filling" and self.space_fill_renderer:
                self.space_fill_renderer.render_molecule(self.mol_data)
    
    def mousePressEvent(self, event):
        """Handle mouse press"""
        self.mouse_last_x = event.position().x()
        self.mouse_last_y = event.position().y()
        self.mouse_pressed = True
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        self.mouse_pressed = False
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for rotation"""
        if not self.mouse_pressed:
            return
        
        x = event.position().x()
        y = event.position().y()
        
        dx = x - self.mouse_last_x
        dy = y - self.mouse_last_y
        
        # Update rotation
        self.rotation_y += dx * 0.5
        self.rotation_x += dy * 0.5
        
        self.mouse_last_x = x
        self.mouse_last_y = y
        self.update()
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zoom"""
        delta = event.angleDelta().y()
        zoom_factor = 1.1 if delta > 0 else 0.9
        
        self.zoom *= zoom_factor
        self.zoom = max(10.0, min(100.0, self.zoom))  # Clamp zoom
        
        self.update()


class Molecule3DPopup(QWidget):
    """
    [Phase C] Main 3D popup window
    Contains viewer, model selector, and interaction controls
    Triggered from theoretical structure layer only
    """
    
    def __init__(self, mol_data: Molecule3DData, parent=None):
        super().__init__(parent)
        self.mol_data = mol_data
        self.viewer = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("ChemDraw Pro - 3D Molecular Viewer (Theory Layer)")
        self.setGeometry(100, 100, 800, 700)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("3D Molecular Visualization - Ball-and-Stick & Space-Filling Models")
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(title)
        
        # Control panel
        control_layout = QHBoxLayout()
        
        # Model selector
        self.model_label = QLabel("Model:")
        control_layout.addWidget(self.model_label)
        
        self.ball_stick_btn = QPushButton("Ball & Stick")
        self.ball_stick_btn.setCheckable(True)
        self.ball_stick_btn.setChecked(True)
        self.ball_stick_btn.clicked.connect(self.set_ball_and_stick)
        control_layout.addWidget(self.ball_stick_btn)
        
        self.space_fill_btn = QPushButton("Space Filling")
        self.space_fill_btn.setCheckable(True)
        self.space_fill_btn.clicked.connect(self.set_space_filling)
        control_layout.addWidget(self.space_fill_btn)
        
        # Zoom slider
        control_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(100)
        self.zoom_slider.setValue(45)
        self.zoom_slider.sliderMoved.connect(self.update_zoom)
        control_layout.addWidget(self.zoom_slider)
        
        # Reset button
        reset_btn = QPushButton("Reset View")
        reset_btn.clicked.connect(self.reset_view)
        control_layout.addWidget(reset_btn)
        
        layout.addLayout(control_layout)
        
        # 3D Viewer
        if OPENGL_AVAILABLE:
            self.viewer = Molecule3DViewer(self.mol_data)
            layout.addWidget(self.viewer, 1)
        else:
            fallback_label = QLabel("OpenGL not available. Install PyOpenGL to enable 3D visualization.")
            fallback_label.setStyleSheet("color: red; font-weight: bold;")
            layout.addWidget(fallback_label, 1)
        
        # Info panel
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"Atoms: {len(self.mol_data.atom_positions)}"))
        info_layout.addWidget(QLabel(f"Bonds: {len(self.mol_data.bonds)}"))
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        self.setLayout(layout)
    
    def set_ball_and_stick(self):
        """Switch to ball-and-stick model"""
        if self.viewer:
            self.viewer.render_mode = "ball_and_stick"
            self.viewer.update()
        self.ball_stick_btn.setChecked(True)
        self.space_fill_btn.setChecked(False)
    
    def set_space_filling(self):
        """Switch to space-filling model"""
        if self.viewer:
            self.viewer.render_mode = "space_filling"
            self.viewer.update()
        self.ball_stick_btn.setChecked(False)
        self.space_fill_btn.setChecked(True)
    
    def update_zoom(self, value):
        """Update zoom level"""
        if self.viewer:
            self.viewer.zoom = float(value)
            self.viewer.update()
    
    def reset_view(self):
        """Reset view to default"""
        if self.viewer:
            self.viewer.rotation_x = 0.0
            self.viewer.rotation_y = 0.0
            self.viewer.rotation_z = 0.0
            self.viewer.pan_x = 0.0
            self.viewer.pan_y = 0.0
            self.viewer._calculate_center_and_scale()
            self.zoom_slider.setValue(45)
            self.viewer.update()
