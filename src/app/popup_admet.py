# popup_admet.py (v1.0 - ADMET Drug-Likeness Analysis Popup)
"""
ChemGrid: ADMET 약물성 분석 팝업
- Tab 1: 분자 정보 (Molecule Info + 2D structure)
- Tab 2: Lipinski / 약물 규칙 (Drug Rules with PASS/FAIL badges)
- Tab 3: BBB / 대사 (BBB Permeability & Metabolic Stability)
- Tab 4: 레이더 차트 (Radar Chart for drug-likeness visualization)
"""

import logging
import math
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QTabWidget, QGroupBox, QFormLayout, QWidget, QScrollArea,
        QSizePolicy, QProgressBar, QTextEdit, QFrame, QGridLayout,
        QLineEdit  # M646_W_MATPROJ_UI: formula 입력
    )
    from PyQt6.QtCore import Qt, QSize
    from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QLinearGradient
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    import numpy as np
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

try:
    from rdkit import Chem
    from rdkit.Chem import Draw, Descriptors, AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    from admet_predictor import (
        predict_admet, evaluate_veber_rules, evaluate_ghose_filter,
        ADMETProfile
    )
    ADMET_AVAILABLE = True
except ImportError:
    ADMET_AVAILABLE = False

# DrugBank 로컬 모듈 (M646_INTEGRATE)
# 학술 인용 (Rule NN):
#   Wishart, D.S. et al. (2018) Nucleic Acids Res. 46(D1): D1074-D1082.
#   Knox, C. et al. (2024) Nucleic Acids Res. 52(D1): D1265-D1275.
try:
    import drugbank_local
    DRUGBANK_AVAILABLE = True
except ImportError:
    DRUGBANK_AVAILABLE = False

# Materials Project (M646_W_MATPROJ_UI — FP-신규 P-MATPROJ-NO-UI 직격)
# popup_3d.fetch_materials_project_summary()는 함수 정의됐으나 popup UI 진입점 0건 (Q-N30 격분).
# 본 카드는 Tab 5에서 호출되는 helper를 popup_3d에서 import.
# 학술 인용 (Rule NN): Jain, A. et al. (2013) APL Materials 1: 011002.
try:
    from popup_3d import fetch_materials_project_summary
    MATERIALS_PROJECT_AVAILABLE = True
except ImportError as _e_matproj:  # Rule M
    logger.warning("[popup_admet] Materials Project helper 임포트 실패: %s", _e_matproj)
    MATERIALS_PROJECT_AVAILABLE = False

# ============================================================================
# COLOR CONSTANTS
# ============================================================================
COLOR_PASS = "#27ae60"
COLOR_FAIL = "#e74c3c"
COLOR_WARN = "#f39c12"
COLOR_BG_CARD = "#f8f9fa"
COLOR_BORDER = "#dee2e6"


# ============================================================================
# HELPER WIDGETS
# ============================================================================

def _make_badge(text: str, color: str) -> QLabel:
    """Create a colored PASS/FAIL/WARN badge label."""
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedWidth(70)
    lbl.setStyleSheet(
        f"background-color: {color}; color: white; font-weight: bold; "
        f"border-radius: 4px; padding: 2px 8px; font-size: 12px;"
    )
    return lbl


def _make_card(title: str) -> tuple:
    """Create a styled QGroupBox card. Returns (group_box, layout)."""
    group = QGroupBox(title)
    group.setStyleSheet(
        f"QGroupBox {{ "
        f"  background-color: {COLOR_BG_CARD}; "
        f"  border: 1px solid {COLOR_BORDER}; "
        f"  border-radius: 6px; "
        f"  margin-top: 12px; "
        f"  padding-top: 18px; "
        f"  font-weight: bold; "
        f"}} "
        f"QGroupBox::title {{ "
        f"  subcontrol-origin: margin; "
        f"  left: 10px; "
        f"  padding: 0 4px; "
        f"}}"
    )
    layout = QVBoxLayout(group)
    layout.setSpacing(6)
    return group, layout


def _score_color(score: float) -> str:
    """Return a hex color interpolated from red (0) to green (1)."""
    if score >= 0.7:
        return COLOR_PASS
    elif score >= 0.4:
        return COLOR_WARN
    return COLOR_FAIL


def _make_score_bar(score: float, parent_layout: QVBoxLayout, label_text: str = ""):
    """Add a horizontal color-gradient score bar (0-1) to the layout."""
    row = QHBoxLayout()
    if label_text:
        lbl = QLabel(label_text)
        lbl.setFixedWidth(160)
        row.addWidget(lbl)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(int(score * 100))
    bar.setTextVisible(True)
    bar.setFormat(f"{score:.2f}")
    color = _score_color(score)
    bar.setStyleSheet(
        f"QProgressBar {{ border: 1px solid {COLOR_BORDER}; border-radius: 4px; "
        f"  text-align: center; height: 20px; background: #eee; }} "
        f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}"
    )
    row.addWidget(bar, 1)
    parent_layout.addLayout(row)


# ============================================================================
# MAIN POPUP
# ============================================================================

