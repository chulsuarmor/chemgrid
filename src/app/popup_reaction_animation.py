#!/usr/bin/env python3
"""
popup_reaction_animation.py -- 3D 반응 메커니즘 애니메이션 팝업
=============================================================
ReactionAnimationEngine이 생성한 ReactionTrajectory를 시각화:
  - OpenGL 3D 볼앤스틱 렌더링 (popup_3d 패턴 재사용, 조명/재질)
  - QPainter 2.5D 폴백 (OpenGL 미지원 환경)
  - QPainter 오버레이: 전하 라벨, 화살표, TS 더블대거
  - matplotlib 에너지 다이어그램 (실시간 마커)
  - 재생/일시정지/리셋/속도 제어
  - 프레임 슬라이더

다크 테마: #1a1a2e 배경, #e0e0e0 텍스트
한국어 라벨
창 크기: ~1000x700
"""

import math
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QFrame, QSplitter,
    QMessageBox, QSizePolicy, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QUrl
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QRadialGradient,
    QPainterPath, QMouseEvent, QWheelEvent, QSurfaceFormat,
    QDesktopServices,
)

logger = logging.getLogger(__name__)

# ============================================================
# OpenGL availability check
# ============================================================
OPENGL_AVAILABLE = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL.GL import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    logger.warning("PyOpenGL not available - using QPainter 2.5D fallback for reaction animation")

# ============================================================
# Optional: matplotlib for energy diagram
# ============================================================
MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    logger.warning("matplotlib not available - energy diagram disabled")

# ============================================================
# Import engine
# ============================================================
try:
    from reaction_animation_engine import (
        ReactionAnimationEngine, ReactionTrajectory, BondChange,
        ChargeLabel, ArrowAnnotation,
    )
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False
    logger.warning("ReactionAnimationEngine not available")

# ============================================================
# CPK Colors (popup_3d와 동일)
# ============================================================
# ============================================================
# Module-level TS capture storage (DryLab 접근용)
# ============================================================
# {reaction_key: {'reactant': QPixmap, 'ts': QPixmap, 'product': QPixmap}}
_captured_ts_images: dict = {}


def get_captured_ts_images() -> dict:
    """DryLab 등 외부 모듈에서 캡처된 전이상태 이미지에 접근.

    Returns:
        dict mapping reaction_key -> {
            'reactant': QPixmap, 'ts': QPixmap, 'product': QPixmap,
            'reactant_path': str, 'ts_path': str, 'product_path': str,
            'comparison_path': str  # 3프레임 횡병렬 비교 이미지 경로
        }
    """
    return _captured_ts_images


def clear_captured_ts_images():
    """캡처 저장소 초기화."""
    _captured_ts_images.clear()


# ============================================================
# CPK Colors (popup_3d와 동일)
# ============================================================
CPK_COLORS = {
    "H": (255, 255, 255), "C": (80, 80, 80), "N": (50, 100, 255),
    "O": (240, 30, 30), "F": (144, 224, 80), "Cl": (31, 240, 31),
    "Br": (130, 60, 30), "I": (148, 0, 148), "S": (255, 255, 48),
    "P": (255, 128, 0), "Na": (171, 92, 242), "K": (143, 64, 212),
    "Ca": (61, 255, 0), "Mg": (138, 255, 0), "Fe": (224, 102, 51),
}
_DEFAULT_CPK = (191, 0, 191)

# CPK 색상 (0.0~1.0 float) — OpenGL용
CPK_COLORS_GL = {
    "H": (1.0, 1.0, 1.0), "C": (0.31, 0.31, 0.31), "N": (0.20, 0.39, 1.0),
    "O": (0.94, 0.12, 0.12), "F": (0.56, 0.88, 0.31), "Cl": (0.12, 0.94, 0.12),
    "Br": (0.51, 0.24, 0.12), "I": (0.58, 0.0, 0.58), "S": (1.0, 1.0, 0.19),
    "P": (1.0, 0.50, 0.0), "Na": (0.67, 0.36, 0.95), "K": (0.56, 0.25, 0.83),
    "Ca": (0.24, 1.0, 0.0), "Mg": (0.54, 1.0, 0.0), "Fe": (0.88, 0.40, 0.20),
}
_DEFAULT_CPK_GL = (0.75, 0.0, 0.75)

# Covalent radii (Angstroms) for ball-and-stick sphere sizing
COVALENT_RADII = {
    "H": 0.31, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
    "Cl": 1.02, "Br": 1.20, "I": 1.39, "S": 1.05, "P": 1.07,
    "B": 0.84, "Si": 1.11, "Na": 1.66, "K": 2.03, "Ca": 1.76,
    "Mg": 1.41, "Fe": 1.32, "Cu": 1.32, "Zn": 1.22,
}
_DEFAULT_COV_R = 0.77  # default covalent radius


def _get_cpk_qcolor(symbol: str) -> QColor:
    # Rule N: 타입 가드 — 모듈 상수 dict
    assert isinstance(CPK_COLORS, dict)
    r, g, b = CPK_COLORS.get(symbol, _DEFAULT_CPK)
    return QColor(r, g, b)


def _get_cpk_gl(symbol: str) -> Tuple[float, float, float]:
    """Get CPK color as (r, g, b) floats for OpenGL."""
    assert isinstance(CPK_COLORS_GL, dict)  # Rule N
    return CPK_COLORS_GL.get(symbol, _DEFAULT_CPK_GL)


def _get_cov_radius(symbol: str) -> float:
    """Get covalent radius in Angstroms."""
    assert isinstance(COVALENT_RADII, dict)  # Rule N
    return COVALENT_RADII.get(symbol, _DEFAULT_COV_R)


# ============================================================
# Dark Theme Palette
# ============================================================
BG_COLOR = QColor("#1a1a2e")
BG_VIEWER = QColor("#0f0f23")
TEXT_COLOR = QColor("#e0e0e0")
ACCENT_BLUE = QColor("#16213e")
ACCENT_GREEN = QColor("#2ecc71")
ACCENT_RED = QColor("#e74c3c")
ACCENT_YELLOW = QColor("#f1c40f")
BOND_DEFAULT = QColor("#8899aa")
BOND_FORMING = QColor(0, 255, 120)   # neon green — high visibility on dark bg
BOND_BREAKING = QColor(255, 60, 60)  # bright red — high visibility on dark bg

def _draw_valid_collision_badge(
    p: QPainter,
    width: int,
    height: int,
    lines: Optional[Tuple[str, str, str]] = None,
) -> None:
    """Draw compact learning cues for the 3D reaction simulation."""
    if lines is None:
        lines = (
            "유효충돌 3D 반응 시뮬레이션",
            "C=C π면과 Br-Br σ*가 정렬되어 접근",
            "녹색=형성, 빨강=절단, 점선=전이상태 결합",
        )
    # Keep this ASCII: some offscreen capture environments do not load Korean/Greek fonts.
    lines = (
        "Valid-collision 3D reaction simulation",
        "Only reaction-center bonds change through the TS",
        "green=forming, red=breaking, dashed=partial bond",
    )
    box_w = min(390, max(300, width - 24))
    box_h = 78
    x = max(10, width - box_w - 12)
    y = 34
    p.setPen(QPen(QColor(70, 140, 210, 210), 1.2))
    p.setBrush(QColor(10, 20, 34, 210))
    p.drawRoundedRect(QRectF(x, y, box_w, box_h), 8, 8)
    p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
    p.setPen(QPen(QColor(210, 235, 255)))
    p.drawText(QRectF(x + 12, y + 8, box_w - 24, 18), Qt.AlignmentFlag.AlignLeft, lines[0])
    p.setFont(QFont("Consolas", 8))
    p.setPen(QPen(QColor(210, 225, 235)))
    p.drawText(QRectF(x + 12, y + 30, box_w - 24, 18), Qt.AlignmentFlag.AlignLeft, lines[1])
    p.setPen(QPen(QColor(180, 255, 205)))
    p.drawText(QRectF(x + 12, y + 50, box_w - 24, 18), Qt.AlignmentFlag.AlignLeft, lines[2])


DARK_STYLE = """
QDialog, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
    font-size: 10pt;
}
QPushButton {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #334;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: bold;
    font-size: 9pt;
}
QPushButton:hover { background-color: #1a3a5c; }
QPushButton:pressed { background-color: #0a1a3e; }
QPushButton:disabled { background-color: #111; color: #555; }
QSlider::groove:horizontal {
    height: 6px; background: #334; border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -5px 0;
    background: #4fc3f7; border-radius: 8px;
}
QComboBox {
    background-color: #16213e; color: #e0e0e0;
    border: 1px solid #334; border-radius: 4px; padding: 4px;
}
QFrame#separator {
    background-color: #334;
}
"""


# ============================================================
# OpenGL 3D Viewer Widget (True 3D with lighting)
# ============================================================

