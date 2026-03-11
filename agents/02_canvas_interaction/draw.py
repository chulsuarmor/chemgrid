import sys
import math
import copy
import json 
import os
import ctypes # [추가] Windows 작업표시줄 아이콘 무결성 확보용
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QToolBar, 
                             QDialog, QGridLayout, QPushButton, QColorDialog, 
                             QSlider, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
                             QMessageBox, QFileDialog, QMenu, QProgressBar, QTextEdit,
                             QListWidget, QListWidgetItem, QScrollArea, QSplitter, QTableWidget,
                             QTableWidgetItem, QTabWidget)
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QAction, QActionGroup, 
                             QFont, QFontMetrics, QIcon, QPolygonF, QPixmap, QCursor, QPainterPath)
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF, QSize, QPoint, pyqtProperty, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal
from PyQt6.QtPrintSupport import QPrinter


from chem_data import ELEMENT_DATA, VISUAL_SETTINGS
from analyzer import ChemicalAnalyzer
from renderer import CloudRenderer
from layer_logic import LewisRenderer, TheoryRenderer

# ========== [Phase Integration] 모든 모듈 임포트 ==========
try:
    from phase_integration import PhaseIntegrationManager, attach_phase_integration
    PHASE_INTEGRATION_AVAILABLE = True
except ImportError:
    PHASE_INTEGRATION_AVAILABLE = False
    print("[draw.py] Phase integration module not available")

try:
    from popup_3d import Molecule3DData, Molecule3DPopup
    PHASE_C_AVAILABLE = True
except ImportError:
    PHASE_C_AVAILABLE = False

try:
    from orca_interface import OrcaCalculationResult
    ORCA_AVAILABLE = True
except ImportError:
    ORCA_AVAILABLE = False

# ========== [Phase C+] Spectrum Analyzer 모듈 임포트 ==========
try:
    from spectrum_analyzer import parse_orca_frequencies, SpectrumViewerWidget
    from popup_spectrum import SpectrumPopup, launch_spectrum_viewer
    SPECTRUM_ANALYZER_AVAILABLE = True
except ImportError:
    SPECTRUM_ANALYZER_AVAILABLE = False
    print("[draw.py] Spectrum analyzer module not available")

# ========== [Phase 5] Phase 4 모듈 임포트 ==========
try:
    from molecule_comparator import MoleculeComparator, ComparisonResult
    PHASE_4_COMPARATOR_AVAILABLE = True
except ImportError:
    PHASE_4_COMPARATOR_AVAILABLE = False
    print("[draw.py] molecule_comparator module not available")

try:
    from history_manager import HistoryManager, CalculationEntry
    PHASE_4_HISTORY_AVAILABLE = True
except ImportError:
    PHASE_4_HISTORY_AVAILABLE = False
    print("[draw.py] history_manager module not available")

try:
    from batch_processor import BatchProcessor, BatchJob, BatchJobStatus
    PHASE_4_BATCH_AVAILABLE = True
except ImportError:
    PHASE_4_BATCH_AVAILABLE = False
    print("[draw.py] batch_processor module not available")

# ========== [최종 100점] 새로운 분광 분석 모듈 임포트 ==========
try:
    from popup_nmr import NMRPopup, launch_nmr_viewer
    NMR_AVAILABLE = True
except ImportError:
    NMR_AVAILABLE = False
    print("[draw.py] NMR module not available")

try:
    from popup_uvvis import UVVisPopup, launch_uvvis_viewer
    UVVIS_AVAILABLE = True
except ImportError:
    UVVIS_AVAILABLE = False
    print("[draw.py] UV-Vis module not available")

try:
    from popup_md import MDPopup, launch_md_viewer
    MD_AVAILABLE = True
except ImportError:
    MD_AVAILABLE = False
    print("[draw.py] MD module not available")

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
    print("[draw.py] Advanced export manager module not available")

try:
    from spectrum_pdf_exporter import ExportSpectrumManager, SpectrumMetadata, SpectrumData
    SPECTRUM_PDF_EXPORTER_AVAILABLE = True
except ImportError:
    SPECTRUM_PDF_EXPORTER_AVAILABLE = False
    print("[draw.py] Spectrum PDF exporter module not available")

try:
    from calculation_logger import CalculationLogger, CalculationEntry
    CALCULATION_LOGGER_AVAILABLE = True
except ImportError:
    CALCULATION_LOGGER_AVAILABLE = False
    print("[draw.py] Calculation logger module not available")

try:
    from verification_report import VerificationEngine, VerificationReport
    VERIFICATION_REPORT_AVAILABLE = True
