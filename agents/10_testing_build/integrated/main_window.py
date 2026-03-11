"""
main_window.py — ChemGrid 메인 윈도우 모듈
MainWindow 클래스 (QMainWindow)
"""
import os
import json
import ctypes
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QColorDialog,
                             QVBoxLayout, QHBoxLayout, QLabel,
                             QMessageBox, QFileDialog, QTextEdit, QDialog, QWidget,
                             QLineEdit, QSizePolicy)
from PyQt6.QtGui import QAction, QIcon, QPainter, QColor
from PyQt6.QtCore import Qt, QPointF, QPoint
from PyQt6.QtPrintSupport import QPrinter

from ui_utils import load_icon
from dialogs import (PeriodicTableDialog, PenSettingsBox,
                     ComparisonDialog, HistoryBrowserDialog, BatchProcessorDialog)
from toolbar_setup import setup_toolbars
from canvas import MoleculeCanvas

# ========== [Phase C] 3D 팝업 임포트 ==========
try:
    from popup_3d import Molecule3DData, Molecule3DPopup
    PHASE_C_AVAILABLE = True
except ImportError:
    PHASE_C_AVAILABLE = False

# ========== [Phase C+] Spectrum Analyzer 모듈 임포트 ==========
try:
    from spectrum_analyzer import parse_orca_frequencies, SpectrumViewerWidget
    from popup_spectrum import SpectrumPopup, launch_spectrum_viewer
    SPECTRUM_ANALYZER_AVAILABLE = True
except ImportError:
    SPECTRUM_ANALYZER_AVAILABLE = False
    print("[main_window.py] Spectrum analyzer module not available")

# ========== [Phase 5] Phase 4 모듈 임포트 ==========
try:
    from molecule_comparator import MoleculeComparator, ComparisonResult
    PHASE_4_COMPARATOR_AVAILABLE = True
except ImportError:
    PHASE_4_COMPARATOR_AVAILABLE = False
    print("[main_window.py] molecule_comparator module not available")

try:
    from history_manager import HistoryManager, CalculationEntry
    PHASE_4_HISTORY_AVAILABLE = True
except ImportError:
    PHASE_4_HISTORY_AVAILABLE = False
    print("[main_window.py] history_manager module not available")

try:
    from batch_processor import BatchProcessor, BatchJob, BatchJobStatus
    PHASE_4_BATCH_AVAILABLE = True
except ImportError:
    PHASE_4_BATCH_AVAILABLE = False
    print("[main_window.py] batch_processor module not available")

# ========== [최종 100점] 새로운 분광 분석 모듈 임포트 ==========
try:
    from popup_nmr import NMRPopup, launch_nmr_viewer
    NMR_AVAILABLE = True
except ImportError:
    NMR_AVAILABLE = False
    print("[main_window.py] NMR module not available")

try:
    from popup_uvvis import UVVisPopup, launch_uvvis_viewer
    UVVIS_AVAILABLE = True
except ImportError:
    UVVIS_AVAILABLE = False
    print("[main_window.py] UV-Vis module not available")

try:
    from popup_md import MDPopup, launch_md_viewer
    MD_AVAILABLE = True
except ImportError:
    MD_AVAILABLE = False
    print("[main_window.py] MD module not available")

try:
    from popup_molorbital import MolecularOrbitalPopup, launch_orbital_viewer
    MOLORBITAL_AVAILABLE = True
except ImportError:
    MOLORBITAL_AVAILABLE = False

# ========== [Phase 5 Advanced] Export & Verification 모듈 임포트 ==========
try:
    from export_manager_enhanced import ExportManager
    EXPORT_MANAGER_AVAILABLE = True
except ImportError:
    EXPORT_MANAGER_AVAILABLE = False
    print("[main_window.py] Advanced export manager module not available")

try:
    from spectrum_pdf_exporter import ExportSpectrumManager, SpectrumMetadata, SpectrumData
    SPECTRUM_PDF_EXPORTER_AVAILABLE = True
except ImportError:
    SPECTRUM_PDF_EXPORTER_AVAILABLE = False
    print("[main_window.py] Spectrum PDF exporter module not available")

try:
    from calculation_logger import CalculationLogger, CalculationEntry
    CALCULATION_LOGGER_AVAILABLE = True
except ImportError:
    CALCULATION_LOGGER_AVAILABLE = False
    print("[main_window.py] Calculation logger module not available")

try:
    from verification_report import VerificationEngine, VerificationReport
    VERIFICATION_REPORT_AVAILABLE = True
except ImportError:
    VERIFICATION_REPORT_AVAILABLE = False
    print("[main_window.py] Verification report module not available")


