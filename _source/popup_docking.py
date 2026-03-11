# popup_docking.py (v1.0 - Molecular Docking Dashboard)
"""
ChemDraw Pro: Molecular Docking Simulation Dashboard
- Tab 1: Setup (receptor input, ligand preview, docking parameters)
- Tab 2: Results (pose table, binding energy chart)
- Tab 3: Interactions (2D interaction map, interaction table)
- Tab 4: 3D View (protein-ligand complex viewer)
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
        QWidget, QHeaderView, QSizePolicy
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
    DockingResult, Interaction
)
from docking_interface import (
    PDBParser, PDBDownloader, LigandPreparer, ReceptorPreparer,
    VinaDockingThread, DOCKING_AVAILABLE, VINA_PYTHON_AVAILABLE,
    RDKIT_AVAILABLE, MEEKO_AVAILABLE, OBABEL_AVAILABLE, REQUESTS_AVAILABLE
)
from docking_interaction_analyzer import InteractionAnalyzer

# Optional: 3D viewer
try:
    from docking_3d_viewer import Docking3DViewerWidget
    DOCKING_3D_AVAILABLE = True
except ImportError:
    DOCKING_3D_AVAILABLE = False


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
        main_layout.addWidget(self.tabs)

        # Disable result tabs initially
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.tabs.setTabEnabled(3, False)

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

        # Receptor info
        self.receptor_info = QLabel("")
        receptor_layout.addWidget(self.receptor_info)

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
        self.results_table.currentRowChanged.connect(self._on_pose_selected)
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

        splitter.addWidget(table_widget)

        # 2D interaction map
        if MATPLOTLIB_AVAILABLE:
            map_widget = QWidget()
            map_layout = QVBoxLayout(map_widget)
            map_layout.addWidget(QLabel("2D 상호작용 다이어그램"))

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

        # Populate results
        self._populate_results_tab()
        self._populate_interactions_tab()
        self._populate_3d_tab()

        # Enable tabs
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, True)
        self.tabs.setTabEnabled(3, DOCKING_3D_AVAILABLE)
        self.tabs.setCurrentIndex(1)

    def _on_docking_error(self, msg: str):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "도킹 오류", msg)
        self.status_label.setText("도킹 오류 발생")

    # ========== POPULATE RESULTS ==========

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

        # Update 2D interaction map
        if MATPLOTLIB_AVAILABLE:
            self.interaction_figure.clear()
            if interactions:
                lig_name = self.ligand.smiles[:15] if self.ligand else "Ligand"
                fig = InteractionAnalyzer.generate_2d_interaction_map(interactions, lig_name)
                if fig:
                    # Copy axes from generated figure to our canvas figure
                    src_ax = fig.axes[0]
                    dst_ax = self.interaction_figure.add_subplot(111)

                    # Redraw the interaction map directly
                    for child in src_ax.get_children():
                        pass  # matplotlib doesn't support easy axis copying

                    # Alternative: regenerate directly on our figure
                    self._draw_interaction_map(dst_ax, interactions)
                    plt.close(fig)
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

    def _on_3d_pose_changed(self, index: int):
        if not self.docking_result or not DOCKING_3D_AVAILABLE or index < 0:
            return

        pose_id = self.viewer_pose_selector.currentData()
        if pose_id is None:
            return

        pose = next((p for p in self.docking_result.poses if p.pose_id == pose_id), None)
        if pose and hasattr(self, 'viewer_3d'):
            interactions = self.docking_result.interactions.get(pose_id, [])
            self.viewer_3d.set_data(self.docking_result.receptor, pose, interactions)

    def _update_dep_status(self):
        deps = []
        deps.append(f"Vina: {'OK (Python)' if VINA_PYTHON_AVAILABLE else 'Not found'}")
        deps.append(f"RDKit: {'OK' if RDKIT_AVAILABLE else 'Missing'}")
        deps.append(f"Meeko: {'OK' if MEEKO_AVAILABLE else 'Fallback'}")
        deps.append(f"OpenBabel: {'OK' if OBABEL_AVAILABLE else 'Fallback'}")
        deps.append(f"RCSB: {'OK' if REQUESTS_AVAILABLE else 'No requests'}")
        deps.append(f"3D Viewer: {'OK' if DOCKING_3D_AVAILABLE else 'Missing PyOpenGL'}")

        self.dep_label.setText("Dependencies: " + " | ".join(deps))


def launch_docking_viewer(canvas=None, parent=None):
    """Convenience function to launch docking popup"""
    popup = DockingPopup(canvas, parent)
    popup.exec()
