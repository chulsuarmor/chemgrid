# popup_admet.py (v1.0 - ADMET Drug-Likeness Analysis Popup)
"""
ChemGrid: ADMET 약물성 분석 팝업
- Tab 1: 분자 정보 (Molecule Info + 2D structure)
- Tab 2: Lipinski / 약물 규칙 (Drug Rules with PASS/FAIL badges)
- Tab 3: BBB / 대사 (BBB Permeability & Metabolic Stability)
- Tab 4: 레이더 차트 (Radar Chart for drug-likeness visualization)
"""

import math
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QTabWidget, QGroupBox, QFormLayout, QWidget, QScrollArea,
        QSizePolicy, QProgressBar, QTextEdit, QFrame, QGridLayout
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

        if self.profile.error:
            self._show_error(f"분석 오류: {self.profile.error}")
            return

        # Parse mol for 2D rendering
        if RDKIT_AVAILABLE:
            self._mol = Chem.MolFromSmiles(self.smiles)

        # Update all tabs
        self._update_tab_info()
        self._update_tab_rules()
        self._update_tab_bbb()
        self._update_tab_radar()

        self.btn_analyze.setText("분석 완료")
        self.btn_analyze.setEnabled(False)

    def _show_error(self, msg: str):
        """Display error text on the info tab."""
        self.lbl_formula.setText(f'<span style="color:{COLOR_FAIL}">{msg}</span>')

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
        except Exception:
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
            except Exception:
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
            grid.addWidget(QLabel(name), r, 0)
            grid.addWidget(QLabel(val), r, 1)
            grid.addWidget(QLabel(criteria), r, 2)
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
                vgrid.addWidget(QLabel(name), r, 0)
                vgrid.addWidget(QLabel(val), r, 1)
                vgrid.addWidget(QLabel(criteria), r, 2)
                badge = _make_badge("PASS" if passed else "FAIL", COLOR_PASS if passed else COLOR_FAIL)
                vgrid.addWidget(badge, r, 3)

            vlayout.addLayout(vgrid)
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
                ggrid.addWidget(QLabel(name), r, 0)
                ggrid.addWidget(QLabel(val), r, 1)
                ggrid.addWidget(QLabel(criteria), r, 2)
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
