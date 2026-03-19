# error_handler.py - 중앙 집중식 오류 처리 시스템
"""
ChemGrid Pro Error Handling System
- 모든 오류를 중앙에서 처리
- 사용자 친화적 메시지 제공
- 로깅 및 추적 기능
"""

import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import pyqtSignal, QObject, Qt


class ErrorHandler(QObject):
    """중앙 집중식 오류 처리 및 로깅"""
    
    error_occurred = pyqtSignal(str, str)  # (error_type, message)
    
    _instance = None
    _logger = None
    
    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """ErrorHandler 초기화"""
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        self.setup_logging()
    
    @staticmethod
    def instance():
        """싱글톤 인스턴스 반환"""
        return ErrorHandler()
    
    def setup_logging(self):
        """로깅 시스템 설정"""
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"chemGrid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        self._logger = logging.getLogger("ChemGridPro")
        self._logger.info("=" * 60)
        self._logger.info("ChemGrid Pro 시작")
        self._logger.info("=" * 60)
    
    def handle_error(
        self,
        error_type: str,
        exception: Optional[Exception] = None,
        context: str = "",
        show_dialog: bool = True,
        severity: str = "ERROR"
    ):
        """
        오류 처리
        
        Args:
            error_type: "ORCA", "PHASE_B", "PHASE_C", "PHASE_D", "SMILES", "IMPORT" 등
            exception: Exception 객체 (선택사항)
            context: 오류 발생 위치/상황 설명
            show_dialog: 사용자 팝업 표시 여부
            severity: "ERROR", "WARNING", "CRITICAL"
        """
        
        # 로깅
        if exception:
            error_msg = f"[{error_type}] {context}\n{traceback.format_exc()}"
        else:
            error_msg = f"[{error_type}] {context}"
        
        if severity == "ERROR":
            self._logger.error(error_msg)
        elif severity == "WARNING":
            self._logger.warning(error_msg)
        elif severity == "CRITICAL":
            self._logger.critical(error_msg)
        
        # 사용자 메시지 생성
        user_msg = self._get_user_friendly_message(error_type, exception, context)
        
        # 신호 발출
        self.error_occurred.emit(error_type, user_msg)
        
        # 팝업 표시
        if show_dialog:
            icon_type = {
                "ERROR": QMessageBox.Icon.Warning,
                "WARNING": QMessageBox.Icon.Information,
                "CRITICAL": QMessageBox.Icon.Critical
            }.get(severity, QMessageBox.Icon.Warning)
            
            msg_box = QMessageBox()
            msg_box.setIcon(icon_type)
            msg_box.setWindowTitle(f"오류: {error_type}")
            msg_box.setText(user_msg)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.setDetailedText(str(exception) if exception else "")
            msg_box.exec()
    
    def _get_user_friendly_message(
        self,
        error_type: str,
        exception: Optional[Exception],
        context: str
    ) -> str:
        """오류 타입별 사용자 친화적 메시지 생성"""
        
        messages = {
            "ORCA": {
                "default": """
ORCA 계산 중 오류가 발생했습니다.

📋 확인사항:
• Orca.6.1.1 경로가 올바른지 확인하세요
• 분자 구조를 다시 확인하세요
• 디스크 공간이 충분한지 확인하세요
• ORCA 설치가 올바른지 확인하세요

💡 해결방법:
1. 분자를 다시 그려보세요
2. 간단한 분자부터 시도하세요
3. 로그 파일을 확인하세요 (logs/ 폴더)
""",
                "TimeoutExpired": """
ORCA 계산이 5분 이내에 완료되지 않았습니다.

📋 원인:
• 계산이 너무 복잡함
• 시스템 리소스 부족
• ORCA 설치 문제

💡 해결방법:
1. 더 간단한 분자부터 시도하세요
2. 기저 집합을 줄여보세요 (STO-3G 등)
3. 시스템 리소스를 확인하세요
""",
                "convergence": """
ORCA 최적화가 수렴하지 않았습니다.

📋 원인:
• 초기 기하가 나쁨
• 너무 엄격한 수렴 기준

💡 해결방법:
1. 분자를 다시 정렬해보세요
2. 완화된 기준으로 다시 계산해보세요
3. 다른 이론적 수준을 시도하세요
"""
            },
            
            "PHASE_B": {
                "default": """
ESP 계산 중 오류가 발생했습니다.

📋 확인사항:
• ORCA 계산이 성공적으로 완료되었는지 확인하세요
• 전자 밀도 데이터가 정상인지 확인하세요

💡 해결방법:
1. ORCA 계산을 다시 수행하세요
2. 전자 밀도 데이터를 재생성하세요
"""
            },
            
            "PHASE_C": {
                "default": """
3D 뷰어를 열 수 없습니다.

📋 확인사항:
• OpenGL이 지원되는지 확인하세요
• GPU 드라이버가 최신인지 확인하세요
• 시스템 메모리가 충분한지 확인하세요

💡 해결방법:
1. 소프트웨어 렌더링 모드를 사용하세요
2. GPU 드라이버를 업데이트하세요
3. 간단한 분자부터 시도하세요
"""
            },
            
            "PHASE_D": {
                "default": """
IUPAC 분석 중 오류가 발생했습니다.

📋 확인사항:
• 분자식이 유효한지 확인하세요
• RDKit가 올바르게 설치되었는지 확인하세요

💡 해결방법:
1. 분자를 다시 그려보세요
2. 간단한 분자부터 시도하세요
3. RDKit을 재설치하세요: pip install rdkit
"""
            },
            
            "SMILES": {
                "default": """
SMILES 생성 중 오류가 발생했습니다.

📋 확인사항:
• 분자 구조가 유효한지 확인하세요
• 웨지/대쉬가 올바르게 표시되었는지 확인하세요

💡 해결방법:
1. 분자를 다시 그려보세요
2. 간단한 분자부터 시도하세요
"""
            },
            
            "IMPORT": {
                "default": """
파일 불러오기 중 오류가 발생했습니다.

📋 확인사항:
• 파일 형식이 올바른지 확인하세요
• 파일이 손상되지 않았는지 확인하세요

💡 해결방법:
1. 다른 파일을 시도해보세요
2. 파일을 다시 저장하고 불러오세요
"""
            },
            
            "EXPORT": {
                "default": """
파일 저장 중 오류가 발생했습니다.

📋 확인사항:
• 저장 위치에 쓰기 권한이 있는지 확인하세요
• 디스크 공간이 충분한지 확인하세요

💡 해결방법:
1. 다른 위치에 저장해보세요
2. 파일 이름을 변경하고 시도하세요
""",
                "pdf_reportlab": """
PDF 내보내기 중 오류가 발생했습니다.

📋 확인사항:
• reportlab 라이브러리가 설치되었는지 확인하세요
• 출력 경로에 쓰기 권한이 있는지 확인하세요

💡 해결방법:
1. pip install reportlab 을 실행하세요
2. 다른 위치에 저장해보세요
3. QPrinter 기반 PDF 대체 모드가 자동 사용됩니다
""",
                "chem_save": """
.chem 파일 저장 중 오류가 발생했습니다.

📋 확인사항:
• 저장 경로가 유효한지 확인하세요
• 디스크 공간이 충분한지 확인하세요

💡 해결방법:
1. 다른 위치에 저장해보세요
2. 파일 이름에 특수문자가 없는지 확인하세요
""",
                "chem_load": """
.chem 파일 불러오기 중 오류가 발생했습니다.

📋 확인사항:
• 파일이 손상되지 않았는지 확인하세요
• 파일 형식이 올바른지 확인하세요 (JSON 기반)

💡 해결방법:
1. 다른 .chem 파일을 시도해보세요
2. 파일을 텍스트 편집기로 열어 JSON 구문 확인
3. v1 / v2 형식 모두 지원됩니다
"""
            },
            
            "THREAD": {
                "default": """
백그라운드 작업 중 오류가 발생했습니다.

📋 확인사항:
• 시스템 리소스가 충분한지 확인하세요
• 다른 프로그램이 리소스를 차단하지 않는지 확인하세요

💡 해결방법:
1. 프로그램을 재시작하세요
2. 다른 프로그램을 종료하고 다시 시도하세요
"""
            }
        }
        
        # 오류 타입별 메시지 선택
        type_messages = messages.get(error_type, {})
        
        # 특정 예외 타입별 메시지
        if exception:
            exc_type = type(exception).__name__
            exc_str = str(exception).lower()
            
            # 키워드 기반 세부 메시지 선택
            if "timeout" in exc_str:
                return type_messages.get("TimeoutExpired", type_messages.get("default", "오류가 발생했습니다."))
            elif "convergence" in exc_str or "converged" in exc_str:
                return type_messages.get("convergence", type_messages.get("default", "오류가 발생했습니다."))
            elif "reportlab" in exc_str:
                return type_messages.get("pdf_reportlab", type_messages.get("default", "오류가 발생했습니다."))
            elif ".chem" in exc_str and "save" in exc_str:
                return type_messages.get("chem_save", type_messages.get("default", "오류가 발생했습니다."))
            elif ".chem" in exc_str and "load" in exc_str:
                return type_messages.get("chem_load", type_messages.get("default", "오류가 발생했습니다."))
        
        # 기본 메시지
        return type_messages.get("default", f"오류가 발생했습니다:\n{context}")
    
    def info(self, message: str, context: str = ""):
        """정보 메시지 로깅"""
        msg = f"{context}: {message}" if context else message
        self._logger.info(msg)
    
    def warning(self, message: str, context: str = ""):
        """경고 메시지 로깅"""
        msg = f"{context}: {message}" if context else message
        self._logger.warning(msg)
    
    def debug(self, message: str, context: str = ""):
        """디버그 메시지 로깅"""
        msg = f"{context}: {message}" if context else message
        self._logger.debug(msg)


# 편의 함수
def error(error_type: str, exception: Exception = None, context: str = "", show_dialog: bool = True):
    """전역 오류 처리 함수"""
    ErrorHandler.instance().handle_error(error_type, exception, context, show_dialog, "ERROR")


def warning(error_type: str, exception: Exception = None, context: str = "", show_dialog: bool = True):
    """전역 경고 처리 함수"""
    ErrorHandler.instance().handle_error(error_type, exception, context, show_dialog, "WARNING")


def critical(error_type: str, exception: Exception = None, context: str = "", show_dialog: bool = True):
    """전역 심각한 오류 처리 함수"""
    ErrorHandler.instance().handle_error(error_type, exception, context, show_dialog, "CRITICAL")
