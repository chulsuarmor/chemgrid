#!/usr/bin/env python3
"""
popup_reaction_animation.py -- 3D 반응 메커니즘 애니메이션 팝업
=============================================================
ReactionAnimationEngine이 생성한 ReactionTrajectory를 시각화:
  - 2.5D QPainter 원자/결합 렌더링 (popup_3d 패턴 재사용)
  - matplotlib 에너지 다이어그램 (실시간 마커)
  - 재생/일시정지/리셋/속도 제어
  - 프레임 슬라이더

다크 테마: #1a1a2e 배경, #e0e0e0 텍스트
한국어 라벨
창 크기: ~1000x700
"""

import math
import logging
from typing import Optional, Dict, Tuple

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QFrame, QSplitter,
    QMessageBox, QSizePolicy, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QRadialGradient,
    QPainterPath, QMouseEvent, QWheelEvent,
)

logger = logging.getLogger(__name__)

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
    )
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False
    logger.warning("ReactionAnimationEngine not available")

# ============================================================
# CPK Colors (popup_3d와 동일)
# ============================================================
CPK_COLORS = {
    "H": (255, 255, 255), "C": (144, 144, 144), "N": (48, 80, 248),
    "O": (255, 13, 13), "F": (144, 224, 80), "Cl": (31, 240, 31),
    "Br": (166, 41, 41), "I": (148, 0, 148), "S": (255, 255, 48),
    "P": (255, 128, 0), "Na": (171, 92, 242), "K": (143, 64, 212),
    "Ca": (61, 255, 0), "Mg": (138, 255, 0), "Fe": (224, 102, 51),
}
_DEFAULT_CPK = (191, 0, 191)


def _get_cpk_qcolor(symbol: str) -> QColor:
    r, g, b = CPK_COLORS.get(symbol, _DEFAULT_CPK)
    return QColor(r, g, b)


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
BOND_FORMING = QColor("#2ecc71")
BOND_BREAKING = QColor("#e74c3c")

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
# 3D Viewer Widget (QPainter 2.5D)
# ============================================================

