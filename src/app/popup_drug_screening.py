# popup_drug_screening.py (v1.0 - Drug Screening Dashboard)
"""
ChemGrid: Drug Screening & Candidate Ranking Popup
- Tab 1: Candidate Input (SMILES list, CSV import, current molecule)
- Tab 2: Screening Results (ranked table with tier badges)
- Tab 3: Score Distribution (matplotlib bar chart)
- Tab 4: Filters (QED, ADMET, PAINS, tier filtering)
"""

import csv
import io
from typing import List, Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QTextEdit, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
        QGroupBox, QFormLayout, QProgressBar, QListWidget, QListWidgetItem,
        QWidget, QHeaderView, QSizePolicy, QSlider, QCheckBox, QMessageBox,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QFont, QColor, QBrush
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from drug_screening import (
        CompoundEntry, ScreeningHit, ScreeningResult,
        run_screening, score_compound, calculate_qed,
    )
    SCREENING_AVAILABLE = True
except ImportError:
    SCREENING_AVAILABLE = False

try:
    from admet_predictor import predict_admet, ADMETProfile
    ADMET_AVAILABLE = True
except ImportError:
    ADMET_AVAILABLE = False

# Tier colors
TIER_COLORS = {
    "A": "#27ae60",
    "B": "#f39c12",
    "C": "#e74c3c",
}


# ============================================================================
# SCREENING WORKER THREAD
# ============================================================================

class _ScreeningWorker(QThread):
    """Background thread for running screening pipeline."""
    progress = pyqtSignal(int)       # 0-100
    finished = pyqtSignal(object)    # ScreeningResult
    error = pyqtSignal(str)

    def __init__(self, compounds: List[CompoundEntry], parent=None):
        super().__init__(parent)
        self.compounds = compounds

    def run(self):
        try:
            if not SCREENING_AVAILABLE:
                self.error.emit("drug_screening module not available")
                return
            total = len(self.compounds)
            hits: List[ScreeningHit] = []
            for i, entry in enumerate(self.compounds):
                hit = score_compound(smiles=entry.smiles, name=entry.name)
                hit.rank = i + 1
                hits.append(hit)
                self.progress.emit(int((i + 1) / total * 100))

            # Sort and re-rank
            hits.sort(key=lambda h: h.composite_score, reverse=True)
            for i, hit in enumerate(hits):
                hit.rank = i + 1

            result = ScreeningResult()
            result.n_compounds = total
            result.n_hits = len(hits)
            result.hits = hits
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ============================================================================
# MAIN DIALOG
# ============================================================================

