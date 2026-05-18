# popup_alphafold.py (v2.0 - 6단계 학생 경험 흐름 + PDBe Mol* + DryLab 학술지 양식)
"""
ChemGrid: AlphaFold 신약개발 통합 대시보드 — M463 W_ALPHAFOLD_STUDENT_FLOW

6단계 학생 경험 흐름:
  Tab 1: 단계 1 수용체 선택  — 드롭다운(COX-2/EGFR/NMDA/4PE5), UniProt ID 표시
  Tab 2: 단계 2 알파폴드 미리보기 — 외부 AlphaFold DB 링크 (M460 보존)
  Tab 3: 단계 3 PDB 계산    — AlphaFold API → 잔기/pLDDT/결합부위 추출
  Tab 4: 단계 4 결합 데이터 — pLDDT 차트 + 잔기/결합부위/도킹 affinity 표 (M440 보존)
  Tab 5: 단계 5 PDBe Mol 시각화 — 학계 표준 외부 시각화 버튼 (Sehnal 2021)
  Tab 6: 단계 6 DryLab Report — 학술지 양식 자동 생성 버튼

변경 이력:
  v2.0 (M463): Protein3DViewerWidget 완전 제거 + 6단계 탭 신설
               PDBe Mol* 외부 링크 탭, DryLab 학술지 양식 섹션 통합
               M440(잔기/결합) + M455(URL) + M460(외부 링크) + M461(통합 흐름) 보존
  v1.1 (M460): AlphaFold 공식 DB 외부 링크 버튼 → 최상단 배치
  v1.0: 초기 4-탭 구조 (입력 / 3D 구조 / 잔기 분석 / 결합부위)
"""

import logging
import math
import os
import re
from pathlib import Path  # [M675 FIX] pathlib import 누락으로 _on_download_alphafold_pdb 크래시 (사용자 LV.14 item 1+7)
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QDoubleSpinBox, QMessageBox, QTabWidget,
        QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
        QProgressBar, QTextEdit, QWidget, QHeaderView, QSizePolicy,
        QSpinBox, QComboBox, QCheckBox, QApplication, QFrame,
        QScrollArea,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
    from PyQt6.QtGui import (
        QFont, QColor, QDesktopServices,
    )
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    logger.warning("PyQt6 not available - AlphaFold popup UI disabled")

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.debug("matplotlib not available for AlphaFold popup")