class _ReactionGL3DWidget(QOpenGLWidget if OPENGL_AVAILABLE else QWidget):
    """OpenGL 기반 3D 반응 애니메이션 뷰어.
    popup_3d.py의 Molecule3DViewer와 동일한 조명/재질 설정을 사용하되,
    반응 애니메이션 특화 기능(결합 스타일, 전하 라벨, 화살표, TS 표시)을 QPainter 오버레이로 구현.

    OpenGL 미지원 시 _Viewer3DWidget(QPainter 2.5D) 폴백 사용.
    """

    # Ball-and-stick scaling (popup_3d.py와 동일)
    ATOM_SCALE = 0.78       # covalent_radius * ATOM_SCALE = sphere radius
    BOND_RADIUS = 0.15      # cylinder radius for bonds

    def __init__(self, parent=None):
        if OPENGL_AVAILABLE:
            fmt = QSurfaceFormat()
            fmt.setVersion(2, 1)
            fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
            fmt.setDepthBufferSize(24)
            fmt.setSamples(4)  # 4x MSAA
            super().__init__(parent)
            self.setFormat(fmt)
        else:
            super().__init__(parent)

        self.setMinimumSize(500, 350)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Frame data
        self._coords: Dict[int, Tuple[float, float, float]] = {}
        self._symbols: Dict[int, str] = {}
        self._bonds: Dict[Tuple[int, int], float] = {}
        self._bond_changes: list = []
        self._charge_labels: list = []
        self._arrows: list = []
        self._bond_styles: Dict[Tuple[int, int], str] = {}
        self._label: str = ""
        self._frame_idx: int = 0
        self._n_frames: int = 1
        self._learning_badge_lines: Optional[Tuple[str, str, str]] = None

        # Camera
        self._rot_x = 32.0
        self._rot_y = -46.0
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._last_mouse = None
        self._last_mouse_right = None

        # Computed scene bounds
        self._center = (0.0, 0.0, 0.0)
        self._view_scale = 1.0

        # OpenGL quadrics (lazy init)
        self._sq = None  # sphere quadric
        self._cq = None  # cylinder quadric
        self._gl_initialized = False

    def set_learning_badge(self, title: str, detail: str, legend: str) -> None:
        """Set the compact top-right learning badge for this viewer instance."""
        self._learning_badge_lines = (str(title), str(detail), str(legend))
        self.update()

    def set_frame_data(
        self,
        coords: Dict[int, Tuple[float, float, float]],
        symbols: Dict[int, str],
        bonds: Dict[Tuple[int, int], float],
        bond_changes: list,
        label: str,
        frame_idx: int,
        n_frames: int,
        charge_labels: Optional[list] = None,
        arrows: Optional[list] = None,
        bond_styles: Optional[Dict[Tuple[int, int], str]] = None,
    ):
        # N-guard: validate external trajectory data types
        if not isinstance(coords, dict):
            logger.warning("set_frame_data: coords is not dict (got %s), using empty", type(coords).__name__)
            coords = {}
        if not isinstance(symbols, dict):
            logger.warning("set_frame_data: symbols is not dict (got %s), using empty", type(symbols).__name__)
            symbols = {}
        if not isinstance(bonds, dict):
            logger.warning("set_frame_data: bonds is not dict (got %s), using empty", type(bonds).__name__)
            bonds = {}
        if bond_styles is not None and not isinstance(bond_styles, dict):
            logger.warning("set_frame_data: bond_styles is not dict (got %s), using empty", type(bond_styles).__name__)
            bond_styles = {}
        self._coords = coords
        self._symbols = symbols
        self._bonds = bonds
        self._bond_changes = bond_changes if isinstance(bond_changes, list) else []
        self._charge_labels = charge_labels if isinstance(charge_labels, list) else []
        self._arrows = arrows if isinstance(arrows, list) else []
        self._bond_styles = bond_styles or {}
        self._label = label if isinstance(label, str) else ""
        self._frame_idx = frame_idx
        self._n_frames = n_frames
        self._recalc_bounds()
        self.update()

    def _recalc_bounds(self):
        """Recalculate scene center and scale from current coords."""
        if not self._coords:
            return
        xs = [c[0] for c in self._coords.values()]
        ys = [c[1] for c in self._coords.values()]
        zs = [c[2] for c in self._coords.values()]
        self._center = (
            (min(xs) + max(xs)) / 2.0,
            (min(ys) + max(ys)) / 2.0,
            (min(zs) + max(zs)) / 2.0,
        )
        extent = max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs),
            1.0,
        )
        self._view_scale = 22.0 / (extent + 1.0)  # fit molecule in view with 3D-layer-like scale

    # --- OpenGL lifecycle ---
    def initializeGL(self):
        if not OPENGL_AVAILABLE:
            return
        try:
            glClearColor(0.06, 0.06, 0.14, 1.0)  # dark bg matching #0f0f23
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glEnable(GL_LIGHT1)
            glDisable(GL_COLOR_MATERIAL)
            glEnable(GL_NORMALIZE)
            # Key light
            glLightfv(GL_LIGHT0, GL_POSITION, [2.0, 3.0, 3.0, 0.0])
            glLightfv(GL_LIGHT0, GL_AMBIENT, [0.25, 0.25, 0.25, 1.0])
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.90, 0.90, 0.90, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
            # Fill light
            glLightfv(GL_LIGHT1, GL_POSITION, [-2.0, -1.0, 1.0, 0.0])
            glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.40, 0.40, 0.45, 1.0])

            self._sq = gluNewQuadric()
            gluQuadricNormals(self._sq, GLU_SMOOTH)
            self._cq = gluNewQuadric()
            gluQuadricNormals(self._cq, GLU_SMOOTH)
            self._gl_initialized = True
        except Exception as e:
            # [FIX-GL-FALLBACK] GL 컨텍스트 초기화 실패 → QPainter 2.5D 폴백
            logger.warning("OpenGL initializeGL 실패 → QPainter 2.5D 폴백: %s", e)
            self._gl_fallback = True

    def resizeGL(self, w, h):
        if not OPENGL_AVAILABLE or getattr(self, '_gl_fallback', False):
            return
        if h == 0:
            h = 1
        try:
            glViewport(0, 0, w, h)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(45.0, w / h, 0.1, 200.0)
            glMatrixMode(GL_MODELVIEW)
        except Exception as e:
            logger.warning("resizeGL 실패 → QPainter 폴백: %s", e)
            self._gl_fallback = True

    def paintGL(self):
        if not OPENGL_AVAILABLE or not self._gl_initialized:
            return
        if getattr(self, '_gl_fallback', False):
            # OpenGL previously failed — delegate to QPainter 2.5D
            self._paint_fallback_2d()
            return
        try:
            self._paintGL_impl()
        except Exception as e:
            # Rule M: no silent failure — log and switch to QPainter 2.5D
            logger.warning("OpenGL paintGL failed, switching to QPainter 2.5D fallback: %s", e)
            self._gl_fallback = True
            self._paint_fallback_2d()

    def _paint_fallback_2d(self):
        """QPainter 2.5D fallback when OpenGL rendering fails at runtime."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor(26, 26, 46))  # #1a1a2e dark bg

        if not self._coords:
            p.setPen(QPen(QColor("#aaa"), 1))
            p.setFont(QFont("Malgun Gothic", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "프레임 데이터 없음")
            p.end()
            return

        w, h = self.width(), self.height()
        cx_s, cy_s = w / 2, h / 2  # screen center
        # Compute 2D projection (simple orthographic with pseudo-depth)
        scale_2d = min(w, h) / 12.0 * self._zoom
        proj_2d: Dict[int, Tuple[float, float, float]] = {}  # idx -> (sx, sy, depth)
        for idx, (x, y, z) in self._coords.items():
            sx = cx_s + (x - self._center[0]) * scale_2d
            sy = cy_s - (y - self._center[1]) * scale_2d  # flip Y
            depth = z - self._center[2]
            proj_2d[idx] = (sx, sy, depth)

        # Draw bonds
        for (bi, bj), bo in self._bonds.items():
            if bi not in proj_2d or bj not in proj_2d or bo < 0.05:
                continue
            sx1, sy1, _ = proj_2d[bi]
            sx2, sy2, _ = proj_2d[bj]
            bkey = (min(bi, bj), max(bi, bj))
            forming = any(
                bc.change_type == "form"
                and bc.frame_start <= self._frame_idx < bc.frame_end
                and (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j)) == bkey
                for bc in self._bond_changes
            )
            breaking = any(
                bc.change_type == "break"
                and bc.frame_start <= self._frame_idx < bc.frame_end
                and (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j)) == bkey
                for bc in self._bond_changes
            )
            if forming:
                color = QColor(0, 255, 120)  # green for forming
            elif breaking:
                color = QColor(255, 61, 61)  # red for breaking
            else:
                color = QColor(180, 180, 200)
            pen_w = 2.5 if bo >= 1.8 else 1.8
            p.setPen(QPen(color, pen_w))
            p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
            if bo >= 1.8:
                # Double bond offset line
                dx, dy = sx2 - sx1, sy2 - sy1
                ln = math.sqrt(dx * dx + dy * dy) or 1.0
                ox, oy = -dy / ln * 3.0, dx / ln * 3.0
                p.setPen(QPen(color, 1.2))
                p.drawLine(QPointF(sx1 + ox, sy1 + oy), QPointF(sx2 + ox, sy2 + oy))

        # Draw atoms
        for idx, (sx, sy, _depth) in proj_2d.items():
            sym = self._symbols.get(idx, "C")
            cpk = CPK_COLORS_GL.get(sym, _DEFAULT_CPK_GL)
            color = QColor(int(cpk[0] * 255), int(cpk[1] * 255), int(cpk[2] * 255))
            rad = max(5.0, _get_cov_radius(sym) * self.ATOM_SCALE * scale_2d * 0.25)
            grad = QRadialGradient(sx - rad * 0.3, sy - rad * 0.3, rad)
            grad.setColorAt(0.0, color.lighter(140))
            grad.setColorAt(1.0, color.darker(130))
            shadow_alpha = int(70 + 70 * depth_norm)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, shadow_alpha))
            p.drawEllipse(
                QPointF(sx + rad * 0.25, sy + rad * 0.38),
                rad * 1.10,
                rad * 0.42,
            )

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(sx, sy), rad, rad)
            # Symbol label for non-C atoms
            if sym != "C":
                p.setPen(QPen(QColor("#fff"), 1))
                p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                p.drawText(QRectF(sx - 10, sy - 8, 20, 16),
                           Qt.AlignmentFlag.AlignCenter, sym)

        # Frame label
        if self._label:
            p.setPen(QPen(QColor("#e0e0e0"), 1))
            p.setFont(QFont("Malgun Gothic", 9))
            p.drawText(QRectF(10, h - 30, w - 20, 25),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._label)
        p.end()

    def _paintGL_impl(self):
        """Actual OpenGL rendering (separated for try-except fallback)."""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self._pan_x, self._pan_y, -50.0)
        s = self._view_scale * self._zoom
        glScalef(s, s, s)
        glRotatef(self._rot_x, 1.0, 0.0, 0.0)
        glRotatef(self._rot_y, 0.0, 1.0, 0.0)
        cx, cy, cz = self._center
        glTranslatef(-cx, -cy, -cz)

        if not self._coords:
            return

        # Build forming/breaking sets for bond color coding
        forming_set = set()
        breaking_set = set()
        for bc in self._bond_changes:
            if not (bc.frame_start <= self._frame_idx < bc.frame_end):
                continue
            key = (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j))
            if bc.change_type == "form":
                forming_set.add(key)
            elif bc.change_type == "break":
                breaking_set.add(key)

        # --- Render bonds --- Rule N: isinstance for _symbols/_bond_styles dicts
        assert isinstance(self._symbols, dict) and isinstance(self._bond_styles, dict)
        for (bi, bj), bo in self._bonds.items():
            if bi not in self._coords or bj not in self._coords:
                continue
            if bo < 0.05:
                continue
            p1 = self._coords[bi]
            p2 = self._coords[bj]
            bkey = (min(bi, bj), max(bi, bj))

            # Determine bond color
            if bkey in forming_set:
                c = (0.0, 1.0, 0.47)  # neon green for forming
            elif bkey in breaking_set:
                c = (1.0, 0.24, 0.24)  # bright red for breaking
            else:
                sym1 = self._symbols.get(bi, "C")
                sym2 = self._symbols.get(bj, "C")
                c1 = _get_cpk_gl(sym1)
                c2 = _get_cpk_gl(sym2)
                c = ((c1[0]+c2[0])/2, (c1[1]+c2[1])/2, (c1[2]+c2[2])/2)
                # Ensure minimum brightness
                c = (max(0.55, c[0]), max(0.55, c[1]), max(0.55, c[2]))

            # Bond style (dashed/dotted/solid)
            bstyle = self._bond_styles.get(bkey, self._bond_styles.get((bj, bi), ""))
            if not bstyle:
                if 0.05 < bo < 0.95:
                    bstyle = "dashed"
                else:
                    bstyle = "solid"

            if bstyle in ("dashed", "dotted"):
                # Dashed bond: segmented cylinders
                self._gl_set_material(*c, 1.0)
                self._gl_dashed_bond(p1, p2, self.BOND_RADIUS * 1.45, 10)
            elif bo >= 2.8:
                # Triple bond
                self._gl_set_material(*c, 1.0)
                self._gl_multi_bond(p1, p2, 3)
            elif bo >= 1.8:
                # Double bond
                self._gl_set_material(*c, 1.0)
                self._gl_multi_bond(p1, p2, 2)
            elif bo >= 1.3:
                # Aromatic
                mid = ((p1[0]+p2[0])*0.5, (p1[1]+p2[1])*0.5, (p1[2]+p2[2])*0.5)
                self._gl_set_material(*c, 1.0)
                self._gl_draw_cylinder(p1, mid, self.BOND_RADIUS, 10)
                self._gl_draw_cylinder(mid, p2, self.BOND_RADIUS, 10)
                # Thin overlay for aromatic
                self._gl_set_material(0.75, 0.75, 0.75, 1.0)
                ox, oy, oz = self._perpendicular_offset(p1, p2, 0.15)
                np1 = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
                np2 = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
                self._gl_draw_cylinder(np1, np2, self.BOND_RADIUS * 0.45, 8)
            else:
                # Single bond — CPK split coloring — Rule N: isinstance
                assert isinstance(self._symbols, dict)
                sym1 = self._symbols.get(bi, "C")
                sym2 = self._symbols.get(bj, "C")
                mid = ((p1[0]+p2[0])*0.5, (p1[1]+p2[1])*0.5, (p1[2]+p2[2])*0.5)
                if bkey in forming_set or bkey in breaking_set:
                    self._gl_set_material(*c, 1.0)
                    self._gl_draw_cylinder(p1, p2, self.BOND_RADIUS * 1.35, 12)
                else:
                    c1 = _get_cpk_gl(sym1)
                    c2 = _get_cpk_gl(sym2)
                    # Ensure min brightness for each half
                    c1 = (max(0.45, c1[0]), max(0.45, c1[1]), max(0.45, c1[2]))
                    c2 = (max(0.45, c2[0]), max(0.45, c2[1]), max(0.45, c2[2]))
                    self._gl_set_material(*c1, 1.0)
                    self._gl_draw_cylinder(p1, mid, self.BOND_RADIUS, 12)
                    self._gl_set_material(*c2, 1.0)
                    self._gl_draw_cylinder(mid, p2, self.BOND_RADIUS, 12)

        # --- Render atoms (spheres) --- Rule N: isinstance
        assert isinstance(self._symbols, dict)
        for idx, (x, y, z) in self._coords.items():
            sym = self._symbols.get(idx, "C")
            r, g, b = _get_cpk_gl(sym)
            self._gl_set_material(r, g, b, 1.0)
            rad = _get_cov_radius(sym) * self.ATOM_SCALE

            glPushMatrix()
            glTranslatef(x, y, z)
            gluSphere(self._sq, rad, 36, 28)
            glPopMatrix()

        # --- QPainter overlay for labels, arrows, charges, TS ---
        self._paint_overlay()

    def _paint_overlay(self):
        """QPainter overlay on top of OpenGL for 2D annotations."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # --- Project atom coords to screen for overlay positioning ---
        proj = {}
        for idx, (x, y, z) in self._coords.items():
            sx, sy = self._project_to_screen(x, y, z)
            proj[idx] = (sx, sy)

        # Active charge labels for current frame
        active_charges = {}
        for cl in self._charge_labels:
            if cl.frame_start <= self._frame_idx < cl.frame_end:
                active_charges[cl.atom_idx] = cl.text

        # --- Draw arrows --- Rule N: isinstance
        assert isinstance(self._symbols, dict)
        for arrow in self._arrows:
            if not (arrow.frame_start <= self._frame_idx < arrow.frame_end):
                continue
            if arrow.from_atom >= 0 and arrow.from_atom in proj:
                ax1, ay1 = proj[arrow.from_atom]
            elif arrow.from_pos is not None:
                ax1, ay1 = self._project_to_screen(*arrow.from_pos)
            else:
                continue
            if arrow.to_atom >= 0 and arrow.to_atom in proj:
                ax2, ay2 = proj[arrow.to_atom]
            elif arrow.to_pos is not None:
                ax2, ay2 = self._project_to_screen(*arrow.to_pos)
            else:
                continue

            arrow_color_map: dict = {
                "yellow": ACCENT_YELLOW, "green": BOND_FORMING, "red": BOND_BREAKING,
            }
            assert isinstance(arrow_color_map, dict)  # Rule N
            acolor = arrow_color_map.get(arrow.color, ACCENT_YELLOW)
            apen = QPen(acolor, 2.5)
            if arrow.style == "dashed":
                apen.setStyle(Qt.PenStyle.DashLine)
            elif arrow.style == "dotted":
                apen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(apen)
            p.drawLine(QPointF(ax1, ay1), QPointF(ax2, ay2))

            # Arrow head
            dx = ax2 - ax1
            dy = ay2 - ay1
            length = math.sqrt(dx * dx + dy * dy)
            if length > 1.0:
                ndx, ndy = dx / length, dy / length
                head_size = 10.0  # M473: mechanism arrowhead minimum is 10 px.
                hx1 = ax2 - head_size * (ndx * 0.866 + ndy * 0.5)
                hy1 = ay2 - head_size * (ndy * 0.866 - ndx * 0.5)
                hx2 = ax2 - head_size * (ndx * 0.866 - ndy * 0.5)
                hy2 = ay2 - head_size * (ndy * 0.866 + ndx * 0.5)
                path = QPainterPath()
                path.moveTo(ax2, ay2)
                path.lineTo(hx1, hy1)
                path.lineTo(hx2, hy2)
                path.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(acolor))
                p.drawPath(path)

        # --- Charge labels --- Rule N: isinstance
        assert isinstance(self._symbols, dict)
        for idx, charge_text in active_charges.items():
            if idx not in proj:
                continue
            sx, sy = proj[idx]
            sym = self._symbols.get(idx, "C")
            rad = 14.0 if sym != "H" else 8.0

            if charge_text in ("+", "\u03b4+", "d+"):
                charge_color = QColor(100, 150, 255)
            elif charge_text in ("-", "\u03b4-", "d-"):
                charge_color = QColor(255, 100, 100)
            else:
                charge_color = ACCENT_YELLOW

            charge_font = QFont("Consolas", 12, QFont.Weight.Bold)
            p.setFont(charge_font)
            cfm = p.fontMetrics()
            cw = cfm.horizontalAdvance(charge_text) + 8
            ch = cfm.height() + 4
            cx_label = sx + rad * 0.5
            cy_label = sy - rad - ch + 2
            # Rounded rect background
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 20, 30, 190))
            p.drawRoundedRect(QRectF(cx_label - 2, cy_label, cw, ch), 4, 4)
            p.setPen(QPen(charge_color))
            p.drawText(QRectF(cx_label - 2, cy_label, cw, ch),
                       Qt.AlignmentFlag.AlignCenter, charge_text)

        # --- Atom symbols overlay (non-H heavy atoms) ---
        for idx, (sx, sy) in proj.items():
            sym = self._symbols.get(idx, "C")
            if sym == "H" or sym == "C":
                continue  # skip H and C for cleaner look
            p.setPen(QPen(QColor(255, 255, 255, 220)))
            p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            p.drawText(QRectF(sx - 8, sy - 6, 16, 12),
                       Qt.AlignmentFlag.AlignCenter, sym)

        # --- Frame label ---
        label_text = ""
        if self._label == "reactant":
            label_text = "Reactants"
        elif self._label == "transition_state":
            label_text = "Transition state (TS)"
        elif self._label == "product":
            label_text = "Products"
        elif self._label == "boat":
            label_text = "Boat form"

        if label_text:
            p.setPen(QPen(ACCENT_YELLOW))
            p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            p.drawText(10, 25, label_text)

        # --- TS double-dagger ---
        if self._label == "transition_state":
            ts_font = QFont("Consolas", 28, QFont.Weight.Bold)
            p.setFont(ts_font)
            ts_text = "\u2021"
            tfm = p.fontMetrics()
            tw = tfm.horizontalAdvance(ts_text) + 12
            th = tfm.height() + 6
            tx = self.width() // 2 - tw // 2
            ty = 6
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 35, 10, 180))
            p.drawRoundedRect(tx, ty, tw, th, 6, 6)
            p.setPen(QPen(QColor(255, 200, 50)))
            p.drawText(QRectF(tx, ty, tw, th),
                       Qt.AlignmentFlag.AlignCenter, ts_text)

        # Frame counter
        p.setPen(QPen(TEXT_COLOR.darker(130)))
        p.setFont(QFont("Consolas", 8))
        p.drawText(self.width() - 80, 20,
                   f"Frame {self._frame_idx + 1}/{self._n_frames}")

        # OpenGL mode indicator
        p.setPen(QPen(QColor(120, 220, 120, 160)))
        p.setFont(QFont("Arial", 8))
        p.drawText(8, self.height() - 8, "3D OpenGL")

        _draw_valid_collision_badge(
            p, self.width(), self.height(), self._learning_badge_lines
        )

        p.end()

    def _project_to_screen(self, x: float, y: float, z: float) -> Tuple[float, float]:
        """Project a 3D world coordinate to 2D screen coordinates.
        Approximation matching the OpenGL modelview/projection used in paintGL."""
        # Apply same rotation and translation as paintGL
        rx = math.radians(self._rot_x)
        ry = math.radians(self._rot_y)
        # Center translation
        cx, cy, cz = self._center
        x -= cx
        y -= cy
        z -= cz
        # Y-axis rotation
        x1 = x * math.cos(ry) + z * math.sin(ry)
        z1 = -x * math.sin(ry) + z * math.cos(ry)
        # X-axis rotation
        y1 = y * math.cos(rx) - z1 * math.sin(rx)
        z2 = y * math.sin(rx) + z1 * math.cos(rx)
        # Scale
        s = self._view_scale * self._zoom
        x1 *= s
        y1 *= s
        z2 *= s
        # Perspective projection (matching gluPerspective 45deg, z=-50)
        view_z = -50.0 + z2 + self._pan_y * 0.0  # simplified
        fov_half = math.radians(22.5)  # half of 45deg FOV
        aspect = self.width() / max(self.height(), 1)
        if abs(view_z) < 0.1:
            view_z = -0.1
        proj_scale = 1.0 / (math.tan(fov_half) * abs(view_z))
        sx = self.width() / 2 + (x1 + self._pan_x) * proj_scale * self.height() / 2
        sy = self.height() / 2 - (y1 + self._pan_y) * proj_scale * self.height() / 2
        return sx, sy

    # --- OpenGL helper methods ---
    def _gl_set_material(self, r: float, g: float, b: float, a: float = 1.0):
        """Set OpenGL material properties (ambient/diffuse/specular)."""
        glColor4f(r, g, b, a)
        glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [r*0.50, g*0.50, b*0.50, a])
        glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [r, g, b, a])
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.85, 0.85, 0.85, a])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 60.0)

    def _gl_draw_cylinder(self, p1, p2, radius, slices=10):
        """Draw a cylinder between two 3D points."""
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        dx, dy, dz = x2-x1, y2-y1, z2-z1
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 1e-6:
            return
        glPushMatrix()
        glTranslatef(x1, y1, z1)
        nx, ny, nz = dx/length, dy/length, dz/length
        if abs(nz) > 0.9999:
            if nz < 0:
                glRotatef(180.0, 1.0, 0.0, 0.0)
        else:
            angle = math.degrees(math.acos(max(-1.0, min(1.0, nz))))
            ax, ay = -ny, nx
            al = math.sqrt(ax*ax + ay*ay)
            if al > 1e-8:
                glRotatef(angle, ax/al, ay/al, 0.0)
        gluCylinder(self._cq, radius, radius, length, slices, 1)
        glPopMatrix()

    def _gl_dashed_bond(self, p1, p2, radius, n_segments=10):
        """Draw a dashed bond as segmented cylinders (TS bonds)."""
        dx = p2[0]-p1[0]
        dy = p2[1]-p1[1]
        dz = p2[2]-p1[2]
        for i in range(n_segments):
            if i % 2 == 0:
                t0 = i / n_segments
                t1 = (i + 1) / n_segments
                sp = (p1[0]+dx*t0, p1[1]+dy*t0, p1[2]+dz*t0)
                ep = (p1[0]+dx*t1, p1[1]+dy*t1, p1[2]+dz*t1)
                self._gl_draw_cylinder(sp, ep, radius, 8)

    def _gl_multi_bond(self, p1, p2, count):
        """Draw double or triple bonds as parallel cylinders."""
        if count == 2:
            ox, oy, oz = self._perpendicular_offset(p1, p2, 0.12)
            np1a = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
            np2a = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
            np1b = (p1[0]-ox, p1[1]-oy, p1[2]-oz)
            np2b = (p2[0]-ox, p2[1]-oy, p2[2]-oz)
            self._gl_draw_cylinder(np1a, np2a, self.BOND_RADIUS * 0.75, 10)
            self._gl_draw_cylinder(np1b, np2b, self.BOND_RADIUS * 0.75, 10)
        elif count >= 3:
            self._gl_draw_cylinder(p1, p2, self.BOND_RADIUS * 0.7, 10)
            ox, oy, oz = self._perpendicular_offset(p1, p2, 0.15)
            np1a = (p1[0]+ox, p1[1]+oy, p1[2]+oz)
            np2a = (p2[0]+ox, p2[1]+oy, p2[2]+oz)
            np1b = (p1[0]-ox, p1[1]-oy, p1[2]-oz)
            np2b = (p2[0]-ox, p2[1]-oy, p2[2]-oz)
            self._gl_draw_cylinder(np1a, np2a, self.BOND_RADIUS * 0.6, 10)
            self._gl_draw_cylinder(np1b, np2b, self.BOND_RADIUS * 0.6, 10)

    def _perpendicular_offset(self, p1, p2, dist):
        """Compute perpendicular offset vector for multi-bond rendering."""
        dx, dy, dz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
        l = math.sqrt(dx*dx + dy*dy + dz*dz)
        if l < 1e-6:
            return (0, 0, 0)
        bx, by, bz = dx/l, dy/l, dz/l
        if abs(bx) < 0.9:
            px, py, pz = 0.0, bz, -by
        else:
            px, py, pz = -bz, 0.0, bx
        pl = math.sqrt(px*px + py*py + pz*pz)
        if pl < 1e-8:
            return (0, 0, 0)
        return (px/pl * dist, py/pl * dist, pz/pl * dist)

    # --- Mouse interaction ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = (event.position().x(), event.position().y())
        elif event.button() == Qt.MouseButton.RightButton:
            self._last_mouse_right = (event.position().x(), event.position().y())

    def mouseMoveEvent(self, event: QMouseEvent):
        x, y = event.position().x(), event.position().y()
        if self._last_mouse and event.buttons() & Qt.MouseButton.LeftButton:
            dx = x - self._last_mouse[0]
            dy = y - self._last_mouse[1]
            self._rot_y += dx * 0.5
            self._rot_x += dy * 0.5
            self._last_mouse = (x, y)
            self.update()
        if self._last_mouse_right and event.buttons() & Qt.MouseButton.RightButton:
            dx = x - self._last_mouse_right[0]
            dy = y - self._last_mouse_right[1]
            self._pan_x += dx * 0.05
            self._pan_y -= dy * 0.05
            self._last_mouse_right = (x, y)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = None
        elif event.button() == Qt.MouseButton.RightButton:
            self._last_mouse_right = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self._zoom *= 1.1 if delta > 0 else (1.0 / 1.1)
        self._zoom = max(0.1, min(10.0, self._zoom))
        self.update()