class ADMETPopup(QDialog):
    """ADMET Drug-Likeness Analysis Dialog."""

    def __init__(self, smiles: str = "", mol_name: str = "", parent=None):
        super().__init__(parent)
        self.smiles = smiles
        self.mol_name = mol_name or "Unknown"
        self.profile: Optional[object] = None  # ADMETProfile
        self._mol = None  # RDKit Mol object

        self.setWindowTitle("ADMET 약물성 분석")
        self.resize(900, 700)
        self.setMinimumSize(700, 500)

        self._init_ui()

        # Auto-analyze if SMILES provided
        if self.smiles:
            self._run_analysis()

    # ----------------------------------------------------------------
    # UI INIT
    # ----------------------------------------------------------------

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Molecule Info
        self.tab_info = QWidget()
        self.tabs.addTab(self.tab_info, "분자 정보")
        self._build_tab_info()

        # Tab 2: Drug Rules
        self.tab_rules = QWidget()
        self.tabs.addTab(self.tab_rules, "Lipinski / 약물 규칙")
        self._build_tab_rules()

        # Tab 3: BBB & Metabolism
        self.tab_bbb = QWidget()
        self.tabs.addTab(self.tab_bbb, "BBB / 대사")
        self._build_tab_bbb()

        # Tab 4: Radar Chart
        self.tab_radar = QWidget()
        self.tabs.addTab(self.tab_radar, "레이더 차트")
        self._build_tab_radar()

        # Tab 5: Materials Project (M646_W_MATPROJ_UI — FP-신규 P-MATPROJ-NO-UI)
        # 사용자 격분 인용 (Q-N30): "orca마냥 연결했다고만 하고 제대로 경로 안짜놓는 경우 너무 많아"
        # popup_3d.fetch_materials_project_summary 함수 정의됐으나 popup UI 진입점 0건 → 본 탭으로 진입점 신설.
        self.tab_matproj = QWidget()
        self.tabs.addTab(self.tab_matproj, "Materials Project")
        self._build_tab_matproj()

        # [M841 DONE #170] Tab 6: hERG 채널 차단 예측
        # Cavero I. et al. Expert Opin Drug Safety 2014, 13(10):1373-1384
        self.tab_herg = QWidget()
        self.tabs.addTab(self.tab_herg, "hERG 위험")
        self._build_tab_herg()

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("닫기")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        main_layout.addLayout(btn_row)

    # ----------------------------------------------------------------
    # TAB 1: 분자 정보
    # ----------------------------------------------------------------

    def _build_tab_info(self):
        layout = QVBoxLayout(self.tab_info)

        # Header card
        header_group, header_layout = _make_card("분자 기본 정보")

        form = QFormLayout()
        self.lbl_name = QLabel(self.mol_name)
        self.lbl_name.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        form.addRow("분자 이름:", self.lbl_name)

        self.lbl_smiles = QLabel(self.smiles or "-")
        self.lbl_smiles.setWordWrap(True)
        self.lbl_smiles.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("SMILES:", self.lbl_smiles)

        self.lbl_formula = QLabel("-")
        form.addRow("분자식:", self.lbl_formula)

        header_layout.addLayout(form)
        layout.addWidget(header_group)

        # 2D structure image
        struct_group, struct_layout = _make_card("2D 구조")
        self.lbl_structure = QLabel("분석을 시작하면 2D 구조가 표시됩니다.")
        self.lbl_structure.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_structure.setMinimumHeight(250)
        self.lbl_structure.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        struct_layout.addWidget(self.lbl_structure)
        layout.addWidget(struct_group)

        # M646_INTEGRATE: DrugBank 매칭 카드
        # 학술 인용 (Rule NN, Tooltip):
        #   Wishart et al. NAR 2018;46:D1074 (DrugBank 5.0)
        #   Knox et al. NAR 2024;52:D1265 (DrugBank 6.0)
        #   Rogers&Hahn JCIM 2010;50:742 (ECFP4 Tanimoto)
        drugbank_group, drugbank_layout = _make_card("DrugBank 매칭 (Wishart 2018, Knox 2024)")
        self.lbl_drugbank_info = QLabel(
            "분석 시 DrugBank 6.0 로컬 데이터셋 (11,000+ 약물)에서 "
            "Tanimoto 유사도 Top-3 매칭 결과가 표시됩니다."
        )
        self.lbl_drugbank_info.setWordWrap(True)
        self.lbl_drugbank_info.setStyleSheet("color: #555; font-size: 10px;")
        # 툴팁: 학술 인용 의무 (Rule NN UI 명시)
        self.lbl_drugbank_info.setToolTip(
            "DrugBank 6.0 (Knox et al. NAR 2024;52:D1265). "
            "Tanimoto 유사도는 Morgan ECFP4 (Rogers&Hahn JCIM 2010;50:742, radius=2, nBits=2048)."
        )
        drugbank_layout.addWidget(self.lbl_drugbank_info)
        self.lbl_drugbank_results = QLabel("")  # 분석 후 채워짐
        self.lbl_drugbank_results.setWordWrap(True)
        self.lbl_drugbank_results.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.lbl_drugbank_results.setOpenExternalLinks(True)
        self.lbl_drugbank_results.setStyleSheet("font-size: 11px; padding: 6px;")
        drugbank_layout.addWidget(self.lbl_drugbank_results)
        layout.addWidget(drugbank_group)

        # Analyze button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_analyze = QPushButton("분석 시작")
        self.btn_analyze.setFixedSize(150, 36)
        self.btn_analyze.setStyleSheet(
            "QPushButton { background-color: #3498db; color: white; font-weight: bold; "
            "border-radius: 4px; font-size: 13px; } "
            "QPushButton:hover { background-color: #2980b9; }"
        )
        self.btn_analyze.clicked.connect(self._run_analysis)
        btn_row.addWidget(self.btn_analyze)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    # ----------------------------------------------------------------
    # TAB 2: Lipinski / 약물 규칙
    # ----------------------------------------------------------------

    def _build_tab_rules(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.rules_layout = QVBoxLayout(container)
        self.rules_layout.setSpacing(10)

        self.lbl_rules_placeholder = QLabel("분석 결과가 여기에 표시됩니다. '분자 정보' 탭에서 분석을 시작하세요.")
        self.lbl_rules_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rules_placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self.rules_layout.addWidget(self.lbl_rules_placeholder)
        self.rules_layout.addStretch()

        scroll.setWidget(container)
        tab_layout = QVBoxLayout(self.tab_rules)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    # ----------------------------------------------------------------
    # TAB 3: BBB / 대사
    # ----------------------------------------------------------------

    def _build_tab_bbb(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.bbb_layout = QVBoxLayout(container)
        self.bbb_layout.setSpacing(10)

        self.lbl_bbb_placeholder = QLabel("분석 결과가 여기에 표시됩니다. '분자 정보' 탭에서 분석을 시작하세요.")
        self.lbl_bbb_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_bbb_placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self.bbb_layout.addWidget(self.lbl_bbb_placeholder)
        self.bbb_layout.addStretch()

        scroll.setWidget(container)
        tab_layout = QVBoxLayout(self.tab_bbb)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    # ----------------------------------------------------------------
    # TAB 4: 레이더 차트
    # ----------------------------------------------------------------

    def _build_tab_radar(self):
        self.radar_layout = QVBoxLayout(self.tab_radar)

        self.lbl_radar_placeholder = QLabel("분석 결과가 여기에 표시됩니다. '분자 정보' 탭에서 분석을 시작하세요.")
        self.lbl_radar_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_radar_placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self.radar_layout.addWidget(self.lbl_radar_placeholder)
        self.radar_layout.addStretch()

    # ----------------------------------------------------------------
    # TAB 5: Materials Project (M646_W_MATPROJ_UI — FP-신규 P-MATPROJ-NO-UI 직격)
    # ----------------------------------------------------------------
    # 사용자 격분 인용 (Q-N30): "orca마냥 연결했다고만 하고 제대로 경로 안짜놓는 경우 너무 많아"
    # 학술 인용 (Rule NN): Jain, A. et al. (2013) APL Materials 1: 011002.
    #   Materials Project: A materials genome approach to accelerating materials innovation.
    # Rule S: clicked.connect — QPushButton.clicked 시그널은 PyQt6 표준, AttributeError 위험 0.
    # Rule N: 응답 dict/list isinstance 가드 (fetch_materials_project_summary 내부 + 본 메서드).
    # Rule M: silent fail 차단 — 빈 결과/네트워크 오류 모두 사용자 라벨 표시.
    # Rule GG: SIMULATION_MODE UI 명시 — API 키 부재 시 노랑 배너 의무.
    # ----------------------------------------------------------------

    def _build_tab_matproj(self):
        """Materials Project 탭 — formula → 무기 재료 (band_gap, density, space_group)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        # ── SIMULATION 배너 (Rule GG): API 키 유무에 따라 색상 분기 ──
        # 노랑 (#fff3cd / #856404) = 키 부재 (계산 불가)
        # 파랑 (#d1ecf1 / #0c5460) = 키 존재 (실제 API 호출)
        api_key_present = bool(
            os.environ.get("Materials_API_KEY") or os.environ.get("MATERIALS_API_KEY")
        )
        if api_key_present:
            banner_text = (
                "Materials Project API 활성 — Jain et al. APL Materials 2013;1:011002. "
                "실제 next-gen.materialsproject.org API 호출."
            )
            banner_bg, banner_fg, banner_border = "#d1ecf1", "#0c5460", "#bee5eb"
        else:
            banner_text = (
                "SIMULATION_MODE — .env Materials_API_KEY 부재. "
                "https://next-gen.materialsproject.org 에서 무료 키 발급 후 .env 등록 필요. "
                "현재 실제 결과 조회 불가 (Rule GG: 학생 학습 오염 차단)."
            )
            banner_bg, banner_fg, banner_border = "#fff3cd", "#856404", "#ffeeba"

        self.lbl_matproj_banner = QLabel(banner_text)
        self.lbl_matproj_banner.setWordWrap(True)
        self.lbl_matproj_banner.setStyleSheet(
            f"background-color: {banner_bg}; color: {banner_fg}; "
            f"border: 1px solid {banner_border}; "
            f"border-radius: 4px; padding: 8px; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(self.lbl_matproj_banner)

        # ── 입력 카드 ──
        in_group, in_layout = _make_card("화학식 (Formula) 입력")
        # 학술 인용 툴팁 (Rule NN UI 명시 의무)
        in_group.setToolTip(
            "Materials Project: Jain A et al. APL Materials 2013;1:011002. "
            "DOI: 10.1063/1.4812323. "
            "본 탭은 popup_3d.fetch_materials_project_summary()를 호출하여 "
            "next-gen.materialsproject.org Summary API에서 무기 재료의 "
            "band gap / density / space group / energy_above_hull 등을 조회."
        )

        in_row = QHBoxLayout()
        lbl_formula_in = QLabel("Formula:")
        lbl_formula_in.setFixedWidth(80)
        in_row.addWidget(lbl_formula_in)
        self.edit_matproj_formula = QLineEdit()
        # [M691_W_P2_MATPROJ_HINT] 사용자 격분 (234203 card14 item25):
        # "SMILES 입력지원 안해? 재료 후보에 아무것도 안뜨네 엔진 정합성 확인해봐"
        # Materials Project는 무기 재료 DB — 유기분자(C/H/N/O/S) 검색 시 0건이 정상.
        self.edit_matproj_formula.setPlaceholderText(
            "무기 재료 화학식 예: Si, NaCl, Fe2O3, TiO2 (유기분자 SMILES 자동 변환됨)"
        )
        # SMILES 기반 분자에서 화학식 자동 추출 (RDKit available 경우만)
        # [M683 FIX] 사용자 LV.14 item 25 — "ADMET Materials Project SMILES 미지원"
        # Materials Project = 무기 재료 DB (Si, NaCl, TiO2 등 무기 화합물 전용).
        # 유기 분자 화학식(C/H/N/O/S만)을 입력해도 결과 0건 → 사용자 혼란.
        # [M689 Fix item25] 유기 분자 감지 시 상태 레이블에 안내 메시지 표시 (Rule M 준수).
        # Materials Project = 무기 재료 DB (Si, NaCl, TiO2 등). 유기 분자 결과 0건 예상.
        # _matproj_organic_warning: str or "" — 이후 lbl_matproj_status 생성 후 setText 호출.
        _matproj_organic_warning = ""
        if RDKIT_AVAILABLE and self.smiles:
            mol = Chem.MolFromSmiles(self.smiles)  # Rule L: MolFromSmiles + None 체크
            if mol is not None:
                from rdkit.Chem import rdMolDescriptors
                _formula = rdMolDescriptors.CalcMolFormula(mol)
                self.edit_matproj_formula.setText(_formula)
                # [M683/M689] 유기 분자 감지: 원소가 C/H/N/O/S/P/F/Cl/Br/I만 있으면 유기 분자 경고
                _organic_only = {"C", "H", "N", "O", "S", "P", "F", "Cl", "Br", "I"}
                _mol_atoms = set(a.GetSymbol() for a in mol.GetAtoms())
                if _mol_atoms.issubset(_organic_only):
                    logger.warning(
                        "[popup_admet/matproj M689] 유기 분자(%s) 화학식=%s → "
                        "Materials Project 무기 재료 DB에서 결과 0건 예상.",
                        self.smiles[:40], _formula
                    )
                    # [M689] Rule M: silent warning 금지 — 사용자 레이블에 안내 저장
                    _matproj_organic_warning = (
                        f"주의: 현재 분자는 유기 화합물({_formula})입니다.\n"
                        "Materials Project는 무기 재료 데이터베이스(Si, NaCl, TiO2 등)이므로\n"
                        "유기 분자 검색 시 결과 0건이 예상됩니다.\n"
                        "무기 원소 화학식(예: Si, Fe2O3, TiO2)을 직접 입력하세요."
                    )
            else:
                logger.warning(
                    "[popup_admet/matproj] MolFromSmiles None for SMILES=%s",
                    self.smiles[:60])
        in_row.addWidget(self.edit_matproj_formula, 1)

        self.btn_matproj_search = QPushButton("Materials Project 검색")
        self.btn_matproj_search.setFixedSize(170, 32)
        self.btn_matproj_search.setStyleSheet(
            "QPushButton { background-color: #3498db; color: white; font-weight: bold; "
            "border-radius: 4px; font-size: 12px; } "
            "QPushButton:hover { background-color: #2980b9; }"
        )
        # Rule S: QPushButton.clicked는 PyQt6 표준 시그널 — AttributeError 위험 0.
        self.btn_matproj_search.clicked.connect(self._run_materials_project)
        in_row.addWidget(self.btn_matproj_search)
        in_layout.addLayout(in_row)
        layout.addWidget(in_group)

        # ── 결과 카드 ──
        out_group, out_layout = _make_card("재료 후보 (Top by stability)")
        # [M689] 유기 분자 경고가 있으면 표시, 없으면 기본 안내 문구
        _status_init = (
            _matproj_organic_warning
            if _matproj_organic_warning
            else "Formula 입력 후 'Materials Project 검색' 버튼을 눌러주세요."
        )
        self.lbl_matproj_status = QLabel(_status_init)
        _status_color = "#c0392b" if _matproj_organic_warning else "#888"  # 경고 시 적색
        self.lbl_matproj_status.setStyleSheet(
            f"color: {_status_color}; font-size: 11px; padding: 4px;"
        )
        out_layout.addWidget(self.lbl_matproj_status)

        self.lbl_matproj_results = QLabel("")
        self.lbl_matproj_results.setWordWrap(True)
        self.lbl_matproj_results.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.lbl_matproj_results.setOpenExternalLinks(True)
        self.lbl_matproj_results.setStyleSheet(
            "font-size: 11px; padding: 6px; background-color: white; "
            "border: 1px solid #ddd; border-radius: 3px;"
        )
        self.lbl_matproj_results.setMinimumHeight(120)
        out_layout.addWidget(self.lbl_matproj_results)
        layout.addWidget(out_group)

        # ── 학술 출처 카드 (Rule NN UI 표시) ──
        cite_group, cite_layout = _make_card("학술 출처 (Citation)")
        lbl_cite = QLabel(
            "<b>Jain, A. et al. (2013)</b> "
            "APL Materials <b>1</b>: 011002. "
            'DOI: <a href="https://doi.org/10.1063/1.4812323">10.1063/1.4812323</a><br>'
            "<i>Commentary: The Materials Project: A materials genome approach "
            "to accelerating materials innovation.</i>"
        )
        lbl_cite.setWordWrap(True)
        lbl_cite.setOpenExternalLinks(True)
        lbl_cite.setStyleSheet("font-size: 10px; color: #555;")
        cite_layout.addWidget(lbl_cite)
        layout.addWidget(cite_group)

        layout.addStretch()
        scroll.setWidget(container)
        tab_layout = QVBoxLayout(self.tab_matproj)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    def _run_materials_project(self):
        """버튼 클릭 슬롯 — Materials Project Summary API 호출 + 결과 표시.

        Rule M: 모든 실패 분기 사용자 피드백 (silent return 금지).
        Rule N: 응답 dict/list isinstance 가드.
        """
        formula = (self.edit_matproj_formula.text() or "").strip()
        if not formula:
            self.lbl_matproj_status.setText(
                f'<span style="color:{COLOR_FAIL}">Formula 비어있음 — 예: Si, NaCl, Fe2O3</span>'
            )
            self.lbl_matproj_results.setText("")
            return

        # [M683 FIX] 유기 분자 화학식 감지 → 사용자 안내 (Rule M: silent return 금지)
        # Materials Project는 무기 재료 DB. 유기 분자(C/H/N/O/S/P/할로겐)는 결과 0건.
        _organic_elements = {"C", "H", "N", "O", "S", "P", "F", "Cl", "Br", "I"}
        # 화학식에서 원소 기호 추출 (Hill 표기: C9H8O4 → {C, H, O})
        import re as _re
        _formula_elements = set(_re.findall(r"[A-Z][a-z]?", formula))
        if _formula_elements and _formula_elements.issubset(_organic_elements):
            self.lbl_matproj_status.setText(
                f'<span style="color:#e67e22"><b>주의 — 유기 분자 화학식 감지</b><br>'
                f'"{formula}"는 유기화합물(C/H/N/O/S 조합)입니다.<br>'
                f'Materials Project는 <b>무기 재료 DB</b>(Si, TiO2, NaCl 등 무기 화합물)이므로 '
                f'유기 분자 화학식으로 조회하면 결과 0건입니다.<br>'
                f'무기 재료 후보를 찾으려면 직접 무기 화학식을 입력하세요 (예: TiO2, Fe2O3).'
                f'</span>'
            )
            self.lbl_matproj_results.setText("")
            return

        if not MATERIALS_PROJECT_AVAILABLE:
            self.lbl_matproj_status.setText(
                f'<span style="color:{COLOR_FAIL}">Materials Project 모듈 미가용 '
                f'(popup_3d 임포트 실패)</span>'
            )
            self.lbl_matproj_results.setText("")
            return

        api_key_present = bool(
            os.environ.get("Materials_API_KEY") or os.environ.get("MATERIALS_API_KEY")
        )
        if not api_key_present:
            self.lbl_matproj_status.setText(
                f'<span style="color:{COLOR_WARN}">SIMULATION_MODE — '
                f'API 키 부재로 호출 차단. .env Materials_API_KEY 등록 필요</span>'
            )
            self.lbl_matproj_results.setText(
                '<span style="color:#888;">학생 학습 오염 차단 (Rule GG): '
                '실제 호출 결과 없이 mock 표시 금지.<br>'
                '<a href="https://next-gen.materialsproject.org/api">'
                'next-gen.materialsproject.org/api'
                '</a>에서 무료 키 발급.</span>'
            )
            return

        # [M764 A70-W1 F5-14 item25] 유기 분자 감지 → 경고 배너, 검색은 계속 진행
        # (Rule M: silent return 금지. 차단 X, 경고 배너만 표시)
        _organic_elems = {"C", "H", "N", "O", "S", "P", "F", "Cl", "Br", "I"}
        import re as _re
        _formula_elems = set(_re.findall(r"[A-Z][a-z]?", formula))
        _is_organic = bool(_formula_elems and _formula_elems.issubset(_organic_elems)
                           and "C" in _formula_elems)
        if _is_organic:
            # [M764] 경고 배너만 표시, 검색 계속 진행 (차단 안 함)
            self.lbl_matproj_status.setText(
                f'<span style="color:#e67e22"><b>주의 — 유기 분자 ({formula})</b><br>'
                f'Materials Project는 무기 재료 DB(Si, TiO2, NaCl 등)이므로 '
                f'유기 분자 조회 결과는 0건 예상. 무기 원소 화학식 입력 권장.<br>'
                f'계속 조회 중...</span>'
            )
            logger.warning("[M764/F5-14] 유기 분자(%s) Materials Project 조회 계속 진행 (차단 해제)",
                           formula[:40])
        else:
            self.lbl_matproj_status.setText(
                f'<span style="color:#3498db;">조회 중: {formula} ...</span>'
            )
        self.lbl_matproj_results.setText("")
        QApplication_processEvents = getattr(
            __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication,
            "processEvents", None)
        if callable(QApplication_processEvents):
            try:
                QApplication_processEvents()
            except Exception as e:  # Rule M
                logger.warning("[matproj] processEvents 실패: %s", e)

        try:
            records = fetch_materials_project_summary(formula, limit=10)
        except Exception as e:  # Rule M
            logger.warning("[matproj] fetch 호출 예외: %s", e)
            self.lbl_matproj_status.setText(
                f'<span style="color:{COLOR_FAIL}">호출 실패: {type(e).__name__}: {e}</span>'
            )
            return

        if records is None:
            self.lbl_matproj_status.setText(
                f'<span style="color:{COLOR_FAIL}">조회 실패 — '
                f'네트워크/API 오류. 로그 확인 (logger.warning [Materials Project])</span>'
            )
            return

        if not isinstance(records, list):  # Rule N
            self.lbl_matproj_status.setText(
                f'<span style="color:{COLOR_FAIL}">비정상 응답: '
                f'{type(records).__name__}</span>'
            )
            return

        if len(records) == 0:
            self.lbl_matproj_status.setText(
                f'<span style="color:#888;">매칭 결과 없음 for formula="{formula}". '
                f'Hill 표기 (예: NaCl, Fe2O3) 시도 권장</span>'
            )
            return

        # 결과 HTML 표 (Rule Q: 한국어 + 영문 병기)
        html_lines = [
            f"<b>{len(records)}개 후보 — {formula}</b><br>",
            '<table cellspacing="0" cellpadding="4" '
            'style="border-collapse:collapse;font-size:11px;">',
            '<tr style="background-color:#e9ecef;">'
            '<th style="border:1px solid #ccc;padding:4px;">Material ID</th>'
            '<th style="border:1px solid #ccc;padding:4px;">Formula</th>'
            '<th style="border:1px solid #ccc;padding:4px;">Density (g/cm³)</th>'
            '<th style="border:1px solid #ccc;padding:4px;">Band gap (eV)</th>'
            '<th style="border:1px solid #ccc;padding:4px;">Space group</th>'
            '<th style="border:1px solid #ccc;padding:4px;">E_hull (eV/atom)</th>'
            '<th style="border:1px solid #ccc;padding:4px;">Stable</th>'
            '</tr>',
        ]
        for rec in records[:10]:  # [MAGIC: 10] 표시 한도
            if not isinstance(rec, dict):  # Rule N
                continue
            mid = rec.get("material_id", "-")
            f_pretty = rec.get("formula_pretty", formula)
            density = rec.get("density")
            bg_val = rec.get("band_gap")
            sym = rec.get("symmetry")
            sg_label = "-"
            if isinstance(sym, dict):
                sg_label = str(sym.get("symbol") or sym.get("number") or "-")
            ehull = rec.get("energy_above_hull")
            is_stable = rec.get("is_stable")
            stable_str = "YES" if is_stable else "NO" if is_stable is False else "-"
            stable_color = (COLOR_PASS if is_stable
                            else (COLOR_WARN if is_stable is False else "#888"))
            density_s = f"{density:.3f}" if isinstance(density, (int, float)) else "-"
            bg_s = f"{bg_val:.3f}" if isinstance(bg_val, (int, float)) else "-"
            ehull_s = f"{ehull:.4f}" if isinstance(ehull, (int, float)) else "-"
            html_lines.append(
                f'<tr>'
                f'<td style="border:1px solid #ccc;padding:4px;">'
                f'<a href="https://next-gen.materialsproject.org/materials/{mid}">'
                f'{mid}</a></td>'
                f'<td style="border:1px solid #ccc;padding:4px;">{f_pretty}</td>'
                f'<td style="border:1px solid #ccc;padding:4px;">{density_s}</td>'
                f'<td style="border:1px solid #ccc;padding:4px;">{bg_s}</td>'
                f'<td style="border:1px solid #ccc;padding:4px;">{sg_label}</td>'
                f'<td style="border:1px solid #ccc;padding:4px;">{ehull_s}</td>'
                f'<td style="border:1px solid #ccc;padding:4px;color:{stable_color};'
                f'font-weight:bold;">{stable_str}</td>'
                f'</tr>'
            )
        html_lines.append("</table>")
        html_lines.append(
            '<br><span style="font-size:10px;color:#555;">'
            "출처: Jain A et al. APL Materials 2013;1:011002 — "
            "next-gen.materialsproject.org Summary API."
            "</span>"
        )
        self.lbl_matproj_results.setText("".join(html_lines))
        self.lbl_matproj_status.setText(
            f'<span style="color:{COLOR_PASS}">조회 성공: '
            f'{len(records)}개 후보 (formula="{formula}")</span>'
        )

    # ================================================================
    # ANALYSIS
    # ================================================================

    def _run_analysis(self):
        """Run ADMET analysis on the current SMILES."""
        if not ADMET_AVAILABLE:
            self._show_error("ADMET 모듈을 사용할 수 없습니다 (admet_predictor 임포트 실패).")
            return

        if not self.smiles:
            self._show_error("SMILES가 입력되지 않았습니다.")
            return

        self.profile = predict_admet(self.smiles, self.mol_name)

        if not isinstance(self.profile, object) or self.profile is None:
            logger.warning("predict_admet returned invalid profile for SMILES: %s", self.smiles)
            self._show_error("ADMET 프로파일 생성에 실패했습니다.")
            return

        if self.profile.error:
            self._show_error(f"분석 오류: {self.profile.error}")
            return

        # Parse mol for 2D rendering
        if RDKIT_AVAILABLE:
            self._mol = Chem.MolFromSmiles(self.smiles)
            if self._mol is None:
                logger.warning("Invalid SMILES for ADMET 2D rendering: %s", self.smiles)

        # Update all tabs
        self._update_tab_info()
        self._update_tab_rules()
        self._update_tab_bbb()
        self._update_tab_radar()
        # M646_INTEGRATE: DrugBank 매칭 실행 (Wishart 2018, Knox 2024)
        self._update_drugbank_panel()

        self.btn_analyze.setText("분석 완료")
        self.btn_analyze.setEnabled(False)

    def _update_drugbank_panel(self):
        """DrugBank Tanimoto Top-3 매칭 결과를 카드에 표시 (Rule M 사용자 피드백)."""
        if not DRUGBANK_AVAILABLE:
            self.lbl_drugbank_results.setText(
                f'<span style="color:{COLOR_FAIL}">DrugBank 모듈 미가용 — '
                f'drugbank_local 임포트 실패 (RDKit 또는 경로 문제)</span>'
            )
            return
        if not self.smiles:
            self.lbl_drugbank_results.setText(
                '<span style="color:#888;">SMILES 없음</span>')
            return
        try:
            results = drugbank_local.search_by_smiles(
                self.smiles, k=3, cutoff=0.4)  # [MAGIC: 3,0.4] Top-3 ECFP4 표준
        except Exception as e:  # Rule M
            logger.warning("[popup_admet] DrugBank 매칭 실패: %s", e)
            self.lbl_drugbank_results.setText(
                f'<span style="color:{COLOR_FAIL}">검색 실패: {e}</span>'
            )
            return
        if not isinstance(results, list):  # Rule N
            self.lbl_drugbank_results.setText(
                f'<span style="color:{COLOR_FAIL}">비정상 응답: {type(results).__name__}</span>'
            )
            return
        # _data_missing/_invalid_smiles 플래그 분기 (Rule M 명시 피드백)
        if results and isinstance(results[0], dict) and results[0].get("_data_missing"):
            self.lbl_drugbank_results.setText(
                f'<span style="color:{COLOR_WARN};">DrugBank 데이터 부재</span> — '
                f'{results[0].get("_reason", "DRUGBANK_DATA_MISSING")}'
            )
            return
        if results and isinstance(results[0], dict) and results[0].get("_invalid_smiles"):
            self.lbl_drugbank_results.setText(
                f'<span style="color:{COLOR_FAIL}">잘못된 SMILES</span>'
            )
            return
        if not results:
            self.lbl_drugbank_results.setText(
                '<span style="color:#888;">매칭 결과 없음 (cutoff 0.4 이상). '
                'cutoff를 낮추려면 신약 스크리닝 팝업 → DrugBank 탭을 사용하세요.</span>'
            )
            return
        # Top-3 HTML 표 (Rule Q 한국어 + 영문 병기)
        html_lines = ["<b>Top-3 Tanimoto 매칭 (DrugBank 6.0):</b><br>"]
        for i, item in enumerate(results, start=1):
            if not isinstance(item, dict):  # Rule N
                continue
            sim = item.get("similarity", 0.0)
            sim_color = "#27ae60" if isinstance(sim, (int, float)) and sim >= 0.7 else "#f39c12"
            url = item.get("drugbank_url", "")
            name = item.get("name", "(이름 없음)")
            db_id = item.get("drugbank_id", "")
            html_lines.append(
                f'{i}. <b>{name}</b> '
                f'[<a href="{url}">{db_id}</a>] '
                f'— Tanimoto <span style="color:{sim_color};font-weight:bold">{sim:.3f}</span>'
            )
        self.lbl_drugbank_results.setText("<br>".join(html_lines))

    def _show_error(self, msg: str):
        """Display error text on the info tab."""
        self.lbl_formula.setText(f'<span style="color:{COLOR_FAIL}">{msg}</span>')

    # ----------------------------------------------------------------
    # TAB 6: hERG 채널 차단 예측 (M841 DONE #170)
    # Cavero I. et al. Expert Opin Drug Safety 2014, 13(10):1373-1384
    # ----------------------------------------------------------------

    def _build_tab_herg(self):
        """hERG 채널 차단 위험 예측 탭.

        간략 경험적 모델 (Cavero 2014 기준):
            고위험: LogP > 3 AND 염기성 N 존재 AND TPSA < 75 Å²
            중위험: 위 기준 2가지 해당
            저위험: 0~1가지 해당
        Rule GG: "(경험적 추정 — 전문 예측기 권장)" 배너 의무.
        """
        layout = QVBoxLayout(self.tab_herg)
        layout.setSpacing(8)

        # Rule GG SIMULATION_MODE 배너
        banner = QLabel(
            "SIMULATION_MODE — hERG 예측: 경험적 추정 모델 (Cavero 2014). "
            "LogP/TPSA/염기성N 기준 간략 분류. 전문 예측기(hERG DB / DeepHIT) 권장. "
            "학생 학습 오염 차단 목적 표시."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            "background:#fff3cd; color:#856404; padding:6px; "
            "border:1px solid #ffeeba; border-radius:4px; font-size:10px;"
        )
        layout.addWidget(banner)

        # hERG 위험 표시 라벨
        herg_card = QGroupBox(
            "hERG 채널 차단 위험 추정 (Cavero 2014 Expert Opin Drug Safety)"
        ) if hasattr(__builtins__, '__import__') else None
        try:
            from PyQt6.QtWidgets import QGroupBox
            herg_group = QGroupBox(
                "hERG 채널 차단 위험 추정 (Cavero 2014 Expert Opin Drug Safety 13:1373)"
            )
        except Exception:
            herg_group = None

        grp_layout = QVBoxLayout()

        self.lbl_herg_risk = QLabel("분자 로드 후 표시됩니다.")
        self.lbl_herg_risk.setStyleSheet(
            "font-size: 12pt; font-weight: bold; padding: 10px;"
        )
        self.lbl_herg_risk.setWordWrap(True)
        grp_layout.addWidget(self.lbl_herg_risk)

        self.lbl_herg_detail = QLabel("")
        self.lbl_herg_detail.setStyleSheet("font-size: 9pt; color: #555; padding: 4px;")
        self.lbl_herg_detail.setWordWrap(True)
        grp_layout.addWidget(self.lbl_herg_detail)

        try:
            herg_group.setLayout(grp_layout)
            layout.addWidget(herg_group)
        except Exception:
            for i in range(grp_layout.count()):
                item = grp_layout.itemAt(i)
                if item and item.widget():
                    layout.addWidget(item.widget())

        layout.addStretch()

    def _estimate_herg_risk(self, smiles: str) -> dict:
        """hERG 채널 차단 위험 경험적 추정.

        기준 (Cavero 2014):
            고위험: LogP > 3.0 AND 염기성N(지방족 아민) AND TPSA < 75 Å²
            중위험: 기준 2가지 충족
            저위험: 0~1가지 충족
        """
        result = {"risk": "알 수 없음", "criteria": [], "logp": None, "tpsa": None, "basic_n": False}
        if not isinstance(smiles, str) or not smiles.strip():
            logger.warning("_estimate_herg_risk: invalid SMILES type=%s", type(smiles).__name__)
            return result
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, Crippen
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning("_estimate_herg_risk: MolFromSmiles failed SMILES=%s", smiles)
                return result
            logp = Crippen.MolLogP(mol)
            tpsa = Descriptors.TPSA(mol)
            # 염기성 지방족 아민 SMARTS
            _ali_amine = Chem.MolFromSmarts("[NX3;H1,H2;!$(N-C=O);!$([nX3])]")
            basic_n = (_ali_amine is not None and mol.HasSubstructMatch(_ali_amine))
            result["logp"] = round(logp, 2)
            result["tpsa"] = round(tpsa, 1)
            result["basic_n"] = basic_n
            # 위험 기준 카운트
            criteria = []
            if logp > 3.0:   # [MAGIC:3.0] Cavero 2014 hERG LogP 임계값
                criteria.append(f"LogP = {logp:.2f} > 3.0 (친유성 높음)")
            if basic_n:
                criteria.append("염기성 지방족 아민 검출 (N-H)")
            if tpsa < 75.0:  # [MAGIC:75.0] Cavero 2014 TPSA 임계값 Å²
                criteria.append(f"TPSA = {tpsa:.1f} < 75 Å² (세포막 투과 높음)")
            result["criteria"] = criteria
            n_risk = len(criteria)
            if n_risk >= 3:
                result["risk"] = "고위험 (HIGH)"
            elif n_risk == 2:
                result["risk"] = "중위험 (MEDIUM)"
            else:
                result["risk"] = "저위험 (LOW)"
        except Exception as e:
            logger.warning("_estimate_herg_risk: 계산 실패 (%s): %s", smiles[:30], e)
        return result

    # ----------------------------------------------------------------
    # UPDATE TAB 1
    # ----------------------------------------------------------------

    def _update_tab_info(self):
        p = self.profile
        self.lbl_name.setText(p.mol_name or "Unknown")
        self.lbl_smiles.setText(p.smiles)

        # Molecular formula from RDKit
        if RDKIT_AVAILABLE and self._mol is not None:
            from rdkit.Chem import rdMolDescriptors
            formula = rdMolDescriptors.CalcMolFormula(self._mol)
            self.lbl_formula.setText(formula)
        else:
            self.lbl_formula.setText("-")

        # 2D structure image
        self._render_2d_structure()

    def _render_2d_structure(self):
        """Render 2D molecular structure using RDKit."""
        if not RDKIT_AVAILABLE or self._mol is None:
            self.lbl_structure.setText("RDKit을 사용할 수 없어 2D 구조를 표시할 수 없습니다.")
            return

        try:
            from rdkit.Chem.Draw import MolToQPixmap
            pixmap = MolToQPixmap(self._mol, size=(400, 300))
            self.lbl_structure.setPixmap(pixmap)
        except Exception as e:
            logger.warning("MolToQPixmap failed, trying PIL fallback: %s", e)
            # Fallback: try PIL-based rendering
            try:
                import io
                from PIL import Image as PILImage
                img = Draw.MolToImage(self._mol, size=(400, 300))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                pixmap = QPixmap()
                pixmap.loadFromData(buf.read())
                self.lbl_structure.setPixmap(pixmap)
            except Exception as e2:
                logger.warning("PIL 2D rendering also failed: %s", e2)
                self.lbl_structure.setText("2D 구조 렌더링 실패")

    # ----------------------------------------------------------------
    # UPDATE TAB 2: Drug Rules
    # ----------------------------------------------------------------

    def _update_tab_rules(self):
        p = self.profile
        layout = self.rules_layout

        # Clear placeholder
        self.lbl_rules_placeholder.hide()

        # Remove old stretch
        while layout.count() > 1:
            item = layout.takeAt(layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()

        # --- Lipinski Rule of Five ---
        lip = p.lipinski
        card, clayout = _make_card("Lipinski Rule of Five")

        grid = QGridLayout()
        grid.setSpacing(8)

        headers = ["속성", "값", "기준", "결과"]
        for i, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            grid.addWidget(lbl, 0, i)

        rows = [
            ("분자량 (MW)", f"{lip.mw:.1f}", "≤ 500", lip.mw <= 500),
            ("LogP", f"{lip.logp:.2f}", "≤ 5", lip.logp <= 5),
            ("수소결합 공여체 (HBD)", str(lip.hbd), "≤ 5", lip.hbd <= 5),
            ("수소결합 수용체 (HBA)", str(lip.hba), "≤ 10", lip.hba <= 10),
        ]

        for r, (name, val, criteria, passed) in enumerate(rows, start=1):
            lbl_name = QLabel(name)
            lbl_val = QLabel(val)
            lbl_crit = QLabel(criteria)
            # Lipinski Ro5: highlight violating value cells in red + bold
            if not passed:
                _fail_style = f"color: {COLOR_FAIL}; font-weight: bold;"
                lbl_name.setStyleSheet(_fail_style)
                lbl_val.setStyleSheet(_fail_style)
                lbl_crit.setStyleSheet(_fail_style)
            grid.addWidget(lbl_name, r, 0)
            grid.addWidget(lbl_val, r, 1)
            grid.addWidget(lbl_crit, r, 2)
            badge = _make_badge("PASS" if passed else "FAIL", COLOR_PASS if passed else COLOR_FAIL)
            grid.addWidget(badge, r, 3)

        clayout.addLayout(grid)

        overall_lip = QLabel(
            f"  전체: {'PASS' if lip.passes else 'FAIL'} (위반 {lip.violations}개, 허용 ≤ 1)"
        )
        overall_lip.setStyleSheet(
            f"font-weight: bold; color: {COLOR_PASS if lip.passes else COLOR_FAIL}; "
            f"font-size: 13px; padding: 4px;"
        )
        clayout.addWidget(overall_lip)

        # M647-W4 USR-LV4-06 직격: "화학적 특성 줄글만 / 형식 부정확"
        # 학술 인용 (Rule NN) — Lipinski 학술 양식 표에 표준 인용 추가
        cite_lip = QLabel(
            "참고 (Rule NN): Lipinski CA et al. Adv Drug Deliv Rev 1997;23:3-25. "
            "(Rule of Five — 경구 흡수 약물 후보 4가지 기준)"
        )
        cite_lip.setStyleSheet(
            "font-size: 9pt; color: #666; padding: 4px 6px; "
            "background: #f8f9fa; border-left: 3px solid #1976D2; "
            "border-radius: 3px; margin-top: 4px;"
        )
        cite_lip.setWordWrap(True)
        clayout.addWidget(cite_lip)
        layout.addWidget(card)

        # --- Veber Rules ---
        if RDKIT_AVAILABLE and self._mol is not None:
            veber = evaluate_veber_rules(self._mol)
            vcard, vlayout = _make_card("Veber Rules (경구 생체이용률)")

            vgrid = QGridLayout()
            vgrid.setSpacing(8)
            for i, h in enumerate(headers):
                lbl = QLabel(h)
                lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                vgrid.addWidget(lbl, 0, i)

            vrows = [
                ("TPSA", f"{veber['tpsa']:.1f}", "≤ 140", veber['tpsa'] <= 140),
                ("회전 가능 결합", str(veber['rotatable_bonds']), "≤ 10", veber['rotatable_bonds'] <= 10),
            ]
            for r, (name, val, criteria, passed) in enumerate(vrows, start=1):
                lbl_name = QLabel(name)
                lbl_val = QLabel(val)
                lbl_crit = QLabel(criteria)
                if not passed:
                    _fail_style = f"color: {COLOR_FAIL}; font-weight: bold;"
                    lbl_name.setStyleSheet(_fail_style)
                    lbl_val.setStyleSheet(_fail_style)
                    lbl_crit.setStyleSheet(_fail_style)
                vgrid.addWidget(lbl_name, r, 0)
                vgrid.addWidget(lbl_val, r, 1)
                vgrid.addWidget(lbl_crit, r, 2)
                badge = _make_badge("PASS" if passed else "FAIL", COLOR_PASS if passed else COLOR_FAIL)
                vgrid.addWidget(badge, r, 3)

            vlayout.addLayout(vgrid)
            # M647-W4 USR-LV4-06: Veber Rules 학술 인용 추가 (Rule NN)
            cite_veber = QLabel(
                "참고 (Rule NN): Veber DF et al. J Med Chem 2002;45:2615-2623. "
                "(Veber Rules — 경구 생체이용률 향상 기준: TPSA ≤ 140 Å², "
                "회전결합 ≤ 10)"
            )
            cite_veber.setStyleSheet(
                "font-size: 9pt; color: #666; padding: 4px 6px; "
                "background: #f8f9fa; border-left: 3px solid #388E3C; "
                "border-radius: 3px; margin-top: 4px;"
            )
            cite_veber.setWordWrap(True)
            vlayout.addWidget(cite_veber)
            overall_v = QLabel(
                f"  전체: {'PASS' if veber['passes'] else 'FAIL'} (위반 {veber['violations']}개)"
            )
            overall_v.setStyleSheet(
                f"font-weight: bold; color: {COLOR_PASS if veber['passes'] else COLOR_FAIL}; font-size: 13px;"
            )
            vlayout.addWidget(overall_v)
            layout.addWidget(vcard)

        # --- Ghose Filter ---
        if RDKIT_AVAILABLE and self._mol is not None:
            ghose = evaluate_ghose_filter(self._mol)
            gcard, glayout = _make_card("Ghose Filter")

            ggrid = QGridLayout()
            ggrid.setSpacing(8)
            for i, h in enumerate(headers):
                lbl = QLabel(h)
                lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                ggrid.addWidget(lbl, 0, i)

            grows = [
                ("분자량 (MW)", f"{ghose['mw']:.1f}", "160 - 480", 160 <= ghose['mw'] <= 480),
                ("LogP", f"{ghose['logp']:.2f}", "-0.4 - 5.6", -0.4 <= ghose['logp'] <= 5.6),
                ("몰 굴절률 (MR)", f"{ghose['molar_refractivity']:.1f}", "40 - 130",
                 40 <= ghose['molar_refractivity'] <= 130),
                ("원자 수", str(ghose['n_atoms']), "20 - 70", 20 <= ghose['n_atoms'] <= 70),
            ]
            for r, (name, val, criteria, passed) in enumerate(grows, start=1):
                lbl_name = QLabel(name)
                lbl_val = QLabel(val)
                lbl_crit = QLabel(criteria)
                if not passed:
                    _fail_style = f"color: {COLOR_FAIL}; font-weight: bold;"
                    lbl_name.setStyleSheet(_fail_style)
                    lbl_val.setStyleSheet(_fail_style)
                    lbl_crit.setStyleSheet(_fail_style)
                ggrid.addWidget(lbl_name, r, 0)
                ggrid.addWidget(lbl_val, r, 1)
                ggrid.addWidget(lbl_crit, r, 2)
                badge = _make_badge("PASS" if passed else "FAIL", COLOR_PASS if passed else COLOR_FAIL)
                ggrid.addWidget(badge, r, 3)

            glayout.addLayout(ggrid)
            overall_g = QLabel(
                f"  전체: {'PASS' if ghose['passes'] else 'FAIL'} (위반 {ghose['violations']}개)"
            )
            overall_g.setStyleSheet(
                f"font-weight: bold; color: {COLOR_PASS if ghose['passes'] else COLOR_FAIL}; font-size: 13px;"
            )
            glayout.addWidget(overall_g)
            layout.addWidget(gcard)

        # --- Overall Drug-Likeness Score ---
        score_card, score_layout = _make_card("종합 약물 유사성 점수")

        # QED (Quantitative Estimate of Drug-likeness) — Bickerton et al. 2012
        qed_val = getattr(p, 'qed_score', 0.0)
        if not isinstance(qed_val, (int, float)):
            qed_val = 0.0
        _make_score_bar(qed_val, score_layout, "QED 점수:")

        _make_score_bar(p.drug_likeness_score, score_layout, "Drug-Likeness:")

        # Oral bioavailability label
        ba_map = {
            "likely": ("경구 생체이용률: 높음 (Likely)", COLOR_PASS),
            "moderate": ("경구 생체이용률: 보통 (Moderate)", COLOR_WARN),
            "unlikely": ("경구 생체이용률: 낮음 (Unlikely)", COLOR_FAIL),
        }
        ba_text, ba_color = ba_map.get(p.oral_bioavailability, ("경구 생체이용률: -", "#888"))
        lbl_ba = QLabel(ba_text)
        lbl_ba.setStyleSheet(f"font-weight: bold; color: {ba_color}; font-size: 13px; padding: 4px;")
        score_layout.addWidget(lbl_ba)

        # Overall assessment
        lbl_assess = QLabel(p.overall_assessment)
        lbl_assess.setStyleSheet("font-style: italic; padding: 2px 4px; color: #555;")
        score_layout.addWidget(lbl_assess)

        layout.addWidget(score_card)
        layout.addStretch()

    # ----------------------------------------------------------------
    # UPDATE TAB 3: BBB / 대사
    # ----------------------------------------------------------------

    def _update_tab_bbb(self):
        p = self.profile
        layout = self.bbb_layout

        self.lbl_bbb_placeholder.hide()

        while layout.count() > 1:
            item = layout.takeAt(layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()

        # --- BBB Permeability ---
        bbb = p.bbb
        card, clayout = _make_card("혈액-뇌 장벽 (BBB) 투과성")

        _make_score_bar(bbb.score, clayout, "BBB 점수:")

        cls_map = {
            "BBB+": ("투과 가능 (BBB+)", COLOR_PASS),
            "uncertain": ("불확실 (Uncertain)", COLOR_WARN),
            "BBB-": ("투과 불가 (BBB-)", COLOR_FAIL),
        }
        # Rule N: isinstance guard for cls_map
        if not isinstance(cls_map, dict): cls_map = {}
        cls_text, cls_color = cls_map.get(bbb.classification, ("-", "#888"))
        lbl_cls = QLabel(f"분류: {cls_text}")
        lbl_cls.setStyleSheet(f"font-weight: bold; color: {cls_color}; font-size: 13px; padding: 4px;")
        clayout.addWidget(lbl_cls)

        # Factors detail
        if bbb.factors:
            factors_group, flayout = _make_card("BBB 영향 인자")
            for key, desc in bbb.factors.items():
                flayout.addWidget(QLabel(f"  {key}: {desc}"))
            clayout.addWidget(factors_group)

        layout.addWidget(card)

        # --- Metabolic Stability ---
        met = p.metabolic_stability
        mcard, mlayout = _make_card("대사 안정성")

        _make_score_bar(met.score, mlayout, "안정성 점수:")

        met_cls_map = {
            "high": ("높음 (High)", COLOR_PASS),
            "moderate": ("보통 (Moderate)", COLOR_WARN),
            "low": ("낮음 (Low)", COLOR_FAIL),
        }
        # Rule N: isinstance guard for met_cls_map
        if not isinstance(met_cls_map, dict): met_cls_map = {}
        met_text, met_color = met_cls_map.get(met.classification, ("-", "#888"))
        lbl_met = QLabel(f"분류: {met_text}")
        lbl_met.setStyleSheet(f"font-weight: bold; color: {met_color}; font-size: 13px; padding: 4px;")
        mlayout.addWidget(lbl_met)

        mlayout.addWidget(QLabel(f"  대사 취약점 수: {len(met.metabolic_soft_spots)}"))

        # Soft spots detail list
        if met.alerts:
            spots_group, slayout = _make_card("감지된 대사 취약점 (Metabolic Soft Spots)")
            for i, alert_text in enumerate(met.alerts, 1):
                slayout.addWidget(QLabel(f"  {i}. {alert_text}"))
            mlayout.addWidget(spots_group)

        layout.addWidget(mcard)

        # --- Warnings ---
        if p.warnings:
            wcard, wlayout = _make_card("경고 사항")
            for w in p.warnings:
                wlbl = QLabel(f"  ⚠ {w}")
                wlbl.setStyleSheet(f"color: {COLOR_WARN}; padding: 2px;")
                wlayout.addWidget(wlbl)
            layout.addWidget(wcard)

        layout.addStretch()

    # ----------------------------------------------------------------
    # UPDATE TAB 4: 레이더 차트
    # ----------------------------------------------------------------

    def _update_tab_radar(self):
        p = self.profile
        layout = self.radar_layout

        self.lbl_radar_placeholder.hide()

        # Remove old stretch / widgets
        while layout.count() > 1:
            item = layout.takeAt(layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()

        if not MATPLOTLIB_AVAILABLE:
            fallback = QLabel("matplotlib을 사용할 수 없어 레이더 차트를 표시할 수 없습니다.")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            layout.addWidget(fallback)
            return

        # Radar chart data
        # 6 axes: MW, LogP, HBD, HBA, TPSA, RotatableBonds
        # Normalize each to 0-1 based on drug-likeness thresholds
        lip = p.lipinski
        categories = ["MW", "LogP", "HBD", "HBA", "TPSA", "회전결합"]

        # Ideal max thresholds for normalization
        thresholds = [500.0, 5.0, 5.0, 10.0, 140.0, 10.0]
        actual = [lip.mw, lip.logp, float(lip.hbd), float(lip.hba), p.tpsa, float(p.n_rotatable_bonds)]

        # Normalize: clamp to [0, 1] (value / threshold)
        normalized = []
        for val, thr in zip(actual, thresholds):
            if thr == 0:
                normalized.append(0.0)
            else:
                normalized.append(min(1.0, max(0.0, val / thr)))

        # Ideal drug range (normalized) - within threshold = 1.0 is the limit
        ideal = [1.0] * 6  # The threshold boundary

        N = len(categories)
        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles += angles[:1]  # close the polygon

        normalized_closed = normalized + [normalized[0]]
        ideal_closed = ideal + [ideal[0]]

        fig = Figure(figsize=(6, 5), dpi=100)
        fig.patch.set_facecolor("#f8f9fa")
        ax = fig.add_subplot(111, polar=True)

        # Draw ideal range
        ax.fill(angles, ideal_closed, alpha=0.15, color="#3498db", label="허용 범위")
        ax.plot(angles, ideal_closed, linewidth=1.5, linestyle="--", color="#3498db", alpha=0.6)

        # Draw actual values
        ax.fill(angles, normalized_closed, alpha=0.3, color="#e74c3c")
        ax.plot(angles, normalized_closed, linewidth=2, color="#e74c3c", marker="o",
                markersize=5, label="실제 값")

        # Axis labels
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=10, fontweight="bold")
        ax.set_ylim(0, 1.3)
        ax.set_yticks([0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=8, color="#888")

        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
        ax.set_title("약물 유사성 레이더 차트", fontsize=13, fontweight="bold", pad=20)

        fig.tight_layout()

        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        canvas.setMinimumHeight(350)
        layout.addWidget(canvas, 1)

        # Annotation below chart
        note = QLabel(
            "파란 점선: 약물 유사성 허용 범위 (Lipinski/Veber 기준)  |  "
            "빨간 영역: 실제 분자 값 (정규화)"
        )
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        layout.addWidget(note)