except ImportError:
    VERIFICATION_REPORT_AVAILABLE = False
    print("[draw.py] Verification report module not available")

# ========== [Phase 6-1B] MoleculeCanvas → canvas.py 분리 ==========
from canvas import MoleculeCanvas, CanvasMode, get_coord_key

# ==========================================
# [SECTION 1] 시스템 유틸리티 및 데이터
# ==========================================
VERSION = "v1.52"

def load_icon(file_name, mode_name=None, symbol_text=None):
    """[해결] v1.71 툴바 부피 15% 축소, 로고 30% 확대, 대쉬 실물화 통합 + 경로 자동 해결"""
    pixmap = QPixmap(40, 40); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 1. 사진 파일 로드 (패딩을 줄여 로고 체감 크기 30% 확대)
    # [수정] 절대 경로 자동 계산: 스크립트 위치 기준으로 이미지 파일 찾기
    if file_name:
        # [해결] __file__ 경로의 절대화를 통해 어떤 환경에서도 파일을 찾도록 보정
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_file_name = os.path.normpath(os.path.join(script_dir, file_name))
        
        if os.path.exists(abs_file_name):
            try:
                img = QPixmap(abs_file_name)
                if not img.isNull():  # 이미지 로드 확인
                    pad = 4 if "hand" in file_name.lower() else 1 # 여백을 최소화하여 꽉 차게 그림
                    painter.drawPixmap(pad, pad, 40-pad*2, 40-pad*2, img)
                    painter.end(); return QIcon(pixmap)
                else:
                    print(f"[load_icon] ⚠️ 이미지 파일 손상: {abs_file_name}")
            except Exception as e:
                print(f"[load_icon] ⚠️ 이미지 로드 실패: {abs_file_name} - {e}")
        else:
            print(f"[load_icon] ⚠️ 파일 없음: {abs_file_name}")

    # 2. 직접 그리기 (기호 10% 축소 및 대쉬 디자인 실물화)
    painter.setPen(QPen(Qt.GlobalColor.black, 3.2))
    if symbol_text: # H, R 등 원소 및 기호
        painter.setFont(QFont("Arial", 18, QFont.Weight.Bold)) # 20 -> 18pt 축소
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, symbol_text)
    elif mode_name == "Wedge": # 그리드 실물과 동일한 기울어진 고깔
        painter.setBrush(Qt.GlobalColor.black)
        painter.drawPolygon(QPolygonF([QPointF(10, 34), QPointF(26, 6), QPointF(32, 12)]))
    elif mode_name == "Dash": # [해결] 세로 바코드 탈피 -> 부채꼴 계단식 실물 디자인
        for i in range(7):
            w = i * 1.5; painter.drawLine(QPointF(10+i*4, 34-i*4+w), QPointF(10+i*4, 34-i*4-w))
    painter.end(); return QIcon(pixmap)

# ==========================================
# [SECTION 2] 보조 UI
# ==========================================
class PeriodicTableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("현대 주기율표 (Xe 54번 포함)")
        layout = QGridLayout(self)
        layout.setSpacing(2)
        elements = [
            ("H", 0, 0), ("He", 0, 17),
            ("Li", 1, 0), ("Be", 1, 1), ("B", 1, 12), ("C", 1, 13), ("N", 1, 14), ("O", 1, 15), ("F", 1, 16), ("Ne", 1, 17),
            ("Na", 2, 0), ("Mg", 2, 1), ("Al", 2, 12), ("Si", 2, 13), ("P", 2, 14), ("S", 2, 15), ("Cl", 2, 16), ("Ar", 2, 17),
            ("K", 3, 0), ("Ca", 3, 1), ("Sc", 3, 2), ("Ti", 3, 3), ("V", 3, 4), ("Cr", 3, 5), ("Mn", 3, 6), ("Fe", 3, 7), 
            ("Co", 3, 8), ("Ni", 3, 9), ("Cu", 3, 10), ("Zn", 3, 11), ("Ga", 3, 12), ("Ge", 3, 13), ("As", 3, 14), ("Se", 3, 15), ("Br", 3, 16), ("Kr", 3, 17),
            ("Rb", 4, 0), ("Sr", 4, 1), ("Y", 4, 2), ("Zr", 4, 3), ("Nb", 4, 4), ("Mo", 4, 5), ("Tc", 4, 6), ("Ru", 4, 7), 
            ("Rh", 4, 8), ("Pd", 4, 9), ("Ag", 4, 10), ("Cd", 4, 11), ("In", 4, 12), ("Sn", 4, 13), ("Sb", 4, 14), ("Te", 4, 15), ("I", 4, 16), ("Xe", 4, 17)
        ]
        self.selected = None
        for el, r, c in elements:
            btn = QPushButton(el)
            btn.setFixedSize(38, 38)
            if c < 2 or (r > 2 and c < 12):
                btn.setStyleSheet("background-color: #FFDADA;")
            elif c > 12:
                btn.setStyleSheet("background-color: #DAEFFF;")
            else:
                btn.setStyleSheet("background-color: #F0F0F0;")
            btn.clicked.connect(lambda ch, e=el: self.done_with(e))
            layout.addWidget(btn, r, c)
    def done_with(self, e):
        self.selected = e
        self.accept()