# ============================================================
# 3D Viewer Widget (QPainter 2.5D — fallback)
# ============================================================

class _Viewer3DWidget(QWidget):
    """프레임별 원자/결합을 QPainter 2.5D로 렌더링 (OpenGL 미지원 폴백).
    Enhanced: charge labels, TS indicator, bond style differentiation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 350)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 데이터
        self._coords: Dict[int, Tuple[float, float, float]] = {}
        self._symbols: Dict[int, str] = {}
        self._bonds: Dict[Tuple[int, int], float] = {}
        self._bond_changes: list = []
        self._charge_labels: list = []     # List[ChargeLabel]
        self._arrows: list = []            # List[ArrowAnnotation]
        self._bond_styles: Dict[Tuple[int, int], str] = {}  # per-frame bond styles
        self._label: str = ""
        self._frame_idx: int = 0
        self._n_frames: int = 1
        self._learning_badge_lines: Optional[Tuple[str, str, str]] = None

        # 카메라
        self._rot_x = 20.0
        self._rot_x = 32.0
        self._rot_y = -46.0
        self._scale = 54.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._last_mouse = None

    def set_learning_badge(self, title: str, detail: str, legend: str) -> None:
        """Set the compact top-right learning badge for this viewer instance."""
        self._learning_badge_lines = (str(title), str(detail), str(legend))
        self.update()

    def set_frame_data(
        self,
        coords: Dict[int, Tuple[float, float, float]],
        symbols: Dict[int, str],
        bonds: Dict[Tuple[int, int], float],
        bond_changes: list,
        label: str,
        frame_idx: int,
        n_frames: int,
        charge_labels: Optional[list] = None,
        arrows: Optional[list] = None,
        bond_styles: Optional[Dict[Tuple[int, int], str]] = None,
    ):
        # N-guard: validate external trajectory data types (QPainter fallback)
        if not isinstance(coords, dict):
            logger.warning("set_frame_data(2D): coords is not dict (got %s), using empty", type(coords).__name__)
            coords = {}
        if not isinstance(symbols, dict):
            logger.warning("set_frame_data(2D): symbols is not dict (got %s), using empty", type(symbols).__name__)
            symbols = {}
        if not isinstance(bonds, dict):
            logger.warning("set_frame_data(2D): bonds is not dict (got %s), using empty", type(bonds).__name__)
            bonds = {}
        if bond_styles is not None and not isinstance(bond_styles, dict):
            logger.warning("set_frame_data(2D): bond_styles is not dict (got %s), using empty", type(bond_styles).__name__)
            bond_styles = {}
        self._coords = coords
        self._symbols = symbols
        self._bonds = bonds
        self._bond_changes = bond_changes if isinstance(bond_changes, list) else []
        self._charge_labels = charge_labels if isinstance(charge_labels, list) else []
        self._arrows = arrows if isinstance(arrows, list) else []
        self._bond_styles = bond_styles or {}
        self._label = label if isinstance(label, str) else ""
        self._frame_idx = frame_idx
        self._n_frames = n_frames
        self.update()

    # --- projection ---
    def _project(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """3D -> 2D + depth. 간단한 회전 + 직교투영."""
        rx = math.radians(self._rot_x)
        ry = math.radians(self._rot_y)
        # Y축 회전
        x1 = x * math.cos(ry) + z * math.sin(ry)
        z1 = -x * math.sin(ry) + z * math.cos(ry)
        # X축 회전
        y1 = y * math.cos(rx) - z1 * math.sin(rx)
        z2 = y * math.sin(rx) + z1 * math.cos(rx)

        cx = self.width() / 2 + self._pan_x
        cy = self.height() / 2 + self._pan_y
        camera_dist = 18.0
        persp = camera_dist / max(6.0, camera_dist - z2)
        sx = cx + x1 * self._scale * persp
        sy = cy - y1 * self._scale * persp
        return sx, sy, z2

    # --- paint ---
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bg = QRadialGradient(
            QPointF(self.width() * 0.42, self.height() * 0.38),
            max(self.width(), self.height()) * 0.74,
        )
        bg.setColorAt(0.0, QColor("#1c2441"))
        bg.setColorAt(0.55, BG_VIEWER)
        bg.setColorAt(1.0, QColor("#070713"))
        p.fillRect(self.rect(), QBrush(bg))

        if not self._coords:
            p.setPen(QPen(TEXT_COLOR))
            p.setFont(QFont("Malgun Gothic", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "\ud504\ub808\uc784 \ub370\uc774\ud130 \uc5c6\uc74c")
            p.end()
            return

        # 결합 변화 세트 (빠른 조회용)
        forming_set = set()
        breaking_set = set()
        for bc in self._bond_changes:
            if not (bc.frame_start <= self._frame_idx < bc.frame_end):
                continue
            key = (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j))
            if bc.change_type == "form":
                forming_set.add(key)
            elif bc.change_type == "break":
                breaking_set.add(key)

        # 현재 프레임에서 활성화된 전하 라벨 수집
        active_charges = {}  # atom_idx -> text
        for cl in self._charge_labels:
            if cl.frame_start <= self._frame_idx < cl.frame_end:
                active_charges[cl.atom_idx] = cl.text

        # 투영
        projected = {}
        for idx, (x, y, z) in self._coords.items():
            sx, sy, depth = self._project(x, y, z)
            projected[idx] = (sx, sy, depth)

        # 깊이 범위 계산 (정규화용)
        all_depths = [d for _, _, d in projected.values()]
        depth_min = min(all_depths) if all_depths else 0.0
        depth_max = max(all_depths) if all_depths else 1.0
        depth_range = depth_max - depth_min if (depth_max - depth_min) > 0.001 else 1.0

        # Rule N: isinstance for _symbols/_bond_styles dicts (QPainter fallback)
        assert isinstance(self._symbols, dict) and isinstance(self._bond_styles, dict)
        # 깊이 정렬 (뒤에서 앞으로 — painter's algorithm)
        sorted_atoms = sorted(projected.items(), key=lambda item: item[1][2])

        # --- 화살표 그리기 (결합 뒤, 원자 뒤) ---
        for arrow in self._arrows:
            if not (arrow.frame_start <= self._frame_idx < arrow.frame_end):
                continue
            # 시작/끝 좌표 결정
            if arrow.from_atom >= 0 and arrow.from_atom in projected:
                ax1, ay1, _ = projected[arrow.from_atom]
            elif arrow.from_pos is not None:
                ax1, ay1, _ = self._project(*arrow.from_pos)
            else:
                continue
            if arrow.to_atom >= 0 and arrow.to_atom in projected:
                ax2, ay2, _ = projected[arrow.to_atom]
            elif arrow.to_pos is not None:
                ax2, ay2, _ = self._project(*arrow.to_pos)
            else:
                continue

            arrow_color_map = {
                "yellow": ACCENT_YELLOW, "green": BOND_FORMING, "red": BOND_BREAKING,
            }
            # Rule N: isinstance guard for arrow_color_map
            if not isinstance(arrow_color_map, dict): arrow_color_map = {}
            acolor = arrow_color_map.get(arrow.color, ACCENT_YELLOW)
            apen = QPen(acolor, 2.0)
            if arrow.style == "dashed":
                apen.setStyle(Qt.PenStyle.DashLine)
            elif arrow.style == "dotted":
                apen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(apen)
            p.drawLine(QPointF(ax1, ay1), QPointF(ax2, ay2))

            # 화살표 머리
            dx = ax2 - ax1
            dy = ay2 - ay1
            length = math.sqrt(dx * dx + dy * dy)
            if length > 1.0:
                ndx, ndy = dx / length, dy / length
                head_size = 10.0  # M473: mechanism arrowhead minimum is 10 px.
                # 화살표 머리 두 꼭짓점
                hx1 = ax2 - head_size * (ndx * 0.866 + ndy * 0.5)
                hy1 = ay2 - head_size * (ndy * 0.866 - ndx * 0.5)
                hx2 = ax2 - head_size * (ndx * 0.866 - ndy * 0.5)
                hy2 = ay2 - head_size * (ndy * 0.866 + ndx * 0.5)
                path = QPainterPath()
                path.moveTo(ax2, ay2)
                path.lineTo(hx1, hy1)
                path.lineTo(hx2, hy2)
                path.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(acolor))
                p.drawPath(path)

        # --- 결합 깊이 정렬 후 그리기 (bonds FIRST, back-to-front) ---
        # Sort bonds by average z-depth of endpoints (painter's algorithm)
        sorted_bonds = []
        for (bi, bj), bo in self._bonds.items():
            if bi not in projected or bj not in projected:
                continue
            if bo < 0.05:
                continue
            _, _, d1 = projected[bi]
            _, _, d2 = projected[bj]
            avg_depth = (d1 + d2) / 2.0  # average depth for sorting
            sorted_bonds.append(((bi, bj), bo, avg_depth))
        sorted_bonds.sort(key=lambda x: x[2])  # back-to-front

        for (bi, bj), bo, bond_depth in sorted_bonds:
            sx1, sy1, _ = projected[bi]
            sx2, sy2, _ = projected[bj]

            # 깊이 정규화 (0=far, 1=near) for bond width scaling
            bond_depth_norm = (bond_depth - depth_min) / depth_range
            bond_depth_norm = max(0.0, min(1.0, bond_depth_norm))

            bkey = (min(bi, bj), max(bi, bj))
            if bkey in forming_set:
                color = BOND_FORMING
            elif bkey in breaking_set:
                color = BOND_BREAKING
            else:
                # Gradient: blend from atom1 color to atom2 color
                assert isinstance(self._symbols, dict) and isinstance(CPK_COLORS, dict)  # Rule N
                sym1 = self._symbols.get(bi, "C")
                sym2 = self._symbols.get(bj, "C")
                c1 = CPK_COLORS.get(sym1, _DEFAULT_CPK)
                c2 = CPK_COLORS.get(sym2, _DEFAULT_CPK)
                # Midpoint color blend for the bond
                color = QColor(
                    (c1[0] + c2[0]) // 2,
                    (c1[1] + c2[1]) // 2,
                    (c1[2] + c2[2]) // 2,
                )
                # Lighten slightly for dark bg visibility (min 140 per channel)
                color = QColor(
                    max(140, color.red()),
                    max(140, color.green()),
                    max(140, color.blue()),
                )

            # 결합 스타일 결정: bond_styles dict 우선, 없으면 bond_order로 판단
            bstyle = self._bond_styles.get(bkey, self._bond_styles.get((bj, bi), ""))
            if not bstyle:
                # 폴백: 부분 결합(전이 상태)은 dashed
                if 0.05 < bo < 0.95:
                    bstyle = "dashed"
                else:
                    bstyle = "solid"

            # Bond direction for perpendicular offset
            bdx = sx2 - sx1
            bdy = sy2 - sy1
            blength = math.sqrt(bdx * bdx + bdy * bdy)
            if blength < 1.0:
                continue
            # Perpendicular unit vector
            bnx = -bdy / blength
            bny = bdx / blength

            # Depth-based bond width: near=6px, far=3px
            base_width = 3.0 + 3.0 * bond_depth_norm  # 3px far .. 6px near

            is_transition = (bstyle == "dashed" or bstyle == "dotted")

            if is_transition:
                # --- Glow layer: wide semi-transparent underlay ---
                glow_color = QColor(color.red(), color.green(), color.blue(), 80)
                glow_pen = QPen(glow_color, 12.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap)
                p.setPen(glow_pen)
                p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
                # --- Main transition state bond: 6px dashed with wide pattern ---
                pen = QPen(color, base_width, Qt.PenStyle.CustomDashLine,
                           Qt.PenCapStyle.RoundCap)
                pen.setDashPattern([12, 6])  # long dashes, clearly visible
                p.setPen(pen)
                p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
            elif bo >= 2.8:
                # 삼중 결합: three parallel thick lines
                offset = 4.0
                for off, w in [(0.0, base_width), (-offset, base_width * 0.7), (offset, base_width * 0.7)]:
                    pen = QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                    p.setPen(pen)
                    p.drawLine(
                        QPointF(sx1 + bnx * off, sy1 + bny * off),
                        QPointF(sx2 + bnx * off, sy2 + bny * off),
                    )
            elif bo >= 1.8:
                # 이중 결합: two parallel thick lines offset 3px
                offset = 3.0
                pen = QPen(color, base_width * 0.8, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(
                    QPointF(sx1 + bnx * offset, sy1 + bny * offset),
                    QPointF(sx2 + bnx * offset, sy2 + bny * offset),
                )
                p.drawLine(
                    QPointF(sx1 - bnx * offset, sy1 - bny * offset),
                    QPointF(sx2 - bnx * offset, sy2 - bny * offset),
                )
            elif bo >= 1.3:
                # 방향족 (1.5): one thick solid + one thin dashed
                offset = 3.0
                pen_solid = QPen(color, base_width, Qt.PenStyle.SolidLine,
                                 Qt.PenCapStyle.RoundCap)
                p.setPen(pen_solid)
                p.drawLine(
                    QPointF(sx1 - bnx * offset * 0.5, sy1 - bny * offset * 0.5),
                    QPointF(sx2 - bnx * offset * 0.5, sy2 - bny * offset * 0.5),
                )
                pen_dash = QPen(color, base_width * 0.5, Qt.PenStyle.DashLine,
                                Qt.PenCapStyle.RoundCap)
                p.setPen(pen_dash)
                p.drawLine(
                    QPointF(sx1 + bnx * offset * 0.5, sy1 + bny * offset * 0.5),
                    QPointF(sx2 + bnx * offset * 0.5, sy2 + bny * offset * 0.5),
                )
            else:
                # 단일 결합: one thick line with round caps
                pen = QPen(color, base_width, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

        # --- 원자 그리기 (AFTER bonds — spheres on top, back-to-front) ---
        assert isinstance(self._symbols, dict)  # Rule N: isinstance
        for idx, (sx, sy, depth) in sorted_atoms:
            sym = self._symbols.get(idx, "C")
            if sym == "H":
                rad = 6.0
            else:
                rad = 12.0  # large spheres for heavy atoms

            # 깊이 정규화 (0=far/back, 1=near/front)
            depth_norm = (depth - depth_min) / depth_range
            depth_norm = max(0.0, min(1.0, depth_norm))

            # Perspective-based radius: near atoms slightly larger
            # radius_scale = 1.0 + 0.2 * (1.0 - depth_normalized)
            # depth_norm=0 (far) → scale=1.2, depth_norm=1 (near) → scale=1.0
            # Inverted: near=larger, far=smaller
            radius_scale = 0.85 + 0.3 * depth_norm  # 0.85 far .. 1.15 near
            rad *= radius_scale
            if sym != "H":
                rad = max(8.0, rad)  # minimum 8px for heavy atoms

            # [FIX-OPAQUE] Atoms are always fully opaque.
            # Depth is conveyed by size scaling and lighting gradient, not transparency.
            # Previous: atom_alpha=180..255 caused translucent see-through effect.
            atom_alpha = 255

            color = _get_cpk_qcolor(sym)
            color.setAlpha(atom_alpha)

            # 라디얼 그라데이션 (Phong-like: bright specular at top-left)
            grad = QRadialGradient(QPointF(sx - rad * 0.3, sy - rad * 0.3), rad * 1.5)
            # Specular highlight: near-white, much brighter
            grad.setColorAt(0.0, QColor(
                min(255, color.red() + 190),
                min(255, color.green() + 190),
                min(255, color.blue() + 190),
                atom_alpha,
            ))
            # Base color
            grad.setColorAt(0.45, QColor(color.red(), color.green(), color.blue(), atom_alpha))
            # Deep shadow at edge
            grad.setColorAt(1.0, QColor(
                max(0, color.red() - 120),
                max(0, color.green() - 120),
                max(0, color.blue() - 120),
                atom_alpha,
            ))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(sx, sy), rad, rad)

            # 원소 기호 (H 제외, larger font for bigger spheres)
            if sym != "H":
                p.setPen(QPen(QColor(255, 255, 255, 220)))
                font_size = max(7, int(rad * 0.6))
                p.setFont(QFont("Consolas", font_size, QFont.Weight.Bold))
                p.drawText(QRectF(sx - rad * 0.7, sy - rad * 0.5, rad * 1.4, rad),
                          Qt.AlignmentFlag.AlignCenter, sym)

            # --- 전하 라벨 표시 (larger 12pt with rounded rect bg) ---
            if idx in active_charges:
                charge_text = active_charges[idx]
                # 전하 색상: 양전하 = 파랑, 음전하 = 빨강, 부분전하 = 노랑
                if charge_text in ("+", "\u03b4+", "d+"):
                    charge_color = QColor(100, 150, 255)   # 청색
                elif charge_text in ("-", "\u03b4-", "d-"):
                    charge_color = QColor(255, 100, 100)   # 적색
                else:
                    charge_color = ACCENT_YELLOW
                charge_font = QFont("Consolas", 12, QFont.Weight.Bold)
                p.setFont(charge_font)
                cfm = p.fontMetrics()
                cw = cfm.horizontalAdvance(charge_text) + 8
                ch = cfm.height() + 4
                cx_label = sx + rad * 0.5
                cy_label = sy - rad - ch + 2
                # Rounded rect background for readability
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(20, 20, 30, 190))
                p.drawRoundedRect(QRectF(cx_label - 2, cy_label, cw, ch), 4, 4)
                # Text
                p.setPen(QPen(charge_color))
                p.drawText(QRectF(cx_label - 2, cy_label, cw, ch),
                          Qt.AlignmentFlag.AlignCenter, charge_text)

        # --- 라벨 표시 ---
        label_text = ""
        if self._label == "reactant":
            label_text = "Reactants"
        elif self._label == "transition_state":
            label_text = "Transition state (TS)"
        elif self._label == "product":
            label_text = "Products"
        elif self._label == "boat":
            label_text = "Boat form"

        if label_text:
            p.setPen(QPen(ACCENT_YELLOW))
            p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            p.drawText(10, 25, label_text)

        # --- 전이상태 더블대거 표시 (gold, larger) ---
        if self._label == "transition_state":
            ts_font = QFont("Consolas", 28, QFont.Weight.Bold)
            p.setFont(ts_font)
            ts_text = "\u2021"
            tfm = p.fontMetrics()
            tw = tfm.horizontalAdvance(ts_text) + 12
            th = tfm.height() + 6
            tx = self.width() // 2 - tw // 2
            ty = 6
            # Gold background pill
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 35, 10, 180))
            p.drawRoundedRect(tx, ty, tw, th, 6, 6)
            # Gold text
            p.setPen(QPen(QColor(255, 200, 50)))
            p.drawText(QRectF(tx, ty, tw, th),
                      Qt.AlignmentFlag.AlignCenter, ts_text)

        # 프레임 카운터
        p.setPen(QPen(TEXT_COLOR.darker(130)))
        p.setFont(QFont("Consolas", 8))
        p.drawText(self.width() - 80, 20,
                   f"Frame {self._frame_idx + 1}/{self._n_frames}")

        _draw_valid_collision_badge(
            p, self.width(), self.height(), self._learning_badge_lines
        )

        p.end()

    # --- mouse interaction ---
    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse = event.position()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        pos = event.position()
        dx = pos.x() - self._last_mouse.x()
        dy = pos.y() - self._last_mouse.y()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self._rot_y += dx * 0.5
            self._rot_x += dy * 0.5
        elif event.buttons() & Qt.MouseButton.RightButton:
            self._pan_x += dx
            self._pan_y += dy

        self._last_mouse = pos
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._last_mouse = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self._scale *= 1.1 if delta > 0 else 0.9
        self._scale = max(10, min(200, self._scale))
        self.update()


# ============================================================
# Energy Diagram Widget (matplotlib)
# ============================================================

class _EnergyDiagramWidget(QWidget):
    """matplotlib 에너지 다이어그램 (실시간 프레임 마커)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._energies = []
        self._labels = []
        self._current_frame = 0
        self._canvas = None
        self._fig = None
        self._ax = None
        self._marker_line = None

        if MATPLOTLIB_AVAILABLE:
            self._fig = Figure(figsize=(6, 1.8), dpi=90)
            self._fig.patch.set_facecolor("#1a1a2e")
            self._ax = self._fig.add_subplot(111)
            self._canvas = FigureCanvasQTAgg(self._fig)
            self._canvas.setMinimumHeight(120)
            self._canvas.setMaximumHeight(180)
            self._layout.addWidget(self._canvas)
        else:
            lbl = QLabel("matplotlib 미설치 — 에너지 다이어그램 비활성")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(lbl)

    def set_energies(self, energies: list, labels: list):
        self._energies = energies
        self._labels = labels
        self._draw_plot()

    def set_current_frame(self, frame_idx: int):
        self._current_frame = frame_idx
        self._update_marker()

    def _draw_plot(self):
        if not MATPLOTLIB_AVAILABLE or self._ax is None:
            return
        ax = self._ax
        ax.clear()
        ax.set_facecolor("#0f0f23")

        n = len(self._energies)
        if n == 0:
            return

        x = list(range(n))
        ax.plot(x, self._energies, color="#4fc3f7", linewidth=2.0)
        ax.fill_between(x, self._energies, alpha=0.15, color="#4fc3f7")

        # 전이상태 영역 하이라이트
        ts_frames = [i for i, l in enumerate(self._labels) if l == "transition_state"]
        if ts_frames:
            ax.axvspan(min(ts_frames), max(ts_frames), alpha=0.08, color="#e74c3c")

        ax.set_ylabel("에너지 (kcal/mol)", color="#aaa", fontsize=8,
                       fontfamily="Malgun Gothic")
        ax.set_xlabel("반응 좌표", color="#aaa", fontsize=8,
                       fontfamily="Malgun Gothic")
        ax.tick_params(colors="#777", labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#444")
        ax.spines["left"].set_color("#444")

        # 마커
        self._marker_line = ax.axvline(x=0, color="#f1c40f", linewidth=1.5, linestyle="--")

        self._fig.tight_layout(pad=0.5)
        self._canvas.draw()

    def _update_marker(self):
        if not MATPLOTLIB_AVAILABLE or self._marker_line is None:
            return
        self._marker_line.set_xdata([self._current_frame])
        self._canvas.draw_idle()


# ============================================================
# Main Popup Dialog
# ============================================================

class ReactionAnimationPopup(QDialog):
    """3D 반응 메커니즘 애니메이션 팝업."""

    def __init__(
        self,
        reactant_smiles: str,
        product_smiles: str,
        reaction_name: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._reactant_smi = reactant_smiles
        self._product_smi = product_smiles
        self._reaction_name = reaction_name

        self._trajectory: Optional[ReactionTrajectory] = None
        self._engine = ReactionAnimationEngine() if ENGINE_AVAILABLE else None
        self._current_frame = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_frame_tick)
        self._timer_interval = 50  # ms (기본 속도)

        self._setup_ui()
        self._apply_style()
        self._generate_animation()

    def _setup_ui(self):
        self.setWindowTitle(
            f"3D 반응 애니메이션 — {self._reaction_name}" if self._reaction_name
            else "3D 반응 메커니즘 애니메이션"
        )
        self.setWindowTitle(
            f"3D 반응 시뮬레이션 — {self._reaction_name}" if self._reaction_name
            else "3D 반응 메커니즘 시뮬레이션"
        )
        self.resize(900, 700)
        self.setMinimumSize(800, 550)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # 제목 바
        title_bar = QHBoxLayout()
        title_lbl = QLabel(f"반응: {self._reactant_smi}  ->  {self._product_smi}")
        title_lbl.setText(f"반응: {self._reactant_smi}  ->  {self._product_smi}")
        title_lbl.setFont(QFont("Consolas", 9))
        title_lbl.setWordWrap(True)
        title_bar.addWidget(title_lbl, 1)

        self._lbl_status = QLabel("준비 중...")
        self._lbl_status.setText("준비 중...")
        self._lbl_status.setFont(QFont("Malgun Gothic", 9))
        title_bar.addWidget(self._lbl_status)
        root.addLayout(title_bar)

        # [SIMULATION_MODE] disclaimer — Rule audit_theory ASPIRIN-SALICYLATE-OPEN-001
        # F12 animation: keyframe interpolation only, not physical MD simulation
        self._simulation_disclaimer = QLabel(
            "[SIMULATION_MODE] F12 반응 애니메이션은 키프레임 보간 기반이며, "
            "물리적 MD 시뮬레이션이 아닙니다. "
            "(Not a physical simulation — rule-based keyframe interpolation)"
        )
        self._simulation_disclaimer.setFont(QFont("Malgun Gothic", 9))
        self._simulation_disclaimer.setWordWrap(True)
        self._simulation_disclaimer.setStyleSheet(
            "background-color: #FFF9C4; color: #5a4a00; "
            "border: 1px solid #e0c800; border-radius: 4px; padding: 4px 8px;"
        )
        root.addWidget(self._simulation_disclaimer)

        self._collision_hint = QLabel(
            "유효충돌: C=C π면 ↔ Br-Br σ* 정렬 | 녹색=형성 결합, 빨강=절단 결합, 점선=전이상태"
        )
        self._collision_hint.setText(
            "유효충돌: 반응 중심 결합만 전이상태로 이동합니다. "
            "초록=생성 중 결합, 빨강=절단 중 결합, 점선=부분 결합/전이상태."
        )
        self._collision_hint.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        self._collision_hint.setWordWrap(True)
        self._collision_hint.setStyleSheet(
            "background:#102033; color:#d8f1ff; border:1px solid #285887; "
            "border-radius:6px; padding:5px 8px;"
        )
        root.addWidget(self._collision_hint)

        # --- 메인 스플리터: 뷰어 + 에너지 ---
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 3D 뷰어 — OpenGL 우선, QPainter 2.5D 폴백
        self._viewer_splitter = splitter  # [FIX-GL-FALLBACK] 뷰어 교체용 참조 보관
        if OPENGL_AVAILABLE:
            self._viewer = _ReactionGL3DWidget()
            logger.info("Reaction animation: using OpenGL 3D viewer")
        else:
            self._viewer = _Viewer3DWidget()
            logger.info("Reaction animation: using QPainter 2.5D fallback")
        splitter.addWidget(self._viewer)

        # 에너지 다이어그램
        self._energy_diagram = _EnergyDiagramWidget()
        splitter.addWidget(self._energy_diagram)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # --- 컨트롤 바 ---
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        # 재생/일시정지
        self._btn_play = QPushButton("  재생")
        self._btn_play.setText("재생")
        self._btn_play.setFixedWidth(90)
        self._btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._btn_play)

        # 이전 프레임 (step backward)
        self._btn_step_back = QPushButton("  이전")
        self._btn_step_back.setText("이전")
        self._btn_step_back.setFixedWidth(70)
        self._btn_step_back.clicked.connect(self._step_backward)
        ctrl.addWidget(self._btn_step_back)

        # 다음 프레임 (step forward)
        self._btn_step_fwd = QPushButton("  다음")
        self._btn_step_fwd.setText("다음")
        self._btn_step_fwd.setFixedWidth(70)
        self._btn_step_fwd.clicked.connect(self._step_forward)
        ctrl.addWidget(self._btn_step_fwd)

        self._btn_reset = QPushButton("  리셋")
        self._btn_reset.setText("리셋")
        self._btn_reset.setFixedWidth(80)
        self._btn_reset.clicked.connect(self._reset_animation)
        ctrl.addWidget(self._btn_reset)

        # 프레임 슬라이더
        ctrl.addWidget(QLabel("프레임:"))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1)
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        ctrl.addWidget(self._slider, 1)

        self._lbl_frame = QLabel("0 / 0")
        self._lbl_frame.setFixedWidth(60)
        ctrl.addWidget(self._lbl_frame)

        # 속도
        ctrl.addWidget(QLabel("속도:"))
        self._combo_speed = QComboBox()
        self._combo_speed.addItems(["0.25x", "0.5x", "1x", "2x", "4x"])
        self._combo_speed.setCurrentText("1x")
        self._combo_speed.currentTextChanged.connect(self._on_speed_changed)
        self._combo_speed.setFixedWidth(70)
        ctrl.addWidget(self._combo_speed)

        # 반응 유형 선택
        ctrl.addWidget(QLabel("유형:"))
        self._combo_type = QComboBox()
        self._combo_type.addItems(["일반 보간", "SN2", "양성자 전달", "의자형 뒤집기"])
        self._combo_type.clear()
        self._combo_type.addItems(["일반 보간", "SN2", "양성자 전달", "의자형 뒤집기"])
        self._combo_type.setFixedWidth(110)
        self._combo_type.currentTextChanged.connect(self._on_type_changed)
        ctrl.addWidget(self._combo_type)

        root.addLayout(ctrl)

        # --- 하단 컨트롤 바 2: 루프 토글 + ORCA 버튼 ---
        ctrl2 = QHBoxLayout()
        ctrl2.setSpacing(8)

        # 루프 토글
        self._loop_enabled = True
        self._btn_loop = QPushButton("Loop: ON")
        self._btn_loop.setText("반복: ON")
        self._btn_loop.setFixedWidth(90)
        self._btn_loop.setCheckable(True)
        self._btn_loop.setChecked(True)
        self._btn_loop.clicked.connect(self._toggle_loop)
        ctrl2.addWidget(self._btn_loop)

        # 전이상태 캡처 버튼
        self._btn_capture_ts = QPushButton("전이상태 캡처")
        self._btn_capture_ts.setText("전이상태 캡처")
        self._btn_capture_ts.setFixedWidth(140)
        self._btn_capture_ts.clicked.connect(self._capture_transition_state)
        ctrl2.addWidget(self._btn_capture_ts)

        self._btn_webgl = QPushButton("WebGL 3D")
        self._btn_webgl.setToolTip("Open this reaction trajectory in a 3Dmol.js WebGL evidence viewer.")
        self._btn_webgl.setFixedWidth(100)
        self._btn_webgl.clicked.connect(self._open_webgl_evidence)
        ctrl2.addWidget(self._btn_webgl)

        ctrl2.addStretch(1)

        # ORCA 정밀 계산 버튼 (플레이스홀더)
        self._btn_orca = QPushButton("ORCA 정밀 계산")
        self._btn_orca.setText("ORCA 정밀 계산")
        self._btn_orca.setFixedWidth(140)
        self._btn_orca.clicked.connect(self._on_orca_clicked)
        ctrl2.addWidget(self._btn_orca)

        root.addLayout(ctrl2)

    def _apply_style(self):
        self.setStyleSheet(DARK_STYLE)

    # --------------------------------------------------------
    # Animation generation
    # --------------------------------------------------------
    def _generate_animation(self):
        if self._engine is None:
            self._lbl_status.setText("엔진 로드 실패")
            return

        reaction_type = self._combo_type.currentText()
        traj = None

        self._lbl_status.setText("프레임 생성 중...")
        QApplication.processEvents()

        try:
            if reaction_type == "SN2":
                traj = self._engine.generate_sn2_animation(
                    self._reactant_smi, self._product_smi
                )
            elif reaction_type == "양성자 전달":
                traj = self._engine.generate_proton_transfer(
                    self._reactant_smi, self._product_smi
                )
            elif reaction_type == "의자형 뒤집기":
                traj = self._engine.generate_chair_flip(self._reactant_smi)
            else:
                traj = self._engine.generate_frames(
                    self._reactant_smi, self._product_smi
                )
        except Exception as e:
            logger.error(f"애니메이션 생성 실패: {e}", exc_info=True)

        if traj is None:
            self._lbl_status.setText("프레임 생성 실패 - SMILES를 확인하세요")
            return

        self._trajectory = traj
        self._current_frame = 0
        self._slider.setRange(0, traj.n_frames - 1)
        self._slider.setValue(0)
        self._lbl_frame.setText(f"1 / {traj.n_frames}")

        # 에너지 다이어그램
        self._energy_diagram.set_energies(traj.energies, traj.labels)
        self._energy_diagram.set_current_frame(0)

        # 첫 프레임 표시
        self._show_frame(0)
        self._lbl_status.setText(f"준비 완료 ({traj.n_frames} 프레임)")

        # [FIX-GL-FALLBACK] OpenGL 렌더링 검증 — 첫 프레임 후 500ms 대기 후 검증
        if OPENGL_AVAILABLE and isinstance(self._viewer, _ReactionGL3DWidget):
            self._gl_check_timer = QTimer(self)
            self._gl_check_timer.setSingleShot(True)
            self._gl_check_timer.timeout.connect(self._validate_gl_rendering)
            self._gl_check_timer.start(500)

    def _validate_gl_rendering(self):
        """[FIX-GL-FALLBACK] OpenGL 렌더링 검증.
        grabFramebuffer()로 실제 픽셀을 읽어서 분자가 렌더링되었는지 확인.
        빈 화면이면 _Viewer3DWidget(QPainter 2.5D)으로 교체.
        """
        if not isinstance(self._viewer, _ReactionGL3DWidget):
            return
        if not self._viewer._coords:
            return  # 좌표 없으면 검증 불필요
        try:
            fb_image = self._viewer.grabFramebuffer()
            if fb_image.isNull():
                logger.warning("Reaction GL 프레임버퍼 캡처 실패 → QPainter 폴백")
                self._switch_viewer_to_fallback()
                return
            w, h = fb_image.width(), fb_image.height()
            cx, cy = w // 2, h // 2
            non_bg_count = 0
            total_sampled = 0
            for dy in range(-40, 40, 5):
                for dx in range(-40, 40, 5):
                    px, py = cx + dx, cy + dy
                    if 0 <= px < w and 0 <= py < h:
                        pixel = fb_image.pixelColor(px, py)
                        total_sampled += 1
                        # 배경 (0.06*255=15): 15 이상 차이 검출
                        if (abs(pixel.red() - 15) > 15 or
                                abs(pixel.green() - 15) > 15 or
                                abs(pixel.blue() - 36) > 15):
                            non_bg_count += 1
            threshold = max(1, int(total_sampled * 0.05))
            if non_bg_count < threshold:
                logger.warning("Reaction GL 렌더링 검증 실패 → QPainter 폴백 전환")
                self._switch_viewer_to_fallback()
        except Exception as e:
            logger.warning("Reaction GL 렌더링 검증 예외 → QPainter 폴백: %s", e)
            self._switch_viewer_to_fallback()

    def _switch_viewer_to_fallback(self):
        """[FIX-GL-FALLBACK] _ReactionGL3DWidget → _Viewer3DWidget 교체."""
        if not isinstance(self._viewer, _ReactionGL3DWidget):
            return
        try:
            old = self._viewer
            new_viewer = _Viewer3DWidget()
            idx = self._viewer_splitter.indexOf(old)
            if idx >= 0:
                old.hide()
                self._viewer_splitter.insertWidget(idx, new_viewer)
                old.setParent(None)
                old.deleteLater()
            self._viewer = new_viewer
            # 현재 프레임 재표시
            if self._trajectory and self._current_frame < self._trajectory.n_frames:
                self._show_frame(self._current_frame)
            logger.info("Reaction animation: QPainter 2.5D 폴백 뷰어로 전환 완료")
        except Exception as e:
            logger.warning("Reaction 폴백 뷰어 전환 실패: %s", e)

    def _show_frame(self, idx: int):
        if self._trajectory is None:
            return
        t = self._trajectory
        if idx < 0 or idx >= t.n_frames:
            return

        # 프레임별 bond_styles (있으면 사용, 없으면 빈 dict)
        bstyles = t.bond_styles[idx] if t.bond_styles and idx < len(t.bond_styles) else {}

        self._viewer.set_frame_data(
            coords=t.frames[idx],
            symbols=t.atom_symbols,
            bonds=t.bonds_per_frame[idx],
            bond_changes=t.bond_changes,
            label=t.labels[idx],
            frame_idx=idx,
            n_frames=t.n_frames,
            charge_labels=t.charge_labels,
            arrows=t.arrows,
            bond_styles=bstyles,
        )
        self._energy_diagram.set_current_frame(idx)
        self._lbl_frame.setText(f"{idx + 1} / {t.n_frames}")

    # --------------------------------------------------------
    # Playback controls
    # --------------------------------------------------------
    def _toggle_play(self):
        if self._trajectory is None:
            return
        if self._playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        self._playing = True
        self._btn_play.setText("  일시정지")
        self._timer.start(self._timer_interval)

    def _pause(self):
        self._playing = False
        self._btn_play.setText("  재생")
        self._timer.stop()

    def _reset_animation(self):
        self._pause()
        self._current_frame = 0
        self._slider.setValue(0)
        self._show_frame(0)

    def _step_backward(self):
        """한 프레임 뒤로 이동."""
        if self._trajectory is None:
            return
        self._pause()
        new_frame = max(0, self._current_frame - 1)
        self._current_frame = new_frame
        self._slider.blockSignals(True)
        self._slider.setValue(new_frame)
        self._slider.blockSignals(False)
        self._show_frame(new_frame)
        QApplication.processEvents()  # force synchronous repaint for reliable capture

    def _step_forward(self):
        """한 프레임 앞으로 이동."""
        if self._trajectory is None:
            return
        self._pause()
        new_frame = min(self._trajectory.n_frames - 1, self._current_frame + 1)
        self._current_frame = new_frame
        self._slider.blockSignals(True)
        self._slider.setValue(new_frame)
        self._slider.blockSignals(False)
        self._show_frame(new_frame)
        QApplication.processEvents()  # force synchronous repaint for reliable capture

    def _toggle_loop(self):
        """루프 재생 토글."""
        self._loop_enabled = self._btn_loop.isChecked()
        self._btn_loop.setText("반복: ON" if self._loop_enabled else "반복: OFF")

    def _on_orca_clicked(self):
        """ORCA IRC 정밀 계산 — 아직 미구현 플레이스홀더."""
        QMessageBox.information(
            self,
            "ORCA IRC 계산",
            "ORCA IRC (Intrinsic Reaction Coordinate) 정밀 계산은\n"
            "아직 사용할 수 없습니다.\n\n"
            "향후 ORCA 6.1.1 연동 시 활성화됩니다.",
        )

    def _on_frame_tick(self):
        if self._trajectory is None:
            return
        self._current_frame += 1
        if self._current_frame >= self._trajectory.n_frames:
            if self._loop_enabled:
                self._current_frame = 0  # 루프 재생
            else:
                self._current_frame = self._trajectory.n_frames - 1
                self._pause()
                # 애니메이션 완료 시 자동 캡처 (최초 1회)
                key = self._get_reaction_key()
                if key not in _captured_ts_images:
                    try:
                        self._auto_capture_key_frames()
                    except Exception as e:
                        logger.warning("Auto-capture failed: %s", e)
                return
        self._slider.blockSignals(True)
        self._slider.setValue(self._current_frame)
        self._slider.blockSignals(False)
        self._show_frame(self._current_frame)

    def _on_slider_changed(self, value: int):
        self._current_frame = value
        self._show_frame(value)

    def _on_speed_changed(self, text: str):
        speed_map: dict = {
            "0.25x": 200,
            "0.5x": 100,
            "1x": 50,
            "2x": 25,
            "4x": 12,
        }
        assert isinstance(speed_map, dict)  # Rule N: 타입 가드
        self._timer_interval = speed_map.get(text, 50)
        if self._playing:
            self._timer.setInterval(self._timer_interval)

    def _on_type_changed(self, text: str):
        """반응 유형 변경 시 재생성."""
        self._pause()
        self._generate_animation()

    # --------------------------------------------------------
    # TS Capture
    # --------------------------------------------------------
    def _get_reaction_key(self) -> str:
        """캡처 저장용 반응 키 생성."""
        return f"{self._reactant_smi}>>{self._product_smi}"

    def _capture_current_frame(self):
        """현재 뷰어 프레임을 QPixmap으로 캡처."""
        from PyQt6.QtGui import QPixmap
        return self._viewer.grab()

    def _capture_transition_state(self):
        """전이상태 프레임으로 이동 후 캡처 (사용자 버튼 클릭)."""
        if self._trajectory is None:
            self._lbl_status.setText("궤적 데이터 없음 - 캡처 불가")
            return

        self._pause()

        # TS 프레임으로 이동
        ts_idx = ReactionAnimationEngine.get_transition_state_frame_index(
            self._trajectory
        ) if ENGINE_AVAILABLE else self._trajectory.n_frames // 2

        self._current_frame = ts_idx
        self._slider.blockSignals(True)
        self._slider.setValue(ts_idx)
        self._slider.blockSignals(False)
        self._show_frame(ts_idx)

        # 렌더링 완료 대기 후 캡처
        QApplication.processEvents()
        ts_pixmap = self._capture_current_frame()

        # 저장
        key = self._get_reaction_key()
        if key not in _captured_ts_images:
            _captured_ts_images[key] = {}
        _captured_ts_images[key]['ts'] = ts_pixmap

        # 임시 파일로도 저장 (DryLab PDF용)
        import tempfile, os
        tmp_dir = os.path.join(tempfile.gettempdir(), "chemgrid_ts_captures")
        os.makedirs(tmp_dir, exist_ok=True)
        safe_name = key.replace(">>", "_to_").replace("/", "_").replace("\\", "_")
        ts_path = os.path.join(tmp_dir, f"ts_{safe_name}.png")
        ts_pixmap.save(ts_path, "PNG")
        _captured_ts_images[key]['ts_path'] = ts_path

        self._lbl_status.setText(f"캡처 완료 (프레임 {ts_idx + 1})")
        logger.info("TS capture saved: %s -> %s", key, ts_path)

        # 3초 후 상태 메시지 복귀
        QTimer.singleShot(3000, lambda: self._lbl_status.setText(
            f"준비 완료 ({self._trajectory.n_frames} 프레임)"
            if self._trajectory else ""))

    def _open_webgl_evidence(self):
        """Open the current trajectory in a 3Dmol.js WebGL evidence viewer."""
        if self._trajectory is None:
            logger.warning("WebGL evidence skipped: trajectory is None")
            QMessageBox.warning(self, "WebGL 3D", "No reaction trajectory is available yet.")
            return
        try:
            from reaction_3dmol_exporter import write_3dmol_reaction_html
        except Exception as exc:
            logger.warning("WebGL evidence exporter unavailable: %s", exc)
            QMessageBox.warning(self, "WebGL 3D", f"Exporter unavailable: {exc}")
            return
        try:
            safe_name = "".join(
                ch if ch.isalnum() or ch in ("-", "_") else "_"
                for ch in (self._reaction_name or "reaction")
            )
            out_dir = Path(r"C:\chemgrid") / "docs" / "reports" / "reaction_3d_evidence_live"
            out_path = out_dir / f"{safe_name}_3dmol_webgl.html"
            written = write_3dmol_reaction_html(
                self._trajectory,
                out_path,
                title=f"ChemGrid WebGL 3D Reaction - {self._reaction_name or 'reaction'}",
            )
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(written)))
            if not opened:
                logger.warning("QDesktopServices.openUrl returned False for %s", written)
                QMessageBox.information(self, "WebGL 3D", str(written))
        except Exception as exc:
            logger.warning("WebGL evidence export failed: %s", exc)
            QMessageBox.warning(self, "WebGL 3D", f"Export failed: {exc}")

    def _auto_capture_key_frames(self):
        """애니메이션 완료 시 3개 키 프레임(반응물/TS/생성물) 자동 캡처."""
        if self._trajectory is None or not ENGINE_AVAILABLE:
            return

        key_indices = ReactionAnimationEngine.get_key_frame_indices(self._trajectory)
        key = self._get_reaction_key()
        if key not in _captured_ts_images:
            _captured_ts_images[key] = {}

        import tempfile, os
        tmp_dir = os.path.join(tempfile.gettempdir(), "chemgrid_ts_captures")
        os.makedirs(tmp_dir, exist_ok=True)
        safe_name = key.replace(">>", "_to_").replace("/", "_").replace("\\", "_")

        for label, frame_idx in key_indices.items():
            # 프레임 이동 + 렌더링
            self._show_frame(frame_idx)
            QApplication.processEvents()
            pixmap = self._capture_current_frame()
            _captured_ts_images[key][label] = pixmap

            # 파일 저장
            fpath = os.path.join(tmp_dir, f"{label}_{safe_name}.png")
            pixmap.save(fpath, "PNG")
            _captured_ts_images[key][f'{label}_path'] = fpath

        logger.info("Auto-captured 3 key frames for: %s", key)

        # 3프레임 비교 이미지 생성
        try:
            comparison_path = self._generate_comparison_image(key)
            if comparison_path:
                _captured_ts_images[key]['comparison_path'] = comparison_path
                logger.info("Comparison image saved: %s", comparison_path)
        except Exception as e:
            logger.warning("Comparison image generation failed: %s", e)

    def _generate_comparison_image(self, reaction_key: str = "") -> str:
        """3개 키 프레임(반응물/TS/생성물) 횡병렬 비교 이미지 생성.

        Args:
            reaction_key: _captured_ts_images 딕셔너리 키.
                          빈 문자열이면 self._get_reaction_key() 사용.

        Returns:
            저장된 PNG 파일 경로. 실패 시 빈 문자열.
        """
        from PyQt6.QtGui import QPixmap, QImage

        if not reaction_key:
            reaction_key = self._get_reaction_key()

        # N-guard: _captured_ts_images is module-level cache, validate type
        if not isinstance(_captured_ts_images, dict):
            logger.warning("_captured_ts_images is not dict (got %s)", type(_captured_ts_images).__name__)
            return ""
        data = _captured_ts_images.get(reaction_key, {})
        if not isinstance(data, dict):
            logger.warning("Captured TS data for key '%s' is not dict (got %s)", reaction_key, type(data).__name__)
            return ""
        labels_map = {
            'reactant': '반응물 (Reactant)',
            'transition_state': '전이상태 (TS\u2021)',
            'product': '생성물 (Product)',
        }

        # 3개 QPixmap 수집 (딕셔너리에서 또는 인자로)
        pixmaps = []
        for frame_key in ('reactant', 'transition_state', 'product'):
            pm = data.get(frame_key)
            if pm is None or pm.isNull():
                logger.warning("Missing frame '%s' for comparison image", frame_key)
                return ""
            pixmaps.append(pm)

        # 크기 계산
        frame_w = max(pm.width() for pm in pixmaps)
        frame_h = max(pm.height() for pm in pixmaps)

        padding = 20          # 프레임 간 여백 (px)
        arrow_w = 40          # 화살표 영역 폭 (px)
        label_h = 36          # 라벨 영역 높이 (px)
        top_margin = 10       # 상단 여백 (px)
        bottom_margin = 10    # 하단 여백 (px)

        # 전체 캔버스 크기: 3프레임 + 2화살표 + 양쪽 패딩
        total_w = (padding + frame_w) * 3 + arrow_w * 2 + padding
        total_h = top_margin + frame_h + label_h + bottom_margin

        # QImage 생성 (흰색 배경)
        canvas = QImage(total_w, total_h, QImage.Format.Format_ARGB32)
        canvas.fill(QColor(255, 255, 255))

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 폰트 설정
        label_font = QFont("맑은 고딕", 11)
        label_font.setBold(True)
        arrow_font = QFont("맑은 고딕", 18)
        arrow_font.setBold(True)

        x_cursor = padding  # 현재 x 위치

        for i, (pm, frame_key) in enumerate(zip(pixmaps, ('reactant', 'transition_state', 'product'))):
            # 프레임 이미지 그리기 (중앙 정렬)
            img_x = x_cursor + (frame_w - pm.width()) // 2
            img_y = top_margin + (frame_h - pm.height()) // 2
            painter.drawPixmap(img_x, img_y, pm)

            # 프레임 테두리
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.drawRect(x_cursor, top_margin, frame_w, frame_h)

            # 라벨 텍스트
            painter.setFont(label_font)
            painter.setPen(QColor(40, 40, 40))
            label_rect = QRectF(x_cursor, top_margin + frame_h + 2, frame_w, label_h - 2)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             labels_map[frame_key])

            x_cursor += frame_w

            # 화살표 (프레임 사이에만, 마지막 프레임 뒤에는 그리지 않음)
            if i < 2:
                painter.setFont(arrow_font)
                painter.setPen(QColor(60, 60, 60))
                arrow_rect = QRectF(x_cursor, top_margin, arrow_w, frame_h)
                painter.drawText(arrow_rect, Qt.AlignmentFlag.AlignCenter, "\u2192")
                x_cursor += arrow_w

        painter.end()

        # 파일 저장
        import tempfile, os
        tmp_dir = os.path.join(tempfile.gettempdir(), "chemgrid_ts_captures")
        os.makedirs(tmp_dir, exist_ok=True)
        safe_name = reaction_key.replace(">>", "_to_").replace("/", "_").replace("\\", "_")
        out_path = os.path.join(tmp_dir, f"comparison_{safe_name}.png")
        if not canvas.save(out_path, "PNG"):
            logger.warning("Failed to save comparison image to %s", out_path)
            return ""

        return out_path

    # --------------------------------------------------------
    # Override: close cleanup
    # --------------------------------------------------------
    def closeEvent(self, event):
        self._pause()
        # 닫기 전 자동 캡처 (아직 캡처되지 않은 경우)
        key = self._get_reaction_key()
        if key not in _captured_ts_images and self._trajectory is not None:
            try:
                self._auto_capture_key_frames()
            except Exception as e:
                logger.warning("Auto-capture on close failed: %s", e)
        super().closeEvent(event)


# ============================================================
# Standalone test
# ============================================================
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    popup = ReactionAnimationPopup(
        reactant_smiles="CCO",
        product_smiles="CC=O",
        reaction_name="에탄올 산화",
    )
    popup.show()
    sys.exit(app.exec())
