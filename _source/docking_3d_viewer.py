# docking_3d_viewer.py (v1.0 - Protein-Ligand 3D Viewer)
"""
ChemDraw Pro: 3D visualization for docking results
- Protein backbone ribbon (C-alpha trace)
- Ligand ball-and-stick rendering
- Binding site residue sticks
- Interaction visualization (dashed lines for H-bonds)
"""

import math
from typing import Dict, List, Tuple, Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QWheelEvent, QMouseEvent

from docking_data import (
    ReceptorData, DockingPose, Interaction, PDBAtom
)

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL.GL import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False


# Element colors (same as popup_3d.py)
ELEMENT_COLORS = {
    "H": (1.0, 1.0, 1.0),
    "C": (0.2, 0.2, 0.2),
    "N": (0.0, 0.0, 1.0),
    "O": (1.0, 0.0, 0.0),
    "S": (1.0, 1.0, 0.0),
    "P": (1.0, 0.65, 0.0),
    "F": (0.2, 1.0, 0.2),
    "Cl": (0.0, 1.0, 0.0),
    "Br": (0.6, 0.2, 0.2),
    "Fe": (0.6, 0.4, 0.1),
}

ELEMENT_RADII = {
    "H": 0.3, "C": 0.5, "N": 0.5, "O": 0.5,
    "S": 0.6, "P": 0.6, "F": 0.4, "Cl": 0.5,
}

# Interaction colors
INTERACTION_COLORS = {
    "hydrogen_bond": (0.1, 0.6, 1.0),    # Blue
    "hydrophobic": (1.0, 0.6, 0.0),       # Orange
    "pi_stacking": (0.6, 0.15, 0.7),      # Purple
    "salt_bridge": (1.0, 0.2, 0.2),       # Red
}

# Protein backbone color
BACKBONE_COLOR = (0.7, 0.7, 0.8)
BINDING_SITE_COLOR = (0.3, 0.8, 0.3, 0.4)


