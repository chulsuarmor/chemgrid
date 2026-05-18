# popup_docking.py (v1.2 - Molecular Docking Dashboard — M851_W2 fix)
# 학술 인용 (Rule NN, THEORY-AUTO-003):
#   Trott, O.; Olson, A.J. (2010) J. Comput. Chem. 31, 455-461. (AutoDock Vina)
#   Eberhardt, J.; Santos-Martins, D.; Tillack, A.F.; Forli, S. (2021)
#       J. Chem. Inf. Model. 61(8):3891-3898. (AutoDock Vina 1.2 — R-T3 M851_W2)
#   Sehnal, D. et al. (2021) Nucleic Acids Res. 49, W431-W437. (Mol*)
"""
ChemDraw Pro: Molecular Docking Simulation Dashboard
- Tab 1: Setup (receptor input, ligand preview, docking parameters)
- Tab 2: Results (pose table, binding energy chart)
- Tab 3: Interactions (2D interaction map, interaction table)
- Tab 4: 3D View (protein-ligand complex viewer with binding site visualization)
- Tab 5: AI Interpretation (Gemini-powered docking result explanation)
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QMessageBox,
        QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
        QGroupBox, QFormLayout, QProgressBar, QTextEdit, QSplitter,
        QWidget, QHeaderView, QSizePolicy, QScrollArea, QCheckBox, QFrame
    )
    from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QUrl
    from PyQt6.QtGui import QFont, QColor, QDesktopServices
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

# Optional: Innate defense docking (Cascade #11 Block 11-A)
try:
    from innate_defense_docking import (
        run_antimicrobial_analysis,
        generate_temperature_chart_data,
        format_analysis_report,
        AntimicrobialAnalysisThread,
        AntimicrobialBindingResult,
        ANTIMICROBIAL_TARGETS,
        STANDARD_TEMPERATURES,
    )
    INNATE_DEFENSE_AVAILABLE = True
except ImportError:
    INNATE_DEFENSE_AVAILABLE = False

# Optional: Membrane permeability engine (Cascade #11 Block 11-B)
try:
    from membrane_permeability import (
        run_permeability_analysis,
        sweep_ph_permeability,
        plot_free_energy_profile,
        plot_ph_permeability_sweep,
        format_permeability_report,
        generate_permeability_chart_data,
        estimate_surfactant_disruption,
        calculate_logd,
        MembranePermeabilityThread,
        PermeabilityResult,
        MEMBRANE_PERM_AVAILABLE as _MEM_PERM_ENGINE,
        _SURFACTANT_DB,
    )
    MEMBRANE_PERM_AVAILABLE = _MEM_PERM_ENGINE
except ImportError:
    MEMBRANE_PERM_AVAILABLE = False

# Optional: Mucin network engine (Cascade #11 Block 11-C)
try:
    from mucin_network import (
        run_mucin_analysis,
        format_mucin_report,
        generate_mucin_chart_data,
        generate_ogston_chart,
        generate_mucolytic_chart,
        MucinAnalysisThread,
        MucinAnalysisResult,
        MUCIN_NETWORK_AVAILABLE as _MUCIN_ENGINE,
        _MUCOLYTIC_DB,
    )
    MUCIN_TAB_AVAILABLE = _MUCIN_ENGINE
except ImportError:
    MUCIN_TAB_AVAILABLE = False

# Optional: Gemini AI for docking interpretation
try:
    import google.genai as _genai_lib
    _GENAI_AVAILABLE = True
except ImportError:
    _genai_lib = None
    _GENAI_AVAILABLE = False


# ============================================================
# [M851 格忿#29] Grok AI 채팅 스레드 — OpenRouter x-ai/grok-2-1212
# Rule I: API 키 소스 금지 (환경변수/env 전용)
# Rule M: silent failure 금지 — error 시그널로 사용자 피드백
# ============================================================
class GrokChatThread(QThread):
    """Grok API (via OpenRouter) 비동기 호출 스레드.
    결과: response_ready(str 응답, list[str] pdb_ids)
    실패: error_occurred(str 오류메시지)
    """
    response_ready = pyqtSignal(str, list)   # (full_text, extracted_pdb_ids)
    error_occurred = pyqtSignal(str)         # error message

    def __init__(self, query: str, api_key: str, parent=None):
        super().__init__(parent)
        self._query = query
        self._api_key = api_key

    # --- [M851_W2 R-T1] 50줄 이내 run() — helper 3종 분리 ---
    # K2 준수: GrokChatThread.run()은 helper 호출만 (Karpathy K2)

    def _call_api(self, model: str) -> "Optional[dict]":
        """HTTP 호출 + timeout → raw dict 반환. 실패 시 None. (M851_W2 R-T1)"""
        import json
        import urllib.request
        import urllib.error

        OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
        TIMEOUT_SEC = 25  # [MAGIC: 25s] OpenRouter 응답 대기 최대 (느린 클라이언트 허용)
        MAX_TOKENS = 512  # [MAGIC: 512] 단백질 5개 설명 충분 길이
        system_prompt = (
            "당신은 고등학생을 위한 구조생물학 전문가 조교입니다. "
            "학생의 질문에 대해 관련 단백질 수용체를 한국어로 친절하게 설명하고, "
            "각 단백질의 PDB ID를 반드시 포함하세요. "
            "마지막에 추천 PDB ID를 JSON 배열로 출력하세요. "
            "예시: {\"recommended_pdb_ids\": [\"1ABC\", \"2DEF\", \"3GHI\"]} "
            "최대 5개 단백질, 각 단백질당 2~3줄 설명."
        )
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._query},
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": 0.3,  # [MAGIC: 0.3] 사실 정확도 우선 (학술)
        }).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_CHAT_URL, data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://chemgrid.app",
                "X-Title": "ChemGrid Student Docking",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as he:
            logger.warning("[GrokChatThread._call_api] HTTPError model=%s: %s %s", model, he.code, he.reason)
            return None
        except Exception as ex:
            logger.warning("[GrokChatThread._call_api] 예외 model=%s: %s", model, ex)
            return None

    def _parse_response(self, data: dict) -> str:
        """JSON 응답 dict → 텍스트 content 추출. 실패 시 빈 문자열. (M851_W2 R-T1)
        Rule N: isinstance 타입 가드 전 단계 적용."""
        if not isinstance(data, dict):
            logger.warning("[GrokChatThread._parse_response] 응답 타입 오류: %s", type(data).__name__)
            return ""
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            logger.warning("[GrokChatThread._parse_response] choices 없음: %s", str(data)[:200])
            return ""
        msg = choices[0]
        if not isinstance(msg, dict):
            logger.warning("[GrokChatThread._parse_response] choices[0] 타입 오류")
            return ""
        content = (msg.get("message") or {}).get("content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        return content.strip()

    def _extract_pdb_ids(self, text: str) -> "list[str]":
        """텍스트에서 PDB ID 추출. JSON 배열 우선, regex fallback. (M851_W2 R-T1/R-T2)
        R-T2 fix: r'\\b[0-9][A-Z0-9]{3}\\b' — 첫 자리 숫자로 PDB 공식 형식 한정 (false positive 차단)."""
        import json
        import re

        pdb_ids: list = []
        # JSON 배열 우선
        json_match = re.search(r'"recommended_pdb_ids"\s*:\s*(\[.*?\])', text, re.DOTALL)
        if json_match:
            try:
                raw = json.loads(json_match.group(1))
                if isinstance(raw, list):
                    pdb_ids = [str(x).strip().upper() for x in raw if x]
            except Exception as je:
                logger.warning("[GrokChatThread._extract_pdb_ids] JSON 파싱 실패: %s", je)

        if not pdb_ids:
            # [M851_W2 R-T2] PDB 공식 형식: 첫 자리 숫자 필수 (영단어 PASS/TRUE false positive 차단)
            # PDB ID 규칙: 4자리, 첫 자리=숫자 (www.rcsb.org/pages/general/column/faq#q38)
            raw_ids = re.findall(r'\b[0-9][A-Z0-9]{3}\b', text.upper())
            seen: set = set()
            for pid in raw_ids:
                if pid not in seen:
                    seen.add(pid)
                    pdb_ids.append(pid)
                    if len(pdb_ids) >= 5:  # [MAGIC: 5] 최대 5 PDB ID 추천
                        break

        return pdb_ids

    def run(self):
        """M851_W2 R-T1: run() 50줄 이내 — _call_api/_parse_response/_extract_pdb_ids 호출만."""
        MODEL_PRIMARY = "x-ai/grok-2-1212"   # [MAGIC] OpenRouter Grok 2 모델
        MODEL_FALLBACK = "x-ai/grok-beta"    # [MAGIC] grok-2-1212 미사용 시 beta fallback

        for model in (MODEL_PRIMARY, MODEL_FALLBACK):
            data = self._call_api(model)
            if data is None:
                if model == MODEL_FALLBACK:
                    self.error_occurred.emit("Grok API 연결 실패 — 잠시 후 다시 시도하세요.")
                continue

            content = self._parse_response(data)
            if not content:
                if model == MODEL_FALLBACK:
                    self.error_occurred.emit("AI 응답이 비어 있습니다.")
                continue

            pdb_ids = self._extract_pdb_ids(content)
            logger.info("[GrokChatThread] 성공 model=%s pdb_ids=%s", model, pdb_ids)
            self.response_ready.emit(content, pdb_ids)
            return


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
        self.setMinimumWidth(700)  # prevent tab truncation on narrow windows
        self.resize(1100, 800)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Title bar
        title = QLabel("Molecular Docking Simulation")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        main_layout.addWidget(title)

        # SIMULATION 상단 고정 배너 — 초기화 시점부터 Vina 미설치 상태 즉시 명시 (M497 FP-15 fix)
        # Rule M: fallback 모드는 초기화부터 명시 의무 — "도킹 완료" 라벨만 보고 mock을 실제로 오인 방지
        # [M530-U8-VERIFIED] SIMULATION_MODE + HEURISTIC + 휴리스틱 + M497 마커 전부 존재 확인 (2026-04-27)
        self._sim_banner: Optional[QLabel] = None
        self._sim_banner_layout = main_layout  # 배너를 삽입할 레이아웃 참조 보존

        if SIMULATION_MODE or not VINA_AVAILABLE:
            # M497: 초기화 시점에 최상단 경고 배너 즉시 표시 (눈에 잘 띄는 노랑/빨강, 14px bold)
            self._sim_banner = QLabel(
                "⚠ AutoDock Vina 미설치 — 휴리스틱 추정값 표시 중 (HEURISTIC ESTIMATE — Not Vina)\n"
                "현재 보이는 결합 에너지는 MW/steric 보정 추정값이며 실험값이 아닙니다.\n"
                "정밀 도킹: pip install vina  또는  VINA_PATH 환경변수에 vina.exe 경로 설정"
            )
            self._sim_banner.setStyleSheet(
                "background: #ffcc00; color: #7a0000; font-weight: bold; font-size: 14px;"  # 노랑 배경 빨강 텍스트 (M497)
                " padding: 10px; border: 3px solid #e53935; border-radius: 4px;"
            )
            self._sim_banner.setWordWrap(True)
            self._sim_banner.setAlignment(Qt.AlignmentFlag.AlignLeft)
            main_layout.addWidget(self._sim_banner)  # 최상단(title 다음)에 추가
            logger.warning(
                "[DockingPopup] SIMULATION_MODE=%s, VINA_AVAILABLE=%s — "
                "초기화 시점 휴리스틱 경고 배너 표시 (M497 FP-15 fix)",
                SIMULATION_MODE, VINA_AVAILABLE,
            )

        # Status bar
        self.status_label = QLabel("준비 완료")
        self.status_label.setStyleSheet("color: #666; padding: 2px;")
        main_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # Tab widget — ensure Korean labels remain readable and clickable
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)  # fallback scroll when window too narrow
        tab_bar = self.tabs.tabBar()
        tab_bar.setExpanding(True)  # distribute tab space evenly
        tab_font = tab_bar.font()
        tab_font.setPointSize(max(tab_font.pointSize(), 10))  # minimum 10pt for readability
        tab_bar.setFont(tab_font)
        self.tabs.setStyleSheet(
            "QTabBar::tab { min-width: 80px; min-height: 32px; padding: 4px 12px; }"
        )
        self.tabs.addTab(self._create_setup_tab(), "설정")
        # M497: 결과 탭 라벨 — SIMULATION_MODE 시 "(휴리스틱)" 명시 (FP-15 fix)
        _result_tab_label = "결과 (휴리스틱 추정값)" if (SIMULATION_MODE or not VINA_AVAILABLE) else "결과 (Vina 정밀)"
        self.tabs.addTab(self._create_results_tab(), _result_tab_label)
        self.tabs.addTab(self._create_interactions_tab(), "상호작용")
        self.tabs.addTab(self._create_3d_tab(), "3D 뷰")
        self.tabs.addTab(self._create_ai_tab(), "AI 해석")
        if INNATE_DEFENSE_AVAILABLE:
            self.tabs.addTab(self._create_antimicrobial_tab(), "항균 결합")
        if MEMBRANE_PERM_AVAILABLE:
            self.tabs.addTab(self._create_membrane_perm_tab(), "막투과성")
        if MUCIN_TAB_AVAILABLE:
            self.tabs.addTab(self._create_mucin_barrier_tab(), "Mucin 장벽")
        # [M851 格忿#29] AI 채팅 탭 — Grok(OpenRouter) 수용체 추천 전용 채팅창
        # 항상 추가 (API 키 없어도 안내 메시지 표시)
        self._ai_chat_tab_idx = self.tabs.count()
        self.tabs.addTab(self._create_ai_chat_tab(), "AI 채팅")
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
        # [FIX-SCROLL-DOCK] 외부 컨테이너: 스크롤 영역 + 고정 하단 버튼
        outer_widget = QWidget()
        outer_layout = QVBoxLayout(outer_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 스크롤 가능한 내부 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

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

        # [A59-W2 F5-15] AI 프리셋 채팅 입력창
        # 사용자 요구: "텍스트 입력창에 경구 투여되었을때 결합 가능한 인슐린 작용 관련 단백질을 정리해 줘
        # 라고 치면, Groq 같은 AI가 PDB ID 반환하고 드롭다운에서 강조"
        ai_preset_row = QHBoxLayout()
        ai_preset_row.addWidget(QLabel("AI 수용체 추천:"))
        self.ai_preset_input = QLineEdit()
        self.ai_preset_input.setPlaceholderText(
            "예: 경구 투여 시 결합 가능한 인슐린 작용 단백질을 알려줘 (Groq AI 사용)"
        )
        self.ai_preset_input.setMinimumWidth(320)
        ai_preset_row.addWidget(self.ai_preset_input, 1)
        self.btn_ai_preset = QPushButton("AI 추천")
        self.btn_ai_preset.setStyleSheet(
            "QPushButton { background: #7C4DFF; color: white; "
            "padding: 4px 12px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #651FFF; }"
        )
        self.btn_ai_preset.setToolTip("Groq AI로 단백질 수용체를 자동 추천합니다")
        self.btn_ai_preset.clicked.connect(self._on_ai_preset_query)
        ai_preset_row.addWidget(self.btn_ai_preset)
        receptor_layout.addLayout(ai_preset_row)

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

        # Web 3D viewer button for receptor
        self.btn_web_receptor_3d = QPushButton("\U0001F310 웹에서 수용체 구조 보기")
        self.btn_web_receptor_3d.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; padding: 6px 14px; "
            "font-weight: bold; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #1976D2; }"
        )
        self.btn_web_receptor_3d.setToolTip("RCSB PDB 웹사이트에서 수용체의 3D 구조를 봅니다")
        self.btn_web_receptor_3d.clicked.connect(self._on_open_web_receptor_3d)
        receptor_layout.addWidget(self.btn_web_receptor_3d)

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

        # -- 간편 설정 안내 --
        quick_info = QLabel(
            "💡 <b>간편 사용법:</b> ① 위 프리셋에서 수용체 선택 → "
            "② 캔버스에서 리간드 가져오기 → ③ 아래 '도킹 실행' 클릭\n"
            "파라미터는 자동으로 최적값이 설정됩니다."
        )
        quick_info.setWordWrap(True)
        quick_info.setStyleSheet(
            "QLabel { background: rgba(76,175,80,40); color: #81C784; "
            "padding: 8px; border-radius: 4px; font-size: 11px; }"
        )
        layout.addWidget(quick_info)

        # -- Docking parameters (접이식) --
        params_group = QGroupBox("⚙ 고급 파라미터 (선택사항 — 자동 설정됨)")
        params_group.setCheckable(True)
        params_group.setChecked(False)  # 기본: 접힌 상태
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
            spin.setToolTip("리간드가 결합할 수용체 부위의 3D 좌표 (Å 단위).\n"
                           "프리셋 선택 시 자동 설정됩니다.")
        center_row.addWidget(QLabel("X:"))
        center_row.addWidget(self.center_x)
        center_row.addWidget(QLabel("Y:"))
        center_row.addWidget(self.center_y)
        center_row.addWidget(QLabel("Z:"))
        center_row.addWidget(self.center_z)

        btn_auto_center = QPushButton("자동 감지")
        btn_auto_center.setToolTip("PDB 파일에서 결합 부위 좌표를 자동으로 찾습니다")
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
            spin.setToolTip("도킹 검색 영역의 크기 (Å 단위).\n"
                           "큰 결합 포켓에는 25~30 Å, 작은 포켓에는 15~20 Å 권장.")
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
        self.exhaustiveness_spin.setToolTip(
            "검색 정밀도 (높을수록 정확하지만 느림)\n"
            "• 빠른 탐색: 4~8\n"
            "• 일반 (권장): 8~16\n"
            "• 정밀 연구: 32~64"
        )
        params_layout.addRow("정밀도 (Exhaustiveness):", self.exhaustiveness_spin)

        # Num modes
        self.num_modes_spin = QSpinBox()
        self.num_modes_spin.setRange(1, 20)
        self.num_modes_spin.setValue(9)
        self.num_modes_spin.setToolTip(
            "생성할 도킹 포즈 수.\n"
            "여러 결합 자세를 비교하려면 9~20개 권장."
        )
        params_layout.addRow("포즈 수 (Num Modes):", self.num_modes_spin)

        layout.addWidget(params_group)

        # -- Receptor summary above run button --
        self.receptor_summary = QLabel("")
        self.receptor_summary.setWordWrap(True)
        self.receptor_summary.setStyleSheet(
            "QLabel { background: #1a2332; color: #c0c0c0; padding: 8px; "
            "border-radius: 4px; font-size: 11px; }"
        )
        self.receptor_summary.hide()
        layout.addWidget(self.receptor_summary)

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

        # [FIX-SCROLL-DOCK] 스크롤 영역에 내부 위젯 설정
        scroll.setWidget(widget)
        outer_layout.addWidget(scroll, 1)  # stretch=1 로 스크롤이 남는 공간 차지

        # -- 고정 하단 바: 도킹 실행 버튼 (항상 보임) --
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet(
            "QWidget { background: #1a1a2e; border-top: 1px solid #333; }"
        )
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 6, 8, 6)
        bottom_layout.addStretch()

        self.btn_run = QPushButton("도킹 실행")
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-size: 14px; font-weight: bold; padding: 10px 30px; "
            "border-radius: 5px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self.btn_run.clicked.connect(self._run_docking)
        bottom_layout.addWidget(self.btn_run)
        bottom_layout.addStretch()
        outer_layout.addWidget(bottom_bar)

        return outer_widget

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
        # M497: SIMULATION_MODE 시 에너지 컬럼 헤더에 HEURISTIC 명시 (FP-15 fix, Rule M)
        _energy_header = (
            "결합 에너지 (kcal/mol, HEURISTIC 추정)"
            if (SIMULATION_MODE or not VINA_AVAILABLE)
            else "결합 에너지 (kcal/mol, Vina 정밀)"
        )
        self.results_table.setHorizontalHeaderLabels([
            "포즈", _energy_header, "RMSD LB (Å)", "RMSD UB (Å)"
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

        # ── [M853 格忿#31] 외부 도킹 서비스 링크 패널 ──
        # 사용자: "도킹 시뮬레이션 결합 강도·결합방향 모두 볼 수 있어야지"
        # Rule FF: 외부 서비스 prominent 배치 (Eberhardt 2021 / Sehnal 2021)
        # Rule I: 하드코딩 금지 — 모든 URL은 상수 또는 f-string으로 구성
        ext_frame = QFrame()
        ext_frame.setStyleSheet(
            "QFrame { background: #1a2635; border: 2px solid #0288d1; "
            "border-radius: 8px; padding: 4px; }"
        )
        ext_frame_layout = QVBoxLayout(ext_frame)
        ext_frame_layout.setSpacing(4)

        ext_header = QLabel(
            "외부 도킹 서비스 — 결합 강도 및 결합 방향 정밀 분석"
        )
        ext_header.setStyleSheet(
            "font-weight: bold; font-size: 11pt; color: #81d4fa; "
            "background: transparent; border: none;"
        )
        ext_header.setWordWrap(True)
        ext_frame_layout.addWidget(ext_header)

        ext_cite = QLabel(
            "Eberhardt et al. 2021 J.Chem.Inf.Model. 61:3891 (AutoDock Vina 1.2)  |  "
            "Sehnal et al. 2021 NAR 49:W431 (Mol*)  |  "
            "Buttenschoen et al. 2024 Chem.Sci. 15:448 (PoseBusters)"
        )
        ext_cite.setStyleSheet(
            "color: #4fc3f7; font-size: 8pt; background: transparent; border: none;"
        )
        ext_cite.setWordWrap(True)
        ext_frame_layout.addWidget(ext_cite)

        ext_btn_row = QHBoxLayout()

        # SwissDock 버튼 (Grosdidier 2011, 게스트 사용 가능)
        self.btn_swissdock = QPushButton("SwissDock 외부 도킹 열기")
        self.btn_swissdock.setStyleSheet(
            "QPushButton { background: #0288d1; color: white; font-weight: bold; "
            "font-size: 12px; padding: 8px 14px; border-radius: 5px; }"
            "QPushButton:hover { background: #0277bd; }"
        )
        self.btn_swissdock.setToolTip(
            "SwissDock (swissdock.ch) — 게스트 사용 가능 외부 AutoDock Vina 도킹 서비스.\n"
            "현재 리간드 SMILES + 수용체 PDB ID가 자동으로 URL에 포함됩니다.\n"
            "결합 강도 (kcal/mol) 및 결합 방향 3D 시각화 제공.\n"
            "Grosdidier A. et al. 2011 Nucleic Acids Res."
        )
        # Rule S: QPushButton.clicked — Qt6 공식 시그널 확인
        self.btn_swissdock.clicked.connect(self._on_open_swissdock_external)
        ext_btn_row.addWidget(self.btn_swissdock)

        # PDBe-KB 결합 데이터 버튼
        self.btn_pdbe_kb = QPushButton("PDBe-KB 결합 데이터")
        self.btn_pdbe_kb.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; font-weight: bold; "
            "font-size: 12px; padding: 8px 14px; border-radius: 5px; }"
            "QPushButton:hover { background: #0d47a1; }"
        )
        self.btn_pdbe_kb.setToolTip(
            "PDBe-KB (EBI) — 결합 부위 + 상호작용 잔기 데이터.\n"
            "수용체 PDB ID 기반으로 UniProt 항목 조회.\n"
            "학술 인용: Sehnal et al. 2021 NAR 49:W431"
        )
        # Rule S: QPushButton.clicked — Qt6 공식 시그널 확인
        self.btn_pdbe_kb.clicked.connect(self._on_open_pdbe_kb_binding)
        ext_btn_row.addWidget(self.btn_pdbe_kb)

        # RCSB PDB 3D 뷰어 버튼
        self.btn_rcsb_3d = QPushButton("RCSB 3D 뷰어")
        self.btn_rcsb_3d.setStyleSheet(
            "QPushButton { background: #4a148c; color: white; font-weight: bold; "
            "font-size: 12px; padding: 8px 14px; border-radius: 5px; }"
            "QPushButton:hover { background: #38006b; }"
        )
        self.btn_rcsb_3d.setToolTip(
            "RCSB PDB 3D 뷰어 — 수용체 결합 포켓 및 리간드 위치 확인.\n"
            "수용체 PDB ID 기반 직접 링크."
        )
        # Rule S: QPushButton.clicked — Qt6 공식 시그널 확인
        self.btn_rcsb_3d.clicked.connect(self._on_open_rcsb_3d_viewer)
        ext_btn_row.addWidget(self.btn_rcsb_3d)

        ext_frame_layout.addLayout(ext_btn_row)

        # 도킹 매트릭스 안내 라벨 (5분자 프리셋)
        self.ext_docking_info = QLabel(
            "도킹 서비스 연결 대기 중 — 수용체 PDB ID 및 리간드 SMILES를 설정 후 사용하세요."
        )
        self.ext_docking_info.setStyleSheet(
            "color: #90a4ae; font-size: 9pt; background: transparent; border: none;"
        )
        self.ext_docking_info.setWordWrap(True)
        ext_frame_layout.addWidget(self.ext_docking_info)

        layout.addWidget(splitter)
        layout.addWidget(self.summary_label)
        layout.addWidget(ext_frame)
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
        """3D 뷰 탭 — M499: PDBe Mol* 학술 표준 최상단 배치.

        Rule O: 학술 표준 우선. 자체 docking_3d_viewer는 deprecated 폴백 (인터넷 없을 때).
        인용: Sehnal et al. 2021 Nucleic Acids Res 49:W431 (Mol* 원문)
        R-21: 단백질/도킹 3D는 PDBe Mol* 외부 링크 우선 (M499)
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ── M499: PDBe Mol* 학술 표준 버튼 최상단 prominent 배치 ──
        # Rule O: 학술 논문 품질 우선 — 자체 3D 엔진보다 PDBe Mol* 학술 표준 우선
        # Rule R-21: 단백질/도킹 3D = PDBe Mol* 외부 링크 우선 (M499 신설)
        # 인용: Sehnal et al. 2021 Nucleic Acids Res 49:W431
        pdbe_frame = QFrame()
        pdbe_frame.setStyleSheet(
            "QFrame { background: #e3f2fd; border: 3px solid #0066cc; border-radius: 8px; padding: 4px; }"
        )
        pdbe_frame_layout = QVBoxLayout(pdbe_frame)
        pdbe_frame_layout.setSpacing(4)

        # 학술 표준 헤더 라벨
        pdbe_header = QLabel(
            "PDBe Mol* — 단백질/도킹 3D 학술 표준 시각화 (Sehnal et al. 2021 NAR W431)"
        )
        pdbe_header.setStyleSheet(
            "font-weight: bold; font-size: 11pt; color: #0d47a1; background: transparent; border: none;"
        )
        pdbe_header.setWordWrap(True)
        pdbe_frame_layout.addWidget(pdbe_header)

        # 버튼 행: PDBe Mol* 열기 + SDF 내보내기
        # [M499] PDBe Mol* prominent 버튼 — 학술 표준, 항상 활성화 (수용체 PDB ID만 있어도 사용 가능)
        btn_row = QHBoxLayout()
        self.btn_pdbe_molstar = QPushButton("\U0001f310 PDBe Mol* 외부 뷰어 열기 (학술 표준)")
        self.btn_pdbe_molstar.setStyleSheet(
            "QPushButton { background: #0066cc; color: white; font-weight: bold; "
            "font-size: 14px; padding: 12px 20px; border-radius: 6px; }"
            "QPushButton:hover { background: #004499; }"
        )
        # M499: 도킹 전에도 수용체 PDB ID만으로 활성화 — 항상 enabled
        self.btn_pdbe_molstar.setEnabled(True)
        # M647-W4 USR-LV4-07 직격: "PDBe Mol* WebGL 유효하지 않음 오류"
        # 사용자 브라우저 WebGL 미활성 시 자체 3D 뷰어로 폴백 안내 강화
        self.btn_pdbe_molstar.setToolTip(
            "수용체 PDB 또는 도킹 complex를 PDBe Mol* 학술 시각화 도구로 엽니다.\n"
            "수용체 PDB ID만 있어도 사용 가능합니다.\n\n"
            "[WebGL 오류 시] 브라우저에 WebGL이 비활성화된 경우:\n"
            "  1. Chrome: chrome://settings/system → '하드웨어 가속' 활성\n"
            "  2. Firefox: about:config → webgl.disabled=false\n"
            "  3. ChemGrid 내장 3D 뷰어 사용 (3D 뷰 탭)\n\n"
            "인용: Sehnal et al. 2021 Nucleic Acids Res 49:W431-W437"
        )
        # Rule S: QPushButton.clicked — Qt6 공식 시그널, 확인 완료
        self.btn_pdbe_molstar.clicked.connect(self._on_open_pdbe_molstar)
        btn_row.addWidget(self.btn_pdbe_molstar, 2)

        # [M499 Task 2] SDF 내보내기 버튼 — PDBe Mol* 업로드용
        self.btn_export_sdf = QPushButton("\U0001f4be 도킹 Pose SDF 내보내기")
        self.btn_export_sdf.setStyleSheet(
            "QPushButton { background: #388e3c; color: white; font-weight: bold; "
            "font-size: 12px; padding: 10px 14px; border-radius: 6px; }"
            "QPushButton:hover { background: #2e7d32; }"
            "QPushButton:disabled { background: #aaa; color: #eee; }"
        )
        self.btn_export_sdf.setEnabled(False)  # 도킹 완료 후 활성화
        self.btn_export_sdf.setToolTip(
            "현재 도킹 pose를 SDF 파일로 Downloads에 저장합니다.\n"
            "PDBe Mol*에 업로드하여 도킹 결과를 학술 품질로 확인하세요."
        )
        # Rule S: QPushButton.clicked — Qt6 공식 시그널, 확인 완료
        self.btn_export_sdf.clicked.connect(self._on_export_docking_pose_sdf)
        btn_row.addWidget(self.btn_export_sdf, 1)
        pdbe_frame_layout.addLayout(btn_row)

        # 학술 인용 라벨
        cite_label = QLabel(
            "학술 인용: Sehnal et al. 2021 Nucleic Acids Res 49:W431-W437  |  "
            "EBI PDBe Mol* — RCSB/PDBe/PDB 통합 3D 시각화 표준"
        )
        cite_label.setStyleSheet(
            "color: #1565c0; font-size: 9pt; background: transparent; border: none;"
        )
        cite_label.setWordWrap(True)
        pdbe_frame_layout.addWidget(cite_label)

        layout.addWidget(pdbe_frame)

        # ── M499 Task 3: deprecated 자체 3D 뷰어 — 폴백 (인터넷 없을 때만) ──
        # docking_3d_viewer.py는 학술 표준 미달 — PDBe Mol* 사용 권장 (M463 교훈)
        deprecated_header = QLabel(
            "\u26a0\ufe0f 자체 3D 엔진 (폴백 — 학술 표준은 PDBe Mol* 사용 권장)"
        )
        deprecated_header.setStyleSheet(
            "background: #fff3e0; color: #e65100; font-size: 10pt; font-weight: bold; "
            "padding: 6px; border: 2px solid #ff9800; border-radius: 4px;"
        )
        deprecated_header.setWordWrap(True)
        layout.addWidget(deprecated_header)

        if DOCKING_3D_AVAILABLE:
            # [M499 Task 3] deprecated 워터마크 배너
            dep_banner = QLabel(
                "\u26a0\ufe0f [DEPRECATED] 자체 3D 엔진 (docking_3d_viewer.py) — "
                "학술 표준은 위의 PDBe Mol* 버튼 사용 권장.\n"
                "인터넷 없는 환경에서만 폴백으로 사용. Sehnal et al. 2021 NAR W431"
            )
            dep_banner.setStyleSheet(
                "background: #ffecb3; color: #795548; font-size: 9pt; "
                "padding: 4px; border: 1px dashed #ff9800;"
            )
            dep_banner.setWordWrap(True)
            layout.addWidget(dep_banner)

            # Pose selector
            control_row = QHBoxLayout()
            control_row.addWidget(QLabel("포즈 선택:"))
            self.viewer_pose_selector = QComboBox()
            self.viewer_pose_selector.currentIndexChanged.connect(self._on_3d_pose_changed)
            control_row.addWidget(self.viewer_pose_selector)
            control_row.addStretch()
            layout.addLayout(control_row)

            # Visibility toggles + representation controls
            vis_row = QHBoxLayout()
            self._chk_protein = QCheckBox("단백질")
            self._chk_protein.setChecked(True)
            self._chk_protein.toggled.connect(self._toggle_3d_protein)
            vis_row.addWidget(self._chk_protein)

            self._chk_ligand = QCheckBox("리간드")
            self._chk_ligand.setChecked(True)
            self._chk_ligand.toggled.connect(self._toggle_3d_ligand)
            vis_row.addWidget(self._chk_ligand)

            self._chk_interactions = QCheckBox("상호작용")
            self._chk_interactions.setChecked(True)
            self._chk_interactions.toggled.connect(self._toggle_3d_interactions)
            vis_row.addWidget(self._chk_interactions)

            self._chk_binding = QCheckBox("결합부위")
            self._chk_binding.setChecked(True)
            self._chk_binding.toggled.connect(self._toggle_3d_binding)
            vis_row.addWidget(self._chk_binding)

            vis_row.addWidget(QLabel("  │  백본:"))
            self._cmb_backbone = QComboBox()
            self._cmb_backbone.addItems(["리본", "트레이스"])
            self._cmb_backbone.currentIndexChanged.connect(self._on_backbone_style)
            vis_row.addWidget(self._cmb_backbone)

            # MolStyle 4종 표준 버튼 (VMD/PyMOL 표준: Ball+Stick / Space Filling / Stick / Wireframe) — M456 F4 fix
            vis_row.addWidget(QLabel("  │  스타일:"))
            self._btn_mol_ball_stick = QPushButton("Ball+Stick")
            self._btn_mol_ball_stick.setToolTip("Ball-and-Stick 표현 (기본)")
            self._btn_mol_ball_stick.clicked.connect(lambda: self._set_mol_style("ball_stick"))
            vis_row.addWidget(self._btn_mol_ball_stick)

            self._btn_mol_stick = QPushButton("Stick")  # 매직넘버 주석: VMD 표준 Licorice/Stick 모드
            self._btn_mol_stick.setToolTip("Stick (Licorice) 표현 — 원자 구 없이 결합만 튜브")
            self._btn_mol_stick.clicked.connect(lambda: self._set_mol_style("stick"))
            vis_row.addWidget(self._btn_mol_stick)

            self._btn_mol_space = QPushButton("Space Filling")
            self._btn_mol_space.setToolTip("Space Filling (CPK) 표현 — van der Waals 반경")
            self._btn_mol_space.clicked.connect(lambda: self._set_mol_style("space_filling"))
            vis_row.addWidget(self._btn_mol_space)

            self._btn_mol_wire = QPushButton("Wireframe")  # 매직넘버 주석: VMD/PyMOL 최소 표현 — Lines/Wireframe
            self._btn_mol_wire.setToolTip("Wireframe (Lines) 표현 — 가장 단순한 결합선 표현")
            self._btn_mol_wire.clicked.connect(lambda: self._set_mol_style("wireframe"))
            vis_row.addWidget(self._btn_mol_wire)

            vis_row.addStretch()
            layout.addLayout(vis_row)

            # M563 격분 9: 수용체 결합부 스타일 선택 row (Discovery Studio 수준)
            # 사용자 인용 (2026-03-18T13:25): "수용체에서 분자랑 결합하는 부위는 ball&stick 형태로 표현되어야 한다"
            # 매직넘버 주석: 3종 모드 = Discovery Studio + VMD/PyMOL Licorice + Lines 학술 표준 통합
            site_row = QHBoxLayout()
            site_row.addWidget(QLabel("결합부 스타일:"))
            self._btn_site_ball_stick = QPushButton("Ball+Stick (기본)")
            self._btn_site_ball_stick.setToolTip(
                "수용체 결합부를 Ball-and-Stick으로 표현 (Discovery Studio 표준).\n"
                "원자 sphere + cylinder 결합 + interaction role 외곽 ring."
            )
            self._btn_site_ball_stick.clicked.connect(lambda: self._set_binding_site_style("ball_stick"))
            site_row.addWidget(self._btn_site_ball_stick)

            self._btn_site_stick = QPushButton("Stick (Licorice)")
            self._btn_site_stick.setToolTip(
                "결합만 두꺼운 cylinder로 표현 (학술 논문 stick).\n"
                "원자 sphere 없음."
            )
            self._btn_site_stick.clicked.connect(lambda: self._set_binding_site_style("stick"))
            site_row.addWidget(self._btn_site_stick)

            self._btn_site_wire = QPushButton("Wireframe")
            self._btn_site_wire.setToolTip(
                "결합부를 Lines로 단순 표현 (가장 빠른 렌더링)."
            )
            self._btn_site_wire.clicked.connect(lambda: self._set_binding_site_style("wireframe"))
            site_row.addWidget(self._btn_site_wire)
            site_row.addStretch()
            layout.addLayout(site_row)

            self.viewer_3d = Docking3DViewerWidget()
            layout.addWidget(self.viewer_3d, 1)
        else:
            placeholder = QLabel(
                "자체 3D 뷰어(PyOpenGL) 미설치.\n"
                "위의 'PDBe Mol* 외부 뷰어 열기' 버튼을 사용하세요 — 학술 표준 품질.\n"
                "(폴백 설치: pip install PyOpenGL PyOpenGL_accelerate)"
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 20px;")
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

    def _on_open_web_receptor_3d(self):
        """Open RCSB 3D viewer for the current receptor PDB ID."""
        # Try preset combo first
        pdb_id = self.preset_combo.currentData() or ""
        if not pdb_id:
            # Fall back to manual PDB ID input
            pdb_id = self.pdb_id_input.text().strip().upper()
        if not pdb_id:
            QMessageBox.information(self, "알림", "수용체 PDB ID를 선택하거나 입력하세요.")
            return
        url = f"https://www.rcsb.org/3d-view/{pdb_id}"
        QDesktopServices.openUrl(QUrl(url))

    def _on_ai_preset_query(self):
        """[A59-W2 F5-15] Groq AI로 단백질 수용체 추천 후 preset_combo 하이라이트.
        사용자 요구: 학생이 텍스트 입력(예: '경구 투여 인슐린 관련 단백질')하면
        AI가 PDB ID 반환 후 드롭다운에서 일치 항목 선택.
        Rule M: silent failure 금지. Rule I: API 키 소스 금지.
        """
        import json
        import urllib.request
        import urllib.error

        query = self.ai_preset_input.text().strip()
        if not query:
            QMessageBox.warning(self, "입력 필요", "수용체 추천 질문을 입력하세요.")
            return

        groq_key = os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            # .env fallback (Rule I)
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
            try:
                with open(env_path, "r", encoding="utf-8", errors="replace") as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line.startswith("GROQ_API_KEY"):
                            groq_key = _line.split("=", 1)[-1].strip().strip('"').strip("'")
                            break
            except OSError as _e:
                logger.warning("[A59-W2] _on_ai_preset_query: .env 읽기 실패: %s", _e)
        if not groq_key:
            QMessageBox.warning(
                self, "API 키 미설정",
                "GROQ_API_KEY 환경변수를 설정하거나 .env 파일에 추가하세요.\n"
                "발급: https://console.groq.com"
            )
            return

        self.btn_ai_preset.setEnabled(False)
        self.btn_ai_preset.setText("조회 중...")
        try:
            preamble = (
                "You are a structural biology expert. "
                "Given the user query, list up to 5 PDB IDs of relevant protein receptors. "
                "Output ONLY a JSON array like [\"1ABC\",\"2DEF\"]. No explanation."
            )
            body = json.dumps({
                "model": "llama-3.3-70b-versatile",  # [MAGIC] Groq 무료 모델 (Rule MM summarize)
                "messages": [
                    {"role": "system", "content": preamble},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 120,  # [MAGIC: 120] PDB ID 배열 최대 길이
                "temperature": 0.1,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as _resp:  # [MAGIC: 20] Groq 응답 timeout
                data = json.loads(_resp.read().decode("utf-8", errors="replace"))

            # Rule N: isinstance 타입 가드
            if not isinstance(data, dict):
                logger.warning("[A59-W2] Groq 응답 타입 오류: %s", type(data).__name__)
                QMessageBox.warning(self, "AI 오류", "AI 응답 형식 오류입니다.")
                return

            choices = data.get("choices", [])
            if not isinstance(choices, list) or not choices:
                logger.warning("[A59-W2] Groq choices 없음: %s", data)
                QMessageBox.warning(self, "AI 오류", "AI에서 결과를 받지 못했습니다.")
                return

            msg = choices[0]
            if not isinstance(msg, dict):
                logger.warning("[A59-W2] Groq choices[0] 타입 오류")
                return
            content = msg.get("message", {}).get("content", "") or ""
            if not isinstance(content, str):
                content = str(content)

            # JSON 파싱 (Rule N: fallback)
            pdb_ids = []
            try:
                import re as _re
                arr_match = _re.search(r"\[.*?\]", content, _re.DOTALL)
                if arr_match:
                    raw_arr = json.loads(arr_match.group(0))
                    if isinstance(raw_arr, list):
                        pdb_ids = [str(x).strip().upper() for x in raw_arr if x]
            except Exception as _je:
                logger.warning("[A59-W2] Groq 응답 JSON 파싱 실패: %s | content=%s", _je, content[:200])

            if not pdb_ids:
                QMessageBox.information(self, "AI 결과 없음", f"질문 '{query}'에 대한 PDB ID를 찾지 못했습니다.")
                return

            # preset_combo에서 매칭 항목 선택
            matched = []
            for i in range(self.preset_combo.count()):
                item_data = self.preset_combo.itemData(i)
                if isinstance(item_data, str) and item_data.upper() in pdb_ids:
                    matched.append((i, item_data))

            if matched:
                first_idx, first_pdb = matched[0]
                self.preset_combo.setCurrentIndex(first_idx)
                msg_lines = [f"AI 추천 수용체 (질문: {query})"]
                msg_lines.append(f"일치 항목 {len(matched)}개 발견:")
                for idx, pid in matched:
                    msg_lines.append(f"  - {pid}: {self.preset_combo.itemText(idx)}")
                QMessageBox.information(self, "AI 수용체 추천", "\n".join(msg_lines))
            else:
                pdb_list = ", ".join(pdb_ids)
                QMessageBox.information(
                    self, "AI 수용체 추천 (DB 외)",
                    f"AI 추천 PDB ID: {pdb_list}\n"
                    f"현재 프리셋 DB에 없습니다. PDB ID 입력창에 직접 입력하세요."
                )
                # 첫 PDB ID를 직접 입력창에 채움
                self.pdb_id_input.setText(pdb_ids[0])

        except urllib.error.HTTPError as _e:
            logger.warning("[A59-W2] Groq HTTP 오류: %s %s", _e.code, _e.reason)
            QMessageBox.warning(self, "Groq API 오류", f"HTTP {_e.code}: {_e.reason}")
        except Exception as _e:
            logger.warning("[A59-W2] _on_ai_preset_query 실패: %s", _e)
            QMessageBox.warning(self, "AI 연결 실패", f"오류: {_e}")
        finally:
            self.btn_ai_preset.setEnabled(True)
            self.btn_ai_preset.setText("AI 추천")

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

        # Compact summary above run button
        summary_parts = [f"<b style='color:#4a9eff;'>{meta.name}</b>"]
        if meta.tissue_location:
            summary_parts.append(f"📍 <b>체내 위치:</b> {meta.tissue_location}")
        if meta.function:
            summary_parts.append(f"🧬 {meta.function[:60]}")
        if meta.disease_relevance:
            summary_parts.append(f"🏥 {meta.disease_relevance[:60]}")
        self.receptor_summary.setText(" | ".join(summary_parts))
        self.receptor_summary.show()

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
            # N-code: type guard — AI response may not be str
            if not isinstance(text, str):
                logger.warning("[DockingPopup] AI result is not str: type=%s",
                               type(text).__name__)
                text = str(text) if text is not None else ""
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
            logger.warning("_auto_detect_binding_site: receptor is None, cannot detect binding site")
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

        # N-code: type guard — result from VinaDockingThread signal
        if not isinstance(result, DockingResult):
            logger.warning("[DockingPopup] docking result is not DockingResult: type=%s",
                           type(result).__name__)
            QMessageBox.warning(self, "도킹 오류", "도킹 결과 형식이 올바르지 않습니다.")
            self.status_label.setText("도킹 결과 형식 오류")
            return

        self.docking_result = result

        # F1 fix (M456): is_simulation=True 시 빨간 배너 표시 — 학계 신뢰도 (Rule M)
        if getattr(result, 'is_simulation', False):
            if self._sim_banner is None:
                self._sim_banner = QLabel(
                    "경고: SIMULATION MODE — AutoDock Vina 미설치.\n"
                    "결과는 MW/steric 보정 포함 휴리스틱 추정값입니다.\n"
                    "정확한 도킹: pip install vina 또는 VINA_PATH 환경변수 설정 필요."
                )
                self._sim_banner.setStyleSheet(
                    "background: #B71C1C; color: #FFFFFF; font-weight: bold;"  # 빨간 배너 — Rule M 학계 신뢰도 (M447/M456)
                    " padding: 8px; border-radius: 4px; font-size: 11px;"
                )
                self._sim_banner.setWordWrap(True)
                self._sim_banner_layout.insertWidget(2, self._sim_banner)  # status_label 아래
                logger.warning("[DockingPopup] SIMULATION MODE 배너 표시됨 (is_simulation=True)")
            else:
                self._sim_banner.show()
        else:
            # [U-8 M516 fix] result.is_simulation=False여도 모듈 레벨 SIMULATION_MODE=True이면
            # init에서 표시한 배너를 절대 숨기면 안 됨 — M497 init 배너 무력화 버그 차단
            # Rule M: SIMULATION_MODE 전역 플래그가 우선 — result 속성이 False여도 숨김 금지
            if self._sim_banner is not None and not (SIMULATION_MODE or not VINA_AVAILABLE):
                self._sim_banner.hide()

        if not result.converged:
            QMessageBox.warning(
                self, "도킹 실패",
                f"도킹이 수렴하지 못했습니다.\n{result.error_message}"
            )
            self.status_label.setText("도킹 실패")
            return

        # M497: is_simulation=True 시 "도킹 완료" 라벨에 "⚠ 휴리스틱 추정값" 명시 (FP-15 fix)
        # Rule M: "도킹 완료"만 표시하면 mock을 진짜로 오인 — 학생 학습 오염
        if getattr(result, 'is_simulation', False):
            self.status_label.setText(
                f"도킹 완료 (⚠ 휴리스틱 추정값 — 정확한 결과 아님)  "
                f"{result.num_poses}개 포즈, "
                f"최적 에너지: {result.best_affinity:.1f} kcal/mol (추정), "
                f"계산 시간: {result.computation_time:.1f}초"
            )
            self.status_label.setStyleSheet(
                "color: #e65100; font-weight: bold; padding: 2px;"  # 주황색 강조 — SIMULATION 상태 (M497)
            )
        else:
            self.status_label.setText(
                f"도킹 완료! {result.num_poses}개 포즈, "
                f"최적 에너지: {result.best_affinity:.1f} kcal/mol, "
                f"계산 시간: {result.computation_time:.1f}초"
            )
            self.status_label.setStyleSheet("color: #666; padding: 2px;")

        # Run interaction analysis for each pose
        # N-code: type guard — poses must be a list
        if not isinstance(result.poses, list):
            logger.warning("[DockingPopup] result.poses is not list: type=%s",
                           type(result.poses).__name__)
            result.poses = []
        for pose in result.poses:
            interactions = InteractionAnalyzer.analyze_pose(result.receptor, pose, result.ligand)
            result.interactions[pose.pose_id] = interactions

        # Extract binding site residues (~8A of ligand) for each pose
        # Increased from 5A to 8A to ensure ball-and-stick binding site is always visible
        self._binding_site_cache = {}
        for pose in result.poses:
            self._binding_site_cache[pose.pose_id] = (
                InteractionAnalyzer.extract_binding_site_residues(
                    result.receptor, pose, radius=8.0
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

        # [M461/M499] 도킹 완료 → PDBe Mol* 버튼 + SDF 내보내기 버튼 활성화
        # M499: btn_pdbe_molstar은 init 시부터 enabled이지만 toolTip 갱신
        if hasattr(self, 'btn_pdbe_molstar'):
            self.btn_pdbe_molstar.setEnabled(True)
            self.btn_pdbe_molstar.setToolTip(
                f"도킹 완료 ({result.num_poses}개 포즈) → PDBe Mol* 학술 시각화\n"
                "인용: Sehnal et al. 2021 Nucleic Acids Res 49:W431-W437"
            )
        # M499 Task 2: 도킹 완료 후 SDF 내보내기 활성화
        if hasattr(self, 'btn_export_sdf'):
            self.btn_export_sdf.setEnabled(True)
            logger.info("_on_docking_finished: btn_export_sdf 활성화 (M499 Task 2)")

        # [M853 格忿#31] 도킹 완료 → 외부 링크 패널 갱신
        self._update_external_docking_panel()
        logger.info(
            "_on_docking_complete: M853 외부 도킹 패널 갱신 완료 (SwissDock/PDBe-KB/RCSB)"
        )

    def _on_docking_error(self, msg: str):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "도킹 오류", msg)
        self.status_label.setText("도킹 오류 발생")

    # ========== POPULATE RESULTS ==========

    def _populate_receptor_info_panel(self):
        """Fill the receptor info panel with biological metadata."""
        if not self.docking_result or not self.docking_result.receptor:
            logger.warning("_populate_receptor_info_panel: docking_result=%s, skipping receptor info",
                           self.docking_result is not None)
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
        # N-code: type guard — interactions 파라미터 검증
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] _update_binding_reason: interactions not list: type=%s",
                           type(interactions).__name__)
            interactions = []
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
        # N-code: type guard — interactions 파라미터 검증
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] _build_interaction_interpretation: interactions not list: type=%s",
                           type(interactions).__name__)
            interactions = []
        if not interactions:
            return "감지된 상호작용이 없습니다."
        if pose is None:
            logger.warning("[DockingPopup] _build_interaction_interpretation: pose is None")
            return "포즈 데이터가 없습니다."

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

        # Rule N: 타입 가드 — 상수 dict 확인
        assert isinstance(TYPE_EXPLANATIONS, dict) and isinstance(AA_DESC, dict)
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
            if mol is None:
                logger.warning("Invalid ligand SMILES for descriptor computation: %s", ligand_smiles)
            else:
                mw = Descriptors.MolWt(mol)
                logp = Descriptors.MolLogP(mol)
                hbd = rdMolDescriptors.CalcNumHBD(mol)
                hba = rdMolDescriptors.CalcNumHBA(mol)
                tpsa = Descriptors.TPSA(mol)
        except Exception as e:
            logger.warning("Failed to compute molecular descriptors: %s", e)

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
            logger.warning("_populate_results_tab: docking_result is None, cannot populate results")
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
            # [U-8 M516 fix] SIMULATION 시 y축 라벨에 HEURISTIC 명시 — Rule M (FP-15 재발방지)
            _ylabel = (
                "Binding Energy (kcal/mol, HEURISTIC 추정)"
                if (SIMULATION_MODE or not VINA_AVAILABLE)
                else "Binding Energy (kcal/mol)"
            )
            ax.set_ylabel(_ylabel)
            ax.set_title("Docking Pose Energies")
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.3)

            self.energy_figure.tight_layout()
            self.energy_canvas.draw()

        # Summary
        if poses:
            best = min(poses, key=lambda p: p.affinity_kcal)
            # Rule N: 변수 사전 초기화 필수 — UnboundLocalError 방지 (M456 F2 fix)
            interactions_map = getattr(self.docking_result, 'interactions', None)
            if not isinstance(interactions_map, dict):
                interactions_map = {}
            best_interactions = interactions_map.get(best.pose_id, [])
            # N-code: type guard — interactions from dict must be list
            if not isinstance(best_interactions, list):
                logger.warning("[DockingPopup] best_interactions not list: type=%s",
                               type(best_interactions).__name__)
                best_interactions = []
            n_hbonds = sum(1 for i in best_interactions if i.type == "hydrogen_bond")
            n_hydro = sum(1 for i in best_interactions if i.type == "hydrophobic")
            n_pi = sum(1 for i in best_interactions if i.type == "pi_stacking")

            # [U-8 M516 fix] SIMULATION_MODE 시 summary_label에 "(추정)" 명시
            # Rule M: 에너지 수치가 휴리스틱 추정값임을 학생이 알 수 있어야 함 (FP-15 재발방지)
            _sim_suffix = " ⚠ 추정값" if (SIMULATION_MODE or not VINA_AVAILABLE) else ""
            self.summary_label.setText(
                f"최적 포즈 #{best.pose_id}: {best.affinity_kcal:.2f} kcal/mol{_sim_suffix} | "
                f"H-Bond: {n_hbonds} | Hydrophobic: {n_hydro} | Pi-stacking: {n_pi} | "
                f"총 {len(best_interactions)}개 상호작용"
            )

    def _populate_interactions_tab(self):
        if not self.docking_result:
            logger.warning("_populate_interactions_tab: docking_result is None, cannot populate interactions")
            return

        self.pose_selector.clear()
        for pose in self.docking_result.poses:
            self.pose_selector.addItem(
                f"포즈 #{pose.pose_id} ({pose.affinity_kcal:.2f} kcal/mol)",
                pose.pose_id,
            )

    def _populate_3d_tab(self):
        if not self.docking_result or not DOCKING_3D_AVAILABLE:
            logger.warning("_populate_3d_tab: docking_result=%s, DOCKING_3D_AVAILABLE=%s, skipping 3D tab",
                           self.docking_result is not None, DOCKING_3D_AVAILABLE)
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
            # Rule N: 변수 사전 초기화 필수 — UnboundLocalError 방지 (M456 F2 fix)
            interactions_map = getattr(self.docking_result, 'interactions', None)
            if not isinstance(interactions_map, dict):
                interactions_map = {}
            interactions = interactions_map.get(pose.pose_id, [])
            # N-code: type guard — interactions from dict must be list
            if not isinstance(interactions, list):
                logger.warning("[DockingPopup] pose_selected interactions not list: type=%s",
                               type(interactions).__name__)
                interactions = []
            # Update binding reason on receptor info panel
            if hasattr(self, 'ri_binding_reason_label'):
                self._update_binding_reason(pose, interactions)
            # Sync pose selector in interactions tab
            idx = self.pose_selector.findData(pose.pose_id)
            if idx >= 0:
                self.pose_selector.setCurrentIndex(idx)

    def _on_interaction_pose_changed(self, index: int):
        if not self.docking_result or index < 0:
            logger.warning("_on_interaction_pose_changed: docking_result=%s, index=%s, skipping",
                           self.docking_result is not None, index)
            return

        pose_id = self.pose_selector.currentData()
        if pose_id is None:
            logger.warning("_on_interaction_pose_changed: pose_id is None from pose_selector")
            return

        pose = next((p for p in self.docking_result.poses if p.pose_id == pose_id), None)
        # Rule N: 변수 사전 초기화 필수 — UnboundLocalError 방지 (M456 F2 fix)
        interactions_map = getattr(self.docking_result, 'interactions', None)
        if not isinstance(interactions_map, dict):
            interactions_map = {}
        interactions = interactions_map.get(pose_id, [])
        # N-code: type guard — interactions from dict must be list
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] interactions for pose %s is not list: type=%s",
                           pose_id, type(interactions).__name__)
            interactions = []

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
        # N-code: type guard — interactions 파라미터 검증
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] _draw_interaction_map: interactions not list: type=%s",
                           type(interactions).__name__)
            return
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

        # Rule N: 타입 가드 — TYPE_COLORS 상수 dict
        assert isinstance(TYPE_COLORS, dict)
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
            logger.warning("_draw_interaction_map: no unique residues found, skipping map drawing")
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
        # N-code: type guard — interactions 파라미터 검증
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] _draw_ligand_interaction_map: interactions not list: type=%s",
                           type(interactions).__name__)
            return
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
            logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
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

        # 원자 라벨 (헤테로원자만) — Rule N: 타입 가드
        ATOM_COLORS: dict = {
            "O": "#FF0000", "N": "#0000FF", "S": "#CCCC00",
            "F": "#00CC00", "Cl": "#00CC00", "Br": "#8B2500", "I": "#9400D3",
        }
        assert isinstance(ATOM_COLORS, dict)
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
            except Exception as e:
                logger.warning("Failed to match functional group '%s': %s", fg_name, e)

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

        # Rule N: 타입 가드 — TYPE_COLORS/TYPE_LABELS 상수 dict
        assert isinstance(TYPE_COLORS, dict)
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
            logger.warning("_on_3d_pose_changed: docking_result=%s, 3D_AVAILABLE=%s, index=%s, skipping",
                           self.docking_result is not None, DOCKING_3D_AVAILABLE, index)
            return

        pose_id = self.viewer_pose_selector.currentData()
        if pose_id is None:
            logger.warning("_on_3d_pose_changed: pose_id is None from viewer_pose_selector")
            return

        pose = next((p for p in self.docking_result.poses if p.pose_id == pose_id), None)
        if pose and hasattr(self, 'viewer_3d'):
            # Rule N: 변수 사전 초기화 필수 — UnboundLocalError 방지 (M456 F2 fix)
            interactions_map = getattr(self.docking_result, 'interactions', None)
            if not isinstance(interactions_map, dict):
                interactions_map = {}
            interactions = interactions_map.get(pose_id, [])
            # N-code: type guard — interactions from dict must be list
            if not isinstance(interactions, list):
                logger.warning("[DockingPopup] 3D tab interactions for pose %s is not list: type=%s",
                               pose_id, type(interactions).__name__)
                interactions = []
            binding_site = None
            if hasattr(self, '_binding_site_cache'):
                binding_site = self._binding_site_cache.get(pose_id)
                # N-code: type guard — binding_site from cache must be list or None
                if binding_site is not None and not isinstance(binding_site, list):
                    logger.warning("[DockingPopup] binding_site cache for pose %s is not list: type=%s",
                                   pose_id, type(binding_site).__name__)
                    binding_site = None
            # Fallback: binding_site 비어있으면 직접 추출 (8Å 반경)
            if not binding_site:
                try:
                    binding_site = InteractionAnalyzer.extract_binding_site_residues(
                        self.docking_result.receptor, pose, radius=8.0
                    )
                    if binding_site and hasattr(self, '_binding_site_cache'):
                        self._binding_site_cache[pose_id] = binding_site
                except Exception as e:
                    logger.warning("Failed to extract binding site residues for pose %s: %s", pose_id, e)
            self.viewer_3d.set_data(
                self.docking_result.receptor, pose, interactions,
                binding_site_residues=binding_site
            )

    # ========== 3D VIEWER TOGGLES ==========

    def _toggle_3d_protein(self, checked: bool):
        if hasattr(self, 'viewer_3d'):
            self.viewer_3d.show_protein = checked
            self.viewer_3d.update()

    def _toggle_3d_ligand(self, checked: bool):
        if hasattr(self, 'viewer_3d'):
            self.viewer_3d.show_ligand = checked
            self.viewer_3d.update()

    def _toggle_3d_interactions(self, checked: bool):
        if hasattr(self, 'viewer_3d'):
            self.viewer_3d.show_interactions = checked
            self.viewer_3d.update()

    def _toggle_3d_binding(self, checked: bool):
        if hasattr(self, 'viewer_3d'):
            self.viewer_3d.show_binding_site = checked
            self.viewer_3d.update()

    def _on_backbone_style(self, index: int):
        # [M722-4 F5-16 item29] 사용자 격분: "리본 버튼을 눌러도 전환되지 않고"
        # backbone_style 변경 후 update()만으로 repaint가 지연될 수 있음 → repaint() 추가.
        # Rule M: 변경 사항을 사용자에게 즉각 시각 피드백.
        if hasattr(self, 'viewer_3d'):
            new_style = 'ribbon' if index == 0 else 'trace'
            self.viewer_3d.backbone_style = new_style
            self.viewer_3d.update()
            self.viewer_3d.repaint()  # [MAGIC: force immediate repaint] M722-4 전환 즉시 반영
            logger.warning("[M722-4] backbone_style 변경: %s → repaint 강제", new_style)

    def _set_mol_style(self, style: str):
        """MolStyle 4종 전환 — VMD/PyMOL 표준 ball_stick/stick/space_filling/wireframe (M456 F4)"""
        # Rule N: 타입 가드
        if not isinstance(style, str):
            logger.warning("[DockingPopup] _set_mol_style: style not str: type=%s", type(style).__name__)
            return
        if not hasattr(self, 'viewer_3d'):
            logger.warning("[DockingPopup] _set_mol_style: viewer_3d not available, style=%s", style)
            return
        # viewer_3d가 mol_style 속성을 지원하는 경우만 설정 (duck typing)
        if hasattr(self.viewer_3d, 'mol_style'):
            self.viewer_3d.mol_style = style
            self.viewer_3d.update()
            logger.warning("[DockingPopup] mol_style 변경: %s", style)
        else:
            # 뷰어가 mol_style 미지원 시 사용자 알림 (Rule M: silent failure 금지)
            logger.warning("[DockingPopup] viewer_3d mol_style 속성 미지원 — 향후 버전 지원 예정. style=%s", style)

    def _set_binding_site_style(self, style: str):
        """M563 격분 9: 수용체 결합부 스타일 전환 — Discovery Studio 수준.

        사용자 인용 (2026-03-18T13:25): "수용체에서 분자랑 결합하는 부위는 ball&stick 형태로 표현되어야 한다"

        Args:
            style: 'ball_stick' (기본, Discovery Studio) | 'stick' (Licorice) | 'wireframe' (Lines)
        """
        # Rule N: 타입 가드
        if not isinstance(style, str):
            logger.warning("[DockingPopup] _set_binding_site_style: style not str: type=%s", type(style).__name__)
            return
        # 화이트리스트 검증 (Rule L 인풋 가드)
        if style not in ('ball_stick', 'stick', 'wireframe'):
            logger.warning("[DockingPopup] _set_binding_site_style: unknown style=%s", style)
            return
        if not hasattr(self, 'viewer_3d'):
            logger.warning("[DockingPopup] _set_binding_site_style: viewer_3d not available, style=%s", style)
            return
        # viewer_3d가 binding_site_style 속성을 지원하는 경우만 설정 (duck typing)
        if hasattr(self.viewer_3d, 'binding_site_style'):
            self.viewer_3d.binding_site_style = style
            self.viewer_3d.update()
            logger.warning("[DockingPopup] binding_site_style 변경: %s", style)
        else:
            # Rule M: silent failure 금지 — 사용자 알림
            logger.warning("[DockingPopup] viewer_3d binding_site_style 속성 미지원. style=%s", style)

    # ========== AI INTERPRETATION ==========

    def _populate_ai_tab(self):
        """Populate AI tab pose selector after docking completes"""
        if not self.docking_result:
            logger.warning("_populate_ai_tab: docking_result is None, cannot populate AI tab")
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

        # Rule N: 변수 사전 초기화 필수 — UnboundLocalError 방지 (M456 F2 fix)
        interactions_map = getattr(self.docking_result, 'interactions', None)
        if not isinstance(interactions_map, dict):
            interactions_map = {}
        interactions = interactions_map.get(pose_id, [])
        # N-code: type guard — interactions from dict must be list
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] AI tab interactions for pose %s is not list: type=%s",
                           pose_id, type(interactions).__name__)
            interactions = []
        binding_site = self._binding_site_cache.get(pose_id, []) if hasattr(self, '_binding_site_cache') else []
        if not isinstance(binding_site, list):
            logger.warning("[DockingPopup] binding_site for pose %s is not list: type=%s",
                           pose_id, type(binding_site).__name__)
            binding_site = []

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
                        except Exception as e:
                            logger.warning("Gemini API call failed for model %s: %s", _model_name, e)
                            continue
                except ImportError as e:
                    logger.debug("Optional google.genai module not available: %s", e)
                # 2차: Top-level SDK fallback
                if not result_text and _genai_lib:
                    client = _genai_lib.Client(api_key=api_key)
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash", contents=prompt
                    )
                    result_text = resp.text

                # N-code: type guard — AI response may not be str
                if result_text is not None and not isinstance(result_text, str):
                    logger.warning("[DockingPopup] AI result_text is not str: type=%s",
                                   type(result_text).__name__)
                    result_text = str(result_text)
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
        # N-code: type guard — 파라미터 검증
        if not isinstance(interactions, list):
            logger.warning("[DockingPopup] _generate_ai_prompt: interactions not list: type=%s",
                           type(interactions).__name__)
            interactions = []
        if not isinstance(binding_site, list):
            logger.warning("[DockingPopup] _generate_ai_prompt: binding_site not list: type=%s",
                           type(binding_site).__name__)
            binding_site = []
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

    # ========== TAB 6: ANTIMICROBIAL BINDING (Cascade #11 Block 11-A) ==========

    def _create_antimicrobial_tab(self) -> QWidget:
        """Create the antimicrobial binding simulation tab.

        Shows temperature-dependent binding analysis for antimicrobial compounds
        against bacterial target proteins (innate immune defence context).
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Header ---
        header = QLabel("비특이적 방어작용 — 항균 결합 시뮬레이션")
        header.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 4px; color: #e0e0e0;"
        )
        layout.addWidget(header)

        desc = QLabel(
            "발열 시 체온 변화가 항균 물질의 표적 단백질 결합에 미치는 열역학적 영향을 분석합니다.\n"
            "van 't Hoff / Gibbs-Helmholtz 보정을 적용한 온도별 DeltaG 비교 차트를 생성합니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(desc)

        # --- Input section ---
        input_group = QGroupBox("분석 설정")
        input_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #555; "
            "border-radius: 4px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }"
        )
        input_layout = QFormLayout(input_group)

        # SMILES input (auto-filled from ligand if available)
        self.amr_smiles_input = QLineEdit()
        self.amr_smiles_input.setPlaceholderText("항균 물질 SMILES (예: C=CCSS(=O)CC=C)")
        input_layout.addRow("SMILES:", self.amr_smiles_input)

        # Molecule name
        self.amr_name_input = QLineEdit()
        self.amr_name_input.setPlaceholderText("물질명 (예: Allicin)")
        input_layout.addRow("물질명:", self.amr_name_input)

        # Target selector
        self.amr_target_combo = QComboBox()
        self.amr_target_combo.addItem("자동 선택 (4종 표적 순차 분석)", "")
        if INNATE_DEFENSE_AVAILABLE:
            for pdb_id, target in ANTIMICROBIAL_TARGETS.items():
                self.amr_target_combo.addItem(
                    f"{target.name} ({pdb_id}) — {target.organism}",
                    pdb_id,
                )
        input_layout.addRow("표적 단백질:", self.amr_target_combo)

        # Auto-fill button
        btn_autofill = QPushButton("현재 리간드에서 가져오기")
        btn_autofill.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        btn_autofill.clicked.connect(self._amr_autofill_from_ligand)
        input_layout.addRow("", btn_autofill)

        layout.addWidget(input_group)

        # --- Run button ---
        btn_row = QHBoxLayout()
        self.btn_amr_run = QPushButton("항균 결합 분석 실행")
        self.btn_amr_run.setStyleSheet(
            "QPushButton { background-color: #E91E63; color: white; "
            "font-weight: bold; padding: 8px 24px; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #C2185B; }"
            "QPushButton:disabled { background-color: #666; }"
        )
        self.btn_amr_run.clicked.connect(self._on_amr_run)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_amr_run)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- Progress ---
        self.amr_progress_label = QLabel("")
        self.amr_progress_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        layout.addWidget(self.amr_progress_label)

        # --- Results area (splitter: chart on left, report on right) ---
        self.amr_results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: temperature chart (matplotlib)
        self.amr_chart_container = QWidget()
        chart_layout = QVBoxLayout(self.amr_chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_label = QLabel("온도별 결합 에너지 비교")
        chart_label.setStyleSheet("font-weight: bold; padding: 2px;")
        chart_layout.addWidget(chart_label)

        if MATPLOTLIB_AVAILABLE:
            self.amr_figure = Figure(figsize=(5, 4), dpi=100)
            self.amr_figure.patch.set_facecolor('#1e1e2e')
            self.amr_canvas = FigureCanvas(self.amr_figure)
            self.amr_canvas.setMinimumHeight(300)
            chart_layout.addWidget(self.amr_canvas)
        else:
            no_mpl = QLabel("matplotlib 미설치 — 차트를 표시할 수 없습니다.")
            no_mpl.setStyleSheet("color: #FF9800; padding: 20px;")
            chart_layout.addWidget(no_mpl)

        self.amr_results_splitter.addWidget(self.amr_chart_container)

        # Right: text report
        self.amr_report_text = QTextEdit()
        self.amr_report_text.setReadOnly(True)
        self.amr_report_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "font-family: 'Consolas', 'D2Coding', monospace; font-size: 11px; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 6px; }"
        )
        self.amr_report_text.setPlaceholderText(
            "항균 물질 SMILES를 입력하고 '항균 결합 분석 실행'을 클릭하세요.\n\n"
            "분석 내용:\n"
            "  - 분자 물성 (MW, LogP, TPSA, HBD/HBA)\n"
            "  - 온도별 결합 에너지 (DeltaG) 비교\n"
            "  - 해리상수 (Kd) 및 결합 확률\n"
            "  - HOMO-LUMO 전자구조 분석\n"
            "  - 분자 정전기 포텐셜 (MEP)\n"
            "  - 발열의 열역학적 항균 효과 해석"
        )
        self.amr_results_splitter.addWidget(self.amr_report_text)

        self.amr_results_splitter.setSizes([500, 500])
        layout.addWidget(self.amr_results_splitter, 1)  # stretch

        # --- Bottom: summary table ---
        self.amr_summary_table = QTableWidget(0, 5)
        self.amr_summary_table.setHorizontalHeaderLabels([
            "온도 (C)", "DeltaG (kcal/mol)", "Kd (M)", "결합 확률", "효과"
        ])
        self.amr_summary_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.amr_summary_table.setMaximumHeight(150)
        self.amr_summary_table.setStyleSheet(
            "QTableWidget { background-color: #1e1e2e; color: #cdd6f4; "
            "gridline-color: #45475a; font-size: 11px; }"
            "QHeaderView::section { background-color: #313244; color: #cdd6f4; "
            "padding: 4px; border: 1px solid #45475a; font-weight: bold; }"
        )
        layout.addWidget(self.amr_summary_table)

        # Internal state
        self._amr_thread = None
        self._amr_result: Optional['AntimicrobialBindingResult'] = None

        return widget

    def _amr_autofill_from_ligand(self):
        """Auto-fill antimicrobial SMILES from the current ligand."""
        if self.ligand and hasattr(self.ligand, 'smiles') and self.ligand.smiles:
            self.amr_smiles_input.setText(self.ligand.smiles)
            self.amr_name_input.setText(getattr(self.ligand, 'name', '')[:50])
            self.amr_progress_label.setText("리간드에서 SMILES 가져옴")
        elif hasattr(self, 'smiles_input') and self.smiles_input.text().strip():
            self.amr_smiles_input.setText(self.smiles_input.text().strip())
            self.amr_progress_label.setText("설정 탭 SMILES에서 가져옴")
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "알림",
                "먼저 설정 탭에서 리간드 SMILES를 입력하거나 도킹을 실행하세요."
            )

    def _on_amr_run(self):
        """Run antimicrobial binding analysis in background thread."""
        smiles = self.amr_smiles_input.text().strip()
        if not smiles:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "알림", "항균 물질 SMILES를 입력하세요.")
            return

        mol_name = self.amr_name_input.text().strip() or smiles[:20]
        receptor_pdb = self.amr_target_combo.currentData() or ""

        self.btn_amr_run.setEnabled(False)
        self.amr_progress_label.setText("분석 중...")
        self.amr_report_text.clear()

        # Run in background thread
        self._amr_thread = AntimicrobialAnalysisThread(
            smiles=smiles,
            molecule_name=mol_name,
            receptor_pdb_id=receptor_pdb,
            parent=self,
        )
        self._amr_thread.progress.connect(self._on_amr_progress)
        self._amr_thread.finished_signal.connect(self._on_amr_finished)
        self._amr_thread.error_signal.connect(self._on_amr_error)
        self._amr_thread.start()

    def _on_amr_progress(self, msg: str):
        self.amr_progress_label.setText(msg)

    def _on_amr_error(self, msg: str):
        self.btn_amr_run.setEnabled(True)
        self.amr_progress_label.setText(f"오류: {msg}")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "항균 결합 분석 오류", msg)

    def _on_amr_finished(self, result):
        """Handle completed antimicrobial analysis."""
        self.btn_amr_run.setEnabled(True)
        self._amr_result = result

        if not result or not result.success:
            err = getattr(result, 'error_message', '알 수 없는 오류')
            self.amr_progress_label.setText(f"분석 실패: {err}")
            return

        self.amr_progress_label.setText("분석 완료!")

        # --- Fill text report ---
        report = format_analysis_report(result)
        self.amr_report_text.setPlainText(report)

        # --- Fill summary table ---
        profiles = result.temperature_profiles
        self.amr_summary_table.setRowCount(len(profiles))
        for i, tp in enumerate(profiles):
            self.amr_summary_table.setItem(i, 0, QTableWidgetItem(f"{tp.temperature_C:.1f}"))
            self.amr_summary_table.setItem(i, 1, QTableWidgetItem(f"{tp.delta_G_corrected_kcal:.3f}"))
            kd_str = f"{tp.Kd_M:.2e}" if tp.Kd_M < 0.01 else f"{tp.Kd_M:.4f}"
            self.amr_summary_table.setItem(i, 2, QTableWidgetItem(kd_str))
            self.amr_summary_table.setItem(i, 3, QTableWidgetItem(f"{tp.binding_probability:.4f}"))

            # Effect column: interpret temperature effect
            if tp.temperature_C <= 37.0:
                effect = "기준 (체온)"
            elif tp.delta_G_corrected_kcal < profiles[0].delta_G_corrected_kcal:
                effect = "결합 강화"
            elif tp.delta_G_corrected_kcal > profiles[0].delta_G_corrected_kcal:
                effect = "결합 약화"
            else:
                effect = "변화 없음"
            self.amr_summary_table.setItem(i, 4, QTableWidgetItem(effect))

        # --- Draw temperature chart ---
        if MATPLOTLIB_AVAILABLE and hasattr(self, 'amr_figure'):
            self._draw_amr_temperature_chart(result)

    def _draw_amr_temperature_chart(self, result):
        """Draw temperature vs binding energy comparison chart."""
        chart_data = generate_temperature_chart_data(result)
        # N-code: type guard — chart_data from external engine
        if not isinstance(chart_data, dict):
            logger.warning("[DockingPopup] chart_data is not dict: type=%s",
                           type(chart_data).__name__)
            return
        temps = chart_data.get("temperatures", [])
        delta_g = chart_data.get("delta_g", [])
        probs = chart_data.get("probability", [])
        if not isinstance(temps, list) or not isinstance(delta_g, list) or not isinstance(probs, list):
            logger.warning("[DockingPopup] chart_data values not lists: temps=%s, delta_g=%s, probs=%s",
                           type(temps).__name__, type(delta_g).__name__, type(probs).__name__)
            return

        self.amr_figure.clear()

        # Two subplots: DeltaG and binding probability
        ax1 = self.amr_figure.add_subplot(2, 1, 1)
        ax2 = self.amr_figure.add_subplot(2, 1, 2)

        # Dark theme styling
        for ax in (ax1, ax2):
            ax.set_facecolor('#1e1e2e')
            ax.tick_params(colors='#cdd6f4', labelsize=9)
            ax.spines['bottom'].set_color('#45475a')
            ax.spines['top'].set_color('#45475a')
            ax.spines['left'].set_color('#45475a')
            ax.spines['right'].set_color('#45475a')

        # Subplot 1: DeltaG vs Temperature
        bar_colors = ['#4CAF50' if dg == min(delta_g) else '#2196F3' for dg in delta_g]
        bars1 = ax1.bar(
            [f"{t:.0f}C" for t in temps], delta_g,
            color=bar_colors, edgecolor='#cdd6f4', linewidth=0.5,
        )
        ax1.set_ylabel("DeltaG (kcal/mol)", color='#cdd6f4', fontsize=9)
        ax1.set_title(
            f"온도별 결합 에너지: {result.molecule_name or result.smiles[:20]}",
            color='#cdd6f4', fontsize=10, fontweight='bold',
        )
        # Value labels on bars
        for bar, val in zip(bars1, delta_g):
            ax1.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{val:.3f}", ha='center', va='bottom',
                color='#cdd6f4', fontsize=8,
            )

        # Subplot 2: Binding probability vs Temperature
        bar_colors2 = ['#E91E63' if p == max(probs) else '#FF9800' for p in probs]
        bars2 = ax2.bar(
            [f"{t:.0f}C" for t in temps], probs,
            color=bar_colors2, edgecolor='#cdd6f4', linewidth=0.5,
        )
        ax2.set_ylabel("결합 확률", color='#cdd6f4', fontsize=9)
        ax2.set_xlabel("온도", color='#cdd6f4', fontsize=9)
        for bar, val in zip(bars2, probs):
            ax2.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{val:.4f}", ha='center', va='bottom',
                color='#cdd6f4', fontsize=8,
            )

        self.amr_figure.tight_layout(pad=1.5)
        self.amr_canvas.draw()

    # ========== TAB 7: MEMBRANE PERMEABILITY ==========

    def _create_membrane_perm_tab(self) -> QWidget:
        """Create pH-dependent membrane permeability analysis tab.

        Features:
        - pH slider (2.0-10.0, 0.5 step) with real-time logD/logPapp display
        - Free energy profile matplotlib chart
        - pH sweep chart (logD + logPapp vs pH)
        - Surfactant disruption analysis button
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Header ---
        header = QLabel("pH 의존적 막 투과 분석")
        header.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 4px; color: #e0e0e0;"
        )
        layout.addWidget(header)

        desc = QLabel(
            "DOPC 5-layer 지질막 모델 기반 약물 투과도를 예측합니다.\n"
            "pH 슬라이더로 Henderson-Hasselbalch logD 및 겉보기 투과도(Papp) 변화를 실시간 확인합니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(desc)

        # --- Input section ---
        input_group = QGroupBox("분석 설정")
        input_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #555; "
            "border-radius: 4px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }"
        )
        input_layout = QFormLayout(input_group)

        # SMILES input
        self.mem_smiles_input = QLineEdit()
        self.mem_smiles_input.setPlaceholderText("약물 SMILES (예: CC(=O)Oc1ccccc1C(=O)O)")
        input_layout.addRow("SMILES:", self.mem_smiles_input)

        # Molecule name
        self.mem_name_input = QLineEdit()
        self.mem_name_input.setPlaceholderText("물질명 (예: Aspirin)")
        input_layout.addRow("물질명:", self.mem_name_input)

        # pH slider row
        ph_widget = QWidget()
        ph_row = QHBoxLayout(ph_widget)
        ph_row.setContentsMargins(0, 0, 0, 0)

        self.mem_ph_slider = QDoubleSpinBox()
        self.mem_ph_slider.setRange(2.0, 10.0)
        self.mem_ph_slider.setSingleStep(0.5)
        self.mem_ph_slider.setValue(7.4)  # physiological default
        self.mem_ph_slider.setDecimals(1)
        self.mem_ph_slider.setSuffix("")
        self.mem_ph_slider.setMinimumWidth(100)
        ph_row.addWidget(self.mem_ph_slider)

        self.mem_ph_label = QLabel("pH 7.4 (생리적 pH)")
        self.mem_ph_label.setStyleSheet("color: #cdd6f4; font-size: 11px; padding-left: 8px;")
        ph_row.addWidget(self.mem_ph_label)
        ph_row.addStretch()

        self.mem_ph_slider.valueChanged.connect(self._on_mem_ph_changed)
        input_layout.addRow("pH:", ph_widget)

        # Auto-fill button
        btn_mem_autofill = QPushButton("현재 리간드에서 가져오기")
        btn_mem_autofill.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        btn_mem_autofill.clicked.connect(self._mem_autofill_from_ligand)
        input_layout.addRow("", btn_mem_autofill)

        layout.addWidget(input_group)

        # --- Action buttons row ---
        btn_row = QHBoxLayout()

        self.btn_mem_single = QPushButton("단일 pH 분석")
        self.btn_mem_single.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #388E3C; }"
            "QPushButton:disabled { background-color: #666; }"
        )
        self.btn_mem_single.clicked.connect(self._on_mem_single_run)

        self.btn_mem_sweep = QPushButton("pH 스윕 (2.0 ~ 10.0)")
        self.btn_mem_sweep.setStyleSheet(
            "QPushButton { background-color: #E91E63; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #C2185B; }"
            "QPushButton:disabled { background-color: #666; }"
        )
        self.btn_mem_sweep.clicked.connect(self._on_mem_sweep_run)

        self.btn_mem_surfactant = QPushButton("계면활성제 분석")
        self.btn_mem_surfactant.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #F57C00; }"
            "QPushButton:disabled { background-color: #666; }"
        )
        self.btn_mem_surfactant.clicked.connect(self._on_mem_surfactant_run)

        btn_row.addStretch()
        btn_row.addWidget(self.btn_mem_single)
        btn_row.addWidget(self.btn_mem_sweep)
        btn_row.addWidget(self.btn_mem_surfactant)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- Progress ---
        self.mem_progress_label = QLabel("")
        self.mem_progress_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        layout.addWidget(self.mem_progress_label)

        # --- Results area (splitter: chart left, report right) ---
        self.mem_results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: matplotlib chart area
        self.mem_chart_container = QWidget()
        chart_layout = QVBoxLayout(self.mem_chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_title = QLabel("자유 에너지 프로파일 / pH 스윕 차트")
        chart_title.setStyleSheet("font-weight: bold; padding: 2px;")
        chart_layout.addWidget(chart_title)

        if MATPLOTLIB_AVAILABLE:
            self.mem_figure = Figure(figsize=(5, 4), dpi=100)
            self.mem_figure.patch.set_facecolor('#1e1e2e')
            self.mem_canvas_widget = FigureCanvas(self.mem_figure)
            self.mem_canvas_widget.setMinimumHeight(300)
            chart_layout.addWidget(self.mem_canvas_widget)
        else:
            no_mpl = QLabel("matplotlib 미설치 — 차트를 표시할 수 없습니다.")
            no_mpl.setStyleSheet("color: #FF9800; padding: 20px;")
            chart_layout.addWidget(no_mpl)

        self.mem_results_splitter.addWidget(self.mem_chart_container)

        # Right: text report
        self.mem_report_text = QTextEdit()
        self.mem_report_text.setReadOnly(True)
        self.mem_report_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "font-family: 'Consolas', 'D2Coding', monospace; font-size: 11px; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 6px; }"
        )
        self.mem_report_text.setPlaceholderText(
            "약물 SMILES를 입력하고 '단일 pH 분석' 또는 'pH 스윕'을 클릭하세요.\n\n"
            "분석 내용:\n"
            "  - logP (Crippen) / pKa (empirical SMARTS)\n"
            "  - Henderson-Hasselbalch logD(pH)\n"
            "  - DOPC 5-layer 자유에너지 프로파일\n"
            "  - 겉보기 투과도 (Papp) 분류\n"
            "  - 이온쌍 보정 및 계면활성제 효과"
        )
        self.mem_results_splitter.addWidget(self.mem_report_text)

        self.mem_results_splitter.setSizes([500, 500])
        layout.addWidget(self.mem_results_splitter, 1)  # stretch

        # --- Bottom: real-time display ---
        self.mem_realtime_group = QGroupBox("실시간 pH 의존 물성")
        self.mem_realtime_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #555; "
            "border-radius: 4px; margin-top: 4px; padding-top: 14px; }"
            "QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }"
        )
        rt_layout = QHBoxLayout(self.mem_realtime_group)

        self.mem_logd_label = QLabel("logD: —")
        self.mem_logd_label.setStyleSheet("color: #2196F3; font-size: 13px; font-weight: bold;")
        rt_layout.addWidget(self.mem_logd_label)

        self.mem_logpapp_label = QLabel("log Papp: —")
        self.mem_logpapp_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        rt_layout.addWidget(self.mem_logpapp_label)

        self.mem_class_label = QLabel("분류: —")
        self.mem_class_label.setStyleSheet("color: #FF9800; font-size: 13px; font-weight: bold;")
        rt_layout.addWidget(self.mem_class_label)

        self.mem_neutral_label = QLabel("중성종: —")
        self.mem_neutral_label.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        rt_layout.addWidget(self.mem_neutral_label)

        layout.addWidget(self.mem_realtime_group)

        # Internal state
        self._mem_thread = None
        self._mem_result: Optional['PermeabilityResult'] = None
        self._mem_sweep_results: list = []
        # Cached molecule data for real-time pH slider updates
        self._mem_cached_logP: Optional[float] = None
        self._mem_cached_pka_values: list = []
        self._mem_cached_pka_types: list = []
        self._mem_cached_mw: float = 300.0  # default MW for Papp estimation

        return widget

    def _on_mem_ph_changed(self, value: float):
        """Update pH label and recalculate logD/Papp in real-time when cached data exists.

        Henderson-Hasselbalch logD is a pure math function (microseconds),
        so we recalculate on every slider tick for instant feedback.
        """
        ph_desc = ""
        if value < 3.0:
            ph_desc = "위액"
        elif value < 5.0:
            ph_desc = "십이지장"
        elif value < 6.5:
            ph_desc = "소장 상부"
        elif value < 7.8:
            ph_desc = "생리적 pH"
        else:
            ph_desc = "대장/알칼리"
        self.mem_ph_label.setText(f"pH {value:.1f} ({ph_desc})")

        # Real-time logD/Papp recalculation from cached molecule data
        if self._mem_cached_logP is not None and MEMBRANE_PERM_AVAILABLE:
            try:
                logd_result = calculate_logd(
                    self._mem_cached_logP,
                    self._mem_cached_pka_values,
                    self._mem_cached_pka_types,
                    value,
                )
                self.mem_logd_label.setText(f"logD: {logd_result.logD:.2f}")
                self.mem_neutral_label.setText(
                    f"중성종: {logd_result.fraction_neutral * 100:.1f}%"
                )

                # Quick Papp estimation from logD (empirical Potts-Guy model):
                # log Papp ~ -2.7 + 0.71*logD - 0.0061*MW (Potts & Guy 1992)
                # Clamp to physically meaningful range [-10, -2]
                import math as _math
                log_papp_est = -2.7 + 0.71 * logd_result.logD - 0.0061 * self._mem_cached_mw
                log_papp_est = max(-10.0, min(-2.0, log_papp_est))
                self.mem_logpapp_label.setText(f"log Papp: {log_papp_est:.2f}")

                # Classification (Yee 1997, MDCK scale)
                if log_papp_est >= -4.5:
                    cls, cls_kr, color = "high", "높음", "#4CAF50"
                elif log_papp_est >= -5.5:
                    cls, cls_kr, color = "moderate", "중간", "#FF9800"
                elif log_papp_est >= -6.5:
                    cls, cls_kr, color = "low", "낮음", "#F44336"
                else:
                    cls, cls_kr, color = "impermeable", "불투과", "#9E9E9E"
                self.mem_class_label.setText(f"분류: {cls_kr}")
                self.mem_class_label.setStyleSheet(
                    f"color: {color}; font-size: 13px; font-weight: bold;"
                )
            except Exception as e:
                logger.warning("Real-time pH recalc error: %s", e)

    def _mem_autofill_from_ligand(self):
        """Auto-fill membrane SMILES from current ligand."""
        if self.ligand and hasattr(self.ligand, 'smiles') and self.ligand.smiles:
            self.mem_smiles_input.setText(self.ligand.smiles)
            self.mem_name_input.setText(getattr(self.ligand, 'name', '')[:50])
            self.mem_progress_label.setText("리간드에서 SMILES 가져옴")
        elif hasattr(self, 'smiles_input') and self.smiles_input.text().strip():
            self.mem_smiles_input.setText(self.smiles_input.text().strip())
            self.mem_progress_label.setText("설정 탭 SMILES에서 가져옴")
        else:
            QMessageBox.information(
                self, "알림",
                "먼저 설정 탭에서 리간드 SMILES를 입력하거나 도킹을 실행하세요."
            )

    def _on_mem_single_run(self):
        """Run single pH membrane permeability analysis."""
        smiles = self.mem_smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "약물 SMILES를 입력하세요.")
            return

        mol_name = self.mem_name_input.text().strip() or smiles[:20]
        pH = self.mem_ph_slider.value()

        self.btn_mem_single.setEnabled(False)
        self.btn_mem_sweep.setEnabled(False)
        self.btn_mem_surfactant.setEnabled(False)
        self.mem_progress_label.setText(f"pH {pH:.1f}에서 분석 중...")

        self._mem_thread = MembranePermeabilityThread(
            smiles=smiles,
            molecule_name=mol_name,
            pH=pH,
            sweep_mode=False,
            parent=self,
        )
        self._mem_thread.finished.connect(self._on_mem_single_finished)
        self._mem_thread.error.connect(self._on_mem_error)
        self._mem_thread.start()

    def _on_mem_sweep_run(self):
        """Run pH sweep (2.0-10.0) membrane permeability analysis."""
        smiles = self.mem_smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "약물 SMILES를 입력하세요.")
            return

        mol_name = self.mem_name_input.text().strip() or smiles[:20]

        self.btn_mem_single.setEnabled(False)
        self.btn_mem_sweep.setEnabled(False)
        self.btn_mem_surfactant.setEnabled(False)
        self.mem_progress_label.setText("pH 스윕 분석 중 (2.0 ~ 10.0, 0.5 간격)...")

        self._mem_thread = MembranePermeabilityThread(
            smiles=smiles,
            molecule_name=mol_name,
            pH=7.4,
            sweep_mode=True,
            ph_range=(2.0, 10.0),
            ph_step=0.5,
            parent=self,
        )
        self._mem_thread.sweep_finished.connect(self._on_mem_sweep_finished)
        self._mem_thread.error.connect(self._on_mem_error)
        self._mem_thread.progress.connect(self._on_mem_progress_update)
        self._mem_thread.start()

    def _on_mem_surfactant_run(self):
        """Run surfactant disruption analysis at current pH."""
        smiles = self.mem_smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "약물 SMILES를 입력하세요.")
            return

        mol_name = self.mem_name_input.text().strip() or smiles[:20]
        pH = self.mem_ph_slider.value()

        self.btn_mem_surfactant.setEnabled(False)
        self.mem_progress_label.setText("계면활성제 교란 분석 중...")

        try:
            # Run baseline first
            baseline = run_permeability_analysis(smiles, mol_name, pH)
            if not baseline.success:
                QMessageBox.warning(self, "분석 실패", f"기본 분석 실패: {baseline.error}")
                self.btn_mem_surfactant.setEnabled(True)
                return

            # Surfactant types and concentration multipliers of CMC
            surfactants = ["SDS", "Triton X-100", "CTAB", "Tween-20", "CHAPS"]
            cmc_multiples = [0.1, 0.5, 1.0, 2.0]

            report_lines = [
                f"== 계면활성제 막 교란 분석 ==",
                f"분자: {mol_name} | pH: {pH:.1f}",
                f"기준 log Papp: {baseline.log_perm:.2f} ({baseline.classification})",
                "",
                f"{'계면활성제':<15} {'xCMC':<8} {'농도(mM)':<10} {'CMC(mM)':<10} {'HLB':<8} {'교란점수':<10} {'효과'}",
                "-" * 80,
            ]

            for surf_name in surfactants:
                surf_info = _SURFACTANT_DB.get(surf_name, {})
                # N-code: type guard — surfactant DB entry
                if not isinstance(surf_info, dict):
                    logger.warning("[DockingPopup] surf_info for %s is not dict: type=%s",
                                   surf_name, type(surf_info).__name__)
                    surf_info = {}
                cmc_val = surf_info.get("cmc_mM", 1.0)
                hlb_val = surf_info.get("hlb", 0.0)
                for mult in cmc_multiples:
                    conc_mM = cmc_val * mult
                    try:
                        score, effect = estimate_surfactant_disruption(
                            surfactant_name=surf_name,
                            concentration_mM=conc_mM,
                        )
                        report_lines.append(
                            f"{surf_name:<15} {mult:<8.1f} {conc_mM:<10.2f} {cmc_val:<10.2f} {hlb_val:<8.1f} {score:<10.3f} {effect}"
                        )
                    except Exception as e:
                        report_lines.append(f"{surf_name:<15} {mult:<8.1f} 오류: {e}")

            self.mem_report_text.setPlainText("\n".join(report_lines))
            self.mem_progress_label.setText("계면활성제 분석 완료")
        except Exception as e:
            QMessageBox.critical(self, "계면활성제 분석 오류", str(e))
            logger.warning("Surfactant analysis error: %s", e)
        finally:
            self.btn_mem_surfactant.setEnabled(True)

    def _on_mem_progress_update(self, pct: int):
        """Update progress label during pH sweep."""
        self.mem_progress_label.setText(f"pH 스윕 분석 중... {pct}%")

    def _on_mem_error(self, msg: str):
        """Handle membrane permeability analysis error."""
        self.btn_mem_single.setEnabled(True)
        self.btn_mem_sweep.setEnabled(True)
        self.btn_mem_surfactant.setEnabled(True)
        self.mem_progress_label.setText(f"오류: {msg}")
        QMessageBox.critical(self, "막투과 분석 오류", msg)

    def _on_mem_single_finished(self, result):
        """Handle completed single-pH membrane permeability analysis."""
        self.btn_mem_single.setEnabled(True)
        self.btn_mem_sweep.setEnabled(True)
        self.btn_mem_surfactant.setEnabled(True)

        # N-code: type guard — result from MembranePermeabilityThread signal
        if result is not None and not isinstance(result, PermeabilityResult):
            logger.warning("[DockingPopup] mem result is not PermeabilityResult: type=%s",
                           type(result).__name__)
            self.mem_progress_label.setText("분석 결과 형식 오류")
            return

        self._mem_result = result

        if not result or not result.success:
            err = getattr(result, 'error', '알 수 없는 오류')
            self.mem_progress_label.setText(f"분석 실패: {err}")
            return

        self.mem_progress_label.setText(
            f"분석 완료 — log Papp: {result.log_perm:.2f} ({result.classification})"
        )

        # Fill text report
        report = format_permeability_report(result)
        self.mem_report_text.setPlainText(report)

        # Update real-time labels
        self.mem_logd_label.setText(f"logD: {result.logD:.2f}")
        self.mem_logpapp_label.setText(f"log Papp: {result.log_perm:.2f}")

        # Color-code classification — Rule N: isinstance for inline dicts
        class_colors: dict = {
            "high": "#4CAF50",
            "moderate": "#FF9800",
            "low": "#F44336",
            "impermeable": "#9E9E9E",
        }
        assert isinstance(class_colors, dict)
        color = class_colors.get(result.classification, "#cdd6f4")
        class_kr: dict = {"high": "높음", "moderate": "중간", "low": "낮음",
                    "impermeable": "불투과", "error": "오류"}
        assert isinstance(class_kr, dict)
        self.mem_class_label.setText(f"분류: {class_kr.get(result.classification, result.classification)}")
        self.mem_class_label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")

        self.mem_neutral_label.setText(f"중성종: {result.fraction_neutral * 100:.1f}%")

        # Cache molecule data for real-time pH slider recalculation
        self._mem_cached_logP = result.logP
        self._mem_cached_pka_values = list(result.pKa_values) if result.pKa_values else []
        self._mem_cached_pka_types = list(result.pKa_types) if result.pKa_types else []
        # Estimate MW from SMILES for Potts-Guy Papp model
        try:
            if RDKIT_AVAILABLE:
                from rdkit import Chem as _Chem
                from rdkit.Chem import Descriptors as _Desc
                _mol = _Chem.MolFromSmiles(result.smiles)
                if _mol is None:
                    logger.warning("Invalid SMILES for MW estimation: %s", result.smiles)
                else:
                    self._mem_cached_mw = _Desc.MolWt(_mol)
        except Exception as e:
            logger.warning("MW estimation from SMILES failed: %s", e)

        # Draw free energy profile chart
        if MATPLOTLIB_AVAILABLE and hasattr(self, 'mem_figure'):
            self._draw_mem_fe_chart(result)

    def _on_mem_sweep_finished(self, results: list):
        """Handle completed pH sweep analysis."""
        self.btn_mem_single.setEnabled(True)
        self.btn_mem_sweep.setEnabled(True)
        self.btn_mem_surfactant.setEnabled(True)

        # N-code: type guard — results from sweep thread must be list
        if not isinstance(results, list):
            logger.warning("[DockingPopup] sweep results is not list: type=%s",
                           type(results).__name__)
            self.mem_progress_label.setText("pH 스윕 결과 형식 오류")
            return

        self._mem_sweep_results = results

        if not results:
            self.mem_progress_label.setText("pH 스윕 결과 없음")
            return

        self.mem_progress_label.setText(
            f"pH 스윕 완료 — {len(results)}개 pH 포인트 분석됨"
        )

        # Generate summary report
        chart_data = generate_permeability_chart_data(results)
        # N-code: type guard — chart_data from external engine
        if not isinstance(chart_data, dict):
            logger.warning("[DockingPopup] permeability chart_data is not dict: type=%s",
                           type(chart_data).__name__)
            chart_data = {}
        report_lines = [
            f"== pH 스윕 막투과도 분석 ==",
            f"분자: {chart_data.get('molecule_name', 'N/A')}",
            f"SMILES: {chart_data.get('smiles', 'N/A')}",
            f"막 모델: {chart_data.get('membrane_model', 'N/A')}",
            f"",
            f"{'pH':<6} {'logD':<8} {'log Papp':<10} {'분류':<12} {'중성종(%)':<10}",
            "-" * 50,
        ]
        class_kr: dict = {"high": "높음", "moderate": "중간", "low": "낮음",
                    "impermeable": "불투과", "error": "오류"}
        assert isinstance(class_kr, dict)  # Rule N: 타입 가드
        for r in results:
            cls = class_kr.get(r.classification, r.classification)
            report_lines.append(
                f"{r.pH:<6.1f} {r.logD:<8.2f} {r.log_perm:<10.2f} {cls:<12} {r.fraction_neutral * 100:<10.1f}"
            )

        self.mem_report_text.setPlainText("\n".join(report_lines))

        # Update real-time labels for pH 7.4 result
        ph74 = [r for r in results if abs(r.pH - 7.4) < 0.1]
        if ph74:
            r = ph74[0]
            self.mem_logd_label.setText(f"logD (pH 7.4): {r.logD:.2f}")
            self.mem_logpapp_label.setText(f"log Papp (pH 7.4): {r.log_perm:.2f}")
            class_colors: dict = {"high": "#4CAF50", "moderate": "#FF9800",
                            "low": "#F44336", "impermeable": "#9E9E9E"}
            assert isinstance(class_colors, dict)  # Rule N: 타입 가드
            color = class_colors.get(r.classification, "#cdd6f4")
            self.mem_class_label.setText(f"분류: {class_kr.get(r.classification, r.classification)}")
            self.mem_class_label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
            self.mem_neutral_label.setText(f"중성종 (pH 7.4): {r.fraction_neutral * 100:.1f}%")

        # Cache molecule data from first sweep result for real-time pH slider
        if results:
            r0 = results[0]
            self._mem_cached_logP = r0.logP
            self._mem_cached_pka_values = list(r0.pKa_values) if r0.pKa_values else []
            self._mem_cached_pka_types = list(r0.pKa_types) if r0.pKa_types else []
            try:
                if RDKIT_AVAILABLE:
                    from rdkit import Chem as _Chem
                    from rdkit.Chem import Descriptors as _Desc
                    _mol = _Chem.MolFromSmiles(r0.smiles)
                    if _mol is None:
                        logger.warning("Invalid SMILES for sweep MW estimation: %s", r0.smiles)
                    else:
                        self._mem_cached_mw = _Desc.MolWt(_mol)
            except Exception as e:
                logger.warning("Sweep MW estimation from SMILES failed: %s", e)

        # Draw pH sweep chart
        if MATPLOTLIB_AVAILABLE and hasattr(self, 'mem_figure'):
            self._draw_mem_sweep_chart(results)

    def _draw_mem_fe_chart(self, result):
        """Draw free energy profile chart in the membrane tab."""
        if not result.free_energy_profile:
            return

        self.mem_figure.clear()
        ax = self.mem_figure.add_subplot(1, 1, 1)
        ax.set_facecolor('#1e1e2e')
        ax.tick_params(colors='#cdd6f4', labelsize=9)
        for spine in ax.spines.values():
            spine.set_color('#45475a')

        z_vals = [p.z_position for p in result.free_energy_profile]
        dg_vals = [p.delta_G for p in result.free_energy_profile]

        ax.plot(z_vals, dg_vals, color='#2196F3', linewidth=2.0, label=r'$\Delta G_{transfer}$')
        ax.fill_between(z_vals, dg_vals, alpha=0.15, color='#2196F3')
        ax.axhline(y=0, color='#666', linestyle='--', linewidth=0.8)

        # Shade membrane layers
        layer_colors = {
            "center": "#FFE0B2", "tail": "#FFF9C4",
            "interface": "#C8E6C9", "headgroup": "#BBDEFB", "water": "#E3F2FD",
        }
        current_layer = ""
        layer_start = z_vals[0]
        for i, point in enumerate(result.free_energy_profile):
            if point.layer_name != current_layer:
                if current_layer and current_layer in layer_colors:
                    ax.axvspan(layer_start, z_vals[i], alpha=0.15,
                               color=layer_colors[current_layer])
                current_layer = point.layer_name
                layer_start = z_vals[i]
        if current_layer in layer_colors:
            ax.axvspan(layer_start, z_vals[-1], alpha=0.15,
                       color=layer_colors[current_layer])

        ax.set_xlabel("z position (A)", color='#cdd6f4', fontsize=10)
        ax.set_ylabel("DeltaG (kcal/mol)", color='#cdd6f4', fontsize=10)
        name = result.molecule_name or result.smiles[:20]
        ax.set_title(
            f"Free Energy Profile - {name} (pH {result.pH:.1f})",
            color='#cdd6f4', fontsize=11, fontweight='bold',
        )
        ax.legend(facecolor='#313244', edgecolor='#45475a', labelcolor='#cdd6f4')
        ax.grid(True, alpha=0.2)

        self.mem_figure.tight_layout(pad=1.5)
        self.mem_canvas_widget.draw()

    def _draw_mem_sweep_chart(self, results):
        """Draw pH sweep chart (logD + logPapp vs pH)."""
        if not results:
            return

        self.mem_figure.clear()
        ax1 = self.mem_figure.add_subplot(2, 1, 1)
        ax2 = self.mem_figure.add_subplot(2, 1, 2)

        for ax in (ax1, ax2):
            ax.set_facecolor('#1e1e2e')
            ax.tick_params(colors='#cdd6f4', labelsize=9)
            for spine in ax.spines.values():
                spine.set_color('#45475a')

        ph_vals = [r.pH for r in results]
        logd_vals = [r.logD for r in results]
        logperm_vals = [r.log_perm for r in results]
        frac_neutral = [r.fraction_neutral * 100 for r in results]

        # Top panel: logD + fraction neutral
        ax1.plot(ph_vals, logd_vals, 'o-', color='#2196F3', linewidth=2, markersize=4, label='logD')
        ax1.set_ylabel("logD", color='#2196F3', fontsize=10)
        ax1.tick_params(axis='y', labelcolor='#2196F3')
        ax1.axhline(y=0, color='#666', linestyle='--', linewidth=0.5)

        ax1b = ax1.twinx()
        ax1b.plot(ph_vals, frac_neutral, '--', color='#F44336', linewidth=1.5, alpha=0.7, label='% neutral')
        ax1b.set_ylabel("% Neutral", color='#F44336', fontsize=10)
        ax1b.tick_params(axis='y', labelcolor='#F44336')
        ax1b.set_ylim(0, 105)
        for spine in ax1b.spines.values():
            spine.set_color('#45475a')

        name = results[0].molecule_name if results else ""
        ax1.set_title(
            f"pH-Dependent Permeability - {name}",
            color='#cdd6f4', fontsize=11, fontweight='bold',
        )
        ax1.grid(True, alpha=0.2)

        # Bottom panel: logPapp with classification zones
        ax2.plot(ph_vals, logperm_vals, 's-', color='#4CAF50', linewidth=2, markersize=5,
                 label=r'log P$_{app}$')

        # Classification zone shading
        ax2.axhspan(-4.5, 0, alpha=0.06, color='#4CAF50', label='High')
        ax2.axhspan(-5.5, -4.5, alpha=0.06, color='#FFC107', label='Moderate')
        ax2.axhspan(-6.5, -5.5, alpha=0.06, color='#FF9800', label='Low')
        ax2.axhspan(-15, -6.5, alpha=0.06, color='#F44336', label='Impermeable')

        ax2.set_xlabel("pH", color='#cdd6f4', fontsize=10)
        ax2.set_ylabel("log Papp (cm/s)", color='#4CAF50', fontsize=10)
        ax2.tick_params(axis='y', labelcolor='#4CAF50')
        ax2.legend(facecolor='#313244', edgecolor='#45475a', labelcolor='#cdd6f4',
                   fontsize=8, ncol=3, loc='upper right')
        ax2.grid(True, alpha=0.2)

        self.mem_figure.tight_layout(pad=1.5)
        self.mem_canvas_widget.draw()

    # ========== TAB 8: MUCIN BARRIER ==========

    def _create_mucin_barrier_tab(self) -> QWidget:
        """Create mucin gel barrier analysis tab (Cascade #11 Block 11-C).

        Features:
        - Drug SMILES + optional particle radius input
        - pH selection (2.0-8.0) with mesh size display
        - Mucolytic agent (NAC/DTT/TCEP/Erdosteine) + concentration slider
        - PEGylation options (MW, grafting density)
        - Ogston sieving results + 3D network visualization (matplotlib)
        - QThread async analysis
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Header ---
        header = QLabel("Mucin 점막 장벽 분석")
        header.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 4px; color: #e0e0e0;"
        )
        layout.addWidget(header)

        desc = QLabel(
            "Ogston 체거름(sieving) 모델 기반 약물의 점막 겔 투과성을 예측합니다.\n"
            "pH 의존적 메쉬 크기 변화, 거담제(mucolytic) 효과, PEGylation 스텔스를 분석합니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(desc)

        # --- Input section ---
        input_group = QGroupBox("분석 설정")
        input_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #555; "
            "border-radius: 4px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }"
        )
        input_layout = QFormLayout(input_group)

        # SMILES
        self.mucin_smiles_input = QLineEdit()
        self.mucin_smiles_input.setPlaceholderText("약물 SMILES (예: CC(=O)Oc1ccccc1C(=O)O)")
        input_layout.addRow("SMILES:", self.mucin_smiles_input)

        # Molecule name
        self.mucin_name_input = QLineEdit()
        self.mucin_name_input.setPlaceholderText("물질명 (예: Aspirin)")
        input_layout.addRow("물질명:", self.mucin_name_input)

        # Particle radius (optional)
        self.mucin_radius_spin = QDoubleSpinBox()
        self.mucin_radius_spin.setRange(0.0, 500.0)
        self.mucin_radius_spin.setValue(0.0)  # 0 = auto-estimate from SMILES
        self.mucin_radius_spin.setSingleStep(0.5)
        self.mucin_radius_spin.setDecimals(1)
        self.mucin_radius_spin.setSuffix(" nm")
        self.mucin_radius_spin.setToolTip("0 = SMILES로부터 자동 추정")
        input_layout.addRow("입자 반경:", self.mucin_radius_spin)

        # pH
        ph_widget = QWidget()
        ph_row = QHBoxLayout(ph_widget)
        ph_row.setContentsMargins(0, 0, 0, 0)

        self.mucin_ph_spin = QDoubleSpinBox()
        self.mucin_ph_spin.setRange(2.0, 8.0)
        self.mucin_ph_spin.setSingleStep(0.5)
        self.mucin_ph_spin.setValue(7.4)
        self.mucin_ph_spin.setDecimals(1)
        self.mucin_ph_spin.setMinimumWidth(100)
        ph_row.addWidget(self.mucin_ph_spin)

        self.mucin_ph_label = QLabel("pH 7.4 — 메쉬 크기: ~340 nm (생리적)")
        self.mucin_ph_label.setStyleSheet("color: #cdd6f4; font-size: 11px; padding-left: 8px;")
        ph_row.addWidget(self.mucin_ph_label)
        ph_row.addStretch()

        self.mucin_ph_spin.valueChanged.connect(self._on_mucin_ph_changed)
        input_layout.addRow("pH:", ph_widget)

        # Mucin concentration
        self.mucin_conc_spin = QDoubleSpinBox()
        self.mucin_conc_spin.setRange(5.0, 100.0)
        self.mucin_conc_spin.setValue(20.0)
        self.mucin_conc_spin.setSingleStep(5.0)
        self.mucin_conc_spin.setDecimals(0)
        self.mucin_conc_spin.setSuffix(" mg/mL")
        self.mucin_conc_spin.setToolTip("일반 점액: 10-50 mg/mL, 낭포성 섬유증: 50-100 mg/mL")
        input_layout.addRow("뮤신 농도:", self.mucin_conc_spin)

        # --- Mucolytic agent ---
        muco_widget = QWidget()
        muco_row = QHBoxLayout(muco_widget)
        muco_row.setContentsMargins(0, 0, 0, 0)

        self.mucin_mucolytic_combo = QComboBox()
        self.mucin_mucolytic_combo.addItem("없음 (No mucolytic)", "")
        mucolytic_agents = ["N-acetylcysteine", "DTT", "TCEP", "Erdosteine"]
        for agent in mucolytic_agents:
            self.mucin_mucolytic_combo.addItem(agent, agent)
        self.mucin_mucolytic_combo.setMinimumWidth(180)
        muco_row.addWidget(self.mucin_mucolytic_combo)

        self.mucin_mucolytic_conc = QDoubleSpinBox()
        self.mucin_mucolytic_conc.setRange(0.0, 50.0)
        self.mucin_mucolytic_conc.setValue(10.0)
        self.mucin_mucolytic_conc.setSingleStep(1.0)
        self.mucin_mucolytic_conc.setDecimals(1)
        self.mucin_mucolytic_conc.setSuffix(" mM")
        muco_row.addWidget(self.mucin_mucolytic_conc)

        self.mucin_mucolytic_combo.currentIndexChanged.connect(
            lambda _: self.mucin_mucolytic_conc.setEnabled(
                self.mucin_mucolytic_combo.currentData() != ""))

        muco_row.addStretch()
        input_layout.addRow("거담제:", muco_widget)

        # --- PEGylation options ---
        peg_widget = QWidget()
        peg_row = QHBoxLayout(peg_widget)
        peg_row.setContentsMargins(0, 0, 0, 0)

        self.mucin_peg_check = QCheckBox("PEGylation 적용")
        self.mucin_peg_check.setStyleSheet("color: #cdd6f4;")
        peg_row.addWidget(self.mucin_peg_check)

        peg_lbl_mw = QLabel("PEG MW:")
        peg_lbl_mw.setStyleSheet("color: #cdd6f4; font-size: 11px; padding-left: 12px;")
        peg_row.addWidget(peg_lbl_mw)

        self.mucin_peg_mw = QDoubleSpinBox()
        self.mucin_peg_mw.setRange(500.0, 40000.0)
        self.mucin_peg_mw.setValue(5000.0)  # PEG 5k -- common choice
        self.mucin_peg_mw.setSingleStep(1000.0)
        self.mucin_peg_mw.setDecimals(0)
        self.mucin_peg_mw.setSuffix(" Da")
        self.mucin_peg_mw.setEnabled(False)
        peg_row.addWidget(self.mucin_peg_mw)

        peg_lbl_dens = QLabel("밀도:")
        peg_lbl_dens.setStyleSheet("color: #cdd6f4; font-size: 11px; padding-left: 8px;")
        peg_row.addWidget(peg_lbl_dens)

        self.mucin_peg_density = QDoubleSpinBox()
        self.mucin_peg_density.setRange(0.01, 1.0)
        self.mucin_peg_density.setValue(0.1)
        self.mucin_peg_density.setSingleStep(0.05)
        self.mucin_peg_density.setDecimals(2)
        self.mucin_peg_density.setSuffix(" chains/nm²")
        self.mucin_peg_density.setEnabled(False)
        peg_row.addWidget(self.mucin_peg_density)

        self.mucin_peg_check.toggled.connect(self.mucin_peg_mw.setEnabled)
        self.mucin_peg_check.toggled.connect(self.mucin_peg_density.setEnabled)

        peg_row.addStretch()
        input_layout.addRow("PEG 코팅:", peg_widget)

        # Auto-fill button
        btn_mucin_autofill = QPushButton("현재 리간드에서 가져오기")
        btn_mucin_autofill.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        btn_mucin_autofill.clicked.connect(self._mucin_autofill_from_ligand)
        input_layout.addRow("", btn_mucin_autofill)

        layout.addWidget(input_group)

        # --- Action buttons ---
        btn_row = QHBoxLayout()

        self.btn_mucin_run = QPushButton("Mucin 장벽 분석 실행")
        self.btn_mucin_run.setStyleSheet(
            "QPushButton { background-color: #9C27B0; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #7B1FA2; }"
            "QPushButton:disabled { background-color: #666; }"
        )
        self.btn_mucin_run.clicked.connect(self._on_mucin_run)

        self.btn_mucin_sweep = QPushButton("NAC 농도 스윕 (0~20 mM)")
        self.btn_mucin_sweep.setStyleSheet(
            "QPushButton { background-color: #E91E63; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #C2185B; }"
            "QPushButton:disabled { background-color: #666; }"
        )
        self.btn_mucin_sweep.clicked.connect(self._on_mucin_nac_sweep)

        btn_row.addStretch()
        btn_row.addWidget(self.btn_mucin_run)
        btn_row.addWidget(self.btn_mucin_sweep)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- Progress ---
        self.mucin_progress_label = QLabel("")
        self.mucin_progress_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        layout.addWidget(self.mucin_progress_label)

        # --- Results area (splitter: chart left, report right) ---
        self.mucin_results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: matplotlib chart area
        self.mucin_chart_container = QWidget()
        chart_layout = QVBoxLayout(self.mucin_chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_title = QLabel("Ogston 체거름 / 거담제 용량-반응 차트")
        chart_title.setStyleSheet("font-weight: bold; padding: 2px;")
        chart_layout.addWidget(chart_title)

        if MATPLOTLIB_AVAILABLE:
            self.mucin_figure = Figure(figsize=(5, 4), dpi=100)
            self.mucin_figure.patch.set_facecolor('#1e1e2e')
            self.mucin_canvas_widget = FigureCanvas(self.mucin_figure)
            self.mucin_canvas_widget.setMinimumHeight(300)
            chart_layout.addWidget(self.mucin_canvas_widget)
        else:
            no_mpl = QLabel("matplotlib 미설치 — 차트를 표시할 수 없습니다.")
            no_mpl.setStyleSheet("color: #FF9800; padding: 20px;")
            chart_layout.addWidget(no_mpl)

        self.mucin_results_splitter.addWidget(self.mucin_chart_container)

        # Right: text report
        self.mucin_report_text = QTextEdit()
        self.mucin_report_text.setReadOnly(True)
        self.mucin_report_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "font-family: 'Consolas', 'D2Coding', monospace; font-size: 11px; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 6px; }"
        )
        self.mucin_report_text.setPlaceholderText(
            "약물 SMILES를 입력하고 'Mucin 장벽 분석 실행'을 클릭하세요.\n\n"
            "분석 내용:\n"
            "  - Ogston 체거름(sieving) 확률\n"
            "  - pH 의존적 메쉬 크기\n"
            "  - 정전기적 상호작용 (시알산 전하)\n"
            "  - 거담제(NAC/DTT/TCEP) S-S 절단\n"
            "  - PEGylation 스텔스 효과"
        )
        self.mucin_results_splitter.addWidget(self.mucin_report_text)

        self.mucin_results_splitter.setSizes([500, 500])
        layout.addWidget(self.mucin_results_splitter, 1)

        # --- Bottom: real-time display ---
        self.mucin_realtime_group = QGroupBox("실시간 결과 요약")
        self.mucin_realtime_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #555; "
            "border-radius: 4px; margin-top: 4px; padding-top: 14px; }"
            "QGroupBox::title { subcontrol-position: top left; padding: 0 6px; }"
        )
        rt_layout = QHBoxLayout(self.mucin_realtime_group)

        self.mucin_mesh_label = QLabel("메쉬 크기: —")
        self.mucin_mesh_label.setStyleSheet("color: #9C27B0; font-size: 13px; font-weight: bold;")
        rt_layout.addWidget(self.mucin_mesh_label)

        self.mucin_pen_label = QLabel("투과 확률: —")
        self.mucin_pen_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        rt_layout.addWidget(self.mucin_pen_label)

        self.mucin_electro_label = QLabel("정전기: —")
        self.mucin_electro_label.setStyleSheet("color: #FF9800; font-size: 13px; font-weight: bold;")
        rt_layout.addWidget(self.mucin_electro_label)

        self.mucin_class_label = QLabel("분류: —")
        self.mucin_class_label.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        rt_layout.addWidget(self.mucin_class_label)

        layout.addWidget(self.mucin_realtime_group)

        # Internal state
        self._mucin_thread = None
        self._mucin_result: Optional[MucinAnalysisResult] = None

        return widget

    def _on_mucin_ph_changed(self, value: float):
        """Update mucin pH label with expected mesh size."""
        # Approximate mesh size from pH (simplified from calculate_ph_dependent_mesh_size)
        base_mesh = 340.0 * (20.0 / max(self.mucin_conc_spin.value(), 1.0)) ** 0.5
        if value < 3.0:
            mesh_est = base_mesh * 0.2
            desc = "위액 (고농축)"
        elif value < 5.0:
            mesh_est = base_mesh * 0.5
            desc = "십이지장 (부분 농축)"
        elif value < 6.5:
            mesh_est = base_mesh * 0.8
            desc = "소장 상부"
        elif value < 7.8:
            mesh_est = base_mesh * 1.0
            desc = "생리적"
        else:
            mesh_est = base_mesh * 1.3
            desc = "알칼리 팽윤"
        self.mucin_ph_label.setText(
            f"pH {value:.1f} — 메쉬 크기: ~{mesh_est:.0f} nm ({desc})"
        )

    def _mucin_autofill_from_ligand(self):
        """Auto-fill mucin SMILES from current ligand."""
        if self.ligand and hasattr(self.ligand, 'smiles') and self.ligand.smiles:
            self.mucin_smiles_input.setText(self.ligand.smiles)
            self.mucin_name_input.setText(getattr(self.ligand, 'name', '')[:50])
            self.mucin_progress_label.setText("리간드에서 SMILES 가져옴")
        elif hasattr(self, 'smiles_input') and self.smiles_input.text().strip():
            self.mucin_smiles_input.setText(self.smiles_input.text().strip())
            self.mucin_progress_label.setText("설정 탭 SMILES에서 가져옴")
        else:
            QMessageBox.information(
                self, "알림",
                "먼저 설정 탭에서 리간드 SMILES를 입력하거나 도킹을 실행하세요."
            )

    def _on_mucin_run(self):
        """Run mucin barrier analysis via QThread."""
        smiles = self.mucin_smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "약물 SMILES를 입력하세요.")
            return

        mol_name = self.mucin_name_input.text().strip() or smiles[:20]
        pH = self.mucin_ph_spin.value()
        conc = self.mucin_conc_spin.value()
        radius = self.mucin_radius_spin.value()

        # Mucolytic agent
        mucolytic_agent = self.mucin_mucolytic_combo.currentData()
        if not mucolytic_agent:
            mucolytic_agent = None
        mucolytic_conc = self.mucin_mucolytic_conc.value()

        # PEGylation
        peg_mw = self.mucin_peg_mw.value() if self.mucin_peg_check.isChecked() else 0.0
        peg_density = self.mucin_peg_density.value() if self.mucin_peg_check.isChecked() else 0.0

        self.btn_mucin_run.setEnabled(False)
        self.btn_mucin_sweep.setEnabled(False)
        self.mucin_progress_label.setText(
            f"pH {pH:.1f}, 뮤신 {conc:.0f} mg/mL 에서 분석 중..."
        )

        self._mucin_thread = MucinAnalysisThread(
            drug_smiles=smiles,
            drug_name=mol_name,
            pH=pH,
            mucin_conc_mg_ml=conc,
            mucolytic_agent=mucolytic_agent,
            mucolytic_conc_mM=mucolytic_conc,
            peg_mw=peg_mw,
            peg_density=peg_density,
            particle_radius_nm=radius,
            parent=self,
        )
        self._mucin_thread.finished.connect(self._on_mucin_finished)
        self._mucin_thread.progress.connect(
            lambda msg: self.mucin_progress_label.setText(msg))
        self._mucin_thread.error.connect(self._on_mucin_error)
        self._mucin_thread.start()

    def _on_mucin_nac_sweep(self):
        """Run NAC concentration sweep (0-20 mM) for smoke test visualization."""
        smiles = self.mucin_smiles_input.text().strip()
        if not smiles:
            QMessageBox.warning(self, "알림", "약물 SMILES를 입력하세요.")
            return

        mol_name = self.mucin_name_input.text().strip() or smiles[:20]
        pH = self.mucin_ph_spin.value()
        conc = self.mucin_conc_spin.value()

        self.btn_mucin_run.setEnabled(False)
        self.btn_mucin_sweep.setEnabled(False)
        self.mucin_progress_label.setText("NAC 농도 스윕 분석 중 (0~20 mM)...")

        try:
            concentrations = [0.0, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0]
            report_lines = [
                f"== NAC 농도 스윕 (Mucin 장벽) ==",
                f"분자: {mol_name}",
                f"SMILES: {smiles}",
                f"pH: {pH:.1f} | 뮤신 농도: {conc:.0f} mg/mL",
                "",
                f"{'NAC (mM)':<12} {'S-S 절단(%)':<14} {'메쉬(nm)':<12} {'점도비':<10} {'투과확률':<12} {'분류'}",
                "-" * 80,
            ]

            for nac_conc in concentrations:
                result = run_mucin_analysis(
                    drug_smiles=smiles,
                    drug_name=mol_name,
                    pH=pH,
                    mucin_conc_mg_ml=conc,
                    mucolytic_agent="N-acetylcysteine" if nac_conc > 0 else None,
                    mucolytic_conc_mM=nac_conc,
                )
                if not result.success:
                    report_lines.append(f"{nac_conc:<12.1f} 오류: {result.error}")
                    continue

                # Get drug's Ogston result (first in list)
                og = result.ogston_results[0] if result.ogston_results else None
                mr = result.mucolytic_result
                if og:
                    ss_frac = mr.fraction_cleaved * 100 if mr else 0.0
                    mesh_after = mr.mesh_size_after_nm if mr else og.mesh_size_nm
                    visc = mr.viscosity_ratio if mr else 1.0
                    report_lines.append(
                        f"{nac_conc:<12.1f} {ss_frac:<14.1f} {mesh_after:<12.1f} "
                        f"{visc:<10.4f} {og.penetration_probability:<12.4f} {og.classification}"
                    )

            self.mucin_report_text.setPlainText("\n".join(report_lines))
            self.mucin_progress_label.setText(
                f"NAC 스윕 완료 — {len(concentrations)}개 농도 포인트 분석됨"
            )

            # Draw mucolytic dose-response chart
            if MATPLOTLIB_AVAILABLE and hasattr(self, 'mucin_figure'):
                nac_concs = [c for c in concentrations if c > 0]
                png_bytes = generate_mucolytic_chart(
                    "N-acetylcysteine", nac_concs,
                )
                if png_bytes:
                    self._draw_mucin_chart_from_bytes(png_bytes)

        except Exception as e:
            QMessageBox.critical(self, "NAC 스윕 오류", str(e))
            logger.warning("NAC sweep error: %s", e, exc_info=True)
        finally:
            self.btn_mucin_run.setEnabled(True)
            self.btn_mucin_sweep.setEnabled(True)

    def _on_mucin_error(self, msg: str):
        """Handle mucin analysis error."""
        self.btn_mucin_run.setEnabled(True)
        self.btn_mucin_sweep.setEnabled(True)
        self.mucin_progress_label.setText(f"오류: {msg}")
        QMessageBox.critical(self, "Mucin 분석 오류", msg)

    def _on_mucin_finished(self, result: 'MucinAnalysisResult'):
        """Handle completed mucin barrier analysis."""
        self.btn_mucin_run.setEnabled(True)
        self.btn_mucin_sweep.setEnabled(True)

        # N-code: type guard — result from MucinAnalysisThread signal
        if result is not None and not isinstance(result, MucinAnalysisResult):
            logger.warning("[DockingPopup] mucin result is not MucinAnalysisResult: type=%s",
                           type(result).__name__)
            self.mucin_progress_label.setText("분석 결과 형식 오류")
            return

        self._mucin_result = result

        if not result or not result.success:
            err = getattr(result, 'error', '알 수 없는 오류')
            self.mucin_progress_label.setText(f"분석 실패: {err}")
            return

        # Status line
        ns = result.network_stats
        if not isinstance(ns, dict):
            logger.warning("mucin network_stats not dict: %s", type(ns))
            ns = {}
        drug_og = result.ogston_results[0] if result.ogston_results else None
        self.mucin_progress_label.setText(
            f"분석 완료 — 메쉬: {ns.get('mesh_size_nm', 0):.1f} nm, "
            f"투과: {drug_og.penetration_probability:.4f}" if drug_og else "분석 완료"
        )

        # Text report
        report = format_mucin_report(result)
        self.mucin_report_text.setPlainText(report)

        # Update real-time labels
        self.mucin_mesh_label.setText(f"메쉬: {ns.get('mesh_size_nm', 0):.1f} nm")

        if drug_og:
            pen_p = drug_og.penetration_probability
            self.mucin_pen_label.setText(f"투과: {pen_p:.4f}")
            # Color-code
            if pen_p > 0.5:
                color = "#4CAF50"
            elif pen_p > 0.1:
                color = "#FF9800"
            else:
                color = "#F44336"
            self.mucin_pen_label.setStyleSheet(
                f"color: {color}; font-size: 13px; font-weight: bold;")

            class_kr: dict = {
                "freely permeable": "자유 투과",
                "partially sieved": "부분 체거름",
                "mostly trapped": "대부분 포획",
                "completely trapped": "완전 포획",
            }
            assert isinstance(class_kr, dict)  # Rule N: 타입 가드
            self.mucin_class_label.setText(
                f"분류: {class_kr.get(drug_og.classification, drug_og.classification)}"
            )

        if result.electrostatic_result:
            er = result.electrostatic_result
            self.mucin_electro_label.setText(
                f"정전기: {er.interaction_type} ({er.interaction_energy_kT:.2f} kT)"
            )

        # Draw Ogston chart
        if MATPLOTLIB_AVAILABLE and hasattr(self, 'mucin_figure') and result.ogston_results:
            png_bytes = generate_ogston_chart(result.ogston_results)
            if png_bytes:
                self._draw_mucin_chart_from_bytes(png_bytes)

    def _draw_mucin_chart_from_bytes(self, png_bytes: bytes):
        """Render PNG bytes into the mucin matplotlib canvas."""
        if not MATPLOTLIB_AVAILABLE or not hasattr(self, 'mucin_figure'):
            return

        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(png_bytes))
            self.mucin_figure.clear()
            ax = self.mucin_figure.add_subplot(1, 1, 1)
            ax.set_facecolor('#1e1e2e')
            ax.imshow(img)
            ax.axis('off')
            self.mucin_figure.tight_layout(pad=0)
            self.mucin_canvas_widget.draw()
        except Exception as e:
            logger.warning("Mucin chart render failed: %s", e)

    # ------------------------------------------------------------------ AlphaFold → Docking (M461)
    def set_receptor_from_alphafold(self, payload: dict) -> None:
        """[M461] Sub-task 1: AlphaFold 결과에서 수용체 정보 자동 설정.

        Rule N: payload는 dict 타입 강제 — AlphaFold 시그널에서 dict 전달 보장되지만
                호출부 오류 방어를 위해 isinstance 가드 필수.
        Rule M: payload 필드 누락 시 silent return 금지 — logger.warning.

        Args:
            payload: alphafold_to_docking 시그널 dict
                {pdb_path, uniprot_id, plddt_summary, binding_residues, binding_center}
        """
        # Rule N: isinstance 타입 가드 — dict 이외 타입 방어
        if not isinstance(payload, dict):
            logger.warning(
                "set_receptor_from_alphafold: payload 타입 오류 — dict 필요, 받은 타입: %s",
                type(payload).__name__,
            )
            self.status_label.setText("[경고] AlphaFold 전달 데이터 형식 오류")
            return

        uniprot_id = payload.get("uniprot_id", "")
        pdb_path = payload.get("pdb_path", "")
        plddt_summary = payload.get("plddt_summary", {})
        binding_residues = payload.get("binding_residues", [])
        binding_center = payload.get("binding_center", {})

        # Rule N: 타입 가드 — dict/list/str 혼재 가능성 방어
        if not isinstance(plddt_summary, dict):
            logger.warning("set_receptor_from_alphafold: plddt_summary 타입 오류: %s",
                           type(plddt_summary).__name__)
            plddt_summary = {}
        if not isinstance(binding_residues, list):
            logger.warning("set_receptor_from_alphafold: binding_residues 타입 오류: %s",
                           type(binding_residues).__name__)
            binding_residues = []
        if not isinstance(binding_center, dict):
            logger.warning("set_receptor_from_alphafold: binding_center 타입 오류: %s",
                           type(binding_center).__name__)
            binding_center = {}

        # 유효성 확인
        if not uniprot_id and not pdb_path:
            logger.warning(
                "set_receptor_from_alphafold: uniprot_id와 pdb_path 모두 비어 있음 — "
                "결합부위 정보만 적용합니다."
            )

        # PDB 파일이 있으면 receptor_path_label에 표시
        if pdb_path and os.path.isfile(pdb_path):
            self.receptor_path_label.setText(f"AlphaFold PDB: {os.path.basename(pdb_path)}")
            self.receptor_path_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            # PDB 로드 시도
            try:
                parser = PDBParser()
                rec = parser.parse_pdb_file(pdb_path)
                if rec is not None:
                    self.receptor = rec
                    logger.info("set_receptor_from_alphafold: PDB 파일 로드 성공: %s", pdb_path)
            except Exception as e:
                logger.warning("set_receptor_from_alphafold: PDB 파일 로드 실패: %s", e)
        elif uniprot_id:
            # UniProt ID 기반 AlphaFold → 수용체 정보 표시
            self.receptor_path_label.setText(
                f"AlphaFold: {uniprot_id} "
                f"(avg pLDDT: {plddt_summary.get('avg_plddt', 0.0):.1f})"
            )
            self.receptor_path_label.setStyleSheet("color: #1976D2; font-weight: bold;")

        # 결합부위 정보 — receptor_info QLabel에 마커 표시
        if binding_residues:
            avg_plddt = plddt_summary.get("avg_plddt", 0.0)
            # pLDDT 0~100 범위 검증 (Rule N: 이론적 정합성)
            if not isinstance(avg_plddt, (int, float)) or not (0.0 <= avg_plddt <= 100.0):
                logger.warning(
                    "set_receptor_from_alphafold: avg_plddt 범위 오류: %s — 0~100 기대",
                    avg_plddt
                )
                avg_plddt = 0.0

            # 결합부위 중심 좌표 추출
            cx = binding_center.get("x", 0.0)
            cy = binding_center.get("y", 0.0)
            cz = binding_center.get("z", 0.0)

            residue_names = [
                r.get("resname", "") for r in binding_residues[:8]
                if isinstance(r, dict)
            ]
            self.receptor_info.setText(
                f"AlphaFold 결합부위: {', '.join(residue_names)}"
                f"{'...' if len(binding_residues) > 8 else ''}\n"
                f"중심 좌표: ({cx:.1f}, {cy:.1f}, {cz:.1f}) | "
                f"평균 pLDDT: {avg_plddt:.1f}"
            )
            self.receptor_info.setStyleSheet(
                "color: #E65100; font-size: 9pt; "
                "background: #FFF3E0; padding: 4px; border-radius: 3px;"
            )

            # AlphaFold 데이터를 popup에 저장 (DryLab 전달용)
            self._alphafold_payload = payload
            logger.info(
                "set_receptor_from_alphafold: 적용 완료 — uniprot_id=%s, "
                "binding_residues=%d개, center=(%.1f,%.1f,%.1f), avg_plddt=%.1f",
                uniprot_id or "(없음)",
                len(binding_residues),
                cx, cy, cz,
                avg_plddt,
            )
        else:
            logger.warning(
                "set_receptor_from_alphafold: binding_residues 비어 있음 — "
                "결합부위 마커 미표시"
            )

        self.status_label.setText(
            f"AlphaFold에서 수용체 정보 전달됨: {uniprot_id or pdb_path or '(정보 없음)'}"
        )

    # ── [M853 格忿#31] 외부 도킹 서비스 메서드 3종 ──────────────────────────
    # Karpathy K2: 각 메서드 50줄 이내. K3: 이 파일 내에만 추가.
    # Rule I: URL 매직넘버 상수 → 주석 필수. Rule M: silent return 금지.
    # 학술 인용:
    #   Grosdidier A. et al. (2011) Nucleic Acids Res. 39:W270-W277. (SwissDock)
    #   Eberhardt J. et al. (2021) J.Chem.Inf.Model. 61:3891-3898. (Vina 1.2)
    #   Sehnal D. et al. (2021) Nucleic Acids Res. 49:W431-W437. (Mol*/PDBe)

    def _get_docking_pdb_id(self) -> str:
        """현재 수용체 PDB ID를 안전하게 추출. Rule N: 타입 가드 필수."""
        pdb_id = ""
        if self.receptor is not None and isinstance(self.receptor, ReceptorData):
            pdb_id = getattr(self.receptor, 'pdb_id', '') or ''
        if not pdb_id:
            try:
                pdb_id = self.pdb_id_input.text().strip().upper()
            except Exception as e:
                logger.warning("[_get_docking_pdb_id] pdb_id_input 읽기 실패: %s", e)
        return pdb_id

    def _get_docking_smiles(self) -> str:
        """현재 리간드 SMILES를 안전하게 추출. Rule N: 타입 가드 필수."""
        smiles = ""
        if self.ligand is not None:
            smiles = getattr(self.ligand, 'smiles', '') or ''
        if not smiles:
            try:
                smiles = self.smiles_input.text().strip()
            except Exception as e:
                logger.warning("[_get_docking_smiles] smiles_input 읽기 실패: %s", e)
        return smiles

    def _on_open_swissdock_external(self) -> None:
        """[M853 格忿#31] SwissDock 외부 도킹 서비스 열기.
        URL: https://www.swissdock.ch/docking (게스트 사용 가능)
        리간드 SMILES + 수용체 PDB ID 정보를 상태바 + QMessageBox로 안내.
        Rule M: 정보 없을 때 silent return 금지.
        Rule FF: 외부 서비스 prominent — Grosdidier 2011 인용.
        """
        import urllib.parse

        SWISSDOCK_BASE_URL = "https://www.swissdock.ch/docking"  # [MAGIC] SwissDock 공식 서비스 URL
        SWISSDOCK_HELP_URL = "https://www.swissdock.ch/docking#help"   # [MAGIC] 도움말
        VINA_DOWNLOAD_URL = "https://vina.scripps.edu/downloads/"      # [MAGIC] Vina 설치

        pdb_id = self._get_docking_pdb_id()
        smiles = self._get_docking_smiles()

        if not pdb_id and not smiles:
            logger.warning("[_on_open_swissdock_external] PDB ID + SMILES 모두 없음 (M853 Rule M)")
            QMessageBox.information(
                self, "SwissDock 외부 도킹",
                "수용체 PDB ID 또는 리간드 SMILES를 먼저 설정하세요.\n\n"
                "사용 방법:\n"
                "1. '설정' 탭 → 수용체 PDB ID 입력 → 'RCSB에서 다운로드'\n"
                "2. 리간드 SMILES 입력 또는 캔버스에서 분자 추출\n"
                "3. 이 버튼을 다시 클릭하면 SwissDock 안내 팝업이 열립니다.\n\n"
                f"SwissDock: {SWISSDOCK_BASE_URL}\n"
                "학술 인용: Grosdidier et al. 2011 NAR 39:W270-W277"
            )
            QDesktopServices.openUrl(QUrl(SWISSDOCK_BASE_URL))
            return

        # SwissDock은 웹 폼 방식 — 직접 URL 파라미터 없음 (게스트 업로드 필요)
        # 따라서 서비스 메인 URL + 복사할 정보를 안내 팝업으로 제공
        info_msg = (
            f"SwissDock 외부 도킹 서비스를 브라우저에서 엽니다.\n\n"
            f"다음 정보를 SwissDock에 입력하세요:\n"
        )
        if pdb_id:
            info_msg += f"  수용체 PDB ID: {pdb_id}\n"
        if smiles:
            info_msg += f"  리간드 SMILES: {smiles}\n"
        info_msg += (
            "\n결과에서 확인할 수 있는 정보:\n"
            "  - 결합 에너지 (kcal/mol) — 값이 낮을수록 강한 결합\n"
            "  - 결합 방향 (3D 포즈) — 리간드가 결합 포켓에 들어가는 방향\n"
            "  - 결합 부위 잔기 (Interacting residues)\n\n"
            "학술 인용: Grosdidier et al. 2011 NAR 39:W270-W277\n"
            f"URL: {SWISSDOCK_BASE_URL}"
        )
        logger.info(
            "[_on_open_swissdock_external] SwissDock 열기 — pdb=%s smiles=%s",
            pdb_id, smiles[:30] if smiles else "(없음)"
        )
        self.status_label.setText(
            f"SwissDock 외부 도킹 — 브라우저에서 결합 강도/방향을 확인하세요. "
            f"(수용체: {pdb_id or '미지정'}, 리간드: {smiles[:20] if smiles else '미지정'})"
        )
        # 상태 정보 업데이트
        if hasattr(self, 'ext_docking_info'):
            self.ext_docking_info.setText(
                f"SwissDock 정보 — 수용체: {pdb_id or '미지정'} | "
                f"리간드: {smiles[:25] if smiles else '미지정'} | "
                "브라우저에서 결합 에너지(kcal/mol) + 3D 포즈 확인"
            )
        QMessageBox.information(self, "SwissDock 외부 도킹 서비스", info_msg)
        # Rule S: QDesktopServices.openUrl — PyQt6 공식 API
        QDesktopServices.openUrl(QUrl(SWISSDOCK_BASE_URL))

    def _on_open_pdbe_kb_binding(self) -> None:
        """[M853 格忿#31] PDBe-KB 결합 부위 + 상호작용 데이터 열기.
        URL: https://www.ebi.ac.uk/pdbe/pdbe-kb/proteins/{UniProt}/ligands
        수용체 PDB ID → 결합 잔기 + 상호작용 파트너 데이터.
        Rule M: silent return 금지. Rule FF: Sehnal 2021 인용.
        """
        PDBE_KB_BASE = "https://www.ebi.ac.uk/pdbe/pdbe-kb/proteins"  # [MAGIC] PDBe-KB UniProt 기반
        PDBE_ENTRY_BASE = "https://www.ebi.ac.uk/pdbe/entry/pdb"      # [MAGIC] PDBe 항목 직접 링크

        pdb_id = self._get_docking_pdb_id()
        if not pdb_id:
            logger.warning("[_on_open_pdbe_kb_binding] PDB ID 없음 (M853 Rule M)")
            QMessageBox.information(
                self, "PDBe-KB 결합 데이터",
                "수용체 PDB ID를 먼저 입력하세요.\n\n"
                "설정 탭에서 PDB ID를 입력하거나 프리셋에서 수용체를 선택하세요.\n\n"
                f"PDBe-KB: {PDBE_KB_BASE}\n"
                "학술 인용: Sehnal et al. 2021 NAR 49:W431-W437"
            )
            QDesktopServices.openUrl(QUrl(PDBE_KB_BASE))
            return

        # PDBe 항목 페이지 (Mol* 임베드 + 결합 부위 데이터)
        pdbe_url = f"{PDBE_ENTRY_BASE}/{pdb_id.lower()}"
        logger.info("[_on_open_pdbe_kb_binding] PDBe entry URL: %s", pdbe_url)
        self.status_label.setText(
            f"PDBe-KB 결합 데이터 — {pdb_id} 수용체 결합 부위 + 상호작용 잔기 (Sehnal 2021)"
        )
        if hasattr(self, 'ext_docking_info'):
            self.ext_docking_info.setText(
                f"PDBe-KB — 수용체 {pdb_id}: 결합 잔기 + 상호작용 파트너 조회 중 (브라우저)"
            )
        # Rule S: QDesktopServices.openUrl — PyQt6 공식 API
        QDesktopServices.openUrl(QUrl(pdbe_url))

    def _on_open_rcsb_3d_viewer(self) -> None:
        """[M853 格忿#31] RCSB PDB 3D 뷰어 — 결합 포켓 + 리간드 위치 확인.
        URL: https://www.rcsb.org/3d-view/{PDB_ID}
        Rule M: PDB ID 없을 때 silent return 금지.
        """
        RCSB_3D_BASE = "https://www.rcsb.org/3d-view"  # [MAGIC] RCSB 3D 뷰어 엔드포인트

        pdb_id = self._get_docking_pdb_id()
        if not pdb_id:
            logger.warning("[_on_open_rcsb_3d_viewer] PDB ID 없음 (M853 Rule M)")
            QMessageBox.information(
                self, "RCSB 3D 뷰어",
                "수용체 PDB ID를 먼저 입력하세요.\n\n"
                f"RCSB PDB: https://www.rcsb.org"
            )
            QDesktopServices.openUrl(QUrl("https://www.rcsb.org"))
            return

        rcsb_url = f"{RCSB_3D_BASE}/{pdb_id}"
        logger.info("[_on_open_rcsb_3d_viewer] RCSB 3D URL: %s", rcsb_url)
        self.status_label.setText(
            f"RCSB 3D 뷰어 — {pdb_id} 수용체 3D 구조 브라우저에서 확인"
        )
        # Rule S: QDesktopServices.openUrl — PyQt6 공식 API
        QDesktopServices.openUrl(QUrl(rcsb_url))

    # ── [M853] 도킹 완료 후 외부 링크 패널 업데이트 ──────────────────────────
    def _update_external_docking_panel(self) -> None:
        """도킹 완료 후 외부 링크 패널의 안내 라벨 갱신. (M853 신설)
        Rule M: silent failure 금지 — hasattr 체크 후 갱신.
        """
        if not hasattr(self, 'ext_docking_info'):
            return
        pdb_id = self._get_docking_pdb_id()
        smiles = self._get_docking_smiles()
        best_energy = ""
        if self.docking_result is not None:
            best = getattr(self.docking_result, 'best_pose', None)
            if best is not None:
                e = getattr(best, 'affinity', None)
                if e is not None:
                    best_energy = f" | 최고 결합 에너지: {e:.2f} kcal/mol"
        self.ext_docking_info.setText(
            f"도킹 완료 — 수용체: {pdb_id or '미지정'} | "
            f"리간드: {smiles[:20] if smiles else '미지정'}"
            f"{best_energy}\n"
            "SwissDock / PDBe-KB / RCSB 3D 버튼으로 결합 강도·방향·잔기 상세 확인"
        )
        self.ext_docking_info.setStyleSheet(
            "color: #a5d6a7; font-size: 9pt; background: transparent; border: none;"
        )

    def _on_open_pdbe_molstar(self) -> None:
        """[M461/M499] PDBe Mol* 학술 3D 시각화 — 도킹 전 PDB ID만으로도 동작.

        R-21 (M499): 단백질/도킹 3D는 PDBe Mol* 우선.
        우선순위:
          1. 도킹 complex PDB (로컬 파일 → file:// URL)
          2. 수용체 PDB ID (RCSB/PDBe 직접 링크)
          3. UniProt ID (AlphaFold DB 링크)
        Rule S: QDesktopServices.openUrl(QUrl) — PyQt6 공식 API.
        Rule M: 모든 실패 경로에 사용자 피드백 필수.
        인용: Sehnal et al. 2021 Nucleic Acids Res 49:W431-W437
        """
        # ── 1순위: 도킹 complex PDB (로컬 파일) ──
        complex_pdb_path = ""
        if self.docking_result is not None:
            complex_pdb_path = getattr(self.docking_result, 'complex_pdb_path', '') or ''
            if not complex_pdb_path:
                best = getattr(self.docking_result, 'best_pose', None)
                if best is not None:
                    complex_pdb_path = getattr(best, 'pdb_path', '') or ''
            if not complex_pdb_path:
                try:
                    import glob
                    candidates = glob.glob(str(self.work_dir / "*.pdb"))
                    if candidates:
                        complex_pdb_path = candidates[0]
                        logger.info("_on_open_pdbe_molstar: work_dir PDB 발견: %s", complex_pdb_path)
                except Exception as e:
                    logger.warning("_on_open_pdbe_molstar: work_dir PDB 탐색 실패: %s", e)

        if complex_pdb_path and os.path.isfile(complex_pdb_path):
            # [M678 FIX] 사용자 LV.14 item 14 — PDBe Mol* embed URL 404 해소
            # 변경 전: /pdbe/molstar/index.html?pdb-url=file://... → 404 (URL 변경됨)
            # 변경 후: molstar.org/viewer/?pdb-url={file_url} (공식 Mol* 뷰어)
            # 학술 인용 (Rule NN): Sehnal D. et al. 2021 NAR 49:W431-W437
            import urllib.parse
            abs_path = os.path.abspath(complex_pdb_path)
            file_url = abs_path.replace("\\", "/")
            if not file_url.startswith("/"):
                file_url = "/" + file_url
            encoded_url = urllib.parse.quote(file_url, safe="/:@")
            molstar_url = (
                f"https://molstar.org/viewer/"
                f"?pdb-url=file://{encoded_url}"
            )
            logger.info("_on_open_pdbe_molstar: complex PDB → Mol* URL: %s", molstar_url)
            # Rule S: QDesktopServices.openUrl — PyQt6 공식 API
            QDesktopServices.openUrl(QUrl(molstar_url))
            self.status_label.setText(
                "PDBe Mol* 학술 시각화 — 브라우저에서 도킹 complex를 확인하세요.\n"
                "(Sehnal et al. 2021 NAR W431-W437)"
            )
            return

        # ── 2순위: 수용체 PDB ID → PDBe 직접 링크 (M499: 도킹 전에도 동작) ──
        # Rule N: isinstance 타입 가드
        pdb_id = ""
        if self.receptor is not None and isinstance(self.receptor, ReceptorData):
            pdb_id = getattr(self.receptor, 'pdb_id', '') or ''
        if not pdb_id:
            # 설정 탭 PDB ID 입력창에서 읽기
            pdb_id_text = ""
            try:
                pdb_id_text = self.pdb_id_input.text().strip()
            except Exception as e:
                logger.warning("_on_open_pdbe_molstar: pdb_id_input 읽기 실패: %s", e)
            pdb_id = pdb_id_text

        if pdb_id:
            # [M678 FIX] 사용자 LV.14 item 14 — PDBe Mol* embed URL 404 해소
            # 변경 전: /pdbe/molstar/index.html?pdbId={id} → 404
            # 변경 후: /pdbe/entry/pdb/{id} (PDBe entry, Mol*가 임베드된 학술 표준 페이지)
            pdbe_url = f"https://www.ebi.ac.uk/pdbe/entry/pdb/{pdb_id.lower()}"
            logger.info("_on_open_pdbe_molstar: 수용체 PDB ID %s → PDBe entry URL: %s", pdb_id, pdbe_url)
            # Rule S: QDesktopServices.openUrl + QUrl — PyQt6 공식 패턴
            QDesktopServices.openUrl(QUrl(pdbe_url))
            self.status_label.setText(
                f"PDBe Mol* 학술 시각화 — 수용체 {pdb_id} 구조를 브라우저에서 확인하세요.\n"
                f"도킹 완료 후에는 복합체 구조도 확인 가능합니다."
            )
            QMessageBox.information(
                self, "PDBe Mol* 학술 시각화",
                f"브라우저에서 PDBe Mol*가 열렸습니다.\n\n"
                f"수용체: {pdb_id}\n"
                f"URL: {pdbe_url}\n\n"
                f"도킹 시뮬레이션 실행 후에는 복합체 구조가 자동으로 로드됩니다.\n"
                f"학술 인용: Sehnal et al. 2021 NAR 49:W431-W437"
            )
            return

        # ── 3순위: UniProt ID → AlphaFold DB 링크 ──
        alphafold_payload = getattr(self, '_alphafold_payload', {})
        if isinstance(alphafold_payload, dict):
            uniprot_id = alphafold_payload.get("uniprot_id", "")
            if uniprot_id:
                url = f"https://alphafold.ebi.ac.uk/entry/{uniprot_id}"
                logger.info("_on_open_pdbe_molstar: UniProt %s → AlphaFold DB: %s", uniprot_id, url)
                QDesktopServices.openUrl(QUrl(url))
                self.status_label.setText(
                    f"AlphaFold DB ({uniprot_id}) 열기 — 브라우저에서 확인하세요."
                )
                return

        # ── 모든 경로 실패 → 사용자 안내 (Rule M: silent return 금지) ──
        logger.warning(
            "_on_open_pdbe_molstar: complex PDB / PDB ID / UniProt ID 모두 미발견 — "
            "수용체를 먼저 설정하세요 (M499 R-21)"
        )
        QMessageBox.information(
            self, "PDBe Mol* 학술 시각화",
            "PDB ID 또는 수용체 정보를 먼저 입력하세요.\n\n"
            "방법:\n"
            "1. '설정' 탭에서 PDB ID 입력 후 'RCSB에서 다운로드'\n"
            "2. AlphaFold 팝업에서 '도킹으로 보내기'\n"
            "3. 도킹 시뮬레이션 실행 후 다시 클릭\n\n"
            "학술 인용: Sehnal et al. 2021 NAR 49:W431-W437"
        )

    def _on_export_docking_pose_sdf(self) -> None:
        """[M499 Task 2] 현재 도킹 pose → SDF 파일 내보내기 (PDBe Mol* 업로드용).

        Rule M: docking_result 없을 때 silent return 금지.
        Rule L: RDKIT mol 파싱 후 None 체크 필수.
        인용: Sehnal et al. 2021 NAR W431-W437 (PDBe Mol* 업로드 포맷)
        """
        if self.docking_result is None:
            logger.warning("_on_export_docking_pose_sdf: docking_result 없음 — 도킹 먼저 실행")
            QMessageBox.warning(
                self, "SDF 내보내기",
                "도킹 시뮬레이션을 먼저 실행하세요.\n"
                "결과가 없어 SDF를 내보낼 수 없습니다."
            )
            return

        if not RDKIT_AVAILABLE:
            logger.warning("_on_export_docking_pose_sdf: RDKit 미설치 — SDF 내보내기 불가")
            QMessageBox.warning(
                self, "SDF 내보내기",
                "RDKit이 설치되지 않아 SDF를 내보낼 수 없습니다.\n"
                "conda install -c conda-forge rdkit"
            )
            return

        # 현재 선택 pose 인덱스 — pose_table 또는 viewer_pose_selector에서
        pose_idx = 0
        try:
            if hasattr(self, 'viewer_pose_selector'):
                pose_idx = max(0, self.viewer_pose_selector.currentIndex())
        except Exception as e:
            logger.warning("_on_export_docking_pose_sdf: pose_idx 읽기 실패: %s", e)

        poses = getattr(self.docking_result, 'poses', [])
        if not isinstance(poses, list) or not poses:
            logger.warning(
                "_on_export_docking_pose_sdf: poses 비어 있음 (M499 Rule M)"
            )
            QMessageBox.warning(self, "SDF 내보내기", "도킹 포즈가 없습니다.")
            return

        # Rule N: 인덱스 범위 가드
        pose_idx = min(pose_idx, len(poses) - 1)
        pose = poses[pose_idx]

        # mol 객체 추출 (DockingPose.mol 또는 pdbqt_path 기반)
        mol = getattr(pose, 'mol', None)
        if mol is None:
            # PDBQT 파일에서 RDKit mol 로드 시도
            pdbqt_path = getattr(pose, 'pdbqt_path', '')
            if pdbqt_path and os.path.isfile(pdbqt_path):
                try:
                    from rdkit import Chem
                    mol = Chem.MolFromPDBFile(str(pdbqt_path), removeHs=False)
                except Exception as e:
                    logger.warning("_on_export_docking_pose_sdf: PDBQT→mol 변환 실패: %s", e)

        if mol is None:
            # Rule M: silent return 금지
            logger.warning(
                "_on_export_docking_pose_sdf: mol 객체 없음 — pose_idx=%d (M499)",
                pose_idx,
            )
            QMessageBox.warning(
                self, "SDF 내보내기",
                f"Pose {pose_idx + 1}의 분자 구조를 추출할 수 없습니다.\n"
                "리간드를 다시 설정하거나 도킹을 재실행하세요."
            )
            return

        # SDF 파일 저장 — Downloads 폴더
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        receptor_id = ""
        if self.receptor is not None:
            receptor_id = getattr(self.receptor, 'pdb_id', '') or ''
        filename = f"docking_pose_p{pose_idx + 1}_{receptor_id}_{ts}.sdf".strip("_")
        out_path = Path.home() / "Downloads" / filename

        try:
            from rdkit import Chem
            writer = Chem.SDWriter(str(out_path))
            writer.write(mol)
            writer.close()
            logger.info("_on_export_docking_pose_sdf: 저장 완료 %s", out_path)
        except Exception as e:
            logger.warning("_on_export_docking_pose_sdf: SDF 저장 실패: %s", e)
            QMessageBox.warning(self, "SDF 내보내기", f"SDF 저장 실패: {e}")
            return

        self.status_label.setText(f"SDF 내보내기 완료: {out_path}")
        QMessageBox.information(
            self, "SDF 내보내기 완료",
            f"도킹 Pose {pose_idx + 1} SDF 저장 완료:\n{out_path}\n\n"
            f"PDBe Mol* (https://www.ebi.ac.uk/pdbe/molstar/)에서 이 파일을\n"
            f"업로드하여 도킹 결과를 학술 품질로 확인하세요.\n\n"
            f"학술 인용: Sehnal et al. 2021 NAR 49:W431-W437"
        )

    # ========== [M851 格忿#29] AI 채팅 탭 — Grok via OpenRouter ==========

    def _create_ai_chat_tab(self) -> QWidget:
        """Grok AI 채팅창 — 학생이 자연어로 수용체 질문 → 응답 + 드롭다운 강조.
        Rule I: API 키 소스코드 금지 (.env / OPENROUTER_API_KEY 환경변수 전용).
        Rule M: silent failure 금지.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- 헤더 ---
        header = QLabel("AI 수용체 추천 채팅 (Grok AI)")
        header.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #7C4DFF; padding: 4px;"
        )
        layout.addWidget(header)

        # API 키 상태 표시
        api_key = self._get_openrouter_key()
        if api_key:
            key_status = QLabel("OpenRouter API 연결됨 (Grok AI 사용 가능)")
            key_status.setStyleSheet("color: #4caf50; font-size: 11px; padding: 2px;")
        else:
            key_status = QLabel(
                "OPENROUTER_API_KEY 미설정 — .env 파일에 OPENROUTER_API_KEY=sk-or-... 추가 필요"
            )
            key_status.setStyleSheet("color: #ff9800; font-size: 11px; padding: 2px;")
        key_status.setWordWrap(True)
        layout.addWidget(key_status)
        self._ai_chat_key_status = key_status

        # 사용 안내
        guide = QLabel(
            "학생 예시 질문:\n"
            "• 경구 투여되었을 때 결합 가능한 인슐린 작용 관련 단백질을 정리해 줘\n"
            "• 아세틸콜린 분해와 관련된 효소 수용체를 알려줘\n"
            "• 도파민 수용체 중 파킨슨병과 관련된 것은?"
        )
        guide.setStyleSheet(
            "color: #aaa; font-size: 11px; background: #1a1a2e; "
            "padding: 8px; border-radius: 4px; border: 1px solid #333;"
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        # 응답 표시 영역 (채팅 기록)
        self.ai_chat_display = QTextEdit()
        self.ai_chat_display.setReadOnly(True)
        self.ai_chat_display.setStyleSheet(
            "QTextEdit { background: #0d1117; color: #e6edf3; "
            "font-family: 'Malgun Gothic', 'NanumGothic', sans-serif; "
            "font-size: 12px; border: 1px solid #30363d; border-radius: 4px; "
            "padding: 10px; }"
        )
        self.ai_chat_display.setPlaceholderText(
            "AI 응답이 여기에 표시됩니다.\n\n"
            "아래 입력창에 질문을 입력하고 '전송' 버튼을 클릭하세요."
        )
        layout.addWidget(self.ai_chat_display, 1)

        # 강조 수용체 상태 레이블
        self.ai_chat_highlight_label = QLabel("")
        self.ai_chat_highlight_label.setWordWrap(True)
        self.ai_chat_highlight_label.setStyleSheet(
            "color: #f0c040; font-size: 11px; padding: 2px;"
        )
        layout.addWidget(self.ai_chat_highlight_label)

        # 입력 행
        input_row = QHBoxLayout()
        self.ai_chat_input = QLineEdit()
        self.ai_chat_input.setPlaceholderText(
            "질문 입력: 예) 경구 투여 시 결합 가능한 인슐린 작용 단백질을 알려줘"
        )
        self.ai_chat_input.setStyleSheet(
            "QLineEdit { background: #161b22; color: #e6edf3; "
            "border: 1px solid #30363d; border-radius: 4px; "
            "padding: 6px; font-size: 12px; }"
            "QLineEdit:focus { border: 2px solid #7C4DFF; }"
        )
        self.ai_chat_input.returnPressed.connect(self._on_ai_chat_send)  # Enter 키 전송
        input_row.addWidget(self.ai_chat_input, 1)

        self.btn_ai_chat_send = QPushButton("전송")
        self.btn_ai_chat_send.setStyleSheet(
            "QPushButton { background: #7C4DFF; color: white; "
            "font-weight: bold; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #651FFF; }"
            "QPushButton:disabled { background: #444; color: #888; }"
        )
        self.btn_ai_chat_send.clicked.connect(self._on_ai_chat_send)
        input_row.addWidget(self.btn_ai_chat_send)

        btn_clear = QPushButton("지우기")
        btn_clear.setStyleSheet(
            "QPushButton { background: #333; color: #aaa; "
            "padding: 6px 12px; border-radius: 4px; }"
            "QPushButton:hover { background: #444; }"
        )
        btn_clear.clicked.connect(self._on_ai_chat_clear)
        input_row.addWidget(btn_clear)

        layout.addLayout(input_row)

        # GrokChatThread 참조 (비동기 완료 추적)
        self._grok_thread: "Optional[GrokChatThread]" = None

        return widget

    def _get_openrouter_key(self) -> str:
        """OPENROUTER_API_KEY 환경변수 또는 .env에서 로드 (Rule I: 하드코딩 금지)."""
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if key:
            return key
        # .env fallback
        env_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"
        )
        try:
            with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENROUTER_API_KEY") and "=" in line:
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except OSError as e:
            logger.warning("[DockingPopup] .env 읽기 실패: %s", e)
        return ""

    def _on_ai_chat_send(self):
        """Grok AI 채팅 전송 핸들러 — 비동기 GrokChatThread 시작.
        Rule M: 입력 없음/API 키 없음 → 즉시 사용자 피드백 (silent 금지).
        """
        query = self.ai_chat_input.text().strip()
        if not query:
            # Rule M: silent failure 금지
            logger.warning("[DockingPopup._on_ai_chat_send] 빈 쿼리")
            self.ai_chat_display.append(
                "<span style='color:#ff9800;'>⚠ 질문을 입력하세요.</span>"
            )
            return

        api_key = self._get_openrouter_key()
        if not api_key:
            logger.warning("[DockingPopup._on_ai_chat_send] OPENROUTER_API_KEY 없음")
            self.ai_chat_display.append(
                "<span style='color:#f44336;'>✗ OPENROUTER_API_KEY가 설정되지 않았습니다.<br>"
                "프로젝트 루트 .env 파일에 OPENROUTER_API_KEY=sk-or-... 를 추가하세요.<br>"
                "발급: https://openrouter.ai</span>"
            )
            return

        # 이전 스레드 정리
        if self._grok_thread is not None and self._grok_thread.isRunning():
            logger.warning("[DockingPopup._on_ai_chat_send] 이전 Grok 스레드 실행 중 — 중복 전송 차단")
            self.ai_chat_display.append(
                "<span style='color:#ff9800;'>⚠ AI가 응답 중입니다. 잠시 기다려 주세요.</span>"
            )
            return

        # UI 상태 변경
        self.btn_ai_chat_send.setEnabled(False)
        self.btn_ai_chat_send.setText("응답 중...")
        self.ai_chat_highlight_label.setText("")

        # 학생 질문 표시
        self.ai_chat_display.append(
            f"<br><b style='color:#58a6ff;'>학생:</b> "
            f"<span style='color:#e6edf3;'>{query}</span>"
        )
        self.ai_chat_input.clear()

        # Grok 스레드 시작
        self._grok_thread = GrokChatThread(query, api_key, parent=self)
        self._grok_thread.response_ready.connect(self._on_grok_response)
        self._grok_thread.error_occurred.connect(self._on_grok_error)
        self._grok_thread.start()

    def _on_grok_response(self, content: str, pdb_ids: list):
        """Grok 응답 수신 — 채팅창 표시 + 드롭다운 강조."""
        # Rule N: isinstance 타입 가드
        if not isinstance(content, str):
            content = str(content)
        if not isinstance(pdb_ids, list):
            pdb_ids = []

        # 응답 텍스트 표시 (줄바꿈 → <br>)
        formatted = content.replace("\n", "<br>")
        self.ai_chat_display.append(
            f"<br><b style='color:#7C4DFF;'>Grok AI:</b><br>"
            f"<span style='color:#e6edf3;'>{formatted}</span>"
        )

        # 드롭다운 강조
        if pdb_ids:
            highlighted = self._highlight_receptor_in_combo(pdb_ids)
            if highlighted:
                labels = [f"{pid}" for pid in highlighted]
                self.ai_chat_highlight_label.setText(
                    f"드롭다운 강조: {', '.join(labels)} "
                    "(노란 테두리 = AI 추천 수용체)"
                )
                self.ai_chat_display.append(
                    f"<br><span style='color:#f0c040;'>추천 수용체 강조 완료: "
                    f"{', '.join(labels)}</span>"
                )
            else:
                self.ai_chat_display.append(
                    f"<br><span style='color:#aaa;'>추천 PDB ID {pdb_ids}는 "
                    f"현재 프리셋 DB에 없습니다. "
                    f"PDB ID 입력창에 직접 입력할 수 있습니다.</span>"
                )
                # 첫 번째 추천 PDB ID를 입력창에 자동 삽입
                if pdb_ids:
                    self.pdb_id_input.setText(pdb_ids[0])
        else:
            self.ai_chat_highlight_label.setText("")

        self._ai_chat_reset_btn()

    def _on_grok_error(self, error_msg: str):
        """Grok 오류 처리 — Rule M: silent 금지."""
        # Rule M: 오류 시 사용자 피드백 필수
        logger.warning("[DockingPopup._on_grok_error] %s", error_msg)
        self.ai_chat_display.append(
            f"<br><span style='color:#f44336;'>✗ 오류: {error_msg}</span>"
        )
        self._ai_chat_reset_btn()

    def _on_ai_chat_clear(self):
        """채팅 기록 초기화."""
        self.ai_chat_display.clear()
        self.ai_chat_highlight_label.setText("")
        # 드롭다운 강조 해제
        self._clear_receptor_highlights()

    def _ai_chat_reset_btn(self):
        """전송 버튼 복원."""
        self.btn_ai_chat_send.setEnabled(True)
        self.btn_ai_chat_send.setText("전송")

    def _highlight_receptor_in_combo(self, pdb_ids: list) -> list:
        """preset_combo에서 pdb_ids와 일치하는 항목에 노란 테두리 강조.
        Returns: 실제로 강조된 PDB ID 목록.
        Rule N: 타입 가드.
        """
        if not isinstance(pdb_ids, list):
            logger.warning("[_highlight_receptor_in_combo] pdb_ids 타입 오류: %s", type(pdb_ids))
            return []

        pdb_set = {str(p).strip().upper() for p in pdb_ids if p}
        highlighted = []

        for i in range(self.preset_combo.count()):
            item_data = self.preset_combo.itemData(i)
            if not isinstance(item_data, str):
                continue
            if item_data.upper() in pdb_set:
                highlighted.append(item_data.upper())
                # QComboBox 개별 아이템 배경 강조 (setItemData with ForegroundRole)
                from PyQt6.QtGui import QBrush
                self.preset_combo.setItemData(
                    i,
                    QBrush(QColor("#f0c040")),  # [MAGIC: #f0c040] 노란색 강조 (격분 #29 요구)
                    Qt.ItemDataRole.ForegroundRole,
                )
                self.preset_combo.setItemData(
                    i,
                    QBrush(QColor("#2a2000")),  # [MAGIC: #2a2000] 어두운 노란 배경
                    Qt.ItemDataRole.BackgroundRole,
                )
                logger.info("[DockingPopup] preset_combo 강조: idx=%d pdb=%s", i, item_data)

        if highlighted:
            # 첫 번째 강조 항목으로 자동 선택
            for i in range(self.preset_combo.count()):
                item_data = self.preset_combo.itemData(i)
                if isinstance(item_data, str) and item_data.upper() == highlighted[0]:
                    self.preset_combo.setCurrentIndex(i)
                    break
            # 드롭다운 테두리 강조 (CSS)
            self.preset_combo.setStyleSheet(
                "QComboBox { border: 3px solid #f0c040; border-radius: 4px; "
                "padding: 2px; color: #f0c040; font-weight: bold; }"
                "QComboBox:hover { border-color: #ffd740; }"
                "QComboBox::drop-down { border: none; }"
            )
        return highlighted

    def _clear_receptor_highlights(self):
        """preset_combo 강조 초기화."""
        self.preset_combo.setStyleSheet("")  # 기본 스타일 복원
        for i in range(self.preset_combo.count()):
            self.preset_combo.setItemData(
                i, None, Qt.ItemDataRole.ForegroundRole
            )
            self.preset_combo.setItemData(
                i, None, Qt.ItemDataRole.BackgroundRole
            )

    # ========== dep status ==========

    def _update_dep_status(self):
        deps = []
        deps.append(f"Vina: {'OK (Python)' if VINA_PYTHON_AVAILABLE else 'Not found'}")
        deps.append(f"RDKit: {'OK' if RDKIT_AVAILABLE else 'Missing'}")
        deps.append(f"Meeko: {'OK' if MEEKO_AVAILABLE else 'Fallback'}")
        deps.append(f"OpenBabel: {'OK' if OBABEL_AVAILABLE else 'Fallback'}")
        deps.append(f"RCSB: {'OK' if REQUESTS_AVAILABLE else 'No requests'}")
        deps.append(f"3D Viewer: {'OK' if DOCKING_3D_AVAILABLE else 'Missing PyOpenGL'}")
        deps.append(f"Antimicrobial: {'OK' if INNATE_DEFENSE_AVAILABLE else 'Not loaded'}")
        deps.append(f"Membrane: {'OK' if MEMBRANE_PERM_AVAILABLE else 'Not loaded'}")
        deps.append(f"Mucin: {'OK' if MUCIN_TAB_AVAILABLE else 'Not loaded'}")
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if _GENAI_AVAILABLE and api_key:
            deps.append("Gemini AI: OK")
        elif _GENAI_AVAILABLE:
            deps.append("Gemini AI: No API Key")
        else:
            deps.append("Gemini AI: Not installed")
        # [M851] Grok AI (OpenRouter) 상태
        grok_key = self._get_openrouter_key()
        deps.append(f"Grok AI: {'OK' if grok_key else 'No OPENROUTER_API_KEY'}")

        self.dep_label.setText("Dependencies: " + " | ".join(deps))


def launch_docking_viewer(canvas=None, parent=None):
    """Convenience function to launch docking popup"""
    popup = DockingPopup(canvas, parent)
    popup.exec()
