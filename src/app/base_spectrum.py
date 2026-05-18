# base_spectrum.py (v1.0 — BaseSpectrumPopup 공통 추상 클래스)
"""
ChemGrid Phase 6/7: 분광학 팝업 공통 인터페이스
- 모든 분광학 팝업(IR/Raman, NMR, UV-Vis, Orbital, MD)의 추상 기반 클래스
- Agent 06의 통합 3D 팝업에 삽입 가능한 위젯 API 제공
- PDF 내보내기(spectrum_pdf_exporter) 연동 인터페이스
"""

import os
import logging
from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QWidget, QFileDialog, QMessageBox
)
from PyQt6.QtCore import pyqtSignal

logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))


# ABCMeta + PyQt6 sip.wrappertype 메타클래스 결합
class _ABCQMeta(ABCMeta, type(QDialog)):
    """Resolve metaclass conflict between ABCMeta and PyQt6's sip.wrappertype."""
    pass


class BaseSpectrumPopup(QDialog, metaclass=_ABCQMeta):
    """
    모든 분광학 팝업의 공통 추상 기반 클래스.

    서브클래스 필수 구현:
        _parse_data()             — ORCA 출력에서 스펙트럼 데이터 파싱
        _setup_ui()               — PyQt6 UI 구성
        get_spectrum_data_for_pdf() — PDF 내보내기용 데이터 반환

    선택 오버라이드:
        _export_to_file(filepath) — 커스텀 파일 내보내기
        get_embeddable_widget()   — 3D 팝업 탭 삽입용 위젯 반환

    시그널:
        data_loaded   — 데이터 파싱 완료 시 emit
        export_ready  — 내보내기 데이터 준비 완료 시 emit
    """

    # 시그널: 3D 팝업 등 외부에서 데이터 상태 변화를 구독할 수 있음
    data_loaded = pyqtSignal()
    export_ready = pyqtSignal()

    def __init__(self, orca_output_path: Optional[Path] = None, parent=None):
        """
        Args:
            orca_output_path: ORCA .out 파일 경로 (None이면 파일 선택 대화상자 사용)
            parent: 부모 위젯
        """
        super().__init__(parent)

        # N: Type guard — orca_output_path must be Path or None
        if orca_output_path is not None and not isinstance(orca_output_path, Path):
            logger.warning(
                "%s: orca_output_path is not Path — type=%s, converting",
                self.__class__.__name__, type(orca_output_path).__name__
            )
            try:
                orca_output_path = Path(str(orca_output_path))
            except Exception as e:
                logger.warning(
                    "%s: Path conversion failed: %s — setting to None",
                    self.__class__.__name__, e
                )
                orca_output_path = None

        self.orca_output_path = orca_output_path
        self.spectrum_data = None  # 서브클래스에서 파싱 결과 저장

        if orca_output_path is not None:
            if not orca_output_path.exists():
                # M: Silent failure 금지 — 파일 미존재 시 경고 로그
                logger.warning(
                    "%s: ORCA output file not found — %s",
                    self.__class__.__name__, orca_output_path
                )
            else:
                try:
                    self._parse_data()
                    self.data_loaded.emit()
                    logger.info(
                        "%s: 데이터 로드 완료 — %s",
                        self.__class__.__name__, orca_output_path.name
                    )
                except Exception as e:
                    # M: Silent failure 금지 — 구체적 에러 로깅
                    logger.warning(
                        "%s: 데이터 파싱 실패 — %s: %s",
                        self.__class__.__name__, orca_output_path, e
                    )

        self._setup_ui()

    # ------------------------------------------------------------------
    # 추상 메서드 (서브클래스 필수 구현)
    # ------------------------------------------------------------------

    @abstractmethod
    def _parse_data(self):
        """ORCA 출력(.out)에서 스펙트럼 데이터를 파싱하여 self.spectrum_data에 저장."""
        ...

    @abstractmethod
    def _setup_ui(self):
        """PyQt6 UI를 구성한다. (레이아웃, matplotlib 캔버스, 컨트롤 등)"""
        ...

    @abstractmethod
    def get_spectrum_data_for_pdf(self) -> Dict[str, Any]:
        """
        spectrum_pdf_exporter가 사용할 데이터 딕셔너리를 반환한다.

        반환 형식 예시::

            {
                "spectrum_type": "IR",
                "peaks": [SpectrumPeakData(...)],
                "image_path": "/path/to/plot.png",   # Optional
                "raw_data": { ... }                    # Optional
            }
        """
        ...

    # ------------------------------------------------------------------
    # 공통 유틸리티 메서드
    # ------------------------------------------------------------------

    def load_orca_file_dialog(self):
        """ORCA .out 파일 선택 대화상자를 열고 데이터를 파싱한다."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select ORCA output",
            "",
            "ORCA Files (*.out);;All Files (*)",
        )
        if not filepath:
            # M: Silent failure 금지 — 파일 미선택 로깅
            logger.info("%s: 파일 선택 취소됨", self.__class__.__name__)
            return

        # N: Type guard — filepath should be str
        if not isinstance(filepath, str):
            logger.warning(
                "%s: filepath is not str — type=%s",
                self.__class__.__name__, type(filepath).__name__
            )
            filepath = str(filepath)

        self.orca_output_path = Path(filepath)
        try:
            self._parse_data()
            self.data_loaded.emit()
            logger.info(
                "%s: 사용자 선택 파일 로드 — %s",
                self.__class__.__name__, filepath
            )
        except Exception as e:
            # M: Silent failure 금지 — 구체적 에러 메시지
            logger.warning(
                "%s: 파일 파싱 실패 — %s: %s",
                self.__class__.__name__, filepath, e
            )
            QMessageBox.critical(
                self, "Parse Error",
                f"Failed to parse ORCA output:\n{filepath}\n\nError: {e}"
            )

    def export_spectrum_dialog(self):
        """스펙트럼 이미지/PDF 내보내기 대화상자."""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Spectrum",
            "",
            "PNG Image (*.png);;PDF (*.pdf);;SVG (*.svg)",
        )
        if not filepath:
            # M: Silent failure 금지 — 파일 미선택 로깅
            logger.info("%s: 내보내기 취소됨", self.__class__.__name__)
            return

        # N: Type guard — filepath should be str
        if not isinstance(filepath, str):
            logger.warning(
                "%s: export filepath is not str — type=%s",
                self.__class__.__name__, type(filepath).__name__
            )
            filepath = str(filepath)

        try:
            self._export_to_file(filepath)
            logger.info(
                "%s: 내보내기 완료 — %s",
                self.__class__.__name__, filepath
            )
        except Exception as e:
            # M: Silent failure 금지 — 구체적 에러 메시지
            logger.warning(
                "%s: 내보내기 실패 — %s: %s",
                self.__class__.__name__, filepath, e
            )
            QMessageBox.critical(
                self, "Export Error",
                f"Failed to export spectrum:\n{filepath}\n\nError: {e}"
            )

    def _export_to_file(self, filepath: str):
        """
        파일 내보내기 기본 구현.
        matplotlib figure가 있으면 savefig, 없으면 경고 로그.
        서브클래스에서 오버라이드 가능.
        """
        if hasattr(self, "figure") and self.figure is not None:
            self.figure.savefig(filepath, dpi=300, bbox_inches="tight")
        else:
            logger.warning(
                "%s: figure 속성이 없어 내보내기 불가",
                self.__class__.__name__
            )

    # ------------------------------------------------------------------
    # 3D 팝업 삽입용 API (Phase 7 — Agent 06 연동)
    # ------------------------------------------------------------------

    def get_embeddable_widget(self) -> QWidget:
        """
        Agent 06의 통합 3D 팝업 탭에 삽입 가능한 QWidget을 반환한다.

        기본 구현: 자기 자신의 centralWidget 레이아웃을 복제하여 독립 위젯으로 제공.
        서브클래스에서 오버라이드하여 경량 위젯을 반환할 수 있다.

        Returns:
            QWidget — 탭에 삽입할 수 있는 위젯
        """
        # 기본 구현: 새 QWidget에 matplotlib canvas를 담아 반환
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        if hasattr(self, "canvas_widget") and self.canvas_widget is not None:
            # matplotlib FigureCanvas를 삽입
            layout.addWidget(self.canvas_widget)
        else:
            logger.warning(
                "%s: canvas_widget 속성이 없어 빈 위젯 반환",
                self.__class__.__name__
            )

        return container

    def get_spectrum_summary(self) -> Dict[str, Any]:
        """
        3D 팝업의 속성 탭에 표시할 스펙트럼 요약 정보를 반환한다.

        Returns:
            {
                "type": "IR",
                "num_peaks": 42,
                "dominant_peak": "1720 cm⁻¹",
                "status": "loaded" | "empty"
            }
        """
        status = "loaded" if self.spectrum_data else "empty"
        if status == "empty":
            # M: Silent failure 금지 — 빈 데이터일 때 로깅
            logger.warning(
                "%s: spectrum_data is empty/None — returning empty summary",
                self.__class__.__name__
            )
        return {
            "type": self.__class__.__name__,
            "num_peaks": 0,
            "dominant_peak": "N/A",
            "status": status,
        }
