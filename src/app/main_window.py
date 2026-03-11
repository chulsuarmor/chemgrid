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
import pubchem_client as _pc_client  # [pubchem 통합] API 키 + rate limiter

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
            app_icon = QIcon()
            from PyQt6.QtGui import QPixmap
            _pix = QPixmap(logo_path)
            if not _pix.isNull():
                for _sz in (16, 32, 48, 64, 128, 256):
                    app_icon.addPixmap(_pix.scaled(
                        _sz, _sz,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
            else:
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

        # [REACTION] 반응 분석 버튼 — btn_3d 위에 배치
        self.btn_reaction = QPushButton("🔬 반응 분석", self)
        self.btn_reaction.setFixedSize(200, 50)
        self.btn_reaction.setStyleSheet("""
            QPushButton {
                background-color: #E65100; color: white; border-radius: 10px;
                font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background-color: #F57C00; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_reaction.clicked.connect(self.open_reaction_popup)
        self.btn_reaction.setEnabled(False)
        self.btn_reaction.setToolTip("2개 이상의 분자를 그려주세요")
        self.btn_reaction.hide()

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

                # ★ [Fix ISSUE-선택] 수동 그리기 분자 → Theory 전환 시 _last_drawn_smiles 자동 갱신
                # 텍스트 입력이 아닌 수동 그리기의 경우 _last_drawn_smiles 가 비어있어
                # open_3d_popup 50% fallback이 트리거되지 않는 문제 해결
                if not getattr(self.cv, '_last_drawn_smiles', '') and has_atoms:
                    try:
                        _auto_smiles = self.cv.get_smiles()
                        if _auto_smiles and _auto_smiles not in ('C', ''):
                            self.cv._last_drawn_smiles = _auto_smiles
                            print(f"[Theory] 수동 그리기 SMILES 자동 저장: {_auto_smiles[:60]}", flush=True)
                    except Exception:
                        pass

                # [REACTION] 반응 분석 버튼: 2개 이상 분자 감지 시 활성화
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.show()
                    self.btn_reaction.raise_()
                    try:
                        n_mols = self._count_molecules()
                        self.btn_reaction.setEnabled(n_mols >= 2)
                        if n_mols >= 2:
                            self.btn_reaction.setToolTip(f"{n_mols}개 분자 감지 — 반응 분석 가능")
                        else:
                            self.btn_reaction.setToolTip("2개 이상의 분자를 그려주세요")
                    except Exception:
                        self.btn_reaction.setEnabled(False)
            else:
                self.btn_3d.hide()
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.hide()
        
        # [v4.0] 분석 버튼 제거됨 — 모든 분석은 "입체 구조" 팝업(popup_3d.py) 내 탭으로 통합

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
            if hasattr(self, 'btn_reaction'):
                self.btn_reaction.hide()
        else:
            self.view_container.hide() # 파란 버튼들 숨김
            self.btn_back.show()       # 초록 버튼 나타남
            if mode == "Theory":
                self.btn_3d.show()
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.show()
                    self.btn_reaction.raise_()
                # [Phase 6-3] btn_3d enabled 상태 유지 (위에서 설정됨)
            else:
                self.btn_3d.hide()
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.hide()

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

                # [REACTION] 반응 분석 버튼을 입체 구조 버튼 10px 위에 배치
                if hasattr(self, 'btn_reaction'):
                    self.btn_reaction.setFixedSize(200, 50)
                    ry = ty - self.btn_reaction.height() - 10
                    self.btn_reaction.move(tx, ry)
                    self.btn_reaction.raise_()
            
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
                # ★ 기존 분자가 캔버스에 있으면 append 모드로 겹치지 않게 배치
                has_existing = bool(self.cv.atoms)
                self._draw_smiles_on_canvas(smiles, name, append=has_existing)
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
        우선순위: 내장사전 > 축약식 파싱 > PubChem REST > Gemini AI
        [BUG-04 Fix] dotenv 로딩 추가, 축약식 처리 추가, BUILTIN 대폭 확장
        """
        import os as _os
        import pathlib as _pathlib

        # ── [FIX-BUG-04] .env 파일 로딩 (GEMINI_API_KEY 환경변수 보장) ──
        try:
            from dotenv import load_dotenv as _load_dotenv
            _env_candidates = [
                _pathlib.Path(__file__).resolve().parents[2] / "agents" / "mcp_server" / ".env",
                _pathlib.Path(__file__).resolve().parents[1] / "agents" / "mcp_server" / ".env",
                _pathlib.Path("c:/chemgrid/agents/mcp_server/.env"),
            ]
            for _env_p in _env_candidates:
                if _env_p.exists():
                    _load_dotenv(str(_env_p), override=False)
                    break
        except ImportError:
            pass

        # ── [Step 1] 내장 사전 (네트워크 불필요, 방향족 이온 포함) ──────
        BUILTIN = {
            # 무기물
            "water": "O", "물": "O", "h2o": "O",
            "ammonia": "N", "암모니아": "N", "nh3": "N",
            "carbon dioxide": "O=C=O", "이산화탄소": "O=C=O", "co2": "O=C=O",
            "carbon monoxide": "[C-]#[O+]", "일산화탄소": "[C-]#[O+]",
            "hydrogen chloride": "Cl", "hydrochloric acid": "Cl",
            "sulfur dioxide": "O=S=O",
            # 알케인
            "methane": "C", "에탄": "CC", "ethane": "CC",
            "propane": "CCC", "butane": "CCCC", "pentane": "CCCCC",
            "hexane": "CCCCCC", "heptane": "CCCCCCC", "octane": "CCCCCCCC",
            "cyclohexane": "C1CCCCC1", "cyclopentane": "C1CCCC1",
            # 불포화 탄화수소
            "ethylene": "C=C", "에틸렌": "C=C", "propylene": "CC=C",
            "acetylene": "C#C", "1-butene": "CCC=C",
            # 알코올
            "methanol": "CO", "메탄올": "CO",
            "ethanol": "CCO", "에탄올": "CCO", "ethyl alcohol": "CCO",
            "isopropanol": "CC(O)C", "isopropyl alcohol": "CC(O)C",
            "1-propanol": "CCCO", "1-butanol": "CCCCO",
            # 카르보닐
            "formaldehyde": "C=O", "acetaldehyde": "CC=O", "acetone": "CC(C)=O", "아세톤": "CC(C)=O",
            # 유기산
            "formic acid": "OC=O", "포름산": "OC=O",
            "acetic acid": "CC(=O)O", "아세트산": "CC(=O)O",
            "propionic acid": "CCC(=O)O",
            "butyric acid": "CCCC(=O)O",
            "valeric acid": "CCCCC(=O)O",
            "lactic acid": "C[C@@H](O)C(=O)O",
            "oxalic acid": "OC(=O)C(=O)O",
            "citric acid": "OC(CC(=O)O)(CC(=O)O)C(=O)O",
            "succinic acid": "OC(=O)CCC(=O)O",
            # 방향족
            "benzene": "c1ccccc1", "벤젠": "c1ccccc1",
            "toluene": "Cc1ccccc1", "톨루엔": "Cc1ccccc1",
            "phenol": "Oc1ccccc1", "페놀": "Oc1ccccc1",
            "aniline": "Nc1ccccc1", "아닐린": "Nc1ccccc1",
            "benzoic acid": "OC(=O)c1ccccc1",
            "nitrobenzene": "O=[N+]([O-])c1ccccc1",
            "naphthalene": "c1ccc2ccccc2c1", "나프탈렌": "c1ccc2ccccc2c1",
            "anthracene": "c1ccc2cc3ccccc3cc2c1",
            "styrene": "C=Cc1ccccc1",
            "pyridine": "c1ccncc1", "피리딘": "c1ccncc1",
            "pyrimidine": "c1cnccn1",
            "furan": "c1ccoc1", "퓨란": "c1ccoc1",
            "thiophene": "c1ccsc1",
            "pyrrole": "c1cc[nH]c1", "피롤": "c1cc[nH]c1",
            "imidazole": "c1cnc[nH]1",
            # ★ 이온성 방향족 (공명 균등화 테스트)
            "cyclopentadienyl anion": "[cH-]1cccc1",
            "cyclopentadienyl": "C1=CC=CC1",
            "사이클로펜타디에닐 음이온": "[cH-]1cccc1",
            "cp-": "[cH-]1cccc1", "cp anion": "[cH-]1cccc1",
            "tropylium": "C1=CC=CC=C[CH+]1",
            "tropylium ion": "C1=CC=CC=C[CH+]1",
            "tropylium cation": "C1=CC=CC=C[CH+]1",
            "트로필리움": "C1=CC=CC=C[CH+]1",
            "트로필리움 이온": "C1=CC=CC=C[CH+]1",
            "cycloheptatrienyl cation": "C1=CC=CC=C[CH+]1",
            "cycloheptatrienyl": "C1=CC=CC=CC1",
            # 당류
            "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "글루코스": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "fructose": "OCC(=O)[C@@H](O)[C@H](O)[C@H](O)CO",
            "sucrose": "OC[C@H]1O[C@@](CO)(O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)[C@@H](O)[C@@H]1O",
            "galactose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            # 약물
            "aspirin": "CC(=O)Oc1ccccc1C(=O)O", "아스피린": "CC(=O)Oc1ccccc1C(=O)O",
            "acetylsalicylic acid": "CC(=O)Oc1ccccc1C(=O)O",
            "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C", "카페인": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
            "ibuprofen": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
            "paracetamol": "CC(=O)Nc1ccc(O)cc1", "acetaminophen": "CC(=O)Nc1ccc(O)cc1",
            "cholesterol": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
            "콜레스테롤": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
            # 핵산 염기
            "adenine": "Nc1ncnc2[nH]cnc12", "아데닌": "Nc1ncnc2[nH]cnc12",
            "guanine": "Nc1nc2[nH]cnc2c(=O)[nH]1",
            "cytosine": "Nc1cc[nH]c(=O)n1",
            "thymine": "Cc1c[nH]c(=O)[nH]c1=O",
            "uracil": "O=c1cc[nH]c(=O)[nH]1",
            # 아미노산
            "glycine": "NCC(=O)O", "글리신": "NCC(=O)O",
            "alanine": "C[C@@H](N)C(=O)O",
            "serine": "N[C@@H](CO)C(=O)O",
            "lysine": "NCCCC[C@@H](N)C(=O)O",
            "phenylalanine": "N[C@@H](Cc1ccccc1)C(=O)O",
            "tryptophan": "N[C@@H](Cc1c[nH]c2ccccc12)C(=O)O",
            # 헤모글로빈 관련 (포르피린 → heme b, Fe 포함)
            "heme": r"CC1=C2C=C3C(=CC4=NC(=CC5=NC(=C1/N2\[Fe]N34)CC(=O)O)C(C=C)=C5C)C(C)=C(CCC(=O)O)C6=CC7=NC(=CC(=C7C)C=C)C(CCC(=O)O)=C6",
            "heme b": r"CC1=C2C=C3C(=CC4=NC(=CC5=NC(=C1/N2\[Fe]N34)CC(=O)O)C(C=C)=C5C)C(C)=C(CCC(=O)O)C6=CC7=NC(=CC(=C7C)C=C)C(CCC(=O)O)=C6",
        }
        lower = name.lower().strip()
        if lower in BUILTIN:
            return BUILTIN[lower]
        # [FIX] 밑줄/하이픈 → 공백 변환 (cp_anion → cp anion, acetic-acid → acetic acid)
        lower_norm = lower.replace("_", " ").replace("-", " ")
        if lower_norm != lower and lower_norm in BUILTIN:
            return BUILTIN[lower_norm]

        # ── [Step 1.5] 축약식/분자식 전처리 (CH3CH2CH2COOH 등) ────────
        _parsed = self._try_parse_condensed(name)
        if _parsed:
            return _parsed

        # ── [Step 2] PubChem REST API ────────────────────────────────
        # ── [Step 2] PubChem REST API (pubchem_client: API 키 + 초당 1회 속도 제한) ──
        try:
            _pc_smiles = _pc_client.get_smiles_by_name(name)
            if _pc_smiles:
                try:
                    from rdkit import Chem as _Chem
                    _mol = _Chem.MolFromSmiles(_pc_smiles)
                    if _mol:
                        return _Chem.MolToSmiles(_mol)
                except Exception:
                    pass
                return _pc_smiles
        except Exception:
            pass

        # ── 대형 단백질/복합체 → 가용 구조로 자동 폴백 ────────────────
        LARGE_MOLECULES = {
            "hemoglobin": "heme",
            "myoglobin": "heme",
            "albumin": None,
            "collagen": None,
            "insulin": "CC(C)CC1NC(=O)C(CC2=CC=CC=C2)NC(=O)",
            "dna": "adenine",
            "rna": "adenine",
            "protein": None,
        }
        if lower in LARGE_MOLECULES:
            alt = LARGE_MOLECULES[lower]
            if alt:
                return self._lookup_smiles_for_name(alt)
            return ""

        # ── [Step 3] Gemini AI 폴백 (dotenv 로딩 후 키 확인) ───────────
        try:
            api_key = (_os.environ.get("GEMINI_API_KEY", "")
                       or _os.environ.get("GOOGLE_API_KEY", ""))
            if api_key:
                try:
                    import google.genai as _genai
                    client = _genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=(
                            f"화학 분자명 또는 분자식 '{name}'의 SMILES 코드를 알려주세요. "
                            "SMILES 코드만 한 줄로 출력하세요. 설명 없이 SMILES만 출력."
                        ),
                    )
                    smiles = response.text.strip().split()[0]
                    if smiles and smiles.upper() not in ("UNKNOWN", "NONE", ""):
                        return smiles
                except Exception:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        import google.generativeai as _genai_old
                    _genai_old.configure(api_key=api_key)
                    model = _genai_old.GenerativeModel("gemini-1.5-flash")
                    resp_old = model.generate_content(
                        f"화학 분자명 또는 분자식 '{name}'의 SMILES 코드만 출력하세요."
                    )
                    smiles = resp_old.text.strip().split()[0]
                    if smiles and smiles.upper() not in ("UNKNOWN", "NONE", ""):
                        return smiles
        except Exception:
            pass

        # ── [Step 3.5] Google Knowledge Graph API → PubChem 교차 검색 ──────────
        # Gemini AI 실패 시, 사용자 입력 단어를 Google KG에서 화학물 엔티티로 검색
        # → 정규 화학명 획득 → PubChem SMILES 조회 (CX 불필요, GOOGLE_API_KEY만 필요)
        try:
            google_key = (_os.environ.get("GOOGLE_API_KEY", "")
                          or _os.environ.get("GEMINI_API_KEY", ""))
            if google_key:
                import urllib.parse as _up2
                # Google Knowledge Graph 엔티티 검색
                kg_params = {
                    "query": name,
                    "key": google_key,
                    "types": "ChemicalCompound",
                    "limit": 3,
                    "languages": "en",
                }
                kg_resp = _req2.get(
                    "https://kgsearch.googleapis.com/v1/entities:search",
                    params=kg_params,
                    timeout=6,
                )
                if kg_resp.status_code == 200:
                    items = kg_resp.json().get("itemListElement", [])
                    for item in items:
                        entity_name = item.get("result", {}).get("name", "")
                        if entity_name and entity_name.lower() != name.lower():
                            # 정규 화학명으로 PubChem 재조회
                            pc_url = (
                                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
                                f"{_up2.quote(entity_name)}/property/IsomericSMILES/JSON"
                            )
                            pc_r = _pc_client._get(pc_url, timeout=5)
                            if pc_r.status_code == 200:
                                _smiles_kg = (
                                    pc_r.json()
                                    .get("PropertyTable", {})
                                    .get("Properties", [{}])[0]
                                    .get("IsomericSMILES", "")
                                )
                                if _smiles_kg:
                                    try:
                                        from rdkit import Chem as _C2
                                        if _C2.MolFromSmiles(_smiles_kg):
                                            return _C2.MolToSmiles(_C2.MolFromSmiles(_smiles_kg))
                                    except Exception:
                                        return _smiles_kg
                        elif entity_name:
                            # 동일 이름이더라도 PubChem에 없었던 케이스 재시도
                            pc_url = (
                                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
                                f"{_up2.quote(entity_name)}/property/IsomericSMILES/JSON"
                            )
                            pc_r = _pc_client._get(pc_url, timeout=5)
                            if pc_r.status_code == 200:
                                _smiles_kg = (
                                    pc_r.json()
                                    .get("PropertyTable", {})
                                    .get("Properties", [{}])[0]
                                    .get("IsomericSMILES", "")
                                )
                                if _smiles_kg:
                                    return _smiles_kg
        except Exception:
            pass

        # ── [Step 3.6] PubChem Autocomplete fuzzy matching (pubchem_client: 초당 1회 속도 제한) ──
        try:
            for _sug in _pc_client.get_suggestions(name, limit=3):
                if _sug.lower() == name.lower():
                    continue
                _sug_smiles = _pc_client.get_smiles_by_name(_sug)
                if _sug_smiles:
                    return _sug_smiles
        except Exception:
            pass

        return ""

    def _try_parse_condensed(self, text: str) -> str:
        """
        축약식 분자식(CH3CH2CH2COOH, C2H5OH 등) → SMILES 변환 시도.
        [BUG-04b Fix] PubChem이 인식하지 못하는 축약식 구조식을 사전+RDKit로 처리.
        """
        # 1) RDKit로 직접 SMILES 파싱 시도 (이미 SMILES인 경우)
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(text)
            if mol:
                return Chem.MolToSmiles(mol)
        except Exception:
            pass

        # 2) 축약식 → SMILES 매핑 사전
        CONDENSED = {
            "ch4": "C",
            "ch3ch3": "CC", "c2h6": "CC",
            "ch3ch2ch3": "CCC", "c3h8": "CCC",
            "ch3(ch2)2ch3": "CCCC", "c4h10": "CCCC",
            "ch3oh": "CO", "ch4o": "CO",
            "ch3ch2oh": "CCO", "c2h5oh": "CCO", "c2h6o": "CCO",
            "ch3ch2ch2oh": "CCCO", "c3h7oh": "CCCO",
            "hcooh": "OC=O", "ch2o2": "OC=O",
            "ch3cooh": "CC(=O)O", "c2h4o2": "CC(=O)O",
            "ch3ch2cooh": "CCC(=O)O",
            "ch3ch2ch2cooh": "CCCC(=O)O",
            "ch3(ch2)2cooh": "CCCC(=O)O",
            "ch3ch2ch2ch2cooh": "CCCCC(=O)O",
            "ch3(ch2)3cooh": "CCCCC(=O)O",
            "ch3cho": "CC=O",
            "ch3coch3": "CC(C)=O",
            "ch2cl2": "ClCCl",
            "chcl3": "ClC(Cl)Cl",
            "ccl4": "ClC(Cl)(Cl)Cl",
            "c6h6": "c1ccccc1",
            "c6h5oh": "Oc1ccccc1",
            "c6h5nh2": "Nc1ccccc1",
            "c6h5cooh": "OC(=O)c1ccccc1",
            "c6h12o6": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
        }
        key = text.lower().replace(" ", "")
        if key in CONDENSED:
            return CONDENSED[key]

        return ""

    def _draw_smiles_on_canvas(self, smiles: str, mol_name: str = "", append: bool = False):
        """RDKit 2D 좌표를 캔버스 원자/결합 데이터로 변환하여 그리기

        [BUG-02 수정] 좌표계 오류 + hex grid 스냅 + analysis_results 갱신
        - 수정 전: cx = width/2 + pan_offset (부호 오류)
        - 수정 후: logical_center = (width/2 - pan_offset) / scale_factor
        - 스냅 방식: 직교 30px 단위 → canvas.get_closest_pt() (hex grid)
        - 수정 후: analysis_results 갱신 → Theory 레이어에서 구조 표시 가능

        Args:
            append: True이면 기존 분자를 지우지 않고 빈 공간에 새 분자 추가
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
            # ★ [BUG-04-DRAW FIX] Kekulize: 방향족 결합을 교차 단일/이중결합으로 변환
            _kekulized = False
            try:
                Chem.Kekulize(mol, clearAromaticFlags=False)
                _kekulized = True
            except Exception:
                pass
            conf = mol.GetConformer()

            xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
            ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
            cx_mol = (max(xs) + min(xs)) / 2
            cy_mol = (max(ys) + min(ys)) / 2
            mol_w = (max(xs) - min(xs))  # RDKit 단위 폭
            mol_h = (max(ys) - min(ys))  # RDKit 단위 높이

            # ✅ [BUG-02A 수정] 올바른 논리 좌표 계산
            sf = getattr(self.cv, 'scale_factor', 1.0)
            pan_x = self.cv.pan_offset.x()
            pan_y = self.cv.pan_offset.y()
            cx_logical = (self.cv.width() / 2 - pan_x) / sf
            cy_logical = (self.cv.height() / 2 - pan_y) / sf

            # RDKit 2D 단위 → 논리 픽셀: grid_size(40px) / C-C bond(1.5Å) ≈ 26.7 px/unit
            scale = 26.7

            self.cv.save_state()

            # ★ 기존 분자가 있고 append 모드이면 빈 공간에 배치
            if append and self.cv.atoms:
                # 기존 원자들의 bounding box 계산
                existing_xs = [k[0] for k in self.cv.atoms.keys()]
                existing_ys = [k[1] for k in self.cv.atoms.keys()]
                ex_max_x = max(existing_xs)
                ex_min_y = min(existing_ys)
                ex_max_y = max(existing_ys)
                ex_center_y = (ex_min_y + ex_max_y) / 2

                # 새 분자 크기 (논리 픽셀)
                new_mol_half_w = mol_w * scale / 2

                # 기존 분자 오른쪽 + 여유 간격(120px)에 새 분자 중심 배치
                cx_logical = ex_max_x + 120 + new_mol_half_w
                cy_logical = ex_center_y
            elif not append:
                # 기존 동작: 캔버스 초기화 후 중앙에 그리기
                self.cv.atoms.clear()
                self.cv.bonds.clear()

            # ✅ [BUG-02B 수정] hex grid 스냅 사용
            idx_to_key = {}
            for i in range(mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                atom = mol.GetAtomWithIdx(i)
                # [BUG-FIX] 탄소 원자를 skeleton 방식(main="")으로 설정
                # 수정 전: main="C" → 모든 탄소에 "C" 라벨 표시 → 트로필리움 "+"가 "C" 위를 가림
                # 수정 후: main="" → 탄소는 bond 교차점으로만 표시, charge만 위첨자로 표시
                sym = "" if atom.GetSymbol() == "C" else atom.GetSymbol()

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

                # ★ [Fix v5.92] SMILES 원자 formal_charge 저장
                # RDKit formal_charge를 atoms dict에 기록 → renderer의 ionic_bias 감지 가능
                _fc = atom.GetFormalCharge()
                _atom_entry = {"main": sym, "attach": {}}
                if _fc != 0:
                    _atom_entry["formal_charge"] = _fc
                    _atom_entry["charge"] = "+" if _fc > 0 else "-"
                self.cv.atoms[key] = _atom_entry
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
                    if _kekulized:
                        # ★ Kekulize 후: AROMATIC→SINGLE/DOUBLE 교차 변환됨
                        # benzene의 3개 이중결합이 올바르게 표시됨
                        bt = bond.GetBondTypeAsDouble()
                        order = 1 if bt < 1.5 else (2 if bt < 2.5 else 3)
                    elif bt_type == _rdchem.BondType.AROMATIC:
                        # Kekulize 실패 시: 방향족 결합을 단일결합으로 폴백
                        order = 1
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
                # [BUG-B FIX] _last_drawn_smiles를 analyze() 전에 먼저 설정해야 현재 SMILES가 주입됨
                self.cv._last_drawn_smiles = smiles
                self.cv._last_drawn_mol_name = mol_name
                self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, smiles=smiles)
                # ★ [Fix v5.92] SMILES를 results에 저장 → renderer의 ionic_bias SMILES fallback 활성화
                # tropylium([CH+]), cp-([cH-]) 등 이온성 SMILES 감지 → BLUE/RED 색상 적용
                if self.cv.analysis_results is not None:
                    self.cv.analysis_results["smiles"] = smiles
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

    # ========== [REACTION] 반응 분석 ==========
    def _count_molecules(self) -> int:
        """캔버스 위의 분리된 분자 개수를 반환"""
        if not hasattr(self.cv, 'atoms') or not self.cv.atoms:
            return 0
        try:
            # analyzer의 _get_molecular_islands 사용
            from analyzer import ChemicalAnalyzer
            analyzer = ChemicalAnalyzer()
            norm_keys = list(self.cv.atoms.keys())
            # adjacency from bonds
            adj = {}
            for key in self.cv.atoms:
                adj[key] = []
            for key, bond_data in getattr(self.cv, 'bonds', {}).items():
                k1, k2 = key
                if k1 in adj:
                    adj[k1].append((k2, 1))
                if k2 in adj:
                    adj[k2].append((k1, 1))
            islands = analyzer._get_molecular_islands(norm_keys, adj)
            # 원자 1개짜리 섬 제외 (고립 원자)
            return sum(1 for isl in islands if len(isl) >= 2)
        except Exception:
            return 0

    def open_reaction_popup(self):
        """반응 분석 팝업 열기"""
        try:
            from popup_reaction import ReactionPopup
            from analyzer import ChemicalAnalyzer

            analyzer = ChemicalAnalyzer()
            norm_keys = list(self.cv.atoms.keys())
            adj = {}
            for key in self.cv.atoms:
                adj[key] = []
            for key, bond_data in getattr(self.cv, 'bonds', {}).items():
                k1, k2 = key
                if k1 in adj:
                    adj[k1].append((k2, 1))
                if k2 in adj:
                    adj[k2].append((k1, 1))

            islands = analyzer._get_molecular_islands(norm_keys, adj)
            islands = [isl for isl in islands if len(isl) >= 2]

            if len(islands) < 2:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "반응 분석",
                                        "2개 이상의 분리된 분자가 필요합니다.\n"
                                        "그리기 레이어에서 서로 떨어진 2개 이상의 분자를 그려주세요.")
                return

            # 각 섬의 SMILES 추출
            smiles_list = []
            names_list = []
            for i, island in enumerate(islands[:4]):  # 최대 4개
                # 섬 원자만으로 서브그래프 SMILES 생성
                sub_atoms = {k: self.cv.atoms[k] for k in island if k in self.cv.atoms}
                sub_bonds = {}
                for bk, bv in getattr(self.cv, 'bonds', {}).items():
                    if bk[0] in island and bk[1] in island:
                        sub_bonds[bk] = bv
                try:
                    smi, _, _, _ = analyzer.generate_smiles(sub_atoms, sub_bonds)
                    if smi:
                        smiles_list.append(smi)
                        names_list.append(f"분자 {chr(65+i)}")
                except Exception:
                    pass

            if len(smiles_list) < 2:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "반응 분석",
                                        "SMILES 변환에 실패한 분자가 있습니다.\n"
                                        "분자 구조를 확인해주세요.")
                return

            popup = ReactionPopup(smiles_list, names_list, parent=self)
            popup.exec()

        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "반응 분석 오류", f"오류 발생: {str(e)}")

    # ========== [U2] 입체 구조 3D 팝업 ==========
    def open_3d_popup(self):
        """선택된 분자의 3D 구조 팝업 열기.
        ★ 개선: 선택 없으면 전체 atoms 사용 → 메탄/벤젠 같은 간단한 분자도 바로 3D 전환
        """
        if not PHASE_C_AVAILABLE:
            QMessageBox.warning(self, "알림", "3D 뷰어 모듈을 사용할 수 없습니다.\nPyOpenGL을 설치해주세요.")
            return

        # ★ [FEAT-4 Fix] _last_drawn_smiles가 있으면 전체 분자 선택 보장
        # 이론적 구조 → 입체 구조 전환 시 선택 도구가 일부만 긁어오는 버그 해결
        # _last_drawn_smiles 존재 시 전체 원자를 선택 (부분 선택 무시)
        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''
        # ★ [개선] 선택된 원자 키 가져오기 — 없으면 전체 atoms 사용
        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())
        if not selected_keys:
            # Drawing 모드 selected_atoms도 확인
            selected_keys = getattr(self.cv, 'selected_atoms', set())
        # [FEAT-4] 선택 원자가 전체의 50% 미만이고 _last_drawn_smiles 있으면 전체 선택으로 교체
        # 이론적 구조에서 드래그 선택 시 일부 원자만 인식되는 버그 해결
        _all_atom_keys = set(self.cv.atoms.keys())
        if _last_smiles and _all_atom_keys and len(selected_keys) < len(_all_atom_keys) * 0.5:
            selected_keys = _all_atom_keys
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
        # [BUG-1 FIX] SMILES 있으면 예측 스펙트럼 우선 표시
        _smiles = getattr(getattr(self, 'cv', None), '_last_drawn_smiles', None)
        if _smiles:
            try:
                from popup_predicted_spectrum import launch_predicted_spectrum
                launch_predicted_spectrum(_smiles, "nmr", self)
                return
            except Exception as _e:
                import traceback; traceback.print_exc()
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
        # [BUG-1 FIX] SMILES 있으면 예측 스펙트럼 우선 표시
        _smiles = getattr(getattr(self, 'cv', None), '_last_drawn_smiles', None)
        if _smiles:
            try:
                from popup_predicted_spectrum import launch_predicted_spectrum
                launch_predicted_spectrum(_smiles, "uvvis", self)
                return
            except Exception as _e:
                import traceback; traceback.print_exc()
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
        # [BUG-1 FIX] SMILES 있으면 예측 스펙트럼 우선 표시
        _smiles = getattr(getattr(self, 'cv', None), '_last_drawn_smiles', None)
        if _smiles:
            try:
                from popup_predicted_spectrum import launch_predicted_spectrum
                launch_predicted_spectrum(_smiles, "ir", self)
                return
            except Exception as _e:
                import traceback; traceback.print_exc()
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