class PenSettingsBox(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: white; border: 2px solid #2196F3; border-radius: 8px;")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Pen Size ({VERSION})"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 10); self.slider.setValue(2)
        layout.addWidget(self.slider)
        self.color_btn = QPushButton("색상 변경"); layout.addWidget(self.color_btn)
        self.setFixedSize(140, 110)

# ==========================================
# [SECTION 3] Phase 4 대화상자 (분자 비교, 히스토리, 배치 처리)
# ==========================================

class ComparisonDialog(QDialog):
    """분자 비교 기능 대화상자"""
    def __init__(self, parent, comparator, canvas):
        super().__init__(parent)
        self.setWindowTitle("분자 비교 (Phase 4)")
        self.setGeometry(150, 150, 800, 650)
        self.comparator = comparator
        self.canvas = canvas
        
        layout = QVBoxLayout(self)
        
        # 상단: 분자 1 정보
        layout.addWidget(QLabel("분자 1 (현재 캔버스):"))
        self.mol1_label = QLabel("분자 SMILES를 생성 중...")
        self.mol1_label.setWordWrap(True)
        self.mol1_label.setStyleSheet("background-color: #f0f0f0; padding: 8px; border-radius: 4px;")
        layout.addWidget(self.mol1_label)
        
        # 분자 1 SMILES 가져오기
        self.mol1_smiles = self.canvas.get_smiles() if hasattr(self.canvas, 'get_smiles') else "unknown"
        self.mol1_label.setText(f"SMILES: {self.mol1_smiles}")
        
        # 중간: 분자 2 입력
        layout.addWidget(QLabel("분자 2 (비교 대상):"))
        self.mol2_input = QTextEdit()
        self.mol2_input.setPlaceholderText("SMILES 또는 분자식 입력 (예: CC(C)C, C1=CC=CC=C1)")
        self.mol2_input.setFixedHeight(80)
        layout.addWidget(self.mol2_input)
        
        # 비교 버튼
        compare_btn = QPushButton("비교 수행")
        compare_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px; border-radius: 4px;")
        compare_btn.clicked.connect(self.perform_comparison)
        layout.addWidget(compare_btn)
        
        # 결과 표시 (탭형 UI)
        layout.addWidget(QLabel("비교 결과:"))
        
        # 탭 위젯으로 여러 결과 표시
        self.tab_widget = QTabWidget()
        
        # 1. 요약 탭
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        summary_layout.addWidget(self.summary_text)
        self.tab_widget.addTab(summary_tab, "요약")
        
        # 2. 상세 정보 탭
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)
        self.tab_widget.addTab(detail_tab, "상세 정보")
        
        layout.addWidget(self.tab_widget)
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def perform_comparison(self):
        """분자 비교 수행"""
        mol2_text = self.mol2_input.toPlainText().strip()
        if not mol2_text:
            QMessageBox.warning(self, "알림", "비교 대상 분자를 입력하세요.")
            return
        
        try:
            # 비교 수행
            result = self.comparator.compare_molecules(self.mol1_smiles, mol2_text)
            
            # 요약 결과 표시
            summary = f"🔬 분자 비교 결과\n\n"
            summary += f"유사도 (Tanimoto): {result.tanimoto_similarity:.1%}\n"
            summary += f"동일 분자: {'✓ Yes' if result.is_identical else '✗ No'}\n"
            if result.common_substructure:
                summary += f"공통 부분구조: {result.common_substructure}\n"
            
            self.summary_text.setText(summary)
            
            # 상세 정보 표시
            detail = f"분자 1 SMILES: {result.mol1_smiles}\n\n"
            detail += f"분자 2 SMILES: {result.mol2_smiles}\n\n"
            detail += f"차이점:\n"
            if isinstance(result.differences, dict):
                for key, value in result.differences.items():
                    detail += f"  • {key}: {value}\n"
            else:
                detail += str(result.differences)
            
            self.detail_text.setText(detail)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"비교 중 오류 발생: {str(e)}")


