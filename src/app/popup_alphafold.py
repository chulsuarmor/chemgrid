# popup_alphafold.py (v1.1 - AlphaFold Protein Structure Prediction Dashboard)
"""
ChemGrid: AlphaFold Protein Structure Prediction Popup
- Tab 1: Input (FASTA sequence, PDB ID, prediction controls)
- Tab 2: 3D Structure (interactive QPainter-based protein backbone viewer with pLDDT coloring)
- Tab 3: Residue Analysis (pLDDT table with color coding)
- Tab 4: Binding Site (extraction by radius around reference atom)
"""

import math
from typing import Optional, List, Tuple, Dict

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QDoubleSpinBox, QMessageBox, QTabWidget,
        QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
        QProgressBar, QTextEdit, QWidget, QHeaderView, QSizePolicy,
        QSpinBox, QComboBox, QCheckBox, QApplication,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF, QRectF
    from PyQt6.QtGui import (
        QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
        QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent,
    )
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# ============================================================================
# INTERACTIVE 3D PROTEIN VIEWER WIDGET
# ============================================================================

# pLDDT color scale (AlphaFold standard)
_PLDDT_COLORS = {
    "very_high": QColor(0, 83, 214),      # Blue (>90)
    "high":      QColor(101, 203, 243),    # Cyan (70-90)
    "low":       QColor(255, 219, 19),     # Yellow (50-70)
    "very_low":  QColor(255, 125, 69),     # Orange (<50)
}


def _plddt_color(score: float) -> QColor:
    """Return AlphaFold-standard pLDDT color."""
    if score > 90:
        return _PLDDT_COLORS["very_high"]
    elif score > 70:
        return _PLDDT_COLORS["high"]
    elif score > 50:
        return _PLDDT_COLORS["low"]
    else:
        return _PLDDT_COLORS["very_low"]