class DrugScreeningPopup(QDialog):
    """Drug screening and candidate ranking popup dialog."""

    def __init__(self, smiles_list: list = None, names_list: list = None, parent=None):
        super().__init__(parent)
        self._smiles_list: List[str] = smiles_list or []
        self._names_list: List[str] = names_list or []
        self._candidates: List[CompoundEntry] = []
        self._screening_result: Optional[ScreeningResult] = None
        self._all_hits: List[ScreeningHit] = []
        self._filtered_hits: List[ScreeningHit] = []
        self._worker: Optional[_ScreeningWorker] = None

        self.setWindowTitle("신약 스크리닝")
        self.resize(1100, 750)

        self._init_ui()
        self._populate_initial_candidates()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_tab_input()
        self._build_tab_results()
        self._build_tab_distribution()
        self._build_tab_filters()

    # ========================= Tab 1: Candidate Input =========================
    def _build_tab_input(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # SMILES text input
        grp_input = QGroupBox("SMILES 입력 (한 줄에 하나)")
        grp_layout = QVBoxLayout(grp_input)
        self.txt_smiles = QTextEdit()
        self.txt_smiles.setPlaceholderText("CCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O")
        self.txt_smiles.setMaximumHeight(140)
        grp_layout.addWidget(self.txt_smiles)
        vbox.addWidget(grp_input)

        # Buttons row
        btn_row = QHBoxLayout()
        self.btn_csv = QPushButton("CSV 불러오기")
        self.btn_csv.clicked.connect(self._on_load_csv)
        btn_row.addWidget(self.btn_csv)

        self.btn_add_current = QPushButton("현재 분자 추가")
        self.btn_add_current.clicked.connect(self._on_add_current_molecule)
        btn_row.addWidget(self.btn_add_current)

        self.btn_add_text = QPushButton("텍스트에서 추가")
        self.btn_add_text.clicked.connect(self._on_add_from_text)
        btn_row.addWidget(self.btn_add_text)

        btn_row.addStretch()
        vbox.addLayout(btn_row)

        # Candidate list
        grp_list = QGroupBox("후보 목록")
        list_layout = QVBoxLayout(grp_list)
        self.lst_candidates = QListWidget()
        list_layout.addWidget(self.lst_candidates)

        list_btn_row = QHBoxLayout()
        self.btn_remove = QPushButton("선택 삭제")
        self.btn_remove.clicked.connect(self._on_remove_candidate)
        list_btn_row.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("전체 삭제")
        self.btn_clear.clicked.connect(self._on_clear_candidates)
        list_btn_row.addWidget(self.btn_clear)
        list_btn_row.addStretch()
        list_layout.addLayout(list_btn_row)

        vbox.addWidget(grp_list)

        # Start screening
        bottom = QHBoxLayout()
        self.btn_start = QPushButton("스크리닝 시작")
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 4px; }"
        )
        self.btn_start.clicked.connect(self._on_start_screening)
        bottom.addWidget(self.btn_start)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        bottom.addWidget(self.progress)
        vbox.addLayout(bottom)

        self.tabs.addTab(tab, "후보 입력")

    # ========================= Tab 2: Results =========================
    def _build_tab_results(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        self.lbl_summary = QLabel("스크리닝 결과가 없습니다. '후보 입력' 탭에서 시작하세요.")
        self.lbl_summary.setFont(QFont("", 10))
        vbox.addWidget(self.lbl_summary)

        self.tbl_results = QTableWidget()
        self.tbl_results.setColumnCount(9)
        self.tbl_results.setHorizontalHeaderLabels([
            "순위", "분자명", "SMILES", "QED", "ADMET점수",
            "도킹점수", "복합점수", "티어", "PAINS경고",
        ])
        self.tbl_results.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.tbl_results.horizontalHeader().setStretchLastSection(True)
        self.tbl_results.setSortingEnabled(True)
        self.tbl_results.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tbl_results.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.tbl_results.doubleClicked.connect(self._on_row_double_click)
        vbox.addWidget(self.tbl_results)

        self.tabs.addTab(tab, "스크리닝 결과")

    # ========================= Tab 3: Distribution =========================
    def _build_tab_distribution(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        if MATPLOTLIB_AVAILABLE:
            self.fig = Figure(figsize=(10, 5), dpi=100)
            self.chart_canvas = FigureCanvas(self.fig)
            self.chart_canvas.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            vbox.addWidget(self.chart_canvas)
        else:
            vbox.addWidget(QLabel("matplotlib이 설치되지 않아 차트를 표시할 수 없습니다."))

        self.tabs.addTab(tab, "점수 분포")

    # ========================= Tab 4: Filters =========================
    def _build_tab_filters(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # QED minimum
        grp_qed = QGroupBox("QED 최소값")
        qed_layout = QHBoxLayout(grp_qed)
        self.slider_qed = QSlider(Qt.Orientation.Horizontal)
        self.slider_qed.setRange(0, 100)
        self.slider_qed.setValue(0)
        self.lbl_qed_val = QLabel("0.00")
        self.slider_qed.valueChanged.connect(
            lambda v: self.lbl_qed_val.setText(f"{v / 100:.2f}")
        )
        qed_layout.addWidget(self.slider_qed)
        qed_layout.addWidget(self.lbl_qed_val)
        vbox.addWidget(grp_qed)

        # ADMET minimum
        grp_admet = QGroupBox("ADMET 최소값")
        admet_layout = QHBoxLayout(grp_admet)
        self.slider_admet = QSlider(Qt.Orientation.Horizontal)
        self.slider_admet.setRange(0, 100)
        self.slider_admet.setValue(0)
        self.lbl_admet_val = QLabel("0.00")
        self.slider_admet.valueChanged.connect(
            lambda v: self.lbl_admet_val.setText(f"{v / 100:.2f}")
        )
        admet_layout.addWidget(self.slider_admet)
        admet_layout.addWidget(self.lbl_admet_val)
        vbox.addWidget(grp_admet)

        # PAINS filter
        grp_pains = QGroupBox("구조 경고 필터")
        pains_layout = QVBoxLayout(grp_pains)
        self.chk_pains = QCheckBox("PAINS 경고 분자 제외")
        pains_layout.addWidget(self.chk_pains)
        vbox.addWidget(grp_pains)

        # Tier filter
        grp_tier = QGroupBox("티어 필터")
        tier_layout = QHBoxLayout(grp_tier)
        self.chk_tier_a = QCheckBox("A (우수)")
        self.chk_tier_a.setChecked(True)
        self.chk_tier_b = QCheckBox("B (보통)")
        self.chk_tier_b.setChecked(True)
        self.chk_tier_c = QCheckBox("C (약함)")
        self.chk_tier_c.setChecked(True)
        tier_layout.addWidget(self.chk_tier_a)
        tier_layout.addWidget(self.chk_tier_b)
        tier_layout.addWidget(self.chk_tier_c)
        vbox.addWidget(grp_tier)

        # Apply button
        self.btn_apply_filter = QPushButton("필터 적용")
        self.btn_apply_filter.setStyleSheet(
            "QPushButton { background-color: #8e44ad; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 4px; }"
        )
        self.btn_apply_filter.clicked.connect(self._on_apply_filters)
        vbox.addWidget(self.btn_apply_filter)

        vbox.addStretch()
        self.tabs.addTab(tab, "필터")

    # ------------------------------------------------------------------ Logic

    def _populate_initial_candidates(self):
        """Add any pre-supplied SMILES to the candidate list."""
        for i, smi in enumerate(self._smiles_list):
            name = self._names_list[i] if i < len(self._names_list) else f"Mol-{i + 1}"
            self._add_candidate(smi, name)

    def _add_candidate(self, smiles: str, name: str = ""):
        smiles = smiles.strip()
        if not smiles:
            return
        entry = CompoundEntry(smiles=smiles, name=name) if SCREENING_AVAILABLE else None
        if entry is None:
            # Fallback: store as tuple-like object
            class _FakeEntry:
                def __init__(self, s, n):
                    self.smiles = s
                    self.name = n
            entry = _FakeEntry(smiles, name)
        self._candidates.append(entry)
        display = f"{name}: {smiles}" if name else smiles
        self.lst_candidates.addItem(QListWidgetItem(display))

    def _on_load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "CSV 파일 불러오기", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    smiles = row.get("smiles", row.get("SMILES", "")).strip()
                    name = row.get("name", row.get("Name", row.get("NAME", ""))).strip()
                    if smiles:
                        self._add_candidate(smiles, name)
                        count += 1
            QMessageBox.information(self, "CSV 불러오기", f"{count}개 분자를 추가했습니다.")
        except Exception as exc:
            QMessageBox.warning(self, "CSV 오류", f"CSV 파일 읽기 실패:\n{exc}")

    def _on_add_current_molecule(self):
        """Add the SMILES from the parent canvas (if available)."""
        parent = self.parent()
        smiles = ""
        if parent and hasattr(parent, "get_smiles"):
            smiles = parent.get_smiles()
        elif parent and hasattr(parent, "canvas") and hasattr(parent.canvas, "get_smiles"):
            smiles = parent.canvas.get_smiles()
        if smiles:
            self._add_candidate(smiles, "현재분자")
        else:
            QMessageBox.information(self, "알림", "캔버스에 분자가 없습니다.")

    def _on_add_from_text(self):
        """Parse the SMILES text area and add each line as a candidate."""
        text = self.txt_smiles.toPlainText().strip()
        if not text:
            return
        count = 0
        for line in text.splitlines():
            parts = line.strip().split(",", 1)
            smiles = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else ""
            if smiles:
                self._add_candidate(smiles, name)
                count += 1
        self.txt_smiles.clear()
        QMessageBox.information(self, "추가 완료", f"{count}개 분자를 추가했습니다.")

    def _on_remove_candidate(self):
        row = self.lst_candidates.currentRow()
        if row >= 0:
            self.lst_candidates.takeItem(row)
            self._candidates.pop(row)

    def _on_clear_candidates(self):
        self.lst_candidates.clear()
        self._candidates.clear()

    def _on_start_screening(self):
        if not self._candidates:
            QMessageBox.warning(self, "경고", "후보 분자가 없습니다.")
            return
        if not SCREENING_AVAILABLE:
            QMessageBox.warning(self, "경고", "drug_screening 모듈을 사용할 수 없습니다.")
            return

        self.btn_start.setEnabled(False)
        self.progress.setValue(0)

        self._worker = _ScreeningWorker(self._candidates, self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_screening_done)
        self._worker.error.connect(self._on_screening_error)
        self._worker.start()

    def _on_screening_done(self, result: "ScreeningResult"):
        self._screening_result = result
        self._all_hits = list(result.hits)
        self._filtered_hits = list(result.hits)
        self.btn_start.setEnabled(True)
        self.progress.setValue(100)

        self._refresh_results_table(self._filtered_hits)
        self._refresh_chart(self._filtered_hits)
        self.tabs.setCurrentIndex(1)

    def _on_screening_error(self, msg: str):
        self.btn_start.setEnabled(True)
        QMessageBox.critical(self, "스크리닝 오류", msg)

    # ------------------------------------------------------------------ Table

    def _refresh_results_table(self, hits: List["ScreeningHit"]):
        self.tbl_results.setSortingEnabled(False)
        self.tbl_results.setRowCount(len(hits))

        self.lbl_summary.setText(
            f"총 {len(self._all_hits)}개 중 {len(hits)}개 표시 | "
            f"A: {sum(1 for h in hits if h.tier == 'A')}  "
            f"B: {sum(1 for h in hits if h.tier == 'B')}  "
            f"C: {sum(1 for h in hits if h.tier == 'C')}"
        )

        for row, hit in enumerate(hits):
            # Rank
            self.tbl_results.setItem(row, 0, self._num_item(hit.rank))
            # Name
            self.tbl_results.setItem(row, 1, QTableWidgetItem(hit.compound.name))
            # SMILES
            self.tbl_results.setItem(row, 2, QTableWidgetItem(hit.compound.smiles))
            # QED
            qed_val = hit.qed.qed_score if hit.qed else 0.0
            self.tbl_results.setItem(row, 3, self._num_item(qed_val, fmt=".3f"))
            # ADMET score
            admet_val = hit.admet.drug_likeness_score if hit.admet else 0.0
            self.tbl_results.setItem(row, 4, self._num_item(admet_val, fmt=".3f"))
            # Docking score
            dock_val = hit.docking.binding_affinity if hit.docking else 0.0
            self.tbl_results.setItem(row, 5, self._num_item(dock_val, fmt=".2f"))
            # Composite score
            self.tbl_results.setItem(
                row, 6, self._num_item(hit.composite_score, fmt=".3f")
            )
            # Tier badge
            tier_item = QTableWidgetItem(hit.tier)
            tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = TIER_COLORS.get(hit.tier, "#999999")
            tier_item.setForeground(QBrush(QColor(color)))
            tier_item.setFont(QFont("", 10, QFont.Weight.Bold))
            self.tbl_results.setItem(row, 7, tier_item)
            # PAINS warning
            n_alerts = hit.qed.n_alerts if hit.qed else 0
            pains_item = QTableWidgetItem(str(n_alerts) if n_alerts else "-")
            if n_alerts > 0:
                pains_item.setForeground(QBrush(QColor("#e74c3c")))
                pains_item.setFont(QFont("", 9, QFont.Weight.Bold))
            pains_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_results.setItem(row, 8, pains_item)

        self.tbl_results.setSortingEnabled(True)
        self.tbl_results.resizeColumnsToContents()

    @staticmethod
    def _num_item(value, fmt: str = "d") -> QTableWidgetItem:
        """Create a right-aligned numeric table item that sorts numerically."""
        if isinstance(value, float):
            text = f"{value:{fmt}}"
        else:
            text = str(value)
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.DisplayRole, text)
        item.setData(Qt.ItemDataRole.UserRole, float(value) if isinstance(value, (int, float)) else 0.0)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def _on_row_double_click(self, index):
        """Open ADMET detail popup for the double-clicked molecule."""
        row = index.row()
        smiles_item = self.tbl_results.item(row, 2)
        if smiles_item is None:
            return
        smiles = smiles_item.text()
        name_item = self.tbl_results.item(row, 1)
        name = name_item.text() if name_item else ""

        try:
            from popup_admet import ADMETPopup
            dlg = ADMETPopup(smiles=smiles, mol_name=name, parent=self)
            dlg.exec()
        except ImportError:
            QMessageBox.information(
                self, "알림",
                f"ADMET 팝업을 열 수 없습니다.\nSMILES: {smiles}",
            )

    # ------------------------------------------------------------------ Chart

    def _refresh_chart(self, hits: List["ScreeningHit"]):
        if not MATPLOTLIB_AVAILABLE:
            return
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        if not hits:
            ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center", fontsize=14)
            self.chart_canvas.draw()
            return

        names = [h.compound.name or h.compound.smiles[:20] for h in hits]
        scores = [h.composite_score for h in hits]
        colors = [TIER_COLORS.get(h.tier, "#999999") for h in hits]

        bars = ax.bar(range(len(hits)), scores, color=colors, edgecolor="#333", linewidth=0.5)

        # Tier threshold lines
        ax.axhline(y=0.7, color="#27ae60", linestyle="--", linewidth=1, alpha=0.7, label="Tier A (0.7)")
        ax.axhline(y=0.4, color="#f39c12", linestyle="--", linewidth=1, alpha=0.7, label="Tier B (0.4)")

        ax.set_ylabel("복합 점수")
        ax.set_title("후보 분자 점수 분포")
        ax.set_ylim(0, 1.05)
        ax.set_xticks(range(len(hits)))
        ax.set_xticklabels(names, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=8)
        self.fig.tight_layout()
        self.chart_canvas.draw()

    # ------------------------------------------------------------------ Filters

    def _on_apply_filters(self):
        if not self._all_hits:
            QMessageBox.information(self, "알림", "스크리닝 결과가 없습니다.")
            return

        qed_min = self.slider_qed.value() / 100.0
        admet_min = self.slider_admet.value() / 100.0
        exclude_pains = self.chk_pains.isChecked()
        tiers = set()
        if self.chk_tier_a.isChecked():
            tiers.add("A")
        if self.chk_tier_b.isChecked():
            tiers.add("B")
        if self.chk_tier_c.isChecked():
            tiers.add("C")

        filtered = []
        for hit in self._all_hits:
            # QED filter
            qed_val = hit.qed.qed_score if hit.qed else 0.0
            if qed_val < qed_min:
                continue
            # ADMET filter
            admet_val = hit.admet.drug_likeness_score if hit.admet else 0.0
            if admet_val < admet_min:
                continue
            # PAINS filter
            if exclude_pains and hit.qed and hit.qed.n_alerts > 0:
                continue
            # Tier filter
            if hit.tier not in tiers:
                continue
            filtered.append(hit)

        self._filtered_hits = filtered
        self._refresh_results_table(filtered)
        self._refresh_chart(filtered)
        self.tabs.setCurrentIndex(1)