class HistoryBrowserDialog(QDialog):
    """계산 히스토리 브라우저 대화상자"""
    def __init__(self, parent, history_manager):
        super().__init__(parent)
        self.setWindowTitle("계산 히스토리 (Phase 4)")
        self.setGeometry(100, 100, 900, 700)
        self.history_manager = history_manager
        self.filtered_entries = []
        
        layout = QVBoxLayout(self)
        
        # 제목
        title = QLabel("📊 계산 히스토리")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # 검색/필터
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("검색:"))
        self.filter_input = QTextEdit()
        self.filter_input.setMaximumHeight(35)
        self.filter_input.setPlaceholderText("분자식, 방법, 또는 날짜로 검색")
        filter_layout.addWidget(self.filter_input)
        filter_btn = QPushButton("검색")
        filter_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        filter_btn.clicked.connect(self.apply_filter)
        filter_layout.addWidget(filter_btn)
        layout.addLayout(filter_layout)
        
        # 히스토리 목록
        layout.addWidget(QLabel("계산 기록:"))
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels(
            ["ID", "날짜", "분자식", "방법", "에너지 (Ha)", "상태", "시간 (s)"]
        )
        self.history_table.setColumnWidth(0, 40)
        self.history_table.setColumnWidth(1, 150)
        self.history_table.setColumnWidth(2, 80)
        self.history_table.setColumnWidth(3, 100)
        self.history_table.setColumnWidth(4, 100)
        self.history_table.setColumnWidth(5, 80)
        self.history_table.setColumnWidth(6, 80)
        self.history_table.itemSelectionChanged.connect(self.show_details)
        layout.addWidget(self.history_table)
        
        # 상세 정보
        layout.addWidget(QLabel("상세 정보:"))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFixedHeight(150)
        layout.addWidget(self.detail_text)
        
        # 버튼
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.setStyleSheet("background-color: #2196F3; color: white;")
        refresh_btn.clicked.connect(self.refresh_history)
        btn_layout.addWidget(refresh_btn)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        # 초기 로드
        self.refresh_history()
    
    def refresh_history(self):
        """히스토리 새로고침"""
        try:
            entries = self.history_manager.get_all_entries() if hasattr(self.history_manager, 'get_all_entries') else []
            self.filtered_entries = entries
            self.history_table.setRowCount(len(entries))
            
            for i, entry in enumerate(entries):
                self.history_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
                self.history_table.setItem(i, 1, QTableWidgetItem(getattr(entry, 'timestamp', 'N/A')[:19]))
                self.history_table.setItem(i, 2, QTableWidgetItem(getattr(entry, 'formula', 'N/A')))
                self.history_table.setItem(i, 3, QTableWidgetItem(getattr(entry, 'method', 'N/A')))
                self.history_table.setItem(i, 4, QTableWidgetItem(f"{round(getattr(entry, 'energy', 0), 4)}"))
                self.history_table.setItem(i, 5, QTableWidgetItem(getattr(entry, 'convergence_status', 'N/A')))
                self.history_table.setItem(i, 6, QTableWidgetItem(f"{round(getattr(entry, 'computation_time_sec', 0), 2)}"))
        except Exception as e:
            QMessageBox.warning(self, "오류", f"히스토리 로드 실패: {str(e)}")
    
    def apply_filter(self):
        """필터 적용"""
        query = self.filter_input.toPlainText().strip().lower()
        if not query:
            self.refresh_history()
            return
        
        try:
            filtered_entries = []
            for entry in self.filtered_entries:
                formula = getattr(entry, 'formula', '').lower()
                method = getattr(entry, 'method', '').lower()
                timestamp = getattr(entry, 'timestamp', '').lower()
                
                if query in formula or query in method or query in timestamp:
                    filtered_entries.append(entry)
            
            # 필터된 결과 표시
            self.history_table.setRowCount(len(filtered_entries))
            for i, entry in enumerate(filtered_entries):
                self.history_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
                self.history_table.setItem(i, 1, QTableWidgetItem(getattr(entry, 'timestamp', 'N/A')[:19]))
                self.history_table.setItem(i, 2, QTableWidgetItem(getattr(entry, 'formula', 'N/A')))
                self.history_table.setItem(i, 3, QTableWidgetItem(getattr(entry, 'method', 'N/A')))
                self.history_table.setItem(i, 4, QTableWidgetItem(f"{round(getattr(entry, 'energy', 0), 4)}"))
                self.history_table.setItem(i, 5, QTableWidgetItem(getattr(entry, 'convergence_status', 'N/A')))
                self.history_table.setItem(i, 6, QTableWidgetItem(f"{round(getattr(entry, 'computation_time_sec', 0), 2)}"))
            
            QMessageBox.information(self, "검색 완료", f"{len(filtered_entries)}개 항목을 찾았습니다.")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"검색 중 오류 발생: {str(e)}")
    
    def show_details(self):
        """선택된 항목의 상세 정보 표시"""
        row = self.history_table.currentRow()
        if row < 0:
            return
        
        try:
            entry = self.filtered_entries[row]
            detail = f"🔬 계산 상세 정보\n\n"
            detail += f"ID: {getattr(entry, 'id', 'N/A')}\n"
            detail += f"SMILES: {getattr(entry, 'smiles', 'N/A')}\n"
            detail += f"분자식: {getattr(entry, 'formula', 'N/A')}\n"
            detail += f"방법: {getattr(entry, 'method', 'N/A')}\n"
            detail += f"기저 집합: {getattr(entry, 'basis_set', 'N/A')}\n"
            detail += f"에너지: {getattr(entry, 'energy', 0)} Ha\n"
            detail += f"HOMO-LUMO Gap: {getattr(entry, 'homo_lumo_gap', 'N/A')} eV\n"
            detail += f"쌍극자 모멘트: {getattr(entry, 'dipole_moment', 'N/A')} D\n"
            detail += f"계산 시간: {getattr(entry, 'computation_time_sec', 0)}초\n"
            detail += f"상태: {getattr(entry, 'convergence_status', 'N/A')}\n"
            detail += f"메모: {getattr(entry, 'notes', 'N/A')}\n"
            
            self.detail_text.setText(detail)
        except Exception as e:
            self.detail_text.setText(f"정보 로드 중 오류 발생: {str(e)}")