class Docking3DViewerWidget(QWidget):
    """2D-projected 3D viewer for protein-ligand complexes

    Uses QPainter for rendering (no OpenGL dependency).
    Supports rotation, zoom, and interaction visualization.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.receptor: Optional[ReceptorData] = None
        self.pose: Optional[DockingPose] = None
        self.interactions: List[Interaction] = []

        # View parameters
        self.rot_x = 20.0
        self.rot_y = 30.0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

        # Mouse state
        self._last_mouse_pos = None
        self._mouse_button = None

        # Display options
        self.show_protein = True
        self.show_ligand = True
        self.show_interactions = True
        self.show_binding_site = True

        # Pre-computed data
        self._center = (0.0, 0.0, 0.0)
        self._scale = 1.0
        self._binding_residue_ids = set()

        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)

    def set_data(self, receptor: ReceptorData, pose: DockingPose,
                 interactions: List[Interaction] = None):
        """Set protein-ligand data for visualization"""
        self.receptor = receptor
        self.pose = pose
        self.interactions = interactions or []

        # Find binding site residues from interactions
        self._binding_residue_ids = set()
        for inter in self.interactions:
            self._binding_residue_ids.add((inter.chain, inter.residue_id))

        # Compute center and scale
        self._compute_view_params()
        self.update()

    def _compute_view_params(self):
        """Compute center and scale from data"""
        all_coords = []

        if self.pose and self.pose.atom_coords:
            all_coords.extend(self.pose.atom_coords)

        if self.receptor:
            # Use C-alpha atoms for protein extent
            for chain_residues in self.receptor.residues.values():
                for res in chain_residues:
                    ca = res.ca_position
                    if ca:
                        all_coords.append(ca)

        if not all_coords:
            return

        xs = [c[0] for c in all_coords]
        ys = [c[1] for c in all_coords]
        zs = [c[2] for c in all_coords]

        self._center = (
            (min(xs) + max(xs)) / 2,
            (min(ys) + max(ys)) / 2,
            (min(zs) + max(zs)) / 2,
        )

        extent = max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs),
            1.0
        )
        self._scale = min(self.width(), self.height()) / (extent * 1.5)

    def _project(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """Project 3D coordinates to 2D screen space with rotation"""
        # Center
        x -= self._center[0]
        y -= self._center[1]
        z -= self._center[2]

        # Rotate around Y axis
        rad_y = math.radians(self.rot_y)
        cos_y, sin_y = math.cos(rad_y), math.sin(rad_y)
        x2 = x * cos_y + z * sin_y
        z2 = -x * sin_y + z * cos_y

        # Rotate around X axis
        rad_x = math.radians(self.rot_x)
        cos_x, sin_x = math.cos(rad_x), math.sin(rad_x)
        y2 = y * cos_x - z2 * sin_x
        z3 = y * sin_x + z2 * cos_x

        # Scale and translate to screen
        sx = self.width() / 2 + x2 * self._scale * self.zoom + self.pan_x
        sy = self.height() / 2 - y2 * self._scale * self.zoom + self.pan_y

        return (sx, sy, z3)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 40))

        if not self.receptor and not self.pose:
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "도킹 결과를 선택하세요")
            return

        # Draw protein backbone
        if self.show_protein and self.receptor:
            self._draw_protein(painter)

        # Draw binding site residues
        if self.show_binding_site and self.receptor:
            self._draw_binding_site(painter)

        # Draw ligand
        if self.show_ligand and self.pose:
            self._draw_ligand(painter)

        # Draw interactions
        if self.show_interactions and self.interactions:
            self._draw_interactions(painter)

        # Info overlay
        self._draw_info(painter)

        painter.end()

    def _draw_protein(self, painter: QPainter):
        """Draw protein backbone as C-alpha trace"""
        pen = QPen(QColor(180, 180, 210), 2)
        painter.setPen(pen)

        for chain_id, residues in self.receptor.residues.items():
            prev_point = None
            for res in residues:
                ca = res.ca_position
                if ca is None:
                    prev_point = None
                    continue

                sx, sy, sz = self._project(*ca)
                point = QPointF(sx, sy)

                if prev_point is not None:
                    painter.drawLine(prev_point, point)

                prev_point = point

    def _draw_binding_site(self, painter: QPainter):
        """Draw binding site residues as sticks"""
        if not self._binding_residue_ids:
            return

        pen = QPen(QColor(100, 200, 100), 1.5)
        painter.setPen(pen)

        for chain_id, residues in self.receptor.residues.items():
            for res in residues:
                if (res.chain, res.residue_id) not in self._binding_residue_ids:
                    continue

                # Draw residue atoms
                for atom in res.atoms:
                    if atom.name.strip() in ("H", "HA", "HB", "HG"):
                        continue  # skip hydrogens

                    sx, sy, sz = self._project(atom.x, atom.y, atom.z)
                    color = ELEMENT_COLORS.get(atom.element, (0.5, 0.5, 0.5))
                    painter.setBrush(QColor(
                        int(color[0]*255), int(color[1]*255), int(color[2]*255), 150
                    ))
                    radius = 3
                    painter.drawEllipse(QPointF(sx, sy), radius, radius)

                # Draw residue label at CA
                ca = res.ca_position
                if ca:
                    sx, sy, _ = self._project(*ca)
                    painter.setPen(QColor(200, 255, 200))
                    painter.setFont(QFont("Arial", 8))
                    painter.drawText(int(sx) + 5, int(sy) - 5,
                                     f"{res.name}{res.residue_id}")
                    painter.setPen(pen)

    def _draw_ligand(self, painter: QPainter):
        """Draw ligand atoms as ball-and-stick"""
        if not self.pose.atom_coords:
            return

        # Draw bonds (connect atoms within 1.8A)
        pen = QPen(QColor(255, 255, 255), 2)
        painter.setPen(pen)

        coords = self.pose.atom_coords
        elements = self.pose.atom_elements

        for i in range(len(coords)):
            for j in range(i+1, len(coords)):
                dist = math.sqrt(
                    sum((a-b)**2 for a, b in zip(coords[i], coords[j]))
                )
                if dist < 1.8:  # likely bonded
                    sx1, sy1, _ = self._project(*coords[i])
                    sx2, sy2, _ = self._project(*coords[j])
                    painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

        # Draw atoms
        for i, (x, y, z) in enumerate(coords):
            elem = elements[i] if i < len(elements) else "C"
            if elem == "H":
                continue  # skip hydrogens for clarity

            sx, sy, sz = self._project(x, y, z)
            color = ELEMENT_COLORS.get(elem, (0.5, 0.5, 0.5))
            radius = ELEMENT_RADII.get(elem, 0.4) * 6

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(
                int(color[0]*255), int(color[1]*255), int(color[2]*255)
            ))
            painter.drawEllipse(QPointF(sx, sy), radius, radius)

            # White highlight
            painter.setBrush(QColor(255, 255, 255, 60))
            painter.drawEllipse(QPointF(sx - radius*0.2, sy - radius*0.2),
                                radius*0.4, radius*0.4)

    def _draw_interactions(self, painter: QPainter):
        """Draw interaction lines between ligand and protein"""
        if not self.pose or not self.receptor:
            return

        for inter in self.interactions:
            # Get ligand atom position
            if inter.ligand_atom_idx >= len(self.pose.atom_coords):
                continue
            lx, ly, lz = self.pose.atom_coords[inter.ligand_atom_idx]
            lsx, lsy, _ = self._project(lx, ly, lz)

            # Find protein atom position
            protein_pos = self._find_protein_atom(inter)
            if protein_pos is None:
                continue
            psx, psy, _ = self._project(*protein_pos)

            # Draw dashed line with interaction color
            color = INTERACTION_COLORS.get(inter.type, (0.5, 0.5, 0.5))
            pen = QPen(QColor(
                int(color[0]*255), int(color[1]*255), int(color[2]*255)
            ))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(QPointF(lsx, lsy), QPointF(psx, psy))

            # Distance label
            mx = (lsx + psx) / 2
            my = (lsy + psy) / 2
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(int(mx), int(my), f"{inter.distance:.1f}Å")

    def _find_protein_atom(self, inter: Interaction) -> Optional[Tuple[float, float, float]]:
        """Find 3D position of protein atom from interaction data"""
        for atom in self.receptor.atoms:
            if (atom.chain == inter.chain and
                atom.residue_id == inter.residue_id and
                atom.name.strip() == inter.protein_atom_name.strip()):
                return (atom.x, atom.y, atom.z)

        # Fallback: find CA of the residue
        for chain_residues in self.receptor.residues.values():
            for res in chain_residues:
                if res.chain == inter.chain and res.residue_id == inter.residue_id:
                    return res.ca_position
        return None

    def _draw_info(self, painter: QPainter):
        """Draw info overlay"""
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Arial", 10))

        y = 20
        if self.receptor:
            painter.drawText(10, y, f"Receptor: {self.receptor.name}")
            y += 18
        if self.pose:
            painter.drawText(10, y,
                             f"Pose #{self.pose.pose_id}: "
                             f"{self.pose.affinity_kcal:.2f} kcal/mol")
            y += 18
        if self.interactions:
            painter.drawText(10, y, f"Interactions: {len(self.interactions)}")

        # Controls hint
        painter.setPen(QColor(100, 100, 120))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(10, self.height() - 10,
                         "Left drag: rotate | Right drag: pan | Scroll: zoom")

    # ========== MOUSE INTERACTION ==========

    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse_pos = event.position()
        self._mouse_button = event.button()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse_pos is None:
            return

        dx = event.position().x() - self._last_mouse_pos.x()
        dy = event.position().y() - self._last_mouse_pos.y()

        if self._mouse_button == Qt.MouseButton.LeftButton:
            self.rot_y += dx * 0.5
            self.rot_x += dy * 0.5
        elif self._mouse_button == Qt.MouseButton.RightButton:
            self.pan_x += dx
            self.pan_y += dy

        self._last_mouse_pos = event.position()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._last_mouse_pos = None
        self._mouse_button = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y() / 120
        self.zoom *= 1.1 ** delta
        self.zoom = max(0.1, min(10.0, self.zoom))
        self.update()