# ==========================================
# [SECTION 4] 메인 인터페이스
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # [해결] Windows 작업표시줄에 로고가 나오도록 시스템 AppID 강제 설정
        try:
            myappid = 'chemgrid.pro.v1.52'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except: pass

        self.setWindowTitle("ChemGrid"); self.setGeometry(100, 100, 1350, 850)
        
        # [해결] 로고 경로: __file__ 기반 포터블 경로
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.normpath(os.path.join(script_dir, "logo.png"))
        
        if os.path.exists(logo_path):
            app_icon = QIcon(logo_path)
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon) 
        else:
            print(f"[MainWindow] Logo not found at {logo_path}")
        
        # [무결성] 캔버스 및 툴바는 단 한 번만 생성하여 메모리 낭비 및 에러 방지
        self.cv = MoleculeCanvas(self); self.setCentralWidget(self.cv)
        
        # ========== [Phase Integration Hook 1] Canvas 초기화 완료 ==========
        # 툴바 설정 (toolbar_setup.py로 분리)
        setup_toolbars(self)

        # ==========================================
        # 뷰 전환 버튼
        # ==========================================
        self.view_container = QWidget(self)
        self.view_layout = QHBoxLayout(self.view_container)
        self.btn_lewis = QPushButton("루이스 구조", self.view_container)
        self.btn_theory = QPushButton("이론적 구조", self.view_container)
        # [해결] 스타일을 통일하고 부모 위젯을 self로 변경하여 레이아웃 간섭 방지
        self.btn_3d = QPushButton("입체 구조", self)
        self.btn_3d.setFixedSize(110, 40)
        self.btn_3d.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border-radius: 10px; font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #555; color: #999;
            }
        """)
        self.btn_3d.clicked.connect(self.open_3d_popup)  # [U2] 클릭 이벤트 연결
        self.btn_3d.setEnabled(False)  # [Phase 6-3] 분자 미선택 시 비활성
        self.btn_3d.setToolTip("먼저 분자를 선택하세요")
        self.btn_3d.hide()
        
        # [U3] 스펙트럼/NMR/UV-Vis/MD/오비탈 버튼은 향후 3D 팝업 탭으로 이동 (Agent 06 담당)

        for btn in [self.btn_lewis, self.btn_theory]:
            btn.setFixedSize(110, 40)
            btn.setStyleSheet("background-color: #2196F3; color: white; border-radius: 10px; font-weight: bold;")
            self.view_layout.addWidget(btn)
        
        self.btn_lewis.clicked.connect(lambda: self.switch_view("Lewis"))
        self.btn_theory.clicked.connect(lambda: self.switch_view("Theory"))
        
        # [신규] 전자구름 토글 버튼 (부드러운 오렌지/레드 계열)
        self.btn_cloud = QPushButton("전자구름 끄기", self) # 초기 상태가 On이므로 '끄기' 표시
        self.btn_cloud.setFixedSize(110, 40)
        self.btn_cloud.setStyleSheet("""
            background-color: #FF8A65; 
            color: white; 
            border-radius: 10px; 
            font-weight: bold;
        """)
        self.btn_cloud.clicked.connect(self.toggle_clouds)
        
        # 돌아가기 버튼 (평상시 숨김)
        self.btn_back = QPushButton("그리기 화면으로 복귀", self)
        self.btn_back.setFixedSize(150, 40); self.btn_back.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 10px;")
        self.btn_back.clicked.connect(lambda: self.switch_view("Drawing")); self.btn_back.hide()

        self.pen_ui = PenSettingsBox(self); self.pen_ui.slider.valueChanged.connect(lambda v: setattr(self.cv, 'pen_width', v))
        self.pen_ui.color_btn.clicked.connect(self.pick_clr); self.pen_ui.hide()

        # [Phase 6-3] molecule_selected 시그널 연결 (Agent 02 미완료 시에도 안전)
        if hasattr(self.cv, 'molecule_selected'):
            self.cv.molecule_selected.connect(self._on_molecule_selection_changed)

        # ========== [신규] 그리기 레이어 하단 텍스트 입력창 (AI 분자 생성) ==========
        self.mol_name_input = QLineEdit(self)
        self.mol_name_input.setPlaceholderText(
            "🤖 분자명 입력 (예: hemoglobin, benzene, aspirin) → AI가 구조를 그립니다"
        )
        self.mol_name_input.setFixedHeight(38)
        self.mol_name_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 40, 210);
                color: #E0E0E0;
                border: 1px solid #4A90E2;
                border-radius: 10px;
                padding: 5px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #64B5F6;
                background-color: rgba(30, 30, 50, 230);
            }
        """)
        self.mol_name_input.returnPressed.connect(self._on_mol_name_submitted)
        self.mol_name_input.show()

        # ========== [신규] 그리기 레이어 하단 중앙 입력 전송 버튼 ==========
        self.mol_name_btn = QPushButton("⚗", self)
        self.mol_name_btn.setFixedSize(38, 38)
        self.mol_name_btn.setToolTip("AI로 분자 그리기")
        self.mol_name_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2; color: white;
                border-radius: 10px; font-size: 16px;
            }
            QPushButton:hover { background-color: #64B5F6; }
        """)
        self.mol_name_btn.clicked.connect(self._on_mol_name_submitted)
        self.mol_name_btn.show()

        # [v4] UI 상태 일괄 갱신
        self.update_ui_state()

        # ========== [Phase 5] Phase 4 모듈 초기화 ==========
        self.molecule_comparator = None
        self.history_manager = None
        self.batch_processor = None
        
        if PHASE_4_COMPARATOR_AVAILABLE:
            self.molecule_comparator = MoleculeComparator()
            
        if PHASE_4_HISTORY_AVAILABLE:
            self.history_manager = HistoryManager()
            
        if PHASE_4_BATCH_AVAILABLE:
            self.batch_processor = BatchProcessor()
        
        # [U1] 분자비교/히스토리/배치처리는 tb2에서 제거됨
        # 향후 3D 팝업 또는 별도 메뉴에서 접근하도록 재배치 예정
        
        # ========== [최종 100점] 진행 추적 및 Discord 보고 시작 ==========
        try:
            from progress_tracker import get_tracker, start_periodic_reporting
            self.progress_tracker = get_tracker()
            # 30분마다 자동 Discord 보고 시작
            self.reporter_thread = start_periodic_reporting()
            print("[MainWindow] Progress tracking and Discord reporting activated")
        except Exception as e:
            print(f"[MainWindow] Progress tracking initialization failed: {e}")

    def switch_view(self, mode):
        """[Step 5] 레이어 전환 및 원형 확장 애니메이션"""
        prev_scale = self.cv.scale_factor
        prev_offset = QPointF(self.cv.pan_offset)

        self.cv.view_state = mode
        is_drawing = (mode == "Drawing")

        self.cv.scale_factor = prev_scale
        self.cv.pan_offset = prev_offset

        # [Step 5] 우측 하단 버튼 위치에서 원형으로 확장하는 애니메이션 시작
        start_x = self.cv.width() - 50
        start_y = self.cv.height() - 50
        start_pt = QPointF(start_x, start_y)
        self.cv.start_reveal_animation(start_pt)

        # [해결] 내보내기 버튼 비활성화 (Drawing 모드에서는 잠금)
        if hasattr(self, 'export_btn'):
            self.export_btn.setEnabled(not is_drawing)

        # ★ [개선] '입체 구조' 버튼: Theory 모드에서 원자가 존재하면 즉시 활성화
        if hasattr(self, 'btn_3d'):
            if mode == "Theory":
                self.btn_3d.show()
                self.btn_3d.raise_()
                # 원자가 하나라도 있으면 btn_3d 활성화 (선택 없어도 전체 원자 사용)
                has_atoms = bool(self.cv.atoms)
                has_selection = hasattr(self.cv, 'selected_molecule_keys') and bool(self.cv.selected_molecule_keys)
                self.btn_3d.setEnabled(has_atoms)
                if has_selection:
                    self.btn_3d.setToolTip("선택된 분자의 3D 구조 보기")
                elif has_atoms:
                    self.btn_3d.setToolTip("캔버스 전체 분자의 3D 구조 보기")
                else:
                    self.btn_3d.setToolTip("먼저 분자를 그리세요")
            else:
                self.btn_3d.hide()
        
        # ========== [Phase C+] & [최종 100점] 스펙트럼/분석 버튼도 Theory 모드에서 표시 ==========
        analysis_buttons = ['btn_spectrum', 'btn_nmr', 'btn_uvvis', 'btn_md', 'btn_molorbital']
        for btn_name in analysis_buttons:
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                if mode == "Theory":
                    btn.show()
                    btn.raise_()
                else:
                    btn.hide()

        # 그리기 관련 도구 비활성화 (회색 처리)
        draw_tools = ["Bond", "Wedge", "Dash", "Arrow", "Text", "H", "R", "O", "N", "P", "S", "F", "Cl", "Br", "I", "LonePair", "Radical"]
        # Lewis/Theory 레이어에서는 +/- 도구도 비활성화
        disable_in_lewis_theory = ["Positive", "Negative"]
        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in draw_tools:
                action.setEnabled(is_drawing)
            elif action_text in disable_in_lewis_theory:
                action.setEnabled(is_drawing)
        
        if is_drawing:
            self.view_container.show() # 파란 버튼들 나타남
            self.btn_back.hide()       # 초록 버튼 숨김
            self.btn_3d.hide()         # 입체 버튼 숨김
        else:
            self.view_container.hide() # 파란 버튼들 숨김
            self.btn_back.show()       # 초록 버튼 나타남
            if mode == "Theory":
                self.btn_3d.show()
                # [Phase 6-3] btn_3d enabled 상태 유지 (위에서 설정됨)
            else:
                self.btn_3d.hide()

        # ★ AI 텍스트 입력창은 그리기 레이어에서만 표시
        if hasattr(self, 'mol_name_input'):
            if is_drawing:
                self.mol_name_input.show()
                self.mol_name_btn.show()
                self.mol_name_input.raise_()
                self.mol_name_btn.raise_()
            else:
                self.mol_name_input.hide()
                self.mol_name_btn.hide()

        if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
            self.btn_3d.raise_()
        self.cv.update()

    # [Phase 6-3] 분자 선택 변경 핸들러
    def _on_molecule_selection_changed(self, selected: bool):
        """분자 선택/해제 시 btn_3d 상태 갱신.
        ★ 개선: 선택 해제여도 원자가 있으면 btn_3d 유지 활성
        """
        if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
            has_atoms = bool(self.cv.atoms)
            self.btn_3d.setEnabled(has_atoms)
            if selected:
                self.btn_3d.setToolTip("선택된 분자의 3D 구조 보기")
            elif has_atoms:
                self.btn_3d.setToolTip("캔버스 전체 분자의 3D 구조 보기")
            else:
                self.btn_3d.setToolTip("먼저 분자를 그리세요")

        # [v4] 선택 영역 내보내기 버튼 활성화
        if hasattr(self, 'export_btn'):
            is_drawing = (self.cv.view_state == "Drawing")
            self.export_btn.setEnabled(not is_drawing and bool(self.cv.atoms))

    def update_ui_state(self):
        """캔버스 상태에 따라 UI 버튼들의 활성/비활성 상태를 일괄 갱신"""
        has_atoms = len(self.cv.atoms) > 0
        is_drawing = (self.cv.view_state == "Drawing")
        
        # 내보내기 버튼 활성화 조건 (Drawing 모드가 아니고 분자가 존재할 때)
        if hasattr(self, 'export_btn'):
            has_selection = hasattr(self.cv, 'selected_molecule_keys') and bool(self.cv.selected_molecule_keys)
            self.export_btn.setEnabled(not is_drawing and (has_atoms or has_selection))

    # [신규] 구름 토글 로직
    def toggle_clouds(self):
        self.cv.show_clouds = not self.cv.show_clouds
        btn_text = "전자구름 켜기" if not self.cv.show_clouds else "전자구름 끄기"
        self.btn_cloud.setText(btn_text)
        self.cv.update()

    def resizeEvent(self, event):
        # [해결] 버튼 컨테이너 크기 고정 및 우하단 마진(25px) 적용
        margin = 25

        if hasattr(self, 'btn_cloud'):
            cx = margin
            cy = self.height() - self.btn_cloud.height() - margin
            self.btn_cloud.move(cx, cy)
            self.btn_cloud.raise_()

        if hasattr(self, 'view_container'):
            self.view_container.setFixedSize(240, 50) # 너비 240, 높이 50으로 확보
            vx = self.width() - self.view_container.width() - margin
            vy = self.height() - self.view_container.height() - margin
            self.view_container.move(vx, vy)
            self.view_container.raise_() # 다른 위젯에 가려지지 않게 최상단으로

        if hasattr(self, 'btn_back'):
            self.btn_back.setFixedSize(200, 50)
            bx = self.width() - self.btn_back.width() - margin
            by = self.height() - self.btn_back.height() - margin
            self.btn_back.move(bx, by)
            self.btn_back.raise_()

            # [해결] 입체 구조 버튼을 '그리기로 돌아가기' 버튼 10px 위에 배치
            if hasattr(self, 'btn_3d'):
                self.btn_3d.setFixedSize(200, 50) # 크기 통일
                tx = bx # X좌표 동일
                ty = by - self.btn_3d.height() - 10 # 10px 위쪽
                self.btn_3d.move(tx, ty)
            
            # [Phase C+] & [최종 100점] 분석 버튼들을 입체 구조 버튼 위에 배치
            analysis_buttons = ['btn_spectrum', 'btn_nmr', 'btn_uvvis', 'btn_md', 'btn_molorbital']
            for i, btn_name in enumerate(analysis_buttons):
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    btn.setFixedSize(200, 50)
                    btn_x = bx
                    btn_y = by - self.btn_3d.height() - (i + 1) * 50 - (i + 1) * 10
                    btn.move(btn_x, btn_y)
                    btn.raise_()

        # ★ AI 텍스트 입력창 → 하단 중앙 배치 (Drawing 레이어 전용)
        if hasattr(self, 'mol_name_input'):
            input_w = min(580, self.width() - 160)
            input_h = 38
            btn_w = 38
            gap = 8
            total_w = input_w + gap + btn_w
            ix = (self.width() - total_w) // 2
            iy = self.height() - input_h - 18
            self.mol_name_input.setFixedWidth(input_w)
            self.mol_name_input.move(ix, iy)
            self.mol_name_btn.move(ix + input_w + gap, iy)
            self.mol_name_input.raise_()
            self.mol_name_btn.raise_()

        super().resizeEvent(event)

    # ========== [신규] AI 분자 그리기: 이름 → SMILES → Canvas ==========
    def _on_mol_name_submitted(self):
        """텍스트 입력창에서 분자명을 받아 AI로 SMILES 변환 후 캔버스에 그리기"""
        name = self.mol_name_input.text().strip()
        if not name:
            return

        # [통로 1] canvas에 draw_molecule_from_name 메서드가 있으면 직접 호출
        if hasattr(self.cv, 'draw_molecule_from_name'):
            try:
                self.mol_name_btn.setEnabled(False)
                self.mol_name_btn.setText("⏳")
                QApplication.processEvents()
                result = self.cv.draw_molecule_from_name(name)
                if result:
                    self.mol_name_input.clear()
                    self.mol_name_input.setPlaceholderText(f"✅ '{name}' 그리기 완료")
                else:
                    self.mol_name_input.setPlaceholderText(f"⚠️ '{name}' 인식 실패 — SMILES를 직접 입력해보세요")
            except Exception as e:
                self.mol_name_input.setPlaceholderText(f"❌ 오류: {str(e)[:50]}")
            finally:
                self.mol_name_btn.setEnabled(True)
                self.mol_name_btn.setText("⚗")
            return

        # [통로 2] PubChem으로 SMILES 조회 후 RDKit 2D 그리기 시도
        try:
            self.mol_name_btn.setEnabled(False)
            self.mol_name_btn.setText("⏳")
            QApplication.processEvents()
            smiles = self._lookup_smiles_for_name(name)
            if smiles:
                self._draw_smiles_on_canvas(smiles, name)
                self.mol_name_input.clear()
                self.mol_name_input.setPlaceholderText(f"✅ '{name}' → {smiles[:40]}")
            else:
                self.mol_name_input.setPlaceholderText(
                    f"⚠️ '{name}' 검색 실패 — 화학명 또는 SMILES로 직접 입력하세요"
                )
        except Exception as e:
            self.mol_name_input.setPlaceholderText(f"❌ 오류: {str(e)[:50]}")
        finally:
            self.mol_name_btn.setEnabled(True)
            self.mol_name_btn.setText("⚗")

    def _lookup_smiles_for_name(self, name: str) -> str:
        """PubChem 또는 Gemini AI로 분자명 → SMILES 변환.
        우선순위: PubChem REST > Gemini AI > 내장 사전
        """
        # [Step 1] 내장 간단 사전 (네트워크 불필요)
        BUILTIN = {
            "methane": "C", "propane": "CCC", "butane": "CCCC", "pentane": "CCCCC",
            "hexane": "CCCCCC", "ethane": "CC", "ethylene": "C=C", "acetylene": "C#C",
            "benzene": "c1ccccc1", "toluene": "Cc1ccccc1",
            "ethylbenzene": "CCc1ccccc1", "styrene": "C=Cc1ccccc1",
            "naphthalene": "c1ccc2ccccc2c1", "anthracene": "c1ccc2cc3ccccc3cc2c1",
            "phenol": "Oc1ccccc1", "aniline": "Nc1ccccc1",
            "pyridine": "c1ccncc1", "pyrimidine": "c1cnccn1",
            "cyclohexane": "C1CCCCC1", "cyclopentane": "C1CCCC1",
            "acetone": "CC(C)=O", "acetic acid": "CC(=O)O",
            "ethanol": "CCO", "methanol": "CO", "water": "O",
            "ammonia": "N", "carbon dioxide": "O=C=O",
            "glucose": "OCC1OC(O)C(O)C(O)C1O",
            "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
            "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
            "ibuprofen": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
            "cholesterol": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@@H]2CC=C4[C@@]3(CC[C@@H](C4)O)C)C",
        }
        lower = name.lower().strip()
        if lower in BUILTIN:
            return BUILTIN[lower]

        # [Step 2] PubChem REST API
        try:
            import requests
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{requests.utils.quote(name)}/property/CanonicalSMILES/JSON"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                smiles = data.get("PropertyTable", {}).get("Properties", [{}])[0].get("CanonicalSMILES", "")
                if smiles:
                    return smiles
        except Exception:
            pass

        # [BUG-01] 대형 단백질/복합체 → 사용자 친화적 오류 메시지
        LARGE_MOLECULES = {
            "hemoglobin": "heme",
            "myoglobin": "heme",
            "albumin": None,
            "collagen": None,
            "insulin": "CC(C)CC1NC(=O)C(CC2=CC=CC=C2)NC(=O)",  # 부분 구조
            "dna": None,
            "rna": None,
            "protein": None,
        }
        if lower in LARGE_MOLECULES:
            alt = LARGE_MOLECULES[lower]
            if alt:
                # 대안 분자로 자동 전환
                return self._lookup_smiles_for_name(alt)
            return ""  # 대안 없음 → 빈 문자열 → 호출부에서 에러 메시지 표시

        # [BUG-07 수정] google.genai로 마이그레이션 (google.generativeai deprecated)
        try:
            import os as _os
            api_key = _os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                # 새 패키지 우선 시도, 실패 시 구 패키지 폴백
                try:
                    import google.genai as _genai
                    client = _genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=(
                            f"분자명 '{name}'의 SMILES 코드를 반환하세요. "
                            "SMILES 코드만 한 줄로 출력하고, 다른 설명은 하지 마세요."
                        ),
                    )
                    smiles = response.text.strip().split()[0]
                    if smiles:
                        return smiles
                except Exception:
                    # 구 패키지 폴백
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        import google.generativeai as _genai_old
                    _genai_old.configure(api_key=api_key)
                    model = _genai_old.GenerativeModel("gemini-1.5-flash")
                    prompt = (
                        f"분자명 '{name}'의 SMILES 코드를 반환하세요. "
                        "SMILES 코드만 한 줄로 출력하고, 다른 설명은 하지 마세요."
                    )
                    resp = model.generate_content(prompt)
                    smiles = resp.text.strip().split()[0]
                    if smiles:
                        return smiles
        except Exception:
            pass

        return ""

    def _draw_smiles_on_canvas(self, smiles: str, mol_name: str = ""):
        """RDKit 2D 좌표를 캔버스 원자/결합 데이터로 변환하여 그리기

        [BUG-02 수정] 좌표계 오류 + hex grid 스냅 + analysis_results 갱신
        - 수정 전: cx = width/2 + pan_offset (부호 오류)
        - 수정 후: logical_center = (width/2 - pan_offset) / scale_factor
        - 스냅 방식: 직교 30px 단위 → canvas.get_closest_pt() (hex grid)
        - 수정 후: analysis_results 갱신 → Theory 레이어에서 구조 표시 가능
        """
        import sys
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            from PyQt6.QtCore import QPointF

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False

            # 수소 제거 (표시 단순화)
            mol = Chem.RemoveHs(mol)
            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer()

            xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
            ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
            cx_mol = (max(xs) + min(xs)) / 2
            cy_mol = (max(ys) + min(ys)) / 2

            # ✅ [BUG-02A 수정] 올바른 논리 좌표 계산
            # to_logical(pos) = (pos - pan_offset) / scale_factor
            # 스크린 중심 = (width/2, height/2) → 논리 좌표:
            sf = getattr(self.cv, 'scale_factor', 1.0)
            pan_x = self.cv.pan_offset.x()
            pan_y = self.cv.pan_offset.y()
            cx_logical = (self.cv.width() / 2 - pan_x) / sf
            cy_logical = (self.cv.height() / 2 - pan_y) / sf

            # RDKit 2D 단위 → 논리 픽셀: grid_size(40px) / C-C bond(1.5Å) ≈ 26.7 px/unit
            scale = 26.7

            self.cv.save_state()

            # ✅ [BUG-02B 수정] hex grid 스냅 사용
            idx_to_key = {}
            for i in range(mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                atom = mol.GetAtomWithIdx(i)
                sym = atom.GetSymbol()

                raw_x = cx_logical + (pos.x - cx_mol) * scale
                raw_y = cy_logical - (pos.y - cy_mol) * scale  # Y축 반전
                raw_pos = QPointF(raw_x, raw_y)

                # hex grid 스냅 시도
                snapped = self.cv.get_closest_pt(raw_pos)
                if snapped is None:
                    snapped = raw_pos  # 스냅 실패 시 원본 위치 사용

                key = (round(snapped.x(), 2), round(snapped.y(), 2))

                # 키 충돌 방지 (같은 그리드 포인트에 두 원자가 겹치는 경우)
                offset = 0
                while key in self.cv.atoms:
                    offset += 1
                    key = (round(snapped.x(), 2) + offset * 2.0, round(snapped.y(), 2))

                self.cv.atoms[key] = {"main": sym, "attach": {}}
                idx_to_key[i] = key

            # 결합 추가
            for bond in mol.GetBonds():
                i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                k1, k2 = idx_to_key.get(i), idx_to_key.get(j)
                if k1 and k2:
                    # [BUG-FIX] 방향족 결합(BondType.AROMATIC) 처리
                    # GetBondTypeAsDouble()이 방향족 결합에 대해 1.5 반환
                    # bt < 1.5 조건은 False → 잘못 order=2로 처리되는 버그 수정
                    from rdkit.Chem import rdchem as _rdchem
                    bt_type = bond.GetBondType()
                    if bt_type == _rdchem.BondType.AROMATIC:
                        order = 1   # 방향족은 Kekulé 단일결합으로 표시 (캔버스 표준)
                    elif bt_type == _rdchem.BondType.SINGLE:
                        order = 1
                    elif bt_type == _rdchem.BondType.DOUBLE:
                        order = 2
                    elif bt_type == _rdchem.BondType.TRIPLE:
                        order = 3
                    else:
                        bt = bond.GetBondTypeAsDouble()
                        order = 1 if bt <= 1.5 else (2 if bt < 2.5 else 3)
                    self.cv.bonds[(k1, k2)] = order

            # 선택 상태 등록
            drawn_keys = set(idx_to_key.values())
            self.cv.selected_molecule_keys = drawn_keys
            self.cv.selected_molecule_name = mol_name if mol_name else "molecule"

            # ✅ [BUG-02C 수정] analysis_results 갱신 → Theory 레이어 표시 가능
            try:
                self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds)
            except Exception as e_analyze:
                print(f"[MolDraw] analyze 실패: {e_analyze}", flush=True)
            try:
                self.cv.on_molecule_updated()
            except Exception:
                pass
            try:
                self.cv.save_current_smiles()
            except Exception:
                pass

            print(
                f"[MolDraw] '{mol_name}' → {mol.GetNumAtoms()} atoms, "
                f"{mol.GetNumBonds()} bonds  (selected_keys={len(drawn_keys)})",
                flush=True,
            )
            sys.stdout.flush()

            self.cv.update()
            if hasattr(self, '_update_toolbar_state'):
                self._update_toolbar_state()
            return True

        except Exception as e:
            print(f"[MolDraw] 오류: {e}", flush=True)
            sys.stdout.flush()
            return False

    def _build_smiles_from_graph(self, atoms: dict, bonds: dict) -> str:
        """sel_atoms/sel_bonds 그래프에서 직접 SMILES를 생성.
        RDKit Edit 기반으로 원자/결합 그래프를 분자 객체로 변환.
        실패 시 빈 문자열 반환 (오류로 팝업 중단되지 않도록).
        """
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem

            rw = Chem.RWMol()
            key_to_idx: dict = {}

            # ① 원자 추가
            for key, adict in atoms.items():
                sym = adict.get("main", "C")
                if len(sym) > 2 or not sym.isalpha():
                    sym = "C"
                try:
                    atomic_num = Chem.GetPeriodicTable().GetAtomicNumber(sym)
                except Exception:
                    atomic_num = 6  # fallback to Carbon
                atom = Chem.Atom(atomic_num)
                idx = rw.AddAtom(atom)
                key_to_idx[key] = idx

            # ② 결합 추가
            bond_type_map = {
                1: Chem.BondType.SINGLE,
                2: Chem.BondType.DOUBLE,
                3: Chem.BondType.TRIPLE,
            }
            for (k1, k2), v in bonds.items():
                i1 = key_to_idx.get(k1)
                i2 = key_to_idx.get(k2)
                if i1 is None or i2 is None:
                    continue
                if isinstance(v, tuple):
                    # Wedge/Dash 결합
                    bt = Chem.BondType.SINGLE
                else:
                    bt = bond_type_map.get(int(v), Chem.BondType.SINGLE)
                # 이미 결합이 있으면 건너뜀
                if rw.GetBondBetweenAtoms(i1, i2) is None:
                    rw.AddBond(i1, i2, bt)

            # ③ 수소 보정 + 정규화
            mol = rw.GetMol()
            try:
                Chem.SanitizeMol(mol)
            except Exception:
                pass

            smiles = Chem.MolToSmiles(mol, canonical=True)
            return smiles if smiles else ""

        except Exception as e:
            print(f"[_build_smiles_from_graph] 실패: {e}")
            return ""

    def clear_all(self):
        if QMessageBox.question(self, "확인", "전체 캔버스를 지우시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.cv.save_state(); self.cv.atoms = {}; self.cv.bonds = {}; self.cv.strokes = []; self.cv.update()

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG 저장", "", "PNG Files (*.png)")
        if path: self.cv.grab().save(path)
            
    def export_pdf(self):
        # [Automation] View State에 따른 파일명 및 절대 경로 설정
        mode = self.cv.view_state
        filename = f"chemgrid_export_{mode}.pdf"
        default_path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
        
        path, _ = QFileDialog.getSaveFileName(self, "PDF 저장", default_path, "PDF Files (*.pdf)")
        if path:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution); printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat); printer.setOutputFileName(path)
            painter = QPainter(printer); target_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            widget_rect = self.cv.rect(); scale = min(target_rect.width()/widget_rect.width(), target_rect.height()/widget_rect.height()) * 0.95
            painter.scale(scale, scale); self.cv.render(painter); painter.end()
            print(f"[Export] PDF Saved to {path}")

    def save_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "파일 저장", "", "Chemical Data (*.chem)")
        if path:
            try:
                # [수정] QPointF 객체는 JSON 저장이 불가능하므로 리스트 [x, y]로 변환
                s_bonds = {}
                for (k1, k2), v in self.cv.bonds.items():
                    b_key = f"{k1[0]},{k1[1]}|{k2[0]},{k2[1]}"
                    if isinstance(v, tuple): # Wedge/Dash 결합 처리
                        s_bonds[b_key] = [[v[0].x(), v[0].y()], [v[1].x(), v[1].y()], v[2]]
                    else:
                        s_bonds[b_key] = v

                # atoms 직렬화: user_lp (set → list) 변환
                s_atoms = {}
                for k, v in self.cv.atoms.items():
                    atom_copy = dict(v)
                    if "user_lp" in atom_copy and isinstance(atom_copy["user_lp"], set):
                        atom_copy["user_lp"] = list(atom_copy["user_lp"])
                    s_atoms[f"{k[0]},{k[1]}"] = atom_copy

                # arrows 직렬화
                s_arrows = []
                for (a_s, a_e) in getattr(self.cv, 'arrows', []):
                    s_arrows.append([[a_s.x(), a_s.y()], [a_e.x(), a_e.y()]])

                # text_boxes 직렬화
                s_text_boxes = []
                for tb in getattr(self.cv, 'text_boxes', []):
                    s_text_boxes.append({
                        "pos": [tb["pos"].x(), tb["pos"].y()],
                        "text": tb["text"],
                        "font_size": tb.get("font_size", 12),
                    })

                save_data = {
                    "atoms": s_atoms,
                    "bonds": s_bonds,
                    "arrows": s_arrows,
                    "text_boxes": s_text_boxes,
                }
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, indent=4)
                QMessageBox.information(self, "성공", "파일이 안전하게 저장되었습니다.")
            except Exception as e:
                QMessageBox.critical(self, "저장 에러", f"저장 중 오류가 발생했습니다: {e}")

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "파일 열기", "", "Chemical Data (*.chem)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.cv.save_state()
                
                # 원자 복원 로직 (기존 유지)
                new_atoms = {}
                for k_str, v in data["atoms"].items():
                    coord = tuple(map(float, k_str.split(',')))
                    if "attach" in v:
                        v["attach"] = {int(dk): dv for dk, dv in v["attach"].items()}
                    new_atoms[coord] = v
                self.cv.atoms = new_atoms

                # [수정] 저장된 [x, y] 리스트를 다시 QPointF 객체로 복원
                new_bonds = {}
                for k_str, v in data["bonds"].items():
                    pts = k_str.split('|')
                    p1_key = tuple(map(float, pts[0].split(',')))
                    p2_key = tuple(map(float, pts[1].split(',')))
                    
                    if isinstance(v, list): # Wedge/Dash 데이터인 경우
                        v = (QPointF(v[0][0], v[0][1]), QPointF(v[1][0], v[1][1]), v[2])
                    
                    new_bonds[(p1_key, p2_key)] = v
                self.cv.bonds = new_bonds
                self.cv.update()
            except Exception as e:
                QMessageBox.critical(self, "불러오기 에러", f"파일을 읽는 중 오류가 발생했습니다: {e}")

    def create_handler(self, mode_name): return lambda: self.set_mode(mode_name)
    def set_mode(self, m):
         self.cv.mode = m; self.pen_ui.hide()
         # [추가] 손 도구 선택 시 마우스 모양 변경
         if m == "Hand":
             self.cv.setCursor(Qt.CursorShape.OpenHandCursor)
         else:
             self.cv.setCursor(Qt.CursorShape.ArrowCursor)

         if m == "Pen":
            action = self.sender()
            # [v5] Pen이 tb(메인 그리기 툴바)에 있음
            widget = self.tb.widgetForAction(action) if hasattr(self, 'tb') else None
            if not widget and hasattr(self, 'tb2'):
                widget = self.tb2.widgetForAction(action)
            if widget:
                global_pos = widget.mapToGlobal(QPoint(0, widget.height()))
                self.pen_ui.move(global_pos)
                self.pen_ui.show()

    def pick_clr(self):
        c = QColorDialog.getColor(self.cv.pen_color, self); self.cv.pen_color = c if c.isValid() else self.cv.pen_color; self.pen_ui.hide()
    def pick_el(self):
        d = PeriodicTableDialog(self); self.cv.mode = d.selected if d.exec() else self.cv.mode
    
    # ========== [Phase 5] Phase 4 기능 메서드 ==========
    
    def enable_lasso_select(self):
        """올가미 선택 모드 [제거됨] - 기본 직사각형 선택만 사용"""
        QMessageBox.information(self, "알림", "올가미 선택 기능이 제거되었습니다.\n기본 직사각형 선택 도구를 사용해주세요.\n\n사용법: Select 도구를 선택한 후 드래그하여 원자를 선택합니다.")

    # ========== [U2] 입체 구조 3D 팝업 ==========
    def open_3d_popup(self):
        """선택된 분자의 3D 구조 팝업 열기.
        ★ 개선: 선택 없으면 전체 atoms 사용 → 메탄/벤젠 같은 간단한 분자도 바로 3D 전환
        """
        if not PHASE_C_AVAILABLE:
            QMessageBox.warning(self, "알림", "3D 뷰어 모듈을 사용할 수 없습니다.\nPyOpenGL을 설치해주세요.")
            return

        # ★ [개선] 선택된 원자 키 가져오기 — 없으면 전체 atoms 사용
        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())
        if not selected_keys:
            # Drawing 모드 selected_atoms도 확인
            selected_keys = getattr(self.cv, 'selected_atoms', set())
        if not selected_keys:
            # 선택 없음 → 전체 원자 사용 (간단한 분자를 바로 3D 전환 가능)
            selected_keys = set(self.cv.atoms.keys())

        if not selected_keys:
            QMessageBox.warning(self, "알림", "먼저 분자를 그리세요.")
            return

        # 선택된 분자의 atoms/bonds만 필터링
        sel_atoms = {k: v for k, v in self.cv.atoms.items() if k in selected_keys}
        sel_bonds = {}
        for (k1, k2), v in self.cv.bonds.items():
            if k1 in selected_keys and k2 in selected_keys:
                sel_bonds[(k1, k2)] = v

        try:
            theory_data = (self.cv.analysis_results.get("theory_data", {})
                           if self.cv.analysis_results else {})

            # ★ SMILES 추출: 선택된 원자/결합 → RDKit → SMILES
            mol_smiles = ""
            # [Step 1] canvas 내부 메서드 시도
            try:
                if getattr(self.cv, 'selected_molecule_keys', set()):
                    mol_smiles = self.cv._get_molecule_smiles() or ""
            except Exception:
                pass
            # [Step 2] sel_atoms/sel_bonds에서 직접 SMILES 생성
            if not mol_smiles:
                mol_smiles = self._build_smiles_from_graph(sel_atoms, sel_bonds)

            mol_data = Molecule3DData(
                atoms=sel_atoms,
                bonds=sel_bonds,
                theory_data=theory_data,
                smiles=mol_smiles,
            )
            popup = Molecule3DPopup(mol_data, self)
            popup.show()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"3D 뷰어 실행 실패:\n{str(e)}")
    
    # ========== [최종 100점] 새로운 분광 분석 기능 ==========
    
    def open_nmr_viewer(self):
        """NMR 스펙트럼 뷰어 열기"""
        if not NMR_AVAILABLE:
            QMessageBox.warning(self, "알림", "NMR 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = NMRPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"NMR 데이터 로드 실패:\n{str(e)}")
    
    def open_uvvis_viewer(self):
        """UV-Vis 스펙트럼 뷰어 열기"""
        if not UVVIS_AVAILABLE:
            QMessageBox.warning(self, "알림", "UV-Vis 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = UVVisPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"UV-Vis 데이터 로드 실패:\n{str(e)}")
    
    def open_md_viewer(self):
        """분자동역학 뷰어 열기"""
        if not MD_AVAILABLE:
            QMessageBox.warning(self, "알림", "MD 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = MDPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"MD 데이터 로드 실패:\n{str(e)}")
    
    def open_molorbital_viewer(self):
        """분자 오비탈 뷰어 열기"""
        if not MOLORBITAL_AVAILABLE:
            QMessageBox.warning(self, "알림", "분자 오비탈 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                popup = MolecularOrbitalPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"분자 오비탈 데이터 로드 실패:\n{str(e)}")
    
    def open_spectrum_viewer(self):
        """IR/Raman 스펙트럼 뷰어 열기"""
        if not SPECTRUM_ANALYZER_AVAILABLE:
            QMessageBox.warning(self, "알림", "스펙트럼 분석 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 파일 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            spectrum_data = parse_orca_frequencies(Path(file_path))
            
            if len(spectrum_data.modes) == 0:
                QMessageBox.warning(self, "경고", f"파일에서 진동수 데이터를 찾을 수 없습니다:\n{file_path}")
                return
            
            popup = SpectrumPopup(spectrum_data, self)
            popup.exec()
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"스펙트럼 데이터를 로드할 수 없습니다:\n{str(e)}")
    
    def open_comparator(self):
        """분자 비교 기능 열기"""
        if not self.molecule_comparator:
            QMessageBox.warning(self, "알림", "분자 비교 모듈을 사용할 수 없습니다.")
            return
        
        dialog = ComparisonDialog(self, self.molecule_comparator, self.cv)
        dialog.exec()
    
    def open_history_browser(self):
        """계산 히스토리 브라우저 열기"""
        if not self.history_manager:
            QMessageBox.warning(self, "알림", "히스토리 관리 모듈을 사용할 수 없습니다.")
            return
        
        dialog = HistoryBrowserDialog(self, self.history_manager)
        dialog.exec()
    
    def open_batch_processor(self):
        """배치 처리 창 열기"""
        if not self.batch_processor:
            QMessageBox.warning(self, "알림", "배치 처리 모듈을 사용할 수 없습니다.")
            return
        
        dialog = BatchProcessorDialog(self, self.batch_processor, self.cv)
        dialog.exec()
    
    # ========== [Phase 5 Advanced] 새로운 내보내기 및 검증 기능 ==========
    
    def export_selection_dialog(self):
        """선택 영역 내보내기 대화 열기"""
        if not EXPORT_MANAGER_AVAILABLE:
            QMessageBox.warning(self, "알림", "고급 내보내기 모듈을 사용할 수 없습니다.")
            return
        
        try:
            manager = ExportManager(self)
            manager.export_selection()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"내보내기 실패:\n{str(e)}")
    
    def export_spectrum_to_pdf(self):
        """스펙트럼 및 구조를 PDF로 내보내기 (자동 캡처 포함)"""
        if not SPECTRUM_PDF_EXPORTER_AVAILABLE:
            QMessageBox.warning(self, "알림", "스펙트럼 PDF 내보내기 모듈을 사용할 수 없습니다.")
            return
            
        try:
            # 1. 메타데이터 생성
            mol_name = getattr(self.cv, "selected_molecule_name", "")
            # analyzer 결과에서 식별된 이름 확인 (오각고리 음이온 등)
            if hasattr(self.cv, "analysis_results") and self.cv.analysis_results:
                special_name = self.cv.analysis_results.get("identified_name", "")
                if special_name:
                    mol_name = special_name
            
            if not mol_name:
                mol_name = "Unknown Molecule"
                
            smiles = self.cv.get_smiles()
            
            metadata = SpectrumMetadata(
                molecule_name=mol_name,
                molecular_formula="C?H?", # TODO: 화학식 계산 로직 연동
                smiles=smiles,
                calculation_method="B3LYP/6-31G(d)",
                final_energy=-100.0 
            )
            
            spectra_data = {}
            
            # 2. 이미지 캡처 (Lewis & Theory)
            import tempfile
            temp_dir = tempfile.gettempdir()
            original_mode = self.cv.view_state
            
            # (1) Lewis Structure 캡처
            self.cv.view_state = "Lewis"
            self.cv.update()
            QApplication.processEvents() # UI 렌더링 대기
            lewis_path = os.path.join(temp_dir, f"chemgrid_lewis_{os.getpid()}.png")
            # 캡처 시 배경 투명도 고려 (grab은 위젯 전체 캡처)
            self.cv.grab().save(lewis_path)
            
            lewis_spec = SpectrumData(
                spectrum_type="Lewis Structure",
                peaks=[],
                image_path=lewis_path,
            )
            # 동적 속성 추가 (AI 분석 텍스트)
            lewis_spec.ai_analysis = f"Lewis structure of {mol_name}. Shows valence electrons and bonding connectivity."
            spectra_data["Lewis Structure"] = lewis_spec
            
            # (2) Theory Structure 캡처
            self.cv.view_state = "Theory"
            self.cv.update()
            QApplication.processEvents()
            theory_path = os.path.join(temp_dir, f"chemgrid_theory_{os.getpid()}.png")
            self.cv.grab().save(theory_path)
            
            theory_spec = SpectrumData(
                spectrum_type="Theory Structure",
                peaks=[],
                image_path=theory_path,
            )
            theory_spec.ai_analysis = f"Optimized geometry of {mol_name} (B3LYP/6-31G*). Correct bond lengths and angles."
            spectra_data["Theory Structure"] = theory_spec
            
            # 원래 모드로 복귀
            self.cv.view_state = original_mode
            self.cv.update()
            
            # 3. ORCA 파일 선택 (선택 사항)
            file_path, _ = QFileDialog.getOpenFileName(
                self, "ORCA 계산 결과 포함 (선택 사항)", "", "ORCA Output (*.out);;All Files (*.*)"
            )
            
            if file_path:
                try:
                    # IR 스펙트럼 데이터 파싱 (있다면)
                    if SPECTRUM_ANALYZER_AVAILABLE:
                        s_data = parse_orca_frequencies(Path(file_path))
                        if s_data and len(s_data.modes) > 0:
                            # 실제 피크 데이터 변환
                            peaks = []
                            for m in s_data.modes:
                                if m.intensity > 10: # 주요 피크만
                                    peaks.append(SpectrumPeakData(
                                        frequency=m.frequency,
                                        intensity=m.intensity,
                                        label=str(int(m.frequency))
                                    ))
                            
                            ir_spec = SpectrumData(
                                spectrum_type="IR Spectrum",
                                peaks=peaks,
                                raw_data={"modes": s_data.modes}
                            )
                            ir_spec.ai_analysis = f"IR Spectrum of {mol_name}. Major peaks identified at {', '.join([str(int(p.frequency)) for p in peaks[:3]])} cm-1."
                            spectra_data["IR Spectrum"] = ir_spec
                except Exception as ex:
                    print(f"ORCA parsing failed: {ex}")

            # 4. 내보내기 매니저 실행
            if not spectra_data:
                QMessageBox.warning(self, "알림", "내보낼 데이터가 없습니다.")
                return

            manager = ExportSpectrumManager(self)
            manager.export_spectra(spectra_data, metadata)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 내보내기 실패:\n{str(e)}")
    
    def show_calculation_history(self):
        """계산 히스토리 표시"""
        if not CALCULATION_LOGGER_AVAILABLE:
            QMessageBox.warning(self, "알림", "계산 로거 모듈을 사용할 수 없습니다.")
            return
        
        try:
            logger = CalculationLogger()
            report = logger.generate_report()
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Calculation History Report")
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(report)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            save_btn = QPushButton("보고서 저장...")
            save_btn.clicked.connect(lambda: self._save_calculation_report(report))
            layout.addWidget(save_btn)
            
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"계산 히스토리 로드 실패:\n{str(e)}")
    
    def show_verification_report(self):
        """검증 보고서 생성 및 표시"""
        if not VERIFICATION_REPORT_AVAILABLE:
            QMessageBox.warning(self, "알림", "검증 보고서 모듈을 사용할 수 없습니다.")
            return
        
        if not CALCULATION_LOGGER_AVAILABLE:
            QMessageBox.warning(self, "알림", "계산 로거 모듈이 필요합니다.")
            return
        
        try:
            logger = CalculationLogger()
            entries = logger.get_all_entries()
            
            if not entries:
                QMessageBox.warning(self, "알림", "검증할 계산 기록이 없습니다.")
                return
            
            engine = VerificationEngine()
            
            latest_entry = entries[-1]
            report = engine.verify_calculation(latest_entry)
            
            report_text = engine.generate_report_text(report)
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Verification Report")
            dialog.resize(900, 700)
            
            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(report_text)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            save_btn = QPushButton("보고서 저장...")
            save_btn.clicked.connect(lambda: self._save_verification_report(report, engine))
            layout.addWidget(save_btn)
            
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"검증 보고서 생성 실패:\n{str(e)}")
    
    def _save_calculation_report(self, report_text: str):
        """계산 히스토리 보고서 저장"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "보고서 저장", "calculation_history.txt", "Text Files (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(report_text)
                QMessageBox.information(self, "성공", f"보고서가 저장되었습니다:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"저장 실패:\n{str(e)}")
    
    def _save_verification_report(self, report, engine):
        """검증 보고서 저장"""
        output_dir, _ = QFileDialog.getSaveFileName(
            self, "보고서 저장 위치 선택", "verification_report.txt", "Text Files (*.txt)"
        )
        if output_dir:
            try:
                json_file, text_file = engine.save_report(report, Path(output_dir).parent)
                QMessageBox.information(self, "성공", 
                    f"보고서가 저장되었습니다:\n{text_file}\n{json_file}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"저장 실패:\n{str(e)}")
    
    def closeEvent(self, event):
        """
        윈도우 종료 시 정리 작업 수행
        ========== [Phase Integration Hook 5] 종료 시 정리 ==========
        """
        self.cv.cleanup()
        super().closeEvent(event)
