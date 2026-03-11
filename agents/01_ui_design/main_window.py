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
                             QMessageBox, QFileDialog, QTextEdit, QDialog, QWidget)
from PyQt6.QtGui import QAction, QIcon, QPainter, QColor
from PyQt6.QtCore import Qt, QPointF, QPoint
from PyQt6.QtPrintSupport import QPrinter

from ui_utils import load_icon
from dialogs import (PeriodicTableDialog, PenSettingsBox,
                     ComparisonDialog, HistoryBrowserDialog, BatchProcessorDialog)
from toolbar_setup import setup_toolbars
from draw import MoleculeCanvas

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

        # [해결] '입체 구조' 버튼은 'Theory' 모드에서만 나타남
        if hasattr(self, 'btn_3d'):
            if mode == "Theory":
                self.btn_3d.show()
                self.btn_3d.raise_() # 버튼이 다른 레이어에 가려지지 않게 함
                # [Phase 6-3] 분자가 이미 선택되어 있으면 활성, 아니면 비활성
                has_selection = hasattr(self.cv, 'selected_molecule_keys') and bool(self.cv.selected_molecule_keys)
                self.btn_3d.setEnabled(has_selection)
                if not has_selection:
                    self.btn_3d.setToolTip("먼저 분자를 선택하세요")
                # [명령 2] Theory→3D 자동 오픈 제거: on_theory_layer_interaction() 호출 삭제
                # 3D 팝업은 오직 btn_3d 클릭으로만 열림
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

        if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
            self.btn_3d.raise_()
        self.cv.update()

    # [Phase 6-3] 분자 선택 변경 핸들러
    def _on_molecule_selection_changed(self, selected: bool):
        """분자 선택/해제 시 btn_3d 활성화 상태 변경"""
        if hasattr(self, 'btn_3d'):
            self.btn_3d.setEnabled(selected)
            if selected:
                self.btn_3d.setToolTip("선택된 분자의 3D 구조 보기")
            else:
                self.btn_3d.setToolTip("먼저 분자를 선택하세요")

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

        super().resizeEvent(event)

    def clear_all(self):
        if QMessageBox.question(self, "확인", "전체 캔버스를 지우시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.cv.save_state(); self.cv.atoms = {}; self.cv.bonds = {}; self.cv.strokes = []; self.cv.update()

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG 저장", "", "PNG Files (*.png)")
        if path: self.cv.grab().save(path)
            
    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "PDF 저장", "", "PDF Files (*.pdf)")
        if path:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution); printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat); printer.setOutputFileName(path)
            painter = QPainter(printer); target_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            widget_rect = self.cv.rect(); scale = min(target_rect.width()/widget_rect.width(), target_rect.height()/widget_rect.height()) * 0.95
            painter.scale(scale, scale); self.cv.render(painter); painter.end()

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

                save_data = {
                    "atoms": {f"{k[0]},{k[1]}": v for k, v in self.cv.atoms.items()},
                    "bonds": s_bonds
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
            # [명령 1] Pen이 tb2로 이동했으므로 양쪽 툴바 탐색
            widget = self.tb2.widgetForAction(action) if hasattr(self, 'tb2') else None
            if not widget:
                widget = self.tb.widgetForAction(action)
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
        """선택된 분자의 3D 구조 팝업 열기"""
        if not PHASE_C_AVAILABLE:
            QMessageBox.warning(self, "알림", "3D 뷰어 모듈을 사용할 수 없습니다.\nPyOpenGL을 설치해주세요.")
            return
        
        # [Phase 6-3] 선택된 분자 원자 키 가져오기
        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())
        if not selected_keys:
            QMessageBox.warning(self, "알림", "먼저 분자를 선택하세요.\nTheory 레이어에서 분자를 클릭하세요.")
            return
        
        # 선택된 분자의 atoms/bonds만 필터링
        sel_atoms = {k: v for k, v in self.cv.atoms.items() if k in selected_keys}
        sel_bonds = {}
        for (k1, k2), v in self.cv.bonds.items():
            if k1 in selected_keys and k2 in selected_keys:
                sel_bonds[(k1, k2)] = v
        
        try:
            theory_data = self.cv.analysis_results.get("theory_data", {}) if self.cv.analysis_results else {}
            mol_data = Molecule3DData(
                atoms=sel_atoms,
                bonds=sel_bonds,
                theory_data=theory_data
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
        """스펙트럼을 PDF로 내보내기"""
        if not SPECTRUM_PDF_EXPORTER_AVAILABLE:
            QMessageBox.warning(self, "알림", "스펙트럼 PDF 내보내기 모듈을 사용할 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            metadata = SpectrumMetadata(
                molecule_name="Calculated Molecule",
                molecular_formula="C?H?",
                calculation_method="B3LYP/6-31G(d)",
                final_energy=-100.0
            )
            
            spectra_data = {}
            
            try:
                spectrum_data = parse_orca_frequencies(Path(file_path))
                if spectrum_data and len(spectrum_data.modes) > 0:
                    spectra_data["IR/Raman"] = SpectrumData(
                        spectrum_type="IR/Raman",
                        peaks=[],
                        raw_data={"modes": spectrum_data.modes}
                    )
            except:
                pass
            
            if not spectra_data:
                QMessageBox.warning(self, "알림", "스펙트럼 데이터를 찾을 수 없습니다.")
                return
            
            manager = ExportSpectrumManager(self)
            manager.export_spectra(spectra_data, metadata)
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"스펙트럼 PDF 내보내기 실패:\n{str(e)}")
    
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
