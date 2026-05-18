"""
ui_utils.py — ChemGrid UI 유틸리티 모듈
VERSION, CanvasMode, get_coord_key(), load_icon()
"""
import logging
import os
from PyQt6.QtGui import QPainter, QPen, QFont, QIcon, QPolygonF, QPixmap
from PyQt6.QtCore import Qt, QPointF

logger = logging.getLogger(__name__)


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
    # N-code: isinstance guard for external point data
    if point is None:
        logger.warning("get_coord_key: point is None, returning (0, 0)")
        return (0.0, 0.0)
    if not hasattr(point, 'x') or not hasattr(point, 'y'):
        logger.warning("get_coord_key: point lacks x/y attributes, type=%s", type(point).__name__)
        if isinstance(point, (tuple, list)) and len(point) >= 2:
            return (round(float(point[0]), 2), round(float(point[1]), 2))
        return (0.0, 0.0)
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
        # N-code: isinstance guard for file_name
        if not isinstance(file_name, str):
            logger.warning("load_icon: file_name is not str, type=%s", type(file_name).__name__)
            file_name = str(file_name) if file_name is not None else ""
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
                    # M-code: no silent failure, use logger
                    logger.warning("load_icon: image file corrupted: %s", abs_file_name)
            except Exception as e:
                logger.warning("load_icon: image load failed: %s - %s", abs_file_name, e)
        else:
            logger.warning("load_icon: file not found: %s", abs_file_name)

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
