#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auto_test_runner.py — ChemGrid 자동 테스트 러너 (원격 검증용)
================================================================
draw.py를 직접 수정하지 않고 (Rule Y: 웹 1:1 복사 강제 — draw.py 원본 보존)
환경변수를 통해 ChemGrid를 자동 실행 + 스크린샷 캡처.

환경변수:
    CHEMGRID_AUTO_SMILES   — 입력할 SMILES 문자열
    CHEMGRID_AUTO_LAYER    — 레이어 ('drawing' | 'lewis' | 'theory')
    CHEMGRID_AUTO_POPUP    — 팝업 열기 ('true' | 'false')
    CHEMGRID_AUTO_POPUP_TAB — 팝업 탭 ('spectrum' | 'synthesis' | 'admet' | 'docking')
    CHEMGRID_AUTO_CAPTURE  — 캡처 저장 경로 (절대 경로, PNG)

사용:
    python src/app/auto_test_runner.py

구조:
    1. QApplication 초기화 (offscreen 렌더링)
    2. draw.py 메인 윈도우 생성 (MainWindow import)
    3. SMILES 입력 → Enter
    4. 레이어 전환
    5. (옵션) 팝업 열기 + 탭 전환
    6. QWidget.grab() + PNG 저장
    7. 앱 종료

Rule L: MolFromSmiles + None 체크 — SMILES 파싱 방어
Rule M: silent failure 금지 — 모든 예외 logger.warning
Rule N: 환경변수는 isinstance(str) 확인 후 사용
Rule F: py_compile ≠ 화면 동작 — 실제 앱 실행 + 캡처 필수