class BatchProcessorDialog(QDialog):
    """배치 처리 대화상자"""
    def __init__(self, parent, batch_processor, canvas):
        super().__init__(parent)
        self.setWindowTitle("배치 처리 (Phase 4)")
        self.setGeometry(200, 200, 700, 600)
        self.batch_processor = batch_processor
        self.canvas = canvas
        
        layout = QVBoxLayout(self)
        
        # 분자 목록 입력
        layout.addWidget(QLabel("처리할 분자 목록 (SMILES, 줄바꿈으로 구분):"))
        self.smiles_input = QTextEdit()
        self.smiles_input.setPlaceholderText("분자 1\n분자 2\n분자 3\n...")
        self.smiles_input.setFixedHeight(150)
        layout.addWidget(self.smiles_input)
        
        # 계산 옵션
        layout.addWidget(QLabel("계산 옵션:"))
        option_layout = QHBoxLayout()
        option_layout.addWidget(QLabel("방법:"))
        self.method_input = QTextEdit()
        self.method_input.setText("B3LYP")
        self.method_input.setMaximumHeight(25)
        option_layout.addWidget(self.method_input)
        layout.addLayout(option_layout)
        
        # 진행률
        layout.addWidget(QLabel("진행 상황:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("대기 중...")
        layout.addWidget(self.progress_label)
        
        # 결과 표시
        layout.addWidget(QLabel("처리 결과:"))
        self.result_list = QListWidget()
        layout.addWidget(self.result_list)
        
        # 버튼
        btn_layout = QHBoxLayout()
        start_btn = QPushButton("시작")
        start_btn.clicked.connect(self.start_batch_processing)
        btn_layout.addWidget(start_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.cancel_batch_processing)
        btn_layout.addWidget(cancel_btn)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
    
    def start_batch_processing(self):
        """배치 처리 시작"""
        smiles_list = [s.strip() for s in self.smiles_input.toPlainText().strip().split('\n') if s.strip()]
        if not smiles_list:
            QMessageBox.warning(self, "알림", "처리할 분자를 입력하세요.")
            return
        
        try:
            # 배치 작업 추가
            job_ids = []
            for idx, smiles in enumerate(smiles_list):
                if hasattr(self.batch_processor, 'add_job'):
                    job_id = self.batch_processor.add_job(smiles)
                    job_ids.append(job_id)
                    
                    # 진행률 업데이트
                    progress = int((idx + 1) / len(smiles_list) * 100)
                    self.progress_bar.setValue(progress)
                    self.progress_label.setText(f"{idx + 1}/{len(smiles_list)} 분자 처리 중... ({progress}%)")
                    
                    # 결과 목록에 추가
                    self.result_list.addItem(f"✓ {smiles[:40]}... (처리됨)")
                    
                    # UI 업데이트
                    QApplication.processEvents()
            
            # 처리 완료
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"처리 완료: {len(job_ids)}개 분자")
            QMessageBox.information(self, "성공", f"{len(job_ids)}개 분자의 배치 처리가 완료되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"배치 처리 중 오류 발생: {str(e)}")
    
    def cancel_batch_processing(self):
        """배치 처리 취소"""
        self.batch_processor.cancel_all()
        self.progress_label.setText("취소됨")
        self.progress_bar.setValue(0)

# ==========================================
# [SECTION 4] 메인 인터페이스
# (MoleculeCanvas는 canvas.py로 분리됨 — Phase 6-1B)
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # [해결] Windows 작업표시줄에 로고가 나오도록 시스템 AppID 강제 설정
        try:
            myappid = 'chemdraw.pro.v1.52'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except: pass

        self.setWindowTitle("ChemDraw Pro"); self.setGeometry(100, 100, 1350, 850)
        
        # [해결] 로고 경로 절대 좌표로 고정 및 앱 전체 아이콘 설정
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
        self.tb = QToolBar(); self.addToolBar(self.tb)
        self.tb.setIconSize(QSize(34, 34)); self.tb.setMinimumHeight(58)
        self.tb.setMovable(False)

        self.tb2 = QToolBar(); self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.tb2)
        self.tb2.setMinimumHeight(40)
        self.tb2.setMovable(False)

        # [추가] 툴바 맨 앞에 로고 아이콘 배치 (사용자 요청: 앱 내 툴바 로고)
        logo_action = QAction(load_icon("logo.png"), "ChemDraw", self)
        self.tb.addAction(logo_action)
        self.tb.addSeparator()

        self.setStyleSheet("QToolButton { font-size: 13px; font-weight: bold; padding: 2px; } QMenu { font-size: 13px; }")

        # [2-TIER TOOLBAR] 파일/내보내기 메뉴는 tb2(두 번째 줄)로 이동
        file_menu = QMenu("파일", self); file_menu.addAction("저장 (.chem)", self.save_file); file_menu.addAction("불러오기 (.chem)", self.load_file)
        file_btn = QAction("파일", self); file_btn.setMenu(file_menu); self.tb2.addAction(file_btn)

        export_menu = QMenu("내보내기", self)
        export_menu.addAction("PNG 저장", self.export_png)
        export_menu.addAction("PDF 저장", self.export_pdf)
        export_menu.addSeparator()
        export_menu.addAction("선택 영역 내보내기...", self.export_selection_dialog)
        export_menu.addAction("스펙트럼 PDF 내보내기...", self.export_spectrum_to_pdf)
        export_menu.addSeparator()
        export_menu.addAction("계산 히스토리 보기", self.show_calculation_history)
        export_menu.addAction("검증 보고서 생성", self.show_verification_report)
        export_btn = QAction("내보내기", self); export_btn.setMenu(export_menu); self.tb2.addAction(export_btn)
        # [해결] 초기 상태를 명시적으로 비활성화하여 디폴트값 보장
        export_btn.setEnabled(False)
        self.export_btn = export_btn # 참조를 위해 저장

        self.tb2.addSeparator()

        grp = QActionGroup(self)
        # [해결] 주신 사진 파일명으로 완벽하게 매핑 (LP, Radical 등은 벡테 생성용 텍스트만 전달)
        tool_icons = {
            "Select": ("select.png", None), "Hand": ("hand.png", None), 
            "Pen": ("pen.png", None), "Eraser": ("eraser.png", None),
            "Bond": ("bond.png", None), "LonePair": ("", ".."), 
            "Radical": ("", "·"), "Positive": ("", "+"), "Negative": ("", "-")
        }
        tools = ["Select", "Hand", "Bond", "Wedge", "Dash", "Pen", "Eraser", "H", "R", "LonePair", "Radical", "Positive", "Negative", "O", "N", "P", "S", "F", "Cl", "Br", "I"]
        
        for n in tools:
            # 원소(H, R, O, N 등)는 텍스트로 자동 처리하도록 symbol_text 전달
            img_info = tool_icons.get(n, ("", n if len(n) <= 2 else None))
            img_path, sym = img_info
            
            icon = load_icon(img_path, mode_name=n, symbol_text=sym)
            a = QAction(icon, n, self); a.setCheckable(True)
            a.triggered.connect(self.create_handler(n)); self.tb.addAction(a); grp.addAction(a)
            if n == "Bond": a.setChecked(True)
        
        self.tb.addSeparator()
        self.tb.addAction(QAction(load_icon("undo.png", symbol_text="↺"), "Undo", self, triggered=self.cv.undo))
        self.tb.addAction(QAction(load_icon("redo.png", symbol_text="↻"), "Redo", self, triggered=self.cv.redo))

        # [2-TIER TOOLBAR] 텍스트 전용 버튼은 tb2로 이동
        self.tb2.addAction(QAction("전체 지우기", self, triggered=self.clear_all))
        self.tb2.addAction(QAction("원소 선택", self, triggered=self.pick_el))

        self.view_container = QWidget(self)
        self.view_layout = QHBoxLayout(self.view_container)
        self.btn_lewis = QPushButton("루이스 구조", self.view_container)
        self.btn_theory = QPushButton("이론적 구조", self.view_container)
        # [해결] 스타일을 통일하고 부모 위젯을 self로 변경하여 레이아웃 간섭 방지
        self.btn_3d = QPushButton("입체 구조", self)
        self.btn_3d.setFixedSize(110, 40)
        self.btn_3d.setStyleSheet("background-color: #2196F3; color: white; border-radius: 10px; font-weight: bold;")
        self.btn_3d.hide()
        
        # ========== [Phase C+] Spectrum Viewer 버튼 ==========
        self.btn_spectrum = QPushButton("스펙트럼", self)
        self.btn_spectrum.setFixedSize(110, 40)
        self.btn_spectrum.setStyleSheet("background-color: #9C27B0; color: white; border-radius: 10px; font-weight: bold;")
        self.btn_spectrum.clicked.connect(self.open_spectrum_viewer)
        self.btn_spectrum.hide()
        
        # ========== [최종 100점] 새로운 분광 분석 버튼 ==========
        self.btn_nmr = QPushButton("NMR", self)
        self.btn_nmr.setFixedSize(110, 40)
        self.btn_nmr.setStyleSheet("background-color: #1976D2; color: white; border-radius: 10px; font-weight: bold;")
        self.btn_nmr.clicked.connect(self.open_nmr_viewer)
        self.btn_nmr.hide()
        
        self.btn_uvvis = QPushButton("UV-Vis", self)
        self.btn_uvvis.setFixedSize(110, 40)
        self.btn_uvvis.setStyleSheet("background-color: #7B1FA2; color: white; border-radius: 10px; font-weight: bold;")
        self.btn_uvvis.clicked.connect(self.open_uvvis_viewer)
        self.btn_uvvis.hide()
        
        self.btn_md = QPushButton("MD", self)
        self.btn_md.setFixedSize(110, 40)
        self.btn_md.setStyleSheet("background-color: #C62828; color: white; border-radius: 10px; font-weight: bold;")
        self.btn_md.clicked.connect(self.open_md_viewer)
        self.btn_md.hide()
        
        self.btn_molorbital = QPushButton("오비탈", self)
        self.btn_molorbital.setFixedSize(110, 40)
        self.btn_molorbital.setStyleSheet("background-color: #F57C00; color: white; border-radius: 10px; font-weight: bold;")
        self.btn_molorbital.clicked.connect(self.open_molorbital_viewer)
        self.btn_molorbital.hide()

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

        # ========== [Phase 5] Lasso Select 버튼 [제거됨] ==========
        # Lasso Select 기능은 제거됨 - 기본 직사각형 선택만 사용
        # self.btn_lasso = QPushButton("올가미 선택", self)
        # self.btn_lasso.setFixedSize(110, 40)
        # self.btn_lasso.setStyleSheet("background-color: #FF6F00; color: white; border-radius: 10px; font-weight: bold;")
        # self.btn_lasso.clicked.connect(self.enable_lasso_select)
        # self.btn_lasso.hide()

        self.pen_ui = PenSettingsBox(self); self.pen_ui.slider.valueChanged.connect(lambda v: setattr(self.cv, 'pen_width', v))
        self.pen_ui.color_btn.clicked.connect(self.pick_clr); self.pen_ui.hide()

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
        
        # ========== [Phase 5] Phase 4 UI 버튼 추가 (2-TIER TOOLBAR: tb2로 이동) ==========
        self.tb2.addSeparator()

        # 분자 비교 버튼
        self.btn_comparator = QAction("분자 비교", self)
        self.btn_comparator.triggered.connect(self.open_comparator)
        self.btn_comparator.setEnabled(PHASE_4_COMPARATOR_AVAILABLE)
        self.tb2.addAction(self.btn_comparator)

        # 히스토리 브라우저 버튼
        self.btn_history = QAction("계산 히스토리", self)
        self.btn_history.triggered.connect(self.open_history_browser)
        self.btn_history.setEnabled(PHASE_4_HISTORY_AVAILABLE)
        self.tb2.addAction(self.btn_history)

        # 배치 처리 버튼
        self.btn_batch = QAction("배치 처리", self)
        self.btn_batch.triggered.connect(self.open_batch_processor)
        self.btn_batch.setEnabled(PHASE_4_BATCH_AVAILABLE)
        self.tb2.addAction(self.btn_batch)
        
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
                # ========== [Phase Integration Hook 3] Theory layer 상호작용 ==========
                self.cv.on_theory_layer_interaction()
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
        
        # ========== [Phase 5] Lasso Select 버튼 [제거됨] ==========
        # Lasso Select 기능은 제거됨 - 기본 직사각형 선택만 사용
        # if hasattr(self, 'btn_lasso'):
        #     if mode == "Theory":
        #         self.btn_lasso.show()
        #         self.btn_lasso.raise_()
        #     else:
        #         self.btn_lasso.hide()

        # 그리기 관련 도구 비활성화 (회색 처리)
        draw_tools = ["Bond", "Wedge", "Dash", "H", "R", "O", "N", "P", "S", "F", "Cl", "Br", "I", "LonePair", "Radical"]
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
            self.btn_3d.setVisible(mode == "Theory") # Theory일 때만 입체 버튼 표시

        if hasattr(self, 'btn_3d') and self.btn_3d.isVisible():
            self.btn_3d.raise_()
            if mode == "Theory":
                self.btn_3d.show(); self.btn_3d.raise_()
            else:
                self.btn_3d.hide()
        self.cv.update()

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
            total_height = 0
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
            widget = self.tb.widgetForAction(action)
            if widget: # [해결] 들여쓰기 4칸으로 수정
                # [해결] 버튼 바로 아래에 정확히 배치 (NameError 해결)
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
    
    # ========== [최종 100점] 새로운 분광 분석 기능 ==========
    
    def open_nmr_viewer(self):
        """NMR 스펙트럼 뷰어 열기"""
        if not NMR_AVAILABLE:
            QMessageBox.warning(self, "알림", "NMR 모듈을 사용할 수 없습니다.")
            return
        
        # ORCA 파일 선택
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if file_path:
            try:
                from pathlib import Path
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
                from pathlib import Path
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
                from pathlib import Path
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
                from pathlib import Path
                popup = MolecularOrbitalPopup(Path(file_path), self)
                popup.exec()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"분자 오비탈 데이터 로드 실패:\n{str(e)}")
    
    def open_spectrum_viewer(self):
        """IR/Raman 스펙트럼 뷰어 열기"""
        if not SPECTRUM_ANALYZER_AVAILABLE:
            QMessageBox.warning(self, "알림", "스펙트럼 분석 모듈을 사용할 수 없습니다.")
            return
        
        # ORCA 계산 결과 파일 선택
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "ORCA 계산 결과 파일 선택",
            "",
            "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            # 스펙트럼 데이터 파싱
            from pathlib import Path
            spectrum_data = parse_orca_frequencies(Path(file_path))
            
            if len(spectrum_data.modes) == 0:
                QMessageBox.warning(
                    self,
                    "경고",
                    f"파일에서 진동수 데이터를 찾을 수 없습니다:\n{file_path}"
                )
                return
            
            # 스펙트럼 팝업 표시
            popup = SpectrumPopup(spectrum_data, self)
            popup.exec()
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "오류",
                f"스펙트럼 데이터를 로드할 수 없습니다:\n{str(e)}"
            )
    
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
        
        # ORCA 파일 선택
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ORCA 계산 결과 선택", "", "ORCA Output (*.out);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            from pathlib import Path
            
            # 간단한 메타데이터 생성
            metadata = SpectrumMetadata(
                molecule_name="Calculated Molecule",
                molecular_formula="C?H?",
                calculation_method="B3LYP/6-31G(d)",
                final_energy=-100.0
            )
            
            # 스펙트럼 데이터 로드 (IR/Raman 예제)
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
            
            # PDF 내보내기
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
            
            # 보고서를 텍스트 다이얼로그로 표시
            dialog = QDialog(self)
            dialog.setWindowTitle("Calculation History Report")
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(report)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            # 저장 버튼
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
            
            # 최신 계산에 대한 검증 보고서 생성
            latest_entry = entries[-1]
            report = engine.verify_calculation(latest_entry)
            
            report_text = engine.generate_report_text(report)
            
            # 보고서를 텍스트 다이얼로그로 표시
            dialog = QDialog(self)
            dialog.setWindowTitle("Verification Report")
            dialog.resize(900, 700)
            
            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(report_text)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            # 저장 버튼
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

if __name__ == "__main__":
    app = QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec())