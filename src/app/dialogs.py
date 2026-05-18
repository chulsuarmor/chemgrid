"""
dialogs.py — ChemGrid 대화상자 모듈
PeriodicTableDialog, PenSettingsBox, ComparisonDialog, HistoryBrowserDialog, BatchProcessorDialog
"""
import logging

from PyQt6.QtWidgets import (QDialog, QGridLayout, QPushButton, QSlider,
                             QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QMessageBox, QTextEdit, QListWidget, QProgressBar,
                             QTableWidget, QTableWidgetItem, QTabWidget,
                             QWidget, QApplication)
from PyQt6.QtCore import Qt

from ui_utils import VERSION

logger = logging.getLogger(__name__)


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

            # N코드: result 타입 가드 — compare_molecules가 None/비정상 반환 방어
            if result is None:
                logger.warning("compare_molecules returned None for mol1=%s, mol2=%s",
                               self.mol1_smiles, mol2_text)
                QMessageBox.warning(self, "알림", "비교 결과를 생성하지 못했습니다.")
                return

            # 요약 결과 표시
            tanimoto = getattr(result, 'tanimoto_similarity', None)
            if not isinstance(tanimoto, (int, float)):
                logger.warning("tanimoto_similarity not numeric: %s", type(tanimoto).__name__)
                tanimoto = 0.0

            is_identical = getattr(result, 'is_identical', False)
            common_sub = getattr(result, 'common_substructure', '')

            summary = f"분자 비교 결과\n\n"
            summary += f"유사도 (Tanimoto): {tanimoto:.1%}\n"
            summary += f"동일 분자: {'Yes' if is_identical else 'No'}\n"
            if common_sub:
                summary += f"공통 부분구조: {common_sub}\n"

            self.summary_text.setText(summary)

            # 상세 정보 표시
            mol1_smiles = getattr(result, 'mol1_smiles', self.mol1_smiles)
            mol2_smiles = getattr(result, 'mol2_smiles', mol2_text)
            differences = getattr(result, 'differences', {})

            detail = f"분자 1 SMILES: {mol1_smiles}\n\n"
            detail += f"분자 2 SMILES: {mol2_smiles}\n\n"
            detail += f"차이점:\n"
            if isinstance(differences, dict):
                for key, value in differences.items():
                    detail += f"  - {key}: {value}\n"
            elif isinstance(differences, (list, tuple)):
                for item in differences:
                    detail += f"  - {item}\n"
            else:
                detail += str(differences)

            self.detail_text.setText(detail)

        except Exception as e:
            logger.warning("분자 비교 중 오류 발생: %s", e)
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
            # N코드: entries 타입 가드
            if not isinstance(entries, (list, tuple)):
                logger.warning("get_all_entries returned non-list: type=%s", type(entries).__name__)
                entries = []
            self.filtered_entries = list(entries)
            self.history_table.setRowCount(len(self.filtered_entries))

            for i, entry in enumerate(self.filtered_entries):
                ts_raw = getattr(entry, 'timestamp', 'N/A')
                ts_str = str(ts_raw)[:19] if ts_raw is not None else 'N/A'
                formula_raw = getattr(entry, 'formula', 'N/A')
                formula_str = str(formula_raw) if formula_raw is not None else 'N/A'
                method_raw = getattr(entry, 'method', 'N/A')
                method_str = str(method_raw) if method_raw is not None else 'N/A'
                energy_raw = getattr(entry, 'energy', 0)
                try:
                    energy_val = round(float(energy_raw), 4)
                except (TypeError, ValueError):
                    energy_val = 0.0
                status_raw = getattr(entry, 'convergence_status', 'N/A')
                status_str = str(status_raw) if status_raw is not None else 'N/A'
                time_raw = getattr(entry, 'computation_time_sec', 0)
                try:
                    time_val = round(float(time_raw), 2)
                except (TypeError, ValueError):
                    time_val = 0.0

                self.history_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.history_table.setItem(i, 1, QTableWidgetItem(ts_str))
                self.history_table.setItem(i, 2, QTableWidgetItem(formula_str))
                self.history_table.setItem(i, 3, QTableWidgetItem(method_str))
                self.history_table.setItem(i, 4, QTableWidgetItem(str(energy_val)))
                self.history_table.setItem(i, 5, QTableWidgetItem(status_str))
                self.history_table.setItem(i, 6, QTableWidgetItem(str(time_val)))
        except Exception as e:
            logger.warning("히스토리 로드 실패: %s", e)
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
                # N코드: getattr 결과 str 변환 보장
                formula = str(getattr(entry, 'formula', '') or '').lower()
                method = str(getattr(entry, 'method', '') or '').lower()
                timestamp = str(getattr(entry, 'timestamp', '') or '').lower()

                if query in formula or query in method or query in timestamp:
                    filtered_entries.append(entry)

            # 필터된 결과 표시
            self.history_table.setRowCount(len(filtered_entries))
            for i, entry in enumerate(filtered_entries):
                ts_raw = getattr(entry, 'timestamp', 'N/A')
                ts_str = str(ts_raw)[:19] if ts_raw is not None else 'N/A'
                formula_raw = getattr(entry, 'formula', 'N/A')
                formula_str = str(formula_raw) if formula_raw is not None else 'N/A'
                method_raw = getattr(entry, 'method', 'N/A')
                method_str = str(method_raw) if method_raw is not None else 'N/A'
                energy_raw = getattr(entry, 'energy', 0)
                try:
                    energy_val = round(float(energy_raw), 4)
                except (TypeError, ValueError):
                    energy_val = 0.0
                status_raw = getattr(entry, 'convergence_status', 'N/A')
                status_str = str(status_raw) if status_raw is not None else 'N/A'
                time_raw = getattr(entry, 'computation_time_sec', 0)
                try:
                    time_val = round(float(time_raw), 2)
                except (TypeError, ValueError):
                    time_val = 0.0

                self.history_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.history_table.setItem(i, 1, QTableWidgetItem(ts_str))
                self.history_table.setItem(i, 2, QTableWidgetItem(formula_str))
                self.history_table.setItem(i, 3, QTableWidgetItem(method_str))
                self.history_table.setItem(i, 4, QTableWidgetItem(str(energy_val)))
                self.history_table.setItem(i, 5, QTableWidgetItem(status_str))
                self.history_table.setItem(i, 6, QTableWidgetItem(str(time_val)))

            logger.info("히스토리 검색 완료: %d건 일치", len(filtered_entries))
            QMessageBox.information(self, "검색 완료", f"{len(filtered_entries)}개 항목을 찾았습니다.")
        except Exception as e:
            logger.warning("히스토리 검색 중 오류: %s", e)
            QMessageBox.warning(self, "오류", f"검색 중 오류 발생: {str(e)}")
    
    def show_details(self):
        """선택된 항목의 상세 정보 표시"""
        row = self.history_table.currentRow()
        if row < 0:
            return

        # N코드: 인덱스 범위 방어
        if row >= len(self.filtered_entries):
            logger.warning("show_details: row %d out of range (entries=%d)",
                           row, len(self.filtered_entries))
            self.detail_text.setText("선택된 항목의 데이터를 찾을 수 없습니다.")
            return

        try:
            entry = self.filtered_entries[row]

            # N코드: 각 필드를 안전하게 str 변환
            def _safe_str(val, default='N/A'):
                if val is None:
                    return default
                return str(val)

            def _safe_num(val, default=0, precision=4):
                try:
                    return round(float(val), precision)
                except (TypeError, ValueError):
                    return default

            detail = "계산 상세 정보\n\n"
            detail += f"ID: {_safe_str(getattr(entry, 'id', 'N/A'))}\n"
            detail += f"SMILES: {_safe_str(getattr(entry, 'smiles', 'N/A'))}\n"
            detail += f"분자식: {_safe_str(getattr(entry, 'formula', 'N/A'))}\n"
            detail += f"방법: {_safe_str(getattr(entry, 'method', 'N/A'))}\n"
            detail += f"기저 집합: {_safe_str(getattr(entry, 'basis_set', 'N/A'))}\n"
            detail += f"에너지: {_safe_num(getattr(entry, 'energy', 0))} Ha\n"
            detail += f"HOMO-LUMO Gap: {_safe_str(getattr(entry, 'homo_lumo_gap', 'N/A'))} eV\n"
            detail += f"쌍극자 모멘트: {_safe_str(getattr(entry, 'dipole_moment', 'N/A'))} D\n"
            detail += f"계산 시간: {_safe_num(getattr(entry, 'computation_time_sec', 0), precision=2)}초\n"
            detail += f"상태: {_safe_str(getattr(entry, 'convergence_status', 'N/A'))}\n"
            detail += f"메모: {_safe_str(getattr(entry, 'notes', 'N/A'))}\n"

            self.detail_text.setText(detail)
        except Exception as e:
            logger.warning("계산 상세 정보 로드 오류: %s", e)
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
        raw_text = self.smiles_input.toPlainText()
        if not isinstance(raw_text, str):
            logger.warning("smiles_input returned non-str: type=%s", type(raw_text).__name__)
            raw_text = str(raw_text) if raw_text is not None else ''
        smiles_list = [s.strip() for s in raw_text.strip().split('\n') if s.strip()]
        if not smiles_list:
            QMessageBox.warning(self, "알림", "처리할 분자를 입력하세요.")
            return

        try:
            # 배치 작업 추가
            job_ids = []
            for idx, smiles in enumerate(smiles_list):
                if hasattr(self.batch_processor, 'add_job'):
                    job_id = self.batch_processor.add_job(smiles)
                    # N코드: job_id 결과 확인
                    if job_id is None:
                        logger.warning("add_job returned None for SMILES: %s", smiles[:60])
                    else:
                        job_ids.append(job_id)

                    # 진행률 업데이트
                    progress = int((idx + 1) / len(smiles_list) * 100)
                    self.progress_bar.setValue(progress)
                    self.progress_label.setText(f"{idx + 1}/{len(smiles_list)} 분자 처리 중... ({progress}%)")

                    # 결과 목록에 추가
                    display_smiles = smiles[:40] if len(smiles) > 40 else smiles
                    self.result_list.addItem(f"[OK] {display_smiles} (처리됨)")

                    # UI 업데이트
                    QApplication.processEvents()
                else:
                    logger.warning("batch_processor에 add_job 메서드 없음")

            # 처리 완료
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"처리 완료: {len(job_ids)}개 분자")
            logger.info("배치 처리 완료: %d/%d 분자", len(job_ids), len(smiles_list))
            QMessageBox.information(self, "성공", f"{len(job_ids)}개 분자의 배치 처리가 완료되었습니다.")
        except Exception as e:
            logger.warning("배치 처리 중 오류: %s", e)
            QMessageBox.critical(self, "오류", f"배치 처리 중 오류 발생: {str(e)}")
    
    def cancel_batch_processing(self):
        """배치 처리 취소"""
        if hasattr(self.batch_processor, 'cancel_all'):
            try:
                self.batch_processor.cancel_all()
            except Exception as e:
                logger.warning("배치 처리 취소 중 오류: %s", e)
        else:
            logger.warning("batch_processor에 cancel_all 메서드 없음")
        self.progress_label.setText("취소됨")
        self.progress_bar.setValue(0)
