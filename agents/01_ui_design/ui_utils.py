"""
ui_utils.py — ChemGrid UI 유틸리티 모듈
VERSION, CanvasMode, get_coord_key(), load_icon()
"""
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QPainter, QPen, QFont, QIcon, QPolygonF, QPixmap, QColor
from PyQt6.QtCore import Qt, QPointF


# ==========================================
# 상수 및 열거형
# ==========================================
VERSION = "v1.52"


class CanvasMode:
    MAIN = "Drawing"    # 메인 그리기 화면
    LEWIS = "Lewis"     # 루이스 구조 레이어
    THEORY = "Theory"   # 이론적 구조 레이어


# ==========================================
# 좌표 유틸리티
# ==========================================
def get_coord_key(point):
    """0.01 단위 정밀도 복구: 붙여넣기 시 미세 소수점 오차로 인한 분자 찌그러짐 방지"""
    return (round(point.x(), 2), round(point.y(), 2))


# ==========================================
# 아이콘 유틸리티
# ==========================================
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
# UI 컴포넌트 및 스타일 (New)
# ==========================================
class AIReportCard(QFrame):
    """
    [NEW] AI 종합 판독 카드 컴포넌트 (Master Plan v5)
    성공/경고/에러 상태에 따른 색상 코드 정의 (Green/Yellow/Red)
    """
    STATUS_SUCCESS = "success"
    STATUS_WARNING = "warning"
    STATUS_ERROR = "error"

    # 배경색 (파스텔 톤)
    COLORS = {
        STATUS_SUCCESS: "#d4edda",  # Light Green
        STATUS_WARNING: "#fff3cd",  # Light Yellow
        STATUS_ERROR: "#f8d7da",    # Light Red
    }
    # 텍스트/테두리 색 (진한 톤)
    TEXT_COLORS = {
        STATUS_SUCCESS: "#155724",  # Dark Green
        STATUS_WARNING: "#856404",  # Dark Yellow
        STATUS_ERROR: "#721c24",    # Dark Red
    }

    def __init__(self, title, message, status=STATUS_SUCCESS, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; border: none;")
        layout.addWidget(self.lbl_title)
        
        # Message
        self.lbl_message = QLabel(message)
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setStyleSheet("border: none;")
        layout.addWidget(self.lbl_message)
        
        self.update_style(status)

    def update_style(self, status):
        """상태에 따라 배경색 및 텍스트 색상 업데이트"""
        bg_color = self.COLORS.get(status, "#ffffff")
        text_color = self.TEXT_COLORS.get(status, "#000000")
        
        # QFrame 자체 스타일 설정
        self.setStyleSheet(f"""
            AIReportCard {{
                background-color: {bg_color};
                border: 1px solid {text_color};
                border-radius: 5px;
            }}
            QLabel {{
                color: {text_color};
                background-color: transparent;
            }}
        """)

    def set_message(self, title, message, status):
        """메시지 및 상태 업데이트"""
        self.lbl_title.setText(title)
        self.lbl_message.setText(message)
        self.update_style(status)


class SpectrumColorMap:
    """
    [NEW] 피크-구조 연동 시각화 (Color Mapping) 헬퍼 (Master Plan v5)
    스펙트럼의 주요 피크와 분자 구조의 해당 원자/결합을 동일한 색상으로 하이라이팅
    """
    # NMR 분석 결과(Zoning)에 따른 색상 띠 디자인에 활용될 팔레트 (고대비 색상)
    PALETTE = [
        "#E74C3C", # Red
        "#2ECC71", # Green
        "#3498DB", # Blue
        "#9B59B6", # Purple
        "#F1C40F", # Yellow
        "#E67E22", # Orange
        "#1ABC9C", # Teal
        "#34495E", # Navy
        "#D35400", # Pumpkin
        "#7F8C8D", # Gray
    ]

    @staticmethod
    def get_color(index):
        """인덱스에 해당하는 색상 반환 (순환)"""
        if index < 0: return "#000000"
        return SpectrumColorMap.PALETTE[index % len(SpectrumColorMap.PALETTE)]

    @staticmethod
    def get_qcolor(index):
        """인덱스에 해당하는 QColor 반환"""
        return QColor(SpectrumColorMap.get_color(index))
