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
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QTextEdit, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
        QGroupBox, QFormLayout, QProgressBar, QListWidget, QListWidgetItem,
        QWidget, QHeaderView, QSizePolicy, QSlider, QCheckBox, QMessageBox,
        QApplication,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QFont, QColor, QBrush, QFontDatabase
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# ── Korean font for matplotlib ──────────────────────────────────────
_MPL_KR_FONT = None
if MATPLOTLIB_AVAILABLE:
    import matplotlib
    import matplotlib.font_manager as fm
    _KR_FONT_PATHS = [
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/NanumGothic.ttf",   # 나눔고딕
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux fallback
    ]
    for _fp in _KR_FONT_PATHS:
        if os.path.exists(_fp):
            _MPL_KR_FONT = fm.FontProperties(fname=_fp)
            matplotlib.rcParams["font.family"] = _MPL_KR_FONT.get_name()
            fm.fontManager.addfont(_fp)
            break

# M1461: Qt widget font registration for Korean offscreen captures.
_QT_KR_FONT = "Malgun Gothic"
_QT_KR_FONT_READY = False


def _ensure_qt_korean_font_ready() -> str:
    """Register a Korean Qt font and return the selected family name."""
    global _QT_KR_FONT, _QT_KR_FONT_READY  # noqa: PLW0603
    if _QT_KR_FONT_READY:
        return _QT_KR_FONT
    if not PYQT_AVAILABLE:
        return _QT_KR_FONT
    app = QApplication.instance()
    if app is None:
        return _QT_KR_FONT
    for _font_path in (
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\malgunbd.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ):
        try:
            if os.path.exists(_font_path):
                _font_id = QFontDatabase.addApplicationFont(_font_path)
                if _font_id >= 0:
                    _families = QFontDatabase.applicationFontFamilies(_font_id)
                    if _families:
                        _QT_KR_FONT = _families[0]
                        break
        except Exception as exc:
            logger.warning("[M1461] Drug Screening Korean font load failed: %s", exc)
    app.setFont(QFont(_QT_KR_FONT, 10))
    _QT_KR_FONT_READY = True
    return _QT_KR_FONT

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

# DrugBank 로컬 모듈 (M646_INTEGRATE)
# 학술 인용: Wishart, D.S. et al. (2018) Nucleic Acids Res. 46(D1): D1074-D1082.
#           Knox, C. et al. (2024) Nucleic Acids Res. 52(D1): D1265-D1275.
try:
    import drugbank_local
    DRUGBANK_AVAILABLE = True