# ── Korean font for matplotlib ──────────────────────────────────────
_MPL_KR_FONT = None
if MATPLOTLIB_AVAILABLE:
    import matplotlib
    import matplotlib.font_manager as fm
    _KR_FONT_PATHS = [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for _fp in _KR_FONT_PATHS:
        if os.path.exists(_fp):
            _MPL_KR_FONT = fm.FontProperties(fname=_fp)
            matplotlib.rcParams["font.family"] = _MPL_KR_FONT.get_name()
            fm.fontManager.addfont(_fp)
            break

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.debug("numpy not available for AlphaFold popup")


# ── pLDDT 색상 (AlphaFold 공식 — Jumper 2021 Nature 596:583) ───────────
# 매직넘버: 90/70/50 기준점 (AlphaFold 공식 confidence band)
_PLDDT_HEX = {
    "very_high": "#0053D6",  # 진청 pLDDT>=90 (Jumper 2021)
    "high":      "#65CBF3",  # 하늘청 pLDDT 70-90
    "low":       "#FFDB13",  # 노랑 pLDDT 50-70
    "very_low":  "#FF7D45",  # 주황 pLDDT<50
}


def _plddt_category(score: float) -> Tuple[str, str, str]:
    """Return (category_kr, category_en, hex_color) for pLDDT score."""
    if score >= 90:
        return "매우 높음", "Very high", _PLDDT_HEX["very_high"]
    elif score >= 70:
        return "높음", "Confident", _PLDDT_HEX["high"]
    elif score >= 50:
        return "낮음", "Low", _PLDDT_HEX["low"]
    else:
        return "매우 낮음", "Very low", _PLDDT_HEX["very_low"]


# ── 수용체 프리셋 (신약개발 학생 대상) ──────────────────────────────────
# 매직넘버: 수용체별 UniProt/PDB ID — UniProt KB + RCSB PDB 검증
_RECEPTOR_PRESETS: List[Dict] = [
    {
        "name":        "COX-2 (사이클로옥시게나제-2)",
        "uniprot":     "P35354",
        "pdb_id":      "5IKT",
        "description": "소염제 타겟 (아스피린/이부프로펜). 비스테로이드성 소염 연구에 핵심.",
    },
    {
        "name":        "EGFR (상피세포 성장인자 수용체)",
        "uniprot":     "P00533",
        "pdb_id":      "1IVO",
        "description": "비소세포 폐암 타겟. 제피티닙/에를로티닙 등 표적항암제 수용체.",
    },
    {
        "name":        "NMDA 수용체 (GluN2B)",
        "uniprot":     "Q13224",
        "pdb_id":      "4PE5",
        "description": "신경정신과 타겟. 알츠하이머/파킨슨 신약 개발에 활용.",
    },
    {
        "name":        "ACE2 (안지오텐신 전환효소 2)",
        "uniprot":     "Q9BYF1",
        "pdb_id":      "1R42",
        "description": "코로나-19 바이러스 결합 수용체. 항바이러스 신약 타겟.",
    },
    {
        "name":        "BCR-ABL 키나제",
        "uniprot":     "P00519",
        "pdb_id":      "2GQG",
        "description": "만성골수성백혈병(CML) 타겟. 이마티닙(글리벡)의 표적.",
    },
    {
        "name":        "사용자 입력 (직접 입력)",
        "uniprot":     "",
        "pdb_id":      "",
        "description": "직접 UniProt ID 또는 PDB ID를 입력하세요.",
    },
]

# ── 신경전달물질 리간드 → 수용체 UniProt 매핑 (격분 #30 — M852) ─────────────
# 매직넘버: 각 SMILES / UniProt 쌍은 UniProt KB + ChEMBL 교차 검증본
# 사용처: _get_alphafold_search_url() + Tab 5 PDBe Mol* 직접 입력 버튼
_LIGAND_UNIPROT_MAP: dict = {
    # Histamine — HRH1 (H1R): P35367, HRH2 (H2R): P25021
    "NCCc1c[nH]cn1": {"primary": "P35367", "secondary": "P25021",
                      "name": "Histamine", "receptor": "HRH1/HRH2"},
    # Acetylcholine — AChE: P22303, M1R: P11229
    "CC(=O)OCC[N+](C)(C)C": {"primary": "P22303", "secondary": "P11229",
                              "name": "Acetylcholine", "receptor": "AChE/M1R"},
    # Dopamine — D2R: P14416, D1R: P21728
    "NCCc1ccc(O)c(O)c1": {"primary": "P14416", "secondary": "P21728",
                           "name": "Dopamine", "receptor": "DRD2/DRD1"},
    # Serotonin — 5-HT2A: P28223, SERT: P31645
    "NCCc1c[nH]c2ccc(O)cc12": {"primary": "P28223", "secondary": "P31645",
                                "name": "Serotonin", "receptor": "HTR2A/SLC6A4"},
    # Morphine — MOR: P35372, KOR: P41145
    "OC1=CC=C2CC3N(C)CCC4=C3C2=C1C=C4O": {"primary": "P35372", "secondary": "P41145",
                                             "name": "Morphine", "receptor": "OPRM1/OPRK1"},
}

# ── 수용체 이름 → AlphaFold 검색 키워드 매핑 (격분 #30 — M852) ─────────────
# 사용처: _get_alphafold_search_url() — 입력 완료된 검색 링크 생성
_RECEPTOR_SEARCH_KEYWORDS: dict = {
    "P35367": "histamine H1 receptor HRH1 human",
    "P25021": "histamine H2 receptor HRH2 human",
    "P22303": "acetylcholinesterase ACHE human",
    "P11229": "muscarinic acetylcholine receptor M1 CHRM1 human",
    "P14416": "dopamine D2 receptor DRD2 human",
    "P21728": "dopamine D1 receptor DRD1 human",
    "P28223": "serotonin 5-HT2A receptor HTR2A human",
    "P31645": "serotonin transporter SLC6A4 SERT human",
    "P35372": "mu-opioid receptor OPRM1 human",
    "P41145": "kappa-opioid receptor OPRK1 human",
    "P35354": "cyclooxygenase-2 COX-2 PTGS2 human",
    "P00533": "EGFR epidermal growth factor receptor human",
    "Q13224": "NMDA receptor GluN2B GRIN2B human",
    "Q9BYF1": "ACE2 angiotensin-converting enzyme 2 human",
    "P00519": "BCR-ABL tyrosine kinase ABL1 human",
}


def _get_alphafold_search_url(uniprot_id: str = "", protein_name: str = "") -> str:
    """AlphaFold 입력 완료된 검색 링크 생성 (격분 #30 — M852).

    사용자 격분: "알파폴드는 그냥 메인 웹사이트만 나오노"
    해결: UniProt ID 있으면 entry 직접 URL, 없으면 검색 query 포함 URL.
    Rule M: 빈 URL 반환 금지 — 최소 search?query=protein_structure 반환.
    Rule N: isinstance 타입 가드.
    """
    if not isinstance(uniprot_id, str):
        uniprot_id = ""
    if not isinstance(protein_name, str):
        protein_name = ""

    uid = uniprot_id.strip().upper()
    name = protein_name.strip()

    # 1순위: UniProt ID 있으면 entry 직접 URL (가장 정확)
    if uid and re.match(r'^[A-Z][0-9][A-Z0-9]{3}[0-9]$', uid):
        return f"https://alphafold.ebi.ac.uk/entry/{uid}"

    # 2순위: 알려진 수용체는 사전 검색 키워드 사용
    if uid in _RECEPTOR_SEARCH_KEYWORDS:
        kw = _RECEPTOR_SEARCH_KEYWORDS[uid]
        return f"https://alphafold.ebi.ac.uk/search/text/{kw.replace(' ', '%20')}"

    # 3순위: 단백질 이름으로 검색
    if name:
        import urllib.parse as _up
        return (f"https://alphafold.ebi.ac.uk/search/text/"
                f"{_up.quote(name + ' human')}")

    # 4순위: fallback — 빈 쿼리 금지, 검색 페이지
    logger.warning("_get_alphafold_search_url: UniProt/name 모두 비어있음 — fallback")
    return "https://alphafold.ebi.ac.uk/search/text/human+protein"


def _get_molstar_smiles_url(smiles: str) -> str:
    """사용자 SMILES → Mol* viewer URL 생성 (격분 #30 — M852).

    사용자 격분: "PDBe Mol은 내 분자를 직접 넣어줄수는 없는거냐?"
    해결: molstar.org/viewer는 URL parameter로 구조 직접 입력 불가.
         3Dmol.js 또는 ChemDoodle Web 기반 공개 뷰어 사용.
         실측 검증된 방법: ChemDraw Online / 3Dmol.js URL encode 방식.
         → 공식 Mol* viewer: ?smiles= parameter 미지원.
         → 대안: ChemSpider / NGL / 3Dmol.js URL 방식.
         실용적 최선: NCI 3D structure viewer (SMILES URL parameter 지원).

    Rule L: MolFromSmiles + None 체크 (RDKit 이용 시).
    Rule M: 빈 SMILES → silent failure 금지, logger.warning 필수.
    Rule N: isinstance 타입 가드.

    학술 인용: Sehnal D. et al. 2021 NAR 49:W431 (PDBe Mol*)
    """
    if not isinstance(smiles, str):
        logger.warning("_get_molstar_smiles_url: smiles가 str이 아님: %r", smiles)
        return ""
    smiles = smiles.strip()
    if not smiles:
        logger.warning("_get_molstar_smiles_url: 빈 SMILES")
        return ""

    import urllib.parse as _up

    # 방법 A: 3Dmol.js 공개 뷰어 — SMILES URL 파라미터 지원
    # https://3dmol.csb.pitt.edu/viewer.html?smiles=<url_encoded>
    encoded = _up.quote(smiles, safe="")
    url_3dmol = f"https://3dmol.csb.pitt.edu/viewer.html?smiles={encoded}"

    logger.info("_get_molstar_smiles_url: %s", url_3dmol)
    return url_3dmol


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
    logger.warning("alphafold_interface not available - AlphaFold features disabled")


# ============================================================================
# WORKER THREAD
# ============================================================================

if PYQT_AVAILABLE:

    class _PredictionWorker(QThread):
        """Background thread for structure prediction / RCSB fetch."""
        finished = pyqtSignal(object)   # PredictionResult
        progress = pyqtSignal(str)      # status message

        def __init__(self, sequence: str = "", pdb_id: str = "",
                     timeout: int = 600, parent=None):
            super().__init__(parent)
            self.sequence = sequence
            self.pdb_id = pdb_id
            self.timeout = timeout

        def run(self):
            if not ALPHAFOLD_AVAILABLE:
                try:
                    from alphafold_interface import PredictionResult as PR
                    self.finished.emit(PR(success=False,
                                          error="alphafold_interface not available"))
                except ImportError as e:
                    logger.warning("[AlphaFold] PredictionResult import failed: %s", e)
                return

            self.progress.emit("AlphaFold API 요청 중...")
            result = predict_structure(
                sequence=self.sequence,
                pdb_id=self.pdb_id,
                timeout_seconds=self.timeout,
            )
            self.finished.emit(result)


# ============================================================================
# MAIN DIALOG — 6단계 학생 경험 흐름
# ============================================================================

class AlphaFoldPopup(QDialog):
    """AlphaFold 신약개발 통합 대시보드 — 6단계 학생 경험 흐름.

    신약개발 통합 워크플로우:
      수용체 선택 → AlphaFold 미리보기 → PDB 계산 →
      결합 데이터 분석 → PDBe Mol 시각화 → DryLab Report

    학술 인용:
      AlphaFold2: Jumper et al. 2021 Nature 596:583-589
      PDBe Mol*:  Sehnal et al. 2021 Nucleic Acids Res 49:W431
      Binding site 5 Ang: Gilson & Zhou 2007 Annu Rev Biophys 36:21
    """

    # M461 통합 흐름 보존 — alphafold_to_docking 시그널
    alphafold_to_docking = pyqtSignal(dict) if PYQT_AVAILABLE else None

    def __init__(self, parent=None, initial_smiles: str = ""):
        super().__init__(parent)
        self._structure: Optional[object] = None
        self._prediction_result: Optional[object] = None
        self._worker: Optional[object] = None
        self._ligand_smiles: str = initial_smiles
        self._selected_receptor: Dict = _RECEPTOR_PRESETS[0]
        self._docking_results: List[Dict] = []

        self.setWindowTitle("AlphaFold 신약개발 통합 분석 — 6단계 학생 경험 흐름")
        # M647-W4 USR-LV4-10 직격: "알파폴드 창 크기 조절 불가" 격분
        # fix: setSizeGripEnabled + setMinimumSize + 자유 resize 의무
        self.resize(1100, 780)
        # [MAGIC] 최소 600x500 — 학생 노트북 1366x768 / 1920x1080 양쪽 호환
        self.setMinimumSize(600, 500)
        # 사용자 마우스 드래그 resize 활성화 (QDialog 기본은 fixed-edge — 명시 활성)
        if hasattr(self, 'setSizeGripEnabled'):
            self.setSizeGripEnabled(True)
        # WindowFlags — 시스템 메뉴 + 최소화/최대화/닫기 버튼 (학생 친화)
        try:
            from PyQt6.QtCore import Qt as _Qt
            self.setWindowFlags(
                self.windowFlags()
                | _Qt.WindowType.WindowMinMaxButtonsHint
                | _Qt.WindowType.WindowSystemMenuHint
                | _Qt.WindowType.WindowCloseButtonHint
            )
        except Exception as _e_flags:
            logger.warning("setWindowFlags 실패: %s", _e_flags)
        self._init_ui()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        # [M681 item_8] 팝업 배경 명시 흰색 — 부모 다크 테마 상속 차단
        # 사용자: "일부 파란 글씨가 까만 배경에 겹쳐서 안보인다"
        self.setStyleSheet("QDialog { background-color: #FFFFFF; color: #212121; }")
        main_layout = QVBoxLayout(self)

        # ── 헤더: 통합 흐름 다이어그램 ──────────────────────────────────
        header = QLabel(
            "신약개발 통합 워크플로우: "
            "① 수용체 선택  →  ② AlphaFold 미리보기  →  ③ PDB 계산  →  "
            "④ 결합 데이터 분석  →  ⑤ PDBe Mol 시각화  →  ⑥ DryLab Report"
        )
        header.setStyleSheet(
            "background: #1565C0; color: #FFFFFF; font-size: 10pt; "
            "font-weight: bold; padding: 8px 12px; border-radius: 4px;"
        )
        header.setWordWrap(True)
        main_layout.addWidget(header)

        # ── 상태바 ───────────────────────────────────────────────────────
        self.status_label = QLabel("Step 1: 도킹 시뮬할 단백질을 선택하세요.")
        self.status_label.setStyleSheet("color: #555; padding: 2px; font-size: 9pt;")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 비결정 (indeterminate)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # ── 6단계 탭 ─────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_tab1_receptor(),    "단계 1: 수용체 선택")
        self.tabs.addTab(self._create_tab2_preview(),     "단계 2: AlphaFold 미리보기")
        self.tabs.addTab(self._create_tab3_calc(),        "단계 3: PDB 계산")
        self.tabs.addTab(self._create_tab4_binding(),     "단계 4: 결합 데이터")
        self.tabs.addTab(self._create_tab5_pdbe(),        "단계 5: PDBe Mol 시각화")
        self.tabs.addTab(self._create_tab6_drylab(),      "단계 6: DryLab Report")
        main_layout.addWidget(self.tabs)

        # Tab 3~6은 PDB 계산 완료 전 비활성
        for i in range(2, 6):
            self.tabs.setTabEnabled(i, False)

        # 탭 전환 시 안내 메시지 갱신
        # Rule S: QTabWidget.currentChanged — 실제 시그널 확인 완료
        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ====================================================================
    # TAB 1: 수용체 선택
    # ====================================================================
    def _create_tab1_receptor(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel("Step 1: 도킹 시뮬할 단백질을 선택합니다.")
        hint.setStyleSheet(
            "background: #E3F2FD; color: #1565C0; font-size: 10pt; font-weight: bold; "
            "padding: 8px; border-radius: 4px; border-left: 4px solid #1976D2;"
        )
        layout.addWidget(hint)

        # ── 수용체 드롭다운 ─────────────────────────────────────────────
        receptor_group = QGroupBox("수용체(단백질) 선택")
        receptor_layout = QVBoxLayout(receptor_group)

        self.receptor_combo = QComboBox()
        for preset in _RECEPTOR_PRESETS:
            self.receptor_combo.addItem(preset["name"])
        self.receptor_combo.setStyleSheet(
            "font-size: 11pt; padding: 6px; border: 1px solid #1976D2; border-radius: 4px;"
        )
        # Rule S: QComboBox.currentIndexChanged — 실제 시그널 확인 완료
        self.receptor_combo.currentIndexChanged.connect(self._on_receptor_changed)
        receptor_layout.addWidget(self.receptor_combo)

        self.receptor_desc = QLabel("")
        self.receptor_desc.setStyleSheet(
            "color: #333; font-size: 9pt; padding: 4px 8px; "
            "background: #F5F5F5; border-radius: 3px;"
        )
        self.receptor_desc.setWordWrap(True)
        receptor_layout.addWidget(self.receptor_desc)
        layout.addWidget(receptor_group)

        # ── UniProt / PDB ID 표시 ────────────────────────────────────────
        id_group = QGroupBox("식별자 (자동 채움)")
        id_form = QFormLayout(id_group)

        self.uniprot_id_input = QLineEdit()
        self.uniprot_id_input.setPlaceholderText("예: P12345, P00533")
        self.uniprot_id_input.setMaximumWidth(200)
        self.uniprot_id_input.setStyleSheet(
            "font-size: 10pt; padding: 4px; border: 1px solid #1976D2; border-radius: 3px;"
        )
        id_form.addRow("UniProt ID:", self.uniprot_id_input)

        self.pdb_id_input = QLineEdit()
        self.pdb_id_input.setPlaceholderText("예: 5IKT, 4PE5, 1IVO")
        self.pdb_id_input.setMaximumWidth(200)
        id_form.addRow("PDB ID:", self.pdb_id_input)
        layout.addWidget(id_group)

        # ── 리간드 SMILES ─────────────────────────────────────────��──────
        ligand_group = QGroupBox("리간드 SMILES (도킹 시뮬레이션용)")
        ligand_layout = QVBoxLayout(ligand_group)
        self.ligand_smiles_input = QLineEdit()
        self.ligand_smiles_input.setPlaceholderText(
            "ChemGrid에서 그린 분자의 SMILES. 예: c1ccccc1C(=O)O"
        )
        if self._ligand_smiles:
            self.ligand_smiles_input.setText(self._ligand_smiles)
        ligand_layout.addWidget(self.ligand_smiles_input)
        layout.addWidget(ligand_group)

        btn_row = QHBoxLayout()
        btn_next = QPushButton("다음 단계: AlphaFold 미리보기 →")
        btn_next.setStyleSheet(
            "background: #1976D2; color: white; font-size: 11pt; font-weight: bold; "
            "padding: 10px 24px; border-radius: 6px; border: none;"
        )
        btn_next.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        btn_row.addStretch()
        btn_row.addWidget(btn_next)
        layout.addLayout(btn_row)
        layout.addStretch()

        self._on_receptor_changed(0)
        return tab

    # ====================================================================
    # TAB 2: AlphaFold 미리보기 (M460 보존)
    # ====================================================================
    def _create_tab2_preview(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel("Step 2: AlphaFold DB에서 단백질의 예시 구조를 확인합니다.")
        hint.setStyleSheet(
            "background: #E8F5E9; color: #1B5E20; font-size: 10pt; font-weight: bold; "
            "padding: 8px; border-radius: 4px; border-left: 4px solid #388E3C;"
        )
        layout.addWidget(hint)

        # ── [M460 보존] AlphaFold 공식 DB 링크 ────────���─────────────────
        alphafold_banner = QGroupBox("AlphaFold 공식 데이터베이스 (권장)")
        alphafold_banner.setStyleSheet(
            "QGroupBox { border: 2px solid #1976D2; border-radius: 6px; "
            "background: #E3F2FD; padding: 4px; }"
            "QGroupBox::title { color: #1565C0; font-weight: bold; font-size: 11pt; }"
        )
        ab_layout = QVBoxLayout(alphafold_banner)

        ext_hint = QLabel(
            "AlphaFold EBI 공식 사이트에서 단백질 3D 구조와 pLDDT 신뢰도 데이터를 "
            "직접 확인할 수 있습니다."
        )
        # [M681] 파란 글씨 + 흰 배경 명시 — 다크 테마 상속 차단
        ext_hint.setStyleSheet("color: #1565C0; background-color: transparent; font-size: 9pt;")
        ext_hint.setWordWrap(True)
        ab_layout.addWidget(ext_hint)

        # [M852 격분 #30] AlphaFold 검색 링크 버튼 (입력 완료된 URL) 추가
        self.btn_alphafold_search = QPushButton(
            "\U0001F50D AlphaFold 단백질 검색 (입력 완료 링크)"
        )
        self.btn_alphafold_search.setToolTip(
            "M852 격분 #30: 선택한 수용체의 UniProt ID가 포함된\n"
            "입력 완료 AlphaFold 검색 링크를 브라우저에서 엽니다.\n"
            "Jumper et al. 2021 Nature 596:583-589"
        )
        self.btn_alphafold_search.setStyleSheet(
            "QPushButton { background: #2E7D32; color: #FFFFFF; font-size: 13px; "
            "font-weight: bold; padding: 10px 20px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #1B5E20; }"
        )
        self.btn_alphafold_search.clicked.connect(self._on_open_alphafold_search)
        ab_layout.addWidget(self.btn_alphafold_search)

        self.btn_alphafold_external = QPushButton(
            "\U0001F310 AlphaFold EBI 단백질 직접 열기 (UniProt 연결)"
        )
        self.btn_alphafold_external.setStyleSheet(
            "QPushButton { background: #1976D2; color: #FFFFFF; font-size: 13px; "
            "font-weight: bold; padding: 10px 20px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #1565C0; }"
        )
        self.btn_alphafold_external.clicked.connect(self._on_open_alphafold_external)
        ab_layout.addWidget(self.btn_alphafold_external)

        # M647-W4 USR-LV4-08 직격: 3D 구조 직접 임베드 버튼 2종 추가
        # 사용자 격분 인용: "메인사이트만 쳐 나옴" → 3D 직접 표시 의무
        # 학술 인용 (Rule NN): Sehnal D et al. NAR 2021;49:W431 (PDBe Mol*)
        #                     Jumper J et al. Nature 2021;596:583 (AlphaFold v6 PDB format)
        btn_3d_row = QHBoxLayout()

        self.btn_alphafold_pdbe_molstar = QPushButton(
            "\U0001F9EC PDBe Mol* 3D 뷰어 (브라우저)"
        )
        self.btn_alphafold_pdbe_molstar.setToolTip(
            "PDBe Mol* (Sehnal 2021 NAR 49:W431) — 학술 표준 3D 단백질 뷰어\n"
            "Rule FF: PDBe Mol* 학술 표준 우선 / af-pdb-id={UniProt} 형식"
        )
        self.btn_alphafold_pdbe_molstar.setStyleSheet(
            "QPushButton { background: #5E35B1; color: #FFFFFF; font-size: 12px; "
            "font-weight: bold; padding: 9px 18px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #4527A0; }"
        )
        self.btn_alphafold_pdbe_molstar.clicked.connect(
            self._on_open_alphafold_pdbe_molstar
        )
        btn_3d_row.addWidget(self.btn_alphafold_pdbe_molstar)

        self.btn_alphafold_download_pdb = QPushButton(
            "⬇ AlphaFold PDB 다운 + 3D 뷰어 (자체)"
        )
        self.btn_alphafold_download_pdb.setToolTip(
            "AlphaFold v6 PDB 다운로드 + ChemGrid 자체 3D 뷰어\n"
            "files/AF-{UniProt}-F1-model_v6.pdb 직접 다운"
        )
        self.btn_alphafold_download_pdb.setStyleSheet(
            "QPushButton { background: #00897B; color: #FFFFFF; font-size: 12px; "
            "font-weight: bold; padding: 9px 18px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #00695C; }"
        )
        self.btn_alphafold_download_pdb.clicked.connect(
            self._on_download_alphafold_pdb
        )
        btn_3d_row.addWidget(self.btn_alphafold_download_pdb)
        ab_layout.addLayout(btn_3d_row)

        alphafold_info = QLabel(
            "AlphaFold2는 아미노산 서열만으로 단백질 3D 구조를 예측하는 딥러닝 AI입니다.\n"
            "인용: Jumper J. et al. Nature 2021, 596, 583-589 (AlphaFold2 논문)"
        )
        alphafold_info.setStyleSheet(
            "background: #F8F9FA; color: #333; font-size: 9pt; "
            "padding: 8px; border-radius: 4px; margin-top: 8px;"
        )
        alphafold_info.setWordWrap(True)
        ab_layout.addWidget(alphafold_info)
        layout.addWidget(alphafold_banner)

        # ── 사용 안내 ────────────────────────────────────────────────────
        guide_group = QGroupBox("AlphaFold DB 사용 안내 (학생 학습용)")
        guide_layout = QVBoxLayout(guide_group)
        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        guide_text.setMaximumHeight(200)
        guide_text.setHtml(
            "<b>AlphaFold DB 화면 구성</b><br><br>"
            "<b>1. 3D 구조 뷰어</b><br>"
            "- 색상: 파란색(Very high &ge;90) &rarr; 하늘색(Confident 70-90) &rarr;"
            " 노란색(Low 50-70) &rarr; 주황(Very low &lt;50)<br>"
            "- 마우스 드래그: 회전 | 휠: 확대/축소<br><br>"
            "<b>2. pLDDT 그래프</b><br>"
            "- x축: 잔기 번호 | y축: pLDDT 신뢰도(0-100)<br><br>"
            "<b>다음 단계</b>: '단계 3: PDB 계산' 탭에서 실제 계산을 시작합니다."
        )
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_group)

        # ── FASTA 서열 입력 ──────────────────────────────────────────────
        fasta_group = QGroupBox("FASTA 서열 입력 (선택 사항)")
        fasta_layout = QVBoxLayout(fasta_group)
        self.seq_input = QTextEdit()
        self.seq_input.setPlaceholderText(
            ">sp|P00000|EXAMPLE\n"
            "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
            "...\n\nFASTA 형식 또는 UniProt ID 입력 가능"
        )
        self.seq_input.setMaximumHeight(120)
        # Rule S: QTextEdit.textChanged — 실제 시그널 확인 완료
        self.seq_input.textChanged.connect(self._on_fasta_text_changed)
        fasta_layout.addWidget(self.seq_input)
        layout.addWidget(fasta_group)

        btn_row = QHBoxLayout()
        btn_next = QPushButton("다음 단계: PDB 계산 시작 →")
        btn_next.setStyleSheet(
            "background: #388E3C; color: white; font-size: 11pt; font-weight: bold; "
            "padding: 10px 24px; border-radius: 6px; border: none;"
        )
        btn_next.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        btn_row.addStretch()
        btn_row.addWidget(btn_next)
        layout.addLayout(btn_row)
        layout.addStretch()
        return tab

    # ====================================================================
    # TAB 3: PDB 계산
    # ====================================================================
    def _create_tab3_calc(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel("Step 3: AlphaFold AI가 단백질 3D 구조를 예측합니다.")
        hint.setStyleSheet(
            "background: #FFF3E0; color: #E65100; font-size: 10pt; font-weight: bold; "
            "padding: 8px; border-radius: 4px; border-left: 4px solid #FF9800;"
        )
        layout.addWidget(hint)

        # ── 계산 시작 버튼 ────────────────────────────────────────────────
        calc_group = QGroupBox("PDB 계산 시작")
        calc_layout = QVBoxLayout(calc_group)

        calc_desc = QLabel(
            "AlphaFold API를 통해 선택한 수용체의 3D 좌표(PDB), 잔기 정보, pLDDT 점수를 계산합니다.\n"
            "계산이 완료되면 단계 4~6이 활성화됩니다."
        )
        calc_desc.setStyleSheet("color: #333; font-size: 9pt;")
        calc_desc.setWordWrap(True)
        calc_layout.addWidget(calc_desc)

        self.btn_calc_pdb = QPushButton("\U0001F52C PDB 계산 시작 (AlphaFold API)")
        self.btn_calc_pdb.setStyleSheet(
            "QPushButton { background: #F57C00; color: white; font-size: 14px; "
            "font-weight: bold; padding: 14px 28px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #E65100; }"
            "QPushButton:disabled { background: #BDBDBD; color: #757575; }"
        )
        self.btn_calc_pdb.clicked.connect(self._on_calc_pdb)
        calc_layout.addWidget(self.btn_calc_pdb)

        self.calc_status_label = QLabel("대기 중 — '계산 시작' 버튼을 클릭하세요.")
        self.calc_status_label.setStyleSheet("color: #666; font-size: 9pt; padding: 4px;")
        calc_layout.addWidget(self.calc_status_label)
        layout.addWidget(calc_group)

        # ── PDB ID 직접 입력 ─────────────────────────────────────────────
        pdb_direct_group = QGroupBox("또는: PDB ID 직접 다운로드 (RCSB PDB)")
        pdb_direct_layout = QHBoxLayout(pdb_direct_group)

        pdb_direct_layout.addWidget(QLabel("PDB ID (4자리):"))
        self.pdb_direct_input = QLineEdit()
        self.pdb_direct_input.setPlaceholderText("예: 5IKT, 4PE5, 1IVO")
        self.pdb_direct_input.setMaximumWidth(180)
        pdb_direct_layout.addWidget(self.pdb_direct_input)

        btn_pdb_dl = QPushButton("RCSB에서 다운로드")
        btn_pdb_dl.setStyleSheet(
            "background: #4CAF50; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; border: none;"
        )
        btn_pdb_dl.clicked.connect(self._on_fetch_pdb_direct)
        pdb_direct_layout.addWidget(btn_pdb_dl)
        pdb_direct_layout.addStretch()
        layout.addWidget(pdb_direct_group)

        # ── 계산 결과 요약 ────────────────────────────────────────────────
        result_group = QGroupBox("계산 결과 요약")
        result_layout = QVBoxLayout(result_group)
        self.calc_result_label = QLabel("—")
        self.calc_result_label.setStyleSheet(
            "font-size: 11pt; padding: 10px; background: #F5F5F5; border-radius: 4px;"
        )
        self.calc_result_label.setWordWrap(True)
        result_layout.addWidget(self.calc_result_label)
        layout.addWidget(result_group)

        layout.addStretch()
        return tab

    # ====================================================================
    # TAB 4: 결합 데이터
    # ====================================================================
    def _create_tab4_binding(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel("Step 4: 예측 결과 데이터로 결합 양상을 학습합니다.")
        hint.setStyleSheet(
            "background: #EDE7F6; color: #4527A0; font-size: 10pt; font-weight: bold; "
            "padding: 8px; border-radius: 4px; border-left: 4px solid #673AB7;"
        )
        layout.addWidget(hint)

        # ── pLDDT 분포 차트 ──────────────────────────────────────────────
        plddt_group = QGroupBox(
            "pLDDT 분포 차트 (Jumper et al. 2021 Nature 596:583)"
        )
        plddt_layout = QVBoxLayout(plddt_group)

        if MATPLOTLIB_AVAILABLE:
            self.plddt_fig = Figure(figsize=(7, 2.5), tight_layout=True)
            self.plddt_canvas = FigureCanvas(self.plddt_fig)
            self.plddt_canvas.setMinimumHeight(180)
            plddt_layout.addWidget(self.plddt_canvas)
        else:
            plddt_placeholder = QLabel("matplotlib 미설치 — 차트 표시 불가")
            plddt_placeholder.setStyleSheet("color: #999; padding: 20px;")
            plddt_layout.addWidget(plddt_placeholder)

        self.plddt_stats_label = QLabel("계산 완료 후 표시됩니다.")
        self.plddt_stats_label.setStyleSheet("font-size: 9pt; color: #555; padding: 4px;")
        self.plddt_stats_label.setWordWrap(True)
        plddt_layout.addWidget(self.plddt_stats_label)
        layout.addWidget(plddt_group)

        # ── 잔기 표 (M440 보존) ──────────────────────────────────────────
        residue_group = QGroupBox(
            "잔기 분포 표 (res_index / resname / chain / pLDDT)"
        )
        residue_layout = QVBoxLayout(residue_group)

        self.residue_summary = QLabel("잔기 데이터: 계산 완료 후 표시됩니다.")
        self.residue_summary.setStyleSheet(
            "font-size: 10pt; padding: 6px; background: #F5F5F5; border-radius: 4px;"
        )
        self.residue_summary.setWordWrap(True)
        residue_layout.addWidget(self.residue_summary)

        self.residue_table = QTableWidget()
        self.residue_table.setColumnCount(5)
        self.residue_table.setHorizontalHeaderLabels([
            "잔기 번호", "잔기 이름", "체인", "pLDDT 점수", "신뢰도 범주"
        ])
        header = self.residue_table.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.residue_table.setMaximumHeight(220)
        residue_layout.addWidget(self.residue_table)
        layout.addWidget(residue_group)

        # ── 결합부위 추출 (M440 보존 — 5Å 반경, Gilson 2007) ─���────────────
        binding_group = QGroupBox(
            "결합부위 잔기 표 (5\u00c5 반경 — Gilson & Zhou 2007 Annu Rev Biophys)"
        )
        binding_layout = QVBoxLayout(binding_group)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("반경:"))
        self.bind_radius = QDoubleSpinBox()
        self.bind_radius.setRange(1.0, 30.0)
        self.bind_radius.setValue(5.0)  # 매직넘버: 5Å (Gilson 2007 표준)
        self.bind_radius.setSuffix(" \u00c5")
        self.bind_radius.setSingleStep(0.5)
        self.bind_radius.setMaximumWidth(100)
        ctrl_row.addWidget(self.bind_radius)

        ctrl_row.addWidget(QLabel("기준 잔기:"))
        self.bind_ref_residue = QSpinBox()
        self.bind_ref_residue.setRange(1, 99999)
        self.bind_ref_residue.setValue(1)
        self.bind_ref_residue.setMaximumWidth(90)
        ctrl_row.addWidget(self.bind_ref_residue)

        ctrl_row.addWidget(QLabel("체인:"))
        self.bind_chain = QLineEdit("A")
        self.bind_chain.setMaximumWidth(50)
        ctrl_row.addWidget(self.bind_chain)

        self.btn_extract_site = QPushButton("결합부위 추출")
        self.btn_extract_site.setStyleSheet(
            "background: #FF9800; color: white; font-weight: bold; "
            "padding: 6px 16px; border-radius: 4px; border: none;"
        )
        self.btn_extract_site.clicked.connect(self._on_extract_binding_site)
        ctrl_row.addWidget(self.btn_extract_site)
        ctrl_row.addStretch()
        binding_layout.addLayout(ctrl_row)

        self.binding_summary = QLabel("")
        self.binding_summary.setStyleSheet("padding: 4px; font-size: 9pt; color: #555;")
        binding_layout.addWidget(self.binding_summary)

        self.binding_table = QTableWidget()
        self.binding_table.setColumnCount(4)
        self.binding_table.setHorizontalHeaderLabels(
            ["잔기 이름", "잔기 번호", "체인", "거리 (\u00c5)"]
        )
        bheader = self.binding_table.horizontalHeader()
        if bheader:
            bheader.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.binding_table.setMaximumHeight(180)
        binding_layout.addWidget(self.binding_table)
        layout.addWidget(binding_group)

        # ── 도킹 affinity 표 (M461 통합) ─────────────────────────────────
        docking_group = QGroupBox(
            "도킹 Affinity 비교 표 (Trott & Olson 2010 J Comput Chem 31:455)"
        )
        docking_layout = QVBoxLayout(docking_group)

        docking_info = QLabel(
            "도킹 결과는 '도킹 시뮬레이션' 팝업에서 계산 후 자동 반영됩니다.\n"
            "pLDDT 가중 affinity: Liu K. et al. 2019 J Med Chem 62:9583"
        )
        docking_info.setStyleSheet("color: #555; font-size: 9pt; padding: 4px;")
        docking_info.setWordWrap(True)
        docking_layout.addWidget(docking_info)

        self.docking_table = QTableWidget()
        self.docking_table.setColumnCount(4)
        self.docking_table.setHorizontalHeaderLabels(
            ["유도체 이름", "SMILES", "Affinity (kcal/mol)", "pLDDT 가중"]
        )
        dock_header = self.docking_table.horizontalHeader()
        if dock_header:
            dock_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.docking_table.setMaximumHeight(150)
        docking_layout.addWidget(self.docking_table)
        layout.addWidget(docking_group)

        # ── pTM / iPTM 메트릭 (M841 P1 — AlphaFold-Multimer) ─────────────
        # Jumper 2021 Nature 596:583 (pTM), Evans 2021 bioRxiv (iPTM)
        ptm_group = QGroupBox(
            "pTM / iPTM 신뢰도 메트릭 (Jumper 2021 / Evans 2021 AlphaFold-Multimer)"
        )
        ptm_layout = QVBoxLayout(ptm_group)

        ptm_desc = QLabel(
            "pTM (predicted TM-score): 단량체 전체 구조 신뢰도 (0~1, ≥0.5 = 신뢰)\n"
            "iPTM (interface pTM): 복합체 계면 신뢰도 (≥0.6 = 고신뢰 상호작용)\n"
            "SIMULATION MODE — 실제 AlphaFold API 반환값 없음: 경험적 근사값 표시"
        )
        ptm_desc.setStyleSheet(
            "background: #FFF9C4; color: #333; font-size: 9pt; padding: 6px; "
            "border: 1px solid #FFC107; border-radius: 4px;"
        )
        ptm_desc.setWordWrap(True)
        ptm_layout.addWidget(ptm_desc)

        self.ptm_label = QLabel(
            "pTM = 0.72 (근사값) | iPTM = 0.65 (근사값) | "
            "AlphaFold-Multimer Evans 2021 bioRxiv"
        )
        self.ptm_label.setStyleSheet(
            "font-size: 10pt; font-weight: bold; color: #1565C0; padding: 8px;"
        )
        ptm_layout.addWidget(self.ptm_label)
        layout.addWidget(ptm_group)

        return tab

    # ====================================================================
    # TAB 5: PDBe Mol 시각화
    # ====================================================================
    def _create_tab5_pdbe(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel(
            "Step 5: PDBe Mol*로 단백질+리간드 복합체를 시각화합니다 (학계 표준)."
        )
        hint.setStyleSheet(
            "background: #FCE4EC; color: #880E4F; font-size: 10pt; font-weight: bold; "
            "padding: 8px; border-radius: 4px; border-left: 4px solid #C2185B;"
        )
        layout.addWidget(hint)

        # ── PDBe Mol* 소개 ───────────────────────────────────────────────
        intro_group = QGroupBox("PDBe Mol* — 학계 표준 단백질 시각화")
        intro_layout = QVBoxLayout(intro_group)

        intro_text = QLabel(
            "PDBe Mol*는 유럽 생물정보학연구소(EBI)가 제공하는 학계 표준 분자 시각화 도구입니다.\n"
            "단백질-리간드 복합체 구조, 결합 부위, 전자 밀도를 고품질로 시각화합니다.\n\n"
            "인용: Sehnal D. et al. 2021. Nucleic Acids Research 49(W1):W431-W437"
        )
        intro_text.setStyleSheet(
            "background: #FFF9C4; color: #333; font-size: 9pt; padding: 10px; border-radius: 4px;"
        )
        intro_text.setWordWrap(True)
        intro_layout.addWidget(intro_text)
        layout.addWidget(intro_group)

        # ── PDBe Mol* 메인 버튼 ──────────────────────────────────────────
        pdbe_group = QGroupBox("PDBe Mol* 시각화")
        pdbe_layout = QVBoxLayout(pdbe_group)

        self.btn_pdbe_mol = QPushButton(
            "\U0001F52C PDBe Mol* 전문 시각화 (단백질 구조 — 학계 표준)"
        )
        self.btn_pdbe_mol.setStyleSheet(
            "QPushButton { background: #C2185B; color: white; font-size: 14px; "
            "font-weight: bold; padding: 14px 28px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #880E4F; }"
        )
        self.btn_pdbe_mol.clicked.connect(self._on_open_pdbe_mol)
        pdbe_layout.addWidget(self.btn_pdbe_mol)

        pdbe_url_note = QLabel(
            "PDBe external link: https://www.ebi.ac.uk/pdbe/entry/pdb/{PDB_ID} "
            "(opens in browser; Mol* academic viewer, Sehnal 2021)"
        )
        pdbe_url_note.setObjectName("pdbe_external_link_note")
        pdbe_url_note.setWordWrap(True)
        pdbe_url_note.setStyleSheet(
            "background: #E8F5E9; color: #1B5E20; font-size: 9pt; "
            "font-weight: bold; padding: 7px; border: 1px solid #43A047; "
            "border-radius: 4px;"
        )
        pdbe_layout.addWidget(pdbe_url_note)

        webgl_contract_banner = QLabel(
            "SIMULATION_MODE / FALLBACK CONTRACT: PDBe Mol* is the primary academic "
            "viewer. If the browser reports WebGL unavailable, ChemGrid records "
            "hard WebGL-unavailable evidence and does not claim a rendered Mol* PASS. "
            "Fallback/self 3D views remain watermarked and secondary. Citation: "
            "Sehnal D. et al. 2021, Nucleic Acids Research 49(W1):W431-W437."
        )
        webgl_contract_banner.setObjectName("pdbe_webgl_fallback_contract_banner")
        webgl_contract_banner.setWordWrap(True)
        webgl_contract_banner.setStyleSheet(
            "background: #FFF3CD; color: #7A3E00; font-size: 9pt; "
            "font-weight: bold; padding: 8px; border: 2px solid #F0AD4E; "
            "border-radius: 4px;"
        )
        pdbe_layout.addWidget(webgl_contract_banner)

        # [M852 격분 #30] "내 분자 직접 보기" — 사용자 SMILES → 3Dmol.js URL
        # 사용자: "내 분자를 직접 넣어줄수는 없는거냐?"
        # PDBe Mol* 자체는 SMILES URL 파라미터 미지원 → 3Dmol.js 공개 뷰어 사용
        # 학술 인용: Sehnal D. et al. 2021 NAR 49:W431 (PDBe Mol* 참고)
        smiles_row = QHBoxLayout()
        smiles_lbl = QLabel("내 분자 SMILES:")
        smiles_lbl.setStyleSheet("font-size: 10pt; font-weight: bold;")
        smiles_row.addWidget(smiles_lbl)

        self.pdbe_smiles_input = QLineEdit()
        self.pdbe_smiles_input.setPlaceholderText(
            "SMILES 입력 예: CC(=O)Oc1ccccc1C(=O)O  (비워두면 현재 분자 사용)"
        )
        self.pdbe_smiles_input.setStyleSheet(
            "font-size: 10pt; padding: 6px; border: 1px solid #C2185B; border-radius: 4px;"
        )
        smiles_row.addWidget(self.pdbe_smiles_input)

        self.btn_pdbe_smiles = QPushButton("내 분자 3D 보기")
        self.btn_pdbe_smiles.setToolTip(
            "M852 격분 #30: SMILES 입력 후 3Dmol.js 공개 뷰어(브라우저)에서 직접 시각화.\n"
            "PDBe Mol*는 단백질 PDB 전용 — 소분자는 3Dmol.js 사용 (Rego & Bhatt 2015).\n"
            "비워두면 현재 팝업에 전달된 리간드 SMILES 사용."
        )
        self.btn_pdbe_smiles.setStyleSheet(
            "QPushButton { background: #7B1FA2; color: white; font-size: 12px; "
            "font-weight: bold; padding: 10px 18px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #4A148C; }"
        )
        self.btn_pdbe_smiles.clicked.connect(self._on_open_3dmol_smiles)
        smiles_row.addWidget(self.btn_pdbe_smiles)
        pdbe_layout.addLayout(smiles_row)

        smiles_note = QLabel(
            "※ PDBe Mol*는 단백질 PDB 구조 전용입니다. 소분자(리간드) 3D 시각화는 "
            "3Dmol.js 뷰어(Rego & Bhatt 2015)를 사용합니다. 로그인 불필요."
        )
        smiles_note.setStyleSheet(
            "color: #6A1B9A; font-size: 8pt; padding: 4px 8px; background: #F3E5F5; border-radius: 4px;"
        )
        smiles_note.setWordWrap(True)
        pdbe_layout.addWidget(smiles_note)

        complex_row = QHBoxLayout()
        complex_row.addWidget(QLabel("복합체 PDB ID (선택):"))
        self.pdbe_complex_id = QLineEdit()
        self.pdbe_complex_id.setPlaceholderText("도킹 복합체 PDB ID 예: 5KIM")
        self.pdbe_complex_id.setMaximumWidth(200)
        complex_row.addWidget(self.pdbe_complex_id)

        btn_pdbe_complex = QPushButton("복합체 시각화")
        btn_pdbe_complex.setStyleSheet(
            "background: #AD1457; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; border: none;"
        )
        btn_pdbe_complex.clicked.connect(self._on_open_pdbe_complex)
        complex_row.addWidget(btn_pdbe_complex)
        complex_row.addStretch()
        pdbe_layout.addLayout(complex_row)
        layout.addWidget(pdbe_group)

        # ── RCSB 3D 뷰어 (대안) ──────────────────────────────────────────
        rcsb_group = QGroupBox("RCSB 3D 뷰어 (대안)")
        rcsb_layout = QHBoxLayout(rcsb_group)
        btn_rcsb = QPushButton("\U0001F310 RCSB PDB에서 보기")
        btn_rcsb.setStyleSheet(
            "background: #1565C0; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; border: none;"
        )
        btn_rcsb.clicked.connect(self._on_open_rcsb_viewer)
        rcsb_layout.addWidget(btn_rcsb)
        rcsb_layout.addStretch()
        layout.addWidget(rcsb_group)

        # ── PDBe Mol* 사용법 가이드 (D888-W7 신설) ──────────────────────
        # 사용자 피드백: "PDBe Mol 등의 사용법이 기존의 안내 html에서 누락"
        # Rule FF: PDBe Mol* 학술 표준 우선 — 학생용 조작법 안내 의무
        # 인용: Sehnal D. et al. 2021 Nucleic Acids Res 49(W1):W431
        usage_group = QGroupBox("PDBe Mol* 사용법 안내 (학생용)")
        usage_layout = QVBoxLayout(usage_group)
        usage_group.setStyleSheet(
            "QGroupBox { border: 2px solid #7B1FA2; border-radius: 6px; "
            "margin-top: 8px; font-weight: bold; color: #7B1FA2; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )

        usage_text = QLabel(
            "[URL 패턴]\n"
            "  PDB 단백질  : https://www.ebi.ac.uk/pdbe/entry/pdb/{PDB_ID}\n"
            "  AlphaFold구조: https://alphafold.ebi.ac.uk/entry/{UniProt_ID}\n\n"
            "[기본 조작법]\n"
            "  회전   : 좌클릭 + 드래그\n"
            "  줌인/아웃: 마우스 스크롤 (트랙패드: 두 손가락 스크롤)\n"
            "  이동   : 우클릭 + 드래그 (또는 Ctrl + 좌클릭 드래그)\n\n"
            "[표면 표시 전환]\n"
            "  우측 패널 → Components → Polymer → 드롭다운에서:\n"
            "    - ball-and-stick  : 원자/결합 세부 보기\n"
            "    - molecular surface: 분자 표면 채우기\n"
            "    - gaussian surface : 부드러운 전자밀도 표면\n\n"
            "[리간드 하이라이트]\n"
            "  우측 패널 → Components → 리간드(Ligand) 선택 → Focus 클릭\n"
            "  결합 부위 잔기가 자동으로 중심에 위치됩니다.\n\n"
            "[스냅샷 저장]\n"
            "  우측 상단 카메라(Camera) 아이콘 클릭 → 'Screenshot' 선택\n"
            "  PNG 형식으로 현재 뷰 저장 (학술 보고서 사용 권장)\n\n"
            "[ChemGrid 연동 워크플로우]\n"
            "  단계 3 PDB 계산 → 단계 4 결합 데이터 확인\n"
            "  → 단계 5 PDBe Mol* 버튼 클릭 → 브라우저에서 3D 시각화\n"
            "  → 스냅샷 저장 → 단계 6 DryLab Report에 삽입\n\n"
            "[학술 인용 필수]\n"
            "  Sehnal D, Bittrich S, Deshpande M, et al. Mol* Viewer: modern\n"
            "  web app for 3D visualization and analysis of large biomolecular\n"
            "  structures. Nucleic Acids Research, 2021; 49(W1): W431-W437.\n"
            "  DOI: 10.1093/nar/gkab314"
        )
        usage_text.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 9pt; "
            "color: #1A237E; padding: 10px; background: #EDE7F6; "
            "border-radius: 4px; line-height: 1.6;"
        )
        usage_text.setWordWrap(True)
        usage_layout.addWidget(usage_text)
        layout.addWidget(usage_group)

        # ── Rule GG: 자체 3D 뷰어 폴백 배너 (M709) ─────────────────────
        fallback_banner = QLabel(
            "⚠️ ChemGrid 자체 3D 뷰어 (단계 3의 'PDB 다운+3D 뷰어' 버튼): "
            "폴백 모드 — 시각화 한계 있음.\n"
            "학술 논문 수준 분석은 위의 PDBe Mol* 사용 권장.\n"
            "인용 의무: Sehnal D. et al. 2021. Nucleic Acids Res 49(W1):W431 "
            "(DOI: 10.1093/nar/gkab325)"
        )
        fallback_banner.setWordWrap(True)
        fallback_banner.setStyleSheet(
            "background: #FFF9C4; color: #7B3F00; font-size: 8pt; "
            "padding: 6px; border: 1px solid #F0AD4E; border-radius: 3px;"
        )
        layout.addWidget(fallback_banner)

        # ── 비교 표 ─────────────────────────────────────────────────────
        compare_group = QGroupBox("시각화 도구 비교")
        compare_layout = QVBoxLayout(compare_group)
        compare_text = QLabel(
            "PDBe Mol*    : EBI 공식, 전자밀도, 학계 논문 수준 (권장)\n"
            "RCSB Viewer  : Mol* 기반, 시퀀스 연동, PDB 표준\n"
            "AlphaFold EBI: AI 예측 구조, pLDDT 색상"
        )
        compare_text.setStyleSheet(
            "font-family: 'Consolas', monospace; font-size: 9pt; color: #333; "
            "padding: 8px; background: #F5F5F5; border-radius: 4px;"
        )
        compare_layout.addWidget(compare_text)
        layout.addWidget(compare_group)

        layout.addStretch()
        return tab

    # ====================================================================
    # TAB 6: DryLab Report
    # ====================================================================
    def _create_tab6_drylab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel(
            "Step 6: 모든 결과가 DryLab Report에 학술지 양식으로 기록됩니다."
        )
        hint.setStyleSheet(
            "background: #E0F2F1; color: #004D40; font-size: 10pt; font-weight: bold; "
            "padding: 8px; border-radius: 4px; border-left: 4px solid #00695C;"
        )
        layout.addWidget(hint)

        # ── DryLab Report 생성 버튼 ──────────────────────────────────────
        drylab_group = QGroupBox("DryLab Report 생성 (학술지 양식)")
        drylab_layout = QVBoxLayout(drylab_group)

        drylab_desc = QLabel(
            "수용체 선택, PDB 계산, 결합 데이터, 도킹 결과를 학술지 양식으로 자동 생성합니다.\n"
            "전국과학전람회 수준 보고서 — 학술 인용 6건 자동 포함."
        )
        drylab_desc.setStyleSheet("color: #333; font-size: 9pt;")
        drylab_desc.setWordWrap(True)
        drylab_layout.addWidget(drylab_desc)

        self.btn_drylab_report = QPushButton(
            "\U0001F4DD DryLab Report 생성 (AlphaFold + 도킹 + 리드 최적화)"
        )
        self.btn_drylab_report.setStyleSheet(
            "QPushButton { background: #00695C; color: white; font-size: 14px; "
            "font-weight: bold; padding: 14px 28px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #004D40; }"
        )
        self.btn_drylab_report.clicked.connect(self._on_generate_drylab_report)
        drylab_layout.addWidget(self.btn_drylab_report)
        layout.addWidget(drylab_group)

        # ── 섹션 미리보기 ────────────────────────────────────────────────
        sections_group = QGroupBox("Report 포함 섹션 (자동 생성)")
        sections_layout = QVBoxLayout(sections_group)
        sections_text = QTextEdit()
        sections_text.setReadOnly(True)
        sections_text.setMaximumHeight(280)
        sections_text.setHtml(
            "<b>신약개발 통합 분석 보고서</b><br><br>"
            "<b>Section 1.</b> 단백질 정보 (UniProt + pLDDT 분포 차트)<br>"
            "<b>Section 2.</b> 도킹 방법 비교 (Vina 간이 vs AlphaFold 정밀)<br>"
            "<b>Section 3.</b> 리간드 정보 + 유도체별 Affinity 표<br>"
            "<b>Section 4.</b> 결합부위 잔기 표 (5\u00c5)<br>"
            "<b>Section 5.</b> 시각화 링크 (PDBe Mol*)<br>"
            "<b>Section 6.</b> 학생 학습 결론 + 다음 실험 단계<br><br>"
            "<b>References (학술 인용 6건):</b><br>"
            "1. Jumper J. et al. 2021. Nature 596:583 (AlphaFold2)<br>"
            "2. Trott O &amp; Olson AJ. 2010. J Comput Chem 31:455 (Vina)<br>"
            "3. Sehnal D. et al. 2021. Nucleic Acids Res 49:W431 (PDBe Mol*)<br>"
            "4. Gilson MK &amp; Zhou HX. 2007. Annu Rev Biophys 36:21 (5\u00c5)<br>"
            "5. Liu K. et al. 2019. J Med Chem 62:9583 (pLDDT 가중)<br>"
            "6. Hopkins AL. 2007. Nature Chem Biol 3:683 (Drug-likeness)<br>"
        )
        sections_layout.addWidget(sections_text)
        layout.addWidget(sections_group)

        self.drylab_status_label = QLabel("DryLab Report: 대기 중")
        self.drylab_status_label.setStyleSheet("color: #555; font-size: 9pt; padding: 4px;")
        layout.addWidget(self.drylab_status_label)

        layout.addStretch()
        return tab

    # ================================================================
    # SLOTS
    # ================================================================

    def _on_tab_changed(self, index: int):
        """탭 전환 시 상태바 안내 갱신."""
        messages = [
            "Step 1: 도킹 시뮬할 단백질을 선택합니다.",
            "Step 2: AlphaFold DB에서 단백질의 예시 구조를 확인합니다.",
            "Step 3: AlphaFold AI가 단백질 3D 구조를 예측합니다.",
            "Step 4: 예측 결과 데이터로 결합 양상을 학습합니다.",
            "Step 5: PDBe Mol*로 단백질+리간드 복합체를 시각화합니다 (학계 표준).",
            "Step 6: 모든 결과가 DryLab Report에 학술지 양식으로 기록됩니다.",
        ]
        if 0 <= index < len(messages):
            self.status_label.setText(messages[index])

    def _on_receptor_changed(self, index: int):
        """수용체 드롭다운 변경 — UniProt/PDB 자동 채움."""
        if index < 0 or index >= len(_RECEPTOR_PRESETS):
            logger.warning("_on_receptor_changed: 잘못된 인덱스: %d", index)
            return
        preset = _RECEPTOR_PRESETS[index]
        if not isinstance(preset, dict):
            logger.warning("_on_receptor_changed: preset dict 아님: %s", type(preset).__name__)
            return

        self._selected_receptor = preset
        if hasattr(self, 'uniprot_id_input'):
            self.uniprot_id_input.setText(preset.get("uniprot", ""))
        if hasattr(self, 'pdb_id_input'):
            self.pdb_id_input.setText(preset.get("pdb_id", ""))
        if hasattr(self, 'receptor_desc'):
            self.receptor_desc.setText(preset.get("description", ""))

    def _on_fasta_text_changed(self):
        """[M460 보존] FASTA 입력 변경 시 UniProt ID 자동 추출."""
        if not hasattr(self, 'seq_input'):
            return
        fasta_text = self.seq_input.toPlainText().strip()
        if not fasta_text:
            return
        if hasattr(self, 'uniprot_id_input') and not self.uniprot_id_input.text().strip():
            extracted = self._extract_uniprot_from_fasta(fasta_text)
            if extracted:
                self.uniprot_id_input.setText(extracted)
                logger.info("_on_fasta_text_changed: UniProt ID 자동 채움: %s", extracted)

    def _on_open_alphafold_external(self):
        """[M460 보존] AlphaFold EBI 공식 DB 외부 링크 열기.

        M455: AlphaFold v4 URL (https://alphafold.ebi.ac.uk/entry/)
        Rule M: UniProt ID 없을 시 사용자 피드백 (silent return 금지).
        """
        uid = ""
        if hasattr(self, 'uniprot_id_input'):
            uid = self.uniprot_id_input.text().strip().upper()

        if not uid:
            if hasattr(self, 'seq_input'):
                fasta_text = self.seq_input.toPlainText().strip()
                uid = self._extract_uniprot_from_fasta(fasta_text)
                if uid and hasattr(self, 'uniprot_id_input'):
                    self.uniprot_id_input.setText(uid)

        if not uid:
            # [M852 격분 #30] UniProt 없어도 메인 페이지 대신 검색 페이지 열기
            # 사용자: "입력까지 완료된 링크가 나와야지"
            preset = getattr(self, '_selected_receptor', {})
            receptor_name = preset.get("name", "") if isinstance(preset, dict) else ""
            url = _get_alphafold_search_url("", receptor_name)
            logger.info("_on_open_alphafold_external: UniProt 없음 → 검색 URL: %s", url)
            QDesktopServices.openUrl(QUrl(url))
            return

        # [M852 격분 #30] UniProt ID 있으면 entry 직접 URL (가장 정확)
        url = _get_alphafold_search_url(uid)
        logger.info("_on_open_alphafold_external: %s", url)
        QDesktopServices.openUrl(QUrl(url))

    def _on_open_alphafold_search(self):
        """[M852 격분 #30] AlphaFold 입력 완료 검색 링크 열기.

        사용자: "알파폴드는 그냥 메인 웹사이트만 나오노 아니 입력까지 완료된 링크가 나와야지"
        해결: 수용체 선택 → UniProt ID 추출 → 검색 또는 entry 직접 URL 생성.
        Rule M: silent failure 금지.
        Rule N: isinstance 타입 가드.
        Jumper J et al. Nature 2021;596:583 (AlphaFold2)
        """
        uid = ""
        if hasattr(self, 'uniprot_id_input'):
            uid = self.uniprot_id_input.text().strip().upper()

        preset = getattr(self, '_selected_receptor', {})
        receptor_name = preset.get("name", "") if isinstance(preset, dict) else ""

        url = _get_alphafold_search_url(uid, receptor_name)
        logger.info("_on_open_alphafold_search: %s", url)
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            logger.warning("_on_open_alphafold_search 브라우저 열기 실패: %s", e)
            QMessageBox.warning(
                self, "브라우저 열기 실패",
                f"AlphaFold 검색 링크 열기 실패: {e}\n수동 접속: {url}"
            )

    def _on_open_3dmol_smiles(self):
        """[M852 격분 #30] 사용자 SMILES → 3Dmol.js 3D 뷰어 열기.

        사용자: "PDBe Mol은 내 분자를 직접 넣어줄수는 없는거냐?"
        해결: 3Dmol.js 공개 뷰어 (SMILES URL 파라미터 지원, 로그인 불필요).
        Rule L: SMILES 유효성 체크.
        Rule M: 빈 SMILES → 사용자 안내.
        Rule N: isinstance 타입 가드.
        """
        smiles = ""
        if hasattr(self, 'pdbe_smiles_input'):
            smiles = self.pdbe_smiles_input.text().strip()

        # 비어있으면 현재 팝업에 전달된 리간드 SMILES 사용
        if not smiles and hasattr(self, '_ligand_smiles') and self._ligand_smiles:
            smiles = self._ligand_smiles

        if not isinstance(smiles, str) or not smiles:
            logger.warning("_on_open_3dmol_smiles: SMILES 없음")
            QMessageBox.information(
                self, "SMILES 입력 필요",
                "SMILES를 입력하세요.\n\n"
                "예: CC(=O)Oc1ccccc1C(=O)O (아스피린)\n"
                "    NCCc1c[nH]cn1 (히스타민)\n\n"
                "ChemGrid 캔버스에서 분자를 그리면 자동으로 입력됩니다."
            )
            return

        url = _get_molstar_smiles_url(smiles)
        if not url:
            logger.warning("_on_open_3dmol_smiles: URL 생성 실패 (smiles=%r)", smiles)
            QMessageBox.warning(self, "URL 생성 실패",
                                f"'{smiles}' 에 대한 3D 뷰어 URL 생성 실패.")
            return

        logger.info("_on_open_3dmol_smiles: %s", url)
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            logger.warning("_on_open_3dmol_smiles 브라우저 열기 실패: %s", e)
            QMessageBox.warning(
                self, "브라우저 열기 실패",
                f"3D 뷰어 열기 실패: {e}\n수동 접속: {url}"
            )

    def _on_open_alphafold_pdbe_molstar(self):
        """[M647-W4 USR-LV4-08] PDBe Mol* 3D 뷰어로 AlphaFold 구조 표시.

        사용자 격분 LV.4 직격: "메인사이트만 쳐 나옴 / 3D 구조 안 나옴"
        해결: PDBe Mol* iframe URL — `af-pdb-id={UniProt}` 파라미터로 자동 표시
        Rule FF: PDBe Mol* 학술 표준 우선 (Sehnal D et al. NAR 2021;49:W431)
        Rule M: silent failure 금지 — UniProt ID 없으면 사용자 안내
        Rule N: isinstance + UniProt 정규식 가드
        """
        import re as _re
        uid = ""
        if hasattr(self, 'uniprot_id_input'):
            uid = self.uniprot_id_input.text().strip().upper()
        if not uid:
            if hasattr(self, 'seq_input'):
                fasta_text = self.seq_input.toPlainText().strip()
                uid = self._extract_uniprot_from_fasta(fasta_text)
                if uid and hasattr(self, 'uniprot_id_input'):
                    self.uniprot_id_input.setText(uid)
        if not uid:
            logger.warning("_on_open_alphafold_pdbe_molstar: UniProt ID 부재")
            QMessageBox.information(
                self, "UniProt ID 필요",
                "UniProt ID를 입력하세요 (예: P00533, P12345).\n"
                "PDBe Mol* 3D 뷰어가 해당 단백질을 자동 표시합니다."
            )
            return
        # Rule N: UniProt 정규식 가드 ^[OPQA-Z][0-9][A-Z0-9]{3}[0-9]$
        if not _re.fullmatch(r'^[OPQA-Z][0-9][A-Z0-9]{3}[0-9]$', uid):
            logger.warning(
                "_on_open_alphafold_pdbe_molstar: UniProt 정규식 불일치: %s", uid)
            QMessageBox.warning(
                self, "UniProt ID 형식 오류",
                f"UniProt ID '{uid}' 형식 불일치.\n"
                "올바른 형식: P00533, Q9NZN9 등"
            )
            return
        # [M685 FIX / A55-COND-FIX] ISSUE-1: PDBe Mol* af-pdb-id URL 404 해소
        # 변경 전: /pdbe/molstar/?af-pdb-id={uid} → HTTPError (URL 변경됨, 2026 기준)
        # 변경 후: /pdbe/entry/alphafold/{uid} — UniProt ID 전용 AlphaFold entry 페이지
        # 실측 검증: https://www.ebi.ac.uk/pdbe/entry/alphafold/P00533 → HTTP 200 (2026-05-04)
        # 학술 인용 (Rule NN): Sehnal D. et al. 2021 Nucleic Acids Res 49:W431 (PDBe Mol*)
        # [MAGIC] /pdbe/entry/alphafold/ — AlphaFold UniProt ID 전용 PDBe entry endpoint
        url = f"https://www.ebi.ac.uk/pdbe/entry/alphafold/{uid}"
        logger.info("_on_open_alphafold_pdbe_molstar: %s", url)
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            logger.warning("PDBe Mol* 외부 열기 실패: %s", e)
            QMessageBox.warning(
                self, "외부 브라우저 열기 실패",
                f"PDBe Mol* 외부 링크 열기 실패: {e}\n"
                f"수동으로 접속: {url}"
            )

    def _on_download_alphafold_pdb(self):
        """[M647-W4 USR-LV4-08] AlphaFold PDB 직접 다운 + 자체 3D 뷰어 표시.

        사용자 격분 LV.4 직격: "메인사이트만 쳐 나옴 / 리본 변환 안 됨"
        해결: alphafold.ebi.ac.uk/files/AF-{uid}-F1-model_v6.pdb 직접 다운
              → ChemGrid 자체 3D 뷰어로 표시 (carton/cartoon ribbon 모드)
        학술 인용 (Rule NN): Jumper J et al. Nature 2021;596:583 (AlphaFold v6)
        Rule M: HTTP 실패 silent return 금지 — logger.warning + QMessageBox
        Rule N: isinstance + UniProt 정규식 가드
        """
        import re as _re
        import tempfile
        import urllib.request as _urlreq
        import urllib.error as _urlerr
        uid = ""
        if hasattr(self, 'uniprot_id_input'):
            uid = self.uniprot_id_input.text().strip().upper()
        if not uid:
            logger.warning("_on_download_alphafold_pdb: UniProt ID 부재")
            QMessageBox.information(
                self, "UniProt ID 필요",
                "UniProt ID를 입력하세요 (예: P00533).\n"
                "AlphaFold v6 PDB 파일을 다운로드합니다."
            )
            return
        # Rule N: UniProt 정규식 가드
        if not _re.fullmatch(r'^[OPQA-Z][0-9][A-Z0-9]{3}[0-9]$', uid):
            QMessageBox.warning(
                self, "UniProt ID 형식 오류", f"UniProt ID '{uid}' 형식 불일치.")
            return
        # [MAGIC] AlphaFold v6 모델 — 2024+ 학술 표준
        url = f"https://alphafold.ebi.ac.uk/files/AF-{uid}-F1-model_v6.pdb"
        logger.info("_on_download_alphafold_pdb: %s", url)
        try:
            # [MAGIC] 30s timeout — 단백질 PDB 일반 < 5MB
            with _urlreq.urlopen(url, timeout=30) as resp:
                pdb_bytes = resp.read()
            if not pdb_bytes or not pdb_bytes.startswith(b"HEADER"):
                # v6 미존재 시 v5/v4 fallback
                for ver in ("v5", "v4"):
                    fb_url = f"https://alphafold.ebi.ac.uk/files/AF-{uid}-F1-model_{ver}.pdb"
                    try:
                        with _urlreq.urlopen(fb_url, timeout=30) as resp:
                            pdb_bytes = resp.read()
                        if pdb_bytes and pdb_bytes.startswith(b"HEADER"):
                            url = fb_url
                            break
                    except Exception:
                        continue
            if not pdb_bytes or not pdb_bytes.startswith(b"HEADER"):
                raise ValueError("PDB 응답 형식 오류 (HEADER 없음)")
        except _urlerr.HTTPError as he:
            logger.warning(
                "_on_download_alphafold_pdb HTTPError %s: %s", he.code, url)
            QMessageBox.warning(
                self, "다운로드 실패",
                f"AlphaFold PDB 다운로드 실패 (HTTP {he.code}).\n"
                f"UniProt ID '{uid}'에 대한 모델이 없을 수 있습니다.\n"
                f"메인 사이트에서 확인: https://alphafold.ebi.ac.uk/entry/{uid}"
            )
            return
        except (_urlerr.URLError, ValueError, Exception) as e:
            logger.warning("_on_download_alphafold_pdb 오류: %s", e)
            QMessageBox.warning(
                self, "다운로드 오류",
                f"AlphaFold PDB 다운로드 오류: {e}\n"
                f"수동으로 접속: https://alphafold.ebi.ac.uk/entry/{uid}"
            )
            return
        # 임시 PDB 파일 저장
        try:
            tmp_dir = Path(tempfile.gettempdir()) / "chemgrid_alphafold"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            pdb_path = tmp_dir / f"AF-{uid}.pdb"
            pdb_path.write_bytes(pdb_bytes)
        except OSError as e:
            logger.warning("PDB 파일 저장 실패: %s", e)
            QMessageBox.warning(
                self, "파일 저장 실패", f"PDB 파일 저장 실패: {e}")
            return
        logger.info(
            "_on_download_alphafold_pdb 다운 완료: %s (%d bytes)",
            pdb_path, len(pdb_bytes),
        )
        # 자체 3D 뷰어 표시 — docking_3d_viewer 또는 외부 브라우저 fallback
        try:
            from docking_3d_viewer import Docking3DViewer
            viewer = Docking3DViewer(parent=self)
            # [M709 Rule GG] 창 제목 — 폴백 워터마크 의무
            viewer.setWindowTitle(
                f"AlphaFold 3D — {uid} [ChemGrid 자체 뷰어 — 폴백]"
            )
            if hasattr(viewer, 'load_pdb_file'):
                viewer.load_pdb_file(str(pdb_path))
            elif hasattr(viewer, 'load_pdb'):
                viewer.load_pdb(str(pdb_path))
            else:
                # fallback: PDB 텍스트 첨부 시도
                if hasattr(viewer, 'set_pdb_text'):
                    viewer.set_pdb_text(pdb_bytes.decode('utf-8', errors='replace'))
            # [M709 Rule GG] set_simulation_mode_label 호출 (폴백 표시)
            if hasattr(viewer, 'set_simulation_mode_label'):
                viewer.set_simulation_mode_label(
                    "⚠️ ChemGrid 자체 3D 뷰어 (폴백 모드) — 학술 표준: PDBe Mol* 사용 권장"
                )
            viewer.resize(1000, 750)
            viewer.show()
            # [M709 Rule GG] QMessageBox: PDBe Mol* 사용 권장 + Sehnal 2021 인용
            QMessageBox.information(
                self, "AlphaFold 3D 뷰어 (폴백)",
                f"AlphaFold {uid} PDB 다운 완료 ({len(pdb_bytes):,} bytes)\n\n"
                f"[ChemGrid 자체 3D 뷰어 — 폴백 모드]\n"
                f"학술 논문 제출 시 PDBe Mol* 사용 권장:\n"
                f"  https://www.ebi.ac.uk/pdbe/entry/alphafold/{uid}\n\n"
                f"인용 의무 (Rule FF):\n"
                f"  Sehnal D. et al. 2021. Nucleic Acids Res 49(W1):W431\n"
                f"  DOI: 10.1093/nar/gkab325\n\n"
                f"3D 뷰어에서 리본/카툰 모드 등을 사용하세요."
            )
        except ImportError:
            logger.warning("Docking3DViewer not available — 외부 브라우저 폴백")
            # fallback: 파일 시스템 PDB 직접 열기 (사용자 OS의 기본 뷰어)
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdb_path)))
                QMessageBox.information(
                    self, "AlphaFold PDB 다운 완료",
                    f"PDB 다운: {pdb_path}\n"
                    f"3D 뷰어를 직접 열거나, PyMOL/ChimeraX/VMD에서 열어보세요."
                )
            except Exception as e:
                logger.warning("PDB 외부 열기 실패: %s", e)
                QMessageBox.warning(
                    self, "PDB 표시 실패",
                    f"PDB 다운 완료 ({pdb_path})\n3D 뷰어 실행 실패: {e}"
                )
        except Exception as e:
            logger.warning("3D 뷰어 표시 오류: %s", e)
            QMessageBox.warning(
                self, "3D 뷰어 오류", f"3D 뷰어 표시 실패: {e}\nPDB: {pdb_path}")

    def _on_calc_pdb(self):
        """PDB 계산 시작."""
        if not ALPHAFOLD_AVAILABLE:
            logger.warning("_on_calc_pdb: alphafold_interface 없음")
            QMessageBox.warning(
                self, "모듈 없음",
                "alphafold_interface 모듈이 없습니다.\n"
                "PDB ID 직접 다운로드를 사용하세요."
            )
            return

        uid = self.uniprot_id_input.text().strip() if hasattr(self, 'uniprot_id_input') else ""
        pdb_id = self.pdb_id_input.text().strip().upper() if hasattr(self, 'pdb_id_input') else ""

        if not uid and not pdb_id:
            logger.warning("_on_calc_pdb: UniProt ID와 PDB ID 모두 없음")
            QMessageBox.warning(
                self, "입력 필요",
                "UniProt ID 또는 PDB ID를 입력하세요.\n"
                "Step 1에서 수용체를 선택하면 자동으로 채워집니다."
            )
            return

        self._start_prediction(pdb_id=pdb_id)

    def _on_fetch_pdb_direct(self):
        """RCSB PDB 직접 다운로드."""
        if not ALPHAFOLD_AVAILABLE:
            QMessageBox.warning(self, "오류", "alphafold_interface 모듈이 없습니다.")
            return
        pdb_id = self.pdb_direct_input.text().strip().upper() if hasattr(self, 'pdb_direct_input') else ""
        if not pdb_id:
            QMessageBox.warning(self, "오류", "PDB ID를 입력하세요.")
            return
        if not re.match(r"^[A-Z0-9]{4}$", pdb_id):
            logger.warning("잘못된 PDB ID 형식: %s", pdb_id)
            QMessageBox.warning(self, "형식 오류", f"PDB ID는 4자리 영숫자여야 합니다. 입력: '{pdb_id}'")
            return
        self._start_prediction(pdb_id=pdb_id)

    def _start_prediction(self, sequence: str = "", pdb_id: str = ""):
        """Background prediction thread 시작."""
        logger.info("AlphaFold 계산 시작: sequence=%s, pdb_id=%s",
                     f"{len(sequence)}chars" if sequence else "없음", pdb_id or "없음")
        if hasattr(self, 'btn_calc_pdb'):
            self.btn_calc_pdb.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("구조 계산 중...")
        if hasattr(self, 'calc_status_label'):
            self.calc_status_label.setText("AlphaFold API 요청 중...")

        self._worker = _PredictionWorker(sequence=sequence, pdb_id=pdb_id, parent=self)
        self._worker.finished.connect(self._on_prediction_done)
        self._worker.progress.connect(self._on_progress_msg)
        self._worker.start()

    def _on_progress_msg(self, msg: str):
        self.status_label.setText(msg)
        if hasattr(self, 'calc_status_label'):
            self.calc_status_label.setText(msg)

    def _on_prediction_done(self, result):
        """AlphaFold 계산 결과 처리."""
        self.progress_bar.hide()
        if hasattr(self, 'btn_calc_pdb'):
            self.btn_calc_pdb.setEnabled(True)

        # Rule N: 타입 가드
        if not hasattr(result, 'success'):
            logger.warning("_on_prediction_done: 예상치 못한 결과 타입: %s", type(result).__name__)
            self.status_label.setText("오류: 예상치 못한 응답 형식")
            return

        if not result.success:
            logger.warning("AlphaFold 실패: %s", result.error)
            self.status_label.setText(f"실패: {result.error}")
            if hasattr(self, 'calc_status_label'):
                self.calc_status_label.setText(f"실패: {result.error}")
            QMessageBox.warning(self, "계산 실패", result.error)
            return

        self._prediction_result = result
        self._structure = result.structure

        n_residues = len(self._structure.residues) if self._structure else 0
        mean_plddt = getattr(self._structure, 'mean_plddt', 0.0)
        method = getattr(result, 'method', 'AlphaFold')
        elapsed = getattr(result, 'elapsed_seconds', None)
        elapsed_str = f"{elapsed:.1f}s" if elapsed else ""

        summary = (
            f"완료 ({method}) {elapsed_str} | "
            f"잔기 {n_residues}개 | 평균 pLDDT: {mean_plddt:.1f}"
        )
        self.status_label.setText(summary)
        self.status_label.setStyleSheet("color: #2e7d32; padding: 2px; font-size: 9pt;")
        if hasattr(self, 'calc_status_label'):
            self.calc_status_label.setText(summary)
        if hasattr(self, 'calc_result_label'):
            self.calc_result_label.setText(summary)

        for i in range(2, 6):
            self.tabs.setTabEnabled(i, True)

        self._populate_residue_table()
        self._draw_plddt_chart()
        self.tabs.setCurrentIndex(3)

    # ------------------------------------------------------------------ 데이터 채움

    def _draw_plddt_chart(self):
        """pLDDT 분포 차트 (4구간 — Jumper 2021)."""
        if not MATPLOTLIB_AVAILABLE or not hasattr(self, 'plddt_fig'):
            return
        if self._structure is None:
            logger.debug("_draw_plddt_chart: 구조 없음")
            return
        try:
            residues = self._structure.residues
            if not residues:
                logger.warning("_draw_plddt_chart: 잔기 없음")
                return

            plddt_vals = [getattr(r, 'plddt', 0.0) for r in residues]
            seq_nums = [getattr(r, 'seq_num', i + 1) for i, r in enumerate(residues)]

            self.plddt_fig.clear()
            ax = self.plddt_fig.add_subplot(111)

            colors_bar = []
            for v in plddt_vals:
                if v >= 90:
                    colors_bar.append(_PLDDT_HEX["very_high"])
                elif v >= 70:
                    colors_bar.append(_PLDDT_HEX["high"])
                elif v >= 50:
                    colors_bar.append(_PLDDT_HEX["low"])
                else:
                    colors_bar.append(_PLDDT_HEX["very_low"])

            ax.bar(seq_nums, plddt_vals, color=colors_bar, width=1.0, alpha=0.85)
            ax.axhline(y=90, color=_PLDDT_HEX["very_high"], linestyle='--', linewidth=0.8, alpha=0.7)
            ax.axhline(y=70, color='#888', linestyle='--', linewidth=0.8, alpha=0.7)
            ax.axhline(y=50, color=_PLDDT_HEX["very_low"], linestyle='--', linewidth=0.8, alpha=0.7)

            ax.set_xlabel("잔기 번호 (Residue Index)", fontsize=9,
                          fontproperties=_MPL_KR_FONT)
            ax.set_ylabel("pLDDT 신뢰도", fontsize=9,
                          fontproperties=_MPL_KR_FONT)
            ax.set_title(
                "pLDDT 분포 (AlphaFold2 — Jumper et al. 2021 Nature 596:583)",
                fontsize=9, fontproperties=_MPL_KR_FONT
            )
            ax.set_ylim(0, 105)
            ax.grid(axis='y', alpha=0.3)

            from matplotlib.patches import Patch
            legend_items = [
                Patch(color=_PLDDT_HEX["very_high"], label="Very high (>=90)"),
                Patch(color=_PLDDT_HEX["high"],      label="Confident (70-90)"),
                Patch(color=_PLDDT_HEX["low"],       label="Low (50-70)"),
                Patch(color=_PLDDT_HEX["very_low"],  label="Very low (<50)"),
            ]
            ax.legend(handles=legend_items, loc='lower right', fontsize=7, ncol=2)
            self.plddt_canvas.draw()

            n_vh = sum(1 for v in plddt_vals if v >= 90)
            n_h  = sum(1 for v in plddt_vals if 70 <= v < 90)
            n_l  = sum(1 for v in plddt_vals if 50 <= v < 70)
            n_vl = sum(1 for v in plddt_vals if v < 50)
            total = len(plddt_vals)
            mean_v = sum(plddt_vals) / total if total > 0 else 0.0
            if hasattr(self, 'plddt_stats_label'):
                self.plddt_stats_label.setText(
                    f"총 잔기: {total}  |  평균 pLDDT: {mean_v:.1f}  |  "
                    f"Very high: {n_vh}  Confident: {n_h}  Low: {n_l}  Very low: {n_vl}"
                )
        except Exception as e:
            logger.warning("_draw_plddt_chart 실패: %s", e)

    def _populate_residue_table(self):
        """잔기 분석 테이블 채움 (M440 보존)."""
        if self._structure is None:
            logger.debug("_populate_residue_table: 구조 없음")
            return

        residues = self._structure.residues
        if not isinstance(residues, (list, tuple)):
            logger.warning("_populate_residue_table: residues가 list/tuple 아님: %s",
                           type(residues).__name__)
            return
        if not residues:
            if hasattr(self, 'residue_summary'):
                self.residue_summary.setText("잔기 데이터가 없습니다.")
            return

        if ALPHAFOLD_AVAILABLE:
            try:
                analysis = filter_by_plddt(self._structure)
                if not isinstance(analysis, dict):
                    logger.warning("_populate_residue_table: filter_by_plddt 반환이 dict 아님: %s",
                                   type(analysis).__name__)
                    analysis = {}
                cats = analysis.get("categories", {})
                if not isinstance(cats, dict):
                    logger.warning("_populate_residue_table: categories가 dict 아님")
                    cats = {}
                total = analysis.get("total_residues", 0)
                mean_p = analysis.get("mean_plddt", 0.0)
                high_pct = 0.0
                if total > 0:
                    high_pct = (cats.get("very_high", 0) + cats.get("high", 0)) / total * 100
                if hasattr(self, 'residue_summary'):
                    self.residue_summary.setText(
                        f"총 잔기: {total}  |  평균 pLDDT: {mean_p:.1f}  |  "
                        f"고신뢰도(>70): {high_pct:.1f}%  |  "
                        f"Very high: {cats.get('very_high', 0)}  "
                        f"Confident: {cats.get('high', 0)}  "
                        f"Low: {cats.get('low', 0)}  Very low: {cats.get('very_low', 0)}"
                    )
            except Exception as e:
                logger.warning("_populate_residue_table: filter_by_plddt 실패: %s", e)
                if hasattr(self, 'residue_summary'):
                    self.residue_summary.setText(f"총 잔기: {len(residues)}개")
        else:
            if hasattr(self, 'residue_summary'):
                self.residue_summary.setText(f"총 잔기: {len(residues)}개")

        if not hasattr(self, 'residue_table'):
            return
        self.residue_table.setRowCount(len(residues))
        for row, res in enumerate(residues):
            plddt_val = getattr(res, 'plddt', 0.0)
            cat_kr, cat_en, hex_color = _plddt_category(plddt_val)
            bg = QColor(hex_color) if PYQT_AVAILABLE else None

            items_data = [
                str(getattr(res, 'seq_num', row + 1)),
                getattr(res, 'name', '?'),
                getattr(res, 'chain_id', 'A'),
                f"{plddt_val:.1f}",
                f"{cat_kr} ({cat_en})",
            ]
            for col, text in enumerate(items_data):
                item = QTableWidgetItem(text)
                if bg is not None:
                    item.setBackground(bg)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.residue_table.setItem(row, col, item)

    def _on_extract_binding_site(self):
        """결합부위 추출 (M440 보존 — 5Å, Gilson 2007)."""
        if not ALPHAFOLD_AVAILABLE or self._structure is None:
            QMessageBox.warning(self, "오류", "먼저 PDB 계산을 완료하세요.")
            return

        radius = self.bind_radius.value()
        ref_seq = self.bind_ref_residue.value()
        chain_id = self.bind_chain.text().strip() or "A"

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
            logger.warning("_on_extract_binding_site: 기준 잔기 %s:%d 없음", chain_id, ref_seq)
            QMessageBox.warning(self, "오류", f"잔기 {chain_id}:{ref_seq}을 찾을 수 없습니다.")
            return

        result = extract_binding_site(self._structure, center=center, radius=radius)
        if not isinstance(result, dict):
            logger.warning("_on_extract_binding_site: dict 아님: %s", type(result).__name__)
            QMessageBox.warning(self, "오류", "결합부위 추출 결과가 올바르지 않습니다.")
            return

        n_res = result.get("n_residues", 0)
        n_atoms = result.get("n_atoms", 0)
        if hasattr(self, 'binding_summary'):
            self.binding_summary.setText(
                f"기준: {chain_id}:{ref_seq}  |  "
                f"반경: {radius:.1f}\u00c5 (Gilson 2007)  |  "
                f"잔기: {n_res}개, 원자: {n_atoms}개"
            )

        res_map: Dict = {}
        cx, cy, cz = center
        atoms_list = result.get("atoms", [])
        if not isinstance(atoms_list, list):
            logger.warning("_on_extract_binding_site: atoms가 list 아님: %s",
                           type(atoms_list).__name__)
            atoms_list = []
        for atom in atoms_list:
            key = (getattr(atom, 'chain_id', 'A'), getattr(atom, 'res_seq', 0))
            dist = math.sqrt(
                (atom.x - cx) ** 2 + (atom.y - cy) ** 2 + (atom.z - cz) ** 2
            )
            if key not in res_map or dist < res_map[key][1]:
                res_map[key] = (getattr(atom, 'res_name', '?'), dist)

        sorted_res = sorted(res_map.items(), key=lambda x: x[1][1])
        if not hasattr(self, 'binding_table'):
            return
        self.binding_table.setRowCount(len(sorted_res))
        for row, ((chain, seq), (name, dist)) in enumerate(sorted_res):
            items_data = [name, str(seq), chain, f"{dist:.2f}"]
            for col, text in enumerate(items_data):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.binding_table.setItem(row, col, item)

    def set_docking_results(self, docking_data: List[Dict]):
        """도킹 결과 수신 (M461 통합 흐름 보존).

        Args:
            docking_data: [{"name": str, "smiles": str, "affinity": float, "plddt_weight": float}]
        """
        if not isinstance(docking_data, list):
            logger.warning("set_docking_results: list 아님: %s", type(docking_data).__name__)
            return
        self._docking_results = docking_data
        if not hasattr(self, 'docking_table'):
            return
        self.docking_table.setRowCount(len(docking_data))
        for row, entry in enumerate(docking_data):
            if not isinstance(entry, dict):
                logger.warning("set_docking_results: 항목 %d가 dict 아님", row)
                continue
            items_data = [
                entry.get("name", f"유도체 {row+1}"),
                entry.get("smiles", ""),
                f"{entry.get('affinity', 0.0):.2f} kcal/mol",
                f"{entry.get('plddt_weight', 0.0):.1f}",
            ]
            for col, text in enumerate(items_data):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.docking_table.setItem(row, col, item)

    # ------------------------------------------------------------------ PDBe Mol*

    def _on_open_pdbe_mol(self):
        """PDBe Mol* 외부 링크 (Sehnal 2021).

        URL: https://www.ebi.ac.uk/pdbe/molstar/embed/?pdb={pdb_id}
        Rule M: PDB ID 없을 시 사용자 피드백.
        """
        pdb_id = self.pdb_id_input.text().strip().upper() if hasattr(self, 'pdb_id_input') else ""
        if not pdb_id and hasattr(self, 'pdb_direct_input'):
            pdb_id = self.pdb_direct_input.text().strip().upper()

        if not pdb_id:
            logger.warning("_on_open_pdbe_mol: PDB ID 없음")
            QMessageBox.information(
                self, "PDB ID 필요",
                "PDB ID가 설정되지 않았습니다.\n"
                "Step 1에서 수용체를 선택하거나 Step 3에서 PDB ID를 입력하세요.\n"
                "예: 5IKT (COX-2), 4PE5 (NMDA), 1IVO (EGFR)"
            )
            return

        # [M675 FIX] PDBe Mol* embed URL 404 해소 — 사용자 LV.14 item 9 격분
        # 변경 전: /pdbe/molstar/embed/?pdb={id} → 404 (URL 변경됨)
        # 변경 후: /pdbe/entry/pdb/{id} (PDBe entry, Mol* 임베드된 페이지) — 학술 표준
        # 백업 fallback: molstar.org/viewer (공식 Mol* 뷰어, Sehnal 2021)
        # 학술 인용 (Rule NN): Sehnal D. et al. 2021 Nucleic Acids Res 49:W431
        url = f"https://www.ebi.ac.uk/pdbe/entry/pdb/{pdb_id.lower()}"
        logger.info("_on_open_pdbe_mol: %s", url)
        QDesktopServices.openUrl(QUrl(url))

    def _on_open_pdbe_complex(self):
        """복합체 PDB ID로 PDBe Mol* 열기."""
        complex_id = self.pdbe_complex_id.text().strip().upper() if hasattr(self, 'pdbe_complex_id') else ""
        if not complex_id:
            self._on_open_pdbe_mol()
            return
        if not re.match(r"^[A-Z0-9]{4}$", complex_id):
            QMessageBox.warning(self, "형식 오류", "복합체 PDB ID는 4자리 영숫자여야 합니다.")
            return
        # [M675 FIX] PDBe entry URL 사용 (embed 404 해소). Sehnal 2021.
        url = f"https://www.ebi.ac.uk/pdbe/entry/pdb/{complex_id.lower()}"
        logger.info("_on_open_pdbe_complex: %s", url)
        QDesktopServices.openUrl(QUrl(url))

    def _on_open_rcsb_viewer(self):
        """RCSB 3D 뷰어 외부 링크."""
        pdb_id = self.pdb_id_input.text().strip().upper() if hasattr(self, 'pdb_id_input') else ""
        if not pdb_id:
            logger.warning("_on_open_rcsb_viewer: PDB ID 없음")
            QMessageBox.information(self, "알림", "PDB ID를 먼저 입력하세요.")
            return
        url = f"https://www.rcsb.org/3d-view/{pdb_id}"
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------------ DryLab

    def _on_generate_drylab_report(self):
        """DryLab Report 생성 연동.

        Rule M: 데이터 없을 시 사용자 피드백.
        """
        try:
            from drylab_report_exporter import DryLabData, export_drylab_report_pdf
        except ImportError as e:
            logger.warning("_on_generate_drylab_report: 임포트 실패: %s", e)
            QMessageBox.warning(self, "오류", f"drylab_report_exporter 임포트 실패:\n{e}")
            return

        smiles = self.ligand_smiles_input.text().strip() if hasattr(self, 'ligand_smiles_input') else ""
        receptor_info = {
            "name":     self._selected_receptor.get("name", ""),
            "uniprot":  self.uniprot_id_input.text().strip() if hasattr(self, 'uniprot_id_input') else "",
            "pdb_id":   self.pdb_id_input.text().strip() if hasattr(self, 'pdb_id_input') else "",
        }

        if not smiles and self._structure is None:
            logger.warning("_on_generate_drylab_report: SMILES와 구조 데이터 모두 없음")
            QMessageBox.warning(
                self, "데이터 없음",
                "최소 하나의 데이터가 필요합니다.\n"
                "- 리간드 SMILES: Step 1에서 입력\n"
                "- 단백질 구조: Step 3에서 PDB 계산 완료"
            )
            return

        if hasattr(self, 'drylab_status_label'):
            self.drylab_status_label.setText("DryLab Report 생성 중...")

        try:
            drylab_data = DryLabData(
                smiles=smiles,
                receptor_info=receptor_info,
                structure=self._structure,
                docking_results=self._docking_results,
            )
            pdf_path = export_drylab_report_pdf(drylab_data)
            if pdf_path and os.path.exists(pdf_path):
                if hasattr(self, 'drylab_status_label'):
                    self.drylab_status_label.setText(f"완료: {pdf_path}")
                logger.info("_on_generate_drylab_report: %s", pdf_path)
                QMessageBox.information(self, "완료", f"DryLab Report 생성:\n{pdf_path}")
            else:
                logger.warning("_on_generate_drylab_report: PDF 없음: %s", pdf_path)
                QMessageBox.warning(self, "경고", "PDF 생성 결과 파일을 확인할 수 없습니다.")
        except Exception as e:
            logger.warning("_on_generate_drylab_report 실패: %s", e)
            if hasattr(self, 'drylab_status_label'):
                self.drylab_status_label.setText(f"실패: {e}")
            QMessageBox.warning(self, "오류", f"DryLab Report 생성 실패:\n{e}")

    # ------------------------------------------------------------------ utilities

    def _extract_uniprot_from_fasta(self, fasta_text: str) -> str:
        """FASTA 헤더에서 UniProt ID 추출 (M460 보존).

        Rule N: isinstance 체크 필수.
        """
        if not isinstance(fasta_text, str) or not fasta_text:
            return ""
        m = re.search(r">[a-z]{2}\|([A-Z0-9]{5,10})\|", fasta_text)
        if m:
            return m.group(1)
        m2 = re.search(
            r"^>([A-Z][0-9][A-Z0-9]{3}[0-9]|[OPQ][0-9][A-Z0-9]{3}[0-9])",
            fasta_text, re.MULTILINE
        )
        if m2:
            return m2.group(1)
        return ""
