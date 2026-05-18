# docking_3d_viewer.py (v1.3 - Protein-Ligand 3D Viewer, enhanced ligand/protein distinction)
"""
ChemDraw Pro: 3D visualization for docking results
- Protein backbone ribbon (C-alpha trace)
- Ligand ball-and-stick rendering
- Binding site residue sticks
- Interaction visualization (dashed lines for H-bonds)
"""

import logging
import math
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QFont, QWheelEvent,
                         QMouseEvent, QRadialGradient, QLinearGradient, QPainterPath,
                         QFontDatabase)


# Rule Q: 한글 폰트 fallback 체인 (Malgun → NanumGothic → Noto → Arial Unicode → 시스템)
def _get_korean_font(size: int = 10, bold: bool = False) -> QFont:
    """Return a QFont that supports Korean glyphs.

    Tries Malgun Gothic (Windows), NanumGothic (Linux/common),
    Noto Sans CJK KR, Arial Unicode MS, then falls back to system font.
    QFontDatabase.families() is a static method in PyQt6 — no instantiation needed.
    """
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    families = QFontDatabase.families()  # static method (PyQt6)
    for name in ["Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Arial Unicode MS"]:
        if name in families:
            f = QFont(name, size)
            f.setWeight(weight)
            return f
    # System fallback — still set weight
    sys_name = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
    f = QFont(sys_name, size)
    f.setWeight(weight)
    return f

from docking_data import (
    ReceptorData, DockingPose, Interaction, PDBAtom
)

# M497: SIMULATION_MODE import — 3D 뷰어 워터마크에 사용 (FP-15 fix)
try:
    from docking_interface import SIMULATION_MODE as _DOCKING_SIMULATION_MODE, VINA_AVAILABLE as _VINA_AVAIL
except ImportError:
    _DOCKING_SIMULATION_MODE = False
    _VINA_AVAIL = True

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
# Rule O + Rule I: 학술 표준 (LigPlot+ / Bisawas P. Int. J. Mol. Sci. 2022, 23(19):11746 기준)
INTERACTION_COLORS = {
    "hydrogen_bond": (1.0, 0.1, 0.1),    # 빨강 — LigPlot+/Bisawas 2022 표준 (D3 fix)
    "hydrophobic": (1.0, 0.65, 0.25),    # 주황
    "pi_stacking": (0.0, 0.8, 0.8),      # 청록 — Bisawas 2022 영상 기준 (D4 fix)
    "salt_bridge": (1.0, 0.6, 0.0),      # 주황-노랑 (salt bridge 구분)
    "halogen_bond": (0.5, 0.7, 1.0),     # 밝은 파랑
}

# Binding site residue role colors (by H-bond capability)
HBOND_DONOR_COLOR = (0.2, 0.5, 1.0)       # Blue — H-bond donor residues
HBOND_ACCEPTOR_COLOR = (1.0, 0.3, 0.3)    # Red — H-bond acceptor residues
HBOND_BOTH_COLOR = (0.7, 0.2, 0.9)        # Purple — both donor and acceptor
BINDING_NEUTRAL_COLOR = (0.6, 0.6, 0.6)   # Gray — no H-bond role
POCKET_HIGHLIGHT_COLOR = (1.0, 0.9, 0.2, 0.15)  # Yellow translucent pocket (15% opacity)

# Interaction type colors for residue highlighting
RESIDUE_INTERACTION_COLORS = {
    "hydrogen_bond": (0.1, 0.6, 1.0),    # Blue
    "hydrophobic": (1.0, 0.8, 0.0),       # Yellow
    "pi_stacking": (0.6, 0.15, 0.7),      # Purple
    "salt_bridge": (1.0, 0.2, 0.2),       # Red
    "halogen_bond": (0.0, 0.75, 0.83),    # Cyan
}

# Covalent radii (Angstroms) for element-pair bond detection
# Source: standard covalent radii tables
COVALENT_RADII = {
    'C': 0.77, 'N': 0.75, 'O': 0.73, 'S': 1.02, 'P': 1.06,
    'F': 0.71, 'Cl': 0.99, 'Br': 1.14, 'I': 1.33, 'H': 0.31,
    'Fe': 1.25, 'Zn': 1.22, 'Mg': 1.36, 'Ca': 1.74,
}
BOND_TOLERANCE = 0.4  # Angstroms added to sum of covalent radii

# Warm color scheme for ligand atoms (distinct from protein CPK)
LIGAND_ELEMENT_COLORS = {
    "H": (1.0, 1.0, 0.9),       # Warm white
    "C": (1.0, 0.65, 0.0),      # Orange (distinct from gray protein C)
    "N": (0.2, 0.4, 1.0),       # Blue (kept for recognition)
    "O": (1.0, 0.2, 0.2),       # Red (kept for recognition)
    "S": (1.0, 0.85, 0.0),      # Golden yellow
    "P": (1.0, 0.5, 0.0),       # Deep orange
    "F": (0.4, 1.0, 0.4),       # Green
    "Cl": (0.2, 0.9, 0.2),      # Bright green
    "Br": (0.8, 0.3, 0.1),      # Dark orange
    "Fe": (0.8, 0.5, 0.1),      # Bronze
}

# Ligand outline/halo color (bright cyan for contrast)
LIGAND_OUTLINE_COLOR = QColor(0, 230, 210, 180)  # Cyan halo
LIGAND_OUTLINE_WIDTH = 2.0  # pixels

# Protein backbone color
BACKBONE_COLOR = (0.7, 0.7, 0.8)
BINDING_SITE_COLOR = (0.3, 0.8, 0.3, 0.4)