except ImportError:
    DRUGBANK_AVAILABLE = False

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

    def __init__(self, compounds: List[CompoundEntry] = None, parent=None):
        super().__init__(parent)
        self.compounds = compounds or []

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
        _ensure_qt_korean_font_ready()

        self.setWindowTitle("신약 스크리닝")
        self.resize(1100, 750)

        self._init_ui()
        self._populate_initial_candidates()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        _kr_font = _ensure_qt_korean_font_ready()
        self.setFont(QFont(_kr_font, 10))
        self.setStyleSheet(f"""
            QDialog, QWidget, QLabel, QGroupBox, QTabWidget, QTabBar,
            QListWidget, QTableWidget, QTextEdit, QPushButton, QCheckBox {{
                font-family: "{_kr_font}", "Malgun Gothic", "NanumGothic", sans-serif;
            }}
        """)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_tab_input()
        self._build_tab_results()
        self._build_tab_distribution()
        self._build_tab_filters()
        # M646_INTEGRATE: DrugBank Tanimoto 매칭 탭 (Wishart 2018, Knox 2024)
        self._build_tab_drugbank()
        # M646_LITE_PARITY: ChEMBL 외부 검색 탭 (Mendez 2019 NAR 47:D930)
        # router src/app 통합 — requests 직접 호출, web 라우터 거치지 않음.
        self._build_tab_chembl()

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
        self.lbl_summary.setFont(QFont(_QT_KR_FONT, 10))
        vbox.addWidget(self.lbl_summary)

        self.tbl_results = QTableWidget()
        self.tbl_results.setColumnCount(9)
        self.tbl_results.setHorizontalHeaderLabels([
            "순위", "분자명", "SMILES", "QED", "ADMET점수",
            "도킹근거/점수", "복합점수", "티어", "PAINS경고",
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

        # ── [M853 格忿#31] 외부 도킹 서비스 링크 패널 ──────────────────────────
        # 사용자: "신약개발 탭에서도 도킹 시뮬레이션 결합방향·강도 볼 수 있어야지"
        # Rule FF: Eberhardt 2021 / Sehnal 2021 / Grosdidier 2011 인용
        # Rule I: URL 상수 주석 필수. Rule S: PyQt6 시그널 확인.
        try:
            from PyQt6.QtWidgets import QFrame
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            ext_frame = QFrame()
            ext_frame.setStyleSheet(
                "QFrame { background: #1a2635; border: 2px solid #0288d1; "
                "border-radius: 8px; padding: 4px; margin-top: 4px; }"
            )
            ext_layout = QVBoxLayout(ext_frame)
            ext_layout.setSpacing(4)

            ext_header = QLabel(
                "외부 도킹/구조 참고 경로 — 로컬 점수와 분리"
            )
            ext_header.setStyleSheet(
                "font-weight: bold; font-size: 11pt; color: #81d4fa; "
                "background: transparent; border: none;"
            )
            ext_header.setWordWrap(True)
            ext_layout.addWidget(ext_header)

            ext_cite = QLabel(
                "Eberhardt et al. 2021 J.Chem.Inf.Model. 61:3891 (Vina 1.2)  |  "
                "Sehnal et al. 2021 NAR 49:W431 (Mol*)  |  "
                "Grosdidier et al. 2011 NAR 39:W270 (SwissDock)"
            )
            ext_cite.setStyleSheet(
                "color: #4fc3f7; font-size: 8pt; background: transparent; border: none;"
            )
            ext_cite.setWordWrap(True)
            ext_layout.addWidget(ext_cite)

            ext_boundary = QLabel(
                "Local screening uses descriptor/ADMET scores only unless docking evidence is loaded. "
                "These buttons open external routes; they do not add docking evidence to the table."
            )
            ext_boundary.setStyleSheet(
                "color: #ffcc80; font-size: 9pt; background: transparent; border: none;"
            )
            ext_boundary.setWordWrap(True)
            ext_layout.addWidget(ext_boundary)

            ext_btn_row = QHBoxLayout()

            btn_sw = QPushButton("SwissDock 외부 도킹")
            btn_sw.setStyleSheet(
                "QPushButton { background: #0288d1; color: white; font-weight: bold; "
                "font-size: 11px; padding: 7px 12px; border-radius: 4px; }"
                "QPushButton:hover { background: #0277bd; }"
            )
            btn_sw.setToolTip(
                "SwissDock — 게스트 사용 가능 외부 AutoDock Vina 서비스.\n"
                "외부 사이트에서 사용자가 별도로 제출한 경우에만 결합 강도/포즈를 확인합니다.\n"
                "로컬 표 점수는 도킹 증거가 로드되기 전까지 descriptor/ADMET 기반입니다.\n"
                "Grosdidier A. et al. 2011 NAR 39:W270"
            )
            SWISSDOCK_URL = "https://www.swissdock.ch/docking"  # [MAGIC] SwissDock 공식 서비스
            # Rule S: QPushButton.clicked — Qt6 공식 시그널 확인
            btn_sw.clicked.connect(
                lambda _checked=False, u=SWISSDOCK_URL: QDesktopServices.openUrl(QUrl(u))
            )
            ext_btn_row.addWidget(btn_sw)

            btn_pdbe = QPushButton("PDBe-KB 결합 데이터")
            btn_pdbe.setStyleSheet(
                "QPushButton { background: #1565c0; color: white; font-weight: bold; "
                "font-size: 11px; padding: 7px 12px; border-radius: 4px; }"
                "QPushButton:hover { background: #0d47a1; }"
            )
            btn_pdbe.setToolTip(
                "PDBe-KB — UniProt 기반 결합 부위 + 상호작용 잔기 데이터.\n"
                "참고 경로만 열며, 로컬 스크리닝 점수에 결합 증거를 자동 반영하지 않습니다.\n"
                "학술 인용: Sehnal et al. 2021 NAR 49:W431"
            )
            PDBE_KB_URL = "https://www.ebi.ac.uk/pdbe/pdbe-kb/proteins"  # [MAGIC] PDBe-KB UniProt
            # Rule S: QPushButton.clicked — Qt6 공식 시그널 확인
            btn_pdbe.clicked.connect(
                lambda _checked=False, u=PDBE_KB_URL: QDesktopServices.openUrl(QUrl(u))
            )
            ext_btn_row.addWidget(btn_pdbe)

            btn_molstar = QPushButton("Mol* 3D 시각화")
            btn_molstar.setStyleSheet(
                "QPushButton { background: #4a148c; color: white; font-weight: bold; "
                "font-size: 11px; padding: 7px 12px; border-radius: 4px; }"
                "QPushButton:hover { background: #38006b; }"
            )
            btn_molstar.setToolTip(
                "Mol* 공식 뷰어 — 단백질-리간드 3D 시각화 학술 표준.\n"
                "구조 시각화 경로이며, 도킹 로그/포즈가 없으면 로컬 도킹 증거가 아닙니다.\n"
                "Sehnal D. et al. 2021 Nucleic Acids Res 49:W431-W437"
            )
            MOLSTAR_URL = "https://molstar.org/viewer/"  # [MAGIC] Mol* 공식 뷰어
            # Rule S: QPushButton.clicked — Qt6 공식 시그널 확인
            btn_molstar.clicked.connect(
                lambda _checked=False, u=MOLSTAR_URL: QDesktopServices.openUrl(QUrl(u))
            )
            ext_btn_row.addWidget(btn_molstar)

            ext_layout.addLayout(ext_btn_row)

            ext_info = QLabel(
                "스크리닝 후 결과 분자를 외부 서비스에 별도로 제출할 수 있습니다.\n"
                "도킹 로그/포즈/결합 에너지 증거가 로드되기 전까지 이 화면의 순위는 로컬 descriptor/ADMET 추정입니다."
            )
            ext_info.setStyleSheet(
                "color: #90a4ae; font-size: 9pt; background: transparent; border: none;"
            )
            ext_info.setWordWrap(True)
            ext_layout.addWidget(ext_info)

            vbox.addWidget(ext_frame)
        except Exception as _ext_e:
            logger.warning(
                "[DrugScreeningPopup._build_tab_results] 외부 도킹 패널 생성 실패: %s (M853)", _ext_e
            )

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
                    # N-code type guard: CSV row from external file
                    if not isinstance(row, dict):
                        logger.warning("_on_load_csv: unexpected row type=%s, skipping", type(row).__name__)
                        continue
                    raw_smiles = row.get("smiles", row.get("SMILES", ""))
                    smiles = raw_smiles.strip() if isinstance(raw_smiles, str) else ""
                    raw_name = row.get("name", row.get("Name", row.get("NAME", "")))
                    name = raw_name.strip() if isinstance(raw_name, str) else ""
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
            f"C: {sum(1 for h in hits if h.tier == 'C')} | "
            "Local screening uses descriptor/ADMET scores only unless docking evidence is loaded."
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
            # Docking evidence/status: descriptor-only rows must not look docked.
            if hit.docking:
                dock_val = hit.docking.binding_affinity
                dock_item = QTableWidgetItem(f"{dock_val:.2f} kcal/mol")
                dock_item.setData(Qt.ItemDataRole.UserRole, float(dock_val))
                dock_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                dock_item = QTableWidgetItem("증거없음")
                dock_item.setData(Qt.ItemDataRole.UserRole, float("-inf"))
                dock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_results.setItem(row, 5, dock_item)
            # Composite score
            self.tbl_results.setItem(
                row, 6, self._num_item(hit.composite_score, fmt=".3f")
            )
            # Tier badge
            # N-code type guard: hit.tier from screening result
            tier_str = hit.tier if isinstance(hit.tier, str) else str(hit.tier) if hit.tier is not None else "-"
            tier_item = QTableWidgetItem(tier_str)
            tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = TIER_COLORS.get(tier_str, "#999999")
            tier_item.setForeground(QBrush(QColor(color)))
            tier_item.setFont(QFont(_QT_KR_FONT, 10, QFont.Weight.Bold))
            self.tbl_results.setItem(row, 7, tier_item)
            # PAINS warning
            n_alerts = hit.qed.n_alerts if hit.qed else 0
            pains_item = QTableWidgetItem(str(n_alerts) if n_alerts else "-")
            if n_alerts > 0:
                pains_item.setForeground(QBrush(QColor("#e74c3c")))
                pains_item.setFont(QFont(_QT_KR_FONT, 9, QFont.Weight.Bold))
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
        colors = [TIER_COLORS.get(h.tier if isinstance(h.tier, str) else str(h.tier) if h.tier is not None else "-", "#999999") for h in hits]

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

    # ========================= Tab 5: DrugBank 매칭 (M646_INTEGRATE) =========================
    # 학술 인용 (Rule NN): Wishart, D.S. et al. (2018) Nucleic Acids Res. 46(D1): D1074-D1082.
    #                    Knox, C. et al. (2024) Nucleic Acids Res. 52(D1): D1265-D1275.
    #                    Rogers, D.; Hahn, M. (2010) ECFP. J.Chem.Inf.Model. 50(5): 742-754.

    def _build_tab_drugbank(self):
        """DrugBank 로컬 데이터셋 Tanimoto 유사도 검색 탭."""
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # 데이터 가용성 표시 (Rule M: silent failure 차단)
        self.lbl_drugbank_status = QLabel()
        self.lbl_drugbank_status.setWordWrap(True)
        self.lbl_drugbank_status.setStyleSheet(
            "QLabel { padding: 8px; background-color: #f8f9fa; border: 1px solid #dee2e6; "
            "border-radius: 4px; font-size: 11px; }"
        )
        self._refresh_drugbank_status_label()
        vbox.addWidget(self.lbl_drugbank_status)

        # 학술 인용 안내 (Rule NN: 항상 표시 — 사용자 학습 정합성)
        lbl_citation = QLabel(
            "<i>참고: Wishart et al. NAR 2018;46:D1074 — DrugBank 5.0. "
            "Knox et al. NAR 2024;52:D1265 — DrugBank 6.0. "
            "Rogers&Hahn JCIM 2010;50:742 — ECFP4 fingerprint.</i>"
        )
        lbl_citation.setWordWrap(True)
        lbl_citation.setStyleSheet("color: #555; font-size: 9px; padding: 2px 8px;")
        vbox.addWidget(lbl_citation)

        lbl_boundary = QLabel(
            "DrugBank local data may be missing. Matches require local vocabulary CSV and open structures SDF; "
            "without them this tab cannot prove a DrugBank match."
        )
        lbl_boundary.setWordWrap(True)
        lbl_boundary.setStyleSheet(
            "QLabel { padding: 8px; background-color: #fff8e1; "
            "border: 1px solid #f9a825; border-radius: 4px; font-size: 11px; }"
        )
        vbox.addWidget(lbl_boundary)

        # 검색 폼
        grp_search = QGroupBox("Tanimoto 유사도 검색 (현재 표 행 또는 SMILES 입력)")
        form_layout = QVBoxLayout(grp_search)

        # SMILES 입력 라인
        smiles_row = QHBoxLayout()
        smiles_row.addWidget(QLabel("SMILES:"))
        self.txt_drugbank_smiles = QTextEdit()
        self.txt_drugbank_smiles.setMaximumHeight(50)
        self.txt_drugbank_smiles.setPlaceholderText(
            "예: CC(=O)Oc1ccccc1C(=O)O (Aspirin) — 빈 칸이면 결과 탭 첫 행 분자 사용"
        )
        smiles_row.addWidget(self.txt_drugbank_smiles)
        form_layout.addLayout(smiles_row)

        # 파라미터 (k, cutoff)
        param_row = QHBoxLayout()
        param_row.addWidget(QLabel("Top-k:"))
        self.slider_drugbank_k = QSlider(Qt.Orientation.Horizontal)
        self.slider_drugbank_k.setRange(1, 20)  # [MAGIC: 1-20] UI 표시 가능 한도
        self.slider_drugbank_k.setValue(5)  # [MAGIC: 5] 기본값
        self.lbl_drugbank_k = QLabel("5")
        self.slider_drugbank_k.valueChanged.connect(
            lambda v: self.lbl_drugbank_k.setText(str(v))
        )
        param_row.addWidget(self.slider_drugbank_k)
        param_row.addWidget(self.lbl_drugbank_k)

        param_row.addWidget(QLabel("  Tanimoto cutoff:"))
        self.slider_drugbank_cutoff = QSlider(Qt.Orientation.Horizontal)
        self.slider_drugbank_cutoff.setRange(0, 100)
        self.slider_drugbank_cutoff.setValue(40)  # [MAGIC: 0.40] ECFP4 표준 (Rogers&Hahn 2010)
        self.lbl_drugbank_cutoff = QLabel("0.40")
        self.slider_drugbank_cutoff.valueChanged.connect(
            lambda v: self.lbl_drugbank_cutoff.setText(f"{v / 100:.2f}")
        )
        param_row.addWidget(self.slider_drugbank_cutoff)
        param_row.addWidget(self.lbl_drugbank_cutoff)
        form_layout.addLayout(param_row)

        # 검색 버튼
        btn_row = QHBoxLayout()
        self.btn_drugbank_search = QPushButton("DrugBank 매칭 검색")
        self.btn_drugbank_search.setStyleSheet(
            "QPushButton { background-color: #16a085; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 4px; }"
        )
        self.btn_drugbank_search.clicked.connect(self._on_drugbank_search)
        btn_row.addWidget(self.btn_drugbank_search)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        vbox.addWidget(grp_search)

        # 결과 표
        grp_res = QGroupBox("매칭 결과 (Tanimoto Top-k)")
        res_layout = QVBoxLayout(grp_res)
        self.tbl_drugbank = QTableWidget()
        self.tbl_drugbank.setColumnCount(6)
        self.tbl_drugbank.setHorizontalHeaderLabels([
            "DrugBank ID", "Common Name", "유사도", "CAS", "InChI Key", "URL",
        ])
        self.tbl_drugbank.horizontalHeader().setStretchLastSection(True)
        self.tbl_drugbank.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tbl_drugbank.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        # 더블클릭 → 브라우저 (Rule M: 사용자 피드백)
        self.tbl_drugbank.doubleClicked.connect(self._on_drugbank_row_doubleclick)
        # 툴팁: Wishart 2018 인용 (Rule NN UI 명시)
        self.tbl_drugbank.setToolTip(
            "DrugBank 6.0 (Knox et al. NAR 2024;52:D1265). "
            "Tanimoto 유사도는 Morgan ECFP4 fingerprint 기반 (Rogers&Hahn JCIM 2010;50:742). "
            "DrugBank local data may be missing; local matches require CSV/SDF files. "
            "더블클릭하면 DrugBank 페이지를 엽니다."
        )
        res_layout.addWidget(self.tbl_drugbank)
        vbox.addWidget(grp_res)

        self.tabs.addTab(tab, "DrugBank")

    # ========================= Tab 6: ChEMBL (M646_LITE_PARITY) =========================
    def _build_tab_chembl(self):
        """ChEMBL 외부 API 검색 탭 — SMILES → 생물활성 데이터.

        학술 인용 (Rule NN — academic_integrity_check.py / FP-28 차단):
          Mendez, D. et al. (2019) ChEMBL: towards direct deposition of
            bioassay data. Nucleic Acids Res. 47(D1): D930-D940.
          Davies, M. et al. (2015) ChEMBL web services. NAR 43(W1): W612-W620.

        Rule M: silent failure 금지 — 모든 실패 logger.warning + UI 메시지.
        Rule N: 응답 dict/list 가드.
        Rule Y: 1:1 router 이식 — ext_live._chembl_get_molecule() 함수와 동일 URL.
        """
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # 학술 인용 안내 (Rule NN: 항상 표시)
        lbl_citation = QLabel(
            "<i>참고: Mendez et al. NAR 2019;47:D930 — ChEMBL bioactivity DB. "
            "Davies et al. NAR 2015;43:W612 — ChEMBL web services REST API.</i>"
        )
        lbl_citation.setWordWrap(True)
        lbl_citation.setStyleSheet("color: #555; font-size: 9px; padding: 2px 8px;")
        vbox.addWidget(lbl_citation)

        # 안내문 (FP-15 차단 — 외부 API 의존성 명시)
        lbl_info = QLabel(
            "<b>외부 API:</b> ChEMBL EBI (ebi.ac.uk/chembl). "
            "네트워크 연결 필수 — 미연결 시 SIMULATION_MODE 표시."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(
            "QLabel { padding: 8px; background-color: #f8f9fa; "
            "border: 1px solid #dee2e6; border-radius: 4px; font-size: 11px; }"
        )
        vbox.addWidget(lbl_info)

        # 검색 폼
        grp_search = QGroupBox("ChEMBL SMILES 검색 (현재 표 행 또는 SMILES 입력)")
        form_layout = QVBoxLayout(grp_search)

        # SMILES 입력 라인
        smiles_row = QHBoxLayout()
        smiles_row.addWidget(QLabel("SMILES:"))
        self.txt_chembl_smiles = QTextEdit()
        self.txt_chembl_smiles.setMaximumHeight(50)
        self.txt_chembl_smiles.setPlaceholderText(
            "예: CC(=O)Oc1ccccc1C(=O)O (Aspirin) — 빈 칸이면 결과 탭 첫 행 분자 사용"
        )
        smiles_row.addWidget(self.txt_chembl_smiles)
        form_layout.addLayout(smiles_row)

        # 검색 버튼
        btn_row = QHBoxLayout()
        self.btn_chembl_search = QPushButton("ChEMBL 외부 검색")
        self.btn_chembl_search.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 4px; }"
        )
        self.btn_chembl_search.clicked.connect(self._on_chembl_search)
        btn_row.addWidget(self.btn_chembl_search)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)
        vbox.addWidget(grp_search)

        # 결과 표
        grp_res = QGroupBox("ChEMBL 매칭 결과")
        res_layout = QVBoxLayout(grp_res)
        self.tbl_chembl = QTableWidget()
        self.tbl_chembl.setColumnCount(5)
        self.tbl_chembl.setHorizontalHeaderLabels([
            "ChEMBL ID", "Pref Name", "Max Phase", "Mol Formula", "URL",
        ])
        self.tbl_chembl.horizontalHeader().setStretchLastSection(True)
        self.tbl_chembl.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tbl_chembl.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        # 학술 인용 툴팁 (Rule NN UI 명시)
        self.tbl_chembl.setToolTip(
            "ChEMBL bioactivity DB (Mendez et al. NAR 2019;47:D930). "
            "Max Phase 4 = 시판 약물 / Phase 1-3 = 임상시험. "
            "더블클릭하면 ChEMBL 페이지를 엽니다."
        )
        self.tbl_chembl.doubleClicked.connect(self._on_chembl_row_doubleclick)
        res_layout.addWidget(self.tbl_chembl)
        vbox.addWidget(grp_res)

        # 상태 라벨 (Rule M: 명시적 피드백)
        self.lbl_chembl_status = QLabel("준비됨 — SMILES 입력 후 '검색' 버튼")
        self.lbl_chembl_status.setStyleSheet(
            "color: #555; font-size: 10px; padding: 4px 8px;"
        )
        vbox.addWidget(self.lbl_chembl_status)

        self.tabs.addTab(tab, "ChEMBL")

    def _on_chembl_search(self):
        """ChEMBL 외부 API 호출 — Mendez 2019 NAR 47:D930.

        Rule M: silent 금지. Rule N: 응답 dict/list 가드.
        Rule Y: 1:1 router 이식 — ext_live._chembl_get_molecule() URL 동일.
        """
        # 입력 SMILES (빈 칸이면 첫 결과 분자 사용)
        smi = self.txt_chembl_smiles.toPlainText().strip()
        if not smi and self._all_hits:  # Rule M: silent 금지
            smi = getattr(self._all_hits[0], "smiles", "") or ""
        if not smi:
            self.lbl_chembl_status.setText(
                "<span style='color:#e74c3c;'>SMILES 입력 또는 결과 탭에 분자 추가</span>"
            )
            QMessageBox.warning(
                self, "ChEMBL", "SMILES 가 비어 있습니다.\n결과 탭에 분자가 있으면 자동 사용합니다."
            )
            return

        self.lbl_chembl_status.setText(
            f"<i>ChEMBL 검색 중... ({smi[:40]})</i>"
        )
        self.btn_chembl_search.setEnabled(False)
        try:
            results = self._chembl_query(smi)
        finally:
            self.btn_chembl_search.setEnabled(True)

        # Rule N: 응답 list 가드
        if not isinstance(results, list):  # Rule N
            logger.warning("[ChEMBL] 예상치 못한 응답 타입 %s", type(results).__name__)
            results = []

        # _simulation_mode 키 체크 (Rule GG)
        sim_flag = False
        sim_reason = ""
        if results and isinstance(results[0], dict):
            sim_flag = bool(results[0].get("_simulation_mode", False))
            sim_reason = str(results[0].get("_reason", ""))
        if sim_flag:
            self.lbl_chembl_status.setText(
                f"<span style='color:#e67e22;'>"
                f"<b>SIMULATION_MODE</b> — {sim_reason}</span>"
            )
            self.tbl_chembl.setRowCount(0)
            return

        # 결과 표 채우기
        self.tbl_chembl.setRowCount(len(results))
        for i, item in enumerate(results):
            if not isinstance(item, dict):  # Rule N
                continue
            chembl_id = str(item.get("molecule_chembl_id", "?"))
            pref = str(item.get("pref_name") or "")
            max_phase = str(item.get("max_phase") or "")
            formula = "?"
            mol_props = item.get("molecule_properties")
            if isinstance(mol_props, dict):  # Rule N
                formula = str(mol_props.get("full_molformula", "") or "?")
            url = f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/"

            self.tbl_chembl.setItem(i, 0, QTableWidgetItem(chembl_id))
            self.tbl_chembl.setItem(i, 1, QTableWidgetItem(pref))
            self.tbl_chembl.setItem(i, 2, QTableWidgetItem(max_phase))
            self.tbl_chembl.setItem(i, 3, QTableWidgetItem(formula))
            self.tbl_chembl.setItem(i, 4, QTableWidgetItem(url))

        if not results:
            self.lbl_chembl_status.setText(
                f"<span style='color:#7f8c8d;'>결과 없음 — '{smi[:40]}' 매칭 ChEMBL 항목 0건</span>"
            )
        else:
            self.lbl_chembl_status.setText(
                f"<span style='color:#27ae60;'>"
                f"<b>{len(results)}건 매칭</b> — Mendez et al. NAR 2019;47:D930</span>"
            )

    def _chembl_query(self, smiles: str) -> list:
        """ChEMBL REST API 직접 호출 — ext_live._chembl_get_molecule() 와 1:1 동일.

        Rule M / Rule N / Rule Y 준수.
        """
        try:
            import requests as _requests
            import urllib.parse as _urlparse
        except ImportError as e:
            logger.warning("[ChEMBL] requests/urllib 미설치: %s", e)
            return [{
                "_simulation_mode": True,
                "_reason": "requests 라이브러리 없음 — 외부 API 호출 불가",
            }]

        if not isinstance(smiles, str) or not smiles.strip():  # Rule N
            return [{"_simulation_mode": True, "_reason": "SMILES 비어 있음"}]

        # ext_live.py 와 동일 URL — Rule Y 1:1 이식
        # [MAGIC: 30s] ChEMBL API 응답 시간 max
        encoded = _urlparse.quote(smiles.strip(), safe='')
        url = (
            f"https://www.ebi.ac.uk/chembl/api/data/molecule"
            f"?smiles={encoded}&format=json&limit=10"
        )
        try:
            resp = _requests.get(  # type: ignore[union-attr]
                url, headers={"User-Agent": "ChemGrid/M646_LITE_PARITY"}, timeout=30,
            )
        except _requests.exceptions.Timeout:  # type: ignore[union-attr]
            logger.warning("[ChEMBL] timeout @ %s", url[:80])
            return [{"_simulation_mode": True, "_reason": "ChEMBL API timeout (30s)"}]
        except Exception as e:
            logger.warning("[ChEMBL] 네트워크 오류 %s: %s", type(e).__name__, e)
            return [{"_simulation_mode": True,
                      "_reason": f"network: {type(e).__name__}: {e}"}]

        if not resp.ok:
            logger.warning("[ChEMBL] HTTP %d", resp.status_code)
            return [{"_simulation_mode": True,
                      "_reason": f"HTTP {resp.status_code}"}]
        try:
            data = resp.json()
        except Exception as e:
            logger.warning("[ChEMBL] JSON 파싱 실패: %s", e)
            return [{"_simulation_mode": True, "_reason": f"json: {e}"}]

        if not isinstance(data, dict):  # Rule N
            return []
        molecules = data.get("molecules", [])
        if not isinstance(molecules, list):  # Rule N
            return []
        # 가드: 각 항목 dict 인지
        return [m for m in molecules if isinstance(m, dict)]

    def _on_chembl_row_doubleclick(self, idx):
        """ChEMBL 행 더블클릭 → 브라우저 외부 열기 (Rule M: 명시적 피드백)."""
        row = idx.row()
        if row < 0:
            return
        item = self.tbl_chembl.item(row, 4)  # URL 열
        if item is None:
            return
        url = item.text().strip()
        if not url:
            return
        try:
            from PyQt6.QtCore import QUrl as _QUrl
            from PyQt6.QtGui import QDesktopServices as _QDS
            _QDS.openUrl(_QUrl(url))
        except Exception as e:
            logger.warning("[ChEMBL] URL 열기 실패: %s", e)

    def _refresh_drugbank_status_label(self):
        """DrugBank 데이터 가용성 라벨 갱신 (Rule M: 명시적 사용자 피드백)."""
        if not DRUGBANK_AVAILABLE:
            self.lbl_drugbank_status.setText(
                "<b style='color:#e74c3c;'>DrugBank 모듈 미가용</b> — RDKit 설치 또는 "
                "drugbank_local.py 임포트 실패. DrugBank local data may be missing. <i>SIMULATION_MODE</i>"
            )
            return
        try:
            status = drugbank_local.get_data_status()
        except Exception as e:  # Rule M
            logger.warning("DrugBank status 조회 실패: %s", e)
            self.lbl_drugbank_status.setText(
                f"<b style='color:#e74c3c;'>상태 조회 실패</b>: {e}"
            )
            return
        if not status.get("csv_exists") or not status.get("sdf_exists"):
            self.lbl_drugbank_status.setText(
                f"<b style='color:#e67e22;'>DrugBank 데이터 미설치</b><br>"
                f"data_root: <code>{status.get('data_root', '?')}</code><br>"
                f"CSV: {'있음' if status.get('csv_exists') else '<b style=\"color:#e74c3c\">없음</b>'} | "
                f"SDF: {'있음' if status.get('sdf_exists') else '<b style=\"color:#e74c3c\">없음</b>'}<br>"
                f"<b>DrugBank local data may be missing; no DrugBank match is proven until both files are present.</b><br>"
                f"<i>해결: drugbank.ca/release/latest 에서 vocabulary CSV + open structures SDF 다운로드 후 위 폴더에 복사.</i>"
            )
            return
        msg = (
            f"<b style='color:#27ae60;'>DrugBank 로컬 데이터 가용</b><br>"
            f"vocabulary: {status.get('vocabulary_count', 0):,} 약물"
        )
        if status.get("fp_index_built"):
            msg += f" | SDF 인덱스: {status.get('fp_index_count', 0):,} 분자 (Tanimoto 검색 가능)"
        else:
            msg += " | SDF 인덱스: <i>첫 검색 시 자동 빌드 (~수십 초)</i>"
        if status.get("build_error"):
            msg += f"<br><span style='color:#e67e22;'>경고: {status['build_error']}</span>"
        self.lbl_drugbank_status.setText(msg)

    def _on_drugbank_search(self):
        """DrugBank Tanimoto 매칭 실행 (Rule M: 명시적 에러 분기)."""
        if not DRUGBANK_AVAILABLE:
            QMessageBox.warning(
                self, "DrugBank",
                "DrugBank 로컬 모듈을 사용할 수 없습니다.\n"
                "RDKit 설치 또는 drugbank_local.py 임포트 실패."
            )
            return
        smiles = self.txt_drugbank_smiles.toPlainText().strip()
        if not smiles:
            # 결과 탭 첫 행 SMILES 자동 사용 (사용자 편의)
            if self._all_hits:
                first_hit = self._all_hits[0]
                if hasattr(first_hit, "compound") and hasattr(first_hit.compound, "smiles"):
                    smiles = first_hit.compound.smiles
            if not smiles and self._candidates:
                first_cand = self._candidates[0]
                if hasattr(first_cand, "smiles"):
                    smiles = first_cand.smiles
            if not smiles:
                QMessageBox.information(
                    self, "DrugBank",
                    "SMILES를 입력하거나 결과 탭에 먼저 분자를 추가하세요."
                )
                return
        k_val = self.slider_drugbank_k.value()
        cutoff_val = self.slider_drugbank_cutoff.value() / 100.0

        # 검색 실행 (큰 SDF 인덱스 빌드 첫 호출 시 수십 초 가능)
        self.btn_drugbank_search.setEnabled(False)
        self.lbl_drugbank_status.setText(
            "<b style='color:#3498db;'>DrugBank 검색 중...</b> (첫 호출은 SDF 인덱싱으로 수십 초 소요 가능)"
        )
        # repaint 강제 (Rule F: 사용자 환경 피드백)
        try:
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
        except Exception as e:  # Rule M: processEvents 실패 시 경고
            logger.warning("processEvents 실패 (무시): %s", e)
        try:
            results = drugbank_local.search_by_smiles(
                smiles, k=k_val, cutoff=cutoff_val)
        except Exception as e:  # Rule M
            logger.warning("DrugBank 검색 실패: %s", e)
            QMessageBox.warning(self, "DrugBank", f"검색 실패: {e}")
            self.btn_drugbank_search.setEnabled(True)
            self._refresh_drugbank_status_label()
            return

        # 결과 표 갱신
        self.tbl_drugbank.setRowCount(0)
        # Rule N: results가 list인지 검증
        if not isinstance(results, list):
            QMessageBox.warning(
                self, "DrugBank",
                f"비정상 응답: {type(results).__name__}")
            self.btn_drugbank_search.setEnabled(True)
            self._refresh_drugbank_status_label()
            return
        # 첫 항목이 _data_missing/_invalid_smiles 단일 dict 인지 확인
        if results and isinstance(results[0], dict) and results[0].get("_data_missing"):
            QMessageBox.warning(
                self, "DrugBank",
                f"데이터 부재: {results[0].get('_reason', 'DRUGBANK_DATA_MISSING')}"
            )
            self.btn_drugbank_search.setEnabled(True)
            self._refresh_drugbank_status_label()
            return
        if results and isinstance(results[0], dict) and results[0].get("_invalid_smiles"):
            QMessageBox.warning(
                self, "DrugBank",
                f"잘못된 SMILES: {results[0].get('_reason', '')}"
            )
            self.btn_drugbank_search.setEnabled(True)
            self._refresh_drugbank_status_label()
            return
        # 정상 결과 채우기
        self.tbl_drugbank.setRowCount(len(results))
        for row, item in enumerate(results):
            if not isinstance(item, dict):  # Rule N
                continue
            self.tbl_drugbank.setItem(row, 0, QTableWidgetItem(item.get("drugbank_id", "")))
            self.tbl_drugbank.setItem(row, 1, QTableWidgetItem(item.get("name", "")))
            sim_val = item.get("similarity", 0.0)
            sim_str = f"{sim_val:.3f}" if isinstance(sim_val, (int, float)) else str(sim_val)
            sim_item = QTableWidgetItem(sim_str)
            sim_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 색상: 0.7 이상 녹색, 0.4-0.7 주황, 그 외 회색
            if isinstance(sim_val, (int, float)):
                if sim_val >= 0.7:  # [MAGIC: 0.7] 강한 매칭 (ECFP4 표준)
                    sim_item.setForeground(QBrush(QColor("#27ae60")))
                    sim_item.setFont(QFont(_QT_KR_FONT, 10, QFont.Weight.Bold))
                elif sim_val >= 0.4:  # [MAGIC: 0.4] 의미있는 매칭
                    sim_item.setForeground(QBrush(QColor("#f39c12")))
            self.tbl_drugbank.setItem(row, 2, sim_item)
            self.tbl_drugbank.setItem(row, 3, QTableWidgetItem(item.get("cas", "")))
            self.tbl_drugbank.setItem(row, 4, QTableWidgetItem(item.get("inchikey", "")))
            self.tbl_drugbank.setItem(row, 5, QTableWidgetItem(item.get("drugbank_url", "")))
        self.tbl_drugbank.resizeColumnsToContents()

        if len(results) == 0:
            QMessageBox.information(
                self, "DrugBank",
                f"매칭 결과 없음 (cutoff={cutoff_val:.2f}). "
                f"cutoff를 낮춰 다시 시도하세요."
            )
        self.btn_drugbank_search.setEnabled(True)
        self._refresh_drugbank_status_label()

    def _on_drugbank_row_doubleclick(self, index):
        """DrugBank 행 더블클릭 → 브라우저로 이동 (Rule M 사용자 피드백)."""
        row = index.row()
        url_item = self.tbl_drugbank.item(row, 5)
        if url_item is None:
            return
        url = url_item.text().strip()
        if not url:
            return
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:  # Rule M
            logger.warning("DrugBank 브라우저 열기 실패: %s", e)
            QMessageBox.information(self, "DrugBank", f"수동으로 이동하세요: {url}")