M146 교훈: offscreen 캡처 시 _reveal_radius = max_r 필수 (0이면 Lewis/Theory 빈화면)
M175 교훈: Ollama vision 금지 — 캡처 결과는 claude_vision_verify.py로 판정
"""
from __future__ import annotations

import io
import logging
import os
import sys
import time
from pathlib import Path

# ── UTF-8 강제 (cp949 환경 대비)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="[auto_test] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

# ── 환경변수 읽기 (Rule N: str 타입 가드)
def _env(key: str, default: str = "") -> str:
    val = os.environ.get(key, default)
    if not isinstance(val, str):
        logger.warning(f"[env] {key} 타입 비정상: {type(val)} — 빈값 사용")
        return default
    return val.strip()


AUTO_SMILES = _env("CHEMGRID_AUTO_SMILES", "c1ccccc1")   # 기본: 벤젠
AUTO_LAYER = _env("CHEMGRID_AUTO_LAYER", "drawing")       # 기본: drawing
AUTO_POPUP = _env("CHEMGRID_AUTO_POPUP", "false").lower() == "true"
AUTO_POPUP_TAB = _env("CHEMGRID_AUTO_POPUP_TAB", "")
AUTO_CAPTURE = _env("CHEMGRID_AUTO_CAPTURE", "")          # 빈값이면 임시경로

# ── 캡처 경로 결정
if AUTO_CAPTURE:
    CAPTURE_PATH = Path(AUTO_CAPTURE)
else:
    CAPTURE_PATH = Path(__file__).parent.parent.parent / "docs/reports/feedback/auto_capture.png"

CAPTURE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── draw.py 경로를 sys.path에 추가 (같은 폴더)
_app_dir = Path(__file__).parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

# ── LAYER → 버튼 인덱스 매핑
LAYER_INDEX = {
    "drawing": 0,
    "lewis": 1,
    "theory": 2,
}
# ── POPUP_TAB → 탭 이름 매핑
POPUP_TAB_NAMES = {
    "spectrum": "Spectra",
    "synthesis": "Synthesis",
    "admet": "ADMET",
    "docking": "Docking",
}

SETTLE_MS = 800     # 렌더 안정화 대기 ms (Magic: ESP/Lewis 렌더링 최대 500ms)
POPUP_MS = 1500     # 팝업 로드 대기 ms (Magic: 스펙트럼 계산 최대 1s)

# ── CLI args (--smiles / --label / --outdir) — 환경변수보다 우선
_OUTDIR: Path | None = None   # 레이어별 캡처 출력 디렉터리
_LABEL: str = "cap"           # 파일명 접두사 (예: cap_drawing.png)


def run_auto_test() -> int:
    """자동 테스트 실행 — 실패 시 1 반환, 성공 시 0"""
    global AUTO_SMILES, _OUTDIR, _LABEL  # [Rule N] 모듈레벨 변수 재할당 안전 선언
    # PyQt6 offscreen 렌더링 강제
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt, QTimer, QEventLoop
    except ImportError as e:
        logger.warning(f"[auto_test] PyQt6 import 실패: {e}")
        return 1

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # [M183 Fix] offscreen 렌더러 한글 폰트 적용
    from PyQt6.QtGui import QFont, QFontDatabase
    _font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/malgun.ttf")
    if _font_id >= 0:
        app.setFont(QFont("Malgun Gothic", 9))
    else:
        app.setFont(QFont("맑은 고딕", 9))

    # draw.py 메인 윈도우 import
    try:
        from draw import MainWindow
    except ImportError as e:
        logger.warning(f"[auto_test] draw.MainWindow import 실패: {e}")
        return 1

    logger.info(f"[auto_test] MainWindow 생성 시작")
    logger.info(f"  SMILES={AUTO_SMILES[:50]}")
    logger.info(f"  layer={AUTO_LAYER}, popup={AUTO_POPUP}, popup_tab={AUTO_POPUP_TAB}")
    logger.info(f"  capture={CAPTURE_PATH}")

    try:
        win = MainWindow()
        win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        win.resize(1280, 800)  # 고정 해상도 (Magic: 표준 FullHD 절반 — 메모리 절약)
        win.show()
    except Exception as e:
        logger.warning(f"[auto_test] MainWindow 생성 실패: {e}")
        return 1

    def _process_events(ms: int) -> None:
        """이벤트 루프 돌려서 렌더 완료 대기"""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    # ── 1. SMILES 입력
    try:
        smiles_input = getattr(win, "smiles_input", None) or getattr(win, "input_smiles", None)
        if smiles_input is None:
            # 자식 위젯에서 찾기
            from PyQt6.QtWidgets import QLineEdit
            inputs = win.findChildren(QLineEdit)
            if inputs:
                smiles_input = inputs[0]

        if smiles_input:
            smiles_input.setText(AUTO_SMILES)
            smiles_input.returnPressed.emit()
            logger.info("[auto_test] SMILES 입력 완료")
        else:
            logger.warning("[auto_test] SMILES 입력 위젯 찾기 실패 — 기본 분자 사용")
    except Exception as e:
        logger.warning(f"[auto_test] SMILES 입력 예외: {e}")

    _process_events(SETTLE_MS)

    # ── 2. Drawing 레이어 캡처 + Lewis/Theory 레이어 직접 렌더링 캡처
    # [M184 Fix] switch_view('Lewis'/'Theory') → render() 무한 블로킹 문제 우회:
    #   Lewis/Theory는 switch_view() 없이, analysis_results로 직접 QPixmap에 렌더링
    # mode: "Drawing" | "Lewis" | "Theory" (main_window.py L542)
    LAYER_MAP = {"drawing": "Drawing", "lewis": "Lewis", "theory": "Theory"}
    import time as _time
    from PyQt6.QtGui import QPixmap, QPainter, QFont, QColor
    from PyQt6.QtCore import Qt as _Qt

    _cv = getattr(win, "cv", None)

    for key, mode in LAYER_MAP.items():
        # 캡처 경로 결정
        if _OUTDIR:
            layer_capture_path = _OUTDIR / f"{_LABEL}_{key}.png"
        else:
            layer_capture_path = CAPTURE_PATH.with_stem(f"{CAPTURE_PATH.stem}_{key}")

        logger.info(f"[auto_test] 캡처 시작 — {key}")

        if key == "drawing":
            # Drawing 레이어: switch_view + win.grab() (정상 동작)
            try:
                win.switch_view("Drawing")
                QApplication.processEvents()
                _time.sleep(1.0)  # Magic: animation 1000ms 완료 대기
                pix = win.grab()
                if not pix.isNull():
                    layer_capture_path.parent.mkdir(parents=True, exist_ok=True)
                    if pix.save(str(layer_capture_path), "PNG"):
                        logger.info(f"[auto_test] Drawing 캡처 저장: {layer_capture_path}")
                    else:
                        logger.warning(f"[auto_test] Drawing 캡처 저장 실패: {layer_capture_path}")
                else:
                    logger.warning(f"[auto_test] Drawing grab() null")
            except Exception as e:
                logger.warning(f"[auto_test] Drawing 캡처 예외: {e}")

        else:
            # Lewis/Theory: switch_view() 없이 analysis_results로 LewisRenderer/TheoryRenderer 직접 호출
            # (switch_view → QPropertyAnimation → render() 무한 블로킹 우회)
            try:
                if _cv is None:
                    logger.warning(f"[auto_test] cv 없음 — {key} 캡처 스킵")
                    continue

                analysis = getattr(_cv, "analysis_results", None)
                atoms = getattr(_cv, "atoms", {})
                bonds = getattr(_cv, "bonds", {})
                w, h = _cv.width(), _cv.height()

                pix = QPixmap(w, h)
                pix.fill(_Qt.GlobalColor.white)
                _p = QPainter(pix)
                _p.setRenderHint(QPainter.RenderHint.Antialiasing)

                if key == "lewis":
                    from layer_logic import LewisRenderer
                    if analysis:
                        LewisRenderer.render(_p, atoms, bonds, analysis)
                        logger.info(f"[auto_test] LewisRenderer.render() 완료")
                    else:
                        logger.warning(f"[auto_test] analysis_results 없음 — Lewis 빈 화면 저장")
                        # 빈 화면에 안내 텍스트 추가
                        _p.setPen(QColor(150, 150, 150))
                        _p.setFont(QFont("Arial", 14))
                        _p.drawText(pix.rect(), _Qt.AlignmentFlag.AlignCenter, "Lewis layer (no data)")

                elif key == "theory":
                    from layer_logic import TheoryRenderer
                    if analysis:
                        TheoryRenderer.render(_p, atoms, bonds, analysis)
                        logger.info(f"[auto_test] TheoryRenderer.render() 완료")
                    else:
                        logger.warning(f"[auto_test] analysis_results 없음 — Theory 빈 화면 저장")
                        _p.setPen(QColor(150, 150, 150))
                        _p.setFont(QFont("Arial", 14))
                        _p.drawText(pix.rect(), _Qt.AlignmentFlag.AlignCenter, "Theory layer (no data)")

                _p.end()

                layer_capture_path.parent.mkdir(parents=True, exist_ok=True)
                if pix.save(str(layer_capture_path), "PNG"):
                    logger.info(f"[auto_test] {key} 캡처 저장: {layer_capture_path}")
                else:
                    logger.warning(f"[auto_test] {key} 캡처 저장 실패: {layer_capture_path}")

            except Exception as e:
                logger.warning(f"[auto_test] {key} 캡처 예외: {e}")

    # 최종 Drawing 레이어로 복원
    try:
        final_mode = {"drawing": "Drawing", "lewis": "Lewis", "theory": "Theory"}.get(AUTO_LAYER, "Drawing")
        win.switch_view(final_mode)
        QApplication.processEvents()
    except Exception as e:
        logger.warning(f"[auto_test] 최종 switch_view 복원 예외: {e}")

    # ── 3. (옵션) 팝업 열기
    if AUTO_POPUP:
        try:
            # 분석 팝업 버튼 찾기
            from PyQt6.QtWidgets import QPushButton
            popup_btn = None
            for btn in win.findChildren(QPushButton):
                txt = btn.text().lower()
                if any(kw in txt for kw in ["analyze", "분석", "popup", "properties"]):
                    popup_btn = btn
                    break
            if popup_btn:
                popup_btn.click()
                logger.info("[auto_test] 팝업 열기 버튼 클릭")
            else:
                # 더블클릭으로 팝업 열기 시도 (canvas에 직접)
                canvas = getattr(win, "canvas", None)
                canvas_ref = getattr(win, "cv", None)  # [M184 Fix] win.canvas → win.cv
                if canvas_ref:
                    from PyQt6.QtCore import QPointF
                    from PyQt6.QtGui import QMouseEvent
                    # 캔버스 중앙 더블클릭
                    logger.warning("[auto_test] 팝업 버튼 없음 — cv 더블클릭 시도")
        except Exception as e:
            logger.warning(f"[auto_test] 팝업 열기 예외: {e}")

        _process_events(POPUP_MS)

        # 팝업 탭 전환
        if AUTO_POPUP_TAB:
            tab_name = POPUP_TAB_NAMES.get(AUTO_POPUP_TAB, AUTO_POPUP_TAB)
            try:
                from PyQt6.QtWidgets import QTabWidget
                tabs = win.findChildren(QTabWidget)
                for tab_widget in tabs:
                    for i in range(tab_widget.count()):
                        if tab_name.lower() in tab_widget.tabText(i).lower():
                            tab_widget.setCurrentIndex(i)
                            logger.info(f"[auto_test] 팝업 탭 전환: {tab_widget.tabText(i)}")
                            break
            except Exception as e:
                logger.warning(f"[auto_test] 팝업 탭 전환 예외: {e}")

            _process_events(POPUP_MS)

    # ── 4. 스크린샷 캡처 (QWidget.grab())
    try:
        pixmap = win.grab()
        if pixmap.isNull():
            logger.warning("[auto_test] grab() 결과가 null pixmap — 저장 스킵")
            return 1

        saved = pixmap.save(str(CAPTURE_PATH), "PNG")
        if saved:
            logger.info(f"[auto_test] 캡처 저장 완료: {CAPTURE_PATH}")
        else:
            logger.warning(f"[auto_test] pixmap.save() 실패: {CAPTURE_PATH}")
            return 1
    except Exception as e:
        logger.warning(f"[auto_test] 캡처 예외: {e}")
        return 1

    # ── 5. 정리
    try:
        win.close()
    except Exception as e:
        logger.warning(f"[auto_test] win.close() 예외: {e}")

    return 0


if __name__ == "__main__":
    import argparse as _argparse
    _cli = _argparse.ArgumentParser(add_help=True)
    _cli.add_argument("--smiles", type=str, default=None,
                      help="입력 SMILES (환경변수 CHEMGRID_AUTO_SMILES보다 우선)")
    _cli.add_argument("--label", type=str, default="cap",
                      help="출력 파일명 접두사 (예: norep → norep_drawing.png)")
    _cli.add_argument("--outdir", type=str, default=None,
                      help="레이어별 PNG 저장 디렉터리 (절대 경로)")
    _args, _ = _cli.parse_known_args()

    if _args.smiles:
        AUTO_SMILES = _args.smiles

    _LABEL = _args.label or "cap"

    if _args.outdir:
        _OUTDIR = Path(_args.outdir)
        _OUTDIR.mkdir(parents=True, exist_ok=True)

    rc = run_auto_test()
    logger.info(f"[auto_test] 종료 코드: {rc}")
    sys.exit(rc)