class _Viewer3DWidget(QWidget):
    """프레임별 원자/결합을 QPainter 2.5D로 렌더링."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 350)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 데이터
        self._coords: Dict[int, Tuple[float, float, float]] = {}
        self._symbols: Dict[int, str] = {}
        self._bonds: Dict[Tuple[int, int], float] = {}
        self._bond_changes: list = []
        self._label: str = ""
        self._frame_idx: int = 0
        self._n_frames: int = 1

        # 카메라
        self._rot_x = 20.0
        self._rot_y = -30.0
        self._scale = 45.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._last_mouse = None

    def set_frame_data(
        self,
        coords: Dict[int, Tuple[float, float, float]],
        symbols: Dict[int, str],
        bonds: Dict[Tuple[int, int], float],
        bond_changes: list,
        label: str,
        frame_idx: int,
        n_frames: int,
    ):
        self._coords = coords
        self._symbols = symbols
        self._bonds = bonds
        self._bond_changes = bond_changes
        self._label = label
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
        sx = cx + x1 * self._scale
        sy = cy - y1 * self._scale
        return sx, sy, z2

    # --- paint ---
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 배경
        p.fillRect(self.rect(), BG_VIEWER)

        if not self._coords:
            p.setPen(QPen(TEXT_COLOR))
            p.setFont(QFont("Malgun Gothic", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "프레임 데이터 없음")
            p.end()
            return

        # 결합 변화 세트 (빠른 조회용)
        forming_set = set()
        breaking_set = set()
        for bc in self._bond_changes:
            key = (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j))
            if bc.change_type == "form":
                forming_set.add(key)
            elif bc.change_type == "break":
                breaking_set.add(key)

        # 투영
        projected = {}
        for idx, (x, y, z) in self._coords.items():
            sx, sy, depth = self._project(x, y, z)
            projected[idx] = (sx, sy, depth)

        # 깊이 정렬 (뒤에서 앞으로)
        sorted_atoms = sorted(projected.items(), key=lambda item: item[1][2])

        # --- 결합 그리기 ---
        for (bi, bj), bo in self._bonds.items():
            if bi not in projected or bj not in projected:
                continue
            if bo < 0.05:
                continue
            sx1, sy1, _ = projected[bi]
            sx2, sy2, _ = projected[bj]

            bkey = (min(bi, bj), max(bi, bj))
            if bkey in forming_set:
                color = BOND_FORMING
            elif bkey in breaking_set:
                color = BOND_BREAKING
            else:
                color = BOND_DEFAULT

            # 부분 결합: 점선
            is_partial = (0.05 < bo < 0.95)
            pen_width = max(1.5, min(bo * 3.0, 4.0))

            pen = QPen(color, pen_width)
            if is_partial:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

            # 이중 결합
            if bo >= 1.8:
                dx = sy2 - sy1
                dy = -(sx2 - sx1)
                length = math.sqrt(dx * dx + dy * dy) or 1.0
                offset = 3.0
                nx, ny = dx / length * offset, dy / length * offset
                pen2 = QPen(color, max(1.0, pen_width * 0.6))
                p.setPen(pen2)
                p.drawLine(QPointF(sx1 + nx, sy1 + ny), QPointF(sx2 + nx, sy2 + ny))

            # 삼중 결합
            if bo >= 2.8:
                dx = sy2 - sy1
                dy = -(sx2 - sx1)
                length = math.sqrt(dx * dx + dy * dy) or 1.0
                offset = 3.0
                nx, ny = dx / length * offset, dy / length * offset
                pen3 = QPen(color, max(1.0, pen_width * 0.5))
                p.setPen(pen3)
                p.drawLine(QPointF(sx1 - nx, sy1 - ny), QPointF(sx2 - nx, sy2 - ny))

        # --- 원자 그리기 (깊이순) ---
        for idx, (sx, sy, depth) in sorted_atoms:
            sym = self._symbols.get(idx, "C")
            if sym == "H":
                rad = 5.0
            else:
                rad = 10.0

            # 깊이 기반 크기 조정
            depth_factor = 1.0 + depth * 0.03
            rad *= max(0.5, min(depth_factor, 1.5))

            color = _get_cpk_qcolor(sym)
            # 라디얼 그라데이션
            grad = QRadialGradient(QPointF(sx - rad * 0.3, sy - rad * 0.3), rad * 1.5)
            lighter = QColor(
                min(255, color.red() + 80),
                min(255, color.green() + 80),
                min(255, color.blue() + 80),
            )
            grad.setColorAt(0.0, lighter)
            grad.setColorAt(0.5, color)
            grad.setColorAt(1.0, color.darker(160))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(sx, sy), rad, rad)

            # 원소 기호 (H 제외)
            if sym != "H":
                p.setPen(QPen(QColor(255, 255, 255, 220)))
                p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                p.drawText(QRectF(sx - 8, sy - 6, 16, 12),
                          Qt.AlignmentFlag.AlignCenter, sym)

        # --- 라벨 표시 ---
        label_text = ""
        if self._label == "reactant":
            label_text = "반응물"
        elif self._label == "transition_state":
            label_text = "전이 상태 (TS)"
        elif self._label == "product":
            label_text = "생성물"
        elif self._label == "boat":
            label_text = "보트형"

        if label_text:
            p.setPen(QPen(ACCENT_YELLOW))
            p.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
            p.drawText(10, 25, label_text)

        # 프레임 카운터
        p.setPen(QPen(TEXT_COLOR.darker(130)))
        p.setFont(QFont("Consolas", 8))
        p.drawText(self.width() - 80, 20,
                   f"Frame {self._frame_idx + 1}/{self._n_frames}")

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
        self.resize(1000, 700)
        self.setMinimumSize(800, 550)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # 제목 바
        title_bar = QHBoxLayout()
        title_lbl = QLabel(f"반응: {self._reactant_smi}  ->  {self._product_smi}")
        title_lbl.setFont(QFont("Consolas", 9))
        title_lbl.setWordWrap(True)
        title_bar.addWidget(title_lbl, 1)

        self._lbl_status = QLabel("준비 중...")
        self._lbl_status.setFont(QFont("Malgun Gothic", 9))
        title_bar.addWidget(self._lbl_status)
        root.addLayout(title_bar)

        # --- 메인 스플리터: 뷰어 + 에너지 ---
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 3D 뷰어
        self._viewer = _Viewer3DWidget()
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

        self._btn_play = QPushButton("  재생")
        self._btn_play.setFixedWidth(90)
        self._btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._btn_play)

        self._btn_reset = QPushButton("  리셋")
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
        self._combo_type.setFixedWidth(110)
        self._combo_type.currentTextChanged.connect(self._on_type_changed)
        ctrl.addWidget(self._combo_type)

        root.addLayout(ctrl)

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

    def _show_frame(self, idx: int):
        if self._trajectory is None:
            return
        t = self._trajectory
        if idx < 0 or idx >= t.n_frames:
            return

        self._viewer.set_frame_data(
            coords=t.frames[idx],
            symbols=t.atom_symbols,
            bonds=t.bonds_per_frame[idx],
            bond_changes=t.bond_changes,
            label=t.labels[idx],
            frame_idx=idx,
            n_frames=t.n_frames,
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

    def _on_frame_tick(self):
        if self._trajectory is None:
            return
        self._current_frame += 1
        if self._current_frame >= self._trajectory.n_frames:
            self._current_frame = 0  # 루프 재생
        self._slider.blockSignals(True)
        self._slider.setValue(self._current_frame)
        self._slider.blockSignals(False)
        self._show_frame(self._current_frame)

    def _on_slider_changed(self, value: int):
        self._current_frame = value
        self._show_frame(value)

    def _on_speed_changed(self, text: str):
        speed_map = {
            "0.25x": 200,
            "0.5x": 100,
            "1x": 50,
            "2x": 25,
            "4x": 12,
        }
        self._timer_interval = speed_map.get(text, 50)
        if self._playing:
            self._timer.setInterval(self._timer_interval)

    def _on_type_changed(self, text: str):
        """반응 유형 변경 시 재생성."""
        self._pause()
        self._generate_animation()

    # --------------------------------------------------------
    # Override: close cleanup
    # --------------------------------------------------------
    def closeEvent(self, event):
        self._pause()
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
