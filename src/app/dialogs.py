"""
dialogs.py — ChemGrid 대화상자 모듈
PeriodicTableDialog, PenSettingsBox, ComparisonDialog, HistoryBrowserDialog, BatchProcessorDialog
"""
from PyQt6.QtWidgets import (QDialog, QGridLayout, QPushButton, QSlider,
                             QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QMessageBox, QTextEdit, QListWidget, QProgressBar,
                             QTableWidget, QTableWidgetItem, QTabWidget,
                             QWidget, QApplication)
from PyQt6.QtCore import Qt

from ui_utils import VERSION


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