# Rule I: 도메인별 색상 — ALDH 도메인 매핑 기준 (Bisawas 2022 + UniProt P05091)
# 매직넘버 150/300: NAD binding 1-150, Catalytic 151-300, Bridging 301+ (Bisawas 2022)
DOMAIN_COLORS = {
    'NAD': QColor(30, 100, 200),       # 파랑 — NAD 결합 도메인
    'Catalytic': QColor(50, 180, 80),  # 초록 — 촉매 도메인
    'Bridging': QColor(210, 120, 30),  # 주황 — 브릿징 도메인
}
DOMAIN_BOUNDARY_NAD = 150     # 잔기 번호 ≤ 150: NAD binding (Bisawas 2022 ALDH2)
DOMAIN_BOUNDARY_CAT = 300     # 잔기 번호 151-300: Catalytic (Bisawas 2022 ALDH2)


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

        # Background color — default dark; override to white for PDF export
        self._bg_color = QColor(30, 30, 40)

        # Display options
        self.show_protein = True
        self.show_ligand = True
        self.show_interactions = True
        self.show_binding_site = True
        self.backbone_style = 'ribbon'  # 'ribbon' or 'trace'

        # M563 격분 9: 수용체 결합부 ball&stick 모드 (Discovery Studio 수준)
        # 사용자 인용 (2026-03-18T13:25): "수용체에서 분자랑 결합하는 부위는 ball&stick 형태로 표현되어야 한다"
        # 옵션: 'ball_stick' (Discovery Studio 표준, 기본) | 'stick' (Licorice) | 'wireframe' (선)
        self.binding_site_style = 'ball_stick'

        # Ligand 렌더 모드 (popup_docking._set_mol_style이 duck typing으로 set 함)
        # 매직넘버 주석: 'ball_stick' = VMD/PyMOL 기본 모드 (M456 F4)
        self.mol_style = 'ball_stick'

        # Pre-computed data
        self._center = (0.0, 0.0, 0.0)
        self._scale = 1.0
        self._binding_residue_ids = set()
        # Extended binding site data: {(chain, res_id): (is_donor, is_acceptor)}
        self._binding_site_roles: Dict[Tuple[str, int], Tuple[bool, bool]] = {}
        # Interaction type per residue: {(chain, res_id): primary_interaction_type}
        self._residue_interaction_types: Dict[Tuple[str, int], str] = {}
        # Key interacting residues (those with direct interactions)
        self._key_residues: set = set()  # (chain, res_id)

        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)

    def set_data(self, receptor: ReceptorData, pose: DockingPose,
                 interactions: List[Interaction] = None,
                 binding_site_residues: List[Tuple] = None):
        """Set protein-ligand data for visualization.

        Args:
            receptor: Protein receptor data
            pose: Docking pose to display
            interactions: Detected interactions for this pose
            binding_site_residues: Optional list of (res_name, res_id, chain,
                is_donor, is_acceptor) from InteractionAnalyzer.extract_binding_site_residues.
                If provided, these are displayed instead of only interaction residues.
        """
        self.receptor = receptor
        self.pose = pose
        self.interactions = interactions or []

        # Populate binding site from explicit residue list or from interactions
        self._binding_residue_ids = set()
        self._binding_site_roles = {}
        self._residue_interaction_types = {}
        self._key_residues = set()

        if binding_site_residues:
            for entry in binding_site_residues:
                # N-code type guard: entry may be tuple/list from external source
                if not isinstance(entry, (tuple, list)) or len(entry) < 3:
                    logger.warning("set_data: invalid binding_site_residues entry type=%s", type(entry).__name__)
                    continue
                res_name, res_id, chain = entry[0], entry[1], entry[2]
                is_donor = entry[3] if len(entry) > 3 else False
                is_acceptor = entry[4] if len(entry) > 4 else False
                self._binding_residue_ids.add((chain, res_id))
                self._binding_site_roles[(chain, res_id)] = (is_donor, is_acceptor)
        else:
            # Fallback: populate from interactions first
            for inter in self.interactions:
                self._binding_residue_ids.add((inter.chain, inter.residue_id))

        # Auto-populate binding site: adaptive radius based on ligand extent + 5A buffer
        if not self._binding_residue_ids and self.receptor and self.pose and self.pose.atom_coords:
            # Compute ligand extent for adaptive radius
            lcoords = self.pose.atom_coords
            lx_vals = [c[0] for c in lcoords]
            ly_vals = [c[1] for c in lcoords]
            lz_vals = [c[2] for c in lcoords]
            ligand_extent = max(
                max(lx_vals) - min(lx_vals),
                max(ly_vals) - min(ly_vals),
                max(lz_vals) - min(lz_vals),
                2.0  # minimum extent
            )
            # Adaptive radius: half the ligand extent + 5A buffer, clamped 6-12A
            adaptive_radius = max(6.0, min(12.0, ligand_extent / 2.0 + 5.0))
            self._auto_populate_binding_site(radius=adaptive_radius)

        # BUG-DOCK-001 fix: Always populate interaction types from interactions list
        # This ensures H-bond=blue, hydrophobic=yellow coloring works regardless
        # of how the binding site was populated (explicit list, interactions, or auto-populate).
        type_priority = {
            "salt_bridge": 5, "hydrogen_bond": 4, "pi_stacking": 3,
            "halogen_bond": 2, "hydrophobic": 1,
        }
        for inter in self.interactions:
            # N-code type guard: inter.type from external PDB/docking data
            inter_type = inter.type if isinstance(inter.type, str) else str(inter.type) if inter.type is not None else ""
            key = (inter.chain, inter.residue_id)
            if key in self._binding_residue_ids:
                current = self._residue_interaction_types.get(key)
                if current is None or type_priority.get(inter_type, 0) > type_priority.get(current, 0):
                    self._residue_interaction_types[key] = inter_type
                self._key_residues.add(key)

        # Compute center and scale
        self._compute_view_params()
        self.update()

    def _auto_populate_binding_site(self, radius: float = 8.0):
        """Auto-extract binding site residues within `radius` Angstroms of ligand center.

        Used as fallback when binding_site_residues is not provided and no
        interactions are available. Populates _binding_residue_ids and _binding_site_roles.
        """
        if not self.pose or not self.pose.atom_coords or not self.receptor:
            return

        # Compute ligand center
        lx = sum(c[0] for c in self.pose.atom_coords) / len(self.pose.atom_coords)
        ly = sum(c[1] for c in self.pose.atom_coords) / len(self.pose.atom_coords)
        lz = sum(c[2] for c in self.pose.atom_coords) / len(self.pose.atom_coords)

        # H-bond donor/acceptor element sets
        hbond_donors = {"N", "O"}
        hbond_acceptors = {"N", "O", "S", "F"}

        seen = set()
        for chain_id, residues in self.receptor.residues.items():
            for res in residues:
                key = (res.chain, res.residue_id)
                if key in seen:
                    continue
                # Check if any atom of this residue is within radius of ligand center
                for atom in res.atoms:
                    dist = math.sqrt(
                        (atom.x - lx) ** 2 + (atom.y - ly) ** 2 + (atom.z - lz) ** 2
                    )
                    if dist <= radius:
                        seen.add(key)
                        self._binding_residue_ids.add(key)
                        # Determine H-bond roles from residue atoms
                        is_donor = any(a.element in hbond_donors for a in res.atoms)
                        is_acceptor = any(a.element in hbond_acceptors for a in res.atoms)
                        self._binding_site_roles[key] = (is_donor, is_acceptor)
                        break  # found one atom in range, no need to check others

        # Map interaction types to residues (for color-coding by interaction)
        # Priority: salt_bridge > hydrogen_bond > pi_stacking > halogen_bond > hydrophobic
        type_priority = {
            "salt_bridge": 5, "hydrogen_bond": 4, "pi_stacking": 3,
            "halogen_bond": 2, "hydrophobic": 1,
        }
        for inter in self.interactions:
            # N-code type guard: inter.type from external PDB/docking data
            inter_type = inter.type if isinstance(inter.type, str) else str(inter.type) if inter.type is not None else ""
            key = (inter.chain, inter.residue_id)
            self._key_residues.add(key)
            current = self._residue_interaction_types.get(key)
            if current is None or type_priority.get(inter_type, 0) > type_priority.get(current, 0):
                self._residue_interaction_types[key] = inter_type

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

        # Background — uses _bg_color (dark default, white for PDF export)
        painter.fillRect(self.rect(), self._bg_color)

        if not self.receptor and not self.pose:
            no_data_color = QColor(100, 100, 100) if self._is_light_background() else QColor(150, 150, 150)
            painter.setPen(no_data_color)
            painter.setFont(_get_korean_font(14))  # Rule Q: 한글 fallback
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

        # M497: SIMULATION_MODE 워터마크 — HEURISTIC ESTIMATE 오버레이 (FP-15 fix, Rule M)
        # mock 결과를 진짜처럼 보이는 3D 뷰어에도 "Not Vina" 명시 필수
        if _DOCKING_SIMULATION_MODE or not _VINA_AVAIL:
            self._draw_heuristic_watermark(painter)

        painter.end()

    def _draw_gradient_sphere(self, painter: QPainter, sx: float, sy: float,
                              r: float, color: QColor, alpha: int = 255):
        """Draw a sphere with radial gradient for 3D shading effect.

        Args:
            painter: Active QPainter
            sx, sy: Screen center coordinates
            r: Sphere radius in pixels
            color: Base color of the sphere
            alpha: Overall alpha (0-255)
        """
        base = QColor(color.red(), color.green(), color.blue(), alpha)
        gradient = QRadialGradient(QPointF(sx - r * 0.3, sy - r * 0.3), r * 1.5)
        gradient.setColorAt(0.0, QColor(
            min(255, base.red() + 180), min(255, base.green() + 180),
            min(255, base.blue() + 180), alpha))   # bright specular (near-white)
        gradient.setColorAt(0.45, base)             # base color
        gradient.setColorAt(1.0, QColor(
            max(0, base.red() - 120), max(0, base.green() - 120),
            max(0, base.blue() - 120), alpha))      # deep shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(sx, sy), r, r)

    def _draw_protein(self, painter: QPainter):
        """Draw protein backbone using current backbone_style.

        v1.3 visual hierarchy:
        - Non-binding-site residues: thin ribbon + tiny dots (3px) = dim background
        - Binding-site residues: medium spheres (8px) with labels (drawn separately)
        - Ligand: large spheres (15px+) with warm colors + cyan halo (drawn separately)
        """
        if self.backbone_style == 'ribbon':
            self._draw_ribbon_backbone(painter)
        else:
            self._draw_trace_backbone(painter)

        # Draw non-binding-site residue atoms as tiny dots for spatial context
        self._draw_protein_background_atoms(painter)

    def _draw_protein_background_atoms(self, painter: QPainter):
        """Draw non-binding-site protein atoms as tiny dots (3-4px).

        Creates visual hierarchy: these are dim background context,
        clearly distinct from the prominent binding site and ligand atoms.
        """
        if not self.receptor:
            return
        light_bg = self._is_light_background()
        # Cool dim color for background protein atoms
        dot_color = QColor(120, 120, 150, 60) if not light_bg else QColor(160, 160, 180, 80)
        dot_radius = 3.0  # 3px — tiny dots for spatial context

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_color))

        for chain_id, residues in self.receptor.residues.items():
            for res in residues:
                key = (res.chain, res.residue_id)
                if key in self._binding_residue_ids:
                    continue  # Skip binding site residues (drawn separately with detail)
                ca = res.ca_position
                if ca:
                    sx, sy, sz = self._project(*ca)
                    # Depth-based alpha: farther = more transparent
                    depth_alpha = max(20, min(60, int(50 - sz * 0.2)))
                    dot_c = QColor(dot_color.red(), dot_color.green(),
                                   dot_color.blue(), depth_alpha)
                    painter.setBrush(QBrush(dot_c))
                    painter.drawEllipse(QPointF(sx, sy), dot_radius, dot_radius)

    def _draw_trace_backbone(self, painter: QPainter):
        """Draw protein backbone as thin C-alpha trace (legacy)"""
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

    def _domain_color(self, residue_idx: int) -> QColor:
        """Return domain ribbon color by residue index (D5 fix).

        Domain boundaries based on ALDH2 (Bisawas 2022 Int. J. Mol. Sci. 23:11746):
        - 1..DOMAIN_BOUNDARY_NAD (150): NAD binding — blue
        - 151..DOMAIN_BOUNDARY_CAT (300): Catalytic — green
        - 301+: Bridging — orange
        For non-ALDH structures the coloring still provides visual variety.
        """
        if residue_idx <= DOMAIN_BOUNDARY_NAD:       # ≤150: NAD binding
            return DOMAIN_COLORS['NAD']
        elif residue_idx <= DOMAIN_BOUNDARY_CAT:     # 151-300: Catalytic
            return DOMAIN_COLORS['Catalytic']
        else:                                         # 301+: Bridging
            return DOMAIN_COLORS['Bridging']

    def _draw_ribbon_backbone(self, painter: QPainter):
        """Draw protein backbone as smooth ribbon spline through C-alpha atoms.

        Uses QPainterPath with cubic bezier curves for smooth interpolation.
        Width 5px, domain-colored with partial transparency for depth perception.
        Domain coloring follows Bisawas 2022 (D5 fix).
        """
        for chain_id, residues in self.receptor.residues.items():
            # Collect projected CA positions with depth + residue_id for domain coloring
            ca_points = []   # (sx, sy, sz, residue_id)
            for res in residues:
                ca = res.ca_position
                if ca is None:
                    # Chain break: draw accumulated segment, start fresh
                    if len(ca_points) >= 2:
                        self._draw_ribbon_segment(painter, ca_points)
                    ca_points = []
                    continue
                sx, sy, sz = self._project(*ca)
                ca_points.append((sx, sy, sz, res.residue_id))

            # Draw remaining segment
            if len(ca_points) >= 2:
                self._draw_ribbon_segment(painter, ca_points)

    def _draw_ribbon_segment(self, painter: QPainter, points: list):
        """Draw a single ribbon segment through a list of (sx, sy, sz[, res_id]) points.

        Uses cubic bezier curves for smooth interpolation with depth-based
        opacity for a 3D ribbon effect. Domain color applied via _domain_color().
        """
        if len(points) < 2:
            return

        # Build QPainterPath with cubic bezier interpolation
        path = QPainterPath()
        path.moveTo(QPointF(points[0][0], points[0][1]))

        if len(points) == 2:
            path.lineTo(QPointF(points[1][0], points[1][1]))
        else:
            # Catmull-Rom to Bezier conversion for smooth spline
            for i in range(len(points) - 1):
                p0 = points[max(0, i - 1)]
                p1 = points[i]
                p2 = points[min(len(points) - 1, i + 1)]
                p3 = points[min(len(points) - 1, i + 2)]

                # Catmull-Rom tangent -> Bezier control points
                cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
                cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
                cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
                cp2y = p2[1] - (p3[1] - p1[1]) / 6.0

                path.cubicTo(
                    QPointF(cp1x, cp1y),
                    QPointF(cp2x, cp2y),
                    QPointF(p2[0], p2[1])
                )

        # Average depth for opacity — adapt to background brightness
        avg_z = sum(p[2] for p in points) / len(points)
        # Domain color based on midpoint residue_id (element 3 if present, else default)
        mid_idx = len(points) // 2
        mid_res_id = points[mid_idx][3] if len(points[mid_idx]) > 3 else 0
        # N-code: type guard — residue_id must be int
        if not isinstance(mid_res_id, int):
            logger.warning("_draw_ribbon_segment: mid_res_id type=%s, using 0", type(mid_res_id).__name__)
            mid_res_id = 0
        domain_col = self._domain_color(mid_res_id)

        # D5 fix: domain-colored ribbon (Bisawas 2022 표준)
        if self._is_light_background():
            # White background: domain color with higher alpha for visibility
            depth_alpha = max(100, min(220, int(180 - avg_z * 0.3)))
            ribbon_color = QColor(domain_col.red(), domain_col.green(), domain_col.blue(), depth_alpha)
            ribbon_width = 6.0
        else:
            depth_alpha = max(60, min(180, int(130 - avg_z * 0.5)))
            ribbon_color = QColor(domain_col.red(), domain_col.green(), domain_col.blue(), depth_alpha)
            ribbon_width = 5.0

        pen = QPen(ribbon_color, ribbon_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _draw_binding_site(self, painter: QPainter):
        """Draw binding site residues with Discovery Studio level ball&stick rendering.

        M563 격분 9 — 사용자 인용 (2026-03-18T13:25):
        "수용체에서 분자랑 결합하는 부위는 ball&stick 형태로 표현되어야 한다"

        binding_site_style modes:
        - 'ball_stick' (default, Discovery Studio 표준):
            * 원자 = CPK 색상 (C=회색/N=파랑/O=빨강/S=노랑) + radial gradient sphere
            * 결합 = cylinder-shaded 6px (interaction role color로 외곽 강조)
            * 라벨 = 잔기명+번호 + interaction type abbreviation
        - 'stick' (Licorice):
            * 결합만 두꺼운 cylinder (8px)
            * 원자 sphere 없음 (학술 논문 stick 표현)
        - 'wireframe' (Lines, 가장 단순):
            * 1px 단순 선
            * 라벨만

        Color scheme for key interacting residues (by primary interaction type):
        - Blue: H-bond | Yellow: Hydrophobic | Purple: Pi-stacking
        - Red: Salt bridge | Cyan: Halogen bond
        Non-interacting pocket residues use H-bond role coloring:
        - Blue: donor | Red: acceptor | Purple: both | Gray: neutral
        Yellow translucent region: binding pocket highlight
        """
        if not self._binding_residue_ids:
            return

        # M563: binding_site_style 듀스 가드 — Rule N (외부 attr 변경 가능성)
        # 매직넘버 주석: 3종 모드 화이트리스트 (Discovery Studio 표준 + 학술 논문 fallback)
        site_style = self.binding_site_style if isinstance(self.binding_site_style, str) else 'ball_stick'
        if site_style not in ('ball_stick', 'stick', 'wireframe'):
            logger.warning("_draw_binding_site: unknown binding_site_style=%s, fallback to ball_stick", site_style)
            site_style = 'ball_stick'

        # -- Phase 1: Draw yellow pocket highlight behind residues --
        pocket_screen_coords = []
        for chain_id, residues in self.receptor.residues.items():
            for res in residues:
                if (res.chain, res.residue_id) not in self._binding_residue_ids:
                    continue
                ca = res.ca_position
                if ca:
                    sx, sy, _ = self._project(*ca)
                    pocket_screen_coords.append((sx, sy))

        if len(pocket_screen_coords) >= 3:
            xs = [c[0] for c in pocket_screen_coords]
            ys = [c[1] for c in pocket_screen_coords]
            cx = (min(xs) + max(xs)) / 2
            cy = (min(ys) + max(ys)) / 2
            rx = (max(xs) - min(xs)) / 2 + 30
            ry = (max(ys) - min(ys)) / 2 + 30
            # Soft-edge radial gradient for pocket highlight (15% center, 0% edge)
            pocket_grad = QRadialGradient(QPointF(cx, cy), max(rx, ry))
            pocket_grad.setColorAt(0.0, QColor(255, 230, 50, 38))   # ~15% center
            pocket_grad.setColorAt(0.7, QColor(255, 230, 50, 20))   # fade
            pocket_grad.setColorAt(1.0, QColor(255, 230, 50, 0))    # transparent edge
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pocket_grad))
            painter.drawEllipse(QPointF(cx, cy), rx, ry)

        # -- Phase 2: Draw residue stick models --
        for chain_id, residues in self.receptor.residues.items():
            for res in residues:
                key = (res.chain, res.residue_id)
                if key not in self._binding_residue_ids:
                    continue

                is_key_residue = key in self._key_residues

                # Determine residue color: interaction type for key residues,
                # H-bond role for non-interacting pocket residues
                if is_key_residue and key in self._residue_interaction_types:
                    inter_type = self._residue_interaction_types[key]
                    role_color = RESIDUE_INTERACTION_COLORS.get(inter_type, BINDING_NEUTRAL_COLOR)
                else:
                    is_donor, is_acceptor = self._binding_site_roles.get(key, (False, False))
                    if is_donor and is_acceptor:
                        role_color = HBOND_BOTH_COLOR
                    elif is_donor:
                        role_color = HBOND_DONOR_COLOR
                    elif is_acceptor:
                        role_color = HBOND_ACCEPTOR_COLOR
                    else:
                        role_color = BINDING_NEUTRAL_COLOR

                role_qcolor = QColor(
                    int(role_color[0] * 255),
                    int(role_color[1] * 255),
                    int(role_color[2] * 255),
                )

                # Draw bonds between consecutive heavy atoms in residue (stick model)
                heavy_atoms = [a for a in res.atoms
                               if a.name.strip() not in ("H", "HA", "HB", "HG",
                                                          "HB2", "HB3", "HG2", "HG3",
                                                          "HD1", "HD2", "HE1", "HE2")]
                projected = []
                for atom in heavy_atoms:
                    sx, sy, sz = self._project(atom.x, atom.y, atom.z)
                    projected.append((sx, sy, sz, atom))

                # M563 격분 9: binding_site_style 별 결합 두께 조절
                # 매직넘버 주석:
                #   ball_stick 6.0/4.5 = Discovery Studio 표준 (학생 시연 기준)
                #   stick      8.0/6.0 = VMD/PyMOL Licorice 표준 (학술 논문 stick 표현)
                #   wireframe  1.5/1.0 = Lines 모드 (단순)
                if site_style == 'ball_stick':
                    stick_width = 6.0 if is_key_residue else 4.5
                elif site_style == 'stick':
                    stick_width = 8.0 if is_key_residue else 6.0
                else:  # wireframe
                    stick_width = 1.5 if is_key_residue else 1.0

                # M563: ball_stick + stick 모드는 cylinder gradient (Discovery Studio 수준 3D 음영)
                # wireframe은 평면 선
                if site_style in ('ball_stick', 'stick'):
                    # cylinder-shaded bond — _draw_cylinder_line 활용 (학술 표준)
                    for i_a in range(len(heavy_atoms)):
                        for j_a in range(i_a + 1, len(heavy_atoms)):
                            a1, a2 = heavy_atoms[i_a], heavy_atoms[j_a]
                            dist = math.sqrt(
                                (a1.x - a2.x)**2 + (a1.y - a2.y)**2 + (a1.z - a2.z)**2
                            )
                            bond_thresh = (COVALENT_RADII.get(a1.element, 0.77)
                                           + COVALENT_RADII.get(a2.element, 0.77)
                                           + BOND_TOLERANCE)
                            if dist < bond_thresh:
                                # 결합 alpha — depth 기반 (사용자 격분 11: 학회 논문 수준 음영)
                                avg_z = (projected[i_a][2] + projected[j_a][2]) / 2.0
                                bond_alpha = max(150, min(255, int(220 - avg_z * 0.4)))
                                bond_color = QColor(
                                    role_qcolor.red(), role_qcolor.green(),
                                    role_qcolor.blue(), bond_alpha,
                                )
                                self._draw_cylinder_line(
                                    painter,
                                    projected[i_a][0], projected[i_a][1],
                                    projected[j_a][0], projected[j_a][1],
                                    stick_width, bond_color,
                                )
                else:
                    # wireframe: 단순 1px 라인
                    stick_pen = QPen(role_qcolor, stick_width)
                    stick_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(stick_pen)
                    for i_a in range(len(heavy_atoms)):
                        for j_a in range(i_a + 1, len(heavy_atoms)):
                            a1, a2 = heavy_atoms[i_a], heavy_atoms[j_a]
                            dist = math.sqrt(
                                (a1.x - a2.x)**2 + (a1.y - a2.y)**2 + (a1.z - a2.z)**2
                            )
                            bond_thresh = (COVALENT_RADII.get(a1.element, 0.77)
                                           + COVALENT_RADII.get(a2.element, 0.77)
                                           + BOND_TOLERANCE)
                            if dist < bond_thresh:
                                painter.drawLine(
                                    QPointF(projected[i_a][0], projected[i_a][1]),
                                    QPointF(projected[j_a][0], projected[j_a][1])
                                )

                # M563 격분 9: 원자 sphere — ball_stick 모드만 그림
                # stick/wireframe 모드는 결합만 (학술 stick 표현)
                # 매직넘버 주석:
                #   ball_stick 12.0/9.0 = Discovery Studio 표준 (sigma sphere 시각화)
                #     (이전 8.0/6.0 → 격분 9 답해서 확장: 학생 식별 가능 수준)
                if site_style == 'ball_stick':
                    base_radius = 12.0 if is_key_residue else 9.0
                    # Sort by depth (back-to-front) for correct occlusion
                    projected_sorted = sorted(projected, key=lambda p: -p[2])
                    for sx, sy, sz, atom in projected_sorted:
                        # Depth-based radius: closer atoms appear larger
                        depth_factor = max(0.5, min(1.5, 1.0 + sz * 0.003))
                        atom_radius = base_radius * depth_factor

                        # N-code type guard: atom.element from external PDB data
                        atom_elem = atom.element if isinstance(atom.element, str) else str(atom.element) if atom.element is not None else "C"
                        # M563: Discovery Studio 표준 CPK 색상 사용 — element_color
                        # 격분 9: "지금 분자 그리는거처럼" → 동일 CPK 적용
                        elem_color = ELEMENT_COLORS.get(atom_elem, (0.5, 0.5, 0.5))
                        # Binding site carbons slightly brighter for visibility
                        if atom_elem == "C":
                            elem_color = (0.35, 0.35, 0.35) if is_key_residue else (0.3, 0.3, 0.3)

                        # Depth-based opacity: farther atoms = more transparent
                        # 매직넘버 주석: 230/170 = key/non-key alpha (Discovery Studio prominence)
                        base_alpha = 230 if is_key_residue else 170
                        depth_opacity = max(80, min(base_alpha, int(base_alpha - sz * 0.4)))

                        atom_qcolor = QColor(
                            int(elem_color[0] * 255),
                            int(elem_color[1] * 255),
                            int(elem_color[2] * 255),
                        )
                        # M563: key residue는 외곽 강조 — interaction role 색 ring
                        if is_key_residue:
                            # 외곽 ring (interaction type 컬러로 강조 — 학회 발표 스타일)
                            outline_pen = QPen(role_qcolor, 2.0)
                            painter.setPen(outline_pen)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawEllipse(QPointF(sx, sy), atom_radius + 1.5, atom_radius + 1.5)
                        # 메인 gradient sphere (CPK 색)
                        self._draw_gradient_sphere(
                            painter, sx, sy, atom_radius, atom_qcolor, depth_opacity
                        )

                # Draw residue label at CA
                ca = res.ca_position
                if ca:
                    sx, sy, _ = self._project(*ca)
                    painter.setPen(role_qcolor)
                    if is_key_residue:
                        # Key residues get larger bold labels with interaction type
                        painter.setFont(_get_korean_font(9, bold=True))  # Rule Q D6 fix
                        inter_type = self._residue_interaction_types.get(key, "")
                        type_abbr = {
                            "hydrogen_bond": "H", "hydrophobic": "hp",
                            "pi_stacking": "pi", "salt_bridge": "sb",
                            "halogen_bond": "X",
                        }.get(inter_type, "")
                        label = f"{res.name}{res.residue_id}"
                        if type_abbr:
                            label += f" [{type_abbr}]"
                        # Draw label background for readability
                        fm = painter.fontMetrics()
                        text_width = fm.horizontalAdvance(label)
                        text_height = fm.height()
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(20, 20, 30, 180))
                        painter.drawRoundedRect(
                            int(sx) + 3, int(sy) - text_height - 3,
                            text_width + 6, text_height + 4, 3, 3
                        )
                        painter.setPen(role_qcolor)
                        painter.drawText(int(sx) + 6, int(sy) - 5, label)
                    else:
                        # Non-key residues get smaller labels
                        painter.setFont(_get_korean_font(7))  # Rule Q D6 fix
                        painter.drawText(int(sx) + 5, int(sy) - 5,
                                         f"{res.name}{res.residue_id}")

    def _detect_ligand_bonds(self):
        """Detect bonds and estimate bond orders from ligand geometry.

        Returns list of (i, j, bond_order) tuples where bond_order is:
        1.0 = single, 1.5 = aromatic, 2.0 = double, 3.0 = triple.
        Uses DockingPose.bond_orders if available, otherwise heuristic detection.
        """
        if not self.pose or not self.pose.atom_coords:
            return []

        coords = self.pose.atom_coords
        elements = self.pose.atom_elements

        # Try RDKit-based bond order detection from SMILES if available
        bond_info = []
        rdkit_bonds = {}
        try:
            from rdkit import Chem
            if hasattr(self.pose, 'smiles') and self.pose.smiles:
                mol = Chem.MolFromSmiles(self.pose.smiles)
                if mol is not None:
                    Chem.Kekulize(mol, clearAromaticFlags=False)
                    for bond in mol.GetBonds():
                        bi, bj = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                        key = (min(bi, bj), max(bi, bj))
                        bt = bond.GetBondType()
                        if bond.GetIsAromatic():
                            rdkit_bonds[key] = 1.5
                        elif bt == Chem.BondType.DOUBLE:
                            rdkit_bonds[key] = 2.0
                        elif bt == Chem.BondType.TRIPLE:
                            rdkit_bonds[key] = 3.0
                        else:
                            rdkit_bonds[key] = 1.0
        except ImportError as e:
            logger.warning("RDKit import failed for bond order detection: %s", e)

        # Distance-based bond detection using element-pair covalent radii + tolerance
        for i in range(len(coords)):
            ei = elements[i] if i < len(elements) else "C"
            # N-code type guard: atom_elements from external docking data
            if not isinstance(ei, str):
                ei = str(ei) if ei is not None else "C"
            if ei == "H":
                continue
            for j in range(i + 1, len(coords)):
                ej = elements[j] if j < len(elements) else "C"
                if not isinstance(ej, str):
                    ej = str(ej) if ej is not None else "C"
                if ej == "H":
                    continue
                dist = math.sqrt(
                    sum((a - b) ** 2 for a, b in zip(coords[i], coords[j]))
                )
                # Element-pair adaptive threshold: sum of covalent radii + 0.4A tolerance
                threshold = (COVALENT_RADII.get(ei, 0.77)
                             + COVALENT_RADII.get(ej, 0.77)
                             + BOND_TOLERANCE)
                if dist < threshold:
                    key = (min(i, j), max(i, j))
                    bo = rdkit_bonds.get(key, 1.0)
                    # Heuristic fallback: short C=O, C=C bonds
                    if bo == 1.0 and not rdkit_bonds:
                        pair = frozenset([ei, ej])
                        if pair == frozenset(["C", "O"]) and dist < 1.30:
                            bo = 2.0
                        elif pair == frozenset(["C", "C"]) and dist < 1.38:
                            bo = 2.0 if dist < 1.34 else 1.5
                        elif pair == frozenset(["C", "N"]) and dist < 1.32:
                            bo = 2.0
                    bond_info.append((i, j, bo))

        return bond_info

    def _make_cylinder_brush(self, sx1: float, sy1: float, sx2: float, sy2: float,
                             width: float, color: QColor) -> QBrush:
        """Create a linear gradient brush perpendicular to bond for cylinder effect.

        Lighter on top side, darker on bottom side to simulate a 3D cylinder.
        """
        dx = sx2 - sx1
        dy = sy2 - sy1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1.0:
            return QBrush(color)
        nx = -dy / length * width * 0.5
        ny = dx / length * width * 0.5
        mx = (sx1 + sx2) / 2.0
        my = (sy1 + sy2) / 2.0
        grad = QLinearGradient(
            QPointF(mx + nx, my + ny),   # top edge of cylinder
            QPointF(mx - nx, my - ny),   # bottom edge of cylinder
        )
        grad.setColorAt(0.0, QColor(
            min(255, color.red() + 60), min(255, color.green() + 60),
            min(255, color.blue() + 60), color.alpha()))   # light top
        grad.setColorAt(0.45, color)                        # base center
        grad.setColorAt(1.0, QColor(
            max(0, color.red() - 50), max(0, color.green() - 50),
            max(0, color.blue() - 50), color.alpha()))     # dark bottom
        return QBrush(grad)

    def _draw_cylinder_line(self, painter: QPainter, sx1: float, sy1: float,
                            sx2: float, sy2: float, width: float, color: QColor):
        """Draw a single bond stroke as a cylinder-shaded rectangle with round caps."""
        dx = sx2 - sx1
        dy = sy2 - sy1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1.0:
            return
        hw = width * 0.5
        nx = -dy / length * hw
        ny = dx / length * hw
        path = QPainterPath()
        path.moveTo(QPointF(sx1 + nx, sy1 + ny))
        path.lineTo(QPointF(sx2 + nx, sy2 + ny))
        path.lineTo(QPointF(sx2 - nx, sy2 - ny))
        path.lineTo(QPointF(sx1 - nx, sy1 - ny))
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._make_cylinder_brush(sx1, sy1, sx2, sy2, width, color))
        painter.drawPath(path)
        # Round caps at ends
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(sx1, sy1), hw, hw)
        painter.drawEllipse(QPointF(sx2, sy2), hw, hw)

    def _draw_bond_line(self, painter: QPainter, sx1: float, sy1: float,
                        sx2: float, sy2: float, bond_order: float,
                        color: QColor, base_width: float = 6.0):
        """Draw a bond with proper bond order rendering (single/double/aromatic/triple).

        Uses cylinder-gradient shading for 3D appearance.
        Double bonds = two parallel cylinders offset 3px.
        Aromatic (1.5) = one solid cylinder + one dashed parallel line.
        Triple = three parallel cylinders.
        """
        dx = sx2 - sx1
        dy = sy2 - sy1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1.0:
            return

        # Perpendicular unit vector for offset
        nx = -dy / length
        ny = dx / length

        if bond_order >= 2.8:
            # Triple bond: three parallel cylinders
            offset = 4.0
            for off, w in [(0.0, base_width), (-offset, base_width * 0.7), (offset, base_width * 0.7)]:
                self._draw_cylinder_line(
                    painter, sx1 + nx * off, sy1 + ny * off,
                    sx2 + nx * off, sy2 + ny * off, w, color)
        elif bond_order >= 1.8:
            # Double bond: two parallel cylinders
            offset = 3.0
            w = base_width * 0.8
            self._draw_cylinder_line(
                painter, sx1 + nx * offset, sy1 + ny * offset,
                sx2 + nx * offset, sy2 + ny * offset, w, color)
            self._draw_cylinder_line(
                painter, sx1 - nx * offset, sy1 - ny * offset,
                sx2 - nx * offset, sy2 - ny * offset, w, color)
        elif bond_order >= 1.3:
            # Aromatic (1.5): one solid cylinder + one thin dashed
            offset = 3.0
            self._draw_cylinder_line(
                painter, sx1 - nx * offset * 0.5, sy1 - ny * offset * 0.5,
                sx2 - nx * offset * 0.5, sy2 - ny * offset * 0.5, base_width, color)
            pen_dash = QPen(color, base_width * 0.5, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_dash)
            painter.drawLine(
                QPointF(sx1 + nx * offset * 0.5, sy1 + ny * offset * 0.5),
                QPointF(sx2 + nx * offset * 0.5, sy2 + ny * offset * 0.5),
            )
        else:
            # Single bond: one cylinder
            self._draw_cylinder_line(painter, sx1, sy1, sx2, sy2, base_width, color)

    def _draw_ligand(self, painter: QPainter):
        """Draw ligand atoms as ball-and-stick with radial gradient spheres.

        Enhanced rendering v1.3:
        - 1.5x radius multiplier for ligand atoms (clearly larger than protein)
        - Warm color palette (orange C, golden S) distinct from protein CPK
        - Cyan outline/halo around each atom for immediate visual identification
        - Depth-based opacity: alpha = 255 - depth_ratio * 100
        - Thick cylindrical bonds (6px) with bond order distinction
        """
        if not self.pose.atom_coords:
            return

        coords = self.pose.atom_coords
        elements = self.pose.atom_elements

        # Detect bonds with bond orders
        bond_list = self._detect_ligand_bonds()

        # Draw bonds with bond order rendering (warm-tinted bond color)
        for i, j, bo in bond_list:
            sx1, sy1, sz1 = self._project(*coords[i])
            sx2, sy2, sz2 = self._project(*coords[j])
            # Depth-based bond opacity
            avg_z = (sz1 + sz2) / 2.0
            bond_alpha = max(100, min(240, int(220 - avg_z * 0.4)))
            bond_color = QColor(255, 220, 180, bond_alpha)  # Warm-tinted bonds
            self._draw_bond_line(painter, sx1, sy1, sx2, sy2, bo, bond_color, 6.0)

        # Collect projected atoms for depth-sorting (back-to-front)
        projected = []
        for i, (x, y, z) in enumerate(coords):
            elem = elements[i] if i < len(elements) else "C"
            # N-code type guard: atom_elements from external docking data
            if not isinstance(elem, str):
                elem = str(elem) if elem is not None else "C"
            if elem == "H":
                continue  # skip hydrogens for clarity
            sx, sy, sz = self._project(x, y, z)
            projected.append((sx, sy, sz, elem))

        projected.sort(key=lambda p: -p[2])  # back-to-front

        # Compute depth range for normalized opacity
        if projected:
            z_values = [p[2] for p in projected]
            z_min, z_max = min(z_values), max(z_values)
            z_range = z_max - z_min if z_max > z_min else 1.0
        else:
            z_min, z_range = 0.0, 1.0

        for sx, sy, sz, elem in projected:
            # Use warm ligand color palette (distinct from protein CPK)
            color = LIGAND_ELEMENT_COLORS.get(elem, (0.8, 0.5, 0.2))

            # 1.5x radius multiplier: ligand atoms significantly larger than protein
            raw_radius = ELEMENT_RADII.get(elem, 0.5) * 20.0 * 1.5  # 1.5x multiplier
            radius = max(14.0, raw_radius)  # min 14px (was 10px)

            # Depth-based opacity: far atoms more transparent
            depth_ratio = (sz - z_min) / z_range if z_range > 0 else 0.0
            depth_alpha = max(155, int(255 - depth_ratio * 100))

            atom_qcolor = QColor(
                int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)
            )

            # Draw cyan outline/halo first (behind the sphere)
            outline_r = radius + LIGAND_OUTLINE_WIDTH
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(
                LIGAND_OUTLINE_COLOR.red(), LIGAND_OUTLINE_COLOR.green(),
                LIGAND_OUTLINE_COLOR.blue(), max(80, depth_alpha - 60))))
            painter.drawEllipse(QPointF(sx, sy), outline_r, outline_r)

            # Draw the main gradient sphere on top
            self._draw_gradient_sphere(
                painter, sx, sy, radius, atom_qcolor, depth_alpha
            )

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

            # Draw interaction line with type-specific style
            # N-code type guard: inter.type from external docking data
            itype = inter.type if isinstance(inter.type, str) else str(inter.type) if inter.type is not None else ""
            color = INTERACTION_COLORS.get(itype, (0.5, 0.5, 0.5))
            icolor = QColor(int(color[0]*255), int(color[1]*255), int(color[2]*255))

            if itype == "hydrogen_bond":
                # H-bonds: dashed cyan lines (2px)
                pen = QPen(icolor, 2, Qt.PenStyle.DashLine)
            elif itype == "hydrophobic":
                # Hydrophobic contacts: dotted gray-orange lines (1.5px)
                pen = QPen(icolor, 2, Qt.PenStyle.DotLine)
            elif itype == "pi_stacking":
                # Pi-stacking: draw as parallel orange double-line
                pen = QPen(icolor, 2, Qt.PenStyle.SolidLine)
                # Draw two parallel offset lines for pi-stacking
                dx_line = psx - lsx
                dy_line = psy - lsy
                line_len = math.sqrt(dx_line * dx_line + dy_line * dy_line)
                if line_len > 1.0:
                    nx = -dy_line / line_len * 3.0  # 3px offset
                    ny = dx_line / line_len * 3.0
                    painter.setPen(pen)
                    painter.drawLine(
                        QPointF(lsx + nx, lsy + ny), QPointF(psx + nx, psy + ny))
                    painter.drawLine(
                        QPointF(lsx - nx, lsy - ny), QPointF(psx - nx, psy - ny))
                    # Skip the single drawLine below; already drawn as parallel pair
                    # Still draw label below
                    pen = None  # signal to skip single line
            else:
                # Salt bridge, halogen bond, etc.: dashed
                pen = QPen(icolor, 2, Qt.PenStyle.DashLine)

            if pen is not None:
                painter.setPen(pen)
                painter.drawLine(QPointF(lsx, lsy), QPointF(psx, psy))

            # Distance + interaction type label at midpoint
            mx = (lsx + psx) / 2
            my = (lsy + psy) / 2

            # Interaction type abbreviation
            type_display = {
                "hydrogen_bond": "H-bond",
                "hydrophobic": "Hydrophobic",
                "pi_stacking": "Pi-stack",
                "salt_bridge": "Salt bridge",
                "halogen_bond": "Halogen",
            }
            # Rule N: isinstance guard for type_display
            if not isinstance(type_display, dict): type_display = {}
            type_label = type_display.get(itype, itype)

            # Draw label background for readability
            painter.setFont(_get_korean_font(7, bold=True))  # Rule Q D6 fix
            fm = painter.fontMetrics()
            dist_text = f"{inter.distance:.1f}A"
            full_label = f"{type_label} {dist_text}"
            text_w = fm.horizontalAdvance(full_label)
            text_h = fm.height()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.drawRoundedRect(
                int(mx) - 2, int(my) - text_h, text_w + 4, text_h + 2, 3, 3
            )

            # Draw colored type label + white distance
            painter.setPen(icolor)
            painter.drawText(int(mx), int(my) - 2, type_label)
            type_w = fm.horizontalAdvance(type_label + " ")
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(_get_korean_font(7))  # Rule Q D6 fix
            painter.drawText(int(mx) + type_w, int(my) - 2, dist_text)

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

    def _is_light_background(self) -> bool:
        """Check if background is light (e.g. white for PDF export)."""
        bg = self._bg_color
        # Perceived luminance formula
        luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        return luminance > 128  # threshold for "light" background

    def _draw_info(self, painter: QPainter):
        """Draw info overlay with semi-transparent panel background."""
        # --- Collect info lines first to measure panel size ---
        info_lines = []  # (text, QColor, QFont)
        font_main = _get_korean_font(10)    # Rule Q D2 fix
        font_legend = _get_korean_font(8)   # Rule Q D2 fix
        # Adapt text/panel colors to background brightness
        light_bg = self._is_light_background()
        text_color = QColor(40, 40, 50) if light_bg else QColor(210, 210, 220)

        if self.receptor:
            info_lines.append((f"Receptor: {self.receptor.name}", text_color, font_main))
        if self.pose:
            info_lines.append((
                f"Pose #{self.pose.pose_id}: {self.pose.affinity_kcal:.2f} kcal/mol",
                text_color, font_main))
        if self.interactions:
            info_lines.append((f"Interactions: {len(self.interactions)}", text_color, font_main))
        if self._binding_residue_ids:
            info_lines.append((
                f"Binding site: {len(self._binding_residue_ids)} residues "
                f"({len(self._key_residues)} interacting)",
                text_color, font_main))

        # Draw info panel background
        if info_lines:
            panel_h = len(info_lines) * 18 + 12
            max_w = 0
            for text, _, font in info_lines:
                painter.setFont(font)
                max_w = max(max_w, painter.fontMetrics().horizontalAdvance(text))
            panel_w = max_w + 20
            painter.setPen(Qt.PenStyle.NoPen)
            panel_bg = QColor(240, 240, 245, 200) if light_bg else QColor(10, 10, 20, 180)
            painter.setBrush(panel_bg)
            painter.drawRoundedRect(4, 4, panel_w, panel_h, 6, 6)

        y = 20
        for text, color, font in info_lines:
            painter.setPen(color)
            painter.setFont(font)
            painter.drawText(12, y, text)
            y += 18

        # --- Legend in a rounded rectangle box ---
        if self._binding_residue_ids and self._residue_interaction_types:
            type_labels = {
                "hydrogen_bond": ("H-Bond", RESIDUE_INTERACTION_COLORS["hydrogen_bond"]),
                "hydrophobic": ("Hydrophobic", RESIDUE_INTERACTION_COLORS["hydrophobic"]),
                "pi_stacking": ("Pi-Stack", RESIDUE_INTERACTION_COLORS["pi_stacking"]),
                "salt_bridge": ("Salt Bridge", RESIDUE_INTERACTION_COLORS["salt_bridge"]),
                "halogen_bond": ("Halogen", RESIDUE_INTERACTION_COLORS["halogen_bond"]),
            }
            seen_types = set(self._residue_interaction_types.values())
            legend_entries = []
            for itype, (label, color) in type_labels.items():
                if itype in seen_types:
                    legend_entries.append((label, QColor(
                        int(color[0]*255), int(color[1]*255), int(color[2]*255))))
            legend_entries.append(("Pocket (no interaction)", QColor(150, 150, 150)))

            if legend_entries:
                painter.setFont(font_legend)
                fm = painter.fontMetrics()
                legend_line_h = 15
                legend_h = len(legend_entries) * legend_line_h + 10
                legend_w = max(fm.horizontalAdvance(f"  {e[0]}") for e in legend_entries) + 20
                legend_x = 4
                legend_y = y + 4

                # Legend box background — adapt to background brightness
                if light_bg:
                    painter.setPen(QPen(QColor(180, 180, 200), 1))
                    painter.setBrush(QColor(240, 240, 245, 210))
                else:
                    painter.setPen(QPen(QColor(60, 60, 80), 1))
                    painter.setBrush(QColor(15, 15, 25, 190))
                painter.drawRoundedRect(legend_x, legend_y, legend_w, legend_h, 5, 5)

                ly = legend_y + 14
                for label, qcolor in legend_entries:
                    painter.setPen(qcolor)
                    symbol = "\u25a0" if label != "Pocket (no interaction)" else "\u25a1"
                    painter.drawText(legend_x + 8, ly, f"{symbol} {label}")
                    ly += legend_line_h

        # Controls hint
        hint_text = "Left drag: rotate | Right drag: pan | Scroll: zoom"
        painter.setFont(_get_korean_font(9))  # Rule Q D2 fix
        fm = painter.fontMetrics()
        hint_w = fm.horizontalAdvance(hint_text) + 16
        hint_h = fm.height() + 6
        hint_x = 4
        hint_y = self.height() - hint_h - 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 10, 20, 150))
        painter.drawRoundedRect(hint_x, hint_y, hint_w, hint_h, 4, 4)
        painter.setPen(QColor(100, 100, 130))
        painter.drawText(hint_x + 8, self.height() - 10, hint_text)

    def _draw_heuristic_watermark(self, painter: QPainter):
        """M497: SIMULATION_MODE 3D 뷰어 워터마크 — HEURISTIC ESTIMATE — Not Vina.

        Rule M: fallback 모드 mock 결과를 3D 뷰어에서도 명시.
        학생이 3D 뷰어 캡처를 학술 보고서에 삽입할 경우 "Not Vina" 경고 표시 의무.
        """
        watermark_lines = [
            "HEURISTIC ESTIMATE",
            "Not AutoDock Vina",
            "결과: 추정값 (실험값 아님)",
        ]

        # 우하단 고정 워터마크 패널 (controls hint 바로 위)
        painter.setFont(_get_korean_font(9, bold=True))  # Rule Q: 한글 폰트
        fm = painter.fontMetrics()
        line_h = fm.height() + 3
        max_w = max(fm.horizontalAdvance(t) for t in watermark_lines) + 20
        wm_h = len(watermark_lines) * line_h + 10
        wm_x = self.width() - max_w - 8
        # controls hint 높이(약 26px) + 간격 8px 위에 배치
        wm_y = self.height() - wm_h - 38  # [MAGIC] 38px: controls hint(26) + gap(12)

        # 반투명 노랑 배경 패널
        painter.setPen(QPen(QColor(200, 50, 50, 220), 2))  # 빨간 테두리
        painter.setBrush(QColor(255, 220, 0, 200))          # 노랑 배경
        painter.drawRoundedRect(wm_x, wm_y, max_w, wm_h, 6, 6)

        # 텍스트
        ty = wm_y + line_h
        for line in watermark_lines:
            painter.setPen(QColor(120, 0, 0))  # 어두운 빨강 텍스트
            painter.drawText(wm_x + 10, ty, line)
            ty += line_h

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
        self.zoom = max(0.05, min(50.0, self.zoom))
        self.update()
