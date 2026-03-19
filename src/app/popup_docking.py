# popup_docking.py (v1.1 - Molecular Docking Dashboard)
"""
ChemDraw Pro: Molecular Docking Simulation Dashboard
- Tab 1: Setup (receptor input, ligand preview, docking parameters)
- Tab 2: Results (pose table, binding energy chart)
- Tab 3: Interactions (2D interaction map, interaction table)
- Tab 4: 3D View (protein-ligand complex viewer with binding site visualization)
- Tab 5: AI Interpretation (Gemini-powered docking result explanation)
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QMessageBox,
        QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
        QGroupBox, QFormLayout, QProgressBar, QTextEdit, QSplitter,
        QWidget, QHeaderView, QSizePolicy, QScrollArea
    )
    from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread
    from PyQt6.QtGui import QFont, QColor
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from docking_data import (
    ReceptorData, LigandData, DockingConfig, DockingPose,
    DockingResult, Interaction, get_receptor_metadata, ReceptorMetadata,
    RECEPTOR_DATABASE
)
from docking_interface import (
    PDBParser, PDBDownloader, LigandPreparer, ReceptorPreparer,
    VinaDockingThread, DOCKING_AVAILABLE, VINA_PYTHON_AVAILABLE,
    RDKIT_AVAILABLE, MEEKO_AVAILABLE, OBABEL_AVAILABLE, REQUESTS_AVAILABLE,
    SIMULATION_MODE, VINA_AVAILABLE
)
from docking_interaction_analyzer import InteractionAnalyzer

# Optional: 3D viewer
try:
    from docking_3d_viewer import Docking3DViewerWidget
    DOCKING_3D_AVAILABLE = True
except ImportError:
    DOCKING_3D_AVAILABLE = False

# Optional: Gemini AI for docking interpretation
try:
    import google.generativeai as _genai_lib
    _GENAI_AVAILABLE = True
except ImportError:
    _genai_lib = None
    _GENAI_AVAILABLE = False


class DockingPopup(QDialog):
    """Main docking simulation dashboard"""

    def __init__(self, canvas=None, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.receptor: Optional[ReceptorData] = None
        self.ligand: Optional[LigandData] = None
        self.docking_result: Optional[DockingResult] = None
        self.work_dir = Path(tempfile.mkdtemp(prefix="chemdraw_dock_"))
        self._download_thread: Optional[PDBDownloader] = None
        self._docking_thread: Optional[VinaDockingThread] = None
        self._binding_site_cache: dict = {}  # pose_id -> binding site residues

        self.setWindowTitle("분자 도킹 시뮬레이션")
        self.resize(1100, 800)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Title bar
        title = QLabel("Molecular Docking Simulation")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        main_layout.addWidget(title)

        # Status bar
        self.status_label = QLabel("준비 완료")
        self.status_label.setStyleSheet("color: #666; padding: 2px;")
        main_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_setup_tab(), "설정")
        self.tabs.addTab(self._create_results_tab(), "결과")
        self.tabs.addTab(self._create_interactions_tab(), "상호작용")
        self.tabs.addTab(self._create_3d_tab(), "3D 뷰")
        self.tabs.addTab(self._create_ai_tab(), "AI 해석")
        main_layout.addWidget(self.tabs)

        # Disable result tabs initially
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.tabs.setTabEnabled(3, False)
        self.tabs.setTabEnabled(4, False)

        # Dependency status
        self._update_dep_status()

    # ========== TAB 1: SETUP ==========

    def _create_setup_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # -- Receptor section --
        receptor_group = QGroupBox("수용체 (Receptor)")
        receptor_layout = QVBoxLayout(receptor_group)

        # PDB file load
        file_row = QHBoxLayout()
        self.receptor_path_label = QLabel("PDB 파일을 로드하거나 PDB ID를 입력하세요")
        self.receptor_path_label.setStyleSheet("color: #888;")
        file_row.addWidget(self.receptor_path_label, 1)

        btn_load_pdb = QPushButton("PDB 파일 열기")
        btn_load_pdb.clicked.connect(self._load_pdb_file)
        file_row.addWidget(btn_load_pdb)
        receptor_layout.addLayout(file_row)

        # PDB ID download
        pdb_id_row = QHBoxLayout()
        pdb_id_row.addWidget(QLabel("PDB ID:"))
        self.pdb_id_input = QLineEdit()
        self.pdb_id_input.setPlaceholderText("예: 1AKE, 4HHB")
        self.pdb_id_input.setMaximumWidth(120)
        pdb_id_row.addWidget(self.pdb_id_input)

        btn_download = QPushButton("RCSB에서 다운로드")
        btn_download.clicked.connect(self._download_pdb)
        btn_download.setEnabled(REQUESTS_AVAILABLE)
        pdb_id_row.addWidget(btn_download)
        pdb_id_row.addStretch()
        receptor_layout.addLayout(pdb_id_row)

        # Preset receptor selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("프리셋 수용체:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("— 수용체 선택 —", "")
        seen = set()
        for pdb_id, meta in RECEPTOR_DATABASE.items():
            if meta.name not in seen:
                seen.add(meta.name)
                self.preset_combo.addItem(f"{meta.pdb_id} — {meta.name}", meta.pdb_id)
        self.preset_combo.setMinimumWidth(350)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addStretch()
        receptor_layout.addLayout(preset_row)

        # Receptor info (summary)
        self.receptor_info = QLabel("")
        receptor_layout.addWidget(self.receptor_info)

        # Receptor detail panel (shown when preset selected)
        self.receptor_detail = QLabel("")
        self.receptor_detail.setWordWrap(True)
        self.receptor_detail.setStyleSheet(
            "color: #ccc; background: #1a1a2e; padding: 8px; "
            "border: 1px solid #333; border-radius: 4px; font-size: 11px;"
        )
        self.receptor_detail.hide()
        receptor_layout.addWidget(self.receptor_detail)

        layout.addWidget(receptor_group)

        # -- Ligand section --
        ligand_group = QGroupBox("리간드 (Ligand)")
        ligand_layout = QVBoxLayout(ligand_group)

        lig_row = QHBoxLayout()
        lig_row.addWidget(QLabel("SMILES:"))
        self.smiles_input = QLineEdit()
        self.smiles_input.setPlaceholderText("캔버스에서 자동 추출 또는 직접 입력")
        lig_row.addWidget(self.smiles_input, 1)

        btn_from_canvas = QPushButton("캔버스에서 가져오기")
        btn_from_canvas.clicked.connect(self._get_smiles_from_canvas)
        lig_row.addWidget(btn_from_canvas)

        btn_prepare = QPushButton("3D 변환")
        btn_prepare.clicked.connect(self._prepare_ligand)
        lig_row.addWidget(btn_prepare)
        ligand_layout.addLayout(lig_row)

        self.ligand_info = QLabel("")
        ligand_layout.addWidget(self.ligand_info)

        layout.addWidget(ligand_group)

        # -- Docking parameters --
        params_group = QGroupBox("도킹 파라미터")
        params_layout = QFormLayout(params_group)

        # Center coordinates
        center_row = QHBoxLayout()
        self.center_x = QDoubleSpinBox()
        self.center_y = QDoubleSpinBox()
        self.center_z = QDoubleSpinBox()
        for spin in [self.center_x, self.center_y, self.center_z]:
            spin.setRange(-999.0, 999.0)
            spin.setDecimals(2)
            spin.setSingleStep(1.0)
        center_row.addWidget(QLabel("X:"))
        center_row.addWidget(self.center_x)
        center_row.addWidget(QLabel("Y:"))
        center_row.addWidget(self.center_y)
        center_row.addWidget(QLabel("Z:"))
        center_row.addWidget(self.center_z)

        btn_auto_center = QPushButton("자동 감지")
        btn_auto_center.clicked.connect(self._auto_detect_binding_site)
        center_row.addWidget(btn_auto_center)
        params_layout.addRow("검색 중심 (Å):", center_row)

        # Box size
        size_row = QHBoxLayout()
        self.size_x = QDoubleSpinBox()
        self.size_y = QDoubleSpinBox()
        self.size_z = QDoubleSpinBox()
        for spin in [self.size_x, self.size_y, self.size_z]:
            spin.setRange(1.0, 100.0)
            spin.setDecimals(1)
            spin.setValue(20.0)
        size_row.addWidget(QLabel("X:"))
        size_row.addWidget(self.size_x)
        size_row.addWidget(QLabel("Y:"))
        size_row.addWidget(self.size_y)
        size_row.addWidget(QLabel("Z:"))
        size_row.addWidget(self.size_z)
        params_layout.addRow("검색 박스 크기 (Å):", size_row)

        # Exhaustiveness
        self.exhaustiveness_spin = QSpinBox()
        self.exhaustiveness_spin.setRange(1, 64)
        self.exhaustiveness_spin.setValue(8)
        params_layout.addRow("정밀도 (Exhaustiveness):", self.exhaustiveness_spin)

        # Num modes
        self.num_modes_spin = QSpinBox()
        self.num_modes_spin.setRange(1, 20)
        self.num_modes_spin.setValue(9)
        params_layout.addRow("포즈 수 (Num Modes):", self.num_modes_spin)

        layout.addWidget(params_group)

        # -- Run button --
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_run = QPushButton("도킹 실행")
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-size: 14px; font-weight: bold; padding: 10px 30px; "
            "border-radius: 5px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self.btn_run.clicked.connect(self._run_docking)
        btn_row.addWidget(self.btn_run)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Vina engine status
        if VINA_AVAILABLE:
            vina_status = "✅ AutoDock Vina 연동됨 — 정밀 도킹 결과 제공"
            vina_color = "#4caf50"
        else:
            vina_status = ("📊 경험적 스코어링 모드 (AutoDock Vina 미설치)\n"
                           "정밀 도킹을 위해: VINA_PATH 환경변수에 vina.exe 경로를 설정하세요\n"
                           "다운로드: https://vina.scripps.edu/downloads/")
            vina_color = "#ff9800"
        vina_label = QLabel(vina_status)
        vina_label.setStyleSheet(f"color: {vina_color}; font-size: 11px; padding: 5px; "
                                  "background: rgba(255,255,255,10); border-radius: 3px;")
        vina_label.setWordWrap(True)
        layout.addWidget(vina_label)

        # Dependency info
        self.dep_label = QLabel()
        self.dep_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")
        layout.addWidget(self.dep_label)

        layout.addStretch()
        return widget

    # ========== TAB 2: RESULTS ==========

    def _create_results_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Receptor Info Panel (수용체 정보) ---
        self.receptor_info_group = QGroupBox("수용체 정보 (Receptor Info)")
        self.receptor_info_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #4a9eff; "
            "border-radius: 5px; margin-top: 6px; padding-top: 14px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 5px; color: #4a9eff; }"
        )
        ri_layout = QFormLayout(self.receptor_info_group)
        ri_layout.setSpacing(4)

        self.ri_name_label = QLabel("-")
        self.ri_name_label.setWordWrap(True)
        self.ri_name_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        ri_layout.addRow("수용체:", self.ri_name_label)

        self.ri_pdb_label = QLabel("-")
        ri_layout.addRow("PDB ID:", self.ri_pdb_label)

        self.ri_function_label = QLabel("-")
        self.ri_function_label.setWordWrap(True)
        self.ri_function_label.setStyleSheet("color: #e0e0e0;")
        ri_layout.addRow("생체 기능:", self.ri_function_label)

        self.ri_disease_label = QLabel("-")
        self.ri_disease_label.setWordWrap(True)
        self.ri_disease_label.setStyleSheet("color: #ff9800;")
        ri_layout.addRow("관련 질환:", self.ri_disease_label)

        self.ri_drugs_label = QLabel("-")
        self.ri_drugs_label.setWordWrap(True)
        self.ri_drugs_label.setStyleSheet("color: #4caf50;")
        ri_layout.addRow("기존 약물:", self.ri_drugs_label)

        self.ri_binding_reason_label = QLabel("-")
        self.ri_binding_reason_label.setWordWrap(True)
        self.ri_binding_reason_label.setStyleSheet("color: #ce93d8;")
        ri_layout.addRow("결합 이유:", self.ri_binding_reason_label)

        self.receptor_info_group.hide()  # show after docking
        layout.addWidget(self.receptor_info_group)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Results table
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.addWidget(QLabel("도킹 포즈 결과"))

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels([
            "포즈", "결합 에너지 (kcal/mol)", "RMSD LB (Å)", "RMSD UB (Å)"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.currentCellChanged.connect(
            lambda row, col, prevRow, prevCol: self._on_pose_selected(row)
        )
        table_layout.addWidget(self.results_table)

        splitter.addWidget(table_widget)

        # Energy chart
        if MATPLOTLIB_AVAILABLE:
            chart_widget = QWidget()
            chart_layout = QVBoxLayout(chart_widget)
            chart_layout.addWidget(QLabel("결합 에너지 비교"))

            self.energy_figure = Figure(figsize=(8, 3))
            self.energy_canvas = FigureCanvas(self.energy_figure)
            chart_layout.addWidget(self.energy_canvas)
            splitter.addWidget(chart_widget)

        # Summary
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("padding: 10px; font-size: 12px;")

        layout.addWidget(splitter)
        layout.addWidget(self.summary_label)
        return widget

    # ========== TAB 3: INTERACTIONS ==========

    def _create_interactions_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Interaction table
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)

        self.pose_selector = QComboBox()
        self.pose_selector.currentIndexChanged.connect(self._on_interaction_pose_changed)
        table_layout.addWidget(self.pose_selector)

        self.interaction_table = QTableWidget()
        self.interaction_table.setColumnCount(5)
        self.interaction_table.setHorizontalHeaderLabels([
            "유형", "잔기", "단백질 원자", "거리 (Å)", "체인"
        ])
        self.interaction_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_layout.addWidget(self.interaction_table)

        # Interaction interpretation panel (상호작용 해석)
        self.interaction_interpretation = QTextEdit()
        self.interaction_interpretation.setReadOnly(True)
        self.interaction_interpretation.setMaximumHeight(200)
        self.interaction_interpretation.setStyleSheet(
            "QTextEdit { background-color: #1a1a2e; color: #e0e0e0; "
            "font-family: 'Malgun Gothic', 'D2Coding', sans-serif; font-size: 11px; "
            "border: 1px solid #3a3a5c; border-radius: 4px; padding: 6px; }"
        )
        self.interaction_interpretation.setPlaceholderText("포즈를 선택하면 상호작용 해석이 여기에 표시됩니다.")
        table_layout.addWidget(QLabel("상호작용 해석 (Interaction Interpretation)"))
        table_layout.addWidget(self.interaction_interpretation)

        splitter.addWidget(table_widget)

        # 2D interaction map
        if MATPLOTLIB_AVAILABLE:
            map_widget = QWidget()
            map_layout = QVBoxLayout(map_widget)

            # 다이어그램 모드 선택
            mode_row = QHBoxLayout()
            mode_row.addWidget(QLabel("다이어그램 모드:"))
            self.diagram_mode_combo = QComboBox()
            self.diagram_mode_combo.addItems(["Circle", "Ligand"])
            self.diagram_mode_combo.currentIndexChanged.connect(
                lambda: self._on_interaction_pose_changed(self.pose_selector.currentIndex()))
            mode_row.addWidget(self.diagram_mode_combo)
            mode_row.addStretch()
            map_layout.addLayout(mode_row)

            self.interaction_figure = Figure(figsize=(6, 6))
            self.interaction_canvas = FigureCanvas(self.interaction_figure)
            map_layout.addWidget(self.interaction_canvas)
            splitter.addWidget(map_widget)

        layout.addWidget(splitter)
        return widget

    # ========== TAB 4: 3D VIEW ==========

    def _create_3d_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if DOCKING_3D_AVAILABLE:
            # Pose selector
            control_row = QHBoxLayout()
            control_row.addWidget(QLabel("포즈 선택:"))
            self.viewer_pose_selector = QComboBox()
            self.viewer_pose_selector.currentIndexChanged.connect(self._on_3d_pose_changed)
            control_row.addWidget(self.viewer_pose_selector)
            control_row.addStretch()
            layout.addLayout(control_row)

            self.viewer_3d = Docking3DViewerWidget()
            layout.addWidget(self.viewer_3d, 1)
        else:
            placeholder = QLabel(
                "3D 뷰어를 사용하려면 PyOpenGL이 필요합니다.\n"
                "pip install PyOpenGL PyOpenGL_accelerate"
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #888; font-size: 14px;")
            layout.addWidget(placeholder)

        return widget

    # ========== TAB 5: AI INTERPRETATION ==========

    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("AI 기반 도킹 결과 해석"))

        self.ai_pose_selector = QComboBox()
        header_row.addWidget(QLabel("포즈:"))
        header_row.addWidget(self.ai_pose_selector)

        self.btn_ai_analyze = QPushButton("AI 해석 실행")
        self.btn_ai_analyze.setStyleSheet(
            "QPushButton { background-color: #7C4DFF; color: white; "
            "font-weight: bold; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #651FFF; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self.btn_ai_analyze.clicked.connect(self._on_ai_analyze)
        header_row.addWidget(self.btn_ai_analyze)
        header_row.addStretch()
        layout.addLayout(header_row)

        # API status
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if _GENAI_AVAILABLE and api_key:
            status_text = "Gemini API: 사용 가능"
            status_color = "#4CAF50"
        elif _GENAI_AVAILABLE:
            status_text = "Gemini API: 키 미설정 (GEMINI_API_KEY 환경변수 필요) — Rule-based 모드"
            status_color = "#FF9800"
        else:
            status_text = "google-generativeai 미설치 — Rule-based 모드"
            status_color = "#FF9800"

        api_label = QLabel(status_text)
        api_label.setStyleSheet(f"color: {status_color}; font-size: 11px; padding: 2px;")
        layout.addWidget(api_label)

        # AI interpretation result area
        self.ai_result_text = QTextEdit()
        self.ai_result_text.setReadOnly(True)
        self.ai_result_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "font-family: 'Consolas', 'D2Coding', monospace; font-size: 12px; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 8px; }"
        )
        self.ai_result_text.setPlaceholderText(
            "도킹 결과를 선택하고 'AI 해석 실행'을 클릭하세요.\n\n"
            "AI가 분석하는 내용:\n"
            "  - 수용체의 위치 및 생체 내 기능\n"
            "  - 결합 친화도의 의미 (치료적 함의)\n"
            "  - 핵심 상호작용 잔기 분석\n"
            "  - 약물 최적화 제안"
        )
        layout.addWidget(self.ai_result_text, 1)

        # Progress indicator for AI
        self.ai_progress = QLabel("")
        self.ai_progress.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.ai_progress)

        return widget

    # ========== ACTIONS ==========

    def _load_pdb_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "PDB 파일 선택", "",
            "PDB Files (*.pdb);;All Files (*.*)"
        )
        if not filepath:
            return

        try:
            self.receptor = PDBParser.parse(Path(filepath))
            self.receptor = PDBParser.remove_water(self.receptor)
            self._update_receptor_info()
            self._auto_detect_binding_site()
            self.status_label.setText(f"수용체 로드 완료: {self.receptor.name}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDB 파일 파싱 실패:\n{str(e)}")

    def _download_pdb(self):
        pdb_id = self.pdb_id_input.text().strip()
        if not pdb_id or len(pdb_id) != 4:
            QMessageBox.warning(self, "알림", "유효한 4자리 PDB ID를 입력하세요.")
            return

        self.progress_bar.show()
        self.status_label.setText(f"PDB ID '{pdb_id}' 다운로드 중...")

        self._download_thread = PDBDownloader(pdb_id, self.work_dir, self)
        self._download_thread.progress.connect(self._on_download_progress)
        self._download_thread.result.connect(self._on_download_complete)
        self._download_thread.error.connect(self._on_download_error)
        self._download_thread.start()

    def _on_download_progress(self, msg: str):
        self.status_label.setText(msg)

    def _on_download_complete(self, filepath):
        self.progress_bar.hide()
        try:
            self.receptor = PDBParser.parse(Path(str(filepath)))
            self.receptor = PDBParser.remove_water(self.receptor)
            self.receptor.pdb_id = self.pdb_id_input.text().strip().upper()
            self._update_receptor_info()
            self._auto_detect_binding_site()
            self.status_label.setText(f"수용체 다운로드 완료: {self.receptor.name}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDB 파싱 실패:\n{str(e)}")

    def _on_download_error(self, msg: str):
        self.progress_bar.hide()
        QMessageBox.critical(self, "다운로드 오류", msg)
        self.status_label.setText("다운로드 실패")

    def _update_receptor_info(self):
        if self.receptor:
            info = (
                f"이름: {self.receptor.name} | "
                f"원자 수: {self.receptor.atom_count:,} | "
                f"잔기 수: {self.receptor.residue_count} | "
                f"체인: {', '.join(self.receptor.chains)}"
            )
            if self.receptor.pdb_id:
                info = f"PDB: {self.receptor.pdb_id} | " + info
            self.receptor_info.setText(info)
            self.receptor_info.setStyleSheet("color: #2196F3; font-weight: bold;")
            self.receptor_path_label.setText(
                str(self.receptor.filepath) if self.receptor.filepath else "RCSB에서 다운로드됨"
            )
            # Show receptor info in results tab immediately
            pdb_id = self.receptor.pdb_id or ""
            meta = get_receptor_metadata(pdb_id)
            if meta:
                self.ri_name_label.setText(meta.name)
                self.ri_pdb_label.setText(f"{meta.pdb_id} ({meta.gene})")
                self.ri_function_label.setText(meta.function)
                self.ri_disease_label.setText(meta.disease_relevance)
                self.ri_drugs_label.setText(", ".join(meta.known_drugs))
                self.ri_binding_reason_label.setText(
                    f"핵심 결합 잔기: {', '.join(meta.binding_site_residues)}")
            else:
                self.ri_name_label.setText(self.receptor.name or pdb_id or "(알 수 없음)")
                self.ri_pdb_label.setText(pdb_id or "-")
                self.ri_function_label.setText("AI 분석 중...")
                self.ri_disease_label.setText("-")
                self.ri_drugs_label.setText("-")
                self.ri_binding_reason_label.setText("-")
                # Attempt AI-based receptor analysis for unknown PDB IDs
                if pdb_id:
                    self._ai_analyze_receptor(pdb_id)
            self.receptor_info_group.show()

    def _on_preset_selected(self, index: int):
        """Handle preset receptor selection — show info and auto-download."""
        pdb_id = self.preset_combo.currentData()
        if not pdb_id:
            self.receptor_detail.hide()
            return

        meta = get_receptor_metadata(pdb_id)
        if not meta:
            self.receptor_detail.hide()
            return

        # Show receptor detail panel immediately
        detail_lines = [
            f"<b style='color:#4a9eff; font-size:13px;'>{meta.name}</b>",
            f"<span style='color:#888;'>PDB: {meta.pdb_id} | Gene: {meta.gene} | "
            f"UniProt: {meta.uniprot_id} | {meta.organism}</span>",
            "",
            f"<b>🧬 생체 기능:</b> {meta.function}",
            f"<b style='color:#ff9800;'>🏥 관련 질환:</b> {meta.disease_relevance}",
            f"<b style='color:#4caf50;'>💊 기존 약물:</b> {', '.join(meta.known_drugs)}",
            f"<b style='color:#ce93d8;'>🔑 결합부 핵심 잔기:</b> {', '.join(meta.binding_site_residues)}",
        ]
        if meta.description:
            detail_lines.insert(2, f"<i style='color:#aaa;'>{meta.description}</i>")
        # 물리화학적 특성 (새 필드)
        if meta.pocket_character:
            detail_lines.append("")
            detail_lines.append(f"<b style='color:#80cbc4;'>🧪 결합부 특성:</b> {meta.pocket_character}")
        if meta.pocket_volume_A3 > 0:
            detail_lines.append(f"<b style='color:#80cbc4;'>📐 포켓 부피:</b> ~{meta.pocket_volume_A3:.0f} ų")
        if meta.key_interactions:
            detail_lines.append(f"<b style='color:#ffab91;'>⚡ 주요 상호작용:</b> {' / '.join(meta.key_interactions)}")
        if meta.selectivity_notes:
            detail_lines.append(f"<b style='color:#b39ddb;'>🎯 선택성:</b> {meta.selectivity_notes}")
        if meta.autodock_tips:
            detail_lines.append("")
            detail_lines.append(f"<b style='color:#a5d6a7;'>🖥️ AutoDock Vina 도킹 설정:</b> {meta.autodock_tips}")
        # 약리학적/해부학적 컨텍스트
        if meta.tissue_location:
            detail_lines.append("")
            detail_lines.append(f"<b style='color:#ef9a9a;'>🏥 체내 분포:</b> {meta.tissue_location}")
        if meta.nervous_system:
            detail_lines.append(f"<b style='color:#ce93d8;'>🧠 신경계 연관:</b> {meta.nervous_system}")
        if meta.bbb_notes:
            detail_lines.append(f"<b style='color:#90caf9;'>🛡️ 혈뇌장벽(BBB):</b> {meta.bbb_notes}")
        if meta.pharmacology:
            detail_lines.append(f"<b style='color:#fff59d;'>💊 약리학:</b> {meta.pharmacology}")
        self.receptor_detail.setText("<br>".join(detail_lines))
        self.receptor_detail.show()

        # Auto-fill PDB ID and trigger download
        self.pdb_id_input.setText(pdb_id)
        self.status_label.setText(f"프리셋 수용체 선택: {meta.name} ({pdb_id})")

        # Auto-download if requests available
        if REQUESTS_AVAILABLE:
            self._download_pdb()

    def _ai_analyze_receptor(self, pdb_id: str):
        """Use Gemini AI to analyze an unknown receptor's properties."""
        import os
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            self.ri_function_label.setText("(AI 분석 불가 — API 키 미설정)")
            return

        prompt = (
            f"PDB ID '{pdb_id}' 단백질에 대해 다음 정보를 한국어로 간결하게 알려줘:\n"
            f"1. 단백질 이름 및 기능 (1줄)\n"
            f"2. 관련 질환 (1줄)\n"
            f"3. 기존 약물 (쉼표로 나열)\n"
            f"4. 결합부위 핵심 잔기 (3자 코드+번호)\n"
            f"5. AutoDock Vina 도킹 시 grid center 좌표 추천\n"
            f"형식: 줄바꿈으로 구분. 모르면 '알 수 없음'."
        )

        from PyQt6.QtCore import QThread, pyqtSignal

        class AIWorker(QThread):
            result_ready = pyqtSignal(str)

            def __init__(self, key, prompt_text, parent=None):
                super().__init__(parent)
                self._key = key
                self._prompt = prompt_text

            def run(self):
                try:
                    import google.genai as genai
                    client = genai.Client(api_key=self._key)
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash", contents=self._prompt
                    )
                    self.result_ready.emit(resp.text.strip())
                except Exception as e:
                    self.result_ready.emit(f"AI 분석 실패: {e}")

        def _on_ai_result(text):
            lines = text.split('\n')
            if len(lines) >= 1:
                self.ri_function_label.setText(lines[0])
            if len(lines) >= 2:
                self.ri_disease_label.setText(lines[1])
            if len(lines) >= 3:
                self.ri_drugs_label.setText(lines[2])
            if len(lines) >= 4:
                self.ri_binding_reason_label.setText(lines[3])
            self.status_label.setText(f"AI 수용체 분석 완료: {pdb_id}")

        self._ai_worker = AIWorker(api_key, prompt)
        self._ai_worker.result_ready.connect(_on_ai_result)
        self._ai_worker.start()

    def _get_smiles_from_canvas(self):
        if self.canvas is None:
            QMessageBox.warning(self, "알림", "캔버스가 연결되어 있지 않습니다.")
            return

        try:
            smiles = self.canvas.get_smiles()
            if smiles and smiles != "C":
                self.smiles_input.setText(smiles)
                self.status_label.setText(f"캔버스에서 SMILES 추출: {smiles}")
            else:
                QMessageBox.warning(self, "알림", "캔버스에 분자가 없습니다.\n분자를 먼저 그려주세요.")
        except Exception as e:
            QMessageBox.warning(self, "알림", f"SMILES 추출 실패:\n{str(e)}")

    def _prepare_ligand(self):
        smiles = self.smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "SMILES를 입력하세요.")
            return

        if not RDKIT_AVAILABLE:
            QMessageBox.warning(self, "알림", "RDKit이 설치되어 있지 않습니다.")
            return

        try:
            self.ligand = LigandPreparer.smiles_to_3d(smiles)
            if self.ligand is None:
                QMessageBox.warning(self, "알림", "SMILES 변환에 실패했습니다.\n유효한 SMILES인지 확인하세요.")
                return

            self.ligand.name = smiles[:30]
            self.ligand_info.setText(
                f"리간드 원자 수: {self.ligand.atom_count} | SMILES: {smiles}"
            )
            self.ligand_info.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.status_label.setText("리간드 3D 구조 생성 완료")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"리간드 준비 실패:\n{str(e)}")

    def _auto_detect_binding_site(self):
        if self.receptor is None:
            return

        center, size = ReceptorPreparer.detect_binding_site(self.receptor)
        self.center_x.setValue(center[0])
        self.center_y.setValue(center[1])
        self.center_z.setValue(center[2])

        size = tuple(size)  # consume generator if needed
        self.size_x.setValue(size[0])
        self.size_y.setValue(size[1])
        self.size_z.setValue(size[2])

    def _run_docking(self):
        # Validate inputs
        if self.receptor is None:
            QMessageBox.warning(self, "알림", "수용체를 먼저 로드하세요.")
            return

        smiles = self.smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "리간드 SMILES를 입력하세요.")
            return

        if not DOCKING_AVAILABLE:
            QMessageBox.warning(
                self, "알림",
                "도킹 엔진이 설치되어 있지 않습니다.\n"
                "pip install vina meeko 또는 AutoDock Vina 실행 파일을 설정하세요."
            )
            return

        # Prepare ligand if not already done
        if self.ligand is None:
            self._prepare_ligand()
            if self.ligand is None:
                return

        try:
            self.status_label.setText("수용체 PDBQT 변환 중...")
            receptor_pdbqt = ReceptorPreparer.prepare_pdbqt(self.receptor, self.work_dir)
            if receptor_pdbqt is None:
                QMessageBox.critical(self, "오류", "수용체 PDBQT 변환 실패")
                return

            self.status_label.setText("리간드 PDBQT 변환 중...")
            ligand_pdbqt = LigandPreparer.prepare_pdbqt(self.ligand, self.work_dir)
            if ligand_pdbqt is None:
                QMessageBox.critical(self, "오류", "리간드 PDBQT 변환 실패")
                return

        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 준비 실패:\n{str(e)}")
            return

        # Build config
        config = DockingConfig(
            center_x=self.center_x.value(),
            center_y=self.center_y.value(),
            center_z=self.center_z.value(),
            size_x=self.size_x.value(),
            size_y=self.size_y.value(),
            size_z=self.size_z.value(),
            exhaustiveness=self.exhaustiveness_spin.value(),
            num_modes=self.num_modes_spin.value(),
        )

        # Start docking thread
        self.btn_run.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("도킹 계산 중...")

        self._docking_thread = VinaDockingThread(
            receptor_pdbqt=receptor_pdbqt,
            ligand_pdbqt=ligand_pdbqt,
            config=config,
            work_dir=self.work_dir,
            receptor=self.receptor,
            ligand=self.ligand,
            parent=self,
        )
        self._docking_thread.progress.connect(self._on_docking_progress)
        self._docking_thread.result.connect(self._on_docking_complete)
        self._docking_thread.error.connect(self._on_docking_error)
        self._docking_thread.start()

    def _on_docking_progress(self, msg: str):
        self.status_label.setText(msg)

    def _on_docking_complete(self, result):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        self.docking_result = result

        if not result.converged:
            QMessageBox.warning(
                self, "도킹 실패",
                f"도킹이 수렴하지 못했습니다.\n{result.error_message}"
            )
            self.status_label.setText("도킹 실패")
            return

        self.status_label.setText(
            f"도킹 완료! {result.num_poses}개 포즈, "
            f"최적 에너지: {result.best_affinity:.1f} kcal/mol, "
            f"계산 시간: {result.computation_time:.1f}초"
        )

        # Run interaction analysis for each pose
        for pose in result.poses:
            interactions = InteractionAnalyzer.analyze_pose(result.receptor, pose, result.ligand)
            result.interactions[pose.pose_id] = interactions

        # Extract binding site residues (~5A of ligand) for each pose
        self._binding_site_cache = {}
        for pose in result.poses:
            self._binding_site_cache[pose.pose_id] = (
                InteractionAnalyzer.extract_binding_site_residues(
                    result.receptor, pose, radius=5.0
                )
            )

        # Populate results
        self._populate_receptor_info_panel()
        self._populate_results_tab()
        self._populate_interactions_tab()
        self._populate_3d_tab()
        self._populate_ai_tab()

        # Enable tabs
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, True)
        self.tabs.setTabEnabled(3, DOCKING_3D_AVAILABLE)
        self.tabs.setTabEnabled(4, True)
        self.tabs.setCurrentIndex(1)

    def _on_docking_error(self, msg: str):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "도킹 오류", msg)
        self.status_label.setText("도킹 오류 발생")

    # ========== POPULATE RESULTS ==========

    def _populate_receptor_info_panel(self):
        """Fill the receptor info panel with biological metadata."""
        if not self.docking_result or not self.docking_result.receptor:
            return

        receptor = self.docking_result.receptor
        pdb_id = receptor.pdb_id or ""
        meta = get_receptor_metadata(pdb_id)

        if meta:
            self.ri_name_label.setText(meta.name)
            self.ri_pdb_label.setText(f"{meta.pdb_id}  (UniProt: {meta.uniprot_id})" if meta.uniprot_id else meta.pdb_id)
            self.ri_function_label.setText(meta.function)
            self.ri_disease_label.setText(meta.disease_relevance)
            self.ri_drugs_label.setText(", ".join(meta.known_drugs) if meta.known_drugs else "-")
        else:
            self.ri_name_label.setText(receptor.name or pdb_id or "(알 수 없음)")
            self.ri_pdb_label.setText(pdb_id or "-")
            self.ri_function_label.setText("(데이터베이스에 없는 수용체 — AI 해석 탭에서 상세 분석 가능)")
            self.ri_disease_label.setText("-")
            self.ri_drugs_label.setText("-")

        # Binding reason will be updated per-pose in _update_binding_reason
        self.ri_binding_reason_label.setText("(포즈 선택 후 업데이트)")
        self.receptor_info_group.show()

    def _update_binding_reason(self, pose, interactions):
        """Update the binding reason label based on detected interactions."""
        if not interactions:
            self.ri_binding_reason_label.setText("(감지된 상호작용 없음)")
            return

        reasons = []
        n_hbond = sum(1 for i in interactions if i.type == "hydrogen_bond")
        n_hydro = sum(1 for i in interactions if i.type == "hydrophobic")
        n_pi = sum(1 for i in interactions if i.type == "pi_stacking")
        n_salt = sum(1 for i in interactions if i.type == "salt_bridge")

        if n_hbond > 0:
            hb_residues = list(set(f"{i.residue_name}{i.residue_id}" for i in interactions if i.type == "hydrogen_bond"))[:3]
            reasons.append(f"수소결합 {n_hbond}개 ({', '.join(hb_residues)}와 극성 상호작용)")
        if n_hydro > 0:
            reasons.append(f"소수성 접촉 {n_hydro}개 (리간드의 탄화수소 부분이 포켓 내 소수성 잔기와 결합)")
        if n_pi > 0:
            pi_residues = list(set(f"{i.residue_name}{i.residue_id}" for i in interactions if i.type == "pi_stacking"))[:2]
            reasons.append(f"Pi-stacking {n_pi}개 ({', '.join(pi_residues)}의 방향족 고리와 적층)")
        if n_salt > 0:
            reasons.append(f"염 다리 {n_salt}개 (이온성 상호작용으로 강한 정전기적 결합)")

        energy = pose.affinity_kcal
        if energy <= -7:
            reasons.append(f"결합 에너지 {energy:.1f} kcal/mol: 약물 수준의 강한 결합")
        elif energy <= -5:
            reasons.append(f"결합 에너지 {energy:.1f} kcal/mol: 중간 결합력")

        self.ri_binding_reason_label.setText(" | ".join(reasons) if reasons else "-")

    def _build_interaction_interpretation(self, pose, interactions) -> str:
        """Build plain-language explanation of each interaction."""
        if not interactions:
            return "감지된 상호작용이 없습니다."

        receptor = self.docking_result.receptor
        pdb_id = receptor.pdb_id or ""
        meta = get_receptor_metadata(pdb_id)

        lines = []

        # Energy context
        energy = pose.affinity_kcal
        if energy <= -10:
            energy_desc = "매우 강한 결합 (우수한 약물 후보 수준)"
        elif energy <= -8:
            energy_desc = "강한 결합 (약물 후보 수준)"
        elif energy <= -6:
            energy_desc = "보통~강한 결합 (리드 화합물 수준)"
        elif energy <= -4:
            energy_desc = "보통 결합 (최적화 필요)"
        else:
            energy_desc = "약한 결합 (구조 수정 권장)"

        lines.append(f"결합 에너지: {energy:.1f} kcal/mol = {energy_desc}")
        lines.append("")

        # Interaction type descriptions
        TYPE_EXPLANATIONS = {
            "hydrogen_bond": "수소결합",
            "hydrophobic": "소수성 접촉",
            "pi_stacking": "Pi-Stacking",
            "salt_bridge": "염 다리 (이온 결합)",
            "halogen_bond": "할로겐 결합",
        }

        # Amino acid descriptions
        AA_DESC = {
            "ARG": ("Arg", "아르기닌", "양전하 구아니디늄기 보유, 강한 H-bond 공여체"),
            "LYS": ("Lys", "라이신", "양전하 아미노기 보유, H-bond 공여 및 염 다리 형성"),
            "ASP": ("Asp", "아스파르트산", "음전하 카복실기 보유, H-bond 수용 및 염 다리 형성"),
            "GLU": ("Glu", "글루탐산", "음전하 카복실기 보유, H-bond 수용 및 염 다리 형성"),
            "HIS": ("His", "히스티딘", "이미다졸 고리 보유, pH 의존적 양전하, Pi-stacking 가능"),
            "PHE": ("Phe", "페닐알라닌", "방향족 벤질기 보유, 소수성/Pi-stacking 주요 잔기"),
            "TYR": ("Tyr", "타이로신", "페놀 -OH 보유, H-bond 공여/수용 및 Pi-stacking 가능"),
            "TRP": ("Trp", "트립토판", "인돌 고리 보유, 강한 Pi-stacking 및 소수성 상호작용"),
            "SER": ("Ser", "세린", "-OH 보유, H-bond 공여/수용"),
            "THR": ("Thr", "트레오닌", "-OH 보유, H-bond 공여/수용"),
            "CYS": ("Cys", "시스테인", "-SH 보유, 이황화 결합 형성 가능"),
            "MET": ("Met", "메티오닌", "황 원자 포함 소수성 잔기"),
            "ALA": ("Ala", "알라닌", "소수성 메틸기, 소수성 포켓 형성에 기여"),
            "VAL": ("Val", "발린", "소수성 이소프로필기, 소수성 코어 형성"),
            "LEU": ("Leu", "류신", "소수성 이소부틸기, 소수성 포켓 주요 구성 잔기"),
            "ILE": ("Ile", "이소류신", "소수성 2차 부틸기, 소수성 상호작용"),
            "PRO": ("Pro", "프롤린", "고리형 이미노산, 단백질 구조 제한"),
            "GLY": ("Gly", "글리신", "가장 작은 아미노산, 유연한 구조 허용"),
            "ASN": ("Asn", "아스파라긴", "아미드기 보유, H-bond 공여/수용"),
            "GLN": ("Gln", "글루타민", "아미드기 보유, H-bond 공여/수용"),
        }

        for inter in interactions:
            res_label = f"{inter.residue_name}{inter.residue_id}"
            type_name = TYPE_EXPLANATIONS.get(inter.type, inter.type)
            aa_info = AA_DESC.get(inter.residue_name, ("", "", ""))
            aa_korean = aa_info[1] if aa_info[1] else inter.residue_name
            aa_property = aa_info[2] if aa_info[2] else ""

            # Build explanation per interaction type
            if inter.type == "hydrogen_bond":
                explanation = (
                    f"{res_label}({aa_korean})과 {type_name}: "
                    f"리간드의 극성 원자가 {res_label}의 {inter.protein_atom_name}과 "
                    f"수소결합 형성 (거리: {inter.distance:.1f}A)"
                )
                if aa_property:
                    explanation += f" [{aa_property}]"
            elif inter.type == "hydrophobic":
                explanation = (
                    f"{res_label}({aa_korean})과 {type_name}: "
                    f"리간드의 비극성 부분이 {res_label}의 소수성 측쇄와 "
                    f"반데르발스 접촉 (거리: {inter.distance:.1f}A)"
                )
            elif inter.type == "pi_stacking":
                explanation = (
                    f"{res_label}({aa_korean})과 {type_name}: "
                    f"리간드의 방향족 고리가 {res_label}의 방향족 측쇄와 "
                    f"Pi 전자 적층 상호작용 (거리: {inter.distance:.1f}A)"
                )
            elif inter.type == "salt_bridge":
                explanation = (
                    f"{res_label}({aa_korean})과 {type_name}: "
                    f"리간드의 이온성 기와 {res_label}의 전하 측쇄 간 "
                    f"정전기적 상호작용 (거리: {inter.distance:.1f}A)"
                )
            elif inter.type == "halogen_bond":
                explanation = (
                    f"{res_label}({aa_korean})과 {type_name}: "
                    f"리간드의 할로겐 원자가 {res_label}의 {inter.protein_atom_name}과 "
                    f"할로겐 결합 형성 (거리: {inter.distance:.1f}A)"
                )
            else:
                explanation = (
                    f"{res_label}({aa_korean})과 {type_name} "
                    f"(거리: {inter.distance:.1f}A)"
                )

            lines.append(f"  {explanation}")

        # Add context about key residues if receptor is known
        if meta and meta.binding_site_residues:
            lines.append("")
            known_set = set(meta.binding_site_residues)
            matched = []
            for inter in interactions:
                label = f"{inter.residue_name[:3]}{inter.residue_id}"
                # Try matching with 3-letter code format
                for known in known_set:
                    if str(inter.residue_id) in known:
                        matched.append(known)
            if matched:
                unique_matched = list(set(matched))[:5]
                lines.append(
                    f"알려진 활성 부위 잔기와의 매칭: {', '.join(unique_matched)} "
                    f"-- 이 수용체의 알려진 약물 결합 부위에서 상호작용이 확인됨"
                )

        # ── 분자-수용체 종합 약리학적 해석 ──
        lines.append("")
        lines.append("── 종합 약리학적 해석 ──")

        # Compute ligand properties from SMILES
        ligand_smiles = self.smiles_input.text().strip() if hasattr(self, 'smiles_input') else ""
        mw, logp, hbd, hba, tpsa = 0, 0, 0, 0, 0
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, rdMolDescriptors
            mol = Chem.MolFromSmiles(ligand_smiles)
            if mol:
                mw = Descriptors.MolWt(mol)
                logp = Descriptors.MolLogP(mol)
                hbd = rdMolDescriptors.CalcNumHBD(mol)
                hba = rdMolDescriptors.CalcNumHBA(mol)
                tpsa = Descriptors.TPSA(mol)
        except Exception:
            pass

        if mw > 0:
            # Lipinski / BBB interpretation
            lipinski_ok = mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10
            bbb_likely = mw < 400 and logp > 1 and logp < 4 and tpsa < 90 and hbd <= 3

            lines.append(f"리간드: MW={mw:.1f}, LogP={logp:.2f}, HBD={hbd}, HBA={hba}, TPSA={tpsa:.1f}Å²")
            lines.append(f"Lipinski 규칙: {'✅ 충족 (경구 투여 가능성 높음)' if lipinski_ok else '⚠️ 위반 — 경구 생체이용률 제한 가능'}")

            if meta:
                # BBB context with receptor location
                if meta.bbb_notes:
                    if bbb_likely:
                        lines.append(f"BBB 통과: ✅ 예상됨 (MW<400, 1<LogP<4, TPSA<90) → {meta.bbb_notes}")
                    else:
                        reason = []
                        if mw >= 400: reason.append(f"MW={mw:.0f}>400")
                        if logp <= 1 or logp >= 4: reason.append(f"LogP={logp:.1f} 범위 밖")
                        if tpsa >= 90: reason.append(f"TPSA={tpsa:.0f}>90")
                        if hbd > 3: reason.append(f"HBD={hbd}>3")
                        lines.append(f"BBB 통과: ⚠️ 제한적 ({', '.join(reason)}) → {meta.bbb_notes}")

                # Tissue location context
                if meta.tissue_location:
                    lines.append(f"표적 위치: {meta.tissue_location}")
                    if "뇌" in meta.tissue_location and not bbb_likely:
                        lines.append("⚠️ 이 수용체는 뇌에 위치하나, 리간드의 BBB 통과가 제한적 → 중추 작용 기대 어려움. 구조 최적화(LogP 증가, TPSA 감소) 필요")
                    elif "뇌" in meta.tissue_location and bbb_likely:
                        lines.append("✅ 이 수용체는 뇌에 위치하며, 리간드의 BBB 통과 예상 → 중추 신경계 효과 가능")

                # Binding strength in pharmacological context
                if energy <= -8:
                    lines.append(f"결합 친화도 해석: {energy:.1f} kcal/mol은 기존 약물({', '.join(meta.known_drugs[:2])})과 유사한 수준의 강한 결합")
                elif energy <= -6:
                    lines.append(f"결합 친화도 해석: {energy:.1f} kcal/mol은 중간 수준 — 기존 약물({', '.join(meta.known_drugs[:2])}) 대비 최적화 여지 있음")
                else:
                    lines.append(f"결합 친화도 해석: {energy:.1f} kcal/mol은 약한 결합 — 추가 작용기 도입 또는 구조 수정 권장")

                # Nervous system context
                if meta.nervous_system:
                    lines.append(f"신경계 연관: {meta.nervous_system}")

        return "\n".join(lines)

    def _populate_results_tab(self):
        if not self.docking_result:
            return

        poses = self.docking_result.poses

        # Table
        self.results_table.setRowCount(len(poses))
        for i, pose in enumerate(poses):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(pose.pose_id)))

            energy_item = QTableWidgetItem(f"{pose.affinity_kcal:.2f}")
            if pose.affinity_kcal == self.docking_result.best_affinity:
                energy_item.setBackground(QColor(200, 255, 200))
            self.results_table.setItem(i, 1, energy_item)

            self.results_table.setItem(i, 2, QTableWidgetItem(f"{pose.rmsd_lb:.2f}"))
            self.results_table.setItem(i, 3, QTableWidgetItem(f"{pose.rmsd_ub:.2f}"))

        # Energy chart
        if MATPLOTLIB_AVAILABLE and poses:
            self.energy_figure.clear()
            ax = self.energy_figure.add_subplot(111)

            ids = [p.pose_id for p in poses]
            energies = [p.affinity_kcal for p in poses]
            colors = ['#4CAF50' if e == min(energies) else '#2196F3' for e in energies]

            ax.bar(ids, energies, color=colors, edgecolor='white', linewidth=0.5)
            ax.set_xlabel("Pose")
            ax.set_ylabel("Binding Energy (kcal/mol)")
            ax.set_title("Docking Pose Energies")
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.3)

            self.energy_figure.tight_layout()
            self.energy_canvas.draw()

        # Summary
        if poses:
            best = min(poses, key=lambda p: p.affinity_kcal)
            best_interactions = self.docking_result.interactions.get(best.pose_id, [])
            n_hbonds = sum(1 for i in best_interactions if i.type == "hydrogen_bond")
            n_hydro = sum(1 for i in best_interactions if i.type == "hydrophobic")
            n_pi = sum(1 for i in best_interactions if i.type == "pi_stacking")

            self.summary_label.setText(
                f"최적 포즈 #{best.pose_id}: {best.affinity_kcal:.2f} kcal/mol | "
                f"H-Bond: {n_hbonds} | Hydrophobic: {n_hydro} | Pi-stacking: {n_pi} | "
                f"총 {len(best_interactions)}개 상호작용"
            )

    def _populate_interactions_tab(self):
        if not self.docking_result:
            return

        self.pose_selector.clear()
        for pose in self.docking_result.poses:
            self.pose_selector.addItem(
                f"포즈 #{pose.pose_id} ({pose.affinity_kcal:.2f} kcal/mol)",
                pose.pose_id,
            )

    def _populate_3d_tab(self):
        if not self.docking_result or not DOCKING_3D_AVAILABLE:
            return

        if hasattr(self, 'viewer_pose_selector'):
            self.viewer_pose_selector.clear()
            for pose in self.docking_result.poses:
                self.viewer_pose_selector.addItem(
                    f"포즈 #{pose.pose_id} ({pose.affinity_kcal:.2f} kcal/mol)",
                    pose.pose_id,
                )

    def _on_pose_selected(self, row: int):
        """When a pose is selected in results table, update other tabs"""
        if self.docking_result and 0 <= row < len(self.docking_result.poses):
            pose = self.docking_result.poses[row]
            interactions = self.docking_result.interactions.get(pose.pose_id, [])
            # Update binding reason on receptor info panel
            if hasattr(self, 'ri_binding_reason_label'):
                self._update_binding_reason(pose, interactions)
            # Sync pose selector in interactions tab
            idx = self.pose_selector.findData(pose.pose_id)
            if idx >= 0:
                self.pose_selector.setCurrentIndex(idx)

    def _on_interaction_pose_changed(self, index: int):
        if not self.docking_result or index < 0:
            return

        pose_id = self.pose_selector.currentData()
        if pose_id is None:
            return

        pose = next((p for p in self.docking_result.poses if p.pose_id == pose_id), None)
        interactions = self.docking_result.interactions.get(pose_id, [])

        # Update table
        self.interaction_table.setRowCount(len(interactions))
        for i, inter in enumerate(interactions):
            self.interaction_table.setItem(i, 0, QTableWidgetItem(inter.type_label))
            self.interaction_table.setItem(i, 1, QTableWidgetItem(
                f"{inter.residue_name}-{inter.residue_id}"
            ))
            self.interaction_table.setItem(i, 2, QTableWidgetItem(inter.protein_atom_name))
            self.interaction_table.setItem(i, 3, QTableWidgetItem(f"{inter.distance:.2f}"))
            self.interaction_table.setItem(i, 4, QTableWidgetItem(inter.chain))

        # Update interaction interpretation panel
        if pose and hasattr(self, 'interaction_interpretation'):
            interpretation = self._build_interaction_interpretation(pose, interactions)
            self.interaction_interpretation.setPlainText(interpretation)

        # Update binding reason on results tab
        if pose and hasattr(self, 'ri_binding_reason_label'):
            self._update_binding_reason(pose, interactions)

        # Update 2D interaction map
        if MATPLOTLIB_AVAILABLE:
            self.interaction_figure.clear()
            if interactions:
                mode = "Circle"
                if hasattr(self, 'diagram_mode_combo'):
                    mode = self.diagram_mode_combo.currentText()

                dst_ax = self.interaction_figure.add_subplot(111)
                if mode == "Ligand" and self.ligand and RDKIT_AVAILABLE:
                    self._draw_ligand_interaction_map(dst_ax, interactions)
                else:
                    self._draw_interaction_map(dst_ax, interactions)
            self.interaction_canvas.draw()

    def _draw_interaction_map(self, ax, interactions: list):
        """Draw 2D interaction map directly on given axes"""
        import math as _math
        import matplotlib.patches as _patches

        ax.set_xlim(-2.5, 2.5)
        ax.set_ylim(-2.5, 2.5)
        ax.set_aspect('equal')
        ax.axis('off')

        TYPE_COLORS = {
            "hydrogen_bond": "#2196F3",
            "hydrophobic": "#FF9800",
            "pi_stacking": "#9C27B0",
            "salt_bridge": "#F44336",
            "halogen_bond": "#00BCD4",
        }

        # Ligand center
        lig_circle = plt.Circle((0, 0), 0.5, color='#4CAF50', alpha=0.8, zorder=5)
        ax.add_patch(lig_circle)
        lig_name = self.ligand.smiles[:12] if self.ligand else "Ligand"
        ax.text(0, 0, lig_name, ha='center', va='center',
                fontsize=8, fontweight='bold', color='white', zorder=6)

        unique_residues = list(set(
            (i.residue_name, i.residue_id, i.chain) for i in interactions
        ))
        n = len(unique_residues)
        if n == 0:
            return

        for idx, (res_name, res_id, chain) in enumerate(unique_residues):
            angle = 2 * _math.pi * idx / n - _math.pi / 2
            rx = 1.8 * _math.cos(angle)
            ry = 1.8 * _math.sin(angle)

            res_ints = [i for i in interactions
                        if i.residue_name == res_name and i.residue_id == res_id]
            color = TYPE_COLORS.get(res_ints[0].type, "#9E9E9E") if res_ints else "#9E9E9E"

            circle = plt.Circle((rx, ry), 0.35, color=color, alpha=0.3, zorder=3)
            ax.add_patch(circle)
            border = plt.Circle((rx, ry), 0.35, fill=False,
                                edgecolor=color, linewidth=2, zorder=4)
            ax.add_patch(border)

            ax.text(rx, ry, f"{res_name}\n{res_id}", ha='center', va='center',
                    fontsize=8, fontweight='bold', zorder=5)

            for inter in res_ints:
                c = TYPE_COLORS.get(inter.type, "#9E9E9E")
                ax.plot([0, rx], [0, ry], color=c, linestyle='--',
                        linewidth=1.5, alpha=0.7, zorder=2)
                mx, my = rx/2, ry/2
                ax.text(mx, my, f"{inter.distance}Å", fontsize=7,
                        ha='center', va='center',
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                  edgecolor=c, alpha=0.9), zorder=4)

        # Legend
        seen = set(i.type for i in interactions)
        patches = []
        for t, c in TYPE_COLORS.items():
            if t in seen:
                label = {"hydrogen_bond": "H-Bond", "hydrophobic": "Hydrophobic",
                         "pi_stacking": "Pi-Stack", "salt_bridge": "Salt Bridge"}.get(t, t)
                patches.append(_patches.Patch(color=c, label=label, alpha=0.7))
        if patches:
            ax.legend(handles=patches, loc='upper right', fontsize=8)

        ax.set_title("Protein-Ligand Interactions", fontsize=12, fontweight='bold')

    def _draw_ligand_interaction_map(self, ax, interactions: list):
        """리간드 2D 골격식 중앙 배치 + 잔기 원형 배치 + 상호작용 점선"""
        import math as _math
        import matplotlib.patches as _patches
        from rdkit import Chem
        from rdkit.Chem import AllChem

        TYPE_COLORS = {
            "hydrogen_bond": "#4CAF50",    # 초록 (H-bond)
            "hydrophobic": "#9E9E9E",       # 회색 (소수성)
            "pi_stacking": "#9C27B0",       # 보라 (pi-stacking)
            "salt_bridge": "#F44336",        # 빨강 (salt bridge)
            "halogen_bond": "#00BCD4",       # 시안 (halogen)
        }
        TYPE_LABELS = {
            "hydrogen_bond": "H-Bond",
            "hydrophobic": "Hydrophobic",
            "pi_stacking": "π-Stacking",
            "salt_bridge": "Salt Bridge",
            "halogen_bond": "Halogen Bond",
        }

        # SMARTS 작용기 패턴
        FG_PATTERNS = {
            "OH": "[OX2H]",
            "COOH": "[CX3](=O)[OX2H1]",
            "NH2": "[NX3H2]",
            "C=O": "[CX3]=[OX1]",
            "Aromatic": "c1ccccc1",
            "Halogen": "[F,Cl,Br,I]",
        }

        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_facecolor('white')

        smiles = self.ligand.smiles if self.ligand else ""
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            # Fallback to circle mode
            self._draw_interaction_map(ax, interactions)
            return

        mol = Chem.RemoveHs(mol)
        AllChem.Compute2DCoords(mol)
        conf = mol.GetConformer()
        n_atoms = mol.GetNumAtoms()
        if n_atoms == 0:
            self._draw_interaction_map(ax, interactions)
            return

        # 2D 좌표 수집
        coords = {}
        for i in range(n_atoms):
            pos = conf.GetAtomPosition(i)
            coords[i] = (pos.x, -pos.y)

        # 스케일: 분자를 [-1.5, 1.5] 범위에 맞추기
        all_x = [c[0] for c in coords.values()]
        all_y = [c[1] for c in coords.values()]
        cx = (min(all_x) + max(all_x)) / 2
        cy = (min(all_y) + max(all_y)) / 2
        mol_range = max(max(all_x) - min(all_x), max(all_y) - min(all_y), 1.0)
        scale = 2.5 / mol_range

        scaled = {}
        for i, (x, y) in coords.items():
            scaled[i] = ((x - cx) * scale, (y - cy) * scale)

        # 결합 그리기
        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            x1, y1 = scaled[i]
            x2, y2 = scaled[j]
            bt = bond.GetBondTypeAsDouble()
            if bt >= 2:
                dx, dy = x2 - x1, y2 - y1
                length = _math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    nx, ny = -dy/length * 0.06, dx/length * 0.06
                    ax.plot([x1+nx, x2+nx], [y1+ny, y2+ny], 'k-', linewidth=1.2, zorder=3)
                    ax.plot([x1-nx, x2-nx], [y1-ny, y2-ny], 'k-', linewidth=1.2, zorder=3)
            else:
                ax.plot([x1, x2], [y1, y2], 'k-', linewidth=1.2, zorder=3)

        # 원자 라벨 (헤테로원자만)
        ATOM_COLORS = {
            "O": "#FF0000", "N": "#0000FF", "S": "#CCCC00",
            "F": "#00CC00", "Cl": "#00CC00", "Br": "#8B2500", "I": "#9400D3",
        }
        for i in range(n_atoms):
            atom = mol.GetAtomWithIdx(i)
            sym = atom.GetSymbol()
            if sym == "C":
                continue
            x, y = scaled[i]
            color = ATOM_COLORS.get(sym, "black")
            ax.text(x, y, sym, ha='center', va='center', fontsize=8,
                    fontweight='bold', color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                              edgecolor='none', alpha=0.9))

        # 작용기 탐지 (SMARTS)
        fg_atoms = {}  # atom_idx → fg_name
        for fg_name, smarts in FG_PATTERNS.items():
            try:
                pat = Chem.MolFromSmarts(smarts)
                if pat:
                    matches = mol.GetSubstructMatches(pat)
                    for match in matches:
                        for idx in match:
                            if idx not in fg_atoms:
                                fg_atoms[idx] = fg_name
            except Exception:
                pass

        # 잔기 원형 배치
        unique_residues = list(set(
            (i.residue_name, i.residue_id, i.chain) for i in interactions
        ))
        n_res = len(unique_residues)
        if n_res == 0:
            # 바운딩 설정
            ax.set_xlim(-3.5, 3.5)
            ax.set_ylim(-3.5, 3.5)
            ax.set_title("Ligand-Centric Interaction Map", fontsize=12, fontweight='bold')
            return

        # 잔기 → 리간드 원자 연결선 + 원형 배치
        residue_radius = max(3.0, mol_range * scale * 0.6 + 1.0)

        for idx, (res_name, res_id, chain) in enumerate(unique_residues):
            angle = 2 * _math.pi * idx / n_res - _math.pi / 2
            rx = residue_radius * _math.cos(angle)
            ry = residue_radius * _math.sin(angle)

            res_ints = [i for i in interactions
                        if i.residue_name == res_name and i.residue_id == res_id
                        and i.chain == chain]

            color = TYPE_COLORS.get(res_ints[0].type, "#9E9E9E") if res_ints else "#9E9E9E"

            # 잔기 원
            circle = plt.Circle((rx, ry), 0.35, color=color, alpha=0.25, zorder=2)
            ax.add_patch(circle)
            border = plt.Circle((rx, ry), 0.35, fill=False,
                                edgecolor=color, linewidth=2, zorder=3)
            ax.add_patch(border)
            ax.text(rx, ry, f"{res_name}\n{res_id}", ha='center', va='center',
                    fontsize=7, fontweight='bold', zorder=4)

            # 상호작용 선: 리간드 원자 → 잔기
            for inter in res_ints:
                c = TYPE_COLORS.get(inter.type, "#9E9E9E")
                lig_idx = inter.ligand_atom_idx
                if lig_idx in scaled:
                    lx, ly = scaled[lig_idx]
                else:
                    lx, ly = 0, 0  # fallback to center
                ax.plot([lx, rx], [ly, ry], color=c, linestyle='--',
                        linewidth=1.2, alpha=0.7, zorder=1)
                mx, my = (lx + rx) / 2, (ly + ry) / 2
                ax.text(mx, my, f"{inter.distance:.1f}Å", fontsize=6,
                        ha='center', va='center',
                        bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                                  edgecolor=c, alpha=0.85), zorder=4)

        # 범례
        seen = set(i.type for i in interactions)
        patches = []
        for t, c in TYPE_COLORS.items():
            if t in seen:
                patches.append(_patches.Patch(color=c, label=TYPE_LABELS.get(t, t), alpha=0.7))
        if patches:
            ax.legend(handles=patches, loc='upper right', fontsize=7)

        ax.set_xlim(-residue_radius - 1, residue_radius + 1)
        ax.set_ylim(-residue_radius - 1, residue_radius + 1)
        ax.set_title("Ligand-Centric Interaction Map", fontsize=12, fontweight='bold')

    def _on_3d_pose_changed(self, index: int):
        if not self.docking_result or not DOCKING_3D_AVAILABLE or index < 0:
            return

        pose_id = self.viewer_pose_selector.currentData()
        if pose_id is None:
            return

        pose = next((p for p in self.docking_result.poses if p.pose_id == pose_id), None)
        if pose and hasattr(self, 'viewer_3d'):
            interactions = self.docking_result.interactions.get(pose_id, [])
            binding_site = None
            if hasattr(self, '_binding_site_cache'):
                binding_site = self._binding_site_cache.get(pose_id)
            # Fallback: binding_site 비어있으면 직접 추출 (5Å 반경)
            if not binding_site:
                try:
                    binding_site = InteractionAnalyzer.extract_binding_site_residues(
                        self.docking_result.receptor, pose, radius=5.0
                    )
                    if binding_site and hasattr(self, '_binding_site_cache'):
                        self._binding_site_cache[pose_id] = binding_site
                except Exception:
                    pass
            self.viewer_3d.set_data(
                self.docking_result.receptor, pose, interactions,
                binding_site_residues=binding_site
            )

    # ========== AI INTERPRETATION ==========

    def _populate_ai_tab(self):
        """Populate AI tab pose selector after docking completes"""
        if not self.docking_result:
            return
        self.ai_pose_selector.clear()
        for pose in self.docking_result.poses:
            self.ai_pose_selector.addItem(
                f"포즈 #{pose.pose_id} ({pose.affinity_kcal:.2f} kcal/mol)",
                pose.pose_id,
            )

    def _on_ai_analyze(self):
        """Run AI interpretation of selected docking pose"""
        if not self.docking_result:
            return

        pose_id = self.ai_pose_selector.currentData()
        if pose_id is None:
            return

        pose = next((p for p in self.docking_result.poses if p.pose_id == pose_id), None)
        if pose is None:
            return

        interactions = self.docking_result.interactions.get(pose_id, [])
        binding_site = self._binding_site_cache.get(pose_id, []) if hasattr(self, '_binding_site_cache') else []

        # Try Gemini API first, fallback to rule-based
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

        if _GENAI_AVAILABLE and api_key:
            self.ai_progress.setText("Gemini API 호출 중...")
            self.btn_ai_analyze.setEnabled(False)
            self.ai_result_text.clear()

            try:
                prompt = self._generate_ai_prompt(pose, interactions, binding_site)
                result_text = None
                # 1차: 새 SDK (google.genai)
                try:
                    import google.genai as _new_genai
                    client = _new_genai.Client(api_key=api_key)
                    for _model_name in ["gemini-2.5-flash", "gemini-2.0-flash"]:
                        try:
                            resp = client.models.generate_content(
                                model=_model_name, contents=prompt
                            )
                            result_text = resp.text
                            if result_text:
                                break
                        except Exception:
                            continue
                except ImportError:
                    pass
                # 2차: Old SDK fallback
                if not result_text and _genai_lib:
                    _genai_lib.configure(api_key=api_key)
                    model = _genai_lib.GenerativeModel("gemini-2.5-flash")
                    response = model.generate_content(prompt)
                    result_text = response.text

                if result_text:
                    self.ai_result_text.setMarkdown(result_text)
                    self.ai_progress.setText("AI 해석 완료")
                else:
                    raise RuntimeError("모든 모델에서 응답 없음")
            except Exception as e:
                # Fallback on API error
                self.ai_progress.setText(f"API 오류 — Rule-based 모드로 전환: {str(e)[:80]}")
                fallback = self._build_fallback_explanation(pose, interactions, binding_site)
                self.ai_result_text.setMarkdown(fallback)
            finally:
                self.btn_ai_analyze.setEnabled(True)
        else:
            # Rule-based fallback
            self.ai_progress.setText("Rule-based 해석 (Gemini API 미연결)")
            fallback = self._build_fallback_explanation(pose, interactions, binding_site)
            self.ai_result_text.setMarkdown(fallback)

    def _generate_ai_prompt(self, pose, interactions, binding_site) -> str:
        """Build Gemini prompt for docking result interpretation"""
        receptor = self.docking_result.receptor
        ligand = self.docking_result.ligand

        # Summarize interactions
        inter_summary = []
        for inter in interactions:
            inter_summary.append(
                f"  - {inter.type_label}: {inter.residue_name}-{inter.residue_id} "
                f"({inter.chain}) {inter.protein_atom_name} {inter.distance:.1f}A"
            )
        inter_text = "\n".join(inter_summary) if inter_summary else "  (상호작용 없음)"

        # Summarize binding site residues
        bs_names = [f"{r[0]}-{r[1]}" for r in binding_site[:20]]
        bs_text = ", ".join(bs_names) if bs_names else "(없음)"

        pdb_id = receptor.pdb_id or "unknown"
        smiles = ligand.smiles if ligand else "unknown"

        prompt = (
            f"You are an expert computational pharmacologist. Analyze the following "
            f"molecular docking result and provide a detailed interpretation in Korean.\n\n"
            f"## Docking Result\n"
            f"- Receptor PDB ID: {pdb_id}\n"
            f"- Receptor name: {receptor.name}\n"
            f"- Ligand SMILES: {smiles}\n"
            f"- Binding energy: {pose.affinity_kcal:.2f} kcal/mol\n"
            f"- Pose #{pose.pose_id}\n"
            f"- Binding site residues (within 5A): {bs_text}\n\n"
            f"## Detected Interactions\n{inter_text}\n\n"
            f"## Please provide:\n"
            f"1. **수용체 정보**: 이 수용체(PDB: {pdb_id})가 인체 내 어디에 위치하며 어떤 기능을 하는지\n"
            f"2. **결합 친화도 해석**: {pose.affinity_kcal:.2f} kcal/mol의 의미 "
            f"(강한/보통/약한 결합, 치료적 함의)\n"
            f"3. **핵심 상호작용 분석**: 어떤 아미노산 잔기가 어떤 유형의 상호작용을 형성하고 있는지, "
            f"이것이 약물의 효능에 어떤 의미가 있는지\n"
            f"4. **결합 부위 특성**: 결합 포켓의 소수성/친수성 특성\n"
            f"5. **약물 최적화 제안**: 결합을 강화하기 위한 구조 수정 제안 (존재하는 경우)\n\n"
            f"Answer in Korean with Markdown formatting."
        )
        return prompt

    def _build_fallback_explanation(self, pose, interactions, binding_site) -> str:
        """Rule-based fallback explanation when Gemini API is unavailable"""
        receptor = self.docking_result.receptor
        ligand = self.docking_result.ligand
        pdb_id = receptor.pdb_id or "unknown"
        smiles = ligand.smiles if ligand else "unknown"
        meta = get_receptor_metadata(pdb_id)

        # Classify binding strength
        energy = pose.affinity_kcal
        if energy <= -10:
            strength = "매우 강한"
            strength_desc = "약물 후보로서 매우 유망한 결합력을 보입니다."
        elif energy <= -7:
            strength = "강한"
            strength_desc = "일반적인 약물 수준의 결합력입니다."
        elif energy <= -5:
            strength = "보통"
            strength_desc = "중간 정도의 결합력으로, 구조 최적화가 필요할 수 있습니다."
        else:
            strength = "약한"
            strength_desc = "약한 결합력으로, 리간드 구조 수정이 권장됩니다."

        # Count interaction types
        n_hbond = sum(1 for i in interactions if i.type == "hydrogen_bond")
        n_hydro = sum(1 for i in interactions if i.type == "hydrophobic")
        n_pi = sum(1 for i in interactions if i.type == "pi_stacking")
        n_salt = sum(1 for i in interactions if i.type == "salt_bridge")
        n_halogen = sum(1 for i in interactions if i.type == "halogen_bond")

        # Binding site composition
        n_donor = sum(1 for r in binding_site if r[3])
        n_acceptor = sum(1 for r in binding_site if r[4])
        n_total = len(binding_site)

        # Key residues
        key_residues = []
        for inter in interactions[:10]:
            key_residues.append(f"**{inter.residue_name}-{inter.residue_id}** ({inter.type_label}, {inter.distance:.1f}A)")

        lines = [
            f"# 도킹 결과 해석 (Rule-based)",
            f"",
            f"> Gemini API가 연결되지 않아 규칙 기반 분석을 제공합니다.",
            f"> 환경변수 `GEMINI_API_KEY` 설정 시 AI 기반 상세 해석을 받을 수 있습니다.",
            f"",
            f"## 1. 수용체 정보",
            f"- PDB ID: **{pdb_id}**",
        ]

        if meta:
            lines.extend([
                f"- 이름: **{meta.name}**",
                f"- 유전자: {meta.gene}" if meta.gene else "",
                f"- **생체 기능**: {meta.function}",
                f"- **관련 질환**: {meta.disease_relevance}",
                f"- **기존 약물**: {', '.join(meta.known_drugs)}" if meta.known_drugs else "",
                f"- 생물종: {meta.organism}",
            ])
            lines = [l for l in lines if l]  # remove empty
        else:
            lines.extend([
                f"- 이름: {receptor.name}",
                f"- 원자 수: {receptor.atom_count:,} | 잔기 수: {receptor.residue_count}",
                f"- 체인: {', '.join(receptor.chains)}",
            ])

        lines.extend([
            f"",
            f"## 2. 결합 친화도",
            f"- 에너지: **{energy:.2f} kcal/mol** ({strength} 결합)",
            f"- {strength_desc}",
            f"",
            f"## 3. 상호작용 요약",
            f"| 유형 | 개수 |",
            f"|------|------|",
            f"| 수소 결합 (H-Bond) | {n_hbond} |",
            f"| 소수성 접촉 | {n_hydro} |",
            f"| Pi-Stacking | {n_pi} |",
            f"| 염 다리 (Salt Bridge) | {n_salt} |",
            f"| 할로겐 결합 | {n_halogen} |",
            f"| **총합** | **{len(interactions)}** |",
            f"",
            f"## 4. 핵심 상호작용 잔기 (상세 해석)",
        ])

        if interactions:
            # Add detailed interaction-by-interaction explanation
            interpretation = self._build_interaction_interpretation(pose, interactions)
            for line in interpretation.split("\n"):
                lines.append(line)
        else:
            lines.append("- (감지된 상호작용 없음)")

        if key_residues:
            lines.append("")
            lines.append("### 잔기 목록")
            for kr in key_residues:
                lines.append(f"- {kr}")

        lines.extend([
            f"",
            f"## 5. 결합 부위 특성",
            f"- 총 잔기 수 (5A 이내): **{n_total}**",
            f"- H-bond 공여 가능 잔기: {n_donor}",
            f"- H-bond 수용 가능 잔기: {n_acceptor}",
        ])

        if n_donor > n_acceptor:
            lines.append(f"- 결합 포켓은 **친수성(hydrophilic)** 특성이 우세합니다.")
        elif n_hydro > n_hbond:
            lines.append(f"- 결합 포켓은 **소수성(hydrophobic)** 특성이 우세합니다.")
        else:
            lines.append(f"- 결합 포켓은 친수성/소수성이 혼합된 특성을 보입니다.")

        lines.extend([
            f"",
            f"## 6. 리간드",
            f"- SMILES: `{smiles}`",
            f"",
            f"---",
            f"*이 분석은 규칙 기반 추정입니다. Gemini API 키를 설정하면 상세 해석을 받을 수 있습니다.*",
        ])

        return "\n".join(lines)

    def _update_dep_status(self):
        deps = []
        deps.append(f"Vina: {'OK (Python)' if VINA_PYTHON_AVAILABLE else 'Not found'}")
        deps.append(f"RDKit: {'OK' if RDKIT_AVAILABLE else 'Missing'}")
        deps.append(f"Meeko: {'OK' if MEEKO_AVAILABLE else 'Fallback'}")
        deps.append(f"OpenBabel: {'OK' if OBABEL_AVAILABLE else 'Fallback'}")
        deps.append(f"RCSB: {'OK' if REQUESTS_AVAILABLE else 'No requests'}")
        deps.append(f"3D Viewer: {'OK' if DOCKING_3D_AVAILABLE else 'Missing PyOpenGL'}")
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if _GENAI_AVAILABLE and api_key:
            deps.append("Gemini AI: OK")
        elif _GENAI_AVAILABLE:
            deps.append("Gemini AI: No API Key")
        else:
            deps.append("Gemini AI: Not installed")

        self.dep_label.setText("Dependencies: " + " | ".join(deps))


def launch_docking_viewer(canvas=None, parent=None):
    """Convenience function to launch docking popup"""
    popup = DockingPopup(canvas, parent)
    popup.exec()