if PYQT_AVAILABLE:

    class Protein3DViewerWidget(QWidget):
        """Interactive 3D protein backbone viewer with mouse rotation/zoom.

        Renders Calpha backbone as a thick tube colored by pLDDT score.
        Supports mouse-drag rotation and scroll-wheel zoom.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(400, 300)
            self.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Expanding)
            self.setMouseTracking(True)

            # Data: list of (x, y, z, plddt, res_name, seq_num)
            self._atoms: List[Tuple[float, float, float, float, str, int]] = []
            self._center = (0.0, 0.0, 0.0)
            self._scale = 1.0

            # Camera
            self._rot_x = -30.0   # degrees
            self._rot_y = 30.0
            self._zoom = 1.0
            self._pan_x = 0.0
            self._pan_y = 0.0

            # Mouse state
            self._last_mouse_pos = None
            self._mouse_button = None

            # Display options
            self.show_labels = False
            self.show_backbone_tube = True
            self.color_mode = "plddt"  # "plddt" or "chain" or "rainbow"

            self.setStyleSheet("background-color: #1a1a2e;")

        def set_structure(self, structure):
            """Load a ProteinStructure object and extract CA atoms."""
            self._atoms = []
            if structure is None:
                self.update()
                return

            for res in structure.residues:
                ca_list = [a for a in res.atoms if a.name == "CA"]
                if ca_list:
                    a = ca_list[0]
                    self._atoms.append(
                        (a.x, a.y, a.z, res.plddt, res.name, res.seq_num)
                    )

            if self._atoms:
                xs = [a[0] for a in self._atoms]
                ys = [a[1] for a in self._atoms]
                zs = [a[2] for a in self._atoms]
                self._center = (
                    (min(xs) + max(xs)) / 2,
                    (min(ys) + max(ys)) / 2,
                    (min(zs) + max(zs)) / 2,
                )
                span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
                self._scale = min(self.width(), self.height()) * 0.35 / span
                self._zoom = 1.0
                self._pan_x = 0.0
                self._pan_y = 0.0

            self.update()

        # ── projection ──────────────────────────────────────────────
        def _project(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
            """Project 3D coords to 2D screen coords with rotation."""
            # Center
            x -= self._center[0]
            y -= self._center[1]
            z -= self._center[2]

            # Rotate Y
            ry = math.radians(self._rot_y)
            cos_ry, sin_ry = math.cos(ry), math.sin(ry)
            x2 = x * cos_ry + z * sin_ry
            z2 = -x * sin_ry + z * cos_ry

            # Rotate X
            rx = math.radians(self._rot_x)
            cos_rx, sin_rx = math.cos(rx), math.sin(rx)
            y2 = y * cos_rx - z2 * sin_rx
            z3 = y * sin_rx + z2 * cos_rx

            # Scale and center on widget
            cx = self.width() / 2 + self._pan_x
            cy = self.height() / 2 + self._pan_y
            s = self._scale * self._zoom
            sx = cx + x2 * s
            sy = cy - y2 * s  # flip Y for screen coords
            return sx, sy, z3

        # ── paint ────────────────────────────────────────────────────
        def paintEvent(self, event: QPaintEvent):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Background
            painter.fillRect(self.rect(), QColor(26, 26, 46))

            if not self._atoms:
                painter.setPen(QColor(150, 150, 150))
                painter.setFont(QFont("Arial", 12))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                                 "구조를 로드하면 여기에 3D 뷰가 표시됩니다")
                painter.end()
                return

            # Project all atoms
            projected = []
            for (x, y, z, plddt, name, seq) in self._atoms:
                sx, sy, sz = self._project(x, y, z)
                projected.append((sx, sy, sz, plddt, name, seq))

            # Draw backbone tube (thick colored segments)
            if self.show_backbone_tube and len(projected) > 1:
                for i in range(len(projected) - 1):
                    sx1, sy1, sz1, plddt1 = projected[i][:4]
                    sx2, sy2, sz2, plddt2 = projected[i + 1][:4]

                    # Use average pLDDT for segment color
                    avg_plddt = (plddt1 + plddt2) / 2
                    color = _plddt_color(avg_plddt)

                    # Tube width varies with depth
                    avg_z = (sz1 + sz2) / 2
                    base_width = 3.0 * self._zoom
                    depth_factor = max(0.5, 1.0 + avg_z * 0.003)
                    width = base_width * depth_factor

                    pen = QPen(color, max(1, width))
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen)
                    painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

            # Draw CA atom spheres (depth-sorted)
            sorted_atoms = sorted(projected, key=lambda a: a[2])  # back to front
            for sx, sy, sz, plddt, name, seq in sorted_atoms:
                color = _plddt_color(plddt)

                # Sphere size varies with depth
                base_r = 3.5 * self._zoom
                depth_factor = max(0.4, 1.0 + sz * 0.003)
                r = base_r * depth_factor

                # Main sphere
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPointF(sx, sy), r, r)

                # Highlight
                lighter = QColor(255, 255, 255, 60)
                painter.setBrush(QBrush(lighter))
                painter.drawEllipse(QPointF(sx - r * 0.25, sy - r * 0.25),
                                    r * 0.4, r * 0.4)

                # Labels (if enabled and enough zoom)
                if self.show_labels and self._zoom > 1.2:
                    painter.setPen(QColor(220, 220, 220))
                    painter.setFont(QFont("Arial", 7))
                    painter.drawText(int(sx + r + 2), int(sy - 2),
                                     f"{name}{seq}")

            # Draw legend
            self._draw_legend(painter)

            # Draw axes indicator
            self._draw_axes(painter)

            painter.end()

        def _draw_legend(self, painter: QPainter):
            """Draw pLDDT color legend in bottom-left corner."""
            x0, y0 = 10, self.height() - 100
            painter.setPen(QColor(200, 200, 200))
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            painter.drawText(x0, y0, "pLDDT 신뢰도")

            legend_items = [
                (_PLDDT_COLORS["very_high"], "매우 높음 (>90)"),
                (_PLDDT_COLORS["high"], "높음 (70-90)"),
                (_PLDDT_COLORS["low"], "낮음 (50-70)"),
                (_PLDDT_COLORS["very_low"], "매우 낮음 (<50)"),
            ]
            painter.setFont(QFont("Arial", 8))
            for i, (color, label) in enumerate(legend_items):
                y = y0 + 16 + i * 18
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(x0, int(y - 5), 10, 10)
                painter.setPen(QColor(200, 200, 200))
                painter.drawText(x0 + 14, int(y + 3), label)

        def _draw_axes(self, painter: QPainter):
            """Draw small XYZ axes indicator in bottom-right corner."""
            cx = self.width() - 50
            cy = self.height() - 50
            length = 25

            axes = [
                (1, 0, 0, QColor(255, 80, 80), "X"),
                (0, 1, 0, QColor(80, 255, 80), "Y"),
                (0, 0, 1, QColor(80, 80, 255), "Z"),
            ]
            for ax, ay, az, color, label in axes:
                # Apply same rotation as model
                ry = math.radians(self._rot_y)
                x2 = ax * math.cos(ry) + az * math.sin(ry)
                z2 = -ax * math.sin(ry) + az * math.cos(ry)
                rx = math.radians(self._rot_x)
                y2 = ay * math.cos(rx) - z2 * math.sin(rx)

                ex = cx + x2 * length
                ey = cy - y2 * length

                pen = QPen(color, 2)
                painter.setPen(pen)
                painter.drawLine(QPointF(cx, cy), QPointF(ex, ey))
                painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                painter.drawText(int(ex + 2), int(ey - 2), label)

        # ── mouse interaction ────────────────────────────────────────
        def mousePressEvent(self, event: QMouseEvent):
            self._last_mouse_pos = event.position()
            self._mouse_button = event.button()

        def mouseMoveEvent(self, event: QMouseEvent):
            if self._last_mouse_pos is None:
                return
            pos = event.position()
            dx = pos.x() - self._last_mouse_pos.x()
            dy = pos.y() - self._last_mouse_pos.y()

            if self._mouse_button == Qt.MouseButton.LeftButton:
                # Rotate
                self._rot_y += dx * 0.5
                self._rot_x += dy * 0.5
                self.update()
            elif self._mouse_button == Qt.MouseButton.RightButton:
                # Pan
                self._pan_x += dx
                self._pan_y += dy
                self.update()

            self._last_mouse_pos = pos

        def mouseReleaseEvent(self, event: QMouseEvent):
            self._last_mouse_pos = None
            self._mouse_button = None

        def wheelEvent(self, event: QWheelEvent):
            delta = event.angleDelta().y()
            factor = 1.1 if delta > 0 else 0.9
            self._zoom = max(0.1, min(20.0, self._zoom * factor))
            self.update()

try:
    from alphafold_interface import (
        predict_structure,
        fetch_pdb_from_rcsb,
        validate_fasta_sequence,
        filter_by_plddt,
        extract_binding_site,
        parse_pdb_text,
        ProteinStructure,
        PredictionResult,
    )
    ALPHAFOLD_AVAILABLE = True
except ImportError:
    ALPHAFOLD_AVAILABLE = False


# ============================================================================
# WORKER THREAD (non-blocking prediction)
# ============================================================================

if PYQT_AVAILABLE:

    class _PredictionWorker(QThread):
        """Background thread for structure prediction / RCSB fetch."""
        finished = pyqtSignal(object)  # PredictionResult
        progress = pyqtSignal(str)     # status message

        def __init__(self, sequence: str = "", pdb_id: str = "",
                     timeout: int = 600, parent=None):
            super().__init__(parent)
            self.sequence = sequence
            self.pdb_id = pdb_id
            self.timeout = timeout

        def run(self):
            if not ALPHAFOLD_AVAILABLE:
                from alphafold_interface import PredictionResult as PR
                self.finished.emit(PR(success=False,
                                      error="alphafold_interface not available"))
                return

            self.progress.emit("예측 진행 중...")
            result = predict_structure(
                sequence=self.sequence,
                pdb_id=self.pdb_id,
                timeout_seconds=self.timeout,
            )
            self.finished.emit(result)


# ============================================================================
# MAIN DIALOG
# ============================================================================

class AlphaFoldPopup(QDialog):
    """AlphaFold protein structure prediction dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._structure: Optional[object] = None  # ProteinStructure
        self._prediction_result: Optional[object] = None
        self._worker: Optional[object] = None

        self.setWindowTitle("AlphaFold 단백질 구조 예측")
        self.resize(1000, 700)
        self._init_ui()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # Title
        title = QLabel("AlphaFold Protein Structure Prediction")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        main_layout.addWidget(title)

        # Status
        self.status_label = QLabel("준비 완료")
        self.status_label.setStyleSheet("color: #666; padding: 2px;")
        main_layout.addWidget(self.status_label)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_input_tab(), "입력")
        self.tabs.addTab(self._create_structure_tab(), "3D 구조")
        self.tabs.addTab(self._create_residue_tab(), "잔기 분석")
        self.tabs.addTab(self._create_binding_tab(), "결합부위")
        main_layout.addWidget(self.tabs)

        # Disable result tabs until prediction completes
        for i in range(1, 4):
            self.tabs.setTabEnabled(i, False)

        # Dependency status
        self._update_dep_status()

    # ========== TAB 1: INPUT ==========
    def _create_input_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # -- FASTA input group --
        fasta_group = QGroupBox("FASTA 서열 입력")
        fasta_layout = QVBoxLayout(fasta_group)

        self.seq_input = QTextEdit()
        self.seq_input.setPlaceholderText(
            ">sp|P00000|EXAMPLE\n"
            "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
            "GSAQVKGHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKL\n"
            "...\n\n"
            "FASTA 형식 또는 순수 아미노산 서열을 입력하세요."
        )
        self.seq_input.setMinimumHeight(150)
        fasta_layout.addWidget(self.seq_input)

        btn_row = QHBoxLayout()
        self.btn_predict = QPushButton("예측 시작")
        self.btn_predict.setStyleSheet(
            "background-color: #2196F3; color: white; padding: 8px 20px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_predict.clicked.connect(self._on_predict)
        btn_row.addWidget(self.btn_predict)
        btn_row.addStretch()
        fasta_layout.addLayout(btn_row)
        layout.addWidget(fasta_group)

        # -- PDB direct download group --
        pdb_group = QGroupBox("PDB ID 직접 다운로드 (RCSB)")
        pdb_layout = QFormLayout(pdb_group)

        self.pdb_id_input = QLineEdit()
        self.pdb_id_input.setPlaceholderText("예: 5KIR, 1CRN, 6LU7")
        self.pdb_id_input.setMaximumWidth(200)
        pdb_layout.addRow("PDB ID:", self.pdb_id_input)

        self.btn_fetch_pdb = QPushButton("PDB 다운로드")
        self.btn_fetch_pdb.setStyleSheet(
            "background-color: #4CAF50; color: white; padding: 8px 20px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_fetch_pdb.clicked.connect(self._on_fetch_pdb)
        pdb_layout.addRow("", self.btn_fetch_pdb)
        layout.addWidget(pdb_group)

        layout.addStretch()
        return tab

    # ========== TAB 2: 3D STRUCTURE ==========
    def _create_structure_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Control bar
        ctrl_row = QHBoxLayout()

        self.chk_labels = QCheckBox("잔기 라벨 표시")
        self.chk_labels.setStyleSheet("color: #ccc;")
        self.chk_labels.toggled.connect(self._on_toggle_labels)
        ctrl_row.addWidget(self.chk_labels)

        self.btn_reset_view = QPushButton("뷰 초기화")
        self.btn_reset_view.setStyleSheet(
            "QPushButton { background: #37474f; color: #fff; border: 1px solid #546e7a; "
            "border-radius: 3px; padding: 4px 10px; font-size: 9pt; }"
            "QPushButton:hover { background: #455a64; }"
        )
        self.btn_reset_view.clicked.connect(self._on_reset_3d_view)
        ctrl_row.addWidget(self.btn_reset_view)

        ctrl_row.addStretch()

        help_label = QLabel("좌클릭 드래그: 회전 | 우클릭 드래그: 이동 | 휠: 확대/축소")
        help_label.setStyleSheet("color: #888; font-size: 9px;")
        ctrl_row.addWidget(help_label)

        layout.addLayout(ctrl_row)

        # 3D Viewer Widget
        self.protein_viewer = Protein3DViewerWidget()
        self.protein_viewer.setMinimumHeight(400)
        layout.addWidget(self.protein_viewer, 1)

        return tab

    # ========== TAB 3: RESIDUE ANALYSIS ==========
    def _create_residue_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Summary stats
        self.residue_summary = QLabel("잔기 분석 결과가 여기에 표시됩니다.")
        self.residue_summary.setStyleSheet(
            "font-size: 13px; padding: 8px; background: #f5f5f5; border-radius: 4px;"
        )
        self.residue_summary.setWordWrap(True)
        layout.addWidget(self.residue_summary)

        # Table
        self.residue_table = QTableWidget()
        self.residue_table.setColumnCount(5)
        self.residue_table.setHorizontalHeaderLabels([
            "잔기 번호", "잔기 이름", "체인", "pLDDT 점수", "신뢰도 범주"
        ])
        header = self.residue_table.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.residue_table)

        return tab

    # ========== TAB 4: BINDING SITE ==========
    def _create_binding_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        ctrl_group = QGroupBox("결합부위 추출 설정")
        ctrl_layout = QFormLayout(ctrl_group)

        self.bind_radius = QDoubleSpinBox()
        self.bind_radius.setRange(1.0, 30.0)
        self.bind_radius.setValue(5.0)
        self.bind_radius.setSuffix(" \u00c5")  # Angstrom
        self.bind_radius.setSingleStep(0.5)
        ctrl_layout.addRow("반경:", self.bind_radius)

        self.bind_ref_residue = QSpinBox()
        self.bind_ref_residue.setRange(1, 99999)
        self.bind_ref_residue.setValue(1)
        ctrl_layout.addRow("기준 잔기 번호:", self.bind_ref_residue)

        self.bind_chain = QLineEdit("A")
        self.bind_chain.setMaximumWidth(60)
        ctrl_layout.addRow("체인 ID:", self.bind_chain)

        self.btn_extract_site = QPushButton("추출")
        self.btn_extract_site.setStyleSheet(
            "background-color: #FF9800; color: white; padding: 8px 20px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_extract_site.clicked.connect(self._on_extract_binding_site)
        ctrl_layout.addRow("", self.btn_extract_site)
        layout.addWidget(ctrl_group)

        # Results
        self.binding_summary = QLabel("")
        self.binding_summary.setStyleSheet("padding: 4px;")
        layout.addWidget(self.binding_summary)

        self.binding_table = QTableWidget()
        self.binding_table.setColumnCount(4)
        self.binding_table.setHorizontalHeaderLabels([
            "잔기 이름", "잔기 번호", "체인", "거리 (\u00c5)"
        ])
        bheader = self.binding_table.horizontalHeader()
        if bheader:
            bheader.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.binding_table)

        return tab

    # ------------------------------------------------------------------ deps
    def _update_dep_status(self):
        parts = []
        if not ALPHAFOLD_AVAILABLE:
            parts.append("alphafold_interface")
        if not MATPLOTLIB_AVAILABLE:
            parts.append("matplotlib")
        if not NUMPY_AVAILABLE:
            parts.append("numpy")
        if parts:
            self.status_label.setText(f"[경고] 누락된 의존성: {', '.join(parts)}")
            self.status_label.setStyleSheet("color: #e65100; padding: 2px;")

    # ------------------------------------------------------------------ slots
    def _on_predict(self):
        """Start prediction from FASTA sequence input."""
        if not ALPHAFOLD_AVAILABLE:
            QMessageBox.warning(self, "오류", "alphafold_interface 모듈을 불러올 수 없습니다.")
            return

        raw_seq = self.seq_input.toPlainText().strip()
        if not raw_seq:
            QMessageBox.warning(self, "오류", "서열을 입력하세요.")
            return

        is_valid, clean_seq, err = validate_fasta_sequence(raw_seq)
        if not is_valid:
            QMessageBox.warning(self, "서열 오류", f"서열 검증 실패:\n{err}")
            return

        self._start_prediction(sequence=clean_seq)

    def _on_fetch_pdb(self):
        """Download structure from RCSB PDB."""
        if not ALPHAFOLD_AVAILABLE:
            QMessageBox.warning(self, "오류", "alphafold_interface 모듈을 불러올 수 없습니다.")
            return

        pdb_id = self.pdb_id_input.text().strip().upper()
        if not pdb_id:
            QMessageBox.warning(self, "오류", "PDB ID를 입력하세요.")
            return

        self._start_prediction(pdb_id=pdb_id)

    def _start_prediction(self, sequence: str = "", pdb_id: str = ""):
        """Launch background prediction thread."""
        self.btn_predict.setEnabled(False)
        self.btn_fetch_pdb.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("구조 예측/다운로드 중...")
        self.status_label.setStyleSheet("color: #1565C0; padding: 2px;")

        self._worker = _PredictionWorker(
            sequence=sequence, pdb_id=pdb_id, parent=self
        )
        self._worker.finished.connect(self._on_prediction_done)
        self._worker.progress.connect(
            lambda msg: self.status_label.setText(msg)
        )
        self._worker.start()

    def _on_prediction_done(self, result):
        """Handle prediction result from worker thread."""
        self.progress_bar.hide()
        self.btn_predict.setEnabled(True)
        self.btn_fetch_pdb.setEnabled(True)

        if not result.success:
            self.status_label.setText(f"실패: {result.error}")
            self.status_label.setStyleSheet("color: #c62828; padding: 2px;")
            QMessageBox.warning(self, "예측 실패", result.error)
            return

        self._prediction_result = result
        self._structure = result.structure
        elapsed = f"{result.elapsed_seconds:.1f}s" if result.elapsed_seconds else ""
        self.status_label.setText(
            f"완료 ({result.method}) {elapsed} | "
            f"잔기 {len(self._structure.residues)}개 | "
            f"평균 pLDDT: {self._structure.mean_plddt:.1f}"
        )
        self.status_label.setStyleSheet("color: #2e7d32; padding: 2px;")

        # Enable result tabs
        for i in range(1, 4):
            self.tabs.setTabEnabled(i, True)

        # Populate tabs
        self._draw_3d_structure()
        self._populate_residue_table()
        self.tabs.setCurrentIndex(1)  # switch to 3D view

    # ------------------------------------------------------------------ 3D
    def _draw_3d_structure(self):
        """Load structure into the interactive 3D protein viewer."""
        if self._structure is None:
            return
        self.protein_viewer.set_structure(self._structure)

    def _on_toggle_labels(self, checked: bool):
        """Toggle residue label display in 3D viewer."""
        if hasattr(self, 'protein_viewer'):
            self.protein_viewer.show_labels = checked
            self.protein_viewer.update()

    def _on_reset_3d_view(self):
        """Reset 3D viewer to default orientation."""
        if hasattr(self, 'protein_viewer'):
            self.protein_viewer._rot_x = -30.0
            self.protein_viewer._rot_y = 30.0
            self.protein_viewer._zoom = 1.0
            self.protein_viewer._pan_x = 0.0
            self.protein_viewer._pan_y = 0.0
            self.protein_viewer.update()

    # ------------------------------------------------------------------ residue table
    def _populate_residue_table(self):
        """Fill residue analysis table and summary stats."""
        if self._structure is None:
            return

        residues = self._structure.residues
        if not residues:
            self.residue_summary.setText("잔기 데이터가 없습니다.")
            return

        # Summary
        if ALPHAFOLD_AVAILABLE:
            analysis = filter_by_plddt(self._structure)
            cats = analysis.get("categories", {})
            total = analysis["total_residues"]
            high_pct = 0.0
            if total > 0:
                high_pct = (cats.get("very_high", 0) + cats.get("high", 0)) / total * 100

            self.residue_summary.setText(
                f"총 잔기: {total}개  |  "
                f"평균 pLDDT: {analysis['mean_plddt']:.1f}  |  "
                f"고신뢰도 (>70): {high_pct:.1f}%\n"
                f"  매우 높음(>90): {cats.get('very_high', 0)}  "
                f"높음(70-90): {cats.get('high', 0)}  "
                f"낮음(50-70): {cats.get('low', 0)}  "
                f"매우 낮음(<50): {cats.get('very_low', 0)}"
            )
        else:
            self.residue_summary.setText(f"총 잔기: {len(residues)}개")

        # Table rows
        self.residue_table.setRowCount(len(residues))
        for row, res in enumerate(residues):
            # Confidence category
            if res.plddt > 90:
                cat = "매우 높음"
                bg = QColor("#BBDEFB")
            elif res.plddt > 70:
                cat = "높음"
                bg = QColor("#B2EBF2")
            elif res.plddt > 50:
                cat = "낮음"
                bg = QColor("#FFF9C4")
            else:
                cat = "매우 낮음"
                bg = QColor("#FFE0B2")

            items = [
                str(res.seq_num),
                res.name,
                res.chain_id,
                f"{res.plddt:.1f}",
                cat,
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setBackground(bg)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.residue_table.setItem(row, col, item)

    # ------------------------------------------------------------------ binding site
    def _on_extract_binding_site(self):
        """Extract binding site residues around a reference residue center."""
        if not ALPHAFOLD_AVAILABLE or self._structure is None:
            QMessageBox.warning(self, "오류", "먼저 구조를 로드하세요.")
            return

        radius = self.bind_radius.value()
        ref_seq = self.bind_ref_residue.value()
        chain_id = self.bind_chain.text().strip() or "A"

        # Find reference residue CA atom as center
        center = None
        for res in self._structure.residues:
            if res.seq_num == ref_seq and res.chain_id == chain_id:
                ca_atoms = [a for a in res.atoms if a.name == "CA"]
                if ca_atoms:
                    a = ca_atoms[0]
                    center = (a.x, a.y, a.z)
                elif res.atoms:
                    a = res.atoms[0]
                    center = (a.x, a.y, a.z)
                break

        if center is None:
            QMessageBox.warning(
                self, "오류",
                f"잔기 {chain_id}:{ref_seq}을(를) 찾을 수 없습니다."
            )
            return

        result = extract_binding_site(self._structure, center=center, radius=radius)

        n_res = result["n_residues"]
        n_atoms = result["n_atoms"]
        self.binding_summary.setText(
            f"기준: 잔기 {chain_id}:{ref_seq}  |  "
            f"반경: {radius:.1f} \u00c5  |  "
            f"발견된 잔기: {n_res}개, 원자: {n_atoms}개"
        )

        # Build residue-level table from atoms
        res_map = {}  # (chain, seq) -> (name, min_dist)
        cx, cy, cz = center
        for atom in result["atoms"]:
            key = (atom.chain_id, atom.res_seq)
            dist = math.sqrt(
                (atom.x - cx) ** 2 + (atom.y - cy) ** 2 + (atom.z - cz) ** 2
            )
            if key not in res_map or dist < res_map[key][1]:
                res_map[key] = (atom.res_name, dist)

        sorted_res = sorted(res_map.items(), key=lambda x: x[1][1])

        self.binding_table.setRowCount(len(sorted_res))
        for row, ((chain, seq), (name, dist)) in enumerate(sorted_res):
            items = [name, str(seq), chain, f"{dist:.2f}"]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.binding_table.setItem(row, col, item)
